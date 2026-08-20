"""Price Approvals router (Sub-fase 1.7) — Special Price / Approval Harga.

Alur: Sales mengajukan harga khusus (nego) per customer+product → upload bukti
(opsional) → manager/admin approve/reject. Harga yang DISETUJUI & masih berlaku
dapat dipakai saat membuat SO (override harga normal). Invarian akuntansi tetap:
item.subtotal = price × quantity (price = harga khusus yang disetujui).

Koleksi: price_approvals (prefix pra_) — terdaftar L0 di ENTITY_REGISTRY.
Kontrak respons: list = ARRAY langsung, detail = objek langsung (tanpa envelope).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Query, Header
from fastapi.responses import Response
from pymongo import ReturnDocument

from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID, rupiah
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas import PriceApprovalCreate, PriceApprovalDecision, GenericPatch
from services import storage_service as storage
from services.notification_service import create_notification
# F1b — bagian BERSAMA alur harga khusus (bentuk dokumen, keberlakuan, efek keputusan)
# dipakai juga oleh Daftar Harga per Pelanggan supaya tidak ada dua definisi.
from services import approval_matrix_service as matrix
from services import price_approval_service as pas
from services import price_guard_service as guard

router = APIRouter(prefix="/api")

EDITABLE_STATUSES = pas.EDITABLE_STATUSES
DECIDABLE_STATUSES = pas.DECIDABLE_STATUSES


# ─── Helpers ─────────────────────────────────────────────────────────────────
# Definisi tanggal / keberlakuan / field turunan hidup di `price_approval_service`
# (SATU sumber). Alias di bawah menjaga pemanggilan lama di berkas ini tetap jalan.
_norm_until = pas.norm_until
_is_active_approval = pas.is_active
_decorate = pas.decorate


async def _resolve_entity(payload_entity: str, customer: Dict[str, Any]) -> str:
    eid = (payload_entity or "").strip()
    if eid:
        return eid
    return customer.get("entity_id") or DEFAULT_ENTITY_ID


def _is_active_approval_legacy(r: Dict[str, Any], now: str) -> bool:
    """Dipertahankan hanya sebagai dokumentasi bentuk lama; pemakai memakai alias
    `_is_active_approval` → `price_approval_service.is_active`."""
    return pas.is_active(r, now)


async def get_effective_special_price(
    entity_id: str, customer_id: str, product_id: str,
    quantity: Optional[float] = None, approval_id: str = "",
) -> Optional[Dict[str, Any]]:
    """Cari price_approval DISETUJUI & berlaku untuk (entity, customer, product).
    Dipakai oleh sales_orders saat membuat SO. None bila tidak ada/expired/qty<min."""
    q: Dict[str, Any] = {"customer_id": customer_id, "product_id": product_id, "status": "approved"}
    if entity_id:
        q["entity_id"] = entity_id
    if approval_id:
        q["id"] = approval_id
    else:
        # Aturan STANDING saja yang berlaku lintas order via /effective.
        # Harga khusus scope "order" terikat SO tertentu (tak boleh bocor ke order lain).
        q["scope"] = {"$ne": "order"}
        # F1b — pengajuan yang lahir dari Daftar Harga per Pelanggan bukan aturan
        # tersendiri (hanya jejak keputusan record harga langganan) → jangan dihitung
        # dua kali; harga langganannya sudah dipakai resolver customer_price_service.
        q["$or"] = [{"customer_price_id": {"$exists": False}}, {"customer_price_id": ""},
                    {"customer_price_id": None}]
    rows = await db.price_approvals.find(q, {"_id": 0}).sort("decided_at", -1).to_list(50)
    now = now_iso()
    for r in rows:
        if not _is_active_approval(r, now):
            continue
        if quantity is not None and float(quantity) < float(r.get("min_quantity", 0) or 0):
            continue
        return r
    return None


async def _get_or_404(approval_id: str) -> Dict[str, Any]:
    doc = safe_doc(await db.price_approvals.find_one({"id": approval_id}, {"_id": 0}))
    if not doc:
        raise HTTPException(status_code=404, detail="Pengajuan harga tidak ditemukan")
    return doc


def _ensure_owner_or_privileged(doc: Dict[str, Any], user: Dict[str, Any]) -> None:
    role = user.get("role")
    if role in ("admin", "manager"):
        return
    if doc.get("requested_by") != user.get("id"):
        raise HTTPException(status_code=403, detail="Anda hanya dapat mengelola pengajuan Anda sendiri")


# ─── List & lookup (specific routes BEFORE /{id}) ────────────────────────────

@router.get("/price-approvals")
async def list_price_approvals(
    request: Request, status: str = None, customer_id: str = None,
    product_id: str = None, entity_id: str = None,
) -> List[Dict[str, Any]]:
    user = await require_permission(request, "price_approval", "view")
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if customer_id:
        query["customer_id"] = customer_id
    if product_id:
        query["product_id"] = product_id
    query = resolve_list_scope("price_approvals", query, ctx, entity_id)
    # Row-level: sales hanya melihat pengajuannya sendiri
    if user.get("role") == "sales":
        query["requested_by"] = user.get("id")
    rows = await db.price_approvals.find(query, {"_id": 0}).sort("created_at", -1).to_list(300)
    return [_decorate(safe_doc(r)) for r in rows]


@router.get("/price-approvals/effective")
async def effective_price(
    request: Request, customer_id: str = Query(...), product_id: str = Query(...),
    entity_id: str = "", quantity: float = None,
) -> Dict[str, Any]:
    """Harga khusus efektif (disetujui & berlaku) untuk POS. Kembalikan objek
    {has_special, ...} — selalu objek (bukan 404) agar mudah dikonsumsi FE."""
    await require_permission(request, "price_approval", "view")
    eid = (entity_id or "").strip()
    if not eid:
        cust = await db.customers.find_one({"id": customer_id}, {"_id": 0, "entity_id": 1})
        eid = (cust or {}).get("entity_id") or DEFAULT_ENTITY_ID
    appr = await get_effective_special_price(eid, customer_id, product_id, quantity)
    if not appr:
        return {"has_special": False}
    return {
        "has_special": True,
        "price_approval_id": appr["id"],
        "requested_price": float(appr["requested_price"]),
        "normal_price": float(appr.get("normal_price", 0) or 0),
        "min_quantity": float(appr.get("min_quantity", 0) or 0),
        "valid_until": appr.get("valid_until", ""),
    }


@router.get("/price-approvals/stats/summary")
async def price_approval_stats(request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "price_approval", "view")
    base: Dict[str, Any] = {}
    if user.get("role") == "sales":
        base["requested_by"] = user.get("id")
    pipeline = [{"$match": base}] if base else []
    pipeline.append({"$group": {"_id": "$status", "count": {"$sum": 1}}})
    rows = await db.price_approvals.aggregate(pipeline).to_list(50)
    by_status = {r["_id"]: r["count"] for r in rows}
    return {
        "by_status": by_status,
        "pending": by_status.get("pending", 0),
        "total": sum(by_status.values()),
    }


# ─── Create ──────────────────────────────────────────────────────────────────

@router.post("/price-approvals")
async def create_price_approval(payload: PriceApprovalCreate, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "price_approval", "create")
    customer = safe_doc(await db.customers.find_one({"id": payload.customer_id}, {"_id": 0}))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    product = safe_doc(await db.products.find_one({"id": payload.product_id}, {"_id": 0}))
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    req_price = round(float(payload.requested_price or 0), 2)
    if req_price <= 0:
        raise HTTPException(status_code=400, detail="Harga khusus harus lebih dari 0")
    entity_id = await _resolve_entity(payload.entity_id, customer)
    status = "pending" if payload.submit_now else "draft"
    # F1b — SATU penilaian "harga terlalu murah" (harga PT / HPP), sama seperti yang
    # dipakai Daftar Harga per Pelanggan. Disimpan sebagai snapshot supaya approver
    # melihat angka pembanding yang sama dengan pengaju.
    verdict = await guard.evaluate(req_price, entity_id, product)
    doc = pas.build_doc(
        customer=customer, product=product, entity_id=entity_id,
        requested_price=req_price, requester=user,
        min_quantity=payload.min_quantity or 0, reason=payload.reason or "",
        valid_until=payload.valid_until or "", status=status,
        scope=payload.scope or pas.SCOPE_STANDING, so_id=payload.so_id or "",
        override=bool(payload.override), source=pas.SOURCE_SALES,
        extra={"guard": {k: verdict.get(k) for k in
                         ("floor", "floor_from", "threshold", "basis", "basis_label",
                          "entity_reference", "has_entity_price", "hpp", "global_price",
                          "below_floor", "gap", "gap_pct", "margin_pct", "reasons",
                          "summary", "tolerance_pct", "guard_on")}},
    )
    await pas.insert(doc)
    if status == "pending":
        await pas.notify_pending(doc, why=(verdict.get("summary") or ""))
    await audit(user.get("name", ""), "price_approval_created", "price_approval", doc["id"], {
        "customer": doc["customer_name"], "product": doc["product_name"],
        "normal_price": doc["normal_price"], "requested_price": req_price, "status": status,
        "scope": doc["scope"], "override": bool(payload.override),
        "below_floor": bool(verdict.get("below_floor")),
    })
    return _decorate(safe_doc(doc))


# ─── Detail / Patch / Delete ─────────────────────────────────────────────────

@router.get("/price-approvals/{approval_id}")
async def get_price_approval(approval_id: str, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "price_approval", "view")
    ctx = await entity_ctx(request)
    doc = await _get_or_404(approval_id)
    assert_entity_access(doc, "price_approvals", ctx)
    _ensure_owner_or_privileged(doc, user)
    return _decorate(doc)


@router.patch("/price-approvals/{approval_id}")
async def patch_price_approval(approval_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "price_approval", "update")
    doc = await _get_or_404(approval_id)
    _ensure_owner_or_privileged(doc, user)
    if doc["status"] not in EDITABLE_STATUSES:
        raise HTTPException(status_code=409, detail=f"Pengajuan status '{doc['status']}' tidak dapat diubah")
    allowed = {"requested_price", "min_quantity", "reason", "valid_until"}
    data: Dict[str, Any] = {}
    for k, v in (payload.data or {}).items():
        if k not in allowed:
            continue
        if k == "requested_price":
            rp = round(float(v or 0), 2)
            if rp <= 0:
                raise HTTPException(status_code=400, detail="Harga khusus harus lebih dari 0")
            data[k] = rp
        elif k == "min_quantity":
            data[k] = round(float(v or 0), 2)
        elif k == "valid_until":
            data[k] = _norm_until(str(v))
        else:
            data[k] = (str(v) or "").strip()
    if not data:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diperbarui")
    data["updated_at"] = now_iso()
    updated = await db.price_approvals.find_one_and_update(
        {"id": approval_id}, {"$set": data},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    await audit(user.get("name", ""), "price_approval_updated", "price_approval", approval_id, data)
    return _decorate(safe_doc(updated))


@router.delete("/price-approvals/{approval_id}")
async def delete_price_approval(approval_id: str, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "price_approval", "delete")
    doc = await _get_or_404(approval_id)
    _ensure_owner_or_privileged(doc, user)
    if doc["status"] == "approved":
        raise HTTPException(status_code=409, detail="Pengajuan yang sudah disetujui tidak dapat dihapus")
    await db.price_approvals.delete_one({"id": approval_id})
    await audit(user.get("name", ""), "price_approval_deleted", "price_approval", approval_id, {"status": doc["status"]})
    return {"deleted": True, "id": approval_id}


# ─── Lifecycle: submit / approve / reject ────────────────────────────────────

@router.post("/price-approvals/{approval_id}/submit")
async def submit_price_approval(approval_id: str, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "price_approval", "update")
    doc = await _get_or_404(approval_id)
    _ensure_owner_or_privileged(doc, user)
    if doc["status"] != "draft":
        raise HTTPException(status_code=409, detail="Hanya pengajuan draft yang dapat disubmit")
    updated = await db.price_approvals.find_one_and_update(
        {"id": approval_id}, {"$set": {"status": "pending", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    await audit(user.get("name", ""), "price_approval_submitted", "price_approval", approval_id, {"status": "pending"})
    return _decorate(safe_doc(updated))


@router.post("/price-approvals/{approval_id}/approve")
async def approve_price_approval(approval_id: str, payload: PriceApprovalDecision, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "price_approval", "approve")
    doc = await _get_or_404(approval_id)
    if doc["status"] not in DECIDABLE_STATUSES:
        raise HTTPException(status_code=409, detail=f"Status '{doc['status']}' tidak dapat disetujui")
    # PS-20 — Pemisahan tugas SATU SUMBER (ikut Pusat Pengaturan, bukan hardcode):
    # pengaju tidak boleh menyetujui pengajuannya sendiri.
    if await matrix.sod_blocked(doc, user, doc.get("entity_id", "")):
        raise HTTPException(
            status_code=403,
            detail="Pemisahan tugas: pengaju harga tidak boleh menyetujui pengajuannya "
                   "sendiri. Minta approver lain, atau ubah sakelar pemisahan tugas di "
                   "Pusat Pengaturan → Persetujuan & Ambang.")
    update = {
        "status": "approved", "approved_by": user.get("id"),
        "approved_by_name": user.get("name", ""),
        "decision_notes": (payload.decision_notes or "").strip(),
        "decided_at": now_iso(), "updated_at": now_iso(),
    }
    updated = await db.price_approvals.find_one_and_update(
        {"id": approval_id}, {"$set": update},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    # Override/replace: aturan STANDING yang baru disetujui menggantikan (supersede)
    # aturan approved lain untuk (entity, customer, product) yang sama → yang terbaru menang.
    superseded = 0
    superseded_docs: List[Dict[str, Any]] = []
    if (updated or {}).get("scope", "standing") != "order":
        sup_filter = {
            "id": {"$ne": approval_id}, "status": "approved",
            "scope": {"$ne": "order"},
            "entity_id": updated.get("entity_id"),
            "customer_id": updated.get("customer_id"),
            "product_id": updated.get("product_id"),
        }
        superseded_docs = await db.price_approvals.find(
            sup_filter,
            {"_id": 0, "id": 1, "requested_by": 1, "requested_by_name": 1,
             "requested_price": 1, "entity_id": 1, "customer_name": 1,
             "product_name": 1, "sku": 1, "unit": 1},
        ).to_list(200)
        res = await db.price_approvals.update_many(
            sup_filter,
            {"$set": {"status": "superseded", "superseded_by": approval_id,
                      "superseded_at": now_iso(), "updated_at": now_iso()}},
        )
        superseded = res.modified_count
    # Notifikasi ke pengaju yang aturannya di-supersede (dedupe per approval lama).
    new_price = float((updated or {}).get("requested_price") or 0)
    approver_name = user.get("name", "") or "Approver"
    for old in superseded_docs:
        owner_id = (old.get("requested_by") or "").strip()
        if not owner_id:
            continue
        old_price = float(old.get("requested_price") or 0)
        delta = new_price - old_price
        delta_pct = (delta / old_price * 100.0) if old_price else 0.0
        arrow = "↓" if delta < 0 else ("↑" if delta > 0 else "→")
        cust = old.get("customer_name") or ""
        prod = old.get("product_name") or old.get("sku") or ""
        unit = old.get("unit") or "meter"
        await create_notification(
            notif_type="price_approval_superseded",
            ref=f"pra_superseded:{old.get('id', '')}",
            title=f"Aturan harga Anda diganti: {prod}",
            body=(f"Aturan Anda untuk {cust} · {prod} digantikan oleh "
                  f"pengajuan {approval_id} yang baru disetujui {approver_name}. "
                  f"Harga: {rupiah(old_price)}/{unit} {arrow} {rupiah(new_price)}/{unit} "
                  f"(Δ {delta_pct:+.1f}%)."),
            severity="warning",
            link="price-approvals",
            entity_id=old.get("entity_id"),
            recipient_role="sales",
            recipient_user=owner_id,
            action_type="price_approval_view",
            action_id=approval_id,
            action_role="sales",
        )
    await audit(user.get("name", ""), "price_approval_approved", "price_approval", approval_id, {
        "requested_price": doc.get("requested_price"), "approved_by": user.get("name", ""),
        "superseded_count": superseded,
    })
    # F1b — efek lanjutan: bila pengajuan ini berasal dari Daftar Harga per Pelanggan,
    # record harga langganannya diaktifkan sekarang (satu keputusan, satu jejak).
    side = await pas.after_decision(updated or {}, user, "approved")
    out = _decorate(safe_doc(updated))
    if side:
        out["customer_price_effect"] = side
    return out


@router.post("/price-approvals/{approval_id}/reject")
async def reject_price_approval(approval_id: str, payload: PriceApprovalDecision, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "price_approval", "reject")
    doc = await _get_or_404(approval_id)
    if doc["status"] not in DECIDABLE_STATUSES:
        raise HTTPException(status_code=409, detail=f"Status '{doc['status']}' tidak dapat ditolak")
    if await matrix.sod_blocked(doc, user, doc.get("entity_id", "")):
        raise HTTPException(
            status_code=403,
            detail="Pemisahan tugas: pengaju harga tidak boleh memutuskan pengajuannya "
                   "sendiri. Minta approver lain, atau ubah sakelar pemisahan tugas di "
                   "Pusat Pengaturan → Persetujuan & Ambang.")
    update = {
        "status": "rejected", "approved_by": user.get("id"),
        "approved_by_name": user.get("name", ""),
        "decision_notes": (payload.decision_notes or "").strip(),
        "decided_at": now_iso(), "updated_at": now_iso(),
    }
    updated = await db.price_approvals.find_one_and_update(
        {"id": approval_id}, {"$set": update},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    await audit(user.get("name", ""), "price_approval_rejected", "price_approval", approval_id, {
        "reason": update["decision_notes"], "rejected_by": user.get("name", ""),
    })
    side = await pas.after_decision(updated or {}, user, "rejected")
    out = _decorate(safe_doc(updated))
    if side:
        out["customer_price_effect"] = side
    return out


@router.post("/price-approvals/{approval_id}/revoke")
async def revoke_price_approval(approval_id: str, payload: PriceApprovalDecision,
                                request: Request) -> Dict[str, Any]:
    """**Akhiri** aturan harga khusus yang sudah disetujui (promo selesai / kesepakatan
    dibatalkan).

    Celah nyata sebelum ini: aturan `standing` yang sudah `approved` TIDAK BISA
    dihentikan lewat cara apa pun — hapus ditolak (409) dan ubah hanya untuk draft/pending.
    Satu-satunya jalan adalah menyetujui aturan lain untuk menggantikannya, sehingga harga
    lama menempel selamanya. Sekarang approver bisa mengakhirinya dengan alasan yang
    tercatat; harga kembali ke rantai normal (pelanggan → PT → umum).
    """
    user = await require_permission(request, "price_approval", "approve")
    doc = await _get_or_404(approval_id)
    ctx = await entity_ctx(request)
    assert_entity_access(doc, "price_approvals", ctx)
    if doc.get("status") != "approved":
        raise HTTPException(status_code=409,
                            detail=f"Hanya aturan yang sudah disetujui dapat diakhiri "
                                   f"(status sekarang '{doc.get('status')}').")
    reason = (payload.decision_notes or "").strip()
    if not reason:
        raise HTTPException(status_code=400,
                            detail="Alasan wajib diisi supaya jejaknya jujur "
                                   "(mis. 'promo selesai', 'kesepakatan dibatalkan').")
    update = {"status": "revoked", "revoked_by": user.get("id"),
              "revoked_by_name": user.get("name", ""), "revoked_at": now_iso(),
              "decision_notes": reason, "updated_at": now_iso()}
    updated = await db.price_approvals.find_one_and_update(
        {"id": approval_id}, {"$set": update},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    owner_id = (doc.get("requested_by") or "").strip()
    if owner_id and owner_id != user.get("id"):
        unit = doc.get("unit", "meter")
        await create_notification(
            notif_type="price_approval_revoked",
            ref=f"pra_revoked:{approval_id}",
            title=f"Harga khusus diakhiri: {doc.get('product_name') or doc.get('sku')}",
            body=(f"{doc.get('customer_name', '')} · "
                  f"{rupiah(doc.get('requested_price') or 0)}/{unit} tidak berlaku lagi "
                  f"(diakhiri {user.get('name', '')}). Alasan: {reason}"),
            severity="warning", link="price-approvals",
            entity_id=doc.get("entity_id"), recipient_role="sales", recipient_user=owner_id,
            action_type="price_approval_view", action_id=approval_id, action_role="sales",
        )
    await audit(user.get("name", ""), "price_approval_revoked", "price_approval", approval_id,
                {"reason": reason, "requested_price": doc.get("requested_price"),
                 "customer": doc.get("customer_name"), "product": doc.get("product_name")})
    side = await pas.after_decision(updated or {}, user, "revoked")
    out = _decorate(safe_doc(updated))
    if side:
        out["customer_price_effect"] = side
    return out


# ─── Attachments (bukti) ─────────────────────────────────────────────────────

@router.post("/price-approvals/{approval_id}/attachments")
async def upload_attachment(approval_id: str, request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    user = await require_permission(request, "price_approval", "update")
    doc = await _get_or_404(approval_id)
    _ensure_owner_or_privileged(doc, user)
    data = await file.read()
    try:
        content_type = storage.validate_upload(file.filename, file.content_type, len(data))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    path = storage.build_path(f"price_approvals/{approval_id}", storage.ext_of(file.filename))
    try:
        result = await storage.put_object(path, data, content_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gagal mengunggah file: {e}")
    att = {
        "id": new_id("att"),
        "storage_path": result.get("path", path),
        "original_filename": file.filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "uploaded_by": user.get("name", ""),
        "uploaded_at": now_iso(),
        "is_deleted": False,
    }
    await db.price_approvals.update_one(
        {"id": approval_id}, {"$push": {"attachments": att}, "$set": {"updated_at": now_iso()}}
    )
    await audit(user.get("name", ""), "price_approval_attachment_added", "price_approval", approval_id,
                {"file": file.filename})
    return att


@router.get("/price-approvals/{approval_id}/attachments/{att_id}/download")
async def download_attachment(
    approval_id: str, att_id: str, request: Request, auth: str = Query(None),
    authorization: str = Header(None),
):
    # Dukung query-param auth untuk <img>/<a> yang tidak bisa kirim header.
    if not authorization and auth:
        # suntik header agar dependency current_user dapat membacanya
        request.scope["headers"] = list(request.scope.get("headers", [])) + [
            (b"authorization", f"Bearer {auth}".encode())
        ]
    user = await require_permission(request, "price_approval", "view")
    doc = await _get_or_404(approval_id)
    _ensure_owner_or_privileged(doc, user)
    att = next((a for a in (doc.get("attachments") or []) if a.get("id") == att_id and not a.get("is_deleted")), None)
    if not att:
        raise HTTPException(status_code=404, detail="Lampiran tidak ditemukan")
    try:
        content, ctype = await storage.get_object(att["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gagal mengambil file: {e}")
    return Response(
        content=content, media_type=att.get("content_type", ctype),
        headers={"Content-Disposition": f'inline; filename="{att.get("original_filename", "file")}"'},
    )


@router.delete("/price-approvals/{approval_id}/attachments/{att_id}")
async def delete_attachment(approval_id: str, att_id: str, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "price_approval", "update")
    doc = await _get_or_404(approval_id)
    _ensure_owner_or_privileged(doc, user)
    res = await db.price_approvals.update_one(
        {"id": approval_id, "attachments.id": att_id},
        {"$set": {"attachments.$.is_deleted": True, "updated_at": now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lampiran tidak ditemukan")
    await audit(user.get("name", ""), "price_approval_attachment_deleted", "price_approval", approval_id,
                {"attachment_id": att_id})
    return {"deleted": True, "id": att_id}
