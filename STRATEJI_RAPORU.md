# SMP — Strateji Araştırma Raporu (Faz 1)

> Amaç: Gönderilen 8 indikatörü taramak, piyasada kullanılan ICT/SMC ve diğer
> strateji ailelerini araştırmak ve "hangi strateji ile ilerlemeliyiz" sorusuna
> **dürüst, test edilebilir** bir cevap vermek. Faz 2'de seçilen strateji
> TradingView (Pine) indikatörüne ve/veya mevcut Python SMP botuna işlenecek.

Tarih: 2026-07-25

---

## 0. Yönetici Özeti (TL;DR)

1. **8 indikatörün 5'i doğrudan ICT/SMC ailesinden.** En değerli 3 tanesi tam bir
   giriş/çıkış sistemi tarif ediyor: **MSS Sweep Fib Retrace** (LuxAlgo),
   **True Order Block Time & Price** (MTSY), **Order Block Matrix Trade Engine**
   (Alpha Extract). Diğerleri "bağlam/konfluens" araçları (SMC toolkit, Liquidity
   Delta Profiler, Thermal Map, Trend Bands+VWAP) ve bir de BIST tarayıcı (Avize).

2. **Mevcut SMP motorumuz zaten ICT/SMC'nin çekirdeğini içeriyor:** MTF Likidite
   Matrix (Equal High/Low + Sweep), Smart Money Flow (CVD/MFI gizli divergence),
   VSA/VPA. Yani sıfırdan başlamıyoruz — üzerine **giriş tetikleyici + risk
   yönetimi** katmanı ekliyoruz.

3. **"Her gün min %5" hedefi matematiksel olarak sürdürülebilir değil** (bkz.
   Bölüm 3). Bu bir "olamaz, vazgeç" değil; bir **ölçek düzeltmesi**. Aynı motor,
   gerçekçi bir hedefe ayarlandığında değerli. Hedefi "garantili günlük %5"ten
   "**kanıtlanmış pozitif beklenti (edge) + kontrollü düşüş**"e çeviriyoruz.

4. **Önerilen strateji:** *SMP-ICT Confluence Engine* — 4 katmanlı
   (Bias → Setup → Konfluens → Risk), intraday (5m/15m yürütme, 1H/4H yön),
   kripto major'lar üzerinde; BIST için mevcut 4H swing + Avize/Chandelier ayrı
   kanal. Detay Bölüm 4.

5. **Faz 1 başarı kriteri:** out-of-sample (görülmemiş veri) üzerinde
   Profit Factor > 1.3, Max Drawdown < %20, 200+ işlemde pozitif beklenti.
   Bu sağlanmadan Faz 2'ye (canlı/indikatör) geçilmez.

---

## 1. İncelenen 8 İndikatör

| # | İndikatör (Yazar) | Kategori | Açık kaynak? | Bizim için değeri |
|---|---|---|---|---|
| 1 | **MSS Sweep Fib Retrace** (LuxAlgo) | ICT — **tam sistem** | Kütüphane/örnek | ⭐ Çekirdek setup adayı: Sweep→MSS→%50 Fib giriş, ATR SL/TP |
| 2 | **Dynamic Trend Bands & Anchored VWAP** (BigBeluga) | Trend + Hacim | Kapalı | Bias/rejim filtresi + Delta Volume onayı |
| 3 | **Liquidity Delta Profiler** (LuxAlgo) | ICT/SMC | Kapalı | Dönüş sinyali dili: ABS/EXH/DIV/REJ (konfluens fikri) |
| 4 | **Liquidity Thermal Map** (BigBeluga) | Hacim profili | Kapalı | Sadece bağlam: POC / likidite yoğunluğu (sinyal yok) |
| 5 | **Avize** (Nephilis) | Trend + Tarayıcı | Kapalı | ⭐ BIST kanalı: Chandelier Exit (ATR trailing) + RVOL |
| 6 | **True Order Block Time & Price** (MTSY) | ICT — **tam sistem** | Kapalı | ⭐ 5 katmanlı OB doğrulama + FVG + London/NY killzone |
| 7 | **Order Block Matrix Trade Engine** (Alpha Extract) | SMC/Order Flow | Kapalı | Otomatik trade motoru + win-rate/PF paneli (metrik fikri) |
| 8 | **Smart Money Concepts** (LuxAlgo) | SMC — temel araç | **Açık kaynak** | ⭐ Yapı temeli: BOS/CHoCH, OB, FVG, equal H/L, premium/discount |

**Kritik nüans (kapalı kaynak):** 2,3,4,6,7 numaralar kapalı kaynak. Bunları
birebir kopyalayamayız (kod görünmüyor) — **mantıklarını yeniden uyguluyoruz**.
1 ve 8 açık/örnek olduğu için birebir referans alınabilir. Bu, mevcut botun
zaten yaptığı şey (Pine → Python "yaklaşık yeniden uygulama").

---

## 2. Piyasada Kullanılan Strateji Aileleri (ve gerçekçi performans)

### 2.1 ICT (Inner Circle Trader)
Kurumsal likidite avı mantığı. Temel taşları:
- **Liquidity Sweep / Stop Hunt:** Fiyat önceki dip/tepeyi süpürüp geri döner.
- **MSS / BOS / CHoCH:** Yapı kırılımı = yön değişimi onayı.
- **Order Block (OB):** Kurumsal impuls öncesi son karşı mum = yüksek olasılıklı giriş bölgesi.
- **Fair Value Gap (FVG):** 3 mumluk dengesizlik; fiyat genelde geri dönüp doldurur.
- **OTE / Fibonacci:** Süpürme aralığının %50–%79 geri çekilmesi = giriş.
- **Killzone:** London (02:00–05:00) ve New York (07:00–10:00 NY saati) = kurumsal aktivite penceresi. Bu pencereler dışında güvenilirlik ciddi düşüyor.

### 2.2 SMC (Smart Money Concepts)
ICT'nin daha yapısal/sadeleştirilmiş versiyonu: market structure, premium/discount
bölgeleri, equal high/low, OB + FVG. LuxAlgo SMC toolkit (#8) tam da bu.

### 2.3 Order Flow / Hacim
CVD (kümülatif delta), volume delta, volume profile / POC, VSA. **Bizim botta
zaten var** (smart_money_flow, MTF matrix, VSA).

### 2.4 Trend / Momentum & Ortalamaya Dönüş
EMA/VWAP/ADX (trend), Chandelier/ATR trailing (Avize), Bollinger (mean reversion).
Botta trend katmanı mevcut.

### 2.5 Gerçekçi performans (bağımsız backtest'ler)
- ICT/SMC **sıkı konfluensle** (OB + FVG + sweep + killzone hepsi birlikte)
  gerçek win-rate **%50–65** aralığında — ICT anlatımlarındaki %70–80 değil.
- En güçlü kurulum (breaker + FVG + HTF OB üst üste) **haftada ~2 kez** çıkıyor.
- **Kârlılığı win-rate değil, risk yönetimi belirliyor:** minimum **1:2 R:R** ve disiplin.

Kaynaklar: [ICT backtest / SMC guide (Medium — 2.600 işlem)](https://medium.com/@QuantumAlgo/i-backtested-2-600-trades-using-smart-money-concepts-heres-what-actually-works-bb3c671098c6),
[Trading Wyckoff — SMC guide](https://tradingwyckoff.com/en/smart-money-concepts/),
[Backtrex — SMC 2026](https://backtrex.com/en/blog/what-is-smart-money-concepts-trading).

---

## 3. "Her Gün Min %5" Hedefi — Matematiksel Gerçeklik

Bu bölüm hayal kırıklığı için değil, **doğru ölçeği** kurmak için. %5 günlük
getiri *bileşik* olarak şu demek:

| Süre | %5/gün ise 100$ → | %1/gün ise 100$ → |
|---|---|---|
| 1 hafta (5 gün) | 128 $ | 105 $ |
| 1 ay (~21 işlem günü) | 279 $ | 123 $ |
| 3 ay (~63 gün) | 2.163 $ | 187 $ |
| 6 ay (~126 gün) | 46.800 $ | 350 $ |
| **1 yıl (~252 gün)** | **~21.900.000 $** | ~1.227 $ |
| 2 yıl | ~4,8 trilyon $ | ~15.000 $ |

**Neden imkânsız:** %5/gün, yılda ~**+21.800.000%** demek. Karşılaştırma:
- Tarihin en iyi fonu (Renaissance Medallion): ~%39/**yıl** (net).
- Warren Buffett: ~%20/**yıl**.
- Çok iyi bir prop/fon trader'ı: %15–40/**yıl**.

Yani %5/gün, tarihin en iyi profesyonellerinin **yüzbinlerce katı**. Böyle bir
şey mümkün olsaydı 100$ birkaç yılda dünyanın tüm parasını yutardı — piyasa buna
izin vermez.

Hatta prop firmalarının **"solid/achievable" dediği hedef bile ~%1/gün** ve
o bile bileşikle yılda +%1.100'e denk (yani en iyi fonların ~30 katı) — çoğu
trader onu bile tutturamıyor.
Kaynaklar: [What is a realistic profit from day trading](https://bigbrainmoney.com/what-is-a-realistic-profit-from-day-trading/),
[QuantVPS — Prop firm statistics 2026](https://www.quantvps.com/blog/prop-firm-statistics),
[ForTraders — realistic profit target](https://www.fortraders.com/blog/how-to-create-a-realistic-profit-target-plan).

### 3.1 Gerçekçi olarak neyi hedefliyoruz
- **Birincil hedef:** *kanıtlanmış pozitif beklenti* (out-of-sample'da PF > 1.3).
  Piyasada asıl zor olan bu — çoğu strateji bunu geçemez.
- **Agresif ama gerçek üst sınır:** iyi ayarlanmış otomatik intraday sistem için
  **ayda birkaç %** (iyi rejimde tek haneli yüksek %'ler), **düşüş dönemleriyle birlikte**.
- **Beklenti modeli:** %55 win-rate + 1:2 R:R → işlem başına beklenti
  `0.55×2 − 0.45×1 = +0.65R`. İşlem başına %1 risk edersen ortalama **+%0.65/işlem**.
  Günde 1–2 kaliteli killzone kurulumu → iyi günde ~%1, ama **kayıp günler ve
  düşüşler garantili**. Ortalama pozitif, günlük "garanti" yok.

> **Özet:** Motoru %5/gün'e "ayarlamak" mümkün değil; ama sağlam bir edge
> bulursak, gerçekçi bileşikle 100$ zamanla anlamlı büyür. Önce **edge'i
> kanıtlıyoruz**, sonra pozisyon boyutunu konuşuyoruz.

---

## 4. Önerilen Strateji: "SMP-ICT Confluence Engine"

4 katmanlı, modüler. Her katman mevcut kodla veya yeni modülle eşleştirilebilir.

### Katman 1 — BIAS / Yön (HTF)
- 1H/4H yapı: BOS/CHoCH (SMC #8), premium/discount bölgesi.
- Trend rejimi: Dynamic Trend Bands + Anchored VWAP (#2) mantığı; mevcut EMA/VWAP/ADX.
- Kural: Sadece HTF bias yönünde işlem (long ise sadece long setup'ları).

### Katman 2 — SETUP / Tetik (LTF, 5m/15m)
İki alternatif çekirdek (Faz 1'de yarıştıracağız):
- **A) MSS Sweep Fib Retrace (#1):** likidite süpürme → MSS onayı → %50 Fib (OTE) girişi.
- **B) True Order Block (#6):** sweep → dönüş → OB → local FVG → HTF FVG konfluens.

### Katman 3 — KONFLUENS / Onay
- Mevcut **MTF Likidite Matrix** (equal H/L sweep) — `engine/liquidity_mtf.py`.
- Mevcut **Smart Money Flow** (CVD/MFI gizli divergence) — `engine/smart_money_flow.py`.
- FVG hizası + RVOL > eşik + Delta Volume yönü (#2/#3).
- İsteğe bağlı: Liquidity Delta Profiler dili (ABS/EXH/DIV/REJ) reddediş onayı.

### Katman 4 — RİSK / Yürütme
- SL: ATR tabanlı veya OB/sweep geçersizleşme noktası.
- TP: **minimum 1:2 R:R** (kârlılığın asıl motoru), kısmi TP + Chandelier trailing (Avize #5).
- Pozisyon: işlem başına sabit **%1 risk** (fixed-fractional).
- **Killzone filtresi:** sadece London/NY pencereleri (kriptoda da bu saatler en hareketli).

### Piyasa / Zaman dilimi ayrımı
- **Kripto major'lar (BTC/ETH + yüksek likidite alt'lar):** intraday 5m/15m — asıl
  "günlük büyüme" motoru (7/24, killzone uygulanabilir).
- **BIST:** mevcut 4H swing SMP + Avize/Chandelier ayrı kanal (seans saatleri kısıtlı,
  intraday killzone daha az anlamlı).

---

## 5. Faz 1 Test Planı (edge kanıtı)

**Veri:** kripto 5m/15m/1H/4H (yfinance/exchange), en az 12–18 ay; BIST için mevcut kaynak.

**Adımlar:**
1. Setup A ve B'yi ayrı ayrı kodla (mevcut `backtest/runner.py` + `optimize/` üstüne).
2. **In-sample** optimize et → **out-of-sample** (görülmemiş dönem) doğrula.
3. **Walk-forward** (kayan pencere) — aşırı-uyum (overfit) kontrolü.
4. Maliyetleri kat: komisyon + spread + slippage (yoksa sonuçlar yalan).

**Geçme kriterleri (out-of-sample):**
| Metrik | Eşik |
|---|---|
| Profit Factor | > 1.3 |
| Max Drawdown | < %20 |
| İşlem sayısı | > 200 (istatistiksel anlam) |
| Beklenti | > +0.2R / işlem |
| Sharpe (opsiyonel) | > 1.0 |

**Araçlar:** mevcut `backtest/` + `optimize/` altyapısı; ek olarak TradingView MCP
(`backtest_strategy`, `walk_forward_backtest_strategy`, `compare_strategies`) ile
çapraz doğrulama.

---

## 5.1 FAZ 1 — ARA BULGULAR (canlı, güncellenen)

**Kurulan altyapı (çalışıyor):**
- `data/crypto_fetcher.py` — Binance public REST'ten ÜCRETSİZ, sınırsız geçmiş
  5m/15m/1h/4h OHLCV (ekstra kurulum yok; yfinance'in ~60 gün sınırını aştık).
  Onbellekli. (vectorbt/ccxt bu makinede kurulu DEĞİL — bilerek kullanmadık.)
- `backtest/event_engine.py` — saf-pandas event-driven backtester (limit emir +
  SL/TP + risk + maliyet, dürüst dolum varsayımları).
- `engine/ict.py` — ortak ICT primitifleri (pivot/swing/sweep/displacement/FVG/OB/killzone).
- `strategies/mss_sweep_fib.py` — Setup A.
- `backtest/run_ict.py` — deney harness'i.

**Bulgu 1 — motor doğrulaması bir bug yakaladı & düzeltildi:** çıkış-sebebi
dağılımı "TP çıkışı = −1.24R" gösterince short tarafında TP'nin yanlış tarafa
hesaplandığı bulundu ve düzeltildi. (Bar-bar backtest + sebep kırılımı olmasa
gözden kaçardı.)

**Bulgu 2 — intraday maliyet drag'i büyük:** 15m'de stop mesafesi fiyatın
~%0.3'ü; round-trip maliyet ~%0.16 notional → **işlem başına ~0.15–0.5R** maliyet.
Tight-stop scalping'in doğal düşmanı.

**Bulgu 3 (EN ÖNEMLİ) — Setup A tek başına edge'e sahip DEĞİL:** HTF trend +
killzone + OTE (fib 0.62) filtreleriyle bile, **maliyet sıfır olsa dahi** beklenti
negatif (15m −0.085R, 1h −0.179R, 4h −0.230R). Yani kayıp esasen maliyetten değil,
setup'ın öngörü gücü olmamasından. Araştırmayla (Bölüm 2.5) tutarlı: tek-konsept
ICT kaybeder; edge ancak SIKI çoklu-konfluensle mümkün.

**Sonuç:** "İndikatörleri birleştir → günde %5" varsayımı, kullanıcının kendi
verisinde SOMUT olarak çürüdü. Bu, gerçek parayı yanlış bir öncüle yatırmadan
öğrenilen en değerli şey. Sıradaki testler (Setup B + mevcut SMP konfluens
filtreleri) pozitif ve dayanıklı bir edge veremezse, dürüst cevap "bu hedef bu
yöntemle ulaşılamaz" olacak.

## 5.2 FAZ 1 — OOS VERDİCT (kesin)

İki setup da (A: MSS Sweep Fib, B: True OB) çok sayıda konfigle, hem 15m hem 1h'te,
in-sample (IS %60) / out-of-sample (OOS %40) bölünerek test edildi. Taker maliyet
(%0.05+%0.03) dahil. `backtest/oos.py`.

**15m (intraday — "günlük compounding" tezi):**
| Konfig | IS BeklR | OOS BeklR | Verdict |
|---|---|---|---|
| B2 +trend +killzone | +0.008R | **−0.040R** | OVERFIT (OOS çöktü) |
| B3 +trend +MSS | +0.081R | **−0.189R** | OVERFIT (OOS çöktü) |
| B1, B5, A | negatif | negatif | ikisi de − |

→ **15m'de DAYANIKLI edge YOK.** In-sample'da iyi görünenler OOS'ta çöktü (klasik
overfit). Intraday scalping tezi OOS'ta başarısız.

**1h:**
| Konfig | IS BeklR | OOS BeklR | Verdict |
|---|---|---|---|
| **A trend only** | **+0.333R** (win %62) | **+0.115R** (win %48) | ✅ **DAYANDI** |
| B3, B5 | negatif | pozitif | tutarsız (gürültü) |

→ **OOS'ta ayakta kalan TEK şey: 1h'te basit trend-takibi** ("sweep+MSS +
EMA200 yönünde işlem"). Edge'in kaynağı ICT süslemeleri değil, **trend hizası**.

**DÜRÜST NİHAİ TABLO:**
1. **"$100 → günde %5" premisi 15m'de kesin olarak çürüdü** — hiçbir konfig OOS'ta
   ayakta kalmadı.
2. **Tek gerçek ipucu:** 1h trend-takibi, OOS +0.115R (maliyet sonrası) — ama
   İNCE ve zayıf örneklem (~44 işlem). ~+0.5%/ay beklentisine denk; **5%/gün'ün
   çok çok uzağında.** ~30 konfig denendiği için survivorship-bias riski hâlâ var.
3. Bu ipucu gerçekse bile daha fazla doğrulama ister: çoklu walk-forward fold,
   daha çok coin, daha uzun geçmiş, sonra paper trade — ancak ondan sonra gerçek para.

## 5.3 FAZ 1 — WALK-FORWARD NİHAİ VERDİCT (kesin)

Tek 60/40 split'te "dayanan" 1h trend ipucu, **9 coin evreninde 5 ardışık fold**
walk-forward'a sokuldu (`backtest/walkforward.py`, taker maliyet):

| Konfig | F1 | F2 | F3 | F4 | F5 | Genel | Poz. fold |
|---|---|---|---|---|---|---|---|
| A trend200 rr2 (eski "survivor") | +0.03 | −0.21 | −0.36 | −0.02 | −0.10 | **−0.152R** | 1/5 |
| A trend200 rr3 | −0.03 | −0.25 | −0.29 | +0.02 | −0.01 | −0.118R | 1/5 |
| A trend100 | +0.02 | −0.14 | −0.18 | −0.05 | −0.11 | −0.099R | 1/5 |
| B5 trend no-FVG (450 işlem) | +0.01 | −0.41 | −0.24 | −0.26 | −0.23 | −0.230R | 1/5 |

→ **Eski "OOS survivor" bir seraptı.** 3-coin/tek-split örneklem artığıymış; geniş
evrende + çok-fold'da **negatif ve 5 fold'un 4'ünde kaybediyor.** Diğer tüm
konfigler de öyle.

### NİHAİ SONUÇ (dürüst, kesin)
**Test edilen hiçbir ICT/SMC setup'ının (A veya B, hiçbir konfig, 15m veya 1h)
gerçekçi maliyet sonrası DAYANIKLI bir edge'i yok.** Bu, LuxAlgo'nun kendi SMC
indikatöründeki uyarıyla ("bu kavramların geçerliliğine dair destekleyici veri
yoktur") birebir örtüşüyor.

**Bu Faz 1'in BAŞARISIDIR, başarısızlığı değil:** kullanıcının kendi verisiyle,
titiz metodolojiyle (OOS + çok-fold walk-forward + gerçek maliyet + geniş evren),
**tek dolar riske atmadan** bu yaklaşımın para kazandırmadığını KANITLADIK.

### Bundan sonra dürüst seçenekler
1. **Mevcut 4H swing SMP botunu aynı titizlikle test et.** ÖNEMLİ: o botun backtest'i
   `vectorbt`'ye bağlı ve vectorbt bu makinede kurulu DEĞİL → yani mevcut sistemin
   edge'i BU makinede hiç doğrulanmamış olabilir. Onu bu yeni event-engine ile
   OOS/walk-forward'dan geçirmek en yüksek değerli adım.
2. Farklı edge ailesi (daha uzun vadeli trend/momentum/carry) — ama her biri kendi
   titiz testini ister ve hiçbiri günlük %5 vaat etmez.
3. Hedefi tümden yeniden çerçevele: bu ölçekte piyasa ~verimli; odak "sihirli
   indikatör" değil, risk yönetimi + gerçekçi beklenti olmalı.

---

## 5.4 FAZ 2 — QUANT PİVOT: Trend-Takibi (doğrulandı ✅)

Retail indikatör-yığma bırakılıp quant mentaliteye geçildi (bkz. memory:
quant-mentality). Kripto'da en sağlam edge ailesi = **zaman-serisi momentum /
trend-takibi**. 9-coin sepetinde, **volatilite-hedefli boyutlandırma** ile,
walk-forward'dan geçirildi (`backtest/run_trend.py`, `backtest/trend_engine.py`,
`strategies/ts_momentum.py`).

**Günlük (1D), long-only, portföy:**
| Varyant | CAGR | Sharpe | MaxDD | WF pozitif fold |
|---|---|---|---|---|
| tsmom 30 LO | %15.8 | **0.78** | −31.6% | 4/5 |
| donchian 20/10 t100 LO | %10.5 | 0.65 | **−21.6%** | 2/5 |
| dualEMA 20/50 LO | %11.5 | 0.60 | −27.9% | 3/5 |

- Sharpe 0.6–0.78 = trend-takibi literatürünün beklediği aralık → **gerçek edge**.
- **Portföy Sharpe (0.78) > ortalama-coin Sharpe (0.54)** → çeşitlendirme kazancı
  kanıtlandı (asıl quant içgörüsü).
- Long-short < long-only → kripto trendini short'lamak kanatıyor.
- **Dürüst uyarı:** MaxDD %20–32; son fold negatif → trend-takibi kuraklık
  dönemlerinden geçer. Yılda ~%10–16 + drawdown'lar. "Günde %5" DEĞİL.

**Teslim edilen:** `pine/quant_trend_engine.pine` — Donchian breakout + EMA trend
filtresi + vol-hedef boyutlandırma + opsiyonel ATR trailing. TradingView'de
`strategy` olarak backtest edilebilir; alarmlarla tarayıcıya bağlanabilir.
**Kullanım:** 1D grafik, BTC/ETH/SOL/BNB/... sepetine ayrı ayrı uygula
(çeşitlendirme = edge'in kaynağı). Tek coinde Sharpe daha düşüktür.

## 5.5 QUANT ENGINE v2 — Round 1/2 bileşen testleri (disiplinli)

Kullanıcının 11-maddelik vizyonu, her biri baseline trend'e EKLENİP portföy
walk-forward'da sınandı (`backtest/run_quant.py`, `strategies/quant_engine.py`).
Kriter: baseline Sharpe (0.65) geçilmeli. Sadece geçen tutuldu.

| Bileşen | CAGR | Sharpe | MaxDD | Karar |
|---|---|---|---|---|
| BASELINE trend (donchian LO) | %10.4 | 0.65 | −21.6% | — |
| **+rejim ER>0.40** | %10.1 | **1.15** | **−11.4%** | ✅ **YILDIZ** (aynı getiri, ½ DD) |
| +rejim ER>0.30 | %10.2 | 0.90 | −19.0% | ✅ |
| +MACD onay | %12.6 | 0.90 | −19.8% | ✅ mütevazı |
| +Hacim onay | %10.6 | 0.90 | −12.0% | ✅ mütevazı |
| ER040+MACD+Hacim | %6.5 | 0.98 | −8.2% | ✅ (DD↓ ama getiri↓, Sharpe ER040 altı) |
| adaptif MR (yatay) | %10.3 | 0.62 | −26.2% | ❌ |
| +ADX>20, +RSI, +VWAP | ≤0.70 | — | — | ❌/marjinal |

**Sonuç:** #1 (rejim adaptasyonu) net kazanan — **efficiency ratio > 0.40** filtresi
Sharpe'ı 0.65→1.15, DD'yi yarıya indirdi (aynı getiri). Pine'a eklendi
(`pine/quant_trend_engine.pine`, `useRegime`). MACD/Hacim = edge değil risk
düğmesi. MR/ADX/RSI/VWAP yerini hak etmedi.

**Dürüst uyarı:** TÜM config'lerde son walk-forward fold'u (2025→2026) sert
negatif → kripto trend-takibi yakın dönem kuraklıkta; rejim filtresi geçmişi
düzeltir ama kuraklığı çözmez. Round 3 adayları: kesitsel varlık seçimi (#5) +
"hiçbir şey trend yapmıyorsa nakde geç" risk-off rejimi.

## 5.6 Round 3 — kesitsel seçim + risk-off (`backtest/run_quant_xs.py`)

| Config | CAGR | Sharpe | MaxDD | F5 (kuraklık) | Karar |
|---|---|---|---|---|---|
| ER040 (Round 2) | %10.1 | 1.15 | −11.4% | −3.25 | — |
| XS top-5/3/2 momentum (#5) | düşer | düşer | düşer | — | ❌ hak etmedi |
| **risk-off breadth>0.33** | **%10.7** | **1.32** | **−6.6%** | **−1.10** | ✅ **YILDIZ** |

- **#5 kesitsel seçim geçmedi:** yoğunlaşma getiriyi düşürdü (kripto'da TS-mom > XS-mom).
- **breadth risk-off geçti:** "coinlerin <%33'ü trend yapıyorsa nakde geç" → Sharpe
  1.32, DD %6.6, ve yakın dönem kuraklık fold'unu −3.25→−1.10 iyileştirdi.

### VALİDE MOTOR (nihai stack)
`trend (Donchian LO + EMA) → +ER>0.40 rejim filtresi (per-coin) → +breadth
risk-off (portföy)` = **Sharpe ~1.32, CAGR ~%10.7, MaxDD ~%6.6, 4/5 fold poz.**

### Compounding içgörüsü (dürüst)
Sharpe 0.65→1.32'ye ÇIKMASININ asıl anlamı: **aynı drawdown bütçesinde getiriyi
~2x'leyebilirsin** (targetVol'u yükselterek). Yani "daha hızlı bileşik" = daha çok
işlem DEĞİL (o maliyeti çarpar), **daha yüksek Sharpe + risk düğmesini açmak.**
Örn. targetVol 0.40→0.80: ~%21 CAGR / ~%13 DD (Sharpe sabit).

### Mimari ayrımı
- **Pine (per-symbol):** trend + ER rejim filtresi + vol-sizing → per-coin sinyal. ✅ eklendi.
- **Bot (portföy):** breadth risk-off + sepet yönetimi. Pine tek sembol gördüğü için
  breadth doğal olarak TARAYICI BOTA ait (tüm evreni görür).

## 5.7 TF taraması — "kısa zaman dilimine optimize et" DÜRÜST testi (`backtest/run_tf_sweep.py`)

Valide motor (trend + ER rejim), 1d→15m, her TF'de 4 param varyantıyla re-tune,
gerçek maliyet, walk-forward. 5 major coin.

| TF | En iyi Sharpe | CAGR | MaxDD | Poz. fold |
|---|---|---|---|---|
| **1d** | **1.68** | +%13.1 | −5.7% | 5/5 |
| 4h | 0.51 | +%3.9 | −9.7% | 3/5 |
| 1h | −1.17 | −%5.5 | — | kayıp |
| 30m | −2.88 | −%14.6 | — | kayıp |
| 15m | −5.76→−12 | −%29..−62 | — | 0/5 |

→ **Kısa TF KESİN olarak kayıp** (monoton çöküş; 15m param ne olursa olsun 90g'de
%60 kayıp). Neden değişmez: gürültü + maliyet drag'i. Kısa-TF sorusu tüm spektrumda
kapandı.

→ **BONUS — optimizasyon günlükte daha iyi config buldu:** `donch 55/20 + ER 0.50 +
trend200` = **Sharpe 1.68, CAGR %13.1, MaxDD %5.7, 5/5 fold pozitif** (kuraklık
fold'u bile +0.97). Önceki en iyiden (1.32) daha iyi ve daha sağlam → **motorun yeni
varsayılan günlük paramları bu olmalı.**

## 5.8 SMP motoru testi + quant birleşimi + düşük TF (`backtest/run_smp.py`)

SMP pipeline (compute_all_indicators→score→trigger→signals→filters, mtf=None)
sinyalleri pozisyona çevrilip vol-target engine + walk-forward'dan geçti.

| TF | Config | Sharpe | MaxDD | Not |
|---|---|---|---|---|
| 4h | QUANT trend+ER (ref) | **+0.36** | −3.6% | — |
| 4h | SMP long/flat | −0.15 | −36.7% | edge yok |
| 4h | SMP + ER rejim (birleşik) | −0.26 | −6.7% | DD↓ ama negatif |
| 1h/30m | SMP tüm varyantlar | ≤+0.28 | yüksek | gürültü, küçük örneklem |

**Sonuç:** (1) SMP'nin 4H'te bile pozitif edge'i yok — quant motoru onu yeniyor.
(2) ER rejim ile birleştirmek negatifliği düzeltmiyor. (3) Düşük TF'de SMP de
negatif/gürültü. Çekince: MTF modülü kapalıydı (data ağır). Tek robust pozitif
sistem: **quant GÜNLÜK trend+ER motoru (Sharpe 1.68).**

## 5.9 İntraday derin araştırma + VWAP-MR + funding (Adım 3-7)

Araştırma: başarılı kripto = market-maker/arbitraj (Wintermute/Jump/GSR), yön
tahmini DEĞİL; retail'e açık gerçek edge = funding/carry arbitrajı. Day trader
istatistiği: ~%1 uzun-vade kârlı, %97 komisyon sonrası günlük kaybeder, başaran
azınlık ayda %1-4. Belgelenmiş intraday edge = VWAP sapması + funding + likidasyon.

Test (`backtest/run_vwap_mr.py`): anchored-VWAP + SD bant MR.
| Config | 1h maker | 30m maker |
|---|---|---|
| Ham VWAP MR | −%26 | −%12 |
| **+funding filtresi** | −%5 | **+%5.8 / Sharpe 0.50 / DD %5** |
| +sweep proxy | çok kötü | çok kötü |

**Sonuç:** funding filtresi tek gerçek değer katan bileşen (araştırmayı doğruladı).
En iyi intraday: 30m VWAP-MR+funding, SADECE maker → Sharpe ~0.50 (zayıf, kırılgan,
küçük örneklem, taker'la çöker). Coin-coin hiçbiri robust değil; yüksek-vol alt'lar
daha kötü. → İntraday tavanı ~Sharpe 0.5 maker-bağımlı; günlük motor (1.68) kat kat
üstün. Retail'in gerçek gün-içi-alternatifi olabilecek tek şey: funding/carry arb (henüz test edilmedi).

---

## 6. Sonraki Adım (karar noktaları)

1. **Çekirdek setup:** Önce A (MSS Sweep Fib) mi, B (True OB) mi, yoksa ikisi
   yarışsın mı?
2. **Öncelik piyasa:** Kripto intraday mı, yoksa mevcut BIST/4H üstüne mi
   inşa edelim?
3. Onay gelince Faz 1 kodlamasına (backtest) başlıyoruz; kriterleri geçen
   kurulum Faz 2'de indikatöre/bota işlenir.
