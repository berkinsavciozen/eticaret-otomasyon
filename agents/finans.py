# Finans Agent
# Görev: Platform tahsilatlarını çeker, banka hareketleriyle birleştirir,
#        P&L raporu üretir, KDV kategorisasyonu yapar.
# Çalışma sıklığı: Haftada 1 kez (Pazartesi) — M4'te gerçek API bağlanacak

import os
import time
from datetime import datetime, timezone, timedelta

from core.supabase_client import get_client
from core.logger import get_logger, log_run
from core.sheets_client import read_sheet, clear_and_write_sheet

logger = get_logger("finans")

AGENT_NAME = "finans"

BANK_SHEET_HEADER = ["Tarih", "Açıklama", "Tutar (TL)", "Kategori", "Not"]


def run():
    start = time.time()
    logger.info("Finans başladı")

    try:
        platform_revenue = _fetch_platform_revenue()
        bank_entries = _read_bank_entries()
        _write_financials(platform_revenue, bank_entries)
        pl_summary = _generate_pl_summary(platform_revenue, bank_entries)
        logger.info(f"P&L özeti: {pl_summary}")

        duration_ms = int((time.time() - start) * 1000)
        log_run(
            AGENT_NAME,
            status="success",
            run_type="cron",
            items_processed=len(platform_revenue) + len(bank_entries),
            duration_ms=duration_ms,
            metadata={"pl_summary": pl_summary},
        )
        logger.info(f"Finans tamamlandı ({duration_ms}ms)")

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron",
                duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Finans hatası: {e}")
        raise


def _fetch_platform_revenue() -> list:
    if os.getenv("MOCK_FINANCIALS", "false").lower() == "true":
        logger.info("MOCK mod: sahte platform geliri üretiliyor")
        return [
            {"platform": "shopify", "amount_tl": 921.5, "category": "platform_revenue",
             "description": "Shopify haftalık net tahsilat", "source": "shopify"},
            {"platform": "trendyol", "amount_tl": 1068.0, "category": "platform_revenue",
             "description": "Trendyol haftalık net tahsilat (komisyon düşülmüş)", "source": "trendyol"},
        ]

    revenues = []
    revenues.extend(_fetch_shopify_payouts())
    revenues.extend(_fetch_trendyol_payments())
    logger.info(f"{len(revenues)} platform gelir kaydı alındı")
    return revenues


def _fetch_shopify_payouts() -> list:
    # TODO M4: GET /admin/api/2024-01/payouts.json
    logger.info("Shopify Payments API henüz bağlı değil (M4)")
    return []


def _fetch_trendyol_payments() -> list:
    # TODO M4: GET /sapigw/suppliers/{supplierId}/finance/settlements
    # ⚠️ 14 günlük ödeme döngüsü
    logger.info("Trendyol Finance API henüz bağlı değil (M4)")
    return []


def _read_bank_entries() -> list:
    sheet_id = os.getenv("SHEETS_BANK_ENTRY_ID")
    if not sheet_id:
        logger.info("SHEETS_BANK_ENTRY_ID tanımlı değil, banka girişleri atlandı")
        return []

    try:
        rows = read_sheet(sheet_id, "Banka!A1:E200")
        if len(rows) <= 1:
            return []

        entries = []
        for row in rows[1:]:
            if len(row) < 3:
                continue
            try:
                amount = float(str(row[2]).replace(",", ".").replace(" ", ""))
            except ValueError:
                continue
            entries.append({
                "date": row[0] if len(row) > 0 else "",
                "description": row[1] if len(row) > 1 else "",
                "amount_tl": amount,
                "category": row[3] if len(row) > 3 else "Diğer",
                "note": row[4] if len(row) > 4 else "",
            })
        logger.info(f"{len(entries)} manuel banka girişi okundu")
        return entries
    except Exception as e:
        logger.warning(f"Banka girişleri okunamadı: {e}")
        return []


def _write_financials(platform_revenue: list, bank_entries: list):
    """Gelir/gider kalemlerini financials tablosuna yazar. Gerçek şema kullanılır."""
    client = get_client()
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).date().isoformat()
    month = now.strftime("%Y-%m")

    for rev in platform_revenue:
        try:
            client.table("financials").insert({
                "week_start": week_start,
                "month": month,
                "category": rev.get("category", "platform_revenue"),
                "platform": rev.get("platform", ""),
                "amount_tl": rev.get("amount_tl", 0),
                "description": rev.get("description", ""),
                "source": rev.get("source", "api"),
                "tax_category": "gelir",
            }).execute()
        except Exception as e:
            logger.warning(f"financials platform geliri yazma hatası: {e}")

    for entry in bank_entries:
        try:
            client.table("financials").insert({
                "week_start": week_start,
                "month": month,
                "category": entry.get("category", "Diğer"),
                "platform": "manual",
                "amount_tl": entry.get("amount_tl", 0),
                "description": entry.get("description", ""),
                "source": "bank_manual",
                "tax_category": _map_tax_category(entry.get("category", "")),
            }).execute()
        except Exception as e:
            logger.warning(f"Banka girişi yazma hatası: {e}")


def _map_tax_category(category: str) -> str:
    mapping = {
        "Gelir": "gelir",
        "COGS": "maliyet",
        "Kargo": "gider",
        "Reklam": "gider",
        "Sabit Gider": "gider",
        "Komisyon": "gider",
        "KDV": "kdv",
    }
    return mapping.get(category, "diger")


def _generate_pl_summary(platform_revenue: list, bank_entries: list) -> dict:
    total_revenue = sum(r.get("amount_tl", 0) for r in platform_revenue)
    total_expenses = sum(
        abs(e.get("amount_tl", 0))
        for e in bank_entries
        if e.get("category") in ("COGS", "Kargo", "Reklam", "Sabit Gider", "Komisyon")
    )
    gross_profit = total_revenue - total_expenses
    return {
        "total_revenue_tl": round(total_revenue, 2),
        "total_expenses_tl": round(total_expenses, 2),
        "gross_profit_tl": round(gross_profit, 2),
        "margin_pct": round((gross_profit / total_revenue * 100) if total_revenue > 0 else 0, 1),
    }


def setup_bank_sheet():
    """Google Sheets'te banka giriş şablonunu oluşturur. Tek seferlik."""
    sheet_id = os.getenv("SHEETS_BANK_ENTRY_ID")
    if not sheet_id:
        logger.error("SHEETS_BANK_ENTRY_ID tanımlı değil")
        return
    example = ["23.06.2026", "Trendyol kargo gideri", "-150", "Kargo", "Haziran haftası 1"]
    clear_and_write_sheet(sheet_id, "Banka!A1", [BANK_SHEET_HEADER, example])
    logger.info("Banka giriş şablonu oluşturuldu")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "setup_bank_sheet":
        setup_bank_sheet()
    else:
        run()
