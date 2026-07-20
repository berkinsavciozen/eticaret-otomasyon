# Orkestratör Agent

**Durum:** ✅ Aktif (M4-complete)  
**Railway servisi:** `eticaret-orkestrator` | `AGENT_NAME=orkestrator`  
**Cron:** `*/30 * * * *`  
**Aylık maliyet:** $2.50

## Rol

Tüm pipeline koordinasyon ve izleme merkezi. Sheets↔Supabase senkronizasyonu, hata yönetimi, haftalık raporlama. Tek başına bağımlılığı yoktur — ilk kurulan, en son kapanan agent.

## Çalışma Akışı (M4 — Her 30 Dakika)

```
1. Ürün onayı işle     Sheet 1 (ONAY/RED) → products.status = approved/rejected
2. Tedarikçi onayı     Sheet 2 (ONAY/RED) → supplier_contacts.status = approved
3. Mail onayı          Sheet 3 (pending/approved) → gerçek mail kuyruğu
4. Sheet 1 mirror      products tablosu → Sheet 1 tam yeniden yazma
5. Sheet 2 mirror      supplier_contacts + products join → Sheet 2
6. Dashboard yenile    Sheet 5 — pipeline sayıları + kullanıcı rehberi
7. Loglama             agent_logs tablosuna çalışma özeti
```

## 5-Sheet Mimarisi

| Sheet | Ad | Yön | Sorumlu |
|-------|----|----|---------|
| Sheet 1 | Ürün Onay | Supabase→Sheet + Sheet→Supabase | Orkestratör |
| Sheet 2 | Tedarikçi Onay | Supabase→Sheet + Sheet→Supabase | Orkestratör |
| Sheet 3 | Mail Onay | Tedarikçi yazar, Orkestratör okur | Tedarikçi/Orkestratör |
| Sheet 4 | Proforma | Tedarikçi (M5+) | Tedarikçi |
| Sheet 5 | Dashboard | Orkestratör yazar | Orkestratör |

## Dropdown Validasyonları (`_setup_validations()`)

| Sheet | Kolon | Kabul Edilen Değerler |
|-------|-------|-----------------------|
| Sheet 1 | Durum (D) | beklemede, ONAY, RED, onaylandı, reddedildi |
| Sheet 2 | Durum (P) | beklemede, ONAY, RED, onaylandı, mail gönderildi, takip gönderildi, tamamlandı |
| Sheet 3 | Excel Onay (G) | ONAY, RED |
| Sheet 3 | Onay Durumu (I) | pending, approved, sent |
| Sheet 4 | Durum (K) | beklemede, onaylandı, reddedildi |

## Supabase Erişimi

- **SERVICE_ROLE_KEY** kullanır (tek agent — RLS bypass, tam erişim)
- Okur: `products`, `supplier_contacts`, `agent_tasks`, `approval_queue`, `agent_logs`
- Yazar: `products` (status), `agent_tasks`, `agent_logs`

## Credentials

| Env Var | Açıklama |
|---------|---------|
| `SUPABASE_URL` | Proje URL |
| `SUPABASE_SERVICE_ROLE_KEY` | ⚠️ Sadece bu agent kullanır |
| `GMAIL_REFRESH_TOKEN` | Haftalık rapor + hata bildirimleri |
| `GMAIL_CLIENT_ID` | OAuth |
| `GMAIL_CLIENT_SECRET` | OAuth |
| `ANTHROPIC_API_KEY` | Haftalık rapor doğal dil özeti |
| `SHEETS_APPROVAL_QUEUE_ID` | 5-sheet dosyasının ID'si |

## Bilinen Sorunlar

- `_refresh_dashboard_step()`: `mail_pending` ve `proforma_pending` hardcoded `0` döndürüyor — Sheet 3/4'ten gerçek sayı okunmuyor (bkz. `guides/PENDING_FIXES.md`)
- Stale TODO notu: `_process_mail_approvals()` içinde "gerçek gönderim M4'te aktif olacak" notu — M4 tamamlandı, not kaldırılmalı
- `railway.toml` cron comment'leri eski değerleri gösteriyor

## Admin Kontrol Noktaları

| Tetikleyici | Beklenen Aksiyon |
|-------------|-----------------|
| Haftalık özet raporu | Gmail'de incele; öncelik değişikliği varsa agent_tasks güncelle |
| Failed task bildirimi | Manuel debug → status güncelle → agent_logs'a not |
| Agent konfigürasyonu | Doğrudan Supabase veya config güncelle |
