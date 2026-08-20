#!/usr/bin/env python3
"""
R1 Sales Return State Machine Test
Tests the complete lifecycle: draft → pending_approval → approved → inspecting → inspected → [refund_settled | credit_settled | nego_settled | rejected]
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://inventory-refund.preview.emergentagent.com/api"
TEST_USER = {"email": "admin@kainnusantara.id", "password": "demo12345"}

class SalesReturnR1Tester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        self.results = []
        self.test_return_id = None
        self.test_order_id = None

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

    def test_list_returns(self):
        """Test GET /api/sales-returns"""
        try:
            r = requests.get(f"{BASE_URL}/sales-returns", headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", data)
                self.log("PASS", "List Returns", f"Found {len(items)} returns")
                return True
            self.log("FAIL", "List Returns", f"Status: {r.status_code}")
            return False
        except Exception as e:
            self.log("FAIL", "List Returns", f"Error: {str(e)}")
            return False

    def test_get_eligible_order(self):
        """Get an eligible order for creating return"""
        try:
            r = requests.get(f"{BASE_URL}/sales-orders", headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                # Handle both list and dict responses
                if isinstance(data, dict):
                    orders = data.get("items", [])
                else:
                    orders = data
                
                # Find an order in eligible status
                eligible_statuses = ["confirmed", "partially_shipped", "shipped", "done"]
                for order in orders:
                    if order.get("status") in eligible_statuses and order.get("items"):
                        self.test_order_id = order["id"]
                        self.log("PASS", "Get Eligible Order", f"Order: {order.get('number')} (status: {order.get('status')})")
                        return True
                self.log("FAIL", "Get Eligible Order", "No eligible orders found")
                return False
            self.log("FAIL", "Get Eligible Order", f"Status: {r.status_code}")
            return False
        except Exception as e:
            self.log("FAIL", "Get Eligible Order", f"Error: {str(e)}")
            return False

    def test_create_return_draft(self):
        """Test POST /api/sales-returns (create draft)"""
        if not self.test_order_id:
            self.log("FAIL", "Create Return Draft", "No test order available")
            return False
        
        try:
            # Get order details to create return items
            r = requests.get(f"{BASE_URL}/sales-orders/{self.test_order_id}", headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Create Return Draft", f"Failed to get order details: {r.status_code}")
                return False
            
            order = r.json()
            items = order.get("items", [])
            if not items:
                self.log("FAIL", "Create Return Draft", "Order has no items")
                return False
            
            # Create return with first item
            item = items[0]
            return_payload = {
                "order_id": self.test_order_id,
                "return_type": "retur",
                "items": [{
                    "product_id": item["product_id"],
                    "product_name": item.get("product_name", ""),
                    "quantity_returned": min(1.0, float(item.get("quantity", 1))),
                    "unit": item.get("unit", "meter"),
                    "reason": "Test R1 state machine",
                    "condition": "ok"
                }],
                "notes": "R1 test return",
                "submit_now": False
            }
            
            r = requests.post(f"{BASE_URL}/sales-returns", json=return_payload, headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                self.test_return_id = data["id"]
                if data.get("status") == "draft":
                    self.log("PASS", "Create Return Draft", f"Return: {data.get('number')} (status: draft)")
                    return True
                else:
                    self.log("FAIL", "Create Return Draft", f"Expected status 'draft', got '{data.get('status')}'")
                    return False
            self.log("FAIL", "Create Return Draft", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Create Return Draft", f"Error: {str(e)}")
            return False

    def test_submit_return(self):
        """Test POST /api/sales-returns/{id}/submit (draft → pending_approval)"""
        if not self.test_return_id:
            self.log("FAIL", "Submit Return", "No test return available")
            return False
        
        try:
            r = requests.post(f"{BASE_URL}/sales-returns/{self.test_return_id}/submit", 
                            json={}, headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "pending_approval":
                    self.log("PASS", "Submit Return", f"Status: pending_approval")
                    return True
                else:
                    self.log("FAIL", "Submit Return", f"Expected 'pending_approval', got '{data.get('status')}'")
                    return False
            self.log("FAIL", "Submit Return", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Submit Return", f"Error: {str(e)}")
            return False

    def test_approve_return(self):
        """Test POST /api/sales-returns/{id}/approve (pending_approval → approved)"""
        if not self.test_return_id:
            self.log("FAIL", "Approve Return", "No test return available")
            return False
        
        try:
            r = requests.post(f"{BASE_URL}/sales-returns/{self.test_return_id}/approve", 
                            json={"notes": "R1 test approval"}, headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "approved":
                    # CRITICAL: Check that credit_note_number is NOT set and stock_adjusted is False
                    if data.get("credit_note_number"):
                        self.log("FAIL", "Approve Return", "credit_note_number should NOT be set at approve stage")
                        return False
                    if data.get("stock_adjusted"):
                        self.log("FAIL", "Approve Return", "stock_adjusted should be False at approve stage")
                        return False
                    self.log("PASS", "Approve Return", f"Status: approved (no CN, no stock adjustment)")
                    return True
                else:
                    self.log("FAIL", "Approve Return", f"Expected 'approved', got '{data.get('status')}'")
                    return False
            self.log("FAIL", "Approve Return", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Approve Return", f"Error: {str(e)}")
            return False

    def test_start_inspection(self):
        """Test POST /api/sales-returns/{id}/inspect/start (approved → inspecting)"""
        if not self.test_return_id:
            self.log("FAIL", "Start Inspection", "No test return available")
            return False
        
        try:
            r = requests.post(f"{BASE_URL}/sales-returns/{self.test_return_id}/inspect/start", 
                            json={}, headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "inspecting":
                    self.log("PASS", "Start Inspection", f"Status: inspecting")
                    return True
                else:
                    self.log("FAIL", "Start Inspection", f"Expected 'inspecting', got '{data.get('status')}'")
                    return False
            self.log("FAIL", "Start Inspection", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Start Inspection", f"Error: {str(e)}")
            return False

    def test_complete_inspection(self):
        """Test POST /api/sales-returns/{id}/inspect/complete (inspecting → inspected)"""
        if not self.test_return_id:
            self.log("FAIL", "Complete Inspection", "No test return available")
            return False
        
        try:
            # Get return details to build inspection payload
            r = requests.get(f"{BASE_URL}/sales-returns/{self.test_return_id}", headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Complete Inspection", f"Failed to get return details: {r.status_code}")
                return False
            
            ret = r.json()
            items = ret.get("items", [])
            
            # Build inspection payload
            inspections = []
            for i, item in enumerate(items):
                inspections.append({
                    "index": i,
                    "grade": "A",
                    "condition": "ok",
                    "recommended_outcome": "refund",
                    "accepted_qty": item.get("quantity_returned", 0)
                })
            
            r = requests.post(f"{BASE_URL}/sales-returns/{self.test_return_id}/inspect/complete", 
                            json={"inspections": inspections, "notes": "R1 test inspection"}, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "inspected":
                    # Check that inspection data is saved
                    if data.get("inspection"):
                        self.log("PASS", "Complete Inspection", f"Status: inspected (inspection data saved)")
                        return True
                    else:
                        self.log("FAIL", "Complete Inspection", "Inspection data not saved")
                        return False
                else:
                    self.log("FAIL", "Complete Inspection", f"Expected 'inspected', got '{data.get('status')}'")
                    return False
            self.log("FAIL", "Complete Inspection", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Complete Inspection", f"Error: {str(e)}")
            return False

    def test_settle_refund(self):
        """Test POST /api/sales-returns/{id}/settle with outcome='refund' (inspected → refund_settled)"""
        if not self.test_return_id:
            self.log("FAIL", "Settle Refund", "No test return available")
            return False
        
        try:
            r = requests.post(f"{BASE_URL}/sales-returns/{self.test_return_id}/settle", 
                            json={
                                "outcome": "refund",
                                "item_decisions": [],
                                "notes": "R1 test settle refund"
                            }, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "refund_settled":
                    # CRITICAL: Check that credit_note_number IS set and stock_adjusted is True
                    if not data.get("credit_note_number"):
                        self.log("FAIL", "Settle Refund", "credit_note_number should be set after settle")
                        return False
                    if not data.get("stock_adjusted"):
                        self.log("FAIL", "Settle Refund", "stock_adjusted should be True after refund settle")
                        return False
                    self.log("PASS", "Settle Refund", f"Status: refund_settled (CN: {data.get('credit_note_number')}, stock adjusted)")
                    return True
                else:
                    self.log("FAIL", "Settle Refund", f"Expected 'refund_settled', got '{data.get('status')}'")
                    return False
            self.log("FAIL", "Settle Refund", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Settle Refund", f"Error: {str(e)}")
            return False

    def test_state_guards(self):
        """Test state guards: invalid transitions should return 400"""
        # Find an inspected return to test invalid transition
        try:
            r = requests.get(f"{BASE_URL}/sales-returns?status=inspected", headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "State Guard - Invalid Approve", f"Failed to get inspected returns: {r.status_code}")
                return False
            
            data = r.json()
            items = data.get("items", data) if isinstance(data, dict) else data
            
            if not items:
                # If no inspected return, try with our test return if it's settled
                if self.test_return_id:
                    r = requests.get(f"{BASE_URL}/sales-returns/{self.test_return_id}", headers=self.get_headers(), timeout=10)
                    if r.status_code == 200:
                        ret = r.json()
                        if ret.get("status") in ["refund_settled", "credit_settled", "nego_settled"]:
                            # Try to approve from settled (should fail)
                            r = requests.post(f"{BASE_URL}/sales-returns/{self.test_return_id}/approve", 
                                            json={"notes": "Invalid transition test"}, headers=self.get_headers(), timeout=10)
                            if r.status_code == 400:
                                self.log("PASS", "State Guard - Invalid Approve", "400 returned for invalid transition")
                                return True
                            else:
                                self.log("FAIL", "State Guard - Invalid Approve", f"Expected 400, got {r.status_code}")
                                return False
                self.log("FAIL", "State Guard - Invalid Approve", "No suitable return found for testing")
                return False
            
            # Try to approve from inspected (should fail)
            test_return = items[0]
            r = requests.post(f"{BASE_URL}/sales-returns/{test_return['id']}/approve", 
                            json={"notes": "Invalid transition test"}, headers=self.get_headers(), timeout=10)
            if r.status_code == 400:
                self.log("PASS", "State Guard - Invalid Approve", "400 returned for invalid transition")
                return True
            else:
                self.log("FAIL", "State Guard - Invalid Approve", f"Expected 400, got {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "State Guard - Invalid Approve", f"Error: {str(e)}")
            return False

    def test_idempotency(self):
        """Test idempotency: calling settle twice should return same credit_note_number"""
        if not self.test_return_id:
            self.log("FAIL", "Idempotency Test", "No test return available")
            return False
        
        try:
            # Get current state
            r = requests.get(f"{BASE_URL}/sales-returns/{self.test_return_id}", headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Idempotency Test", f"Failed to get return: {r.status_code}")
                return False
            
            data = r.json()
            if data.get("status") != "refund_settled":
                self.log("FAIL", "Idempotency Test", f"Return not in settled state: {data.get('status')}")
                return False
            
            first_cn = data.get("credit_note_number")
            
            # Call settle again
            r = requests.post(f"{BASE_URL}/sales-returns/{self.test_return_id}/settle", 
                            json={
                                "outcome": "refund",
                                "item_decisions": [],
                                "notes": "Idempotency test"
                            }, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                second_cn = data.get("credit_note_number")
                if first_cn == second_cn:
                    self.log("PASS", "Idempotency Test", f"Same CN returned: {first_cn}")
                    return True
                else:
                    self.log("FAIL", "Idempotency Test", f"Different CNs: {first_cn} vs {second_cn}")
                    return False
            self.log("FAIL", "Idempotency Test", f"Status: {r.status_code}")
            return False
        except Exception as e:
            self.log("FAIL", "Idempotency Test", f"Error: {str(e)}")
            return False

    def test_credit_note_gl(self):
        """Test that Credit Note has journal_entry_id"""
        if not self.test_return_id:
            self.log("FAIL", "Credit Note GL", "No test return available")
            return False
        
        try:
            # Get return to find credit_note_id
            r = requests.get(f"{BASE_URL}/sales-returns/{self.test_return_id}", headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Credit Note GL", f"Failed to get return: {r.status_code}")
                return False
            
            ret = r.json()
            cn_id = ret.get("credit_note_id")
            if not cn_id:
                self.log("FAIL", "Credit Note GL", "No credit_note_id found")
                return False
            
            # Get credit note
            r = requests.get(f"{BASE_URL}/credit-notes/{cn_id}", headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                cn = r.json()
                if cn.get("journal_entry_id"):
                    self.log("PASS", "Credit Note GL", f"Journal entry: {cn.get('journal_entry_id')}")
                    return True
                else:
                    self.log("FAIL", "Credit Note GL", "No journal_entry_id in Credit Note")
                    return False
            self.log("FAIL", "Credit Note GL", f"Status: {r.status_code}")
            return False
        except Exception as e:
            self.log("FAIL", "Credit Note GL", f"Error: {str(e)}")
            return False

    def test_auth_permissions(self):
        """Test that endpoints require proper auth"""
        try:
            # Try to list returns without token
            r = requests.get(f"{BASE_URL}/sales-returns", timeout=10)
            if r.status_code in [401, 403]:
                self.log("PASS", "Auth Permissions", f"Unauthorized access blocked: {r.status_code}")
                return True
            else:
                self.log("FAIL", "Auth Permissions", f"Expected 401/403, got {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "Auth Permissions", f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*60)
        print("R1 SALES RETURN STATE MACHINE TEST")
        print("="*60 + "\n")
        
        # Auth
        if not self.test_auth():
            print("\n❌ Auth failed, stopping tests")
            return False
        
        # Basic tests
        self.test_list_returns()
        self.test_auth_permissions()
        
        # Lifecycle tests (create new return)
        if self.test_get_eligible_order():
            self.test_create_return_draft()
            self.test_submit_return()
            self.test_approve_return()
            self.test_start_inspection()
            self.test_complete_inspection()
            self.test_settle_refund()
            self.test_idempotency()
            self.test_credit_note_gl()
        
        # State guard tests
        self.test_state_guards()
        
        # Additional outcome tests
        self.test_store_credit_outcome()
        self.test_nego_outcome()
        self.test_reject_outcome()
        self.test_partial_settle()
        
        # Summary
        print("\n" + "="*60)
        print(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        print("="*60 + "\n")
        
        return self.tests_passed == self.tests_run

    def test_store_credit_outcome(self):
        """Test settle with outcome='store_credit' (inspected → credit_settled)"""
        # Create a new return for this test
        if not self.test_order_id:
            self.log("FAIL", "Store Credit Outcome", "No test order available")
            return False
        
        try:
            # Get order details
            r = requests.get(f"{BASE_URL}/sales-orders/{self.test_order_id}", headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Store Credit Outcome", f"Failed to get order: {r.status_code}")
                return False
            
            order = r.json()
            items = order.get("items", [])
            if not items:
                self.log("FAIL", "Store Credit Outcome", "Order has no items")
                return False
            
            # Create return
            item = items[0]
            return_payload = {
                "order_id": self.test_order_id,
                "return_type": "retur",
                "items": [{
                    "product_id": item["product_id"],
                    "product_name": item.get("product_name", ""),
                    "quantity_returned": min(0.5, float(item.get("quantity", 1))),
                    "unit": item.get("unit", "meter"),
                    "reason": "Test store credit",
                    "condition": "ok"
                }],
                "notes": "Store credit test",
                "submit_now": True
            }
            
            r = requests.post(f"{BASE_URL}/sales-returns", json=return_payload, headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Store Credit Outcome", f"Failed to create return: {r.status_code}")
                return False
            
            ret = r.json()
            ret_id = ret["id"]
            
            # Approve
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/approve", json={"notes": ""}, headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Store Credit Outcome", f"Failed to approve: {r.status_code}")
                return False
            
            # Start inspection
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/start", json={}, headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Store Credit Outcome", f"Failed to start inspection: {r.status_code}")
                return False
            
            # Complete inspection
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/complete", 
                            json={"inspections": [{"index": 0, "grade": "A", "condition": "ok", "accepted_qty": 0.5}], "notes": ""}, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Store Credit Outcome", f"Failed to complete inspection: {r.status_code}")
                return False
            
            # Settle with store_credit
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/settle", 
                            json={"outcome": "store_credit", "item_decisions": [], "notes": ""}, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "credit_settled":
                    # Check settlement details
                    settlement = data.get("settlement", {})
                    if settlement.get("settlement") == "store_credit" and settlement.get("store_credit_amount", 0) > 0:
                        self.log("PASS", "Store Credit Outcome", f"Status: credit_settled (store_credit_amount: {settlement.get('store_credit_amount')})")
                        return True
                    else:
                        self.log("FAIL", "Store Credit Outcome", f"Settlement details incorrect: {settlement}")
                        return False
                else:
                    self.log("FAIL", "Store Credit Outcome", f"Expected 'credit_settled', got '{data.get('status')}'")
                    return False
            self.log("FAIL", "Store Credit Outcome", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Store Credit Outcome", f"Error: {str(e)}")
            return False

    def test_nego_outcome(self):
        """Test settle with outcome='nego' (NO stock movement)"""
        if not self.test_order_id:
            self.log("FAIL", "Nego Outcome", "No test order available")
            return False
        
        try:
            # Get order details
            r = requests.get(f"{BASE_URL}/sales-orders/{self.test_order_id}", headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Nego Outcome", f"Failed to get order: {r.status_code}")
                return False
            
            order = r.json()
            items = order.get("items", [])
            if not items:
                self.log("FAIL", "Nego Outcome", "Order has no items")
                return False
            
            # Create return
            item = items[0]
            return_payload = {
                "order_id": self.test_order_id,
                "return_type": "retur",
                "items": [{
                    "product_id": item["product_id"],
                    "product_name": item.get("product_name", ""),
                    "quantity_returned": min(0.3, float(item.get("quantity", 1))),
                    "unit": item.get("unit", "meter"),
                    "reason": "Test nego",
                    "condition": "ok"
                }],
                "notes": "Nego test",
                "submit_now": True
            }
            
            r = requests.post(f"{BASE_URL}/sales-returns", json=return_payload, headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Nego Outcome", f"Failed to create return: {r.status_code}")
                return False
            
            ret = r.json()
            ret_id = ret["id"]
            
            # Approve, inspect, complete
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/approve", json={"notes": ""}, headers=self.get_headers(), timeout=10)
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/start", json={}, headers=self.get_headers(), timeout=10)
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/complete", 
                        json={"inspections": [{"index": 0, "grade": "A", "condition": "ok", "accepted_qty": 0.3}], "notes": ""}, 
                        headers=self.get_headers(), timeout=10)
            
            # Settle with nego
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/settle", 
                            json={"outcome": "nego", "item_decisions": [], "notes": ""}, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "nego_settled":
                    # CRITICAL: Check that stock_adjusted is FALSE for nego
                    if data.get("stock_adjusted"):
                        self.log("FAIL", "Nego Outcome", "stock_adjusted should be False for nego outcome")
                        return False
                    # Check that Credit Note was created
                    if not data.get("credit_note_number"):
                        self.log("FAIL", "Nego Outcome", "credit_note_number should be set for nego")
                        return False
                    self.log("PASS", "Nego Outcome", f"Status: nego_settled (CN created, NO stock movement)")
                    return True
                else:
                    self.log("FAIL", "Nego Outcome", f"Expected 'nego_settled', got '{data.get('status')}'")
                    return False
            self.log("FAIL", "Nego Outcome", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Nego Outcome", f"Error: {str(e)}")
            return False

    def test_reject_outcome(self):
        """Test reject flow (pending_approval → rejected)"""
        if not self.test_order_id:
            self.log("FAIL", "Reject Outcome", "No test order available")
            return False
        
        try:
            # Get order details
            r = requests.get(f"{BASE_URL}/sales-orders/{self.test_order_id}", headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Reject Outcome", f"Failed to get order: {r.status_code}")
                return False
            
            order = r.json()
            items = order.get("items", [])
            if not items:
                self.log("FAIL", "Reject Outcome", "Order has no items")
                return False
            
            # Create return
            item = items[0]
            return_payload = {
                "order_id": self.test_order_id,
                "return_type": "retur",
                "items": [{
                    "product_id": item["product_id"],
                    "product_name": item.get("product_name", ""),
                    "quantity_returned": min(0.2, float(item.get("quantity", 1))),
                    "unit": item.get("unit", "meter"),
                    "reason": "Test reject",
                    "condition": "ok"
                }],
                "notes": "Reject test",
                "submit_now": True
            }
            
            r = requests.post(f"{BASE_URL}/sales-returns", json=return_payload, headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Reject Outcome", f"Failed to create return: {r.status_code}")
                return False
            
            ret = r.json()
            ret_id = ret["id"]
            
            # Reject from pending_approval
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/reject", 
                            json={"notes": "Test rejection reason"}, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "rejected" and data.get("outcome") == "reject":
                    self.log("PASS", "Reject Outcome", f"Status: rejected (reason: {data.get('reject_reason')})")
                    return True
                else:
                    self.log("FAIL", "Reject Outcome", f"Expected 'rejected', got '{data.get('status')}'")
                    return False
            self.log("FAIL", "Reject Outcome", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Reject Outcome", f"Error: {str(e)}")
            return False

    def test_partial_settle(self):
        """Test partial settle (per-item decisions)"""
        if not self.test_order_id:
            self.log("FAIL", "Partial Settle", "No test order available")
            return False
        
        try:
            # Get order with multiple items
            r = requests.get(f"{BASE_URL}/sales-orders/{self.test_order_id}", headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Partial Settle", f"Failed to get order: {r.status_code}")
                return False
            
            order = r.json()
            items = order.get("items", [])
            if len(items) < 2:
                self.log("FAIL", "Partial Settle", "Need order with at least 2 items")
                return False
            
            # Create return with 2 items
            return_payload = {
                "order_id": self.test_order_id,
                "return_type": "retur",
                "items": [
                    {
                        "product_id": items[0]["product_id"],
                        "product_name": items[0].get("product_name", ""),
                        "quantity_returned": min(1.0, float(items[0].get("quantity", 1))),
                        "unit": items[0].get("unit", "meter"),
                        "reason": "Test partial item 1",
                        "condition": "ok"
                    },
                    {
                        "product_id": items[1]["product_id"],
                        "product_name": items[1].get("product_name", ""),
                        "quantity_returned": min(1.0, float(items[1].get("quantity", 1))),
                        "unit": items[1].get("unit", "meter"),
                        "reason": "Test partial item 2",
                        "condition": "ok"
                    }
                ],
                "notes": "Partial settle test",
                "submit_now": True
            }
            
            r = requests.post(f"{BASE_URL}/sales-returns", json=return_payload, headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Partial Settle", f"Failed to create return: {r.status_code}")
                return False
            
            ret = r.json()
            ret_id = ret["id"]
            
            # Approve, inspect, complete
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/approve", json={"notes": ""}, headers=self.get_headers(), timeout=10)
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/start", json={}, headers=self.get_headers(), timeout=10)
            requests.post(f"{BASE_URL}/sales-returns/{ret_id}/inspect/complete", 
                        json={"inspections": [
                            {"index": 0, "grade": "A", "condition": "ok", "accepted_qty": 1.0},
                            {"index": 1, "grade": "A", "condition": "ok", "accepted_qty": 1.0}
                        ], "notes": ""}, 
                        headers=self.get_headers(), timeout=10)
            
            # Settle with partial: item 0 with partial qty, item 1 rejected
            r = requests.post(f"{BASE_URL}/sales-returns/{ret_id}/settle", 
                            json={
                                "outcome": "refund",
                                "item_decisions": [
                                    {"index": 0, "settle_qty": 0.5},  # Partial qty
                                    {"index": 1, "outcome": "reject"}  # Exclude item
                                ],
                                "notes": "Partial settle"
                            }, 
                            headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "refund_settled":
                    items = data.get("items", [])
                    if len(items) >= 2:
                        # Check item 0 has settled_qty = 0.5
                        if items[0].get("settled_qty") == 0.5:
                            # Check item 1 has settle_outcome = reject
                            if items[1].get("settle_outcome") == "reject":
                                self.log("PASS", "Partial Settle", f"Item 0 settled_qty: {items[0].get('settled_qty')}, Item 1 outcome: {items[1].get('settle_outcome')}")
                                return True
                            else:
                                self.log("FAIL", "Partial Settle", f"Item 1 should have settle_outcome='reject', got '{items[1].get('settle_outcome')}'")
                                return False
                        else:
                            self.log("FAIL", "Partial Settle", f"Item 0 should have settled_qty=0.5, got {items[0].get('settled_qty')}")
                            return False
                    else:
                        self.log("FAIL", "Partial Settle", f"Expected 2 items, got {len(items)}")
                        return False
                else:
                    self.log("FAIL", "Partial Settle", f"Expected 'refund_settled', got '{data.get('status')}'")
                    return False
            self.log("FAIL", "Partial Settle", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Partial Settle", f"Error: {str(e)}")
            return False

def main():
    tester = SalesReturnR1Tester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
