"""FASE C — Migrasi & backfill lot (IDEMPOTEN).

Keputusan pemilik #3: **backfill penuh** — setiap string `inventory_rolls.lot` unik
(termasuk `LOT-MIGRATED`, `LOT-PO-00007`, `GREY-MKO-S1A`, …) menjadi dokumen
`inventory_lots` bertanda `source="migration"`; roll mendapat `lot_id`, dan **string
lama TETAP disimpan** (di `roll.lot` sebagai jejak + di `lot.legacy_lot_codes`).

Dipakai dua jalur (satu implementasi — tidak ada logika ganda):
  * `bootstrap.ensure_lots()`  → otomatis saat server start / setelah seed.
  * `backend/scripts/migrate_fase_c_lots.py` → CLI (mendukung `--dry-run`).

Idempoten: jalankan berulang → `changed=0` pada eksekusi kedua.
"""
from __future__ import annotations

from typing import Any, Dict, List

from core_utils import DEFAULT_ENTITY_ID
from db import db
from services import lot_service as ls


async def _rolls_without_lot(limit: int = 100000) -> List[Dict[str, Any]]:
    return await db.inventory_rolls.find(
        {"$or": [{"lot_id": {"$exists": False}}, {"lot_id": None}, {"lot_id": ""}]},
        {"_id": 0, "id": 1, "product_id": 1, "owner_entity_id": 1, "warehouse_id": 1,
         "lot": 1, "dye_lot": 1, "supplier_lot": 1, "status": 1, "stage": 1,
         "supplier_id": 1, "supplier_name": 1, "acquired": 1}).to_list(limit)


async def backfill_missing(actor: str = "Migrasi Fase C", dry_run: bool = False) -> Dict[str, Any]:
    """Tautkan semua roll (dan movement) yang belum punya lot ke `inventory_lots`."""
    rolls = await _rolls_without_lot()
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    orphan_products: List[str] = []
    for r in rolls:
        key = (r.get("owner_entity_id") or DEFAULT_ENTITY_ID,
               r.get("product_id") or "",
               (r.get("lot") or "").strip() or "LOT-MIGRATED",
               (r.get("dye_lot") or "").strip())
        groups.setdefault(key, []).append(r)

    lots_created = rolls_linked = 0
    touched: List[str] = []
    for (owner, product_id, lot_code, dye_lot), members in groups.items():
        if not product_id:
            continue
        if not await db.products.find_one({"id": product_id}, {"_id": 0, "id": 1}):
            orphan_products.append(product_id)
            continue
        if dry_run:
            lots_created += 1
            rolls_linked += len(members)
            continue
        first = members[0]
        before = await db[ls.COLL].count_documents({})
        lot = await ls.resolve_or_create(
            product_id=product_id, owner_entity_id=owner,
            warehouse_id=first.get("warehouse_id", ""), lot_code=lot_code,
            source="migration",
            source_ref={"type": "legacy_roll", "id": first.get("id", ""),
                        "number": lot_code},
            supplier_lot=(first.get("supplier_lot") or ""), dye_lot=dye_lot,
            supplier_id=first.get("supplier_id", ""),
            supplier_name=first.get("supplier_name", ""),
            status="karantina" if first.get("status") == "quarantine" else "released",
            actor=actor)
        if await db[ls.COLL].count_documents({}) > before:
            lots_created += 1
        # `set_lot_string=False` → string lot lama pada roll DIPERTAHANKAN (jejak, keputusan #3)
        await ls.attach_rolls(lot["id"], [m["id"] for m in members],
                              set_lot_string=False, actor=actor)
        rolls_linked += len(members)
        touched.append(lot["id"])

    # Movement lama: isi `lot_id` dari roll (append-only → hanya field jejak ditambah)
    movements_linked = 0
    movements_orphan = 0
    mv_missing = await db.inventory_movements.find(
        {"roll_id": {"$nin": [None, ""]},
         "$or": [{"lot_id": {"$exists": False}}, {"lot_id": None}, {"lot_id": ""}]},
        {"_id": 0, "id": 1, "roll_id": 1}).to_list(100000)
    if mv_missing:
        roll_ids = list({m["roll_id"] for m in mv_missing})
        lot_by_roll = {r["id"]: r.get("lot_id") for r in await db.inventory_rolls.find(
            {"id": {"$in": roll_ids}}, {"_id": 0, "id": 1, "lot_id": 1}).to_list(100000)}
        buckets: Dict[str, List[str]] = {}
        for m in mv_missing:
            lid = lot_by_roll.get(m["roll_id"])
            if lid:
                buckets.setdefault(lid, []).append(m["id"])
            else:
                # movement lama menunjuk roll yang sudah tidak ada (mis. `ROLL-001`
                # dari data awal) → TIDAK dikarang lot-nya; dilaporkan apa adanya.
                movements_orphan += 1
        if dry_run:
            movements_linked = sum(len(v) for v in buckets.values())
        else:
            for lid, ids in buckets.items():
                res = await db.inventory_movements.update_many(
                    {"id": {"$in": ids}}, {"$set": {"lot_id": lid}})
                movements_linked += res.modified_count

    if not dry_run:
        await ls.recompute_many(touched)
    return {
        "dry_run": dry_run,
        "rolls_without_lot": len(rolls),
        "lots_created": lots_created,
        "rolls_linked": rolls_linked,
        "movements_linked": movements_linked,
        "movements_orphan_roll": movements_orphan,
        "orphan_products": sorted(set(orphan_products)),
        "changed": lots_created + rolls_linked + movements_linked,
    }


async def recompute_all() -> int:
    """Segarkan agregat SEMUA lot (dipakai setelah migrasi / perbaikan data)."""
    ids = [l["id"] for l in await db[ls.COLL].find({}, {"_id": 0, "id": 1}).to_list(100000)]
    return await ls.recompute_many(ids)


async def run_all(actor: str = "Migrasi Fase C", dry_run: bool = False) -> Dict[str, Any]:
    """Urutan lengkap: pengaturan default → backfill → recompute agregat."""
    settings_created = await ls.ensure_defaults(actor=actor, dry_run=dry_run)
    out = await backfill_missing(actor=actor, dry_run=dry_run)
    out["settings_created"] = settings_created
    out["changed"] += 1 if settings_created else 0
    if not dry_run:
        out["lots_recomputed"] = await recompute_all()
    return out
