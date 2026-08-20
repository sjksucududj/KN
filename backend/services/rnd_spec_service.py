"""FASE F · PS-12 — Layanan **SPESIFIKASI PRODUK versi R&D** (`md_specs`).

Alur yang dijamin di sini:
    draft → submit → (review) → approve → PRODUK lahir (lifecycle `disetujui`)
                                        → release → lifecycle `produksi` (boleh dijual)

Kenapa produk baru lahir `disetujui` dan BUKAN langsung `produksi`: KN_18 PS-12
menyatakan produk = **hasil approve spesifikasi**, sedangkan izin dijual/dibeli
adalah keputusan terpisah (rilis). Dengan begitu "barang belum jadi" tidak pernah
bocor ke SO/PR/PO — dijaga `services/rnd_gate.py`.

Tidak ada edit senyap: setiap transisi menulis `timeline[]` + audit log (router).
Semua relasi dokumen memakai `doc_refs_service` (FASE G-4), bukan field ad-hoc.
"""
from typing import Any, Dict, List, Optional

import domain_registry as dr
from core_utils import new_id, next_doc_number, now_iso, parse_decimal, safe_doc, timeline_entry
from db import db
from services import doc_refs_service as refs
from services import rnd_gate
from services import line_scope as _lines      # FASE L — satu pintu normalisasi lini

COLL = "md_specs"
PREFIX = "spec"

SPEC_STATUSES = ("draft", "review", "approved", "rejected")
OPEN_STATUSES = ("draft", "review")


class RndError(ValueError):
    """Kesalahan alur R&D dengan pesan siap tampil (Bahasa Indonesia)."""


# ─── Helper ───────────────────────────────────────────────────────
async def _color_snapshot(color: Dict[str, Any]) -> Dict[str, str]:
    """PS-13 — warna WAJIB dari pustaka (`color_library`), bukan teks bebas."""
    cid = (color or {}).get("color_id") or ""
    code = ((color or {}).get("code") or "").strip().upper()
    if not cid and not code:
        return {"color_id": "", "code": "", "name": "", "hex": ""}
    q = {"id": cid} if cid else {"code": code}
    row = await db.color_library.find_one(q, {"_id": 0})
    if not row:
        raise RndError(
            "Warna target tidak ada di Pustaka Warna. Pilih dari pustaka "
            "(Produk & Harga → Pustaka Warna) — warna tidak boleh diketik bebas.")
    return {"color_id": row["id"], "code": row.get("code", ""),
            "name": row.get("name", ""), "hex": row.get("hex", "")}


async def _design_snapshot(design_id: str, version: int = 0) -> Dict[str, Any]:
    if not design_id:
        return {"design_id": "", "design_code": "", "design_title": "", "design_version": 0}
    row = await db.design_gallery.find_one({"id": design_id}, {"_id": 0})
    if not row:
        raise RndError("Kode desain tidak ditemukan di Master Desain.")
    if (row.get("status") or "") == "retired":
        raise RndError(f"Desain '{row.get('code') or row.get('title')}' sudah di-retire — "
                       "tidak boleh dipakai permintaan baru.")
    return {"design_id": row["id"], "design_code": row.get("code", ""),
            "design_title": row.get("title", ""),
            "design_version": int(version or row.get("version") or 1)}


def _clean_target(target: Dict[str, Any]) -> Dict[str, Any]:
    t = dict(target or {})
    out: Dict[str, Any] = {
        "stage": (t.get("stage") or "finished").strip().lower(),
        "fabric_type": (t.get("fabric_type") or "").strip().lower(),
        "yarn_count": (t.get("yarn_count") or "").strip(),
        "yarn_count_system": (t.get("yarn_count_system") or "").strip(),
        "warp_count": (t.get("warp_count") or "").strip(),
        "weft_count": (t.get("weft_count") or "").strip(),
        "grade": (t.get("grade") or "").strip(),
    }
    for num in ("gramasi", "lebar", "epi", "ppi", "reed_width"):
        val = t.get(num)
        out[num] = None if val in (None, "") else parse_decimal(val)
    return out


def _product_draft(spec: Dict[str, Any], sku: str, name: str, price: float) -> Dict[str, Any]:
    """Bentuk dokumen produk dari spesifikasi (dipakai saat ACC)."""
    t = spec.get("target") or {}
    color = spec.get("color_target") or {}
    doc: Dict[str, Any] = {
        "id": new_id("prod"),
        "sku": sku,
        "name": name,
        "category": spec.get("category") or "",
        "base_unit": spec.get("base_unit") or "meter",
        "price": round(float(price or 0), 2),
        "harga_pokok": 0.0,
        "status": "active",
        "stage": t.get("stage") or "finished",
        "fabric_type": t.get("fabric_type") or "",
        "gramasi": t.get("gramasi"),
        "lebar": t.get("lebar"),
        "yarn_count": t.get("yarn_count") or "",
        "yarn_count_system": t.get("yarn_count_system") or "",
        "grade": t.get("grade") or "",
        "construction": {k: t.get(k) for k in ("epi", "ppi", "warp_count", "weft_count", "reed_width")},
        "color_code": color.get("code", ""), "color_name": color.get("name", ""),
        "color_hex": color.get("hex", ""), "color": color.get("name", ""),
        # FASE F — jejak asal produk (dua arah dengan md_specs).
        "lifecycle": "disetujui",
        "spec_id": spec["id"],
        "design_id": spec.get("design_id", ""),
        "design_version": int(spec.get("design_version") or 0),
        "batch_lot_rolls": [],
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    return doc


# ─── CRUD ──────────────────────────────────────────────────────
async def create_spec(payload: Dict[str, Any], *, entity_id: str, actor: str = "") -> Dict[str, Any]:
    title = (payload.get("title") or "").strip()
    if not title:
        raise RndError("Judul spesifikasi wajib diisi.")
    hint = (payload.get("sample_type_hint") or "labdip").strip().lower()
    if not dr.is_valid("sample_type", hint):
        raise RndError(f"Jenis sample '{hint}' tidak dikenal. "
                       f"Pilihan: {', '.join(dr.values_of('sample_type'))}.")
    target = _clean_target(payload.get("target") or {})
    if not target["fabric_type"]:
        raise RndError("Jenis kain (woven/knit) wajib diisi — dipakai membentuk produk saat ACC.")
    if not dr.is_valid("fabric_type", target["fabric_type"]):
        raise RndError(f"Jenis kain '{target['fabric_type']}' tidak dikenal.")
    if not dr.is_valid("stage", target["stage"]):
        raise RndError(f"Tahap bahan '{target['stage']}' tidak dikenal.")
    color = await _color_snapshot(payload.get("color_target") or {})
    design = await _design_snapshot(payload.get("design_id") or "",
                                   int(payload.get("design_version") or 0))
    doc: Dict[str, Any] = {
        "id": new_id(PREFIX),
        "number": await next_doc_number(COLL, "number", "SPEC-", entity_id=entity_id),
        "entity_id": entity_id or "",
        "title": title,
        "status": "draft",
        "lifecycle": "konsep",
        "category": (payload.get("category") or "").strip(),
        "base_unit": (payload.get("base_unit") or "meter").strip(),
        "sku_hint": (payload.get("sku_hint") or "").strip().upper(),
        "sample_type_hint": hint,
        # FASE L — lini kerja MD spesifikasi. Sengaja dari payload (pilihan MD), bukan
        # ditebak dari `fabric_type`: kain woven bisa dikerjakan lini woven MAUPUN
        # printing, jadi menebaknya akan menaruh pekerjaan di papan yang salah.
        "line_code": _lines.norm(payload.get("line_code")),
        "target": target,
        "color_target": color,
        **design,
        "customer_id": (payload.get("customer_id") or "").strip(),
        "so_id": (payload.get("so_id") or "").strip(),
        "target_price": parse_decimal(payload.get("target_price"), 2),
        "notes": payload.get("notes") or "",
        "product_id": "",
        "sample_ids": [],
        "attachments": [],
        "refs": [],
        "timeline": [timeline_entry("created", "Spesifikasi dibuat (draft)", actor)],
        "created_by": actor, "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db[COLL].insert_one(dict(doc))
    if doc["so_id"]:
        await refs.safe_link(("md_spec", doc["id"]), ("sales_order", doc["so_id"]), "parent",
                             note="permintaan pelanggan")
    return safe_doc(doc)


async def get_spec(spec_id: str) -> Optional[Dict[str, Any]]:
    return safe_doc(await db[COLL].find_one({"id": spec_id}, {"_id": 0}))


async def list_specs(query: Dict[str, Any], *, q: str = "", status: str = "",
                     lifecycle: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    flt = dict(query or {})
    if status:
        flt["status"] = status
    if lifecycle:
        flt["lifecycle"] = lifecycle
    if q:
        rx = {"$regex": q.strip(), "$options": "i"}
        flt["$or"] = [{"number": rx}, {"title": rx}, {"sku_hint": rx},
                      {"color_target.name": rx}, {"color_target.code": rx}]
    rows = await db[COLL].find(flt, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return [safe_doc(r) for r in rows]


async def patch_spec(spec_id: str, payload: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    cur = await db[COLL].find_one({"id": spec_id}, {"_id": 0})
    if not cur:
        raise RndError("Spesifikasi tidak ditemukan.")
    if cur.get("status") not in OPEN_STATUSES:
        raise RndError(f"Spesifikasi berstatus '{cur.get('status')}' tidak bisa diubah. "
                       "Buat spesifikasi baru bila targetnya berbeda (jejak tetap utuh).")
    data: Dict[str, Any] = {}
    for key in ("title", "category", "base_unit", "sku_hint", "customer_id", "so_id", "notes"):
        if payload.get(key) is not None:
            data[key] = payload[key]
    if payload.get("sample_type_hint"):
        hint = str(payload["sample_type_hint"]).strip().lower()
        if not dr.is_valid("sample_type", hint):
            raise RndError(f"Jenis sample '{hint}' tidak dikenal.")
        data["sample_type_hint"] = hint
    if payload.get("target") is not None:
        merged = {**(cur.get("target") or {}), **(payload["target"] or {})}
        data["target"] = _clean_target(merged)
    if payload.get("color_target") is not None:
        data["color_target"] = await _color_snapshot(payload["color_target"])
    if payload.get("design_id") is not None:
        data.update(await _design_snapshot(payload["design_id"],
                                          int(payload.get("design_version") or 0)))
    if payload.get("target_price") is not None:
        data["target_price"] = parse_decimal(payload["target_price"], 2)
    data["updated_at"] = now_iso()
    await db[COLL].update_one({"id": spec_id}, {
        "$set": data,
        "$push": {"timeline": timeline_entry("updated", "Spesifikasi diperbarui", actor)}})
    return await get_spec(spec_id)


# ─── Transisi ──────────────────────────────────────────────────
async def submit_spec(spec_id: str, actor: str = "") -> Dict[str, Any]:
    cur = await db[COLL].find_one({"id": spec_id}, {"_id": 0})
    if not cur:
        raise RndError("Spesifikasi tidak ditemukan.")
    if cur.get("status") != "draft":
        raise RndError(f"Hanya spesifikasi draft yang bisa diajukan (sekarang '{cur.get('status')}').")
    await db[COLL].update_one({"id": spec_id}, {
        "$set": {"status": "review", "submitted_by": actor, "submitted_at": now_iso(),
                 "updated_at": now_iso()},
        "$push": {"timeline": timeline_entry("submitted", "Diajukan untuk persetujuan", actor)}})
    return await get_spec(spec_id)


async def _assert_role(actor: Dict[str, Any], policy_key: str, entity_id: str, what: str) -> None:
    """Kebijakan peran (registry G-0) — wewenang tidak bisa dilangkahi lewat endpoint."""
    pol = await rnd_gate.policy(entity_id)
    allowed = pol.get(policy_key) or []
    if isinstance(allowed, str):
        allowed = [x.strip() for x in allowed.split(",") if x.strip()]
    role = (actor or {}).get("role", "")
    if allowed and role not in allowed:
        raise RndError(f"Peran '{role}' tidak berwenang {what}. "
                       f"Kebijakan berlaku: {', '.join(allowed)} "
                       "(ubah di Pusat Pengaturan → R&D & Desain).")


async def approve_spec(spec_id: str, payload: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    """ACC spesifikasi → **produk lahir** berstatus `disetujui` (belum boleh dijual)."""
    cur = await db[COLL].find_one({"id": spec_id}, {"_id": 0})
    if not cur:
        raise RndError("Spesifikasi tidak ditemukan.")
    if cur.get("status") not in ("review", "draft"):
        raise RndError(f"Spesifikasi berstatus '{cur.get('status')}' tidak bisa disetujui lagi.")
    await _assert_role(actor, "spec_approval_roles", cur.get("entity_id", ""),
                       "menyetujui spesifikasi")
    actor_name = (actor or {}).get("name", "")
    sku = ((payload.get("sku") or cur.get("sku_hint") or "").strip().upper()
           or f"RND-{(cur.get('number') or '').split('/')[-1]}")
    name = (payload.get("name") or cur.get("title") or "").strip()
    if await db.products.find_one({"sku": sku}, {"_id": 0, "id": 1}):
        raise RndError(f"SKU '{sku}' sudah dipakai produk lain. Isi kode SKU yang berbeda.")
    prod = _product_draft(cur, sku, name, payload.get("price") or cur.get("target_price") or 0)
    check = dr.validate_product(prod)
    if check["errors"]:
        raise RndError("Spesifikasi belum lengkap untuk menjadi produk: " + " ".join(check["errors"]))
    prod["needs_review"] = check["needs_review"]
    prod["needs_review_reasons"] = check["needs_review_reasons"]
    await db.products.insert_one(dict(prod))
    await db[COLL].update_one({"id": spec_id}, {
        "$set": {"status": "approved", "lifecycle": "disetujui", "product_id": prod["id"],
                 "product_sku": sku, "approved_by": actor_name, "approved_at": now_iso(),
                 "updated_at": now_iso()},
        "$push": {"timeline": timeline_entry(
            "approved", f"Disetujui → produk {sku} lahir (belum boleh dijual)", actor_name,
            payload.get("note") or "")}})
    return {"spec": await get_spec(spec_id), "product": safe_doc(prod)}


async def reject_spec(spec_id: str, reason: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    cur = await db[COLL].find_one({"id": spec_id}, {"_id": 0})
    if not cur:
        raise RndError("Spesifikasi tidak ditemukan.")
    if cur.get("status") not in OPEN_STATUSES:
        raise RndError("Hanya spesifikasi yang masih terbuka bisa ditolak.")
    await _assert_role(actor, "spec_approval_roles", cur.get("entity_id", ""),
                       "menolak spesifikasi")
    name = (actor or {}).get("name", "")
    await db[COLL].update_one({"id": spec_id}, {
        "$set": {"status": "rejected", "reject_reason": reason, "rejected_by": name,
                 "rejected_at": now_iso(), "updated_at": now_iso()},
        "$push": {"timeline": timeline_entry("rejected", "Ditolak", name, reason)}})
    return await get_spec(spec_id)


async def release_product(spec_id: str, actor: Dict[str, Any], note: str = "") -> Dict[str, Any]:
    """Rilis ke produksi → produk boleh dipesan/dijual (lifecycle `produksi`)."""
    cur = await db[COLL].find_one({"id": spec_id}, {"_id": 0})
    if not cur:
        raise RndError("Spesifikasi tidak ditemukan.")
    if cur.get("status") != "approved" or not cur.get("product_id"):
        raise RndError("Hanya spesifikasi yang sudah disetujui (dan sudah punya produk) "
                       "bisa dirilis ke produksi.")
    await _assert_role(actor, "spec_approval_roles", cur.get("entity_id", ""),
                       "merilis produk ke produksi")
    name = (actor or {}).get("name", "")
    await db.products.update_one({"id": cur["product_id"]},
                                 {"$set": {"lifecycle": "produksi", "updated_at": now_iso()}})
    await db[COLL].update_one({"id": spec_id}, {
        "$set": {"lifecycle": "produksi", "released_by": name, "released_at": now_iso(),
                 "updated_at": now_iso()},
        "$push": {"timeline": timeline_entry("released", "Dirilis ke produksi (boleh dijual)",
                                             name, note)}})
    return {"spec": await get_spec(spec_id),
            "product": safe_doc(await db.products.find_one({"id": cur["product_id"]}, {"_id": 0}))}


async def set_lifecycle_stage(spec_id: str, lifecycle: str) -> None:
    """Dipakai layanan sample: spesifikasi mengikuti tahap sample (labdip/proofing)."""
    if lifecycle not in dr.values_of("lifecycle"):
        return
    cur = await db[COLL].find_one({"id": spec_id}, {"_id": 0, "status": 1, "lifecycle": 1})
    if not cur or cur.get("status") not in OPEN_STATUSES:
        return
    await db[COLL].update_one({"id": spec_id},
                             {"$set": {"lifecycle": lifecycle, "updated_at": now_iso()}})


async def stats(query: Dict[str, Any]) -> Dict[str, Any]:
    rows = await db[COLL].find(dict(query or {}), {"_id": 0, "status": 1}).to_list(5000)
    out = {s: 0 for s in SPEC_STATUSES}
    for r in rows:
        out[r.get("status", "draft")] = out.get(r.get("status", "draft"), 0) + 1
    out["total"] = len(rows)
    return out
