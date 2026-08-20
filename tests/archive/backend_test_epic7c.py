"""
Comprehensive Backend Test for EPIC 7-C: Chart of Accounts + General Ledger
Tests all backend endpoints with proper RBAC validation
"""
import requests
import sys
from typing import Dict, Any

# Use public URL
BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add(self, name: str, passed: bool, message: str = ""):
        self.tests.append({"name": name, "passed": passed, "message": message})
        if passed:
            self.passed += 1
            print(f"  ✅ PASS: {name}")
        else:
            self.failed += 1
            print(f"  ❌ FAIL: {name} - {message}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"  TOTAL: {total} | PASSED: {self.passed} | FAILED: {self.failed}")
        print(f"{'='*60}")
        return self.failed == 0

results = TestResults()

def login(email: str, password: str = "demo12345") -> str:
    """Login and return token"""
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("token", "")
        return ""
    except Exception as e:
        print(f"Login error for {email}: {e}")
        return ""

def headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

def test_chart_of_accounts(admin_token: str):
    """Test Chart of Accounts endpoints"""
    print("\n=== Chart of Accounts Tests ===")
    h = headers(admin_token)
    
    # GET /api/gl/accounts
    try:
        resp = requests.get(f"{BASE_URL}/gl/accounts", headers=h, timeout=10)
        results.add("GET /gl/accounts returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            accounts = resp.json()
            results.add("Accounts is array", isinstance(accounts, list), f"Type: {type(accounts)}")
            results.add(">=30 accounts seeded", len(accounts) >= 30, f"Count: {len(accounts)}")
            
            # Check account types
            types = {acc.get("type") for acc in accounts}
            expected_types = {"asset", "liability", "equity", "income", "expense"}
            results.add("5 account types present", types == expected_types, f"Types: {types}")
            
            # Check key accounts
            acc_map = {acc["code"]: acc for acc in accounts}
            key_accounts = ["1-1100", "1-1200", "2-1100", "2-1200", "3-1000", "4-1000", "5-1000", "6-4000"]
            for code in key_accounts:
                results.add(f"Key account {code} exists", code in acc_map, f"Missing: {code}")
            
            # Check normal_balance
            if "1-1200" in acc_map:
                results.add("Piutang (1-1200) normal_balance=debit", 
                           acc_map["1-1200"].get("normal_balance") == "debit",
                           f"Got: {acc_map['1-1200'].get('normal_balance')}")
            
            if "4-1000" in acc_map:
                results.add("Pendapatan (4-1000) normal_balance=credit",
                           acc_map["4-1000"].get("normal_balance") == "credit",
                           f"Got: {acc_map['4-1000'].get('normal_balance')}")
            
            # Check postable flags
            if "1-1100" in acc_map and "1-0000" in acc_map:
                results.add("Detail account (1-1100) is_postable=true",
                           acc_map["1-1100"].get("is_postable") is True,
                           f"Got: {acc_map['1-1100'].get('is_postable')}")
                results.add("Header account (1-0000) is_postable=false",
                           acc_map["1-0000"].get("is_postable") is False,
                           f"Got: {acc_map['1-0000'].get('is_postable')}")
            
            # Check system flag
            if "1-1100" in acc_map:
                results.add("System account has system=true",
                           acc_map["1-1100"].get("system") is True,
                           f"Got: {acc_map['1-1100'].get('system')}")
    except Exception as e:
        results.add("GET /gl/accounts", False, str(e))

def test_coa_crud(admin_token: str):
    """Test CoA CRUD operations"""
    print("\n=== CoA CRUD Tests ===")
    h = headers(admin_token)
    test_code = "6-5500"
    
    # Clean up first
    requests.delete(f"{BASE_URL}/gl/accounts/{test_code}", headers=h)
    
    # POST - Create new account
    try:
        resp = requests.post(f"{BASE_URL}/gl/accounts", headers=h, json={
            "code": test_code,
            "name": "Beban Pemasaran Test",
            "type": "expense",
            "parent_code": "6-0000"
        }, timeout=10)
        results.add("POST /gl/accounts creates account", resp.status_code == 200, f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            acc = resp.json()
            results.add("New expense account has normal_balance=debit",
                       acc.get("normal_balance") == "debit",
                       f"Got: {acc.get('normal_balance')}")
    except Exception as e:
        results.add("POST /gl/accounts", False, str(e))
    
    # POST - Duplicate code should fail
    try:
        resp = requests.post(f"{BASE_URL}/gl/accounts", headers=h, json={
            "code": test_code,
            "name": "Duplicate",
            "type": "expense"
        }, timeout=10)
        results.add("POST duplicate code returns 400", resp.status_code == 400, f"Status: {resp.status_code}")
    except Exception as e:
        results.add("POST duplicate code", False, str(e))
    
    # DELETE - System account should fail
    try:
        resp = requests.delete(f"{BASE_URL}/gl/accounts/1-1100", headers=h, timeout=10)
        results.add("DELETE system account returns 400", resp.status_code == 400, f"Status: {resp.status_code}")
    except Exception as e:
        results.add("DELETE system account", False, str(e))
    
    # DELETE - Custom unused account should succeed
    try:
        resp = requests.delete(f"{BASE_URL}/gl/accounts/{test_code}", headers=h, timeout=10)
        results.add("DELETE custom account returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
    except Exception as e:
        results.add("DELETE custom account", False, str(e))

def test_sync_journals(admin_token: str):
    """Test auto-posting sync"""
    print("\n=== Auto-Posting Sync Tests ===")
    h = headers(admin_token)
    
    try:
        # First sync
        resp1 = requests.post(f"{BASE_URL}/gl/sync", headers=h, timeout=30)
        results.add("POST /gl/sync returns 200", resp1.status_code == 200, f"Status: {resp1.status_code}")
        
        if resp1.status_code == 200:
            data1 = resp1.json()
            total1 = data1.get("total", 0)
            results.add("Sync returns result with total", "total" in data1, f"Keys: {data1.keys()}")
            
            # Get summary
            sum_resp = requests.get(f"{BASE_URL}/gl/summary", headers=h, timeout=10)
            if sum_resp.status_code == 200:
                summary = sum_resp.json()
                count1 = summary.get("journal_count", 0)
                results.add("Journal count >= 15", count1 >= 15, f"Count: {count1}")
                
                # Second sync should be idempotent
                resp2 = requests.post(f"{BASE_URL}/gl/sync", headers=h, timeout=30)
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    results.add("Second sync returns total=0 (idempotent)",
                               data2.get("total", -1) == 0,
                               f"Total: {data2.get('total')}")
                    
                    # Verify count unchanged
                    sum_resp2 = requests.get(f"{BASE_URL}/gl/summary", headers=h, timeout=10)
                    if sum_resp2.status_code == 200:
                        count2 = sum_resp2.json().get("journal_count", 0)
                        results.add("Journal count stable after second sync",
                                   count1 == count2,
                                   f"Before: {count1}, After: {count2}")
    except Exception as e:
        results.add("Sync journals", False, str(e))

def test_trial_balance(admin_token: str):
    """Test trial balance"""
    print("\n=== Trial Balance Tests ===")
    h = headers(admin_token)
    
    try:
        resp = requests.get(f"{BASE_URL}/gl/trial-balance", headers=h, timeout=10)
        results.add("GET /gl/trial-balance returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            tb = resp.json()
            results.add("Trial balance has balanced flag", "balanced" in tb, f"Keys: {tb.keys()}")
            results.add("Trial balance is balanced", tb.get("balanced") is True, f"Balanced: {tb.get('balanced')}")
            
            debit = tb.get("total_debit", 0)
            credit = tb.get("total_credit", 0)
            results.add("Total debit == total credit",
                       abs(debit - credit) < 1.0,
                       f"Debit: {debit}, Credit: {credit}, Diff: {abs(debit - credit)}")
            
            rows = tb.get("rows", [])
            results.add("Trial balance has rows", len(rows) > 0, f"Rows: {len(rows)}")
            
            # Check key accounts
            row_map = {r["code"]: r for r in rows}
            if "1-1200" in row_map:
                results.add("Piutang (1-1200) has debit balance",
                           row_map["1-1200"].get("debit_balance", 0) > 0,
                           f"Balance: {row_map['1-1200'].get('debit_balance')}")
            
            if "4-1000" in row_map:
                results.add("Pendapatan (4-1000) has credit balance",
                           row_map["4-1000"].get("credit_balance", 0) > 0,
                           f"Balance: {row_map['4-1000'].get('credit_balance')}")
    except Exception as e:
        results.add("Trial balance", False, str(e))

def test_manual_journal(admin_token: str):
    """Test manual journal entry"""
    print("\n=== Manual Journal Entry Tests ===")
    h = headers(admin_token)
    
    # Balanced entry should succeed
    try:
        resp = requests.post(f"{BASE_URL}/gl/journal", headers=h, json={
            "description": "Test balanced entry",
            "lines": [
                {"account_code": "6-2000", "debit": 1000000, "credit": 0},
                {"account_code": "1-1100", "debit": 0, "credit": 1000000}
            ]
        }, timeout=10)
        results.add("POST balanced journal returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
        
        je_id = None
        if resp.status_code == 200:
            je = resp.json()
            je_id = je.get("id")
            results.add("Journal has number starting with JE-",
                       je.get("number", "").startswith("JE-"),
                       f"Number: {je.get('number')}")
            results.add("Journal total_debit correct",
                       abs(je.get("total_debit", 0) - 1000000) < 1,
                       f"Total: {je.get('total_debit')}")
    except Exception as e:
        results.add("POST balanced journal", False, str(e))
        je_id = None
    
    # Unbalanced entry should fail
    try:
        resp = requests.post(f"{BASE_URL}/gl/journal", headers=h, json={
            "description": "Test unbalanced",
            "lines": [
                {"account_code": "6-2000", "debit": 1000000, "credit": 0},
                {"account_code": "1-1100", "debit": 0, "credit": 900000}
            ]
        }, timeout=10)
        results.add("POST unbalanced journal returns 400", resp.status_code == 400, f"Status: {resp.status_code}")
    except Exception as e:
        results.add("POST unbalanced journal", False, str(e))
    
    # Header account should fail
    try:
        resp = requests.post(f"{BASE_URL}/gl/journal", headers=h, json={
            "description": "Test header account",
            "lines": [
                {"account_code": "1-0000", "debit": 500000, "credit": 0},
                {"account_code": "1-1100", "debit": 0, "credit": 500000}
            ]
        }, timeout=10)
        results.add("POST journal to header account returns 400", resp.status_code == 400, f"Status: {resp.status_code}")
    except Exception as e:
        results.add("POST journal to header account", False, str(e))
    
    # Test void
    if je_id:
        try:
            resp = requests.post(f"{BASE_URL}/gl/journal/{je_id}/void", headers=h, timeout=10)
            results.add("POST void manual journal returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
            
            if resp.status_code == 200:
                voided = resp.json()
                results.add("Voided journal has status=void",
                           voided.get("status") == "void",
                           f"Status: {voided.get('status')}")
        except Exception as e:
            results.add("POST void manual journal", False, str(e))
    
    # Try to void auto journal (should fail)
    try:
        # Get auto journals
        resp = requests.get(f"{BASE_URL}/gl/journal", headers=h, params={"source": "sales_order"}, timeout=10)
        if resp.status_code == 200:
            autos = resp.json()
            if len(autos) > 0:
                auto_id = autos[0].get("id")
                void_resp = requests.post(f"{BASE_URL}/gl/journal/{auto_id}/void", headers=h, timeout=10)
                results.add("POST void auto journal returns 400",
                           void_resp.status_code == 400,
                           f"Status: {void_resp.status_code}")
    except Exception as e:
        results.add("POST void auto journal", False, str(e))

def test_account_ledger(admin_token: str):
    """Test account ledger"""
    print("\n=== Account Ledger Tests ===")
    h = headers(admin_token)
    
    try:
        resp = requests.get(f"{BASE_URL}/gl/accounts/1-1100/ledger", headers=h, timeout=10)
        results.add("GET /gl/accounts/{code}/ledger returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            ledger = resp.json()
            results.add("Ledger has lines", "lines" in ledger, f"Keys: {ledger.keys()}")
            
            lines = ledger.get("lines", [])
            if len(lines) > 0:
                results.add("All lines have running_balance",
                           all("running_balance" in l for l in lines),
                           f"Sample: {lines[0].keys() if lines else []}")
            
            # Compare with trial balance
            tb_resp = requests.get(f"{BASE_URL}/gl/trial-balance", headers=h, timeout=10)
            if tb_resp.status_code == 200:
                tb = tb_resp.json()
                rows = {r["code"]: r for r in tb.get("rows", [])}
                if "1-1100" in rows:
                    tb_balance = rows["1-1100"].get("debit_balance", 0) - rows["1-1100"].get("credit_balance", 0)
                    ledger_balance = ledger.get("balance", 0)
                    results.add("Ledger balance matches trial balance",
                               abs(tb_balance - ledger_balance) < 1.0,
                               f"TB: {tb_balance}, Ledger: {ledger_balance}")
    except Exception as e:
        results.add("Account ledger", False, str(e))

def test_rbac(admin_token: str, manager_token: str, sales_token: str, warehouse_token: str):
    """Test RBAC permissions"""
    print("\n=== RBAC Tests ===")
    
    # Manager should have access
    try:
        resp = requests.get(f"{BASE_URL}/gl/accounts", headers=headers(manager_token), timeout=10)
        results.add("Manager GET /gl/accounts returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
        
        resp = requests.get(f"{BASE_URL}/gl/trial-balance", headers=headers(manager_token), timeout=10)
        results.add("Manager GET /gl/trial-balance returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
    except Exception as e:
        results.add("Manager access", False, str(e))
    
    # Sales should NOT have access
    try:
        resp = requests.get(f"{BASE_URL}/gl/accounts", headers=headers(sales_token), timeout=10)
        results.add("Sales GET /gl/accounts returns 403", resp.status_code == 403, f"Status: {resp.status_code}")
        
        resp = requests.get(f"{BASE_URL}/gl/trial-balance", headers=headers(sales_token), timeout=10)
        results.add("Sales GET /gl/trial-balance returns 403", resp.status_code == 403, f"Status: {resp.status_code}")
        
        resp = requests.post(f"{BASE_URL}/gl/journal", headers=headers(sales_token), json={"lines": []}, timeout=10)
        results.add("Sales POST /gl/journal returns 403", resp.status_code == 403, f"Status: {resp.status_code}")
    except Exception as e:
        results.add("Sales RBAC", False, str(e))
    
    # Warehouse should NOT have access
    try:
        resp = requests.get(f"{BASE_URL}/gl/accounts", headers=headers(warehouse_token), timeout=10)
        results.add("Warehouse GET /gl/accounts returns 403", resp.status_code == 403, f"Status: {resp.status_code}")
    except Exception as e:
        results.add("Warehouse RBAC", False, str(e))

def main():
    print("="*60)
    print("EPIC 7-C Backend Test Suite")
    print("="*60)
    
    # Login all users
    print("\n=== Logging in users ===")
    admin_token = login("admin@kainnusantara.id")
    manager_token = login("manager@kainnusantara.id")
    sales_token = login("sales@kainnusantara.id")
    warehouse_token = login("warehouse@kainnusantara.id")
    
    if not admin_token:
        print("❌ Failed to login as admin")
        return 1
    print("✅ Logged in as admin")
    
    if not manager_token:
        print("❌ Failed to login as manager")
        return 1
    print("✅ Logged in as manager")
    
    if not sales_token:
        print("❌ Failed to login as sales")
        return 1
    print("✅ Logged in as sales")
    
    if not warehouse_token:
        print("❌ Failed to login as warehouse")
        return 1
    print("✅ Logged in as warehouse")
    
    # Run tests
    test_chart_of_accounts(admin_token)
    test_coa_crud(admin_token)
    test_sync_journals(admin_token)
    test_trial_balance(admin_token)
    test_manual_journal(admin_token)
    test_account_ledger(admin_token)
    test_rbac(admin_token, manager_token, sales_token, warehouse_token)
    
    # Summary
    success = results.summary()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
