"""FASE C — Router Lot kelas satu (`inventory_lots`): identitas batch, silsilah,
recall, dan label.

Rujukan: `docs/KN_23_PLAN_FASE_C_LOT.md` · KN_18 PS-10 · keputusan **D-10** (format
`LOT-YYMM-####`, granularitas per batch penerimaan/proses), **D-26** (nomor per
entitas), **D-27** (penegakan `warn`/`block` configurable).

RBAC — memakai modul izin `inventory` yang SUDAH ADA (tanpa modul izin baru, R3):
  * lihat (`inventory:view`)   → admin, manager, sales, warehouse (traceability harus
    transparan lintas peran: sales perlu recall, gudang perlu silsilah).
  * ubah  (`inventory:update`) → admin, manager, warehouse (aksi lapangan).
  * pengaturan penegakan      → admin/manager (`require_role`).
Semua endpoint ber-prefix `/api` (aturan ingress).
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from db import db
from dependencies import audit, require_permission, require_role
from entity_scope import assert_entity_access, entity_ctx, resolve_list_scope
from pagination import envelope, get_page_params, is_paged
from schemas_lots import (LotAttachRollsIn, LotCreateIn, LotLabelIn, LotMergeIn,
                          LotPatchIn, LotReworkIn, LotSettingsIn, LotSplitIn,
                          LotStatusIn)
from services import lot_service as ls
from services import warehouse_scope_service as whscope
from services import lot_trace_service as lts

router = APIRouter(prefix="/api")


def _err(exc: ls.LotError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


async def _guard_lot(request: Request, lot_id: str) -> Dict[str, Any]:
    """FASE E-0 (L8) — pagar anti-IDOR untuk SEMUA endpoint lot by-id.

    Daftar lot sudah ter-scope, tetapi detail/silsilah/recall/label/aksi TIDAK:
    sales PT Kain Suka Cita bisa membuka lot CV Kanda Suka (HTTP 200). Sekarang
    lot di luar entitas yang diizinkan dianggap TIDAK ADA (404).
    """
    ctx = await entity_ctx(request)
    lot = await db.inventory_lots.find_one({"id": lot_id},
                                          {"_id": 0, "id": 1, "owner_entity_id": 1})
    if not lot:
        raise HTTPException(status_code=404, detail="Lot tidak ditemukan")
    assert_entity_access(lot, "inventory_lots", ctx)
    return lot


# ── Daftar & statistik ──────────────────────────────────────────────────
@router.get("/lots")
async def list_lots(request: Request, q: str = "", product_id: str = "",
                    warehouse_id: str = "", source: str = "", lot_status: str = "",
                    stage: str = "", entity_id: Optional[str] = None,
                    line: str = "", limit: int = 200) -> Any:
    """Daftar lot (entity-scoped). Mendukung paginasi opsional `?page=&page_size=`."""
    actor = await require_permission(request, "inventory", "view")
    ctx = await entity_ctx(request)
    flt: Dict[str, Any] = resolve_list_scope("inventory_lots", {}, ctx, entity_id)
    for key, val in (("product_id", product_id), ("warehouse_id", warehouse_id),
                     ("source", source), ("lot_status", lot_status), ("stage", stage)):
        if val:
            flt[key] = val
    # FASE L — pagar lini juga di lot. Lot lama tanpa lini tetap terlihat (data lama).
    from services import line_scope as _lines
    flt = _lines.narrow(flt, actor, line)
    if is_paged(request):
        page, size, term, sort = get_page_params(request)
        rows = await ls.list_lots(flt, q=q or term, limit=size, skip=(page - 1) * size,
                                  sort=sort or "-created_at")
        total = await ls.count_lots(flt) if not (q or term) else len(
            await ls.list_lots(flt, q=q or term, limit=1000))
        return envelope(rows, total, page, size)
    return await ls.list_lots(flt, q=q, limit=limit)


@router.get("/lots/stats")
async def lot_stats(request: Request, entity_id: Optional[str] = None) -> Dict[str, Any]:
    await require_permission(request, "inventory", "view")
    ctx = await entity_ctx(request)
    flt = resolve_list_scope("inventory_lots", {}, ctx, entity_id)
    return await ls.stats(flt)


@router.get("/lots/settings")
async def lot_settings(request: Request) -> Dict[str, Any]:
    """FASE E-4 (E4.5) — setelan lot badan usaha AKTIF (global + override-nya)."""
    await require_permission(request, "inventory", "view")
    ctx = await entity_ctx(request)
    return await ls.get_settings(ctx.active_entity_id)


@router.put("/lots/settings")
async def update_lot_settings(payload: LotSettingsIn, request: Request) -> Dict[str, Any]:
    actor = await require_role(request, ["manager"])
    try:
        doc = await ls.update_settings(payload.model_dump(exclude_none=True),
                                       actor.get("name", ""))
    except ls.LotError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "lot_settings_updated", "system_settings", "lot",
                doc, "Fase C — penegakan lot (D-27)")
    return doc


@router.get("/lots/unassigned-rolls")
async def unassigned_rolls(request: Request, product_id: str = "",
                           entity_id: Optional[str] = None,
                           limit: int = 100) -> Dict[str, Any]:
    """Roll yang BELUM punya lot (mode `warn` — dipakai layar untuk penambalan data)."""
    await require_permission(request, "inventory", "view")
    ctx = await entity_ctx(request)
    flt: Dict[str, Any] = resolve_list_scope("inventory_rolls", {}, ctx, entity_id)
    flt["lot_id"] = {"$in": [None, ""]}
    if product_id:
        flt["product_id"] = product_id
    rows = await db.inventory_rolls.find(
        flt, {"_id": 0, "id": 1, "roll_no": 1, "product_id": 1, "lot": 1, "dye_lot": 1,
              "status": 1, "stage": 1, "length_remaining": 1, "unit": 1,
              "warehouse_id": 1, "owner_entity_id": 1}).limit(
        max(1, min(int(limit), 500))).to_list(500)
    return {"rolls": rows, "total": await db.inventory_rolls.count_documents(flt)}


# ── Detail & silsilah ────────────────────────────────────────────────
@router.get("/lots/{lot_id}")
async def get_lot(lot_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "inventory", "view")
    await _guard_lot(request, lot_id)
    try:
        lot = await ls.get_lot(lot_id)
    except ls.LotError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    lot["rolls"] = await ls.rolls_of(lot["id"])
    lot["warnings"] = ls.capture_warnings(lot.get("supplier_lot", ""),
                                          lot.get("dye_lot", ""), await ls.get_settings())
    parents = await db.inventory_lots.find(
        {"id": {"$in": lot.get("parent_lot_ids") or []}},
        {"_id": 0, "id": 1, "lot_number": 1, "stage": 1, "source": 1}).to_list(200)
    children = await db.inventory_lots.find(
        {"id": {"$in": lot.get("child_lot_ids") or []}},
        {"_id": 0, "id": 1, "lot_number": 1, "stage": 1, "source": 1}).to_list(200)
    lot["parents"] = parents
    lot["children"] = children
    return lot


@router.get("/lots/{lot_id}/genealogy")
async def lot_genealogy(lot_id: str, request: Request, depth: int = 6) -> Dict[str, Any]:
    await require_permission(request, "inventory", "view")
    await _guard_lot(request, lot_id)
    try:
        return await lts.genealogy(lot_id, max_depth=max(1, min(int(depth), 10)))
    except ls.LotError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/lots/{lot_id}/recall")
async def lot_recall(lot_id: str, request: Request,
                     include_descendants: bool = True) -> Dict[str, Any]:
    await require_permission(request, "inventory", "view")
    await _guard_lot(request, lot_id)
    try:
        return await lts.recall(lot_id, include_descendants=include_descendants)
    except ls.LotError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/lots/{lot_id}/label")
async def lot_label(lot_id: str, payload: LotLabelIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "view")
    await _guard_lot(request, lot_id)
    try:
        out = await lts.label(lot_id, fmt=payload.format, qty=payload.qty,
                              roll_id=payload.roll_id)
    except ls.LotError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "lot_label_generated", "inventory_lot", lot_id,
                {"format": payload.format, "qty": payload.qty,
                 "roll_id": payload.roll_id}, "Fase C — label lot/QR")
    return out


# ── Mutasi ──────────────────────────────────────────────────────────
@router.post("/lots")
async def create_lot(payload: LotCreateIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "update")
    ctx = await entity_ctx(request)
    owner = payload.owner_entity_id or ctx.active_entity_id
    if owner not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=403, detail="Tidak berwenang atas entitas ini")
    # E4.1 — lot lahir di gudang; gudang khusus badan usaha lain ditolak di server.
    if payload.warehouse_id:
        await whscope.assert_usable(payload.warehouse_id, owner,
                                   action="membuat lot di sini")
    try:
        warnings = await ls.guard_capture(payload.supplier_lot, payload.dye_lot)
        lot = await ls.create_lot(
            product_id=payload.product_id, owner_entity_id=owner,
            warehouse_id=payload.warehouse_id, source=payload.source or "manual",
            source_ref={"type": "manual", "id": "", "number": ""},
            supplier_lot=payload.supplier_lot, dye_lot=payload.dye_lot,
            shade_ref=payload.shade_ref, supplier_id=payload.supplier_id,
            supplier_name=payload.supplier_name, status=payload.lot_status or "released",
            note=payload.note, parent_lot_ids=payload.parent_lot_ids,
            actor=actor.get("name", "Admin"))
        if payload.roll_ids:
            lot = await ls.attach_rolls(lot["id"], payload.roll_ids,
                                        actor=actor.get("name", "Admin"))
    except ls.LotError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "lot_created", "inventory_lot", lot["id"],
                {"lot_number": lot["lot_number"], "product_id": lot["product_id"],
                 "source": lot["source"]}, "Fase C — lot kelas satu")
    lot["warnings"] = warnings
    return lot


@router.patch("/lots/{lot_id}")
async def patch_lot(lot_id: str, payload: LotPatchIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "update")
    await _guard_lot(request, lot_id)
    try:
        lot = await ls.patch_lot(lot_id, payload.model_dump(exclude_none=True),
                                 actor.get("name", "Admin"))
    except ls.LotError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "lot_updated", "inventory_lot", lot_id,
                payload.model_dump(exclude_none=True))
    lot["warnings"] = ls.capture_warnings(lot.get("supplier_lot", ""),
                                          lot.get("dye_lot", ""), await ls.get_settings())
    return lot


@router.post("/lots/{lot_id}/status")
async def set_lot_status(lot_id: str, payload: LotStatusIn,
                         request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "update")
    await _guard_lot(request, lot_id)
    try:
        lot = await ls.set_status(lot_id, payload.status, payload.reason,
                                 actor.get("name", "Admin"))
    except ls.LotError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "lot_status_changed", "inventory_lot", lot_id,
                {"status": lot["lot_status"], "reason": payload.reason})
    return lot


@router.post("/lots/{lot_id}/rolls")
async def attach_rolls(lot_id: str, payload: LotAttachRollsIn,
                       request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "update")
    await _guard_lot(request, lot_id)
    if not payload.roll_ids:
        raise HTTPException(status_code=400, detail="Pilih minimal 1 roll.")
    try:
        lot = await ls.attach_rolls(lot_id, payload.roll_ids,
                                    set_lot_string=not payload.keep_lot_string,
                                    actor=actor.get("name", "Admin"))
    except ls.LotError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "lot_rolls_attached", "inventory_lot", lot_id,
                {"rolls": payload.roll_ids[:20], "count": len(payload.roll_ids)})
    return lot


@router.post("/lots/{lot_id}/split")
async def split_lot(lot_id: str, payload: LotSplitIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "update")
    await _guard_lot(request, lot_id)
    if payload.warehouse_id:   # E4.1 — anak lot tidak boleh pindah ke gudang orang lain
        await whscope.assert_usable(payload.warehouse_id,
                                   (await entity_ctx(request)).active_entity_id,
                                   action="menempatkan lot pecahan di sini")
    try:
        out = await ls.split_lot(lot_id, roll_ids=payload.roll_ids, reason=payload.reason,
                                 dye_lot=payload.dye_lot, warehouse_id=payload.warehouse_id,
                                 actor=actor.get("name", "Admin"))
    except ls.LotError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "lot_split", "inventory_lot", lot_id,
                {"child": out["child"]["lot_number"], "rolls": out["moved_rolls"],
                 "reason": payload.reason}, "Fase C — split lot")
    return out


@router.post("/lots/merge")
async def merge_lots(payload: LotMergeIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "update")
    for _lid in (payload.lot_ids or []):
        await _guard_lot(request, _lid)
    if payload.warehouse_id:   # E4.1 — lot gabungan tidak boleh mendarat di gudang orang lain
        await whscope.assert_usable(payload.warehouse_id,
                                   (await entity_ctx(request)).active_entity_id,
                                   action="menempatkan lot gabungan di sini")
    try:
        out = await ls.merge_lots(payload.lot_ids, reason=payload.reason,
                                  dye_lot=payload.dye_lot,
                                  warehouse_id=payload.warehouse_id,
                                  actor=actor.get("name", "Admin"))
    except ls.LotError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "lot_merged", "inventory_lot", out["lot"]["id"],
                {"lot_number": out["lot"]["lot_number"], "sources": out["sources"],
                 "rolls": out["moved_rolls"]}, "Fase C — merge lot")
    return out


@router.post("/lots/{lot_id}/rework")
async def rework_lot(lot_id: str, payload: LotReworkIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "update")
    await _guard_lot(request, lot_id)
    try:
        out = await ls.rework_lot(lot_id, process_type=payload.process_type,
                                  roll_ids=payload.roll_ids or None,
                                  partner_id=payload.partner_id,
                                  partner_name=payload.partner_name,
                                  to_stage=payload.to_stage, dye_lot=payload.dye_lot,
                                  reason=payload.reason, actor=actor.get("name", "Admin"))
    except ls.LotError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "lot_rework", "inventory_lot", lot_id,
                {"child": out["child"]["lot_number"], "process": payload.process_type,
                 "to_stage": payload.to_stage, "rolls": out["moved_rolls"]},
                "Fase C — rework lot")
    return out


@router.get("/rolls/{roll_id}/lot")
async def roll_lot(roll_id: str, request: Request) -> Dict[str, Any]:
    """Lot dari sebuah roll (dipakai panel detail roll di gudang)."""
    await require_permission(request, "inventory", "view")
    ctx = await entity_ctx(request)
    roll = await db.inventory_rolls.find_one(
        {"id": roll_id},
        {"_id": 0, "lot_id": 1, "lot": 1, "roll_no": 1, "owner_entity_id": 1})
    if not roll:
        raise HTTPException(status_code=404, detail="Roll tidak ditemukan")
    assert_entity_access(roll, "inventory_rolls", ctx)   # FASE E-0 (L8)
    if not roll.get("lot_id"):
        return {"roll_no": roll.get("roll_no", ""), "lot_id": "",
                "lot_code_legacy": roll.get("lot", ""), "lot": None,
                "warning": "Roll ini belum tertaut ke lot kelas satu (mode peringatan)."}
    try:
        lot = await ls.get_lot(roll["lot_id"])
    except ls.LotError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"roll_no": roll.get("roll_no", ""), "lot_id": lot["id"], "lot": lot,
            "lot_code_legacy": roll.get("lot", "")}
