"""R4 — Comprehensive Backend Testing for Retur & Refunds with Supplier RMA lifecycle.

Tests all R4 features:
1. Chain: Sales Return → Purchase Return (create-purchase-return endpoint)
2. RMA Approve: Gate (status approved, no stock/DN yet)
3. RMA Ship+Accept: Ship → Accept (outcome) → stock adjusted + debit note
4. RMA Reject→Goods Back+Regrade: Reject → Goods back with regrade
5. Import Policy (§J): Import suppliers cannot be returned to (unless bypass)
6. Direct PR flow: Non-chain PR still works
7. Guards: Various validation checks
8. Dashboard Integrity: Metrics match inventory balances
"""
import os
import sys
import requests
from datetime import datetime

# Use public endpoint from frontend/.env
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://return-reconcile-r3.preview.emergentagent.com")
API = f"{BASE_URL}/api"

# Test credentials from review request
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}

class R4Tester:
    def __init__(self):
        self.token = None
        self.headers = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        
    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{API}/{endpoint}"
        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=self.headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=self.headers, timeout=30)
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                return True, response.json() if response.text else {}
            else:
                self.tests_failed += 1
                msg = f"Expected {expected_status}, got {response.status_code}"
                print(f"❌ Failed - {msg}")
                print(f"   Response: {response.text[:200]}")
                self.failures.append({"test": name, "error": msg, "response": response.text[:200]})
                return False, {}
        except Exception as e:
            self.tests_failed += 1
            msg = f"Error: {str(e)}"
            print(f"❌ Failed - {msg}")
            self.failures.append({"test": name, "error": msg})
            return False, {}
    
    def login(self):
        """Login and get token"""
        print("\n🔐 Logging in...")
        success, response = self.run_test("Login", "POST", "auth/login", 200, data=ADMIN)
        if success and 'token' in response:
            self.token = response['token']
            self.headers = {'Authorization': f'Bearer {self.token}'}
            print(f"✅ Logged in successfully")
            return True
        print(f"❌ Login failed")
        return False
    
    def get_eligible_order(self):
        """Get an eligible sales order for return"""
        print("\n📦 Finding eligible sales order...")
        success, response = self.run_test("Get Sales Orders", "GET", "sales-orders", 200)
        if not success:
            return None
        
        orders = response.get('items', []) if isinstance(response, dict) else response
        eligible_statuses = {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
        
        for order in orders:
            if order.get('status') in eligible_statuses:
                items = order.get('items', [])
                if items and any(float(it.get('quantity', 0) or 0) >= 1 for it in items):
                    print(f"✅ Found eligible order: {order.get('number')}")
                    return order
        
        print("❌ No eligible orders found")
        return None
    
    def create_settled_sales_return(self, order, warehouse_id):
        """Create a sales return, inspect, and settle with refund"""
        print(f"\n📝 Creating settled sales return from order {order.get('number')}...")
        
        # Find item with quantity >= 1
        items = [it for it in order.get('items', []) if float(it.get('quantity', 0) or 0) >= 1]
        if not items:
            print("❌ No items with quantity >= 1")
            return None, []
        
        item = items[0]
        
        # Create return
        sr_data = {
            "order_id": order['id'],
            "return_type": "retur",
            "items": [{
                "product_id": item['product_id'],
                "product_name": item.get('product_name', ''),
                "quantity_returned": 1,
                "unit": item.get('unit', 'meter'),
                "reason": "R4 test",
                "condition": "ok"
            }],
            "notes": "R4 comprehensive test",
            "submit_now": True
        }
        
        success, sr = self.run_test("Create Sales Return", "POST", "sales-returns", 200, data=sr_data)
        if not success:
            return None, []
        
        sr_id = sr['id']
        
        # Approve
        self.run_test("Approve Sales Return", "POST", f"sales-returns/{sr_id}/approve", 200, data={"notes": ""})
        
        # Start inspection
        self.run_test("Start Inspection", "POST", f"sales-returns/{sr_id}/inspect/start", 200)
        
        # Complete inspection
        inspect_data = {
            "inspections": [{
                "index": 0,
                "defects": [{"point_value": 1, "count": 2}],
                "condition": "ok",
                "accepted_qty": 1
            }],
            "notes": "4-point inspection"
        }
        self.run_test("Complete Inspection", "POST", f"sales-returns/{sr_id}/inspect/complete", 200, data=inspect_data)
        
        # Settle with refund
        settle_data = {
            "outcome": "refund",
            "return_warehouse_id": warehouse_id,
            "item_decisions": [],
            "notes": "R4 test settle"
        }
        success, settled = self.run_test("Settle Sales Return", "POST", f"sales-returns/{sr_id}/settle", 200, data=settle_data)
        
        # Get quarantine rolls
        success, quarantine = self.run_test("Get Quarantine Rolls", "GET", f"sales-returns/{sr_id}/quarantine", 200)
        rolls = quarantine if isinstance(quarantine, list) else []
        
        print(f"✅ Created settled sales return with {len(rolls)} quarantine rolls")
        return settled, rolls
    
    def test_chain_and_rma_accept(self, sr, rolls, supplier_id):
        """Test 1: Chain SR→PR + RMA lifecycle (approve→ship→accept)"""
        print("\n" + "="*60)
        print("TEST 1: Chain Sales Return → Purchase Return + RMA Accept")
        print("="*60)
        
        sr_id = sr['id']
        
        # Create purchase return from sales return
        pr_data = {
            "supplier_id": supplier_id,
            "reason": "Defective from customer",
            "notes": "R4 chain test"
        }
        success, pr = self.run_test(
            "Create Purchase Return from Sales Return",
            "POST",
            f"sales-returns/{sr_id}/create-purchase-return",
            200,
            data=pr_data
        )
        
        if not success:
            return None
        
        pr_id = pr['id']
        
        # Verify PR fields
        if pr.get('supplier_flow') is True:
            print("✅ PR supplier_flow = True")
            self.tests_passed += 1
        else:
            print(f"❌ PR supplier_flow = {pr.get('supplier_flow')}, expected True")
            self.tests_failed += 1
            self.failures.append({"test": "PR supplier_flow", "error": f"Got {pr.get('supplier_flow')}"})
        
        if pr.get('supplier_status') == 'requested_supplier':
            print("✅ PR supplier_status = requested_supplier")
            self.tests_passed += 1
        else:
            print(f"❌ PR supplier_status = {pr.get('supplier_status')}, expected requested_supplier")
            self.tests_failed += 1
            self.failures.append({"test": "PR supplier_status", "error": f"Got {pr.get('supplier_status')}"})
        
        if pr.get('origin_sales_return_id') == sr_id:
            print("✅ PR origin_sales_return_id linked")
            self.tests_passed += 1
        else:
            print(f"❌ PR origin_sales_return_id not linked")
            self.tests_failed += 1
            self.failures.append({"test": "PR origin link", "error": "Not linked"})
        
        # Verify 2-way link
        success, sr_after = self.run_test("Get Sales Return After Link", "GET", f"sales-returns/{sr_id}", 200)
        if success and sr_after.get('linked_purchase_return_id') == pr_id:
            print("✅ SR linked_purchase_return_id (2-way link)")
            self.tests_passed += 1
        else:
            print(f"❌ SR 2-way link failed")
            self.tests_failed += 1
            self.failures.append({"test": "SR 2-way link", "error": "Not linked"})
        
        # Approve (RMA gate)
        success, approved = self.run_test("Approve PR (RMA Gate)", "POST", f"purchase-returns/{pr_id}/approve", 200, data={"notes": ""})
        
        if approved.get('status') == 'approved':
            print("✅ Approve → status = approved")
            self.tests_passed += 1
        else:
            print(f"❌ Status = {approved.get('status')}, expected approved")
            self.tests_failed += 1
        
        if not approved.get('stock_adjusted'):
            print("✅ Approve RMA: stock NOT adjusted yet")
            self.tests_passed += 1
        else:
            print(f"❌ Stock adjusted = {approved.get('stock_adjusted')}, expected False")
            self.tests_failed += 1
        
        if approved.get('supplier_status') == 'requested_supplier':
            print("✅ Approve RMA: supplier_status still requested_supplier")
            self.tests_passed += 1
        else:
            print(f"❌ supplier_status = {approved.get('supplier_status')}")
            self.tests_failed += 1
        
        if not approved.get('debit_note_number'):
            print("✅ Approve RMA: NO debit note yet")
            self.tests_passed += 1
        else:
            print(f"❌ Debit note = {approved.get('debit_note_number')}, expected empty")
            self.tests_failed += 1
        
        # Ship to supplier
        ship_data = {"carrier": "JNE", "tracking_no": "TRK123", "notes": "R4 test"}
        success, shipped = self.run_test("Ship to Supplier", "POST", f"purchase-returns/{pr_id}/ship-to-supplier", 200, data=ship_data)
        
        if shipped.get('supplier_status') == 'shipped_supplier':
            print("✅ Ship → supplier_status = shipped_supplier")
            self.tests_passed += 1
        else:
            print(f"❌ supplier_status = {shipped.get('supplier_status')}")
            self.tests_failed += 1
        
        # Supplier accept
        accept_data = {"outcome": "ap_credit", "notes": "Accepted"}
        success, accepted = self.run_test("Supplier Accept", "POST", f"purchase-returns/{pr_id}/supplier-accept", 200, data=accept_data)
        
        if accepted.get('supplier_status') == 'accepted_supplier':
            print("✅ Accept → supplier_status = accepted_supplier")
            self.tests_passed += 1
        else:
            print(f"❌ supplier_status = {accepted.get('supplier_status')}")
            self.tests_failed += 1
        
        if accepted.get('supplier_outcome') == 'ap_credit':
            print("✅ Accept → supplier_outcome = ap_credit")
            self.tests_passed += 1
        else:
            print(f"❌ supplier_outcome = {accepted.get('supplier_outcome')}")
            self.tests_failed += 1
        
        if accepted.get('debit_note_number'):
            print(f"✅ Accept → Debit note issued: {accepted.get('debit_note_number')}")
            self.tests_passed += 1
        else:
            print(f"❌ No debit note issued")
            self.tests_failed += 1
        
        if accepted.get('stock_adjusted') is True:
            print("✅ Accept → stock adjusted")
            self.tests_passed += 1
        else:
            print(f"❌ stock_adjusted = {accepted.get('stock_adjusted')}")
            self.tests_failed += 1
        
        # Verify roll status
        success, qrolls = self.run_test("Get Quarantine After Accept", "GET", f"sales-returns/{sr_id}/quarantine", 200)
        if success and qrolls:
            roll = qrolls[0] if isinstance(qrolls, list) else {}
            if roll.get('status') == 'returned_supplier':
                print("✅ Roll status = returned_supplier")
                self.tests_passed += 1
            else:
                print(f"❌ Roll status = {roll.get('status')}, expected returned_supplier")
                self.tests_failed += 1
        
        self.tests_run += 11  # Manual checks
        return pr_id
    
    def test_supplier_reject_goods_back(self, order, warehouse_id, supplier_id):
        """Test 2: Supplier reject → goods back + regrade"""
        print("\n" + "="*60)
        print("TEST 2: Supplier Reject → Goods Back + Regrade")
        print("="*60)
        
        # Create another settled return
        sr2, rolls2 = self.create_settled_sales_return(order, warehouse_id)
        if not sr2 or not rolls2:
            print("❌ Failed to create second sales return")
            return
        
        sr2_id = sr2['id']
        roll2 = rolls2[0]
        
        # Create PR
        pr_data = {"supplier_id": supplier_id, "reason": "Test reject", "notes": "R4 reject test"}
        success, pr2 = self.run_test("Create PR for Reject Test", "POST", f"sales-returns/{sr2_id}/create-purchase-return", 200, data=pr_data)
        if not success:
            return
        
        pr2_id = pr2['id']
        
        # Approve → Ship → Reject
        self.run_test("Approve PR2", "POST", f"purchase-returns/{pr2_id}/approve", 200, data={})
        self.run_test("Ship PR2", "POST", f"purchase-returns/{pr2_id}/ship-to-supplier", 200, data={})
        
        reject_data = {"reason": "Quality not as claimed"}
        success, rejected = self.run_test("Supplier Reject", "POST", f"purchase-returns/{pr2_id}/supplier-reject", 200, data=reject_data)
        
        if rejected.get('supplier_status') == 'rejected_supplier':
            print("✅ Reject → supplier_status = rejected_supplier")
            self.tests_passed += 1
        else:
            print(f"❌ supplier_status = {rejected.get('supplier_status')}")
            self.tests_failed += 1
        
        # Goods back with regrade
        goods_back_data = {
            "regrade": [{"roll_id": roll2['id'], "grade": "B"}],
            "notes": "Goods back test"
        }
        success, goods_back = self.run_test("Goods Back", "POST", f"purchase-returns/{pr2_id}/goods-back", 200, data=goods_back_data)
        
        if goods_back.get('supplier_status') == 'goods_back':
            print("✅ Goods back → supplier_status = goods_back")
            self.tests_passed += 1
        else:
            print(f"❌ supplier_status = {goods_back.get('supplier_status')}")
            self.tests_failed += 1
        
        if not goods_back.get('debit_note_number'):
            print("✅ Goods back → NO debit note (as expected)")
            self.tests_passed += 1
        else:
            print(f"❌ Debit note issued: {goods_back.get('debit_note_number')}")
            self.tests_failed += 1
        
        # Verify roll status and grade
        success, qrolls2 = self.run_test("Get Quarantine After Goods Back", "GET", f"sales-returns/{sr2_id}/quarantine", 200)
        if success and qrolls2:
            roll = next((r for r in qrolls2 if r['id'] == roll2['id']), {})
            if roll.get('status') == 'available':
                print("✅ Roll status = available")
                self.tests_passed += 1
            else:
                print(f"❌ Roll status = {roll.get('status')}, expected available")
                self.tests_failed += 1
            
            if roll.get('grade') == 'B':
                print("✅ Roll grade = B (regraded)")
                self.tests_passed += 1
            else:
                print(f"❌ Roll grade = {roll.get('grade')}, expected B")
                self.tests_failed += 1
            
            if roll.get('regraded_from') == 'A':
                print("✅ Roll regraded_from = A")
                self.tests_passed += 1
            else:
                print(f"❌ Roll regraded_from = {roll.get('regraded_from')}, expected A")
                self.tests_failed += 1
        
        self.tests_run += 6  # Manual checks
    
    def test_import_policy(self, warehouse_id, product_id):
        """Test 3: Import policy enforcement (§J)"""
        print("\n" + "="*60)
        print("TEST 3: Import Policy (§J) Enforcement")
        print("="*60)
        
        # Create import supplier with returnable_to_supplier=false
        supplier_data = {
            "name": "R4 Test Import NonReturnable",
            "origin_type": "import",
            "country": "CN",
            "return_policy": {
                "returnable_to_supplier": False,
                "refund_modes": ["ap_credit"]
            }
        }
        success, imp_supplier = self.run_test("Create Import Supplier", "POST", "suppliers", 200, data=supplier_data)
        if not success:
            print("❌ Failed to create import supplier")
            return
        
        imp_id = imp_supplier['id']
        
        # Try to create PR without bypass (should fail)
        pr_data = {
            "supplier_id": imp_id,
            "warehouse_id": warehouse_id,
            "items": [{
                "product_id": product_id,
                "quantity": 1,
                "price": 1000,
                "reason": "cacat"
            }]
        }
        success, response = self.run_test("Create PR Import (should fail)", "POST", "purchase-returns", 400, data=pr_data)
        
        if not success:  # 400 is expected
            print("✅ Import policy blocked PR creation (400)")
            self.tests_passed += 1
        else:
            print("❌ Import policy did NOT block PR creation")
            self.tests_failed += 1
        
        # Try with bypass (should succeed)
        pr_data['bypass_import_policy'] = True
        success, response = self.run_test("Create PR Import with Bypass", "POST", "purchase-returns", 200, data=pr_data)
        
        if success:
            print("✅ Bypass import policy succeeded")
            self.tests_passed += 1
        else:
            print("❌ Bypass import policy failed")
            self.tests_failed += 1
        
        self.tests_run += 2  # Manual checks
    
    def test_direct_pr_flow(self, warehouse_id, supplier_id):
        """Test 4: Direct PR flow (non-chain)"""
        print("\n" + "="*60)
        print("TEST 4: Direct PR Flow (supplier_flow=false)")
        print("="*60)
        
        # Get available rolls
        success, balances = self.run_test("Get Inventory Balances", "GET", "inventory/balances", 200)
        if not success:
            print("❌ Failed to get inventory balances")
            return
        
        bals = balances.get('items', []) if isinstance(balances, dict) else balances
        seg = next((b for b in bals if float(b.get('available_qty', 0) or 0) >= 2), None)
        
        if not seg:
            print("⚠️  No segments with available_qty >= 2, skipping direct PR test")
            return
        
        # Get source rolls
        params = {
            "product_id": seg['product_id'],
            "warehouse_id": seg.get('warehouse_id'),
            "entity_id": seg.get('owner_entity_id')
        }
        success, src = self.run_test("Get Source Rolls", "GET", "purchase-returns/source-rolls", 200, params=params)
        
        if not success:
            print("❌ Failed to get source rolls")
            return
        
        rolls = src.get('rolls', []) if isinstance(src, dict) else []
        if not rolls:
            print("⚠️  No source rolls available, skipping direct PR test")
            return
        
        roll_id = rolls[0].get('id') or rolls[0].get('roll_id')
        
        # Create direct PR
        pr_data = {
            "supplier_id": supplier_id,
            "warehouse_id": seg.get('warehouse_id'),
            "entity_id": seg.get('owner_entity_id'),
            "submit_now": True,
            "items": [{
                "product_id": seg['product_id'],
                "quantity": 1,
                "roll_ids": [roll_id],
                "reason": "cacat"
            }]
        }
        success, direct_pr = self.run_test("Create Direct PR", "POST", "purchase-returns", 200, data=pr_data)
        if not success:
            return
        
        direct_pr_id = direct_pr['id']
        
        # Approve (should finalize immediately)
        success, approved = self.run_test("Approve Direct PR", "POST", f"purchase-returns/{direct_pr_id}/approve", 200, data={})
        
        if approved.get('status') == 'approved':
            print("✅ Direct PR → status = approved")
            self.tests_passed += 1
        else:
            print(f"❌ Status = {approved.get('status')}")
            self.tests_failed += 1
        
        if approved.get('debit_note_number'):
            print(f"✅ Direct PR → Debit note issued: {approved.get('debit_note_number')}")
            self.tests_passed += 1
        else:
            print(f"❌ No debit note issued")
            self.tests_failed += 1
        
        if approved.get('stock_adjusted') is True:
            print("✅ Direct PR → stock adjusted")
            self.tests_passed += 1
        else:
            print(f"❌ stock_adjusted = {approved.get('stock_adjusted')}")
            self.tests_failed += 1
        
        if approved.get('supplier_status') == 'accepted_supplier':
            print("✅ Direct PR → supplier_status = accepted_supplier")
            self.tests_passed += 1
        else:
            print(f"❌ supplier_status = {approved.get('supplier_status')}")
            self.tests_failed += 1
        
        self.tests_run += 4  # Manual checks
    
    def test_guards(self, order, warehouse_id, supplier_id):
        """Test 5: Guards and validation"""
        print("\n" + "="*60)
        print("TEST 5: Guards and Validation")
        print("="*60)
        
        # Create SR for guard tests
        sr3, rolls3 = self.create_settled_sales_return(order, warehouse_id)
        if not sr3:
            print("❌ Failed to create SR for guard tests")
            return
        
        # Create PR
        pr_data = {"supplier_id": supplier_id, "reason": "Guard test"}
        success, pr3 = self.run_test("Create PR for Guards", "POST", f"sales-returns/{sr3['id']}/create-purchase-return", 200, data=pr_data)
        if not success:
            return
        
        pr3_id = pr3['id']
        
        # Approve
        self.run_test("Approve PR3", "POST", f"purchase-returns/{pr3_id}/approve", 200, data={})
        
        # Try to accept before ship (should fail)
        success, response = self.run_test("Accept Before Ship (should fail)", "POST", f"purchase-returns/{pr3_id}/supplier-accept", 400, data={"outcome": "ap_credit"})
        if not success:  # 400 is expected
            print("✅ Guard: Cannot accept before ship")
            self.tests_passed += 1
        else:
            print("❌ Guard failed: Accepted before ship")
            self.tests_failed += 1
        
        # Try goods-back before reject (should fail)
        success, response = self.run_test("Goods Back Before Reject (should fail)", "POST", f"purchase-returns/{pr3_id}/goods-back", 400, data={})
        if not success:  # 400 is expected
            print("✅ Guard: Cannot goods-back before reject")
            self.tests_passed += 1
        else:
            print("❌ Guard failed: Goods back before reject")
            self.tests_failed += 1
        
        self.tests_run += 2  # Manual checks
    
    def test_dashboard_integrity(self):
        """Test 6: Dashboard metrics match inventory balances"""
        print("\n" + "="*60)
        print("TEST 6: Dashboard Integrity")
        print("="*60)
        
        # Get dashboard metrics
        success, dashboard = self.run_test("Get Dashboard", "GET", "dashboard", 200)
        if not success:
            print("❌ Failed to get dashboard")
            return
        
        # Get inventory balances
        success, balances = self.run_test("Get Inventory Balances", "GET", "inventory/balances", 200)
        if not success:
            print("❌ Failed to get inventory balances")
            return
        
        bals = balances.get('items', []) if isinstance(balances, dict) else balances
        total_available = sum(float(b.get('available_qty', 0) or 0) for b in bals)
        
        dashboard_available = float(dashboard.get('metrics', {}).get('available_qty', 0) or 0)
        
        if abs(dashboard_available - total_available) < 0.01:
            print(f"✅ Dashboard integrity: available_qty matches ({dashboard_available:.2f})")
            self.tests_passed += 1
        else:
            print(f"❌ Dashboard integrity failed: dashboard={dashboard_available:.2f}, sum={total_available:.2f}")
            self.tests_failed += 1
        
        self.tests_run += 1  # Manual check

def main():
    print("\n" + "="*60)
    print("R4 COMPREHENSIVE BACKEND TESTING")
    print("="*60)
    print(f"API: {API}")
    print(f"Time: {datetime.now().isoformat()}")
    
    tester = R4Tester()
    
    # Login
    if not tester.login():
        print("\n❌ Login failed, cannot proceed")
        sys.exit(1)
    
    # Get prerequisites
    print("\n📋 Getting prerequisites...")
    success, warehouses = tester.run_test("Get Warehouses", "GET", "warehouses", 200)
    if not success or not warehouses:
        print("❌ No warehouses found")
        sys.exit(1)
    
    whs = warehouses if isinstance(warehouses, list) else warehouses.get('items', [])
    warehouse_id = whs[0]['id'] if whs else None
    
    success, suppliers = tester.run_test("Get Suppliers", "GET", "suppliers", 200)
    if not success or not suppliers:
        print("❌ No suppliers found")
        sys.exit(1)
    
    sups = suppliers if isinstance(suppliers, list) else suppliers.get('items', [])
    local_supplier = next((s for s in sups if s.get('origin_type', 'local') != 'import'), None)
    
    if not local_supplier:
        print("❌ No local supplier found")
        sys.exit(1)
    
    supplier_id = local_supplier['id']
    
    # Get eligible order
    order = tester.get_eligible_order()
    if not order:
        print("❌ No eligible order found")
        sys.exit(1)
    
    product_id = order['items'][0]['product_id']
    
    # Run tests
    print("\n" + "="*60)
    print("STARTING R4 TESTS")
    print("="*60)
    
    # Test 1: Chain + RMA Accept
    sr1, rolls1 = tester.create_settled_sales_return(order, warehouse_id)
    if sr1 and rolls1:
        tester.test_chain_and_rma_accept(sr1, rolls1, supplier_id)
    
    # Test 2: Supplier Reject + Goods Back
    tester.test_supplier_reject_goods_back(order, warehouse_id, supplier_id)
    
    # Test 3: Import Policy
    tester.test_import_policy(warehouse_id, product_id)
    
    # Test 4: Direct PR Flow
    tester.test_direct_pr_flow(warehouse_id, supplier_id)
    
    # Test 5: Guards
    tester.test_guards(order, warehouse_id, supplier_id)
    
    # Test 6: Dashboard Integrity
    tester.test_dashboard_integrity()
    
    # Print results
    print("\n" + "="*60)
    print("TEST RESULTS")
    print("="*60)
    print(f"Total Tests: {tester.tests_run}")
    print(f"✅ Passed: {tester.tests_passed}")
    print(f"❌ Failed: {tester.tests_failed}")
    print(f"Success Rate: {(tester.tests_passed/tester.tests_run*100):.1f}%")
    
    if tester.failures:
        print("\n" + "="*60)
        print("FAILURES")
        print("="*60)
        for i, failure in enumerate(tester.failures[:10], 1):
            print(f"\n{i}. {failure['test']}")
            print(f"   Error: {failure['error']}")
            if 'response' in failure:
                print(f"   Response: {failure['response']}")
    
    return 0 if tester.tests_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
