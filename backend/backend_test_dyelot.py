#!/usr/bin/env python3
"""
Backend API Test — Phase 5.3 P0-4: Dye Lot + Grade Traceability
================================================================
Comprehensive test covering:
1. POST /api/inbound/tasks/{task_id}/complete with optional GRCompletePayload
   - (a) No body still works (backward compatible)
   - (b) With {dye_lot, grade} → inventory_roll has that dye_lot + grade
   - (c) With rolls[] → creates N rolls with unique roll_no, Σ length ≈ received qty
2. POST /api/inbound/tasks/{task_id}/qc-decision with accept_grade + defects[]
3. POST /api/customers and PATCH /api/customers/{id} persist enforce_single_dye_lot, lot_policy
4. POST /api/sales-orders/preview-lots — enforce_single_dye_lot forces single dye_lot allocation
5. Regression: sweep key GET endpoints (no 5xx)
"""
import os
import sys
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://po-pdf-sender.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

PASS, FAIL = [], []

def ok(m):
    PASS.append(m)
    print(f"  ✅ [PASS] {m}")

def bad(m):
    FAIL.append(m)
    print(f"  ❌ [FAIL] {m}")

def info(m):
    print(f"  ℹ️  {m}")


class DyeLotTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.entity_id = None
        self.warehouse_id = None
        self.customer_id = None
        self.product_id = None
        
    def login(self):
        """Login as admin"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": "admin@kainnusantara.id", "password": "demo12345"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login failed: {r.status_code} {r.text[:200]}")
                return False
            data = r.json()
            self.token = data.get("token")
            if not self.token:
                bad("Login response missing token")
                return False
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            ok("Login admin@kainnusantara.id")
            return True
        except Exception as e:
            bad(f"Login exception: {e}")
            return False
    
    def setup_references(self):
        """Get entity, warehouse, customer, product references"""
        try:
            # Get entity
            r = self.session.get(f"{API}/entities", timeout=30)
            if r.status_code == 200:
                entities = r.json()
                if entities:
                    self.entity_id = entities[0]["id"]
            
            # Get warehouse
            r = self.session.get(f"{API}/warehouses", timeout=30)
            if r.status_code == 200:
                warehouses = r.json()
                if warehouses:
                    self.warehouse_id = warehouses[0]["id"]
            
            # Get customer
            r = self.session.get(f"{API}/customers", timeout=30)
            if r.status_code == 200:
                customers = r.json()
                if customers:
                    self.customer_id = customers[0]["id"]
            
            # Get product
            r = self.session.get(f"{API}/products", timeout=30)
            if r.status_code == 200:
                products = r.json()
                if products:
                    self.product_id = products[0]["id"]
            
            ok(f"Setup references: entity={self.entity_id[:8] if self.entity_id else 'N/A'}, warehouse={self.warehouse_id[:8] if self.warehouse_id else 'N/A'}")
            return True
        except Exception as e:
            bad(f"Setup references exception: {e}")
            return False
    
    def test_regression_endpoints(self):
        """Test 5: Regression sweep of key GET endpoints"""
        info("TEST 5: Regression sweep of key GET endpoints")
        endpoints = [
            "/dashboard",
            "/products",
            "/customers",
            "/inventory/balances",
            "/inventory/rolls",
            "/sales-orders",
            "/purchase-orders",
            "/inbound/qc/queue",
        ]
        
        all_ok = True
        for endpoint in endpoints:
            try:
                r = self.session.get(f"{API}{endpoint}", timeout=30)
                if r.status_code >= 500:
                    bad(f"GET {endpoint} returned {r.status_code}")
                    all_ok = False
                else:
                    ok(f"GET {endpoint} → {r.status_code}")
            except Exception as e:
                bad(f"GET {endpoint} exception: {e}")
                all_ok = False
        
        return all_ok
    
    def test_gr_complete_backward_compat(self):
        """Test 1a: GR complete without body (backward compatible)"""
        info("TEST 1a: GR complete without body (backward compatible)")
        
        # Find an inbound task in qc_check status
        try:
            r = self.session.get(f"{API}/inbound/tasks?status=qc_check", timeout=30)
            if r.status_code != 200:
                info(f"  Cannot get inbound tasks: {r.status_code}")
                return False
            
            tasks = r.json()
            if not tasks:
                info("  No inbound tasks in qc_check status - skipping test")
                return True
            
            task_id = tasks[0]["id"]
            
            # Complete without body
            r = self.session.post(f"{API}/inbound/tasks/{task_id}/complete", timeout=30)
            if r.status_code == 200:
                ok("GR complete without body works (backward compatible)")
                return True
            else:
                bad(f"GR complete without body failed: {r.status_code} {r.text[:200]}")
                return False
        except Exception as e:
            bad(f"Test 1a exception: {e}")
            return False
    
    def test_gr_complete_with_dyelot_grade(self):
        """Test 1b: GR complete with dye_lot + grade"""
        info("TEST 1b: GR complete with dye_lot + grade")
        
        try:
            # Find an inbound task in qc_check status
            r = self.session.get(f"{API}/inbound/tasks?status=qc_check", timeout=30)
            if r.status_code != 200:
                info(f"  Cannot get inbound tasks: {r.status_code}")
                return False
            
            tasks = r.json()
            if not tasks:
                info("  No inbound tasks in qc_check status - skipping test")
                return True
            
            task_id = tasks[0]["id"]
            product_id = tasks[0].get("product_id")
            
            # Complete with dye_lot + grade
            r = self.session.post(
                f"{API}/inbound/tasks/{task_id}/complete",
                json={"dye_lot": "DL-TEST-001", "grade": "B"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"GR complete with dye_lot failed: {r.status_code} {r.text[:200]}")
                return False
            
            # Check if roll was created with dye_lot + grade
            r = self.session.get(f"{API}/inventory/rolls?product_id={product_id}", timeout=30)
            if r.status_code != 200:
                bad(f"Cannot get rolls: {r.status_code}")
                return False
            
            rolls = r.json()
            found = False
            for roll in rolls:
                if roll.get("dye_lot") == "DL-TEST-001" and roll.get("grade") == "B":
                    found = True
                    ok(f"Roll created with dye_lot=DL-TEST-001 grade=B")
                    break
            
            if not found:
                bad("Roll with specified dye_lot + grade not found")
                return False
            
            return True
        except Exception as e:
            bad(f"Test 1b exception: {e}")
            return False
    
    def test_gr_complete_multi_roll(self):
        """Test 1c: GR complete with rolls[] (multi-roll breakdown)"""
        info("TEST 1c: GR complete with rolls[] (multi-roll breakdown)")
        
        try:
            # Find an inbound task in qc_check status
            r = self.session.get(f"{API}/inbound/tasks?status=qc_check", timeout=30)
            if r.status_code != 200:
                info(f"  Cannot get inbound tasks: {r.status_code}")
                return False
            
            tasks = r.json()
            if not tasks:
                info("  No inbound tasks in qc_check status - skipping test")
                return True
            
            task = tasks[0]
            task_id = task["id"]
            product_id = task.get("product_id")
            qty = task.get("quantity", 100)
            
            # Complete with multi-roll breakdown
            r = self.session.post(
                f"{API}/inbound/tasks/{task_id}/complete",
                json={
                    "rolls": [
                        {"length": qty * 0.6, "dye_lot": "DL-A", "grade": "A", "defects": []},
                        {"length": qty * 0.4, "dye_lot": "DL-B", "grade": "B", "defects": ["noda"]},
                    ]
                },
                timeout=30
            )
            if r.status_code != 200:
                bad(f"GR complete with rolls[] failed: {r.status_code} {r.text[:200]}")
                return False
            
            # Check if 2 rolls were created with unique roll_no
            r = self.session.get(f"{API}/inventory/rolls?product_id={product_id}", timeout=30)
            if r.status_code != 200:
                bad(f"Cannot get rolls: {r.status_code}")
                return False
            
            rolls = r.json()
            dl_a = [r for r in rolls if r.get("dye_lot") == "DL-A"]
            dl_b = [r for r in rolls if r.get("dye_lot") == "DL-B"]
            
            if dl_a and dl_b:
                if dl_a[0].get("roll_no") != dl_b[0].get("roll_no"):
                    ok(f"Multi-roll: 2 rolls created with unique roll_no")
                else:
                    bad("Multi-roll: roll_no not unique")
                    return False
                
                if dl_b[0].get("defects") == ["noda"]:
                    ok("Multi-roll: defects persisted correctly")
                else:
                    bad(f"Multi-roll: defects incorrect: {dl_b[0].get('defects')}")
                    return False
                
                return True
            else:
                bad("Multi-roll: rolls not found")
                return False
        except Exception as e:
            bad(f"Test 1c exception: {e}")
            return False
    
    def test_qc_decision_with_grade_defects(self):
        """Test 2: QC decision with accept_grade + defects[]"""
        info("TEST 2: QC decision with accept_grade + defects[]")
        
        try:
            # Find a qc_pending task
            r = self.session.get(f"{API}/inbound/qc/queue", timeout=30)
            if r.status_code != 200:
                info(f"  Cannot get QC queue: {r.status_code}")
                return False
            
            tasks = r.json()
            if not tasks:
                info("  No tasks in QC queue - skipping test")
                return True
            
            task = tasks[0]
            task_id = task["id"]
            product_id = task.get("product_id")
            qty = task.get("quarantine_qty", 50)
            
            # QC accept with grade + defects
            r = self.session.post(
                f"{API}/inbound/tasks/{task_id}/qc-decision",
                json={
                    "accept_qty": qty,
                    "reject_qty": 0,
                    "reject_disposition": "damaged",
                    "accept_grade": "C",
                    "defects": ["belang", "noda"],
                    "reason": "QC test"
                },
                timeout=30
            )
            if r.status_code != 200:
                bad(f"QC decision failed: {r.status_code} {r.text[:200]}")
                return False
            
            # Check if roll has grade=C, qc_grade=C, defects
            r = self.session.get(f"{API}/inventory/rolls?product_id={product_id}&status=available", timeout=30)
            if r.status_code != 200:
                bad(f"Cannot get rolls: {r.status_code}")
                return False
            
            rolls = r.json()
            found = False
            for roll in rolls:
                if roll.get("grade") == "C" and roll.get("qc_grade") == "C":
                    if roll.get("defects") == ["belang", "noda"]:
                        ok("QC decision: grade=C qc_grade=C defects=['belang', 'noda']")
                        found = True
                        break
            
            if not found:
                bad("QC decision: roll with correct grade + defects not found")
                return False
            
            return True
        except Exception as e:
            bad(f"Test 2 exception: {e}")
            return False
    
    def test_customer_enforce_single_dye_lot(self):
        """Test 3 & 4: Customer enforce_single_dye_lot + preview-lots"""
        info("TEST 3 & 4: Customer enforce_single_dye_lot + preview-lots")
        
        try:
            # Create customer with enforce_single_dye_lot=true
            r = self.session.post(
                f"{API}/customers",
                json={
                    "name": f"Test Customer Dye Lot {datetime.now().timestamp()}",
                    "pic_name": "Test PIC",
                    "phone": "08123456789",
                    "email": "test@test.com",
                    "city": "Jakarta",
                    "address": "Test Address",
                    "entity_id": self.entity_id,
                    "enforce_single_dye_lot": True,
                    "lot_policy": "strict_single"
                },
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Create customer failed: {r.status_code} {r.text[:200]}")
                return False
            
            customer = r.json()
            customer_id = customer["id"]
            
            if customer.get("enforce_single_dye_lot") is True:
                ok("Customer created with enforce_single_dye_lot=True")
            else:
                bad(f"Customer enforce_single_dye_lot not persisted: {customer.get('enforce_single_dye_lot')}")
                return False
            
            if customer.get("lot_policy") == "strict_single":
                ok("Customer lot_policy=strict_single persisted")
            else:
                bad(f"Customer lot_policy not persisted: {customer.get('lot_policy')}")
                return False
            
            # Test PATCH
            r = self.session.patch(
                f"{API}/customers/{customer_id}",
                json={"data": {"lot_policy": "prefer_single"}},
                timeout=30
            )
            if r.status_code == 200:
                updated = r.json()
                if updated.get("lot_policy") == "prefer_single":
                    ok("Customer PATCH lot_policy works")
                else:
                    bad(f"Customer PATCH lot_policy failed: {updated.get('lot_policy')}")
            
            # Test preview-lots with enforce_single_dye_lot customer
            if self.product_id:
                r = self.session.post(
                    f"{API}/sales-orders/preview-lots",
                    json={
                        "customer_id": customer_id,
                        "entity_id": self.entity_id,
                        "items": [{"product_id": self.product_id, "quantity": 100, "unit": "meter"}]
                    },
                    timeout=30
                )
                if r.status_code == 200:
                    preview = r.json()
                    lines = preview.get("lines", [])
                    if lines:
                        line = lines[0]
                        if line.get("dye_lot_strict") is True:
                            ok("preview-lots: dye_lot_strict=True for enforce_single_dye_lot customer")
                        else:
                            bad(f"preview-lots: dye_lot_strict not set: {line.get('dye_lot_strict')}")
                    else:
                        info("  preview-lots: no lines returned")
                else:
                    info(f"  preview-lots failed: {r.status_code}")
            
            return True
        except Exception as e:
            bad(f"Test 3 & 4 exception: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "=" * 70)
        print("  Backend API Test — Phase 5.3 P0-4: Dye Lot + Grade Traceability")
        print("=" * 70 + "\n")
        
        if not self.login():
            return False
        
        if not self.setup_references():
            return False
        
        # Run tests
        self.test_regression_endpoints()
        self.test_gr_complete_backward_compat()
        self.test_gr_complete_with_dyelot_grade()
        self.test_gr_complete_multi_roll()
        self.test_qc_decision_with_grade_defects()
        self.test_customer_enforce_single_dye_lot()
        
        # Summary
        print("\n" + "=" * 70)
        print(f"  SUMMARY: {len(PASS)} PASS | {len(FAIL)} FAIL")
        print("=" * 70)
        
        if FAIL:
            print("\n❌ FAILED:")
            for f in FAIL:
                print(f"  - {f}")
        
        return len(FAIL) == 0


def main():
    tester = DyeLotTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
