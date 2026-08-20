"""PS-21 — Generator ALERT OPERASIONAL (quick win di atas mesin R6.5/R6.6).

Rujukan: `docs/KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md` §A.3 **PS-21**
("alur barang tidak ready & notifikasi operasional belum lengkap").

Tiga job baru — SEMUA memakai mesin yang sudah ada (R3: tidak membuat sistem
notifikasi kedua): `notification_service.create_notification(dedupe_scope="day")`
→ dedupe harian → kanal WhatsApp (instant/digest) → eskalasi R6.6.

| Job | Peristiwa nyata | Penerima |
|---|---|---|
| `po_arrival`      | barang PO **datang** (GR/inbound selesai) | manager (MD) + gudang + sales pemilik order pendingan |
| `backorder_ready` | barang **pendingan** tersedia / siap kirim | sales pemegang akun + manager |
| `ar_due_soon`     | piutang jatuh tempo **H-3 · H-1 · H · H+1** | sales pemegang akun + manager |

DESAIN PENTING
* **Event-driven + safety net.** `notify_po_arrival()` & `notify_backorder_ready()`
  dipanggil LANGSUNG saat peristiwanya terjadi (GR selesai / backorder terpenuhi)
  supaya notifikasi muncul seketika. Job terjadwal memindai ulang jendela waktu
  terakhir sebagai jaring pengaman — dedupe harian membuat TIDAK ada duplikasi.
* **Tanpa data palsu.** Semua angka dibaca dari `wms_tasks`, `inventory_balances`,
  `sales_orders`, dan mesin AR (`ar_aging_service`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from db import db
from services.notification_service import create_notification
from core_utils import rupiah

logger = logging.getLogger("alert_ops")

# Jendela pindai job po_arrival (jam). GR yang selesai dalam jendela ini dianggap
# "baru datang" — mencegah notifikasi lama muncul ulang tiap hari.
PO_ARRIVAL_LOOKBACK_HOURS = 24
# PS-21 — offset hari notifikasi jatuh tempo AR (negatif = sebelum jatuh tempo).
AR_DUE_SOON_OFFSETS = [-3, -1, 0, 1]
MAX_ALERTS_PER_JOB = 40
EPS = 0.01


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(iso: Any) -> Optional[datetime]:
    if isinstance(iso, datetime):
        return iso if iso.tzinfo else iso.replace(tzinfo=timezone.utc)
    if not iso or not isinstance(iso, str):
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _rp(v: Any) -> str:
    """Alias tipis ke `core_utils.rupiah` — satu sumber format uang untuk seluruh backend."""
    return rupiah(v)


def _qty(v: Any) -> str:
    try:
        return f"{float(v or 0):g}"
    except (TypeError, ValueError):
        return "0"


async def _sales_owner(customer_id: str) -> Dict[str, str]:
    """Sales pemegang akun (SSOT = `customers.assigned_sales_id`)."""
    if not customer_id:
        return {}
    cust = await db.customers.find_one(
        {"id": customer_id}, {"_id": 0, "assigned_sales_id": 1, "name": 1})
    sid = (cust or {}).get("assigned_sales_id") or ""
    if not sid:
        return {}
    user = await db.users.find_one({"id": sid}, {"_id": 0, "name": 1})
    return {"id": sid, "name": (user or {}).get("name", "")}


async def _available_qty(product_id: str, entity_id: str) -> float:
    """Stok tersedia (proyeksi balance = Σ roll available) untuk produk × entitas."""
    q: Dict[str, Any] = {"product_id": product_id}
    if entity_id:
        q["owner_entity_id"] = entity_id
    rows = await db.inventory_balances.find(q, {"_id": 0, "available_qty": 1}).to_list(200)
    return round(sum(float(r.get("available_qty", 0) or 0) for r in rows), 2)


# ═══ JOB 10 — barang PO datang (po_arrival) ══════════════════════════════════
async def notify_po_arrival(task: Dict[str, Any]) -> int:
    """Kirim notifikasi "barang PO datang" untuk SATU tugas inbound yang selesai.

    Dipanggil event-driven dari Goods Receipt **dan** oleh job `po_arrival`
    (dedupe harian menjaga tidak dobel).
    """
    if not task:
        return 0
    po_number = task.get("po_number") or ""
    prod_name = task.get("product_name") or task.get("sku") or ""
    qty = task.get("received_qty") or task.get("quantity") or 0
    unit = task.get("unit") or ""
    wh = task.get("warehouse_name") or task.get("warehouse_id") or ""
    body = (f"{prod_name} {_qty(qty)} {unit} diterima di {wh}"
            + (f" (PO {po_number})." if po_number else ".")
            + " Cek kualitas/putaway & lanjutkan alokasi order pendingan.")
    created = 0
    ref = f"po_arrival:{task.get('id', '')}"
    note = await create_notification(
        notif_type="po_arrival", ref=ref,
        title=f"Barang PO datang: {po_number or prod_name}",
        body=body, severity="info", link="purchasing",
        entity_id=task.get("entity_id"), recipient_role="manager", dedupe_scope="day",
    )
    if note:
        created += 1
    note_wh = await create_notification(
        notif_type="po_arrival", ref=f"po_arrival_wh:{task.get('id', '')}",
        title=f"Penerimaan selesai: {po_number or prod_name}",
        body=body, severity="info", link="operations",
        entity_id=task.get("entity_id"), recipient_role="warehouse", dedupe_scope="day",
    )
    if note_wh:
        created += 1

    # Sales yang punya order pendingan atas produk ini perlu tahu barang sudah masuk.
    pid = task.get("product_id") or ""
    if pid:
        orders = await db.sales_orders.find(
            {"has_backorder": True, "backorders.product_id": pid},
            {"_id": 0, "id": 1, "number": 1, "customer_id": 1, "customer_name": 1,
             "entity_id": 1}).to_list(50)
        for o in orders:
            owner = await _sales_owner(o.get("customer_id", ""))
            note_s = await create_notification(
                notif_type="po_arrival",
                ref=f"po_arrival_so:{task.get('id', '')}:{o.get('id')}",
                title=f"Barang pendingan {o.get('number', '')} sudah datang",
                body=(f"{prod_name} {_qty(qty)} {unit} masuk gudang {wh}"
                      + (f" via PO {po_number}" if po_number else "")
                      + f" — order {o.get('number', '')} ({o.get('customer_name', '')}) "
                      "bisa dilanjutkan."),
                severity="warning", link="orders", entity_id=o.get("entity_id"),
                recipient_role="sales", recipient_user=owner.get("id") or None,
                dedupe_scope="day",
            )
            if note_s:
                created += 1
    return created


async def job_po_arrival() -> Dict[str, Any]:
    """Pindai tugas inbound PO yang SELESAI dalam 24 jam terakhir."""
    cutoff = (_now() - timedelta(hours=PO_ARRIVAL_LOOKBACK_HOURS)).isoformat()
    tasks = await db.wms_tasks.find(
        {"flow_type": "inbound", "source_type": "purchase_order",
         "status": {"$in": ["completed", "qc_pending"]},
         "$or": [{"completed_at": {"$gte": cutoff}}, {"updated_at": {"$gte": cutoff}}]},
        {"_id": 0}).to_list(500)
    created = 0
    for t in tasks[:MAX_ALERTS_PER_JOB]:
        created += await notify_po_arrival(t)
    return {"created": created, "scanned": len(tasks),
            "detail": f"{len(tasks)} penerimaan PO selesai < {PO_ARRIVAL_LOOKBACK_HOURS} jam"}


# ═══ JOB 11 — barang pendingan siap (backorder_ready) ════════════════════════
async def notify_backorder_ready(order: Dict[str, Any], product_id: str = "",
                                 kind: str = "stock_available",
                                 qty: float = 0.0) -> int:
    """Notifikasi pendingan: `stock_available` (stok sudah ada) / `fulfilled` (sudah
    ter-reservasi, siap lanjut kirim)."""
    if not order:
        return 0
    owner = await _sales_owner(order.get("customer_id", ""))
    prod = await db.products.find_one({"id": product_id}, {"_id": 0, "name": 1, "sku": 1}) or {}
    pname = prod.get("name") or prod.get("sku") or product_id
    if kind == "fulfilled":
        title = f"Pendingan siap kirim: {order.get('number', '')}"
        body = (f"{pname} {_qty(qty)} untuk {order.get('customer_name', '')} sudah "
                "ter-reservasi dari stok yang baru masuk. Lanjutkan proses kirim.")
        sev = "warning"
    else:
        title = f"Stok pendingan tersedia: {order.get('number', '')}"
        body = (f"{pname} sudah tersedia {_qty(qty)} di gudang — order "
                f"{order.get('number', '')} ({order.get('customer_name', '')}) menunggu "
                "alokasi. Buka order untuk melanjutkan.")
        sev = "warning"
    created = 0
    note = await create_notification(
        notif_type="backorder_ready",
        ref=f"backorder_{kind}:{order.get('id')}:{product_id}",
        title=title, body=body, severity=sev, link="orders",
        entity_id=order.get("entity_id"), recipient_role="sales",
        recipient_user=owner.get("id") or None, dedupe_scope="day",
    )
    if note:
        created += 1
    note_m = await create_notification(
        notif_type="backorder_ready",
        ref=f"backorder_{kind}_mgr:{order.get('id')}:{product_id}",
        title=title, body=body, severity="info", link="orders",
        entity_id=order.get("entity_id"), recipient_role="manager", dedupe_scope="day",
    )
    if note_m:
        created += 1
    return created


async def job_backorder_ready() -> Dict[str, Any]:
    """Pendingan yang stoknya sudah tersedia (siap dialokasikan)."""
    orders = await db.sales_orders.find(
        {"has_backorder": True,
         "status": {"$nin": ["cancelled", "rejected", "delivered", "completed", "closed"]}},
        {"_id": 0, "id": 1, "number": 1, "customer_id": 1, "customer_name": 1,
         "entity_id": 1, "backorders": 1, "status": 1}).to_list(2000)
    created, scanned = 0, 0
    for o in orders:
        for bo in (o.get("backorders") or []):
            need = float(bo.get("backorder_qty", 0) or 0)
            if need <= EPS or bo.get("status") == "fulfilled":
                continue
            pid = bo.get("product_id") or ""
            avail = await _available_qty(pid, o.get("entity_id") or "")
            scanned += 1
            if avail <= EPS:
                continue
            if created >= MAX_ALERTS_PER_JOB:
                break
            created += await notify_backorder_ready(
                o, pid, kind="stock_available", qty=min(avail, need))
    return {"created": created, "scanned": scanned,
            "detail": f"{scanned} baris pendingan dipindai · {created} notifikasi stok tersedia"}


# ═══ JOB 12 — piutang jatuh tempo H-3 / H-1 / H / H+1 (ar_due_soon) ══════════
async def job_ar_due_soon() -> Dict[str, Any]:
    """Ingatkan piutang tepat pada offset H-3, H-1, H, dan H+1 (tanpa duplikasi).

    Sumber angka: `ar_aging_service.orders_due_soon` (SSOT AR yang sama dengan
    laporan aging & credit gate) — bukan hitungan sendiri (R3).
    """
    from services.ar_aging_service import orders_due_soon
    rows = await orders_due_soon(AR_DUE_SOON_OFFSETS)
    created = 0
    for r in rows[:MAX_ALERTS_PER_JOB]:
        offset = int(r.get("offset", 0))
        outstanding = float(r.get("outstanding", 0) or 0)
        due = str(r.get("due_date", ""))
        if offset < 0:
            when, sev = f"jatuh tempo {abs(offset)} hari lagi", "info"
        elif offset == 0:
            when, sev = "jatuh tempo HARI INI", "warning"
        else:
            when, sev = f"LEWAT jatuh tempo {offset} hari", "critical"
        body = (f"{r.get('customer_name', '')} · order {r.get('number', '')} · "
                f"{_rp(outstanding)} · {when} (tanggal {due}). "
                "Hubungi pelanggan / siapkan penagihan.")
        note = await create_notification(
            notif_type="ar_due_soon",
            ref=f"ar_due:{r.get('order_id')}:H{offset:+d}",
            title=f"Piutang {when}: {r.get('number', '')}",
            body=body, severity=sev, link="ar-aging", entity_id=r.get("entity_id"),
            recipient_role="sales", recipient_user=r.get("assigned_sales_id") or None,
            dedupe_scope="day",
        )
        if note:
            created += 1
        note_m = await create_notification(
            notif_type="ar_due_soon",
            ref=f"ar_due_mgr:{r.get('order_id')}:H{offset:+d}",
            title=f"Piutang {when}: {r.get('number', '')}",
            body=body, severity=sev, link="ar-aging", entity_id=r.get("entity_id"),
            recipient_role="manager", dedupe_scope="day",
        )
        if note_m:
            created += 1
    offsets = ", ".join(f"H{o:+d}".replace("H+0", "H") for o in AR_DUE_SOON_OFFSETS)
    return {"created": created, "scanned": len(rows),
            "detail": f"{len(rows)} order pada offset {offsets}"}


# ═══ Notifikasi permintaan repeat/restock (SO → PR) ══════════════════════════
async def notify_restock_request(order: Dict[str, Any], pr: Dict[str, Any],
                                 requester: str = "") -> int:
    """PS-21(a) — beri tahu MD (role manager) bahwa sales meminta repeat/restock.

    Catatan: divisi MD sebagai entitas tersendiri baru ada di Fase H (PS-17);
    sampai saat itu penerima = role `manager` (merchandiser/atasan) + admin
    (admin melihat semua notifikasi role-nya sendiri di bell).
    """
    items = pr.get("items") or []
    ringkas = ", ".join(
        f"{it.get('product_name', '')} {_qty(it.get('quantity'))} {it.get('unit', '')}"
        for it in items[:3])
    if len(items) > 3:
        ringkas += f", +{len(items) - 3} item lain"
    note = await create_notification(
        notif_type="restock_request", ref=f"restock:{pr.get('id')}",
        title=f"Permintaan repeat/restock: {pr.get('number', '')}",
        body=(f"{requester or 'Sales'} meminta pengadaan dari order "
              f"{order.get('number', '')} ({order.get('customer_name', '')}): {ringkas}. "
              f"Estimasi {_rp(pr.get('total_est_amount'))}. Tinjau & setujui PR."),
        severity="warning", link="purchase-requisitions",
        entity_id=pr.get("entity_id"), recipient_role="manager", dedupe_scope="day",
    )
    return 1 if note else 0
