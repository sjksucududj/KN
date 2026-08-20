#!/usr/bin/env python3
"""Backend API Testing for FASE G-2 — Payment Plans & Penalties"""
import requests
import sys

BASE_URL = "https://jasad-dokumen.preview.emergentagent.com/api"
CREDENTIALS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "manager": {"email": "manager@kainnusantara.id", "password": "demo12345"},
    "sales": {"email": "sales@kainnusantara.id", "password": "demo12345"},
    "warehouse": {"email": "warehouse@kainnusantara.id", "password": "demo12345"},
}

class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tokens = {}
        
    def login(self, role):
        if role in self.tokens:
            return self.tokens[role]
        cred = CREDENTIALS[role]
        r = requests.post(f"{BASE_URL}/auth/login", json=cred, timeout=20)
        if r.status_code == 200:
            token = r.json().get("token")
            self.tokens[role] = token
            return token
        raise Exception(f"Login failed for {role}: {r.status_code}")
    
    def headers(self, role):
        return {"Authorization": f"Bearer {self.login(role)}", "Content-Type": "application/json"}
    
    def test(self, name, condition, detail=""):
        if condition:
            self.passed += 1
            print(f"✓ {name}" + (f" — {detail}" if detail else ""))
        else:
            self.failed += 1
            print(f"✗ {name}" + (f" — {detail}" if detail else ""))
        return condition
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*70}")
        print(f"PASS {self.passed} / FAIL {self.failed} (total {total})")
        print(f"{'='*70}")
        return 0 if self.failed == 0 else 1

def main():
    runner = TestRunner()
    
    print("\n" + "="*70)
    print("BACKEND API TESTS — FASE G-2 Payment Plans & Penalties")
    print("="*70 + "\n")
    
    # TEST 1: Metadata endpoint
    print("TEST 1 — GET /api/payment-plans/meta")
    try:
        r = requests.get(f"{BASE_URL}/payment-plans/meta", headers=runner.headers("admin"), timeout=30)
        meta = r.json() if r.status_code == 200 else {}
        runner.test("Meta endpoint returns 200", r.status_code == 200)
        runner.test("Modes available", len(meta.get("modes", [])) == 4, "dp_installment, milestone, net, custom")
        runner.test("Due rules available", len(meta.get("due_rules", [])) >= 4)
        runner.test("Penalty reasons available", len(meta.get("reasons", [])) >= 1, f"{len(meta.get('reasons', []))} reasons")
        runner.test("Plan policy present", "plan_policy" in meta)
        runner.test("Penalty policy present", "penalty_policy" in meta)
    except Exception as e:
        runner.test("Meta endpoint accessible", False, str(e))
    
    # TEST 2: Get existing sales orders
    print("\nTEST 2 — Find existing sales order for testing")
    try:
        r = requests.get(f"{BASE_URL}/sales-orders", headers=runner.headers("admin"), params={"limit": 10}, timeout=30)
        orders = r.json() if r.status_code == 200 else {}
        order_list = orders if isinstance(orders, list) else orders.get("items", [])
        runner.test("Can fetch sales orders", len(order_list) > 0, f"{len(order_list)} orders found")
        
        if order_list:
            so = order_list[0]
            so_id = so.get("id")
            total = float(so.get("grand_total") or so.get("total_amount") or 0)
            runner.test("SO has valid total", total > 0, f"SO {so.get('number')} = Rp {total:,.0f}")
            
            # TEST 3: Preview payment plan
            print("\nTEST 3 — POST /api/payment-plans/preview")
            r = requests.post(f"{BASE_URL}/payment-plans/preview", headers=runner.headers("admin"), 
                            json={"doc_type": "sales_order", "doc_id": so_id, "mode": "dp_installment",
                                  "dp_percent": 15, "installments": 6, "interval": "monthly"}, timeout=40)
            preview = r.json() if r.status_code == 200 else {}
            runner.test("Preview returns 200", r.status_code == 200)
            runner.test("Preview has 7 lines (DP + 6 installments)", len(preview.get("lines", [])) == 7)
            runner.test("Preview is balanced", preview.get("balanced") is True)
            
            # TEST 4: Get payment plan by document
            print("\nTEST 4 — GET /api/payment-plans/by-doc/sales_order/{so_id}")
            r = requests.get(f"{BASE_URL}/payment-plans/by-doc/sales_order/{so_id}", 
                           headers=runner.headers("admin"), timeout=40)
            by_doc = r.json() if r.status_code == 200 else {}
            runner.test("By-doc endpoint returns 200", r.status_code == 200)
            runner.test("Response has plan/penalties/next_due/overdue keys", 
                       all(k in by_doc for k in ["plan", "penalties", "next_due", "overdue"]))
            
            # TEST 5: List penalties
            print("\nTEST 5 — GET /api/penalties")
            r = requests.get(f"{BASE_URL}/penalties", headers=runner.headers("admin"), timeout=30)
            pen_list = r.json() if r.status_code == 200 else {}
            runner.test("Penalties endpoint returns 200", r.status_code == 200)
            runner.test("Response has items and stats", "items" in pen_list and "stats" in pen_list)
            
            # TEST 6: Filter penalties by status
            print("\nTEST 6 — GET /api/penalties?status=draft")
            r = requests.get(f"{BASE_URL}/penalties", headers=runner.headers("admin"), 
                           params={"status": "draft"}, timeout=30)
            runner.test("Filter by status works", r.status_code == 200)
            
    except Exception as e:
        runner.test("Sales order tests", False, str(e))
    
    # TEST 7: RBAC - Sales role
    print("\nTEST 7 — RBAC: Sales can view but not decide")
    try:
        # Sales can view meta
        r = requests.get(f"{BASE_URL}/payment-plans/meta", headers=runner.headers("sales"), timeout=30)
        runner.test("Sales can GET /payment-plans/meta", r.status_code == 200)
        
        # Sales can view penalties
        r = requests.get(f"{BASE_URL}/penalties", headers=runner.headers("sales"), timeout=30)
        runner.test("Sales can GET /penalties", r.status_code == 200)
        
    except Exception as e:
        runner.test("Sales RBAC tests", False, str(e))
    
    # TEST 8: RBAC - Warehouse role
    print("\nTEST 8 — RBAC: Warehouse gets 403 for payment endpoints")
    try:
        r = requests.get(f"{BASE_URL}/payment-plans/meta", headers=runner.headers("warehouse"), timeout=30)
        runner.test("Warehouse gets 403 for /payment-plans/meta", r.status_code == 403)
        
        r = requests.get(f"{BASE_URL}/penalties", headers=runner.headers("warehouse"), timeout=30)
        runner.test("Warehouse gets 403 for /penalties", r.status_code == 403)
        
    except Exception as e:
        runner.test("Warehouse RBAC tests", False, str(e))
    
    return runner.summary()

if __name__ == "__main__":
    sys.exit(main())
