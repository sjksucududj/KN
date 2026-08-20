"""
Self-contained POC — Retur Beli PRESISI per roll/lot (S#2026-07-21 continuation).

Membuktikan pipeline end-to-end yang dipakai UI RollPickerModal + Kartu Asal:
  PO baru -> approve -> scan-receive -> complete -> QC accept (quarantine->available,
  origin supplier/PO tersimpan) -> source-rolls (picker) -> buat retur presisi
  (roll_ids) -> approve retur -> roll terkonsumsi + Nota Debit + Kartu Asal update.

Run: cd /app && python test_precision_return_poc.py
"""
import sys
import requests

BASE = "http://localhost:8001/api"
SUPPLIER_ID = "sup_783209b83eba"   # Cirebon Craft (seed)
PRODUCT_ID = "prod_batik_mega"
WAREHOUSE_ID = "wh_jakarta"

PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name} {extra}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


def login():
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": "admin@kainnusantara.id", "password": "demo12345"})
    r.raise_for_status()
    return r.json()["token"]


def main():
    tok = login()
    H = {"Authorization": f"Bearer {tok}"}
    print("== 1. LOGIN ==")
    check("login admin", bool(tok))

    print("\n== 2. CREATE PO (Cirebon Craft / Batik / 300 yard) ==")
    po_body = {
        "supplier_id": SUPPLIER_ID,
        "warehouse_id": WAREHOUSE_ID,
        "items": [{"product_id": PRODUCT_ID, "quantity": 300, "unit": "yard", "price": 120000}],
        "notes": "POC retur presisi",
    }
    r = requests.post(f"{BASE}/purchase-orders", json=po_body, headers=H)
    check("PO created", r.status_code == 200, f"({r.status_code})")
    if r.status_code != 200:
        print("   ", r.text[:300]); return
    po = r.json()
    po_id = po["id"]
    print(f"    PO {po.get('po_number')} status={po.get('status')} needs_approval={po.get('approval_required')}")

    if po.get("approval_required") or po.get("status") == "waiting_approval":
        print("\n== 2b. APPROVE PO ==")
        # approve sampai fully approved (multi-level aman: loop hingga 'pending')
        for _ in range(5):
            ra = requests.post(f"{BASE}/purchase-orders/{po_id}/approve",
                               json={"notes": "ok poc"}, headers=H)
            if ra.status_code != 200:
                print("    approve resp:", ra.status_code, ra.text[:200]); break
            st = ra.json().get("status")
            if st != "waiting_approval":
                break
        r2 = requests.get(f"{BASE}/purchase-orders/{po_id}", headers=H)
        check("PO approved -> pending", r2.json().get("status") in ("pending", "receiving"),
              f"(status={r2.json().get('status')})")

    print("\n== 3. FIND INBOUND TASK ==")
    rt = requests.get(f"{BASE}/inbound/tasks", headers=H)
    tasks = [t for t in rt.json() if t.get("po_id") == po_id and t.get("product_id") == PRODUCT_ID]
    check("inbound task created for PO", len(tasks) >= 1, f"(found {len(tasks)})")
    if not tasks:
        return
    task_id = tasks[0]["id"]
    print(f"    task {task_id} status={tasks[0].get('status')}")

    print("\n== 4. SCAN-RECEIVE (300 yard, LOT-POC) ==")
    rr = requests.post(f"{BASE}/inbound/tasks/{task_id}/scan-receive",
                       json={"product_id": PRODUCT_ID, "actual_qty": 300,
                             "lot": "LOT-POC", "dye_lot": "LOT-POC", "grade": "A"}, headers=H)
    check("scan-receive ok", rr.status_code == 200, f"({rr.status_code} {rr.text[:120] if rr.status_code!=200 else ''})")

    print("\n== 5. COMPLETE (single roll fallback) ==")
    rc = requests.post(f"{BASE}/inbound/tasks/{task_id}/complete", json={}, headers=H)
    check("complete ok", rc.status_code == 200, f"({rc.status_code} {rc.text[:160] if rc.status_code!=200 else ''})")
    comp = rc.json() if rc.status_code == 200 else {}
    print(f"    next_stage/status: {comp.get('status') or comp.get('next_stage') or comp}")

    print("\n== 6. QC ACCEPT (quarantine -> available) ==")
    # roll milik task ini
    rq = requests.get(f"{BASE}/inbound/qc/tasks/{task_id}/rolls", headers=H)
    qrolls = rq.json() if rq.status_code == 200 else []
    q_qty = sum(float(x.get("length_remaining") or x.get("qty_remaining") or 0) for x in qrolls)
    print(f"    quarantine rolls: {len(qrolls)} total~{q_qty}")
    rqc = requests.post(f"{BASE}/inbound/tasks/{task_id}/qc-decision",
                        json={"accept_qty": 300, "reject_qty": 0, "accept_grade": "A"}, headers=H)
    check("qc-decision accept ok", rqc.status_code == 200, f"({rqc.status_code} {rqc.text[:160] if rqc.status_code!=200 else ''})")

    # Also QC-accept any other pre-existing qc_pending batik task (richer demo data)
    for t in rt.json():
        if t.get("product_id") == PRODUCT_ID and t.get("status") == "qc_pending" and t["id"] != task_id:
            requests.post(f"{BASE}/inbound/tasks/{t['id']}/qc-decision",
                          json={"accept_qty": float(t.get("quantity") or t.get("received_qty") or 0),
                                "reject_qty": 0, "accept_grade": "A"}, headers=H)

    print("\n== 7. SOURCE-ROLLS (picker) filtered by supplier+product ==")
    rs = requests.get(f"{BASE}/purchase-returns/source-rolls",
                      params={"product_id": PRODUCT_ID, "supplier_id": SUPPLIER_ID}, headers=H)
    src = rs.json() if rs.status_code == 200 else {}
    rolls = src.get("rolls", [])
    check("source-rolls returns available supplier-origin rolls", len(rolls) >= 1,
          f"(count={src.get('count')}, returnable={src.get('total_returnable')})")
    if not rolls:
        print("    (no rolls -> cannot proceed precision return)"); _summary(); return
    # ambil 1 roll dari PO baru ini utk retur (sisakan lainnya utk uji frontend)
    poc_roll = next((x for x in rolls if x.get("po_number") == po.get("po_number")), rolls[0])
    print(f"    pick roll {poc_roll['roll_no']} lot={poc_roll.get('lot')} qty={poc_roll['qty_remaining']} "
          f"cost={poc_roll.get('unit_cost')} po={poc_roll.get('po_number')} sup={poc_roll.get('supplier_name')}")

    print("\n== 8. CREATE PRECISION PURCHASE RETURN (roll_ids) ==")
    ret_body = {
        "supplier_id": SUPPLIER_ID,
        "po_id": po_id,
        "warehouse_id": WAREHOUSE_ID,
        "reason": "POC cacat sebagian",
        "items": [{
            "product_id": PRODUCT_ID,
            "quantity": poc_roll["qty_remaining"],
            "unit": poc_roll.get("unit", "yard"),
            "price": 0,                       # biar backend isi dari roll asal
            "reason": "cacat", "condition": "damaged",
            "roll_ids": [poc_roll["roll_id"]],
        }],
        "submit_now": True,
    }
    rcre = requests.post(f"{BASE}/purchase-returns", json=ret_body, headers=H)
    check("purchase-return created", rcre.status_code == 200, f"({rcre.status_code} {rcre.text[:200] if rcre.status_code!=200 else ''})")
    if rcre.status_code != 200:
        _summary(); return
    ret = rcre.json()
    ret_id = ret["id"]
    it0 = (ret.get("items") or [{}])[0]
    print(f"    retur {ret.get('number')} status={ret.get('status')} total={ret.get('total_amount')}")
    check("price auto-filled from roll cost", float(it0.get("price", 0)) > 0, f"(price={it0.get('price')})")
    check("roll_ids stored on item", bool(it0.get("roll_ids")), f"(roll_ids={it0.get('roll_ids')})")

    print("\n== 9. APPROVE RETURN -> debit note + consume roll ==")
    rap = requests.post(f"{BASE}/purchase-returns/{ret_id}/approve", json={"notes": "ok"}, headers=H)
    check("return approved", rap.status_code == 200, f"({rap.status_code} {rap.text[:200] if rap.status_code!=200 else ''})")
    approved = rap.json() if rap.status_code == 200 else {}
    check("debit note issued", bool(approved.get("debit_note_number")), f"(dn={approved.get('debit_note_number')})")

    print("\n== 10. VERIFY roll consumed via source-rolls delta ==")
    rs2 = requests.get(f"{BASE}/purchase-returns/source-rolls",
                       params={"product_id": PRODUCT_ID, "supplier_id": SUPPLIER_ID}, headers=H)
    ids_after = {x["roll_id"] for x in rs2.json().get("rolls", [])}
    check("returned roll no longer available", poc_roll["roll_id"] not in ids_after,
          f"(roll {poc_roll['roll_no']} present_after={poc_roll['roll_id'] in ids_after})")

    print("\n== 11. VERIFY Kartu Asal (purchase-history) has supplier event ==")
    rh = requests.get(f"{BASE}/products/{PRODUCT_ID}/purchase-history", headers=H)
    hist = rh.json() if rh.status_code == 200 else {}
    sups = hist.get("summary", {}).get("suppliers", [])
    check("Kartu Asal lists Cirebon Craft", "Cirebon Craft" in sups, f"(suppliers={sups})")

    _summary()


def _summary():
    print("\n" + "=" * 50)
    print(f"RESULT: {PASS} PASS / {FAIL} FAIL")
    print("=" * 50)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
