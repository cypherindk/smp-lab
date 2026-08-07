"""
lab/rotation.py — GENISLETILMIS EVREN + SERMAYE ROTASYONU (kullanicinin fikri).
  * Evren 30 -> ~60 likit coin (breadth artisi, Grinold: IR ~ IC*sqrt(breadth))
  * SERMAYE ROTASYONU: slot bosalinca en yuksek-ER (konviksiyon) sinyale kayar;
    daha cok coin -> daha sik sinyal -> sermaye bos durmaz (surekli calisir)
  * DURUST kontroller: edge yeni coinlerde de + mi? DD kotulesiyor mu (kripto
    korelasyonu = yogunlasma)? Sharpe tutuyor mu?
Kiyas: 30 coin vs 60 coin, ayni sizing (%3 risk, 1x). Actions/LAB.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.crypto_fetcher import fetch_binance_ohlcv
from engine.indicators import compute_all_indicators
from engine.signals import calc_bull_bear_score, calc_triggers, generate_signals
from engine.filters import apply_all_filters
from lab.breadth_wide import WIDE, efficiency_ratio, gated
from lab.backtest_smp import backtest

DAYS = 600
RISK_PCT = 0.03

# 30 mevcut + 30 ek likit (600g gecmisi olmayan/migre olanlar otomatik atlanir)
EXTRA = ["POL-USD", "IMX-USD", "GRT-USD", "LDO-USD", "STX-USD", "RENDER-USD",
         "FTM-USD", "MKR-USD", "CRV-USD", "SNX-USD", "COMP-USD", "GALA-USD",
         "AXS-USD", "CHZ-USD", "MANA-USD", "THETA-USD", "EGLD-USD", "FLOW-USD",
         "XTZ-USD", "KAVA-USD", "ZEC-USD", "DASH-USD", "EOS-USD", "NEO-USD",
         "IOTA-USD", "QNT-USD", "MINA-USD", "ROSE-USD", "1INCH-USD", "ENS-USD"]
XL = dict(WIDE)
for _c in EXTRA:
    XL[_c] = (1.5, 2.0)


def collect_all_trades(universe):
    """no-RSI + A+ + ER>0.15 (dogrulanmis cekirdek). Her islemde ER=konviksiyon."""
    out, loaded = [], []
    for c in universe:
        try:
            df = fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True)
            if len(df) < 300:
                continue
            ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=240, adr_mult=universe[c][0])
            sc = calc_bull_bear_score(ind, mtf=None, drop={"rsi"})
            tr = calc_triggers(ind, sc)
            sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                                  min_conf=2, grade_filter="A+ Only")
            fs = apply_all_filters(ind, sg, use_cvd=True)
            er = efficiency_ratio(df["close"], 20)
            fs = gated(fs, er > 0.15)
            for _, r in backtest(df, ind, fs, universe[c][1]).iterrows():
                et = pd.Timestamp(r["entry_time"])
                if pd.isna(et) or pd.isna(r["exit_time"]):
                    continue
                out.append({"coin": c, "entry": et, "exit": pd.Timestamp(r["exit_time"]),
                            "R": float(r["R"]), "conv": float(er.asof(et))})
            loaded.append(c)
        except Exception:
            pass
    return out, loaded


def rotate_sim(trades, start=100.0, risk_pct=RISK_PCT, max_conc=5, rank=True):
    """Event-driven + eszamanlilik + KONVIKSIYON siralamasi (slot bosalinca en iyi)."""
    ev = []
    for k, t in enumerate(trades):
        ev.append((t["entry"], 1, t["conv"], k))
        ev.append((t["exit"], 0, 0.0, k))
    # ayni an: once kapat(0) sonra ac(1); acilislar arasi yuksek-konviksiyon once
    ev.sort(key=lambda x: (x[0], x[1], -x[2] if rank else 0))
    eq, open_risk, taken, skipped = start, {}, 0, 0
    curve = [(min(t["entry"] for t in trades), start)]
    last_t, slot_area, span = None, 0.0, 0.0
    for ts, typ, conv, k in ev:
        if last_t is not None:
            dt = (ts - last_t).total_seconds()
            span += dt; slot_area += dt * len(open_risk)
        last_t = ts
        if typ == 0:
            if k in open_risk:
                eq += trades[k]["R"] * open_risk.pop(k)
                curve.append((ts, eq))
        else:
            if len(open_risk) < max_conc and eq > 0:
                open_risk[k] = risk_pct * eq; taken += 1
            else:
                skipped += 1
    util = (slot_area / span / max_conc * 100) if span > 0 else 0.0
    s = pd.Series({pd.Timestamp(t): v for t, v in curve})
    return s[~s.index.duplicated(keep="last")].sort_index(), taken, skipped, util


def metrics(curve, start=100.0):
    idx = pd.date_range(curve.index.min().normalize(), curve.index.max().normalize(), freq="D")
    d = curve.reindex(idx, method="ffill").fillna(start)
    ret = d.pct_change().dropna()
    cagr = (d.iloc[-1] / d.iloc[0]) ** (365 / len(d)) - 1 if len(d) > 1 else 0
    return dict(final=d.iloc[-1], cagr=cagr * 100,
                maxdd=(d / d.cummax() - 1).min() * 100,
                sharpe=ret.mean() / ret.std() * np.sqrt(365) if ret.std() > 0 else 0)


def avgR(trades):
    r = [t["R"] for t in trades]
    return (np.mean(r), len(r)) if r else (0.0, 0)


def main():
    print("=" * 88, flush=True)
    print("  GENISLETILMIS EVREN + SERMAYE ROTASYONU — 30 vs 60 coin, surekli calisan para", flush=True)
    print("=" * 88, flush=True)
    print(f"  Islem toplaniyor ({len(XL)} coin hedef, 4H)...", flush=True)
    trades, loaded = collect_all_trades(XL)
    orig = set(WIDE)
    new = [c for c in loaded if c not in orig]
    t30 = [t for t in trades if t["coin"] in orig]
    tNew = [t for t in trades if t["coin"] not in orig]
    print(f"  Yuklendi: {len(loaded)} coin ({len(orig & set(loaded))} eski + {len(new)} yeni), {len(trades)} islem\n", flush=True)

    # --- EDGE tutuyor mu? (yeni coinlerde) ---
    r30, n30 = avgR(t30); rNew, nNew = avgR(tNew)
    print(f"  EDGE KONTROLU (islem-basi ort R):", flush=True)
    print(f"    Eski 30 coin : {r30:+.3f}R  ({n30} islem)", flush=True)
    print(f"    Yeni coinler : {rNew:+.3f}R  ({nNew} islem)  -> "
          f"{'edge TUTUYOR ✓' if rNew > 0.15 else 'edge SEYRELDI/ZAYIF ✗ (illiquid)'}", flush=True)

    # --- ROTASYON KIYASI ---
    print(f"\n  {'Kurulum':22} | {'son$':>8} {'CAGR':>7} {'MaxDD':>8} {'Sharpe':>7} {'alinan':>7} {'atlanan':>8} {'kullanim':>9}", flush=True)
    print("  " + "-" * 86, flush=True)
    for label, tr, mc in [("30 coin, 5 slot", t30, 5),
                          ("60 coin, 5 slot", trades, 5),
                          ("60 coin, 8 slot", trades, 8)]:
        if not tr:
            continue
        curve, taken, skip, util = rotate_sim(tr, 100.0, RISK_PCT, mc)
        m = metrics(curve)
        print(f"  {label:22} | {m['final']:8.2f} {m['cagr']:6.1f}% {m['maxdd']:7.1f}% "
              f"{m['sharpe']:7.2f} {taken:7d} {skip:8d} {util:8.0f}%", flush=True)

    print("\n  OKUMA: 60-coin CAGR>30-coin + Sharpe tutuyor + DD cok kotulesmiyorsa breadth KAZANC.", flush=True)
    print("  DD ciddi kotulesiyor / Sharpe dusuyorsa = kripto korelasyonu (yogunlasma) devrede.", flush=True)
    print("  8 slot: daha cok sermaye calisir ama es zamanli BTC-beta maruziyeti artar (DD'ye bak).", flush=True)
    print("  Backtest/tek rejim -> canlida haircut. Geceni tut, gecmeyeni at.", flush=True)


if __name__ == "__main__":
    main()
