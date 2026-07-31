"""
lab/er_sweep.py — #1'i ADİL test: ER eşigini 4H'e uygun tara (hem trend hem chop
yonu). SMP A+ sinyalleri hangi rejimde daha iyi? Sadece LAB.
"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.crypto_fetcher import fetch_binance_ohlcv
from strategies.quant_engine import efficiency_ratio
from lab.backtest_smp import backtest, metrics
from lab.measure_edge import UNIVERSE, DAYS
from lab.test_additions import base_signals, gated


def evalg(dfs, sigs, gatefn):
    T = []
    for c, df in dfs.items():
        ind, fs = sigs[c]
        gfs = fs if gatefn is None else gated(fs, *gatefn(df))
        T.append(backtest(df, ind, gfs, UNIVERSE[c][1]))
    pool = pd.concat(T, ignore_index=True).sort_values("entry_time")
    return metrics(pool), metrics(pool.iloc[int(len(pool) * 0.6):])


def main():
    dfs, sigs = {}, {}
    for c in UNIVERSE:
        try:
            dfs[c] = fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True)
            sigs[c] = base_signals(dfs[c], UNIVERSE[c][0])
        except Exception:
            pass
    b, bo = evalg(dfs, sigs, None)
    print("=" * 84)
    print(f"  ER SWEEP (4H) — SMP A+ hangi rejimde daha iyi?  baseline: {b['n']}i {b['exp']:+.3f}R PF{b['pf']:.2f} OOS{bo['exp']:+.2f}")
    print("=" * 84)
    print(f"{'gate':22} | {'islem':>5} {'win%':>6} {'beklenti':>9} {'PF':>5} {'OOS':>7}")
    print("-" * 84)
    configs = [
        ("ER>0.10 (trend)", lambda df: (efficiency_ratio(df["close"], 20) > 0.10,) * 2),
        ("ER>0.15 (trend)", lambda df: (efficiency_ratio(df["close"], 20) > 0.15,) * 2),
        ("ER>0.20 (trend)", lambda df: (efficiency_ratio(df["close"], 20) > 0.20,) * 2),
        ("ER<0.15 (chop)",  lambda df: (efficiency_ratio(df["close"], 20) < 0.15,) * 2),
        ("ER<0.20 (chop)",  lambda df: (efficiency_ratio(df["close"], 20) < 0.20,) * 2),
        ("ER<0.25 (chop)",  lambda df: (efficiency_ratio(df["close"], 20) < 0.25,) * 2),
    ]
    for name, fn in configs:
        m, mo = evalg(dfs, sigs, fn)
        print(f"{name:22} | {m['n']:5d} {m['wr']:5.1f}% {m['exp']:+8.3f}R {m['pf']:5.2f} {mo['exp']:+6.2f}R")


if __name__ == "__main__":
    main()
