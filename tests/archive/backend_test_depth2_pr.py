#!/usr/bin/env python3
"""
Backend Test: Depth #2 — Purchase Requisition (PR) + Reorder Suggestions + Special Order → PR Bridge
Tests all PR lifecycle, reorder suggestions, and special order integration.
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

class Depth2PRTester:
    def __init__(self):
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
    def log_test(self, name, passed, details=""):
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            print(f"✅ {name}")
            self.test_results.append({"test": name, "status": "PASS", "details": details})
        else:
            print(f"❌ {name}: {details}")
            self.test_results.append({"test": name, "status": "FAIL", "details": details})
    
    def login(self, email, password):
        """Login and store token"""
        try:
            res = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
            if res.status_code == 200:
                data = res.json()
                token = data.get("token", "")
                if token:
                    self.tokens[email] = token
                    self.log_test(f"Login {email}", True, f"Token: {token[:20]}...")
                    return token
                else:
                    self.log_test(f"Login {email}", False, "No token in response")
                    return None
            else:
                self.log_test(f"Login {email}", False, f"Status {res.status_code}: {res.text}")
                return None
        except Exception as e:
            self.log_test(f"Login {email}", False, str(e))
            return None
    
    def get(self, endpoint, token, params=None):
        """GET request"""
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get(f"{BASE_URL}{endpoint}", headers=headers, params=params)
        return res
    
    def post(self, endpoint, token, data):
        """POST request"""
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        res = requests.post(f"{BASE_URL}{endpoint}", headers=headers, json=data)
        return res
    
    def test_auth(self):
        """Test authentication for all roles"""
        print("\n=== AUTH TESTS ===")
        self.login("admin@kainnusantara.id", "demo12345")
        self.login("manager@kainnusantara.id", "demo12345")
        self.login("sales@kainnusantara.id", "demo12345")
        self.login("warehouse@kainnusantara.id", "demo12345")
    
    def test_pr_list(self):
        """Test GET /purchase-requisitions - should return 3 seeded PRs"""
        print("\n=== PR LIST TESTS ===")
        token = self.tokens.get("admin@kainnusantara.id")
        if not token:
            self.log_test("PR List", False, "No admin token")
            return
        
        res = self.get("/purchase-requisitions", token)
        if res.status_code == 200:
            data = res.json()
            items = data.get("items", [])
            by_status = data.get("by_status", {})
            
            # Check for 3 seeded PRs
            if len(items) >= 3:
                self.log_test("PR List - Count", True, f"Found {len(items)} PRs")
            else:
                self.log_test("PR List - Count", False, f"Expected >=3 PRs, got {len(items)}")
            
            # Check for specific PRs
            pr_numbers = [pr.get("number") for pr in items]
            if "PR-00001" in pr_numbers:
                self.log_test("PR List - PR-00001 exists", True)
            else:
                self.log_test("PR List - PR-00001 exists", False, f"PRs: {pr_numbers}")
            
            if "PR-00002" in pr_numbers:
                self.log_test("PR List - PR-00002 exists", True)
            else:
                self.log_test("PR List - PR-00002 exists", False, f"PRs: {pr_numbers}")
            
            if "PR-00003" in pr_numbers:
                self.log_test("PR List - PR-00003 exists", True)
            else:
                self.log_test("PR List - PR-00003 exists", False, f"PRs: {pr_numbers}")
            
            # Check by_status aggregation
            if by_status:
                self.log_test("PR List - by_status aggregation", True, f"Stats: {by_status}")
            else:
                self.log_test("PR List - by_status aggregation", False, "No by_status data")
            
            # Store PRs for later tests
            self.prs = items
        else:
            self.log_test("PR List", False, f"Status {res.status_code}: {res.text}")
    
    def test_pr_detail(self):
        """Test GET /purchase-requisitions/{id}"""
        print("\n=== PR DETAIL TESTS ===")
        token = self.tokens.get("admin@kainnusantara.id")
        if not token or not hasattr(self, 'prs') or not self.prs:
            self.log_test("PR Detail", False, "No PRs available")
            return
        
        pr = self.prs[0]
        pr_id = pr.get("id")
        res = self.get(f"/purchase-requisitions/{pr_id}", token)
        
        if res.status_code == 200:
            data = res.json()
            required_fields = ["id", "number", "status", "items", "total_est_amount", "source"]
            missing = [f for f in required_fields if f not in data]
            if not missing:
                self.log_test("PR Detail - Required fields", True, f"PR {data.get('number')}")
            else:
                self.log_test("PR Detail - Required fields", False, f"Missing: {missing}")
            
            # Check items structure
            items = data.get("items", [])
            if items and len(items) > 0:
                item = items[0]
                item_fields = ["product_id", "quantity", "unit", "est_price", "subtotal"]
                missing_item = [f for f in item_fields if f not in item]
                if not missing_item:
                    self.log_test("PR Detail - Item structure", True)
                else:
                    self.log_test("PR Detail - Item structure", False, f"Missing: {missing_item}")
        else:
            self.log_test("PR Detail", False, f"Status {res.status_code}: {res.text}")
    
    def test_pr_create(self):
        """Test POST /purchase-requisitions - create new PR"""
        print("\n=== PR CREATE TESTS ===")
        token = self.tokens.get("admin@kainnusantara.id")
        if not token:
            self.log_test("PR Create", False, "No admin token")
            return
        
        # Get products and warehouses first
        products_res = self.get("/products", token)
        warehouses_res = self.get("/warehouses", token)
        
        if products_res.status_code != 200 or warehouses_res.status_code != 200:
            self.log_test("PR Create - Prerequisites", False, "Failed to get products/warehouses")
            return
        
        products = products_res.json()
        warehouses = warehouses_res.json()
        
        if not products or not warehouses:
            self.log_test("PR Create - Prerequisites", False, "No products or warehouses")
            return
        
        product = products[0] if isinstance(products, list) else products.get("items", [])[0]
        warehouse = warehouses[0] if isinstance(warehouses, list) else warehouses.get("items", [])[0]
        
        payload = {
            "items": [
                {
                    "product_id": product.get("id"),
                    "quantity": 100,
                    "unit": product.get("base_unit", "meter"),
                    "est_price": product.get("harga_pokok", 50000)
                }
            ],
            "warehouse_id": warehouse.get("id"),
            "entity_id": "ent_ksc",
            "source": "manual",
            "reason": "Test PR creation from automated test",
            "submit_now": False
        }
        
        res = self.post("/purchase-requisitions", token, payload)
        
        if res.status_code == 200:
            data = res.json()
            self.created_pr_id = data.get("id")
            self.created_pr_number = data.get("number")
            self.log_test("PR Create", True, f"Created {data.get('number')} with status {data.get('status')}")
            
            # Verify status is draft
            if data.get("status") == "draft":
                self.log_test("PR Create - Status draft", True)
            else:
                self.log_test("PR Create - Status draft", False, f"Status: {data.get('status')}")
        else:
            self.log_test("PR Create", False, f"Status {res.status_code}: {res.text}")
    
    def test_pr_submit(self):
        """Test POST /purchase-requisitions/{id}/submit"""
        print("\n=== PR SUBMIT TESTS ===")
        token = self.tokens.get("admin@kainnusantara.id")
        if not token or not hasattr(self, 'created_pr_id'):
            self.log_test("PR Submit", False, "No PR to submit")
            return
        
        res = self.post(f"/purchase-requisitions/{self.created_pr_id}/submit", token, {})
        
        if res.status_code == 200:
            data = res.json()
            status = data.get("status")
            # Should be either pending_approval or approved (if no approval needed)
            if status in ["pending_approval", "approved"]:
                self.log_test("PR Submit", True, f"Status changed to {status}")
                self.submitted_pr_status = status
            else:
                self.log_test("PR Submit", False, f"Unexpected status: {status}")
        else:
            self.log_test("PR Submit", False, f"Status {res.status_code}: {res.text}")
    
    def test_pr_approve_reject(self):
        """Test PR approval and rejection"""
        print("\n=== PR APPROVE/REJECT TESTS ===")
        manager_token = self.tokens.get("manager@kainnusantara.id")
        admin_token = self.tokens.get("admin@kainnusantara.id")
        
        if not manager_token or not admin_token:
            self.log_test("PR Approve/Reject", False, "No manager/admin token")
            return
        
        # Find a pending_approval PR
        res = self.get("/purchase-requisitions", admin_token, {"status": "pending_approval"})
        if res.status_code == 200:
            data = res.json()
            items = data.get("items", [])
            if items:
                pr = items[0]
                pr_id = pr.get("id")
                
                # Test approve
                approve_res = self.post(f"/purchase-requisitions/{pr_id}/approve", manager_token, {"notes": "Approved by test"})
                if approve_res.status_code == 200:
                    approve_data = approve_res.json()
                    if approve_data.get("status") == "approved":
                        self.log_test("PR Approve", True, f"PR {pr.get('number')} approved")
                        self.approved_pr_id = pr_id
                    else:
                        self.log_test("PR Approve", False, f"Status: {approve_data.get('status')}")
                else:
                    self.log_test("PR Approve", False, f"Status {approve_res.status_code}: {approve_res.text}")
            else:
                self.log_test("PR Approve", False, "No pending_approval PRs found")
        
        # Test reject on another PR (create one first)
        # Create a PR that requires approval
        products_res = self.get("/products", admin_token)
        warehouses_res = self.get("/warehouses", admin_token)
        
        if products_res.status_code == 200 and warehouses_res.status_code == 200:
            products = products_res.json()
            warehouses = warehouses_res.json()
            product = products[0] if isinstance(products, list) else products.get("items", [])[0]
            warehouse = warehouses[0] if isinstance(warehouses, list) else warehouses.get("items", [])[0]
            
            # Create PR with high amount to trigger approval
            payload = {
                "items": [
                    {
                        "product_id": product.get("id"),
                        "quantity": 10000,
                        "unit": product.get("base_unit", "meter"),
                        "est_price": 100000
                    }
                ],
                "warehouse_id": warehouse.get("id"),
                "entity_id": "ent_ksc",
                "source": "manual",
                "reason": "Test PR for rejection",
                "submit_now": True
            }
            
            create_res = self.post("/purchase-requisitions", admin_token, payload)
            if create_res.status_code == 200:
                pr_data = create_res.json()
                pr_id = pr_data.get("id")
                
                # Reject it
                reject_res = self.post(f"/purchase-requisitions/{pr_id}/reject", manager_token, {"notes": "Rejected by test"})
                if reject_res.status_code == 200:
                    reject_data = reject_res.json()
                    if reject_data.get("status") == "rejected":
                        self.log_test("PR Reject", True, f"PR {pr_data.get('number')} rejected")
                    else:
                        self.log_test("PR Reject", False, f"Status: {reject_data.get('status')}")
                else:
                    self.log_test("PR Reject", False, f"Status {reject_res.status_code}: {reject_res.text}")
    
    def test_pr_cancel(self):
        """Test POST /purchase-requisitions/{id}/cancel"""
        print("\n=== PR CANCEL TESTS ===")
        token = self.tokens.get("admin@kainnusantara.id")
        if not token:
            self.log_test("PR Cancel", False, "No admin token")
            return
        
        # Create a draft PR to cancel
        products_res = self.get("/products", token)
        warehouses_res = self.get("/warehouses", token)
        
        if products_res.status_code == 200 and warehouses_res.status_code == 200:
            products = products_res.json()
            warehouses = warehouses_res.json()
            product = products[0] if isinstance(products, list) else products.get("items", [])[0]
            warehouse = warehouses[0] if isinstance(warehouses, list) else warehouses.get("items", [])[0]
            
            payload = {
                "items": [{"product_id": product.get("id"), "quantity": 50, "unit": "meter", "est_price": 50000}],
                "warehouse_id": warehouse.get("id"),
                "entity_id": "ent_ksc",
                "source": "manual",
                "submit_now": False
            }
            
            create_res = self.post("/purchase-requisitions", token, payload)
            if create_res.status_code == 200:
                pr_data = create_res.json()
                pr_id = pr_data.get("id")
                
                # Cancel it
                cancel_res = self.post(f"/purchase-requisitions/{pr_id}/cancel", token, {})
                if cancel_res.status_code == 200:
                    cancel_data = cancel_res.json()
                    if cancel_data.get("status") == "cancelled":
                        self.log_test("PR Cancel", True, f"PR {pr_data.get('number')} cancelled")
                    else:
                        self.log_test("PR Cancel", False, f"Status: {cancel_data.get('status')}")
                else:
                    self.log_test("PR Cancel", False, f"Status {cancel_res.status_code}: {cancel_res.text}")
    
    def test_pr_convert_to_po(self):
        """Test POST /purchase-requisitions/{id}/convert-to-po"""
        print("\n=== PR CONVERT TO PO TESTS ===")
        token = self.tokens.get("admin@kainnusantara.id")
        if not token:
            self.log_test("PR Convert to PO", False, "No admin token")
            return
        
        # Get suppliers
        suppliers_res = self.get("/suppliers", token)
        if suppliers_res.status_code != 200:
            self.log_test("PR Convert to PO - Get Suppliers", False, "Failed to get suppliers")
            return
        
        suppliers = suppliers_res.json()
        if not suppliers:
            self.log_test("PR Convert to PO - Get Suppliers", False, "No suppliers found")
            return
        
        supplier = suppliers[0] if isinstance(suppliers, list) else suppliers.get("items", [])[0]
        
        # Use the approved PR from earlier test
        if hasattr(self, 'approved_pr_id'):
            pr_id = self.approved_pr_id
        else:
            # Find an approved PR
            res = self.get("/purchase-requisitions", token, {"status": "approved"})
            if res.status_code == 200:
                data = res.json()
                items = data.get("items", [])
                if items:
                    pr_id = items[0].get("id")
                else:
                    self.log_test("PR Convert to PO", False, "No approved PRs found")
                    return
            else:
                self.log_test("PR Convert to PO", False, "Failed to get approved PRs")
                return
        
        # Get warehouses
        warehouses_res = self.get("/warehouses", token)
        warehouses = warehouses_res.json()
        warehouse = warehouses[0] if isinstance(warehouses, list) else warehouses.get("items", [])[0]
        
        payload = {
            "supplier_id": supplier.get("id"),
            "warehouse_id": warehouse.get("id"),
            "expected_delivery_date": "2025-09-01",
            "notes": "Converted from test"
        }
        
        res = self.post(f"/purchase-requisitions/{pr_id}/convert-to-po", token, payload)
        
        if res.status_code == 200:
            data = res.json()
            pr = data.get("pr", {})
            po = data.get("po", {})
            
            if pr.get("status") == "converted" and po.get("po_number"):
                self.log_test("PR Convert to PO", True, f"PR converted to {po.get('po_number')}")
            else:
                self.log_test("PR Convert to PO", False, f"PR status: {pr.get('status')}, PO: {po.get('po_number')}")
        else:
            self.log_test("PR Convert to PO", False, f"Status {res.status_code}: {res.text}")
    
    def test_reorder_suggestions(self):
        """Test GET /purchase-requisitions/reorder-suggestions"""
        print("\n=== REORDER SUGGESTIONS TESTS ===")
        token = self.tokens.get("admin@kainnusantara.id")
        if not token:
            self.log_test("Reorder Suggestions", False, "No admin token")
            return
        
        # Test with entity_id
        res = self.get("/purchase-requisitions/reorder-suggestions", token, {"entity_id": "ent_ksc"})
        
        if res.status_code == 200:
            data = res.json()
            items = data.get("items", [])
            
            self.log_test("Reorder Suggestions - API", True, f"Found {len(items)} suggestions")
            
            # Check structure
            if items:
                item = items[0]
                required_fields = ["product_id", "sku", "product_name", "available", "on_order", 
                                 "projected", "reorder_point", "suggested_qty"]
                missing = [f for f in required_fields if f not in item]
                if not missing:
                    self.log_test("Reorder Suggestions - Structure", True)
                else:
                    self.log_test("Reorder Suggestions - Structure", False, f"Missing: {missing}")
                
                # Verify logic: projected <= reorder_point
                projected = item.get("projected", 0)
                reorder_point = item.get("reorder_point", 0)
                if projected <= reorder_point:
                    self.log_test("Reorder Suggestions - Logic", True, f"Projected {projected} <= ROP {reorder_point}")
                else:
                    self.log_test("Reorder Suggestions - Logic", False, f"Projected {projected} > ROP {reorder_point}")
            else:
                self.log_test("Reorder Suggestions - No items", True, "No products need reordering (good)")
        else:
            self.log_test("Reorder Suggestions", False, f"Status {res.status_code}: {res.text}")
    
    def test_reorder_create_pr(self):
        """Test creating PR from reorder suggestions"""
        print("\n=== REORDER CREATE PR TESTS ===")
        token = self.tokens.get("admin@kainnusantara.id")
        if not token:
            self.log_test("Reorder Create PR", False, "No admin token")
            return
        
        # Get reorder suggestions
        res = self.get("/purchase-requisitions/reorder-suggestions", token, {"entity_id": "ent_ksc"})
        
        if res.status_code == 200:
            data = res.json()
            items = data.get("items", [])
            
            if items:
                # Take first suggestion
                suggestion = items[0]
                
                # Get warehouses
                warehouses_res = self.get("/warehouses", token)
                warehouses = warehouses_res.json()
                warehouse = warehouses[0] if isinstance(warehouses, list) else warehouses.get("items", [])[0]
                
                payload = {
                    "items": [
                        {
                            "product_id": suggestion.get("product_id"),
                            "quantity": suggestion.get("suggested_qty"),
                            "unit": suggestion.get("unit"),
                            "est_price": suggestion.get("est_price")
                        }
                    ],
                    "warehouse_id": warehouse.get("id"),
                    "entity_id": "ent_ksc",
                    "source": "reorder",
                    "reason": "Replenishment from reorder suggestions",
                    "submit_now": True
                }
                
                create_res = self.post("/purchase-requisitions", token, payload)
                
                if create_res.status_code == 200:
                    pr_data = create_res.json()
                    if pr_data.get("source") == "reorder":
                        self.log_test("Reorder Create PR", True, f"Created {pr_data.get('number')} from reorder")
                    else:
                        self.log_test("Reorder Create PR", False, f"Source: {pr_data.get('source')}")
                else:
                    self.log_test("Reorder Create PR", False, f"Status {create_res.status_code}: {create_res.text}")
            else:
                self.log_test("Reorder Create PR", True, "No reorder suggestions to test (skipped)")
        else:
            self.log_test("Reorder Create PR", False, f"Status {res.status_code}: {res.text}")
    
    def test_special_order_create_pr(self):
        """Test POST /special-orders/{id}/create-pr"""
        print("\n=== SPECIAL ORDER → PR BRIDGE TESTS ===")
        token = self.tokens.get("admin@kainnusantara.id")
        if not token:
            self.log_test("Special Order Create PR", False, "No admin token")
            return
        
        # Get special orders
        res = self.get("/special-orders", token)
        
        if res.status_code == 200:
            data = res.json()
            items = data.get("items", [])
            
            # Find a confirmed special order without linked PR
            confirmed_so = None
            for so in items:
                if so.get("status") == "confirmed" and not so.get("linked_pr_id"):
                    confirmed_so = so
                    break
            
            if not confirmed_so:
                # Try to find any special order and approve it first
                for so in items:
                    if so.get("status") == "pending_approval":
                        # Approve it first
                        approve_res = self.post(f"/special-orders/{so.get('id')}/approve", token, {"notes": "Approved for test"})
                        if approve_res.status_code == 200:
                            confirmed_so = approve_res.json()
                            break
            
            if confirmed_so:
                so_id = confirmed_so.get("id")
                
                # Get warehouses
                warehouses_res = self.get("/warehouses", token)
                warehouses = warehouses_res.json()
                warehouse = warehouses[0] if isinstance(warehouses, list) else warehouses.get("items", [])[0]
                
                payload = {
                    "warehouse_id": warehouse.get("id"),
                    "est_price": 100000,
                    "needed_by_date": "2025-09-01",
                    "notes": "PR from special order test",
                    "submit_now": True
                }
                
                create_pr_res = self.post(f"/special-orders/{so_id}/create-pr", token, payload)
                
                if create_pr_res.status_code == 200:
                    result = create_pr_res.json()
                    pr = result.get("pr", {})
                    so = result.get("special_order", {})
                    
                    if pr.get("source") == "special_order" and so.get("linked_pr_number"):
                        self.log_test("Special Order Create PR", True, 
                                    f"Created {pr.get('number')} from SO {confirmed_so.get('number')}")
                        self.log_test("Special Order Create PR - Link", True, 
                                    f"SO linked to {so.get('linked_pr_number')}")
                    else:
                        self.log_test("Special Order Create PR", False, 
                                    f"PR source: {pr.get('source')}, SO link: {so.get('linked_pr_number')}")
                else:
                    self.log_test("Special Order Create PR", False, 
                                f"Status {create_pr_res.status_code}: {create_pr_res.text}")
            else:
                self.log_test("Special Order Create PR", True, "No confirmed special orders to test (skipped)")
        else:
            self.log_test("Special Order Create PR", False, f"Status {res.status_code}: {res.text}")
    
    def run_all_tests(self):
        """Run all tests"""
        print("=" * 80)
        print("DEPTH #2 PURCHASE REQUISITION BACKEND TESTS")
        print("=" * 80)
        
        self.test_auth()
        self.test_pr_list()
        self.test_pr_detail()
        self.test_pr_create()
        self.test_pr_submit()
        self.test_pr_approve_reject()
        self.test_pr_cancel()
        self.test_pr_convert_to_po()
        self.test_reorder_suggestions()
        self.test_reorder_create_pr()
        self.test_special_order_create_pr()
        
        print("\n" + "=" * 80)
        print(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        print("=" * 80)
        
        return self.tests_passed == self.tests_run

if __name__ == "__main__":
    tester = Depth2PRTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
