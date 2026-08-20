"""M0 — Color Library service (Pantone-style master warna).

Koleksi `color_library` (prefix `col_`) = master warna internal bergaya Pantone
(code/name/hex/system/family). SHARED lintas-entitas (seperti products).
Dipakai lintas menu (Master Produk, Template Varian, POS, Special Order, Makloon).

Backward-compat: produk lama pakai `color` teks bebas; color_code opsional.
"""
import re
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso, safe_doc

PREFIX = "col"
VALID_SYSTEMS = {"TPX", "TCX", "C", "U", "KN"}

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def normalize_hex(value: str) -> Optional[str]:
    """Normalisasi '#rrggbb' → 'RRGGBB' (uppercase, tanpa #). None bila invalid."""
    if not value:
        return None
    m = _HEX_RE.match(str(value).strip())
    if not m:
        return None
    return m.group(1).upper()


def hex_to_rgb(value: str) -> Optional[tuple]:
    h = normalize_hex(value)
    if not h:
        return None
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def color_distance(rgb1: tuple, rgb2: tuple) -> float:
    """Jarak warna 'redmean' (aproksimasi perseptual sederhana, tanpa dependency).

    Lebih baik dari Euclidean RGB polos untuk mendekati persepsi mata manusia.
    """
    r1, g1, b1 = rgb1
    r2, g2, b2 = rgb2
    rmean = (r1 + r2) / 2.0
    dr, dg, db_ = r1 - r2, g1 - g2, b1 - b2
    return (
        (2 + rmean / 256) * dr * dr
        + 4 * dg * dg
        + (2 + (255 - rmean) / 256) * db_ * db_
    ) ** 0.5


# ─── CRUD ────────────────────────────────────────────────────────────────────

async def list_colors(q: str = "", family: str = "", system: str = "",
                      status: str = "active") -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {}
    if status and status != "all":
        query["status"] = status
    if family:
        query["family"] = family
    if system:
        query["system"] = system
    rows = await db.color_library.find(query, {"_id": 0}).sort("code", 1).to_list(2000)
    if q:
        s = q.lower()
        rows = [r for r in rows
                if s in f"{r.get('code','')}{r.get('name','')}{r.get('family','')}".lower()]
    return [safe_doc(r) for r in rows]


async def create_color(data: Dict[str, Any], actor_name: str = "") -> Dict[str, Any]:
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    if not code:
        raise ValueError("Kode warna wajib diisi")
    if not name:
        raise ValueError("Nama warna wajib diisi")
    hex_norm = normalize_hex(data.get("hex") or "")
    if not hex_norm:
        raise ValueError("Hex warna tidak valid (harus 6 digit, mis. #1A2B3C)")
    if await db.color_library.find_one({"code": code}, {"_id": 0}):
        raise ValueError(f"Kode warna '{code}' sudah digunakan")
    system = (data.get("system") or "KN").strip().upper()
    if system not in VALID_SYSTEMS:
        system = "KN"
    doc = {
        "id": new_id(PREFIX),
        "code": code,
        "name": name,
        "hex": f"#{hex_norm}",
        "system": system,
        "family": (data.get("family") or "").strip() or "Lainnya",
        "status": "active",
        "created_by": actor_name,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.color_library.insert_one(doc)
    return safe_doc(doc)


async def update_color(color_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    upd: Dict[str, Any] = {}
    if patch.get("name") is not None:
        upd["name"] = str(patch["name"]).strip()
    if patch.get("hex") is not None:
        hex_norm = normalize_hex(patch["hex"])
        if not hex_norm:
            raise ValueError("Hex warna tidak valid")
        upd["hex"] = f"#{hex_norm}"
    if patch.get("family") is not None:
        upd["family"] = str(patch["family"]).strip() or "Lainnya"
    if patch.get("system") is not None:
        sysv = str(patch["system"]).strip().upper()
        upd["system"] = sysv if sysv in VALID_SYSTEMS else "KN"
    if patch.get("status") is not None:
        upd["status"] = str(patch["status"]).strip() or "active"
    if not upd:
        return safe_doc(await db.color_library.find_one({"id": color_id}, {"_id": 0}))
    upd["updated_at"] = now_iso()
    await db.color_library.update_one({"id": color_id}, {"$set": upd})
    return safe_doc(await db.color_library.find_one({"id": color_id}, {"_id": 0}))


async def delete_color(color_id: str) -> Dict[str, Any]:
    res = await db.color_library.update_one(
        {"id": color_id}, {"$set": {"status": "inactive", "updated_at": now_iso()}})
    if res.matched_count == 0:
        raise ValueError("Warna tidak ditemukan")
    return {"deleted": True, "id": color_id}


async def nearest(hex_value: str, limit: int = 8) -> Dict[str, Any]:
    """Cari warna terdekat by hex (ΔE redmean sederhana)."""
    target = hex_to_rgb(hex_value)
    if target is None:
        raise ValueError("Hex tidak valid (mis. #1A2B3C)")
    rows = await db.color_library.find(
        {"status": "active"}, {"_id": 0}).to_list(5000)
    scored = []
    for r in rows:
        rgb = hex_to_rgb(r.get("hex", ""))
        if rgb is None:
            continue
        d = color_distance(target, rgb)
        scored.append({**safe_doc(r), "distance": round(d, 2)})
    scored.sort(key=lambda x: x["distance"])
    top = scored[: max(1, min(limit, 24))]
    return {
        "query_hex": f"#{normalize_hex(hex_value)}",
        "nearest_id": top[0]["id"] if top else None,
        "results": top,
    }
