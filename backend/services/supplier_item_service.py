"""FASE E — SERVICE `supplier_items` (Barang Supplier / katalog versi supplier).

Masalah nyata: supplier menyebut barang dengan **kode & nama sendiri** (mis. `TX-COT-30S`
"Cotton Combed 30s Cone 1,89kg") sementara KN memakai SKU sendiri (`BNG-KTN-001`
"Benang Katun Cone (per Kg)"). Tanpa peta ini, tim purchasing menerjemahkan manual saat
membuat PO & saat menerima barang → salah barang, salah satuan, salah harga.

Fitur:
  * CRUD + pencarian **by SKU supplier** (`lookup`).
  * **Impor massal** CSV/XLSX (pratinjau → commit), **idempotent** upsert by
    (supplier_id, supplier_sku) — jalan 2× ⇒ `created=0`.
  * Konversi satuan supplier → base_unit produk (`conv_factor`) untuk qty PO.
  * `resolve_for_product` → dipakai PR→PO agar PO membawa nama/SKU supplier + grade.

Kunci logis: **(supplier_id, supplier_sku)** unik. `usage_count` naik saat dipakai PO
sehingga penghapusan yang merusak jejak audit ditolak (409 di router).
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional, Tuple

from core_utils import new_id, now_iso, parse_decimal, safe_doc
from db import db

try:  # opsional — impor XLSX
    import openpyxl
    XLSX_AVAILABLE = True
except ImportError:  # pragma: no cover
    XLSX_AVAILABLE = False

COLL = "supplier_items"
STATUSES = ("active", "inactive")

# Kolom impor yang dikenali (alias ramah pengguna → nama kanonik).
COLUMN_ALIASES: Dict[str, str] = {
    "supplier_sku": "supplier_sku", "kode_supplier": "supplier_sku",
    "sku_supplier": "supplier_sku", "supplier_code": "supplier_sku",
    "supplier_item_name": "supplier_item_name", "nama_supplier": "supplier_item_name",
    "nama_barang_supplier": "supplier_item_name", "supplier_name_item": "supplier_item_name",
    "sku": "sku", "sku_kn": "sku", "kode_kn": "sku",
    "product_id": "product_id",
    "supplier_uom": "supplier_uom", "satuan_supplier": "supplier_uom", "uom": "supplier_uom",
    "conv_factor": "conv_factor", "faktor": "conv_factor", "faktor_konversi": "conv_factor",
    "last_price": "last_price", "harga": "last_price", "harga_terakhir": "last_price",
    "currency": "currency", "mata_uang": "currency",
    "moq": "moq", "min_order": "moq",
    "lead_time_days": "lead_time_days", "lead_time": "lead_time_days",
    "expected_grade": "expected_grade", "grade": "expected_grade",
    "barcode": "barcode",
    "notes": "notes", "catatan": "notes",
}

CSV_TEMPLATE_HEADERS = ["supplier_sku", "supplier_item_name", "sku", "supplier_uom",
                        "conv_factor", "last_price", "currency", "moq",
                        "lead_time_days", "expected_grade", "barcode", "notes"]


class SupplierItemError(Exception):
    """Pelanggaran aturan barang supplier (dipetakan ke HTTP 400/409 di router)."""


# ═══════════════════════════════════════════════════════════════════════════
# 1. HELPER
# ═══════════════════════════════════════════════════════════════════════════
async def _supplier_snapshot(supplier_id: str) -> Dict[str, str]:
    sup = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0, "name": 1})
    if not sup:
        raise SupplierItemError(f"Supplier {supplier_id} tidak ditemukan.")
    return {"name": sup.get("name", "")}


async def _resolve_product(product_id: str = "", sku: str = "") -> Dict[str, Any]:
    prod = None
    if product_id:
        prod = await db.products.find_one({"id": product_id}, {"_id": 0})
        if not prod:
            raise SupplierItemError(f"Produk {product_id} tidak ditemukan.")
    elif sku:
        prod = await db.products.find_one({"sku": sku.strip()}, {"_id": 0})
        if not prod:
            raise SupplierItemError(f"SKU KN '{sku}' tidak ada di master produk.")
    else:
        raise SupplierItemError("Produk KN wajib: isi `product_id` atau `sku`.")
    return prod


def _norm_row(raw: Dict[str, Any]) -> Dict[str, str]:
    """Normalisasi header impor (case-insensitive + alias Indonesia)."""
    out: Dict[str, str] = {}
    for key, val in (raw or {}).items():
        canon = COLUMN_ALIASES.get(str(key or "").strip().lower().replace(" ", "_"))
        if canon and canon not in out:
            out[canon] = "" if val is None else str(val).strip()
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 2. CRUD
# ═══════════════════════════════════════════════════════════════════════════
async def create_item(payload: Dict[str, Any], *, entity_id: str,
                      actor: str = "") -> Dict[str, Any]:
    supplier_id = (payload.get("supplier_id") or "").strip()
    supplier_sku = (payload.get("supplier_sku") or "").strip()
    if not supplier_id:
        raise SupplierItemError("Supplier wajib dipilih.")
    if not supplier_sku:
        raise SupplierItemError("Kode barang supplier (supplier_sku) wajib diisi.")
    status = (payload.get("status") or "active").strip().lower()
    if status not in STATUSES:
        raise SupplierItemError(f"Status harus salah satu: {', '.join(STATUSES)}.")
    dup = await db[COLL].find_one({"supplier_id": supplier_id, "supplier_sku": supplier_sku},
                                  {"_id": 0, "id": 1})
    if dup:
        raise SupplierItemError(
            f"Kode supplier '{supplier_sku}' sudah terdaftar untuk supplier ini "
            "(kunci unik supplier + kode). Gunakan ubah/impor untuk memperbarui.")
    snap = await _supplier_snapshot(supplier_id)
    prod = await _resolve_product(payload.get("product_id") or "", payload.get("sku") or "")
    conv = parse_decimal(payload.get("conv_factor") if payload.get("conv_factor") not in (None, "") else 1, 6)
    if conv <= 0:
        raise SupplierItemError("Faktor konversi harus lebih besar dari 0.")
    doc: Dict[str, Any] = {
        "id": new_id("sit"),
        "entity_id": entity_id or "",
        "supplier_id": supplier_id, "supplier_name": snap["name"],
        "product_id": prod["id"], "sku": prod.get("sku", ""),
        "product_name": prod.get("name", ""),
        "base_unit": prod.get("base_unit", ""),
        "supplier_sku": supplier_sku,
        "supplier_item_name": (payload.get("supplier_item_name") or "").strip() or prod.get("name", ""),
        "supplier_uom": (payload.get("supplier_uom") or "").strip() or prod.get("base_unit", ""),
        "conv_factor": conv,
        "last_price": parse_decimal(payload.get("last_price"), 2),
        "currency": payload.get("currency") or "IDR",
        "moq": parse_decimal(payload.get("moq")),
        "lead_time_days": int(payload.get("lead_time_days") or 0),
        "expected_grade": (payload.get("expected_grade") or "").strip(),
        "barcode": (payload.get("barcode") or "").strip(),
        "notes": payload.get("notes") or "",
        "status": status,
        "usage_count": 0,
        "created_at": now_iso(), "created_by": actor,
        "updated_at": now_iso(), "updated_by": actor,
    }
    await db[COLL].insert_one(dict(doc))
    return safe_doc(doc)


async def get_item(sid: str) -> Optional[Dict[str, Any]]:
    return safe_doc(await db[COLL].find_one({"id": sid}, {"_id": 0}))


async def patch_item(sid: str, payload: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    cur = await db[COLL].find_one({"id": sid}, {"_id": 0})
    if not cur:
        raise SupplierItemError("Barang supplier tidak ditemukan.")
    upd: Dict[str, Any] = {}
    if payload.get("supplier_sku") not in (None, ""):
        new_sku = str(payload["supplier_sku"]).strip()
        if new_sku != cur["supplier_sku"]:
            dup = await db[COLL].find_one(
                {"supplier_id": cur["supplier_id"], "supplier_sku": new_sku, "id": {"$ne": sid}},
                {"_id": 0, "id": 1})
            if dup:
                raise SupplierItemError(f"Kode supplier '{new_sku}' sudah dipakai supplier ini.")
        upd["supplier_sku"] = new_sku
    if payload.get("product_id") not in (None, "") or payload.get("sku") not in (None, ""):
        prod = await _resolve_product(payload.get("product_id") or "", payload.get("sku") or "")
        upd.update({"product_id": prod["id"], "sku": prod.get("sku", ""),
                    "product_name": prod.get("name", ""), "base_unit": prod.get("base_unit", "")})
    if payload.get("conv_factor") not in (None, ""):
        conv = parse_decimal(payload["conv_factor"], 6)
        if conv <= 0:
            raise SupplierItemError("Faktor konversi harus lebih besar dari 0.")
        upd["conv_factor"] = conv
    if payload.get("status") not in (None, ""):
        st = str(payload["status"]).strip().lower()
        if st not in STATUSES:
            raise SupplierItemError(f"Status harus salah satu: {', '.join(STATUSES)}.")
        upd["status"] = st
    for key, cast in (("supplier_item_name", str), ("supplier_uom", str), ("currency", str),
                      ("expected_grade", str), ("barcode", str), ("notes", str)):
        if payload.get(key) is not None:
            upd[key] = cast(payload[key]).strip() if cast is str else payload[key]
    for key in ("last_price", "moq"):
        if payload.get(key) is not None:
            upd[key] = parse_decimal(payload[key], 2)
    if payload.get("lead_time_days") is not None:
        upd["lead_time_days"] = int(payload["lead_time_days"] or 0)
    if not upd:
        return safe_doc(cur)
    upd.update({"updated_at": now_iso(), "updated_by": actor})
    await db[COLL].update_one({"id": sid}, {"$set": upd})
    return safe_doc(await db[COLL].find_one({"id": sid}, {"_id": 0}))


async def delete_item(sid: str) -> Dict[str, Any]:
    cur = await db[COLL].find_one({"id": sid}, {"_id": 0})
    if not cur:
        raise SupplierItemError("Barang supplier tidak ditemukan.")
    if int(cur.get("usage_count") or 0) > 0:
        raise SupplierItemError(
            f"Barang supplier '{cur.get('supplier_sku')}' sudah dipakai "
            f"{cur['usage_count']}× pada PO — tidak bisa dihapus. Ubah status ke 'inactive'.")
    await db[COLL].delete_one({"id": sid})
    return {"deleted": True, "id": sid}


def _rx(term: str) -> Dict[str, Any]:
    import re as _re
    return {"$regex": _re.escape(term), "$options": "i"}


async def list_items(query: Dict[str, Any], *, q: str = "", limit: int = 200,
                     skip: int = 0, sort: str = "-created_at") -> List[Dict[str, Any]]:
    flt = dict(query or {})
    if q:
        flt["$or"] = [{"supplier_sku": _rx(q)}, {"supplier_item_name": _rx(q)},
                      {"sku": _rx(q)}, {"product_name": _rx(q)}, {"barcode": _rx(q)}]
    field = sort.lstrip("-") or "created_at"
    direction = -1 if sort.startswith("-") else 1
    rows = await db[COLL].find(flt, {"_id": 0}).sort(field, direction).skip(skip).limit(limit).to_list(limit)
    return [safe_doc(r) for r in rows]


async def count_items(query: Dict[str, Any]) -> int:
    return await db[COLL].count_documents(dict(query or {}))


async def stats(query: Dict[str, Any]) -> Dict[str, Any]:
    rows = await db[COLL].find(dict(query or {}), {"_id": 0}).to_list(20000)
    suppliers = {r.get("supplier_id") for r in rows if r.get("supplier_id")}
    return {
        "total": len(rows),
        "active": sum(1 for r in rows if r.get("status") == "active"),
        "inactive": sum(1 for r in rows if r.get("status") != "active"),
        "suppliers": len(suppliers),
        "mapped_products": len({r.get("product_id") for r in rows if r.get("product_id")}),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. PENCARIAN / RESOLVER
# ═══════════════════════════════════════════════════════════════════════════
async def lookup(*, supplier_sku: str, supplier_id: str = "",
                 entity_id: str = "") -> Optional[Dict[str, Any]]:
    """Cari barang KN dari **kode supplier** (kasus nyata: operator hanya pegang kode supplier)."""
    if not (supplier_sku or "").strip():
        raise SupplierItemError("Kode supplier (supplier_sku) wajib diisi untuk pencarian.")
    flt: Dict[str, Any] = {"supplier_sku": (supplier_sku or "").strip()}
    if supplier_id:
        flt["supplier_id"] = supplier_id
    if entity_id:
        flt["entity_id"] = {"$in": [entity_id, "", None]}
    row = await db[COLL].find_one(flt, {"_id": 0})
    if not row:  # fallback: case-insensitive
        flt["supplier_sku"] = _rx((supplier_sku or "").strip())
        row = await db[COLL].find_one(flt, {"_id": 0})
    return safe_doc(row)


async def resolve_for_product(*, supplier_id: str, product_id: str,
                              entity_id: str = "") -> Optional[Dict[str, Any]]:
    """Barang supplier aktif untuk (supplier × produk) — dipakai saat PR→PO."""
    if not (supplier_id and product_id):
        return None
    flt: Dict[str, Any] = {"supplier_id": supplier_id, "product_id": product_id,
                           "status": "active"}
    if entity_id:
        flt["entity_id"] = {"$in": [entity_id, "", None]}
    rows = await db[COLL].find(flt, {"_id": 0}).sort("updated_at", -1).to_list(20)
    return safe_doc(rows[0]) if rows else None


async def mark_used(sid: str, price: float = 0.0) -> None:
    if not sid:
        return
    upd: Dict[str, Any] = {"last_used_at": now_iso()}
    if price and price > 0:
        upd["last_price"] = round(float(price), 2)
    await db[COLL].update_one({"id": sid}, {"$inc": {"usage_count": 1}, "$set": upd})


# ═══════════════════════════════════════════════════════════════════════════
# 4. IMPOR MASSAL (E-01/E-02) — pratinjau & commit idempotent
# ═══════════════════════════════════════════════════════════════════════════
def csv_template() -> str:
    """Template CSV siap unduh (header + 1 baris contoh)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_TEMPLATE_HEADERS)
    writer.writerow(["TX-COT-30S", "Cotton Combed 30s Cone", "BNG-KTN-001", "cone",
                     "1.89", "68000", "IDR", "10", "7", "A", "", "harga per cone 1,89 kg"])
    return buf.getvalue()


def parse_file(content: bytes, filename: str = "") -> List[Dict[str, Any]]:
    """Parse CSV atau XLSX → list dict mentah (header apa adanya)."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        if not XLSX_AVAILABLE:
            raise SupplierItemError("Impor XLSX belum tersedia di server — pakai CSV.")
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001
            raise SupplierItemError("Berkas XLSX tidak valid atau rusak.") from exc
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(h or "").strip() for h in rows[0]]
        out: List[Dict[str, Any]] = []
        for row in rows[1:]:
            if any(c is not None and str(c).strip() != "" for c in row):
                out.append({headers[i]: row[i] for i in range(min(len(headers), len(row)))})
        return out
    return parse_csv_text(content.decode("utf-8-sig", errors="replace"))


def parse_csv_text(text: str) -> List[Dict[str, Any]]:
    body = (text or "").strip()
    if not body:
        return []
    # Deteksi pemisah (Excel Indonesia sering memakai ';').
    first = body.splitlines()[0]
    delim = ";" if first.count(";") > first.count(",") else ","
    return list(csv.DictReader(io.StringIO(body), delimiter=delim))


async def validate_rows(rows: List[Dict[str, Any]], *, supplier_id: str,
                        entity_id: str = "") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validasi tiap baris → (baris_valid, kesalahan). TIDAK menulis apa pun."""
    if not supplier_id:
        raise SupplierItemError("Supplier wajib dipilih sebelum impor.")
    await _supplier_snapshot(supplier_id)      # pastikan supplier ada
    existing = {r["supplier_sku"]: r for r in await db[COLL].find(
        {"supplier_id": supplier_id}, {"_id": 0}).to_list(20000)}
    seen: Dict[str, int] = {}
    ok: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for idx, raw in enumerate(rows, start=2):        # baris 1 = header
        row = _norm_row(raw)
        sup_sku = row.get("supplier_sku", "")
        if not sup_sku:
            errors.append({"row": idx, "supplier_sku": "", "error": "Kolom supplier_sku wajib diisi."})
            continue
        if sup_sku in seen:
            errors.append({"row": idx, "supplier_sku": sup_sku,
                           "error": f"Duplikat di dalam berkas (baris {seen[sup_sku]})."})
            continue
        seen[sup_sku] = idx
        try:
            prod = await _resolve_product(row.get("product_id", ""), row.get("sku", ""))
        except SupplierItemError as exc:
            errors.append({"row": idx, "supplier_sku": sup_sku, "error": str(exc)})
            continue
        conv_raw = row.get("conv_factor", "")
        conv = parse_decimal(conv_raw, 6) if conv_raw else 1.0
        if conv <= 0:
            errors.append({"row": idx, "supplier_sku": sup_sku,
                           "error": f"Faktor konversi tidak valid ('{conv_raw}') — harus > 0."})
            continue
        price = parse_decimal(row.get("last_price", ""), 2)
        if price < 0:
            errors.append({"row": idx, "supplier_sku": sup_sku,
                           "error": "Harga tidak boleh negatif."})
            continue
        lead_raw = (row.get("lead_time_days") or "").strip()
        try:
            lead = int(float(lead_raw)) if lead_raw else 0
        except ValueError:
            errors.append({"row": idx, "supplier_sku": sup_sku,
                           "error": f"Lead time tidak valid ('{lead_raw}')."})
            continue
        prev = existing.get(sup_sku)
        ok.append({
            "row": idx, "action": "update" if prev else "create",
            "existing_id": (prev or {}).get("id", ""),
            "supplier_id": supplier_id, "entity_id": entity_id or "",
            "supplier_sku": sup_sku,
            "supplier_item_name": row.get("supplier_item_name", "") or prod.get("name", ""),
            "product_id": prod["id"], "sku": prod.get("sku", ""),
            "product_name": prod.get("name", ""), "base_unit": prod.get("base_unit", ""),
            "supplier_uom": row.get("supplier_uom", "") or prod.get("base_unit", ""),
            "conv_factor": conv, "last_price": price,
            "currency": row.get("currency", "") or "IDR",
            "moq": parse_decimal(row.get("moq", "")),
            "lead_time_days": lead,
            "expected_grade": row.get("expected_grade", ""),
            "barcode": row.get("barcode", ""), "notes": row.get("notes", ""),
        })
    return ok, errors


async def import_rows(rows: List[Dict[str, Any]], *, supplier_id: str, entity_id: str = "",
                      actor: str = "", dry_run: bool = True) -> Dict[str, Any]:
    """Pratinjau (`dry_run=True`) atau commit impor. Commit **idempotent**:
    upsert by (supplier_id, supplier_sku) ⇒ jalan ke-2 `created=0`, `updated=N`."""
    valid, errors = await validate_rows(rows, supplier_id=supplier_id, entity_id=entity_id)
    result: Dict[str, Any] = {
        "total": len(rows), "valid": len(valid), "invalid": len(errors),
        "created": 0, "updated": 0, "dry_run": bool(dry_run),
        "errors": errors[:200], "preview": valid[:50],
    }
    if dry_run:
        result["will_create"] = sum(1 for r in valid if r["action"] == "create")
        result["will_update"] = sum(1 for r in valid if r["action"] == "update")
        return result
    snap = await _supplier_snapshot(supplier_id)
    for r in valid:
        body = {k: v for k, v in r.items() if k not in ("row", "action", "existing_id")}
        body["supplier_name"] = snap["name"]
        body["updated_at"] = now_iso()
        body["updated_by"] = actor
        if r["action"] == "update":
            await db[COLL].update_one({"id": r["existing_id"]}, {"$set": body})
            result["updated"] += 1
        else:
            body.update({"id": new_id("sit"), "status": "active", "usage_count": 0,
                         "created_at": now_iso(), "created_by": actor})
            await db[COLL].insert_one(dict(body))
            result["created"] += 1
    return result
