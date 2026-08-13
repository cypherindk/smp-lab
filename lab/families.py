"""
lab/families.py — KALAN TUM STRATEJI AILELERI (kapsamli sup�rge).

Simdiye kadar hep AYNI aileyi aradik: fiyat uzerinde YONLU trend/momentum.
Bu dosya, denemedigimiz her aileyi test eder — hepsi ayni disiplinle
(IS/OOS bolme, maliyet dahil, Sharpe/CAGR/DD + OOS dogrulamasi):

  1) STAT ARB        — kointegrasyon cift ticareti (piyasa-notr, ort.donus)
  2) KESITSEL MOM    — guclu long / zayif short (goreli deger)
  3) KESITSEL REVERSAL — kaybedeni al / kazanani sat (kisa vade)
  4) ZAMAN-SERISI REVERSAL — dususte al (tek varlik ort.donus)
  5) LEAD-LAG        — BTC hareketi alt'lari onculuyor mu?
  6) MEVSIMSELLIK    — haftanin gunu / gunun saati etkisi
  7) VOL ANOMALISI   — dusuk-vol primi (long dusuk-vol / short yuksek-vol)

Veri: Binance gunluk + 4H, bedava. Maliyet: 10bps devir basina (gercekci taker).
DURUST: coklu test yapiyoruz -> her ek deneme DSR cezasini buyutur; sadece
IS VE OOS'ta birlikte ayakta kalan + ekonomik gerekcesi olan aile kabul edilir.
"""
import os
import sys
import itertools
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from data.crypto_fetcher import fetch_binance_ohlcv
from lab.breadth_wide import WIDE

DAYS = 700
COST = 10 / 1e4          # 10 bps devir basina (round-trip ~20bps)
IS_FRAC = 0.60


# ───────────────────────────────────────────── yardimcilar
def stats(r, ppy=365):
    r = pd.Series(r).dropna()
    if len(r) < 30 or r.std() == 0:
        return dict(sharpe=0.0, cagr=0.0, maxdd=0.0, n=len(r))
    eq = (1 + r).cumprod()
    return dict(sharpe=r.mean() / r.std() * np.sqrt(ppy),
                cagr=(eq.iloc[-1] ** (ppy / len(r)) - 1) * 100 if eq.iloc[-1] > 0 else -100,
                maxdd=(eq / eq.cummax() - 1).min() * 100, n=len(r))


def split(r):
    r = pd.Series(r).dropna()
    k = int(len(r) * IS_FRAC)
    return r.iloc[:k], r.iloc[k:]


def report(name, r, out):
    IS, OOS = split(r)
    a, b = stats(IS), stats(OOS)
    ok = (a["sharpe"] > 0.4 and b["sharpe"] > 0.4)
    flag = "  <== IS+OOS AYAKTA" if ok else ""
    print(f"  {name:30} | IS {a['sharpe']:6.2f} {a['cagr']:7.1f}% | "
          f"OOS {b['sharpe']:6.2f} {b['cagr']:7.1f}% {b['maxdd']:7.1f}%{flag}", flush=True)
    out.append((name, a, b, ok))


def ols_beta(y, x):
    A = np.column_stack([np.ones(len(x)), x])
    return np.linalg.lstsq(A, y, rcond=None)[0]


def adf_tstat(y, lags=1):
    """Augmented Dickey-Fuller t-istatistigi (numpy ile). < -3.0 = duragan/kointegre."""
    y = np.asarray(y, float)
    dy = np.diff(y)
    if len(dy) < lags + 10:
        return 0.0
    Y = dy[lags:]
    cols = [np.ones(len(Y)), y[lags:-1]]
    for i in range(1, lags + 1):
        cols.append(dy[lags - i:-i] if i else dy)
    X = np.column_stack(cols)
    try:
        beta = np.linalg.lstsq(X, Y, rcond=None)[0]
        resid = Y - X @ beta
        dof = max(len(Y) - X.shape[1], 1)
        s2 = float(resid @ resid) / dof
        se = np.sqrt(s2 * np.linalg.pinv(X.T @ X)[1, 1])
        return float(beta[1] / se) if se > 0 else 0.0
    except Exception:
        return 0.0


# ───────────────────────────────────────────── veri
def load(interval="1d"):
    px, ok = {}, []
    for c in WIDE:
        try:
            d = fetch_binance_ohlcv(c, interval=interval, days=DAYS, quiet=True)
            if len(d) < (300 if interval == "1d" else 1200):
                continue
            s = d["close"].copy()
            s.index = pd.DatetimeIndex(s.index).tz_localize(None)
            px[c] = s
            ok.append(c)
        except Exception:
            pass
    P = pd.concat(px, axis=1).dropna(how="all").ffill()
    return P.dropna(axis=1)


# ───────────────────────────────────────────── 1) STAT ARB
def stat_arb(P, zin=2.0, zout=0.5, win=60, top=15):
    """IS'te kointegre ciftleri sec -> TUM donemde z-skor ort.donus ticareti."""
    L = np.log(P)
    k = int(len(L) * IS_FRAC)
    cands = []
    cols = list(L.columns)
    for a, b in itertools.combinations(cols, 2):
        ya, xb = L[a].iloc[:k].values, L[b].iloc[:k].values
        if np.isnan(ya).any() or np.isnan(xb).any():
            continue
        c0, beta = ols_beta(ya, xb)
        t = adf_tstat(ya - (c0 + beta * xb))
        if t < -3.0 and 0.2 < beta < 5.0:
            cands.append((t, a, b, beta))
    cands.sort()
    cands = cands[:top]
    if not cands:
        return pd.Series(dtype=float), 0
    legs = []
    for t, a, b, beta in cands:
        sp = L[a] - beta * L[b]
        z = (sp - sp.rolling(win).mean()) / sp.rolling(win).std().replace(0, np.nan)
        pos = np.zeros(len(z)); cur = 0.0
        zv = z.values
        for i in range(len(zv)):
            if np.isnan(zv[i]):
                pos[i] = 0.0; continue
            if cur == 0.0:
                if zv[i] > zin:   cur = -1.0      # spread genis -> short A / long B
                elif zv[i] < -zin: cur = 1.0
            elif abs(zv[i]) < zout:
                cur = 0.0
            pos[i] = cur
        pos = pd.Series(pos, index=z.index).shift(1).fillna(0.0)
        ra = P[a].pct_change().fillna(0.0)
        rb = P[b].pct_change().fillna(0.0)
        gross = pos * (ra - beta * rb) / (1 + beta)       # notional-normalize
        turn = pos.diff().abs().fillna(0.0) * (1 + beta) / (1 + beta)
        legs.append(gross - turn * COST * 2)
    return pd.concat(legs, axis=1).mean(axis=1), len(cands)


# ───────────────────────────────────────────── 2/3) KESITSEL
def cross_sectional(P, lookback, hold, reverse=False, n_side=6):
    R = P.pct_change()
    sig = P.pct_change(lookback)
    out = pd.Series(0.0, index=P.index)
    turn = pd.Series(0.0, index=P.index)
    prev = None
    for i in range(lookback + 1, len(P), hold):
        row = sig.iloc[i].dropna()
        if len(row) < 2 * n_side:
            continue
        rank = row.sort_values(ascending=reverse)
        shorts, longs = rank.index[:n_side], rank.index[-n_side:]
        w = pd.Series(0.0, index=P.columns)
        w[longs] = 1.0 / n_side; w[shorts] = -1.0 / n_side
        seg = R.iloc[i + 1:i + 1 + hold]
        if len(seg) == 0:
            continue
        out.loc[seg.index] = (seg * w).sum(axis=1)
        turn.loc[seg.index[0]] = (w - prev).abs().sum() if prev is not None else w.abs().sum()
        prev = w
    return out - turn * COST


# ───────────────────────────────────────────── 4) ZAMAN-SERISI REVERSAL
def ts_reversal(P, lookback=3, hold=2, thr=-0.05):
    R = P.pct_change()
    past = P.pct_change(lookback)
    sig = (past < thr).astype(float)                 # sert dususte al
    pos = sig.rolling(hold).max().shift(1).fillna(0.0)
    w = pos.div(pos.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    gross = (w * R).sum(axis=1)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    return gross - turn * COST


# ───────────────────────────────────────────── 5) LEAD-LAG
def lead_lag(P, leader="BTC-USD", thr=0.02):
    if leader not in P.columns:
        return pd.Series(dtype=float)
    R = P.pct_change()
    lead = R[leader].shift(1)
    alts = [c for c in P.columns if c != leader]
    sig = np.sign(lead).where(lead.abs() > thr, 0.0)
    pos = pd.DataFrame({c: sig for c in alts}, index=P.index)
    gross = (pos * R[alts]).mean(axis=1)
    turn = pos.diff().abs().mean(axis=1).fillna(0.0)
    return gross - turn * COST


# ───────────────────────────────────────────── 6) MEVSIMSELLIK
def seasonality(P4, out):
    """4H barlarda gunun saati + haftanin gunu etkisi (IS'te sec, OOS'ta dogrula)."""
    R = P4.pct_change().mean(axis=1).dropna()          # esit agirlik sepet
    k = int(len(R) * IS_FRAC)
    IS, OOS = R.iloc[:k], R.iloc[k:]
    # saat etkisi
    hi = IS.groupby(IS.index.hour).mean()
    best_h = list(hi.sort_values(ascending=False).index[:2])
    r_h = R.where(R.index.hour.isin(best_h), 0.0) - COST * (R.index.hour.isin(best_h)).astype(float)
    report(f"6a) Saat etkisi (IS'te en iyi {best_h})", r_h, out)
    # gun etkisi
    di = IS.groupby(IS.index.dayofweek).mean()
    best_d = list(di.sort_values(ascending=False).index[:2])
    r_d = R.where(R.index.dayofweek.isin(best_d), 0.0) - COST * (R.index.dayofweek.isin(best_d)).astype(float)
    report(f"6b) Gun etkisi (IS'te en iyi {best_d})", r_d, out)


# ───────────────────────────────────────────── 7) VOL ANOMALISI
def vol_anomaly(P, win=30, n_side=6, hold=7):
    R = P.pct_change()
    rv = R.rolling(win).std()
    out = pd.Series(0.0, index=P.index); turn = pd.Series(0.0, index=P.index)
    prev = None
    for i in range(win + 1, len(P), hold):
        row = rv.iloc[i].dropna()
        if len(row) < 2 * n_side:
            continue
        rank = row.sort_values()                      # dusuk vol -> long
        longs, shorts = rank.index[:n_side], rank.index[-n_side:]
        w = pd.Series(0.0, index=P.columns)
        w[longs] = 1.0 / n_side; w[shorts] = -1.0 / n_side
        seg = R.iloc[i + 1:i + 1 + hold]
        if len(seg) == 0:
            continue
        out.loc[seg.index] = (seg * w).sum(axis=1)
        turn.loc[seg.index[0]] = (w - prev).abs().sum() if prev is not None else w.abs().sum()
        prev = w
    return out - turn * COST


# ───────────────────────────────────────────── main
def main():
    print("=" * 100)
    print("  KALAN TUM STRATEJI AILELERI — kapsamli tarama (IS/OOS, maliyet dahil)")
    print("=" * 100)
    print("  Gunluk veri yukleniyor...", flush=True)
    P = load("1d")
    print(f"  {P.shape[1]} coin, {len(P)} gun ({P.index[0].date()} -> {P.index[-1].date()})\n", flush=True)

    out = []
    print(f"  {'AILE':30} | {'IN-SAMPLE':>22} | {'OUT-OF-SAMPLE':>30}")
    print("  " + "-" * 92)

    print("  1) Stat arb (kointegrasyon) hesaplaniyor...", flush=True)
    sa, npair = stat_arb(P)
    if len(sa):
        report(f"1) STAT ARB ({npair} cift)", sa, out)
    else:
        print("  1) STAT ARB: kointegre cift bulunamadi")

    report("2) Kesitsel MOM (30g/7g)", cross_sectional(P, 30, 7), out)
    report("2b) Kesitsel MOM (90g/30g)", cross_sectional(P, 90, 30), out)
    report("3) Kesitsel REVERSAL (5g/5g)", cross_sectional(P, 5, 5, reverse=True), out)
    report("3b) Kesitsel REVERSAL (1g/1g)", cross_sectional(P, 1, 1, reverse=True), out)
    report("4) TS reversal (3g dusus)", ts_reversal(P), out)
    report("5) Lead-lag (BTC -> alt)", lead_lag(P), out)
    report("7) Vol anomalisi (dusuk-vol)", vol_anomaly(P), out)

    print("\n  4H veri yukleniyor (mevsimsellik)...", flush=True)
    try:
        P4 = load("4h")
        seasonality(P4, out)
    except Exception as e:
        print(f"  mevsimsellik atlandi: {repr(e)[:50]}")

    # ─── verdict
    print("\n" + "=" * 100)
    survivors = [o for o in out if o[3]]
    if survivors:
        print("  IS VE OOS'TA AYAKTA KALANLAR (aday — sonra derin test):")
        for name, a, b, _ in survivors:
            print(f"    * {name:30} OOS Sharpe {b['sharpe']:.2f}  CAGR {b['cagr']:.1f}%  DD {b['maxdd']:.1f}%")
        print("\n  -> Bunlari SMP+Trend ile KORELASYONA sokup portfoye aday et.")
    else:
        print("  HICBIR AILE IS+OOS'ta ayakta kalmadi (esik: her ikisinde Sharpe>0.4).")
        print("  -> Kripto'da bu ailelerin bize ulasilabilir edge'i yok. Cekirdek sistemde kal.")
    print("\n  NOT: coklu test yaptik -> DSR cezasi buyudu. 'Ayakta kalan' bile")
    print("  ekonomik gerekce + korelasyon + derin OOS testinden gecmeden portfoye girmez.")


if __name__ == "__main__":
    main()
