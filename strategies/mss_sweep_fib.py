"""
strategies/mss_sweep_fib.py
SETUP A — "MSS Sweep Fib Retrace" (LuxAlgo mantiginin yeniden uygulamasi).

Akis (bullish):
  1) Likidite supurme: fiyat son swing low'u fitille asagi kirar ama USTUNE
     kapanir (sell-side likidite alindi, dip tutmadi).
  2) MSS (Market Structure Shift): supurme sonrasi `mss_window` bar icinde
     kapanis, supurme anindaki son swing HIGH'i yukari kirar (istege bagli
     displacement/momentum mumuyla).
  3) Fib girisi: supurme dibi (range_low) ile o ana kadarki tepe (range_high)
     arasinda %fib geri cekilmeye LIMIT emir. SL supurme dibinin altinda
     (ATR tamponu), TP = R:R.

Bearish tam simetrik. Cikti: event_engine.simulate() icin emir listesi.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ict import (swing_levels, atr, displacement,
                        liquidity_sweep, killzone_mask)


def build_orders(df: pd.DataFrame,
                 left: int = 5, right: int = 5,
                 mss_window: int = 10,
                 entry_fib: float = 0.5,
                 sl_atr: float = 0.5,
                 rr: float = 2.0,
                 require_displacement: bool = True,
                 disp_mult: float = 1.0,
                 use_killzone: bool = False,
                 trend_ema: int = None) -> list:
    high, low, close, open_ = df["high"], df["low"], df["close"], df["open"]
    n = len(df)

    sw = swing_levels(high, low, left, right)
    a = atr(high, low, close)
    disp = displacement(open_, high, low, close, a, body_mult=disp_mult)
    swp = liquidity_sweep(high, low, close, sw)
    kz = killzone_mask(df.index) if use_killzone else pd.Series(True, index=df.index)

    # HTF bias proxy: yurutme TF'inde EMA. close>ema -> sadece long,
    # close<ema -> sadece short. None ise filtre kapali.
    if trend_ema:
        ema_t = close.ewm(span=trend_ema, adjust=False).mean()
        trend_up = (close > ema_t).values
        trend_dn = (close < ema_t).values
    else:
        trend_up = np.ones(n, dtype=bool)
        trend_dn = np.ones(n, dtype=bool)

    H, L, C = high.values, low.values, close.values
    A = a.values
    sh_price = sw["sh_price"].values
    sl_price = sw["sl_price"].values
    sweep_bull = swp["sweep_bull"].values
    sweep_bear = swp["sweep_bear"].values
    disp_bull = disp["disp_bull"].values
    disp_bear = disp["disp_bear"].values
    KZ = kz.values

    orders = []
    pend_bull = None   # {"s","sweep_low","sh","deadline","range_high"}
    pend_bear = None
    n_sweep_b = n_sweep_s = 0

    for i in range(n):
        # yeni supurme kaydet (gecerli swing seviyesi varsa)
        if sweep_bull[i] and not np.isnan(sh_price[i]):
            pend_bull = {"s": i, "sweep_low": L[i], "sh": sh_price[i],
                         "deadline": i + mss_window, "range_high": H[i]}
            n_sweep_b += 1
        if sweep_bear[i] and not np.isnan(sl_price[i]):
            pend_bear = {"s": i, "sweep_high": H[i], "sl": sl_price[i],
                         "deadline": i + mss_window, "range_low": L[i]}
            n_sweep_s += 1

        # bekleyen kurulumlarin tepe/dip araligini guncelle
        if pend_bull is not None:
            pend_bull["range_high"] = max(pend_bull["range_high"], H[i])
        if pend_bear is not None:
            pend_bear["range_low"] = min(pend_bear["range_low"], L[i])

        # ── bullish MSS onayi ──
        if pend_bull is not None:
            if i > pend_bull["deadline"]:
                pend_bull = None
            elif i > pend_bull["s"]:
                mss = C[i] > pend_bull["sh"] and (disp_bull[i] if require_displacement else True)
                if mss and KZ[i] and trend_up[i]:
                    rl = pend_bull["sweep_low"]
                    rh = pend_bull["range_high"]
                    if rh > rl:
                        entry = rh - entry_fib * (rh - rl)
                        sl = rl - sl_atr * A[i]
                        if entry > sl:
                            tp = entry + rr * (entry - sl)
                            orders.append({"signal_pos": i, "side": 1,
                                           "entry": entry, "sl": sl, "tp": tp})
                    pend_bull = None

        # ── bearish MSS onayi ──
        if pend_bear is not None:
            if i > pend_bear["deadline"]:
                pend_bear = None
            elif i > pend_bear["s"]:
                mss = C[i] < pend_bear["sl"] and (disp_bear[i] if require_displacement else True)
                if mss and KZ[i] and trend_dn[i]:
                    rh = pend_bear["sweep_high"]
                    rl = pend_bear["range_low"]
                    if rh > rl:
                        entry = rl + entry_fib * (rh - rl)
                        sl = rh + sl_atr * A[i]
                        if entry < sl:
                            tp = entry - rr * (sl - entry)   # entry'nin ALTINDA
                            orders.append({"signal_pos": i, "side": -1,
                                           "entry": entry, "sl": sl, "tp": tp})
                    pend_bear = None

    orders.sort(key=lambda x: x["signal_pos"])
    return orders


if __name__ == "__main__":
    from data.crypto_fetcher import fetch_binance_ohlcv
    from backtest.event_engine import simulate, print_stats

    tf = "15m"
    for coin in ["BTC-USD", "ETH-USD", "SOL-USD"]:
        df = fetch_binance_ohlcv(coin, interval=tf, days=120, quiet=True)
        orders = build_orders(df, rr=2.0, use_killzone=False)
        res = simulate(df, orders, tf=tf, initial_capital=100.0, risk_pct=0.01)
        print_stats(res["stats"], f"SETUP A — {coin} {tf} (120g, {len(orders)} kurulum)")
