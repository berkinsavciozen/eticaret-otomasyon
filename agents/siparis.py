# Sipariş Agent
# Görev: Shopify ve Trendyol'dan yeni siparişleri çeker, kargo etiketleri oluşturur,
#        stok günceller, iade takibi yapar.
# Çalışma sıklığı: Her 30 dakikada bir — M4'te gerçek API bağlanacak

import os
import time
from datetime import datetime, timezone

from core.supabase_client import get_client
from core.logger import get_logger, log_run

logger = get_logger("siparis")

AGENT_NAME = "siparis"
CRITICAL_STOCK_THRESHOLD = 3


def run():
    start = time.time()
    logger.info("Sipariş başladı")

    try:
        new_orders = _fetch_new_orders()
        processed = 0

        for order in new_orders:
            _process_order(order)
            processed += 1

        low_stock = _check_low_stock()

        duration_ms = int((time.time() - start) * 1000)
        log_run(
            AGENT_NAME,
            status="success",
            run_type="cron",
            items_processed=processed,
            items_success=processed,
            duration_ms=duration_ms,
            metadata={"low_stock_alerts": low_stock},
        )
        logger.info(f"{processed} sipariş işlendi, {low_stock} düşük stok uyarısı ({duration_ms}ms)")

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron",
                duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Sipariş hatası: {e}")
        raise


def _fetch_new_orders() -> list:
    if os.getenv("MOCK_ORDERS", "false").lower() == "true":
        logger.info("MOCK mod: test siparişi üretiliyor")
        # listed ürünü bul
        result = get_client().table("products").select("id, name, target_price_tl").eq("status", "listed").limit(1).execute()
        if not result.data:
            logger.warning("Listed ürün bulunamadı, mock sipariş atlandı")
            return []
        product = result.data[0]
        return [{
            "platform": "shopify",
            "platform_order_id": f"MOCK-{int(time.time())}",
            "product_id": product["id"],
            "product_name": product["name"],
            "quantity": 1,
            "unit_price_tl": product.get("target_price_tl") or 950.0,
            "total_tl": product.get("target_price_tl") or 950.0,
            "mock": True,
        }]

    orders = []
    orders.extend(_fetch_shopify_orders())
    orders.extend(_fetch_trendyol_orders())
    logger.info(f"{len(orders)} yeni sipariş bulundu")
    return orders


def _fetch_shopify_orders() -> list:
    # TODO M4: GET /admin/api/2024-01/orders.json?status=open
    logger.info("Shopify API henüz bağlı değil (M4)")
    return []


def _fetch_trendyol_orders() -> list:
    # TODO M4: GET /sapigw/suppliers/{supplierId}/orders
    # ⚠️ V1 API 10 Ağustos 2026'da kapanıyor — sadece V3 kullan
    logger.info("Trendyol API henüz bağlı değil (M4)")
    return []


def _process_order(order: dict):
    """Siparişi kaydeder, kargo etiketi oluşturur, stok günceller."""
    try:
        result = get_client().table("orders").insert({
            "platform": order.get("platform", ""),
            "platform_order_id": order.get("platform_order_id", ""),
            "product_id": order.get("product_id"),
            "quantity": order.get("quantity", 1),
            "unit_price_tl": order.get("unit_price_tl", 0),
            "total_tl": order.get("total_tl", 0),
            "status": "processing",
            "ordered_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        logger.info(f"Sipariş kaydedildi: {order.get('platform_order_id')}")
    except Exception as e:
        logger.warning(f"orders tablosuna yazılamadı: {e}")
        return

    # Kargo etiketi
    tracking_number = _create_shipping_label(order)
    if tracking_number and result.data:
        try:
            get_client().table("orders").update({
                "tracking_number": tracking_number,
                "status": "shipped",
                "shipped_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", result.data[0]["id"]).execute()
        except Exception as e:
            logger.warning(f"Kargo güncelleme hatası: {e}")

    # Stok düşür
    if order.get("product_id"):
        _decrement_stock(order["product_id"], order.get("quantity", 1))


def _create_shipping_label(order: dict) -> str:
    if order.get("mock") or os.getenv("MOCK_ORDERS", "false").lower() == "true":
        tracking = f"MOCK1234567{str(order.get('platform_order_id', ''))[-4:]}"
        logger.info(f"MOCK kargo etiketi: {tracking}")
        return tracking
    # TODO M4: Yurtiçi Kargo API
    logger.info("Kargo API henüz bağlı değil (M4)")
    return ""


def _decrement_stock(product_id: str, quantity: int):
    try:
        result = get_client().table("products").select("id, stock_count").eq("id", product_id).execute()
        if not result.data:
            return
        current_stock = result.data[0].get("stock_count") or 0
        new_stock = max(0, current_stock - quantity)
        get_client().table("products").update({"stock_count": new_stock}).eq("id", product_id).execute()
        logger.info(f"Stok güncellendi: {product_id} → {new_stock}")
    except Exception as e:
        logger.warning(f"Stok güncellenemedi: {e}")


def _check_low_stock() -> int:
    try:
        result = (
            get_client().table("products")
            .select("id, name, stock_count")
            .eq("status", "listed")
            .lte("stock_count", CRITICAL_STOCK_THRESHOLD)
            .execute()
        )
        for product in result.data:
            existing = (
                get_client().table("approval_queue")
                .select("id")
                .eq("status", "pending")
                .eq("request_type", "restock_request")
                .like("title", f"%{product['name']}%")
                .execute()
            )
            if existing.data:
                continue
            get_client().table("approval_queue").insert({
                "request_type": "restock_request",
                "agent_source": AGENT_NAME,
                "title": f"Kritik stok: {product['name']}",
                "summary": f"Stok {product.get('stock_count', 0)} adede düştü. Yeniden sipariş gerekiyor.",
                "payload": {"product_id": str(product["id"]), "stock_count": product.get("stock_count", 0)},
                "status": "pending",
                "timeout_hours": 24,
            }).execute()
            logger.warning(f"Kritik stok uyarısı: {product['name']} ({product.get('stock_count', 0)} adet)")
        return len(result.data)
    except Exception as e:
        logger.warning(f"Stok kontrolü başarısız: {e}")
        return 0


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
