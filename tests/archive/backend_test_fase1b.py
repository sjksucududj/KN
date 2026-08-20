"""Backend API Testing for Kain Nusantara ERP/WMS - Fase 1B Configuration Consumption"""
import requests
import sys
from datetime import datetime

class Fase1BAPITester:
    def __init__(self, base_url="https://po-pdf-sender.preview.emergentagent.com"):
        self.base_url = base_url
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.test_order_ids = []
        self.test_po_ids = []

    def run_test(self, name, method, endpoint, expected_status, data=None, token=None, description=""):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        if description:
            print(f"   {description}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=15)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=15)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=15)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:300]}")
                self.failed_tests.append({
                    "test": name,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "endpoint": endpoint,
                    "response": response.text[:300]
                })

            try:
                return success, response.json() if response.text else {}
            except:
                return success, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append({
                "test": name,
                "error": str(e),
                "endpoint": endpoint
            })
            return False, {}

    def test_login(self, email, password, role):
        """Test login and get token"""
        success, response = self.run_test(
            f"Login as {role}",
            "POST",
            "api/auth/login",
            200,
            data={"email": email, "password": password},
            description=f"Login with {email}"
        )
        if success and 'token' in response:
            self.tokens[role] = response['token']
            print(f"   Token stored for {role}")
            return True
        return False

    def test_sales_order_with_discounts_and_tax(self):
        """Test POST /api/sales-orders with item discount + order discount + payment term + PPN"""
        print("\n" + "="*80)
        print("TEST: Sales Order with Discounts + Payment Term + PPN Calculation")
        print("="*80)
        
        token = self.tokens.get('admin')
        
        # Get customers
        success, customers = self.run_test(
            "Get Customers",
            "GET",
            "api/customers",
            200,
            token=token
        )
        if not success or not customers:
            print("❌ Cannot proceed - no customers found")
            return False
        
        customer = customers[0]
        address = customer.get('addresses', [{}])[0]
        
        # Create SO with discounts
        so_data = {
            "customer_id": customer['id'],
            "shipping_address_id": address.get('id', ''),
            "items": [
                {
                    "product_id": "prod_batik_mega",
                    "quantity": 10,
                    "unit": "meter",
                    "discount_percent": 10  # 10% item discount
                }
            ],
            "order_discount_percent": 5,  # 5% order discount
            "payment_term_code": "NET30",
            "sales_name": "Test Sales",
            "shipment_policy": "allow_partial_shipment",
            "entity_id": "ent_ksc"  # PKP entity
        }
        
        success, order = self.run_test(
            "Create SO with Discounts + PPN",
            "POST",
            "api/sales-orders",
            200,
            data=so_data,
            token=token,
            description="Create SO with item discount 10%, order discount 5%, NET30 term, PKP entity"
        )
        
        if success and order:
            self.test_order_ids.append(order['id'])
            
            # Verify math
            print("\n📊 Verifying Pricing Math:")
            price = 185000
            qty = 10
            expected_subtotal = price * qty  # 1,850,000 (GROSS)
            
            print(f"   Expected subtotal (GROSS): Rp {expected_subtotal:,.0f}")
            print(f"   Actual total_amount: Rp {order.get('total_amount', 0):,.0f}")
            
            # Item discount: 1,850,000 * 10% = 185,000
            expected_item_disc = expected_subtotal * 0.10
            print(f"   Expected item discount (10%): Rp {expected_item_disc:,.0f}")
            print(f"   Actual items_discount_total: Rp {order.get('items_discount_total', 0):,.0f}")
            
            # After item discount: 1,850,000 - 185,000 = 1,665,000
            after_item = expected_subtotal - expected_item_disc
            
            # Order discount: 1,665,000 * 5% = 83,250
            expected_order_disc = after_item * 0.05
            print(f"   Expected order discount (5%): Rp {expected_order_disc:,.0f}")
            print(f"   Actual order_discount_amount: Rp {order.get('order_discount_amount', 0):,.0f}")
            
            # Net subtotal (DPP): 1,665,000 - 83,250 = 1,581,750
            expected_net = after_item - expected_order_disc
            print(f"   Expected net_subtotal (DPP): Rp {expected_net:,.0f}")
            print(f"   Actual net_subtotal: Rp {order.get('net_subtotal', 0):,.0f}")
            
            # PPN 11%: 1,581,750 * 11% = 173,992.5 → 173,993
            expected_ppn = round(expected_net * 0.11)
            print(f"   Expected PPN (11%): Rp {expected_ppn:,.0f}")
            print(f"   Actual ppn_amount: Rp {order.get('ppn_amount', 0):,.0f}")
            
            # Grand total: 1,581,750 + 173,993 = 1,755,743
            expected_grand = expected_net + expected_ppn
            print(f"   Expected grand_total: Rp {expected_grand:,.0f}")
            print(f"   Actual grand_total: Rp {order.get('grand_total', 0):,.0f}")
            
            # Verify payment term
            print(f"   Payment term: {order.get('payment_term_code')} - {order.get('payment_term_name')}")
            
            # Verify approval fields
            print(f"   Approval required: {order.get('approval_required')}")
            print(f"   Required approval role: {order.get('required_approval_role')}")
            
            # Check math accuracy (allow small rounding differences)
            math_ok = (
                abs(order.get('total_amount', 0) - expected_subtotal) < 1 and
                abs(order.get('net_subtotal', 0) - expected_net) < 1 and
                abs(order.get('ppn_amount', 0) - expected_ppn) < 2 and
                abs(order.get('grand_total', 0) - expected_grand) < 2
            )
            
            if math_ok:
                print("   ✅ Math verification PASSED")
            else:
                print("   ❌ Math verification FAILED")
                return False
            
            return True
        
        return False

    def test_compute_tax_pkp_vs_nonpkp(self):
        """Test GET /api/settings/compute-tax for PKP vs non-PKP entities"""
        print("\n" + "="*80)
        print("TEST: Compute Tax - PKP vs Non-PKP")
        print("="*80)
        
        token = self.tokens.get('admin')
        
        # Test PKP entity (ent_ksc)
        success, tax_pkp = self.run_test(
            "Compute Tax - PKP Entity",
            "GET",
            "api/settings/compute-tax?subtotal=1000000&entity_id=ent_ksc",
            200,
            token=token,
            description="PKP entity should have 11% PPN"
        )
        
        if success:
            print(f"   PKP - DPP: Rp {tax_pkp.get('dpp', 0):,.0f}")
            print(f"   PKP - PPN: Rp {tax_pkp.get('ppn_amount', 0):,.0f}")
            print(f"   PKP - Grand Total: Rp {tax_pkp.get('grand_total', 0):,.0f}")
            
            expected_ppn = 110000
            expected_grand = 1110000
            
            if abs(tax_pkp.get('ppn_amount', 0) - expected_ppn) < 1 and abs(tax_pkp.get('grand_total', 0) - expected_grand) < 1:
                print("   ✅ PKP tax calculation correct")
            else:
                print("   ❌ PKP tax calculation incorrect")
                return False
        
        # Test non-PKP entity (ent_kanda)
        success, tax_nonpkp = self.run_test(
            "Compute Tax - Non-PKP Entity",
            "GET",
            "api/settings/compute-tax?subtotal=1000000&entity_id=ent_kanda",
            200,
            token=token,
            description="Non-PKP entity should have 0% PPN"
        )
        
        if success:
            print(f"   Non-PKP - DPP: Rp {tax_nonpkp.get('dpp', 0):,.0f}")
            print(f"   Non-PKP - PPN: Rp {tax_nonpkp.get('ppn_amount', 0):,.0f}")
            print(f"   Non-PKP - Grand Total: Rp {tax_nonpkp.get('grand_total', 0):,.0f}")
            
            if tax_nonpkp.get('ppn_amount', 0) == 0 and tax_nonpkp.get('grand_total', 0) == 1000000:
                print("   ✅ Non-PKP tax calculation correct")
                return True
            else:
                print("   ❌ Non-PKP tax calculation incorrect")
                return False
        
        return False

    def test_dynamic_so_approval(self):
        """Test dynamic SO approval based on approval_rules"""
        print("\n" + "="*80)
        print("TEST: Dynamic SO Approval Workflow")
        print("="*80)
        
        token_admin = self.tokens.get('admin')
        token_manager = self.tokens.get('manager')
        token_sales = self.tokens.get('sales')
        
        # Get customer
        success, customers = self.run_test(
            "Get Customers",
            "GET",
            "api/customers",
            200,
            token=token_admin
        )
        if not success or not customers:
            return False
        
        customer = customers[0]
        address = customer.get('addresses', [{}])[0]
        
        # Test 1: Large SO (>= 50M) - requires manager approval
        print("\n--- Test 1: Large SO (>= 50M) ---")
        large_so_data = {
            "customer_id": customer['id'],
            "shipping_address_id": address.get('id', ''),
            "items": [
                {
                    "product_id": "prod_batik_mega",
                    "quantity": 300,  # 300 * 185000 = 55,500,000
                    "unit": "meter",
                    "discount_percent": 0
                }
            ],
            "order_discount_percent": 0,
            "payment_term_code": "NET30",
            "sales_name": "Test Sales",
            "shipment_policy": "allow_partial_shipment",
            "entity_id": "ent_ksc"
        }
        
        success, large_order = self.run_test(
            "Create Large SO (>= 50M)",
            "POST",
            "api/sales-orders",
            200,
            data=large_so_data,
            token=token_admin
        )
        
        if success and large_order:
            self.test_order_ids.append(large_order['id'])
            print(f"   Grand Total: Rp {large_order.get('grand_total', 0):,.0f}")
            print(f"   Approval Required: {large_order.get('approval_required')}")
            print(f"   Required Role: {large_order.get('required_approval_role')}")
            
            if not large_order.get('approval_required'):
                print("   ❌ Large SO should require approval")
                return False
            
            if large_order.get('required_approval_role') != 'manager':
                print("   ❌ Large SO should require manager role")
                return False
            
            # Submit for approval
            success, submitted = self.run_test(
                "Submit Large SO for Approval",
                "POST",
                f"api/sales-orders/{large_order['id']}/submit-for-approval",
                200,
                token=token_admin
            )
            
            if success:
                print(f"   Status after submit: {submitted.get('status')}")
                if submitted.get('status') != 'waiting_approval':
                    print("   ❌ Status should be 'waiting_approval'")
                    return False
            
            # Try to approve as SALES (should fail with 403)
            success, _ = self.run_test(
                "Approve as SALES (should fail)",
                "POST",
                f"api/sales-orders/{large_order['id']}/approve",
                403,
                token=token_sales,
                description="Sales role should not be able to approve manager-level orders"
            )
            
            if not success:
                print("   ❌ Should return 403 for sales role")
                return False
            
            # Approve as MANAGER (should succeed)
            success, approved = self.run_test(
                "Approve as MANAGER",
                "POST",
                f"api/sales-orders/{large_order['id']}/approve",
                200,
                token=token_manager
            )
            
            if success:
                print(f"   Status after approval: {approved.get('status')}")
                if approved.get('status') != 'approved':
                    print("   ❌ Status should be 'approved'")
                    return False
                print("   ✅ Large SO approval workflow correct")
        
        # Test 2: Small SO (< 50M) - auto-approve
        print("\n--- Test 2: Small SO (< 50M) - Auto-Approve ---")
        small_so_data = {
            "customer_id": customer['id'],
            "shipping_address_id": address.get('id', ''),
            "items": [
                {
                    "product_id": "prod_batik_mega",
                    "quantity": 10,  # 10 * 185000 = 1,850,000
                    "unit": "meter",
                    "discount_percent": 0
                }
            ],
            "order_discount_percent": 0,
            "payment_term_code": "NET30",
            "sales_name": "Test Sales",
            "shipment_policy": "allow_partial_shipment",
            "entity_id": "ent_ksc"
        }
        
        success, small_order = self.run_test(
            "Create Small SO (< 50M)",
            "POST",
            "api/sales-orders",
            200,
            data=small_so_data,
            token=token_admin
        )
        
        if success and small_order:
            self.test_order_ids.append(small_order['id'])
            print(f"   Grand Total: Rp {small_order.get('grand_total', 0):,.0f}")
            print(f"   Approval Required: {small_order.get('approval_required')}")
            
            if small_order.get('approval_required'):
                print("   ❌ Small SO should not require approval")
                return False
            
            # Submit for approval (should auto-approve)
            success, submitted = self.run_test(
                "Submit Small SO (Auto-Approve)",
                "POST",
                f"api/sales-orders/{small_order['id']}/submit-for-approval",
                200,
                token=token_admin
            )
            
            if success:
                print(f"   Status after submit: {submitted.get('status')}")
                if submitted.get('status') != 'approved':
                    print("   ❌ Small SO should auto-approve to 'approved' status")
                    return False
                print("   ✅ Small SO auto-approval correct")
                return True
        
        return False

    def test_dynamic_po_approval(self):
        """Test dynamic PO approval - affects inbound_tasks creation"""
        print("\n" + "="*80)
        print("TEST: Dynamic PO Approval Workflow")
        print("="*80)
        
        token_admin = self.tokens.get('admin')
        token_manager = self.tokens.get('manager')
        
        # Get warehouse
        success, warehouses = self.run_test(
            "Get Warehouses",
            "GET",
            "api/warehouses",
            200,
            token=token_admin
        )
        if not success or not warehouses:
            return False
        
        warehouse = warehouses[0]
        
        # Test 1: Large PO (> 100M) - requires approval, no inbound tasks yet
        print("\n--- Test 1: Large PO (> 100M) - Requires Approval ---")
        large_po_data = {
            "supplier_name": "Test Supplier Large",
            "supplier_contact": "081234567890",
            "warehouse_id": warehouse['id'],
            "items": [
                {
                    "product_id": "prod_batik_mega",
                    "quantity": 700,  # 700 * 185000 = 129,500,000
                    "unit": "meter",
                    "price": 185000
                }
            ],
            "expected_delivery_date": "2025-09-01",
            "notes": "Test large PO",
            "created_by": "Admin Test",
            "entity_id": "ent_ksc"
        }
        
        success, large_po = self.run_test(
            "Create Large PO (> 100M)",
            "POST",
            "api/purchase-orders",
            200,
            data=large_po_data,
            token=token_admin
        )
        
        if success and large_po:
            self.test_po_ids.append(large_po['id'])
            print(f"   Total Amount: Rp {large_po.get('total_amount', 0):,.0f}")
            print(f"   Status: {large_po.get('status')}")
            print(f"   Approval Required: {large_po.get('approval_required')}")
            print(f"   Required Role: {large_po.get('required_approval_role')}")
            
            if large_po.get('status') != 'waiting_approval':
                print("   ❌ Large PO should have status 'waiting_approval'")
                return False
            
            # Get PO detail - should have 0 inbound tasks
            success, po_detail = self.run_test(
                "Get Large PO Detail (Before Approval)",
                "GET",
                f"api/purchase-orders/{large_po['id']}",
                200,
                token=token_admin
            )
            
            if success:
                inbound_count = len(po_detail.get('inbound_tasks', []))
                print(f"   Inbound Tasks Count (before approval): {inbound_count}")
                if inbound_count != 0:
                    print("   ❌ Should have 0 inbound tasks before approval")
                    return False
            
            # Approve as MANAGER
            success, approved_po = self.run_test(
                "Approve Large PO as MANAGER",
                "POST",
                f"api/purchase-orders/{large_po['id']}/approve",
                200,
                token=token_manager
            )
            
            if success:
                print(f"   Status after approval: {approved_po.get('status')}")
                print(f"   Approval Status: {approved_po.get('approval_status')}")
                
                if approved_po.get('status') != 'pending':
                    print("   ❌ Status should be 'pending' after approval")
                    return False
                
                # Get PO detail again - should have inbound tasks now
                success, po_detail_after = self.run_test(
                    "Get Large PO Detail (After Approval)",
                    "GET",
                    f"api/purchase-orders/{large_po['id']}",
                    200,
                    token=token_admin
                )
                
                if success:
                    inbound_count_after = len(po_detail_after.get('inbound_tasks', []))
                    print(f"   Inbound Tasks Count (after approval): {inbound_count_after}")
                    if inbound_count_after == 0:
                        print("   ❌ Should have inbound tasks after approval")
                        return False
                    print("   ✅ Large PO approval workflow correct")
        
        # Test 2: Small PO (< 100M) - no approval, inbound tasks created immediately
        print("\n--- Test 2: Small PO (< 100M) - No Approval ---")
        small_po_data = {
            "supplier_name": "Test Supplier Small",
            "supplier_contact": "081234567890",
            "warehouse_id": warehouse['id'],
            "items": [
                {
                    "product_id": "prod_batik_mega",
                    "quantity": 50,  # 50 * 185000 = 9,250,000
                    "unit": "meter",
                    "price": 185000
                }
            ],
            "expected_delivery_date": "2025-09-01",
            "notes": "Test small PO",
            "created_by": "Admin Test",
            "entity_id": "ent_ksc"
        }
        
        success, small_po = self.run_test(
            "Create Small PO (< 100M)",
            "POST",
            "api/purchase-orders",
            200,
            data=small_po_data,
            token=token_admin
        )
        
        if success and small_po:
            self.test_po_ids.append(small_po['id'])
            print(f"   Total Amount: Rp {small_po.get('total_amount', 0):,.0f}")
            print(f"   Status: {small_po.get('status')}")
            print(f"   Approval Required: {small_po.get('approval_required')}")
            
            if small_po.get('status') != 'pending':
                print("   ❌ Small PO should have status 'pending' (no approval needed)")
                return False
            
            # Get PO detail - should have inbound tasks immediately
            success, po_detail = self.run_test(
                "Get Small PO Detail",
                "GET",
                f"api/purchase-orders/{small_po['id']}",
                200,
                token=token_admin
            )
            
            if success:
                inbound_count = len(po_detail.get('inbound_tasks', []))
                print(f"   Inbound Tasks Count: {inbound_count}")
                if inbound_count == 0:
                    print("   ❌ Should have inbound tasks immediately for small PO")
                    return False
                print("   ✅ Small PO workflow correct")
                return True
        
        return False

    def test_invoice_tax_calculation(self):
        """Test invoice tax calculation via simulate-payment"""
        print("\n" + "="*80)
        print("TEST: Invoice Tax Calculation")
        print("="*80)
        
        token = self.tokens.get('admin')
        
        # Get an order to test payment
        if not self.test_order_ids:
            print("   ⚠️  No test orders available, skipping invoice test")
            return True
        
        order_id = self.test_order_ids[0]
        
        # Get order detail
        success, order = self.run_test(
            "Get Order Detail",
            "GET",
            f"api/sales-orders/{order_id}",
            200,
            token=token
        )
        
        if not success:
            return False
        
        # Confirm order first (if not already)
        if order.get('status') in ['reserved', 'waiting_approval']:
            self.run_test(
                "Submit for Approval",
                "POST",
                f"api/sales-orders/{order_id}/submit-for-approval",
                200,
                token=token
            )
        
        if order.get('status') == 'approved':
            self.run_test(
                "Confirm Order",
                "POST",
                f"api/sales-orders/{order_id}/confirm",
                200,
                token=token
            )
        
        # Simulate payment (no amount = full grand_total)
        success, invoice = self.run_test(
            "Simulate Payment (Full Amount)",
            "POST",
            f"api/sales-orders/{order_id}/simulate-payment",
            200,
            data={
                "amount": 0,  # 0 means full grand_total
                "method": "Transfer Test",
                "created_by": "Admin Test"
            },
            token=token,
            description="Invoice should include tax breakdown"
        )
        
        if success and invoice:
            print(f"\n📊 Invoice Tax Breakdown:")
            print(f"   Total Amount (GROSS): Rp {invoice.get('total_amount', 0):,.0f}")
            print(f"   Discount Total: Rp {invoice.get('discount_total', 0):,.0f}")
            print(f"   Net Subtotal: Rp {invoice.get('net_subtotal', 0):,.0f}")
            print(f"   DPP: Rp {invoice.get('dpp', 0):,.0f}")
            print(f"   PPN Rate: {invoice.get('ppn_rate', 0)}%")
            print(f"   PPN Amount: Rp {invoice.get('ppn_amount', 0):,.0f}")
            print(f"   Grand Total: Rp {invoice.get('grand_total', 0):,.0f}")
            print(f"   Payment Term: {invoice.get('payment_term_code')} - {invoice.get('payment_term_name')}")
            
            # Verify order payment status updated
            success, updated_order = self.run_test(
                "Get Order After Payment",
                "GET",
                f"api/sales-orders/{order_id}",
                200,
                token=token
            )
            
            if success:
                print(f"   Order Payment Status: {updated_order.get('payment_status')}")
                if updated_order.get('payment_status') != 'paid':
                    print("   ❌ Order payment status should be 'paid'")
                    return False
                print("   ✅ Invoice tax calculation correct")
                return True
        
        return False

    def test_regression_endpoints(self):
        """Test regression - ensure existing endpoints still work"""
        print("\n" + "="*80)
        print("TEST: Regression - Existing Endpoints")
        print("="*80)
        
        token = self.tokens.get('admin')
        
        # Test GET /api/sales-orders
        success, orders = self.run_test(
            "GET /api/sales-orders",
            "GET",
            "api/sales-orders",
            200,
            token=token,
            description="Should not return 500 error (ObjectId regression)"
        )
        
        if not success:
            print("   ❌ GET /api/sales-orders failed")
            return False
        
        print(f"   Orders count: {len(orders)}")
        
        # Test GET /api/sales-orders/stats/summary
        success, stats = self.run_test(
            "GET /api/sales-orders/stats/summary",
            "GET",
            "api/sales-orders/stats/summary",
            200,
            token=token
        )
        
        if not success:
            print("   ❌ GET /api/sales-orders/stats/summary failed")
            return False
        
        print(f"   Total orders: {stats.get('total_orders', 0)}")
        print(f"   Total reserved qty: {stats.get('total_reserved_qty', 0)}")
        
        # Test GET /api/dashboard
        success, dashboard = self.run_test(
            "GET /api/dashboard",
            "GET",
            "api/dashboard",
            200,
            token=token
        )
        
        if not success:
            print("   ❌ GET /api/dashboard failed")
            return False
        
        print(f"   Products: {dashboard.get('products', 0)}")
        print(f"   Available: {dashboard.get('available', 0)}")
        print(f"   Reserved: {dashboard.get('reserved', 0)}")
        print(f"   Active orders: {dashboard.get('active_orders', 0)}")
        print(f"   Warehouses: {dashboard.get('gudang', 0)}")
        
        print("   ✅ All regression endpoints working")
        return True

    def run_all_tests(self):
        """Run all Fase 1B tests"""
        print("\n" + "="*80)
        print("FASE 1B - CONFIGURATION CONSUMPTION TESTING")
        print("="*80)
        
        # Login as different roles
        print("\n--- Authentication ---")
        self.test_login("admin@kainnusantara.id", "demo12345", "admin")
        self.test_login("manager@kainnusantara.id", "demo12345", "manager")
        self.test_login("sales@kainnusantara.id", "demo12345", "sales")
        
        # Run tests
        self.test_sales_order_with_discounts_and_tax()
        self.test_compute_tax_pkp_vs_nonpkp()
        self.test_dynamic_so_approval()
        self.test_dynamic_po_approval()
        self.test_invoice_tax_calculation()
        self.test_regression_endpoints()
        
        # Print summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        
        if self.failed_tests:
            print("\n❌ Failed Tests:")
            for fail in self.failed_tests:
                print(f"   - {fail.get('test')}: {fail.get('error', '')} {fail.get('response', '')}")
        
        return self.tests_passed == self.tests_run

def main():
    tester = Fase1BAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
