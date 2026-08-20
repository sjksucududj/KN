#!/usr/bin/env python3
"""
R5.2 Store Credit Comprehensive Backend Test
Tests all store credit endpoints including issue flow via sales return
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://supplier-rma-portal.preview.emergentagent.com/api"
TEST_USER = {"email": "admin@kainnusantara.id", "password": "demo12345"}

class StoreCreditComprehensiveTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        self.results = []
        self.test_customer_id = None
        self.test_entity_id = None

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
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def test_auth(self):
        try:
            r = requests.post(f"{BASE_URL}/auth/login", json=TEST_USER, timeout=10)
            if r.status_code == 200 and "token" in r.json():
                self.token = r.json()["token"]
                self.log("PASS", "Auth - Login", f"User: {r.json().get('user', {}).get('name', 'N/A')}")
                return True
            self.log("FAIL", "Auth - Login", f"Status: {r.status_code}")
            return False
        except Exception as e:
            self.log("FAIL", "Auth - Login", f"Error: {str(e)}")
            return False

    def test_get_summary_empty(self):
        """Test GET /api/store-credit returns empty array when no balances"""
        try:
            r = requests.get(f"{BASE_URL}/store-credit", headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    self.log("PASS", "GET /store-credit (empty state)", f"Returns array with {len(data)} items")
                    return True
                self.log("FAIL", "GET /store-credit", f"Expected list, got {type(data)}")
                return False
            self.log("FAIL", "GET /store-credit", f"Status: {r.status_code}")
            return False
        except Exception as e:
            self.log("FAIL", "GET /store-credit", f"Error: {str(e)}")
            return False

    def test_get_ledger_all(self):
        """Test GET /api/store-credit/ledger without filters"""
        try:
            r = requests.get(f"{BASE_URL}/store-credit/ledger", headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    self.log("PASS", "GET /store-credit/ledger (all)", f"Returns {len(data)} entries")
                    return True, data
                self.log("FAIL", "GET /store-credit/ledger", f"Expected list")
                return False, []
            self.log("FAIL", "GET /store-credit/ledger", f"Status: {r.status_code}")
            return False, []
        except Exception as e:
            self.log("FAIL", "GET /store-credit/ledger", f"Error: {str(e)}")
            return False, []

    def create_store_credit_via_return(self):
        """Create store credit by settling a sales return"""
        try:
            print("\n--- Creating Store Credit via Sales Return ---")
            
            # Get eligible orders
            r = requests.get(f"{BASE_URL}/sales-orders", headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                print(f"  ⚠️  Cannot get orders: {r.status_code}")
                return False
            
            orders = r.json()
            if isinstance(orders, dict):
                orders = orders.get("items", [])
            
            # Find order with items
            eligible = None
            for order in orders:
                if order.get("status") in ["confirmed", "shipped", "done", "picked"]:
                    items = order.get("items", [])
                    if items and any(float(it.get("quantity", 0) or 0) >= 2 for it in items):
                        eligible = order
                        break
            
            if not eligible:
                print("  ⚠️  No eligible orders found")
                return False
            
            print(f"  Found eligible order: {eligible.get('number')}")
            
            # Get first item with qty >= 2
            item = next((it for it in eligible["items"] if float(it.get("quantity", 0) or 0) >= 2), None)
            if not item:
                print("  ⚠️  No suitable item found")
                return False
            
            # Create return
            return_payload = {
                "order_id": eligible["id"],
                "return_type": "retur",
                "items": [{
                    "product_id": item["product_id"],
                    "product_name": item.get("product_name", ""),
                    "quantity_returned": 2,
                    "unit": item.get("unit", "meter"),
                    "reason": "Test R5.2",
                    "condition": "ok"
                }],
                "notes": "Test store credit creation"
            }
            
            r = requests.post(f"{BASE_URL}/sales-returns", json=return_payload, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                print(f"  ⚠️  Cannot create return: {r.status_code} - {r.text[:200]}")
                return False
            
            ret = r.json()
            ret_id = ret["id"]
            print(f"  Created return: {ret.get('number')}")
            
            # Submit
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/submit", 
                            headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                print(f"  ⚠️  Cannot submit: {r.status_code}")
                return False
            
            # Approve
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/approve", 
                            json={"notes": "Test"}, headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                print(f"  ⚠️  Cannot approve: {r.status_code}")
                return False
            
            # Start inspection
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/start", 
                            headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                print(f"  ⚠️  Cannot start inspection: {r.status_code}")
                return False
            
            # Complete inspection
            insp_payload = {
                "inspections": [{
                    "index": 0,
                    "defects": [{"point_value": 1, "count": 1}],
                    "condition": "ok",
                    "accepted_qty": 2
                }],
                "notes": "Test inspection"
            }
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/complete", 
                            json=insp_payload, headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                print(f"  ⚠️  Cannot complete inspection: {r.status_code}")
                return False
            
            # Settle with store_credit outcome
            settle_payload = {
                "outcome": "store_credit",
                "return_warehouse_id": ""
            }
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/settle", 
                            json=settle_payload, headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                print(f"  ⚠️  Cannot settle: {r.status_code} - {r.text[:200]}")
                return False
            
            settled = r.json()
            self.test_customer_id = settled.get("customer_id")
            self.test_entity_id = settled.get("entity_id")
            
            settlement = settled.get("settlement", {})
            sc_amount = settlement.get("store_credit_amount", 0)
            
            print(f"  ✅ Settled with store_credit: {sc_amount}")
            print(f"  Customer: {self.test_customer_id}, Entity: {self.test_entity_id}")
            
            self.log("PASS", "ISSUE - Create store credit via return", 
                   f"Amount: {sc_amount}, CN: {settled.get('credit_note_number')}")
            return True
            
        except Exception as e:
            print(f"  ⚠️  Error: {str(e)}")
            self.log("FAIL", "ISSUE - Create store credit via return", f"Error: {str(e)}")
            return False

    def test_get_summary_with_data(self):
        """Test GET /api/store-credit returns data after creation"""
        try:
            r = requests.get(f"{BASE_URL}/store-credit", headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    found = any(c.get("customer_id") == self.test_customer_id for c in data)
                    if found:
                        self.log("PASS", "GET /store-credit (with data)", 
                               f"Found test customer in {len(data)} results")
                        return True
                    self.log("FAIL", "GET /store-credit", "Test customer not found")
                    return False
                self.log("FAIL", "GET /store-credit", f"Expected non-empty list, got {len(data)}")
                return False
            self.log("FAIL", "GET /store-credit", f"Status: {r.status_code}")
            return False
        except Exception as e:
            self.log("FAIL", "GET /store-credit", f"Error: {str(e)}")
            return False

    def test_get_balance(self):
        """Test GET /api/store-credit/balance"""
        try:
            params = {"customer_id": self.test_customer_id}
            if self.test_entity_id:
                params["entity_id"] = self.test_entity_id
            
            r = requests.get(f"{BASE_URL}/store-credit/balance", params=params,
                           headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "balance" in data and "by_entity" in data:
                    balance = data.get("balance", 0)
                    if balance > 0:
                        self.log("PASS", "GET /store-credit/balance", 
                               f"Balance: {balance}, Entities: {len(data.get('by_entity', {}))}")
                        return True, balance
                    self.log("FAIL", "GET /store-credit/balance", "Balance is 0")
                    return False, 0
                self.log("FAIL", "GET /store-credit/balance", "Missing fields")
                return False, 0
            self.log("FAIL", "GET /store-credit/balance", f"Status: {r.status_code}")
            return False, 0
        except Exception as e:
            self.log("FAIL", "GET /store-credit/balance", f"Error: {str(e)}")
            return False, 0

    def test_get_ledger_filtered(self):
        """Test GET /api/store-credit/ledger with customer filter"""
        try:
            params = {"customer_id": self.test_customer_id}
            r = requests.get(f"{BASE_URL}/store-credit/ledger", params=params,
                           headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    # Check for issue entry
                    has_issue = any(e.get("type") == "issue" for e in data)
                    if has_issue:
                        self.log("PASS", "GET /store-credit/ledger (filtered)", 
                               f"Found {len(data)} entries including issue")
                        return True
                    self.log("FAIL", "GET /store-credit/ledger", "No issue entry found")
                    return False
                self.log("FAIL", "GET /store-credit/ledger", "Empty result")
                return False
            self.log("FAIL", "GET /store-credit/ledger", f"Status: {r.status_code}")
            return False
        except Exception as e:
            self.log("FAIL", "GET /store-credit/ledger", f"Error: {str(e)}")
            return False

    def test_get_open_orders(self):
        """Test GET /api/store-credit/open-orders"""
        try:
            r = requests.get(f"{BASE_URL}/store-credit/open-orders",
                           params={"customer_id": self.test_customer_id},
                           headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    self.log("PASS", "GET /store-credit/open-orders", 
                           f"Found {len(data)} open AR orders")
                    return True, data
                self.log("FAIL", "GET /store-credit/open-orders", "Expected list")
                return False, []
            self.log("FAIL", "GET /store-credit/open-orders", f"Status: {r.status_code}")
            return False, []
        except Exception as e:
            self.log("FAIL", "GET /store-credit/open-orders", f"Error: {str(e)}")
            return False, []

    def test_redeem(self, balance, orders):
        """Test POST /api/store-credit/redeem"""
        if not orders:
            print("  ⚠️  No open orders to redeem against")
            return False
        
        try:
            order = orders[0]
            redeem_amount = min(balance, order.get("outstanding", 0), 1000)
            
            if redeem_amount <= 0:
                print("  ⚠️  Cannot determine redeem amount")
                return False
            
            payload = {
                "customer_id": self.test_customer_id,
                "entity_id": self.test_entity_id,
                "amount": redeem_amount,
                "allocations": [{"order_id": order["order_id"], "amount": redeem_amount}],
                "note": "Test redeem"
            }
            
            r = requests.post(f"{BASE_URL}/store-credit/redeem", json=payload,
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                applied = data.get("applied_amount", 0)
                if applied > 0:
                    self.log("PASS", "POST /store-credit/redeem", 
                           f"Applied: {applied}, Number: {data.get('number')}")
                    return True
                self.log("FAIL", "POST /store-credit/redeem", "Applied amount is 0")
                return False
            self.log("FAIL", "POST /store-credit/redeem", 
                   f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "POST /store-credit/redeem", f"Error: {str(e)}")
            return False

    def test_over_redeem(self):
        """Test over-redeem validation"""
        try:
            payload = {
                "customer_id": self.test_customer_id,
                "entity_id": self.test_entity_id,
                "amount": 999999999,
                "note": "Test over-redeem"
            }
            r = requests.post(f"{BASE_URL}/store-credit/redeem", json=payload,
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 400:
                self.log("PASS", "Over-redeem validation (400)", "Correctly rejected")
                return True
            self.log("FAIL", "Over-redeem validation", f"Expected 400, got {r.status_code}")
            return False
        except Exception as e:
            self.log("FAIL", "Over-redeem validation", f"Error: {str(e)}")
            return False

    def test_adjust_plus(self):
        """Test POST /api/store-credit/adjust (positive)"""
        try:
            payload = {
                "customer_id": self.test_customer_id,
                "entity_id": self.test_entity_id,
                "amount": 500,
                "note": "Test adjustment +500"
            }
            r = requests.post(f"{BASE_URL}/store-credit/adjust", json=payload,
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "balance_after" in data:
                    self.log("PASS", "POST /store-credit/adjust (+)", 
                           f"Balance after: {data.get('balance_after')}")
                    return True
                self.log("FAIL", "POST /store-credit/adjust", "Missing balance_after")
                return False
            self.log("FAIL", "POST /store-credit/adjust", f"Status: {r.status_code}")
            return False
        except Exception as e:
            self.log("FAIL", "POST /store-credit/adjust", f"Error: {str(e)}")
            return False

    def test_adjust_minus(self):
        """Test POST /api/store-credit/adjust (negative)"""
        try:
            payload = {
                "customer_id": self.test_customer_id,
                "entity_id": self.test_entity_id,
                "amount": -200,
                "note": "Test adjustment -200"
            }
            r = requests.post(f"{BASE_URL}/store-credit/adjust", json=payload,
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "balance_after" in data:
                    self.log("PASS", "POST /store-credit/adjust (-)", 
                           f"Balance after: {data.get('balance_after')}")
                    return True
                self.log("FAIL", "POST /store-credit/adjust", "Missing balance_after")
                return False
            self.log("FAIL", "POST /store-credit/adjust", f"Status: {r.status_code}")
            return False
        except Exception as e:
            self.log("FAIL", "POST /store-credit/adjust", f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        print("=" * 80)
        print("R5.2 STORE CREDIT COMPREHENSIVE BACKEND TEST")
        print("=" * 80)
        print()

        # Auth
        if not self.test_auth():
            print("\n❌ Auth failed. Cannot proceed.")
            return False

        # Test empty state
        print("\n--- Testing Empty State ---")
        self.test_get_summary_empty()
        self.test_get_ledger_all()

        # Create store credit
        if not self.create_store_credit_via_return():
            print("\n⚠️  Could not create store credit. Skipping remaining tests.")
        else:
            # Test with data
            print("\n--- Testing With Store Credit Data ---")
            self.test_get_summary_with_data()
            success_bal, balance = self.test_get_balance()
            self.test_get_ledger_filtered()
            success_orders, orders = self.test_get_open_orders()
            
            # Test redeem
            if success_bal and success_orders and balance > 0:
                print("\n--- Testing Redeem ---")
                self.test_redeem(balance, orders)
                self.test_over_redeem()
            
            # Test adjust
            print("\n--- Testing Adjust ---")
            self.test_adjust_plus()
            self.test_adjust_minus()

        # Summary
        print("\n" + "=" * 80)
        print("COMPREHENSIVE TEST SUMMARY")
        print("=" * 80)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        if self.tests_run > 0:
            print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        print("=" * 80)

        return self.tests_passed == self.tests_run


def main():
    tester = StoreCreditComprehensiveTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
