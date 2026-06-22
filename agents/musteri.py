# Müşteri Agent — M4'te aktif olacak
from core.logger import get_logger, log_to_supabase
logger = get_logger("musteri")

def run():
    logger.info("Müşteri stub — M4'te aktif olacak")
    log_to_supabase("musteri", "INFO", "Stub çalıştı")

if __name__ == "__main__":
    from dotenv import load_dotenv; load_dotenv()
    run()
