#!/usr/bin/env python3
"""
Vendor Bill + 3-Way Matching Backend Test (Fase 5.2 — P0-2)
============================================================
Comprehensive backend API testing for Vendor Bill feature.
Tests: billing-context, matched bills, over-billing, price variance, 
       SoD approval, payment, AP summary, RBAC, dedupe.
"""
import sys
import requests
from datetime import datetime

# Use PUBLIC endpoint from frontend/.env
BASE = "https://po-pdf-sender.preview.emergentagent.com"
API = f"{BASE}/api"

ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
MANAGER = {"email": "manager@kainnusantara.id", "password": "demo12345"}
SALES = {"email": "sales@kainnusantara.id", "password": "demo12345"}

passed, failed = 0, 0
test_results = {"passed": [], "failed": []}


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
        test_results["passed"].append(name)
    else:
        failed += 1
        print(f"  ❌ {name} {extra}")
        test_results["failed"].append(f"{name} {extra}")


def login(creds):
    try:
        r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
        if r.status_code != 200:
            print(f"Login failed: {r.status_code} {r.text[:200]}")
            return None
        return r.json()["token"]
    except Exception as e:
        print(f"Login exception: {e}")
        return None


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    print("=" * 70)
    print("VENDOR BILL + 3-WAY MATCHING BACKEND TEST")
    print("=" * 70)
    
    # ── Auth ──────────────────────────────────────────────────────────────
    print("\n== 1. Authentication ==")
    admin = login(ADMIN)
    manager = login(MANAGER)
    sales = login(SALES)
    check("Login admin", admin is not None)
    check("Login manager", manager is not None)
    check("Login sales", sales is not None)
    
    if not admin:
        print("\n❌ Cannot proceed without admin login")
        sys.exit(1)
    
    # ── Get POs ───────────────────────────────────────────────────────────
    print("\n== 2. Get Purchase Orders ==")
    try:
        r = requests.get(f"{API}/purchase-orders", headers=H(admin), timeout=30)
        check("GET /purchase-orders 200", r.status_code == 200, r.text[:200])
        pos = r.json()
        po1 = next((p for p in pos if p["po_number"] == "PO-00001"), None)
        po3 = next((p for p in pos if p["po_number"] == "PO-00003"), None)
        check("PO-00001 exists (fully received, non-PKP)", po1 is not None)
        check("PO-00003 exists (partially received, PKP)", po3 is not None)
        
        if not po1 or not po3:
            print("\n❌ Required POs not found. Cannot proceed.")
            sys.exit(1)
    except Exception as e:
        check("GET /purchase-orders exception", False, str(e))
        sys.exit(1)
    
    # ── Billing Context ───────────────────────────────────────────────────
    print("\n== 3. GET /purchase-orders/{po_id}/billing-context ==")
    try:
        r = requests.get(f"{API}/purchase-orders/{po1['id']}/billing-context", 
                        headers=H(admin), timeout=30)
        check("GET billing-context 200", r.status_code == 200, r.text[:200])
        ctx = r.json()
        check("Context has items", "items" in ctx and len(ctx["items"]) > 0)
        
        if ctx.get("items"):
            it0 = ctx["items"][0]
            check("Item has ordered_qty", "ordered_qty" in it0)
            check("Item has received_qty", "received_qty" in it0)
            check("Item has already_billed_qty", "already_billed_qty" in it0)
            check("Item has billable_received", "billable_received" in it0)
            check("Item has po_price", "po_price" in it0)
            
            # Verify billable_received calculation
            expected = it0["received_qty"] - it0["already_billed_qty"]
            actual = it0["billable_received"]
            check("billable_received = received - already_billed", 
                  abs(actual - expected) < 0.01, 
                  f"expected {expected}, got {actual}")
    except Exception as e:
        check("billing-context exception", False, str(e))
    
    # ── Create MATCHED Bill (auto-post) ───────────────────────────────────
    print("\n== 4. POST /vendor-bills (MATCHED + submit_now=true) ==")
    try:
        # Get fresh context
        r = requests.get(f"{API}/purchase-orders/{po1['id']}/billing-context", 
                        headers=H(admin), timeout=30)
        ctx = r.json()
        
        # Create bill with exact received qty and PO price
        body = {
            "po_id": po1["id"],
            "supplier_invoice_no": f"TEST-INV-{datetime.now().strftime('%H%M%S')}",
            "match_mode": "received",
            "submit_now": True,
            "items": [
                {
                    "product_id": i["product_id"],
                    "billed_qty": i["billable_received"],
                    "price": i["po_price"]
                }
                for i in ctx["items"] if i["billable_received"] > 0
            ]
        }
        
        r = requests.post(f"{API}/vendor-bills", json=body, headers=H(admin), timeout=30)
        check("Create matched bill 200", r.status_code == 200, r.text[:200])
        
        if r.status_code == 200:
            bill = r.json()
            check("match_status = matched", bill.get("match_status") == "matched", 
                  f"got {bill.get('match_status')}")
            check("status = posted (auto-post)", bill.get("status") == "posted", 
                  f"got {bill.get('status')}")
            check("grand_total > 0", bill.get("grand_total", 0) > 0)
            check("financials.outstanding = grand_total", 
                  abs(bill.get("financials", {}).get("outstanding", 0) - bill.get("grand_total", 0)) < 0.01)
            
            # PO-00001 is non-PKP (PPN 0)
            check("PPN = 0 for non-PKP entity", bill.get("ppn_amount", 0) == 0, 
                  f"got ppn_amount={bill.get('ppn_amount')}")
            
            bill_id = bill["id"]
            bill_number = bill.get("bill_number")
    except Exception as e:
        check("Create matched bill exception", False, str(e))
        bill_id = None
    
    # ── PPN Computed for PKP Entity ───────────────────────────────────────
    print("\n== 5. PPN Computed for PKP Entity (PO-00003) ==")
    try:
        r = requests.get(f"{API}/purchase-orders/{po3['id']}/billing-context", 
                        headers=H(admin), timeout=30)
        ctx3 = r.json()
        
        # Find item with billable qty
        li = next((i for i in ctx3["items"] if i["billable_received"] > 0), None)
        if li:
            body = {
                "po_id": po3["id"],
                "supplier_invoice_no": f"TEST-PKP-{datetime.now().strftime('%H%M%S')}",
                "match_mode": "received",
                "items": [{"product_id": li["product_id"], "billed_qty": min(10, li["billable_received"]), "price": li["po_price"]}]
            }
            r = requests.post(f"{API}/vendor-bills", json=body, headers=H(admin), timeout=30)
            check("Create PKP bill 200", r.status_code == 200, r.text[:200])
            
            if r.status_code == 200:
                pkp_bill = r.json()
                check("ppn_amount > 0 for PKP", pkp_bill.get("ppn_amount", 0) > 0, 
                      f"got ppn_amount={pkp_bill.get('ppn_amount')}")
                check("is_pkp = true", pkp_bill.get("is_pkp") == True)
    except Exception as e:
        check("PKP bill exception", False, str(e))
    
    # ── PO Billing Sync ───────────────────────────────────────────────────
    print("\n== 6. PO Billing Sync ==")
    try:
        r = requests.get(f"{API}/purchase-orders/{po1['id']}", headers=H(admin), timeout=30)
        check("GET PO after billing 200", r.status_code == 200)
        
        if r.status_code == 200:
            po1_updated = r.json()
            check("PO billed_total updated", po1_updated.get("billed_total", 0) > 0, 
                  f"got billed_total={po1_updated.get('billed_total')}")
    except Exception as e:
        check("PO billing sync exception", False, str(e))
    
    # ── Payables Summary ──────────────────────────────────────────────────
    print("\n== 7. GET /vendor-bills/payables/summary ==")
    try:
        r = requests.get(f"{API}/vendor-bills/payables/summary", headers=H(admin), timeout=30)
        check("GET payables/summary 200", r.status_code == 200, r.text[:200])
        
        if r.status_code == 200:
            pay = r.json()
            check("total_outstanding present", "total_outstanding" in pay)
            check("total_outstanding > 0", pay.get("total_outstanding", 0) > 0)
            check("aging buckets present", "aging" in pay)
            check("by_supplier present", "by_supplier" in pay)
            check("bills array present", "bills" in pay)
            
            if bill_id:
                check("Created bill in payables", 
                      any(b["bill_id"] == bill_id for b in pay.get("bills", [])))
    except Exception as e:
        check("Payables summary exception", False, str(e))
    
    # ── Payment (Partial + Full) ──────────────────────────────────────────
    print("\n== 8. POST /vendor-bills/{id}/pay (Partial + Full) ==")
    if bill_id:
        try:
            # Get current bill
            r = requests.get(f"{API}/vendor-bills/{bill_id}", headers=H(admin), timeout=30)
            bill = r.json()
            grand = bill.get("grand_total", 0)
            
            # Partial payment
            half = round(grand / 2, 2)
            r = requests.post(f"{API}/vendor-bills/{bill_id}/pay", 
                            json={"amount": half, "cash_type": "kas_besar", "method": "transfer"}, 
                            headers=H(admin), timeout=30)
            check("Partial payment 200", r.status_code == 200, r.text[:200])
            
            if r.status_code == 200:
                bill = r.json()
                check("Status still posted after partial", bill.get("status") == "posted")
                check("payment_status = partial", 
                      bill.get("financials", {}).get("payment_status") == "partial")
                
                # Full payment
                rest = bill.get("financials", {}).get("outstanding", 0)
                r = requests.post(f"{API}/vendor-bills/{bill_id}/pay", 
                                json={"amount": rest, "cash_type": "kas_besar", "method": "transfer"}, 
                                headers=H(admin), timeout=30)
                check("Full payment 200", r.status_code == 200, r.text[:200])
                
                if r.status_code == 200:
                    bill = r.json()
                    check("Status = paid after full payment", bill.get("status") == "paid", 
                          f"got {bill.get('status')}")
        except Exception as e:
            check("Payment exception", False, str(e))
    
    # ── Cash Transaction Created ──────────────────────────────────────────
    print("\n== 9. Cash Transaction with ref_type=vendor_bill ==")
    try:
        r = requests.get(f"{API}/cash-transactions", headers=H(admin), timeout=30)
        check("GET cash-transactions 200", r.status_code == 200)
        
        if r.status_code == 200:
            cash = r.json()
            check("Cash txn with ref_type=vendor_bill exists", 
                  any(c.get("ref_type") == "vendor_bill" for c in cash))
    except Exception as e:
        check("Cash transaction exception", False, str(e))
    
    # ── Over-Billing (BLOCKED) ────────────────────────────────────────────
    print("\n== 10. Over-Billing (match_status=blocked, submit fails) ==")
    try:
        r = requests.get(f"{API}/purchase-orders/{po3['id']}/billing-context", 
                        headers=H(admin), timeout=30)
        ctx3 = r.json()
        over_item = next((i for i in ctx3["items"] if i["received_qty"] > 0), None)
        
        if over_item:
            body = {
                "po_id": po3["id"],
                "supplier_invoice_no": f"TEST-OVER-{datetime.now().strftime('%H%M%S')}",
                "match_mode": "received",
                "items": [{
                    "product_id": over_item["product_id"],
                    "billed_qty": over_item["received_qty"] + 100,  # Way over
                    "price": over_item["po_price"]
                }]
            }
            r = requests.post(f"{API}/vendor-bills", json=body, headers=H(admin), timeout=30)
            check("Over-bill create 200 (draft)", r.status_code == 200, r.text[:200])
            
            if r.status_code == 200:
                ob = r.json()
                check("match_status = blocked", ob.get("match_status") == "blocked", 
                      f"got {ob.get('match_status')}")
                
                # Try to submit
                r = requests.post(f"{API}/vendor-bills/{ob['id']}/submit", 
                                headers=H(admin), timeout=30)
                check("Submit blocked bill → 400", r.status_code == 400, 
                      f"got {r.status_code}")
    except Exception as e:
        check("Over-billing exception", False, str(e))
    
    # ── Price Variance (WARNING → Approval) ───────────────────────────────
    print("\n== 11. Price Variance (warning → pending_approval → SoD) ==")
    try:
        r = requests.get(f"{API}/purchase-orders/{po3['id']}/billing-context", 
                        headers=H(admin), timeout=30)
        ctx3 = r.json()
        pv_item = next((i for i in ctx3["items"] if i["received_qty"] > 0), None)
        
        if pv_item:
            # Price 20% above PO price
            hi_price = round(pv_item["po_price"] * 1.2, 2)
            body = {
                "po_id": po3["id"],
                "supplier_invoice_no": f"TEST-PV-{datetime.now().strftime('%H%M%S')}",
                "match_mode": "received",
                "submit_now": True,
                "items": [{
                    "product_id": pv_item["product_id"],
                    "billed_qty": min(pv_item["received_qty"], 50),
                    "price": hi_price
                }]
            }
            r = requests.post(f"{API}/vendor-bills", json=body, headers=H(admin), timeout=30)
            check("Price variance create+submit 200", r.status_code == 200, r.text[:200])
            
            if r.status_code == 200:
                pv = r.json()
                check("match_status = warning", pv.get("match_status") == "warning", 
                      f"got {pv.get('match_status')}")
                check("status = pending_approval", pv.get("status") == "pending_approval", 
                      f"got {pv.get('status')}")
                pv_id = pv["id"]
                
                # SoD: admin created, admin cannot approve
                r = requests.post(f"{API}/vendor-bills/{pv_id}/approve", 
                                headers=H(admin), timeout=30)
                check("Creator (admin) cannot approve own (SoD) → 403", 
                      r.status_code == 403, f"got {r.status_code}")
                
                # Manager approves
                if manager:
                    r = requests.post(f"{API}/vendor-bills/{pv_id}/approve", 
                                    headers=H(manager), timeout=30)
                    check("Manager approves → 200", r.status_code == 200, 
                          f"got {r.status_code}")
                    
                    if r.status_code == 200:
                        check("Status = posted after approval", 
                              r.json().get("status") == "posted")
    except Exception as e:
        check("Price variance exception", False, str(e))
    
    # ── RBAC: Sales Role ──────────────────────────────────────────────────
    print("\n== 12. RBAC: Sales Role Restrictions ==")
    if sales:
        try:
            # Sales cannot create
            body = {
                "po_id": po3["id"],
                "items": [{"product_id": po3["items"][0]["product_id"], "billed_qty": 5}]
            }
            r = requests.post(f"{API}/vendor-bills", json=body, headers=H(sales), timeout=30)
            check("Sales create vendor bill → 403", r.status_code == 403, 
                  f"got {r.status_code}")
            
            # Sales can view
            r = requests.get(f"{API}/vendor-bills", headers=H(sales), timeout=30)
            check("Sales can view list → 200", r.status_code == 200)
        except Exception as e:
            check("RBAC exception", False, str(e))
    
    # ── Dedupe Supplier Invoice No ────────────────────────────────────────
    print("\n== 13. Dedupe: Duplicate supplier_invoice_no ==")
    try:
        # Create first bill
        inv_no = f"TEST-DUP-{datetime.now().strftime('%H%M%S')}"
        r = requests.get(f"{API}/purchase-orders/{po3['id']}/billing-context", 
                        headers=H(admin), timeout=30)
        ctx3 = r.json()
        item = next((i for i in ctx3["items"] if i["billable_received"] > 0), None)
        
        if item:
            body = {
                "po_id": po3["id"],
                "supplier_invoice_no": inv_no,
                "items": [{"product_id": item["product_id"], "billed_qty": min(5, item["billable_received"])}]
            }
            r1 = requests.post(f"{API}/vendor-bills", json=body, headers=H(admin), timeout=30)
            check("First bill with invoice_no created", r1.status_code == 200)
            
            if r1.status_code == 200:
                # Try to create second bill with same invoice_no and same supplier
                r2 = requests.post(f"{API}/vendor-bills", json=body, headers=H(admin), timeout=30)
                check("Duplicate invoice_no → 409", r2.status_code == 409, 
                      f"got {r2.status_code}")
    except Exception as e:
        check("Dedupe exception", False, str(e))
    
    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"RESULT: {passed} PASS | {failed} FAIL")
    print("=" * 70)
    
    if failed > 0:
        print("\nFailed tests:")
        for f in test_results["failed"]:
            print(f"  - {f}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
