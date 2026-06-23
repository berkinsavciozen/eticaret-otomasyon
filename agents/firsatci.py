# Fırsatçı Agent
# Görev: Trendyol'da trend ürünleri tarar, fırsatları approval_queue'ya ekler.
# Çalışma sıklığı: Günde 2 kez (Railway cron)
# NOT: M4'e kadar MOCK_OPPORTUNITIES=true ile test edilir.

import os
import time
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
            metadata={"mock": os.getenv("MOCK_OPPORTUNITIES", "false") == "true"},
        )
        logger.info(f"{len(opportunities)} fırsat işlendi ({duration_ms}ms)")

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron",
                duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Fırsatçı hatası: {e}")
        raise


def _scan_opportunities() -> list:
    # TODO M4: Trendyol Seller API V3 entegrasyonu
    if os.getenv("MOCK_OPPORTUNITIES", "false").lower() == "true":
        logger.info("MOCK mod: 1 test fırsatı üretiliyor")
        return [{
            "name": "TEST - Akıllı Saat (Mock Veri)",
            "summary": "Trendyol'da trend olan ürün. Tahmini kar marjı %35. Haftalık satış: 1200+. [BU BİR TEST KAYDIDIR]",
            "trendyol_category": "Elektronik > Akıllı Saatler",
            "estimated_price_tl": 850,
            "estimated_margin_pct": 35,
            "mock": True,
        }]
    logger.info("Fırsat taraması (M4'te gerçek API bağlanacak)")
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
    logger.info(f"{len(opportunities)} kayıt approval_queue'ya eklendi")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
