# Tedarikçi Agent
# Görev: Onaylanan ürünler için tedarikçi bulur, teklif maili gönderir,
#         takip eder ve proformayı approval_queue'ya ekler.
# Çalışma sıklığı: Günde 1 kez (Railway cron) — M3'te aktif

import os
import time
import base64
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import anthropic

from core.supabase_client import get_client
from core.logger import get_logger, log_run
from core.sheets_client import get_gmail_service

logger = get_logger("tedarikci")

AGENT_NAME = "tedarikci"
FOLLOWUP_HOURS = 48


def run():
    start = time.time()
    logger.info("Tedarikçi başladı")

    try:
        processed = 0

        approved_products = _get_approved_products()
        for product in approved_products:
            _process_new_product(product)
            processed += 1

        followup_count = _send_followups()

        duration_ms = int((time.time() - start) * 1000)
        log_run(
            AGENT_NAME,
            status="success",
            run_type="cron",
            items_processed=processed,
            items_success=processed,
            duration_ms=duration_ms,
            metadata={"followups_sent": followup_count},
        )
        logger.info(f"{processed} yeni ürün işlendi, {followup_count} hatırlatma gönderildi ({duration_ms}ms)")

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron",
                duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Tedarikçi hatası: {e}")
        raise


def _get_approved_products() -> list:
    client = get_client()
    result = (
        client.table("products")
        .select("*")
        .eq("status", "approved")
        .execute()
    )
    logger.info(f"{len(result.data)} onaylı ürün bulundu")
    return result.data


def _process_new_product(product: dict):
    product_id = product["id"]
    product_name = product.get("name", "Bilinmeyen ürün")
    logger.info(f"Ürün işleniyor: {product_name} (ID: {product_id})")

    suppliers = _find_suppliers(product)
    if not suppliers:
        logger.warning(f"Tedarikçi bulunamadı: {product_name}")
        return

    sent_count = 0
    for supplier in suppliers[:3]:
        success = _send_inquiry_email(product, supplier)
        if success:
            _log_supplier_contact(product_id, supplier)
            sent_count += 1

    if sent_count > 0:
        # products tablosunda updated_at yok, sadece status güncelle
        get_client().table("products").update(
            {"status": "sourcing"}
        ).eq("id", product_id).execute()
        logger.info(f"{sent_count} tedarikçiye teklif maili gönderildi: {product_name}")


def _find_suppliers(product: dict) -> list:
    product_name = product.get("name", "")
    return [
        {
            "name": "Alibaba Supplier A",
            "email": os.getenv("MOCK_SUPPLIER_EMAIL", ""),
            "platform": "alibaba",
            "url": f"https://www.alibaba.com/trade/search?SearchText={product_name.replace(' ', '+')}",
            "mock": True,
        },
        {
            "name": "1688 Supplier B",
            "email": os.getenv("MOCK_SUPPLIER_EMAIL", ""),
            "platform": "1688",
            "url": "https://www.1688.com",
            "mock": True,
        },
        {
            "name": "Yerel Toptancı C",
            "email": os.getenv("MOCK_SUPPLIER_EMAIL", ""),
            "platform": "local",
            "url": "",
            "mock": True,
        },
    ]


def _generate_inquiry_email(product: dict, supplier: dict) -> str:
    """Claude ile tedarikçiye teklif maili üretir."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    product_name = product.get("name", "")
    category = product.get("category", "")
    target_price = product.get("target_price_tl", "")

    prompt = f"""Write a short professional supplier inquiry email for the following product.

Product: {product_name}
Category: {category}
Target unit price (TRY): {target_price if target_price else "not specified"}
Supplier platform: {supplier.get("platform", "")}

Include: product description, MOQ question, unit/bulk price request, sample availability, delivery time and shipping options.
Keep it concise and friendly. Only write the email body, no subject or explanation."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _send_inquiry_email(product: dict, supplier: dict) -> bool:
    supplier_email = supplier.get("email", "")
    if not supplier_email:
        logger.info(f"Tedarikçi emaili yok, atlandı: {supplier.get('name')}")
        return False

    try:
        product_name = product.get("name", "Ürün")
        email_body = _generate_inquiry_email(product, supplier)

        message = MIMEMultipart()
        message["to"] = supplier_email
        message["subject"] = f"Product Inquiry: {product_name}"
        message.attach(MIMEText(email_body, "plain"))

        service = get_gmail_service()
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()

        logger.info(f"Teklif maili gönderildi: {supplier.get('name')} → {supplier_email}")
        return True

    except Exception as e:
        logger.error(f"Mail gönderilemedi ({supplier.get('name')}): {e}")
        return False


def _log_supplier_contact(product_id: str, supplier: dict):
    try:
        get_client().table("supplier_contacts").insert({
            "product_id": product_id,
            "supplier_name": supplier.get("name"),
            "supplier_email": supplier.get("email"),
            "platform": supplier.get("platform"),
            "status": "inquiry_sent",
            "contacted_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        logger.warning(f"supplier_contacts kaydı oluşturulamadı: {e}")


def _send_followups() -> int:
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=FOLLOWUP_HOURS)).isoformat()
        result = (
            get_client().table("supplier_contacts")
            .select("*")
            .eq("status", "inquiry_sent")
            .lt("contacted_at", cutoff)
            .execute()
        )

        sent = 0
        for contact in result.data:
            if contact.get("supplier_email") and not contact.get("mock"):
                _send_followup_email(contact)
                get_client().table("supplier_contacts").update(
                    {"status": "followup_sent"}
                ).eq("id", contact["id"]).execute()
                sent += 1

        return sent

    except Exception as e:
        logger.warning(f"Hatırlatma kontrolü başarısız: {e}")
        return 0


def _send_followup_email(contact: dict):
    message = MIMEText(
        f"Hi,\n\nJust following up on my inquiry about {contact.get('supplier_name', 'the product')}. "
        f"Could you please share pricing and MOQ information?\n\nThank you!"
    )
    message["to"] = contact["supplier_email"]
    message["subject"] = "Follow-up: Product Inquiry"

    service = get_gmail_service()
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    logger.info(f"Hatırlatma maili gönderildi: {contact.get('supplier_name')}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
