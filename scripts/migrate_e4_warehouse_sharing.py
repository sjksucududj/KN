#!/usr/bin/env python3
"""MIGRASI FASE E-4 (E4.1) — mode pemakaian gudang (bersama / khusus badan usaha).

IDEMPOTEN: aman dijalankan berulang. Tidak pernah memindahkan stok.

Keputusan pemilik (2026-08-10, opsi **a** setelah benturan data ditunjukkan):
  - `wh_jakarta`  → **bersama** (berisi roll KSC *dan* 1 roll Kanda)
  - `wh_surabaya` → **bersama** (berisi 20 roll KSC; menjadikannya khusus Kanda
                    akan MENGURUNG stok KSC → ditolak pemilik)
  - `wh_bandung`  → **khusus PT Kain Suka Cita** (13 roll di dalamnya memang
                    seluruhnya milik KSC, jadi konsisten & membuktikan penyaringan)
  - gudang BARU `wh_tangerang` → **khusus CV Kanda Suka** (kosong, siap dipakai)

Gudang lain (buatan pengguna) hanya diberi nilai bawaan **bersama** bila field-nya
belum ada — supaya tidak ada gudang tanpa aturan, dan tidak ada stok terkurung.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

DEMO_PLAN = {
    "wh_jakarta": ("shared", []),
    "wh_surabaya": ("shared", []),
    "wh_bandung": ("dedicated", ["ent_ksc"]),
}

TANGERANG = {
    "id": "wh_tangerang",
    "code": "WH-TGR",
    "name": "Gudang Tangerang Cikupa",
    "city": "Tangerang",
    "lat": -6.2088,
    "lng": 106.5306,
    "sharing_mode": "dedicated",
    "entity_ids": ["ent_kanda"],
    "active": True,
    "zones": [{
        "id": "zone_tgr_a", "name": "Zone A",
        "racks": [{"id": "rack_tgr_a1", "name": "Rack A1", "bins": [
            {"id": "bin_tgr_a1_01", "code": "A1-01", "capacity": 500},
            {"id": "bin_tgr_a1_02", "code": "A1-02", "capacity": 500},
        ]}],
    }],
}


async def main() -> int:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    changed = 0

    ent_ids = {e["id"] for e in await db.business_entities.find({}, {"_id": 0, "id": 1}).to_list(200)}

    # 1. Gudang demo sesuai keputusan pemilik.
    for wid, (mode, ents) in DEMO_PLAN.items():
        wh = await db.warehouses.find_one({"id": wid}, {"_id": 0})
        if not wh:
            continue
        ents = [e for e in ents if e in ent_ids]
        if mode == "dedicated" and not ents:
            print(f"  ! {wid}: badan usaha target tidak ada → dilewati (tetap bersama)")
            mode, ents = "shared", []
        if wh.get("sharing_mode") == mode and (wh.get("entity_ids") or []) == ents:
            print(f"  = {wid}: sudah {mode} {ents or ''}".rstrip())
            continue
        await db.warehouses.update_one({"id": wid},
                                       {"$set": {"sharing_mode": mode, "entity_ids": ents}})
        changed += 1
        print(f"  → {wid}: {mode} {ents or ''}".rstrip())

    # 2. Gudang khusus CV Kanda Suka (baru, kosong).
    if "ent_kanda" in ent_ids:
        exists = await db.warehouses.find_one({"id": TANGERANG["id"]}, {"_id": 0})
        if not exists:
            from datetime import datetime, timezone
            doc = dict(TANGERANG)
            doc["created_at"] = datetime.now(timezone.utc).isoformat()
            await db.warehouses.insert_one(doc)
            changed += 1
            print(f"  + {TANGERANG['id']}: dibuat (khusus CV Kanda Suka)")
        else:
            await db.warehouses.update_one(
                {"id": TANGERANG["id"]},
                {"$set": {"sharing_mode": "dedicated", "entity_ids": ["ent_kanda"]}})
            print(f"  = {TANGERANG['id']}: sudah ada")

    # 3. Sisa gudang tanpa aturan → bersama (jangan mengurung stok siapa pun).
    res = await db.warehouses.update_many(
        {"sharing_mode": {"$exists": False}},
        {"$set": {"sharing_mode": "shared", "entity_ids": []}})
    if res.modified_count:
        changed += res.modified_count
        print(f"  → {res.modified_count} gudang lain diberi bawaan 'bersama'")

    print("\n  Ringkasan gudang:")
    for wh in await db.warehouses.find({}, {"_id": 0}).sort("code", 1).to_list(200):
        print(f"    {wh.get('code'):9} {wh.get('name'):28} "
              f"{wh.get('sharing_mode'):10} {wh.get('entity_ids') or ''}")
    print(f"\n  MIGRASI SELESAI · {changed} perubahan")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
