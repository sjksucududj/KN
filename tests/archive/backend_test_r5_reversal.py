"""R5.4 Reversals/Corrections Backend API Testing
Tests all reversal endpoints with comprehensive validation.
"""
import os
import sys
import requests
from datetime import datetime

# Get the public backend URL
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://supplier-rma-portal.preview.emergentagent.com')
API_BASE = f"{BASE_URL}/api"

class R5ReversalTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def check(self, name, condition, extra=""):
        """Run a single test check"""
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            print(f"  ✅ {name}")
            return True
        else:
            self.tests_passed += 0
            self.failed_tests.append(f"{name}: {extra}")
            print(f"  ❌ {name} - {extra}")
            return False

    def login(self):
        """Login as admin"""
        print("\n🔐 Logging in as admin...")
        try:
            r = requests.post(
                f"{API_BASE}/auth/login",
                json={"email": "admin@kainnusantara.id", "password": "demo12345"},
                timeout=30
            )
            if r.status_code == 200:
                self.token = r.json().get('token')
                self.check("Admin login", bool(self.token), f"Status: {r.status_code}")
                return True
            else:
                self.check("Admin login", False, f"Status: {r.status_code}, Response: {r.text[:200]}")
                return False
        except Exception as e:
            self.check("Admin login", False, f"Exception: {str(e)}")
            return False

    def headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def get_eligible_orders(self):
        """Get orders eligible for returns"""
        try:
            r = requests.get(f"{API_BASE}/sales-orders", headers=self.headers(), timeout=30)
            if r.status_code != 200:
                return []
            orders = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
            eligible_statuses = {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
            return [o for o in orders if o.get("status") in eligible_statuses and
                    any(float(it.get("quantity", 0) or 0) >= 3 for it in (o.get("items") or []))]
        except Exception as e:
            print(f"  ⚠️  Error getting orders: {str(e)}")
            return []

    def get_warehouses(self):
        """Get warehouses"""
        try:
            r = requests.get(f"{API_BASE}/warehouses", headers=self.headers(), timeout=30)
            if r.status_code == 200:
                whs = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
                return whs
            return []
        except Exception as e:
            print(f"  ⚠️  Error getting warehouses: {str(e)}")
            return []

    def create_and_settle_return(self, order, qty, outcome, dest_wh):
        """Create a return and settle it through the full flow"""
        try:
            # Find suitable item
            item = next((it for it in order.get("items", []) if float(it.get("quantity", 0) or 0) >= qty), None)
            if not item:
                return None

            # Create return
            r = requests.post(
                f"{API_BASE}/sales-returns",
                headers=self.headers(),
                json={
                    "order_id": order["id"],
                    "return_type": "retur",
                    "items": [{
                        "product_id": item["product_id"],
                        "product_name": item.get("product_name", ""),
                        "quantity_returned": qty,
                        "unit": item.get("unit", "meter"),
                        "reason": "R5.4 test",
                        "condition": "ok"
                    }],
                    "notes": "R5.4 reversal test"
                },
                timeout=30
            )
            if r.status_code != 200:
                return None
            
            return_id = r.json()["id"]

            # Submit
            requests.post(f"{API_BASE}/sales-returns/{return_id}/submit", headers=self.headers(), timeout=30)
            
            # Approve
            requests.post(f"{API_BASE}/sales-returns/{return_id}/approve", 
                         headers=self.headers(), json={"notes": ""}, timeout=30)
            
            # Start inspection
            requests.post(f"{API_BASE}/sales-returns/{return_id}/inspect/start", headers=self.headers(), timeout=30)
            
            # Complete inspection
            requests.post(
                f"{API_BASE}/sales-returns/{return_id}/inspect/complete",
                headers=self.headers(),
                json={
                    "inspections": [{
                        "index": 0,
                        "defects": [{"point_value": 1, "count": int(qty)}],
                        "condition": "ok",
                        "accepted_qty": qty
                    }],
                    "notes": "4pt"
                },
                timeout=30
            )
            
            # Settle
            settle_r = requests.post(
                f"{API_BASE}/sales-returns/{return_id}/settle",
                headers=self.headers(),
                json={
                    "outcome": outcome,
                    "return_warehouse_id": dest_wh
                },
                timeout=30
            )
            
            if settle_r.status_code != 200:
                return None
                
            return return_id
        except Exception as e:
            print(f"  ⚠️  Error creating/settling return: {str(e)}")
            return None

    def get_store_credit_balance(self, customer_id):
        """Get store credit balance for a customer"""
        try:
            r = requests.get(
                f"{API_BASE}/store-credit/balance",
                headers=self.headers(),
                params={"customer_id": customer_id},
                timeout=30
            )
            if r.status_code == 200:
                return round(float(r.json().get("balance", 0) or 0), 2)
            return 0.0
        except Exception as e:
            print(f"  ⚠️  Error getting balance: {str(e)}")
            return 0.0

    def get_store_credit_ledger(self, customer_id):
        """Get store credit ledger for a customer"""
        try:
            r = requests.get(
                f"{API_BASE}/store-credit/ledger",
                headers=self.headers(),
                params={"customer_id": customer_id},
                timeout=30
            )
            if r.status_code == 200:
                ledger = r.json()
                return ledger if isinstance(ledger, list) else ledger.get("items", [])
            return []
        except Exception as e:
            print(f"  ⚠️  Error getting ledger: {str(e)}")
            return []

    def test_sales_return_refund_reversal(self, orders, dest_wh):
        """Test 1: Sales return refund reversal"""
        print("\n📋 TEST 1: Sales Return Refund Reversal")
        print("  Setup: Create return -> submit -> approve -> inspect -> settle (refund)")
        
        if not orders:
            self.check("Sales return refund reversal", False, "No eligible orders")
            return

        return_id = self.create_and_settle_return(orders[0], 2, "refund", dest_wh)
        self.check("Create and settle refund return", bool(return_id), "Failed to create/settle")
        
        if not return_id:
            return

        # Reverse the return
        print("  Reversing the settled return...")
        try:
            r = requests.post(
                f"{API_BASE}/sales-returns/{return_id}/reverse",
                headers=self.headers(),
                json={"notes": "Test reversal"},
                timeout=30
            )
            self.check("POST /reverse returns 200", r.status_code == 200, 
                      f"Status: {r.status_code}, Response: {r.text[:200]}")
            
            if r.status_code == 200:
                doc = r.json()
                self.check("Return status is 'cancelled'", doc.get("status") == "cancelled",
                          f"Status: {doc.get('status')}")
                self.check("Return reversed flag is True", doc.get("reversed") is True,
                          f"Reversed: {doc.get('reversed')}")
                self.check("Reversal summary present", "_reversal_summary" in doc,
                          "Missing _reversal_summary")
                
                # Test idempotency
                print("  Testing idempotency (calling reverse again)...")
                r2 = requests.post(
                    f"{API_BASE}/sales-returns/{return_id}/reverse",
                    headers=self.headers(),
                    json={"notes": "Second reversal attempt"},
                    timeout=30
                )
                self.check("Idempotent: second reverse returns 200", r2.status_code == 200,
                          f"Status: {r2.status_code}")
        except Exception as e:
            self.check("Sales return reversal", False, f"Exception: {str(e)}")

    def test_store_credit_reversal_guard(self, orders, dest_wh):
        """Test 2: Store credit reversal guard (balance already used)"""
        print("\n📋 TEST 2: Store Credit Reversal Guard (Balance Used)")
        print("  Setup: Settle return with store_credit -> reduce balance -> try reverse")
        
        # Find order with customer
        order = next((o for o in orders if o.get("customer_id")), None)
        if not order:
            self.check("Store credit guard test", False, "No order with customer_id")
            return

        customer_id = order["customer_id"]
        return_id = self.create_and_settle_return(order, 2, "store_credit", dest_wh)
        self.check("Create and settle store_credit return", bool(return_id), "Failed to create/settle")
        
        if not return_id:
            return

        # Get issued amount and current balance
        balance = self.get_store_credit_balance(customer_id)
        print(f"  Current balance: {balance}")
        
        # Reduce balance below issued amount
        if balance > 10:
            reduce_amount = balance - 5  # Leave only 5
            print(f"  Reducing balance by {reduce_amount}...")
            r = requests.post(
                f"{API_BASE}/store-credit/adjust",
                headers=self.headers(),
                json={
                    "customer_id": customer_id,
                    "amount": -reduce_amount,
                    "note": "Test reduction"
                },
                timeout=30
            )
            self.check("Balance reduction successful", r.status_code == 200,
                      f"Status: {r.status_code}")

        # Try to reverse - should fail with 400
        print("  Attempting reversal (should fail with 400)...")
        try:
            r = requests.post(
                f"{API_BASE}/sales-returns/{return_id}/reverse",
                headers=self.headers(),
                json={"notes": "Test reversal"},
                timeout=30
            )
            self.check("Reversal blocked with 400", r.status_code == 400,
                      f"Status: {r.status_code}, Expected 400")
            
            if r.status_code == 400:
                self.check("Error message in Indonesian", 
                          any(word in r.text.lower() for word in ["saldo", "tidak", "cukup"]),
                          f"Response: {r.text[:200]}")
            
            # Verify return status unchanged
            r2 = requests.get(f"{API_BASE}/sales-returns/{return_id}", headers=self.headers(), timeout=30)
            if r2.status_code == 200:
                doc = r2.json()
                self.check("Return status unchanged (credit_settled)", 
                          doc.get("status") == "credit_settled",
                          f"Status: {doc.get('status')}")
        except Exception as e:
            self.check("Store credit guard test", False, f"Exception: {str(e)}")

    def test_adjust_entry_reversal(self, orders):
        """Test 3: Store credit adjust entry reversal"""
        print("\n📋 TEST 3: Store Credit Adjust Entry Reversal")
        
        # Find customer
        order = next((o for o in orders if o.get("customer_id")), None)
        if not order:
            self.check("Adjust entry reversal", False, "No order with customer_id")
            return

        customer_id = order["customer_id"]
        balance_before = self.get_store_credit_balance(customer_id)
        print(f"  Balance before: {balance_before}")
        
        # Create adjust entry
        print("  Creating adjust entry (+40000)...")
        try:
            r = requests.post(
                f"{API_BASE}/store-credit/adjust",
                headers=self.headers(),
                json={
                    "customer_id": customer_id,
                    "amount": 40000,
                    "note": "Test adjust"
                },
                timeout=30
            )
            self.check("Adjust entry created", r.status_code == 200,
                      f"Status: {r.status_code}, Response: {r.text[:200]}")
            
            if r.status_code != 200:
                return
            
            entry_id = r.json().get("id")
            balance_after_adjust = self.get_store_credit_balance(customer_id)
            print(f"  Balance after adjust: {balance_after_adjust}")
            self.check("Balance increased by 40000", 
                      abs(balance_after_adjust - (balance_before + 40000)) < 1,
                      f"Expected: {balance_before + 40000}, Got: {balance_after_adjust}")
            
            # Reverse the adjust entry
            print(f"  Reversing adjust entry {entry_id}...")
            r2 = requests.post(
                f"{API_BASE}/store-credit/entries/{entry_id}/reverse",
                headers=self.headers(),
                json={"reason": "Test reversal"},
                timeout=30
            )
            self.check("Adjust reversal returns 200", r2.status_code == 200,
                      f"Status: {r2.status_code}, Response: {r2.text[:200]}")
            
            balance_after_reverse = self.get_store_credit_balance(customer_id)
            print(f"  Balance after reverse: {balance_after_reverse}")
            self.check("Balance restored to original", 
                      abs(balance_after_reverse - balance_before) < 1,
                      f"Expected: {balance_before}, Got: {balance_after_reverse}")
            
            # Test idempotency - reverse again should fail
            print("  Testing idempotency (reversing again)...")
            r3 = requests.post(
                f"{API_BASE}/store-credit/entries/{entry_id}/reverse",
                headers=self.headers(),
                json={"reason": "Second reversal"},
                timeout=30
            )
            self.check("Second reversal returns 400", r3.status_code == 400,
                      f"Status: {r3.status_code}")
        except Exception as e:
            self.check("Adjust entry reversal", False, f"Exception: {str(e)}")

    def test_redeem_entry_reversal(self, orders):
        """Test 4: Store credit redeem entry reversal"""
        print("\n📋 TEST 4: Store Credit Redeem Entry Reversal")
        
        # Find customer with open AR order
        customer_id = None
        open_order = None
        
        for order in orders:
            cid = order.get("customer_id")
            if not cid:
                continue
            try:
                r = requests.get(
                    f"{API_BASE}/store-credit/open-orders",
                    headers=self.headers(),
                    params={"customer_id": cid},
                    timeout=30
                )
                if r.status_code == 200:
                    open_orders = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
                    if open_orders:
                        customer_id = cid
                        open_order = open_orders[0]
                        break
            except Exception:
                continue
        
        if not customer_id or not open_order:
            self.check("Redeem entry reversal", False, "No customer with open AR order")
            return

        print(f"  Found customer {customer_id} with open order {open_order.get('order_id')}")
        outstanding_before = round(float(open_order.get("outstanding", 0) or 0), 2)
        print(f"  Outstanding before: {outstanding_before}")
        
        # Top up balance
        amount = min(30000, int(outstanding_before))
        balance_before = self.get_store_credit_balance(customer_id)
        
        print(f"  Topping up balance by {amount}...")
        requests.post(
            f"{API_BASE}/store-credit/adjust",
            headers=self.headers(),
            json={"customer_id": customer_id, "amount": amount, "note": "Test topup"},
            timeout=30
        )
        
        # Redeem
        print(f"  Redeeming {amount} against order...")
        try:
            r = requests.post(
                f"{API_BASE}/store-credit/redeem",
                headers=self.headers(),
                json={
                    "customer_id": customer_id,
                    "amount": amount,
                    "allocations": [{"order_id": open_order["order_id"], "amount": amount}]
                },
                timeout=30
            )
            self.check("Redeem successful", r.status_code == 200,
                      f"Status: {r.status_code}, Response: {r.text[:200]}")
            
            if r.status_code != 200:
                return
            
            redeem_id = r.json().get("id")
            
            # Get redeem ledger entry
            ledger = self.get_store_credit_ledger(customer_id)
            redeem_entry = next((e for e in ledger if e.get("type") == "redeem" and 
                               e.get("ref_id") == redeem_id), None)
            
            if not redeem_entry:
                self.check("Find redeem ledger entry", False, "Redeem entry not found in ledger")
                return
            
            entry_id = redeem_entry.get("id")
            print(f"  Reversing redeem entry {entry_id}...")
            
            # Reverse the redeem
            r2 = requests.post(
                f"{API_BASE}/store-credit/entries/{entry_id}/reverse",
                headers=self.headers(),
                json={"reason": "Test reversal"},
                timeout=30
            )
            self.check("Redeem reversal returns 200", r2.status_code == 200,
                      f"Status: {r2.status_code}, Response: {r2.text[:200]}")
            
            # Check outstanding restored
            r3 = requests.get(
                f"{API_BASE}/store-credit/open-orders",
                headers=self.headers(),
                params={"customer_id": customer_id},
                timeout=30
            )
            if r3.status_code == 200:
                open_orders_after = r3.json() if isinstance(r3.json(), list) else r3.json().get("items", [])
                order_after = next((o for o in open_orders_after if 
                                  o["order_id"] == open_order["order_id"]), None)
                if order_after:
                    outstanding_after = round(float(order_after.get("outstanding", 0) or 0), 2)
                    print(f"  Outstanding after: {outstanding_after}")
                    self.check("Outstanding restored", 
                              abs(outstanding_after - outstanding_before) < 1,
                              f"Expected: {outstanding_before}, Got: {outstanding_after}")
            
            # Check balance
            balance_after = self.get_store_credit_balance(customer_id)
            expected_balance = balance_before + amount  # topup amount (redeem was reversed)
            print(f"  Balance after: {balance_after}, Expected: {expected_balance}")
            self.check("Balance = original + topup (redeem reversed)", 
                      abs(balance_after - expected_balance) < 1,
                      f"Expected: {expected_balance}, Got: {balance_after}")
        except Exception as e:
            self.check("Redeem entry reversal", False, f"Exception: {str(e)}")

    def test_issue_entry_reversal_rejected(self, orders, dest_wh):
        """Test 5: Issue entry reversal should be rejected"""
        print("\n📋 TEST 5: Issue Entry Reversal Rejection")
        print("  Setup: Create store_credit return to generate issue entry")
        
        order = next((o for o in orders if o.get("customer_id")), None)
        if not order:
            self.check("Issue entry reversal rejection", False, "No order with customer_id")
            return

        customer_id = order["customer_id"]
        return_id = self.create_and_settle_return(order, 2, "store_credit", dest_wh)
        self.check("Create store_credit return", bool(return_id), "Failed to create/settle")
        
        if not return_id:
            return

        # Get the issue ledger entry
        ledger = self.get_store_credit_ledger(customer_id)
        issue_entry = next((e for e in ledger if e.get("type") == "issue" and 
                          e.get("ref_type") == "sales_return" and 
                          e.get("ref_id") == return_id), None)
        
        if not issue_entry:
            self.check("Find issue entry", False, "Issue entry not found")
            return

        entry_id = issue_entry.get("id")
        print(f"  Attempting to reverse issue entry {entry_id} (should fail)...")
        
        try:
            r = requests.post(
                f"{API_BASE}/store-credit/entries/{entry_id}/reverse",
                headers=self.headers(),
                json={"reason": "Test reversal"},
                timeout=30
            )
            self.check("Issue reversal returns 400", r.status_code == 400,
                      f"Status: {r.status_code}, Expected 400")
            
            if r.status_code == 400:
                self.check("Error mentions 'retur' or 'reversal'",
                          any(word in r.text.lower() for word in ["retur", "reversal", "batalkan"]),
                          f"Response: {r.text[:200]}")
        except Exception as e:
            self.check("Issue entry reversal rejection", False, f"Exception: {str(e)}")

    def test_regression_r5_1_2_3(self):
        """Test 6: Regression - R5.1/R5.2/R5.3 endpoints still work"""
        print("\n📋 TEST 6: Regression - R5.1/R5.2/R5.3 Endpoints")
        
        try:
            # Test cash accounts endpoint (R5.3)
            r = requests.get(f"{API_BASE}/gl/cash-accounts", headers=self.headers(), timeout=30)
            self.check("GET /gl/cash-accounts works", r.status_code == 200,
                      f"Status: {r.status_code}")
            
            # Test store credit summary (R5.2)
            r = requests.get(f"{API_BASE}/store-credit", headers=self.headers(), timeout=30)
            self.check("GET /store-credit works", r.status_code == 200,
                      f"Status: {r.status_code}")
            
            # Test credit notes (R5.1)
            r = requests.get(f"{API_BASE}/credit-notes", headers=self.headers(), timeout=30)
            self.check("GET /credit-notes works", r.status_code == 200,
                      f"Status: {r.status_code}")
        except Exception as e:
            self.check("Regression tests", False, f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run all R5.4 reversal tests"""
        print("=" * 70)
        print("R5.4 REVERSALS/CORRECTIONS - BACKEND API TESTING")
        print("=" * 70)
        
        if not self.login():
            print("\n❌ Login failed. Cannot proceed with tests.")
            return False

        # Get test data
        print("\n📦 Fetching test data...")
        orders = self.get_eligible_orders()
        warehouses = self.get_warehouses()
        
        if not orders:
            print("  ⚠️  No eligible orders found")
            self.check("Test data available", False, "No eligible orders")
            return False
        
        if not warehouses:
            print("  ⚠️  No warehouses found")
            self.check("Test data available", False, "No warehouses")
            return False
        
        print(f"  ✓ Found {len(orders)} eligible orders")
        print(f"  ✓ Found {len(warehouses)} warehouses")
        dest_wh = warehouses[-1]["id"]

        # Run all tests
        self.test_sales_return_refund_reversal(orders, dest_wh)
        self.test_store_credit_reversal_guard(orders, dest_wh)
        self.test_adjust_entry_reversal(orders)
        self.test_redeem_entry_reversal(orders)
        self.test_issue_entry_reversal_rejected(orders, dest_wh)
        self.test_regression_r5_1_2_3()

        # Print summary
        print("\n" + "=" * 70)
        print(f"TEST SUMMARY: {self.tests_passed}/{self.tests_run} PASSED")
        print("=" * 70)
        
        if self.failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in self.failed_tests:
                print(f"  - {test}")
        
        return self.tests_run == self.tests_passed


def main():
    tester = R5ReversalTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
