#!/usr/bin/env python3
"""
POC ISOLASI — P0-3: Faktur Pajak Masukan (Input VAT) — Phase 5.5
================================================================
Membuktikan core SEBELUM frontend:

  A. Eligible bills: Vendor Bill ber-PPN (posted) muncul sebagai eligible.
  B. Create dari bill → status recorded; DPP/PPN/supplier disalin dari bill; period benar.
  C. Bill ter-flag → tidak lagi eligible; create kedua utk bill sama → 409.
  D. NSFP dedupe → NSFP sama pada bill lain → 409.
  E. Rekap PPN: vat-summary periode → Masukan vs Keluaran + net kurang/lebih bayar.
  F. Cancel → status cancelled; bill eligible lagi; NSFP bisa dipakai ulang.

Isolated: fixtures (vendor_bill posted + tax_invoice keluaran) di-seed via motor,
eksekusi via HTTP API NYATA, assert via DB + cross-endpoint. Idempotent (cleanup awal).
"""
import asyncio
import os
import sys
import requests
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE = os.environ.get("BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
ENTITY = "ent_ksc"

MARK = "ITPOC"
PERIOD = "2099-01"               # periode terisolasi (hindari tabrakan faktur seed)
PDATE = f"{PERIOD}-15T00:00:00+00:00"
NSFP = "0100123456789012"        # 16-digit
NSFP2 = "0100999888777666"

PASS, FAIL = [], []
def ok(m): PASS.append(m); print(f"  \u2705 [PASS] {m}")
def bad(m): FAIL.append(m); print(f"  \u274c [FAIL] {m}")
def info(m): print(f"  \u2139  {m}")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "demo12345"}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


async def cleanup(db):
    await db.vendor_bills.delete_many({"mark": MARK})
    await db.tax_invoices_in.delete_many({"$or": [{"mark": MARK}, {"nsfp_digits": {"$in": [NSFP, NSFP2]}}]})
    await db.tax_invoices.delete_many({"mark": MARK})


async def seed_bill(db, suffix, ppn, dpp):
    bid = f"vbill_{MARK.lower()}_{suffix}"
    await db.vendor_bills.delete_many({"id": bid})
    await db.vendor_bills.insert_one({
        "id": bid, "mark": MARK, "bill_number": f"VB-{MARK}-{suffix}",
        "supplier_invoice_no": f"INV-{suffix}", "po_id": f"po_{MARK.lower()}", "po_number": f"PO-{MARK}",
        "supplier_id": "sup_itpoc", "supplier_name": "Supplier Pajak POC", "supplier_npwp": "01.234.567.8-901.000",
        "entity_id": ENTITY, "bill_date": PDATE, "status": "posted",
        "dpp": dpp, "ppn_rate": 11.0, "ppn_mode": "excluded", "ppn_amount": ppn,
        "grand_total": round(dpp + ppn, 2), "input_faktur_status": "none",
        "created_at": now_iso(), "updated_at": now_iso()})
    return bid


async def seed_output_faktur(db, ppn, dpp):
    fid = f"fkt_{MARK.lower()}_1"
    await db.tax_invoices.delete_many({"id": fid})
    await db.tax_invoices.insert_one({
        "id": fid, "mark": MARK, "number": f"FKT-{MARK}", "status": "normal",
        "entity_id": ENTITY, "faktur_date": PDATE, "order_id": "so_itpoc",
        "dpp": dpp, "ppn_rate": 11.0, "ppn_amount": ppn, "grand_total": round(dpp + ppn, 2),
        "created_at": now_iso(), "updated_at": now_iso()})
    return fid


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {login('admin@kainnusantara.id')}"})
    ok("Login admin")

    await cleanup(db)
    bill1 = await seed_bill(db, "1", ppn=110000.0, dpp=1000000.0)
    await seed_output_faktur(db, ppn=200000.0, dpp=1818181.0)

    # ── A. Eligible bills ─────────────────────────────────────────────────
    info("TEST A: Eligible bills (bill posted ber-PPN muncul)")
    ra = s.get(f"{API}/input-tax-invoices/eligible-bills", params={"entity_id": ENTITY}, timeout=30)
    if ra.status_code == 200 and any(b["vendor_bill_id"] == bill1 for b in ra.json()):
        ok("Bill posted ber-PPN muncul di eligible-bills")
    else:
        bad(f"eligible-bills tak memuat bill: {ra.status_code} {ra.text[:150]}")

    # ── B. Create dari bill ───────────────────────────────────────────────
    info("TEST B: Catat Faktur Masukan dari bill (DPP/PPN disalin)")
    rb = s.post(f"{API}/input-tax-invoices",
                json={"vendor_bill_id": bill1, "nsfp": NSFP, "faktur_date": PDATE}, timeout=30)
    if rb.status_code != 200:
        bad(f"create gagal: {rb.status_code} {rb.text[:250]}")
        await _finish(client); return
    v = rb.json()
    fpm_id = v["id"]
    checks = [
        (v.get("status") == "recorded", "status recorded"),
        (abs(float(v.get("ppn_amount", 0)) - 110000) < 1, "ppn_amount disalin 110.000"),
        (abs(float(v.get("dpp", 0)) - 1000000) < 1, "dpp disalin 1.000.000"),
        (v.get("supplier_name") == "Supplier Pajak POC", "supplier disalin"),
        (v.get("period") == PERIOD, f"period {PERIOD}"),
        (v.get("nsfp_digits") == NSFP, "nsfp_digits ternormalisasi"),
        (v.get("number", "").startswith("FPM-"), "nomor internal FPM-"),
    ]
    for cond, label in checks:
        ok(label) if cond else bad(f"{label} — dapat {v.get('status')}/{v.get('ppn_amount')}/{v.get('dpp')}/{v.get('period')}")

    # bill ter-flag di DB
    b = await db.vendor_bills.find_one({"id": bill1}, {"_id": 0})
    if b and b.get("input_faktur_status") == "recorded" and b.get("input_faktur_id") == fpm_id:
        ok("Vendor Bill ter-flag input_faktur_status=recorded")
    else:
        bad(f"bill flag salah: {b and b.get('input_faktur_status')}")

    # ── C. Tidak eligible lagi + create kedua → 409 ───────────────────────
    info("TEST C: Bill ter-flag tak eligible + create ulang bill sama → 409")
    rc = s.get(f"{API}/input-tax-invoices/eligible-bills", params={"entity_id": ENTITY}, timeout=30)
    if rc.status_code == 200 and not any(b["vendor_bill_id"] == bill1 for b in rc.json()):
        ok("Bill ter-flag hilang dari eligible-bills")
    else:
        bad("bill masih eligible setelah dicatat")
    rc2 = s.post(f"{API}/input-tax-invoices",
                 json={"vendor_bill_id": bill1, "nsfp": "0100111122223333"}, timeout=30)
    if rc2.status_code == 409:
        ok("Create kedua utk bill sama → 409")
    else:
        bad(f"harus 409, dapat {rc2.status_code}")

    # ── D. NSFP dedupe ────────────────────────────────────────────────────
    info("TEST D: NSFP dedupe (bill lain, NSFP sama → 409)")
    bill2 = await seed_bill(db, "2", ppn=55000.0, dpp=500000.0)
    rd = s.post(f"{API}/input-tax-invoices",
                json={"vendor_bill_id": bill2, "nsfp": NSFP}, timeout=30)
    if rd.status_code == 409:
        ok("NSFP duplikat ditolak → 409")
    else:
        bad(f"NSFP dedupe GAGAL: harus 409, dapat {rd.status_code} {rd.text[:120]}")

    # ── E. Rekap PPN ──────────────────────────────────────────────────────
    info("TEST E: Rekap PPN Masukan vs Keluaran")
    re = s.get(f"{API}/tax/vat-summary", params={"period": PERIOD, "entity_id": ENTITY}, timeout=30)
    if re.status_code != 200:
        bad(f"vat-summary gagal: {re.status_code} {re.text[:150]}")
    else:
        sm = re.json()
        mas = float(sm.get("masukan", {}).get("ppn", 0))
        kel = float(sm.get("keluaran", {}).get("ppn", 0))
        net = float(sm.get("net_ppn", 0))
        if abs(mas - 110000) < 1:
            ok("Masukan PPN == 110.000")
        else:
            bad(f"Masukan salah: {mas}")
        if abs(kel - 200000) < 1:
            ok("Keluaran PPN == 200.000")
        else:
            bad(f"Keluaran salah: {kel}")
        if abs(net - 90000) < 1 and sm.get("position") == "kurang_bayar":
            ok("Net 90.000 → KURANG BAYAR (setor)")
        else:
            bad(f"Net/position salah: net={net} pos={sm.get('position')}")

    # ── F. Cancel → eligible lagi + NSFP reusable ─────────────────────────
    info("TEST F: Cancel → bill eligible lagi + NSFP reusable")
    rf = s.post(f"{API}/input-tax-invoices/{fpm_id}/cancel", json={"reason": "POC test cancel"}, timeout=30)
    if rf.status_code == 200 and rf.json().get("status") == "cancelled":
        ok("Cancel → status cancelled")
    else:
        bad(f"cancel salah: {rf.status_code} {rf.text[:120]}")
    rf2 = s.get(f"{API}/input-tax-invoices/eligible-bills", params={"entity_id": ENTITY}, timeout=30)
    if rf2.status_code == 200 and any(b["vendor_bill_id"] == bill1 for b in rf2.json()):
        ok("Bill kembali eligible setelah cancel")
    else:
        bad("bill tidak kembali eligible setelah cancel")
    rf3 = s.post(f"{API}/input-tax-invoices",
                 json={"vendor_bill_id": bill1, "nsfp": NSFP, "faktur_date": PDATE}, timeout=30)
    if rf3.status_code == 200:
        ok("NSFP lama bisa dipakai ulang setelah cancel")
    else:
        bad(f"NSFP reuse gagal: {rf3.status_code} {rf3.text[:120]}")

    await cleanup(db)
    await _finish(client)


async def _finish(client):
    client.close()
    print("\n" + "=" * 64)
    print(f"  SUMMARY: {len(PASS)} PASS | {len(FAIL)} FAIL")
    print("=" * 64)
    if FAIL:
        print("\n\u274c FAILED:")
        for f in FAIL:
            print(f"  - {f}")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0 if not FAIL else 1)
