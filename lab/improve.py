"""
lab/improve.py — MEVCUT SISTEMI IYILESTIRME (yeni edge aramiyoruz!).
Ayni sinyalleri kullaniyoruz; sadece CIKIS, ZAMAN DILIMI ve BOYUTLANDIRMAyi
optimize ediyoruz. Istatistiksel olarak daha guvenli: yeni edge iddiasi yok.

  A) CIKIS MODELI  — sabit TP yerine: TP taramasi, trailing (chandelier),
                     breakeven, kismi kar, zaman-stopu
  B) ZAMAN DILIMI  — 4H vs 1D (ayni SMP mantigi)
  C) BOYUTLANDIRMA — sabit %3 vs konviksiyon-olcekli (skor/ER)

Her sey IS/OOS bolmeli. DURUST: cikis parametresi taramak da coklu testtir ->
PLATO ariyoruz (genis bolge iyi), tepe degil.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from data.crypto_fetcher import fetch_binance_ohlcv
from engine.indicators import compute_all_indicators
from engine.signals import calc_bull_bear_score, calc_triggers, generate_signals
from engine.filters import apply_all_filters
from lab.breadth_wide import WIDE, efficiency_ratio, gated

DAYS = 600
FEE, SLIP = 0.0005, 0.0003


def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"].shift(1)
    return pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1).rolling(n).mean()


def sig_frame(df, adr_mult, tf_min):
    ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=tf_min, adr_mult=adr_mult)
    sc = calc_bull_bear_score(ind, mtf=None, drop={"rsi"})
    tr = calc_triggers(ind, sc)
    sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                          min_conf=2, grade_filter="A+ Only")
    fs = apply_all_filters(ind, sg, use_cvd=True)
    er = efficiency_ratio(df["close"], 20)
    fs = gated(fs, er > 0.15)
    return ind, fs, sg, er


def bt(df, ind, fs, sg, er, tp_mult=2.0, mode="fixed", trail_k=3.0,
       be_at=1.0, partial_at=1.0, max_bars=0):
    """mode: fixed | trail | be | partial | time"""
    o, h, l, c = (df["open"].values, df["high"].values, df["low"].values, df["close"].values)
    stop = (ind["safe_stop_pct"] / 100.0).values
    a = atr(df).values
    buy, sell = fs["buy_signal"].values, fs["sell_signal"].values
    bull = sg["total_bull_score"].values if "total_bull_score" in sg else np.zeros(len(df))
    bear = sg["total_bear_score"].values if "total_bear_score" in sg else np.zeros(len(df))
    ev = er.values
    n, out, i = len(df), [], 0
    while i < n - 1:
        if (buy[i] or sell[i]) and not (np.isnan(stop[i]) or stop[i] <= 0):
            side = 1 if buy[i] else -1
            entry = o[i + 1] * (1 + SLIP * side)
            sp = stop[i]
            sl = entry * (1 - sp * side)
            tp = entry * (1 + sp * tp_mult * side)
            risk = abs(entry - sl)
            best = entry
            realized, part_done = 0.0, False
            exit_p, j = None, i + 1
            while j < n:
                hi, lo = h[j], l[j]
                best = max(best, hi) if side == 1 else min(best, lo)
                # kismi kar
                if mode == "partial" and not part_done:
                    lvl = entry + side * risk * partial_at
                    if (side == 1 and hi >= lvl) or (side == -1 and lo <= lvl):
                        realized += 0.5 * partial_at        # yarisini 1R'da al
                        part_done = True
                        sl = entry                          # kalani breakeven'a cek
                # breakeven
                if mode == "be":
                    lvl = entry + side * risk * be_at
                    if (side == 1 and hi >= lvl) or (side == -1 and lo <= lvl):
                        sl = entry if side == 1 else entry
                # trailing (chandelier)
                if mode == "trail" and not np.isnan(a[j]):
                    ts = best - side * trail_k * a[j]
                    sl = max(sl, ts) if side == 1 else min(sl, ts)
                # cikis kontrolu
                if side == 1:
                    if lo <= sl: exit_p = sl; break
                    if mode != "trail" and hi >= tp: exit_p = tp; break
                else:
                    if hi >= sl: exit_p = sl; break
                    if mode != "trail" and lo <= tp: exit_p = tp; break
                if mode == "time" and max_bars and (j - i) >= max_bars:
                    exit_p = c[j]; break
                j += 1
            if exit_p is None:
                exit_p = c[n - 1]; j = n - 1
            pnl = (exit_p - entry) * side - entry * 2 * FEE
            R = pnl / risk
            if mode == "partial" and part_done:
                R = realized + 0.5 * R                      # yarisi 1R'da, yarisi sonda
            out.append(dict(entry_time=df.index[i + 1], R=R,
                            score=float(bull[i] if side == 1 else bear[i]),
                            er=float(ev[i]) if not np.isnan(ev[i]) else 0.0))
            i = j + 1
        else:
            i += 1
    return out


def load(tf, tf_min):
    data = {}
    for c in WIDE:
        try:
            df = fetch_binance_ohlcv(c, interval=tf, days=DAYS, quiet=True)
            need = 300 if tf == "4h" else 250
            if len(df) < need:
                continue
            data[c] = (df,) + sig_frame(df, WIDE[c][0], tf_min)
        except Exception:
            pass
    return data


def run_all(data, **kw):
    T = []
    for c, (df, ind, fs, sg, er) in data.items():
        kw2 = dict(kw)
        if kw2.get("tp_mult") == "rr":
            kw2["tp_mult"] = WIDE[c][1]
        T += bt(df, ind, fs, sg, er, **kw2)
    T.sort(key=lambda x: x["entry_time"])
    return T


def m(T):
    if not T:
        return dict(n=0, wr=0, exp=0, pf=0)
    R = np.array([t["R"] for t in T])
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return dict(n=len(R), wr=(R > 0).mean() * 100, exp=R.mean(), pf=g / l if l > 0 else 9.99)


def line(name, T, base=None):
    a = m(T); k = int(len(T) * 0.6)
    o = m(T[k:])
    d = f" ({a['exp']-base:+.3f})" if base is not None else ""
    print(f"  {name:30} | {a['n']:4d} {a['wr']:5.1f}% {a['exp']:+7.3f}R{d:>10} "
          f"{a['pf']:5.2f} | OOS {o['exp']:+7.3f}R", flush=True)
    return a["exp"]


def main():
    print("=" * 92)
    print("  SISTEM IYILESTIRME — cikis modeli / zaman dilimi / boyutlandirma")
    print("=" * 92)
    print("  4H veri yukleniyor...", flush=True)
    d4 = load("4h", 240)
    print(f"  {len(d4)} coin\n", flush=True)

    print(f"  {'Kurulum':30} | {'n':>4} {'win%':>6} {'beklenti':>8} {'delta':>10} {'PF':>5} | {'OOS':>12}")
    print("  " + "-" * 88)
    base = line("BASELINE (sabit TP=rr)", run_all(d4, tp_mult="rr", mode="fixed"))

    print("\n  A) CIKIS MODELI")
    print("   A1) sabit TP taramasi (plato mu tepe mi?)")
    for tp in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
        line(f"      TP = {tp:.1f}R", run_all(d4, tp_mult=tp, mode="fixed"), base)
    print("   A2) trailing / breakeven / kismi / zaman")
    for k in (2.0, 3.0, 4.0):
        line(f"      Trailing {k:.0f}xATR", run_all(d4, tp_mult="rr", mode="trail", trail_k=k), base)
    line("      Breakeven @1R", run_all(d4, tp_mult="rr", mode="be", be_at=1.0), base)
    line("      Kismi kar @1R (yari)", run_all(d4, tp_mult="rr", mode="partial"), base)
    for mb in (12, 24, 48):
        line(f"      Zaman stopu {mb} bar", run_all(d4, tp_mult="rr", mode="time", max_bars=mb), base)

    print("\n  B) ZAMAN DILIMI — ayni mantik gunlukte")
    try:
        d1 = load("1d", 1440)
        print(f"      ({len(d1)} coin gunluk veri)")
        line("      1D (sabit TP=rr)", run_all(d1, tp_mult="rr", mode="fixed"), base)
        line("      1D TP=2R", run_all(d1, tp_mult=2.0, mode="fixed"), base)
        line("      1D trailing 3xATR", run_all(d1, tp_mult="rr", mode="trail", trail_k=3.0), base)
    except Exception as e:
        print(f"      atlandi: {repr(e)[:50]}")

    # ── C) BOYUTLANDIRMA
    print("\n  C) BOYUTLANDIRMA — konviksiyon (skor/ER) ile olcekle")
    T = run_all(d4, tp_mult="rr", mode="fixed")
    if T:
        sc = np.array([t["score"] for t in T]); ers = np.array([t["er"] for t in T])
        R = np.array([t["R"] for t in T])
        print(f"      sabit  : ort agirlikli R {R.mean():+.3f}")
        for nm, v in [("skor", sc), ("ER", ers)]:
            if v.std() == 0:
                continue
            w = 1.0 + 0.5 * ((v - v.mean()) / v.std())      # +-0.5 sigma olcekleme
            w = np.clip(w, 0.5, 1.5)
            wr = (w * R).sum() / w.sum()
            print(f"      {nm:6} : ort agirlikli R {wr:+.3f}  ({wr-R.mean():+.3f}) "
                  f"{'iyilesme' if wr > R.mean()+0.02 else 'fayda yok'}")
        # ust/alt yari kiyasi (konviksiyon gercekten bilgi tasiyor mu?)
        for nm, v in [("skor", sc), ("ER", ers)]:
            hi = R[v >= np.median(v)]; lo = R[v < np.median(v)]
            if len(hi) > 3 and len(lo) > 3:
                print(f"      {nm:6} ust-yari {hi.mean():+.3f}R ({len(hi)}i) vs "
                      f"alt-yari {lo.mean():+.3f}R ({len(lo)}i)")

    print("\n  OKUMA: TP taramasinda GENIS bir bolge iyiyse -> plato (saglam).")
    print("  Tek bir deger parliyorsa -> overfit, baseline'da kal.")
    print("  Bir varyant hem beklentiyi hem OOS'u yukseltiyorsa -> aday.")


if __name__ == "__main__":
    main()


def followup():
    """Trailing PLATO mu TEPE mi? + slot cakismasi ne siklikta oluyor?"""
    print("=" * 92); print("  TAKIP TESTI"); print("=" * 92)
    d4 = load("4h", 240)
    base = m(run_all(d4, tp_mult="rr", mode="fixed"))["exp"]
    print(f"  baseline {base:+.3f}R\n")
    print("  1) TRAILING GENIS TARAMA (plato mu tepe mi?)")
    print(f"  {'kurulum':30} | {'n':>4} {'win%':>6} {'beklenti':>8} {'delta':>10} {'PF':>5} | {'OOS':>12}")
    for k in (3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        line(f"      Trailing {k:.0f}xATR", run_all(d4, tp_mult="rr", mode="trail", trail_k=k), base)
    print("\n  2) SADECE SL (TP YOK, ters sinyale/sona kadar) — ust sinir")
    line("      TP=20R (pratikte sinirsiz)", run_all(d4, tp_mult=20.0, mode="fixed"), base)
    print("\n  3) SLOT CAKISMASI — ayni anda kac sinyal yarisiyor?")
    T = run_all(d4, tp_mult="rr", mode="fixed")
    ts = sorted(pd.Timestamp(t["entry_time"]) for t in T)
    from collections import Counter
    days = Counter(t.normalize() for t in ts)
    multi = {d: c for d, c in days.items() if c > 1}
    print(f"      {len(T)} islem, {len(days)} farkli gun; ayni GUN birden fazla sinyal: {len(multi)} gun")
    if multi:
        print(f"      dagilim: {sorted(Counter(multi.values()).items())}")
    print(f"      -> cakisma {'NADIR: secim kurali pratikte fark etmez' if len(multi) < len(days)*0.2 else 'SIK: secim kurali onemli'}")
