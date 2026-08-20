#!/usr/bin/env python3
"""
R2 — Returns & Refunds Backend Test (Unified Inspection + Quarantine)
Testing: 4-point inspection, grade calculation, quarantine, release/scrap
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://inventory-refund.preview.emergentagent.com/api"
TEST_USER = {"email": "admin@kainnusantara.id", "password": "demo12345"}

class R2BackendTester:
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
                    self.log("PASS", "Auth - Login", f"User: {data.get('user', {}).get('name', 'Admin')}")
                    return True
                else:
                    self.log("FAIL", "Auth - Login", f"Missing token. Keys: {list(data.keys())}")
                    return False
            self.log("FAIL", "Auth - Login", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Auth - Login", f"Error: {str(e)}")
            return False

    def get_eligible_orders(self):
        """Get eligible orders for return creation"""
        try:
            r = requests.get(f"{BASE_URL}/sales-orders", headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                orders = data if isinstance(data, list) else data.get("items", [])
                eligible = [o for o in orders if o.get("status") in 
                           {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
                           and any(float(it.get("quantity", 0) or 0) >= 1 for it in (o.get("items") or []))]
                return eligible
            return []
        except Exception as e:
            print(f"   Error getting orders: {str(e)}")
            return []

    def create_return(self, order, qty=1):
        """Create a sales return"""
        try:
            items = [it for it in order.get("items", []) if float(it.get("quantity", 0) or 0) >= qty]
            if not items:
                return None
            
            item = items[0]
            payload = {
                "order_id": order["id"],
                "return_type": "retur",
                "items": [{
                    "product_id": item["product_id"],
                    "product_name": item.get("product_name", ""),
                    "quantity_returned": qty,
                    "unit": item.get("unit", "meter"),
                    "reason": "R2 test",
                    "condition": "ok"
                }],
                "notes": "R2 backend test"
            }
            
            r = requests.post(f"{BASE_URL}/sales-returns", json=payload, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
            else:
                print(f"   Create return failed: {r.status_code}, {r.text[:200]}")
                return None
        except Exception as e:
            print(f"   Error creating return: {str(e)}")
            return None

    def test_return_lifecycle(self):
        """Test: create -> submit -> approve -> inspect/start -> inspect/complete"""
        try:
            orders = self.get_eligible_orders()
            if not orders:
                self.log("FAIL", "Return Lifecycle", "No eligible orders found")
                return None
            
            # Create
            ret = self.create_return(orders[0])
            if not ret:
                self.log("FAIL", "Return Lifecycle - Create", "Failed to create return")
                return None
            
            ret_id = ret["id"]
            self.log("PASS", "Return Lifecycle - Create", f"Created {ret['number']}")
            
            # Submit
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/submit", 
                            headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Return Lifecycle - Submit", f"Status: {r.status_code}")
                return None
            self.log("PASS", "Return Lifecycle - Submit", "Status: pending_approval")
            
            # Approve
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/approve", 
                            json={"notes": ""}, headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Return Lifecycle - Approve", f"Status: {r.status_code}")
                return None
            self.log("PASS", "Return Lifecycle - Approve", "Status: approved")
            
            # Start Inspection
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/start", 
                            headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Return Lifecycle - Start Inspect", f"Status: {r.status_code}")
                return None
            self.log("PASS", "Return Lifecycle - Start Inspect", "Status: inspecting")
            
            return ret_id
            
        except Exception as e:
            self.log("FAIL", "Return Lifecycle", f"Error: {str(e)}")
            return None

    def test_4point_inspection_grading(self):
        """Test: 4-point defect scoring and grade calculation (A/B/C)"""
        try:
            orders = self.get_eligible_orders()
            if not orders:
                self.log("FAIL", "4-Point Grading", "No eligible orders")
                return False
            
            # Use different orders for each test to avoid return limit
            if len(orders) < 3:
                orders = orders * 3  # Repeat if not enough
            
            # Test Grade C (points > 40)
            ret = self.create_return(orders[0] if len(orders) > 0 else orders[0])
            if not ret:
                self.log("FAIL", "4-Point Grading - Grade C", "Failed to create return")
                return False
            
            ret_id = ret["id"]
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/submit", headers=self.get_headers(), timeout=10)
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/approve", json={"notes": ""}, 
                         headers=self.get_headers(), timeout=10)
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/start", headers=self.get_headers(), timeout=10)
            
            # Complete inspection with 48 points (4 × 12 = 48 > 40 → Grade C)
            payload = {
                "inspections": [{
                    "index": 0,
                    "defects": [{"point_value": 4, "count": 12}],
                    "condition": "ok",
                    "accepted_qty": 1
                }],
                "notes": "Grade C test"
            }
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/complete", 
                            json=payload, headers=self.get_headers(), timeout=10)
            
            if r.status_code != 200:
                self.log("FAIL", "4-Point Grading - Grade C", f"Status: {r.status_code}, {r.text[:200]}")
                return False
            
            data = r.json()
            insp = data["items"][0].get("inspection", {})
            grade = insp.get("grade")
            points = insp.get("points")
            rec = insp.get("recommended_outcome")
            
            if grade != "C":
                self.log("FAIL", "4-Point Grading - Grade C", f"Expected C, got {grade} (points: {points})")
                return False
            
            if abs(points - 48) > 0.01:
                self.log("FAIL", "4-Point Grading - Points", f"Expected 48, got {points}")
                return False
            
            if rec != "nego":
                self.log("FAIL", "4-Point Grading - Recommendation", f"Expected nego for C, got {rec}")
                return False
            
            self.log("PASS", "4-Point Grading - Grade C", f"Points: {points}, Grade: {grade}, Rec: {rec}")
            
            # Test Grade B (21-40 points)
            ret = self.create_return(orders[1] if len(orders) > 1 else orders[0])
            if ret:
                ret_id = ret["id"]
                requests.post(f"{BASE_URL}/sales-returns/{ret_id}/submit", headers=self.get_headers(), timeout=10)
                requests.post(f"{BASE_URL}/sales-returns/{ret_id}/approve", json={"notes": ""}, 
                             headers=self.get_headers(), timeout=10)
                requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/start", headers=self.get_headers(), timeout=10)
                
                # 30 points (2 × 15 = 30, 21-40 → Grade B)
                payload = {
                    "inspections": [{
                        "index": 0,
                        "defects": [{"point_value": 2, "count": 15}],
                        "condition": "ok",
                        "accepted_qty": 1
                    }],
                    "notes": "Grade B test"
                }
                r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/complete", 
                                json=payload, headers=self.get_headers(), timeout=10)
                
                if r.status_code == 200:
                    data = r.json()
                    insp = data["items"][0].get("inspection", {})
                    if insp.get("grade") == "B" and insp.get("recommended_outcome") == "store_credit":
                        self.log("PASS", "4-Point Grading - Grade B", 
                               f"Points: {insp.get('points')}, Grade: B, Rec: store_credit")
                    else:
                        self.log("FAIL", "4-Point Grading - Grade B", 
                               f"Grade: {insp.get('grade')}, Rec: {insp.get('recommended_outcome')}")
            
            # Test Grade A (≤20 points)
            ret = self.create_return(orders[2] if len(orders) > 2 else orders[0])
            if ret:
                ret_id = ret["id"]
                requests.post(f"{BASE_URL}/sales-returns/{ret_id}/submit", headers=self.get_headers(), timeout=10)
                requests.post(f"{BASE_URL}/sales-returns/{ret_id}/approve", json={"notes": ""}, 
                             headers=self.get_headers(), timeout=10)
                requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/start", headers=self.get_headers(), timeout=10)
                
                # 5 points (1 × 5 = 5 ≤ 20 → Grade A)
                payload = {
                    "inspections": [{
                        "index": 0,
                        "defects": [{"point_value": 1, "count": 5}],
                        "condition": "ok",
                        "accepted_qty": 1
                    }],
                    "notes": "Grade A test"
                }
                r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/complete", 
                                json=payload, headers=self.get_headers(), timeout=10)
                
                if r.status_code == 200:
                    data = r.json()
                    insp = data["items"][0].get("inspection", {})
                    if insp.get("grade") == "A" and insp.get("recommended_outcome") == "refund":
                        self.log("PASS", "4-Point Grading - Grade A", 
                               f"Points: {insp.get('points')}, Grade: A, Rec: refund")
                    else:
                        self.log("FAIL", "4-Point Grading - Grade A", 
                               f"Grade: {insp.get('grade')}, Rec: {insp.get('recommended_outcome')}")
            
            return True
            
        except Exception as e:
            self.log("FAIL", "4-Point Grading", f"Error: {str(e)}")
            return False

    def test_quarantine_refund(self):
        """Test: settle refund -> rolls enter quarantine -> release to available"""
        try:
            orders = self.get_eligible_orders()
            if not orders:
                self.log("FAIL", "Quarantine Refund", "No eligible orders")
                return False
            
            # Use a different order (index 3)
            order_idx = 3 if len(orders) > 3 else 0
            
            # Create and inspect return
            ret = self.create_return(orders[order_idx])
            if not ret:
                self.log("FAIL", "Quarantine Refund", "Failed to create return")
                return False
            
            ret_id = ret["id"]
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/submit", headers=self.get_headers(), timeout=10)
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/approve", json={"notes": ""}, 
                         headers=self.get_headers(), timeout=10)
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/start", headers=self.get_headers(), timeout=10)
            
            # Complete inspection (Grade A)
            payload = {
                "inspections": [{
                    "index": 0,
                    "defects": [{"point_value": 1, "count": 2}],
                    "condition": "ok",
                    "accepted_qty": 1
                }],
                "notes": "Quarantine test"
            }
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/complete", 
                         json=payload, headers=self.get_headers(), timeout=10)
            
            # Settle with refund outcome
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/settle", 
                            json={"outcome": "refund"}, headers=self.get_headers(), timeout=10)
            
            if r.status_code != 200:
                self.log("FAIL", "Quarantine Refund - Settle", f"Status: {r.status_code}, {r.text[:200]}")
                return False
            
            data = r.json()
            if data.get("status") != "refund_settled":
                self.log("FAIL", "Quarantine Refund - Status", f"Expected refund_settled, got {data.get('status')}")
                return False
            
            self.log("PASS", "Quarantine Refund - Settle", "Status: refund_settled")
            
            # Get quarantine rolls
            r = requests.get(f"{BASE_URL}/sales-returns/{ret_id}/quarantine", 
                           headers=self.get_headers(), timeout=10)
            
            if r.status_code != 200:
                self.log("FAIL", "Quarantine Refund - List", f"Status: {r.status_code}")
                return False
            
            rolls = r.json()
            if not isinstance(rolls, list) or len(rolls) == 0:
                self.log("FAIL", "Quarantine Refund - Rolls", f"Expected array with rolls, got: {rolls}")
                return False
            
            # Check all rolls are in quarantine status
            quarantine_rolls = [r for r in rolls if r.get("status") == "quarantine"]
            if len(quarantine_rolls) == 0:
                self.log("FAIL", "Quarantine Refund - Status", 
                       f"No quarantine rolls. Statuses: {[r.get('status') for r in rolls]}")
                return False
            
            self.log("PASS", "Quarantine Refund - Rolls in Quarantine", 
                   f"Found {len(quarantine_rolls)} roll(s) with status=quarantine")
            
            # Release quarantine (all rolls to available)
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/quarantine/release", 
                            json={"decisions": [], "notes": "Release all"}, 
                            headers=self.get_headers(), timeout=10)
            
            if r.status_code != 200:
                self.log("FAIL", "Quarantine Refund - Release", f"Status: {r.status_code}, {r.text[:200]}")
                return False
            
            # Verify rolls are now available
            r = requests.get(f"{BASE_URL}/sales-returns/{ret_id}/quarantine", 
                           headers=self.get_headers(), timeout=10)
            rolls = r.json()
            available_rolls = [r for r in rolls if r.get("status") == "available"]
            
            if len(available_rolls) == 0:
                self.log("FAIL", "Quarantine Refund - Released", 
                       f"No available rolls after release. Statuses: {[r.get('status') for r in rolls]}")
                return False
            
            self.log("PASS", "Quarantine Refund - Released to Available", 
                   f"{len(available_rolls)} roll(s) now available")
            
            return True
            
        except Exception as e:
            self.log("FAIL", "Quarantine Refund", f"Error: {str(e)}")
            return False

    def test_quarantine_scrap(self):
        """Test: settle store_credit -> scrap decision -> roll becomes damaged"""
        try:
            orders = self.get_eligible_orders()
            if not orders:
                self.log("FAIL", "Quarantine Scrap", "No eligible orders")
                return False
            
            # Use a different order (index 4)
            order_idx = 4 if len(orders) > 4 else 0
            
            # Create and inspect return
            ret = self.create_return(orders[order_idx])
            if not ret:
                self.log("FAIL", "Quarantine Scrap", "Failed to create return")
                return False
            
            ret_id = ret["id"]
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/submit", headers=self.get_headers(), timeout=10)
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/approve", json={"notes": ""}, 
                         headers=self.get_headers(), timeout=10)
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/start", headers=self.get_headers(), timeout=10)
            
            # Complete inspection (Grade C)
            payload = {
                "inspections": [{
                    "index": 0,
                    "defects": [{"point_value": 4, "count": 12}],
                    "condition": "ok",
                    "accepted_qty": 1
                }],
                "notes": "Scrap test"
            }
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/complete", 
                         json=payload, headers=self.get_headers(), timeout=10)
            
            # Settle with store_credit outcome
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/settle", 
                         json={"outcome": "store_credit"}, headers=self.get_headers(), timeout=10)
            
            # Get quarantine rolls
            r = requests.get(f"{BASE_URL}/sales-returns/{ret_id}/quarantine", 
                           headers=self.get_headers(), timeout=10)
            rolls = r.json()
            
            if not rolls or len(rolls) == 0:
                self.log("FAIL", "Quarantine Scrap - No Rolls", "No quarantine rolls found")
                return False
            
            quarantine_rolls = [r for r in rolls if r.get("status") == "quarantine"]
            if len(quarantine_rolls) == 0:
                self.log("FAIL", "Quarantine Scrap - Status", "No rolls in quarantine status")
                return False
            
            self.log("PASS", "Quarantine Scrap - Store Credit Settled", 
                   f"{len(quarantine_rolls)} roll(s) in quarantine")
            
            # Release with scrap decision
            roll_id = quarantine_rolls[0]["id"]
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/quarantine/release", 
                            json={"decisions": [{"roll_id": roll_id, "action": "scrap"}], "notes": "Scrap"}, 
                            headers=self.get_headers(), timeout=10)
            
            if r.status_code != 200:
                self.log("FAIL", "Quarantine Scrap - Release", f"Status: {r.status_code}, {r.text[:200]}")
                return False
            
            # Verify roll is now damaged
            r = requests.get(f"{BASE_URL}/sales-returns/{ret_id}/quarantine", 
                           headers=self.get_headers(), timeout=10)
            rolls = r.json()
            damaged_rolls = [r for r in rolls if r.get("status") == "damaged"]
            
            if len(damaged_rolls) == 0:
                self.log("FAIL", "Quarantine Scrap - Damaged", 
                       f"No damaged rolls after scrap. Statuses: {[r.get('status') for r in rolls]}")
                return False
            
            self.log("PASS", "Quarantine Scrap - Scrapped to Damaged", 
                   f"{len(damaged_rolls)} roll(s) marked as damaged")
            
            return True
            
        except Exception as e:
            self.log("FAIL", "Quarantine Scrap", f"Error: {str(e)}")
            return False

    def test_nego_no_quarantine(self):
        """Test: settle nego -> no quarantine rolls (no stock movement)"""
        try:
            orders = self.get_eligible_orders()
            if not orders:
                self.log("FAIL", "Nego No Quarantine", "No eligible orders")
                return False
            
            # Use a different order (index 5)
            order_idx = 5 if len(orders) > 5 else 0
            
            # Create and inspect return
            ret = self.create_return(orders[order_idx])
            if not ret:
                self.log("FAIL", "Nego No Quarantine", "Failed to create return")
                return False
            
            ret_id = ret["id"]
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/submit", headers=self.get_headers(), timeout=10)
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/approve", json={"notes": ""}, 
                         headers=self.get_headers(), timeout=10)
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/start", headers=self.get_headers(), timeout=10)
            
            # Complete inspection (Grade C)
            payload = {
                "inspections": [{
                    "index": 0,
                    "defects": [{"point_value": 4, "count": 12}],
                    "condition": "ok",
                    "accepted_qty": 1
                }],
                "notes": "Nego test"
            }
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/complete", 
                         json=payload, headers=self.get_headers(), timeout=10)
            
            # Settle with nego outcome
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/settle", 
                            json={"outcome": "nego"}, headers=self.get_headers(), timeout=10)
            
            if r.status_code != 200:
                self.log("FAIL", "Nego No Quarantine - Settle", f"Status: {r.status_code}")
                return False
            
            # Get quarantine rolls (should be empty)
            r = requests.get(f"{BASE_URL}/sales-returns/{ret_id}/quarantine", 
                           headers=self.get_headers(), timeout=10)
            
            if r.status_code != 200:
                self.log("FAIL", "Nego No Quarantine - List", f"Status: {r.status_code}")
                return False
            
            rolls = r.json()
            if not isinstance(rolls, list):
                self.log("FAIL", "Nego No Quarantine - Response", f"Expected array, got: {type(rolls)}")
                return False
            
            if len(rolls) > 0:
                self.log("FAIL", "Nego No Quarantine - Rolls", 
                       f"Expected no rolls, found {len(rolls)} roll(s)")
                return False
            
            self.log("PASS", "Nego No Quarantine", "No quarantine rolls (no stock movement)")
            return True
            
        except Exception as e:
            self.log("FAIL", "Nego No Quarantine", f"Error: {str(e)}")
            return False

    def test_transition_guards(self):
        """Test: invalid transitions return 400"""
        try:
            orders = self.get_eligible_orders()
            if not orders:
                self.log("FAIL", "Transition Guards", "No eligible orders")
                return False
            
            # Use a different order (index 6)
            order_idx = 6 if len(orders) > 6 else 0
            
            # Create return
            ret = self.create_return(orders[order_idx])
            if not ret:
                self.log("FAIL", "Transition Guards", "Failed to create return")
                return False
            
            ret_id = ret["id"]
            
            # Try to settle before inspect (should fail)
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/settle", 
                            json={"outcome": "refund"}, headers=self.get_headers(), timeout=10)
            
            if r.status_code == 400:
                self.log("PASS", "Transition Guards - Settle before Inspect", 
                       "Correctly blocked with 400")
            else:
                self.log("FAIL", "Transition Guards - Settle before Inspect", 
                       f"Expected 400, got {r.status_code}")
                return False
            
            # Try to inspect before approve (should fail)
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/start", 
                            headers=self.get_headers(), timeout=10)
            
            if r.status_code == 400:
                self.log("PASS", "Transition Guards - Inspect before Approve", 
                       "Correctly blocked with 400")
            else:
                self.log("FAIL", "Transition Guards - Inspect before Approve", 
                       f"Expected 400, got {r.status_code}")
                return False
            
            return True
            
        except Exception as e:
            self.log("FAIL", "Transition Guards", f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all R2 backend tests"""
        print("=" * 80)
        print("R2 — RETURNS & REFUNDS BACKEND TEST")
        print("Testing: 4-point inspection, grading, quarantine, release/scrap")
        print("=" * 80)
        print()

        # Auth test
        print("--- Authentication Test ---")
        if not self.test_auth():
            print("\n❌ Admin auth failed. Cannot proceed.")
            return False

        # R2 Tests
        print("\n--- R2 Backend Tests ---")
        self.test_return_lifecycle()
        self.test_4point_inspection_grading()
        self.test_quarantine_refund()
        self.test_quarantine_scrap()
        self.test_nego_no_quarantine()
        self.test_transition_guards()

        # Summary
        print("\n" + "=" * 80)
        print(f"R2 BACKEND TEST SUMMARY")
        print("=" * 80)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        print("=" * 80)

        return self.tests_passed == self.tests_run


def main():
    tester = R2BackendTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
