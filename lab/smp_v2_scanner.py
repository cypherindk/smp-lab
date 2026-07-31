"""
lab/smp_v2_scanner.py — SMP v2 OPERASYONEL TARAYICI (lab).
Ogrenilen her sey: 30-coin genis evren + SMP A+ + ER>0.15 kalite filtresi.
Her coin icin son 2 barda (4H) aktif sinyal var mi bakar; varsa giris/SL/TP/ER/
skoru gosterir. "Sistem canlida nasil calisacak"in lab prototipi. Canliya
DOKUNMAZ; GitHub Actions'ta (Binance acik) gercek veriyle kosar.
"""
import os
import sys
from datetime import timezone, timedelta
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.crypto_fetcher import fetch_binance_ohlcv
from engine.indicators import compute_all_indicators
from engine.signals import calc_bull_bear_score, calc_triggers, generate_signals
from engine.filters import apply_all_filters

IST = timezone(timedelta(hours=3))
ER_MIN = 0.15
DAYS = 400   # scanner icin yeterli (EMA200 + son sinyaller); backtest ayri

UNIVERSE = {c: (1.5, 2.0) for c in [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD",
    "AVAX-USD", "LINK-USD", "DOT-USD", "LTC-USD", "TRX-USD", "ATOM-USD", "UNI-USD",
    "ETC-USD", "XLM-USD", "NEAR-USD", "FIL-USD", "APT-USD", "ARB-USD", "OP-USD",
    "INJ-USD", "SUI-USD", "HBAR-USD", "AAVE-USD", "RUNE-USD", "ALGO-USD",
    "ICP-USD", "VET-USD", "SAND-USD"]}
UNIVERSE["ETH-USD"] = (2.8, 3.5)
UNIVERSE["SOL-USD"] = (1.9, 1.8)


def efficiency_ratio(close, n=20):
    ch = (close - close.shift(n)).abs()
    path = close.diff().abs().rolling(n).sum()
    return (ch / path.replace(0, np.nan)).fillna(0.0)


def scan_coin(coin, df, adr_mult, rr):
    ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=240, adr_mult=adr_mult)
    sc = calc_bull_bear_score(ind, mtf=None)
    tr = calc_triggers(ind, sc)
    sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                          min_conf=2, grade_filter="A+ Only")
    fs = apply_all_filters(ind, sg, use_cvd=True)
    er = efficiency_ratio(df["close"], 20)
    gate = er > ER_MIN
    buy = fs["buy_signal"] & gate
    sell = fs["sell_signal"] & gate
    for i in (-1, -2):                                    # son 2 bar (4H tarama)
        if bool(buy.iloc[i]) or bool(sell.iloc[i]):
            side = "LONG" if bool(buy.iloc[i]) else "SHORT"
            entry = float(df["close"].iloc[i])
            sp = float(ind["safe_stop_pct"].iloc[i]) / 100.0
            sl = entry * (1 - sp) if side == "LONG" else entry * (1 + sp)
            tp = entry * (1 + sp * rr) if side == "LONG" else entry * (1 - sp * rr)
            score = float((sg["total_bull_score"] if side == "LONG" else sg["total_bear_score"]).iloc[i])
            return dict(coin=coin.replace("-USD", ""), side=side, entry=entry, sl=sl, tp=tp,
                        sp=sp * 100, rr=rr, er=float(er.iloc[i]), score=score,
                        bar=df.index[i]), float(er.iloc[-1])
    return None, float(er.iloc[-1])


def main():
    print(f"{'='*80}\n  SMP v2 SCANNER — {len(UNIVERSE)} coin, 4H, SMP A+ + ER>{ER_MIN}\n{'='*80}", flush=True)
    active, regime, last_bar = [], {}, None
    for c, (adr, rr) in UNIVERSE.items():
        try:
            df = fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True)
            if len(df) < 250:
                continue
            sig, er_now = scan_coin(c, df, adr, rr)
            regime[c.replace("-USD", "")] = er_now
            last_bar = df.index[-1]
            if sig:
                active.append(sig)
        except Exception as e:
            print(f"  atla {c}: {repr(e)[:40]}", flush=True)

    if last_bar is not None:
        ist = last_bar.tz_convert(IST) if last_bar.tzinfo else last_bar
        print(f"\nSon kapali/aktif bar: {last_bar}  (TSİ {ist.strftime('%d.%m %H:%M')})\n", flush=True)

    if active:
        print(f"🟢 AKTIF SINYALLER ({len(active)}):", flush=True)
        for s in sorted(active, key=lambda x: -x["score"]):
            arrow = "📈" if s["side"] == "LONG" else "📉"
            print(f"  {arrow} {s['coin']:6} {s['side']:5} | giris {s['entry']:.4g} | "
                  f"SL {s['sl']:.4g} (-{s['sp']:.1f}%) | TP {s['tp']:.4g} (+{s['sp']*s['rr']:.1f}%) | "
                  f"R:R 1:{s['rr']:.1f} | ER {s['er']:.2f} | skor {s['score']:.1f}", flush=True)
    else:
        print("Aktif sinyal yok (bu tarama).", flush=True)

    trending = sum(1 for v in regime.values() if v > ER_MIN)
    print(f"\nRejim: {trending}/{len(regime)} coin ER>{ER_MIN} (islem yapilabilir rejim).", flush=True)
    print("Coin ER: " + "  ".join(f"{k}:{v:.2f}" for k, v in sorted(regime.items(), key=lambda x: -x[1])[:12]) + " ...", flush=True)


if __name__ == "__main__":
    main()
