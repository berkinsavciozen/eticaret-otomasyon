# Agent Index

## Pipeline Diyagramı

```
[Fırsatçı] ──onay──► [Tedarikçi] ──proforma──► [Listeleme]
                                                      │
                                           ┌──────────┴──────────┐
                                  [Pazarlama]           [Sipariş]
                                           │                 │
                                           └──────► [Finans] ◄┘
                                                        │
                                          [Orkestratör] ◄── tümü koordine eder
```

## Tüm Agentlar

| Agent | Durum | Railway Cron | Aylık Maliyet |
|-------|-------|-------------|---------------|
| Orkestratör | ✅ Aktif (M4) | `*/30 * * * *` | $2.50 |
| Fırsatçı | ✅ Aktif (M3) | `0 6,18 * * *` | $7.00 |
| Tedarikçi | ✅ Aktif (M4) | `0 * * * *` | $2.50 |
| Listeleme | 🔲 Planlandı (M5) | Event + 30dk polling | $2.50 |
| Sipariş | 🔲 Planlandı (M5) | 30dk polling | $1.50 |
| Finans | 🔲 Planlandı (M5) | Haftalık + aylık | $1.00 |
| Pazarlama | 🔲 Planlandı (M6) | Event + haftalık | $4.00 |
| **Toplam** | | | **$21.00** |

## Railway Servis Yapısı

Tek `railway.toml` — `python main.py $AGENT_NAME` start komutu.  
Her Railway servisi kendi `AGENT_NAME` env var'ını Variables'ta tanımlar.

| Railway Servisi | AGENT_NAME |
|-----------------|------------|
| eticaret-orkestrator | `orkestrator` |
| eticaret-firsatci | `firsatci` |
| eticaret-tedarikci | `tedarikci` |

## Supabase Tablo Sahipliği

| Tablo | Yazan | Okuyan |
|-------|-------|--------|
| `agent_tasks` | Orkestratör, Sipariş | Tüm agentlar |
| `approval_queue` | Fırsatçı, Tedarikçi, Listeleme, Pazarlama, Sipariş, Finans | Orkestratör, Berkin (Sheets) |
| `agent_logs` | Tüm agentlar | Orkestratör, Finans |
| `products` | Fırsatçı, Tedarikçi, Listeleme, Sipariş | Pazarlama, Finans |
| `orders` | Sipariş | Finans, Pazarlama, Fırsatçı |
| `financials` | Finans | Orkestratör |
| `preferred_suppliers` | Tedarikçi | Tedarikçi |
| `ad_campaigns` | Pazarlama | Finans |
| `supplier_contacts` | Tedarikçi | Orkestratör (Sheet 2 mirror) |

## İnsan Kontrol Noktaları

| Agent | Aksiyon | Sıklık |
|-------|---------|--------|
| Fırsatçı | Sheet 1 — ONAY/RED | ~5/hafta |
| Tedarikçi | Sheet 2 — araştırma ONAY/RED | Her ürün x3 tedarikçi |
| Tedarikçi | Sheet 3 — mail onayı | Her ürün |
| Listeleme | Sheet içerik onayı | İlk 3 ürün |
| Pazarlama | Kampanya + bütçe onayı | Her kampanya |
| Sipariş | İade ONAY/RED | Her iade |
| Finans | Manuel banka girişi | Haftalık |
| Orkestratör | Haftalık rapor + failed task | Haftalık |

## Feedback Sinyalleri

| Sinyal | Kaynak | Hedef | Etki |
|--------|--------|-------|------|
| İade oranı >%8 | Sipariş | Fırsatçı | Kategori kara listeye |
| COGS marjı <%15 | Finans | Tedarikçi | Müzakere görevi |
| Reklam bütçesi aşıldı | Finans | Pazarlama | Kampanya duraklat |
| Düşük CTR <%0.5 | Pazarlama | Listeleme | İçerik revizyonu |
| Stok kritik (≤3) | Sipariş | Tedarikçi | Yeniden sipariş görevi |
| ROAS ≥3x | Pazarlama | Fırsatçı | Benzer kategori öner |
