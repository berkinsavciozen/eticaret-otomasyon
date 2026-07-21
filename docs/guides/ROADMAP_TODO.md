# Roadmap & TODO — Backend Sağlamlaştırma → Lovable Geçişi

> Bu dosya projenin CANLI TODO kaynağıdır. Her fazda Claude (claude.ai chat)
> ve Berkin birlikte güncelleyecek. Kod değişiklikleri Claude Code'a devrediliyor,
> analiz/planlama Claude (chat) tarafında kalıyor, manuel hesap/dashboard işleri
> Berkin'e ait.

## Stratejik Karar (21 Temmuz 2026)

Google Sheets, backend sağlamlaştırma tamamlanana kadar FE (onay arayüzü)
olarak kalacak. Lovable'a geçiş SADECE operasyon baştan sona güvenilir şekilde
çalıştığı doğrulandıktan sonra başlayacak. Hazır Lovable analiz + prompt
docs/guides/LOVABLE_MIGRATION_PLAN.md'de duruyor — Faz 4'e kadar dokunma.

Ayrıca kararlaştırıldı: Şirket kurma aşamasına (M5) gelindiğinde TÜM kod
implemente edilmiş olmalı — proforma dahil hiçbir akış "dead code" veya
yarım kalmamalı.

## Faz 1 — Kritik Bug Fixler ✅ TAMAMLANDI

- [x] BUG-1: tedarikci.py "pending"→"beklemede" (commit `10ce1af`)
- [x] BUG-2: Google OAuth Production'a alındı (kullanıcı onayı)
- [x] ACTION-1: Supabase RLS 9 tabloda etkinleştirildi (kullanıcı onayı)
- [x] ACTION-2: Healthchecks.io period 35dk'ya çekildi (kullanıcı onayı)
- [x] BUG-3: Dashboard mail/proforma pending artık gerçek veriden okunuyor
      (commit `278c9e4`)
- [x] BUG-4: `orkestrator._process_mail_approvals()` artık Sheet 3'e yazmıyor,
      tek yazıcı `tedarikci.py` Faz 3 (commit `7357f00`) — GAP-4'ü de
      büyük ölçüde çözdü.
- [x] BUG-5: railway.toml + `eticaret-operations`/main.py doğrulaması
      (commit `df043d3`)
- [x] Orkestrator cron'u bilerek `0 7,19 * * *`'ye düşürüldü (Faz 3
      stabilize olunca eski sıklığa dönülmesi değerlendirilecek)
- [x] **KARAR (21 Temmuz 2026):** `eticaret-operations` mock modda çalışmaya
      DEVAM EDECEK — pause edilmeyecek, mock veri üretmesi şu an sorun değil.

## Faz 2 — Source-of-Truth Boşlukları (mimari analizden, 21 Temmuz 2026) 🔲 SIRADA

- [ ] **GAP-1 (Öncelik 1 — Mail Onay):** Sheet 3'ün Supabase'de karşılığı yok.

      1. Yeni tablo (SQL önce göster, onay iste):
         CREATE TABLE mail_approvals (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           tm_id text UNIQUE NOT NULL,
           product_id uuid REFERENCES products(id),
           supplier_contact_id uuid REFERENCES supplier_contacts(id),
           mail_turu text DEFAULT 'ilk_temas',
           email_body text,
           test_gonderildi_at timestamptz,
           excel_onay text,
           gmail_yaniti_alindi boolean DEFAULT false,
           onay_durumu text DEFAULT 'pending',
           gercek_gonderim_at timestamptz,
           note text,
           created_at timestamptz DEFAULT now()
         );
      2. core/sheets_client.py'deki append_mail_onay, check_mail_onay_approvals,
         update_mail_onay_status fonksiyonlarını Sheet 3'e EK OLARAK bu tabloya
         da yazacak/okuyacak şekilde güncelle (dual-write — Sheets kullanıcı
         arayüzü, Supabase gerçek kaynak). BUG-4'te kurulan tek-yazıcı
         prensibini bu yeni tabloda da koru.
      3. get_mail_onay_status_counts()'un Supabase üzerinden çalışan bir
         eşdeğerini değerlendir.

- [ ] **GAP-2 (Öncelik 2 — Proforma, KARAR VERİLDİ: şimdi implemente et):**
      Sheet 4 (Proforma) akışı tedarikci.py agent'ına yeni bir "Faz 5" olarak
      eklenecek. Kapsam:

      1. Yeni Supabase tablosu (SQL önce göster, onay iste):
         CREATE TABLE proforma_offers (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           product_id uuid REFERENCES products(id),
           supplier_contact_id uuid REFERENCES supplier_contacts(id),
           teklif_fiyat_usd numeric,
           moq integer,
           teslim_sure_gun integer,
           tahmini_cogs_tl numeric,
           tahmini_marj_pct numeric,
           firsatci_tahmini_fark_tl numeric,
           status text DEFAULT 'pending',  -- pending/approved/rejected
                                            -- (diğer Supabase tablolarıyla
                                            -- tutarlı; Sheet 4'e yazarken
                                            -- Türkçe'ye map'le, mevcut
                                            -- STATUS_MAP pattern'i gibi)
           note text,
           mock boolean DEFAULT false,
           created_at timestamptz DEFAULT now(),
           reviewed_at timestamptz
         );

      2. agents/tedarikci.py'ye `_phase5_handle_proforma()` ekle:
         - status='inquiry_sent' veya 'followup_sent' olan supplier_contacts
           için Gmail yanıtlarını kontrol et (_check_gmail_for_tm_replies
           ile aynı mekanizmayı genişlet — sadece "yanıt var mı" değil,
           yanıt İÇERİĞİNİ de oku).
         - Gerçek tedarikçi henüz yokken (mock=true kontaklar için) test
           edebilmek için, mevcut mock pattern'iyle tutarlı sentetik bir
           proforma yanıtı üret (Claude Haiku ile — _claude_supplier_research
           deki mock üretim mantığına benzer).
         - Gerçek yanıtlarda (mock=false), Claude Haiku ile yanıt metninden
           fiyat/MOQ/teslim süresi bilgisini çıkar (yapılandırılmamış metinden
           yapılandırılmış veri çıkarma — JSON response formatı kullan).
         - Sonucu proforma_offers tablosuna insert et VE Sheet 4'e
           append_proforma_onay() ile mirror'la.

      3. agents/orkestrator.py → _process_proforma_approvals_step()'i
         güncelle: Sheet 4'te (veya proforma_offers'da) onaylanan bir
         proforma bulunduğunda:
         - İlgili products kaydının status'unu 'sourcing' → 'sourced' yap
           (bu, listeleme.py'nin beklediği durum — şu an bunu HİÇBİR yer
           tetiklemiyor, bu pipeline'ı tamamlıyor)
         - İlgili supplier_contacts kaydının status'unu 'completed' yap

      4. Bu değişiklik products.status='sourced' geçişini ilk kez aktif
         hale getirdiği için, listeleme.py'nin (_get_sourced_products())
         artık gerçekten besleneceğini doğrula — bu Faz 3'te E2E test
         edilecek.

- [ ] **GAP-3:** financials tablosu şema tutarsızlığı — docs/infrastructure/
      SUPABASE.md ile agents/finans.py kodu farklı alanlar kullanıyor.
      Supabase'den information_schema.columns ile gerçek şema teyit edilip
      doküman düzeltilecek.

- [x] **GAP-4 (BÜYÜK ÖLÇÜDE ÇÖZÜLDÜ — BUG-4, commit `7357f00`):** Tek yazıcı
      artık tedarikci.py. Kalan: GAP-1 ve GAP-2'deki yeni tablolarda da bu
      prensibi koru.

- [ ] **GAP-5:** docs/infrastructure/SUPABASE.md'deki supplier_contacts status
      akışı gerçek kodla uyuşmuyor ("test_sent"/"inquiry_sent" vs "sent") —
      dokümanı düzelt.

## Faz 3 — E2E Doğrulama 🔲 BEKLEMEDE (Faz 2 sonrası)

- [ ] Ürün onay akışı baştan sona canlı test
- [ ] Tedarikçi onay akışı baştan sona canlı test
- [ ] Mail onay akışı baştan sona canlı test (yeni mail_approvals tablosuyla)
- [ ] Takip maili (48s) akışı test
- [ ] Proforma akışı baştan sona canlı test (yeni proforma_offers tablosu +
      products.status='sourced' geçişi + listeleme.py'nin bunu alması)
- [ ] Orkestrator cron'unu eski sıklığına döndürme kararı

## Faz 4 — Lovable FE 🔒 KİLİTLİ

Faz 3 tamamlanmadan başlamaz. Hazır plan: docs/guides/LOVABLE_MIGRATION_PLAN.md

## Backlog

- Token optimizasyonları (Opt-1..6) → docs/guides/TOKEN_OPTIMIZATION.md
- Trendyol V1→V3 API geçişi — DEADLINE: 10 Ağustos 2026
- M5 iş kurulumu → docs/guides/SETUP.md
- Railway Hobby plan kararı

## Sorumluluk Dağılımı

| İş türü | Kim |
|---|---|
| Kod değişiklikleri (Python, SQL migration, railway.toml) | Claude Code |
| Analiz, planlama, doküman güncelleme | Claude (chat) |
| Manuel hesap/dashboard işlemleri | Berkin |

## Değişiklik Geçmişi

| Tarih | Değişiklik |
|---|---|
| 21 Temmuz 2026 | Konsolidasyon: ONBOARDING.md silindi, PENDING_FIXES.md → ROADMAP_TODO.md, GAP-1..5 eklendi, BUG-3/4/5 tamamlandı, GAP-2 kararı verildi (şimdi implemente edilecek), eticaret-operations kararı verildi (mock modda devam) |
