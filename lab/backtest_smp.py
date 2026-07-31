"""
lab/backtest_smp.py  —  ONERI #1: SMP sinyallerinin EDGE'ini olc.

SMP'nin GERCEKTE nasil trade ettigini modelleyen sadik, bar-bar, event-driven
backtest: her buy/sell sinyalinde bir sonraki BAR ACILISINDA gir (lookahead yok),
ADR tabanli SL + (tp_mult x stop) TP koy, fiyat SL/TP'ye degene kadar ilerle.
Gercek maliyet (taker ~5bps round-trip). R-multiple bazli metrikler + walk-forward.

Sadece LAB — canliya dokunmaz.
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

# Canlidaki COINS ayarlari (Aggressive / eff_score=3 / min_conf=2 / A+ Only)
COINS = {
    "BTC-USD": dict(adr_mult=1.5, rr=2.0),
    "ETH-USD": dict(adr_mult=2.8, rr=3.5),
    "SOL-USD": dict(adr_mult=1.9, rr=1.8),
}
DAYS = 720
FEE = 0.0005      # taker ~5bps (round-trip ~2x asagida)
SLIP = 0.0003


def smp_signals(df, adr_mult):
    ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=240, adr_mult=adr_mult)
    sc = calc_bull_bear_score(ind, mtf=None)
    tr = calc_triggers(ind, sc)
    sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                          min_conf=2, grade_filter="A+ Only")
    fs = apply_all_filters(ind, sg, use_cvd=True)
    return ind, fs


def backtest(df, ind, fs, tp_mult):
    o = df["open"].values; h = df["high"].values
    l = df["low"].values; c = df["close"].values
    stop = (ind["safe_stop_pct"] / 100.0).values
    buy = fs["buy_signal"].values; sell = fs["sell_signal"].values
    n = len(df); trades = []; i = 0
    while i < n - 1:
        if (buy[i] or sell[i]) and not (np.isnan(stop[i]) or stop[i] <= 0):
            side = 1 if buy[i] else -1
            entry = o[i + 1] * (1 + SLIP * side)          # sonraki bar acilisi + slippage
            sp = stop[i]
            sl = entry * (1 - sp * side)
            tp = entry * (1 + sp * tp_mult * side)
            risk = abs(entry - sl)
            exit_p, j = None, i + 1
            while j < n:                                    # SL/TP'ye degene kadar
                if side == 1:
                    if l[j] <= sl: exit_p = sl; break
                    if h[j] >= tp: exit_p = tp; break
                else:
                    if h[j] >= sl: exit_p = sl; break
                    if l[j] <= tp: exit_p = tp; break
                j += 1
            if exit_p is None: exit_p = c[n - 1]; j = n - 1
            pnl = (exit_p - entry) * side - entry * 2 * FEE
            trades.append(dict(entry_time=df.index[i + 1], side=side,
                               R=pnl / risk, pnl_pct=pnl / entry * 100))
            i = j + 1                                        # cakisma yok
        else:
            i += 1
    return pd.DataFrame(trades)


def metrics(T):
    if T.empty:
        return dict(n=0, wr=0, exp=0, pf=0)
    w = T[T["R"] > 0]; loss = T[T["R"] <= 0]
    gl = abs(loss["R"].sum())
    return dict(n=len(T), wr=len(w) / len(T) * 100, exp=T["R"].mean(),
                pf=(w["R"].sum() / gl) if gl > 0 else float("inf"))


def run():
    dfs = {c: fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True) for c in COINS}
    sigs = {c: smp_signals(dfs[c], COINS[c]["adr_mult"]) for c in COINS}

    for label, tp_desc in [("TP=1R (tp_mult=1.0)", "1.0"), ("TP=hedef R:R (coin-ozel)", "rr")]:
        print(f"\n{'='*82}\n  SMP EDGE OLCUMU — {label}  (4H, {DAYS}g, Binance, maliyet ~10bps)\n{'='*82}")
        print(f"{'Coin':10} | {'islem':>6} {'win%':>6} {'beklenti(R)':>12} {'PF':>6}")
        print("-" * 82)
        all_T = []
        for c in COINS:
            ind, fs = sigs[c]
            tpm = 1.0 if tp_desc == "1.0" else COINS[c]["rr"]
            T = backtest(dfs[c], ind, fs, tpm)
            all_T.append(T)
            m = metrics(T)
            print(f"{c:10} | {m['n']:6d} {m['wr']:5.1f}% {m['exp']:+11.3f}R {m['pf']:6.2f}")
        pool = pd.concat(all_T, ignore_index=True) if all_T else pd.DataFrame()
        m = metrics(pool)
        print("-" * 82)
        print(f"{'HAVUZ':10} | {m['n']:6d} {m['wr']:5.1f}% {m['exp']:+11.3f}R {m['pf']:6.2f}")
        # walk-forward: ilk %60 / son %40
        if not pool.empty:
            pool = pool.sort_values("entry_time")
            cut = int(len(pool) * 0.6)
            mi, mo = metrics(pool.iloc[:cut]), metrics(pool.iloc[cut:])
            print(f"  WF -> IS(ilk %60): {mi['n']}i {mi['exp']:+.3f}R | OOS(son %40): {mo['n']}i {mo['exp']:+.3f}R")


if __name__ == "__main__":
    run()
