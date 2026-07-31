"""
engine/ict.py
ICT / SMC ortak primitifleri — her iki setup (MSS Sweep Fib, True OB) da
bunlari kullanir.

TEMEL KURAL — LOOKAHEAD YOK:
  ta.pivothigh(left,right) bir pivotu ANCAK `right` bar SONRA "bilir".
  Bu yuzden tum "confirmed swing" serileri `right` kadar kaydirilir; yani
  bir pivotun degeri, gercek pivot barinda degil, onaylandigi (pivot_bar +
  right) barda kullanilabilir olur. Boylece backtest gelecegi gormez.

Uretilen primitifler:
  - find_pivots / swing_levels : swing high/low seviyeleri (as-of confirmed)
  - atr                        : ATR (Wilder/EMA)
  - liquidity_sweep            : likidite supurme (wick disari, close geri iceri)
  - displacement               : momentum/yer degistirme mumu
  - fair_value_gaps            : FVG (3 mumluk dengesizlik)
  - order_blocks               : son karsi mum (bullish/bearish OB)
"""

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────
def atr(high, low, close, period=14):
    """Wilder ATR (EMA yaklasik)."""
    hl = high - low
    hc = (high - close.shift(1)).abs()
    lc = (low - close.shift(1)).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


# ──────────────────────────────────────────────────────────────────
def find_pivots(high: pd.Series, low: pd.Series, left=5, right=5):
    """
    ta.pivothigh(high,left,right) / ta.pivotlow(low,left,right) esdegeri.

    Donen: (ph, pl) — pivot BARINDA fiyat, diger barlarda NaN. (Ham; henuz
    kaydirilmamis. Confirmed hali icin swing_levels kullan.)
    """
    n = len(high)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    h = high.values
    l = low.values
    for i in range(left, n - right):
        wh = h[i - left:i + right + 1]
        if h[i] == wh.max() and np.sum(wh == h[i]) == 1:
            ph[i] = h[i]
        wl = l[i - left:i + right + 1]
        if l[i] == wl.min() and np.sum(wl == l[i]) == 1:
            pl[i] = l[i]
    return pd.Series(ph, index=high.index), pd.Series(pl, index=low.index)


def swing_levels(high: pd.Series, low: pd.Series, left=5, right=5):
    """
    "Bar i itibariyle en son ONAYLANMIS swing high/low" serileri.

    Donen DataFrame kolonlari:
      sh_price, sh_bar : son swing high fiyati ve o pivotun bar konumu (pozisyon)
      sl_price, sl_bar : son swing low  fiyati ve o pivotun bar konumu
    Hepsi confirmed (pivot_bar + right barda biliniyor), ffill'li.
    """
    ph, pl = find_pivots(high, low, left, right)
    n = len(high)

    sh_price = np.full(n, np.nan)
    sh_bar = np.full(n, np.nan)
    sl_price = np.full(n, np.nan)
    sl_bar = np.full(n, np.nan)

    ph_v = ph.values
    pl_v = pl.values
    for i in range(n):
        if not np.isnan(ph_v[i]):
            c = min(i + right, n - 1)   # onay bari
            sh_price[c] = ph_v[i]
            sh_bar[c] = i
        if not np.isnan(pl_v[i]):
            c = min(i + right, n - 1)
            sl_price[c] = pl_v[i]
            sl_bar[c] = i

    out = pd.DataFrame({
        "sh_price": sh_price, "sh_bar": sh_bar,
        "sl_price": sl_price, "sl_bar": sl_bar,
    }, index=high.index)
    out[["sh_price", "sh_bar"]] = out[["sh_price", "sh_bar"]].ffill()
    out[["sl_price", "sl_bar"]] = out[["sl_price", "sl_bar"]].ffill()
    return out


# ──────────────────────────────────────────────────────────────────
def displacement(open_, high, low, close, atr_ser, body_mult=1.0):
    """
    Yer degistirme (momentum) mumu: govde ATR'nin `body_mult` kati veya
    ustunde. Bullish/bearish ayri.
    """
    body = (close - open_)
    strong = body.abs() >= (atr_ser * body_mult)
    return pd.DataFrame({
        "disp_bull": strong & (body > 0),
        "disp_bear": strong & (body < 0),
    }, index=close.index)


# ──────────────────────────────────────────────────────────────────
def liquidity_sweep(high, low, close, sw, wick_min_frac=0.0):
    """
    Likidite supurme:
      - bullish (sell-side likidite alindi): bar.low < son swing low VE
        close > o seviye  (fitil altina sarkti, geri kapandi) -> LONG kurulum
        cekirdegi.
      - bearish (buy-side likidite alindi): bar.high > son swing high VE
        close < o seviye -> SHORT kurulum cekirdegi.

    sw: swing_levels() ciktisi.
    Donen: sweep_bull, sweep_low(supurulen dip=bar.low), sweep_bear,
           sweep_high(bar.high), swept_sl_level, swept_sh_level
    """
    sl_level = sw["sl_price"]
    sh_level = sw["sh_price"]

    sweep_bull = (low < sl_level) & (close > sl_level) & sl_level.notna()
    sweep_bear = (high > sh_level) & (close < sh_level) & sh_level.notna()

    return pd.DataFrame({
        "sweep_bull": sweep_bull.fillna(False),
        "sweep_bear": sweep_bear.fillna(False),
        "sweep_low": low.where(sweep_bull),
        "sweep_high": high.where(sweep_bear),
        "swept_sl_level": sl_level.where(sweep_bull),
        "swept_sh_level": sh_level.where(sweep_bear),
    }, index=close.index)


# ──────────────────────────────────────────────────────────────────
def fair_value_gaps(high, low):
    """
    FVG (3 mumluk dengesizlik):
      - bullish FVG bar i'de: low[i] > high[i-2]  (bosluk: high[i-2]..low[i])
      - bearish FVG bar i'de: high[i] < low[i-2]  (bosluk: high[i]..low[i-2])
    Donen: fvg_bull, fvg_bear (bool) + bolge sinirlari (top/bot).
    """
    h2 = high.shift(2)
    l2 = low.shift(2)
    fvg_bull = low > h2
    fvg_bear = high < l2
    return pd.DataFrame({
        "fvg_bull": fvg_bull.fillna(False),
        "fvg_bear": fvg_bear.fillna(False),
        "fvg_bull_bot": h2.where(fvg_bull),   # bosluk alt siniri
        "fvg_bull_top": low.where(fvg_bull),  # bosluk ust siniri
        "fvg_bear_top": l2.where(fvg_bear),
        "fvg_bear_bot": high.where(fvg_bear),
    }, index=high.index)


# ──────────────────────────────────────────────────────────────────
def order_blocks(open_, high, low, close, disp):
    """
    Order Block: bir yer degistirme mumundan ONCEKI son karsi-yon mumu.
      - bullish OB: bullish displacement'tan onceki son BEARISH mum. Bolge =
        o mumun [low, high]'i. (Fiyat geri donup bu bolgeye girince long.)
      - bearish OB: bearish displacement'tan onceki son BULLISH mum.

    Donen (her bar icin, o barda YENI olusan OB'nin sinirlari; yoksa NaN):
      ob_bull_top, ob_bull_bot, ob_bear_top, ob_bear_bot
    """
    n = len(close)
    o = open_.values; h = high.values; l = low.values; c = close.values
    db = disp["disp_bull"].values
    ds = disp["disp_bear"].values

    ob_bull_top = np.full(n, np.nan)
    ob_bull_bot = np.full(n, np.nan)
    ob_bear_top = np.full(n, np.nan)
    ob_bear_bot = np.full(n, np.nan)

    for i in range(1, n):
        if db[i]:  # bullish displacement -> geriye dogru son bearish mumu bul
            for j in range(i - 1, max(-1, i - 11), -1):
                if c[j] < o[j]:
                    ob_bull_top[i] = h[j]
                    ob_bull_bot[i] = l[j]
                    break
        if ds[i]:
            for j in range(i - 1, max(-1, i - 11), -1):
                if c[j] > o[j]:
                    ob_bear_top[i] = h[j]
                    ob_bear_bot[i] = l[j]
                    break

    return pd.DataFrame({
        "ob_bull_top": ob_bull_top, "ob_bull_bot": ob_bull_bot,
        "ob_bear_top": ob_bear_top, "ob_bear_bot": ob_bear_bot,
    }, index=close.index)


# ──────────────────────────────────────────────────────────────────
def killzone_mask(index: pd.DatetimeIndex, zones=None, tz="America/New_York"):
    """
    ICT killzone filtresi. index UTC olmali. `zones`: [(start_h, end_h), ...]
    NY saatiyle. Varsayilan: London (02-05) + NY (07-10) NY-time.
    Kripto 7/24 ama bu saatler yine de en likit/hareketli pencereler.
    """
    if zones is None:
        zones = [(2, 5), (7, 10)]
    local = index.tz_convert(tz)
    hours = local.hour + local.minute / 60.0
    mask = np.zeros(len(index), dtype=bool)
    for a, b in zones:
        mask |= (hours >= a) & (hours < b)
    return pd.Series(mask, index=index)
