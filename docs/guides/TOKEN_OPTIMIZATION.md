# Claude API Token Optimizasyonu

**Model:** Claude Haiku 4.5 — $0.25/M input · $1.25/M output  
**Tahmini günlük maliyet (M4 baseline):** ~$0.005–0.02

## Mevcut Token Haritası (M4 Baseline)

| Agent | Fonksiyon | Çağrı/gün | ~Token | Durum |
|-------|-----------|-----------|--------|-------|
| Fırsatçı ×2 | `_enrich_with_claude()` | 2 | ~900/çağrı | ✅ Opt-4 uygulandı |
| Fırsatçı ×2 | `_run_priority_ranking()` | 0-2 | ~700-2000 (N×50) | ✅ Opt-3 uygulandı |
| Fırsatçı ×2 | `_claude_fallback_opportunities()` | 0-2 | ~700/çağrı | Koşullu, sık değil |
| Tedarikçi ×1 | `_claude_supplier_research()` | N ürün | ~700/ürün | Bir kez, cache yok |
| Tedarikçi ×1 | `_generate_inquiry_email()` | N tedarikçi | ~500/mail | Batch değil, cache yok |

---

## ✅ Tamamlanan Optimizasyonlar

### Opt-3 — Koşullu Priority Ranking (commit: `cf662af`)
**Dosya:** `agents/firsatci.py` → `_run_priority_ranking()`  
**Ne yaptı:** Son ranking'ten bu yana yeni `pending` item eklenmemişse Claude çağrısı atlanır.  
`priority.ranked_at` timestamp'i metadata'ya yazılır, bir sonraki cron'da karşılaştırılır.  
**Tasarruf:** Günlük 1 gereksiz ranking çağrısı (~700–2000 token). Sabah cron'u genellikle boş geçer.

### Opt-4 — Enrich'e Sadece Top 3 Gönder (commit: `cf662af`)
**Dosya:** `agents/firsatci.py` → `_scan_new_opportunities()`  
**Ne yaptı:** `scored_candidates` skora göre sıralanıp yalnızca ilk 3'ü `_enrich_with_claude()`'a gönderiliyor. Öncesi: max 8 aday.  
**Tasarruf:** Enrich prompt input token'ında ~%60 azalma.

---

## 🔲 Planlanan Optimizasyonlar

### Opt-1 — Email Body Caching (Tedarikçi) — YÜKSEKÖNELİKLİ

**Etki:** Yüksek — retry/hata durumlarında tekrar üretimi engeller  
**Dosya:** `agents/tedarikci.py` → `_generate_inquiry_email()` → yeni `_get_or_generate_email()`  
**Supabase Migration gerekli:**

```sql
-- migrations/004_supplier_contacts_email_body.sql
ALTER TABLE supplier_contacts
  ADD COLUMN IF NOT EXISTS email_body TEXT;
```

**Kod değişikliği:**

```python
def _get_or_generate_email(product, supplier_contact, client) -> str:
    cached = supplier_contact.get("email_body")
    if cached:
        return cached  # Claude çağrısı YOK
    body = _generate_inquiry_email(product, supplier_contact)
    client.table("supplier_contacts").update(
        {"email_body": body}
    ).eq("id", supplier_contact["id"]).execute()
    return body
```

`_phase2_send_test_mails()` ve `_phase3_send_real_mails()` içinde `_generate_inquiry_email()` çağrılarını `_get_or_generate_email(product, sc, client)` olarak güncelle.

---

### Opt-2 — Email Generation Batch (Tedarikçi)

**Etki:** Orta — N ayrı çağrı → 1 batch  
**Bağımlılık:** Opt-1 sonra uygula (cache varsa batch zaten gereksizleşir — sadece cache miss'lerde devreye girer)

```python
def _generate_inquiry_emails_batch(items: list) -> dict:
    """
    items: [{"idx": 0, "product_name": ..., "supplier_name": ..., "platform": ...}]
    Returns: {"0": "email body", "1": "email body", ...}
    """
    prompt = f"""Write {len(items)} supplier inquiry emails.
Sender: {SENDER_NAME}
Products/Suppliers:
{json.dumps(items, ensure_ascii=False)}
Return ONLY JSON: {{"0": "body1", "1": "body2"}}
Each body max 150 words. Professional English."""
    # 1 çağrı → N email
```

**Tasarruf:** 3 tedarikçi → 3×500 token yerine 1×700 token (~%53 azalma)

---

### Opt-5 — Supplier Research Cache (Tedarikçi)

**Etki:** Orta — 7 gün içinde aynı keyword tekrar araştırılmaz

```python
def _is_recently_researched(keyword: str, client) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    res = client.table("supplier_contacts") \
        .select("id") \
        .ilike("supplier_name", f"%{keyword[:15]}%") \
        .gte("contacted_at", cutoff) \
        .execute()
    return len(res.data) > 0
```

---

### Opt-6 — Fallback Prompt Küçültme (Fırsatçı)

**Etki:** Düşük — `_claude_fallback_opportunities()` promptundaki embedded JSON şeması kaldırılabilir  
**Dosya:** `agents/firsatci.py`  
**Tasarruf:** Fallback çağrısında ~%30 input token azalması

---

## Uygulama Sırası

```
1. Supabase SQL Editor → migration 004 çalıştır (email_body kolonu)
2. Opt-1 uygula → email caching
3. Opt-2 uygula → batch (Opt-1 ile birlikte anlamlı)
4. Opt-5 uygula → supplier cache
5. Opt-6 uygula → prompt trim
```

## Referans

- Anthropic Console kullanım: https://console.anthropic.com/settings/usage
- Haiku fiyatlandırma: $0.25/M input · $1.25/M output
- En yüksek ROI: **Opt-1** (retry'da gereksiz yeniden üretimi engeller)
