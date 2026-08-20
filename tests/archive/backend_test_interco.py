"""Backend API Testing for Sub-fase 1.5: Inter-Company Transfer Flow
Tests the complete inter-company transfer workflow from POS preview to ownership transfer.
"""
import requests
import sys
from datetime import datetime

class InterCompanyTransferTester:
    def __init__(self, base_url="https://po-pdf-sender.preview.emergentagent.com"):
        self.base_url = base_url
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.entities = {}
        self.products = []
        self.transfer_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, token=None, description=""):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        if description:
            print(f"   {description}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=15)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:300]}")
                self.failed_tests.append({
                    "test": name,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "endpoint": endpoint,
                    "response": response.text[:200]
                })

            try:
                return success, response.json() if response.text else {}
            except:
                return success, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append({
                "test": name,
                "error": str(e),
                "endpoint": endpoint
            })
            return False, {}

    def test_login(self, email, password, role):
        """Test login and get token"""
        success, response = self.run_test(
            f"Login as {role}",
            "POST",
            "api/auth/login",
            200,
            data={"email": email, "password": password},
            description=f"Login with {email}"
        )
        if success and 'token' in response:
            self.tokens[role] = response['token']
            print(f"   Token stored for {role}")
            return True
        return False

    def load_entities(self, token):
        """Load business entities"""
        success, response = self.run_test(
            "Load Business Entities",
            "GET",
            "api/entities",
            200,
            token=token,
            description="Get all business entities"
        )
        if success and isinstance(response, list):
            for e in response:
                self.entities[e.get("short_name", "")] = e.get("id", "")
            print(f"   Loaded entities: {list(self.entities.keys())}")
            return True
        return False

    def load_products(self, token):
        """Load products"""
        success, response = self.run_test(
            "Load Products",
            "GET",
            "api/products",
            200,
            token=token,
            description="Get all products"
        )
        if success and isinstance(response, list):
            self.products = response
            print(f"   Loaded {len(self.products)} products")
            return True
        return False

    def find_product(self, name_fragment):
        """Find product by name fragment"""
        for p in self.products:
            if name_fragment.lower() in p.get("name", "").lower():
                return p
        return None

    def get_inventory_status(self, product_id, token):
        """Get inventory status board for a product"""
        success, response = self.run_test(
            "Get Inventory Status",
            "GET",
            f"api/inventory/status-board?product_id={product_id}",
            200,
            token=token,
            description=f"Get inventory status for product {product_id}"
        )
        if success and isinstance(response, list) and len(response) > 0:
            return True, response[0]
        return False, {}

    def preview_allocation(self, entity_id, product_id, quantity, token):
        """Preview allocation for sales order"""
        success, response = self.run_test(
            "Preview Allocation",
            "POST",
            "api/sales-orders/preview-allocation",
            200,
            data={
                "entity_id": entity_id,
                "items": [{"product_id": product_id, "quantity": quantity, "unit": "meter"}]
            },
            token=token,
            description=f"Preview allocation for entity {entity_id}, qty {quantity}"
        )
        if success and "lines" in response and len(response["lines"]) > 0:
            return True, response["lines"][0]
        return False, {}

    def create_inter_company_transfer(self, source_entity_id, dest_entity_id, product_id, quantity, token):
        """Create inter-company transfer"""
        success, response = self.run_test(
            "Create Inter-Company Transfer",
            "POST",
            "api/transfers/inter-company",
            200,
            data={
                "source_entity_id": source_entity_id,
                "dest_entity_id": dest_entity_id,
                "items": [{"product_id": product_id, "quantity": quantity, "unit": "meter"}],
                "notes": "Test inter-company transfer",
                "requested_by": "Test Sales"
            },
            token=token,
            description=f"Create transfer from {source_entity_id} to {dest_entity_id}"
        )
        if success and "id" in response:
            self.transfer_id = response["id"]
            return True, response
        return False, {}

    def list_transfers(self, transfer_kind, token):
        """List transfers by kind"""
        success, response = self.run_test(
            f"List Transfers (kind={transfer_kind})",
            "GET",
            f"api/transfers?transfer_kind={transfer_kind}",
            200,
            token=token,
            description=f"List all {transfer_kind} transfers"
        )
        return success, response if isinstance(response, list) else []

    def approve_transfer(self, transfer_id, token):
        """Approve transfer"""
        success, response = self.run_test(
            "Approve Transfer",
            "POST",
            f"api/transfers/{transfer_id}/approve",
            200,
            data={"approved_by": "Manager Test"},
            token=token,
            description=f"Approve transfer {transfer_id}"
        )
        return success, response

    def reject_transfer(self, transfer_id, token):
        """Reject transfer"""
        success, response = self.run_test(
            "Reject Transfer",
            "POST",
            f"api/transfers/{transfer_id}/reject",
            200,
            data={"rejected_by": "Manager Test", "reason": "Test rejection"},
            token=token,
            description=f"Reject transfer {transfer_id}"
        )
        return success, response

    def cancel_transfer(self, transfer_id, token):
        """Cancel transfer"""
        success, response = self.run_test(
            "Cancel Transfer",
            "DELETE",
            f"api/transfers/{transfer_id}",
            200,
            token=token,
            description=f"Cancel transfer {transfer_id}"
        )
        return success, response

    def test_validation_same_entity(self, token):
        """Test validation: source and dest must be different"""
        ksc = self.entities.get("KSC", "")
        batik = self.find_product("Batik Mega")
        if not batik or not ksc:
            print("⚠️  Skipping validation test - missing data")
            return False
        
        success, response = self.run_test(
            "Validation: Same Source/Dest",
            "POST",
            "api/transfers/inter-company",
            400,
            data={
                "source_entity_id": ksc,
                "dest_entity_id": ksc,
                "items": [{"product_id": batik["id"], "quantity": 10, "unit": "meter"}],
            },
            token=token,
            description="Should fail when source == dest"
        )
        return success

    def test_validation_entity_not_found(self, token):
        """Test validation: entity not found"""
        batik = self.find_product("Batik Mega")
        if not batik:
            print("⚠️  Skipping validation test - missing product")
            return False
        
        success, response = self.run_test(
            "Validation: Entity Not Found",
            "POST",
            "api/transfers/inter-company",
            404,
            data={
                "source_entity_id": "ent_nonexistent",
                "dest_entity_id": self.entities.get("Kanda", ""),
                "items": [{"product_id": batik["id"], "quantity": 10, "unit": "meter"}],
            },
            token=token,
            description="Should fail when entity doesn't exist"
        )
        return success

    def test_validation_insufficient_stock(self, token):
        """Test validation: insufficient stock"""
        ksc = self.entities.get("KSC", "")
        kanda = self.entities.get("Kanda", "")
        batik = self.find_product("Batik Mega")
        if not batik or not ksc or not kanda:
            print("⚠️  Skipping validation test - missing data")
            return False
        
        success, response = self.run_test(
            "Validation: Insufficient Stock",
            "POST",
            "api/transfers/inter-company",
            409,
            data={
                "source_entity_id": ksc,
                "dest_entity_id": kanda,
                "items": [{"product_id": batik["id"], "quantity": 999999, "unit": "meter"}],
            },
            token=token,
            description="Should fail when source doesn't have enough stock"
        )
        return success

    def test_permission_sales_create(self, token):
        """Test permission: sales can create transfer"""
        ksc = self.entities.get("KSC", "")
        kanda = self.entities.get("Kanda", "")
        batik = self.find_product("Batik Mega")
        if not batik or not ksc or not kanda:
            print("⚠️  Skipping permission test - missing data")
            return False
        
        success, response = self.run_test(
            "Permission: Sales Create Transfer",
            "POST",
            "api/transfers/inter-company",
            200,
            data={
                "source_entity_id": ksc,
                "dest_entity_id": kanda,
                "items": [{"product_id": batik["id"], "quantity": 5, "unit": "meter"}],
                "notes": "Sales permission test"
            },
            token=token,
            description="Sales role should be able to create transfer (order:create)"
        )
        if success and "id" in response:
            # Clean up - cancel this test transfer
            self.cancel_transfer(response["id"], self.tokens.get("admin"))
        return success

    def test_permission_sales_cannot_approve(self, transfer_id, token):
        """Test permission: sales cannot approve transfer"""
        success, response = self.run_test(
            "Permission: Sales Cannot Approve",
            "POST",
            f"api/transfers/{transfer_id}/approve",
            403,
            data={"approved_by": "Sales User"},
            token=token,
            description="Sales role should NOT be able to approve (needs transfer:approve)"
        )
        return success

    def run_main_scenario(self):
        """Run the main inter-company transfer scenario"""
        print("\n" + "="*80)
        print("MAIN SCENARIO: KSC → Kanda, Batik Mega Mendung 60 meter")
        print("="*80)

        admin_token = self.tokens.get("admin")
        ksc = self.entities.get("KSC", "")
        kanda = self.entities.get("Kanda", "")
        batik = self.find_product("Batik Mega")
        
        if not batik or not ksc or not kanda:
            print("❌ Cannot run main scenario - missing required data")
            return False

        QTY = 60.0
        product_id = batik["id"]

        # Step 1: Preview allocation for Kanda (should be inter_company)
        print("\n--- Step 1: Preview Allocation (Before Transfer) ---")
        success, preview_before = self.preview_allocation(kanda, product_id, QTY, admin_token)
        if not success:
            return False
        
        print(f"   Primary mode: {preview_before.get('primary_mode')}")
        print(f"   Own available: {preview_before.get('own_available')}")
        print(f"   Own ATP: {preview_before.get('own_atp')}")
        
        if preview_before.get("primary_mode") != "inter_company":
            print(f"   ⚠️  Expected inter_company mode, got {preview_before.get('primary_mode')}")

        # Step 2: Get initial inventory status
        print("\n--- Step 2: Get Initial Inventory Status ---")
        success, status_before = self.get_inventory_status(product_id, admin_token)
        if not success:
            return False
        
        ksc_before = 0.0
        kanda_before = 0.0
        total_before = status_before.get("total_available", 0)
        
        for e in status_before.get("by_entity", []):
            if e.get("entity_id") == ksc:
                ksc_before = e.get("available", 0)
            elif e.get("entity_id") == kanda:
                kanda_before = e.get("available", 0)
        
        print(f"   KSC available: {ksc_before}")
        print(f"   Kanda available: {kanda_before}")
        print(f"   Total available: {total_before}")

        # Step 3: Create inter-company transfer
        print("\n--- Step 3: Create Inter-Company Transfer ---")
        success, transfer = self.create_inter_company_transfer(ksc, kanda, product_id, QTY, admin_token)
        if not success:
            return False
        
        print(f"   Transfer ID: {transfer.get('id')}")
        print(f"   Code: {transfer.get('code')}")
        print(f"   Kind: {transfer.get('transfer_kind')}")
        print(f"   Status: {transfer.get('status')}")
        print(f"   Rolls reserved: {sum(len(i.get('rolls', [])) for i in transfer.get('items', []))}")
        
        if transfer.get("status") != "waiting_approval":
            print(f"   ⚠️  Expected status waiting_approval, got {transfer.get('status')}")
        if transfer.get("transfer_kind") != "inter_entity":
            print(f"   ⚠️  Expected transfer_kind inter_entity, got {transfer.get('transfer_kind')}")

        # Step 4: Check KSC available decreased (reserved)
        print("\n--- Step 4: Check Reservation Applied ---")
        success, status_pending = self.get_inventory_status(product_id, admin_token)
        if not success:
            return False
        
        ksc_pending = 0.0
        for e in status_pending.get("by_entity", []):
            if e.get("entity_id") == ksc:
                ksc_pending = e.get("available", 0)
        
        print(f"   KSC available after request: {ksc_pending}")
        print(f"   Expected: {ksc_before - QTY}")
        
        if abs(ksc_pending - (ksc_before - QTY)) > 0.5:
            print(f"   ⚠️  Reservation not applied correctly")

        # Step 5: Approve transfer (ownership moves)
        print("\n--- Step 5: Approve Transfer (Ownership Transfer) ---")
        success, approved = self.approve_transfer(transfer["id"], admin_token)
        if not success:
            return False
        
        print(f"   Status: {approved.get('status')}")
        print(f"   Ownership moved: {approved.get('ownership_moved')}")
        
        if approved.get("status") != "completed":
            print(f"   ⚠️  Expected status completed, got {approved.get('status')}")

        # Step 6: Check final inventory status
        print("\n--- Step 6: Check Final Inventory Status ---")
        success, status_after = self.get_inventory_status(product_id, admin_token)
        if not success:
            return False
        
        ksc_after = 0.0
        kanda_after = 0.0
        total_after = status_after.get("total_available", 0)
        
        for e in status_after.get("by_entity", []):
            if e.get("entity_id") == ksc:
                ksc_after = e.get("available", 0)
            elif e.get("entity_id") == kanda:
                kanda_after = e.get("available", 0)
        
        print(f"   KSC available: {ksc_after} (expected: {ksc_before - QTY})")
        print(f"   Kanda available: {kanda_after} (expected: {kanda_before + QTY})")
        print(f"   Total available: {total_after} (expected: {total_before})")
        
        # Verify ownership transfer
        if abs(kanda_after - (kanda_before + QTY)) > 0.5:
            print(f"   ❌ Kanda stock not increased correctly")
            self.failed_tests.append({"test": "Main Scenario - Kanda Stock", "issue": "Stock not increased"})
        else:
            print(f"   ✅ Kanda stock increased correctly")
            self.tests_passed += 1
        
        if abs(ksc_after - (ksc_before - QTY)) > 0.5:
            print(f"   ❌ KSC stock not decreased correctly")
            self.failed_tests.append({"test": "Main Scenario - KSC Stock", "issue": "Stock not decreased"})
        else:
            print(f"   ✅ KSC stock decreased correctly")
            self.tests_passed += 1

        # Step 7: Preview allocation again (should be from_stock now)
        print("\n--- Step 7: Preview Allocation (After Transfer) ---")
        success, preview_after = self.preview_allocation(kanda, product_id, QTY, admin_token)
        if success:
            print(f"   Primary mode: {preview_after.get('primary_mode')}")
            if preview_after.get("primary_mode") != "from_stock":
                print(f"   ⚠️  Expected from_stock mode, got {preview_after.get('primary_mode')}")
            else:
                print(f"   ✅ Mode changed to from_stock")
                self.tests_passed += 1

        # Step 8: Check conservation
        print("\n--- Step 8: Check Stock Conservation ---")
        if abs(total_after - total_before) > 0.5:
            print(f"   ❌ Total stock changed (before: {total_before}, after: {total_after})")
            self.failed_tests.append({"test": "Main Scenario - Conservation", "issue": "Total stock changed"})
        else:
            print(f"   ✅ Total stock conserved")
            self.tests_passed += 1

        self.tests_run += 4  # Count the verification steps
        return True

    def test_reject_flow(self):
        """Test reject flow"""
        print("\n" + "="*80)
        print("TEST: Reject Flow")
        print("="*80)

        admin_token = self.tokens.get("admin")
        ksc = self.entities.get("KSC", "")
        kanda = self.entities.get("Kanda", "")
        batik = self.find_product("Batik Mega")
        
        if not batik or not ksc or not kanda:
            print("❌ Cannot run reject test - missing required data")
            return False

        product_id = batik["id"]
        QTY = 20.0

        # Get initial status
        success, status_before = self.get_inventory_status(product_id, admin_token)
        if not success:
            return False
        
        ksc_before = 0.0
        for e in status_before.get("by_entity", []):
            if e.get("entity_id") == ksc:
                ksc_before = e.get("available", 0)

        # Create transfer
        success, transfer = self.create_inter_company_transfer(ksc, kanda, product_id, QTY, admin_token)
        if not success:
            return False
        
        print(f"   Transfer created: {transfer.get('code')}")

        # Check reservation
        success, status_pending = self.get_inventory_status(product_id, admin_token)
        if success:
            ksc_pending = 0.0
            for e in status_pending.get("by_entity", []):
                if e.get("entity_id") == ksc:
                    ksc_pending = e.get("available", 0)
            print(f"   KSC available after request: {ksc_pending} (reserved {QTY})")

        # Reject transfer
        success, rejected = self.reject_transfer(transfer["id"], admin_token)
        if not success:
            return False
        
        print(f"   Transfer rejected: {rejected.get('status')}")

        # Check reservation released
        success, status_after = self.get_inventory_status(product_id, admin_token)
        if success:
            ksc_after = 0.0
            for e in status_after.get("by_entity", []):
                if e.get("entity_id") == ksc:
                    ksc_after = e.get("available", 0)
            print(f"   KSC available after reject: {ksc_after}")
            
            if abs(ksc_after - ksc_before) > 0.5:
                print(f"   ❌ Reservation not released (expected {ksc_before}, got {ksc_after})")
                self.failed_tests.append({"test": "Reject Flow", "issue": "Reservation not released"})
            else:
                print(f"   ✅ Reservation released correctly")
                self.tests_passed += 1
        
        self.tests_run += 1
        return True

    def test_cancel_flow(self):
        """Test cancel flow"""
        print("\n" + "="*80)
        print("TEST: Cancel Flow")
        print("="*80)

        admin_token = self.tokens.get("admin")
        ksc = self.entities.get("KSC", "")
        kanda = self.entities.get("Kanda", "")
        batik = self.find_product("Batik Mega")
        
        if not batik or not ksc or not kanda:
            print("❌ Cannot run cancel test - missing required data")
            return False

        product_id = batik["id"]
        QTY = 15.0

        # Get initial status
        success, status_before = self.get_inventory_status(product_id, admin_token)
        if not success:
            return False
        
        ksc_before = 0.0
        for e in status_before.get("by_entity", []):
            if e.get("entity_id") == ksc:
                ksc_before = e.get("available", 0)

        # Create transfer
        success, transfer = self.create_inter_company_transfer(ksc, kanda, product_id, QTY, admin_token)
        if not success:
            return False
        
        print(f"   Transfer created: {transfer.get('code')}")

        # Cancel transfer
        success, cancelled = self.cancel_transfer(transfer["id"], admin_token)
        if not success:
            return False
        
        print(f"   Transfer cancelled: {cancelled.get('status')}")

        # Check reservation released
        success, status_after = self.get_inventory_status(product_id, admin_token)
        if success:
            ksc_after = 0.0
            for e in status_after.get("by_entity", []):
                if e.get("entity_id") == ksc:
                    ksc_after = e.get("available", 0)
            print(f"   KSC available after cancel: {ksc_after}")
            
            if abs(ksc_after - ksc_before) > 0.5:
                print(f"   ❌ Reservation not released (expected {ksc_before}, got {ksc_after})")
                self.failed_tests.append({"test": "Cancel Flow", "issue": "Reservation not released"})
            else:
                print(f"   ✅ Reservation released correctly")
                self.tests_passed += 1
        
        self.tests_run += 1
        return True

def main():
    print("="*80)
    print("BACKEND API TESTING: Sub-fase 1.5 Inter-Company Transfer Flow")
    print("="*80)
    
    tester = InterCompanyTransferTester()
    
    # Login
    print("\n--- Authentication ---")
    if not tester.test_login("admin@kainnusantara.id", "demo12345", "admin"):
        print("❌ Admin login failed, stopping tests")
        return 1
    
    if not tester.test_login("sales@kainnusantara.id", "demo12345", "sales"):
        print("⚠️  Sales login failed, some permission tests will be skipped")
    
    if not tester.test_login("manager@kainnusantara.id", "demo12345", "manager"):
        print("⚠️  Manager login failed, some permission tests will be skipped")
    
    # Load data
    print("\n--- Loading Reference Data ---")
    admin_token = tester.tokens.get("admin")
    if not tester.load_entities(admin_token):
        print("❌ Failed to load entities, stopping tests")
        return 1
    
    if not tester.load_products(admin_token):
        print("❌ Failed to load products, stopping tests")
        return 1
    
    # Validation tests
    print("\n" + "="*80)
    print("VALIDATION TESTS")
    print("="*80)
    tester.test_validation_same_entity(admin_token)
    tester.test_validation_entity_not_found(admin_token)
    tester.test_validation_insufficient_stock(admin_token)
    
    # Permission tests
    print("\n" + "="*80)
    print("PERMISSION TESTS")
    print("="*80)
    sales_token = tester.tokens.get("sales")
    if sales_token:
        tester.test_permission_sales_create(sales_token)
    
    # Main scenario
    tester.run_main_scenario()
    
    # Test reject flow
    tester.test_reject_flow()
    
    # Test cancel flow
    tester.test_cancel_flow()
    
    # List transfers
    print("\n" + "="*80)
    print("LIST TRANSFERS")
    print("="*80)
    success, transfers = tester.list_transfers("inter_entity", admin_token)
    if success:
        print(f"   Found {len(transfers)} inter-company transfers")
        for t in transfers[:3]:
            print(f"   - {t.get('code')}: {t.get('source_entity_name')} → {t.get('dest_entity_name')} ({t.get('status')})")
    
    # Permission test: sales cannot approve
    if sales_token and tester.transfer_id:
        print("\n" + "="*80)
        print("PERMISSION TEST: Sales Cannot Approve")
        print("="*80)
        # Create a new transfer for this test
        ksc = tester.entities.get("KSC", "")
        kanda = tester.entities.get("Kanda", "")
        batik = tester.find_product("Batik Mega")
        if batik and ksc and kanda:
            success, transfer = tester.create_inter_company_transfer(ksc, kanda, batik["id"], 5, admin_token)
            if success:
                tester.test_permission_sales_cannot_approve(transfer["id"], sales_token)
                # Clean up
                tester.cancel_transfer(transfer["id"], admin_token)
    
    # Print results
    print("\n" + "="*80)
    print("TEST RESULTS")
    print("="*80)
    print(f"Tests run: {tester.tests_run}")
    print(f"Tests passed: {tester.tests_passed}")
    print(f"Tests failed: {len(tester.failed_tests)}")
    
    if tester.failed_tests:
        print("\n❌ Failed tests:")
        for fail in tester.failed_tests:
            print(f"   - {fail.get('test')}: {fail.get('error', fail.get('issue', 'Status mismatch'))}")
    
    success_rate = (tester.tests_passed / tester.tests_run * 100) if tester.tests_run > 0 else 0
    print(f"\nSuccess rate: {success_rate:.1f}%")
    
    if success_rate >= 80:
        print("\n✅ BACKEND TESTS PASSED (≥80%)")
        return 0
    else:
        print("\n❌ BACKEND TESTS FAILED (<80%)")
        return 1

if __name__ == "__main__":
    sys.exit(main())
