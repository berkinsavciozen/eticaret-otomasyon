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
    else:
        print(f"Bilinmeyen agent: {agent_name}")
        sys.exit(1)

    run()


if __name__ == "__main__":
    main()
