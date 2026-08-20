#!/usr/bin/env python3
"""MIGRASI — nomor roll memakai nama kanonik `roll_no` (KN-ROLL-NO-DRIFT)

MASALAH YANG DIPERBAIKI
-----------------------
Enam dari tujuh pembuat roll menulis nomor roll ke field **`roll_no`** — nama yang
dipakai SEMUA konsumennya: Daftar Roll, Buku Besar Persediaan, pencarian
(`build_search(["roll_no", …])`), ekspor CSV, label cetak, pegging, dan potong-roll.
Satu pembuat, `services/return_service.py` (roll hasil retur pelanggan yang masuk
karantina), menulis ke **`roll_number`** — nama yang hanya hidup di berkas itu.

Akibatnya roll hasil retur tampil **tanpa nomor** di layar & CSV, tidak bisa dicari,
dan tidak bisa dicocokkan dengan kain fisik di rak. Terukur pada data demo:
**1 dari 59 roll** kosong nomor + kosong satuan (`unit` juga tak pernah diisi baris
itu). Sesi sebelumnya mencatatnya sebagai "cacat data demo, bukan bug kode" —
padahal roll itu dibuat oleh **alur HTTP nyata** (retur pelanggan → karantina),
jadi setiap retur di produksi menghasilkan roll tanpa nomor.

Kenapa drift ini bisa bertahan lama: field yang salah nama **punya pembacanya
sendiri**. `ReturnQuarantinePanel.jsx` membaca `r.roll_number`, dan dua service
(`interco_return_service`, `return_chain_service`) menulis `roll_no or roll_number`
sebagai kompensasi. Jadi satu layar tampak benar sementara layar lain kosong —
tidak ada error, tidak ada uji yang gagal.

APA YANG DILAKUKAN SKRIP INI
----------------------------
1. `roll_number` → `roll_no` (bila `roll_no` belum ada/kosong), dengan **penomoran
   ulang** ke `RTN-NNNNN` lewat sequence bersama. Nilai lama seperti
   `RTN-00003-ntai` sengaja tidak dipertahankan: akhiran "ntai" adalah 4 huruf
   terakhir `prod_e9_demo_rantai` (potongan id produk) — bukan nomor yang bisa
   dicari orang, dan bisa bertabrakan antar produk yang 4 huruf terakhirnya sama.
2. `unit` yang kosong diisi dari `products.base_unit` (fallback `meter`).
3. Field `roll_number` dihapus supaya tidak ada dua sumber kebenaran.
4. **Nomor KEMBAR dipisah.** Tiga cara penomoran lama bisa memberi nomor yang sama
   ke kain yang berbeda (rincian di `services/roll_service.py` §INV-ROLL-01).
   Terukur: **3 nomor dipakai 10 roll**, termasuk `RL-00002` yang dipegang DUA badan
   usaha (KSC 140 yard & Kanda 7 yard) dan `RL-00042` yang dipakai 4 roll. Yang
   TERTUA mempertahankan nomornya; sisanya menjadi `RL-00002-1`, `-2`, … (pola
   potongan roll) sehingga asal-usulnya tetap terbaca di label.

Sifatnya **idempotent** (roll yang sudah bersih dilewati) dan punya **--dry-run**.

    python scripts/migrate_roll_no_canonical.py --dry-run
    python scripts/migrate_roll_no_canonical.py
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

G, Y, R, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[1m", "\033[0m"

MISSING = [None, ""]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="hanya laporkan, jangan tulis apa pun")
    args = ap.parse_args()

    from db import db  # noqa: PLC0415

    print(f"{B}MIGRASI nomor roll → `roll_no` kanonik (KN-ROLL-NO-DRIFT){X}")

    # Roll yang nomornya belum kanonik ATAU satuannya kosong.
    q = {"$or": [{"roll_no": {"$in": MISSING}}, {"roll_no": {"$exists": False}},
                 {"roll_number": {"$exists": True}},
                 {"unit": {"$in": MISSING}}, {"unit": {"$exists": False}}]}
    rolls = await db.inventory_rolls.find(
        q, {"_id": 0, "id": 1, "roll_no": 1, "roll_number": 1, "unit": 1,
            "product_id": 1, "origin_type": 1}).to_list(100000)
    total = await db.inventory_rolls.count_documents({})
    print(f"  roll total: {total}  ·  perlu diperiksa: {len(rolls)}")
    if not rolls:
        print(f"{G}  Nomor & satuan: sudah bersih.{X}")
        return await split_duplicates(db, args.dry_run)

    # Nomor RTN- tertinggi yang sudah kanonik → titik mulai penomoran ulang.
    pat = re.compile(r"^RTN-(\d+)$")
    top = 0
    async for d in db.inventory_rolls.find({"roll_no": {"$regex": r"^RTN-\d+$"}},
                                           {"_id": 0, "roll_no": 1}):
        m = pat.match(str(d.get("roll_no") or ""))
        if m:
            top = max(top, int(m.group(1)))

    base_units = {p["id"]: (p.get("base_unit") or "meter") for p in
                  await db.products.find({}, {"_id": 0, "id": 1, "base_unit": 1}).to_list(100000)}

    plan = []
    for r in rolls:
        sets, unsets = {}, {}
        if (r.get("roll_no") or "") in MISSING:
            top += 1
            sets["roll_no"] = f"RTN-{top:05d}"
        if "roll_number" in r:
            unsets["roll_number"] = ""
        if (r.get("unit") or "") in MISSING:
            sets["unit"] = base_units.get(r.get("product_id", ""), "meter")
        if sets or unsets:
            plan.append((r["id"], r.get("roll_number") or "—", sets, unsets))

    if not plan:
        print(f"{G}  Nomor & satuan: sudah bersih.{X}")
        return await split_duplicates(db, args.dry_run)

    for rid, old, sets, unsets in plan[:20]:
        print(f"    · {rid}  lama roll_number={old!r}  →  "
              + ", ".join(f"{k}={v!r}" for k, v in sets.items())
              + (f"  (hapus: {', '.join(unsets)})" if unsets else ""))
    if len(plan) > 20:
        print(f"    … dan {len(plan) - 20} lagi")

    if args.dry_run:
        print(f"{Y}  --dry-run: tidak ada yang ditulis.{X}")
        return await split_duplicates(db, True)

    changed = 0
    for rid, _old, sets, unsets in plan:
        upd: dict = {}
        if sets:
            upd["$set"] = sets
        if unsets:
            upd["$unset"] = unsets
        res = await db.inventory_rolls.update_one({"id": rid}, upd)
        changed += res.modified_count

    left = await db.inventory_rolls.count_documents(
        {"$or": [{"roll_no": {"$in": MISSING}}, {"roll_no": {"$exists": False}},
                 {"roll_number": {"$exists": True}},
                 {"unit": {"$in": MISSING}}, {"unit": {"$exists": False}}]})
    print(f"{G}  Selesai: {changed} roll diperbarui · sisa belum kanonik: {left}{X}")
    rc_dup = await split_duplicates(db, False)
    return 0 if (left == 0 and rc_dup == 0) else 1


async def split_duplicates(db, dry_run: bool) -> int:
    """Nomor kembar → yang TERTUA memegang nomornya, sisanya jadi `<nomor>-N`."""
    groups = await db.inventory_rolls.aggregate([
        {"$group": {"_id": "$roll_no", "ids": {"$push": "$id"}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}}]).to_list(10000)
    if not groups:
        print(f"{G}  Nomor kembar: 0 — setiap nomor menunjuk satu roll.{X}")
        return 0
    total = sum(g["n"] - 1 for g in groups)
    print(f"{Y}  Nomor kembar: {len(groups)} nomor dipakai "
          f"{sum(g['n'] for g in groups)} roll → {total} roll perlu nomor sendiri{X}")

    renamed = 0
    for g in sorted(groups, key=lambda x: str(x["_id"])):
        base = str(g["_id"] or "")
        docs = await db.inventory_rolls.find(
            {"id": {"$in": g["ids"]}},
            {"_id": 0, "id": 1, "created_at": 1, "owner_entity_id": 1,
             "length_remaining": 1, "status": 1}).to_list(1000)
        # Tertua (created_at, lalu id) memegang nomor aslinya.
        docs.sort(key=lambda d: (str(d.get("created_at") or ""), str(d.get("id"))))
        keep, rest = docs[0], docs[1:]
        print(f"    · {base}: {keep['id']} MEMPERTAHANKAN nomor · "
              f"{len(rest)} roll dinomori ulang")
        n = await db.inventory_rolls.count_documents(
            {"roll_no": {"$regex": f"^{re.escape(base)}-[0-9]+$"}})
        for d in rest:
            while True:
                n += 1
                cand = f"{base}-{n}"
                if not await db.inventory_rolls.find_one({"roll_no": cand}, {"_id": 1}):
                    break
            print(f"        {d['id']}  ({d.get('owner_entity_id','?')} · "
                  f"{d.get('status','?')} · {d.get('length_remaining',0)}) → {cand}")
            if not dry_run:
                await db.inventory_rolls.update_one({"id": d["id"]}, {"$set": {"roll_no": cand}})
                renamed += 1
    if dry_run:
        print(f"{Y}  --dry-run: nomor kembar TIDAK diubah.{X}")
        return 0
    dup_left = await db.inventory_rolls.aggregate([
        {"$group": {"_id": "$roll_no", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}}]).to_list(10)
    print(f"{G}  {renamed} roll dinomori ulang · nomor kembar sisa: {len(dup_left)}{X}")
    return 0 if not dup_left else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
