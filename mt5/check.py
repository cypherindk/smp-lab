"""
mt5/check.py — KURULUM KONTROLU. Her adimi tek tek dogrular, sorunu soyler.
Kullanim:  python mt5/check.py
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

print("=" * 66)
print("  MT5 KURULUM KONTROLU")
print("=" * 66)

# 1) paket
try:
    import MetaTrader5 as mt5
    print(f"  1) Python paketi        ✓ (v{mt5.__version__})")
except Exception as e:
    print(f"  1) Python paketi        ✗ {e}\n     -> pip install MetaTrader5")
    sys.exit(1)

# 2) terminal baglantisi
if not mt5.initialize():
    code, msg = mt5.last_error()
    print(f"  2) Terminal baglantisi  ✗ ({code}: {msg})")
    print("""
     OLASI SEBEPLER:
       * MT5 MASAUSTU uygulamasi kurulu degil  -> kur (web terminal YETMEZ)
       * Terminal kapali                       -> ac ve demo hesabina giris yap
       * Hesaba giris yapilmamis               -> Dosya > Hesaba giris yap
    """)
    sys.exit(1)
ti = mt5.terminal_info()
print(f"  2) Terminal baglantisi  ✓ ({ti.name}, build {ti.build})")

# 3) hesap
acc = mt5.account_info()
if acc is None:
    print("  3) Hesap                ✗ giris yapilmamis -> Dosya > Hesaba giris yap")
    mt5.shutdown(); sys.exit(1)
mode = {0: "DEMO", 1: "YARISMA", 2: "GERCEK"}.get(acc.trade_mode, "?")
mark = "✓" if acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else "⛔"
print(f"  3) Hesap                {mark} {acc.login} | {acc.server} | {mode} | "
      f"{acc.equity:.2f} {acc.currency}")
if acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
    print("     ⛔ GERCEK HESAP! Bot calismayi reddeder. Demo hesaba gec.")

# 4) algo trading izni
if ti.trade_allowed:
    print("  4) Algo Trading izni    ✓")
else:
    print("  4) Algo Trading izni    ✗ -> Araclar > Secenekler > Uzman Danismanlar >")
    print("     'Algo Trading'e izin ver' isaretle (ve ustteki 'Algo Trading' butonu yesil olsun)")

# 5) semboller
print("\n  5) SEMBOL KONTROLU (broker'inda adlar farkli olabilir):")
want = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
found, missing = [], []
for s in want:
    if mt5.symbol_info(s) is not None:
        found.append(s)
    else:
        missing.append(s)
print(f"     bulunan: {', '.join(found) if found else '(yok)'}")
if missing:
    print(f"     BULUNAMADI: {', '.join(missing)}")
    allsym = mt5.symbols_get() or []
    print(f"\n     Broker'inda {len(allsym)} sembol var. Benzer isimler:")
    for m in missing:
        base = m[:6]
        alt = [x.name for x in allsym if base[:3] in x.name and base[3:6] in x.name][:6]
        if alt:
            print(f"       {m} yerine -> {', '.join(alt)}")
    print("     -> mt5/bot.py icindeki SYMBOLS listesini bu adlarla guncelle.")

# 6) veri
if found:
    r = mt5.copy_rates_from_pos(found[0], mt5.TIMEFRAME_H4, 0, 10)
    print(f"\n  6) Veri cekme           {'✓ (' + found[0] + ' H4, ' + str(len(r)) + ' bar)' if r is not None and len(r) else '✗ veri gelmedi'}")

mt5.shutdown()
print("\n  Hepsi ✓ ise:  python mt5/bot.py --dry   (emir gondermeden dener)")
