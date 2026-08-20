"""
Comprehensive Vendor Bill GL Posting Test

This test creates a complete flow:
1. Find/approve a PO
2. Receive goods (GR)
3. Create vendor bill
4. Submit/approve bill
5. VERIFY GL journal is created (CRITICAL TEST)

Bug being tested: routers/vendor_bills.py was missing `from services import gl_service`
→ NameError silently swallowed → bill posted but NO GL journal created
"""
import requests
import sys
from datetime import datetime
from typing import Dict, Any, Optional

BASE_URL = "http://localhost:8001/api"
LOGIN_EMAIL = "admin@kainnusantara.id"
LOGIN_PASSWORD = "demo12345"

class ComprehensiveVendorBillGLTester:
    def __init__(self):
        self.token = None
        self.test_results = []

    def log(self, message, level="INFO"):
        prefix = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "FAIL": "❌",
            "WARN": "⚠️",
            "CRITICAL": "🔴"
        }.get(level, "•")
        print(f"{prefix} {message}")

    def api_call(self, method: str, endpoint: str, data=None, params=None) -> tuple:
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
            else:
                return False, None

            return True, response
        except Exception as e:
            self.log(f"Exception: {str(e)}", "FAIL")
            return False, None

    def login(self):
        self.log("\n=== AUTHENTICATION ===", "INFO")
        success, response = self.api_call("POST", "/auth/login", 
                                         data={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD})
        if success and response and response.status_code == 200:
            self.token = response.json().get('token')
            self.log(f"Login successful", "SUCCESS")
            return True
        self.log("Login failed", "FAIL")
        return False

    def get_or_create_receivable_po(self) -> Optional[Dict[str, Any]]:
        """Find a PO that can be received, or approve one"""
        self.log("\n=== FINDING/PREPARING PO FOR RECEIVING ===", "INFO")
        
        success, response = self.api_call("GET", "/purchase-orders")
        if not success or response.status_code != 200:
            self.log("Failed to get POs", "FAIL")
            return None

        pos = response.json()
        self.log(f"Found {len(pos)} POs", "INFO")

        # Look for PO in 'receiving' status (approved, ready to receive)
        for po in pos:
            if po.get('status') == 'receiving':
                self.log(f"Found PO in 'receiving' status: {po.get('id')}", "SUCCESS")
                return po

        # Look for PO waiting approval
        for po in pos:
            if po.get('status') == 'waiting_approval':
                self.log(f"Found PO waiting approval: {po.get('id')}, will try to approve", "INFO")
                # Try to approve it
                success, resp = self.api_call("POST", f"/purchase-orders/{po.get('id')}/approve",
                                             data={"decision": "approve", "note": "Test approval"})
                if success and resp.status_code == 200:
                    approved_po = resp.json()
                    self.log(f"PO approved, status: {approved_po.get('status')}", "SUCCESS")
                    return approved_po
                else:
                    self.log(f"Failed to approve PO: {resp.status_code if resp else 'no response'}", "WARN")

        self.log("No suitable PO found", "WARN")
        return None

    def receive_goods(self, po: Dict[str, Any]) -> bool:
        """Create goods receipt for PO"""
        self.log(f"\n=== RECEIVING GOODS FOR PO {po.get('id')} ===", "INFO")
        
        # Get PO details
        success, response = self.api_call("GET", f"/purchase-orders/{po.get('id')}")
        if not success or response.status_code != 200:
            self.log("Failed to get PO details", "FAIL")
            return False

        po_detail = response.json()
        items = po_detail.get('items', [])
        
        if not items:
            self.log("PO has no items", "FAIL")
            return False

        # Prepare GR payload - receive all items
        gr_items = []
        for item in items:
            qty = float(item.get('qty') or item.get('quantity') or 0)
            if qty > 0:
                gr_items.append({
                    "product_id": item.get('product_id'),
                    "sku": item.get('sku'),
                    "product_name": item.get('product_name'),
                    "qty_received": qty,  # Receive full quantity
                    "uom": item.get('uom', 'meter'),
                    "unit_cost": float(item.get('unit_price', 0))
                })

        if not gr_items:
            self.log("No items to receive", "FAIL")
            return False

        # Create GR via inbound task
        gr_payload = {
            "po_id": po.get('id'),
            "type": "goods_receipt",
            "items": gr_items,
            "notes": "Test goods receipt for GL posting verification"
        }

        self.log(f"Creating GR with {len(gr_items)} items", "INFO")
        success, response = self.api_call("POST", "/inbound/tasks", data=gr_payload)
        
        if not success:
            self.log("Failed to create GR task", "FAIL")
            return False

        if response.status_code != 200:
            self.log(f"GR creation failed: {response.status_code} - {response.text[:200]}", "FAIL")
            return False

        gr_task = response.json()
        self.log(f"GR task created: {gr_task.get('id')}", "SUCCESS")

        # Complete the GR task
        task_id = gr_task.get('id')
        success, response = self.api_call("POST", f"/inbound/tasks/{task_id}/complete")
        
        if success and response.status_code == 200:
            self.log(f"GR task completed", "SUCCESS")
            return True
        else:
            self.log(f"Failed to complete GR: {response.status_code if response else 'no response'}", "WARN")
            # Even if completion fails, the GR might be created
            return True

    def create_and_post_vendor_bill(self, po: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create vendor bill and post it"""
        self.log(f"\n=== CREATING VENDOR BILL FOR PO {po.get('id')} ===", "INFO")
        
        # Get billing context
        success, response = self.api_call("GET", f"/purchase-orders/{po.get('id')}/billing-context")
        if not success or response.status_code != 200:
            self.log(f"Failed to get billing context: {response.status_code if response else 'no response'}", "FAIL")
            return None

        context = response.json()
        billable_qty = float(context.get('billable_qty', 0))
        
        if billable_qty <= 0:
            self.log(f"No billable quantity (billable_qty={billable_qty})", "WARN")
            self.log("This might mean goods haven't been received yet", "WARN")
            return None

        self.log(f"Billable qty: {billable_qty}, Total: {context.get('total_amount')}", "INFO")

        # Build bill payload
        bill_items = []
        for item in context.get('items', []):
            qty = float(item.get('billable_qty', 0))
            if qty > 0:
                bill_items.append({
                    "product_id": item.get('product_id'),
                    "sku": item.get('sku'),
                    "product_name": item.get('product_name'),
                    "qty": qty,
                    "unit_price": float(item.get('unit_price', 0)),
                    "uom": item.get('uom', 'meter')
                })

        bill_data = {
            "po_id": po.get('id'),
            "supplier_id": context.get('supplier_id'),
            "supplier_name": context.get('supplier_name'),
            "bill_date": datetime.now().isoformat(),
            "due_date": datetime.now().isoformat(),
            "items": bill_items,
            "notes": "Test bill for GL posting verification"
        }

        # Create bill
        success, response = self.api_call("POST", "/vendor-bills", data=bill_data)
        if not success or response.status_code != 200:
            self.log(f"Failed to create bill: {response.status_code if response else 'no response'}", "FAIL")
            if response:
                self.log(f"Error: {response.text[:300]}", "FAIL")
            return None

        bill = response.json()
        bill_id = bill.get('id')
        bill_number = bill.get('bill_number')
        self.log(f"Bill created: {bill_number} (ID: {bill_id})", "SUCCESS")
        self.log(f"  Status: {bill.get('status')}, Grand total: {bill.get('grand_total')}", "INFO")

        # Submit bill
        self.log(f"Submitting bill {bill_id}...", "INFO")
        success, response = self.api_call("POST", f"/vendor-bills/{bill_id}/submit")
        if not success or response.status_code != 200:
            self.log(f"Failed to submit bill: {response.status_code if response else 'no response'}", "FAIL")
            return None

        submitted_bill = response.json()
        status = submitted_bill.get('status')
        approval_status = submitted_bill.get('approval_status')
        self.log(f"Bill submitted - Status: {status}, Approval: {approval_status}", "INFO")

        # If pending approval, approve it
        if status == 'pending_approval':
            self.log(f"Bill needs approval, approving...", "INFO")
            success, response = self.api_call("POST", f"/vendor-bills/{bill_id}/approve",
                                             data={"decision": "approve", "note": "Test approval"})
            if success and response.status_code == 200:
                approved_bill = response.json()
                self.log(f"Bill approved - Status: {approved_bill.get('status')}", "SUCCESS")
                return approved_bill
            else:
                self.log(f"Failed to approve bill", "WARN")
                return submitted_bill

        return submitted_bill

    def verify_gl_journal_exists(self, bill: Dict[str, Any]) -> bool:
        """CRITICAL TEST: Verify GL journal was created for vendor bill"""
        self.log(f"\n{'='*80}", "CRITICAL")
        self.log(f"CRITICAL TEST: VERIFYING GL JOURNAL FOR VENDOR BILL", "CRITICAL")
        self.log(f"{'='*80}", "CRITICAL")
        
        bill_id = bill.get('id')
        bill_number = bill.get('bill_number')
        grand_total = float(bill.get('grand_total', 0))
        status = bill.get('status')

        self.log(f"Bill: {bill_number} (ID: {bill_id})", "INFO")
        self.log(f"Status: {status}, Grand Total: {grand_total:,.2f}", "INFO")

        if status != 'posted':
            self.log(f"⚠️  Bill status is '{status}', not 'posted' - GL journal may not be created yet", "WARN")
            return False

        # Get all GL journal entries
        success, response = self.api_call("GET", "/gl/journal")
        if not success or response.status_code != 200:
            self.log(f"Failed to get GL journal entries", "FAIL")
            return False

        entries = response.json()
        self.log(f"Total GL entries in system: {len(entries)}", "INFO")

        # Find entry for this vendor bill
        bill_entry = None
        for entry in entries:
            if entry.get('source_type') == 'vendor_bill' and entry.get('source_id') == bill_id:
                bill_entry = entry
                break

        if not bill_entry:
            self.log(f"", "CRITICAL")
            self.log(f"❌❌❌ CRITICAL FAILURE ❌❌❌", "CRITICAL")
            self.log(f"NO GL JOURNAL FOUND FOR VENDOR BILL {bill_number}", "CRITICAL")
            self.log(f"", "CRITICAL")
            self.log(f"This indicates the bug is NOT FIXED:", "CRITICAL")
            self.log(f"  - gl_service.post_vendor_bill() was NOT called", "CRITICAL")
            self.log(f"  - OR the import is still missing", "CRITICAL")
            self.log(f"  - OR there's a NameError being silently swallowed", "CRITICAL")
            self.log(f"", "CRITICAL")
            
            # Check backend logs for errors
            self.log(f"Checking backend logs for errors...", "INFO")
            try:
                import subprocess
                result = subprocess.run(
                    ["grep", "-A", "2", "Gagal posting GL vendor bill", "/var/log/supervisor/backend.err.log"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    self.log(f"Found GL posting error in logs:", "CRITICAL")
                    for line in result.stdout.strip().split('\n')[-10:]:
                        self.log(f"  {line}", "FAIL")
                else:
                    self.log(f"No 'Gagal posting GL' errors in logs", "INFO")
                    self.log(f"This suggests the error is being swallowed silently", "WARN")
            except:
                pass

            return False

        # GL Journal found!
        self.log(f"", "SUCCESS")
        self.log(f"✅✅✅ GL JOURNAL FOUND ✅✅✅", "SUCCESS")
        self.log(f"", "SUCCESS")
        self.log(f"Journal Number: {bill_entry.get('number')}", "SUCCESS")
        self.log(f"Journal ID: {bill_entry.get('id')}", "INFO")
        self.log(f"Date: {bill_entry.get('date')}", "INFO")
        self.log(f"Description: {bill_entry.get('description')}", "INFO")

        # Verify balanced
        total_debit = float(bill_entry.get('total_debit', 0))
        total_credit = float(bill_entry.get('total_credit', 0))
        balanced = abs(total_debit - total_credit) < 0.01

        self.log(f"", "INFO")
        self.log(f"Journal Amounts:", "INFO")
        self.log(f"  Total Debit:  {total_debit:>15,.2f}", "INFO")
        self.log(f"  Total Credit: {total_credit:>15,.2f}", "INFO")
        self.log(f"  Balanced: {balanced}", "SUCCESS" if balanced else "FAIL")

        if not balanced:
            self.log(f"❌ Journal is NOT balanced!", "FAIL")
            return False

        # Verify amounts match
        if abs(total_credit - grand_total) > 0.5:
            self.log(f"⚠️  Warning: Journal credit ({total_credit:,.2f}) != bill grand_total ({grand_total:,.2f})", "WARN")

        # Analyze journal lines
        lines = bill_entry.get('lines', [])
        self.log(f"", "INFO")
        self.log(f"Journal Lines ({len(lines)} lines):", "INFO")

        accounts_summary = {}
        for line in lines:
            acc_code = line.get('account_code')
            acc_name = line.get('account_name')
            debit = float(line.get('debit', 0))
            credit = float(line.get('credit', 0))
            desc = line.get('description', '')

            if acc_code not in accounts_summary:
                accounts_summary[acc_code] = {'name': acc_name, 'debit': 0, 'credit': 0}
            accounts_summary[acc_code]['debit'] += debit
            accounts_summary[acc_code]['credit'] += credit

        for code, data in sorted(accounts_summary.items()):
            if data['debit'] > 0:
                self.log(f"  Dr {code:8} ({data['name']:30}): {data['debit']:>12,.2f}", "INFO")
            if data['credit'] > 0:
                self.log(f"  Cr {code:8} ({data['name']:30}): {data['credit']:>12,.2f}", "INFO")

        # Verify expected accounts
        self.log(f"", "INFO")
        self.log(f"Account Verification:", "INFO")
        
        # Expected: Dr 2-1150 (GR-IR), Dr 1-1500 (PPN Masukan), Cr 2-1100 (Hutang Usaha)
        has_grir_dr = '2-1150' in accounts_summary and accounts_summary['2-1150']['debit'] > 0
        has_ppn_dr = '1-1500' in accounts_summary and accounts_summary['1-1500']['debit'] > 0
        has_ap_cr = '2-1100' in accounts_summary and accounts_summary['2-1100']['credit'] > 0

        if has_grir_dr:
            self.log(f"  ✅ Dr 2-1150 (GR-IR) present", "SUCCESS")
        else:
            self.log(f"  ⚠️  Dr 2-1150 (GR-IR) missing", "WARN")

        if has_ppn_dr:
            self.log(f"  ✅ Dr 1-1500 (PPN Masukan) present", "SUCCESS")
        else:
            self.log(f"  ℹ️  Dr 1-1500 (PPN Masukan) not present (may be zero PPN)", "INFO")

        if has_ap_cr:
            self.log(f"  ✅ Cr 2-1100 (Hutang Usaha) present", "SUCCESS")
        else:
            self.log(f"  ❌ Cr 2-1100 (Hutang Usaha) MISSING", "FAIL")

        # Overall result
        if balanced and has_ap_cr:
            self.log(f"", "SUCCESS")
            self.log(f"✅✅✅ GL JOURNAL VERIFICATION PASSED ✅✅✅", "SUCCESS")
            self.log(f"The bug fix is WORKING correctly!", "SUCCESS")
            self.log(f"", "SUCCESS")
            return True
        else:
            self.log(f"", "WARN")
            self.log(f"⚠️  GL journal exists but has issues", "WARN")
            return False

    def run_full_test(self):
        """Run complete end-to-end test"""
        self.log("\n" + "="*80, "INFO")
        self.log("COMPREHENSIVE VENDOR BILL GL POSTING TEST", "INFO")
        self.log("="*80, "INFO")

        # Login
        if not self.login():
            return False

        # Get or prepare PO
        po = self.get_or_create_receivable_po()
        if not po:
            self.log("\n❌ Cannot proceed: No suitable PO available", "FAIL")
            return False

        # Receive goods
        if not self.receive_goods(po):
            self.log("\n⚠️  Goods receipt may have failed, but continuing...", "WARN")

        # Wait a moment for GR to process
        import time
        time.sleep(2)

        # Create and post vendor bill
        bill = self.create_and_post_vendor_bill(po)
        if not bill:
            self.log("\n❌ Cannot proceed: Failed to create/post vendor bill", "FAIL")
            return False

        # CRITICAL TEST: Verify GL journal
        result = self.verify_gl_journal_exists(bill)

        # Final summary
        self.log("\n" + "="*80, "INFO")
        self.log("TEST RESULT", "INFO")
        self.log("="*80, "INFO")
        
        if result:
            self.log("✅✅✅ TEST PASSED ✅✅✅", "SUCCESS")
            self.log("The bug fix is WORKING: GL journals are being created for vendor bills", "SUCCESS")
        else:
            self.log("❌❌❌ TEST FAILED ❌❌❌", "CRITICAL")
            self.log("The bug fix is NOT working: GL journals are NOT being created", "CRITICAL")
        
        self.log("="*80, "INFO")
        return result

def main():
    tester = ComprehensiveVendorBillGLTester()
    result = tester.run_full_test()
    return 0 if result else 1

if __name__ == "__main__":
    sys.exit(main())
