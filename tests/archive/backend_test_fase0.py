"""Backend API Testing for Kain Nusantara FASE 0: Multi-Entity + Notification Center"""
import requests
import sys
from datetime import datetime

class Fase0APITester:
    def __init__(self, base_url="https://po-pdf-sender.preview.emergentagent.com"):
        self.base_url = base_url
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.created_entity_id = None

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
                    "endpoint": endpoint
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

    # ========== ENTITY MANAGEMENT TESTS ==========
    
    def test_list_entities(self, role):
        """Test GET /api/entities - should return 2 entities"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping entities list test for {role} - no token")
            return False
        
        success, response = self.run_test(
            f"List Entities ({role})",
            "GET",
            "api/entities",
            200,
            token=token,
            description="Should return 2 seeded entities (PT Kain Suka Cita, CV Kanda Suka)"
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} entities")
            if len(response) >= 2:
                for entity in response[:2]:
                    print(f"      - {entity.get('legal_name')} ({entity.get('short_name')}) [{entity.get('type')}]")
                return True
            else:
                print(f"   ⚠️  Expected at least 2 entities, got {len(response)}")
        return success

    def test_create_entity(self, role):
        """Test POST /api/entities - admin only"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping create entity test for {role} - no token")
            return False
        
        entity_data = {
            "legal_name": "PT Test Fase 0",
            "short_name": f"TEST{datetime.now().strftime('%H%M%S')}",
            "type": "PT",
            "npwp": "99.999.999.9-999.000",
            "address": "Jl. Test No. 123",
            "city": "Jakarta",
            "default_tax_mode": "ppn",
            "doc_prefix": "TST",
            "logo_url": ""
        }
        
        expected_status = 200 if role == "admin" else 403
        success, response = self.run_test(
            f"Create Entity ({role})",
            "POST",
            "api/entities",
            expected_status,
            data=entity_data,
            token=token,
            description=f"Create new entity (admin only, {role} expects {expected_status})"
        )
        
        if success and role == "admin" and response.get('id'):
            self.created_entity_id = response['id']
            print(f"   ✓ Created entity ID: {self.created_entity_id}")
            print(f"   ✓ Entity: {response.get('legal_name')} ({response.get('short_name')})")
        
        return success

    def test_duplicate_entity_short_name(self, role):
        """Test POST /api/entities with duplicate short_name - should return 409"""
        token = self.tokens.get(role)
        if not token or role != "admin":
            print(f"⚠️  Skipping duplicate entity test for {role} - requires admin")
            return False
        
        entity_data = {
            "legal_name": "PT Duplicate Test",
            "short_name": "KSC",  # Duplicate of existing entity
            "type": "PT",
            "npwp": "88.888.888.8-888.000",
            "address": "Jl. Duplicate No. 456",
            "city": "Bandung",
            "default_tax_mode": "ppn",
            "doc_prefix": "DUP"
        }
        
        success, response = self.run_test(
            "Duplicate Entity Short Name",
            "POST",
            "api/entities",
            409,
            data=entity_data,
            token=token,
            description="Should return 409 for duplicate short_name"
        )
        
        return success

    def test_update_entity(self, role):
        """Test PATCH /api/entities/{id} - admin only"""
        token = self.tokens.get(role)
        if not token or role != "admin" or not self.created_entity_id:
            print(f"⚠️  Skipping update entity test for {role} - requires admin and created entity")
            return False
        
        update_data = {
            "data": {
                "city": "Surabaya",
                "address": "Jl. Updated No. 789"
            }
        }
        
        success, response = self.run_test(
            f"Update Entity ({role})",
            "PATCH",
            f"api/entities/{self.created_entity_id}",
            200,
            data=update_data,
            token=token,
            description=f"Update entity {self.created_entity_id}"
        )
        
        if success:
            print(f"   ✓ Updated city: {response.get('city')}")
            print(f"   ✓ Updated address: {response.get('address')}")
        
        return success

    def test_delete_entity(self, role):
        """Test DELETE /api/entities/{id} - soft delete (status=inactive)"""
        token = self.tokens.get(role)
        if not token or role != "admin" or not self.created_entity_id:
            print(f"⚠️  Skipping delete entity test for {role} - requires admin and created entity")
            return False
        
        success, response = self.run_test(
            f"Delete Entity ({role})",
            "DELETE",
            f"api/entities/{self.created_entity_id}",
            200,
            token=token,
            description=f"Soft delete entity {self.created_entity_id} (status=inactive)"
        )
        
        if success:
            print(f"   ✓ Entity status: {response.get('status')}")
            if response.get('status') == 'inactive':
                print(f"   ✅ Soft delete verified (status=inactive)")
            else:
                print(f"   ⚠️  Expected status=inactive, got {response.get('status')}")
        
        return success

    # ========== NOTIFICATION CENTER TESTS ==========
    
    def test_list_notifications(self, role):
        """Test GET /api/notifications"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping notifications list test for {role} - no token")
            return False
        
        success, response = self.run_test(
            f"List Notifications ({role})",
            "GET",
            "api/notifications",
            200,
            token=token,
            description="Get all notifications for user"
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} notifications")
            if len(response) > 0:
                notif = response[0]
                print(f"      - {notif.get('title')} [{notif.get('severity')}] (read: {notif.get('read')})")
        
        return success

    def test_unread_count(self, role):
        """Test GET /api/notifications/unread-count"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping unread count test for {role} - no token")
            return False
        
        success, response = self.run_test(
            f"Unread Count ({role})",
            "GET",
            "api/notifications/unread-count",
            200,
            token=token,
            description="Get unread notification count"
        )
        
        if success and 'count' in response:
            print(f"   ✓ Unread count: {response['count']}")
        
        return success

    def test_mark_notification_read(self, role):
        """Test POST /api/notifications/{id}/read"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping mark read test for {role} - no token")
            return False
        
        # First get notifications to find an unread one
        success, notifications = self.run_test(
            f"Get Notifications for Mark Read ({role})",
            "GET",
            "api/notifications",
            200,
            token=token,
            description="Get notifications to find unread one"
        )
        
        if success and isinstance(notifications, list) and len(notifications) > 0:
            unread_notif = next((n for n in notifications if not n.get('read')), notifications[0])
            notif_id = unread_notif.get('id')
            
            if notif_id:
                success, response = self.run_test(
                    f"Mark Notification Read ({role})",
                    "POST",
                    f"api/notifications/{notif_id}/read",
                    200,
                    token=token,
                    description=f"Mark notification {notif_id} as read"
                )
                
                if success:
                    print(f"   ✓ Notification marked read: {response.get('read')}")
                    print(f"   ✓ Read at: {response.get('read_at')}")
                
                return success
        
        print(f"   ⚠️  No notifications found to mark as read")
        return True  # Not a failure, just no data

    def test_mark_all_read(self, role):
        """Test POST /api/notifications/read-all"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping mark all read test for {role} - no token")
            return False
        
        success, response = self.run_test(
            f"Mark All Read ({role})",
            "POST",
            "api/notifications/read-all",
            200,
            token=token,
            description="Mark all notifications as read"
        )
        
        if success and 'updated' in response:
            print(f"   ✓ Marked {response['updated']} notifications as read")
        
        return success

    def test_generate_notifications(self, role):
        """Test POST /api/notifications/generate - admin/manager only, idempotent"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping generate notifications test for {role} - no token")
            return False
        
        expected_status = 200 if role in ["admin", "manager"] else 403
        
        # First call
        success1, response1 = self.run_test(
            f"Generate Notifications - Call 1 ({role})",
            "POST",
            "api/notifications/generate",
            expected_status,
            token=token,
            description=f"Generate system notifications (admin/manager only, {role} expects {expected_status})"
        )
        
        if success1 and role in ["admin", "manager"]:
            created1 = response1.get('created', 0)
            print(f"   ✓ First call created: {created1} notifications")
            
            # Second call - should be idempotent (dedupe by ref)
            success2, response2 = self.run_test(
                f"Generate Notifications - Call 2 ({role})",
                "POST",
                "api/notifications/generate",
                200,
                token=token,
                description="Second call should be idempotent (dedupe by ref)"
            )
            
            if success2:
                created2 = response2.get('created', 0)
                print(f"   ✓ Second call created: {created2} notifications")
                if created2 == 0:
                    print(f"   ✅ Idempotency verified (dedupe working)")
                else:
                    print(f"   ⚠️  Expected 0 on second call (idempotent), got {created2}")
            
            return success1 and success2
        
        return success1

    # ========== ENTITY SCOPING TESTS ==========
    
    def test_dashboard_entity_scoping(self, role):
        """Test GET /api/dashboard with entity_id filter - scoped vs shared resources"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping dashboard entity scoping test for {role} - no token")
            return False
        
        # Get dashboard without filter (all entities)
        success1, response_all = self.run_test(
            f"Dashboard - All Entities ({role})",
            "GET",
            "api/dashboard",
            200,
            token=token,
            description="Get dashboard for all entities"
        )
        
        if not success1:
            return False
        
        metrics_all = response_all.get('metrics', {})
        print(f"   ✓ All entities metrics:")
        print(f"      - active_orders: {metrics_all.get('active_orders')}")
        print(f"      - customers: {metrics_all.get('customers')}")
        print(f"      - products: {metrics_all.get('products')} (SHARED)")
        print(f"      - warehouses: {metrics_all.get('warehouses')} (SHARED)")
        print(f"      - available_qty: {metrics_all.get('available_qty')} (SHARED)")
        print(f"      - reserved_qty: {metrics_all.get('reserved_qty')} (SHARED)")
        
        # Get dashboard with entity_id=ent_kanda filter
        success2, response_kanda = self.run_test(
            f"Dashboard - Entity Kanda ({role})",
            "GET",
            "api/dashboard?entity_id=ent_kanda",
            200,
            token=token,
            description="Get dashboard filtered by entity_id=ent_kanda"
        )
        
        if not success2:
            return False
        
        metrics_kanda = response_kanda.get('metrics', {})
        print(f"   ✓ Kanda entity metrics:")
        print(f"      - active_orders: {metrics_kanda.get('active_orders')} (SCOPED)")
        print(f"      - customers: {metrics_kanda.get('customers')} (SCOPED)")
        print(f"      - products: {metrics_kanda.get('products')} (SHARED)")
        print(f"      - warehouses: {metrics_kanda.get('warehouses')} (SHARED)")
        print(f"      - available_qty: {metrics_kanda.get('available_qty')} (SHARED)")
        print(f"      - reserved_qty: {metrics_kanda.get('reserved_qty')} (SHARED)")
        
        # Verify scoping: Kanda should have FEWER active_orders and customers
        if metrics_kanda.get('active_orders', 0) < metrics_all.get('active_orders', 0):
            print(f"   ✅ Entity scoping verified: Kanda has fewer active_orders")
        else:
            print(f"   ⚠️  Expected Kanda to have fewer active_orders")
        
        # Verify shared resources: products, warehouses, available_qty, reserved_qty should be SAME
        shared_same = (
            metrics_kanda.get('products') == metrics_all.get('products') and
            metrics_kanda.get('warehouses') == metrics_all.get('warehouses') and
            metrics_kanda.get('available_qty') == metrics_all.get('available_qty') and
            metrics_kanda.get('reserved_qty') == metrics_all.get('reserved_qty')
        )
        
        if shared_same:
            print(f"   ✅ Shared resources verified: products/warehouses/stock same across entities")
        else:
            print(f"   ⚠️  Shared resources should be same across entities")
        
        return success1 and success2

    def test_sales_orders_entity_scoping(self, role):
        """Test GET /api/sales-orders with entity_id filter"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping sales orders entity scoping test for {role} - no token")
            return False
        
        # Get all orders
        success1, orders_all = self.run_test(
            f"Sales Orders - All Entities ({role})",
            "GET",
            "api/sales-orders",
            200,
            token=token,
            description="Get all sales orders (no filter)"
        )
        
        if not success1 or not isinstance(orders_all, list):
            return False
        
        print(f"   ✓ All entities: {len(orders_all)} orders")
        
        # Get orders for ent_ksc
        success2, orders_ksc = self.run_test(
            f"Sales Orders - Entity KSC ({role})",
            "GET",
            "api/sales-orders?entity_id=ent_ksc",
            200,
            token=token,
            description="Get sales orders filtered by entity_id=ent_ksc"
        )
        
        if not success2 or not isinstance(orders_ksc, list):
            return False
        
        print(f"   ✓ KSC entity: {len(orders_ksc)} orders")
        
        # Get orders for ent_kanda
        success3, orders_kanda = self.run_test(
            f"Sales Orders - Entity Kanda ({role})",
            "GET",
            "api/sales-orders?entity_id=ent_kanda",
            200,
            token=token,
            description="Get sales orders filtered by entity_id=ent_kanda"
        )
        
        if not success3 or not isinstance(orders_kanda, list):
            return False
        
        print(f"   ✓ Kanda entity: {len(orders_kanda)} orders")
        
        # Verify: KSC + Kanda should approximately equal total (allowing for some variance)
        total_filtered = len(orders_ksc) + len(orders_kanda)
        print(f"   ✓ KSC ({len(orders_ksc)}) + Kanda ({len(orders_kanda)}) = {total_filtered}")
        print(f"   ✓ Total unfiltered: {len(orders_all)}")
        
        if total_filtered <= len(orders_all):
            print(f"   ✅ Entity scoping verified: filtered subsets <= total")
        else:
            print(f"   ⚠️  Filtered subsets exceed total (possible issue)")
        
        return success1 and success2 and success3

    def test_customers_entity_scoping(self, role):
        """Test GET /api/customers with entity_id filter"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping customers entity scoping test for {role} - no token")
            return False
        
        # Get all customers
        success1, customers_all = self.run_test(
            f"Customers - All Entities ({role})",
            "GET",
            "api/customers",
            200,
            token=token,
            description="Get all customers (no filter)"
        )
        
        if not success1 or not isinstance(customers_all, list):
            return False
        
        print(f"   ✓ All entities: {len(customers_all)} customers")
        
        # Get customers for ent_kanda
        success2, customers_kanda = self.run_test(
            f"Customers - Entity Kanda ({role})",
            "GET",
            "api/customers?entity_id=ent_kanda",
            200,
            token=token,
            description="Get customers filtered by entity_id=ent_kanda"
        )
        
        if not success2 or not isinstance(customers_kanda, list):
            return False
        
        print(f"   ✓ Kanda entity: {len(customers_kanda)} customers")
        
        if len(customers_kanda) < len(customers_all):
            print(f"   ✅ Entity scoping verified: Kanda has fewer customers than total")
        else:
            print(f"   ⚠️  Expected Kanda to have fewer customers than total")
        
        return success1 and success2

    # ========== NEW FIELDS TESTS ==========
    
    def test_create_customer_with_new_fields(self, role):
        """Test POST /api/customers with new fields (npwp, credit_limit, sales_pic, entity_id)"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping create customer test for {role} - no token")
            return False
        
        customer_data = {
            "name": f"Test Customer Fase0 {datetime.now().strftime('%H%M%S')}",
            "pic_name": "Pak Test",
            "phone": "081234567890",
            "email": "test@fase0.id",
            "type": "Retail",
            "city": "Jakarta",
            "address": "Jl. Test No. 123",
            "npwp": "11.222.333.4-555.000",
            "credit_limit": 50000000,
            "sales_pic": "Ayu Marketing",
            "entity_id": "ent_kanda"
        }
        
        expected_status = 200 if role in ["admin", "sales"] else 403
        success, response = self.run_test(
            f"Create Customer with New Fields ({role})",
            "POST",
            "api/customers",
            expected_status,
            data=customer_data,
            token=token,
            description=f"Create customer with npwp, credit_limit, sales_pic, entity_id"
        )
        
        if success and role in ["admin", "sales"]:
            print(f"   ✓ Customer created: {response.get('name')}")
            print(f"   ✓ NPWP: {response.get('npwp')}")
            print(f"   ✓ Credit Limit: {response.get('credit_limit')}")
            print(f"   ✓ Sales PIC: {response.get('sales_pic')}")
            print(f"   ✓ Entity ID: {response.get('entity_id')}")
            
            # Verify new fields are persisted
            if (response.get('npwp') == customer_data['npwp'] and
                response.get('credit_limit') == customer_data['credit_limit'] and
                response.get('sales_pic') == customer_data['sales_pic'] and
                response.get('entity_id') == customer_data['entity_id']):
                print(f"   ✅ New fields persisted correctly")
            else:
                print(f"   ⚠️  New fields not persisted correctly")
        
        return success

    def test_create_product_with_new_fields(self, role):
        """Test POST /api/products with new fields (harga_pokok, gramasi)"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping create product test for {role} - no token")
            return False
        
        product_data = {
            "sku": f"TST-FASE0-{datetime.now().strftime('%H%M%S')}",
            "name": "Test Product Fase 0",
            "category": "Batik",
            "variant": "Premium",
            "color": "Biru",
            "motif": "Test",
            "grade": "A",
            "supplier": "Test Supplier",
            "base_unit": "meter",
            "price": 150000,
            "harga_pokok": 100000,
            "gramasi": 120,
            "status": "active"
        }
        
        expected_status = 200 if role == "admin" else 403
        success, response = self.run_test(
            f"Create Product with New Fields ({role})",
            "POST",
            "api/products",
            expected_status,
            data=product_data,
            token=token,
            description=f"Create product with harga_pokok and gramasi"
        )
        
        if success and role == "admin":
            print(f"   ✓ Product created: {response.get('name')}")
            print(f"   ✓ SKU: {response.get('sku')}")
            print(f"   ✓ Price: {response.get('price')}")
            print(f"   ✓ Harga Pokok: {response.get('harga_pokok')}")
            print(f"   ✓ Gramasi: {response.get('gramasi')}")
            
            # Verify new fields are persisted
            if (response.get('harga_pokok') == product_data['harga_pokok'] and
                response.get('gramasi') == product_data['gramasi']):
                print(f"   ✅ New fields persisted correctly")
                return True
            else:
                print(f"   ⚠️  New fields not persisted correctly")
                return False
        
        return success

    def test_update_product_new_fields(self, role):
        """Test PATCH /api/products/{id} to update harga_pokok and gramasi"""
        token = self.tokens.get(role)
        if not token or role != "admin":
            print(f"⚠️  Skipping update product test for {role} - requires admin")
            return False
        
        # First get a product
        success, products = self.run_test(
            "Get Products for Update Test",
            "GET",
            "api/products",
            200,
            token=token,
            description="Get products to find one to update"
        )
        
        if not success or not isinstance(products, list) or len(products) == 0:
            print(f"   ⚠️  No products found to update")
            return False
        
        product = products[0]
        product_id = product.get('id')
        
        update_data = {
            "data": {
                "harga_pokok": 125000,
                "gramasi": 150
            }
        }
        
        success, response = self.run_test(
            f"Update Product New Fields ({role})",
            "PATCH",
            f"api/products/{product_id}",
            200,
            data=update_data,
            token=token,
            description=f"Update harga_pokok and gramasi for product {product_id}"
        )
        
        if success:
            print(f"   ✓ Updated harga_pokok: {response.get('harga_pokok')}")
            print(f"   ✓ Updated gramasi: {response.get('gramasi')}")
            
            if (response.get('harga_pokok') == update_data['data']['harga_pokok'] and
                response.get('gramasi') == update_data['data']['gramasi']):
                print(f"   ✅ New fields updated correctly")
            else:
                print(f"   ⚠️  New fields not updated correctly")
        
        return success

    # ========== REGRESSION TESTS ==========
    
    def test_regression_endpoints(self, role):
        """Test that existing endpoints still work"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping regression tests for {role} - no token")
            return False
        
        print(f"\n🔍 Testing Regression: Existing Endpoints for {role}")
        
        endpoints = [
            ("Dashboard", "GET", "api/dashboard", 200),
            ("Products", "GET", "api/products", 200),
            ("Customers", "GET", "api/customers", 200),
            ("Warehouses", "GET", "api/warehouses", 200),
            ("Sales Orders", "GET", "api/sales-orders", 200),
            ("Invoices", "GET", "api/invoices", 200),
            ("Purchase Orders", "GET", "api/purchase-orders", 200),
        ]
        
        all_success = True
        for name, method, endpoint, expected_status in endpoints:
            success, _ = self.run_test(
                f"Regression: {name}",
                method,
                endpoint,
                expected_status,
                token=token,
                description=f"Verify {endpoint} still works"
            )
            if not success:
                all_success = False
        
        return all_success

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print(f"📊 FASE 0 TEST SUMMARY")
        print("="*70)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print("\n❌ FAILED TESTS:")
            for fail in self.failed_tests:
                error_msg = fail.get('error', f"Expected {fail.get('expected')}, got {fail.get('actual')}")
                print(f"  - {fail['test']}: {error_msg}")
                print(f"    Endpoint: {fail['endpoint']}")
        
        print("="*70)


def main():
    print("="*70)
    print("🧪 KAIN NUSANTARA FASE 0 API TEST SUITE")
    print("   Multi-Entity Foundation + Notification Center + Master Fields")
    print("="*70)
    
    tester = Fase0APITester()
    
    # Test login for all roles
    print("\n📍 TESTING AUTHENTICATION")
    print("-"*70)
    roles = [
        ("admin@kainnusantara.id", "demo12345", "admin"),
        ("sales@kainnusantara.id", "demo12345", "sales"),
        ("manager@kainnusantara.id", "demo12345", "manager"),
        ("warehouse@kainnusantara.id", "demo12345", "warehouse"),
    ]
    
    for email, password, role in roles:
        if not tester.test_login(email, password, role):
            print(f"❌ {role} login failed")
    
    # ENTITY MANAGEMENT TESTS
    print("\n" + "="*70)
    print("🏢 ENTITY MANAGEMENT TESTS")
    print("="*70)
    
    tester.test_list_entities("admin")
    tester.test_create_entity("admin")
    tester.test_create_entity("sales")  # Should fail (403)
    tester.test_duplicate_entity_short_name("admin")
    tester.test_update_entity("admin")
    tester.test_delete_entity("admin")
    
    # NOTIFICATION CENTER TESTS
    print("\n" + "="*70)
    print("🔔 NOTIFICATION CENTER TESTS")
    print("="*70)
    
    tester.test_list_notifications("admin")
    tester.test_unread_count("admin")
    tester.test_mark_notification_read("admin")
    tester.test_mark_all_read("admin")
    tester.test_generate_notifications("admin")
    tester.test_generate_notifications("manager")
    tester.test_generate_notifications("sales")  # Should fail (403)
    
    # ENTITY SCOPING TESTS
    print("\n" + "="*70)
    print("🎯 ENTITY SCOPING TESTS")
    print("="*70)
    
    tester.test_dashboard_entity_scoping("admin")
    tester.test_sales_orders_entity_scoping("admin")
    tester.test_customers_entity_scoping("admin")
    
    # NEW FIELDS TESTS
    print("\n" + "="*70)
    print("📝 NEW FIELDS TESTS")
    print("="*70)
    
    tester.test_create_customer_with_new_fields("admin")
    tester.test_create_customer_with_new_fields("sales")
    tester.test_create_product_with_new_fields("admin")
    tester.test_update_product_new_fields("admin")
    
    # REGRESSION TESTS
    print("\n" + "="*70)
    print("🔄 REGRESSION TESTS")
    print("="*70)
    
    tester.test_regression_endpoints("admin")
    
    # Print summary
    tester.print_summary()
    
    # Return exit code
    return 0 if tester.tests_passed == tester.tests_run else 1


if __name__ == "__main__":
    sys.exit(main())
