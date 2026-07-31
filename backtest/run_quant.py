"""
backtest/run_quant.py
SMP Quant Engine v2 — bilesen testi (Round 1: rejim + onay filtreleri).
Her bilesen, valide trend BASELINE'ina EKLENİR ve portfoy walk-forward'da
baseline'i gecip gecmedigine bakilir. Sadece GEÇEN tutulur.
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

COINS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
         "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD"]
TF, DAYS = "1d", 1500


def base_trend(df):
    return sig_donchian(df, 20, 10, 100, long_only=True)


# Her config: df -> hedef pozisyon serisi
CONFIGS = [
    ("BASELINE trend (donchian LO)", lambda d: base_trend(d)),
    # ── Rejim katmani (#1) ──
    ("+rejim ER>0.30",   lambda d: base_trend(d).where(qe.regime_is_trend(d, "er", er_thr=0.30), 0.0)),
    ("+rejim ER>0.40",   lambda d: base_trend(d).where(qe.regime_is_trend(d, "er", er_thr=0.40), 0.0)),
    ("+rejim ADX>25",    lambda d: base_trend(d).where(qe.regime_is_trend(d, "adx", adx_thr=25), 0.0)),
    ("adaptif: trend+MR(yatay)", lambda d: base_trend(d).where(
        qe.regime_is_trend(d, "er", er_thr=0.30), qe.sig_meanrev(d, long_only=True))),
    # ── Onay filtreleri (#2,#6,#11) ──
    ("+ADX>20 onay",     lambda d: base_trend(d).where(qe.gate_adx(d, thr=20), 0.0)),
    ("+MACD onay",       lambda d: base_trend(d).where(qe.gate_macd_long(d), 0.0)),
    ("+Hacim onay",      lambda d: base_trend(d).where(qe.gate_volume(d), 0.0)),
    ("+VWAP50 onay",     lambda d: base_trend(d).where(qe.gate_vwap_long(d), 0.0)),
    ("+RSI onay",        lambda d: base_trend(d).where(qe.gate_rsi_long(d), 0.0)),
    # ── Kazananlari birlestir (Round 2) ──
    ("ER040 + MACD",     lambda d: base_trend(d).where(qe.regime_is_trend(d, "er", er_thr=0.40) & qe.gate_macd_long(d), 0.0)),
    ("ER040 + Hacim",    lambda d: base_trend(d).where(qe.regime_is_trend(d, "er", er_thr=0.40) & qe.gate_volume(d), 0.0)),
    ("ER040 + MACD + Hacim", lambda d: base_trend(d).where(
        qe.regime_is_trend(d, "er", er_thr=0.40) & qe.gate_macd_long(d) & qe.gate_volume(d), 0.0)),
]


def run():
    dfs = {c: fetch_binance_ohlcv(c, interval=TF, days=DAYS, quiet=True) for c in COINS}
    n0 = len(next(iter(dfs.values())))
    print(f"\n{'='*104}")
    print(f"  SMP QUANT ENGINE v2 — Round 1  ({TF}, {len(COINS)} coin, ~{n0} bar, vol-hedef %40, 8bps)")
    print(f"  Kriter: portfoy Sharpe/CAGR/DD baseline'i GECMELI + walk-forward saglam")
    print(f"{'='*104}")
    print(f"{'Config':30} | {'CAGR':>7} {'Sharpe':>6} {'MaxDD':>7} | {'walk-forward fold Sharpe':>28} [poz/5]")
    print("-" * 104)
    base_sharpe = None
    for name, posf in CONFIGS:
        nets = {c: vol_target_returns(df, posf(df), TF) for c, df in dfs.items()}
        port = portfolio_returns(nets)
        st = stats_from_returns(port, TF)
        wf = walkforward_sharpe(port, TF, 5)
        pos_folds = sum(1 for x in wf if x > 0)
        if base_sharpe is None:
            base_sharpe = st["sharpe"]
            tag = "(baseline)"
        else:
            tag = ">> GECTI" if st["sharpe"] > base_sharpe else "   gecemedi"
        wf_str = " ".join(f"{x:+.2f}" for x in wf)
        print(f"{name:30} | {st['cagr']:6.1f}% {st['sharpe']:6.2f} {st['maxdd']:6.1f}% | "
              f"{wf_str} [{pos_folds}/5] {tag}")


if __name__ == "__main__":
    run()
