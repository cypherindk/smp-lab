"""
lab/universe_robust.py — "FARKLI 30 COIN SECSEK?" sorusunun BILIMSEL versiyonu.

YANLIS soru: "hangi 30'lu kombinasyon en iyi sonucu verir?" -> evren cherry-pick'i,
   59 coinden 30'lu ~5e16 kombinasyon; en iyisi kesin harika gorunur, kesin sahtedir.
DOGRU soru: "bizim 30'umuz TESADUF MU? Coinleri degistirince edge ayakta mi?"

Testler:
  T1) JACKKNIFE  — her coini TEK TEK cikar; edge cokuyor mu? (bir-iki coin mi tasiyor)
  T2) YOGUNLASMA — toplam karin yuzde kaci en iyi 3 coinden geliyor?
  T3) RASTGELE ALT-KUMELER — 30'dan rastgele 15 coin sec, 500 kez; beklenti dagilimi
  T4) ALTERNATIF EVREN — hic kullanmadigimiz 29 coin tek basina ne veriyor?
  T5) COIN-BOOTSTRAP — coinleri (islemleri degil) yeniden ornekle -> evren belirsizligi

Edge GENIS TABANLIYSA: coin cikarmak/degistirmek onu bozmaz -> saglam.
Edge BIRKAC COINDE YOGUNSA: sansliyiz, canlida cokme riski yuksek.
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "live"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from validate import collect_smp_trades          # dogrulanmis cekirdek (no-RSI, A+, ER>0.15)
from lab.rotation import collect_all_trades, XL
from lab.breadth_wide import WIDE


def exp_of(trades):
    R = [t["R"] for t in trades]
    return (float(np.mean(R)), len(R)) if R else (0.0, 0)


def main():
    print("=" * 88)
    print("  EVREN SAGLAMLIK TESTI — 'bizim 30 coin tesaduf mu?'")
    print("=" * 88)
    print("  Islemler toplaniyor...", flush=True)
    tr = collect_smp_trades()                      # bizim 30 coin
    base_exp, base_n = exp_of(tr)
    coins = sorted({t["coin"] for t in tr})
    print(f"  Bizim evren: {len(WIDE)} coin, {base_n} islem, beklenti {base_exp:+.3f}R")
    print(f"  Islem ureten coin sayisi: {len(coins)}\n", flush=True)

    # ── T1 JACKKNIFE
    print("  T1) JACKKNIFE — her coini tek tek cikar (edge tek coine mi bagli?)")
    rows = []
    for c in coins:
        e, n = exp_of([t for t in tr if t["coin"] != c])
        rows.append((e, c, n))
    rows.sort()
    print(f"    En COK dusuren 5 (bu coinler edge'i tasiyor):")
    for e, c, n in rows[:5]:
        print(f"      {c:10} cikarilinca -> {e:+.3f}R  (delta {e-base_exp:+.3f})")
    print(f"    En AZ etkileyen 3:")
    for e, c, n in rows[-3:]:
        print(f"      {c:10} cikarilinca -> {e:+.3f}R  (delta {e-base_exp:+.3f})")
    worst = rows[0][0]
    print(f"    -> En kotu durumda bile beklenti {worst:+.3f}R "
          f"({'POZITIF kaliyor ✓' if worst > 0.2 else 'ciddi dusuyor ✗'})")

    # ── T2 YOGUNLASMA
    print("\n  T2) YOGUNLASMA — kar kac coine dagilmis?")
    per = {}
    for t in tr:
        per[t["coin"]] = per.get(t["coin"], 0.0) + t["R"]
    tot = sum(per.values())
    top = sorted(per.values(), reverse=True)
    if tot > 0:
        print(f"    Toplam {tot:+.1f}R. En iyi 1 coin: %{top[0]/tot*100:.0f}  "
              f"en iyi 3: %{sum(top[:3])/tot*100:.0f}  en iyi 5: %{sum(top[:5])/tot*100:.0f}")
        pos_coins = sum(1 for v in per.values() if v > 0)
        print(f"    Kar eden coin: {pos_coins}/{len(per)}  "
              f"({'genis tabanli ✓' if pos_coins >= len(per)*0.55 else 'dar taban ✗'})")

    # ── T3 RASTGELE ALT-KUMELER
    print("\n  T3) RASTGELE ALT-KUMELER — 30'dan rastgele 15 coin, 500 kez")
    rng = np.random.default_rng(7)
    exps = []
    for _ in range(500):
        sub = set(rng.choice(coins, size=min(15, len(coins)), replace=False))
        e, n = exp_of([t for t in tr if t["coin"] in sub])
        if n >= 10:
            exps.append(e)
    if exps:
        exps = np.array(exps)
        print(f"    beklenti dagilimi: medyan {np.median(exps):+.3f}R  "
              f"5%-95%: [{np.percentile(exps,5):+.3f}, {np.percentile(exps,95):+.3f}]")
        print(f"    pozitif cikan alt-kume orani: %{(exps>0).mean()*100:.0f}  "
              f"({'evren secimine DAYANIKLI ✓' if (exps>0).mean()>0.9 else 'evrene DUYARLI ✗'})")

    # ── T4 ALTERNATIF EVREN
    print("\n  T4) ALTERNATIF EVREN — hic kullanmadigimiz diger coinler tek basina")
    all_tr, loaded = collect_all_trades(XL)
    other = [t for t in all_tr if t["coin"] not in set(WIDE)]
    e_o, n_o = exp_of(other)
    print(f"    {len(set(t['coin'] for t in other))} farkli coin, {n_o} islem -> {e_o:+.3f}R")
    print(f"    ({'bu evren de calisiyor' if e_o > 0.2 else 'bu evren CALISMIYOR -> likidite onemli'})")

    # ── T5 COIN-BOOTSTRAP
    print("\n  T5) COIN-BOOTSTRAP — coinleri yeniden ornekle (evren belirsizligi)")
    boots = []
    for _ in range(2000):
        pick = rng.choice(coins, size=len(coins), replace=True)
        bag = []
        for c in pick:
            bag += [t for t in tr if t["coin"] == c]
        if bag:
            boots.append(float(np.mean([t["R"] for t in bag])))
    boots = np.array(boots)
    print(f"    beklenti %90 guven araligi: [{np.percentile(boots,5):+.3f}R, "
          f"{np.percentile(boots,95):+.3f}R]")
    print(f"    P(beklenti>0) = %{(boots>0).mean()*100:.1f}")

    print("\n" + "=" * 88)
    print("  YORUM: T1'de cikarma dayaniyorsa + T2 genis tabanliysa + T3'un cogu pozitifse")
    print("  -> edge EVRENDEN BAGIMSIZ, bizim 30 tesaduf degil. Aksi halde sansliyiz demektir.")
    print("  NOT: 'daha iyi 30' ARAMAK overfit olurdu; burada sadece SAGLAMLIK olctuk.")


if __name__ == "__main__":
    main()
