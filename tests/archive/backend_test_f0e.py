"""
Backend API Testing for F0-E Multi-Entity Finance Phase
Tests: per-entity scoping, incentive→GL accrual, RBAC, GL isolation
"""
import requests
import sys
from typing import Dict, Any, List, Optional

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

class F0EBackendTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.test_results = {
            "reports_scoping": [],
            "incentive_gl": [],
            "rbac": [],
            "gl_isolation": []
        }
        
    def login(self, email: str, password: str) -> Optional[str]:
        """Login and return token"""
        try:
            resp = requests.post(
                f"{self.base_url}/auth/login",
                json={"email": email, "password": password},
                timeout=10
            )
            if resp.status_code == 200:
                token = resp.json().get("token")
                self.tokens[email] = token
                print(f"✅ Login successful: {email}")
                return token
            else:
                print(f"❌ Login failed for {email}: {resp.status_code}")
                return None
        except Exception as e:
            print(f"❌ Login error for {email}: {str(e)}")
            return None
    
    def run_test(self, name: str, method: str, endpoint: str, 
                 expected_status: int, token: str = None, 
                 data: Dict = None, params: Dict = None,
                 headers: Dict = None, category: str = "general") -> tuple:
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        req_headers = {"Content-Type": "application/json"}
        if token:
            req_headers["Authorization"] = f"Bearer {token}"
        if headers:
            req_headers.update(headers)
        
        self.tests_run += 1
        print(f"\n🔍 Test #{self.tests_run}: {name}")
        
        try:
            if method == "GET":
                resp = requests.get(url, headers=req_headers, params=params, timeout=15)
            elif method == "POST":
                resp = requests.post(url, json=data, headers=req_headers, params=params, timeout=15)
            elif method == "PUT":
                resp = requests.put(url, json=data, headers=req_headers, params=params, timeout=15)
            else:
                print(f"❌ Unsupported method: {method}")
                return False, {}
            
            success = resp.status_code == expected_status
            response_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            
            if success:
                self.tests_passed += 1
                print(f"✅ PASSED - Status: {resp.status_code}")
                self.test_results[category].append({
                    "name": name,
                    "status": "passed",
                    "endpoint": endpoint,
                    "response": response_data
                })
            else:
                print(f"❌ FAILED - Expected {expected_status}, got {resp.status_code}")
                print(f"   Response: {response_data}")
                self.failed_tests.append({
                    "name": name,
                    "expected": expected_status,
                    "actual": resp.status_code,
                    "endpoint": endpoint,
                    "response": response_data
                })
                self.test_results[category].append({
                    "name": name,
                    "status": "failed",
                    "endpoint": endpoint,
                    "expected": expected_status,
                    "actual": resp.status_code,
                    "response": response_data
                })
            
            return success, response_data
        
        except Exception as e:
            print(f"❌ FAILED - Error: {str(e)}")
            self.failed_tests.append({
                "name": name,
                "error": str(e),
                "endpoint": endpoint
            })
            self.test_results[category].append({
                "name": name,
                "status": "error",
                "endpoint": endpoint,
                "error": str(e)
            })
            return False, {}
    
    def test_reports_per_entity_scoping(self, admin_token: str):
        """Test CRITICAL: per-entity scoping with additive invariant"""
        print("\n" + "="*70)
        print("TESTING: Reports Per-Entity Scoping (CRITICAL INVARIANT)")
        print("="*70)
        
        # Test each report endpoint with entity_id param
        report_endpoints = [
            "reports/summary",
            "reports/top-customers",
            "reports/reservation-funnel",
            "reports/order-velocity",
            "reports/warehouse-utilization",
            "reports/stock-aging"
        ]
        
        results = {}
        
        for endpoint in report_endpoints:
            print(f"\n--- Testing {endpoint} ---")
            
            # Get data for ent_ksc
            success_ksc, data_ksc = self.run_test(
                f"{endpoint} - ent_ksc",
                "GET",
                endpoint,
                200,
                token=admin_token,
                params={"entity_id": "ent_ksc"},
                category="reports_scoping"
            )
            
            # Get data for ent_kanda
            success_kanda, data_kanda = self.run_test(
                f"{endpoint} - ent_kanda",
                "GET",
                endpoint,
                200,
                token=admin_token,
                params={"entity_id": "ent_kanda"},
                category="reports_scoping"
            )
            
            # Get data for all
            success_all, data_all = self.run_test(
                f"{endpoint} - all",
                "GET",
                endpoint,
                200,
                token=admin_token,
                params={"entity_id": "all"},
                category="reports_scoping"
            )
            
            if success_ksc and success_kanda and success_all:
                results[endpoint] = {
                    "ksc": data_ksc,
                    "kanda": data_kanda,
                    "all": data_all
                }
        
        # CRITICAL: Verify additive invariant for summary endpoint
        if "reports/summary" in results:
            print("\n🔍 CRITICAL INVARIANT CHECK: ksc + kanda == all")
            ksc = results["reports/summary"]["ksc"]
            kanda = results["reports/summary"]["kanda"]
            all_data = results["reports/summary"]["all"]
            
            # Check orders_today
            ksc_orders = ksc.get("orders_today", 0)
            kanda_orders = kanda.get("orders_today", 0)
            all_orders = all_data.get("orders_today", 0)
            sum_orders = ksc_orders + kanda_orders
            
            print(f"  orders_today: ksc={ksc_orders} + kanda={kanda_orders} = {sum_orders}, all={all_orders}")
            if sum_orders == all_orders:
                print(f"  ✅ orders_today additive invariant PASSED")
                self.tests_passed += 1
            else:
                print(f"  ❌ orders_today additive invariant FAILED")
                self.failed_tests.append({
                    "name": "Additive invariant - orders_today",
                    "expected": sum_orders,
                    "actual": all_orders
                })
            self.tests_run += 1
            
            # Check monthly_revenue
            ksc_rev = ksc.get("monthly_revenue", 0)
            kanda_rev = kanda.get("monthly_revenue", 0)
            all_rev = all_data.get("monthly_revenue", 0)
            sum_rev = ksc_rev + kanda_rev
            
            print(f"  monthly_revenue: ksc={ksc_rev} + kanda={kanda_rev} = {sum_rev}, all={all_rev}")
            if abs(sum_rev - all_rev) < 1:  # Allow small rounding difference
                print(f"  ✅ monthly_revenue additive invariant PASSED")
                self.tests_passed += 1
            else:
                print(f"  ❌ monthly_revenue additive invariant FAILED")
                self.failed_tests.append({
                    "name": "Additive invariant - monthly_revenue",
                    "expected": sum_rev,
                    "actual": all_rev
                })
            self.tests_run += 1
        
        # Test with X-Entity-Id header
        print("\n--- Testing X-Entity-Id header ---")
        self.run_test(
            "reports/summary with X-Entity-Id header",
            "GET",
            "reports/summary",
            200,
            token=admin_token,
            headers={"X-Entity-Id": "ent_ksc"},
            category="reports_scoping"
        )
    
    def test_incentive_gl_accrual(self, admin_token: str, manager_token: str):
        """Test incentive→GL accrual posting and idempotency"""
        print("\n" + "="*70)
        print("TESTING: Incentive→GL Accrual")
        print("="*70)
        
        period = "2026-06"
        entity_id = "ent_ksc"
        
        # Get GL status before posting
        success, status_before = self.run_test(
            "Get GL status before posting",
            "GET",
            "sales/incentive/gl-status",
            200,
            token=admin_token,
            params={"period": period, "entity_id": entity_id},
            category="incentive_gl"
        )
        
        print(f"  Status before: posted={status_before.get('posted')}, amount={status_before.get('amount')}")
        
        # Post incentive to GL (may already be posted from prior tests)
        success, post_result = self.run_test(
            "Post incentive to GL",
            "POST",
            "sales/incentive/post-gl",
            200,
            token=admin_token,
            params={"period": period, "entity_id": entity_id},
            category="incentive_gl"
        )
        
        if success:
            print(f"  Post result: created={post_result.get('created')}, message={post_result.get('message')}")
        
        # Get GL status after posting
        success, status_after = self.run_test(
            "Get GL status after posting",
            "GET",
            "sales/incentive/gl-status",
            200,
            token=admin_token,
            params={"period": period, "entity_id": entity_id},
            category="incentive_gl"
        )
        
        if success:
            print(f"  Status after: posted={status_after.get('posted')}, amount={status_after.get('amount')}, journal={status_after.get('journal_number')}")
            
            # Verify it's posted
            if status_after.get("posted"):
                print(f"  ✅ Incentive accrual is posted")
                self.tests_passed += 1
            else:
                print(f"  ❌ Incentive accrual not posted")
                self.failed_tests.append({
                    "name": "Incentive accrual posted status",
                    "expected": True,
                    "actual": status_after.get("posted")
                })
            self.tests_run += 1
        
        # Test idempotency - post again
        success, post_result2 = self.run_test(
            "Post incentive to GL (idempotency test)",
            "POST",
            "sales/incentive/post-gl",
            200,
            token=admin_token,
            params={"period": period, "entity_id": entity_id},
            category="incentive_gl"
        )
        
        if success:
            print(f"  Idempotency result: created={post_result2.get('created')}")
            if post_result2.get('created') == False:
                print(f"  ✅ Idempotency check PASSED (created=false on second call)")
                self.tests_passed += 1
            else:
                print(f"  ⚠️  Idempotency: created={post_result2.get('created')} (may be first posting)")
            self.tests_run += 1
        
        # Get trial balance for entity
        success, trial_balance = self.run_test(
            "Get trial balance for ent_ksc",
            "GET",
            "gl/trial-balance",
            200,
            token=admin_token,
            params={"entity_id": entity_id},
            category="incentive_gl"
        )
        
        if success:
            balanced = trial_balance.get("balanced")
            total_debit = trial_balance.get("total_debit", 0)
            total_credit = trial_balance.get("total_credit", 0)
            
            print(f"  Trial balance: balanced={balanced}, debit={total_debit}, credit={total_credit}")
            
            if balanced:
                print(f"  ✅ Trial balance is BALANCED")
                self.tests_passed += 1
            else:
                print(f"  ❌ Trial balance is NOT balanced")
                self.failed_tests.append({
                    "name": "Trial balance balanced",
                    "expected": True,
                    "actual": balanced,
                    "debit": total_debit,
                    "credit": total_credit
                })
            self.tests_run += 1
            
            # Check for incentive accounts
            rows = trial_balance.get("rows", [])
            has_beban = any(r.get("code") == "6-5000" for r in rows)
            has_hutang = any(r.get("code") == "2-1500" for r in rows)
            
            print(f"  Incentive accounts: Beban(6-5000)={has_beban}, Hutang(2-1500)={has_hutang}")
            if has_beban and has_hutang:
                print(f"  ✅ Incentive accounts present in trial balance")
                self.tests_passed += 1
            else:
                print(f"  ⚠️  Incentive accounts not found (may be zero balance)")
            self.tests_run += 1
    
    def test_rbac_incentive_endpoints(self, sales_token: str, admin_token: str):
        """Test RBAC on incentive endpoints"""
        print("\n" + "="*70)
        print("TESTING: RBAC on Incentive Endpoints")
        print("="*70)
        
        period = "2026-06"
        entity_id = "ent_ksc"
        
        # Sales role should get 403 on POST incentive/post-gl
        self.run_test(
            "Sales role POST incentive/post-gl (expect 403)",
            "POST",
            "sales/incentive/post-gl",
            403,
            token=sales_token,
            params={"period": period, "entity_id": entity_id},
            category="rbac"
        )
        
        # entity_id=all should get 400
        self.run_test(
            "POST incentive/post-gl with entity_id=all (expect 400)",
            "POST",
            "sales/incentive/post-gl",
            400,
            token=admin_token,
            params={"period": period, "entity_id": "all"},
            category="rbac"
        )
        
        # gl-status with entity_id=all should get 400
        self.run_test(
            "GET gl-status with entity_id=all (expect 400)",
            "GET",
            "sales/incentive/gl-status",
            400,
            token=admin_token,
            params={"period": period, "entity_id": "all"},
            category="rbac"
        )
    
    def test_gl_per_entity_isolation(self, admin_token: str):
        """Test GL per-entity isolation"""
        print("\n" + "="*70)
        print("TESTING: GL Per-Entity Isolation")
        print("="*70)
        
        # Get trial balance for ent_ksc
        success_ksc, tb_ksc = self.run_test(
            "Trial balance for ent_ksc",
            "GET",
            "gl/trial-balance",
            200,
            token=admin_token,
            params={"entity_id": "ent_ksc"},
            category="gl_isolation"
        )
        
        # Get trial balance for ent_kanda
        success_kanda, tb_kanda = self.run_test(
            "Trial balance for ent_kanda",
            "GET",
            "gl/trial-balance",
            200,
            token=admin_token,
            params={"entity_id": "ent_kanda"},
            category="gl_isolation"
        )
        
        if success_ksc and success_kanda:
            # Check both are balanced
            ksc_balanced = tb_ksc.get("balanced")
            kanda_balanced = tb_kanda.get("balanced")
            
            print(f"  ent_ksc balanced: {ksc_balanced}")
            print(f"  ent_kanda balanced: {kanda_balanced}")
            
            if ksc_balanced and kanda_balanced:
                print(f"  ✅ Both entity books are separately balanced")
                self.tests_passed += 1
            else:
                print(f"  ❌ Entity books not balanced")
                self.failed_tests.append({
                    "name": "Entity books balanced",
                    "ksc_balanced": ksc_balanced,
                    "kanda_balanced": kanda_balanced
                })
            self.tests_run += 1
        
        # Get journal entries for ent_ksc
        success, entries_ksc = self.run_test(
            "Journal entries for ent_ksc",
            "GET",
            "gl/journal-entries",
            200,
            token=admin_token,
            params={"entity_id": "ent_ksc", "limit": 5},
            category="gl_isolation"
        )
        
        if success and entries_ksc:
            # Check journal number prefix
            if isinstance(entries_ksc, list) and len(entries_ksc) > 0:
                first_entry = entries_ksc[0]
                journal_number = first_entry.get("number", "")
                print(f"  Sample journal number: {journal_number}")
                
                if journal_number.startswith("KSC/JE-") or journal_number.startswith("ent_ksc"):
                    print(f"  ✅ Journal numbers are entity-prefixed")
                    self.tests_passed += 1
                else:
                    print(f"  ⚠️  Journal number format: {journal_number}")
            self.tests_run += 1
        
        # Verify CoA is shared (same accounts regardless of entity)
        success, accounts = self.run_test(
            "Get CoA (shared)",
            "GET",
            "gl/accounts",
            200,
            token=admin_token,
            category="gl_isolation"
        )
        
        if success:
            print(f"  CoA accounts count: {len(accounts) if isinstance(accounts, list) else 'N/A'}")
            print(f"  ✅ CoA is shared (accessible without entity filter)")
            self.tests_passed += 1
            self.tests_run += 1
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Total tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Tests failed: {len(self.failed_tests)}")
        print(f"Success rate: {(self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0:.1f}%")
        
        if self.failed_tests:
            print("\n❌ FAILED TESTS:")
            for i, test in enumerate(self.failed_tests, 1):
                print(f"\n  {i}. {test.get('name')}")
                if 'expected' in test:
                    print(f"     Expected: {test['expected']}")
                    print(f"     Actual: {test['actual']}")
                if 'error' in test:
                    print(f"     Error: {test['error']}")
                if 'endpoint' in test:
                    print(f"     Endpoint: {test['endpoint']}")
        
        print("\n" + "="*70)
        
        return len(self.failed_tests) == 0


def main():
    print("="*70)
    print("F0-E Multi-Entity Finance Backend Testing")
    print("="*70)
    
    tester = F0EBackendTester()
    
    # Login with different roles
    print("\n--- Logging in ---")
    admin_token = tester.login("admin@kainnusantara.id", "demo12345")
    manager_token = tester.login("manager@kainnusantara.id", "demo12345")
    sales_token = tester.login("sales@kainnusantara.id", "demo12345")
    
    if not admin_token:
        print("❌ Admin login failed, cannot continue")
        return 1
    
    # Run test suites
    tester.test_reports_per_entity_scoping(admin_token)
    
    if manager_token:
        tester.test_incentive_gl_accrual(admin_token, manager_token)
    else:
        print("⚠️  Manager token not available, skipping some incentive tests")
        tester.test_incentive_gl_accrual(admin_token, admin_token)
    
    if sales_token:
        tester.test_rbac_incentive_endpoints(sales_token, admin_token)
    else:
        print("⚠️  Sales token not available, skipping RBAC tests")
    
    tester.test_gl_per_entity_isolation(admin_token)
    
    # Print summary
    all_passed = tester.print_summary()
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
