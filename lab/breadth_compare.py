"""
lab/breadth_compare.py  —  "AZ COIN cok sinyal" vs "COK COIN iyi sinyal" karari.
9 coin uzerinde: baseline (filtresiz, cok sinyal) vs ER>0.15 (az-ama-kaliteli).
Sinyal FREKANSI (aylik) + kalite + coin basina dagilim + kac coin gerektigi
ekstrapolasyonu. Sadece LAB.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.crypto_fetcher import fetch_binance_ohlcv
from strategies.quant_engine import efficiency_ratio
from lab.backtest_smp import backtest, metrics
from lab.measure_edge import UNIVERSE, DAYS
from lab.test_additions import base_signals, gated


def run(dfs, sigs, use_er):
    T = []; per_coin = {}
    for c, df in dfs.items():
        ind, fs = sigs[c]
        if use_er:
            g = efficiency_ratio(df["close"], 20) > 0.15
            fs = gated(fs, g, g)
        t = backtest(df, ind, fs, UNIVERSE[c][1])
        T.append(t); per_coin[c] = len(t)
    pool = pd.concat(T, ignore_index=True).sort_values("entry_time")
    return metrics(pool), metrics(pool.iloc[int(len(pool) * 0.6):]), per_coin


def main():
    dfs, sigs = {}, {}
    for c in UNIVERSE:
        try:
            dfs[c] = fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True)
            sigs[c] = base_signals(dfs[c], UNIVERSE[c][0])
        except Exception:
            pass
    ncoin = len(dfs)
    span = next(iter(dfs.values())).index
    months = (span.max() - span.min()).days / 30.44

    print("=" * 90)
    print(f"  BREADTH KARARI — {ncoin} coin, {months:.0f} ay (4H, {DAYS}g)")
    print("=" * 90)
    print(f"{'Config':26} | {'toplam':>6} {'sinyal/ay':>9} {'win%':>6} {'beklenti':>9} {'PF':>5} {'OOS':>7}")
    print("-" * 90)
    for name, use_er in [("AZ COIN cok sinyal (filtresiz)", False),
                         ("COK COIN iyi sinyal (ER>0.15)", True)]:
        m, mo, pc = run(dfs, sigs, use_er)
        spm = m["n"] / months
        print(f"{name:26} | {m['n']:6d} {spm:9.2f} {m['wr']:5.1f}% {m['exp']:+8.3f}R {m['pf']:5.2f} {mo['exp']:+6.2f}R")

    # ekstrapolasyon: kaliteli (ER>0.15) sinyal/coin/ay -> hedef frekans icin kac coin
    m_er, _, pc_er = run(dfs, sigs, True)
    per_coin_month = m_er["n"] / ncoin / months
    print("\n" + "-" * 90)
    print(f"  ER>0.15 kalitesiyle sinyal/coin/ay = {per_coin_month:.3f}")
    print(f"  {'Hedef sinyal/ay':>18} -> gereken coin sayisi (ER>0.15 kalitesinde):")
    for target in [2, 3, 5, 8]:
        need = target / per_coin_month if per_coin_month > 0 else 0
        print(f"  {target:>18} -> ~{need:.0f} coin")
    print("\n  NOT: {} coin cache'de var; daha genis evren (top20-30) icin 4H veri".format(ncoin))
    print("       cekilmeli (borsa bloklu -> VPN/GitHub Actions'ta calisir).")


if __name__ == "__main__":
    main()
