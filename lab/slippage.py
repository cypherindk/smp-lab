"""
lab/slippage.py — GERCEK ICRA MALIYETI (hesap/API-key GEREKMEZ).

Testnet'in bize verecegi asil bilgi: "backtest %23 diyor, gercek icra ne goturuyor?"
Bunu Binance'in PUBLIC order book (depth) verisiyle hesap acmadan olcebiliriz:
  * gercek spread (bid/ask)
  * bizim POZISYON BUYUKLUGUMUZ order book'ta yurudugunde olusan market impact
  * toplam round-trip maliyet vs backtest'te varsaydigimiz 10bps

Pozisyon buyuklugu = RISK / stop-mesafesi (canli sistemle ayni mantik).
Farkli sermaye seviyeleri icin ($100 / $1k / $10k / $100k) ayri ayri olculur —
"ne zamana kadar likidite sorun degil" sorusunun cevabi.
"""
import os
import sys
import time
import requests
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from data.crypto_fetcher import to_binance_symbol, _BASES
from lab.breadth_wide import WIDE

RISK_PCT = 0.03
BACKTEST_ASSUMED_BPS = 10.0     # backtest'te varsaydigimiz round-trip maliyet
EQUITIES = [100, 1_000, 10_000, 100_000]


def depth(symbol, limit=1000):
    for base in _BASES:
        try:
            r = requests.get(base + "/api/v3/depth",
                             params={"symbol": symbol, "limit": limit}, timeout=15)
            if r.status_code == 200:
                d = r.json()
                bids = np.array([[float(p), float(q)] for p, q in d["bids"]])
                asks = np.array([[float(p), float(q)] for p, q in d["asks"]])
                return bids, asks
        except Exception:
            pass
    return None, None


def walk(book, usd):
    """Emri order book'ta yurut -> ortalama fill fiyati. book: [[fiyat, miktar], ...]"""
    need, cost, got = usd, 0.0, 0.0
    for px, qty in book:
        lvl = px * qty
        take = min(need, lvl)
        cost += take
        got += take / px
        need -= take
        if need <= 0:
            break
    if need > 0 or got <= 0:
        return None                      # kitap yetmedi
    return cost / got


def measure(coin, eq):
    sym = to_binance_symbol(coin)
    bids, asks = depth(sym)
    if bids is None or len(asks) == 0:
        return None
    best_bid, best_ask = bids[0][0], asks[0][0]
    mid = (best_bid + best_ask) / 2
    spread_bps = (best_ask - best_bid) / mid * 1e4
    # canli sistemle ayni boyutlandirma: stop ~%5 varsayimi (ADR tipik)
    stop_pct = 0.05
    usd = (RISK_PCT * eq) / stop_pct
    buy_fill = walk(asks, usd)
    sell_fill = walk(bids, usd)
    if buy_fill is None or sell_fill is None:
        return dict(coin=coin, spread=spread_bps, usd=usd, impact=None, total=None)
    # market impact: fill'in mid'den sapmasi (tek yon)
    imp_buy = (buy_fill - mid) / mid * 1e4
    imp_sell = (mid - sell_fill) / mid * 1e4
    total = imp_buy + imp_sell            # round-trip (giris+cikis)
    return dict(coin=coin, spread=spread_bps, usd=usd,
                impact=(imp_buy + imp_sell) / 2, total=total)


def main():
    print("=" * 92)
    print("  GERCEK ICRA MALIYETI — canli order book (hesap/API-key gerekmez)")
    print("=" * 92)
    print(f"  Pozisyon = (%{RISK_PCT*100:g} risk x sermaye) / %5 stop  |  "
          f"backtest varsayimi: {BACKTEST_ASSUMED_BPS:.0f} bps round-trip\n", flush=True)

    for eq in EQUITIES:
        rows, fails = [], 0
        for coin in WIDE:
            try:
                r = measure(coin, eq)
                if r is None:
                    fails += 1; continue
                rows.append(r)
                time.sleep(0.05)
            except Exception:
                fails += 1
        ok = [r for r in rows if r["total"] is not None]
        if not ok:
            print(f"  ${eq:,}: olculemedi"); continue
        tot = np.array([r["total"] for r in ok])
        spr = np.array([r["spread"] for r in ok])
        pos = ok[0]["usd"]
        worst = sorted(ok, key=lambda x: -x["total"])[:3]
        drag = tot.mean() - BACKTEST_ASSUMED_BPS
        print(f"  SERMAYE ${eq:>7,}  (pozisyon ~${pos:,.0f})")
        print(f"    spread    : ort {spr.mean():5.1f} bps   medyan {np.median(spr):5.1f}")
        print(f"    round-trip: ort {tot.mean():5.1f} bps   medyan {np.median(tot):5.1f}   "
              f"en kotu {tot.max():5.1f}")
        print(f"    backtest varsayimina gore: {drag:+5.1f} bps "
              f"({'ILAVE MALIYET' if drag > 0 else 'varsayim MUHAFAZAKAR — iyi'})")
        print(f"    en pahali 3: " + ", ".join(f"{r['coin'].replace('-USD','')} {r['total']:.0f}bps"
                                               for r in worst))
        # yillik etki: ~22 islem/yil (dogrulanmis frekans)
        ann = (tot.mean() - BACKTEST_ASSUMED_BPS) / 1e4 * 22 * (RISK_PCT / 0.05) * 100
        print(f"    -> yillik getiriye tahmini etki: {-ann:+.2f} puan "
              f"(~22 islem/yil)\n", flush=True)

    print("  OKUMA: fark kucukse (<5 bps) backtest maliyet varsayimimiz gercekci,")
    print("  %23 CAGR tahmini ayakta. Buyuk sermayede impact artar -> kapasite siniri.")


if __name__ == "__main__":
    main()
