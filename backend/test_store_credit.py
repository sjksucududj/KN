#!/usr/bin/env python3
"""
R5.2 Store Credit Backend API Test
Tests all store credit endpoints and flows
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://supplier-rma-portal.preview.emergentagent.com/api"
TEST_USER = {"email": "admin@kainnusantara.id", "password": "demo12345"}

class StoreCreditTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        self.results = []

    def log(self, status, test_name, details=""):
        """Log test result"""
        self.tests_run += 1
        if status == "PASS":
            self.tests_passed += 1
            print(f"✅ PASS: {test_name}")
        else:
            print(f"❌ FAIL: {test_name}")
        if details:
            print(f"   {details}")
        self.results.append({"test": test_name, "status": status, "details": details})

    def get_headers(self):
        """Get auth headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def test_auth(self):
        """Test authentication"""
        try:
            r = requests.post(f"{BASE_URL}/auth/login", json=TEST_USER, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "token" in data:
                    self.token = data["token"]
                    self.log("PASS", "Auth - Login", f"User: {data.get('user', {}).get('name', 'N/A')}")
                    return True
                else:
                    self.log("FAIL", "Auth - Login", f"Missing 'token' field")
                    return False
            self.log("FAIL", "Auth - Login", f"Status: {r.status_code}")
            return False
        except Exception as e:
            self.log("FAIL", "Auth - Login", f"Error: {str(e)}")
            return False

    def test_get_summary(self):
        """Test GET /api/store-credit (summary)"""
        try:
            r = requests.get(f"{BASE_URL}/store-credit", headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    self.log("PASS", "GET /store-credit (summary)", f"Returned {len(data)} customers")
                    return True, data
                else:
                    self.log("FAIL", "GET /store-credit", f"Expected list, got {type(data)}")
                    return False, []
            else:
                self.log("FAIL", "GET /store-credit", f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False, []
        except Exception as e:
            self.log("FAIL", "GET /store-credit", f"Error: {str(e)}")
            return False, []

    def test_get_balance(self, customer_id, entity_id=None):
        """Test GET /api/store-credit/balance"""
        try:
            params = {"customer_id": customer_id}
            if entity_id:
                params["entity_id"] = entity_id
            r = requests.get(f"{BASE_URL}/store-credit/balance", params=params, 
                           headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "balance" in data and "by_entity" in data:
                    self.log("PASS", "GET /store-credit/balance", 
                           f"Balance: {data.get('balance')}, Entities: {len(data.get('by_entity', {}))}")
                    return True, data
                else:
                    self.log("FAIL", "GET /store-credit/balance", f"Missing fields: {list(data.keys())}")
                    return False, {}
            else:
                self.log("FAIL", "GET /store-credit/balance", f"Status: {r.status_code}")
                return False, {}
        except Exception as e:
            self.log("FAIL", "GET /store-credit/balance", f"Error: {str(e)}")
            return False, {}

    def test_get_ledger(self, customer_id=None, entity_id=None):
        """Test GET /api/store-credit/ledger"""
        try:
            params = {}
            if customer_id:
                params["customer_id"] = customer_id
            if entity_id:
                params["entity_id"] = entity_id
            r = requests.get(f"{BASE_URL}/store-credit/ledger", params=params,
                           headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    self.log("PASS", "GET /store-credit/ledger", f"Returned {len(data)} entries")
                    return True, data
                else:
                    self.log("FAIL", "GET /store-credit/ledger", f"Expected list, got {type(data)}")
                    return False, []
            else:
                self.log("FAIL", "GET /store-credit/ledger", f"Status: {r.status_code}")
                return False, []
        except Exception as e:
            self.log("FAIL", "GET /store-credit/ledger", f"Error: {str(e)}")
            return False, []

    def test_get_open_orders(self, customer_id):
        """Test GET /api/store-credit/open-orders"""
        try:
            r = requests.get(f"{BASE_URL}/store-credit/open-orders", 
                           params={"customer_id": customer_id},
                           headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    self.log("PASS", "GET /store-credit/open-orders", 
                           f"Returned {len(data)} open AR orders")
                    return True, data
                else:
                    self.log("FAIL", "GET /store-credit/open-orders", f"Expected list")
                    return False, []
            else:
                self.log("FAIL", "GET /store-credit/open-orders", f"Status: {r.status_code}")
                return False, []
        except Exception as e:
            self.log("FAIL", "GET /store-credit/open-orders", f"Error: {str(e)}")
            return False, []

    def test_redeem(self, customer_id, entity_id, amount, allocations=None):
        """Test POST /api/store-credit/redeem"""
        try:
            payload = {
                "customer_id": customer_id,
                "entity_id": entity_id,
                "amount": amount,
                "note": "Test redeem"
            }
            if allocations:
                payload["allocations"] = allocations
            
            r = requests.post(f"{BASE_URL}/store-credit/redeem", json=payload,
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "applied_amount" in data:
                    self.log("PASS", "POST /store-credit/redeem", 
                           f"Applied: {data.get('applied_amount')}, Number: {data.get('number')}")
                    return True, data
                else:
                    self.log("FAIL", "POST /store-credit/redeem", f"Missing applied_amount")
                    return False, {}
            else:
                self.log("FAIL", "POST /store-credit/redeem", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False, {}
        except Exception as e:
            self.log("FAIL", "POST /store-credit/redeem", f"Error: {str(e)}")
            return False, {}

    def test_adjust(self, customer_id, entity_id, amount, note="Test adjust"):
        """Test POST /api/store-credit/adjust"""
        try:
            payload = {
                "customer_id": customer_id,
                "entity_id": entity_id,
                "amount": amount,
                "note": note
            }
            r = requests.post(f"{BASE_URL}/store-credit/adjust", json=payload,
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "balance_after" in data:
                    self.log("PASS", "POST /store-credit/adjust", 
                           f"Adjusted by {amount}, Balance after: {data.get('balance_after')}")
                    return True, data
                else:
                    self.log("FAIL", "POST /store-credit/adjust", f"Missing balance_after")
                    return False, {}
            else:
                self.log("FAIL", "POST /store-credit/adjust", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False, {}
        except Exception as e:
            self.log("FAIL", "POST /store-credit/adjust", f"Error: {str(e)}")
            return False, {}

    def test_over_redeem(self, customer_id, entity_id):
        """Test over-redeem (should return 400)"""
        try:
            payload = {
                "customer_id": customer_id,
                "entity_id": entity_id,
                "amount": 999999999,
                "note": "Test over-redeem"
            }
            r = requests.post(f"{BASE_URL}/store-credit/redeem", json=payload,
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 400:
                self.log("PASS", "Over-redeem validation", "Correctly rejected with 400")
                return True
            else:
                self.log("FAIL", "Over-redeem validation", 
                       f"Expected 400, got {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "Over-redeem validation", f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all store credit tests"""
        print("=" * 80)
        print("R5.2 STORE CREDIT BACKEND API TEST")
        print("=" * 80)
        print()

        # Auth test
        print("--- Authentication Test ---")
        if not self.test_auth():
            print("\n❌ Admin auth failed. Cannot proceed.")
            return False

        # Test GET endpoints
        print("\n--- GET Endpoints ---")
        success, summary = self.test_get_summary()
        
        # Test with first customer if available
        if summary and len(summary) > 0:
            customer = summary[0]
            customer_id = customer.get("customer_id")
            entity_id = customer.get("entity_id")
            
            print(f"\n--- Testing with customer: {customer.get('customer_name')} ---")
            
            # Balance
            self.test_get_balance(customer_id, entity_id)
            
            # Ledger
            self.test_get_ledger(customer_id, entity_id)
            
            # Open orders
            success_orders, orders = self.test_get_open_orders(customer_id)
            
            # Test redeem if there are open orders and balance
            balance = customer.get("balance", 0)
            if success_orders and orders and balance > 0:
                print("\n--- Testing Redeem ---")
                order = orders[0]
                redeem_amount = min(balance, order.get("outstanding", 0), 1000)
                if redeem_amount > 0:
                    self.test_redeem(customer_id, entity_id, redeem_amount,
                                   [{"order_id": order["order_id"], "amount": redeem_amount}])
                
                # Test over-redeem
                self.test_over_redeem(customer_id, entity_id)
            
            # Test adjust (small amount)
            print("\n--- Testing Adjust ---")
            self.test_adjust(customer_id, entity_id, 100, "Test adjustment +100")
            self.test_adjust(customer_id, entity_id, -50, "Test adjustment -50")
        else:
            print("\n⚠️  No store credit data found. This is expected if DB was just reseeded.")
            print("   Store credit is issued when sales returns are settled with outcome='store_credit'")

        # Summary
        print("\n" + "=" * 80)
        print(f"STORE CREDIT TEST SUMMARY")
        print("=" * 80)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        if self.tests_run > 0:
            print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        print("=" * 80)

        return self.tests_passed == self.tests_run


def main():
    tester = StoreCreditTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
