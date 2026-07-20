# Listeleme Agent

**Durum:** 🔲 Planlandı (M5)  
**Railway servisi:** Henüz yok  
**Schedule:** Event-driven (yeni ürün) + 30dk polling (stok sync)  
**Aylık maliyet (tahmini):** $2.50

## Rol

Tedarikçi'nin onayladığı ve fiziksel stokta olan ürünleri Shopify ve Trendyol'a otomatik yükler. SEO optimizasyonlu içerik üretir, stok ve fiyat senkronizasyonunu sürekli tutar.

## Bağımlılıklar

- **Başlamadan önce gerekli:** Shopify hesabı + API key, Trendyol satıcı hesabı + Supplier ID
- **Tetikleyen:** Tedarikçi Agent → `products.status = sourced`

## Çalışma Akışı (Planlandı)

```
Event: products.status = 'sourced' TETİK
  └─ _generate_listing_content()   Claude Sonnet → SEO başlık + açıklama (2 A/B varyasyon)
  └─ _approval_check()            İlk 3 ürün için approval_queue'ya içerik onayı
  └─ _list_on_shopify()           Shopify Admin API → ürün oluştur
  └─ _list_on_trendyol()          Trendyol Seller API V3 → ürün yükle
  └─ products.status = 'listed'   + shopify_product_id + trendyol_barcode kaydet

Polling: 30 dakika
  └─ _sync_stock()                Platform ↔ Supabase stok karşılaştır + güncelle
```

> ⚠️ M4'te hem `_list_on_shopify()` hem `_list_on_trendyol()` TODO — boş string döndürüyor.

## Kritik Uyarı

**Trendyol V1 API 10 Ağustos 2026'da kapanıyor.**  
Tüm geliştirme Trendyol V3 API üzerinden yapılmalı: `https://apigw.trendyol.com`

## Trendyol V3 Endpoint Referansı

| İşlem | Endpoint | Method |
|-------|----------|--------|
| Ürün yükleme | `/sapigw/suppliers/{supplierId}/v2/products` | POST |
| Stok/fiyat güncelleme | `/sapigw/suppliers/{supplierId}/products/price-and-inventory` | POST |

## İçerik Üretim Standartları

| Alan | Format |
|------|--------|
| Başlık | `[Marka] [Ürün Adı] [Ana Özellik] [Boyut/Renk]` |
| Açıklama | 3 paragraf: özellikler · kullanım · bakım |
| Etiketler | 5-8 anahtar kelime |
| A/B | 2 farklı başlık — Pazarlama Agent test eder |

## Admin Kontrol Noktaları

| Tetikleyici | Aksiyon |
|-------------|---------|
| İlk 3 ürün içerik onayı | approval_queue'da incele + onayla |
| Yeni kategori — ilk ürün | Trendyol/Shopify kategori ID doğrula |
| Stok uyuşmazlığı >2 adet | Elle doğrula + sync düzelt |

## Credentials (M5'te gerekli)

| Env Var |
|---------|
| `SHOPIFY_API_KEY` |
| `SHOPIFY_API_SECRET` |
| `SHOPIFY_STORE_URL` |
| `TRENDYOL_SUPPLIER_ID` |
| `TRENDYOL_API_KEY` |
| `TRENDYOL_API_SECRET` |
| `SUPABASE_URL` |
| `SUPABASE_ANON_KEY` |
| `ANTHROPIC_API_KEY` |

## Başarı Metrikleri

| Metrik | Ay 1 | Ay 3 | Ay 6 |
|--------|------|------|------|
| Her iki platformda listelenen ürün | ≥5 | ≥20 | ≥50 |
| sourced → listed süresi | <2 saat | <1 saat | <30 dk |
| Trendyol listeleme kalite skoru | >60 | >70 | >80 |
