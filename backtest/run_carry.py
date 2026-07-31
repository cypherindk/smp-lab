"""
backtest/run_carry.py
Cash-and-carry / funding arbitraji analizi. Delta-notr: spot LONG + perp SHORT
esit buyuklukte -> fiyat riski hedge, P&L ~ toplanan funding.
Funding pozitifken perp short funding ALIR. Her 8 saatte bir odenir.

Modeller:
  passive : her zaman spot long + perp short. ret_t = funding_t (negatif olabilir).
  active  : sadece funding>0 iken pozisyonda (negatifte nakde/flat) -> ret_t=max(funding,0).
Getiri notional uzerinden (1x konuslandirilmis sermaye varsayimi).

DURUST CEKINCELER (funding verisinden GORUNMEYEN gercek riskler):
  - Basis blowout / perp short likidasyonu (ani spike'ta perp short zarar eder,
    spot kar realize olmadan margin yetersizse likide olabilir) -> kuyruk riski.
  - Borsa/karsi taraf riski, spot-perp cekilme farki (basis), giris/cikis maliyeti.
  Yani gercek risk-ayarli getiri buradaki funding-only Sharpe'in ALTINDA olur.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.funding_fetcher import fetch_binance_funding

COINS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
         "ADA-USD", "DOGE-USD", "LINK-USD"]
DAYS = 720
PPY = 3 * 365  # funding periyodu / yil (8h)


def metrics(r):
    r = r.dropna()
    if len(r) < 10:
        return dict(ann=0, sharpe=0, maxdd=0, pos=0, n=0)
    eq = (1 + r).cumprod()
    ann = eq.iloc[-1] ** (PPY / len(r)) - 1
    sharpe = r.mean() / r.std() * np.sqrt(PPY) if r.std() > 0 else 0
    maxdd = (eq / eq.cummax() - 1).min()
    return dict(ann=ann * 100, sharpe=sharpe, maxdd=maxdd * 100,
                pos=(r > 0).mean() * 100, n=len(r))


def run():
    passive, active = {}, {}
    print(f"\n{'='*80}\n  CARRY / FUNDING ARB  ({DAYS}g, 8h funding, delta-notr)\n{'='*80}")
    print(f"{'Coin':10} | {'passive: yil% Sharpe MaxDD %+':>34} | {'active(>0): yil% Sharpe':>24}")
    print("-" * 80)
    for c in COINS:
        f = fetch_binance_funding(c, days=DAYS)
        if f.empty:
            print(f"{c:10} | veri yok")
            continue
        passive[c] = f
        active[c] = f.clip(lower=0.0)
        mp, ma = metrics(f), metrics(f.clip(lower=0.0))
        print(f"{c:10} | {mp['ann']:7.2f}% {mp['sharpe']:6.2f} {mp['maxdd']:6.2f}% {mp['pos']:4.0f}%+"
              f" | {ma['ann']:7.2f}% {ma['sharpe']:6.2f}")

    # Esit-agirlik portfoy (coinler ayni 8h timestamp'lerini paylasir)
    Pp = pd.concat(passive, axis=1).mean(axis=1)
    Pa = pd.concat(active, axis=1).mean(axis=1)
    mp, ma = metrics(Pp), metrics(Pa)
    print("-" * 80)
    print(f"{'PORTFOY':10} | {mp['ann']:7.2f}% {mp['sharpe']:6.2f} {mp['maxdd']:6.2f}% {mp['pos']:4.0f}%+"
          f" | {ma['ann']:7.2f}% {ma['sharpe']:6.2f}")
    print(f"\n  Ortalama funding (yillik, passive portfoy): %{mp['ann']:.2f}")
    print(f"  Not: gercek getiri maliyet+basis+likidasyon riski ile bunun ALTINDA.")


if __name__ == "__main__":
    run()
