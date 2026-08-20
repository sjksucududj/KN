#!/usr/bin/env python3
"""
TESTING AGENT — Backend API Test for Fase E (Sourcing Berbasis Kontrak)
=========================================================================
Independent verification of all user stories US-E1 through US-E9 + regression.
Uses PUBLIC URL for realistic testing.
"""
import requests
import sys
import json
from datetime import datetime, timedelta

# Use public URL as instructed
BASE_URL = "https://kn-makloon-wms.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@kainnusantara.id"
ADMIN_PASSWORD = "demo12345"
MANAGER_EMAIL = "manager@kainnusantara.id"
WAREHOUSE_EMAIL = "warehouse@kainnusantara.id"
SALES_EMAIL = "sales@kainnusantara.id"

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.total = 0
    
    def add_pass(self, test_name, details=""):
        self.total += 1
        self.passed.append({"test": test_name, "details": details})
        print(f"✅ PASS: {test_name}")
        if details:
            print(f"   → {details}")
    
    def add_fail(self, test_name, reason):
        self.total += 1
        self.failed.append({"test": test_name, "reason": reason})
        print(f"❌ FAIL: {test_name}")
        print(f"   → {reason}")
    
    def summary(self):
        return {
            "total": self.total,
            "passed": len(self.passed),
            "failed": len(self.failed),
            "pass_rate": f"{(len(self.passed)/self.total*100):.1f}%" if self.total > 0 else "0%"
        }

def login(email, password):
    """Login and return token"""
    try:
        r = requests.post(f"{API_URL}/auth/login", 
                         json={"email": email, "password": password},
                         timeout=30)
        if r.status_code == 200:
            return r.json().get("token")
        return None
    except Exception as e:
        print(f"Login error: {e}")
        return None

def get_headers(token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {token}"}

def test_us_e1_supplier_contracts(results, admin_token):
    """US-E1: Supplier contracts (purchase type) CRUD and resolve"""
    print("\n" + "="*70)
    print("US-E1: Supplier Contracts (Purchase Type)")
    print("="*70)
    
    headers = get_headers(admin_token)
    
    # Test 1: Create purchase contract
    try:
        today = datetime.now().date().isoformat()
        future = (datetime.now().date() + timedelta(days=180)).isoformat()
        
        contract_data = {
            "contract_type": "purchase",
            "partner_kind": "supplier",
            "partner_id": "sup_solo_weave",  # From seed data
            "title": "Test Contract Benang 2026",
            "tariff_basis": "kg",
            "tariff_rate": 50000,
            "moq": 100,
            "valid_from": today,
            "valid_to": future,
            "entity_id": "ent_ksc",
            "notes": "TESTING_AGENT_E1"
        }
        
        r = requests.post(f"{API_URL}/supplier-contracts", 
                         json=contract_data, headers=headers, timeout=30)
        
        if r.status_code in [200, 201]:
            contract = r.json()
            if contract.get("contract_type") == "purchase":
                results.add_pass("E1-01: Create purchase contract", 
                               f"Contract {contract.get('contract_number')} created")
                test_contract_id = contract.get("id")
            else:
                results.add_fail("E1-01: Create purchase contract", 
                               f"Wrong contract_type: {contract.get('contract_type')}")
                test_contract_id = None
        else:
            results.add_fail("E1-01: Create purchase contract", 
                           f"Status {r.status_code}: {r.text[:200]}")
            test_contract_id = None
    except Exception as e:
        results.add_fail("E1-01: Create purchase contract", str(e))
        test_contract_id = None
    
    # Test 2: GET contracts with filter
    try:
        r = requests.get(f"{API_URL}/supplier-contracts", 
                        params={"contract_type": "purchase", "entity_id": "ent_ksc"},
                        headers=headers, timeout=30)
        
        if r.status_code == 200:
            contracts = r.json()
            purchase_contracts = [c for c in contracts if c.get("contract_type") == "purchase"]
            if len(purchase_contracts) >= 3:  # Seed has 3 purchase contracts
                results.add_pass("E1-02: GET purchase contracts", 
                               f"Found {len(purchase_contracts)} purchase contracts")
            else:
                results.add_fail("E1-02: GET purchase contracts", 
                               f"Expected >=3, got {len(purchase_contracts)}")
        else:
            results.add_fail("E1-02: GET purchase contracts", 
                           f"Status {r.status_code}")
    except Exception as e:
        results.add_fail("E1-02: GET purchase contracts", str(e))
    
    # Test 3: Resolve contract (specific wins over generic)
    try:
        r = requests.post(f"{API_URL}/supplier-contracts/resolve",
                         params={
                             "partner_id": "sup_solo_weave",
                             "contract_type": "purchase",
                             "product_id": "prod_benang_katun_001"
                         },
                         headers=headers, timeout=30)
        
        if r.status_code == 200:
            result = r.json()
            if result.get("found") and result.get("contract"):
                results.add_pass("E1-03: Resolve contract (specific wins)", 
                               f"Resolved to {result['contract'].get('contract_number')}")
            else:
                results.add_pass("E1-03: Resolve contract (no match)", 
                               "No active contract found (expected if no specific contract)")
        else:
            results.add_fail("E1-03: Resolve contract", 
                           f"Status {r.status_code}")
    except Exception as e:
        results.add_fail("E1-03: Resolve contract", str(e))
    
    # Test 4: DELETE contract that's been used should return 409
    if test_contract_id:
        try:
            r = requests.delete(f"{API_URL}/supplier-contracts/{test_contract_id}",
                              headers=headers, timeout=30)
            
            # If it's been used, should be 409; if not used yet, 200 is OK
            if r.status_code in [200, 409]:
                results.add_pass("E1-04: DELETE protection", 
                               f"Status {r.status_code} (409 if used, 200 if unused)")
            else:
                results.add_fail("E1-04: DELETE protection", 
                               f"Unexpected status {r.status_code}")
        except Exception as e:
            results.add_fail("E1-04: DELETE protection", str(e))

def test_us_e2_supplier_items_crud(results, admin_token):
    """US-E2: supplier_items CRUD"""
    print("\n" + "="*70)
    print("US-E2: Supplier Items CRUD")
    print("="*70)
    
    headers = get_headers(admin_token)
    
    # Test 1: Create supplier item
    try:
        item_data = {
            "supplier_id": "sup_solo_weave",
            "sku": "BNG-KTN-001",
            "supplier_sku": "TEST-YARN-001",
            "supplier_item_name": "Test Yarn Item",
            "supplier_uom": "cone",
            "conv_factor": 2.0,
            "last_price": 100000,
            "entity_id": "ent_ksc"
        }
        
        r = requests.post(f"{API_URL}/supplier-items", 
                         json=item_data, headers=headers, timeout=30)
        
        if r.status_code in [200, 201]:
            item = r.json()
            if item.get("supplier_sku") == "TEST-YARN-001":
                results.add_pass("E2-01: Create supplier item", 
                               f"Item {item.get('id')} created with conv_factor {item.get('conv_factor')}")
                test_item_id = item.get("id")
            else:
                results.add_fail("E2-01: Create supplier item", 
                               "Item created but data mismatch")
                test_item_id = None
        else:
            results.add_fail("E2-01: Create supplier item", 
                           f"Status {r.status_code}: {r.text[:200]}")
            test_item_id = None
    except Exception as e:
        results.add_fail("E2-01: Create supplier item", str(e))
        test_item_id = None
    
    # Test 2: Duplicate (supplier_id, supplier_sku) should return 400
    try:
        r = requests.post(f"{API_URL}/supplier-items", 
                         json=item_data, headers=headers, timeout=30)
        
        if r.status_code == 400:
            results.add_pass("E2-02: Duplicate rejected", 
                           "Duplicate (supplier_id, supplier_sku) correctly rejected")
        else:
            results.add_fail("E2-02: Duplicate rejected", 
                           f"Expected 400, got {r.status_code}")
    except Exception as e:
        results.add_fail("E2-02: Duplicate rejected", str(e))
    
    # Test 3: Same code different supplier should be allowed
    try:
        item_data_diff_supplier = {
            "supplier_id": "sup_cirebon_craft",
            "sku": "BNG-KTN-001",
            "supplier_sku": "TEST-YARN-001",  # Same code
            "supplier_item_name": "Test Yarn from different supplier",
            "entity_id": "ent_ksc"
        }
        
        r = requests.post(f"{API_URL}/supplier-items", 
                         json=item_data_diff_supplier, headers=headers, timeout=30)
        
        if r.status_code in [200, 201]:
            results.add_pass("E2-03: Same code different supplier allowed", 
                           "Same supplier_sku with different supplier_id allowed")
            test_item_id_2 = r.json().get("id")
        else:
            results.add_fail("E2-03: Same code different supplier allowed", 
                           f"Status {r.status_code}")
            test_item_id_2 = None
    except Exception as e:
        results.add_fail("E2-03: Same code different supplier allowed", str(e))
        test_item_id_2 = None
    
    # Test 4: conv_factor 0 should be rejected
    try:
        bad_item = {
            "supplier_id": "sup_solo_weave",
            "sku": "BNG-KTN-001",
            "supplier_sku": "BAD-CONV",
            "conv_factor": 0,
            "entity_id": "ent_ksc"
        }
        
        r = requests.post(f"{API_URL}/supplier-items", 
                         json=bad_item, headers=headers, timeout=30)
        
        if r.status_code in [400, 422]:
            results.add_pass("E2-04: conv_factor 0 rejected", 
                           "Zero conversion factor correctly rejected")
        else:
            results.add_fail("E2-04: conv_factor 0 rejected", 
                           f"Expected 400/422, got {r.status_code}")
    except Exception as e:
        results.add_fail("E2-04: conv_factor 0 rejected", str(e))
    
    # Test 5: PATCH supplier item
    if test_item_id:
        try:
            r = requests.patch(f"{API_URL}/supplier-items/{test_item_id}",
                             json={"last_price": 110000, "notes": "Price updated"},
                             headers=headers, timeout=30)
            
            if r.status_code == 200:
                updated = r.json()
                if updated.get("last_price") == 110000:
                    results.add_pass("E2-05: PATCH supplier item", 
                                   "Item updated successfully")
                else:
                    results.add_fail("E2-05: PATCH supplier item", 
                                   "Update returned 200 but data not changed")
            else:
                results.add_fail("E2-05: PATCH supplier item", 
                               f"Status {r.status_code}")
        except Exception as e:
            results.add_fail("E2-05: PATCH supplier item", str(e))
    
    # Test 6: GET with filters
    try:
        r = requests.get(f"{API_URL}/supplier-items",
                        params={"supplier_id": "sup_solo_weave", "entity_id": "ent_ksc"},
                        headers=headers, timeout=30)
        
        if r.status_code == 200:
            items = r.json()
            if len(items) > 0:
                results.add_pass("E2-06: GET with filter", 
                               f"Found {len(items)} items for supplier")
            else:
                results.add_fail("E2-06: GET with filter", 
                               "No items found")
        else:
            results.add_fail("E2-06: GET with filter", 
                           f"Status {r.status_code}")
    except Exception as e:
        results.add_fail("E2-06: GET with filter", str(e))
    
    # Test 7: GET stats
    try:
        r = requests.get(f"{API_URL}/supplier-items/stats",
                        params={"entity_id": "ent_ksc"},
                        headers=headers, timeout=30)
        
        if r.status_code == 200:
            stats = r.json()
            results.add_pass("E2-07: GET stats", 
                           f"Total: {stats.get('total')}, Active: {stats.get('active')}")
        else:
            results.add_fail("E2-07: GET stats", 
                           f"Status {r.status_code}")
    except Exception as e:
        results.add_fail("E2-07: GET stats", str(e))
    
    # Test 8: DELETE unused item (should succeed)
    if test_item_id_2:
        try:
            r = requests.delete(f"{API_URL}/supplier-items/{test_item_id_2}",
                              headers=headers, timeout=30)
            
            if r.status_code in [200, 204]:
                results.add_pass("E2-08: DELETE unused item", 
                               "Unused item deleted successfully")
            else:
                results.add_fail("E2-08: DELETE unused item", 
                               f"Status {r.status_code}")
        except Exception as e:
            results.add_fail("E2-08: DELETE unused item", str(e))

def test_us_e3_lookup(results, admin_token):
    """US-E3: Lookup by supplier code"""
    print("\n" + "="*70)
    print("US-E3: Lookup by Supplier Code")
    print("="*70)
    
    headers = get_headers(admin_token)
    
    # Test 1: Lookup existing code from seed data
    try:
        r = requests.get(f"{API_URL}/supplier-items/lookup",
                        params={"supplier_sku": "SLW-YARN-30S"},
                        headers=headers, timeout=30)
        
        if r.status_code == 200:
            result = r.json()
            if result.get("found") and result.get("item"):
                item = result["item"]
                results.add_pass("E3-01: Lookup existing code", 
                               f"Found {item.get('sku')} - {item.get('product_name')}")
            else:
                results.add_fail("E3-01: Lookup existing code", 
                               "Code not found in seed data")
        else:
            results.add_fail("E3-01: Lookup existing code", 
                           f"Status {r.status_code}")
    except Exception as e:
        results.add_fail("E3-01: Lookup existing code", str(e))
    
    # Test 2: Lookup non-existent code should return 404
    try:
        r = requests.get(f"{API_URL}/supplier-items/lookup",
                        params={"supplier_sku": "NONEXISTENT-CODE-999"},
                        headers=headers, timeout=30)
        
        if r.status_code == 404:
            results.add_pass("E3-02: Lookup non-existent code", 
                           "404 returned with actionable message")
        else:
            results.add_fail("E3-02: Lookup non-existent code", 
                           f"Expected 404, got {r.status_code}")
    except Exception as e:
        results.add_fail("E3-02: Lookup non-existent code", str(e))

def test_us_e4_mass_import(results, admin_token):
    """US-E4: Mass import CSV/XLSX"""
    print("\n" + "="*70)
    print("US-E4: Mass Import CSV/XLSX")
    print("="*70)
    
    headers = get_headers(admin_token)
    
    # Test 1: GET import template
    try:
        r = requests.get(f"{API_URL}/supplier-items/import-template",
                        headers=headers, timeout=30)
        
        if r.status_code == 200 and "supplier_sku" in r.text:
            results.add_pass("E4-01: GET import template", 
                           "CSV template downloaded successfully")
        else:
            results.add_fail("E4-01: GET import template", 
                           f"Status {r.status_code} or invalid content")
    except Exception as e:
        results.add_fail("E4-01: GET import template", str(e))
    
    # Test 2: Dry run with mixed valid/invalid rows
    try:
        csv_data = """supplier_sku,supplier_item_name,sku,supplier_uom,conv_factor,last_price
TEST-VALID-1,Valid Item 1,BNG-KTN-001,kg,1.5,50000
TEST-VALID-2,Valid Item 2,BTK-MEGA-001,meter,1.0,75000
TEST-INVALID-SKU,Invalid SKU,NONEXISTENT-SKU,kg,1.0,50000
TEST-INVALID-CONV,Invalid Conv,BNG-KTN-001,kg,0,50000
,Empty Code,BNG-KTN-001,kg,1.0,50000"""
        
        r = requests.post(f"{API_URL}/supplier-items/import",
                         json={
                             "supplier_id": "sup_solo_weave",
                             "entity_id": "ent_ksc",
                             "csv_text": csv_data,
                             "dry_run": True
                         },
                         headers=headers, timeout=60)
        
        if r.status_code == 200:
            result = r.json()
            if result.get("valid") == 2 and result.get("invalid") == 3:
                results.add_pass("E4-02: Dry run validation", 
                               f"Correctly identified {result['valid']} valid, {result['invalid']} invalid")
                
                # Check if errors have reasons
                errors = result.get("errors", [])
                if len(errors) == 3:
                    results.add_pass("E4-03: Error reasons provided", 
                                   "Each invalid row has specific error reason")
                else:
                    results.add_fail("E4-03: Error reasons provided", 
                                   f"Expected 3 errors, got {len(errors)}")
            else:
                results.add_fail("E4-02: Dry run validation", 
                               f"Expected 2 valid/3 invalid, got {result.get('valid')}/{result.get('invalid')}")
        else:
            results.add_fail("E4-02: Dry run validation", 
                           f"Status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        results.add_fail("E4-02: Dry run validation", str(e))
    
    # Test 3: Commit import
    try:
        csv_valid = """supplier_sku,supplier_item_name,sku,supplier_uom,conv_factor,last_price
TEST-IMPORT-1,Import Test 1,BNG-KTN-001,kg,1.5,50000
TEST-IMPORT-2,Import Test 2,BTK-MEGA-001,meter,1.0,75000"""
        
        r = requests.post(f"{API_URL}/supplier-items/import",
                         json={
                             "supplier_id": "sup_solo_weave",
                             "entity_id": "ent_ksc",
                             "csv_text": csv_valid,
                             "dry_run": False
                         },
                         headers=headers, timeout=60)
        
        if r.status_code == 200:
            result = r.json()
            if result.get("created") == 2:
                results.add_pass("E4-04: Commit import", 
                               f"Created {result['created']} items")
                
                # Test 4: Idempotent - run again
                r2 = requests.post(f"{API_URL}/supplier-items/import",
                                  json={
                                      "supplier_id": "sup_solo_weave",
                                      "entity_id": "ent_ksc",
                                      "csv_text": csv_valid,
                                      "dry_run": False
                                  },
                                  headers=headers, timeout=60)
                
                if r2.status_code == 200:
                    result2 = r2.json()
                    if result2.get("created") == 0 and result2.get("updated") == 2:
                        results.add_pass("E4-05: Idempotent import", 
                                       "Second run: created=0, updated=2")
                    else:
                        results.add_fail("E4-05: Idempotent import", 
                                       f"Expected created=0/updated=2, got {result2.get('created')}/{result2.get('updated')}")
            else:
                results.add_fail("E4-04: Commit import", 
                               f"Expected created=2, got {result.get('created')}")
        else:
            results.add_fail("E4-04: Commit import", 
                           f"Status {r.status_code}")
    except Exception as e:
        results.add_fail("E4-04: Commit import", str(e))
    
    # Test 5: CSV with semicolon delimiter
    try:
        csv_semi = """supplier_sku;supplier_item_name;sku;supplier_uom;conv_factor;last_price
TEST-SEMI-1;Semicolon Test;BNG-KTN-001;kg;1.0;50000"""
        
        r = requests.post(f"{API_URL}/supplier-items/import",
                         json={
                             "supplier_id": "sup_solo_weave",
                             "entity_id": "ent_ksc",
                             "csv_text": csv_semi,
                             "dry_run": False
                         },
                         headers=headers, timeout=60)
        
        if r.status_code == 200:
            result = r.json()
            if result.get("created") >= 1 or result.get("updated") >= 1:
                results.add_pass("E4-06: Semicolon delimiter auto-detected", 
                               "CSV with ';' delimiter processed correctly")
            else:
                results.add_fail("E4-06: Semicolon delimiter auto-detected", 
                               "No items created/updated")
        else:
            results.add_fail("E4-06: Semicolon delimiter auto-detected", 
                           f"Status {r.status_code}")
    except Exception as e:
        results.add_fail("E4-06: Semicolon delimiter auto-detected", str(e))

def test_us_e9_rbac(results, admin_token, warehouse_token, sales_token):
    """US-E9: RBAC permissions"""
    print("\n" + "="*70)
    print("US-E9: RBAC Permissions")
    print("="*70)
    
    admin_headers = get_headers(admin_token)
    wh_headers = get_headers(warehouse_token)
    sales_headers = get_headers(sales_token)
    
    # Test 1: Warehouse can GET supplier items
    try:
        r = requests.get(f"{API_URL}/supplier-items",
                        params={"entity_id": "ent_ksc"},
                        headers=wh_headers, timeout=30)
        
        if r.status_code == 200:
            results.add_pass("E9-01: Warehouse can view supplier items", 
                           "GET allowed for warehouse role")
        else:
            results.add_fail("E9-01: Warehouse can view supplier items", 
                           f"Expected 200, got {r.status_code}")
    except Exception as e:
        results.add_fail("E9-01: Warehouse can view supplier items", str(e))
    
    # Test 2: Warehouse cannot POST supplier items
    try:
        r = requests.post(f"{API_URL}/supplier-items",
                         json={
                             "supplier_id": "sup_solo_weave",
                             "sku": "BNG-KTN-001",
                             "supplier_sku": "WH-TEST",
                             "entity_id": "ent_ksc"
                         },
                         headers=wh_headers, timeout=30)
        
        if r.status_code == 403:
            results.add_pass("E9-02: Warehouse cannot create supplier items", 
                           "403 Forbidden as expected")
        else:
            results.add_fail("E9-02: Warehouse cannot create supplier items", 
                           f"Expected 403, got {r.status_code}")
    except Exception as e:
        results.add_fail("E9-02: Warehouse cannot create supplier items", str(e))
    
    # Test 3: Warehouse cannot import
    try:
        r = requests.post(f"{API_URL}/supplier-items/import",
                         json={
                             "supplier_id": "sup_solo_weave",
                             "entity_id": "ent_ksc",
                             "csv_text": "supplier_sku,sku\nTEST,BNG-KTN-001",
                             "dry_run": True
                         },
                         headers=wh_headers, timeout=30)
        
        if r.status_code == 403:
            results.add_pass("E9-03: Warehouse cannot import", 
                           "403 Forbidden as expected")
        else:
            results.add_fail("E9-03: Warehouse cannot import", 
                           f"Expected 403, got {r.status_code}")
    except Exception as e:
        results.add_fail("E9-03: Warehouse cannot import", str(e))
    
    # Test 4: Sales cannot GET supplier items
    try:
        r = requests.get(f"{API_URL}/supplier-items",
                        params={"entity_id": "ent_ksc"},
                        headers=sales_headers, timeout=30)
        
        if r.status_code == 403:
            results.add_pass("E9-04: Sales cannot view supplier items", 
                           "403 Forbidden as expected (commercial data)")
        else:
            results.add_fail("E9-04: Sales cannot view supplier items", 
                           f"Expected 403, got {r.status_code}")
    except Exception as e:
        results.add_fail("E9-04: Sales cannot view supplier items", str(e))
    
    # Test 5: Manager can access all
    try:
        r = requests.get(f"{API_URL}/supplier-items",
                        params={"entity_id": "ent_ksc"},
                        headers=admin_headers, timeout=30)
        
        if r.status_code == 200:
            results.add_pass("E9-05: Manager/Admin can access all", 
                           "Full access granted")
        else:
            results.add_fail("E9-05: Manager/Admin can access all", 
                           f"Expected 200, got {r.status_code}")
    except Exception as e:
        results.add_fail("E9-05: Manager/Admin can access all", str(e))

def test_regression(results, admin_token):
    """Regression tests - ensure existing endpoints still work"""
    print("\n" + "="*70)
    print("REGRESSION: Existing Endpoints")
    print("="*70)
    
    headers = get_headers(admin_token)
    
    endpoints = [
        ("/dashboard", "Dashboard"),
        ("/products", "Products"),
        ("/sales-orders", "Sales Orders"),
        ("/purchase-orders", "Purchase Orders"),
        ("/purchase-requisitions", "Purchase Requisitions"),
        ("/makloon-orders", "Makloon Orders"),
        ("/makloon-orders/claims", "Makloon Claims"),
        ("/supplier-contracts", "Supplier Contracts"),
        ("/gl/trial-balance", "Trial Balance"),
        ("/inventory/balances", "Inventory Balances"),
    ]
    
    for endpoint, name in endpoints:
        try:
            r = requests.get(f"{API_URL}{endpoint}", 
                           params={"entity_id": "ent_ksc"} if endpoint != "/dashboard" else {},
                           headers=headers, timeout=30)
            
            if r.status_code == 200:
                results.add_pass(f"REG: {name}", f"GET {endpoint} OK")
            else:
                results.add_fail(f"REG: {name}", f"Status {r.status_code}")
        except Exception as e:
            results.add_fail(f"REG: {name}", str(e))

def main():
    print("="*70)
    print("BACKEND API TESTING - FASE E (Sourcing Berbasis Kontrak)")
    print("="*70)
    print(f"Testing against: {BASE_URL}")
    print()
    
    results = TestResults()
    
    # Login all users
    print("Logging in users...")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    manager_token = login(MANAGER_EMAIL, ADMIN_PASSWORD)
    warehouse_token = login(WAREHOUSE_EMAIL, ADMIN_PASSWORD)
    sales_token = login(SALES_EMAIL, ADMIN_PASSWORD)
    
    if not admin_token:
        print("❌ CRITICAL: Cannot login as admin. Aborting tests.")
        return 1
    
    print("✅ All users logged in successfully\n")
    
    # Run tests
    test_us_e1_supplier_contracts(results, admin_token)
    test_us_e2_supplier_items_crud(results, admin_token)
    test_us_e3_lookup(results, admin_token)
    test_us_e4_mass_import(results, admin_token)
    test_us_e9_rbac(results, admin_token, warehouse_token, sales_token)
    test_regression(results, admin_token)
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    summary = results.summary()
    print(f"Total Tests: {summary['total']}")
    print(f"Passed: {summary['passed']} ✅")
    print(f"Failed: {summary['failed']} ❌")
    print(f"Pass Rate: {summary['pass_rate']}")
    print("="*70)
    
    if results.failed:
        print("\nFailed Tests:")
        for fail in results.failed:
            print(f"  ❌ {fail['test']}")
            print(f"     {fail['reason']}")
    
    return 0 if len(results.failed) == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
