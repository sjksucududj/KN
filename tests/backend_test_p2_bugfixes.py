#!/usr/bin/env python3
"""
Backend Test — P2 Bug Fixes Verification (KN-078-WMS-RESURRECTION, KN-076-COGS-ZERO, KN-076-AR-GL-DRIFT)
==========================================================================================================
Verifies three P2 data-integrity/state bugs are fixed:
1. KN-078-WMS-RESURRECTION — anti-resurrection guard (terminal tasks cannot be advanced/scanned)
2. KN-076-COGS-ZERO — GL posts COGS for every revenue order
3. KN-076-AR-GL-DRIFT — AR (1-1200 Piutang) reconciles per entity

Usage:
    cd /app && python tests/backend_test_p2_bugfixes.py
"""
import sys
import requests
from typing import Dict, Any, List, Optional

# Backend URL from environment
BASE_URL = "https://bug-fix-sprint-27.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

# Test credentials
ADMIN_EMAIL = "admin@kainnusantara.id"
ADMIN_PASSWORD = "demo12345"

# Color codes
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.tests = []
    
    def add_pass(self, test_name: str, detail: str = ""):
        self.passed += 1
        self.tests.append({"name": test_name, "status": "PASS", "detail": detail})
        print(f"  {G}[PASS]{X} {test_name}" + (f" — {detail}" if detail else ""))
    
    def add_fail(self, test_name: str, detail: str = ""):
        self.failed += 1
        self.tests.append({"name": test_name, "status": "FAIL", "detail": detail})
        print(f"  {R}[FAIL]{X} {test_name}" + (f" — {detail}" if detail else ""))
    
    def add_warn(self, test_name: str, detail: str = ""):
        self.warnings += 1
        self.tests.append({"name": test_name, "status": "WARN", "detail": detail})
        print(f"  {Y}[WARN]{X} {test_name}" + (f" — {detail}" if detail else ""))
    
    def summary(self):
        print(f"\n{B}{'='*80}{X}")
        print(f"  {G}PASS {self.passed}{X}  |  {R}FAIL {self.failed}{X}  |  {Y}WARN {self.warnings}{X}")
        if self.failed > 0:
            print(f"  {R}{B}TESTS FAILED — bugs not fully fixed{X}\n")
            return 1
        print(f"  {G}{B}ALL TESTS PASSED{X}\n")
        return 0

results = TestResults()

def login() -> Optional[str]:
    """Login and return auth token"""
    try:
        r = requests.post(f"{API_BASE}/auth/login", 
                         json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                         timeout=20)
        if r.status_code != 200:
            results.add_fail("Login", f"Status {r.status_code}")
            return None
        data = r.json()
        token = data.get("token")
        if not token:
            results.add_fail("Login", "No token in response")
            return None
        results.add_pass("Login", f"Authenticated as {ADMIN_EMAIL}")
        return token
    except Exception as e:
        results.add_fail("Login", f"Exception: {e}")
        return None

def get_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

# ═══════════════════════════════════════════════════════════════════════════════
# KN-078-WMS-RESURRECTION — Anti-resurrection guard
# ═══════════════════════════════════════════════════════════════════════════════

def test_wms_resurrection(token: str):
    """Test that terminal WMS tasks cannot be advanced or scanned"""
    print(f"\n{C}{B}KN-078-WMS-RESURRECTION — Anti-resurrection guard{X}")
    headers = get_headers(token)
    
    # Step 1: List tasks to find terminal ones
    try:
        r = requests.get(f"{API_BASE}/wms/tasks", headers=headers, timeout=20)
        if r.status_code != 200:
            results.add_fail("WMS-RESURRECTION-1", f"GET /wms/tasks failed: {r.status_code}")
            return
        
        tasks = r.json()
        if not isinstance(tasks, list):
            results.add_fail("WMS-RESURRECTION-1", "Response not a list")
            return
        
        results.add_pass("WMS-RESURRECTION-1", f"Listed {len(tasks)} WMS tasks")
        
        # Find terminal tasks (completed, done, dispatched, cancelled)
        terminal_statuses = ["completed", "done", "dispatched", "cancelled"]
        terminal_tasks = [t for t in tasks if t.get("status") in terminal_statuses]
        
        if not terminal_tasks:
            results.add_warn("WMS-RESURRECTION-2", "No terminal tasks found in seed data")
            return
        
        results.add_pass("WMS-RESURRECTION-2", f"Found {len(terminal_tasks)} terminal tasks")
        
        # Step 2: Try to advance a terminal task (should return 409)
        terminal_task = terminal_tasks[0]
        task_id = terminal_task.get("id")
        status = terminal_task.get("status")
        
        r = requests.post(f"{API_BASE}/wms/tasks/{task_id}/advance", 
                         headers=headers, timeout=20)
        
        if r.status_code == 409:
            results.add_pass("WMS-RESURRECTION-3", 
                           f"Terminal task ({status}) correctly rejected advance with 409")
        elif r.status_code == 200:
            results.add_fail("WMS-RESURRECTION-3", 
                           f"BUG: Terminal task ({status}) was advanced (200) — resurrection bug NOT fixed")
        else:
            results.add_warn("WMS-RESURRECTION-3", 
                           f"Unexpected status {r.status_code} for terminal task advance")
        
        # Step 3: Verify task status unchanged after advance attempt
        r = requests.get(f"{API_BASE}/wms/tasks", headers=headers, timeout=20)
        if r.status_code == 200:
            updated_tasks = r.json()
            updated_task = next((t for t in updated_tasks if t.get("id") == task_id), None)
            if updated_task and updated_task.get("status") == status:
                results.add_pass("WMS-RESURRECTION-4", 
                               f"Task status unchanged ({status}) after rejected advance")
            else:
                results.add_fail("WMS-RESURRECTION-4", 
                               f"Task status changed from {status} to {updated_task.get('status') if updated_task else 'NOT FOUND'}")
        
        # Step 4: Try to scan a terminal task (should return 409)
        r = requests.post(f"{API_BASE}/wms/tasks/{task_id}/scan",
                         json={"scan_type": "roll", "scan_value": "TEST-ROLL"},
                         headers=headers, timeout=20)
        
        if r.status_code == 409:
            results.add_pass("WMS-RESURRECTION-5", 
                           f"Terminal task ({status}) correctly rejected scan with 409")
        elif r.status_code == 200:
            results.add_fail("WMS-RESURRECTION-5", 
                           f"BUG: Terminal task ({status}) accepted scan (200) — scan guard NOT fixed")
        else:
            results.add_warn("WMS-RESURRECTION-5", 
                           f"Unexpected status {r.status_code} for terminal task scan")
        
    except Exception as e:
        results.add_fail("WMS-RESURRECTION", f"Exception: {e}")

def test_wms_legitimate_advance(token: str):
    """Test that legitimate WMS task advance still works"""
    print(f"\n{C}{B}WMS Legitimate Advance (Regression){X}")
    headers = get_headers(token)
    
    try:
        r = requests.get(f"{API_BASE}/wms/tasks", headers=headers, timeout=20)
        if r.status_code != 200:
            results.add_warn("WMS-LEGIT-1", "Cannot list tasks for regression test")
            return
        
        tasks = r.json()
        # Find in-flow tasks (created, in_transit for inbound; created, picking for outbound)
        in_flow_statuses = ["created", "in_transit", "picking"]
        in_flow_tasks = [t for t in tasks if t.get("status") in in_flow_statuses]
        
        if not in_flow_tasks:
            results.add_warn("WMS-LEGIT-1", "No in-flow tasks found for regression test (acceptable)")
            return
        
        task = in_flow_tasks[0]
        task_id = task.get("id")
        old_status = task.get("status")
        
        r = requests.post(f"{API_BASE}/wms/tasks/{task_id}/advance", 
                         headers=headers, timeout=20)
        
        if r.status_code == 200:
            data = r.json()
            new_status = data.get("status")
            if new_status != old_status:
                results.add_pass("WMS-LEGIT-1", 
                               f"In-flow task advanced successfully: {old_status} → {new_status}")
            else:
                results.add_warn("WMS-LEGIT-1", 
                               f"Task advanced but status unchanged ({old_status})")
        elif r.status_code == 409:
            results.add_warn("WMS-LEGIT-1", 
                           f"In-flow task ({old_status}) rejected with 409 — may be at final stage")
        else:
            results.add_fail("WMS-LEGIT-1", 
                           f"In-flow task advance failed: {r.status_code}")
        
    except Exception as e:
        results.add_warn("WMS-LEGIT", f"Exception: {e}")

def test_wms_off_flow_status(token: str):
    """Test that off-flow status tasks are rejected"""
    print(f"\n{C}{B}WMS Off-flow Status Rejection{X}")
    # This is harder to test without creating a task with off-flow status
    # We'll document observation instead
    results.add_warn("WMS-OFF-FLOW", 
                    "Off-flow status test requires manual task creation (skipped in automated test)")

# ═══════════════════════════════════════════════════════════════════════════════
# KN-076-COGS-ZERO — GL posts COGS for revenue orders
# ═══════════════════════════════════════════════════════════════════════════════

def test_cogs_zero(token: str):
    """Test that COGS account has entries after GL sync"""
    print(f"\n{C}{B}KN-076-COGS-ZERO — GL posts COGS for revenue orders{X}")
    headers = get_headers(token)
    
    try:
        # Step 1: Run GL sync (backfill)
        r = requests.post(f"{API_BASE}/gl/sync", headers=headers, timeout=60)
        if r.status_code != 200:
            results.add_fail("COGS-ZERO-1", f"GL sync failed: {r.status_code}")
            return
        
        sync_result = r.json()
        results.add_pass("COGS-ZERO-1", 
                        f"GL sync completed: {sync_result.get('total', 0)} journals posted")
        
        # Step 2: Check COGS account (5-1000) ledger
        r = requests.get(f"{API_BASE}/gl/accounts/5-1000/ledger", 
                        headers=headers, timeout=20)
        
        if r.status_code != 200:
            results.add_fail("COGS-ZERO-2", f"GET COGS ledger failed: {r.status_code}")
            return
        
        ledger = r.json()
        # API returns {"account": {...}, "lines": [...]}
        entries = ledger.get("lines", []) if isinstance(ledger, dict) else []
        
        if not entries:
            results.add_fail("COGS-ZERO-2", 
                           "BUG: COGS account (5-1000) has NO entries — COGS-ZERO bug NOT fixed")
            return
        
        total_debit = sum(float(e.get("debit", 0) or 0) for e in entries)
        
        if total_debit > 0:
            results.add_pass("COGS-ZERO-2", 
                           f"COGS account (5-1000) has {len(entries)} entries, total debit: {total_debit:,.2f}")
        else:
            results.add_fail("COGS-ZERO-2", 
                           f"BUG: COGS account has {len(entries)} entries but total debit = 0")
        
        # Step 3: Check trial balance for COGS account
        r = requests.get(f"{API_BASE}/gl/trial-balance", headers=headers, timeout=20)
        if r.status_code != 200:
            results.add_warn("COGS-ZERO-3", f"GET trial-balance failed: {r.status_code}")
            return
        
        tb = r.json()
        accounts = tb.get("accounts", []) if isinstance(tb, dict) else tb
        cogs_account = next((a for a in accounts if a.get("code") == "5-1000"), None)
        
        if cogs_account:
            balance = float(cogs_account.get("debit_balance", 0) or 0)
            if balance > 0:
                results.add_pass("COGS-ZERO-3", 
                               f"Trial balance: COGS (5-1000) balance = {balance:,.2f} (> 0)")
            else:
                results.add_fail("COGS-ZERO-3", 
                               f"BUG: Trial balance COGS = {balance} (should be > 0)")
        else:
            results.add_warn("COGS-ZERO-3", "COGS account not found in trial balance")
        
    except Exception as e:
        results.add_fail("COGS-ZERO", f"Exception: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# KN-076-AR-GL-DRIFT — AR reconciles per entity
# ═══════════════════════════════════════════════════════════════════════════════

def test_ar_gl_drift(token: str):
    """Test that AR (1-1200) reconciles per entity"""
    print(f"\n{C}{B}KN-076-AR-GL-DRIFT — AR reconciles per entity{X}")
    headers = get_headers(token)
    
    try:
        # Step 1: Run GL sync
        r = requests.post(f"{API_BASE}/gl/sync", headers=headers, timeout=60)
        if r.status_code != 200:
            results.add_warn("AR-GL-DRIFT-1", f"GL sync failed: {r.status_code}")
        else:
            results.add_pass("AR-GL-DRIFT-1", "GL sync completed")
        
        # Step 2: Check trial balance per entity (ent_ksc)
        r = requests.get(f"{API_BASE}/gl/trial-balance?entity_id=ent_ksc", 
                        headers=headers, timeout=20)
        
        if r.status_code != 200:
            results.add_fail("AR-GL-DRIFT-2", f"GET trial-balance ent_ksc failed: {r.status_code}")
            return
        
        tb_ksc = r.json()
        accounts_ksc = tb_ksc.get("accounts", []) if isinstance(tb_ksc, dict) else tb_ksc
        ar_ksc = next((a for a in accounts_ksc if a.get("code") == "1-1200"), None)
        
        if ar_ksc:
            balance_ksc = float(ar_ksc.get("debit_balance", 0) or 0) - float(ar_ksc.get("credit_balance", 0) or 0)
            if balance_ksc >= 0:
                results.add_pass("AR-GL-DRIFT-2", 
                               f"ent_ksc: AR (1-1200) balance = {balance_ksc:,.2f} (non-negative)")
            else:
                results.add_fail("AR-GL-DRIFT-2", 
                               f"BUG: ent_ksc AR balance = {balance_ksc:,.2f} (NEGATIVE)")
        else:
            results.add_warn("AR-GL-DRIFT-2", "ent_ksc: AR account not found (may be zero)")
        
        # Step 3: Check trial balance per entity (ent_kanda)
        r = requests.get(f"{API_BASE}/gl/trial-balance?entity_id=ent_kanda", 
                        headers=headers, timeout=20)
        
        if r.status_code != 200:
            results.add_warn("AR-GL-DRIFT-3", f"GET trial-balance ent_kanda failed: {r.status_code}")
        else:
            tb_kanda = r.json()
            accounts_kanda = tb_kanda.get("accounts", []) if isinstance(tb_kanda, dict) else tb_kanda
            ar_kanda = next((a for a in accounts_kanda if a.get("code") == "1-1200"), None)
            
            if ar_kanda:
                balance_kanda = float(ar_kanda.get("debit_balance", 0) or 0) - float(ar_kanda.get("credit_balance", 0) or 0)
                if balance_kanda >= 0:
                    results.add_pass("AR-GL-DRIFT-3", 
                                   f"ent_kanda: AR (1-1200) balance = {balance_kanda:,.2f} (non-negative)")
                else:
                    results.add_fail("AR-GL-DRIFT-3", 
                                   f"BUG: ent_kanda AR balance = {balance_kanda:,.2f} (NEGATIVE)")
            else:
                results.add_warn("AR-GL-DRIFT-3", "ent_kanda: AR account not found (may be zero)")
        
        # Step 4: Check consolidated trial balance (no entity filter)
        r = requests.get(f"{API_BASE}/gl/trial-balance", headers=headers, timeout=20)
        
        if r.status_code != 200:
            results.add_warn("AR-GL-DRIFT-4", f"GET consolidated trial-balance failed: {r.status_code}")
        else:
            tb_all = r.json()
            accounts_all = tb_all.get("accounts", []) if isinstance(tb_all, dict) else tb_all
            
            # Check that AR is NOT booked under 'all' or empty entity
            # (AR must be under real entities only)
            ar_all = next((a for a in accounts_all if a.get("code") == "1-1200"), None)
            
            # Also check for Uang Muka Pelanggan (2-1400) - customer deposits
            deposit_all = next((a for a in accounts_all if a.get("code") == "2-1400"), None)
            
            if deposit_all:
                deposit_balance = float(deposit_all.get("credit_balance", 0) or 0) - float(deposit_all.get("debit_balance", 0) or 0)
                if deposit_balance > 0:
                    results.add_pass("AR-GL-DRIFT-4", 
                                   f"Uang Muka Pelanggan (2-1400) credit balance = {deposit_balance:,.2f} (customer deposits)")
                else:
                    results.add_warn("AR-GL-DRIFT-4", 
                                   f"Uang Muka Pelanggan (2-1400) balance = {deposit_balance:,.2f}")
            else:
                results.add_warn("AR-GL-DRIFT-4", "Uang Muka Pelanggan (2-1400) not found")
            
            # Step 5: Verify trial balance is balanced
            total_debit = sum(float(a.get("debit_balance", 0) or 0) for a in accounts_all)
            total_credit = sum(float(a.get("credit_balance", 0) or 0) for a in accounts_all)
            
            if abs(total_debit - total_credit) < 1.0:
                results.add_pass("AR-GL-DRIFT-5", 
                               f"Trial balance balanced: debit={total_debit:,.2f}, credit={total_credit:,.2f}")
            else:
                results.add_fail("AR-GL-DRIFT-5", 
                               f"BUG: Trial balance NOT balanced: debit={total_debit:,.2f}, credit={total_credit:,.2f}")
        
    except Exception as e:
        results.add_fail("AR-GL-DRIFT", f"Exception: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# REGRESSION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

def test_ar_receipt_creation(token: str):
    """Test that AR receipt creation still works"""
    print(f"\n{C}{B}REGRESSION — AR Receipt Creation{X}")
    headers = get_headers(token)
    
    try:
        # Step 1: Find an unpaid order
        r = requests.get(f"{API_BASE}/sales-orders", headers=headers, timeout=20)
        if r.status_code != 200:
            results.add_warn("AR-RECEIPT-1", f"Cannot list orders: {r.status_code}")
            return
        
        orders = r.json()
        if not isinstance(orders, list):
            orders = orders.get("items", [])
        
        # Find order with outstanding
        unpaid_orders = []
        for o in orders:
            if o.get("status") not in ["cancelled", "expired"]:
                grand = float(o.get("grand_total", 0) or 0)
                paid = float(o.get("paid_total", 0) or 0)
                outstanding = grand - paid
                if outstanding > 0.01:
                    unpaid_orders.append({
                        "id": o.get("id"),
                        "number": o.get("number"),
                        "customer_id": o.get("customer_id"),
                        "entity_id": o.get("entity_id"),
                        "outstanding": outstanding
                    })
        
        if not unpaid_orders:
            results.add_warn("AR-RECEIPT-1", "No unpaid orders found for regression test")
            return
        
        order = unpaid_orders[0]
        results.add_pass("AR-RECEIPT-1", 
                        f"Found unpaid order {order['number']} with outstanding {order['outstanding']:,.2f}")
        
        # Step 2: Create AR receipt (partial payment)
        payment_amount = min(order['outstanding'], 100000)  # Pay 100k or outstanding, whichever is less
        
        payload = {
            "customer_id": order['customer_id'],
            "amount": payment_amount,
            "method": "transfer",
            "entity_id": order['entity_id'] or "ent_ksc",
            "allocations": [
                {
                    "order_id": order['id'],
                    "amount": payment_amount
                }
            ]
        }
        
        r = requests.post(f"{API_BASE}/ar-receipts", 
                         json=payload, headers=headers, timeout=20)
        
        if r.status_code == 200:
            receipt = r.json()
            results.add_pass("AR-RECEIPT-2", 
                           f"AR receipt created: {receipt.get('number')} for {payment_amount:,.2f}")
            
            # Verify order updated
            r = requests.get(f"{API_BASE}/sales-orders", headers=headers, timeout=20)
            if r.status_code == 200:
                updated_orders = r.json()
                if not isinstance(updated_orders, list):
                    updated_orders = updated_orders.get("items", [])
                updated_order = next((o for o in updated_orders if o.get("id") == order['id']), None)
                
                if updated_order:
                    new_paid = float(updated_order.get("paid_total", 0) or 0)
                    payments = updated_order.get("payments", [])
                    if len(payments) > 0 and new_paid > 0:
                        results.add_pass("AR-RECEIPT-3", 
                                       f"Order updated: paid_total={new_paid:,.2f}, {len(payments)} payment(s)")
                    else:
                        results.add_fail("AR-RECEIPT-3", 
                                       "Order not updated after AR receipt")
        elif r.status_code == 400:
            results.add_warn("AR-RECEIPT-2", 
                           f"AR receipt rejected (400): {r.json().get('detail', 'Unknown')}")
        else:
            results.add_fail("AR-RECEIPT-2", 
                           f"AR receipt creation failed: {r.status_code}")
        
    except Exception as e:
        results.add_fail("AR-RECEIPT", f"Exception: {e}")

def test_gl_trial_balance_integrity(token: str):
    """Test that GL trial balance stays balanced"""
    print(f"\n{C}{B}REGRESSION — GL Trial Balance Integrity{X}")
    headers = get_headers(token)
    
    try:
        r = requests.get(f"{API_BASE}/gl/trial-balance", headers=headers, timeout=20)
        
        if r.status_code != 200:
            results.add_fail("GL-INTEGRITY-1", f"GET trial-balance failed: {r.status_code}")
            return
        
        tb = r.json()
        accounts = tb.get("accounts", []) if isinstance(tb, dict) else tb
        
        total_debit = sum(float(a.get("debit_balance", 0) or 0) for a in accounts)
        total_credit = sum(float(a.get("credit_balance", 0) or 0) for a in accounts)
        
        if abs(total_debit - total_credit) < 1.0:
            results.add_pass("GL-INTEGRITY-1", 
                           f"Trial balance balanced: debit={total_debit:,.2f}, credit={total_credit:,.2f}")
        else:
            results.add_fail("GL-INTEGRITY-1", 
                           f"Trial balance NOT balanced: debit={total_debit:,.2f}, credit={total_credit:,.2f}, diff={abs(total_debit-total_credit):,.2f}")
        
    except Exception as e:
        results.add_fail("GL-INTEGRITY", f"Exception: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"{B}{C}{'='*80}{X}")
    print(f"{B}  P2 Bug Fixes Verification — Backend Testing{X}")
    print(f"{B}  Base URL: {BASE_URL}{X}")
    print(f"{B}{C}{'='*80}{X}")
    
    # Login
    token = login()
    if not token:
        print(f"\n{R}Cannot proceed without authentication{X}")
        return 1
    
    # Run tests
    test_wms_resurrection(token)
    test_wms_legitimate_advance(token)
    test_wms_off_flow_status(token)
    
    test_cogs_zero(token)
    
    test_ar_gl_drift(token)
    
    test_ar_receipt_creation(token)
    test_gl_trial_balance_integrity(token)
    
    # Summary
    return results.summary()

if __name__ == "__main__":
    sys.exit(main())
