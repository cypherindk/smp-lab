"""
lab/orderflow.py — ORDER FLOW FILTRESI (BEDAVA, Bookmap/DeepCharts'a gerek yok).

Binance klines'inin ICINDE zaten agresif (taker) alim hacmi var: `tbbav`.
  taker_ratio = taker_buy_volume / toplam_volume     (0..1)
    > 0.5 -> agresif ALICILAR baskin (piyasa emriyle aliyorlar)
    < 0.5 -> agresif SATICILAR baskin
Bu, footprint/delta/CVD'nin ta kendisi — yillarca gecmisi var, ucretsiz.

TEST: dogrulanmis SMP cekirdegimizin (no-RSI + A+ + ER>0.15, 30 coin)
sinyallerine order-flow FILTRESI eklemek edge'i iyilestiriyor mu?
  A) Onay    : LONG ise alis baskin olsun, SHORT ise satis baskin
  B) Guclu   : daha sIkI esik (0.55/0.45)
  C) Fade    : TERSI (akisi sonuk olani al) — belki flow bir fade sinyalidir
  D) Delta-z : akis z-skoru ile onay (rejime gore normalize)
DURUST: filtre orneklemi kucultur; n ve OOS'a bakip karar veririz. Actions/LAB.
"""
import os
import sys
import time
import requests
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from data.crypto_fetcher import to_binance_symbol, _BASES, _INTERVAL_MS
from data.crypto_fetcher import fetch_binance_ohlcv
from engine.indicators import compute_all_indicators
from engine.signals import calc_bull_bear_score, calc_triggers, generate_signals
from engine.filters import apply_all_filters
from lab.breadth_wide import WIDE, efficiency_ratio, gated
from lab.backtest_smp import backtest

DAYS = 600
INTERVAL = "4h"


# ─────────────────────────────────────────── order flow verisi
def fetch_orderflow(symbol, interval=INTERVAL, days=DAYS):
    """Klines'i TAKER ALIM hacmiyle birlikte cek -> taker_ratio + delta."""
    bsym = to_binance_symbol(symbol)
    step = _INTERVAL_MS[interval]
    end = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    start = end - days * 86_400_000
    rows, cur = [], start
    while cur < end:
        params = {"symbol": bsym, "interval": interval, "startTime": cur,
                  "endTime": min(cur + step * 1000, end), "limit": 1000}
        data = None
        for base in _BASES:
            try:
                r = requests.get(base + "/api/v3/klines", params=params, timeout=20)
                if r.status_code == 200:
                    data = r.json(); break
            except Exception:
                pass
        if not data:
            break
        rows += data
        cur = data[-1][0] + step
        time.sleep(0.05)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume",
                                     "close_time", "qav", "trades", "tbbav", "tbqav", "ignore"])
    df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df[~df.index.duplicated()]
    vol = df["volume"].astype(float)
    tbb = df["tbbav"].astype(float)                      # taker (agresif) ALIM hacmi
    out = pd.DataFrame(index=df.index)
    out["taker_ratio"] = (tbb / vol.replace(0, np.nan)).fillna(0.5)
    out["delta"] = 2 * tbb - vol                          # net agresif akis
    out["dz"] = ((out["delta"] - out["delta"].rolling(50).mean())
                 / out["delta"].rolling(50).std().replace(0, np.nan)).fillna(0.0)
    return out


# ─────────────────────────────────────────── SMP islemleri + akis etiketi
def collect_with_flow():
    trades = []
    for c in WIDE:
        try:
            df = fetch_binance_ohlcv(c, interval=INTERVAL, days=DAYS, quiet=True)
            if len(df) < 300:
                continue
            of = fetch_orderflow(c)
            if of.empty:
                continue
            ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=240,
                                         adr_mult=WIDE[c][0])
            sc = calc_bull_bear_score(ind, mtf=None, drop={"rsi"})
            tr = calc_triggers(ind, sc)
            sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                                  min_conf=2, grade_filter="A+ Only")
            fs = apply_all_filters(ind, sg, use_cvd=True)
            fs = gated(fs, efficiency_ratio(df["close"], 20) > 0.15)
            for _, r in backtest(df, ind, fs, WIDE[c][1]).iterrows():
                et = pd.Timestamp(r["entry_time"])
                if pd.isna(et):
                    continue
                if et.tzinfo is None:
                    et = et.tz_localize("UTC")
                prior = of[of.index < et]          # SINYAL bari (girisTEN ONCE bilinen)
                if prior.empty:
                    continue
                trades.append({"coin": c, "side": str(r.get("side", "LONG")).upper(),
                               "R": float(r["R"]), "entry": et,
                               "ratio": float(prior["taker_ratio"].iloc[-1]),
                               "dz": float(prior["dz"].iloc[-1])})
        except Exception:
            pass
    trades.sort(key=lambda x: x["entry"])
    return trades


# ─────────────────────────────────────────── metrikler
def metrics(ts):
    if not ts:
        return dict(n=0, wr=0, exp=0, pf=0)
    R = np.array([t["R"] for t in ts])
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return dict(n=len(R), wr=(R > 0).mean() * 100, exp=R.mean(),
                pf=(g / l if l > 0 else float("inf")))


def apply_filter(ts, mode, thr=0.50):
    out = []
    for t in ts:
        long_ = t["side"].startswith("L") or "BUY" in t["side"]
        if mode == "onay":
            ok = (t["ratio"] > thr) if long_ else (t["ratio"] < (1 - thr))
        elif mode == "fade":
            ok = (t["ratio"] < (1 - thr)) if long_ else (t["ratio"] > thr)
        elif mode == "dz":
            ok = (t["dz"] > 0) if long_ else (t["dz"] < 0)
        else:
            ok = True
        if ok:
            out.append(t)
    return out


def row(name, ts, base_n):
    m = metrics(ts)
    oos = metrics(ts[int(len(ts) * 0.6):]) if len(ts) >= 10 else dict(exp=0, n=0)
    keep = f"{m['n']}/{base_n}"
    print(f"  {name:26} | {keep:>8} {m['wr']:5.1f}% {m['exp']:+7.3f}R {m['pf']:6.2f} "
          f"{oos['exp']:+7.3f}R", flush=True)
    return m, oos


def main():
    print("=" * 84)
    print("  ORDER FLOW FILTRESI — Binance taker (agresif) alim akisi, BEDAVA")
    print("=" * 84)
    print("  Islem + akis verisi toplaniyor (30 coin, 4H)...", flush=True)
    ts = collect_with_flow()
    if not ts:
        print("  Veri alinamadi."); return
    base = metrics(ts)
    rr = np.array([t["ratio"] for t in ts])
    print(f"  {len(ts)} islem. Sinyal barindaki taker_ratio: ort {rr.mean():.3f} "
          f"(min {rr.min():.2f} / max {rr.max():.2f})\n", flush=True)

    print(f"  {'Kurulum':26} | {'kalan':>8} {'win%':>6} {'beklenti':>8} {'PF':>6} {'OOS':>8}")
    print("  " + "-" * 74)
    row("BASELINE (filtresiz)", ts, base["n"])
    print("  " + "-" * 74)
    a, _ = row("A) Onay  (0.50)", apply_filter(ts, "onay", 0.50), base["n"])
    b, _ = row("B) Guclu (0.55/0.45)", apply_filter(ts, "onay", 0.55), base["n"])
    c, _ = row("C) Fade  (tersi)", apply_filter(ts, "fade", 0.50), base["n"])
    d, _ = row("D) Delta z-skor", apply_filter(ts, "dz"), base["n"])

    print("\n  VERDICT:", flush=True)
    best, bn = None, None
    for nm, m in [("A) Onay", a), ("B) Guclu", b), ("C) Fade", c), ("D) Delta-z", d)]:
        if m["n"] >= 20 and m["exp"] > base["exp"] + 0.05:
            if best is None or m["exp"] > best["exp"]:
                best, bn = m, nm
    if best:
        print(f"    {bn} beklentiyi {base['exp']:+.3f}R -> {best['exp']:+.3f}R yukseltti "
              f"({best['n']} islem kaldi). ADAY — ama kucuk orneklem, OOS'a bak.")
    else:
        print(f"    Hicbir filtre yeterli iyilesme + orneklem (n>=20) saglamadi.")
        print(f"    -> ORDER FLOW FILTRESI GECMEDI. Baseline'da kal (beklenti {base['exp']:+.3f}R).")
    print("\n  NOT: filtre orneklemi kucultur; n<20 ise sonuc gurultu (bkz MinTRL~18).")


if __name__ == "__main__":
    main()
