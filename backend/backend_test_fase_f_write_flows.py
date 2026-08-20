"""
FASE F — Backend Write Flows Test (Iteration 180)
Tests ONLY write operations (POST/PATCH) for R&D & Design module.
Iteration 179 already verified GET APIs and UI rendering.
"""
import requests
import sys
import json
from datetime import datetime

BASE_URL = "https://kn-supplier-verify.preview.emergentagent.com/api"

class FaseFWriteFlowsTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.results = []
        
    def log(self, test_name, passed, details=""):
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            print(f"✅ {test_name}")
        else:
            print(f"❌ {test_name}")
            if details:
                print(f"   Details: {details}")
        self.results.append({"test": test_name, "passed": passed, "details": details})
    
    def login(self, email, password="demo12345"):
        """Login and get token"""
        try:
            r = requests.post(f"{BASE_URL}/auth/login", 
                            json={"email": email, "password": password})
            if r.status_code == 200:
                data = r.json()
                self.token = data.get("token")
                self.log(f"Login as {email}", True)
                return True
            else:
                self.log(f"Login as {email}", False, f"Status {r.status_code}")
                return False
        except Exception as e:
            self.log(f"Login as {email}", False, str(e))
            return False
    
    def headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_create_spec(self):
        """P1 US1: Create new specification"""
        try:
            payload = {
                "title": f"Test Spec {datetime.now().strftime('%H%M%S')}",
                "sample_type_hint": "labdip",
                "target": {
                    "stage": "grey",
                    "fabric_type": "woven",
                    "gramasi": 135,
                    "lebar": 150
                },
                "category": "kain",
                "base_unit": "meter"
            }
            r = requests.post(f"{BASE_URL}/rnd/specs", json=payload, headers=self.headers())
            if r.status_code == 200:
                data = r.json()
                self.spec_id = data.get("id")
                self.spec_number = data.get("number")
                self.log("Create specification", True, f"Created {self.spec_number}")
                return data
            else:
                self.log("Create specification", False, f"Status {r.status_code}: {r.text}")
                return None
        except Exception as e:
            self.log("Create specification", False, str(e))
            return None
    
    def test_submit_spec(self, spec_id):
        """P1 US1: Submit specification for approval"""
        try:
            r = requests.post(f"{BASE_URL}/rnd/specs/{spec_id}/submit", 
                            headers=self.headers())
            if r.status_code == 200:
                data = r.json()
                self.log("Submit specification", data.get("status") == "review", 
                        f"Status: {data.get('status')}")
                return data
            else:
                self.log("Submit specification", False, f"Status {r.status_code}: {r.text}")
                return None
        except Exception as e:
            self.log("Submit specification", False, str(e))
            return None
    
    def test_approve_spec(self, spec_id):
        """P1 US2: Approve specification → product born"""
        try:
            payload = {
                "sku": f"RND-TEST-{datetime.now().strftime('%H%M%S')}",
                "name": "Test Product from Spec",
                "price": 50000,
                "note": "Test approval"
            }
            r = requests.post(f"{BASE_URL}/rnd/specs/{spec_id}/approve", 
                            json=payload, headers=self.headers())
            if r.status_code == 200:
                data = r.json()
                product = data.get("product", {})
                self.product_id = product.get("id")
                self.product_sku = product.get("sku")
                lifecycle = product.get("lifecycle")
                self.log("Approve specification → product born", 
                        lifecycle == "disetujui",
                        f"Product {self.product_sku} lifecycle: {lifecycle}")
                return data
            else:
                self.log("Approve specification", False, f"Status {r.status_code}: {r.text}")
                return None
        except Exception as e:
            self.log("Approve specification", False, str(e))
            return None
    
    def test_product_not_orderable(self, product_id):
        """P1 US3: Product not yet released CANNOT be sold"""
        try:
            # Check orderable_only endpoint
            r = requests.get(f"{BASE_URL}/products?orderable_only=true", 
                           headers=self.headers())
            if r.status_code == 200:
                data = r.json()
                products = data.get("items", []) if isinstance(data, dict) else data
                product_ids = [p.get("id") for p in products]
                not_in_list = product_id not in product_ids
                self.log("Product not in orderable list", not_in_list,
                        f"Product {product_id} {'NOT' if not_in_list else 'IS'} in orderable list")
                return not_in_list
            else:
                self.log("Check orderable products", False, f"Status {r.status_code}")
                return False
        except Exception as e:
            self.log("Check orderable products", False, str(e))
            return False
    
    def test_release_product(self, spec_id):
        """P1 US8: Release product to production"""
        try:
            payload = {"reason": "Test release to production"}
            r = requests.post(f"{BASE_URL}/rnd/specs/{spec_id}/release-product",
                            json=payload, headers=self.headers())
            if r.status_code == 200:
                data = r.json()
                product = data.get("product", {})
                lifecycle = product.get("lifecycle")
                self.log("Release product to production", 
                        lifecycle == "produksi",
                        f"Lifecycle: {lifecycle}")
                return data
            else:
                self.log("Release product", False, f"Status {r.status_code}: {r.text}")
                return None
        except Exception as e:
            self.log("Release product", False, str(e))
            return None
    
    def test_create_sample_without_design(self):
        """P1 US9: Proofing without design REJECTED"""
        try:
            payload = {
                "title": f"Test Proofing {datetime.now().strftime('%H%M%S')}",
                "sample_type": "proofing",
                # NO design_id - should be rejected
            }
            r = requests.post(f"{BASE_URL}/rnd/samples", json=payload, headers=self.headers())
            # Should be rejected (400)
            rejected = r.status_code == 400
            msg = r.json().get("detail", "") if r.status_code == 400 else ""
            has_design_msg = "desain" in msg.lower()
            self.log("Proofing without design REJECTED", 
                    rejected and has_design_msg,
                    f"Status {r.status_code}, Message: {msg}")
            return rejected
        except Exception as e:
            self.log("Proofing without design", False, str(e))
            return False
    
    def test_create_sample_with_design(self):
        """P1 US9: Proofing with design SUCCESS"""
        try:
            # First get a design
            r = requests.get(f"{BASE_URL}/design-gallery?status=approved&limit=1", 
                           headers=self.headers())
            if r.status_code != 200:
                self.log("Get design for sample", False, "Cannot get design")
                return None
            
            data = r.json()
            designs = data.get("items", []) if isinstance(data, dict) else data
            if not designs:
                self.log("Get design for sample", False, "No approved designs")
                return None
            
            design = designs[0] if isinstance(designs, list) else designs
            
            payload = {
                "title": f"Test Proofing {datetime.now().strftime('%H%M%S')}",
                "sample_type": "proofing",
                "design_id": design.get("id"),
                "design_version": design.get("version", 1)
            }
            r = requests.post(f"{BASE_URL}/rnd/samples", json=payload, headers=self.headers())
            if r.status_code == 200:
                data = r.json()
                self.sample_id = data.get("id")
                self.sample_number = data.get("number")
                self.log("Create proofing with design", True, 
                        f"Created {self.sample_number}")
                return data
            else:
                self.log("Create proofing with design", False, 
                        f"Status {r.status_code}: {r.text}")
                return None
        except Exception as e:
            self.log("Create proofing with design", False, str(e))
            return None
    
    def test_send_sample_to_suppliers(self, sample_id):
        """P1 US5: Send sample to suppliers"""
        try:
            # Get suppliers
            r = requests.get(f"{BASE_URL}/suppliers?limit=2", headers=self.headers())
            if r.status_code != 200:
                self.log("Get suppliers", False, "Cannot get suppliers")
                return None
            
            data = r.json()
            suppliers = data.get("items", []) if isinstance(data, dict) else data
            if len(suppliers) < 1:
                self.log("Get suppliers", False, "No suppliers available")
                return None
            
            supplier_ids = [s.get("id") for s in suppliers[:2]]
            
            payload = {
                "supplier_ids": supplier_ids,
                "note": "Test sample request"
            }
            r = requests.post(f"{BASE_URL}/rnd/samples/{sample_id}/send",
                            json=payload, headers=self.headers())
            if r.status_code == 200:
                data = r.json()
                self.log("Send sample to suppliers", True,
                        f"Sent to {len(supplier_ids)} suppliers")
                return data
            else:
                self.log("Send sample to suppliers", False,
                        f"Status {r.status_code}: {r.text}")
                return None
        except Exception as e:
            self.log("Send sample to suppliers", False, str(e))
            return None
    
    def test_submit_round_without_attachment(self, sample_id):
        """P1 US5: Submit round WITHOUT attachment → REJECTED"""
        try:
            # Get sample to find round
            r = requests.get(f"{BASE_URL}/rnd/samples/{sample_id}", headers=self.headers())
            if r.status_code != 200:
                self.log("Get sample for round", False, "Cannot get sample")
                return False
            
            sample = r.json()
            rounds = sample.get("rounds", [])
            if not rounds:
                self.log("Find round", False, "No rounds found")
                return False
            
            round_id = rounds[0].get("id")
            
            # Try to submit without attachment
            payload = {
                "note": "Test submission without attachment"
            }
            r = requests.post(f"{BASE_URL}/rnd/samples/{sample_id}/rounds/{round_id}/submit",
                            json=payload, headers=self.headers())
            
            # Should be rejected (400)
            rejected = r.status_code == 400
            msg = r.json().get("detail", "") if r.status_code == 400 else ""
            has_attachment_msg = "lampiran" in msg.lower() or "bukti" in msg.lower()
            self.log("Submit round without attachment REJECTED",
                    rejected and has_attachment_msg,
                    f"Status {r.status_code}, Message: {msg}")
            return rejected
        except Exception as e:
            self.log("Submit round without attachment", False, str(e))
            return False
    
    def test_assess_round_acc_without_score(self, sample_id):
        """P1 US6: ACC round WITHOUT score → REJECTED"""
        try:
            # Get sample to find submitted round
            r = requests.get(f"{BASE_URL}/rnd/samples/{sample_id}", headers=self.headers())
            if r.status_code != 200:
                return False
            
            sample = r.json()
            rounds = sample.get("rounds", [])
            submitted_rounds = [r for r in rounds if r.get("status") == "submitted"]
            
            if not submitted_rounds:
                self.log("Find submitted round", False, "No submitted rounds")
                return False
            
            round_id = submitted_rounds[0].get("id")
            
            # Try to ACC without score
            payload = {
                "result": "acc",
                "note": "Test ACC without score"
                # NO score - should be rejected
            }
            r = requests.post(f"{BASE_URL}/rnd/samples/{sample_id}/rounds/{round_id}/assess",
                            json=payload, headers=self.headers())
            
            # Should be rejected (400)
            rejected = r.status_code == 400
            msg = r.json().get("detail", "") if r.status_code == 400 else ""
            has_score_msg = "skor" in msg.lower()
            self.log("ACC round without score REJECTED",
                    rejected and has_score_msg,
                    f"Status {r.status_code}, Message: {msg}")
            return rejected
        except Exception as e:
            self.log("ACC round without score", False, str(e))
            return False
    
    def test_issue_material(self, sample_id):
        """P1 US10+11: Issue material → stock decreases"""
        try:
            # Get available rolls
            r = requests.get(f"{BASE_URL}/inventory/rolls?status=available&limit=1",
                           headers=self.headers())
            if r.status_code != 200:
                self.log("Get available rolls", False, "Cannot get rolls")
                return None
            
            data = r.json()
            rolls = data.get("items", []) if isinstance(data, dict) else data
            if not rolls:
                self.log("Get available rolls", False, "No available rolls")
                return None
            
            roll = rolls[0]
            roll_id = roll.get("id")
            roll_no = roll.get("roll_no")
            initial_length = float(roll.get("length_remaining", 0))
            
            # Issue 3 meters
            payload = {
                "roll_id": roll_id,
                "qty": 3,
                "note": "Test material issue"
            }
            r = requests.post(f"{BASE_URL}/rnd/samples/{sample_id}/issue-material",
                            json=payload, headers=self.headers())
            
            if r.status_code == 200:
                # Verify stock decreased
                r2 = requests.get(f"{BASE_URL}/inventory/rolls?roll_no={roll_no}",
                                headers=self.headers())
                if r2.status_code == 200:
                    data2 = r2.json()
                    updated_rolls = data2.get("items", []) if isinstance(data2, dict) else data2
                    if updated_rolls:
                        new_length = float(updated_rolls[0].get("length_remaining", 0))
                        decreased = abs((initial_length - new_length) - 3.0) < 0.01
                        self.log("Issue material → stock decreases",
                                decreased,
                                f"Roll {roll_no}: {initial_length} → {new_length} (expected -3)")
                        return decreased
                
                self.log("Issue material", True, "Material issued but cannot verify stock")
                return True
            else:
                self.log("Issue material", False, f"Status {r.status_code}: {r.text}")
                return False
        except Exception as e:
            self.log("Issue material", False, str(e))
            return False
    
    def run_all_tests(self):
        print("\n" + "="*70)
        print("FASE F — Backend Write Flows Test (Iteration 180)")
        print("="*70 + "\n")
        
        # Login as admin (full permissions)
        if not self.login("admin@kainnusantara.id"):
            print("\n❌ Cannot proceed without login")
            return 1
        
        print("\n--- P1 US1+2+8: Spec → Submit → Approve → Release ---")
        spec = self.test_create_spec()
        if spec:
            self.test_submit_spec(spec.get("id"))
            
            # Login as manager to approve
            self.login("manager@kainnusantara.id")
            approval = self.test_approve_spec(spec.get("id"))
            if approval:
                product = approval.get("product", {})
                self.test_product_not_orderable(product.get("id"))
                self.test_release_product(spec.get("id"))
        
        print("\n--- P1 US9: Proofing without/with design ---")
        self.login("admin@kainnusantara.id")
        self.test_create_sample_without_design()
        sample = self.test_create_sample_with_design()
        
        print("\n--- P1 US5+6: Sample → Send → Submit round → Assess ---")
        if sample:
            self.test_send_sample_to_suppliers(sample.get("id"))
            self.test_submit_round_without_attachment(sample.get("id"))
            # Note: Cannot test full round submission with attachment in simple HTTP test
            # This requires file upload which is better tested in frontend
        
        print("\n--- P1 US10+11: Issue material → stock decreases ---")
        if sample:
            self.test_issue_material(sample.get("id"))
        
        print("\n" + "="*70)
        print(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        print("="*70 + "\n")
        
        return 0 if self.tests_passed == self.tests_run else 1

if __name__ == "__main__":
    tester = FaseFWriteFlowsTester()
    sys.exit(tester.run_all_tests())
