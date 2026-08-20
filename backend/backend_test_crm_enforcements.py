"""
Backend test for KN_17 CRM Enforcements + Incentive/Tier Schema UI Editor.
Tests credit gate, collection reminders, sales force KPI/commission, and incentive scheme editor.
"""
import requests
import sys
import os
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = os.getenv("REACT_APP_BACKEND_URL", "https://po-pdf-sender.preview.emergentagent.com")
API_BASE = f"{BACKEND_URL}/api"

class CRMEnforcementsTest:
    def __init__(self):
        self.admin_token = None
        self.manager_token = None
        self.sales_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_customer_id = None
        self.test_sales_id = None
        self.test_order_id = None

    def log(self, message, status="INFO"):
        """Log test messages"""
        symbols = {"PASS": "✅", "FAIL": "❌", "INFO": "🔍", "WARN": "⚠️"}
        print(f"{symbols.get(status, '•')} {message}")

    def run_test(self, name, test_func):
        """Run a single test"""
        self.tests_run += 1
        self.log(f"Testing {name}...", "INFO")
        try:
            test_func()
            self.tests_passed += 1
            self.log(f"PASSED - {name}", "PASS")
            return True
        except AssertionError as e:
            self.log(f"FAILED - {name}: {str(e)}", "FAIL")
            return False
        except Exception as e:
            self.log(f"ERROR - {name}: {str(e)}", "FAIL")
            return False

    def test_login(self):
        """Test login for all roles"""
        # Admin login
        response = requests.post(f"{API_BASE}/auth/login", json={
            "email": "admin@kainnusantara.id",
            "password": "demo12345"
        })
        assert response.status_code == 200, f"Admin login failed: {response.status_code}"
        data = response.json()
        assert "token" in data, "No token in admin login response"
        self.admin_token = data["token"]
        self.log("Admin login successful")

        # Manager login
        response = requests.post(f"{API_BASE}/auth/login", json={
            "email": "manager@kainnusantara.id",
            "password": "demo12345"
        })
        assert response.status_code == 200, f"Manager login failed: {response.status_code}"
        data = response.json()
        self.manager_token = data["token"]
        self.log("Manager login successful")

        # Sales login
        response = requests.post(f"{API_BASE}/auth/login", json={
            "email": "sales@kainnusantara.id",
            "password": "demo12345"
        })
        assert response.status_code == 200, f"Sales login failed: {response.status_code}"
        data = response.json()
        self.sales_token = data["token"]
        self.log("Sales login successful")

    def test_get_sales_users(self):
        """Test GET /api/sales-users"""
        response = requests.get(f"{API_BASE}/sales-users", headers={
            "Authorization": f"Bearer {self.admin_token}"
        })
        assert response.status_code == 200, f"Failed to get sales users: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Sales users should be a list"
        if len(data) > 0:
            self.test_sales_id = data[0]["id"]
            self.log(f"Found {len(data)} sales users, using {self.test_sales_id}")

    def test_get_customers(self):
        """Test GET /api/customers and find over-limit customer"""
        response = requests.get(f"{API_BASE}/customers", headers={
            "Authorization": f"Bearer {self.admin_token}"
        })
        assert response.status_code == 200, f"Failed to get customers: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Customers should be a list"
        
        # Find "Butik Bali Indah" or any customer with credit_limit
        for customer in data:
            if "Butik Bali" in customer.get("name", "") or customer.get("id") == "cust_butik_bali":
                self.test_customer_id = customer["id"]
                self.log(f"Found test customer: {customer['name']} (ID: {self.test_customer_id})")
                break
        
        if not self.test_customer_id and len(data) > 0:
            self.test_customer_id = data[0]["id"]
            self.log(f"Using first customer: {data[0].get('name')} (ID: {self.test_customer_id})")

    def test_credit_status_api(self):
        """Test GET /api/customers/{id}/credit-status?amount=X"""
        if not self.test_customer_id:
            self.log("Skipping credit status test - no customer ID", "WARN")
            return
        
        # Test with high amount to trigger blocking
        response = requests.get(
            f"{API_BASE}/customers/{self.test_customer_id}/credit-status",
            params={"amount": 50000000},  # 50 million
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        assert response.status_code == 200, f"Failed to get credit status: {response.status_code}"
        data = response.json()
        
        # Verify response structure
        assert "level" in data, "Missing 'level' in credit status"
        assert "blocked" in data, "Missing 'blocked' in credit status"
        assert "credit" in data, "Missing 'credit' in credit status"
        assert "projected_ar" in data, "Missing 'projected_ar' in credit status"
        
        self.log(f"Credit status: level={data['level']}, blocked={data['blocked']}, projected_ar={data['projected_ar']}")

    def test_create_sales_order_credit_blocked(self):
        """Test POST /api/sales-orders with over-limit customer returns 409 CREDIT_BLOCKED"""
        if not self.test_customer_id:
            self.log("Skipping credit blocked test - no customer ID", "WARN")
            return
        
        # Get products
        response = requests.get(f"{API_BASE}/products", headers={
            "Authorization": f"Bearer {self.admin_token}"
        })
        assert response.status_code == 200, "Failed to get products"
        products = response.json()
        if len(products) == 0:
            self.log("No products available for testing", "WARN")
            return
        
        product = products[0]
        
        # Get all customers to find the one with addresses
        response = requests.get(f"{API_BASE}/customers", headers={
            "Authorization": f"Bearer {self.admin_token}"
        })
        assert response.status_code == 200, "Failed to get customers list"
        customers = response.json()
        
        customer = None
        for c in customers:
            if c["id"] == self.test_customer_id:
                customer = c
                break
        
        if not customer:
            self.log("Customer not found in list", "WARN")
            return
        
        addresses = customer.get("addresses", [])
        if len(addresses) == 0:
            self.log("Customer has no addresses", "WARN")
            return
        
        # Try to create order with very high quantity (should trigger credit block)
        payload = {
            "customer_id": self.test_customer_id,
            "shipping_address_id": addresses[0]["id"],
            "shipment_policy": "allow_partial_shipment",
            "sales_name": "Test Sales",
            "items": [{
                "product_id": product["id"],
                "quantity": 500,  # High quantity
                "unit": product.get("base_unit", "meter"),
                "discount_percent": 0
            }],
            "order_discount_percent": 0,
            "payment_term_code": "NET30",
            "allow_backorder": False,
            "confirm_mixed_lot": False
        }
        
        response = requests.post(f"{API_BASE}/sales-orders", json=payload, headers={
            "Authorization": f"Bearer {self.admin_token}"
        })
        
        # Should return 409 with CREDIT_BLOCKED code
        if response.status_code == 409:
            detail = response.json().get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("code") == "CREDIT_BLOCKED", f"Expected CREDIT_BLOCKED code, got {detail.get('code')}"
                assert "message" in detail, "Missing message in CREDIT_BLOCKED response"
                assert "reasons" in detail, "Missing reasons in CREDIT_BLOCKED response"
                self.log(f"Credit blocked correctly: {detail.get('message')}")
            else:
                self.log(f"Got 409 but detail is not structured: {detail}", "WARN")
        else:
            self.log(f"Expected 409 CREDIT_BLOCKED, got {response.status_code}", "WARN")

    def test_collection_reminders(self):
        """Test GET /api/collection-reminders"""
        response = requests.get(
            f"{API_BASE}/collection-reminders",
            params={"days_ahead": 60},
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        assert response.status_code == 200, f"Failed to get collection reminders: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Collection reminders should be a list"
        self.log(f"Found {len(data)} collection reminders")
        
        # Verify structure if data exists
        if len(data) > 0:
            reminder = data[0]
            assert "order_id" in reminder, "Missing order_id in reminder"
            assert "customer_name" in reminder, "Missing customer_name in reminder"
            assert "outstanding" in reminder, "Missing outstanding in reminder"
            assert "due_date" in reminder, "Missing due_date in reminder"
            assert "overdue" in reminder, "Missing overdue in reminder"
            self.test_order_id = reminder["order_id"]

    def test_mark_reminder(self):
        """Test POST /api/collection-reminders/mark"""
        if not self.test_customer_id or not self.test_order_id:
            self.log("Skipping mark reminder test - no customer/order ID", "WARN")
            return
        
        payload = {
            "customer_id": self.test_customer_id,
            "order_id": self.test_order_id,
            "note": "Test reminder marked"
        }
        
        response = requests.post(
            f"{API_BASE}/collection-reminders/mark",
            json=payload,
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        assert response.status_code == 200, f"Failed to mark reminder: {response.status_code}"
        data = response.json()
        assert "id" in data, "Missing id in mark reminder response"
        self.log("Reminder marked successfully")

    def test_add_followup(self):
        """Test POST /api/customers/{id}/followups"""
        if not self.test_customer_id or not self.test_order_id:
            self.log("Skipping followup test - no customer/order ID", "WARN")
            return
        
        payload = {
            "customer_id": self.test_customer_id,
            "order_id": self.test_order_id,
            "note": "Test follow-up note",
            "outcome": "contacted"
        }
        
        response = requests.post(
            f"{API_BASE}/customers/{self.test_customer_id}/followups",
            json=payload,
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        assert response.status_code == 200, f"Failed to add followup: {response.status_code}"
        data = response.json()
        assert "id" in data, "Missing id in followup response"
        self.log("Follow-up added successfully")

    def test_sales_kpi(self):
        """Test GET /api/sales/kpi"""
        if not self.test_sales_id:
            self.log("Skipping sales KPI test - no sales ID", "WARN")
            return
        
        response = requests.get(
            f"{API_BASE}/sales/kpi",
            params={"sales_id": self.test_sales_id, "period": "2025-01"},
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        assert response.status_code == 200, f"Failed to get sales KPI: {response.status_code}"
        data = response.json()
        
        # Verify KPI structure
        assert "total_sales" in data, "Missing total_sales in KPI"
        assert "total_collected" in data, "Missing total_collected in KPI"
        assert "ar_outstanding" in data, "Missing ar_outstanding in KPI"
        assert "customers_count" in data, "Missing customers_count in KPI"
        assert "orders_count" in data, "Missing orders_count in KPI"
        
        self.log(f"Sales KPI: sales={data['total_sales']}, collected={data['total_collected']}, orders={data['orders_count']}")

    def test_sales_commission(self):
        """Test GET /api/sales/commission"""
        if not self.test_sales_id:
            self.log("Skipping commission test - no sales ID", "WARN")
            return
        
        response = requests.get(
            f"{API_BASE}/sales/commission",
            params={"sales_id": self.test_sales_id, "period": "2025-01"},
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        assert response.status_code == 200, f"Failed to get commission: {response.status_code}"
        data = response.json()
        
        # Verify commission structure
        assert "base_amount" in data, "Missing base_amount in commission"
        assert "target_amount" in data, "Missing target_amount in commission"
        assert "achievement_pct" in data, "Missing achievement_pct in commission"
        assert "applied_rate" in data, "Missing applied_rate in commission"
        assert "total_incentive" in data, "Missing total_incentive in commission"
        
        self.log(f"Commission: base={data['base_amount']}, achievement={data['achievement_pct']}%, incentive={data['total_incentive']}")

    def test_commission_history(self):
        """Test GET /api/sales/commission-history"""
        if not self.test_sales_id:
            self.log("Skipping commission history test - no sales ID", "WARN")
            return
        
        response = requests.get(
            f"{API_BASE}/sales/commission-history",
            params={"sales_id": self.test_sales_id, "period_type": "month", "anchor": "2025-01", "count": 6},
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        assert response.status_code == 200, f"Failed to get commission history: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Commission history should be a list"
        assert len(data) <= 6, "Commission history should have max 6 periods"
        
        # Verify structure if data exists
        if len(data) > 0:
            period = data[0]
            assert "period" in period, "Missing period in history"
            assert "total_collected" in period, "Missing total_collected in history"
            assert "total_incentive" in period, "Missing total_incentive in history"
            assert "achievement_pct" in period, "Missing achievement_pct in history"
        
        self.log(f"Commission history: {len(data)} periods")

    def test_leaderboard(self):
        """Test GET /api/sales/leaderboard (manager only)"""
        response = requests.get(
            f"{API_BASE}/sales/leaderboard",
            params={"period": "2025-01"},
            headers={"Authorization": f"Bearer {self.manager_token}"}
        )
        assert response.status_code == 200, f"Failed to get leaderboard: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Leaderboard should be a list"
        
        # Verify structure if data exists
        if len(data) > 0:
            entry = data[0]
            assert "rank" in entry, "Missing rank in leaderboard"
            assert "sales_name" in entry, "Missing sales_name in leaderboard"
            assert "total_sales" in entry, "Missing total_sales in leaderboard"
            assert "total_collected" in entry, "Missing total_collected in leaderboard"
        
        self.log(f"Leaderboard: {len(data)} entries")

    def test_sales_targets_create_admin(self):
        """Test POST /api/sales-targets (admin/manager only)"""
        if not self.test_sales_id:
            self.log("Skipping sales targets test - no sales ID", "WARN")
            return
        
        payload = {
            "sales_id": self.test_sales_id,
            "period": "2025-02",
            "period_type": "month",
            "target_sales_amount": 100000000,
            "target_collection_amount": 80000000,
            "target_new_customers": 5,
            "notes": "Test target"
        }
        
        response = requests.post(
            f"{API_BASE}/sales-targets",
            json=payload,
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        assert response.status_code == 200, f"Failed to create sales target: {response.status_code}"
        data = response.json()
        assert "id" in data, "Missing id in sales target response"
        assert data["target_sales_amount"] == 100000000, "Target sales amount mismatch"
        self.log("Sales target created successfully")

    def test_sales_targets_forbidden_sales(self):
        """Test POST /api/sales-targets returns 403 for sales role"""
        if not self.test_sales_id:
            self.log("Skipping sales targets forbidden test - no sales ID", "WARN")
            return
        
        payload = {
            "sales_id": self.test_sales_id,
            "period": "2025-02",
            "period_type": "month",
            "target_sales_amount": 100000000,
            "target_collection_amount": 80000000,
            "target_new_customers": 5
        }
        
        response = requests.post(
            f"{API_BASE}/sales-targets",
            json=payload,
            headers={"Authorization": f"Bearer {self.sales_token}"}
        )
        assert response.status_code == 403, f"Expected 403 for sales role, got {response.status_code}"
        self.log("Sales targets correctly forbidden for sales role")

    def test_sales_incentives_create_admin(self):
        """Test POST /api/sales-incentives (admin/manager only)"""
        if not self.test_sales_id:
            self.log("Skipping sales incentives test - no sales ID", "WARN")
            return
        
        payload = {
            "sales_id": self.test_sales_id,
            "period": "2025-02",
            "basis": "collection",
            "tiers": [
                {"min_achievement": 0, "rate": 1.0},
                {"min_achievement": 80, "rate": 1.5},
                {"min_achievement": 100, "rate": 2.5}
            ],
            "bonus_new_customer": 500000,
            "bonus_focus_product": 0,
            "notes": "Test incentive scheme"
        }
        
        response = requests.post(
            f"{API_BASE}/sales-incentives",
            json=payload,
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        assert response.status_code == 200, f"Failed to create sales incentive: {response.status_code}"
        data = response.json()
        assert "id" in data, "Missing id in sales incentive response"
        assert data["basis"] == "collection", "Basis mismatch"
        assert len(data["tiers"]) == 3, "Tiers count mismatch"
        self.log("Sales incentive scheme created successfully")

    def test_sales_incentives_forbidden_sales(self):
        """Test POST /api/sales-incentives returns 403 for sales role"""
        if not self.test_sales_id:
            self.log("Skipping sales incentives forbidden test - no sales ID", "WARN")
            return
        
        payload = {
            "sales_id": self.test_sales_id,
            "period": "2025-02",
            "basis": "collection",
            "tiers": [{"min_achievement": 0, "rate": 1.0}],
            "bonus_new_customer": 500000
        }
        
        response = requests.post(
            f"{API_BASE}/sales-incentives",
            json=payload,
            headers={"Authorization": f"Bearer {self.sales_token}"}
        )
        assert response.status_code == 403, f"Expected 403 for sales role, got {response.status_code}"
        self.log("Sales incentives correctly forbidden for sales role")

    def run_all_tests(self):
        """Run all tests"""
        self.log("=" * 60)
        self.log("Starting CRM Enforcements + Incentive Schema Backend Tests")
        self.log("=" * 60)
        
        # Authentication
        self.run_test("Login (all roles)", self.test_login)
        
        # Setup data
        self.run_test("Get sales users", self.test_get_sales_users)
        self.run_test("Get customers", self.test_get_customers)
        
        # Phase A - Credit Gate & Collection
        self.run_test("Credit status API", self.test_credit_status_api)
        self.run_test("Create SO with credit blocked (409)", self.test_create_sales_order_credit_blocked)
        self.run_test("Collection reminders", self.test_collection_reminders)
        self.run_test("Mark reminder", self.test_mark_reminder)
        self.run_test("Add follow-up", self.test_add_followup)
        
        # Phase A - Sales Force KPI & Commission
        self.run_test("Sales KPI", self.test_sales_kpi)
        self.run_test("Sales commission", self.test_sales_commission)
        self.run_test("Commission history (6 periods)", self.test_commission_history)
        self.run_test("Leaderboard (manager)", self.test_leaderboard)
        
        # Phase B - Incentive Schema Editor
        self.run_test("Create sales target (admin)", self.test_sales_targets_create_admin)
        self.run_test("Sales target forbidden (sales role)", self.test_sales_targets_forbidden_sales)
        self.run_test("Create sales incentive (admin)", self.test_sales_incentives_create_admin)
        self.run_test("Sales incentive forbidden (sales role)", self.test_sales_incentives_forbidden_sales)
        
        # Summary
        self.log("=" * 60)
        self.log(f"Tests completed: {self.tests_passed}/{self.tests_run} passed")
        self.log("=" * 60)
        
        return 0 if self.tests_passed == self.tests_run else 1

def main():
    tester = CRMEnforcementsTest()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
