"""
backtest/compare_ab.py
Setup A (MSS Sweep Fib) vs Setup B (True OB) — yan yana, havuzlanmis islem
metrikleri. Hem 'taker' hem 'sifir' maliyetle koser (edge'i maliyet drag'inden
ayirmak icin).
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

COINS = ["BTC-USD", "ETH-USD", "SOL-USD"]


def pooled(ts):
    if not ts:
        return dict(n=0, wr=0, exp=0, pf=0)
    T = pd.concat(ts, ignore_index=True)
    w = T[T["pnl"] > 0]; l = T[T["pnl"] <= 0]
    gl = abs(l["pnl"].sum())
    return dict(n=len(T), wr=len(w) / len(T) * 100, exp=T["R"].mean(),
                pf=(w["pnl"].sum() / gl) if gl > 0 else float("inf"))


def run(dfs, tf, label, builder, cfg, mw, mh, fee, slip):
    ts = []
    for c in COINS:
        o = builder(dfs[c], **cfg)
        r = simulate(dfs[c], o, tf=tf, initial_capital=100.0, risk_pct=0.01,
                     fee_pct=fee, slippage_pct=slip, max_wait_bars=mw, max_hold_bars=mh)
        if not r["trades"].empty:
            ts.append(r["trades"])
    return pooled(ts)


CONFIGS = [
    ("A best (trend+kz+OTE)", build_a, dict(trend_ema=200, use_killzone=True, entry_fib=0.62)),
    ("A trend only",          build_a, dict(trend_ema=200)),
    ("B0 raw (sweep+disp+FVG+OB)", build_b, dict()),
    ("B1 +trend",             build_b, dict(trend_ema=200)),
    ("B2 +trend +killzone",   build_b, dict(trend_ema=200, use_killzone=True)),
    ("B3 +trend +MSS",        build_b, dict(trend_ema=200, require_mss=True)),
    ("B4 +trend entry=mid",   build_b, dict(trend_ema=200, ob_entry="mid")),
    ("B5 +trend no-FVG",      build_b, dict(trend_ema=200, require_fvg=False)),
]


if __name__ == "__main__":
    for tf, days, mw, mh in [("15m", 120, 12, 48), ("1h", 365, 8, 24)]:
        dfs = {c: fetch_binance_ohlcv(c, interval=tf, days=days, quiet=True) for c in COINS}
        print(f"\n{'='*82}\n  {tf}  ({days}g, ~{len(next(iter(dfs.values())))} bar/coin)  "
              f"| BeklR: taker(%0.05+%0.03) / sifir\n{'='*82}")
        print(f"{'Konfig':30} | {'Isl':>4} {'Win':>6} | {'BeklR taker':>11} {'PF':>4} | {'BeklR sifir':>11} {'PF':>4}")
        print("-" * 82)
        for label, builder, cfg in CONFIGS:
            tk = run(dfs, tf, label, builder, cfg, mw, mh, 0.0005, 0.0003)
            zr = run(dfs, tf, label, builder, cfg, mw, mh, 0.0, 0.0)
            print(f"{label:30} | {tk['n']:4d} {tk['wr']:5.1f}% | "
                  f"{tk['exp']:+10.3f}R {tk['pf']:4.2f} | {zr['exp']:+10.3f}R {zr['pf']:4.2f}")
