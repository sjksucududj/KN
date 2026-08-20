"""
Quick backend API test for Price Approvals endpoints
Tests the new "Minta Harga Khusus" feature backend integration
"""
import requests
import sys

BASE_URL = "https://warehouse-fase-b.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@kainnusantara.id"
ADMIN_PASSWORD = "demo12345"
SALES_EMAIL = "sales@kainnusantara.id"
SALES_PASSWORD = "demo12345"

class PriceApprovalsAPITester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []

    def log(self, message, level="INFO"):
        prefix = {"INFO": "ℹ️", "SUCCESS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "•")
        print(f"{prefix} {message}")

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        url = f"{BASE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        self.log(f"Testing: {name}", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"PASSED - {name} (Status: {response.status_code})", "SUCCESS")
                return True, response.json() if response.content else {}
            else:
                self.tests_failed += 1
                self.failed_tests.append(name)
                self.log(f"FAILED - {name} (Expected {expected_status}, got {response.status_code})", "FAIL")
                try:
                    self.log(f"  Error: {response.json()}", "FAIL")
                except:
                    self.log(f"  Response: {response.text[:200]}", "FAIL")
                return False, {}

        except Exception as e:
            self.tests_failed += 1
            self.failed_tests.append(name)
            self.log(f"FAILED - {name} (Exception: {str(e)})", "FAIL")
            return False, {}

    def test_login(self, email, password):
        self.log(f"\n=== LOGIN as {email} ===", "INFO")
        success, data = self.run_test(
            f"Login as {email}",
            "POST",
            "/auth/login",
            200,
            data={"email": email, "password": password}
        )
        if success and data.get('token'):
            self.token = data['token']
            self.log(f"Token obtained: {self.token[:20]}...", "SUCCESS")
            return True
        return False

    def test_price_approvals_flow(self):
        self.log("\n=== PRICE APPROVALS BACKEND TESTS ===", "INFO")
        
        # Get customers and products first
        success, customers_data = self.run_test("Get Customers", "GET", "/customers", 200)
        if not success or not customers_data:
            self.log("Cannot proceed without customers", "FAIL")
            return
        
        # Find a customer that is NOT "Toko Kain Sejahtera" (to avoid existing special price)
        customers = customers_data if isinstance(customers_data, list) else []
        test_customer = None
        for c in customers:
            if c.get('name') != 'Toko Kain Sejahtera':
                test_customer = c
                break
        
        if not test_customer:
            self.log("No suitable customer found (avoiding Toko Kain Sejahtera)", "WARN")
            if customers:
                test_customer = customers[0]
        
        success, products_data = self.run_test("Get Products", "GET", "/products", 200)
        if not success or not products_data:
            self.log("Cannot proceed without products", "FAIL")
            return
        
        products = products_data if isinstance(products_data, list) else []
        test_product = None
        for p in products:
            # Avoid "Batik Mega Mendung" if customer is "Toko Kain Sejahtera"
            if test_customer.get('name') == 'Toko Kain Sejahtera' and p.get('name') == 'Batik Mega Mendung':
                continue
            if p.get('price', 0) > 0:
                test_product = p
                break
        
        if not test_product:
            self.log("No suitable product found", "FAIL")
            return
        
        self.log(f"Using customer: {test_customer.get('name')} (ID: {test_customer.get('id')})", "INFO")
        self.log(f"Using product: {test_product.get('name')} (ID: {test_product.get('id')}, Price: {test_product.get('price')})", "INFO")
        
        # Test 1: Create price approval (request)
        normal_price = float(test_product.get('price', 0))
        requested_price = round(normal_price * 0.85, 2)  # 15% discount
        
        success, approval_data = self.run_test(
            "Create Price Approval",
            "POST",
            "/price-approvals",
            200,
            data={
                "customer_id": test_customer['id'],
                "product_id": test_product['id'],
                "requested_price": requested_price,
                "min_quantity": 10,
                "valid_until": "2025-12-31",
                "reason": "Test special price request from checkout",
                "submit_now": True,
                "entity_id": test_customer.get('entity_id', '')
            }
        )
        
        if not success:
            self.log("Failed to create price approval", "FAIL")
            return
        
        approval_id = approval_data.get('id')
        self.log(f"Created approval ID: {approval_id}", "SUCCESS")
        
        # Test 2: Get effective price (should not exist yet - pending)
        success, effective_data = self.run_test(
            "Get Effective Price (should be false - pending)",
            "GET",
            "/price-approvals/effective",
            200,
            params={
                "customer_id": test_customer['id'],
                "product_id": test_product['id'],
                "entity_id": test_customer.get('entity_id', ''),
                "quantity": 10
            }
        )
        
        if success:
            has_special = effective_data.get('has_special', False)
            if not has_special:
                self.log("Correctly returns has_special=false for pending approval", "SUCCESS")
            else:
                self.log("WARNING: has_special=true for pending approval (should be false)", "WARN")
        
        # Test 3: Approve the price approval (admin only)
        success, approved_data = self.run_test(
            "Approve Price Approval",
            "POST",
            f"/price-approvals/{approval_id}/approve",
            200,
            data={"decision_notes": "Approved for testing"}
        )
        
        if not success:
            self.log("Failed to approve price approval", "FAIL")
            return
        
        self.log(f"Approved approval ID: {approval_id}", "SUCCESS")
        
        # Test 4: Get effective price (should exist now - approved)
        success, effective_data = self.run_test(
            "Get Effective Price (should be true - approved)",
            "GET",
            "/price-approvals/effective",
            200,
            params={
                "customer_id": test_customer['id'],
                "product_id": test_product['id'],
                "entity_id": test_customer.get('entity_id', ''),
                "quantity": 10
            }
        )
        
        if success:
            has_special = effective_data.get('has_special', False)
            returned_price = effective_data.get('requested_price', 0)
            if has_special and abs(returned_price - requested_price) < 0.01:
                self.log(f"Correctly returns has_special=true with price={returned_price}", "SUCCESS")
            else:
                self.log(f"WARNING: has_special={has_special}, price={returned_price} (expected {requested_price})", "WARN")
        
        # Test 5: List price approvals
        success, list_data = self.run_test(
            "List Price Approvals",
            "GET",
            "/price-approvals",
            200
        )
        
        if success:
            approvals = list_data if isinstance(list_data, list) else []
            found = any(a.get('id') == approval_id for a in approvals)
            if found:
                self.log(f"Found approval {approval_id} in list", "SUCCESS")
            else:
                self.log(f"Approval {approval_id} not found in list", "WARN")

    def print_summary(self):
        self.log("\n" + "="*60, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("="*60, "INFO")
        self.log(f"Total Tests: {self.tests_run}", "INFO")
        self.log(f"Passed: {self.tests_passed}", "SUCCESS")
        self.log(f"Failed: {self.tests_failed}", "FAIL")
        
        if self.failed_tests:
            self.log("\nFailed Tests:", "FAIL")
            for test in self.failed_tests:
                self.log(f"  - {test}", "FAIL")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"\nSuccess Rate: {success_rate:.1f}%", "INFO")
        
        return 0 if self.tests_failed == 0 else 1

def main():
    tester = PriceApprovalsAPITester()
    
    # Login as admin
    if not tester.test_login(ADMIN_EMAIL, ADMIN_PASSWORD):
        print("❌ Login failed, cannot proceed")
        return 1
    
    # Run price approvals tests
    tester.test_price_approvals_flow()
    
    # Print summary
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
