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
        pending_counts = _check_pending_approvals()

        # 3. Sheet 1 ve Sheet 2'yi Supabase'den tazele
        _mirror_urun_onay_to_sheets(sheet_id)
        _mirror_tedarikci_onay_to_sheets(sheet_id)

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
    """Sheet 1'deki onay/red kararlarını Supabase'e yansıtır."""
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
            result = client.table("approval_queue").select("id, status").eq("id", row_id).execute()
            if not result.data or result.data[0].get("status") != "pending":
                continue
            client.table("approval_queue").update({
                "status": "approved",
                "decision_note": item.get("note", ""),
            }).eq("id", row_id).execute()
            _create_product_from_approval(row_id, client)
            approved_count += 1
            logger.info(f"Ürün onaylandı: {row_id}")
        except Exception as e:
            logger.error(f"Ürün onay hatası {row_id}: {e}")

    for item in rejected_list:
        row_id = item["id"]
        try:
            result = client.table("approval_queue").select("id, status").eq("id", row_id).execute()
            if not result.data or result.data[0].get("status") != "pending":
                continue
            client.table("approval_queue").update({
                "status": "rejected",
                "decision_note": item.get("note", ""),
            }).eq("id", row_id).execute()
            rejected_count += 1
            logger.info(f"Ürün reddedildi: {row_id}")
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
        approved_mails = check_mail_onay_approvals(sheet_id)
    except Exception as e:
        logger.warning(f"Sheet 3 okunamadı: {e}")
        return 0

    if approved_mails:
        logger.info(
            f"{len(approved_mails)} mail onayı gönderim bekliyor "
            f"(gerçek gönderim tedarikci.py Faz 3'te yapılır)"
        )

    return len(approved_mails)


# ── Sheet 4: Proforma Onay işleme ────────────────────────────────────────────

def _process_proforma_approvals_step(sheet_id: str) -> tuple:
    """Sheet 4'teki proforma onaylarını işler."""
    if not sheet_id:
        return 0, 0
    try:
        approved_list, rejected_list = process_proforma_approvals(sheet_id)
    except Exception as e:
        logger.warning(f"Sheet 4 okunamadı: {e}")
        return 0, 0

    if approved_list:
        logger.info(f"{len(approved_list)} proforma onaylandı (sipariş akışı M4'te)")
    return len(approved_list), len(rejected_list)


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

def _check_pending_approvals() -> dict:
    client = get_client()
    pending = (
        client.table("approval_queue")
        .select("id")
        .eq("status", "pending")
        .execute()
    )
    count = len(pending.data)
    counts = {
        "urun": count,
        "tedarikci": 0,  # M4'te dolar
        "mail": 0,       # M4'te dolar
        "proforma": 0,   # M4'te dolar
    }
    if count > 0:
        logger.info(f"{count} bekleyen ürün onayı var")
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
