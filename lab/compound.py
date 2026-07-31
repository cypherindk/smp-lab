"""
lab/compound.py — BILESIK GETIRI (compounding) motoru, SMP v2 edge'i uzerine.
Her islemi GUNCEL sermayenin %'si kadar riskle boyutlandirir -> kazanclar
biresiklenir. Eszamanli pozisyon destegi (senin "parayi bol" fikrin). Bu,
ileride OTO-TRADER'in kullanacagi sizing/risk katmaninin ta kendisi.

$100'den basla, SMP v2 (30 coin + A+ + ER>0.15) islemlerini KRONOLOJIK isle,
farkli risk% + eszamanlilik ayarlarinda equity buyumesini goster. Sadece LAB.
DURUST: gecmis performans; canlida slippage/icra/rejim farki olur.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.crypto_fetcher import fetch_binance_ohlcv
from lab.breadth_wide import WIDE, DAYS, efficiency_ratio, base_signals, gated
from lab.backtest_smp import backtest


def collect_trades():
    out = []
    print("Islem toplaniyor (30 coin, SMP A+ + ER>0.15):", flush=True)
    for c in WIDE:
        try:
            df = fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True)
            if len(df) < 300:
                continue
            ind, fs = base_signals(df, WIDE[c][0])
            fs = gated(fs, efficiency_ratio(df["close"], 20) > 0.15)
            t = backtest(df, ind, fs, WIDE[c][1])
            for _, r in t.iterrows():
                out.append({"entry": r["entry_time"], "exit": r["exit_time"], "R": float(r["R"])})
        except Exception as e:
            print(f"  atla {c}: {repr(e)[:40]}", flush=True)
    print(f"  toplam {len(out)} islem\n", flush=True)
    return out


def compound_sim(trades, start=100.0, risk_pct=0.01, max_conc=5):
    """Kronolojik, eszamanli, fixed-fractional. Kapasite doluysa yeni sinyal atlanir."""
    ev = []
    for k, t in enumerate(trades):
        ev.append((t["entry"], 1, k))   # open
        ev.append((t["exit"], 0, k))    # close
    ev.sort(key=lambda x: (x[0], x[1]))  # ayni an: once kapat (0), sonra ac (1)
    eq, peak, maxdd, taken = start, start, 0.0, 0
    open_risk = {}
    for _, typ, k in ev:
        if typ == 0:                     # kapanis
            if k in open_risk:
                eq += trades[k]["R"] * open_risk.pop(k)
                peak = max(peak, eq)
                maxdd = min(maxdd, eq / peak - 1)
        else:                            # acilis
            if len(open_risk) < max_conc and eq > 0:
                open_risk[k] = risk_pct * eq
                taken += 1
    return eq, maxdd * 100, taken


def main():
    trades = collect_trades()
    trades = [t for t in trades if pd.notna(t["entry"]) and pd.notna(t["exit"])]
    trades.sort(key=lambda x: x["entry"])
    if not trades:
        print("Islem yok."); return
    yrs = (max(t["exit"] for t in trades) - min(t["entry"] for t in trades)).days / 365.25

    print("=" * 92)
    print(f"  BILESIK GETIRI — $100 baslangic, {len(trades)} islem, {yrs*12:.0f} ay (SMP v2)")
    print("=" * 92)
    print("  (5 eszamanli pozisyon sabit; SADECE risk% degisiyor. ~%3 stop -> kaldirac ≈ risk%/3)")
    print(f"{'Ayar (risk% ~ kaldirac)':34} | {'son $':>10} {'toplam%':>9} {'CAGR':>7} {'MaxDD':>7}")
    print("-" * 92)
    for label, rp in [
        ("%1 risk  (~0.3x kaldirac)", 0.01),
        ("%2 risk  (~0.7x)", 0.02),
        ("%3 risk  (~1x)", 0.03),
        ("%5 risk  (~1.7x)", 0.05),
        ("%9 risk  (~3x kaldirac)", 0.09),
        ("%15 risk (~5x kaldirac)", 0.15),
        ("%25 risk (~8x)", 0.25),
    ]:
        final, mdd, taken = compound_sim(trades, 100.0, rp, 5)
        cagr = (final / 100.0) ** (1 / yrs) - 1 if final > 0 and yrs > 0 else -1
        ruin = "  <- RUIN yakini!" if mdd < -50 else ("  <- tehlikeli" if mdd < -30 else "")
        print(f"{label:34} | {final:10.2f} {(final/100-1)*100:+8.1f}% {cagr*100:6.1f}% {mdd:6.1f}%{ruin}")
    print("\n  NOT: kaldirac = daha yuksek risk% (sihir degil). Risk% arttikca getiri de")
    print("       DRAWDOWN da artar; bir yerden sonra risk-of-ruin. Gecmis performans;")
    print("       canlida slippage/icra bunu DUSURUR. Oto-trader sizing katmaninin prototipi.")


if __name__ == "__main__":
    main()
