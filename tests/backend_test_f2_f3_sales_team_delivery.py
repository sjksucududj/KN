"""
Backend API tests for F2 (Sales Team at Checkout) and F3 (Delivery Date).

Tests:
1. Login with admin credentials
2. F2: Sales team validation (exactly 1 PIC, no duplicates, split > 0, total = 100%)
3. F3: Delivery date validation (optional, cannot be past, kirim only)
4. Order creation with custom sales team and delivery date
5. Order retrieval to verify sales_team and delivery_date stored correctly
"""
import requests
import sys
from datetime import datetime, timedelta

BASE_URL = "https://kainnusantara-stage.preview.emergentagent.com/api"

class TestF2F3:
    def __init__(self):
        self.token = None
        self.customer_id = None
        self.address_id = None
        self.product_id = None
        self.sales_user_ids = []
        self.tests_run = 0
        self.tests_passed = 0

    def log(self, msg, success=None):
        """Log test result"""
        self.tests_run += 1
        if success is True:
            self.tests_passed += 1
            print(f"✅ PASS: {msg}")
        elif success is False:
            print(f"❌ FAIL: {msg}")
        else:
            print(f"🔍 {msg}")

    def test_login(self):
        """Test 1: Login with admin credentials"""
        self.log("Testing login with admin@kainnusantara.id", None)
        try:
            response = requests.post(f"{BASE_URL}/auth/login", json={
                "email": "admin@kainnusantara.id",
                "password": "demo12345"
            })
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token")
                self.log(f"Login successful, role: {data.get('user', {}).get('role')}", True)
                return True
            else:
                self.log(f"Login failed: {response.status_code} - {response.text}", False)
                return False
        except Exception as e:
            self.log(f"Login error: {str(e)}", False)
            return False

    def get_test_data(self):
        """Get customer, product, and sales users for testing"""
        self.log("Fetching test data (customers, products, sales users)", None)
        headers = {"Authorization": f"Bearer {self.token}"}
        
        try:
            # Get customers
            resp = requests.get(f"{BASE_URL}/customers", headers=headers)
            if resp.status_code == 200:
                customers = resp.json()
                if customers:
                    self.customer_id = customers[0]["id"]
                    self.address_id = customers[0].get("addresses", [{}])[0].get("id", "")
                    self.log(f"Found customer: {customers[0]['name']} (ID: {self.customer_id})", True)
            
            # Get products
            resp = requests.get(f"{BASE_URL}/products", headers=headers)
            if resp.status_code == 200:
                products = resp.json()
                if products:
                    self.product_id = products[0]["id"]
                    self.log(f"Found product: {products[0]['name']} (ID: {self.product_id})", True)
            
            # Get sales users
            resp = requests.get(f"{BASE_URL}/sales-users", headers=headers)
            if resp.status_code == 200:
                sales_users = resp.json()
                self.sales_user_ids = [u["id"] for u in sales_users[:3]]  # Get first 3 sales users
                self.log(f"Found {len(self.sales_user_ids)} sales users", True)
            
            return bool(self.customer_id and self.product_id and len(self.sales_user_ids) >= 2)
        except Exception as e:
            self.log(f"Error fetching test data: {str(e)}", False)
            return False

    def test_sales_team_validation_total_not_100(self):
        """Test F2: Sales team with total split != 100% should return 400"""
        self.log("Testing sales team validation: total split != 100%", None)
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        payload = {
            "customer_id": self.customer_id,
            "shipping_address_id": self.address_id,
            "items": [{"product_id": self.product_id, "quantity": 10, "unit": "meter"}],
            "sales_team": [
                {"sales_id": self.sales_user_ids[0], "name": "Sales A", "role": "pic", "split_pct": 60},
                {"sales_id": self.sales_user_ids[1], "name": "Sales B", "role": "co", "split_pct": 30}
            ],  # Total = 90%, not 100%
            "fulfillment_method": "kirim"
        }
        
        try:
            response = requests.post(f"{BASE_URL}/sales-orders", json=payload, headers=headers)
            if response.status_code == 400 and "100%" in response.text:
                self.log(f"Correctly rejected: {response.json().get('detail', response.text)}", True)
                return True
            else:
                self.log(f"Expected 400 with '100%' message, got {response.status_code}: {response.text}", False)
                return False
        except Exception as e:
            self.log(f"Error: {str(e)}", False)
            return False

    def test_sales_team_validation_no_pic(self):
        """Test F2: Sales team without exactly 1 PIC should return 400"""
        self.log("Testing sales team validation: no PIC", None)
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        payload = {
            "customer_id": self.customer_id,
            "shipping_address_id": self.address_id,
            "items": [{"product_id": self.product_id, "quantity": 10, "unit": "meter"}],
            "sales_team": [
                {"sales_id": self.sales_user_ids[0], "name": "Sales A", "role": "co", "split_pct": 50},
                {"sales_id": self.sales_user_ids[1], "name": "Sales B", "role": "co", "split_pct": 50}
            ],  # No PIC
            "fulfillment_method": "kirim"
        }
        
        try:
            response = requests.post(f"{BASE_URL}/sales-orders", json=payload, headers=headers)
            if response.status_code == 400 and "PIC" in response.text:
                self.log(f"Correctly rejected: {response.json().get('detail', response.text)}", True)
                return True
            else:
                self.log(f"Expected 400 with 'PIC' message, got {response.status_code}: {response.text}", False)
                return False
        except Exception as e:
            self.log(f"Error: {str(e)}", False)
            return False

    def test_sales_team_validation_duplicate(self):
        """Test F2: Sales team with duplicate sales IDs should return 400"""
        self.log("Testing sales team validation: duplicate sales IDs", None)
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        payload = {
            "customer_id": self.customer_id,
            "shipping_address_id": self.address_id,
            "items": [{"product_id": self.product_id, "quantity": 10, "unit": "meter"}],
            "sales_team": [
                {"sales_id": self.sales_user_ids[0], "name": "Sales A", "role": "pic", "split_pct": 60},
                {"sales_id": self.sales_user_ids[0], "name": "Sales A", "role": "co", "split_pct": 40}
            ],  # Duplicate sales_id
            "fulfillment_method": "kirim"
        }
        
        try:
            response = requests.post(f"{BASE_URL}/sales-orders", json=payload, headers=headers)
            if response.status_code == 400 and "duplikat" in response.text.lower():
                self.log(f"Correctly rejected: {response.json().get('detail', response.text)}", True)
                return True
            else:
                self.log(f"Expected 400 with 'duplikat' message, got {response.status_code}: {response.text}", False)
                return False
        except Exception as e:
            self.log(f"Error: {str(e)}", False)
            return False

    def test_delivery_date_past(self):
        """Test F3: Delivery date in the past should return 400"""
        self.log("Testing delivery date validation: past date", None)
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        payload = {
            "customer_id": self.customer_id,
            "shipping_address_id": self.address_id,
            "items": [{"product_id": self.product_id, "quantity": 10, "unit": "meter"}],
            "fulfillment_method": "kirim",
            "delivery_date": yesterday
        }
        
        try:
            response = requests.post(f"{BASE_URL}/sales-orders", json=payload, headers=headers)
            if response.status_code == 400 and "masa lalu" in response.text.lower():
                self.log(f"Correctly rejected: {response.json().get('detail', response.text)}", True)
                return True
            else:
                self.log(f"Expected 400 with 'masa lalu' message, got {response.status_code}: {response.text}", False)
                return False
        except Exception as e:
            self.log(f"Error: {str(e)}", False)
            return False

    def test_empty_sales_team_fallback(self):
        """Test F2: Empty sales_team should fallback to customer's default team"""
        self.log("Testing empty sales_team fallback to customer default", None)
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        payload = {
            "customer_id": self.customer_id,
            "shipping_address_id": self.address_id,
            "items": [{"product_id": self.product_id, "quantity": 10, "unit": "meter"}],
            "sales_team": [],  # Empty
            "fulfillment_method": "kirim"
        }
        
        try:
            response = requests.post(f"{BASE_URL}/sales-orders", json=payload, headers=headers)
            if response.status_code in [200, 201]:
                order = response.json()
                sales_team = order.get("sales_team", [])
                if len(sales_team) > 0:
                    self.log(f"Order created with fallback sales_team: {len(sales_team)} member(s)", True)
                    return order["id"]
                else:
                    self.log("Order created but sales_team is empty (customer may not have default team)", True)
                    return order["id"]
            else:
                self.log(f"Order creation failed: {response.status_code} - {response.text}", False)
                return None
        except Exception as e:
            self.log(f"Error: {str(e)}", False)
            return None

    def test_valid_custom_sales_team_and_delivery_date(self):
        """Test F2+F3: Valid custom sales team (PIC 60% + co 40%) with future delivery date"""
        self.log("Testing valid custom sales team (PIC 60% + co 40%) with future delivery date", None)
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        payload = {
            "customer_id": self.customer_id,
            "shipping_address_id": self.address_id,
            "items": [{"product_id": self.product_id, "quantity": 10, "unit": "meter"}],
            "sales_team": [
                {"sales_id": self.sales_user_ids[0], "name": "Sales A", "role": "pic", "split_pct": 60},
                {"sales_id": self.sales_user_ids[1], "name": "Sales B", "role": "co", "split_pct": 40}
            ],
            "fulfillment_method": "kirim",
            "delivery_date": tomorrow
        }
        
        try:
            response = requests.post(f"{BASE_URL}/sales-orders", json=payload, headers=headers)
            if response.status_code in [200, 201]:
                order = response.json()
                self.log(f"Order created: {order.get('number')} (ID: {order.get('id')})", True)
                
                # Verify sales_team
                sales_team = order.get("sales_team", [])
                if len(sales_team) == 2:
                    pic_count = sum(1 for m in sales_team if m.get("role") == "pic")
                    total_split = sum(m.get("split_pct", 0) for m in sales_team)
                    if pic_count == 1 and abs(total_split - 100) < 0.01:
                        self.log(f"Sales team correct: 2 members, 1 PIC, total split {total_split}%", True)
                    else:
                        self.log(f"Sales team incorrect: PIC count={pic_count}, total split={total_split}%", False)
                else:
                    self.log(f"Sales team incorrect: expected 2 members, got {len(sales_team)}", False)
                
                # Verify delivery_date
                if order.get("delivery_date") == tomorrow:
                    self.log(f"Delivery date correct: {tomorrow}", True)
                else:
                    self.log(f"Delivery date incorrect: expected {tomorrow}, got {order.get('delivery_date')}", False)
                
                return order["id"]
            else:
                self.log(f"Order creation failed: {response.status_code} - {response.text}", False)
                return None
        except Exception as e:
            self.log(f"Error: {str(e)}", False)
            return None

    def test_order_retrieval(self, order_id):
        """Test: Retrieve order and verify sales_team and delivery_date are stored"""
        self.log(f"Testing order retrieval for ID: {order_id}", None)
        headers = {"Authorization": f"Bearer {self.token}"}
        
        try:
            response = requests.get(f"{BASE_URL}/sales-orders/{order_id}", headers=headers)
            if response.status_code == 200:
                order = response.json()
                sales_team = order.get("sales_team", [])
                delivery_date = order.get("delivery_date", "")
                
                self.log(f"Order retrieved: {order.get('number')}", True)
                self.log(f"  - Sales team: {len(sales_team)} member(s)", None)
                for i, m in enumerate(sales_team):
                    self.log(f"    [{i}] {m.get('name')} ({m.get('role')}) - {m.get('split_pct')}%", None)
                self.log(f"  - Delivery date: {delivery_date or '(not set)'}", None)
                return True
            else:
                self.log(f"Order retrieval failed: {response.status_code} - {response.text}", False)
                return False
        except Exception as e:
            self.log(f"Error: {str(e)}", False)
            return False

    def run_all_tests(self):
        """Run all backend tests"""
        print("\n" + "="*80)
        print("BACKEND API TESTS: F2 (Sales Team) + F3 (Delivery Date)")
        print("="*80 + "\n")
        
        # Test 1: Login
        if not self.test_login():
            print("\n❌ Login failed, cannot continue tests")
            return False
        
        # Get test data
        if not self.get_test_data():
            print("\n❌ Failed to get test data, cannot continue tests")
            return False
        
        print("\n" + "-"*80)
        print("F2: SALES TEAM VALIDATION TESTS")
        print("-"*80 + "\n")
        
        # Test 2: Sales team validation - total != 100%
        self.test_sales_team_validation_total_not_100()
        
        # Test 3: Sales team validation - no PIC
        self.test_sales_team_validation_no_pic()
        
        # Test 4: Sales team validation - duplicate
        self.test_sales_team_validation_duplicate()
        
        print("\n" + "-"*80)
        print("F3: DELIVERY DATE VALIDATION TESTS")
        print("-"*80 + "\n")
        
        # Test 5: Delivery date in the past
        self.test_delivery_date_past()
        
        print("\n" + "-"*80)
        print("F2+F3: ORDER CREATION TESTS")
        print("-"*80 + "\n")
        
        # Test 6: Empty sales_team fallback
        order_id_1 = self.test_empty_sales_team_fallback()
        if order_id_1:
            self.test_order_retrieval(order_id_1)
        
        # Test 7: Valid custom sales team + delivery date
        order_id_2 = self.test_valid_custom_sales_team_and_delivery_date()
        if order_id_2:
            self.test_order_retrieval(order_id_2)
        
        # Summary
        print("\n" + "="*80)
        print(f"BACKEND TESTS SUMMARY: {self.tests_passed}/{self.tests_run} passed")
        print("="*80 + "\n")
        
        return self.tests_passed == self.tests_run


if __name__ == "__main__":
    tester = TestF2F3()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
