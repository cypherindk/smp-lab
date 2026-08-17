"""
live/testnet_bot.py — BINANCE FUTURES TESTNET PAPER TRADER (ccxt).

Neden testnet: kendi paper botumuz (executor.py) fill'leri TEORIK varsayar.
Testnet ise GERCEK order book + GERCEK slippage + canlida kullanacagimiz API'nin
BIREBIR AYNISI — ama sanal para. Ikisini paralel kosunca aradaki fark =
GERCEK ICRA MALIYETI (canliya gecmeden bilmemiz gereken tek eksik sayi).

Sistem: dogrulanmis cekirdek — SMP no-RSI + A+ + ER>0.15, 30 likit coin, 4H.
Boyutlandirma: RISK once (%3 x equity), pozisyon = risk$ / stop-mesafesi.
Emirler: market giris + STOP_MARKET (SL) + TAKE_PROFIT_MARKET (TP), reduceOnly.

KALDIRAC NOTU (TW'deki 10x surprizi tekrarlanmasin):
  Kaldirac = sadece MARJ BASLIGI, risk degil. Riski STOP belirler (%3).
  5 pozisyon x ~%60 notional = ~3x toplam -> LEVERAGE=5 marj icin yeterli.
  Kaldiraci artirmak pozisyonu BUYUTMEZ; sizing risk'e gore hesaplanir.

KURULUM — IKI SECENEK (hangisine erisebiliyorsan):

  A) BYBIT TESTNET (hesap gerekmez, e-posta ile kayit — ONERILEN)
       1. https://testnet.bybit.com -> e-posta ile kayit ol
       2. Profil > API > New Key (Read-Write, "API Transaction" izni)
       3. $env:TESTNET_KEY="..." ; $env:TESTNET_SECRET="..." ; $env:TESTNET_EX="bybit"

  B) BINANCE DEMO (GERCEK Binance hesabi ister — eski GitHub girisi KALDIRILDI;
     testnet.binancefuture.com artik demo.binance.com'a yonleniyor)
       1. https://demo.binance.com -> Binance hesabinla giris
       2. API Key uret (demo/testnet — gercek bakiyene DOKUNMAZ)
       3. $env:TESTNET_KEY="..." ; $env:TESTNET_SECRET="..." ; $env:TESTNET_EX="binance"

  Sonra:
     python live/testnet_bot.py --dry    (once bu — emir GONDERMEZ)
     python live/testnet_bot.py          (gercek testnet emri, sanal para)
     python live/testnet_bot.py --status
     python live/testnet_bot.py --close-all
"""
import argparse
import os
import sys
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import ccxt
from data.crypto_fetcher import fetch_binance_ohlcv
from engine.indicators import compute_all_indicators
from engine.signals import calc_bull_bear_score, calc_triggers, generate_signals
from engine.filters import apply_all_filters
from lab.breadth_wide import WIDE, efficiency_ratio, gated
from core import RISK_PCT, MAX_CONC, ER_MIN, KILL_DD, SCALE

IST = timezone(timedelta(hours=3))
LEVERAGE = 5           # sadece marj basligi (5 slot x ~%60 notional icin). Risk = stop.
DAYS = 400


def _load_env():
    """live/.env dosyasindan anahtarlari oku (gitignore'da — repoya ASLA girmez).
    Format:  ANAHTAR=deger   (tirnak gereksiz, satir basi # yorum)"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(p):
        return
    for ln in open(p, encoding="utf-8"):
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def exchange():
    """TESTNET_EX = bybit | binance. Anahtarlar .env veya ortam degiskeninden
    (ASLA kodda/repoda degil)."""
    _load_env()
    which = (os.getenv("TESTNET_EX") or "bybit").lower()
    key = os.getenv("TESTNET_KEY") or os.getenv("BINANCE_TESTNET_KEY")
    sec = os.getenv("TESTNET_SECRET") or os.getenv("BINANCE_TESTNET_SECRET")
    if not key or not sec:
        print("  ✗ TESTNET_KEY / TESTNET_SECRET tanimli degil.\n")
        print("    A) BYBIT TESTNET (hesap gerekmez, e-posta ile kayit — ONERILEN)")
        print("       https://testnet.bybit.com -> kayit -> Profil > API > New Key")
        print('       $env:TESTNET_EX="bybit"; $env:TESTNET_KEY="..."; $env:TESTNET_SECRET="..."\n')
        print("    B) BINANCE DEMO (gercek Binance hesabi ister)")
        print("       https://demo.binance.com -> giris -> API Key")
        print('       $env:TESTNET_EX="binance"; $env:TESTNET_KEY="..."; $env:TESTNET_SECRET="..."')
        return None
    cfg = {"apiKey": key, "secret": sec, "enableRateLimit": True}
    if which.startswith("bin"):
        cfg["options"] = {"defaultType": "future"}
        ex = ccxt.binanceusdm(cfg)
    else:
        cfg["options"] = {"defaultType": "swap"}
        ex = ccxt.bybit(cfg)
    ex.set_sandbox_mode(True)          # TESTNET
    ex._which = which
    try:
        ex.load_markets()
    except Exception as e:
        print(f"  ✗ Baglanti/anahtar hatasi ({which}): {repr(e)[:140]}")
        return None
    print(f"  Borsa: {which.upper()} TESTNET (sanal para)")
    return ex


def sym(coin):
    return coin.replace("-USD", "") + "/USDT:USDT"


def signal_for(coin):
    """Son KAPALI 4H barda dogrulanmis cekirdek sinyali. -> dict | None"""
    df = fetch_binance_ohlcv(coin, interval="4h", days=DAYS, quiet=True)
    if len(df) < 250:
        return None, 0.0
    ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=240,
                                 adr_mult=WIDE[coin][0])
    sc = calc_bull_bear_score(ind, mtf=None, drop={"rsi"})
    tr = calc_triggers(ind, sc)
    sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                          min_conf=2, grade_filter="A+ Only")
    fs = apply_all_filters(ind, sg, use_cvd=True)
    er = efficiency_ratio(df["close"], 20)
    fs = gated(fs, er > ER_MIN)
    i = -1
    er_now = float(er.iloc[i])
    if not (bool(fs["buy_signal"].iloc[i]) or bool(fs["sell_signal"].iloc[i])):
        return None, er_now
    side = "buy" if bool(fs["buy_signal"].iloc[i]) else "sell"
    sp = float(ind["safe_stop_pct"].iloc[i]) / 100.0
    return dict(coin=coin, side=side, stop_pct=sp, rr=WIDE[coin][1], er=er_now), er_now


def equity(ex):
    b = ex.fetch_balance()
    return float(b["total"].get("USDT", 0.0))


def positions(ex):
    out = {}
    for p in ex.fetch_positions():
        amt = float(p.get("contracts") or 0)
        if abs(amt) > 0:
            out[p["symbol"]] = p
    return out


def place(ex, s, eq, dry):
    m = sym(s["coin"])
    px = float(ex.fetch_ticker(m)["last"])
    sgn = 1 if s["side"] == "buy" else -1
    sl = px * (1 - s["stop_pct"] * sgn)
    tp = px * (1 + s["stop_pct"] * s["rr"] * sgn)
    risk_usd = RISK_PCT * SCALE * eq
    qty = risk_usd / (px * s["stop_pct"])                  # RISK ONCE
    try:
        qty = float(ex.amount_to_precision(m, qty))
        sl = float(ex.price_to_precision(m, sl))
        tp = float(ex.price_to_precision(m, tp))
    except Exception:
        pass
    notional = qty * px
    print(f"  ► {s['coin']:9} {s['side'].upper():4} @ {px:.6g} | SL {sl:.6g} "
          f"(-{s['stop_pct']*100:.1f}%) TP {tp:.6g} (+{s['stop_pct']*s['rr']*100:.1f}%) | "
          f"{qty:g} adet = ${notional:.2f} notional | risk ${risk_usd:.2f} (%{RISK_PCT*100:g}) | ER {s['er']:.2f}",
          flush=True)
    if dry:
        print("     (dry: emir gonderilmedi)"); return False
    try:
        try:
            ex.set_leverage(LEVERAGE, m)
        except Exception:
            pass
        if getattr(ex, "_which", "bybit").startswith("bin"):
            ex.create_order(m, "market", s["side"], qty)
            opp = "sell" if s["side"] == "buy" else "buy"
            ex.create_order(m, "STOP_MARKET", opp, qty, None,
                            {"stopPrice": sl, "reduceOnly": True})
            ex.create_order(m, "TAKE_PROFIT_MARKET", opp, qty, None,
                            {"stopPrice": tp, "reduceOnly": True})
        else:   # bybit: SL/TP giris emrine iliştirilir (tek cagri, daha guvenli)
            ex.create_order(m, "market", s["side"], qty, None,
                            {"stopLoss": str(sl), "takeProfit": str(tp)})
        print("     ✓ POZISYON ACILDI + SL/TP yerlesti", flush=True)
        return True
    except Exception as e:
        print(f"     ✗ HATA: {repr(e)[:160]}", flush=True)
        return False


def show_status(ex):
    eq = equity(ex)
    pos = positions(ex)
    print(f"  Testnet equity: ${eq:.2f} USDT | acik pozisyon: {len(pos)}/{MAX_CONC}")
    for m_, p in pos.items():
        pnl = float(p.get("unrealizedPnl") or 0)
        print(f"    {m_:18} {p.get('side','?'):5} {p.get('contracts')} adet "
              f"giris {p.get('entryPrice')} | P&L {pnl:+.2f} USDT")
    return eq, pos


def close_all(ex):
    pos = positions(ex)
    if not pos:
        print("  Acik pozisyon yok."); return
    for m_, p in pos.items():
        side = "sell" if p.get("side") == "long" else "buy"
        try:
            ex.create_order(m_, "market", side, abs(float(p["contracts"])), None,
                            {"reduceOnly": True})
            print(f"  ✓ kapatildi: {m_}")
        except Exception as e:
            print(f"  ✗ {m_}: {repr(e)[:100]}")
    try:
        for m_ in pos:
            ex.cancel_all_orders(m_)
    except Exception:
        pass


def cycle(dry):
    print("=" * 84)
    print(f"  BINANCE FUTURES TESTNET — {'DRY (emir YOK)' if dry else 'GERCEK testnet emri'} "
          f"| TSİ {datetime.now(IST):%d.%m %H:%M}")
    print("=" * 84)
    ex = exchange()
    if ex is None:
        return
    eq, pos = show_status(ex)
    open_syms = set(pos)
    scanned = trending = 0
    for coin in WIDE:
        try:
            s, er_now = signal_for(coin)
            scanned += 1
            trending += 1 if er_now > ER_MIN else 0
            if not s:
                continue
            if sym(coin) in open_syms:
                print(f"    {coin:9} sinyal var ama pozisyon acik"); continue
            if len(open_syms) >= MAX_CONC:
                print(f"    {coin:9} sinyal var ama slot dolu ({MAX_CONC})"); continue
            if place(ex, s, eq, dry):
                open_syms.add(sym(coin))
        except Exception as e:
            print(f"    atla {coin}: {repr(e)[:60]}")
    print(f"\n  Tarandi {scanned}/{len(WIDE)} coin | rejim: {trending} coin ER>{ER_MIN}")
    print(f"  Kaldirac {LEVERAGE}x = sadece marj basligi; RISK'i stop belirler (%{RISK_PCT*100:g}/islem).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--close-all", action="store_true")
    a = ap.parse_args()
    if a.status:
        e = exchange()
        if e:
            show_status(e)
    elif a.close_all:
        e = exchange()
        if e:
            close_all(e)
    else:
        cycle(a.dry)
