# Pending Fixes & Yapılacaklar

> Bu dosya bilinen bugları, kullanıcı aksiyonlarını ve sonraki session'da uygulanacak kod değişikliklerini listeler.

## 🔴 Kritik — Hemen Yapılacak

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

_Şu an bu bölümde açık madde yok — BUG-3, BUG-4, BUG-5 tamamlandı (bkz. "✅ Tamamlananlar")._ 

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

### Orkestrator Cron Sıklığı — Geçici Düşürüldü
**Durum:** `eticaret-otomasyon` (orkestrator) cron'u Railway'de bilerek 30 dakikadan
**günde 2 kez'e** (`0 7,19 * * *`) düşürüldü, çünkü `tedarikci.py` Faz 3'teki gerçek
tedarikçi mail gönderimi henüz üretimde sık çalıştırılacak kadar olgunlaşmadı.
**Not:** Faz 3 stabilize olup güvenilir çalıştığı doğrulanınca eski sıklığa
(`*/30 * * * *` gibi) geri dönülmesi düşünülebilir. (Detay: `railway.toml` yorumu)

### `eticaret-operations` Servisi — Sadece MOCK Modda
**Durum:** `eticaret-operations` (AGENT_NAME=operations) servisi `main.py` üzerinden
mevcut `listeleme.py` + `siparis.py` + `finans.py` agentlarını sırayla çalıştırıyor
(ayrı bir `agents/operations.py` dosyasına ihtiyaç yok, main.py bunu zaten doğru
handle ediyor — bkz. BUG-5). Ancak bu üç agent'ın Shopify/Trendyol/banka API
entegrasyonları henüz gerçek değil, hepsi `MOCK_LISTING` / `MOCK_ORDERS` /
`MOCK_FINANCIALS` env var'larına bağlı mock modda çalışıyor.
**Öneri (kod değişikliği gerekmez):** Gerçek entegrasyonlar tamamlanana kadar bu
servisi Railway'de pause etmeyi değerlendirebilirsin — şu an çalışsa da mock veri
üretmekten öteye geçmiyor.

---

## ✅ Tamamlananlar (Referans)

| Fix | Commit | Tarih |
|-----|--------|-------|
| `tedarikci.py` — `_phase1_supplier_research()` explicit "pending" → "beklemede" (Sheet 2 dropdown fix) | `10ce1af` | Temmuz 2026 |
| `sheets_client.py` — 4 yerde "pending" → "beklemede" | `ad07e61` | Haziran 2026 |
| `orkestrator.py` — Sheet mirror try/except (token expiry fix) | `19aa437` | Haziran 2026 |
| Fırsatçı Opt-3: Koşullu priority ranking | `cf662af` | Haziran 2026 |
| Fırsatçı Opt-4: Enrich'e sadece top 3 gönder | `cf662af` | Haziran 2026 |
| BUG-3: `orkestrator.py` dashboard mail/proforma pending gerçek verilerle değiştirildi (`get_mail_onay_status_counts` / `get_proforma_onay_status_counts` eklendi) | `278c9e4` | Temmuz 2026 |
| BUG-4: `orkestrator.py` stale M4 TODO'su temizlendi, `_process_mail_approvals()` artık Sheet 3'e yazmıyor (duplike işleme riski tedarikci.py Faz 3 ile çakışmasın diye) | `7357f00` | Temmuz 2026 |
| BUG-5: `railway.toml` cron comment'leri gerçek Railway durumuna göre güncellendi, `eticaret-operations`/main.py doğrulandı | `df043d3` | Temmuz 2026 |
