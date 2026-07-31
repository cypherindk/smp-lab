"""
backtest/trend_engine.py
Vektorize, volatilite-hedefli pozisyon backtester'i — sistematik trend/momentum
sistemleri icin (event_engine'in limit+SL/TP mantigi trend-takibine uymuyor:
trend sistemleri trailing/sinyal-flip cikisi ister, sabit TP degil).

Quant standardi "sinyal -> getiri" yaklasimi:
  - Her bar bir HEDEF POZISYON (pos in {-1,0,+1}) uretilir.
  - Volatilite hedefleme: kaldirac = hedef_vol / gerceklesmis_vol (cap'li) ->
    dusuk vol'de buyu, yuksek vol'de kucul (sabit risk).
  - Getiri = onceki_barin_pozisyonu * bugunku_getiri  (shift(1) = lookahead yok).
  - Maliyet: pozisyon DEGISIMINDE (turnover) bps olarak dusulur.
"""

import numpy as np
import pandas as pd

_BPY = {"5m": 105120, "15m": 35040, "30m": 17520, "1h": 8760, "4h": 2190, "1d": 365}


def vol_target_returns(df, pos, tf, target_vol=0.40, cost_bps=8.0,
                       vol_window=30, max_lev=3.0):
    """pos: hedef pozisyon serisi (df.index ile hizali). Donen: net getiri serisi."""
    r = df["close"].pct_change().fillna(0.0)
    bpy = _BPY.get(tf, 365)
    rvol = (r.rolling(vol_window).std() * np.sqrt(bpy)).replace(0.0, np.nan)
    lev = (target_vol / rvol).clip(upper=max_lev).fillna(0.0)
    exposure = (pos.astype(float) * lev).fillna(0.0)
    held = exposure.shift(1).fillna(0.0)          # dunku hedefi bugun tut
    gross = held * r
    turn = (exposure - exposure.shift(1)).abs().fillna(0.0)
    cost = (turn * cost_bps / 1e4).shift(1).fillna(0.0)
    return gross - cost


def stats_from_returns(net, tf):
    bpy = _BPY.get(tf, 365)
    net = net.fillna(0.0)
    eq = (1 + net).cumprod()
    n = max(len(net), 1)
    cagr = eq.iloc[-1] ** (bpy / n) - 1 if eq.iloc[-1] > 0 else -1.0
    sharpe = (net.mean() / net.std() * np.sqrt(bpy)) if net.std() > 0 else 0.0
    peak = eq.cummax(); maxdd = (eq / peak - 1).min()
    return dict(cagr=cagr * 100, sharpe=sharpe, maxdd=maxdd * 100, final=eq.iloc[-1])


def portfolio_returns(coin_nets):
    """coin_nets: {coin: net_return_series}. Esit-agirlik sepet (her bar mevcut
    coinlerin ortalamasi)."""
    M = pd.concat(coin_nets, axis=1)
    return M.mean(axis=1, skipna=True).fillna(0.0)


def walkforward_sharpe(net, tf, K=5):
    """Zaman cizgisini K ardisik fold'a bol, her fold Sharpe'i + kac pozitif."""
    net = net.dropna()
    bpy = _BPY.get(tf, 365)
    idx = net.index
    edges = pd.date_range(idx.min(), idx.max(), periods=K + 1)
    out = []
    for k in range(K):
        seg = net[(idx >= edges[k]) & (idx < edges[k + 1])]
        s = (seg.mean() / seg.std() * np.sqrt(bpy)) if seg.std() > 0 else 0.0
        out.append(s)
    return out
