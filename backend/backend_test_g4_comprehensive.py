#!/usr/bin/env python3
"""
FASE G-4 Comprehensive Backend API Testing
Testing all document relations, reference numbers & digital signatures APIs
from consumer perspective (not unit tests).
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://jasad-dokumen.preview.emergentagent.com/api"
PWD = "demo12345"

USERS = {
    "admin": "admin@kainnusantara.id",
    "manager": "manager@kainnusantara.id",
    "sales": "sales@kainnusantara.id",
    "warehouse": "warehouse@kainnusantara.id",
}

class G4APITester:
    def __init__(self):
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def login(self, role):
        """Login and get token"""
        try:
            r = requests.post(f"{BASE_URL}/auth/login", 
                json={"email": USERS[role], "password": PWD}, timeout=20)
            if r.status_code == 200:
                self.tokens[role] = r.json()["token"]
                return True
            print(f"❌ Login failed for {role}: {r.status_code}")
            return False
        except Exception as e:
            print(f"❌ Login error for {role}: {e}")
            return False

    def H(self, role):
        """Get headers with token"""
        return {"Authorization": f"Bearer {self.tokens[role]}", "Content-Type": "application/json"}

    def test(self, name, condition, detail=""):
        """Record test result"""
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            print(f"  ✓ {name}" + (f" — {detail}" if detail else ""))
            return True
        else:
            self.tests_failed += 1
            self.failures.append(name)
            print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))
            return False

    def run_all_tests(self):
        """Run all G-4 API tests"""
        print("\n" + "="*80)
        print("FASE G-4 COMPREHENSIVE BACKEND API TESTING")
        print("="*80)

        # Login all users
        print("\n[LOGIN] Authenticating all users...")
        for role in USERS.keys():
            if not self.login(role):
                print(f"❌ Cannot proceed without {role} login")
                return False

        # TEST GROUP 1: Document Reference Types
        print("\n[TEST 1] GET /api/documents/ref-types — Document types map + Indonesian rel_labels")
        try:
            r = requests.get(f"{BASE_URL}/documents/ref-types", headers=self.H("admin"), timeout=30)
            data = r.json() if r.status_code == 200 else {}
            types = data.get("types", [])
            rel_labels = data.get("rel_labels", {})
            
            self.test("ref-types returns 200", r.status_code == 200)
            self.test("ref-types has 20+ document types", len(types) >= 20, f"{len(types)} types")
            self.test("ref-types has Indonesian rel_labels", len(rel_labels) >= 12, f"{len(rel_labels)} labels")
            self.test("vendor_bill marked needs_parent", 
                any(t["doc_type"] == "vendor_bill" and t["needs_parent"] for t in types))
            
            # RBAC: admin/manager/sales/warehouse can view
            for role in ["manager", "sales", "warehouse"]:
                r2 = requests.get(f"{BASE_URL}/documents/ref-types", headers=self.H(role), timeout=30)
                self.test(f"ref-types accessible by {role}", r2.status_code == 200)
        except Exception as e:
            self.test("ref-types API", False, str(e))

        # TEST GROUP 2: Document Trace (from any anchor)
        print("\n[TEST 2] GET /api/documents/trace/{doc_type}/{doc_id} — Trace from any anchor")
        try:
            # Get a sales order with refs
            sos = requests.get(f"{BASE_URL}/sales-orders", headers=self.H("admin"), 
                params={"limit": 50}, timeout=40).json()
            so_list = sos if isinstance(sos, list) else sos.get("items", [])
            so = so_list[0] if so_list else None
            
            if so:
                # Trace from sales_order
                r = requests.get(f"{BASE_URL}/documents/trace/sales_order/{so['id']}", 
                    headers=self.H("admin"), timeout=40)
                trace = r.json() if r.status_code == 200 else {}
                
                self.test("trace from sales_order returns 200", r.status_code == 200)
                self.test("trace has anchor", bool(trace.get("anchor")))
                self.test("trace has nodes", isinstance(trace.get("nodes"), list))
                self.test("trace has edges", isinstance(trace.get("edges"), list))
                self.test("trace has groups", isinstance(trace.get("groups"), list))
                self.test("trace has depth", "depth" in trace)
                self.test("trace has node_count", "node_count" in trace)
                self.test("trace has edge_count", "edge_count" in trace)
                
                # Test depth parameter
                r_depth1 = requests.get(f"{BASE_URL}/documents/trace/sales_order/{so['id']}", 
                    headers=self.H("admin"), params={"depth": 1}, timeout=40)
                trace_depth1 = r_depth1.json() if r_depth1.status_code == 200 else {}
                self.test("trace with depth=1 returns 200", r_depth1.status_code == 200)
                self.test("trace depth=1 has fewer nodes", 
                    len(trace_depth1.get("nodes", [])) <= len(trace.get("nodes", [])))
                
                # Test 404 for non-existent doc
                r_404 = requests.get(f"{BASE_URL}/documents/trace/sales_order/nonexistent_id", 
                    headers=self.H("admin"), timeout=30)
                self.test("trace returns 404 for non-existent doc", r_404.status_code == 404)
                
                # Test trace from purchase_order
                pos = requests.get(f"{BASE_URL}/purchase-orders", headers=self.H("admin"), 
                    params={"limit": 50}, timeout=40).json()
                po_list = pos if isinstance(pos, list) else pos.get("items", [])
                po = po_list[0] if po_list else None
                
                if po:
                    r_po = requests.get(f"{BASE_URL}/documents/trace/purchase_order/{po['id']}", 
                        headers=self.H("admin"), timeout=40)
                    self.test("trace from purchase_order returns 200", r_po.status_code == 200)
                
                # Test trace from vendor_bill (mid-chain)
                bills = requests.get(f"{BASE_URL}/vendor-bills", headers=self.H("admin"), 
                    params={"limit": 50}, timeout=40).json()
                bill_list = bills if isinstance(bills, list) else bills.get("items", [])
                bill = bill_list[0] if bill_list else None
                
                if bill:
                    r_bill = requests.get(f"{BASE_URL}/documents/trace/vendor_bill/{bill['id']}", 
                        headers=self.H("admin"), timeout=40)
                    self.test("trace from vendor_bill (mid-chain) returns 200", r_bill.status_code == 200)
                
                # Test trace from ar_receipt (mid-chain)
                receipts = requests.get(f"{BASE_URL}/ar-receipts", headers=self.H("admin"), 
                    params={"limit": 50}, timeout=40).json()
                receipt_list = receipts if isinstance(receipts, list) else receipts.get("items", [])
                receipt = receipt_list[0] if receipt_list else None
                
                if receipt:
                    r_receipt = requests.get(f"{BASE_URL}/documents/trace/ar_receipt/{receipt['id']}", 
                        headers=self.H("admin"), timeout=40)
                    self.test("trace from ar_receipt (mid-chain) returns 200", r_receipt.status_code == 200)
                
                # Test trace from grn/wms_tasks inbound
                tasks = requests.get(f"{BASE_URL}/wms/tasks", headers=self.H("admin"), 
                    params={"flow_type": "inbound", "limit": 50}, timeout=40).json()
                task_list = tasks if isinstance(tasks, list) else tasks.get("items", [])
                task = task_list[0] if task_list else None
                
                if task:
                    r_task = requests.get(f"{BASE_URL}/documents/trace/grn/{task['id']}", 
                        headers=self.H("admin"), timeout=40)
                    self.test("trace from grn (inbound task) returns 200", r_task.status_code == 200)
            else:
                self.test("trace tests", False, "No sales orders found for testing")
        except Exception as e:
            self.test("trace API", False, str(e))

        # TEST GROUP 3: Document Refs (bidirectional)
        print("\n[TEST 3] GET /api/documents/refs/{doc_type}/{doc_id} — Bidirectional refs")
        try:
            if so:
                r = requests.get(f"{BASE_URL}/documents/refs/sales_order/{so['id']}", 
                    headers=self.H("admin"), timeout=30)
                refs_data = r.json() if r.status_code == 200 else {}
                
                self.test("refs returns 200", r.status_code == 200)
                self.test("refs has doc_type", refs_data.get("doc_type") == "sales_order")
                self.test("refs has doc_id", refs_data.get("doc_id") == so["id"])
                self.test("refs has number", bool(refs_data.get("number")))
                self.test("refs has refs array", isinstance(refs_data.get("refs"), list))
                self.test("refs has anchor", bool(refs_data.get("anchor")))
                
                # Check ref structure
                refs = refs_data.get("refs", [])
                if refs:
                    ref = refs[0]
                    self.test("ref has rel_label", bool(ref.get("rel_label")))
                    self.test("ref has label", bool(ref.get("label")))
                    self.test("ref has alive status", "alive" in ref)
                    self.test("ref has link", bool(ref.get("link")))
        except Exception as e:
            self.test("refs API", False, str(e))

        # TEST GROUP 4: Trace Search
        print("\n[TEST 4] GET /api/documents/trace-search?q= — Cross-document search")
        try:
            # Search with valid query
            r = requests.get(f"{BASE_URL}/documents/trace-search", 
                headers=self.H("admin"), params={"q": "SO-000"}, timeout=30)
            results = r.json() if r.status_code == 200 else []
            
            self.test("trace-search with 'SO-000' returns 200", r.status_code == 200)
            self.test("trace-search returns array", isinstance(results, list))
            
            # Search with different patterns
            r2 = requests.get(f"{BASE_URL}/documents/trace-search", 
                headers=self.H("admin"), params={"q": "AR-"}, timeout=30)
            self.test("trace-search with 'AR-' returns 200", r2.status_code == 200)
            
            r3 = requests.get(f"{BASE_URL}/documents/trace-search", 
                headers=self.H("admin"), params={"q": "PO-"}, timeout=30)
            self.test("trace-search with 'PO-' returns 200", r3.status_code == 200)
            
            # Search with < 2 chars should return empty
            r4 = requests.get(f"{BASE_URL}/documents/trace-search", 
                headers=self.H("admin"), params={"q": "S"}, timeout=30)
            results4 = r4.json() if r4.status_code == 200 else []
            self.test("trace-search with 1 char returns empty array", 
                r4.status_code == 200 and len(results4) == 0)
        except Exception as e:
            self.test("trace-search API", False, str(e))

        # TEST GROUP 5: Backfill (idempotent, admin-only)
        print("\n[TEST 5] POST /api/documents/refs/backfill?dry_run=true — Idempotent backfill")
        try:
            # Admin can run dry_run
            r = requests.post(f"{BASE_URL}/documents/refs/backfill?dry_run=true", 
                headers=self.H("admin"), timeout=180)
            result = r.json() if r.status_code == 200 else {}
            
            self.test("backfill dry_run by admin returns 200", r.status_code == 200)
            self.test("backfill dry_run is idempotent (no changes)", result.get("dry_run") is True)
            self.test("backfill has candidates count", "candidates" in result)
            self.test("backfill has would_add count", "would_add" in result)
            
            # Sales cannot run backfill (403)
            r_sales = requests.post(f"{BASE_URL}/documents/refs/backfill?dry_run=true", 
                headers=self.H("sales"), timeout=60)
            self.test("backfill by sales returns 403 (RBAC)", r_sales.status_code == 403)
            
            # Warehouse cannot run backfill (403)
            r_wh = requests.post(f"{BASE_URL}/documents/refs/backfill?dry_run=true", 
                headers=self.H("warehouse"), timeout=60)
            self.test("backfill by warehouse returns 403 (RBAC)", r_wh.status_code == 403)
            
            # Test dry_run=false (only if would_add is 0, to avoid changing data)
            if result.get("would_add", 0) == 0:
                r_apply = requests.post(f"{BASE_URL}/documents/refs/backfill?dry_run=false", 
                    headers=self.H("admin"), timeout=180)
                apply_result = r_apply.json() if r_apply.status_code == 200 else {}
                self.test("backfill apply when complete returns 200", r_apply.status_code == 200)
                
                # After apply, dry_run should report would_add=0
                r_check = requests.post(f"{BASE_URL}/documents/refs/backfill?dry_run=true", 
                    headers=self.H("admin"), timeout=180)
                check_result = r_check.json() if r_check.status_code == 200 else {}
                self.test("backfill after apply reports would_add=0", 
                    check_result.get("would_add", -1) == 0)
        except Exception as e:
            self.test("backfill API", False, str(e))

        # TEST GROUP 6: PDF Documents List (NEW fields)
        print("\n[TEST 6] GET /api/pdf/documents/{doc_type} — NEW fields: trace_type, ref_count, e-sign status")
        try:
            for doc_type in ["sales_order", "invoice", "delivery_note", "purchase_order", "vendor_bill", "ar_receipt"]:
                r = requests.get(f"{BASE_URL}/pdf/documents/{doc_type}", 
                    headers=self.H("admin"), params={"limit": 10}, timeout=60)
                data = r.json() if r.status_code == 200 else {}
                docs = data.get("documents", [])
                
                self.test(f"pdf/documents/{doc_type} returns 200", r.status_code == 200)
                
                if docs:
                    doc = docs[0]
                    self.test(f"pdf/documents/{doc_type} has trace_type", "trace_type" in doc)
                    self.test(f"pdf/documents/{doc_type} has ref_count", "ref_count" in doc)
                    self.test(f"pdf/documents/{doc_type} has signed", "signed" in doc)
                    self.test(f"pdf/documents/{doc_type} has sign_count", "sign_count" in doc)
                    self.test(f"pdf/documents/{doc_type} has esignable", "esignable" in doc)
        except Exception as e:
            self.test("pdf/documents API", False, str(e))

        # TEST GROUP 7: PDF Render HTML (refs block + QR)
        print("\n[TEST 7] GET /api/pdf/render/{doc_type}/{source_id}?format=html — HTML with refs block + QR")
        try:
            if so:
                headers_html = {**self.H("admin"), "Accept": "text/html"}
                r = requests.get(f"{BASE_URL}/pdf/render/invoice/{so['id']}", 
                    headers=headers_html, params={"format": "html"}, timeout=90)
                html = r.text if r.status_code == 200 else ""
                
                self.test("pdf/render invoice HTML returns 200", r.status_code == 200)
                self.test("pdf/render HTML has refs block", 'class="refs"' in html)
                self.test("pdf/render HTML has 'Merujuk:'", "Merujuk:" in html)
                self.test("pdf/render HTML has QR code", 
                    "data:image/png;base64" in html or "jejak-dokumen" in html)
                
                # Test delivery_note
                r2 = requests.get(f"{BASE_URL}/pdf/render/delivery_note/{so['id']}", 
                    headers=headers_html, params={"format": "html"}, timeout=90)
                self.test("pdf/render delivery_note HTML returns 200", r2.status_code == 200)
                
            if po:
                # Test purchase_order
                headers_html = {**self.H("admin"), "Accept": "text/html"}
                r3 = requests.get(f"{BASE_URL}/pdf/render/purchase_order/{po['id']}", 
                    headers=headers_html, params={"format": "html"}, timeout=90)
                self.test("pdf/render purchase_order HTML returns 200", r3.status_code == 200)
        except Exception as e:
            self.test("pdf/render HTML API", False, str(e))

        # TEST GROUP 8: E-Sign Flow
        print("\n[TEST 8] E-Sign Flow: request → verify → public verification")
        try:
            if so:
                # Request e-sign
                r_req = requests.post(f"{BASE_URL}/esign/request", 
                    headers=self.H("admin"), timeout=60, json={
                        "doc_type": "sales_order", "source_id": so["id"],
                        "signer_name": "Test Signer", "signer_role": "Manager Penjualan",
                        "signer_contact": "081234567890"
                    })
                req_data = r_req.json() if r_req.status_code == 200 else {}
                
                self.test("esign/request returns 200", r_req.status_code == 200)
                self.test("esign/request has request_id", bool(req_data.get("request_id")))
                self.test("esign/request has channel", bool(req_data.get("channel")))
                
                # Get OTP from simulated response
                otp = req_data.get("reveal_code") or req_data.get("simulated", {}).get("code", "")
                if isinstance(otp, dict):
                    otp = otp.get("code", "")
                
                if req_data.get("request_id") and otp:
                    # Verify e-sign
                    r_verify = requests.post(f"{BASE_URL}/esign/verify", 
                        headers=self.H("admin"), timeout=60, json={
                            "request_id": req_data["request_id"], "otp": str(otp),
                            "signature_b64": "iVBORw0KGgoAAAANSUhEUg=="
                        })
                    verify_data = r_verify.json() if r_verify.status_code == 200 else {}
                    
                    self.test("esign/verify returns 200", r_verify.status_code == 200)
                    self.test("esign/verify has verification_code", bool(verify_data.get("verification_code")))
                    self.test("esign/verify has doc_hash (SHA-256)", 
                        len(verify_data.get("doc_hash", "")) == 64)
                    
                    if verify_data.get("verification_code"):
                        # Public verification (no login required)
                        r_public = requests.get(
                            f"{BASE_URL}/esign/verify/{verify_data['verification_code']}", 
                            timeout=30)
                        public_data = r_public.json() if r_public.status_code == 200 else {}
                        
                        self.test("esign/verify/{code} public access returns 200", r_public.status_code == 200)
                        self.test("esign/verify public has valid=True", public_data.get("valid") is True)
                        self.test("esign/verify public has signers", bool(public_data.get("signers")))
                        
                        # Check signer has role and signed_at
                        signers = public_data.get("signers", [])
                        if signers:
                            signer = signers[0]
                            self.test("esign signer has role (JABATAN)", bool(signer.get("role")))
                            self.test("esign signer has signed_at (WAKTU)", bool(signer.get("signed_at")))
                        
                        # Check HTML render shows verification
                        headers_html = {**self.H("admin"), "Accept": "text/html"}
                        r_html = requests.get(f"{BASE_URL}/pdf/render/sales_order/{so['id']}", 
                            headers=headers_html, params={"format": "html"}, timeout=90)
                        html = r_html.text if r_html.status_code == 200 else ""
                        self.test("pdf/render after e-sign has 'DOKUMEN TERVERIFIKASI ELEKTRONIK'", 
                            "DOKUMEN TERVERIFIKASI ELEKTRONIK" in html)
                        self.test("pdf/render after e-sign shows JABATAN", 
                            "Manager Penjualan" in html or "JABATAN" in html.lower())
        except Exception as e:
            self.test("e-sign flow", False, str(e))

        # TEST GROUP 9: Regression - existing endpoints still return refs[]
        print("\n[TEST 9] Regression: existing endpoints still return refs[]")
        try:
            # GET /api/sales-orders
            r_so = requests.get(f"{BASE_URL}/sales-orders", 
                headers=self.H("admin"), params={"limit": 10}, timeout=40)
            so_data = r_so.json()
            so_items = so_data if isinstance(so_data, list) else so_data.get("items", [])
            self.test("GET /api/sales-orders returns 200", r_so.status_code == 200)
            if so_items:
                self.test("sales-orders items have refs[] field", "refs" in so_items[0])
            
            # GET /api/purchase-orders
            r_po = requests.get(f"{BASE_URL}/purchase-orders", 
                headers=self.H("admin"), params={"limit": 10}, timeout=40)
            self.test("GET /api/purchase-orders returns 200", r_po.status_code == 200)
            
            # GET /api/vendor-bills
            r_vb = requests.get(f"{BASE_URL}/vendor-bills", 
                headers=self.H("admin"), params={"limit": 10}, timeout=40)
            self.test("GET /api/vendor-bills returns 200", r_vb.status_code == 200)
            
            # GET /api/ar-receipts
            r_ar = requests.get(f"{BASE_URL}/ar-receipts", 
                headers=self.H("admin"), params={"limit": 10}, timeout=40)
            self.test("GET /api/ar-receipts returns 200", r_ar.status_code == 200)
            
            # GET /api/wms/tasks
            r_wms = requests.get(f"{BASE_URL}/wms/tasks", 
                headers=self.H("admin"), params={"limit": 10}, timeout=40)
            self.test("GET /api/wms/tasks returns 200", r_wms.status_code == 200)
        except Exception as e:
            self.test("regression tests", False, str(e))

        return True

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_failed}")
        
        if self.tests_failed > 0:
            print(f"\n❌ FAILED TESTS ({self.tests_failed}):")
            for failure in self.failures:
                print(f"  - {failure}")
            return 1
        else:
            print("\n✅ ALL TESTS PASSED!")
            return 0

def main():
    tester = G4APITester()
    tester.run_all_tests()
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
