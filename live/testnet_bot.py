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

KURULUM (senin adimlarin):
  1. https://testnet.binancefuture.com -> GitHub ile giris yap
  2. API Key uret (testnet, sanal para — gercek hesabinla ALAKASI YOK)
  3. Ortam degiskeni olarak ver:
       $env:BINANCE_TESTNET_KEY="..."      (PowerShell)
       $env:BINANCE_TESTNET_SECRET="..."
  4. python live/testnet_bot.py --dry    (once bu)
     python live/testnet_bot.py          (gercek testnet emri)
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


def exchange():
    key = os.getenv("BINANCE_TESTNET_KEY")
    sec = os.getenv("BINANCE_TESTNET_SECRET")
    if not key or not sec:
        print("  ✗ BINANCE_TESTNET_KEY / BINANCE_TESTNET_SECRET tanimli degil.")
        print("    testnet.binancefuture.com -> GitHub ile giris -> API Key uret")
        return None
    ex = ccxt.binanceusdm({"apiKey": key, "secret": sec,
                           "enableRateLimit": True,
                           "options": {"defaultType": "future"}})
    ex.set_sandbox_mode(True)          # TESTNET
    try:
        ex.load_markets()
    except Exception as e:
        print(f"  ✗ Baglanti/anahtar hatasi: {repr(e)[:120]}")
        return None
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
        ex.create_order(m, "market", s["side"], qty)
        opp = "sell" if s["side"] == "buy" else "buy"
        ex.create_order(m, "STOP_MARKET", opp, qty, None,
                        {"stopPrice": sl, "reduceOnly": True})
        ex.create_order(m, "TAKE_PROFIT_MARKET", opp, qty, None,
                        {"stopPrice": tp, "reduceOnly": True})
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
