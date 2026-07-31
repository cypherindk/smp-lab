"""
backtest/run_quant_xs.py
Round 3 — kesitsel (cross-sectional) varlik secimi (#5) + breadth risk-off.
ER040 kazanani uzerine: her bar sinyal veren coinler arasindan en guclu
momentumlulari sec (top-K); ayrica "yeterince coin trend yapmiyorsa nakde
gec" overlay'i. Amac: yakin donem kuraklik fold'unu (F5) iyilestirmek.
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


def er040_pos(df):
    return sig_donchian(df, 20, 10, 100, long_only=True).where(
        qe.regime_is_trend(df, "er", er_thr=0.40), 0.0)


def evaluate(dfs, masked_panel, label, base_sharpe=None):
    nets = {}
    for c, df in dfs.items():
        p = masked_panel[c].reindex(df.index).fillna(0.0)
        nets[c] = vol_target_returns(df, p, TF)
    port = portfolio_returns(nets)
    st = stats_from_returns(port, TF)
    wf = walkforward_sharpe(port, TF, 5)
    pos_folds = sum(1 for x in wf if x > 0)
    tag = "" if base_sharpe is None else (">> GECTI" if st["sharpe"] > base_sharpe else "   gecemedi")
    wf_str = " ".join(f"{x:+.2f}" for x in wf)
    print(f"{label:26} | {st['cagr']:6.1f}% {st['sharpe']:6.2f} {st['maxdd']:6.1f}% | {wf_str} [{pos_folds}/5] {tag}")
    return st["sharpe"]


def run():
    dfs = {c: fetch_binance_ohlcv(c, interval=TF, days=DAYS, quiet=True) for c in COINS}
    uni = None
    for df in dfs.values():
        uni = df.index if uni is None else uni.union(df.index)

    pos_panel = pd.DataFrame({c: er040_pos(df).reindex(uni) for c, df in dfs.items()}).fillna(0.0)
    mom_panel = pd.DataFrame({c: (df["close"] / df["close"].shift(60) - 1).reindex(uni)
                              for c, df in dfs.items()})

    print(f"\n{'='*100}")
    print(f"  QUANT ENGINE v2 — Round 3: kesitsel secim + risk-off  ({TF}, {len(COINS)} coin)")
    print(f"{'='*100}")
    print(f"{'Config':26} | {'CAGR':>7} {'Sharpe':>6} {'MaxDD':>7} | {'walk-forward fold Sharpe':>26} [poz/5]")
    print("-" * 100)

    base = evaluate(dfs, pos_panel, "ER040 (tum sinyaller)")

    # kesitsel top-K: sinyal veren coinler icinde en yuksek momentumlu K tanesi
    for K in [5, 3, 2]:
        mw = mom_panel.where(pos_panel > 0)
        keep = mw.rank(axis=1, ascending=False) <= K
        evaluate(dfs, pos_panel.where(keep, 0.0), f"XS top-{K} momentum", base)

    # breadth risk-off: sinyal veren coin orani esigin altindaysa nakde gec
    breadth = (pos_panel > 0).sum(axis=1) / pos_panel.shape[1]
    for thr in [0.20, 0.33]:
        gate = (breadth.shift(1) > thr).astype(float)
        evaluate(dfs, pos_panel.mul(gate, axis=0), f"risk-off breadth>{thr:.2f}", base)


if __name__ == "__main__":
    run()
