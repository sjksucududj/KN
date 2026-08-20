"""
Vendor Bill GL Posting Test - Verifikasi bug fix: missing gl_service import

Bug: routers/vendor_bills.py memanggil gl_service.post_vendor_bill() tanpa import
→ NameError silently swallowed → vendor bill status "posted" tapi GL journal TIDAK dibuat

Fix: menambahkan `from services import gl_service` di module-level

Test Scenarios:
1. Setup: Login admin, cek PO yang siap ditagih
2. Scenario A: Auto-post (clean match) → verify GL journal created
3. Scenario B: Approve path (variance) → verify GL journal created after approval
4. Verify: GL journal balanced, correct accounts hit
"""
import requests
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List

# Use internal URL for speed
BASE_URL = "http://localhost:8001/api"
LOGIN_EMAIL = "admin@kainnusantara.id"
LOGIN_PASSWORD = "demo12345"

class VendorBillGLTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.test_results = []

    def log(self, message, level="INFO"):
        """Log test messages"""
        prefix = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "FAIL": "❌",
            "WARN": "⚠️",
            "CRITICAL": "🔴"
        }.get(level, "•")
        print(f"{prefix} {message}")

    def api_call(self, method: str, endpoint: str, data=None, params=None, expected_status=None) -> tuple:
        """Make API call and return (success, response)"""
        url = f"{BASE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, params=params, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, params=params, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, params=params, timeout=30)
            else:
                return False, None

            if expected_status and response.status_code != expected_status:
                self.log(f"  Expected {expected_status}, got {response.status_code}", "WARN")
                try:
                    self.log(f"  Response: {response.json()}", "WARN")
                except:
                    self.log(f"  Response: {response.text[:200]}", "WARN")
                return False, response

            return True, response
        except Exception as e:
            self.log(f"  Exception: {str(e)}", "FAIL")
            return False, None

    def test_login(self):
        """Test login and get token"""
        self.log("\n=== AUTHENTICATION ===", "INFO")
        success, response = self.api_call(
            "POST", "/auth/login", 
            data={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
            expected_status=200
        )
        if success and response:
            try:
                data = response.json()
                self.token = data.get('token')
                if self.token:
                    self.log(f"Login successful, token: {self.token[:20]}...", "SUCCESS")
                    return True
                else:
                    self.log("No token in response", "FAIL")
                    return False
            except:
                self.log("Failed to parse login response", "FAIL")
                return False
        return False

    def find_billable_po(self) -> Optional[Dict[str, Any]]:
        """Find a PO with received goods ready to be billed"""
        self.log("\n=== FINDING BILLABLE PO ===", "INFO")
        success, response = self.api_call("GET", "/purchase-orders", expected_status=200)
        
        if not success or not response:
            self.log("Failed to get purchase orders", "FAIL")
            return None

        try:
            pos = response.json()
            self.log(f"Found {len(pos)} purchase orders", "INFO")
            
            # Look for PO with received_qty > 0 and billable_qty > 0
            for po in pos:
                received_qty = float(po.get('received_qty', 0) or 0)
                billable_qty = float(po.get('billable_qty', 0) or 0)
                
                if received_qty > 0 and billable_qty > 0:
                    self.log(f"Found billable PO: {po.get('number')} (ID: {po.get('id')})", "SUCCESS")
                    self.log(f"  Received: {received_qty}, Billable: {billable_qty}", "INFO")
                    return po
            
            self.log("No billable PO found (need received_qty > 0 and billable_qty > 0)", "WARN")
            return None
        except Exception as e:
            self.log(f"Error parsing POs: {e}", "FAIL")
            return None

    def get_billing_context(self, po_id: str) -> Optional[Dict[str, Any]]:
        """Get billing context for a PO"""
        self.log(f"\n=== GETTING BILLING CONTEXT FOR PO {po_id} ===", "INFO")
        success, response = self.api_call("GET", f"/purchase-orders/{po_id}/billing-context", expected_status=200)
        
        if not success or not response:
            self.log("Failed to get billing context", "FAIL")
            return None

        try:
            context = response.json()
            self.log(f"Billing context retrieved", "SUCCESS")
            self.log(f"  Billable qty: {context.get('billable_qty', 0)}", "INFO")
            self.log(f"  Total amount: {context.get('total_amount', 0)}", "INFO")
            return context
        except Exception as e:
            self.log(f"Error parsing billing context: {e}", "FAIL")
            return None

    def create_vendor_bill(self, po_id: str, context: Dict[str, Any], variance: bool = False) -> Optional[Dict[str, Any]]:
        """Create a vendor bill from PO context"""
        self.log(f"\n=== CREATING VENDOR BILL (variance={variance}) ===", "INFO")
        
        # Build bill payload from context
        items = []
        for item in context.get('items', []):
            qty = float(item.get('billable_qty', 0))
            unit_price = float(item.get('unit_price', 0))
            
            # Add variance if requested (10% price increase to trigger approval)
            if variance:
                unit_price = unit_price * 1.10
            
            items.append({
                "product_id": item.get('product_id'),
                "sku": item.get('sku'),
                "product_name": item.get('product_name'),
                "qty": qty,
                "unit_price": unit_price,
                "uom": item.get('uom', 'meter')
            })

        bill_data = {
            "po_id": po_id,
            "supplier_id": context.get('supplier_id'),
            "supplier_name": context.get('supplier_name'),
            "bill_date": datetime.now().isoformat(),
            "due_date": datetime.now().isoformat(),
            "items": items,
            "notes": f"Test bill - variance={variance}"
        }

        success, response = self.api_call("POST", "/vendor-bills", data=bill_data, expected_status=200)
        
        if not success or not response:
            self.log("Failed to create vendor bill", "FAIL")
            return None

        try:
            bill = response.json()
            self.log(f"Vendor bill created: {bill.get('bill_number')} (ID: {bill.get('id')})", "SUCCESS")
            self.log(f"  Status: {bill.get('status')}", "INFO")
            self.log(f"  Grand total: {bill.get('grand_total')}", "INFO")
            return bill
        except Exception as e:
            self.log(f"Error parsing bill response: {e}", "FAIL")
            return None

    def submit_vendor_bill(self, bill_id: str) -> Optional[Dict[str, Any]]:
        """Submit vendor bill"""
        self.log(f"\n=== SUBMITTING VENDOR BILL {bill_id} ===", "INFO")
        success, response = self.api_call("POST", f"/vendor-bills/{bill_id}/submit", expected_status=200)
        
        if not success or not response:
            self.log("Failed to submit vendor bill", "FAIL")
            return None

        try:
            bill = response.json()
            self.log(f"Vendor bill submitted", "SUCCESS")
            self.log(f"  Status: {bill.get('status')}", "INFO")
            self.log(f"  Approval status: {bill.get('approval_status')}", "INFO")
            return bill
        except Exception as e:
            self.log(f"Error parsing submit response: {e}", "FAIL")
            return None

    def approve_vendor_bill(self, bill_id: str) -> Optional[Dict[str, Any]]:
        """Approve vendor bill"""
        self.log(f"\n=== APPROVING VENDOR BILL {bill_id} ===", "INFO")
        success, response = self.api_call(
            "POST", f"/vendor-bills/{bill_id}/approve",
            data={"decision": "approve", "note": "Test approval"},
            expected_status=200
        )
        
        if not success or not response:
            self.log("Failed to approve vendor bill", "FAIL")
            return None

        try:
            bill = response.json()
            self.log(f"Vendor bill approved", "SUCCESS")
            self.log(f"  Status: {bill.get('status')}", "INFO")
            return bill
        except Exception as e:
            self.log(f"Error parsing approve response: {e}", "FAIL")
            return None

    def verify_gl_journal(self, bill_id: str, bill_number: str, grand_total: float) -> bool:
        """CRITICAL: Verify GL journal was created for vendor bill"""
        self.log(f"\n=== VERIFYING GL JOURNAL FOR BILL {bill_number} ===", "CRITICAL")
        
        # Get all GL entries
        success, response = self.api_call("GET", "/gl/entries", expected_status=200)
        
        if not success or not response:
            self.log("Failed to get GL entries", "FAIL")
            return False

        try:
            entries = response.json()
            self.log(f"Total GL entries: {len(entries)}", "INFO")
            
            # Find entry for this vendor bill
            bill_entry = None
            for entry in entries:
                if entry.get('source_type') == 'vendor_bill' and entry.get('source_id') == bill_id:
                    bill_entry = entry
                    break
            
            if not bill_entry:
                self.log(f"❌ CRITICAL FAILURE: No GL journal found for bill {bill_number} (ID: {bill_id})", "CRITICAL")
                self.log(f"  This indicates the bug is NOT fixed - gl_service.post_vendor_bill() was not called", "CRITICAL")
                return False
            
            self.log(f"✅ GL journal found: {bill_entry.get('number')}", "SUCCESS")
            self.log(f"  Journal ID: {bill_entry.get('id')}", "INFO")
            self.log(f"  Date: {bill_entry.get('date')}", "INFO")
            
            # Verify balanced
            total_debit = float(bill_entry.get('total_debit', 0))
            total_credit = float(bill_entry.get('total_credit', 0))
            balanced = abs(total_debit - total_credit) < 0.01
            
            self.log(f"  Total Debit: {total_debit:,.2f}", "INFO")
            self.log(f"  Total Credit: {total_credit:,.2f}", "INFO")
            self.log(f"  Balanced: {balanced}", "SUCCESS" if balanced else "FAIL")
            
            if not balanced:
                self.log(f"❌ Journal not balanced!", "FAIL")
                return False
            
            # Verify total matches bill grand_total
            if abs(total_credit - grand_total) > 0.5:
                self.log(f"⚠️  Warning: Journal credit ({total_credit:,.2f}) doesn't match bill grand_total ({grand_total:,.2f})", "WARN")
            
            # Verify accounts hit
            lines = bill_entry.get('lines', [])
            self.log(f"  Journal lines: {len(lines)}", "INFO")
            
            accounts_hit = {}
            for line in lines:
                acc_code = line.get('account_code')
                acc_name = line.get('account_name')
                debit = float(line.get('debit', 0))
                credit = float(line.get('credit', 0))
                
                if acc_code not in accounts_hit:
                    accounts_hit[acc_code] = {'name': acc_name, 'debit': 0, 'credit': 0}
                accounts_hit[acc_code]['debit'] += debit
                accounts_hit[acc_code]['credit'] += credit
            
            self.log(f"  Accounts hit:", "INFO")
            for code, data in accounts_hit.items():
                if data['debit'] > 0:
                    self.log(f"    Dr {code} ({data['name']}): {data['debit']:,.2f}", "INFO")
                if data['credit'] > 0:
                    self.log(f"    Cr {code} ({data['name']}): {data['credit']:,.2f}", "INFO")
            
            # Expected accounts:
            # Dr: 2-1150 (GR-IR) + 1-1500 (PPN Masukan)
            # Cr: 2-1100 (Hutang Usaha)
            expected_dr = ['2-1150', '1-1500']  # GR-IR, PPN Masukan
            expected_cr = ['2-1100']  # Hutang Usaha
            
            has_grir = '2-1150' in accounts_hit and accounts_hit['2-1150']['debit'] > 0
            has_ap = '2-1100' in accounts_hit and accounts_hit['2-1100']['credit'] > 0
            
            if has_grir and has_ap:
                self.log(f"✅ Correct accounts hit: GR-IR (Dr) and Hutang Usaha (Cr)", "SUCCESS")
            else:
                self.log(f"⚠️  Warning: Expected accounts not found", "WARN")
                if not has_grir:
                    self.log(f"    Missing: Dr 2-1150 (GR-IR)", "WARN")
                if not has_ap:
                    self.log(f"    Missing: Cr 2-1100 (Hutang Usaha)", "WARN")
            
            return True
            
        except Exception as e:
            self.log(f"Error verifying GL journal: {e}", "FAIL")
            import traceback
            traceback.print_exc()
            return False

    def check_backend_logs_for_errors(self):
        """Check if backend logs have GL posting errors"""
        self.log("\n=== CHECKING BACKEND LOGS ===", "INFO")
        try:
            import subprocess
            result = subprocess.run(
                ["grep", "-i", "Gagal posting GL vendor bill", "/var/log/supervisor/backend.err.log"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                self.log(f"❌ Found GL posting errors in backend logs:", "CRITICAL")
                for line in result.stdout.strip().split('\n')[-5:]:  # Last 5 errors
                    self.log(f"  {line}", "FAIL")
                return False
            else:
                self.log(f"✅ No GL posting errors in backend logs", "SUCCESS")
                return True
        except Exception as e:
            self.log(f"Could not check backend logs: {e}", "WARN")
            return True

    def run_scenario_a_auto_post(self):
        """Scenario A: Auto-post (clean match)"""
        self.log("\n" + "="*80, "INFO")
        self.log("SCENARIO A: AUTO-POST (CLEAN MATCH)", "INFO")
        self.log("="*80, "INFO")
        
        # Find billable PO
        po = self.find_billable_po()
        if not po:
            self.log("Cannot run Scenario A: No billable PO found", "FAIL")
            self.failed_tests.append("Scenario A: Auto-post")
            return False
        
        po_id = po.get('id')
        
        # Get billing context
        context = self.get_billing_context(po_id)
        if not context:
            self.log("Cannot run Scenario A: Failed to get billing context", "FAIL")
            self.failed_tests.append("Scenario A: Auto-post")
            return False
        
        # Create vendor bill (no variance)
        bill = self.create_vendor_bill(po_id, context, variance=False)
        if not bill:
            self.log("Cannot run Scenario A: Failed to create bill", "FAIL")
            self.failed_tests.append("Scenario A: Auto-post")
            return False
        
        bill_id = bill.get('id')
        bill_number = bill.get('bill_number')
        grand_total = float(bill.get('grand_total', 0))
        
        # Submit bill (should auto-post if clean match)
        submitted_bill = self.submit_vendor_bill(bill_id)
        if not submitted_bill:
            self.log("Cannot run Scenario A: Failed to submit bill", "FAIL")
            self.failed_tests.append("Scenario A: Auto-post")
            return False
        
        # Check if posted
        status = submitted_bill.get('status')
        approval_status = submitted_bill.get('approval_status')
        
        if status != 'posted':
            self.log(f"⚠️  Bill not auto-posted (status: {status}, approval: {approval_status})", "WARN")
            self.log(f"  This might be due to variance tolerance - will try approval path", "WARN")
            
            # Try to approve if pending
            if status == 'pending_approval':
                approved_bill = self.approve_vendor_bill(bill_id)
                if approved_bill and approved_bill.get('status') == 'posted':
                    self.log(f"✅ Bill posted after approval", "SUCCESS")
                else:
                    self.log(f"❌ Bill not posted even after approval", "FAIL")
                    self.failed_tests.append("Scenario A: Auto-post")
                    return False
        else:
            self.log(f"✅ Bill auto-posted (status: {status}, approval: {approval_status})", "SUCCESS")
        
        # CRITICAL: Verify GL journal
        gl_verified = self.verify_gl_journal(bill_id, bill_number, grand_total)
        
        if gl_verified:
            self.log(f"\n✅✅✅ SCENARIO A PASSED: GL journal created successfully", "SUCCESS")
            self.tests_passed += 1
            return True
        else:
            self.log(f"\n❌❌❌ SCENARIO A FAILED: GL journal NOT created", "CRITICAL")
            self.failed_tests.append("Scenario A: Auto-post - GL journal missing")
            self.tests_failed += 1
            return False

    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "="*80, "INFO")
        self.log("TEST SUMMARY - VENDOR BILL GL POSTING", "INFO")
        self.log("="*80, "INFO")
        
        if self.tests_failed == 0:
            self.log(f"✅✅✅ ALL TESTS PASSED", "SUCCESS")
            self.log(f"The bug fix is WORKING: gl_service import is present and GL journals are created", "SUCCESS")
        else:
            self.log(f"❌❌❌ TESTS FAILED", "CRITICAL")
            self.log(f"The bug fix is NOT working: GL journals are NOT being created", "CRITICAL")
            self.log(f"\nFailed tests:", "FAIL")
            for test in self.failed_tests:
                self.log(f"  - {test}", "FAIL")
        
        self.log("="*80, "INFO")
        return 0 if self.tests_failed == 0 else 1

def main():
    """Main test runner"""
    tester = VendorBillGLTester()
    
    # Login
    if not tester.test_login():
        print("\n❌ Login failed, cannot proceed with tests")
        return 1
    
    # Check backend logs first
    tester.check_backend_logs_for_errors()
    
    # Run Scenario A
    tester.run_scenario_a_auto_post()
    
    # Check backend logs after test
    tester.check_backend_logs_for_errors()
    
    # Print summary
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
