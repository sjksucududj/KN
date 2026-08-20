"""
Backend API Testing for FASE P2 — Nota Retur/Kredit Antar-PT
Tests all endpoints related to interco_return doc_type and regressions.
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://kn-dev-review.preview.emergentagent.com/api"
TEST_EMAIL = "admin@kainnusantara.id"
TEST_PASSWORD = "demo12345"

class APITester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        self.returner_id = None
        self.receiver_id = None
        self.returner_entity_id = None
        self.receiver_entity_id = None

    def log(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {msg}")

    def test(self, name, condition, details=""):
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log(f"✅ PASS: {name} {details}", "PASS")
            return True
        else:
            self.tests_failed += 1
            self.failures.append(f"{name} {details}")
            self.log(f"❌ FAIL: {name} {details}", "FAIL")
            return False

    def login(self):
        """Test login and get auth token"""
        self.log("Testing login...")
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token")
                self.test("Login", self.token is not None, f"(got token)")
                return True
            else:
                self.test("Login", False, f"(status {response.status_code})")
                return False
        except Exception as e:
            self.test("Login", False, f"(error: {e})")
            return False

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def test_doc_types_registry(self):
        """Test GET /api/pdf/doc-types includes interco_return"""
        self.log("Testing doc-types registry...")
        try:
            response = requests.get(
                f"{BASE_URL}/pdf/doc-types",
                headers=self.get_headers(),
                timeout=10
            )
            self.test("GET /api/pdf/doc-types status", response.status_code == 200,
                     f"(got {response.status_code})")
            
            if response.status_code == 200:
                doc_types = response.json()
                interco_return = next((d for d in doc_types if d.get("doc_type") == "interco_return"), None)
                
                self.test("interco_return in DOC_REGISTRY", interco_return is not None)
                
                if interco_return:
                    self.test("interco_return label", 
                             interco_return.get("label") == "Nota Retur / Kredit Antar-PT",
                             f"(got '{interco_return.get('label')}')")
                    self.test("interco_return esignable", 
                             interco_return.get("esignable") is True,
                             f"(got {interco_return.get('esignable')})")
                    self.test("interco_return collection", 
                             interco_return.get("collection") == "interco_returns",
                             f"(got '{interco_return.get('collection')}')")
                    self.test("interco_return module", 
                             interco_return.get("module") == "interco",
                             f"(got '{interco_return.get('module')}')")
        except Exception as e:
            self.test("GET /api/pdf/doc-types", False, f"(error: {e})")

    def get_interco_return_ids(self):
        """Get interco_return source_ids from the transaction journal"""
        self.log("Getting interco_return source IDs...")
        try:
            response = requests.get(
                f"{BASE_URL}/interco/transactions/ict_f69f720fbba0/journal",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                returns = data.get("returns", [])
                
                for ret in returns:
                    if ret.get("role") == "returner" and ret.get("number") == "KANDA/ICR-00001":
                        self.returner_id = ret.get("id")
                        self.returner_entity_id = ret.get("entity_id")
                    elif ret.get("role") == "receiver" and ret.get("number") == "KSC/ICR-00001":
                        self.receiver_id = ret.get("id")
                        self.receiver_entity_id = ret.get("entity_id")
                
                self.test("Found returner doc", self.returner_id is not None,
                         f"(id: {self.returner_id})")
                self.test("Found receiver doc", self.receiver_id is not None,
                         f"(id: {self.receiver_id})")
                
                return self.returner_id and self.receiver_id
            else:
                self.test("Get interco_return IDs", False, f"(status {response.status_code})")
                return False
        except Exception as e:
            self.test("Get interco_return IDs", False, f"(error: {e})")
            return False

    def test_render_html(self, role, source_id, entity_id, expected_title):
        """Test HTML rendering for interco_return"""
        self.log(f"Testing HTML render for {role}...")
        try:
            response = requests.get(
                f"{BASE_URL}/pdf/render/interco_return/{source_id}",
                params={"format": "html", "entity_id": entity_id},
                headers=self.get_headers(),
                timeout=15
            )
            
            self.test(f"GET /api/pdf/render/interco_return/{source_id} HTML status",
                     response.status_code == 200,
                     f"(got {response.status_code})")
            
            if response.status_code == 200:
                html = response.text
                self.test(f"HTML contains title '{expected_title}'",
                         expected_title in html,
                         f"({len(html)} chars)")
                self.test(f"HTML contains ANTAR-PT disclaimer",
                         "ANTAR-PT" in html or "antar-PT" in html)
                
                # Check for document number
                if role == "returner":
                    self.test(f"HTML contains returner number",
                             "KANDA/ICR-00001" in html)
                else:
                    self.test(f"HTML contains receiver number",
                             "KSC/ICR-00001" in html)
        except Exception as e:
            self.test(f"Render HTML {role}", False, f"(error: {e})")

    def test_render_pdf(self, source_id, entity_id):
        """Test PDF rendering for interco_return"""
        self.log(f"Testing PDF render for {source_id}...")
        try:
            response = requests.get(
                f"{BASE_URL}/pdf/render/interco_return/{source_id}",
                params={"format": "pdf", "entity_id": entity_id, "download": "false"},
                headers=self.get_headers(),
                timeout=20
            )
            
            self.test(f"GET /api/pdf/render/interco_return/{source_id} PDF status",
                     response.status_code == 200,
                     f"(got {response.status_code})")
            
            if response.status_code == 200:
                self.test("PDF content-type",
                         response.headers.get("content-type") == "application/pdf",
                         f"(got '{response.headers.get('content-type')}')")
                
                content = response.content
                self.test("PDF starts with %PDF",
                         content[:4] == b"%PDF",
                         f"({len(content)} bytes)")
        except Exception as e:
            self.test(f"Render PDF", False, f"(error: {e})")

    def test_esign_request(self, source_id, entity_id):
        """Test e-sign request creation for interco_return"""
        self.log(f"Testing e-sign request for {source_id}...")
        try:
            response = requests.post(
                f"{BASE_URL}/esign/request",
                json={
                    "doc_type": "interco_return",
                    "source_id": source_id,
                    "entity_id": entity_id,
                    "signer_name": "Test Admin",
                    "signer_phone": "081234567890"
                },
                headers=self.get_headers(),
                timeout=10
            )
            
            self.test(f"POST /api/esign/request for interco_return",
                     response.status_code == 200,
                     f"(got {response.status_code})")
            
            if response.status_code == 200:
                data = response.json()
                self.test("E-sign request created",
                         data.get("request_id") is not None,
                         f"(request_id: {data.get('request_id')})")
        except Exception as e:
            self.test(f"E-sign request", False, f"(error: {e})")

    def test_esign_signatures(self, source_id):
        """Test GET /api/esign/signatures/interco_return/{id}"""
        self.log(f"Testing e-sign signatures endpoint for {source_id}...")
        try:
            response = requests.get(
                f"{BASE_URL}/esign/signatures/interco_return/{source_id}",
                headers=self.get_headers(),
                timeout=10
            )
            
            self.test(f"GET /api/esign/signatures/interco_return/{source_id}",
                     response.status_code == 200,
                     f"(got {response.status_code})")
            
            if response.status_code == 200:
                data = response.json()
                self.test("Signatures list returned",
                         isinstance(data.get("signatures"), list),
                         f"({len(data.get('signatures', []))} signatures)")
        except Exception as e:
            self.test(f"E-sign signatures", False, f"(error: {e})")

    def test_regression_tax_invoice(self):
        """Test regression: tax_invoice rendering still works"""
        self.log("Testing regression: tax_invoice rendering...")
        try:
            # Get a sample tax invoice
            response = requests.get(
                f"{BASE_URL}/pdf/sample/tax_invoice",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                sample = response.json()
                source_id = sample.get("source_id")
                entity_id = sample.get("entity_id")
                
                if source_id:
                    # Test rendering
                    render_response = requests.get(
                        f"{BASE_URL}/pdf/render/tax_invoice/{source_id}",
                        params={"format": "html", "entity_id": entity_id},
                        headers=self.get_headers(),
                        timeout=15
                    )
                    
                    self.test("Regression: tax_invoice render",
                             render_response.status_code == 200,
                             f"(got {render_response.status_code})")
                else:
                    self.log("No tax_invoice sample found, skipping regression test", "WARN")
        except Exception as e:
            self.test("Regression: tax_invoice", False, f"(error: {e})")

    def test_regression_interco_endpoints(self):
        """Test regression: interco transactions and journal endpoints"""
        self.log("Testing regression: interco endpoints...")
        try:
            # Test GET /api/interco/transactions
            response = requests.get(
                f"{BASE_URL}/interco/transactions",
                headers=self.get_headers(),
                timeout=10
            )
            
            self.test("Regression: GET /api/interco/transactions",
                     response.status_code == 200,
                     f"(got {response.status_code})")
            
            # Test GET /api/interco/transactions/{id}/journal
            journal_response = requests.get(
                f"{BASE_URL}/interco/transactions/ict_f69f720fbba0/journal",
                headers=self.get_headers(),
                timeout=10
            )
            
            self.test("Regression: GET /api/interco/transactions/{id}/journal",
                     journal_response.status_code == 200,
                     f"(got {journal_response.status_code})")
            
            if journal_response.status_code == 200:
                data = journal_response.json()
                returns = data.get("returns", [])
                
                self.test("Journal includes returns list",
                         isinstance(returns, list),
                         f"({len(returns)} returns)")
                
                if returns:
                    first_return = returns[0]
                    self.test("Return has entity_id field",
                             "entity_id" in first_return)
                    self.test("Return has id field",
                             "id" in first_return)
                    self.test("Return has number field",
                             "number" in first_return)
        except Exception as e:
            self.test("Regression: interco endpoints", False, f"(error: {e})")

    def run_all_tests(self):
        """Run all backend tests"""
        self.log("=" * 60)
        self.log("Starting Backend API Tests for FASE P2 - Interco Return")
        self.log("=" * 60)
        
        # Login first
        if not self.login():
            self.log("Login failed, cannot continue tests", "ERROR")
            return False
        
        # Test doc-types registry
        self.test_doc_types_registry()
        
        # Get interco_return IDs
        if not self.get_interco_return_ids():
            self.log("Could not get interco_return IDs, skipping render tests", "WARN")
        else:
            # Test HTML rendering for both roles
            self.test_render_html("returner", self.returner_id, self.returner_entity_id,
                                 "Nota Retur Antar-PT")
            self.test_render_html("receiver", self.receiver_id, self.receiver_entity_id,
                                 "Nota Kredit Antar-PT")
            
            # Test PDF rendering
            self.test_render_pdf(self.returner_id, self.returner_entity_id)
            
            # Test e-sign endpoints
            self.test_esign_request(self.returner_id, self.returner_entity_id)
            self.test_esign_signatures(self.returner_id)
        
        # Test regressions
        self.test_regression_tax_invoice()
        self.test_regression_interco_endpoints()
        
        # Print summary
        self.log("=" * 60)
        self.log(f"Tests Run: {self.tests_run}")
        self.log(f"Tests Passed: {self.tests_passed}")
        self.log(f"Tests Failed: {self.tests_failed}")
        self.log("=" * 60)
        
        if self.tests_failed > 0:
            self.log("Failed tests:", "ERROR")
            for failure in self.failures:
                self.log(f"  - {failure}", "ERROR")
        
        return self.tests_failed == 0


def main():
    tester = APITester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
