"""
lab/bist.py — BIST TESTI (kullanicinin fikri: "belki kriptodan cok kazandirir").

ONEMLI DURUSTLUK: BIST getirisini TL NOMINAL olcersen rakamlar SISKIN gorunur —
icinde enflasyon + kur kaybi vardir. "Aylik %8" harika gelir ama enflasyon %5 ise
gercek getiri %3'tur. Bu yuzden HER SEY IKI BAZDA raporlanir:
   TL  : nominal (yaniltici, ama insanlarin gordugu)
   USD : TL/USDTRY ile duzeltilmis -> kripto ile ELMAYLA ELMA kiyasi

Test edilen: dogrulanmis trend cekirdegimiz (Donchian55/20 + EMA200 + ER rejim),
LONG-ONLY (BIST'te short pratik degil), vol-hedefli, maliyet dahil, IS/OOS bolme.
Kiyas: al-tut (BIST) ve sadece-dolar-tut.

Not: altin ve forex ZATEN test edildi (lab/cross_asset.py): altin Sharpe 0.11,
forex -0.27 -> kripto'nun cok altinda. BIST tek denenmemis olandi.
"""
import os
import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import yfinance as yf

START = "2019-01-01"
COST_BPS = 15.0        # BIST komisyon+spread, muhafazakar
TARGET_VOL = 0.25
IS_FRAC = 0.60

BIST = ["AEFES", "AGHOL", "AKBNK", "AKSA", "AKSEN", "ALARK", "ARCLK", "ASELS",
        "BIMAS", "BRSAN", "BRYAT", "CCOLA", "CIMSA", "DOAS", "DOHOL", "ECILC",
        "EGEEN", "EKGYO", "ENJSA", "ENKAI", "EREGL", "FROTO", "GARAN", "GUBRF",
        "HALKB", "HEKTS", "ISCTR", "KCHOL", "KORDS", "KRDMD", "LOGO", "MAVI",
        "MGROS", "ODAS", "OTKAR", "OYAKC", "PETKM", "PGSUS", "SAHOL", "SASA",
        "SISE", "SOKM", "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO", "TSKB",
        "TTKOM", "TTRAK", "TUPRS", "ULKER", "VAKBN", "VESTL", "YKBNK", "ZOREN"]


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def efficiency_ratio(close, n=20):
    ch = (close - close.shift(n)).abs()
    path = close.diff().abs().rolling(n).sum()
    return (ch / path.replace(0, np.nan)).fillna(0.0)


def sig_donchian_long(df, entry_n=55, exit_n=20, trend_ema=200):
    high, low, close = df["high"], df["low"], df["close"]
    up = high.rolling(entry_n).max().shift(1).values
    xd = low.rolling(exit_n).min().shift(1).values
    te = ema(close, trend_ema).values
    c = close.values
    pos = np.zeros(len(df)); cur = 0.0
    for i in range(len(df)):
        if np.isnan(up[i]) or np.isnan(te[i]):
            pos[i] = 0.0; continue
        if cur == 0.0:
            if c[i] > up[i] and c[i] > te[i]:
                cur = 1.0
        elif c[i] < xd[i]:
            cur = 0.0
        pos[i] = cur
    return pd.Series(pos, index=df.index)


def vol_target(df, pos, target=TARGET_VOL, cost_bps=COST_BPS, win=30, cap=2.0):
    r = df["close"].pct_change().fillna(0.0)
    rv = (r.rolling(win).std() * np.sqrt(252)).replace(0.0, np.nan)
    lev = (target / rv).clip(upper=cap).fillna(0.0)
    exp_ = (pos.astype(float) * lev).fillna(0.0)
    held = exp_.shift(1).fillna(0.0)
    turn = (exp_ - exp_.shift(1)).abs().fillna(0.0)
    return held * r - (turn * cost_bps / 1e4).shift(1).fillna(0.0)


def stats(r, ppy=252):
    r = pd.Series(r).dropna()
    if len(r) < 40 or r.std() == 0:
        return dict(sharpe=0.0, cagr=0.0, maxdd=0.0)
    eq = (1 + r).cumprod()
    return dict(sharpe=r.mean() / r.std() * np.sqrt(ppy),
                cagr=(eq.iloc[-1] ** (ppy / len(r)) - 1) * 100 if eq.iloc[-1] > 0 else -100,
                maxdd=(eq / eq.cummax() - 1).min() * 100)


def split(r):
    r = pd.Series(r).dropna()
    k = int(len(r) * IS_FRAC)
    return r.iloc[:k], r.iloc[k:]


def fetch(tk):
    d = yf.download(tk, start=START, progress=False, auto_adjust=True)
    if d is None or len(d) < 400:
        return None
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    d = d.rename(columns=str.lower)[["open", "high", "low", "close"]].dropna()
    d.index = pd.DatetimeIndex(d.index).tz_localize(None)
    return d if len(d) >= 400 else None


def line(name, r):
    IS, OOS = split(r)
    a, b = stats(IS), stats(OOS)
    print(f"  {name:34} | IS {a['sharpe']:6.2f} {a['cagr']:7.1f}% | "
          f"OOS {b['sharpe']:6.2f} {b['cagr']:7.1f}% {b['maxdd']:7.1f}%", flush=True)
    return b


def main():
    print("=" * 96)
    print("  BIST TESTI — trend cekirdegi (Donchian+EMA+ER), TL vs USD bazinda")
    print("=" * 96)
    print(f"  Veri cekiliyor ({len(BIST)} hisse + USDTRY, {START}'ten beri)...", flush=True)

    usdtry = fetch("USDTRY=X")
    if usdtry is None:
        print("  USDTRY alinamadi."); return
    fx = usdtry["close"]

    nets_tl, nets_usd, bh_tl, bh_usd, ok = {}, {}, {}, {}, 0
    for t in BIST:
        try:
            df = fetch(t + ".IS")
            if df is None:
                continue
            # TL bazinda
            pos = sig_donchian_long(df)
            pos = pos.where(efficiency_ratio(df["close"], 20).shift(1) > 0.30, 0.0)
            nets_tl[t] = vol_target(df, pos)
            bh_tl[t] = df["close"].pct_change()
            # USD bazinda: fiyati dolara cevir, ayni sistemi kos
            f = fx.reindex(df.index).ffill()
            du = df.div(f, axis=0).dropna()
            if len(du) < 400:
                continue
            pu = sig_donchian_long(du)
            pu = pu.where(efficiency_ratio(du["close"], 20).shift(1) > 0.30, 0.0)
            nets_usd[t] = vol_target(du, pu)
            bh_usd[t] = du["close"].pct_change()
            ok += 1
        except Exception:
            pass

    if ok < 10:
        print(f"  Yeterli hisse yuklenemedi ({ok})."); return
    print(f"  Yuklendi: {ok} hisse\n", flush=True)

    PTL = pd.concat(nets_tl, axis=1).mean(axis=1, skipna=True).fillna(0.0)
    PUS = pd.concat(nets_usd, axis=1).mean(axis=1, skipna=True).fillna(0.0)
    BTL = pd.concat(bh_tl, axis=1).mean(axis=1, skipna=True).fillna(0.0)
    BUS = pd.concat(bh_usd, axis=1).mean(axis=1, skipna=True).fillna(0.0)

    print(f"  {'Kurulum':34} | {'IN-SAMPLE':>20} | {'OUT-OF-SAMPLE':>28}")
    print("  " + "-" * 88)
    print("  --- TL BAZINDA (nominal — enflasyon+kur kaybi ICINDE, YANILTICI) ---")
    line("Trend sistemi (TL)", PTL)
    line("Al-tut BIST sepeti (TL)", BTL)
    print("  --- USD BAZINDA (gercek satin alma gucu — kripto ile kiyaslanabilir) ---")
    b_sys = line("Trend sistemi (USD)", PUS)
    b_bh = line("Al-tut BIST sepeti (USD)", BUS)

    # TL yanilsamasinin buyuklugu
    yrs = len(fx) / 252
    fx_cagr = (fx.iloc[-1] / fx.iloc[0]) ** (1 / yrs) - 1
    print(f"\n  USDTRY yillik degisim: %{fx_cagr*100:.1f}  <- TL getirilerinin BU KADARI kur kaybi")

    print("\n  KIYAS — kripto cekirdegimiz (dogrulanmis): CAGR ~%23, MaxDD ~-%6.8, Sharpe 1.54")
    print(f"  BIST trend (USD)     : CAGR %{b_sys['cagr']:.1f}, MaxDD %{b_sys['maxdd']:.1f}, "
          f"Sharpe {b_sys['sharpe']:.2f}")
    if b_sys["sharpe"] > 0.8 and b_sys["cagr"] > 15:
        print("\n  -> BIST (USD bazinda) CIDDI ADAY. Korelasyona sok, portfoye ekle.")
    elif b_sys["sharpe"] > 0.4:
        print("\n  -> BIST zayif-orta. Ancak korelasyon dusukse cesitlendirici olarak dusun.")
    else:
        print("\n  -> BIST trend sistemi USD bazinda YETERSIZ. TL'deki parlak rakam kur yanilsamasi.")
    print("\n  NOT: BIST'te short pratik degil (long-only), islem maliyeti 15bps varsayildi.")


if __name__ == "__main__":
    main()
