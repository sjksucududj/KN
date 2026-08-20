"""
Backend API Testing for Blanket/Contract PO Feature (P2)
Tests the 5 business rules through public endpoint
"""
import requests
import sys
from datetime import date, timedelta

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

class BlanketPOTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.token = None
        self.failures = []
        self.created_ids = {"products": [], "pos": []}

    def log(self, message: str, level: str = "INFO"):
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "•")
        print(f"{prefix} {message}")

    def test(self, name: str, expected_status: int, method: str = "GET", 
             endpoint: str = "", data: dict = None) -> tuple[bool, dict]:
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.log(f"Test #{self.tests_run}: {name}", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            response_data = {}
            try:
                response_data = response.json()
            except:
                pass

            if success:
                self.tests_passed += 1
                self.log(f"  PASSED (status: {response.status_code})", "PASS")
            else:
                self.log(f"  FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                if response_data:
                    detail = response_data.get('detail', str(response_data)[:200])
                    self.log(f"  Response: {detail}", "FAIL")
                self.failures.append(f"{name}: Expected {expected_status}, got {response.status_code}")
                self.tests_failed += 1

            return success, response_data

        except Exception as e:
            self.log(f"  FAILED - Error: {str(e)}", "FAIL")
            self.failures.append(f"{name}: {str(e)}")
            self.tests_failed += 1
            return False, {}

    def login(self, email: str = "admin@kainnusantara.id", password: str = "demo12345"):
        """Login and get token"""
        self.log(f"Logging in as {email}...", "INFO")
        success, data = self.test(
            f"Login {email}",
            200,
            "POST",
            "auth/login",
            {"email": email, "password": password}
        )
        if success and 'token' in data:
            self.token = data['token']
            self.log(f"  Token obtained", "PASS")
            return True
        self.log(f"  Login failed", "FAIL")
        return False

    def run_tests(self):
        """Run all Blanket PO tests"""
        print("\n" + "="*70)
        print("BLANKET / CONTRACT PO API TESTS (P2)")
        print("="*70 + "\n")

        # Login
        if not self.login():
            self.log("Cannot proceed without login", "FAIL")
            return False

        # Get warehouses and products
        self.log("\n--- Setup: Get Master Data ---", "INFO")
        success, wh_data = self.test("Get Warehouses", 200, "GET", "warehouses")
        if not success or not wh_data:
            self.log("No warehouses available", "FAIL")
            return False
        warehouse_id = wh_data[0]["id"]
        self.log(f"Using warehouse: {wh_data[0].get('name', 'N/A')}", "INFO")

        success, prod_data = self.test("Get Products", 200, "GET", "products")
        if not success or len(prod_data) < 2:
            self.log("Need at least 2 products", "FAIL")
            return False
        product_a = prod_data[0]
        product_b = prod_data[1]
        self.log(f"Using products: {product_a.get('sku', 'N/A')}, {product_b.get('sku', 'N/A')}", "INFO")

        # Test 1: Create Blanket PO (Rule 1.c - qty + value cap)
        self.log("\n--- Test 1: Create Blanket Contract (Rule 1.c) ---", "INFO")
        blanket_payload = {
            "supplier_name": "PT Supplier Test Blanket",
            "warehouse_id": warehouse_id,
            "items": [
                {"product_id": product_a["id"], "contract_qty": 1000, "contract_price": 50000},
                {"product_id": product_b["id"], "contract_qty": 500, "contract_price": 40000}
            ],
            "contract_value_cap": 0,  # Auto-calculate
            "valid_from": date.today().isoformat(),
            "valid_until": (date.today() + timedelta(days=90)).isoformat(),
            "notes": "Test contract"
        }
        success, blanket = self.test(
            "Create Blanket PO",
            200,
            "POST",
            "purchase-orders/blanket",
            blanket_payload
        )
        if not success or not blanket.get("id"):
            self.log("Cannot proceed without blanket contract", "FAIL")
            return False
        
        blanket_id = blanket["id"]
        self.created_ids["pos"].append(blanket_id)
        self.log(f"Blanket PO created: {blanket.get('po_number', 'N/A')}", "PASS")

        # Verify blanket properties
        if blanket.get("po_type") != "blanket":
            self.log(f"  Wrong po_type: {blanket.get('po_type')}", "FAIL")
            self.tests_failed += 1
        if blanket.get("status") != "active":
            self.log(f"  Wrong status: {blanket.get('status')}", "FAIL")
            self.tests_failed += 1

        # Test 2: Get Blanket List
        self.log("\n--- Test 2: List Blanket Contracts ---", "INFO")
        success, blanket_list = self.test("GET /purchase-orders/blanket", 200, "GET", "purchase-orders/blanket")
        if success:
            found = any(b["id"] == blanket_id for b in blanket_list)
            if found:
                self.log("  Blanket found in list", "PASS")
            else:
                self.log("  Blanket NOT found in list", "FAIL")
                self.tests_failed += 1

        # Test 3: Get Blanket Detail with Drawdown
        self.log("\n--- Test 3: Get Blanket Detail (Drawdown) ---", "INFO")
        success, detail = self.test(
            f"GET /purchase-orders/{blanket_id}",
            200,
            "GET",
            f"purchase-orders/{blanket_id}"
        )
        if success:
            # Check drawdown fields
            if "value_called" not in detail:
                self.log("  Missing value_called field", "FAIL")
                self.tests_failed += 1
            elif detail["value_called"] != 0:
                self.log(f"  Initial value_called should be 0, got {detail['value_called']}", "FAIL")
                self.tests_failed += 1
            
            if "value_remaining" not in detail:
                self.log("  Missing value_remaining field", "FAIL")
                self.tests_failed += 1
            
            if "contract_items" not in detail:
                self.log("  Missing contract_items field", "FAIL")
                self.tests_failed += 1

        # Test 4: Create Normal Call-off (Rule 2.a)
        self.log("\n--- Test 4: Create Normal Call-off (Rule 2.a) ---", "INFO")
        calloff_payload = {
            "items": [
                {"product_id": product_a["id"], "quantity": 100, "price": 50000}
            ],
            "warehouse_id": warehouse_id,
            "notes": "Test call-off"
        }
        success, calloff = self.test(
            "Create Call-off",
            200,
            "POST",
            f"purchase-orders/{blanket_id}/call-off",
            calloff_payload
        )
        if success and calloff.get("id"):
            self.created_ids["pos"].append(calloff["id"])
            self.log(f"Call-off created: {calloff.get('po_number', 'N/A')}", "PASS")
            
            # Verify call-off properties
            if calloff.get("po_type") != "call_off":
                self.log(f"  Wrong po_type: {calloff.get('po_type')}", "FAIL")
                self.tests_failed += 1
            if calloff.get("parent_po_id") != blanket_id:
                self.log(f"  Wrong parent_po_id", "FAIL")
                self.tests_failed += 1

        # Test 5: Price Override without Reason (Rule 3.b - should fail)
        self.log("\n--- Test 5: Price Override without Reason (Rule 3.b) ---", "INFO")
        override_payload = {
            "items": [
                {"product_id": product_b["id"], "quantity": 50, "price": 45000}  # Different price
            ],
            "warehouse_id": warehouse_id
        }
        success, _ = self.test(
            "Call-off with price override (no reason) - should fail",
            400,
            "POST",
            f"purchase-orders/{blanket_id}/call-off",
            override_payload
        )

        # Test 6: Price Override with Reason (Rule 3.b - should succeed)
        self.log("\n--- Test 6: Price Override with Reason (Rule 3.b) ---", "INFO")
        override_payload["price_override_reason"] = "Harga spot naik"
        success, calloff2 = self.test(
            "Call-off with price override (with reason)",
            200,
            "POST",
            f"purchase-orders/{blanket_id}/call-off",
            override_payload
        )
        if success and calloff2.get("id"):
            self.created_ids["pos"].append(calloff2["id"])

        # Test 7: Over-call (Rule 4.b)
        self.log("\n--- Test 7: Over-call Forces Approval (Rule 4.b) ---", "INFO")
        # Get current remaining
        success, detail = self.test(
            "Get updated blanket detail",
            200,
            "GET",
            f"purchase-orders/{blanket_id}"
        )
        if success and detail.get("contract_items"):
            item_a = next((i for i in detail["contract_items"] if i["product_id"] == product_a["id"]), None)
            if item_a:
                remaining = item_a.get("remaining_qty", 0)
                overcall_qty = remaining + 100  # Exceed by 100
                
                overcall_payload = {
                    "items": [
                        {"product_id": product_a["id"], "quantity": overcall_qty, "price": 50000}
                    ],
                    "warehouse_id": warehouse_id
                }
                success, overcall = self.test(
                    "Over-call (exceeds remaining)",
                    200,
                    "POST",
                    f"purchase-orders/{blanket_id}/call-off",
                    overcall_payload
                )
                if success and overcall.get("id"):
                    self.created_ids["pos"].append(overcall["id"])
                    # Should force approval
                    if overcall.get("status") != "waiting_approval":
                        self.log(f"  Over-call should force approval, got status: {overcall.get('status')}", "FAIL")
                        self.tests_failed += 1
                    else:
                        self.log("  Over-call correctly forced approval", "PASS")

        # Test 8: Close Contract (Rule 5.a)
        self.log("\n--- Test 8: Close Contract (Rule 5.a) ---", "INFO")
        
        # Create a new contract to close
        blanket2_payload = {
            "supplier_name": "PT Supplier Test Close",
            "warehouse_id": warehouse_id,
            "items": [
                {"product_id": product_a["id"], "contract_qty": 100, "contract_price": 50000}
            ],
            "contract_value_cap": 0,
            "notes": "Test contract for closing"
        }
        success, blanket2 = self.test(
            "Create second blanket for close test",
            200,
            "POST",
            "purchase-orders/blanket",
            blanket2_payload
        )
        if success and blanket2.get("id"):
            blanket2_id = blanket2["id"]
            self.created_ids["pos"].append(blanket2_id)
            
            # Close it
            close_payload = {"reason": "Test closing contract"}
            success, _ = self.test(
                "Close contract",
                200,
                "POST",
                f"purchase-orders/{blanket2_id}/close-contract",
                close_payload
            )
            
            # Try to create call-off on closed contract (should fail)
            calloff_closed_payload = {
                "items": [
                    {"product_id": product_a["id"], "quantity": 10, "price": 50000}
                ],
                "warehouse_id": warehouse_id
            }
            success, _ = self.test(
                "Call-off on closed contract - should fail",
                400,
                "POST",
                f"purchase-orders/{blanket2_id}/call-off",
                calloff_closed_payload
            )

        # Test 9: Verify Separation (blanket not in standard PO list)
        self.log("\n--- Test 9: Verify List Separation ---", "INFO")
        success, std_pos = self.test("GET /purchase-orders (standard)", 200, "GET", "purchase-orders")
        if success:
            blanket_in_std = any(po["id"] == blanket_id for po in std_pos)
            if blanket_in_std:
                self.log("  ERROR: Blanket PO should NOT appear in standard PO list", "FAIL")
                self.tests_failed += 1
            else:
                self.log("  Blanket correctly excluded from standard PO list", "PASS")
            
            # Call-offs should appear in standard list
            if calloff.get("id"):
                calloff_in_std = any(po["id"] == calloff["id"] for po in std_pos)
                if calloff_in_std:
                    self.log("  Call-off correctly appears in standard PO list", "PASS")
                else:
                    self.log("  WARNING: Call-off should appear in standard PO list", "WARN")

        return True

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed} ✅")
        print(f"Failed: {self.tests_failed} ❌")
        
        if self.failures:
            print("\nFailed Tests:")
            for failure in self.failures:
                print(f"  • {failure}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"\nSuccess Rate: {success_rate:.1f}%")
        print("="*70 + "\n")
        
        return self.tests_failed == 0

def main():
    tester = BlanketPOTester()
    try:
        tester.run_tests()
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        success = tester.print_summary()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
