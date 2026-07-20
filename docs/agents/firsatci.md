# Fırsatçı Agent

**Durum:** ✅ Aktif (M3-complete)  
**Railway servisi:** `eticaret-firsatci` | `AGENT_NAME=firsatci`  
**Cron:** `0 6,18 * * *` (09:00 + 21:00 TR)  
**Aylık maliyet:** $7.00

## Rol

Pipeline'ın başlangıç noktası. Hiçbir agenta bağımlı değildir. Günde 2 kez çalışır, ürün fırsatı keşfeder, Claude Haiku ile fizibilite skorlar ve Berkin'in onayına sunar.

## Çalışma Akışı (M3)

```
Railway cron (06:00 + 18:00 UTC)
  └─ _get_trending_keywords()   pytrends → Google Trends TR top 20
       └─ [başarısız ise]       SEED_CATEGORIES fallback (23 kategori, 8 rastgele)
  └─ _score_with_claude()       Claude Haiku → top 3 fırsat JSON
  └─ _is_duplicate()            Son 7 gün approval_queue'da aynı başlık var mı?
  └─ _queue_for_approval()      Supabase approval_queue'ya insert
```

## Veri Kaynakları

| Kaynak | Yöntem | Durum |
|--------|--------|-------|
| Google Trends TR | pytrends `trending_searches(pn="turkey")` | ⚠️ 404 intermittent → fallback |
| Seed kategoriler | 23 hardcoded, 8 rastgele seçim | ✅ Aktif |
| Claude Haiku | Scoring + fırsat seçimi | ✅ Aktif |
| Trendyol Seller API V3 | Bestseller + satış hacmi | ❌ M5+ planlandı |
| Web Search MCP | Alibaba fiyat araştırması | ❌ M5+ planlandı |

## Seed Kategoriler (23 adet)

Elektronik: akıllı saat, kablosuz kulaklık, powerbank, şarj aleti, web kamerası, oyuncu mouse, laptop çantası  
Spor: yoga matı, direnç bandı, protein tozu  
Mutfak: hava fritözü, blender, kahve makinesi, mini ütü  
Kişisel bakım: cilt bakım seti, saç düzleştirici, göz kremi  
Oyuncak: lego seti, puzzle, çocuk oyuncak  
Ev: ev dekor, led şerit, yastık seti

## Claude Haiku Promptu — Çıktı Formatı

```json
{
  "name": "Ürün adı (Türkçe)",
  "summary": "2-3 cümle: neden fırsat, talep sinyali, margin potansiyeli",
  "trendyol_category": "Ana Kategori > Alt Kategori",
  "estimated_price_tl": 500,
  "estimated_margin_pct": 35,
  "trend_score": 80
}
```

> ⚠️ `trend_score` deterministik değil — Claude tahmini. Onay eşiği uygulanmıyor (M5+ planlandı).

## Skorlama Kriterleri (M3 — ağırlıksız)

| Kriter | Açıklama |
|--------|---------|
| Talep sinyali | Trend'de ya da evergreen mi? |
| Tedarik edilebilirlik | Alibaba/1688/yerel'den bulunabilir mi? |
| Kar marjı | Hedef %30+ (Trendyol komisyonu ~%15 dahil) |
| Yasal uygunluk | TR'de kısıt yok mu? |
| Kargo uygunluğu | Max 3kg, kırılgan değil |

## Supabase Erişimi

- **ANON_KEY** kullanır
- Okur: `approval_queue` (duplicate check)
- Yazar: `approval_queue` (pending fırsatlar), `agent_logs`

> ⚠️ Eski vault notlarında `products` tablosuna direkt yazdığı belirtiliyordu — **bu değişti.** Fırsatçı yalnızca `approval_queue`'ya yazar. Orkestratör, Sheets'te onay görünce `products` kaydını oluşturur.

## Credentials

| Env Var | Açıklama |
|---------|---------|
| `ANTHROPIC_API_KEY` | Claude Haiku scoring |
| `SUPABASE_URL` | — |
| `SUPABASE_ANON_KEY` | — |

## Token Optimizasyonları (M4 uygulandı)

- **Opt-3:** Koşullu priority ranking — yeni pending item yoksa Claude çağrısı atlanır (commit `cf662af`)
- **Opt-4:** Enrich'e sadece top 3 aday gönderilir (commit `cf662af`)

## M5+ Planlamalar

| Özellik | Öncelik |
|---------|---------|
| Trendyol Seller API V3 — bestseller çekme | 🔴 Yüksek |
| Ağırlıklı skorlama (Talep 30% + Rekabet 25% + Tedarik 25% + Marj 15% + Risk 5%) | 🔴 Yüksek |
| Onay eşiği 70/100 — altındakiler otomatik reject | 🟡 Orta |
| Web Search MCP — Alibaba COGS tahmini | 🟡 Orta |
| Negatif örnek öğrenmesi (reddedilen ürünlerden öğren) | 🟡 Orta |
| Kategori kara liste — Sipariş Agent iade sinyaliyle | 🟢 Düşük |
