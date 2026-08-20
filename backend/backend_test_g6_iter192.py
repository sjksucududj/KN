#!/usr/bin/env python3
"""
Backend API Test — FASE G-6 Iteration 192 (Inter-Entity Transactions)
======================================================================
Testing 3 untested flows from iteration 191:
1. POST receive without warehouse task → 400 with 'tugas gudang' message
2. POST warehouse-task on 'confirmed' transaction → 200; calling twice → 400
3. Approve warehouse task → je_intercompany.posted == false, revalued_rolls >= 1
4. Create transaction for cancellation test with reason
5. Run verify_data_integrity.py --only interco → 6 PASS / 0 FAIL
"""
import os
import sys
import requests
import json
from datetime import datetime

BASE = "https://supplier-contract-ui.preview.emergentagent.com"
API = f"{BASE}/api"
PASS, FAIL = [], []

def ok(m):
    PASS.append(m)
    print(f"  ✅ [PASS] {m}")

def bad(m):
    FAIL.append(m)
    print(f"  ❌ [FAIL] {m}")

def info(m):
    print(f"  ℹ️  {m}")

class G6Tester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.confirmed_id = None
        self.confirmed_pair_id = None
        self.warehouse_task_id = None
        self.cancel_test_id = None
        self.cancel_test_pair_id = None
        
    def login(self, email="admin@kainnusantara.id", password="demo12345"):
        """Login with admin credentials"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login failed: {r.status_code} {r.text[:100]}")
                return False
            data = r.json()
            self.token = data.get("token")
            if not self.token:
                bad(f"Login response missing token")
                return False
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            ok(f"Login {email}")
            return True
        except Exception as e:
            bad(f"Login exception: {e}")
            return False
    
    def find_confirmed_transaction(self):
        """Find a 'confirmed' transaction without warehouse task"""
        info("Finding 'confirmed' transaction for testing...")
        try:
            r = self.session.get(
                f"{API}/interco/transactions",
                params={"role": "seller", "status": "confirmed"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"GET /interco/transactions failed: {r.status_code}")
                return False
            
            data = r.json()
            # Find one without warehouse_transfer_id
            for txn in data:
                if not txn.get("warehouse_transfer_id"):
                    self.confirmed_id = txn["id"]
                    self.confirmed_pair_id = txn["pair_id"]
                    ok(f"Found confirmed transaction: {txn.get('number')} (id={self.confirmed_id[:8]})")
                    return True
            
            bad("No confirmed transaction without warehouse task found")
            return False
        except Exception as e:
            bad(f"Find confirmed transaction exception: {e}")
            return False
    
    def test_receive_without_warehouse_task(self):
        """Test 1: POST receive without warehouse task → 400 with 'tugas gudang' message"""
        info("Test 1: POST /interco/transactions/{id}/receive without warehouse task")
        if not self.confirmed_id:
            bad("No confirmed transaction ID available")
            return False
        
        try:
            r = self.session.post(
                f"{API}/interco/transactions/{self.confirmed_id}/receive",
                json={"note": ""},
                timeout=30
            )
            if r.status_code != 400:
                bad(f"POST receive without warehouse task should return 400, got {r.status_code}")
                return False
            
            detail = r.json().get("detail", "").lower()
            if "tugas gudang" not in detail:
                bad(f"Error message should mention 'tugas gudang', got: {detail}")
                return False
            
            ok("POST receive without warehouse task returns 400 with 'tugas gudang' message")
            return True
        except Exception as e:
            bad(f"Test receive without warehouse task exception: {e}")
            return False
    
    def test_create_warehouse_task(self):
        """Test 2: POST warehouse-task → 200 with TRF code; calling twice → 400"""
        info("Test 2: POST /interco/transactions/{id}/warehouse-task")
        if not self.confirmed_id:
            bad("No confirmed transaction ID available")
            return False
        
        try:
            # First call should succeed
            r = self.session.post(
                f"{API}/interco/transactions/{self.confirmed_id}/warehouse-task",
                json={"note": ""},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"POST warehouse-task failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            if not data.get("code") or not data["code"].startswith("TRF-"):
                bad(f"Warehouse task should have TRF code, got: {data.get('code')}")
                return False
            
            if data.get("interco_pair_id") != self.confirmed_pair_id:
                bad(f"Warehouse task should have interco_pair_id")
                return False
            
            if data.get("status") != "waiting_approval":
                bad(f"Warehouse task status should be 'waiting_approval', got: {data.get('status')}")
                return False
            
            self.warehouse_task_id = data["id"]
            ok(f"POST warehouse-task created {data['code']} (status={data['status']})")
            
            # Second call should fail (duplicate)
            r2 = self.session.post(
                f"{API}/interco/transactions/{self.confirmed_id}/warehouse-task",
                json={"note": ""},
                timeout=30
            )
            if r2.status_code != 400:
                bad(f"POST warehouse-task (duplicate) should return 400, got {r2.status_code}")
                return False
            
            ok("POST warehouse-task (duplicate) returns 400")
            
            # Verify transaction has warehouse_transfer_code and status
            r3 = self.session.get(f"{API}/interco/transactions/{self.confirmed_id}", timeout=30)
            if r3.status_code == 200:
                txn = r3.json()
                seller = txn.get("seller", {})
                if seller.get("warehouse_transfer_code") and seller.get("warehouse_transfer_status") == "waiting_approval":
                    ok("GET transaction shows warehouse_transfer_code and status")
                else:
                    bad(f"Transaction missing warehouse_transfer_code or status")
            
            return True
        except Exception as e:
            bad(f"Test create warehouse task exception: {e}")
            return False
    
    def test_approve_warehouse_task(self):
        """Test 3: Approve warehouse task → je_intercompany.posted == false, revalued_rolls >= 1"""
        info("Test 3: POST /transfers/{id}/approve")
        if not self.warehouse_task_id:
            bad("No warehouse task ID available")
            return False
        
        try:
            r = self.session.post(
                f"{API}/transfers/{self.warehouse_task_id}/approve",
                json={"approved_by": "Siti Nurhaliza"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"POST approve warehouse task failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            je = data.get("je_intercompany", {})
            
            # Check je_intercompany.posted == false
            if je.get("posted") != False:
                bad(f"je_intercompany.posted should be false, got: {je.get('posted')}")
                return False
            ok("je_intercompany.posted == false (correct)")
            
            # Check skipped_reason contains 'G-6'
            skipped_reason = je.get("skipped_reason", "")
            if "G-6" not in skipped_reason:
                bad(f"je_intercompany.skipped_reason should contain 'G-6', got: {skipped_reason}")
                return False
            ok(f"je_intercompany.skipped_reason contains 'G-6'")
            
            # Check revalued_rolls >= 1
            revalued_rolls = je.get("revalued_rolls", 0)
            if revalued_rolls < 1:
                bad(f"je_intercompany.revalued_rolls should be >= 1, got: {revalued_rolls}")
                return False
            ok(f"je_intercompany.revalued_rolls = {revalued_rolls} (>= 1)")
            
            # Verify transaction status is 'received'
            r2 = self.session.get(f"{API}/interco/transactions/{self.confirmed_id}", timeout=30)
            if r2.status_code == 200:
                txn = r2.json()
                seller = txn.get("seller", {})
                if seller.get("status") == "received":
                    ok("Transaction status is 'received' after warehouse task approval")
                else:
                    bad(f"Transaction status should be 'received', got: {seller.get('status')}")
            
            # Verify journal has cogs and receipt
            r3 = self.session.get(f"{API}/interco/transactions/{self.confirmed_id}/journal", timeout=30)
            if r3.status_code == 200:
                journal = r3.json()
                if journal.get("cogs") and journal.get("receipt"):
                    cogs = journal["cogs"]
                    receipt = journal["receipt"]
                    # Check if balanced
                    cogs_balanced = abs(cogs.get("total_debit", 0) - cogs.get("total_credit", 0)) < 0.01
                    receipt_balanced = abs(receipt.get("total_debit", 0) - receipt.get("total_credit", 0)) < 0.01
                    if cogs_balanced and receipt_balanced:
                        ok("Journal has cogs and receipt, both balanced")
                    else:
                        bad(f"Journal cogs or receipt not balanced")
                else:
                    bad(f"Journal missing cogs or receipt")
            
            # Verify NO journal_entries with source_type='inter_company_transfer' for this transfer
            # This would require MongoDB access, so we'll skip this check in the API test
            info("(Skipping MongoDB check for inter_company_transfer journal entries)")
            
            return True
        except Exception as e:
            bad(f"Test approve warehouse task exception: {e}")
            return False
    
    def test_create_and_cancel_transaction(self):
        """Test 4: Create transaction, cancel without note → 400; cancel with note → 200"""
        info("Test 4: Create transaction for cancellation test")
        try:
            # Create new transaction
            payload = {
                "seller_entity_id": "ent_ksc",
                "buyer_entity_id": "ent_kanda",
                "pricing_mode": "at_cost",
                "items": [
                    {
                        "product_id": "prod_batik_mega",
                        "quantity": 1,
                        "unit_price": 40000
                    }
                ],
                "submit_now": True
            }
            
            r = self.session.post(f"{API}/interco/transactions", json=payload, timeout=30)
            if r.status_code != 200:
                bad(f"POST create transaction failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            self.cancel_test_id = data["seller"]["id"]
            self.cancel_test_pair_id = data["pair_id"]
            ok(f"Created transaction {data['seller']['number']} for cancellation test")
            
            # Try to cancel without note (should fail)
            r2 = self.session.post(
                f"{API}/interco/transactions/{self.cancel_test_id}/cancel",
                json={"note": ""},
                timeout=30
            )
            if r2.status_code != 400:
                bad(f"POST cancel without note should return 400, got {r2.status_code}")
                return False
            
            detail = r2.json().get("detail", "").lower()
            if "alasan" not in detail:
                bad(f"Error message should mention 'alasan', got: {detail}")
                return False
            ok("POST cancel without note returns 400 with 'alasan' message")
            
            # Cancel with note (should succeed)
            r3 = self.session.post(
                f"{API}/interco/transactions/{self.cancel_test_id}/cancel",
                json={"note": "Salah PT pembeli - dibatalkan Keuangan"},
                timeout=30
            )
            if r3.status_code != 200:
                bad(f"POST cancel with note failed: {r3.status_code} {r3.text[:200]}")
                return False
            
            data3 = r3.json()
            reversed_journals = data3.get("reversed_journals", 0)
            if reversed_journals < 2:
                bad(f"reversed_journals should be >= 2, got: {reversed_journals}")
                return False
            ok(f"POST cancel with note returns 200 with reversed_journals={reversed_journals}")
            
            # Verify in MongoDB: journal_entries with source_id regex '^{pair}:.*:reversal$'
            # and intercompany_eliminations with source_g6_pair_id={pair} should NOT exist
            # This would require MongoDB access, so we'll skip this check in the API test
            info("(Skipping MongoDB verification for reversal journals and eliminations)")
            
            return True
        except Exception as e:
            bad(f"Test create and cancel transaction exception: {e}")
            return False
    
    def test_data_integrity(self):
        """Test 5: Run verify_data_integrity.py --only interco → 6 PASS / 0 FAIL"""
        info("Test 5: Run verify_data_integrity.py --only interco")
        try:
            import subprocess
            result = subprocess.run(
                ["python", "/app/scripts/verify_data_integrity.py", "--only", "interco"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            output = result.stdout + result.stderr
            
            # Check for "PASS 6" and "FAIL 0"
            if "PASS 6" in output and "FAIL 0" in output:
                ok("verify_data_integrity.py --only interco: 6 PASS / 0 FAIL")
                return True
            else:
                # Extract PASS/FAIL counts
                import re
                pass_match = re.search(r'PASS (\d+)', output)
                fail_match = re.search(r'FAIL (\d+)', output)
                pass_count = pass_match.group(1) if pass_match else "?"
                fail_count = fail_match.group(1) if fail_match else "?"
                bad(f"verify_data_integrity.py --only interco: PASS {pass_count} / FAIL {fail_count}")
                # Print failed checks
                if fail_count != "0":
                    info("Failed checks:")
                    for line in output.split('\n'):
                        if '[FAIL]' in line:
                            info(f"  {line}")
                return False
        except Exception as e:
            bad(f"Test data integrity exception: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*70)
        print("  BACKEND API TEST — FASE G-6 Iteration 192")
        print("="*70)
        
        # Login
        if not self.login():
            return False
        
        # Find confirmed transaction
        if not self.find_confirmed_transaction():
            return False
        
        print("\n--- G-6 ITERATION 192 TESTS ---")
        self.test_receive_without_warehouse_task()
        self.test_create_warehouse_task()
        self.test_approve_warehouse_task()
        self.test_create_and_cancel_transaction()
        self.test_data_integrity()
        
        return True

def main():
    tester = G6Tester()
    tester.run_all_tests()
    
    print("\n" + "="*70)
    print(f"  HASIL: {len(PASS)} PASS | {len(FAIL)} FAIL")
    print("="*70)
    
    if FAIL:
        print("\n❌ FAILED TESTS:")
        for f in FAIL:
            print(f"   - {f}")
        return 1
    
    print("\n✅ SEMUA TEST BACKEND LULUS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
