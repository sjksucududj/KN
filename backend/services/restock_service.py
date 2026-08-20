"""PS-21(a) — Repeat/Restock 1-klik dari Sales Order → Purchase Requisition.

Rujukan: `docs/KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md` §A.3 **PS-21**
("dari layar order, sales dapat menandai kebutuhan repeat/restock → membuat PR
otomatis (jalur PS-05) + notifikasi ke MD; barang yang belum tersedia masuk
pendingan dengan status yang terlihat sales").

PRINSIP (R3 — tanpa sistem kedua)
* PR dibuat lewat `purchase_requisition_service.create_requisition` yang SUDAH ada
  (matriks approval, penomoran, invarian PR tetap berlaku).
* Pendingan memakai `sales_orders.backorders[]` yang sudah ada — TIDAK ada koleksi
  pendingan baru.
* Notifikasi memakai mesin R6.5/R6.6 lewat `alert_ops_service.notify_restock_request`.

Jejak dua arah: PR menyimpan `source="so_repeat"` + `source_ref_id=<so_id>`;
SO menyimpan `restock_requests[]` (nomor PR, item, status, waktu, pemohon).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from db import db
from core_utils import now_iso
from services import purchase_requisition_service as prs
from services import alert_ops_service as ops

EPS = 0.01
PR_SOURCE = "so_repeat"
# Status PR yang masih "terbuka" (belum jadi PO / belum ditolak) — dipakai untuk
# mencegah PR ganda atas SO+produk yang sama (selaras `prs.OPEN_PR_STATUSES`).
OPEN_PR_STATUSES = prs.OPEN_PR_STATUSES


class RestockError(ValueError):
    """Kesalahan yang harus dipetakan ke HTTP 400 oleh router."""


class _ItemShim:
    """Adaptor agar `create_requisition` (yang membaca atribut) bisa dipakai ulang."""

    def __init__(self, product_id: str, quantity: float, unit: str,
                 est_price: float, description: str, note: str):
        self.product_id = product_id
        self.quantity = quantity
        self.unit = unit
        self.est_price = est_price
        self.description = description
        self.note = note


class _PRShim:
    def __init__(self, **kw: Any):
        for k, v in kw.items():
            setattr(self, k, v)


async def _order_or_raise(order_id: str) -> Dict[str, Any]:
    order = await db.sales_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise RestockError("Sales order tidak ditemukan")
    return order


async def _open_restock_prs(order_id: str) -> List[Dict[str, Any]]:
    return await db.purchase_requisitions.find(
        {"source": PR_SOURCE, "source_ref_id": order_id},
        {"_id": 0, "id": 1, "number": 1, "status": 1, "items": 1, "created_at": 1,
         "created_by": 1, "total_est_amount": 1, "po_id": 1, "po_number": 1},
    ).sort("created_at", -1).to_list(50)


async def order_restock_state(order_id: str) -> Dict[str, Any]:
    """Ringkasan untuk layar SO: kandidat repeat/restock + pendingan + PR terkait.

    Kandidat = gabungan baris order & baris pendingan; setiap baris membawa
    `available_qty` (stok nyata), `backorder_qty` (pendingan), dan `suggest_qty`
    (kekurangan yang perlu dibeli) sehingga sales tidak perlu menghitung manual.
    """
    order = await _order_or_raise(order_id)
    entity_id = order.get("entity_id") or ""
    prs_open = await _open_restock_prs(order_id)
    open_by_product: Dict[str, Dict[str, Any]] = {}
    for pr in prs_open:
        if pr.get("status") in OPEN_PR_STATUSES:
            for it in pr.get("items") or []:
                open_by_product.setdefault(it.get("product_id", ""), pr)

    bo_by_product: Dict[str, float] = {}
    bo_status: Dict[str, str] = {}
    for bo in order.get("backorders") or []:
        pid = bo.get("product_id") or ""
        bo_by_product[pid] = round(bo_by_product.get(pid, 0.0)
                                   + float(bo.get("backorder_qty", 0) or 0), 2)
        bo_status[pid] = bo.get("status") or "waiting_stock"

    rows: List[Dict[str, Any]] = []
    seen: set = set()

    async def _row(pid: str, name: str, sku: str, unit: str, ordered: float,
                   price: float) -> Dict[str, Any]:
        avail = await ops._available_qty(pid, entity_id)
        backorder = bo_by_product.get(pid, 0.0)
        suggest = round(backorder if backorder > EPS else max(ordered - avail, 0.0), 2)
        pr_open = open_by_product.get(pid)
        prod = await db.products.find_one(
            {"id": pid}, {"_id": 0, "harga_pokok": 1, "price": 1, "base_unit": 1}) or {}
        est = round(float(price or prod.get("harga_pokok") or prod.get("price") or 0), 2)
        return {
            "product_id": pid, "product_name": name, "sku": sku,
            "unit": unit or prod.get("base_unit") or "meter",
            "ordered_qty": round(float(ordered or 0), 2),
            "available_qty": avail,
            "backorder_qty": backorder,
            "backorder_status": bo_status.get(pid, ""),
            "suggest_qty": suggest if suggest > EPS else round(float(ordered or 0), 2),
            "est_price": est,
            "open_pr_number": (pr_open or {}).get("number", ""),
            "open_pr_status": (pr_open or {}).get("status", ""),
        }

    for it in order.get("items") or []:
        pid = it.get("product_id") or ""
        if not pid or pid in seen:
            continue
        seen.add(pid)
        rows.append(await _row(pid, it.get("product_name") or it.get("name", ""),
                               it.get("sku", ""), it.get("unit", ""),
                               float(it.get("quantity", 0) or 0),
                               float(it.get("harga_pokok", 0) or 0)))
    for bo in order.get("backorders") or []:
        pid = bo.get("product_id") or ""
        if not pid or pid in seen:
            continue
        seen.add(pid)
        rows.append(await _row(pid, bo.get("product_name", ""), bo.get("sku", ""),
                               bo.get("unit", ""),
                               float(bo.get("requested_qty", 0) or 0), 0.0))

    pendingan = [
        {"product_id": bo.get("product_id"), "product_name": bo.get("product_name", ""),
         "sku": bo.get("sku", ""),
         "requested_qty": round(float(bo.get("requested_qty", 0) or 0), 2),
         "reserved_qty": round(float(bo.get("reserved_qty", 0) or 0), 2),
         "backorder_qty": round(float(bo.get("backorder_qty", 0) or 0), 2),
         "status": bo.get("status", ""),
         "available_qty": await ops._available_qty(bo.get("product_id", ""), entity_id),
         "updated_at": bo.get("updated_at", "")}
        for bo in (order.get("backorders") or [])
    ]

    return {
        "order_id": order_id, "number": order.get("number", ""),
        "status": order.get("status", ""), "sub_status": order.get("sub_status", ""),
        "customer_name": order.get("customer_name", ""),
        "entity_id": entity_id,
        "has_backorder": bool(order.get("has_backorder")),
        "candidates": rows,
        "pendingan": pendingan,
        "restock_requests": order.get("restock_requests") or [],
        "purchase_requisitions": prs_open,
    }


async def request_repeat_restock(order_id: str, items: List[Any], actor: Dict[str, Any],
                                 reason: str = "", notes: str = "",
                                 warehouse_id: str = "", needed_by_date: str = "",
                                 submit_now: bool = True) -> Dict[str, Any]:
    """Buat PR dari SO dalam satu langkah + notifikasi MD + jejak dua arah.

    `items` = daftar objek/dict dengan `product_id`, `quantity`, opsional `unit`,
    `est_price`, `note`. Menolak (400) bila: order tidak ada, item kosong, qty <= 0,
    produk tidak dikenal, atau sudah ada PR repeat/restock TERBUKA untuk produk sama
    (mencegah PR ganda — selaras aturan reorder R1-05).
    """
    order = await _order_or_raise(order_id)
    raw = list(items or [])
    if not raw:
        raise RestockError("Pilih minimal satu item yang ingin di-repeat/restock")

    open_prs = [p for p in await _open_restock_prs(order_id)
                if p.get("status") in OPEN_PR_STATUSES]
    already: Dict[str, str] = {}
    for p in open_prs:
        for it in p.get("items") or []:
            already[it.get("product_id", "")] = p.get("number", "")

    shims: List[_ItemShim] = []
    for it in raw:
        pid = str((it.get("product_id") if isinstance(it, dict)
                   else getattr(it, "product_id", "")) or "").strip()
        qty = float((it.get("quantity") if isinstance(it, dict)
                     else getattr(it, "quantity", 0)) or 0)
        unit = str((it.get("unit") if isinstance(it, dict)
                    else getattr(it, "unit", "")) or "").strip()
        est = float((it.get("est_price") if isinstance(it, dict)
                     else getattr(it, "est_price", 0)) or 0)
        note = str((it.get("note") if isinstance(it, dict)
                    else getattr(it, "note", "")) or "")
        if not pid:
            raise RestockError("Produk wajib dipilih untuk setiap baris repeat/restock")
        if qty <= EPS:
            raise RestockError("Jumlah (qty) setiap baris harus lebih besar dari 0")
        if pid in already:
            raise RestockError(
                f"Produk ini sudah punya permintaan repeat/restock terbuka "
                f"({already[pid]}). Selesaikan/batalkan PR itu dulu agar tidak dobel.")
        prod = await db.products.find_one(
            {"id": pid}, {"_id": 0, "name": 1, "sku": 1, "base_unit": 1,
                          "harga_pokok": 1, "price": 1})
        if not prod:
            raise RestockError(f"Produk {pid} tidak ditemukan")
        shims.append(_ItemShim(
            product_id=pid, quantity=round(qty, 2),
            unit=unit or prod.get("base_unit") or "meter",
            est_price=round(est or float(prod.get("harga_pokok") or prod.get("price") or 0), 2),
            description=prod.get("name", ""),
            note=note or f"Repeat/restock dari {order.get('number', '')}",
        ))

    wh = warehouse_id or await _default_warehouse(order)
    payload = _PRShim(
        items=shims, warehouse_id=wh, entity_id=order.get("entity_id") or "",
        reason=reason or (f"Repeat/restock permintaan pelanggan "
                          f"{order.get('customer_name', '')} (order {order.get('number', '')})"),
        needed_by_date=needed_by_date, source=PR_SOURCE, source_ref_id=order_id,
        preferred_supplier_id="", notes=notes, submit_now=bool(submit_now),
    )
    try:
        pr = await prs.create_requisition(
            payload, created_by=actor.get("name", "System"),
            created_by_id=actor.get("id", ""))
    except ValueError as exc:
        raise RestockError(str(exc)) from exc

    entry = {
        "pr_id": pr["id"], "pr_number": pr.get("number", ""),
        "status": pr.get("status", ""),
        "items": [{"product_id": s.product_id, "product_name": s.description,
                   "quantity": s.quantity, "unit": s.unit} for s in shims],
        "total_est_amount": pr.get("total_est_amount", 0),
        "requested_by": actor.get("name", ""), "requested_by_id": actor.get("id", ""),
        "requested_at": now_iso(), "reason": payload.reason,
    }
    tl_note = (f"Permintaan repeat/restock → PR {pr.get('number', '')} "
               f"({len(shims)} item)")
    await db.sales_orders.update_one(
        {"id": order_id},
        {"$push": {"restock_requests": entry},
         "$set": {"updated_at": now_iso(), "last_restock_note": tl_note}})

    notified = await ops.notify_restock_request(order, pr, requester=actor.get("name", ""))
    from dependencies import audit
    await audit(actor.get("name", "System"), "restock_requested", "sales_order", order_id,
                {"pr_id": pr["id"], "pr_number": pr.get("number", ""),
                 "items": len(shims), "total_est": pr.get("total_est_amount", 0),
                 "notified_md": notified},
                "PS-21 — repeat/restock 1-klik dari Sales Order")
    return {"ok": True, "pr": pr, "notified_md": notified,
            "message": (f"PR {pr.get('number', '')} dibuat ({pr.get('status', '')}) "
                        f"& MD sudah dinotifikasi." if notified else
                        f"PR {pr.get('number', '')} dibuat ({pr.get('status', '')}).")}


async def _default_warehouse(order: Dict[str, Any]) -> str:
    """Gudang tujuan default: gudang alokasi order, else gudang pertama entitas."""
    for a in order.get("allocations") or []:
        if a.get("warehouse_id"):
            return a["warehouse_id"]
    q: Dict[str, Any] = {}
    if order.get("entity_id"):
        q["entity_id"] = order["entity_id"]
    wh = await db.warehouses.find_one(q, {"_id": 0, "id": 1}) or \
        await db.warehouses.find_one({}, {"_id": 0, "id": 1})
    return (wh or {}).get("id", "")
