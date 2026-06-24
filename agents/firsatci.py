# Fırsatçı Agent — M4
# Görev: Deterministik 3-bileşen puanlama (Trend/40 + Pazar/35 + Fizibilite/25)
#         ile ürün fırsatları bulur, approval_queue'ya ekler.
# Cron 3 fazlı: A) Mevcut kayıtları yeniden skorla  B) Yeni öğe ekle  C) Önceliklendirme
# Çalışma sıklığı: Günde 2 kez (Railway cron: 0 6,18 * * *)

import os
import json
import time
import random
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple

import requests
import anthropic

from core.supabase_client import get_client
from core.logger import get_logger, log_run

logger = get_logger("firsatci")

AGENT_NAME = "firsatci"

# ── Puanlama sabitleri ────────────────────────────────────────────────────────
SCORE_THRESHOLD = 60          # approval_queue'ya girebilmek için minimum skor
REJECTED_CONVERT_DELTA = 20   # Red edilen ürün bu kadar skor artarsa pending'e çevrilir

# ── Sermaye limiti ────────────────────────────────────────────────────────────
_CAPITAL_LIMIT_TL = int(os.getenv("CAPITAL_LIMIT_TL", "10000"))
_MIN_MOQ_ESTIMATE = 50        # Minimum sipariş miktarı tahmini (adet)
_COST_RATIO       = 0.45      # Satış fiyatının kaçı maliyet (0.45 = %45)

# ── Sezonluk ceza kelimeleri ──────────────────────────────────────────────────
_WINTER_KEYWORDS = ["bota", "kaban", "mont ", "bere ", "eldiven", "kazak",
                    "palto", "kar botu", "atkı", "çizme"]
_SUMMER_KEYWORDS = ["mayo ", "bikini", "güneş kremı", "soğutucu", "klima",
                    "havuz", "sörf", "çadır", "güneş gözlüğü"]

# ── Seed kategoriler (pytrends fallback) ─────────────────────────────────────
SEED_CATEGORIES = [
    "akıllı saat", "kablosuz kulaklık", "powerbank", "şarj aleti",
    "yoga matı", "direnç bandı", "protein tozu", "dambıl set",
    "hava fritözü", "blender", "kahve makinesi", "mini ütü",
    "cilt bakım seti", "saç düzleştirici", "göz kremi", "nemlendirici",
    "lego seti", "puzzle", "çocuk oyuncak", "bebek monitörü",
    "laptop çantası", "oyuncu mouse", "web kamerası", "klavye",
    "ev dekor", "led şerit", "yastık seti", "dekoratif ayna",
    "makyaj çantası", "parfüm şişesi", "tırnak seti",
]

# ── Trendyol public API ───────────────────────────────────────────────────────
_TRENDYOL_SEARCH_URL = (
    "https://public.trendyol.com/discovery-web-searchgw-service/api/filter/"
    "product-search-v2?q={q}&culture=tr-TR&currency=TRY"
)
_REDDIT_TR_URL = (
    "https://www.reddit.com/r/Turkey/search.json?q={q}&sort=hot&t=week&restrict_sr=true"
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ═════════════════════════════════════════════════════════════════════════════
# ANA AKIŞ
# ═════════════════════════════════════════════════════════════════════════════

def run():
    start = time.time()
    logger.info("Fırsatçı başladı (M4 deterministik puanlama)")

    try:
        mock_mode = os.getenv("MOCK_OPPORTUNITIES", "false").lower() == "true"

        if mock_mode:
            _run_mock()
            return

        # ── Faz A: Mevcut kayıtları yeniden skorla ───────────────────────────
        recalc_updated, recalc_converted = _recalculate_existing_items()
        logger.info(f"Faz A: {recalc_updated} güncellendi, {recalc_converted} rejected→pending")

        # ── Faz B: Yeni fırsatlar bul & kuyruğa ekle ─────────────────────────
        new_opportunities = _scan_new_opportunities()
        queued = 0
        if new_opportunities:
            queued = _queue_for_approval(new_opportunities)
        logger.info(f"Faz B: {queued} yeni fırsat eklendi")

        # ── Faz C: Önceliklendirme ─────────────────────────────────────────
        ranked = _run_priority_ranking()
        logger.info(f"Faz C: {ranked} öğe önceliklendirildi")

        total_items = recalc_updated + queued
        duration_ms = int((time.time() - start) * 1000)
        log_run(
            AGENT_NAME,
            status="success",
            run_type="cron",
            items_processed=total_items,
            items_success=total_items,
            duration_ms=duration_ms,
            metadata={
                "recalc_updated": recalc_updated,
                "recalc_converted": recalc_converted,
                "new_queued": queued,
                "priority_ranked": ranked,
            },
        )
        logger.info(f"Fırsatçı tamamlandı ({duration_ms}ms)")

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron",
                duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Fırsatçı hatası: {e}")
        raise


def _run_mock():
    """MOCK_OPPORTUNITIES=true olduğunda test kaydı ekler."""
    logger.info("MOCK mod: test fırsatı üretiliyor")
    mock_opp = {
        "name": "TEST - Kablosuz Kulaklık (Mock)",
        "summary": "[TEST] Trendyol'da trend ürün. Bu bir test kaydıdır.",
        "trendyol_category": "Elektronik > Kulaklıklar",
        "estimated_price_tl": 650,
        "estimated_margin_pct": 32,
        "scoring": {
            "total": 72,
            "trend": {"total": 28, "pytrends": 14, "rising": 8, "sosyal": 6, "sezon_ceza": 0},
            "pazar": {"total": 25, "listing_sayisi": 5000, "talep": 15, "fiyat_via": 10},
            "fizibilite": {"total": 19, "marj_pct": 32, "marj_skor": 12, "kargo": 5, "yasal": 2},
        },
        "mock": True,
    }
    _queue_for_approval([mock_opp])


# ═════════════════════════════════════════════════════════════════════════════
# FAZ A — Mevcut kayıtları yeniden skorla
# ═════════════════════════════════════════════════════════════════════════════

def _recalculate_existing_items() -> Tuple[int, int]:
    """
    approval_queue'daki firsatci kaynaklı pending + rejected öğeleri yeniden skorlar.
    rejected öğede skor REJECTED_CONVERT_DELTA kadar artarsa pending'e çevrilir
    ve converted_from_rejected tag'i eklenir.
    Returns: (updated_count, converted_count)
    """
    client = get_client()
    updated = 0
    converted = 0

    try:
        result = (
            client.table("approval_queue")
            .select("*")
            .eq("agent_source", AGENT_NAME)
            .in_("status", ["pending", "rejected"])
            .execute()
        )
    except Exception as e:
        logger.error(f"Faz A: Supabase sorgu hatası: {e}")
        return 0, 0

    for item in result.data:
        try:
            keyword       = item.get("title", "")
            old_meta      = item.get("metadata") or {}
            old_scoring   = old_meta.get("scoring", {})
            old_total     = int(old_scoring.get("total", 0))
            est_price     = int(old_meta.get("estimated_price_tl", 0) or 0)

            new_scoring   = _score_item(keyword, est_price or None)
            new_total     = new_scoring["total"]
            delta         = new_total - old_total

            # Metadata güncelle
            new_meta = dict(old_meta)
            new_meta["scoring"]            = new_scoring
            new_meta["last_recalculated"]  = datetime.now(timezone.utc).isoformat()

            update_payload: Dict[str, Any] = {
                "metadata": new_meta,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            # rejected + skor sıçraması → pending'e geri al
            if item.get("status") == "rejected" and delta >= REJECTED_CONVERT_DELTA:
                update_payload["status"]       = "pending"
                update_payload["decision_note"] = (
                    f"[Sistem] Red sonrası skor +{delta} arttı "
                    f"({old_total}→{new_total}). Yeniden değerlendirmeye alındı."
                )
                new_meta["converted_from_rejected"] = True
                new_meta["convert_delta"]           = delta
                update_payload["metadata"]          = new_meta
                converted += 1
                logger.info(f"converted_from_rejected: '{keyword}' (+{delta} puan)")

            client.table("approval_queue").update(update_payload).eq("id", item["id"]).execute()
            updated += 1
            time.sleep(0.5)  # rate limit

        except Exception as e:
            logger.warning(f"Faz A: '{item.get('title', '?')}' yeniden skorlama hatası: {e}")

    return updated, converted


# ═════════════════════════════════════════════════════════════════════════════
# FAZ B — Yeni fırsatlar tara
# ═════════════════════════════════════════════════════════════════════════════

def _scan_new_opportunities() -> List[Dict[str, Any]]:
    """Trend ve seed verilerinden yeni ürün fırsatları üretir."""
    logger.info("Faz B: Yeni fırsat taraması başlıyor")

    # 1. pytrends interest_over_time ile stabil TR trend verileri
    trending_keywords = _get_pytrends_trending()

    # 2. Seed'den rastgele karışım
    seed_sample = random.sample(SEED_CATEGORIES, min(10, len(SEED_CATEGORIES)))

    # 3. Birleştir (tekrarsız)
    all_candidates = list(dict.fromkeys(trending_keywords[:12] + seed_sample))
    logger.info(f"Toplam {len(all_candidates)} aday anahtar kelime")

    # 4. Her aday için deterministik skor hesapla
    scored_candidates = []
    for i, keyword in enumerate(all_candidates):
        try:
            if i > 0:
                time.sleep(2)  # rate limit: pytrends + Trendyol

            # Tahmini fiyatı Claude ile al (toplu sorgu — aşağıda)
            scoring = _score_item(keyword, estimated_price_tl=None)
            if scoring["total"] >= SCORE_THRESHOLD:
                scored_candidates.append({
                    "keyword": keyword,
                    "scoring": scoring,
                })
                logger.info(f"  [{i+1}/{len(all_candidates)}] '{keyword}' → skor {scoring['total']}")
            else:
                logger.info(f"  [{i+1}/{len(all_candidates)}] '{keyword}' → skor {scoring['total']} (eşik altı, atlandı)")

        except Exception as e:
            logger.warning(f"  '{keyword}' skor hatası: {e}")

    if not scored_candidates:
        logger.info("Eşiği geçen fırsat bulunamadı, Claude fallback çalışıyor")
        return _claude_fallback_opportunities(seed_sample)

    # 5. Geçen adaylar için Claude'dan özet + tahmini fiyat al
    return _enrich_with_claude(scored_candidates)


def _enrich_with_claude(candidates: List[Dict]) -> List[Dict]:
    """Claude Haiku ile eşiği geçen adaylara özet, fiyat ve kategori bilgisi ekler."""
    ai_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    candidate_lines = []
    for c in candidates[:8]:  # max 8 aday (token limiti)
        sc = c["scoring"]
        candidate_lines.append(
            f"- {c['keyword']} | Skor:{sc['total']} | Trend:{sc['trend']['total']} | "
            f"Pazar:{sc['pazar']['total']} | Fizibilite:{sc['fizibilite']['total']}"
        )

    prompt = f"""Sen Türk e-ticaret pazarı uzmanısın. Aşağıdaki aday ürünler veri ile puanlandı.
Her aday için Türkçe ürün adı, kısa özet, Trendyol kategori yolu ve tahmini satış fiyatı (TL) belirle.

Adaylar:
{chr(10).join(candidate_lines)}

Kriter: Alibaba/1688'den tedarik edilebilir, %30+ net marj potansiyeli, Türkiye'de yasal.

SADECE JSON dizisi döndür:
[
  {{
    "keyword": "orijinal anahtar kelime",
    "name": "Ürün adı Türkçe",
    "summary": "Neden fırsat? Talep sinyali + maliyet + margin. Max 2 cümle.",
    "trendyol_category": "Ana > Alt",
    "estimated_price_tl": 500,
    "estimated_margin_pct": 35
  }}
]"""

    try:
        response = ai_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        enriched = json.loads(raw)
    except Exception as e:
        logger.error(f"Claude enrichment hatası: {e}")
        return []

    # Scoring verisini Claude çıktısıyla birleştir
    candidate_map = {c["keyword"]: c for c in candidates}
    results = []
    for item in enriched:
        kw = item.get("keyword", "")
        orig = candidate_map.get(kw, {})
        scoring = orig.get("scoring", {})

        # estimated_price_tl artık bilindiği için sermaye kontrolü yap
        est_price   = int(item.get("estimated_price_tl") or 0)
        sermaye_ok  = _check_capital(est_price)

        # Fizibilite marj skor'unu gerçek marj ile güncelle
        marj_pct = int(item.get("estimated_margin_pct") or 0)
        marj_skor = _marj_to_score(marj_pct)
        scoring.setdefault("fizibilite", {})["marj_pct"]   = marj_pct
        scoring.setdefault("fizibilite", {})["marj_skor"]  = marj_skor
        # Fizibilite toplamı güncelle
        fiz = scoring.get("fizibilite", {})
        fiz["total"] = fiz.get("marj_skor", 0) + fiz.get("kargo", 0) + fiz.get("yasal", 0)
        # Genel total güncelle
        scoring["total"] = (
            scoring.get("trend", {}).get("total", 0)
            + scoring.get("pazar", {}).get("total", 0)
            + fiz["total"]
        )

        results.append({
            "name":                 item.get("name", kw),
            "summary":              item.get("summary", ""),
            "trendyol_category":    item.get("trendyol_category", ""),
            "estimated_price_tl":   est_price,
            "estimated_margin_pct": marj_pct,
            "scoring":              scoring,
            "sermaye_ok":           sermaye_ok,
        })

    return results


def _claude_fallback_opportunities(seed_sample: List[str]) -> List[Dict]:
    """Tüm veri kaynakları skor eşiği geçemediğinde Claude'un doğrudan değerlendirmesi."""
    ai_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = f"""Türk e-ticaret uzmanı olarak şu kategorilerden EN İYİ 3 fırsatı seç:
{chr(10).join(f'- {k}' for k in seed_sample)}

Kriter: Alibaba tedarik, %30+ marj, yasal, kargo dostu (max 3kg).

SADECE JSON dizisi ver:
[
  {{
    "name": "Ürün adı Türkçe",
    "summary": "Neden fırsat? Max 2 cümle.",
    "trendyol_category": "Ana > Alt",
    "estimated_price_tl": 500,
    "estimated_margin_pct": 35,
    "scoring": {{
      "total": 65,
      "trend":       {{"total": 20, "pytrends": 10, "rising": 5, "sosyal": 5, "sezon_ceza": 0}},
      "pazar":       {{"total": 25, "listing_sayisi": 3000, "talep": 15, "fiyat_via": 10}},
      "fizibilite":  {{"total": 20, "marj_pct": 35, "marj_skor": 12, "kargo": 5, "yasal": 3}}
    }}
  }}
]"""
    try:
        response = ai_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        items = json.loads(raw)
        for item in items:
            ep = int(item.get("estimated_price_tl") or 0)
            item["sermaye_ok"] = _check_capital(ep)
        return items[:3]
    except Exception as e:
        logger.error(f"Claude fallback hatası: {e}")
        return []


# ═════════════════════════════════════════════════════════════════════════════
# FAZ C — Önceliklendirme
# ═════════════════════════════════════════════════════════════════════════════

def _run_priority_ranking() -> int:
    """Pending approval_queue öğelerini Claude ile önceliklendirir."""
    client = get_client()
    try:
        result = (
            client.table("approval_queue")
            .select("id, title, metadata")
            .eq("status", "pending")
            .eq("agent_source", AGENT_NAME)
            .execute()
        )
    except Exception as e:
        logger.error(f"Faz C: Supabase sorgu hatası: {e}")
        return 0

    if not result.data:
        return 0

    items_for_claude = []
    for r in result.data:
        meta    = r.get("metadata") or {}
        scoring = meta.get("scoring", {})
        items_for_claude.append({
            "id":    r["id"],
            "title": r["title"],
            "total": scoring.get("total", 0),
            "trend": scoring.get("trend", {}).get("total", 0),
            "pazar": scoring.get("pazar", {}).get("total", 0),
            "fiz":   scoring.get("fizibilite", {}).get("total", 0),
            "marj":  scoring.get("fizibilite", {}).get("marj_pct", 0),
        })

    if not items_for_claude:
        return 0

    prompt = f"""E-ticaret fırsat değerlendirme uzmanısın.
Şu anda onay bekleyen ürünleri öncelik sırasına diz:

{json.dumps(items_for_claude, ensure_ascii=False)}

Değerlendirme kriterleri (önem sırasıyla):
1. Toplam skor (total) yüksek olması
2. Trend skoru yüksek → hızlı satış
3. Marj yüksek → kârlılık
4. Talep güçlü → düşük stok riski

SADECE JSON dizisi döndür (tüm öğeleri dahil et):
[
  {{"id": "uuid", "rank": 1, "reason": "Max 50 karakter gerekçe"}},
  ...
]"""

    try:
        ai_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = ai_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        ranked = json.loads(raw)
    except Exception as e:
        logger.error(f"Faz C: Claude önceliklendirme hatası: {e}")
        return 0

    # Her öğenin metadata.priority'sini güncelle
    updated = 0
    for entry in ranked:
        item_id = entry.get("id")
        if not item_id:
            continue
        try:
            # Mevcut metadata'yı al
            res = client.table("approval_queue").select("metadata").eq("id", item_id).execute()
            if not res.data:
                continue
            meta = res.data[0].get("metadata") or {}
            meta["priority"] = {
                "rank":   entry.get("rank", 99),
                "reason": entry.get("reason", ""),
            }
            client.table("approval_queue").update({"metadata": meta}).eq("id", item_id).execute()
            updated += 1
        except Exception as e:
            logger.warning(f"Faz C: Priority güncelleme hatası {item_id}: {e}")

    return updated


# ═════════════════════════════════════════════════════════════════════════════
# PUANLAMA FONKSİYONLARI
# ═════════════════════════════════════════════════════════════════════════════

def _score_item(keyword: str, estimated_price_tl: Optional[int] = None) -> Dict[str, Any]:
    """
    Deterministik 3-bileşen puanlama.
    Trend Gücü (40) + Pazar Büyüklüğü (35) + Fizibilite (25) = max 100.
    """
    # 1. Trend Gücü (40)
    pytrends_score, rising_score = _get_pytrends_score(keyword)
    sosyal_score                 = _get_social_score(keyword)
    sezon_ceza                   = _get_seasonal_penalty(keyword)
    trend_total = max(0, min(40, pytrends_score + rising_score + sosyal_score + sezon_ceza))

    # 2. Pazar Büyüklüğü (35)
    listing_sayisi, talep_score, fiyat_via = _get_trendyol_data(keyword, estimated_price_tl)
    pazar_total = min(35, talep_score + fiyat_via)

    # 3. Fizibilite (25) — marj_pct bilinmiyorsa kategori tahmini kullanılır
    marj_pct, marj_skor, kargo_skor, yasal_skor = _get_feasibility_score(
        estimated_price_tl, keyword
    )
    fiz_total = min(25, marj_skor + kargo_skor + yasal_skor)

    total = trend_total + pazar_total + fiz_total

    return {
        "total": total,
        "trend": {
            "total":      trend_total,
            "pytrends":   pytrends_score,
            "rising":     rising_score,
            "sosyal":     sosyal_score,
            "sezon_ceza": sezon_ceza,
        },
        "pazar": {
            "total":         pazar_total,
            "listing_sayisi": listing_sayisi,
            "talep":         talep_score,
            "fiyat_via":     fiyat_via,
        },
        "fizibilite": {
            "total":     fiz_total,
            "marj_pct":  marj_pct,
            "marj_skor": marj_skor,
            "kargo":     kargo_skor,
            "yasal":     yasal_skor,
        },
    }


def _get_pytrends_score(keyword: str) -> Tuple[int, int]:
    """
    pytrends interest_over_time ile TR trend skoru.
    Returns: (pytrends_score 0-20, rising_score 0-10)
    """
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="tr-TR", tz=180, timeout=(10, 25), retries=1, backoff_factor=0.5)
        pytrends.build_payload([keyword], cat=0, timeframe="now 7-d", geo="TR")

        # interest_over_time (0-100 Google skalası)
        df = pytrends.interest_over_time()
        pt_score = 0
        if not df.empty and keyword in df.columns:
            avg = float(df[keyword].mean())
            pt_score = int(avg * 20 / 100)  # normalize 0→20

        # Rising queries → rising_score
        related = pytrends.related_queries()
        rising_df = related.get(keyword, {}).get("rising")
        rq_score = 0
        if rising_df is not None and not rising_df.empty:
            count = min(len(rising_df), 10)
            rq_score = count  # 1 rising query per point, max 10

        logger.debug(f"pytrends '{keyword}': interest={pt_score}, rising={rq_score}")
        return pt_score, rq_score

    except Exception as e:
        logger.warning(f"pytrends '{keyword}' hatası: {e}")
        return 8, 4  # Makul default (eşiği geçmemek için düşük)


def _get_social_score(keyword: str) -> int:
    """
    Reddit TR'de keyword aktivitesine göre sosyal skor (0-10).
    """
    try:
        url = _REDDIT_TR_URL.format(q=urllib.parse.quote(keyword))
        resp = requests.get(url, headers=_HEADERS, timeout=8)
        if resp.status_code != 200:
            return 5
        data  = resp.json()
        posts = data.get("data", {}).get("children", [])
        # Aktif post sayısı × 2, max 10
        score = min(len(posts) * 2, 10)
        logger.debug(f"Reddit TR '{keyword}': {len(posts)} post → skor {score}")
        return score
    except Exception as e:
        logger.warning(f"Reddit skor '{keyword}' hatası: {e}")
        return 5  # nötr default


def _get_seasonal_penalty(keyword: str) -> int:
    """
    Mevcut aya göre sezonluk ceza.
    Returns: 0 veya -10
    """
    month = datetime.now().month
    kw_lower = keyword.lower()

    is_summer = 5 <= month <= 8   # Mayıs–Ağustos
    is_winter = month in (12, 1, 2, 3)  # Aralık–Mart

    if is_summer and any(w in kw_lower for w in _WINTER_KEYWORDS):
        logger.debug(f"Sezon cezası (-10): '{keyword}' kış ürünü, yaz ayı")
        return -10
    if is_winter and any(w in kw_lower for w in _SUMMER_KEYWORDS):
        logger.debug(f"Sezon cezası (-10): '{keyword}' yaz ürünü, kış ayı")
        return -10
    return 0


def _get_trendyol_data(
    keyword: str,
    estimated_price_tl: Optional[int] = None,
) -> Tuple[int, int, int]:
    """
    Trendyol public search API'den pazar verileri.
    Returns: (listing_sayisi, talep_score 0-20, fiyat_viabilite 0-15)
    """
    try:
        url  = _TRENDYOL_SEARCH_URL.format(q=urllib.parse.quote(keyword))
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        if resp.status_code != 200:
            return 0, 10, 8  # default fallback

        data     = resp.json()
        result   = data.get("result", {})
        total    = int(result.get("totalCount", 0))
        products = result.get("products", [])

        # Talep skoru (0-20) — listing yoğunluğu = talep sinyali
        if total > 50_000:   talep = 20
        elif total > 20_000: talep = 17
        elif total > 10_000: talep = 14
        elif total > 5_000:  talep = 11
        elif total > 1_000:  talep = 8
        elif total > 100:    talep = 5
        else:                talep = 2

        # Fiyat viabilite (0-15) — mevcut ürünlerle fiyat rekabeti
        fiyat_via = 8  # default
        if products and estimated_price_tl and estimated_price_tl > 0:
            prices = []
            for p in products[:20]:
                sp = p.get("price", {}).get("sellingPrice", 0)
                if sp and float(sp) > 0:
                    prices.append(float(sp))
            if prices:
                avg_mkt = sum(prices) / len(prices)
                # Pazar ortalaması bizim fiyatımızdan yüksekse rekabetçi girebiliriz
                ratio = avg_mkt / estimated_price_tl
                if ratio >= 1.3:   fiyat_via = 15
                elif ratio >= 1.1: fiyat_via = 12
                elif ratio >= 0.9: fiyat_via = 9
                elif ratio >= 0.7: fiyat_via = 5
                else:              fiyat_via = 2

        logger.debug(f"Trendyol '{keyword}': count={total}, talep={talep}, fiyat_via={fiyat_via}")
        return total, talep, fiyat_via

    except Exception as e:
        logger.warning(f"Trendyol '{keyword}' hatası: {e}")
        return 0, 10, 8  # makul fallback


def _get_feasibility_score(
    estimated_price_tl: Optional[int],
    keyword: str = "",
) -> Tuple[int, int, int, int]:
    """
    Fizibilite puanlaması.
    Returns: (marj_pct, marj_skor 0-15, kargo_skor 0-5, yasal_skor 0-5)
    """
    # Marj tahmini — fiyata göre kaba tahmin (gerçek marj Claude enrichment'ta güncellenir)
    marj_pct = _estimate_margin(keyword, estimated_price_tl)
    marj_skor = _marj_to_score(marj_pct)

    # Kargo skoru — keyword'den ağırlık/boyut kestirimi
    kw = keyword.lower()
    heavy_items = ["koltuk", "mobilya", "bisiklet", "kayak", "ağırlık", "squat rack"]
    fragile_items = ["cam", "porselen", "kristal", "ayna"]
    if any(w in kw for w in heavy_items) or any(w in kw for w in fragile_items):
        kargo_skor = 2
    else:
        kargo_skor = 5  # çoğu ürün kargo dostudur

    # Yasal skor
    restricted = ["ilaç", "vitamin", "gıda takviyesi", "alkol", "sigara",
                  "silah", "bıçak", "kimyasal", "patlayıcı"]
    if any(w in kw for w in restricted):
        yasal_skor = 0
    else:
        yasal_skor = 5

    return marj_pct, marj_skor, kargo_skor, yasal_skor


def _estimate_margin(keyword: str, estimated_price_tl: Optional[int] = None) -> int:
    """Kategoriye ve fiyata göre kaba marj tahmini (gerçek skor Claude'dan gelir)."""
    kw = keyword.lower()

    # Elektronik: düşük marj (rekabetçi pazar)
    if any(w in kw for w in ["kulaklık", "saat", "powerbank", "şarj", "mouse",
                               "klavye", "kamera", "tablet", "laptop"]):
        return 25

    # Spor/sağlık: orta-iyi marj
    if any(w in kw for w in ["yoga", "direnç", "protein", "dambıl", "halter",
                               "pilates", "koşu", "spor"]):
        return 35

    # Ev/mutfak: iyi marj
    if any(w in kw for w in ["fritöz", "blender", "kahve", "ütü", "yastık",
                               "dekor", "led", "mutfak"]):
        return 32

    # Güzellik/kişisel bakım: en iyi marj
    if any(w in kw for w in ["cilt", "saç", "makyaj", "parfüm", "nemlendirici",
                               "serum", "krem", "göz"]):
        return 45

    # Oyuncak/eğlence
    if any(w in kw for w in ["lego", "puzzle", "oyuncak", "çocuk"]):
        return 38

    return 30  # genel default


def _marj_to_score(marj_pct: int) -> int:
    """Marj yüzdesini 0-15 puana çevirir."""
    if marj_pct >= 45: return 15
    if marj_pct >= 40: return 13
    if marj_pct >= 35: return 11
    if marj_pct >= 30: return 9
    if marj_pct >= 25: return 6
    if marj_pct >= 20: return 3
    return 0


def _check_capital(estimated_price_tl: int) -> bool:
    """Sermaye yeterliliği: minimum sipariş maliyeti < CAPITAL_LIMIT_TL mi?"""
    if not estimated_price_tl:
        return True
    min_order_cost = estimated_price_tl * _COST_RATIO * _MIN_MOQ_ESTIMATE
    return min_order_cost <= _CAPITAL_LIMIT_TL


# ═════════════════════════════════════════════════════════════════════════════
# pytrends trending keywords (Faz B başlangıç)
# ═════════════════════════════════════════════════════════════════════════════

def _get_pytrends_trending() -> List[str]:
    """
    pytrends interest_over_time yerine trending_searches + seed ile aday liste üretir.
    Başarısız olursa boş liste döner.
    """
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="tr-TR", tz=180, timeout=(10, 25), retries=1, backoff_factor=0.5)
        df = pytrends.trending_searches(pn="turkey")
        trends = df[0].tolist()[:15]
        logger.info(f"pytrends trending: {len(trends)} TR trend alındı")
        return trends
    except Exception as e:
        logger.warning(f"pytrends trending başarısız (seed kullanılacak): {e}")
        return []


# ═════════════════════════════════════════════════════════════════════════════
# KUYRUĞA EKLEME
# ═════════════════════════════════════════════════════════════════════════════

def _is_duplicate(title: str) -> bool:
    """Son 7 günde aynı başlıkla approval_queue'ya eklenmiş mi kontrol eder."""
    try:
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


def _queue_for_approval(opportunities: List[Dict]) -> int:
    """Eşiği geçen fırsatları approval_queue'ya ekler. Queued count döner."""
    client  = get_client()
    queued  = 0

    for opp in opportunities:
        title   = opp.get("name", "Bilinmeyen ürün")
        scoring = opp.get("scoring", {})
        total   = scoring.get("total", 0)

        # Eşik kontrolü (Claude fallback'ten gelen öğeler için)
        if total < SCORE_THRESHOLD:
            logger.info(f"Atlandı (eşik altı {total}<{SCORE_THRESHOLD}): {title}")
            continue

        if _is_duplicate(title):
            logger.info(f"Atlandı (son 7 günde zaten var): {title}")
            continue

        est_price  = int(opp.get("estimated_price_tl") or 0)
        sermaye_ok = opp.get("sermaye_ok", _check_capital(est_price))

        metadata = {
            "scoring":             scoring,
            "estimated_price_tl":  est_price,
            "sermaye_ok":          sermaye_ok,
            "trendyol_category":   opp.get("trendyol_category", ""),
            "priority":            {},
        }

        client.table("approval_queue").insert({
            "request_type":  "product_approval",
            "agent_source":  AGENT_NAME,
            "title":         title,
            "category":      opp.get("trendyol_category", ""),
            "summary":       opp.get("summary", ""),
            "payload":       opp,
            "metadata":      metadata,
            "status":        "pending",
            "timeout_hours": 48,
        }).execute()

        queued += 1
        logger.info(
            f"approval_queue'ya eklendi ({total} puan): {title} "
            f"| sermaye_ok={sermaye_ok}"
        )

    logger.info(f"{queued}/{len(opportunities)} fırsat kuyruğa eklendi")
    return queued


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
