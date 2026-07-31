"""
backtest/run_smp.py
Kullanicinin mevcut SMP motorunu AYNI hakemden gecir + quant ER-rejim filtresiyle
BIRLESTIR + dusuk TF'ye adapte et. Hepsi tek yerde, walk-forward + gercek maliyet.

- SMP sinyalleri (buy/sell) -> pozisyona cevrilir (long/flat), directional edge
  vol-target engine ile olculur (SMP'nin kendi ADR SL/TP'sinden bagimsiz, saf
  yon edge'i). mtf=None (MTF alt-TF verisi olmadan, desteklenen yol).
- "SMP + ER rejim" = quant motorunun valide ER filtresi SMP sinyallerine uygulanir
  (SMP sadece trend rejiminde islem yapar) -> birlesme testi.
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
from engine.indicators import compute_all_indicators
from engine.signals import calc_bull_bear_score, calc_triggers, generate_signals
from engine.filters import apply_all_filters

COINS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]


def smp_position(df, tf_min, long_only=True):
    ind = compute_all_indicators(df, preset="Default", timeframe_minutes=tf_min)
    sc = calc_bull_bear_score(ind, htf_bias="auto", mtf=None)
    tr = calc_triggers(ind, sc)
    sg = generate_signals(ind, sc, tr, preset="Default")
    fin = apply_all_filters(ind, sg)
    raw = pd.Series(np.nan, index=df.index)
    raw[fin["buy_signal"].values] = 1.0
    raw[fin["sell_signal"].values] = 0.0 if long_only else -1.0
    return raw.ffill().fillna(0.0)


def quant_position(df):
    return sig_donchian(df, 55, 20, 200, long_only=True).where(
        qe.regime_is_trend(df, "er", er_thr=0.50), 0.0)


def evaluate(dfs, tf, posf, volwin, label, base=None):
    nets = {c: vol_target_returns(df, posf(df), tf, vol_window=volwin) for c, df in dfs.items()}
    port = portfolio_returns(nets)
    st = stats_from_returns(port, tf)
    wf = walkforward_sharpe(port, tf, 5)
    pf = sum(1 for x in wf if x > 0)
    tag = "" if base is None else (">> gecti" if st["sharpe"] > base else "  gecemedi")
    print(f"{label:34} | {st['cagr']:7.1f}% {st['sharpe']:5.2f} {st['maxdd']:6.1f}% | [{pf}/5] {tag}")
    return st["sharpe"]


def run():
    for tf, days, tfmin, volwin in [("4h", 720, 240, 60), ("1h", 365, 60, 120), ("30m", 180, 30, 180)]:
        dfs = {c: fetch_binance_ohlcv(c, interval=tf, days=days, quiet=True) for c in COINS}
        print(f"\n{'='*86}\n  SMP MOTORU  TF={tf} ({days}g, 5 coin, tf_min={tfmin})  | vol-hedef %40, 8bps\n{'='*86}")
        print(f"{'Config':34} | {'CAGR':>7} {'Sharpe':>5} {'MaxDD':>6} | walk-forward")
        print("-" * 86)
        q = evaluate(dfs, tf, quant_position, volwin, "QUANT trend+ER (referans)")
        evaluate(dfs, tf, lambda d: smp_position(d, tfmin, long_only=False), volwin, "SMP long/short", q)
        evaluate(dfs, tf, lambda d: smp_position(d, tfmin, long_only=True), volwin, "SMP long/flat", q)
        evaluate(dfs, tf, lambda d: smp_position(d, tfmin, long_only=True).where(
            qe.regime_is_trend(d, "er", er_thr=0.50), 0.0), volwin, "SMP + ER rejim (BIRLESIK)", q)


if __name__ == "__main__":
    run()
