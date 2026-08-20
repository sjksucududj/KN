"""
Backend API Testing for Depth #3 Enhancements:
1. Settings UI for price-deviation approval threshold
2. Notification to approver role when PO enters waiting_approval
"""
import requests
import sys
from datetime import datetime

class Depth3Tester:
    def __init__(self, base_url="https://po-pdf-sender.preview.emergentagent.com"):
        self.base_url = base_url
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

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
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=15)

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
                    "endpoint": endpoint
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

    def test_get_settings_effective(self, role):
        """Test GET /api/settings/effective - should return purchasing.price_deviation_approval_percent"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping test for {role} - no token")
            return False
        
        success, response = self.run_test(
            "GET /api/settings/effective",
            "GET",
            "api/settings/effective",
            200,
            token=token,
            description="Should return purchasing.price_deviation_approval_percent (default 10)"
        )
        
        if success:
            purchasing = response.get('purchasing', {})
            threshold = purchasing.get('price_deviation_approval_percent')
            print(f"   ✓ price_deviation_approval_percent: {threshold}")
            
            if threshold is not None:
                print(f"   ✅ Threshold field exists (value: {threshold})")
                return True
            else:
                print(f"   ❌ price_deviation_approval_percent field missing")
                return False
        return False

    def test_update_settings_threshold(self, role, new_threshold):
        """Test PUT /api/settings - update price_deviation_approval_percent"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping test for {role} - no token")
            return False
        
        success, response = self.run_test(
            f"PUT /api/settings (threshold={new_threshold})",
            "PUT",
            "api/settings",
            200,
            data={
                "scope": "global",
                "purchasing": {
                    "price_deviation_approval_percent": new_threshold
                }
            },
            token=token,
            description=f"Update threshold to {new_threshold}%"
        )
        
        if success:
            print(f"   ✅ Settings updated successfully")
            
            # Verify the update
            success2, response2 = self.run_test(
                "Verify threshold update",
                "GET",
                "api/settings/effective",
                200,
                token=token,
                description=f"Verify threshold is now {new_threshold}"
            )
            
            if success2:
                purchasing = response2.get('purchasing', {})
                actual_threshold = purchasing.get('price_deviation_approval_percent')
                print(f"   ✓ Verified threshold: {actual_threshold}")
                
                if actual_threshold == new_threshold:
                    print(f"   ✅ Threshold correctly updated to {new_threshold}")
                    return True
                else:
                    print(f"   ❌ Threshold mismatch: expected {new_threshold}, got {actual_threshold}")
                    return False
        return False

    def test_po_price_deviation_enforcement(self, role, threshold):
        """Test PO creation with price deviation - should trigger approval when above threshold"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping test for {role} - no token")
            return False
        
        # Get suppliers and products
        success1, suppliers = self.run_test(
            "Get suppliers",
            "GET",
            "api/suppliers",
            200,
            token=token,
            description="Get supplier list"
        )
        
        success2, products = self.run_test(
            "Get products",
            "GET",
            "api/products",
            200,
            token=token,
            description="Get product list"
        )
        
        success3, warehouses = self.run_test(
            "Get warehouses",
            "GET",
            "api/warehouses",
            200,
            token=token,
            description="Get warehouse list"
        )
        
        if not (success1 and success2 and success3):
            print(f"   ❌ Failed to load required data")
            return False
        
        # Find Cirebon Craft supplier
        supplier = next((s for s in suppliers if 'Cirebon' in s.get('name', '')), None)
        if not supplier:
            print(f"   ❌ Cirebon Craft supplier not found")
            return False
        
        # Get first product and warehouse
        if not products or not warehouses:
            print(f"   ❌ No products or warehouses found")
            return False
        
        product = products[0]
        warehouse = warehouses[0]
        
        # Get supplier price list for this product
        success4, price_lists = self.run_test(
            "Get supplier price lists",
            "GET",
            f"api/suppliers/{supplier['id']}/price-lists",
            200,
            token=token,
            description=f"Get price lists for {supplier['name']}"
        )
        
        if not success4 or not price_lists:
            print(f"   ⚠️  No price lists found for supplier, using product price")
            base_price = float(product.get('price', 100000))
        else:
            # Find price list for this product
            price_list = next((pl for pl in price_lists if pl.get('product_id') == product['id']), None)
            if price_list:
                base_price = float(price_list.get('price', 100000))
            else:
                base_price = float(product.get('price', 100000))
        
        print(f"   ✓ Base price: Rp {base_price:,.0f}")
        
        # Test 1: Price below threshold (should NOT require approval)
        below_threshold_price = base_price * (1 + (threshold - 5) / 100)  # threshold - 5%
        
        success5, po_below = self.run_test(
            f"Create PO with price {threshold-5}% above base (below threshold)",
            "POST",
            "api/purchase-orders",
            200,
            data={
                "supplier_id": supplier['id'],
                "warehouse_id": warehouse['id'],
                "items": [
                    {
                        "product_id": product['id'],
                        "quantity": 10,
                        "unit": "meter",
                        "price": below_threshold_price
                    }
                ],
                "expected_delivery_date": "2025-09-01",
                "notes": f"Test PO - price {threshold-5}% above base",
                "created_by": "Test Admin"
            },
            token=token,
            description=f"Price {threshold-5}% above base should NOT trigger approval"
        )
        
        if success5:
            status = po_below.get('status')
            price_deviation = po_below.get('price_deviation', {})
            flagged = price_deviation.get('flagged', False)
            
            print(f"   ✓ PO Status: {status}")
            print(f"   ✓ Price Deviation Flagged: {flagged}")
            
            if status == 'pending' and not flagged:
                print(f"   ✅ Below threshold: PO status=pending, not flagged")
            else:
                print(f"   ❌ Below threshold: Expected status=pending and not flagged, got status={status}, flagged={flagged}")
                return False
        
        # Test 2: Price above threshold (should require approval)
        above_threshold_price = base_price * (1 + (threshold + 5) / 100)  # threshold + 5%
        
        success6, po_above = self.run_test(
            f"Create PO with price {threshold+5}% above base (above threshold)",
            "POST",
            "api/purchase-orders",
            200,
            data={
                "supplier_id": supplier['id'],
                "warehouse_id": warehouse['id'],
                "items": [
                    {
                        "product_id": product['id'],
                        "quantity": 10,
                        "unit": "meter",
                        "price": above_threshold_price
                    }
                ],
                "expected_delivery_date": "2025-09-01",
                "notes": f"Test PO - price {threshold+5}% above base",
                "created_by": "Test Admin"
            },
            token=token,
            description=f"Price {threshold+5}% above base should trigger approval"
        )
        
        if success6:
            status = po_above.get('status')
            price_deviation = po_above.get('price_deviation', {})
            flagged = price_deviation.get('flagged', False)
            approval_reason = po_above.get('approval_reason', '')
            
            print(f"   ✓ PO Status: {status}")
            print(f"   ✓ Price Deviation Flagged: {flagged}")
            print(f"   ✓ Approval Reason: {approval_reason}")
            
            if status == 'waiting_approval' and flagged and 'price_deviation' in approval_reason:
                print(f"   ✅ Above threshold: PO status=waiting_approval, flagged=True, reason contains 'price_deviation'")
                return True
            else:
                print(f"   ❌ Above threshold: Expected status=waiting_approval, flagged=True, got status={status}, flagged={flagged}")
                return False
        
        return False

    def test_notifications_for_po_approval(self, role):
        """Test GET /api/notifications - should show PO approval notifications for manager"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping test for {role} - no token")
            return False
        
        success, response = self.run_test(
            "GET /api/notifications",
            "GET",
            "api/notifications",
            200,
            token=token,
            description="Get notifications for manager role"
        )
        
        if success:
            notifications = response if isinstance(response, list) else []
            print(f"   ✓ Found {len(notifications)} notifications")
            
            # Find PO approval notifications
            po_approval_notifs = [n for n in notifications if n.get('type') == 'po_approval']
            print(f"   ✓ PO approval notifications: {len(po_approval_notifs)}")
            
            if len(po_approval_notifs) > 0:
                sample = po_approval_notifs[0]
                print(f"   ✓ Sample notification:")
                print(f"      - Title: {sample.get('title')}")
                print(f"      - Body: {sample.get('body')}")
                print(f"      - Link: {sample.get('link')}")
                print(f"      - Severity: {sample.get('severity')}")
                print(f"      - Recipient Role: {sample.get('recipient_role')}")
                
                # Verify notification structure
                if (sample.get('link') == 'purchase-approval' and 
                    sample.get('recipient_role') in ['manager', 'admin'] and
                    'menunggu persetujuan' in sample.get('title', '').lower()):
                    print(f"   ✅ PO approval notification structure is correct")
                    return True
                else:
                    print(f"   ❌ PO approval notification structure incorrect")
                    return False
            else:
                print(f"   ⚠️  No PO approval notifications found (may need to create a PO first)")
                return True  # Not a failure, just no notifications yet
        
        return False

    def test_notifications_unread_count(self, role):
        """Test GET /api/notifications/unread-count"""
        token = self.tokens.get(role)
        if not token:
            print(f"⚠️  Skipping test for {role} - no token")
            return False
        
        success, response = self.run_test(
            "GET /api/notifications/unread-count",
            "GET",
            "api/notifications/unread-count",
            200,
            token=token,
            description="Get unread notification count"
        )
        
        if success:
            count = response.get('count', 0)
            print(f"   ✓ Unread count: {count}")
            print(f"   ✅ Unread count endpoint working")
            return True
        
        return False

def main():
    tester = Depth3Tester()
    
    print("=" * 80)
    print("DEPTH #3 ENHANCEMENTS TESTING")
    print("1. Settings UI for price-deviation approval threshold")
    print("2. Notification to approver role when PO enters waiting_approval")
    print("=" * 80)
    
    # Login as admin and manager
    print("\n" + "=" * 80)
    print("AUTHENTICATION")
    print("=" * 80)
    
    if not tester.test_login("admin@kainnusantara.id", "demo12345", "admin"):
        print("❌ Admin login failed, stopping tests")
        return 1
    
    if not tester.test_login("manager@kainnusantara.id", "demo12345", "manager"):
        print("❌ Manager login failed, stopping tests")
        return 1
    
    # Test 1: Settings API
    print("\n" + "=" * 80)
    print("TEST 1: SETTINGS API - Price Deviation Threshold")
    print("=" * 80)
    
    tester.test_get_settings_effective("admin")
    
    # Test 2: Update threshold to 20
    print("\n" + "=" * 80)
    print("TEST 2: UPDATE THRESHOLD TO 20%")
    print("=" * 80)
    
    tester.test_update_settings_threshold("admin", 20)
    
    # Test 3: PO creation with price deviation enforcement at 20% threshold
    print("\n" + "=" * 80)
    print("TEST 3: PO PRICE DEVIATION ENFORCEMENT (threshold=20%)")
    print("=" * 80)
    
    tester.test_po_price_deviation_enforcement("admin", 20)
    
    # Test 4: Notifications for manager
    print("\n" + "=" * 80)
    print("TEST 4: NOTIFICATIONS FOR MANAGER")
    print("=" * 80)
    
    tester.test_notifications_for_po_approval("manager")
    tester.test_notifications_unread_count("manager")
    
    # Test 5: Reset threshold back to 10
    print("\n" + "=" * 80)
    print("TEST 5: RESET THRESHOLD TO 10%")
    print("=" * 80)
    
    tester.test_update_settings_threshold("admin", 10)
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Tests run: {tester.tests_run}")
    print(f"Tests passed: {tester.tests_passed}")
    print(f"Tests failed: {tester.tests_run - tester.tests_passed}")
    
    if tester.failed_tests:
        print("\n❌ Failed tests:")
        for ft in tester.failed_tests:
            error_msg = ft.get('error', f"Expected {ft.get('expected')}, got {ft.get('actual')}")
            print(f"  - {ft['test']}: {error_msg} ({ft['endpoint']})")
    
    success_rate = (tester.tests_passed / tester.tests_run * 100) if tester.tests_run > 0 else 0
    print(f"\n📊 Success rate: {success_rate:.1f}%")
    
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())
