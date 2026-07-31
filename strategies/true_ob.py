"""
strategies/true_ob.py
SETUP B — "True Order Block" (MTSY / Alpha Extract mantiginin sadelestirilmis,
çoklu-katman doğrulamalı yeniden uygulamasi).

Akis (bullish):
  1) Likidite supurme (sell-side): son swing low fitille kirilir, ustune kapanir.
  2) Yer degistirme (displacement): supurme sonrasi `window` bar icinde bir
     bullish momentum mumu (govde >= disp_mult*ATR).
  3) Local FVG dogrulamasi: o displacement bolgesinde bullish FVG (dengesizlik)
     olmali (istege bagli, require_fvg).
  4) MSS (istege bagli, require_mss): kapanis son swing high'i kirsin.
  5) POB (Order Block): displacement'tan onceki son BEARISH mum = talep bolgesi.
     Giris = OB'nin USTUNE (ob_top) LIMIT (fiyat geri donup dokununca al).
     SL = OB dibinin altinda (ATR tamponu), TP = R:R.

Bearish tam simetrik. Cikti: event_engine.simulate() icin emir listesi.
Setup A'dan FARKI: giris fib seviyesine degil, FVG ile doğrulanmis ORDER
BLOCK bolgesine yapilir (konfluens odakli, daha secici).
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ict import (swing_levels, atr, displacement, liquidity_sweep,
                        fair_value_gaps, order_blocks, killzone_mask)


def build_orders(df: pd.DataFrame,
                 left: int = 5, right: int = 5,
                 window: int = 8,
                 disp_mult: float = 1.0,
                 sl_atr: float = 0.5,
                 rr: float = 2.0,
                 ob_entry: str = "top",     # "top" | "mid"
                 require_fvg: bool = True,
                 require_mss: bool = False,
                 use_killzone: bool = False,
                 trend_ema: int = None) -> list:
    high, low, close, open_ = df["high"], df["low"], df["close"], df["open"]
    n = len(df)

    sw = swing_levels(high, low, left, right)
    a = atr(high, low, close)
    disp = displacement(open_, high, low, close, a, body_mult=disp_mult)
    swp = liquidity_sweep(high, low, close, sw)
    fvg = fair_value_gaps(high, low)
    obs = order_blocks(open_, high, low, close, disp)
    kz = killzone_mask(df.index) if use_killzone else pd.Series(True, index=df.index)

    if trend_ema:
        ema_t = close.ewm(span=trend_ema, adjust=False).mean()
        trend_up = (close > ema_t).values
        trend_dn = (close < ema_t).values
    else:
        trend_up = np.ones(n, dtype=bool)
        trend_dn = np.ones(n, dtype=bool)

    C = close.values; A = a.values
    sh_price = sw["sh_price"].values; sl_price = sw["sl_price"].values
    sweep_bull = swp["sweep_bull"].values; sweep_bear = swp["sweep_bear"].values
    disp_bull = disp["disp_bull"].values; disp_bear = disp["disp_bear"].values
    fvg_bull = fvg["fvg_bull"].values; fvg_bear = fvg["fvg_bear"].values
    ob_bt = obs["ob_bull_top"].values; ob_bb = obs["ob_bull_bot"].values
    ob_st = obs["ob_bear_top"].values; ob_sb = obs["ob_bear_bot"].values
    KZ = kz.values

    orders = []
    last_sweep_bull = -10**9
    last_sweep_bear = -10**9

    for i in range(n):
        if sweep_bull[i]:
            last_sweep_bull = i
        if sweep_bear[i]:
            last_sweep_bear = i

        # ── bullish OB kurulumu ──
        if (disp_bull[i] and (i - last_sweep_bull) <= window
                and not np.isnan(ob_bt[i]) and KZ[i] and trend_up[i]):
            fvg_ok = (not require_fvg) or fvg_bull[i] or (i > 0 and fvg_bull[i - 1])
            mss_ok = (not require_mss) or (not np.isnan(sh_price[i]) and C[i] > sh_price[i])
            if fvg_ok and mss_ok:
                top, bot = ob_bt[i], ob_bb[i]
                entry = top if ob_entry == "top" else (top + bot) / 2.0
                sl = bot - sl_atr * A[i]
                if entry > sl:
                    tp = entry + rr * (entry - sl)
                    orders.append({"signal_pos": i, "side": 1,
                                   "entry": entry, "sl": sl, "tp": tp})

        # ── bearish OB kurulumu ──
        if (disp_bear[i] and (i - last_sweep_bear) <= window
                and not np.isnan(ob_st[i]) and KZ[i] and trend_dn[i]):
            fvg_ok = (not require_fvg) or fvg_bear[i] or (i > 0 and fvg_bear[i - 1])
            mss_ok = (not require_mss) or (not np.isnan(sl_price[i]) and C[i] < sl_price[i])
            if fvg_ok and mss_ok:
                top, bot = ob_st[i], ob_sb[i]
                entry = bot if ob_entry == "top" else (top + bot) / 2.0
                sl = top + sl_atr * A[i]
                if entry < sl:
                    tp = entry - rr * (sl - entry)
                    orders.append({"signal_pos": i, "side": -1,
                                   "entry": entry, "sl": sl, "tp": tp})

    orders.sort(key=lambda x: x["signal_pos"])
    return orders
