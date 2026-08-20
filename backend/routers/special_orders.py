"""Special Orders Router - Sub-fase 1.12

Handles custom product orders (products not yet in catalog).
Status flow aligned with sales_orders for consistency.
"""
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from db import db
from dependencies import require_permission, audit, current_user
from core_utils import new_id, now_iso, safe_doc
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from services.special_order_service import (
    generate_special_order_number,
    can_approve_special_order,
    approve_special_order,
    reject_special_order,
    transition_special_order_status,
    create_sku_from_special_order,
    APPROVAL_THRESHOLD
)
from services import purchase_requisition_service as pr_svc
from services import approval_matrix_service as amx  # PS-20 — PO Custom 2 tingkat (Manager → Direksi)
from schemas import (
    PurchaseRequisitionCreate, PurchaseRequisitionItem, SpecialOrderToPR,
    SalesOrderCreate, SalesOrderItemIn,
)

router = APIRouter(prefix="/api")


# ─── Schemas ─────────────────────────────────────────────────────────────────

class CustomItemSpec(BaseModel):
    """Custom item specification"""
    description: str = Field(..., description="Item description")
    specifications: Dict[str, Any] = Field(default_factory=dict, description="Custom specs (size, color, material, etc)")
    quantity: float = Field(..., gt=0, description="Quantity")
    unit: str = Field(..., description="Unit of measure")
    target_price: float = Field(..., ge=0, description="Target price per unit (IDR)")
    notes: str = Field(default="", description="Additional notes")


class SpecialOrderCreate(BaseModel):
    """Create special order request"""
    customer_id: str = Field(..., description="Customer ID")
    entity_id: str = Field(default="", description="Selling entity ID")
    custom_item: CustomItemSpec = Field(..., description="Custom item details")
    expected_delivery: str = Field(..., description="Expected delivery date (ISO format)")
    shipping_address_id: str = Field(default="", description="Shipping address ID")
    notes: str = Field(default="", description="Order notes")
    submit_for_approval: bool = Field(default=False, description="Auto-submit if needs approval")


class SpecialOrderApprove(BaseModel):
    """Approve special order"""
    notes: str = Field(default="", description="Approval notes")


class SpecialOrderReject(BaseModel):
    """Reject special order"""
    reason: str = Field(..., min_length=1, description="Rejection reason")


class SpecialOrderStatusUpdate(BaseModel):
    """Update special order status"""
    status: str = Field(..., description="New status")
    notes: str = Field(default="", description="Update notes")


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/special-orders")
async def list_special_orders(
    request: Request,
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
    entity_id: Optional[str] = None
) -> Dict[str, Any]:
    """List special orders with optional filters.
    
    Query params:
    - status: Filter by status
    - customer_id: Filter by customer
    - entity_id: Filter by entity
    """
    await require_permission(request, "order", "view")
    ctx = await entity_ctx(request)
    
    query = {}
    if status:
        query["status"] = status
    if customer_id:
        query["customer_id"] = customer_id
    query = resolve_list_scope("special_orders", query, ctx, entity_id)
    
    special_orders = await db.special_orders.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    
    # Aggregate stats (ter-scope entitas, lepas dari filter status/customer)
    stats_match = resolve_list_scope("special_orders", {}, ctx, entity_id)
    pipeline = [
        {"$match": stats_match},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "total_amount": {"$sum": "$total_amount"}
        }}
    ]
    
    status_counts = {}
    async for doc in db.special_orders.aggregate(pipeline):
        status_counts[doc["_id"]] = {
            "count": doc["count"],
            "total_amount": doc["total_amount"]
        }
    
    return {
        "items": special_orders,
        "count": len(special_orders),
        "by_status": status_counts,
        "approval_threshold": APPROVAL_THRESHOLD
    }


@router.post("/special-orders")
async def create_special_order(payload: SpecialOrderCreate, request: Request) -> Dict[str, Any]:
    """Create new special order for custom product.
    
    Flow:
    1. Validate customer exists
    2. Calculate total amount
    3. Generate order number
    4. Check approval requirement (amount > threshold)
    5. Create order document
    6. Return created order
    """
    await require_permission(request, "order", "create")
    user = await current_user(request)
    ctx = await entity_ctx(request)
    
    # Validate customer
    customer = await db.customers.find_one({"id": payload.customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    
    # Get shipping address
    address = {}
    if payload.shipping_address_id:
        address = next(
            (a for a in customer.get("addresses", []) if a["id"] == payload.shipping_address_id),
            customer.get("addresses", [{}])[0] if customer.get("addresses") else {}
        )
    else:
        address = customer.get("addresses", [{}])[0] if customer.get("addresses") else {}
    
    # Calculate total amount
    total_amount = payload.custom_item.target_price * payload.custom_item.quantity
    
    # Generate order ID and number
    order_id = new_id("sord")
    order_number = await generate_special_order_number()
    
    # Determine initial status
    initial_status = "draft"
    if total_amount > APPROVAL_THRESHOLD and payload.submit_for_approval:
        initial_status = "pending_approval"
    
    # Create special order document
    special_order = {
        "id": order_id,
        "number": order_number,
        "status": initial_status,
        "type": "special_order",
        
        # Customer info
        "customer_id": customer["id"],
        "customer_name": customer["name"],
        "customer_email": customer.get("email", ""),
        "customer_phone": customer.get("phone", ""),
        
        # Shipping
        "shipping_address": address,
        
        # Custom item
        "custom_item": {
            "description": payload.custom_item.description,
            "specifications": payload.custom_item.specifications,
            "quantity": payload.custom_item.quantity,
            "unit": payload.custom_item.unit,
            "target_price": payload.custom_item.target_price,
            "notes": payload.custom_item.notes
        },
        
        # Financial
        "total_amount": total_amount,
        "requires_approval": total_amount > APPROVAL_THRESHOLD,
        "approval_threshold": APPROVAL_THRESHOLD,
        
        # Timeline
        "expected_delivery": payload.expected_delivery,
        
        # Entity
        "entity_id": payload.entity_id or customer.get("entity_id") or ctx.active_entity_id,
        
        # Notes
        "notes": payload.notes,
        
        # Status tracking
        "status_history": [{
            "status": initial_status,
            "timestamp": now_iso(),
            "user": user["email"]
        }],
        
        # Metadata
        "created_at": now_iso(),
        "created_by": user["email"],
        "updated_at": now_iso()
    }

    # PS-20 — cap rantai persetujuan sejak awal supaya pembuat dokumen langsung
    # melihat berapa tingkat yang dibutuhkan (Manager, dan Direksi bila nilainya besar).
    if initial_status == "pending_approval":
        _chain, _cfg = await amx.special_order_chain(special_order,
                                                     special_order.get("entity_id", ""))
        special_order["approval_chain"] = _chain
        special_order["approval_level_current"] = (_chain[0]["level"] if _chain else 0)
        special_order["required_approval_role"] = (
            (_chain[0].get("roles") or ["manager"])[0] if _chain else "")
        special_order["approval_status"] = "pending"

    from services import line_scope as _lines            # FASE L
    await _lines.stamp_doc(db, special_order)
    await db.special_orders.insert_one(special_order)
    special_order.pop("_id", None)
    
    # Audit log
    await audit(
        user.get("name", ""),
        "special_order_created",
        "special_order",
        order_id,
        {"number": order_number, "customer_id": payload.customer_id, "total_amount": total_amount}
    )
    
    return special_order


@router.get("/special-orders/{order_id}")
async def get_special_order(order_id: str, request: Request) -> Dict[str, Any]:
    """Get special order detail by ID."""
    await require_permission(request, "order", "view")
    ctx = await entity_ctx(request)
    
    special_order = await db.special_orders.find_one({"id": order_id}, {"_id": 0})
    if not special_order:
        raise HTTPException(status_code=404, detail="Special order tidak ditemukan")
    assert_entity_access(special_order, "special_orders", ctx)
    
    return special_order


@router.post("/special-orders/{order_id}/approve")

async def approve_special_order_endpoint(
    order_id: str,
    payload: SpecialOrderApprove,
    request: Request
) -> Dict[str, Any]:
    """Approve special order (PO Custom) — PS-20: BERJENJANG sesuai matriks divisi.

    Tingkat 1 = Manager (admin juga boleh). Bila nilai pesanan ≥ ambang
    `approval.po_custom_direksi_min`, dibutuhkan tingkat 2 = **Direksi (admin)**.
    Transisi: pending_approval → (tingkat 2 menunggu) → confirmed.
    """
    await require_permission(request, "order", "approve")
    user = await current_user(request)

    special_order = safe_doc(await db.special_orders.find_one({"id": order_id}, {"_id": 0}))
    if not special_order:
        raise HTTPException(status_code=404, detail="Special order tidak ditemukan")

    if not await can_approve_special_order(special_order, user["role"]):
        raise HTTPException(
            status_code=403,
            detail="Hanya manager/admin yang dapat approve special order dengan status pending_approval"
        )

    entity_id = special_order.get("entity_id", "")
    chain, _cfg = await amx.special_order_chain(special_order, entity_id)
    level = amx.pending_level(chain)
    if level is None:
        raise HTTPException(status_code=409, detail="Semua tingkat persetujuan sudah terpenuhi.")
    # Matriks persetujuan divisi (peran per tingkat + pemisahan tugas) — MENGIKAT.
    ev = await amx.guard("po_custom", user, special_order, entity_id,
                         amount=special_order.get("total_amount"), level=level,
                         action="approve")

    level["status"] = "approved"
    level["approved_by"] = user.get("name", "")
    level["approved_by_id"] = user.get("id", "")
    level["approved_at"] = now_iso()
    nxt = amx.pending_level(chain)

    if nxt is not None:
        # Masih butuh tingkat berikutnya (Direksi) → tetap menunggu persetujuan.
        await db.special_orders.update_one(
            {"id": order_id},
            {"$set": {"approval_chain": chain,
                      "approval_level_current": nxt["level"],
                      "required_approval_role": (nxt.get("roles") or ["admin"])[0],
                      "updated_at": now_iso()},
             "$push": {"status_history": {
                 "status": "pending_approval",
                 "timestamp": now_iso(), "user": user.get("email", ""),
                 "note": (f"Disetujui tingkat {level['level']} ({level.get('label', '')}) — "
                          f"lanjut ke {nxt.get('label', '')}")}}})
        await amx.record(stage="po_custom", action="approve", actor=user, doc=special_order,
                         entity_id=entity_id, level=level["level"],
                         level_label=level.get("label", ""),
                         outcome=f"disetujui tingkat {level['level']} — menunggu {nxt.get('label', '')}",
                         note=payload.notes or "", enforced=ev.get("enforced", True))
        await audit(user.get("name", ""), "special_order_approved_level", "special_order",
                    order_id, {"number": special_order.get("number"),
                               "level": level["level"], "next": nxt.get("label", "")},
                    reason=payload.notes or "")
        return safe_doc(await db.special_orders.find_one({"id": order_id}, {"_id": 0}))

    try:
        updated = await approve_special_order(order_id, user["email"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.special_orders.update_one(
        {"id": order_id},
        {"$set": {"approval_chain": chain, "approval_level_current": 0,
                  "approval_status": "approved"}})
    await amx.record(stage="po_custom", action="approve", actor=user, doc=special_order,
                     entity_id=entity_id, level=level["level"],
                     level_label=level.get("label", ""),
                     outcome=f"disetujui penuh ({len(chain)} tingkat)",
                     note=payload.notes or "", enforced=ev.get("enforced", True))
    await audit(user.get("name", ""), "special_order_approved", "special_order", order_id,
                {"number": special_order.get("number"), "levels": len(chain)},
                reason=payload.notes or "")
    return safe_doc(await db.special_orders.find_one({"id": order_id}, {"_id": 0})) or updated


@router.post("/special-orders/{order_id}/reject")

async def reject_special_order_endpoint(
    order_id: str,
    payload: SpecialOrderReject,
    request: Request
) -> Dict[str, Any]:
    """Reject special order (manager/admin only) — PS-20: dijaga matriks divisi.
    
    Transitions: pending_approval → cancelled
    """
    await require_permission(request, "order", "approve")
    user = await current_user(request)
    
    # Check if user can reject
    special_order = safe_doc(await db.special_orders.find_one({"id": order_id}, {"_id": 0}))
    if not special_order:
        raise HTTPException(status_code=404, detail="Special order tidak ditemukan")
    
    if not await can_approve_special_order(special_order, user["role"]):
        raise HTTPException(
            status_code=403,
            detail="Hanya manager/admin yang dapat reject special order dengan status pending_approval"
        )
    entity_id = special_order.get("entity_id", "")
    chain, _cfg = await amx.special_order_chain(special_order, entity_id)
    level = amx.pending_level(chain) or (chain[0] if chain else None)
    ev = await amx.guard("po_custom", user, special_order, entity_id,
                         amount=special_order.get("total_amount"), level=level,
                         action="reject")
    try:
        updated = await reject_special_order(order_id, user["email"], payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await amx.record(stage="po_custom", action="reject", actor=user, doc=special_order,
                     entity_id=entity_id, level=(level or {}).get("level", 1),
                     level_label=(level or {}).get("label", ""), outcome="ditolak",
                     note=payload.reason or "", enforced=ev.get("enforced", True))
    await audit(user.get("name", ""), "special_order_rejected", "special_order", order_id,
                {"number": special_order.get("number")}, reason=payload.reason or "")
    return updated


@router.post("/special-orders/{order_id}/status")

async def update_special_order_status(
    order_id: str,
    payload: SpecialOrderStatusUpdate,
    request: Request
) -> Dict[str, Any]:
    """Update special order status.
    
    Valid transitions:
    - confirmed → in_production (purchasing started)
    - in_production → ready (item produced/received)
    - ready → shipped (dispatched to customer)
    - shipped → done (delivered)
    """
    await require_permission(request, "order", "update")
    user = await current_user(request)
    
    try:
        updated = await transition_special_order_status(
            order_id,
            payload.status,
            user["email"]
        )
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/special-orders/{order_id}/create-pr")
async def create_pr_from_special_order(
    order_id: str,
    payload: SpecialOrderToPR,
    request: Request
) -> Dict[str, Any]:
    """Depth #2c — Jembatan Special Order → Purchase Requisition (pengadaan).

    Membuat PR (source=special_order) untuk item custom, lalu menggerakkan
    special order: confirmed → in_production (purchasing started).
    """
    await require_permission(request, "purchase_requisition", "create")
    user = await current_user(request)

    so = await db.special_orders.find_one({"id": order_id}, {"_id": 0})
    if not so:
        raise HTTPException(status_code=404, detail="Special order tidak ditemukan")
    if so.get("linked_pr_id"):
        raise HTTPException(status_code=400, detail=f"Special order sudah punya PR ({so.get('linked_pr_number')})")
    if so["status"] not in ("confirmed", "in_production"):
        raise HTTPException(status_code=400,
                            detail="PR hanya bisa dibuat untuk special order yang sudah confirmed")

    ci = so.get("custom_item", {})
    if payload.warehouse_id:   # E4.1 — gudang tujuan pengadaan harus boleh dipakai
        from services import warehouse_scope_service as whscope
        await whscope.assert_usable(payload.warehouse_id, so.get("entity_id", ""),
                                   action="menerima barang di sini",
                                   field_label="Gudang tujuan")
    est_price = payload.est_price if payload.est_price > 0 else float(ci.get("target_price", 0) or 0)
    pr_payload = PurchaseRequisitionCreate(
        items=[PurchaseRequisitionItem(
            product_id="",
            description=ci.get("description", f"Custom item {so.get('number')}"),
            quantity=float(ci.get("quantity", 1) or 1),
            unit=ci.get("unit", "meter"),
            est_price=est_price,
            note=ci.get("notes", ""),
        )],
        warehouse_id=payload.warehouse_id,
        entity_id=so.get("entity_id", ""),
        reason=f"Pengadaan untuk Special Order {so.get('number')} — {so.get('customer_name','')}",
        needed_by_date=payload.needed_by_date or so.get("expected_delivery", ""),
        source="special_order",
        source_ref_id=order_id,
        notes=payload.notes,
        submit_now=payload.submit_now,
    )
    try:
        pr = await pr_svc.create_requisition(pr_payload, created_by=user.get("name", "Admin"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.special_orders.update_one({"id": order_id}, {"$set": {
        "linked_pr_id": pr["id"], "linked_pr_number": pr["number"], "updated_at": now_iso()}})

    # Gerakkan ke in_production (purchasing started) bila masih confirmed
    if so["status"] == "confirmed":
        try:
            await transition_special_order_status(order_id, "in_production", user["email"])
        except ValueError:
            pass

    await audit(user.get("name", ""), "special_order_pr_created", "special_order", order_id,
                {"pr_number": pr["number"], "pr_id": pr["id"]})

    so_updated = await db.special_orders.find_one({"id": order_id}, {"_id": 0})
    return {"pr": pr, "special_order": safe_doc(so_updated)}


@router.post("/special-orders/{order_id}/create-sku")
async def create_sku_endpoint(order_id: str, request: Request) -> Dict[str, Any]:
    """F3 (2.a) — Materialisasi Product SKU dari Special Order MTO (idempotent).

    Otomatis dijalankan saat approve; endpoint ini adalah fallback manual
    (mis. special order lama yang dibuat sebelum fitur auto-create).
    """
    await require_permission(request, "order", "approve")
    user = await current_user(request)
    ctx = await entity_ctx(request)

    so = await db.special_orders.find_one({"id": order_id}, {"_id": 0})
    if not so:
        raise HTTPException(status_code=404, detail="Special order tidak ditemukan")
    assert_entity_access(so, "special_orders", ctx)

    try:
        product = await create_sku_from_special_order(
            order_id, created_by=user.get("email", user.get("name", "system")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await audit(user.get("name", ""), "special_order_sku_created", "special_order", order_id,
                {"product_id": product["id"], "sku": product["sku"]})
    so_updated = await db.special_orders.find_one({"id": order_id}, {"_id": 0})
    return {"product": product, "special_order": safe_doc(so_updated)}


@router.post("/special-orders/{order_id}/convert-to-so")
async def convert_special_order_to_so(order_id: str, request: Request) -> Dict[str, Any]:
    """F3 — Konversi Special Order (MTO) menjadi Sales Order standar.

    Menutup loop MTO: produk custom yang sudah punya SKU dimasukkan ke jalur
    fulfillment standar. Reuse penuh logika `create_order` (pricing/reservasi/
    credit gate). `allow_backorder=True` agar tidak gagal bila stok MTO belum
    tersedia. Idempotent: tolak bila sudah pernah dikonversi.
    """
    await require_permission(request, "order", "create")
    user = await current_user(request)
    ctx = await entity_ctx(request)

    so = await db.special_orders.find_one({"id": order_id}, {"_id": 0})
    if not so:
        raise HTTPException(status_code=404, detail="Special order tidak ditemukan")
    assert_entity_access(so, "special_orders", ctx)

    if so.get("linked_sales_order_id"):
        raise HTTPException(
            status_code=400,
            detail=f"Special order sudah dikonversi ke SO {so.get('linked_sales_order_number')}")
    if so.get("status") not in ("confirmed", "in_production", "ready"):
        raise HTTPException(
            status_code=400,
            detail="Konversi hanya untuk special order yang sudah disetujui (confirmed/in_production/ready).")

    # Pastikan SKU sudah ada (auto-create bila belum — mis. order lama sebelum fitur 2.a).
    if not so.get("linked_product_id"):
        try:
            await create_sku_from_special_order(
                order_id, created_by=user.get("email", "system"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        so = await db.special_orders.find_one({"id": order_id}, {"_id": 0})

    ci = so.get("custom_item", {}) or {}
    addr = so.get("shipping_address", {}) or {}
    so_payload = SalesOrderCreate(
        customer_id=so["customer_id"],
        shipping_address_id=addr.get("id", ""),
        items=[SalesOrderItemIn(
            product_id=so["linked_product_id"],
            quantity=float(ci.get("quantity", 1) or 1),
            unit=ci.get("unit", "meter"),
        )],
        entity_id=so.get("entity_id", ""),
        allow_backorder=True,         # MTO: stok mungkin belum tersedia → backorder
        confirm_mixed_lot=True,       # item custom tunggal — lewati gate mixed-lot
        source_special_order_id=order_id,
        sales_name=so.get("created_by", "Sales"),
    )

    # Reuse penuh create_order (local import → hindari circular import).
    from routers.sales_orders import create_order as _create_sales_order
    sales_order = await _create_sales_order(so_payload, request)

    await db.special_orders.update_one(
        {"id": order_id},
        {"$set": {
            "linked_sales_order_id": sales_order["id"],
            "linked_sales_order_number": sales_order["number"],
            "converted_at": now_iso(),
            "converted_by": user.get("email", user.get("name", "")),
            "updated_at": now_iso(),
        }})
    await audit(user.get("name", ""), "special_order_converted_to_so", "special_order", order_id,
                {"so_id": sales_order["id"], "so_number": sales_order["number"]})

    so_updated = await db.special_orders.find_one({"id": order_id}, {"_id": 0})
    return {"special_order": safe_doc(so_updated), "sales_order": sales_order}


@router.patch("/special-orders/{order_id}")

async def patch_special_order(
    order_id: str,
    payload: Dict[str, Any],
    request: Request
) -> Dict[str, Any]:
    """Partial update special order (draft only).
    
    Allowed fields: notes, expected_delivery, custom_item fields
    """
    await require_permission(request, "order", "update")
    user = await current_user(request)
    
    ctx = await entity_ctx(request)
    special_order = await db.special_orders.find_one({"id": order_id}, {"_id": 0})
    if not special_order:
        raise HTTPException(status_code=404, detail="Special order tidak ditemukan")
    assert_entity_access(special_order, "special_orders", ctx)  # S#074 IDOR
    if special_order["status"] != "draft":
        raise HTTPException(
            status_code=400,
            detail="Hanya special order dengan status draft yang dapat diedit"
        )
    
    # Allowed updates
    allowed_fields = ["notes", "expected_delivery"]
    updates = {k: v for k, v in payload.items() if k in allowed_fields}
    
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field yang dapat diupdate")
    
    updates["updated_at"] = now_iso()
    updates["updated_by"] = user["email"]
    
    result = await db.special_orders.find_one_and_update(
        {"id": order_id},
        {"$set": updates},
        return_document=True
    )
    
    result.pop("_id", None)
    return result


@router.delete("/special-orders/{order_id}")

async def delete_special_order(
    order_id: str,
    request: Request
) -> Dict[str, Any]:
    """Soft delete special order (draft only)."""
    await require_permission(request, "order", "delete")
    user = await current_user(request)
    
    special_order = await db.special_orders.find_one({"id": order_id}, {"_id": 0})
    if not special_order:
        raise HTTPException(status_code=404, detail="Special order tidak ditemukan")
    
    if special_order["status"] != "draft":
        raise HTTPException(
            status_code=400,
            detail="Hanya special order dengan status draft yang dapat dihapus"
        )
    
    result = await db.special_orders.find_one_and_update(
        {"id": order_id},
        {
            "$set": {
                "status": "cancelled",
                "cancelled_at": now_iso(),
                "cancelled_by": user["email"],
                "updated_at": now_iso()
            }
        },
        return_document=True
    )
    
    result.pop("_id", None)
    return result
