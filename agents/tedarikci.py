# Tedarikçi Agent — M4
# Görev: Onaylanan ürünler için tedarikçi araştırması (Alibaba scraping),
#         ürün×tedarikçi Sheet 2'ye yazma, TM-ID test maili, Sheet 3 onay akışı,
#         proforma teklif işleme (Sheet 4).
# Çalışma sıklığı: Saatte 1 kez (Railway cron: 0 * * * *)
#
# Akış:
#   Faz 1: Alibaba scraping → supplier_contacts (Supabase) + Sheet 2 (Tedarikçi Onay)
#   Faz 2: Sheet 2 onaylı tedarikçiler → TM-ID test maili → Sheet 3 (Mail Onay)
#   Faz 3: Sheet 3 onaylı test mailler → gerçek mail (MOCK_SUPPLIER_EMAIL)
#   Faz 4: 48s geçen inquiry_sent'lere takip maili
#   Faz 5: inquiry_sent/followup_sent kontaklar için proforma teklifi işleme
#          (proforma_offers Supabase tablosu + Sheet 4)
#   Faz 6: RED yazılan (ve en az test_sent aşamasına ulaşmış) tedarikçi
#          kontakları için onaya tabi red bildirimi maili taslağı (GAP-9)

import os
import re
import json
import time
import uuid
import base64
import urllib.parse
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any, Tuple

import requests
import anthropic

from core.supabase_client import get_client
from core.logger import get_logger, log_run
from core.sheets_client import (
    get_gmail_service,
    upsert_tedarikci_onay,
    append_mail_onay,
    check_mail_onay_approvals,
    process_tedarikci_onay_approvals,
    update_mail_onay_status,
    append_proforma_onay,
    update_row,
    read_sheet,
    build_durum_note,
    TAB_MAIL_ONAY,
    M_TM_ID, M_GMAIL_ONAY, M_ONAY_DURUMU,
    SISTEM_BEKLEMEDE, SISTEM_ISLENIYOR,
)

logger = get_logger("tedarikci")

AGENT_NAME       = "tedarikci"
FOLLOWUP_HOURS   = 48
SENDER_NAME      = os.getenv("SENDER_NAME", "E-Ticaret Ekibi")
SENDER_EMAIL     = os.getenv("NOTIFICATION_EMAIL", "")
MOCK_MAIL        = os.getenv("MOCK_SUPPLIER_EMAIL", "")
TEST_MAIL_TO     = os.getenv("NOTIFICATION_EMAIL", "")  # Berkin'in Gmail'i
USD_TRY_RATE     = float(os.getenv("USD_TRY_RATE", "34.0"))

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ═════════════════════════════════════════════════════════════════════════════
# ANA AKIŞ
# ═════════════════════════════════════════════════════════════════════════════

def run():
    start = time.time()
    logger.info("Tedarikçi başladı (M4)")
    sheet_id = os.getenv("SHEETS_APPROVAL_QUEUE_ID")

    try:
        # Faz 1: Alibaba araştırması → Sheet 2
        researched = _phase1_supplier_research(sheet_id)

        # Faz 2: Sheet 2 onaylılar → Test maili → Sheet 3
        test_sent = _phase2_send_test_mails(sheet_id)

        # Faz 3: Sheet 3 onaylılar → Gerçek mail (MOCK)
        real_sent = _phase3_send_real_mails(sheet_id)

        # Faz 4: Takip maili
        followup_count = _phase4_send_followups()

        # Faz 5: Proforma teklifi işleme
        proforma_count = _phase5_handle_proforma(sheet_id)

        # Faz 6: Tedarikçi RED bildirimi taslakları (GAP-9)
        rejection_notices = _phase6_handle_rejection_notices(sheet_id)

        duration_ms = int((time.time() - start) * 1000)
        log_run(
            AGENT_NAME,
            status="success",
            run_type="cron",
            items_processed=researched,
            items_success=researched,
            duration_ms=duration_ms,
            metadata={
                "researched": researched,
                "test_sent": test_sent,
                "real_sent": real_sent,
                "followups": followup_count,
                "proforma": proforma_count,
                "rejection_notices": rejection_notices,
            },
        )
        logger.info(
            f"Tedarikçi tamamlandı ({duration_ms}ms) — "
            f"araştırıldı:{researched} test:{test_sent} gerçek:{real_sent} "
            f"takip:{followup_count} proforma:{proforma_count} "
            f"red_bildirimi:{rejection_notices}"
        )

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron",
                duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Tedarikçi hatası: {e}")
        raise


# ═════════════════════════════════════════════════════════════════════════════
# FAZ 1: Alibaba araştırması → Sheet 2
# ═════════════════════════════════════════════════════════════════════════════

def _phase1_supplier_research(sheet_id: Optional[str]) -> int:
    """Yeni onaylı ürünler için Alibaba'dan tedarikçi araştırır ve Sheet 2'ye yazar."""
    client = get_client()

    # Tedarikçi araştırması yapılmamış approved ürünleri bul
    products = (
        client.table("products")
        .select("*")
        .in_("status", ["approved"])
        .execute()
    )

    researched = 0
    for product in products.data:
        pid = product["id"]

        # Bu ürün için zaten araştırma yapıldı mı?
        existing = (
            client.table("supplier_contacts")
            .select("id")
            .eq("product_id", pid)
            .execute()
        )
        if existing.data:
            logger.info(f"Atlandı (zaten araştırıldı): {product.get('name')}")
            continue

        logger.info(f"Tedarikçi araştırması: {product.get('name')}")
        suppliers = _find_suppliers(product)

        for supplier in suppliers[:3]:
            contact_id = str(uuid.uuid4())
            relationship = _detect_relationship_type(product, supplier, client)
            scoring     = _score_supplier(supplier)
            supplier["scoring"] = scoring

            # Supabase supplier_contacts
            try:
                client.table("supplier_contacts").insert({
                    "id":              contact_id,
                    "product_id":      pid,
                    "supplier_name":   supplier.get("name", ""),
                    "supplier_email":  MOCK_MAIL,
                    "platform":        supplier.get("platform", "alibaba"),
                    "url":             supplier.get("url", ""),
                    "birim_usd":       supplier.get("birim_usd"),
                    "moq":             supplier.get("moq"),
                    "supplier_scoring": scoring,
                    "iliski_tipi":     relationship,
                    "status":          "research_found",
                    "mock":            supplier.get("mock", False),
                    "contacted_at":    datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception as e:
                logger.warning(f"supplier_contacts insert hatası: {e}")
                continue

            # Sheet 2
            if sheet_id:
                try:
                    upsert_tedarikci_onay(sheet_id, {
                        "id":            contact_id,
                        "product_id":    str(pid),
                        "product_title": product.get("name", ""),
                        "supplier_name": supplier.get("name", ""),
                        "platform":      supplier.get("platform", "alibaba"),
                        "iliski_tipi":   relationship,
                        "onceki_siparis_ref": supplier.get("onceki_siparis_ref", ""),
                        "url":           supplier.get("url", ""),
                        "birim_usd":     supplier.get("birim_usd", ""),
                        "moq":           supplier.get("moq", ""),
                        "scoring":       scoring,
                        "durum":         SISTEM_BEKLEMEDE,
                        "not":           supplier.get("not", ""),
                        "tarih":         datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    })
                except Exception as e:
                    logger.warning(f"Sheet 2 upsert hatası: {e}")

        # Ürün durumunu güncelle
        client.table("products").update({"status": "sourcing"}).eq("id", pid).execute()
        researched += 1
        time.sleep(1)

    return researched


# ═════════════════════════════════════════════════════════════════════════════
# FAZ 2: Sheet 2 onaylı → Test maili → Sheet 3
# ═════════════════════════════════════════════════════════════════════════════

def _phase2_send_test_mails(sheet_id: Optional[str]) -> int:
    """Sheet 2'de Berkin tarafından onaylanan tedarikçilere test maili gönderir."""
    if not sheet_id:
        return 0

    sent = 0
    client = get_client()

    try:
        approved_list, _ = process_tedarikci_onay_approvals(sheet_id)
    except Exception as e:
        logger.warning(f"Faz 2: Sheet 2 okunamadı: {e}")
        return 0

    for item in approved_list:
        contact_id = item["id"]

        # Zaten test mail gönderilmiş mi?
        try:
            res = client.table("supplier_contacts").select("status, tm_id").eq("id", contact_id).execute()
            if not res.data:
                continue
            contact = res.data[0]
            if contact.get("status") not in ("research_found", "approved"):
                continue  # zaten ilerledi
        except Exception as e:
            logger.warning(f"Faz 2: contact sorgu hatası {contact_id}: {e}")
            continue

        # Ürün ve tedarikçi bilgilerini çek
        try:
            sc_res = client.table("supplier_contacts").select("*").eq("id", contact_id).execute()
            if not sc_res.data:
                continue
            sc = sc_res.data[0]

            prod_res = client.table("products").select("*").eq("id", sc["product_id"]).execute()
            if not prod_res.data:
                continue
            product = prod_res.data[0]
        except Exception as e:
            logger.warning(f"Faz 2: veri çekme hatası: {e}")
            continue

        # TM-ID üret
        tm_id = _get_next_tm_id(client)

        # Test maili gönder
        success, email_body = _send_test_mail(product, sc, tm_id)
        if not success:
            continue

        # Supabase güncelle
        # Not: Sistem Durumu artık sadece 4 üst-seviye değer gösteriyor (GAP-7),
        # bu yüzden 'test_sent' alt-aşama detayı notes'un başına tag olarak eklenir.
        try:
            client.table("supplier_contacts").update({
                "tm_id":  tm_id,
                "status": "test_sent",
                "notes":  build_durum_note("test_sent", sc.get("notes", "")),
            }).eq("id", contact_id).execute()
        except Exception as e:
            logger.warning(f"Faz 2: status güncelleme hatası: {e}")

        # Sheet 3
        if sheet_id:
            try:
                append_mail_onay(sheet_id, {
                    "tm_id":               tm_id,
                    "product_id":          str(sc["product_id"]),
                    "product_title":       product.get("name", ""),
                    "supplier_name":       sc.get("supplier_name", ""),
                    "supplier_contact_id": contact_id,
                    "mail_turu":           "ilk_temas",
                    "email_body":          email_body,
                    "test_gonderildi":     datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "not":                 f"Tedarikçi: {sc.get('platform','alibaba')} | contact_id:{contact_id}",
                })
            except Exception as e:
                logger.warning(f"Faz 2: Sheet 3 append hatası: {e}")

        logger.info(f"Test maili gönderildi: {tm_id} → {product.get('name')} / {sc.get('supplier_name')}")
        sent += 1
        time.sleep(1)

    return sent


# ═════════════════════════════════════════════════════════════════════════════
# FAZ 3: Sheet 3 onaylı → Gerçek mail
# ═════════════════════════════════════════════════════════════════════════════

def _phase3_send_real_mails(sheet_id: Optional[str]) -> int:
    """Sheet 3'te onaylanan test mailler için gerçek tedarikçi mailini gönderir."""
    if not sheet_id:
        return 0

    sent = 0
    client = get_client()

    # Gmail inbox'ta [TM-XXX] reply var mı kontrol et → Sheet 3 güncelle
    _check_gmail_for_tm_replies(sheet_id, client)

    # Sheet 3'te onaylı olanları al (rejected_mails — mail taslağının kendi
    # reddi — burada işlenmiyor, ayrı bir backlog maddesi; GAP-9 farklı bir
    # akış, bkz. _phase6_handle_rejection_notices)
    try:
        approved_mails, _rejected_mails = check_mail_onay_approvals(sheet_id)
    except Exception as e:
        logger.warning(f"Faz 3: Sheet 3 okunamadı: {e}")
        return 0

    for mail_item in approved_mails:
        tm_id = mail_item.get("tm_id", "")
        if not tm_id:
            continue
        is_rejection_notice = mail_item.get("mail_turu") == "red_bildirimi"

        # TM-ID'den contact bul
        try:
            res = client.table("supplier_contacts").select("*").eq("tm_id", tm_id).execute()
            if not res.data:
                continue
            sc = res.data[0]
            # Normal ilk_temas/takip akışı test_sent bekler; red bildirimi
            # (GAP-9) ise kontak zaten 'rejected' durumundayken gönderilir —
            # o durumu geri almaz, sadece bildirim mailini yollar.
            if is_rejection_notice:
                if sc.get("status") != "rejected":
                    continue
            elif sc.get("status") != "test_sent":
                continue

            prod_res = client.table("products").select("*").eq("id", sc["product_id"]).execute()
            if not prod_res.data:
                continue
            product = prod_res.data[0]
        except Exception as e:
            logger.warning(f"Faz 3: veri hatası {tm_id}: {e}")
            continue

        # Gerçek mail gönder (MOCK → MOCK_SUPPLIER_EMAIL)
        mail_turu = "red_bildirimi" if is_rejection_notice else "ilk_temas"
        success = _send_real_inquiry_email(product, sc, mail_turu=mail_turu)
        if not success:
            continue

        # Supabase güncelle
        if is_rejection_notice:
            # Kontak zaten 'rejected' — bu terminal durumu geri almıyoruz,
            # sadece bildirim mailinin gittiğini not düşüyoruz.
            try:
                client.table("supplier_contacts").update({
                    "notes": build_durum_note("red_bildirimi_gonderildi", sc.get("notes", "")),
                }).eq("id", sc["id"]).execute()
            except Exception as e:
                logger.warning(f"Faz 3: red bildirimi not güncelleme hatası: {e}")
        else:
            now_str = datetime.now(timezone.utc).isoformat()
            try:
                client.table("supplier_contacts").update({
                    "status":       "inquiry_sent",
                    "contacted_at": now_str,
                    "notes":        build_durum_note("inquiry_sent", sc.get("notes", "")),
                }).eq("id", sc["id"]).execute()
            except Exception as e:
                logger.warning(f"Faz 3: status güncelleme hatası: {e}")

        # Sheet 3 güncelle
        if sheet_id:
            try:
                update_mail_onay_status(
                    sheet_id,
                    mail_item["row_num"],
                    status="sent",
                    gercek_gonderim=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                )
            except Exception as e:
                logger.warning(f"Faz 3: Sheet 3 güncelleme hatası: {e}")

        if is_rejection_notice:
            logger.info(f"Red bildirimi maili gönderildi: {tm_id} → {sc.get('supplier_name')} ({MOCK_MAIL})")
        else:
            logger.info(f"Gerçek mail gönderildi: {tm_id} → {sc.get('supplier_name')} ({MOCK_MAIL})")
        sent += 1

    return sent


# ═════════════════════════════════════════════════════════════════════════════
# FAZ 4: Takip maili
# ═════════════════════════════════════════════════════════════════════════════

def _phase4_send_followups() -> int:
    """48s geçen inquiry_sent kontaklar için takip maili gönderir."""
    client = get_client()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=FOLLOWUP_HOURS)).isoformat()
        result = (
            client.table("supplier_contacts")
            .select("*")
            .eq("status", "inquiry_sent")
            .lt("contacted_at", cutoff)
            .execute()
        )
        sent = 0
        for contact in result.data:
            if contact.get("mock"):
                continue  # Mock kontaklar için takip gönderme
            try:
                _send_followup_email(contact)
                client.table("supplier_contacts").update({
                    "status": "followup_sent",
                    "notes":  build_durum_note("followup_sent", contact.get("notes", "")),
                }).eq("id", contact["id"]).execute()
                sent += 1
            except Exception as e:
                logger.warning(f"Takip maili gönderilemedi: {e}")
        return sent
    except Exception as e:
        logger.warning(f"Takip kontrolü başarısız: {e}")
        return 0


# ═════════════════════════════════════════════════════════════════════════════
# FAZ 5: Proforma teklifi işleme (GAP-2)
# ═════════════════════════════════════════════════════════════════════════════

def _phase5_handle_proforma(sheet_id: Optional[str]) -> int:
    """
    inquiry_sent/followup_sent durumundaki supplier_contacts için proforma
    teklifi üretir/çıkarır. mock=true kontaklar için Claude Haiku ile sentetik
    teklif üretilir (gerçek tedarikçi henüz yokken test edilebilsin diye);
    mock=false kontaklar için Gmail yanıtı aranır ve içeriği Claude Haiku ile
    yapılandırılmış veriye çevrilir. Sonuç proforma_offers'a insert edilir
    ve Sheet 4'e append_proforma_onay() ile mirror'lanır.
    """
    client = get_client()
    try:
        contacts = (
            client.table("supplier_contacts")
            .select("*")
            .in_("status", ["inquiry_sent", "followup_sent"])
            .execute()
        )
    except Exception as e:
        logger.warning(f"Faz 5: supplier_contacts okunamadı: {e}")
        return 0

    processed = 0
    for sc in contacts.data:
        contact_id = sc["id"]

        try:
            existing = (
                client.table("proforma_offers")
                .select("id")
                .eq("supplier_contact_id", contact_id)
                .execute()
            )
            if existing.data:
                continue  # zaten proforma alınmış
        except Exception as e:
            logger.warning(f"Faz 5: proforma_offers sorgu hatası: {e}")
            continue

        try:
            prod_res = client.table("products").select("*").eq("id", sc["product_id"]).execute()
            if not prod_res.data:
                continue
            product = prod_res.data[0]
        except Exception as e:
            logger.warning(f"Faz 5: ürün sorgu hatası: {e}")
            continue

        if sc.get("mock"):
            offer = _generate_mock_proforma(product, sc)
        else:
            offer = _extract_proforma_from_gmail(product, sc)
            if not offer:
                continue  # henüz yanıt yok, bir sonraki cron'da tekrar denenecek

        offer_id = str(uuid.uuid4())
        try:
            client.table("proforma_offers").insert({
                "id":                       offer_id,
                "product_id":               sc["product_id"],
                "supplier_contact_id":      contact_id,
                "teklif_fiyat_usd":         offer.get("teklif_fiyat_usd"),
                "moq":                      offer.get("moq"),
                "teslim_sure_gun":          offer.get("teslim_sure_gun"),
                "tahmini_cogs_tl":          offer.get("tahmini_cogs_tl"),
                "tahmini_marj_pct":         offer.get("tahmini_marj_pct"),
                "firsatci_tahmini_fark_tl": offer.get("firsatci_tahmini_fark_tl"),
                "status":                   "pending",
                "note":                     offer.get("note", ""),
                "mock":                     bool(sc.get("mock", False)),
            }).execute()
        except Exception as e:
            logger.warning(f"Faz 5: proforma_offers insert hatası: {e}")
            continue

        if sheet_id:
            try:
                append_proforma_onay(sheet_id, {
                    "id":               offer_id,
                    "product_id":       str(sc["product_id"]),
                    "product_title":    product.get("name", ""),
                    "supplier_name":    sc.get("supplier_name", ""),
                    "teklif_fiyat_usd": offer.get("teklif_fiyat_usd", ""),
                    "moq":              offer.get("moq", ""),
                    "teslim_sure_gun":  offer.get("teslim_sure_gun", ""),
                    "tahmini_cogs_tl":  offer.get("tahmini_cogs_tl", ""),
                    "tahmini_marj_pct": offer.get("tahmini_marj_pct", ""),
                    "firsatci_tahmini_tl": _get_estimated_price_tl(product),
                    "durum":            SISTEM_BEKLEMEDE,
                    "not":              offer.get("note", ""),
                    "tarih":            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                })
            except Exception as e:
                logger.warning(f"Faz 5: Sheet 4 append hatası: {e}")

        logger.info(f"Proforma alındı: {product.get('name')} / {sc.get('supplier_name')}")
        processed += 1

    return processed


# ═════════════════════════════════════════════════════════════════════════════
# FAZ 6: Tedarikçi RED bildirimi taslakları (GAP-9)
# ═════════════════════════════════════════════════════════════════════════════

def _phase6_handle_rejection_notices(sheet_id: Optional[str]) -> int:
    """
    Sheet 2'de RED yazılıp `supplier_contacts.status='rejected'` yapılmış,
    ve daha önce en az test_sent aşamasına ulaşmış (tm_id atanmış) kontaklar
    için Claude Haiku ile kibar bir red/vazgeçme maili taslağı üretir ve
    Sheet 3'e YENİ bir satır (`mail_turu='red_bildirimi'`) olarak ekler.
    research_found/approved aşamasında kalıp hiç mail gitmemiş kontaklar
    atlanır — onlara zaten hiç temas kurulmadı.

    GAP-14'teki TM-ID race condition'ı büyütmemek için burada yeni bir
    TM-ID ÜRETİLMEZ — mevcut tm_id hem Sheet 3'ün TM-ID kolonuna (Faz 3'ün
    aynı ID'den kontağı bulup gerçek gönderimi yapabilmesi için) hem de Not
    kolonuna referans olarak taşınır. Gerçek gönderim, Berkin bu satırı
    onayladığında mevcut _phase3_send_real_mails() akışının içinde otomatik
    gerçekleşir (mail_turu ayrımı orada yapılır).
    """
    if not sheet_id:
        return 0

    client = get_client()
    try:
        contacts = (
            client.table("supplier_contacts")
            .select("*")
            .eq("status", "rejected")
            .eq("rejection_notice_drafted", False)
            .not_.is_("tm_id", "null")
            .execute()
        )
    except Exception as e:
        logger.warning(f"Faz 6: supplier_contacts okunamadı: {e}")
        return 0

    drafted = 0
    for sc in contacts.data:
        contact_id = sc["id"]
        tm_id = sc.get("tm_id")
        if not tm_id:
            continue

        try:
            prod_res = client.table("products").select("*").eq("id", sc["product_id"]).execute()
            if not prod_res.data:
                continue
            product = prod_res.data[0]
        except Exception as e:
            logger.warning(f"Faz 6: ürün sorgu hatası: {e}")
            continue

        try:
            email_body = _generate_rejection_email(product, sc)
        except Exception as e:
            logger.warning(f"Faz 6: red maili üretilemedi ({tm_id}): {e}")
            continue

        try:
            append_mail_onay(sheet_id, {
                "tm_id":               tm_id,
                "product_id":          str(sc["product_id"]),
                "product_title":       product.get("name", ""),
                "supplier_name":       sc.get("supplier_name", ""),
                "supplier_contact_id": contact_id,
                "mail_turu":           "red_bildirimi",
                "email_body":          email_body,
                "test_gonderildi":     datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "not":                 f"Orijinal TM-ID: {tm_id} | Red bildirimi",
            })
        except Exception as e:
            logger.warning(f"Faz 6: Sheet 3 append hatası ({tm_id}): {e}")
            continue

        try:
            client.table("supplier_contacts").update({
                "rejection_notice_drafted": True,
            }).eq("id", contact_id).execute()
        except Exception as e:
            logger.warning(f"Faz 6: rejection_notice_drafted güncelleme hatası: {e}")

        logger.info(f"Red bildirimi taslağı oluşturuldu: {tm_id} → {sc.get('supplier_name')} (onay bekliyor)")
        drafted += 1

    return drafted


def _get_estimated_price_tl(product: dict) -> float:
    """Ürünün fırsatçı tahmini satış fiyatını döner (metadata veya target_price_tl)."""
    meta = product.get("metadata") or {}
    return float(meta.get("estimated_price_tl") or product.get("target_price_tl") or 0)


def _compute_cogs_and_margin(product: dict, teklif_fiyat_usd) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    USD teklif fiyatını TL COGS'a çevirir (USD_TRY_RATE), fırsatçının tahmini
    satış fiyatına göre marj yüzdesini ve farkı hesaplar.
    Fark = cogs - tahmini satış fiyatı (append_proforma_onay ile aynı işaret kuralı).
    Returns: (tahmini_cogs_tl, tahmini_marj_pct, firsatci_tahmini_fark_tl)
    """
    if not teklif_fiyat_usd:
        return None, None, None
    cogs_tl = round(float(teklif_fiyat_usd) * USD_TRY_RATE, 2)
    est_price = _get_estimated_price_tl(product)
    marj_pct = fark = None
    if est_price:
        marj_pct = round((est_price - cogs_tl) / est_price * 100, 1)
        fark = round(cogs_tl - est_price, 2)
    return cogs_tl, marj_pct, fark


def _generate_mock_proforma(product: dict, sc: dict) -> Dict[str, Any]:
    """Mock tedarikçi kontakları için Claude Haiku ile sentetik proforma teklifi üretir."""
    ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    product_name = product.get("name", "")
    birim_usd    = sc.get("birim_usd")
    moq          = sc.get("moq")

    prompt = f"""Alibaba tedarikçisi '{sc.get("supplier_name", "Tedarikçi")}', '{product_name}' ürünü
için proforma teklif gönderdi. İlk araştırmadaki tahmini birim fiyat: {birim_usd} USD, MOQ: {moq}.
Gerçekçi bir proforma teklifi oluştur (ilk tahminden hafif sapmalı olabilir, sample/nakliye şartları içerebilir).

SADECE JSON döndür:
{{
  "teklif_fiyat_usd": 12.8,
  "moq": 50,
  "teslim_sure_gun": 30,
  "note": "Trade assurance destekler. %30 peşin, %70 sevkiyat öncesi."
}}"""

    try:
        resp = ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        offer = json.loads(raw)
    except Exception as e:
        logger.warning(f"Mock proforma üretilemedi, fallback kullanılıyor: {e}")
        offer = {
            "teklif_fiyat_usd": birim_usd or 10.0,
            "moq":              moq or 50,
            "teslim_sure_gun":  30,
            "note":             "Mock proforma (fallback)",
        }

    offer["tahmini_cogs_tl"], offer["tahmini_marj_pct"], offer["firsatci_tahmini_fark_tl"] = (
        _compute_cogs_and_margin(product, offer.get("teklif_fiyat_usd"))
    )
    return offer


def _extract_proforma_from_gmail(product: dict, sc: dict) -> Optional[Dict[str, Any]]:
    """
    Gerçek tedarikçi yanıtını Gmail'de arar (ürün adına göre konu eşleşmesi).
    Bulursa gövdeyi Claude Haiku ile yapılandırılmış proforma verisine çevirir.
    Yanıt yoksa None döner (bir sonraki cron'da tekrar denenir).
    """
    product_name   = product.get("name", "")
    supplier_email = sc.get("supplier_email", "")

    try:
        service = get_gmail_service()
        query_parts = ["in:inbox", "newer_than:45d"]
        if supplier_email:
            query_parts.append(f"from:{supplier_email}")
        results = service.users().messages().list(
            userId="me", q=" ".join(query_parts), maxResults=20,
        ).execute()

        messages = results.get("messages", [])
        for msg_ref in messages:
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="full",
            ).execute()
            headers = msg["payload"].get("headers", [])
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
            if product_name and product_name.lower()[:15] not in subject.lower():
                continue
            body = _extract_gmail_body(msg["payload"])
            if not body:
                continue
            return _claude_extract_proforma_fields(body, product, sc)

    except Exception as e:
        logger.warning(f"Faz 5: Gmail proforma arama hatası: {e}")

    return None


def _extract_gmail_body(payload: dict) -> str:
    """Gmail mesaj payload'ından text/plain gövdeyi çıkarır (recursive, multipart destekli)."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
    for part in payload.get("parts", []) or []:
        text = _extract_gmail_body(part)
        if text:
            return text
    return ""


def _claude_extract_proforma_fields(body: str, product: dict, sc: dict) -> Dict[str, Any]:
    """Claude Haiku ile serbest metin tedarikçi yanıtından fiyat/MOQ/teslim süresi çıkarır."""
    ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = f"""Aşağıdaki tedarikçi mail yanıtından proforma teklif bilgilerini çıkar.

Mail içeriği:
\"\"\"{body[:2000]}\"\"\"

SADECE JSON döndür:
{{
  "teklif_fiyat_usd": <birim fiyat USD, bulunamazsa null>,
  "moq": <minimum sipariş adedi, bulunamazsa null>,
  "teslim_sure_gun": <teslim süresi gün, bulunamazsa null>,
  "note": "<mail içeriğinden kısa özet>"
}}"""

    try:
        resp = ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        offer = json.loads(raw)
    except Exception as e:
        logger.warning(f"Proforma alan çıkarma hatası: {e}")
        offer = {
            "teklif_fiyat_usd": sc.get("birim_usd"),
            "moq":              sc.get("moq"),
            "teslim_sure_gun":  None,
            "note":             "Otomatik çıkarım başarısız, manuel kontrol gerekli",
        }

    offer["tahmini_cogs_tl"], offer["tahmini_marj_pct"], offer["firsatci_tahmini_fark_tl"] = (
        _compute_cogs_and_margin(product, offer.get("teklif_fiyat_usd"))
    )
    return offer


# ═════════════════════════════════════════════════════════════════════════════
# ALİBABA SCRAPING + FALLBACK
# ═════════════════════════════════════════════════════════════════════════════

def _find_suppliers(product: dict) -> List[Dict[str, Any]]:
    """
    Ürün için Alibaba'dan tedarikçi araştırır.
    1. Gerçek scraping dener → 2. Claude fallback
    """
    keyword    = product.get("name", "")
    price_tl   = product.get("metadata", {}).get("estimated_price_tl") if product.get("metadata") else None

    # 1. Gerçek Alibaba scraping
    scraped = _scrape_alibaba(keyword)
    if scraped and len(scraped) >= 2:
        logger.info(f"Alibaba scraping başarılı: {len(scraped)} tedarikçi bulundu")
        return scraped

    # 2. Claude ile araştırma
    logger.info(f"Alibaba scraping yetersiz, Claude fallback çalışıyor: {keyword}")
    return _claude_supplier_research(keyword, price_tl)


def _scrape_alibaba(keyword: str) -> List[Dict[str, Any]]:
    """
    Alibaba.com search sayfasını scrape eder.
    JS-rendered sayfa nedeniyle başarısız olabilir → boş liste döner.
    """
    try:
        q = urllib.parse.quote(keyword)
        url = (
            f"https://www.alibaba.com/trade/search"
            f"?SearchText={q}&IndexArea=product_en&tab=supplier"
        )
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        if resp.status_code != 200:
            logger.warning(f"Alibaba HTTP {resp.status_code}: {url}")
            return []

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        suppliers = []

        # 1. Embedded JSON in <script> tag
        for script in soup.find_all("script"):
            text = script.get_text()
            # Alibaba embeds supplier/product data in window.__GLOBAL_DATA__ or similar
            for pattern in [
                r'"companyName"\s*:\s*"([^"]+)"',
                r'"supplierName"\s*:\s*"([^"]+)"',
            ]:
                matches = re.findall(pattern, text)
                if matches:
                    for m in matches[:3]:
                        if len(m) > 3 and m not in [s.get("name") for s in suppliers]:
                            suppliers.append({
                                "name":     m,
                                "platform": "alibaba",
                                "url":      f"https://www.alibaba.com/trade/search?SearchText={q}",
                                "mock":     False,
                            })
                    if len(suppliers) >= 3:
                        break

        # 2. HTML element parsing
        if len(suppliers) < 2:
            for el in soup.select('[class*="supplier-name"]')[:5]:
                name = el.get_text(strip=True)
                if name and len(name) > 3:
                    suppliers.append({
                        "name":     name,
                        "platform": "alibaba",
                        "url":      f"https://www.alibaba.com/trade/search?SearchText={q}",
                        "mock":     False,
                    })

        # Fiyat/MOQ parse dene
        for i, s in enumerate(suppliers[:3]):
            price_el = soup.select('[class*="price"]')
            if price_el and i < len(price_el):
                price_text = price_el[i].get_text(strip=True)
                match = re.search(r"[\d.]+", price_text.replace(",", ""))
                if match:
                    s["birim_usd"] = float(match.group())
            s.setdefault("birim_usd", None)
            s.setdefault("moq", 50)

        return suppliers[:3]

    except Exception as e:
        logger.warning(f"Alibaba scraping hatası: {e}")
        return []


def _claude_supplier_research(keyword: str, price_tl: Optional[float] = None) -> List[Dict[str, Any]]:
    """
    Claude Haiku ile Alibaba'da bulunabilecek tedarikçi profilleri üretir.
    Bu araştırma amaçlıdır — gerçek sipariş verilmez.
    """
    ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    price_info = f"Hedef satış fiyatı yaklaşık {price_tl} TL" if price_tl else ""

    prompt = f"""Alibaba.com'da '{keyword}' ürünü için 3 farklı tedarikçi profili oluştur.
{price_info}
Bu profiller araştırma amaçlı ve gerçekçi olmalı.

SADECE JSON dizisi döndür:
[
  {{
    "name": "Tedarikçi şirket adı (Çince şirket veya İngilizce marka)",
    "platform": "alibaba",
    "url": "https://www.alibaba.com/product-detail/product-slug-here_1600123456789.html",
    "birim_usd": 12.5,
    "moq": 50,
    "yil": 5,
    "gold_supplier": true,
    "rating": 4.8,
    "teslimat_gun": 30,
    "not": "Trade assurance destekler. Min. sipariş 50 adet.",
    "mock": true
  }}
]

KURALLAR:
- "url" alanı her tedarikçi için, o tedarikçinin şirket adını ve ürünü birleştiren gerçek Alibaba arama URL'i olmalı.
  Format: https://www.alibaba.com/trade/search?SearchText={{TEDARIKCI_ADI_INGILIZCE+URUN_ADI_INGILIZCE}}
  Tedarikçi adı ve ürün adını URL encode ederek birleştir. Her tedarikçi için FARKLI URL kullan.
  Örnek: https://www.alibaba.com/trade/search?SearchText=Dongguan+Elastic+Force+resistance+band+set
- Fiyatlar gerçekçi olsun (USD). 3 farklı fiyat/kalite segmenti seç (budget/mid/premium)."""

    try:
        resp = ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        suppliers = json.loads(raw)
        for s in suppliers:
            s.setdefault("mock", True)
        return suppliers[:3]
    except Exception as e:
        logger.error(f"Claude supplier research hatası: {e}")
        # Hardcoded fallback — absolute minimum
        return [
            {
                "name": f"{keyword.title()} Manufacturer A",
                "platform": "alibaba",
                "url": f"https://www.alibaba.com/trade/search?SearchText={urllib.parse.quote(keyword)}",
                "birim_usd": None,
                "moq": 50,
                "mock": True,
            }
        ]


def _score_supplier(supplier: Dict[str, Any]) -> Dict[str, int]:
    """
    Tedarikçi puanlaması (0-100).
    Rating/30 + Fiyat/30 + Teslimat/20 + Feedback/20
    """
    # Rating skoru (0-30): gold supplier + yıl sayısı
    is_gold   = supplier.get("gold_supplier", False)
    years     = int(supplier.get("yil", 0) or 0)
    rating    = float(supplier.get("rating", 4.0) or 4.0)
    rating_s  = min(30, int(is_gold * 10 + min(years, 10) + int((rating - 3.0) * 5)))

    # Fiyat skoru (0-30): fiyat ne kadar düşükse o kadar iyi
    birim     = float(supplier.get("birim_usd", 0) or 0)
    if birim <= 0:
        fiyat_s = 15  # bilinmiyorsa nötr
    elif birim <= 5:   fiyat_s = 30
    elif birim <= 10:  fiyat_s = 25
    elif birim <= 20:  fiyat_s = 18
    elif birim <= 50:  fiyat_s = 10
    else:              fiyat_s = 5

    # Teslimat skoru (0-20)
    gun = int(supplier.get("teslimat_gun", 35) or 35)
    if gun <= 15:   teslimat_s = 20
    elif gun <= 25: teslimat_s = 15
    elif gun <= 35: teslimat_s = 10
    elif gun <= 50: teslimat_s = 5
    else:           teslimat_s = 2

    # Feedback skoru (0-20): şimdilik rating'den türet
    feedback_s = min(20, int((rating - 3.0) * 10))

    total = rating_s + fiyat_s + teslimat_s + feedback_s
    return {
        "total":    total,
        "rating":   rating_s,
        "fiyat":    fiyat_s,
        "teslimat": teslimat_s,
        "feedback": feedback_s,
    }


def _detect_relationship_type(product: dict, supplier: dict, client) -> str:
    """
    Tedarikçi ilişki tipini belirler.
    'new' / 'known_new_product' / 'reorder'
    """
    supplier_name = supplier.get("name", "").lower().strip()
    product_name  = product.get("name", "").lower().strip()

    try:
        # Bu tedarikçiyle daha önce çalışıldı mı?
        prev = (
            client.table("supplier_contacts")
            .select("product_id, supplier_name")
            .ilike("supplier_name", f"%{supplier_name[:20]}%")
            .execute()
        )
        if not prev.data:
            return "new"

        # Aynı ürün kategorisiyle çalışıldı mı?
        for p in prev.data:
            if product_name[:10].lower() in (p.get("supplier_name", "") or "").lower():
                return "reorder"

        return "known_new_product"

    except Exception:
        return "new"


# ═════════════════════════════════════════════════════════════════════════════
# TM-ID SİSTEMİ
# ═════════════════════════════════════════════════════════════════════════════

def _get_next_tm_id(client) -> str:
    """
    Sıradaki TM-ID'yi döner. Formatı: TM-001, TM-042 vb.
    supplier_contacts tablosundaki tm_id sayısından türetilir.
    """
    try:
        res = (
            client.table("supplier_contacts")
            .select("tm_id")
            .not_.is_("tm_id", "null")
            .execute()
        )
        n = len(res.data) + 1
    except Exception:
        n = 1
    return f"TM-{n:03d}"


# ═════════════════════════════════════════════════════════════════════════════
# MAİL FONKSİYONLARI
# ═════════════════════════════════════════════════════════════════════════════

def _generate_inquiry_email(product: dict, supplier: dict) -> str:
    """Claude Haiku ile tedarikçi teklif maili üretir."""
    ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    product_name = product.get("name", "")
    category     = product.get("category", "")

    prompt = f"""Write a concise professional supplier inquiry email.

Product: {product_name}
Category: {category}
Supplier platform: {supplier.get("platform", "alibaba")}
Sender name: {SENDER_NAME}

Include: product specs question, MOQ, unit/bulk price, sample availability, delivery time, payment terms.
End with: Best regards, {SENDER_NAME}
Write only the email body. Keep under 200 words. Professional, friendly tone."""

    resp = ai.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def _generate_rejection_email(product: dict, supplier: dict) -> str:
    """
    GAP-9: Claude Haiku ile kibar, kısa bir "teşekkürler ama şu an
    ilerlemiyoruz" tarzı red/vazgeçme maili üretir. Sadece Berkin RED sonrası
    kontak en az test_sent aşamasına ulaşmışsa (yani tedarikçiyle gerçekten
    temas kurulmuşsa) çağrılır.
    """
    ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    product_name = product.get("name", "")

    prompt = f"""Write a short, polite email to a supplier we previously contacted, letting them know
we will not be moving forward with this inquiry at this time.

Product: {product_name}
Supplier platform: {supplier.get("platform", "alibaba")}
Sender name: {SENDER_NAME}

Thank them for their time and the information they shared. Do not give a detailed reason.
Leave the door open for future opportunities.
End with: Best regards, {SENDER_NAME}
Write only the email body. Keep under 120 words. Polite, professional, friendly tone."""

    resp = ai.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def _send_test_mail(product: dict, supplier_contact: dict, tm_id: str) -> Tuple[bool, str]:
    """
    Test mailini NOTIFICATION_EMAIL'e gönderir (Berkin'in Gmail'i).
    Konu: [TM-XXX] Product Inquiry: {ürün} — {tedarikçi}
    MOCK_SUPPLIER_EMAIL'e değil — bu sadece onay için.
    Returns: (başarılı mı, üretilen mail gövdesi)
    """
    if not TEST_MAIL_TO:
        logger.warning("TEST_MAIL_TO (NOTIFICATION_EMAIL) tanımlı değil")
        return False, ""

    try:
        product_name    = product.get("name", "Ürün")
        supplier_name   = supplier_contact.get("supplier_name", "Tedarikçi")
        email_body      = _generate_inquiry_email(product, supplier_contact)

        preview_note = f"""--- TEST MAİL ÖNIZLEME ---
TM-ID: {tm_id}
Tedarikçi: {supplier_name}
Platform: {supplier_contact.get("platform", "alibaba")}
Tahmini Birim: {supplier_contact.get("birim_usd", "?")} USD
MOQ: {supplier_contact.get("moq", "?")}

Bu mail onaylanırsa MOCK tedarikçi adresine ({MOCK_MAIL}) gönderilecektir.
Onaylamak için Google Sheets Mail Onay sekmesindeki "Excel Onay" kolonuna ONAY yazın,
ya da bu maili yanıtlayın.

--- MAIL İÇERİĞİ ---
{email_body}"""

        message = MIMEMultipart()
        message["to"]      = TEST_MAIL_TO
        message["subject"] = f"[{tm_id}] Product Inquiry: {product_name} — {supplier_name}"
        if SENDER_EMAIL:
            message["from"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        message.attach(MIMEText(preview_note, "plain"))

        service = get_gmail_service()
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info(f"Test maili gönderildi: [{tm_id}] → {TEST_MAIL_TO}")
        return True, email_body

    except Exception as e:
        logger.error(f"Test mail gönderilemedi ({tm_id}): {e}")
        return False, ""


def _send_real_inquiry_email(product: dict, supplier_contact: dict, mail_turu: str = "ilk_temas") -> bool:
    """
    Onaylanmış tedarikçiye gerçek maili gönderir. Şu an MOCK_SUPPLIER_EMAIL'e
    gider. TM-ID konu satırında YOK.
    `mail_turu='red_bildirimi'` (GAP-9) ise konu/gövde "Product Inquiry"
    yerine kibar bir vazgeçme bildirimi olur — ONAY/gönderim akışı ortak
    kalıyor, sadece içerik seçimi mail_turu'ne göre değişiyor.
    """
    supplier_email = MOCK_MAIL or supplier_contact.get("supplier_email", "")
    if not supplier_email:
        return False

    try:
        product_name = product.get("name", "Ürün")
        supplier_name = supplier_contact.get("supplier_name", "Supplier")
        if mail_turu == "red_bildirimi":
            email_body = _generate_rejection_email(product, supplier_contact)
            subject = f"Update on Inquiry: {product_name}"
        else:
            email_body = _generate_inquiry_email(product, supplier_contact)
            subject = f"Product Inquiry: {product_name}"  # TM-ID YOK

        message = MIMEMultipart()
        message["to"]      = supplier_email
        message["subject"] = subject
        if SENDER_EMAIL:
            message["from"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        message.attach(MIMEText(email_body, "plain"))

        service = get_gmail_service()
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info(f"Gerçek mail gönderildi ({mail_turu}): {supplier_name} → {supplier_email}")
        return True

    except Exception as e:
        logger.error(f"Gerçek mail gönderilemedi: {e}")
        return False


def _send_followup_email(contact: dict):
    """48s geçen inquiry için takip maili."""
    if not MOCK_MAIL:
        return
    message = MIMEText(
        f"Hi,\n\nFollowing up on my earlier inquiry about "
        f"{contact.get('supplier_name', 'the product')}. "
        f"Could you please share pricing and MOQ information?\n\nThank you!\n{SENDER_NAME}"
    )
    message["to"]      = MOCK_MAIL
    message["subject"] = "Follow-up: Product Inquiry"
    if SENDER_EMAIL:
        message["from"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"

    service = get_gmail_service()
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    logger.info(f"Takip maili gönderildi: {contact.get('supplier_name')}")


# ═════════════════════════════════════════════════════════════════════════════
# GMAİL GELEN KUTUSU KONTROLÜ
# ═════════════════════════════════════════════════════════════════════════════

def _check_gmail_for_tm_replies(sheet_id: str, client):
    """
    Gmail'de [TM-XXX] içeren yanıtları arar.
    Bulursa Sheet 3'te Gmail Onay kolonunu günceller.
    """
    try:
        service = get_gmail_service()
        # Son 7 günde gelen [TM- ile başlayan konular
        results = service.users().messages().list(
            userId="me",
            q="in:inbox [TM- newer_than:7d",
            maxResults=20,
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            return

        # Sheet 3'ü oku
        try:
            sheet3_rows = read_sheet(sheet_id, f"'{TAB_MAIL_ONAY}'!A1:K500")
        except Exception:
            sheet3_rows = []

        for msg_ref in messages:
            try:
                msg = service.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="metadata",
                    metadataHeaders=["subject", "from"],
                ).execute()
                subject = next(
                    (h["value"] for h in msg["payload"]["headers"] if h["name"] == "Subject"),
                    ""
                )
                # [TM-001] gibi pattern ara
                match = re.search(r"\[?(TM-\d{3})\]?", subject)
                if not match:
                    continue
                found_tm = match.group(1)
                logger.info(f"Gmail'de {found_tm} yanıtı bulundu")

                # Sheet 3'te bu TM-ID'yi bul ve Gmail Onay güncelle
                for i, row in enumerate(sheet3_rows[1:], start=2):
                    if row and len(row) > M_TM_ID and row[M_TM_ID] == found_tm:
                        row_padded = row + [""] * (11 - len(row))
                        row_padded[M_GMAIL_ONAY] = "Gmail Yanıtı Alındı"
                        # Eski sheet verisinde "pending"/"beklemede" de olabilir
                        # (migrasyon öncesi) — GAP-7: yeni yazımlarda SISTEM_BEKLEMEDE.
                        if row_padded[M_ONAY_DURUMU] in (SISTEM_BEKLEMEDE, "pending", "beklemede"):
                            row_padded[M_ONAY_DURUMU] = SISTEM_ISLENIYOR
                        update_row(sheet_id, "Mail Onay", i, row_padded)
                        logger.info(f"Sheet 3 Gmail Onay güncellendi: {found_tm}")
                        break

            except Exception as e:
                logger.warning(f"Gmail mesaj işleme hatası: {e}")

    except Exception as e:
        logger.warning(f"Gmail inbox kontrolü başarısız: {e}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
