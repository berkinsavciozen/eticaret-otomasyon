# Fırsatçı Agent
# Görev: Trendyol'da trend ürünleri tarar, fırsatları approval_queue'ya ekler.
# Çalışma sıklığı: Günde 2 kez (Railway cron)
# NOT: M2'de aktif olacak — Trendyol API erişimi M4'e kadar simüle edilir.

import time
from datetime import datetime, timezone
from core.supabase_client import get_client
from core.logger import get_logger, log_run

logger = get_logger("firsatci")

AGENT_NAME = "firsatci"


def run():
    start = time.time()
    logger.info("Fırsatçı başladı")

    try:
        opportunities = _scan_opportunities()
        if opportunities:
            _queue_for_approval(opportunities)

        duration_ms = int((time.time() - start) * 1000)
        log_run(
            AGENT_NAME,
            status="success",
            run_type="cron",
            items_processed=len(opportunities),
            items_success=len(opportunities),
            duration_ms=duration_ms,
            metadata={"note": "mock_scan_m2_placeholder"},
        )
        logger.info(f"{len(opportunities)} fırsat tarandı ({duration_ms}ms)")

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron", duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Fırsatçı hatası: {e}")
        raise


def _scan_opportunities() -> list:
    # TODO M2: Trendyol Seller API V3 entegrasyonu
    logger.info("Mock fırsat taraması (M2'de gerçek API)")
    return []


def _queue_for_approval(opportunities: list):
    client = get_client()
    for opp in opportunities:
        client.table("approval_queue").insert({
            "request_type": "product_approval",
            "agent_source": AGENT_NAME,
            "title": opp.get("name", "Bilinmeyen ürün"),
            "summary": opp.get("summary", ""),
            "payload": opp,
            "status": "pending",
            "timeout_hours": 48,
        }).execute()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
