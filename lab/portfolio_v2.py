"""
lab/portfolio_v2.py — GELISTIRILMIS PORTFOY: oncelikli eklemeler + DURUST kiyas.
Disiplin: EKLE -> TEST ET -> gecmeyeni AT. Cekirdek = SMP(no-RSI)+Trend (dogrulandi).

  #1 Yeni sleeve: REBALANCING PREMIUM (mekanik esit-agirlik yeniden dengeleme primi,
     forecasting yok -> overfit-guvenli). Korelasyon+Sharpe testinden gecerse eklenir.
  #2 VOL-HEDEFLI overlay: birlesik getiriyi sabit yillik vol'e olcekle -> DD yumusar.
  #3 FRACTIONAL KELLY: edge'den buyume-optimal risk%; ama 37 islemde Kelly gurultuye
     asiri tepki verir -> ceyrek/yarim Kelly + DD-sweep capi. Durustce raporlanir.

Baseline (SMP+Trend) vs Enhanced (+rebal +vol-target) kiyasi. Actions/LAB.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "live"))
from data.crypto_fetcher import fetch_binance_ohlcv
from lab.portfolio import smp_daily, trend_daily, stats, _naive_day
from validate import collect_smp_trades

DAYS = 600
REBAL_COINS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
               "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "DOT-USD"]


# ------------------------------------------------ #1 Rebalancing premium sleeve
def rebal_premium_daily(rebal_days=7):
    """Esit-agirlik yeniden-dengelenen sepet getirisi - buy&hold getirisi = prim.
    Piyasa-notr'a yakin (ikisi de ayni sepette long); fark rebalancing bonusu."""
    rets = {}
    for c in REBAL_COINS:
        try:
            df = fetch_binance_ohlcv(c, interval="1d", days=DAYS, quiet=True)
            r = df["close"].pct_change()
            r.index = _naive_day(r.index)
            rets[c] = r
        except Exception:
            pass
    if len(rets) < 4:
        return pd.Series(dtype=float)
    R = pd.concat(rets, axis=1).dropna(how="all").fillna(0.0)
    n = R.shape[1]
    eq = np.ones(n) / n

    def walk(reset):
        w = eq.copy(); out = []
        for i, (ts, row) in enumerate(R.iterrows()):
            v = row.values
            out.append((ts, float((w * v).sum())))      # gunun getirisi (gun-basi agirlik)
            w = w * (1 + v)
            s = w.sum(); w = w / s if s > 0 else eq.copy()
            if reset and (i + 1) % rebal_days == 0:
                w = eq.copy()                            # yeniden dengele
        return pd.Series(dict(out))

    return (walk(True) - walk(False)).rename("Rebal")    # prim = rebalanced - buyhold


# ------------------------------------------------ #2 Vol-hedefli overlay
def vol_target(r, target=0.15, lb=30, cap=3.0):
    rv = r.rolling(lb).std() * np.sqrt(365)
    lev = (target / rv).clip(upper=cap).shift(1).fillna(1.0)
    return r * lev


# ------------------------------------------------ #3 Fractional Kelly
def kelly_stats(R):
    R = np.asarray(R, float)
    p = float((R > 0).mean())
    win = float(R[R > 0].mean()) if (R > 0).any() else 0.0
    loss = float(-R[R < 0].mean()) if (R < 0).any() else 1.0
    b = win / loss if loss > 0 else 0.0
    f = (p - (1 - p) / b) if b > 0 else 0.0              # tam Kelly (bankroll frac.)
    return dict(p=p, b=b, win=win, loss=loss, full=f, half=f/2, quarter=f/4)


# ------------------------------------------------ yardimci
def densify(series_list):
    idx = series_list[0].index
    for s in series_list[1:]:
        idx = idx.union(s.index)
    master = pd.date_range(idx.min(), idx.max(), freq="D")
    return [s.reindex(master).fillna(0.0) for s in series_list]


def inv_vol(cols, tv=0.10):
    sc = [c * (tv / (c.std() * np.sqrt(365))) if c.std() > 0 else c * 0 for c in cols]
    return sum(sc) / len(sc)


def main():
    print("=" * 82 + "\n  GELISTIRILMIS PORTFOY — oncelikli eklemeler + durust kiyas\n" + "=" * 82, flush=True)
    print("  Bacaklar hesaplaniyor (30 coin)...", flush=True)
    smp = smp_daily(drop={"rsi"})
    trend = trend_daily()
    trend.index = _naive_day(trend.index)
    rebal = rebal_premium_daily()
    smp, trend, rebal = densify([smp, trend, rebal])

    # ---- standalone ----
    print(f"\n  {'Bacak':16} | {'Sharpe':>7} {'CAGR':>8} {'MaxDD':>8}", flush=True)
    print("  " + "-" * 46, flush=True)
    for nm, r in [("SMP no-RSI", smp), ("Trend", trend), ("Rebal premium(#1)", rebal)]:
        s = stats(r)
        print(f"  {nm:16} | {s['sharpe']:7.2f} {s['cagr']:7.1f}% {s['maxdd']:7.1f}%", flush=True)

    # ---- #1 TEST: rebal gecer mi? (Sharpe>0 ve |corr|<0.35) ----
    M = pd.concat({"SMP": smp, "Trend": trend, "Rebal": rebal}, axis=1).fillna(0.0)
    corr = M.corr()
    print(f"\n  Korelasyon: SMP-Trend {corr.loc['SMP','Trend']:+.2f}  "
          f"SMP-Rebal {corr.loc['SMP','Rebal']:+.2f}  Trend-Rebal {corr.loc['Trend','Rebal']:+.2f}", flush=True)
    rs = stats(rebal)
    passes = rs["sharpe"] > 0.3 and abs(corr.loc["SMP", "Rebal"]) < 0.35 and abs(corr.loc["Trend", "Rebal"]) < 0.35
    print(f"  #1 Rebal verdict: {'GECTI ✓ eklenir' if passes else 'KALDI ✗ atilir (dusuk Sharpe/yuksek korel)'}", flush=True)

    # ---- baseline vs enhanced ----
    baseline = inv_vol([smp, trend])
    legs = [smp, trend] + ([rebal] if passes else [])
    enhanced = inv_vol(legs)
    enhanced_vt = vol_target(enhanced)                  # #2 overlay

    print(f"\n  {'Portfoy':28} | {'Sharpe':>7} {'CAGR':>8} {'MaxDD':>8}", flush=True)
    print("  " + "-" * 58, flush=True)
    for nm, r in [("Baseline (SMP+Trend)", baseline),
                  (f"Enhanced (+rebal? {'E' if passes else 'H'})", enhanced),
                  ("Enhanced + vol-target(#2)", enhanced_vt)]:
        s = stats(r)
        print(f"  {nm:28} | {s['sharpe']:7.2f} {s['cagr']:7.1f}% {s['maxdd']:7.1f}%", flush=True)

    # ---- #3 Kelly ----
    R = [t["R"] for t in collect_smp_trades()]
    k = kelly_stats(R)
    print(f"\n  #3 FRACTIONAL KELLY (SMP edge'inden):", flush=True)
    print(f"     win%={k['p']*100:.0f}  odds b={k['b']:.2f}  (ort kazanc {k['win']:.2f}R / kayip {k['loss']:.2f}R)", flush=True)
    print(f"     Tam Kelly: %{k['full']*100:.1f} risk  |  Yarim: %{k['half']*100:.1f}  |  Ceyrek: %{k['quarter']*100:.1f}", flush=True)
    print(f"     Mevcut: %3. DURUST: 37 islemde Kelly gurultuye asiri tepki verir + DD-sweep %5+'te", flush=True)
    print(f"     -%31 DD gosterdi -> Ceyrek Kelly'yi %3-4 capinda tut. Kelly 'daha buyuk bahis' diyor ama guvenlik once.", flush=True)

    print("\n  NOT: ekler TEST'ten gecerse anlamli. Backtest/tek rejim -> canlida haircut.", flush=True)


if __name__ == "__main__":
    main()
