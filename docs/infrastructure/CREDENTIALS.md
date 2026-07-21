# Credential Takip

> Bu dosya gerçek key değerlerini **içermez**. Sadece hangi credential'ların alındığını, nerede saklandığını ve hangi agent'ın kullandığını takip eder.
>
> **Kural:** Her yeni key alındığında bu dosyayı güncelle. Gerçek değerler SADECE Bitwarden'de.

## Saklama Kuralı

| Ortam | Nerede |
|-------|--------|
| Yedek | Bitwarden — "E-Ticaret Otomasyon" klasörü |
| Local geliştirme | `.env` dosyası (git'e commit edilmez) |
| Production | Railway → Service → Variables |

---

## 🔴 Kritik (M1 — şu an gerekli)

### Anthropic
| Key | Alındı | Bitwarden |
|-----|--------|-----------|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic - eticaret-main |

### Supabase
| Key | Alındı | Bitwarden |
|-----|--------|-----------|
| `SUPABASE_URL` | ✅ | E-Ticaret - Supabase |
| `SUPABASE_ANON_KEY` | ✅ | E-Ticaret - Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | E-Ticaret - Supabase |

### Google Gmail OAuth
| Key | Alındı | Bitwarden | Not |
|-----|--------|-----------|-----|
| `GMAIL_CLIENT_ID` | ✅ | E-Ticaret - Gmail OAuth | — |
| `GMAIL_CLIENT_SECRET` | ✅ | E-Ticaret - Gmail OAuth | — |
| `GMAIL_REFRESH_TOKEN` | ✅ | E-Ticaret - Gmail OAuth | ✅ Production modda — artık 7 günde expire olmuyor, bkz. RAILWAY.md |

**M1 Kritik: 7 / 7 tamamlandı ✅**

---

## 🟠 Önemli (M5 — şirket kurulduktan sonra)

### Shopify
| Key | Alındı | Bitwarden |
|-----|--------|-----------|
| `SHOPIFY_API_KEY` | ☐ | — |
| `SHOPIFY_API_SECRET` | ☐ | — |
| `SHOPIFY_ACCESS_TOKEN` | ☐ | — |
| `SHOPIFY_STORE_URL` | ☐ | — |

### Trendyol
| Key | Alındı | Bitwarden | Not |
|-----|--------|-----------|-----|
| `TRENDYOL_SUPPLIER_ID` | ☐ | — | Onay 3-7 iş günü |
| `TRENDYOL_API_KEY` | ☐ | — | Entegrasyon → API |
| `TRENDYOL_API_SECRET` | ☐ | — | — |

> ⚠️ Trendyol V1 API **10 Ağustos 2026'da kapanıyor** — tüm geliştirme V3 ile.

### Google Sheets
| Key | Alındı | Değer |
|-----|--------|-------|
| `SHEETS_APPROVAL_QUEUE_ID` | ✅ | `1HfRKYMah7HcawCjmSYjE7OXMtOuvHQVJ25GH5zcTmvw` |
| `SHEETS_BANK_ENTRY_ID` | ☐ | — |
| `GDRIVE_PROFORMA_FOLDER_ID` | ☐ | — |

### İzleme
| Key | Alındı | Not |
|-----|--------|-----|
| `HEALTHCHECKS_PING_URL` | ✅ | Period 35 dk olarak ayarlandı |

---

## 🟡 Beklemede (M5 — ödeme & kargo)

### iyzico
| Key | Alındı |
|-----|--------|
| `IYZICO_API_KEY` | ☐ |
| `IYZICO_SECRET_KEY` | ☐ |

### PayTR (yedek)
| Key | Alındı |
|-----|--------|
| `PAYTR_MERCHANT_ID` | ☐ |
| `PAYTR_MERCHANT_KEY` | ☐ |
| `PAYTR_MERCHANT_SALT` | ☐ |

### Kargo
| Key | Alındı |
|-----|--------|
| `YURTICI_USERNAME` | ☐ |
| `YURTICI_PASSWORD` | ☐ |
| `YURTICI_CUSTOMER_NO` | ☐ |
| `MNG_USERNAME` | ☐ |
| `MNG_PASSWORD` | ☐ |

---

## 🟢 M6+ (Pazarlama)

### Meta
| Key | Alındı |
|-----|--------|
| `META_APP_ID` | ☐ |
| `META_APP_SECRET` | ☐ |
| `META_ACCESS_TOKEN` | ☐ |
| `META_AD_ACCOUNT_ID` | ☐ |

### Google Ads
| Key | Alındı |
|-----|--------|
| `GOOGLE_ADS_DEVELOPER_TOKEN` | ☐ |
| `GOOGLE_ADS_CLIENT_ID` | ☐ |
| `GOOGLE_ADS_CLIENT_SECRET` | ☐ |
| `GOOGLE_ADS_REFRESH_TOKEN` | ☐ |
| `GOOGLE_ADS_CUSTOMER_ID` | ☐ |

---

## Agent × Credential Matrisi

| Credential | Orkestratör | Fırsatçı | Tedarikçi | Listeleme | Pazarlama | Sipariş | Finans |
|------------|-------------|----------|-----------|-----------|-----------|---------|--------|
| `SUPABASE_URL` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `SUPABASE_SERVICE_ROLE_KEY` | ✓ | — | — | — | — | — | — |
| `SUPABASE_ANON_KEY` | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ANTHROPIC_API_KEY` | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| `GMAIL_*` | ✓ | — | ✓ | — | — | ✓ | — |
| `SHEETS_*` | ✓ | ✓ | — | — | — | — | ✓ |
| `SHOPIFY_*` | — | — | — | ✓ | ✓ | ✓ | ✓ |
| `TRENDYOL_*` | — | — | — | ✓ | ✓ | ✓ | ✓ |
| `YURTICI_*` / `MNG_*` | — | — | — | — | — | ✓ | — |
| `META_*` | — | — | — | — | ✓ | — | — |
| `GOOGLE_ADS_*` | — | — | — | — | ✓ | — | — |
