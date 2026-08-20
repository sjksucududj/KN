"""Product Categories router (EPIC2) — Master Kategori Produk.

Koleksi kanonik: `product_categories` (prefix cat_).
Master kategori dipakai sebagai sumber dropdown di form produk dan basis
snapshot kategori pada SO line (untuk laporan & insentif per kategori).

Kontrak KN3: respons ARRAY/OBJEK telanjang (tanpa envelope). PATCH memakai
GenericPatch (`{data:{...}}`) agar konsisten dengan adminPatch FE.
"""
import re
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc

router = APIRouter(prefix="/api")


class CategoryPayload(BaseModel):
    code: str = ""
    name: str
    base_unit: str = "meter"
    description: str = ""
    sort_order: int = 0
    status: str = "active"


class GenericPatch(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug_code(name: str) -> str:
    base = _SLUG_RE.sub("-", (name or "").strip().lower()).strip("-")
    return (base or "kategori").upper()[:24]


async def _with_counts(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Lampirkan product_count (jumlah produk memakai kategori ini, by name)."""
    out = []
    for row in rows:
        doc = safe_doc(row)
        doc["product_count"] = await db.products.count_documents({"category": doc.get("name")})
        out.append(doc)
    return out


@router.get("/product-categories")
async def list_categories(request: Request) -> List[Dict[str, Any]]:
    await require_permission(request, "product", "view")
    rows = await db.product_categories.find({}, {"_id": 0}).to_list(500)
    rows.sort(key=lambda c: (c.get("sort_order", 0), c.get("name", "")))
    return await _with_counts(rows)


@router.post("/product-categories")
async def create_category(payload: CategoryPayload, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "create")
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nama kategori wajib diisi")
    if await db.product_categories.find_one({"name": name}, {"_id": 0}):
        raise HTTPException(status_code=409, detail="Nama kategori sudah digunakan")
    code = (payload.code or "").strip().upper() or _slug_code(name)
    if await db.product_categories.find_one({"code": code}, {"_id": 0}):
        raise HTTPException(status_code=409, detail="Kode kategori sudah digunakan")
    category = payload.model_dump()
    category.update({
        "id": new_id("cat"),
        "name": name,
        "code": code,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    await db.product_categories.insert_one(category)
    await audit(actor["name"], "category_created", "product", category["id"], category)
    doc = safe_doc(category)
    doc["product_count"] = 0
    return doc


@router.patch("/product-categories/{category_id}")
async def update_category(category_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "update")
    allowed = ["code", "name", "base_unit", "description", "sort_order", "status"]
    data = {k: v for k, v in payload.data.items() if k in allowed}
    if "name" in data:
        data["name"] = (data["name"] or "").strip()
        if not data["name"]:
            raise HTTPException(status_code=400, detail="Nama kategori tidak boleh kosong")
        dup = await db.product_categories.find_one(
            {"name": data["name"], "id": {"$ne": category_id}}, {"_id": 0})
        if dup:
            raise HTTPException(status_code=409, detail="Nama kategori sudah digunakan")
    if "code" in data:
        data["code"] = (data["code"] or "").strip().upper()
    existing = await db.product_categories.find_one({"id": category_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan")
    # Jika nama berubah, propagasikan rename ke produk yang memakainya (jaga konsistensi).
    new_name = data.get("name")
    if new_name and new_name != existing.get("name"):
        await db.products.update_many({"category": existing.get("name")}, {"$set": {"category": new_name}})
    data["updated_at"] = now_iso()
    category = await db.product_categories.find_one_and_update(
        {"id": category_id}, {"$set": data},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    await audit(actor["name"], "category_updated", "product", category_id, category)
    doc = safe_doc(category)
    doc["product_count"] = await db.products.count_documents({"category": doc.get("name")})
    return doc


@router.delete("/product-categories/{category_id}")
async def delete_category(category_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "delete")
    existing = await db.product_categories.find_one({"id": category_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan")
    in_use = await db.products.count_documents({"category": existing.get("name")})
    if in_use > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Kategori dipakai {in_use} produk — nonaktifkan tidak diizinkan. Pindahkan produk dulu.",
        )
    category = await db.product_categories.find_one_and_update(
        {"id": category_id},
        {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    await audit(actor["name"], "category_deactivated", "product", category_id, category)
    return safe_doc(category)
