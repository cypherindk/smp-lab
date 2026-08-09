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
ok = mt5.initialize()
if not ok:                      # kurulu ama bulunamiyorsa acik yolla dene
    ok = mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe")
if not ok:
    code, msg = mt5.last_error()
    print(f"  2) Terminal baglantisi  ✗ ({code}: {msg})")
    if code == -6:
        # config'ten gercek sebebi oku: [Experts] Api=0 -> Python API bloklu
        import glob
        import os
        api_val = enabled_val = None
        for ini in glob.glob(os.path.join(os.environ.get("APPDATA", ""),
                                          "MetaQuotes", "Terminal", "*", "config", "common.ini")):
            try:
                txt = open(ini, encoding="utf-16-le", errors="ignore").read()
                if "[Experts]" not in txt:
                    txt = open(ini, encoding="utf-8", errors="ignore").read()
                blk = txt.split("[Experts]")[1].split("[")[0]
                for line in blk.splitlines():
                    if line.strip().startswith("Api="):
                        api_val = line.strip().split("=")[1]
                    if line.strip().startswith("Enabled="):
                        enabled_val = line.strip().split("=")[1]
            except Exception:
                pass
        print(f"\n     Config: Algo Trading Enabled={enabled_val}  |  Api(devre-disi-birak)={api_val}")

        # terminal ag logunda hesap yetkilendirme hatasi var mi? (asil sebep genelde bu)
        import datetime
        logdir = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                              "*", "logs", datetime.date.today().strftime("%Y%m%d") + ".log")
        for lf in glob.glob(logdir):
            try:
                lines = open(lf, encoding="utf-16-le", errors="ignore").read().splitlines()
                if not any("Network" in x for x in lines):
                    lines = open(lf, encoding="utf-8", errors="ignore").read().splitlines()
            except Exception:
                continue
            bad = [x for x in lines if "authorization" in x.lower() and "failed" in x.lower()]
            if bad:
                print("\n     >>> ASIL SEBEP (MT5 ag logundan):")
                print("         " + bad[-1].strip()[-90:])
                print("""
         Terminal hesaba GIRIS YAPAMIYOR (Python'dan once bu duzelmeli).
         'Invalid account' = hesap no / sifre / SUNUCU eslesmiyor.
         EN KOLAY COZUM — masaustunde YENI demo ac:
           Dosya > Hesap Ac  ->  broker ara/sec  ->  'Demo hesap'
           -> formu doldur -> cikan LOGIN + SIFREYI KAYDET -> otomatik baglanir
         (Web'deki hesabi kullanacaksan: DOGRU SUNUCU adini ve sifreyi gir.)
                """)
                break
        if api_val == "0":
            print("""
     >>> SEBEP BULUNDU: Python API kapali (Api=0). Algo Trading acik olsa bile
         HARICI API ayrica engellenir. COZUM:

           Araclar > Secenekler > Uzman Danismanlar sekmesi
             -> 'Python'/'harici API' ile ilgili kutuyu bul:
                * "Algo Trading'i harici Python API uzerinden devre dISI bIrak"
                  gibi bir ifade varsa -> ISARETI KALDIR
                * "Harici API'ye izin ver" gibiyse -> ISARETLE
             -> Tamam > MT5'i KAPAT ve YENIDEN AC (ayar kayit icin sart)
            """)
        else:
            print("""
     SIRAYLA YAP:
       1. Ust cubuktaki [Algo Trading] butonu YESIL olsun
       2. Araclar > Secenekler > Uzman Danismanlar > izin kutulari isaretli
       3. Sag alt kosede baglanti/ping gorunuyor mu?
       4. MT5'i kapatip yeniden ac, sonra tekrar dene.
            """)
    else:
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
