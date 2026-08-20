"""Backend API Testing for Kain Nusantara - Fase 3 Purchasing Module RE-TEST"""
import requests
import sys
from datetime import datetime

class Fase3PurchasingTester:
    def __init__(self, base_url="https://po-pdf-sender.preview.emergentagent.com"):
        self.base_url = base_url
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

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
                    "response": response.text[:200]
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

    # ── FIX VERIFICATION #1: PO Approval Creates Inbound Tasks ──────────────────
    
    def test_fix1_po_approval_seeded_po(self):
        """Test FIX #1: Approve seeded PO-00007 (id 'po_007') as ADMIN"""
        token = self.tokens.get('admin')
        if not token:
            print("⚠️  Skipping - no admin token")
            return False
        
        print(f"\n{'='*70}")
        print("FIX VERIFICATION #1: PO Approval Creates Inbound Tasks (Seeded PO)")
        print(f"{'='*70}")
        
        # Step 1: Get PO-00007 details
        success1, po = self.run_test(
            "Get seeded PO-00007 (po_007)",
            "GET",
            "api/purchase-orders/po_007",
            200,
            token=token,
            description="Check seeded PO status before approval"
        )
        
        if success1:
            print(f"   ✓ PO Number: {po.get('po_number')}")
            print(f"   ✓ Status: {po.get('status')}")
            print(f"   ✓ Approval Status: {po.get('approval_status')}")
            print(f"   ✓ Total Amount: Rp {po.get('total_amount'):,.0f}")
            print(f"   ✓ Supplier: {po.get('supplier_name')}")
            print(f"   ✓ Warehouse: {po.get('warehouse_name', 'N/A')}")
            
            if po.get('status') != 'waiting_approval':
                print(f"   ⚠️  PO is not in waiting_approval status, current: {po.get('status')}")
                # Continue anyway to test the endpoint
        
        # Step 2: Approve the PO
        success2, approved_po = self.run_test(
            "Approve PO-00007 as ADMIN",
            "POST",
            "api/purchase-orders/po_007/approve",
            200,
            token=token,
            description="Should return 200 with status='pending' and approval_status='approved'"
        )
        
        if success2:
            new_status = approved_po.get('status')
            approval_status = approved_po.get('approval_status')
            print(f"   ✓ New Status: {new_status}")
            print(f"   ✓ Approval Status: {approval_status}")
            print(f"   ✓ Approved By: {approved_po.get('approved_by', 'N/A')}")
            
            if new_status == 'pending' and approval_status == 'approved':
                print(f"   ✅ PO approval successful with correct status")
            else:
                print(f"   ❌ Status mismatch: expected status='pending' & approval_status='approved'")
                return False
        else:
            print(f"   ❌ PO approval failed")
            return False
        
        # Step 3: Verify inbound tasks were created
        success3, tasks = self.run_test(
            "Get inbound tasks for po_007",
            "GET",
            "api/inbound/tasks",
            200,
            token=token,
            description="Verify inbound tasks created with warehouse_name"
        )
        
        if success3:
            po_tasks = [t for t in tasks if t.get('po_id') == 'po_007']
            print(f"   ✓ Found {len(po_tasks)} inbound tasks for po_007")
            
            if len(po_tasks) == 0:
                print(f"   ❌ No inbound tasks created for po_007")
                return False
            
            # Check warehouse_name is present and not empty
            tasks_with_warehouse = [t for t in po_tasks if t.get('warehouse_name')]
            print(f"   ✓ Tasks with warehouse_name: {len(tasks_with_warehouse)}/{len(po_tasks)}")
            
            if len(tasks_with_warehouse) == len(po_tasks):
                print(f"   ✅ All inbound tasks have warehouse_name")
                # Show sample task
                sample = po_tasks[0]
                print(f"   ✓ Sample task: {sample.get('id')}")
                print(f"      - Product: {sample.get('product_name')}")
                print(f"      - Warehouse: {sample.get('warehouse_name')}")
                print(f"      - Expected Qty: {sample.get('expected_qty')}")
                print(f"      - Status: {sample.get('status')}")
                return True
            else:
                print(f"   ❌ Some tasks missing warehouse_name")
                return False
        
        return False
    
    def test_fix1_manager_approval_fresh_po(self):
        """Test FIX #1: Manager can approve a fresh waiting PO"""
        admin_token = self.tokens.get('admin')
        manager_token = self.tokens.get('manager')
        if not admin_token or not manager_token:
            print("⚠️  Skipping - need both admin and manager tokens")
            return False
        
        print(f"\n{'='*70}")
        print("FIX VERIFICATION #1: Manager Approval on Fresh PO")
        print(f"{'='*70}")
        
        # Get suppliers and warehouses first
        success_sup, suppliers = self.run_test(
            "Get suppliers",
            "GET",
            "api/suppliers",
            200,
            token=admin_token
        )
        
        success_wh, warehouses = self.run_test(
            "Get warehouses",
            "GET",
            "api/warehouses",
            200,
            token=admin_token
        )
        
        success_prod, products = self.run_test(
            "Get products",
            "GET",
            "api/products",
            200,
            token=admin_token
        )
        
        if not (success_sup and success_wh and success_prod):
            print("   ❌ Failed to get required data")
            return False
        
        if not suppliers or not warehouses or not products:
            print("   ❌ No suppliers, warehouses, or products available")
            return False
        
        supplier_id = suppliers[0].get('id')
        warehouse_id = warehouses[0].get('id')
        product_id = products[0].get('id')
        
        # Create a high-value PO as admin (>100M to require manager approval)
        po_data = {
            "supplier_id": supplier_id,
            "warehouse_id": warehouse_id,
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 1000,
                    "unit": "meter",
                    "price": 150000  # 1000 x 150000 = 150M > 100M
                }
            ],
            "expected_delivery_date": "2025-09-01",
            "notes": "Test PO for manager approval",
            "created_by": "admin@kainnusantara.id"
        }
        
        success_create, new_po = self.run_test(
            "Create high-value PO (150M) as admin",
            "POST",
            "api/purchase-orders",
            200,
            data=po_data,
            token=admin_token,
            description="Should require manager approval (>100M)"
        )
        
        if not success_create:
            print("   ❌ Failed to create PO")
            return False
        
        po_id = new_po.get('id')
        po_status = new_po.get('status')
        approval_required = new_po.get('approval_required')
        required_role = new_po.get('required_approval_role')
        
        print(f"   ✓ Created PO: {new_po.get('po_number')} (id: {po_id})")
        print(f"   ✓ Status: {po_status}")
        print(f"   ✓ Approval Required: {approval_required}")
        print(f"   ✓ Required Role: {required_role}")
        
        if po_status != 'waiting_approval':
            print(f"   ❌ PO should be waiting_approval, got: {po_status}")
            return False
        
        # Manager approves the PO
        success_approve, approved = self.run_test(
            "Manager approves PO",
            "POST",
            f"api/purchase-orders/{po_id}/approve",
            200,
            token=manager_token,
            description="Manager should be able to approve"
        )
        
        if success_approve:
            print(f"   ✓ New Status: {approved.get('status')}")
            print(f"   ✓ Approval Status: {approved.get('approval_status')}")
            print(f"   ✓ Approved By: {approved.get('approved_by')}")
            
            if approved.get('status') == 'pending' and approved.get('approval_status') == 'approved':
                print(f"   ✅ Manager approval successful")
                return True
            else:
                print(f"   ❌ Approval status incorrect")
                return False
        
        return False
    
    # ── FIX VERIFICATION #2: Manager Can Create POs ─────────────────────────────
    
    def test_fix2_permission_checks(self):
        """Test FIX #2: PO creation permissions for all roles"""
        print(f"\n{'='*70}")
        print("FIX VERIFICATION #2: PO Creation Permissions")
        print(f"{'='*70}")
        
        # Get required data
        admin_token = self.tokens.get('admin')
        success_sup, suppliers = self.run_test(
            "Get suppliers",
            "GET",
            "api/suppliers",
            200,
            token=admin_token
        )
        
        success_wh, warehouses = self.run_test(
            "Get warehouses",
            "GET",
            "api/warehouses",
            200,
            token=admin_token
        )
        
        success_prod, products = self.run_test(
            "Get products",
            "GET",
            "api/products",
            200,
            token=admin_token
        )
        
        if not (success_sup and success_wh and success_prod) or not suppliers or not warehouses or not products:
            print("   ❌ Failed to get required data")
            return False
        
        supplier_id = suppliers[0].get('id')
        warehouse_id = warehouses[0].get('id')
        product_id = products[0].get('id')
        
        po_data = {
            "supplier_id": supplier_id,
            "warehouse_id": warehouse_id,
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 10,
                    "unit": "meter",
                    "price": 50000
                }
            ],
            "expected_delivery_date": "2025-09-01",
            "notes": "Test PO for permission check",
            "created_by": "test@kainnusantara.id"
        }
        
        all_passed = True
        
        # Test 1: Manager can create PO (200)
        manager_token = self.tokens.get('manager')
        if manager_token:
            success1, _ = self.run_test(
                "Manager creates PO (should be 200)",
                "POST",
                "api/purchase-orders",
                200,
                data=po_data,
                token=manager_token,
                description="Manager has 'create' permission"
            )
            if success1:
                print(f"   ✅ Manager can create PO")
            else:
                print(f"   ❌ Manager cannot create PO")
                all_passed = False
        
        # Test 2: Admin can create PO (200)
        admin_token = self.tokens.get('admin')
        if admin_token:
            success2, _ = self.run_test(
                "Admin creates PO (should be 200)",
                "POST",
                "api/purchase-orders",
                200,
                data=po_data,
                token=admin_token,
                description="Admin has 'create' permission"
            )
            if success2:
                print(f"   ✅ Admin can create PO")
            else:
                print(f"   ❌ Admin cannot create PO")
                all_passed = False
        
        # Test 3: Warehouse can GET but not POST (403)
        warehouse_token = self.tokens.get('warehouse')
        if warehouse_token:
            success3a, _ = self.run_test(
                "Warehouse GET POs (should be 200)",
                "GET",
                "api/purchase-orders",
                200,
                token=warehouse_token,
                description="Warehouse has 'view' permission"
            )
            if success3a:
                print(f"   ✅ Warehouse can view POs")
            else:
                print(f"   ❌ Warehouse cannot view POs")
                all_passed = False
            
            success3b, _ = self.run_test(
                "Warehouse POST PO (should be 403)",
                "POST",
                "api/purchase-orders",
                403,
                data=po_data,
                token=warehouse_token,
                description="Warehouse lacks 'create' permission"
            )
            if success3b:
                print(f"   ✅ Warehouse correctly blocked from creating PO")
            else:
                print(f"   ❌ Warehouse permission check failed")
                all_passed = False
        
        # Test 4: Sales can GET but not POST (403)
        sales_token = self.tokens.get('sales')
        if sales_token:
            success4a, _ = self.run_test(
                "Sales GET POs (should be 200)",
                "GET",
                "api/purchase-orders",
                200,
                token=sales_token,
                description="Sales has 'view' permission"
            )
            if success4a:
                print(f"   ✅ Sales can view POs")
            else:
                print(f"   ❌ Sales cannot view POs")
                all_passed = False
            
            success4b, _ = self.run_test(
                "Sales POST PO (should be 403)",
                "POST",
                "api/purchase-orders",
                403,
                data=po_data,
                token=sales_token,
                description="Sales lacks 'create' permission"
            )
            if success4b:
                print(f"   ✅ Sales correctly blocked from creating PO")
            else:
                print(f"   ❌ Sales permission check failed")
                all_passed = False
        
        return all_passed
    
    # ── PO REJECT FLOW ──────────────────────────────────────────────────────────
    
    def test_po_reject_flow(self):
        """Test PO reject flow"""
        admin_token = self.tokens.get('admin')
        manager_token = self.tokens.get('manager')
        if not admin_token or not manager_token:
            print("⚠️  Skipping - need both admin and manager tokens")
            return False
        
        print(f"\n{'='*70}")
        print("PO REJECT FLOW TEST")
        print(f"{'='*70}")
        
        # Get required data
        success_sup, suppliers = self.run_test(
            "Get suppliers",
            "GET",
            "api/suppliers",
            200,
            token=admin_token
        )
        
        success_wh, warehouses = self.run_test(
            "Get warehouses",
            "GET",
            "api/warehouses",
            200,
            token=admin_token
        )
        
        success_prod, products = self.run_test(
            "Get products",
            "GET",
            "api/products",
            200,
            token=admin_token
        )
        
        if not (success_sup and success_wh and success_prod) or not suppliers or not warehouses or not products:
            print("   ❌ Failed to get required data")
            return False
        
        # Create high-value PO (>100M)
        po_data = {
            "supplier_id": suppliers[0].get('id'),
            "warehouse_id": warehouses[0].get('id'),
            "items": [
                {
                    "product_id": products[0].get('id'),
                    "quantity": 1000,
                    "unit": "meter",
                    "price": 150000  # 150M
                }
            ],
            "expected_delivery_date": "2025-09-01",
            "notes": "Test PO for rejection",
            "created_by": "admin@kainnusantara.id"
        }
        
        success_create, new_po = self.run_test(
            "Create high-value PO (150M)",
            "POST",
            "api/purchase-orders",
            200,
            data=po_data,
            token=admin_token
        )
        
        if not success_create:
            print("   ❌ Failed to create PO")
            return False
        
        po_id = new_po.get('id')
        print(f"   ✓ Created PO: {new_po.get('po_number')} (id: {po_id})")
        print(f"   ✓ Status: {new_po.get('status')}")
        print(f"   ✓ Total: Rp {new_po.get('total_amount'):,.0f}")
        
        # Manager rejects the PO
        success_reject, rejected = self.run_test(
            "Manager rejects PO",
            "POST",
            f"api/purchase-orders/{po_id}/reject",
            200,
            data={"reason": "Harga terlalu tinggi, perlu negosiasi ulang"},
            token=manager_token,
            description="Should return 200 with status='rejected'"
        )
        
        if success_reject:
            print(f"   ✓ Status: {rejected.get('status')}")
            print(f"   ✓ Approval Status: {rejected.get('approval_status')}")
            print(f"   ✓ Rejected By: {rejected.get('rejected_by')}")
            print(f"   ✓ Rejection Reason: {rejected.get('rejection_reason')}")
            
            if rejected.get('status') == 'rejected' and rejected.get('rejection_reason'):
                print(f"   ✅ PO rejection successful with reason saved")
            else:
                print(f"   ❌ Rejection status or reason incorrect")
                return False
        else:
            return False
        
        # Try to reject again (should return 409)
        success_409, _ = self.run_test(
            "Try to reject non-waiting PO (should be 409)",
            "POST",
            f"api/purchase-orders/{po_id}/reject",
            409,
            data={"reason": "test"},
            token=manager_token,
            description="Should return 409 for non-waiting PO"
        )
        
        if success_409:
            print(f"   ✅ Correctly returns 409 for non-waiting PO")
            return True
        else:
            print(f"   ❌ Should return 409 for non-waiting PO")
            return False
    
    # ── SUPPLIER CRUD REGRESSION ────────────────────────────────────────────────
    
    def test_supplier_crud(self):
        """Test Supplier CRUD operations"""
        admin_token = self.tokens.get('admin')
        manager_token = self.tokens.get('manager')
        if not admin_token or not manager_token:
            print("⚠️  Skipping - need admin and manager tokens")
            return False
        
        print(f"\n{'='*70}")
        print("SUPPLIER CRUD REGRESSION TEST")
        print(f"{'='*70}")
        
        all_passed = True
        
        # Test 1: GET suppliers
        success1, suppliers = self.run_test(
            "GET /api/suppliers",
            "GET",
            "api/suppliers",
            200,
            token=admin_token,
            description="List all suppliers"
        )
        if success1:
            print(f"   ✅ GET suppliers successful ({len(suppliers)} found)")
        else:
            print(f"   ❌ GET suppliers failed")
            all_passed = False
        
        # Test 2: POST create supplier (should return SUP-NNNNN code)
        unique_name = f"Test Supplier {datetime.now().strftime('%H%M%S')}"
        supplier_data = {
            "name": unique_name,
            "npwp": "12.345.678.9-012.345",
            "pic_name": "John Doe",
            "phone": "081234567890",
            "email": "test@supplier.com",
            "address": "Jl. Test No. 123",
            "city": "Jakarta",
            "goods_type": "Kain",
            "payment_term_code": "NET30",
            "notes": "Test supplier",
            "created_by": "admin@kainnusantara.id"
        }
        
        success2, new_supplier = self.run_test(
            "POST /api/suppliers",
            "POST",
            "api/suppliers",
            200,
            data=supplier_data,
            token=admin_token,
            description="Create new supplier (should return SUP-NNNNN)"
        )
        
        supplier_id = None
        if success2:
            supplier_id = new_supplier.get('id')
            supplier_code = new_supplier.get('code')
            print(f"   ✓ Created supplier: {supplier_code} (id: {supplier_id})")
            
            if supplier_code and supplier_code.startswith('SUP-'):
                print(f"   ✅ Supplier code format correct (SUP-NNNNN)")
            else:
                print(f"   ❌ Supplier code format incorrect: {supplier_code}")
                all_passed = False
        else:
            print(f"   ❌ POST supplier failed")
            all_passed = False
        
        # Test 3: PATCH supplier (uses {data:{...}} format)
        if supplier_id:
            success3, updated = self.run_test(
                "PATCH /api/suppliers/{id}",
                "PATCH",
                f"api/suppliers/{supplier_id}",
                200,
                data={"data": {"city": "Bandung", "notes": "Updated notes"}},
                token=manager_token,
                description="Update supplier (uses {data:{...}} format)"
            )
            
            if success3:
                print(f"   ✓ Updated city: {updated.get('city')}")
                print(f"   ✓ Updated notes: {updated.get('notes')}")
                
                if updated.get('city') == 'Bandung':
                    print(f"   ✅ PATCH supplier successful")
                else:
                    print(f"   ❌ PATCH update not applied")
                    all_passed = False
            else:
                print(f"   ❌ PATCH supplier failed")
                all_passed = False
        
        # Test 4: DELETE supplier (soft delete → status=inactive)
        if supplier_id:
            success4, deleted = self.run_test(
                "DELETE /api/suppliers/{id}",
                "DELETE",
                f"api/suppliers/{supplier_id}",
                200,
                token=admin_token,
                description="Soft delete supplier (status=inactive)"
            )
            
            if success4:
                status = deleted.get('status')
                print(f"   ✓ Status after delete: {status}")
                
                if status == 'inactive':
                    print(f"   ✅ Soft delete successful (status=inactive)")
                else:
                    print(f"   ❌ Soft delete failed: status should be 'inactive'")
                    all_passed = False
            else:
                print(f"   ❌ DELETE supplier failed")
                all_passed = False
        
        return all_passed
    
    # ── CASH REGRESSION ─────────────────────────────────────────────────────────
    
    def test_cash_regression(self):
        """Test Cash management operations"""
        admin_token = self.tokens.get('admin')
        if not admin_token:
            print("⚠️  Skipping - need admin token")
            return False
        
        print(f"\n{'='*70}")
        print("CASH REGRESSION TEST")
        print(f"{'='*70}")
        
        all_passed = True
        
        # Test 1: GET cash transactions
        success1, txns = self.run_test(
            "GET /api/cash-transactions",
            "GET",
            "api/cash-transactions",
            200,
            token=admin_token,
            description="List cash transactions"
        )
        if success1:
            print(f"   ✅ GET cash transactions successful ({len(txns)} found)")
        else:
            print(f"   ❌ GET cash transactions failed")
            all_passed = False
        
        # Test 2: GET cash summary
        success2, summary = self.run_test(
            "GET /api/cash-transactions/summary",
            "GET",
            "api/cash-transactions/summary",
            200,
            token=admin_token,
            description="Get cash summary (kas_kecil/kas_besar with balance)"
        )
        if success2:
            kas_kecil = summary.get('kas_kecil', {})
            kas_besar = summary.get('kas_besar', {})
            kas_kecil_per_entity = summary.get('kas_kecil_per_entity', {})
            
            print(f"   ✓ Kas Kecil: balance={kas_kecil.get('balance')}, count={kas_kecil.get('count')}")
            print(f"   ✓ Kas Besar: balance={kas_besar.get('balance')}, count={kas_besar.get('count')}")
            print(f"   ✓ Kas Kecil per Entity: {len(kas_kecil_per_entity)} entities")
            print(f"   ✅ GET cash summary successful")
        else:
            print(f"   ❌ GET cash summary failed")
            all_passed = False
        
        # Test 3: POST create cash transaction (should return CASH-NNNNN)
        cash_data = {
            "cash_type": "kas_kecil",
            "direction": "in",
            "amount": 5000000,
            "category": "Penerimaan",
            "description": "Test cash in",
            "entity_id": "ent_ksc",
            "ref_type": "manual",
            "ref_id": "",
            "created_by": "admin@kainnusantara.id"
        }
        
        success3, new_cash = self.run_test(
            "POST /api/cash-transactions (kas_kecil)",
            "POST",
            "api/cash-transactions",
            200,
            data=cash_data,
            token=admin_token,
            description="Create cash transaction (should return CASH-NNNNN)"
        )
        
        cash_id = None
        if success3:
            cash_id = new_cash.get('id')
            cash_number = new_cash.get('number')
            print(f"   ✓ Created cash txn: {cash_number} (id: {cash_id})")
            
            if cash_number and cash_number.startswith('CASH-'):
                print(f"   ✅ Cash number format correct (CASH-NNNNN)")
            else:
                print(f"   ❌ Cash number format incorrect: {cash_number}")
                all_passed = False
        else:
            print(f"   ❌ POST cash transaction failed")
            all_passed = False
        
        # Test 4: kas_besar forces entity_id='all'
        cash_besar_data = {
            "cash_type": "kas_besar",
            "direction": "in",
            "amount": 10000000,
            "category": "Penerimaan Besar",
            "description": "Test kas besar",
            "entity_id": "ent_ksc",  # Should be overridden to 'all'
            "ref_type": "manual",
            "ref_id": "",
            "created_by": "admin@kainnusantara.id"
        }
        
        success4, new_besar = self.run_test(
            "POST /api/cash-transactions (kas_besar)",
            "POST",
            "api/cash-transactions",
            200,
            data=cash_besar_data,
            token=admin_token,
            description="kas_besar should force entity_id='all'"
        )
        
        if success4:
            entity_id = new_besar.get('entity_id')
            print(f"   ✓ Entity ID: {entity_id}")
            
            if entity_id == 'all':
                print(f"   ✅ kas_besar correctly forces entity_id='all'")
            else:
                print(f"   ❌ kas_besar should force entity_id='all', got: {entity_id}")
                all_passed = False
        else:
            print(f"   ❌ POST kas_besar failed")
            all_passed = False
        
        # Test 5: amount<=0 returns 400
        invalid_cash = {
            "cash_type": "kas_kecil",
            "direction": "in",
            "amount": 0,
            "category": "Test",
            "description": "Invalid amount",
            "created_by": "admin@kainnusantara.id"
        }
        
        success5, _ = self.run_test(
            "POST cash with amount=0 (should be 400)",
            "POST",
            "api/cash-transactions",
            400,
            data=invalid_cash,
            token=admin_token,
            description="amount<=0 should return 400"
        )
        
        if success5:
            print(f"   ✅ Correctly returns 400 for amount<=0")
        else:
            print(f"   ❌ Should return 400 for amount<=0")
            all_passed = False
        
        # Test 6: POST void
        if cash_id:
            success6, voided = self.run_test(
                "POST /api/cash-transactions/{id}/void",
                "POST",
                f"api/cash-transactions/{cash_id}/void",
                200,
                token=admin_token,
                description="Void cash transaction"
            )
            
            if success6:
                status = voided.get('status')
                print(f"   ✓ Status after void: {status}")
                
                if status == 'void':
                    print(f"   ✅ Void successful")
                else:
                    print(f"   ❌ Void failed: status should be 'void'")
                    all_passed = False
            else:
                print(f"   ❌ POST void failed")
                all_passed = False
        
        return all_passed
    
    # ── RECEIVING TOLERANCE ±2% ─────────────────────────────────────────────────
    
    def test_receiving_tolerance(self):
        """Test receiving tolerance ±2%"""
        admin_token = self.tokens.get('admin')
        warehouse_token = self.tokens.get('warehouse')
        if not admin_token or not warehouse_token:
            print("⚠️  Skipping - need admin and warehouse tokens")
            return False
        
        print(f"\n{'='*70}")
        print("RECEIVING TOLERANCE ±2% TEST")
        print(f"{'='*70}")
        
        # Get inbound tasks
        success1, tasks = self.run_test(
            "GET /api/inbound/tasks",
            "GET",
            "api/inbound/tasks",
            200,
            token=warehouse_token,
            description="Get inbound receiving tasks"
        )
        
        if not success1 or not tasks:
            print("   ⚠️  No inbound tasks available for testing")
            print("   ℹ️  This test requires an existing inbound task from a pending PO")
            return True  # Not a failure, just no data to test
        
        # Find a task in waiting_goods or receiving status
        testable_task = None
        for task in tasks:
            if task.get('status') in ['waiting_goods', 'receiving']:
                testable_task = task
                break
        
        if not testable_task:
            print("   ⚠️  No testable inbound tasks (need waiting_goods or receiving status)")
            print("   ℹ️  This test requires a task that hasn't been completed yet")
            return True  # Not a failure
        
        task_id = testable_task.get('id')
        product_id = testable_task.get('product_id')
        expected_qty = testable_task.get('expected_qty', 100)
        
        print(f"   ✓ Testing with task: {task_id}")
        print(f"   ✓ Product: {testable_task.get('product_name')}")
        print(f"   ✓ Expected Qty: {expected_qty}")
        print(f"   ✓ Current Status: {testable_task.get('status')}")
        
        # Test 1: Receive within tolerance (+2%)
        within_tolerance_qty = expected_qty * 1.02  # Exactly at +2%
        
        receive_data_ok = {
            "product_id": product_id,
            "actual_qty": within_tolerance_qty,
            "batch": "BATCH-TEST-001",
            "lot": "LOT-TEST-001",
            "roll_id": "",
            "bin_id": "BIN-A1"
        }
        
        success2, received_ok = self.run_test(
            f"Receive within +2% tolerance ({within_tolerance_qty})",
            "POST",
            f"api/inbound/tasks/{task_id}/scan-receive",
            200,
            data=receive_data_ok,
            token=warehouse_token,
            description=f"Should succeed (within +2% of {expected_qty})"
        )
        
        if success2:
            print(f"   ✓ Received Qty: {received_ok.get('received_qty')}")
            print(f"   ✓ Variance: {received_ok.get('receive_variance_percent')}%")
            print(f"   ✓ Within Tolerance: {received_ok.get('receive_within_tolerance')}")
            print(f"   ✅ Within-tolerance receive successful")
        else:
            print(f"   ❌ Within-tolerance receive failed (should succeed)")
            return False
        
        # Test 2: Try to receive exceeding tolerance (>+2%)
        # Create a new task or use another one for this test
        # For simplicity, we'll test with the same task if it's still in receiving status
        
        # Get fresh task state
        success3, fresh_tasks = self.run_test(
            "Get fresh task state",
            "GET",
            "api/inbound/tasks",
            200,
            token=warehouse_token
        )
        
        if success3:
            current_task = next((t for t in fresh_tasks if t.get('id') == task_id), None)
            if current_task and current_task.get('status') in ['waiting_goods', 'receiving']:
                current_received = current_task.get('received_qty', 0)
                remaining = expected_qty - current_received
                
                # Try to receive more than +2% of remaining
                over_tolerance_qty = remaining * 1.05  # +5% over remaining
                
                receive_data_over = {
                    "product_id": product_id,
                    "actual_qty": over_tolerance_qty,
                    "batch": "BATCH-TEST-002",
                    "lot": "LOT-TEST-002",
                    "roll_id": "",
                    "bin_id": "BIN-A1"
                }
                
                success4, _ = self.run_test(
                    f"Receive exceeding +2% tolerance (should be 400)",
                    "POST",
                    f"api/inbound/tasks/{task_id}/scan-receive",
                    400,
                    data=receive_data_over,
                    token=warehouse_token,
                    description="Should return 400 with 'toleransi' message"
                )
                
                if success4:
                    print(f"   ✅ Over-tolerance correctly rejected with 400")
                    return True
                else:
                    print(f"   ❌ Over-tolerance should return 400")
                    return False
            else:
                print(f"   ℹ️  Task already completed or changed status, cannot test over-tolerance")
                return True  # Not a failure
        
        return True
    
    def print_summary(self):
        """Print test summary"""
        print(f"\n{'='*70}")
        print("📊 TEST SUMMARY")
        print(f"{'='*70}")
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {len(self.failed_tests)}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print(f"\n❌ FAILED TESTS:")
            for ft in self.failed_tests:
                print(f"   - {ft['test']}")
                if 'expected' in ft:
                    print(f"     Expected: {ft['expected']}, Got: {ft['actual']}")
                if 'error' in ft:
                    print(f"     Error: {ft['error']}")
                if 'response' in ft:
                    print(f"     Response: {ft['response']}")


def main():
    print("="*70)
    print("🧪 KAIN NUSANTARA - FASE 3 PURCHASING MODULE RE-TEST")
    print("="*70)
    
    tester = Fase3PurchasingTester()
    
    # Login all roles
    print("\n📍 AUTHENTICATION")
    print("-"*70)
    
    credentials = [
        ("admin@kainnusantara.id", "demo12345", "admin"),
        ("manager@kainnusantara.id", "demo12345", "manager"),
        ("warehouse@kainnusantara.id", "demo12345", "warehouse"),
        ("sales@kainnusantara.id", "demo12345", "sales")
    ]
    
    for email, password, role in credentials:
        if not tester.test_login(email, password, role):
            print(f"❌ {role} login failed")
            return 1
    
    # Run all tests
    print("\n" + "="*70)
    print("🎯 RUNNING FASE 3 PURCHASING TESTS")
    print("="*70)
    
    # FIX #1: PO Approval
    tester.test_fix1_po_approval_seeded_po()
    tester.test_fix1_manager_approval_fresh_po()
    
    # FIX #2: Permissions
    tester.test_fix2_permission_checks()
    
    # PO Reject
    tester.test_po_reject_flow()
    
    # Supplier CRUD
    tester.test_supplier_crud()
    
    # Cash
    tester.test_cash_regression()
    
    # Receiving Tolerance
    tester.test_receiving_tolerance()
    
    # Print summary
    tester.print_summary()
    
    return 0 if tester.tests_passed == tester.tests_run else 1


if __name__ == "__main__":
    sys.exit(main())
