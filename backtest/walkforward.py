"""
backtest/walkforward.py
Cok-fold walk-forward: OOS'ta ayakta kalan 1h trend ipucu GERCEK mi yoksa
tek-split tesaduf mu? Genis coin evreninde, zaman cizgisini K ardisik fold'a
bolup her fold'da beklentiyi olcer. GERCEK edge cogu fold'da pozitif kalir.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.crypto_fetcher import fetch_binance_ohlcv
from backtest.event_engine import simulate
from strategies.mss_sweep_fib import build_orders as build_a
from strategies.true_ob import build_orders as build_b

COINS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
         "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD"]


def collect(dfs, tf, builder, cfg, mw, mh, fee, slip):
    ts = []
    for c, df in dfs.items():
        o = builder(df, **cfg)
        r = simulate(df, o, tf=tf, initial_capital=100.0, risk_pct=0.01,
                     fee_pct=fee, slippage_pct=slip, max_wait_bars=mw, max_hold_bars=mh)
        if not r["trades"].empty:
            ts.append(r["trades"])
    return pd.concat(ts, ignore_index=True) if ts else pd.DataFrame()


def walk(dfs, tf, label, builder, cfg, mw, mh, K=5, fee=0.0005, slip=0.0003):
    T = collect(dfs, tf, builder, cfg, mw, mh, fee, slip)
    if T.empty:
        print(f"{label:26} | islem yok")
        return
    T = T.sort_values("entry_time").reset_index(drop=True)
    idx = next(iter(dfs.values())).index
    edges = pd.date_range(idx.min(), idx.max(), periods=K + 1)
    cells = []
    pos_folds = 0
    for k in range(K):
        seg = T[(T["entry_time"] >= edges[k]) & (T["entry_time"] < edges[k + 1])]
        if len(seg) == 0:
            cells.append("   .  "); continue
        e = seg["R"].mean()
        pos_folds += (e > 0)
        cells.append(f"{e:+.2f}({len(seg)})")
    overall = T["R"].mean()
    win = (T["pnl"] > 0).mean() * 100
    print(f"{label:26} | " + " ".join(f"{c:>10}" for c in cells)
          + f" | oq {overall:+.3f}R win{win:4.0f}% n{len(T):4d} [{pos_folds}/{K}+]")


if __name__ == "__main__":
    tf, days, mw, mh, K = "1h", 365, 8, 24, 5
    dfs = {c: fetch_binance_ohlcv(c, interval=tf, days=days, quiet=True) for c in COINS}
    n0 = len(next(iter(dfs.values())))
    print(f"\nWalk-forward {tf}  {len(COINS)} coin  {K} fold  (~{n0} bar/coin, taker maliyet)")
    print(f"{'Konfig':26} | " + " ".join(f"{'F'+str(k+1):>10}" for k in range(K)) + " | genel")
    print("-" * 104)
    walk(dfs, tf, "A trend200 rr2 (OOS survivor)", build_a, dict(trend_ema=200), mw, mh, K)
    walk(dfs, tf, "A trend200 rr3", build_a, dict(trend_ema=200, rr=3.0), mw, mh, K)
    walk(dfs, tf, "A trend100 rr2", build_a, dict(trend_ema=100), mw, mh, K)
    walk(dfs, tf, "A trend200 rr2 disp1.5", build_a, dict(trend_ema=200, disp_mult=1.5), mw, mh, K)
    walk(dfs, tf, "B5 trend no-FVG", build_b, dict(trend_ema=200, require_fvg=False), mw, mh, K)
    walk(dfs, tf, "B3 trend +MSS", build_b, dict(trend_ema=200, require_mss=True), mw, mh, K)
