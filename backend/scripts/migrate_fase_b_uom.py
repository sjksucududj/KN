#!/usr/bin/env python3
"""migrate_fase_b_uom.py — MIGRASI IDEMPOTEN Fase B (konversi satuan · D-06/D-07).

Yang dikerjakan (boleh dijalankan berulang, aman untuk produksi):
  1. **Seed aturan konversi GLOBAL** (konstanta fisika: yard/cm/inch/feet/km ↔ meter,
     gram/ton/lbs/ounce ↔ kg, dozen/gross → piece, sqft ↔ m², formula GSM × lebar)
     + pengaturan **toleransi** (`system_settings` scope `uom`) bila belum ada.
  2. **Backfill jejak konversi** (`uom_trail`) + `base_unit`/`quantity_base` pada
     dokumen lama: `purchase_orders.items[]` & `purchase_requisitions.items[]`.
     Jejak hasil migrasi ditandai `source_migrated=true` agar bisa dibedakan dari
     konversi yang benar-benar dilakukan user.
  3. Melaporkan baris yang **tidak bisa dikonversi** (tidak ada aturan) — TIDAK
     mengarang faktor; baris itu ditandai `uom_unresolved=true` supaya bisa
     dilengkapi user lewat layar Konversi Satuan.

Pemakaian:
    python backend/scripts/migrate_fase_b_uom.py            # jalankan migrasi
    python backend/scripts/migrate_fase_b_uom.py --dry-run   # hanya laporan
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv                                     # noqa: E402
load_dotenv(ROOT / "backend" / ".env")

from db import db                                                  # noqa: E402
from core_utils import now_iso                                     # noqa: E402
from services import uom_rules_service as uomr                     # noqa: E402

DRY = "--dry-run" in sys.argv


async def _backfill(coll_name: str, number_field: str, context: str,
                    engine: dict) -> dict:
    coll = db[coll_name]
    docs = await coll.find({}, {"_id": 0}).to_list(20000)
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(20000)}
    changed, unresolved, skipped = 0, 0, 0
    for doc in docs:
        items = doc.get("items") or []
        touched = False
        for it in items:
            if it.get("uom_trail"):
                skipped += 1
                continue
            pid = it.get("product_id") or ""
            prod = products.get(pid)
            if not prod:
                skipped += 1
                continue
            base_unit = prod.get("base_unit", "meter")
            unit = it.get("unit") or base_unit
            qty = it.get("quantity") or 0
            try:
                trail = await uomr.convert_with_trail(
                    prod, qty, unit, base_unit, engine=engine, context=context)
            except uomr.UomRuleError:
                it["uom_unresolved"] = True
                unresolved += 1
                touched = True
                continue
            trail["source_migrated"] = True
            it["uom_trail"] = trail
            it["base_unit"] = base_unit
            it["quantity_base"] = trail["base_qty"]
            it.pop("uom_unresolved", None)
            touched = True
        if touched and not DRY:
            await coll.update_one({"id": doc["id"]},
                                  {"$set": {"items": items, "updated_at": now_iso()}})
        if touched:
            changed += 1
    return {"collection": coll_name, "docs_changed": changed,
            "items_unresolved": unresolved, "items_skipped": skipped,
            "docs_total": len(docs), "number_field": number_field}


async def main() -> int:
    print("=" * 74)
    print(f"  MIGRASI FASE B — KONVERSI SATUAN {'(DRY RUN)' if DRY else ''}")
    print(f"  DB: {os.environ.get('DB_NAME')}")
    print("=" * 74)

    seeded = {"rules_created": 0, "rules_existing": 0}
    if not DRY:
        seeded = await uomr.ensure_defaults(actor="migration")
    print(f"1) Aturan global   : dibuat {seeded['rules_created']} · sudah ada "
          f"{seeded['rules_existing']}")
    settings = await uomr.get_settings()
    print(f"   Toleransi        : peringatan {settings['warn_pct']}% · blokir "
          f"{settings['block_pct']}% · override "
          f"{'diizinkan' if settings['allow_override'] else 'dilarang'} · "
          f"pembulatan {settings['precision']}")

    engine = await uomr.load_engine()
    rep_po = await _backfill("purchase_orders", "po_number", "purchase_order_migrated", engine)
    rep_pr = await _backfill("purchase_requisitions", "number", "purchase_requisition_migrated",
                             engine)
    for rep in (rep_po, rep_pr):
        print(f"2) {rep['collection']:<24} dokumen diubah {rep['docs_changed']}"
              f" / {rep['docs_total']} · item dilewati (sudah berjejak) {rep['items_skipped']}"
              f" · item tanpa aturan {rep['items_unresolved']}")

    total_changed = rep_po["docs_changed"] + rep_pr["docs_changed"]
    unresolved = rep_po["items_unresolved"] + rep_pr["items_unresolved"]
    rules_total = len(await uomr.list_rules())
    print("-" * 74)
    print(f"Ringkasan: changed={total_changed} · aturan_total={rules_total} · "
          f"item_tanpa_aturan={unresolved}")
    if unresolved:
        print("  ⚠️  Lengkapi aturan di Produk & Harga → Konversi Satuan "
              "(atau isi gramasi & lebar produk) lalu jalankan ulang migrasi.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
