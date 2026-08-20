#!/usr/bin/env python3
"""FASE E-2 (E2.6) — RAPIKAN TAUTAN KARYAWAN HR ↔ AKUN.

Tiga jenis kotoran yang dibersihkan (semuanya IDEMPOTEN, dan `--dry-run` dulu):

1. **Karyawan yatim** — `hr_employees.user_id` menunjuk akun yang sudah tidak ada
   (akun dihapus keras di masa lalu). Tautannya dikosongkan supaya karyawan itu
   bisa dipasangkan ke akun baru.
2. **Badan usaha tidak sinkron** — `users.home_entity_id` ≠ `hr_employees.entity_id`
   untuk pasangan yang tertaut. Sejak E2.1 **HR yang menang**, jadi akun
   diselaraskan ke badan usaha karyawannya (dan sesinya dicabut supaya wewenang
   lama tidak terbawa).
3. **`users.employee_id` hilang** — tautan hanya ada di sisi HR. Diisi balik supaya
   kedua arah konsisten (dipakai layar Akun & Akses).

Pakai:
    python /app/scripts/fix_orphan_employees.py --dry-run
    python /app/scripts/fix_orphan_employees.py --apply
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


async def main(apply: bool) -> int:
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "test_database")]

    users = {u["id"]: u async for u in db.users.find(
        {}, {"_id": 0, "id": 1, "name": 1, "home_entity_id": 1, "employee_id": 1,
             "status": 1})}
    ents = {e["id"]: (e.get("legal_name") or e.get("short_name") or e["id"])
            async for e in db.business_entities.find({}, {"_id": 0, "id": 1,
                                                          "legal_name": 1, "short_name": 1})}

    orphans, mismatched, missing_link = [], [], []
    async for emp in db.hr_employees.find({}, {"_id": 0, "id": 1, "name": 1, "code": 1,
                                               "user_id": 1, "entity_id": 1}):
        uid = emp.get("user_id") or ""
        if not uid:
            continue
        user = users.get(uid)
        if not user:
            orphans.append(emp)
            continue
        if emp.get("entity_id") and user.get("home_entity_id") != emp["entity_id"]:
            mismatched.append((emp, user))
        if user.get("employee_id") != emp["id"]:
            missing_link.append((emp, user))

    print("=" * 74)
    print("  RAPIKAN TAUTAN KARYAWAN HR ↔ AKUN (FASE E-2 / E2.6)")
    print("=" * 74)
    print(f"\n[1] Karyawan yatim (akun sudah tidak ada): {len(orphans)}")
    for e in orphans[:20]:
        print(f"    • {e.get('code', '')} {e.get('name', '')} → user_id={e.get('user_id')}")
    print(f"\n[2] Badan usaha akun ≠ HR: {len(mismatched)}")
    for e, u in mismatched[:20]:
        print(f"    • {u.get('name', '')}: akun={ents.get(u.get('home_entity_id'), u.get('home_entity_id'))}"
              f" · HR={ents.get(e.get('entity_id'), e.get('entity_id'))}")
    print(f"\n[3] users.employee_id belum terisi: {len(missing_link)}")
    for e, u in missing_link[:20]:
        print(f"    • {u.get('name', '')} → {e.get('code', '')} {e.get('name', '')}")

    total = len(orphans) + len(mismatched) + len(missing_link)
    if not apply:
        print(f"\nMODE PRATINJAU — {total} temuan. Jalankan dengan --apply untuk merapikan.")
        return 0
    if total == 0:
        print("\nNihil — tidak ada yang perlu dirapikan.")
        return 0

    for e in orphans:
        await db.hr_employees.update_one({"id": e["id"]}, {"$set": {"user_id": ""}})
    revoked = 0
    for e, u in mismatched:
        await db.users.update_one({"id": u["id"]},
                                  {"$set": {"home_entity_id": e["entity_id"]}})
        # Sesi dicabut: daftar badan usaha di sesi lama sudah tidak berlaku.
        res = await db.sessions.delete_many({"user_id": u["id"]})
        revoked += res.deleted_count
    for e, u in missing_link:
        await db.users.update_one({"id": u["id"]}, {"$set": {"employee_id": e["id"]}})

    print(f"\nSELESAI — {len(orphans)} tautan yatim dikosongkan · "
          f"{len(mismatched)} akun diselaraskan ke HR ({revoked} sesi dicabut) · "
          f"{len(missing_link)} employee_id diisi balik.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="benar-benar menulis perubahan")
    ap.add_argument("--dry-run", action="store_true", help="hanya melaporkan (bawaan)")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(apply=args.apply)))
