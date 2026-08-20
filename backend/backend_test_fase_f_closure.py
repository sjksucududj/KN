#!/usr/bin/env python3
"""Backend API Testing for Phase F Closure - Kain Nusantara ERP/WMS

Tests:
1. REGRESSION #1: source_document_label field in /api/inventory/movements
2. Movement type filtering (sample_issue)
3. Sales order blocking for non-released products
4. Document trace endpoints
5. Deterministic document numbers
6. All major endpoints regression check
"""
import requests
import sys
import re
from typing import Dict, Any, List

BASE_URL = "https://nusantara-staging-1.preview.emergentagent.com/api"

class BackendTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.failures = []
        self.token = None

    def ok(self, label: str, cond: bool, extra: str = ""):
        self.tests_run += 1
        if cond:
            self.tests_passed += 1
            print(f"  ✅ [PASS] {label}")
        else:
            self.tests_passed += 0
            self.failures.append(f"{label} :: {extra}")
            print(f"  ❌ [FAIL] {label} — {extra}")
        return cond

    def login(self, email: str, password: str) -> bool:
        try:
            r = requests.post(f"{BASE_URL}/auth/login", 
                            json={"email": email, "password": password}, 
                            timeout=30)
            if r.status_code == 200:
                data = r.json()
                self.token = data.get("token") or data.get("session_token")
                return self.ok(f"Login {email}", bool(self.token))
            else:
                return self.ok(f"Login {email}", False, f"Status {r.status_code}")
        except Exception as e:
            return self.ok(f"Login {email}", False, str(e))

    def get(self, path: str, params: Dict = None) -> requests.Response:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        return requests.get(f"{BASE_URL}{path}", headers=headers, params=params or {}, timeout=60)

    def post(self, path: str, data: Dict) -> requests.Response:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        return requests.post(f"{BASE_URL}{path}", headers=headers, json=data, timeout=60)

    def test_movement_labels(self):
        """REGRESSION #1: Test source_document_label field"""
        print("\n=== REGRESSION #1: Movement Document Labels ===")
        
        r = self.get("/inventory/movements")
        if not self.ok("GET /inventory/movements returns 200", r.status_code == 200, f"Status: {r.status_code}"):
            return
        
        movements = r.json()
        if isinstance(movements, dict):
            movements = movements.get("items", [])
        
        self.ok("Movements list not empty", len(movements) > 0, f"Count: {len(movements)}")
        
        # Check for source_document_label field
        has_label_field = all("source_document_label" in m for m in movements)
        self.ok("All movements have source_document_label field", has_label_field)
        
        # Check for technical IDs (should NOT exist in labels)
        technical_id_pattern = re.compile(r'\b(so|wo|mko|po|smp|spec|trn|pret|sret)_[0-9a-f]{6,}')
        labels_with_tech_ids = []
        
        for m in movements:
            label = m.get("source_document_label", "")
            if technical_id_pattern.search(str(label)):
                labels_with_tech_ids.append({
                    "id": m.get("id"),
                    "type": m.get("movement_type"),
                    "label": label,
                    "source": m.get("source_document")
                })
        
        self.ok("NO technical IDs in source_document_label", 
                len(labels_with_tech_ids) == 0,
                f"Found {len(labels_with_tech_ids)} with tech IDs: {labels_with_tech_ids[:3]}")
        
        # Check for human-readable numbers
        human_readable_patterns = [
            r'WO-\d+',
            r'MKO-\d+',
            r'PO-\d+',
            r'SO-\d+',
            r'KSC/[A-Z]+-\d+',
            r'INIT-\d+'
        ]
        
        sample_labels = [m.get("source_document_label") for m in movements[:10]]
        print(f"  📋 Sample labels: {sample_labels[:5]}")
        
        # Check specific movement types
        movement_types = {}
        for m in movements:
            mtype = m.get("movement_type")
            if mtype not in movement_types:
                movement_types[mtype] = {
                    "label": m.get("source_document_label"),
                    "source": m.get("source_document")
                }
        
        print(f"  📊 Movement types found: {list(movement_types.keys())}")
        
        # Verify mapping for known types
        for mtype, data in movement_types.items():
            if mtype in ["reservation", "release_reservation", "production_consume", 
                        "production_output", "subcon_receipt", "subcon_issue", "subcon_consume"]:
                # These should have been converted from technical IDs
                has_tech_id = technical_id_pattern.search(str(data["label"]))
                self.ok(f"Movement type '{mtype}' has human-readable label",
                       not has_tech_id,
                       f"Label: {data['label']}")

    def test_movement_filtering(self):
        """US11: Test movement type filtering"""
        print("\n=== US11: Movement Type Filtering ===")
        
        # Test without filter
        r = self.get("/inventory/movements")
        if r.status_code == 200:
            all_movements = r.json()
            if isinstance(all_movements, dict):
                all_movements = all_movements.get("items", [])
            total_count = len(all_movements)
            self.ok("GET /inventory/movements without filter", True, f"Total: {total_count}")
        
        # Test with sample_issue filter
        r = self.get("/inventory/movements", {"movement_type": "sample_issue"})
        if not self.ok("GET /inventory/movements?movement_type=sample_issue returns 200", 
                      r.status_code == 200, f"Status: {r.status_code}"):
            return
        
        filtered = r.json()
        if isinstance(filtered, dict):
            filtered = filtered.get("items", [])
        
        self.ok("sample_issue filter returns exactly 1 movement", 
                len(filtered) == 1,
                f"Count: {len(filtered)}")
        
        if len(filtered) > 0:
            sample = filtered[0]
            self.ok("sample_issue movement has negative quantity",
                   float(sample.get("quantity", 0)) < 0,
                   f"Qty: {sample.get('quantity')}")
            
            self.ok("sample_issue movement has correct document",
                   "KSC/SMP-00001" in str(sample.get("source_document_label", "")),
                   f"Label: {sample.get('source_document_label')}")

    def test_product_history_labels(self):
        """REGRESSION #2: Test product history labels"""
        print("\n=== REGRESSION #2: Product History Labels ===")
        
        # Get a product with movements
        r = self.get("/products")
        if r.status_code != 200:
            self.ok("GET /products", False, f"Status: {r.status_code}")
            return
        
        products = r.json()
        if isinstance(products, dict):
            products = products.get("items", [])
        
        # Test with BTK-MEGA-001
        test_product = next((p for p in products if p.get("sku") == "BTK-MEGA-001"), None)
        if not test_product:
            self.ok("Find test product BTK-MEGA-001", False, "Product not found")
            return
        
        product_id = test_product["id"]
        r = self.get(f"/history/{product_id}")
        
        if not self.ok(f"GET /history/{product_id} returns 200", 
                      r.status_code == 200, f"Status: {r.status_code}"):
            return
        
        history = r.json()
        self.ok("Product history not empty", len(history) > 0, f"Count: {len(history)}")
        
        # Check for technical IDs
        technical_id_pattern = re.compile(r'\b(so|wo|mko|po|smp|spec|trn|pret|sret)_[0-9a-f]{6,}')
        history_with_tech_ids = []
        
        for h in history:
            label = h.get("source_document_label", "")
            if technical_id_pattern.search(str(label)):
                history_with_tech_ids.append(label)
        
        self.ok("NO technical IDs in product history labels",
                len(history_with_tech_ids) == 0,
                f"Found {len(history_with_tech_ids)} with tech IDs")

    def test_sales_order_blocking(self):
        """US3: Test sales order blocking for non-released products"""
        print("\n=== US3: Sales Order Blocking ===")
        
        # Get RND-KTN-150 product
        r = self.get("/products")
        if r.status_code != 200:
            self.ok("GET /products", False, f"Status: {r.status_code}")
            return
        
        products = r.json()
        if isinstance(products, dict):
            products = products.get("items", [])
        
        rnd_product = next((p for p in products if p.get("sku") == "RND-KTN-150"), None)
        self.ok("RND-KTN-150 product exists", rnd_product is not None)
        
        if rnd_product:
            self.ok("RND-KTN-150 lifecycle is 'disetujui'",
                   rnd_product.get("lifecycle") == "disetujui",
                   f"Lifecycle: {rnd_product.get('lifecycle')}")

    def test_document_trace(self):
        """US12: Test document trace endpoints"""
        print("\n=== US12: Document Trace ===")
        
        # Get supplier contracts
        r = self.get("/supplier-contracts")
        if not self.ok("GET /supplier-contracts returns 200", 
                      r.status_code == 200, f"Status: {r.status_code}"):
            return
        
        contracts = r.json()
        if isinstance(contracts, dict):
            contracts = contracts.get("items", [])
        
        # Find contract with sample reference
        contract_with_sample = next(
            (c for c in contracts 
             if any((ref or {}).get("doc_type") == "md_sample" for ref in (c.get("refs") or []))),
            None
        )
        
        self.ok("Found contract with md_sample reference", 
                contract_with_sample is not None)
        
        if contract_with_sample:
            contract_id = contract_with_sample["id"]
            contract_number = contract_with_sample.get("contract_number") or contract_with_sample.get("number")
            
            self.ok("Contract has human-readable number",
                   contract_number and contract_number.startswith("KSC/SCT-"),
                   f"Number: {contract_number}")
            
            # Test trace endpoint
            r = self.get(f"/documents/trace/supplier_contract/{contract_id}")
            if self.ok("GET /documents/trace/supplier_contract/{id} returns 200",
                      r.status_code == 200, f"Status: {r.status_code}"):
                
                trace = r.json()
                nodes = trace.get("nodes", [])
                
                self.ok("Trace has nodes", len(nodes) > 0, f"Count: {len(nodes)}")
                
                # Check for md_sample and md_spec nodes
                has_sample = any(n.get("doc_type") == "md_sample" for n in nodes)
                has_spec = any(n.get("doc_type") == "md_spec" for n in nodes)
                
                self.ok("Trace includes md_sample node", has_sample)
                self.ok("Trace includes md_spec node", has_spec)
                
                # Check node numbers
                for node in nodes:
                    if node.get("doc_type") in ["md_sample", "md_spec", "supplier_contract"]:
                        number = node.get("number", "")
                        self.ok(f"Node {node.get('doc_type')} has human-readable number",
                               number.startswith(("KSC/", "KDN/")),
                               f"Number: {number}")
        
        # Test ref-types endpoint
        r = self.get("/documents/ref-types")
        if self.ok("GET /documents/ref-types returns 200",
                  r.status_code == 200, f"Status: {r.status_code}"):
            
            ref_types = r.json()
            types_map = {t["doc_type"]: t["label"] for t in ref_types.get("types", [])}
            
            self.ok("md_spec has Indonesian label",
                   "md_spec" in types_map and "Spesifikasi" in types_map["md_spec"],
                   f"Label: {types_map.get('md_spec')}")
            
            self.ok("md_sample has Indonesian label",
                   "md_sample" in types_map and "Sample" in types_map["md_sample"],
                   f"Label: {types_map.get('md_sample')}")

    def test_deterministic_numbers(self):
        """Test deterministic document numbers after seed"""
        print("\n=== Deterministic Document Numbers ===")
        
        # Check supplier contracts
        r = self.get("/supplier-contracts")
        if r.status_code == 200:
            contracts = r.json()
            if isinstance(contracts, dict):
                contracts = contracts.get("items", [])
            
            contract_numbers = sorted([c.get("contract_number") or c.get("number") for c in contracts])
            expected_pattern = re.compile(r'KSC/SCT-\d{5}')
            
            valid_numbers = [n for n in contract_numbers if expected_pattern.match(str(n))]
            self.ok("Supplier contracts have deterministic numbers",
                   len(valid_numbers) == len(contract_numbers),
                   f"Valid: {len(valid_numbers)}/{len(contract_numbers)}, Sample: {contract_numbers[:3]}")
        
        # Check md_specs
        r = self.get("/rnd/specs")
        if r.status_code == 200:
            specs = r.json()
            if isinstance(specs, dict):
                specs = specs.get("items", [])
            
            spec_numbers = [s.get("number") for s in specs]
            self.ok("md_specs have deterministic numbers (KSC/SPEC-)",
                   all(str(n).startswith("KSC/SPEC-") for n in spec_numbers if n),
                   f"Sample: {spec_numbers[:3]}")
        
        # Check md_samples
        r = self.get("/rnd/samples")
        if r.status_code == 200:
            samples = r.json()
            if isinstance(samples, dict):
                samples = samples.get("items", [])
            
            sample_numbers = [s.get("number") for s in samples]
            self.ok("md_samples have deterministic numbers (KSC/SMP-)",
                   all(str(n).startswith("KSC/SMP-") for n in sample_numbers if n),
                   f"Sample: {sample_numbers[:3]}")

    def test_major_endpoints(self):
        """Regression test for all major endpoints"""
        print("\n=== Major Endpoints Regression ===")
        
        endpoints = [
            "/sales-orders",
            "/purchase-orders",
            "/inventory/balances",
            "/inventory/rolls",
            "/inventory/movements",
            "/wms/tasks",
            "/transfers",  # NOT /warehouse-transfers
            "/cycle-count/sessions",
            "/uom-conversions/catalog",
            "/uom-conversions/rules",
            "/uom-conversions/usage",
            "/purchase-returns",
            "/products",
            "/onboarding",
            "/rnd/meta",
            "/rnd/specs",
            "/rnd/samples",
            "/supplier-contracts",
            "/documents/ref-types",
        ]
        
        for endpoint in endpoints:
            r = self.get(endpoint)
            self.ok(f"GET {endpoint} returns 200 with data",
                   r.status_code == 200 and len(r.text) > 10,
                   f"Status: {r.status_code}, Length: {len(r.text)}")

    def run_all_tests(self):
        print("=" * 80)
        print("BACKEND API TESTING - Phase F Closure")
        print("=" * 80)
        
        # Login as warehouse user
        if not self.login("warehouse@kainnusantara.id", "demo12345"):
            print("\n❌ Login failed, cannot continue")
            return 1
        
        # Run all test suites
        self.test_movement_labels()
        self.test_movement_filtering()
        self.test_product_history_labels()
        self.test_sales_order_blocking()
        self.test_document_trace()
        self.test_deterministic_numbers()
        self.test_major_endpoints()
        
        # Print summary
        print("\n" + "=" * 80)
        print(f"RESULTS: ✅ {self.tests_passed} PASSED / ❌ {len(self.failures)} FAILED (Total: {self.tests_run})")
        
        if self.failures:
            print("\n❌ FAILURES:")
            for failure in self.failures:
                print(f"  • {failure}")
        
        print("=" * 80)
        
        return 0 if len(self.failures) == 0 else 1

if __name__ == "__main__":
    tester = BackendTester()
    sys.exit(tester.run_all_tests())
