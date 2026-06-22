# Pazarlama Agent — M5'te aktif olacak
from core.logger import get_logger, log_to_supabase
logger = get_logger("pazarlama")

def run():
    logger.info("Pazarlama stub — M5'te aktif olacak")
    log_to_supabase("pazarlama", "INFO", "Stub çalıştı")

if __name__ == "__main__":
    from dotenv import load_dotenv; load_dotenv()
    run()
