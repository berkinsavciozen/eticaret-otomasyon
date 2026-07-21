# Google Sheets — 5-Sheet Mimarisi

**Spreadsheet ID:** `1HfRKYMah7HcawCjmSYjE7OXMtOuvHQVJ25GH5zcTmvw`  
**Env Var:** `SHEETS_APPROVAL_QUEUE_ID`  
**Erişim:** Berkin'in kişisel Gmail → OAuth 2.0

## Sheet Genel Bakış

| # | Ad | Yön | Güncelleme Sıklığı | Berkin'in Rolü |
|---|----|----|-------------------|---------------|
| Sheet 1 | Ürün Onay | Supabase↔Sheet | Her 30 dk (Orkestratör) | ONAY/RED yaz |
| Sheet 2 | Tedarikçi Onay | Supabase↔Sheet | Her 30 dk (Orkestratör) | ONAY/RED yaz |
| Sheet 3 | Mail Onay | Tedarikçi yazar | Saatte 1 (Tedarikçi) | Onay Durumu seç |
| Sheet 4 | Proforma | Tedarikçi yazar | Saatte 1 (Tedarikçi Faz 5) | Fiyat onayı |
| Sheet 5 | Dashboard | Orkestratör yazar | Her 30 dk | Sadece okur |

## Sheet 1 — Ürün Onay

**Ne gösterir:** Fırsatçı'nın approval_queue'ya koyduğu ürün adayları  
**Orkestratör mirror:** products tablosu → Sheet 1 (tam yeniden yazma)  
**Berkin aksiyonu:** D kolonu (Durum) dropdown'a ONAY veya RED yaz

| Kolon | İçerik |
|-------|--------|
| A | Ürün ID |
| B | Ürün Adı |
| C | Kategori |
| D | **Durum** ← BERKIN BURAYA YAZAR |
| ... | Skor, tahmini fiyat, özet vb. |

**Dropdown değerleri (D kolonu):** `beklemede`, `ONAY`, `RED`, `onaylandı`, `reddedildi`

## Sheet 2 — Tedarikçi Onay

**Ne gösterir:** Claude Haiku'nun önerdiği tedarikçiler (ürün başına 3 adet)  
**Orkestratör mirror:** supplier_contacts + products join → Sheet 2  
**Berkin aksiyonu:** P kolonu (Durum) dropdown'a ONAY veya RED yaz

**Dropdown değerleri (P kolonu):** `beklemede`, `ONAY`, `RED`, `onaylandı`, `mail gönderildi`, `takip gönderildi`, `tamamlandı`

## Sheet 3 — Mail Onay

**Ne gösterir:** Test mail gönderim durumu + Gmail yanıt durumu  
**Yazan:** Tedarikçi Agent  
**Berkin aksiyonu:** G kolonu (Excel Onay) + I kolonu (Onay Durumu) seç

| Kolon | İçerik |
|-------|--------|
| G | **Excel Onay** — `ONAY` / `RED` |
| I | **Onay Durumu** — `pending` / `approved` / `sent` |

Akış:
1. Tedarikçi test mail gönderir → Sheet 3'e yazar
2. Berkin Gmail'de test maili görür → G'ye ONAY yazar
3. Orkestratör okur → Tedarikçi'ye gerçek mail sinyali
4. Gmail'den tedarikçi yanıtı gelirse → Sheet 3 güncellenir
5. I kolonuna `approved` yazarsan → gerçek tedarikçi maili gönderilir

## Sheet 4 — Proforma

**Ne gösterir:** Tedarikçi Agent Faz 5'te üretilen/çıkarılan proforma teklifleri
(mock kontaklarda Claude Haiku ile sentetik, gerçek kontaklarda Gmail yanıtından
çıkarılmış). Supabase karşılığı: `proforma_offers` (bkz. GAP-2, ROADMAP_TODO.md).
**Yazan:** Tedarikçi Agent (`append_proforma_onay`)
**Berkin aksiyonu:** K kolonu (Durum) dropdown'a ONAY veya RED yaz — onaylanınca
ilgili ürün `sourced` durumuna geçer, tedarikçi kaydı `completed` olur.
**Dropdown (K kolonu):** `beklemede`, `onaylandı`, `reddedildi`

## Sheet 5 — Dashboard

**Ne gösterir:** Pipeline özeti + kullanıcı rehberi  
**Yazan:** Orkestratör  
**Berkin rolü:** Sadece okur

İçerik:
- Bekleyen onay sayıları
- Her Sheet için hangi kolona ne yazılacağı (kılavuz)
- Durum değerlerinin anlamları

## Dropdowns Özet

| Sheet | Kolon | Değerler |
|-------|-------|---------|
| Sheet 1 | D (Durum) | beklemede, ONAY, RED, onaylandı, reddedildi |
| Sheet 2 | P (Durum) | beklemede, ONAY, RED, onaylandı, mail gönderildi, takip gönderildi, tamamlandı |
| Sheet 3 | G (Excel Onay) | ONAY, RED |
| Sheet 3 | I (Onay Durumu) | pending, approved, sent |
| Sheet 4 | K (Durum) | beklemede, onaylandı, reddedildi |

## Banka Hareketi Girişi (Finans Agent — M5+)

Aynı spreadsheet dosyasında ayrı bir sekme: `Banka Hareketleri`  
Env Var: `SHEETS_BANK_ENTRY_ID`

Format: Tarih | Tutar (TL) | Açıklama | Kategori
