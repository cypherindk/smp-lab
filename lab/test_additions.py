"""
lab/test_additions.py  —  ONERI #1-#4'u SMP A+ baseline USTUNE tek tek ekle, olc.
Her ekleme bir GATE (sinyal barina bool filtre): sinyal & gate. Sonra sadik
SL/TP backtest. Etki: islem / win% / beklenti(R) / PF / OOS.
#5 (vol-targeting) per-trade win/R'yi degistirmez (sizing) -> ayri not.
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
from strategies.quant_engine import efficiency_ratio
from lab.backtest_smp import backtest, metrics
from lab.measure_edge import UNIVERSE, DAYS

daily_dfs = {}
breadth_gate = None


def base_signals(df, adr_mult):
    ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=240, adr_mult=adr_mult)
    sc = calc_bull_bear_score(ind, mtf=None)
    tr = calc_triggers(ind, sc)
    sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                          min_conf=2, grade_filter="A+ Only")
    return ind, apply_all_filters(ind, sg, use_cvd=True)


def gated(fs, bg, sg):
    out = fs.copy()
    out["buy_signal"] = fs["buy_signal"] & bg.reindex(fs.index).fillna(False).astype(bool)
    out["sell_signal"] = fs["sell_signal"] & sg.reindex(fs.index).fillna(False).astype(bool)
    return out


# ── GATE'ler (buy_gate, sell_gate) ──
def g_er(c, df, ind):
    g = efficiency_ratio(df["close"], 20) > 0.30          # #1 rejim: temiz trend
    return g, g


def g_htf(c, df, ind):
    d = daily_dfs[c]                                       # #2 gunluk trend hizasi
    d_up = (d["close"] > d["close"].ewm(span=50, adjust=False).mean()).shift(1)
    up4 = d_up.reindex(df.index, method="ffill").fillna(False).astype(bool)
    return up4, ~up4


def g_cvd(c, df, ind):                                     # #3 CVD egimi yon onayi
    delta = np.where(df["close"].values > df["open"].values,
                     df["volume"].values, -df["volume"].values)
    slope = pd.Series(delta, index=df.index).cumsum().diff(10)
    return (slope > 0), (slope < 0)


def g_breadth(c, df, ind):                                 # #4 piyasa breadth risk-off
    return breadth_gate, breadth_gate


def evaluate(dfs, sigs, gatefn):
    all_T = []
    for c, df in dfs.items():
        ind, fs = sigs[c]
        gfs = fs if gatefn is None else gated(fs, *gatefn(c, df, ind))
        all_T.append(backtest(df, ind, gfs, UNIVERSE[c][1]))
    pool = pd.concat(all_T, ignore_index=True)
    m = metrics(pool)
    pool = pool.sort_values("entry_time")
    mo = metrics(pool.iloc[int(len(pool) * 0.6):])
    return m, mo


def main():
    global daily_dfs, breadth_gate
    dfs, sigs = {}, {}
    for c in UNIVERSE:
        try:
            dfs[c] = fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True)
        except Exception:
            continue
        sigs[c] = base_signals(dfs[c], UNIVERSE[c][0])
    daily_dfs = {c: fetch_binance_ohlcv(c, interval="1d", days=DAYS + 60, quiet=True) for c in dfs}
    # #4 breadth: coinlerin ER>0.40 orani (onceki bar, lookahead yok)
    E = pd.concat({c: (efficiency_ratio(df["close"], 20) > 0.40).astype(float)
                   for c, df in dfs.items()}, axis=1)
    breadth = E.mean(axis=1)
    breadth_gate = (breadth.shift(1) > 0.33)

    base, base_oos = evaluate(dfs, sigs, None)
    print("=" * 94)
    print(f"  EKLEME TESTLERI — SMP A+ baseline ustune (9 coin, 4H, {DAYS}g, TP=hedef R:R)")
    print("=" * 94)
    print(f"{'Config':28} | {'islem':>5} {'win%':>6} {'beklenti':>9} {'PF':>5} {'OOS':>7} | karar")
    print("-" * 94)
    print(f"{'BASELINE (13 faktor A+)':28} | {base['n']:5d} {base['wr']:5.1f}% {base['exp']:+8.3f}R {base['pf']:5.2f} {base_oos['exp']:+6.2f}R | (referans)")

    for name, fn in [("#1 +ER rejim (>0.30)", g_er), ("#2 +HTF gunluk trend", g_htf),
                     ("#3 +CVD egimi onayi", g_cvd), ("#4 +breadth risk-off", g_breadth)]:
        m, mo = evaluate(dfs, sigs, fn)
        better = (m["exp"] > base["exp"] + 0.03) or (mo["exp"] > base_oos["exp"] + 0.05 and m["exp"] >= base["exp"] - 0.03)
        karar = ">> GECTI" if better and m["n"] >= 20 else ("az orneklem" if m["n"] < 20 else "gecemedi")
        print(f"{name:28} | {m['n']:5d} {m['wr']:5.1f}% {m['exp']:+8.3f}R {m['pf']:5.2f} {mo['exp']:+6.2f}R | {karar}")


if __name__ == "__main__":
    main()
