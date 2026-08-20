#!/usr/bin/env python3
"""
Backend Testing for SALES REVAMP V2 (FASE C, C2, D)
Tests roll picker, reconciliation, and cross-entity features
"""
import requests
import sys

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

class TestRunner:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.admin_token = None
        self.failures = []

    def log(self, message: str, level: str = "INFO"):
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "•")
        print(f"{prefix} {message}")

    def test(self, name: str, method: str, endpoint: str, expected_status: int,
             data=None, token=None, params=None, check_response=None):
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.log(f"Test #{self.tests_run}: {name}", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            response_data = {}
            try:
                response_data = response.json()
            except:
                pass

            if success:
                if check_response and not check_response(response_data):
                    success = False
                    self.log(f"  Response validation failed", "FAIL")
                    self.failures.append(f"{name}: Response validation failed")
                    self.tests_failed += 1
                else:
                    self.tests_passed += 1
                    self.log(f"  PASSED (status: {response.status_code})", "PASS")
            else:
                self.log(f"  FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                if response_data:
                    self.log(f"  Response: {str(response_data)[:200]}", "FAIL")
                self.failures.append(f"{name}: Expected {expected_status}, got {response.status_code}")
                self.tests_failed += 1

            return success, response_data

        except Exception as e:
            self.log(f"  FAILED - Error: {str(e)}", "FAIL")
            self.failures.append(f"{name}: {str(e)}")
            self.tests_failed += 1
            return False, {}

    def login(self, email: str, password: str):
        """Login and return token"""
        self.log(f"Logging in as {email}...", "INFO")
        success, data = self.test(
            f"Login {email}",
            "POST",
            "auth/login",
            200,
            data={"email": email, "password": password}
        )
        if success and 'token' in data:
            self.log(f"  Login successful", "PASS")
            return data['token']
        self.log(f"  Login failed", "FAIL")
        return None

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Total Tests: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {self.tests_failed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0:.1f}%")
        
        if self.failures:
            print("\n" + "="*70)
            print("FAILURES:")
            print("="*70)
            for i, failure in enumerate(self.failures, 1):
                print(f"{i}. {failure}")
        
        print("="*70)


def main():
    runner = TestRunner()
    
    print("="*70)
    print("SALES REVAMP V2 - BACKEND TESTING (FASE C, C2, D)")
    print("="*70)
    print()

    # Login
    runner.admin_token = runner.login("admin@kainnusantara.id", "demo12345")
    if not runner.admin_token:
        print("❌ CRITICAL: Admin login failed. Cannot continue.")
        return 1

    # ========== FASE C: ROLL PICKER API ==========
    print("\n" + "="*70)
    print("FASE C: ROLL PICKER API")
    print("="*70)
    
    # Get a product with rolls
    runner.log("Getting products with rolls...", "INFO")
    success, products = runner.test(
        "GET products",
        "GET",
        "products",
        200,
        token=runner.admin_token
    )
    
    product_with_rolls = None
    if success and products:
        for p in products:
            if int(p.get('roll_count', 0)) > 0:
                product_with_rolls = p
                break
    
    if not product_with_rolls:
        runner.log("No products with rolls found, skipping roll picker tests", "WARN")
    else:
        runner.log(f"Using product: {product_with_rolls.get('name')} (roll_count: {product_with_rolls.get('roll_count')})", "INFO")
        
        # Test GET /api/inventory/rolls/available with all_entities=true
        runner.log("\nTesting GET /api/inventory/rolls/available...", "INFO")
        success, rolls_data = runner.test(
            "GET inventory/rolls/available (all_entities=true)",
            "GET",
            "inventory/rolls/available",
            200,
            params={
                "product_id": product_with_rolls['id'],
                "all_entities": "true",
                "sort": "fefo",
                "skip": 0,
                "limit": 8
            },
            token=runner.admin_token,
            check_response=lambda r: (
                'items' in r and
                'total' in r and
                isinstance(r['items'], list)
            )
        )
        
        if success and rolls_data:
            items = rolls_data.get('items', [])
            total = rolls_data.get('total', 0)
            runner.log(f"  Found {len(items)} rolls (total: {total})", "INFO")
            
            if len(items) > 0:
                roll = items[0]
                runner.log(f"  Sample roll: {roll.get('roll_no')} - {roll.get('length_remaining')} {roll.get('unit')}", "INFO")
                
                # Check required fields
                required_fields = ['id', 'roll_no', 'length_remaining', 'owner_entity_id', 'owner_entity_name', 'warehouse_name', 'lot']
                missing = [f for f in required_fields if f not in roll]
                if not missing:
                    runner.log("  Roll has all required fields ✓", "PASS")
                    runner.tests_passed += 1
                else:
                    runner.log(f"  Missing fields: {missing}", "FAIL")
                    runner.failures.append(f"Roll missing fields: {missing}")
                    runner.tests_failed += 1
                
                # Check is_cross_entity flag
                if 'is_cross_entity' in roll:
                    runner.log(f"  Roll has is_cross_entity flag: {roll.get('is_cross_entity')} ✓", "PASS")
                    runner.tests_passed += 1
                else:
                    runner.log("  Roll missing is_cross_entity flag", "FAIL")
                    runner.failures.append("Roll missing is_cross_entity flag")
                    runner.tests_failed += 1
        
        # Test pagination
        if success and rolls_data and rolls_data.get('total', 0) > 8:
            runner.log("\nTesting pagination (skip=8, limit=8)...", "INFO")
            success, page2 = runner.test(
                "GET inventory/rolls/available (page 2)",
                "GET",
                "inventory/rolls/available",
                200,
                params={
                    "product_id": product_with_rolls['id'],
                    "all_entities": "true",
                    "sort": "fefo",
                    "skip": 8,
                    "limit": 8
                },
                token=runner.admin_token,
                check_response=lambda r: 'items' in r and isinstance(r['items'], list)
            )
            
            if success:
                runner.log(f"  Page 2 has {len(page2.get('items', []))} items ✓", "PASS")

    # ========== FASE C2: ROLL RECONCILIATION API ==========
    print("\n" + "="*70)
    print("FASE C2: ROLL RECONCILIATION API")
    print("="*70)
    
    if product_with_rolls:
        runner.log("Testing POST /api/sales-orders/preview-roll-reconcile...", "INFO")
        
        # Test reconciliation for 50 units
        success, reconcile_data = runner.test(
            "POST sales-orders/preview-roll-reconcile (50 units)",
            "POST",
            "sales-orders/preview-roll-reconcile",
            200,
            data={
                "items": [
                    {
                        "product_id": product_with_rolls['id'],
                        "quantity": 50,
                        "base_quantity": 50
                    }
                ],
                "all_entities": True
            },
            token=runner.admin_token,
            check_response=lambda r: isinstance(r, list) and len(r) > 0
        )
        
        if success and reconcile_data:
            rec = reconcile_data[0]
            runner.log(f"  Reconciliation result for product: {rec.get('product_id')}", "INFO")
            
            # Check options
            options = rec.get('options', {})
            if options:
                runner.log(f"  Available options: {list(options.keys())}", "INFO")
                
                # Check for expected option types
                expected_options = ['exact_whole', 'round_up', 'round_down', 'exact_cut', 'take_all']
                found_options = [opt for opt in expected_options if opt in options]
                
                if found_options:
                    runner.log(f"  Found {len(found_options)} reconciliation options ✓", "PASS")
                    runner.tests_passed += 1
                    
                    # Check first option structure
                    first_opt_key = found_options[0]
                    first_opt = options[first_opt_key]
                    
                    required_opt_fields = ['total_qty', 'roll_count', 'roll_lines', 'snapshot']
                    missing_opt = [f for f in required_opt_fields if f not in first_opt]
                    
                    if not missing_opt:
                        runner.log(f"  Option '{first_opt_key}' has all required fields ✓", "PASS")
                        runner.tests_passed += 1
                        runner.log(f"    total_qty: {first_opt.get('total_qty')}, roll_count: {first_opt.get('roll_count')}", "INFO")
                    else:
                        runner.log(f"  Option missing fields: {missing_opt}", "FAIL")
                        runner.failures.append(f"Reconciliation option missing fields: {missing_opt}")
                        runner.tests_failed += 1
                else:
                    runner.log("  No valid reconciliation options found", "FAIL")
                    runner.failures.append("No valid reconciliation options")
                    runner.tests_failed += 1
            else:
                runner.log("  No options in reconciliation response", "FAIL")
                runner.failures.append("No options in reconciliation response")
                runner.tests_failed += 1

    # ========== FASE D: INVENTORY DISPLAY (via products endpoint) ==========
    print("\n" + "="*70)
    print("FASE D: INVENTORY DISPLAY")
    print("="*70)
    
    runner.log("Verifying products endpoint returns global totals only...", "INFO")
    
    if products:
        sample_product = products[0]
        runner.log(f"Sample product: {sample_product.get('name')}", "INFO")
        
        # Check that product has global totals
        has_global_fields = all(f in sample_product for f in ['available_qty', 'roll_count'])
        
        if has_global_fields:
            runner.log(f"  Product has global fields: available_qty={sample_product.get('available_qty')}, roll_count={sample_product.get('roll_count')} ✓", "PASS")
            runner.tests_passed += 1
        else:
            runner.log("  Product missing global inventory fields", "FAIL")
            runner.failures.append("Product missing global inventory fields")
            runner.tests_failed += 1

    # ========== REGRESSION: CREATE SO WITH ROLL MODE ==========
    print("\n" + "="*70)
    print("REGRESSION: CREATE SO WITH ROLL MODE")
    print("="*70)
    
    if product_with_rolls:
        runner.log("Testing POST /api/sales-orders with roll mode...", "INFO")
        
        # Get rolls for the product
        success, rolls_for_so = runner.test(
            "GET rolls for SO creation",
            "GET",
            "inventory/rolls/available",
            200,
            params={
                "product_id": product_with_rolls['id'],
                "all_entities": "true",
                "sort": "fefo",
                "skip": 0,
                "limit": 2
            },
            token=runner.admin_token
        )
        
        if success and rolls_for_so and len(rolls_for_so.get('items', [])) > 0:
            roll = rolls_for_so['items'][0]
            
            # Get a customer
            success, customers = runner.test(
                "GET customers for SO test",
                "GET",
                "customers",
                200,
                token=runner.admin_token
            )
            
            if success and customers and len(customers) > 0:
                customer = customers[0]
                addresses = customer.get('addresses', [])
                shipping_address_id = addresses[0]['id'] if addresses else None
                
                # Create SO with roll mode
                so_data = {
                    "customer_id": customer['id'],
                    "shipping_address_id": shipping_address_id,
                    "allow_backorder": True,
                    "confirm_mixed_lot": True,
                    "items": [
                        {
                            "product_id": product_with_rolls['id'],
                            "quantity": float(roll.get('length_remaining', 10)),
                            "unit": product_with_rolls.get('base_unit', 'meter'),
                            "purchase_mode": "roll",
                            "roll_lines": [
                                {
                                    "roll_id": roll['id'],
                                    "take_qty": float(roll.get('length_remaining', 10))
                                }
                            ]
                        }
                    ]
                }
                
                success, so = runner.test(
                    "POST sales-orders (with roll mode)",
                    "POST",
                    "sales-orders",
                    200,
                    data=so_data,
                    token=runner.admin_token,
                    check_response=lambda r: (
                        'number' in r and
                        'items' in r and
                        len(r['items']) > 0 and
                        r['items'][0].get('purchase_mode') == 'roll'
                    )
                )
                
                if success and so:
                    runner.log(f"  Created SO: {so.get('number')}", "INFO")
                    item = so['items'][0]
                    
                    # Verify roll mode fields
                    if item.get('purchase_mode') == 'roll':
                        runner.log("  Item has purchase_mode='roll' ✓", "PASS")
                        runner.tests_passed += 1
                    
                    if 'roll_lines' in item:
                        runner.log(f"  Item has roll_lines: {len(item.get('roll_lines', []))} rolls ✓", "PASS")
                        runner.tests_passed += 1
                    
                    if 'reserved_qty' in item:
                        runner.log(f"  Item has reserved_qty: {item.get('reserved_qty')} ✓", "PASS")
                        runner.tests_passed += 1

    # Print summary
    runner.print_summary()
    
    return 0 if runner.tests_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
