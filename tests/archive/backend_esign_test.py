#!/usr/bin/env python3
"""
Kain Nusantara E-Sign (Fase 4) Backend Test
Tests E-Sign request, OTP verification, public verification, and RBAC
"""
import requests
import sys
import base64
from datetime import datetime

BASE_URL = "https://static-bundle-2.preview.emergentagent.com/api"

# Test credentials
TEST_USERS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "warehouse": {"email": "warehouse@kainnusantara.id", "password": "demo12345"},
}

# Dummy signature image (1x1 transparent PNG)
DUMMY_SIGNATURE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

class ESignTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tokens = {}
        self.results = []
        self.request_id = None
        self.reveal_code = None
        self.verification_code = None

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

    def test_health(self):
        """Test API health endpoint"""
        try:
            r = requests.get(f"{BASE_URL.replace('/api', '')}/api/", timeout=10)
            if r.status_code == 200:
                self.log("PASS", "API Health Check", f"Status: {r.status_code}")
                return True
            else:
                self.log("FAIL", "API Health Check", f"Status: {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "API Health Check", f"Error: {str(e)}")
            return False

    def test_auth(self, role):
        """Test authentication for a role"""
        try:
            creds = TEST_USERS[role]
            r = requests.post(f"{BASE_URL}/auth/login", json=creds, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "token" in data and "user" in data:
                    self.tokens[role] = data["token"]
                    self.log("PASS", f"Auth - {role}", f"User: {data['user'].get('name', 'N/A')}")
                    return True
            self.log("FAIL", f"Auth - {role}", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", f"Auth - {role}", f"Error: {str(e)}")
            return False

    def get_headers(self, role="admin"):
        """Get auth headers for a role"""
        token = self.tokens.get(role, "")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_esign_request_admin(self):
        """Test POST /api/esign/request (admin) - create signing request"""
        try:
            payload = {
                "doc_type": "sales_order",
                "source_id": "so_003",
                "signer_name": "Ibu Sari",
                "signer_role": "Finance"
            }
            r = requests.post(f"{BASE_URL}/esign/request", json=payload, headers=self.get_headers("admin"), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                # Check required fields
                if "request_id" in data and "channel" in data and "reveal_code" in data:
                    self.request_id = data["request_id"]
                    self.reveal_code = data["reveal_code"]
                    
                    # Verify it's simulated
                    if data.get("channel") == "simulated" and data.get("simulated") == True:
                        self.log("PASS", "E-Sign Request (admin)", 
                                f"request_id: {self.request_id}, reveal_code: {self.reveal_code}, channel: simulated")
                        return True
                    else:
                        self.log("FAIL", "E-Sign Request (admin)", 
                                f"Expected simulated channel, got: {data.get('channel')}")
                        return False
                else:
                    self.log("FAIL", "E-Sign Request (admin)", 
                            f"Missing required fields. Got: {list(data.keys())}")
                    return False
            else:
                self.log("FAIL", "E-Sign Request (admin)", 
                        f"Status: {r.status_code}, Body: {r.text[:300]}")
                return False
        except Exception as e:
            self.log("FAIL", "E-Sign Request (admin)", f"Error: {str(e)}")
            return False

    def test_esign_verify_wrong_otp(self):
        """Test POST /api/esign/verify with WRONG OTP - should return 400"""
        if not self.request_id:
            self.log("FAIL", "E-Sign Verify (wrong OTP)", "No request_id available")
            return False
        
        try:
            payload = {
                "request_id": self.request_id,
                "otp": "999999",  # Wrong OTP
                "signature_b64": DUMMY_SIGNATURE
            }
            r = requests.post(f"{BASE_URL}/esign/verify", json=payload, headers=self.get_headers("admin"), timeout=10)
            
            if r.status_code == 400:
                data = r.json()
                if "detail" in data and "OTP salah" in data["detail"]:
                    self.log("PASS", "E-Sign Verify (wrong OTP)", 
                            f"Correctly rejected with 400: {data['detail']}")
                    return True
                else:
                    self.log("FAIL", "E-Sign Verify (wrong OTP)", 
                            f"Got 400 but wrong message: {data.get('detail')}")
                    return False
            else:
                self.log("FAIL", "E-Sign Verify (wrong OTP)", 
                        f"Expected 400, got {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "E-Sign Verify (wrong OTP)", f"Error: {str(e)}")
            return False

    def test_esign_verify_correct_otp(self):
        """Test POST /api/esign/verify with correct OTP - should succeed"""
        if not self.request_id or not self.reveal_code:
            self.log("FAIL", "E-Sign Verify (correct OTP)", "No request_id or reveal_code available")
            return False
        
        try:
            payload = {
                "request_id": self.request_id,
                "otp": self.reveal_code,
                "signature_b64": DUMMY_SIGNATURE
            }
            r = requests.post(f"{BASE_URL}/esign/verify", json=payload, headers=self.get_headers("admin"), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                # Check required fields
                required = ["status", "verification_code", "doc_hash", "verify_url"]
                if all(k in data for k in required):
                    self.verification_code = data["verification_code"]
                    
                    # Verify status is 'signed'
                    if data["status"] == "signed":
                        # Verify doc_hash is 64 hex chars
                        if len(data["doc_hash"]) == 64 and all(c in "0123456789abcdef" for c in data["doc_hash"].lower()):
                            self.log("PASS", "E-Sign Verify (correct OTP)", 
                                    f"verification_code: {self.verification_code}, doc_hash: {data['doc_hash'][:16]}...")
                            return True
                        else:
                            self.log("FAIL", "E-Sign Verify (correct OTP)", 
                                    f"Invalid doc_hash format: {data['doc_hash']}")
                            return False
                    else:
                        self.log("FAIL", "E-Sign Verify (correct OTP)", 
                                f"Expected status 'signed', got: {data['status']}")
                        return False
                else:
                    self.log("FAIL", "E-Sign Verify (correct OTP)", 
                            f"Missing required fields. Got: {list(data.keys())}")
                    return False
            else:
                self.log("FAIL", "E-Sign Verify (correct OTP)", 
                        f"Status: {r.status_code}, Body: {r.text[:300]}")
                return False
        except Exception as e:
            self.log("FAIL", "E-Sign Verify (correct OTP)", f"Error: {str(e)}")
            return False

    def test_public_verify_valid_code(self):
        """Test GET /api/esign/verify/{code} WITHOUT auth - should return valid document"""
        if not self.verification_code:
            self.log("FAIL", "Public Verify (valid code)", "No verification_code available")
            return False
        
        try:
            # No auth headers for public endpoint
            r = requests.get(f"{BASE_URL}/esign/verify/{self.verification_code}", timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                # Check required fields
                required = ["valid", "doc_type", "number", "entity_name", "signers", "doc_hash"]
                if all(k in data for k in required):
                    if data["valid"] == True:
                        self.log("PASS", "Public Verify (valid code)", 
                                f"doc_type: {data['doc_type']}, number: {data.get('number')}, signers: {len(data['signers'])}")
                        return True
                    else:
                        self.log("FAIL", "Public Verify (valid code)", 
                                f"Expected valid=True, got: {data['valid']}")
                        return False
                else:
                    self.log("FAIL", "Public Verify (valid code)", 
                            f"Missing required fields. Got: {list(data.keys())}")
                    return False
            else:
                self.log("FAIL", "Public Verify (valid code)", 
                        f"Status: {r.status_code}, Body: {r.text[:300]}")
                return False
        except Exception as e:
            self.log("FAIL", "Public Verify (valid code)", f"Error: {str(e)}")
            return False

    def test_public_verify_invalid_code(self):
        """Test GET /api/esign/verify/BOGUSXXX - should return valid=false"""
        try:
            # No auth headers for public endpoint
            r = requests.get(f"{BASE_URL}/esign/verify/BOGUSXXX", timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                if data.get("valid") == False:
                    self.log("PASS", "Public Verify (invalid code)", 
                            f"Correctly returned valid=false")
                    return True
                else:
                    self.log("FAIL", "Public Verify (invalid code)", 
                            f"Expected valid=false, got: {data}")
                    return False
            else:
                self.log("FAIL", "Public Verify (invalid code)", 
                        f"Status: {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "Public Verify (invalid code)", f"Error: {str(e)}")
            return False

    def test_pdf_render_after_signing(self):
        """Test GET /api/pdf/render/sales_order/so_003?format=html - should contain verification_code"""
        try:
            r = requests.get(f"{BASE_URL}/pdf/render/sales_order/so_003", 
                           params={"format": "html"}, 
                           headers=self.get_headers("admin"), 
                           timeout=10)
            
            if r.status_code == 200:
                html = r.text
                # Check for verification code, verify-document, and Ditandatangani
                checks = [
                    ("verification_code" in html or (self.verification_code and self.verification_code in html), "verification_code"),
                    ("verify-document" in html, "verify-document"),
                    ("Ditandatangani" in html, "Ditandatangani")
                ]
                
                passed = all(check[0] for check in checks)
                failed = [check[1] for check in checks if not check[0]]
                
                if passed:
                    self.log("PASS", "PDF Render After Signing", 
                            "Contains verification_code, verify-document, and Ditandatangani")
                    return True
                else:
                    self.log("FAIL", "PDF Render After Signing", 
                            f"Missing: {', '.join(failed)}")
                    return False
            else:
                self.log("FAIL", "PDF Render After Signing", 
                        f"Status: {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "PDF Render After Signing", f"Error: {str(e)}")
            return False

    def test_pdf_documents_list(self):
        """Test GET /api/pdf/documents/sales_order - should show so_003 as signed"""
        try:
            r = requests.get(f"{BASE_URL}/pdf/documents/sales_order", 
                           headers=self.get_headers("admin"), 
                           timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                documents = data.get("documents", [])
                
                # Find so_003
                so_003 = next((d for d in documents if d.get("source_id") == "so_003"), None)
                
                if so_003:
                    if so_003.get("signed") == True and so_003.get("verification_code"):
                        self.log("PASS", "PDF Documents List", 
                                f"so_003 signed=True, verification_code={so_003.get('verification_code')}")
                        return True
                    else:
                        self.log("FAIL", "PDF Documents List", 
                                f"so_003 found but signed={so_003.get('signed')}, verification_code={so_003.get('verification_code')}")
                        return False
                else:
                    self.log("FAIL", "PDF Documents List", 
                            f"so_003 not found in documents list")
                    return False
            else:
                self.log("FAIL", "PDF Documents List", 
                        f"Status: {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "PDF Documents List", f"Error: {str(e)}")
            return False

    def test_rbac_warehouse_allowed(self):
        """Test RBAC: warehouse user CAN sign (has esign:sign permission)"""
        try:
            payload = {
                "doc_type": "sales_order",
                "source_id": "so_004",
                "signer_name": "Test User",
                "signer_role": "Test"
            }
            r = requests.post(f"{BASE_URL}/esign/request", json=payload, 
                            headers=self.get_headers("warehouse"), timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                if "request_id" in data:
                    self.log("PASS", "RBAC - Warehouse Allowed", 
                            f"Warehouse user correctly allowed (has esign:sign permission)")
                    return True
                else:
                    self.log("FAIL", "RBAC - Warehouse Allowed", 
                            f"Got 200 but missing request_id")
                    return False
            else:
                self.log("FAIL", "RBAC - Warehouse Allowed", 
                        f"Expected 200, got {r.status_code}")
                return False
        except Exception as e:
            self.log("FAIL", "RBAC - Warehouse Allowed", f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all E-Sign backend tests"""
        print("=" * 70)
        print("KAIN NUSANTARA E-SIGN (FASE 4) BACKEND TEST")
        print("=" * 70)
        print()

        # Health check
        if not self.test_health():
            print("\n❌ API health check failed. Stopping tests.")
            return False

        # Auth tests
        print("\n--- Authentication Tests ---")
        for role in ["admin", "warehouse"]:
            self.test_auth(role)

        if not self.tokens.get("admin"):
            print("\n❌ Admin auth failed. Cannot proceed with API tests.")
            return False

        # E-Sign flow tests
        print("\n--- E-Sign Flow Tests ---")
        self.test_esign_request_admin()
        self.test_esign_verify_wrong_otp()
        self.test_esign_verify_correct_otp()
        
        print("\n--- Public Verification Tests ---")
        self.test_public_verify_valid_code()
        self.test_public_verify_invalid_code()
        
        print("\n--- PDF Integration Tests ---")
        self.test_pdf_render_after_signing()
        self.test_pdf_documents_list()
        
        print("\n--- RBAC Tests ---")
        self.test_rbac_warehouse_allowed()

        # Summary
        print("\n" + "=" * 70)
        print(f"E-SIGN BACKEND TEST SUMMARY")
        print("=" * 70)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        print("=" * 70)

        return self.tests_passed == self.tests_run


def main():
    tester = ESignTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
