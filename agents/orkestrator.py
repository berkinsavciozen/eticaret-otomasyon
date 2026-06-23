# Orkestratör Agent
# Görev: Diğer agentları tetikler, approval_queue'yu yönetir, sistem sağlığını kontrol eder.
# Çalışma sıklığı: Her 15 dakikada bir (Railway cron)

import os
import time
from datetime import datetime, timezone
from core.supabase_client import get_client
from core.logger import get_logger, log_run
from core.sheets_client import clear_and_write_sheet

logger = get_logger("orkestrator")

AGENT_NAME = "orkestrator"

SHEETS_HEADER = [
    "ID", "Tip", "Başlık", "Özet", "Agent", "Durum", "Oluşturulma", "Onay Notu"
]


def run():
    start = time.time()
    logger.info("Orkestratör başladı")

    try:
        pending_count = _check_pending_approvals()
        _mirror_approval_queue_to_sheets()
        _check_agent_health()

        if pending_count > 0:
            _send_gmail_reminder(pending_count)

        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="success", run_type="cron", duration_ms=duration_ms)
        logger.info(f"Orkestratör tamamlandı ({duration_ms}ms)")

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron",
                duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Orkestratör hatası: {e}")
        raise


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
            r.get("decision_note", ""),
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
