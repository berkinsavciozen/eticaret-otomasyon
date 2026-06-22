# Sipariş Agent — M4'te aktif olacak
from core.logger import get_logger, log_to_supabase
logger = get_logger("siparis")

def run():
    logger.info("Sipariş stub — M4'te aktif olacak")
    log_to_supabase("siparis", "INFO", "Stub çalıştı")

if __name__ == "__main__":
    from dotenv import load_dotenv; load_dotenv()
    run()
