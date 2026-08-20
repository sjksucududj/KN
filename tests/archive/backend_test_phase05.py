"""Backend API Testing for Phase 0.5 - Roll-as-SSOT Inventory Ownership
Tests the critical roll-level reservation lifecycle and owner-scoped inventory.
"""
import requests
import sys
from datetime import datetime

class Phase05Tester:
    def __init__(self, base_url="https://po-pdf-sender.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.test_data = {}

    def run_test(self, name, method, endpoint, expected_status, data=None, description=""):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        if description:
            print(f"   {description}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=15)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ PASS - Status: {response.status_code}")
            else:
                print(f"❌ FAIL - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:300]}")
                self.failed_tests.append({
                    "test": name,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "endpoint": endpoint,
                    "response": response.text[:200]
                })

            try:
                return success, response.json() if response.text else {}
            except:
                return success, {}

        except Exception as e:
            print(f"❌ FAIL - Error: {str(e)}")
            self.failed_tests.append({
                "test": name,
                "error": str(e),
                "endpoint": endpoint
            })
            return False, {}

    def test_login(self):
        """Test login with admin credentials"""
        print("\n" + "="*70)
        print("🔐 AUTHENTICATION")
        print("="*70)
        
        success, response = self.run_test(
            "Login as Admin",
            "POST",
            "api/auth/login",
            200,
            data={"email": "admin@kainnusantara.id", "password": "demo12345"},
            description="Login with admin@kainnusantara.id"
        )
        if success and 'token' in response:
            self.token = response['token']
            print(f"   ✓ Token obtained: {self.token[:20]}...")
            return True
        return False

    def test_inventory_balances(self):
        """Test GET /api/inventory/balances with owner filtering"""
        print("\n" + "="*70)
        print("📦 INVENTORY BALANCES (Owner-aware)")
        print("="*70)
        
        # Test 1: Get all balances
        success, response = self.run_test(
            "Get all inventory balances",
            "GET",
            "api/inventory/balances",
            200,
            description="Should return balances with owner_entity_id and owner_entity_name"
        )
        
        if success and isinstance(response, list):
            balances = response
            print(f"   ✓ Found {len(balances)} balance records")
            
            # Verify structure
            if balances:
                sample = balances[0]
                required_fields = ['owner_entity_id', 'owner_entity_name', 'available_qty', 
                                 'reserved_qty', 'committed_qty', 'on_hand_qty']
                missing = [f for f in required_fields if f not in sample]
                if missing:
                    print(f"   ⚠️  Missing fields in balance: {missing}")
                else:
                    print(f"   ✓ Balance structure correct")
                    print(f"   ✓ Sample: owner={sample.get('owner_entity_name')}, "
                          f"available={sample.get('available_qty')}, "
                          f"reserved={sample.get('reserved_qty')}")
        
        # Test 2: Filter by owner_entity_id
        success, response = self.run_test(
            "Filter balances by owner_entity_id=ent_ksc",
            "GET",
            "api/inventory/balances?owner_entity_id=ent_ksc",
            200,
            description="Should return only balances owned by ent_ksc"
        )
        
        if success and isinstance(response, list):
            ksc_balances = response
            print(f"   ✓ Found {len(ksc_balances)} balances for ent_ksc")
            # Verify all are ent_ksc
            wrong_owner = [b for b in ksc_balances if b.get('owner_entity_id') != 'ent_ksc']
            if wrong_owner:
                print(f"   ❌ Found {len(wrong_owner)} balances with wrong owner!")
                return False
            else:
                print(f"   ✓ All balances belong to ent_ksc")
        
        return True

    def test_inventory_rolls(self):
        """Test GET /api/inventory/rolls with multiple filters"""
        print("\n" + "="*70)
        print("🎞️  INVENTORY ROLLS (SSOT)")
        print("="*70)
        
        # Test 1: Get all rolls
        success, response = self.run_test(
            "Get all inventory rolls",
            "GET",
            "api/inventory/rolls",
            200,
            description="Should return roll documents with owner, lot, status"
        )
        
        if success and isinstance(response, list):
            rolls = response
            print(f"   ✓ Found {len(rolls)} roll records")
            
            if rolls:
                sample = rolls[0]
                required_fields = ['id', 'roll_no', 'owner_entity_id', 'lot', 'status', 
                                 'length_remaining', 'length_initial', 'warehouse_id']
                missing = [f for f in required_fields if f not in sample]
                if missing:
                    print(f"   ⚠️  Missing fields in roll: {missing}")
                else:
                    print(f"   ✓ Roll structure correct")
                    print(f"   ✓ Sample: roll_no={sample.get('roll_no')}, "
                          f"owner={sample.get('owner_entity_name')}, "
                          f"lot={sample.get('lot')}, status={sample.get('status')}, "
                          f"length={sample.get('length_remaining')}")
                
                # Store a product with available rolls for later tests
                available_rolls = [r for r in rolls if r.get('status') == 'available' 
                                 and float(r.get('length_remaining', 0)) >= 30]
                if available_rolls:
                    self.test_data['sample_roll'] = available_rolls[0]
                    self.test_data['sample_product_id'] = available_rolls[0]['product_id']
                    print(f"   ✓ Stored sample product: {available_rolls[0]['product_id']}")
        
        # Test 2: Filter by owner
        success, response = self.run_test(
            "Filter rolls by owner_entity_id=ent_ksc",
            "GET",
            "api/inventory/rolls?owner_entity_id=ent_ksc",
            200,
            description="Should return only rolls owned by ent_ksc"
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} rolls for ent_ksc")
        
        # Test 3: Filter by status
        success, response = self.run_test(
            "Filter rolls by status=available",
            "GET",
            "api/inventory/rolls?status=available",
            200,
            description="Should return only available rolls"
        )
        
        if success and isinstance(response, list):
            available = response
            print(f"   ✓ Found {len(available)} available rolls")
            wrong_status = [r for r in available if r.get('status') != 'available']
            if wrong_status:
                print(f"   ❌ Found {len(wrong_status)} rolls with wrong status!")
                return False
        
        return True

    def test_stock_breakdown(self):
        """Test GET /api/products/{id}/stock-breakdown - ownership matrix"""
        print("\n" + "="*70)
        print("📊 STOCK BREAKDOWN (Ownership Matrix)")
        print("="*70)
        
        # Get a product ID
        product_id = self.test_data.get('sample_product_id')
        if not product_id:
            # Get from products list
            success, response = self.run_test(
                "Get products list",
                "GET",
                "api/products",
                200,
                description="Get products to test stock breakdown"
            )
            if success and isinstance(response, list) and response:
                product_id = response[0]['id']
        
        if not product_id:
            print("   ⚠️  No product ID available, skipping stock breakdown test")
            return False
        
        success, response = self.run_test(
            f"Get stock breakdown for product {product_id}",
            "GET",
            f"api/products/{product_id}/stock-breakdown",
            200,
            description="Should return ownership_matrix, rolls, balances"
        )
        
        if success:
            required_keys = ['product', 'balances', 'ownership_matrix', 'rolls']
            missing = [k for k in required_keys if k not in response]
            if missing:
                print(f"   ❌ Missing keys in response: {missing}")
                return False
            
            print(f"   ✓ Response structure correct")
            print(f"   ✓ Ownership matrix cells: {len(response.get('ownership_matrix', []))}")
            print(f"   ✓ Rolls: {len(response.get('rolls', []))}")
            print(f"   ✓ Balances: {len(response.get('balances', []))}")
            
            # Check ownership matrix structure
            matrix = response.get('ownership_matrix', [])
            if matrix:
                cell = matrix[0]
                required_cell_fields = ['owner_entity_id', 'owner_entity_name', 'warehouse_id', 
                                       'lot', 'available_qty', 'reserved_qty', 'roll_count']
                missing_cell = [f for f in required_cell_fields if f not in cell]
                if missing_cell:
                    print(f"   ⚠️  Missing fields in matrix cell: {missing_cell}")
                else:
                    print(f"   ✓ Matrix cell structure correct")
                    print(f"   ✓ Sample cell: owner={cell.get('owner_entity_name')}, "
                          f"warehouse={cell.get('warehouse_name')}, lot={cell.get('lot')}, "
                          f"available={cell.get('available_qty')}, rolls={cell.get('roll_count')}")
        
        return success

    def test_initial_stock(self):
        """Test POST /api/inventory/initial-stock - create roll"""
        print("\n" + "="*70)
        print("➕ INITIAL STOCK (Create Roll)")
        print("="*70)
        
        # Get product and warehouse
        success, products = self.run_test(
            "Get products for initial stock test",
            "GET",
            "api/products",
            200,
            description="Get a product to add stock"
        )
        
        if not success or not isinstance(products, list) or not products:
            print("   ⚠️  No products available")
            return False
        
        product_id = products[0]['id']
        
        success, warehouses = self.run_test(
            "Get warehouses for initial stock test",
            "GET",
            "api/warehouses",
            200,
            description="Get a warehouse"
        )
        
        if not success or not isinstance(warehouses, list) or not warehouses:
            print("   ⚠️  No warehouses available")
            return False
        
        warehouse_id = warehouses[0]['id']
        
        # Create initial stock
        payload = {
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "owner_entity_id": "ent_ksc",
            "lot": f"LOT-TEST-{datetime.now().strftime('%H%M%S')}",
            "quantity": 50.0,
            "unit": "meter",
            "grade": "A"
        }
        
        success, response = self.run_test(
            "Create initial stock (roll)",
            "POST",
            "api/inventory/initial-stock",
            200,
            data=payload,
            description=f"Create roll: 50m, lot={payload['lot']}"
        )
        
        if success:
            print(f"   ✓ Roll created: {response.get('roll_id')}")
            print(f"   ✓ Lot: {response.get('lot')}")
            self.test_data['created_roll_id'] = response.get('roll_id')
            return True
        
        return False

    def test_reservation_lifecycle(self):
        """Test CRITICAL: Full reservation lifecycle"""
        print("\n" + "="*70)
        print("🔄 RESERVATION LIFECYCLE (CRITICAL)")
        print("="*70)
        
        # Get customer and product
        success, customers = self.run_test(
            "Get customers",
            "GET",
            "api/customers",
            200,
            description="Get customer for order"
        )
        
        if not success or not isinstance(customers, list) or not customers:
            print("   ⚠️  No customers available")
            return False
        
        customer = customers[0]
        if not customer.get('addresses'):
            print("   ⚠️  Customer has no addresses")
            return False
        
        address_id = customer['addresses'][0]['id']
        
        # Get product with available stock
        success, products = self.run_test(
            "Get products with stock",
            "GET",
            "api/products",
            200,
            description="Get product with available stock"
        )
        
        if not success or not isinstance(products, list):
            print("   ⚠️  No products available")
            return False
        
        # Find product with available_qty >= 30
        product = next((p for p in products if float(p.get('available_qty', 0)) >= 30), None)
        if not product:
            print("   ⚠️  No product with available_qty >= 30")
            return False
        
        product_id = product['id']
        print(f"   ✓ Using product: {product.get('name')} (available: {product.get('available_qty')})")
        
        # Get initial balance state
        success, balances_before = self.run_test(
            "Get balances before order",
            "GET",
            f"api/inventory/balances",
            200,
            description="Capture initial balance state"
        )
        
        if not success:
            return False
        
        # Find balance for this product and owner
        balance_before = next((b for b in balances_before 
                              if b.get('product_id') == product_id 
                              and b.get('owner_entity_id') == 'ent_ksc'), None)
        
        if not balance_before:
            print(f"   ⚠️  No balance found for product {product_id} and owner ent_ksc")
            return False
        
        avail_before = float(balance_before.get('available_qty', 0))
        reserved_before = float(balance_before.get('reserved_qty', 0))
        committed_before = float(balance_before.get('committed_qty', 0))
        
        print(f"   ✓ Initial state: available={avail_before}, reserved={reserved_before}, committed={committed_before}")
        
        # STEP 1: Create Sales Order (Reserve Rolls)
        print(f"\n   📝 STEP 1: Create Sales Order (Reserve Rolls)")
        order_qty = 35.0
        order_payload = {
            "customer_id": customer['id'],
            "shipping_address_id": address_id,
            "items": [{
                "product_id": product_id,
                "quantity": order_qty,
                "unit": product.get('base_unit', 'meter')
            }],
            "entity_id": "ent_ksc"
        }
        
        success, order = self.run_test(
            "Create Sales Order (reserve rolls)",
            "POST",
            "api/sales-orders",
            200,
            data=order_payload,
            description=f"Create order for {order_qty}m"
        )
        
        if not success:
            print("   ❌ Failed to create order")
            return False
        
        order_id = order.get('id')
        print(f"   ✓ Order created: {order.get('number')} (id: {order_id})")
        print(f"   ✓ Status: {order.get('status')}")
        
        # Verify allocations
        allocations = order.get('allocations', [])
        if not allocations:
            print("   ❌ No allocations in order")
            return False
        
        print(f"   ✓ Allocations: {len(allocations)}")
        
        # Verify rolls in allocations
        total_reserved_length = 0
        for alloc in allocations:
            rolls = alloc.get('rolls', [])
            print(f"   ✓ Allocation: warehouse={alloc.get('warehouse_name')}, "
                  f"owner={alloc.get('owner_entity_id')}, rolls={len(rolls)}")
            for roll in rolls:
                total_reserved_length += float(roll.get('length', 0))
                print(f"      - Roll: {roll.get('roll_no')}, lot={roll.get('lot')}, length={roll.get('length')}")
        
        # Verify total reserved length matches order qty
        if abs(total_reserved_length - order_qty) > 0.01:
            print(f"   ❌ Reserved length mismatch: {total_reserved_length} vs {order_qty}")
            return False
        else:
            print(f"   ✅ Reserved length matches order qty: {total_reserved_length}")
        
        # Verify balance changes after reservation
        success, balances_after_reserve = self.run_test(
            "Get balances after reservation",
            "GET",
            "api/inventory/balances",
            200,
            description="Check balance changes"
        )
        
        if not success:
            return False
        
        balance_after_reserve = next((b for b in balances_after_reserve 
                                     if b.get('product_id') == product_id 
                                     and b.get('owner_entity_id') == 'ent_ksc'), None)
        
        if not balance_after_reserve:
            print("   ❌ Balance not found after reservation")
            return False
        
        avail_after_reserve = float(balance_after_reserve.get('available_qty', 0))
        reserved_after_reserve = float(balance_after_reserve.get('reserved_qty', 0))
        
        print(f"   ✓ After reserve: available={avail_after_reserve}, reserved={reserved_after_reserve}")
        
        # Verify: available decreased by order_qty
        expected_avail = avail_before - order_qty
        if abs(avail_after_reserve - expected_avail) > 0.5:
            print(f"   ❌ Available qty mismatch: {avail_after_reserve} vs expected {expected_avail}")
            return False
        else:
            print(f"   ✅ Available decreased correctly: {avail_before} → {avail_after_reserve}")
        
        # Verify: reserved increased by order_qty
        expected_reserved = reserved_before + order_qty
        if abs(reserved_after_reserve - expected_reserved) > 0.5:
            print(f"   ❌ Reserved qty mismatch: {reserved_after_reserve} vs expected {expected_reserved}")
            return False
        else:
            print(f"   ✅ Reserved increased correctly: {reserved_before} → {reserved_after_reserve}")
        
        # STEP 2: Approve Order (Commit Rolls)
        print(f"\n   ✅ STEP 2: Approve Order (Commit Rolls)")
        
        success, order_approved = self.run_test(
            "Approve Sales Order (commit rolls)",
            "POST",
            f"api/sales-orders/{order_id}/approve",
            200,
            description="Approve order to commit rolls"
        )
        
        if not success:
            print("   ❌ Failed to approve order")
            return False
        
        print(f"   ✓ Order approved, status: {order_approved.get('status')}")
        
        # Verify balance changes after approval
        success, balances_after_approve = self.run_test(
            "Get balances after approval",
            "GET",
            "api/inventory/balances",
            200,
            description="Check balance changes after approval"
        )
        
        if not success:
            return False
        
        balance_after_approve = next((b for b in balances_after_approve 
                                     if b.get('product_id') == product_id 
                                     and b.get('owner_entity_id') == 'ent_ksc'), None)
        
        if not balance_after_approve:
            print("   ❌ Balance not found after approval")
            return False
        
        reserved_after_approve = float(balance_after_approve.get('reserved_qty', 0))
        committed_after_approve = float(balance_after_approve.get('committed_qty', 0))
        
        print(f"   ✓ After approve: reserved={reserved_after_approve}, committed={committed_after_approve}")
        
        # Verify: reserved back to original
        if abs(reserved_after_approve - reserved_before) > 0.5:
            print(f"   ❌ Reserved not restored: {reserved_after_approve} vs {reserved_before}")
            return False
        else:
            print(f"   ✅ Reserved restored: {reserved_after_approve}")
        
        # Verify: committed increased by order_qty
        expected_committed = committed_before + order_qty
        if abs(committed_after_approve - expected_committed) > 0.5:
            print(f"   ❌ Committed qty mismatch: {committed_after_approve} vs expected {expected_committed}")
            return False
        else:
            print(f"   ✅ Committed increased correctly: {committed_before} → {committed_after_approve}")
        
        # STEP 3: Cancel Order (Release Rolls)
        print(f"\n   🚫 STEP 3: Cancel Order (Release Rolls)")
        
        success, order_cancelled = self.run_test(
            "Cancel Sales Order (release rolls)",
            "POST",
            f"api/sales-orders/{order_id}/cancel",
            200,
            description="Cancel order to release rolls back to available"
        )
        
        if not success:
            print("   ❌ Failed to cancel order")
            return False
        
        print(f"   ✓ Order cancelled, status: {order_cancelled.get('status')}")
        
        # Verify balance restoration after cancellation
        success, balances_after_cancel = self.run_test(
            "Get balances after cancellation",
            "GET",
            "api/inventory/balances",
            200,
            description="Check balance restoration"
        )
        
        if not success:
            return False
        
        balance_after_cancel = next((b for b in balances_after_cancel 
                                    if b.get('product_id') == product_id 
                                    and b.get('owner_entity_id') == 'ent_ksc'), None)
        
        if not balance_after_cancel:
            print("   ❌ Balance not found after cancellation")
            return False
        
        avail_after_cancel = float(balance_after_cancel.get('available_qty', 0))
        reserved_after_cancel = float(balance_after_cancel.get('reserved_qty', 0))
        committed_after_cancel = float(balance_after_cancel.get('committed_qty', 0))
        
        print(f"   ✓ After cancel: available={avail_after_cancel}, reserved={reserved_after_cancel}, committed={committed_after_cancel}")
        
        # Verify: available restored to original
        if abs(avail_after_cancel - avail_before) > 0.5:
            print(f"   ❌ Available not restored: {avail_after_cancel} vs {avail_before}")
            return False
        else:
            print(f"   ✅ Available restored: {avail_before} → {avail_after_cancel}")
        
        # Verify: reserved and committed back to original
        if abs(reserved_after_cancel - reserved_before) > 0.5:
            print(f"   ❌ Reserved not restored: {reserved_after_cancel} vs {reserved_before}")
            return False
        else:
            print(f"   ✅ Reserved restored: {reserved_after_cancel}")
        
        if abs(committed_after_cancel - committed_before) > 0.5:
            print(f"   ❌ Committed not restored: {committed_after_cancel} vs {committed_before}")
            return False
        else:
            print(f"   ✅ Committed restored: {committed_after_cancel}")
        
        print(f"\n   🎉 RESERVATION LIFECYCLE TEST PASSED!")
        return True

    def test_dashboard_summary(self):
        """Test GET /api/dashboard/summary - KPI consistency"""
        print("\n" + "="*70)
        print("📈 DASHBOARD SUMMARY (KPI Consistency)")
        print("="*70)
        
        success, response = self.run_test(
            "Get dashboard summary",
            "GET",
            "api/dashboard/summary",
            200,
            description="Check KPI consistency with balances"
        )
        
        if success:
            print(f"   ✓ Available qty: {response.get('available_qty')}")
            print(f"   ✓ Reserved qty: {response.get('reserved_qty')}")
            print(f"   ✓ On-hand qty: {response.get('on_hand_qty')}")
            
            # Get balances to verify
            success2, balances = self.run_test(
                "Get balances for verification",
                "GET",
                "api/inventory/balances",
                200,
                description="Verify dashboard matches sum of balances"
            )
            
            if success2 and isinstance(balances, list):
                total_available = sum(float(b.get('available_qty', 0)) for b in balances)
                total_reserved = sum(float(b.get('reserved_qty', 0)) for b in balances)
                
                dashboard_available = float(response.get('available_qty', 0))
                dashboard_reserved = float(response.get('reserved_qty', 0))
                
                print(f"   ✓ Sum of balances: available={total_available}, reserved={total_reserved}")
                
                if abs(dashboard_available - total_available) > 1.0:
                    print(f"   ⚠️  Dashboard available mismatch: {dashboard_available} vs {total_available}")
                else:
                    print(f"   ✅ Dashboard available matches balances")
                
                if abs(dashboard_reserved - total_reserved) > 1.0:
                    print(f"   ⚠️  Dashboard reserved mismatch: {dashboard_reserved} vs {total_reserved}")
                else:
                    print(f"   ✅ Dashboard reserved matches balances")
        
        return success

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("📊 TEST SUMMARY - PHASE 0.5")
        print("="*70)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        success_rate = (self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        
        if self.failed_tests:
            print("\n❌ FAILED TESTS:")
            for fail in self.failed_tests:
                error_msg = fail.get('error', f"Expected {fail.get('expected')}, got {fail.get('actual')}")
                print(f"  - {fail['test']}: {error_msg}")
                if 'response' in fail:
                    print(f"    Response: {fail['response']}")
        else:
            print("\n✅ ALL TESTS PASSED!")
        
        print("="*70)


def main():
    print("="*70)
    print("🧪 PHASE 0.5 BACKEND TEST SUITE")
    print("   Roll-as-SSOT Inventory Ownership")
    print("="*70)
    
    tester = Phase05Tester()
    
    # Authentication
    if not tester.test_login():
        print("\n❌ Authentication failed, cannot proceed")
        return 1
    
    # Run all tests
    tester.test_inventory_balances()
    tester.test_inventory_rolls()
    tester.test_stock_breakdown()
    tester.test_initial_stock()
    tester.test_reservation_lifecycle()  # CRITICAL TEST
    tester.test_dashboard_summary()
    
    # Print summary
    tester.print_summary()
    
    # Return exit code
    return 0 if tester.tests_passed == tester.tests_run else 1


if __name__ == "__main__":
    sys.exit(main())
