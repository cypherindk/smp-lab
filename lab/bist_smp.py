"""
lab/bist_smp.py — SMP MANTIGI BIST'TE (kullanicinin Matriks .mib fikrinin on-testi).

NEDEN ONCE BU: Matriks'te simulasyon kurmak kolay ama Matriks TL bazinda ve
IN-SAMPLE sonuc verir — TradingView'in "%40-50"si gibi yaniltici. Once KENDI
labimizda, USD duzeltmeli + IS/OOS bolmeli test edelim. Gecerse .mib yazmak
anlamli; gecmezse bos yere ugrasmayiz.

NOT: `lab/bist.py` TREND cekirdegini gunlukte test etti (USD Sharpe 0.35 = yetersiz).
Bu dosya SMP'nin KENDI mantigini intraday'de test eder (denenmemis olan buydu).

Veri: yfinance 1h / 730 gun -> 4H'e yeniden orneklenir (SMP 4H'te kalibre).
BIST GERCEGI: aciga satis kisitli -> LONG-ONLY sonuc ayrica raporlanir.
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
from engine.indicators import compute_all_indicators
from engine.signals import calc_bull_bear_score, calc_triggers, generate_signals
from engine.filters import apply_all_filters
from lab.breadth_wide import efficiency_ratio, gated

FEE, SLIP = 0.0008, 0.0005          # BIST komisyon+spread (kriptodan pahali)
ADR_MULT, RR = 1.5, 2.0
ER_MIN = 0.15

BIST = ["THYAO", "GARAN", "AKBNK", "ISCTR", "YKBNK", "VAKBN", "HALKB", "SAHOL",
        "KCHOL", "EREGL", "TUPRS", "BIMAS", "ASELS", "SISE", "PETKM", "TOASO",
        "FROTO", "TCELL", "TTKOM", "PGSUS", "SASA", "KRDMD", "ARCLK", "TAVHL",
        "MGROS", "ENKAI", "OYAKC", "TKFEN", "ULKER", "AEFES", "DOAS", "EKGYO",
        "GUBRF", "HEKTS", "ALARK", "AKSEN", "CCOLA", "TTRAK", "VESTL", "SOKM"]


def fetch_1h(tk, period="730d"):
    # BIST hisseleri ".IS" ister; USDTRY=X gibi hazir semboller aynen kullanilir
    sym = tk if ("=" in tk or "." in tk) else tk + ".IS"
    d = yf.download(sym, interval="1h", period=period, progress=False, auto_adjust=True)
    if d is None or len(d) < 800:
        return None
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    d = d.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
    d.index = pd.DatetimeIndex(d.index).tz_localize(None)
    return d


def to_4h(d):
    o = d.resample("4h").agg({"open": "first", "high": "max", "low": "min",
                              "close": "last", "volume": "sum"}).dropna()
    return o


def smp_trades(df, tf_min, usd_fx=None):
    """SMP no-RSI + A+ + ER kapisi -> islemler. usd_fx verilirse USD bazinda."""
    if usd_fx is not None:
        f = usd_fx.reindex(df.index).ffill()
        df = df.copy()
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] / f
        df = df.dropna()
        if len(df) < 300:
            return []
    ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=tf_min, adr_mult=ADR_MULT)
    sc = calc_bull_bear_score(ind, mtf=None, drop={"rsi"})
    tr = calc_triggers(ind, sc)
    sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                          min_conf=2, grade_filter="A+ Only")
    fs = apply_all_filters(ind, sg, use_cvd=True)
    fs = gated(fs, efficiency_ratio(df["close"], 20) > ER_MIN)
    o, h, l, c = (df["open"].values, df["high"].values, df["low"].values, df["close"].values)
    stop = (ind["safe_stop_pct"] / 100.0).values
    buy, sell = fs["buy_signal"].values, fs["sell_signal"].values
    n, out, i = len(df), [], 0
    while i < n - 1:
        if (buy[i] or sell[i]) and not (np.isnan(stop[i]) or stop[i] <= 0):
            side = 1 if buy[i] else -1
            entry = o[i + 1] * (1 + SLIP * side)
            sp = stop[i]
            sl = entry * (1 - sp * side); tp = entry * (1 + sp * RR * side)
            risk = abs(entry - sl)
            ex, j = None, i + 1
            while j < n:
                if side == 1:
                    if l[j] <= sl: ex = sl; break
                    if h[j] >= tp: ex = tp; break
                else:
                    if h[j] >= sl: ex = sl; break
                    if l[j] <= tp: ex = tp; break
                j += 1
            if ex is None:
                ex = c[n - 1]; j = n - 1
            pnl = (ex - entry) * side - entry * 2 * FEE
            out.append(dict(t=df.index[i + 1], R=pnl / risk, side=side))
            i = j + 1
        else:
            i += 1
    return out


def stats(T):
    if not T:
        return dict(n=0, wr=0, exp=0, pf=0)
    R = np.array([x["R"] for x in T])
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return dict(n=len(R), wr=(R > 0).mean() * 100, exp=R.mean(), pf=g / l if l > 0 else 9.99)


def line(name, T):
    T = sorted(T, key=lambda x: x["t"])
    a = stats(T); o = stats(T[int(len(T) * 0.6):])
    print(f"  {name:34} | {a['n']:4d} {a['wr']:5.1f}% {a['exp']:+7.3f}R {a['pf']:5.2f} "
          f"| OOS {o['n']:3d}i {o['exp']:+7.3f}R", flush=True)
    return a, o


def main():
    print("=" * 96)
    print("  SMP MANTIGI BIST'TE — Matriks .mib fikrinin on-testi (TL vs USD, IS/OOS)")
    print("=" * 96)
    print(f"  {len(BIST)} hisse, 1h veri (730g) -> 4H, SMP no-RSI + A+ + ER>{ER_MIN}", flush=True)

    fx1h = fetch_1h("USDTRY=X")
    fx = to_4h(fx1h)["close"] if fx1h is not None else None
    if fx is None:
        print("  USDTRY alinamadi, sadece TL bazinda kosulacak.", flush=True)

    T_tl, T_usd, ok = [], [], 0
    for t in BIST:
        try:
            d1 = fetch_1h(t)
            if d1 is None:
                continue
            d4 = to_4h(d1)
            if len(d4) < 400:
                continue
            T_tl += smp_trades(d4, 240)
            if fx is not None:
                T_usd += smp_trades(d4, 240, usd_fx=fx)
            ok += 1
        except Exception:
            pass
    print(f"  Yuklendi: {ok} hisse\n", flush=True)

    if not T_tl:
        print("  Hic sinyal uretilmedi."); return

    print(f"  {'Kurulum':34} | {'n':>4} {'win%':>6} {'beklenti':>8} {'PF':>5} | {'OOS':>16}")
    print("  " + "-" * 88)
    line("TL bazinda — TUM (long+short)", T_tl)
    line("TL bazinda — SADECE LONG *", [x for x in T_tl if x["side"] == 1])
    if T_usd:
        print("  " + "-" * 88)
        a_all, o_all = line("USD bazinda — TUM (long+short)", T_usd)
        a_l, o_l = line("USD bazinda — SADECE LONG *", [x for x in T_usd if x["side"] == 1])

        print("\n  * BIST'te aciga satis KISITLI -> gercekci senaryo SADECE LONG + USD bazinda.")
        print(f"\n  KIYAS — kripto cekirdegimiz: +0.667R beklenti, PF 2.4, OOS +0.85R")
        print(f"  BIST (USD, long-only)      : {a_l['exp']:+.3f}R beklenti, PF {a_l['pf']:.2f}, "
              f"OOS {o_l['exp']:+.3f}R  ({a_l['n']} islem)")
        good = a_l["exp"] > 0.25 and o_l["exp"] > 0.15 and a_l["n"] >= 30
        print("\n  VERDICT: " + ("BIST ADAY — .mib yazmaya deger, korelasyona sok ✓" if good else
                                 "BIST YETERSIZ — Matriks'te simulasyon kurmaya degmez ✗"))
    print("\n  NOT: Matriks simulasyonu TL + in-sample gosterir; bu test USD + OOS.")


if __name__ == "__main__":
    main()
