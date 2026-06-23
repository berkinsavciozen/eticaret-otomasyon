# Orkestratör Agent
# Görev: Diğer agentları tetikler, approval_queue'yu yönetir, sistem sağlığını kontrol eder.
# Çalışma sıklığı: Her 15 dakikada bir (Railway cron)

import os
import time
from datetime import datetime, timezone
from core.supabase_client import get_client
from core.logger import get_logger, log_run
from core.sheets_client import clear_and_write_sheet, read_sheet

logger = get_logger("orkestrator")

AGENT_NAME = "orkestrator"

# Sheets kolon indeksleri (0-based)
COL_ID = 0
COL_TYPE = 1
COL_TITLE = 2
COL_SUMMARY = 3
COL_AGENT = 4
COL_STATUS = 5
COL_CREATED = 6
COL_NOTE = 7

SHEETS_HEADER = [
    "ID", "Tip", "Başlık", "Özet", "Agent", "Durum", "Oluşturulma", "Onay Notu"
]


def run():
    start = time.time()
    logger.info("Orkestratör başladı")

    try:
        # 1. Sheets'teki onayları önce işle (Berkin'in değişiklikleri Supabase'e yansısın)
        approved, rejected = _process_sheet_approvals()

        # 2. Bekleyen onayları say (bildirim için)
        pending_count = _check_pending_approvals()

        # 3. Sheets'i Supabase'den tazele (güncel durumu yaz)
        _mirror_approval_queue_to_sheets()

        # 4. Agent sağlık kontrolü
        _check_agent_health()

        # 5. Bekleyen onay varsa Gmail bildirimi
        if pending_count > 0:
            _send_gmail_reminder(pending_count)

        duration_ms = int((time.time() - start) * 1000)
        log_run(
            AGENT_NAME,
            status="success",
            run_type="cron",
            duration_ms=duration_ms,
            metadata={"approved": approved, "rejected": rejected, "pending": pending_count},
        )
        logger.info(f"Orkestratör tamamlandı ({duration_ms}ms) — onaylanan: {approved}, reddedilen: {rejected}")

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron",
                duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Orkestratör hatası: {e}")
        raise


def _process_sheet_approvals() -> tuple:
    """
    Sheets'teki Durum kolonunu okur.
    'approved' veya 'rejected' olan satırları Supabase'e yansıtır.
    Onaylananları products tablosuna ekler.
    """
    sheet_id = os.getenv("SHEETS_APPROVAL_QUEUE_ID")
    if not sheet_id:
        return 0, 0

    try:
        rows = read_sheet(sheet_id, "Onay Kuyruğu!A1:H200")
    except Exception as e:
        logger.warning(f"Sheets okunamadı: {e}")
        return 0, 0

    if len(rows) <= 1:  # sadece header veya boş
        return 0, 0

    approved_count = 0
    rejected_count = 0
    client = get_client()

    for row in rows[1:]:  # header'ı atla
        if len(row) <= COL_STATUS:
            continue

        row_id = row[COL_ID] if len(row) > COL_ID else ""
        sheet_status = row[COL_STATUS].strip().lower() if len(row) > COL_STATUS else ""
        decision_note = row[COL_NOTE].strip() if len(row) > COL_NOTE else ""

        if not row_id or sheet_status not in ("approved", "rejected"):
            continue

        # Supabase'deki mevcut durumu kontrol et
        try:
            result = client.table("approval_queue").select("id, status").eq("id", row_id).execute()
        except Exception:
            continue

        if not result.data:
            continue

        current_status = result.data[0].get("status", "")
        if current_status != "pending":
            continue  # zaten işlenmiş

        # approval_queue güncelle
        client.table("approval_queue").update({
            "status": sheet_status,
            "decision_note": decision_note,
        }).eq("id", row_id).execute()

        if sheet_status == "approved":
            _create_product_from_approval(result.data[0]["id"], row, client)
            approved_count += 1
            logger.info(f"Onaylandı ve products'a eklendi: {row[COL_TITLE] if len(row) > COL_TITLE else row_id}")
        else:
            rejected_count += 1
            logger.info(f"Reddedildi: {row[COL_TITLE] if len(row) > COL_TITLE else row_id}")

    return approved_count, rejected_count


def _create_product_from_approval(approval_id: str, row: list, client):
    """Onaylanan approval_queue kaydından products tablosuna kayıt oluşturur."""
    title = row[COL_TITLE] if len(row) > COL_TITLE else "Bilinmeyen ürün"
    request_type = row[COL_TYPE] if len(row) > COL_TYPE else ""

    # Aynı başlıkta ürün zaten varsa ekleme
    existing = client.table("products").select("id").eq("name", title).execute()
    if existing.data:
        logger.info(f"products'ta zaten var, atlandı: {title}")
        return

    client.table("products").insert({
        "name": title,
        "status": "approved",
        "category": request_type,
    }).execute()


def _check_pending_approvals() -> int:
    client = get_client()
    pending = (
        client.table("approval_queue")
        .select("id, status")
        .eq("status", "pending")
        .execute()
    )
    count = len(pending.data)
    if count > 0:
        logger.info(f"{count} bekleyen onay var")
    else:
        logger.info("Bekleyen onay yok")
    return count


def _mirror_approval_queue_to_sheets():
    """approval_queue tablosunu Google Sheets'e yazar."""
    sheet_id = os.getenv("SHEETS_APPROVAL_QUEUE_ID")
    if not sheet_id:
        logger.info("SHEETS_APPROVAL_QUEUE_ID tanımlı değil, mirror atlandı")
        return

    client = get_client()
    rows = (
        client.table("approval_queue")
        .select("*")
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )

    values = [SHEETS_HEADER]
    for r in rows.data:
        values.append([
            str(r.get("id", "")),
            r.get("request_type", ""),
            r.get("title", ""),
            r.get("summary", ""),
            r.get("agent_source", ""),
            r.get("status", ""),
            str(r.get("created_at", "")),
            r.get("decision_note", "") or "",
        ])

    clear_and_write_sheet(sheet_id, "Onay Kuyruğu!A1", values)
    logger.info(f"Sheets mirror: {len(rows.data)} kayıt yazıldı")


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


def _send_gmail_reminder(pending_count: int):
    """Bekleyen onaylar için Gmail bildirimi gönderir."""
    notification_email = os.getenv("NOTIFICATION_EMAIL")
    if not notification_email:
        logger.info("NOTIFICATION_EMAIL tanımlı değil, mail atlandı")
        return

    try:
        import base64
        from email.mime.text import MIMEText
        from core.sheets_client import get_gmail_service

        sheet_id = os.getenv("SHEETS_APPROVAL_QUEUE_ID", "")
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}" if sheet_id else ""

        body = f"""Merhaba,

{pending_count} adet onay bekleyen kayıt var.

Onay paneline gitmek için:
{sheet_url}

Onaylamak için "Durum" kolonunu "approved", reddetmek için "rejected" yap.

— E-Ticaret Otomasyon Sistemi
"""
        message = MIMEText(body)
        message["to"] = notification_email
        message["subject"] = f"[E-Ticaret] {pending_count} onay bekliyor"

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
