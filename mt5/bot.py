"""
mt5/bot.py — MT5 OTOMATIK TRADE BOTU (SADECE DEMO).

AMAC: otomatik trade'in MEKANIGINI gormek/dogrulamak — baglan, veri cek, sinyal
uret, RISK'e gore boyutlandir, SL/TP'li emir gonder, pozisyon yonet, raporla.

DURUSTLUK NOTU: `lab/cross_asset.py` testi gosterdi ki trend cekirdegimizin
forex/endeks/emtiada DOGRULANMIS EDGE'i YOK (21 enstruman/22 yil -> Sharpe -0.04).
Bu bot bir PARA MAKINESI DEGIL, ICRA (otomasyon) KANITIDIR. Demo'da mekanigi
ogrenmek icin. Kanitli edge'imiz kripto'da (bkz live/executor.py).

GUVENLIK: gercek hesapta CALISMAYI REDDEDER (DEMO_ONLY). Once --dry ile bak.

Kullanim:
  python mt5/bot.py --dry      # emir GONDERMEZ, ne yapacagini gosterir
  python mt5/bot.py            # demo hesapta gercekten emir gonderir
  python mt5/bot.py --close-all
"""
import argparse
import sys
from datetime import datetime

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import MetaTrader5 as mt5

# ─────────────────────────────────────────────────────── KONFIG
DEMO_ONLY   = True      # ASLA kapatma. Gercek hesapta calismayi reddeder.
SYMBOLS     = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]   # broker adlari degisebilir
TIMEFRAME   = mt5.TIMEFRAME_H4
BARS        = 500
RISK_PCT    = 0.01      # islem basi risk (demo'da ogrenme amacli dusuk)
MAX_POS     = 3         # es zamanli pozisyon tavani
SL_ATR_MULT = 2.0       # stop = 2 x ATR(14)
RR          = 2.0       # TP = 2R
ENTRY_N     = 55        # Donchian giris
TREND_EMA   = 200
ER_MIN      = 0.30      # rejim kapisi
MAGIC       = 20260810  # bu botun emirlerini tanimak icin


# ─────────────────────────────────────────────────────── gostergeler
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def efficiency_ratio(close, n=20):
    ch = (close - close.shift(n)).abs()
    path = close.diff().abs().rolling(n).sum()
    return (ch / path.replace(0, np.nan)).fillna(0.0)


def signal(df):
    """Donchian kirilim + EMA trend + ER rejim. -> 'BUY' | 'SELL' | None"""
    up = df["high"].rolling(ENTRY_N).max().shift(1)
    dn = df["low"].rolling(ENTRY_N).min().shift(1)
    te = ema(df["close"], TREND_EMA)
    er = efficiency_ratio(df["close"], 20)
    i = -1                                    # son KAPALI bar
    if pd.isna(up.iloc[i]) or pd.isna(te.iloc[i]) or er.iloc[i] <= ER_MIN:
        return None
    c = df["close"].iloc[i]
    if c > up.iloc[i] and c > te.iloc[i]:
        return "BUY"
    if c < dn.iloc[i] and c < te.iloc[i]:
        return "SELL"
    return None


# ─────────────────────────────────────────────────────── MT5 yardimcilari
def connect():
    if not mt5.initialize():
        print(f"  ✗ MT5 baglanamadi: {mt5.last_error()}")
        print("    -> MetaTrader 5 terminalini kur + demo hesabina giris yap, sonra tekrar dene.")
        return None
    acc = mt5.account_info()
    if acc is None:
        print(f"  ✗ Hesap bilgisi alinamadi: {mt5.last_error()}"); mt5.shutdown(); return None
    mode = {0: "DEMO", 1: "YARISMA", 2: "GERCEK"}.get(acc.trade_mode, "?")
    print(f"  Hesap {acc.login} | {acc.server} | mod: {mode} | equity: {acc.equity:.2f} {acc.currency}")
    if DEMO_ONLY and acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        print("  ⛔ GUVENLIK: bu bot SADECE DEMO hesapta calisir. Cikiliyor.")
        mt5.shutdown(); return None
    return acc


def rates(sym, n=BARS):
    if not mt5.symbol_select(sym, True):
        return None
    r = mt5.copy_rates_from_pos(sym, TIMEFRAME, 0, n)
    if r is None or len(r) < 250:
        return None
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df.set_index("time")[["open", "high", "low", "close", "tick_volume"]]


def calc_lots(sym, side, entry, sl, equity):
    """Risk-bazli lot: 1 lotun SL'e kadarki zarari uzerinden olcekle."""
    info = mt5.symbol_info(sym)
    if info is None:
        return 0.0
    act = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
    loss1 = mt5.order_calc_profit(act, sym, 1.0, entry, sl)   # 1 lot icin zarar (negatif)
    if loss1 is None or loss1 == 0:
        return 0.0
    lots = (equity * RISK_PCT) / abs(loss1)
    step = info.volume_step or 0.01
    lots = max(info.volume_min, min(info.volume_max, round(lots / step) * step))
    return round(lots, 2)


def send(sym, side, lots, sl, tp):
    tick = mt5.symbol_info_tick(sym)
    price = tick.ask if side == "BUY" else tick.bid
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": lots,
           "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
           "price": price, "sl": sl, "tp": tp, "deviation": 20, "magic": MAGIC,
           "comment": "smp-lab demo", "type_time": mt5.ORDER_TIME_GTC,
           "type_filling": mt5.ORDER_FILLING_IOC}
    res = mt5.order_send(req)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        # bazi brokerlar FOK ister
        req["type_filling"] = mt5.ORDER_FILLING_FOK
        res = mt5.order_send(req)
    return res


def close_all():
    for p in (mt5.positions_get() or []):
        if p.magic != MAGIC:
            continue
        t = mt5.symbol_info_tick(p.symbol)
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume,
               "type": mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY,
               "position": p.ticket, "price": t.bid if p.type == 0 else t.ask,
               "deviation": 20, "magic": MAGIC, "type_time": mt5.ORDER_TIME_GTC,
               "type_filling": mt5.ORDER_FILLING_IOC}
        r = mt5.order_send(req)
        print(f"  kapat {p.symbol} #{p.ticket}: {'OK' if r and r.retcode == 10009 else r}")


# ─────────────────────────────────────────────────────── ana dongu
def cycle(dry):
    print("=" * 78)
    print(f"  MT5 OTOMATIK TRADE — {'DRY (emir YOK)' if dry else 'DEMO (gercek emir)'} "
          f"| {datetime.now():%d.%m %H:%M}")
    print("=" * 78)
    acc = connect()
    if acc is None:
        return

    mine = [p for p in (mt5.positions_get() or []) if p.magic == MAGIC]
    print(f"  Acik (bot): {len(mine)}/{MAX_POS}", flush=True)
    for p in mine:
        print(f"    {p.symbol:8} {'LONG' if p.type == 0 else 'SHORT':5} {p.volume} lot  "
              f"giris {p.price_open:.5f}  P&L {p.profit:+.2f}")

    held = {p.symbol for p in mine}
    for sym in SYMBOLS:
        df = rates(sym)
        if df is None:
            print(f"    {sym:8} veri yok (broker sembol adi farkli olabilir)"); continue
        sig = signal(df)
        er = efficiency_ratio(df["close"], 20).iloc[-1]
        if sig is None:
            print(f"    {sym:8} sinyal yok  (ER {er:.2f})"); continue
        if sym in held:
            print(f"    {sym:8} {sig} ama zaten acik pozisyon var"); continue
        if len(mine) >= MAX_POS:
            print(f"    {sym:8} {sig} ama slot dolu ({MAX_POS})"); continue

        tick = mt5.symbol_info_tick(sym)
        entry = tick.ask if sig == "BUY" else tick.bid
        a = float(atr(df).iloc[-1])
        dist = a * SL_ATR_MULT
        sl = entry - dist if sig == "BUY" else entry + dist
        tp = entry + dist * RR if sig == "BUY" else entry - dist * RR
        lots = calc_lots(sym, sig, entry, sl, acc.equity)
        if lots <= 0:
            print(f"    {sym:8} {sig} ama lot hesaplanamadi"); continue

        risk = acc.equity * RISK_PCT
        print(f"  ► {sym} {sig} | giris {entry:.5f} SL {sl:.5f} TP {tp:.5f} | "
              f"{lots} lot (~{risk:.2f} {acc.currency} risk, ER {er:.2f})")
        if dry:
            print("    (dry: emir gonderilmedi)")
        else:
            r = send(sym, sig, lots, sl, tp)
            ok = r is not None and r.retcode == mt5.TRADE_RETCODE_DONE
            print(f"    {'✓ EMIR ACILDI #' + str(r.order) if ok else '✗ HATA: ' + str(r)}")
            if ok:
                mine.append(r)

    mt5.shutdown()
    print("\n  Not: bu ICRA demosudur. Bu enstrumanlarda dogrulanmis edge YOK")
    print("  (bkz lab/cross_asset.py). Kanitli sistem kripto'da: live/executor.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="emir gondermeden goster")
    ap.add_argument("--close-all", action="store_true", help="botun tum pozisyonlarini kapat")
    a = ap.parse_args()
    if a.close_all:
        if connect():
            close_all(); mt5.shutdown()
    else:
        cycle(a.dry)
