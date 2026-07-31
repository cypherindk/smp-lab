"""
backtest/run_trend.py
Sistematik trend/momentum sistemini quant disipliniyle dogrula:
9-coin sepeti, volatilite-hedefli boyutlandirma, esit-agirlik portfoy,
walk-forward fold Sharpe'lari. Az ve ILKESEL sayida varyant (coklu-test
yanliligini sinirlamak icin — deflated Sharpe dersi).
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.crypto_fetcher import fetch_binance_ohlcv
from backtest.trend_engine import (vol_target_returns, stats_from_returns,
                                   portfolio_returns, walkforward_sharpe)
from strategies.ts_momentum import sig_dual_ema, sig_tsmom, sig_donchian

COINS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
         "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD"]

VARIANTS = [
    ("dualEMA 20/50 LO",   lambda d: sig_dual_ema(d, 20, 50, long_only=True)),
    ("dualEMA 20/50 LS",   lambda d: sig_dual_ema(d, 20, 50, long_only=False)),
    ("tsmom 30 LO",        lambda d: sig_tsmom(d, 30, long_only=True)),
    ("tsmom 60 LS",        lambda d: sig_tsmom(d, 60, long_only=False)),
    ("donchian 20/10 t100 LO", lambda d: sig_donchian(d, 20, 10, 100, long_only=True)),
    ("donchian 55/20 t200 LS", lambda d: sig_donchian(d, 55, 20, 200, long_only=False)),
]


def run_tf(tf, days, K=5):
    dfs = {c: fetch_binance_ohlcv(c, interval=tf, days=days, quiet=True) for c in COINS}
    print(f"\n{'='*100}\n  {tf}  ({days}g, {len(COINS)} coin, vol-hedef %40, maliyet 8bps/turnover)\n{'='*100}")
    print(f"{'Varyant':26} | {'Port CAGR':>9} {'Sharpe':>6} {'MaxDD':>7} | {'ort coin Sharpe':>14} | walk-forward fold Sharpe [poz/K]")
    print("-" * 100)
    for name, sigf in VARIANTS:
        nets = {}
        coin_sharpes = []
        for c, df in dfs.items():
            pos = sigf(df)
            net = vol_target_returns(df, pos, tf)
            nets[c] = net
            coin_sharpes.append(stats_from_returns(net, tf)["sharpe"])
        port = portfolio_returns(nets)
        st = stats_from_returns(port, tf)
        wf = walkforward_sharpe(port, tf, K)
        pos_folds = sum(1 for x in wf if x > 0)
        wf_str = " ".join(f"{x:+.2f}" for x in wf)
        print(f"{name:26} | {st['cagr']:8.1f}% {st['sharpe']:6.2f} {st['maxdd']:6.1f}% | "
              f"{np.mean(coin_sharpes):14.2f} | {wf_str} [{pos_folds}/{K}]")


if __name__ == "__main__":
    run_tf("1d", 1500)
    run_tf("4h", 720)
