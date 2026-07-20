# Sipariş Agent

**Durum:** 🔲 Planlandı (M5)  
**Schedule:** Her 30 dakika polling + event-driven (iade, stok kritik)  
**Aylık maliyet (tahmini):** $1.50

## Rol

Shopify ve Trendyol'daki siparişleri otomatik işler: kargo etiketi oluşturur, stok günceller, kritik stok seviyesinde tedarik döngüsünü başlatır, iade taleplerini yönetir.

## Çalışma Akışı (Planlandı)

```
30 dakika polling:
  1. Shopify/Trendyol → yeni siparişleri çek
  2. orders tablosuna kaydet
  3. Kargo etiketi oluştur (Yurtiçi API)
  4. Tracking numarasını platforma bildir (Shopify + Trendyol)
  5. products.stock_count -= sipariş adedi
  6. stock_count ≤ 3 → agent_tasks'a Tedarikçi yeniden sipariş görevi
  7. 18:00 → günlük özet logu

Event: iade talebi:
  → orders.status = 'return_requested'
  → approval_queue kaydı (ürün, tutar, gerekçe)
  → Gmail bildirimi → Berkin
  → Berkin onayı/reddi → müşteriye iletilir
```

## Kritik Uyarı

**Trendyol V1 API 10 Ağustos 2026'da kapanıyor.**  
`_fetch_trendyol_orders()` V3 endpoint'i kullanmalı: `getShipmentPackages`

> M4'te `_fetch_shopify_orders()` ve `_fetch_trendyol_orders()` TODO — boş döndürüyor.

## Stok Yenileme Tetikleyicisi

- Kritik eşik: `products.critical_stock_threshold` (default: 5 adet)
- Trigger: `stock_count ≤ critical_stock_threshold`
- Aksiyon: `agent_tasks`'a `task_type=restock`, `agent_name=tedarikci` yazılır

## İade Oranı Sinyali

- İade oranı >%8 → `agent_tasks`'a Fırsatçı için sinyal
- Fırsatçı o kategoriyi kara listeye ekler

## Sipariş Durum Akışı

```
new → (kargo etiketi) → shipped → (teslim) → delivered
 └→ return_requested → (Berkin onayı) → returned
```

## Credentials (M5'te gerekli)

| Env Var |
|---------|
| `SHOPIFY_API_KEY` |
| `TRENDYOL_SUPPLIER_ID` + `TRENDYOL_API_KEY` + `TRENDYOL_API_SECRET` |
| `YURTICI_USERNAME` + `YURTICI_PASSWORD` + `YURTICI_CUSTOMER_NO` |
| `MNG_USERNAME` + `MNG_PASSWORD` (yedek kargo) |
| `GMAIL_REFRESH_TOKEN` (kargo gecikme + iade bildirimi) |
| `SUPABASE_URL` + `SUPABASE_ANON_KEY` |

## Başarı Metrikleri

| Metrik | Ay 1 | Ay 3 |
|--------|------|------|
| Sipariş → kargo süresi | <2 saat | <1 saat |
| İade oranı | <%8 | <%5 |
| Stok tutarsızlığı (platform ↔ Supabase) | <%3 | <%1 |
