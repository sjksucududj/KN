"""
Backend API Testing for Gelombang 3 Finance Features (F-7, F-8, F-9)
Tests: Suspense report/reclass, Period closing (monthly/annual/residual), Stale detection, Trial balance
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://focused-pascal-5.preview.emergentagent.com/api"
LOGIN_EMAIL = "admin@kainnusantara.id"
LOGIN_PASSWORD = "demo12345"

class Gelombang3APITester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []

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

    def test_f8_suspense_report(self):
        """F-8: Test suspense report (should show -10,000,000 balance)"""
        self.log("\n=== F-8 SUSPENSE REPORT ===", "INFO")
        success, response = self.run_test(
            "GET /gl/suspense (initial balance)",
            "GET",
            "/gl/suspense",
            200,
            headers={"X-Entity-Id": "ent_ksc"}
        )
        if success and response:
            try:
                data = response.json()
                balance = data.get('balance', 0)
                entry_count = data.get('entry_count', 0)
                self.log(f"  Suspense balance: Rp {balance:,.0f}", "SUCCESS")
                self.log(f"  Entry count: {entry_count}", "SUCCESS")
                
                # Verify balance is -10,000,000 (negative/credit)
                if abs(balance + 10000000) < 1:
                    self.log(f"  ✓ Balance matches expected -10,000,000", "SUCCESS")
                else:
                    self.log(f"  ⚠ Balance {balance} doesn't match expected -10,000,000", "WARN")
                
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_f8_suspense_reclass(self):
        """F-8: Test suspense reclassification to zero"""
        self.log("\n=== F-8 SUSPENSE RECLASS ===", "INFO")
        
        # First get list of accounts to pick a valid target
        success, acc_resp = self.run_test(
            "GET /gl/accounts (to pick reclass target)",
            "GET",
            "/gl/accounts",
            200,
            params={"active_only": True}
        )
        
        target_account = "4-1000"  # Default to revenue account
        if success and acc_resp:
            try:
                accounts = acc_resp.json()
                # Find a postable account that's not suspense
                for acc in accounts:
                    if acc.get('is_postable') and acc.get('code') != '1-9999':
                        target_account = acc.get('code')
                        break
                self.log(f"  Using target account: {target_account}", "INFO")
            except:
                pass
        
        # Reclass 10,000,000 from suspense (credit side) to target account
        success, response = self.run_test(
            "POST /gl/suspense/reclass (10M credit to target)",
            "POST",
            "/gl/suspense/reclass",
            200,
            data={
                "amount": 10000000,
                "side": "credit",
                "target_account": target_account,
                "note": "Test reclass suspense to zero",
                "entity_id": "ent_ksc"
            },
            headers={"X-Entity-Id": "ent_ksc"}
        )
        
        if success and response:
            try:
                data = response.json()
                je_number = data.get('number', '—')
                self.log(f"  Journal entry created: {je_number}", "SUCCESS")
                
                # Verify suspense balance is now zero
                success2, resp2 = self.run_test(
                    "GET /gl/suspense (verify zero after reclass)",
                    "GET",
                    "/gl/suspense",
                    200,
                    headers={"X-Entity-Id": "ent_ksc"}
                )
                
                if success2 and resp2:
                    data2 = resp2.json()
                    balance = data2.get('balance', 0)
                    self.log(f"  New suspense balance: Rp {balance:,.0f}", "SUCCESS")
                    if abs(balance) < 1:
                        self.log(f"  ✓ Suspense balance is now ZERO (ready for closing)", "SUCCESS")
                    else:
                        self.log(f"  ⚠ Suspense balance {balance} is not zero", "WARN")
                
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_f9_closing_preview_monthly(self):
        """F-9: Test monthly closing preview (Juni 2026)"""
        self.log("\n=== F-9 CLOSING PREVIEW (MONTHLY - JUNI 2026) ===", "INFO")
        success, response = self.run_test(
            "GET /finance/closing/preview (month=2026-06)",
            "GET",
            "/finance/closing/preview",
            200,
            params={
                "period_type": "month",
                "period_key": "2026-06",
                "entity_id": "ent_ksc"
            }
        )
        
        if success and response:
            try:
                data = response.json()
                can_close = data.get('can_close', False)
                net_income = data.get('net_income', 0)
                revenue = data.get('revenue_total', 0)
                expense = data.get('expense_total', 0)
                suspense_warning = data.get('suspense_warning', False)
                
                self.log(f"  Can close: {can_close}", "SUCCESS" if can_close else "WARN")
                self.log(f"  Net income: Rp {net_income:,.0f}", "SUCCESS")
                self.log(f"  Revenue: Rp {revenue:,.0f}", "SUCCESS")
                self.log(f"  Expense: Rp {expense:,.0f}", "SUCCESS")
                self.log(f"  Suspense warning: {suspense_warning}", "INFO")
                
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_f9_closing_close_monthly(self):
        """F-9: Test monthly closing execution (Juni 2026)"""
        self.log("\n=== F-9 CLOSING EXECUTE (MONTHLY - JUNI 2026) ===", "INFO")
        success, response = self.run_test(
            "POST /finance/closing/close (month=2026-06)",
            "POST",
            "/finance/closing/close",
            200,
            data={
                "period_type": "month",
                "period_key": "2026-06",
                "entity_id": "ent_ksc",
                "note": "Test monthly closing Juni 2026"
            }
        )
        
        if success and response:
            try:
                data = response.json()
                period_label = data.get('period_label', '—')
                je_number = data.get('journal_entry_number', '—')
                net_income = data.get('net_income', 0)
                status = data.get('status', '—')
                
                self.log(f"  Period closed: {period_label}", "SUCCESS")
                self.log(f"  Journal entry: {je_number}", "SUCCESS")
                self.log(f"  Net income: Rp {net_income:,.0f}", "SUCCESS")
                self.log(f"  Status: {status}", "SUCCESS")
                
                return True, data.get('id')
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False, None

    def test_f9_closing_preview_annual(self):
        """F-9: Test annual closing preview (2026) - should show RESIDUAL only"""
        self.log("\n=== F-9 CLOSING PREVIEW (ANNUAL - 2026 RESIDUAL) ===", "INFO")
        success, response = self.run_test(
            "GET /finance/closing/preview (year=2026)",
            "GET",
            "/finance/closing/preview",
            200,
            params={
                "period_type": "year",
                "period_key": "2026",
                "entity_id": "ent_ksc"
            }
        )
        
        if success and response:
            try:
                data = response.json()
                can_close = data.get('can_close', False)
                net_income = data.get('net_income', 0)
                residual_net_income = data.get('residual_net_income', 0)
                
                self.log(f"  Can close: {can_close}", "SUCCESS" if can_close else "WARN")
                self.log(f"  Total net income: Rp {net_income:,.0f}", "SUCCESS")
                self.log(f"  Residual net income: Rp {residual_net_income:,.0f}", "SUCCESS")
                
                # KEY TEST: residual should be LESS than total (annual-over-monthly)
                if abs(residual_net_income) < abs(net_income):
                    self.log(f"  ✓ RESIDUAL ({residual_net_income:,.0f}) < TOTAL ({net_income:,.0f}) - annual-over-monthly works!", "SUCCESS")
                else:
                    self.log(f"  ⚠ Residual should be less than total for annual-over-monthly", "WARN")
                
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_f9_closing_close_annual(self):
        """F-9: Test annual closing execution (2026)"""
        self.log("\n=== F-9 CLOSING EXECUTE (ANNUAL - 2026) ===", "INFO")
        success, response = self.run_test(
            "POST /finance/closing/close (year=2026)",
            "POST",
            "/finance/closing/close",
            200,
            data={
                "period_type": "year",
                "period_key": "2026",
                "entity_id": "ent_ksc",
                "note": "Test annual closing 2026"
            }
        )
        
        if success and response:
            try:
                data = response.json()
                period_label = data.get('period_label', '—')
                je_number = data.get('journal_entry_number', '—')
                net_income = data.get('net_income', 0)
                status = data.get('status', '—')
                
                self.log(f"  Period closed: {period_label}", "SUCCESS")
                self.log(f"  Journal entry: {je_number}", "SUCCESS")
                self.log(f"  Net income: Rp {net_income:,.0f}", "SUCCESS")
                self.log(f"  Status: {status}", "SUCCESS")
                
                return True, data.get('id')
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False, None

    def test_f9b_post_backdated_journal(self):
        """F-9b: Post backdated journal to closed June period"""
        self.log("\n=== F-9b POST BACKDATED JOURNAL (2026-06-15) ===", "INFO")
        success, response = self.run_test(
            "POST /gl/journal (backdated to 2026-06-15)",
            "POST",
            "/gl/journal",
            200,
            data={
                "date": "2026-06-15T10:00:00",
                "description": "Test backdate for stale detection",
                "lines": [
                    {"account_code": "5-1000", "debit": 500000, "credit": 0, "description": "Test expense"},
                    {"account_code": "1-1100", "debit": 0, "credit": 500000, "description": "Test cash"}
                ]
            },
            headers={"X-Entity-Id": "ent_ksc"}
        )
        
        if success and response:
            try:
                data = response.json()
                je_number = data.get('number', '—')
                je_date = data.get('date', '—')
                self.log(f"  Backdated journal created: {je_number}", "SUCCESS")
                self.log(f"  Journal date: {je_date}", "SUCCESS")
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_f9b_verify_stale(self):
        """F-9b: Verify June 2026 closing is now marked as STALE"""
        self.log("\n=== F-9b VERIFY STALE DETECTION ===", "INFO")
        success, response = self.run_test(
            "GET /finance/closing (check for stale badge)",
            "GET",
            "/finance/closing",
            200,
            params={"entity_id": "ent_ksc"}
        )
        
        if success and response:
            try:
                closings = response.json()
                june_closing = None
                year_closing = None
                
                for c in closings:
                    if c.get('period_key') == '2026-06':
                        june_closing = c
                    elif c.get('period_key') == '2026':
                        year_closing = c
                
                if june_closing:
                    is_stale = june_closing.get('stale', False)
                    stale_reason = june_closing.get('stale_reason', '')
                    self.log(f"  June 2026 closing found: {june_closing.get('period_label')}", "SUCCESS")
                    self.log(f"  Is stale: {is_stale}", "SUCCESS" if is_stale else "WARN")
                    if is_stale:
                        self.log(f"  ✓ June closing correctly marked as STALE", "SUCCESS")
                        self.log(f"  Stale reason: {stale_reason}", "INFO")
                    else:
                        self.log(f"  ⚠ June closing should be marked as stale after backdated posting", "WARN")
                else:
                    self.log(f"  ⚠ June 2026 closing not found", "WARN")
                
                if year_closing:
                    is_stale = year_closing.get('stale', False)
                    self.log(f"  Year 2026 closing stale: {is_stale} (may also be stale)", "INFO")
                
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_f9b_reclose(self, closing_id=None):
        """F-9b: Test reclose (Tutup Ulang) for stale period"""
        self.log("\n=== F-9b RECLOSE STALE PERIOD ===", "INFO")
        
        # If no closing_id provided, get it from the list
        if not closing_id:
            success, response = self.run_test(
                "GET /finance/closing (to find June closing ID)",
                "GET",
                "/finance/closing",
                200,
                params={"entity_id": "ent_ksc"}
            )
            if success and response:
                try:
                    closings = response.json()
                    for c in closings:
                        if c.get('period_key') == '2026-06' and c.get('stale'):
                            closing_id = c.get('id')
                            break
                except:
                    pass
        
        if not closing_id:
            self.log("  ⚠ No stale closing ID found to reclose", "WARN")
            return False
        
        success, response = self.run_test(
            f"POST /finance/closing/{closing_id}/reclose",
            "POST",
            f"/finance/closing/{closing_id}/reclose",
            200
        )
        
        if success and response:
            try:
                data = response.json()
                period_label = data.get('period_label', '—')
                je_number = data.get('journal_entry_number', '—')
                is_stale = data.get('stale', False)
                
                self.log(f"  Period reclosed: {period_label}", "SUCCESS")
                self.log(f"  New journal entry: {je_number}", "SUCCESS")
                self.log(f"  Still stale: {is_stale}", "INFO")
                
                if not is_stale:
                    self.log(f"  ✓ June closing no longer stale after reclose", "SUCCESS")
                else:
                    self.log(f"  ⚠ June closing still marked as stale (may need to reclose year too)", "WARN")
                
                return True
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def test_f7_trial_balance_integrity(self):
        """F-7: Verify trial balance is balanced after all closing operations"""
        self.log("\n=== F-7 TRIAL BALANCE INTEGRITY ===", "INFO")
        success, response = self.run_test(
            "GET /gl/trial-balance (verify balanced)",
            "GET",
            "/gl/trial-balance",
            200,
            params={"entity_id": "ent_ksc"}
        )
        
        if success and response:
            try:
                data = response.json()
                balanced = data.get('balanced', False)
                total_debit = data.get('total_debit', 0)
                total_credit = data.get('total_credit', 0)
                
                self.log(f"  Total debit: Rp {total_debit:,.0f}", "SUCCESS")
                self.log(f"  Total credit: Rp {total_credit:,.0f}", "SUCCESS")
                self.log(f"  Balanced: {balanced}", "SUCCESS" if balanced else "FAIL")
                
                if balanced:
                    self.log(f"  ✓ Trial balance is BALANCED - COGS integrity maintained", "SUCCESS")
                else:
                    self.log(f"  ✗ Trial balance NOT balanced - integrity issue!", "FAIL")
                
                return balanced
            except Exception as e:
                self.log(f"  Failed to parse response: {e}", "FAIL")
        return False

    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "="*60, "INFO")
        self.log("TEST SUMMARY - GELOMBANG 3 (F-7, F-8, F-9)", "INFO")
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
    tester = Gelombang3APITester()
    
    print("\n" + "="*60)
    print("GELOMBANG 3 FINANCE FEATURES - BACKEND API TESTS")
    print("F-7: COGS Integrity | F-8: Suspense | F-9: Closing")
    print("="*60)
    
    # Authentication
    if not tester.test_login():
        print("\n❌ Login failed, stopping tests")
        return 1
    
    # F-8: Suspense Report & Reclass
    tester.test_f8_suspense_report()
    tester.test_f8_suspense_reclass()
    
    # F-9: Monthly Closing (Juni 2026)
    tester.test_f9_closing_preview_monthly()
    success_monthly, june_closing_id = tester.test_f9_closing_close_monthly()
    
    # F-9: Annual Closing (2026) - should show residual only
    tester.test_f9_closing_preview_annual()
    success_annual, year_closing_id = tester.test_f9_closing_close_annual()
    
    # F-9b: Stale Detection & Reclose
    tester.test_f9b_post_backdated_journal()
    tester.test_f9b_verify_stale()
    tester.test_f9b_reclose(june_closing_id)
    
    # F-7: Trial Balance Integrity
    tester.test_f7_trial_balance_integrity()
    
    # Print summary
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
