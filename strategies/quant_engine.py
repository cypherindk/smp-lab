"""
strategies/quant_engine.py
SMP Quant Engine v2 — rejim katmani, onay filtreleri, mean-reversion modulu.
Hepsi nedensel (lookahead yok). Her biri "baseline trend'i walk-forward'da
gecti mi?" diye ayri ayri test edilmek uzere tasarlandi (bkz backtest/run_quant.py).
"""

import numpy as np
import pandas as pd


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


# ── REJİM (#1) ──────────────────────────────────────────────────────
def efficiency_ratio(close, n=20):
    """Kaufman ER: |net degisim| / |toplam yol|. ~1 trend, ~0 yatay/gurultu."""
    change = (close - close.shift(n)).abs()
    path = close.diff().abs().rolling(n).sum()
    return (change / path.replace(0, np.nan)).fillna(0.0)


def adx(high, low, close, n=14):
    up = high.diff()
    dn = -low.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=high.index)
    tr = pd.concat([high - low, (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / n, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1.0 / n, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1.0 / n, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1.0 / n, adjust=False).mean().fillna(0.0)


def regime_is_trend(df, method="er", er_n=20, er_thr=0.30, adx_n=14, adx_thr=25):
    """Bool: bar trend rejiminde mi? (shift(1) ile — o bar acilirken bilinen bilgi)"""
    if method == "er":
        r = efficiency_ratio(df["close"], er_n) > er_thr
    else:
        r = adx(df["high"], df["low"], df["close"], adx_n) > adx_thr
    return r.shift(1).fillna(False).astype(bool)


# ── MEAN-REVERSION (yatay rejim icin, #1) ───────────────────────────
def sig_meanrev(df, n=20, k=1.5, long_only=False):
    """BB z-skoru fade: z<-k iken long, z>k iken short; z ortalamaya donunce (0) kapat."""
    sma = df["close"].rolling(n).mean()
    sd = df["close"].rolling(n).std()
    z = ((df["close"] - sma) / sd.replace(0, np.nan)).values
    out = np.zeros(len(df)); cur = 0.0
    for i in range(len(df)):
        if np.isnan(z[i]):
            out[i] = cur; continue
        if cur == 0.0:
            if z[i] < -k:
                cur = 1.0
            elif z[i] > k and not long_only:
                cur = -1.0
        elif cur > 0 and z[i] >= 0:
            cur = 0.0
        elif cur < 0 and z[i] <= 0:
            cur = 0.0
        out[i] = cur
    return pd.Series(out, index=df.index)


# ── ONAY FİLTRELERİ (long tarafi; #2,#6,#11) ────────────────────────
# Hepsi bool gate doner; trend pozisyonuna pos.where(gate, 0) ile uygulanir.
def gate_adx(df, n=14, thr=20):
    return (adx(df["high"], df["low"], df["close"], n) > thr).shift(1).fillna(False)


def gate_macd_long(df, fast=12, slow=26, sig=9):
    macd = _ema(df["close"], fast) - _ema(df["close"], slow)
    hist = macd - _ema(macd, sig)
    return (hist > 0).shift(1).fillna(False)


def gate_volume(df, n=20):
    return (df["volume"] > df["volume"].rolling(n).mean()).shift(1).fillna(False)


def gate_vwap_long(df, n=50):
    """Kayan VWAP uzeri (fiyat maliyetinin ustunde — #6)."""
    pv = (df["close"] * df["volume"]).rolling(n).sum()
    v = df["volume"].rolling(n).sum().replace(0, np.nan)
    vwap = pv / v
    return (df["close"] > vwap).shift(1).fillna(False)


def gate_rsi_long(df, n=14, lo=40, hi=80):
    d = df["close"].diff()
    g = d.clip(lower=0).ewm(alpha=1.0 / n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1.0 / n, adjust=False).mean()
    rsi = 100 - 100 / (1 + g / l.replace(0, np.nan))
    return ((rsi > lo) & (rsi < hi)).shift(1).fillna(False)
