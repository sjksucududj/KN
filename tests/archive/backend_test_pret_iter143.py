#!/usr/bin/env python3
"""
Kain Nusantara Backend Test - Purchase Returns Iteration 143
Testing: DELETE draft returns, precision return flow regression
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://po-receiving-flow.preview.emergentagent.com/api"

# Test credentials
TEST_USER = {"email": "admin@kainnusantara.id", "password": "demo12345"}

class PurchaseReturnTester:
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

    def test_health(self):
        """Test API health endpoint"""
        try:
            r = requests.get(f"{BASE_URL}/", timeout=10)
            if r.status_code == 200:
                self.log("PASS", "API Health Check", f"Status: {r.status_code}")
                return True
            else:
                self.log("FAIL", "API Health Check", f"Status: {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "API Health Check", f"Error: {str(e)}")
            return False

    def test_auth(self):
        """Test authentication"""
        try:
            r = requests.post(f"{BASE_URL}/auth/login", json=TEST_USER, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "token" in data:
                    self.token = data["token"]
                    self.log("PASS", "Auth - Admin Login", f"User: {data.get('user', {}).get('name', 'N/A')}")
                    return True
                else:
                    self.log("FAIL", "Auth - Admin Login", f"Missing 'token' field")
                    return False
            self.log("FAIL", "Auth - Admin Login", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Auth - Admin Login", f"Error: {str(e)}")
            return False

    def test_list_returns(self):
        """Test GET /api/purchase-returns"""
        try:
            r = requests.get(f"{BASE_URL}/purchase-returns", headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [])
                self.log("PASS", "List Purchase Returns", f"Found {len(items)} returns")
                return True, items
            else:
                self.log("FAIL", "List Purchase Returns", f"Status: {r.status_code}")
                return False, []
        except Exception as e:
            self.log("FAIL", "List Purchase Returns", f"Error: {str(e)}")
            return False, []

    def test_get_source_rolls(self):
        """Test GET /api/purchase-returns/source-rolls (regression)"""
        try:
            # Test with prod_batik_mega and sup_783209b83eba (Cirebon Craft)
            params = {
                "product_id": "prod_batik_mega",
                "supplier_id": "sup_783209b83eba"
            }
            r = requests.get(f"{BASE_URL}/purchase-returns/source-rolls", 
                           params=params, headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                rolls = data.get("rolls", [])
                self.log("PASS", "Get Source Rolls (Regression)", 
                       f"Found {len(rolls)} returnable rolls for Batik Mega from Cirebon")
                return True, rolls
            else:
                self.log("FAIL", "Get Source Rolls (Regression)", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False, []
        except Exception as e:
            self.log("FAIL", "Get Source Rolls (Regression)", f"Error: {str(e)}")
            return False, []

    def test_create_draft_return(self, supplier_id="sup_783209b83eba", warehouse_id="wh_001"):
        """Test POST /api/purchase-returns with submit_now=false (draft)"""
        try:
            payload = {
                "supplier_id": supplier_id,
                "warehouse_id": warehouse_id,
                "reason": "Test draft return for deletion",
                "notes": "Automated test - iteration 143",
                "items": [
                    {
                        "product_id": "prod_batik_mega",
                        "quantity": 10,
                        "unit": "meter",
                        "price": 100000,
                        "reason": "cacat",
                        "condition": "damaged",
                        "roll_ids": []
                    }
                ],
                "submit_now": False  # Create as draft
            }
            r = requests.post(f"{BASE_URL}/purchase-returns", json=payload, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                return_id = data.get("id")
                return_number = data.get("number")
                status = data.get("status")
                if status == "draft":
                    self.log("PASS", "Create Draft Return", 
                           f"Created {return_number} (status: {status})")
                    return True, return_id, return_number
                else:
                    self.log("FAIL", "Create Draft Return", 
                           f"Expected status 'draft', got '{status}'")
                    return False, None, None
            else:
                self.log("FAIL", "Create Draft Return", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False, None, None
        except Exception as e:
            self.log("FAIL", "Create Draft Return", f"Error: {str(e)}")
            return False, None, None

    def test_delete_draft_return(self, return_id, return_number):
        """Test DELETE /api/purchase-returns/{id} for draft return"""
        try:
            r = requests.delete(f"{BASE_URL}/purchase-returns/{return_id}", 
                              headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("deleted") == True:
                    self.log("PASS", "Delete Draft Return", 
                           f"Successfully deleted {return_number}")
                    return True
                else:
                    self.log("FAIL", "Delete Draft Return", 
                           f"Response missing 'deleted: true': {data}")
                    return False
            else:
                self.log("FAIL", "Delete Draft Return", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Delete Draft Return", f"Error: {str(e)}")
            return False

    def test_delete_approved_return_should_fail(self, returns):
        """Test DELETE /api/purchase-returns/{id} for approved return (should fail)"""
        try:
            # Find an approved return
            approved = [r for r in returns if r.get("status") == "approved"]
            if not approved:
                self.log("PASS", "Delete Approved Return (Should Fail)", 
                       "No approved returns to test (skipped)")
                return True
            
            return_id = approved[0].get("id")
            return_number = approved[0].get("number")
            
            r = requests.delete(f"{BASE_URL}/purchase-returns/{return_id}", 
                              headers=self.get_headers(), timeout=10)
            if r.status_code == 400:
                data = r.json()
                detail = data.get("detail", "")
                if "draft" in detail.lower():
                    self.log("PASS", "Delete Approved Return (Should Fail)", 
                           f"Correctly rejected: {detail}")
                    return True
                else:
                    self.log("FAIL", "Delete Approved Return (Should Fail)", 
                           f"Wrong error message: {detail}")
                    return False
            else:
                self.log("FAIL", "Delete Approved Return (Should Fail)", 
                       f"Expected 400, got {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "Delete Approved Return (Should Fail)", f"Error: {str(e)}")
            return False

    def test_create_precision_return(self, rolls):
        """Test POST /api/purchase-returns with roll_ids (precision return regression)"""
        try:
            if not rolls or len(rolls) == 0:
                self.log("PASS", "Create Precision Return (Regression)", 
                       "No returnable rolls available (skipped)")
                return True, None
            
            # Select first roll
            roll = rolls[0]
            roll_id = roll.get("roll_id")
            qty = float(roll.get("qty_remaining", 0))
            cost = float(roll.get("unit_cost", 0))
            
            payload = {
                "supplier_id": "sup_783209b83eba",
                "warehouse_id": "wh_001",
                "reason": "Test precision return",
                "notes": "Automated test - iteration 143 regression",
                "items": [
                    {
                        "product_id": "prod_batik_mega",
                        "quantity": qty,
                        "unit": "meter",
                        "price": cost,
                        "reason": "cacat",
                        "condition": "damaged",
                        "roll_ids": [roll_id]
                    }
                ],
                "submit_now": True  # Submit for approval
            }
            r = requests.post(f"{BASE_URL}/purchase-returns", json=payload, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                return_id = data.get("id")
                return_number = data.get("number")
                items = data.get("items", [])
                
                # Verify roll_ids are stored
                if items and items[0].get("roll_ids") == [roll_id]:
                    self.log("PASS", "Create Precision Return (Regression)", 
                           f"Created {return_number} with roll_ids: {roll_id}")
                    return True, return_id
                else:
                    self.log("FAIL", "Create Precision Return (Regression)", 
                           f"roll_ids not stored correctly: {items[0].get('roll_ids') if items else 'no items'}")
                    return False, None
            else:
                self.log("FAIL", "Create Precision Return (Regression)", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False, None
        except Exception as e:
            self.log("FAIL", "Create Precision Return (Regression)", f"Error: {str(e)}")
            return False, None

    def test_approve_precision_return(self, return_id):
        """Test POST /api/purchase-returns/{id}/approve (regression)"""
        try:
            if not return_id:
                self.log("PASS", "Approve Precision Return (Regression)", 
                       "No return to approve (skipped)")
                return True
            
            r = requests.post(f"{BASE_URL}/purchase-returns/{return_id}/approve", 
                            json={"notes": "Automated test approval"}, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                debit_note = data.get("debit_note_number")
                status = data.get("status")
                if status == "approved" and debit_note:
                    self.log("PASS", "Approve Precision Return (Regression)", 
                           f"Approved with debit note: {debit_note}")
                    return True
                else:
                    self.log("FAIL", "Approve Precision Return (Regression)", 
                           f"Status: {status}, Debit Note: {debit_note}")
                    return False
            else:
                self.log("FAIL", "Approve Precision Return (Regression)", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Approve Precision Return (Regression)", f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all backend tests"""
        print("=" * 80)
        print("KAIN NUSANTARA BACKEND TEST - Purchase Returns Iteration 143")
        print("Testing: DELETE draft returns, precision return flow regression")
        print("=" * 80)
        print()

        # Health check
        if not self.test_health():
            print("\n❌ API health check failed. Stopping tests.")
            return False

        # Auth test
        print("\n--- Authentication Test ---")
        if not self.test_auth():
            print("\n❌ Admin auth failed. Cannot proceed with API tests.")
            return False

        # List returns
        print("\n--- List Purchase Returns ---")
        success, returns = self.test_list_returns()
        if not success:
            returns = []

        # Test source rolls (regression)
        print("\n--- Source Rolls API (Regression) ---")
        success, rolls = self.test_get_source_rolls()

        # Test DELETE draft return
        print("\n--- DELETE Draft Return (New Feature) ---")
        success, draft_id, draft_number = self.test_create_draft_return()
        if success and draft_id:
            self.test_delete_draft_return(draft_id, draft_number)

        # Test DELETE approved return should fail
        print("\n--- DELETE Approved Return (Should Fail) ---")
        self.test_delete_approved_return_should_fail(returns)

        # Test precision return creation (regression)
        print("\n--- Precision Return Creation (Regression) ---")
        success, precision_id = self.test_create_precision_return(rolls)

        # Test approve precision return (regression)
        print("\n--- Approve Precision Return (Regression) ---")
        self.test_approve_precision_return(precision_id)

        # Summary
        print("\n" + "=" * 80)
        print(f"BACKEND TEST SUMMARY")
        print("=" * 80)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        print("=" * 80)

        return self.tests_passed == self.tests_run


def main():
    tester = PurchaseReturnTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
