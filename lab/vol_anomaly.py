"""
lab/vol_anomaly.py — TEK HAYATTA KALANI ISKENCEYE SOK.

families.py'de sadece DUSUK-VOL ANOMALISI IS+OOS ayakta kaldi (OOS Sharpe 2.04,
CAGR %116). Bu rakam FAZLA IYI -> once cürütmeye calisiyoruz. Supheler:
  S1) Short bacagin FUNDING maliyeti modellenmedi (yuksek-vol alt short'u pahali)
  S2) OOS'ta alt-coin cokusu varsa "short high-vol" tek seferlik jackpot olabilir
      -> LONG-ONLY versiyonu edge'i tasiyor mu? (short'suz da kazaniyor mu?)
  S3) Tek donem mi? -> 6 aylik dilimlerde istikrar
  S4) Parametreye asiri duyarli mi? -> plato mu tepe mi (win/hold/n_side taramasi)
  S5) SMP+Trend ile korelasyon (cesitlendirme degeri var mi?)
Ekonomik gerekce VAR (betting-against-beta, akademide saglam) — ama gerekce
yetmez, testten gecmesi lazim.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "live"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from lab.families import load, stats, split, COST, IS_FRAC

# Kripto perp funding: yuksek-vol alt'larda short tutmak PAHALI olabilir.
# Muhafazakar tahmin: short bacaga yillik %15 maliyet (gunluk ~4bps).
SHORT_FUND_ANN = 0.15


def vol_sleeve(P, win=30, n_side=6, hold=7, mode="ls", short_cost=True):
    """mode: 'ls' long-short | 'lo' sadece long dusuk-vol | 'so' sadece short yuksek-vol"""
    R = P.pct_change()
    rv = R.rolling(win).std()
    out = pd.Series(0.0, index=P.index)
    turn = pd.Series(0.0, index=P.index)
    shortw = pd.Series(0.0, index=P.index)
    prev = None
    for i in range(win + 1, len(P), hold):
        row = rv.iloc[i].dropna()
        if len(row) < 2 * n_side:
            continue
        rank = row.sort_values()
        lo, hi = rank.index[:n_side], rank.index[-n_side:]
        w = pd.Series(0.0, index=P.columns)
        if mode in ("ls", "lo"):
            w[lo] = 1.0 / n_side
        if mode in ("ls", "so"):
            w[hi] = -1.0 / n_side
        seg = R.iloc[i + 1:i + 1 + hold]
        if len(seg) == 0:
            continue
        out.loc[seg.index] = (seg * w).sum(axis=1)
        turn.loc[seg.index[0]] = (w - prev).abs().sum() if prev is not None else w.abs().sum()
        shortw.loc[seg.index] = -w[w < 0].sum()          # short notional
        prev = w
    net = out - turn * COST
    if short_cost:
        net = net - shortw * (SHORT_FUND_ANN / 365.0)    # S1: funding maliyeti
    return net


def line(name, r):
    IS, OOS = split(r)
    a, b = stats(IS), stats(OOS)
    print(f"  {name:34} | IS {a['sharpe']:6.2f} {a['cagr']:7.1f}% | "
          f"OOS {b['sharpe']:6.2f} {b['cagr']:7.1f}% {b['maxdd']:7.1f}%", flush=True)
    return b


def main():
    print("=" * 96)
    print("  DUSUK-VOL ANOMALISI — ISKENCE TESTI (curutmeye calisiyoruz)")
    print("=" * 96)
    P = load("1d")
    print(f"  {P.shape[1]} coin, {len(P)} gun\n", flush=True)

    # ── S1+S2: bacak ayristirmasi + funding maliyeti
    print("  S1/S2) BACAK AYRISTIRMASI (edge nereden geliyor? short mu long mu?)")
    print(f"  {'Kurulum':34} | {'IN-SAMPLE':>20} | {'OUT-OF-SAMPLE':>28}")
    print("  " + "-" * 88)
    line("Long-Short (funding YOK — eski)", vol_sleeve(P, short_cost=False))
    b_ls = line("Long-Short (funding DAHIL)", vol_sleeve(P))
    b_lo = line("SADECE long dusuk-vol", vol_sleeve(P, mode="lo"))
    b_so = line("SADECE short yuksek-vol", vol_sleeve(P, mode="so"))

    # ── S3: donem istikrari
    print("\n  S3) 6-AYLIK DILIMLERDE ISTIKRAR (tek donem jackpot mi?)")
    r = vol_sleeve(P)
    per = r.resample("6ME")
    for ts, seg in per:
        if len(seg) < 40:
            continue
        s = stats(seg)
        mark = "  <- NEGATIF" if s["sharpe"] < 0 else ""
        print(f"    {str(ts)[:7]} | Sharpe {s['sharpe']:6.2f}  getiri {(1+seg).prod()*100-100:+7.1f}%{mark}", flush=True)

    # ── S4: parametre platosu mu, tepe mi?
    print("\n  S4) PARAMETRE ROBUSTLUGU (plato = gercek, tepe = overfit)")
    print(f"    {'win/hold/n':>14} | {'OOS Sharpe':>11} {'OOS CAGR':>10}")
    pos = 0; tot = 0
    for win in (20, 30, 60):
        for hold in (5, 7, 14):
            for n in (4, 6, 8):
                b = stats(split(vol_sleeve(P, win=win, n_side=n, hold=hold))[1])
                tot += 1; pos += 1 if b["sharpe"] > 0.4 else 0
                if (win, hold, n) in [(20, 5, 4), (30, 7, 6), (60, 14, 8), (20, 14, 6), (60, 5, 4)]:
                    print(f"    {f'{win}/{hold}/{n}':>14} | {b['sharpe']:11.2f} {b['cagr']:9.1f}%", flush=True)
    print(f"    -> {pos}/{tot} kombinasyon OOS Sharpe>0.4  "
          f"({'PLATO (saglam)' if pos >= tot * 0.6 else 'TEPE (kirilgan/overfit)'})")

    # ── S5: korelasyon
    print("\n  S5) MEVCUT SISTEMLE KORELASYON")
    try:
        from lab.portfolio import smp_daily, trend_daily, _naive_day
        smp = smp_daily(drop={"rsi"}); tr = trend_daily()
        tr.index = _naive_day(tr.index)
        M = pd.concat({"VolAnom": r, "SMP": smp, "Trend": tr}, axis=1).fillna(0.0)
        c = M.corr()
        print(f"    VolAnom-SMP {c.loc['VolAnom','SMP']:+.2f}   "
              f"VolAnom-Trend {c.loc['VolAnom','Trend']:+.2f}")
    except Exception as e:
        print(f"    korelasyon atlandi: {repr(e)[:60]}")

    print("\n" + "=" * 96)
    print("  KARAR REHBERI:")
    print("   * Edge SADECE short bacaktan geliyorsa (long-only cokuyorsa) -> alt-cokusu")
    print("     bahsi, gercek anomali degil. Short funding + likidite riski gercektir.")
    print("   * 6-aylik dilimlerin cogu negatifse -> tek donem jackpot, REDDET.")
    print("   * Parametre platosu yoksa -> overfit, REDDET.")
    print("   * Hepsi gecerse: KUCUK dilimle, funding maliyeti DAHIL, canli izlemeyle ekle.")


if __name__ == "__main__":
    main()
