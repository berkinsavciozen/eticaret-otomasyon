# Kurulum Rehberi

> Bağımlılık sırasına göre düzenlenmiştir. Bir fazı tamamlamadan sonrakine geçme.

## Hesap Sahipliği Kuralı

**Berkin'in kişisel Gmail ile açılacaklar:**  
Supabase · Anthropic API · Google Cloud Project · Gmail OAuth · Google Sheets · Drive · Railway · Healthchecks.io · Meta (M6+) · Google Ads (M6+)

**Aile üyesinin kimliğiyle açılacaklar (yasal zorunluluk):**  
Trendyol Satıcı Paneli · Shopify · iyzico/PayTR · Yurtiçi Kargo · MNG Kargo

---

## Faz 0 — Hazırlık (M5 öncesi, şirket gerekli)

### 0.1 Şahıs Şirketi Kaydı
- Aile üyesiyle vergi dairesine git
- "İşe başlama bildirimi" doldur
- Gerekli belgeler: TC kimlik + ikametgah belgesi (aile üyesine ait)
- Vergi levhasını al → PDF olarak sakla
- Muhasebeci bul (~500 TL/ay) + e-fatura aktivasyonu

### 0.2 Banka Hesabı
- Aile üyesinin mevcut hesabı kullanılabilir
- IBAN'ı not et

---

## Faz 1 — Temel Altyapı ✅ (Tamamlandı)

### Supabase
- Proje: `ypusjrrklxssjvefkypd` (Singapore)
- 8 tablo oluşturuldu + `supplier_contacts` eklendi
- Credentials: Bitwarden → E-Ticaret - Supabase
- **Bekleyen:** RLS etkinleştirme (bkz. `PENDING_FIXES.md`)

### Anthropic API
- Bitwarden → Anthropic - eticaret-main
- $30 aylık harcama limiti ayarlı

---

## Faz 2 — Google Ekosistemi ✅ (Tamamlandı)

### Google Cloud Project: `eticaret-otomasyon`
- Gmail API + Google Drive API + Google Sheets API açık
- OAuth 2.0 Desktop app: `eticaret-agent`
- Credentials: Bitwarden → E-Ticaret - Gmail OAuth

**⚠️ Bekleyen:** OAuth consent screen'i "Testing"den "Production"a al  
(7 günlük token expiry sorununu çözer — detay: `infrastructure/RAILWAY.md`)

### Google Sheets
- Spreadsheet ID: `1HfRKYMah7HcawCjmSYjE7OXMtOuvHQVJ25GH5zcTmvw`
- 5-sheet yapısı hazır + dropdown validasyonlar aktif

---

## Faz 3 — E-Ticaret Platformları (M5)

### Shopify
- Aile üyesinin e-postasıyla aç
- Plan: Basic ($29/ay)
- Admin API scopes: `read/write_products`, `read/write_orders`, `read/write_inventory`, `read/write_fulfillments`
- App adı: `eticaret-agent`
- Store URL formatı: `magaza-adi.myshopify.com`

### Trendyol
- partner.trendyol.com → Satıcı Başvurusu
- Belgeler: vergi levhası + IBAN + TC kimlik
- Onay: **3-7 iş günü**
- **⚠️ V1 API 10 Ağustos 2026'da kapanıyor — tüm geliştirme V3'e**
- Sandbox ortamı erişimi iste: developers.trendyol.com

---

## Faz 4 — Ödeme ve Kargo (M5)

### iyzico (Shopify Ödeme)
- iyzico.com → Satıcı Başvurusu
- Belgeler: vergi levhası + banka hesabı + kimlik
- Onay: ~2-5 iş günü
- Yedek: PayTR (aynı adımları tekrarla)

### Yurtiçi Kargo — Kurumsal Hesap
- yurticikargo.com → Kurumsal Başvuru
- Onay sonrası müşteri temsilcisinden API erişimi iste
- Yedek: MNG Kargo

---

## Faz 5 — Credential Yönetimi

### `.env` Şablonu

```env
# SUPABASE
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...  # Sadece orkestratör

# ANTHROPIC
ANTHROPIC_API_KEY=sk-ant-...

# GOOGLE
GMAIL_CLIENT_ID=xxxxxx.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-...
GMAIL_REFRESH_TOKEN=1//...
GDRIVE_PROFORMA_FOLDER_ID=1aBcDeFgHiJ...
SHEETS_APPROVAL_QUEUE_ID=1HfRKYMah7HcawCjmSYjE7OXMtOuvHQVJ25GH5zcTmvw

# RAILWAY / AGENT
AGENT_NAME=orkestrator  # veya firsatci / tedarikci
SENDER_NAME=Berkin
NOTIFICATION_EMAIL=berkinsavciozen@gmail.com
MOCK_SUPPLIER_EMAIL=berkinsavciozen@gmail.com

# SHOPIFY (M5)
SHOPIFY_API_KEY=
SHOPIFY_API_SECRET=
SHOPIFY_ACCESS_TOKEN=shpat_...
SHOPIFY_STORE_URL=https://magaza-adi.myshopify.com

# TRENDYOL (M5)
TRENDYOL_SUPPLIER_ID=
TRENDYOL_API_KEY=
TRENDYOL_API_SECRET=
TRENDYOL_BASE_URL=https://apigw.trendyol.com

# KARGO (M5)
YURTICI_USERNAME=
YURTICI_PASSWORD=
YURTICI_CUSTOMER_NO=
MNG_USERNAME=
MNG_PASSWORD=

# ÖDEME (M5)
IYZICO_API_KEY=
IYZICO_SECRET_KEY=
PAYTR_MERCHANT_ID=
PAYTR_MERCHANT_KEY=
PAYTR_MERCHANT_SALT=

# M6+
META_APP_ID=
META_APP_SECRET=
META_ACCESS_TOKEN=
META_AD_ACCOUNT_ID=
GOOGLE_ADS_DEVELOPER_TOKEN=
```

---

## Faz 6 — M6+ Genişleme

### Meta Business Suite
- business.facebook.com → Business account → Ad Account
- developers.facebook.com → App → Marketing API erişimi

### Google Ads
- ads.google.com → Expert mode
- Tools → API Center → Developer token başvurusu (1-3 iş günü)

### Hepsiburada / n11 (İsteğe Bağlı)
- Aile üyesi kimliğiyle başvuru
- n11: Chrome Connector kullanacak — API gerekmez
