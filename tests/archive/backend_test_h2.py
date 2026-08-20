"""
Backend Testing for FASE H2: HRD Live Tracking + Visits (Kunjungan)
Tests all H2 endpoints with RBAC and business rules
"""
import requests
import sys
from typing import Dict, Any, Optional

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

class H2TestRunner:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.admin_token = None
        self.manager_token = None
        self.sales_token = None
        self.failures = []
        self.created_visit_id = None

    def log(self, message: str, level: str = "INFO"):
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "•")
        print(f"{prefix} {message}")

    def test(self, name: str, method: str, endpoint: str, expected_status: int,
             data: Optional[Dict] = None, token: Optional[str] = None,
             check_response: Optional[callable] = None) -> tuple[bool, Any]:
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.log(f"Test #{self.tests_run}: {name}", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            response_data = {}
            try:
                response_data = response.json()
            except:
                pass

            if success:
                # Additional response checks
                if check_response and not check_response(response_data):
                    success = False
                    self.log(f"  Response validation failed", "FAIL")
                    self.failures.append(f"{name}: Response validation failed")
                    self.tests_failed += 1
                else:
                    self.tests_passed += 1
                    self.log(f"  PASSED (status: {response.status_code})", "PASS")
            else:
                self.log(f"  FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                if response_data:
                    self.log(f"  Response: {response_data}", "FAIL")
                self.failures.append(f"{name}: Expected {expected_status}, got {response.status_code}")
                self.tests_failed += 1

            return success, response_data

        except Exception as e:
            self.log(f"  FAILED - Error: {str(e)}", "FAIL")
            self.failures.append(f"{name}: {str(e)}")
            self.tests_failed += 1
            return False, {}

    def login(self, email: str, password: str) -> Optional[str]:
        """Login and return token"""
        self.log(f"Logging in as {email}...", "INFO")
        success, data = self.test(
            f"Login {email}",
            "POST",
            "auth/login",
            200,
            data={"email": email, "password": password}
        )
        if success and 'token' in data:
            # Check token prefix
            token = data['token']
            if token.startswith('sess_'):
                self.log(f"  Login successful, token obtained (prefix: sess_) ✓", "PASS")
            else:
                self.log(f"  Login successful but token prefix is '{token[:5]}...' (expected sess_)", "WARN")
            return token
        self.log(f"  Login failed", "FAIL")
        return None

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("TEST SUMMARY - FASE H2")
        print("="*70)
        print(f"Total Tests: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {self.tests_failed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0:.1f}%")
        
        if self.failures:
            print("\n" + "="*70)
            print("FAILURES:")
            print("="*70)
            for i, failure in enumerate(self.failures, 1):
                print(f"{i}. {failure}")
        
        print("="*70)


def main():
    runner = H2TestRunner()
    
    print("="*70)
    print("KAIN NUSANTARA - FASE H2: HRD LIVE TRACKING + VISITS")
    print("Backend API Testing")
    print("="*70)
    print()

    # ========== AUTHENTICATION ==========
    print("\n" + "="*70)
    print("PHASE 1: AUTHENTICATION (3 roles)")
    print("="*70)
    
    runner.admin_token = runner.login("admin@kainnusantara.id", "demo12345")
    if not runner.admin_token:
        print("❌ CRITICAL: Admin login failed. Cannot continue.")
        return 1
    
    runner.manager_token = runner.login("manager@kainnusantara.id", "demo12345")
    if not runner.manager_token:
        print("❌ CRITICAL: Manager login failed. Cannot continue.")
        return 1
    
    runner.sales_token = runner.login("sales@kainnusantara.id", "demo12345")
    if not runner.sales_token:
        print("❌ CRITICAL: Sales login failed. Cannot continue.")
        return 1

    # ========== FIELD TRACKS - LATEST POSITIONS ==========
    print("\n" + "="*70)
    print("PHASE 2: FIELD TRACKS - Latest Positions (Live Map)")
    print("="*70)
    
    runner.log("Testing GET /api/hr/field-tracks/latest with RBAC...", "INFO")
    
    # Admin should get 200
    success, tracks_admin = runner.test(
        "GET field-tracks/latest as ADMIN (should 200)",
        "GET",
        "hr/field-tracks/latest",
        200,
        token=runner.admin_token,
        check_response=lambda r: (
            isinstance(r, list) and
            all(k in r[0] for k in ['employee_id', 'employee_name', 'lat', 'lon', 'accuracy', 'battery', 'ts', 'online']) if len(r) > 0 else True
        )
    )
    
    if success and tracks_admin:
        runner.log(f"  Found {len(tracks_admin)} field employees with positions", "INFO")
        if len(tracks_admin) > 0:
            sample = tracks_admin[0]
            runner.log(f"  Sample: {sample.get('employee_name')} - lat:{sample.get('lat')}, lon:{sample.get('lon')}, online:{sample.get('online')}, battery:{sample.get('battery')}%", "INFO")
    
    # Manager should get 200
    runner.test(
        "GET field-tracks/latest as MANAGER (should 200)",
        "GET",
        "hr/field-tracks/latest",
        200,
        token=runner.manager_token,
        check_response=lambda r: isinstance(r, list)
    )
    
    # Sales should get 403 (RBAC)
    runner.test(
        "GET field-tracks/latest as SALES (should 403 - RBAC)",
        "GET",
        "hr/field-tracks/latest",
        403,
        token=runner.sales_token
    )

    # ========== FIELD TRACKS - POST OWN POSITION ==========
    print("\n" + "="*70)
    print("PHASE 3: FIELD TRACKS - Sales can POST own position")
    print("="*70)
    
    runner.log("Testing POST /api/hr/field-tracks (sales posts own position)...", "INFO")
    
    success, pos_result = runner.test(
        "POST field-tracks as SALES (should 200)",
        "POST",
        "hr/field-tracks",
        200,
        data={"lat": -6.9175, "lon": 107.6191, "accuracy": 0},
        token=runner.sales_token,
        check_response=lambda r: (
            'employee_id' in r and
            'lat' in r and
            'lon' in r and
            abs(r['lat'] - (-6.9175)) < 0.001 and
            abs(r['lon'] - 107.6191) < 0.001
        )
    )
    
    if success:
        runner.log(f"  Sales posted position: lat={pos_result.get('lat')}, lon={pos_result.get('lon')} ✓", "PASS")

    # ========== VISITS - LIST & FILTERS ==========
    print("\n" + "="*70)
    print("PHASE 4: VISITS - List & Filters")
    print("="*70)
    
    runner.log("Testing GET /api/hr/visits (default today)...", "INFO")
    
    success, visits_today = runner.test(
        "GET hr/visits as ADMIN (default today)",
        "GET",
        "hr/visits",
        200,
        token=runner.admin_token,
        check_response=lambda r: isinstance(r, list)
    )
    
    if success:
        runner.log(f"  Found {len(visits_today)} visits today", "INFO")
    
    # Test with date range filter
    runner.log("\nTesting GET /api/hr/visits with date_from & date_to filters...", "INFO")
    
    success, visits_range = runner.test(
        "GET hr/visits with date range (2026-01-01 to 2026-12-31)",
        "GET",
        "hr/visits?date_from=2026-01-01&date_to=2026-12-31",
        200,
        token=runner.admin_token,
        check_response=lambda r: isinstance(r, list)
    )
    
    if success:
        runner.log(f"  Found {len(visits_range)} visits in 2026", "INFO")
    
    # Test manager access
    runner.test(
        "GET hr/visits as MANAGER (should 200)",
        "GET",
        "hr/visits",
        200,
        token=runner.manager_token,
        check_response=lambda r: isinstance(r, list)
    )
    
    # Test sales access (should 403)
    runner.test(
        "GET hr/visits as SALES (should 403 - RBAC)",
        "GET",
        "hr/visits",
        403,
        token=runner.sales_token
    )

    # ========== VISITS - SUMMARY (KPI) ==========
    print("\n" + "="*70)
    print("PHASE 5: VISITS - Summary/KPI")
    print("="*70)
    
    runner.log("Testing GET /api/hr/visits/summary?month=YYYY-MM...", "INFO")
    
    success, summary = runner.test(
        "GET hr/visits/summary (current month)",
        "GET",
        "hr/visits/summary",
        200,
        token=runner.admin_token,
        check_response=lambda r: (
            'month' in r and
            'totals' in r and
            'rows' in r and
            isinstance(r['totals'], dict) and
            'visits' in r['totals'] and
            'with_order' in r['totals'] and
            'sales' in r['totals'] and
            isinstance(r['rows'], list)
        )
    )
    
    if success and summary:
        totals = summary.get('totals', {})
        runner.log(f"  Month: {summary.get('month')}", "INFO")
        runner.log(f"  Totals: {totals.get('visits')} visits, {totals.get('with_order')} with order, {totals.get('sales')} sales", "INFO")
        runner.log(f"  Per-sales rows: {len(summary.get('rows', []))}", "INFO")
    
    # Test manager access
    runner.test(
        "GET hr/visits/summary as MANAGER (should 200)",
        "GET",
        "hr/visits/summary",
        200,
        token=runner.manager_token
    )

    # ========== VISITS - MY VISITS (ESS) ==========
    print("\n" + "="*70)
    print("PHASE 6: VISITS - My Visits (ESS for sales)")
    print("="*70)
    
    runner.log("Testing GET /api/hr/visits/me (sales ESS)...", "INFO")
    
    success, my_visits = runner.test(
        "GET hr/visits/me as SALES (should 200)",
        "GET",
        "hr/visits/me",
        200,
        token=runner.sales_token,
        check_response=lambda r: (
            'employee' in r and
            'ongoing' in r and
            'today' in r and
            'count_today' in r and
            isinstance(r['today'], list)
        )
    )
    
    if success and my_visits:
        emp = my_visits.get('employee', {})
        ongoing = my_visits.get('ongoing')
        today_count = my_visits.get('count_today', 0)
        runner.log(f"  Employee: {emp.get('name')} (ID: {emp.get('id')})", "INFO")
        runner.log(f"  Ongoing visit: {ongoing is not None}", "INFO")
        runner.log(f"  Today's visits: {today_count}", "INFO")

    # ========== VISITS - CHECK-IN ==========
    print("\n" + "="*70)
    print("PHASE 7: VISITS - Check-In (Business Rules)")
    print("="*70)
    
    runner.log("Testing POST /api/hr/visits/check-in (sales check-in)...", "INFO")
    
    # First, ensure no ongoing visit (if there is one from previous test, we'll handle it)
    # Try to check-in
    success, checkin_result = runner.test(
        "POST hr/visits/check-in as SALES (first check-in)",
        "POST",
        "hr/visits/check-in",
        200,
        data={
            "customer_name": "Customer QA Test",
            "lat": -6.9175,
            "lon": 107.6191,
            "notes": "QA test check-in"
        },
        token=runner.sales_token,
        check_response=lambda r: (
            'id' in r and
            r.get('status') == 'ongoing' and
            'check_in' in r and
            r.get('customer_name') == 'Customer QA Test'
        )
    )
    
    if success and checkin_result:
        runner.created_visit_id = checkin_result.get('id')
        runner.log(f"  Created visit ID: {runner.created_visit_id}", "INFO")
        runner.log(f"  Status: {checkin_result.get('status')}", "INFO")
        runner.log(f"  Customer: {checkin_result.get('customer_name')}", "INFO")
        
        # Now test business rule: second check-in should return 409
        runner.log("\nTesting business rule: second check-in while one is ongoing (should 409)...", "INFO")
        
        runner.test(
            "POST hr/visits/check-in (second check-in should 409)",
            "POST",
            "hr/visits/check-in",
            409,
            data={
                "customer_name": "Another Customer",
                "lat": -6.9175,
                "lon": 107.6191,
                "notes": "This should fail"
            },
            token=runner.sales_token
        )
    else:
        # If check-in failed, it might be because there's already an ongoing visit
        # Let's try to get the ongoing visit and check it out first
        runner.log("  First check-in failed (might have ongoing visit from previous test)", "WARN")
        
        # Get my visits to see if there's an ongoing one
        try:
            resp = requests.get(f"{BASE_URL}/hr/visits/me", 
                              headers={'Authorization': f'Bearer {runner.sales_token}'}, 
                              timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                ongoing = data.get('ongoing')
                if ongoing:
                    runner.created_visit_id = ongoing.get('id')
                    runner.log(f"  Found existing ongoing visit: {runner.created_visit_id}", "INFO")
        except:
            pass

    # ========== VISITS - CHECK-OUT ==========
    print("\n" + "="*70)
    print("PHASE 8: VISITS - Check-Out")
    print("="*70)
    
    if runner.created_visit_id:
        runner.log(f"Testing POST /api/hr/visits/{runner.created_visit_id}/check-out...", "INFO")
        
        success, checkout_result = runner.test(
            "POST hr/visits/{id}/check-out as SALES (should 200)",
            "POST",
            f"hr/visits/{runner.created_visit_id}/check-out",
            200,
            data={
                "lat": -6.9175,
                "lon": 107.6191,
                "outcome": "order",
                "linked_so_id": "SO-QA-TEST-1",
                "notes": "QA test check-out - closing"
            },
            token=runner.sales_token,
            check_response=lambda r: (
                r.get('status') == 'done' and
                r.get('outcome') == 'order' and
                'duration_min' in r and
                'check_out' in r
            )
        )
        
        if success and checkout_result:
            runner.log(f"  Visit checked out successfully", "PASS")
            runner.log(f"  Status: {checkout_result.get('status')}", "INFO")
            runner.log(f"  Outcome: {checkout_result.get('outcome')}", "INFO")
            runner.log(f"  Duration: {checkout_result.get('duration_min')} minutes", "INFO")
            runner.log(f"  Linked SO: {checkout_result.get('linked_so_id')}", "INFO")
        
        # Verify the visit now appears in "today" list as done
        runner.log("\nVerifying visit appears in today's list as 'done'...", "INFO")
        
        try:
            resp = requests.get(f"{BASE_URL}/hr/visits/me", 
                              headers={'Authorization': f'Bearer {runner.sales_token}'}, 
                              timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                today_visits = data.get('today', [])
                done_visit = next((v for v in today_visits if v.get('id') == runner.created_visit_id), None)
                if done_visit and done_visit.get('status') == 'done':
                    runner.log(f"  Visit found in today's list with status 'done' ✓", "PASS")
                    runner.tests_passed += 1
                    runner.tests_run += 1
                else:
                    runner.log(f"  Visit not found in today's list or status not 'done'", "FAIL")
                    runner.tests_failed += 1
                    runner.tests_run += 1
                    runner.failures.append("Visit not found in today's list after check-out")
        except Exception as e:
            runner.log(f"  Error verifying visit in today's list: {str(e)}", "WARN")
    else:
        runner.log("  No visit ID available for check-out test", "WARN")

    # ========== PRINT SUMMARY ==========
    runner.print_summary()
    
    return 0 if runner.tests_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
