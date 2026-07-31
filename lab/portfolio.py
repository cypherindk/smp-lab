"""
lab/portfolio.py — 3-STRATEJILI COK-STRATEJI PORTFOY (fonların yaptigi cesitlendirme).
Her stratejiyi GUNLUK getiri serisine cevir -> korelasyon + risk-parity birlesik
portfoy. 30 coin. Actions'ta kosar (binance.vision + OKX acik). Sadece LAB.

  SMP v2  : 30 coin, A+ + ER>0.15, SL/TP -> islem R'leri cikis gunune (chop rejimi)
  Trend   : 30 coin, gunluk Donchian 55/20 + ER>0.50 + vol-target (trend rejimi)
  Carry   : 10 coin, OKX funding, delta-notr (piyasa-notr stabilizator)
Beklenti: birlesik Sharpe HER BACAKTAN yuksek (dusuk korelasyon), drawdown dusuk.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.crypto_fetcher import fetch_binance_ohlcv
from lab.breadth_wide import WIDE, efficiency_ratio, base_signals, gated
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


def smp_daily(risk=0.02):
    print("  SMP v2 gunluk getiri...", flush=True)
    daily = {}
    for c in WIDE:
        try:
            df = fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True)
            if len(df) < 300:
                continue
            ind, fs = base_signals(df, WIDE[c][0])
            fs = gated(fs, efficiency_ratio(df["close"], 20) > 0.15)
            t = backtest(df, ind, fs, WIDE[c][1])
            for _, r in t.iterrows():
                d = pd.Timestamp(r["exit_time"])
                d = (d.tz_localize(None) if d.tzinfo else d).normalize()
                daily[d] = daily.get(d, 0.0) + r["R"] * risk
        except Exception:
            pass
    return pd.Series(daily).sort_index()


def trend_daily():
    print("  Trend motoru gunluk getiri...", flush=True)
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


def carry_daily():
    print("  Carry gunluk getiri (OKX funding)...", flush=True)
    ser = {}
    for c in CARRY_COINS:
        f = fetch_okx_funding(c, DAYS)
        if f.empty:
            continue
        f.index = _naive_day(f.index)
        ser[c] = f.groupby(f.index).sum()
    if not ser:
        return pd.Series(dtype=float)
    return pd.concat(ser, axis=1).mean(axis=1)


def stats(r, ppy=365):
    r = r.dropna()
    if len(r) < 20:
        return dict(sharpe=0, cagr=0, maxdd=0)
    eq = (1 + r).cumprod()
    return dict(sharpe=r.mean() / r.std() * np.sqrt(ppy) if r.std() > 0 else 0,
                cagr=(eq.iloc[-1] ** (ppy / len(r)) - 1) * 100 if eq.iloc[-1] > 0 else -100,
                maxdd=(eq / eq.cummax() - 1).min() * 100)


def main():
    print("=" * 84 + "\n  3-STRATEJILI PORTFOY — 30 coin (SMP v2 + Trend + Carry)\n" + "=" * 84, flush=True)
    legs = {"SMP v2": smp_daily(), "Trend": trend_daily(), "Carry": carry_daily()}
    M = pd.concat(legs, axis=1).fillna(0.0)
    M = M[(M.index >= M.index.min())]  # ortak takvim (union, bosluk=0 getiri)

    print(f"\n{'Bacak (standalone, gunluk)':26} | {'Sharpe':>7} {'CAGR':>8} {'MaxDD':>8}", flush=True)
    print("-" * 60, flush=True)
    for name in legs:
        s = stats(M[name])
        print(f"{name:26} | {s['sharpe']:7.2f} {s['cagr']:7.1f}% {s['maxdd']:7.1f}%", flush=True)

    print("\n  Korelasyon (dusuk = iyi cesitlendirme):", flush=True)
    corr = M.corr()
    print(f"    SMP-Trend : {corr.loc['SMP v2','Trend']:+.2f}   SMP-Carry : {corr.loc['SMP v2','Carry']:+.2f}   "
          f"Trend-Carry: {corr.loc['Trend','Carry']:+.2f}", flush=True)

    # risk-parity: her bacagi %10 yillik vol'a olcekle, esit agirlik
    tv = 0.10
    scaled = []
    for name in legs:
        v = M[name].std() * np.sqrt(365)
        scaled.append(M[name] * (tv / v) if v > 0 else M[name] * 0)
    combined = sum(scaled) / len(scaled)
    sc = stats(combined)
    best_single = max(stats(M[n])["sharpe"] for n in legs)
    print("\n" + "=" * 60, flush=True)
    print(f"  BIRLESIK (risk-parity, %10 vol/bacak): Sharpe {sc['sharpe']:.2f} | "
          f"CAGR {sc['cagr']:.1f}% | MaxDD {sc['maxdd']:.1f}%", flush=True)
    print(f"  En iyi TEK bacak Sharpe: {best_single:.2f}  ->  "
          f"{'BIRLESIK DAHA IYI (cesitlendirme calisti)' if sc['sharpe'] > best_single else 'birlesik dusuk'}", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
