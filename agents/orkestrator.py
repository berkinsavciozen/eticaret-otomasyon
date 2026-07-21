# Orkestratör Agent
# Görev: Diğer agentları tetikler, approval_queue'yu yönetir, sistem sağlığını kontrol eder.
# Çalışma sıklığı: Her 30 dakikada bir (Railway cron)

import os
import time
from datetime import datetime, timezone
from core.supabase_client import get_client
from core.logger import get_logger, log_run
from core.sheets_client import (
    setup_all_sheets,
    mirror_urun_onay,
    mirror_tedarikci_onay,
    mirror_proforma_onay,
    process_urun_onay_approvals,
    process_tedarikci_onay_approvals,
    check_mail_onay_approvals,
    process_proforma_approvals,
    get_mail_onay_status_counts,
    get_proforma_onay_status_counts,
    refresh_dashboard,
    get_gmail_service,
)

logger = get_logger("orkestrator")

AGENT_NAME = "orkestrator"


def run():
    start = time.time()
    logger.info("Orkestratör başladı")

    try:
        sheet_id = os.getenv("SHEETS_APPROVAL_QUEUE_ID")

        # 0. İlk çalışmada sekme başlıklarını oluştur
        if sheet_id:
            try:
                setup_all_sheets(sheet_id)
            except Exception as e:
                logger.warning(f"setup_all_sheets atlandı: {e}")

        # 1. Sheets'teki onayları önce işle → Supabase'e yansısın
        urun_approved, urun_rejected = _process_urun_approvals(sheet_id)
        tedarikci_approved, _ = _process_tedarikci_approvals(sheet_id)
        mail_approved = _process_mail_approvals(sheet_id)
        proforma_approved, _ = _process_proforma_approvals_step(sheet_id)

        # 2. Bekleyen onayları say
        pending_counts = _check_pending_approvals(sheet_id)

        # 3. Sheet 1, 2 ve 4'ü Supabase'den tazele
        _mirror_urun_onay_to_sheets(sheet_id)
        _mirror_tedarikci_onay_to_sheets(sheet_id)
        _mirror_proforma_onay_to_sheets(sheet_id)

        # 4. Dashboard güncelle
        _refresh_dashboard_step(sheet_id, pending_counts)

        # 5. Agent sağlık kontrolü
        _check_agent_health()

        # 6. Bekleyen onay varsa Gmail bildirimi
        total_pending = sum(pending_counts.values())
        if total_pending > 0:
            _send_gmail_reminder(pending_counts)

        duration_ms = int((time.time() - start) * 1000)
        log_run(
            AGENT_NAME,
            status="success",
            run_type="cron",
            duration_ms=duration_ms,
            metadata={
                "urun_approved": urun_approved,
                "urun_rejected": urun_rejected,
                "tedarikci_approved": tedarikci_approved,
                "mail_approved": mail_approved,
                "proforma_approved": proforma_approved,
                "pending": pending_counts,
            },
        )
        logger.info(
            f"Orkestratör tamamlandı ({duration_ms}ms) — "
            f"ürün onay: {urun_approved}, red: {urun_rejected} | "
            f"tedarikçi: {tedarikci_approved} | mail: {mail_approved} | "
            f"proforma: {proforma_approved}"
        )

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron",
                duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Orkestratör hatası: {e}")
        raise


# ── Sheet 1: Ürün Onay işleme ─────────────────────────────────────────────────

def _process_urun_approvals(sheet_id: str) -> tuple:
    """
    Sheet 1'deki onay/red kararlarını Supabase'e yansıtır.

    GAP-8: Tek yönlü değil — Berkin fikrini değiştirip aksiyonu tersine
    çevirirse, approval_queue.status'u da tersine çevirir:
      - approved (Sheet'te ONAY) + Supabase'de hâlâ 'pending' → 'approved' +
        products satırı oluştur (mevcut davranış).
      - approved (ONAY) + Supabase'de 'rejected' → 'approved'e geri döndür,
        daha önce oluşturulmuş products satırı varsa 'approved'e geri çek,
        yoksa yeniden oluştur.
      - rejected (RED) + Supabase'de hâlâ 'pending' → 'rejected' (mevcut
        davranış, products satırı hiç oluşturulmamıştı).
      - rejected (RED) + Supabase'de 'approved' → 'rejected'e geri döndür,
        oluşturulan products satırı SİLİNMEZ, 'delisted' yapılır (iz kalır).
      - Zaten aynı durumdaysa (approved+ONAY veya rejected+RED) no-op.
    """
    if not sheet_id:
        return 0, 0

    try:
        approved_list, rejected_list = process_urun_onay_approvals(sheet_id)
    except Exception as e:
        logger.warning(f"Sheet 1 okunamadı: {e}")
        return 0, 0

    client = get_client()
    approved_count = 0
    rejected_count = 0

    for item in approved_list:
        row_id = item["id"]
        try:
            result = client.table("approval_queue").select("id, status, title").eq("id", row_id).execute()
            if not result.data:
                continue
            current_status = result.data[0].get("status")
            title = result.data[0].get("title", "Bilinmeyen ürün")
            if current_status == "approved":
                continue  # zaten onaylı, değişiklik yok

            client.table("approval_queue").update({
                "status": "approved",
                "decision_note": item.get("note", ""),
            }).eq("id", row_id).execute()

            if current_status == "rejected":
                _restore_product_from_approval(row_id, title, client)
                logger.info(f"Ürün onayı geri alındı: {title} (rejected→approved)")
            else:
                _create_product_from_approval(row_id, client)
                logger.info(f"Ürün onaylandı: {row_id}")
            approved_count += 1
        except Exception as e:
            logger.error(f"Ürün onay hatası {row_id}: {e}")

    for item in rejected_list:
        row_id = item["id"]
        try:
            result = client.table("approval_queue").select("id, status, title").eq("id", row_id).execute()
            if not result.data:
                continue
            current_status = result.data[0].get("status")
            title = result.data[0].get("title", "Bilinmeyen ürün")
            if current_status == "rejected":
                continue  # zaten red, değişiklik yok

            client.table("approval_queue").update({
                "status": "rejected",
                "decision_note": item.get("note", ""),
            }).eq("id", row_id).execute()

            if current_status == "approved":
                _delist_product_from_approval(title, client)
                logger.info(f"Ürün onayı geri alındı: {title} (approved→rejected)")
            else:
                logger.info(f"Ürün reddedildi: {row_id}")
            rejected_count += 1
        except Exception as e:
            logger.error(f"Ürün red hatası {row_id}: {e}")

    return approved_count, rejected_count


def _create_product_from_approval(approval_id: str, client):
    """Onaylanan approval_queue kaydından products tablosuna kayıt oluşturur."""
    result = client.table("approval_queue").select("*").eq("id", approval_id).execute()
    if not result.data:
        return
    r = result.data[0]
    title = r.get("title", "Bilinmeyen ürün")

    existing = client.table("products").select("id").eq("name", title).execute()
    if existing.data:
        logger.info(f"products'ta zaten var, atlandı: {title}")
        return

    client.table("products").insert({
        "name": title,
        "status": "approved",
        "category": r.get("category", ""),
    }).execute()


def _restore_product_from_approval(approval_id: str, title: str, client):
    """
    GAP-8: RED'den ONAY'a geri dönüldüğünde, daha önce bu başlıkla
    oluşturulmuş bir products satırı varsa (delisted dahil hangi durumda
    olursa olsun) 'approved'e geri döndürür; hiç oluşturulmamışsa
    _create_product_from_approval ile yeniden oluşturur.
    """
    existing = client.table("products").select("id").eq("name", title).execute()
    if existing.data:
        client.table("products").update({"status": "approved"}).eq("id", existing.data[0]["id"]).execute()
        return
    _create_product_from_approval(approval_id, client)


def _delist_product_from_approval(title: str, client):
    """
    GAP-8: ONAY'dan RED'e geri dönüldüğünde, oluşturulmuş products satırını
    SİLMEDEN 'delisted' yapar — mevcut status akışında zaten terminal bir
    durum, burada "iptal edilmiş ürün" anlamında kullanılır, iz kalır.
    """
    existing = client.table("products").select("id").eq("name", title).execute()
    if existing.data:
        client.table("products").update({"status": "delisted"}).eq("id", existing.data[0]["id"]).execute()


# ── Sheet 2: Tedarikçi Onay işleme ───────────────────────────────────────────

def _process_tedarikci_approvals(sheet_id: str) -> tuple:
    """Sheet 2'deki tedarikçi onaylarını işler."""
    if not sheet_id:
        return 0, 0
    try:
        approved_list, rejected_list = process_tedarikci_onay_approvals(sheet_id)
    except Exception as e:
        logger.warning(f"Sheet 2 okunamadı: {e}")
        return 0, 0

    # Şu an tedarikçi approval'ları Supabase'de ayrı tablo yok (M4 kapsam).
    # Sadece sayıyı log'la.
    client = get_client()
    approved_count = 0
    ALREADY_PROCESSED = {"inquiry_sent", "followup_sent", "completed", "sent"}
    for item in approved_list:
        try:
            res = client.table("supplier_contacts").select("status").eq("id", item["id"]).execute()
            if res.data and res.data[0].get("status") in ALREADY_PROCESSED:
                continue  # zaten ilerledi, üzerine yazma
            client.table("supplier_contacts").update({
                "status": "approved",
            }).eq("id", item["id"]).execute()
            approved_count += 1
            logger.info(f"Tedarikçi onaylandı (Supabase): {item.get('id')}")
        except Exception as e:
            logger.warning(f"Tedarikçi onay Supabase hatası: {e}")

    for item in rejected_list:
        try:
            client.table("supplier_contacts").update({
                "status": "rejected",
            }).eq("id", item["id"]).execute()
        except Exception as e:
            logger.warning(f"Tedarikçi red Supabase hatası: {e}")

    return approved_count, len(rejected_list)


# ── Sheet 3: Mail Onay işleme ─────────────────────────────────────────────────

def _process_mail_approvals(sheet_id: str) -> int:
    """Sheet 3'te onaylı (gönderim bekleyen) mail sayısını raporlar.

    Gerçek tedarikçi mail gönderimi artık tedarikci.py → _phase3_send_real_mails()
    tarafından yapılıyor (aynı check_mail_onay_approvals() ile Sheet 3'ü okuyup
    gerçek maili gönderiyor ve durumu "sent" olarak işaretliyor). Burada Sheet 3'e
    ayrıca yazmıyoruz — iki fonksiyonun aynı satırları farklı durumlarla
    güncellemesi (duplike işleme) riskini önlemek için bu fonksiyon salt
    okuma/loglama amaçlıdır.
    """
    if not sheet_id:
        return 0

    try:
        approved_mails, rejected_mails = check_mail_onay_approvals(sheet_id)
    except Exception as e:
        logger.warning(f"Sheet 3 okunamadı: {e}")
        return 0

    if approved_mails:
        logger.info(
            f"{len(approved_mails)} mail onayı gönderim bekliyor "
            f"(gerçek gönderim tedarikci.py Faz 3'te yapılır)"
        )
    if rejected_mails:
        logger.info(
            f"{len(rejected_mails)} mail reddi okundu "
            f"(mail_approvals.onay_durumu='rejected' işaretlendi, ayrı işleme henüz eklenmedi — "
            f"bu, mail taslağının kendisinin reddi; GAP-9 farklı bir akış, bkz. tedarikci.py Faz 6)"
        )

    return len(approved_mails)


# ── Sheet 4: Proforma Onay işleme ────────────────────────────────────────────

def _process_proforma_approvals_step(sheet_id: str) -> tuple:
    """
    Sheet 4'teki proforma onaylarını işler (GAP-2). Onaylanan bir proforma
    bulunduğunda:
    - İlgili proforma_offers (Supabase) kaydı 'approved' / 'rejected' olarak işaretlenir
    - İlgili products kaydının status'u 'sourcing' → 'sourced' yapılır
      (listeleme.py'nin _get_sourced_products() bu geçişi bekliyor)
    - İlgili supplier_contacts kaydının status'u 'completed' yapılır
    """
    if not sheet_id:
        return 0, 0
    try:
        approved_list, rejected_list = process_proforma_approvals(sheet_id)
    except Exception as e:
        logger.warning(f"Sheet 4 okunamadı: {e}")
        return 0, 0

    client = get_client()
    now_iso = datetime.now(timezone.utc).isoformat()
    approved_count = 0

    for item in approved_list:
        offer_id = item["id"]
        try:
            res = client.table("proforma_offers").select("*").eq("id", offer_id).execute()
            if not res.data:
                continue
            offer = res.data[0]
            if offer.get("status") != "pending":
                continue  # zaten işlendi

            update_fields = {"status": "approved", "reviewed_at": now_iso}
            if item.get("note"):
                update_fields["note"] = item["note"]
            client.table("proforma_offers").update(update_fields).eq("id", offer_id).execute()

            client.table("products").update({"status": "sourced"}).eq(
                "id", offer["product_id"]
            ).eq("status", "sourcing").execute()

            if offer.get("supplier_contact_id"):
                client.table("supplier_contacts").update({"status": "completed"}).eq(
                    "id", offer["supplier_contact_id"]
                ).execute()

            approved_count += 1
            logger.info(f"Proforma onaylandı: {offer_id} → ürün sourced, tedarikçi completed")
        except Exception as e:
            logger.error(f"Proforma onay işleme hatası {offer_id}: {e}")

    for item in rejected_list:
        offer_id = item["id"]
        try:
            update_fields = {"status": "rejected", "reviewed_at": now_iso}
            if item.get("note"):
                update_fields["note"] = item["note"]
            client.table("proforma_offers").update(update_fields).eq("id", offer_id).execute()
        except Exception as e:
            logger.warning(f"Proforma red işleme hatası {offer_id}: {e}")

    if approved_count:
        logger.info(f"{approved_count} proforma onaylandı (sourced geçişi tetiklendi)")
    return approved_count, len(rejected_list)


# ── Sheet 1 mirror ────────────────────────────────────────────────────────────

def _mirror_urun_onay_to_sheets(sheet_id: str):
    """approval_queue tablosunu Sheet 1'e yazar (tüm statüler)."""
    if not sheet_id:
        logger.info("SHEETS_APPROVAL_QUEUE_ID tanımlı değil, mirror atlandı")
        return

    try:
        client = get_client()
        rows = (
            client.table("approval_queue")
            .select("*")
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        count = mirror_urun_onay(sheet_id, rows.data)
        logger.info(f"Sheet 1 mirror: {count} kayıt yazıldı")
    except Exception as e:
        logger.warning(f"Sheet 1 mirror atlandı (Sheets erişim hatası): {e}")


# ── Sheet 2 mirror ────────────────────────────────────────────────────────────

def _mirror_tedarikci_onay_to_sheets(sheet_id: str):
    """supplier_contacts tablosunu Sheet 2'ye yazar (products join ile)."""
    if not sheet_id:
        return
    client = get_client()
    try:
        sc_res = client.table("supplier_contacts").select("*").order("contacted_at", desc=False).execute()
        prod_res = client.table("products").select("id, name").execute()
        prod_map = {p["id"]: p["name"] for p in prod_res.data}
        rows = []
        for sc in sc_res.data:
            sc["product_name"] = prod_map.get(sc.get("product_id"), "")
            rows.append(sc)
        count = mirror_tedarikci_onay(sheet_id, rows)
        logger.info(f"Sheet 2 mirror: {count} tedarikçi yazıldı")
    except Exception as e:
        logger.warning(f"Sheet 2 mirror hatası: {e}")


# ── Sheet 4 mirror (GAP-7: K kolonu artık periyodik olarak sistem durumuna
#    çevriliyor — Sheet1/2 ile aynı dual-purpose pattern) ─────────────────────

def _mirror_proforma_onay_to_sheets(sheet_id: str):
    """proforma_offers tablosunu Sheet 4'e yazar (products + supplier_contacts join ile)."""
    if not sheet_id:
        return
    client = get_client()
    try:
        po_res = client.table("proforma_offers").select("*").order("created_at", desc=False).execute()
        prod_res = client.table("products").select("id, name").execute()
        prod_map = {p["id"]: p["name"] for p in prod_res.data}
        sc_res = client.table("supplier_contacts").select("id, supplier_name").execute()
        sc_map = {s["id"]: s["supplier_name"] for s in sc_res.data}
        rows = []
        for po in po_res.data:
            po["product_title"] = prod_map.get(po.get("product_id"), "")
            po["supplier_name"] = sc_map.get(po.get("supplier_contact_id"), "")
            rows.append(po)
        count = mirror_proforma_onay(sheet_id, rows)
        logger.info(f"Sheet 4 mirror: {count} proforma yazıldı")
    except Exception as e:
        logger.warning(f"Sheet 4 mirror hatası: {e}")


# ── Dashboard ─────────────────────────────────────────────────────────────────

def _refresh_dashboard_step(sheet_id: str, pending_counts: dict):
    """Sheet 5 Dashboard'u günceller."""
    if not sheet_id:
        return

    client = get_client()
    try:
        # Ürün pipeline sayıları
        all_q = client.table("approval_queue").select("status").execute()
        urun_pending  = sum(1 for r in all_q.data if r["status"] == "pending")
        urun_approved = sum(1 for r in all_q.data if r["status"] == "approved")
        urun_rejected = sum(1 for r in all_q.data if r["status"] == "rejected")

        # Tedarikçi sayıları
        all_sc = client.table("supplier_contacts").select("status, supplier_name, product_id").execute()
        tedarikci_pending  = sum(1 for r in all_sc.data if r["status"] in ("research_found",))
        tedarikci_approved = sum(1 for r in all_sc.data if r["status"] in ("approved", "inquiry_sent", "followup_sent"))

        # Ürün × Tedarikçi matrisi
        products_res = client.table("products").select("id, name").execute()
        prod_map = {p["id"]: p["name"] for p in products_res.data}
        matrix = []
        for sc in all_sc.data:
            matrix.append({
                "product":  prod_map.get(sc.get("product_id"), sc.get("product_id", "")),
                "supplier": sc.get("supplier_name", ""),
                "status":   sc.get("status", ""),
                "score":    "",
            })

        mail_pending, mail_approved_ct = get_mail_onay_status_counts(sheet_id)
        proforma_pending, proforma_approved_ct = get_proforma_onay_status_counts(sheet_id)

        pipeline_data = {
            "urun_pending":       urun_pending,
            "urun_approved":      urun_approved,
            "urun_rejected":      urun_rejected,
            "tedarikci_pending":  tedarikci_pending,
            "tedarikci_approved": tedarikci_approved,
            "mail_pending":       mail_pending,
            "mail_approved":      mail_approved_ct,
            "proforma_pending":   proforma_pending,
            "proforma_approved":  proforma_approved_ct,
            "last_updated":       datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "product_supplier_matrix": matrix,
        }
        refresh_dashboard(sheet_id, pipeline_data)
        logger.info("Dashboard güncellendi")
    except Exception as e:
        logger.warning(f"Dashboard güncelleme hatası: {e}")


# ── Pending approval sayıları ─────────────────────────────────────────────────

def _check_pending_approvals(sheet_id: str = None) -> dict:
    """
    Bekleyen onay sayılarını döner (GAP-6). Gmail hatırlatma maili bu sayıları
    kullanır — dashboard'daki pending sayaçlarından (BUG-3, _refresh_dashboard_step)
    AYRI bir fonksiyon, o yüzden burada da gerçek veriden okunması gerekiyor.
    """
    client = get_client()
    urun_pending = (
        client.table("approval_queue")
        .select("id")
        .eq("status", "pending")
        .execute()
    )
    urun_count = len(urun_pending.data)

    tedarikci_count = 0
    try:
        tedarikci_pending = (
            client.table("supplier_contacts")
            .select("id")
            .eq("status", "research_found")
            .execute()
        )
        tedarikci_count = len(tedarikci_pending.data)
    except Exception as e:
        logger.warning(f"Tedarikçi bekleyen sayısı alınamadı: {e}")

    mail_count = proforma_count = 0
    if sheet_id:
        try:
            mail_count, _ = get_mail_onay_status_counts(sheet_id)
        except Exception as e:
            logger.warning(f"Mail bekleyen sayısı alınamadı: {e}")
        try:
            proforma_count, _ = get_proforma_onay_status_counts(sheet_id)
        except Exception as e:
            logger.warning(f"Proforma bekleyen sayısı alınamadı: {e}")

    counts = {
        "urun": urun_count,
        "tedarikci": tedarikci_count,
        "mail": mail_count,
        "proforma": proforma_count,
    }
    total = sum(counts.values())
    if total > 0:
        logger.info(f"Bekleyen onaylar: {counts}")
    else:
        logger.info("Bekleyen onay yok")
    return counts


def _check_agent_health():
    client = get_client()
    recent = (
        client.table("agent_logs")
        .select("agent_name, status, started_at")
        .order("started_at", desc=True)
        .limit(20)
        .execute()
    )
    logger.info(f"Son {len(recent.data)} log kaydı kontrol edildi")


# ── Gmail bildirimi ───────────────────────────────────────────────────────────

def _send_gmail_reminder(pending_counts: dict):
    """Bekleyen onaylar için Gmail bildirimi gönderir."""
    notification_email = os.getenv("NOTIFICATION_EMAIL")
    if not notification_email:
        logger.info("NOTIFICATION_EMAIL tanımlı değil, mail atlandı")
        return

    try:
        import base64
        from email.mime.text import MIMEText

        sheet_id  = os.getenv("SHEETS_APPROVAL_QUEUE_ID", "")
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}" if sheet_id else ""

        lines = []
        if pending_counts.get("urun"):
            lines.append(f"• Ürün Onay: {pending_counts['urun']} bekleyen")
        if pending_counts.get("tedarikci"):
            lines.append(f"• Tedarikçi Onay: {pending_counts['tedarikci']} bekleyen")
        if pending_counts.get("mail"):
            lines.append(f"• Mail Onay: {pending_counts['mail']} bekleyen")
        if pending_counts.get("proforma"):
            lines.append(f"• Proforma Onay: {pending_counts['proforma']} bekleyen")

        total = sum(pending_counts.values())
        body = f"""Merhaba,

{total} adet onay bekleyen kayıt var:

{chr(10).join(lines)}

Onay paneline git:
{sheet_url}

— E-Ticaret Otomasyon Sistemi
"""
        message = MIMEText(body)
        message["to"] = notification_email
        message["subject"] = f"[E-Ticaret] {total} onay bekliyor"

        service = get_gmail_service()
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        logger.info(f"Gmail bildirimi gönderildi: {notification_email}")

    except Exception as e:
        logger.error(f"Gmail bildirimi gönderilemedi: {e}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
