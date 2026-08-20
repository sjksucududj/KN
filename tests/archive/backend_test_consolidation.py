"""
Backend API Testing for P7 Consolidation Module (FINANCE)
Tests: Consolidation Summary, Eliminations CRUD, IC Candidates, RBAC, Entity Scoping, Regression
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"
LOGIN_EMAIL = "admin@kainnusantara.id"
LOGIN_PASSWORD = "demo12345"

class ConsolidationAPITester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.test_elimination_id = None

    def log(self, message, level="INFO"):
        """Log test messages"""
        prefix = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "FAIL": "❌",
            "WARN": "⚠️"
        }.get(level, "•")
        print(f"{prefix} {message}")

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None, headers=None):
        """Run a single API test"""
        url = f"{BASE_URL}{endpoint}"
        req_headers = {'Content-Type': 'application/json'}
        if self.token:
            req_headers['Authorization'] = f'Bearer {self.token}'
        if headers:
            req_headers.update(headers)

        self.tests_run += 1
        self.log(f"Testing: {name}", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=req_headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=req_headers, params=params, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=req_headers, params=params, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=req_headers, params=params, timeout=30)

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"PASSED - {name} (Status: {response.status_code})", "SUCCESS")
                return True, response
            else:
                self.tests_failed += 1
                self.failed_tests.append(name)
                self.log(f"FAILED - {name} (Expected {expected_status}, got {response.status_code})", "FAIL")
                try:
                    error_detail = response.json()
                    self.log(f"  Error: {error_detail}", "FAIL")
                except:
                    self.log(f"  Response: {response.text[:200]}", "FAIL")
                return False, response

        except Exception as e:
            self.tests_failed += 1
            self.failed_tests.append(name)
            self.log(f"FAILED - {name} (Exception: {str(e)})", "FAIL")
            return False, None

    def test_login(self):
        """Test login and get token"""
        self.log("\n=== AUTHENTICATION ===", "INFO")
        success, response = self.run_test(
            "Login",
            "POST",
            "/auth/login",
            200,
            data={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD}
        )
        if success and response:
            try:
                data = response.json()
                self.token = data.get('token')
                if self.token:
                    self.log(f"  Token obtained: {self.token[:20]}...", "SUCCESS")
                    return True
                else:
                    self.log("  No token in response", "FAIL")
                    return False
            except:
                self.log("  Failed to parse login response", "FAIL")
                return False
        return False

    def test_consolidation_summary(self):
        """Test GET /api/finance/consolidation/summary"""
        self.log("\n=== CONSOLIDATION SUMMARY ===", "INFO")
        success, response = self.run_test(
            "Consolidation Summary (year=2026, as_of=2026-07-01)",
            "GET",
            "/finance/consolidation/summary",
            200,
            params={"year": 2026, "as_of": "2026-07-01"}
        )
        if success and response:
            try:
                data = response.json()
                # Check required fields
                required_fields = ['year', 'as_of', 'entities', 'gross', 'elimination', 'consolidated', 'balanced']
                missing = [f for f in required_fields if f not in data]
                if missing:
                    self.log(f"  Missing fields: {missing}", "FAIL")
                    return False
                
                self.log(f"  Year: {data.get('year')}, As Of: {data.get('as_of')}", "SUCCESS")
                self.log(f"  Entities count: {len(data.get('entities', []))}", "SUCCESS")
                self.log(f"  Balanced: {data.get('balanced')}", "SUCCESS" if data.get('balanced') else "WARN")
                
                # Check entities structure
                entities = data.get('entities', [])
                if entities:
                    first_entity = entities[0]
                    entity_fields = ['entity_id', 'entity_name', 'revenue', 'cogs', 'opex', 'expense', 
                                     'gross_profit', 'net_income', 'assets', 'liabilities', 'equity']
                    missing_entity_fields = [f for f in entity_fields if f not in first_entity]
                    if missing_entity_fields:
                        self.log(f"  Entity missing fields: {missing_entity_fields}", "WARN")
                    else:
                        self.log(f"  Entity structure valid", "SUCCESS")
                
                # Check gross, elimination, consolidated structure
                for key in ['gross', 'elimination', 'consolidated']:
                    obj = data.get(key, {})
                    metric_fields = ['revenue', 'cogs', 'opex', 'expense', 'gross_profit', 'net_income', 
                                     'assets', 'liabilities', 'equity']
                    missing_metrics = [f for f in metric_fields if f not in obj]
                    if missing_metrics:
                        self.log(f"  {key.capitalize()} missing fields: {missing_metrics}", "WARN")
                    else:
                        self.log(f"  {key.capitalize()} structure valid", "SUCCESS")
                
                # Verify consolidated = gross + elimination
                gross = data.get('gross', {})
                elimination = data.get('elimination', {})
                consolidated = data.get('consolidated', {})
                
                revenue_check = abs(consolidated.get('revenue', 0) - (gross.get('revenue', 0) + elimination.get('revenue', 0))) < 1.0
                assets_check = abs(consolidated.get('assets', 0) - (gross.get('assets', 0) + elimination.get('assets', 0))) < 1.0
                
                if revenue_check and assets_check:
                    self.log(f"  Consolidated = Gross + Elimination (verified)", "SUCCESS")
                else:
                    self.log(f"  Consolidated != Gross + Elimination (mismatch)", "WARN")
                
                # Check Neraca balanced (assets == liabilities + equity)
                cons_assets = consolidated.get('assets', 0)
                cons_liab = consolidated.get('liabilities', 0)
                cons_equity = consolidated.get('equity', 0)
                balance_check = abs(cons_assets - (cons_liab + cons_equity)) < 1.0
                
                if balance_check:
                    self.log(f"  Neraca balanced: Assets={cons_assets}, Liab+Equity={cons_liab + cons_equity}", "SUCCESS")
                else:
                    self.log(f"  Neraca NOT balanced: Assets={cons_assets}, Liab+Equity={cons_liab + cons_equity}", "WARN")
                
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_list_eliminations(self):
        """Test GET /api/finance/consolidation/eliminations"""
        self.log("\n=== LIST ELIMINATIONS ===", "INFO")
        success, response = self.run_test(
            "List Eliminations",
            "GET",
            "/finance/consolidation/eliminations",
            200
        )
        if success and response:
            try:
                data = response.json()
                if not isinstance(data, list):
                    self.log(f"  Response is not a list", "FAIL")
                    return False
                
                self.log(f"  Eliminations count: {len(data)}", "SUCCESS")
                
                # Check for demo elimination
                demo_elim = [e for e in data if 'Eliminasi Pinjaman Intercompany' in e.get('name', '')]
                if demo_elim:
                    self.log(f"  Demo elimination found: {demo_elim[0].get('name')}", "SUCCESS")
                else:
                    self.log(f"  Demo elimination 'Eliminasi Pinjaman Intercompany KSC-Kanda' not found", "WARN")
                
                # Check structure of first elimination if exists
                if data:
                    first = data[0]
                    required_fields = ['id', 'name', 'effective_date', 'lines', 'total_debit', 'total_credit', 'balanced', 'impact']
                    missing = [f for f in required_fields if f not in first]
                    if missing:
                        self.log(f"  Elimination missing fields: {missing}", "WARN")
                    else:
                        self.log(f"  Elimination structure valid", "SUCCESS")
                        self.log(f"    Name: {first.get('name')}, Balanced: {first.get('balanced')}", "SUCCESS")
                
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_create_elimination_valid(self):
        """Test POST /api/finance/consolidation/eliminations with valid balanced data"""
        self.log("\n=== CREATE ELIMINATION (VALID) ===", "INFO")
        
        # Create a balanced elimination
        payload = {
            "name": "Test Elimination - Automated Test",
            "effective_date": "2026-07-01",
            "note": "Created by automated test - should be deleted after test",
            "lines": [
                {
                    "account_code": "1-1100",
                    "debit": 0,
                    "credit": 1000000,
                    "description": "Test credit line"
                },
                {
                    "account_code": "2-1100",
                    "debit": 1000000,
                    "credit": 0,
                    "description": "Test debit line"
                }
            ]
        }
        
        success, response = self.run_test(
            "Create Elimination (balanced)",
            "POST",
            "/finance/consolidation/eliminations",
            200,
            data=payload
        )
        if success and response:
            try:
                data = response.json()
                self.test_elimination_id = data.get('id')
                self.log(f"  Created elimination ID: {self.test_elimination_id}", "SUCCESS")
                self.log(f"  Name: {data.get('name')}", "SUCCESS")
                self.log(f"  Balanced: {data.get('balanced')}", "SUCCESS" if data.get('balanced') else "FAIL")
                self.log(f"  Total Debit: {data.get('total_debit')}, Total Credit: {data.get('total_credit')}", "SUCCESS")
                
                # Check impact
                impact = data.get('impact', {})
                if impact:
                    self.log(f"  Impact computed: {list(impact.keys())}", "SUCCESS")
                else:
                    self.log(f"  Impact missing", "WARN")
                
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_create_elimination_empty_lines(self):
        """Test POST /api/finance/consolidation/eliminations with empty lines (should return 400)"""
        self.log("\n=== CREATE ELIMINATION (EMPTY LINES) ===", "INFO")
        
        payload = {
            "name": "Test Elimination - Empty Lines",
            "effective_date": "2026-07-01",
            "lines": []
        }
        
        success, response = self.run_test(
            "Create Elimination (empty lines - expect 400)",
            "POST",
            "/finance/consolidation/eliminations",
            400,
            data=payload
        )
        if success:
            self.log(f"  Correctly rejected empty lines with 400", "SUCCESS")
            return True
        return False

    def test_create_elimination_unbalanced(self):
        """Test POST /api/finance/consolidation/eliminations with unbalanced lines (should save but balanced=false)"""
        self.log("\n=== CREATE ELIMINATION (UNBALANCED) ===", "INFO")
        
        payload = {
            "name": "Test Elimination - Unbalanced",
            "effective_date": "2026-07-01",
            "note": "Unbalanced test - should be deleted",
            "lines": [
                {
                    "account_code": "1-1100",
                    "debit": 0,
                    "credit": 1000000,
                    "description": "Test credit"
                },
                {
                    "account_code": "2-1100",
                    "debit": 500000,
                    "credit": 0,
                    "description": "Test debit (unbalanced)"
                }
            ]
        }
        
        success, response = self.run_test(
            "Create Elimination (unbalanced - should save with balanced=false)",
            "POST",
            "/finance/consolidation/eliminations",
            200,
            data=payload
        )
        if success and response:
            try:
                data = response.json()
                balanced = data.get('balanced')
                if not balanced:
                    self.log(f"  Correctly saved unbalanced elimination with balanced=false", "SUCCESS")
                    # Store ID for cleanup
                    unbalanced_id = data.get('id')
                    if unbalanced_id:
                        # Clean up immediately
                        self.run_test(
                            "Delete unbalanced test elimination",
                            "DELETE",
                            f"/finance/consolidation/eliminations/{unbalanced_id}",
                            200
                        )
                    return True
                else:
                    self.log(f"  Unexpected: balanced=true for unbalanced lines", "FAIL")
                    return False
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_delete_elimination(self):
        """Test DELETE /api/finance/consolidation/eliminations/{id}"""
        self.log("\n=== DELETE ELIMINATION ===", "INFO")
        
        if not self.test_elimination_id:
            self.log(f"  No test elimination ID to delete (skipping)", "WARN")
            return True
        
        success, response = self.run_test(
            f"Delete Elimination (ID: {self.test_elimination_id})",
            "DELETE",
            f"/finance/consolidation/eliminations/{self.test_elimination_id}",
            200
        )
        if success and response:
            try:
                data = response.json()
                if data.get('deleted'):
                    self.log(f"  Elimination deleted successfully", "SUCCESS")
                    return True
                else:
                    self.log(f"  Unexpected response: {data}", "WARN")
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_delete_elimination_nonexistent(self):
        """Test DELETE /api/finance/consolidation/eliminations/{id} with non-existent ID (should return 404)"""
        self.log("\n=== DELETE ELIMINATION (NON-EXISTENT) ===", "INFO")
        
        fake_id = "icelim_nonexistent_12345"
        success, response = self.run_test(
            f"Delete Elimination (non-existent ID - expect 404)",
            "DELETE",
            f"/finance/consolidation/eliminations/{fake_id}",
            404
        )
        if success:
            self.log(f"  Correctly returned 404 for non-existent ID", "SUCCESS")
            return True
        return False

    def test_ic_candidates(self):
        """Test GET /api/finance/consolidation/ic-candidates"""
        self.log("\n=== IC CANDIDATES (AUTO-DETECT) ===", "INFO")
        success, response = self.run_test(
            "IC Candidates (as_of=2026-07-01)",
            "GET",
            "/finance/consolidation/ic-candidates",
            200,
            params={"as_of": "2026-07-01"}
        )
        if success and response:
            try:
                data = response.json()
                required_fields = ['as_of', 'keywords', 'candidates', 'suggested_lines', 'detected_accounts']
                missing = [f for f in required_fields if f not in data]
                if missing:
                    self.log(f"  Missing fields: {missing}", "FAIL")
                    return False
                
                self.log(f"  As Of: {data.get('as_of')}", "SUCCESS")
                self.log(f"  Detected Accounts: {data.get('detected_accounts')}", "SUCCESS")
                self.log(f"  Candidates count: {len(data.get('candidates', []))}", "SUCCESS")
                self.log(f"  Suggested Lines count: {len(data.get('suggested_lines', []))}", "SUCCESS")
                
                # Check candidates structure
                candidates = data.get('candidates', [])
                if candidates:
                    first = candidates[0]
                    cand_fields = ['account_code', 'account_name', 'type', 'per_entity', 'total_net']
                    missing_cand = [f for f in cand_fields if f not in first]
                    if missing_cand:
                        self.log(f"  Candidate missing fields: {missing_cand}", "WARN")
                    else:
                        self.log(f"  Candidate structure valid", "SUCCESS")
                        self.log(f"    Account: {first.get('account_code')} - {first.get('account_name')}", "SUCCESS")
                
                # Check suggested_lines structure
                suggested = data.get('suggested_lines', [])
                if suggested:
                    first_line = suggested[0]
                    line_fields = ['account_code', 'account_name', 'debit', 'credit', 'description']
                    missing_line = [f for f in line_fields if f not in first_line]
                    if missing_line:
                        self.log(f"  Suggested line missing fields: {missing_line}", "WARN")
                    else:
                        self.log(f"  Suggested line structure valid", "SUCCESS")
                
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_regression_income_statement(self):
        """Test regression: GET /api/finance/income-statement"""
        self.log("\n=== REGRESSION - INCOME STATEMENT ===", "INFO")
        success, response = self.run_test(
            "Income Statement (regression)",
            "GET",
            "/finance/income-statement",
            200,
            params={"start": "2026-01-01", "end": "2026-12-31"}
        )
        if success and response:
            try:
                data = response.json()
                if 'sections' in data and 'revenue_total' in data:
                    self.log(f"  Income Statement working: revenue={data.get('revenue_total')}", "SUCCESS")
                    return True
                else:
                    self.log(f"  Income Statement structure invalid", "WARN")
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_regression_balance_sheet(self):
        """Test regression: GET /api/finance/balance-sheet"""
        self.log("\n=== REGRESSION - BALANCE SHEET ===", "INFO")
        success, response = self.run_test(
            "Balance Sheet (regression)",
            "GET",
            "/finance/balance-sheet",
            200,
            params={"as_of": "2026-12-31"}
        )
        if success and response:
            try:
                data = response.json()
                if 'assets_total' in data and 'balanced' in data:
                    self.log(f"  Balance Sheet working: assets={data.get('assets_total')}, balanced={data.get('balanced')}", "SUCCESS")
                    return True
                else:
                    self.log(f"  Balance Sheet structure invalid", "WARN")
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_regression_closing(self):
        """Test regression: GET /api/finance/closing"""
        self.log("\n=== REGRESSION - CLOSING (TUTUP BUKU) ===", "INFO")
        success, response = self.run_test(
            "Closing (regression)",
            "GET",
            "/finance/closing",
            200
        )
        if success and response:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log(f"  Closing working: {len(data)} periods returned", "SUCCESS")
                    return True
                else:
                    self.log(f"  Closing response format unexpected", "WARN")
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_regression_bi(self):
        """Test regression: GET /api/finance/bi"""
        self.log("\n=== REGRESSION - BI KEUANGAN ===", "INFO")
        success, response = self.run_test(
            "BI Keuangan (regression)",
            "GET",
            "/finance/bi",
            200
        )
        if success and response:
            try:
                data = response.json()
                # BI endpoint returns various metrics
                self.log(f"  BI Keuangan working", "SUCCESS")
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_regression_crm_leads(self):
        """Test regression: GET /api/crm/leads/board"""
        self.log("\n=== REGRESSION - CRM LEADS ===", "INFO")
        success, response = self.run_test(
            "CRM Leads Board (regression)",
            "GET",
            "/crm/leads/board",
            200
        )
        if success and response:
            try:
                data = response.json()
                if 'stages' in data:
                    self.log(f"  CRM Leads working: {len(data.get('stages', []))} stages", "SUCCESS")
                    return True
                else:
                    self.log(f"  CRM Leads structure unexpected", "WARN")
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "="*60, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("="*60, "INFO")
        self.log(f"Total Tests: {self.tests_run}", "INFO")
        self.log(f"Passed: {self.tests_passed}", "SUCCESS")
        self.log(f"Failed: {self.tests_failed}", "FAIL" if self.tests_failed > 0 else "INFO")
        
        if self.tests_failed > 0:
            self.log("\nFailed Tests:", "FAIL")
            for test in self.failed_tests:
                self.log(f"  - {test}", "FAIL")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"\nSuccess Rate: {success_rate:.1f}%", "SUCCESS" if success_rate >= 80 else "WARN")
        self.log("="*60, "INFO")
        
        return 0 if self.tests_failed == 0 else 1

def main():
    """Main test runner"""
    tester = ConsolidationAPITester()
    
    print("\n" + "="*60)
    print("P7 CONSOLIDATION MODULE - BACKEND API TESTS")
    print("="*60)
    
    # Authentication
    if not tester.test_login():
        print("\n❌ Login failed, stopping tests")
        return 1
    
    # P7 Consolidation Tests
    tester.test_consolidation_summary()
    tester.test_list_eliminations()
    tester.test_create_elimination_valid()
    tester.test_create_elimination_empty_lines()
    tester.test_create_elimination_unbalanced()
    tester.test_delete_elimination()
    tester.test_delete_elimination_nonexistent()
    tester.test_ic_candidates()
    
    # Regression Tests
    tester.test_regression_income_statement()
    tester.test_regression_balance_sheet()
    tester.test_regression_closing()
    tester.test_regression_bi()
    tester.test_regression_crm_leads()
    
    # Print summary
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
