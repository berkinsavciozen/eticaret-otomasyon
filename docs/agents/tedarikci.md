# Tedarikçi Agent

**Durum:** ✅ Aktif (M4-complete) — E2E test başarılı, gerçek mail gönderildi  
**Railway servisi:** `eticaret-tedarikci` | `AGENT_NAME=tedarikci`  
**Cron:** `0 * * * *` (saatte 1)  
**Aylık maliyet:** $2.50

## Rol

Fırsatçı'nın onayladığı ürünler için tedarikçi bulan, Claude Haiku ile mail yazan, Gmail'den gönderen, 48 saat followup yapan agent. Tedarik zincirinin tek iletişim noktası.

## 4-Aşamalı Pipeline (M4)

```
Railway cron (0 * * * *)
  │
  ├─ AŞAMA 1: Yeni onaylı ürünler
  │   products WHERE status='approved'
  │   → _claude_supplier_research(): Claude Haiku → 3 tedarikçi önerir
  │   → supplier_contacts'a kayıt (status: research_found)
  │   → Sheet 2'ye mirror (Orkestratör üzerinden)
  │   → products.status → 'sourcing'
  │
  ├─ AŞAMA 2: Tedarikçi onayı kontrolü
  │   supplier_contacts WHERE status IN ('research_found', 'approved')
  │   Sheet 2'de Berkin "ONAY" yazarsa → _send_test_mail()
  │     To: MOCK_SUPPLIER_EMAIL (berkinsavciozen@gmail.com)
  │     Subject: "[TM-001] Test: Product Inquiry — {ürün adı}"
  │     status → 'approved'
  │
  ├─ AŞAMA 3: Gmail kontrol (test reply → gerçek mail)
  │   _check_gmail_for_tm_replies() — TM-ID içeren reply ara
  │   Reply bulununca → Sheet 3 güncellenir
  │   Sheet 3'te Berkin "approved" seçerse → _send_real_supplier_mail()
  │     Subject: "Product Inquiry: {ürün adı}" ← TM-ID YOK
  │     status → 'sent'
  │
  └─ AŞAMA 4: Followup
      supplier_contacts WHERE status='inquiry_sent' AND contacted_at > 48h
      → Gerçek followup maili
      → status → 'followup_sent'
```

## TM-ID Sistemi — KRİTİK GÜVENLİK KURALI

| Kural | Detay |
|-------|-------|
| Format | `TM-001`, `TM-002`, ... — her supplier_contact'a benzersiz |
| Test mail subject | `[TM-001] Test: Product Inquiry — {ürün adı}` |
| Gerçek mail subject | `Product Inquiry: {ürün adı}` — **TM-ID ASLA GİRMEZ** |
| Mock hedef | `MOCK_SUPPLIER_EMAIL=berkinsavciozen@gmail.com` |
| Reply eşleme | Gmail'de TM-ID aranarak supplier_contact'a bağlanır |

## Durum Makinesi (`supplier_contacts.status`)

```
research_found → (Berkin ONAY) → approved
approved → (test mail gönderildi) → approved (mail gönderilince)
approved → (Gmail reply + Berkin onayı) → sent → (48h) → followup_sent
```

## Sheet Entegrasyonu

| Sheet | Rol | Tedarikçi Etkisi |
|-------|-----|-----------------|
| Sheet 2 | Tedarikçi araştırma onayı | Orkestratör mirror eder; Berkin ONAY/RED yazar |
| Sheet 3 | Test→gerçek mail akışı | Tedarikçi yazar (test gönderildi, Gmail yanıtı, sent) |

## Credentials

| Env Var | Açıklama |
|---------|---------|
| `GMAIL_CLIENT_ID` | OAuth |
| `GMAIL_CLIENT_SECRET` | OAuth |
| `GMAIL_REFRESH_TOKEN` | ⚠️ 7 günde bir expires — Google OAuth "Testing" modunda |
| `NOTIFICATION_EMAIL` | From adresi (Berkin'in Gmail'i) |
| `SENDER_NAME` | Mail imzasındaki ad |
| `MOCK_SUPPLIER_EMAIL` | `berkinsavciozen@gmail.com` — test hedefi |
| `ANTHROPIC_API_KEY` | Tedarikçi araştırması + mail üretimi (Claude Haiku) |
| `SUPABASE_URL` | — |
| `SUPABASE_ANON_KEY` | — |

## Bilinen Sorunlar

- **BUG:** `_phase1_supplier_research()` içinde `upsert_tedarikci_onay` çağrısında explicit `"durum": "pending"` geçiyor. Bu `sheets_client.py`'daki `"beklemede"` default'unu override ediyor ve Sheet 2 dropdown validation hatasına yol açıyor. Fix: `"durum": "pending"` → `"durum": "beklemede"` (bkz. `guides/PENDING_FIXES.md`)
- **Google OAuth 7-gün expiry:** `GMAIL_REFRESH_TOKEN` her 7 günde sürüyor çünkü Google Cloud OAuth app "Testing" modunda. Fix: Google Cloud Console'da Production'a publish, yeni token üret (bkz. `guides/PENDING_FIXES.md`)

## M5+ Planlamalar

| Özellik | Öncelik |
|---------|---------|
| `preferred_suppliers` tablosu — başarılı tedarikçi kaydı | 🔴 |
| Proforma alımı + Sheet 4 entegrasyonu | 🔴 |
| products'a COGS yazma | 🟡 |
| Token Opt-1: Email body caching | 🟡 |
| Token Opt-2: Batch email generation | 🟡 |

## Token Optimizasyonları (Planlandı)

- **Opt-1:** Email caching — `supplier_contacts.email_body` kolonu, bir kez üretilir tekrar üretilmez
- **Opt-2:** Batch generation — N ayrı çağrı yerine 1 batch çağrı
- **Opt-5:** Supplier research cache — aynı keyword 7 gün içinde tekrar araştırılmaz

Detay: `guides/TOKEN_OPTIMIZATION.md`
