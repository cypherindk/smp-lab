"""
strategies/ts_momentum.py
Zaman-serisi momentum / trend-takibi sinyalleri. Her fonksiyon df.index ile
hizali bir HEDEF POZISYON serisi (+1 long / -1 short / 0 flat) doner.
Nedensel (lookahead yok): tum esikler shift(1)/gecmis pencereyle.
"""

import numpy as np
import pandas as pd


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def sig_dual_ema(df, fast=20, slow=50, long_only=False):
    f = _ema(df["close"], fast)
    s = _ema(df["close"], slow)
    pos = pd.Series(np.where(f > s, 1.0, -1.0), index=df.index)
    if long_only:
        pos = pos.clip(lower=0.0)
    return pos


def sig_tsmom(df, lookback=30, long_only=False):
    mom = df["close"] / df["close"].shift(lookback) - 1.0
    pos = pd.Series(np.sign(mom.fillna(0.0)), index=df.index)
    if long_only:
        pos = pos.clip(lower=0.0)
    return pos


def sig_donchian(df, entry_n=20, exit_n=10, trend_ema=100, long_only=False):
    """Donchian breakout + uzun-vade EMA trend filtresi. Durumsal pozisyon."""
    high, low, close = df["high"], df["low"], df["close"]
    up = high.rolling(entry_n).max().shift(1).values
    dn = low.rolling(entry_n).min().shift(1).values
    x_dn = low.rolling(exit_n).min().shift(1).values
    x_up = high.rolling(exit_n).max().shift(1).values
    te = _ema(close, trend_ema)
    tu = (close > te).values
    td = (close < te).values
    c = close.values
    n = len(df)
    pos = np.zeros(n)
    cur = 0.0
    for i in range(n):
        if np.isnan(up[i]):
            pos[i] = cur; continue
        # giris kirilimlari (trend filtresi hizasinda)
        if cur <= 0 and c[i] > up[i] and tu[i]:
            cur = 1.0
        elif (not long_only) and cur >= 0 and c[i] < dn[i] and td[i]:
            cur = -1.0
        # cikislar (kisa Donchian karsi taraf)
        if cur > 0 and c[i] < x_dn[i]:
            cur = 0.0
        elif cur < 0 and c[i] > x_up[i]:
            cur = 0.0
        pos[i] = cur
    return pd.Series(pos, index=df.index)
