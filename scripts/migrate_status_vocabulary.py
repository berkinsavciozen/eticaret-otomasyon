"""
Tek seferlik veri migrasyonu (GAP-7): Google Sheets'teki eski, sheet'ten
sheet'e tutarsız durum kelimelerini (beklemede/onaylandı/reddedildi/pending/
sent/tamamlandı/mail gönderildi/takip gönderildi/ONAY karışık) yeni standart
sözlüğe çevirir:

  - Aksiyon (Berkin'in yazdığı):     BEKLEMEDE / ONAY / RED
  - Sistem Durumu (sistemin yazdığı): BEKLEMEDE / İŞLENİYOR / TAMAMLANDI / İPTAL

Supabase'deki iç status string'leri (approval_queue.status,
supplier_contacts.status, mail_approvals.onay_durumu, proforma_offers.status)
DEĞİŞMİYOR — sadece Sheets'te GÖRÜNEN metin standardize ediliyor.

Sheet2'de (Tedarikçi Onay) kaybolan alt-aşama detayı ("mail gönderildi",
"takip gönderildi" gibi eski Durum değerleri İŞLENİYOR'a toplanıyor) Not
kolonunun başına "Durum: <eski_deger> (migration)" olarak taşınır.

ÇALIŞTIRMADAN ÖNCE: Berkin'in onayı gerekli — Google Sheets'e canlı yazıyor.

Kullanım:
    python scripts/migrate_status_vocabulary.py --dry-run   # sadece önizleme, yazmaz
    python scripts/migrate_status_vocabulary.py             # gerçekten yazar
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from core.sheets_client import (  # noqa: E402
    read_sheet, clear_and_write_sheet,
    TAB_URUN_ONAY, TAB_TEDARIKCI_ONAY, TAB_MAIL_ONAY, TAB_PROFORMA_ONAY,
    U_DURUM, T_DURUM, T_NOT, M_EXCEL_ONAY, M_ONAY_DURUMU, P_DURUM,
    SISTEM_BEKLEMEDE, SISTEM_ISLENIYOR, SISTEM_TAMAMLANDI, SISTEM_IPTAL,
    AKSIYON_BEKLEMEDE, AKSIYON_ONAY, AKSIYON_RED,
    build_durum_note,
)

SPREADSHEET_ID = os.getenv(
    "SHEETS_APPROVAL_QUEUE_ID", "1HfRKYMah7HcawCjmSYjE7OXMtOuvHQVJ25GH5zcTmvw"
)

# Eski (sistem tarafından yazılmış) değer → yeni Sistem Durumu.
SISTEM_LEGACY_MAP = {
    "beklemede":        SISTEM_BEKLEMEDE,
    "pending":          SISTEM_BEKLEMEDE,
    "research_found":   SISTEM_BEKLEMEDE,
    "onaylandı":        SISTEM_ISLENIYOR,
    "approved":         SISTEM_ISLENIYOR,
    "mail gönderildi":  SISTEM_ISLENIYOR,
    "takip gönderildi": SISTEM_ISLENIYOR,
    "test_sent":        SISTEM_ISLENIYOR,
    "inquiry_sent":     SISTEM_ISLENIYOR,
    "followup_sent":    SISTEM_ISLENIYOR,
    "tamamlandı":       SISTEM_TAMAMLANDI,
    "completed":        SISTEM_TAMAMLANDI,
    "sent":             SISTEM_TAMAMLANDI,
    "reddedildi":       SISTEM_IPTAL,
    "rejected":         SISTEM_IPTAL,
}

# Alt-aşama detayı taşıyan eski değerler — dönüşümde Not kolonuna taşınır.
SUB_STAGE_VALUES = {"mail gönderildi", "takip gönderildi", "test_sent", "inquiry_sent", "followup_sent"}

# Eski (Berkin tarafından yazılmış) değer → yeni Aksiyon.
AKSIYON_LEGACY_MAP = {
    "onay":       AKSIYON_ONAY,
    "approved":   AKSIYON_ONAY,
    "onaylandı":  AKSIYON_ONAY,
    "red":        AKSIYON_RED,
    "rejected":   AKSIYON_RED,
    "reddedildi": AKSIYON_RED,
    "beklemede":  AKSIYON_BEKLEMEDE,
    "pending":    AKSIYON_BEKLEMEDE,
}

_ALREADY_NEW = {
    SISTEM_BEKLEMEDE, SISTEM_ISLENIYOR, SISTEM_TAMAMLANDI, SISTEM_IPTAL,
    AKSIYON_ONAY, AKSIYON_RED,
}


def _migrate_sistem_deger(raw: str) -> str:
    key = (raw or "").strip()
    if not key or key in _ALREADY_NEW:
        return key
    return SISTEM_LEGACY_MAP.get(key.lower(), key)


def _migrate_aksiyon_deger(raw: str) -> str:
    key = (raw or "").strip()
    if not key or key in _ALREADY_NEW:
        return key
    return AKSIYON_LEGACY_MAP.get(key.lower(), key)


def migrate_sheet1(dry_run: bool):
    """Sheet1 (Ürün Onay) — Durum (D) dual-purpose kolon, sistem durumu olarak çevrilir."""
    rows = read_sheet(SPREADSHEET_ID, f"'{TAB_URUN_ONAY}'!A1:AA500")
    if len(rows) <= 1:
        print("Sheet1 (Ürün Onay): veri yok, atlandı")
        return
    changed = 0
    for row in rows[1:]:
        if len(row) <= U_DURUM:
            continue
        old = row[U_DURUM]
        new = _migrate_sistem_deger(old)
        if new != old:
            print(f"  [Sheet1] {row[0] if row else '?'}: {old!r} -> {new!r}")
            row[U_DURUM] = new
            changed += 1
    print(f"Sheet1 (Ürün Onay): {changed} satır güncellenecek")
    if not dry_run and changed:
        clear_and_write_sheet(SPREADSHEET_ID, f"'{TAB_URUN_ONAY}'!A1", rows)


def migrate_sheet2(dry_run: bool):
    """Sheet2 (Tedarikçi Onay) — Durum (P) dual-purpose kolon; alt-aşama detayı Not'a (Q) taşınır."""
    rows = read_sheet(SPREADSHEET_ID, f"'{TAB_TEDARIKCI_ONAY}'!A1:R500")
    if len(rows) <= 1:
        print("Sheet2 (Tedarikçi Onay): veri yok, atlandı")
        return
    changed = 0
    for row in rows[1:]:
        if len(row) <= T_DURUM:
            continue
        row.extend([""] * (18 - len(row)))
        old = row[T_DURUM]
        new = _migrate_sistem_deger(old)
        if new != old:
            print(f"  [Sheet2] {row[0] if row else '?'}: {old!r} -> {new!r}")
            if old.strip().lower() in SUB_STAGE_VALUES:
                row[T_NOT] = build_durum_note(old.strip(), row[T_NOT], when="migration")
            row[T_DURUM] = new
            changed += 1
    print(f"Sheet2 (Tedarikçi Onay): {changed} satır güncellenecek")
    if not dry_run and changed:
        clear_and_write_sheet(SPREADSHEET_ID, f"'{TAB_TEDARIKCI_ONAY}'!A1", rows)


def migrate_sheet3(dry_run: bool):
    """Sheet3 (Mail Onay) — Excel Onay (G) aksiyon, Onay Durumu (I) sistem durumu, ayrı kolonlar."""
    rows = read_sheet(SPREADSHEET_ID, f"'{TAB_MAIL_ONAY}'!A1:K500")
    if len(rows) <= 1:
        print("Sheet3 (Mail Onay): veri yok, atlandı")
        return
    changed = 0
    for row in rows[1:]:
        if len(row) <= M_ONAY_DURUMU:
            continue
        row.extend([""] * (11 - len(row)))
        old_durum = row[M_ONAY_DURUMU]
        new_durum = _migrate_sistem_deger(old_durum)
        old_excel = row[M_EXCEL_ONAY]
        new_excel = _migrate_aksiyon_deger(old_excel)
        if new_durum != old_durum or new_excel != old_excel:
            print(f"  [Sheet3] {row[0] if row else '?'}: Onay Durumu {old_durum!r} -> {new_durum!r}, "
                  f"Excel Onay {old_excel!r} -> {new_excel!r}")
            row[M_ONAY_DURUMU] = new_durum
            row[M_EXCEL_ONAY]  = new_excel
            changed += 1
    print(f"Sheet3 (Mail Onay): {changed} satır güncellenecek")
    if not dry_run and changed:
        clear_and_write_sheet(SPREADSHEET_ID, f"'{TAB_MAIL_ONAY}'!A1", rows)


def migrate_sheet4(dry_run: bool):
    """
    Sheet4 (Proforma Onay) — Durum (K) dual-purpose kolon. Şu an canlı veride
    en az bir satırda "ONAY" (Berkin'in aksiyonu) var, diğerlerinde muhtemelen
    "beklemede" gibi sistem kelimeleri — ikisini ayırt etmek için önce ONAY/RED
    olup olmadığına bakılır, değilse sistem durumu olarak çevrilir.
    """
    rows = read_sheet(SPREADSHEET_ID, f"'{TAB_PROFORMA_ONAY}'!A1:M500")
    if len(rows) <= 1:
        print("Sheet4 (Proforma Onay): veri yok, atlandı")
        return
    changed = 0
    for row in rows[1:]:
        if len(row) <= P_DURUM:
            continue
        row.extend([""] * (13 - len(row)))
        old = (row[P_DURUM] or "").strip()
        if old.upper() in ("ONAY", "RED"):
            new = _migrate_aksiyon_deger(old)
        else:
            new = _migrate_sistem_deger(old)
        if new != old:
            print(f"  [Sheet4] {row[0] if row else '?'}: {old!r} -> {new!r}")
            row[P_DURUM] = new
            changed += 1
    print(f"Sheet4 (Proforma Onay): {changed} satır güncellenecek")
    if not dry_run and changed:
        clear_and_write_sheet(SPREADSHEET_ID, f"'{TAB_PROFORMA_ONAY}'!A1", rows)


def main():
    dry_run = "--dry-run" in sys.argv
    label = "[DRY RUN] " if dry_run else ""
    print(f"{label}Durum sözlüğü migrasyonu başlıyor — spreadsheet: {SPREADSHEET_ID}\n")

    migrate_sheet1(dry_run)
    migrate_sheet2(dry_run)
    migrate_sheet3(dry_run)
    migrate_sheet4(dry_run)

    if dry_run:
        print("\nDRY RUN tamamlandı — hiçbir şey yazılmadı. "
              "Gerçek çalıştırma için --dry-run bayrağı olmadan çalıştır.")
    else:
        print("\nMigrasyon tamamlandı.")


if __name__ == "__main__":
    main()
