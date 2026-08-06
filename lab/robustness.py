"""
lab/robustness.py — SISTEM NE KADAR SAGLAM? Overfit'e karsi iki DURUST test.
Ikisi de YENI PARAMETRE ICERMEZ (mevcut 37 islemi kullanir) -> overfit-dayanikli.

  1) DEFLATED SHARPE / PSR / MinTRL (Bailey & Lopez de Prado)
     "Edge gercek mi, yoksa onlarca konfig deneyip sansli mi ciktik?"
     - PSR   : gozlenen Sharpe'in true>0 olma olasiligi (skew/kurtoz + orneklem duzeltmeli)
     - MinTRL: %95 guven icin GEREKEN islem sayisi  (bizde 37 var -> yetiyor mu?)
     - DSR   : deneme sayisina gore DEFLATE edilmis Sharpe olasiligi

  2) MONTE CARLO BOOTSTRAP
     37 islemi binlerce kez yeniden ornekle (with replacement), bilesik boyutlandir
     -> sonuc dagilimi (5/25/50/75/95 persentil), zarar olasiligi, risk-of-ruin.

Sadece numpy/pandas (scipy YOK — normal dagilimi elle). Actions'ta kosar. Sadece LAB.
"""
import os
import sys
import math
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "live"))
from validate import collect_smp_trades


# --------------------------------------------------- normal dagilim (scipy'siz)
def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_ppf(p):
    """Acklam ters-normal CDF yaklasimi (yeterince hassas)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= ph:
        q = p - 0.5; r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def moments(r):
    r = np.asarray(r, float); m = r.mean(); s0 = r.std(ddof=0)
    sk = ((r - m) ** 3).mean() / s0 ** 3
    ku = ((r - m) ** 4).mean() / s0 ** 4          # non-excess (normal=3)
    return m, r.std(ddof=1), sk, ku


# --------------------------------------------------- 1) Deflated Sharpe
def psr(sr, n, sk, ku, sr0=0.0):
    return norm_cdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(max(1 - sk*sr + (ku-1)/4*sr*sr, 1e-9)))


def min_trl(sr, sk, ku, sr0=0.0, conf=0.95):
    z = norm_ppf(conf)
    return 1 + (1 - sk*sr + (ku-1)/4*sr*sr) * (z / (sr - sr0)) ** 2


def exp_max_sr(nt, var):
    g = 0.5772156649
    return math.sqrt(var) * ((1 - g) * norm_ppf(1 - 1.0/nt) + g * norm_ppf(1 - 1.0/(nt*math.e)))


def deflated_sharpe(R, tpy):
    mean, sd, sk, ku = moments(R)
    n = len(R); sr = mean / sd                     # islem-basi Sharpe
    sr_ann = sr * math.sqrt(tpy)
    print("=" * 78)
    print("  1) DEFLATED SHARPE / PSR / MinTRL  —  'edge gercek mi?'")
    print("=" * 78)
    print(f"  islem: {n}  |  ortalama R: {mean:+.3f}  |  islem-basi Sharpe: {sr:.3f}  "
          f"(yillik ~{sr_ann:.2f})")
    print(f"  skew: {sk:+.2f}   kurtoz: {ku:.2f} (normal=3)")
    print(f"  PSR (true Sharpe>0 olasiligi):        {psr(sr,n,sk,ku,0.0)*100:5.1f}%")
    mtrl = min_trl(sr, sk, ku, 0.0, 0.95)
    verdict = "YETERLI ✓" if mtrl <= n else "YETERSIZ — daha cok islem lazim"
    print(f"  MinTRL (%95 guven icin gereken islem): {mtrl:5.0f}  (bizde {n}) -> {verdict}")
    var_sr = (1 - sk*sr + (ku-1)/4*sr*sr) / (n - 1)     # SR-tahmin varyansi (trial proxy)
    print(f"\n  DSR — kac konfig denedigimizi hesaba katinca (deneme -> beklenen max-Sharpe deflate):")
    print(f"  {'deneme':>8} | {'beklenen max SR':>16} | {'Deflated Sharpe olasiligi':>26}")
    for nt in [5, 15, 30, 60, 100]:
        srstar = exp_max_sr(nt, var_sr)
        print(f"  {nt:8d} | {srstar:16.3f} | {psr(sr,n,sk,ku,srstar)*100:24.1f}%")
    print("  (>%95 = deneme sayisina ragmen edge saglam; <%90 = temkinli ol)")


# --------------------------------------------------- 2) Monte Carlo bootstrap
def mc_bootstrap(R, horizon, risk, sims=20000, start=100.0, seed=7):
    rng = np.random.default_rng(seed)
    R = np.asarray(R, float)
    finals = np.empty(sims); dds = np.empty(sims)
    for i in range(sims):
        seq = rng.choice(R, size=horizon, replace=True)
        eq = start; peak = start; mdd = 0.0
        for r in seq:
            eq *= (1 + risk * r)                    # fixed-fractional bilesik
            if eq <= 0:
                eq = 1e-9
            peak = max(peak, eq); mdd = min(mdd, eq/peak - 1)
        finals[i] = eq; dds[i] = mdd
    return finals, dds


def mc_block(R, tpy):
    horizon = max(int(round(tpy)), 10)              # ~1 yillik islem sayisi
    print("\n" + "=" * 78)
    print(f"  2) MONTE CARLO BOOTSTRAP  —  1 yillik ({horizon} islem) sonuc dagilimi, 20k sim")
    print("=" * 78)
    print(f"  {'risk/islem':>10} | {'medyan $':>9} {'5-95% araligi':>18} {'medyan DD':>10} "
          f"{'P(zarar)':>9} {'P(DD<-30%)':>11}")
    for risk in [0.03, 0.06]:                        # 1x, 2x
        f, d = mc_bootstrap(R, horizon, risk)
        p5, p50, p95 = np.percentile(f, [5, 50, 95])
        print(f"  {'%'+str(int(risk*100)):>10} | {p50:9.2f} {('$'+format(p5,'.0f')+'-'+format(p95,'.0f')):>18} "
              f"{np.median(d)*100:9.1f}% {(f<100).mean()*100:8.1f}% {(d<-0.30).mean()*100:10.1f}%")
    print("  (100$ -> 1 yil sonrasi. Genis 5-95% araligi = kucuk orneklem belirsizligi = durust.)")


def main():
    print("Islem toplaniyor (30 coin, SMP no-RSI A+ ER>0.15)...", flush=True)
    trades = collect_smp_trades()
    R = [t["R"] for t in trades]
    span_yrs = (max(t["exit"] for t in trades) - min(t["entry"] for t in trades)).days / 365.25
    tpy = len(R) / span_yrs if span_yrs > 0 else len(R)
    print(f"  {len(R)} islem, ~{span_yrs*12:.0f} ay, ~{tpy:.0f} islem/yil\n", flush=True)
    deflated_sharpe(R, tpy)
    mc_block(R, tpy)
    print("\n  NOT: her iki test de mevcut 37 islemi kullanir, YENI parametre yok -> overfit-dayanikli.")
    print("       Kucuk orneklem (37) genis belirsizlik verir; islem biriktikce daralir.")


if __name__ == "__main__":
    main()
