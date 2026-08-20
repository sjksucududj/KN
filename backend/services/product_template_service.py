"""F1b — Product Templates & Variants (pendekatan ADDITIVE/non-destruktif).

Katalog `products` TETAP unit jual ber-SKU (POS/stok/SO/harga tidak berubah).
`product_templates` = lapisan induk (definisi + atribut bersama + axis varian).
`products.template_id` menautkan varian ke template. SHARED lintas-entitas (D1).

Axis varian fleksibel:
  axis = {"key": "color", "label": "Warna",
          "options": [{"code": "MRH", "label": "Merah", "value": ""}, ...]}
Generate = cartesian product semua axis → buat produk ber-SKU
  SKU  = f"{sku_prefix}-{kode1}-{kode2}..." (uppercase, lewati SKU yang sudah ada)
  Nama = f"{template.name} {label1} {label2}..."
"""
import itertools
import re
from typing import Any, Dict, List, Optional

import domain_registry as dr
from db import db
from core_utils import new_id, now_iso, safe_doc

PREFIX = "ptpl"
DEFAULT_IMAGE = ("https://images.unsplash.com/photo-1774679817333-decf0d988dd5"
                 "?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85")


def _slug(text: str, n: int = 8) -> str:
    s = re.sub(r"[^A-Za-z0-9]", "", str(text or "")).upper()
    return s[:n]


def _prefix_from_name(name: str) -> str:
    words = [w for w in re.split(r"\s+", str(name or "").strip()) if w]
    initials = "".join(w[0] for w in words)[:6].upper()
    return initials or _slug(name, 6) or "PRD"


# ─── CRUD Template ───────────────────────────────────────────────────────────

async def create_template(data: Dict[str, Any], actor_name: str) -> Dict[str, Any]:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Nama template wajib diisi")
    doc = {
        "id": new_id(PREFIX),
        "name": name,
        "category": (data.get("category") or "Kain").strip(),
        "fabric_type": (data.get("fabric_type") or "").strip(),
        "motif": (data.get("motif") or "Polos").strip(),
        "stage": (data.get("stage") or "finished").strip(),
        # Fase A · D-22 — atribut benang (dipakai bila stage=yarn)
        "yarn_count": (data.get("yarn_count") or "").strip(),
        "yarn_count_system": (data.get("yarn_count_system") or "").strip(),
        "description": (data.get("description") or "").strip(),
        "image": (data.get("image") or "").strip() or DEFAULT_IMAGE,
        "base_unit": (data.get("base_unit") or "meter").strip(),
        "base_price": round(float(data.get("base_price") or 0), 2),
        "harga_pokok": round(float(data.get("harga_pokok") or 0), 2),
        "gramasi": float(data.get("gramasi") or 0),
        "lebar": float(data.get("lebar") or 0),
        "supplier": (data.get("supplier") or "Internal").strip(),
        "sku_prefix": (data.get("sku_prefix") or "").strip().upper() or _prefix_from_name(name),
        "axes": _normalize_axes(data.get("axes") or []),
        "status": "active",
        "created_by": actor_name, "created_at": now_iso(), "updated_at": now_iso(),
    }
    # Fase A (PS-01/02/03) — template = induk produk: domain WAJIB sah sejak awal.
    dr.apply_normalization(doc)
    check = dr.validate_product(doc)
    if check["errors"]:
        raise ValueError(" ".join(check["errors"]))
    doc["needs_review"] = check["needs_review"]
    doc["needs_review_reasons"] = check["needs_review_reasons"]
    await db.product_templates.insert_one(doc)
    out = safe_doc(doc)
    out["domain_warnings"] = check["warnings"]
    return out


def _normalize_axes(axes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for ax in axes or []:
        key = (ax.get("key") or "").strip().lower() or _slug(ax.get("label", ""), 6).lower()
        label = (ax.get("label") or key).strip()
        options = []
        for opt in ax.get("options") or []:
            olabel = (opt.get("label") or opt.get("code") or "").strip()
            if not olabel:
                continue
            options.append({
                "code": (opt.get("code") or _slug(olabel, 6)).strip().upper(),
                "label": olabel,
                "value": opt.get("value", ""),
            })
        if label and options:
            out.append({"key": key, "label": label, "options": options})
    return out


async def update_template(template_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tpl = await db.product_templates.find_one({"id": template_id}, {"_id": 0})
    if not tpl:
        return None
    allowed = ["name", "category", "fabric_type", "motif", "description", "image",
               "base_unit", "base_price", "harga_pokok", "gramasi", "lebar",
               "supplier", "sku_prefix", "status", "stage",
               "yarn_count", "yarn_count_system"]   # Fase A · D-22
    upd: Dict[str, Any] = {}
    for k in allowed:
        if k in patch and patch[k] is not None:
            upd[k] = patch[k]
    if "axes" in patch and patch["axes"] is not None:
        upd["axes"] = _normalize_axes(patch["axes"])
    if "sku_prefix" in upd:
        upd["sku_prefix"] = (str(upd["sku_prefix"]).strip().upper() or tpl.get("sku_prefix"))
    # Fase A — normalisasi + validasi domain terhadap dokumen gabungan (patch parsial).
    dr.apply_normalization(upd)
    check = dr.validate_product(upd, tpl)
    if check["errors"]:
        raise ValueError(" ".join(check["errors"]))
    upd["needs_review"] = check["needs_review"]
    upd["needs_review_reasons"] = check["needs_review_reasons"]
    upd["updated_at"] = now_iso()
    await db.product_templates.update_one({"id": template_id}, {"$set": upd})
    return safe_doc(await db.product_templates.find_one({"id": template_id}, {"_id": 0}))


async def delete_template(template_id: str) -> Dict[str, Any]:
    tpl = await db.product_templates.find_one({"id": template_id}, {"_id": 0})
    if not tpl:
        raise ValueError("Template tidak ditemukan")
    # Non-destruktif: lepas tautan varian (produk tetap utuh), lalu hapus template.
    res = await db.products.update_many(
        {"template_id": template_id}, {"$set": {"template_id": "", "updated_at": now_iso()}})
    await db.product_templates.delete_one({"id": template_id})
    return {"deleted": True, "id": template_id, "detached_variants": res.modified_count}


# ─── List / detail (dengan jumlah varian) ────────────────────────────────────

async def _variant_counts() -> Dict[str, int]:
    rows = await db.products.aggregate([
        {"$match": {"template_id": {"$exists": True, "$nin": ["", None]}}},
        {"$group": {"_id": "$template_id", "count": {"$sum": 1}}},
    ]).to_list(2000)
    return {r["_id"]: r["count"] for r in rows}


async def list_templates(search: str = "") -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    tpls = await db.product_templates.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    if search:
        s = search.lower()
        tpls = [t for t in tpls if s in f"{t.get('name','')}{t.get('category','')}{t.get('motif','')}".lower()]
    counts = await _variant_counts()
    for t in tpls:
        t["variant_count"] = counts.get(t["id"], 0)
    return [safe_doc(t) for t in tpls]


async def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    tpl = await db.product_templates.find_one({"id": template_id}, {"_id": 0})
    if not tpl:
        return None
    variants = await db.products.find(
        {"template_id": template_id}, {"_id": 0}).sort("sku", 1).to_list(2000)
    tpl = safe_doc(tpl)
    tpl["variants"] = [safe_doc(v) for v in variants]
    tpl["variant_count"] = len(variants)
    return tpl


# ─── Generate varian massal (cartesian) ──────────────────────────────────────

async def generate_variants(template_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    tpl = await db.product_templates.find_one({"id": template_id}, {"_id": 0})
    if not tpl:
        raise ValueError("Template tidak ditemukan")
    axes = _normalize_axes(data.get("axes") or tpl.get("axes") or [])
    axis_lists = [(ax, ax["options"]) for ax in axes if ax.get("options")]
    if not axis_lists:
        raise ValueError("Minimal satu axis dengan opsi diperlukan untuk generate varian")
    base_price = float(data.get("base_price") if data.get("base_price") is not None
                       else tpl.get("base_price", 0) or 0)
    prefix = (data.get("sku_prefix") or tpl.get("sku_prefix") or _prefix_from_name(tpl["name"])).strip().upper()
    existing = {p["sku"] for p in await db.products.find({}, {"_id": 0, "sku": 1}).to_list(10000)}
    combos = list(itertools.product(*[opts for _, opts in axis_lists]))
    created: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for combo in combos:
        codes, labels, attrs = [], [], {}
        color = tpl.get("color", "Natural")
        grade = tpl.get("grade", "A")
        color_code = ""
        color_hex = ""
        lebar = float(tpl.get("lebar", 0) or 0)
        for (ax, _), opt in zip(axis_lists, combo):
            codes.append(opt["code"])
            labels.append(opt["label"])
            key = ax["key"]
            attrs[key] = opt["label"]
            if key == "color":
                color = opt["label"]
                color_code = str(opt.get("value") or "").strip()   # M0 — axis color option.value = color_library.code
                color_hex = str(opt.get("hex") or "").strip()
            elif key == "grade":
                grade = opt["label"]
            elif key == "lebar":
                try:
                    lebar = float(opt.get("value") or opt["label"])
                except (TypeError, ValueError):
                    pass
        sku = (f"{prefix}-" + "-".join(codes)).upper()
        if sku in existing:
            skipped.append(sku)
            continue
        prod = {
            "id": new_id("prod"), "sku": sku,
            "name": f"{tpl['name']} " + " ".join(labels),
            "category": tpl.get("category", "Kain"),
            "variant": " ".join(labels) or "Regular",
            "color": color, "motif": tpl.get("motif", "Polos"), "grade": grade,
            "color_code": color_code, "color_name": color if color_code else "", "color_hex": color_hex,
            "stage": tpl.get("stage", "finished"),
            # Fase A · PS-02/D-02 — varian WAJIB mewarisi jenis kain & atribut benang induk.
            "fabric_type": tpl.get("fabric_type", ""),
            "yarn_count": tpl.get("yarn_count", ""),
            "yarn_count_system": tpl.get("yarn_count_system", ""),
            "supplier": tpl.get("supplier", "Internal"),
            "base_unit": tpl.get("base_unit", "meter"),
            "price": round(base_price, 2), "harga_pokok": float(tpl.get("harga_pokok", 0) or 0),
            "gramasi": float(tpl.get("gramasi", 0) or 0), "lebar": lebar, "kg_per_meter": 0,
            "reorder_point": 0, "reorder_qty": 0,
            "image": tpl.get("image") or DEFAULT_IMAGE,
            "status": "active", "uom_conversions": [],
            "template_id": template_id, "variant_attrs": attrs,
            "batch_lot_rolls": [], "created_at": now_iso(), "updated_at": now_iso(),
        }
        # Fase A — varian yang dihasilkan WAJIB lulus validasi domain (tanpa ini,
        # generator bisa menyisipkan produk cacat yang menembus validasi router).
        dr.apply_normalization(prod)
        vcheck = dr.validate_product(prod)
        if vcheck["errors"]:
            raise ValueError(f"Varian {sku} tidak sah: " + " ".join(vcheck["errors"]))
        prod["needs_review"] = vcheck["needs_review"]
        prod["needs_review_reasons"] = vcheck["needs_review_reasons"]
        await db.products.insert_one(prod)
        existing.add(sku)
        created.append(safe_doc(prod))
    return {"created": len(created), "skipped": len(skipped),
            "skipped_skus": skipped, "variants": created,
            "total_combinations": len(combos)}


# ─── Assign / detach produk existing ─────────────────────────────────────────

async def assign_products(template_id: str, product_ids: List[str]) -> Dict[str, Any]:
    tpl = await db.product_templates.find_one({"id": template_id}, {"_id": 0})
    if not tpl:
        raise ValueError("Template tidak ditemukan")
    res = await db.products.update_many(
        {"id": {"$in": product_ids or []}},
        {"$set": {"template_id": template_id, "updated_at": now_iso()}})
    return {"assigned": res.modified_count, "template_id": template_id}


async def detach_products(product_ids: List[str]) -> Dict[str, Any]:
    res = await db.products.update_many(
        {"id": {"$in": product_ids or []}},
        {"$set": {"template_id": "", "updated_at": now_iso()}})
    return {"detached": res.modified_count}
