#!/usr/bin/env python3
"""Backend API Test for PS-21 Features"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://grade-registry-qa.preview.emergentagent.com/api"

class PS21APITester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        self.session = requests.Session()

    def test(self, name, condition, detail=""):
        """Run a single test"""
        self.tests_run += 1
        status = "✅ PASS" if condition else "❌ FAIL"
        print(f"{status} - {name}")
        if detail:
            print(f"         {detail}")
        if condition:
            self.tests_passed += 1
        return condition

    def login(self, email, password):
        """Login and get token"""
        try:
            response = self.session.post(
                f"{BASE_URL}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token") or data.get("session_token")
                if self.token:
                    self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                    return True
            return False
        except Exception as e:
            print(f"Login error: {e}")
            return False

    def test_scheduler_jobs(self):
        """Test GET /api/scheduler/jobs - should return 12 jobs including 3 new ones"""
        print("\n=== Testing Scheduler Jobs API ===")
        
        try:
            response = self.session.get(f"{BASE_URL}/scheduler/jobs", timeout=30)
            self.test("GET /scheduler/jobs returns 200", response.status_code == 200,
                     f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                jobs = data.get("jobs", [])
                job_ids = [j.get("id") for j in jobs]
                
                self.test("Total jobs count is 12", len(jobs) == 12,
                         f"Found {len(jobs)} jobs")
                
                # Check for 3 new PS-21 jobs
                new_jobs = ["po_arrival", "backorder_ready", "ar_due_soon"]
                for job_id in new_jobs:
                    found = job_id in job_ids
                    self.test(f"Job '{job_id}' exists", found)
                
                # Check job details
                for job in jobs:
                    if job.get("id") in new_jobs:
                        has_label = bool(job.get("label"))
                        has_schedule = bool(job.get("schedule_label"))
                        self.test(f"Job '{job.get('id')}' has label and schedule",
                                 has_label and has_schedule,
                                 f"Label: {job.get('label')}, Schedule: {job.get('schedule_label')}")
        except Exception as e:
            self.test("Scheduler jobs API test", False, f"Error: {e}")

    def test_run_job(self, job_id):
        """Test POST /api/scheduler/jobs/{job_id}/run"""
        print(f"\n=== Testing Job Execution: {job_id} ===")
        
        try:
            # POST without body (should work per PS-21 fix)
            response = self.session.post(
                f"{BASE_URL}/scheduler/jobs/{job_id}/run",
                timeout=120
            )
            
            self.test(f"POST /scheduler/jobs/{job_id}/run returns 200",
                     response.status_code == 200,
                     f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                run_data = data.get("run", data)
                status = run_data.get("status")
                
                self.test(f"Job {job_id} execution status is 'success'",
                         status == "success",
                         f"Status: {status}, Created: {run_data.get('created')}, Detail: {run_data.get('detail', '')[:100]}")
        except Exception as e:
            self.test(f"Run job {job_id}", False, f"Error: {e}")

    def test_restock_endpoints(self):
        """Test restock-related endpoints"""
        print("\n=== Testing Restock Endpoints ===")
        
        try:
            # Get sales orders
            response = self.session.get(f"{BASE_URL}/sales-orders", timeout=30)
            self.test("GET /sales-orders returns 200", response.status_code == 200)
            
            if response.status_code == 200:
                orders = response.json()
                if isinstance(orders, dict):
                    orders = orders.get("items", [])
                
                # Find an order (preferably SO-0009)
                test_order = None
                for order in orders:
                    if order.get("number") == "SO-0009":
                        test_order = order
                        break
                
                if not test_order and orders:
                    test_order = orders[0]
                
                if test_order:
                    order_id = test_order.get("id")
                    print(f"Testing with order: {test_order.get('number')}")
                    
                    # Test GET /sales-orders/{id}/restock-state
                    response = self.session.get(
                        f"{BASE_URL}/sales-orders/{order_id}/restock-state",
                        timeout=30
                    )
                    
                    self.test("GET /sales-orders/{id}/restock-state returns 200",
                             response.status_code == 200,
                             f"Status: {response.status_code}")
                    
                    if response.status_code == 200:
                        state = response.json()
                        has_candidates = "candidates" in state
                        has_pendingan = "pendingan" in state
                        
                        self.test("Restock state has 'candidates' field", has_candidates)
                        self.test("Restock state has 'pendingan' field", has_pendingan)
                        
                        if has_candidates:
                            candidates = state.get("candidates", [])
                            print(f"         Found {len(candidates)} restock candidates")
                else:
                    print("         No orders found to test restock endpoints")
        except Exception as e:
            self.test("Restock endpoints test", False, f"Error: {e}")

    def test_notifications(self):
        """Test notifications endpoint"""
        print("\n=== Testing Notifications ===")
        
        try:
            response = self.session.get(f"{BASE_URL}/notifications", timeout=30)
            self.test("GET /notifications returns 200", response.status_code == 200)
            
            if response.status_code == 200:
                notifications = response.json()
                if isinstance(notifications, list):
                    # Check for PS-21 notification types
                    ps21_types = ["ar_due_soon", "po_arrival", "backorder_ready", "restock_request"]
                    found_types = set()
                    
                    for notif in notifications:
                        ntype = notif.get("type")
                        if ntype in ps21_types:
                            found_types.add(ntype)
                    
                    print(f"         Found PS-21 notification types: {sorted(found_types)}")
                    
                    if found_types:
                        self.test("PS-21 notifications exist", True,
                                 f"Types: {', '.join(sorted(found_types))}")
                    else:
                        print("         ⚠️  No PS-21 notifications found (may not have been generated yet)")
        except Exception as e:
            self.test("Notifications test", False, f"Error: {e}")

    def run_all_tests(self):
        """Run all PS-21 backend tests"""
        print("=" * 80)
        print("PS-21 Backend API Tests")
        print("=" * 80)
        
        # Login as admin
        print("\n--- Logging in as Admin ---")
        if not self.login("admin@kainnusantara.id", "demo12345"):
            print("❌ Failed to login as admin")
            return 1
        print("✅ Logged in as admin")
        
        # Run tests
        self.test_scheduler_jobs()
        self.test_run_job("ar_due_soon")
        self.test_notifications()
        
        # Login as sales for restock tests
        print("\n--- Logging in as Sales ---")
        if self.login("sales@kainnusantara.id", "demo12345"):
            print("✅ Logged in as sales")
            self.test_restock_endpoints()
        
        # Print summary
        print("\n" + "=" * 80)
        print(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        print("=" * 80)
        
        return 0 if self.tests_passed == self.tests_run else 1

if __name__ == "__main__":
    tester = PS21APITester()
    sys.exit(tester.run_all_tests())
