# Orkestratör Agent
# Görev: Diğer agentları tetikler, approval_queue'yu yönetir, sistem sağlığını kontrol eder.
# Çalışma sıklığı: Her 15 dakikada bir (Railway cron)

import time
from datetime import datetime
from core.supabase_client import get_client
from core.logger import get_logger, log_run

logger = get_logger("orkestrator")

AGENT_NAME = "orkestrator"


def run():
    start = time.time()
    logger.info("Orkestratör başladı")

    try:
        _check_pending_approvals()
        _check_agent_health()

        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="success", run_type="cron", duration_ms=duration_ms)
        logger.info(f"Orkestratör tamamlandı ({duration_ms}ms)")

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron", duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Orkestratör hatası: {e}")
        raise


def _check_pending_approvals():
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


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
