"""FASE E — Router `supplier_items` (Barang Supplier / katalog versi supplier).

RBAC memakai resource **`supplier_item`**:
  * lihat / cari  → `view`   (admin, manager, warehouse)
  * kelola        → `create|update|delete` (admin, manager)
  * impor massal  → `import` (admin, manager)

Semua endpoint ber-prefix `/api` dan mengembalikan ARRAY/OBJEK telanjang (kontrak KN),
kecuali saat paginasi diminta (`?page=`).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from dependencies import audit, require_permission
from entity_scope import entity_ctx, resolve_list_scope
from pagination import envelope, get_page_params, is_paged
from schemas_supplier_items import (SupplierItemCreate, SupplierItemImportIn,
                                    SupplierItemPatch)
from services import supplier_item_service as sis

router = APIRouter(prefix="/api")


def _err(exc: Exception, code: int = 400) -> HTTPException:
    return HTTPException(status_code=code, detail=str(exc))


def _scope_entity(ctx: Any, entity_id: Optional[str]) -> str:
    """Entitas riil untuk penulisan (tidak boleh 'all')."""
    ent = (entity_id or "").strip()
    if ent in ("", "all"):
        ent = getattr(ctx, "active_entity_id", "") or ""
    if not ent or ent == "all":
        raise HTTPException(status_code=400,
                            detail="Pilih ENTITAS spesifik (bukan 'Semua Entitas') untuk menyimpan barang supplier.")
    return ent


# ── Daftar · statistik · template ────────────────────────────────────
@router.get("/supplier-items")
async def list_supplier_items(request: Request, q: str = "", supplier_id: str = "",
                              product_id: str = "", status: str = "",
                              entity_id: Optional[str] = None, limit: int = 200) -> Any:
    await require_permission(request, "supplier_item", "view")
    ctx = await entity_ctx(request)
    flt: Dict[str, Any] = resolve_list_scope("supplier_items", {}, ctx, entity_id)
    for key, val in (("supplier_id", supplier_id), ("product_id", product_id),
                     ("status", status)):
        if val:
            flt[key] = val
    if is_paged(request):
        page, size, term, sort = get_page_params(request)
        rows = await sis.list_items(flt, q=q or term, limit=size, skip=(page - 1) * size,
                                    sort=sort or "-created_at")
        total = await sis.count_items(flt) if not (q or term) else len(
            await sis.list_items(flt, q=q or term, limit=1000))
        return envelope(rows, total, page, size)
    return await sis.list_items(flt, q=q, limit=limit)


@router.get("/supplier-items/stats")
async def supplier_item_stats(request: Request, supplier_id: str = "",
                              entity_id: Optional[str] = None) -> Dict[str, Any]:
    await require_permission(request, "supplier_item", "view")
    ctx = await entity_ctx(request)
    flt = resolve_list_scope("supplier_items", {}, ctx, entity_id)
    if supplier_id:
        flt["supplier_id"] = supplier_id
    return await sis.stats(flt)


@router.get("/supplier-items/lookup")
async def lookup_supplier_item(request: Request, supplier_sku: str,
                               supplier_id: str = "",
                               entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Cari barang KN dari KODE SUPPLIER (kasus nyata: operator hanya pegang kode supplier)."""
    await require_permission(request, "supplier_item", "view")
    ctx = await entity_ctx(request)
    ent = (entity_id or "").strip()
    if ent == "all":
        ent = ""
    try:
        row = await sis.lookup(supplier_sku=supplier_sku, supplier_id=supplier_id,
                               entity_id=ent or (getattr(ctx, "active_entity_id", "") or ""))
    except sis.SupplierItemError as exc:
        raise _err(exc) from exc
    if not row:
        raise HTTPException(status_code=404,
                            detail=f"Kode supplier '{supplier_sku}' belum terdaftar di Barang Supplier.")
    return {"found": True, "item": row}


@router.get("/supplier-items/import-template")
async def import_template(request: Request) -> Response:
    await require_permission(request, "supplier_item", "view")
    return Response(content=sis.csv_template(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="template_barang_supplier.csv"'})


# ── Impor massal (E-01) ──────────────────────────────────────────────
@router.post("/supplier-items/import")
async def import_supplier_items(request: Request, payload: SupplierItemImportIn) -> Dict[str, Any]:
    """Impor via JSON: `rows[]` ATAU `csv_text`. `dry_run=true` = pratinjau."""
    actor = await require_permission(request, "supplier_item", "import")
    ctx = await entity_ctx(request)
    ent = _scope_entity(ctx, payload.entity_id)
    rows: List[Dict[str, Any]] = [r.model_dump() for r in payload.rows]
    if payload.csv_text.strip():
        rows = sis.parse_csv_text(payload.csv_text)
    if not rows:
        raise HTTPException(status_code=400, detail="Tidak ada baris untuk diimpor.")
    try:
        result = await sis.import_rows(rows, supplier_id=payload.supplier_id, entity_id=ent,
                                       actor=actor.get("name", ""), dry_run=payload.dry_run)
    except sis.SupplierItemError as exc:
        raise _err(exc) from exc
    if not payload.dry_run:
        await audit(actor, "import", "supplier_items", payload.supplier_id,
                    f"Impor barang supplier: +{result['created']} baru · {result['updated']} diperbarui")
    return result


@router.post("/supplier-items/import-file")
async def import_supplier_items_file(request: Request, file: UploadFile = File(...),
                                     supplier_id: str = "", entity_id: str = "",
                                     dry_run: bool = True) -> Dict[str, Any]:
    """Impor via UNGGAH BERKAS CSV/XLSX (multipart). `dry_run=true` = pratinjau."""
    actor = await require_permission(request, "supplier_item", "import")
    ctx = await entity_ctx(request)
    ent = _scope_entity(ctx, entity_id)
    content = await file.read()
    try:
        rows = sis.parse_file(content, file.filename or "")
        if not rows:
            raise HTTPException(status_code=400, detail="Berkas kosong atau format tidak dikenal.")
        result = await sis.import_rows(rows, supplier_id=supplier_id, entity_id=ent,
                                       actor=actor.get("name", ""), dry_run=dry_run)
    except sis.SupplierItemError as exc:
        raise _err(exc) from exc
    result["filename"] = file.filename or ""
    if not dry_run:
        await audit(actor, "import", "supplier_items", supplier_id,
                    f"Impor berkas {file.filename}: +{result['created']} baru · {result['updated']} diperbarui")
    return result


# ── CRUD ─────────────────────────────────────────────────────────────
@router.get("/supplier-items/{sid}")
async def get_supplier_item(request: Request, sid: str) -> Dict[str, Any]:
    await require_permission(request, "supplier_item", "view")
    row = await sis.get_item(sid)
    if not row:
        raise HTTPException(status_code=404, detail="Barang supplier tidak ditemukan")
    return row


@router.post("/supplier-items")
async def create_supplier_item(request: Request, payload: SupplierItemCreate) -> Dict[str, Any]:
    actor = await require_permission(request, "supplier_item", "create")
    ctx = await entity_ctx(request)
    ent = _scope_entity(ctx, payload.entity_id)
    try:
        row = await sis.create_item(payload.model_dump(), entity_id=ent,
                                    actor=actor.get("name", ""))
    except sis.SupplierItemError as exc:
        raise _err(exc) from exc
    await audit(actor, "create", "supplier_items", row["id"],
                f"Barang supplier {row['supplier_sku']} → {row['sku']}")
    return row


@router.patch("/supplier-items/{sid}")
async def patch_supplier_item(request: Request, sid: str,
                              payload: SupplierItemPatch) -> Dict[str, Any]:
    actor = await require_permission(request, "supplier_item", "update")
    body = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        row = await sis.patch_item(sid, body, actor=actor.get("name", ""))
    except sis.SupplierItemError as exc:
        raise _err(exc) from exc
    await audit(actor, "update", "supplier_items", sid, "Barang supplier diperbarui")
    return row


@router.delete("/supplier-items/{sid}")
async def delete_supplier_item(request: Request, sid: str) -> Dict[str, Any]:
    actor = await require_permission(request, "supplier_item", "delete")
    try:
        out = await sis.delete_item(sid)
    except sis.SupplierItemError as exc:
        code = 409 if "dipakai" in str(exc) else 400
        raise _err(exc, code) from exc
    await audit(actor, "delete", "supplier_items", sid, "Barang supplier dihapus")
    return out
