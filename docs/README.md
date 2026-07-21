# eticaret-otomasyon — Proje Dökümantasyonu

> Bu `docs/` klasörü projenin tek kaynak-of-truth'udur. Obsidian vault'un e-ticaret içeriği buraya taşındı. Claude.ai bu klasörü GitHub MCP üzerinden okur ve yazar.

## Klasör Yapısı

```
docs/
├── README.md                     ← Bu dosya
├── MASTER_PLAN.md                ← Sistem mimarisi, milestone geçmişi, roadmap
├── agents/
│   ├── index.md                  ← Agent özet tablosu + pipeline diyagramı
│   ├── orkestrator.md
│   ├── firsatci.md
│   ├── tedarikci.md
│   ├── listeleme.md
│   ├── siparis.md
│   ├── finans.md
│   └── pazarlama.md
├── infrastructure/
│   ├── SUPABASE.md               ← Tablo şemaları, RLS, bağlantı
│   ├── RAILWAY.md                ← Servis yapısı, env var listesi, deploy
│   ├── SHEETS.md                 ← 5-sheet mimarisi, dropdown validasyonlar
│   └── CREDENTIALS.md            ← Credential takip (değerler YOK — sadece durum)
└── guides/
    ├── SETUP.md                  ← Kurulum rehberi (fazlar halinde)
    ├── TOKEN_OPTIMIZATION.md     ← Claude API maliyet optimizasyonu
    ├── ROADMAP_TODO.md           ← Canlı TODO kaynağı — bilinen buglar, GAP'ler, faz durumu
    └── LOVABLE_MIGRATION_PLAN.md ← Lovable FE geçiş planı (Faz 4'e kadar kilitli)
```

## Kullanım Kuralları

- **Güncel durumu öğrenmek için:** `docs/guides/ROADMAP_TODO.md` ve ilgili agent dosyasına bak
- **Credential değerleri bu klasörde YOK** — sadece Bitwarden'de saklanır
- **`.env` hiçbir zaman commit edilmez** — `.gitignore`'da tanımlı

## Milestone Durumu

| Milestone | Tarih | Durum |
|-----------|-------|-------|
| M1 — Temel altyapı | Haziran 2026 | ✅ Tamamlandı |
| M2 — Fırsatçı + Tedarikçi mock | Haziran 2026 | ✅ Tamamlandı |
| M3 — E2E mock pipeline | Haziran 2026 | ✅ Tamamlandı |
| M4 — Gerçek mail, 5-sheet sync | Haziran 2026 | ✅ Tamamlandı |
| M5 — Şirket kurma + marketplace hesapları | Temmuz 2026 | 🔄 Devam ediyor |
| M6 — Canlı satış (Shopify + Trendyol) | Ağustos 2026 | ⏳ Beklemede |

_Son güncelleme: Temmuz 2026_
