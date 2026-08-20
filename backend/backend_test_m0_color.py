"""
M0 — Color Library & Product Stage Backend Test
Tests color CRUD, nearest color, permissions, and product stage fields.
"""
import requests
import sys
from typing import Optional

BASE_URL = "https://subcon-preview.preview.emergentagent.com"

class M0ColorTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.admin_token = None
        self.sales_token = None
        self.warehouse_token = None
        self.created_color_id = None

    def log(self, msg: str):
        print(f"  {msg}")

    def test(self, name: str, fn):
        """Run a test function"""
        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        try:
            fn()
            self.tests_passed += 1
            print(f"✅ PASSED")
            return True
        except AssertionError as e:
            print(f"❌ FAILED: {e}")
            return False
        except Exception as e:
            print(f"❌ ERROR: {e}")
            return False

    def login(self, email: str, password: str) -> Optional[str]:
        """Login and return token"""
        try:
            res = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=10)
            if res.status_code == 200:
                token = res.json().get("token")
                self.log(f"✓ Logged in as {email}")
                return token
            else:
                self.log(f"✗ Login failed for {email}: {res.status_code}")
                return None
        except Exception as e:
            self.log(f"✗ Login error for {email}: {e}")
            return None

    def headers(self, token: Optional[str] = None):
        """Get headers with optional auth"""
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    # ─── AUTH TESTS ───────────────────────────────────────────────────────────

    def test_login_all_users(self):
        """Test login for admin, sales, warehouse"""
        self.admin_token = self.login("admin@kainnusantara.id", "demo12345")
        assert self.admin_token, "Admin login failed"
        
        self.sales_token = self.login("sales@kainnusantara.id", "demo12345")
        assert self.sales_token, "Sales login failed"
        
        self.warehouse_token = self.login("warehouse@kainnusantara.id", "demo12345")
        assert self.warehouse_token, "Warehouse login failed"

    # ─── COLOR LIBRARY CRUD TESTS ─────────────────────────────────────────────

    def test_get_color_library_admin(self):
        """GET /api/color-library (admin) returns array"""
        res = requests.get(f"{BASE_URL}/api/color-library", headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        assert isinstance(data, list), f"Expected array, got {type(data)}"
        self.log(f"✓ Got {len(data)} colors")
        assert len(data) >= 28, f"Expected at least 28 seeded colors, got {len(data)}"

    def test_get_color_library_query_params(self):
        """GET /api/color-library with query params (q, family, system, status)"""
        # Test search query
        res = requests.get(f"{BASE_URL}/api/color-library", 
                          params={"q": "biru", "status": "active"}, 
                          headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        self.log(f"✓ Search 'biru' returned {len(data)} colors")
        
        # Test family filter
        res = requests.get(f"{BASE_URL}/api/color-library", 
                          params={"family": "Biru", "status": "active"}, 
                          headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        self.log(f"✓ Family 'Biru' returned {len(data)} colors")
        
        # Test system filter
        res = requests.get(f"{BASE_URL}/api/color-library", 
                          params={"system": "KN", "status": "active"}, 
                          headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        self.log(f"✓ System 'KN' returned {len(data)} colors")

    def test_create_color_admin(self):
        """POST /api/color-library (admin) creates color"""
        payload = {
            "code": "TEST-M0-001",
            "name": "Test Color M0",
            "hex": "#FF5733",
            "system": "KN",
            "family": "Merah"
        }
        res = requests.post(f"{BASE_URL}/api/color-library", 
                           json=payload, 
                           headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data.get("code") == "TEST-M0-001", f"Expected code TEST-M0-001, got {data.get('code')}"
        assert data.get("hex") == "#FF5733", f"Expected hex #FF5733, got {data.get('hex')}"
        self.created_color_id = data.get("id")
        self.log(f"✓ Created color {self.created_color_id}")

    def test_create_color_duplicate_code(self):
        """POST /api/color-library with duplicate code returns 400"""
        payload = {
            "code": "TEST-M0-001",  # Same as previous test
            "name": "Duplicate Test",
            "hex": "#123456",
            "system": "KN",
            "family": "Test"
        }
        res = requests.post(f"{BASE_URL}/api/color-library", 
                           json=payload, 
                           headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 400, f"Expected 400 for duplicate, got {res.status_code}"
        self.log(f"✓ Duplicate code rejected with 400")

    def test_create_color_invalid_hex(self):
        """POST /api/color-library with invalid hex returns 400"""
        payload = {
            "code": "TEST-INVALID-HEX",
            "name": "Invalid Hex Test",
            "hex": "GGGGGG",  # Invalid hex
            "system": "KN",
            "family": "Test"
        }
        res = requests.post(f"{BASE_URL}/api/color-library", 
                           json=payload, 
                           headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 400, f"Expected 400 for invalid hex, got {res.status_code}"
        self.log(f"✓ Invalid hex rejected with 400")

    def test_create_color_missing_fields(self):
        """POST /api/color-library with missing code/name returns 400"""
        payload = {
            "hex": "#123456",
            "system": "KN"
        }
        res = requests.post(f"{BASE_URL}/api/color-library", 
                           json=payload, 
                           headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 422 or res.status_code == 400, f"Expected 422/400 for missing fields, got {res.status_code}"
        self.log(f"✓ Missing fields rejected with {res.status_code}")

    def test_patch_color_admin(self):
        """PATCH /api/color-library/{id} updates color"""
        if not self.created_color_id:
            raise AssertionError("No color created to patch")
        
        payload = {
            "name": "Updated Test Color",
            "hex": "#00FF00",
            "family": "Hijau"
        }
        res = requests.patch(f"{BASE_URL}/api/color-library/{self.created_color_id}", 
                            json=payload, 
                            headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data.get("name") == "Updated Test Color", f"Expected updated name, got {data.get('name')}"
        assert data.get("hex") == "#00FF00", f"Expected updated hex, got {data.get('hex')}"
        self.log(f"✓ Updated color {self.created_color_id}")

    def test_delete_color_admin(self):
        """DELETE /api/color-library/{id} soft-deactivates color"""
        if not self.created_color_id:
            raise AssertionError("No color created to delete")
        
        res = requests.delete(f"{BASE_URL}/api/color-library/{self.created_color_id}", 
                             headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data.get("deleted") == True, f"Expected deleted=True, got {data}"
        self.log(f"✓ Soft-deleted color {self.created_color_id}")

    # ─── NEAREST COLOR TESTS ──────────────────────────────────────────────────

    def test_nearest_color_valid_hex(self):
        """GET /api/color-library/nearest?hex=10406F returns nearest colors"""
        res = requests.get(f"{BASE_URL}/api/color-library/nearest", 
                          params={"hex": "10406F", "limit": 3}, 
                          headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "query_hex" in data, f"Expected query_hex in response, got {data.keys()}"
        assert "nearest_id" in data, f"Expected nearest_id in response, got {data.keys()}"
        assert "results" in data, f"Expected results in response, got {data.keys()}"
        assert isinstance(data["results"], list), f"Expected results to be list, got {type(data['results'])}"
        assert len(data["results"]) <= 3, f"Expected max 3 results, got {len(data['results'])}"
        self.log(f"✓ Nearest color query returned {len(data['results'])} results")
        if data["results"]:
            self.log(f"  Nearest: {data['results'][0].get('code')} (distance: {data['results'][0].get('distance')})")

    def test_nearest_color_invalid_hex(self):
        """GET /api/color-library/nearest with invalid hex returns 400"""
        res = requests.get(f"{BASE_URL}/api/color-library/nearest", 
                          params={"hex": "ZZZZZZ"}, 
                          headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 400, f"Expected 400 for invalid hex, got {res.status_code}"
        self.log(f"✓ Invalid hex rejected with 400")

    # ─── PERMISSIONS TESTS ────────────────────────────────────────────────────

    def test_sales_can_get_colors(self):
        """Sales can GET color-library"""
        res = requests.get(f"{BASE_URL}/api/color-library", 
                          headers=self.headers(self.sales_token), timeout=10)
        assert res.status_code == 200, f"Expected 200 for sales GET, got {res.status_code}"
        self.log(f"✓ Sales can GET colors")

    def test_sales_can_create_colors(self):
        """Sales can POST color-library"""
        payload = {
            "code": "SALES-TEST-001",
            "name": "Sales Test Color",
            "hex": "#AABBCC",
            "system": "KN",
            "family": "Test"
        }
        res = requests.post(f"{BASE_URL}/api/color-library", 
                           json=payload, 
                           headers=self.headers(self.sales_token), timeout=10)
        assert res.status_code == 200, f"Expected 200 for sales POST, got {res.status_code}: {res.text}"
        self.log(f"✓ Sales can POST colors")
        # Clean up
        color_id = res.json().get("id")
        if color_id:
            requests.delete(f"{BASE_URL}/api/color-library/{color_id}", 
                          headers=self.headers(self.admin_token), timeout=10)

    def test_warehouse_can_get_colors(self):
        """Warehouse can GET color-library"""
        res = requests.get(f"{BASE_URL}/api/color-library", 
                          headers=self.headers(self.warehouse_token), timeout=10)
        assert res.status_code == 200, f"Expected 200 for warehouse GET, got {res.status_code}"
        self.log(f"✓ Warehouse can GET colors")

    def test_warehouse_cannot_create_colors(self):
        """Warehouse cannot POST color-library"""
        payload = {
            "code": "WH-TEST-001",
            "name": "Warehouse Test",
            "hex": "#123456",
            "system": "KN",
            "family": "Test"
        }
        res = requests.post(f"{BASE_URL}/api/color-library", 
                           json=payload, 
                           headers=self.headers(self.warehouse_token), timeout=10)
        assert res.status_code in [401, 403], f"Expected 401/403 for warehouse POST, got {res.status_code}"
        self.log(f"✓ Warehouse cannot POST colors (got {res.status_code})")

    def test_unauthenticated_cannot_access(self):
        """Unauthenticated requests return 401/403"""
        res = requests.get(f"{BASE_URL}/api/color-library", timeout=10)
        assert res.status_code in [401, 403], f"Expected 401/403 for unauthenticated, got {res.status_code}"
        self.log(f"✓ Unauthenticated access blocked (got {res.status_code})")

    # ─── PRODUCT STAGE & COLOR SNAPSHOT TESTS ─────────────────────────────────

    def test_products_have_stage_field(self):
        """GET /api/products returns products with stage field"""
        res = requests.get(f"{BASE_URL}/api/products", 
                          headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        assert isinstance(data, list), f"Expected array, got {type(data)}"
        
        # Find seeded 'Benang' product (SKU BNG-KTN-001)
        benang = next((p for p in data if p.get("sku") == "BNG-KTN-001"), None)
        if benang:
            assert benang.get("stage") == "yarn", f"Expected stage=yarn for Benang, got {benang.get('stage')}"
            self.log(f"✓ Benang product has stage=yarn")
        else:
            self.log(f"⚠ Benang product (BNG-KTN-001) not found in seed data")
        
        # Check other products have stage='finished'
        finished_products = [p for p in data if p.get("stage") == "finished"]
        self.log(f"✓ Found {len(finished_products)} products with stage=finished")

    def test_products_have_color_snapshot(self):
        """Products have color_code, color_name, color_hex fields"""
        res = requests.get(f"{BASE_URL}/api/products", 
                          headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        
        # Check for products with color snapshots
        with_color = [p for p in data if p.get("color_code") or p.get("color_hex")]
        self.log(f"✓ Found {len(with_color)} products with color snapshots")
        
        if with_color:
            sample = with_color[0]
            self.log(f"  Sample: {sample.get('sku')} - color_code={sample.get('color_code')}, color_hex={sample.get('color_hex')}")

    def test_product_create_with_stage_and_color(self):
        """POST /api/products accepts stage + color_code + color_name + color_hex"""
        payload = {
            "sku": "TEST-M0-PROD-001",
            "name": "Test Product M0",
            "category": "Kain",
            "stage": "grey",
            "color_code": "KN-BLU-01",
            "color_name": "Biru Indigo",
            "color_hex": "#10406F",
            "price": 50000,
            "base_unit": "meter"
        }
        res = requests.post(f"{BASE_URL}/api/products", 
                           json=payload, 
                           headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data.get("stage") == "grey", f"Expected stage=grey, got {data.get('stage')}"
        assert data.get("color_code") == "KN-BLU-01", f"Expected color_code, got {data.get('color_code')}"
        assert data.get("color_hex") == "#10406F", f"Expected color_hex, got {data.get('color_hex')}"
        self.log(f"✓ Created product with stage and color snapshot")
        
        # Clean up
        product_id = data.get("id")
        if product_id:
            requests.delete(f"{BASE_URL}/api/products/{product_id}", 
                          headers=self.headers(self.admin_token), timeout=10)

    def test_product_templates_have_stage(self):
        """GET /api/product-templates returns templates with stage field"""
        res = requests.get(f"{BASE_URL}/api/product-templates", 
                          headers=self.headers(self.admin_token), timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        assert isinstance(data, list), f"Expected array, got {type(data)}"
        
        if data:
            sample = data[0]
            # Check if stage field exists (may be empty string or value)
            assert "stage" in sample, f"Expected stage field in template, got keys: {sample.keys()}"
            self.log(f"✓ Product templates have stage field")
            self.log(f"  Sample: {sample.get('name')} - stage={sample.get('stage')}")
        else:
            self.log(f"⚠ No product templates found")

    # ─── SUMMARY ──────────────────────────────────────────────────────────────

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"M0 COLOR LIBRARY TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Tests Run:    {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        print(f"{'='*60}\n")
        return 0 if self.tests_passed == self.tests_run else 1


def main():
    tester = M0ColorTester()
    
    print("="*60)
    print("M0 — COLOR LIBRARY & PRODUCT STAGE BACKEND TEST")
    print("="*60)
    
    # Auth
    tester.test("Login all users (admin, sales, warehouse)", tester.test_login_all_users)
    
    # Color Library CRUD
    tester.test("GET /api/color-library (admin)", tester.test_get_color_library_admin)
    tester.test("GET /api/color-library with query params", tester.test_get_color_library_query_params)
    tester.test("POST /api/color-library (admin)", tester.test_create_color_admin)
    tester.test("POST /api/color-library duplicate code → 400", tester.test_create_color_duplicate_code)
    tester.test("POST /api/color-library invalid hex → 400", tester.test_create_color_invalid_hex)
    tester.test("POST /api/color-library missing fields → 400", tester.test_create_color_missing_fields)
    tester.test("PATCH /api/color-library/{id}", tester.test_patch_color_admin)
    tester.test("DELETE /api/color-library/{id} soft-deactivate", tester.test_delete_color_admin)
    
    # Nearest Color
    tester.test("GET /api/color-library/nearest valid hex", tester.test_nearest_color_valid_hex)
    tester.test("GET /api/color-library/nearest invalid hex → 400", tester.test_nearest_color_invalid_hex)
    
    # Permissions
    tester.test("Sales can GET color-library", tester.test_sales_can_get_colors)
    tester.test("Sales can POST color-library", tester.test_sales_can_create_colors)
    tester.test("Warehouse can GET color-library", tester.test_warehouse_can_get_colors)
    tester.test("Warehouse cannot POST color-library", tester.test_warehouse_cannot_create_colors)
    tester.test("Unauthenticated → 401/403", tester.test_unauthenticated_cannot_access)
    
    # Product Stage & Color Snapshot
    tester.test("Products have stage field", tester.test_products_have_stage_field)
    tester.test("Products have color snapshot fields", tester.test_products_have_color_snapshot)
    tester.test("POST /api/products with stage + color", tester.test_product_create_with_stage_and_color)
    tester.test("Product templates have stage field", tester.test_product_templates_have_stage)
    
    return tester.print_summary()


if __name__ == "__main__":
    sys.exit(main())
