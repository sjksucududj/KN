#!/usr/bin/env python3
"""
Backend API Testing for PS-18 - Designer KPI & SLA Escalation
Tests all backend endpoints with different roles and validates responses.
"""
import requests
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# Public endpoint from frontend/.env
BASE_URL = "https://kn-dev-continue-1.preview.emergentagent.com/api"

# Test credentials from test_credentials.md
CREDENTIALS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "manager": {"email": "manager@kainnusantara.id", "password": "demo12345"},
    "sales": {"email": "sales@kainnusantara.id", "password": "demo12345"},
    "warehouse": {"email": "warehouse@kainnusantara.id", "password": "demo12345"},
}

class APITester:
    def __init__(self):
        self.tokens: Dict[str, str] = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.results = []

    def log(self, status: str, message: str):
        """Log test result"""
        symbol = "✅" if status == "PASS" else "❌"
        print(f"{symbol} {status}: {message}")
        self.results.append((status, message))

    def test(self, name: str, condition: bool, detail: str = ""):
        """Run a test assertion"""
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log("PASS", f"{name}" + (f" - {detail}" if detail else ""))
        else:
            self.log("FAIL", f"{name}" + (f" - {detail}" if detail else ""))
        return condition

    def login(self, role: str) -> Optional[str]:
        """Login and get token for a role"""
        if role in self.tokens:
            return self.tokens[role]
        
        creds = CREDENTIALS.get(role)
        if not creds:
            self.log("FAIL", f"No credentials for role: {role}")
            return None
        
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json=creds,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                token = data.get("token")
                if token:
                    self.tokens[role] = token
                    self.log("PASS", f"Login successful for {role}")
                    return token
                else:
                    self.log("FAIL", f"No token in response for {role}")
                    return None
            else:
                self.log("FAIL", f"Login failed for {role}: {response.status_code}")
                return None
        except Exception as e:
            self.log("FAIL", f"Login error for {role}: {str(e)}")
            return None

    def api_call(self, method: str, endpoint: str, role: str = "admin", 
                 expected_status: int = 200, json_data: Optional[Dict] = None) -> Optional[Dict]:
        """Make an API call with authentication"""
        token = self.login(role)
        if not token:
            return None
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        url = f"{BASE_URL}/{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=15)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=json_data or {}, timeout=15)
            else:
                self.log("FAIL", f"Unsupported method: {method}")
                return None
            
            if response.status_code == expected_status:
                if response.status_code in [200, 201]:
                    return response.json()
                return {"status_code": response.status_code}
            else:
                self.log("FAIL", f"{method} {endpoint} returned {response.status_code}, expected {expected_status}")
                try:
                    error_detail = response.json()
                    print(f"   Error detail: {error_detail}")
                except Exception:
                    print(f"   Response text: {response.text[:200]}")
                return None
        except Exception as e:
            self.log("FAIL", f"{method} {endpoint} error: {str(e)}")
            return None

    def test_designer_kpi_endpoint(self):
        """Test GET /api/rnd/reports/designer-kpi with all period filters"""
        print("\n" + "="*80)
        print("TEST 1: Designer KPI Endpoint")
        print("="*80)
        
        # Test with admin
        data = self.api_call("GET", "rnd/reports/designer-kpi?period=all", "admin")
        if data:
            # Check required fields
            self.test("Designer KPI response has 'period' field", "period" in data)
            self.test("Designer KPI response has 'period_label' field", "period_label" in data)
            self.test("Designer KPI response has 'from_date' field", "from_date" in data)
            self.test("Designer KPI response has 'to_date' field", "to_date" in data)
            self.test("Designer KPI response has 'count' field", "count" in data)
            self.test("Designer KPI response has 'items' field", "items" in data and isinstance(data["items"], list))
            self.test("Designer KPI response has 'summary' field", "summary" in data)
            self.test("Designer KPI response has 'weights' field", "weights" in data)
            self.test("Designer KPI response has 'period_options' field", "period_options" in data)
            self.test("Designer KPI response has 'grade_bands' field", "grade_bands" in data)
            
            # Check seed data: 3 designers
            count = data.get("count", 0)
            self.test("Designer KPI has 3 designers from seed", count >= 3, f"Found {count} designers")
            
            # Check item fields
            if data.get("items"):
                item = data["items"][0]
                required_fields = [
                    "designer", "rank", "rounds", "submitted", "assessed", "acc", "revisi", 
                    "tolak", "rework", "late_submitted", "overdue_now", "overdue_critical",
                    "max_days_late", "late_total", "on_time_pct", "acc_rate", "rework_pct",
                    "avg_score", "avg_days", "cost_total", "grade_score", "grade_base",
                    "grade_penalty", "grade_letter", "grade_meaning"
                ]
                for field in required_fields:
                    self.test(f"Designer item has '{field}' field", field in item)
                
                # Check for specific designers from seed
                designers = [item["designer"] for item in data["items"]]
                self.test("Dewi Lestari in designers", "Dewi Lestari" in designers)
                self.test("Rina Kartika in designers", "Rina Kartika" in designers)
                self.test("Bagas Nugroho in designers", "Bagas Nugroho" in designers)
                
                # Check grades
                for item in data["items"]:
                    if item["designer"] == "Dewi Lestari":
                        self.test("Dewi Lestari has grade B", item["grade_letter"] == "B", 
                                f"Grade: {item['grade_letter']}")
                    elif item["designer"] == "Rina Kartika":
                        self.test("Rina Kartika has grade C", item["grade_letter"] == "C",
                                f"Grade: {item['grade_letter']}")
                    elif item["designer"] == "Bagas Nugroho":
                        self.test("Bagas Nugroho has grade D or 0.0", 
                                item["grade_letter"] in ["D", "—"] or item["grade_score"] == 0.0,
                                f"Grade: {item['grade_letter']}, Score: {item['grade_score']}")

    def test_period_filters(self):
        """Test period filters: month, 30d, 90d, all"""
        print("\n" + "="*80)
        print("TEST 2: Period Filters")
        print("="*80)
        
        periods = ["month", "30d", "90d", "all", "xyz"]  # xyz should fallback to 'all'
        
        for period in periods:
            data = self.api_call("GET", f"rnd/reports/designer-kpi?period={period}", "admin")
            if data:
                if period == "xyz":
                    self.test(f"Period '{period}' falls back to 'all'", 
                            data.get("period") == "all",
                            f"Got period: {data.get('period')}")
                else:
                    self.test(f"Period '{period}' returns correct period", 
                            data.get("period") == period,
                            f"Got period: {data.get('period')}")
                
                # Check from_date logic
                if period == "month":
                    self.test(f"Period 'month' has from_date as 1st of month",
                            data.get("from_date", "").endswith("-01") if data.get("from_date") else False,
                            f"from_date: {data.get('from_date')}")
                elif period == "all":
                    self.test(f"Period 'all' has empty from_date",
                            data.get("from_date") == "",
                            f"from_date: {data.get('from_date')}")

    def test_sla_board(self):
        """Test GET /api/rnd/sla/board"""
        print("\n" + "="*80)
        print("TEST 3: SLA Board Endpoint")
        print("="*80)
        
        data = self.api_call("GET", "rnd/sla/board", "admin")
        if data:
            self.test("SLA board has 'count' field", "count" in data)
            self.test("SLA board has 'items' field", "items" in data)
            self.test("SLA board has 'manager_count' field", "manager_count" in data)
            self.test("SLA board has 'admin_count' field", "admin_count" in data)
            self.test("SLA board has 'worst_days_late' field", "worst_days_late" in data)
            self.test("SLA board has 'escalate_admin_days' field", "escalate_admin_days" in data)
            self.test("SLA board has 'round_sla_days' field", "round_sla_days" in data)
            
            # Check for 2 overdue rounds from seed
            count = data.get("count", 0)
            self.test("SLA board has 2 overdue rounds from seed", count >= 2, 
                    f"Found {count} overdue rounds")
            
            # Check item fields
            if data.get("items"):
                item = data["items"][0]
                required_fields = [
                    "days_late", "tier", "designer", "state_label", "due_date",
                    "number", "round_no", "supplier_name"
                ]
                for field in required_fields:
                    self.test(f"SLA item has '{field}' field", field in item)
                
                # Check for specific rounds from seed
                numbers = [item.get("number", "") for item in data["items"]]
                self.test("KSC/SMP-00010 in overdue rounds", "KSC/SMP-00010" in numbers,
                        f"Found: {', '.join(numbers[:5])}")
                self.test("KSC/SMP-00008 in overdue rounds", "KSC/SMP-00008" in numbers,
                        f"Found: {', '.join(numbers[:5])}")
                
                # Check tiers
                for item in data["items"]:
                    if item.get("number") == "KSC/SMP-00010":
                        self.test("KSC/SMP-00010 has tier 'admin' (4 days late)",
                                item.get("tier") == "admin",
                                f"Tier: {item.get('tier')}, Days late: {item.get('days_late')}")
                    elif item.get("number") == "KSC/SMP-00008":
                        self.test("KSC/SMP-00008 has tier 'manager' (1 day late)",
                                item.get("tier") == "manager",
                                f"Tier: {item.get('tier')}, Days late: {item.get('days_late')}")

    def test_sla_escalation(self):
        """Test POST /api/rnd/sla/escalate (idempotent)"""
        print("\n" + "="*80)
        print("TEST 4: SLA Escalation Endpoint (Idempotent)")
        print("="*80)
        
        # First call
        data1 = self.api_call("POST", "rnd/sla/escalate", "admin")
        if data1:
            self.test("SLA escalation returns 'status' field", "status" in data1)
            self.test("SLA escalation returns 'created' field", "created" in data1)
            self.test("SLA escalation returns 'scanned' field", "scanned" in data1)
            self.test("SLA escalation returns 'detail' field", "detail" in data1)
            self.test("SLA escalation status is 'success'", data1.get("status") == "success",
                    f"Status: {data1.get('status')}")
            
            created1 = data1.get("created", 0)
            
            # Second call (should be idempotent)
            data2 = self.api_call("POST", "rnd/sla/escalate", "admin")
            if data2:
                created2 = data2.get("created", 0)
                self.test("SLA escalation is idempotent (2nd call creates 0 notifications)",
                        created2 == 0,
                        f"1st call created: {created1}, 2nd call created: {created2}")

    def test_notifications(self):
        """Test that notifications were created"""
        print("\n" + "="*80)
        print("TEST 5: Notifications Created")
        print("="*80)
        
        data = self.api_call("GET", "notifications?limit=50", "admin")
        if data and "items" in data:
            items = data["items"]
            
            # Check for rnd_sla_overdue notifications
            overdue_notifs = [n for n in items if n.get("type") == "rnd_sla_overdue"]
            self.test("Found rnd_sla_overdue notifications", len(overdue_notifs) > 0,
                    f"Found {len(overdue_notifs)} notifications")
            
            # Check for rnd_sla_escalated notifications
            escalated_notifs = [n for n in items if n.get("type") == "rnd_sla_escalated"]
            self.test("Found rnd_sla_escalated notifications", len(escalated_notifs) > 0,
                    f"Found {len(escalated_notifs)} notifications")
            
            # Check recipient roles
            manager_notifs = [n for n in overdue_notifs if n.get("recipient_role") == "manager"]
            admin_notifs = [n for n in escalated_notifs if n.get("recipient_role") == "admin"]
            
            self.test("Manager notifications have correct recipient_role",
                    len(manager_notifs) > 0,
                    f"Found {len(manager_notifs)} manager notifications")
            self.test("Admin notifications have correct recipient_role",
                    len(admin_notifs) > 0,
                    f"Found {len(admin_notifs)} admin notifications")

    def test_scheduler_jobs(self):
        """Test GET /api/scheduler/jobs and job execution"""
        print("\n" + "="*80)
        print("TEST 6: Scheduler Jobs")
        print("="*80)
        
        data = self.api_call("GET", "scheduler/jobs", "admin")
        if data and "items" in data:
            jobs = data["items"]
            
            # Find rnd_sla_escalation job
            escalation_job = next((j for j in jobs if j.get("id") == "rnd_sla_escalation"), None)
            
            self.test("Job 'rnd_sla_escalation' exists", escalation_job is not None)
            
            if escalation_job:
                self.test("Job has label 'Eskalasi SLA Sample R&D'",
                        escalation_job.get("label") == "Eskalasi SLA Sample R&D",
                        f"Label: {escalation_job.get('label')}")
                self.test("Job kind is 'daily'", escalation_job.get("kind") == "daily",
                        f"Kind: {escalation_job.get('kind')}")
                self.test("Job is enabled", escalation_job.get("enabled") == True,
                        f"Enabled: {escalation_job.get('enabled')}")
                self.test("Job schedule is '07:35'", "07:35" in str(escalation_job.get("schedule", "")),
                        f"Schedule: {escalation_job.get('schedule')}")
        
        # Test job execution
        run_data = self.api_call("POST", "scheduler/jobs/rnd_sla_escalation/run", "admin")
        if run_data:
            self.test("Job execution returns 'status' field", "status" in run_data)
            self.test("Job execution status is 'success'", run_data.get("status") == "success",
                    f"Status: {run_data.get('status')}")
        
        # Test job runs
        runs_data = self.api_call("GET", "scheduler/runs?job_id=rnd_sla_escalation&limit=5", "admin")
        if runs_data and "items" in runs_data:
            self.test("Job runs recorded", len(runs_data["items"]) > 0,
                    f"Found {len(runs_data['items'])} runs")

    def test_config_registry(self):
        """Test GET /api/config/registry?group=rnd"""
        print("\n" + "="*80)
        print("TEST 7: Config Registry (R&D Settings)")
        print("="*80)
        
        data = self.api_call("GET", "config/registry?group=rnd", "admin")
        if data and "items" in data:
            items = data["items"]
            
            # Check for 6 new keys
            required_keys = [
                "rnd.sla_escalate_admin_days",
                "rnd.kpi_weight_on_time",
                "rnd.kpi_weight_score",
                "rnd.kpi_weight_acc",
                "rnd.kpi_penalty_rework",
                "rnd.kpi_penalty_overdue"
            ]
            
            found_keys = [item.get("key") for item in items]
            
            for key in required_keys:
                self.test(f"Config key '{key}' exists", key in found_keys)
            
            # Check default values
            for item in items:
                key = item.get("key")
                if key == "rnd.sla_escalate_admin_days":
                    self.test("rnd.sla_escalate_admin_days default is 3",
                            item.get("default") == 3,
                            f"Default: {item.get('default')}")
                elif key == "rnd.kpi_weight_on_time":
                    self.test("rnd.kpi_weight_on_time default is 40",
                            item.get("default") == 40,
                            f"Default: {item.get('default')}")
                elif key == "rnd.kpi_weight_score":
                    self.test("rnd.kpi_weight_score default is 40",
                            item.get("default") == 40,
                            f"Default: {item.get('default')}")
                elif key == "rnd.kpi_weight_acc":
                    self.test("rnd.kpi_weight_acc default is 20",
                            item.get("default") == 20,
                            f"Default: {item.get('default')}")

    def test_rbac_permissions(self):
        """Test RBAC for different roles"""
        print("\n" + "="*80)
        print("TEST 8: RBAC Permissions")
        print("="*80)
        
        # Admin should have access
        self.test("Admin can access designer-kpi",
                self.api_call("GET", "rnd/reports/designer-kpi", "admin") is not None)
        self.test("Admin can access sla/board",
                self.api_call("GET", "rnd/sla/board", "admin") is not None)
        self.test("Admin can POST sla/escalate",
                self.api_call("POST", "rnd/sla/escalate", "admin") is not None)
        
        # Manager should have access
        self.test("Manager can access designer-kpi",
                self.api_call("GET", "rnd/reports/designer-kpi", "manager") is not None)
        self.test("Manager can access sla/board",
                self.api_call("GET", "rnd/sla/board", "manager") is not None)
        self.test("Manager can POST sla/escalate",
                self.api_call("POST", "rnd/sla/escalate", "manager") is not None)
        
        # Sales should be denied
        sales_kpi = self.api_call("GET", "rnd/reports/designer-kpi", "sales", expected_status=403)
        self.test("Sales is denied access to designer-kpi (403)",
                sales_kpi is not None and sales_kpi.get("status_code") == 403)
        
        sales_escalate = self.api_call("POST", "rnd/sla/escalate", "sales", expected_status=403)
        self.test("Sales is denied POST sla/escalate (403)",
                sales_escalate is not None and sales_escalate.get("status_code") == 403)
        
        # Warehouse should be denied
        wh_kpi = self.api_call("GET", "rnd/reports/designer-kpi", "warehouse", expected_status=403)
        self.test("Warehouse is denied access to designer-kpi (403)",
                wh_kpi is not None and wh_kpi.get("status_code") == 403)
        
        wh_escalate = self.api_call("POST", "rnd/sla/escalate", "warehouse", expected_status=403)
        self.test("Warehouse is denied POST sla/escalate (403)",
                wh_escalate is not None and wh_escalate.get("status_code") == 403)

    def test_backward_compatibility(self):
        """Test backward compatibility of existing endpoints"""
        print("\n" + "="*80)
        print("TEST 9: Backward Compatibility")
        print("="*80)
        
        # Test old performer endpoint
        data = self.api_call("GET", "rnd/reports/performer", "admin")
        if data:
            self.test("Old performer endpoint still works", "count" in data and "items" in data)
            if data.get("items"):
                item = data["items"][0]
                self.test("Performer endpoint has backward compatible fields",
                        all(f in item for f in ["performer", "rounds", "acc", "revisi", "avg_score", "avg_days"]))
        
        # Test other R&D endpoints
        self.test("GET /api/rnd/lifecycle-board works",
                self.api_call("GET", "rnd/lifecycle-board", "admin") is not None)
        self.test("GET /api/rnd/samples works",
                self.api_call("GET", "rnd/samples?limit=10", "admin") is not None)
        self.test("GET /api/rnd/specs works",
                self.api_call("GET", "rnd/specs?limit=10", "admin") is not None)
        self.test("GET /api/rnd/meta works",
                self.api_call("GET", "rnd/meta", "admin") is not None)

    def run_all_tests(self):
        """Run all backend tests"""
        print("\n" + "="*80)
        print("BACKEND API TESTING - PS-18")
        print("Testing Designer KPI & SLA Escalation Features")
        print("="*80)
        
        self.test_designer_kpi_endpoint()
        self.test_period_filters()
        self.test_sla_board()
        self.test_sla_escalation()
        self.test_notifications()
        self.test_scheduler_jobs()
        self.test_config_registry()
        self.test_rbac_permissions()
        self.test_backward_compatibility()
        
        # Print summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        print("="*80)
        
        # Print failed tests
        if self.tests_passed < self.tests_run:
            print("\nFAILED TESTS:")
            for status, message in self.results:
                if status == "FAIL":
                    print(f"  ❌ {message}")
        
        return 0 if self.tests_passed == self.tests_run else 1

def main():
    tester = APITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
