"""
Backend Security Testing - KN-076/KN-079 P0/P1 Bug Fixes
Tests auth enforcement, IDOR protection, numeric bounds validation
"""
import requests
import sys
from typing import Dict, Any, Optional

BASE_URL = "https://bug-fix-sprint-27.preview.emergentagent.com/api"

class SecurityTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.admin_token = None
        self.sales_token = None
        self.warehouse_token = None
        self.failures = []

    def log_result(self, test_name: str, passed: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            print(f"✅ PASS: {test_name}")
        else:
            self.tests_failed += 1
            print(f"❌ FAIL: {test_name}")
            if details:
                print(f"   Details: {details}")
            self.failures.append({"test": test_name, "details": details})

    def login(self, email: str, password: str) -> Optional[str]:
        """Login and return token"""
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": email, "password": password},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("token")
            else:
                print(f"⚠️  Login failed for {email}: {response.status_code}")
                return None
        except Exception as e:
            print(f"⚠️  Login error for {email}: {str(e)}")
            return None

    def test_auth_enforcement(self):
        """Test KN-076: Auth enforcement on previously unprotected endpoints"""
        print("\n" + "="*80)
        print("TEST GROUP 1: AUTH ENFORCEMENT (KN-076)")
        print("="*80)

        # Endpoints that MUST require auth
        unauth_endpoints = [
            ("GET", "/products", "Products list"),
            ("GET", "/uoms", "UOMs list"),
            ("GET", "/warehouses", "Warehouses list"),
            ("GET", "/pos/best-sellers", "POS best sellers"),
            ("GET", "/documents/preview/so_001?document_type=surat_jalan", "Document preview"),
        ]

        for method, endpoint, description in unauth_endpoints:
            try:
                response = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
                expected = 401
                actual = response.status_code
                passed = actual == expected
                self.log_result(
                    f"Unauth {description}",
                    passed,
                    f"Expected {expected}, got {actual}"
                )
            except Exception as e:
                self.log_result(f"Unauth {description}", False, f"Error: {str(e)}")

        # Same endpoints WITH auth should work
        if self.admin_token:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            for method, endpoint, description in unauth_endpoints:
                try:
                    response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=10)
                    expected = 200
                    actual = response.status_code
                    passed = actual == expected
                    self.log_result(
                        f"Auth {description}",
                        passed,
                        f"Expected {expected}, got {actual}"
                    )
                except Exception as e:
                    self.log_result(f"Auth {description}", False, f"Error: {str(e)}")

    def test_idor_read_customers(self):
        """Test KN-076/KN-079: IDOR read protection for customers"""
        print("\n" + "="*80)
        print("TEST GROUP 2: IDOR READ PROTECTION - CUSTOMERS (KN-076/KN-079)")
        print("="*80)

        if not self.sales_token or not self.admin_token:
            print("⚠️  Skipping IDOR tests - missing tokens")
            return

        # sales@kainnusantara.id is in ent_ksc
        # Should access own entity customer (cust_toko_kain in ent_ksc)
        # Should NOT access foreign entity customer (cust_moda_surabaya in ent_kanda)

        sales_headers = {"Authorization": f"Bearer {self.sales_token}"}
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}

        # Test 1: Sales accessing OWN entity customer - should work (200)
        own_customer_tests = [
            ("/customers/cust_toko_kain/360", "Customer 360 (own entity)"),
            ("/customers/cust_toko_kain/credit-status", "Credit status (own entity)"),
        ]

        for endpoint, description in own_customer_tests:
            try:
                response = requests.get(f"{BASE_URL}{endpoint}", headers=sales_headers, timeout=10)
                expected = 200
                actual = response.status_code
                passed = actual == expected
                self.log_result(
                    f"Sales {description}",
                    passed,
                    f"Expected {expected}, got {actual}"
                )
            except Exception as e:
                self.log_result(f"Sales {description}", False, f"Error: {str(e)}")

        # Test 2: Sales accessing FOREIGN entity customer - should be blocked (403)
        foreign_customer_tests = [
            ("/customers/cust_moda_surabaya/360", "Customer 360 (foreign entity)"),
            ("/customers/cust_moda_surabaya/credit-status", "Credit status (foreign entity)"),
        ]

        for endpoint, description in foreign_customer_tests:
            try:
                response = requests.get(f"{BASE_URL}{endpoint}", headers=sales_headers, timeout=10)
                expected = 403
                actual = response.status_code
                passed = actual == expected
                self.log_result(
                    f"Sales {description} BLOCKED",
                    passed,
                    f"Expected {expected}, got {actual}"
                )
            except Exception as e:
                self.log_result(f"Sales {description} BLOCKED", False, f"Error: {str(e)}")

        # Test 3: Admin (cross-entity) accessing foreign customer - should work (200)
        try:
            response = requests.get(f"{BASE_URL}/customers/cust_moda_surabaya/360", headers=admin_headers, timeout=10)
            expected = 200
            actual = response.status_code
            passed = actual == expected
            self.log_result(
                "Admin cross-entity customer access",
                passed,
                f"Expected {expected}, got {actual}"
            )
        except Exception as e:
            self.log_result("Admin cross-entity customer access", False, f"Error: {str(e)}")

    def test_idor_read_sales_orders(self):
        """Test KN-076: IDOR read protection for sales order sub-resources"""
        print("\n" + "="*80)
        print("TEST GROUP 3: IDOR READ PROTECTION - SALES ORDERS (KN-076)")
        print("="*80)

        if not self.sales_token or not self.admin_token:
            print("⚠️  Skipping SO IDOR tests - missing tokens")
            return

        sales_headers = {"Authorization": f"Bearer {self.sales_token}"}
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}

        # First, get a foreign entity SO (ent_kanda) as admin
        try:
            response = requests.get(f"{BASE_URL}/sales-orders", headers=admin_headers, timeout=10)
            if response.status_code == 200:
                orders = response.json()
                foreign_so = None
                for order in orders:
                    if order.get("entity_id") == "ent_kanda":
                        foreign_so = order.get("id")
                        break
                
                if foreign_so:
                    # Sales (ent_ksc) trying to access foreign SO invoices - should be blocked
                    try:
                        response = requests.get(
                            f"{BASE_URL}/sales-orders/{foreign_so}/invoices",
                            headers=sales_headers,
                            timeout=10
                        )
                        expected_codes = [403, 404]
                        actual = response.status_code
                        passed = actual in expected_codes
                        self.log_result(
                            "Sales accessing foreign SO invoices BLOCKED",
                            passed,
                            f"Expected {expected_codes}, got {actual}"
                        )
                    except Exception as e:
                        self.log_result("Sales accessing foreign SO invoices BLOCKED", False, f"Error: {str(e)}")
                else:
                    print("⚠️  No foreign entity SO found for testing")
        except Exception as e:
            print(f"⚠️  Error fetching SOs: {str(e)}")

    def test_idor_write_inbound(self):
        """Test KN-076: IDOR write protection for inbound tasks"""
        print("\n" + "="*80)
        print("TEST GROUP 4: IDOR WRITE PROTECTION - INBOUND TASKS (KN-076)")
        print("="*80)

        if not self.warehouse_token or not self.admin_token:
            print("⚠️  Skipping inbound IDOR tests - missing tokens")
            return

        warehouse_headers = {"Authorization": f"Bearer {self.warehouse_token}"}
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}

        # First, get a foreign entity inbound task (ent_kanda) as admin
        try:
            response = requests.get(f"{BASE_URL}/inbound/tasks", headers=admin_headers, timeout=10)
            if response.status_code == 200:
                tasks = response.json()
                foreign_task = None
                for task in tasks:
                    if task.get("entity_id") == "ent_kanda":
                        foreign_task = task.get("id")
                        break
                
                if foreign_task:
                    # Warehouse (ent_ksc) trying to escalate foreign task - should be blocked
                    try:
                        response = requests.post(
                            f"{BASE_URL}/inbound/tasks/{foreign_task}/escalate",
                            headers=warehouse_headers,
                            json={"reason": "Test escalation"},
                            timeout=10
                        )
                        expected_codes = [403, 404]
                        actual = response.status_code
                        passed = actual in expected_codes
                        self.log_result(
                            "Warehouse escalating foreign task BLOCKED",
                            passed,
                            f"Expected {expected_codes}, got {actual}"
                        )
                    except Exception as e:
                        self.log_result("Warehouse escalating foreign task BLOCKED", False, f"Error: {str(e)}")
                else:
                    print("⚠️  No foreign entity inbound task found for testing")
        except Exception as e:
            print(f"⚠️  Error fetching inbound tasks: {str(e)}")

    def test_numeric_bounds(self):
        """Test KN-079: Numeric bounds validation"""
        print("\n" + "="*80)
        print("TEST GROUP 5: NUMERIC BOUNDS VALIDATION (KN-079)")
        print("="*80)

        if not self.admin_token:
            print("⚠️  Skipping numeric bounds tests - missing admin token")
            return

        headers = {"Authorization": f"Bearer {self.admin_token}"}

        # Test 1: Negative credit_limit - should be rejected (422)
        try:
            response = requests.post(
                f"{BASE_URL}/customers",
                headers=headers,
                json={
                    "name": "Test Customer Negative",
                    "pic_name": "Test PIC",
                    "phone": "08123456789",
                    "city": "Jakarta",
                    "address": "Test Address",
                    "credit_limit": -5000000
                },
                timeout=10
            )
            expected = 422
            actual = response.status_code
            passed = actual == expected
            self.log_result(
                "Negative credit_limit rejected",
                passed,
                f"Expected {expected}, got {actual}"
            )
        except Exception as e:
            self.log_result("Negative credit_limit rejected", False, f"Error: {str(e)}")

        # Test 2: Negative product price - should be rejected (422)
        try:
            response = requests.post(
                f"{BASE_URL}/products",
                headers=headers,
                json={
                    "sku": "NEGSKU1",
                    "name": "Negative Price Product",
                    "price": -1000,
                    "harga_pokok": -500,
                    "gramasi": -10
                },
                timeout=10
            )
            expected = 422
            actual = response.status_code
            passed = actual == expected
            self.log_result(
                "Negative product price rejected",
                passed,
                f"Expected {expected}, got {actual}"
            )
        except Exception as e:
            self.log_result("Negative product price rejected", False, f"Error: {str(e)}")

        # Test 3: Invalid payment terms - should be rejected (422)
        try:
            response = requests.post(
                f"{BASE_URL}/payment-terms",
                headers=headers,
                json={
                    "code": "NEGT",
                    "name": "Negative Terms",
                    "type": "credit",
                    "net_days": -30,
                    "dp_percent": 999,
                    "installment_count": -5
                },
                timeout=10
            )
            expected = 422
            actual = response.status_code
            passed = actual == expected
            self.log_result(
                "Invalid payment terms rejected",
                passed,
                f"Expected {expected}, got {actual}"
            )
        except Exception as e:
            self.log_result("Invalid payment terms rejected", False, f"Error: {str(e)}")

        # Test 4: Valid values - should be accepted (200)
        try:
            response = requests.post(
                f"{BASE_URL}/customers",
                headers=headers,
                json={
                    "name": "Test Customer Valid",
                    "pic_name": "Test PIC",
                    "phone": "08123456789",
                    "city": "Jakarta",
                    "address": "Test Address",
                    "credit_limit": 5000000
                },
                timeout=10
            )
            expected = 200
            actual = response.status_code
            passed = actual == expected
            self.log_result(
                "Valid customer creation",
                passed,
                f"Expected {expected}, got {actual}"
            )
        except Exception as e:
            self.log_result("Valid customer creation", False, f"Error: {str(e)}")

    def test_legitimate_flows(self):
        """Test legitimate flows still work (regression check)"""
        print("\n" + "="*80)
        print("TEST GROUP 6: LEGITIMATE FLOW REGRESSION CHECK")
        print("="*80)

        if not self.admin_token:
            print("⚠️  Skipping regression tests - missing admin token")
            return

        headers = {"Authorization": f"Bearer {self.admin_token}"}

        # Test dashboard and list endpoints
        endpoints = [
            ("/dashboard", "Dashboard"),
            ("/products", "Products list"),
            ("/customers", "Customers list"),
            ("/sales-orders", "Sales orders list"),
            ("/purchase-orders", "Purchase orders list"),
        ]

        for endpoint, description in endpoints:
            try:
                response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=10)
                expected = 200
                actual = response.status_code
                passed = actual == expected
                self.log_result(
                    f"Admin {description}",
                    passed,
                    f"Expected {expected}, got {actual}"
                )
            except Exception as e:
                self.log_result(f"Admin {description}", False, f"Error: {str(e)}")

    def run_all_tests(self):
        """Run all security tests"""
        print("\n" + "="*80)
        print("KAIN NUSANTARA ERP - SECURITY TESTING")
        print("Testing P0/P1 Backend Security Fixes (KN-076, KN-079)")
        print("="*80)

        # Login all users
        print("\n🔐 Logging in test users...")
        self.admin_token = self.login("admin@kainnusantara.id", "demo12345")
        self.sales_token = self.login("sales@kainnusantara.id", "demo12345")
        self.warehouse_token = self.login("warehouse@kainnusantara.id", "demo12345")

        if not self.admin_token:
            print("❌ CRITICAL: Admin login failed. Cannot proceed with tests.")
            return 1

        # Run test groups
        self.test_auth_enforcement()
        self.test_idor_read_customers()
        self.test_idor_read_sales_orders()
        self.test_idor_write_inbound()
        self.test_numeric_bounds()
        self.test_legitimate_flows()

        # Print summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Total tests run: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {self.tests_failed}")
        print(f"Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")

        if self.failures:
            print("\n" + "="*80)
            print("FAILED TESTS DETAILS")
            print("="*80)
            for failure in self.failures:
                print(f"\n❌ {failure['test']}")
                print(f"   {failure['details']}")

        return 0 if self.tests_failed == 0 else 1


def main():
    tester = SecurityTester()
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
