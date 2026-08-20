#!/usr/bin/env python3
"""FASE E-0 (E0.7 + E0.8b/E0.8e) — Migrasi & pembersihan referensi entitas.

Idempotent. Aman dijalankan berulang. Semua perubahan DILAPORKAN per baris supaya
tidak ada "perbaikan diam-diam" (aturan §2.3 plan.md: gagal berisik, bukan diam-diam).

Yang dikerjakan:
  1. **Backfill `warehouse_transfers.entity_id`** (L14) — 2 dokumen antar-PT tidak
     punya `entity_id` sama sekali sehingga lolos dari registry ter-scope.
     Aturan: `entity_id = source_entity_id` (pemilik barang saat dokumen lahir).
  2. **Backfill `notifications.entity_id`** yang bisa disimpulkan dari dokumen acuan
     (`ref`, mis. `po_appr:<id>`) — sisanya dibiarkan `None` = notifikasi sistem.
  3. **Stempel entitas `sales_targets` / `sales_incentives`** (L12) diselaraskan ke
     `users.home_entity_id` pemiliknya (kasus nyata: target & insentif Citra Lestari,
     sales CV Kanda Suka, ter-stempel `ent_ksc`).
  4. **Laporan dokumen YATIM** — dokumen ber-`entity_id` yang entitasnya sudah tidak
     ada (kasus nyata: 12 baris `hr_org_units` menunjuk `ent_f39d5cfe1728` yang sudah
     dihapus). Dengan `--fix` baris yatim dipindahkan ke entitas home admin pertama
     bila koleksinya infrastruktur (hr_org_units), sisanya hanya dilaporkan.

Pakai:
    python /app/scripts/fix_orphan_entity_refs.py            # laporan saja (dry-run)
    python /app/scripts/fix_orphan_entity_refs.py --fix      # terapkan
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")

from db import db  # noqa: E402
from entity_scope import SCOPE_FIELD, SCOPED_COLLECTIONS  # noqa: E402

# Koleksi infrastruktur yang aman dipindahkan otomatis saat entitasnya hilang.
AUTO_REHOME = {"hr_org_units", "rnd_person_divisions"}

report: list = []


def say(line: str) -> None:
    print(line)
    report.append(line)


async def live_entities() -> set:
    return {e["id"] async for e in db.business_entities.find({}, {"_id": 0, "id": 1})}


async def step_transfers(fix: bool) -> int:
    """(1) Backfill `warehouse_transfers.entity_id`."""
    say("\n── 1) warehouse_transfers.entity_id (L14)")
    q = {"$or": [{"entity_id": {"$exists": False}}, {"entity_id": None}, {"entity_id": ""}]}
    rows = await db.warehouse_transfers.find(q, {"_id": 0}).to_list(5000)
    if not rows:
        say("   nihil — semua transfer sudah ber-entitas.")
        return 0
    changed = 0
    for t in rows:
        src = t.get("source_entity_id") or t.get("dest_entity_id")
        if not src:
            # transfer intra lama: turunkan dari gudang/roll pertama
            item = (t.get("items") or [{}])[0]
            src = item.get("owner_entity_id") or ""
        if not src:
            say(f"   ! {t.get('code') or t.get('id')} — tidak bisa disimpulkan, DILEWATI")
            continue
        say(f"   {t.get('code') or t.get('id')}: entity_id → {src}"
            f"  (kind={t.get('transfer_kind', 'intra_entity')})")
        if fix:
            await db.warehouse_transfers.update_one({"id": t["id"]},
                                                    {"$set": {"entity_id": src}})
        changed += 1
    return changed


async def step_notifications(fix: bool) -> int:
    """(2) Backfill `notifications.entity_id` dari dokumen acuan."""
    say("\n── 2) notifications.entity_id (L1)")
    ref_coll = {
        "po_appr": "purchase_orders", "po": "purchase_orders",
        "so": "sales_orders", "so_appr": "sales_orders",
        "pr": "purchase_requisitions", "ar": "ar_receipts",
        "pen": "penalties", "plan": "payment_plans",
        "ic": "interco_transactions", "trf": "warehouse_transfers",
    }
    q = {"$or": [{"entity_id": {"$exists": False}}, {"entity_id": None}, {"entity_id": ""}]}
    rows = await db.notifications.find(q, {"_id": 0}).to_list(5000)
    changed = 0
    for n in rows:
        ref = str(n.get("ref") or "")
        if ":" not in ref:
            continue
        prefix, doc_id = ref.split(":", 1)
        coll = ref_coll.get(prefix)
        if not coll:
            continue
        doc = await db[coll].find_one({"id": doc_id}, {"_id": 0, "entity_id": 1})
        ent = (doc or {}).get("entity_id")
        if not ent:
            continue
        say(f"   {n.get('id')} ({n.get('notif_type', '')}) → {ent}")
        if fix:
            await db.notifications.update_one({"id": n["id"]}, {"$set": {"entity_id": ent}})
        changed += 1
    say(f"   {len(rows) - changed} notifikasi tetap GLOBAL (tanpa entitas) — itu benar "
        f"untuk notifikasi sistem.")
    return changed


async def step_sales_stamps(fix: bool) -> int:
    """(3) Selaraskan stempel entitas target & insentif sales."""
    say("\n── 3) sales_targets / sales_incentives (L12)")
    users = {u["id"]: u async for u in db.users.find(
        {}, {"_id": 0, "id": 1, "email": 1, "name": 1, "home_entity_id": 1})}
    changed = 0
    for coll in ("sales_targets", "sales_incentives"):
        async for d in db[coll].find({}, {"_id": 0}):
            owner = users.get(d.get("sales_id"))
            if not owner or not owner.get("home_entity_id"):
                continue
            if d.get("entity_id") == owner["home_entity_id"]:
                continue
            say(f"   {coll}/{d.get('id')} ({owner.get('email')}): "
                f"{d.get('entity_id')} → {owner['home_entity_id']}")
            if fix:
                await db[coll].update_one(
                    {"id": d["id"]}, {"$set": {"entity_id": owner["home_entity_id"]}})
            changed += 1
    if not changed:
        say("   nihil — semua stempel sudah benar.")
    return changed


async def step_orphans(fix: bool) -> int:
    """(4) Laporan (+ opsi rapikan) dokumen ber-entitas yatim."""
    say("\n── 4) dokumen ber-entitas YATIM (L11)")
    live = await live_entities()
    fallback = ""
    admin = await db.users.find_one({"role": "admin", "status": "active"},
                                    {"_id": 0, "home_entity_id": 1})
    fallback = (admin or {}).get("home_entity_id") or (sorted(live)[0] if live else "")
    total = 0
    colls = sorted(set(SCOPED_COLLECTIONS) | set(SCOPE_FIELD))
    existing = set(await db.list_collection_names())
    for coll in colls:
        if coll not in existing:
            continue
        fld = SCOPE_FIELD.get(coll, "entity_id")
        if fld is None:
            continue
        bad = []
        async for d in db[coll].find({}, {"_id": 0, "id": 1, fld: 1}):
            ent = d.get(fld)
            if ent and ent != "all" and ent not in live:
                bad.append((d.get("id"), ent))
        if not bad:
            continue
        total += len(bad)
        say(f"   {coll}: {len(bad)} baris yatim → {sorted({e for _, e in bad})}")
        if fix and coll in AUTO_REHOME and fallback:
            ids = [i for i, _ in bad]
            await db[coll].update_many({"id": {"$in": ids}}, {"$set": {fld: fallback}})
            say(f"     dipindahkan ke {fallback} (koleksi infrastruktur)")
        elif fix:
            say("     TIDAK diubah otomatis — koleksi transaksional butuh keputusan manusia.")
    if not total:
        say("   nihil — tidak ada dokumen menunjuk entitas yang sudah hilang.")
    return total


async def step_rfid(fix: bool) -> int:
    """(5) Backfill `rfid_reads.owner_entity_id` / `rfid_tags.owner_entity_id` dari roll."""
    say("\n── 5) rfid_tags / rfid_reads .owner_entity_id (L15)")
    changed = 0
    rolls = {r["id"]: r.get("owner_entity_id") async for r in db.inventory_rolls.find(
        {}, {"_id": 0, "id": 1, "owner_entity_id": 1})}
    tags = {t["id"]: t.get("owner_entity_id") async for t in db.rfid_tags.find(
        {}, {"_id": 0, "id": 1, "owner_entity_id": 1})}
    for coll in ("rfid_tags", "rfid_reads"):
        q = {"$or": [{"owner_entity_id": {"$exists": False}}, {"owner_entity_id": None},
                     {"owner_entity_id": ""}]}
        rows = await db[coll].find(q, {"_id": 0}).to_list(20000)
        if not rows:
            say(f"   {coll}: nihil — sudah ber-entitas.")
            continue
        for d in rows:
            ent = rolls.get(d.get("roll_id")) or tags.get(d.get("tag_id"))
            if not ent:
                continue
            if fix:
                await db[coll].update_one({"id": d["id"]},
                                          {"$set": {"owner_entity_id": ent}})
            changed += 1
        say(f"   {coll}: {changed} baris di-stempel dari kepemilikan roll/tag "
            f"({len(rows)} kandidat)")
    return changed


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="terapkan perubahan (default: dry-run)")
    args = ap.parse_args()
    mode = "TERAPKAN" if args.fix else "DRY-RUN (tidak ada yang diubah)"
    say("=" * 76)
    say(f"  MIGRASI REFERENSI ENTITAS — FASE E-0  ·  mode: {mode}")
    say(f"  DB: {os.environ.get('DB_NAME', 'test_database')}")
    say("=" * 76)
    n1 = await step_transfers(args.fix)
    n2 = await step_notifications(args.fix)
    n3 = await step_sales_stamps(args.fix)
    n4 = await step_orphans(args.fix)
    n5 = await step_rfid(args.fix)
    say("\n" + "=" * 76)
    say(f"  RINGKASAN: transfers={n1} · notifikasi={n2} · stempel sales={n3} · "
        f"yatim={n4} · rfid={n5}")
    if not args.fix and (n1 or n2 or n3 or n5):
        say("  Jalankan ulang dengan --fix untuk menerapkan.")
    say("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
