"""
lab/rotation_oos.py — #4: "buyuk havuzdan en-iyi-ER sec" fikri OOS'ta ayakta mi?
Islemleri kronolojik BOL (ilk %60 IS / son %40 OOS); her yarida 30-coin vs 60-coin
rotasyonu + yeni-coin edge'ini olc. 60-coin avantaji SADECE IS'te varsa = in-sample
sans (reddet). Her iki yarida da varsa = gercek (tut). Actions/LAB.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lab.rotation import collect_all_trades, rotate_sim, metrics, avgR, XL, RISK_PCT
from lab.breadth_wide import WIDE

ORIG = set(WIDE)


def split_by_time(trades, frac=0.6):
    ts = sorted(t["entry"] for t in trades)
    cut = ts[int(len(ts) * frac)]
    return [t for t in trades if t["entry"] < cut], [t for t in trades if t["entry"] >= cut], cut


def report(trades):
    t30 = [t for t in trades if t["coin"] in ORIG]
    tNew = [t for t in trades if t["coin"] not in ORIG]
    r30, n30 = avgR(t30); rNew, nNew = avgR(tNew)
    print(f"    edge: eski30 {r30:+.3f}R ({n30}i)   yeni {rNew:+.3f}R ({nNew}i)", flush=True)
    out = {}
    for label, tr in [("30c", t30), ("60c", trades)]:
        if len(tr) < 5:
            print(f"    {label}: yetersiz islem ({len(tr)})", flush=True); continue
        curve, taken, skip, util = rotate_sim(tr, 100.0, RISK_PCT, 5)
        m = metrics(curve)
        out[label] = m
        print(f"    {label:4} | CAGR {m['cagr']:6.1f}%  DD {m['maxdd']:6.1f}%  Sharpe {m['sharpe']:5.2f}  "
              f"(aldi {taken}/{taken+skip})", flush=True)
    return out


def main():
    print("=" * 84, flush=True)
    print("  #4 OOS TESTI — 'buyuk havuzdan en-iyi-ER sec' fikri OOS'ta ayakta mi?", flush=True)
    print("=" * 84, flush=True)
    print(f"  Islem toplaniyor ({len(XL)} coin)...", flush=True)
    trades, loaded = collect_all_trades(XL)
    IS, OOS, cut = split_by_time(trades, 0.6)
    print(f"  {len(loaded)} coin, {len(trades)} islem. Bolme: IS {len(IS)}i / OOS {len(OOS)}i (kesim {str(cut)[:10]})\n", flush=True)

    print("  IN-SAMPLE (ilk %60):", flush=True)
    is_r = report(IS)
    print("\n  OUT-OF-SAMPLE (son %40):", flush=True)
    oos_r = report(OOS)

    print("\n  VERDICT:", flush=True)
    if "30c" in oos_r and "60c" in oos_r:
        d = oos_r["60c"]["sharpe"] - oos_r["30c"]["sharpe"]
        if d > 0.1:
            print(f"    OOS'ta 60c Sharpe > 30c ({oos_r['60c']['sharpe']:.2f} vs {oos_r['30c']['sharpe']:.2f}) "
                  f"-> secim GERCEK olabilir (yine de kucuk orneklem).", flush=True)
        else:
            print(f"    OOS'ta 60c avantaji YOK ({oos_r['60c']['sharpe']:.2f} vs {oos_r['30c']['sharpe']:.2f}) "
                  f"-> IS'teki iyilesme IN-SAMPLE SANS. Likit 30'da kal.", flush=True)
    else:
        print("    OOS orneklemi cok kucuk -> guvenilir yargi yok; ihtiyatla likit 30'da kal.", flush=True)
    print("\n  NOT: 66 islemi ikiye bolunce her yari kucuk -> yonlu kanit, kesin degil.", flush=True)


if __name__ == "__main__":
    main()
