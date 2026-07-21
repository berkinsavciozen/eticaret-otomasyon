# Orkestratör Agent
# Görev: Diğer agentları tetikler, approval_queue'yu yönetir, sistem sağlığını kontrol eder.
# Çalışma sıklığı: Her 30 dakikada bir (Railway cron)

import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from core.supabase_client import get_client
from core.logger import get_logger, log_run
from core.sheets_client import (
    setup_all_sheets,
    mirror_urun_onay,
    mirror_tedarikci_onay,
    mirror_proforma_onay,
    process_urun_onay_approvals,
    process_tedarikci_onay_approvals,
    check_mail_onay_approvals,
    process_proforma_approvals,
    get_mail_onay_status_counts,
    get_proforma_onay_status_counts,
    refresh_dashboard,
    get_gmail_service,
)

logger = get_logger("orkestrator")

AGENT_NAME = "orkestrator"


def run():
    start = time.time()
    logger.info("Orkestratör başladı")

    try:
        sheet_id = os.getenv("SHEETS_APPROVAL_QUEUE_ID")

        # 0. İlk çalışmada sekme başlıklarını oluştur
        if sheet_id:
            try:
                setup_all_sheets(sheet_id)
            except Exception as e:
                logger.warning(f"setup_all_sheets atlandı: {e}")

        # 1. Sheets'teki onayları önce işle → Supabase'e yansısın
        urun_approved, urun_rejected = _process_urun_approvals(sheet_id)
        tedarikci_approved, _ = _process_tedarikci_approvals(sheet_id)
        mail_approved = _process_mail_approvals(sheet_id)
        proforma_approved, _ = _process_proforma_approvals_step(sheet_id)

        # 2. Bekleyen onayları say
        pending_counts = _check_pending_approvals(sheet_id)

        # 3. Sheet 1, 2 ve 4'ü Supabase'den tazele
        _mirror_urun_onay_to_sheets(sheet_id)
        _mirror_tedarikci_onay_to_sheets(sheet_id)
        _mirror_proforma_onay_to_sheets(sheet_id)

        # 4. Dashboard güncelle
        _refresh_dashboard_step(sheet_id, pending_counts)

        # 5. Agent sağlık kontrolü
        _check_agent_health()

        # 6. Bekleyen onay varsa Gmail bildirimi
        total_pending = sum(pending_counts.values())
        if total_pending > 0:
            _send_gmail_reminder(pending_counts)

        duration_ms = int((time.time() - start) * 1000)
        log_run(
            AGENT_NAME,
            status="success",
            run_type="cron",
            duration_ms=duration_ms,
            metadata={
                "urun_approved": urun_approved,
                "urun_rejected": urun_rejected,
                "tedarikci_approved": tedarikci_approved,
                "mail_approved": mail_approved,
                "proforma_approved": proforma_approved,
                "pending": pending_counts,
            },
        )
        logger.info(
            f"Orkestratör tamamlandı ({duration_ms}ms) — "
            f"ürün onay: {urun_approved}, red: {urun_rejected} | "
            f"tedarikçi: {tedarikci_approved} | mail: {mail_approved} | "
            f"proforma: {proforma_approved}"
        )

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log_run(AGENT_NAME, status="failed", run_type="cron",
                duration_ms=duration_ms, error_message=str(e))
        logger.error(f"Orkestratör hatası: {e}")
        raise


# ── Sheet 1: Ürün Onay işleme ─────────────────────────────────────────────────

def _process_urun_approvals(sheet_id: str) -> tuple:
    """
    Sheet 1'deki onay/red kararlarını Supabase'e yansıtır.

    Sheet 1 tek bir yerde karışık request_type'lar taşır (product_approval,
    restock_request, return_manual, ...) çünkü _mirror_urun_onay_to_sheets
    approval_queue'nun tamamını yazıyor. Bu fonksiyon SADECE Sheet'ten okuyup
    her satırı request_type'ına göre doğru handler'a yönlendirir — asıl iş
    mantığı _handle_*_approval_row fonksiyonlarında.
    """
    if not sheet_id:
        return 0, 0

    try:
        approved_list, rejected_list = process_urun_onay_approvals(sheet_id)
    except Exception as e:
        logger.warning(f"Sheet 1 okunamadı: {e}")
        return 0, 0

    client = get_client()
    approved_count = 0
    rejected_count = 0

    for item in approved_list:
        row_id = item["id"]
        try:
            row = _fetch_approval_row(row_id, client)
            if not row:
                continue
            if _dispatch_urun_approval_row(row, item, client, "approved"):
                approved_count += 1
        except Exception as e:
            logger.error(f"Ürün onay hatası {row_id}: {e}")

    for item in rejected_list:
        row_id = item["id"]
        try:
            row = _fetch_approval_row(row_id, client)
            if not row:
                continue
            if _dispatch_urun_approval_row(row, item, client, "rejected"):
                rejected_count += 1
        except Exception as e:
            logger.error(f"Ürün red hatası {row_id}: {e}")

    return approved_count, rejected_count


def _fetch_approval_row(row_id: str, client) -> Optional[dict]:
    result = (
        client.table("approval_queue")
        .select("id, status, title, request_type, payload")
        .eq("id", row_id)
        .execute()
    )
    return result.data[0] if result.data else None


def _dispatch_urun_approval_row(row: dict, item: dict, client, decision: str) -> bool:
    """approval_queue satırını request_type'ına göre doğru handler'a yönlendirir."""
    request_type = row.get("request_type") or "product_approval"
    if request_type == "restock_request":
        return _handle_restock_approval_row(row, item, client, decision)
    if request_type == "return_manual":
        return _handle_return_approval_row(row, item, client, decision)
    return _handle_product_approval_row(row, item, client, decision)


def _handle_product_approval_row(row: dict, item: dict, client, decision: str) -> bool:
    """
    request_type='product_approval' (veya null/eski satırlar için varsayılan).

    GAP-8: Tek yönlü değil — Berkin fikrini değiştirip aksiyonu tersine
    çevirirse, approval_queue.status'u da tersine çevirir:
      - approved (Sheet'te ONAY) + Supabase'de hâlâ 'pending' → 'approved' +
        products satırı oluştur (mevcut davranış).
      - approved (ONAY) + Supabase'de 'rejected' → 'approved'e geri döndür,
        daha önce oluşturulmuş products satırı varsa 'approved'e geri çek,
        yoksa yeniden oluştur.
      - rejected (RED) + Supabase'de hâlâ 'pending' → 'rejected' (mevcut
        davranış, products satırı hiç oluşturulmamıştı).
      - rejected (RED) + Supabase'de 'approved' → 'rejected'e geri döndür,
        oluşturulan products satırı SİLİNMEZ, 'delisted' yapılır (iz kalır).
      - Zaten aynı durumdaysa (approved+ONAY veya rejected+RED) no-op.
    """
    row_id = row["id"]
    current_status = row.get("status")
    title = row.get("title", "Bilinmeyen ürün")

    if decision == "approved":
        if current_status == "approved":
            return False  # zaten onaylı, değişiklik yok

        client.table("approval_queue").update({
            "status": "approved",
            "decision_note": item.get("note", ""),
        }).eq("id", row_id).execute()

        if current_status == "rejected":
            _restore_product_from_approval(row_id, title, client)
            logger.info(f"Ürün onayı geri alındı: {title} (rejected→approved)")
        else:
            _create_product_from_approval(row_id, client)
            logger.info(f"Ürün onaylandı: {row_id}")
        return True

    if current_status == "rejected":
        return False  # zaten red, değişiklik yok

    client.table("approval_queue").update({
        "status": "rejected",
        "decision_note": item.get("note", ""),
    }).eq("id", row_id).execute()

    if current_status == "approved":
        _delist_product_from_approval(title, client)
        logger.info(f"Ürün onayı geri alındı: {title} (approved→rejected)")
    else:
        logger.info(f"Ürün reddedildi: {row_id}")
    return True


def _handle_restock_approval_row(row: dict, item: dict, client, decision: str) -> bool:
    """
    request_type='restock_request' (GAP-12) — siparis.py._check_low_stock()
    tarafından eklenir, payload={'product_id':..., 'stock_count':...}.

    ONAY: YENİ bir products satırı YARATMAZ — aynı product_id'yi
    _requeue_product_for_sourcing ile 'approved'e geri çeker, böylece
    tedarikci.py Faz 1 bir sonraki run'da onu tekrar işleyip yeni tedarikçi
    adayları bulur.
    RED: approval_queue satırı 'rejected' yapılır, ürüne dokunulmaz.
    """
    row_id = row["id"]
    current_status = row.get("status")
    if current_status == decision:
        return False

    client.table("approval_queue").update({
        "status": decision,
        "decision_note": item.get("note", ""),
    }).eq("id", row_id).execute()

    if decision == "approved":
        payload = row.get("payload") or {}
        product_id = payload.get("product_id")
        if product_id:
            _requeue_product_for_sourcing(product_id, client, "kritik stok")
        else:
            logger.warning(f"restock_request satırında product_id yok: {row_id}")
    return True


def _handle_return_approval_row(row: dict, item: dict, client, decision: str) -> bool:
    """
    request_type='return_manual' (GAP-13) — scripts/manual_return.py ile
    Berkin tarafından oluşturulur, payload={'order_id':, 'product_id':,
    'quantity':}.

    ONAY: orders.status→'returned', products.stock_count quantity kadar
    geri artırılır, financials'a negatif bir 'iade' kaydı düşer.
    RED: approval_queue satırı 'rejected' yapılır, başka bir şey yapılmaz.
    """
    row_id = row["id"]
    current_status = row.get("status")
    if current_status == decision:
        return False

    client.table("approval_queue").update({
        "status": decision,
        "decision_note": item.get("note", ""),
    }).eq("id", row_id).execute()

    if decision == "approved":
        payload = row.get("payload") or {}
        _process_return_approval(
            payload.get("order_id"),
            payload.get("product_id"),
            payload.get("quantity", 0),
            client,
        )
    return True


def _process_return_approval(order_id, product_id, quantity, client):
    """
    GAP-13: iade onaylandığında siparişi 'returned' yapar, stoğu geri artırır
    ve financials'a negatif bir iade kaydı düşer. financials alan adları
    agents/finans.py._write_financials ile aynı (week_start, month, category,
    platform, amount_tl, description, source, tax_category) — bu oturumda
    gerçek Supabase şemasına erişilemediği için mevcut, prodüksiyonda
    çalışan finans.py kodu ground truth kabul edildi (bkz. GAP-3).
    """
    if not order_id or not product_id:
        logger.warning(f"return_manual payload eksik: order_id={order_id} product_id={product_id}")
        return
    quantity = quantity or 0

    order_res = client.table("orders").select("id, unit_price_tl").eq("id", order_id).execute()
    if not order_res.data:
        logger.warning(f"İade: sipariş bulunamadı: {order_id}")
        return
    unit_price = order_res.data[0].get("unit_price_tl") or 0

    client.table("orders").update({"status": "returned"}).eq("id", order_id).execute()

    prod_res = client.table("products").select("id, name, stock_count").eq("id", product_id).execute()
    if not prod_res.data:
        logger.warning(f"İade: ürün bulunamadı: {product_id}")
        return
    product = prod_res.data[0]
    new_stock = (product.get("stock_count") or 0) + quantity
    client.table("products").update({"stock_count": new_stock}).eq("id", product_id).execute()

    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).date().isoformat()
    try:
        client.table("financials").insert({
            "week_start": week_start,
            "month": now.strftime("%Y-%m"),
            "category": "iade",
            "platform": "manual",
            "amount_tl": -round(unit_price * quantity, 2),
            "description": f"İade: {product.get('name', '')} (sipariş {order_id})",
            "source": "return_manual",
            "tax_category": "gider",
        }).execute()
    except Exception as e:
        logger.warning(f"İade financials kaydı hatası: {e}")

    logger.info(f"İade işlendi: sipariş {order_id}, ürün {product.get('name')}, +{quantity} stok")


def _create_product_from_approval(approval_id: str, client):
    """Onaylanan approval_queue kaydından products tablosuna kayıt oluşturur."""
    result = client.table("approval_queue").select("*").eq("id", approval_id).execute()
    if not result.data:
        return
    r = result.data[0]
    title = r.get("title", "Bilinmeyen ürün")

    existing = client.table("products").select("id").eq("name", title).execute()
    if existing.data:
        logger.info(f"products'ta zaten var, atlandı: {title}")
        return

    client.table("products").insert({
        "name": title,
        "status": "approved",
        "category": r.get("category", ""),
    }).execute()


def _restore_product_from_approval(approval_id: str, title: str, client):
    """
    GAP-8: RED'den ONAY'a geri dönüldüğünde, daha önce bu başlıkla
    oluşturulmuş bir products satırı varsa (delisted dahil hangi durumda
    olursa olsun) 'approved'e geri döndürür; hiç oluşturulmamışsa
    _create_product_from_approval ile yeniden oluşturur.
    """
    existing = client.table("products").select("id").eq("name", title).execute()
    if existing.data:
        client.table("products").update({"status": "approved"}).eq("id", existing.data[0]["id"]).execute()
        return
    _create_product_from_approval(approval_id, client)


def _delist_product_from_approval(title: str, client):
    """
    GAP-8: ONAY'dan RED'e geri dönüldüğünde, oluşturulmuş products satırını
    SİLMEDEN 'delisted' yapar — mevcut status akışında zaten terminal bir
    durum, burada "iptal edilmiş ürün" anlamında kullanılır, iz kalır.
    """
    existing = client.table("products").select("id").eq("name", title).execute()
    if existing.data:
        client.table("products").update({"status": "delisted"}).eq("id", existing.data[0]["id"]).execute()


# ── Sheet 2: Tedarikçi Onay işleme ───────────────────────────────────────────

def _process_tedarikci_approvals(sheet_id: str) -> tuple:
    """Sheet 2'deki tedarikçi onaylarını işler."""
    if not sheet_id:
        return 0, 0
    try:
        approved_list, rejected_list = process_tedarikci_onay_approvals(sheet_id)
    except Exception as e:
        logger.warning(f"Sheet 2 okunamadı: {e}")
        return 0, 0

    # Şu an tedarikçi approval'ları Supabase'de ayrı tablo yok (M4 kapsam).
    # Sadece sayıyı log'la.
    client = get_client()
    approved_count = 0
    ALREADY_PROCESSED = {"inquiry_sent", "followup_sent", "completed", "sent"}
    for item in approved_list:
        try:
            res = client.table("supplier_contacts").select("status").eq("id", item["id"]).execute()
            if res.data and res.data[0].get("status") in ALREADY_PROCESSED:
                continue  # zaten ilerledi, üzerine yazma
            client.table("supplier_contacts").update({
                "status": "approved",
            }).eq("id", item["id"]).execute()
            approved_count += 1
            logger.info(f"Tedarikçi onaylandı (Supabase): {item.get('id')}")
        except Exception as e:
            logger.warning(f"Tedarikçi onay Supabase hatası: {e}")

    for item in rejected_list:
        try:
            client.table("supplier_contacts").update({
                "status": "rejected",
            }).eq("id", item["id"]).execute()
        except Exception as e:
            logger.warning(f"Tedarikçi red Supabase hatası: {e}")

    return approved_count, len(rejected_list)


# ── Sheet 3: Mail Onay işleme ─────────────────────────────────────────────────

def _process_mail_approvals(sheet_id: str) -> int:
    """Sheet 3'te onaylı (gönderim bekleyen) mail sayısını raporlar.

    Gerçek tedarikçi mail gönderimi artık tedarikci.py → _phase3_send_real_mails()
    tarafından yapılıyor (aynı check_mail_onay_approvals() ile Sheet 3'ü okuyup
    gerçek maili gönderiyor ve durumu "sent" olarak işaretliyor). Burada Sheet 3'e
    ayrıca yazmıyoruz — iki fonksiyonun aynı satırları farklı durumlarla
    güncellemesi (duplike işleme) riskini önlemek için bu fonksiyon salt
    okuma/loglama amaçlıdır.
    """
    if not sheet_id:
        return 0

    try:
        approved_mails, rejected_mails = check_mail_onay_approvals(sheet_id)
    except Exception as e:
        logger.warning(f"Sheet 3 okunamadı: {e}")
        return 0

    if approved_mails:
        logger.info(
            f"{len(approved_mails)} mail onayı gönderim bekliyor "
            f"(gerçek gönderim tedarikci.py Faz 3'te yapılır)"
        )
    if rejected_mails:
        logger.info(
            f"{len(rejected_mails)} mail reddi okundu "
            f"(mail_approvals.onay_durumu='rejected' işaretlendi, ayrı işleme henüz eklenmedi — "
            f"bu, mail taslağının kendisinin reddi; GAP-9 farklı bir akış, bkz. tedarikci.py Faz 6)"
        )

    return len(approved_mails)


# ── Sheet 4: Proforma Onay işleme ────────────────────────────────────────────

def _process_proforma_approvals_step(sheet_id: str) -> tuple:
    """
    Sheet 4'teki proforma onaylarını işler (GAP-2). Onaylanan bir proforma
    bulunduğunda:
    - İlgili proforma_offers (Supabase) kaydı 'approved' / 'rejected' olarak işaretlenir
    - İlgili products kaydının status'u 'sourcing' → 'sourced' yapılır
      (listeleme.py'nin _get_sourced_products() bu geçişi bekliyor)
    - İlgili supplier_contacts kaydının status'u 'completed' yapılır
    - GAP-11: aynı ürüne ait, hâlâ pending olan DİĞER proformalar otomatik
      İPTAL edilir (çoklu-onay engeli).
    Red olduğunda (GAP-11): aynı ürün için başka pending proforma veya aktif
    (rejected olmayan) tedarikçi kontağı kalmadıysa, ürün otomatik olarak
    yeniden tedarikçi araştırmasına düşer.
    """
    if not sheet_id:
        return 0, 0
    try:
        approved_list, rejected_list = process_proforma_approvals(sheet_id)
    except Exception as e:
        logger.warning(f"Sheet 4 okunamadı: {e}")
        return 0, 0

    client = get_client()
    now_iso = datetime.now(timezone.utc).isoformat()
    approved_count = 0

    for item in approved_list:
        offer_id = item["id"]
        try:
            res = client.table("proforma_offers").select("*").eq("id", offer_id).execute()
            if not res.data:
                continue
            offer = res.data[0]
            if offer.get("status") != "pending":
                continue  # zaten işlendi

            update_fields = {"status": "approved", "reviewed_at": now_iso}
            if item.get("note"):
                update_fields["note"] = item["note"]
            client.table("proforma_offers").update(update_fields).eq("id", offer_id).execute()

            client.table("products").update({"status": "sourced"}).eq(
                "id", offer["product_id"]
            ).eq("status", "sourcing").execute()

            if offer.get("supplier_contact_id"):
                client.table("supplier_contacts").update({"status": "completed"}).eq(
                    "id", offer["supplier_contact_id"]
                ).execute()

            _cancel_sibling_pending_proformas(offer["product_id"], offer_id, client)
            _check_and_requeue_if_exhausted(offer["product_id"], client)

            approved_count += 1
            logger.info(f"Proforma onaylandı: {offer_id} → ürün sourced, tedarikçi completed")
        except Exception as e:
            logger.error(f"Proforma onay işleme hatası {offer_id}: {e}")

    for item in rejected_list:
        offer_id = item["id"]
        try:
            res = client.table("proforma_offers").select("product_id").eq("id", offer_id).execute()
            product_id = res.data[0].get("product_id") if res.data else None

            update_fields = {"status": "rejected", "reviewed_at": now_iso}
            if item.get("note"):
                update_fields["note"] = item["note"]
            client.table("proforma_offers").update(update_fields).eq("id", offer_id).execute()

            _check_and_requeue_if_exhausted(product_id, client)
        except Exception as e:
            logger.warning(f"Proforma red işleme hatası {offer_id}: {e}")

    if approved_count:
        logger.info(f"{approved_count} proforma onaylandı (sourced geçişi tetiklendi)")
    return approved_count, len(rejected_list)


def _cancel_sibling_pending_proformas(product_id, approved_offer_id: str, client):
    """
    GAP-11: bir proforma onaylandığında, aynı ürüne ait hâlâ pending olan
    diğer proformaları otomatik 'rejected' yapar. Sheet4 mirror'ı bir sonraki
    run'da bunları İPTAL gösterir (map_sistem_durum zaten 'rejected'→İPTAL
    çeviriyor, GAP-7 sözlüğü).
    """
    if not product_id:
        return
    try:
        siblings = (
            client.table("proforma_offers")
            .select("id")
            .eq("product_id", product_id)
            .eq("status", "pending")
            .neq("id", approved_offer_id)
            .execute()
        )
        for sibling in siblings.data:
            client.table("proforma_offers").update({
                "status": "rejected",
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "note": "Otomatik iptal: aynı ürün için başka bir proforma onaylandı",
            }).eq("id", sibling["id"]).execute()
        if siblings.data:
            logger.info(f"{len(siblings.data)} proforma otomatik iptal edildi (ürün {product_id})")
    except Exception as e:
        logger.warning(f"Proforma cascade iptal hatası (ürün {product_id}): {e}")


def _check_and_requeue_if_exhausted(product_id, client):
    """
    GAP-11: bir ürün için tüm yollar tükendiyse (hiç pending proforma yok VE
    'rejected' olmayan aktif bir supplier_contacts kaydı da yok) ürünü
    _requeue_product_for_sourcing ile yeniden tedarikçi araştırmasına sokar.
    Hem onay hem red döngüsünden çağrılır — onay durumunda tükenme oluşması
    ihtimal dışı (az önce completed edilen kontak aktif sayılır) ama
    fonksiyon her iki akışta da tutarlı davransın diye buradan da çağrılıyor.
    """
    if not product_id:
        return
    try:
        pending = (
            client.table("proforma_offers")
            .select("id")
            .eq("product_id", product_id)
            .eq("status", "pending")
            .execute()
        )
        if pending.data:
            return

        active_contacts = (
            client.table("supplier_contacts")
            .select("id")
            .eq("product_id", product_id)
            .neq("status", "rejected")
            .execute()
        )
        if active_contacts.data:
            return

        _requeue_product_for_sourcing(product_id, client, "tüm proformalar reddedildi")
    except Exception as e:
        logger.warning(f"Tükenme kontrolü hatası (ürün {product_id}): {e}")


def _requeue_product_for_sourcing(product_id, client, reason: str):
    """
    products.status'u 'approved'e geri çeker — tedarikci.py'nin
    _phase1_supplier_research() bir sonraki run'da bunu tekrar işleyip yeni
    tedarikçi adayları bulur (GAP-11/GAP-12 paylaşılan helper; bunun
    çalışması için _phase1_supplier_research()'teki "zaten araştırıldı mı"
    kontrolünün sadece aktif/rejected-olmayan kontakları sayması gerekir).
    """
    client.table("products").update({"status": "approved"}).eq("id", product_id).execute()
    logger.info(f"Ürün yeniden tedarikçi araştırmasına alındı ({reason}): {product_id}")


# ── Sheet 1 mirror ────────────────────────────────────────────────────────────

def _mirror_urun_onay_to_sheets(sheet_id: str):
    """approval_queue tablosunu Sheet 1'e yazar (tüm statüler)."""
    if not sheet_id:
        logger.info("SHEETS_APPROVAL_QUEUE_ID tanımlı değil, mirror atlandı")
        return

    try:
        client = get_client()
        rows = (
            client.table("approval_queue")
            .select("*")
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        count = mirror_urun_onay(sheet_id, rows.data)
        logger.info(f"Sheet 1 mirror: {count} kayıt yazıldı")
    except Exception as e:
        logger.warning(f"Sheet 1 mirror atlandı (Sheets erişim hatası): {e}")


# ── Sheet 2 mirror ────────────────────────────────────────────────────────────

def _mirror_tedarikci_onay_to_sheets(sheet_id: str):
    """supplier_contacts tablosunu Sheet 2'ye yazar (products join ile)."""
    if not sheet_id:
        return
    client = get_client()
    try:
        sc_res = client.table("supplier_contacts").select("*").order("contacted_at", desc=False).execute()
        prod_res = client.table("products").select("id, name").execute()
        prod_map = {p["id"]: p["name"] for p in prod_res.data}
        rows = []
        for sc in sc_res.data:
            sc["product_name"] = prod_map.get(sc.get("product_id"), "")
            rows.append(sc)
        count = mirror_tedarikci_onay(sheet_id, rows)
        logger.info(f"Sheet 2 mirror: {count} tedarikçi yazıldı")
    except Exception as e:
        logger.warning(f"Sheet 2 mirror hatası: {e}")


# ── Sheet 4 mirror (GAP-7: K kolonu artık periyodik olarak sistem durumuna
#    çevriliyor — Sheet1/2 ile aynı dual-purpose pattern) ─────────────────────

def _mirror_proforma_onay_to_sheets(sheet_id: str):
    """proforma_offers tablosunu Sheet 4'e yazar (products + supplier_contacts join ile)."""
    if not sheet_id:
        return
    client = get_client()
    try:
        po_res = client.table("proforma_offers").select("*").order("created_at", desc=False).execute()
        prod_res = client.table("products").select("id, name").execute()
        prod_map = {p["id"]: p["name"] for p in prod_res.data}
        sc_res = client.table("supplier_contacts").select("id, supplier_name").execute()
        sc_map = {s["id"]: s["supplier_name"] for s in sc_res.data}
        rows = []
        for po in po_res.data:
            po["product_title"] = prod_map.get(po.get("product_id"), "")
            po["supplier_name"] = sc_map.get(po.get("supplier_contact_id"), "")
            rows.append(po)
        count = mirror_proforma_onay(sheet_id, rows)
        logger.info(f"Sheet 4 mirror: {count} proforma yazıldı")
    except Exception as e:
        logger.warning(f"Sheet 4 mirror hatası: {e}")


# ── Dashboard ─────────────────────────────────────────────────────────────────

def _refresh_dashboard_step(sheet_id: str, pending_counts: dict):
    """Sheet 5 Dashboard'u günceller."""
    if not sheet_id:
        return

    client = get_client()
    try:
        # Ürün pipeline sayıları
        all_q = client.table("approval_queue").select("status").execute()
        urun_pending  = sum(1 for r in all_q.data if r["status"] == "pending")
        urun_approved = sum(1 for r in all_q.data if r["status"] == "approved")
        urun_rejected = sum(1 for r in all_q.data if r["status"] == "rejected")

        # Tedarikçi sayıları
        all_sc = client.table("supplier_contacts").select("status, supplier_name, product_id").execute()
        tedarikci_pending  = sum(1 for r in all_sc.data if r["status"] in ("research_found",))
        tedarikci_approved = sum(1 for r in all_sc.data if r["status"] in ("approved", "inquiry_sent", "followup_sent"))

        # Ürün × Tedarikçi matrisi
        products_res = client.table("products").select("id, name").execute()
        prod_map = {p["id"]: p["name"] for p in products_res.data}
        matrix = []
        for sc in all_sc.data:
            matrix.append({
                "product":  prod_map.get(sc.get("product_id"), sc.get("product_id", "")),
                "supplier": sc.get("supplier_name", ""),
                "status":   sc.get("status", ""),
                "score":    "",
            })

        mail_pending, mail_approved_ct = get_mail_onay_status_counts(sheet_id)
        proforma_pending, proforma_approved_ct = get_proforma_onay_status_counts(sheet_id)

        pipeline_data = {
            "urun_pending":       urun_pending,
            "urun_approved":      urun_approved,
            "urun_rejected":      urun_rejected,
            "tedarikci_pending":  tedarikci_pending,
            "tedarikci_approved": tedarikci_approved,
            "mail_pending":       mail_pending,
            "mail_approved":      mail_approved_ct,
            "proforma_pending":   proforma_pending,
            "proforma_approved":  proforma_approved_ct,
            "last_updated":       datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "product_supplier_matrix": matrix,
        }
        refresh_dashboard(sheet_id, pipeline_data)
        logger.info("Dashboard güncellendi")
    except Exception as e:
        logger.warning(f"Dashboard güncelleme hatası: {e}")


# ── Pending approval sayıları ─────────────────────────────────────────────────

def _check_pending_approvals(sheet_id: str = None) -> dict:
    """
    Bekleyen onay sayılarını döner (GAP-6). Gmail hatırlatma maili bu sayıları
    kullanır — dashboard'daki pending sayaçlarından (BUG-3, _refresh_dashboard_step)
    AYRI bir fonksiyon, o yüzden burada da gerçek veriden okunması gerekiyor.
    """
    client = get_client()
    urun_pending = (
        client.table("approval_queue")
        .select("id")
        .eq("status", "pending")
        .execute()
    )
    urun_count = len(urun_pending.data)

    tedarikci_count = 0
    try:
        tedarikci_pending = (
            client.table("supplier_contacts")
            .select("id")
            .eq("status", "research_found")
            .execute()
        )
        tedarikci_count = len(tedarikci_pending.data)
    except Exception as e:
        logger.warning(f"Tedarikçi bekleyen sayısı alınamadı: {e}")

    mail_count = proforma_count = 0
    if sheet_id:
        try:
            mail_count, _ = get_mail_onay_status_counts(sheet_id)
        except Exception as e:
            logger.warning(f"Mail bekleyen sayısı alınamadı: {e}")
        try:
            proforma_count, _ = get_proforma_onay_status_counts(sheet_id)
        except Exception as e:
            logger.warning(f"Proforma bekleyen sayısı alınamadı: {e}")

    counts = {
        "urun": urun_count,
        "tedarikci": tedarikci_count,
        "mail": mail_count,
        "proforma": proforma_count,
    }
    total = sum(counts.values())
    if total > 0:
        logger.info(f"Bekleyen onaylar: {counts}")
    else:
        logger.info("Bekleyen onay yok")
    return counts


def _check_agent_health():
    client = get_client()
    recent = (
        client.table("agent_logs")
        .select("agent_name, status, started_at")
        .order("started_at", desc=True)
        .limit(20)
        .execute()
    )
    logger.info(f"Son {len(recent.data)} log kaydı kontrol edildi")


# ── Gmail bildirimi ───────────────────────────────────────────────────────────

def _send_gmail_reminder(pending_counts: dict):
    """Bekleyen onaylar için Gmail bildirimi gönderir."""
    notification_email = os.getenv("NOTIFICATION_EMAIL")
    if not notification_email:
        logger.info("NOTIFICATION_EMAIL tanımlı değil, mail atlandı")
        return

    try:
        import base64
        from email.mime.text import MIMEText

        sheet_id  = os.getenv("SHEETS_APPROVAL_QUEUE_ID", "")
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}" if sheet_id else ""

        lines = []
        if pending_counts.get("urun"):
            lines.append(f"• Ürün Onay: {pending_counts['urun']} bekleyen")
        if pending_counts.get("tedarikci"):
            lines.append(f"• Tedarikçi Onay: {pending_counts['tedarikci']} bekleyen")
        if pending_counts.get("mail"):
            lines.append(f"• Mail Onay: {pending_counts['mail']} bekleyen")
        if pending_counts.get("proforma"):
            lines.append(f"• Proforma Onay: {pending_counts['proforma']} bekleyen")

        total = sum(pending_counts.values())
        body = f"""Merhaba,

{total} adet onay bekleyen kayıt var:

{chr(10).join(lines)}

Onay paneline git:
{sheet_url}

— E-Ticaret Otomasyon Sistemi
"""
        message = MIMEText(body)
        message["to"] = notification_email
        message["subject"] = f"[E-Ticaret] {total} onay bekliyor"

        service = get_gmail_service()
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        logger.info(f"Gmail bildirimi gönderildi: {notification_email}")

    except Exception as e:
        logger.error(f"Gmail bildirimi gönderilemedi: {e}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run()
