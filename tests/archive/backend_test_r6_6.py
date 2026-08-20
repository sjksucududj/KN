#!/usr/bin/env python3
"""
Backend API Testing for R6.6 Features:
- Daily Digest (Ringkasan Harian)
- Escalation (Eskalasi Bertingkat)
- Bell Notification Filters
Tests all new R6.6 endpoints with RBAC validation
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://job-notif.preview.emergentagent.com/api"

class R66APITester:
    def __init__(self):
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.failures = []

    def run_test(self, name, method, endpoint, expected_status, token=None, data=None, params=None):
        """Run a single API test"""
        url = f"{BASE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return True, response.json()
                except Exception:
                    return True, {}
            else:
                self.failures.append(f"{name}: Expected {expected_status}, got {response.status_code}")
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"   Response: {response.json()}")
                except Exception:
                    print(f"   Response: {response.text[:200]}")
                return False, {}

        except Exception as e:
            self.failures.append(f"{name}: {str(e)}")
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def login(self, role):
        """Login and get token for a role"""
        email = f"{role}@kainnusantara.id"
        password = "demo12345"
        
        success, response = self.run_test(
            f"Login as {role}",
            "POST",
            "/auth/login",
            200,
            data={"email": email, "password": password}
        )
        
        if success and 'token' in response:
            self.tokens[role] = response['token']
            return True
        return False

    def test_jobs_status(self):
        """Test that scheduler has 9 jobs now (7 alert + escalation_scan + daily_digest)"""
        print("\n" + "="*70)
        print("TESTING: Scheduler Jobs Status (9 jobs expected)")
        print("="*70)
        
        success, response = self.run_test(
            "GET /scheduler/jobs - should have 9 jobs",
            "GET",
            "/scheduler/jobs",
            200,
            token=self.tokens.get('admin')
        )
        
        if success:
            jobs = response.get('jobs', [])
            if len(jobs) == 9:
                print(f"✅ Correct: Found 9 jobs")
                self.tests_passed += 1
            else:
                print(f"❌ Failed: Expected 9 jobs, got {len(jobs)}")
                self.failures.append(f"Jobs count: Expected 9, got {len(jobs)}")
            
            # Check for escalation_scan job
            escalation_job = next((j for j in jobs if j.get('id') == 'escalation_scan'), None)
            if escalation_job:
                print(f"✅ Found escalation_scan job")
                if escalation_job.get('next_run'):
                    print(f"✅ escalation_scan has next_run: {escalation_job.get('next_run')}")
                else:
                    print(f"❌ escalation_scan missing next_run")
                    self.failures.append("escalation_scan missing next_run")
            else:
                print(f"❌ escalation_scan job not found")
                self.failures.append("escalation_scan job not found")
            
            # Check for daily_digest job
            digest_job = next((j for j in jobs if j.get('id') == 'daily_digest'), None)
            if digest_job:
                print(f"✅ Found daily_digest job")
                if digest_job.get('next_run'):
                    print(f"✅ daily_digest has next_run: {digest_job.get('next_run')}")
                else:
                    print(f"❌ daily_digest missing next_run")
                    self.failures.append("daily_digest missing next_run")
            else:
                print(f"❌ daily_digest job not found")
                self.failures.append("daily_digest job not found")
            
            # Check scheduler is running
            if response.get('running'):
                print(f"✅ Scheduler is running")
            else:
                print(f"❌ Scheduler is NOT running")
                self.failures.append("Scheduler not running")

    def test_settings_structure(self):
        """Test that settings include escalation config and delivery_modes"""
        print("\n" + "="*70)
        print("TESTING: Settings Structure (escalation + delivery_modes)")
        print("="*70)
        
        success, response = self.run_test(
            "GET /scheduler/settings - check structure",
            "GET",
            "/scheduler/settings",
            200,
            token=self.tokens.get('admin')
        )
        
        if success:
            # Check escalation config
            escalation = response.get('escalation', {})
            if escalation:
                print(f"✅ Found escalation config")
                required_fields = ['enabled', 'after_hours', 'min_severity', 'max_level']
                for field in required_fields:
                    if field in escalation:
                        print(f"✅ escalation.{field} = {escalation[field]}")
                    else:
                        print(f"❌ Missing escalation.{field}")
                        self.failures.append(f"Missing escalation.{field}")
            else:
                print(f"❌ escalation config not found")
                self.failures.append("escalation config not found")
            
            # Check delivery_modes
            delivery_modes = response.get('delivery_modes', [])
            if 'instant' in delivery_modes and 'digest' in delivery_modes:
                print(f"✅ delivery_modes includes instant and digest")
            else:
                print(f"❌ delivery_modes incorrect: {delivery_modes}")
                self.failures.append(f"delivery_modes incorrect: {delivery_modes}")
            
            # Check wa config has delivery_mode
            wa = response.get('wa', {})
            if 'delivery_mode' in wa:
                print(f"✅ wa.delivery_mode = {wa.get('delivery_mode')}")
            else:
                print(f"❌ wa.delivery_mode not found")
                self.failures.append("wa.delivery_mode not found")
            
            # Check credentials are masked
            if 'access_token' not in wa and 'fonnte_token' not in wa:
                print(f"✅ Credentials are masked (not in response)")
            else:
                print(f"❌ Credentials leaked in response")
                self.failures.append("Credentials leaked")
            
            if 'has_access_token' in wa or 'has_fonnte_token' in wa:
                print(f"✅ Has credential indicators present")

    def test_settings_validation(self):
        """Test validation of new R6.6 settings"""
        print("\n" + "="*70)
        print("TESTING: Settings Validation")
        print("="*70)
        
        # Test invalid delivery_mode
        self.run_test(
            "PUT /scheduler/settings - invalid delivery_mode (should be 400)",
            "PUT",
            "/scheduler/settings",
            400,
            token=self.tokens.get('admin'),
            data={"wa": {"delivery_mode": "harian"}}
        )
        
        # Test invalid after_hours (0)
        self.run_test(
            "PUT /scheduler/settings - after_hours=0 (should be 400)",
            "PUT",
            "/scheduler/settings",
            400,
            token=self.tokens.get('admin'),
            data={"escalation": {"after_hours": 0}}
        )
        
        # Test invalid after_hours (100)
        self.run_test(
            "PUT /scheduler/settings - after_hours=100 (should be 400)",
            "PUT",
            "/scheduler/settings",
            400,
            token=self.tokens.get('admin'),
            data={"escalation": {"after_hours": 100}}
        )
        
        # Test invalid max_level (0)
        self.run_test(
            "PUT /scheduler/settings - max_level=0 (should be 400)",
            "PUT",
            "/scheduler/settings",
            400,
            token=self.tokens.get('admin'),
            data={"escalation": {"max_level": 0}}
        )
        
        # Test invalid max_level (9)
        self.run_test(
            "PUT /scheduler/settings - max_level=9 (should be 400)",
            "PUT",
            "/scheduler/settings",
            400,
            token=self.tokens.get('admin'),
            data={"escalation": {"max_level": 9}}
        )
        
        # Test invalid min_severity
        self.run_test(
            "PUT /scheduler/settings - invalid min_severity (should be 400)",
            "PUT",
            "/scheduler/settings",
            400,
            token=self.tokens.get('admin'),
            data={"escalation": {"min_severity": "gawat"}}
        )
        
        # Test valid settings
        success, response = self.run_test(
            "PUT /scheduler/settings - valid escalation config",
            "PUT",
            "/scheduler/settings",
            200,
            token=self.tokens.get('admin'),
            data={"escalation": {"enabled": True, "after_hours": 8, "min_severity": "warning", "max_level": 2}}
        )
        
        if success:
            escalation = response.get('escalation', {})
            if escalation.get('after_hours') == 8:
                print(f"✅ Valid settings saved correctly")

    def test_digest_preview(self):
        """Test digest preview endpoint"""
        print("\n" + "="*70)
        print("TESTING: Digest Preview Endpoint")
        print("="*70)
        
        # Test admin can access
        success, response = self.run_test(
            "GET /scheduler/digest-preview?role=admin",
            "GET",
            "/scheduler/digest-preview",
            200,
            token=self.tokens.get('admin'),
            params={"role": "admin"}
        )
        
        if success:
            required_fields = ['groups', 'total', 'unread', 'text', 'delivery_mode', 'wa_enabled']
            for field in required_fields:
                if field in response:
                    print(f"✅ digest preview has {field}")
                else:
                    print(f"❌ Missing {field} in digest preview")
                    self.failures.append(f"Missing {field} in digest preview")
        
        # Test manager can access (view permission)
        self.run_test(
            "GET /scheduler/digest-preview?role=manager (manager token)",
            "GET",
            "/scheduler/digest-preview",
            200,
            token=self.tokens.get('manager'),
            params={"role": "manager"}
        )
        
        # Test sales cannot access (403)
        self.run_test(
            "GET /scheduler/digest-preview (sales - should be 403)",
            "GET",
            "/scheduler/digest-preview",
            403,
            token=self.tokens.get('sales'),
            params={"role": "sales"}
        )
        
        # Test warehouse cannot access (403)
        self.run_test(
            "GET /scheduler/digest-preview (warehouse - should be 403)",
            "GET",
            "/scheduler/digest-preview",
            403,
            token=self.tokens.get('warehouse'),
            params={"role": "warehouse"}
        )
        
        # Test invalid role (400)
        self.run_test(
            "GET /scheduler/digest-preview?role=invalid (should be 400)",
            "GET",
            "/scheduler/digest-preview",
            400,
            token=self.tokens.get('admin'),
            params={"role": "invalid"}
        )

    def test_summary_endpoint(self):
        """Test summary endpoint includes escalation stats and delivery_mode"""
        print("\n" + "="*70)
        print("TESTING: Summary Endpoint")
        print("="*70)
        
        success, response = self.run_test(
            "GET /scheduler/summary",
            "GET",
            "/scheduler/summary",
            200,
            token=self.tokens.get('admin')
        )
        
        if success:
            # Check escalation stats
            escalation = response.get('escalation', {})
            if escalation:
                print(f"✅ Found escalation stats")
                stats_fields = ['today', 'open', 'pending_next_scan', 'enabled', 'after_hours', 'min_severity', 'max_level']
                for field in stats_fields:
                    if field in escalation:
                        print(f"✅ escalation.{field} = {escalation[field]}")
                    else:
                        print(f"❌ Missing escalation.{field}")
                        self.failures.append(f"Missing escalation.{field}")
            else:
                print(f"❌ escalation stats not found")
                self.failures.append("escalation stats not found")
            
            # Check delivery_mode
            if 'delivery_mode' in response:
                print(f"✅ delivery_mode = {response.get('delivery_mode')}")
            else:
                print(f"❌ delivery_mode not found in summary")
                self.failures.append("delivery_mode not found in summary")
            
            # Check jobs_total is 9
            if response.get('jobs_total') == 9:
                print(f"✅ jobs_total = 9")
            else:
                print(f"❌ jobs_total = {response.get('jobs_total')} (expected 9)")
                self.failures.append(f"jobs_total incorrect: {response.get('jobs_total')}")

    def test_rbac_escalation(self):
        """Test RBAC for escalation settings"""
        print("\n" + "="*70)
        print("TESTING: RBAC for Escalation Settings")
        print("="*70)
        
        # Manager cannot configure escalation (403)
        self.run_test(
            "PUT /scheduler/settings (manager - escalation - should be 403)",
            "PUT",
            "/scheduler/settings",
            403,
            token=self.tokens.get('manager'),
            data={"escalation": {"after_hours": 6}}
        )
        
        # Manager cannot configure wa delivery_mode (403)
        self.run_test(
            "PUT /scheduler/settings (manager - wa - should be 403)",
            "PUT",
            "/scheduler/settings",
            403,
            token=self.tokens.get('manager'),
            data={"wa": {"delivery_mode": "instant"}}
        )
        
        # Sales cannot access scheduler at all (403)
        self.run_test(
            "GET /scheduler/settings (sales - should be 403)",
            "GET",
            "/scheduler/settings",
            403,
            token=self.tokens.get('sales')
        )
        
        # Warehouse cannot access scheduler at all (403)
        self.run_test(
            "GET /scheduler/settings (warehouse - should be 403)",
            "GET",
            "/scheduler/settings",
            403,
            token=self.tokens.get('warehouse')
        )

    def test_job_execution(self):
        """Test running escalation_scan and daily_digest jobs"""
        print("\n" + "="*70)
        print("TESTING: Job Execution (escalation_scan & daily_digest)")
        print("="*70)
        
        # Run escalation_scan
        success, response = self.run_test(
            "POST /scheduler/jobs/escalation_scan/run",
            "POST",
            "/scheduler/jobs/escalation_scan/run",
            200,
            token=self.tokens.get('admin'),
            data={}
        )
        
        if success:
            if response.get('status') == 'success':
                print(f"✅ escalation_scan executed successfully")
                print(f"   Created: {response.get('created')}, Scanned: {response.get('scanned')}")
            else:
                print(f"❌ escalation_scan failed: {response.get('error')}")
                self.failures.append(f"escalation_scan failed: {response.get('error')}")
        
        # Run daily_digest
        success, response = self.run_test(
            "POST /scheduler/jobs/daily_digest/run",
            "POST",
            "/scheduler/jobs/daily_digest/run",
            200,
            token=self.tokens.get('admin'),
            data={}
        )
        
        if success:
            if response.get('status') == 'success':
                print(f"✅ daily_digest executed successfully")
                print(f"   Created: {response.get('created')}, Scanned: {response.get('scanned')}")
            else:
                print(f"❌ daily_digest failed: {response.get('error')}")
                self.failures.append(f"daily_digest failed: {response.get('error')}")
        
        # Test idempotency - run daily_digest again
        success, response = self.run_test(
            "POST /scheduler/jobs/daily_digest/run (2nd time - should be idempotent)",
            "POST",
            "/scheduler/jobs/daily_digest/run",
            200,
            token=self.tokens.get('admin'),
            data={}
        )
        
        if success:
            if response.get('created') == 0:
                print(f"✅ daily_digest is idempotent (created=0 on 2nd run)")
            else:
                print(f"⚠️  daily_digest created {response.get('created')} on 2nd run (may not be same day)")

    def test_notifications_structure(self):
        """Test that notifications have required fields for filtering"""
        print("\n" + "="*70)
        print("TESTING: Notifications Structure (for bell filters)")
        print("="*70)
        
        success, response = self.run_test(
            "GET /notifications",
            "GET",
            "/notifications",
            200,
            token=self.tokens.get('admin')
        )
        
        if success and response:
            notifications = response if isinstance(response, list) else []
            if notifications:
                sample = notifications[0]
                required_fields = ['id', 'type', 'severity', 'title', 'body', 'read', 'created_at']
                for field in required_fields:
                    if field in sample:
                        print(f"✅ Notification has {field}")
                    else:
                        print(f"❌ Missing {field} in notification")
                        self.failures.append(f"Missing {field} in notification")
                
                # Check for escalation notifications
                escalation_notifs = [n for n in notifications if n.get('type') == 'escalation']
                if escalation_notifs:
                    print(f"✅ Found {len(escalation_notifs)} escalation notifications")
                    sample_esc = escalation_notifs[0]
                    if sample_esc.get('severity') == 'critical':
                        print(f"✅ Escalation notification has severity=critical")
                    if 'ESKALASI' in sample_esc.get('title', ''):
                        print(f"✅ Escalation notification title has ESKALASI marker")
                else:
                    print(f"ℹ️  No escalation notifications found (may be normal if none triggered)")
            else:
                print(f"ℹ️  No notifications found")

def main():
    tester = R66APITester()
    
    print("="*70)
    print("R6.6 BACKEND API TESTING")
    print("Daily Digest + Escalation + Bell Filters")
    print("="*70)
    
    # Login all roles
    print("\n" + "="*70)
    print("LOGGING IN")
    print("="*70)
    
    roles = ['admin', 'manager', 'sales', 'warehouse']
    for role in roles:
        if not tester.login(role):
            print(f"❌ Failed to login as {role}")
            return 1
    
    # Run all tests
    tester.test_jobs_status()
    tester.test_settings_structure()
    tester.test_settings_validation()
    tester.test_digest_preview()
    tester.test_summary_endpoint()
    tester.test_rbac_escalation()
    tester.test_job_execution()
    tester.test_notifications_structure()
    
    # Print results
    print("\n" + "="*70)
    print(f"RESULTS: {tester.tests_passed}/{tester.tests_run} tests passed")
    print("="*70)
    
    if tester.failures:
        print("\n❌ FAILURES:")
        for failure in tester.failures:
            print(f"  - {failure}")
        return 1
    else:
        print("\n✅ ALL TESTS PASSED!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
