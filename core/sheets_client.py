"""Google Sheets istemcisi — 5-sheet yapısı.

Sheet 1: Ürün Onay        — approval_queue (Fırsatçı çıktısı, deterministik skorlar)
Sheet 2: Tedarikçi Onay   — product × supplier kombinasyonları
Sheet 3: Mail Onay        — test mail onay akışı (Gmail + Excel çift onay)
Sheet 4: Proforma Onay    — proforma teklifleri karşılaştırma
Sheet 5: Dashboard        — pipeline özet + matris
"""

import os
from typing import Optional, List, Dict, Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from core.supabase_client import get_client as _get_supabase_client


# ── Sheet sekme isimleri ───────────────────────────────────────────────────────
TAB_URUN_ONAY       = "Ürün Onay"
TAB_TEDARIKCI_ONAY  = "Tedarikçi Onay"
TAB_MAIL_ONAY       = "Mail Onay"
TAB_PROFORMA_ONAY   = "Proforma Onay"
TAB_DASHBOARD       = "Dashboard"

# ── Sheet 1: Ürün Onay ────────────────────────────────────────────────────────
# Sütunlar: A–AA (27 kolon)
URUN_HEADER = [
    "ID",                    # A  0
    "Başlık",                # B  1
    "Kategori",              # C  2
    "Durum",                 # D  3
    "Öncelik Sırası",        # E  4
    "Öncelik Gerekçesi",     # F  5
    "Toplam Skor",           # G  6
    "Trend/40",              # H  7
    "  pytrends/20",         # I  8
    "  Rising/10",           # J  9
    "  Sosyal/10",           # K  10
    "  Sezon Cezası",        # L  11
    "Pazar/35",              # M  12
    "  Listing Sayısı",      # N  13
    "  Talep Skoru/20",      # O  14
    "  Fiyat Viabilite/15",  # P  15
    "Fizibilite/25",         # Q  16
    "  Marj %",              # R  17
    "  Marj Skoru/15",       # S  18
    "  Kargo Skoru/5",       # T  19
    "  Yasal Skoru/5",       # U  20
    "Sermaye OK",            # V  21
    "Tahmini Fiyat TL",      # W  22
    "Özet",                  # X  23
    "Reddet Notu",           # Y  24
    "Son Güncelleme",        # Z  25
    "Ekleme Tarihi",         # AA 26
]

# Kolon indeks sabitleri (Sheet 1)
U_ID              = 0
U_BASLIK          = 1
U_KATEGORI        = 2
U_DURUM           = 3
U_ONCELIK_SIRA    = 4
U_ONCELIK_GEREKCESI = 5
U_TOPLAM_SKOR     = 6
U_TREND           = 7
U_PYTRENDS        = 8
U_RISING          = 9
U_SOSYAL          = 10
U_SEZON_CEZA      = 11
U_PAZAR           = 12
U_LISTING         = 13
U_TALEP           = 14
U_FIYAT_VIA       = 15
U_FIZIBILITE      = 16
U_MARJ_PCT        = 17
U_MARJ_SKOR       = 18
U_KARGO_SKOR      = 19
U_YASAL_SKOR      = 20
U_SERMAYE_OK      = 21
U_TAHMINI_FIYAT   = 22
U_OZET            = 23
U_REDDET_NOTU     = 24
U_SON_GUNCELLEME  = 25
U_EKLEME_TARIHI   = 26

# ── Sheet 2: Tedarikçi Onay ───────────────────────────────────────────────────
# Sütunlar: A–R (18 kolon)
TEDARIKCI_HEADER = [
    "ID",                    # A  0
    "Ürün ID",               # B  1
    "Ürün Başlığı",          # C  2
    "Tedarikçi Adı",         # D  3
    "Platform",              # E  4
    "İlişki Tipi",           # F  5  (new / known_new_product / reorder)
    "Önceki Sipariş Ref",    # G  6
    "URL",                   # H  7
    "Tahmini Birim (USD)",   # I  8
    "MOQ",                   # J  9
    "Tedarikçi Skoru/100",   # K  10
    "  Rating/30",           # L  11
    "  Fiyat/30",            # M  12
    "  Teslimat/20",         # N  13
    "  Feedback/20",         # O  14
    "Durum",                 # P  15  (pending / approved / rejected)
    "Not",                   # Q  16
    "Tarih",                 # R  17
]

T_ID              = 0
T_URUN_ID         = 1
T_URUN_BASLIK     = 2
T_TEDARIKCI_ADI   = 3
T_PLATFORM        = 4
T_ILISKI_TIPI     = 5
T_ONCEKI_REF      = 6
T_URL             = 7
T_BIRIM_USD       = 8
T_MOQ             = 9
T_SKOR            = 10
T_RATING          = 11
T_FIYAT           = 12
T_TESLIMAT        = 13
T_FEEDBACK        = 14
T_DURUM           = 15
T_NOT             = 16
T_TARIH           = 17

# ── Sheet 3: Mail Onay ────────────────────────────────────────────────────────
# Sütunlar: A–K (11 kolon)
MAIL_HEADER = [
    "Test Mail ID",          # A  0  (TM-001 formatı)
    "Ürün ID",               # B  1
    "Ürün Başlığı",          # C  2
    "Tedarikçi Adı",         # D  3
    "Mail Türü",             # E  4  (ilk_temas / takip)
    "Test Gönderildi",       # F  5  (timestamp)
    "Excel Onay",            # G  6  (ONAY / boş)
    "Gmail Onay",            # H  7  (otomatik doldurulur)
    "Onay Durumu",           # I  8  (pending / approved / rejected)
    "Gerçek Gönderim Tarihi", # J 9
    "Not",                   # K  10
]

M_TM_ID           = 0
M_URUN_ID         = 1
M_URUN_BASLIK     = 2
M_TEDARIKCI_ADI   = 3
M_MAIL_TURU       = 4
M_TEST_GONDERILDI = 5
M_EXCEL_ONAY      = 6
M_GMAIL_ONAY      = 7
M_ONAY_DURUMU     = 8
M_GERCEK_GONDERIM = 9
M_NOT             = 10

# ── Sheet 4: Proforma Onay ────────────────────────────────────────────────────
# Sütunlar: A–M (13 kolon)
PROFORMA_HEADER = [
    "Proforma ID",                  # A  0
    "Ürün ID",                      # B  1
    "Ürün Başlığı",                 # C  2
    "Tedarikçi Adı",                # D  3
    "Teklif Fiyat (USD)",           # E  4
    "MOQ",                          # F  5
    "Teslim Süresi (gün)",          # G  6
    "Tahmini COGS (TL)",            # H  7
    "Tahmini Marj (%)",             # I  8
    "Fırsatçı Tahminiyle Fark",     # J  9
    "Durum",                        # K  10  (pending / approved / rejected)
    "Not",                          # L  11
    "Tarih",                        # M  12
]

P_ID              = 0
P_URUN_ID         = 1
P_URUN_BASLIK     = 2
P_TEDARIKCI_ADI   = 3
P_TEKLIF_FIYAT    = 4
P_MOQ             = 5
P_TESLIM_SURE     = 6
P_COGS            = 7
P_MARJ            = 8
P_FARK            = 9
P_DURUM           = 10
P_NOT             = 11
P_TARIH           = 12


# ── Standart durum sözlüğü (GAP-7) ─────────────────────────────────────────────
# Supabase'deki iç status string'leri (products.status, supplier_contacts.status,
# approval_queue.status, mail_approvals.onay_durumu, proforma_offers.status)
# DEĞİŞMİYOR. Burada standardize edilen SADECE Sheets görünüm katmanı:
#   1. Sistem Durumu — sistemin Supabase'den map'leyip yazdığı, TÜM sheet'lerde
#      aynı 4 değer.
#   2. Aksiyon — Berkin'in yazdığı, TÜM sheet'lerde aynı 3 değer, her zaman
#      geri yazılabilir (ONAY↔RED↔BEKLEMEDE serbestçe).
# Sheet1 (D), Sheet2 (P), Sheet4 (K) tek, dual-purpose bir kolon kullanır: aynı
# hücre hem Berkin'in aksiyonunu hem (bir sonraki mirror'da) sistemin durumunu
# taşır — mevcut Sheet1/2 pattern'i budur, Sheet4 de bu oturumda aynı pattern'e
# taşındı (bkz. mirror_proforma_onay). Sheet3'te bu ikisi zaten ayrı kolon
# (Excel Onay = aksiyon, Onay Durumu = sistem durumu).

AKSIYON_BEKLEMEDE = "BEKLEMEDE"
AKSIYON_ONAY      = "ONAY"
AKSIYON_RED       = "RED"
AKSIYON_DEGERLERI = [AKSIYON_BEKLEMEDE, AKSIYON_ONAY, AKSIYON_RED]

SISTEM_BEKLEMEDE  = "BEKLEMEDE"
SISTEM_ISLENIYOR  = "İŞLENİYOR"
SISTEM_TAMAMLANDI = "TAMAMLANDI"
SISTEM_IPTAL      = "İPTAL"
SISTEM_DURUM_DEGERLERI = [SISTEM_BEKLEMEDE, SISTEM_ISLENIYOR, SISTEM_TAMAMLANDI, SISTEM_IPTAL]


def _tr_upper(s: Optional[str]) -> str:
    """
    Türkçe İ/ı güvenli upper-case. Python'ın yerleşik .upper()/.lower() metodu
    'İ' (U+0130) karakterini locale-bağımsız case-fold kurallarına göre iki
    karaktere ('i' + combining dot) çeviriyor, bu da "İŞLENİYOR" gibi
    değerlerle round-trip karşılaştırmayı bozuyor. Bu fonksiyon önce
    i→İ / ı→I çevirip sonra upper() uygulayarak bunu güvenli hale getirir.
    """
    return (s or "").strip().replace("i", "İ").replace("ı", "I").upper()


def _tr_upper_set(values) -> set:
    return {_tr_upper(v) for v in values}


_AKSIYON_ONAY_ALIASES = _tr_upper_set(["onay", "approved", "onaylandı"])
_AKSIYON_RED_ALIASES  = _tr_upper_set(["red", "rejected", "reddedildi"])


def parse_aksiyon(value: Optional[str]) -> str:
    """
    Aksiyon hücresini (Berkin'in yazdığı) standart üç değerden birine çevirir:
    ONAY / RED / BEKLEMEDE. Case-insensitive, Türkçe İ/ı güvenli. Veri
    migrasyonu (scripts/migrate_status_vocabulary.py) tamamlanana kadar eski
    kelimeleri de (onaylandı/approved/reddedildi/rejected) kabul eder —
    geriye dönük uyumluluk için.
    Tüm 4 sheet'in approval-okuma fonksiyonu (process_urun_onay_approvals,
    process_tedarikci_onay_approvals, check_mail_onay_approvals,
    process_proforma_approvals) bunu kullanır.
    """
    v = _tr_upper(value)
    if v in _AKSIYON_ONAY_ALIASES:
        return AKSIYON_ONAY
    if v in _AKSIYON_RED_ALIASES:
        return AKSIYON_RED
    return AKSIYON_BEKLEMEDE


# Supabase/iç status değeri → Sheets'te gösterilen Türkçe sistem durumu.
SYSTEM_DURUM_MAP = {
    "pending":        SISTEM_BEKLEMEDE,
    "research_found": SISTEM_BEKLEMEDE,
    "approved":       SISTEM_ISLENIYOR,
    "test_sent":      SISTEM_ISLENIYOR,
    "inquiry_sent":   SISTEM_ISLENIYOR,
    "followup_sent":  SISTEM_ISLENIYOR,
    "sent":           SISTEM_TAMAMLANDI,
    "completed":      SISTEM_TAMAMLANDI,
    "rejected":       SISTEM_IPTAL,
}


def map_sistem_durum(raw_status: Optional[str]) -> str:
    """Supabase'in iç status değerini Sheets'te gösterilecek Türkçe sistem durumuna çevirir."""
    return SYSTEM_DURUM_MAP.get(raw_status or "", raw_status or "")


_OPEN_SISTEM_DURUM_ALIASES = _tr_upper_set(["", "beklemede", "işleniyor", "pending", "approved"])


def _is_open_sistem_durum(raw: Optional[str]) -> bool:
    """Onay Durumu hâlâ 'açık' mı (BEKLEMEDE/İŞLENİYOR) — kapanmış (TAMAMLANDI/İPTAL) satırları tekrar işlememek için."""
    return _tr_upper(raw) in _OPEN_SISTEM_DURUM_ALIASES


_PENDING_BUCKET_ALIASES  = _tr_upper_set(["", "beklemede", "pending"])
_APPROVED_BUCKET_ALIASES = _tr_upper_set(["işleniyor", "tamamlandı", "approved", "sent", "onaylandı"])


def build_durum_note(raw_status: str, existing_note: str = "", when: Optional[str] = None) -> str:
    """
    Sistem Durumu artık sadece 4 üst-seviye değer gösteriyor (BEKLEMEDE/
    İŞLENİYOR/TAMAMLANDI/İPTAL) — hangi alt-aşamada olunduğu bilgisi
    (örn. 'test_sent', 'inquiry_sent') dropdown'dan kalktı. Bu fonksiyon o
    bilgiyi Not kolonunun BAŞINA ekler, mevcut not içeriğinin üzerine yazmaz.
    """
    from datetime import datetime, timezone
    ts = when or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    tag = f"Durum: {raw_status} ({ts})"
    existing = (existing_note or "").strip()
    return f"{tag} | {existing}" if existing else tag


# ── Auth & service helpers ─────────────────────────────────────────────────────

def _get_credentials() -> Credentials:
    return Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"].strip(),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GMAIL_CLIENT_ID"].strip(),
        client_secret=os.environ["GMAIL_CLIENT_SECRET"].strip(),
    )


def get_sheets_service():
    return build(
        "sheets",
        "v4",
        credentials=_get_credentials(),
        cache_discovery=False,
    )


def get_gmail_service():
    return build(
        "gmail",
        "v1",
        credentials=_get_credentials(),
        cache_discovery=False,
    )

# ── Temel okuma/yazma fonksiyonları ────────────────────────────────────────────

def read_sheet(spreadsheet_id: str, range_name: str) -> List[List[str]]:
    """Sheets'ten satırları okur. Header dahil tüm satırları döner."""
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
    ).execute()
    return result.get("values", [])


def append_to_sheet(spreadsheet_id: str, range_name: str, values: List[List]):
    """Sheets'in sonuna yeni satırlar ekler."""
    service = get_sheets_service()
    body = {"values": values}
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


def clear_and_write_sheet(spreadsheet_id: str, range_name: str, values: List[List]):
    """Sheets aralığını temizler ve baştan yazar."""
    service = get_sheets_service()
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id, range=range_name
    ).execute()
    if values:
        body = {"values": values}
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()


def update_row(spreadsheet_id: str, tab: str, row_num: int, values: List):
    """1-indexed row_num'daki satırı günceller (header=1, ilk veri=2)."""
    service = get_sheets_service()
    range_name = f"'{tab}'!A{row_num}"
    body = {"values": [values]}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()


# ── Setup: ilk çalışmada tüm sekme başlıklarını yaz ──────────────────────────

def setup_all_sheets(spreadsheet_id: str):
    """
    Tüm 5 sekmeyi oluşturur (yoksa) ve header satırlarını yazar.
    Mevcut veriye dokunmaz.
    """
    required_tabs = [
        (TAB_URUN_ONAY,      URUN_HEADER),
        (TAB_TEDARIKCI_ONAY, TEDARIKCI_HEADER),
        (TAB_MAIL_ONAY,      MAIL_HEADER),
        (TAB_PROFORMA_ONAY,  PROFORMA_HEADER),
        (TAB_DASHBOARD,      ["Dashboard — E-Ticaret Otomasyon Pipeline"]),
    ]
    service = get_sheets_service()

    # 1. Mevcut sekmeleri öğren
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing_titles = {s["properties"]["title"] for s in spreadsheet.get("sheets", [])}

    # 2. Eksik sekmeleri oluştur (batchUpdate)
    missing = [t for t, _ in required_tabs if t not in existing_titles]
    if missing:
        requests_body = [
            {"addSheet": {"properties": {"title": tab_name}}}
            for tab_name in missing
        ]
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests_body},
        ).execute()

    # 3. Header satırlarını yaz (boşsa)
    for tab, header in required_tabs:
        try:
            existing = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=f"'{tab}'!A1:A1"
            ).execute()
            first_cell = (
                existing.get("values", [[""]])[0][0]
                if existing.get("values") else ""
            )
            if not first_cell:
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"'{tab}'!A1",
                    valueInputOption="USER_ENTERED",
                    body={"values": [header]},
                ).execute()
        except Exception as e:
            pass  # sekme henüz indexlenmemiş olabilir, bir sonraki cron'da tekrar dener

    # 4. Dropdown validation kur
    try:
        _setup_validations(spreadsheet_id, service)
    except Exception as e:
        pass  # validation hatası kritik değil


def _make_validation_request(sheet_id: int, col: int, values: list, strict: bool = True) -> dict:
    """Google Sheets setDataValidation batchUpdate request nesnesi üretir."""
    return {
        "setDataValidation": {
            "range": {
                "sheetId":          sheet_id,
                "startRowIndex":    1,      # header'ı atla
                "endRowIndex":      1000,
                "startColumnIndex": col,
                "endColumnIndex":   col + 1,
            },
            "rule": {
                "condition": {
                    "type":   "ONE_OF_LIST",
                    "values": [{"userEnteredValue": v} for v in values],
                },
                "showCustomUi": True,
                "strict":       strict,
            },
        }
    }


def _setup_validations(spreadsheet_id: str, service):
    """
    Kullanıcı-düzenlenebilir kolonlara dropdown validation ekler.
    Tüm sheetlerde status isimleri tutarlı olur.
    """
    # Numeric sheet ID'leri al
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    id_map = {
        s["properties"]["title"]: s["properties"]["sheetId"]
        for s in spreadsheet.get("sheets", [])
    }

    # Dual-purpose kolonlar (Sheet1 D, Sheet2 P, Sheet4 K): aynı hücre hem
    # Berkin'in aksiyonunu (BEKLEMEDE/ONAY/RED) hem bir sonraki mirror'da
    # sistemin durumunu (BEKLEMEDE/İŞLENİYOR/TAMAMLANDI/İPTAL) taşıyabilir —
    # dropdown her ikisini de kabul etmeli.
    DUAL_PURPOSE_DEGERLERI = AKSIYON_DEGERLERI + [
        v for v in SISTEM_DURUM_DEGERLERI if v not in AKSIYON_DEGERLERI
    ]

    requests = []

    # Sheet 1: Durum (D = 3)
    if TAB_URUN_ONAY in id_map:
        requests.append(_make_validation_request(
            id_map[TAB_URUN_ONAY], col=3,
            values=DUAL_PURPOSE_DEGERLERI
        ))

    # Sheet 2: Durum (P = 15)
    if TAB_TEDARIKCI_ONAY in id_map:
        requests.append(_make_validation_request(
            id_map[TAB_TEDARIKCI_ONAY], col=15,
            values=DUAL_PURPOSE_DEGERLERI
        ))

    # Sheet 3: Excel Onay (G = 6) — kullanıcı yazar, blank da geçerli
    if TAB_MAIL_ONAY in id_map:
        requests.append(_make_validation_request(
            id_map[TAB_MAIL_ONAY], col=6,
            values=AKSIYON_DEGERLERI, strict=False
        ))
        # Onay Durumu (I = 8) — sistem yönetir
        requests.append(_make_validation_request(
            id_map[TAB_MAIL_ONAY], col=8,
            values=SISTEM_DURUM_DEGERLERI, strict=False
        ))

    # Sheet 4: Durum (K = 10) — Sheet1/2 ile aynı dual-purpose pattern
    if TAB_PROFORMA_ONAY in id_map:
        requests.append(_make_validation_request(
            id_map[TAB_PROFORMA_ONAY], col=10,
            values=DUAL_PURPOSE_DEGERLERI
        ))

    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()


# ── Sheet 1: Ürün Onay ────────────────────────────────────────────────────────

def mirror_urun_onay(spreadsheet_id: str, rows_data: List[Dict[str, Any]]):
    """
    approval_queue verilerini Sheet 1'e yazar (clear + rewrite).
    rows_data: Supabase approval_queue kayıtları listesi.
    Scoring sub-parametreler metadata JSONB alanından okunur.
    """
    values = [URUN_HEADER]
    for r in rows_data:
        meta = r.get("metadata") or {}
        scoring = meta.get("scoring", {})
        trend   = scoring.get("trend", {})
        pazar   = scoring.get("pazar", {})
        fiz     = scoring.get("fizibilite", {})
        priority = meta.get("priority", {})

        values.append([
            str(r.get("id", "")),
            r.get("title", ""),
            r.get("category", ""),
            map_sistem_durum(r.get("status", "")),
            str(priority.get("rank", "")),
            priority.get("reason", ""),
            str(scoring.get("total", "")),
            str(trend.get("total", "")),
            str(trend.get("pytrends", "")),
            str(trend.get("rising", "")),
            str(trend.get("sosyal", "")),
            str(trend.get("sezon_ceza", "")),
            str(pazar.get("total", "")),
            str(pazar.get("listing_sayisi", "")),
            str(pazar.get("talep", "")),
            str(pazar.get("fiyat_via", "")),
            str(fiz.get("total", "")),
            str(fiz.get("marj_pct", "")),
            str(fiz.get("marj_skor", "")),
            str(fiz.get("kargo", "")),
            str(fiz.get("yasal", "")),
            "EVET" if meta.get("sermaye_ok") else "HAYIR",
            str(r.get("estimated_price_tl", meta.get("estimated_price_tl", ""))),
            r.get("summary", ""),
            r.get("decision_note", "") or "",
            str(r.get("updated_at", "")),
            str(r.get("created_at", "")),
        ])

    clear_and_write_sheet(spreadsheet_id, f"'{TAB_URUN_ONAY}'!A1", values)
    return len(rows_data)


def process_urun_onay_approvals(spreadsheet_id: str) -> tuple:
    """
    Sheet 1'deki Durum kolonunu okur.
    'approved' / 'rejected' olan ve Supabase'de hâlâ 'pending' olanları döner.
    Returns: (list of approved IDs with notes, list of rejected IDs with notes)
    """
    try:
        rows = read_sheet(spreadsheet_id, f"'{TAB_URUN_ONAY}'!A1:AA500")
    except Exception:
        return [], []

    approved, rejected = [], []
    for row in rows[1:]:
        if len(row) <= U_DURUM:
            continue
        row_id  = row[U_ID].strip() if len(row) > U_ID else ""
        aksiyon = parse_aksiyon(row[U_DURUM] if len(row) > U_DURUM else "")
        note    = row[U_REDDET_NOTU].strip() if len(row) > U_REDDET_NOTU else ""
        if not row_id or aksiyon == AKSIYON_BEKLEMEDE:
            continue
        if aksiyon == AKSIYON_ONAY:
            approved.append({"id": row_id, "note": note})
        else:
            rejected.append({"id": row_id, "note": note})
    return approved, rejected


# ── Sheet 2: Tedarikçi Onay ───────────────────────────────────────────────────

def mirror_tedarikci_onay(spreadsheet_id: str, rows_data: List[Dict[str, Any]]):
    """
    supplier_contacts verilerini Sheet 2'ye yazar (clear + rewrite).
    Supabase status → Türkçe Durum eşlemesi yapar.
    """
    values = [TEDARIKCI_HEADER]
    for r in rows_data:
        scoring = r.get("supplier_scoring") or {}
        if isinstance(scoring, str):
            import json as _json
            try:
                scoring = _json.loads(scoring)
            except Exception:
                scoring = {}
        supabase_status = r.get("status", "")
        display_status  = map_sistem_durum(supabase_status)
        values.append([
            str(r.get("id", "")),
            str(r.get("product_id", "")),
            r.get("product_name", ""),           # products tablosundan join edilmiş gelecek
            r.get("supplier_name", ""),
            r.get("platform", "alibaba"),
            r.get("iliski_tipi", "new"),
            "",                                   # önceki sipariş ref
            r.get("url", ""),
            str(r.get("birim_usd", "")),
            str(r.get("moq", "")),
            str(scoring.get("total", "")),
            str(scoring.get("rating", "")),
            str(scoring.get("fiyat", "")),
            str(scoring.get("teslimat", "")),
            str(scoring.get("feedback", "")),
            display_status,
            r.get("notes", ""),
            str(r.get("contacted_at", ""))[:16],
        ])
    clear_and_write_sheet(spreadsheet_id, f"'{TAB_TEDARIKCI_ONAY}'!A1", values)
    return len(rows_data)


def upsert_tedarikci_onay(spreadsheet_id: str, row_data: Dict[str, Any]):
    """
    Tedarikçi Onay sheet'ine yeni ürün×tedarikçi satırı ekler.
    Aynı ID varsa satırı günceller.
    """
    existing_rows = read_sheet(spreadsheet_id, f"'{TAB_TEDARIKCI_ONAY}'!A1:R500")
    row_id = str(row_data.get("id", ""))
    scoring = row_data.get("scoring", {})

    new_row = [
        row_id,
        str(row_data.get("product_id", "")),
        row_data.get("product_title", ""),
        row_data.get("supplier_name", ""),
        row_data.get("platform", ""),
        row_data.get("iliski_tipi", "new"),          # new / known_new_product / reorder
        row_data.get("onceki_siparis_ref", ""),
        row_data.get("url", ""),
        str(row_data.get("birim_usd", "")),
        str(row_data.get("moq", "")),
        str(scoring.get("total", "")),
        str(scoring.get("rating", "")),
        str(scoring.get("fiyat", "")),
        str(scoring.get("teslimat", "")),
        str(scoring.get("feedback", "")),
        row_data.get("durum", "beklemede"),
        row_data.get("not", ""),
        str(row_data.get("tarih", "")),
    ]

    # Var mı kontrol et
    for i, row in enumerate(existing_rows[1:], start=2):
        if row and row[T_ID] == row_id:
            update_row(spreadsheet_id, TAB_TEDARIKCI_ONAY, i, new_row)
            return

    # Yoksa append
    append_to_sheet(spreadsheet_id, f"'{TAB_TEDARIKCI_ONAY}'!A1", [new_row])


def process_tedarikci_onay_approvals(spreadsheet_id: str) -> tuple:
    """Sheet 2'de Durum kolonunu tarayarak approved/rejected kayıtları döner."""
    try:
        rows = read_sheet(spreadsheet_id, f"'{TAB_TEDARIKCI_ONAY}'!A1:R500")
    except Exception:
        return [], []

    approved, rejected = [], []
    for row in rows[1:]:
        if len(row) <= T_DURUM:
            continue
        row_id  = row[T_ID].strip() if len(row) > T_ID else ""
        aksiyon = parse_aksiyon(row[T_DURUM] if len(row) > T_DURUM else "")
        note    = row[T_NOT].strip() if len(row) > T_NOT else ""
        if not row_id or aksiyon == AKSIYON_BEKLEMEDE:
            continue
        if aksiyon == AKSIYON_ONAY:
            approved.append({"id": row_id, "note": note,
                             "product_id": row[T_URUN_ID] if len(row) > T_URUN_ID else ""})
        else:
            rejected.append({"id": row_id, "note": note})
    return approved, rejected


# ── Sheet 3: Mail Onay ────────────────────────────────────────────────────────

def append_mail_onay(spreadsheet_id: str, row_data: Dict[str, Any]):
    """
    Mail Onay sheet'ine test mail kaydı ekler.
    Dual-write (GAP-1): aynı kayıt mail_approvals (Supabase) tablosuna da yazılır.
    Sheets kullanıcı arayüzü, Supabase gerçek kaynak (tek yazıcı burası —
    BUG-4'teki prensiple tutarlı).
    """
    new_row = [
        row_data.get("tm_id", ""),           # TM-001 formatı
        str(row_data.get("product_id", "")),
        row_data.get("product_title", ""),
        row_data.get("supplier_name", ""),
        row_data.get("mail_turu", "ilk_temas"),
        str(row_data.get("test_gonderildi", "")),
        "",                                   # Excel Onay — Berkin doldurur
        "",                                   # Gmail Onay — otomatik
        SISTEM_BEKLEMEDE,                     # Onay Durumu
        "",                                   # Gerçek Gönderim Tarihi
        row_data.get("not", ""),
    ]
    append_to_sheet(spreadsheet_id, f"'{TAB_MAIL_ONAY}'!A1", [new_row])
    _upsert_mail_approval(row_data)


def _upsert_mail_approval(row_data: Dict[str, Any]):
    """mail_approvals tablosuna tm_id üzerinden insert/upsert eder."""
    tm_id = row_data.get("tm_id", "")
    if not tm_id:
        return
    try:
        client = _get_supabase_client()
        client.table("mail_approvals").upsert({
            "tm_id":                tm_id,
            "product_id":           row_data.get("product_id") or None,
            "supplier_contact_id":  row_data.get("supplier_contact_id") or None,
            "mail_turu":            row_data.get("mail_turu", "ilk_temas"),
            "email_body":           row_data.get("email_body"),
            "test_gonderildi_at":   row_data.get("test_gonderildi") or None,
            "note":                 row_data.get("not", ""),
        }, on_conflict="tm_id").execute()
    except Exception:
        pass  # Supabase yazımı ikincil — Sheets birincil arayüz olarak çalışmaya devam eder


def check_mail_onay_approvals(spreadsheet_id: str) -> tuple:
    """
    Sheet 3'te Excel Onay (aksiyon) = ONAY veya Gmail yanıtı gelmiş VE
    Onay Durumu hâlâ açık (BEKLEMEDE/İŞLENİYOR) olan satırları 'approved'
    olarak, Excel Onay = RED yazılan satırları 'rejected' olarak döner.
    RED bu fonksiyonda sadece mail_approvals.onay_durumu='rejected' olarak
    işaretlenip OKUNABİLİR hale getiriliyor — bu, Excel Onay'a RED yazılan
    (yani mail taslağının kendisi reddedilen) satırlar için; ayrı bir işleme
    henüz eklenmedi (GAP-9 farklı bir akış — tedarikçi kontağının Sheet 2'de
    RED'i sonrası red bildirimi maili taslağı, bkz. tedarikci.py Faz 6).
    """
    try:
        rows = read_sheet(spreadsheet_id, f"'{TAB_MAIL_ONAY}'!A1:K500")
    except Exception:
        return [], []

    approved, rejected = [], []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) <= M_ONAY_DURUMU:
            continue
        tm_id     = row[M_TM_ID].strip() if len(row) > M_TM_ID else ""
        excel_raw = row[M_EXCEL_ONAY] if len(row) > M_EXCEL_ONAY else ""
        gmail_ok  = row[M_GMAIL_ONAY].strip() if len(row) > M_GMAIL_ONAY else ""
        mevcut    = row[M_ONAY_DURUMU] if len(row) > M_ONAY_DURUMU else ""
        if not _is_open_sistem_durum(mevcut):
            continue

        mail_turu = row[M_MAIL_TURU] if len(row) > M_MAIL_TURU else ""

        aksiyon = parse_aksiyon(excel_raw)
        if aksiyon == AKSIYON_RED:
            rejected.append({
                "row_num": i,
                "tm_id": tm_id,
                "product_id": row[M_URUN_ID] if len(row) > M_URUN_ID else "",
                "product_title": row[M_URUN_BASLIK] if len(row) > M_URUN_BASLIK else "",
                "supplier_name": row[M_TEDARIKCI_ADI] if len(row) > M_TEDARIKCI_ADI else "",
                "mail_turu": mail_turu,
            })
            _sync_mail_approval_status(tm_id, onay_durumu="rejected")
            continue

        if aksiyon == AKSIYON_ONAY or gmail_ok:
            approved.append({
                "row_num": i,
                "tm_id": tm_id,
                "product_id": row[M_URUN_ID] if len(row) > M_URUN_ID else "",
                "product_title": row[M_URUN_BASLIK] if len(row) > M_URUN_BASLIK else "",
                "supplier_name": row[M_TEDARIKCI_ADI] if len(row) > M_TEDARIKCI_ADI else "",
                "mail_turu": mail_turu,
            })
            _sync_mail_approval_status(tm_id, onay_durumu="approved",
                                        excel_onay=(excel_raw.strip() or None),
                                        gmail_yaniti_alindi=bool(gmail_ok))
    return approved, rejected


def _sync_mail_approval_status(tm_id: str, **fields):
    """
    mail_approvals tablosunda tm_id eşleşen kaydı günceller (dual-write).
    Sheets'te değişen durum buraya da yansıtılır; Sheets birincil arayüz kalır.
    """
    if not tm_id:
        return
    update_data = {k: v for k, v in fields.items() if v is not None}
    if not update_data:
        return
    try:
        client = _get_supabase_client()
        client.table("mail_approvals").update(update_data).eq("tm_id", tm_id).execute()
    except Exception:
        pass  # Supabase yazımı ikincil


def update_mail_onay_status(spreadsheet_id: str, row_num: int,
                             status: str, gercek_gonderim: Optional[str] = None,
                             note: Optional[str] = None):
    """
    Mail Onay sheet'inde belirli satırın durumunu günceller.
    `status`: mail_approvals.onay_durumu için kullanılan iç (İngilizce) değer
    (ör. 'sent', 'approved', 'rejected') — Supabase'e olduğu gibi yazılır,
    Sheets hücresine yazılırken Türkçe sistem durumu karşılığına çevrilir.
    """
    rows = read_sheet(spreadsheet_id, f"'{TAB_MAIL_ONAY}'!A{row_num}:K{row_num}")
    if not rows:
        return
    row = rows[0] + [""] * (11 - len(rows[0]))  # padding
    row[M_ONAY_DURUMU]     = map_sistem_durum(status)
    row[M_GERCEK_GONDERIM] = gercek_gonderim or row[M_GERCEK_GONDERIM]
    row[M_NOT]             = note or row[M_NOT]
    update_row(spreadsheet_id, TAB_MAIL_ONAY, row_num, row)
    _sync_mail_approval_status(
        row[M_TM_ID],
        onay_durumu=status,
        gercek_gonderim_at=gercek_gonderim,
        note=note,
    )


# ── Sheet 4: Proforma Onay ────────────────────────────────────────────────────

def append_proforma_onay(spreadsheet_id: str, row_data: Dict[str, Any]):
    """Proforma Onay sheet'ine yeni proforma teklifi ekler."""
    firsatci_fiyat = float(row_data.get("firsatci_tahmini_tl", 0) or 0)
    cogs           = float(row_data.get("tahmini_cogs_tl", 0) or 0)
    fark           = round(cogs - firsatci_fiyat, 2) if firsatci_fiyat else ""

    new_row = [
        str(row_data.get("id", "")),
        str(row_data.get("product_id", "")),
        row_data.get("product_title", ""),
        row_data.get("supplier_name", ""),
        str(row_data.get("teklif_fiyat_usd", "")),
        str(row_data.get("moq", "")),
        str(row_data.get("teslim_sure_gun", "")),
        str(cogs or ""),
        str(row_data.get("tahmini_marj_pct", "")),
        str(fark),
        row_data.get("durum", SISTEM_BEKLEMEDE),
        row_data.get("not", ""),
        str(row_data.get("tarih", "")),
    ]
    append_to_sheet(spreadsheet_id, f"'{TAB_PROFORMA_ONAY}'!A1", [new_row])


def mirror_proforma_onay(spreadsheet_id: str, rows_data: List[Dict[str, Any]]):
    """
    proforma_offers verilerini Sheet 4'e yazar (clear + rewrite) — Sheet1/2 ile
    aynı pattern (GAP-7): K (Durum) kolonu dual-purpose — Berkin'in yazdığı
    aksiyonu (ONAY/RED) orkestratör her cron'da önce okuyup Supabase'e işler,
    bu fonksiyon SONRA çağrılıp K'yı güncel sistem durumuna (BEKLEMEDE/
    İŞLENİYOR/TAMAMLANDI/İPTAL) çevirir. Önceden Sheet4'ün periyodik bir
    mirror'ı yoktu — bu da Berkin'in yazdığı ONAY/RED'in işlendikten sonra
    hiç sistem durumuna dönüşmeden K'da asılı kalmasına yol açıyordu.
    rows_data: her satırda proforma_offers alanları + çağıranın eklediği
    product_title / supplier_name.
    """
    values = [PROFORMA_HEADER]
    for r in rows_data:
        values.append([
            str(r.get("id", "")),
            str(r.get("product_id", "")),
            r.get("product_title", ""),
            r.get("supplier_name", ""),
            str(r.get("teklif_fiyat_usd", "")),
            str(r.get("moq", "")),
            str(r.get("teslim_sure_gun", "")),
            str(r.get("tahmini_cogs_tl", "")),
            str(r.get("tahmini_marj_pct", "")),
            str(r.get("firsatci_tahmini_fark_tl", "")),
            map_sistem_durum(r.get("status", "")),
            r.get("note", "") or "",
            str(r.get("created_at", ""))[:16],
        ])
    clear_and_write_sheet(spreadsheet_id, f"'{TAB_PROFORMA_ONAY}'!A1", values)
    return len(rows_data)


def process_proforma_approvals(spreadsheet_id: str) -> tuple:
    """Sheet 4'te Durum kolonunu tarayarak approved/rejected kayıtları döner."""
    try:
        rows = read_sheet(spreadsheet_id, f"'{TAB_PROFORMA_ONAY}'!A1:M500")
    except Exception:
        return [], []

    approved, rejected = [], []
    for row in rows[1:]:
        if len(row) <= P_DURUM:
            continue
        row_id  = row[P_ID].strip() if len(row) > P_ID else ""
        aksiyon = parse_aksiyon(row[P_DURUM] if len(row) > P_DURUM else "")
        note    = row[P_NOT].strip() if len(row) > P_NOT else ""
        if not row_id or aksiyon == AKSIYON_BEKLEMEDE:
            continue
        if aksiyon == AKSIYON_ONAY:
            approved.append({"id": row_id, "note": note,
                             "product_id": row[P_URUN_ID] if len(row) > P_URUN_ID else ""})
        else:
            rejected.append({"id": row_id, "note": note})
    return approved, rejected


def get_mail_onay_status_counts(spreadsheet_id: str) -> tuple:
    """Sheet 3 Onay Durumu kolonundan (bekleyen, işlemde/tamamlanan) sayılarını döner."""
    try:
        rows = read_sheet(spreadsheet_id, f"'{TAB_MAIL_ONAY}'!A1:K500")
    except Exception:
        return 0, 0

    pending = approved = 0
    for row in rows[1:]:
        raw = row[M_ONAY_DURUMU] if len(row) > M_ONAY_DURUMU else ""
        norm = _tr_upper(raw)
        if norm in _PENDING_BUCKET_ALIASES:
            pending += 1
        elif norm in _APPROVED_BUCKET_ALIASES:
            approved += 1
    return pending, approved


def get_mail_onay_status_counts_supabase() -> tuple:
    """
    mail_approvals tablosundan (pending, approved) sayılarını döner.
    get_mail_onay_status_counts()'un Sheets'e bağımlı olmayan eşdeğeri.
    """
    try:
        client = _get_supabase_client()
        rows = client.table("mail_approvals").select("onay_durumu").execute()
    except Exception:
        return 0, 0

    pending = sum(1 for r in rows.data if r.get("onay_durumu") == "pending")
    approved = sum(1 for r in rows.data if r.get("onay_durumu") in ("approved", "sent"))
    return pending, approved


def get_proforma_onay_status_counts(spreadsheet_id: str) -> tuple:
    """Sheet 4 Durum kolonundan (bekleyen, işlemde/tamamlanan) sayılarını döner."""
    try:
        rows = read_sheet(spreadsheet_id, f"'{TAB_PROFORMA_ONAY}'!A1:M500")
    except Exception:
        return 0, 0

    pending = approved = 0
    for row in rows[1:]:
        raw = row[P_DURUM] if len(row) > P_DURUM else ""
        norm = _tr_upper(raw)
        if norm in _PENDING_BUCKET_ALIASES:
            pending += 1
        elif norm in _APPROVED_BUCKET_ALIASES:
            approved += 1
    return pending, approved


# ── Sheet 5: Dashboard ────────────────────────────────────────────────────────

def refresh_dashboard(spreadsheet_id: str, pipeline_data: Dict[str, Any]):
    """
    Dashboard sheet'ini yeniler.
    pipeline_data örnek:
    {
      "urun_pending": 3, "urun_approved": 10, "urun_rejected": 5,
      "tedarikci_pending": 2, "tedarikci_approved": 4,
      "mail_pending": 1, "mail_approved": 2,
      "proforma_pending": 0, "proforma_approved": 1,
      "last_updated": "2024-01-15 09:30",
      "product_supplier_matrix": [
        {"product": "X", "supplier": "Y", "status": "approved"},
        ...
      ]
    }
    """
    from datetime import datetime
    now = pipeline_data.get("last_updated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))

    values = [
        ["E-Ticaret Otomasyon — Pipeline Dashboard"],
        ["Son Güncelleme:", now],
        [],
        ["── KULLANICI REHBERİ ──"],
        ["Sheet", "Kolon", "Ne Yazmalısın", "Açıklama"],
        ["1 - Ürün Onay",       "Durum (D)",       "ONAY",  "Ürünü onaylar → Supabase'e products olarak geçer"],
        ["1 - Ürün Onay",       "Durum (D)",       "RED",   "Ürünü reddeder → approval_queue'dan çıkar"],
        ["2 - Tedarikçi Onay",  "Durum (P)",       "ONAY",  "Tedarikçiyi onaylar → test maili gönderilir"],
        ["2 - Tedarikçi Onay",  "Durum (P)",       "RED",   "Tedarikçiyi reddeder"],
        ["3 - Mail Onay",       "Excel Onay (G)",  "ONAY",  "Test mailini onaylar → gerçek tedarikçiye mail gider"],
        ["3 - Mail Onay",       "Excel Onay (G)",  "(boş)", "Gmail reply ile de onaylanabilir, o zaman boş bırak"],
        ["4 - Proforma Onay",   "Durum (K)",       "ONAY",  "Proformayı onaylar → sipariş akışı başlar"],
        ["4 - Proforma Onay",   "Durum (K)",       "RED",   "Proformayı reddeder"],
        [],
        ["── DURUM ANLAMI ──"],
        ["Durum",      "Açıklama"],
        ["BEKLEMEDE",  "Sistem yazdı (senin kararını bekliyor) veya sen henüz aksiyon yazmadın"],
        ["ONAY",       "Sen yazdın → orkestratör bir sonraki cron'da işleyecek (RED'e veya tekrar BEKLEMEDE'ye geri dönebilirsin)"],
        ["RED",        "Sen yazdın → orkestratör bir sonraki cron'da işleyecek (ONAY'a veya tekrar BEKLEMEDE'ye geri dönebilirsin)"],
        ["İŞLENİYOR",  "Orkestratör işledi, süreç devam ediyor (Supabase güncellendi)"],
        ["TAMAMLANDI", "Süreç bu kayıt için bitti"],
        ["İPTAL",      "Reddedildi / iptal edildi (Supabase güncellendi)"],
        [],
        ["── PIPELINE ÖZETİ ──"],
        ["Aşama",             "Bekleyen", "Onaylanan", "Reddedilen"],
        ["Ürün Onay",
         pipeline_data.get("urun_pending", ""),
         pipeline_data.get("urun_approved", ""),
         pipeline_data.get("urun_rejected", "")],
        ["Tedarikçi Onay",
         pipeline_data.get("tedarikci_pending", ""),
         pipeline_data.get("tedarikci_approved", ""),
         "—"],
        ["Mail Onay",
         pipeline_data.get("mail_pending", ""),
         pipeline_data.get("mail_approved", ""),
         "—"],
        ["Proforma Onay",
         pipeline_data.get("proforma_pending", ""),
         pipeline_data.get("proforma_approved", ""),
         "—"],
        [],
        ["── ÜRÜN × TEDARİKÇİ MATRİSİ ──"],
        ["Ürün", "Tedarikçi", "Durum", "Skor"],
    ]

    matrix = pipeline_data.get("product_supplier_matrix", [])
    for item in matrix:
        values.append([
            item.get("product", ""),
            item.get("supplier", ""),
            item.get("status", ""),
            str(item.get("score", "")),
        ])

    clear_and_write_sheet(spreadsheet_id, f"'{TAB_DASHBOARD}'!A1", values)
