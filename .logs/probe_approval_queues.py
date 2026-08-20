#!/usr/bin/env python3
"""PROBE (read-only) — antrean "menunggu keputusan orang" yang ADA di basis data
tetapi TIDAK terdaftar di `services/approval_backlog_service.QUEUES`.

Dipakai untuk MEMILIH fase berikutnya dengan bukti, bukan tebakan.
"""
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass

from pymongo import MongoClient  # noqa: E402

WAIT = {"waiting_approval", "pending_approval", "submitted", "review", "pending",
        "awaiting_approval", "pending_review", "waiting_review", "requested",
        "menunggu_persetujuan", "need_approval", "for_approval"}

db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)[
    os.environ.get("DB_NAME", "test_database")]

# koleksi yang SUDAH terdaftar
src = (ROOT / "backend/services/approval_backlog_service.py").read_text(encoding="utf-8")
registered = set(re.findall(r'"([a-z_]+)",?\s*$|"([a-z_]+)",\s*\n?\s*#?', ""))  # noqa
block = src.split("QUEUES: List[tuple] = [", 1)[1].split("\n]", 1)[0]
registered = set(re.findall(r'"(?:approval-inbox|[\w-]+)",\s*\n?\s*#?[^"]*"([a-z_]+)"', block))
# lebih andal: ambil semua string, cocokkan dengan nama koleksi nyata
all_strings = set(re.findall(r'"([a-z_]+)"', block))
existing = set(db.list_collection_names())
registered = all_strings & existing

print(f"Koleksi terdaftar di QUEUES ({len(registered)}): {sorted(registered)}\n")

found = defaultdict(dict)
for c in sorted(existing):
    try:
        vals = db[c].distinct("status")
    except Exception:
        continue
    for v in vals:
        if isinstance(v, str) and v.lower() in WAIT:
            n = db[c].count_documents({"status": v})
            if n:
                found[c][v] = n

print("=== KOLEKSI DENGAN DOKUMEN BERSTATUS 'MENUNGGU KEPUTUSAN' ===")
gap_total = 0
for c, sv in sorted(found.items(), key=lambda kv: -sum(kv[1].values())):
    tag = "TERDAFTAR" if c in registered else "!! TIDAK TERDAFTAR !!"
    if c not in registered:
        gap_total += sum(sv.values())
    print(f"  {c:32s} {sv}  [{tag}]")

print(f"\nTotal dokumen menunggu di koleksi TIDAK TERDAFTAR: {gap_total}")

# apakah ada yang memakai approval_requests?
print(f"\napproval_requests count      : {db.approval_requests.count_documents({})}")
print(f"approval_rules count         : {db.approval_rules.count_documents({})}")
for r in db.approval_rules.find({}, {"_id": 0, "name": 1, "entity_type": 1,
                                     "threshold_field": 1, "threshold_value": 1,
                                     "approver_role": 1, "is_active": 1}):
    print("   rule:", r)
