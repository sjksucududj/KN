"""FASE D/E — Router `supplier_contracts` (kontrak mitra makloon & supplier).

RBAC (tanpa modul izin baru yang berlebihan):
  * lihat   → `supplier_contract:view`   (admin, manager, warehouse, purchasing-role)
  * kelola  → `supplier_contract:create|update|delete` (admin, manager)
  * kebijakan makloon (toleransi/susut default) → admin/manager (`require_role`)

Semua endpoint ber-prefix `/api` (aturan ingress) dan mengembalikan ARRAY/OBJEK telanjang
(kontrak respons KN) kecuali saat paginasi diminta (`?page=`).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from db import db
from dependencies import audit, require_permission, require_role
from entity_scope import entity_ctx, resolve_list_scope
from pagination import envelope, get_page_params, is_paged
from schemas_contracts import (ContractStatusIn, MakloonPolicyIn, SupplierContractCreate,
                               SupplierContractPatch, TariffPreviewIn)
from services import contract_service as cs
from services import makloon_claim_service as mcs
from services.uom_rules_service import UomRuleError

router = APIRouter(prefix="/api")


def _err(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


# ── Daftar & statistik ───────────────────────────────────────────────
@router.get("/supplier-contracts")
async def list_contracts(request: Request, q: str = "", contract_type: str = "",
                         partner_id: str = "", process_type: str = "", product_id: str = "",
                         status: str = "", entity_id: Optional[str] = None,
                         limit: int = 200) -> Any:
    await require_permission(request, "supplier_contract", "view")
    ctx = await entity_ctx(request)
    flt: Dict[str, Any] = resolve_list_scope("supplier_contracts", {}, ctx, entity_id)
    for key, val in (("contract_type", contract_type), ("partner_id", partner_id),
                     ("process_type", process_type), ("product_id", product_id),
                     ("status", status)):
        if val:
            flt[key] = val
    if is_paged(request):
        page, size, term, sort = get_page_params(request)
        rows = await cs.list_contracts(flt, q=q or term, limit=size, skip=(page - 1) * size,
                                       sort=sort or "-created_at")
        total = await cs.count_contracts(flt) if not (q or term) else len(
            await cs.list_contracts(flt, q=q or term, limit=1000))
        return envelope(rows, total, page, size)
    return await cs.list_contracts(flt, q=q, limit=limit)


@router.get("/supplier-contracts/stats")
async def contract_stats(request: Request, contract_type: str = "",
                         entity_id: Optional[str] = None) -> Dict[str, Any]:
    await require_permission(request, "supplier_contract", "view")
    ctx = await entity_ctx(request)
    flt = resolve_list_scope("supplier_contracts", {}, ctx, entity_id)
    if contract_type:
        flt["contract_type"] = contract_type
    return await cs.stats(flt)


@router.get("/supplier-contracts/policy")
async def get_policy(request: Request) -> Dict[str, Any]:
    """FASE E-4 (E4.5) — kebijakan makloon badan usaha AKTIF (global + override-nya)."""
    await require_permission(request, "supplier_contract", "view")
    ctx = await entity_ctx(request)
    return await cs.get_settings(ctx.active_entity_id)


@router.put("/supplier-contracts/policy")
async def update_policy(payload: MakloonPolicyIn, request: Request) -> Dict[str, Any]:
    actor = await require_role(request, ["admin", "manager"])
    try:
        out = await cs.update_settings(payload.model_dump(exclude_none=True),
                                       actor=actor.get("name", ""))
    except cs.ContractError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "makloon_policy_updated", "settings", "makloon",
                payload.model_dump(exclude_none=True))
    return out


@router.post("/supplier-contracts/resolve")
async def resolve_contract(request: Request, partner_id: str = "", process_type: str = "",
                           product_id: str = "", input_product_id: str = "",
                           contract_type: str = "makloon") -> Dict[str, Any]:
    """Kontrak aktif paling spesifik untuk (mitra × proses × produk) — dipakai wizard."""
    await require_permission(request, "supplier_contract", "view")
    ctx = await entity_ctx(request)
    found = await cs.resolve_active(partner_id=partner_id, contract_type=contract_type,
                                    process_type=process_type, product_id=product_id,
                                    input_product_id=input_product_id,
                                    entity_id=ctx.active_entity_id)
    return {"contract": found, "found": bool(found)}


@router.post("/supplier-contracts/tariff-preview")
async def tariff_preview(payload: TariffPreviewIn, request: Request) -> Dict[str, Any]:
    """Simulasi tarif (angka antara terlihat) — tidak menyimpan apa pun."""
    await require_permission(request, "supplier_contract", "view")
    try:
        return await cs.tariff_preview(payload.model_dump())
    except (cs.ContractError, UomRuleError) as exc:
        raise _err(exc) from exc


@router.get("/supplier-contracts/{contract_id}")
async def get_contract(contract_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "supplier_contract", "view")
    doc = await cs.get_contract(contract_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Kontrak tidak ditemukan")
    return doc


@router.post("/supplier-contracts")
async def create_contract(payload: SupplierContractCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "supplier_contract", "create")
    ctx = await entity_ctx(request)
    data = payload.model_dump()
    entity_id = data.get("entity_id") or ctx.active_entity_id
    try:
        doc = await cs.create_contract(data, entity_id=entity_id, actor=actor.get("name", ""))
    except cs.ContractError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "supplier_contract_created", "supplier_contract",
                doc["id"], {"contract_number": doc.get("contract_number"),
                            "partner_name": doc.get("partner_name"),
                            "tariff_basis": doc.get("tariff_basis")})
    return doc


@router.patch("/supplier-contracts/{contract_id}")
async def patch_contract(contract_id: str, payload: SupplierContractPatch,
                         request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "supplier_contract", "update")
    try:
        doc = await cs.patch_contract(contract_id, payload.model_dump(exclude_none=True),
                                      actor=actor.get("name", ""))
    except cs.ContractError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "supplier_contract_updated", "supplier_contract",
                contract_id, payload.model_dump(exclude_none=True))
    return doc


@router.post("/supplier-contracts/{contract_id}/status")
async def set_contract_status(contract_id: str, payload: ContractStatusIn,
                              request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "supplier_contract", "update")
    try:
        doc = await cs.set_status(contract_id, payload.status, reason=payload.reason,
                                  actor=actor.get("name", ""))
    except cs.ContractError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "supplier_contract_status", "supplier_contract",
                contract_id, {"status": payload.status, "reason": payload.reason})
    return doc


@router.delete("/supplier-contracts/{contract_id}")
async def delete_contract(contract_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "supplier_contract", "delete")
    doc = await cs.get_contract(contract_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Kontrak tidak ditemukan")
    used = await db.makloon_orders.count_documents({"steps.contract_id": contract_id})
    # FASE E — kontrak PEMBELIAN dipakai oleh baris Purchase Order (jejak harga & audit).
    used_po = await db.purchase_orders.count_documents(
        {"$or": [{"items.contract_id": contract_id}, {"contract_ids": contract_id}]})
    if used or used_po:
        where = " · ".join(x for x in [f"{used} order makloon" if used else "",
                                       f"{used_po} purchase order" if used_po else ""] if x)
        raise HTTPException(status_code=409,
                            detail=f"Kontrak dipakai {where} — nonaktifkan "
                                   "(status 'terminated') alih-alih menghapus.")
    await db[cs.COLL].delete_one({"id": contract_id})
    await audit(actor.get("name", ""), "supplier_contract_deleted", "supplier_contract",
                contract_id, {"contract_number": doc.get("contract_number")})
    return {"deleted": True, "id": contract_id}


# ── Skor mitra (turunan klaim · PS-11) ────────────────────────────────
@router.get("/makloon-partners/scorecard")
async def partner_scorecard(request: Request, entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
    await require_permission(request, "makloon", "view")
    ctx = await entity_ctx(request)
    flt = resolve_list_scope("makloon_orders", {}, ctx, entity_id)
    return await mcs.partner_scorecard(flt)
