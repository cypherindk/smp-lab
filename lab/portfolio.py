"""
lab/portfolio.py — 3-STRATEJILI PORTFOY (A+B+C).
  A) Carry GERCEK risk: funding + basis P&L (OKX perp vs binance spot) -> realistik Sharpe
  B) SMP rafine: RSI cikarilmis (ablation'da zararliydi) vs full — kiyas
  C) Olcek taramasi: birlesik 1x..3x -> CAGR/DD
Actions'ta kosar (binance.vision + OKX acik). Sadece LAB.
"""
import os
import sys
import time
import requests
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.crypto_fetcher import fetch_binance_ohlcv
from engine.indicators import compute_all_indicators
from engine.signals import calc_bull_bear_score, calc_triggers, generate_signals
from engine.filters import apply_all_filters
from lab.breadth_wide import WIDE, efficiency_ratio, gated
from lab.backtest_smp import backtest
from backtest.trend_engine import vol_target_returns, portfolio_returns
from strategies.ts_momentum import sig_donchian
from strategies import quant_engine as qe
from lab.carry_test import fetch_okx_funding, COINS as CARRY_COINS

DAYS = 600


def _naive_day(idx):
    idx = pd.DatetimeIndex(idx)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return idx.normalize()


def stats(r, ppy=365):
    r = r.dropna()
    if len(r) < 20:
        return dict(sharpe=0, cagr=0, maxdd=0)
    eq = (1 + r).cumprod()
    return dict(sharpe=r.mean() / r.std() * np.sqrt(ppy) if r.std() > 0 else 0,
                cagr=(eq.iloc[-1] ** (ppy / len(r)) - 1) * 100 if eq.iloc[-1] > 0 else -100,
                maxdd=(eq / eq.cummax() - 1).min() * 100)


def smp_daily(drop=None, risk=0.02):
    daily = {}
    for c in WIDE:
        try:
            df = fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True)
            if len(df) < 300:
                continue
            ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=240, adr_mult=WIDE[c][0])
            sc = calc_bull_bear_score(ind, mtf=None, drop=drop)
            tr = calc_triggers(ind, sc)
            sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                                  min_conf=2, grade_filter="A+ Only")
            fs = apply_all_filters(ind, sg, use_cvd=True)
            fs = gated(fs, efficiency_ratio(df["close"], 20) > 0.15)
            for _, r in backtest(df, ind, fs, WIDE[c][1]).iterrows():
                d = pd.Timestamp(r["exit_time"])
                d = (d.tz_localize(None) if d.tzinfo else d).normalize()
                daily[d] = daily.get(d, 0.0) + r["R"] * risk
        except Exception:
            pass
    return pd.Series(daily).sort_index()


def trend_daily():
    nets = {}
    for c in WIDE:
        try:
            df = fetch_binance_ohlcv(c, interval="1d", days=DAYS + 200, quiet=True)
            if len(df) < 260:
                continue
            pos = sig_donchian(df, 55, 20, 200, long_only=True).where(
                qe.regime_is_trend(df, "er", er_thr=0.50), 0.0)
            nets[c] = vol_target_returns(df, pos, "1d")
        except Exception:
            pass
    port = portfolio_returns(nets)
    port.index = _naive_day(port.index)
    return port.groupby(port.index).sum()


def okx_perp_daily_close(coin, days):
    url = "https://www.okx.com/api/v5/market/candles"
    end = int(time.time() * 1000); start = end - days * 86400 * 1000
    out, after = [], None
    while True:
        p = {"instId": f"{coin}-USDT-SWAP", "bar": "1D", "limit": 100}
        if after:
            p["after"] = after
        try:
            data = requests.get(url, params=p, timeout=20).json().get("data", [])
        except Exception:
            break
        if not data:
            break
        for row in data:
            out.append((int(row[0]), float(row[4])))
        oldest = int(data[-1][0])
        if oldest <= start or len(data) < 100:
            break
        after = oldest; time.sleep(0.1)
    if not out:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(t, unit="ms").normalize(): v for t, v in out}).sort_index()
    return s[~s.index.duplicated()]


def carry_daily(realistic=True):
    """A: realistic -> funding + basis P&L. perp/spot alinamazsa funding-only fallback."""
    ser, nb = {}, 0
    for c in CARRY_COINS:
        f = fetch_okx_funding(c, DAYS)
        if f.empty:
            continue
        f.index = _naive_day(f.index)
        fd = f.groupby(f.index).sum()                       # gunluk funding (her zaman)
        if realistic:
            try:
                perp = okx_perp_daily_close(c, DAYS)
                spot = fetch_binance_ohlcv(c, interval="1d", days=DAYS, quiet=True)["close"]
                spot.index = _naive_day(spot.index)
                if not perp.empty and not spot.empty:
                    basis = spot.pct_change() - perp.pct_change()   # delta-notr fiyat P&L
                    d = pd.DataFrame({"f": fd, "b": basis}).fillna(0.0)
                    fd = d["f"] + d["b"]
                    nb += 1
            except Exception:
                pass
        ser[c] = fd
    print(f"    (carry: {len(ser)} coin yuklendi, {nb} tanesi basis-riskli)", flush=True)
    if not ser:
        return pd.Series(dtype=float)
    return pd.concat(ser, axis=1).mean(axis=1)


def main():
    print("=" * 84 + "\n  3-STRATEJILI PORTFOY (A: realistik carry, B: SMP-noRSI, C: olcek)\n" + "=" * 84, flush=True)
    print("  SMP full...", flush=True); smp_full = smp_daily(drop=None)
    print("  SMP no-RSI (B)...", flush=True); smp_norsi = smp_daily(drop={"rsi"})
    print("  Trend...", flush=True); trend = trend_daily()
    print("  Carry realistik (A)...", flush=True); carry = carry_daily(realistic=True)

    # [FIX] tum bacaklari ORTAK YOGUN gunluk takvime hizala. SMP/carry seyrek
    # (sadece islem/funding gunleri) -> 0-fill; yoksa yillıklaştırma patlar (69028%!).
    ai = smp_full.index.union(smp_norsi.index).union(trend.index).union(carry.index)
    master = pd.date_range(ai.min(), ai.max(), freq="D")
    smp_full = smp_full.reindex(master).fillna(0.0)
    smp_norsi = smp_norsi.reindex(master).fillna(0.0)
    trend = trend.reindex(master).fillna(0.0)
    carry = carry.reindex(master).fillna(0.0)

    print(f"\n{'Bacak (standalone)':22} | {'Sharpe':>7} {'CAGR':>8} {'MaxDD':>8}", flush=True)
    print("-" * 52, flush=True)
    for name, r in [("SMP full", smp_full), ("SMP no-RSI (B)", smp_norsi),
                    ("Trend", trend), ("Carry realistik (A)", carry)]:
        s = stats(r)
        print(f"{name:22} | {s['sharpe']:7.2f} {s['cagr']:7.1f}% {s['maxdd']:7.1f}%", flush=True)

    smp = smp_norsi if stats(smp_norsi)["sharpe"] >= stats(smp_full)["sharpe"] else smp_full
    legs = {"SMP": smp, "Trend": trend, "Carry": carry}
    M = pd.concat(legs, axis=1).fillna(0.0)
    corr = M.corr()
    print(f"\n  Korelasyon: SMP-Trend {corr.loc['SMP','Trend']:+.2f}  "
          f"SMP-Carry {corr.loc['SMP','Carry']:+.2f}  Trend-Carry {corr.loc['Trend','Carry']:+.2f}", flush=True)

    tv = 0.10
    scaled = [M[n] * (tv / (M[n].std() * np.sqrt(365))) if M[n].std() > 0 else M[n] * 0 for n in legs]
    combined = sum(scaled) / len(scaled)

    print("\n  C) OLCEK TARAMASI (birlesik portfoy):", flush=True)
    print(f"  {'olcek':>6} | {'CAGR':>8} {'MaxDD':>8} {'Sharpe':>7}", flush=True)
    for k in [1.0, 1.5, 2.0, 3.0]:
        s = stats(combined * k)
        print(f"  {k:5.1f}x | {s['cagr']:7.1f}% {s['maxdd']:7.1f}% {s['sharpe']:7.2f}", flush=True)
    print("\n  NOT: A ile carry artik basis-riskli (realistik). Backtest/tek rejim; canlida duser.", flush=True)


if __name__ == "__main__":
    main()
