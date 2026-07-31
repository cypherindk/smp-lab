"""
backtest/run_vwap_mr2.py
İnce intraday edge'i (VWAP-MR + funding) sağlamlaştırma denemesi:
  1) funding'i temiz GIRIS kapisi olarak uygula (pozisyonu ortada kesme)
  2) gercekci PERP FUTURES maliyetleri (taker~5, maker~2, VIP~1, rebate~0 bps)
  3) funding esigi taramasi (ne kadar ekstrem funding => daha secici)
Amac: marjinal (Sharpe 0.5) -> saglam olabiliyor mu?
DURUST CEKINCE: maker fill garanti degil (ters secilim); bu bps modeli fill
belirsizligini yakalamaz -> gercek sonuc bunun bir tik altinda olur.
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
TF, DAYS, VOLWIN = "30m", 180, 180


def build_pos(df, coin, days, k, thr):
    fa, z = funding_aligned(coin, df.index, days=days)
    al = ash = None
    if z is not None:
        al = z < -thr
        ash = z > thr
    return sig_vwap_mr(df, k=k, allow_long=al, allow_short=ash)


def port(dfs, cost, k, thr):
    nets = {c: vol_target_returns(df, build_pos(df, c, DAYS, k, thr), TF,
                                  cost_bps=cost, vol_window=VOLWIN) for c, df in dfs.items()}
    p = portfolio_returns(nets)
    st = stats_from_returns(p, TF)
    wf = walkforward_sharpe(p, TF, 5)
    return st, sum(1 for x in wf if x > 0)


def run():
    dfs = {c: fetch_binance_ohlcv(c, interval=TF, days=DAYS, quiet=True) for c in MAJORS}

    print(f"\n{'='*78}\n  FUNDING ESIGI TARAMASI  (30m, 5 coin, maker 2bps, k=2.0)\n{'='*78}")
    print(f"{'funding esigi |z|>':20} | {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'poz/5':>6}")
    print("-" * 78)
    best = (None, -9)
    for thr in [0.3, 0.75, 1.0, 1.5]:
        st, pf = port(dfs, 2.0, 2.0, thr)
        if st["sharpe"] > best[1]:
            best = (thr, st["sharpe"])
        print(f"{'|z| > '+str(thr):20} | {st['cagr']:7.1f}% {st['sharpe']:7.2f} {st['maxdd']:7.1f}% {pf:>5}/5")

    bthr = best[0]
    print(f"\n{'='*78}\n  MALIYET DUYARLILIGI  (en iyi esik |z|>{bthr}, k=2.0)\n{'='*78}")
    print(f"{'maliyet (bps)':20} | {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'poz/5':>6}")
    print("-" * 78)
    for cost, lbl in [(5.0, "taker 5"), (2.0, "maker 2"), (1.0, "maker-VIP 1"), (0.0, "rebate 0")]:
        st, pf = port(dfs, cost, 2.0, bthr)
        print(f"{lbl:20} | {st['cagr']:7.1f}% {st['sharpe']:7.2f} {st['maxdd']:7.1f}% {pf:>5}/5")


if __name__ == "__main__":
    run()
