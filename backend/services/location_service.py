"""Location (Zone→Rack→Level→Bin) & Putaway — Fase 5 (KN_15 §3.1 / KN_16 I11).

Struktur lokasi disimpan EMBEDDED di `warehouses.zones` (SSOT lokasi tunggal — tidak
membuat koleksi paralel). Backward-compatible: rack lama boleh punya `bins` langsung
(dianggap Level default). Bin diidentifikasi flat `id`; `inventory_rolls.bin_id` menunjuk
ke sana. PUTAWAY hanya mengubah `roll.bin_id` (sub-lokasi dalam gudang yang sama) →
TIDAK memengaruhi balance (per product×warehouse×owner) → SSOT-safe.
"""
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from db import db
from core_utils import new_id, now_iso
from entity_scope import EntityContext, resolve_list_scope


def flatten_bins(warehouse: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Semua bin dgn path lengkap. Dukung rack.levels[].bins (baru) & rack.bins (lama)."""
    out: List[Dict[str, Any]] = []
    for zone in warehouse.get("zones", []) or []:
        for rack in zone.get("racks", []) or []:
            base = {
                "zone": zone.get("name", ""), "zone_id": zone.get("id"),
                "rack": rack.get("name", ""), "rack_id": rack.get("id"),
            }
            levels = rack.get("levels")
            if levels:
                for lvl in levels:
                    for b in lvl.get("bins", []) or []:
                        out.append({**base, "bin_id": b.get("id"), "code": b.get("code", ""),
                                    "capacity": float(b.get("capacity", 0) or 0),
                                    "level": lvl.get("name", ""), "level_id": lvl.get("id"),
                                    "path": f"{base['zone']}/{base['rack']}/{lvl.get('name','')}/{b.get('code','')}"})
            else:
                for b in rack.get("bins", []) or []:
                    out.append({**base, "bin_id": b.get("id"), "code": b.get("code", ""),
                                "capacity": float(b.get("capacity", 0) or 0),
                                "level": "", "level_id": None,
                                "path": f"{base['zone']}/{base['rack']}/{b.get('code','')}"})
    return out


async def _bin_occupancy(warehouse_id: str, ctx: EntityContext, entity_id: Optional[str]) -> Dict[str, Dict[str, float]]:
    """Occupancy per bin_id: Σ length_remaining roll fisik (owner-scoped)."""
    from services.roll_service import PHYSICAL_STATUS_TO_BUCKET
    q = resolve_list_scope("inventory_rolls", {
        "warehouse_id": warehouse_id, "length_remaining": {"$gt": 0},
        "status": {"$in": list(PHYSICAL_STATUS_TO_BUCKET.keys())},
    }, ctx, entity_id)
    occ: Dict[str, Dict[str, float]] = {}
    async for r in db.inventory_rolls.find(q, {"_id": 0, "bin_id": 1, "length_remaining": 1}):
        bid = r.get("bin_id") or "__unassigned__"
        d = occ.setdefault(bid, {"qty": 0.0, "rolls": 0.0})
        d["qty"] += float(r.get("length_remaining", 0) or 0)
        d["rolls"] += 1
    return occ


async def warehouse_locations(warehouse_id: str, ctx: EntityContext, entity_id: Optional[str]) -> Dict[str, Any]:
    wh = await db.warehouses.find_one({"id": warehouse_id}, {"_id": 0})
    if not wh:
        raise HTTPException(status_code=404, detail="Gudang tidak ditemukan")
    bins = flatten_bins(wh)
    occ = await _bin_occupancy(warehouse_id, ctx, entity_id)
    for b in bins:
        o = occ.get(b["bin_id"], {"qty": 0.0, "rolls": 0.0})
        b["occupied"] = round(o["qty"], 2)
        b["roll_count"] = int(o["rolls"])
        b["utilization"] = round(o["qty"] / b["capacity"] * 100, 1) if b["capacity"] > 0 else None
    ua = occ.get("__unassigned__", {"qty": 0.0, "rolls": 0.0})
    return {
        "warehouse": {"id": wh["id"], "code": wh.get("code"), "name": wh.get("name")},
        "zones": wh.get("zones", []),
        "bins": bins,
        "unassigned": {"qty": round(ua["qty"], 2), "rolls": int(ua["rolls"])},
        "total_capacity": round(sum(b["capacity"] for b in bins), 2),
        "total_occupied": round(sum(b["occupied"] for b in bins), 2),
        "bin_count": len(bins),
    }


def _ensure_ids(zones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Beri id pada node baru (tanpa id) + normalisasi kapasitas float."""
    for z in zones or []:
        if not z.get("id"):
            z["id"] = new_id("zone")
        for rk in z.get("racks", []) or []:
            if not rk.get("id"):
                rk["id"] = new_id("rack")
            for lvl in rk.get("levels", []) or []:
                if not lvl.get("id"):
                    lvl["id"] = new_id("level")
                for b in lvl.get("bins", []) or []:
                    if not b.get("id"):
                        b["id"] = new_id("bin")
                    b["capacity"] = float(b.get("capacity", 0) or 0)
            for b in rk.get("bins", []) or []:  # legacy bins langsung di rack
                if not b.get("id"):
                    b["id"] = new_id("bin")
                b["capacity"] = float(b.get("capacity", 0) or 0)
    return zones


async def save_warehouse_structure(warehouse_id: str, zones: List[Dict[str, Any]]) -> Dict[str, Any]:
    wh = await db.warehouses.find_one({"id": warehouse_id}, {"_id": 0})
    if not wh:
        raise HTTPException(status_code=404, detail="Gudang tidak ditemukan")
    zones = _ensure_ids(zones or [])
    codes = [b["code"] for b in flatten_bins({"zones": zones}) if b.get("code")]
    if len(codes) != len(set(codes)):
        raise HTTPException(status_code=400, detail="Kode bin harus unik dalam satu gudang.")
    await db.warehouses.update_one(
        {"id": warehouse_id}, {"$set": {"zones": zones, "updated_at": now_iso()}}
    )
    return await db.warehouses.find_one({"id": warehouse_id}, {"_id": 0})


async def putaway_queue(warehouse_id: Optional[str], ctx: EntityContext, entity_id: Optional[str], limit: int = 500) -> List[Dict[str, Any]]:
    """Roll fisik yang BELUM ditempatkan ke bin (bin_id kosong)."""
    from services.roll_service import PHYSICAL_STATUS_TO_BUCKET
    q: Dict[str, Any] = {
        "length_remaining": {"$gt": 0},
        "status": {"$in": list(PHYSICAL_STATUS_TO_BUCKET.keys())},
        "$or": [{"bin_id": None}, {"bin_id": ""}, {"bin_id": {"$exists": False}}],
    }
    if warehouse_id:
        q["warehouse_id"] = warehouse_id
    q = resolve_list_scope("inventory_rolls", q, ctx, entity_id)
    rolls = await db.inventory_rolls.find(
        q, {"_id": 0, "id": 1, "roll_no": 1, "product_id": 1, "warehouse_id": 1,
            "owner_entity_id": 1, "lot": 1, "length_remaining": 1, "unit": 1, "status": 1}
    ).to_list(limit)
    pids = list({r["product_id"] for r in rolls})
    prods = {p["id"]: p for p in await db.products.find(
        {"id": {"$in": pids}}, {"_id": 0, "id": 1, "sku": 1, "name": 1}).to_list(2000)}
    for r in rolls:
        p = prods.get(r["product_id"], {})
        r["sku"] = p.get("sku", "")
        r["product_name"] = p.get("name", "")
    return rolls


async def putaway_roll(roll_id: str, bin_id: str, actor_name: str = "System") -> Dict[str, Any]:
    """Tempatkan/pindahkan roll ke bin (dalam gudang yang sama). Hanya ubah bin_id → SSOT-safe."""
    roll = await db.inventory_rolls.find_one({"id": roll_id}, {"_id": 0})
    if not roll:
        raise HTTPException(status_code=404, detail="Roll tidak ditemukan")
    wh = await db.warehouses.find_one({"id": roll["warehouse_id"]}, {"_id": 0})
    if not wh:
        raise HTTPException(status_code=404, detail="Gudang roll tidak ditemukan")
    bins = {b["bin_id"]: b for b in flatten_bins(wh)}
    if bin_id not in bins:
        raise HTTPException(status_code=400, detail="Bin tujuan tidak ada di gudang roll ini.")
    old_bin = roll.get("bin_id")
    await db.inventory_rolls.update_one(
        {"id": roll_id}, {"$set": {"bin_id": bin_id, "updated_at": now_iso()}}
    )
    await db.inventory_movements.insert_one({
        "id": new_id("mov"), "product_id": roll["product_id"], "warehouse_id": roll["warehouse_id"],
        "owner_entity_id": roll.get("owner_entity_id"), "movement_type": "putaway",
        "quantity": 0.0, "unit": roll.get("unit", "meter"), "lot": roll.get("lot", ""),
        "roll_id": roll_id,
        # FASE U — satu baris mutasi menunjuk SATU roll fisik.
        "qty_rolls": (1 if roll_id else None), "source_document": f"putaway:{old_bin or '-'}->{bin_id}",
        "timestamp": now_iso(),
    })
    return {"roll_id": roll_id, "bin_id": bin_id, "bin_code": bins[bin_id]["code"],
            "bin_path": bins[bin_id]["path"], "from_bin": old_bin}
