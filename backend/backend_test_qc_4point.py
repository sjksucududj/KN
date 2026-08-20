#!/usr/bin/env python3
"""
Backend Test — Phase 6.2: QC 4-Point Inspection per Roll
==========================================================
Tests all backend APIs for the QC 4-Point Inspection feature:
  - GET /api/qc/grade-thresholds
  - GET /api/inbound/qc/queue
  - GET /api/inbound/qc/tasks/{task_id}/rolls
  - POST /api/inbound/rolls/{roll_id}/inspect
  - Permission tests (sales user should get 403)
  - Validation tests (invalid point_value)
  - Boundary tests (20 points -> A, 40 points -> B)
"""
import requests
import sys
import os
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = os.environ.get("BACKEND_URL", "https://po-pdf-sender.preview.emergentagent.com")
API = f"{BACKEND_URL}/api"

class QC4PointTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.admin_token = None
        self.sales_token = None
        self.task_id = None
        self.roll_id = None

    def log_pass(self, test_name):
        self.tests_passed += 1
        self.tests_run += 1
        print(f"✅ PASS: {test_name}")

    def log_fail(self, test_name, reason):
        self.tests_failed += 1
        self.tests_run += 1
        print(f"❌ FAIL: {test_name}")
        print(f"   Reason: {reason}")

    def login(self, email, password):
        """Login and return token"""
        try:
            response = requests.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                # Check if response is bare object (no envelope)
                if "token" in data:
                    return data["token"]
                else:
                    print(f"⚠️  Login response has envelope structure: {list(data.keys())}")
                    return None
            else:
                print(f"⚠️  Login failed: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            print(f"⚠️  Login error: {str(e)}")
            return None

    def test_login(self):
        """Test 1: Login as admin"""
        print("\n=== Test 1: Login as Admin ===")
        self.admin_token = self.login("admin@kainnusantara.id", "demo12345")
        if self.admin_token:
            self.log_pass("Admin login successful")
        else:
            self.log_fail("Admin login", "Failed to get admin token")
            return False
        return True

    def test_sales_login(self):
        """Test 2: Login as sales user (for permission test)"""
        print("\n=== Test 2: Login as Sales User ===")
        self.sales_token = self.login("sales@kainnusantara.id", "demo12345")
        if self.sales_token:
            self.log_pass("Sales user login successful")
        else:
            self.log_fail("Sales user login", "Failed to get sales token")
            return False
        return True

    def test_grade_thresholds(self):
        """Test 3: GET /api/qc/grade-thresholds"""
        print("\n=== Test 3: GET Grade Thresholds ===")
        try:
            response = requests.get(
                f"{API}/qc/grade-thresholds",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                # Check bare object (no envelope)
                if "a_max" in data and "b_max" in data:
                    if data["a_max"] == 20.0 and data["b_max"] == 40.0:
                        self.log_pass("Grade thresholds correct (a_max=20.0, b_max=40.0)")
                    else:
                        self.log_fail("Grade thresholds", f"Expected a_max=20.0, b_max=40.0, got {data}")
                else:
                    self.log_fail("Grade thresholds", f"Response has envelope or missing fields: {list(data.keys())}")
            else:
                self.log_fail("Grade thresholds", f"Status {response.status_code}: {response.text[:200]}")
        except Exception as e:
            self.log_fail("Grade thresholds", str(e))

    def test_qc_queue(self):
        """Test 4: GET /api/inbound/qc/queue"""
        print("\n=== Test 4: GET QC Queue ===")
        try:
            response = requests.get(
                f"{API}/inbound/qc/queue",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                # Check bare array (no envelope)
                if isinstance(data, list):
                    if len(data) > 0:
                        # Find qc_pending task
                        qc_tasks = [t for t in data if t.get("status") == "qc_pending"]
                        if qc_tasks:
                            self.task_id = qc_tasks[0]["id"]
                            self.log_pass(f"QC queue has {len(qc_tasks)} qc_pending task(s), task_id={self.task_id}")
                        else:
                            self.log_fail("QC queue", "No qc_pending tasks found")
                    else:
                        self.log_fail("QC queue", "Queue is empty")
                else:
                    self.log_fail("QC queue", f"Response is not bare array: {type(data)}")
            else:
                self.log_fail("QC queue", f"Status {response.status_code}: {response.text[:200]}")
        except Exception as e:
            self.log_fail("QC queue", str(e))

    def test_task_rolls(self):
        """Test 5: GET /api/inbound/qc/tasks/{task_id}/rolls"""
        print("\n=== Test 5: GET Task Rolls ===")
        if not self.task_id:
            self.log_fail("Task rolls", "No task_id available from previous test")
            return
        
        try:
            response = requests.get(
                f"{API}/inbound/qc/tasks/{self.task_id}/rolls",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                # Check bare array (no envelope)
                if isinstance(data, list):
                    if len(data) > 0:
                        roll = data[0]
                        self.roll_id = roll.get("id")
                        # Check required fields
                        required_fields = ["id", "roll_no", "sku", "gsm_standard", "width_standard", 
                                         "length_initial", "grade", "inspected"]
                        missing = [f for f in required_fields if f not in roll]
                        if not missing:
                            self.log_pass(f"Task rolls has {len(data)} roll(s) with all required fields, roll_id={self.roll_id}")
                        else:
                            self.log_fail("Task rolls", f"Missing fields: {missing}")
                    else:
                        self.log_fail("Task rolls", "No rolls found for task")
                else:
                    self.log_fail("Task rolls", f"Response is not bare array: {type(data)}")
            else:
                self.log_fail("Task rolls", f"Status {response.status_code}: {response.text[:200]}")
        except Exception as e:
            self.log_fail("Task rolls", str(e))

    def test_inspect_grade_a(self):
        """Test 6: POST inspect with 10 points -> Grade A"""
        print("\n=== Test 6: Inspect Roll - Grade A (10 points) ===")
        if not self.roll_id:
            self.log_fail("Inspect Grade A", "No roll_id available from previous test")
            return
        
        try:
            response = requests.post(
                f"{API}/inbound/rolls/{self.roll_id}/inspect",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                json={
                    "defects": [
                        {"point_value": 1, "count": 2},
                        {"point_value": 4, "count": 2}
                    ],
                    "gsm_actual": 145,
                    "width_actual": 115,
                    "note": "test"
                },
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                # Check bare object (no envelope)
                if "points" in data and "grade" in data:
                    if abs(data["points"] - 10.0) < 0.01 and data["grade"] == "A":
                        self.log_pass("Inspect Grade A: points=10, grade=A")
                    else:
                        self.log_fail("Inspect Grade A", f"Expected points=10, grade=A, got points={data.get('points')}, grade={data.get('grade')}")
                else:
                    self.log_fail("Inspect Grade A", f"Response missing fields or has envelope: {list(data.keys())}")
            else:
                self.log_fail("Inspect Grade A", f"Status {response.status_code}: {response.text[:200]}")
        except Exception as e:
            self.log_fail("Inspect Grade A", str(e))

    def test_inspect_grade_b(self):
        """Test 7: POST inspect with 30 points -> Grade B"""
        print("\n=== Test 7: Inspect Roll - Grade B (30 points) ===")
        if not self.roll_id:
            self.log_fail("Inspect Grade B", "No roll_id available")
            return
        
        try:
            response = requests.post(
                f"{API}/inbound/rolls/{self.roll_id}/inspect",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                json={
                    "defects": [{"point_value": 3, "count": 10}],
                    "gsm_actual": 145,
                    "width_actual": 115,
                    "note": "test"
                },
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                if abs(data.get("points", 0) - 30.0) < 0.01 and data.get("grade") == "B":
                    self.log_pass("Inspect Grade B: points=30, grade=B")
                else:
                    self.log_fail("Inspect Grade B", f"Expected points=30, grade=B, got points={data.get('points')}, grade={data.get('grade')}")
            else:
                self.log_fail("Inspect Grade B", f"Status {response.status_code}: {response.text[:200]}")
        except Exception as e:
            self.log_fail("Inspect Grade B", str(e))

    def test_inspect_grade_c(self):
        """Test 8: POST inspect with 48 points -> Grade C"""
        print("\n=== Test 8: Inspect Roll - Grade C (48 points) ===")
        if not self.roll_id:
            self.log_fail("Inspect Grade C", "No roll_id available")
            return
        
        try:
            response = requests.post(
                f"{API}/inbound/rolls/{self.roll_id}/inspect",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                json={
                    "defects": [{"point_value": 4, "count": 12}],
                    "gsm_actual": 145,
                    "width_actual": 115,
                    "note": "test"
                },
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                if abs(data.get("points", 0) - 48.0) < 0.01 and data.get("grade") == "C":
                    self.log_pass("Inspect Grade C: points=48, grade=C")
                else:
                    self.log_fail("Inspect Grade C", f"Expected points=48, grade=C, got points={data.get('points')}, grade={data.get('grade')}")
            else:
                self.log_fail("Inspect Grade C", f"Status {response.status_code}: {response.text[:200]}")
        except Exception as e:
            self.log_fail("Inspect Grade C", str(e))

    def test_boundary_20_points(self):
        """Test 9: Boundary test - 20 points -> Grade A"""
        print("\n=== Test 9: Boundary Test - 20 points -> Grade A ===")
        if not self.roll_id:
            self.log_fail("Boundary 20 points", "No roll_id available")
            return
        
        try:
            response = requests.post(
                f"{API}/inbound/rolls/{self.roll_id}/inspect",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                json={
                    "defects": [{"point_value": 4, "count": 5}],
                    "gsm_actual": 145,
                    "width_actual": 115,
                    "note": "boundary test"
                },
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                if abs(data.get("points", 0) - 20.0) < 0.01 and data.get("grade") == "A":
                    self.log_pass("Boundary 20 points: grade=A")
                else:
                    self.log_fail("Boundary 20 points", f"Expected points=20, grade=A, got points={data.get('points')}, grade={data.get('grade')}")
            else:
                self.log_fail("Boundary 20 points", f"Status {response.status_code}: {response.text[:200]}")
        except Exception as e:
            self.log_fail("Boundary 20 points", str(e))

    def test_boundary_40_points(self):
        """Test 10: Boundary test - 40 points -> Grade B"""
        print("\n=== Test 10: Boundary Test - 40 points -> Grade B ===")
        if not self.roll_id:
            self.log_fail("Boundary 40 points", "No roll_id available")
            return
        
        try:
            response = requests.post(
                f"{API}/inbound/rolls/{self.roll_id}/inspect",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                json={
                    "defects": [{"point_value": 4, "count": 10}],
                    "gsm_actual": 145,
                    "width_actual": 115,
                    "note": "boundary test"
                },
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                if abs(data.get("points", 0) - 40.0) < 0.01 and data.get("grade") == "B":
                    self.log_pass("Boundary 40 points: grade=B")
                else:
                    self.log_fail("Boundary 40 points", f"Expected points=40, grade=B, got points={data.get('points')}, grade={data.get('grade')}")
            else:
                self.log_fail("Boundary 40 points", f"Status {response.status_code}: {response.text[:200]}")
        except Exception as e:
            self.log_fail("Boundary 40 points", str(e))

    def test_invalid_point_value(self):
        """Test 11: Validation - invalid point_value (5) -> 400"""
        print("\n=== Test 11: Validation - Invalid point_value ===")
        if not self.roll_id:
            self.log_fail("Invalid point_value", "No roll_id available")
            return
        
        try:
            response = requests.post(
                f"{API}/inbound/rolls/{self.roll_id}/inspect",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                json={
                    "defects": [{"point_value": 5, "count": 1}],
                    "gsm_actual": 145,
                    "width_actual": 115,
                    "note": "invalid test"
                },
                timeout=30
            )
            if response.status_code == 400:
                self.log_pass("Invalid point_value: correctly returns 400")
            else:
                self.log_fail("Invalid point_value", f"Expected 400, got {response.status_code}")
        except Exception as e:
            self.log_fail("Invalid point_value", str(e))

    def test_sales_permission(self):
        """Test 12: Permission - sales user (view-only) should get 403"""
        print("\n=== Test 12: Permission Test - Sales User ===")
        if not self.sales_token:
            self.log_fail("Sales permission", "No sales token available")
            return
        if not self.roll_id:
            self.log_fail("Sales permission", "No roll_id available")
            return
        
        try:
            response = requests.post(
                f"{API}/inbound/rolls/{self.roll_id}/inspect",
                headers={"Authorization": f"Bearer {self.sales_token}"},
                json={
                    "defects": [{"point_value": 1, "count": 1}],
                    "gsm_actual": 145,
                    "width_actual": 115,
                    "note": "permission test"
                },
                timeout=30
            )
            if response.status_code == 403:
                self.log_pass("Sales permission: correctly returns 403 (forbidden)")
            else:
                self.log_fail("Sales permission", f"Expected 403, got {response.status_code}")
        except Exception as e:
            self.log_fail("Sales permission", str(e))

    def run_all_tests(self):
        """Run all tests in sequence"""
        print("=" * 70)
        print("QC 4-Point Inspection Backend Tests - Phase 6.2")
        print("=" * 70)
        
        # Login tests
        if not self.test_login():
            print("\n❌ Cannot proceed without admin login")
            return False
        
        self.test_sales_login()  # Continue even if sales login fails
        
        # API tests
        self.test_grade_thresholds()
        self.test_qc_queue()
        self.test_task_rolls()
        
        # Inspection tests
        self.test_inspect_grade_a()
        self.test_inspect_grade_b()
        self.test_inspect_grade_c()
        
        # Boundary tests
        self.test_boundary_20_points()
        self.test_boundary_40_points()
        
        # Validation tests
        self.test_invalid_point_value()
        
        # Permission tests
        self.test_sales_permission()
        
        # Summary
        print("\n" + "=" * 70)
        print(f"TEST SUMMARY: {self.tests_passed} PASSED | {self.tests_failed} FAILED | {self.tests_run} TOTAL")
        print("=" * 70)
        
        return self.tests_failed == 0

def main():
    tester = QC4PointTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
