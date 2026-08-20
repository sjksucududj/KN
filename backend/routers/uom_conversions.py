"""FASE B — Router Konversi Satuan (registry GLOBAL + toleransi + pratinjau).

Rujukan: `docs/KN_22_PLAN_FASE_B_UOM.md` · keputusan **D-06/D-07** (KN_18 §11).
Semua endpoint memakai prefix `/api` (aturan ingress) dan permission `product`
(master data) — TIDAK membuat modul izin baru (R3).

RBAC (memakai modul izin `uom` yang SUDAH ADA — bukan modul izin baru, R3):
  * lihat (`uom:view`)   → admin, manager, sales, warehouse (semua boleh melihat &
    memakai pratinjau konversi agar transparan di lapangan)
  * ubah  (`uom:update`) → default hanya **admin**; dapat diberikan ke manager kapan pun
    lewat **Pengaturan & Master Data → Permissions** (matriks izin) tanpa deploy.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request

from db import db
from dependencies import audit, require_permission
from entity_scope import EntityContext, entity_ctx, resolve_list_scope
from schemas_uom import (UomConvertIn, UomRuleIn, UomRulePatch, UomSettingsIn,
                         UomVarianceIn)
from services import uom_rules_service as rules
from services import uom_service

router = APIRouter(prefix="/api")


@router.get("/uom-conversions/catalog")
async def get_catalog(request: Request) -> Dict[str, Any]:
    """Katalog satuan + jenis aturan + formula (SSOT FE — tanpa hardcode di komponen).

    FASE U — katalog benih (`UNIT_CATALOG`) di-**overlay** baris MASTER `uoms` yang
    aktif, memakai pola FASE T (`domain_registry` = benih, master = nilai hidup):
    satuan yang ditambah pemilik (mis. `PANEL`) langsung muncul di pemilih satuan di
    layar tanpa satu baris kode diubah. Kata satuan yang dipakai FE tetap **alias
    pertama** (yaitu kata yang benar-benar tersimpan di dokumen: `yard`, `kg`, `panel`),
    supaya tidak lahir kosakata ke-2 di layar.
    """
    await require_permission(request, "uom", "view")
    snap = rules.catalog_snapshot()
    master_rows = await uom_service.load_uom_rows()
    snap["units_master"] = [
        {k: r.get(k) for k in ("code", "name", "base_type", "precision",
                               "factor_to_base", "status", "aliases",
                               "factor_per_document")}
        for r in master_rows]
    dim_of = {"length": "length", "weight": "weight", "count": "count", "area": "area"}
    known = {u["code"] for u in snap["units"]}
    tambahan = []
    for r in master_rows:
        if (r.get("status") or "active") != "active":
            continue
        aliases = [str(a).strip().lower() for a in (r.get("aliases") or []) if str(a).strip()]
        kode_fe = aliases[0] if aliases else str(r.get("code") or "").lower()
        if not kode_fe or kode_fe in known:
            continue
        tambahan.append({
            "code": kode_fe,
            "label": f"{r.get('name')} ({r.get('code')})",
            "dimension": dim_of.get(str(r.get("base_type") or "").lower(), "count"),
            "aliases": [a for a in aliases[1:]] + [str(r.get("code") or "").lower()],
            "from_master": True,
            "factor_per_document": bool(r.get("factor_per_document")),
        })
        known.add(kode_fe)
    if tambahan:
        snap["units"] = list(snap["units"]) + tambahan
    ctx = await entity_ctx(request)
    snap["settings"] = await rules.get_settings(ctx.active_entity_id)
    return snap


@router.get("/uom-conversions/rules")
async def list_rules(request: Request, status: str = "", dimension: str = "",
                     kind: str = "") -> Dict[str, Any]:
    await require_permission(request, "uom", "view")
    rows = await rules.list_rules(status=status, dimension=dimension, kind=kind)
    return {"rules": rows, "total": len(rows),
            "active": sum(1 for r in rows if r.get("status") == "active")}


@router.post("/uom-conversions/rules")
async def create_rule(payload: UomRuleIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "uom", "update")
    try:
        doc = await rules.create_rule(payload.model_dump(), actor.get("name", ""))
    except rules.UomRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor.get("name", ""), "uom_rule_created", "uom_conversion_rule", doc["id"],
                {"from": doc["from_unit"], "to": doc["to_unit"], "kind": doc["kind"],
                 "factor": doc.get("factor")}, "Fase B — aturan konversi global")
    return doc


@router.patch("/uom-conversions/rules/{rule_id}")
async def update_rule(rule_id: str, payload: UomRulePatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "uom", "update")
    try:
        doc = await rules.update_rule(rule_id, payload.model_dump(exclude_none=True),
                                      actor.get("name", ""))
    except rules.UomRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor.get("name", ""), "uom_rule_updated", "uom_conversion_rule", rule_id,
                {"from": doc.get("from_unit"), "to": doc.get("to_unit"),
                 "factor": doc.get("factor"), "status": doc.get("status")})
    return doc


@router.post("/uom-conversions/rules/{rule_id}/status")
async def toggle_rule(rule_id: str, request: Request, status: str = "inactive") -> Dict[str, Any]:
    actor = await require_permission(request, "uom", "update")
    try:
        doc = await rules.set_rule_status(rule_id, status, actor.get("name", ""))
    except rules.UomRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor.get("name", ""), "uom_rule_status", "uom_conversion_rule", rule_id,
                {"status": doc.get("status")})
    return doc


@router.get("/uom-conversions/settings")
async def get_settings(request: Request) -> Dict[str, Any]:
    """FASE E-4 (E4.5) — toleransi konversi badan usaha AKTIF (global + override-nya)."""
    await require_permission(request, "uom", "view")
    ctx = await entity_ctx(request)
    return await rules.get_settings(ctx.active_entity_id)


@router.put("/uom-conversions/settings")
async def update_settings(payload: UomSettingsIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "uom", "update")
    try:
        doc = await rules.update_settings(payload.model_dump(exclude_none=True),
                                          actor.get("name", ""))
    except rules.UomRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor.get("name", ""), "uom_settings_updated", "system_settings", "uom",
                {"warn_pct": doc["warn_pct"], "block_pct": doc["block_pct"],
                 "allow_override": doc["allow_override"], "precision": doc["precision"]},
                "Fase B — toleransi selisih konversi")
    return doc


@router.post("/uom-conversions/convert")
async def convert_preview(payload: UomConvertIn, request: Request) -> Dict[str, Any]:
    """Pratinjau konversi + JEJAK (dipakai komponen “Input & Konversi” di FE).

    `product_id` opsional: bila kosong dipakai `base_unit`/`gramasi`/`lebar` dari payload
    sehingga form produk baru pun bisa melihat hasil konversi sebelum disimpan.
    """
    await require_permission(request, "uom", "view")
    product: Dict[str, Any] = {}
    if payload.product_id:
        product = await db.products.find_one({"id": payload.product_id}, {"_id": 0}) or {}
        if not product:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    product = dict(product)
    if payload.base_unit:
        product["base_unit"] = payload.base_unit
    product.setdefault("base_unit", "meter")
    if payload.gramasi is not None:
        product["gramasi"] = payload.gramasi
    if payload.lebar is not None:
        product["lebar"] = payload.lebar
    try:
        trail = await rules.convert_with_trail(
            product, payload.qty, payload.from_unit, payload.to_unit, context="preview")
    except rules.UomRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    from services.uom_service import product_kg_per_meter
    trail["product_sku"] = product.get("sku", "")
    trail["kg_per_meter"] = product_kg_per_meter(product) or None
    return trail


@router.post("/uom-conversions/check-variance")
async def check_variance(payload: UomVarianceIn, request: Request) -> Dict[str, Any]:
    """Cek selisih hasil konversi vs ukur/timbang aktual memakai toleransi tersimpan."""
    await require_permission(request, "uom", "view")
    return await rules.check_variance(payload.expected, payload.actual, label=payload.label)


@router.get("/uom-conversions/usage")
async def conversion_usage(request: Request, limit: int = 25,
                           ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    """Jejak konversi terakhir dari dokumen nyata (bukti D-07 untuk audit).

    F0-C: `purchase_orders` · `purchase_requisitions` · `wms_tasks` adalah koleksi
    SCOPED. Sebelumnya jejak ini menampilkan nomor dokumen SEMUA PT — warehouse
    PT A bisa membaca nomor PO/PR PT B. Kini seluruh query lewat
    `resolve_list_scope()` (entitas aktif; `X-Entity-Id: all` hanya untuk role
    lintas-entitas).
    """
    await require_permission(request, "uom", "view")
    limit = max(1, min(int(limit or 25), 100))
    out: List[Dict[str, Any]] = []
    pos = await db.purchase_orders.find(
        resolve_list_scope("purchase_orders", {"items.uom_trail": {"$exists": True}}, ctx),
        {"_id": 0, "po_number": 1, "items": 1, "created_at": 1}).sort(
            "created_at", -1).to_list(limit)
    for po in pos:
        for it in po.get("items", []):
            t = it.get("uom_trail") or {}
            if t:
                out.append({"doc_type": "Pesanan Pembelian", "number": po.get("po_number", ""),
                            "sku": it.get("sku", ""), **t})
    prs = await db.purchase_requisitions.find(
        resolve_list_scope("purchase_requisitions", {"items.uom_trail": {"$exists": True}}, ctx),
        {"_id": 0, "number": 1, "items": 1, "created_at": 1}).sort(
            "created_at", -1).to_list(limit)
    for pr in prs:
        for it in pr.get("items", []):
            t = it.get("uom_trail") or {}
            if t:
                out.append({"doc_type": "Permintaan Pembelian", "number": pr.get("number", ""),
                            "sku": it.get("sku", ""), **t})
    tasks = await db.wms_tasks.find(
        resolve_list_scope("wms_tasks", {"uom_trail": {"$exists": True}}, ctx),
        {"_id": 0, "po_number": 1, "sku": 1, "uom_trail": 1, "conversion_variance": 1,
         "updated_at": 1}).sort("updated_at", -1).to_list(limit)
    for t in tasks:
        out.append({"doc_type": "Penerimaan (GR)", "number": t.get("po_number", ""),
                    "sku": t.get("sku", ""), **(t.get("uom_trail") or {}),
                    "variance": t.get("conversion_variance")})
    out.sort(key=lambda r: str(r.get("converted_at") or ""), reverse=True)
    return {"usage": out[:limit], "total": len(out)}
