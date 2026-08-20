"""Backend API Testing - Auto-fulfill Backorder Flow (Sub-fase 1.6)
Critical test: Create backorder → PO → Inbound → Auto-fulfill → Data Integrity Check
"""
import requests
import sys
import time
import subprocess

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com"
API = f"{BASE_URL}/api"

class AutoFulfillTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        
    def log_pass(self, msg):
        self.tests_passed += 1
        print(f"  ✅ PASS: {msg}")
        
    def log_fail(self, msg):
        self.failed_tests.append(msg)
        print(f"  ❌ FAIL: {msg}")
    
    def api_call(self, method, endpoint, data=None, expected_status=200):
        """Make API call"""
        url = f"{API}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            
            if response.status_code == expected_status:
                try:
                    return True, response.json() if response.text else {}
                except:
                    return True, {}
            else:
                print(f"   ❌ Expected {expected_status}, got {response.status_code}: {response.text[:200]}")
                return False, {}
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            return False, {}
    
    def test_auto_fulfill_flow(self):
        """Complete auto-fulfill flow test"""
        print("\n" + "=" * 70)
        print("  AUTO-FULFILL BACKORDER FLOW TEST")
        print("=" * 70)
        
        # Step 1: Login
        print("\n📍 Step 1: Login")
        success, response = self.api_call('POST', 'auth/login', 
            data={"email": "admin@kainnusantara.id", "password": "demo12345"})
        if not success or 'token' not in response:
            self.log_fail("Login failed")
            return False
        self.token = response['token']
        self.log_pass("Login successful")
        
        # Step 2: Get test data
        print("\n📍 Step 2: Get test data (entity, warehouse, product, customer)")
        success, entities = self.api_call('GET', 'entities')
        if not success or not entities:
            self.log_fail("Failed to get entities")
            return False
        entity_id = entities[0]['id']
        entity_name = entities[0].get('short_name', entity_id)
        print(f"   ✓ Entity: {entity_name} ({entity_id})")
        
        success, warehouses = self.api_call('GET', 'warehouses')
        if not success or not warehouses:
            self.log_fail("Failed to get warehouses")
            return False
        warehouse_id = warehouses[0]['id']
        warehouse_name = warehouses[0].get('name', warehouse_id)
        print(f"   ✓ Warehouse: {warehouse_name}")
        
        success, products = self.api_call('GET', 'products')
        if not success or not products:
            self.log_fail("Failed to get products")
            return False
        product_id = products[0]['id']
        product_name = products[0].get('name', product_id)
        print(f"   ✓ Product: {product_name}")
        
        success, customers = self.api_call('GET', 'customers')
        if not success or not customers:
            self.log_fail("Failed to get customers")
            return False
        customer_id = customers[0]['id']
        address_id = customers[0].get('addresses', [{}])[0].get('id')
        customer_name = customers[0].get('name', customer_id)
        print(f"   ✓ Customer: {customer_name}")
        
        self.log_pass("Test data loaded")
        
        # Step 3: Get available stock
        print("\n📍 Step 3: Check available stock for entity")
        success, board = self.api_call('GET', f'inventory/status-board?owner_entity_id={entity_id}')
        if not success:
            self.log_fail("Failed to get status board")
            return False
        
        available = 0.0
        for row in board:
            if row.get('product_id') == product_id:
                for be in row.get('by_entity', []):
                    if be.get('entity_id') == entity_id:
                        available = float(be.get('available', 0) or 0)
                        break
                break
        
        print(f"   ✓ Available stock: {available}m")
        
        # Step 4: Create backorder SO
        print("\n📍 Step 4: Create Sales Order with Backorder")
        backorder_qty = 50.0
        request_qty = round(available + backorder_qty, 2)
        print(f"   ✓ Requesting: {request_qty}m (available {available}m + backorder {backorder_qty}m)")
        
        success, so = self.api_call('POST', 'sales-orders', data={
            "customer_id": customer_id,
            "shipping_address_id": address_id,
            "entity_id": entity_id,
            "allow_backorder": True,
            "items": [{"product_id": product_id, "quantity": request_qty, "unit": "meter"}]
        })
        
        if not success:
            self.log_fail("Failed to create backorder SO")
            return False
        
        so_id = so.get('id')
        so_number = so.get('number')
        print(f"   ✓ SO created: {so_number} (ID: {so_id})")
        print(f"   ✓ Status: {so.get('status')}")
        print(f"   ✓ Has backorder: {so.get('has_backorder')}")
        
        if so.get('status') != 'waiting_stock':
            self.log_fail(f"SO status should be waiting_stock, got {so.get('status')}")
            return False
        
        if not so.get('has_backorder'):
            self.log_fail("SO should have has_backorder=true")
            return False
        
        item = so.get('items', [{}])[0]
        reserved_qty = float(item.get('reserved_qty', 0) or 0)
        item_backorder_qty = float(item.get('backorder_qty', 0) or 0)
        print(f"   ✓ Item: reserved={reserved_qty}m, backorder={item_backorder_qty}m")
        
        if item_backorder_qty < 1.0:
            self.log_fail(f"Backorder qty too small: {item_backorder_qty}")
            return False
        
        self.log_pass(f"Backorder SO created: {so_number} with backorder={item_backorder_qty}m")
        
        # Step 5: Create PO to fulfill backorder
        print("\n📍 Step 5: Create Purchase Order to fulfill backorder")
        po_qty = round(item_backorder_qty, 2)
        print(f"   ✓ PO qty: {po_qty}m (to fulfill backorder)")
        
        success, po = self.api_call('POST', 'purchase-orders', data={
            "supplier_name": "Supplier Auto-fulfill Test",
            "warehouse_id": warehouse_id,
            "entity_id": entity_id,
            "items": [{"product_id": product_id, "quantity": po_qty, "unit": "meter", "price": 0.0}]
        })
        
        if not success:
            self.log_fail("Failed to create PO")
            return False
        
        po_id = po.get('id')
        po_number = po.get('po_number')
        po_status = po.get('status')
        print(f"   ✓ PO created: {po_number} (ID: {po_id})")
        print(f"   ✓ Status: {po_status}")
        
        self.log_pass(f"PO created: {po_number}")
        
        # Step 6: Approve PO if needed
        if po_status == 'waiting_approval':
            print("\n📍 Step 6: Approve Purchase Order")
            success, po = self.api_call('POST', f'purchase-orders/{po_id}/approve')
            if not success:
                self.log_fail("Failed to approve PO")
                return False
            print(f"   ✓ PO approved, new status: {po.get('status')}")
            self.log_pass("PO approved")
        else:
            print(f"\n📍 Step 6: PO approval not needed (status: {po_status})")
        
        # Step 7: Get inbound task
        print("\n📍 Step 7: Get inbound receiving task")
        success, tasks = self.api_call('GET', 'inbound/tasks')
        if not success:
            self.log_fail("Failed to get inbound tasks")
            return False
        
        task = None
        for t in tasks:
            if t.get('po_id') == po_id and t.get('product_id') == product_id:
                task = t
                break
        
        if not task:
            self.log_fail(f"Inbound task not found for PO {po_number}")
            return False
        
        task_id = task.get('id')
        expected_qty = float(task.get('expected_qty', 0))
        print(f"   ✓ Inbound task: {task_id}")
        print(f"   ✓ Expected qty: {expected_qty}m")
        print(f"   ✓ Status: {task.get('status')}")
        
        self.log_pass(f"Inbound task found: {task_id}")
        
        # Step 8: Scan-receive
        print("\n📍 Step 8: Scan-receive goods (full quantity)")
        success, task = self.api_call('POST', f'inbound/tasks/{task_id}/scan-receive', data={
            "product_id": product_id,
            "actual_qty": expected_qty,
            "lot": "LOT-AUTOFULFILL-TEST",
            "batch": "BATCH-TEST"
        })
        
        if not success:
            self.log_fail("Failed to scan-receive")
            return False
        
        print(f"   ✓ Scanned: {expected_qty}m")
        print(f"   ✓ Task status: {task.get('status')}")
        self.log_pass("Scan-receive successful")
        
        # Step 9: Complete inbound (GR) - triggers auto-fulfill
        print("\n📍 Step 9: Complete inbound receiving (Goods Receipt)")
        print("   ⚠️  This should trigger auto-fulfill of backorder...")
        
        success, task = self.api_call('POST', f'inbound/tasks/{task_id}/complete')
        if not success:
            self.log_fail("Failed to complete inbound")
            return False
        
        print(f"   ✓ Inbound completed, status: {task.get('status')}")
        self.log_pass("Inbound receiving completed (GR)")
        
        # Step 10: Verify SO auto-fulfilled
        print("\n📍 Step 10: Verify Sales Order auto-fulfilled")
        time.sleep(1)  # Brief wait for async processing
        
        success, so_updated = self.api_call('GET', f'sales-orders/{so_id}')
        if not success:
            self.log_fail("Failed to get updated SO")
            return False
        
        new_status = so_updated.get('status')
        has_backorder = so_updated.get('has_backorder')
        item_updated = so_updated.get('items', [{}])[0]
        reserved_after = float(item_updated.get('reserved_qty', 0) or 0)
        backorder_after = float(item_updated.get('backorder_qty', 0) or 0)
        
        print(f"   ✓ SO status: {new_status} (was: waiting_stock)")
        print(f"   ✓ Has backorder: {has_backorder} (was: true)")
        print(f"   ✓ Item reserved: {reserved_after}m (was: {reserved_qty}m)")
        print(f"   ✓ Item backorder: {backorder_after}m (was: {item_backorder_qty}m)")
        
        # Verify auto-fulfill worked
        if new_status == 'reserved':
            self.log_pass("✅ SO status changed to 'reserved' (auto-fulfill successful)")
        else:
            self.log_fail(f"SO status should be 'reserved', got '{new_status}'")
        
        if not has_backorder:
            self.log_pass("✅ has_backorder = false (backorder fulfilled)")
        else:
            self.log_fail("has_backorder should be false after auto-fulfill")
        
        if backorder_after <= 0.5:
            self.log_pass(f"✅ Item backorder_qty = {backorder_after} (fulfilled)")
        else:
            self.log_fail(f"Item backorder_qty should be ~0, got {backorder_after}")
        
        if abs(reserved_after - request_qty) < 0.5:
            self.log_pass(f"✅ Item reserved_qty = {reserved_after} (full quantity reserved)")
        else:
            self.log_fail(f"Item reserved_qty should be ~{request_qty}, got {reserved_after}")
        
        return True
    
    def test_data_integrity(self):
        """Run data integrity verification script"""
        print("\n" + "=" * 70)
        print("  CRITICAL: DATA INTEGRITY VERIFICATION")
        print("=" * 70)
        print("\n📍 Running verify_data_integrity.py...")
        print("   ⚠️  This MUST show 0 FAIL for balance == Σ rolls invariant")
        
        try:
            result = subprocess.run(
                ['python', '/app/scripts/verify_data_integrity.py'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            output = result.stdout
            print("\n" + output)
            
            # Check for FAIL in output
            if 'FAIL' in output and '0 FAIL' not in output:
                self.log_fail("Data integrity check found FAILURES")
                return False
            
            # Check for specific invariants
            if 'balance == Σ rolls' in output:
                if 'PASS' in output:
                    self.log_pass("✅ CRITICAL: balance == Σ rolls invariant PASSED")
                else:
                    self.log_fail("❌ CRITICAL: balance == Σ rolls invariant FAILED")
                    return False
            
            self.log_pass("Data integrity verification completed successfully")
            return True
            
        except subprocess.TimeoutExpired:
            self.log_fail("Data integrity check timed out")
            return False
        except Exception as e:
            self.log_fail(f"Data integrity check error: {str(e)}")
            return False
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 70)
        print("  AUTO-FULFILL TEST SUMMARY")
        print("=" * 70)
        print(f"  Passed: {self.tests_passed}")
        print(f"  Failed: {len(self.failed_tests)}")
        
        if self.failed_tests:
            print("\n  ❌ FAILED TESTS:")
            for i, fail in enumerate(self.failed_tests, 1):
                print(f"     {i}. {fail}")
            print("\n  ❌ AUTO-FULFILL FLOW FAILED")
        else:
            print("\n  ✅ AUTO-FULFILL FLOW PASSED!")
            print("  ✅ DATA INTEGRITY MAINTAINED!")
        
        print("=" * 70)
        
        return len(self.failed_tests) == 0

def main():
    tester = AutoFulfillTester()
    
    # Run auto-fulfill flow test
    flow_success = tester.test_auto_fulfill_flow()
    
    # Run data integrity check (CRITICAL)
    if flow_success:
        integrity_success = tester.test_data_integrity()
    else:
        print("\n⚠️  Skipping data integrity check due to flow failures")
        integrity_success = False
    
    # Print summary
    all_passed = tester.print_summary()
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
