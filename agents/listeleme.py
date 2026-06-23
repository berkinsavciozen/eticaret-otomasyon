# Listeleme Agent
# Görev: Temin edilen ürünleri Shopify ve Trendyol'a listeler.
# Çalışma sıklığı: Günde 1 kez — M4'te gerçek API bağlanacak

import os
import time
from datetime import datetime, timezone

import anthropic

from core.supabase_client import get_client
from core.logger import get_logger, log_run

logger = get_logger("listeleme")

AGENT_NAME = "listeleme"


def run():
    start = time.time()
    logger.info("Listeleme başladı")

    try:
        sourced_products = _get_sourced_products()
        processed = 0

        for product in sourced_products:
            _list_product(product)
            processed += 1

        duration_ms = int((time.time() - start) * 1000)
        log_run(
            AGENT_NAME,
            status="success",
            run_type="cron",
            items_processed=processed,
            items_success=processed,
            duration_ms=duration_ms,
        )
        logger.info(f"{processed} ürün listelendi ({duration_ms}ms)")

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron",
                duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Listeleme hatası: {e}")
        raise


def _get_sourced_products() -> list:
    """products tablosunda status=sourced olan kayıtları çeker."""
    result = get_client().table("products").select("*").eq("status", "sourced").execute()
    logger.info(f"{len(result.data)} temin edilmiş ürün bulundu")
    return result.data


def _list_product(product: dict):
    product_id = product["id"]
    product_name = product.get("name", "Bilinmeyen ürün")
    logger.info(f"Listeleniyor: {product_name}")

    # SEO içerik üret
    content = _generate_listing_content(product)

    # Shopify'a listele (mock veya gerçek)
    shopify_id = _list_on_shopify(product, content)

    # Trendyol'a listele (mock veya gerçek)
    trendyol_barcode = _list_on_trendyol(product, content)

    # products tablosunu güncelle
    update_data = {"status": "listed", "listed_at": datetime.now(timezone.utc).isoformat()}
    if shopify_id:
        update_data["shopify_product_id"] = shopify_id
    if trendyol_barcode:
        update_data["trendyol_barcode"] = trendyol_barcode

    get_client().table("products").update(update_data).eq("id", product_id).execute()
    logger.info(f"Listelendi: {product_name} — Shopify: {shopify_id}, Trendyol: {trendyol_barcode}")


def _generate_listing_content(product: dict) -> dict:
    """Claude ile SEO başlık, açıklama ve etiketler üretir."""
    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        prompt = f"""Türk e-ticaret platformu için ürün listeleme içeriği yaz.

Ürün: {product.get("name", "")}
Kategori: {product.get("category", "")}
Fiyat (TL): {product.get("target_price_tl", "")}

Şunları üret (JSON formatında):
- title: SEO dostu başlık (max 100 karakter)
- description: Ürün açıklaması (150-200 kelime, Türkçe)
- tags: Etiket listesi (5-8 etiket)
- shopify_collection: Shopify koleksiyon adı önerisi

Sadece JSON döndür, başka açıklama ekleme."""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        text = response.content[0].text.strip()
        # JSON bloğunu temizle
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        logger.warning(f"İçerik üretilemedi, varsayılan kullanılıyor: {e}")
        return {
            "title": product.get("name", ""),
            "description": f"{product.get('name', '')} — Kaliteli ürün.",
            "tags": [product.get("category", "genel")],
            "shopify_collection": product.get("category", "Genel"),
        }


def _list_on_shopify(product: dict, content: dict) -> str:
    """Shopify Admin API ile ürün oluşturur. Mock modda simüle eder."""
    if os.getenv("MOCK_LISTING", "false").lower() == "true":
        mock_id = f"mock_shopify_{product['id'][:8]}"
        logger.info(f"MOCK Shopify listing: {mock_id}")
        return mock_id

    # TODO M4: Gerçek Shopify Admin API entegrasyonu
    # shopify_url = os.environ["SHOPIFY_STORE_URL"]
    # api_key = os.environ["SHOPIFY_API_KEY"]
    # ...
    logger.info("Shopify API henüz bağlı değil (M4)")
    return ""


def _list_on_trendyol(product: dict, content: dict) -> str:
    """Trendyol Seller API V3 ile ürün oluşturur. Mock modda simüle eder."""
    if os.getenv("MOCK_LISTING", "false").lower() == "true":
        mock_barcode = f"MOCK{product['id'][:10].upper().replace('-', '')}"
        logger.info(f"MOCK Trendyol listing: {mock_barcode}")
        return mock_barcode

    # TODO M4: Trendyol Seller API V3 entegrasyonu
    # supplier_id = os.environ["TRENDYOL_SUPPLIER_ID"]
    # ⚠️ V1 API 10 Ağustos 2026'da kapanıyor — sadece V3 kullan
    logger.info("Trendyol API henüz bağlı değil (M4)")
    return ""


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
