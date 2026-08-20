#!/usr/bin/env python3
"""
BACKEND TEST - FASE E-3 VERIFICATION
Testing write guard, entity isolation, and new endpoints for Entities & Access screen.
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://hub-manager-preview.preview.emergentagent.com"
PASSWORD = "demo12345"

class E3BackendTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.admin_session = None
        self.sales3_session = None
        self.admin_token = None
        self.sales3_token = None
        
    def log(self, status, message):
        """Log test result"""
        self.tests_run += 1
        if status == "PASS":
            self.tests_passed += 1
            print(f"  ✅ [PASS] {message}")
        else:
            self.tests_failed += 1
            print(f"  ❌ [FAIL] {message}")
    
    def login(self, email):
        """Login and return session with token"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": PASSWORD},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                token = data.get("token")
                if not token:
                    print(f"  ⚠️  Login response missing 'token' key: {data.keys()}")
                    return None
                session = requests.Session()
                session.headers.update({
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                })
                return session, token
            else:
                print(f"  ⚠️  Login failed for {email}: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            print(f"  ⚠️  Login error for {email}: {str(e)}")
            return None
    
    def test_write_guard_blocks_create_in_all_mode(self):
        """Test that write guard blocks document creation in 'all' mode"""
        print("\n📋 TEST 1: Write Guard - Block Creation in 'All Entities' Mode")
        
        endpoints_to_test = [
            ("/api/customers", {"name": "Test Customer", "phone": "081234567890", "address": "Test", "city": "Test"}, "customers"),
            ("/api/sales-orders", {"customer_id": "test", "items": []}, "sales orders"),
            ("/api/ar-receipts", {"customer_id": "test", "amount": 1000}, "AR receipts"),
            ("/api/purchase-requisitions", {"items": []}, "purchase requisitions"),
            ("/api/hr/employees", {"name": "Test Employee"}, "HR employees"),
            ("/api/suppliers", {"name": "Test Supplier"}, "suppliers"),
            ("/api/wms/tasks", {"task_type": "inbound"}, "WMS tasks"),
        ]
        
        for endpoint, payload, label in endpoints_to_test:
            try:
                response = self.admin_session.post(
                    f"{BASE_URL}{endpoint}",
                    json=payload,
                    headers={"X-Entity-Id": "all"},
                    timeout=30
                )
                
                if response.status_code == 409:
                    detail = response.json().get("detail", "")
                    if "Semua Entitas" in detail or "badan usaha" in detail:
                        self.log("PASS", f"POST {endpoint} with X-Entity-Id:all → 409 with proper message")
                    else:
                        self.log("FAIL", f"POST {endpoint} → 409 but message doesn't mention 'Semua Entitas': {detail}")
                else:
                    self.log("FAIL", f"POST {endpoint} with X-Entity-Id:all → {response.status_code} (expected 409). Response: {response.text[:200]}")
            except Exception as e:
                self.log("FAIL", f"POST {endpoint} error: {str(e)}")
    
    def test_write_guard_allows_after_selecting_entity(self):
        """Test that operations succeed after selecting a specific entity"""
        print("\n📋 TEST 2: Write Guard - Allow Creation After Selecting Entity")
        
        try:
            # Create customer with specific entity
            response = self.admin_session.post(
                f"{BASE_URL}/api/customers",
                json={
                    "name": f"Test Customer {datetime.now().strftime('%H%M%S')}",
                    "pic_name": "Test PIC",
                    "phone": "081234567890",
                    "address": "Test Address",
                    "city": "Bandung"
                },
                headers={"X-Entity-Id": "ent_kanda"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                entity_id = data.get("entity_id")
                customer_id = data.get("id")
                
                if entity_id == "ent_kanda":
                    self.log("PASS", f"POST /api/customers with X-Entity-Id:ent_kanda → 200 and entity_id=ent_kanda")
                    
                    # Clean up
                    if customer_id:
                        try:
                            self.admin_session.delete(f"{BASE_URL}/api/customers/{customer_id}", timeout=30)
                        except Exception:  # noqa: S110
                            pass
                else:
                    self.log("FAIL", f"Customer created but entity_id={entity_id}, expected ent_kanda")
            else:
                self.log("FAIL", f"POST /api/customers with X-Entity-Id:ent_kanda → {response.status_code}. Response: {response.text[:200]}")
        except Exception as e:
            self.log("FAIL", f"Error testing entity selection: {str(e)}")
    
    def test_write_guard_allows_get_operations(self):
        """Test that GET operations are allowed in 'all' mode"""
        print("\n📋 TEST 3: Write Guard - Allow GET Operations in 'All' Mode")
        
        endpoints = [
            "/api/customers",
            "/api/sales-orders",
            "/api/dashboard",
        ]
        
        for endpoint in endpoints:
            try:
                response = self.admin_session.get(
                    f"{BASE_URL}{endpoint}",
                    headers={"X-Entity-Id": "all"},
                    timeout=30
                )
                
                if response.status_code == 200:
                    self.log("PASS", f"GET {endpoint} with X-Entity-Id:all → 200")
                else:
                    self.log("FAIL", f"GET {endpoint} with X-Entity-Id:all → {response.status_code}")
            except Exception as e:
                self.log("FAIL", f"GET {endpoint} error: {str(e)}")
    
    def test_write_guard_allows_shared_masters(self):
        """Test that shared master creation is allowed in 'all' mode"""
        print("\n📋 TEST 4: Write Guard - Allow Shared Masters in 'All' Mode")
        
        # Test UOM creation (shared master)
        try:
            response = self.admin_session.post(
                f"{BASE_URL}/api/uoms",
                json={
                    "code": f"TST{datetime.now().strftime('%H%M%S')}",
                    "name": f"Test UOM {datetime.now().strftime('%H%M%S')}",
                    "base_type": "length",
                    "precision": 2
                },
                headers={"X-Entity-Id": "all"},
                timeout=30
            )
            
            if response.status_code == 200:
                self.log("PASS", "POST /api/uoms with X-Entity-Id:all → 200 (shared master allowed)")
                # Clean up
                uom_id = response.json().get("id")
                if uom_id:
                    try:
                        self.admin_session.delete(f"{BASE_URL}/api/uoms/{uom_id}", timeout=30)
                    except Exception:  # noqa: S110
                        pass
            else:
                self.log("FAIL", f"POST /api/uoms with X-Entity-Id:all → {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error testing shared masters: {str(e)}")
        
        # Test product category creation (shared master)
        try:
            response = self.admin_session.post(
                f"{BASE_URL}/api/product-categories",
                json={
                    "code": f"TSTCAT{datetime.now().strftime('%H%M%S')}",
                    "name": f"Test Category {datetime.now().strftime('%H%M%S')}"
                },
                headers={"X-Entity-Id": "all"},
                timeout=30
            )
            
            if response.status_code in (200, 201):
                self.log("PASS", "POST /api/product-categories with X-Entity-Id:all → 200 (shared master allowed)")
                # Clean up
                cat_id = response.json().get("id")
                if cat_id:
                    try:
                        self.admin_session.delete(f"{BASE_URL}/api/product-categories/{cat_id}", timeout=30)
                    except Exception:  # noqa: S110
                        pass
            else:
                self.log("FAIL", f"POST /api/product-categories with X-Entity-Id:all → {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error testing product categories: {str(e)}")
    
    def test_write_guard_allows_updates_to_existing(self):
        """Test that PATCH operations on existing documents are allowed"""
        print("\n📋 TEST 5: Write Guard - Allow Updates to Existing Documents")
        
        try:
            # Get entities
            response = self.admin_session.get(f"{BASE_URL}/api/entities", timeout=30)
            if response.status_code == 200:
                entities = response.json()
                if len(entities) > 0:
                    entity_id = entities[0].get("id")
                    
                    # Try to patch entity in 'all' mode
                    patch_response = self.admin_session.patch(
                        f"{BASE_URL}/api/entities/{entity_id}",
                        json={"data": {"phone": "0800123456"}},
                        headers={"X-Entity-Id": "all"},
                        timeout=30
                    )
                    
                    if patch_response.status_code == 200:
                        self.log("PASS", f"PATCH /api/entities/{{id}} with X-Entity-Id:all → 200 (update existing allowed)")
                    else:
                        self.log("FAIL", f"PATCH /api/entities/{{id}} with X-Entity-Id:all → {patch_response.status_code}")
                else:
                    self.log("FAIL", "No entities found to test PATCH operation")
            else:
                self.log("FAIL", f"GET /api/entities failed: {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error testing updates: {str(e)}")
    
    def test_entity_isolation_sales3(self):
        """Test that sales3@kainnusantara.id (CV Kanda Suka) only sees their entity data"""
        print("\n📋 TEST 6: Entity Isolation - sales3 (CV Kanda Suka)")
        
        # Test customers
        try:
            response = self.sales3_session.get(f"{BASE_URL}/api/customers", timeout=30)
            if response.status_code == 200:
                customers = response.json()
                # Check that all customers belong to ent_kanda
                wrong_entity = [c for c in customers if c.get("entity_id") not in ("ent_kanda", None, "")]
                if len(wrong_entity) == 0:
                    self.log("PASS", f"sales3 GET /api/customers → only sees ent_kanda data ({len(customers)} customers)")
                else:
                    self.log("FAIL", f"sales3 sees {len(wrong_entity)} customers from other entities: {[c.get('entity_id') for c in wrong_entity]}")
            else:
                self.log("FAIL", f"sales3 GET /api/customers → {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error testing sales3 customers: {str(e)}")
        
        # Test sales orders
        try:
            response = self.sales3_session.get(f"{BASE_URL}/api/sales-orders", timeout=30)
            if response.status_code == 200:
                orders = response.json()
                wrong_entity = [o for o in orders if o.get("entity_id") not in ("ent_kanda", None, "")]
                if len(wrong_entity) == 0:
                    self.log("PASS", f"sales3 GET /api/sales-orders → only sees ent_kanda data ({len(orders)} orders)")
                else:
                    self.log("FAIL", f"sales3 sees {len(wrong_entity)} orders from other entities")
            else:
                self.log("FAIL", f"sales3 GET /api/sales-orders → {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error testing sales3 orders: {str(e)}")
        
        # Test notifications
        try:
            response = self.sales3_session.get(f"{BASE_URL}/api/notifications", timeout=30)
            if response.status_code == 200:
                notifications = response.json()
                wrong_entity = [n for n in notifications if n.get("entity_id") not in ("ent_kanda", None, "")]
                if len(wrong_entity) == 0:
                    self.log("PASS", f"sales3 GET /api/notifications → only sees ent_kanda data ({len(notifications)} notifications)")
                else:
                    self.log("FAIL", f"sales3 sees {len(wrong_entity)} notifications from other entities")
            else:
                self.log("FAIL", f"sales3 GET /api/notifications → {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error testing sales3 notifications: {str(e)}")
        
        # Test audit logs (should be 403 for sales)
        try:
            response = self.sales3_session.get(f"{BASE_URL}/api/audit-logs", timeout=30)
            if response.status_code == 403:
                self.log("PASS", "sales3 GET /api/audit-logs → 403 (correctly forbidden)")
            else:
                self.log("FAIL", f"sales3 GET /api/audit-logs → {response.status_code} (expected 403)")
        except Exception as e:
            self.log("FAIL", f"Error testing sales3 audit logs: {str(e)}")
        
        # Test that sales3 cannot access ent_ksc data by forcing header
        try:
            response = self.sales3_session.get(
                f"{BASE_URL}/api/customers",
                headers={"X-Entity-Id": "ent_ksc"},
                timeout=30
            )
            if response.status_code == 200:
                customers = response.json()
                ksc_customers = [c for c in customers if c.get("entity_id") == "ent_ksc"]
                if len(ksc_customers) == 0:
                    self.log("PASS", "sales3 with X-Entity-Id:ent_ksc → still cannot see ent_ksc data")
                else:
                    self.log("FAIL", f"sales3 with X-Entity-Id:ent_ksc → sees {len(ksc_customers)} ent_ksc customers (isolation breach!)")
            elif response.status_code == 403:
                self.log("PASS", "sales3 with X-Entity-Id:ent_ksc → 403 (correctly forbidden)")
            else:
                self.log("FAIL", f"sales3 with X-Entity-Id:ent_ksc → {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error testing sales3 forced header: {str(e)}")
    
    def test_new_endpoints_e3(self):
        """Test new endpoints for E-3 Entities & Access screen"""
        print("\n📋 TEST 7: New Endpoints for E-3 Screen")
        
        # GET /api/entities?status=all&with_readiness=true
        try:
            response = self.admin_session.get(
                f"{BASE_URL}/api/entities",
                params={"status": "all", "with_readiness": "true"},
                timeout=30
            )
            if response.status_code == 200:
                entities = response.json()
                if len(entities) > 0:
                    first = entities[0]
                    has_readiness = "readiness" in first or "user_count" in first
                    if has_readiness:
                        self.log("PASS", f"GET /api/entities?status=all&with_readiness=true → 200 with readiness data")
                    else:
                        self.log("FAIL", f"GET /api/entities → 200 but missing readiness data. Keys: {first.keys()}")
                else:
                    self.log("FAIL", "GET /api/entities → 200 but empty list")
            else:
                self.log("FAIL", f"GET /api/entities?status=all&with_readiness=true → {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error testing entities endpoint: {str(e)}")
        
        # GET /api/entities/count
        try:
            response = self.admin_session.get(f"{BASE_URL}/api/entities/count", timeout=30)
            if response.status_code == 200:
                self.log("PASS", f"GET /api/entities/count → 200")
            else:
                self.log("FAIL", f"GET /api/entities/count → {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error testing entities count: {str(e)}")
        
        # GET /api/enums/entity_type
        try:
            response = self.admin_session.get(f"{BASE_URL}/api/enums/entity_type", timeout=30)
            if response.status_code == 200:
                self.log("PASS", "GET /api/enums/entity_type → 200")
            else:
                self.log("FAIL", f"GET /api/enums/entity_type → {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error testing entity_type enum: {str(e)}")
        
        # GET /api/users with filters
        try:
            response = self.admin_session.get(
                f"{BASE_URL}/api/users",
                params={"limit": 10, "role": "admin", "status": "active"},
                timeout=30
            )
            if response.status_code == 200:
                self.log("PASS", "GET /api/users with filters → 200")
            else:
                self.log("FAIL", f"GET /api/users with filters → {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error testing users endpoint: {str(e)}")
    
    def test_entity_lifecycle(self):
        """Test entity lifecycle operations"""
        print("\n📋 TEST 8: Entity Lifecycle (Archive/Reactivate)")
        
        # Get an entity to test with
        try:
            response = self.admin_session.get(f"{BASE_URL}/api/entities", timeout=30)
            if response.status_code == 200:
                entities = response.json()
                # Find a test entity or use the first one
                test_entity = None
                for e in entities:
                    if e.get("status") == "active" and e.get("id") not in ("ent_ksc", "ent_kanda"):
                        test_entity = e
                        break
                
                if not test_entity and len(entities) > 0:
                    # Use ent_kanda for testing but will reactivate immediately
                    test_entity = next((e for e in entities if e.get("id") == "ent_kanda"), None)
                
                if test_entity:
                    entity_id = test_entity.get("id")
                    
                    # Test deactivation impact check
                    try:
                        impact_response = self.admin_session.get(
                            f"{BASE_URL}/api/entities/{entity_id}/deactivation-impact",
                            timeout=30
                        )
                        if impact_response.status_code == 200:
                            self.log("PASS", f"GET /api/entities/{{id}}/deactivation-impact → 200")
                        else:
                            self.log("FAIL", f"GET /api/entities/{{id}}/deactivation-impact → {impact_response.status_code}")
                    except Exception as e:
                        self.log("FAIL", f"Error testing deactivation impact: {str(e)}")
                    
                    # Test readiness endpoint
                    try:
                        readiness_response = self.admin_session.get(
                            f"{BASE_URL}/api/entities/{entity_id}/readiness",
                            timeout=30
                        )
                        if readiness_response.status_code == 200:
                            self.log("PASS", f"GET /api/entities/{{id}}/readiness → 200")
                        else:
                            self.log("FAIL", f"GET /api/entities/{{id}}/readiness → {readiness_response.status_code}")
                    except Exception as e:
                        self.log("FAIL", f"Error testing readiness: {str(e)}")
                    
                    # Test audit endpoint
                    try:
                        audit_response = self.admin_session.get(
                            f"{BASE_URL}/api/entities/{entity_id}/audit",
                            timeout=30
                        )
                        if audit_response.status_code == 200:
                            self.log("PASS", f"GET /api/entities/{{id}}/audit → 200")
                        else:
                            self.log("FAIL", f"GET /api/entities/{{id}}/audit → {audit_response.status_code}")
                    except Exception as e:
                        self.log("FAIL", f"Error testing entity audit: {str(e)}")
                else:
                    self.log("FAIL", "No suitable entity found for lifecycle testing")
            else:
                self.log("FAIL", f"GET /api/entities failed: {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error in entity lifecycle test: {str(e)}")
    
    def test_doc_prefix_locking(self):
        """Test that doc_prefix cannot be changed for entities with documents"""
        print("\n📋 TEST 9: Document Prefix Locking")
        
        try:
            # Try to change doc_prefix for ent_ksc (which has documents)
            response = self.admin_session.patch(
                f"{BASE_URL}/api/entities/ent_ksc",
                json={"data": {"doc_prefix": "XXX"}},
                timeout=30
            )
            
            if response.status_code in (400, 409):
                detail = response.json().get("detail", "")
                if "dokumen" in detail.lower() or "prefix" in detail.lower():
                    self.log("PASS", "PATCH /api/entities/ent_ksc with new doc_prefix → rejected with proper message")
                else:
                    self.log("FAIL", f"PATCH rejected but message unclear: {detail}")
            elif response.status_code == 200:
                self.log("FAIL", "PATCH /api/entities/ent_ksc with new doc_prefix → 200 (should be rejected!)")
            else:
                self.log("FAIL", f"PATCH /api/entities/ent_ksc with new doc_prefix → {response.status_code}")
        except Exception as e:
            self.log("FAIL", f"Error testing doc_prefix locking: {str(e)}")
    
    def run_all_tests(self):
        """Run all backend tests"""
        print("=" * 80)
        print("BACKEND TEST - FASE E-3 VERIFICATION")
        print("=" * 80)
        
        # Login
        print("\n🔐 Logging in...")
        admin_result = self.login("admin@kainnusantara.id")
        if not admin_result:
            print("❌ Failed to login as admin. Cannot proceed.")
            return 1
        self.admin_session, self.admin_token = admin_result
        print("  ✅ Logged in as admin@kainnusantara.id")
        
        sales3_result = self.login("sales3@kainnusantara.id")
        if not sales3_result:
            print("❌ Failed to login as sales3. Cannot proceed.")
            return 1
        self.sales3_session, self.sales3_token = sales3_result
        print("  ✅ Logged in as sales3@kainnusantara.id")
        
        # Run tests
        self.test_write_guard_blocks_create_in_all_mode()
        self.test_write_guard_allows_after_selecting_entity()
        self.test_write_guard_allows_get_operations()
        self.test_write_guard_allows_shared_masters()
        self.test_write_guard_allows_updates_to_existing()
        self.test_entity_isolation_sales3()
        self.test_new_endpoints_e3()
        self.test_entity_lifecycle()
        self.test_doc_prefix_locking()
        
        # Summary
        print("\n" + "=" * 80)
        print(f"RESULTS: {self.tests_passed} PASSED / {self.tests_failed} FAILED / {self.tests_run} TOTAL")
        print("=" * 80)
        
        return 0 if self.tests_failed == 0 else 1

if __name__ == "__main__":
    tester = E3BackendTester()
    sys.exit(tester.run_all_tests())
