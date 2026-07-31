"""
lab/ablation.py  —  ONERI #2: hangi faktor A+ edge'ini TASIYOR, hangisi GURULTU?
Her faktoru tek tek skordan cikar (drop), A+ Only + sadik SL/TP backtest'i tekrar
kos, baseline'a gore beklenti degisimini olc.
  - cikarinca beklenti DUSUYORSA -> faktor KATKI yapiyor (tut).
  - cikarinca beklenti ARTIYOR/AYNI -> faktor GURULTU (cikarilabilir).
Sadece LAB.
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
from lab.backtest_smp import backtest, metrics
from lab.measure_edge import UNIVERSE, DAYS

FACTORS = ["ema", "close_slow", "rsi", "macd", "vwap", "rvol",
           "dmi", "htf", "whale", "rvol3", "poc"]


def run_config(dfs, drop):
    all_T = []
    for c, df in dfs.items():
        adr_mult, rr = UNIVERSE[c]
        ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=240, adr_mult=adr_mult)
        sc = calc_bull_bear_score(ind, mtf=None, drop=drop)
        tr = calc_triggers(ind, sc)
        sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                              min_conf=2, grade_filter="A+ Only")
        fs = apply_all_filters(ind, sg, use_cvd=True)
        all_T.append(backtest(df, ind, fs, rr))
    pool = pd.concat(all_T, ignore_index=True) if all_T else pd.DataFrame()
    m = metrics(pool)
    if pool.empty:
        return m, dict(exp=0)
    pool = pool.sort_values("entry_time")
    mo = metrics(pool.iloc[int(len(pool) * 0.6):])
    return m, mo


def main():
    dfs = {}
    for c in UNIVERSE:
        try:
            dfs[c] = fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True)
        except Exception:
            pass
    base, base_oos = run_config(dfs, None)
    print("=" * 92)
    print(f"  ABLATION — SMP A+ edge (9 coin, 4H, {DAYS}g, TP=hedef R:R)")
    print(f"  BASELINE (13 faktor): {base['n']} islem | beklenti {base['exp']:+.3f}R | PF {base['pf']:.2f} | OOS {base_oos['exp']:+.3f}R")
    print("=" * 92)
    print(f"{'CIKARILAN faktor':18} | {'islem':>5} {'beklenti':>9} {'PF':>5} {'OOS':>7} | {'d-beklenti':>10} -> yorum")
    print("-" * 92)

    rows = []
    for f in FACTORS:
        m, mo = run_config(dfs, {f})
        rows.append((f, m, mo, m["exp"] - base["exp"]))
    rows.sort(key=lambda x: x[3])   # en negatif delta (en onemli) ustte

    for f, m, mo, d in rows:
        if d <= -0.10:
            yorum = "!! KATKI (tut)"
        elif d >= 0.10:
            yorum = "GURULTU (cikarilabilir)"
        else:
            yorum = "notr"
        print(f"{f:18} | {m['n']:5d} {m['exp']:+8.3f}R {m['pf']:5.2f} {mo['exp']:+6.2f}R | {d:+9.3f} -> {yorum}")


if __name__ == "__main__":
    main()
