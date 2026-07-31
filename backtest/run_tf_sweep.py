"""
backtest/run_tf_sweep.py
"Kisa zaman dilimine optimize et" isteginin DURUST testi. Valide motoru
(trend + ER040 rejim) 1d'den 15m'e kadar, HER TF icin birkac parametre
varyantiyla (re-tune denemesi), GERCEK maliyetle (8bps/turnover) ve
walk-forward'la kosar. Kisa TF gercekten iyilesiyor mu, yoksa gurultu+maliyet
mi kazaniyor -> data karar versin.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.crypto_fetcher import fetch_binance_ohlcv
from backtest.trend_engine import (vol_target_returns, stats_from_returns,
                                   portfolio_returns, walkforward_sharpe)
from strategies.ts_momentum import sig_donchian
from strategies import quant_engine as qe

COINS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]

# TF -> (gun, vol_penceresi). Kisa TF'de daha uzun vol penceresi (daha cok bar).
TF_CONFIG = [
    ("1d",  1500, 30),
    ("4h",  720,  60),
    ("1h",  365,  120),
    ("30m", 180,  180),
    ("15m", 90,   240),
]

# Her TF icin denenecek param setleri (gurultuye karsi daha uzun Donchian + daha yuksek ER)
PARAM_SETS = [
    ("donch20/10 ER0.40", 20, 10, 100, 0.40),
    ("donch40/20 ER0.40", 40, 20, 100, 0.40),
    ("donch40/20 ER0.50", 40, 20, 100, 0.50),
    ("donch55/20 ER0.50", 55, 20, 200, 0.50),
]


def run():
    for tf, days, volwin in TF_CONFIG:
        dfs = {c: fetch_binance_ohlcv(c, interval=tf, days=days, quiet=True) for c in COINS}
        n0 = len(next(iter(dfs.values())))
        print(f"\n{'='*96}\n  TF={tf}  ({days}g, ~{n0} bar/coin, volwin={volwin}, maliyet 8bps)\n{'='*96}")
        print(f"{'Param seti':22} | {'CAGR':>7} {'Sharpe':>6} {'MaxDD':>7} | walk-forward fold Sharpe [poz/5]")
        print("-" * 96)
        for name, en, ex, tl, erthr in PARAM_SETS:
            nets = {}
            for c, df in dfs.items():
                pos = sig_donchian(df, en, ex, tl, long_only=True).where(
                    qe.regime_is_trend(df, "er", er_thr=erthr), 0.0)
                nets[c] = vol_target_returns(df, pos, tf, vol_window=volwin)
            port = portfolio_returns(nets)
            st = stats_from_returns(port, tf)
            wf = walkforward_sharpe(port, tf, 5)
            pf = sum(1 for x in wf if x > 0)
            wf_str = " ".join(f"{x:+.2f}" for x in wf)
            print(f"{name:22} | {st['cagr']:6.1f}% {st['sharpe']:6.2f} {st['maxdd']:6.1f}% | {wf_str} [{pf}/5]")


if __name__ == "__main__":
    run()
