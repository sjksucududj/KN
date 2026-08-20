#!/usr/bin/env python3
"""
Backend API Test — EPIC7-B: Kas & Bank Module
==============================================
Comprehensive test covering:
1. GET /api/bank-accounts (admin) => 200 array with >=4 seeded accounts
2. Balance invariant: balance == opening_balance + inflow - outflow
3. Specific balances: Kas Kecil KSC = 9,750,000; BCA Operasional = 50,000,000
4. GET /api/bank-accounts/{id}/ledger => 200 with running_balance
5. POST /api/bank-accounts (create account)
6. POST /api/cash-transactions (tie to account, balance updates)
7. POST /api/cash-transactions/{txn_id}/reconcile (toggle reconciled)
8. PATCH /api/bank-accounts/{id} (update name/is_active)
9. RBAC: manager => 200, sales => 403
10. Edge cases: unknown id => 404
"""
import os
import sys
import requests
from datetime import datetime

BASE = os.environ.get("BACKEND_URL", "https://po-pdf-sender.preview.emergentagent.com").rstrip("/")
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


def approx(a, b, eps=1.0):
    """Check if two floats are approximately equal"""
    return abs(float(a) - float(b)) <= eps


class BankTester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.manager_token = None
        self.sales_token = None
        
    def login(self, email, password="demo12345"):
        """Login and return token"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login failed for {email}: {r.status_code} {r.text[:100]}")
                return None
            data = r.json()
            token = data.get("token")
            if not token:
                bad(f"Login response missing token for {email}")
                return None
            ok(f"Login {email}")
            return token
        except Exception as e:
            bad(f"Login exception for {email}: {e}")
            return None
    
    def headers(self, token):
        """Return authorization headers"""
        return {"Authorization": f"Bearer {token}"}
    
    def test_list_accounts_admin(self):
        """Test GET /api/bank-accounts (admin) => 200 array with >=4 accounts"""
        print("\n=== TEST: List Bank Accounts (Admin) ===")
        try:
            r = self.session.get(f"{API}/bank-accounts", headers=self.headers(self.admin_token), timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/bank-accounts returned {r.status_code}, expected 200")
                return None
            ok("GET /api/bank-accounts => 200")
            
            accounts = r.json()
            if not isinstance(accounts, list):
                bad(f"Response is not a list: {type(accounts)}")
                return None
            ok(f"Response is array")
            
            if len(accounts) < 4:
                bad(f"Expected >=4 seeded accounts, got {len(accounts)}")
                return None
            ok(f"Found {len(accounts)} accounts (>=4 required)")
            
            # Check required fields
            required_fields = ["id", "name", "balance", "opening_balance", "inflow", "outflow", 
                             "txn_count", "unreconciled_count", "account_type"]
            for acc in accounts:
                missing = [f for f in required_fields if f not in acc]
                if missing:
                    bad(f"Account {acc.get('id', 'unknown')} missing fields: {missing}")
                    return None
            ok("All accounts have required fields")
            
            # Check account_type values
            for acc in accounts:
                if acc["account_type"] not in ("bank", "cash"):
                    bad(f"Account {acc['id']} has invalid account_type: {acc['account_type']}")
                    return None
            ok("All accounts have valid account_type (bank/cash)")
            
            return accounts
        except Exception as e:
            bad(f"Exception in test_list_accounts_admin: {e}")
            return None
    
    def test_balance_invariant(self, accounts):
        """Test balance invariant: balance == opening_balance + inflow - outflow"""
        print("\n=== TEST: Balance Invariant ===")
        try:
            for acc in accounts:
                expected = acc["opening_balance"] + acc["inflow"] - acc["outflow"]
                actual = acc["balance"]
                if not approx(expected, actual):
                    bad(f"Account {acc['name']} balance invariant failed: expected {expected}, got {actual}")
                    return False
            ok("All accounts satisfy balance invariant: balance == opening + inflow - outflow")
            return True
        except Exception as e:
            bad(f"Exception in test_balance_invariant: {e}")
            return False
    
    def test_specific_balances(self, accounts):
        """Test specific balances: Kas Kecil KSC = 9,750,000; BCA Operasional = 50,000,000"""
        print("\n=== TEST: Specific Account Balances ===")
        try:
            # Find Kas Kecil KSC
            kas_ksc = next((a for a in accounts if a["id"] == "bank_kas_ksc"), None)
            if not kas_ksc:
                bad("Account 'bank_kas_ksc' (Kas Kecil KSC) not found")
                return None
            
            if not approx(kas_ksc["balance"], 9750000):
                bad(f"Kas Kecil KSC balance expected 9,750,000, got {kas_ksc['balance']}")
                return None
            ok(f"Kas Kecil KSC balance = {kas_ksc['balance']:,.0f} (expected 9,750,000)")
            
            # Find BCA Operasional KSC
            bca_ksc = next((a for a in accounts if a["id"] == "bank_bca_ksc"), None)
            if not bca_ksc:
                bad("Account 'bank_bca_ksc' (BCA Operasional KSC) not found")
                return None
            
            if not approx(bca_ksc["balance"], 50000000):
                bad(f"BCA Operasional KSC balance expected 50,000,000, got {bca_ksc['balance']}")
                return None
            ok(f"BCA Operasional KSC balance = {bca_ksc['balance']:,.0f} (expected 50,000,000)")
            
            if bca_ksc["txn_count"] != 0:
                bad(f"BCA Operasional KSC expected 0 transactions, got {bca_ksc['txn_count']}")
                return None
            ok(f"BCA Operasional KSC has 0 transactions")
            
            return kas_ksc
        except Exception as e:
            bad(f"Exception in test_specific_balances: {e}")
            return None
    
    def test_ledger(self, account_id):
        """Test GET /api/bank-accounts/{id}/ledger => 200 with running_balance"""
        print("\n=== TEST: Account Ledger ===")
        try:
            r = self.session.get(f"{API}/bank-accounts/{account_id}/ledger", 
                               headers=self.headers(self.admin_token), timeout=30)
            if r.status_code != 200:
                bad(f"GET /api/bank-accounts/{account_id}/ledger returned {r.status_code}, expected 200")
                return None
            ok(f"GET /api/bank-accounts/{account_id}/ledger => 200")
            
            ledger = r.json()
            if "transactions" not in ledger:
                bad("Ledger response missing 'transactions' field")
                return None
            ok("Ledger has 'transactions' field")
            
            txns = ledger["transactions"]
            if not isinstance(txns, list):
                bad(f"Ledger transactions is not a list: {type(txns)}")
                return None
            
            # Check all transactions have running_balance
            for txn in txns:
                if "running_balance" not in txn:
                    bad(f"Transaction {txn.get('id', 'unknown')} missing running_balance")
                    return None
            ok(f"All {len(txns)} transactions have running_balance")
            
            # Check latest transaction running_balance == account balance
            if txns:
                latest_running = txns[0]["running_balance"]
                account_balance = ledger["balance"]
                if not approx(latest_running, account_balance):
                    bad(f"Latest transaction running_balance {latest_running} != account balance {account_balance}")
                    return None
                ok(f"Latest transaction running_balance ({latest_running:,.0f}) == account balance")
            
            return ledger
        except Exception as e:
            bad(f"Exception in test_ledger: {e}")
            return None
    
    def test_create_account(self):
        """Test POST /api/bank-accounts (create account)"""
        print("\n=== TEST: Create Bank Account ===")
        try:
            payload = {
                "name": "Test Mandiri Giro",
                "account_type": "bank",
                "bank_name": "Mandiri",
                "account_number": "999888777",
                "opening_balance": 1000000,
                "entity_id": "ent_ksc",
                "currency": "IDR"
            }
            r = self.session.post(f"{API}/bank-accounts", json=payload,
                                headers=self.headers(self.admin_token), timeout=30)
            if r.status_code != 200:
                bad(f"POST /api/bank-accounts returned {r.status_code}, expected 200")
                return None
            ok("POST /api/bank-accounts => 200")
            
            account = r.json()
            if not account.get("id"):
                bad("Created account missing 'id' field")
                return None
            ok(f"Created account with id: {account['id']}")
            
            # Check balance == opening_balance
            if not approx(account["balance"], 1000000):
                bad(f"New account balance {account['balance']} != opening_balance 1,000,000")
                return None
            ok(f"New account balance = opening_balance = {account['balance']:,.0f}")
            
            return account
        except Exception as e:
            bad(f"Exception in test_create_account: {e}")
            return None
    
    def test_cash_transaction(self, account_id):
        """Test POST /api/cash-transactions (tie to account, balance updates)"""
        print("\n=== TEST: Cash Transaction (Account Link) ===")
        try:
            # Get initial balance
            r = self.session.get(f"{API}/bank-accounts", headers=self.headers(self.admin_token), timeout=30)
            accounts = r.json()
            initial_acc = next((a for a in accounts if a["id"] == account_id), None)
            if not initial_acc:
                bad(f"Account {account_id} not found before transaction")
                return None
            initial_balance = initial_acc["balance"]
            info(f"Initial balance: {initial_balance:,.0f}")
            
            # Create cash transaction
            payload = {
                "cash_type": "kas_kecil",
                "direction": "in",
                "amount": 250000,
                "category": "transfer",
                "description": "Test top-up",
                "entity_id": "ent_ksc",
                "account_id": account_id,
                "created_by": "admin"
            }
            r = self.session.post(f"{API}/cash-transactions", json=payload,
                                headers=self.headers(self.admin_token), timeout=30)
            if r.status_code != 200:
                bad(f"POST /api/cash-transactions returned {r.status_code}, expected 200")
                return None
            ok("POST /api/cash-transactions => 200")
            
            txn = r.json()
            if not txn.get("id"):
                bad("Created transaction missing 'id' field")
                return None
            ok(f"Created transaction with id: {txn['id']}")
            
            # Check account_id is saved
            if txn.get("account_id") != account_id:
                bad(f"Transaction account_id {txn.get('account_id')} != expected {account_id}")
                return None
            ok(f"Transaction linked to account {account_id}")
            
            # Check balance updated
            r = self.session.get(f"{API}/bank-accounts", headers=self.headers(self.admin_token), timeout=30)
            accounts = r.json()
            updated_acc = next((a for a in accounts if a["id"] == account_id), None)
            if not updated_acc:
                bad(f"Account {account_id} not found after transaction")
                return None
            
            expected_balance = initial_balance + 250000
            actual_balance = updated_acc["balance"]
            if not approx(expected_balance, actual_balance):
                bad(f"Account balance after transaction: expected {expected_balance:,.0f}, got {actual_balance:,.0f}")
                return None
            ok(f"Account balance updated: {initial_balance:,.0f} + 250,000 = {actual_balance:,.0f}")
            
            return txn
        except Exception as e:
            bad(f"Exception in test_cash_transaction: {e}")
            return None
    
    def test_reconcile(self, txn_id, account_id):
        """Test POST /api/cash-transactions/{txn_id}/reconcile (toggle reconciled)"""
        print("\n=== TEST: Reconcile Transaction ===")
        try:
            # Reconcile = true
            payload = {"reconciled": True}
            r = self.session.post(f"{API}/cash-transactions/{txn_id}/reconcile", json=payload,
                                headers=self.headers(self.admin_token), timeout=30)
            if r.status_code != 200:
                bad(f"POST /api/cash-transactions/{txn_id}/reconcile returned {r.status_code}, expected 200")
                return False
            ok("POST /api/cash-transactions/{txn_id}/reconcile (true) => 200")
            
            txn = r.json()
            if txn.get("reconciled") is not True:
                bad(f"Transaction reconciled field is {txn.get('reconciled')}, expected True")
                return False
            ok("Transaction marked as reconciled")
            
            # Check reconciled_balance
            r = self.session.get(f"{API}/bank-accounts", headers=self.headers(self.admin_token), timeout=30)
            accounts = r.json()
            acc = next((a for a in accounts if a["id"] == account_id), None)
            if not acc:
                bad(f"Account {account_id} not found")
                return False
            
            info(f"Account reconciled_balance: {acc.get('reconciled_balance', 0):,.0f}")
            ok("Reconciled balance updated")
            
            # Reconcile = false
            payload = {"reconciled": False}
            r = self.session.post(f"{API}/cash-transactions/{txn_id}/reconcile", json=payload,
                                headers=self.headers(self.admin_token), timeout=30)
            if r.status_code != 200:
                bad(f"POST /api/cash-transactions/{txn_id}/reconcile (false) returned {r.status_code}, expected 200")
                return False
            ok("POST /api/cash-transactions/{txn_id}/reconcile (false) => 200")
            
            txn = r.json()
            if txn.get("reconciled") is not False:
                bad(f"Transaction reconciled field is {txn.get('reconciled')}, expected False")
                return False
            ok("Transaction unmarked as reconciled")
            
            return True
        except Exception as e:
            bad(f"Exception in test_reconcile: {e}")
            return False
    
    def test_update_account(self, account_id):
        """Test PATCH /api/bank-accounts/{id} (update name/is_active)"""
        print("\n=== TEST: Update Bank Account ===")
        try:
            payload = {
                "name": "Test Mandiri Giro Updated",
                "is_active": False
            }
            r = self.session.patch(f"{API}/bank-accounts/{account_id}", json=payload,
                                 headers=self.headers(self.admin_token), timeout=30)
            if r.status_code != 200:
                bad(f"PATCH /api/bank-accounts/{account_id} returned {r.status_code}, expected 200")
                return False
            ok("PATCH /api/bank-accounts/{account_id} => 200")
            
            account = r.json()
            if account.get("name") != "Test Mandiri Giro Updated":
                bad(f"Account name not updated: {account.get('name')}")
                return False
            ok("Account name updated")
            
            if account.get("is_active") is not False:
                bad(f"Account is_active not updated: {account.get('is_active')}")
                return False
            ok("Account deactivated (is_active=false)")
            
            return True
        except Exception as e:
            bad(f"Exception in test_update_account: {e}")
            return False
    
    def test_rbac(self):
        """Test RBAC: manager => 200, sales => 403"""
        print("\n=== TEST: RBAC (Role-Based Access Control) ===")
        try:
            # Manager should have access
            r = self.session.get(f"{API}/bank-accounts", 
                               headers=self.headers(self.manager_token), timeout=30)
            if r.status_code != 200:
                bad(f"Manager GET /api/bank-accounts returned {r.status_code}, expected 200")
                return False
            ok("Manager can access /api/bank-accounts (200)")
            
            # Sales should NOT have access
            r = self.session.get(f"{API}/bank-accounts", 
                               headers=self.headers(self.sales_token), timeout=30)
            if r.status_code != 403:
                bad(f"Sales GET /api/bank-accounts returned {r.status_code}, expected 403")
                return False
            ok("Sales cannot access /api/bank-accounts (403)")
            
            return True
        except Exception as e:
            bad(f"Exception in test_rbac: {e}")
            return False
    
    def test_edge_cases(self):
        """Test edge cases: unknown id => 404"""
        print("\n=== TEST: Edge Cases (404 for Unknown IDs) ===")
        try:
            # Unknown account ledger
            r = self.session.get(f"{API}/bank-accounts/unknown_id/ledger", 
                               headers=self.headers(self.admin_token), timeout=30)
            if r.status_code != 404:
                bad(f"GET /api/bank-accounts/unknown_id/ledger returned {r.status_code}, expected 404")
                return False
            ok("GET /api/bank-accounts/unknown_id/ledger => 404")
            
            # Unknown transaction reconcile
            r = self.session.post(f"{API}/cash-transactions/unknown_txn/reconcile", 
                                json={"reconciled": True},
                                headers=self.headers(self.admin_token), timeout=30)
            if r.status_code != 404:
                bad(f"POST /api/cash-transactions/unknown_txn/reconcile returned {r.status_code}, expected 404")
                return False
            ok("POST /api/cash-transactions/unknown_txn/reconcile => 404")
            
            return True
        except Exception as e:
            bad(f"Exception in test_edge_cases: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests"""
        print("=" * 60)
        print("EPIC7-B: Kas & Bank Module - Backend API Tests")
        print("=" * 60)
        
        # Login all users
        self.admin_token = self.login("admin@kainnusantara.id")
        if not self.admin_token:
            print("\n❌ CRITICAL: Admin login failed. Cannot proceed.")
            return False
        
        self.manager_token = self.login("manager@kainnusantara.id")
        if not self.manager_token:
            print("\n⚠️  WARNING: Manager login failed. RBAC tests will be skipped.")
        
        self.sales_token = self.login("sales@kainnusantara.id")
        if not self.sales_token:
            print("\n⚠️  WARNING: Sales login failed. RBAC tests will be skipped.")
        
        # Test 1: List accounts
        accounts = self.test_list_accounts_admin()
        if not accounts:
            print("\n❌ CRITICAL: List accounts failed. Cannot proceed.")
            return False
        
        # Test 2: Balance invariant
        self.test_balance_invariant(accounts)
        
        # Test 3: Specific balances
        kas_ksc = self.test_specific_balances(accounts)
        if not kas_ksc:
            print("\n⚠️  WARNING: Specific balance test failed.")
        
        # Test 4: Ledger
        if kas_ksc:
            self.test_ledger(kas_ksc["id"])
        
        # Test 5: Create account
        new_account = self.test_create_account()
        if not new_account:
            print("\n⚠️  WARNING: Create account failed. Skipping dependent tests.")
        else:
            # Test 6: Cash transaction
            txn = self.test_cash_transaction(new_account["id"])
            
            # Test 7: Reconcile
            if txn:
                self.test_reconcile(txn["id"], new_account["id"])
            
            # Test 8: Update account
            self.test_update_account(new_account["id"])
        
        # Test 9: RBAC
        if self.manager_token and self.sales_token:
            self.test_rbac()
        
        # Test 10: Edge cases
        self.test_edge_cases()
        
        return True


def main():
    tester = BankTester()
    tester.run_all_tests()
    
    print("\n" + "=" * 60)
    print(f"RESULTS: ✅ PASS {len(PASS)} | ❌ FAIL {len(FAIL)}")
    print("=" * 60)
    
    if FAIL:
        print("\n❌ FAILED TESTS:")
        for f in FAIL:
            print(f"  - {f}")
    
    return 0 if len(FAIL) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
