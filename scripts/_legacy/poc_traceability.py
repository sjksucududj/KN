"""
poc_traceability.py — POC Traceability Asal Barang + Retur Presisi (controlled).

Skenario terkontrol (seed PO + roll bersih meniru output GRN), lalu uji jalur NYATA:
  P1  (statik) kode complete_inbound_receiving menyimpan origin di roll_doc
  P2  (HTTP)  Vendor Bill posted → roll tertaut vendor_bill_id + supplier_invoice_no
  P3  (HTTP)  GET /products/{id}/purchase-history → kartu asal (supplier/PO/invoice/lot)
  P3b (HTTP)  GET /purchase-returns/source-rolls → roll returnable per asal
  P4  (HTTP)  Retur berbasis roll_ids → roll SPESIFIK berkurang; roll lain TETAP available

Run: cd /app && python scripts/poc_traceability.py
"""
import os
import sys
import time
import uuid
import datetime as dt
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE = "http://localhost:8001/api"
mongo = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
PASS = FAIL = 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"   ✅ {msg}")
    else:
        FAIL += 1; print(f"   ❌ {msg}")


def login():
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": "admin@kainnusantara.id", "password": "demo12345"}, timeout=15)
    return {"Authorization": f"Bearer {r.json()['token']}"}


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    h = login()
    print("=" * 70)
    print("  POC TRACEABILITY ASAL BARANG + RETUR PRESISI (controlled)")
    print("=" * 70)

    # ── ambil master nyata dari PO seed ──────────────────────────────────────
    seed_po = mongo.purchase_orders.find_one({"items.0": {"$exists": True}}, {"_id": 0})
    it0 = seed_po["items"][0]
    pid = it0["product_id"]
    supplier_id = seed_po.get("supplier_id", "sup_poc")
    supplier_name = seed_po.get("supplier_name", "Supplier POC")
    warehouse_id = seed_po.get("warehouse_id", "wh_jkt")
    entity_id = seed_po.get("entity_id", "")
    price = float(it0.get("price", 50000) or 50000)
    unit = it0.get("unit", "meter")

    TAG = uuid.uuid4().hex[:6]
    LOT = f"POCLOT-{TAG}"
    INV = f"INV-POC-{TAG}"
    poc_po_id = f"po_poc_{TAG}"
    poc_po_no = f"PO-POC-{TAG}"
    QTY_EACH = 60.0

    # ── seed PO 'completed' (received=ordered agar 3-way match lolos) ─────────
    print(f"\n[setup] seed PO {poc_po_no} + 2 roll available (produk {pid})")
    mongo.purchase_orders.insert_one({
        "id": poc_po_id, "po_number": poc_po_no, "supplier_id": supplier_id,
        "supplier_name": supplier_name, "warehouse_id": warehouse_id, "entity_id": entity_id,
        "status": "completed", "payment_status": "unpaid", "created_at": now_iso(),
        "items": [{"product_id": pid, "sku": it0.get("sku", ""), "product_name": it0.get("product_name", ""),
                   "quantity": 120.0, "received_qty": 120.0, "unit": unit, "price": price,
                   "subtotal": price * 120.0}],
        "subtotal": price * 120.0, "grand_total": price * 120.0, "billed_amount": 0.0,
    })
    roll_ids = []
    for i in range(2):
        rid = f"roll_poc_{TAG}_{i}"
        roll_ids.append(rid)
        mongo.inventory_rolls.insert_one({
            "id": rid, "roll_no": f"RLPOC-{TAG}-{i}", "product_id": pid,
            "warehouse_id": warehouse_id, "owner_entity_id": entity_id, "status": "available",
            "length_initial": QTY_EACH, "length_remaining": QTY_EACH, "unit": unit,
            "lot": LOT, "dye_lot": f"DL-{TAG}", "grade": "A",
            "unit_cost": price, "base_unit_cost": price, "landed_cost_total": 0.0,
            "acquired": {"via": "inbound", "ref_id": poc_po_id, "date": now_iso()},
            # origin denormalisasi (yang dihasilkan GRN):
            "supplier_id": supplier_id, "supplier_name": supplier_name,
            "po_id": poc_po_id, "po_number": poc_po_no, "grn_task_id": f"task_poc_{TAG}",
            "received_date": now_iso(), "vendor_bill_id": "", "supplier_invoice_no": "",
            "created_at": now_iso(),
        })
    print(f"   rolls: {roll_ids}")

    # ── P1: verifikasi kode capture origin di GRN ────────────────────────────
    print("\n[P1] Origin fields ditulis saat GRN (static check kode)")
    src = open("/app/backend/routers/inbound_receiving.py").read()
    for f in ['"supplier_id":', '"supplier_name":', '"po_number":', '"grn_task_id":', '"received_date":']:
        ok(f in src, f"roll_doc GRN menulis {f}")

    # ── P2: Vendor Bill posted → tautkan invoice ke roll ─────────────────────
    print("\n[P2] Vendor Bill posted → roll tertaut invoice")
    rb = requests.post(f"{BASE}/vendor-bills", headers=h, timeout=20,
                       json={"po_id": poc_po_id, "supplier_invoice_no": INV,
                             "items": [{"product_id": pid, "billed_qty": 120.0, "price": price}],
                             "submit_now": True})
    ok(rb.status_code in (200, 201), f"create vendor bill HTTP {rb.status_code} ({str(rb.text)[:150]})")
    bill = rb.json() if rb.status_code in (200, 201) else {}
    bid = bill.get("id"); st = bill.get("status")
    print(f"   bill={bid} status={st}")
    if st in ("draft", "pending_approval", "submitted"):
        if st == "draft":
            requests.post(f"{BASE}/vendor-bills/{bid}/submit", headers=h, timeout=15)
        ra = requests.post(f"{BASE}/vendor-bills/{bid}/approve", headers=h, timeout=20)
        print(f"   approve → HTTP {ra.status_code} status={(ra.json().get('status') if ra.status_code==200 else '?')}")
    time.sleep(0.6)
    linked = list(mongo.inventory_rolls.find({"id": {"$in": roll_ids}}, {"_id": 0, "id": 1, "vendor_bill_id": 1, "supplier_invoice_no": 1}))
    ok(all(r.get("vendor_bill_id") == bid for r in linked), f"kedua roll.vendor_bill_id = {bid}")
    ok(all(r.get("supplier_invoice_no") == INV for r in linked), f"kedua roll.supplier_invoice_no = {INV}")

    # ── P3: purchase-history (Kartu Asal Produk) ─────────────────────────────
    print("\n[P3] GET /products/{id}/purchase-history")
    ph = requests.get(f"{BASE}/products/{pid}/purchase-history", headers=h, timeout=15)
    ok(ph.status_code == 200, f"purchase-history HTTP {ph.status_code}")
    data = ph.json() if ph.status_code == 200 else {}
    ev = next((e for e in data.get("events", []) if e.get("lot") == LOT), None)
    ok(ev is not None, f"event lot {LOT} muncul di kartu asal")
    if ev:
        ok(ev.get("supplier_name") == supplier_name, f"event.supplier_name = {ev.get('supplier_name')!r}")
        ok(ev.get("po_number") == poc_po_no, f"event.po_number = {ev.get('po_number')!r}")
        ok(ev.get("supplier_invoice_no") == INV, f"event.supplier_invoice_no = {ev.get('supplier_invoice_no')!r}")
        ok(abs(ev.get("qty_received", 0) - 120.0) < 0.5, f"event.qty_received = {ev.get('qty_received')}")
        ok(ev.get("roll_count") == 2, f"event.roll_count = {ev.get('roll_count')}")

    # ── P3b: source-rolls returnable ─────────────────────────────────────────
    print("\n[P3b] GET /purchase-returns/source-rolls")
    sr = requests.get(f"{BASE}/purchase-returns/source-rolls", headers=h, timeout=15,
                      params={"product_id": pid, "po_id": poc_po_id})
    ok(sr.status_code == 200, f"source-rolls HTTP {sr.status_code}")
    rr = sr.json().get("rolls", []) if sr.status_code == 200 else []
    got = {x["roll_id"] for x in rr}
    ok(set(roll_ids).issubset(got), f"kedua roll returnable ({len(got)} ditemukan)")
    sample = next((x for x in rr if x["roll_id"] == roll_ids[0]), {})
    ok(sample.get("supplier_invoice_no") == INV, f"returnable membawa invoice {sample.get('supplier_invoice_no')!r}")

    # ── P4: Retur PRESISI (hanya roll_ids[0]) ────────────────────────────────
    print("\n[P4] Retur berbasis roll_ids — hanya 1 roll spesifik")
    target = roll_ids[0]; other = roll_ids[1]
    pr = requests.post(f"{BASE}/purchase-returns", headers=h, timeout=20,
                       json={"supplier_id": supplier_id, "po_id": poc_po_id, "warehouse_id": warehouse_id,
                             "reason": "cacat",
                             "items": [{"product_id": pid, "quantity": 0, "condition": "damaged",
                                        "roll_ids": [target]}],
                             "submit_now": True})
    ok(pr.status_code in (200, 201), f"create return HTTP {pr.status_code} ({str(pr.text)[:150]})")
    ret = pr.json() if pr.status_code in (200, 201) else {}
    rid = ret.get("id"); rstatus = ret.get("status")
    item0 = (ret.get("items") or [{}])[0]
    ok(abs(item0.get("quantity", 0) - QTY_EACH) < 0.5, f"qty retur diturunkan dari roll = {item0.get('quantity')}")
    ok(item0.get("roll_ids") == [target], f"item.roll_ids = {item0.get('roll_ids')}")
    if rstatus in ("draft", "pending_approval", "submitted"):
        if rstatus == "draft":
            requests.post(f"{BASE}/purchase-returns/{rid}/submit", headers=h, timeout=15)
        rap = requests.post(f"{BASE}/purchase-returns/{rid}/approve", headers=h, timeout=20)
        ok(rap.status_code == 200, f"approve return HTTP {rap.status_code} ({str(rap.text)[:120]})")
    time.sleep(0.6)
    a = mongo.inventory_rolls.find_one({"id": target}, {"_id": 0})
    b = mongo.inventory_rolls.find_one({"id": other}, {"_id": 0})
    ok(a.get("status") == "returned_supplier", f"roll TARGET returned_supplier (dapat {a.get('status')})")
    ok(b.get("status") == "available", f"roll LAIN tetap available (dapat {b.get('status')}) → bukti PRESISI, bukan FIFO")
    mov = mongo.inventory_movements.find_one({"roll_id": target, "movement_type": "return_out"})
    ok(mov is not None, "movement return_out tercatat utk roll spesifik")

    # ── cleanup ──────────────────────────────────────────────────────────────
    mongo.purchase_orders.delete_one({"id": poc_po_id})
    mongo.inventory_rolls.delete_many({"id": {"$in": roll_ids}})
    mongo.inventory_movements.delete_many({"roll_id": {"$in": roll_ids}})
    if bid:
        mongo.vendor_bills.delete_one({"id": bid})
    if ret.get("id"):
        mongo.purchase_returns.delete_one({"id": ret["id"]})
    print("\n[cleanup] data POC dihapus.")

    print("\n" + "=" * 70)
    print(f"  HASIL: PASS={PASS}  FAIL={FAIL}")
    print("=" * 70)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
