"""M1 — Process Recipes router (resep konversi input→output + tarif + forecast).

Koleksi kanonik `process_recipes` (prefix prcp_), SCOPED per entitas.
Snapshot nama produk/makloon disimpan agar tampilan tak perlu join.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument

from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc
from entity_scope import entity_ctx, resolve_list_scope
from schemas import ProcessRecipeCreate, ForecastPreviewIn, GenericPatch
from services.process_recipe_service import compute_forecast

router = APIRouter(prefix="/api")

_ALLOWED = {"name", "process_type", "input_product_id", "input_stage",
            "output_product_id", "output_stage", "yield_factor", "waste_pct",
            "byproduct_pct", "byproduct_product_id", "default_makloon_id",
            "default_tariff", "tariff_unit", "aux_cost_default", "formula",
            "notes", "status", "entity_id"}


async def _snap_product(pid: str) -> Dict[str, str]:
    if not pid:
        return {"sku": "", "name": "", "base_unit": ""}
    p = await db.products.find_one({"id": pid}, {"_id": 0, "sku": 1, "name": 1, "base_unit": 1})
    return {"sku": (p or {}).get("sku", ""), "name": (p or {}).get("name", ""),
            "base_unit": (p or {}).get("base_unit", "")}


async def _enrich(doc: Dict[str, Any]) -> Dict[str, Any]:
    inp = await _snap_product(doc.get("input_product_id", ""))
    out = await _snap_product(doc.get("output_product_id", ""))
    doc["input_sku"], doc["input_name"], doc["input_unit"] = inp["sku"], inp["name"], inp["base_unit"]
    doc["output_sku"], doc["output_name"], doc["output_unit"] = out["sku"], out["name"], out["base_unit"]
    if doc.get("byproduct_product_id"):
        by = await _snap_product(doc.get("byproduct_product_id", ""))
        doc["byproduct_sku"], doc["byproduct_name"], doc["byproduct_unit"] = by["sku"], by["name"], by["base_unit"]
    else:
        doc["byproduct_sku"], doc["byproduct_name"], doc["byproduct_unit"] = "", "", ""
    if doc.get("default_makloon_id"):
        mk = await db.makloons.find_one({"id": doc["default_makloon_id"]}, {"_id": 0, "name": 1})
        doc["default_makloon_name"] = (mk or {}).get("name", "")
    else:
        doc["default_makloon_name"] = ""
    return doc


@router.get("/process-recipes")
async def list_recipes(request: Request, entity_id: str = None, status: str = None,
                       process_type: str = None) -> List[Dict[str, Any]]:
    await require_permission(request, "process_recipe", "view")
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if process_type:
        query["process_type"] = process_type
    query = resolve_list_scope("process_recipes", query, ctx, entity_id)
    rows = await db.process_recipes.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [await _enrich(safe_doc(r)) for r in rows]


@router.post("/process-recipes")
async def create_recipe(payload: ProcessRecipeCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "process_recipe", "create")
    ctx = await entity_ctx(request)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nama resep wajib diisi")
    doc = {
        "id": new_id("prcp"),
        "name": payload.name.strip(),
        "process_type": (payload.process_type or "tenun").strip(),
        "input_product_id": payload.input_product_id,
        "input_stage": payload.input_stage,
        "output_product_id": payload.output_product_id,
        "output_stage": payload.output_stage,
        "yield_factor": float(payload.yield_factor or 0),
        "waste_pct": float(payload.waste_pct or 0),
        "byproduct_pct": float(payload.byproduct_pct or 0),
        "byproduct_product_id": payload.byproduct_product_id,
        "default_makloon_id": payload.default_makloon_id,
        "default_tariff": float(payload.default_tariff or 0),
        "tariff_unit": (payload.tariff_unit or "output").strip(),
        "aux_cost_default": float(payload.aux_cost_default or 0),
        "formula": (payload.formula or "").strip(),
        "notes": payload.notes,
        "entity_id": payload.entity_id or ctx.active_entity_id,
        "status": "active",
        "created_by": payload.created_by or actor.get("name", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.process_recipes.insert_one(doc)
    await audit(actor.get("name", ""), "recipe_created", "process_recipe", doc["id"], {"name": doc["name"]})
    return await _enrich(safe_doc(doc))


@router.patch("/process-recipes/{recipe_id}")
async def update_recipe(recipe_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "process_recipe", "update")
    rec = await db.process_recipes.find_one({"id": recipe_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Resep tidak ditemukan")
    updates = {k: v for k, v in (payload.data or {}).items() if k in _ALLOWED}
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diupdate")
    for numf in ("yield_factor", "waste_pct", "byproduct_pct", "default_tariff", "aux_cost_default"):
        if numf in updates:
            try:
                updates[numf] = float(updates[numf] or 0)
            except (ValueError, TypeError):
                updates[numf] = 0
    updates["updated_at"] = now_iso()
    updated = await db.process_recipes.find_one_and_update(
        {"id": recipe_id}, {"$set": updates},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor.get("name", ""), "recipe_updated", "process_recipe", recipe_id, updates)
    return await _enrich(safe_doc(updated))


@router.delete("/process-recipes/{recipe_id}")
async def deactivate_recipe(recipe_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "process_recipe", "delete")
    rec = await db.process_recipes.find_one({"id": recipe_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Resep tidak ditemukan")
    updated = await db.process_recipes.find_one_and_update(
        {"id": recipe_id}, {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor.get("name", ""), "recipe_deactivated", "process_recipe", recipe_id, {})
    return await _enrich(safe_doc(updated))


@router.post("/process-recipes/forecast")
async def preview_forecast(payload: ForecastPreviewIn, request: Request) -> Dict[str, Any]:
    await require_permission(request, "process_recipe", "view")
    return await compute_forecast(payload.model_dump())
