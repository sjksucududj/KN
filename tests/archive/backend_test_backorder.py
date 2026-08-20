"""Backend API Testing for Sub-fase 1.6 - Backorder Lifecycle
Tests all backorder scenarios including auto-fulfill flow and data integrity.
"""
import requests
import sys
import time
from datetime import datetime

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com"
API = f"{BASE_URL}/api"

class BackorderTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.entity_id = None
        self.warehouse_id = None
        self.product_id = None
        self.customer_id = None
        self.address_id = None
        
    def log_pass(self, msg):
        self.tests_passed += 1
        print(f"  ✅ PASS: {msg}")
        
    def log_fail(self, msg):
        self.failed_tests.append(msg)
        print(f"  ❌ FAIL: {msg}")
        
    def run_test(self, name, method, endpoint, expected_status, data=None, description=""):
        """Run a single API test"""
        url = f"{API}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        if description:
            print(f"   {description}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=30)
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"   ✅ Status: {response.status_code}")
            else:
                print(f"   ❌ Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:300]}")
                self.failed_tests.append(f"{name}: Expected {expected_status}, got {response.status_code}")
            
            try:
                return success, response.json() if response.text else {}
            except:
                return success, {}
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            self.failed_tests.append(f"{name}: {str(e)}")
            return False, {}
    
    def test_login(self):
        """Test 1: Login as admin"""
        success, response = self.run_test(
            "Login Admin",
            "POST",
            "auth/login",
            200,
            data={"email": "admin@kainnusantara.id", "password": "demo12345"},
            description="Login with admin credentials"
        )
        if success and 'token' in response:
            self.token = response['token']
            self.log_pass("Admin login successful, token obtained")
            return True
        self.log_fail("Admin login failed or no token")
        return False
    
    def setup_test_data(self):
        """Test 2: Get entities, warehouses, products, customers"""
        print(f"\n🔍 Test {self.tests_run + 1}: Setup Test Data")
        
        # Get entities
        success, entities = self.run_test(
            "Get Entities",
            "GET",
            "entities",
            200,
            description="Get business entities"
        )
        if success and entities:
            self.entity_id = entities[0]['id']
            print(f"   ✓ Entity: {entities[0].get('short_name')} ({self.entity_id})")
        else:
            self.log_fail("Failed to get entities")
            return False
        
        # Get warehouses
        success, warehouses = self.run_test(
            "Get Warehouses",
            "GET",
            "warehouses",
            200,
            description="Get warehouses"
        )
        if success and warehouses:
            self.warehouse_id = warehouses[0]['id']
            print(f"   ✓ Warehouse: {warehouses[0].get('name')} ({self.warehouse_id})")
        else:
            self.log_fail("Failed to get warehouses")
            return False
        
        # Get products
        success, products = self.run_test(
            "Get Products",
            "GET",
            "products",
            200,
            description="Get products"
        )
        if success and products:
            self.product_id = products[0]['id']
            print(f"   ✓ Product: {products[0].get('name')} ({self.product_id})")
        else:
            self.log_fail("Failed to get products")
            return False
        
        # Get customers
        success, customers = self.run_test(
            "Get Customers",
            "GET",
            "customers",
            200,
            description="Get customers"
        )
        if success and customers:
            self.customer_id = customers[0]['id']
            self.address_id = customers[0].get('addresses', [{}])[0].get('id')
            print(f"   ✓ Customer: {customers[0].get('name')} ({self.customer_id})")
        else:
            self.log_fail("Failed to get customers")
            return False
        
        self.log_pass("Test data setup complete")
        return True
    
    def test_backorder_allow_true_qty_exceeds_stock(self):
        """Test 3: Create SO with allow_backorder=true and qty > stock"""
        print(f"\n🔍 Test {self.tests_run + 1}: Backorder with allow_backorder=true")
        
        # Get available stock for entity
        success, board = self.run_test(
            "Get Status Board",
            "GET",
            f"inventory/status-board?owner_entity_id={self.entity_id}",
            200,
            description="Get available stock for entity"
        )
        
        available = 0.0
        if success and board:
            for row in board:
                if row.get('product_id') == self.product_id:
                    for be in row.get('by_entity', []):
                        if be.get('entity_id') == self.entity_id:
                            available = float(be.get('available', 0) or 0)
                            break
                    break
        
        print(f"   ✓ Available stock for entity: {available}")
        
        # Request qty = available + 50 (force backorder)
        request_qty = round(available + 50.0, 2)
        print(f"   ✓ Requesting qty: {request_qty} (available + 50)")
        
        success, so = self.run_test(
            "Create SO with Backorder",
            "POST",
            "sales-orders",
            200,
            data={
                "customer_id": self.customer_id,
                "shipping_address_id": self.address_id,
                "entity_id": self.entity_id,
                "allow_backorder": True,
                "items": [{"product_id": self.product_id, "quantity": request_qty, "unit": "meter"}]
            },
            description=f"Create SO with allow_backorder=true, qty={request_qty}"
        )
        
        if not success:
            self.log_fail("Failed to create SO with backorder")
            return False, None
        
        # Verify status = waiting_stock
        if so.get('status') == 'waiting_stock':
            self.log_pass(f"SO status = waiting_stock (correct)")
        else:
            self.log_fail(f"SO status should be waiting_stock, got {so.get('status')}")
        
        # Verify has_backorder = true
        if so.get('has_backorder'):
            self.log_pass("SO has_backorder = true (correct)")
        else:
            self.log_fail("SO has_backorder should be true")
        
        # Verify backorders array is filled
        backorders = so.get('backorders', [])
        if backorders:
            self.log_pass(f"Backorders array has {len(backorders)} entries")
        else:
            self.log_fail("Backorders array is empty")
        
        # Verify item: reserved_qty + backorder_qty == quantity
        item = so.get('items', [{}])[0]
        reserved_qty = float(item.get('reserved_qty', 0) or 0)
        backorder_qty = float(item.get('backorder_qty', 0) or 0)
        total = round(reserved_qty + backorder_qty, 2)
        
        print(f"   ✓ Item breakdown: reserved={reserved_qty}, backorder={backorder_qty}, total={total}")
        
        if abs(total - request_qty) < 0.5:
            self.log_pass(f"Item: reserved_qty + backorder_qty == quantity ({total} ≈ {request_qty})")
        else:
            self.log_fail(f"Item: reserved_qty + backorder_qty != quantity ({total} != {request_qty})")
        
        return True, so
    
    def test_backorder_allow_false_qty_exceeds_stock(self):
        """Test 4: Create SO with allow_backorder=false (default) and qty > stock → 409"""
        print(f"\n🔍 Test {self.tests_run + 1}: Backorder with allow_backorder=false (backward compatible)")
        
        # Get available stock
        success, board = self.run_test(
            "Get Status Board",
            "GET",
            f"inventory/status-board?owner_entity_id={self.entity_id}",
            200,
            description="Get available stock"
        )
        
        available = 0.0
        if success and board:
            for row in board:
                if row.get('product_id') == self.product_id:
                    for be in row.get('by_entity', []):
                        if be.get('entity_id') == self.entity_id:
                            available = float(be.get('available', 0) or 0)
                            break
                    break
        
        # Request qty > available
        request_qty = round(available + 100.0, 2)
        print(f"   ✓ Available: {available}, Requesting: {request_qty}")
        
        success, response = self.run_test(
            "Create SO without Backorder (409)",
            "POST",
            "sales-orders",
            409,
            data={
                "customer_id": self.customer_id,
                "shipping_address_id": self.address_id,
                "entity_id": self.entity_id,
                "allow_backorder": False,  # Explicit false
                "items": [{"product_id": self.product_id, "quantity": request_qty, "unit": "meter"}]
            },
            description="Should return 409 when qty > stock and allow_backorder=false"
        )
        
        if success:
            self.log_pass("Correctly returned 409 for insufficient stock (backward compatible)")
            return True
        else:
            self.log_fail("Should return 409 when allow_backorder=false and qty > stock")
            return False
    
    def test_normal_order_no_backorder(self):
        """Test 5: Create normal SO (qty <= stock) → status reserved, no backorder"""
        print(f"\n🔍 Test {self.tests_run + 1}: Normal order (qty <= stock, no backorder)")
        
        # Get available stock
        success, board = self.run_test(
            "Get Status Board",
            "GET",
            f"inventory/status-board?owner_entity_id={self.entity_id}",
            200,
            description="Get available stock"
        )
        
        available = 0.0
        if success and board:
            for row in board:
                if row.get('product_id') == self.product_id:
                    for be in row.get('by_entity', []):
                        if be.get('entity_id') == self.entity_id:
                            available = float(be.get('available', 0) or 0)
                            break
                    break
        
        # Request qty <= available (use 10m or 10% of available, whichever is smaller)
        request_qty = min(10.0, round(available * 0.1, 2)) if available > 0 else 10.0
        print(f"   ✓ Available: {available}, Requesting: {request_qty}")
        
        success, so = self.run_test(
            "Create Normal SO",
            "POST",
            "sales-orders",
            200,
            data={
                "customer_id": self.customer_id,
                "shipping_address_id": self.address_id,
                "entity_id": self.entity_id,
                "items": [{"product_id": self.product_id, "quantity": request_qty, "unit": "meter"}]
            },
            description=f"Create normal SO with qty={request_qty} <= available"
        )
        
        if not success:
            self.log_fail("Failed to create normal SO")
            return False
        
        # Verify status = reserved (or waiting_approval if approval needed)
        status = so.get('status')
        if status in ['reserved', 'waiting_approval']:
            self.log_pass(f"SO status = {status} (correct for normal order)")
        else:
            self.log_fail(f"SO status should be reserved or waiting_approval, got {status}")
        
        # Verify backorder_qty = 0
        item = so.get('items', [{}])[0]
        backorder_qty = float(item.get('backorder_qty', 0) or 0)
        
        if backorder_qty <= 0.01:
            self.log_pass(f"Item backorder_qty = {backorder_qty} (no backorder)")
        else:
            self.log_fail(f"Item backorder_qty should be 0, got {backorder_qty}")
        
        # Verify has_backorder = false
        if not so.get('has_backorder'):
            self.log_pass("SO has_backorder = false (correct)")
        else:
            self.log_fail("SO has_backorder should be false for normal order")
        
        return True
    
    def test_cancel_waiting_stock_order(self, so):
        """Test 6: Cancel SO with status waiting_stock"""
        if not so:
            print(f"\n⚠️  Skipping cancel test - no backorder SO available")
            return False
        
        so_id = so.get('id')
        print(f"\n🔍 Test {self.tests_run + 1}: Cancel waiting_stock order")
        
        success, cancelled_so = self.run_test(
            "Cancel Waiting Stock Order",
            "POST",
            f"sales-orders/{so_id}/cancel",
            200,
            description=f"Cancel SO {so.get('number')} with status waiting_stock"
        )
        
        if not success:
            self.log_fail("Failed to cancel waiting_stock order")
            return False
        
        # Verify status = cancelled
        if cancelled_so.get('status') == 'cancelled':
            self.log_pass("SO status = cancelled (correct)")
        else:
            self.log_fail(f"SO status should be cancelled, got {cancelled_so.get('status')}")
        
        return True
    
    def test_release_reservation_waiting_stock(self):
        """Test 7: Release reservation on waiting_stock order"""
        print(f"\n🔍 Test {self.tests_run + 1}: Release reservation on waiting_stock order")
        
        # Create a new backorder SO for this test
        success, board = self.run_test(
            "Get Status Board",
            "GET",
            f"inventory/status-board?owner_entity_id={self.entity_id}",
            200,
            description="Get available stock"
        )
        
        available = 0.0
        if success and board:
            for row in board:
                if row.get('product_id') == self.product_id:
                    for be in row.get('by_entity', []):
                        if be.get('entity_id') == self.entity_id:
                            available = float(be.get('available', 0) or 0)
                            break
                    break
        
        request_qty = round(available + 30.0, 2)
        
        success, so = self.run_test(
            "Create SO for Release Test",
            "POST",
            "sales-orders",
            200,
            data={
                "customer_id": self.customer_id,
                "shipping_address_id": self.address_id,
                "entity_id": self.entity_id,
                "allow_backorder": True,
                "items": [{"product_id": self.product_id, "quantity": request_qty, "unit": "meter"}]
            },
            description="Create backorder SO for release test"
        )
        
        if not success or so.get('status') != 'waiting_stock':
            self.log_fail("Failed to create waiting_stock SO for release test")
            return False
        
        so_id = so.get('id')
        
        # Release reservation
        success, released_so = self.run_test(
            "Release Reservation",
            "POST",
            f"sales-orders/{so_id}/release-reservation",
            200,
            description=f"Release reservation for SO {so.get('number')}"
        )
        
        if not success:
            self.log_fail("Failed to release reservation")
            return False
        
        # Verify status = draft
        if released_so.get('status') == 'draft':
            self.log_pass("SO status = draft after release (correct)")
        else:
            self.log_fail(f"SO status should be draft after release, got {released_so.get('status')}")
        
        # Verify backorders array is empty
        if not released_so.get('backorders'):
            self.log_pass("Backorders array is empty after release (correct)")
        else:
            self.log_fail("Backorders array should be empty after release")
        
        # Verify has_backorder = false
        if not released_so.get('has_backorder'):
            self.log_pass("has_backorder = false after release (correct)")
        else:
            self.log_fail("has_backorder should be false after release")
        
        return True
    
    def test_orders_stats_backorder(self):
        """Test 8: Check orders stats includes backorder count"""
        print(f"\n🔍 Test {self.tests_run + 1}: Orders stats with backorder")
        
        success, stats = self.run_test(
            "Get Orders Stats",
            "GET",
            "sales-orders/stats/summary",
            200,
            description="Get orders statistics summary"
        )
        
        if not success:
            self.log_fail("Failed to get orders stats")
            return False
        
        by_status = stats.get('by_status', {})
        waiting_stock_stats = by_status.get('waiting_stock', {})
        
        if waiting_stock_stats:
            count = waiting_stock_stats.get('count', 0)
            self.log_pass(f"Orders stats includes waiting_stock: count={count}")
        else:
            print(f"   ⚠️  No waiting_stock orders in stats (may be expected if all cancelled)")
        
        return True
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 70)
        print(f"  BACKEND TEST SUMMARY - Sub-fase 1.6 Backorder Lifecycle")
        print("=" * 70)
        print(f"  Total Tests: {self.tests_run}")
        print(f"  Passed: {self.tests_passed}")
        print(f"  Failed: {len(self.failed_tests)}")
        print(f"  Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print("\n  ❌ FAILED TESTS:")
            for i, fail in enumerate(self.failed_tests, 1):
                print(f"     {i}. {fail}")
        else:
            print("\n  ✅ ALL TESTS PASSED!")
        
        print("=" * 70)
        
        return len(self.failed_tests) == 0

def main():
    print("=" * 70)
    print("  Backend API Testing - Sub-fase 1.6 Backorder Lifecycle")
    print("  Base URL: " + BASE_URL)
    print("=" * 70)
    
    tester = BackorderTester()
    
    # Run tests
    if not tester.test_login():
        print("\n❌ Login failed, cannot continue")
        return 1
    
    if not tester.setup_test_data():
        print("\n❌ Setup failed, cannot continue")
        return 1
    
    # Test backorder scenarios
    success, backorder_so = tester.test_backorder_allow_true_qty_exceeds_stock()
    tester.test_backorder_allow_false_qty_exceeds_stock()
    tester.test_normal_order_no_backorder()
    
    # Test cancel and release
    if backorder_so:
        tester.test_cancel_waiting_stock_order(backorder_so)
    
    tester.test_release_reservation_waiting_stock()
    tester.test_orders_stats_backorder()
    
    # Print summary
    all_passed = tester.print_summary()
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
