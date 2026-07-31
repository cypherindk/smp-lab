"""
backtest/event_engine.py
Saf pandas/numpy event-driven backtester (vectorbt YOK).

Neden vectorbt degil?
  - vectorbt bu makinede kurulu degil + pandas 3.0/numpy 2.x ile basi dertli.
  - ICT setup'lari DURUMSAL: "sweep -> MSS -> %50 fib'e LIMIT emir -> dolarsa
    yonet". Bu bar-bar bir durum makinesi ister; from_signals ile temiz
    ifade edilemez. Bar-bar simulasyon ayni zamanda dolum varsayimlarini
    (fill assumptions) DURUST ve acik yapar.

DOLUM (FILL) VARSAYIMLARI — hepsi lehimize DEGIL, muhafazakar:
  1. Sinyal bar i'nin KAPANISINDA hesaplanir; emir i+1'den itibaren aktif
     (lookahead yok).
  2. Giris LIMIT emri: long icin bar.low <= entry olunca `entry`ten dolar
     (gap ile daha iyi fiyat verilmez -> hafif muhafazakar). Slippage
     aleyhimize eklenir.
  3. Pozisyon dolduktan SONRAKI bardan itibaren yonetilir (ayni-bar giris+cikis
     belirsizligi yok).
  4. Ayni barda hem SL hem TP teghetlenirse -> SL once (worst-case).
  5. Komisyon her iki bacakta; slippage her iki bacakta.
  6. Ayni anda TEK pozisyon; pozisyondayken gelen yeni sinyaller atlanir.
  7. Pozisyon boyutu = (equity * risk_pct) / stop_mesafesi; kaldiracsiz
     (nominal <= equity) tavani var. Equity islem-islem bilesiklenir.
"""

import numpy as np
import pandas as pd


# Yaklasik yillik bar sayisi (Sharpe annualization icin)
_BARS_PER_YEAR = {
    "1m": 525600, "5m": 105120, "15m": 35040, "30m": 17520,
    "1h": 8760, "2h": 4380, "4h": 2190, "1d": 365,
}


def simulate(df: pd.DataFrame, orders: list, tf: str = "15m",
             initial_capital: float = 100.0,
             risk_pct: float = 0.01,
             fee_pct: float = 0.0005,      # taker, bacak basina (%0.05)
             slippage_pct: float = 0.0003,  # bacak basina (%0.03)
             max_wait_bars: int = 12,
             max_hold_bars: int = 48) -> dict:
    """
    df     : yurutme TF OHLCV (DatetimeIndex, lowercase kolonlar)
    orders : [{"signal_pos": int, "side": +1/-1, "entry": f, "sl": f, "tp": f}, ...]
             signal_pos = kurulumun ONAYLANDIGI bar konumu.
    """
    n = len(df)
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    orders = sorted(orders, key=lambda x: x["signal_pos"])

    state = "flat"          # flat | armed | in
    p = 0                   # siradaki emir isaretcisi
    armed = None
    arm_deadline = -1
    pos = None
    equity = initial_capital
    trades = []
    equity_curve = np.full(n, equity, dtype=float)

    for i in range(n):
        # ── acik pozisyonu yonet (giris barindan SONRA) ──
        if state == "in":
            held = i - pos["entry_bar"]
            exit_price = None
            reason = None
            if held >= 1:
                side = pos["side"]
                sl = pos["sl"]; tp = pos["tp"]
                if side == 1:
                    if l[i] <= sl:
                        exit_price, reason = sl, "sl"
                    elif h[i] >= tp:
                        exit_price, reason = tp, "tp"
                else:
                    if h[i] >= sl:
                        exit_price, reason = sl, "sl"
                    elif l[i] <= tp:
                        exit_price, reason = tp, "tp"
                if exit_price is None and held >= max_hold_bars:
                    exit_price, reason = c[i], "time"

            if exit_price is not None:
                side = pos["side"]
                qty = pos["qty"]
                # cikista slippage aleyhimize
                exit_fill = exit_price * (1 - slippage_pct) if side == 1 else exit_price * (1 + slippage_pct)
                entry_fill = pos["entry_fill"]
                gross = qty * (exit_fill - entry_fill) * side
                fees = fee_pct * (qty * entry_fill + qty * exit_fill)
                pnl = gross - fees
                equity += pnl
                trades.append({
                    "entry_time": df.index[pos["entry_bar"]],
                    "exit_time": df.index[i],
                    "side": "long" if side == 1 else "short",
                    "entry": entry_fill, "exit": exit_fill,
                    "sl": pos["sl"], "tp": pos["tp"],
                    "bars_held": held, "reason": reason,
                    "pnl": pnl, "R": pnl / pos["risk_amount"] if pos["risk_amount"] else 0.0,
                    "equity": equity,
                })
                state = "flat"
                pos = None

        # ── flat: bu barda (signal_pos==i) onaylanan emri kur ──
        if state == "flat":
            while p < len(orders) and orders[p]["signal_pos"] < i:
                p += 1  # pozisyondayken kacirilan bayat sinyalleri at
            if p < len(orders) and orders[p]["signal_pos"] == i:
                armed = orders[p]
                p += 1
                arm_deadline = i + max_wait_bars
                state = "armed"    # dolum takibi i+1'den baslar

        # ── armed: limit dolumu bekle ──
        elif state == "armed":
            if i > arm_deadline:
                state = "flat"
                armed = None
            else:
                side = armed["side"]
                entry = armed["entry"]
                filled = (side == 1 and l[i] <= entry) or (side == -1 and h[i] >= entry)
                if filled:
                    entry_fill = entry * (1 + slippage_pct) if side == 1 else entry * (1 - slippage_pct)
                    stop_dist = abs(entry - armed["sl"])
                    if stop_dist <= 0:
                        state = "flat"; armed = None
                    else:
                        risk_amount = equity * risk_pct
                        qty = risk_amount / stop_dist
                        qty = min(qty, equity / entry_fill)   # kaldiracsiz tavan
                        pos = {
                            "side": side, "entry_bar": i, "entry_fill": entry_fill,
                            "sl": armed["sl"], "tp": armed["tp"],
                            "qty": qty, "risk_amount": risk_amount,
                        }
                        state = "in"
                        armed = None

        equity_curve[i] = equity

    trades_df = pd.DataFrame(trades)
    stats = _compute_stats(trades_df, equity_curve, initial_capital, tf)
    return {"stats": stats, "trades": trades_df,
            "equity_curve": pd.Series(equity_curve, index=df.index)}


def _compute_stats(trades: pd.DataFrame, equity_curve: np.ndarray,
                   init: float, tf: str) -> dict:
    if trades.empty:
        return {"trades": 0, "return_pct": 0.0, "win_rate": 0.0,
                "profit_factor": 0.0, "expectancy_R": 0.0, "max_dd": 0.0,
                "sharpe": 0.0, "avg_win_R": 0.0, "avg_loss_R": 0.0,
                "final_equity": init}

    wins = trades[trades["pnl"] > 0]
    losses = trades[trades["pnl"] <= 0]
    gross_win = wins["pnl"].sum()
    gross_loss = abs(losses["pnl"].sum())
    final_eq = equity_curve[-1]

    # Max drawdown (equity curve, peak-to-trough %)
    peak = np.maximum.accumulate(equity_curve)
    dd = (equity_curve - peak) / peak
    max_dd = abs(dd.min()) * 100

    # Sharpe: equity egrisinin bar-bar getirilerinden, yillikla
    ec = pd.Series(equity_curve)
    rets = ec.pct_change().dropna()
    if rets.std() > 0:
        bpy = _BARS_PER_YEAR.get(tf, 35040)
        sharpe = (rets.mean() / rets.std()) * np.sqrt(bpy)
    else:
        sharpe = 0.0

    return {
        "trades": len(trades),
        "return_pct": (final_eq - init) / init * 100,
        "win_rate": len(wins) / len(trades) * 100,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_R": trades["R"].mean(),
        "avg_win_R": wins["R"].mean() if len(wins) else 0.0,
        "avg_loss_R": losses["R"].mean() if len(losses) else 0.0,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "final_equity": final_eq,
    }


def print_stats(stats: dict, label: str = "Backtest"):
    print(f"\n{'='*54}\n  {label}\n{'='*54}")
    print(f"  Islem sayisi   : {stats['trades']}")
    print(f"  Toplam getiri  : %{stats['return_pct']:.1f}  "
          f"({stats['final_equity']:.2f})")
    print(f"  Win rate       : %{stats['win_rate']:.1f}")
    print(f"  Profit factor  : {stats['profit_factor']:.2f}")
    print(f"  Beklenti (R)   : {stats['expectancy_R']:+.3f} R/islem")
    print(f"  Ort. kazanc/kayip: +{stats['avg_win_R']:.2f}R / {stats['avg_loss_R']:.2f}R")
    print(f"  Max drawdown   : %{stats['max_dd']:.1f}")
    print(f"  Sharpe         : {stats['sharpe']:.2f}")
    print(f"{'='*54}")
