"""
FASE 3 Backend API Testing — Description & Image per-variant
Tests POST, PATCH, GET /api/products for description field and variant images.
"""
import requests
import sys
import os

# Get backend URL from frontend .env
BACKEND_URL = "https://po-pdf-sender.preview.emergentagent.com"
API = f"{BACKEND_URL}/api"

class FASE3BackendTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_product_id = None

    def log(self, msg, status="info"):
        symbols = {"pass": "✅", "fail": "❌", "info": "🔍"}
        print(f"{symbols.get(status, '•')} {msg}")

    def run_test(self, name, method, endpoint, expected_status, data=None, json_data=None):
        """Run a single API test"""
        url = f"{API}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        self.log(f"Testing {name}...", "info")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=json_data or data, headers=headers, timeout=10)
            elif method == 'PATCH':
                response = requests.patch(url, json=json_data or data, headers=headers, timeout=10)
            else:
                self.log(f"Unsupported method {method}", "fail")
                return False, {}

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"PASS — Status: {response.status_code}", "pass")
            else:
                self.log(f"FAIL — Expected {expected_status}, got {response.status_code}", "fail")
                self.log(f"Response: {response.text[:200]}", "fail")

            try:
                return success, response.json() if response.text else {}
            except:
                return success, {}

        except Exception as e:
            self.log(f"FAIL — Error: {str(e)}", "fail")
            return False, {}

    def test_login(self):
        """Test login and get token"""
        self.log("=== FASE 3 Backend Testing: Login ===", "info")
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            json_data={"email": "admin@kainnusantara.id", "password": "demo12345"}
        )
        if success and 'token' in response:
            self.token = response['token']
            self.log(f"Token obtained: {self.token[:20]}...", "pass")
            return True
        self.log("Login failed — cannot proceed", "fail")
        return False

    def test_post_product_with_description(self):
        """Test POST /api/products with description field"""
        self.log("\n=== Test 1: POST /api/products with description ===", "info")
        
        product_data = {
            "sku": f"TEST-F3-{os.urandom(4).hex()}",
            "name": "Test Product FASE 3",
            "category": "Batik",
            "variant": "Test",
            "color": "Test-Color",
            "motif": "Test-Motif",
            "grade": "A",
            "supplier": "Test Supplier",
            "base_unit": "meter",
            "price": 100000,
            "harga_pokok": 80000,
            "gramasi": 120,
            "lebar": 1.15,
            "image": "https://images.unsplash.com/photo-1761516659766-c092d4b1209d?q=85",
            "description": "Test description for FASE 3 — this should be persisted and returned in GET.",
            "status": "active"
        }
        
        success, response = self.run_test(
            "POST /api/products with description",
            "POST",
            "products",
            200,
            json_data=product_data
        )
        
        if success and response.get('id'):
            self.test_product_id = response['id']
            # Verify description is in response
            if response.get('description') == product_data['description']:
                self.log(f"Description persisted correctly: '{response.get('description')[:50]}...'", "pass")
                return True
            else:
                self.log(f"Description mismatch! Expected: '{product_data['description'][:50]}...', Got: '{response.get('description', 'NONE')}'", "fail")
                return False
        return False

    def test_patch_product_description_and_image(self):
        """Test PATCH /api/products/{id} with description and image"""
        self.log("\n=== Test 2: PATCH /api/products/{id} with description & image ===", "info")
        
        if not self.test_product_id:
            self.log("No test product ID — skipping PATCH test", "fail")
            return False
        
        patch_data = {
            "data": {
                "description": "Updated description for FASE 3 — testing round-trip persistence.",
                "image": "https://images.unsplash.com/photo-1761515315375-1315503bb3ce?q=85"
            }
        }
        
        success, response = self.run_test(
            "PATCH /api/products with description & image",
            "PATCH",
            f"products/{self.test_product_id}",
            200,
            json_data=patch_data
        )
        
        if success:
            # Verify both fields updated
            desc_ok = response.get('description') == patch_data['data']['description']
            img_ok = response.get('image') == patch_data['data']['image']
            
            if desc_ok and img_ok:
                self.log(f"Description & image updated correctly", "pass")
                return True
            else:
                if not desc_ok:
                    self.log(f"Description not updated! Got: '{response.get('description', 'NONE')}'", "fail")
                if not img_ok:
                    self.log(f"Image not updated! Got: '{response.get('image', 'NONE')}'", "fail")
                return False
        return False

    def test_get_products_with_description(self):
        """Test GET /api/products returns description"""
        self.log("\n=== Test 3: GET /api/products returns description ===", "info")
        
        success, response = self.run_test(
            "GET /api/products",
            "GET",
            "products",
            200
        )
        
        if success and isinstance(response, list):
            self.log(f"Retrieved {len(response)} products", "pass")
            
            # Find our test product
            test_prod = next((p for p in response if p.get('id') == self.test_product_id), None)
            if test_prod:
                if test_prod.get('description'):
                    self.log(f"Test product has description: '{test_prod['description'][:50]}...'", "pass")
                else:
                    self.log("Test product missing description field!", "fail")
                    return False
            
            # Check batik template variants have distinct images (seed data)
            batik_variants = [p for p in response if p.get('template_id') == 'tpl_batik_mega']
            if len(batik_variants) >= 3:
                images = [p.get('image', '') for p in batik_variants]
                unique_images = set(images)
                if len(unique_images) == len(batik_variants):
                    self.log(f"Batik template has {len(batik_variants)} variants with {len(unique_images)} DISTINCT images ✓", "pass")
                    for v in batik_variants:
                        self.log(f"  • {v.get('sku')}: {v.get('image', 'NO IMAGE')[:60]}...", "info")
                    return True
                else:
                    self.log(f"Batik variants do NOT have distinct images! {len(unique_images)} unique out of {len(batik_variants)}", "fail")
                    return False
            else:
                self.log(f"Expected 3+ batik variants, found {len(batik_variants)}", "fail")
                return False
        
        return False

    def run_all_tests(self):
        """Run all FASE 3 backend tests"""
        self.log("\n" + "="*70, "info")
        self.log("FASE 3 Backend API Testing — Description & Image per-variant", "info")
        self.log("="*70 + "\n", "info")
        
        if not self.test_login():
            return 1
        
        # Run tests in sequence
        self.test_post_product_with_description()
        self.test_patch_product_description_and_image()
        self.test_get_products_with_description()
        
        # Print summary
        self.log("\n" + "="*70, "info")
        self.log(f"SUMMARY: {self.tests_passed}/{self.tests_run} tests passed", 
                 "pass" if self.tests_passed == self.tests_run else "fail")
        self.log("="*70 + "\n", "info")
        
        return 0 if self.tests_passed == self.tests_run else 1


def main():
    tester = FASE3BackendTester()
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
