# Fırsatçı Agent
# Görev: Google Trends TR + seed kategori verisiyle trend ürün fırsatları bulur,
#         Claude Haiku ile skorlar, approval_queue'ya ekler.
# Çalışma sıklığı: Günde 2 kez (Railway cron)
# M3: pytrends + Claude scoring aktif
# M4: Trendyol Seller API V3 entegrasyonu

import os
import json
import time
import random
from typing import Optional

import anthropic

from core.supabase_client import get_client
from core.logger import get_logger, log_run

logger = get_logger("firsatci")

AGENT_NAME = "firsatci"

# Fırsat taramasında pytrends başarısız olursa fallback seed kategoriler
SEED_CATEGORIES = [
    "akıllı saat", "kablosuz kulaklık", "powerbank", "şarj aleti",
    "yoga matı", "direnç bandı", "protein tozu",
    "hava fritözü", "blender", "kahve makinesi", "mini ütü",
    "cilt bakım seti", "saç düzleştirici", "göz kremi",
    "lego seti", "puzzle", "çocuk oyuncak",
    "laptop çantası", "oyuncu mouse", "web kamerası",
    "ev dekor", "led şerit", "yastık seti",
]


def run():
    start = time.time()
    logger.info("Fırsatçı başladı")

    try:
        opportunities = _scan_opportunities()
        if opportunities:
            _queue_for_approval(opportunities)

        duration_ms = int((time.time() - start) * 1000)
        mock_mode = os.getenv("MOCK_OPPORTUNITIES", "false").lower() == "true"
        log_run(
            AGENT_NAME,
            status="success",
            run_type="cron",
            items_processed=len(opportunities),
            items_success=len(opportunities),
            duration_ms=duration_ms,
            metadata={"mock": mock_mode, "count": len(opportunities)},
        )
        logger.info(f"{len(opportunities)} fırsat işlendi ({duration_ms}ms)")

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron",
                duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Fırsatçı hatası: {e}")
        raise


def _scan_opportunities() -> list:
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

    logger.info("Gerçek trend taraması başlıyor")

    # 1. Google Trends TR'den trending keyword'ler
    trending_keywords = _get_trending_keywords()

    # 2. Seed kategorilerden rastgele mix ekle (pytrends tek başına yeterli olmayabilir)
    seed_sample = random.sample(SEED_CATEGORIES, min(8, len(SEED_CATEGORIES)))

    # 3. Claude Haiku ile skorla ve fırsatları belirle
    opportunities = _score_with_claude(seed_sample, trending_keywords)
    logger.info(f"Claude skorlaması: {len(opportunities)} fırsat belirlendi")

    return opportunities


def _get_trending_keywords() -> list:
    """pytrends ile Türkiye günlük trending aramaları çeker.
    Başarısız olursa boş liste döner (caller seed_sample ile devam eder).
    """
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="tr-TR", tz=180, timeout=(10, 25), retries=2, backoff_factor=0.5)
        trending_df = pytrends.trending_searches(pn="turkey")
        trends = trending_df[0].tolist()[:20]
        logger.info(f"pytrends: {len(trends)} TR trend alındı")
        return trends
    except Exception as e:
        logger.warning(f"pytrends başarısız (seed kullanılacak): {e}")
        return []


def _score_with_claude(seed_categories: list, trending_keywords: list) -> list:
    """Claude Haiku ile ürün fırsatı skorlaması.
    trending_keywords: Google Trends'den gelen raw arama terimleri
    seed_categories: Her zaman değerlendirilen kategori havuzu
    Döner: approval_queue formatında dict listesi (max 3)
    """
    ai_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    trending_section = ""
    if trending_keywords:
        top_trends = trending_keywords[:15]
        trending_section = f"""Bugün Türkiye'de trend olan Google aramaları:
{chr(10).join(f'- {k}' for k in top_trends)}

"""

    prompt = f"""Sen Trendyol ve Shopify'da satan bir Türk e-ticaret satıcısının ürün analisti asistanısın.

{trending_section}Değerlendirilecek ürün kategorileri:
{chr(10).join(f'- {k}' for k in seed_categories)}

Görev: Yukarıdaki verilerden EN İYİ 3 ürün fırsatını seç. Kriter:
1. Net talep sinyali var (trend'de ya da evergreen)
2. Tedarik edilebilir (Alibaba, 1688, yerel toptancı)
3. Kar marjı hedef %30+ (Trendyol komisyonu ~%15 dahil)
4. Türkiye'de yasal kısıt yok (ilaç, silah, kimyasal değil)
5. Paket/kargo dostu (max 3kg, kırılgan değil)

Yanıtı SADECE JSON dizisi olarak ver, başka hiçbir şey yazma:
[
  {{
    "name": "Ürün adı (Türkçe)",
    "summary": "Neden fırsat? Talep sinyali, maliyet tahmini, margin potansiyeli. 2-3 cümle.",
    "trendyol_category": "Ana Kategori > Alt Kategori",
    "estimated_price_tl": 500,
    "estimated_margin_pct": 35,
    "trend_score": 80
  }}
]"""

    response = ai_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # JSON parse — bazen Claude ```json ... ``` bloğu ekler
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    scored = json.loads(raw)
    return scored[:3]  # max 3 fırsat


def _is_duplicate(title: str) -> bool:
    """Son 7 günde aynı başlıkla approval_queue'ya eklenmiş mi kontrol eder."""
    try:
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        client = get_client()
        result = (
            client.table("approval_queue")
            .select("id")
            .eq("title", title)
            .gte("created_at", cutoff)
            .execute()
        )
        return len(result.data) > 0
    except Exception as e:
        logger.warning(f"Duplicate kontrolü başarısız: {e}")
        return False


def _queue_for_approval(opportunities: list):
    client = get_client()
    queued = 0
    for opp in opportunities:
        title = opp.get("name", "Bilinmeyen ürün")

        if _is_duplicate(title):
            logger.info(f"Atlandı (son 7 günde zaten var): {title}")
            continue

        client.table("approval_queue").insert({
            "request_type": "product_approval",
            "agent_source": AGENT_NAME,
            "title": title,
            "summary": opp.get("summary", ""),
            "payload": opp,
            "status": "pending",
            "timeout_hours": 48,
        }).execute()
        queued += 1
        logger.info(f"approval_queue'ya eklendi: {title}")

    logger.info(f"{queued}/{len(opportunities)} fırsat kuyruğa eklendi")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
