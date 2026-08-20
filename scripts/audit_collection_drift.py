#!/usr/bin/env python3
"""
audit_collection_drift.py — KN3 collection-drift scanner (read-only)
====================================================================
Untuk setiap referensi db.<koleksi> / db["<koleksi>"] yang DIBACA di
routers+services, tandai koleksi yang KOSONG/HILANG di DB live
(potensi RC-1 drift / dead read).

Usage: cd /app && python scripts/audit_collection_drift.py
"""
import asyncio
import os
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass
from motor.motor_asyncio import AsyncIOMotorClient

BACKEND = ROOT / "backend"
DB_NAME = os.environ.get("DB_NAME", "kain_nusantara")
db = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[DB_NAME]
G, Y, R, X = "\033[92m", "\033[93m", "\033[91m", "\033[0m"

# Tangkap KEDUA bentuk: db.coll.OP  dan  db["coll"].OP
PAT = re.compile(
    r'''db(?:\.([a-z][a-z0-9_]*)|\[\s*['\"]([a-z][a-z0-9_]*)['\"]\s*\])\s*\.\s*'''
    r'''(find|find_one|aggregate|count_documents|distinct|update_one|update_many|'''
    r'''insert_one|insert_many|delete_one|delete_many|find_one_and_update)'''
)
IGNORE = {"command", "client", "name"}
READ_OPS = {"find", "find_one", "aggregate", "count_documents", "distinct"}


async def main():
    live = {c: await db[c].count_documents({}) for c in await db.list_collection_names()}
    refs = defaultdict(lambda: defaultdict(set))
    for py in list((BACKEND / "services").rglob("*.py")) + list((BACKEND / "routers").rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        for i, line in enumerate(py.read_text(errors="ignore").splitlines(), 1):
            for m in PAT.finditer(line):
                coll = m.group(1) or m.group(2)
                op = m.group(3)
                if coll in IGNORE:
                    continue
                refs[coll][op].add(f"{py.relative_to(BACKEND)}:{i}")

    print("=== KOLEKSI DIBACA DI KODE TAPI KOSONG/HILANG DI DB ===")
    print("(read op pada koleksi kosong = mungkin drift atau fitur mati)\n")
    suspects = 0
    for coll in sorted(refs):
        n = live.get(coll)
        has_read = any(op in READ_OPS for op in refs[coll])
        has_write = any(op in {"insert_one", "insert_many"} for op in refs[coll])
        if (n is None or n == 0) and has_read:
            suspects += 1
            tag = "MISSING" if n is None else "EMPTY"
            readers = sorted({r for op in READ_OPS for r in refs[coll].get(op, [])})
            print(f"  {Y}[{tag}]{X} db.{coll}  (ditulis_kode={has_write})")
            for r in readers[:5]:
                print(f"        read @ {r}")
    if not suspects:
        print(f"  {G}none — semua koleksi yang dibaca berisi data.{X}")


if __name__ == "__main__":
    asyncio.run(main())
