"""
lab/measure_edge.py  —  ONERI #1 devam: ORNEKLEMI BUYUT.
A+ Only cok seciciydi (21 islem). Grade filtresini gevsetip (A+&A, Hepsi) +
mumkun oldugunca cok coin ekleyip edge istatistiksel anlam kazaniyor mu bak.
Ayni sadik SL/TP (TP=hedef R:R) modeli. Sadece LAB.
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

# 9 coin dene (4h cache'i olmayan sessizce atlanir). rr yoksa varsayilan 2.0.
UNIVERSE = {
    "BTC-USD": (1.5, 2.0), "ETH-USD": (2.8, 3.5), "SOL-USD": (1.9, 1.8),
    "BNB-USD": (1.5, 2.0), "XRP-USD": (1.5, 2.0), "ADA-USD": (1.5, 2.0),
    "DOGE-USD": (1.5, 2.0), "AVAX-USD": (1.5, 2.0), "LINK-USD": (1.5, 2.0),
}
DAYS = 720


def sigs_for(df, adr_mult, grade_filter):
    ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=240, adr_mult=adr_mult)
    sc = calc_bull_bear_score(ind, mtf=None)
    tr = calc_triggers(ind, sc)
    sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                          min_conf=2, grade_filter=grade_filter)
    fs = apply_all_filters(ind, sg, use_cvd=True)
    return ind, fs


def run():
    dfs = {}
    for c in UNIVERSE:
        try:
            dfs[c] = fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True)
        except Exception:
            pass   # 4h cache yok + ag bloklu -> atla
    print(f"\n4h cache'i olan coin: {list(dfs.keys())}\n")

    for gf in ["A+ Only", "A+ and A", "All"]:
        all_T = []
        for c, df in dfs.items():
            adr_mult, rr = UNIVERSE[c]
            ind, fs = sigs_for(df, adr_mult, gf)
            all_T.append(backtest(df, ind, fs, rr))
        pool = pd.concat(all_T, ignore_index=True) if all_T else pd.DataFrame()
        m = metrics(pool)
        line = f"{gf:12} | {m['n']:4d} islem | win {m['wr']:4.1f}% | beklenti {m['exp']:+.3f}R | PF {m['pf']:.2f}"
        if not pool.empty:
            pool = pool.sort_values("entry_time")
            cut = int(len(pool) * 0.6)
            mi, mo = metrics(pool.iloc[:cut]), metrics(pool.iloc[cut:])
            v = "DAYANDI +" if (mi["exp"] > 0 and mo["exp"] > 0) else ("OOS-" if mo["exp"] <= 0 else "IS-")
            line += f" | WF IS {mi['exp']:+.2f} / OOS {mo['exp']:+.2f} [{v}]"
        print(line)


if __name__ == "__main__":
    print("="*100)
    print("  SMP EDGE — grade filtresi taramasi (ornekem buyutme)  4H, 720g, TP=hedef R:R, ~10bps")
    print("="*100)
    run()
