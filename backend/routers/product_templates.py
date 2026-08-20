"""F1b — Product Templates & Variants router (ADDITIVE/non-destruktif).

Katalog SHARED lintas-entitas (D1). Akses: permission module "product"
(create/update/delete = admin; view = semua). Kontrak respons OBJEK/ARRAY telanjang.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request, Query

from dependencies import require_permission, audit
from schemas import ProductTemplateCreate, ProductTemplatePatch, VariantGenerateIn, AssignProductsIn
from services import product_template_service as svc

router = APIRouter(prefix="/api")


@router.get("/product-templates")
async def list_templates(request: Request, search: str = Query("")) -> List[Dict[str, Any]]:
    await require_permission(request, "product", "view")
    return await svc.list_templates(search=search)


@router.get("/product-templates/{template_id}")
async def get_template(template_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "product", "view")
    tpl = await svc.get_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")
    return tpl


@router.post("/product-templates")
async def create_template(payload: ProductTemplateCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "create")
    try:
        tpl = await svc.create_template(payload.model_dump(), actor.get("name", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "product_template_created", "product_template", tpl["id"],
                {"name": tpl["name"], "axes": len(tpl.get("axes", []))})
    return tpl


@router.patch("/product-templates/{template_id}")
async def patch_template(template_id: str, payload: ProductTemplatePatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "update")
    tpl = await svc.update_template(template_id, payload.model_dump(exclude_none=True))
    if tpl is None:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")
    await audit(actor.get("name", ""), "product_template_updated", "product_template", template_id, {})
    return tpl


@router.delete("/product-templates/{template_id}")
async def delete_template(template_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "delete")
    try:
        res = await svc.delete_template(template_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await audit(actor.get("name", ""), "product_template_deleted", "product_template", template_id, res)
    return res


@router.post("/product-templates/{template_id}/generate-variants")
async def generate_variants(template_id: str, payload: VariantGenerateIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "create")
    try:
        res = await svc.generate_variants(template_id, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "variants_generated", "product_template", template_id,
                {"created": res["created"], "skipped": res["skipped"]})
    return res


@router.post("/product-templates/{template_id}/assign")
async def assign_products(template_id: str, payload: AssignProductsIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "update")
    try:
        res = await svc.assign_products(template_id, payload.product_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await audit(actor.get("name", ""), "variants_assigned", "product_template", template_id, res)
    return res


@router.post("/product-templates/detach")
async def detach_products(payload: AssignProductsIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "update")
    res = await svc.detach_products(payload.product_ids)
    await audit(actor.get("name", ""), "variants_detached", "product", "batch", res)
    return res
