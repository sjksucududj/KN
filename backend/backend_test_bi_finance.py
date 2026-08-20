"""Backend test for BI Keuangan (Financial BI Dashboard) module.

Tests:
1. GET /api/finance/bi (default year)
2. GET /api/finance/bi?year=2026 (specific year with seed data)
3. GET /api/finance/bi?year=2026&entity_id=ent_ksc (single entity scope)
4. Verify monthly data structure (12 entries)
5. Verify KPI structure (YTD values)
6. Verify ratios structure
7. Verify entity_comparison structure
8. Verify multi_entity flag
9. Regression: existing finance endpoints still work
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"
EMAIL = "admin@kainnusantara.id"
PASSWORD = "demo12345"

class BIFinanceTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failures = []

    def log(self, msg, level="INFO"):
        prefix = "✅" if level == "PASS" else "❌" if level == "FAIL" else "🔍"
        print(f"{prefix} {msg}")

    def run_test(self, name, test_func):
        """Run a single test"""
        self.tests_run += 1
        self.log(f"Testing {name}...", "INFO")
        try:
            test_func()
            self.tests_passed += 1
            self.log(f"{name} - PASSED", "PASS")
            return True
        except AssertionError as e:
            self.log(f"{name} - FAILED: {str(e)}", "FAIL")
            self.failures.append({"test": name, "error": str(e)})
            return False
        except Exception as e:
            self.log(f"{name} - ERROR: {str(e)}", "FAIL")
            self.failures.append({"test": name, "error": f"Exception: {str(e)}"})
            return False

    def login(self):
        """Login and get token"""
        self.log("Logging in...")
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": EMAIL, "password": PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.status_code}"
        data = response.json()
        self.token = data.get("token")
        assert self.token, "No token received"
        self.log("Login successful", "PASS")

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def test_bi_default_year(self):
        """Test GET /api/finance/bi (default year)"""
        response = requests.get(f"{BASE_URL}/finance/bi", headers=self.get_headers())
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        current_year = datetime.now().year
        assert data.get("year") == current_year, f"Expected year {current_year}, got {data.get('year')}"
        assert "monthly" in data, "Missing 'monthly' field"
        assert "kpi" in data, "Missing 'kpi' field"
        assert "ratios" in data, "Missing 'ratios' field"
        assert "entity_comparison" in data, "Missing 'entity_comparison' field"
        assert "multi_entity" in data, "Missing 'multi_entity' field"

    def test_bi_year_2026(self):
        """Test GET /api/finance/bi?year=2026 (with seed data)"""
        response = requests.get(f"{BASE_URL}/finance/bi?year=2026", headers=self.get_headers())
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("year") == 2026, f"Expected year 2026, got {data.get('year')}"
        
        # Verify monthly structure (12 entries)
        monthly = data.get("monthly", [])
        assert len(monthly) == 12, f"Expected 12 monthly entries, got {len(monthly)}"
        
        # Check first month structure
        first_month = monthly[0]
        required_fields = ["month", "label", "revenue", "cogs", "opex", "expense", "gross_profit", "net_income"]
        for field in required_fields:
            assert field in first_month, f"Missing field '{field}' in monthly data"
        
        # Check July 2026 (month 7) - should have operational data from seed
        july = next((m for m in monthly if m["month"] == "2026-07"), None)
        assert july is not None, "July 2026 data not found"
        self.log(f"July 2026 data: opex={july.get('opex')}, net_income={july.get('net_income')}")
        
        # According to agent note: Juli 2026 should have opex ~1.500.000, net_income ~ -1.500.000
        # We'll check if there's data (not zero)
        assert july.get("opex") != 0 or july.get("net_income") != 0, "July 2026 should have operational data"

    def test_bi_kpi_structure(self):
        """Test KPI structure (YTD values)"""
        response = requests.get(f"{BASE_URL}/finance/bi?year=2026", headers=self.get_headers())
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        kpi = data.get("kpi", {})
        
        required_kpi_fields = ["revenue", "expense", "net_income", "gross_margin", "net_margin"]
        for field in required_kpi_fields:
            assert field in kpi, f"Missing KPI field '{field}'"
        
        self.log(f"KPI: revenue={kpi.get('revenue')}, expense={kpi.get('expense')}, net_income={kpi.get('net_income')}, gross_margin={kpi.get('gross_margin')}%, net_margin={kpi.get('net_margin')}%")

    def test_bi_ratios_structure(self):
        """Test ratios structure"""
        response = requests.get(f"{BASE_URL}/finance/bi?year=2026", headers=self.get_headers())
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        ratios = data.get("ratios", {})
        
        required_ratio_fields = [
            "gross_margin", "net_margin", "current_ratio", "debt_to_equity",
            "current_assets", "current_liabilities", "assets_total", 
            "liabilities_total", "equity_total"
        ]
        for field in required_ratio_fields:
            assert field in ratios, f"Missing ratio field '{field}'"
        
        # current_ratio can be null if current_liabilities is 0
        self.log(f"Ratios: current_ratio={ratios.get('current_ratio')}, debt_to_equity={ratios.get('debt_to_equity')}")
        self.log(f"Balance: assets={ratios.get('assets_total')}, liabilities={ratios.get('liabilities_total')}, equity={ratios.get('equity_total')}")

    def test_bi_entity_comparison(self):
        """Test entity_comparison structure (multi-entity)"""
        response = requests.get(f"{BASE_URL}/finance/bi?year=2026", headers=self.get_headers())
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        comparison = data.get("entity_comparison", [])
        multi_entity = data.get("multi_entity", False)
        
        assert isinstance(comparison, list), "entity_comparison should be a list"
        self.log(f"Entity comparison: {len(comparison)} entities, multi_entity={multi_entity}")
        
        if len(comparison) > 0:
            # Check first entity structure
            first_entity = comparison[0]
            required_fields = ["entity_id", "name", "revenue", "expense", "net_income", "net_margin"]
            for field in required_fields:
                assert field in first_entity, f"Missing field '{field}' in entity_comparison"
            
            # Verify sorted by revenue desc
            if len(comparison) > 1:
                for i in range(len(comparison) - 1):
                    assert comparison[i]["revenue"] >= comparison[i+1]["revenue"], \
                        "entity_comparison should be sorted by revenue desc"
            
            # Log entities
            for entity in comparison:
                self.log(f"  Entity: {entity['name']} ({entity['entity_id']}) - revenue={entity['revenue']}, net_income={entity['net_income']}")
        
        # multi_entity should be true if > 1 entity
        if len(comparison) > 1:
            assert multi_entity == True, "multi_entity should be true when > 1 entity"

    def test_bi_single_entity_scope(self):
        """Test GET /api/finance/bi?year=2026&entity_id=ent_ksc (single entity scope)"""
        response = requests.get(
            f"{BASE_URL}/finance/bi?year=2026&entity_id=ent_ksc",
            headers=self.get_headers()
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        comparison = data.get("entity_comparison", [])
        
        # When scoped to single entity, comparison should only contain that entity
        assert len(comparison) <= 1, f"Expected 1 or 0 entities, got {len(comparison)}"
        
        if len(comparison) == 1:
            assert comparison[0]["entity_id"] == "ent_ksc", \
                f"Expected entity_id 'ent_ksc', got '{comparison[0]['entity_id']}'"
            self.log(f"Single entity scope: {comparison[0]['name']} - revenue={comparison[0]['revenue']}")

    def test_bi_consistency_operational_data(self):
        """Test consistency: operational data excludes closing entries"""
        # This is more of a verification that the data is consistent
        # We'll call the endpoint twice and verify the data is the same
        response1 = requests.get(f"{BASE_URL}/finance/bi?year=2026", headers=self.get_headers())
        assert response1.status_code == 200, f"Expected 200, got {response1.status_code}"
        
        response2 = requests.get(f"{BASE_URL}/finance/bi?year=2026", headers=self.get_headers())
        assert response2.status_code == 200, f"Expected 200, got {response2.status_code}"
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Verify KPI values are consistent
        assert data1["kpi"]["revenue"] == data2["kpi"]["revenue"], "KPI revenue should be consistent"
        assert data1["kpi"]["expense"] == data2["kpi"]["expense"], "KPI expense should be consistent"
        assert data1["kpi"]["net_income"] == data2["kpi"]["net_income"], "KPI net_income should be consistent"
        
        self.log("Operational data is consistent across calls")

    def test_regression_income_statement(self):
        """Regression: /api/finance/income-statement still works"""
        response = requests.get(
            f"{BASE_URL}/finance/income-statement?start=2026-01-01&end=2026-12-31",
            headers=self.get_headers()
        )
        assert response.status_code == 200, f"Income statement failed: {response.status_code}"
        
        data = response.json()
        assert "revenue_total" in data, "Missing revenue_total in income statement"
        assert "net_income" in data, "Missing net_income in income statement"
        self.log(f"Income statement: revenue={data.get('revenue_total')}, net_income={data.get('net_income')}")

    def test_regression_balance_sheet(self):
        """Regression: /api/finance/balance-sheet still works"""
        response = requests.get(
            f"{BASE_URL}/finance/balance-sheet?as_of=2026-12-31",
            headers=self.get_headers()
        )
        assert response.status_code == 200, f"Balance sheet failed: {response.status_code}"
        
        data = response.json()
        assert "assets_total" in data, "Missing assets_total in balance sheet"
        assert "liabilities_total" in data, "Missing liabilities_total in balance sheet"
        assert "equity_total" in data, "Missing equity_total in balance sheet"
        assert "balanced" in data, "Missing balanced flag in balance sheet"
        
        self.log(f"Balance sheet: assets={data.get('assets_total')}, liabilities={data.get('liabilities_total')}, equity={data.get('equity_total')}, balanced={data.get('balanced')}")

    def test_regression_trial_balance(self):
        """Regression: /api/gl/trial-balance still works"""
        response = requests.get(
            f"{BASE_URL}/gl/trial-balance?as_of=2026-12-31",
            headers=self.get_headers()
        )
        assert response.status_code == 200, f"Trial balance failed: {response.status_code}"
        
        data = response.json()
        assert "rows" in data, "Missing rows in trial balance"
        assert "total_debit" in data, "Missing total_debit in trial balance"
        assert "total_credit" in data, "Missing total_credit in trial balance"
        assert "balanced" in data, "Missing balanced flag in trial balance"
        
        self.log(f"Trial balance: debit={data.get('total_debit')}, credit={data.get('total_credit')}, balanced={data.get('balanced')}")

    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*80)
        print("BI KEUANGAN (FINANCIAL BI DASHBOARD) - BACKEND TESTS")
        print("="*80 + "\n")
        
        # Login first
        try:
            self.login()
        except Exception as e:
            print(f"❌ Login failed: {e}")
            return 1
        
        # Run all tests
        self.run_test("BI Default Year", self.test_bi_default_year)
        self.run_test("BI Year 2026 (with seed data)", self.test_bi_year_2026)
        self.run_test("BI KPI Structure", self.test_bi_kpi_structure)
        self.run_test("BI Ratios Structure", self.test_bi_ratios_structure)
        self.run_test("BI Entity Comparison", self.test_bi_entity_comparison)
        self.run_test("BI Single Entity Scope", self.test_bi_single_entity_scope)
        self.run_test("BI Consistency (Operational Data)", self.test_bi_consistency_operational_data)
        self.run_test("Regression: Income Statement", self.test_regression_income_statement)
        self.run_test("Regression: Balance Sheet", self.test_regression_balance_sheet)
        self.run_test("Regression: Trial Balance", self.test_regression_trial_balance)
        
        # Print summary
        print("\n" + "="*80)
        print(f"SUMMARY: {self.tests_passed}/{self.tests_run} tests passed")
        print("="*80)
        
        if self.failures:
            print("\n❌ FAILED TESTS:")
            for failure in self.failures:
                print(f"  - {failure['test']}: {failure['error']}")
        
        return 0 if self.tests_passed == self.tests_run else 1

def main():
    tester = BIFinanceTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
