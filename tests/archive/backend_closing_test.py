"""
Backend API Testing for Period Closing Module (FINANCE - Tutup Buku)
Tests: preview, close, reopen, overlap protection, status, list, accounting effects, multi-entity
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"
LOGIN_EMAIL = "admin@kainnusantara.id"
LOGIN_PASSWORD = "demo12345"
ENTITY_ID = "ent_ksc"  # PT Kain Suka Cita

class ClosingAPITester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.created_closings = []  # Track created closings for cleanup

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

    def test_preview_monthly(self):
        """Test preview closing for monthly period"""
        self.log("\n=== PREVIEW CLOSING - MONTHLY ===", "INFO")
        success, response = self.run_test(
            "Preview closing for July 2026",
            "GET",
            "/finance/closing/preview",
            200,
            params={"period_type": "month", "period_key": "2026-07", "entity_id": ENTITY_ID}
        )
        if success and response:
            try:
                data = response.json()
                # Check required fields
                required = ['period_type', 'period_key', 'period_label', 'start_date', 'end_date', 
                           'revenue_total', 'expense_total', 'net_income', 'closing_lines', 
                           'can_close', 'blocking_closing']
                missing = [f for f in required if f not in data]
                if missing:
                    self.log(f"  Missing fields: {missing}", "WARN")
                else:
                    self.log(f"  All required fields present", "SUCCESS")
                
                self.log(f"  Period: {data.get('period_label')}", "INFO")
                self.log(f"  Revenue: {data.get('revenue_total')}", "INFO")
                self.log(f"  Expense: {data.get('expense_total')}", "INFO")
                self.log(f"  Net Income: {data.get('net_income')}", "INFO")
                self.log(f"  Can Close: {data.get('can_close')}", "INFO")
                self.log(f"  Closing Lines: {len(data.get('closing_lines', []))} lines", "INFO")
                
                return True, data
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False, None

    def test_preview_yearly(self):
        """Test preview closing for yearly period"""
        self.log("\n=== PREVIEW CLOSING - YEARLY ===", "INFO")
        success, response = self.run_test(
            "Preview closing for Year 2026",
            "GET",
            "/finance/closing/preview",
            200,
            params={"period_type": "year", "period_key": "2026", "entity_id": ENTITY_ID}
        )
        if success and response:
            try:
                data = response.json()
                self.log(f"  Period: {data.get('period_label')}", "INFO")
                self.log(f"  Net Income: {data.get('net_income')}", "INFO")
                self.log(f"  Can Close: {data.get('can_close')}", "INFO")
                return True, data
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False, None

    def test_close_monthly(self):
        """Test closing a monthly period"""
        self.log("\n=== CLOSE PERIOD - MONTHLY ===", "INFO")
        success, response = self.run_test(
            "Close August 2026",
            "POST",
            "/finance/closing/close",
            200,
            data={"period_type": "month", "period_key": "2026-08", "entity_id": ENTITY_ID, "note": "Test closing"}
        )
        if success and response:
            try:
                data = response.json()
                self.log(f"  Closing ID: {data.get('id')}", "SUCCESS")
                self.log(f"  Period: {data.get('period_label')}", "SUCCESS")
                self.log(f"  Status: {data.get('status')}", "SUCCESS")
                self.log(f"  Journal Entry: {data.get('journal_entry_number')}", "SUCCESS")
                self.log(f"  Net Income: {data.get('net_income')}", "SUCCESS")
                
                # Track for cleanup
                if data.get('id'):
                    self.created_closings.append(data.get('id'))
                
                return True, data
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False, None

    def test_overlap_protection_month_then_year(self):
        """Test overlap protection: close month, then try to close year (should fail)"""
        self.log("\n=== OVERLAP PROTECTION - MONTH THEN YEAR ===", "INFO")
        
        # First close August 2026 (if not already closed)
        self.log("  Step 1: Ensure August 2026 is closed", "INFO")
        success, close_data = self.test_close_monthly()
        
        if not success:
            self.log("  Could not close August 2026, checking if already closed", "WARN")
        
        # Now try to close Year 2026 (should fail with 400)
        self.log("  Step 2: Try to close Year 2026 (should fail)", "INFO")
        success, response = self.run_test(
            "Close Year 2026 (should fail due to overlap)",
            "POST",
            "/finance/closing/close",
            400,  # Expect 400 error
            data={"period_type": "year", "period_key": "2026", "entity_id": ENTITY_ID}
        )
        
        if success:
            self.log("  Overlap protection working: Year closing rejected", "SUCCESS")
            return True
        else:
            self.log("  Overlap protection NOT working: Year closing should have been rejected", "FAIL")
            return False

    def test_list_closings(self):
        """Test listing closings for entity"""
        self.log("\n=== LIST CLOSINGS ===", "INFO")
        success, response = self.run_test(
            "List closings for entity",
            "GET",
            "/finance/closing",
            200,
            params={"entity_id": ENTITY_ID}
        )
        if success and response:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log(f"  Found {len(data)} closing records", "SUCCESS")
                    for closing in data[:3]:  # Show first 3
                        self.log(f"    - {closing.get('period_label')} ({closing.get('status')})", "INFO")
                    return True, data
                else:
                    self.log(f"  Unexpected response format", "WARN")
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False, None

    def test_reopen_period(self):
        """Test reopening a closed period"""
        self.log("\n=== REOPEN PERIOD ===", "INFO")
        
        # First get list of closings to find a closed one
        success, closings = self.test_list_closings()
        if not success or not closings:
            self.log("  No closings found to reopen", "WARN")
            return False
        
        # Find a closed period
        closed_period = None
        for closing in closings:
            if closing.get('status') == 'closed':
                closed_period = closing
                break
        
        if not closed_period:
            self.log("  No closed periods found to reopen", "WARN")
            return False
        
        closing_id = closed_period.get('id')
        self.log(f"  Reopening: {closed_period.get('period_label')} (ID: {closing_id})", "INFO")
        
        success, response = self.run_test(
            f"Reopen period {closed_period.get('period_label')}",
            "POST",
            f"/finance/closing/{closing_id}/reopen",
            200
        )
        
        if success and response:
            try:
                data = response.json()
                self.log(f"  Status after reopen: {data.get('status')}", "SUCCESS")
                self.log(f"  Reopened by: {data.get('reopened_by')}", "SUCCESS")
                return True, data
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False, None

    def test_status_for_date(self):
        """Test checking closing status for a date"""
        self.log("\n=== CLOSING STATUS FOR DATE ===", "INFO")
        success, response = self.run_test(
            "Check status for 2026-08-15",
            "GET",
            "/finance/closing/status",
            200,
            params={"date": "2026-08-15", "entity_id": ENTITY_ID}
        )
        if success and response:
            try:
                data = response.json()
                self.log(f"  Closed: {data.get('closed')}", "INFO")
                if data.get('closed'):
                    self.log(f"  Period: {data.get('period_label')}", "INFO")
                    self.log(f"  Closed at: {data.get('closed_at')}", "INFO")
                return True, data
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False, None

    def test_reject_all_entity_mode(self):
        """Test that closing rejects 'all' entity mode"""
        self.log("\n=== REJECT 'ALL' ENTITY MODE ===", "INFO")
        success, response = self.run_test(
            "Try to close with entity_id='all' (should fail)",
            "POST",
            "/finance/closing/close",
            400,  # Expect 400 error
            data={"period_type": "month", "period_key": "2026-09", "entity_id": "all"}
        )
        
        if success:
            self.log("  'All' entity mode correctly rejected", "SUCCESS")
            return True
        else:
            self.log("  'All' entity mode should have been rejected", "FAIL")
            return False

    def test_accounting_effects_income_statement(self):
        """Test that Income Statement excludes closing entries"""
        self.log("\n=== ACCOUNTING EFFECTS - INCOME STATEMENT ===", "INFO")
        
        # Get income statement for a closed period
        success, response = self.run_test(
            "Income Statement for closed period (should exclude closing entries)",
            "GET",
            "/finance/income-statement",
            200,
            params={"start": "2026-08-01", "end": "2026-08-31", "entity_id": ENTITY_ID}
        )
        
        if success and response:
            try:
                data = response.json()
                self.log(f"  Revenue: {data.get('revenue_total')}", "INFO")
                self.log(f"  Net Income: {data.get('net_income')}", "INFO")
                self.log("  Income statement should show operational figures (excluding closing entries)", "SUCCESS")
                return True, data
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False, None

    def test_accounting_effects_balance_sheet(self):
        """Test that Balance Sheet includes closing entries"""
        self.log("\n=== ACCOUNTING EFFECTS - BALANCE SHEET ===", "INFO")
        
        # Get balance sheet after closing
        success, response = self.run_test(
            "Balance Sheet after closing (should include closing entries)",
            "GET",
            "/finance/balance-sheet",
            200,
            params={"as_of": "2026-08-31", "entity_id": ENTITY_ID}
        )
        
        if success and response:
            try:
                data = response.json()
                balanced = data.get('balanced')
                self.log(f"  Assets: {data.get('assets_total')}", "INFO")
                self.log(f"  Liabilities + Equity: {data.get('liabilities_equity_total')}", "INFO")
                self.log(f"  Balanced: {balanced}", "SUCCESS" if balanced else "FAIL")
                
                # Check Retained Earnings (3-2000) in equity
                equity = data.get('equity', {})
                equity_lines = equity.get('lines', [])
                retained_earnings = None
                for line in equity_lines:
                    if line.get('code') == '3-2000':
                        retained_earnings = line
                        break
                
                if retained_earnings:
                    self.log(f"  Retained Earnings (3-2000): {retained_earnings.get('amount')}", "SUCCESS")
                else:
                    self.log("  Retained Earnings (3-2000) not found in equity", "WARN")
                
                return True, data
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False, None

    def test_gl_regression_trial_balance(self):
        """Test GL regression: trial balance still balanced"""
        self.log("\n=== GL REGRESSION - TRIAL BALANCE ===", "INFO")
        success, response = self.run_test(
            "GL Trial Balance",
            "GET",
            "/gl/trial-balance",
            200,
            params={"entity_id": ENTITY_ID}
        )
        if success and response:
            try:
                data = response.json()
                balanced = data.get('balanced')
                total_debit = data.get('total_debit', 0)
                total_credit = data.get('total_credit', 0)
                self.log(f"  Debit: {total_debit}, Credit: {total_credit}, Balanced: {balanced}", 
                        "SUCCESS" if balanced else "FAIL")
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_gl_regression_summary(self):
        """Test GL regression: summary still works"""
        self.log("\n=== GL REGRESSION - SUMMARY ===", "INFO")
        success, response = self.run_test(
            "GL Summary",
            "GET",
            "/gl/summary",
            200,
            params={"entity_id": ENTITY_ID}
        )
        if success and response:
            try:
                data = response.json()
                balanced = data.get('balanced')
                self.log(f"  Journals: {data.get('journal_count')}, Balanced: {balanced}", 
                        "SUCCESS" if balanced else "FAIL")
                return True
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
    tester = ClosingAPITester()
    
    print("\n" + "="*60)
    print("PERIOD CLOSING MODULE - BACKEND API TESTS")
    print("="*60)
    
    # Authentication
    if not tester.test_login():
        print("\n❌ Login failed, stopping tests")
        return 1
    
    # Preview Tests
    tester.test_preview_monthly()
    tester.test_preview_yearly()
    
    # List existing closings
    tester.test_list_closings()
    
    # Status check
    tester.test_status_for_date()
    
    # Close period test
    tester.test_close_monthly()
    
    # Overlap protection
    tester.test_overlap_protection_month_then_year()
    
    # Reopen test
    tester.test_reopen_period()
    
    # Multi-entity rejection
    tester.test_reject_all_entity_mode()
    
    # Accounting effects
    tester.test_accounting_effects_income_statement()
    tester.test_accounting_effects_balance_sheet()
    
    # GL Regression
    tester.test_gl_regression_trial_balance()
    tester.test_gl_regression_summary()
    
    # Print summary
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
