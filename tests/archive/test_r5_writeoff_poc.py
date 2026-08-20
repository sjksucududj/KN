"""R5.1 — Inventory Write-off GL (scrap & goods) — POC.

Membuktikan:
  1. Scrap roll karantina hasil retur jual → posting JE write-off otomatis:
       Dr 5-9500 Beban Kerugian/Penghapusan Persediaan / Cr 1-1300 Persediaan
     sebesar length_remaining * unit_cost roll.
  2. JE seimbang (Σdebit == Σkredit) & memakai akun yang benar.
  3. Idempotent: post ulang write-off untuk roll yang sama TIDAK membuat JE ganda.
  4. Roll ter-tag writeoff_je_number + writeoff_amount (untuk badge UI).
  5. Setelah scrap, subledger persediaan ↔ GL 1-1300 tetap rekonsiliasi (anti INV-GL-DRIFT):
     GL 1-1300 turun tepat sebesar nilai roll yang di-scrap.

Jalankan: python test_r5_writeoff_poc.py
"""
import asyncio
import os
import sys

import requests
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

API = f"{os.environ.get('R5_BASE', 'http://localhost:8001')}/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
_MC = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DBS = _MC[os.environ.get("DB_NAME", "test_database")]
PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  \u2705 {name}")
    else:
        FAIL += 1
        print(f"  \u274c {name}  {extra}")


def login():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def eligible(h):
    r = requests.get(f"{API}/sales-orders", headers=h, timeout=30)
    o = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    ok = {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
    return [x for x in o if x.get("status") in ok and
            any(float(it.get("quantity", 0) or 0) >= 5 for it in (x.get("items") or []))]


def create(h, orders, q=2):
    for o in orders:
        its = [it for it in o["items"] if float(it.get("quantity", 0) or 0) >= q]
        if not its:
            continue
        it = its[0]
        r = requests.post(f"{API}/sales-returns", headers=h, timeout=30, json={
            "order_id": o["id"], "return_type": "retur",
            "items": [{"product_id": it["product_id"], "product_name": it.get("product_name", ""),
                       "quantity_returned": q, "unit": it.get("unit", "meter"),
                       "reason": "R5", "condition": "ok"}], "notes": "R5.1"})
        if r.status_code == 200:
            return r.json()
    return None


def inspect(h, rid, defects, qty=2):
    requests.post(f"{API}/sales-returns/{rid}/submit", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/approve", headers=h, json={"notes": ""}, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
    return requests.post(f"{API}/sales-returns/{rid}/inspect/complete", headers=h, timeout=30,
                         json={"inspections": [{"index": 0, "defects": defects, "condition": "ok",
                                                "accepted_qty": qty}], "notes": "4point"}).json()


async def _mongo():
    from db import db  # noqa: E402
    return db


def count_writeoff_je(roll_id):
    return DBS.journal_entries.count_documents(
        {"source_type": "inventory_writeoff", "source_id": roll_id, "status": {"$ne": "void"}})


def get_writeoff_je(roll_id):
    return DBS.journal_entries.find_one(
        {"source_type": "inventory_writeoff", "source_id": roll_id, "status": {"$ne": "void"}},
        {"_id": 0})


def gl_1300_for_entity(entity_id):
    total = 0.0
    for je in DBS.journal_entries.find({"entity_id": entity_id, "status": {"$ne": "void"}}, {"_id": 0}):
        for l in je.get("lines", []):
            if l.get("account_code") == "1-1300":
                total += float(l.get("debit", 0) or 0) - float(l.get("credit", 0) or 0)
    return round(total, 2)


def direct_idempotent_repost(roll_id, entity_id, amount):
    """Panggil helper langsung (SATU event loop) utk buktikan idempotensi (harus None)."""
    async def _run():
        from services import gl_service  # noqa: E402
        return await gl_service.post_inventory_writeoff(
            roll_id=roll_id, entity_id=entity_id, amount=amount, reason="idempotency-test")
    return asyncio.run(_run())


def main():
    h = login()
    orders = eligible(h)
    print(f"== R5.1 WRITE-OFF POC == (orders={len(orders)})")
    if not orders:
        check("prasyarat data (orders eligible)", False)
        sys.exit(1)

    whs = requests.get(f"{API}/warehouses", headers=h, timeout=30).json()
    whs = whs if isinstance(whs, list) else whs.get("items", [])
    dest_wh = whs[-1]["id"] if whs else ""

    # Cari retur yang menghasilkan roll karantina dengan unit_cost > 0 (agar write-off bernilai)
    print("\n[1] Buat retur → settle refund → roll karantina (unit_cost > 0)")
    roll = None
    rid = None
    so_entity = None
    for _ in range(len(orders)):
        ret = create(h, orders)
        if not ret:
            continue
        rid = ret["id"]
        inspect(h, rid, [{"point_value": 1, "count": 2}], qty=2)  # grade A → unit_cost = WAC
        s = requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30,
                          json={"outcome": "refund", "return_warehouse_id": dest_wh}).json()
        so_entity = s.get("entity_id")
        q = requests.get(f"{API}/sales-returns/{rid}/quarantine", headers=h, timeout=30).json()
        cand = next((x for x in (q or []) if float(x.get("unit_cost") or 0) > 0), None)
        if cand:
            roll = cand
            break
    check("dapat roll karantina unit_cost>0", bool(roll), "tidak ada roll bernilai (WAC 0?)")
    if not roll:
        print(f"\n=== HASIL R5.1: PASS={PASS} FAIL={FAIL} ===")
        sys.exit(1 if FAIL else 0)

    qty = round(float(roll.get("length_remaining", roll.get("length", 0)) or 0), 2)
    unit_cost = round(float(roll.get("unit_cost") or roll.get("base_unit_cost") or 0), 2)
    expected = round(qty * unit_cost, 2)
    owner = roll.get("owner_entity_id")
    print(f"    roll={roll['id'][:12]} qty={qty} unit_cost={unit_cost} expected_writeoff={expected} owner={owner}")

    gl_before = gl_1300_for_entity(owner)

    # ── 2. Scrap roll → write-off JE otomatis ──
    print("\n[2] Scrap roll karantina → write-off GL otomatis")
    rel = requests.post(f"{API}/sales-returns/{rid}/quarantine/release", headers=h, timeout=30,
                        json={"decisions": [{"roll_id": roll["id"], "action": "scrap"}]})
    check("release/scrap → 200", rel.status_code == 200, f"{rel.status_code} {rel.text[:160]}")
    relj = rel.json() if rel.status_code == 200 else {}
    summ = relj.get("_release_summary", {})
    check("summary scrapped >= 1", summ.get("scrapped", 0) >= 1, str(summ))
    check("summary writeoff_total > 0", float(summ.get("writeoff_total", 0) or 0) > 0, str(summ))

    je = get_writeoff_je(roll["id"])
    check("JE write-off dibuat (source_type=inventory_writeoff)", bool(je), str(je)[:120] if je else "none")
    if je:
        d = round(sum(float(l.get("debit", 0) or 0) for l in je["lines"]), 2)
        c = round(sum(float(l.get("credit", 0) or 0) for l in je["lines"]), 2)
        check("JE seimbang (Dr == Cr)", abs(d - c) < 0.01, f"Dr {d} Cr {c}")
        check("JE amount == qty*unit_cost", abs(d - expected) < 0.5, f"JE {d} vs expected {expected}")
        accs = {l.get("account_code"): l for l in je["lines"]}
        check("Dr 5-9500 (beban write-off)", float(accs.get("5-9500", {}).get("debit", 0) or 0) > 0, str(list(accs)))
        check("Cr 1-1300 (persediaan)", float(accs.get("1-1300", {}).get("credit", 0) or 0) > 0, str(list(accs)))
        check("JE entity = owner roll", je.get("entity_id") == owner, f"{je.get('entity_id')} vs {owner}")

    # ── 3. Roll ter-tag writeoff (untuk UI badge) ──
    print("\n[3] Roll ter-tag writeoff_je_number + writeoff_amount")
    q2 = requests.get(f"{API}/sales-returns/{rid}/quarantine", headers=h, timeout=30).json()
    rr = next((x for x in q2 if x["id"] == roll["id"]), {})
    check("roll status damaged", rr.get("status") == "damaged", str(rr.get("status")))
    check("roll.writeoff_je_number ada", bool(rr.get("writeoff_je_number")), str(rr.get("writeoff_je_number")))
    check("roll.writeoff_amount == expected", abs(float(rr.get("writeoff_amount", 0) or 0) - expected) < 0.5,
          str(rr.get("writeoff_amount")))

    # ── 4. Idempotensi: post ulang tidak buat JE ganda ──
    print("\n[4] Idempotensi write-off (repost → None, count tetap 1)")
    cnt1 = count_writeoff_je(roll["id"])
    dup = direct_idempotent_repost(roll["id"], owner, expected)
    cnt2 = count_writeoff_je(roll["id"])
    check("repost helper → None (idempotent)", dup is None, str(dup)[:80])
    check("jumlah JE tetap 1", cnt1 == 1 and cnt2 == 1, f"cnt1={cnt1} cnt2={cnt2}")

    # ── 5. GL 1-1300 turun tepat sebesar nilai roll (anti-drift) ──
    print("\n[5] GL 1-1300 turun == nilai roll (anti INV-GL-DRIFT)")
    gl_after = gl_1300_for_entity(owner)
    delta = round(gl_before - gl_after, 2)
    check("penurunan GL 1-1300 == expected write-off", abs(delta - expected) < 0.5,
          f"before={gl_before} after={gl_after} delta={delta} expected={expected}")

    print(f"\n=== HASIL R5.1: PASS={PASS}  FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
