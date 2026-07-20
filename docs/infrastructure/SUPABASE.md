# Supabase — Altyapı Referansı

**Proje:** `ypusjrrklxssjvefkypd`  
**Bölge:** ap-southeast-1 (Singapore)  
**Tier:** Free (500MB limit — tahmini kullanım Ay 6: ~50MB)  
**Pro geçiş önerisi:** M5-M6 arası ($25/ay)

## Bağlantı

| Credential | Nerede | Kullanım |
|------------|--------|----------|
| `SUPABASE_URL` | Bitwarden: E-Ticaret - Supabase | Tüm agentlar |
| `SUPABASE_ANON_KEY` | Bitwarden: E-Ticaret - Supabase | Fırsatçı, Tedarikçi, Listeleme, Sipariş, Finans, Pazarlama |
| `SUPABASE_SERVICE_ROLE_KEY` | Bitwarden: E-Ticaret - Supabase | ⚠️ SADECE Orkestratör |

> `SERVICE_ROLE_KEY` RLS'yi bypass eder. Hiçbir zaman frontend veya diğer agentlara verilmez.

## RLS Durumu

**Güvenlik açığı:** Tüm tablolar public erişime açık (`rls_disabled_in_public`).

Etkinleştirmek için SQL Editor'de çalıştır:

```sql
ALTER TABLE agent_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE financials ENABLE ROW LEVEL SECURITY;
ALTER TABLE preferred_suppliers ENABLE ROW LEVEL SECURITY;
ALTER TABLE ad_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_contacts ENABLE ROW LEVEL SECURITY;
```

**Not:** RLS etkinleştirmek agentları kırmaz — tüm agentlar `SERVICE_ROLE_KEY` kullanır ve bu key RLS'yi otomatik bypass eder.

## Tablolar

### `agent_tasks` — Pipeline görev kuyruğu

| Alan | Tür | Açıklama |
|------|-----|---------|
| `id` | uuid PK | — |
| `agent_name` | text | `firsatci` / `tedarikci` / vb. |
| `task_type` | text | `scan_trends` / `restock` / `list_product` |
| `payload` | jsonb | Göreve özel veri |
| `status` | text | `pending` / `in_progress` / `done` / `failed` |
| `retry_count` | int | default 0 |
| `created_by` | text | Oluşturan agent adı |
| `created_at` | timestamp | — |
| `started_at` / `completed_at` | timestamp | — |
| `error_message` | text | Hata detayı |

### `approval_queue` — İnsan onay kuyruğu

| Alan | Tür | Açıklama |
|------|-----|---------|
| `id` | uuid PK | — |
| `request_type` | text | `product_approval` / `proforma` / `listing_content` / `ad_campaign` / `return` / `anomaly` |
| `agent_source` | text | Talep eden agent |
| `title` | text | Sheets'te görünür başlık |
| `summary` | text | Özet açıklama |
| `payload` | jsonb | Detay veri |
| `status` | text | `pending` / `approved` / `rejected` |
| `timeout_hours` | int | Hatırlatma eşiği (default 48) |
| `created_at` / `reviewed_at` | timestamp | — |

### `agent_logs` — Çalışma günlüğü

| Alan | Tür | Açıklama |
|------|-----|---------|
| `agent_name` | text | — |
| `run_type` | text | `cron` / `event` / `retry` |
| `status` | text | `success` / `failed` / `partial` |
| `items_processed` / `items_success` / `items_failed` | int | — |
| `duration_ms` | int | Çalışma süresi |
| `metadata` | jsonb | Agent'a özel ek bilgi |

### `products` — Ürün yaşam döngüsü

Status akışı: `candidate → approved → sourcing → sourced → listed → delisted`

Önemli alanlar: `score`, `cogs_tl`, `target_price_tl`, `supplier_id`, `stock_count`, `critical_stock_threshold` (default 5), `shopify_product_id`, `trendyol_barcode`

### `supplier_contacts` — Tedarikçi iletişim geçmişi

Status akışı: `research_found → approved → sent → followup_sent`

Önemli alanlar: `tm_id` (TM-001 formatı), `supplier_name`, `contact_email`, `email_body`, `contacted_at`

> **M5+ TOKEN OPT-1:** `email_body` kolonu eklenecek — bir kez üretilen mail body cache'lenecek.

### `orders` — Sipariş kayıtları

Status: `new → shipped → delivered` / `return_requested → returned`

### `financials` — Gelir/gider kayıtları

`amount_tl`: gelir pozitif, gider negatif. `category` alanı için değerler: `gelir_shopify`, `gelir_trendyol`, `cogs`, `komisyon_trendyol`, `kargo`, `reklam`, `sabit_gider`, `banka_hareketi`, `kdv_yukumlulugu`

### `preferred_suppliers` — Başarılı tedarikçi hafızası (M5+)

### `ad_campaigns` — Reklam kampanya takibi (M6+)

## Pending M5+ Migration

```sql
-- Token Opt-1: email body caching
ALTER TABLE supplier_contacts
  ADD COLUMN IF NOT EXISTS email_body TEXT;
```
