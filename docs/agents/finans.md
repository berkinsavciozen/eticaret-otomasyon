# Finans Agent

**Durum:** 🔲 Planlandı (M5)  
**Schedule:** Haftalık Pazar 22:00 (tam analiz) + aylık P&L (ayın son günü)  
**Aylık maliyet (tahmini):** $1.00

## Rol

E-ticaret gelirini takip eder, giderleri kategorize eder, aylık P&L üretir, vergi hazırlığını muhasebeciye iletir. Tek manuel girdi banka hareketleri — her şey otomatik.

## Veri Kaynakları

| Kaynak | Ne | Sıklık |
|--------|----|----|
| `orders` tablosu | Haftalık sipariş + gelir | Haftalık |
| Shopify Payouts API | Platform tahsilat raporu | Haftalık |
| Trendyol Finance API | 14 günlük ödeme raporu | Haftalık |
| Google Sheets (manuel) | Banka hareketi girişleri | Berkin haftalık ~5-10dk |
| `ad_campaigns` tablosu | Haftalık reklam gideri | Haftalık |
| `products` tablosu | COGS ve ürün bazlı veri | Aylık |

## Gelir Kategorileri (`financials` tablosu)

| Kategori | Kaynak | Otomatik mi |
|----------|--------|-------------|
| `gelir_shopify` | Shopify Payouts API | ✅ |
| `gelir_trendyol` | Trendyol Finance API | ✅ |
| `cogs` | products.cogs_tl × sipariş adedi | ✅ |
| `komisyon_trendyol` | Trendyol Finance API | ✅ |
| `kargo` | orders.shipping_cost_tl | ✅ |
| `reklam` | ad_campaigns.total_spend_tl | ✅ |
| `sabit_gider` | Manuel (Shopify abonelik, API, muhasebe) | ❌ Manuel |
| `banka_hareketi` | Google Sheets | ❌ Manuel |
| `kdv_yukumlulugu` | Gelir × %20 | ✅ |

## Admin Kontrol Noktaları

| Adım | Sıklık |
|------|--------|
| Banka hareketi girişi (Google Sheets) | Haftalık ~5-10 dk |
| Aylık P&L incelemesi | Her ayın sonu |
| Anomali bildirimi (±%30 sapma) | Anlık (approval_queue) |
| KDV beyan hazırlığı onayı | Beyan tarihinden 3 gün önce |

## Manuel Banka Girişi Format (Google Sheets)

| Sütun | Örnek |
|-------|-------|
| Tarih | 2026-06-09 |
| Tutar | 1200.00 (pozitif=giriş, negatif=çıkış) |
| Açıklama | "Trendyol ödeme — 26-31 Mayıs" |
| Kategori | gelir / gider / vergi / diger |

## Feedback Loops

```
Ürün marjı < %15 → Tedarikçi Agent için müzakere görevi
Reklam gideri > bütçe → Pazarlama Agent için kampanya duraklat
Aylık P&L → Orkestratör haftalık raporuna eklenir
```

## Credentials (M5'te gerekli)

| Env Var |
|---------|
| `SHOPIFY_API_KEY` |
| `TRENDYOL_SUPPLIER_ID` + `TRENDYOL_API_KEY` + `TRENDYOL_API_SECRET` |
| `GMAIL_REFRESH_TOKEN` + `GMAIL_CLIENT_ID` + `GMAIL_CLIENT_SECRET` |
| `SHEETS_BANK_ENTRY_ID` |
| `SUPABASE_URL` + `SUPABASE_ANON_KEY` |
| `ANTHROPIC_API_KEY` |

## Başarı Metrikleri

| Metrik | Ay 1 | Ay 3 |
|--------|------|------|
| İlk P&L raporu | ✓ | — |
| Gelir kategorizasyon doğruluğu | >%90 | >%97 |
| Aylık P&L üretim süresi | <60 dk | <30 dk |
| KDV beyan hazırlığı zamanında | %100 | %100 |
