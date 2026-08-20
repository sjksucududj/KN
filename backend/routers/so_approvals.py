"""F5 — Unified Approval router untuk Sales Order.

Aksi approval terpusat (KEPUTUSAN OWNER §2.4): special_price + over-credit + nilai
disatukan ke SSOT `sales_orders.pending_approvals[]` + 1 inbox "Pusat Persetujuan".

Endpoint:
  POST /sales-orders/{id}/request-special-price     — sales ajukan harga khusus per item
  POST /sales-orders/{id}/request-credit-approval    — minta approval kredit (over-limit)
  POST /sales-orders/{id}/approvals/{aid}/decide      — approver putuskan (approve|reject)
  POST /sales-orders/{id}/approvals/{aid}/evidence    — unggah bukti (multipart)
  GET  /approvals/queue                                — inbox approver (flat lintas SO)

Koleksi detail tetap dipakai: price_approvals (pra_), credit_overrides (cro_).
Kontrak respons: list = ARRAY langsung; detail = objek langsung (tanpa envelope).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Query, Header
from fastapi.responses import Response
from pymongo import ReturnDocument

from db import db
from dependencies import require_permission, require_any_permission, audit
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID
from entity_scope import entity_ctx, resolve_list_scope, resolve_scope_ids, assert_entity_access
from schemas import SoSpecialPriceRequest, SoCreditApprovalRequest, SoApprovalDecision
from services import so_approvals, storage_service as storage
from services.config_service import compute_order_pricing
from services.so_status import stage_fields
# Reuse transisi + commit roll dari source service (tak ada import balik → aman).
from services.sales_order_helpers import so_transition as _transition
from services.roll_service import set_order_rolls_status

router = APIRouter(prefix="/api")

OPEN_STATES = {"reserved", "waiting_approval", "waiting_stock", "draft"}


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _load_so(order_id: str, ctx) -> Dict[str, Any]:
    order = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")
    assert_entity_access(order, "sales_orders", ctx)
    return order


def _find_entry(order: Dict[str, Any], approval_id: str) -> Optional[Dict[str, Any]]:
    for p in (order.get("pending_approvals") or []):
        if p.get("id") == approval_id:
            return p
    return None


async def _persist_pending(order_id: str, pa: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Simpan pending_approvals + sinkronkan approval_required/role + stage."""
    order = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    order["pending_approvals"] = pa
    afields = so_approvals.approval_fields(order, require_validation=False)
    sset = {"pending_approvals": pa, "updated_at": now_iso(), **afields}
    sset.update(stage_fields(order))
    updated = await db.sales_orders.find_one_and_update(
        {"id": order_id}, {"$set": sset},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    return safe_doc(updated)


async def _recompute_so_totals(order: Dict[str, Any]) -> None:
    """F5 — recompute pricing SO setelah harga item berubah (INVARIAN-SAFE)."""
    pricing = await compute_order_pricing(
        order.get("items", []), order.get("entity_id"),
        order.get("order_discount_percent", 0) or 0)
    await db.sales_orders.update_one({"id": order["id"]}, {"$set": {
        "items": pricing["items"], "total_amount": pricing["total_amount"],
        "items_discount_total": pricing["items_discount_total"],
        "order_discount_amount": pricing["order_discount_amount"],
        "discount_total": pricing["discount_total"], "net_subtotal": pricing["net_subtotal"],
        "dpp": pricing["dpp"], "dpp_nilai_lain": pricing.get("dpp_nilai_lain", False),
        "effective_rate": pricing.get("effective_rate", pricing["ppn_rate"]),
        "ppn_amount": pricing["ppn_amount"],
        "grand_total": pricing["grand_total"], "approval_amount": pricing["grand_total"],
        "updated_at": now_iso(),
    }})


# ─── Sales: ajukan harga khusus (aksi di DETAIL SO) ──────────────────────────

@router.post("/sales-orders/{order_id}/request-special-price")
async def request_special_price(order_id: str, payload: SoSpecialPriceRequest, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "order", "update")
    ctx = await entity_ctx(request)
    order = await _load_so(order_id, ctx)
    if order.get("status") not in OPEN_STATES:
        raise HTTPException(status_code=409, detail={
            "code": "SO_LOCKED",
            "message": "Harga khusus hanya bisa diajukan sebelum pesanan disetujui (tahap Dipesan)."})
    if not (payload.reason or "").strip():
        raise HTTPException(status_code=400, detail="Alasan WAJIB diisi untuk pengajuan harga khusus.")
    items = order.get("items", [])
    idx = payload.item_index
    if idx is None and payload.product_id:
        idx = next((i for i, it in enumerate(items) if it.get("product_id") == payload.product_id), None)
    if idx is None or idx < 0 or idx >= len(items):
        raise HTTPException(status_code=400, detail="Item tidak ditemukan pada pesanan.")
    item = items[idx]
    normal_price = float(item.get("price", 0) or 0)
    req_price = float(payload.requested_price or 0)
    if req_price <= 0:
        raise HTTPException(status_code=400, detail="Harga khusus harus lebih dari 0.")
    # Dokumen detail price_approvals (pra_) tertaut SO.
    pra_id = new_id("pra")
    await db.price_approvals.insert_one({
        "id": pra_id, "customer_id": order.get("customer_id"), "customer_name": order.get("customer_name"),
        "product_id": item.get("product_id"), "product_name": item.get("product_name"),
        "normal_price": normal_price, "requested_price": req_price,
        "min_quantity": float(payload.min_quantity or 0), "valid_until": "",
        "reason": payload.reason.strip(), "entity_id": order.get("entity_id", DEFAULT_ENTITY_ID),
        "status": "pending", "so_id": order_id, "so_item_index": idx,
        "attachments": [], "requested_by": actor["name"], "requested_by_id": actor["id"],
        "created_at": now_iso(), "updated_at": now_iso(),
    })
    entry = so_approvals.make_approval(
        "special_price", required_role="manager", reason=payload.reason.strip(),
        requested_by=actor["name"], requested_by_id=actor["id"], ref_id=pra_id,
        item_index=idx, product_id=item.get("product_id"), product_name=item.get("product_name"),
        normal_price=normal_price, requested_price=req_price)
    pa = list(order.get("pending_approvals") or []) + [entry]
    result = await _persist_pending(order_id, pa)
    await audit(actor["name"], "so_special_price_requested", "sales_order", order_id,
                {"product": item.get("product_name"), "normal": normal_price, "requested": req_price})
    return result


# ─── Sales: minta approval kredit (over-limit) ───────────────────────────────

@router.post("/sales-orders/{order_id}/request-credit-approval")
async def request_credit_approval(order_id: str, payload: SoCreditApprovalRequest, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "order", "update")
    ctx = await entity_ctx(request)
    order = await _load_so(order_id, ctx)
    if order.get("status") not in OPEN_STATES:
        raise HTTPException(status_code=409, detail={
            "code": "SO_LOCKED", "message": "Persetujuan kredit hanya relevan sebelum pesanan disetujui."})
    pa = list(order.get("pending_approvals") or [])
    # Cegah duplikat: bila sudah ada entri kredit pending → kembalikan apa adanya.
    if any(p.get("type") == "kredit" and p.get("status") == "pending" for p in pa):
        raise HTTPException(status_code=409, detail="Sudah ada permintaan approval kredit yang menunggu.")
    amount = float(order.get("grand_total", 0) or 0)
    cro_id = new_id("cro")
    await db.credit_overrides.insert_one({
        "id": cro_id, "customer_id": order.get("customer_id"), "customer_name": order.get("customer_name"),
        "order_id": order_id, "order_number": order.get("number"), "amount": amount,
        "reason": (payload.reason or "").strip() or "Permintaan approval kredit (over-limit).",
        "evidence_url": "", "entity_id": order.get("entity_id", DEFAULT_ENTITY_ID),
        "status": "pending", "requested_by": actor["name"], "requested_by_id": actor["id"],
        "created_at": now_iso(),
    })
    pa.append(so_approvals.make_approval(
        "kredit", required_role="manager", reason=(payload.reason or "").strip() or "Over-limit kredit.",
        requested_by=actor["name"], requested_by_id=actor["id"], ref_id=cro_id, amount=amount))
    result = await _persist_pending(order_id, pa)
    await db.sales_orders.update_one({"id": order_id}, {"$set": {"credit_hold": True}})
    await audit(actor["name"], "so_credit_approval_requested", "sales_order", order_id, {"amount": amount})
    return safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))


# ─── Approver: keputusan atas 1 entri (approve | reject) ─────────────────────

@router.post("/sales-orders/{order_id}/approvals/{approval_id}/decide")
async def decide_approval(order_id: str, approval_id: str, payload: SoApprovalDecision, request: Request) -> Dict[str, Any]:
    # RBAC — keputusan approval butuh order.approve (sales TIDAK punya → 403).
    actor = await require_permission(request, "order", "approve")
    ctx = await entity_ctx(request)
    order = await _load_so(order_id, ctx)
    decision = (payload.decision or "").strip().lower()
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision harus 'approve' atau 'reject'.")
    pa = list(order.get("pending_approvals") or [])
    entry = next((p for p in pa if p.get("id") == approval_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Entri approval tidak ditemukan.")
    if entry.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Entri approval sudah diputuskan.")
    # role aktor harus memenuhi required_role entri
    from services.config_service import role_satisfies
    if not role_satisfies(actor.get("role"), entry.get("required_role")):
        raise HTTPException(status_code=403,
            detail=f"Keputusan butuh role minimal '{entry.get('required_role')}'.")
    new_status = "approved" if decision == "approve" else "rejected"
    entry.update({"status": new_status, "decided_by": actor["name"], "decided_by_id": actor["id"],
                  "decided_at": now_iso(), "decision_notes": (payload.notes or "").strip()})
    atype = entry.get("type")

    # Efek samping per tipe (mirror ke dokumen detail).
    if atype == "special_price":
        await db.price_approvals.update_one({"id": entry.get("ref_id")}, {"$set": {
            "status": new_status, "decided_by": actor["name"], "decided_by_id": actor["id"],
            "decision_notes": (payload.notes or "").strip(), "decided_at": now_iso(), "updated_at": now_iso()}})
        if new_status == "approved":
            items = order.get("items", [])
            idx = entry.get("item_index")
            if isinstance(idx, int) and 0 <= idx < len(items):
                items[idx]["price"] = float(entry.get("requested_price") or items[idx].get("price"))
                items[idx]["special_price_id"] = entry.get("ref_id")
                await db.sales_orders.update_one({"id": order_id}, {"$set": {"items": items}})
                order["items"] = items
                await _recompute_so_totals(order)
    elif atype == "kredit":
        ref = entry.get("ref_id")
        if ref:
            await db.credit_overrides.update_one({"id": ref}, {"$set": {
                "status": new_status, "decided_by": actor["name"], "decided_by_id": actor["id"],
                "decision_reason": (payload.notes or "").strip(), "decided_at": now_iso(),
                **({"consumed": True, "consumed_order_id": order_id, "consumed_at": now_iso()} if new_status == "approved" else {})}})
        if new_status == "approved":
            await db.sales_orders.update_one({"id": order_id}, {"$set": {"credit_hold": False, "credit_override_id": ref or ""}})

    result = await _persist_pending(order_id, pa)
    # F5 — bila SEMUA approved → SO otomatis naik ke Approved + commit roll.
    if new_status == "approved" and so_approvals.all_approved(result):
        if result.get("status") in ("reserved", "waiting_approval", "waiting_stock"):
            result = await _transition(order_id, ["reserved", "waiting_approval", "waiting_stock"],
                                       "approved", actor["name"], "order_approved", {"approved_by": actor["name"]})
            await set_order_rolls_status(order_id, "committed")
    await audit(actor["name"], f"so_approval_{new_status}", "sales_order", order_id,
                {"type": atype, "approval_id": approval_id, "notes": (payload.notes or "").strip()})
    return safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))


# ─── Unggah bukti untuk 1 entri approval ─────────────────────────────────────

@router.post("/sales-orders/{order_id}/approvals/{approval_id}/evidence")
async def upload_evidence(order_id: str, approval_id: str, request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    actor = await require_permission(request, "order", "update")
    ctx = await entity_ctx(request)
    order = await _load_so(order_id, ctx)
    entry = _find_entry(order, approval_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entri approval tidak ditemukan.")
    data = await file.read()
    try:
        content_type = storage.validate_upload(file.filename, file.content_type, len(data))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    path = storage.build_path(f"so_approvals/{order_id}/{approval_id}", storage.ext_of(file.filename))
    try:
        res = await storage.put_object(path, data, content_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gagal mengunggah file: {e}")
    att = {
        "id": new_id("att"), "storage_path": res.get("path", path), "original_filename": file.filename,
        "content_type": content_type, "size": res.get("size", len(data)),
        "uploaded_by": actor["name"], "uploaded_at": now_iso(), "is_deleted": False,
    }
    pa = list(order.get("pending_approvals") or [])
    for p in pa:
        if p.get("id") == approval_id:
            p["evidence"] = (p.get("evidence") or []) + [att]
            # mirror ke dokumen detail bila ada
            if p.get("ref_id"):
                coll = db.price_approvals if p.get("type") == "special_price" else db.credit_overrides
                await coll.update_one({"id": p["ref_id"]}, {"$push": {"attachments": att}, "$set": {"updated_at": now_iso()}})
            break
    await _persist_pending(order_id, pa)
    await audit(actor["name"], "so_approval_evidence_added", "sales_order", order_id,
                {"approval_id": approval_id, "file": file.filename})
    return att


# ─── Unduh bukti (inline; dukung query-param auth utk <img>/<a>) ─────────────

@router.get("/sales-orders/{order_id}/approvals/{approval_id}/evidence/{att_id}/download")
async def download_evidence(
    order_id: str, approval_id: str, att_id: str, request: Request,
    auth: str = Query(None), authorization: str = Header(None),
):
    # <img>/<a> tak bisa kirim header → terima token via query-param `auth`.
    if not authorization and auth:
        request.scope["headers"] = list(request.scope.get("headers", [])) + [
            (b"authorization", f"Bearer {auth}".encode())
        ]
    await require_permission(request, "order", "view")
    ctx = await entity_ctx(request)
    order = await _load_so(order_id, ctx)
    entry = _find_entry(order, approval_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entri approval tidak ditemukan.")
    att = next((a for a in (entry.get("evidence") or []) if a.get("id") == att_id and not a.get("is_deleted")), None)
    if not att:
        raise HTTPException(status_code=404, detail="Lampiran tidak ditemukan.")
    try:
        content, ctype = await storage.get_object(att["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gagal mengambil file: {e}")
    return Response(
        content=content, media_type=att.get("content_type", ctype),
        headers={"Content-Disposition": f'inline; filename="{att.get("original_filename", "file")}"'},
    )


# ─── Ringkasan SELURUH antrean keputusan (satu pintu yang jujur) ─────────────

@router.get("/approvals/backlog")
async def approvals_backlog(request: Request, entity_id: str = None,
                            oldest: int = 0) -> Dict[str, Any]:
    """Berapa yang menunggu keputusan — LINTAS SEMUA jenis, dari satu sumber.

    KENAPA ADA (terukur 2026-08-15): layar "Pusat Persetujuan" menghitung antreannya
    di BROWSER dari 7 permintaan terpisah, sementara KPI beranda memakai sumber lain
    lagi. Hasilnya tiga angka berbeda untuk satu pertanyaan yang sama — dan yang di
    beranda bahkan selalu 0. Endpoint ini memberi angka yang SAMA dengan KPI beranda
    (`services/approval_backlog_service.py`), termasuk antrean yang layar ini sendiri
    tidak menampilkan (PR, spesifikasi/sample, pesanan khusus → tab "Persetujuan
    Saya"; transaksi antar-PT di atas ambang → layar Antar Entitas). Dengan begitu
    Pusat Persetujuan berhenti mengaku "tidak ada apa-apa" untuk pekerjaan yang
    sebenarnya menumpuk di tab sebelah.

    Izin: MEMBACA antrean ≠ MEMUTUSKAN (`approval.view` cukup — Admin Sales yang
    tugasnya mengejar persetujuan nyangkut ikut boleh melihat).
    """
    await require_any_permission(request, [("order", "approve"), ("approval", "view")])
    ctx = await entity_ctx(request)
    from services import approval_backlog_service as abl
    # Mode "Semua Entitas" → tanpa saringan (angka gabungan, sama dengan KPI beranda).
    # Selain itu: hanya badan usaha yang memang ditugaskan ke pengguna ini.
    ids = resolve_scope_ids(ctx, entity_id)
    if getattr(ctx, "view_all", False) and not entity_id:
        scope = None
    else:
        scope = ids[0] if len(ids) == 1 else {"$in": ids}
    # `?oldest=N` → sekalian bawa N dokumen yang PALING LAMA menunggu (umur tunggu),
    # supaya layar bisa menyebut "PO-00010 — menunggu 12 hari", bukan cuma angka.
    n = max(0, min(int(oldest or 0), 25))
    return await abl.backlog(scope, with_oldest=bool(n), oldest_limit=n or 5)


# ─── Inbox approver: antrian persetujuan (flat lintas SO, entity-scoped) ──────

@router.get("/approvals/queue")
async def approvals_queue(request: Request, type: str = None, entity_id: str = None) -> List[Dict[str, Any]]:
    # BACAAN antrean ≠ MEMUTUSKAN. Dulu hanya `order.approve` yang boleh membaca,
    # sehingga Admin Sales — yang tugasnya justru MENGEJAR persetujuan yang nyangkut —
    # membuka "Pusat Persetujuan" dan mendapat 403 (menu ada, isinya dinding).
    # Keputusan pemilik E8.1b memberi peran itu `approval: ["view"]`; di sini izin itu
    # akhirnya berlaku. Tombol keputusan tetap dijaga endpoint approve/reject.
    await require_any_permission(request, [("order", "approve"), ("approval", "view")])
    ctx = await entity_ctx(request)
    query = resolve_list_scope("sales_orders", {"pending_approvals.status": "pending"}, ctx, entity_id)
    orders = await db.sales_orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(300)
    out: List[Dict[str, Any]] = []
    for o in orders:
        for p in (o.get("pending_approvals") or []):
            if p.get("status") != "pending":
                continue
            if type and p.get("type") != type:
                continue
            out.append({
                **{k: p.get(k) for k in ("id", "type", "required_role", "reason", "requested_by",
                                          "requested_at", "amount", "product_name", "normal_price",
                                          "requested_price", "item_index", "ref_id")},
                "type_label": so_approvals.TYPE_LABELS.get(p.get("type"), p.get("type")),
                "evidence": [a for a in (p.get("evidence") or []) if not a.get("is_deleted")],
                "order_id": o.get("id"), "order_number": o.get("number"),
                "customer_name": o.get("customer_name"), "entity_id": o.get("entity_id"),
                "grand_total": o.get("grand_total"), "order_status": o.get("status"),
                "stage": o.get("stage"),
            })
    return out
