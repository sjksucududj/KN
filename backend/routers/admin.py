"""Admin router: master data import/export, permissions, bulk ops."""
import csv
import io
import os
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from db import db
from dependencies import require_permission, audit
from entity_scope import assert_write_entity, entity_ctx
from core_utils import new_id, now_iso, safe_doc, parse_decimal
import domain_registry as _dr        # Fase A · R7 — SSOT domain (stamp defaults)
from schemas import PermissionUpdate
from permissions_config import DEFAULT_PERMISSIONS
from services.demo_seed_service import run_demo_seed

try:
    import openpyxl
    XLSX_AVAILABLE = True
except ImportError:
    XLSX_AVAILABLE = False

import math
from urllib.parse import urlparse

DEFAULT_PRODUCT_IMG = ("https://images.unsplash.com/photo-1774679817333-decf0d988dd5"
                       "?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85")
_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: Any) -> str:
    """S#074 (IMP-CSV-INJECTION): cegah CSV/formula injection saat EXPORT — sel yang
    diawali =,+,-,@,TAB,CR diberi prefiks apostrof agar tidak dieksekusi Excel/Sheets."""
    s = "" if value is None else str(value)
    return ("'" + s) if s[:1] in _FORMULA_PREFIX else s


def _sanitize_rows(rows: List[Dict[str, Any]], fields: List[str]) -> List[Dict[str, Any]]:
    return [{f: _csv_safe(r.get(f, "")) for f in fields} for r in rows]


def _safe_image_url(raw: str) -> Optional[str]:
    """S#074 (IMP-IMG-XSS): izinkan hanya http/https atau path relatif; tolak
    javascript:/data:/vbscript: dll. Return None bila skema tidak aman."""
    s = (raw or "").strip()
    if not s:
        return ""
    if s.startswith("/"):
        return s
    scheme = (urlparse(s).scheme or "").lower()
    return s if scheme in ("http", "https") else None


router = APIRouter(prefix="/api")


def _parse_csv_or_xlsx(content: bytes, filename: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """Parse CSV or XLSX, return (headers, rows)."""
    if filename.endswith(".xlsx") and XLSX_AVAILABLE:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            raise HTTPException(status_code=400, detail="File XLSX tidak valid atau rusak.")
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return [], []
        headers = [str(h).strip() for h in rows[0]]
        data = []
        for row in rows[1:]:
            if any(cell is not None for cell in row):
                data.append({headers[i]: str(row[i] or "").strip() for i in range(len(headers))})
        return headers, data
    else:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400,
                                detail="File bukan UTF-8. Simpan ulang sebagai CSV berenkoding UTF-8.")
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        return list(headers), list(reader)


def _validate_and_enrich_product(row: Dict[str, str], idx: int) -> Tuple[Optional[Dict], Optional[str]]:
    """Validate a product row. Returns (product_dict, error_msg)."""
    errors = []
    sku = row.get("sku", "").strip()
    name = row.get("name", "").strip()
    if not sku:
        errors.append("SKU wajib diisi")
    if not name:
        errors.append("Nama wajib diisi")
    try:
        price = float(row.get("price", 0) or 0)
    except ValueError:
        errors.append("Price harus angka")
        price = 0
    if not math.isfinite(price) or price < 0:                     # S#074 IMP-NEG/INF-PRICE
        errors.append("Price harus angka >= 0 dan berhingga")
    raw_img = row.get("image", "").strip()                        # S#074 IMP-IMG-XSS
    img = _safe_image_url(raw_img)
    if img is None:
        errors.append("URL gambar tidak valid (hanya http/https diizinkan)")
    if errors:
        return None, f"Baris {idx + 2}: {', '.join(errors)}"
    prod = {
        "sku": sku, "name": name,
        "category": row.get("category", "Kain").strip() or "Kain",
        "variant": row.get("variant", "Regular").strip() or "Regular",
        "color": row.get("color", "Natural").strip() or "Natural",
        "motif": row.get("motif", "Polos").strip() or "Polos",
        "grade": row.get("grade", "A").strip() or "A",
        "supplier": row.get("supplier", "Internal").strip() or "Internal",
        "base_unit": row.get("base_unit", "meter").strip() or "meter",
        "price": price,
        "image": img or DEFAULT_PRODUCT_IMG,
        "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
        # ── Fase A · PS-01/02/03 — kolom domain tekstil (opsional di file) ──
        "stage": row.get("stage", "").strip(),
        "fabric_type": row.get("fabric_type", "").strip(),
        "yarn_count": row.get("yarn_count", "").strip(),
        "yarn_count_system": row.get("yarn_count_system", "").strip(),
    }
    for num_field, keys in (("gramasi", ("gramasi", "gsm")), ("lebar", ("lebar", "width"))):
        raw = ""
        for k in keys:
            raw = row.get(k, "") or raw
        try:
            prod[num_field] = parse_decimal(str(raw).strip() or 0)
        except ValueError:
            return None, f"Baris {idx + 2}: {num_field} harus angka (mis. 180,5)"
    try:
        # Normalisasi + lengkapi field domain; TIDAK mengarang GSM/lebar.
        # Kekurangan wajib → produk ditandai needs_review + domain_gaps (D-22).
        _dr.stamp_domain_defaults(prod, source="import_csv")
    except _dr.DomainValidationError as exc:
        return None, f"Baris {idx + 2}: {exc.message}"
    return prod, None


@router.post("/master-data/import-products")
async def import_products(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = False
) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "import")
    content = await file.read()
    _, rows = _parse_csv_or_xlsx(content, file.filename or "")
    if not rows:
        raise HTTPException(status_code=400, detail="File kosong atau format tidak dikenal")
    results = {"total": len(rows), "created": 0, "updated": 0, "errors": [], "dry_run": dry_run}
    for idx, row in enumerate(rows):
        product_data, error = _validate_and_enrich_product(row, idx)
        if error:
            results["errors"].append(error)
            continue
        existing = safe_doc(await db.products.find_one({"sku": product_data["sku"]}, {"_id": 0}))
        if dry_run:
            if existing:
                results["updated"] += 1
            else:
                results["created"] += 1
            continue
        if existing:
            await db.products.update_one(
                {"sku": product_data["sku"]},
                {"$set": {**product_data, "updated_at": now_iso()}}
            )
            results["updated"] += 1
        else:
            product_data.update({"id": new_id("prod"), "created_at": now_iso(), "updated_at": now_iso()})
            await db.products.insert_one(product_data)
            results["created"] += 1
    if not dry_run:
        await audit(actor["name"], "products_imported", "product", "bulk",
                    {"total": results["total"], "created": results["created"],
                     "updated": results["updated"], "errors": len(results["errors"])})
    return results


@router.post("/master-data/import-customers")
async def import_customers(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = False
) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "import")
    content = await file.read()
    _, rows = _parse_csv_or_xlsx(content, file.filename or "")
    if not rows:
        raise HTTPException(status_code=400, detail="File kosong")
    results = {"total": len(rows), "created": 0, "updated": 0, "errors": [], "dry_run": dry_run}
    # FASE E-0 (L17) — impor pelanggan WAJIB masuk ke satu entitas: dulu pelanggan
    # hasil impor lahir tanpa `entity_id` (data yatim, terlihat lintas-PT).
    ctx = await entity_ctx(request)
    ent = assert_write_entity(ctx, "mengimpor pelanggan")
    results["entity_id"] = ent
    count = await db.customers.count_documents({})
    for idx, row in enumerate(rows):
        name = row.get("name", "").strip()
        if not name:
            results["errors"].append(f"Baris {idx + 2}: Nama wajib diisi")
            continue
        city = row.get("city", "").strip()
        address = row.get("address", "").strip()
        pic_name = row.get("pic_name", name).strip()
        phone = row.get("phone", "").strip()
        email = row.get("email", "").strip()
        existing = safe_doc(await db.customers.find_one(
            {"$and": [
                {"$or": [{"name": name}, {"email": email}] if email else [{"name": name}]},
                {"entity_id": ent},
            ]},
            {"_id": 0}
        ))
        if dry_run:
            if existing:
                results["updated"] += 1
            else:
                results["created"] += 1
            continue
        if existing:
            await db.customers.update_one(
                {"id": existing["id"]},
                {"$set": {"name": name, "pic_name": pic_name, "phone": phone,
                           "city": city, "updated_at": now_iso()}}
            )
            results["updated"] += 1
        else:
            count += 1
            customer = {
                "id": new_id("cust"), "code": f"CUST-{count:04d}",
                "entity_id": ent,
                "name": name, "pic_name": pic_name, "phone": phone, "email": email,
                "type": row.get("type", "Retail").strip() or "Retail",
                "city": city, "status": "active", "created_by": actor["name"],
                "created_at": now_iso(),
                "addresses": [{"id": new_id("addr"), "label": "Alamat Utama",
                               "recipient_name": pic_name, "phone": phone,
                               "city": city, "address": address, "is_primary": True}]
            }
            await db.customers.insert_one(customer)
            results["created"] += 1
    if not dry_run:
        await audit(actor["name"], "customers_imported", "customer", "bulk",
                    {"total": results["total"], "created": results["created"]})
    return results


@router.post("/master-data/import-warehouses")
async def import_warehouses(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = False
) -> Dict[str, Any]:
    actor = await require_permission(request, "warehouse", "import")
    content = await file.read()
    _, rows = _parse_csv_or_xlsx(content, file.filename or "")
    if not rows:
        raise HTTPException(status_code=400, detail="File kosong")
    results = {"total": len(rows), "created": 0, "updated": 0, "errors": [], "dry_run": dry_run}
    for idx, row in enumerate(rows):
        code = row.get("code", "").strip()
        name = row.get("name", "").strip()
        if not code or not name:
            results["errors"].append(f"Baris {idx + 2}: Code dan nama wajib")
            continue
        if dry_run:
            existing = await db.warehouses.find_one({"code": code}, {"_id": 0})
            if existing:
                results["updated"] += 1
            else:
                results["created"] += 1
            continue
        existing = safe_doc(await db.warehouses.find_one({"code": code}, {"_id": 0}))
        if existing:
            await db.warehouses.update_one(
                {"code": code},
                {"$set": {"name": name, "city": row.get("city", "").strip(), "updated_at": now_iso()}}
            )
            results["updated"] += 1
        else:
            wh_id = new_id("wh")
            await db.warehouses.insert_one({
                "id": wh_id, "code": code, "name": name, "city": row.get("city", "").strip(),
                "lat": None, "lng": None,
                "zones": [{"id": new_id("zone"), "name": "Zone A",
                           "racks": [{"id": new_id("rack"), "name": "Rack A1",
                                      "bins": [{"id": new_id("bin"), "code": "A1-01", "capacity": 1000}]}]}],
                "active": True, "created_at": now_iso()
            })
            results["created"] += 1
    if not dry_run:
        await audit(actor["name"], "warehouses_imported", "warehouse", "bulk",
                    {"total": results["total"], "created": results["created"]})
    return results


@router.get("/master-data/export-products")
async def export_products(request: Request) -> Response:
    await require_permission(request, "product", "export")
    products = await db.products.find({}, {"_id": 0}).to_list(1000)
    fields = ["id", "sku", "name", "category", "variant", "color", "motif", "grade",
              "supplier", "base_unit", "price", "status"]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(_sanitize_rows(products, fields))
    return Response(content=out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=products.csv"})


@router.get("/master-data/export-customers")
async def export_customers(request: Request) -> Response:
    await require_permission(request, "customer", "export")
    customers = await db.customers.find({}, {"_id": 0}).to_list(500)
    fields = ["id", "code", "name", "pic_name", "phone", "email", "type", "city", "status"]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(_sanitize_rows(customers, fields))
    return Response(content=out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=customers.csv"})


@router.get("/master-data/export-warehouses")
async def export_warehouses(request: Request) -> Response:
    await require_permission(request, "warehouse", "export")
    warehouses = await db.warehouses.find({}, {"_id": 0}).to_list(100)
    fields = ["id", "code", "name", "city", "active"]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(_sanitize_rows(warehouses, fields))
    return Response(content=out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=warehouses.csv"})


@router.get("/permissions")
async def get_permissions(request: Request) -> Dict[str, Any]:
    await require_permission(request, "permission", "view")
    record = safe_doc(await db.permission_settings.find_one({"id": "default"}, {"_id": 0}))
    return {"matrix": record.get("matrix", DEFAULT_PERMISSIONS) if record else DEFAULT_PERMISSIONS}


@router.put("/permissions")
async def update_permissions(payload: PermissionUpdate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "permission", "update")
    await db.permission_settings.update_one(
        {"id": "default"}, {"$set": {"matrix": payload.matrix, "updated_at": now_iso()}}, upsert=True
    )
    await audit(actor["name"], "permissions_updated", "permission_settings", "default", payload.matrix)
    return {"matrix": payload.matrix}


# =============================================================================
# DEMO SEED ENDPOINT
# =============================================================================
# Endpoint admin-only untuk reset & re-populate database dengan data demo.
# Diproteksi dengan:
#   1. Role admin (via require_permission)
#   2. Confirm token wajib di body (mencegah accidental call)
#   3. Optional env var SEED_DEMO_ENABLED — bila di-set ke "false", endpoint
#      akan menolak request (untuk safety di production setelah data real masuk)
# =============================================================================

class SeedDemoRequest(BaseModel):
    confirm: str  # Harus = "YES_CLEAR_AND_SEED_DEMO_DATA"


@router.post("/admin/seed-demo")
async def seed_demo(payload: SeedDemoRequest, request: Request) -> Dict[str, Any]:
    """
    DESTRUCTIVE: Hapus semua data operasional dan isi ulang dengan demo data.
    Hanya untuk admin. Wajib kirim confirm token agar tidak terjadi accidental call.
    """
    actor = await require_permission(request, "permission", "update")

    # Safety check 1 — feature flag
    enabled = os.environ.get("SEED_DEMO_ENABLED", "true").lower()
    if enabled in ("false", "0", "no"):
        raise HTTPException(
            status_code=403,
            detail="Seed demo endpoint dinonaktifkan via SEED_DEMO_ENABLED=false"
        )

    # Safety check 2 — explicit confirm token
    expected_token = "YES_CLEAR_AND_SEED_DEMO_DATA"
    if payload.confirm != expected_token:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Confirm token tidak sesuai. Wajib kirim body "
                f'{{"confirm": "{expected_token}"}} untuk konfirmasi reset+seed.'
            )
        )

    # Run seed pipeline
    try:
        summary = await run_demo_seed(db)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Seed gagal dijalankan: {type(exc).__name__}: {exc}"
        )

    # Audit log
    await audit(
        actor["name"],
        "demo_seed_executed",
        "database",
        "all_operational_collections",
        summary
    )

    return {
        "status": "ok",
        "executed_by": actor["name"],
        "summary": summary,
        "note": (
            "Database telah di-reset dan diisi ulang dengan demo data. "
            "Login dengan akun demo: admin / sales / manager / warehouse (password: demo12345)."
        ),
    }
