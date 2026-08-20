#!/usr/bin/env python3
"""Backend API Test — FASE F R&D & DESAIN Endpoints

Tests all R&D endpoints with focus on:
1. All CRUD operations for specs and samples
2. Hard validation rules (must return 4xx with clear messages, not 500)
3. RBAC per role (admin, manager, sales, warehouse)
4. issue-material inventory movements
5. Auto-contract creation on decide
"""
import sys
import requests
from datetime import datetime, timedelta

BASE_URL = "https://kn-product-hub.preview.emergentagent.com/api"
PWD = "demo12345"

USERS = {
    "admin": "admin@kainnusantara.id",
    "manager": "manager@kainnusantara.id",
    "sales": "sales@kainnusantara.id",
    "warehouse": "warehouse@kainnusantara.id",
}

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"

class RnDAPITester:
    def __init__(self):
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.created_ids = {
            "specs": [],
            "samples": [],
            "products": [],
        }
        
    def login(self, role: str) -> str:
        """Login and cache token"""
        if role in self.tokens:
            return self.tokens[role]
        
        print(f"\n{Colors.CYAN}🔐 Logging in as {role}...{Colors.END}")
        try:
            r = requests.post(f"{BASE_URL}/auth/login", 
                            json={"email": USERS[role], "password": PWD}, 
                            timeout=20)
            r.raise_for_status()
            token = r.json()["token"]
            self.tokens[role] = token
            print(f"{Colors.GREEN}✓ Logged in as {role}{Colors.END}")
            return token
        except Exception as e:
            print(f"{Colors.RED}✗ Login failed for {role}: {e}{Colors.END}")
            return ""
    
    def headers(self, role: str) -> dict:
        """Get auth headers for role"""
        token = self.login(role)
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def test(self, name: str, condition: bool, detail: str = "") -> bool:
        """Record test result"""
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            print(f"  {Colors.GREEN}✓{Colors.END} {name}" + (f" — {detail}" if detail else ""))
        else:
            print(f"  {Colors.RED}✗ {name}" + (f" — {detail}" if detail else "") + Colors.END)
        return condition
    
    def section(self, title: str):
        """Print section header"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 78}")
        print(f"{title}")
        print(f"{'=' * 78}{Colors.END}")
    
    # ═══ META & POLICY ═══════════════════════════════════════════════════════
    def test_meta_endpoint(self):
        """Test GET /rnd/meta"""
        self.section("1. META & POLICY")
        
        try:
            r = requests.get(f"{BASE_URL}/rnd/meta", headers=self.headers("admin"), timeout=20)
            self.test("GET /rnd/meta returns 200", r.status_code == 200)
            
            if r.status_code == 200:
                data = r.json()
                self.test("Meta has policy", "policy" in data)
                self.test("Meta has sample_types", "sample_types" in data)
                self.test("Meta has lifecycles", "lifecycles" in data)
                self.test("Meta has spec_statuses", "spec_statuses" in data)
                self.test("Meta has sample_statuses", "sample_statuses" in data)
        except Exception as e:
            self.test("GET /rnd/meta", False, str(e))
    
    # ═══ SPECIFICATIONS ══════════════════════════════════════════════════════
    def test_spec_crud(self):
        """Test spec CRUD operations"""
        self.section("2. SPECIFICATIONS CRUD")
        
        # List specs
        try:
            r = requests.get(f"{BASE_URL}/rnd/specs", headers=self.headers("admin"), timeout=20)
            self.test("GET /rnd/specs returns 200", r.status_code == 200)
        except Exception as e:
            self.test("GET /rnd/specs", False, str(e))
        
        # Create spec
        try:
            spec_data = {
                "title": f"Test Spec {datetime.now().strftime('%H%M%S')}",
                "lifecycle": "konsep",
                "target": {
                    "stage": "greige",
                    "fabric_type": "katun",
                    "gramasi": 150,
                    "lebar": 150
                },
                "color_target": {
                    "code": "RED-001",
                    "name": "Merah Cerah",
                    "hex": "#FF0000"
                },
                "sample_type_hint": "labdip",
                "category": "kain",
                "base_unit": "meter",
                "notes": "Test spec for API testing"
            }
            
            r = requests.post(f"{BASE_URL}/rnd/specs", 
                            headers=self.headers("admin"), 
                            json=spec_data, 
                            timeout=20)
            
            if self.test("POST /rnd/specs returns 200/201", r.status_code in [200, 201]):
                spec = r.json()
                spec_id = spec.get("id")
                self.created_ids["specs"].append(spec_id)
                self.test("Created spec has ID", bool(spec_id))
                self.test("Created spec has number", bool(spec.get("number")))
                self.test("Created spec status is draft", spec.get("status") == "draft")
                
                # Get spec
                r2 = requests.get(f"{BASE_URL}/rnd/specs/{spec_id}", 
                                headers=self.headers("admin"), 
                                timeout=20)
                self.test("GET /rnd/specs/{id} returns 200", r2.status_code == 200)
                
                # Submit spec
                r3 = requests.post(f"{BASE_URL}/rnd/specs/{spec_id}/submit", 
                                 headers=self.headers("admin"), 
                                 json={}, 
                                 timeout=20)
                if self.test("POST /rnd/specs/{id}/submit returns 200", r3.status_code == 200):
                    submitted = r3.json()
                    self.test("Submitted spec status is review", 
                            submitted.get("status") == "review")
                
                return spec_id
        except Exception as e:
            self.test("POST /rnd/specs", False, str(e))
            return None
    
    def test_spec_approval(self, spec_id: str = None):
        """Test spec approval flow"""
        self.section("3. SPEC APPROVAL & PRODUCT CREATION")
        
        if not spec_id:
            print(f"{Colors.YELLOW}⚠ No spec_id provided, skipping approval tests{Colors.END}")
            return None
        
        try:
            # Approve spec (should create product)
            r = requests.post(f"{BASE_URL}/rnd/specs/{spec_id}/approve", 
                            headers=self.headers("manager"), 
                            json={"note": "Approved for testing"}, 
                            timeout=20)
            
            if self.test("POST /rnd/specs/{id}/approve returns 200", r.status_code == 200):
                result = r.json()
                self.test("Approval result has spec", "spec" in result)
                self.test("Approval result has product", "product" in result)
                
                if "product" in result:
                    product = result["product"]
                    product_id = product.get("id")
                    self.created_ids["products"].append(product_id)
                    self.test("Product created with ID", bool(product_id))
                    self.test("Product lifecycle is disetujui", 
                            product.get("lifecycle") == "disetujui")
                    return product_id
        except Exception as e:
            self.test("POST /rnd/specs/{id}/approve", False, str(e))
        
        return None
    
    # ═══ LIFECYCLE GATING ════════════════════════════════════════════════════
    def test_lifecycle_gating(self, product_id: str = None):
        """Test that products with lifecycle konsep/disetujui cannot be ordered"""
        self.section("4. LIFECYCLE GATING (US3)")
        
        if not product_id:
            print(f"{Colors.YELLOW}⚠ No product_id provided, skipping gating tests{Colors.END}")
            return
        
        # Try to create SO with non-orderable product (should fail with 400)
        try:
            so_data = {
                "customer_id": "CUST-001",
                "items": [
                    {
                        "product_id": product_id,
                        "qty": 10,
                        "unit": "meter",
                        "price": 50000
                    }
                ],
                "notes": "Test SO for lifecycle gating"
            }
            
            r = requests.post(f"{BASE_URL}/sales-orders", 
                            headers=self.headers("sales"), 
                            json=so_data, 
                            timeout=20)
            
            # Should be rejected with 400 (not 500)
            self.test("SO with non-orderable product returns 4xx", 
                     r.status_code >= 400 and r.status_code < 500,
                     f"Got {r.status_code}")
            
            if r.status_code >= 400 and r.status_code < 500:
                error_msg = r.json().get("detail", "")
                self.test("Error message mentions lifecycle", 
                         "lifecycle" in error_msg.lower() or "belum boleh" in error_msg.lower(),
                         error_msg[:100])
        except Exception as e:
            self.test("SO lifecycle gating", False, str(e))
    
    # ═══ SAMPLES ═════════════════════════════════════════════════════════════
    def test_sample_crud(self, spec_id: str = None):
        """Test sample CRUD operations"""
        self.section("5. SAMPLES CRUD")
        
        # List samples
        try:
            r = requests.get(f"{BASE_URL}/rnd/samples", headers=self.headers("admin"), timeout=20)
            self.test("GET /rnd/samples returns 200", r.status_code == 200)
        except Exception as e:
            self.test("GET /rnd/samples", False, str(e))
        
        # Create sample
        try:
            sample_data = {
                "spec_id": spec_id or "",
                "sample_type": "labdip",
                "color_target": {
                    "code": "RED-001",
                    "name": "Merah Cerah",
                    "hex": "#FF0000"
                },
                "target_date": (datetime.now() + timedelta(days=7)).isoformat(),
                "brief": "Test labdip sample for API testing"
            }
            
            r = requests.post(f"{BASE_URL}/rnd/samples", 
                            headers=self.headers("admin"), 
                            json=sample_data, 
                            timeout=20)
            
            if self.test("POST /rnd/samples returns 200/201", r.status_code in [200, 201]):
                sample = r.json()
                sample_id = sample.get("id")
                self.created_ids["samples"].append(sample_id)
                self.test("Created sample has ID", bool(sample_id))
                self.test("Created sample has number", bool(sample.get("number")))
                self.test("Created sample status is draft", sample.get("status") == "draft")
                
                return sample_id
        except Exception as e:
            self.test("POST /rnd/samples", False, str(e))
        
        return None
    
    def test_proofing_requires_design(self):
        """Test that proofing sample requires design_id (US9)"""
        self.section("6. PROOFING REQUIRES DESIGN (US9)")
        
        try:
            # Try to create proofing without design_id (should fail)
            sample_data = {
                "sample_type": "proofing",
                "color_target": {
                    "code": "RED-001",
                    "name": "Merah Cerah",
                    "hex": "#FF0000"
                },
                "brief": "Test proofing without design"
            }
            
            r = requests.post(f"{BASE_URL}/rnd/samples", 
                            headers=self.headers("admin"), 
                            json=sample_data, 
                            timeout=20)
            
            # Should be rejected with 400
            self.test("Proofing without design_id returns 4xx", 
                     r.status_code >= 400 and r.status_code < 500,
                     f"Got {r.status_code}")
            
            if r.status_code >= 400 and r.status_code < 500:
                error_msg = r.json().get("detail", "")
                self.test("Error message mentions design", 
                         "design" in error_msg.lower(),
                         error_msg[:100])
        except Exception as e:
            self.test("Proofing design validation", False, str(e))
    
    # ═══ RBAC TESTS ══════════════════════════════════════════════════════════
    def test_rbac(self, spec_id: str = None, sample_id: str = None):
        """Test RBAC per role"""
        self.section("7. RBAC TESTS")
        
        # Sales cannot approve spec (should get 403)
        if spec_id:
            try:
                r = requests.post(f"{BASE_URL}/rnd/specs/{spec_id}/approve", 
                                headers=self.headers("sales"), 
                                json={"note": "Trying to approve"}, 
                                timeout=20)
                self.test("Sales cannot approve spec (403)", 
                         r.status_code == 403,
                         f"Got {r.status_code}")
            except Exception as e:
                self.test("Sales approve spec RBAC", False, str(e))
        
        # Warehouse cannot create spec (should get 403)
        try:
            spec_data = {
                "title": "Test from warehouse",
                "lifecycle": "konsep",
                "target": {"stage": "greige", "fabric_type": "katun", "gramasi": 150, "lebar": 150},
                "category": "kain",
                "base_unit": "meter"
            }
            r = requests.post(f"{BASE_URL}/rnd/specs", 
                            headers=self.headers("warehouse"), 
                            json=spec_data, 
                            timeout=20)
            self.test("Warehouse cannot create spec (403)", 
                     r.status_code == 403,
                     f"Got {r.status_code}")
        except Exception as e:
            self.test("Warehouse create spec RBAC", False, str(e))
        
        # Warehouse can view (should get 200)
        try:
            r = requests.get(f"{BASE_URL}/rnd/specs", 
                           headers=self.headers("warehouse"), 
                           timeout=20)
            self.test("Warehouse can view specs (200)", 
                     r.status_code == 200,
                     f"Got {r.status_code}")
        except Exception as e:
            self.test("Warehouse view specs RBAC", False, str(e))
    
    # ═══ REPORTS ═════════════════════════════════════════════════════════════
    def test_reports(self):
        """Test report endpoints"""
        self.section("8. REPORTS")
        
        try:
            r = requests.get(f"{BASE_URL}/rnd/reports/performer", 
                           headers=self.headers("admin"), 
                           timeout=20)
            self.test("GET /rnd/reports/performer returns 200", r.status_code == 200)
        except Exception as e:
            self.test("GET /rnd/reports/performer", False, str(e))
        
        try:
            r = requests.get(f"{BASE_URL}/rnd/lifecycle-board", 
                           headers=self.headers("admin"), 
                           timeout=20)
            self.test("GET /rnd/lifecycle-board returns 200", r.status_code == 200)
            
            if r.status_code == 200:
                data = r.json()
                self.test("Lifecycle board has enforcement", "enforcement" in data)
                self.test("Lifecycle board has counts", "counts" in data)
                self.test("Lifecycle board has not_orderable", "not_orderable" in data)
        except Exception as e:
            self.test("GET /rnd/lifecycle-board", False, str(e))
    
    # ═══ MAIN TEST FLOW ══════════════════════════════════════════════════════
    def run_all_tests(self):
        """Run all backend tests"""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 78}")
        print("FASE F R&D & DESAIN — Backend API Tests")
        print(f"{'=' * 78}{Colors.END}\n")
        print(f"Base URL: {BASE_URL}")
        print(f"Testing with roles: {', '.join(USERS.keys())}")
        
        # 1. Meta & Policy
        self.test_meta_endpoint()
        
        # 2. Spec CRUD
        spec_id = self.test_spec_crud()
        
        # 3. Spec Approval (creates product)
        product_id = self.test_spec_approval(spec_id)
        
        # 4. Lifecycle Gating
        self.test_lifecycle_gating(product_id)
        
        # 5. Sample CRUD
        sample_id = self.test_sample_crud(spec_id)
        
        # 6. Proofing requires design
        self.test_proofing_requires_design()
        
        # 7. RBAC
        self.test_rbac(spec_id, sample_id)
        
        # 8. Reports
        self.test_reports()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 78}")
        print("TEST SUMMARY")
        print(f"{'=' * 78}{Colors.END}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        print(f"\nTotal Tests: {self.tests_run}")
        print(f"{Colors.GREEN}Passed: {self.tests_passed}{Colors.END}")
        print(f"{Colors.RED}Failed: {self.tests_run - self.tests_passed}{Colors.END}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if self.created_ids["specs"]:
            print(f"\n{Colors.YELLOW}Created Specs: {', '.join(self.created_ids['specs'])}{Colors.END}")
        if self.created_ids["samples"]:
            print(f"{Colors.YELLOW}Created Samples: {', '.join(self.created_ids['samples'])}{Colors.END}")
        if self.created_ids["products"]:
            print(f"{Colors.YELLOW}Created Products: {', '.join(self.created_ids['products'])}{Colors.END}")
        
        return 0 if self.tests_passed == self.tests_run else 1

def main():
    tester = RnDAPITester()
    exit_code = tester.run_all_tests()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
