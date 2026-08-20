"""
Backend Testing for Kain Nusantara FASE H5
Tests KPI Design, Design Gallery, AI Integrations, and RBAC
"""
import requests
import sys
import io
from typing import Dict, Any, Optional

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

class H5TestRunner:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.admin_token = None
        self.manager_token = None
        self.sales_token = None
        self.failures = []
        self.kpi_id = None
        self.gallery_id = None
        self.file_id = None

    def log(self, message: str, level: str = "INFO"):
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "•")
        print(f"{prefix} {message}")

    def test(self, name: str, method: str, endpoint: str, expected_status: int,
             data: Optional[Dict] = None, token: Optional[str] = None,
             check_response: Optional[callable] = None, files=None) -> tuple[bool, Any]:
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}/{endpoint}"
        headers = {}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        # Only set Content-Type for non-file uploads
        if not files:
            headers['Content-Type'] = 'application/json'

        self.log(f"Test #{self.tests_run}: {name}", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                if files:
                    response = requests.post(url, files=files, headers=headers, timeout=15)
                else:
                    response = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=15)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=15)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            response_data = {}
            try:
                response_data = response.json()
            except:
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
            self.log(f"  Token obtained for {email}", "PASS")
            return data['token']
        return None

    def test_kpi_crud(self):
        """Test KPI CRUD operations"""
        self.log("\n=== Testing KPI Design (US1) ===", "INFO")
        
        # Get employees list first
        success, emp_data = self.test(
            "Get employees list",
            "GET",
            "hr/employees",
            200,
            token=self.admin_token
        )
        
        if not success or not emp_data:
            self.log("Cannot proceed with KPI tests - no employees", "FAIL")
            return
        
        employee_id = emp_data[0]['id'] if emp_data else None
        if not employee_id:
            self.log("No employee found for KPI test", "FAIL")
            return
        
        # Create KPI
        success, kpi_data = self.test(
            "Create KPI (admin)",
            "POST",
            "hr/kpi",
            200,
            data={
                "employee_id": employee_id,
                "period": "2026-07",
                "metric": "Jumlah Desain",
                "target": 10,
                "actual": 8,
                "weight": 1,
                "note": "Test KPI"
            },
            token=self.admin_token,
            check_response=lambda r: r.get('score') == 80.0  # 8/10 * 100 = 80
        )
        
        if success:
            self.kpi_id = kpi_data.get('id')
            self.log(f"  KPI created with ID: {self.kpi_id}, auto-score: {kpi_data.get('score')}", "INFO")
        
        # List KPIs
        self.test(
            "List KPIs (admin)",
            "GET",
            "hr/kpi?period=2026-07",
            200,
            token=self.admin_token,
            check_response=lambda r: isinstance(r, list) and len(r) > 0
        )
        
        # Update KPI (change actual to 12, score should become 120)
        if self.kpi_id:
            success, updated = self.test(
                "Update KPI actual to 12 (score should be 120)",
                "PUT",
                f"hr/kpi/{self.kpi_id}",
                200,
                data={"actual": 12},
                token=self.admin_token,
                check_response=lambda r: r.get('score') == 120.0  # 12/10 * 100 = 120
            )
            if success:
                self.log(f"  Updated score: {updated.get('score')}", "INFO")
        
        # Delete KPI
        if self.kpi_id:
            self.test(
                "Delete KPI",
                "DELETE",
                f"hr/kpi/{self.kpi_id}",
                200,
                token=self.admin_token,
                check_response=lambda r: r.get('deleted') == True
            )

    def test_ess_kpi(self):
        """Test ESS KPI endpoint (US2)"""
        self.log("\n=== Testing ESS KPI Saya (US2) ===", "INFO")
        
        # Admin should have linked employee
        self.test(
            "Get my KPI (admin)",
            "GET",
            "hr/kpi/me",
            200,
            token=self.admin_token,
            check_response=lambda r: 'employee' in r and 'latest' in r
        )
        
        # Sales should also work (all roles with employee)
        self.test(
            "Get my KPI (sales)",
            "GET",
            "hr/kpi/me",
            200,
            token=self.sales_token
        )

    def test_design_gallery_crud(self):
        """Test Design Gallery CRUD (US3)"""
        self.log("\n=== Testing Design Gallery CRUD (US3) ===", "INFO")
        
        # List galleries (should have 2 seeded)
        success, galleries = self.test(
            "List design galleries",
            "GET",
            "design-gallery",
            200,
            token=self.admin_token,
            check_response=lambda r: isinstance(r, list)
        )
        if success:
            self.log(f"  Found {len(galleries)} galleries", "INFO")
        
        # Create new gallery
        success, gallery_data = self.test(
            "Create design gallery",
            "POST",
            "design-gallery",
            200,
            data={
                "title": "Motif Uji",
                "story": "Cerita motif uji untuk testing",
                "tags": ["batik", "uji"],
                "product_id": ""
            },
            token=self.admin_token,
            check_response=lambda r: r.get('title') == 'Motif Uji'
        )
        
        if success:
            self.gallery_id = gallery_data.get('id')
            self.log(f"  Gallery created with ID: {self.gallery_id}", "INFO")
        
        # Get gallery detail
        if self.gallery_id:
            self.test(
                "Get gallery detail",
                "GET",
                f"design-gallery/{self.gallery_id}",
                200,
                token=self.admin_token,
                check_response=lambda r: r.get('id') == self.gallery_id
            )

    def test_gallery_file_upload(self):
        """Test gallery file upload (US3)"""
        self.log("\n=== Testing Gallery File Upload (US3) ===", "INFO")
        
        if not self.gallery_id:
            self.log("No gallery ID, skipping file upload test", "WARN")
            return
        
        # Create a small test image (1x1 PNG)
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        
        files = {'file': ('test_motif.png', io.BytesIO(png_data), 'image/png')}
        
        success, file_data = self.test(
            "Upload image to gallery",
            "POST",
            f"design-gallery/{self.gallery_id}/files",
            200,
            token=self.admin_token,
            files=files,
            check_response=lambda r: 'id' in r and r.get('filename') == 'test_motif.png'
        )
        
        if success:
            self.file_id = file_data.get('id')
            self.log(f"  File uploaded with ID: {self.file_id}", "INFO")
        
        # Get file (should return image blob)
        if self.file_id:
            url = f"{BASE_URL}/design-gallery/{self.gallery_id}/files/{self.file_id}"
            headers = {'Authorization': f'Bearer {self.admin_token}'}
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200 and response.headers.get('content-type', '').startswith('image/'):
                    self.tests_run += 1
                    self.tests_passed += 1
                    self.log(f"Test #{self.tests_run}: Get gallery file", "INFO")
                    self.log(f"  PASSED (status: 200, content-type: {response.headers.get('content-type')})", "PASS")
                else:
                    self.tests_run += 1
                    self.tests_failed += 1
                    self.log(f"Test #{self.tests_run}: Get gallery file", "INFO")
                    self.log(f"  FAILED - status: {response.status_code}", "FAIL")
                    self.failures.append(f"Get gallery file: Expected 200 with image, got {response.status_code}")
            except Exception as e:
                self.tests_run += 1
                self.tests_failed += 1
                self.log(f"Test #{self.tests_run}: Get gallery file", "INFO")
                self.log(f"  FAILED - Error: {str(e)}", "FAIL")
                self.failures.append(f"Get gallery file: {str(e)}")
        
        # Delete file
        if self.file_id:
            self.test(
                "Delete gallery file",
                "DELETE",
                f"design-gallery/{self.gallery_id}/files/{self.file_id}",
                200,
                token=self.admin_token,
                check_response=lambda r: r.get('deleted') == True
            )

    def test_ai_autotag_graceful(self):
        """Test AI auto-tag graceful degradation (US4)"""
        self.log("\n=== Testing AI Auto-tag Graceful (US4) ===", "INFO")
        
        if not self.gallery_id:
            self.log("No gallery ID, skipping autotag test", "WARN")
            return
        
        # Re-upload a file for autotag test
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        files = {'file': ('autotag_test.png', io.BytesIO(png_data), 'image/png')}
        
        success, _ = self.test(
            "Upload image for autotag test",
            "POST",
            f"design-gallery/{self.gallery_id}/files",
            200,
            token=self.admin_token,
            files=files
        )
        
        if not success:
            self.log("Cannot upload file for autotag test", "WARN")
            return
        
        # Trigger autotag (should return enabled:false since no API key)
        self.test(
            "Trigger AI autotag (should be gracefully disabled)",
            "POST",
            f"design-gallery/{self.gallery_id}/autotag",
            200,
            token=self.admin_token,
            check_response=lambda r: r.get('enabled') == False  # Expected: AI inactive
        )

    def test_integrations_settings(self):
        """Test Integrations settings (US5)"""
        self.log("\n=== Testing Integrations Settings (US5) ===", "INFO")
        
        # Get integrations (admin only)
        success, config = self.test(
            "Get integrations config (admin)",
            "GET",
            "admin/integrations",
            200,
            token=self.admin_token,
            check_response=lambda r: 'anthropic' in r and 'has_key' in r.get('anthropic', {})
        )
        
        if success:
            has_key = config.get('anthropic', {}).get('has_key')
            self.log(f"  Current has_key status: {has_key}", "INFO")
            # Verify key is NOT returned in plaintext
            if 'api_key' in config.get('anthropic', {}):
                self.log("  SECURITY ISSUE: api_key returned in GET response!", "FAIL")
                self.failures.append("Integrations GET: api_key leaked in response")
                self.tests_failed += 1
        
        # Update integrations (set dummy key)
        success, updated = self.test(
            "Update integrations (set dummy key)",
            "PUT",
            "admin/integrations",
            200,
            data={
                "anthropic_api_key": "sk-ant-test-dummy-key-12345",
                "anthropic_model": "claude-sonnet-4-6",
                "anthropic_enabled": True
            },
            token=self.admin_token,
            check_response=lambda r: r.get('anthropic', {}).get('has_key') == True
        )
        
        if success:
            self.log(f"  Key set, has_key: {updated.get('anthropic', {}).get('has_key')}", "INFO")
            # Verify key is NOT returned in plaintext
            if 'api_key' in updated.get('anthropic', {}):
                self.log("  SECURITY ISSUE: api_key returned in PUT response!", "FAIL")
                self.failures.append("Integrations PUT: api_key leaked in response")
                self.tests_failed += 1
        
        # Clear key
        self.test(
            "Clear integrations key",
            "PUT",
            "admin/integrations",
            200,
            data={"anthropic_clear_key": True},
            token=self.admin_token,
            check_response=lambda r: r.get('anthropic', {}).get('has_key') == False
        )

    def test_rbac(self):
        """Test RBAC restrictions (US6)"""
        self.log("\n=== Testing RBAC (US6) ===", "INFO")
        
        # Sales should NOT access KPI list
        self.test(
            "Sales GET /hr/kpi (should be 403)",
            "GET",
            "hr/kpi",
            403,
            token=self.sales_token
        )
        
        # Sales SHOULD access /hr/kpi/me
        self.test(
            "Sales GET /hr/kpi/me (should be 200)",
            "GET",
            "hr/kpi/me",
            200,
            token=self.sales_token
        )
        
        # Sales should NOT access design-gallery
        self.test(
            "Sales GET /design-gallery (should be 403)",
            "GET",
            "design-gallery",
            403,
            token=self.sales_token
        )
        
        # Sales should NOT access integrations
        self.test(
            "Sales GET /admin/integrations (should be 403)",
            "GET",
            "admin/integrations",
            403,
            token=self.sales_token
        )
        
        # Manager CAN access KPI and gallery
        self.test(
            "Manager GET /hr/kpi (should be 200)",
            "GET",
            "hr/kpi",
            200,
            token=self.manager_token
        )
        
        self.test(
            "Manager GET /design-gallery (should be 200)",
            "GET",
            "design-gallery",
            200,
            token=self.manager_token
        )
        
        # Manager should NOT access integrations (no manage_settings)
        self.test(
            "Manager GET /admin/integrations (should be 403)",
            "GET",
            "admin/integrations",
            403,
            token=self.manager_token
        )

    def run_all_tests(self):
        """Run all H5 tests"""
        self.log("=" * 60, "INFO")
        self.log("FASE H5 Backend Testing - KPI, Gallery, AI, RBAC", "INFO")
        self.log("=" * 60, "INFO")
        
        # Login all users
        self.admin_token = self.login("admin@kainnusantara.id", "demo12345")
        self.manager_token = self.login("manager@kainnusantara.id", "demo12345")
        self.sales_token = self.login("sales@kainnusantara.id", "demo12345")
        
        if not all([self.admin_token, self.manager_token, self.sales_token]):
            self.log("Failed to login all users, aborting tests", "FAIL")
            return 1
        
        # Run test suites
        self.test_kpi_crud()
        self.test_ess_kpi()
        self.test_design_gallery_crud()
        self.test_gallery_file_upload()
        self.test_ai_autotag_graceful()
        self.test_integrations_settings()
        self.test_rbac()
        
        # Summary
        self.log("\n" + "=" * 60, "INFO")
        self.log(f"BACKEND TESTS COMPLETE", "INFO")
        self.log(f"Total: {self.tests_run} | Passed: {self.tests_passed} | Failed: {self.tests_failed}", "INFO")
        
        if self.failures:
            self.log("\nFailed Tests:", "FAIL")
            for failure in self.failures:
                self.log(f"  - {failure}", "FAIL")
        
        self.log("=" * 60, "INFO")
        
        return 0 if self.tests_failed == 0 else 1

if __name__ == "__main__":
    runner = H5TestRunner()
    sys.exit(runner.run_all_tests())
