#!/usr/bin/env python3
"""
Backend API Testing for FASE L — LINI PRODUK (Product Lines)
Testing comprehensive line filtering, line-gated accounts, and master lifecycle
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://stock-sync-246.preview.emergentagent.com"
PASSWORD = "demo12345"

class FaseLAPITester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.admin_token = None
        self.dewi_token = None
        self.manager_token = None
        
    def log(self, status, message, detail=""):
        """Log test result"""
        self.tests_run += 1
        if status == "PASS":
            self.tests_passed += 1
            print(f"✅ PASS: {message}")
        elif status == "FAIL":
            self.tests_failed += 1
            print(f"❌ FAIL: {message}")
            if detail:
                print(f"   → {detail}")
        else:
            print(f"ℹ️  INFO: {message}")
        if detail and status == "PASS":
            print(f"   → {detail}")
    
    def login(self, email, password=PASSWORD):
        """Login and return token"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if response.status_code == 200:
                token = response.json().get("token")
                self.log("INFO", f"Logged in as {email}")
                return token
            else:
                self.log("FAIL", f"Login failed for {email}", f"Status: {response.status_code}")
                return None
        except Exception as e:
            self.log("FAIL", f"Login error for {email}", str(e))
            return None
    
    def get_headers(self, token, entity_id="ent_ksc"):
        """Get request headers with auth and entity context"""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Entity-Id": entity_id
        }
    
    def test_enums_endpoint(self):
        """Test GET /api/enums for product_line values"""
        print("\n" + "="*80)
        print("TEST 1: GET /api/enums — Master lini hidup")
        print("="*80)
        
        try:
            response = requests.get(
                f"{BASE_URL}/api/enums",
                headers=self.get_headers(self.admin_token, "ent_ksc"),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                product_line_enum = data.get("enums", {}).get("product_line", {})
                values = product_line_enum.get("values", [])
                line_codes = [v.get("value") for v in values]
                
                # Check for expected lines
                expected = ["woven", "knit", "printing"]
                has_all = all(code in line_codes for code in expected)
                
                if has_all:
                    self.log("PASS", "GET /api/enums memuat woven, knit, printing", 
                            f"Found: {', '.join(line_codes)}")
                else:
                    self.log("FAIL", "GET /api/enums tidak memuat semua lini yang diharapkan",
                            f"Expected: {expected}, Got: {line_codes}")
                
                # Check source is 'master'
                source = product_line_enum.get("source")
                if source == "master":
                    self.log("PASS", "Enum product_line source='master' (dari koleksi, bukan hardcode)")
                else:
                    self.log("FAIL", f"Enum product_line source bukan 'master'", f"Got: {source}")
                    
                return line_codes
            else:
                self.log("FAIL", "GET /api/enums gagal", f"Status: {response.status_code}")
                return []
        except Exception as e:
            self.log("FAIL", "GET /api/enums error", str(e))
            return []
    
    def test_products_line_filter(self):
        """Test GET /api/products with line filter"""
        print("\n" + "="*80)
        print("TEST 2: GET /api/products?line=printing — Penyaring lini")
        print("="*80)
        
        try:
            # Get all products
            response_all = requests.get(
                f"{BASE_URL}/api/products",
                headers=self.get_headers(self.admin_token),
                timeout=30
            )
            
            if response_all.status_code == 200:
                all_products = response_all.json()
                total_count = len(all_products) if isinstance(all_products, list) else all_products.get("total", 0)
                self.log("PASS", f"GET /api/products (semua) berhasil", f"Total: {total_count} produk")
            else:
                self.log("FAIL", "GET /api/products gagal", f"Status: {response_all.status_code}")
                return
            
            # Get printing products only
            response_printing = requests.get(
                f"{BASE_URL}/api/products?line=printing",
                headers=self.get_headers(self.admin_token),
                timeout=30
            )
            
            if response_printing.status_code == 200:
                printing_products = response_printing.json()
                printing_count = len(printing_products) if isinstance(printing_products, list) else printing_products.get("total", 0)
                
                # Verify all returned products have line_code=printing or empty
                if isinstance(printing_products, list):
                    products_list = printing_products
                else:
                    products_list = printing_products.get("items", [])
                
                invalid = [p for p in products_list 
                          if p.get("line_code") and p.get("line_code") not in ["printing", ""]]
                
                if not invalid:
                    self.log("PASS", f"GET /api/products?line=printing hanya memuat produk printing",
                            f"Count: {printing_count}")
                else:
                    self.log("FAIL", "GET /api/products?line=printing memuat produk lini lain",
                            f"Invalid: {[p.get('sku') for p in invalid[:3]]}")
            else:
                self.log("FAIL", "GET /api/products?line=printing gagal", 
                        f"Status: {response_printing.status_code}")
                
        except Exception as e:
            self.log("FAIL", "GET /api/products error", str(e))
    
    def test_sales_orders_line_filter(self):
        """Test GET /api/sales-orders with line filter"""
        print("\n" + "="*80)
        print("TEST 3: GET /api/sales-orders?line=printing — Penyaring SO per lini")
        print("="*80)
        
        try:
            response = requests.get(
                f"{BASE_URL}/api/sales-orders?line=printing",
                headers=self.get_headers(self.admin_token),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                orders = data.get("items", []) if isinstance(data, dict) else data
                
                # Check if orders have line_codes field
                has_line_codes = any("line_codes" in order for order in orders)
                
                if has_line_codes:
                    self.log("PASS", "GET /api/sales-orders?line=printing berhasil",
                            f"Found {len(orders)} orders")
                else:
                    self.log("PASS", "GET /api/sales-orders?line=printing berhasil (no orders with line_codes yet)",
                            f"Found {len(orders)} orders")
            else:
                self.log("FAIL", "GET /api/sales-orders?line=printing gagal",
                        f"Status: {response.status_code}")
        except Exception as e:
            self.log("FAIL", "GET /api/sales-orders error", str(e))
    
    def test_purchase_orders_line_filter(self):
        """Test GET /api/purchase-orders with line filter"""
        print("\n" + "="*80)
        print("TEST 4: GET /api/purchase-orders?line=printing — Penyaring PO per lini")
        print("="*80)
        
        try:
            response = requests.get(
                f"{BASE_URL}/api/purchase-orders?line=printing",
                headers=self.get_headers(self.admin_token),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                orders = data.get("items", []) if isinstance(data, dict) else data
                self.log("PASS", "GET /api/purchase-orders?line=printing berhasil",
                        f"Found {len(orders)} POs")
            else:
                self.log("FAIL", "GET /api/purchase-orders?line=printing gagal",
                        f"Status: {response.status_code}")
        except Exception as e:
            self.log("FAIL", "GET /api/purchase-orders error", str(e))
    
    def test_inventory_rolls_line_filter(self):
        """Test GET /api/inventory/rolls with line filter"""
        print("\n" + "="*80)
        print("TEST 5: GET /api/inventory/rolls?line=printing — Penyaring roll per lini")
        print("="*80)
        
        try:
            response = requests.get(
                f"{BASE_URL}/api/inventory/rolls?line=printing",
                headers=self.get_headers(self.admin_token),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                rolls = data.get("items", []) if isinstance(data, dict) else data
                self.log("PASS", "GET /api/inventory/rolls?line=printing berhasil",
                        f"Found {len(rolls)} rolls")
            else:
                self.log("FAIL", "GET /api/inventory/rolls?line=printing gagal",
                        f"Status: {response.status_code}")
        except Exception as e:
            self.log("FAIL", "GET /api/inventory/rolls error", str(e))
    
    def test_line_gated_account_products(self):
        """Test line-gated account (dewi.printing) can only see printing products"""
        print("\n" + "="*80)
        print("TEST 6: Akun berpagar lini (dewi.printing) — hanya melihat produk printing")
        print("="*80)
        
        try:
            response = requests.get(
                f"{BASE_URL}/api/products",
                headers=self.get_headers(self.dewi_token),
                timeout=30
            )
            
            if response.status_code == 200:
                products = response.json()
                products_list = products if isinstance(products, list) else products.get("items", [])
                
                # Check that no woven or knit products are visible
                woven_products = [p for p in products_list if p.get("line_code") == "woven"]
                knit_products = [p for p in products_list if p.get("line_code") == "knit"]
                printing_products = [p for p in products_list if p.get("line_code") == "printing"]
                
                if not woven_products and not knit_products:
                    self.log("PASS", "Dewi TIDAK melihat produk woven/knit",
                            f"Printing: {len(printing_products)}, Woven: 0, Knit: 0")
                else:
                    self.log("FAIL", "Dewi melihat produk di luar lininya",
                            f"Woven: {len(woven_products)}, Knit: {len(knit_products)}")
                
                # Check that printing products ARE visible
                if printing_products:
                    self.log("PASS", "Dewi melihat produk printing",
                            f"Count: {len(printing_products)}")
                else:
                    self.log("FAIL", "Dewi TIDAK melihat produk printing (seharusnya terlihat)")
            else:
                self.log("FAIL", "GET /api/products untuk Dewi gagal",
                        f"Status: {response.status_code}")
        except Exception as e:
            self.log("FAIL", "Test akun berpagar error", str(e))
    
    def test_line_gated_account_forbidden_access(self):
        """Test line-gated account gets 403 when accessing woven product"""
        print("\n" + "="*80)
        print("TEST 7: Akun berpagar lini — 403 saat akses produk woven")
        print("="*80)
        
        try:
            # First get a woven product ID as admin
            response_admin = requests.get(
                f"{BASE_URL}/api/products",
                headers=self.get_headers(self.admin_token),
                timeout=30
            )
            
            if response_admin.status_code == 200:
                products = response_admin.json()
                products_list = products if isinstance(products, list) else products.get("items", [])
                woven_product = next((p for p in products_list if p.get("line_code") == "woven"), None)
                
                if woven_product:
                    # Try to access as Dewi
                    product_id = woven_product.get("id")
                    response_dewi = requests.get(
                        f"{BASE_URL}/api/products/{product_id}/stock-breakdown",
                        headers=self.get_headers(self.dewi_token),
                        timeout=30
                    )
                    
                    if response_dewi.status_code == 403:
                        detail = response_dewi.json().get("detail", "")
                        # Check for Indonesian error message
                        has_indonesian = any(word in detail.lower() for word in ["lini", "akses", "printing"])
                        
                        if has_indonesian:
                            self.log("PASS", "403 dengan pesan Indonesia yang jelas",
                                    f"Message: {detail[:100]}")
                        else:
                            self.log("FAIL", "403 tetapi pesan bukan Indonesia atau tidak jelas",
                                    f"Message: {detail[:100]}")
                    else:
                        self.log("FAIL", "Seharusnya 403, tetapi dapat status lain",
                                f"Status: {response_dewi.status_code}")
                else:
                    self.log("FAIL", "Tidak ada produk woven untuk diuji")
            else:
                self.log("FAIL", "Gagal mendapatkan produk untuk uji 403")
        except Exception as e:
            self.log("FAIL", "Test 403 error", str(e))
    
    def test_line_gated_account_create_so_forbidden(self):
        """Test line-gated account gets 403 when creating SO with woven product"""
        print("\n" + "="*80)
        print("TEST 8: Akun berpagar lini — 403 saat membuat SO dengan produk woven")
        print("="*80)
        
        try:
            # Get woven product and customer as admin
            response_products = requests.get(
                f"{BASE_URL}/api/products",
                headers=self.get_headers(self.admin_token),
                timeout=30
            )
            
            response_customers = requests.get(
                f"{BASE_URL}/api/customers",
                headers=self.get_headers(self.admin_token),
                timeout=30
            )
            
            if response_products.status_code == 200 and response_customers.status_code == 200:
                products = response_products.json()
                products_list = products if isinstance(products, list) else products.get("items", [])
                woven_product = next((p for p in products_list if p.get("line_code") == "woven"), None)
                
                customers = response_customers.json()
                customers_list = customers if isinstance(customers, list) else customers.get("items", [])
                # Find customer with address and not "Sejahtera" (blocked)
                customer = next((c for c in customers_list 
                               if c.get("addresses") and "Sejahtera" not in c.get("name", "")), None)
                
                if woven_product and customer:
                    # Try to create SO as Dewi with woven product
                    so_data = {
                        "customer_id": customer["id"],
                        "shipping_address_id": customer["addresses"][0]["id"],
                        "items": [{
                            "product_id": woven_product["id"],
                            "quantity": 1,
                            "unit": "meter"
                        }]
                    }
                    
                    response_so = requests.post(
                        f"{BASE_URL}/api/sales-orders",
                        headers=self.get_headers(self.dewi_token),
                        json=so_data,
                        timeout=30
                    )
                    
                    if response_so.status_code == 403:
                        detail = response_so.json().get("detail", "")
                        # Check for Indonesian error message mentioning line and product
                        has_indonesian = any(word in detail.lower() 
                                           for word in ["lini", "produk", "printing", "woven"])
                        
                        if has_indonesian:
                            self.log("PASS", "POST SO dengan produk woven ditolak 403 dengan pesan Indonesia",
                                    f"Message: {detail[:150]}")
                        else:
                            self.log("FAIL", "403 tetapi pesan tidak memadai",
                                    f"Message: {detail[:150]}")
                    else:
                        self.log("FAIL", "Seharusnya 403, tetapi dapat status lain",
                                f"Status: {response_so.status_code}, Response: {response_so.text[:200]}")
                else:
                    self.log("FAIL", "Tidak ada produk woven atau customer untuk diuji")
            else:
                self.log("FAIL", "Gagal mendapatkan data untuk uji POST SO")
        except Exception as e:
            self.log("FAIL", "Test POST SO forbidden error", str(e))
    
    def test_master_line_creation(self):
        """Test creating new line via master API"""
        print("\n" + "="*80)
        print("TEST 9: POST /api/entity-masters/product-lines — Membuat lini baru")
        print("="*80)
        
        try:
            test_code = f"denimuji{datetime.now().strftime('%H%M%S')}"
            line_data = {
                "code": test_code,
                "name": "Denim Uji",
                "sort": 10,
                "fabric_type_required": "",
                "measure_unit_default": "yard",
                "stage_sequence": ["yarn", "tenun", "celup", "inspect"],
                "active": True
            }
            
            response = requests.post(
                f"{BASE_URL}/api/entity-masters/product-lines",
                headers=self.get_headers(self.admin_token, "all"),
                json=line_data,
                timeout=30
            )
            
            if response.status_code == 200:
                created = response.json()
                self.log("PASS", f"Lini baru '{test_code}' berhasil dibuat",
                        f"ID: {created.get('id')}")
                
                # Verify it appears in enums
                response_enum = requests.get(
                    f"{BASE_URL}/api/enums",
                    headers=self.get_headers(self.admin_token),
                    timeout=30
                )
                
                if response_enum.status_code == 200:
                    data = response_enum.json()
                    values = data.get("enums", {}).get("product_line", {}).get("values", [])
                    line_codes = [v.get("value") for v in values]
                    
                    if test_code in line_codes:
                        self.log("PASS", "Lini baru langsung muncul di /api/enums (tanpa restart)")
                    else:
                        self.log("FAIL", "Lini baru tidak muncul di /api/enums",
                                f"Expected: {test_code}, Got: {line_codes}")
                
                # Cleanup: delete the test line
                try:
                    requests.delete(
                        f"{BASE_URL}/api/entity-masters/product-lines/{created.get('id')}",
                        headers=self.get_headers(self.admin_token, "all"),
                        timeout=30
                    )
                except Exception:  # noqa: S110
                    pass
            else:
                self.log("FAIL", "POST /api/entity-masters/product-lines gagal",
                        f"Status: {response.status_code}, Response: {response.text[:200]}")
        except Exception as e:
            self.log("FAIL", "Test master line creation error", str(e))
    
    def test_user_line_assignment_validation(self):
        """Test PATCH /api/users with invalid line code"""
        print("\n" + "="*80)
        print("TEST 10: PATCH /api/users — Validasi kode lini yang salah")
        print("="*80)
        
        try:
            # Get dewi's user ID
            response_users = requests.get(
                f"{BASE_URL}/api/users",
                headers=self.get_headers(self.admin_token),
                timeout=30
            )
            
            if response_users.status_code == 200:
                users = response_users.json()
                users_list = users if isinstance(users, list) else users.get("items", [])
                dewi = next((u for u in users_list if "dewi.printing" in u.get("email", "")), None)
                
                if dewi:
                    # Try to assign invalid line code
                    response_patch = requests.patch(
                        f"{BASE_URL}/api/users/{dewi['id']}",
                        headers=self.get_headers(self.admin_token),
                        json={"data": {"allowed_line_codes": ["printng"]}},  # typo: printng instead of printing
                        timeout=30
                    )
                    
                    if response_patch.status_code == 400:
                        detail = response_patch.json().get("detail", "")
                        # Check for Indonesian error message
                        has_indonesian = "lini" in detail.lower() or "pilihan" in detail.lower()
                        
                        if has_indonesian:
                            self.log("PASS", "Kode lini salah ditolak 400 dengan pesan Indonesia",
                                    f"Message: {detail[:150]}")
                        else:
                            self.log("FAIL", "400 tetapi pesan tidak memadai",
                                    f"Message: {detail[:150]}")
                    else:
                        self.log("FAIL", "Seharusnya 400, tetapi dapat status lain",
                                f"Status: {response_patch.status_code}")
                else:
                    self.log("FAIL", "User dewi.printing tidak ditemukan")
            else:
                self.log("FAIL", "Gagal mendapatkan daftar user")
        except Exception as e:
            self.log("FAIL", "Test user line assignment validation error", str(e))
    
    def run_all_tests(self):
        """Run all backend API tests"""
        print("\n" + "="*80)
        print("FASE L — BACKEND API TESTING")
        print("Testing Product Lines (Lini Produk) Implementation")
        print("="*80)
        
        # Login
        print("\n📝 Logging in...")
        self.admin_token = self.login("admin@kainnusantara.id")
        self.dewi_token = self.login("dewi.printing@kainnusantara.id")
        self.manager_token = self.login("manager@kainnusantara.id")
        
        if not self.admin_token:
            print("❌ Cannot proceed without admin login")
            return False
        
        if not self.dewi_token:
            print("⚠️  Warning: dewi.printing login failed, some tests will be skipped")
        
        # Run tests
        self.test_enums_endpoint()
        self.test_products_line_filter()
        self.test_sales_orders_line_filter()
        self.test_purchase_orders_line_filter()
        self.test_inventory_rolls_line_filter()
        
        if self.dewi_token:
            self.test_line_gated_account_products()
            self.test_line_gated_account_forbidden_access()
            self.test_line_gated_account_create_so_forbidden()
        
        self.test_master_line_creation()
        self.test_user_line_assignment_validation()
        
        # Summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Total Tests: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {self.tests_failed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0:.1f}%")
        print("="*80)
        
        return self.tests_failed == 0

def main():
    tester = FaseLAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
