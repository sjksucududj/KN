#!/usr/bin/env python3
"""
Backend API Testing for Phase F-1 (Receiving with Supplier UOM)
Tests all user stories US-F1 through US-F8 + RBAC + regressions
"""
import requests
import sys
import os
from datetime import datetime

# Get public endpoint from environment
BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
if not BACKEND_URL.startswith("http"):
    BACKEND_URL = f"https://{BACKEND_URL}"
BASE_URL = BACKEND_URL.rstrip("/")
API_URL = f"{BASE_URL}/api"

class APITester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        self.headers = {}

    def login(self, email="admin@kainnusantara.id", password="demo12345"):
        """Login and get token"""
        print(f"\n🔐 Logging in as {email}...")
        try:
            r = requests.post(f"{API_URL}/auth/login", 
                            json={"email": email, "password": password}, 
                            timeout=30)
            if r.status_code == 200:
                data = r.json()
                self.token = data.get("token")
                self.headers = {"Authorization": f"Bearer {self.token}"}
                print(f"✅ Login successful")
                return True
            else:
                print(f"❌ Login failed: {r.status_code} - {r.text[:200]}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False

    def test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        
        url = f"{API_URL}/{endpoint}"
        h = headers or self.headers
        
        try:
            if method == "GET":
                r = requests.get(url, headers=h, timeout=30)
            elif method == "POST":
                r = requests.post(url, json=data, headers=h, timeout=30)
            elif method == "PUT":
                r = requests.put(url, json=data, headers=h, timeout=30)
            else:
                print(f"❌ Unknown method: {method}")
                return False, {}
            
            success = r.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ PASS - Status: {r.status_code}")
                try:
                    return True, r.json()
                except Exception:
                    return True, {}
            else:
                print(f"❌ FAIL - Expected {expected_status}, got {r.status_code}")
                print(f"   Response: {r.text[:300]}")
                return False, {}
        except Exception as e:
            print(f"❌ FAIL - Error: {str(e)}")
            return False, {}

def main():
    print("=" * 80)
    print("  FASE F-1 BACKEND API TESTING")
    print("  Testing Receiving with Supplier UOM")
    print("=" * 80)
    print(f"  Backend URL: {BASE_URL}")
    
    tester = APITester()
    
    # Login as admin
    if not tester.login("admin@kainnusantara.id", "demo12345"):
        print("\n❌ Cannot proceed without login")
        return 1
    
    # Test 1: Get receiving UOM settings (US-F6)
    print("\n" + "="*80)
    print("TEST GROUP 1: Receiving UOM Settings (US-F6)")
    print("="*80)
    
    success, settings = tester.test(
        "Get receiving UOM settings",
        "GET", "receiving/uom-settings", 200
    )
    if success:
        print(f"   Mode: {settings.get('supplier_uom_input_mode')}")
        print(f"   Require supplier item: {settings.get('require_supplier_item_for_supplier_uom')}")
        print(f"   Block over remaining: {settings.get('block_over_remaining')}")
    
    # Test 2: Get inbound tasks
    print("\n" + "="*80)
    print("TEST GROUP 2: Inbound Tasks")
    print("="*80)
    
    success, tasks = tester.test(
        "List inbound tasks",
        "GET", "inbound/tasks", 200
    )
    
    if success and tasks:
        # Find a task with waiting_goods status
        waiting_tasks = [t for t in tasks if t.get("status") == "waiting_goods"]
        if waiting_tasks:
            task = waiting_tasks[0]
            task_id = task.get("id")
            print(f"   Found task: {task_id}")
            print(f"   Product: {task.get('product_name')}")
            print(f"   Expected qty: {task.get('expected_qty')} {task.get('unit')}")
            
            # Test 3: Get UOM options for task (US-F3, US-F4)
            print("\n" + "="*80)
            print("TEST GROUP 3: UOM Options (US-F3, US-F4)")
            print("="*80)
            
            success, uom_opts = tester.test(
                "Get UOM options for task",
                "GET", f"inbound/tasks/{task_id}/uom-options", 200
            )
            if success:
                print(f"   Task UOM: {uom_opts.get('task_uom')}")
                print(f"   Default UOM: {uom_opts.get('default_uom')}")
                print(f"   Remaining: {uom_opts.get('remaining_qty')} {uom_opts.get('task_uom')}")
                print(f"   Options: {[o.get('value') for o in uom_opts.get('options', [])]}")
                
                # Test 4: Preview UOM conversion (US-F2)
                print("\n" + "="*80)
                print("TEST GROUP 4: Preview UOM Conversion (US-F2)")
                print("="*80)
                
                # Try to preview with supplier UOM if available
                supplier_opt = next((o for o in uom_opts.get('options', []) 
                                   if o.get('source') == 'supplier_item'), None)
                if supplier_opt:
                    doc_uom = supplier_opt.get('value')
                    doc_qty = 1.0
                    
                    success, preview = tester.test(
                        f"Preview conversion: {doc_qty} {doc_uom}",
                        "POST", f"inbound/tasks/{task_id}/preview-uom", 200,
                        data={"doc_uom": doc_uom, "doc_qty": doc_qty}
                    )
                    if success:
                        trail = preview.get('trail', {})
                        print(f"   Conversion: {trail.get('doc_qty')} {trail.get('doc_uom')} "
                              f"→ {trail.get('task_qty')} {trail.get('task_uom')}")
                        print(f"   Factor: {trail.get('factor')}")
                        print(f"   Source: {trail.get('source')}")
                        print(f"   Level: {preview.get('level')}")
    
    # Test 5: RBAC - Warehouse user
    print("\n" + "="*80)
    print("TEST GROUP 5: RBAC - Warehouse User")
    print("="*80)
    
    wh_tester = APITester()
    if wh_tester.login("warehouse@kainnusantara.id", "demo12345"):
        # Warehouse should be able to view UOM options
        if waiting_tasks:
            task_id = waiting_tasks[0].get("id")
            wh_tester.test(
                "Warehouse can view UOM options",
                "GET", f"inbound/tasks/{task_id}/uom-options", 200
            )
            
            # Warehouse should NOT be able to change settings
            wh_tester.test(
                "Warehouse CANNOT change UOM settings",
                "PUT", "receiving/uom-settings", 403,
                data={"supplier_uom_input_mode": "off"}
            )
    
    # Test 6: RBAC - Sales user
    print("\n" + "="*80)
    print("TEST GROUP 6: RBAC - Sales User")
    print("="*80)
    
    sales_tester = APITester()
    if sales_tester.login("sales@kainnusantara.id", "demo12345"):
        # Sales should NOT be able to view UOM options
        if waiting_tasks:
            task_id = waiting_tasks[0].get("id")
            sales_tester.test(
                "Sales CANNOT view UOM options",
                "GET", f"inbound/tasks/{task_id}/uom-options", 403
            )
    
    # Test 7: Phase E Regressions
    print("\n" + "="*80)
    print("TEST GROUP 7: Phase E Regressions")
    print("="*80)
    
    tester.test("List supplier items", "GET", "supplier-items", 200)
    tester.test("List purchase requisitions", "GET", "purchase-requisitions", 200)
    tester.test("List supplier contracts", "GET", "supplier-contracts", 200)
    
    # Test 8: Invalid UOM (US-F4)
    print("\n" + "="*80)
    print("TEST GROUP 8: Invalid UOM Handling (US-F4)")
    print("="*80)
    
    if waiting_tasks:
        task_id = waiting_tasks[0].get("id")
        # Try invalid UOM
        tester.test(
            "Invalid UOM should be rejected with actionable message",
            "POST", f"inbound/tasks/{task_id}/preview-uom", 400,
            data={"doc_uom": "invalid_unit_xyz", "doc_qty": 10}
        )
        
        # Try zero quantity
        tester.test(
            "Zero quantity should be rejected",
            "POST", f"inbound/tasks/{task_id}/preview-uom", 400,
            data={"doc_uom": "kg", "doc_qty": 0}
        )
    
    # Print summary
    print("\n" + "=" * 80)
    print(f"  TESTS COMPLETED: {tester.tests_passed}/{tester.tests_run} PASSED")
    if wh_tester.tests_run > 0:
        print(f"  Warehouse RBAC: {wh_tester.tests_passed}/{wh_tester.tests_run} PASSED")
    if sales_tester.tests_run > 0:
        print(f"  Sales RBAC: {sales_tester.tests_passed}/{sales_tester.tests_run} PASSED")
    
    total_run = tester.tests_run + wh_tester.tests_run + sales_tester.tests_run
    total_passed = tester.tests_passed + wh_tester.tests_passed + sales_tester.tests_passed
    
    print(f"\n  TOTAL: {total_passed}/{total_run} PASSED")
    
    if total_passed == total_run:
        print("\n✅ ALL BACKEND TESTS PASSED")
        print("=" * 80)
        return 0
    else:
        print(f"\n❌ {total_run - total_passed} TESTS FAILED")
        print("=" * 80)
        return 1

if __name__ == "__main__":
    sys.exit(main())
