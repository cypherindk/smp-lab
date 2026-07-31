"""
backtest/oos.py
Out-of-sample (OOS) dayaniklilik testi. Builder'lar nedensel (causal, lookahead
yok) oldugu icin: tum seride emir uret -> simule et -> ortaya cikan ISLEMLERI
giris tarihine gore boyle bol: ilk %60 = in-sample (IS), son %40 = OOS.

Bir edge GERCEKSE, IS'te pozitif olan OOS'ta da (isaret + buyukluk olarak)
ayakta kalmali. OOS'ta cokuyorsa -> in-sample overfit.
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


def collect(dfs, tf, builder, cfg, mw, mh, fee, slip):
    ts = []
    for c, df in dfs.items():
        o = builder(df, **cfg)
        r = simulate(df, o, tf=tf, initial_capital=100.0, risk_pct=0.01,
                     fee_pct=fee, slippage_pct=slip, max_wait_bars=mw, max_hold_bars=mh)
        if not r["trades"].empty:
            ts.append(r["trades"])
    return pd.concat(ts, ignore_index=True) if ts else pd.DataFrame()


def metrics(T):
    if T.empty:
        return dict(n=0, wr=0.0, exp=0.0)
    w = T[T["pnl"] > 0]
    return dict(n=len(T), wr=len(w) / len(T) * 100, exp=T["R"].mean())


def run_tf(tf, days, mw, mh, configs):
    dfs = {c: fetch_binance_ohlcv(c, interval=tf, days=days, quiet=True) for c in COINS}
    idx = next(iter(dfs.values())).index
    cutoff = idx.min() + (idx.max() - idx.min()) * 0.6
    print(f"\n{'='*88}\n  {tf} ({days}g)  IS=<{cutoff.date()}  |  OOS>={cutoff.date()}   "
          f"(taker maliyet %0.05+%0.03)\n{'='*88}")
    print(f"{'Konfig':26} | {'IS n':>5} {'IS win':>6} {'IS BeklR':>9} | {'OOS n':>5} {'OOS win':>7} {'OOS BeklR':>9} | verdict")
    print("-" * 88)
    for label, builder, cfg in configs:
        T = collect(dfs, tf, builder, cfg, mw, mh, 0.0005, 0.0003)
        if T.empty:
            print(f"{label:26} | islem yok")
            continue
        IS = T[T["entry_time"] < cutoff]; OOS = T[T["entry_time"] >= cutoff]
        mi, mo = metrics(IS), metrics(OOS)
        # verdict: her iki dilim de pozitif mi?
        if mi["exp"] > 0 and mo["exp"] > 0:
            v = "DAYANDI +"
        elif mo["exp"] > 0:
            v = "OOS+ (IS-)"
        elif mi["exp"] > 0:
            v = "OVERFIT (OOS coktu)"
        else:
            v = "ikisi de -"
        print(f"{label:26} | {mi['n']:5d} {mi['wr']:5.1f}% {mi['exp']:+8.3f}R | "
              f"{mo['n']:5d} {mo['wr']:6.1f}% {mo['exp']:+8.3f}R | {v}")


if __name__ == "__main__":
    run_tf("15m", 120, 12, 48, [
        ("A trend only",        build_a, dict(trend_ema=200)),
        ("B1 +trend",           build_b, dict(trend_ema=200)),
        ("B2 +trend +killzone", build_b, dict(trend_ema=200, use_killzone=True)),
        ("B3 +trend +MSS",      build_b, dict(trend_ema=200, require_mss=True)),
        ("B5 +trend no-FVG",    build_b, dict(trend_ema=200, require_fvg=False)),
    ])
    run_tf("1h", 365, 8, 24, [
        ("A trend only",        build_a, dict(trend_ema=200)),
        ("B3 +trend +MSS",      build_b, dict(trend_ema=200, require_mss=True)),
        ("B5 +trend no-FVG",    build_b, dict(trend_ema=200, require_fvg=False)),
    ])
