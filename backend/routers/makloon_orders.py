"""M3 — Makloon Orders router (transaksi subkontrak: create/issue/receive/cancel).

Koleksi kanonik `makloon_orders` (prefix mko_), SCOPED per entitas. Respons ARRAY/OBJEK
telanjang (kontrak KN). Auth wajib via require_permission("makloon_order", ...).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from db import db
from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas import (
    MakloonOrderCreate, MakloonIssueIn, MakloonReceiveIn, MakloonOrderCancel,
    MakloonClaimIn, MakloonClaimDecisionIn, MakloonEstimateIn, MakloonServiceIn,
)
from services import contract_service as cs
from services import makloon_claim_service as mclaim
from services import master_registry as mreg
from services.makloon_order_service import (
    create_makloon_order, issue_step, receive_step, cancel_order,
    list_makloon_orders, makloon_order_detail, estimate_step_preview,
    record_service_step,
)

router = APIRouter(prefix="/api")


# ── FASE T — pemilih TAHAPAN PROSES untuk papan & form SPK ───────────────────
# Kenapa endpoint sendiri dan bukan `/api/enums` saja: form SPK butuh tahap yang
# SUDAH disaring (hanya yang boleh jadi langkah SPK, dan hanya yang berlaku untuk
# lini kerjanya). Menyaring di layar berarti setiap layar menyalin aturannya.

@router.get("/process-stages")
async def list_process_stages(request: Request, line: str = "",
                              spk_only: bool = True) -> List[Dict[str, Any]]:
    """Tahapan proses EFEKTIF untuk badan usaha aktif (dari master, fallback benih)."""
    await require_permission(request, "makloon_order", "view")
    ctx = await entity_ctx(request)
    ent = getattr(ctx, "active_entity_id", "") or ""
    if ent == "all":
        ent = ""
    if spk_only:
        return await mreg.stage_options(ent, line or "")
    return await mreg.stages_for_line(line or "", ent, spk_only=False)


@router.get("/process-stages/for-line/{line_code}")
async def process_stages_for_line(line_code: str, request: Request) -> List[Dict[str, Any]]:
    """Tahapan yang berlaku untuk satu lini kerja (kosong di master = semua lini)."""
    await require_permission(request, "makloon_order", "view")
    ctx = await entity_ctx(request)
    ent = getattr(ctx, "active_entity_id", "") or ""
    if ent == "all":
        ent = ""
    return await mreg.stage_options(ent, "" if line_code in ("all", "-") else line_code)


@router.get("/makloon-orders")
async def list_orders(request: Request, entity_id: str = None, status: str = None,
                      mode: str = None, line: str = None) -> List[Dict[str, Any]]:
    actor = await require_permission(request, "makloon_order", "view")
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if mode:
        query["mode"] = mode
    query = resolve_list_scope("makloon_orders", query, ctx, entity_id)
    from services import line_scope as _lines
    query = _lines.narrow(query, actor, line)   # FASE L — pagar & penyaring lini
    return await list_makloon_orders(query)


@router.post("/makloon-orders")
async def create_order(payload: MakloonOrderCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "makloon_order", "create")
    ctx = await entity_ctx(request)
    data = payload.model_dump()
    entity_id = data.get("entity_id") or ctx.active_entity_id
    # FASE D (PS-03) — pagar "override yield wajib beralasan" TIDAK lagi berdiri di sini.
    # Ia pindah ke `services/makloon_order_service.assert_yield_reason()` supaya SEMUA
    # penulis mematuhinya (API, seed, migrasi, realisasi PR), bukan hanya yang lewat
    # HTTP. Router tinggal mencatat jejak auditnya setelah SPK lahir.
    order = await create_makloon_order(data, entity_id=entity_id,
                                       actor_name=actor.get("name", ""))
    for i, s in enumerate(data.get("steps") or [], start=1):
        if float(s.get("yield_factor") or 0) > 0:
            await audit(actor.get("name", ""), "makloon_yield_override", "makloon_order",
                        order["id"], {"step": i, "yield_factor": s.get("yield_factor"),
                                      "reason": s.get("yield_override_reason", "")})
    await audit(actor.get("name", ""), "makloon_order_created", "makloon_order", order["id"],
                {"mko_number": order.get("mko_number"), "mode": order.get("mode"),
                 "steps": len(order.get("steps", []))})
    return order


@router.post("/makloon-orders/estimate")
async def estimate_step(payload: MakloonEstimateIn, request: Request) -> Dict[str, Any]:
    """Pratinjau langkah wizard: kontrak aktif → susut → estimasi GSM → tarif (auditable)."""
    await require_permission(request, "makloon_order", "view")
    ctx = await entity_ctx(request)
    data = payload.model_dump()
    data["entity_id"] = data.get("entity_id") or ctx.active_entity_id
    return await estimate_step_preview(data)


# ── FASE D — Selisih & klaim (PS-11 · D-09) ─────────────────────────────────
@router.get("/makloon-orders/claims")
async def list_claims(request: Request, status: str = "", entity_id: Optional[str] = None,
                      limit: int = 200) -> List[Dict[str, Any]]:
    await require_permission(request, "makloon_order", "view")
    ctx = await entity_ctx(request)
    flt = resolve_list_scope("makloon_orders", {}, ctx, entity_id)
    return await mclaim.list_claims(flt, status=status, limit=limit)


@router.get("/makloon-orders/claims/stats")
async def claim_stats(request: Request, entity_id: Optional[str] = None) -> Dict[str, Any]:
    await require_permission(request, "makloon_order", "view")
    ctx = await entity_ctx(request)
    flt = resolve_list_scope("makloon_orders", {}, ctx, entity_id)
    return await mclaim.claim_stats(flt)


@router.get("/makloon-orders/{mko_id}")
async def get_order(mko_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "makloon_order", "view")
    ctx = await entity_ctx(request)
    data = await makloon_order_detail(mko_id)
    if not data:
        raise HTTPException(status_code=404, detail="Order makloon tidak ditemukan")
    assert_entity_access(data, "makloon_orders", ctx)
    return data


@router.post("/makloon-orders/{mko_id}/issue")
async def issue_order_step(mko_id: str, payload: MakloonIssueIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "makloon_order", "issue")
    ctx = await entity_ctx(request)
    await _assert_access(mko_id, ctx)
    if payload.from_warehouse_id:   # E4.1 — bahan keluar dari gudang yang boleh dipakai
        from services import warehouse_scope_service as whscope
        await whscope.assert_usable(payload.from_warehouse_id, ctx.active_entity_id,
                                   action="mengeluarkan bahan dari sini",
                                   field_label="Gudang asal")
    order = await issue_step(mko_id, payload.step_seq,
                             from_warehouse_id=payload.from_warehouse_id,
                             doc_uom=payload.doc_uom, doc_qty=payload.doc_qty,
                             actor_name=actor.get("name", ""))
    await audit(actor.get("name", ""), "makloon_order_issued", "makloon_order", mko_id,
                {"step_seq": payload.step_seq, "doc_uom": payload.doc_uom,
                 "doc_qty": payload.doc_qty})
    return order


@router.post("/makloon-orders/{mko_id}/receive")
async def receive_order_step(mko_id: str, payload: MakloonReceiveIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "makloon_order", "receive")
    ctx = await entity_ctx(request)
    await _assert_access(mko_id, ctx)
    order = await receive_step(mko_id, payload.step_seq, payload.model_dump(),
                               actor_name=actor.get("name", ""))
    await audit(actor.get("name", ""), "makloon_order_received", "makloon_order", mko_id,
                {"step_seq": payload.step_seq})
    return order


@router.post("/makloon-orders/{mko_id}/record-service")
async def record_order_service(mko_id: str, payload: MakloonServiceIn,
                               request: Request) -> Dict[str, Any]:
    """FASE T — catat JASA langkah yang tidak memindahkan kain (mis. pembuatan kasa).

    Izinnya sengaja `receive` (bukan `issue`): aksi ini MENYELESAIKAN langkah dan
    melahirkan tagihan mitra, jadi wewenangnya setara menerima hasil — bukan setara
    mengeluarkan bahan.
    """
    actor = await require_permission(request, "makloon_order", "receive")
    ctx = await entity_ctx(request)
    await _assert_access(mko_id, ctx)
    order = await record_service_step(mko_id, payload.step_seq, payload.model_dump(),
                                      actor_name=actor.get("name", ""))
    await audit(actor.get("name", ""), "makloon_service_recorded", "makloon_order", mko_id,
                {"step_seq": payload.step_seq, "tariff": payload.tariff,
                 "aux_cost": payload.aux_cost, "note": payload.note})
    return order


@router.post("/makloon-orders/{mko_id}/claim")
async def propose_claim(mko_id: str, payload: MakloonClaimIn, request: Request) -> Dict[str, Any]:
    """Ajukan tindakan klaim selisih (potong bon / ganti rugi / terima) — butuh approval."""
    actor = await require_permission(request, "makloon_order", "claim")
    ctx = await entity_ctx(request)
    await _assert_access(mko_id, ctx)
    try:
        order = await mclaim.propose_claim(mko_id, payload.step_seq, action=payload.action,
                                           amount=payload.amount, reason=payload.reason,
                                           actor=actor.get("name", ""))
    except mclaim.ClaimError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor.get("name", ""), "makloon_claim_proposed", "makloon_order", mko_id,
                {"step_seq": payload.step_seq, "action": payload.action,
                 "amount": payload.amount, "reason": payload.reason})
    return order


@router.post("/makloon-orders/{mko_id}/claim/approve")
async def approve_claim(mko_id: str, payload: MakloonClaimDecisionIn,
                        request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "makloon_order", "claim_approve")
    ctx = await entity_ctx(request)
    await _assert_access(mko_id, ctx)
    try:
        order = await mclaim.approve_claim(mko_id, payload.step_seq, actor=actor.get("name", ""),
                                           actor_role=actor.get("role", ""), note=payload.note)
    except mclaim.ClaimError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor.get("name", ""), "makloon_claim_approved", "makloon_order", mko_id,
                {"step_seq": payload.step_seq, "note": payload.note})
    return order


@router.post("/makloon-orders/{mko_id}/claim/reject")
async def reject_claim(mko_id: str, payload: MakloonClaimDecisionIn,
                       request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "makloon_order", "claim_approve")
    ctx = await entity_ctx(request)
    await _assert_access(mko_id, ctx)
    try:
        order = await mclaim.reject_claim(mko_id, payload.step_seq,
                                          reason=payload.reason or payload.note,
                                          actor=actor.get("name", ""),
                                          actor_role=actor.get("role", ""))
    except mclaim.ClaimError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor.get("name", ""), "makloon_claim_rejected", "makloon_order", mko_id,
                {"step_seq": payload.step_seq, "reason": payload.reason or payload.note})
    return order


@router.post("/makloon-orders/{mko_id}/cancel")
async def cancel_order_ep(mko_id: str, payload: MakloonOrderCancel, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "makloon_order", "cancel")
    ctx = await entity_ctx(request)
    await _assert_access(mko_id, ctx)
    order = await cancel_order(mko_id, reason=payload.reason, actor_name=actor.get("name", ""))
    await audit(actor.get("name", ""), "makloon_order_cancelled", "makloon_order", mko_id,
                {"reason": payload.reason})
    return order


async def _assert_access(mko_id: str, ctx) -> None:
    doc = await db.makloon_orders.find_one({"id": mko_id}, {"_id": 0, "entity_id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Order makloon tidak ditemukan")
    assert_entity_access(doc, "makloon_orders", ctx)
