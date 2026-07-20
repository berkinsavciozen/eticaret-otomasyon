# Railway — Altyapı Referansı

## Servis Yapısı

Tek repo, tek `railway.toml`, 3 aktif servis (M4 itibarıyla).

```
railway.toml:
  startCommand = "python main.py $AGENT_NAME"
```

Her servis kendi `AGENT_NAME` env var'ını Railway Variables'ta tanımlar.

| Railway Servisi | AGENT_NAME | Cron | Durum |
|-----------------|------------|------|-------|
| eticaret-orkestrator | `orkestrator` | `*/30 * * * *` | ✅ Aktif |
| eticaret-firsatci | `firsatci` | `0 6,18 * * *` | ✅ Aktif |
| eticaret-tedarikci | `tedarikci` | `0 * * * *` | ✅ Aktif |

> ⚠️ `railway.toml` içindeki cron comment'leri eski değerleri gösteriyor (stale). Gerçek schedule'lar Railway Variables/Settings'te tanımlıdır.

## Healthchecks.io Monitoring

**Mevcut sorun:** Orkestratör 30 dakikada çalıştığı halde Healthchecks.io period'u hâlâ 15 dakika.  
**Fix:** Healthchecks.io dashboard'da period'u **35 dakikaya** çek (30 dk + 5 dk buffer).

## Env Var Listesi

Tüm servislerde ortak olan env var'lar:

| Env Var | Değer Kaynağı | Bitwarden Adı |
|---------|---------------|--------------|
| `SUPABASE_URL` | Supabase Settings → API | E-Ticaret - Supabase |
| `SUPABASE_ANON_KEY` | Supabase Settings → API | E-Ticaret - Supabase |
| `ANTHROPIC_API_KEY` | Anthropic Console | Anthropic - eticaret-main |

Sadece Orkestratör'e özel:

| Env Var | Açıklama |
|---------|---------|
| `SUPABASE_SERVICE_ROLE_KEY` | ⚠️ Sadece bu servise gir |
| `SHEETS_APPROVAL_QUEUE_ID` | `1HfRKYMah7HcawCjmSYjE7OXMtOuvHQVJ25GH5zcTmvw` |
| `GMAIL_CLIENT_ID` | Google Cloud OAuth |
| `GMAIL_CLIENT_SECRET` | Google Cloud OAuth |
| `GMAIL_REFRESH_TOKEN` | OAuth akışından |

Tedarikçi'ye özel:

| Env Var | Açıklama |
|---------|---------|
| `GMAIL_CLIENT_ID` | — |
| `GMAIL_CLIENT_SECRET` | — |
| `GMAIL_REFRESH_TOKEN` | — |
| `NOTIFICATION_EMAIL` | Berkin'in Gmail adresi |
| `SENDER_NAME` | Mail imzası (isim) |
| `MOCK_SUPPLIER_EMAIL` | `berkinsavciozen@gmail.com` |
| `AGENT_NAME` | `tedarikci` |

## Gmail OAuth Refresh Token Yenileme

`GMAIL_REFRESH_TOKEN` Google Cloud OAuth app "Testing" modunda iken **7 günde bir** expires.

**Kalıcı fix:** Google Cloud Console → OAuth consent screen → "PUBLISH APP" (Production'a al)

Ardından yeni token üretme adımları:

```bash
pip install google-auth-oauthlib
python3 -c "
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_secrets_file('client_secret.json',
  scopes=['https://mail.google.com/',
          'https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/spreadsheets'])
creds = flow.run_local_server(port=0)
print('REFRESH_TOKEN:', creds.refresh_token)
print('CLIENT_ID:', creds.client_id)
print('CLIENT_SECRET:', creds.client_secret)
"
```

Çıktıdaki token'ı **tüm 4 Railway servisinin** `GMAIL_REFRESH_TOKEN` değerini güncelle.

## Railway Plan

- **Free trial:** 7 gün sonra sürüyor (Haziran 2026 itibarıyla)
- **Hobby plan:** $5/ay — cron job'lar çalışmaya devam eder
- **Karar:** Log'ları kontrol et; cron gerekiyorsa Hobby'e geç

## Deploy Akışı

1. Repo'ya push et
2. Railway otomatik deploy eder (Git-connected)
3. Her servis kendi `AGENT_NAME`'ine göre ilgili agent'ı çalıştırır
4. Cron'lar Railway Cron Jobs bölümünde ayarlı

## Güvenlik Kuralı

- `.env` dosyası **hiçbir zaman** commit edilmez (`.gitignore`'da tanımlı)
- Railway Variables → gerçek credential'lar buraya girilir
- `SUPABASE_SERVICE_ROLE_KEY` sadece Orkestratör servisine verilir
