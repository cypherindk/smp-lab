"""
live/engine.py — OTO-TRADE MIMARISI cekirdegi: KONFIG + Position + Broker + sizing.

Gorev bolumu:
  BEN  -> logic / risk / sizing / state / paper-simulasyon (bu dosya + validate/executor)
  SEN  -> exchange-API + imza + key-guvenligi + gercek icra (LiveBroker'i doldur)

Rakamlar A/B/C'de dogrulandi (lab/portfolio.py): cekirdek = SMP(no-RSI)+Trend,
korelasyon +0.03, birlesik Sharpe 1.36, 1x %10/-4DD, 2x %20/-8DD. Carry HARIC (serap).
Sadece LAB — canliya dokunmaz.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
import numpy as np

# ------------------------------------------------------------------ KONFIG
RISK_PCT    = 0.03     # SMP islem-basi TABAN risk (guncel sermaye %'si). ~1x tatli nokta.
MAX_CONC    = 5        # es zamanli SMP pozisyon tavani (compound.py'de dogrulandi)
SMP_ALLOC   = 0.70     # sermaye bolusumu: SMP sleeve (ana motor)
TREND_ALLOC = 0.30     # Trend sleeve (korelasyonsuz yumusatici)
SCALE       = 1.0      # 1x baslat; canlida kanitlaninca 1.5x/2x
TREND_VOL   = 0.10     # Trend sleeve yillik vol hedefi
ER_MIN      = 0.15     # SMP 4H rejim kapisi
KILL_DAY    = -0.08    # gunluk equity -%8 -> o gun dur (kill-switch)
KILL_DD     = -0.20    # tepe-den -%20 dususte -> sistemi durdur/incele

# --- VOL-TARGET = SIGORTA (SADECE riski kisar, ASLA kaldirac eklemez) ---
# Test (validate) gosterdi: market-vol'u kaldirac gibi kullanmak Sharpe'i iyilestirmez
# (1.54->1.54, sadece DD'yi buyutur). Bu yuzden TAVAN 1.0: yuksek-BTC-vol'de riski
# KISAR (kriz korumasi), sakinde notr kalir. Sharpe'i iyilestiren strateji-getiri-vol
# versiyonu, paper bot kendi equity gecmisini biriktirince devreye alinacak.
TARGET_VOL   = 0.50    # referans yillik BTC vol; ustunde risk kisilir
VOL_MULT_LO  = 0.40    # yuksek-vol tabani: riski en fazla %60 kis
VOL_MULT_HI  = 1.00    # TAVAN=1.0: asla taban riskin uzerine cikma (kaldirac yok)


# ------------------------------------------------------------------ POZISYON
@dataclass
class Position:
    coin: str
    side: str               # LONG / SHORT
    strategy: str           # SMP / TREND
    entry: float
    qty: float              # pozitif birim; yon 'side'da
    sl: float = 0.0         # SMP icin dolu; TREND'de 0 (rejim-cikisi)
    tp: float = 0.0
    risk_dollars: float = 0.0
    entry_time: str = ""

    def signed_qty(self) -> float:
        return self.qty if self.side == "LONG" else -self.qty

    def unrealized(self, price: float) -> float:
        return self.signed_qty() * (price - self.entry)

    def r_multiple(self, price: float) -> float:
        risk = abs(self.entry - self.sl)
        if risk <= 0:
            return 0.0
        move = (price - self.entry) if self.side == "LONG" else (self.entry - price)
        return move / risk

    def to_dict(self):
        return asdict(self)


# ------------------------------------------------------------------ BROKER
class Broker(ABC):
    """Icra soyutlamasi. Manager buna kor bakar; paper<->canli tek satirda degisir."""
    @abstractmethod
    def get_equity(self, prices: dict) -> float: ...
    @abstractmethod
    def get_positions(self) -> dict: ...
    @abstractmethod
    def open(self, pos: Position) -> str: ...
    @abstractmethod
    def close(self, coin: str, price: float, reason: str): ...


class PaperBroker(Broker):
    """Fiyat-bazli hesap simulatoru. equity = base + realized + unrealized(MTM).
    Notional/margin modellemez (risk-bazli sizing); sadece P&L takip eder."""
    def __init__(self, base_cash: float, realized: float = 0.0, positions: dict | None = None):
        self.base_cash = base_cash
        self.realized = realized
        self._pos: dict[str, Position] = positions or {}

    def get_equity(self, prices: dict) -> float:
        eq = self.base_cash + self.realized
        for c, p in self._pos.items():
            eq += p.unrealized(prices.get(c, p.entry))
        return eq

    def get_positions(self) -> dict:
        return self._pos

    def open(self, pos: Position) -> str:
        self._pos[pos.coin] = pos
        return (f"OPEN {pos.strategy} {pos.side} {pos.coin} @ {pos.entry:.4g} "
                f"qty {pos.qty:.4g} risk ${pos.risk_dollars:.2f}")

    def close(self, coin: str, price: float, reason: str):
        p = self._pos.pop(coin, None)
        if not p:
            return None
        pnl = p.unrealized(price)
        self.realized += pnl
        return (p, pnl, f"CLOSE {p.strategy} {coin} @ {price:.4g} ({reason}) "
                        f"pnl {pnl:+.2f} [{p.r_multiple(price):+.2f}R]")


class LiveBroker(Broker):
    """CANLI icra — SEN DOLDURACAKSIN. Onerilen: Binance USD-M futures.

    TODO(sen):
      * API key/secret -> Actions Secret (asla repoya yazma). Borsada: withdraw KAPALI,
        IP-whitelist, sadece futures-trade izni.
      * imzali istek: HMAC-SHA256(query, secret), X-MBX-APIKEY header.
      * open(): SMP -> market entry + OCO (STOP_MARKET SL + TAKE_PROFIT_MARKET TP,
        reduceOnly). TREND -> market ile hedef pozisyona rebalance.
      * close(): reduceOnly market.
      * get_equity/get_positions: /fapi/v2/account, /fapi/v2/positionRisk.
      * kill-switch: gunluk -%8 / DD -%20 -> yeni giris yok, aciklari kapat.
    Ben logic/sizing/state veriyorum (Position + qty + sl/tp hazir); sen REST'e cevir.
    """
    def __init__(self, *a, **k):
        raise NotImplementedError(
            "LiveBroker: exchange entegrasyonu sana ait — bkz live/ARCHITECTURE.md")

    def get_equity(self, prices): raise NotImplementedError
    def get_positions(self): raise NotImplementedError
    def open(self, pos): raise NotImplementedError
    def close(self, coin, price, reason): raise NotImplementedError


# ------------------------------------------------------------------ SIZING
def smp_size(equity: float, entry: float, sl: float,
             risk_pct: float = RISK_PCT, scale: float = SCALE):
    """Fixed-fractional: guncel sermayenin risk_pct*scale'i kadar riske. -> (qty, risk$)."""
    risk_dollars = risk_pct * scale * equity
    per_unit = abs(entry - sl)
    if per_unit <= 0 or equity <= 0:
        return 0.0, 0.0
    return risk_dollars / per_unit, risk_dollars


def trend_size(equity: float, price: float, coin_ann_vol: float,
               alloc: float = TREND_ALLOC, tvol: float = TREND_VOL, scale: float = SCALE):
    """Vol-hedefli: trend sleeve'i yillik tvol'e olcekle. -> hedef qty."""
    if coin_ann_vol <= 0 or price <= 0 or equity <= 0:
        return 0.0
    target_notional = alloc * equity * (tvol * scale / coin_ann_vol)
    return target_notional / price


def realized_vol(close, lookback_bars: int, bars_per_year: int) -> float:
    """Yillik realized vol (bar getirilerinden). close: pd.Series."""
    r = close.pct_change().dropna()
    if len(r) < 5:
        return 0.0
    return float(r.tail(lookback_bars).std() * np.sqrt(bars_per_year))


def vol_scaled_risk(base_risk: float, market_vol: float,
                    target: float = TARGET_VOL, lo: float = VOL_MULT_LO, hi: float = VOL_MULT_HI):
    """Taban riski piyasa vol'una gore olcekle (vol yuksek->kis, dusuk->hafif artir)."""
    if market_vol <= 0:
        return base_risk
    return base_risk * max(lo, min(hi, target / market_vol))
