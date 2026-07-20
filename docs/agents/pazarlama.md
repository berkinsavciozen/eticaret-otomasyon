# Pazarlama Agent

**Durum:** 🔲 Planlandı (M6)  
**Schedule:** Event-driven (yeni listeleme) + haftalık performans analizi  
**Aylık maliyet (tahmini):** $4.00

## Rol

Listelenen ürünler için reklam içeriği üretir, Trendyol Sponsored kampanya yönetir, performans verisiyle optimize eder. Her harcama kararı Berkin'in onayına tabi. Meta/Google reklamları M6+ planlandı.

## Bağımlılıklar

- **Başlamadan önce gerekli:** Listeleme Agent aktif, ilk ürün listed durumda
- **M6+ için:** Meta Business hesabı + Google Ads hesabı

## ROAS Eşik Kuralları

| Durum | Eşik | Aksiyon |
|-------|------|---------|
| Yüksek performans | ROAS ≥ 3.0 | approval_queue → bütçe artırma önerisi |
| Normal | 1.0 ≤ ROAS < 3.0 | İzle, haftalık rapor |
| Düşük (3 gün üst üste) | ROAS < 1.0 | approval_queue → kampanya durdurma önerisi |

**Hedef ROAS:** 2.5x  
**Aylık reklam bütçesi:** 500 TL başlangıç

## Çalışma Akışı (Planlandı)

```
Event: products.status = 'listed' TETİK
  → _generate_ad_content(): Claude → başlık (2 A/B) + Trendyol Sponsored copy
  → approval_queue: kampanya başlatma talebi
  → Berkin onayı → Trendyol Sponsored kampanya oluştur
  → ad_campaigns tablosuna kayıt

Haftalık:
  → Tüm aktif kampanya metriklerini çek (gösterim, tıklama, ROAS)
  → ROAS eşik kontrolü → gerekiyorsa approval_queue'ya öneri
  → Haftalık performans raporu → Orkestratör'e
```

## İçerik Üretim Standartları

| Tür | Format | A/B |
|-----|--------|-----|
| Trendyol Sponsored başlık | ≤60 karakter, güçlü keyword öne | 2 varyasyon |
| Shopify ürün başlığı | SEO optimizasyonlu, benefit-first | 2 varyasyon |
| Meta reklam kopyası (M6+) | Hook + özellik + CTA, ≤125 karakter | 3 varyasyon |

## Admin Kontrol Noktaları

| Adım | Tetikleyici | Timeout |
|------|-------------|---------|
| Kampanya başlatma | Her listed ürün | 12 saat |
| Bütçe artırma | ROAS ≥ 3.0 | 24 saat |
| Kampanya durdurma | ROAS ≤ 1.0 (3 gün) | 6 saat |
| A/B test başlatma | Yeni varyasyon önerisi | 24 saat |
| Meta/Google etkinleştirme | M6 aşaması | — |

## Credentials

| Env Var | Aşama |
|---------|-------|
| `TRENDYOL_SUPPLIER_ID` + API creds | M5 |
| `SHOPIFY_API_KEY` | M5 |
| `ANTHROPIC_API_KEY` | M5 |
| `SUPABASE_URL` + `SUPABASE_ANON_KEY` | M5 |
| `META_APP_ID` + `META_APP_SECRET` + `META_ACCESS_TOKEN` + `META_AD_ACCOUNT_ID` | M6+ |
| `GOOGLE_ADS_DEVELOPER_TOKEN` + `GOOGLE_ADS_CLIENT_ID/SECRET/REFRESH/CUSTOMER_ID` | M6+ |

## Başarı Metrikleri

| Metrik | Ay 1 | Ay 3 | Ay 6 |
|--------|------|------|------|
| Aktif Trendyol Sponsored | ≥1 | ≥5 | ≥15 |
| Ortalama ROAS | — | >2x | >3x |
| Trendyol CTR | — | >%1.5 | >%2 |
| Reklam gideri / ciro | — | <%8 | <%6 |
