"""
lab/breadth_wide.py — GENIS EVREN breadth testi (GitHub Actions'ta kosar, Binance
acik). Top-30 likit coin: SMP A+ baseline (filtresiz, cok sinyal) vs ER>0.15
(az-ama-kaliteli). Sinyal frekansi (aylik) + kalite + kac coin sinyal verdi.
"az coin cok sinyal" mi "cok coin iyi sinyal" mi -> data karar versin.
"""
import os
import sys
import requests
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.crypto_fetcher import fetch_binance_ohlcv
from engine.indicators import compute_all_indicators
from engine.signals import calc_bull_bear_score, calc_triggers, generate_signals
from engine.filters import apply_all_filters
from lab.backtest_smp import backtest, metrics

DAYS = 600
# top-30 likit. BTC/ETH/SOL coin-ozel adr/rr; gerisi 1.5/2.0.
WIDE = {c: (1.5, 2.0) for c in [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD",
    "AVAX-USD", "LINK-USD", "DOT-USD", "LTC-USD", "TRX-USD", "ATOM-USD", "UNI-USD",
    "ETC-USD", "XLM-USD", "NEAR-USD", "FIL-USD", "APT-USD", "ARB-USD", "OP-USD",
    "INJ-USD", "SUI-USD", "HBAR-USD", "AAVE-USD", "RUNE-USD", "ALGO-USD",
    "ICP-USD", "VET-USD", "SAND-USD"]}
WIDE["ETH-USD"] = (2.8, 3.5)
WIDE["SOL-USD"] = (1.9, 1.8)


def efficiency_ratio(close, n=20):
    change = (close - close.shift(n)).abs()
    path = close.diff().abs().rolling(n).sum()
    return (change / path.replace(0, np.nan)).fillna(0.0)


def base_signals(df, adr_mult):
    ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=240, adr_mult=adr_mult)
    sc = calc_bull_bear_score(ind, mtf=None)
    tr = calc_triggers(ind, sc)
    sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                          min_conf=2, grade_filter="A+ Only")
    return ind, apply_all_filters(ind, sg, use_cvd=True)


def gated(fs, g):
    out = fs.copy()
    gb = g.reindex(fs.index).fillna(False).astype(bool)
    out["buy_signal"] = fs["buy_signal"] & gb
    out["sell_signal"] = fs["sell_signal"] & gb
    return out


def run(dfs, sigs, use_er):
    T, ncoin_sig = [], 0
    for c, df in dfs.items():
        ind, fs = sigs[c]
        if use_er:
            fs = gated(fs, efficiency_ratio(df["close"], 20) > 0.15)
        t = backtest(df, ind, fs, WIDE[c][1])
        if len(t) > 0:
            ncoin_sig += 1
        T.append(t)
    pool = pd.concat(T, ignore_index=True).sort_values("entry_time")
    return metrics(pool), metrics(pool.iloc[int(len(pool) * 0.6):]), ncoin_sig


def probe():
    print("=== ENDPOINT PROBE — Actions'tan hangi borsa acik? ===", flush=True)
    for name, url in [
        ("binance.vision", "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=2"),
        ("binance.com", "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=2"),
        ("kraken", "https://api.kraken.com/0/public/Time"),
        ("coinbase", "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=14400"),
    ]:
        try:
            r = requests.get(url, timeout=15)
            print(f"  {name:16} {r.status_code}", flush=True)
        except Exception as e:
            print(f"  {name:16} ERR {type(e).__name__}", flush=True)
    print("=" * 55, flush=True)


def main():
    probe()
    dfs, sigs = {}, {}
    print("Coin yukleme (4H, Binance):", flush=True)
    for c in WIDE:
        try:
            d = fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True)
            if len(d) < 300:
                print(f"  atla {c}: kisa gecmis ({len(d)})"); continue
            dfs[c] = d
            sigs[c] = base_signals(d, WIDE[c][0])
            print(f"  ok {c} ({len(d)} bar)", flush=True)
        except Exception as e:
            print(f"  atla {c}: {repr(e)[:40]}", flush=True)
    n = len(dfs)
    months = (next(iter(dfs.values())).index.max() - next(iter(dfs.values())).index.min()).days / 30.44
    print(f"\n{'='*92}\n  GENIS BREADTH — {n} coin, {months:.0f} ay (4H, {DAYS}g, TP=hedef R:R)\n{'='*92}")
    print(f"{'Config':30} | {'toplam':>6} {'/ay':>6} {'sinyal veren coin':>17} {'win%':>6} {'beklenti':>9} {'PF':>5} {'OOS':>7}")
    print("-" * 92)
    for name, use_er in [("AZ COIN mantigi (filtresiz)", False), ("COK COIN (ER>0.15)", True)]:
        m, mo, ncs = run(dfs, sigs, use_er)
        print(f"{name:30} | {m['n']:6d} {m['n']/months:6.2f} {f'{ncs}/{n}':>17} {m['wr']:5.1f}% {m['exp']:+8.3f}R {m['pf']:5.2f} {mo['exp']:+6.2f}R", flush=True)

    # coin-coin (baseline) -> hangi coinler edge tasiyor (evren kuratorlugu icin)
    print("\n  COIN-COIN (baseline A+, en iyiden en kotuye):", flush=True)
    rows = [(c, metrics(backtest(df, sigs[c][0], sigs[c][1], WIDE[c][1]))) for c, df in dfs.items()]
    for c, mm in sorted(rows, key=lambda x: -x[1]["exp"]):
        tag = "  <- iyi" if mm["exp"] > 0.2 else ("  <- ZARAR" if mm["exp"] < -0.1 else "")
        print(f"    {c:10} {mm['n']:3d}i  win {mm['wr']:5.1f}%  {mm['exp']:+.3f}R  PF {mm['pf']:.2f}{tag}", flush=True)


if __name__ == "__main__":
    main()
