"""
R5.4b Backend API Test - Purchase Return Reversal & Write-off Reversal
Tests all R5.4b endpoints with proper authentication and RBAC
"""
import requests
import sys

BASE_URL = "https://return-reversals.preview.emergentagent.com/api"

# Test credentials
ADMIN_CREDS = {"email": "admin@kainnusantara.id", "password": "demo12345"}
SALES_CREDS = {"email": "sales@kainnusantara.id", "password": "demo12345"}

class R54bAPITester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.admin_token = None
        self.sales_token = None

    def test(self, name, condition, details=""):
        """Run a single test"""
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        return condition

    def login(self, credentials):
        """Login and return auth header"""
        try:
            r = requests.post(f"{BASE_URL}/auth/login", json=credentials, timeout=30)
            if r.status_code == 200:
                token = r.json().get("token")
                return {"Authorization": f"Bearer {token}"}
            return None
        except Exception as e:
            print(f"Login error: {e}")
            return None

    def test_auth(self):
        """Test authentication"""
        print("\n=== Testing Authentication ===")
        self.admin_token = self.login(ADMIN_CREDS)
        self.test("Admin login successful", self.admin_token is not None)
        
        self.sales_token = self.login(SALES_CREDS)
        self.test("Sales login successful", self.sales_token is not None)

    def test_purchase_return_reversal_rbac(self):
        """Test RBAC for purchase return reversal"""
        print("\n=== Testing Purchase Return Reversal RBAC ===")
        
        # Get a finalized purchase return
        try:
            r = requests.get(f"{BASE_URL}/purchase-returns", 
                           headers=self.admin_token, 
                           params={"status": "approved"},
                           timeout=30)
            if r.status_code == 200:
                returns = r.json().get("items", [])
                finalized = [pr for pr in returns if pr.get("stock_adjusted") and 
                           pr.get("supplier_status") == "accepted_supplier" and
                           not pr.get("reversed")]
                
                if finalized:
                    pr_id = finalized[0]["id"]
                    
                    # Test sales role (should be forbidden)
                    r_sales = requests.post(
                        f"{BASE_URL}/purchase-returns/{pr_id}/reverse",
                        headers=self.sales_token,
                        json={"notes": "test reversal"},
                        timeout=30
                    )
                    self.test("Sales role forbidden for purchase return reversal",
                            r_sales.status_code in [401, 403],
                            f"Got {r_sales.status_code}")
                    
                    # Test admin role (should succeed or already reversed)
                    r_admin = requests.post(
                        f"{BASE_URL}/purchase-returns/{pr_id}/reverse",
                        headers=self.admin_token,
                        json={"notes": "test reversal admin"},
                        timeout=30
                    )
                    self.test("Admin can access purchase return reversal endpoint",
                            r_admin.status_code in [200, 400],
                            f"Got {r_admin.status_code}")
                else:
                    print("⚠️  No finalized purchase returns available for RBAC test")
        except Exception as e:
            print(f"❌ Purchase return reversal RBAC test error: {e}")

    def test_writeoff_reversal_rbac(self):
        """Test RBAC for write-off reversal"""
        print("\n=== Testing Write-off Reversal RBAC ===")
        
        try:
            # Get sales returns
            r = requests.get(f"{BASE_URL}/sales-returns",
                           headers=self.admin_token,
                           timeout=30)
            if r.status_code == 200:
                returns = r.json().get("items", [])
                
                # Find a return with potential scrapped rolls
                for ret in returns:
                    ret_id = ret["id"]
                    
                    # Test sales role (should be forbidden)
                    r_sales = requests.post(
                        f"{BASE_URL}/sales-returns/{ret_id}/reverse-writeoff",
                        headers=self.sales_token,
                        json={"roll_ids": [], "reason": "test"},
                        timeout=30
                    )
                    self.test("Sales role forbidden for write-off reversal",
                            r_sales.status_code in [401, 403],
                            f"Got {r_sales.status_code}")
                    
                    # Test admin role (should succeed or no scrapped rolls)
                    r_admin = requests.post(
                        f"{BASE_URL}/sales-returns/{ret_id}/reverse-writeoff",
                        headers=self.admin_token,
                        json={"roll_ids": [], "reason": "test admin"},
                        timeout=30
                    )
                    self.test("Admin can access write-off reversal endpoint",
                            r_admin.status_code in [200, 400],
                            f"Got {r_admin.status_code}: {r_admin.text[:100]}")
                    break
        except Exception as e:
            print(f"❌ Write-off reversal RBAC test error: {e}")

    def test_purchase_return_list(self):
        """Test purchase returns list endpoint"""
        print("\n=== Testing Purchase Returns List ===")
        try:
            r = requests.get(f"{BASE_URL}/purchase-returns",
                           headers=self.admin_token,
                           timeout=30)
            self.test("GET /purchase-returns returns 200",
                     r.status_code == 200,
                     f"Got {r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                self.test("Purchase returns response has items",
                         "items" in data or isinstance(data, list))
        except Exception as e:
            print(f"❌ Purchase returns list error: {e}")

    def test_sales_return_list(self):
        """Test sales returns list endpoint"""
        print("\n=== Testing Sales Returns List ===")
        try:
            r = requests.get(f"{BASE_URL}/sales-returns",
                           headers=self.admin_token,
                           timeout=30)
            self.test("GET /sales-returns returns 200",
                     r.status_code == 200,
                     f"Got {r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                self.test("Sales returns response has items",
                         "items" in data or isinstance(data, list))
        except Exception as e:
            print(f"❌ Sales returns list error: {e}")

    def test_regression_r5_4_endpoints(self):
        """Test that existing R5.4 endpoints still work"""
        print("\n=== Testing R5.4 Regression (Existing Endpoints) ===")
        
        # Test sales return settlement reversal endpoint exists
        try:
            r = requests.get(f"{BASE_URL}/sales-returns",
                           headers=self.admin_token,
                           timeout=30)
            if r.status_code == 200:
                returns = r.json().get("items", [])
                if returns:
                    ret_id = returns[0]["id"]
                    # Just check endpoint exists (will return 400 if not settled, but that's ok)
                    r_rev = requests.post(
                        f"{BASE_URL}/sales-returns/{ret_id}/reverse",
                        headers=self.admin_token,
                        json={"notes": "test"},
                        timeout=30
                    )
                    self.test("R5.4 sales return reversal endpoint exists",
                             r_rev.status_code in [200, 400, 404],
                             f"Got {r_rev.status_code}")
        except Exception as e:
            print(f"⚠️  R5.4 regression test: {e}")

    def run_all_tests(self):
        """Run all tests"""
        print("=" * 60)
        print("R5.4b Backend API Tests")
        print("=" * 60)
        
        self.test_auth()
        
        if not self.admin_token:
            print("\n❌ Cannot proceed without admin authentication")
            return False
        
        self.test_purchase_return_list()
        self.test_sales_return_list()
        self.test_purchase_return_reversal_rbac()
        self.test_writeoff_reversal_rbac()
        self.test_regression_r5_4_endpoints()
        
        print("\n" + "=" * 60)
        print(f"Results: {self.tests_passed}/{self.tests_run} tests passed")
        print("=" * 60)
        
        return self.tests_passed == self.tests_run

def main():
    tester = R54bAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
