#!/usr/bin/env python3
"""
Kain Nusantara Backend Test - Purchase Returns & Product Traceability
Testing: precision purchase returns with roll picker, approval flow, 
         product purchase history (Kartu Asal), and ATP detail panel
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://po-receiving-flow.preview.emergentagent.com/api"

# Test credentials
TEST_USER = {"email": "admin@kainnusantara.id", "password": "demo12345"}

# Known test data from context
TEST_SUPPLIER_ID = "sup_783209b83eba"  # Cirebon Craft
TEST_PRODUCT_ID = "prod_batik_mega"    # Batik Mega Mendung Premium

class PurchaseReturnTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        self.results = []
        self.created_return_id = None
        self.created_return_number = None

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
                    user_name = data.get('user', {}).get('name', 'N/A')
                    user_role = data.get('user', {}).get('role', 'N/A')
                    self.log("PASS", "Auth - Login", f"User: {user_name}, Role: {user_role}")
                    return True
                else:
                    self.log("FAIL", "Auth - Login", f"Missing 'token' field")
                    return False
            self.log("FAIL", "Auth - Login", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Auth - Login", f"Error: {str(e)}")
            return False

    def test_list_purchase_returns(self):
        """Test GET /api/purchase-returns"""
        try:
            r = requests.get(f"{BASE_URL}/purchase-returns", headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [])
                total = data.get("total", 0)
                self.log("PASS", "List Purchase Returns", f"Found {total} returns")
                return True
            else:
                self.log("FAIL", "List Purchase Returns", f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "List Purchase Returns", f"Error: {str(e)}")
            return False

    def test_get_source_rolls(self):
        """Test GET /api/purchase-returns/source-rolls (for RollPickerModal)"""
        try:
            params = {
                "product_id": TEST_PRODUCT_ID,
                "supplier_id": TEST_SUPPLIER_ID
            }
            r = requests.get(f"{BASE_URL}/purchase-returns/source-rolls", 
                           params=params, headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                rolls = data.get("rolls", [])
                count = data.get("count", 0)
                total_returnable = data.get("total_returnable", 0)
                
                if count > 0:
                    self.log("PASS", "Get Source Rolls", 
                           f"Found {count} returnable rolls, total qty: {total_returnable}")
                    # Store first 2 roll IDs for creating return
                    self.returnable_rolls = rolls[:2] if len(rolls) >= 2 else rolls
                    return True
                else:
                    self.log("FAIL", "Get Source Rolls", 
                           f"No returnable rolls found for product {TEST_PRODUCT_ID} and supplier {TEST_SUPPLIER_ID}")
                    return False
            else:
                self.log("FAIL", "Get Source Rolls", f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Get Source Rolls", f"Error: {str(e)}")
            return False

    def test_create_precision_return(self):
        """Test POST /api/purchase-returns with roll_ids (precision return)"""
        if not hasattr(self, 'returnable_rolls') or not self.returnable_rolls:
            self.log("FAIL", "Create Precision Return", "No returnable rolls available")
            return False
        
        try:
            # Get warehouse and supplier info
            r_warehouses = requests.get(f"{BASE_URL}/warehouses", headers=self.get_headers(), timeout=10)
            warehouses = r_warehouses.json() if r_warehouses.status_code == 200 else []
            warehouse_id = warehouses[0]["id"] if warehouses else "wh_default"
            
            # Prepare roll_ids from returnable rolls
            roll_ids = [roll["roll_id"] for roll in self.returnable_rolls]
            total_qty = sum(roll.get("qty_remaining", 0) for roll in self.returnable_rolls)
            avg_cost = sum(roll.get("unit_cost", 0) for roll in self.returnable_rolls) / len(self.returnable_rolls)
            
            payload = {
                "supplier_id": TEST_SUPPLIER_ID,
                "warehouse_id": warehouse_id,
                "items": [
                    {
                        "product_id": TEST_PRODUCT_ID,
                        "quantity": total_qty,
                        "unit": "meter",
                        "price": avg_cost,
                        "reason": "cacat",
                        "condition": "damaged",
                        "roll_ids": roll_ids
                    }
                ],
                "reason": "Barang cacat - test precision return",
                "notes": "Test precision return with specific rolls",
                "submit_now": True
            }
            
            r = requests.post(f"{BASE_URL}/purchase-returns", json=payload, 
                            headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                self.created_return_id = data.get("id")
                self.created_return_number = data.get("number")
                status = data.get("status")
                
                # Verify roll_ids are in the response
                items = data.get("items", [])
                if items and items[0].get("roll_ids") == roll_ids:
                    self.log("PASS", "Create Precision Return", 
                           f"Created {self.created_return_number}, status: {status}, rolls: {len(roll_ids)}")
                    return True
                else:
                    self.log("FAIL", "Create Precision Return", 
                           f"Roll IDs not preserved in response")
                    return False
            else:
                self.log("FAIL", "Create Precision Return", 
                       f"Status: {r.status_code}, Body: {r.text[:300]}")
                return False
        except Exception as e:
            self.log("FAIL", "Create Precision Return", f"Error: {str(e)}")
            return False

    def test_get_return_detail(self):
        """Test GET /api/purchase-returns/{id}"""
        if not self.created_return_id:
            self.log("FAIL", "Get Return Detail", "No return ID available")
            return False
        
        try:
            r = requests.get(f"{BASE_URL}/purchase-returns/{self.created_return_id}", 
                           headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                number = data.get("number")
                status = data.get("status")
                items = data.get("items", [])
                
                self.log("PASS", "Get Return Detail", 
                       f"Retrieved {number}, status: {status}, items: {len(items)}")
                return True
            else:
                self.log("FAIL", "Get Return Detail", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Get Return Detail", f"Error: {str(e)}")
            return False

    def test_approve_return(self):
        """Test POST /api/purchase-returns/{id}/approve"""
        if not self.created_return_id:
            self.log("FAIL", "Approve Return", "No return ID available")
            return False
        
        try:
            payload = {"notes": "Approved for testing"}
            r = requests.post(f"{BASE_URL}/purchase-returns/{self.created_return_id}/approve", 
                            json=payload, headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                status = data.get("status")
                debit_note = data.get("debit_note_number")
                
                if status == "approved" and debit_note:
                    self.log("PASS", "Approve Return", 
                           f"Approved {self.created_return_number}, Debit Note: {debit_note}")
                    return True
                else:
                    self.log("FAIL", "Approve Return", 
                           f"Status: {status}, Debit Note: {debit_note}")
                    return False
            else:
                self.log("FAIL", "Approve Return", 
                       f"Status: {r.status_code}, Body: {r.text[:300]}")
                return False
        except Exception as e:
            self.log("FAIL", "Approve Return", f"Error: {str(e)}")
            return False

    def test_product_purchase_history(self):
        """Test GET /api/products/{id}/purchase-history (Kartu Asal)"""
        try:
            r = requests.get(f"{BASE_URL}/products/{TEST_PRODUCT_ID}/purchase-history", 
                           headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                product_name = data.get("product_name")
                summary = data.get("summary", {})
                events = data.get("events", [])
                
                total_received = summary.get("total_received", 0)
                total_remaining = summary.get("total_remaining", 0)
                event_count = summary.get("event_count", 0)
                supplier_count = summary.get("supplier_count", 0)
                
                if event_count > 0:
                    self.log("PASS", "Product Purchase History", 
                           f"{product_name}: {event_count} events, {supplier_count} suppliers, "
                           f"received: {total_received}, remaining: {total_remaining}")
                    return True
                else:
                    self.log("FAIL", "Product Purchase History", 
                           f"No purchase history events found for {TEST_PRODUCT_ID}")
                    return False
            else:
                self.log("FAIL", "Product Purchase History", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Product Purchase History", f"Error: {str(e)}")
            return False

    def test_atp_detail(self):
        """Test GET /api/stock/atp (ATP detail with purchase history)"""
        try:
            params = {"product_id": TEST_PRODUCT_ID}
            r = requests.get(f"{BASE_URL}/stock/atp", params=params, 
                           headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                available = data.get("available", 0)
                incoming = data.get("incoming_in_horizon", 0)
                pending = data.get("pending_total", 0)
                atp = data.get("atp_horizon", 0)
                horizon_days = data.get("horizon_days", 0)
                
                self.log("PASS", "ATP Detail", 
                       f"Available: {available}, Incoming: {incoming}, Pending: {pending}, "
                       f"ATP: {atp}, Horizon: {horizon_days} days")
                return True
            else:
                self.log("FAIL", "ATP Detail", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "ATP Detail", f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all backend tests"""
        print("=" * 80)
        print("KAIN NUSANTARA BACKEND TEST - Purchase Returns & Traceability")
        print("Testing: Precision returns, roll picker, approval, Kartu Asal, ATP")
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

        # Purchase Returns tests
        print("\n--- Purchase Returns API Tests ---")
        self.test_list_purchase_returns()
        
        # Test source rolls (for RollPickerModal)
        if self.test_get_source_rolls():
            # Create precision return with roll_ids
            if self.test_create_precision_return():
                # Get return detail
                self.test_get_return_detail()
                # Approve return
                self.test_approve_return()

        # Product Traceability tests
        print("\n--- Product Traceability API Tests ---")
        self.test_product_purchase_history()
        self.test_atp_detail()

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
