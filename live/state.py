"""
live/state.py — kalici durum (JSON). Actions cron STATELESS kosar; her dongu
state'i okur, bir tarama yapar, gunceller, geri commit eder (audit izi + sureklilik).

state.json semasi:
  { "base_cash":100.0, "realized":0.0, "scale":1.0,
    "positions": { "BTC": {Position...}, ... },
    "history":   [ {coin, side, strategy, entry, exit, pnl, r, opened, closed, reason}, ... ],
    "equity_curve": [ [iso_ts, equity], ... ],
    "last_bar": "2026-08-01T12:00:00+00:00" }
"""
from __future__ import annotations
import json
import os
from core import Position

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")


def load(path: str = DEFAULT_PATH, start_cash: float = 100.0, scale: float = 1.0) -> dict:
    if not os.path.exists(path):
        return {"base_cash": start_cash, "realized": 0.0, "scale": scale,
                "positions": {}, "history": [], "equity_curve": [], "last_bar": None}
    with open(path, "r", encoding="utf-8") as f:
        s = json.load(f)
    # positions dict -> Position nesnelerine
    s["positions"] = {c: Position(**p) for c, p in s.get("positions", {}).items()}
    return s


def save(state: dict, path: str = DEFAULT_PATH) -> None:
    out = dict(state)
    out["positions"] = {c: (p.to_dict() if isinstance(p, Position) else p)
                        for c, p in state.get("positions", {}).items()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)


def broker_from_state(state: dict):
    """PaperBroker'i kayitli durumdan kur (canliya gecerken LiveBroker ile degistir)."""
    from core import PaperBroker
    return PaperBroker(base_cash=state["base_cash"], realized=state["realized"],
                       positions=dict(state["positions"]))
