"""Purchase Orders router (extra): Blanket/Contract PO, payables summary, pay/close/cancel.

Dipisah dari `routers/purchase_orders.py` agar file router di bawah batas guardrail.
Register SEBELUM `purchase_orders` di server.py agar GET /purchase-orders/blanket
tetap match sebelum GET /purchase-orders/{po_id}. Helper inti (_po_financials,
_create_po_core, AP_LIABILITY_STATUSES) di-reuse dari router utama.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, audit
from core_utils import now_iso, safe_doc, timeline_entry
from entity_scope import entity_ctx, resolve_list_scope
from schemas import POPaymentCreate, POCloseRequest, BlanketPOCreate, CallOffCreate, BlanketCloseRequest
from services import blanket_po_service
from routers.purchase_orders import _po_financials, _create_po_core, AP_LIABILITY_STATUSES

router = APIRouter(prefix="/api")


@router.post("/purchase-orders/blanket")
async def create_blanket_po(payload: BlanketPOCreate, request: Request) -> Dict[str, Any]:
    """P2 — buat kontrak Blanket/Contract PO (1.c qty per item + plafon nilai). Tanpa inbound task."""
    actor = await require_permission(request, "purchase_order", "create")
    blanket = await blanket_po_service.create_blanket(payload, actor)
    await audit(actor["name"], "blanket_po_created", "purchase_order", blanket["id"], {
        "po_number": blanket["po_number"], "supplier": blanket.get("supplier_name"),
        "items": len(blanket.get("contract_items", [])), "value_cap": blanket.get("contract_value_cap")})
    return blanket


@router.get("/purchase-orders/blanket")
async def list_blanket_pos(request: Request, entity_id: str = None) -> List[Dict[str, Any]]:
    """P2 — daftar Blanket PO + drawdown ringkas (called/remaining/status)."""
    await require_permission(request, "purchase_order", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("purchase_orders", {}, ctx, entity_id)
    return await blanket_po_service.list_blankets(scope=scope)


@router.post("/purchase-orders/{blanket_id}/call-off")
async def create_call_off(blanket_id: str, payload: CallOffCreate, request: Request) -> Dict[str, Any]:
    """P2 — call-off (release) terhadap Blanket PO → PO anak normal (2.a).

    4.b over-call (qty/nilai > sisa) DIIZINKAN tapi memaksa approval. 3.b override harga
    wajib alasan. 5.a kontrak kadaluarsa/habis → ditolak (di prepare_call_off).
    """
    actor = await require_permission(request, "purchase_order", "create")
    prep = await blanket_po_service.prepare_call_off(blanket_id, payload, actor)
    notes = []
    if prep["has_override"]:
        notes.append(f"override harga: {prep['price_override_reason']}")
    if prep["force_approval"]:
        notes.append("over-call: " + "; ".join(prep["over_items"]))
    po = await _create_po_core(
        prep["po_payload"], actor, po_type="call_off", parent=prep["blanket"],
        force_approval=prep["force_approval"], force_reason=prep["force_reason"],
        extra_note="; ".join(notes))
    await blanket_po_service.recompute_blanket_drawdown(prep["blanket"], persist=True)
    await audit(actor["name"], "po_call_off_created", "purchase_order", po["id"], {
        "po_number": po.get("po_number"), "blanket_id": blanket_id,
        "blanket_po_number": prep["blanket"].get("po_number"),
        "over_call": prep["force_approval"], "price_override": prep["has_override"]})
    return po


@router.post("/purchase-orders/{blanket_id}/close-contract")
async def close_blanket_contract(blanket_id: str, payload: BlanketCloseRequest, request: Request) -> Dict[str, Any]:
    """P2 — tutup kontrak Blanket secara manual (call-off baru ditolak — 5.a)."""
    actor = await require_permission(request, "purchase_order", "update")
    result = await blanket_po_service.close_blanket(blanket_id, payload.reason, actor)
    await audit(actor["name"], "blanket_po_closed", "purchase_order", blanket_id,
                {"reason": payload.reason})
    return result


@router.post("/purchase-orders/{po_id}/pay")
async def pay_purchase_order(po_id: str, payload: POPaymentCreate, request: Request) -> Dict[str, Any]:
    """P0-B (SSOT AP) — Pembayaran PO DINONAKTIFKAN.

    Hutang (AP) & pembayaran ke supplier kini dikelola SATU PINTU melalui
    Vendor Bill (menu "Tagihan Supplier"). Endpoint ini sengaja diblokir agar
    tidak terjadi double-count hutang / kas keluar ganda dengan Vendor Bill.
    """
    await require_permission(request, "purchase_order", "update")
    raise HTTPException(
        status_code=400,
        detail=("Pembayaran langsung di PO dinonaktifkan. Hutang & pembayaran supplier "
                "dikelola via Tagihan Supplier (Vendor Bill). Buat/posting Vendor Bill "
                "untuk PO ini, lalu bayar dari sana."))


@router.post("/purchase-orders/{po_id}/close")
async def close_purchase_order_short(po_id: str, payload: POCloseRequest, request: Request) -> Dict[str, Any]:
    """Depth 1A — tutup PO yang kurang terima (short-close). Sisa item tak diharapkan lagi."""
    actor = await require_permission(request, "purchase_order", "update")
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order tidak ditemukan")
    if po.get("status") not in ("receiving", "partial", "pending"):
        raise HTTPException(status_code=400, detail=f"PO status '{po.get('status')}' tidak bisa ditutup-kurang")
    updated = await db.purchase_orders.find_one_and_update(
        {"id": po_id},
        {"$set": {"status": "closed_short", "close_reason": payload.reason,
                  "closed_by": actor["name"], "closed_at": now_iso(), "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry(
             "closed_short", "Ditutup-kurang", actor["name"], payload.reason or "")}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    # Batalkan inbound task yang belum selesai
    await db.wms_tasks.update_many(
        {"po_id": po_id, "status": {"$nin": ["completed", "cancelled"]}},
        {"$set": {"status": "cancelled", "updated_at": now_iso(),
                  "cancel_reason": "PO ditutup-kurang"}})
    await audit(actor["name"], "po_closed_short", "purchase_order", po_id,
                {"po_number": po.get("po_number"), "reason": payload.reason})
    return safe_doc(updated)


@router.get("/purchase-orders/payables/summary")
async def payables_summary(request: Request, entity_id: str = None) -> Dict[str, Any]:
    """Depth 1C — ringkasan hutang (AP) ke supplier + aging per PO."""
    await require_permission(request, "purchase_order", "view")
    from datetime import datetime, timezone
    ctx = await entity_ctx(request)
    q: Dict[str, Any] = {"status": {"$in": list(AP_LIABILITY_STATUSES)}}
    q = resolve_list_scope("purchase_orders", q, ctx, entity_id)
    pos = await db.purchase_orders.find(q, {"_id": 0}).to_list(1000)
    now = datetime.now(timezone.utc)
    by_supplier: Dict[str, Dict[str, Any]] = {}
    aging = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, ">90": 0.0}
    total_outstanding = 0.0
    rows = []
    for po in pos:
        fin = _po_financials(po)
        out = fin["outstanding"]
        if out <= 0.01:
            continue
        total_outstanding += out
        # aging dari expected_delivery_date / created_at
        ref_date = po.get("expected_delivery_date") or po.get("created_at") or ""
        days = 0
        try:
            d = datetime.fromisoformat(ref_date.replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            days = (now - d).days
        except Exception:  # noqa: BLE001
            days = 0
        bucket = "0-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else ">90"
        aging[bucket] += out
        sid = po.get("supplier_id") or po.get("supplier_name") or "—"
        sup = by_supplier.setdefault(sid, {
            "supplier_id": po.get("supplier_id", ""), "supplier_name": po.get("supplier_name", "—"),
            "outstanding": 0.0, "po_count": 0})
        sup["outstanding"] = round(sup["outstanding"] + out, 2)
        sup["po_count"] += 1
        rows.append({
            "po_id": po["id"], "po_number": po.get("po_number"), "supplier_name": po.get("supplier_name"),
            "supplier_id": po.get("supplier_id", ""), "status": po.get("status"),
            "total_amount": fin["total_amount"], "amount_paid": fin["amount_paid"],
            "returned_amount": fin["returned_amount"], "outstanding": out,
            "payment_status": fin["payment_status"], "days_outstanding": days, "aging_bucket": bucket,
            "expected_delivery_date": po.get("expected_delivery_date", ""),
        })
    rows.sort(key=lambda r: (-r["days_outstanding"], -r["outstanding"]))
    return {
        "total_outstanding": round(total_outstanding, 2),
        "aging": {k: round(v, 2) for k, v in aging.items()},
        "by_supplier": sorted(by_supplier.values(), key=lambda s: -s["outstanding"]),
        "purchase_orders": rows,
    }


@router.post("/purchase-orders/{po_id}/cancel")
async def cancel_purchase_order(po_id: str, request: Request) -> Dict[str, Any]:
    """Cancel a purchase order."""
    actor = await require_permission(request, "purchase_order", "update")

    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order tidak ditemukan")

    if po["status"] not in ["pending", "receiving", "waiting_approval"]:
        raise HTTPException(status_code=400, detail=f"PO dengan status {po['status']} tidak bisa dibatalkan")

    # Update PO status
    updated_po = await db.purchase_orders.find_one_and_update(
        {"id": po_id},
        {"$set": {"status": "cancelled", "cancelled_by": actor["name"],
                  "cancelled_at": now_iso(), "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry(
             "cancelled", "PO dibatalkan", actor["name"], "")}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )

    # Cancel related inbound tasks
    await db.wms_tasks.update_many(
        {"po_id": po_id},
        {"$set": {"status": "cancelled", "updated_at": now_iso()}}
    )

    await audit(actor["name"], "po_cancelled", "purchase_order", po_id, {})

    return safe_doc(updated_po)
