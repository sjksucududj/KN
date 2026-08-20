"""F0-C — Migrasi/backfill entity_id pada koleksi SCOPED (idempotent).

Men-stamp field entitas pada dokumen legacy yang belum ber-entitas, menurunkan
entitas dari dokumen sumber bila memungkinkan (wms_tasks←PO, shipments←SO),
selebihnya default ke entitas primer (ent_ksc).

Pakai:
    cd /app/backend && python -m scripts.migrate_entity_scoping --dry-run
    cd /app/backend && python -m scripts.migrate_entity_scoping        # eksekusi
Aman diulang: hanya menyentuh dokumen yang field-nya kosong/hilang.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import db  # noqa: E402
from entity_scope import field_for, SCOPED_COLLECTIONS  # noqa: E402
from services.entity_context_service import PRIMARY_ENTITY_ID  # noqa: E402


def _missing_filter(field: str) -> dict:
    return {"$or": [{field: {"$exists": False}}, {field: None}, {field: ""}]}


async def _entity_from_po(po_id):
    if not po_id:
        return None
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0, "entity_id": 1})
    return (po or {}).get("entity_id")


async def _entity_from_so(order_id):
    if not order_id:
        return None
    so = await db.sales_orders.find_one({"id": order_id}, {"_id": 0, "entity_id": 1})
    return (so or {}).get("entity_id")


async def _resolve_wms_task(doc):
    return (await _entity_from_po(doc.get("po_id"))) or \
           (await _entity_from_so(doc.get("order_id"))) or PRIMARY_ENTITY_ID


async def _resolve_shipment(doc):
    return (await _entity_from_so(doc.get("order_id"))) or PRIMARY_ENTITY_ID


async def _resolve_default(doc):
    return PRIMARY_ENTITY_ID


# (collection, resolver) — hanya koleksi yang ada & butuh backfill.
PLAN = [
    ("wms_tasks", _resolve_wms_task),
    ("shipments", _resolve_shipment),
    # F0-E SELESAI: gl_accounts = SHARED (CoA by-code) → tidak di-stamp entitas.
    ("audit_logs", _resolve_default),
]


async def migrate(dry_run: bool) -> int:
    real = set(await db.list_collection_names())
    total_updated = 0
    print(f"{'=' * 60}\nF0-C migrate_entity_scoping  (dry_run={dry_run})  primary={PRIMARY_ENTITY_ID}\n{'=' * 60}")
    for coll, resolver in PLAN:
        if coll not in real:
            print(f"[skip] {coll}: koleksi tidak ada")
            continue
        field = field_for(coll) or "entity_id"
        cursor = db[coll].find(_missing_filter(field))
        breakdown, n = {}, 0
        async for doc in cursor:
            eid = await resolver(doc)
            breakdown[eid] = breakdown.get(eid, 0) + 1
            n += 1
            if not dry_run:
                await db[coll].update_one({"id": doc["id"]}, {"$set": {field: eid}})
        total_updated += n
        tag = "WOULD stamp" if dry_run else "stamped"
        print(f"[{coll}] {tag} {n} doc → {field}  breakdown={breakdown or '-'}")

    # Catch-all: koleksi SCOPED lain yang masih punya dok tanpa entitas → PRIMARY.
    handled = {c for c, _ in PLAN}
    for coll in sorted(SCOPED_COLLECTIONS):
        if coll in handled or coll not in real:
            continue
        field = field_for(coll) or "entity_id"
        n = await db[coll].count_documents(_missing_filter(field))
        if n == 0:
            continue
        if not dry_run:
            await db[coll].update_many(_missing_filter(field), {"$set": {field: PRIMARY_ENTITY_ID}})
        total_updated += n
        tag = "WOULD stamp" if dry_run else "stamped"
        print(f"[{coll}] (catch-all) {tag} {n} doc → {field}={PRIMARY_ENTITY_ID}")

    print("-" * 60)
    print(f"Total {'(dry-run) ' if dry_run else ''}updated: {total_updated}")
    return total_updated


async def validate() -> bool:
    real = set(await db.list_collection_names())
    print(f"\n{'=' * 60}\nVALIDASI: 0 dokumen SCOPED tanpa field entitas\n{'=' * 60}")
    ok = True
    for coll in sorted(SCOPED_COLLECTIONS):
        if coll not in real:
            continue
        field = field_for(coll) or "entity_id"
        missing = await db[coll].count_documents(_missing_filter(field))
        status = "OK" if missing == 0 else "FAIL"
        if missing:
            ok = False
        print(f"  [{status}] {coll:24} missing={missing}")
    print("-" * 60)
    print("HASIL:", "✅ LULUS — semua koleksi SCOPED ter-stamp" if ok else "❌ GAGAL — masih ada dokumen tanpa entitas")
    return ok


async def run_full_migration() -> bool:
    """Entry programatik (dipakai seed): backfill + validasi. True bila lulus."""
    await migrate(dry_run=False)
    return await validate()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="hanya simulasi, tidak menulis")
    args = ap.parse_args()
    await migrate(args.dry_run)
    if not args.dry_run:
        ok = await validate()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
