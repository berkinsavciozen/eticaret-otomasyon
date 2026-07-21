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

✅ RLS 9 tabloda etkinleştirildi (21 Temmuz 2026).

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

> **GAP-8 notu:** `delisted` artık iki anlamda kullanılıyor: (1) orijinal
> anlamı — aktif bir listing durdurulduğunda; (2) Berkin bir ürün onayını
> Sheet 1'de sonradan RED'e çevirdiğinde (`orkestrator._delist_product_from_approval`)
> — "iptal edilen onay" anlamında, oluşturulan `products` satırı silinmeden
> terminal duruma çekilir (iz kalır). RED→ONAY'a geri dönülürse aynı satır
> `approved`'e geri döndürülür (`_restore_product_from_approval`).

Önemli alanlar: `score`, `cogs_tl`, `target_price_tl`, `supplier_id`, `stock_count`, `critical_stock_threshold` (default 5), `shopify_product_id`, `trendyol_barcode`

### `supplier_contacts` — Tedarikçi iletişim geçmişi

Status akışı: `research_found → approved → test_sent → inquiry_sent → followup_sent`
(RED yazılırsa herhangi bir aşamadan `rejected`'a geçebilir.)

Önemli alanlar: `tm_id` (TM-001 formatı), `supplier_name`, `contact_email`, `email_body`, `contacted_at`,
`rejection_notice_drafted` (GAP-9 — RED sonrası onaya tabi red bildirimi maili taslağının
tekrar üretilmesini önleyen flag, migration 006)

> **M5+ TOKEN OPT-1:** `email_body` kolonu eklenecek — bir kez üretilen mail body cache'lenecek.

### `mail_approvals` — Mail Onay source-of-truth (M4, GAP-1)

Sheet 3'ün (Mail Onay) Supabase karşılığı. `tedarikci.py` dual-write yapar:
Sheets kullanıcı arayüzü, bu tablo gerçek kaynak. Önemli alanlar: `tm_id`
(unique), `product_id`, `supplier_contact_id`, `onay_durumu`
(`pending`/`approved`/`sent`), `gmail_yaniti_alindi`.

### `proforma_offers` — Proforma teklifleri (M4, GAP-2)

Sheet 4'ün (Proforma Onay) Supabase karşılığı. `tedarikci.py` Faz 5'te
insert edilir (mock kontaklarda sentetik, gerçek kontaklarda Gmail yanıtından
Claude Haiku ile çıkarılmış veri). Onaylandığında orkestratör `products.status`'u
`sourcing → sourced`, ilgili `supplier_contacts.status`'u `completed` yapar.
Önemli alanlar: `product_id`, `supplier_contact_id`, `teklif_fiyat_usd`, `moq`,
`teslim_sure_gun`, `tahmini_cogs_tl`, `tahmini_marj_pct`,
`firsatci_tahmini_fark_tl`, `status` (`pending`/`approved`/`rejected`), `mock`.

### `orders` — Sipariş kayıtları

Status: `new → shipped → delivered` / `return_requested → returned`

### `financials` — Gelir/gider kayıtları

Önemli alanlar (`agents/finans.py._write_financials` ile birebir, GAP-3
kapatıldı — bkz. ROADMAP_TODO.md): `week_start`, `month`, `category`,
`platform`, `amount_tl` (gelir pozitif, gider negatif), `description`,
`source`, `tax_category` (`gelir`/`maliyet`/`gider`/`kdv`/`diger`).

`category` alanı serbest metin — kodun ürettiği değerler: platform geliri
için `rev.get("category", "platform_revenue")`, banka girişleri için Banka
sheet'indeki `Kategori` kolonu (`Gelir`/`COGS`/`Kargo`/`Reklam`/`Sabit
Gider`/`Komisyon`/`KDV`/`Diğer`), GAP-13 iade kaydı için `iade`.

> **GAP-3 — KAPATILDI:** Bu bölümdeki eski şema (sadece `amount_tl` +
> `category`, değer listesi `gelir_shopify` vb.) `agents/finans.py` koduyla
> uyuşmuyordu. Bu oturumda Supabase'in gerçek şemasına (canlı proje
> `ypusjrrklxssjvefkypd`) bu Claude Code oturumundan erişilemedi (bağlı
> Supabase MCP bağlantısı farklı, ilgisiz projelere işaret ediyordu); Berkin
> onayıyla `finans.py`'nin zaten kullandığı ve prodüksiyonda hatasız
> çalışan alanlar ground truth kabul edildi.

### `preferred_suppliers` — Başarılı tedarikçi hafızası (M5+)

### `ad_campaigns` — Reklam kampanya takibi (M6+)

## Pending M5+ Migration

```sql
-- Token Opt-1: email body caching
ALTER TABLE supplier_contacts
  ADD COLUMN IF NOT EXISTS email_body TEXT;
```
