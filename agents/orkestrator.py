# Orkestratör Agent
# Görev: Diğer agentları tetikler, approval_queue'yu yönetir, sistem sağlığını kontrol eder.
# Çalışma sıklığı: Her 15 dakikada bir (Railway cron)

import os
from core.supabase_client import get_client
from core.logger import get_logger, log_to_supabase

logger = get_logger("orkestrator")

AGENT_NAME = "orkestrator"


def run():
    logger.info("Orkestratör başladı")
    log_to_supabase(AGENT_NAME, "INFO", "Orkestratör çalışma döngüsü başladı")

    try:
        _check_pending_approvals()
        _check_agent_health()
        logger.info("Orkestratör tamamlandı")
        log_to_supabase(AGENT_NAME, "INFO", "Döngü başarıyla tamamlandı")
    except Exception as e:
        logger.error(f"Orkestratör hatası: {e}")
        log_to_supabase(AGENT_NAME, "ERROR", str(e))
        raise


def _check_pending_approvals():
    client = get_client()
    pending = (
        client.table("approval_queue")
        .select("*")
        .eq("status", "pending")
        .execute()
    )
    count = len(pending.data)
    if count > 0:
        logger.info(f"{count} bekleyen onay var")
        log_to_supabase(AGENT_NAME, "INFO", f"{count} bekleyen onay", {"count": count})


def _check_agent_health():
    client = get_client()
    recent = (
        client.table("agent_logs")
        .select("agent_name, created_at")
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    logger.info(f"Son {len(recent.data)} log kaydı kontrol edildi")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
