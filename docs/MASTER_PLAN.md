# E-Ticaret Agent Orkestrasyonu — Master Plan

## Proje Özeti

Türkiye pazarında (Trendyol + Shopify) dropshipping/stok tabanlı e-ticaret operasyonunu tam otomatize eden, 7-agent Claude tabanlı sistem. Supabase merkezi veri katmanı, Railway cron altyapısı, Google Sheets insan-kontrol noktası.

**GitHub:** `github-personal:savciozenberkin/eticaret-otomasyon`  
**Sahip:** Berkin Savcıözen (kişisel proje — Dataroid'den bağımsız)

---

## Sistem Mimarisi

```
┌─────────────────────────────────────────────────────────────┐
│                    BERKIN (İnsan Kontrol)                    │
│              Google Sheets Onay Panosu (5 sheet)             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │ Orkestratör │  ← Pipeline koordinatörü
                    │  */30 cron  │    Sheet↔Supabase sync
                    └──────┬──────┘    Hata yönetimi
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼────┐      ┌─────▼─────┐    ┌──────▼──────┐
    │Fırsatçı │      │Tedarikçi  │    │  Listeleme  │
    │0 6,18   │      │0 * * * *  │    │  (M5+)      │
    │* * *    │      │(saatte 1) │    └──────┬───────┘
    └────┬────┘      └─────┬─────┘           │
         │                 │         ┌────────┴────────┐
         │ (onay)          │ (sourced)│                │
         └─────────────────┘    ┌────▼────┐    ┌──────▼──────┐
                                │Pazarlama│    │   Sipariş   │
                                │  (M6+)  │    │   (M5+)     │
                                └────┬────┘    └──────┬──────┘
                                     │                │
                                     └───────┬─────────┘
                                             │
                                       ┌─────▼──────┐
                                       │   Finans   │
                                       │   (M5+)    │
                                       └────────────┘
```

## Veri Akışı

Agentlar birbirini **doğrudan çağırmaz** — Supabase tabloları üzerinden iletişir:

```
Fırsatçı → approval_queue (pending)
Orkestratör → products (approved) — Sheets onayı sonrası
Tedarikçi → supplier_contacts (research_found → sent)
Orkestratör → sheets mirror (her 30 dk)
```

---

## Milestone Geçmişi

### M1 — Temel Altyapı ✅
- Supabase şeması (8 tablo)
- Orkestratör Agent kurulumu
- Railway cron altyapısı
- Gmail OAuth
- Google Sheets onay panosu (temel)

### M2 — Mock Pipeline ✅
- Fırsatçı Agent — pytrends + Claude Haiku scoring
- Tedarikçi Agent — mock supplier araştırması
- Approval loop (Sheet → Supabase → Sheet)

### M3 — E2E Mock + Optimizasyon ✅
- Fırsatçı M3-complete (Opt-3 + Opt-4 uygulandı)
- 5-sheet mimarisi tamamlandı
- Dropdown validasyonlar kuruldu
- `sheets_client.py` status mapping düzeltmeleri (commit `ad07e61`)

### M4 — Gerçek Mail Pipeline ✅ (Haziran 2026)
- Tedarikçi M4-complete — gerçek mail E2E test başarılı
- TM-ID sistemi (test/gerçek mail ayrımı)
- 4-aşamalı pipeline (research_found → approved → sent → followup_sent)
- Gmail reply okuma + TM-ID eşleme
- Orkestratör defensive error handling (commit `19aa437`)

### M5 — Şirket Kurma + Marketplace (Temmuz 2026) 🔄
Beklenen sıra:
1. Şahıs şirketi kaydı (aile üyesi adına)
2. Shopify mağazası aç + API key al
3. Trendyol başvurusu yap (3-7 iş günü)
4. iyzico + kargo hesapları
5. Listeleme Agent devreye al
6. Sipariş Agent devreye al
7. Finans Agent devreye al

### M6 — Canlı Satış (Ağustos 2026) ⏳
- İlk canlı sipariş
- Kargo etiketi otomasyonu
- P&L raporlama
- Pazarlama Agent — Trendyol Sponsored

---

## Kritik Tarihler

| Tarih | Olay | Etki |
|-------|------|------|
| **10 Ağustos 2026** | Trendyol V1 API kapanıyor | `siparis.py` + `listeleme.py` V3'e geçmeli |
| Her 7 gün | Gmail OAuth token expire | Google Cloud'u Production'a al (kalıcı fix) |
| M5 öncesi | Railway trial sona eriyor | Hobby plan al ($5/ay) |

---

## Teknik Stack

| Katman | Teknoloji |
|--------|-----------|
| Agent runtime | Python 3.12 (Railway) |
| AI model | Claude Haiku 4.5 (scoring + mail) |
| Veritabanı | Supabase PostgreSQL (Singapore) |
| Cron altyapısı | Railway Cron Jobs |
| İnsan kontrol | Google Sheets (5-sheet) |
| Mail | Gmail OAuth 2.0 |
| E-ticaret | Shopify Admin API + Trendyol Seller API V3 |
| Kargo | Yurtiçi Kargo API + MNG (yedek) |
| Ödeme | iyzico / PayTR |
| Reklam (M6+) | Trendyol Sponsored + Meta + Google Ads |

---

## Güvenlik Kuralları (KRİTİK)

1. **`.env` hiçbir zaman commit edilmez** — `.gitignore`'da tanımlı
2. **Gerçek credential'lar sadece Bitwarden'de** — vault/docs'ta sadece durum takibi
3. **`SUPABASE_SERVICE_ROLE_KEY` sadece Orkestratör'e** — diğer tüm agentlar `ANON_KEY` kullanır
4. **TM-ID sadece test mail subject'inde** — gerçek tedarikçi mailine ASLA girmez
5. **`MOCK_SUPPLIER_EMAIL=berkinsavciozen@gmail.com`** — test mailleri bu adrese, gerçek tedarikçiye değil

---

## Aylık Maliyet Tahmini

| Kalem | Miktar |
|-------|--------|
| Railway (Hobby) | $5 |
| Anthropic API | ~$5-15 |
| Supabase (Free) | $0 (M6+ Pro: $25) |
| Shopify (Basic) | $29 |
| Toplam (M5) | ~$40-50 |
| Toplam (M6) | ~$65-75 + reklam bütçesi |

---

## Hesap Sahipliği

| Hesap | Kimin Adına |
|-------|-------------|
| Supabase, Anthropic, Google Cloud, Railway | Berkin'in kişisel Gmail |
| Trendyol, Shopify, iyzico, Kargo | Aile üyesinin adına (şirket zorunluluğu) |

---

## Dökümantasyon Yapısı

Tüm docs `docs/` klasöründe — detay için `docs/README.md`.
