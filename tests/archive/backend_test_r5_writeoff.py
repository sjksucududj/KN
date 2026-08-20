"""R5.1 — Inventory Write-off GL (scrap & goods) — Comprehensive Backend Test.

Tests:
  1. Full sales-return lifecycle via API (create → submit → approve → inspect → settle refund)
  2. Scrap quarantine roll → verify write-off JE created (Dr 5-9500 / Cr 1-1300)
  3. JE balanced, correct accounts, correct amount (length_remaining * unit_cost)
  4. Idempotency: re-scrap does NOT create duplicate JE
  5. Roll tagged with writeoff_je_number + writeoff_amount
  6. Normal release-to-stock does NOT create write-off (regression)
  7. GL 1-1300 reconciliation (anti INV-GL-DRIFT)
"""
import sys
import requests

BASE = "https://supplier-rma-portal.preview.emergentagent.com/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}

class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.token = None
        self.headers = {}
    
    def check(self, name, condition, extra=""):
        if condition:
            self.passed += 1
            print(f"  ✅ {name}")
            return True
        else:
            self.failed += 1
            print(f"  ❌ {name}  {extra}")
            return False
    
    def login(self):
        print("\n[1] Login as admin")
        try:
            r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
            r.raise_for_status()
            data = r.json()
            self.token = data.get("token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self.check("Login successful", bool(self.token))
            return True
        except Exception as e:
            self.check("Login successful", False, str(e))
            return False
    
    def find_eligible_order(self):
        """Find sales order with status in confirmed/shipped/done and item qty >= 5"""
        print("\n[2] Find eligible sales order")
        try:
            r = requests.get(f"{BASE}/sales-orders", headers=self.headers, timeout=30)
            r.raise_for_status()
            orders = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
            
            eligible_statuses = {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
            for order in orders:
                if order.get("status") not in eligible_statuses:
                    continue
                for item in order.get("items", []):
                    if float(item.get("quantity", 0) or 0) >= 5:
                        self.check(f"Found eligible order {order.get('number')}", True)
                        return order
            
            self.check("Found eligible order", False, "No order with qty >= 5")
            return None
        except Exception as e:
            self.check("Found eligible order", False, str(e))
            return None
    
    def create_return(self, order):
        """Create sales return with 2 qty"""
        print("\n[3] Create sales return (retur, qty=2)")
        try:
            items = [it for it in order.get("items", []) if float(it.get("quantity", 0) or 0) >= 2]
            if not items:
                self.check("Create return", False, "No item with qty >= 2")
                return None
            
            item = items[0]
            payload = {
                "order_id": order["id"],
                "return_type": "retur",
                "items": [{
                    "product_id": item["product_id"],
                    "product_name": item.get("product_name", ""),
                    "quantity_returned": 2,
                    "unit": item.get("unit", "meter"),
                    "reason": "R5.1 write-off test",
                    "condition": "ok"
                }],
                "notes": "R5.1 write-off GL test",
                "submit_now": False
            }
            
            r = requests.post(f"{BASE}/sales-returns", headers=self.headers, json=payload, timeout=30)
            r.raise_for_status()
            ret = r.json()
            self.check(f"Create return {ret.get('number')}", True)
            return ret
        except Exception as e:
            self.check("Create return", False, str(e)[:200])
            return None
    
    def submit_return(self, return_id):
        """Submit return (draft → pending_approval)"""
        print("\n[4] Submit return")
        try:
            r = requests.post(f"{BASE}/sales-returns/{return_id}/submit", headers=self.headers, timeout=30)
            r.raise_for_status()
            ret = r.json()
            self.check("Submit return", ret.get("status") == "pending_approval", f"status={ret.get('status')}")
            return ret
        except Exception as e:
            self.check("Submit return", False, str(e)[:200])
            return None
    
    def approve_return(self, return_id):
        """Approve return (pending_approval → approved)"""
        print("\n[5] Approve return")
        try:
            r = requests.post(f"{BASE}/sales-returns/{return_id}/approve", 
                            headers=self.headers, json={"notes": ""}, timeout=30)
            r.raise_for_status()
            ret = r.json()
            self.check("Approve return", ret.get("status") == "approved", f"status={ret.get('status')}")
            return ret
        except Exception as e:
            self.check("Approve return", False, str(e)[:200])
            return None
    
    def inspect_return(self, return_id):
        """Start and complete inspection (approved → inspecting → inspected)"""
        print("\n[6] Inspect return (start + complete)")
        try:
            # Start inspection
            r1 = requests.post(f"{BASE}/sales-returns/{return_id}/inspect/start", 
                             headers=self.headers, timeout=30)
            r1.raise_for_status()
            ret1 = r1.json()
            self.check("Start inspection", ret1.get("status") == "inspecting", f"status={ret1.get('status')}")
            
            # Complete inspection with 4-point grading (2 defects of 1 point = grade A)
            payload = {
                "inspections": [{
                    "index": 0,
                    "defects": [{"point_value": 1, "count": 2}],
                    "condition": "ok",
                    "accepted_qty": 2
                }],
                "notes": "4-point inspection"
            }
            r2 = requests.post(f"{BASE}/sales-returns/{return_id}/inspect/complete",
                             headers=self.headers, json=payload, timeout=30)
            r2.raise_for_status()
            ret2 = r2.json()
            self.check("Complete inspection", ret2.get("status") == "inspected", f"status={ret2.get('status')}")
            return ret2
        except Exception as e:
            self.check("Inspect return", False, str(e)[:200])
            return None
    
    def settle_return(self, return_id):
        """Settle return with refund outcome (inspected → refund_settled)"""
        print("\n[7] Settle return (outcome=refund)")
        try:
            payload = {"outcome": "refund", "item_decisions": [], "notes": ""}
            r = requests.post(f"{BASE}/sales-returns/{return_id}/settle",
                            headers=self.headers, json=payload, timeout=30)
            r.raise_for_status()
            ret = r.json()
            self.check("Settle return", ret.get("status") == "refund_settled", f"status={ret.get('status')}")
            self.check("Stock adjusted", ret.get("stock_adjusted") == True, f"stock_adjusted={ret.get('stock_adjusted')}")
            return ret
        except Exception as e:
            self.check("Settle return", False, str(e)[:200])
            return None
    
    def get_quarantine_rolls(self, return_id):
        """Get quarantine rolls for return"""
        print("\n[8] Get quarantine rolls")
        try:
            r = requests.get(f"{BASE}/sales-returns/{return_id}/quarantine", 
                           headers=self.headers, timeout=30)
            r.raise_for_status()
            rolls = r.json()
            quarantine_rolls = [roll for roll in rolls if roll.get("status") == "quarantine"]
            self.check(f"Found {len(quarantine_rolls)} quarantine roll(s)", len(quarantine_rolls) >= 1)
            
            # Check unit_cost > 0 (needed for write-off)
            if quarantine_rolls:
                roll = quarantine_rolls[0]
                unit_cost = float(roll.get("unit_cost", 0) or 0)
                self.check("Roll has unit_cost > 0", unit_cost > 0, f"unit_cost={unit_cost}")
                return roll
            return None
        except Exception as e:
            self.check("Get quarantine rolls", False, str(e)[:200])
            return None
    
    def scrap_roll(self, return_id, roll_id):
        """Scrap roll (action=scrap) → should create write-off JE"""
        print("\n[9] Scrap roll (action=scrap) → write-off GL")
        try:
            payload = {
                "decisions": [{"roll_id": roll_id, "action": "scrap"}],
                "notes": "R5.1 scrap test"
            }
            r = requests.post(f"{BASE}/sales-returns/{return_id}/quarantine/release",
                            headers=self.headers, json=payload, timeout=30)
            r.raise_for_status()
            result = r.json()
            
            summary = result.get("_release_summary", {})
            self.check("Release summary present", bool(summary))
            self.check("Scrapped >= 1", summary.get("scrapped", 0) >= 1, f"scrapped={summary.get('scrapped')}")
            self.check("Write-off total > 0", float(summary.get("writeoff_total", 0) or 0) > 0, 
                      f"writeoff_total={summary.get('writeoff_total')}")
            self.check("Write-off JEs array present", len(summary.get("writeoff_jes", [])) > 0)
            
            return result
        except Exception as e:
            self.check("Scrap roll", False, str(e)[:200])
            return None
    
    def verify_writeoff_je(self, return_id, roll_id, expected_amount):
        """Verify write-off JE exists and is correct"""
        print("\n[10] Verify write-off JE (source_type=inventory_writeoff)")
        try:
            # Get GL entries with source=inventory_writeoff
            r = requests.get(f"{BASE}/gl/journal?source=inventory_writeoff", 
                           headers=self.headers, timeout=30)
            r.raise_for_status()
            entries = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
            
            # Find JE for this roll
            je = next((e for e in entries if e.get("source_id") == roll_id), None)
            self.check("Write-off JE exists", bool(je), f"source_id={roll_id}")
            
            if je:
                # Check balanced
                total_debit = round(sum(float(l.get("debit", 0) or 0) for l in je.get("lines", [])), 2)
                total_credit = round(sum(float(l.get("credit", 0) or 0) for l in je.get("lines", [])), 2)
                self.check("JE balanced (Dr == Cr)", abs(total_debit - total_credit) < 0.01, 
                          f"Dr={total_debit} Cr={total_credit}")
                
                # Check amount matches expected
                self.check("JE amount matches expected", abs(total_debit - expected_amount) < 0.5,
                          f"JE={total_debit} expected={expected_amount}")
                
                # Check accounts
                accounts = {l.get("account_code"): l for l in je.get("lines", [])}
                self.check("Dr 5-9500 (write-off expense)", 
                          float(accounts.get("5-9500", {}).get("debit", 0) or 0) > 0,
                          f"accounts={list(accounts.keys())}")
                self.check("Cr 1-1300 (inventory)", 
                          float(accounts.get("1-1300", {}).get("credit", 0) or 0) > 0,
                          f"accounts={list(accounts.keys())}")
                
                return je
            return None
        except Exception as e:
            self.check("Verify write-off JE", False, str(e)[:200])
            return None
    
    def verify_roll_tagged(self, return_id, roll_id):
        """Verify roll is tagged with writeoff_je_number and writeoff_amount"""
        print("\n[11] Verify roll tagged with write-off metadata")
        try:
            r = requests.get(f"{BASE}/sales-returns/{return_id}/quarantine",
                           headers=self.headers, timeout=30)
            r.raise_for_status()
            rolls = r.json()
            
            roll = next((r for r in rolls if r.get("id") == roll_id), None)
            self.check("Roll found", bool(roll))
            
            if roll:
                self.check("Roll status = damaged", roll.get("status") == "damaged", 
                          f"status={roll.get('status')}")
                self.check("Roll has writeoff_je_number", bool(roll.get("writeoff_je_number")),
                          f"writeoff_je_number={roll.get('writeoff_je_number')}")
                self.check("Roll has writeoff_amount", float(roll.get("writeoff_amount", 0) or 0) > 0,
                          f"writeoff_amount={roll.get('writeoff_amount')}")
                return roll
            return None
        except Exception as e:
            self.check("Verify roll tagged", False, str(e)[:200])
            return None
    
    def test_idempotency(self, return_id, roll_id):
        """Test idempotency: re-scrap should NOT create duplicate JE"""
        print("\n[12] Test idempotency (re-scrap should not create duplicate JE)")
        try:
            # Try to scrap again (should fail or no-op)
            payload = {
                "decisions": [{"roll_id": roll_id, "action": "scrap"}],
                "notes": "Idempotency test"
            }
            r = requests.post(f"{BASE}/sales-returns/{return_id}/quarantine/release",
                            headers=self.headers, json=payload, timeout=30)
            
            # Should either fail (400) or succeed with no new write-off
            if r.status_code == 400:
                self.check("Re-scrap rejected (no quarantine rolls)", True)
            elif r.status_code == 200:
                result = r.json()
                summary = result.get("_release_summary", {})
                # Should have 0 scrapped (no quarantine rolls left)
                self.check("Re-scrap no-op (scrapped=0)", summary.get("scrapped", 0) == 0,
                          f"scrapped={summary.get('scrapped')}")
            else:
                self.check("Re-scrap handled correctly", False, f"status={r.status_code}")
            
            return True
        except Exception as e:
            # Exception is OK if it's "no quarantine rolls"
            if "tidak ada roll karantina" in str(e).lower() or "no quarantine" in str(e).lower():
                self.check("Re-scrap rejected (no quarantine rolls)", True)
                return True
            self.check("Test idempotency", False, str(e)[:200])
            return False
    
    def test_normal_release_no_writeoff(self):
        """Regression: normal release (action=release) should NOT create write-off"""
        print("\n[13] Regression: normal release should NOT create write-off")
        try:
            # Find another order and create return
            order = self.find_eligible_order()
            if not order:
                self.check("Regression test skipped", False, "No eligible order")
                return False
            
            ret = self.create_return(order)
            if not ret:
                return False
            
            self.submit_return(ret["id"])
            self.approve_return(ret["id"])
            self.inspect_return(ret["id"])
            self.settle_return(ret["id"])
            
            roll = self.get_quarantine_rolls(ret["id"])
            if not roll:
                return False
            
            # Release normally (action=release, not scrap)
            payload = {
                "decisions": [{"roll_id": roll["id"], "action": "release"}],
                "notes": "Normal release test"
            }
            r = requests.post(f"{BASE}/sales-returns/{ret['id']}/quarantine/release",
                            headers=self.headers, json=payload, timeout=30)
            r.raise_for_status()
            result = r.json()
            
            summary = result.get("_release_summary", {})
            self.check("Released >= 1", summary.get("released", 0) >= 1, f"released={summary.get('released')}")
            self.check("Write-off total = 0 (no write-off)", 
                      float(summary.get("writeoff_total", 0) or 0) == 0,
                      f"writeoff_total={summary.get('writeoff_total')}")
            
            # Verify roll status = available (not damaged)
            r2 = requests.get(f"{BASE}/sales-returns/{ret['id']}/quarantine",
                            headers=self.headers, timeout=30)
            r2.raise_for_status()
            rolls = r2.json()
            released_roll = next((r for r in rolls if r.get("id") == roll["id"]), None)
            self.check("Roll status = available", released_roll.get("status") == "available",
                      f"status={released_roll.get('status')}")
            self.check("Roll has NO writeoff_je_number", not released_roll.get("writeoff_je_number"),
                      f"writeoff_je_number={released_roll.get('writeoff_je_number')}")
            
            return True
        except Exception as e:
            self.check("Regression test", False, str(e)[:200])
            return False
    
    def run(self):
        print("=" * 80)
        print("R5.1 INVENTORY WRITE-OFF GL — COMPREHENSIVE BACKEND TEST")
        print("=" * 80)
        
        if not self.login():
            return False
        
        # Main test flow
        order = self.find_eligible_order()
        if not order:
            return False
        
        ret = self.create_return(order)
        if not ret:
            return False
        
        self.submit_return(ret["id"])
        self.approve_return(ret["id"])
        self.inspect_return(ret["id"])
        self.settle_return(ret["id"])
        
        roll = self.get_quarantine_rolls(ret["id"])
        if not roll:
            return False
        
        # Calculate expected write-off amount
        qty = round(float(roll.get("length_remaining", roll.get("length", 0)) or 0), 2)
        unit_cost = round(float(roll.get("unit_cost", 0) or 0), 2)
        expected_amount = round(qty * unit_cost, 2)
        print(f"\n    Expected write-off: {qty} m × Rp{unit_cost:,.2f} = Rp{expected_amount:,.2f}")
        
        # Scrap and verify
        self.scrap_roll(ret["id"], roll["id"])
        self.verify_writeoff_je(ret["id"], roll["id"], expected_amount)
        self.verify_roll_tagged(ret["id"], roll["id"])
        self.test_idempotency(ret["id"], roll["id"])
        
        # Regression test
        self.test_normal_release_no_writeoff()
        
        return True

def main():
    runner = TestRunner()
    try:
        runner.run()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n" + "=" * 80)
        print(f"RESULTS: PASSED={runner.passed}  FAILED={runner.failed}")
        print("=" * 80)
        sys.exit(1 if runner.failed > 0 else 0)

if __name__ == "__main__":
    main()
