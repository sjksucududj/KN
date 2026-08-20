#!/usr/bin/env python3
"""
Backend API Test — FASE H6 (HR Analytics Dashboard / BI SDM)
=============================================================
Testing iteration_90 fixes:
1. FIX-1: Default period should be '2026-06' (latest payroll period WITH attendance)
2. US3: Manager role has hr.view permission (GET /hr/analytics/summary -> 200)
3. US4: RBAC checks (sales -> 403, manager -> 200, admin -> 200)
4. US2: Period switching works correctly
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


class HRAnalyticsTester:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.manager_token = None
        self.sales_token = None
        
    def login(self, email, password):
        """Login and return token"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login {email} failed: {r.status_code} {r.text[:100]}")
                return None
            data = r.json()
            token = data.get("token")
            if not token:
                bad(f"Login {email} response missing token")
                return None
            ok(f"Login {email}")
            return token
        except Exception as e:
            bad(f"Login {email} exception: {e}")
            return None
    
    def test_us4_rbac(self):
        """TEST US4: Backend RBAC checks"""
        info("\n=== TEST US4: Backend RBAC ===")
        
        # Login all users
        self.admin_token = self.login("admin@kainnusantara.id", "demo12345")
        self.manager_token = self.login("manager@kainnusantara.id", "demo12345")
        self.sales_token = self.login("sales@kainnusantara.id", "demo12345")
        
        if not all([self.admin_token, self.manager_token, self.sales_token]):
            bad("US4: Failed to login all users")
            return False
        
        # Test sales user (should get 403)
        try:
            r = requests.get(
                f"{API}/hr/analytics/summary",
                headers={"Authorization": f"Bearer {self.sales_token}"},
                timeout=30
            )
            if r.status_code == 403:
                ok("US4: Sales user GET /hr/analytics/summary -> 403 (correct)")
            else:
                bad(f"US4: Sales user expected 403, got {r.status_code}")
        except Exception as e:
            bad(f"US4: Sales test exception: {e}")
        
        # Test manager user (should get 200)
        try:
            r = requests.get(
                f"{API}/hr/analytics/summary",
                headers={"Authorization": f"Bearer {self.manager_token}"},
                timeout=30
            )
            if r.status_code == 200:
                ok("US4: Manager user GET /hr/analytics/summary -> 200 (correct)")
                data = r.json()
                period = data.get("period")
                info(f"US4: Manager response period = {period}")
            else:
                bad(f"US4: Manager user expected 200, got {r.status_code}")
        except Exception as e:
            bad(f"US4: Manager test exception: {e}")
        
        # Test admin user with entity_id=all and NO period param (should default to 2026-06)
        try:
            r = requests.get(
                f"{API}/hr/analytics/summary",
                params={"entity_id": "all"},
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=30
            )
            if r.status_code == 200:
                ok("US4: Admin user GET /hr/analytics/summary?entity_id=all -> 200")
                data = r.json()
                period = data.get("period")
                
                # FIX-1: Check default period is 2026-06
                if period == "2026-06":
                    ok("FIX-1: Default period is '2026-06' (latest payroll WITH attendance)")
                else:
                    bad(f"FIX-1: Expected default period '2026-06', got '{period}'")
                
                # Check attendance data is present (not 0%)
                attendance = data.get("attendance", {})
                att_rate = attendance.get("attendance_rate", 0)
                if att_rate > 0:
                    ok(f"FIX-1: Attendance rate = {att_rate}% (dashboard has data on initial load)")
                else:
                    bad(f"FIX-1: Attendance rate = {att_rate}% (dashboard appears empty)")
                
                # Check payroll data is present
                payroll = data.get("payroll", {})
                net = payroll.get("net", 0)
                if net > 0:
                    ok(f"FIX-1: Payroll net = Rp {net:,.0f} (data present)")
                else:
                    bad(f"FIX-1: Payroll net = {net} (no payroll data)")
                
            else:
                bad(f"US4: Admin user expected 200, got {r.status_code}")
        except Exception as e:
            bad(f"US4: Admin test exception: {e}")
        
        return True
    
    def test_us2_period_switch(self):
        """TEST US2: Period switching"""
        info("\n=== TEST US2: Period Switching ===")
        
        if not self.admin_token:
            bad("US2: No admin token available")
            return False
        
        # Test period 2026-07 (should have overtime data ~4.5 hours)
        try:
            r = requests.get(
                f"{API}/hr/analytics/summary",
                params={"entity_id": "all", "period": "2026-07"},
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                period = data.get("period")
                if period == "2026-07":
                    ok("US2: Period switch to 2026-07 successful")
                else:
                    bad(f"US2: Expected period '2026-07', got '{period}'")
                
                # Check overtime trend for 2026-07
                ot_trend = data.get("overtime_trend", [])
                ot_2026_07 = next((o for o in ot_trend if o.get("period") == "2026-07"), None)
                if ot_2026_07:
                    hours = ot_2026_07.get("hours", 0)
                    if 4.0 <= hours <= 5.0:
                        ok(f"US2: Tren Lembur 2026-07 shows {hours} jam (expected ~4.5)")
                    else:
                        info(f"US2: Tren Lembur 2026-07 shows {hours} jam (expected ~4.5)")
                else:
                    info("US2: No overtime data for 2026-07 in trend")
            else:
                bad(f"US2: Period 2026-07 request failed: {r.status_code}")
        except Exception as e:
            bad(f"US2: Period 2026-07 test exception: {e}")
        
        # Test period 2026-08 (should have 0% attendance, no attendance data)
        try:
            r = requests.get(
                f"{API}/hr/analytics/summary",
                params={"entity_id": "all", "period": "2026-08"},
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                period = data.get("period")
                if period == "2026-08":
                    ok("US2: Period switch to 2026-08 successful")
                else:
                    bad(f"US2: Expected period '2026-08', got '{period}'")
                
                # Check attendance is 0% (no attendance data)
                attendance = data.get("attendance", {})
                att_rate = attendance.get("attendance_rate", 0)
                if att_rate == 0:
                    ok("US2: Attendance rate 2026-08 = 0% (no attendance data, expected)")
                else:
                    bad(f"US2: Expected attendance rate 0%, got {att_rate}%")
            else:
                bad(f"US2: Period 2026-08 request failed: {r.status_code}")
        except Exception as e:
            bad(f"US2: Period 2026-08 test exception: {e}")
        
        # Test switch back to 2026-06 (should have full data)
        try:
            r = requests.get(
                f"{API}/hr/analytics/summary",
                params={"entity_id": "all", "period": "2026-06"},
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                period = data.get("period")
                if period == "2026-06":
                    ok("US2: Period switch back to 2026-06 successful")
                else:
                    bad(f"US2: Expected period '2026-06', got '{period}'")
                
                # Check full data returns
                attendance = data.get("attendance", {})
                att_rate = attendance.get("attendance_rate", 0)
                if att_rate == 100.0:
                    ok(f"US2: Attendance rate 2026-06 = {att_rate}% (full data returns)")
                else:
                    info(f"US2: Attendance rate 2026-06 = {att_rate}% (expected 100%)")
            else:
                bad(f"US2: Period 2026-06 request failed: {r.status_code}")
        except Exception as e:
            bad(f"US2: Period 2026-06 test exception: {e}")
        
        return True
    
    def run_all_tests(self):
        """Run all backend tests"""
        print("\n" + "="*70)
        print("  BACKEND API TEST — FASE H6 (HR Analytics Dashboard / BI SDM)")
        print("  Testing iteration_90 fixes")
        print("="*70)
        
        # Test US4 RBAC (includes FIX-1 default period check)
        self.test_us4_rbac()
        
        # Test US2 period switching
        self.test_us2_period_switch()
        
        return True


def main():
    tester = HRAnalyticsTester()
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
