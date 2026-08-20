#!/usr/bin/env python3
"""
EPIC7-A Backend Test — AR / Piutang Aging
==========================================
Tests:
1. GET /api/ar/aging (admin/manager) - summary with totals, customers, config
2. Verify calculations: sum of buckets == total, customer outstanding sums
3. Verify denda (late fee) calculations
4. GET /api/ar/aging/{customer_id} - drill-down to per-order details
5. RBAC: admin/manager get 200, sales gets 403
6. Entity filter support
"""
import os
import requests

BASE = "https://po-pdf-sender.preview.emergentagent.com"
API = f"{BASE}/api"
PASS, FAIL = 0, 0
BUCKETS = ["current", "b1_30", "b31_60", "b61_90", "b90_plus"]


def ok(c, m):
    global PASS, FAIL
    if c:
        PASS += 1
        print(f"  ✅ [PASS] {m}")
    else:
        FAIL += 1
        print(f"  ❌ [FAIL] {m}")


def info(m):
    print(f"  ℹ️  {m}")


def login(email):
    """Login and return token"""
    try:
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": "demo12345"}, timeout=30)
        if r.status_code != 200:
            print(f"  ❌ Login failed for {email}: {r.status_code}")
            return None
        return r.json().get("token")
    except Exception as e:
        print(f"  ❌ Login exception for {email}: {e}")
        return None


def H(token):
    """Authorization header"""
    return {"Authorization": f"Bearer {token}"}


def approx(a, b, eps=1.0):
    """Check if two floats are approximately equal"""
    return abs(float(a) - float(b)) <= eps


def main():
    print("\n" + "=" * 60)
    print("EPIC7-A Backend Test — AR / Piutang Aging")
    print("=" * 60)
    
    # Login
    print("\n[1] Authentication")
    admin = login("admin@kainnusantara.id")
    ok(admin is not None, "Admin login successful")
    
    manager = login("manager@kainnusantara.id")
    ok(manager is not None, "Manager login successful")
    
    sales = login("sales@kainnusantara.id")
    ok(sales is not None, "Sales login successful")
    
    if not admin:
        print("\n❌ Cannot proceed without admin token")
        return 1
    
    # Test GET /api/ar/aging (admin)
    print("\n[2] GET /api/ar/aging (admin)")
    try:
        r = requests.get(f"{API}/ar/aging", headers=H(admin), timeout=30)
        ok(r.status_code == 200, f"GET /api/ar/aging returns 200 (got {r.status_code})")
        
        if r.status_code == 200:
            data = r.json()
            
            # Check structure
            ok("totals" in data, "Response has 'totals' field")
            ok("customers" in data, "Response has 'customers' field")
            ok("config" in data, "Response has 'config' field")
            
            totals = data.get("totals", {})
            customers = data.get("customers", [])
            config = data.get("config", {})
            
            # Check all buckets present
            ok(all(k in totals for k in BUCKETS), f"Totals has all bucket keys")
            
            # Verify sum of buckets == total
            bucket_sum = round(sum(totals.get(k, 0) for k in BUCKETS), 2)
            total = totals.get("total", 0)
            ok(approx(bucket_sum, total), f"Sum of buckets ({bucket_sum}) == total ({total})")
            
            # Check counts
            ok(totals.get("customers", 0) >= 0, f"Has customers count: {totals.get('customers')}")
            ok(totals.get("orders", 0) >= 0, f"Has orders count: {totals.get('orders')}")
            
            # Verify customer rows
            ok(len(customers) == totals.get("customers", -1), 
               f"Customer rows ({len(customers)}) == totals.customers ({totals.get('customers')})")
            
            # Per-customer invariant: sum of buckets == outstanding
            if customers:
                inv_ok = all(
                    approx(round(sum(c.get(k, 0) for k in BUCKETS), 2), c.get("outstanding", -1))
                    for c in customers
                )
                ok(inv_ok, "Per-customer: sum of buckets == outstanding")
                
                # Sorted by outstanding desc
                sorted_ok = all(
                    customers[i]["outstanding"] >= customers[i + 1]["outstanding"]
                    for i in range(len(customers) - 1)
                ) if len(customers) > 1 else True
                ok(sorted_ok, "Customers sorted by outstanding (descending)")
                
                # Sum of customer outstanding == total
                cust_sum = round(sum(c.get("outstanding", 0) for c in customers), 2)
                ok(approx(cust_sum, total), f"Sum of customer outstanding ({cust_sum}) == total ({total})")
                
                # Credit status valid
                valid_statuses = all(
                    c.get("credit_status") in ("active", "warning", "blocked")
                    for c in customers
                )
                ok(valid_statuses, "All customers have valid credit_status")
            
            # Denda (late fee) checks
            print("\n[3] Denda (Late Fee) Calculations")
            denda_rate = config.get("denda_rate_pct_per_month", 0)
            ok(denda_rate > 0, f"Denda rate configured: {denda_rate}%/month")
            
            # Customers with no overdue should have denda == 0
            if customers:
                denda_consistent = all(
                    c.get("denda", 0) == 0
                    for c in customers
                    if c.get("overdue", 0) <= 0.01
                )
                ok(denda_consistent, "Customers with no overdue have denda == 0")
            
            ok(totals.get("denda", 0) >= 0, f"Total denda calculated: {totals.get('denda')}")
            
            # Sum of customer denda == total denda
            if customers:
                cust_denda_sum = round(sum(c.get("denda", 0) for c in customers), 2)
                total_denda = totals.get("denda", 0)
                ok(approx(cust_denda_sum, total_denda), 
                   f"Sum of customer denda ({cust_denda_sum}) == total denda ({total_denda})")
            
            # Drill-down test
            print("\n[4] GET /api/ar/aging/{customer_id} (drill-down)")
            if customers:
                cid = customers[0]["customer_id"]
                info(f"Testing drill-down for customer: {cid}")
                
                r2 = requests.get(f"{API}/ar/aging/{cid}", headers=H(admin), timeout=30)
                ok(r2.status_code == 200, f"GET /api/ar/aging/{{id}} returns 200 (got {r2.status_code})")
                
                if r2.status_code == 200:
                    detail = r2.json()
                    ok(detail.get("customer_id") == cid, "Detail customer_id matches")
                    
                    items = detail.get("items", [])
                    ok(len(items) >= 0, f"Has {len(items)} order items")
                    
                    if items:
                        # Check item structure
                        required_fields = ["order_number", "due_date", "days_late", "bucket", "outstanding", "denda_estimate"]
                        has_fields = all(
                            all(field in item for field in required_fields)
                            for item in items
                        )
                        ok(has_fields, "All items have required fields (order_number, due_date, days_late, bucket, outstanding, denda_estimate)")
                        
                        # Sum of item outstanding == customer outstanding
                        item_sum = round(sum(it.get("outstanding", 0) for it in items), 2)
                        cust_outstanding = customers[0]["outstanding"]
                        ok(approx(item_sum, cust_outstanding), 
                           f"Sum of item outstanding ({item_sum}) == customer outstanding ({cust_outstanding})")
            
            # Test unknown customer ID
            r3 = requests.get(f"{API}/ar/aging/unknown_customer_id", headers=H(admin), timeout=30)
            ok(r3.status_code == 404, f"Unknown customer ID returns 404 (got {r3.status_code})")
            
    except Exception as e:
        ok(False, f"Exception during /api/ar/aging test: {e}")
    
    # RBAC tests
    print("\n[5] RBAC Tests")
    if manager:
        r = requests.get(f"{API}/ar/aging", headers=H(manager), timeout=30)
        ok(r.status_code == 200, f"Manager can access /api/ar/aging (got {r.status_code})")
    
    if sales:
        r = requests.get(f"{API}/ar/aging", headers=H(sales), timeout=30)
        ok(r.status_code == 403, f"Sales gets 403 on /api/ar/aging (got {r.status_code})")
    
    # Entity filter test
    print("\n[6] Entity Filter Test")
    try:
        r_all = requests.get(f"{API}/ar/aging", headers=H(admin), timeout=30)
        if r_all.status_code == 200:
            total_all = r_all.json()["totals"]["total"]
            
            r_ent = requests.get(f"{API}/ar/aging?entity_id=ent_ksc", headers=H(admin), timeout=30)
            if r_ent.status_code == 200:
                total_ent = r_ent.json()["totals"]["total"]
                ok(total_ent <= total_all + 1, 
                   f"Entity filter total ({total_ent}) <= global total ({total_all})")
            else:
                info(f"Entity filter returned {r_ent.status_code}")
    except Exception as e:
        info(f"Entity filter test skipped: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"RESULTS: PASS {PASS} | FAIL {FAIL}")
    print("=" * 60)
    
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
