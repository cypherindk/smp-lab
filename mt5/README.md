# MT5 Otomatik Trade — DEMO (icra kanıtı)

Otomatik trade'in **mekaniğini** görmek için: bağlan → veri çek → sinyal üret → risk'e göre boyutlandır → SL/TP'li emir gönder → pozisyon yönet.

> **Dürüstlük:** `lab/cross_asset.py` testi (21 enstrüman, 22 yıl) gösterdi ki trend çekirdeğimizin **forex/endeks/emtiada doğrulanmış edge'i YOK** (Sharpe −0.04). Bu bot bir **para makinesi değil, otomasyon kanıtı**. Kanıtlı edge kripto'da: `live/executor.py`.

## Kurulum (senin adımların)
1. **MetaTrader 5 terminalini kur** — herhangi bir broker'dan (ör. metatrader5.com veya broker'ının sitesi).
2. **DEMO hesabı aç** ve terminalde giriş yap. (Gerçek hesap açma — bot zaten reddeder.)
3. Terminal **açık kalsın** (Python API terminale bağlanır).
4. Araçlar → Seçenekler → Uzman Danışmanlar → **"Algo Trading" / "Otomatik alım satıma izin ver"** işaretli olsun.

## Çalıştırma
```bash
python mt5/bot.py --dry        # emir GÖNDERMEZ — ne yapacağını gösterir (önce bunu koş)
python mt5/bot.py              # demo hesapta gerçekten emir açar
python mt5/bot.py --close-all  # botun açtığı pozisyonları kapatır
```

## Güvenlik
- `DEMO_ONLY = True` → **gerçek hesapta çalışmayı reddeder** (kapatma).
- `RISK_PCT = 0.01` → işlem başı %1 risk (öğrenme amaçlı düşük).
- `MAX_POS = 3` → en fazla 3 eş zamanlı pozisyon.
- `MAGIC = 20260810` → sadece kendi emirlerini tanır/yönetir, elle açtıklarına dokunmaz.
- Her emir **SL + TP ile** gider (korumasız pozisyon yok).

## Ayarlar (`bot.py` üstü)
| Ayar | Varsayılan | Ne işe yarar |
|---|---|---|
| `SYMBOLS` | EURUSD, GBPUSD, USDJPY, XAUUSD | **Broker'ında adlar farklı olabilir** (ör. `EURUSD.m`, `GOLD`) — "veri yok" derse düzelt |
| `TIMEFRAME` | H4 | tarama periyodu |
| `RISK_PCT` | %1 | işlem başı risk |
| `SL_ATR_MULT` / `RR` | 2.0 / 2.0 | stop = 2×ATR, TP = 2R |
| `ER_MIN` | 0.30 | rejim kapısı (chop'ta işlem yok) |

## Otomatik (periyodik) çalıştırma
Windows Görev Zamanlayıcı ile 4 saatte bir `python mt5/bot.py` koştur — MT5 terminali açık olmalı.

## Ne öğreneceksin
Emrin nasıl gittiğini, lot hesabının nasıl yapıldığını, SL/TP'nin nasıl yerleştiğini, pozisyonun nasıl yönetildiğini — **gerçek para riske atmadan**. Kripto canlıya (ccxt) geçerken bu mekanik bilgi doğrudan işine yarar.
