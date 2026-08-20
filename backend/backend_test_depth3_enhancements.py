"""Backend API Testing for Depth #3 Enhancements
Tests: 
1. Reorder suggestions with lead-time/ETA integration
2. Price-deviation approval for PO
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com"

class Depth3EnhancementsTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.supplier_id = None
        self.product_id = None
        self.warehouse_id = None
        self.pr_id = None
        self.po_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None, description=""):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 {name}")
        if description:
            print(f"   {description}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=15)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ PASS - Status: {response.status_code}")
            else:
                print(f"❌ FAIL - Expected {expected_status}, got {response.status_code}")
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
            except Exception:
                return success, {}

        except Exception as e:
            print(f"❌ FAIL - Error: {str(e)}")
            self.failed_tests.append({"test": name, "error": str(e), "endpoint": endpoint})
            return False, {}

    def test_login(self):
        """Test login as admin"""
        success, response = self.run_test(
            "Login as admin",
            "POST",
            "api/auth/login",
            200,
            data={"email": "admin@kainnusantara.id", "password": "demo12345"},
            description="Login to get auth token"
        )
        if success and 'token' in response:
            self.token = response['token']
            print(f"   Token obtained")
            return True
        return False

    def test_get_effective_settings(self):
        """Test GET /api/settings/effective for price_deviation_approval_percent"""
        success, response = self.run_test(
            "GET /api/settings/effective",
            "GET",
            "api/settings/effective",
            200,
            description="Should return purchasing.price_deviation_approval_percent"
        )
        
        if success:
            purchasing = response.get('purchasing', {})
            threshold = purchasing.get('price_deviation_approval_percent')
            
            print(f"   ✓ Purchasing settings: {purchasing}")
            print(f"   ✓ Price deviation threshold: {threshold}%")
            
            if threshold is not None:
                print(f"   ✅ price_deviation_approval_percent present (default: 10.0)")
                return True
        return False

    def test_reorder_suggestions_with_lead_time(self):
        """Test GET /api/purchase-requisitions/reorder-suggestions returns lead_time_days and expected_arrival_date"""
        success, response = self.run_test(
            "GET /api/purchase-requisitions/reorder-suggestions",
            "GET",
            "api/purchase-requisitions/reorder-suggestions",
            200,
            description="Should return items with lead_time_days, expected_arrival_date, preferred_supplier_id"
        )
        
        if success:
            items = response.get('items', [])
            count = response.get('count', 0)
            
            print(f"   ✓ Reorder suggestions count: {count}")
            
            if len(items) > 0:
                item = items[0]
                print(f"   ✓ Sample product: {item.get('sku')} - {item.get('product_name')}")
                print(f"   ✓ Available: {item.get('available')}, On-order: {item.get('on_order')}")
                print(f"   ✓ Projected: {item.get('projected')}, Reorder point: {item.get('reorder_point')}")
                print(f"   ✓ Suggested qty: {item.get('suggested_qty')}")
                print(f"   ✓ Est price: {item.get('est_price')} (source: {item.get('price_source')})")
                print(f"   ✓ Lead time: {item.get('lead_time_days')} days")
                print(f"   ✓ Expected arrival: {item.get('expected_arrival_date')}")
                print(f"   ✓ Preferred supplier: {item.get('preferred_supplier_name')} (ID: {item.get('preferred_supplier_id')})")
                
                # Store for later tests
                self.product_id = item.get('product_id')
                self.supplier_id = item.get('preferred_supplier_id')
                
                # Check required fields
                has_lead_time = 'lead_time_days' in item
                has_eta = 'expected_arrival_date' in item
                has_price_source = 'price_source' in item
                has_supplier_id = 'preferred_supplier_id' in item
                
                if has_lead_time and has_eta and has_price_source and has_supplier_id:
                    print(f"   ✅ All required fields present (lead_time_days, expected_arrival_date, price_source, preferred_supplier_id)")
                    return True
                else:
                    print(f"   ❌ Missing fields - lead_time: {has_lead_time}, eta: {has_eta}, price_source: {has_price_source}, supplier_id: {has_supplier_id}")
            else:
                print(f"   ⚠️  No reorder suggestions (all products above reorder point)")
                # This is OK - not a failure
                return True
        return False

    def test_create_pr_from_reorder_with_needed_by_date(self):
        """Test POST /api/purchase-requisitions with needed_by_date and preferred_supplier_id"""
        # Get warehouses first
        _, warehouses = self.run_test("Get warehouses", "GET", "api/warehouses", 200)
        if not warehouses or not isinstance(warehouses, list) or len(warehouses) == 0:
            print("⚠️  No warehouses found")
            return False
        
        self.warehouse_id = warehouses[0].get('id')
        
        # Get reorder suggestions to get a product
        _, reorder_data = self.run_test("Get reorder suggestions", "GET", "api/purchase-requisitions/reorder-suggestions", 200)
        items = reorder_data.get('items', [])
        
        if len(items) == 0:
            print("⚠️  No reorder suggestions available, skipping PR creation test")
            return True  # Not a failure
        
        item = items[0]
        
        success, response = self.run_test(
            "POST /api/purchase-requisitions (from reorder with needed_by_date)",
            "POST",
            "api/purchase-requisitions",
            200,
            data={
                "items": [
                    {
                        "product_id": item.get('product_id'),
                        "quantity": item.get('suggested_qty', 10),
                        "unit": item.get('unit', 'meter'),
                        "est_price": item.get('est_price', 0)
                    }
                ],
                "warehouse_id": self.warehouse_id,
                "entity_id": "",
                "needed_by_date": item.get('expected_arrival_date', ''),
                "preferred_supplier_id": item.get('preferred_supplier_id', ''),
                "source": "reorder",
                "reason": "Test reorder with ETA",
                "submit_now": True
            },
            description="Should create PR with needed_by_date (ETA) and preferred_supplier_id"
        )
        
        if success:
            pr_number = response.get('number')
            needed_by = response.get('needed_by_date')
            supplier_id = response.get('preferred_supplier_id')
            supplier_name = response.get('preferred_supplier_name')
            
            print(f"   ✓ PR created: {pr_number}")
            print(f"   ✓ Needed by date: {needed_by}")
            print(f"   ✓ Preferred supplier: {supplier_name} (ID: {supplier_id})")
            
            self.pr_id = response.get('id')
            
            if needed_by and supplier_id:
                print(f"   ✅ PR created with needed_by_date and preferred_supplier_id")
                return True
        return False

    def test_po_price_deviation_approval(self):
        """Test POST /api/purchase-orders with price >10% above price-list triggers approval"""
        # Get supplier with price-list
        _, suppliers = self.run_test("Get suppliers", "GET", "api/suppliers", 200)
        if not suppliers or not isinstance(suppliers, list):
            print("⚠️  No suppliers found")
            return False
        
        # Find Cirebon Craft or use first supplier
        supplier = next((s for s in suppliers if 'Cirebon' in s.get('name', '')), suppliers[0])
        supplier_id = supplier.get('id')
        
        # Get price-list for this supplier
        _, price_list = self.run_test("Get supplier price-list", "GET", f"api/suppliers/{supplier_id}/price-list", 200)
        
        if not price_list or not isinstance(price_list, list) or len(price_list) == 0:
            print("⚠️  No price-list entries for supplier")
            return False
        
        entry = price_list[0]
        product_id = entry.get('product_id')
        ref_price = entry.get('price', 100000)
        unit = entry.get('unit', 'meter')
        
        # Calculate price 25% above reference (should trigger approval)
        inflated_price = ref_price * 1.25
        
        print(f"   ✓ Reference price: {ref_price}")
        print(f"   ✓ Inflated price (25% above): {inflated_price}")
        
        # Get warehouse
        _, warehouses = self.run_test("Get warehouses", "GET", "api/warehouses", 200)
        if not warehouses or not isinstance(warehouses, list):
            print("⚠️  No warehouses found")
            return False
        
        warehouse_id = warehouses[0].get('id')
        
        success, response = self.run_test(
            "POST /api/purchase-orders (price 25% above price-list)",
            "POST",
            "api/purchase-orders",
            200,
            data={
                "supplier_id": supplier_id,
                "supplier_name": "",
                "supplier_contact": "",
                "warehouse_id": warehouse_id,
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 100,
                        "unit": unit,
                        "price": inflated_price
                    }
                ],
                "expected_delivery_date": "2025-09-15",
                "notes": "Test PO with price deviation",
                "created_by": "Test Admin",
                "entity_id": ""
            },
            description="Should create PO with status=waiting_approval and price_deviation.flagged=true"
        )
        
        if success:
            po_number = response.get('po_number')
            status = response.get('status')
            approval_required = response.get('approval_required')
            approval_reason = response.get('approval_reason')
            price_deviation = response.get('price_deviation', {})
            
            print(f"   ✓ PO created: {po_number}")
            print(f"   ✓ Status: {status}")
            print(f"   ✓ Approval required: {approval_required}")
            print(f"   ✓ Approval reason: {approval_reason}")
            print(f"   ✓ Price deviation flagged: {price_deviation.get('flagged')}")
            print(f"   ✓ Max deviation: {price_deviation.get('max_deviation_pct')}%")
            print(f"   ✓ Threshold: {price_deviation.get('threshold_pct')}%")
            print(f"   ✓ Flagged items: {len(price_deviation.get('items', []))} items")
            
            self.po_id = response.get('id')
            
            # Check if price deviation triggered approval
            is_flagged = price_deviation.get('flagged') == True
            is_waiting_approval = status == 'waiting_approval'
            has_price_deviation_reason = 'price_deviation' in (approval_reason or '')
            
            if is_flagged and is_waiting_approval and has_price_deviation_reason:
                print(f"   ✅ Price deviation approval working correctly")
                return True
            else:
                print(f"   ❌ Price deviation not working - flagged: {is_flagged}, status: {status}, reason: {approval_reason}")
        return False

    def test_po_no_price_deviation(self):
        """Test POST /api/purchase-orders with price at price-list does NOT trigger deviation"""
        # Get supplier with price-list
        _, suppliers = self.run_test("Get suppliers", "GET", "api/suppliers", 200)
        if not suppliers or not isinstance(suppliers, list):
            print("⚠️  No suppliers found")
            return False
        
        supplier = next((s for s in suppliers if 'Cirebon' in s.get('name', '')), suppliers[0])
        supplier_id = supplier.get('id')
        
        # Get price-list
        _, price_list = self.run_test("Get supplier price-list", "GET", f"api/suppliers/{supplier_id}/price-list", 200)
        
        if not price_list or not isinstance(price_list, list) or len(price_list) == 0:
            print("⚠️  No price-list entries")
            return False
        
        entry = price_list[0]
        product_id = entry.get('product_id')
        ref_price = entry.get('price', 100000)
        unit = entry.get('unit', 'meter')
        
        print(f"   ✓ Using exact price-list price: {ref_price}")
        
        # Get warehouse
        _, warehouses = self.run_test("Get warehouses", "GET", "api/warehouses", 200)
        warehouse_id = warehouses[0].get('id') if warehouses else None
        
        success, response = self.run_test(
            "POST /api/purchase-orders (price at price-list)",
            "POST",
            "api/purchase-orders",
            200,
            data={
                "supplier_id": supplier_id,
                "supplier_name": "",
                "supplier_contact": "",
                "warehouse_id": warehouse_id,
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 100,
                        "unit": unit,
                        "price": ref_price  # Exact price-list price
                    }
                ],
                "expected_delivery_date": "2025-09-15",
                "notes": "Test PO without price deviation",
                "created_by": "Test Admin",
                "entity_id": ""
            },
            description="Should create PO without price_deviation flag (price at price-list)"
        )
        
        if success:
            po_number = response.get('po_number')
            status = response.get('status')
            price_deviation = response.get('price_deviation', {})
            approval_reason = response.get('approval_reason', '')
            
            print(f"   ✓ PO created: {po_number}")
            print(f"   ✓ Status: {status}")
            print(f"   ✓ Price deviation flagged: {price_deviation.get('flagged')}")
            print(f"   ✓ Approval reason: {approval_reason}")
            
            # Check that price deviation is NOT flagged
            is_not_flagged = price_deviation.get('flagged') == False
            no_price_deviation_reason = 'price_deviation' not in approval_reason
            
            if is_not_flagged:
                print(f"   ✅ Price deviation NOT triggered (correct)")
                return True
            else:
                print(f"   ❌ Price deviation incorrectly flagged")
        return False

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*80)
        print("📊 DEPTH #3 ENHANCEMENTS TEST SUMMARY")
        print("="*80)
        print(f"Total tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Tests failed: {len(self.failed_tests)}")
        
        if self.tests_run > 0:
            success_rate = (self.tests_passed / self.tests_run * 100)
            print(f"Success rate: {success_rate:.1f}%")
        
        if self.failed_tests:
            print("\n❌ Failed Tests:")
            for ft in self.failed_tests:
                print(f"  - {ft.get('test')}")
                if 'error' in ft:
                    print(f"    Error: {ft.get('error')}")
                if 'response' in ft:
                    print(f"    Response: {ft.get('response')}")
        
        print("="*80)
        return len(self.failed_tests) == 0

def main():
    tester = Depth3EnhancementsTester()
    
    print("🚀 Starting Depth #3 Enhancements Backend Tests")
    print("="*80)
    
    # Login
    if not tester.test_login():
        print("❌ Login failed, stopping tests")
        return 1
    
    # Test settings
    print("\n\n⚙️  TESTING SETTINGS")
    print("="*80)
    tester.test_get_effective_settings()
    
    # Test reorder with lead-time/ETA
    print("\n\n📦 TESTING REORDER SUGGESTIONS WITH LEAD-TIME/ETA")
    print("="*80)
    tester.test_reorder_suggestions_with_lead_time()
    tester.test_create_pr_from_reorder_with_needed_by_date()
    
    # Test price-deviation approval
    print("\n\n💰 TESTING PRICE-DEVIATION APPROVAL")
    print("="*80)
    tester.test_po_price_deviation_approval()
    tester.test_po_no_price_deviation()
    
    # Print summary
    success = tester.print_summary()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
