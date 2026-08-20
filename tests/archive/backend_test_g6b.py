#!/usr/bin/env python3
"""
FASE G-6b - Backend API Testing
Tests 4 new features: Faktur Pajak Internal, Retur Antar-PT, Pengingat Settlement, Rapor Margin
"""
import requests
import sys
from datetime import datetime

# Use preview URL as specified in requirements
BASE_URL = "https://kn-dev-preview-1.preview.emergentagent.com"
API = f"{BASE_URL}/api"

# Test credentials from requirements
USERS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "manager": {"email": "manager@kainnusantara.id", "password": "demo12345"},
    "sales": {"email": "sales@kainnusantara.id", "password": "demo12345"},
    "warehouse": {"email": "warehouse@kainnusantara.id", "password": "demo12345"},
}

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add(self, name, passed, details=""):
        self.tests.append({"name": name, "passed": passed, "details": details})
        if passed:
            self.passed += 1
            print(f"✓ {name}")
            if details:
                print(f"  → {details}")
        else:
            self.failed += 1
            print(f"✗ {name}")
            if details:
                print(f"  → {details}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"FASE G-6b BACKEND API TEST RESULTS")
        print(f"{'='*60}")
        print(f"Passed: {self.passed}/{total}")
        print(f"Failed: {self.failed}/{total}")
        print(f"Success Rate: {(self.passed/total*100) if total > 0 else 0:.1f}%")
        return self.failed == 0

results = TestResults()

def login(role):
    """Login and get token - returns 'token' key as per requirements"""
    try:
        r = requests.post(f"{API}/auth/login", json=USERS[role], timeout=10)
        if r.status_code == 200:
            data = r.json()
            # Requirements specify response uses 'token' key (not access_token)
            return data.get("token")
        return None
    except Exception as e:
        print(f"Login failed for {role}: {e}")
        return None

def headers(token):
    """Get auth headers - must include X-Entity-Id: all to see twin documents"""
    return {
        "Authorization": f"Bearer {token}",
        "X-Entity-Id": "all",  # Required to see documents in both PTs
        "Content-Type": "application/json"
    }

def get_transactions(token):
    """Get interco transactions"""
    try:
        r = requests.get(f"{API}/interco/transactions", headers=headers(token), timeout=10)
        if r.status_code == 200:
            return r.json()
        return []
    except Exception:
        return []

# ═════════════════════════════════════════════════════════════════════════════
#  US-A: FAKTUR PAJAK INTERNAL
# ═════════════════════════════════════════════════════════════════════════════
def test_faktur_pajak_internal(tokens):
    """Test US-A1 & US-A2: Tax invoice issuance and VAT summary integration"""
    print("\n--- Testing Faktur Pajak Internal (US-A1, US-A2) ---")
    
    token = tokens["admin"]
    txs = get_transactions(token)
    
    # US-A1: Test blocked_reason for draft transaction
    draft = next((t for t in txs if t.get("role") == "seller" and t.get("status") == "draft"), None)
    if draft:
        try:
            r = requests.get(
                f"{API}/interco/transactions/{draft['id']}/tax-invoice",
                headers=headers(token),
                timeout=10
            )
            results.add(
                "US-A1: GET tax-invoice state for draft",
                r.status_code == 200,
                f"Status: {r.status_code}"
            )
            
            if r.status_code == 200:
                state = r.json()
                results.add(
                    "US-A1: Draft transaction blocked with reason",
                    state.get("can_issue") == False and "Faktur Internal" in state.get("blocked_reason", ""),
                    f"Blocked: {state.get('blocked_reason', '')[:80]}"
                )
                
                # Try to issue - should fail with clear message
                r2 = requests.post(
                    f"{API}/interco/transactions/{draft['id']}/tax-invoice",
                    headers=headers(token),
                    json={"nsfp": "", "kode_transaksi": "01"},
                    timeout=10
                )
                results.add(
                    "US-A1: POST tax-invoice for draft returns 400",
                    r2.status_code == 400 and "Faktur Internal" in r2.text,
                    f"Status: {r2.status_code}"
                )
        except Exception as e:
            results.add("US-A1: Test draft transaction blocking", False, str(e))
    else:
        results.add("US-A1: Find draft transaction", False, "No draft transaction found")
    
    # US-A1: Test transaction without PPN
    no_ppn = next((t for t in txs if t.get("role") == "seller" and not t.get("tax_apply")), None)
    if no_ppn:
        try:
            r = requests.get(
                f"{API}/interco/transactions/{no_ppn['id']}/tax-invoice",
                headers=headers(token),
                timeout=10
            )
            if r.status_code == 200:
                state = r.json()
                results.add(
                    "US-A1: Transaction without PPN blocked",
                    state.get("can_issue") == False and "TANPA PPN" in state.get("blocked_reason", ""),
                    f"Blocked: {state.get('blocked_reason', '')[:80]}"
                )
        except Exception as e:
            results.add("US-A1: Test no-PPN transaction", False, str(e))
    
    # US-A1 & US-A2: Test issuance for invoiced transaction with PPN
    invoiced = next((t for t in txs 
                     if t.get("role") == "seller" 
                     and t.get("status") in ("invoiced", "settled")
                     and t.get("tax_apply")
                     and not t.get("tax_faktur_out_number")), None)
    
    if invoiced:
        try:
            # Check state first
            r = requests.get(
                f"{API}/interco/transactions/{invoiced['id']}/tax-invoice",
                headers=headers(token),
                timeout=10
            )
            if r.status_code == 200:
                state = r.json()
                results.add(
                    "US-A1: Invoiced transaction can issue tax invoice",
                    state.get("can_issue") == True,
                    f"Can issue: {state.get('can_issue')}"
                )
                
                # Issue tax invoice
                r2 = requests.post(
                    f"{API}/interco/transactions/{invoiced['id']}/tax-invoice",
                    headers=headers(token),
                    json={"nsfp": "", "kode_transaksi": "01"},
                    timeout=10
                )
                results.add(
                    "US-A1: POST tax-invoice creates twin documents",
                    r2.status_code == 200,
                    f"Status: {r2.status_code}"
                )
                
                if r2.status_code == 200:
                    data = r2.json()
                    out = data.get("out", {})
                    inn = data.get("in", {})
                    
                    results.add(
                        "US-A1: Tax invoice OUT and IN have same DPP and PPN",
                        abs(out.get("dpp", 0) - inn.get("dpp", 0)) < 0.01 and
                        abs(out.get("ppn_amount", 0) - inn.get("ppn_amount", 0)) < 0.01,
                        f"OUT DPP: {out.get('dpp')}, IN DPP: {inn.get('dpp')}"
                    )
                    
                    results.add(
                        "US-A1: Tax invoices are counterparts",
                        out.get("counterpart_faktur_number") == inn.get("number"),
                        f"OUT counterpart: {out.get('counterpart_faktur_number')}"
                    )
                    
                    # US-A2: Check VAT summary integration
                    try:
                        r3 = requests.get(
                            f"{API}/tax/vat-summary",
                            headers=headers(token),
                            params={"entity_id": invoiced.get("seller_entity_id")},
                            timeout=10
                        )
                        if r3.status_code == 200:
                            vat = r3.json()
                            results.add(
                                "US-A2: VAT summary includes internal tax invoice (seller)",
                                vat.get("keluaran", {}).get("ppn", 0) >= out.get("ppn_amount", 0) - 0.01,
                                f"VAT keluaran: {vat.get('keluaran', {}).get('ppn')}"
                            )
                    except Exception as e:
                        results.add("US-A2: Check VAT summary (seller)", False, str(e))
                    
                    try:
                        r4 = requests.get(
                            f"{API}/input-tax-invoices",
                            headers=headers(token),
                            timeout=10
                        )
                        if r4.status_code == 200:
                            invoices = r4.json()
                            results.add(
                                "US-A2: Input tax invoices list includes internal invoice",
                                any(x.get("number") == inn.get("number") for x in invoices),
                                f"Found {len(invoices)} input tax invoices"
                            )
                    except Exception as e:
                        results.add("US-A2: Check input tax invoices list", False, str(e))
                    
                    # US-A1: Test duplicate issuance prevention
                    r5 = requests.post(
                        f"{API}/interco/transactions/{invoiced['id']}/tax-invoice",
                        headers=headers(token),
                        json={"nsfp": "", "kode_transaksi": "01"},
                        timeout=10
                    )
                    results.add(
                        "US-A1: Cannot issue tax invoice twice",
                        r5.status_code == 400 and "sudah terbit" in r5.text,
                        f"Status: {r5.status_code}"
                    )
                    
                    # US-A1: Test replace without reason
                    r6 = requests.post(
                        f"{API}/interco/transactions/{invoiced['id']}/tax-invoice/replace",
                        headers=headers(token),
                        json={"reason": "abc"},
                        timeout=10
                    )
                    results.add(
                        "US-A1: Replace requires reason >= 5 chars",
                        r6.status_code == 400 and "Alasan" in r6.text,
                        f"Status: {r6.status_code}"
                    )
                    
                    # US-A1: Test cancel without reason
                    r7 = requests.post(
                        f"{API}/interco/transactions/{invoiced['id']}/tax-invoice/cancel",
                        headers=headers(token),
                        json={"reason": ""},
                        timeout=10
                    )
                    results.add(
                        "US-A1: Cancel requires reason >= 5 chars",
                        r7.status_code == 400 and "Alasan" in r7.text,
                        f"Status: {r7.status_code}"
                    )
                    
                    # Clean up: cancel the tax invoice
                    r8 = requests.post(
                        f"{API}/interco/transactions/{invoiced['id']}/tax-invoice/cancel",
                        headers=headers(token),
                        json={"reason": "Pembersihan testing G-6b"},
                        timeout=10
                    )
                    results.add(
                        "US-A1: Cancel tax invoice with valid reason",
                        r8.status_code == 200,
                        f"Status: {r8.status_code}"
                    )
        except Exception as e:
            results.add("US-A1/A2: Test tax invoice issuance", False, str(e))
    else:
        results.add("US-A1: Find invoiced transaction with PPN", False, "No suitable transaction found")

# ═════════════════════════════════════════════════════════════════════════════
#  US-B: RETUR ANTAR-PT
# ═════════════════════════════════════════════════════════════════════════════
def test_retur_antar_pt(tokens):
    """Test US-B1, US-B2, US-B3: Returns between companies"""
    print("\n--- Testing Retur Antar-PT (US-B1, US-B2, US-B3) ---")
    
    admin_token = tokens["admin"]
    mgr_token = tokens["manager"]
    txs = get_transactions(admin_token)
    
    # US-B1: Test returnable validation - goods not yet moved
    not_moved = next((t for t in txs 
                      if t.get("role") == "seller" 
                      and t.get("warehouse_transfer_status") != "completed"
                      and t.get("status") in ("draft", "confirmed")), None)
    
    if not_moved:
        try:
            r = requests.get(
                f"{API}/interco/transactions/{not_moved['id']}/returnable",
                headers=headers(admin_token),
                timeout=10
            )
            results.add(
                "US-B1: GET returnable for unmoved goods",
                r.status_code == 200,
                f"Status: {r.status_code}"
            )
            
            if r.status_code == 200:
                data = r.json()
                results.add(
                    "US-B1: Unmoved goods blocked with 'Batalkan' message",
                    data.get("can_return") == False and "Batalkan" in data.get("blocked_reason", ""),
                    f"Blocked: {data.get('blocked_reason', '')[:80]}"
                )
        except Exception as e:
            results.add("US-B1: Test returnable for unmoved goods", False, str(e))
    
    # US-B1: Test returnable for completed transaction
    completed = next((t for t in txs 
                      if t.get("role") == "seller" 
                      and t.get("warehouse_transfer_status") == "completed"), None)
    
    if completed:
        try:
            r = requests.get(
                f"{API}/interco/transactions/{completed['id']}/returnable",
                headers=headers(admin_token),
                timeout=10
            )
            results.add(
                "US-B1: GET returnable for completed transaction",
                r.status_code == 200,
                f"Status: {r.status_code}"
            )
            
            if r.status_code == 200:
                data = r.json()
                results.add(
                    "US-B1: Completed transaction can return",
                    data.get("can_return") == True,
                    f"Can return: {data.get('can_return')}"
                )
                
                lines = data.get("lines", [])
                if lines:
                    line = lines[0]
                    
                    # US-B1: Test qty exceeds returnable
                    r2 = requests.post(
                        f"{API}/interco/returns",
                        headers=headers(admin_token),
                        json={
                            "interco_id": completed["id"],
                            "items": [{
                                "product_id": line["product_id"],
                                "quantity": line["qty_returnable"] + 999
                            }],
                            "reason": "Testing qty validation"
                        },
                        timeout=10
                    )
                    results.add(
                        "US-B1: POST return with qty > returnable returns 400",
                        r2.status_code == 400 and "melebihi" in r2.text,
                        f"Status: {r2.status_code}"
                    )
                    
                    # US-B1: Test reason < 5 chars
                    r3 = requests.post(
                        f"{API}/interco/returns",
                        headers=headers(admin_token),
                        json={
                            "interco_id": completed["id"],
                            "items": [{
                                "product_id": line["product_id"],
                                "quantity": 1
                            }],
                            "reason": "x"
                        },
                        timeout=10
                    )
                    results.add(
                        "US-B1: POST return requires reason >= 5 chars",
                        r3.status_code == 400 and "Alasan retur" in r3.text,
                        f"Status: {r3.status_code}"
                    )
                    
                    # US-B2: Create draft return for dual-control test
                    r4 = requests.post(
                        f"{API}/interco/returns",
                        headers=headers(admin_token),
                        json={
                            "interco_id": completed["id"],
                            "items": [{
                                "product_id": line["product_id"],
                                "quantity": 1
                            }],
                            "reason": "Testing dual-control G-6b"
                        },
                        timeout=10
                    )
                    results.add(
                        "US-B2: POST return creates draft",
                        r4.status_code == 200,
                        f"Status: {r4.status_code}"
                    )
                    
                    if r4.status_code == 200:
                        ret_data = r4.json()
                        returner = ret_data.get("returner", {})
                        receiver = ret_data.get("receiver", {})
                        
                        results.add(
                            "US-B2: Return creates twin documents",
                            returner.get("number") != receiver.get("number"),
                            f"Returner: {returner.get('number')}, Receiver: {receiver.get('number')}"
                        )
                        
                        results.add(
                            "US-B2: Return status is draft",
                            returner.get("status") == "draft",
                            f"Status: {returner.get('status')}"
                        )
                        
                        # US-B2: Test maker cannot approve own return
                        r5 = requests.post(
                            f"{API}/interco/returns/{returner['id']}/approve",
                            headers=headers(admin_token),
                            json={"note": ""},
                            timeout=10
                        )
                        results.add(
                            "US-B2: Maker cannot approve own return",
                            r5.status_code == 400 and "sendiri" in r5.text,
                            f"Status: {r5.status_code}"
                        )
                        
                        # US-B2: Manager approves (different user)
                        r6 = requests.post(
                            f"{API}/interco/returns/{returner['id']}/approve",
                            headers=headers(mgr_token),
                            json={"note": ""},
                            timeout=10
                        )
                        results.add(
                            "US-B2: Manager can approve return",
                            r6.status_code == 200,
                            f"Status: {r6.status_code}"
                        )
                        
                        if r6.status_code == 200:
                            # US-B3: Check status changed to approved
                            approved_data = r6.json()
                            results.add(
                                "US-B3: Return status becomes approved",
                                approved_data.get("returner", {}).get("status") == "approved",
                                f"Status: {approved_data.get('returner', {}).get('status')}"
                            )
                            
                            # US-B3: Create warehouse task
                            r7 = requests.post(
                                f"{API}/interco/returns/{returner['id']}/warehouse-task",
                                headers=headers(admin_token),
                                json={"note": ""},
                                timeout=10
                            )
                            results.add(
                                "US-B3: POST warehouse-task for return",
                                r7.status_code == 200,
                                f"Status: {r7.status_code}"
                            )
                            
                            # Clean up: cancel the draft return (if still draft)
                            # Note: We can't cancel approved returns
                        else:
                            # Cancel draft return for cleanup
                            r_cancel = requests.post(
                                f"{API}/interco/returns/{returner['id']}/cancel",
                                headers=headers(admin_token),
                                json={"reason": "Pembersihan testing G-6b"},
                                timeout=10
                            )
                            results.add(
                                "US-B3: Cancel draft return",
                                r_cancel.status_code == 200,
                                f"Status: {r_cancel.status_code}"
                            )
        except Exception as e:
            results.add("US-B1/B2/B3: Test return creation and approval", False, str(e))
    else:
        results.add("US-B1: Find completed transaction", False, "No completed transaction found")
    
    # US-B3: Check existing completed return from demo data
    try:
        r = requests.get(
            f"{API}/interco/returns",
            headers=headers(admin_token),
            timeout=10
        )
        if r.status_code == 200:
            returns = r.json()
            completed_ret = next((ret for ret in returns 
                                  if ret.get("status") == "completed" 
                                  and ret.get("role") == "returner"), None)
            
            if completed_ret:
                results.add(
                    "US-B3: Demo data has completed return",
                    completed_ret.get("warehouse_transfer_status") == "completed",
                    f"Return: {completed_ret.get('number')}"
                )
                
                results.add(
                    "US-B3: Completed return has returned_cost",
                    float(completed_ret.get("returned_cost", 0)) > 0,
                    f"Returned cost: {completed_ret.get('returned_cost')}"
                )
    except Exception as e:
        results.add("US-B3: Check completed return", False, str(e))

# ═════════════════════════════════════════════════════════════════════════════
#  US-C: PENGINGAT SETTLEMENT
# ═════════════════════════════════════════════════════════════════════════════
def test_pengingat_settlement(tokens):
    """Test US-C: Settlement reminders"""
    print("\n--- Testing Pengingat Settlement (US-C) ---")
    
    token = tokens["admin"]
    
    # US-C: Test GET reminders
    try:
        r = requests.get(
            f"{API}/interco/reminders",
            headers=headers(token),
            timeout=10
        )
        results.add(
            "US-C: GET /api/interco/reminders",
            r.status_code == 200,
            f"Status: {r.status_code}"
        )
        
        if r.status_code == 200:
            data = r.json()
            results.add(
                "US-C: Reminders response has required fields",
                all(k in data for k in ["rows", "overdue", "checked"]),
                f"Checked: {data.get('checked')}, Overdue: {len(data.get('overdue', []))}"
            )
            
            rows = data.get("rows", [])
            if rows:
                for row in rows:
                    results.add(
                        "US-C: Reminder row has idle_days and limit_days",
                        "idle_days" in row and "limit_days" in row,
                        f"Idle: {row.get('idle_days')}, Limit: {row.get('limit_days')}"
                    )
                    break  # Just check first row
    except Exception as e:
        results.add("US-C: GET reminders", False, str(e))
    
    # US-C: Test POST remind for a pair with outstanding balance
    try:
        r = requests.get(
            f"{API}/interco/accounts",
            headers=headers(token),
            timeout=10
        )
        if r.status_code == 200:
            accounts = r.json()
            payable = next((a for a in accounts 
                           if a.get("role") == "payable" 
                           and float(a.get("outstanding", 0)) > 0.01), None)
            
            if payable:
                payer = payable.get("from_entity_id")
                payee = payable.get("to_entity_id")
                
                r2 = requests.post(
                    f"{API}/interco/accounts/{payer}/{payee}/remind",
                    headers=headers(token),
                    json={"note": ""},
                    timeout=10
                )
                results.add(
                    "US-C: POST remind creates notification",
                    r2.status_code == 200,
                    f"Status: {r2.status_code}"
                )
                
                if r2.status_code == 200:
                    remind_data = r2.json()
                    results.add(
                        "US-C: Remind response has notified flag",
                        remind_data.get("notified") == True,
                        f"Notified: {remind_data.get('notified')}"
                    )
                    
                    # US-C: Test deduplication - second call should be deduped
                    r3 = requests.post(
                        f"{API}/interco/accounts/{payer}/{payee}/remind",
                        headers=headers(token),
                        json={"note": ""},
                        timeout=10
                    )
                    if r3.status_code == 200:
                        remind_data2 = r3.json()
                        results.add(
                            "US-C: Second remind is deduped",
                            remind_data2.get("deduped") == True,
                            f"Deduped: {remind_data2.get('deduped')}"
                        )
                
                # US-C: Test remind for zero balance (should fail)
                # Find a pair with zero balance or use invalid pair
                r4 = requests.post(
                    f"{API}/interco/accounts/{payer}/ent_invalid_test/remind",
                    headers=headers(token),
                    json={"note": ""},
                    timeout=10
                )
                results.add(
                    "US-C: Remind for zero balance returns 400",
                    r4.status_code == 400 and "sudah nol" in r4.text,
                    f"Status: {r4.status_code}"
                )
            else:
                results.add("US-C: Find payable account", False, "No payable account with outstanding balance")
    except Exception as e:
        results.add("US-C: Test remind endpoint", False, str(e))
    
    # US-C: Check job is registered
    try:
        r = requests.get(
            f"{API}/scheduler/jobs",
            headers=headers(token),
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs", []) if isinstance(data, dict) else data
            job_ids = [j.get("id") for j in jobs]
            results.add(
                "US-C: Job 'interco_settlement_reminder' is registered",
                "interco_settlement_reminder" in job_ids,
                f"Found {len(job_ids)} jobs"
            )
    except Exception as e:
        results.add("US-C: Check scheduler jobs", False, str(e))

# ═════════════════════════════════════════════════════════════════════════════
#  US-D: RAPOR MARGIN GRUP
# ═════════════════════════════════════════════════════════════════════════════
def test_rapor_margin(tokens):
    """Test US-D: Margin report"""
    print("\n--- Testing Rapor Margin Grup (US-D) ---")
    
    token = tokens["admin"]
    
    # US-D: Test GET margin-report
    try:
        r = requests.get(
            f"{API}/interco/margin-report",
            headers=headers(token),
            timeout=10
        )
        results.add(
            "US-D: GET /api/interco/margin-report",
            r.status_code == 200,
            f"Status: {r.status_code}"
        )
        
        if r.status_code == 200:
            data = r.json()
            results.add(
                "US-D: Margin report has required fields",
                all(k in data for k in ["rows", "pairs", "totals"]),
                f"Rows: {len(data.get('rows', []))}, Pairs: {len(data.get('pairs', []))}"
            )
            
            totals = data.get("totals", {})
            if totals:
                # US-D: Check margin = subtotal - cost
                margin_calc = totals.get("subtotal", 0) - totals.get("cost", 0)
                margin_actual = totals.get("margin", 0)
                results.add(
                    "US-D: margin = subtotal - cost",
                    abs(margin_calc - margin_actual) < 0.05,
                    f"Calculated: {margin_calc:.2f}, Actual: {margin_actual:.2f}"
                )
                
                # US-D: Check unrealized + realized = margin
                unrealized = totals.get("unrealized_margin", 0)
                realized = totals.get("realized_margin", 0)
                results.add(
                    "US-D: unrealized + realized = margin",
                    abs((unrealized + realized) - margin_actual) < 0.05,
                    f"Unrealized: {unrealized:.2f}, Realized: {realized:.2f}, Margin: {margin_actual:.2f}"
                )
                
                # US-D: Check elimination_gap = 0
                elim_gap = totals.get("elimination_gap", 0)
                results.add(
                    "US-D: elimination_gap should be ~0",
                    abs(elim_gap) < 0.05,
                    f"Gap: {elim_gap:.2f}"
                )
            
            rows = data.get("rows", [])
            if rows:
                for row in rows:
                    # US-D: Check unsold_ratio is between 0 and 1
                    ratio = row.get("unsold_ratio", -1)
                    results.add(
                        "US-D: unsold_ratio between 0 and 1",
                        0.0 <= ratio <= 1.0,
                        f"Ratio: {ratio:.4f} for {row.get('number')}"
                    )
                    
                    # US-D: Check margin calculation per row
                    row_margin = row.get("subtotal", 0) - row.get("cost", 0)
                    results.add(
                        "US-D: Row margin = subtotal - cost",
                        abs(row_margin - row.get("margin", 0)) < 0.05,
                        f"Margin: {row.get('margin'):.2f}"
                    )
                    
                    # US-D: Check unrealized = margin * unsold_ratio
                    expected_unrealized = row.get("margin", 0) * ratio
                    results.add(
                        "US-D: unrealized = margin * unsold_ratio",
                        abs(expected_unrealized - row.get("unrealized_margin", 0)) < 0.05,
                        f"Expected: {expected_unrealized:.2f}, Actual: {row.get('unrealized_margin'):.2f}"
                    )
                    
                    # US-D: Check elimination_gap per row
                    results.add(
                        "US-D: Row elimination_gap should be ~0",
                        abs(row.get("elimination_gap", 0)) < 0.05,
                        f"Gap: {row.get('elimination_gap', 0):.2f}"
                    )
                    break  # Just check first row in detail
    except Exception as e:
        results.add("US-D: Test margin report", False, str(e))

# ═════════════════════════════════════════════════════════════════════════════
#  US-E: RBAC
# ═════════════════════════════════════════════════════════════════════════════
def test_rbac(tokens):
    """Test US-E: Role-based access control"""
    print("\n--- Testing RBAC (US-E) ---")
    
    sales_token = tokens["sales"]
    
    # US-E: Sales cannot access returns
    try:
        r = requests.get(
            f"{API}/interco/returns",
            headers=headers(sales_token),
            timeout=10
        )
        results.add(
            "US-E: Sales cannot GET /api/interco/returns",
            r.status_code == 403,
            f"Status: {r.status_code}"
        )
    except Exception as e:
        results.add("US-E: Sales GET returns", False, str(e))
    
    try:
        r = requests.post(
            f"{API}/interco/returns",
            headers=headers(sales_token),
            json={"interco_id": "test", "items": [], "reason": "test"},
            timeout=10
        )
        results.add(
            "US-E: Sales cannot POST /api/interco/returns",
            r.status_code == 403,
            f"Status: {r.status_code}"
        )
    except Exception as e:
        results.add("US-E: Sales POST returns", False, str(e))
    
    # US-E: Sales cannot access tax invoice endpoints
    try:
        r = requests.post(
            f"{API}/interco/transactions/test_id/tax-invoice",
            headers=headers(sales_token),
            json={"nsfp": "", "kode_transaksi": "01"},
            timeout=10
        )
        results.add(
            "US-E: Sales cannot POST tax-invoice",
            r.status_code == 403,
            f"Status: {r.status_code}"
        )
    except Exception as e:
        results.add("US-E: Sales POST tax-invoice", False, str(e))

# ═════════════════════════════════════════════════════════════════════════════
#  US-F: REGRESSION G-6
# ═════════════════════════════════════════════════════════════════════════════
def test_regression_g6(tokens):
    """Test US-F: Ensure G-6 features still work"""
    print("\n--- Testing G-6 Regression (US-F) ---")
    
    token = tokens["admin"]
    
    # US-F: Test GET summary
    try:
        r = requests.get(
            f"{API}/interco/summary",
            headers=headers(token),
            timeout=10
        )
        results.add(
            "US-F: GET /api/interco/summary",
            r.status_code == 200,
            f"Status: {r.status_code}"
        )
    except Exception as e:
        results.add("US-F: GET summary", False, str(e))
    
    # US-F: Test GET transactions
    try:
        r = requests.get(
            f"{API}/interco/transactions",
            headers=headers(token),
            timeout=10
        )
        results.add(
            "US-F: GET /api/interco/transactions",
            r.status_code == 200,
            f"Status: {r.status_code}, Count: {len(r.json()) if r.status_code == 200 else 0}"
        )
    except Exception as e:
        results.add("US-F: GET transactions", False, str(e))
    
    # US-F: Test GET accounts
    try:
        r = requests.get(
            f"{API}/interco/accounts",
            headers=headers(token),
            timeout=10
        )
        results.add(
            "US-F: GET /api/interco/accounts",
            r.status_code == 200,
            f"Status: {r.status_code}, Count: {len(r.json()) if r.status_code == 200 else 0}"
        )
    except Exception as e:
        results.add("US-F: GET accounts", False, str(e))
    
    # US-F: Test GET settlements
    try:
        r = requests.get(
            f"{API}/interco/settlements",
            headers=headers(token),
            timeout=10
        )
        results.add(
            "US-F: GET /api/interco/settlements",
            r.status_code == 200,
            f"Status: {r.status_code}, Count: {len(r.json()) if r.status_code == 200 else 0}"
        )
    except Exception as e:
        results.add("US-F: GET settlements", False, str(e))
    
    # US-F: Test GET journal for a transaction
    txs = get_transactions(token)
    if txs:
        tx = txs[0]
        try:
            r = requests.get(
                f"{API}/interco/transactions/{tx['id']}/journal",
                headers=headers(token),
                timeout=10
            )
            results.add(
                "US-F: GET /api/interco/transactions/{id}/journal",
                r.status_code == 200,
                f"Status: {r.status_code}"
            )
        except Exception as e:
            results.add("US-F: GET journal", False, str(e))

def main():
    print("="*60)
    print("FASE G-6b - Backend API Testing")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Login all users
    print("\n--- Logging in users ---")
    tokens = {}
    for role in USERS.keys():
        token = login(role)
        if token:
            tokens[role] = token
            print(f"✓ Logged in as {role}")
        else:
            print(f"✗ Failed to login as {role}")
            return 1
    
    # Run tests
    test_faktur_pajak_internal(tokens)
    test_retur_antar_pt(tokens)
    test_pengingat_settlement(tokens)
    test_rapor_margin(tokens)
    test_rbac(tokens)
    test_regression_g6(tokens)
    
    # Print summary
    success = results.summary()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
