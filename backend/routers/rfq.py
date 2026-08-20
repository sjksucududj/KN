"""RFQ / Quotation router — Fase 6.1 (P1 Sourcing).

Koleksi kanonik: `rfqs` (prefix rfq_, nomor RFQ-NNNNN).
Alur: create (PR/manual) → send → quote (per supplier) → compare → award → PO.
Status: draft → open → awarded | cancelled.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from db import db
from services import dual_qty_service as _dual  # FASE U — dua satuan (roll + ukuran)
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc, timeline_entry, rupiah
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas import RFQCreate, RFQQuoteSubmit, RFQAward, RFQDecision
from services.rfq_service import (
    next_rfq_number, build_items_from_products, build_suppliers, build_compare,
    supplier_total, award_rfq, OPEN_STATUSES,
)

router = APIRouter(prefix="/api")


async def _get(rfq_id: str) -> Dict[str, Any]:
    d = safe_doc(await db.rfqs.find_one({"id": rfq_id}, {"_id": 0}))
    if not d:
        raise HTTPException(status_code=404, detail="RFQ tidak ditemukan")
    return d


@router.get("/rfqs")
async def list_rfqs(request: Request, entity_id: str = None, status: str = None) -> List[Dict[str, Any]]:
    await require_permission(request, "rfq", "view")
    ctx = await entity_ctx(request)
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    q = resolve_list_scope("rfqs", q, ctx, entity_id)
    docs = await db.rfqs.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [safe_doc(d) for d in docs]


@router.get("/rfqs/{rfq_id}")
async def get_rfq(rfq_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "rfq", "view")
    ctx = await entity_ctx(request)
    rfq = await _get(rfq_id)
    assert_entity_access(rfq, "rfqs", ctx)
    return rfq


@router.get("/rfqs/{rfq_id}/compare")
async def compare_rfq(rfq_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "rfq", "view")
    return build_compare(await _get(rfq_id))


@router.post("/rfqs")
async def create_rfq(payload: RFQCreate, request: Request) -> Dict[str, Any]:
    """Buat RFQ dari PR approved (tarik item) atau standalone manual."""
    actor = await require_permission(request, "rfq", "create")
    ctx = await entity_ctx(request)
    entity_id = payload.entity_id or ctx.active_entity_id
    pr_id, pr_number = "", ""
    raw_items = [it.dict() for it in payload.items]

    if payload.source == "pr":
        if not payload.pr_id:
            raise HTTPException(status_code=400, detail="pr_id wajib untuk sumber PR")
        pr = await db.purchase_requisitions.find_one({"id": payload.pr_id}, {"_id": 0})
        if not pr:
            raise HTTPException(status_code=404, detail="PR tidak ditemukan")
        if pr.get("status") != "approved":
            raise HTTPException(status_code=400, detail=f"Hanya PR approved (status: {pr.get('status')})")
        if any(not it.get("product_id") for it in pr.get("items", [])):
            raise HTTPException(status_code=400, detail="PR berisi item non-katalog — tak bisa jadi RFQ otomatis.")
        # FASE U — dua satuan ikut turun dari PR (rencana jumlah roll tidak hilang di RFQ).
        raw_items = [{"product_id": it["product_id"], "quantity": it["quantity"],
                      "unit": it.get("unit", "meter"), "note": it.get("notes", ""),
                      "qty_rolls": it.get("qty_rolls"),
                      **({"unit_factor": it["unit_factor"],
                          "unit_factor_to": it.get("unit_factor_to", "")}
                         if it.get("unit_factor") else {})} for it in pr["items"]]
        pr_id, pr_number = pr["id"], pr["number"]
        entity_id = pr.get("entity_id") or entity_id

    if not raw_items:
        raise HTTPException(status_code=400, detail="Minimal 1 item dibutuhkan")
    if not payload.warehouse_id:
        raise HTTPException(status_code=400, detail="Gudang tujuan wajib dipilih")
    # E4.1 — gudang tujuan penerimaan harus boleh dipakai badan usaha ini.
    from services import warehouse_scope_service as whscope
    warehouse = await whscope.assert_usable(payload.warehouse_id, entity_id,
                                           action="menerima barang di sini",
                                           field_label="Gudang tujuan")

    try:
        items = await build_items_from_products(raw_items)
        suppliers = await build_suppliers(payload.supplier_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    now = now_iso()
    actor_name = payload.created_by or actor.get("name", "Admin")
    doc = {
        "id": new_id("rfq"), "rfq_number": await next_rfq_number(),
        "title": payload.title or (f"RFQ dari {pr_number}" if pr_number else "RFQ Pengadaan"),
        "entity_id": entity_id, "source": payload.source,
        "pr_id": pr_id, "pr_number": pr_number,
        "warehouse_id": warehouse["id"], "warehouse_name": warehouse.get("name", ""),
        "status": "draft", "items": items, "suppliers": suppliers,
        "needed_by_date": payload.needed_by_date or "", "due_date": payload.due_date or "",
        "notes": payload.notes or "", "award": {},
        "timeline": [timeline_entry("created", "RFQ dibuat",
                     actor_name, f"{len(items)} item · {len(suppliers)} supplier diundang")],
        "created_by": actor_name, "created_by_id": actor.get("id", ""),
        "created_at": now, "updated_at": now,
    }
    from services import line_scope as _lines            # FASE L
    await _lines.stamp_doc(db, doc)
    await db.rfqs.insert_one(doc)
    await audit(actor["name"], "rfq_created", "rfq", doc["id"],
                {"number": doc["rfq_number"], "items": len(items), "suppliers": len(suppliers)})
    return safe_doc(doc)


@router.post("/rfqs/{rfq_id}/send")
async def send_rfq(rfq_id: str, request: Request) -> Dict[str, Any]:
    """draft → open (penawaran mulai dikumpulkan)."""
    actor = await require_permission(request, "rfq", "update")
    rfq = await _get(rfq_id)
    if rfq["status"] != "draft":
        raise HTTPException(status_code=400, detail=f"Hanya RFQ draft yang bisa dikirim (status: {rfq['status']})")
    await db.rfqs.update_one({"id": rfq_id}, {
        "$set": {"status": "open", "updated_at": now_iso()},
        "$push": {"timeline": timeline_entry("open", "RFQ dikirim ke supplier", actor["name"],
                  f"{len(rfq.get('suppliers', []))} supplier")}})
    return await _get(rfq_id)


@router.post("/rfqs/{rfq_id}/quote")
async def submit_quote(rfq_id: str, payload: RFQQuoteSubmit, request: Request) -> Dict[str, Any]:
    """Input penawaran 1 supplier (harga per baris). RFQ draft otomatis → open."""
    actor = await require_permission(request, "rfq", "update")
    rfq = await _get(rfq_id)
    if rfq["status"] not in OPEN_STATUSES:
        raise HTTPException(status_code=400, detail=f"RFQ {rfq['status']} tidak menerima penawaran")
    sup = next((s for s in rfq.get("suppliers", []) if s["supplier_id"] == payload.supplier_id), None)
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier tidak diundang pada RFQ ini")

    valid_lines = {it["line_id"] for it in rfq.get("items", [])}
    lines = []
    for ln in payload.lines:
        if ln.line_id not in valid_lines:
            raise HTTPException(status_code=400, detail=f"line_id {ln.line_id} tidak ada di RFQ")
        lines.append({"line_id": ln.line_id, "price": round(float(ln.price or 0), 2),
                      "available": bool(ln.available), "note": ln.note or ""})
    if not any(l["available"] and l["price"] > 0 for l in lines):
        raise HTTPException(status_code=400, detail="Minimal 1 baris dengan harga > 0")

    sup.update({"lines": lines, "valid_until": payload.valid_until or "",
                "lead_time_days": int(payload.lead_time_days or 0), "note": payload.note or "",
                "quote_status": "quoted", "quoted_at": now_iso()})
    sup["total"] = supplier_total(rfq, sup)
    new_status = "open" if rfq["status"] == "draft" else rfq["status"]
    await db.rfqs.update_one({"id": rfq_id}, {
        "$set": {"suppliers": rfq["suppliers"], "status": new_status, "updated_at": now_iso()},
        "$push": {"timeline": timeline_entry("quoted", f"Penawaran {sup['supplier_name']} masuk",
                  actor["name"], f"Total {rupiah(sup['total'])}")}})
    await audit(actor["name"], "rfq_quoted", "rfq", rfq_id,
                {"supplier": sup["supplier_name"], "total": sup["total"]})
    return await _get(rfq_id)


@router.post("/rfqs/{rfq_id}/award")
async def award(rfq_id: str, payload: RFQAward, request: Request) -> Dict[str, Any]:
    """Award RFQ → buat PO (full / per-baris) + upsert supplier price-list."""
    actor = await require_permission(request, "rfq", "award")
    rfq = await _get(rfq_id)
    if rfq["status"] == "awarded":
        raise HTTPException(status_code=409, detail="RFQ sudah di-award.")
    if rfq["status"] != "open":
        raise HTTPException(status_code=400, detail=f"Hanya RFQ open yang bisa di-award (status: {rfq['status']})")
    if not any(s.get("quote_status") == "quoted" for s in rfq.get("suppliers", [])):
        raise HTTPException(status_code=400, detail="Belum ada penawaran masuk")
    try:
        result = await award_rfq(rfq, payload.mode, payload.full_supplier_id or "",
                                 [la.dict() for la in (payload.line_awards or [])], actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "rfq_awarded", "rfq", rfq_id,
                {"mode": payload.mode, "pos": result["rfq"].get("award", {}).get("po_numbers", [])})
    return result


@router.post("/rfqs/{rfq_id}/cancel")
async def cancel_rfq(rfq_id: str, payload: RFQDecision, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "rfq", "update")
    rfq = await _get(rfq_id)
    if rfq["status"] in ("awarded", "cancelled"):
        raise HTTPException(status_code=409, detail=f"RFQ sudah {rfq['status']}.")
    await db.rfqs.update_one({"id": rfq_id}, {
        "$set": {"status": "cancelled", "cancel_reason": (payload.reason or "").strip(),
                 "updated_at": now_iso()},
        "$push": {"timeline": timeline_entry("cancelled", "RFQ dibatalkan", actor["name"],
                  (payload.reason or "").strip())}})
    await audit(actor["name"], "rfq_cancelled", "rfq", rfq_id, {"reason": payload.reason})
    return await _get(rfq_id)
