"""
Backend Test: Fase 8 — Catch-weight / Dual-UoM Pembelian
Tests catch-weight functionality for purchase orders with kg and meter units.
"""
import requests
import sys
from datetime import datetime

# Use public endpoint from frontend/.env
BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

class CatchWeightTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, passed, details=""):
        """Log test result"""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name}")
            if details:
                print(f"   Details: {details}")
        self.test_results.append({"name": name, "passed": passed, "details": details})

    def login(self, email, password):
        """Login and get token"""
        try:
            response = requests.post(f"{BASE_URL}/auth/login", json={
                "email": email,
                "password": password
            })
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token")
                self.log_test("Login", True, f"Logged in as {email}")
                return True
            else:
                self.log_test("Login", False, f"Status {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_test("Login", False, str(e))
            return False

    def headers(self):
        """Get auth headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def test_create_product_with_catch_weight(self):
        """Test: Create product with gramasi & lebar"""
        try:
            # Create a test product with catch-weight data
            product_data = {
                "sku": f"TEST-CW-{datetime.now().strftime('%H%M%S')}",
                "name": "Test Catch-Weight Fabric",
                "category": "Kain",
                "variant": "Test",
                "color": "Test",
                "motif": "Test",
                "grade": "A",
                "supplier": "Test Supplier",
                "base_unit": "meter",
                "price": 100000,
                "harga_pokok": 80000,
                "gramasi": 250,  # 250 gsm
                "lebar": 1.6,    # 1.6 m width
                # kg_per_meter = 250 * 1.6 / 1000 = 0.4 kg/m
                "status": "active"
            }
            response = requests.post(f"{BASE_URL}/products", json=product_data, headers=self.headers())
            
            if response.status_code == 200:
                product = response.json()
                product_id = product.get("id")
                sku = product.get("sku")
                gramasi = product.get("gramasi")
                lebar = product.get("lebar")
                kg_per_m = (gramasi * lebar) / 1000 if gramasi and lebar else 0
                
                self.log_test(
                    "Create product with gramasi & lebar",
                    True,
                    f"Product {sku}: gramasi={gramasi}, lebar={lebar}, kg/m≈{kg_per_m:.3f}"
                )
                return product_id, sku, kg_per_m
            else:
                self.log_test("Create product with gramasi & lebar", False, f"Status {response.status_code}: {response.text}")
                return None, None, None
        except Exception as e:
            self.log_test("Create product with gramasi & lebar", False, str(e))
            return None, None, None

    def test_create_po_with_kg_unit(self, product_id, sku, kg_per_m):
        """Test: Create PO with unit='kg'"""
        try:
            # Get warehouses
            wh_response = requests.get(f"{BASE_URL}/warehouses", headers=self.headers())
            warehouses = wh_response.json()
            if not warehouses:
                self.log_test("Create PO with unit='kg'", False, "No warehouses found")
                return None, None
            warehouse_id = warehouses[0]["id"]

            # Create PO with kg unit
            po_data = {
                "supplier_name": "Test Supplier Catch-Weight",
                "supplier_contact": "081234567890",
                "warehouse_id": warehouse_id,
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 200,  # 200 kg
                        "unit": "kg",
                        "price": 50000  # price per kg
                    }
                ],
                "expected_delivery_date": datetime.now().strftime("%Y-%m-%d"),
                "notes": "Test PO catch-weight kg unit",
                "created_by": "Admin Test"
            }
            response = requests.post(f"{BASE_URL}/purchase-orders", json=po_data, headers=self.headers())
            
            if response.status_code == 200:
                po = response.json()
                po_id = po.get("id")
                po_number = po.get("po_number")
                items = po.get("items", [])
                
                if items:
                    item = items[0]
                    unit = item.get("unit")
                    quantity = item.get("quantity")
                    quantity_base = item.get("quantity_base", 0)
                    expected_base = quantity / kg_per_m if kg_per_m > 0 else quantity
                    
                    # Check if quantity_base is calculated correctly (200 kg / 0.4 kg/m = 500 m)
                    base_correct = abs(quantity_base - expected_base) < 1.0
                    
                    self.log_test(
                        "Create PO with unit='kg'",
                        unit == "kg" and base_correct,
                        f"PO {po_number}: unit={unit}, qty={quantity} kg, qty_base={quantity_base:.2f} m (expected ≈{expected_base:.2f} m)"
                    )
                    return po_id, po_number
                else:
                    self.log_test("Create PO with unit='kg'", False, "No items in PO")
                    return None, None
            else:
                self.log_test("Create PO with unit='kg'", False, f"Status {response.status_code}: {response.text}")
                return None, None
        except Exception as e:
            self.log_test("Create PO with unit='kg'", False, str(e))
            return None, None

    def test_inbound_task_created(self, po_id, product_id):
        """Test: Check inbound task created with unit='kg'"""
        try:
            response = requests.get(f"{BASE_URL}/inbound/tasks", headers=self.headers())
            
            if response.status_code == 200:
                tasks = response.json()
                # Find task for this PO
                task = next((t for t in tasks if t.get("po_id") == po_id and t.get("product_id") == product_id), None)
                
                if task:
                    task_id = task.get("id")
                    unit = task.get("unit")
                    expected_qty = task.get("expected_qty")
                    
                    self.log_test(
                        "Inbound task created with unit='kg'",
                        unit == "kg",
                        f"Task {task_id}: unit={unit}, expected_qty={expected_qty}"
                    )
                    return task_id
                else:
                    self.log_test("Inbound task created with unit='kg'", False, "Task not found")
                    return None
            else:
                self.log_test("Inbound task created with unit='kg'", False, f"Status {response.status_code}")
                return None
        except Exception as e:
            self.log_test("Inbound task created with unit='kg'", False, str(e))
            return None

    def test_scan_receive(self, task_id, product_id, qty):
        """Test: Scan-receive actual_qty"""
        try:
            scan_data = {
                "product_id": product_id,
                "actual_qty": qty,
                "batch": "TEST-BATCH-001",
                "lot": "TEST-LOT-001",
                "dye_lot": "DL-TEST-01",
                "grade": "A",
                "bin_id": "A1-01"
            }
            response = requests.post(
                f"{BASE_URL}/inbound/tasks/{task_id}/scan-receive",
                json=scan_data,
                headers=self.headers()
            )
            
            if response.status_code == 200:
                task = response.json()
                received_qty = task.get("received_qty", 0)
                
                self.log_test(
                    "Scan-receive actual_qty",
                    received_qty == qty,
                    f"Received {received_qty} kg (expected {qty} kg)"
                )
                return True
            else:
                self.log_test("Scan-receive actual_qty", False, f"Status {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_test("Scan-receive actual_qty", False, str(e))
            return False

    def test_complete_with_rolls(self, task_id, kg_per_m):
        """Test: Complete GR with roll details (weight, length, dye_lot, grade)"""
        try:
            # Complete with 2 rolls: 120 kg + 80 kg = 200 kg total
            # Roll 1: 120 kg, length override 290 m (actual measured)
            # Roll 2: 80 kg, length auto-calculated from weight (80/0.4 = 200 m)
            complete_data = {
                "rolls": [
                    {
                        "weight": 120,
                        "length": 290,  # Override: actual measured length
                        "dye_lot": "DL1",
                        "grade": "A"
                    },
                    {
                        "weight": 80,
                        "length": 0,  # Will be auto-calculated from weight
                        "dye_lot": "DL2",
                        "grade": "A"
                    }
                ]
            }
            response = requests.post(
                f"{BASE_URL}/inbound/tasks/{task_id}/complete",
                json=complete_data,
                headers=self.headers()
            )
            
            if response.status_code == 200:
                task = response.json()
                status = task.get("status")
                
                self.log_test(
                    "Complete GR with roll details",
                    status in ["completed", "qc_pending"],
                    f"Task status: {status}"
                )
                return True
            else:
                self.log_test("Complete GR with roll details", False, f"Status {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_test("Complete GR with roll details", False, str(e))
            return False

    def test_verify_rolls_created(self, product_id):
        """Test: Verify inventory rolls created with weight_kg"""
        try:
            response = requests.get(
                f"{BASE_URL}/inventory/rolls",
                params={"product_id": product_id},
                headers=self.headers()
            )
            
            if response.status_code == 200:
                rolls = response.json()
                # Filter rolls for this product (recent ones)
                recent_rolls = [r for r in rolls if r.get("product_id") == product_id][-2:]  # Last 2 rolls
                
                if len(recent_rolls) >= 2:
                    total_weight = sum(float(r.get("weight_kg", 0)) for r in recent_rolls)
                    total_length = sum(float(r.get("length_initial", 0)) for r in recent_rolls)
                    
                    # Check if weights are correct (120 + 80 = 200 kg)
                    weight_correct = abs(total_weight - 200) < 1.0
                    # Check if lengths are correct (290 + 200 = 490 m)
                    length_correct = abs(total_length - 490) < 5.0
                    
                    self.log_test(
                        "Verify rolls created with weight_kg",
                        weight_correct and length_correct,
                        f"2 rolls: total weight={total_weight:.1f} kg (expected 200), total length={total_length:.1f} m (expected ≈490)"
                    )
                    return True
                else:
                    self.log_test("Verify rolls created with weight_kg", False, f"Expected 2 rolls, found {len(recent_rolls)}")
                    return False
            else:
                self.log_test("Verify rolls created with weight_kg", False, f"Status {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Verify rolls created with weight_kg", False, str(e))
            return False

    def test_verify_po_received_qty(self, po_id):
        """Test: Verify PO received_qty updated"""
        try:
            response = requests.get(f"{BASE_URL}/purchase-orders/{po_id}", headers=self.headers())
            
            if response.status_code == 200:
                po = response.json()
                items = po.get("items", [])
                
                if items:
                    item = items[0]
                    received_qty = item.get("received_qty", 0)
                    unit = item.get("unit")
                    
                    # Check if received_qty is 200 kg
                    self.log_test(
                        "Verify PO received_qty updated",
                        received_qty == 200 and unit == "kg",
                        f"Received {received_qty} {unit} (expected 200 kg)"
                    )
                    return True
                else:
                    self.log_test("Verify PO received_qty updated", False, "No items in PO")
                    return False
            else:
                self.log_test("Verify PO received_qty updated", False, f"Status {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Verify PO received_qty updated", False, str(e))
            return False

    def test_regression_meter_unit(self):
        """Test: Regression - PO with unit='meter' still works"""
        try:
            # Get existing product (Batik Mega)
            prod_response = requests.get(f"{BASE_URL}/products", headers=self.headers())
            products = prod_response.json()
            batik = next((p for p in products if p.get("sku") == "BTK-MEGA-001"), None)
            
            if not batik:
                self.log_test("Regression: PO unit='meter'", False, "Batik product not found")
                return False
            
            # Get warehouse
            wh_response = requests.get(f"{BASE_URL}/warehouses", headers=self.headers())
            warehouses = wh_response.json()
            warehouse_id = warehouses[0]["id"]

            # Create PO with meter unit
            po_data = {
                "supplier_name": "Test Supplier Meter",
                "supplier_contact": "081234567890",
                "warehouse_id": warehouse_id,
                "items": [
                    {
                        "product_id": batik["id"],
                        "quantity": 100,  # 100 meter
                        "unit": "meter",
                        "price": 150000
                    }
                ],
                "expected_delivery_date": datetime.now().strftime("%Y-%m-%d"),
                "notes": "Test PO meter unit regression",
                "created_by": "Admin Test"
            }
            response = requests.post(f"{BASE_URL}/purchase-orders", json=po_data, headers=self.headers())
            
            if response.status_code == 200:
                po = response.json()
                items = po.get("items", [])
                
                if items:
                    item = items[0]
                    unit = item.get("unit")
                    
                    self.log_test(
                        "Regression: PO unit='meter'",
                        unit == "meter",
                        f"PO created with unit={unit}"
                    )
                    return True
                else:
                    self.log_test("Regression: PO unit='meter'", False, "No items in PO")
                    return False
            else:
                self.log_test("Regression: PO unit='meter'", False, f"Status {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_test("Regression: PO unit='meter'", False, str(e))
            return False

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print(f"BACKEND CATCH-WEIGHT TEST SUMMARY")
        print("="*60)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        print("="*60)
        
        if self.tests_passed < self.tests_run:
            print("\nFailed Tests:")
            for result in self.test_results:
                if not result["passed"]:
                    print(f"  ❌ {result['name']}")
                    if result["details"]:
                        print(f"     {result['details']}")


def main():
    print("="*60)
    print("BACKEND TEST: Fase 8 — Catch-weight / Dual-UoM")
    print("="*60)
    
    tester = CatchWeightTester()
    
    # Login
    if not tester.login("admin@kainnusantara.id", "demo12345"):
        print("❌ Login failed. Cannot proceed with tests.")
        return 1
    
    print("\n--- CATCH-WEIGHT E2E FLOW ---")
    
    # Test 1: Create product with gramasi & lebar
    product_id, sku, kg_per_m = tester.test_create_product_with_catch_weight()
    if not product_id:
        print("❌ Cannot proceed without product")
        tester.print_summary()
        return 1
    
    # Test 2: Create PO with unit='kg'
    po_id, po_number = tester.test_create_po_with_kg_unit(product_id, sku, kg_per_m)
    if not po_id:
        print("❌ Cannot proceed without PO")
        tester.print_summary()
        return 1
    
    # Test 3: Check inbound task created
    task_id = tester.test_inbound_task_created(po_id, product_id)
    if not task_id:
        print("❌ Cannot proceed without inbound task")
        tester.print_summary()
        return 1
    
    # Test 4: Scan-receive
    if not tester.test_scan_receive(task_id, product_id, 200):
        print("❌ Scan-receive failed")
        tester.print_summary()
        return 1
    
    # Test 5: Complete with rolls
    if not tester.test_complete_with_rolls(task_id, kg_per_m):
        print("❌ Complete GR failed")
        tester.print_summary()
        return 1
    
    # Test 6: Verify rolls created
    tester.test_verify_rolls_created(product_id)
    
    # Test 7: Verify PO received_qty
    tester.test_verify_po_received_qty(po_id)
    
    print("\n--- REGRESSION TESTS ---")
    
    # Test 8: Regression - meter unit
    tester.test_regression_meter_unit()
    
    # Print summary
    tester.print_summary()
    
    # Return exit code
    return 0 if tester.tests_passed == tester.tests_run else 1


if __name__ == "__main__":
    sys.exit(main())
