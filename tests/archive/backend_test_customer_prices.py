#!/usr/bin/env python3
"""Backend API Testing for Customer Pricelist Feature (F1b)"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://number-separator.preview.emergentagent.com/api"
ENTITY_ID = "ent_ksc"
PASSWORD = "demo12345"

class APITester:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url
        self.tokens = {}
        self.sessions = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def login(self, role):
        """Login and store session per role"""
        emails = {
            "admin": "admin@kainnusantara.id",
            "manager": "manager@kainnusantara.id",
            "sales": "sales@kainnusantara.id",
            "warehouse": "warehouse@kainnusantara.id"
        }
        
        if role in self.sessions:
            return self.sessions[role]
        
        session = requests.Session()
        try:
            r = session.post(f"{self.base_url}/auth/login",
                           json={"email": emails[role], "password": PASSWORD},
                           timeout=30)
            r.raise_for_status()
            data = r.json()
            self.tokens[role] = data.get("token", "")
            session.headers.update({
                "Authorization": f"Bearer {self.tokens[role]}",
                "X-Entity-Id": ENTITY_ID,
                "Content-Type": "application/json"
            })
            self.sessions[role] = session
            print(f"✅ Logged in as {role}")
            return session
        except Exception as e:
            print(f"❌ Login failed for {role}: {e}")
            return None

    def test(self, name, condition, details=""):
        """Record test result"""
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            print(f"  ✅ {name}")
            return True
        else:
            self.tests_failed += 1
            msg = f"{name}" + (f" - {details}" if details else "")
            self.failures.append(msg)
            print(f"  ❌ {name}" + (f" - {details}" if details else ""))
            return False

    def get_customer(self, session):
        """Get first customer for testing"""
        try:
            r = session.get(f"{self.base_url}/customers", timeout=30)
            r.raise_for_status()
            data = r.json()
            items = data.get("items", []) if isinstance(data, dict) else data
            for item in items:
                if item.get("entity_id") == ENTITY_ID or not item.get("entity_id"):
                    return item
            return items[0] if items else None
        except Exception as e:
            print(f"❌ Failed to get customer: {e}")
            return None

    def get_products(self, session, n=2):
        """Get products for testing"""
        try:
            r = session.get(f"{self.base_url}/products", timeout=30)
            r.raise_for_status()
            data = r.json()
            items = data if isinstance(data, list) else data.get("items", [])
            return [p for p in items if float(p.get("price", 0)) > 0][:n]
        except Exception as e:
            print(f"❌ Failed to get products: {e}")
            return []

    def run_tests(self):
        """Run all backend tests"""
        print("=" * 80)
        print("BACKEND API TESTING - Customer Pricelist (F1b)")
        print("=" * 80)
        
        # Login all roles
        admin = self.login("admin")
        manager = self.login("manager")
        sales = self.login("sales")
        warehouse = self.login("warehouse")
        
        if not admin:
            print("❌ FATAL: Cannot login as admin")
            return 1
        
        # Get test data
        customer = self.get_customer(admin)
        products = self.get_products(admin, 2)
        
        if not customer:
            print("❌ FATAL: No customer found")
            return 1
        if len(products) < 2:
            print("❌ FATAL: Need at least 2 products")
            return 1
        
        print(f"\n📋 Test Data:")
        print(f"  Customer: {customer.get('name')} ({customer.get('id')})")
        print(f"  Products: {products[0].get('sku')}, {products[1].get('sku')}")
        
        # Test 1: Grid endpoint
        print("\n[1] GET /api/customer-prices (Grid)")
        try:
            r = admin.get(f"{self.base_url}/customer-prices",
                         params={"customer_id": customer["id"]},
                         timeout=30)
            self.test("Grid returns 200", r.status_code == 200, f"Got {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                self.test("Grid has rows", "rows" in data and len(data["rows"]) > 0)
                self.test("Grid has customer_name", data.get("customer_name") == customer.get("name"))
                self.test("Grid has guard info", "guard" in data and "guard_on" in data.get("guard", {}))
                if data.get("rows"):
                    row = data["rows"][0]
                    required_fields = ["global_price", "entity_price", "customer_price", 
                                     "special_price", "effective_price", "price_source",
                                     "pending_price", "hpp_ref"]
                    self.test("Grid row has all required fields",
                            all(f in row for f in required_fields),
                            f"Missing: {[f for f in required_fields if f not in row]}")
        except Exception as e:
            self.test("Grid endpoint", False, str(e))
        
        # Test 2: Records endpoint
        print("\n[2] GET /api/customer-prices/records (History)")
        try:
            r = admin.get(f"{self.base_url}/customer-prices/records",
                         params={"customer_id": customer["id"]},
                         timeout=30)
            self.test("Records returns 200", r.status_code == 200, f"Got {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                self.test("Records is a list", isinstance(data, list))
                if data:
                    rec = data[0]
                    self.test("Record has effective_status", "effective_status" in rec)
        except Exception as e:
            self.test("Records endpoint", False, str(e))
        
        # Test 3: Quote endpoint
        print("\n[3] GET /api/customer-prices/quote (Price Resolution)")
        try:
            product_ids = f"{products[0]['id']},{products[1]['id']}"
            r = admin.get(f"{self.base_url}/customer-prices/quote",
                         params={"customer_id": customer["id"], "product_ids": product_ids},
                         timeout=30)
            self.test("Quote returns 200", r.status_code == 200, f"Got {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                self.test("Quote has prices dict", "prices" in data)
                if "prices" in data:
                    prices = data["prices"]
                    self.test("Quote has both products", 
                            products[0]["id"] in prices and products[1]["id"] in prices)
                    if products[0]["id"] in prices:
                        p = prices[products[0]["id"]]
                        self.test("Price has source field", "source" in p)
                        self.test("Price has price field", "price" in p)
        except Exception as e:
            self.test("Quote endpoint", False, str(e))
        
        # Test 4: Floor endpoint
        print("\n[4] GET /api/customer-prices/floor (Price Floor)")
        try:
            r = admin.get(f"{self.base_url}/customer-prices/floor",
                         params={"product_id": products[0]["id"]},
                         timeout=30)
            self.test("Floor returns 200", r.status_code == 200, f"Got {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                required = ["floor", "hpp", "entity_reference", "basis_label", "guard_on"]
                self.test("Floor has all required fields",
                        all(f in data for f in required),
                        f"Missing: {[f for f in required if f not in data]}")
                
                # Test with price parameter
                r2 = admin.get(f"{self.base_url}/customer-prices/floor",
                             params={"product_id": products[0]["id"], "price": 1},
                             timeout=30)
                self.test("Floor with price returns 200", r2.status_code == 200)
                if r2.status_code == 200:
                    data2 = r2.json()
                    self.test("Floor evaluation has below_floor", "below_floor" in data2)
                    self.test("Floor evaluation has needs_approval", "needs_approval" in data2)
                    self.test("Floor evaluation has summary", "summary" in data2)
        except Exception as e:
            self.test("Floor endpoint", False, str(e))
        
        # Test 5: Create customer price (above floor)
        print("\n[5] POST /api/customer-prices (Create - Above Floor)")
        try:
            # Get floor first
            r_floor = admin.get(f"{self.base_url}/customer-prices/floor",
                              params={"product_id": products[0]["id"]},
                              timeout=30)
            if r_floor.status_code == 200:
                floor_data = r_floor.json()
                floor = floor_data.get("floor", 0)
                # Set price 50% above floor
                test_price = round(floor * 1.5, 2) if floor > 0 else 100000
                
                r = admin.post(f"{self.base_url}/customer-prices",
                             json={
                                 "customer_id": customer["id"],
                                 "product_id": products[0]["id"],
                                 "sell_price": test_price,
                                 "note": "Test above floor"
                             },
                             timeout=30)
                self.test("Create above floor returns 200/201", 
                        r.status_code in [200, 201], f"Got {r.status_code}")
                if r.status_code in [200, 201]:
                    data = r.json()
                    self.test("Above floor does not need approval",
                            data.get("approval_required") == False,
                            f"approval_required={data.get('approval_required')}")
                    self.test("Above floor status is active/current",
                            data.get("status") == "active" or data.get("effective_status") == "current",
                            f"status={data.get('status')}, effective_status={data.get('effective_status')}")
        except Exception as e:
            self.test("Create above floor", False, str(e))
        
        # Test 6: Create customer price (below floor)
        print("\n[6] POST /api/customer-prices (Create - Below Floor)")
        try:
            r_floor = admin.get(f"{self.base_url}/customer-prices/floor",
                              params={"product_id": products[1]["id"]},
                              timeout=30)
            if r_floor.status_code == 200:
                floor_data = r_floor.json()
                floor = floor_data.get("floor", 0)
                # Set price 40% below floor
                test_price = round(floor * 0.6, 2) if floor > 0 else 1000
                
                r = admin.post(f"{self.base_url}/customer-prices",
                             json={
                                 "customer_id": customer["id"],
                                 "product_id": products[1]["id"],
                                 "sell_price": test_price,
                                 "note": "Test below floor"
                             },
                             timeout=30)
                self.test("Create below floor returns 200/201",
                        r.status_code in [200, 201], f"Got {r.status_code}")
                if r.status_code in [200, 201]:
                    data = r.json()
                    self.test("Below floor needs approval",
                            data.get("approval_required") == True,
                            f"approval_required={data.get('approval_required')}")
                    self.test("Below floor status is pending_approval",
                            data.get("status") == "pending_approval",
                            f"status={data.get('status')}")
                    self.test("Below floor has price_approval_id",
                            bool(data.get("price_approval_id")),
                            f"price_approval_id={data.get('price_approval_id')}")
        except Exception as e:
            self.test("Create below floor", False, str(e))
        
        # Test 7: CSV Import
        print("\n[7] POST /api/customer-prices/import (CSV Import)")
        try:
            # Test Indonesian number format
            csv_text = f"""sku;nama_produk;harga_pelanggan;berlaku_dari;berlaku_sampai;catatan
{products[0]['sku']};{products[0]['name']};255.000;;;Test import
{products[1]['sku']};{products[1]['name']};1.265.400;;;Test import"""
            
            r = admin.post(f"{self.base_url}/customer-prices/import",
                         json={"customer_id": customer["id"], "csv_text": csv_text},
                         timeout=30)
            self.test("CSV import returns 200", r.status_code == 200, f"Got {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                self.test("Import has applied count", "applied" in data)
                self.test("Import has pending count", "pending" in data)
                self.test("Import has errors list", "errors" in data)
        except Exception as e:
            self.test("CSV import", False, str(e))
        
        # Test 8: CSV Export
        print("\n[8] GET /api/customer-prices/export (CSV Export)")
        try:
            r = admin.get(f"{self.base_url}/customer-prices/export",
                         params={"customer_id": customer["id"]},
                         timeout=30)
            self.test("CSV export returns 200", r.status_code == 200, f"Got {r.status_code}")
            if r.status_code == 200:
                content = r.content
                self.test("CSV has UTF-8 BOM", content.startswith(b"\xef\xbb\xbf"))
                self.test("CSV uses semicolon delimiter", b";" in content)
        except Exception as e:
            self.test("CSV export", False, str(e))
        
        # Test 9: RBAC - Sales can view
        print("\n[9] RBAC - Sales View Access")
        if sales:
            try:
                r = sales.get(f"{self.base_url}/customer-prices",
                            params={"customer_id": customer["id"]},
                            timeout=30)
                self.test("Sales can view grid", r.status_code == 200, f"Got {r.status_code}")
            except Exception as e:
                self.test("Sales view access", False, str(e))
        
        # Test 10: RBAC - Sales cannot create
        print("\n[10] RBAC - Sales Cannot Create")
        if sales:
            try:
                r = sales.post(f"{self.base_url}/customer-prices",
                             json={
                                 "customer_id": customer["id"],
                                 "product_id": products[0]["id"],
                                 "sell_price": 50000
                             },
                             timeout=30)
                self.test("Sales create returns 403", r.status_code == 403, f"Got {r.status_code}")
            except Exception as e:
                self.test("Sales create blocked", False, str(e))
        
        # Test 11: RBAC - Warehouse blocked
        print("\n[11] RBAC - Warehouse Blocked")
        if warehouse:
            try:
                r = warehouse.get(f"{self.base_url}/customer-prices",
                                params={"customer_id": customer["id"]},
                                timeout=30)
                self.test("Warehouse view returns 403", r.status_code == 403, f"Got {r.status_code}")
            except Exception as e:
                self.test("Warehouse blocked", False, str(e))
        
        # Test 12: Price Approvals Integration
        print("\n[12] Price Approvals Integration")
        try:
            r = admin.get(f"{self.base_url}/price-approvals",
                         params={"customer_id": customer["id"]},
                         timeout=30)
            self.test("Price approvals endpoint accessible", r.status_code == 200, f"Got {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    # Check if any approval is from customer pricelist
                    from_pricelist = [a for a in data if a.get("source") == "customer_pricelist"]
                    self.test("Has approvals from customer pricelist", len(from_pricelist) > 0,
                            f"Found {len(from_pricelist)} approvals")
        except Exception as e:
            self.test("Price approvals integration", False, str(e))
        
        # Test 13: Invalid customer_id
        print("\n[13] Error Handling - Invalid Customer")
        try:
            r = admin.get(f"{self.base_url}/customer-prices",
                         params={"customer_id": "invalid_customer_id"},
                         timeout=30)
            self.test("Invalid customer returns 400", r.status_code == 400, f"Got {r.status_code}")
        except Exception as e:
            self.test("Invalid customer handling", False, str(e))
        
        # Print summary
        print("\n" + "=" * 80)
        print(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failures:
            print(f"\n❌ FAILED TESTS ({len(self.failures)}):")
            for i, failure in enumerate(self.failures, 1):
                print(f"  {i}. {failure}")
        
        return 0 if self.tests_failed == 0 else 1

def main():
    tester = APITester()
    return tester.run_tests()

if __name__ == "__main__":
    sys.exit(main())
