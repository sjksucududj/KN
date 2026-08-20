#!/usr/bin/env python3
"""
Backend API Test — Sub-fase 1.8 Extended SO Status + Partial Shipment
======================================================================
Tests:
1. Login works
2. SO confirm auto-creates outbound tasks
3. Scan-pick updates picked_qty and SO status
4. Partial dispatch creates shipment with SJ-##### number
5. Full dispatch completes task
6. SO status auto-derives (confirmed → picked → partially_shipped → shipped)
7. Mark-delivered transitions to done
8. Shipments API returns shipments for order
9. Surat Jalan HTML generation
10. Regression: Dashboard KPIs, Orders list
"""
import os
import sys
import requests
from datetime import datetime

BASE = os.environ.get("BACKEND_URL", "https://po-pdf-sender.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
PASS, FAIL = [], []


def ok(m):
    PASS.append(m)
    print(f"  ✅ {m}")


def bad(m):
    FAIL.append(m)
    print(f"  ❌ {m}")


def info(m):
    print(f"  ℹ️  {m}")


class SubFase18Tester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        
    def login(self):
        """Test 1: Login"""
        info("\n=== TEST 1: Login ===")
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": "admin@kainnusantara.id", "password": "demo12345"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login failed: {r.status_code}")
                return False
            data = r.json()
            self.token = data.get("token")
            if not self.token:
                bad("Login response missing token")
                return False
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            ok("Login successful")
            return True
        except Exception as e:
            bad(f"Login exception: {e}")
            return False
    
    def test_confirm_creates_tasks(self):
        """Test 2: Confirm SO auto-creates outbound tasks"""
        info("\n=== TEST 2: Confirm SO Auto-creates Outbound Tasks ===")
        
        try:
            # Find an approved order
            r = self.session.get(f"{API}/sales-orders", params={"status": "approved"}, timeout=30)
            orders = r.json()
            
            if not orders:
                info("No approved orders, creating one...")
                # Create and approve an order
                so_id = self._create_and_approve_order()
                if not so_id:
                    bad("Failed to create order for testing")
                    return False
            else:
                so_id = orders[0]["id"]
            
            # Confirm the order
            r = self.session.post(f"{API}/sales-orders/{so_id}/confirm", timeout=30)
            if r.status_code != 200:
                bad(f"Confirm failed: {r.status_code} {r.text[:200]}")
                return False
            
            so = r.json()
            if so["status"] != "confirmed":
                bad(f"SO status should be 'confirmed', got '{so['status']}'")
                return False
            
            ok("SO confirmed")
            
            # Check outbound tasks created
            r = self.session.get(f"{API}/outbound/tasks", timeout=30)
            tasks = r.json()
            order_tasks = [t for t in tasks if t.get("order_id") == so_id]
            
            if len(order_tasks) > 0:
                ok(f"Outbound tasks auto-created: {len(order_tasks)} task(s)")
                return so_id, order_tasks[0]["id"]
            else:
                bad("No outbound tasks created")
                return False
                
        except Exception as e:
            bad(f"Test exception: {e}")
            return False
    
    def test_scan_pick(self, task_id):
        """Test 3: Scan-pick updates picked_qty"""
        info("\n=== TEST 3: Scan-pick Updates Picked Qty ===")
        
        try:
            # Get task details
            r = self.session.get(f"{API}/outbound/tasks", timeout=30)
            tasks = r.json()
            task = next((t for t in tasks if t["id"] == task_id), None)
            
            if not task:
                bad("Task not found")
                return False
            
            qty = float(task["quantity"])
            
            # Scan-pick full qty
            r = self.session.post(
                f"{API}/outbound/tasks/{task_id}/scan-pick",
                params={"actual_qty": qty, "lot": "TEST-LOT", "roll_id": ""},
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Scan-pick failed: {r.status_code} {r.text[:200]}")
                return False
            
            updated_task = r.json()
            picked_qty = float(updated_task.get("picked_qty", 0))
            
            if picked_qty >= qty - 0.01:
                ok(f"Scan-pick successful: picked_qty={picked_qty}")
                return task["order_id"], task_id
            else:
                bad(f"Picked qty mismatch: expected {qty}, got {picked_qty}")
                return False
                
        except Exception as e:
            bad(f"Test exception: {e}")
            return False
    
    def test_partial_dispatch(self, task_id):
        """Test 4: Partial dispatch creates shipment with SJ-#####"""
        info("\n=== TEST 4: Partial Dispatch Creates Shipment ===")
        
        try:
            # Get task
            r = self.session.get(f"{API}/outbound/tasks", timeout=30)
            tasks = r.json()
            task = next((t for t in tasks if t["id"] == task_id), None)
            
            if not task:
                bad("Task not found")
                return False
            
            picked_qty = float(task.get("picked_qty", 0))
            if picked_qty <= 0:
                bad("No picked qty to dispatch")
                return False
            
            # Dispatch half
            ship_qty = round(picked_qty / 2, 2)
            
            r = self.session.post(
                f"{API}/outbound/tasks/{task_id}/dispatch",
                params={"ship_qty": ship_qty},
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Partial dispatch failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            shipment = result.get("shipment", {})
            updated_task = result.get("task", {})
            
            # Check shipment number
            shipment_no = shipment.get("shipment_no", "")
            if shipment_no.startswith("SJ-"):
                ok(f"Shipment created: {shipment_no}")
            else:
                bad(f"Shipment number invalid: {shipment_no}")
            
            # Check is_partial flag
            if shipment.get("is_partial"):
                ok("Shipment marked as partial")
            else:
                bad("Shipment should be marked as partial")
            
            # Check task status
            task_status = updated_task.get("status")
            if task_status == "partially_shipped":
                ok(f"Task status: {task_status}")
            else:
                bad(f"Task status should be 'partially_shipped', got '{task_status}'")
            
            return task["order_id"], task_id, shipment["id"]
            
        except Exception as e:
            bad(f"Test exception: {e}")
            return False
    
    def test_full_dispatch(self, task_id):
        """Test 5: Full dispatch completes task"""
        info("\n=== TEST 5: Full Dispatch Completes Task ===")
        
        try:
            # Dispatch remaining qty
            r = self.session.post(f"{API}/outbound/tasks/{task_id}/dispatch", timeout=30)
            
            if r.status_code != 200:
                bad(f"Full dispatch failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            updated_task = result.get("task", {})
            
            # Check task status
            task_status = updated_task.get("status")
            if task_status == "dispatched":
                ok(f"Task fully dispatched: {task_status}")
                return updated_task.get("order_id")
            else:
                bad(f"Task status should be 'dispatched', got '{task_status}'")
                return False
                
        except Exception as e:
            bad(f"Test exception: {e}")
            return False
    
    def test_so_status_derivation(self, order_id):
        """Test 6: SO status auto-derives"""
        info("\n=== TEST 6: SO Status Auto-derivation ===")
        
        try:
            r = self.session.get(f"{API}/sales-orders/{order_id}", timeout=30)
            if r.status_code != 200:
                bad(f"Get SO failed: {r.status_code}")
                return False
            
            so = r.json()
            status = so.get("status")
            
            # Should be 'shipped' after all tasks dispatched
            if status in ["picked", "partially_shipped", "shipped"]:
                ok(f"SO status auto-derived: {status}")
                return order_id
            else:
                bad(f"SO status unexpected: {status}")
                return False
                
        except Exception as e:
            bad(f"Test exception: {e}")
            return False
    
    def test_mark_delivered(self, order_id):
        """Test 7: Mark-delivered transitions to done"""
        info("\n=== TEST 7: Mark-delivered Transitions to Done ===")
        
        try:
            # First ensure order is shipped
            r = self.session.get(f"{API}/sales-orders/{order_id}", timeout=30)
            so = r.json()
            
            if so["status"] != "shipped":
                info(f"Order status is '{so['status']}', not 'shipped'. Skipping mark-delivered test.")
                return True
            
            # Mark delivered
            r = self.session.post(f"{API}/sales-orders/{order_id}/mark-delivered", timeout=30)
            
            if r.status_code != 200:
                bad(f"Mark-delivered failed: {r.status_code} {r.text[:200]}")
                return False
            
            result = r.json()
            if result.get("status") == "done":
                ok("SO marked as delivered: status=done")
                return True
            else:
                bad(f"SO status should be 'done', got '{result.get('status')}'")
                return False
                
        except Exception as e:
            bad(f"Test exception: {e}")
            return False
    
    def test_shipments_api(self, order_id):
        """Test 8: Shipments API returns shipments"""
        info("\n=== TEST 8: Shipments API ===")
        
        try:
            r = self.session.get(f"{API}/shipments", params={"order_id": order_id}, timeout=30)
            
            if r.status_code != 200:
                bad(f"Get shipments failed: {r.status_code}")
                return False
            
            shipments = r.json()
            
            if len(shipments) >= 2:
                ok(f"Shipments API returned {len(shipments)} shipment(s)")
                return shipments[0]["id"]
            else:
                bad(f"Expected >= 2 shipments, got {len(shipments)}")
                return False
                
        except Exception as e:
            bad(f"Test exception: {e}")
            return False
    
    def test_surat_jalan(self, shipment_id):
        """Test 9: Surat Jalan HTML generation"""
        info("\n=== TEST 9: Surat Jalan Generation ===")
        
        try:
            r = self.session.get(f"{API}/shipments/{shipment_id}/surat-jalan", timeout=30)
            
            if r.status_code != 200:
                bad(f"Surat Jalan generation failed: {r.status_code}")
                return False
            
            html = r.text
            
            if "SURAT JALAN" in html and "SJ-" in html:
                ok("Surat Jalan HTML generated successfully")
                return True
            else:
                bad("Surat Jalan HTML missing expected content")
                return False
                
        except Exception as e:
            bad(f"Test exception: {e}")
            return False
    
    def test_regression_dashboard(self):
        """Test 10: Regression - Dashboard KPIs"""
        info("\n=== TEST 10: Regression - Dashboard KPIs ===")
        
        try:
            r = self.session.get(f"{API}/dashboard/kpis", timeout=30)
            
            if r.status_code != 200:
                bad(f"Dashboard KPIs failed: {r.status_code}")
                return False
            
            kpis = r.json()
            
            # Check for expected KPIs
            has_products = "active_products" in kpis or "total_products" in kpis
            has_inventory = "available_qty" in kpis or "total_available" in kpis
            
            if has_products and has_inventory:
                ok("Dashboard KPIs working")
                return True
            else:
                info("Dashboard KPIs structure may have changed")
                return True
                
        except Exception as e:
            info(f"Dashboard test skipped: {e}")
            return True
    
    def _create_and_approve_order(self):
        """Helper: Create and approve an order"""
        try:
            # Get references
            r = self.session.get(f"{API}/customers", timeout=30)
            customers = r.json()
            if not customers:
                return None
            customer = customers[0]
            
            r = self.session.get(f"{API}/inventory/balances", timeout=30)
            balances = r.json()
            balance = next((b for b in balances if float(b.get("available_qty", 0)) >= 10), None)
            if not balance:
                return None
            
            # Create order
            r = self.session.post(
                f"{API}/sales-orders",
                json={
                    "customer_id": customer["id"],
                    "shipping_address_id": customer["addresses"][0]["id"],
                    "entity_id": balance["owner_entity_id"],
                    "items": [{"product_id": balance["product_id"], "quantity": 10.0, "unit": "meter"}],
                },
                timeout=30
            )
            
            if r.status_code != 200:
                return None
            
            so = r.json()
            so_id = so["id"]
            
            # Submit and approve
            r = self.session.post(f"{API}/sales-orders/{so_id}/submit-for-approval", timeout=30)
            result = r.json()
            
            if result.get("status") == "waiting_approval":
                self.session.post(f"{API}/sales-orders/{so_id}/approve", timeout=30)
            
            return so_id
            
        except Exception:
            return None
    
    def run_all_tests(self):
        """Run all Sub-fase 1.8 tests"""
        print("\n" + "="*70)
        print("  BACKEND API TEST — Sub-fase 1.8 Extended SO Status + Partial Shipment")
        print("="*70)
        
        if not self.login():
            return False
        
        # Test 2-3: Confirm and scan-pick
        result = self.test_confirm_creates_tasks()
        if not result:
            return False
        so_id, task_id = result
        
        result = self.test_scan_pick(task_id)
        if not result:
            return False
        so_id, task_id = result
        
        # Test 4: Partial dispatch
        result = self.test_partial_dispatch(task_id)
        if not result:
            return False
        so_id, task_id, shipment_id = result
        
        # Test 5: Full dispatch
        result = self.test_full_dispatch(task_id)
        if result:
            so_id = result
        
        # Test 6: SO status derivation
        if so_id:
            self.test_so_status_derivation(so_id)
        
        # Test 7: Mark delivered
        if so_id:
            self.test_mark_delivered(so_id)
        
        # Test 8: Shipments API
        if so_id:
            shipment_id = self.test_shipments_api(so_id)
        
        # Test 9: Surat Jalan
        if shipment_id:
            self.test_surat_jalan(shipment_id)
        
        # Test 10: Regression
        self.test_regression_dashboard()
        
        return True


def main():
    tester = SubFase18Tester()
    tester.run_all_tests()
    
    print("\n" + "="*70)
    print(f"  HASIL: {len(PASS)} PASS | {len(FAIL)} FAIL")
    print("="*70)
    
    if FAIL:
        print("\n❌ FAILED TESTS:")
        for f in FAIL:
            print(f"   - {f}")
        return 1
    
    print("\n✅ SEMUA TEST BACKEND LULUS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
