import logging
import os
from datetime import datetime

from core.supabase_client import get_client


def get_logger(agent_name: str) -> logging.Logger:
    logger = logging.getLogger(agent_name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def log_to_supabase(agent_name: str, level: str, message: str, metadata: dict = None):
    try:
        client = get_client()
        client.table("agent_logs").insert({
            "agent_name": agent_name,
            "level": level,
            "message": message,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        logging.getLogger("logger").error(f"Supabase log failed: {e}")
