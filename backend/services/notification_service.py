"""Notification service — pembuatan notifikasi + generator dari event REAL.

Tidak ada data mock: notifikasi dihitung dari kondisi nyata di
`inventory_balances` (stok menipis) dan `sales_orders` (reservasi mendekati
kedaluwarsa 3 hari). Dedupe berbasis `ref` agar tidak menumpuk duplikat.
"""
from typing import Any, Dict, Optional
from datetime import datetime, timezone, timedelta
from db import db
from core_utils import new_id, now_iso, safe_doc, rupiah
from services.inventory_service import product_summary

LOW_STOCK_THRESHOLD = 100.0  # meter — ambang batas default stok menipis


async def _has_unread(notif_type: str, ref: str) -> bool:
    return bool(await db.notifications.find_one(
        {"type": notif_type, "ref": ref, "read": False}, {"_id": 1}
    ))


async def create_notification(
    *, notif_type: str, title: str, body: str, severity: str = "info",
    link: str = "", entity_id: Optional[str] = None, recipient_role: str = "all",
    recipient_user: Optional[str] = None, ref: str = "", dedupe: bool = True,
    dedupe_scope: str = "unread",
    action_type: str = "", action_id: str = "", action_role: str = "",
) -> Optional[Dict[str, Any]]:
    """Buat 1 notifikasi. Return None bila di-dedupe.

    `dedupe_scope`:
    - `"unread"` (default, perilaku lama) → dilewati bila masih ada notifikasi
      SAMA yang BELUM dibaca.
    - `"day"` (R6.5, dipakai job scheduler) → dilewati bila notifikasi sama sudah
      pernah dibuat HARI INI (dibaca atau belum) → job boleh dijalankan berkali-kali
      dalam sehari tanpa menduplikasi.

    `action_type`/`action_id`/`action_role` → aksi inline (mis. approve PO langsung
    dari kartu notifikasi). `action_role` = role minimum yang boleh aksi.
    """
    day = now_iso()[:10]
    dedupe_key = f"{notif_type}:{ref}:{day}" if ref else ""
    if dedupe and ref:
        if dedupe_scope == "day":
            if await db.notifications.find_one({"dedupe_key": dedupe_key}, {"_id": 1}):
                return None
        elif await _has_unread(notif_type, ref):
            return None
    doc = {
        "id": new_id("ntf"), "entity_id": entity_id,
        "recipient_role": recipient_role, "recipient_user": recipient_user,
        "type": notif_type, "title": title, "body": body, "link": link,
        "severity": severity, "ref": ref, "dedupe_key": dedupe_key,
        "read": False, "created_at": now_iso(),
        "action_type": action_type, "action_id": action_id, "action_role": action_role,
    }
    await db.notifications.insert_one(doc)
    clean = safe_doc(doc)
    # R6.5 — kanal WhatsApp (best-effort; TIDAK pernah menggagalkan pembuatan notifikasi).
    try:
        from services import wa_alert_service
        await wa_alert_service.push_notification(clean)
    except Exception:  # noqa: BLE001
        pass
    return clean


async def resolve_action(action_type: str, action_id: str, *, outcome: str = "",
                         actor: str = "") -> int:
    """Tutup notifikasi AKSI yang permintaannya sudah diputus.

    MASALAH YANG DISELESAIKAN: notifikasi "menunggu persetujuan" tetap menyala di
    lonceng walaupun dokumennya sudah disetujui/ditolak. Penerima mengklik tombol
    aksi yang PASTI gagal — bentuk lain dari tombol palsu, dan membuat pengguna
    tidak lagi percaya pada lonceng.

    Notifikasi TIDAK dihapus (jejak audit tetap utuh): ditandai `read` + diberi
    `resolved_at`/`resolution` sehingga aksi inline hilang tetapi riwayat tetap
    bisa dibaca. Aman dipanggil berkali-kali (idempotent) dan tidak pernah
    menggagalkan alur pemanggilnya.
    """
    if not action_type or not action_id:
        return 0
    try:
        res = await db.notifications.update_many(
            {"action_type": action_type, "action_id": action_id,
             "resolved_at": {"$exists": False}},
            {"$set": {"read": True, "read_at": now_iso(), "resolved_at": now_iso(),
                      "resolution": (outcome or "selesai")[:120], "resolved_by": actor}},
        )
        return int(res.modified_count or 0)
    except Exception:  # noqa: BLE001
        return 0


async def notify_po_awaiting_approval(po: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Depth #3 — notifikasi ke role approver saat PO masuk waiting_approval.

    Ditujukan ke `required_approval_role` (mis. manager). Dedupe via ref po_appr:<id>.
    Menyertakan alasan deviasi harga bila ada + aksi approve inline.
    """
    role = po.get("required_approval_role") or "manager"
    dev = po.get("price_deviation") or {}
    extra = ""
    if dev.get("flagged"):
        extra = f" Harga di atas price-list (+{dev.get('max_deviation_pct')}%)."
    return await create_notification(
        notif_type="po_approval", ref=f"po_appr:{po.get('id', '')}",
        title=f"PO menunggu persetujuan: {po.get('po_number', '')}",
        body=(f"{po.get('supplier_name', '')} · {rupiah(float(po.get('total_amount', 0)))}.{extra} "
              f"Perlu persetujuan {role}."),
        severity="warning" if dev.get("flagged") else "info",
        link="purchase-approval", entity_id=po.get("entity_id"), recipient_role=role,
        action_type="po_approve", action_id=po.get("id", ""), action_role=role,
    )


async def generate_system_notifications() -> int:
    """Pindai kondisi nyata sistem & buat notifikasi. Return jumlah yang dibuat."""
    created = 0

    # 1) Stok menipis — ambang batas per produk (`reorder_point`, konfigurasi NYATA
    #    di master produk); fallback ke ambang default bila produk belum diatur.
    products = await db.products.find({"status": "active"}, {"_id": 0}).to_list(300)
    for product in products:
        summary = await product_summary(product["id"])
        threshold = float(product.get("reorder_point") or 0) or LOW_STOCK_THRESHOLD
        if summary["available_qty"] < threshold:
            note = await create_notification(
                notif_type="low_stock", ref=f"low_stock:{product['id']}",
                title=f"Stok menipis: {product['name']}",
                body=(f"Available {summary['available_qty']:.0f} "
                      f"{product.get('base_unit', 'meter')} (< ambang {threshold:.0f}). "
                      f"Pertimbangkan buat PO ulang."),
                severity="warning", link="reorder", recipient_role="all",
                dedupe_scope="day",
            )
            if note:
                created += 1

    # 2) Reservasi mendekati kedaluwarsa (<= 24 jam) dari sales_orders
    soon = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    orders = await db.sales_orders.find(
        {"status": {"$in": ["reserved", "waiting_approval", "approved"]},
         "reservation_expires_at": {"$lte": soon}}, {"_id": 0}
    ).to_list(200)
    for order in orders:
        note = await create_notification(
            notif_type="reservation_expiring", ref=f"resv:{order['id']}",
            title=f"Reservasi akan kedaluwarsa: {order.get('number', '')}",
            body=(f"Order {order.get('number', '')} ({order.get('customer_name', '')}) "
                  f"reservasinya mendekati batas 3 hari. Segera approve/konfirmasi."),
            severity="warning", link="orders", entity_id=order.get("entity_id"),
            recipient_role="all",
        )
        if note:
            created += 1

    # 3) Order menunggu persetujuan (actionable, dari sales_orders)
    pending = await db.sales_orders.find({"status": "waiting_approval"}, {"_id": 0}).to_list(200)
    for order in pending:
        note = await create_notification(
            notif_type="order_approval", ref=f"appr:{order['id']}",
            title=f"Order menunggu persetujuan: {order.get('number', '')}",
            body=(f"{order.get('customer_name', '')} · {rupiah(float(order.get('total_amount', 0)))}. "
                  f"Memerlukan persetujuan manajer."),
            severity="info", link="orders", entity_id=order.get("entity_id"),
            recipient_role="all",
        )
        if note:
            created += 1

    # 4) Order split antar gudang (informasi fulfillment)
    splits = await db.sales_orders.find(
        {"is_split_warehouse": True, "status": {"$nin": ["cancelled", "expired", "done"]}}, {"_id": 0}
    ).to_list(200)
    for order in splits:
        note = await create_notification(
            notif_type="order_split", ref=f"split:{order['id']}",
            title=f"Order split antar gudang: {order.get('number', '')}",
            body=(f"Order {order.get('number', '')} dipenuhi dari beberapa gudang. "
                  f"Koordinasikan pengiriman gabungan."),
            severity="info", link="operations", entity_id=order.get("entity_id"),
            recipient_role="all",
        )
        if note:
            created += 1

    # 5) PO menunggu persetujuan (Depth #3 — approver notification, deduped)
    pending_po = await db.purchase_orders.find(
        {"status": "waiting_approval"}, {"_id": 0}).to_list(200)
    for po in pending_po:
        note = await notify_po_awaiting_approval(po)
        if note:
            created += 1

    return created
