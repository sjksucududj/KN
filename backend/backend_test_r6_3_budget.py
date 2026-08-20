"""
R6.3 Budget Control — Comprehensive Backend API Test
Tests: Budget CRUD, Budget vs Actual Report, Budget Rules, PO Enforcement, RBAC
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://po-budget-warn.preview.emergentagent.com/api"

# Test credentials from test_credentials.md
CREDS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "manager": {"email": "manager@kainnusantara.id", "password": "demo12345"},
    "sales": {"email": "sales@kainnusantara.id", "password": "demo12345"},
    "warehouse": {"email": "warehouse@kainnusantara.id", "password": "demo12345"},
}

class BudgetTester:
    def __init__(self):
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.created_budget_ids = []
        self.created_po_ids = []
        self.original_rules = None

    def log(self, msg, status="info"):
        prefix = {"info": "ℹ️", "pass": "✅", "fail": "❌", "warn": "⚠️"}
        print(f"{prefix.get(status, 'ℹ️')} {msg}")

    def test(self, name, method, endpoint, expected_status, role="admin", data=None, params=None):
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        
        if role and role in self.tokens:
            headers["Authorization"] = f"Bearer {self.tokens[role]}"
        
        self.log(f"Testing [{role}] {name}...", "info")
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == "PATCH":
                response = requests.patch(url, json=data, headers=headers, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=10)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=headers, timeout=10)
            else:
                self.log(f"Unknown method {method}", "fail")
                return False, {}

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"PASSED - Status: {response.status_code}", "pass")
            else:
                self.log(f"FAILED - Expected {expected_status}, got {response.status_code}", "fail")
                if response.status_code >= 400:
                    try:
                        self.log(f"  Error: {response.json()}", "fail")
                    except Exception:
                        self.log(f"  Response: {response.text[:200]}", "fail")

            try:
                return success, response.json() if response.text else {}
            except Exception:
                return success, {}

        except Exception as e:
            self.log(f"FAILED - Exception: {str(e)}", "fail")
            return False, {}

    def login_all(self):
        """Login all test users"""
        self.log("=== PHASE 1: Authentication ===", "info")
        for role, creds in CREDS.items():
            success, resp = self.test(
                f"Login as {role}",
                "POST",
                "auth/login",
                200,
                role=None,
                data=creds
            )
            if success and "token" in resp:
                self.tokens[role] = resp["token"]
                self.log(f"  Token obtained for {role}", "pass")
            else:
                self.log(f"  Failed to get token for {role}", "fail")
                return False
        return True

    def test_budget_crud(self):
        """Test Budget CRUD operations"""
        self.log("\n=== PHASE 2: Budget CRUD ===", "info")
        
        # Get budget keys first
        success, keys = self.test(
            "Get budget keys",
            "GET",
            "finance/budget-keys",
            200,
            role="admin"
        )
        if not success or not keys.get("accounts"):
            self.log("Failed to get budget keys", "fail")
            return False
        
        test_account = keys["accounts"][0]["code"] if keys["accounts"] else "5-1100"
        test_category = keys["categories"][0]["code"] if keys["categories"] else "TRANSPORT"
        
        # Create budget (account dimension)
        success, budget1 = self.test(
            "Create budget (account dimension)",
            "POST",
            "finance/budgets",
            200,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "year": 2026,
                "month": 0,
                "dimension": "account",
                "key": test_account,
                "amount": 50000000,
                "note": "Test budget R6.3"
            }
        )
        if success and budget1.get("id"):
            self.created_budget_ids.append(budget1["id"])
        
        # Create budget (category dimension)
        success, budget2 = self.test(
            "Create budget (category dimension)",
            "POST",
            "finance/budgets",
            200,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "year": 2026,
                "month": 1,
                "dimension": "category",
                "key": test_category,
                "amount": 10000000,
                "note": "Test category budget"
            }
        )
        if success and budget2.get("id"):
            self.created_budget_ids.append(budget2["id"])
        
        # Test duplicate rejection
        self.test(
            "Reject duplicate budget",
            "POST",
            "finance/budgets",
            400,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "year": 2026,
                "month": 0,
                "dimension": "account",
                "key": test_account,
                "amount": 10000000
            }
        )
        
        # Test invalid key rejection
        self.test(
            "Reject unknown account key",
            "POST",
            "finance/budgets",
            400,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "year": 2026,
                "month": 0,
                "dimension": "account",
                "key": "INVALID-9999",
                "amount": 10000000
            }
        )
        
        # Test amount <= 0 rejection
        self.test(
            "Reject amount <= 0",
            "POST",
            "finance/budgets",
            400,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "year": 2026,
                "month": 0,
                "dimension": "account",
                "key": test_account,
                "amount": 0
            }
        )
        
        # List budgets
        success, budgets = self.test(
            "List budgets",
            "GET",
            "finance/budgets",
            200,
            role="admin",
            params={"year": 2026}
        )
        
        # Update budget
        if self.created_budget_ids:
            self.test(
                "Update budget amount",
                "PATCH",
                f"finance/budgets/{self.created_budget_ids[0]}",
                200,
                role="admin",
                data={"amount": 60000000}
            )
        
        return True

    def test_budget_report(self):
        """Test Budget vs Actual Report"""
        self.log("\n=== PHASE 3: Budget vs Actual Report ===", "info")
        
        success, report = self.test(
            "Get budget vs actual report",
            "GET",
            "finance/budget-vs-actual",
            200,
            role="admin",
            params={"year": 2026, "entity_id": "ent_ksc"}
        )
        
        if not success:
            return False
        
        # Verify report structure
        required_keys = ["rows", "totals", "by_dimension", "alerts", "unbudgeted_commitments", "rules"]
        for key in required_keys:
            if key not in report:
                self.log(f"Missing key in report: {key}", "fail")
                self.tests_run += 1
            else:
                self.log(f"Report has {key}", "pass")
                self.tests_run += 1
                self.tests_passed += 1
        
        # Verify totals consistency
        totals = report.get("totals", {})
        rows = report.get("rows", [])
        
        if rows:
            sum_budget = sum(r.get("budget", 0) for r in rows)
            sum_committed = sum(r.get("committed", 0) for r in rows)
            sum_actual = sum(r.get("actual", 0) for r in rows)
            
            self.tests_run += 3
            if abs(sum_budget - totals.get("budget", 0)) < 0.01:
                self.log(f"Totals consistent: budget {totals.get('budget')}", "pass")
                self.tests_passed += 1
            else:
                self.log(f"Totals mismatch: sum={sum_budget}, total={totals.get('budget')}", "fail")
            
            if abs(sum_committed - totals.get("committed", 0)) < 0.01:
                self.log(f"Totals consistent: committed {totals.get('committed')}", "pass")
                self.tests_passed += 1
            else:
                self.log(f"Totals mismatch: sum={sum_committed}, total={totals.get('committed')}", "fail")
            
            if abs(sum_actual - totals.get("actual", 0)) < 0.01:
                self.log(f"Totals consistent: actual {totals.get('actual')}", "pass")
                self.tests_passed += 1
            else:
                self.log(f"Totals mismatch: sum={sum_actual}, total={totals.get('actual')}", "fail")
        
        return True

    def test_budget_rules(self):
        """Test Budget Rules"""
        self.log("\n=== PHASE 4: Budget Rules ===", "info")
        
        # Get current rules (save for restoration)
        success, rules = self.test(
            "Get budget rules",
            "GET",
            "finance/budget-rules",
            200,
            role="admin",
            params={"entity_id": "ent_ksc"}
        )
        if success:
            self.original_rules = rules
            self.log(f"  Current mode: {rules.get('mode')}", "info")
        
        # Test invalid mode rejection
        self.test(
            "Reject invalid mode",
            "PUT",
            "finance/budget-rules",
            400,
            role="admin",
            data={"entity_id": "ent_ksc", "mode": "invalid_mode"}
        )
        
        # Test invalid threshold rejection
        self.test(
            "Reject invalid threshold (>100)",
            "PUT",
            "finance/budget-rules",
            400,
            role="admin",
            data={"entity_id": "ent_ksc", "warn_threshold_pct": 150}
        )
        
        # Test manager cannot configure (403)
        self.test(
            "Manager cannot configure rules (403)",
            "PUT",
            "finance/budget-rules",
            403,
            role="manager",
            data={"entity_id": "ent_ksc", "mode": "warn"}
        )
        
        # Admin can set rules
        self.test(
            "Admin can set rules",
            "PUT",
            "finance/budget-rules",
            200,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "mode": "warn",
                "warn_threshold_pct": 85,
                "unbudgeted_action": "allow"
            }
        )
        
        return True

    def test_budget_check(self):
        """Test Budget Check endpoint"""
        self.log("\n=== PHASE 5: Budget Check ===", "info")
        
        success, check = self.test(
            "Check budget availability",
            "POST",
            "finance/budget-check",
            200,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "dimension": "account",
                "key": "1-1300",
                "amount": 5000000,
                "date": "2026-01-15"
            }
        )
        
        if success:
            required = ["has_budget", "budget", "actual", "committed", "available", "available_after"]
            for key in required:
                if key in check:
                    self.log(f"  Check has {key}: {check[key]}", "pass")
                else:
                    self.log(f"  Missing {key} in check", "fail")
        
        return True

    def test_po_enforcement(self):
        """Test PO Budget Enforcement"""
        self.log("\n=== PHASE 6: PO Budget Enforcement ===", "info")
        
        # Get suppliers and warehouses
        success, suppliers = self.test(
            "Get suppliers",
            "GET",
            "suppliers",
            200,
            role="admin"
        )
        
        success, warehouses = self.test(
            "Get warehouses",
            "GET",
            "warehouses",
            200,
            role="admin"
        )
        
        success, products = self.test(
            "Get products",
            "GET",
            "products",
            200,
            role="admin"
        )
        
        if not suppliers or not warehouses or not products:
            self.log("Cannot test PO enforcement - missing data", "warn")
            return True
        
        supplier_id = suppliers[0]["id"] if suppliers else None
        warehouse_id = warehouses[0]["id"] if warehouses else None
        product_id = products[0]["id"] if products else None
        
        if not all([supplier_id, warehouse_id, product_id]):
            self.log("Cannot test PO enforcement - missing IDs", "warn")
            return True
        
        # Test 1: mode=warn allows PO with warnings
        self.test(
            "Set rules to mode=warn",
            "PUT",
            "finance/budget-rules",
            200,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "mode": "warn",
                "warn_threshold_pct": 85,
                "unbudgeted_action": "allow"
            }
        )
        
        success, po_warn = self.test(
            "Create PO with mode=warn (should succeed)",
            "POST",
            "purchase-orders",
            200,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "supplier_id": supplier_id,
                "warehouse_id": warehouse_id,
                "items": [{
                    "product_id": product_id,
                    "quantity": 10,
                    "unit": "meter",
                    "price": 50000
                }],
                "expected_delivery_date": "2026-02-01",
                "notes": "Test PO warn mode",
                "budget_dimension": "account",
                "budget_key": "1-1300"
            }
        )
        if success and po_warn.get("id"):
            self.created_po_ids.append(po_warn["id"])
            if po_warn.get("budget_check", {}).get("warnings"):
                self.log(f"  PO has budget warnings: {po_warn['budget_check']['warnings']}", "pass")
        
        # Test 2: mode=block rejects over-budget PO
        # First create a budget with small amount
        success, small_budget = self.test(
            "Create small budget for block test",
            "POST",
            "finance/budgets",
            200,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "year": 2026,
                "month": 0,
                "dimension": "account",
                "key": "5-2100",  # Different account for testing
                "amount": 100000,  # Very small budget
                "note": "Small budget for block test"
            }
        )
        if success and small_budget.get("id"):
            self.created_budget_ids.append(small_budget["id"])
        
        self.test(
            "Set rules to mode=block",
            "PUT",
            "finance/budget-rules",
            200,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "mode": "block",
                "warn_threshold_pct": 85,
                "unbudgeted_action": "allow"
            }
        )
        
        self.test(
            "Create over-budget PO with mode=block (should fail 400)",
            "POST",
            "purchase-orders",
            400,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "supplier_id": supplier_id,
                "warehouse_id": warehouse_id,
                "items": [{
                    "product_id": product_id,
                    "quantity": 100,
                    "unit": "meter",
                    "price": 50000  # 5M total, exceeds 100k budget
                }],
                "expected_delivery_date": "2026-02-01",
                "notes": "Test PO block mode",
                "budget_dimension": "account",
                "budget_key": "5-2100"
            }
        )
        
        # Test 3: mode=off skips check
        self.test(
            "Set rules to mode=off",
            "PUT",
            "finance/budget-rules",
            200,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "mode": "off"
            }
        )
        
        success, po_off = self.test(
            "Create PO with mode=off (should succeed)",
            "POST",
            "purchase-orders",
            200,
            role="admin",
            data={
                "entity_id": "ent_ksc",
                "supplier_id": supplier_id,
                "warehouse_id": warehouse_id,
                "items": [{
                    "product_id": product_id,
                    "quantity": 10,
                    "unit": "meter",
                    "price": 50000
                }],
                "expected_delivery_date": "2026-02-01",
                "notes": "Test PO off mode"
            }
        )
        if success and po_off.get("id"):
            self.created_po_ids.append(po_off["id"])
            if po_off.get("budget_check", {}).get("skipped"):
                self.log("  Budget check skipped (mode=off)", "pass")
        
        return True

    def test_rbac(self):
        """Test RBAC - sales and warehouse should get 403"""
        self.log("\n=== PHASE 7: RBAC ===", "info")
        
        # Sales cannot access budget endpoints
        self.test(
            "Sales cannot list budgets (403)",
            "GET",
            "finance/budgets",
            403,
            role="sales"
        )
        
        self.test(
            "Sales cannot get budget report (403)",
            "GET",
            "finance/budget-vs-actual",
            403,
            role="sales",
            params={"year": 2026}
        )
        
        self.test(
            "Sales cannot get budget rules (403)",
            "GET",
            "finance/budget-rules",
            403,
            role="sales"
        )
        
        # Warehouse cannot access budget endpoints
        self.test(
            "Warehouse cannot list budgets (403)",
            "GET",
            "finance/budgets",
            403,
            role="warehouse"
        )
        
        self.test(
            "Warehouse cannot get budget report (403)",
            "GET",
            "finance/budget-vs-actual",
            403,
            role="warehouse",
            params={"year": 2026}
        )
        
        # Manager can view but not configure
        self.test(
            "Manager can list budgets",
            "GET",
            "finance/budgets",
            200,
            role="manager"
        )
        
        self.test(
            "Manager can get budget report",
            "GET",
            "finance/budget-vs-actual",
            200,
            role="manager",
            params={"year": 2026}
        )
        
        return True

    def cleanup(self):
        """Clean up test data and restore original rules"""
        self.log("\n=== CLEANUP ===", "info")
        
        # Restore original rules (CRITICAL: reset to mode=warn)
        if self.original_rules:
            self.log("Restoring original budget rules...", "info")
            self.test(
                "Restore budget rules to mode=warn",
                "PUT",
                "finance/budget-rules",
                200,
                role="admin",
                data={
                    "entity_id": "ent_ksc",
                    "mode": "warn",
                    "warn_threshold_pct": 85,
                    "unbudgeted_action": "allow"
                }
            )
        
        # Delete test budgets
        for budget_id in self.created_budget_ids:
            self.log(f"Deleting test budget {budget_id}...", "info")
            self.test(
                f"Delete budget {budget_id}",
                "DELETE",
                f"finance/budgets/{budget_id}",
                200,
                role="admin"
            )
        
        self.log("Cleanup complete", "pass")

    def run_all(self):
        """Run all tests"""
        self.log("=" * 60, "info")
        self.log("R6.3 Budget Control — Backend API Test", "info")
        self.log("=" * 60, "info")
        
        if not self.login_all():
            self.log("Authentication failed, stopping tests", "fail")
            return 1
        
        self.test_budget_crud()
        self.test_budget_report()
        self.test_budget_rules()
        self.test_budget_check()
        self.test_po_enforcement()
        self.test_rbac()
        
        self.cleanup()
        
        # Summary
        self.log("\n" + "=" * 60, "info")
        self.log(f"SUMMARY: {self.tests_passed}/{self.tests_run} tests passed", 
                 "pass" if self.tests_passed == self.tests_run else "fail")
        self.log("=" * 60, "info")
        
        return 0 if self.tests_passed == self.tests_run else 1


if __name__ == "__main__":
    tester = BudgetTester()
    sys.exit(tester.run_all())
