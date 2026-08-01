# SMP + Trend — Oto-Trade Mimarisi

Doğrulanmış çekirdeğin (SMP no-RSI + Trend, Sharpe **1.36**, 2x ≈ %20 CAGR / −%8 DD; carry hariç — serap) canlıya taşınma iskeleti. **Paper şimdi çalışır; canlı borsa icrasını sen doldurursun.**

## Görev bölümü
| Katman | Kim | Dosya |
|---|---|---|
| Sinyal / risk / sizing / state / paper-sim | **Ben** | `core.py`, `state.py`, `validate.py`, `executor.py` |
| Exchange API + imza + key güvenliği + gerçek icra | **Sen** | `core.LiveBroker` (stub) |

## Veri akışı (katmanlar)
```
1 VERI      binance.vision OHLCV — 4H (SMP) + 1D (Trend)   [data/crypto_fetcher.py]
   │
2 SINYAL    SMP no-RSI · A+ Only · ER>0.15 · 30 coin  -> discrete trade (entry/SL/TP)
            Trend: Donchian 55/20 LO · ER>0.50 · vol-hedefli sürekli pozisyon
   │
3 RISK/SIZE SMP: fixed-fractional risk_pct=%3 (1x) · max 5 eş zamanlı · sleeve %70
            Trend: vol-target %10 · sleeve %30 · ölçek 1x→2x
   │
4 EXECUTION Broker ABC:  PaperBroker (şimdi)  |  LiveBroker (sen: Binance USD-M)
            SMP -> market entry + OCO(SL+TP)   Trend -> market rebalance
   │
5 STATE     state.json (equity, açık poz, geçmiş, eğri) — Actions her döngü commit
   │
6 MONITOR   Telegram (giriş/çıkış/özet) + kill-switch (gün −%8 / DD −%20)
```

## Sizing kuralları (kilitli, A/B/C'den)
- **SMP**: her işlem `risk_pct × scale × equity` riске atar. `qty = risk$ / |entry−SL|`. En çok **5** eş zamanlı; slot doluysa sinyal atlanır.
- **Trend**: `hedef_notional = %30 × equity × (%10 × scale / coin_yıllık_vol)`.
- **Ölçek**: 1x başla. Canlıda ≥3 ay tutarlıysa 1.5x, sonra 2x. Kaldıraç = risk% (sihir değil).

## Dağıtım (GitHub Actions)
- Cron 4H → `executor.py` bir cycle koşar (stateless) → `state.json`'ı okur/yazar/commit'ler.
- `permissions: contents: write` + commit-push adımı state'i kalıcı yapar (audit izi).
- Telegram: `LAB_BOT_TOKEN` / `LAB_CHAT_ID` secret (canlı SMP botundan **ayrı**).

## Canlıya geçiş yol haritası
1. **Paper** (şimdi): `executor.py` PaperBroker ile, $100 sanal. Eğriyi izle.
2. **Doğrula**: `validate.py` — paylaşımlı-sermaye backtest, canlı mantığın aynısı.
3. **LiveBroker** (sen): Binance USD-M futures. Key → Actions Secret, borsada **withdraw KAPALI + IP-whitelist + sadece futures-trade**. İmzalı istek (HMAC-SHA256). OCO emirleri.
4. **Minik canlı**: $50–100, 1x. Paper eğrisiyle tutuyor mu?
5. **Ölçekle**: kanıtlanınca sermaye + ölçek artır.

## Dürüstlük / riskler
- Rakamlar **backtest** (tek rejim, survivor coin, kripto primi). Canlıda slippage + icra + rejim değişimi **haircut** yapar. Gerçekçi sürdürülebilir ~%20–40/yıl; en iyi CTA fonları %8–12/yıl.
- **Kill-switch şart**: gün −%8 veya DD −%20 → yeni giriş yok / açıkları kapat.
- Carry dahil değil (funding-only Sharpe serap + ters-vol onu şişirir). Canlı basis/likidasyon izlemesi kurulursa küçük sabit dilim olarak eklenebilir.

## Dosyalar
- `core.py` — konfig, `Position`, `Broker`/`PaperBroker`/`LiveBroker`, `smp_size`/`trend_size`
- `state.py` — JSON kalıcılık (`load`/`save`/`broker_from_state`)
- `validate.py` — mimari doğrulayıcı (paylaşımlı havuz, gerçek eğri) → `python live/validate.py`
- `executor.py` — canlı döngü (paper) → `python live/executor.py`
