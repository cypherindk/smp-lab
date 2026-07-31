"""
lab/carry_test.py — CARRY (funding arb), OKX funding verisiyle (Actions'ta acik).
Delta-notr: spot LONG + perp SHORT -> fiyat riski hedge, getiri ~ toplanan funding.
Funding pozitifken perp short funding ALIR. 8h.
  passive : her zaman short perp -> ret = funding (negatif olabilir)
  active  : sadece funding>0 iken -> ret = max(funding,0)
3-stratejili portfoyun KORELASYONSUZ 3. bacagi. Sadece LAB.
DURUST: funding-only; basis/likidasyon/icra riski bunu DUSURUR.
"""
import time
import requests
import numpy as np
import pandas as pd

COINS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT", "LTC"]
DAYS = 400
PPY = 3 * 365   # 8h funding periyodu / yil


def fetch_okx_funding(coin, days):
    url = "https://www.okx.com/api/v5/public/funding-rate-history"
    inst = f"{coin}-USDT-SWAP"
    end = int(time.time() * 1000)
    start = end - days * 86400 * 1000
    out, after = [], None
    while True:
        p = {"instId": inst, "limit": 100}
        if after:
            p["after"] = after
        try:
            data = requests.get(url, params=p, timeout=20).json().get("data", [])
        except Exception:
            break
        if not data:
            break
        for row in data:
            out.append((int(row["fundingTime"]), float(row["fundingRate"])))
        oldest = int(data[-1]["fundingTime"])
        if oldest <= start or len(data) < 100:
            break
        after = oldest
        time.sleep(0.1)
    out = [(t, r) for t, r in out if t >= start]
    if not out:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(t, unit="ms"): r for t, r in out}).sort_index()
    return s[~s.index.duplicated()]


def metrics(r):
    r = r.dropna()
    if len(r) < 20:
        return dict(ann=0, sharpe=0, maxdd=0, pos=0, n=len(r))
    eq = (1 + r).cumprod()
    ann = eq.iloc[-1] ** (PPY / len(r)) - 1
    sharpe = r.mean() / r.std() * np.sqrt(PPY) if r.std() > 0 else 0
    maxdd = (eq / eq.cummax() - 1).min()
    return dict(ann=ann * 100, sharpe=sharpe, maxdd=maxdd * 100,
                pos=(r > 0).mean() * 100, n=len(r))


def main():
    print(f"{'='*82}\n  CARRY / FUNDING ARB — OKX, {DAYS}g, delta-notr, 8h\n{'='*82}", flush=True)
    print(f"{'Coin':6} | {'passive: yil% Sharpe MaxDD %+':>34} | {'active(>0): yil% Sharpe':>24}", flush=True)
    print("-" * 82, flush=True)
    passive, active = {}, {}
    for c in COINS:
        f = fetch_okx_funding(c, DAYS)
        if f.empty:
            print(f"{c:6} | veri yok", flush=True)
            continue
        passive[c] = f
        active[c] = f.clip(lower=0.0)
        mp, ma = metrics(f), metrics(f.clip(lower=0.0))
        print(f"{c:6} | {mp['ann']:7.2f}% {mp['sharpe']:6.2f} {mp['maxdd']:6.2f}% {mp['pos']:4.0f}%+"
              f" | {ma['ann']:7.2f}% {ma['sharpe']:6.2f}", flush=True)

    if passive:
        Pp = pd.concat(passive, axis=1).mean(axis=1).dropna()
        Pa = pd.concat(active, axis=1).mean(axis=1).dropna()
        mp, ma = metrics(Pp), metrics(Pa)
        print("-" * 82, flush=True)
        print(f"{'PORTFOY':6} | {mp['ann']:7.2f}% {mp['sharpe']:6.2f} {mp['maxdd']:6.2f}% {mp['pos']:4.0f}%+"
              f" | {ma['ann']:7.2f}% {ma['sharpe']:6.2f}", flush=True)
        print(f"\n  Passive portfoy yillik carry: %{mp['ann']:.2f}  (Sharpe {mp['sharpe']:.2f})", flush=True)
        print("  NOT: funding-only; canlida basis/likidasyon/icra riski bunu DUSURUR.", flush=True)


if __name__ == "__main__":
    main()
