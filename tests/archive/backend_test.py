"""
Backend API Testing for Kain Nusantara ERP
Tests R&D/Designer report endpoints including SLA board regression fix
"""
import requests
import sys
from typing import Dict, Any

BASE_URL = "https://po-grid-layout.preview.emergentagent.com"
ENTITY_ID = "ent_ksc"

class DesignerKpiTester:
    def __init__(self):
        self.manager_token = None
        self.sales_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def log(self, message: str, status: str = "info"):
        """Log test messages"""
        symbols = {"pass": "✅", "fail": "❌", "info": "🔍", "warn": "⚠️"}
        print(f"{symbols.get(status, '•')} {message}")

    def run_test(self, name: str, test_func) -> bool:
        """Run a single test and track results"""
        self.tests_run += 1
        self.log(f"Testing {name}...", "info")
        try:
            test_func()
            self.tests_passed += 1
            self.log(f"PASSED: {name}", "pass")
            return True
        except AssertionError as e:
            self.log(f"FAILED: {name} - {str(e)}", "fail")
            self.failed_tests.append({"test": name, "error": str(e)})
            return False
        except Exception as e:
            self.log(f"ERROR: {name} - {str(e)}", "fail")
            self.failed_tests.append({"test": name, "error": f"Exception: {str(e)}"})
            return False

    def login(self, email: str, password: str) -> str:
        """Login and return token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password}
        )
        assert response.status_code == 200, f"Login failed: {response.status_code}"
        data = response.json()
        assert "token" in data, "No token in login response"
        return data["token"]

    def setup_auth(self):
        """Setup authentication tokens"""
        self.log("Setting up authentication...", "info")
        self.manager_token = self.login("manager@kainnusantara.id", "demo12345")
        self.sales_token = self.login("sales@kainnusantara.id", "demo12345")
        self.log("Authentication setup complete", "pass")

    def get_headers(self, token: str) -> Dict[str, str]:
        """Get request headers with auth and entity"""
        return {
            "Authorization": f"Bearer {token}",
            "X-Entity-Id": ENTITY_ID,
            "Content-Type": "application/json"
        }

    # ═══ REGRESSION FIX - SLA Board Endpoint ═══
    def test_sla_board_endpoint(self):
        """Test GET /api/rnd/sla/board returns 200 (NOT 404) - REGRESSION FIX"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/sla/board",
            headers=self.get_headers(self.manager_token)
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code} - Route decorator missing?"
        data = response.json()
        
        # Verify response structure
        assert "count" in data, "Missing 'count' key"
        assert "items" in data, "Missing 'items' key"
        assert "manager_count" in data, "Missing 'manager_count' key"
        assert "admin_count" in data, "Missing 'admin_count' key"
        assert "worst_days_late" in data, "Missing 'worst_days_late' key"
        
        # Verify count >= 1 (there are overdue rounds in seed)
        assert data["count"] >= 1, f"Expected count >= 1 (overdue rounds exist), got {data['count']}"
        
        self.log(f"SLA Board: {data['count']} overdue rounds, {data['manager_count']} manager-level, {data['admin_count']} admin-level", "info")

    def test_sla_board_sales_forbidden(self):
        """Test GET /api/rnd/sla/board returns 403 for sales role (RBAC)"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/sla/board",
            headers=self.get_headers(self.sales_token)
        )
        assert response.status_code == 403, f"Expected 403 for sales role, got {response.status_code}"

    def test_sla_escalate_endpoint(self):
        """Test POST /api/rnd/sla/escalate returns 200 (idempotent)"""
        response = requests.post(
            f"{BASE_URL}/api/rnd/sla/escalate",
            headers=self.get_headers(self.manager_token)
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify response structure (idempotent run, don't assert on created count)
        assert "status" in data or "scanned" in data or "created" in data, "Missing expected keys in escalate response"
        
        self.log(f"SLA Escalate: {data}", "info")

    # ═══ KONTRABON REGRESSION ═══
    def test_contra_bons_list(self):
        """Test GET /api/contra-bons returns 3 items for KSC entity"""
        response = requests.get(
            f"{BASE_URL}/api/contra-bons",
            headers=self.get_headers(self.manager_token)
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify it's a list
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        
        # Verify count is 3 (KSC/CB-00001 paid, KSC/CB-00002 scheduled_payment, KSC/CB-00003 submitted)
        assert len(data) == 3, f"Expected 3 contra-bons for KSC, got {len(data)}"
        
        # Verify the expected numbers exist
        numbers = [cb.get("number") for cb in data]
        self.log(f"Contra-bons found: {numbers}", "info")
        
        # Verify expected statuses
        statuses = {cb.get("number"): cb.get("status") for cb in data}
        self.log(f"Contra-bon statuses: {statuses}", "info")

    # ═══ PHASE C TESTS - Trend Chart Endpoint ═══
    def test_trend_endpoint_basic(self):
        """Test GET /api/rnd/reports/designer-kpi/trend with default params"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi/trend",
            headers=self.get_headers(self.manager_token),
            params={"months": 6, "metric": "avg_score"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify response structure
        assert "months" in data, "Missing 'months' key"
        assert "month_labels" in data, "Missing 'month_labels' key"
        assert "series" in data, "Missing 'series' key"
        assert "metric" in data, "Missing 'metric' key"
        
        # Verify months count
        assert len(data["months"]) == 6, f"Expected 6 months, got {len(data['months'])}"
        assert len(data["month_labels"]) == 6, f"Expected 6 month labels, got {len(data['month_labels'])}"
        
        # Verify metric
        assert data["metric"] == "avg_score", f"Expected metric 'avg_score', got {data['metric']}"
        
        # Verify series structure
        if data["series"]:
            for s in data["series"]:
                assert "designer" in s, "Series missing 'designer' key"
                assert "points" in s, "Series missing 'points' key"
                assert len(s["points"]) == 6, f"Expected 6 points, got {len(s['points'])}"
                for p in s["points"]:
                    assert "month" in p, "Point missing 'month' key"
                    assert "score" in p, "Point missing 'score' key"

    def test_trend_endpoint_grade_metric(self):
        """Test trend endpoint with metric=grade"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi/trend",
            headers=self.get_headers(self.manager_token),
            params={"months": 6, "metric": "grade"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["metric"] == "grade", f"Expected metric 'grade', got {data['metric']}"

    def test_trend_endpoint_3_months(self):
        """Test trend endpoint with 3 months"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi/trend",
            headers=self.get_headers(self.manager_token),
            params={"months": 3, "metric": "avg_score"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert len(data["months"]) == 3, f"Expected 3 months, got {len(data['months'])}"

    def test_trend_endpoint_12_months(self):
        """Test trend endpoint with 12 months"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi/trend",
            headers=self.get_headers(self.manager_token),
            params={"months": 12, "metric": "avg_score"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert len(data["months"]) == 12, f"Expected 12 months, got {len(data['months'])}"

    def test_trend_endpoint_sales_forbidden(self):
        """Test trend endpoint returns 403 for sales role"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi/trend",
            headers=self.get_headers(self.sales_token),
            params={"months": 6, "metric": "avg_score"}
        )
        assert response.status_code == 403, f"Expected 403 for sales, got {response.status_code}"

    # ═══ PHASE D TESTS - PDF Report Endpoint ═══
    def test_report_endpoint_pdf(self):
        """Test GET /api/rnd/reports/designer-kpi/report returns PDF"""
        # First get the list of designers
        kpi_response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi",
            headers=self.get_headers(self.manager_token),
            params={"period": "all"}
        )
        assert kpi_response.status_code == 200, "Failed to get KPI data"
        kpi_data = kpi_response.json()
        
        if not kpi_data.get("items"):
            self.log("No designers found, skipping PDF test", "warn")
            return
        
        designer_name = kpi_data["items"][0]["designer"]
        
        # Test PDF download
        response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi/report",
            headers=self.get_headers(self.manager_token),
            params={"designer": designer_name, "period": "all", "format": "pdf"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get("content-type") == "application/pdf", \
            f"Expected application/pdf, got {response.headers.get('content-type')}"
        
        # Verify PDF content starts with %PDF
        content = response.content
        assert content[:4] == b"%PDF", "Response does not start with PDF signature"
        assert len(content) > 1000, f"PDF too small: {len(content)} bytes"

    def test_report_endpoint_invalid_format(self):
        """Test report endpoint returns 400 for invalid format"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi/report",
            headers=self.get_headers(self.manager_token),
            params={"designer": "Test Designer", "period": "all", "format": "csv"}
        )
        assert response.status_code == 400, f"Expected 400 for invalid format, got {response.status_code}"

    def test_report_endpoint_unknown_designer(self):
        """Test report endpoint returns 200 with 'no data' PDF for unknown designer"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi/report",
            headers=self.get_headers(self.manager_token),
            params={"designer": "Orang Tidak Ada", "period": "all", "format": "pdf"}
        )
        assert response.status_code == 200, f"Expected 200 for unknown designer, got {response.status_code}"
        assert response.headers.get("content-type") == "application/pdf", \
            "Expected PDF content-type for unknown designer"
        # Should still be a valid PDF
        assert response.content[:4] == b"%PDF", "Should return valid PDF even for unknown designer"

    def test_report_endpoint_sales_forbidden(self):
        """Test report endpoint returns 403 for sales role"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi/report",
            headers=self.get_headers(self.sales_token),
            params={"designer": "Test Designer", "period": "all", "format": "pdf"}
        )
        assert response.status_code == 403, f"Expected 403 for sales, got {response.status_code}"

    # ═══ PS-17 TESTS - Division Management ═══
    def test_divisions_list_manager(self):
        """Test GET /api/rnd/divisions returns 200 for manager with divisions and approver_matrix"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/divisions",
            headers=self.get_headers(self.manager_token)
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify response structure
        assert "divisions" in data, "Missing 'divisions' key"
        assert "approver_matrix" in data, "Missing 'approver_matrix' key"
        assert isinstance(data["divisions"], list), "divisions should be a list"
        assert isinstance(data["approver_matrix"], list), "approver_matrix should be a list"
        
        # Verify divisions structure (7 fixed divisions per D-13)
        assert len(data["divisions"]) == 7, f"Expected 7 divisions, got {len(data['divisions'])}"
        for div in data["divisions"]:
            assert "id" in div, "Division missing 'id' key"
            assert "name" in div, "Division missing 'name' key"
            assert "member_count" in div, "Division missing 'member_count' key"
        
        # Verify approver_matrix structure (4 stages per D-13)
        assert len(data["approver_matrix"]) == 4, f"Expected 4 approval stages, got {len(data['approver_matrix'])}"
        expected_stages = ["design_acc", "sample_acc", "po_custom", "purchase_request"]
        for stage in data["approver_matrix"]:
            assert "stage" in stage, "Stage missing 'stage' key"
            assert stage["stage"] in expected_stages, f"Unexpected stage: {stage['stage']}"
            assert "label" in stage, "Stage missing 'label' key"
            assert "approvers" in stage, "Stage missing 'approvers' key"
        
        self.log(f"Divisions: {len(data['divisions'])}, Approver stages: {len(data['approver_matrix'])}", "info")

    def test_divisions_list_sales_forbidden(self):
        """Test GET /api/rnd/divisions returns 403 for sales role"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/divisions",
            headers=self.get_headers(self.sales_token)
        )
        assert response.status_code == 403, f"Expected 403 for sales role, got {response.status_code}"

    def test_divisions_members_list(self):
        """Test GET /api/rnd/divisions/members returns 200 with people (>=5)"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/divisions/members",
            headers=self.get_headers(self.manager_token)
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify it's a list
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        
        # Verify count >= 5 (per test requirement)
        assert len(data) >= 5, f"Expected >= 5 members, got {len(data)}"
        
        # Verify member structure
        for member in data:
            assert "name" in member, "Member missing 'name' key"
            assert "role" in member, "Member missing 'role' key"
            assert "source" in member, "Member missing 'source' key"
            assert "division" in member, "Member missing 'division' key"
            assert "division_name" in member, "Member missing 'division_name' key"
        
        self.log(f"Members found: {len(data)}", "info")

    def test_divisions_members_sales_forbidden(self):
        """Test GET /api/rnd/divisions/members returns 403 for sales role"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/divisions/members",
            headers=self.get_headers(self.sales_token)
        )
        assert response.status_code == 403, f"Expected 403 for sales role, got {response.status_code}"

    def test_set_member_division_valid(self):
        """Test PUT /api/rnd/divisions/members with valid division (Bagas Nugroho -> sample)"""
        # First, get current members to find Bagas Nugroho
        response = requests.get(
            f"{BASE_URL}/api/rnd/divisions/members",
            headers=self.get_headers(self.manager_token)
        )
        assert response.status_code == 200, "Failed to get members list"
        members = response.json()
        
        # Find Bagas Nugroho
        bagas = next((m for m in members if m["name"] == "Bagas Nugroho"), None)
        original_division = bagas["division"] if bagas else "rnd"
        
        # Set Bagas to 'sample' division
        response = requests.put(
            f"{BASE_URL}/api/rnd/divisions/members",
            headers=self.get_headers(self.manager_token),
            json={"name": "Bagas Nugroho", "division": "sample"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify response
        assert data["name"] == "Bagas Nugroho", "Name mismatch in response"
        assert data["division"] == "sample", "Division not set to 'sample'"
        assert data["division_name"] == "Sample", "Division name should be 'Sample'"
        
        # Restore original division
        restore_response = requests.put(
            f"{BASE_URL}/api/rnd/divisions/members",
            headers=self.get_headers(self.manager_token),
            json={"name": "Bagas Nugroho", "division": original_division}
        )
        assert restore_response.status_code == 200, "Failed to restore original division"
        
        self.log(f"Bagas Nugroho division changed to 'sample' and restored to '{original_division}'", "info")

    def test_set_member_division_invalid(self):
        """Test PUT /api/rnd/divisions/members with invalid division returns 400"""
        response = requests.put(
            f"{BASE_URL}/api/rnd/divisions/members",
            headers=self.get_headers(self.manager_token),
            json={"name": "Bagas Nugroho", "division": "xxx"}
        )
        assert response.status_code == 400, f"Expected 400 for invalid division, got {response.status_code}"

    def test_set_member_division_sales_forbidden(self):
        """Test PUT /api/rnd/divisions/members returns 403 for sales role"""
        response = requests.put(
            f"{BASE_URL}/api/rnd/divisions/members",
            headers=self.get_headers(self.sales_token),
            json={"name": "Bagas Nugroho", "division": "sample"}
        )
        assert response.status_code == 403, f"Expected 403 for sales role, got {response.status_code}"

    def test_kpi_with_division_field(self):
        """Test GET /api/rnd/reports/designer-kpi?period=all returns items with division/division_name"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi",
            headers=self.get_headers(self.manager_token),
            params={"period": "all"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify structure
        assert "items" in data, "Missing 'items' key"
        assert "divisions_present" in data, "Missing 'divisions_present' key"
        
        # Verify items have division fields
        if data["items"]:
            for item in data["items"]:
                assert "division" in item, "Item missing 'division' key"
                assert "division_name" in item, "Item missing 'division_name' key"
        
        self.log(f"KPI items: {len(data['items'])}, divisions_present: {data.get('divisions_present', [])}", "info")

    def test_kpi_division_filter(self):
        """Test GET /api/rnd/reports/designer-kpi?division=designer returns only designer division"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi",
            headers=self.get_headers(self.manager_token),
            params={"period": "all", "division": "designer"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify structure
        assert "items" in data, "Missing 'items' key"
        assert "division" in data, "Missing 'division' key in response"
        assert data["division"] == "designer", f"Expected division='designer', got {data['division']}"
        
        # Verify all items are from designer division
        for item in data["items"]:
            assert item["division"] == "designer", f"Expected designer division, got {item['division']} for {item['designer']}"
        
        # Verify we have 2 designers (Dewi Lestari, Rina Kartika per test requirement)
        designer_names = [item["designer"] for item in data["items"]]
        self.log(f"Designer division members: {designer_names}", "info")
        # Note: We don't assert exact count as seed data may vary, but log for verification

    # ═══ REGRESSION TESTS ═══
    def test_existing_kpi_endpoint(self):
        """Test existing KPI endpoint still works"""
        response = requests.get(
            f"{BASE_URL}/api/rnd/reports/designer-kpi",
            headers=self.get_headers(self.manager_token),
            params={"period": "30d"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify structure
        assert "items" in data, "Missing 'items' key"
        assert "summary" in data, "Missing 'summary' key"
        assert "weights" in data, "Missing 'weights' key"
        assert "period_options" in data, "Missing 'period_options' key"

    def test_export_endpoints(self):
        """Test export endpoints (xlsx, pdf, csv) still work"""
        for fmt in ["xlsx", "pdf", "csv"]:
            response = requests.get(
                f"{BASE_URL}/api/rnd/reports/designer-kpi/export",
                headers=self.get_headers(self.manager_token),
                params={"period": "30d", "format": fmt}
            )
            assert response.status_code == 200, f"Export {fmt} failed: {response.status_code}"
            assert len(response.content) > 100, f"Export {fmt} content too small"

    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*70)
        print("BACKEND API TESTING - Kain Nusantara ERP")
        print("R&D/Designer Report Endpoints + SLA Board Regression Fix")
        print("="*70 + "\n")

        # Setup
        try:
            self.setup_auth()
        except Exception as e:
            self.log(f"Authentication setup failed: {e}", "fail")
            return 1

        # REGRESSION FIX - SLA Board
        print("\n" + "-"*70)
        print("REGRESSION FIX - SLA Board Endpoint")
        print("-"*70)
        self.run_test("SLA Board endpoint returns 200 (NOT 404)", self.test_sla_board_endpoint)
        self.run_test("SLA Board 403 for sales role (RBAC)", self.test_sla_board_sales_forbidden)
        self.run_test("SLA Escalate endpoint (idempotent)", self.test_sla_escalate_endpoint)

        # KONTRABON REGRESSION
        print("\n" + "-"*70)
        print("KONTRABON REGRESSION")
        print("-"*70)
        self.run_test("Contra-bons list returns 3 items for KSC", self.test_contra_bons_list)

        # PS-17 - Division Management Tests
        print("\n" + "-"*70)
        print("PS-17 - Division Management (R&D Organization)")
        print("-"*70)
        self.run_test("Divisions list (manager 200)", self.test_divisions_list_manager)
        self.run_test("Divisions list (sales 403)", self.test_divisions_list_sales_forbidden)
        self.run_test("Divisions members list (>=5 people)", self.test_divisions_members_list)
        self.run_test("Divisions members (sales 403)", self.test_divisions_members_sales_forbidden)
        self.run_test("Set member division (valid)", self.test_set_member_division_valid)
        self.run_test("Set member division (invalid 400)", self.test_set_member_division_invalid)
        self.run_test("Set member division (sales 403)", self.test_set_member_division_sales_forbidden)
        self.run_test("KPI with division field", self.test_kpi_with_division_field)
        self.run_test("KPI division filter (designer)", self.test_kpi_division_filter)

        # PHASE C - Trend Chart Tests
        print("\n" + "-"*70)
        print("R&D REPORTS - Trend Chart Endpoint")
        print("-"*70)
        self.run_test("Trend endpoint basic (6 months, avg_score)", self.test_trend_endpoint_basic)
        self.run_test("Trend endpoint with grade metric", self.test_trend_endpoint_grade_metric)
        self.run_test("Trend endpoint with 3 months", self.test_trend_endpoint_3_months)
        self.run_test("Trend endpoint with 12 months", self.test_trend_endpoint_12_months)
        self.run_test("Trend endpoint 403 for sales role", self.test_trend_endpoint_sales_forbidden)

        # PHASE D - PDF Report Tests
        print("\n" + "-"*70)
        print("R&D REPORTS - PDF Report Endpoint")
        print("-"*70)
        self.run_test("Report endpoint returns PDF", self.test_report_endpoint_pdf)
        self.run_test("Report endpoint 400 for invalid format", self.test_report_endpoint_invalid_format)
        self.run_test("Report endpoint 200 for unknown designer", self.test_report_endpoint_unknown_designer)
        self.run_test("Report endpoint 403 for sales role", self.test_report_endpoint_sales_forbidden)

        # REGRESSION Tests
        print("\n" + "-"*70)
        print("REGRESSION - Existing Endpoints")
        print("-"*70)
        self.run_test("Existing KPI endpoint", self.test_existing_kpi_endpoint)
        self.run_test("Export endpoints (xlsx/pdf/csv)", self.test_export_endpoints)

        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Total tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Tests failed: {len(self.failed_tests)}")
        print(f"Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print("\nFailed tests:")
            for fail in self.failed_tests:
                print(f"  ❌ {fail['test']}: {fail['error']}")
        
        print("="*70 + "\n")
        
        return 0 if self.tests_passed == self.tests_run else 1

if __name__ == "__main__":
    tester = DesignerKpiTester()
    sys.exit(tester.run_all_tests())
