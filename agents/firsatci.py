# Fırsatçı Agent
# Görev: Trendyol'da trend ürünleri tarar, fırsatları approval_queue'ya ekler.
# Çalışma sıklığı: Günde 2 kez (Railway cron)
# NOT: M2'de aktif olacak — Trendyol API erişimi M4'e kadar simüle edilir.

import os
from datetime import datetime
from core.supabase_client import get_client
from core.logger import get_logger, log_to_supabase

logger = get_logger("firsatci")

AGENT_NAME = "firsatci"


def run():
    logger.info("Fırsatçı başladı")
    log_to_supabase(AGENT_NAME, "INFO", "Fırsatçı çalışma döngüsü başladı")

    try:
        opportunities = _scan_opportunities()
        if opportunities:
            _queue_for_approval(opportunities)
        logger.info(f"{len(opportunities)} fırsat tarandı")
        log_to_supabase(AGENT_NAME, "INFO", f"{len(opportunities)} fırsat bulundu")
    except Exception as e:
        logger.error(f"Fırsatçı hatası: {e}")
        log_to_supabase(AGENT_NAME, "ERROR", str(e))
        raise


def _scan_opportunities() -> list[dict]:
    # TODO M2: Trendyol Seller API V3 entegrasyonu
    # Şimdilik mock data döner
    logger.info("Mock fırsat taraması (M2'de gerçek API)")
    return []


def _queue_for_approval(opportunities: list[dict]):
    client = get_client()
    for opp in opportunities:
        client.table("approval_queue").insert({
            "type": "product_opportunity",
            "payload": opp,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }).execute()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
