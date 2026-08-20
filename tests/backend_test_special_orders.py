"""
Backend API Testing for Special Orders (Sub-fase 1.12)

Tests all CRUD operations, approval workflow, and status transitions.
"""
import requests
import sys
from datetime import datetime, timedelta

API_BASE = "https://po-pdf-sender.preview.emergentagent.com/api"

class SpecialOrderTester:
    def __init__(self):
        self.admin_token = None
        self.sales_token = None
        self.manager_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_customer_id = None
        self.test_order_id_draft = None
        self.test_order_id_approval = None
        
    def log(self, msg, status="info"):
        symbols = {"pass": "✅", "fail": "❌", "info": "🔍"}
        print(f"{symbols.get(status, '•')} {msg}")
    
    def test(self, name, func):
        """Run a test and track results"""
        self.tests_run += 1
        self.log(f"Testing: {name}", "info")
        try:
            func()
            self.tests_passed += 1
            self.log(f"PASSED: {name}", "pass")
            return True
        except AssertionError as e:
            self.log(f"FAILED: {name} - {str(e)}", "fail")
            return False
        except Exception as e:
            self.log(f"ERROR: {name} - {str(e)}", "fail")
            return False
    
    def login(self, email, password):
        """Login and return token"""
        res = requests.post(f"{API_BASE}/auth/login", json={"email": email, "password": password})
        assert res.status_code == 200, f"Login failed: {res.status_code} - {res.text}"
        data = res.json()
        assert "token" in data, "No token in response"
        return data["token"]
    
    def get_customers(self, token):
        """Get list of customers"""
        res = requests.get(f"{API_BASE}/customers", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200, f"Failed to get customers: {res.status_code}"
        data = res.json()
        customers = data.get("items", data) if isinstance(data, dict) else data
        assert len(customers) > 0, "No customers found"
        return customers
    
    # ─── Test Cases ──────────────────────────────────────────────────────────
    
    def test_auth(self):
        """Test authentication for all roles"""
        self.admin_token = self.login("admin@kainnusantara.id", "demo12345")
        self.sales_token = self.login("sales@kainnusantara.id", "demo12345")
        self.manager_token = self.login("manager@kainnusantara.id", "demo12345")
        assert self.admin_token, "Admin token missing"
        assert self.sales_token, "Sales token missing"
        assert self.manager_token, "Manager token missing"
    
    def test_get_customer(self):
        """Get a test customer for creating orders"""
        customers = self.get_customers(self.sales_token)
        self.test_customer_id = customers[0]["id"]
        assert self.test_customer_id, "No customer ID found"
    
    def test_list_special_orders_empty(self):
        """Test listing special orders (may be empty initially)"""
        res = requests.get(
            f"{API_BASE}/special-orders",
            headers={"Authorization": f"Bearer {self.sales_token}"}
        )
        assert res.status_code == 200, f"Failed to list: {res.status_code} - {res.text}"
        data = res.json()
        assert "items" in data, "No items field in response"
        assert "by_status" in data, "No by_status field in response"
        assert "approval_threshold" in data, "No approval_threshold field"
        assert data["approval_threshold"] == 10_000_000, "Wrong approval threshold"
    
    def test_create_special_order_below_threshold(self):
        """Create special order with amount < 10 million (no approval needed)"""
        expected_delivery = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        payload = {
            "customer_id": self.test_customer_id,
            "custom_item": {
                "description": "Kain Batik Custom Motif Perusahaan",
                "specifications": {
                    "Warna": "Biru Navy",
                    "Ukuran": "2x1.5 meter",
                    "Material": "Katun Premium"
                },
                "quantity": 50,
                "unit": "meter",
                "target_price": 150000,
                "notes": "Logo perusahaan di pojok kanan"
            },
            "expected_delivery": expected_delivery,
            "notes": "Test order below threshold",
            "submit_for_approval": True
        }
        
        res = requests.post(
            f"{API_BASE}/special-orders",
            json=payload,
            headers={"Authorization": f"Bearer {self.sales_token}"}
        )
        assert res.status_code == 200, f"Failed to create: {res.status_code} - {res.text}"
        data = res.json()
        
        # Validate response
        assert "id" in data, "No ID in response"
        assert "number" in data, "No order number"
        assert data["number"].startswith("SORD-"), "Invalid order number format"
        assert data["status"] == "draft", f"Expected draft status, got {data['status']}"
        assert data["total_amount"] == 7_500_000, f"Wrong total: {data['total_amount']}"
        assert data["requires_approval"] == False, "Should not require approval"
        
        self.test_order_id_draft = data["id"]
    
    def test_create_special_order_above_threshold(self):
        """Create special order with amount > 10 million (requires approval)"""
        expected_delivery = (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d")
        
        payload = {
            "customer_id": self.test_customer_id,
            "custom_item": {
                "description": "Tenun Ikat Custom Premium",
                "specifications": {
                    "Motif": "Garuda Custom",
                    "Warna": "Emas-Merah",
                    "Grade": "A+"
                },
                "quantity": 100,
                "unit": "meter",
                "target_price": 250000,
                "notes": "Benang emas asli"
            },
            "expected_delivery": expected_delivery,
            "notes": "Test order above threshold - needs approval",
            "submit_for_approval": True
        }
        
        res = requests.post(
            f"{API_BASE}/special-orders",
            json=payload,
            headers={"Authorization": f"Bearer {self.sales_token}"}
        )
        assert res.status_code == 200, f"Failed to create: {res.status_code} - {res.text}"
        data = res.json()
        
        # Validate response
        assert data["status"] == "pending_approval", f"Expected pending_approval, got {data['status']}"
        assert data["total_amount"] == 25_000_000, f"Wrong total: {data['total_amount']}"
        assert data["requires_approval"] == True, "Should require approval"
        
        self.test_order_id_approval = data["id"]
    
    def test_get_special_order_detail(self):
        """Test getting special order detail"""
        res = requests.get(
            f"{API_BASE}/special-orders/{self.test_order_id_draft}",
            headers={"Authorization": f"Bearer {self.sales_token}"}
        )
        assert res.status_code == 200, f"Failed to get detail: {res.status_code} - {res.text}"
        data = res.json()
        
        assert data["id"] == self.test_order_id_draft, "Wrong order ID"
        assert "custom_item" in data, "No custom_item field"
        assert "customer_name" in data, "No customer_name field"
        assert "status_history" in data, "No status_history field"
    
    def test_list_with_status_filter(self):
        """Test listing with status filter"""
        res = requests.get(
            f"{API_BASE}/special-orders?status=pending_approval",
            headers={"Authorization": f"Bearer {self.manager_token}"}
        )
        assert res.status_code == 200, f"Failed to list: {res.status_code} - {res.text}"
        data = res.json()
        
        # Should have at least our test order
        items = data["items"]
        pending = [o for o in items if o["status"] == "pending_approval"]
        assert len(pending) > 0, "No pending_approval orders found"
    
    def test_update_draft_order(self):
        """Test updating draft order (PATCH)"""
        payload = {
            "notes": "Updated notes for draft order",
            "expected_delivery": (datetime.now() + timedelta(days=35)).strftime("%Y-%m-%d")
        }
        
        res = requests.patch(
            f"{API_BASE}/special-orders/{self.test_order_id_draft}",
            json=payload,
            headers={"Authorization": f"Bearer {self.sales_token}"}
        )
        assert res.status_code == 200, f"Failed to update: {res.status_code} - {res.text}"
        data = res.json()
        
        assert data["notes"] == payload["notes"], "Notes not updated"
    
    def test_approve_special_order(self):
        """Test approving special order (manager/admin only)"""
        res = requests.post(
            f"{API_BASE}/special-orders/{self.test_order_id_approval}/approve",
            json={"notes": "Approved by manager"},
            headers={"Authorization": f"Bearer {self.manager_token}"}
        )
        assert res.status_code == 200, f"Failed to approve: {res.status_code} - {res.text}"
        data = res.json()
        
        assert data["status"] == "confirmed", f"Expected confirmed status, got {data['status']}"
        assert "approved_by" in data, "No approved_by field"
        assert "approved_at" in data, "No approved_at field"
    
    def test_status_transition_to_production(self):
        """Test status transition: confirmed → in_production"""
        res = requests.post(
            f"{API_BASE}/special-orders/{self.test_order_id_approval}/status",
            json={"status": "in_production", "notes": "Production started"},
            headers={"Authorization": f"Bearer {self.manager_token}"}
        )
        assert res.status_code == 200, f"Failed to transition: {res.status_code} - {res.text}"
        data = res.json()
        
        assert data["status"] == "in_production", f"Expected in_production, got {data['status']}"
    
    def test_status_transition_to_ready(self):
        """Test status transition: in_production → ready"""
        res = requests.post(
            f"{API_BASE}/special-orders/{self.test_order_id_approval}/status",
            json={"status": "ready", "notes": "Item ready"},
            headers={"Authorization": f"Bearer {self.manager_token}"}
        )
        assert res.status_code == 200, f"Failed to transition: {res.status_code} - {res.text}"
        data = res.json()
        
        assert data["status"] == "ready", f"Expected ready, got {data['status']}"
    
    def test_status_transition_to_shipped(self):
        """Test status transition: ready → shipped"""
        res = requests.post(
            f"{API_BASE}/special-orders/{self.test_order_id_approval}/status",
            json={"status": "shipped", "notes": "Shipped to customer"},
            headers={"Authorization": f"Bearer {self.manager_token}"}
        )
        assert res.status_code == 200, f"Failed to transition: {res.status_code} - {res.text}"
        data = res.json()
        
        assert data["status"] == "shipped", f"Expected shipped, got {data['status']}"
    
    def test_status_transition_to_done(self):
        """Test status transition: shipped → done"""
        res = requests.post(
            f"{API_BASE}/special-orders/{self.test_order_id_approval}/status",
            json={"status": "done", "notes": "Delivered successfully"},
            headers={"Authorization": f"Bearer {self.manager_token}"}
        )
        assert res.status_code == 200, f"Failed to transition: {res.status_code} - {res.text}"
        data = res.json()
        
        assert data["status"] == "done", f"Expected done, got {data['status']}"
    
    def test_reject_special_order(self):
        """Test rejecting special order (create new one first)"""
        # Create another order for rejection test
        expected_delivery = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        payload = {
            "customer_id": self.test_customer_id,
            "custom_item": {
                "description": "Test Order for Rejection",
                "specifications": {"Test": "Reject"},
                "quantity": 100,
                "unit": "meter",
                "target_price": 200000,
                "notes": ""
            },
            "expected_delivery": expected_delivery,
            "notes": "Will be rejected",
            "submit_for_approval": True
        }
        
        res = requests.post(
            f"{API_BASE}/special-orders",
            json=payload,
            headers={"Authorization": f"Bearer {self.sales_token}"}
        )
        assert res.status_code == 200, "Failed to create order for rejection"
        order_id = res.json()["id"]
        
        # Now reject it
        res = requests.post(
            f"{API_BASE}/special-orders/{order_id}/reject",
            json={"reason": "Budget tidak mencukupi"},
            headers={"Authorization": f"Bearer {self.manager_token}"}
        )
        assert res.status_code == 200, f"Failed to reject: {res.status_code} - {res.text}"
        data = res.json()
        
        assert data["status"] == "cancelled", f"Expected cancelled, got {data['status']}"
        assert "rejected_by" in data, "No rejected_by field"
        assert data["reject_reason"] == "Budget tidak mencukupi", "Wrong reject reason"
    
    def test_delete_draft_order(self):
        """Test soft deleting draft order (admin only)"""
        res = requests.delete(
            f"{API_BASE}/special-orders/{self.test_order_id_draft}",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        assert res.status_code == 200, f"Failed to delete: {res.status_code} - {res.text}"
        data = res.json()
        
        assert data["status"] == "cancelled", f"Expected cancelled, got {data['status']}"
        assert "cancelled_by" in data, "No cancelled_by field"
    
    def test_invalid_status_transition(self):
        """Test invalid status transition (should fail)"""
        # Create a draft order and try to transition to shipped (invalid)
        expected_delivery = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        payload = {
            "customer_id": self.test_customer_id,
            "custom_item": {
                "description": "Test Invalid Transition",
                "specifications": {},
                "quantity": 10,
                "unit": "meter",
                "target_price": 100000,
                "notes": ""
            },
            "expected_delivery": expected_delivery,
            "notes": "",
            "submit_for_approval": False
        }
        
        res = requests.post(
            f"{API_BASE}/special-orders",
            json=payload,
            headers={"Authorization": f"Bearer {self.sales_token}"}
        )
        order_id = res.json()["id"]
        
        # Try invalid transition: draft → shipped (should fail)
        res = requests.post(
            f"{API_BASE}/special-orders/{order_id}/status",
            json={"status": "shipped", "notes": ""},
            headers={"Authorization": f"Bearer {self.manager_token}"}
        )
        assert res.status_code == 400, f"Should fail with 400, got {res.status_code}"
    
    def test_sales_cannot_approve(self):
        """Test that sales role cannot approve orders"""
        # Create order that needs approval
        expected_delivery = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        payload = {
            "customer_id": self.test_customer_id,
            "custom_item": {
                "description": "Test Sales Cannot Approve",
                "specifications": {},
                "quantity": 100,
                "unit": "meter",
                "target_price": 150000,
                "notes": ""
            },
            "expected_delivery": expected_delivery,
            "notes": "",
            "submit_for_approval": True
        }
        
        res = requests.post(
            f"{API_BASE}/special-orders",
            json=payload,
            headers={"Authorization": f"Bearer {self.sales_token}"}
        )
        order_id = res.json()["id"]
        
        # Try to approve with sales token (should fail)
        res = requests.post(
            f"{API_BASE}/special-orders/{order_id}/approve",
            json={"notes": ""},
            headers={"Authorization": f"Bearer {self.sales_token}"}
        )
        assert res.status_code in [403, 400], f"Should fail with 403/400, got {res.status_code}"
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*70)
        print("🧪 SPECIAL ORDERS BACKEND API TESTING")
        print("="*70 + "\n")
        
        # Authentication
        self.test("Authentication for all roles", self.test_auth)
        self.test("Get test customer", self.test_get_customer)
        
        # List operations
        self.test("List special orders (initial)", self.test_list_special_orders_empty)
        
        # Create operations
        self.test("Create special order below threshold", self.test_create_special_order_below_threshold)
        self.test("Create special order above threshold", self.test_create_special_order_above_threshold)
        
        # Read operations
        self.test("Get special order detail", self.test_get_special_order_detail)
        self.test("List with status filter", self.test_list_with_status_filter)
        
        # Update operations
        self.test("Update draft order (PATCH)", self.test_update_draft_order)
        
        # Approval workflow
        self.test("Approve special order (manager)", self.test_approve_special_order)
        
        # Status transitions
        self.test("Status transition: confirmed → in_production", self.test_status_transition_to_production)
        self.test("Status transition: in_production → ready", self.test_status_transition_to_ready)
        self.test("Status transition: ready → shipped", self.test_status_transition_to_shipped)
        self.test("Status transition: shipped → done", self.test_status_transition_to_done)
        
        # Rejection workflow
        self.test("Reject special order", self.test_reject_special_order)
        
        # Delete operations
        self.test("Delete draft order (soft delete)", self.test_delete_draft_order)
        
        # Error cases
        self.test("Invalid status transition", self.test_invalid_status_transition)
        self.test("Sales cannot approve orders", self.test_sales_cannot_approve)
        
        # Summary
        print("\n" + "="*70)
        print(f"📊 TEST SUMMARY")
        print("="*70)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed} ✅")
        print(f"Failed: {self.tests_run - self.tests_passed} ❌")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        print("="*70 + "\n")
        
        return 0 if self.tests_passed == self.tests_run else 1


if __name__ == "__main__":
    tester = SpecialOrderTester()
    sys.exit(tester.run_all_tests())
