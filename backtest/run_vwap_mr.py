"""
backtest/run_vwap_mr.py
Adım 6 — belgelenmis intraday edge'ini (anchored VWAP + SD bant MR, +sweep,
+funding filtresi) rigorlu test et: 30m/1h, taker+maker maliyet, walk-forward.
Adım 7 — en iyi config'i genis coin setinde coin-coin dene (hangi coinler intraday
daha uygun). Survivorship uyarisi: bugun yasayan coinler test ediliyor.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.crypto_fetcher import fetch_binance_ohlcv
from data.funding_fetcher import funding_aligned
from backtest.trend_engine import (vol_target_returns, stats_from_returns,
                                   portfolio_returns, walkforward_sharpe)
from strategies.vwap_mr import sig_vwap_mr

MAJORS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]
ALL9 = MAJORS + ["ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD"]


def apply_funding(pos, coin, idx, days):
    fa, z = funding_aligned(coin, idx, days=days)
    if z is None:
        return pos
    al = (z < -0.3).fillna(False)
    ash = (z > 0.3).fillna(False)
    return pos.mask((pos > 0) & (~al), 0.0).mask((pos < 0) & (~ash), 0.0)


def port_eval(dfs, tf, volwin, cost, k, sweep, funding, days):
    nets = {}
    for c, df in dfs.items():
        pos = sig_vwap_mr(df, k=k, require_sweep=sweep, long_only=False)
        if funding:
            pos = apply_funding(pos, c, df.index, days)
        nets[c] = vol_target_returns(df, pos, tf, cost_bps=cost, vol_window=volwin)
    port = portfolio_returns(nets)
    st = stats_from_returns(port, tf)
    wf = walkforward_sharpe(port, tf, 5)
    return st, sum(1 for x in wf if x > 0)


def step6():
    for tf, days, volwin, coins in [("1h", 365, 120, ALL9), ("30m", 180, 180, MAJORS)]:
        dfs = {c: fetch_binance_ohlcv(c, interval=tf, days=days, quiet=True) for c in coins}
        print(f"\n{'='*92}\n  ADIM 6 — VWAP MR  TF={tf} ({days}g, {len(coins)} coin)\n{'='*92}")
        print(f"{'Config':30} | {'taker: CAGR Sharpe DD':>26} | {'maker: CAGR Sharpe DD':>26}")
        print("-" * 92)
        for label, k, sweep, fund in [
            ("VWAP MR k2.0", 2.0, False, False),
            ("VWAP MR k2.5", 2.5, False, False),
            ("VWAP MR k2.0 +sweep", 2.0, True, False),
            ("VWAP MR k2.0 +funding", 2.0, False, True),
            ("VWAP MR k2.0 +sweep +funding", 2.0, True, True),
        ]:
            t, tf_ = port_eval(dfs, tf, volwin, 8.0, k, sweep, fund, days)
            m, mf_ = port_eval(dfs, tf, volwin, 3.0, k, sweep, fund, days)
            print(f"{label:30} | {t['cagr']:7.1f}% {t['sharpe']:5.2f} {t['maxdd']:6.1f}% [{tf_}/5]"
                  f" | {m['cagr']:7.1f}% {m['sharpe']:5.2f} {m['maxdd']:6.1f}% [{mf_}/5]")


def step7():
    tf, days, volwin = "1h", 365, 120
    dfs = {c: fetch_binance_ohlcv(c, interval=tf, days=days, quiet=True) for c in ALL9}
    print(f"\n{'='*92}\n  ADIM 7 — coin-coin VWAP MR k2.0+sweep+funding  (1h, maker 3bps)\n{'='*92}")
    print(f"{'Coin':10} | {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'islem/gun proxy':>16}")
    print("-" * 92)
    for c, df in dfs.items():
        pos = apply_funding(sig_vwap_mr(df, k=2.0, require_sweep=True, long_only=False), c, df.index, days)
        net = vol_target_returns(df, pos, tf, cost_bps=3.0, vol_window=volwin)
        st = stats_from_returns(net, tf)
        turnover = (pos.diff().abs() > 0).sum()
        print(f"{c:10} | {st['cagr']:7.1f}% {st['sharpe']:7.2f} {st['maxdd']:7.1f}% {turnover:16d}")


if __name__ == "__main__":
    step6()
    step7()
