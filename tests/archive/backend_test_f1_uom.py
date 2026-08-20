#!/usr/bin/env python3
"""
Kain Nusantara Backend Test - F1 Feature (UOM/Units following master data)
Tests that units follow each product's master data base_unit (yard, meter, kg)
and inventory displays show dual units (roll count + quantity-with-unit)
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://kainnusantara-stage.preview.emergentagent.com/api"

# Test credentials
TEST_USER = {"email": "admin@kainnusantara.id", "password": "demo12345"}

class F1UOMTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        self.results = []

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

    def test_auth(self):
        """Test authentication"""
        try:
            r = requests.post(f"{BASE_URL}/auth/login", json=TEST_USER, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "token" in data and "user" in data:
                    self.token = data["token"]
                    self.log("PASS", "Authentication", f"User: {data['user'].get('name', 'N/A')}")
                    return True
            self.log("FAIL", "Authentication", f"Status: {r.status_code}, Body: {r.text[:200]}")
            return False
        except Exception as e:
            self.log("FAIL", "Authentication", f"Error: {str(e)}")
            return False

    def get_headers(self):
        """Get auth headers"""
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def test_products_with_non_meter_units(self):
        """Test GET /products - verify new products with base_unit yard and kg exist"""
        try:
            r = requests.get(f"{BASE_URL}/products", headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Products API", f"Status: {r.status_code}")
                return False
            
            products = r.json()
            
            # Find the two new products
            denim = next((p for p in products if p.get("sku") == "DNM-BDG-001"), None)
            benang = next((p for p in products if p.get("sku") == "BNG-KTN-001"), None)
            
            if not denim:
                self.log("FAIL", "Products - Denim (yard)", "DNM-BDG-001 not found")
                return False
            
            if not benang:
                self.log("FAIL", "Products - Benang (kg)", "BNG-KTN-001 not found")
                return False
            
            # Verify base_unit
            denim_unit = denim.get("base_unit", "")
            benang_unit = benang.get("base_unit", "")
            
            if denim_unit != "yard":
                self.log("FAIL", "Products - Denim base_unit", f"Expected 'yard', got '{denim_unit}'")
                return False
            
            if benang_unit != "kg":
                self.log("FAIL", "Products - Benang base_unit", f"Expected 'kg', got '{benang_unit}'")
                return False
            
            self.log("PASS", "Products - Non-meter units", 
                    f"Denim: {denim_unit}, Benang: {benang_unit}")
            return True
            
        except Exception as e:
            self.log("FAIL", "Products API", f"Error: {str(e)}")
            return False

    def test_inventory_balances_with_units(self):
        """Test GET /inventory/balances - verify balances show correct base_unit and roll_count"""
        try:
            r = requests.get(f"{BASE_URL}/inventory/balances", headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Inventory Balances API", f"Status: {r.status_code}")
                return False
            
            balances = r.json()
            
            # Find balances for the two new products
            denim_balance = next((b for b in balances if b.get("sku") == "DNM-BDG-001"), None)
            benang_balance = next((b for b in balances if b.get("sku") == "BNG-KTN-001"), None)
            
            if not denim_balance:
                self.log("FAIL", "Inventory Balances - Denim", "DNM-BDG-001 balance not found")
                return False
            
            if not benang_balance:
                self.log("FAIL", "Inventory Balances - Benang", "BNG-KTN-001 balance not found")
                return False
            
            # Verify base_unit
            denim_unit = denim_balance.get("base_unit", "")
            benang_unit = benang_balance.get("base_unit", "")
            
            if denim_unit != "yard":
                self.log("FAIL", "Inventory Balances - Denim unit", 
                        f"Expected 'yard', got '{denim_unit}'")
                return False
            
            if benang_unit != "kg":
                self.log("FAIL", "Inventory Balances - Benang unit", 
                        f"Expected 'kg', got '{benang_unit}'")
                return False
            
            # Verify quantities and roll counts
            denim_qty = denim_balance.get("on_hand_qty", 0)
            denim_rolls = denim_balance.get("on_hand_roll_count", 0)
            benang_qty = benang_balance.get("on_hand_qty", 0)
            benang_rolls = benang_balance.get("on_hand_roll_count", 0)
            
            # Expected: Denim 300 yard = 2 rolls, Benang 90 kg = 1 roll
            if denim_qty != 300:
                self.log("FAIL", "Inventory Balances - Denim qty", 
                        f"Expected 300 yard, got {denim_qty}")
                return False
            
            if denim_rolls != 2:
                self.log("FAIL", "Inventory Balances - Denim rolls", 
                        f"Expected 2 rolls, got {denim_rolls}")
                return False
            
            if benang_qty != 90:
                self.log("FAIL", "Inventory Balances - Benang qty", 
                        f"Expected 90 kg, got {benang_qty}")
                return False
            
            if benang_rolls != 1:
                self.log("FAIL", "Inventory Balances - Benang rolls", 
                        f"Expected 1 roll, got {benang_rolls}")
                return False
            
            self.log("PASS", "Inventory Balances - Units & Rolls", 
                    f"Denim: {denim_qty} {denim_unit} = {denim_rolls} rolls, "
                    f"Benang: {benang_qty} {benang_unit} = {benang_rolls} roll")
            return True
            
        except Exception as e:
            self.log("FAIL", "Inventory Balances API", f"Error: {str(e)}")
            return False

    def test_inventory_rolls_with_units(self):
        """Test GET /inventory/rolls - verify rolls have correct units"""
        try:
            # Test for denim product
            r = requests.get(f"{BASE_URL}/inventory/rolls", 
                           params={"product_id": "prod_denim_selvedge"},
                           headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Inventory Rolls API - Denim", f"Status: {r.status_code}")
                return False
            
            denim_rolls = r.json()
            if len(denim_rolls) == 0:
                self.log("FAIL", "Inventory Rolls - Denim", "No rolls found for denim product")
                return False
            
            # Check if rolls have yard unit
            for roll in denim_rolls:
                if roll.get("unit") != "yard":
                    self.log("FAIL", "Inventory Rolls - Denim unit", 
                            f"Expected 'yard', got '{roll.get('unit')}'")
                    return False
            
            # Test for benang product
            r = requests.get(f"{BASE_URL}/inventory/rolls", 
                           params={"product_id": "prod_benang_katun"},
                           headers=self.get_headers(), timeout=10)
            if r.status_code != 200:
                self.log("FAIL", "Inventory Rolls API - Benang", f"Status: {r.status_code}")
                return False
            
            benang_rolls = r.json()
            if len(benang_rolls) == 0:
                self.log("FAIL", "Inventory Rolls - Benang", "No rolls found for benang product")
                return False
            
            # Check if rolls have kg unit
            for roll in benang_rolls:
                if roll.get("unit") != "kg":
                    self.log("FAIL", "Inventory Rolls - Benang unit", 
                            f"Expected 'kg', got '{roll.get('unit')}'")
                    return False
            
            self.log("PASS", "Inventory Rolls - Units", 
                    f"Denim rolls: {len(denim_rolls)} (yard), Benang rolls: {len(benang_rolls)} (kg)")
            return True
            
        except Exception as e:
            self.log("FAIL", "Inventory Rolls API", f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all F1 UOM tests"""
        print("=" * 70)
        print("KAIN NUSANTARA F1 FEATURE TEST - UOM/UNITS FOLLOWING MASTER DATA")
        print("=" * 70)
        print()

        # Auth
        if not self.test_auth():
            print("\n❌ Authentication failed. Stopping tests.")
            return False

        # F1 Backend Tests
        print("\n--- F1 Backend API Tests ---")
        self.test_products_with_non_meter_units()
        self.test_inventory_balances_with_units()
        self.test_inventory_rolls_with_units()

        # Summary
        print("\n" + "=" * 70)
        print(f"F1 BACKEND TEST SUMMARY")
        print("=" * 70)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        print("=" * 70)

        return self.tests_passed == self.tests_run


def main():
    tester = F1UOMTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
