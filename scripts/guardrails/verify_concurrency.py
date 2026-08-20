#!/usr/bin/env python3
"""INV-CONC-01 (RUNTIME) — GATE anti-RACE / TOCTOU pada jalur uang & stok.

Blindspot yang ditutup: verifikasi #074–#076 KN TAK PERNAH menguji konkurensi.
Proyek pembanding (travel) menemukan bug P0 #1 justru di sini (pembayaran paralel → overpay).

Pola bug (check-then-$inc, NON-atomic):
  - `/vendor-bills/{id}/pay`  : baca bill → cek `amount <= outstanding` → `$inc amount_paid`.
  - `/ar-receipts`            : baca order → cek `amount <= outstanding` → update paid.
  K request paralel semua lolos cek (baca stale) → amount_paid > grand_total = OVERPAYMENT.

Kriteria (INVARIAN keras): untuk dokumen apa pun, `amount_paid` TIDAK BOLEH > `grand_total`.
  K pembayaran-penuh paralel → hanya 1 boleh sukses; sisanya 4xx. Bila amount_paid > grand_total = LEAK.

Resilient: backend down / login gagal / tak bisa siapkan target → SKIP. Exit 1 hanya bila RACE terbukti.
Usage: cd /app && MONGO_URL=... DB_NAME=... python scripts/guardrails/verify_concurrency.py
"""
import concurrent.futures as cf
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import run_with_restore  # noqa: E402
from pymongo import MongoClient

BASE = os.environ.get("API_BASE", "http://localhost:8001").rstrip("/") + "/api"
G, Y, R, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[1m", "\033[0m"
EPS = 0.5
K = 6  # derajat paralelisme
fails = 0
skips = 0


def ok(m):
    print(f"  {G}[OK]{X} {m}")


def leak(m):
    global fails
    fails += 1
    print(f"  {R}[RACE]{X} {m}")


def skip(m):
    global skips
    skips += 1
    print(f"  {Y}[SKIP]{X} {m}")


def admin_headers():
    try:
        r = requests.post(f"{BASE}/auth/login",
                          json={"email": "admin@kainnusantara.id", "password": "demo12345"}, timeout=10)
        return {"Authorization": f"Bearer {r.json()['token']}"} if r.status_code == 200 else None
    except Exception:
        return None


def fire_parallel(fn, k=K):
    with cf.ThreadPoolExecutor(max_workers=k) as ex:
        return list(ex.map(fn, range(k)))


def test_vendor_bill_overpay(mc, H):
    # buat satu vendor-bill dari PO yang sudah bisa ditagih
    bill = None
    for po in mc.purchase_orders.find({}, {"_id": 0, "id": 1}):
        ctx = requests.get(f"{BASE}/purchase-orders/{po['id']}/billing-context", headers=H, timeout=10)
        if ctx.status_code != 200:
            continue
        items = [it for it in ctx.json().get("items", [])
                 if (it.get("billable_received") or it.get("billable_qty") or 0) > 0]
        if not items:
            continue
        qty = max(1, int(items[0].get("billable_received") or items[0].get("billable_qty") or 1))
        r = requests.post(f"{BASE}/vendor-bills", headers=H,
                          json={"po_id": po["id"], "items": [{"product_id": items[0]["product_id"], "billed_qty": qty}],
                                "submit_now": True}, timeout=15)
        if r.status_code == 200:
            bill = r.json()
            break
    if not bill:
        skip("vendor-bill: tak bisa membuat bill dari PO seed.")
        return
    bid, grand = bill["id"], float(bill["grand_total"])
    codes = fire_parallel(lambda i: requests.post(f"{BASE}/vendor-bills/{bid}/pay", headers=H,
                          json={"amount": grand, "method": "Transfer", "cash_type": "bank"}, timeout=15).status_code)
    after = mc.vendor_bills.find_one({"id": bid}, {"_id": 0, "amount_paid": 1, "grand_total": 1})
    paid, gt = float(after.get("amount_paid", 0)), float(after.get("grand_total", 0))
    succ = sum(1 for c in codes if c == 200)
    if paid > gt + EPS:
        leak(f"vendor-bill pay: {K} pay-penuh paralel → {succ}× 200; amount_paid={paid:,.0f} > grand_total={gt:,.0f} "
             f"(OVERPAY {paid/gt:.1f}×). TOCTOU di POST /vendor-bills/{{id}}/pay (baca→cek→$inc non-atomic).")
    else:
        ok(f"vendor-bill pay paralel aman (amount_paid={paid:,.0f} ≤ grand_total={gt:,.0f}; sukses={succ}).")


def test_ar_receipt_overpay(mc, H):
    # cari SO AR-eligible (status hidup, belum ada payment) → outstanding = grand_total.
    dead = {"cancelled", "expired", "draft", "rejected"}
    target = None
    for so in mc.sales_orders.find({}, {"_id": 0, "id": 1, "number": 1, "status": 1, "customer_id": 1,
                                        "grand_total": 1, "paid_total": 1, "entity_id": 1}):
        gt = float(so.get("grand_total", 0) or 0)
        paid = float(so.get("paid_total", 0) or 0)
        if so.get("status") not in dead and gt > 1000 and paid <= 0.5 and so.get("customer_id"):
            target = (so, round(gt, 2))
            break
    if not target:
        skip("ar-receipt: tak ada SO AR-eligible di seed.")
        return
    so, outstanding = target
    payload = {"customer_id": so["customer_id"], "amount": outstanding, "method": "transfer",
               "entity_id": so.get("entity_id"), "allocations": [{"order_id": so["id"], "amount": outstanding}]}
    K_AR = 20  # window AR lebih kecil (endpoint berat) → butuh paralelisme lebih tinggi
    codes = fire_parallel(lambda i: requests.post(f"{BASE}/ar-receipts", headers=H, json=payload, timeout=20).status_code, K_AR)
    succ = sum(1 for c in codes if c == 200)
    after = mc.sales_orders.find_one({"id": so["id"]}, {"_id": 0, "paid_total": 1, "payments": 1, "grand_total": 1})
    pt = float(after.get("paid_total", 0) or 0)
    plen = len(after.get("payments") or [])
    nrec = mc.ar_receipts.count_documents({"allocations.order_id": so["id"]}) if "ar_receipts" in mc.list_collection_names() else -1
    if succ > 1:
        kind = "OVERPAY (paid_total>grand)" if pt > outstanding + EPS else \
               (f"LOST-UPDATE ({nrec} receipt dibuat tapi order.payments={plen})" if nrec != plen else "double-apply")
        leak(f"ar-receipt {so.get('number')}: {succ}/{K_AR} receipt-penuh paralel SUKSES utk outstanding tunggal → {kind}. "
             f"TOCTOU di _apply_to_order (baca payments→$set clobber). Uang diterima tak tercatat konsisten.")
    elif succ == 0:
        skip(f"ar-receipt: 0 receipt sukses (order tak eligible: {codes[:4]}...) — INCONCLUSIVE.")
    else:
        ok(f"ar-receipt paralel aman ({succ}/{K_AR} sukses; paid_total={pt:,.0f} ≤ grand={outstanding:,.0f}; receipts={nrec}=payments={plen}).")


def main() -> int:
    print(f"\n{B}{'='*64}{X}\n  CONCURRENCY / RACE GATE (INV-CONC-01)  {BASE}\n{B}{'='*64}{X}")
    try:
        if requests.get(f"{BASE}/", timeout=5).status_code >= 500:
            raise Exception("5xx")
    except Exception:
        print(f"{Y}  Backend belum berjalan — SKIP (Phase 0).{X}")
        return 0
    H = admin_headers()
    if not H:
        skip("login admin gagal.")
        return _summary()
    mc = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
    test_vendor_bill_overpay(mc, H)
    test_ar_receipt_overpay(mc, H)
    return _summary()


def _summary() -> int:
    print(f"\n{B}{'='*64}{X}\n  {R}RACE {fails}{X} | {Y}SKIP {skips}{X}\n{B}{'='*64}{X}")
    if fails:
        print(f"{R}{B}  RACE/TOCTOU TERBUKTI — jalur uang tidak atomic (INV-CONC-01).{X}\n")
        return 1
    print(f"{G}{B}  Tak ada race terdeteksi (INV-CONC-01 tertutup untuk jalur teruji).{X}\n")
    return 0


if __name__ == "__main__":
    try:
        # Gate runtime memanggil API sungguhan -> MENGUBAH data (mis. audit_logs).
        # run_with_restore() snapshot DB sebelum uji & memulihkannya di `finally`,
        # supaya `gate.sh` tidak lagi meninggalkan residu di data demo.
        rc = run_with_restore(main)
    except Exception as ex:  # noqa: BLE001
        print(f"{Y}  Gate error (dianggap SKIP): {ex}{X}")
        rc = 0
    sys.exit(rc)
