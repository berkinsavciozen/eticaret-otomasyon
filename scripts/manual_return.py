"""
GAP-13: İade — minimal manuel giriş noktası.

Gerçek webhook/API entegrasyonu olmadan otomatik iade algılama mümkün değil
(M6'da gerçek Shopify/Trendyol API'leriyle gelecek). Şimdilik Berkin bir iade
fark ettiğinde bu script'i çalıştırarak approval_queue'ya bir
'return_manual' talebi düşürür — diğer tüm onay akışlarıyla aynı prensip:
orkestrator._handle_return_approval_row() Berkin Sheet 1'de ONAY yazana
kadar hiçbir şeyi (stok, sipariş durumu, financials) değiştirmez.

Kullanım:
    python3 scripts/manual_return.py --order-id <uuid> --product-id <uuid> --quantity <int>
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from core.supabase_client import get_client  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Manuel iade talebi oluştur (GAP-13)")
    parser.add_argument("--order-id", required=True, help="orders.id (uuid)")
    parser.add_argument("--product-id", required=True, help="products.id (uuid)")
    parser.add_argument("--quantity", required=True, type=int, help="İade edilen adet")
    args = parser.parse_args()

    if args.quantity <= 0:
        print("Hata: --quantity 0'dan büyük olmalı")
        sys.exit(1)

    client = get_client()

    order_res = client.table("orders").select("id, platform_order_id").eq("id", args.order_id).execute()
    if not order_res.data:
        print(f"Hata: sipariş bulunamadı: {args.order_id}")
        sys.exit(1)

    product_res = client.table("products").select("id, name").eq("id", args.product_id).execute()
    if not product_res.data:
        print(f"Hata: ürün bulunamadı: {args.product_id}")
        sys.exit(1)
    product_name = product_res.data[0].get("name", "Bilinmeyen ürün")

    client.table("approval_queue").insert({
        "request_type": "return_manual",
        "agent_source": "manual_return_script",
        "title": f"İade: {product_name} (sipariş {args.order_id})",
        "summary": f"{args.quantity} adet iade talebi manuel olarak girildi.",
        "payload": {
            "order_id": args.order_id,
            "product_id": args.product_id,
            "quantity": args.quantity,
        },
        "status": "pending",
    }).execute()

    print(f"İade talebi oluşturuldu: {product_name} — {args.quantity} adet (sipariş {args.order_id})")
    print("Onay için Sheet 1'e (Ürün Onay) düşecek — Berkin ONAY/RED yazınca bir sonraki orkestratör cron'unda işlenir.")


if __name__ == "__main__":
    main()
