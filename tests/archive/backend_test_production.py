#!/usr/bin/env python3
"""
R6.4 Production Module Backend Test
Testing: BOM CRUD, Work Order lifecycle, RBAC, validations, idempotency
"""
import requests
import sys
from datetime import datetime

# Use public endpoint from frontend/.env
BASE_URL = "https://kn-inventory-prod.preview.emergentagent.com/api"

# Test credentials
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
MANAGER = {"email": "manager@kainnusantara.id", "password": "demo12345"}
SALES = {"email": "sales@kainnusantara.id", "password": "demo12345"}
WAREHOUSE = {"email": "warehouse@kainnusantara.id", "password": "demo12345"}

ENTITY_ID = "ent_ksc"

class ProductionTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.tokens = {}
        self.created_boms = []
        self.created_wos = []
        self.test_scenario = None

    def log_pass(self, test_name, details=""):
        self.tests_run += 1
        self.tests_passed += 1
        print(f"✅ PASS: {test_name}")
        if details:
            print(f"   {details}")

    def log_fail(self, test_name, details=""):
        self.tests_run += 1
        self.tests_failed += 1
        print(f"❌ FAIL: {test_name}")
        if details:
            print(f"   {details}")

    def login(self, cred, role_name):
        """Login and get token"""
        try:
            r = requests.post(f"{BASE_URL}/auth/login", json=cred, timeout=30)
            if r.status_code == 200:
                data = r.json()
                token = data.get("token")
                if token:
                    self.tokens[role_name] = token
                    print(f"  ✓ Logged in as {role_name}: {cred['email']}")
                    return True
                else:
                    print(f"  ✗ Login failed for {role_name}: no token in response")
                    return False
            else:
                print(f"  ✗ Login failed for {role_name}: {r.status_code} - {r.text[:200]}")
                return False
        except Exception as e:
            print(f"  ✗ Login error for {role_name}: {str(e)}")
            return False

    def get_headers(self, role="admin"):
        """Get auth headers for a role"""
        return {
            "Authorization": f"Bearer {self.tokens.get(role, '')}",
            "X-Entity-Id": ENTITY_ID,
            "Content-Type": "application/json"
        }

    def get_balances(self):
        """Get inventory balances"""
        try:
            r = requests.get(f"{BASE_URL}/inventory/balances", 
                           params={"entity_id": ENTITY_ID}, 
                           headers=self.get_headers("admin"), timeout=30)
            if r.status_code == 200:
                data = r.json()
                return data if isinstance(data, list) else data.get("items", [])
            return []
        except Exception:
            return []

    def get_available_qty(self, product_id, warehouse_id):
        """Get available quantity for a product in a warehouse"""
        balances = self.get_balances()
        total = 0.0
        for b in balances:
            if (b.get("product_id") == product_id and 
                b.get("warehouse_id") == warehouse_id and 
                b.get("owner_entity_id") == ENTITY_ID):
                total += float(b.get("available_qty", 0))
        return round(total, 2)

    def setup_test_scenario(self):
        """Find warehouse with 2+ materials with stock and 1 output product"""
        print("\n--- Setting up test scenario ---")
        balances = [b for b in self.get_balances() if float(b.get("available_qty", 0)) >= 40]
        
        by_warehouse = {}
        for b in balances:
            wid = b["warehouse_id"]
            by_warehouse.setdefault(wid, []).append(b)
        
        for wid, items in by_warehouse.items():
            products = list({i["product_id"]: i for i in items}.values())
            if len(products) >= 2:
                mat1 = products[0]["product_id"]
                mat2 = products[1]["product_id"]
                
                # Get all products to find output product
                try:
                    r = requests.get(f"{BASE_URL}/products", 
                                   headers=self.get_headers("admin"), timeout=30)
                    if r.status_code == 200:
                        all_products = r.json()
                        all_pids = [p["id"] for p in all_products]
                        output_pid = next((p for p in all_pids if p not in [mat1, mat2]), None)
                        
                        if output_pid:
                            self.test_scenario = {
                                "warehouse_id": wid,
                                "material1_id": mat1,
                                "material2_id": mat2,
                                "output_product_id": output_pid
                            }
                            print(f"  ✓ Scenario: warehouse={wid}, mat1={mat1}, mat2={mat2}, output={output_pid}")
                            return True
                except Exception:
                    pass
        
        print("  ✗ Could not find suitable test scenario")
        return False

    def test_auth(self):
        """Test authentication for all roles"""
        print("\n=== AUTH TESTS ===")
        success = True
        success &= self.login(ADMIN, "admin")
        success &= self.login(MANAGER, "manager")
        success &= self.login(SALES, "sales")
        success &= self.login(WAREHOUSE, "warehouse")
        
        if success:
            self.log_pass("AUTH - All roles login", "admin, manager, sales, warehouse")
        else:
            self.log_fail("AUTH - All roles login", "Some roles failed to login")
        
        return success

    def test_bom_validations(self):
        """Test BOM validation rules"""
        print("\n=== BOM VALIDATION TESTS ===")
        s = self.test_scenario
        h = self.get_headers("admin")
        
        # A1: Empty name
        r = requests.post(f"{BASE_URL}/production/boms", 
                         json={"name": "", "output_product_id": s["output_product_id"],
                               "components": [{"material_product_id": s["material1_id"], "qty_per_unit": 1}]},
                         headers=h, timeout=30)
        if r.status_code in [400, 422]:
            self.log_pass("BOM Validation - Empty name rejected")
        else:
            self.log_fail("BOM Validation - Empty name rejected", f"Got {r.status_code}")
        
        # A2: Unknown output product
        r = requests.post(f"{BASE_URL}/production/boms",
                         json={"name": "Test", "output_product_id": "prod_nonexistent",
                               "components": [{"material_product_id": s["material1_id"], "qty_per_unit": 1}]},
                         headers=h, timeout=30)
        if r.status_code == 400:
            self.log_pass("BOM Validation - Unknown output product rejected (400)")
        else:
            self.log_fail("BOM Validation - Unknown output product rejected", f"Got {r.status_code}")
        
        # A3: Empty components
        r = requests.post(f"{BASE_URL}/production/boms",
                         json={"name": "Test", "output_product_id": s["output_product_id"],
                               "components": []},
                         headers=h, timeout=30)
        if r.status_code in [400, 422]:
            self.log_pass("BOM Validation - Empty components rejected")
        else:
            self.log_fail("BOM Validation - Empty components rejected", f"Got {r.status_code}")
        
        # A4: qty_per_unit <= 0
        r = requests.post(f"{BASE_URL}/production/boms",
                         json={"name": "Test", "output_product_id": s["output_product_id"],
                               "components": [{"material_product_id": s["material1_id"], "qty_per_unit": 0}]},
                         headers=h, timeout=30)
        if r.status_code in [400, 422]:
            self.log_pass("BOM Validation - qty_per_unit <= 0 rejected")
        else:
            self.log_fail("BOM Validation - qty_per_unit <= 0 rejected", f"Got {r.status_code}")
        
        # A5: Component == output
        r = requests.post(f"{BASE_URL}/production/boms",
                         json={"name": "Test", "output_product_id": s["output_product_id"],
                               "components": [{"material_product_id": s["output_product_id"], "qty_per_unit": 1}]},
                         headers=h, timeout=30)
        if r.status_code == 400:
            self.log_pass("BOM Validation - Component == output rejected (400)")
        else:
            self.log_fail("BOM Validation - Component == output rejected", f"Got {r.status_code}")
        
        # A6: Duplicate component
        r = requests.post(f"{BASE_URL}/production/boms",
                         json={"name": "Test", "output_product_id": s["output_product_id"],
                               "components": [
                                   {"material_product_id": s["material1_id"], "qty_per_unit": 1},
                                   {"material_product_id": s["material1_id"], "qty_per_unit": 2}
                               ]},
                         headers=h, timeout=30)
        if r.status_code == 400:
            self.log_pass("BOM Validation - Duplicate component rejected (400)")
        else:
            self.log_fail("BOM Validation - Duplicate component rejected", f"Got {r.status_code}")

    def test_bom_crud(self):
        """Test BOM CRUD operations"""
        print("\n=== BOM CRUD TESTS ===")
        s = self.test_scenario
        h = self.get_headers("admin")
        
        # Create valid BOM
        r = requests.post(f"{BASE_URL}/production/boms",
                         json={
                             "name": "Test BOM R6.4",
                             "output_product_id": s["output_product_id"],
                             "overhead_per_unit": 1500,
                             "components": [
                                 {"material_product_id": s["material1_id"], "qty_per_unit": 2},
                                 {"material_product_id": s["material2_id"], "qty_per_unit": 1}
                             ]
                         }, headers=h, timeout=30)
        
        if r.status_code == 200:
            bom = r.json()
            self.created_boms.append(bom["id"])
            if (len(bom.get("components", [])) == 2 and 
                bom.get("status") == "active" and
                bom.get("overhead_per_unit") == 1500):
                self.log_pass("BOM CRUD - Create valid BOM", f"ID: {bom['id']}")
            else:
                self.log_fail("BOM CRUD - Create valid BOM", "Invalid BOM structure")
        else:
            self.log_fail("BOM CRUD - Create valid BOM", f"Status: {r.status_code}, {r.text[:200]}")
            return None
        
        # PATCH BOM
        r = requests.patch(f"{BASE_URL}/production/boms/{bom['id']}",
                          json={"overhead_per_unit": 2000},
                          headers=h, timeout=30)
        if r.status_code == 200 and r.json().get("overhead_per_unit") == 2000:
            self.log_pass("BOM CRUD - PATCH overhead", "Updated to 2000")
        else:
            self.log_fail("BOM CRUD - PATCH overhead", f"Status: {r.status_code}")
        
        # GET BOM detail
        r = requests.get(f"{BASE_URL}/production/boms/{bom['id']}", headers=h, timeout=30)
        if r.status_code == 200 and r.json().get("id") == bom["id"]:
            self.log_pass("BOM CRUD - GET detail", f"Retrieved {bom['id']}")
        else:
            self.log_fail("BOM CRUD - GET detail", f"Status: {r.status_code}")
        
        # LIST BOMs
        r = requests.get(f"{BASE_URL}/production/boms", 
                        params={"entity_id": ENTITY_ID},
                        headers=h, timeout=30)
        if r.status_code == 200:
            boms = r.json()
            if any(b["id"] == bom["id"] for b in boms):
                self.log_pass("BOM CRUD - LIST BOMs", f"Found {len(boms)} BOMs")
            else:
                self.log_fail("BOM CRUD - LIST BOMs", "Created BOM not in list")
        else:
            self.log_fail("BOM CRUD - LIST BOMs", f"Status: {r.status_code}")
        
        return bom

    def test_work_order_lifecycle(self, bom):
        """Test Work Order lifecycle: draft -> released -> completed"""
        print("\n=== WORK ORDER LIFECYCLE TESTS ===")
        s = self.test_scenario
        h = self.get_headers("admin")
        
        # Get pre-completion stock levels
        pre_output = self.get_available_qty(s["output_product_id"], s["warehouse_id"])
        pre_mat1 = self.get_available_qty(s["material1_id"], s["warehouse_id"])
        pre_mat2 = self.get_available_qty(s["material2_id"], s["warehouse_id"])
        
        planned_qty = 3.0
        
        # Create WO (draft)
        r = requests.post(f"{BASE_URL}/production/work-orders",
                         json={
                             "bom_id": bom["id"],
                             "planned_qty": planned_qty,
                             "warehouse_id": s["warehouse_id"],
                             "entity_id": ENTITY_ID
                         }, headers=h, timeout=30)
        
        if r.status_code == 200:
            wo = r.json()
            self.created_wos.append(wo["id"])
            if wo.get("status") == "draft" and wo.get("wo_number", "").startswith("WO-"):
                self.log_pass("WO Lifecycle - Create draft", f"WO: {wo['wo_number']}")
            else:
                self.log_fail("WO Lifecycle - Create draft", "Invalid WO structure")
                return None
        else:
            self.log_fail("WO Lifecycle - Create draft", f"Status: {r.status_code}, {r.text[:200]}")
            return None
        
        # Check material plan
        plan = {p["material_product_id"]: p for p in wo.get("material_plan", [])}
        mat1_required = plan.get(s["material1_id"], {}).get("required_qty", 0)
        mat2_required = plan.get(s["material2_id"], {}).get("required_qty", 0)
        
        if abs(mat1_required - 2 * planned_qty) < 0.01:
            self.log_pass("WO Lifecycle - Material plan mat1", f"Required: {mat1_required} (2×{planned_qty})")
        else:
            self.log_fail("WO Lifecycle - Material plan mat1", f"Expected {2*planned_qty}, got {mat1_required}")
        
        if abs(mat2_required - 1 * planned_qty) < 0.01:
            self.log_pass("WO Lifecycle - Material plan mat2", f"Required: {mat2_required} (1×{planned_qty})")
        else:
            self.log_fail("WO Lifecycle - Material plan mat2", f"Expected {planned_qty}, got {mat2_required}")
        
        # Release WO
        r = requests.post(f"{BASE_URL}/production/work-orders/{wo['id']}/release",
                         headers=h, timeout=30)
        if r.status_code == 200 and r.json().get("status") == "released":
            self.log_pass("WO Lifecycle - Release", "Status: released")
        else:
            self.log_fail("WO Lifecycle - Release", f"Status: {r.status_code}")
        
        # Complete WO
        r = requests.post(f"{BASE_URL}/production/work-orders/{wo['id']}/complete",
                         headers=h, timeout=30)
        
        if r.status_code == 200:
            completed = r.json()
            if completed.get("status") == "completed":
                self.log_pass("WO Lifecycle - Complete", "Status: completed")
            else:
                self.log_fail("WO Lifecycle - Complete", f"Status: {completed.get('status')}")
            
            # Check stock changes
            post_output = self.get_available_qty(s["output_product_id"], s["warehouse_id"])
            post_mat1 = self.get_available_qty(s["material1_id"], s["warehouse_id"])
            post_mat2 = self.get_available_qty(s["material2_id"], s["warehouse_id"])
            
            if abs(post_output - (pre_output + planned_qty)) < 0.01:
                self.log_pass("WO Lifecycle - Output stock increased", 
                            f"{pre_output} → {post_output} (+{planned_qty})")
            else:
                self.log_fail("WO Lifecycle - Output stock increased",
                            f"Expected {pre_output + planned_qty}, got {post_output}")
            
            if abs(post_mat1 - (pre_mat1 - 2 * planned_qty)) < 0.01:
                self.log_pass("WO Lifecycle - Mat1 stock decreased",
                            f"{pre_mat1} → {post_mat1} (-{2*planned_qty})")
            else:
                self.log_fail("WO Lifecycle - Mat1 stock decreased",
                            f"Expected {pre_mat1 - 2*planned_qty}, got {post_mat1}")
            
            if abs(post_mat2 - (pre_mat2 - 1 * planned_qty)) < 0.01:
                self.log_pass("WO Lifecycle - Mat2 stock decreased",
                            f"{pre_mat2} → {post_mat2} (-{planned_qty})")
            else:
                self.log_fail("WO Lifecycle - Mat2 stock decreased",
                            f"Expected {pre_mat2 - planned_qty}, got {post_mat2}")
            
            # Check costing
            if completed.get("material_cost", 0) > 0:
                self.log_pass("WO Lifecycle - Material cost > 0", 
                            f"Cost: {completed['material_cost']}")
            else:
                self.log_fail("WO Lifecycle - Material cost > 0", "Material cost is 0")
            
            expected_overhead = round(2000 * planned_qty, 2)  # overhead was updated to 2000
            if abs(completed.get("overhead_cost", 0) - expected_overhead) < 1:
                self.log_pass("WO Lifecycle - Overhead cost", 
                            f"Cost: {completed['overhead_cost']} (≈{expected_overhead})")
            else:
                self.log_fail("WO Lifecycle - Overhead cost",
                            f"Expected ≈{expected_overhead}, got {completed.get('overhead_cost')}")
            
            if completed.get("je_id"):
                self.log_pass("WO Lifecycle - GL journal created", f"JE: {completed['je_id']}")
            else:
                self.log_fail("WO Lifecycle - GL journal created", "No je_id")
            
            if len(completed.get("produced_roll_ids", [])) >= 1:
                self.log_pass("WO Lifecycle - Produced rolls", 
                            f"Rolls: {len(completed['produced_roll_ids'])}")
            else:
                self.log_fail("WO Lifecycle - Produced rolls", "No rolls produced")
            
            return wo, post_output, post_mat1, post_mat2
        else:
            self.log_fail("WO Lifecycle - Complete", f"Status: {r.status_code}, {r.text[:200]}")
            return None

    def test_idempotency(self, wo, post_output, post_mat1, post_mat2):
        """Test idempotency of complete operation"""
        print("\n=== IDEMPOTENCY TESTS ===")
        s = self.test_scenario
        h = self.get_headers("admin")
        
        # Complete again
        r = requests.post(f"{BASE_URL}/production/work-orders/{wo['id']}/complete",
                         headers=h, timeout=30)
        
        if r.status_code == 200:
            self.log_pass("Idempotency - Complete again returns 200")
            
            # Check stock hasn't changed
            current_output = self.get_available_qty(s["output_product_id"], s["warehouse_id"])
            current_mat1 = self.get_available_qty(s["material1_id"], s["warehouse_id"])
            current_mat2 = self.get_available_qty(s["material2_id"], s["warehouse_id"])
            
            if abs(current_output - post_output) < 0.01:
                self.log_pass("Idempotency - Output stock unchanged", f"Still {current_output}")
            else:
                self.log_fail("Idempotency - Output stock unchanged",
                            f"Changed from {post_output} to {current_output}")
            
            if abs(current_mat1 - post_mat1) < 0.01:
                self.log_pass("Idempotency - Mat1 stock unchanged", f"Still {current_mat1}")
            else:
                self.log_fail("Idempotency - Mat1 stock unchanged",
                            f"Changed from {post_mat1} to {current_mat1}")
        else:
            self.log_fail("Idempotency - Complete again", f"Status: {r.status_code}")

    def test_rbac(self, bom):
        """Test RBAC for different roles"""
        print("\n=== RBAC TESTS ===")
        s = self.test_scenario
        
        # Sales - should get 403 on everything
        h_sales = self.get_headers("sales")
        
        r = requests.get(f"{BASE_URL}/production/boms", headers=h_sales, timeout=30)
        if r.status_code == 403:
            self.log_pass("RBAC - Sales GET BOMs denied (403)")
        else:
            self.log_fail("RBAC - Sales GET BOMs denied", f"Got {r.status_code}")
        
        r = requests.post(f"{BASE_URL}/production/boms",
                         json={"name": "Test", "output_product_id": s["output_product_id"],
                               "components": [{"material_product_id": s["material1_id"], "qty_per_unit": 1}]},
                         headers=h_sales, timeout=30)
        if r.status_code == 403:
            self.log_pass("RBAC - Sales POST BOM denied (403)")
        else:
            self.log_fail("RBAC - Sales POST BOM denied", f"Got {r.status_code}")
        
        r = requests.post(f"{BASE_URL}/production/work-orders",
                         json={"bom_id": bom["id"], "planned_qty": 1, "warehouse_id": s["warehouse_id"]},
                         headers=h_sales, timeout=30)
        if r.status_code == 403:
            self.log_pass("RBAC - Sales POST WO denied (403)")
        else:
            self.log_fail("RBAC - Sales POST WO denied", f"Got {r.status_code}")
        
        # Warehouse - can view, create WO, but not manage BOM or cancel
        h_wh = self.get_headers("warehouse")
        
        r = requests.get(f"{BASE_URL}/production/boms", headers=h_wh, timeout=30)
        if r.status_code == 200:
            self.log_pass("RBAC - Warehouse GET BOMs allowed (200)")
        else:
            self.log_fail("RBAC - Warehouse GET BOMs allowed", f"Got {r.status_code}")
        
        r = requests.post(f"{BASE_URL}/production/boms",
                         json={"name": "Test", "output_product_id": s["output_product_id"],
                               "components": [{"material_product_id": s["material1_id"], "qty_per_unit": 1}]},
                         headers=h_wh, timeout=30)
        if r.status_code == 403:
            self.log_pass("RBAC - Warehouse POST BOM denied (403, no manage_bom)")
        else:
            self.log_fail("RBAC - Warehouse POST BOM denied", f"Got {r.status_code}")
        
        r = requests.post(f"{BASE_URL}/production/work-orders",
                         json={"bom_id": bom["id"], "planned_qty": 1, 
                               "warehouse_id": s["warehouse_id"], "entity_id": ENTITY_ID},
                         headers=h_wh, timeout=30)
        if r.status_code == 200:
            wo_wh = r.json()
            self.created_wos.append(wo_wh["id"])
            self.log_pass("RBAC - Warehouse POST WO allowed (200)")
            
            # Try to cancel (should be denied)
            r = requests.post(f"{BASE_URL}/production/work-orders/{wo_wh['id']}/cancel",
                             json={}, headers=h_wh, timeout=30)
            if r.status_code == 403:
                self.log_pass("RBAC - Warehouse cancel WO denied (403)")
            else:
                self.log_fail("RBAC - Warehouse cancel WO denied", f"Got {r.status_code}")
        else:
            self.log_fail("RBAC - Warehouse POST WO allowed", f"Got {r.status_code}, {r.text[:200]}")
        
        # No auth - should get 401/403
        r = requests.get(f"{BASE_URL}/production/boms", timeout=30)
        if r.status_code in [401, 403]:
            self.log_pass("RBAC - No auth denied (401/403)")
        else:
            self.log_fail("RBAC - No auth denied", f"Got {r.status_code}")

    def test_insufficient_stock(self):
        """Test that completing WO with insufficient stock is rejected"""
        print("\n=== INSUFFICIENT STOCK TEST ===")
        s = self.test_scenario
        h = self.get_headers("admin")
        
        # Create BOM with huge material requirement
        r = requests.post(f"{BASE_URL}/production/boms",
                         json={
                             "name": "Test Insufficient Stock",
                             "output_product_id": s["output_product_id"],
                             "components": [
                                 {"material_product_id": s["material2_id"], "qty_per_unit": 100000}
                             ]
                         }, headers=h, timeout=30)
        
        if r.status_code == 200:
            bom_big = r.json()
            self.created_boms.append(bom_big["id"])
            
            # Create WO
            r = requests.post(f"{BASE_URL}/production/work-orders",
                             json={"bom_id": bom_big["id"], "planned_qty": 1,
                                   "warehouse_id": s["warehouse_id"], "entity_id": ENTITY_ID},
                             headers=h, timeout=30)
            
            if r.status_code == 200:
                wo_big = r.json()
                self.created_wos.append(wo_big["id"])
                
                # Try to complete (should fail)
                r = requests.post(f"{BASE_URL}/production/work-orders/{wo_big['id']}/complete",
                                 headers=h, timeout=30)
                
                if r.status_code == 400:
                    self.log_pass("Insufficient Stock - Complete rejected (400)")
                else:
                    self.log_fail("Insufficient Stock - Complete rejected",
                                f"Expected 400, got {r.status_code}")
            else:
                self.log_fail("Insufficient Stock - Create WO", f"Status: {r.status_code}")
        else:
            self.log_fail("Insufficient Stock - Create BOM", f"Status: {r.status_code}")

    def cleanup(self):
        """Cleanup created test data"""
        print("\n--- Cleanup ---")
        h = self.get_headers("admin")
        
        # Cancel open WOs
        cancelled = 0
        for wo_id in self.created_wos:
            try:
                r = requests.post(f"{BASE_URL}/production/work-orders/{wo_id}/cancel",
                                 json={"reason": "test cleanup"}, headers=h, timeout=30)
                if r.status_code == 200:
                    cancelled += 1
            except Exception:
                pass
        
        # Delete BOMs
        deleted = 0
        for bom_id in self.created_boms:
            try:
                r = requests.delete(f"{BASE_URL}/production/boms/{bom_id}", headers=h, timeout=30)
                if r.status_code == 200:
                    deleted += 1
            except Exception:
                pass
        
        print(f"  ✓ Cancelled {cancelled} WOs, deleted {deleted} BOMs")

    def run_all_tests(self):
        """Run all production tests"""
        print("=" * 80)
        print("R6.4 PRODUCTION MODULE BACKEND TEST")
        print("Testing: BOM CRUD, Work Order lifecycle, RBAC, validations")
        print("=" * 80)
        
        # Auth
        if not self.test_auth():
            print("\n❌ Authentication failed. Cannot proceed.")
            return False
        
        # Setup scenario
        if not self.setup_test_scenario():
            print("\n❌ Could not setup test scenario. Cannot proceed.")
            return False
        
        # Run tests
        self.test_bom_validations()
        bom = self.test_bom_crud()
        
        if bom:
            result = self.test_work_order_lifecycle(bom)
            if result:
                wo, post_output, post_mat1, post_mat2 = result
                self.test_idempotency(wo, post_output, post_mat1, post_mat2)
            
            self.test_rbac(bom)
        
        self.test_insufficient_stock()
        
        # Cleanup
        self.cleanup()
        
        # Summary
        print("\n" + "=" * 80)
        print("BACKEND TEST SUMMARY")
        print("=" * 80)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_failed}")
        if self.tests_run > 0:
            print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        print("=" * 80)
        
        return self.tests_failed == 0


def main():
    tester = ProductionTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
