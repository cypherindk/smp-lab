"""
strategies/vwap_mr.py
Adım 5 — Anchored VWAP + standart sapma bantlari mean-reversion (kripto intraday
literaturunun belgeledigi setup). UTC gun basina cipalanmis VWAP; hacim-agirlikli
SD bantlari; fiyat ±k*SD ekstremine gelince fade, VWAP'a donunce cik.
require_sweep=True -> likidasyon-grab deseni (fitil bandi deler, iceri kapanir).
Nedensel: t barinda sadece t'ye kadarki gun-ici kumulatif bilgi kullanilir.
"""

import numpy as np
import pandas as pd


def anchored_vwap_bands(df, k=2.0):
    hlc3 = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"]
    day = pd.Series(df.index.floor("D"), index=df.index)
    cum_v = vol.groupby(day).cumsum().replace(0, np.nan)
    vwap = (hlc3 * vol).groupby(day).cumsum() / cum_v
    var = (vol * (hlc3 - vwap) ** 2).groupby(day).cumsum() / cum_v
    sd = np.sqrt(var)
    return vwap, vwap + k * sd, vwap - k * sd


def sig_vwap_mr(df, k=2.0, require_sweep=False, long_only=False,
               allow_long=None, allow_short=None):
    """
    allow_long / allow_short: opsiyonel bool seri (df.index hizali) — GIRIS
    kapisi (ornek: funding onayi). Verilirse, o yonde giris sadece kapi True
    iken acilir; pozisyon acildiktan sonra VWAP'a kadar tutulur (kapi ortada
    kesmez). None ise kisitsiz.
    """
    vwap, upper, lower = anchored_vwap_bands(df, k)
    c = df["close"].values
    hi = df["high"].values
    lo = df["low"].values
    U, L, V = upper.values, lower.values, vwap.values
    al = np.ones(len(df), bool) if allow_long is None else allow_long.reindex(df.index).fillna(False).values
    ash = np.ones(len(df), bool) if allow_short is None else allow_short.reindex(df.index).fillna(False).values
    n = len(df)
    pos = np.zeros(n)
    cur = 0.0
    for i in range(n):
        if np.isnan(U[i]) or np.isnan(V[i]):
            pos[i] = cur
            continue
        if cur == 0.0:
            if require_sweep:
                long_c = lo[i] < L[i] and c[i] > L[i]          # fitil alt bandi deldi, iceri kapandi
                short_c = (hi[i] > U[i] and c[i] < U[i]) and not long_only
            else:
                long_c = c[i] < L[i]
                short_c = (c[i] > U[i]) and not long_only
            if long_c and al[i]:
                cur = 1.0
            elif short_c and ash[i] and not long_only:
                cur = -1.0
        elif cur > 0 and c[i] >= V[i]:                          # VWAP'a dondu -> cik
            cur = 0.0
        elif cur < 0 and c[i] <= V[i]:
            cur = 0.0
        pos[i] = cur
    return pd.Series(pos, index=df.index)
