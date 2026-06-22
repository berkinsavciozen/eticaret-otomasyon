import logging
from datetime import datetime
from typing import Optional
from core.supabase_client import get_client


def get_logger(agent_name: str) -> logging.Logger:
    logger = logging.getLogger(agent_name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def log_run(
    agent_name: str,
    status: str,
    run_type: str = "cron",
    items_processed: Optional[int] = None,
    items_success: Optional[int] = None,
    items_failed: Optional[int] = None,
    duration_ms: Optional[int] = None,
    error_message: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """agent_logs tablosuna bir çalışma kaydı yazar."""
    try:
        client = get_client()
        row = {
            "agent_name": agent_name,
            "run_type": run_type,
            "status": status,
            "started_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        if items_processed is not None:
            row["items_processed"] = items_processed
        if items_success is not None:
            row["items_success"] = items_success
        if items_failed is not None:
            row["items_failed"] = items_failed
        if duration_ms is not None:
            row["duration_ms"] = duration_ms
        if error_message is not None:
            row["error_message"] = error_message

        client.table("agent_logs").insert(row).execute()
    except Exception as e:
        logging.getLogger("logger").error(f"Supabase log_run failed: {e}")
