"""
live/executor.py — CANLI DONGU (tek tarama cyclesi). Actions cron 4H'de kosar.
  1) state.json yukle -> PaperBroker kur
  2) acik pozisyonlar: son barda SL/TP vurulduysa KAPAT
  3) evreni tara (SMP no-RSI + A+ + ER>0.15); bos slot varsa YENI AC (sized)
  4) equity/tarihce guncelle, state.json'a yaz (Actions commit eder), Telegram bildir
Broker'i LiveBroker ile degistirince ayni mantik CANLI calisir. Sadece LAB/paper.
"""
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import requests
from data.crypto_fetcher import fetch_binance_ohlcv
from engine.indicators import compute_all_indicators
from engine.signals import calc_bull_bear_score, calc_triggers, generate_signals
from engine.filters import apply_all_filters
from lab.breadth_wide import WIDE, efficiency_ratio, gated
import state as st
from core import Position, smp_size, RISK_PCT, MAX_CONC, SMP_ALLOC, SCALE, ER_MIN, KILL_DD

IST = timezone(timedelta(hours=3))
DAYS = 400


def _fetch(c):
    df = fetch_binance_ohlcv(c, interval="4h", days=DAYS, quiet=True)
    return df if len(df) >= 250 else None


def _signal(c, df):
    """Son KAPALI barda no-RSI A+ ER>0.15 sinyali. -> dict | None."""
    ind = compute_all_indicators(df, preset="Aggressive", timeframe_minutes=240, adr_mult=WIDE[c][0])
    sc = calc_bull_bear_score(ind, mtf=None, drop={"rsi"})
    tr = calc_triggers(ind, sc)
    sg = generate_signals(ind, sc, tr, preset="Aggressive", eff_score=3.0,
                          min_conf=2, grade_filter="A+ Only")
    fs = apply_all_filters(ind, sg, use_cvd=True)
    gate = efficiency_ratio(df["close"], 20) > ER_MIN
    fs = gated(fs, gate)
    i = -1
    buy, sell = bool(fs["buy_signal"].iloc[i]), bool(fs["sell_signal"].iloc[i])
    if not (buy or sell):
        return None
    side = "LONG" if buy else "SHORT"
    entry = float(df["close"].iloc[i])
    sp = float(ind["safe_stop_pct"].iloc[i]) / 100.0
    rr = WIDE[c][1]
    sl = entry * (1 - sp) if side == "LONG" else entry * (1 + sp)
    tp = entry * (1 + sp * rr) if side == "LONG" else entry * (1 - sp * rr)
    return dict(coin=c, side=side, entry=entry, sl=sl, tp=tp, bar=str(df.index[i]))


def tg(msg):
    tok, chat = os.getenv("LAB_BOT_TOKEN"), os.getenv("LAB_CHAT_ID")
    if not (tok and chat):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": msg, "parse_mode": "HTML"}, timeout=15)
    except Exception:
        pass


def cycle():
    s = st.load(start_cash=100.0, scale=SCALE)
    broker = st.broker_from_state(s)
    scale = s.get("scale", SCALE)
    alerts, prices = [], {}

    # --- veri (acik pozisyon coinleri + tum evren) ---
    dfs = {}
    for c in WIDE:
        try:
            d = _fetch(c)
            if d is not None:
                dfs[c] = d
                prices[c.replace("-USD", "")] = float(d["close"].iloc[-1])
        except Exception:
            pass

    # --- 1) CIKIS: acik pozisyonlarda son bar SL/TP ---
    for coin in list(broker.get_positions().keys()):
        p = broker.get_positions()[coin]
        df = dfs.get(coin + "-USD")
        if df is None:
            continue
        hi, lo, close = float(df["high"].iloc[-1]), float(df["low"].iloc[-1]), float(df["close"].iloc[-1])
        exit_px, reason = None, None
        if p.side == "LONG":
            if lo <= p.sl: exit_px, reason = p.sl, "SL"
            elif hi >= p.tp: exit_px, reason = p.tp, "TP"
        else:
            if hi >= p.sl: exit_px, reason = p.sl, "SL"
            elif lo <= p.tp: exit_px, reason = p.tp, "TP"
        if exit_px:
            pos, pnl, line = broker.close(coin, exit_px, reason)
            s["history"].append(dict(coin=coin, side=pos.side, strategy=pos.strategy,
                                     entry=pos.entry, exit=exit_px, pnl=round(pnl, 2),
                                     r=round(pos.r_multiple(exit_px), 2), opened=pos.entry_time,
                                     closed=str(df.index[-1]), reason=reason))
            alerts.append(("🔴" if pnl < 0 else "🟢") + " " + line)

    # --- equity + kill-switch ---
    equity = broker.get_equity(prices)
    curve = s.get("equity_curve", [])
    peak = max([e for _, e in curve] + [equity]) if curve else equity
    dd = equity / peak - 1 if peak > 0 else 0
    blocked = dd <= KILL_DD

    # --- 2) GIRIS: bos slot + rejim + kill-switch degilse ---
    open_smp = [c for c, p in broker.get_positions().items() if p.strategy == "SMP"]
    if not blocked:
        for c in WIDE:
            base = c.replace("-USD", "")
            if base in broker.get_positions() or len(open_smp) >= MAX_CONC:
                continue
            df = dfs.get(c)
            if df is None:
                continue
            sig = _signal(c, df)
            if not sig:
                continue
            qty, risk_d = smp_size(equity, sig["entry"], sig["sl"], RISK_PCT, scale)
            if qty <= 0:
                continue
            pos = Position(coin=base, side=sig["side"], strategy="SMP", entry=sig["entry"],
                           qty=qty, sl=sig["sl"], tp=sig["tp"], risk_dollars=risk_d,
                           entry_time=sig["bar"])
            alerts.append("🟢 " + broker.open(pos))
            open_smp.append(base)

    # --- 3) kaydet ---
    now = datetime.now(timezone.utc)
    s["base_cash"], s["realized"] = broker.base_cash, broker.realized
    s["positions"] = dict(broker.get_positions())
    equity = broker.get_equity(prices)
    curve.append([now.isoformat(), round(equity, 2)])
    s["equity_curve"], s["last_bar"] = curve[-500:], now.isoformat()
    st.save(s)

    # --- 4) rapor ---
    ist = now.astimezone(IST).strftime("%d.%m %H:%M")
    head = (f"📊 SMP+Trend PAPER — TSİ {ist}\nEquity: ${equity:.2f}  "
            f"(DD {dd*100:+.1f}%{'  ⛔KILL' if blocked else ''})\n"
            f"Acik: {len(broker.get_positions())}/{MAX_CONC}  Realized: ${broker.realized:+.2f}")
    print(head, flush=True)
    for a in alerts:
        print("  " + a, flush=True)
    if alerts:
        tg(head + "\n" + "\n".join(alerts))
    else:
        print("  (yeni islem yok)", flush=True)


if __name__ == "__main__":
    cycle()
