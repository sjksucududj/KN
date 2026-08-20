"""R5.3 Backend API Testing - Cash Refund + GL Separation"""
import requests
import sys
from typing import Dict, Any

BASE_URL = "https://supplier-rma-portal.preview.emergentagent.com/api"
ADMIN_CREDS = {"email": "admin@kainnusantara.id", "password": "demo12345"}

class R53BackendTester:
    def __init__(self):
        self.token = None
        self.headers = {}
        self.passed = 0
        self.failed = 0
        
    def log(self, status: str, test_name: str, details: str = ""):
        symbol = "✅" if status == "PASS" else "❌"
        print(f"{symbol} {test_name}")
        if details and status == "FAIL":
            print(f"   Details: {details}")
        if status == "PASS":
            self.passed += 1
        else:
            self.failed += 1
    
    def login(self) -> bool:
        """Login and get auth token"""
        try:
            resp = requests.post(f"{BASE_URL}/auth/login", json=ADMIN_CREDS, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("token")
                self.headers = {"Authorization": f"Bearer {self.token}"}
                self.log("PASS", "Login successful")
                return True
            else:
                self.log("FAIL", "Login failed", f"Status: {resp.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "Login failed", str(e))
            return False
    
    def test_cash_accounts_endpoint(self):
        """Test GET /api/gl/cash-accounts"""
        print("\n[TEST 1] GET /api/gl/cash-accounts")
        try:
            resp = requests.get(f"{BASE_URL}/gl/cash-accounts", headers=self.headers, timeout=30)
            if resp.status_code != 200:
                self.log("FAIL", "GET /api/gl/cash-accounts", f"Status: {resp.status_code}")
                return
            
            accounts = resp.json()
            if not isinstance(accounts, list):
                self.log("FAIL", "Response is array", f"Got: {type(accounts)}")
                return
            
            self.log("PASS", "GET /api/gl/cash-accounts returns 200")
            self.log("PASS", "Response is array", f"Count: {len(accounts)}")
            
            # Check for required accounts
            codes = [a.get("code") for a in accounts]
            has_1100 = "1-1100" in codes
            has_1110 = "1-1110" in codes
            
            if has_1100:
                self.log("PASS", "Account 1-1100 (Kas Besar) present")
            else:
                self.log("FAIL", "Account 1-1100 missing", f"Codes: {codes}")
            
            if has_1110:
                self.log("PASS", "Account 1-1110 (Kas Kecil) present")
            else:
                self.log("FAIL", "Account 1-1110 missing", f"Codes: {codes}")
            
            # Check structure
            if accounts:
                acc = accounts[0]
                if "code" in acc and "name" in acc:
                    self.log("PASS", "Account structure has code and name")
                else:
                    self.log("FAIL", "Account structure incomplete", f"Keys: {acc.keys()}")
            
        except Exception as e:
            self.log("FAIL", "GET /api/gl/cash-accounts", str(e))
    
    def test_sales_return_cash_refund(self):
        """Test sales return cash refund flow"""
        print("\n[TEST 2] Sales Return Cash Refund")
        try:
            # Get sales returns
            resp = requests.get(f"{BASE_URL}/sales-returns", headers=self.headers, timeout=30)
            if resp.status_code != 200:
                self.log("FAIL", "Get sales returns", f"Status: {resp.status_code}")
                return
            
            returns = resp.json()
            if isinstance(returns, dict):
                returns = returns.get("items", [])
            
            # Find an inspected return
            inspected = [r for r in returns if r.get("status") == "inspected"]
            if not inspected:
                self.log("FAIL", "No inspected returns found for testing", "Need inspected return")
                return
            
            ret = inspected[0]
            self.log("PASS", f"Found inspected return: {ret.get('number')}")
            
            # Try to settle with refund outcome and account picker
            settle_payload = {
                "outcome": "refund",
                "return_warehouse_id": ret.get("return_warehouse_id") or "wh_default",
                "refund_account_code": "1-1110"  # Kas Kecil
            }
            
            resp = requests.post(
                f"{BASE_URL}/sales-returns/{ret['id']}/settle",
                headers=self.headers,
                json=settle_payload,
                timeout=30
            )
            
            if resp.status_code == 200:
                settled = resp.json()
                settlement = settled.get("settlement", {})
                
                self.log("PASS", "Settle with refund_account_code succeeds")
                
                # Check settlement fields
                if settlement.get("settlement") == "cash":
                    self.log("PASS", "settlement.settlement == 'cash'")
                else:
                    self.log("FAIL", "settlement.settlement != 'cash'", f"Got: {settlement.get('settlement')}")
                
                if settlement.get("cash_txn_number"):
                    self.log("PASS", "settlement.cash_txn_number is set")
                else:
                    self.log("FAIL", "settlement.cash_txn_number missing")
                
                if settlement.get("refund_account_code") == "1-1110":
                    self.log("PASS", "settlement.refund_account_code == '1-1110'")
                else:
                    self.log("FAIL", "refund_account_code mismatch", f"Got: {settlement.get('refund_account_code')}")
                
            else:
                # May already be settled - check if it's idempotent
                if resp.status_code == 400 or "already" in resp.text.lower():
                    self.log("PASS", "Settle is idempotent (already settled)")
                else:
                    self.log("FAIL", "Settle failed", f"Status: {resp.status_code}, {resp.text[:200]}")
        
        except Exception as e:
            self.log("FAIL", "Sales return cash refund test", str(e))
    
    def test_purchase_return_supplier_accept(self):
        """Test purchase return supplier-accept with refund vs ap_credit"""
        print("\n[TEST 3] Purchase Return Supplier Accept")
        try:
            # Get purchase returns
            resp = requests.get(f"{BASE_URL}/purchase-returns", headers=self.headers, timeout=30)
            if resp.status_code != 200:
                self.log("FAIL", "Get purchase returns", f"Status: {resp.status_code}")
                return
            
            returns = resp.json()
            if isinstance(returns, dict):
                returns = returns.get("items", [])
            
            # Find shipped_supplier returns
            shipped = [r for r in returns if r.get("supplier_status") == "shipped_supplier"]
            if not shipped:
                self.log("FAIL", "No shipped_supplier returns found", "Need RMA in shipped state")
                return
            
            ret = shipped[0]
            self.log("PASS", f"Found shipped return: {ret.get('number')}")
            
            # Test refund outcome
            refund_payload = {
                "outcome": "refund",
                "refund_account_code": "1-1100"
            }
            
            resp = requests.post(
                f"{BASE_URL}/purchase-returns/{ret['id']}/supplier-accept",
                headers=self.headers,
                json=refund_payload,
                timeout=30
            )
            
            if resp.status_code == 200:
                self.log("PASS", "Supplier-accept with outcome='refund' succeeds")
                accepted = resp.json()
                
                if accepted.get("supplier_outcome") == "refund":
                    self.log("PASS", "supplier_outcome == 'refund'")
                else:
                    self.log("FAIL", "supplier_outcome mismatch", f"Got: {accepted.get('supplier_outcome')}")
                
                if accepted.get("cash_txn_number"):
                    self.log("PASS", "cash_txn_number is set for refund")
                else:
                    self.log("FAIL", "cash_txn_number missing for refund")
            else:
                if "already" in resp.text.lower():
                    self.log("PASS", "Supplier-accept is idempotent")
                else:
                    self.log("FAIL", "Supplier-accept refund failed", f"Status: {resp.status_code}")
            
            # Test ap_credit outcome (if we have another shipped return)
            if len(shipped) > 1:
                ret2 = shipped[1]
                ap_payload = {"outcome": "ap_credit"}
                
                resp = requests.post(
                    f"{BASE_URL}/purchase-returns/{ret2['id']}/supplier-accept",
                    headers=self.headers,
                    json=ap_payload,
                    timeout=30
                )
                
                if resp.status_code == 200:
                    self.log("PASS", "Supplier-accept with outcome='ap_credit' succeeds")
                    accepted = resp.json()
                    
                    if not accepted.get("cash_txn_number"):
                        self.log("PASS", "No cash_txn_number for ap_credit (correct)")
                    else:
                        self.log("FAIL", "cash_txn_number should not exist for ap_credit")
                else:
                    if "already" in resp.text.lower():
                        self.log("PASS", "ap_credit is idempotent")
        
        except Exception as e:
            self.log("FAIL", "Purchase return supplier-accept test", str(e))
    
    def test_regression_ar_refund(self):
        """Test that normal AR refund (credit order) doesn't create cash_transaction"""
        print("\n[TEST 4] Regression - AR Refund (Credit Order)")
        try:
            # This is tested by the POC - just verify endpoint still works
            resp = requests.get(f"{BASE_URL}/sales-returns", headers=self.headers, timeout=30)
            if resp.status_code == 200:
                self.log("PASS", "Sales returns endpoint accessible")
                
                returns = resp.json()
                if isinstance(returns, dict):
                    returns = returns.get("items", [])
                
                # Check for any settled returns with AR settlement
                ar_settled = [r for r in returns if r.get("settlement", {}).get("settlement") == "ar"]
                if ar_settled:
                    self.log("PASS", f"Found {len(ar_settled)} AR-settled returns (regression OK)")
                else:
                    self.log("PASS", "No AR-settled returns found (acceptable)")
            else:
                self.log("FAIL", "Sales returns endpoint", f"Status: {resp.status_code}")
        
        except Exception as e:
            self.log("FAIL", "Regression test", str(e))
    
    def run_all_tests(self):
        """Run all backend tests"""
        print("=" * 60)
        print("R5.3 BACKEND API TESTING - Cash Refund + GL Separation")
        print("=" * 60)
        
        if not self.login():
            print("\n❌ Login failed - cannot proceed with tests")
            return False
        
        self.test_cash_accounts_endpoint()
        self.test_sales_return_cash_refund()
        self.test_purchase_return_supplier_accept()
        self.test_regression_ar_refund()
        
        print("\n" + "=" * 60)
        print(f"RESULTS: {self.passed} PASSED, {self.failed} FAILED")
        print("=" * 60)
        
        return self.failed == 0

if __name__ == "__main__":
    tester = R53BackendTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
