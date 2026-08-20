"""R6.4 — Produksi In-House (BOM + Work Order).

Koleksi (prefix mfg_*, SCOPED per entitas):
- `mfg_boms` (bom_): resep produksi in-house MULTI-komponen.
    output_product_id + components[{material_product_id, qty_per_unit}] + overhead_per_unit (opsional).
    `qty_per_unit` = kebutuhan bahan per 1 unit (base_unit) output.
- `mfg_work_orders` (wo_): perintah kerja.
    complete = KONSUMSI roll bahan (FEFO, owner+gudang) → PRODUKSI roll barang jadi (Roll-as-SSOT).

GL-safe (invarian INV-GL-DRIFT / GL-3): bahan & barang jadi memakai akun Persediaan 1-1300 yang
sama, sehingga transformasi bahan NET-0 di GL (subledger roll sudah menyeimbangkan). Hanya OVERHEAD
(opsional) yang menambah nilai persediaan → Dr 1-1300 / Cr 5-1100 (Overhead Diserap). Idempotent per WO.

Valuasi: konsumsi bahan pada unit_cost roll (WAC/landed-inclusive) — identik dengan basis GL-3.
Barang jadi dinilai (Σ nilai bahan + overhead) / qty → dibawa sebagai unit_cost roll output.
"""
from typing import Any, Dict, List, Optional, Tuple

from db import db
from core_utils import new_id, now_iso, safe_doc
from services import roll_service
from services import gl_service

EPS = 0.005

BOM_ACTIVE, BOM_INACTIVE = "active", "inactive"
BOM_STATUSES = (BOM_ACTIVE, BOM_INACTIVE)

WO_DRAFT, WO_RELEASED, WO_COMPLETED, WO_CANCELLED = "draft", "released", "completed", "cancelled"
WO_OPEN = (WO_DRAFT, WO_RELEASED)


def _r(v: Any) -> float:
    return round(float(v or 0), 2)


async def _product(pid: str) -> Dict[str, Any]:
    if not pid:
        return {}
    return await db.products.find_one({"id": pid}, {"_id": 0}) or {}


async def _warehouse(wid: str) -> Dict[str, Any]:
    if not wid:
        return {}
    return await db.warehouses.find_one({"id": wid}, {"_id": 0}) or {}


# ═══ Validasi komponen BOM ═══════════════════════════════════════════════════
async def _validate_components(comps_in: List[Dict[str, Any]], output_pid: str) -> List[Dict[str, Any]]:
    if not comps_in:
        raise ValueError("Minimal satu komponen bahan diperlukan.")
    out: List[Dict[str, Any]] = []
    seen = set()
    for c in comps_in:
        mpid = (c.get("material_product_id") or "").strip()
        if not mpid:
            raise ValueError("material_product_id komponen wajib diisi.")
        if mpid == output_pid:
            raise ValueError("Bahan komponen tidak boleh sama dengan produk output.")
        if mpid in seen:
            raise ValueError("Komponen bahan duplikat pada BOM.")
        mp = await _product(mpid)
        if not mp:
            raise ValueError(f"Produk bahan '{mpid}' tidak ditemukan.")
        qpu = _r(c.get("qty_per_unit"))
        if qpu <= 0:
            raise ValueError("qty_per_unit tiap komponen harus > 0.")
        seen.add(mpid)
        out.append({
            "material_product_id": mpid,
            "sku": mp.get("sku", ""),
            "name": mp.get("name", ""),
            "unit": mp.get("base_unit", "meter"),
            "qty_per_unit": qpu,
        })
    return out


# ═══ BOM CRUD ════════════════════════════════════════════════════════════════
async def create_bom(payload: Dict[str, Any], entity_id: str, actor_name: str = "") -> Dict[str, Any]:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("Nama BOM wajib diisi.")
    out_pid = (payload.get("output_product_id") or "").strip()
    op = await _product(out_pid)
    if not op:
        raise ValueError("Produk output tidak ditemukan.")
    components = await _validate_components(payload.get("components") or [], out_pid)
    overhead = _r(payload.get("overhead_per_unit"))
    if overhead < 0:
        raise ValueError("overhead_per_unit tidak boleh negatif.")
    doc = {
        "id": new_id("bom"),
        "entity_id": entity_id,
        "name": name,
        "output_product_id": out_pid,
        "output_sku": op.get("sku", ""),
        "output_name": op.get("name", ""),
        "output_unit": op.get("base_unit", "meter"),
        "overhead_per_unit": overhead,
        "components": components,
        "status": BOM_ACTIVE,
        "notes": (payload.get("notes") or "").strip(),
        "created_by": actor_name,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.mfg_boms.insert_one(dict(doc))
    return safe_doc(doc)


async def list_boms(scope: Optional[Dict[str, Any]], status: Optional[str] = None,
                    output_product_id: Optional[str] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {**(scope or {})}
    if status:
        q["status"] = status
    if output_product_id:
        q["output_product_id"] = output_product_id
    return await db.mfg_boms.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


async def get_bom(bom_id: str, scope: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    return await db.mfg_boms.find_one({"id": bom_id, **(scope or {})}, {"_id": 0})


async def update_bom(bom_id: str, patch: Dict[str, Any],
                     scope: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    cur = await get_bom(bom_id, scope)
    if not cur:
        return None
    upd: Dict[str, Any] = {"updated_at": now_iso()}
    if patch.get("name") is not None:
        if not str(patch["name"]).strip():
            raise ValueError("Nama BOM tidak boleh kosong.")
        upd["name"] = str(patch["name"]).strip()
    if patch.get("notes") is not None:
        upd["notes"] = str(patch["notes"]).strip()
    if patch.get("status") is not None:
        if patch["status"] not in BOM_STATUSES:
            raise ValueError("status BOM harus 'active' atau 'inactive'.")
        upd["status"] = patch["status"]
    if patch.get("overhead_per_unit") is not None:
        ov = _r(patch["overhead_per_unit"])
        if ov < 0:
            raise ValueError("overhead_per_unit tidak boleh negatif.")
        upd["overhead_per_unit"] = ov
    if patch.get("components") is not None:
        upd["components"] = await _validate_components(patch["components"], cur["output_product_id"])
    res = await db.mfg_boms.find_one_and_update(
        {"id": bom_id, **(scope or {})}, {"$set": upd}, return_document=True)
    if res:
        res.pop("_id", None)
    return res


async def delete_bom(bom_id: str, scope: Optional[Dict[str, Any]] = None) -> bool:
    used = await db.mfg_work_orders.count_documents({"bom_id": bom_id, "status": {"$in": list(WO_OPEN)}})
    if used:
        raise ValueError("BOM dipakai Work Order yang masih terbuka — batalkan/selesaikan dulu.")
    res = await db.mfg_boms.delete_one({"id": bom_id, **(scope or {})})
    return res.deleted_count > 0


# ═══ Ketersediaan & rencana bahan ════════════════════════════════════════════
async def _available_qty(product_id: str, warehouse_id: str, owner_entity_id: str) -> float:
    rolls = await db.inventory_rolls.find(
        {"product_id": product_id, "warehouse_id": warehouse_id, "owner_entity_id": owner_entity_id,
         "status": "available", "length_remaining": {"$gt": 0}},
        {"_id": 0, "length_remaining": 1}).to_list(100000)
    return _r(sum(float(r.get("length_remaining", 0) or 0) for r in rolls))


async def _material_plan(bom: Dict[str, Any], planned_qty: float,
                         warehouse_id: str, entity_id: str) -> List[Dict[str, Any]]:
    plan: List[Dict[str, Any]] = []
    for c in bom.get("components", []):
        need = _r(c["qty_per_unit"] * planned_qty)
        avail = await _available_qty(c["material_product_id"], warehouse_id, entity_id)
        plan.append({
            "material_product_id": c["material_product_id"], "sku": c.get("sku", ""),
            "name": c.get("name", ""), "unit": c.get("unit", "meter"),
            "qty_per_unit": c["qty_per_unit"], "required_qty": need,
            "available_qty": avail, "sufficient": avail + EPS >= need,
        })
    return plan


# ═══ Nomor WO ════════════════════════════════════════════════════════════════
async def _next_wo_number() -> str:
    last = await db.mfg_work_orders.find_one({}, {"_id": 0, "wo_number": 1}, sort=[("wo_number", -1)])
    n = 0
    if last and isinstance(last.get("wo_number"), str) and last["wo_number"].startswith("WO-"):
        try:
            n = int(last["wo_number"].split("-")[1])
        except (ValueError, IndexError):
            n = 0
    return f"WO-{n + 1:05d}"


# ═══ Work Order — CRUD & transisi ════════════════════════════════════════════
async def create_work_order(payload: Dict[str, Any], entity_id: str,
                            actor_name: str = "") -> Dict[str, Any]:
    bom = await get_bom((payload.get("bom_id") or "").strip(), {"entity_id": entity_id})
    if not bom:
        raise ValueError("BOM tidak ditemukan pada entitas ini.")
    if bom.get("status") != BOM_ACTIVE:
        raise ValueError("BOM non-aktif tidak bisa dijadikan Work Order.")
    planned_qty = _r(payload.get("planned_qty"))
    if planned_qty <= 0:
        raise ValueError("Jumlah produksi (planned_qty) harus > 0.")
    warehouse_id = (payload.get("warehouse_id") or "").strip()
    wh = await _warehouse(warehouse_id)
    if not wh:
        raise ValueError("Gudang produksi tidak ditemukan.")
    plan = await _material_plan(bom, planned_qty, warehouse_id, entity_id)
    doc = {
        "id": new_id("wo"),
        "wo_number": await _next_wo_number(),
        "entity_id": entity_id,
        "bom_id": bom["id"],
        "bom_name": bom.get("name", ""),
        "output_product_id": bom["output_product_id"],
        "output_sku": bom.get("output_sku", ""),
        "output_name": bom.get("output_name", ""),
        "output_unit": bom.get("output_unit", "meter"),
        "warehouse_id": warehouse_id,
        "warehouse_name": wh.get("name", ""),
        "planned_qty": planned_qty,
        "overhead_per_unit": _r(bom.get("overhead_per_unit")),
        "material_plan": plan,
        "status": WO_DRAFT,
        "notes": (payload.get("notes") or "").strip(),
        "consumed": [],
        "produced_roll_ids": [],
        "produced_qty": 0.0,
        "material_cost": 0.0,
        "overhead_cost": 0.0,
        "total_cost": 0.0,
        "unit_cost": 0.0,
        "je_id": "",
        "created_by": actor_name,
        "created_at": now_iso(),
        "released_at": "",
        "completed_at": "",
    }
    await db.mfg_work_orders.insert_one(dict(doc))
    return safe_doc(doc)


async def list_work_orders(scope: Optional[Dict[str, Any]], status: Optional[str] = None,
                           bom_id: Optional[str] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {**(scope or {})}
    if status:
        q["status"] = status
    if bom_id:
        q["bom_id"] = bom_id
    return await db.mfg_work_orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


async def get_work_order(wo_id: str, scope: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    wo = await db.mfg_work_orders.find_one({"id": wo_id, **(scope or {})}, {"_id": 0})
    if wo:
        bom = await get_bom(wo.get("bom_id", ""), None)
        # refresh availability snapshot for open WO (informational)
        if wo.get("status") in WO_OPEN and bom:
            wo["material_plan"] = await _material_plan(bom, wo.get("planned_qty", 0),
                                                       wo.get("warehouse_id", ""), wo.get("entity_id", ""))
    return wo


async def release_work_order(wo_id: str, scope: Optional[Dict[str, Any]] = None,
                             actor_name: str = "") -> Dict[str, Any]:
    wo = await db.mfg_work_orders.find_one({"id": wo_id, **(scope or {})}, {"_id": 0})
    if not wo:
        raise ValueError("Work Order tidak ditemukan.")
    if wo["status"] == WO_RELEASED:
        return wo
    if wo["status"] != WO_DRAFT:
        raise ValueError(f"Work Order status '{wo['status']}' tidak bisa dirilis.")
    bom = await get_bom(wo["bom_id"], None)
    plan = await _material_plan(bom, wo["planned_qty"], wo["warehouse_id"], wo["entity_id"]) if bom else wo["material_plan"]
    await db.mfg_work_orders.update_one({"id": wo_id}, {"$set": {
        "status": WO_RELEASED, "material_plan": plan, "released_at": now_iso(),
        "released_by": actor_name, "updated_at": now_iso()}})
    return await db.mfg_work_orders.find_one({"id": wo_id}, {"_id": 0})


async def cancel_work_order(wo_id: str, scope: Optional[Dict[str, Any]] = None,
                            actor_name: str = "", reason: str = "") -> Dict[str, Any]:
    wo = await db.mfg_work_orders.find_one({"id": wo_id, **(scope or {})}, {"_id": 0})
    if not wo:
        raise ValueError("Work Order tidak ditemukan.")
    if wo["status"] == WO_CANCELLED:
        return wo
    if wo["status"] == WO_COMPLETED:
        raise ValueError("Work Order yang sudah selesai tidak bisa dibatalkan.")
    await db.mfg_work_orders.update_one({"id": wo_id}, {"$set": {
        "status": WO_CANCELLED, "cancel_reason": reason, "cancelled_by": actor_name,
        "cancelled_at": now_iso(), "updated_at": now_iso()}})
    return await db.mfg_work_orders.find_one({"id": wo_id}, {"_id": 0})


# ═══ Konsumsi roll bahan (FEFO) — mirror cycle_count (Roll-as-SSOT safe) ══════
async def _consume_material(product_id: str, warehouse_id: str, owner_entity_id: str,
                            need: float, wo_id: str) -> Tuple[float, float, List[str]]:
    """Kurangi roll `available` FEFO sebesar `need`.

    Return (qty_consumed, value_consumed, lot_ids_bahan). `lot_ids` dipakai Fase C
    sebagai INDUK lot barang jadi (genealogi produksi in-house).
    """
    need = _r(need)
    if need <= EPS:
        return 0.0, 0.0, []
    rolls = await db.inventory_rolls.find(
        {"product_id": product_id, "warehouse_id": warehouse_id, "owner_entity_id": owner_entity_id,
         "status": "available", "length_remaining": {"$gt": 0}}, {"_id": 0}).to_list(100000)
    rolls.sort(key=lambda r: (r.get("created_at", ""), -float(r.get("length_remaining", 0) or 0)))
    total_avail = _r(sum(float(r.get("length_remaining", 0) or 0) for r in rolls))
    if total_avail + EPS < need:
        raise ValueError(f"Stok bahan {product_id} tidak cukup: butuh {need:g}, tersedia {total_avail:g}.")
    consumed_qty = 0.0
    value = 0.0
    lot_ids: List[str] = []
    for r in rolls:
        if need <= EPS:
            break
        rlen = float(r.get("length_remaining", 0) or 0)
        take = round(min(rlen, need), 2)
        if take <= 0:
            continue
        uc = float(r.get("unit_cost") or r.get("base_unit_cost") or 0)
        value += take * uc
        new_len = round(rlen - take, 2)
        if new_len <= EPS:
            await db.inventory_rolls.update_one(
                {"id": r["id"]}, {"$set": {"length_remaining": 0.0, "status": "consumed",
                                           "updated_at": now_iso()}})
        else:
            await db.inventory_rolls.update_one(
                {"id": r["id"]}, {"$set": {"length_remaining": new_len, "updated_at": now_iso()}})
        await db.inventory_movements.insert_one({
            "id": new_id("mov"), "product_id": product_id, "warehouse_id": warehouse_id,
            "owner_entity_id": owner_entity_id, "movement_type": "production_consume",
            "quantity": -take, "unit": r.get("unit", "meter"), "lot": r.get("lot", ""),
            "lot_id": r.get("lot_id", ""),
            "roll_id": r["id"],
            # FASE U — satu baris mutasi menunjuk SATU roll fisik.
            "qty_rolls": (1 if r["id"] else None), "source_document": wo_id, "timestamp": now_iso(),
        })
        if r.get("lot_id") and r["lot_id"] not in lot_ids:
            lot_ids.append(r["lot_id"])
        consumed_qty += take
        need = round(need - take, 2)
    await roll_service.rebuild_balance(product_id, warehouse_id, owner_entity_id)
    return round(consumed_qty, 2), round(value, 2), lot_ids


# ═══ Selesaikan WO — konsumsi bahan → produksi barang jadi ═══════════════════
async def complete_work_order(wo_id: str, scope: Optional[Dict[str, Any]] = None,
                              actor_name: str = "") -> Dict[str, Any]:
    wo = await db.mfg_work_orders.find_one({"id": wo_id, **(scope or {})}, {"_id": 0})
    if not wo:
        raise ValueError("Work Order tidak ditemukan.")
    if wo["status"] == WO_COMPLETED:
        return wo  # idempotent
    if wo["status"] == WO_CANCELLED:
        raise ValueError("Work Order dibatalkan — tidak bisa diselesaikan.")

    bom = await get_bom(wo["bom_id"], None)
    if not bom:
        raise ValueError("BOM Work Order tidak ditemukan lagi.")
    entity_id = wo["entity_id"]
    warehouse_id = wo["warehouse_id"]
    planned_qty = _r(wo["planned_qty"])

    # Pre-check ketersediaan semua bahan (fail-fast sebelum mutasi apapun).
    for c in bom["components"]:
        need = _r(c["qty_per_unit"] * planned_qty)
        avail = await _available_qty(c["material_product_id"], warehouse_id, entity_id)
        if avail + EPS < need:
            raise ValueError(f"Stok bahan {c.get('name') or c['material_product_id']} tidak cukup: "
                             f"butuh {need:g} {c.get('unit', '')}, tersedia {avail:g}.")

    # Konsumsi bahan (FEFO) + akumulasi nilai.
    consumed: List[Dict[str, Any]] = []
    material_cost = 0.0
    material_lot_ids: List[str] = []
    for c in bom["components"]:
        need = _r(c["qty_per_unit"] * planned_qty)
        qty, val, _lots_in = await _consume_material(c["material_product_id"], warehouse_id,
                                                     entity_id, need, wo_id)
        material_cost += val
        material_lot_ids.extend([l for l in _lots_in if l not in material_lot_ids])
        consumed.append({"material_product_id": c["material_product_id"], "sku": c.get("sku", ""),
                         "name": c.get("name", ""), "unit": c.get("unit", "meter"),
                         "qty": qty, "value": round(val, 2), "lot_ids": _lots_in})
    material_cost = round(material_cost, 2)
    overhead_cost = _r(wo.get("overhead_per_unit") or bom.get("overhead_per_unit")) * planned_qty
    overhead_cost = round(overhead_cost, 2)
    total_cost = round(material_cost + overhead_cost, 2)
    unit_cost = round(total_cost / planned_qty, 4) if planned_qty > 0 else 0.0

    # Produksi roll barang jadi (Roll-as-SSOT) — dinilai HPP produksi.
    # FASE C — lot barang jadi = anak dari lot bahan (genealogi produksi in-house).
    roll = await roll_service.create_inbound_roll(
        wo["output_product_id"], warehouse_id, entity_id, planned_qty,
        acquired_via="production_output", ref_id=wo_id, created_by=actor_name or "System",
        unit_cost=unit_cost, lot_source="production",
        lot_source_ref={"type": "work_order", "id": wo_id,
                        "number": wo.get("wo_number", "")},
        parent_lot_ids=material_lot_ids)

    # GL: kapitalisasi overhead (bila ada). Porsi bahan NET-0 (akun 1-1300 sama).
    je = await gl_service.post_production_output(
        wo_id=wo_id, entity_id=entity_id, overhead=overhead_cost, label=wo.get("wo_number", ""))

    await db.mfg_work_orders.update_one({"id": wo_id}, {"$set": {
        "status": WO_COMPLETED, "consumed": consumed,
        "produced_roll_ids": [roll["id"]], "produced_qty": planned_qty,
        "output_lot_id": roll.get("lot_id", ""), "output_lot_number": roll.get("lot", ""),
        "input_lot_ids": material_lot_ids,
        "material_cost": material_cost, "overhead_cost": overhead_cost,
        "total_cost": total_cost, "unit_cost": unit_cost,
        "je_id": (je or {}).get("id", ""), "completed_by": actor_name,
        "completed_at": now_iso(), "updated_at": now_iso()}})
    return await db.mfg_work_orders.find_one({"id": wo_id}, {"_id": 0})


# ═══ Ringkasan (dashboard produksi) ══════════════════════════════════════════
async def summary(scope: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    q = {**(scope or {})}
    wos = await db.mfg_work_orders.find(q, {"_id": 0}).to_list(5000)
    by_status: Dict[str, int] = {}
    produced_value = 0.0
    produced_qty = 0.0
    for w in wos:
        by_status[w.get("status", "?")] = by_status.get(w.get("status", "?"), 0) + 1
        if w.get("status") == WO_COMPLETED:
            produced_value += _r(w.get("total_cost"))
            produced_qty += _r(w.get("produced_qty"))
    boms = await db.mfg_boms.count_documents(q)
    return {
        "boms": boms,
        "work_orders": len(wos),
        "by_status": by_status,
        "completed": by_status.get(WO_COMPLETED, 0),
        "open": by_status.get(WO_DRAFT, 0) + by_status.get(WO_RELEASED, 0),
        "produced_qty": round(produced_qty, 2),
        "produced_value": round(produced_value, 2),
        "generated_at": now_iso(),
    }
