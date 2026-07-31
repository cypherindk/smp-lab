"""
data/funding_fetcher.py
Perpetual funding rate gecmisi (8 saatlik). Adım 5 — funding'i "kalabalik"
sinyali / carry getirisi olarak kullanmak icin. Onbellekli.

KAYNAK: Binance futures (fapi) bu makineden araliklı BLOKLU (ConnectionReset),
bu yuzden BYBIT birincil kaynak (api.bybit.com erisilebilir), Binance fallback.
Cikti her iki kaynakta da ayni: 8h funding orani (ondalik).
"""

import os
import time
import json
import requests
import numpy as np
import pandas as pd

_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache_funding")
os.makedirs(_CACHE, exist_ok=True)


def _sym(symbol):
    s = symbol.upper().replace("/", "").replace(" ", "").replace("-", "")
    if s.endswith("USD") and not s.endswith("USDT"):
        s += "T"
    return s


def _bybit_raw(sym, days):
    """Bybit v5 linear funding/history. Donen: [(ts_ms, rate_float), ...]. Newest-first pagelenir."""
    url = "https://api.bybit.com/v5/market/funding/history"
    end = int(time.time() * 1000)
    start = end - days * 86400 * 1000
    out, cur_end = [], end
    while cur_end > start:
        try:
            r = requests.get(url, params={"category": "linear", "symbol": sym,
                                          "startTime": start, "endTime": cur_end,
                                          "limit": 200}, timeout=20)
            lst = r.json().get("result", {}).get("list", []) if r.status_code == 200 else []
        except Exception:
            break
        if not lst:
            break
        for row in lst:
            out.append((int(row["fundingRateTimestamp"]), float(row["fundingRate"])))
        oldest = int(lst[-1]["fundingRateTimestamp"])
        if oldest <= start or len(lst) < 200:
            break
        cur_end = oldest - 1
        time.sleep(0.15)
    return out


def _binance_raw(sym, days):
    """Binance fapi fundingRate (bloklu olabilir). Donen: [(ts_ms, rate_float), ...]."""
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    end = int(time.time() * 1000)
    start = end - days * 86400 * 1000
    out, cur = [], start
    while cur < end:
        try:
            r = requests.get(url, params={"symbol": sym, "startTime": cur, "limit": 1000}, timeout=15)
            data = r.json() if r.status_code == 200 else None
        except Exception:
            data = None
        if not isinstance(data, list) or not data:
            break
        for row in data:
            out.append((int(row["fundingTime"]), float(row["fundingRate"])))
        cur = data[-1]["fundingTime"] + 1
        if len(data) < 1000:
            break
        time.sleep(0.15)
    return out


def fetch_binance_funding(symbol, days=365, quiet=True):
    """Donen: DatetimeIndex'li funding serisi (8 saatlik, oran ondalik). Bybit oncelikli."""
    sym = _sym(symbol)
    cache = os.path.join(_CACHE, f"{sym}_{days}.json")
    if os.path.exists(cache) and (time.time() - os.path.getmtime(cache)) < 86400:
        raw = json.load(open(cache))
    else:
        raw = _bybit_raw(sym, days)
        src = "bybit"
        if not raw:
            raw = _binance_raw(sym, days)
            src = "binance"
        if raw:
            json.dump(raw, open(cache, "w"))
            if not quiet:
                print(f"  [funding] {sym}: {len(raw)} kayit ({src})")
    if not raw:
        return pd.Series(dtype=float)
    df = pd.DataFrame(raw, columns=["ts", "funding"]).drop_duplicates("ts")
    df["time"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("time")["funding"].sort_index()


def _norm(idx):
    idx = pd.DatetimeIndex(idx)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.as_unit("ns")


def funding_aligned(symbol, bar_index, days=365):
    """Funding'i bar index'ine hizala (ffill) + 30-gunluk ortalamaya gore z-benzeri sapma."""
    f = fetch_binance_funding(symbol, days=days)
    if f.empty:
        return None, None
    f = f.copy()
    f.index = _norm(f.index)
    bidx = _norm(bar_index)
    fa = f.reindex(bidx, method="ffill")
    avg = f.rolling(90, min_periods=20).mean().reindex(bidx, method="ffill")
    std = f.rolling(90, min_periods=20).std().reindex(bidx, method="ffill")
    z = (fa - avg) / std.replace(0, np.nan)
    fa.index = bar_index
    z.index = bar_index
    return fa, z.astype(float)


if __name__ == "__main__":
    for s in ["BTC-USD", "ETH-USD", "SOL-USD"]:
        f = fetch_binance_funding(s, days=120, quiet=False)
        if not f.empty:
            print(f"{s}: {len(f)} kayit, ort={f.mean()*100:.4f}%/8h, son={f.iloc[-1]*100:.4f}%")
        else:
            print(f"{s}: veri yok")
