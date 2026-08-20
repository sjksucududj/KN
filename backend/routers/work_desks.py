"""FASE E-8 (E8.7/E8.13/E8.15/E8.20) — **MEJA KERJA** Admin Sales & Finance.

Endpoint di sini TIDAK membangun mesin baru; ia menyusun antrean kerja dari mesin
yang sudah terbukti (papan pending SO · backorder · retur · permintaan internal ·
pengingat penagihan · selisih bayar · denda) dan menyediakan **satu tindakan per
baris**. Lihat `services/work_desk_service.py` untuk alasan lengkapnya.

Pembagian meja mengikuti keputusan pemilik E8.10b#2: faktur pajak & uang masuk ada di
**Meja Finance**, bukan di meja Admin Sales.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from db import db
from core_utils import safe_doc
from dependencies import require_permission, permission_matrix, audit
from entity_scope import assert_entity_access, entity_ctx, resolve_list_scope
from services import fulfillment_decision_service as fds
from services import so_verify_service as verify_svc
from services import work_desk_service as desks

router = APIRouter(prefix="/api")


class VerifyIn(BaseModel):
    note: str = ""


class FulfillmentIn(BaseModel):
    mode: str                      # interco | reorder | wait
    source_entity_id: str = ""     # wajib untuk mode `interco`
    product_ids: List[str] = []    # kosong = seluruh baris yang kurang
    note: str = ""


async def _scope(request: Request, entity_id: Optional[str]):
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("sales_orders", {}, ctx, entity_id)
    ids = ([entity_id] if entity_id and entity_id != "all"
           else list(ctx.allowed_entity_ids) if getattr(ctx, "view_all", False)
           else [ctx.active_entity_id])
    return ctx, scope, ids


async def _order_in_scope(request: Request, order_id: str) -> Dict[str, Any]:
    order = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    if not order:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    assert_entity_access(order, "sales_orders", await entity_ctx(request))
    return order


async def _assert_may_choose_source(actor: Dict[str, Any]) -> None:
    """Yang MEMILIH badan usaha sumber wajib boleh MENGESAHKANNYA.

    Dulu daftar kandidat (berisi rincian stok badan usaha lain) hanya untuk peran
    lintas-entitas. Sejak keputusan pemilik E8.10b#4, **Admin Sales** yang memutuskan
    "ambil dari PT lain" — tanpa melihat kandidat, keputusan itu tidak mungkin diambil.
    Karena itu gerbangnya dipindah ke izin `internal_request.convert` (sales & gudang
    TIDAK punya, jadi rincian stok PT lain tetap tertutup bagi mereka).
    """
    matrix = await permission_matrix()
    actions = (matrix.get(actor.get("role") or "", {}) or {}).get("internal_request", [])
    if "convert" not in actions and "*" not in actions:
        raise HTTPException(
            status_code=403,
            detail=("Rincian stok badan usaha lain bukan wewenang peran Anda. Ajukan "
                    "permintaannya saja — Admin Sales/manajer yang memilih sumbernya."))


# ═══════════════════════════════════════════════════════════════════════════
# MEJA ADMIN SALES
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/sales-admin/desk")
async def sales_admin_desk(request: Request, entity_id: str = Query("")) -> Dict[str, Any]:
    """8 antrean kerja Admin Sales + jumlah, nilai, dan umur tertua per antrean."""
    actor = await require_permission(request, "order", "confirm")
    _, scope, ids = await _scope(request, entity_id or None)
    return await desks.sales_admin_desk(actor, scope, ids)


@router.get("/sales-orders/{order_id}/verification")
async def verification_preview(order_id: str, request: Request) -> Dict[str, Any]:
    """Daftar periksa kelengkapan (read-only) — dipakai dialog sebelum Verifikasi."""
    await require_permission(request, "order", "view")
    order = await _order_in_scope(request, order_id)
    return await verify_svc.preview(order)


@router.post("/sales-orders/{order_id}/verify")
async def verify_order(order_id: str, payload: VerifyIn, request: Request) -> Dict[str, Any]:
    """E8.13 — verifikasi ADMINISTRATIF (bukan persetujuan nilai)."""
    actor = await require_permission(request, "order", "verify")
    order = await _order_in_scope(request, order_id)
    try:
        res = await verify_svc.verify(order, actor, note=payload.note)
    except verify_svc.VerifyError as exc:
        raise HTTPException(status_code=409,
                            detail={"message": str(exc), "checks": exc.checks}) from exc
    await audit(actor.get("name", ""), "sales_order_verified", "sales_orders", order_id,
                {"number": order.get("number"), "warnings": res.get("warnings", [])},
                reason=payload.note or "")
    return res


@router.get("/sales-admin/orders/{order_id}/fulfillment")
async def fulfillment_options(order_id: str, request: Request) -> Dict[str, Any]:
    """US16 — kekurangan pesanan + TIGA pilihan pemenuhan beserta kelayakannya."""
    actor = await require_permission(request, "order", "confirm")
    order = await _order_in_scope(request, order_id)
    await _assert_may_choose_source(actor)
    try:
        return await fds.options(order)
    except fds.FulfillmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sales-admin/orders/{order_id}/fulfillment-decision")
async def fulfillment_decision(order_id: str, payload: FulfillmentIn,
                               request: Request) -> Dict[str, Any]:
    """US16/E8.10b#4 — putuskan pemenuhan: ambil dari PT lain · reorder · tahan.

    Wewenang PENUH Admin Sales (tanpa persetujuan manajer). Satu-satunya penahan
    adalah ambang rupiah antar-PT di Pusat Pengaturan.
    """
    actor = await require_permission(request, "order", "confirm")
    await _order_in_scope(request, order_id)
    if payload.mode == "interco":
        await _assert_may_choose_source(actor)
    try:
        res = await fds.decide(order_id, payload.mode, actor,
                               source_entity_id=payload.source_entity_id,
                               note=payload.note, product_ids=payload.product_ids)
    except fds.FulfillmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor.get("name", ""), "fulfillment_decided", "sales_orders", order_id,
                {"mode": payload.mode, "ref": res["decision"].get("ref_number", ""),
                 "summary": res["decision"]["summary"]},
                reason=payload.note or "")
    return res


# ═══════════════════════════════════════════════════════════════════════════
# MEJA FINANCE
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/finance/desk")
async def finance_desk(request: Request, entity_id: str = Query("")) -> Dict[str, Any]:
    """5 antrean kerja Finance: faktur pajak · uang masuk · selisih · denda · jatuh tempo.

    Gerbangnya `ar_receipt.create`, **bukan** `ar_receipt.view`. Sales tetap boleh
    MELIHAT kwitansi (dia yang ditanya pelanggan "pembayaran saya sudah masuk belum?"),
    jadi izin `view` masih dimilikinya — memakai `view` sebagai gerbang membuat Meja
    Finance terbuka untuk sales (terukur: 200, bukan 403), padahal keputusan pemilik
    E8.10b#2 menaruh uang masuk & pajak keluaran di peran `finance`. Yang membedakan
    meja ini adalah wewenang MENCATAT.
    """
    actor = await require_permission(request, "ar_receipt", "create")
    _, scope, ids = await _scope(request, entity_id or None)
    return await desks.finance_desk(actor, scope, ids)
