# Pending Fixes & Yapılacaklar

> Bu dosya bilinen bugları, kullanıcı aksiyonlarını ve sonraki session'da uygulanacak kod değişikliklerini listeler.

## 🔴 Kritik — Hemen Yapılacak

### BUG-1: `tedarikci.py` — Explicit "pending" override
**Dosya:** `agents/tedarikci.py` — `_phase1_supplier_research()` fonksiyonu  
**Sorun:** `upsert_tedarikci_onay` çağrısında explicit `"durum": "pending"` geçiyor. Bu `sheets_client.py`'daki default `"beklemede"` fix'ini override ediyor ve Sheet 2 dropdown validation hatasına yol açıyor.  
**Belirtisi:** Sheet 2'de "pending" görünüyor → "Invalid: Input must be on list" hatası  
**Fix:**
```python
# tedarikci.py içinde — upsert_tedarikci_onay çağrısını bul
# "durum": "pending"  ← BUNU DEĞİŞTİR
# "durum": "beklemede"  ← BUNA
```

### BUG-2: Google OAuth 7-Gün Token Expiry
**Sorun:** Google Cloud OAuth app "Testing" modunda — refresh token'lar 7 günde bir expire oluyor.  
**Belirti:** Railway'de `google.auth.exceptions.RefreshError: invalid_grant: Bad Request`  
**Geçici fix (uygulandı):** `orkestrator.py` Sheet mirror çağrıları try/except içine alındı (commit `19aa437`)  
**Kalıcı fix — KULLANICI AKSİYONU GEREKLI:**
1. Google Cloud Console → OAuth consent screen → "PUBLISH APP" (Production'a al)
2. Yeni `GMAIL_REFRESH_TOKEN` üret (Python script — `infrastructure/RAILWAY.md`'de adımlar var)
3. Tüm Railway servislerin `GMAIL_REFRESH_TOKEN` env var'ını güncelle

### ACTION-1: Supabase RLS Etkinleştir
**Sorun:** 9 tablo public erişime açık (`rls_disabled_in_public`)  
**Fix — Supabase SQL Editor'de çalıştır:**
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
**Not:** Agentlar `SERVICE_ROLE_KEY` kullandığı için RLS etkinleştirmek hiçbir şeyi kırmaz.

### ACTION-2: Healthchecks.io Period Güncelle
**Sorun:** Orkestratör 30dk'da çalışıyor ama Healthchecks.io period hâlâ 15 dk → DOWN/UP cycling  
**Fix:** Healthchecks.io dashboard → ilgili check → Period = **35 dakika**

---

## 🟠 Orta Öncelikli — Sonraki Session

### BUG-3: `orkestrator.py` — Dashboard Hardcoded Değerler
**Dosya:** `agents/orkestrator.py` — `_refresh_dashboard_step()`  
**Sorun:** `"mail_pending": 0, "proforma_pending": 0` hardcoded — Sheet 3/4'ten gerçek sayı okunmuyor  
**Fix:** Sheet 3 ve Sheet 4'ten gerçek pending sayılarını sorgula

### BUG-4: `orkestrator.py` — Stale TODO Notu
**Dosya:** `agents/orkestrator.py` — `_process_mail_approvals()`  
**Sorun:** "gerçek gönderim M4'te aktif olacak" notu kaldı — M4 tamamlandı  
**Fix:** TODO notunu kaldır veya güncelle

### BUG-5: `railway.toml` — Stale Cron Comment'ler
**Dosya:** `railway.toml`  
**Sorun:** Cron comment'leri eski değerleri gösteriyor (*/15 ve 0 7)  
**Fix:** Comment'leri güncelle veya kaldır (gerçek cron Railway Variables'ta zaten doğru)

---

## 🟡 Düşük Öncelikli — M5+ Token Optimizasyonları

### OPT-1: Email Body Caching (Tedarikçi)
**Öncelik:** Yüksek — retry/hata durumlarında gereksiz yeniden üretimi önler  
**Gerekli:** Supabase migration (email_body kolonu) + tedarikci.py kod değişikliği  
Detay: `guides/TOKEN_OPTIMIZATION.md`

### OPT-2: Email Generation Batch (Tedarikçi)
**Öncelik:** Orta — N ayrı çağrı → 1 batch  
**Bağımlılık:** OPT-1 sonra uygula  
Detay: `guides/TOKEN_OPTIMIZATION.md`

### OPT-5: Supplier Research Cache (Tedarikçi)
**Öncelik:** Orta — 7 gün içinde aynı keyword tekrar araştırılmaz  
Detay: `guides/TOKEN_OPTIMIZATION.md`

### OPT-6: Fallback Prompt Küçültme (Fırsatçı)
**Öncelik:** Düşük — `_claude_fallback_opportunities()` promptundan JSON şeması kaldırılabilir  
Detay: `guides/TOKEN_OPTIMIZATION.md`

---

## 🔵 M5 Geliştirme Görevleri

### Şirket Kurma (Kullanıcı Aksiyonu)
- Aile üyesiyle vergi dairesine git → şahıs şirketi kaydı
- Vergi levhası al → IBAN belirle
- Shopify hesabı aç (aile üyesi e-postası) → API key al
- Trendyol başvurusu yap (3-7 iş günü onay)
- iyzico + PayTR başvurusu
- Yurtiçi + MNG Kargo kurumsal hesap

### Railway Hobby Plan
**Durum:** Karar bekleniyor  
**Maliyet:** $5/ay  
**Öneri:** Loglar stabil görünüyorsa Hobby'e geç — cron'lar kesintisiz çalışır

### Trendyol V3 API Geçişi — ACIL
**Deadline: 10 Ağustos 2026** — V1 API kapatılıyor  
**Etkilenen:** `agents/siparis.py`, `agents/listeleme.py`  
**Tüm geliştirme V3 base URL'den yapılmalı:** `https://apigw.trendyol.com`

---

## ✅ Tamamlananlar (Referans)

| Fix | Commit | Tarih |
|-----|--------|-------|
| `sheets_client.py` — 4 yerde "pending" → "beklemede" | `ad07e61` | Haziran 2026 |
| `orkestrator.py` — Sheet mirror try/except (token expiry fix) | `19aa437` | Haziran 2026 |
| Fırsatçı Opt-3: Koşullu priority ranking | `cf662af` | Haziran 2026 |
| Fırsatçı Opt-4: Enrich'e sadece top 3 gönder | `cf662af` | Haziran 2026 |
