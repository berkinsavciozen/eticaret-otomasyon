# Finans Agent — M4'te aktif olacak
from core.logger import get_logger, log_to_supabase
logger = get_logger("finans")

def run():
    logger.info("Finans stub — M4'te aktif olacak")
    log_to_supabase("finans", "INFO", "Stub çalıştı")

if __name__ == "__main__":
    from dotenv import load_dotenv; load_dotenv()
    run()
