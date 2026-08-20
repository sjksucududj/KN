#!/usr/bin/env python3
"""Backend test for Finance & Accounting Analytics Suite (5 features).

Tests:
1. Cash Flow Statement + CSV export
2. Profitability (WAC)
3. Cash Flow Forecast
4. Finance Control Tower
5. Budget vs Actual + CRUD

Login: admin@kainnusantara.id / demo12345
Token field: 'token' (NOT access_token)
"""
import requests
import sys
from datetime import datetime, date
from typing import Dict, Any, Optional

BASE_URL = "https://kn123-backend-fixes.preview.emergentagent.com"
ADMIN_EMAIL = "admin@kainnusantara.id"
ADMIN_PASSWORD = "demo12345"
ENTITY_ID = "ent_ksc"


class FinanceAnalyticsTest:
    def __init__(self):
        self.token: Optional[str] = None
        self.tests_run = 0
        self.tests_passed = 0
        self.budget_id: Optional[str] = None

    def log(self, msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def test(self, name: str, func):
        """Run a test function."""
        self.tests_run += 1
        self.log(f"\n{'='*60}")
        self.log(f"TEST {self.tests_run}: {name}")
        self.log('='*60)
        try:
            func()
            self.tests_passed += 1
            self.log(f"✅ PASSED: {name}")
            return True
        except AssertionError as e:
            self.log(f"❌ FAILED: {name}")
            self.log(f"   Error: {str(e)}")
            return False
        except Exception as e:
            self.log(f"❌ ERROR: {name}")
            self.log(f"   Exception: {str(e)}")
            return False

    def login(self):
        """Login and get token."""
        self.log("Logging in as admin...")
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "token" in data, f"Token field missing in response: {data.keys()}"
        self.token = data["token"]
        self.log(f"✅ Login successful, token: {self.token[:20]}...")

    def headers(self) -> Dict[str, str]:
        """Get auth headers."""
        return {"Authorization": f"Bearer {self.token}"}

    # =========================================================================
    # FEATURE 1: Cash Flow Statement
    # =========================================================================
    def test_cash_flow_statement(self):
        """Test GET /api/finance/cash-flow."""
        today = date.today().isoformat()
        url = f"{BASE_URL}/api/finance/cash-flow"
        params = {
            "entity_id": ENTITY_ID,
            "start": "2026-01-01",
            "end": today
        }
        resp = requests.get(url, params=params, headers=self.headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        self.log(f"Cash Flow response keys: {list(data.keys())}")
        
        # Verify required keys
        required_keys = [
            "operating", "investing", "financing", 
            "net_change", "begin_cash", "end_cash", "end_cash_actual", "reconciled"
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"
        
        # Verify operating section
        op = data["operating"]
        assert "net_income" in op, "Missing net_income in operating"
        assert "working_capital" in op, "Missing working_capital in operating"
        assert "total" in op, "Missing total in operating"
        assert isinstance(op["working_capital"], list), "working_capital should be a list"
        
        # Verify investing section
        inv = data["investing"]
        assert "lines" in inv, "Missing lines in investing"
        assert "total" in inv, "Missing total in investing"
        assert isinstance(inv["lines"], list), "investing lines should be a list"
        
        # Verify financing section
        fin = data["financing"]
        assert "lines" in fin, "Missing lines in financing"
        assert "total" in fin, "Missing total in financing"
        assert isinstance(fin["lines"], list), "financing lines should be a list"
        
        # CRITICAL: Verify reconciliation
        reconciled = data["reconciled"]
        self.log(f"Reconciliation status: {reconciled}")
        self.log(f"begin_cash: {data['begin_cash']}, net_change: {data['net_change']}, end_cash_actual: {data['end_cash_actual']}")
        assert reconciled is True, f"Cash flow MUST be reconciled! reconciled={reconciled}"
        
        self.log(f"✅ Cash flow reconciled: begin_cash + net_change ≈ end_cash_actual")

    def test_cash_flow_csv_export(self):
        """Test GET /api/finance/cash-flow/export.csv."""
        today = date.today().isoformat()
        url = f"{BASE_URL}/api/finance/cash-flow/export.csv"
        params = {
            "entity_id": ENTITY_ID,
            "start": "2026-01-01",
            "end": today
        }
        resp = requests.get(url, params=params, headers=self.headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", ""), "Response should be CSV"
        assert len(resp.text) > 0, "CSV export should not be empty"
        self.log(f"✅ CSV export returned {len(resp.text)} bytes")

    # =========================================================================
    # FEATURE 2: Profitability (WAC)
    # =========================================================================
    def test_profitability(self):
        """Test GET /api/finance/profitability."""
        url = f"{BASE_URL}/api/finance/profitability"
        params = {"entity_id": ENTITY_ID}
        resp = requests.get(url, params=params, headers=self.headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        self.log(f"Profitability response keys: {list(data.keys())}")
        
        # Verify required dimensions
        required_dims = ["by_product", "by_category", "by_customer", "by_sales"]
        for dim in required_dims:
            assert dim in data, f"Missing dimension: {dim}"
            assert isinstance(data[dim], list), f"{dim} should be a list"
        
        # Verify totals
        assert "totals" in data, "Missing totals"
        totals = data["totals"]
        assert "revenue" in totals, "Missing revenue in totals"
        assert "cogs" in totals, "Missing cogs in totals"
        assert "margin" in totals, "Missing margin in totals"
        assert "margin_pct" in totals, "Missing margin_pct in totals"
        
        # Verify cost_basis
        assert "cost_basis" in data, "Missing cost_basis"
        assert data["cost_basis"] == "WAC", f"cost_basis should be WAC, got {data['cost_basis']}"
        
        # Verify monthly trend
        assert "monthly" in data, "Missing monthly"
        assert isinstance(data["monthly"], list), "monthly should be a list"
        
        # Verify margin calculation
        revenue = totals["revenue"]
        cogs = totals["cogs"]
        margin = totals["margin"]
        expected_margin = round(revenue - cogs, 2)
        assert margin == expected_margin, f"margin mismatch: {margin} != {expected_margin}"
        assert revenue > 0, "Revenue should be > 0"
        
        self.log(f"✅ Profitability: revenue={revenue}, cogs={cogs}, margin={margin}")
        
        # Verify row structure in one dimension
        if data["by_product"]:
            row = data["by_product"][0]
            required_row_keys = ["key", "name", "revenue", "cogs", "margin", "margin_pct", "qty", "orders"]
            for key in required_row_keys:
                assert key in row, f"Missing key in by_product row: {key}"

    # =========================================================================
    # FEATURE 3: Cash Flow Forecast
    # =========================================================================
    def test_cashflow_forecast(self):
        """Test GET /api/finance/cashflow-forecast."""
        url = f"{BASE_URL}/api/finance/cashflow-forecast"
        params = {"entity_id": ENTITY_ID}
        resp = requests.get(url, params=params, headers=self.headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        self.log(f"Cashflow forecast response keys: {list(data.keys())}")
        
        # Verify required keys
        required_keys = [
            "cash_now", "projected_cash", "buckets",
            "total_inflow", "total_outflow", "ar_items", "ap_items"
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"
        
        # Verify exactly 5 buckets
        buckets = data["buckets"]
        assert isinstance(buckets, list), "buckets should be a list"
        assert len(buckets) == 5, f"Expected exactly 5 buckets, got {len(buckets)}"
        
        # Verify bucket structure
        for i, bucket in enumerate(buckets):
            required_bucket_keys = ["label", "inflow", "outflow", "net", "cumulative_cash"]
            for key in required_bucket_keys:
                assert key in bucket, f"Missing key in bucket {i}: {key}"
        
        # Verify AR/AP items
        assert isinstance(data["ar_items"], list), "ar_items should be a list"
        assert isinstance(data["ap_items"], list), "ap_items should be a list"
        
        self.log(f"✅ Forecast: cash_now={data['cash_now']}, projected={data['projected_cash']}, buckets={len(buckets)}")

    # =========================================================================
    # FEATURE 4: Finance Control Tower
    # =========================================================================
    def test_finance_tower(self):
        """Test GET /api/finance/tower."""
        url = f"{BASE_URL}/api/finance/tower"
        params = {"entity_id": ENTITY_ID}
        resp = requests.get(url, params=params, headers=self.headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        self.log(f"Finance tower response keys: {list(data.keys())}")
        
        # Verify required sections
        required_keys = ["cash", "ar", "ap", "working_capital", "pl", "ratios"]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"
        
        # Verify cash section
        cash = data["cash"]
        assert "total" in cash, "Missing total in cash"
        assert "accounts" in cash, "Missing accounts in cash"
        assert isinstance(cash["accounts"], list), "cash accounts should be a list"
        
        # Verify AR section
        ar = data["ar"]
        assert "outstanding" in ar, "Missing outstanding in ar"
        assert "overdue" in ar, "Missing overdue in ar"
        assert "aging" in ar, "Missing aging in ar"
        assert "top" in ar, "Missing top in ar"
        assert isinstance(ar["top"], list), "ar top should be a list"
        
        # Verify AP section
        ap = data["ap"]
        assert "outstanding" in ap, "Missing outstanding in ap"
        assert "aging" in ap, "Missing aging in ap"
        assert "top" in ap, "Missing top in ap"
        assert isinstance(ap["top"], list), "ap top should be a list"
        
        # Verify P&L section
        pl = data["pl"]
        assert "mtd" in pl, "Missing mtd in pl"
        assert "ytd" in pl, "Missing ytd in pl"
        
        # Verify monthly trend (at top level, not inside pl)
        assert "monthly" in data, "Missing monthly"
        monthly = data["monthly"]
        assert isinstance(monthly, list), "monthly should be a list"
        assert len(monthly) == 12, f"Expected 12 monthly points, got {len(monthly)}"
        
        # Verify ratios
        ratios = data["ratios"]
        assert isinstance(ratios, dict), "ratios should be a dict"
        
        self.log(f"✅ Tower: cash={cash['total']}, ar_outstanding={ar['outstanding']}, ap_outstanding={ap['outstanding']}")

    def test_finance_tower_auth(self):
        """Test GET /api/finance/tower WITHOUT auth token → MUST be 401/403."""
        url = f"{BASE_URL}/api/finance/tower"
        params = {"entity_id": ENTITY_ID}
        resp = requests.get(url, params=params)  # No auth header
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"
        self.log(f"✅ Auth check: got {resp.status_code} without token")

    # =========================================================================
    # FEATURE 5: Budget vs Actual + CRUD
    # =========================================================================
    def test_budget_create(self):
        """Test POST /api/finance/budgets."""
        url = f"{BASE_URL}/api/finance/budgets"
        payload = {
            "entity_id": ENTITY_ID,
            "year": 2026,
            "month": 0,  # Annual budget
            "account_code": "4-1000",
            "amount": 500000000,
            "note": "test budget"
        }
        resp = requests.post(url, json=payload, headers=self.headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "id" in data, "Response should contain id"
        self.budget_id = data["id"]
        self.log(f"✅ Budget created: id={self.budget_id}")

    def test_budget_list(self):
        """Test GET /api/finance/budgets."""
        url = f"{BASE_URL}/api/finance/budgets"
        params = {"year": 2026, "entity_id": ENTITY_ID}
        resp = requests.get(url, params=params, headers=self.headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Find our created budget
        found = False
        for budget in data:
            if budget.get("id") == self.budget_id:
                found = True
                assert budget["account_code"] == "4-1000", "account_code mismatch"
                assert budget["amount"] == 500000000, "amount mismatch"
                break
        
        assert found, f"Created budget {self.budget_id} not found in list"
        self.log(f"✅ Budget found in list: {len(data)} budgets total")

    def test_budget_vs_actual(self):
        """Test GET /api/finance/budget-vs-actual."""
        url = f"{BASE_URL}/api/finance/budget-vs-actual"
        params = {"year": 2026, "entity_id": ENTITY_ID}
        resp = requests.get(url, params=params, headers=self.headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        self.log(f"Budget vs actual response keys: {list(data.keys())}")
        
        # Verify required keys
        assert "rows" in data, "Missing rows"
        assert "totals" in data, "Missing totals"
        
        rows = data["rows"]
        assert isinstance(rows, list), "rows should be a list"
        
        # Verify row structure
        if rows:
            row = rows[0]
            required_row_keys = [
                "account_code", "account_name", "budget", "actual", 
                "variance", "used_pct", "status"
            ]
            for key in required_row_keys:
                assert key in row, f"Missing key in row: {key}"
            
            # Verify variance calculation
            variance = row["variance"]
            expected_variance = round(row["budget"] - row["actual"], 2)
            assert variance == expected_variance, f"variance mismatch: {variance} != {expected_variance}"
        
        # Verify totals
        totals = data["totals"]
        assert "budget" in totals, "Missing budget in totals"
        assert "actual" in totals, "Missing actual in totals"
        assert "variance" in totals, "Missing variance in totals"
        assert "commitment" in totals, "Missing commitment in totals"
        
        self.log(f"✅ Budget vs actual: {len(rows)} rows, totals={totals}")

    def test_budget_update(self):
        """Test PATCH /api/finance/budgets/{id}."""
        assert self.budget_id, "Budget ID not set"
        url = f"{BASE_URL}/api/finance/budgets/{self.budget_id}"
        payload = {"amount": 600000000}
        resp = requests.patch(url, json=payload, headers=self.headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert data["amount"] == 600000000, f"Amount not updated: {data['amount']}"
        self.log(f"✅ Budget updated: amount=600000000")

    def test_budget_delete(self):
        """Test DELETE /api/finance/budgets/{id}."""
        assert self.budget_id, "Budget ID not set"
        url = f"{BASE_URL}/api/finance/budgets/{self.budget_id}"
        resp = requests.delete(url, headers=self.headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert data.get("ok") is True, "Delete should return ok=True"
        self.log(f"✅ Budget deleted: {self.budget_id}")

    # =========================================================================
    # MAIN TEST RUNNER
    # =========================================================================
    def run_all(self):
        """Run all tests."""
        self.log("="*60)
        self.log("FINANCE & ACCOUNTING ANALYTICS SUITE - BACKEND TESTS")
        self.log("="*60)
        
        # Login first
        try:
            self.login()
        except Exception as e:
            self.log(f"❌ Login failed: {e}")
            return 1
        
        # Feature 1: Cash Flow Statement
        self.test("Cash Flow Statement", self.test_cash_flow_statement)
        self.test("Cash Flow CSV Export", self.test_cash_flow_csv_export)
        
        # Feature 2: Profitability
        self.test("Profitability (WAC)", self.test_profitability)
        
        # Feature 3: Cash Flow Forecast
        self.test("Cash Flow Forecast", self.test_cashflow_forecast)
        
        # Feature 4: Finance Control Tower
        self.test("Finance Control Tower", self.test_finance_tower)
        self.test("Finance Tower Auth Check", self.test_finance_tower_auth)
        
        # Feature 5: Budget CRUD
        self.test("Budget Create", self.test_budget_create)
        self.test("Budget List", self.test_budget_list)
        self.test("Budget vs Actual", self.test_budget_vs_actual)
        self.test("Budget Update", self.test_budget_update)
        self.test("Budget Delete", self.test_budget_delete)
        
        # Summary
        self.log("\n" + "="*60)
        self.log(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        self.log("="*60)
        
        return 0 if self.tests_passed == self.tests_run else 1


if __name__ == "__main__":
    tester = FinanceAnalyticsTest()
    sys.exit(tester.run_all())
