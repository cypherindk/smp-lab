"""
backtest/run_intraday_mr.py
Gün içi (30m/1h) icin DOGRU edge ailesi: MEAN-REVERSION (trend degil).
Mantik: gun ici piyasa daha cok ortalamaya donucu. YATAY rejimde (ER dusuk)
BB z-skoru ekstremlerini fade et; ortalamaya donunce kapat. Vol-hedef + gercek
maliyet. Hem taker (8bps) hem maker (3bps) — MR cok islem yaptigi icin maliyet
belirleyici; limit (maker) girisle yasayabilir mi ona bakiyoruz.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.crypto_fetcher import fetch_binance_ohlcv
from backtest.trend_engine import (vol_target_returns, stats_from_returns,
                                   portfolio_returns, walkforward_sharpe)
from strategies.quant_engine import sig_meanrev, regime_is_trend

COINS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]


def ranged(d, k, lo, erthr):
    """MR sinyali, sadece YATAY rejimde aktif (ER < erthr)."""
    mr = sig_meanrev(d, n=20, k=k, long_only=lo)
    return mr.where(~regime_is_trend(d, "er", er_thr=erthr), 0.0)


CONFIGS = [
    ("MR k1.5 LS (rejimsiz)", lambda d: sig_meanrev(d, 20, 1.5, False)),
    ("MR k2.0 LS (rejimsiz)", lambda d: sig_meanrev(d, 20, 2.0, False)),
    ("MR k1.5 LS +yatay(ER<.30)", lambda d: ranged(d, 1.5, False, 0.30)),
    ("MR k2.0 LS +yatay(ER<.30)", lambda d: ranged(d, 2.0, False, 0.30)),
    ("MR k2.0 LO +yatay(ER<.30)", lambda d: ranged(d, 2.0, True, 0.30)),
]


def stats(dfs, tf, posf, volwin, cost_bps):
    nets = {}
    for c, df in dfs.items():
        nets[c] = vol_target_returns(df, posf(df), tf, cost_bps=cost_bps, vol_window=volwin)
    port = portfolio_returns(nets)
    st = stats_from_returns(port, tf)
    wf = walkforward_sharpe(port, tf, 5)
    return st, sum(1 for x in wf if x > 0)


def run():
    for tf, days, volwin in [("1h", 365, 120), ("30m", 180, 180)]:
        dfs = {c: fetch_binance_ohlcv(c, interval=tf, days=days, quiet=True) for c in COINS}
        print(f"\n{'='*94}\n  GUN ICI MEAN-REVERSION  TF={tf} ({days}g, 5 coin)\n{'='*94}")
        print(f"{'Config':28} | {'taker 8bps: CAGR Sharpe DD':>30} | {'maker 3bps: CAGR Sharpe DD':>30}")
        print("-" * 94)
        for name, posf in CONFIGS:
            t, tf_ = stats(dfs, tf, posf, volwin, 8.0)
            m, mf_ = stats(dfs, tf, posf, volwin, 3.0)
            print(f"{name:28} | {t['cagr']:7.1f}% {t['sharpe']:5.2f} {t['maxdd']:6.1f}% [{tf_}/5]"
                  f" | {m['cagr']:7.1f}% {m['sharpe']:5.2f} {m['maxdd']:6.1f}% [{mf_}/5]")


if __name__ == "__main__":
    run()
