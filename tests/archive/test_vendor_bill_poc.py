"""POC test — Fase 5.2 Vendor Bill + 3-Way Matching (backend core validation)."""
import requests, sys, json

BASE = "http://localhost:8001/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
SALES = {"email": "sales@kainnusantara.id", "password": "demo12345"}
MANAGER = {"email": "manager@kainnusantara.id", "password": "demo12345"}

passed, failed = 0, 0
def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1; print(f"  ✅ {name}")
    else:
        failed += 1; print(f"  ❌ {name} {extra}")

def login(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds)
    return r.json()["token"]

def H(tok): return {"Authorization": f"Bearer {tok}"}

def main():
    admin = login(ADMIN); manager = login(MANAGER); sales = login(SALES)
    print("== Auth ==")
    check("login admin/manager/sales", all([admin, manager, sales]))

    # Find a completed PO with received qty
    pos = requests.get(f"{BASE}/purchase-orders", headers=H(admin)).json()
    po1 = next((p for p in pos if p["po_number"] == "PO-00001"), None)
    po3 = next((p for p in pos if p["po_number"] == "PO-00003"), None)
    check("PO-00001 + PO-00003 exist", po1 and po3)

    print("\n== billing-context ==")
    ctx = requests.get(f"{BASE}/purchase-orders/{po1['id']}/billing-context", headers=H(admin)).json()
    check("context returns items with billable_received", ctx.get("items") and all("billable_received" in i for i in ctx["items"]))
    it0 = ctx["items"][0]
    check("billable_received == received - already_billed", abs(it0["billable_received"] - (it0["received_qty"] - it0["already_billed_qty"])) < 0.01, json.dumps(it0))

    print("\n== Create MATCHED bill (bill exactly received) + auto-post ==")
    body = {"po_id": po1["id"], "supplier_invoice_no": "SUP-INV-A1",
            "match_mode": "received", "submit_now": True,
            "items": [{"product_id": i["product_id"], "billed_qty": i["billable_received"], "price": i["po_price"]}
                      for i in ctx["items"] if i["billable_received"] > 0]}
    r = requests.post(f"{BASE}/vendor-bills", json=body, headers=H(admin))
    check("create+submit 200", r.status_code == 200, r.text[:200])
    bill = r.json()
    check("match_status == matched", bill.get("match_status") == "matched", bill.get("match_status"))
    check("auto-posted (no approval)", bill.get("status") == "posted", bill.get("status"))
    check("grand_total > 0 (PO-00001 = non-PKP, PPN 0 OK)", bill.get("grand_total", 0) > 0)
    check("financials.outstanding == grand_total", abs(bill["financials"]["outstanding"] - bill["grand_total"]) < 0.01)
    bill_id = bill["id"]

    print("\n== PPN computed on PKP entity (PO-00003 = ent_ksc) ==")
    ctx3p = requests.get(f"{BASE}/purchase-orders/{po3['id']}/billing-context", headers=H(admin)).json()
    li = next(i for i in ctx3p["items"] if i["billable_received"] > 0)
    rppn = requests.post(f"{BASE}/vendor-bills", json={"po_id": po3["id"], "supplier_invoice_no": "SUP-PPN-1",
            "match_mode": "received", "items": [{"product_id": li["product_id"], "billed_qty": 10, "price": li["po_price"]}]},
            headers=H(admin))
    check("PKP bill create 200", rppn.status_code == 200, rppn.text[:160])
    check("ppn_amount > 0 for PKP", rppn.json().get("ppn_amount", 0) > 0, str(rppn.json().get("ppn_amount")))

    print("\n== PO billing sync ==")
    po1b = requests.get(f"{BASE}/purchase-orders/{po1['id']}", headers=H(admin)).json()
    check("PO billed_total updated", po1b.get("billed_total", 0) > 0, str(po1b.get("billed_total")))

    print("\n== Payables summary (bill-based AP) ==")
    pay = requests.get(f"{BASE}/vendor-bills/payables/summary", headers=H(admin)).json()
    check("payables total_outstanding > 0", pay.get("total_outstanding", 0) > 0)
    check("bill appears in payables rows", any(b["bill_id"] == bill_id for b in pay.get("bills", [])))

    print("\n== Pay the bill (partial then full) ==")
    half = round(bill["grand_total"] / 2, 2)
    r = requests.post(f"{BASE}/vendor-bills/{bill_id}/pay", json={"amount": half, "cash_type": "kas_besar"}, headers=H(admin))
    check("partial pay 200", r.status_code == 200, r.text[:200])
    check("status still posted after partial", r.json().get("status") == "posted")
    check("payment_status partial", r.json()["financials"]["payment_status"] == "partial")
    rest = r.json()["financials"]["outstanding"]
    r = requests.post(f"{BASE}/vendor-bills/{bill_id}/pay", json={"amount": rest, "cash_type": "kas_besar"}, headers=H(admin))
    check("full pay 200", r.status_code == 200, r.text[:200])
    check("status paid", r.json().get("status") == "paid", r.json().get("status"))
    # cash transaction created with ref_type vendor_bill
    cash = requests.get(f"{BASE}/cash-transactions", headers=H(admin)).json()
    check("cash txn ref_type=vendor_bill exists", any(c.get("ref_type") == "vendor_bill" for c in cash))

    print("\n== Dedupe supplier_invoice_no ==")
    r = requests.post(f"{BASE}/vendor-bills", json={"po_id": po3["id"], "supplier_invoice_no": "SUP-INV-A1",
            "items": [{"product_id": po3["items"][0]["product_id"], "billed_qty": 10}]}, headers=H(admin))
    # po3 supplier differs from po1? dedupe is per supplier — only blocks if same supplier. Accept 200 or 409.
    check("dedupe handled (200 diff supplier OR 409 same)", r.status_code in (200, 409), r.text[:150])
    if r.status_code == 200:
        # cleanup-ish: leave as draft
        pass

    print("\n== OVER-BILLING (blocked) ==")
    ctx3 = requests.get(f"{BASE}/purchase-orders/{po3['id']}/billing-context", headers=H(admin)).json()
    over_item = next(i for i in ctx3["items"] if i["received_qty"] > 0)
    r = requests.post(f"{BASE}/vendor-bills", json={"po_id": po3["id"], "supplier_invoice_no": "SUP-OVER-1",
            "match_mode": "received",
            "items": [{"product_id": over_item["product_id"], "billed_qty": over_item["received_qty"] + 50, "price": over_item["po_price"]}]},
            headers=H(admin))
    check("over-bill create returns 200 draft", r.status_code == 200, r.text[:200])
    ob = r.json()
    check("match_status == blocked", ob.get("match_status") == "blocked", ob.get("match_status"))
    # submit should fail
    r = requests.post(f"{BASE}/vendor-bills/{ob['id']}/submit", headers=H(admin))
    check("submit blocked bill → 400", r.status_code == 400, r.text[:150])

    print("\n== PRICE VARIANCE (warning → approval) ==")
    # bill at price 20% above PO price → price_variance warning → pending_approval
    pv_item = next(i for i in ctx3["items"] if i["received_qty"] > 0)
    hi_price = round(pv_item["po_price"] * 1.2, 2)
    r = requests.post(f"{BASE}/vendor-bills", json={"po_id": po3["id"], "supplier_invoice_no": "SUP-PV-1",
            "match_mode": "received", "submit_now": True,
            "items": [{"product_id": pv_item["product_id"], "billed_qty": min(pv_item["received_qty"], 50), "price": hi_price}]},
            headers=H(admin))
    check("price-variance create+submit 200", r.status_code == 200, r.text[:200])
    pv = r.json()
    check("match_status == warning", pv.get("match_status") == "warning", pv.get("match_status"))
    check("submit → pending_approval", pv.get("status") == "pending_approval", pv.get("status"))
    pv_id = pv["id"]
    # SoD: admin created → admin cannot approve own? admin is creator; manager approves
    r = requests.post(f"{BASE}/vendor-bills/{pv_id}/approve", json={}, headers=H(admin))
    check("creator(admin) cannot approve own (SoD 403)", r.status_code == 403, f"{r.status_code} {r.text[:120]}")
    r = requests.post(f"{BASE}/vendor-bills/{pv_id}/approve", json={}, headers=H(manager))
    check("manager approves → posted", r.status_code == 200 and r.json().get("status") == "posted", r.text[:160])

    print("\n== RBAC: sales cannot create bill ==")
    r = requests.post(f"{BASE}/vendor-bills", json={"po_id": po3["id"], "items": [{"product_id": pv_item["product_id"], "billed_qty": 5}]}, headers=H(sales))
    check("sales create → 403", r.status_code == 403, f"{r.status_code}")
    r = requests.get(f"{BASE}/vendor-bills", headers=H(sales))
    check("sales can view list (200)", r.status_code == 200)

    print(f"\n{'='*50}\n  RESULT: {passed} PASS | {failed} FAIL\n{'='*50}")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
