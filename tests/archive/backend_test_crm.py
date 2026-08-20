#!/usr/bin/env python3
"""
Backend API Test — CRM / Customer Management + Sales Force (KN_17)
===================================================================
Tests CRM endpoints via public URL:
1. Customer list with row-level scoping (sales sees only own customers)
2. Customer 360 with credit derivation
3. Create/Edit customer
4. Reassign customer (manager only)
5. Credit override request + approval
6. Collection worklist
7. Follow-up creation
8. Sales KPI & commission
9. Leaderboard (manager only)
10. Sales targets (manager only)
"""
import os
import sys
import requests
from datetime import datetime

# Use public URL from frontend/.env
BASE = os.environ.get("BACKEND_URL", "https://po-pdf-sender.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
PASS, FAIL = [], []

def ok(m):
    PASS.append(m)
    print(f"  ✅ [PASS] {m}")

def bad(m):
    FAIL.append(m)
    print(f"  ❌ [FAIL] {m}")

def info(m):
    print(f"  ℹ️  {m}")

class CRMTester:
    def __init__(self):
        self.session = requests.Session()
        self.token_admin = None
        self.token_manager = None
        self.token_sales = None
        self.sales_users = []
        self.test_customer_id = None
        
    def login(self, email, password="demo12345"):
        """Login and return token"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login {email} failed: {r.status_code}")
                return None
            data = r.json()
            token = data.get("token")
            if token:
                ok(f"Login {email}")
            return token
        except Exception as e:
            bad(f"Login {email} exception: {e}")
            return None
    
    def setup_tokens(self):
        """Login all test users"""
        self.token_admin = self.login("admin@kainnusantara.id")
        self.token_manager = self.login("manager@kainnusantara.id")
        self.token_sales = self.login("sales@kainnusantara.id")
        return all([self.token_admin, self.token_manager, self.token_sales])
    
    def get(self, endpoint, token, params=None):
        """GET request with token"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.get(f"{API}/{endpoint}", headers=headers, params=params, timeout=40)
            return r
        except requests.exceptions.Timeout:
            info(f"GET /{endpoint} timeout")
            return None
        except Exception as e:
            info(f"GET /{endpoint} exception: {e}")
            return None
    
    def post(self, endpoint, token, json_data):
        """POST request with token"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.post(f"{API}/{endpoint}", headers=headers, json=json_data, timeout=40)
            return r
        except requests.exceptions.Timeout:
            info(f"POST /{endpoint} timeout")
            return None
        except Exception as e:
            info(f"POST /{endpoint} exception: {e}")
            return None
    
    def patch(self, endpoint, token, json_data):
        """PATCH request with token"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.patch(f"{API}/{endpoint}", headers=headers, json=json_data, timeout=40)
            return r
        except requests.exceptions.Timeout:
            info(f"PATCH /{endpoint} timeout")
            return None
        except Exception as e:
            info(f"PATCH /{endpoint} exception: {e}")
            return None
    
    # ── Test 1: Sales users list ──────────────────────────────────────
    def test_sales_users(self):
        print("\n── Test 1: Sales Users List ──────────────────────────────")
        r = self.get("sales-users", self.token_admin)
        if not r or r.status_code != 200:
            bad(f"GET /sales-users failed: {r.status_code if r else 'no response'}")
            return False
        
        self.sales_users = r.json()
        if len(self.sales_users) >= 3:
            ok(f"Sales users list: {len(self.sales_users)} users")
        else:
            bad(f"Expected >= 3 sales users, got {len(self.sales_users)}")
        return True
    
    # ── Test 2: Customer list with row-level scoping ──────────────────
    def test_customer_list_scoping(self):
        print("\n── Test 2: Customer List + Row-Level Scoping ─────────────")
        
        # Admin sees all customers
        r_admin = self.get("customers", self.token_admin)
        if not r_admin or r_admin.status_code != 200:
            bad(f"Admin GET /customers failed: {r_admin.status_code if r_admin else 'no response'}")
            return False
        
        admin_customers = r_admin.json()
        if len(admin_customers) >= 5:
            ok(f"Admin sees all customers: {len(admin_customers)}")
        else:
            bad(f"Admin should see >= 5 customers, got {len(admin_customers)}")
        
        # Sales sees only own customers
        r_sales = self.get("customers", self.token_sales)
        if not r_sales or r_sales.status_code != 200:
            bad(f"Sales GET /customers failed: {r_sales.status_code if r_sales else 'no response'}")
            return False
        
        sales_customers = r_sales.json()
        if len(sales_customers) >= 1 and len(sales_customers) < len(admin_customers):
            ok(f"Sales sees only own customers: {len(sales_customers)} (< {len(admin_customers)})")
        else:
            bad(f"Sales scoping failed: sales={len(sales_customers)}, admin={len(admin_customers)}")
        
        # Verify all sales customers are assigned to user_sales_01
        all_assigned = all(c.get("assigned_sales_id") == "user_sales_01" for c in sales_customers)
        if all_assigned:
            ok("All sales customers assigned to user_sales_01")
        else:
            bad("Some sales customers not assigned to user_sales_01")
        
        # Verify customers have credit enrichment
        has_credit = all("credit" in c for c in sales_customers)
        if has_credit:
            ok("Customers have credit enrichment")
        else:
            bad("Some customers missing credit data")
        
        return True
    
    # ── Test 3: Customer filters ──────────────────────────────────────
    def test_customer_filters(self):
        print("\n── Test 3: Customer Filters ──────────────────────────────")
        
        # Filter by segment
        r = self.get("customers", self.token_admin, params={"segment": "Wholesale"})
        if r and r.status_code == 200:
            wholesale = r.json()
            ok(f"Segment filter: {len(wholesale)} Wholesale customers")
        else:
            bad("Segment filter failed")
        
        # Filter by credit status
        r = self.get("customers", self.token_admin, params={"credit_status": "warning"})
        if r and r.status_code == 200:
            warning = r.json()
            ok(f"Credit status filter: {len(warning)} warning customers")
        else:
            bad("Credit status filter failed")
        
        return True
    
    # ── Test 4: Create customer ───────────────────────────────────────
    def test_create_customer(self):
        print("\n── Test 4: Create Customer ───────────────────────────────")
        
        # Get first sales user for assignment
        if not self.sales_users:
            bad("No sales users available for customer creation")
            return False
        
        sales_id = self.sales_users[0]["id"]
        
        payload = {
            "name": f"PT CRM Test {datetime.now().strftime('%H%M%S')}",
            "segment": "Wholesale",
            "assigned_sales_id": sales_id,
            "pic_name": "Test PIC",
            "phone": "08123456789",
            "email": "test@crm.id",
            "city": "Jakarta",
            "address": "Jl Test",
            "credit_limit": 50000000,
            "payment_profile": {
                "allowed_methods": ["tempo"],
                "default_method": "tempo",
                "term_days": 30
            }
        }
        
        r = self.post("customers", self.token_admin, payload)
        if not r or r.status_code != 200:
            bad(f"Create customer failed: {r.status_code if r else 'no response'} {r.text[:200] if r else ''}")
            return False
        
        customer = r.json()
        self.test_customer_id = customer.get("id")
        
        if customer.get("name") == payload["name"]:
            ok(f"Customer created: {customer.get('name')} (ID: {self.test_customer_id[:8]})")
        else:
            bad("Customer creation response mismatch")
        
        if customer.get("assigned_sales_id") == sales_id:
            ok("Customer assigned to sales correctly")
        else:
            bad("Customer assignment failed")
        
        return True
    
    # ── Test 5: Customer 360 ──────────────────────────────────────────
    def test_customer_360(self):
        print("\n── Test 5: Customer 360 ──────────────────────────────────")
        
        if not self.test_customer_id:
            info("Skipping 360 test (no test customer)")
            return True
        
        r = self.get(f"customers/{self.test_customer_id}/360", self.token_admin)
        if not r or r.status_code != 200:
            bad(f"GET /customers/.../360 failed: {r.status_code if r else 'no response'}")
            return False
        
        c360 = r.json()
        
        # Check structure
        required_keys = ["credit", "order_history", "document_history", "special_price_history", 
                        "collection_followups", "credit_overrides", "stats"]
        missing = [k for k in required_keys if k not in c360]
        if not missing:
            ok("Customer 360 has all required sections")
        else:
            bad(f"Customer 360 missing: {missing}")
        
        # Check credit object
        credit = c360.get("credit", {})
        if "status" in credit and "ar_outstanding" in credit:
            ok(f"Credit derived: status={credit.get('status')}, AR={credit.get('ar_outstanding')}")
        else:
            bad("Credit derivation incomplete")
        
        # Check stats
        stats = c360.get("stats", {})
        if "total_orders" in stats and "lifetime_value" in stats:
            ok(f"Stats: {stats.get('total_orders')} orders, LTV={stats.get('lifetime_value')}")
        else:
            bad("Stats incomplete")
        
        return True
    
    # ── Test 6: Customer 360 access control ───────────────────────────
    def test_customer_360_access(self):
        print("\n── Test 6: Customer 360 Access Control ───────────────────")
        
        # Get a customer that belongs to sales user
        r = self.get("customers", self.token_sales)
        if not r or r.status_code != 200:
            bad("Cannot get sales customers for access test")
            return False
        
        sales_customers = r.json()
        if not sales_customers:
            info("No sales customers for access test")
            return True
        
        own_customer_id = sales_customers[0]["id"]
        
        # Sales can access own customer
        r = self.get(f"customers/{own_customer_id}/360", self.token_sales)
        if r and r.status_code == 200:
            ok("Sales can access own customer 360")
        else:
            bad(f"Sales cannot access own customer: {r.status_code if r else 'no response'}")
        
        # Sales cannot access test customer (belongs to different sales)
        # Check if test customer is actually assigned to a different sales user
        if self.test_customer_id:
            r_test = self.get(f"customers/{self.test_customer_id}/360", self.token_admin)
            if r_test and r_test.status_code == 200:
                test_cust = r_test.json()
                test_assigned = test_cust.get("assigned_sales_id")
                info(f"Test customer assigned to: {test_assigned}, sales user is: user_sales_01")
                
                if test_assigned == "user_sales_01":
                    info("Test customer is assigned to sales user, skipping 403 test")
                else:
                    r = self.get(f"customers/{self.test_customer_id}/360", self.token_sales)
                    if r and r.status_code == 403:
                        ok("Sales blocked from accessing other's customer (403)")
                    else:
                        bad(f"Sales access control failed: expected 403, got {r.status_code if r else 'no response'}")
        
        return True
    
    # ── Test 7: Edit customer ─────────────────────────────────────────
    def test_edit_customer(self):
        print("\n── Test 7: Edit Customer ─────────────────────────────────")
        
        if not self.test_customer_id:
            info("Skipping edit test (no test customer)")
            return True
        
        payload = {
            "data": {
                "credit_limit": 75000000,
                "tags": ["test", "crm"]
            }
        }
        
        r = self.patch(f"customers/{self.test_customer_id}", self.token_admin, payload)
        if not r or r.status_code != 200:
            bad(f"Edit customer failed: {r.status_code if r else 'no response'}")
            return False
        
        customer = r.json()
        if customer.get("credit_limit") == 75000000:
            ok("Customer credit limit updated")
        else:
            bad("Customer update failed")
        
        return True
    
    # ── Test 8: Reassign customer (manager only) ──────────────────────
    def test_reassign_customer(self):
        print("\n── Test 8: Reassign Customer (Manager) ───────────────────")
        
        if not self.test_customer_id or len(self.sales_users) < 2:
            info("Skipping reassign test (need test customer + 2 sales)")
            return True
        
        # Get current assignment
        r = self.get(f"customers/{self.test_customer_id}/360", self.token_admin)
        if not r or r.status_code != 200:
            bad("Cannot get customer for reassign test")
            return False
        
        current_sales = r.json().get("assigned_sales_id")
        new_sales = next((s["id"] for s in self.sales_users if s["id"] != current_sales), None)
        
        if not new_sales:
            info("Cannot find different sales for reassign")
            return True
        
        payload = {
            "assigned_sales_id": new_sales,
            "reason": "Test reassignment"
        }
        
        r = self.post(f"customers/{self.test_customer_id}/reassign", self.token_manager, payload)
        if not r or r.status_code != 200:
            bad(f"Reassign failed: {r.status_code if r else 'no response'}")
            return False
        
        customer = r.json()
        if customer.get("assigned_sales_id") == new_sales:
            ok(f"Customer reassigned to {new_sales[:8]}")
        else:
            bad("Reassignment did not update assigned_sales_id")
        
        # Test sales cannot reassign (403)
        r = self.post(f"customers/{self.test_customer_id}/reassign", self.token_sales, payload)
        if r and r.status_code == 403:
            ok("Sales blocked from reassigning (403)")
        else:
            bad(f"Sales reassign access control failed: expected 403, got {r.status_code if r else 'no response'}")
        
        return True
    
    # ── Test 9: Credit override request ───────────────────────────────
    def test_credit_override(self):
        print("\n── Test 9: Credit Override Request ───────────────────────")
        
        # Get a customer owned by sales user
        r = self.get("customers", self.token_sales)
        if not r or r.status_code != 200 or not r.json():
            info("No sales customers for override test")
            return True
        
        customer_id = r.json()[0]["id"]
        
        payload = {
            "customer_id": customer_id,
            "amount": 5000000,
            "reason": "Test override - PO besar approved",
            "evidence_url": ""
        }
        
        r = self.post(f"customers/{customer_id}/credit-override", self.token_sales, payload)
        if not r or r.status_code != 200:
            bad(f"Credit override request failed: {r.status_code if r else 'no response'}")
            return False
        
        override = r.json()
        override_id = override.get("id")
        
        if override.get("status") == "pending":
            ok(f"Credit override requested (ID: {override_id[:8]})")
        else:
            bad("Override status should be pending")
        
        # Test approval by manager
        if override_id:
            decision_payload = {
                "decision": "approve",
                "reason": "Test approval"
            }
            
            r = self.post(f"credit-overrides/{override_id}/decision", self.token_manager, decision_payload)
            if r and r.status_code == 200:
                result = r.json()
                if result.get("status") == "approved":
                    ok("Credit override approved by manager")
                else:
                    bad("Override approval did not change status")
            else:
                bad(f"Override approval failed: {r.status_code if r else 'no response'}")
        
        return True
    
    # ── Test 10: Credit overrides list ────────────────────────────────
    def test_credit_overrides_list(self):
        print("\n── Test 10: Credit Overrides List ────────────────────────")
        
        # Manager can see all
        r = self.get("credit-overrides", self.token_manager)
        if r and r.status_code == 200:
            overrides = r.json()
            ok(f"Manager sees credit overrides: {len(overrides)}")
        else:
            bad("Manager cannot list overrides")
        
        # Sales sees only own requests
        r = self.get("credit-overrides", self.token_sales)
        if r and r.status_code == 200:
            sales_overrides = r.json()
            ok(f"Sales sees own overrides: {len(sales_overrides)}")
        else:
            bad("Sales cannot list own overrides")
        
        return True
    
    # ── Test 11: Collection worklist ──────────────────────────────────
    def test_collection_worklist(self):
        print("\n── Test 11: Collection Worklist ──────────────────────────")
        
        r = self.get("collection-worklist", self.token_admin)
        if not r or r.status_code != 200:
            bad(f"GET /collection-worklist failed: {r.status_code if r else 'no response'}")
            return False
        
        worklist = r.json()
        ok(f"Collection worklist: {len(worklist)} items")
        
        # Check structure
        if worklist:
            item = worklist[0]
            required = ["order_id", "customer_id", "outstanding", "due_date", "days_late", "overdue"]
            missing = [k for k in required if k not in item]
            if not missing:
                ok("Worklist items have required fields")
            else:
                bad(f"Worklist items missing: {missing}")
        
        return True
    
    # ── Test 12: Follow-up creation ───────────────────────────────────
    def test_followup(self):
        print("\n── Test 12: Follow-up Creation ───────────────────────────")
        
        # Get a customer owned by sales
        r = self.get("customers", self.token_sales)
        if not r or r.status_code != 200 or not r.json():
            info("No sales customers for followup test")
            return True
        
        customer_id = r.json()[0]["id"]
        
        payload = {
            "customer_id": customer_id,
            "note": "Test follow-up call",
            "outcome": "contacted",
            "next_action_date": "2025-09-01"
        }
        
        r = self.post(f"customers/{customer_id}/followups", self.token_sales, payload)
        if not r or r.status_code != 200:
            bad(f"Follow-up creation failed: {r.status_code if r else 'no response'}")
            return False
        
        followup = r.json()
        if followup.get("note") == payload["note"]:
            ok(f"Follow-up created (ID: {followup.get('id', '')[:8]})")
        else:
            bad("Follow-up creation response mismatch")
        
        return True
    
    # ── Test 13: Sales KPI ────────────────────────────────────────────
    def test_sales_kpi(self):
        print("\n── Test 13: Sales KPI ────────────────────────────────────")
        
        # Sales user gets own KPI
        r = self.get("sales/kpi", self.token_sales)
        if not r or r.status_code != 200:
            bad(f"GET /sales/kpi failed: {r.status_code if r else 'no response'}")
            return False
        
        kpi = r.json()
        
        # Check KPI structure
        required = ["sales_id", "total_sales", "total_collected", "collection_rate", 
                   "ar_outstanding", "customers_count", "orders_count"]
        missing = [k for k in required if k not in kpi]
        if not missing:
            ok(f"Sales KPI complete: {kpi.get('customers_count')} customers, {kpi.get('orders_count')} orders")
        else:
            bad(f"Sales KPI missing: {missing}")
        
        # Verify sales_id is forced to own ID
        if kpi.get("sales_id") == "user_sales_01":
            ok("Sales KPI forced to own ID (user_sales_01)")
        else:
            bad(f"Sales KPI ID mismatch: {kpi.get('sales_id')}")
        
        return True
    
    # ── Test 14: Sales commission ─────────────────────────────────────
    def test_sales_commission(self):
        print("\n── Test 14: Sales Commission ─────────────────────────────")
        
        period = datetime.now().strftime("%Y-%m")
        
        r = self.get("sales/commission", self.token_sales, params={"period": period})
        if not r or r.status_code != 200:
            bad(f"GET /sales/commission failed: {r.status_code if r else 'no response'}")
            return False
        
        comm = r.json()
        
        # Check commission structure
        required = ["basis", "base_amount", "target_amount", "achievement_pct", 
                   "applied_rate", "commission", "total_incentive"]
        missing = [k for k in required if k not in comm]
        if not missing:
            ok(f"Commission: basis={comm.get('basis')}, achievement={comm.get('achievement_pct')}%, rate={comm.get('applied_rate')}%")
        else:
            bad(f"Commission missing: {missing}")
        
        # Verify basis is collection
        if comm.get("basis") == "collection":
            ok("Commission basis is collection (pencairan)")
        else:
            bad(f"Commission basis unexpected: {comm.get('basis')}")
        
        return True
    
    # ── Test 15: Leaderboard (manager only) ───────────────────────────
    def test_leaderboard(self):
        print("\n── Test 15: Leaderboard (Manager Only) ───────────────────")
        
        # Manager can access
        r = self.get("sales/leaderboard", self.token_manager)
        if not r or r.status_code != 200:
            bad(f"Manager GET /sales/leaderboard failed: {r.status_code if r else 'no response'}")
            return False
        
        board = r.json()
        if len(board) >= 3:
            ok(f"Leaderboard: {len(board)} sales ranked")
        else:
            bad(f"Leaderboard should have >= 3 entries, got {len(board)}")
        
        # Check ranking
        if board:
            ranks = [b.get("rank") for b in board]
            if ranks == list(range(1, len(board) + 1)):
                ok("Leaderboard ranks correct (1, 2, 3...)")
            else:
                bad(f"Leaderboard ranks incorrect: {ranks}")
        
        # Sales cannot access (403)
        r = self.get("sales/leaderboard", self.token_sales)
        if r and r.status_code == 403:
            ok("Sales blocked from leaderboard (403)")
        else:
            bad(f"Sales leaderboard access control failed: expected 403, got {r.status_code if r else 'no response'}")
        
        return True
    
    # ── Test 16: Sales targets (manager only) ─────────────────────────
    def test_sales_targets(self):
        print("\n── Test 16: Sales Targets (Manager Only) ─────────────────")
        
        if not self.sales_users:
            info("No sales users for target test")
            return True
        
        sales_id = self.sales_users[0]["id"]
        period = "2026-12"
        
        payload = {
            "sales_id": sales_id,
            "period": period,
            "target_sales_amount": 100000000,
            "target_collection_amount": 80000000,
            "target_new_customers": 5
        }
        
        # Manager can set target
        r = self.post("sales-targets", self.token_manager, payload)
        if not r or r.status_code != 200:
            bad(f"Manager POST /sales-targets failed: {r.status_code if r else 'no response'}")
            return False
        
        target = r.json()
        if target.get("target_collection_amount") == 80000000:
            ok(f"Sales target set: {sales_id[:8]} for {period}")
        else:
            bad("Sales target creation response mismatch")
        
        # Sales cannot set target (403)
        r = self.post("sales-targets", self.token_sales, payload)
        if r and r.status_code == 403:
            ok("Sales blocked from setting targets (403)")
        else:
            bad(f"Sales target access control failed: expected 403, got {r.status_code if r else 'no response'}")
        
        return True
    
    def run_all(self):
        """Run all tests"""
        print(f"\n{'='*70}")
        print(f"CRM Backend API Tests — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Base URL: {BASE}")
        print(f"{'='*70}")
        
        if not self.setup_tokens():
            bad("Failed to setup test tokens")
            return False
        
        # Run all tests
        self.test_sales_users()
        self.test_customer_list_scoping()
        self.test_customer_filters()
        self.test_create_customer()
        self.test_customer_360()
        self.test_customer_360_access()
        self.test_edit_customer()
        self.test_reassign_customer()
        self.test_credit_override()
        self.test_credit_overrides_list()
        self.test_collection_worklist()
        self.test_followup()
        self.test_sales_kpi()
        self.test_sales_commission()
        self.test_leaderboard()
        self.test_sales_targets()
        
        # Summary
        print(f"\n{'='*70}")
        print(f"RESULTS: {len(PASS)} PASS / {len(FAIL)} FAIL")
        print(f"{'='*70}")
        
        if FAIL:
            print("\nFailed tests:")
            for f in FAIL:
                print(f"  ❌ {f}")
        
        return len(FAIL) == 0

def main():
    tester = CRMTester()
    success = tester.run_all()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
