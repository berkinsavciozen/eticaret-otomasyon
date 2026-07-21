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

- [x] **GAP-7 (TEMEL, KARAR VERİLDİ) — KOD TAMAMLANDI, MİGRASYON BEKLİYOR
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
      3. [x] **Migration script'i YAZILDI, `--dry-run` ile mock veriyle test
         edildi, ama gerçek spreadsheet'e (ID:
         1HfRKYMah7HcawCjmSYjE7OXMtOuvHQVJ25GH5zcTmvw) KARŞI HENÜZ
         ÇALIŞTIRILMADI** — `scripts/migrate_status_vocabulary.py`
         (commit `483b677`). Bu oturumda Railway/Sheets credential'ları
         mevcut değildi, o yüzden gerçek çalıştırma Berkin'in onayı +
         kendi ortamında (veya credential'ları olan bir sonraki oturumda)
         yapılması gerekiyor. Çalıştırılana kadar canlı sheet'te eski
         kelimeler (Sheet1 "onaylandı"/"reddedildi", Sheet2 "tamamlandı",
         Sheet3 "sent"/"pending", Sheet4 "ONAY") durmaya devam eder — kod
         hem yeni hem eski kelimeleri okuyabildiği için (geriye dönük
         uyumluluk) bu functional bir sorun yaratmaz, sadece görünüm
         migrasyon çalışana kadar karışık kalır.
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

- [ ] **GAP-8 (KARAR VERİLDİ — geri alınabilir yapılacak):** Ürün onayı
      artık tek yönlü değil. Berkin ONAY yazdıktan sonra fikrini değiştirip
      RED yazarsa: oluşturulan `products` kaydı silinmez, durumu (GAP-7
      sonrası) İPTAL'e çekilir (iz kalır). RED'den ONAY'a dönerse de aynı
      şekilde tersine işlesin. `orkestrator._process_urun_approvals()`'ın
      "sadece hâlâ pending olanı işle" mantığı kaldırılıp her yönde durum
      senkronu yapacak şekilde güncellenecek.

- [ ] **GAP-9 (KARAR VERİLDİ — onaya tabi red maili):** Tedarikçi RED
      yazıldığında, eğer kontak zaten ilerlemişse (test_sent veya sonrası),
      Claude ile kibar bir red/vazgeçme maili taslağı üretilip Sheet3'e
      yeni bir onay satırı (`mail_turu='red_bildirimi'`) olarak düşecek —
      diğer tüm dışarı giden maillerle aynı prensip: Berkin onaylamadan
      hiçbir mail gönderilmez.

- [ ] **GAP-10 (Test aşamasında kabul edilebilir, M5 ÖNCESİ ZORUNLU):**
      Mail onayında Gmail yanıtı içerik kontrolü yok (her yanıt otomatik
      onay sayılıyor), red seçeneği yok. Şirket kurma/canlı satış öncesi
      eklenmesi ZORUNLU — Claude ile yanıtın onay/red niyetini sınıflandır,
      Sheet3 Excel Onay'a RED de yazılabilsin.

- [ ] **GAP-11 (KARAR VERİLDİ — eklenecek):** Proforma çoklu-onay engeli +
      red sonrası otomatik fallback. Bir tedarikçinin proformasını
      onaylamak, aynı ürünün diğer bekleyen proformalarını otomatik İPTAL
      yapacak. TÜM proformalar red olursa (başka bekleyen yoksa), ürün
      otomatik olarak yeniden tedarikçi araştırmasına düşecek
      (`iliski_tipi='reorder'`, mevcut alan zaten destekliyor).

- [ ] **GAP-12 (KARAR VERİLDİ — gerçek yeniden tedarik tetiklenecek):**
      `siparis.py._check_low_stock()` artık anlamsız yeni bir "ürün"
      yaratmayacak. Onaylanan restock talebi, AYNI `product_id`'yi tekrar
      tedarikçi araştırma kuyruğuna sokacak (`iliski_tipi='reorder'`),
      mümkünse `preferred_suppliers` tablosundan (M5+, var ama kullanılmıyor)
      bilinen iyi tedarikçi önerilecek.

- [ ] **GAP-13 (KARAR VERİLDİ — minimal scaffold eklenecek):** Gerçek
      webhook/API entegrasyonu olmadan otomatik iade algılama mümkün değil.
      Şimdilik: `approval_queue`'ya yeni `request_type='return_manual'` —
      Berkin bir iade fark ettiğinde manuel tetikleyebileceği basit bir giriş
      noktası. Onaylandığında: `orders.status→returned` (GAP-7 sonrası
      standart kelimeyle), `products.stock_count` geri artırılır,
      `financials`'a negatif "iade" kaydı düşer. Gerçek otomasyon (webhook)
      M6'da gerçek API'lerle gelecek.

Kod implementasyonu ayrı, odaklı Claude Code oturumlarına bölünecek —
GAP-7 (durum standardizasyonu) her şeyin temeli olduğu için İLK yapılacak,
diğerleri (GAP-8, GAP-9, GAP-11, GAP-12, GAP-13) ondan sonra bağımsız
oturumlarda. GAP-10 M5 öncesi zorunlu ama şimdilik backlog'da. GAP-6 küçük
olduğu için GAP-7 oturumuna bindirilebilir.

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
| 21 Temmuz 2026 | GAP-6..13 eklendi (mimari analiz + forklar netleştirildi), GAP-1/2 migration'ları uygulandı olarak işaretlendi, şirket kurulmadan önce güvenlik notu eklendi |
| 21 Temmuz 2026 | GAP-6 tamamlandı (commit `06ab94b`), GAP-7 kodu tamamlandı (commit `861e442`, migration script `483b677` — henüz çalıştırılmadı, Berkin onayı bekliyor) |
