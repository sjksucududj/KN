#!/usr/bin/env python3
"""
R0 Return Policy Engine Backend Test
Testing: Supplier return policy (embedded), Sales return policy CRUD,
         Eligibility check, Policy snapshot in sales returns, Auth validation
"""
import requests
import sys
from datetime import datetime, timedelta

# Use public endpoint from frontend/.env
BASE_URL = "https://inventory-refund.preview.emergentagent.com/api"

# Test credentials from test_credentials.md
TEST_USER = {"email": "admin@kainnusantara.id", "password": "demo12345"}


class R0Tester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        self.results = []
        self.created_ids = {
            "suppliers": [],
            "policies": [],
            "returns": []
        }

    def log(self, status, test_name, details=""):
        """Log test result"""
        self.tests_run += 1
        if status == "PASS":
            self.tests_passed += 1
            print(f"✅ PASS: {test_name}")
        else:
            print(f"❌ FAIL: {test_name}")
        if details:
            print(f"   {details}")
        self.results.append({"test": test_name, "status": status, "details": details})

    def get_headers(self):
        """Get auth headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def test_health(self):
        """Test API health endpoint"""
        try:
            r = requests.get(f"{BASE_URL}/", timeout=10)
            if r.status_code == 200:
                self.log("PASS", "API Health Check", f"Status: {r.status_code}")
                return True
            else:
                self.log("FAIL", "API Health Check", f"Status: {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "API Health Check", f"Error: {str(e)}")
            return False

    def test_auth(self):
        """Test authentication"""
        try:
            r = requests.post(f"{BASE_URL}/auth/login", json=TEST_USER, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "token" in data:
                    self.token = data["token"]
                    self.log("PASS", "Auth - Login", f"User: {data.get('user', {}).get('name', 'N/A')}")
                    return True
                else:
                    self.log("FAIL", "Auth - Login", f"Missing 'token' field")
                    return False
            self.log("FAIL", "Auth - Login", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Auth - Login", f"Error: {str(e)}")
            return False

    # ─── SUPPLIER RETURN POLICY TESTS ────────────────────────────────────────

    def test_create_supplier_with_return_policy(self):
        """Test POST /api/suppliers with origin_type=import, country, nested return_policy"""
        try:
            payload = {
                "name": f"Test Import Supplier {datetime.now().strftime('%H%M%S')}",
                "npwp": "12.345.678.9-012.345",
                "pic_name": "John Doe",
                "phone": "081234567890",
                "email": "test@supplier.com",
                "address": "Test Address",
                "city": "Shanghai",
                "goods_type": "Kain Import",
                "payment_term_code": "",
                "lead_time_days": 30,
                "origin_type": "import",
                "country": "China",
                "return_policy": {
                    "window_days": 45,
                    "refund_modes": ["ap_credit", "cash"],
                    "returnable_to_supplier": False,
                    "rma_required": True,
                    "restocking_fee_pct": 15.5,
                    "condition_requirements": "Original packaging required",
                    "custom_fields": {
                        "min_defect_rate": "5%",
                        "inspection_location": "warehouse"
                    },
                    "notes": "Import goods - difficult to return"
                }
            }
            
            r = requests.post(f"{BASE_URL}/suppliers", json=payload, 
                            headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                supplier_id = data.get("id")
                
                # Verify all fields persisted
                checks = []
                if data.get("origin_type") != "import":
                    checks.append("origin_type not 'import'")
                if data.get("country") != "China":
                    checks.append("country not 'China'")
                
                rp = data.get("return_policy", {})
                if rp.get("window_days") != 45:
                    checks.append(f"window_days={rp.get('window_days')} (expected 45)")
                if rp.get("returnable_to_supplier") != False:
                    checks.append("returnable_to_supplier not False")
                if rp.get("restocking_fee_pct") != 15.5:
                    checks.append(f"restocking_fee_pct={rp.get('restocking_fee_pct')} (expected 15.5)")
                
                cf = rp.get("custom_fields", {})
                if cf.get("min_defect_rate") != "5%":
                    checks.append("custom_fields.min_defect_rate missing")
                
                if checks:
                    self.log("FAIL", "Supplier - Create with Return Policy", 
                           f"Field issues: {', '.join(checks)}")
                    return False, None
                
                self.created_ids["suppliers"].append(supplier_id)
                self.log("PASS", "Supplier - Create with Return Policy", 
                       f"ID: {supplier_id}, origin=import, country=China, custom_fields OK")
                return True, supplier_id
            else:
                self.log("FAIL", "Supplier - Create with Return Policy", 
                       f"Status: {r.status_code}, Body: {r.text[:300]}")
                return False, None
        except Exception as e:
            self.log("FAIL", "Supplier - Create with Return Policy", f"Error: {str(e)}")
            return False, None

    def test_get_supplier_return_policy(self, supplier_id):
        """Test GET /api/suppliers/{id}/return-policy - effective policy resolution"""
        try:
            r = requests.get(f"{BASE_URL}/suppliers/{supplier_id}/return-policy", 
                           headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                
                # Verify response structure
                checks = []
                if data.get("origin_type") != "import":
                    checks.append("origin_type not 'import'")
                if data.get("returnable_to_supplier") != False:
                    checks.append("returnable_to_supplier not False")
                if data.get("recommend_regrade_local") != True:
                    checks.append("recommend_regrade_local not True (expected for import + non-returnable)")
                
                policy = data.get("policy", {})
                if policy.get("window_days") != 45:
                    checks.append(f"policy.window_days={policy.get('window_days')} (expected 45)")
                
                if checks:
                    self.log("FAIL", "Supplier - Get Return Policy", 
                           f"Issues: {', '.join(checks)}")
                    return False
                
                self.log("PASS", "Supplier - Get Return Policy", 
                       f"origin=import, returnable=False, recommend_regrade_local=True")
                return True
            else:
                self.log("FAIL", "Supplier - Get Return Policy", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Supplier - Get Return Policy", f"Error: {str(e)}")
            return False

    def test_update_supplier_return_policy(self, supplier_id):
        """Test PATCH /api/suppliers/{id} with return_policy updates"""
        try:
            payload = {
                "data": {
                    "return_policy": {
                        "window_days": 60,
                        "refund_modes": ["cash", "ap_credit", "none"],  # Test normalization
                        "returnable_to_supplier": True,
                        "restocking_fee_pct": 20.0
                    }
                }
            }
            
            r = requests.patch(f"{BASE_URL}/suppliers/{supplier_id}", json=payload,
                             headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                rp = data.get("return_policy", {})
                
                checks = []
                if rp.get("window_days") != 60:
                    checks.append(f"window_days={rp.get('window_days')} (expected 60)")
                
                # Verify refund_modes normalized to canonical values
                modes = rp.get("refund_modes", [])
                if not all(m in ["cash", "ap_credit", "none"] for m in modes):
                    checks.append(f"refund_modes not normalized: {modes}")
                
                if checks:
                    self.log("FAIL", "Supplier - Update Return Policy", 
                           f"Issues: {', '.join(checks)}")
                    return False
                
                self.log("PASS", "Supplier - Update Return Policy", 
                       f"window_days=60, refund_modes normalized OK")
                return True
            else:
                self.log("FAIL", "Supplier - Update Return Policy", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Supplier - Update Return Policy", f"Error: {str(e)}")
            return False

    # ─── SALES RETURN POLICY CRUD TESTS ──────────────────────────────────────

    def test_create_sales_return_policy_global(self):
        """Test POST /api/sales-return-policies (global scope)"""
        try:
            payload = {
                "name": f"Test Global Policy {datetime.now().strftime('%H%M%S')}",
                "scope": "global",
                "scope_ref": "",
                "window_days": 30,
                "allowed_return_types": ["retur", "bs", "penggantian"],
                "allowed_outcomes": ["refund", "store_credit"],
                "restocking_fee_pct": 5.0,
                "require_inspection": True,
                "enforce_window": False,
                "link_to_supplier_window": False,
                "condition_requirements": "Good condition required",
                "custom_fields": {"max_value": "5000000"},
                "notes": "Test global policy"
            }
            
            r = requests.post(f"{BASE_URL}/sales-return-policies", json=payload,
                            headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                policy_id = data.get("id")
                
                checks = []
                if data.get("scope") != "global":
                    checks.append("scope not 'global'")
                if data.get("window_days") != 30:
                    checks.append(f"window_days={data.get('window_days')}")
                if data.get("require_inspection") != True:
                    checks.append("require_inspection not True")
                
                if checks:
                    self.log("FAIL", "Sales Policy - Create Global", 
                           f"Issues: {', '.join(checks)}")
                    return False, None
                
                self.created_ids["policies"].append(policy_id)
                self.log("PASS", "Sales Policy - Create Global", 
                       f"ID: {policy_id}, scope=global, window_days=30")
                return True, policy_id
            else:
                self.log("FAIL", "Sales Policy - Create Global", 
                       f"Status: {r.status_code}, Body: {r.text[:300]}")
                return False, None
        except Exception as e:
            self.log("FAIL", "Sales Policy - Create Global", f"Error: {str(e)}")
            return False, None

    def test_create_sales_return_policy_category(self):
        """Test POST /api/sales-return-policies (category scope with scope_ref)"""
        try:
            payload = {
                "name": f"Test Category Policy {datetime.now().strftime('%H%M%S')}",
                "scope": "category",
                "scope_ref": "Kain",
                "window_days": 45,
                "allowed_return_types": ["retur", "garansi"],
                "allowed_outcomes": ["refund", "store_credit", "nego"],
                "restocking_fee_pct": 10.0,
                "require_inspection": True,
                "enforce_window": True,
                "link_to_supplier_window": True,
                "notes": "Test category policy"
            }
            
            r = requests.post(f"{BASE_URL}/sales-return-policies", json=payload,
                            headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                policy_id = data.get("id")
                
                checks = []
                if data.get("scope") != "category":
                    checks.append("scope not 'category'")
                if data.get("scope_ref") != "Kain":
                    checks.append(f"scope_ref={data.get('scope_ref')} (expected 'Kain')")
                if data.get("window_days") != 45:
                    checks.append(f"window_days={data.get('window_days')}")
                
                if checks:
                    self.log("FAIL", "Sales Policy - Create Category", 
                           f"Issues: {', '.join(checks)}")
                    return False, None
                
                self.created_ids["policies"].append(policy_id)
                self.log("PASS", "Sales Policy - Create Category", 
                       f"ID: {policy_id}, scope=category, scope_ref=Kain")
                return True, policy_id
            else:
                self.log("FAIL", "Sales Policy - Create Category", 
                       f"Status: {r.status_code}, Body: {r.text[:300]}")
                return False, None
        except Exception as e:
            self.log("FAIL", "Sales Policy - Create Category", f"Error: {str(e)}")
            return False, None

    def test_list_sales_return_policies(self):
        """Test GET /api/sales-return-policies (list - bare array)"""
        try:
            r = requests.get(f"{BASE_URL}/sales-return-policies", 
                           headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                
                if not isinstance(data, list):
                    self.log("FAIL", "Sales Policy - List", 
                           f"Expected bare array, got: {type(data)}")
                    return False
                
                # Should have at least the seeded policies + our test policies
                if len(data) < 2:
                    self.log("FAIL", "Sales Policy - List", 
                           f"Expected >=2 policies, got {len(data)}")
                    return False
                
                self.log("PASS", "Sales Policy - List", 
                       f"Returned {len(data)} policies (bare array)")
                return True
            else:
                self.log("FAIL", "Sales Policy - List", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Sales Policy - List", f"Error: {str(e)}")
            return False

    def test_get_sales_return_policy(self, policy_id):
        """Test GET /api/sales-return-policies/{id} (detail)"""
        try:
            r = requests.get(f"{BASE_URL}/sales-return-policies/{policy_id}", 
                           headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                
                if data.get("id") != policy_id:
                    self.log("FAIL", "Sales Policy - Get Detail", 
                           f"ID mismatch: {data.get('id')} != {policy_id}")
                    return False
                
                self.log("PASS", "Sales Policy - Get Detail", 
                       f"ID: {policy_id}, name: {data.get('name')}")
                return True
            else:
                self.log("FAIL", "Sales Policy - Get Detail", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Sales Policy - Get Detail", f"Error: {str(e)}")
            return False

    def test_update_sales_return_policy(self, policy_id):
        """Test PATCH /api/sales-return-policies/{id} (update)"""
        try:
            payload = {
                "data": {
                    "window_days": 60,
                    "restocking_fee_pct": 15.0,
                    "enforce_window": True
                }
            }
            
            r = requests.patch(f"{BASE_URL}/sales-return-policies/{policy_id}", 
                             json=payload, headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                
                checks = []
                if data.get("window_days") != 60:
                    checks.append(f"window_days={data.get('window_days')} (expected 60)")
                if data.get("restocking_fee_pct") != 15.0:
                    checks.append(f"restocking_fee_pct={data.get('restocking_fee_pct')}")
                if data.get("enforce_window") != True:
                    checks.append("enforce_window not True")
                
                if checks:
                    self.log("FAIL", "Sales Policy - Update", 
                           f"Issues: {', '.join(checks)}")
                    return False
                
                self.log("PASS", "Sales Policy - Update", 
                       f"window_days=60, restocking_fee_pct=15.0, enforce_window=True")
                return True
            else:
                self.log("FAIL", "Sales Policy - Update", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Sales Policy - Update", f"Error: {str(e)}")
            return False

    def test_delete_sales_return_policy(self, policy_id):
        """Test DELETE /api/sales-return-policies/{id} (soft deactivate)"""
        try:
            r = requests.delete(f"{BASE_URL}/sales-return-policies/{policy_id}", 
                              headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                
                if data.get("status") != "inactive":
                    self.log("FAIL", "Sales Policy - Delete (Soft)", 
                           f"Status not 'inactive': {data.get('status')}")
                    return False
                
                # Verify it's hidden from list (without include_inactive)
                r2 = requests.get(f"{BASE_URL}/sales-return-policies", 
                                headers=self.get_headers(), timeout=10)
                if r2.status_code == 200:
                    policies = r2.json()
                    if any(p.get("id") == policy_id for p in policies):
                        self.log("FAIL", "Sales Policy - Delete (Soft)", 
                               "Inactive policy still in list")
                        return False
                
                self.log("PASS", "Sales Policy - Delete (Soft)", 
                       f"Status=inactive, hidden from list")
                return True
            else:
                self.log("FAIL", "Sales Policy - Delete (Soft)", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Sales Policy - Delete (Soft)", f"Error: {str(e)}")
            return False

    # ─── VALIDATION TESTS ────────────────────────────────────────────────────

    def test_validation_category_empty_scope_ref(self):
        """Test POST with scope=category and empty scope_ref returns 400"""
        try:
            payload = {
                "name": "Invalid Category Policy",
                "scope": "category",
                "scope_ref": "",  # Empty - should fail
                "window_days": 30
            }
            
            r = requests.post(f"{BASE_URL}/sales-return-policies", json=payload,
                            headers=self.get_headers(), timeout=10)
            
            if r.status_code == 400:
                self.log("PASS", "Validation - Category Empty Scope Ref", 
                       "Correctly rejected with 400")
                return True
            else:
                self.log("FAIL", "Validation - Category Empty Scope Ref", 
                       f"Expected 400, got {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "Validation - Category Empty Scope Ref", f"Error: {str(e)}")
            return False

    def test_validation_invalid_scope(self):
        """Test POST with invalid scope returns 400"""
        try:
            payload = {
                "name": "Invalid Scope Policy",
                "scope": "invalid_scope",
                "window_days": 30
            }
            
            r = requests.post(f"{BASE_URL}/sales-return-policies", json=payload,
                            headers=self.get_headers(), timeout=10)
            
            if r.status_code == 400:
                self.log("PASS", "Validation - Invalid Scope", 
                       "Correctly rejected with 400")
                return True
            else:
                self.log("FAIL", "Validation - Invalid Scope", 
                       f"Expected 400, got {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "Validation - Invalid Scope", f"Error: {str(e)}")
            return False

    # ─── ELIGIBILITY TESTS ───────────────────────────────────────────────────

    def test_eligibility_check(self):
        """Test GET /api/sales-return-policies/eligibility"""
        try:
            # Get any order (eligibility check works on any order)
            r = requests.get(f"{BASE_URL}/sales-orders", 
                           params={"limit": 1},
                           headers=self.get_headers(), timeout=10)
            
            if r.status_code != 200:
                self.log("FAIL", "Eligibility - Check", 
                       f"Failed to get orders: {r.status_code}")
                return False
            
            orders = r.json()
            if isinstance(orders, dict):
                orders = orders.get("items", [])
            
            if not orders:
                self.log("FAIL", "Eligibility - Check", 
                       "No orders found for testing")
                return False
            
            order_id = orders[0].get("id")
            
            # Check eligibility
            r = requests.get(f"{BASE_URL}/sales-return-policies/eligibility", 
                           params={"order_id": order_id, "return_type": "retur"},
                           headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                
                # Verify required fields
                required_fields = [
                    "eligible", "within_window", "deadline", "days_remaining",
                    "window_days", "require_inspection", "policy", "warnings"
                ]
                missing = [f for f in required_fields if f not in data]
                
                if missing:
                    self.log("FAIL", "Eligibility - Check", 
                           f"Missing fields: {', '.join(missing)}")
                    return False
                
                # Verify policy snapshot is non-empty
                policy = data.get("policy", {})
                if not policy or not policy.get("name"):
                    self.log("FAIL", "Eligibility - Check", 
                           "Policy snapshot empty or missing name")
                    return False
                
                self.log("PASS", "Eligibility - Check", 
                       f"All fields present, policy: {policy.get('name')}, "
                       f"eligible: {data.get('eligible')}, within_window: {data.get('within_window')}")
                return True
            else:
                self.log("FAIL", "Eligibility - Check", 
                       f"Status: {r.status_code}, Body: {r.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", "Eligibility - Check", f"Error: {str(e)}")
            return False

    # ─── SALES RETURN CREATION TESTS ─────────────────────────────────────────

    def test_sales_return_with_policy_snapshot(self):
        """Test POST /api/sales-returns attaches policy_snapshot, return_deadline, policy_eligibility"""
        try:
            # Get a confirmed/approved order (return requires confirmed+ status)
            r = requests.get(f"{BASE_URL}/sales-orders", 
                           params={"limit": 10},
                           headers=self.get_headers(), timeout=10)
            
            if r.status_code != 200:
                self.log("FAIL", "Sales Return - Policy Snapshot", 
                       f"Failed to get orders: {r.status_code}")
                return False
            
            orders = r.json()
            if isinstance(orders, dict):
                orders = orders.get("items", [])
            
            # Find a confirmed/approved/reserved order
            valid_statuses = ["confirmed", "partially_shipped", "done", "fulfilled", "dispatched", "packed"]
            order = None
            for o in orders:
                if o.get("status") in valid_statuses:
                    order = o
                    break
            
            if not order:
                self.log("FAIL", "Sales Return - Policy Snapshot", 
                       f"No confirmed/approved orders found (need status in {valid_statuses})")
                return False
            order_id = order.get("id")
            
            # Get first item
            items = order.get("items", [])
            if not items:
                self.log("FAIL", "Sales Return - Policy Snapshot", 
                       "Order has no items")
                return False
            
            item = items[0]
            
            # Create sales return
            payload = {
                "order_id": order_id,
                "return_type": "retur",
                "items": [{
                    "product_id": item.get("product_id"),
                    "product_name": item.get("product_name", "Test Product"),
                    "quantity_returned": 1.0,
                    "unit": item.get("unit", "meter"),
                    "reason": "Test return",
                    "condition": "ok"
                }],
                "notes": "Test return for R0",
                "submit_now": False
            }
            
            r = requests.post(f"{BASE_URL}/sales-returns", json=payload,
                            headers=self.get_headers(), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                return_id = data.get("id")
                
                # Verify policy_snapshot, return_deadline, policy_eligibility
                checks = []
                
                policy_snapshot = data.get("policy_snapshot", {})
                if not policy_snapshot or not policy_snapshot.get("name"):
                    checks.append("policy_snapshot empty or missing name")
                
                return_deadline = data.get("return_deadline", "")
                if not return_deadline:
                    checks.append("return_deadline empty")
                
                policy_eligibility = data.get("policy_eligibility", {})
                if not isinstance(policy_eligibility, dict):
                    checks.append("policy_eligibility not a dict")
                elif "eligible" not in policy_eligibility:
                    checks.append("policy_eligibility missing 'eligible' field")
                
                if checks:
                    self.log("FAIL", "Sales Return - Policy Snapshot", 
                           f"Issues: {', '.join(checks)}")
                    return False
                
                self.created_ids["returns"].append(return_id)
                self.log("PASS", "Sales Return - Policy Snapshot", 
                       f"ID: {return_id}, policy: {policy_snapshot.get('name')}, "
                       f"deadline: {return_deadline[:10]}, eligible: {policy_eligibility.get('eligible')}")
                return True
            else:
                self.log("FAIL", "Sales Return - Policy Snapshot", 
                       f"Status: {r.status_code}, Body: {r.text[:300]}")
                return False
        except Exception as e:
            self.log("FAIL", "Sales Return - Policy Snapshot", f"Error: {str(e)}")
            return False

    # ─── AUTH TESTS ──────────────────────────────────────────────────────────

    def test_auth_rejection(self):
        """Test all new endpoints reject requests without valid Bearer token"""
        try:
            endpoints = [
                ("GET", "/sales-return-policies"),
                ("GET", "/sales-return-policies/eligibility?order_id=test"),
                ("GET", "/suppliers/test/return-policy"),
            ]
            
            failed = []
            for method, endpoint in endpoints:
                if method == "GET":
                    r = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
                else:
                    r = requests.post(f"{BASE_URL}{endpoint}", json={}, timeout=10)
                
                if r.status_code not in [401, 403]:
                    failed.append(f"{method} {endpoint} returned {r.status_code} (expected 401/403)")
            
            if failed:
                self.log("FAIL", "Auth - Rejection Without Token", 
                       f"Issues: {'; '.join(failed)}")
                return False
            
            self.log("PASS", "Auth - Rejection Without Token", 
                   f"All {len(endpoints)} endpoints correctly reject unauthorized requests")
            return True
        except Exception as e:
            self.log("FAIL", "Auth - Rejection Without Token", f"Error: {str(e)}")
            return False

    # ─── MAIN TEST RUNNER ────────────────────────────────────────────────────

    def run_all_tests(self):
        """Run all R0 Return Policy Engine tests"""
        print("=" * 80)
        print("R0 RETURN POLICY ENGINE BACKEND TEST")
        print("Testing: Supplier return policy, Sales return policy CRUD,")
        print("         Eligibility check, Policy snapshot, Auth validation")
        print("=" * 80)
        print()

        # Health check
        if not self.test_health():
            print("\n❌ API health check failed. Stopping tests.")
            return False

        # Auth test
        print("\n--- Authentication Test ---")
        if not self.test_auth():
            print("\n❌ Admin auth failed. Cannot proceed with API tests.")
            return False

        # Auth rejection test
        print("\n--- Auth Rejection Tests ---")
        self.test_auth_rejection()

        # Supplier return policy tests
        print("\n--- Supplier Return Policy Tests ---")
        success, supplier_id = self.test_create_supplier_with_return_policy()
        if success and supplier_id:
            self.test_get_supplier_return_policy(supplier_id)
            self.test_update_supplier_return_policy(supplier_id)

        # Sales return policy CRUD tests
        print("\n--- Sales Return Policy CRUD Tests ---")
        success_global, global_policy_id = self.test_create_sales_return_policy_global()
        success_category, category_policy_id = self.test_create_sales_return_policy_category()
        self.test_list_sales_return_policies()
        
        if success_global and global_policy_id:
            self.test_get_sales_return_policy(global_policy_id)
            self.test_update_sales_return_policy(global_policy_id)
            self.test_delete_sales_return_policy(global_policy_id)

        # Validation tests
        print("\n--- Validation Tests ---")
        self.test_validation_category_empty_scope_ref()
        self.test_validation_invalid_scope()

        # Eligibility tests
        print("\n--- Eligibility Tests ---")
        self.test_eligibility_check()

        # Sales return creation tests
        print("\n--- Sales Return Creation Tests ---")
        self.test_sales_return_with_policy_snapshot()

        # Summary
        print("\n" + "=" * 80)
        print(f"R0 BACKEND TEST SUMMARY")
        print("=" * 80)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        print("=" * 80)

        return self.tests_passed == self.tests_run


def main():
    tester = R0Tester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
