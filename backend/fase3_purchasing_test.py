"""Backend API Testing for Kain Nusantara - Fase 3 Purchasing/Procurement"""
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
        self.supplier_ids = []
        self.po_ids = []
        self.cash_txn_ids = []

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
            except Exception:
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

    # ── FASE 3: SUPPLIER MASTER CRUD ──────────────────────────────────────────────
    
    def test_suppliers_list(self, role):
        """Test GET /api/suppliers - list suppliers"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping suppliers list test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: GET /api/suppliers for {role}")
        success, response = self.run_test(
            "Fase3: List suppliers",
            "GET",
            "api/suppliers",
            200,
            token=token,
            description="Should return list of suppliers (SUP-00001..SUP-00006)"
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} suppliers")
            if len(response) > 0:
                sample = response[0]
                print(f"   ✓ Sample: {sample.get('code')} - {sample.get('name')}")
                self.supplier_ids = [s.get('id') for s in response if s.get('id')]
            return True
        return False
    
    def test_suppliers_create(self, role):
        """Test POST /api/suppliers - create supplier"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping suppliers create test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: POST /api/suppliers for {role}")
        
        unique_name = f"Test Supplier {datetime.now().strftime('%H%M%S')}"
        success, response = self.run_test(
            "Fase3: Create supplier",
            "POST",
            "api/suppliers",
            200,
            data={
                "name": unique_name,
                "npwp": "01.234.567.8-901.000",
                "pic_name": "Test PIC",
                "phone": "081234567890",
                "email": "test@supplier.co.id",
                "address": "Jl. Test No. 123",
                "city": "Jakarta",
                "goods_type": "Benang",
                "payment_term_code": "NET30",
                "entity_id": "",
                "notes": "Test supplier",
                "created_by": "Test Admin"
            },
            token=token,
            description="Should create supplier with code SUP-NNNNN"
        )
        
        if success:
            code = response.get('code')
            supplier_id = response.get('id')
            print(f"   ✅ Supplier created: {code} - {response.get('name')}")
            if supplier_id:
                self.supplier_ids.append(supplier_id)
            return True
        return False
    
    def test_suppliers_get_detail(self, role):
        """Test GET /api/suppliers/{id} - get supplier detail with PO list"""
        token = self.tokens.get(role)
        if not token or not self.supplier_ids:
            print(f"⚠️  Skipping supplier detail test for {role} - no token or supplier")
            return False
        
        print(f"\n🔍 Testing Fase 3: GET /api/suppliers/{{id}} for {role}")
        
        supplier_id = self.supplier_ids[0]
        success, response = self.run_test(
            "Fase3: Get supplier detail",
            "GET",
            f"api/suppliers/{supplier_id}",
            200,
            token=token,
            description=f"Should return supplier with purchase_orders array + po_count"
        )
        
        if success:
            print(f"   ✓ Supplier: {response.get('name')}")
            print(f"   ✓ PO count: {response.get('po_count', 0)}")
            print(f"   ✓ PO total value: {response.get('po_total_value', 0)}")
            if 'purchase_orders' in response:
                print(f"   ✅ purchase_orders array present")
                return True
        return False
    
    def test_suppliers_update(self, role):
        """Test PATCH /api/suppliers/{id} - update supplier"""
        token = self.tokens.get(role)
        if not token or not self.supplier_ids:
            print(f"⚠️  Skipping supplier update test for {role} - no token or supplier")
            return False
        
        print(f"\n🔍 Testing Fase 3: PATCH /api/suppliers/{{id}} for {role}")
        
        supplier_id = self.supplier_ids[-1]  # Use last created
        success, response = self.run_test(
            "Fase3: Update supplier",
            "PATCH",
            f"api/suppliers/{supplier_id}",
            200,
            data={
                "data": {
                    "phone": "081999888777",
                    "notes": "Updated via test"
                }
            },
            token=token,
            description="Should update supplier fields"
        )
        
        if success:
            print(f"   ✅ Supplier updated: {response.get('name')}")
            print(f"   ✓ New phone: {response.get('phone')}")
            return True
        return False
    
    def test_suppliers_delete(self, role):
        """Test DELETE /api/suppliers/{id} - soft delete (status inactive)"""
        token = self.tokens.get(role)
        if not token or not self.supplier_ids:
            print(f"⚠️  Skipping supplier delete test for {role} - no token or supplier")
            return False
        
        print(f"\n🔍 Testing Fase 3: DELETE /api/suppliers/{{id}} for {role}")
        
        supplier_id = self.supplier_ids[-1]  # Use last created
        success, response = self.run_test(
            "Fase3: Soft delete supplier",
            "DELETE",
            f"api/suppliers/{supplier_id}",
            200,
            token=token,
            description="Should set status=inactive"
        )
        
        if success:
            status = response.get('status')
            print(f"   ✅ Supplier deactivated: status={status}")
            if status == 'inactive':
                print(f"   ✅ Soft delete verified")
                return True
        return False
    
    def test_suppliers_permission_sales_403(self, role):
        """Test that sales role gets 403 on supplier create"""
        token = self.tokens.get(role)
        if not token or role != 'sales':
            print(f"⚠️  Skipping permission test - need sales role")
            return False
        
        print(f"\n🔍 Testing Fase 3: Supplier permission check for {role}")
        
        success, response = self.run_test(
            "Fase3: Sales create supplier (403)",
            "POST",
            "api/suppliers",
            403,
            data={
                "name": "Should Fail",
                "npwp": "",
                "pic_name": "",
                "phone": "",
                "email": "",
                "address": "",
                "city": "",
                "goods_type": "",
                "payment_term_code": "",
                "entity_id": "",
                "notes": "",
                "created_by": "Sales"
            },
            token=token,
            description="Sales role should get 403 on create"
        )
        
        if success:
            print(f"   ✅ Permission check passed: sales got 403")
            return True
        return False

    # ── FASE 3: PURCHASE ORDER WITH SUPPLIER FK ───────────────────────────────────
    
    def test_po_with_supplier_fk(self, role):
        """Test POST /api/purchase-orders with supplier_id (FK to suppliers)"""
        token = self.tokens.get(role)
        if not token or not self.supplier_ids:
            print(f"⚠️  Skipping PO with supplier FK test for {role} - no token or supplier")
            return False
        
        print(f"\n🔍 Testing Fase 3: POST /api/purchase-orders with supplier_id for {role}")
        
        # Get warehouses and products first
        _, warehouses = self.run_test("Get warehouses", "GET", "api/warehouses", 200, token=token)
        _, products = self.run_test("Get products", "GET", "api/products", 200, token=token)
        
        if not warehouses or not products:
            print(f"   ⚠️  Missing warehouses or products")
            return False
        
        warehouse_id = warehouses[0].get('id') if isinstance(warehouses, list) else None
        product_id = products[0].get('id') if isinstance(products, list) else None
        
        if not warehouse_id or not product_id:
            print(f"   ⚠️  Could not get warehouse or product ID")
            return False
        
        supplier_id = self.supplier_ids[0]
        success, response = self.run_test(
            "Fase3: Create PO with supplier_id",
            "POST",
            "api/purchase-orders",
            200,
            data={
                "supplier_id": supplier_id,
                "supplier_name": "",  # Should be auto-filled
                "supplier_contact": "",
                "warehouse_id": warehouse_id,
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 50,
                        "unit": "meter",
                        "price": 150000
                    }
                ],
                "expected_delivery_date": "2025-09-01",
                "notes": "Test PO with supplier FK",
                "created_by": "Test Admin",
                "entity_id": ""
            },
            token=token,
            description="Should auto-fill supplier_name and supplier_npwp from supplier master"
        )
        
        if success:
            po_number = response.get('po_number')
            po_id = response.get('id')
            supplier_name = response.get('supplier_name')
            supplier_npwp = response.get('supplier_npwp')
            
            print(f"   ✅ PO created: {po_number}")
            print(f"   ✓ Supplier ID: {response.get('supplier_id')}")
            print(f"   ✓ Supplier name (auto-filled): {supplier_name}")
            print(f"   ✓ Supplier NPWP (auto-filled): {supplier_npwp}")
            
            if po_id:
                self.po_ids.append(po_id)
            
            if supplier_name and response.get('supplier_id') == supplier_id:
                print(f"   ✅ Supplier FK and snapshot verified")
                return True
        return False
    
    def test_po_manual_supplier(self, role):
        """Test POST /api/purchase-orders with manual supplier_name (no supplier_id)"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping PO manual supplier test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: POST /api/purchase-orders with manual supplier_name for {role}")
        
        # Get warehouses and products
        _, warehouses = self.run_test("Get warehouses", "GET", "api/warehouses", 200, token=token)
        _, products = self.run_test("Get products", "GET", "api/products", 200, token=token)
        
        warehouse_id = warehouses[0].get('id') if isinstance(warehouses, list) else None
        product_id = products[0].get('id') if isinstance(products, list) else None
        
        if not warehouse_id or not product_id:
            print(f"   ⚠️  Could not get warehouse or product ID")
            return False
        
        success, response = self.run_test(
            "Fase3: Create PO with manual supplier",
            "POST",
            "api/purchase-orders",
            200,
            data={
                "supplier_id": "",  # No FK
                "supplier_name": "Manual Supplier Test",
                "supplier_contact": "081234567890",
                "warehouse_id": warehouse_id,
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 30,
                        "unit": "meter",
                        "price": 120000
                    }
                ],
                "expected_delivery_date": "2025-09-01",
                "notes": "Test PO manual supplier",
                "created_by": "Test Admin",
                "entity_id": ""
            },
            token=token,
            description="Should work with manual supplier_name (backward compat)"
        )
        
        if success:
            po_number = response.get('po_number')
            print(f"   ✅ PO created with manual supplier: {po_number}")
            print(f"   ✓ Supplier name: {response.get('supplier_name')}")
            return True
        return False
    
    def test_po_no_supplier_400(self, role):
        """Test POST /api/purchase-orders without supplier_id or supplier_name returns 400"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping PO no supplier test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: POST /api/purchase-orders without supplier (400) for {role}")
        
        _, warehouses = self.run_test("Get warehouses", "GET", "api/warehouses", 200, token=token)
        _, products = self.run_test("Get products", "GET", "api/products", 200, token=token)
        
        warehouse_id = warehouses[0].get('id') if isinstance(warehouses, list) else None
        product_id = products[0].get('id') if isinstance(products, list) else None
        
        success, response = self.run_test(
            "Fase3: Create PO without supplier (400)",
            "POST",
            "api/purchase-orders",
            400,
            data={
                "supplier_id": "",
                "supplier_name": "",  # Both empty
                "supplier_contact": "",
                "warehouse_id": warehouse_id,
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 10,
                        "unit": "meter",
                        "price": 100000
                    }
                ],
                "expected_delivery_date": "2025-09-01",
                "notes": "Should fail",
                "created_by": "Test Admin",
                "entity_id": ""
            },
            token=token,
            description="Should return 400 when neither supplier_id nor supplier_name provided"
        )
        
        if success:
            print(f"   ✅ Validation passed: got 400 for missing supplier")
            return True
        return False

    # ── FASE 3: PURCHASE APPROVAL WORKFLOW ────────────────────────────────────────
    
    def test_po_high_value_approval(self, role):
        """Test high-value PO (>100M) requires manager approval"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping high-value PO test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: High-value PO approval workflow for {role}")
        
        # Get warehouses and products
        _, warehouses = self.run_test("Get warehouses", "GET", "api/warehouses", 200, token=token)
        _, products = self.run_test("Get products", "GET", "api/products", 200, token=token)
        
        warehouse_id = warehouses[0].get('id') if isinstance(warehouses, list) else None
        product_id = products[0].get('id') if isinstance(products, list) else None
        
        # Create high-value PO: 1000 x 150000 = 150M (>100M)
        success, response = self.run_test(
            "Fase3: Create high-value PO (>100M)",
            "POST",
            "api/purchase-orders",
            200,
            data={
                "supplier_id": self.supplier_ids[0] if self.supplier_ids else "",
                "supplier_name": "Test Supplier",
                "supplier_contact": "",
                "warehouse_id": warehouse_id,
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 1000,
                        "unit": "meter",
                        "price": 150000
                    }
                ],
                "expected_delivery_date": "2025-09-01",
                "notes": "High-value PO test",
                "created_by": "Test Admin",
                "entity_id": ""
            },
            token=token,
            description="Should create PO with status=waiting_approval, required_approval_role=manager"
        )
        
        if success:
            po_id = response.get('id')
            po_number = response.get('po_number')
            status = response.get('status')
            required_role = response.get('required_approval_role')
            total_amount = response.get('total_amount')
            
            print(f"   ✅ High-value PO created: {po_number}")
            print(f"   ✓ Total amount: Rp {total_amount:,.0f}")
            print(f"   ✓ Status: {status}")
            print(f"   ✓ Required approval role: {required_role}")
            
            if status == 'waiting_approval' and required_role == 'manager':
                print(f"   ✅ Approval workflow triggered correctly")
                if po_id:
                    self.po_ids.append(po_id)
                return True
            else:
                print(f"   ❌ Expected status=waiting_approval, required_role=manager")
                return False
        return False
    
    def test_po_approve(self, role):
        """Test POST /api/purchase-orders/{id}/approve as manager"""
        token = self.tokens.get(role)
        if not token or role != 'manager':
            print(f"⚠️  Skipping PO approve test - need manager role")
            return False
        
        print(f"\n🔍 Testing Fase 3: POST /api/purchase-orders/{{id}}/approve for {role}")
        
        # Find a waiting_approval PO
        _, pos = self.run_test("Get POs", "GET", "api/purchase-orders", 200, token=token)
        waiting_po = None
        if isinstance(pos, list):
            waiting_po = next((p for p in pos if p.get('status') == 'waiting_approval'), None)
        
        if not waiting_po:
            print(f"   ⚠️  No waiting_approval PO found")
            return False
        
        po_id = waiting_po.get('id')
        po_number = waiting_po.get('po_number')
        
        success, response = self.run_test(
            "Fase3: Approve PO",
            "POST",
            f"api/purchase-orders/{po_id}/approve",
            200,
            token=token,
            description=f"Should approve {po_number} → status=pending, approval_status=approved"
        )
        
        if success:
            new_status = response.get('status')
            approval_status = response.get('approval_status')
            approved_by = response.get('approved_by')
            
            print(f"   ✅ PO approved: {po_number}")
            print(f"   ✓ New status: {new_status}")
            print(f"   ✓ Approval status: {approval_status}")
            print(f"   ✓ Approved by: {approved_by}")
            
            if new_status == 'pending' and approval_status == 'approved':
                print(f"   ✅ Approval workflow completed correctly")
                return True
        return False
    
    def test_po_reject(self, role):
        """Test POST /api/purchase-orders/{id}/reject with reason"""
        token = self.tokens.get(role)
        if not token or role != 'manager':
            print(f"⚠️  Skipping PO reject test - need manager role")
            return False
        
        print(f"\n🔍 Testing Fase 3: POST /api/purchase-orders/{{id}}/reject for {role}")
        
        # Create another high-value PO to reject
        _, warehouses = self.run_test("Get warehouses", "GET", "api/warehouses", 200, token=token)
        _, products = self.run_test("Get products", "GET", "api/products", 200, token=token)
        
        warehouse_id = warehouses[0].get('id') if isinstance(warehouses, list) else None
        product_id = products[0].get('id') if isinstance(products, list) else None
        
        _, po_response = self.run_test(
            "Create PO to reject",
            "POST",
            "api/purchase-orders",
            200,
            data={
                "supplier_id": "",
                "supplier_name": "Test Supplier for Reject",
                "supplier_contact": "",
                "warehouse_id": warehouse_id,
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 1000,
                        "unit": "meter",
                        "price": 150000
                    }
                ],
                "expected_delivery_date": "2025-09-01",
                "notes": "PO to reject",
                "created_by": "Test Admin",
                "entity_id": ""
            },
            token=token
        )
        
        po_id = po_response.get('id')
        po_number = po_response.get('po_number')
        
        if not po_id:
            print(f"   ⚠️  Could not create PO to reject")
            return False
        
        success, response = self.run_test(
            "Fase3: Reject PO",
            "POST",
            f"api/purchase-orders/{po_id}/reject",
            200,
            data={"reason": "Test rejection reason"},
            token=token,
            description=f"Should reject {po_number} → status=rejected, rejection_reason saved"
        )
        
        if success:
            new_status = response.get('status')
            approval_status = response.get('approval_status')
            rejected_by = response.get('rejected_by')
            rejection_reason = response.get('rejection_reason')
            
            print(f"   ✅ PO rejected: {po_number}")
            print(f"   ✓ New status: {new_status}")
            print(f"   ✓ Approval status: {approval_status}")
            print(f"   ✓ Rejected by: {rejected_by}")
            print(f"   ✓ Rejection reason: {rejection_reason}")
            
            if new_status == 'rejected' and rejection_reason:
                print(f"   ✅ Rejection workflow completed correctly")
                return True
        return False
    
    def test_po_low_value_no_approval(self, role):
        """Test low-value PO (<100M) is created directly without approval"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping low-value PO test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: Low-value PO (no approval) for {role}")
        
        _, warehouses = self.run_test("Get warehouses", "GET", "api/warehouses", 200, token=token)
        _, products = self.run_test("Get products", "GET", "api/products", 200, token=token)
        
        warehouse_id = warehouses[0].get('id') if isinstance(warehouses, list) else None
        product_id = products[0].get('id') if isinstance(products, list) else None
        
        # Create low-value PO: 50 x 150000 = 7.5M (<100M)
        success, response = self.run_test(
            "Fase3: Create low-value PO (<100M)",
            "POST",
            "api/purchase-orders",
            200,
            data={
                "supplier_id": "",
                "supplier_name": "Test Supplier Low Value",
                "supplier_contact": "",
                "warehouse_id": warehouse_id,
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 50,
                        "unit": "meter",
                        "price": 150000
                    }
                ],
                "expected_delivery_date": "2025-09-01",
                "notes": "Low-value PO test",
                "created_by": "Test Admin",
                "entity_id": ""
            },
            token=token,
            description="Should create PO with status=pending (no approval needed)"
        )
        
        if success:
            po_number = response.get('po_number')
            status = response.get('status')
            approval_required = response.get('approval_required')
            total_amount = response.get('total_amount')
            
            print(f"   ✅ Low-value PO created: {po_number}")
            print(f"   ✓ Total amount: Rp {total_amount:,.0f}")
            print(f"   ✓ Status: {status}")
            print(f"   ✓ Approval required: {approval_required}")
            
            if status == 'pending' and approval_required == False:
                print(f"   ✅ Low-value PO created without approval")
                return True
            else:
                print(f"   ❌ Expected status=pending, approval_required=False")
                return False
        return False

    # ── FASE 3: RECEIVING TOLERANCE ±2% ───────────────────────────────────────────
    
    def test_receiving_tolerance_within(self, role):
        """Test scan-receive with qty within +2% tolerance"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping receiving tolerance test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: Receiving tolerance within +2% for {role}")
        
        # Get inbound tasks
        success, tasks = self.run_test(
            "Get inbound tasks",
            "GET",
            "api/inbound/tasks",
            200,
            token=token,
            description="Find pending inbound task"
        )
        
        if not success or not isinstance(tasks, list) or len(tasks) == 0:
            print(f"   ⚠️  No inbound tasks found")
            return False
        
        # Find a task with expected_qty > 0
        task = next((t for t in tasks if t.get('expected_qty', 0) > 0 and t.get('status') not in ['completed', 'cancelled']), None)
        
        if not task:
            print(f"   ⚠️  No suitable inbound task found")
            return False
        
        task_id = task.get('id')
        expected_qty = task.get('expected_qty', 0)
        product_id = task.get('product_id')
        
        # Calculate qty within +2% (e.g., 800 → max 816)
        within_tolerance_qty = expected_qty * 1.01  # +1% (within +2%)
        
        print(f"   ✓ Task: {task.get('po_number')} - {task.get('product_name')}")
        print(f"   ✓ Expected qty: {expected_qty}")
        print(f"   ✓ Testing with qty: {within_tolerance_qty} (+1%, within tolerance)")
        
        success, response = self.run_test(
            "Fase3: Scan-receive within tolerance",
            "POST",
            f"api/inbound/tasks/{task_id}/scan-receive",
            200,
            data={
                "product_id": product_id,
                "actual_qty": within_tolerance_qty,
                "batch": "TEST-BATCH",
                "lot": "TEST-LOT",
                "roll_id": "",
                "bin_id": "A1-01"
            },
            token=token,
            description="Should succeed with qty within +2% tolerance"
        )
        
        if success:
            received_qty = response.get('received_qty')
            variance_pct = response.get('receive_variance_percent')
            within_tol = response.get('receive_within_tolerance')
            
            print(f"   ✅ Scan-receive succeeded")
            print(f"   ✓ Received qty: {received_qty}")
            print(f"   ✓ Variance: {variance_pct}%")
            print(f"   ✓ Within tolerance: {within_tol}")
            
            if within_tol:
                print(f"   ✅ Tolerance check passed")
                return True
        return False
    
    def test_receiving_tolerance_exceed(self, role):
        """Test scan-receive with qty exceeding +2% tolerance returns 400"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping receiving tolerance exceed test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: Receiving tolerance exceed +2% (400) for {role}")
        
        # Get inbound tasks
        _, tasks = self.run_test("Get inbound tasks", "GET", "api/inbound/tasks", 200, token=token)
        
        if not isinstance(tasks, list) or len(tasks) == 0:
            print(f"   ⚠️  No inbound tasks found")
            return False
        
        # Find a fresh task (received_qty = 0)
        task = next((t for t in tasks if t.get('expected_qty', 0) > 0 and t.get('received_qty', 0) == 0 and t.get('status') not in ['completed', 'cancelled']), None)
        
        if not task:
            print(f"   ⚠️  No suitable fresh inbound task found")
            return False
        
        task_id = task.get('id')
        expected_qty = task.get('expected_qty', 0)
        product_id = task.get('product_id')
        
        # Calculate qty exceeding +2% (e.g., 800 → 900 = +12.5%)
        exceed_tolerance_qty = expected_qty * 1.10  # +10% (exceeds +2%)
        
        print(f"   ✓ Task: {task.get('po_number')} - {task.get('product_name')}")
        print(f"   ✓ Expected qty: {expected_qty}")
        print(f"   ✓ Testing with qty: {exceed_tolerance_qty} (+10%, exceeds tolerance)")
        
        success, response = self.run_test(
            "Fase3: Scan-receive exceed tolerance (400)",
            "POST",
            f"api/inbound/tasks/{task_id}/scan-receive",
            400,
            data={
                "product_id": product_id,
                "actual_qty": exceed_tolerance_qty,
                "batch": "TEST-BATCH",
                "lot": "TEST-LOT",
                "roll_id": "",
                "bin_id": "A1-01"
            },
            token=token,
            description="Should return 400 with toleransi message"
        )
        
        if success:
            print(f"   ✅ Tolerance validation passed: got 400 for over-tolerance")
            return True
        return False

    # ── FASE 3: CASH MANAGEMENT ───────────────────────────────────────────────────
    
    def test_cash_transactions_list(self, role):
        """Test GET /api/cash-transactions - list transactions"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping cash transactions list test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: GET /api/cash-transactions for {role}")
        success, response = self.run_test(
            "Fase3: List cash transactions",
            "GET",
            "api/cash-transactions",
            200,
            token=token,
            description="Should return list of cash transactions (CASH-00001..CASH-00006)"
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} cash transactions")
            if len(response) > 0:
                sample = response[0]
                print(f"   ✓ Sample: {sample.get('number')} - {sample.get('cash_type')} {sample.get('direction')}")
            return True
        return False
    
    def test_cash_transactions_summary(self, role):
        """Test GET /api/cash-transactions/summary - get balances"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping cash summary test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: GET /api/cash-transactions/summary for {role}")
        success, response = self.run_test(
            "Fase3: Cash summary",
            "GET",
            "api/cash-transactions/summary",
            200,
            token=token,
            description="Should return kas_kecil, kas_besar with in/out/balance + kas_kecil_per_entity"
        )
        
        if success:
            kas_kecil = response.get('kas_kecil', {})
            kas_besar = response.get('kas_besar', {})
            per_entity = response.get('kas_kecil_per_entity', {})
            
            print(f"   ✓ Kas Kecil: in={kas_kecil.get('in')}, out={kas_kecil.get('out')}, balance={kas_kecil.get('balance')}")
            print(f"   ✓ Kas Besar: in={kas_besar.get('in')}, out={kas_besar.get('out')}, balance={kas_besar.get('balance')}")
            print(f"   ✓ Per entity breakdown: {len(per_entity)} entities")
            
            if 'in' in kas_kecil and 'balance' in kas_besar:
                print(f"   ✅ Summary structure correct")
                return True
        return False
    
    def test_cash_transactions_create(self, role):
        """Test POST /api/cash-transactions - create transaction"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping cash create test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: POST /api/cash-transactions for {role}")
        
        success, response = self.run_test(
            "Fase3: Create cash transaction (kas_kecil out)",
            "POST",
            "api/cash-transactions",
            200,
            data={
                "cash_type": "kas_kecil",
                "direction": "out",
                "amount": 500000,
                "category": "operasional",
                "description": "Test cash out",
                "entity_id": "",
                "ref_type": "",
                "ref_id": "",
                "txn_date": "",
                "created_by": "Test Admin"
            },
            token=token,
            description="Should create transaction with number CASH-NNNNN"
        )
        
        if success:
            number = response.get('number')
            cash_type = response.get('cash_type')
            direction = response.get('direction')
            amount = response.get('amount')
            
            print(f"   ✅ Cash transaction created: {number}")
            print(f"   ✓ Type: {cash_type}, Direction: {direction}, Amount: {amount}")
            
            if number and number.startswith('CASH-'):
                print(f"   ✅ Number format correct")
                self.cash_txn_ids.append(response.get('id'))
                return True
        return False
    
    def test_cash_transactions_kas_besar_force_all(self, role):
        """Test kas_besar forces entity_id='all'"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping kas_besar test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: kas_besar forces entity_id='all' for {role}")
        
        success, response = self.run_test(
            "Fase3: Create kas_besar transaction",
            "POST",
            "api/cash-transactions",
            200,
            data={
                "cash_type": "kas_besar",
                "direction": "in",
                "amount": 1000000,
                "category": "modal",
                "description": "Test kas besar",
                "entity_id": "some_entity",  # Should be overridden to 'all'
                "ref_type": "",
                "ref_id": "",
                "txn_date": "",
                "created_by": "Test Admin"
            },
            token=token,
            description="Should force entity_id='all' for kas_besar"
        )
        
        if success:
            entity_id = response.get('entity_id')
            print(f"   ✅ Kas besar transaction created")
            print(f"   ✓ Entity ID: {entity_id}")
            
            if entity_id == 'all':
                print(f"   ✅ Entity ID correctly forced to 'all'")
                return True
            else:
                print(f"   ❌ Expected entity_id='all', got '{entity_id}'")
                return False
        return False
    
    def test_cash_transactions_invalid_amount(self, role):
        """Test amount<=0 returns 400"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping invalid amount test for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Fase 3: Invalid amount (400) for {role}")
        
        success, response = self.run_test(
            "Fase3: Create cash with amount=0 (400)",
            "POST",
            "api/cash-transactions",
            400,
            data={
                "cash_type": "kas_kecil",
                "direction": "out",
                "amount": 0,
                "category": "operasional",
                "description": "Should fail",
                "entity_id": "",
                "ref_type": "",
                "ref_id": "",
                "txn_date": "",
                "created_by": "Test Admin"
            },
            token=token,
            description="Should return 400 for amount<=0"
        )
        
        if success:
            print(f"   ✅ Validation passed: got 400 for amount=0")
            return True
        return False
    
    def test_cash_transactions_void(self, role):
        """Test POST /api/cash-transactions/{id}/void"""
        token = self.tokens.get(role)
        if not token or not self.cash_txn_ids:
            print(f"⚠️  Skipping void test for {role} - no token or transaction")
            return False
        
        print(f"\n🔍 Testing Fase 3: POST /api/cash-transactions/{{id}}/void for {role}")
        
        txn_id = self.cash_txn_ids[0]
        success, response = self.run_test(
            "Fase3: Void cash transaction",
            "POST",
            f"api/cash-transactions/{txn_id}/void",
            200,
            token=token,
            description="Should set status=void, excluded from summary"
        )
        
        if success:
            status = response.get('status')
            print(f"   ✅ Transaction voided: status={status}")
            
            if status == 'void':
                print(f"   ✅ Void successful")
                return True
        return False

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*80)
        print("📊 FASE 3 PURCHASING TEST SUMMARY")
        print("="*80)
        print(f"Total tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Tests failed: {len(self.failed_tests)}")
        print(f"Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print("\n❌ Failed Tests:")
            for ft in self.failed_tests:
                print(f"  - {ft.get('test')}: {ft.get('error', '')} {ft.get('response', '')}")
        
        print("="*80)
        return len(self.failed_tests) == 0

def main():
    tester = Fase3PurchasingTester("https://po-pdf-sender.preview.emergentagent.com")
    
    print("🚀 Starting Fase 3 Purchasing Backend Tests")
    print("="*80)
    
    # Login as different roles
    print("\n📝 Logging in as different roles...")
    tester.test_login("admin@kainnusantara.id", "demo12345", "admin")
    tester.test_login("manager@kainnusantara.id", "demo12345", "manager")
    tester.test_login("warehouse@kainnusantara.id", "demo12345", "warehouse")
    
    # Test Suppliers CRUD
    print("\n\n🏢 TESTING SUPPLIER MASTER CRUD")
    print("="*80)
    tester.test_suppliers_list("admin")
    tester.test_suppliers_create("admin")
    tester.test_suppliers_get_detail("admin")
    tester.test_suppliers_update("admin")
    tester.test_suppliers_delete("admin")
    
    # Test Purchase Orders with Supplier FK
    print("\n\n📦 TESTING PURCHASE ORDERS WITH SUPPLIER FK")
    print("="*80)
    tester.test_po_with_supplier_fk("admin")
    tester.test_po_manual_supplier("admin")
    tester.test_po_no_supplier_400("admin")
    
    # Test Purchase Approval Workflow
    print("\n\n✅ TESTING PURCHASE APPROVAL WORKFLOW")
    print("="*80)
    tester.test_po_high_value_approval("admin")
    tester.test_po_approve("manager")
    tester.test_po_reject("manager")
    tester.test_po_low_value_no_approval("admin")
    
    # Test Receiving Tolerance
    print("\n\n📥 TESTING RECEIVING TOLERANCE ±2%")
    print("="*80)
    tester.test_receiving_tolerance_within("warehouse")
    tester.test_receiving_tolerance_exceed("warehouse")
    
    # Test Cash Management
    print("\n\n💰 TESTING CASH MANAGEMENT")
    print("="*80)
    tester.test_cash_transactions_list("admin")
    tester.test_cash_transactions_summary("admin")
    tester.test_cash_transactions_create("admin")
    tester.test_cash_transactions_kas_besar_force_all("admin")
    tester.test_cash_transactions_invalid_amount("admin")
    tester.test_cash_transactions_void("admin")
    
    # Print summary
    success = tester.print_summary()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
