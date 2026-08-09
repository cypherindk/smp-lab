"""
lab/cross_asset.py — CAPRAZ-VARLIK TREND TESTI (gercek CTA yolu).
Dogrulanmis TREND cekirdegimiz (Donchian + ER rejim + EMA trend) varlik-sinifi
BAGIMSIZ mi? Forex + endeks + emtia + tahvilde onlarca yillik veriyle test.

NEDEN: (1) kucuk orneklem (37 islem, DSR %50-65) -> bu piyasalarda cok daha cok
islem, (2) 60 altcoin sahte breadth'ti (hepsi BTC'yi takip eder) -> forex/endeks
GERCEK korelasyonsuz breadth, (3) Grinold: IR ~ IC*sqrt(breadth).

Veri: yfinance (bedava, gunluk, onlarca yil). YERELDE kosar: python lab/cross_asset.py
DURUST: trend-takibi burada long/short (futures/forex'te short kolay). Sadece LAB.
"""
import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import yfinance as yf

UNIVERSE = {
    # --- Forex (majorler) ---
    "EURUSD=X": "FX", "GBPUSD=X": "FX", "USDJPY=X": "FX", "AUDUSD=X": "FX",
    "USDCHF=X": "FX", "USDCAD=X": "FX", "NZDUSD=X": "FX",
    # --- Endeksler ---
    "^GSPC": "ENDEKS", "^NDX": "ENDEKS", "^GDAXI": "ENDEKS", "^N225": "ENDEKS",
    "^FTSE": "ENDEKS", "^HSI": "ENDEKS",
    # --- Emtia ---
    "GC=F": "EMTIA", "SI=F": "EMTIA", "CL=F": "EMTIA", "NG=F": "EMTIA",
    "HG=F": "EMTIA", "ZC=F": "EMTIA",
    # --- Tahvil ---
    "ZN=F": "TAHVIL", "ZB=F": "TAHVIL",
}
START = "2005-01-01"
COST_BPS = 5.0          # futures/FX gunluk: kripto'dan ucuz ama muhafazakar
TARGET_VOL = 0.15       # geleneksel varliklar kripto'dan cok daha az oynak


# ---------------------------------------------------------------- sinyal
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def efficiency_ratio(close, n=20):
    ch = (close - close.shift(n)).abs()
    path = close.diff().abs().rolling(n).sum()
    return (ch / path.replace(0, np.nan)).fillna(0.0)


def sig_donchian_ls(df, entry_n=55, exit_n=20, trend_ema=200):
    """Donchian breakout (long/short) + EMA trend filtresi. Durumsal pozisyon."""
    high, low, close = df["high"], df["low"], df["close"]
    up = high.rolling(entry_n).max().shift(1)
    dn = low.rolling(entry_n).min().shift(1)
    x_dn = low.rolling(exit_n).min().shift(1)
    x_up = high.rolling(exit_n).max().shift(1)
    te = ema(close, trend_ema)
    pos = np.zeros(len(df)); cur = 0.0
    c, u, d, xd, xu, t = (close.values, up.values, dn.values,
                          x_dn.values, x_up.values, te.values)
    for i in range(len(df)):
        if np.isnan(u[i]) or np.isnan(t[i]):
            pos[i] = 0.0; continue
        if cur == 0.0:
            if c[i] > u[i] and c[i] > t[i]:
                cur = 1.0
            elif c[i] < d[i] and c[i] < t[i]:
                cur = -1.0
        elif cur > 0 and c[i] < xd[i]:
            cur = 0.0
        elif cur < 0 and c[i] > xu[i]:
            cur = 0.0
        pos[i] = cur
    return pd.Series(pos, index=df.index)


def vol_target_returns(df, pos, target_vol=TARGET_VOL, cost_bps=COST_BPS,
                       vol_window=30, max_lev=3.0):
    r = df["close"].pct_change().fillna(0.0)
    rvol = (r.rolling(vol_window).std() * np.sqrt(365)).replace(0.0, np.nan)
    lev = (target_vol / rvol).clip(upper=max_lev).fillna(0.0)
    exposure = (pos.astype(float) * lev).fillna(0.0)
    held = exposure.shift(1).fillna(0.0)
    turn = (exposure - exposure.shift(1)).abs().fillna(0.0)
    return held * r - (turn * cost_bps / 1e4).shift(1).fillna(0.0)


def stats(net, ppy=252):
    net = net.fillna(0.0)
    eq = (1 + net).cumprod()
    n = max(len(net), 1)
    return dict(cagr=(eq.iloc[-1] ** (ppy / n) - 1) * 100 if eq.iloc[-1] > 0 else -100,
                sharpe=net.mean() / net.std() * np.sqrt(ppy) if net.std() > 0 else 0.0,
                maxdd=(eq / eq.cummax() - 1).min() * 100, n=n)


# ---------------------------------------------------------------- veri
def fetch(tk):
    d = yf.download(tk, start=START, progress=False, auto_adjust=True)
    if d is None or len(d) < 500:
        return None
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    d = d.rename(columns=str.lower)[["open", "high", "low", "close"]].dropna()
    d.index = pd.DatetimeIndex(d.index).tz_localize(None)
    return d if len(d) >= 500 else None


def main():
    print("=" * 86)
    print("  CAPRAZ-VARLIK TREND TESTI — trend cekirdegi varlik-sinifi bagimsiz mi?")
    print("=" * 86)
    print(f"  Veri cekiliyor ({len(UNIVERSE)} enstruman, {START}'ten beri, yfinance)...", flush=True)

    nets, by_class, loaded = {}, {}, []
    for tk, cls in UNIVERSE.items():
        try:
            df = fetch(tk)
            if df is None:
                print(f"    atla {tk}: veri yok/kisa", flush=True); continue
            pos = sig_donchian_ls(df)
            pos = pos.where(efficiency_ratio(df["close"], 20).shift(1) > 0.30, 0.0)  # ER rejim
            net = vol_target_returns(df, pos)
            nets[tk] = net
            by_class.setdefault(cls, []).append(tk)
            loaded.append((tk, cls, len(df), df.index[0].year))
        except Exception as e:
            print(f"    atla {tk}: {repr(e)[:45]}", flush=True)

    if not nets:
        print("  Veri alinamadi."); return
    yrs = max(len(n) for n in nets.values()) / 252
    print(f"  Yuklendi: {len(nets)} enstruman, ~{yrs:.0f} yil gecmis\n", flush=True)

    # --- enstruman bazinda ---
    print(f"  {'Enstruman':12} {'Sinif':8} | {'Sharpe':>7} {'CAGR':>7} {'MaxDD':>8} {'yil':>5}")
    print("  " + "-" * 58)
    for tk, cls, nbar, y0 in loaded:
        s = stats(nets[tk])
        print(f"  {tk:12} {cls:8} | {s['sharpe']:7.2f} {s['cagr']:6.1f}% {s['maxdd']:7.1f}% {nbar/252:5.0f}")

    # --- varlik sinifi bazinda (esit agirlik sepet) ---
    print(f"\n  {'VARLIK SINIFI':14} | {'Sharpe':>7} {'CAGR':>7} {'MaxDD':>8}  (sepet)")
    print("  " + "-" * 50)
    class_nets = {}
    for cls, tks in by_class.items():
        b = pd.concat({t: nets[t] for t in tks}, axis=1).mean(axis=1, skipna=True).fillna(0.0)
        class_nets[cls] = b
        s = stats(b)
        print(f"  {cls:14} | {s['sharpe']:7.2f} {s['cagr']:6.1f}% {s['maxdd']:7.1f}%")

    # --- tum capraz-varlik portfoy ---
    ALL = pd.concat(nets, axis=1).mean(axis=1, skipna=True).fillna(0.0)
    s = stats(ALL)
    print(f"\n  {'TUM CAPRAZ-VARLIK':14} | {s['sharpe']:7.2f} {s['cagr']:6.1f}% {s['maxdd']:7.1f}%"
          f"   <- {len(nets)} enstruman birlesik")

    # --- walk-forward: 4 esit donem ---
    print(f"\n  WALK-FORWARD (4 esit donem, tum portfoy) — edge zamanla tutuyor mu?")
    idx = ALL.index
    edges = pd.date_range(idx.min(), idx.max(), periods=5)
    pos_folds = 0
    for i in range(4):
        seg = ALL[(idx >= edges[i]) & (idx < edges[i + 1])]
        if len(seg) < 50:
            continue
        ss = stats(seg)
        pos_folds += 1 if ss["sharpe"] > 0 else 0
        print(f"    {str(edges[i])[:7]} - {str(edges[i+1])[:7]} | Sharpe {ss['sharpe']:6.2f}  "
              f"CAGR {ss['cagr']:6.1f}%  DD {ss['maxdd']:6.1f}%")
    print(f"    -> {pos_folds}/4 donem pozitif")

    # --- korelasyon: sinif-arasi ---
    if len(class_nets) > 1:
        C = pd.concat(class_nets, axis=1).fillna(0.0)
        print(f"\n  SINIF-ARASI KORELASYON (dusuk = gercek cesitlendirme):")
        print("    " + C.corr().round(2).to_string().replace("\n", "\n    "))

    print(f"\n  OKUMA: Sharpe>0.5 + 3-4/4 donem pozitif + dusuk korelasyon = trend cekirdegi")
    print("  VARLIK-SINIFI BAGIMSIZ (gercek CTA breadth'i) -> kripto'ya EKLENEBILIR.")
    print("  Not: maliyet 5bps, vol hedefi %15, long/short. Gecmis performans.")


if __name__ == "__main__":
    main()
