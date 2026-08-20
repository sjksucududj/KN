"""R6.2 — Fixed Assets & Depresiasi router. Akses: permission "fixed_asset" (admin/manager).

Respons OBJEK/ARRAY telanjang (konsisten dgn bank.py / bank_reconciliation.py).
Penyusutan straight-line + disposal gain/loss (self-balancing JE). GL-safe & idempotent.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel

from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_scope_ids
from schemas_interco_loan import FixedAssetTransferIn, FixedAssetTransferSettleIn
from services import fixed_asset_service as svc
from services import gl_service

router = APIRouter(prefix="/api")


class FixedAssetIn(BaseModel):
    name: str
    category: str = "Peralatan & Mesin"
    acquisition_cost: float = 0
    acquisition_date: str = ""
    useful_life_months: int = 0
    salvage_value: float = 0
    entity_id: Optional[str] = ""
    gl_account_asset: Optional[str] = ""
    funding_account: Optional[str] = ""
    notes: Optional[str] = ""


class FixedAssetPatch(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    gl_account_asset: Optional[str] = None
    acquisition_cost: Optional[float] = None
    useful_life_months: Optional[int] = None
    salvage_value: Optional[float] = None
    acquisition_date: Optional[str] = None


class RunDepreciationIn(BaseModel):
    period: str                       # YYYY-MM
    asset_id: Optional[str] = ""
    entity_id: Optional[str] = ""


class DisposeIn(BaseModel):
    proceeds: float = 0
    date: Optional[str] = ""
    note: Optional[str] = ""


def _scope(ctx, entity_id: Optional[str]) -> Dict[str, Any]:
    ids = resolve_scope_ids(ctx, entity_id)
    return {"entity_id": {"$in": ids}}


@router.get("/fixed-assets")
async def list_fixed_assets(request: Request, entity_id: str = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "fixed_asset", "view")
    ctx = await entity_ctx(request)
    return await svc.list_assets(scope=_scope(ctx, entity_id))


@router.get("/fixed-assets/meta")
async def fixed_asset_meta(request: Request, entity_id: str = Query(None)) -> Dict[str, Any]:
    """Kategori + akun GL aset yang bisa dipilih (postable di bawah 1-2000, kecuali akumulasi)."""
    await require_permission(request, "fixed_asset", "view")
    await gl_service.seed_default_coa()
    accts = await gl_service.list_accounts(active_only=True, entity_id=entity_id or None)
    asset_accts = [{"code": a["code"], "name": a["name"]} for a in accts
                   if a.get("code", "").startswith("1-2") and a.get("is_postable")
                   and a.get("code") != gl_service.ACC_FA_ACCUM_DEP]
    asset_accts.sort(key=lambda x: x["code"])
    return {
        "categories": svc.ASSET_CATEGORIES,
        "category_account": svc.CATEGORY_ACCOUNT,
        "asset_accounts": asset_accts,
        "acc_dep_account": gl_service.ACC_FA_ACCUM_DEP,
        "dep_expense_account": gl_service.ACC_DEP_EXPENSE,
    }


@router.get("/fixed-assets/summary")
async def fixed_asset_summary(request: Request, entity_id: str = Query(None)) -> Dict[str, Any]:
    await require_permission(request, "fixed_asset", "view")
    ctx = await entity_ctx(request)
    return await svc.summary(scope=_scope(ctx, entity_id))


@router.post("/fixed-assets")
async def create_fixed_asset(payload: FixedAssetIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "fixed_asset", "create")
    try:
        asset = await svc.create_asset(payload.model_dump(), actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "fixed_asset_created", "fixed_asset", asset["id"],
                {"number": asset["number"], "cost": asset["acquisition_cost"]})
    return asset


@router.post("/fixed-assets/run-depreciation")
async def run_depreciation(payload: RunDepreciationIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "fixed_asset", "run")
    ctx = await entity_ctx(request)
    try:
        res = await svc.run_depreciation(payload.period, actor,
                                         asset_id=payload.asset_id or None,
                                         scope=_scope(ctx, payload.entity_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "fixed_asset_depreciation_run", "fixed_asset",
                payload.asset_id or "batch", {"period": res["period"], "posted": res["posted"],
                                              "total": res["total_amount"]})
    return res


@router.get("/fixed-assets/{asset_id}")
async def get_fixed_asset(asset_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "fixed_asset", "view")
    a = await svc.get_asset(asset_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Aset tidak ditemukan")
    return a


@router.patch("/fixed-assets/{asset_id}")
async def patch_fixed_asset(asset_id: str, payload: FixedAssetPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "fixed_asset", "update")
    try:
        a = await svc.update_asset(asset_id, payload.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if a is None:
        raise HTTPException(status_code=404, detail="Aset tidak ditemukan")
    await audit(actor.get("name", ""), "fixed_asset_updated", "fixed_asset", asset_id, {})
    return a


@router.post("/fixed-assets/{asset_id}/dispose")
async def dispose_fixed_asset(asset_id: str, payload: DisposeIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "fixed_asset", "dispose")
    try:
        a = await svc.dispose_asset(asset_id, payload.proceeds, actor,
                                    date=payload.date or "", note=payload.note or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "fixed_asset_disposed", "fixed_asset", asset_id,
                {"proceeds": payload.proceeds, "gain_loss": (a.get("disposal") or {}).get("gain_loss")})
    return a


# ── FASE E-7 (E7g) — PINDAH ASET TETAP ANTAR-PT ──────────────────────────────
@router.post("/fixed-assets/{asset_id}/transfer")
async def transfer_fixed_asset(asset_id: str, payload: FixedAssetTransferIn,
                               request: Request) -> Dict[str, Any]:
    """Pindahkan aset ke badan usaha lain di dalam grup (nilai buku + masa manfaat sisa).

    Bukan sekadar mengganti `entity_id`: aset lahir kembali di PT penerima, akumulasi
    penyusutan di PT pengirim dihapus lewat jurnal, dan laba pindah (bila harga di atas
    nilai buku) ikut dieliminasi di konsolidasi grup — karena pembelinya PT sendiri.
    """
    actor = await require_permission(request, "fixed_asset", "update")
    ctx = await entity_ctx(request)
    if payload.to_entity_id not in ctx.allowed_entity_ids:
        raise HTTPException(
            status_code=403,
            detail=("Anda tidak berwenang di badan usaha penerima — minta admin/manajer "
                    "yang ditugaskan di sana yang memindahkan asetnya."))
    try:
        res = await svc.transfer_to_entity(asset_id, payload.model_dump(), actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "fixed_asset_transferred", "fixed_asset", asset_id,
                {"to_entity_id": payload.to_entity_id, "price": res["price"],
                 "book_value": res["book_value"], "gain": res["gain"],
                 "new_asset": res["new_asset"]["number"]})
    return res


@router.post("/fixed-assets/{asset_id}/transfer/settle")
async def settle_fixed_asset_transfer(asset_id: str, payload: FixedAssetTransferSettleIn,
                                      request: Request) -> Dict[str, Any]:
    """Catat pembayaran utang antar-PT atas aset yang dipindah (uang benar-benar pindah)."""
    actor = await require_permission(request, "fixed_asset", "update")
    try:
        res = await svc.settle_transfer(asset_id, actor, payload.note or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "fixed_asset_transfer_settled", "fixed_asset",
                asset_id, res)
    return res
