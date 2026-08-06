"""
live/validate.py — MIMARI DOGRULAYICI (paylasimli-sermaye backtest).

portfolio.py soyut getiri-serisi birlestiriyordu; BU, gercek mimariyi kosar:
  * SMP sleeve: KRONOLOJIK discrete islemler, fixed-fractional risk_pct, MAX_CONC
    es zamanlilik, guncel sermaye uzerinden bilesiklenir (compound.py mantigi + egri)
  * Trend sleeve: gunluk vol-hedefli getiri, kendi alt-hesabinda bilesiklenir
  * Toplam equity = iki sleeve'in gunluk toplami -> tek egri, gercek CAGR/DD/Sharpe
$100'den, olcek 1x/1.5x/2x. Actions'ta (binance.vision) kosar. Sadece LAB.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.crypto_fetcher import fetch_binance_ohlcv
from engine.indicators import compute_all_indicators
from engine.signals import calc_bull_bear_score, calc_triggers, generate_signals
from engine.filters import apply_all_filters
from lab.breadth_wide import WIDE, efficiency_ratio, gated
from lab.backtest_smp import backtest
from lab.portfolio import trend_daily
from core import (RISK_PCT, MAX_CONC, SMP_ALLOC, TREND_ALLOC, TREND_VOL, ER_MIN,
                  TARGET_VOL, VOL_MULT_LO, VOL_MULT_HI)

DAYS = 600


def _naive(ts):
    ts = pd.Timestamp(ts)
    return ts.tz_localize(None) if ts.tzinfo else ts


def btc_vol_series():
    """BTC yillik realized vol serisi (180 4H-bar ~30 gun penceresi)."""
    df = fetch_binance_ohlcv("BTC-USD", interval="4h", days=DAYS, quiet=True)
    rv = df["close"].pct_change().rolling(180).std() * np.sqrt(6 * 365)
    rv.index = pd.DatetimeIndex([_naive(t) for t in rv.index])
    return rv.dropna()


def trade_vol_mults(trades, rv):
    """Her islemin GIRIS anindaki BTC vol'una gore risk carpani (vol-target)."""
    idx = rv.index
    mults = []
    for t in trades:
        et = _naive(t["entry"])
        prior = rv[idx <= et]
        mv = float(prior.iloc[-1]) if len(prior) else 0.0
        mults.append(max(VOL_MULT_LO, min(VOL_MULT_HI, TARGET_VOL / mv)) if mv > 0 else 1.0)
    return mults


def collect_smp_trades(drop={"rsi"}):
    """no-RSI SMP (B karari), A+ + ER>0.15, 30 coin -> [{coin,side,entry,exit,R}]."""
    out = []
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
            fs = gated(fs, efficiency_ratio(df["close"], 20) > ER_MIN)
            for _, r in backtest(df, ind, fs, WIDE[c][1]).iterrows():
                if pd.notna(r["entry_time"]) and pd.notna(r["exit_time"]):
                    out.append({"coin": c, "side": r.get("side", "LONG"),
                                "entry": pd.Timestamp(r["entry_time"]),
                                "exit": pd.Timestamp(r["exit_time"]), "R": float(r["R"])})
        except Exception:
            pass
    out.sort(key=lambda x: x["entry"])
    return out


def smp_curve(trades, start, risk_pct, max_conc=MAX_CONC, mults=None):
    """Kronolojik + es zamanli + bilesik. mults: islem-basi vol-target risk carpani."""
    ev = []
    for k, t in enumerate(trades):
        ev.append((t["entry"], 1, k)); ev.append((t["exit"], 0, k))
    ev.sort(key=lambda x: (x[0], x[1]))          # ayni an: once kapat sonra ac
    eq, open_risk, curve, taken = start, {}, [(min((t["entry"] for t in trades)), start)], 0
    for ts, typ, k in ev:
        if typ == 0 and k in open_risk:
            eq += trades[k]["R"] * open_risk.pop(k)
            curve.append((ts, eq))
        elif typ == 1 and len(open_risk) < max_conc and eq > 0:
            open_risk[k] = risk_pct * eq * (mults[k] if mults else 1.0); taken += 1
    s = pd.Series({pd.Timestamp(t).tz_localize(None) if pd.Timestamp(t).tzinfo else pd.Timestamp(t): v
                   for t, v in curve})
    return s[~s.index.duplicated(keep="last")].sort_index(), taken


def metrics(total):
    ret = total.pct_change().dropna()
    if len(ret) < 20:
        return dict(final=total.iloc[-1] if len(total) else 0, cagr=0, maxdd=0, sharpe=0)
    cagr = (total.iloc[-1] / total.iloc[0]) ** (365 / len(total)) - 1
    return dict(final=total.iloc[-1], cagr=cagr * 100,
                maxdd=(total / total.cummax() - 1).min() * 100,
                sharpe=ret.mean() / ret.std() * np.sqrt(365) if ret.std() > 0 else 0)


def run(start=100.0, scale=1.0, trades=None, trend=None, mults=None):
    trades = trades if trades is not None else collect_smp_trades()
    trend = trend if trend is not None else trend_daily()
    # SMP sleeve -> gunluk
    sc, taken = smp_curve(trades, start * SMP_ALLOC, RISK_PCT * scale, mults=mults)
    # Trend sleeve -> gunluk (vol scale ~ getiriyi olcekle)
    tr = trend.copy(); tr.index = pd.DatetimeIndex(tr.index).tz_localize(None) if tr.index.tz else tr.index
    tcurve = (1 + tr * scale).cumprod() * (start * TREND_ALLOC)
    # ortak gunluk takvim
    lo = min(sc.index.min(), tcurve.index.min()); hi = max(sc.index.max(), tcurve.index.max())
    idx = pd.date_range(lo.normalize(), hi.normalize(), freq="D")
    smp_d = sc.reindex(idx, method="ffill").fillna(start * SMP_ALLOC)
    trend_d = tcurve.reindex(idx, method="ffill").fillna(start * TREND_ALLOC)
    total = smp_d + trend_d
    return metrics(total), taken, total


def main():
    print("=" * 84, flush=True)
    print("  MIMARI DOGRULAMA — paylasimli sermaye, SMP(no-RSI)+Trend, gercek sizing/eszamanlilik", flush=True)
    print("=" * 84, flush=True)
    print("  Islem/veri toplaniyor (30 coin + BTC vol)...", flush=True)
    trades = collect_smp_trades()
    trend = trend_daily()
    rv = btc_vol_series()
    mults = trade_vol_mults(trades, rv)
    yrs = ((max(t["exit"] for t in trades) - min(t["entry"] for t in trades)).days / 365.25) if trades else 0
    avg_m = float(np.mean(mults)) if mults else 1.0
    print(f"  SMP islem: {len(trades)}  |  ~{yrs*12:.0f} ay  |  SMP {SMP_ALLOC:.0%}/Trend {TREND_ALLOC:.0%}, "
          f"risk %{RISK_PCT*100:.0f}, max {MAX_CONC} es zamanli", flush=True)
    print(f"  Vol-target risk carpani: ort x{avg_m:.2f}  (aralik x{min(mults):.2f}-{max(mults):.2f})\n", flush=True)
    print(f"  {'olcek':>6} | {'BASELINE (sabit risk)':>28} | {'VOL-TARGET (#2)':>28}", flush=True)
    print(f"  {'':>6} | {'son$':>8} {'CAGR':>7} {'DD':>7} {'Shp':>4} | {'son$':>8} {'CAGR':>7} {'DD':>7} {'Shp':>4}", flush=True)
    print("  " + "-" * 68, flush=True)
    for scale in [1.0, 1.5, 2.0]:
        b, _, _ = run(100.0, scale, trades, trend, mults=None)
        v, _, _ = run(100.0, scale, trades, trend, mults=mults)
        print(f"  {scale:5.1f}x | {b['final']:8.2f} {b['cagr']:6.1f}% {b['maxdd']:6.1f}% {b['sharpe']:4.2f} | "
              f"{v['final']:8.2f} {v['cagr']:6.1f}% {v['maxdd']:6.1f}% {v['sharpe']:4.2f}", flush=True)
    print("\n  Vol-target: yuksek-BTC-vol donemlerinde risk kisar (DD/Sharpe iyilesir beklenir).", flush=True)
    print("  Bu CANLI botun uygulayacagi GERCEK mantik. Backtest/tek rejim -> canlida haircut. Basla: 1x.", flush=True)


if __name__ == "__main__":
    main()
