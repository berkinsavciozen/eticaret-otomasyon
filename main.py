"""
E-Ticaret Otomasyon — Ana Giriş Noktası
Railway cron job'ları bu dosyayı çağırır: python main.py <agent_name>

Kullanım:
  python main.py orkestrator
  python main.py firsatci
  python main.py tedarikci
  python main.py listeleme
  python main.py siparis
  python main.py finans
  python main.py operations   ← listeleme + siparis + finans sırayla
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()


def main():
    if len(sys.argv) < 2:
        print("Kullanım: python main.py <agent_name>")
        print("Agentlar: orkestrator, firsatci, tedarikci, listeleme, siparis, finans, pazarlama, musteri")
        sys.exit(1)

    agent_name = sys.argv[1].lower()

    # Healthchecks.io ping (opsiyonel)
    ping_url = os.getenv("HEALTHCHECKS_PING_URL")
    if ping_url:
        try:
            import requests
            requests.get(ping_url, timeout=5)
        except Exception:
            pass

    if agent_name == "orkestrator":
        from agents.orkestrator import run
    elif agent_name == "firsatci":
        from agents.firsatci import run
    elif agent_name == "tedarikci":
        from agents.tedarikci import run
    elif agent_name == "listeleme":
        from agents.listeleme import run
    elif agent_name == "siparis":
        from agents.siparis import run
    elif agent_name == "finans":
        from agents.finans import run
    elif agent_name == "pazarlama":
        from agents.pazarlama import run
    elif agent_name == "musteri":
        from agents.musteri import run
    elif agent_name == "operations":
        _run_operations()
        return
    else:
        print(f"Bilinmeyen agent: {agent_name}")
        sys.exit(1)

    run()


def _run_operations():
    """Listeleme → Sipariş → Finans sırayla çalıştırır.
    Railway'de tek servis olarak deploy edilir: eticaret-operations
    """
    from core.logger import get_logger
    logger = get_logger("operations")

    steps = [
        ("listeleme", "agents.listeleme"),
        ("siparis",   "agents.siparis"),
        ("finans",    "agents.finans"),
    ]

    for name, module_path in steps:
        try:
            logger.info(f"--- {name.upper()} başlıyor ---")
            import importlib
            module = importlib.import_module(module_path)
            module.run()
            logger.info(f"--- {name.upper()} tamamlandı ---")
        except Exception as e:
            logger.error(f"{name} başarısız: {e} — sonraki adıma geçiliyor")
            # Bir agent hata verse bile diğerleri çalışmaya devam eder


if __name__ == "__main__":
    main()
