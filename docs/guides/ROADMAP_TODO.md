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
- [x] GAP-1 ve GAP-2 SQL migration'ları (004_mail_approvals.sql,
      005_proforma_offers.sql) Berkin tarafından Supabase'e UYGULANDI (21 Temmuz
      2026). mail_approvals ve proforma_offers tabloları artık canlı.

## Faz 2 — Source-of-Truth Boşlukları (mimari analizden, 21 Temmuz 2026) 🔲 SIRADA

## ⚠️ Güvenlik Notu — Şirket Henüz Kurulmadı

Şahıs şirketi kaydı tamamlanana kadar (bkz. guides/SETUP.md Faz 0) gerçek
tedarikçiye mail gitmemeli, Trendyol/Shopify gerçek API bağlantısı
kurulmamalı. Sistem şu an bunu yapısal olarak zaten sağlıyor:
- MOCK_SUPPLIER_EMAIL env var'ı devrede olduğu sürece 'gerçek' tedarikçi
  maili dahi Berkin'in kendi adresine gider (agents/tedarikci.py
  _send_real_inquiry_email).
- MOCK_LISTING / MOCK_ORDERS / MOCK_FINANCIALS flag'leri Trendyol/Shopify
  gerçek çağrılarını engelliyor.
- GAP-9 (red maili), GAP-11 (proforma fallback), GAP-12 (kritik stok
  reorder) gibi yeni eklenecek akışların HİÇBİRİ bu güvenlik katmanını
  atlamaz — hepsi mevcut mock/onay akışının içinde kalır.

KURAL: Şirket kurulana kadar MOCK_SUPPLIER_EMAIL, MOCK_LISTING, MOCK_ORDERS,
MOCK_FINANCIALS Railway'de KALDIRILMAYACAK. Bu değişikliklerin hiçbiri bu
flag'lere dokunmayı gerektirmiyor — dokunan bir kod önerisi çıkarsa önce
Berkin'e sorulacak.

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

- [x] **GAP-6 (Küçük) — TAMAMLANDI (21 Temmuz 2026, commit `06ab94b`):**
      `orkestrator._check_pending_approvals()` artık tedarikçi (research_found
      sayısı, Supabase), mail ve proforma (get_mail_onay_status_counts() /
      get_proforma_onay_status_counts(), Sheets) için gerçek sayıları
      döndürüyor. Gmail hatırlatma maili artık doğru bekleyen sayısını
      gösteriyor.

- [x] **GAP-7 (TEMEL, KARAR VERİLDİ) — TAMAMLANDI
      (21 Temmuz 2026, commit `861e442` + script `483b677`):**
      Durum sözlüğü standardizasyonu. Şu an her sheet'te farklı durum
      kelimeleri var (beklemede/onaylandı/reddedildi, pending/sent/approved,
      research_found/inquiry_sent/completed vb.) — bunlar TEK bir standart
      kelime setine indirilecek:

      - Aksiyon dropdown'u (Berkin'in yazdığı, TÜM sheet'lerde aynı):
        BEKLEMEDE, ONAY, RED — her zaman geri yazılabilir.
      - Sistem Durumu dropdown'u (sistemin yazdığı, TÜM sheet'lerde aynı):
        BEKLEMEDE, İŞLENİYOR, TAMAMLANDI, İPTAL
      - Alt-aşama detayı (hangi mail gönderildi, Gmail yanıtı geldi mi vb.)
        dropdown'dan kaldırılıp her sheette zaten var olan "Not" kolonuna
        serbest metin olarak taşınacak.

      Kapsam:
      1. [x] `core/sheets_client.py`'ye merkezi `SYSTEM_DURUM_MAP` +
         `map_sistem_durum()` eklendi, Sheet1/2/4 mirror fonksiyonları artık
         bunu kullanıyor (eskiden birbiriyle tutarsız ayrı `STATUS_MAP`'ler
         vardı). Ortak `parse_aksiyon()` (case-insensitive, Türkçe İ/ı güvenli)
         tüm 4 sheet'in approval-okuma fonksiyonunda kullanılıyor.
      2. [x] `_setup_validations()`'daki dropdown value listeleri yeni
         standarda göre güncellendi.
      3. [x] Migration script'i (scripts/migrate_status_vocabulary.py) Berkin
         tarafından local ortamında çalıştırıldı (21 Temmuz 2026). Sonuç: Sheet1
         (0 satır — periyodik mirror zaten normalize etmişti), Sheet2 (0 satır —
         aynı sebep), Sheet3 (5 satır güncellendi — bu sheet'in periyodik mirror'ı
         olmadığı için gerçekten gerekliydi: sent→TAMAMLANDI, pending→BEKLEMEDE),
         Sheet4 (0 satır — mirror_proforma_onay zaten normalize etmişti). Sheet1/2/4
         dual-purpose kolonlar olduğu için (Berkin'in yazdığı ONAY/RED kalıcı
         değil — bir sonraki orkestratör cron'unda otomatik olarak sistem durumuna
         çevriliyor) bu üç sheet'te gözlemlenen herhangi bir 'eski görünüm' bir
         sonraki mirror'da kendiliğinden düzelir, ekstra aksiyon gerekmez.
      4. [x] **TASARIM KARARI:** Supabase tablolarındaki iç status
         değerleri (`products.status`, `supplier_contacts.status`,
         `approval_queue.status`, `mail_approvals.onay_durumu`,
         `proforma_offers.status`) DEĞİŞMEDİ — bu string'ler kodun her
         yerinde `.eq("status", ...)` sorgularında kullanıldığı için
         değiştirmenin blast radius'u bu oturumun kapsamı dışındaydı.
         SADECE Sheets görünüm katmanı (kullanıcıya gösterilen metin +
         aksiyon dropdown parse mantığı) standardize edildi.
      5. [x] **Sheet4 (Proforma) K kolonu ayrımı çözüldü:** K kolonunun
         periyodik bir mirror'ı yoktu (Sheet1/2'nin aksine), bu yüzden
         Berkin'in yazdığı ONAY/RED işlendikten sonra hiçbir zaman sistem
         durumuna dönüşmeden K'da asılı kalıyordu — canlı veride bir
         satırda "ONAY" görülmesinin sebebi buydu. Yeni bir kolon EKLEMEK
         yerine (Sheet1/2'de zaten böyle ikinci bir kolon yok), Sheet4'e
         Sheet1/2 ile birebir aynı pattern uygulandı: `mirror_proforma_onay()`
         eklendi ve orkestratörün her cron cycle'ında Sheet1/2 gibi Sheet4'ü
         de proforma_offers'tan tazelemesi sağlandı. K kolonu Sheet1 D /
         Sheet2 P ile aynı şekilde dual-purpose kalmaya devam ediyor
         (Berkin'in aksiyonu → orkestratör okur/işler → bir sonraki mirror
         sistem durumuna çevirir). `_process_proforma_approvals_step()`
         artık onay/red notunu da Supabase'e yazıyor (yeni periyodik
         mirror'ın Berkin'in notunu üzerine yazmaması için).

- [x] **GAP-8 — TAMAMLANDI (commit `876e1b0`):** Ürün onayı artık tek
      yönlü değil. `orkestrator._process_urun_approvals()` Sheet 1'deki
      aksiyonu her okuduğunda approval_queue'nun GÜNCEL durumuyla
      karşılaştırıp gerekirse tersine çeviriyor: approved→rejected'ta
      oluşturulan `products` kaydı silinmiyor, `delisted`'a çekiliyor (iz
      kalıyor); rejected→approved'da aynı isimli `products` kaydı varsa
      `approved`'e geri dönüyor, yoksa yeniden oluşturuluyor. Reversal'lar
      log'da açıkça görünüyor ("Ürün onayı geri alındı: ... (approved→rejected)").
      `docs/infrastructure/SUPABASE.md`'de `delisted`'ın artık "iptal edilen
      onay" anlamında da kullanıldığı not edildi.

- [x] **GAP-9 — TAMAMLANDI (commit `01e4689` migration, `b188275` kod):**
      Tedarikçi RED yazıldığında, kontak zaten ilerlemişse (test_sent veya
      sonrası — `tm_id` atanmış), `tedarikci.py` Faz 6
      (`_phase6_handle_rejection_notices`) Claude Haiku ile kibar bir
      red/vazgeçme maili taslağı üretip Sheet3'e yeni bir onay satırı
      (`mail_turu='red_bildirimi'`, mevcut tm_id yeniden kullanılıp Not
      kolonuna "Orijinal TM-ID: ..." referansı yazılıyor — GAP-14'ü
      büyütmemek için yeni TM-ID üretilmiyor) olarak düşüyor — diğer tüm
      dışarı giden maillerle aynı prensip: Berkin onaylamadan hiçbir mail
      gönderilmez. Onaylanınca gönderim mevcut Faz 3 akışı içinde otomatik
      oluyor (subject/body `mail_turu`'ne göre seçiliyor, `supplier_contacts.status`
      'rejected' olarak kalıyor). Migration: `rejection_notice_drafted`
      kolonu (006_supplier_contacts_rejection_notice.sql, Berkin tarafından
      Supabase'de manuel çalıştırılacak).

- [ ] **GAP-10 (Test aşamasında kabul edilebilir, M5 ÖNCESİ ZORUNLU):**
      Mail onayında Gmail yanıtı içerik kontrolü yok (her yanıt otomatik
      onay sayılıyor), red seçeneği yok. Şirket kurma/canlı satış öncesi
      eklenmesi ZORUNLU — Claude ile yanıtın onay/red niyetini sınıflandır,
      Sheet3 Excel Onay'a RED de yazılabilsin.

- [x] **GAP-11 — TAMAMLANDI (commit `4b32cdc`):** Proforma çoklu-onay engeli
      + red sonrası otomatik fallback. Bir proforma onaylandığında aynı
      ürünün diğer pending proformaları otomatik `rejected` yapılıyor
      (`_cancel_sibling_pending_proformas`, Sheet4 mirror'ı bir sonraki
      run'da İPTAL gösterir). Bir ürün için tüm proforma/tedarikçi yolları
      tükendiğinde (pending proforma yok VE `rejected` olmayan aktif
      supplier_contacts yok) `_check_and_requeue_if_exhausted`, paylaşılan
      `_requeue_product_for_sourcing` helper'ıyla ürünü `approved`'e geri
      çekiyor. Bunun işlemesi için `tedarikci.py._phase1_supplier_research()`
      artık sadece `rejected` OLMAYAN kontakları "zaten araştırıldı" sayıyor.

- [x] **GAP-12 — TAMAMLANDI (commit `09005b9`, altyapı `a6bab17`):**
      `orkestrator._process_urun_approvals()` artık `request_type`'a göre
      dispatch yapıyor (`_handle_product_approval_row` /
      `_handle_restock_approval_row` / `_handle_return_approval_row`).
      `siparis.py._check_low_stock()`'un oluşturduğu `restock_request`
      onaylandığında artık anlamsız yeni bir "ürün" yaratmıyor — AYNI
      `product_id`'yi `_requeue_product_for_sourcing` ile tekrar tedarikçi
      araştırma kuyruğuna sokuyor. (`preferred_suppliers` tabanlı tedarikçi
      önerisi kapsam dışı bırakıldı — M5+ konusu, GAP-12'nin çekirdek amacı
      olan "duplike ürün yaratma" bug'ı çözüldü.)

- [x] **GAP-13 — TAMAMLANDI (commit `22a8053`):** Gerçek webhook/API
      entegrasyonu olmadan otomatik iade algılama mümkün değil. Minimal
      manuel scaffold eklendi: `scripts/manual_return.py --order-id
      --product-id --quantity`, `approval_queue`'ya
      `request_type='return_manual'` satırı düşürüyor (mevcut
      `restock_request` pattern'iyle aynı — Sheet1'e normal mirror'lanır,
      skor kolonları boş kalır). Onaylandığında `_handle_return_approval_row`
      + `_process_return_approval`: `orders.status→returned`,
      `products.stock_count` geri artırılır, `financials`'a negatif "iade"
      kaydı düşer. Gerçek otomasyon (webhook) M6'da gerçek API'lerle
      gelecek. **Not:** `financials` insert alanları bu oturumda
      `agents/finans.py`'nin zaten kullandığı şema (ground truth kabul
      edildi, Berkin onayıyla) — bkz. güncellenmiş GAP-3.

- [ ] **GAP-14 (Düşük Öncelik — Race Condition):** Sheet3'te (Mail Onay)
      aynı TM-ID'nin (TM-004) iki farklı contact_id için iki kez üretildiği
      gözlemlendi (21 Temmuz 2026, iki satır 1 dakika arayla oluşturulmuş).
      Kök sebep muhtemelen `agents/tedarikci.py` → `_get_next_tm_id()`'nin
      `supplier_contacts` tablosundaki mevcut `tm_id` sayısını sayıp +1
      yaparak yeni ID üretmesi — eğer `_phase2_send_test_mails()` aynı anda
      (veya çok kısa aralıkla) iki kez tetiklenirse (örn. manuel + cron
      çakışması, ya da aynı cron run içinde iki ürün için art arda çağrılırken
      ikisi de sayıyı DB'ye yazılmadan önce okursa) aynı sayı üretilebilir.
      Şu an ZARARSIZ (iki satır farklı contact_id'ye işaret ediyor, karışıklık
      yaratmıyor) ama TM-ID'nin unique olması beklentisini bozuyor
      (mail_approvals.tm_id UNIQUE constraint'i bir gün bu yüzden insert
      hatası verebilir — upsert on_conflict='tm_id' kullanıldığı için şu an
      ikinci satır ilkinin üzerine yazıyor olabilir, bu da veri kaybına yol
      açabilir). Düzeltme: `_get_next_tm_id()`'yi count-based yerine
      Postgres sequence veya `INSERT ... RETURNING` ile atomik hale getir,
      ya da tm_id üretimini DB tarafında (default değer / trigger) yap.

Kod implementasyonu ayrı, odaklı Claude Code oturumlarına bölündü — GAP-7
(durum standardizasyonu) her şeyin temeli olduğu için İLK yapıldı, GAP-8/9
sonraki oturumda, GAP-11/12/13 (ortak "ürünü yeniden tedarikçi
araştırmasına sokma" mekanizmasını paylaştıkları için) aynı oturumda birlikte
tamamlandı. GAP-10 M5 öncesi zorunlu ama şimdilik backlog'da.

- [x] **GAP-3 — KAPATILDI (21 Temmuz 2026, Berkin kararıyla):** financials
      tablosu şema tutarsızlığı — docs/infrastructure/SUPABASE.md ile
      agents/finans.py kodu farklı alanlar kullanıyordu. Bu oturumda
      Supabase'in gerçek `information_schema.columns`'unu sorgulama girişimi
      yapıldı, ancak bu Claude Code oturumuna bağlı Supabase MCP bağlantısı
      eticaret-otomasyon projesine (`ypusjrrklxssjvefkypd`) erişemiyor
      (sadece ilgisiz başka projelere erişimi var) ve repo'da `.env` yok —
      yani canlı şema bu oturumda BAĞIMSIZ olarak teyit edilemedi. Berkin'e
      soruldu: `agents/finans.py._write_financials`'ın zaten prodüksiyonda
      kullandığı alanlar (`week_start`, `month`, `category`, `platform`,
      `amount_tl`, `description`, `source`, `tax_category`) ground truth
      kabul edilsin dendi — kod hatasız çalıştığına göre bu alanlar gerçek
      şemayla eşleşiyor demektir. `docs/infrastructure/SUPABASE.md`'deki
      `financials` bölümü buna göre güncellendi (aşağıda), eski
      `category` değer listesi (`gelir_shopify` vb.) YANLIŞ olarak
      işaretlendi — kodun kullandığı gerçek değerler farklı
      (`platform_revenue`, banka girişlerinin kendi `category`'si,
      GAP-13'ün eklediği `iade`). GAP-13'ün financials insert'i de bu
      ground-truth şemaya göre yazıldı.

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
| 21 Temmuz 2026 | GAP-6..13 eklendi (mimari analiz + forklar netleştirildi), GAP-1/2 migration'ları uygulandı olarak işaretlendi, şirket kurulmadan önce güvenlik notu eklendi |
| 21 Temmuz 2026 | GAP-6 tamamlandı (commit `06ab94b`), GAP-7 kodu tamamlandı (commit `861e442`, migration script `483b677` — henüz çalıştırılmadı, Berkin onayı bekliyor) |
| 21 Temmuz 2026 | GAP-7 tam tamamlandı olarak işaretlendi (migration script Berkin tarafından çalıştırıldı, Sheet3'te 5 satır güncellendi), GAP-14 eklendi (TM-ID race condition, düşük öncelik) |
| 21 Temmuz 2026 | GAP-8 tamamlandı (commit `876e1b0`) — ürün onayı geri alınabilir. GAP-9 tamamlandı (migration `01e4689`, kod `b188275`) — tedarikçi RED'inde onaya tabi red bildirimi maili; `rejection_notice_drafted` migration'ı Berkin onayı bekliyor (Supabase'de manuel çalıştırılacak) |
| 21 Temmuz 2026 | request_type dispatch altyapısı eklendi (commit `a6bab17`) — `_process_urun_approvals()` artık product_approval/restock_request/return_manual'ı ayrı handler'lara yönlendiriyor. GAP-11 tamamlandı (commit `4b32cdc`) — proforma çoklu-onay engeli + red sonrası otomatik fallback, paylaşılan `_requeue_product_for_sourcing` helper'ı + tedarikci.py Faz 1 kontrolü güncellendi. GAP-12 tamamlandı (commit `09005b9`) — kritik stok onayı artık duplike ürün yaratmıyor, gerçek yeniden tedarik tetikliyor. GAP-13 tamamlandı (commit `22a8053`) — `scripts/manual_return.py` + iade onay handler'ı. GAP-3 kapatıldı — financials şeması bu oturumda Supabase'e erişilemediği için `agents/finans.py` kodu ground truth kabul edilerek (Berkin onayıyla) dokümante edildi. |
