"""
backtest/run_ict.py
ICT setup'lari icin deney harness'i. Birden cok konfigurasyonu ayni veri
uzerinde kosturup HAVUZLANMIS islem metrikleriyle (win-rate, beklenti R,
profit factor — compounding'den bagimsiz, dürüst edge olcutu) karsilastirir.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.crypto_fetcher import fetch_binance_ohlcv
from backtest.event_engine import simulate
from strategies.mss_sweep_fib import build_orders as build_a

COINS = ["BTC-USD", "ETH-USD", "SOL-USD"]


def load(coins, tf, days):
    return {c: fetch_binance_ohlcv(c, interval=tf, days=days, quiet=True) for c in coins}


def pooled(trades_list):
    if not trades_list:
        return dict(n=0, wr=0, exp=0, pf=0)
    T = pd.concat(trades_list, ignore_index=True)
    wins = T[T["pnl"] > 0]; losses = T[T["pnl"] <= 0]
    gl = abs(losses["pnl"].sum())
    return dict(
        n=len(T),
        wr=len(wins) / len(T) * 100,
        exp=T["R"].mean(),
        pf=(wins["pnl"].sum() / gl) if gl > 0 else float("inf"),
        T=T,
    )


def run_config(dfs, tf, label, **cfg):
    trades = []
    rets = {}
    for c, df in dfs.items():
        orders = build_a(df, **cfg)
        res = simulate(df, orders, tf=tf, initial_capital=100.0, risk_pct=0.01)
        if not res["trades"].empty:
            trades.append(res["trades"])
        rets[c] = res["stats"]["return_pct"]
    ps = pooled(trades)
    ret_str = " ".join(f"{k.split('-')[0]}:{v:+.0f}%" for k, v in rets.items())
    print(f"{label:34} | {ps['n']:4d} | {ps['wr']:5.1f}% | "
          f"{ps['exp']:+.3f}R | {ps['pf']:.2f} | {ret_str}")
    return ps


if __name__ == "__main__":
    tf, days = "15m", 120
    dfs = load(COINS, tf, days)
    print(f"\nVeri: {COINS} [{tf}] {days} gun  "
          f"(~{len(next(iter(dfs.values())))} bar/coin)\n")
    print(f"{'Konfig':34} | {'Isl':>4} | {'Win':>6} | {'BeklR':>7} | {'PF':>4} | Getiri (100$)")
    print("-" * 100)

    base = run_config(dfs, tf, "A0 ham (sweep+MSS)")
    run_config(dfs, tf, "A1 +trend_ema200", trend_ema=200)
    run_config(dfs, tf, "A2 +killzone", use_killzone=True)
    run_config(dfs, tf, "A3 +trend +killzone", trend_ema=200, use_killzone=True)
    run_config(dfs, tf, "A4 +trend +kz  rr=1.5", trend_ema=200, use_killzone=True, rr=1.5)
    run_config(dfs, tf, "A5 +trend  fib=0.62 (OTE)", trend_ema=200, entry_fib=0.62)
    run_config(dfs, tf, "A6 +trend +kz fib=0.62", trend_ema=200, use_killzone=True, entry_fib=0.62)
    run_config(dfs, tf, "A7 +trend disp_mult=1.5", trend_ema=200, disp_mult=1.5)

    # Motor dogrulamasi: ham baseline cikis-sebebi dagilimi
    print("\n[Motor dogrulama] A0 cikis sebebi -> ortalama R:")
    T = base["T"]
    for reason, g in T.groupby("reason"):
        print(f"   {reason:5}: {len(g):4d} islem, ort {g['R'].mean():+.2f}R")
