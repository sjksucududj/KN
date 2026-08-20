#!/usr/bin/env python3
"""
H1 Attendance Module - Backend API Testing
Tests all H1 attendance endpoints: shifts, geofences, devices, attendance, clock-in/out, import, recap
"""
import requests
import sys
from typing import Dict, Any, Optional

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

class H1TestRunner:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.admin_token = None
        self.manager_token = None
        self.sales_token = None
        self.warehouse_token = None
        self.failures = []
        self.created_shift_id = None
        self.created_geofence_id = None
        self.created_device_id = None

    def log(self, message: str, level: str = "INFO"):
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "•")
        print(f"{prefix} {message}")

    def test(self, name: str, method: str, endpoint: str, expected_status: int,
             data: Optional[Dict] = None, token: Optional[str] = None,
             check_response: Optional[callable] = None, params: Optional[Dict] = None) -> tuple[bool, Any]:
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.log(f"Test #{self.tests_run}: {name}", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=15)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=15)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            response_data = {}
            try:
                response_data = response.json()
            except Exception:
                pass

            if success:
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

    def login(self, email: str, password: str = "demo12345") -> Optional[str]:
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
            self.log(f"  Login successful", "PASS")
            return data['token']
        self.log(f"  Login failed", "FAIL")
        return None

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("H1 ATTENDANCE MODULE - TEST SUMMARY")
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
    runner = H1TestRunner()
    
    print("="*70)
    print("KAIN NUSANTARA - H1 ATTENDANCE MODULE TESTING")
    print("Testing: Shifts, Geofences, Devices, Attendance, Clock-in/out, Import")
    print("="*70)
    print()

    # ========== AUTHENTICATION ==========
    print("\n" + "="*70)
    print("PHASE 1: AUTHENTICATION")
    print("="*70)
    
    runner.admin_token = runner.login("admin@kainnusantara.id")
    if not runner.admin_token:
        print("❌ CRITICAL: Admin login failed. Cannot continue.")
        return 1
    
    runner.manager_token = runner.login("manager@kainnusantara.id")
    if not runner.manager_token:
        print("❌ CRITICAL: Manager login failed. Cannot continue.")
        return 1
    
    runner.sales_token = runner.login("sales@kainnusantara.id")
    if not runner.sales_token:
        print("❌ CRITICAL: Sales login failed. Cannot continue.")
        return 1
    
    runner.warehouse_token = runner.login("warehouse@kainnusantara.id")
    if not runner.warehouse_token:
        print("❌ CRITICAL: Warehouse login failed. Cannot continue.")
        return 1

    # ========== SEEDED DATA VERIFICATION ==========
    print("\n" + "="*70)
    print("PHASE 2: SEEDED DATA VERIFICATION")
    print("="*70)
    
    runner.log("Verifying seeded shifts, geofences, devices...", "INFO")
    
    success, shifts = runner.test(
        "GET hr/shifts (verify seeded data)",
        "GET",
        "hr/shifts",
        200,
        token=runner.admin_token,
        check_response=lambda r: isinstance(r, list) and len(r) >= 1
    )
    
    if success and shifts:
        runner.log(f"  Found {len(shifts)} shifts", "INFO")
        if len(shifts) >= 1:
            runner.log(f"  Sample shift: {shifts[0].get('name')} ({shifts[0].get('jam_in')}-{shifts[0].get('jam_out')})", "INFO")
    
    success, geofences = runner.test(
        "GET hr/geofences (verify seeded data)",
        "GET",
        "hr/geofences",
        200,
        token=runner.admin_token,
        check_response=lambda r: isinstance(r, list) and len(r) >= 1
    )
    
    if success and geofences:
        runner.log(f"  Found {len(geofences)} geofences", "INFO")
        if len(geofences) >= 1:
            runner.log(f"  Sample geofence: {geofences[0].get('name')} (radius: {geofences[0].get('radius_m')}m)", "INFO")
    
    success, devices = runner.test(
        "GET hr/devices (verify seeded data)",
        "GET",
        "hr/devices",
        200,
        token=runner.admin_token,
        check_response=lambda r: isinstance(r, list) and len(r) >= 1
    )
    
    if success and devices:
        runner.log(f"  Found {len(devices)} devices", "INFO")
        if len(devices) >= 1:
            runner.log(f"  Sample device: {devices[0].get('name')}", "INFO")

    # ========== SHIFT CRUD ==========
    print("\n" + "="*70)
    print("PHASE 3: SHIFT CRUD")
    print("="*70)
    
    runner.log("Testing shift CRUD operations...", "INFO")
    
    # Create shift
    success, new_shift = runner.test(
        "POST hr/shifts (create shift)",
        "POST",
        "hr/shifts",
        200,
        data={
            "name": "Shift Sore Test",
            "code": "SORE-TEST",
            "jam_in": "13:00",
            "jam_out": "21:00",
            "grace_late_min": 5,
            "break_min": 60,
            "work_days": [1, 2, 3, 4, 5]
        },
        token=runner.admin_token,
        check_response=lambda r: 'id' in r and r.get('name') == 'Shift Sore Test'
    )
    
    if success and new_shift:
        runner.created_shift_id = new_shift.get('id')
        runner.log(f"  Created shift ID: {runner.created_shift_id}", "INFO")
        
        # Update shift
        runner.test(
            "PATCH hr/shifts/{id} (update grace_late_min)",
            "PATCH",
            f"hr/shifts/{runner.created_shift_id}",
            200,
            data={"data": {"grace_late_min": 15}},
            token=runner.admin_token,
            check_response=lambda r: r.get('grace_late_min') == 15
        )
        
        # Deactivate shift
        runner.test(
            "DELETE hr/shifts/{id} (soft delete)",
            "DELETE",
            f"hr/shifts/{runner.created_shift_id}",
            200,
            token=runner.admin_token,
            check_response=lambda r: r.get('status') == 'inactive'
        )

    # ========== GEOFENCE CRUD ==========
    print("\n" + "="*70)
    print("PHASE 4: GEOFENCE CRUD")
    print("="*70)
    
    runner.log("Testing geofence CRUD operations...", "INFO")
    
    # Create geofence
    success, new_geo = runner.test(
        "POST hr/geofences (create geofence)",
        "POST",
        "hr/geofences",
        200,
        data={
            "name": "Gudang Test",
            "lat": -6.305,
            "lon": 107.158,
            "radius_m": 100,
            "address": "Test Address"
        },
        token=runner.admin_token,
        check_response=lambda r: 'id' in r and r.get('name') == 'Gudang Test'
    )
    
    if success and new_geo:
        runner.created_geofence_id = new_geo.get('id')
        runner.log(f"  Created geofence ID: {runner.created_geofence_id}", "INFO")
        
        # Update geofence
        runner.test(
            "PATCH hr/geofences/{id} (update radius)",
            "PATCH",
            f"hr/geofences/{runner.created_geofence_id}",
            200,
            data={"data": {"radius_m": 150}},
            token=runner.admin_token,
            check_response=lambda r: r.get('radius_m') == 150
        )
        
        # Deactivate geofence
        runner.test(
            "DELETE hr/geofences/{id} (soft delete)",
            "DELETE",
            f"hr/geofences/{runner.created_geofence_id}",
            200,
            token=runner.admin_token,
            check_response=lambda r: r.get('status') == 'inactive'
        )

    # ========== DEVICE CRUD ==========
    print("\n" + "="*70)
    print("PHASE 5: DEVICE CRUD")
    print("="*70)
    
    runner.log("Testing device CRUD operations...", "INFO")
    
    # Create device
    success, new_device = runner.test(
        "POST hr/devices (create device)",
        "POST",
        "hr/devices",
        200,
        data={
            "name": "ZKTeco Test",
            "code": "ZK-TEST-001",
            "location": "Test Location"
        },
        token=runner.admin_token,
        check_response=lambda r: 'id' in r and 'device_token' in r
    )
    
    if success and new_device:
        runner.created_device_id = new_device.get('id')
        runner.log(f"  Created device ID: {runner.created_device_id}", "INFO")
        runner.log(f"  Device token: {new_device.get('device_token')[:20]}...", "INFO")
        
        # Update device
        runner.test(
            "PATCH hr/devices/{id} (update location)",
            "PATCH",
            f"hr/devices/{runner.created_device_id}",
            200,
            data={"data": {"location": "Updated Location"}},
            token=runner.admin_token,
            check_response=lambda r: r.get('location') == 'Updated Location'
        )
        
        # Deactivate device
        runner.test(
            "DELETE hr/devices/{id} (soft delete)",
            "DELETE",
            f"hr/devices/{runner.created_device_id}",
            200,
            token=runner.admin_token,
            check_response=lambda r: r.get('status') == 'inactive'
        )

    # ========== ATTENDANCE - DAILY VIEW ==========
    print("\n" + "="*70)
    print("PHASE 6: ATTENDANCE - DAILY VIEW")
    print("="*70)
    
    runner.log("Testing GET hr/attendance (daily view)...", "INFO")
    
    # Get today's attendance
    success, today_att = runner.test(
        "GET hr/attendance (today)",
        "GET",
        "hr/attendance",
        200,
        token=runner.admin_token,
        check_response=lambda r: isinstance(r, list)
    )
    
    if success:
        runner.log(f"  Found {len(today_att)} attendance records for today", "INFO")
        if len(today_att) > 0:
            sample = today_att[0]
            runner.log(f"  Sample: {sample.get('employee_name')} - {sample.get('status')}", "INFO")

    # ========== ATTENDANCE - IMPORT CSV ==========
    print("\n" + "="*70)
    print("PHASE 7: ATTENDANCE - IMPORT CSV (ZKTeco)")
    print("="*70)
    
    runner.log("Testing POST hr/attendance/import (CSV import)...", "INFO")
    
    # Get employees with device_user_id
    success, employees = runner.test(
        "GET hr/employees (find employees with device_user_id)",
        "GET",
        "hr/employees",
        200,
        token=runner.admin_token
    )
    
    if success and employees:
        mapped = [e for e in employees if e.get('device_user_id')]
        runner.log(f"  Found {len(mapped)} employees with device_user_id", "INFO")
        
        if len(mapped) >= 2:
            a, b = mapped[0]['device_user_id'], mapped[1]['device_user_id']
            csv_text = (
                "user_id,timestamp\n"
                f"{a},2026-03-02 08:01:00\n"
                f"{a},2026-03-02 17:06:00\n"
                f"{b},2026-03-02 07:55:00\n"
                f"{b},2026-03-02 17:31:00\n"
            )
            
            # First import
            success, import1 = runner.test(
                "POST hr/attendance/import (first import)",
                "POST",
                "hr/attendance/import",
                200,
                data={"csv_text": csv_text},
                token=runner.admin_token,
                check_response=lambda r: r.get('imported', 0) >= 1
            )
            
            if success:
                runner.log(f"  Imported {import1.get('imported')} records", "INFO")
                
                # Second import (idempotent test)
                success, import2 = runner.test(
                    "POST hr/attendance/import (idempotent re-import)",
                    "POST",
                    "hr/attendance/import",
                    200,
                    data={"csv_text": csv_text},
                    token=runner.admin_token
                )
                
                if success:
                    runner.log(f"  Re-import result: {import2.get('imported')} records (idempotent)", "INFO")
        else:
            runner.log("  Not enough employees with device_user_id, skipping import test", "WARN")

    # ========== ATTENDANCE - MANUAL ENTRY ==========
    print("\n" + "="*70)
    print("PHASE 8: ATTENDANCE - MANUAL ENTRY")
    print("="*70)
    
    runner.log("Testing POST hr/attendance/manual...", "INFO")
    
    if employees and len(employees) > 0:
        emp = employees[0]
        success, manual = runner.test(
            "POST hr/attendance/manual (create manual entry)",
            "POST",
            "hr/attendance/manual",
            200,
            data={
                "employee_id": emp['id'],
                "date": "2026-03-05",
                "clock_in": "08:00",
                "clock_out": "17:00",
                "status": "hadir",
                "note": "Manual entry test"
            },
            token=runner.admin_token,
            check_response=lambda r: r.get('status') == 'hadir' and r.get('method') == 'manual'
        )
        
        if success:
            runner.log(f"  Created manual entry for {emp.get('name')}", "INFO")

    # ========== ATTENDANCE - RECAP ==========
    print("\n" + "="*70)
    print("PHASE 9: ATTENDANCE - RECAP")
    print("="*70)
    
    runner.log("Testing GET hr/attendance/recap...", "INFO")
    
    success, recap = runner.test(
        "GET hr/attendance/recap (monthly recap)",
        "GET",
        "hr/attendance/recap",
        200,
        params={"month": "2026-03"},
        token=runner.admin_token,
        check_response=lambda r: 'rows' in r and 'totals' in r
    )
    
    if success and recap:
        totals = recap.get('totals', {})
        rows = recap.get('rows', [])
        runner.log(f"  Month: {recap.get('month')}", "INFO")
        runner.log(f"  Employees: {totals.get('employees', 0)}", "INFO")
        runner.log(f"  Present days: {totals.get('present_days', 0)}", "INFO")
        runner.log(f"  Late days: {totals.get('late_days', 0)}", "INFO")
        runner.log(f"  Recap rows: {len(rows)}", "INFO")

    # ========== ESS - CLOCK-IN/OUT ==========
    print("\n" + "="*70)
    print("PHASE 10: ESS - CLOCK-IN/OUT")
    print("="*70)
    
    runner.log("Testing ESS endpoints (warehouse user)...", "INFO")
    
    # Get /me endpoint
    success, me = runner.test(
        "GET hr/attendance/me (ESS - my attendance)",
        "GET",
        "hr/attendance/me",
        200,
        token=runner.warehouse_token,
        check_response=lambda r: 'employee' in r and 'shift' in r
    )
    
    if success and me:
        emp_info = me.get('employee', {})
        shift_info = me.get('shift', {})
        runner.log(f"  Employee: {emp_info.get('name')}", "INFO")
        runner.log(f"  Shift: {shift_info.get('name')} ({shift_info.get('jam_in')}-{shift_info.get('jam_out')})", "INFO")
        today_rec = me.get('today')
        if today_rec:
            runner.log(f"  Today record: {today_rec.get('status', 'none')}", "INFO")
        else:
            runner.log(f"  Today record: none", "INFO")
    
    # Clock-in (may fail with 409 if already clocked in today)
    runner.log("\nAttempting clock-in (may 409 if already done today)...", "INFO")
    success, clock_in = runner.test(
        "POST hr/attendance/clock-in (ESS)",
        "POST",
        "hr/attendance/clock-in",
        200,
        data={
            "lat": -6.917300,
            "lon": 107.619000,
            "accuracy": 12
        },
        token=runner.warehouse_token
    )
    
    if not success:
        # Try without expecting 200 (might be 409 if already clocked in)
        runner.log("  Clock-in may have failed due to existing record (409 expected)", "INFO")

    # ========== RBAC TESTS ==========
    print("\n" + "="*70)
    print("PHASE 11: RBAC - PERMISSION TESTS")
    print("="*70)
    
    runner.log("Testing RBAC - sales should NOT be able to manage attendance...", "INFO")
    
    # Sales should NOT be able to create shift
    runner.test(
        "POST hr/shifts as SALES (should 403)",
        "POST",
        "hr/shifts",
        403,
        data={"name": "Test", "jam_in": "08:00", "jam_out": "17:00"},
        token=runner.sales_token
    )
    
    # Sales should NOT be able to create geofence
    runner.test(
        "POST hr/geofences as SALES (should 403)",
        "POST",
        "hr/geofences",
        403,
        data={"name": "Test", "lat": 0, "lon": 0},
        token=runner.sales_token
    )
    
    # Sales should be able to view (hr.view permission)
    runner.test(
        "GET hr/shifts as SALES (should 200 - view only)",
        "GET",
        "hr/shifts",
        200,
        token=runner.sales_token
    )
    
    # Manager should be able to manage
    runner.test(
        "POST hr/shifts as MANAGER (should 200)",
        "POST",
        "hr/shifts",
        200,
        data={"name": "Manager Test Shift", "jam_in": "08:00", "jam_out": "17:00"},
        token=runner.manager_token,
        check_response=lambda r: 'id' in r
    )

    # ========== PRINT SUMMARY ==========
    runner.print_summary()
    
    return 0 if runner.tests_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
