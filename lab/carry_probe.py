"""
lab/carry_probe.py — Carry (funding arb) icin: Actions'tan hangi funding kaynagi
acik? Binance-fapi US'de bloklu (451); Kraken-Futures/Bybit/OKX'i dene. Calisan
kaynagin FORMATINI da gorelim ki dogru parser'i yazalim. Sadece probe.
"""
import requests

SOURCES = [
    ("kraken-fut PF_XBTUSD",
     "https://futures.kraken.com/derivatives/api/v4/historicalfundingrates?symbol=PF_XBTUSD"),
    ("bybit BTCUSDT",
     "https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=5"),
    ("binance-fapi BTCUSDT",
     "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=5"),
    ("okx BTC-USDT-SWAP",
     "https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=5"),
    ("bitmex XBTUSD",
     "https://www.bitmex.com/api/v1/funding?symbol=XBTUSD&count=5&reverse=true"),
]

print("=== FUNDING KAYNAK PROBE (Actions) ===", flush=True)
for name, url in SOURCES:
    try:
        r = requests.get(url, timeout=20)
        body = r.text[:320].replace("\n", " ")
        print(f"\n[{name}] HTTP {r.status_code}\n  {body}", flush=True)
    except Exception as e:
        print(f"\n[{name}] ERR {type(e).__name__}: {repr(e)[:80]}", flush=True)
print("\n" + "=" * 55, flush=True)
