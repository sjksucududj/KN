"""
Backend Testing for FASE 4: SO Status 2-level SSOT (STAGE + SUB-STATUS)
Tests stage/sub_status derivation, transition endpoints, guiding 409, and migration script.
"""
import requests
import sys
import subprocess
from typing import Dict, Any, Optional

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

class TestRunner:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.admin_token = None
        self.sales_token = None
        self.manager_token = None
        self.failures = []
        self.test_order_id = None

    def log(self, message: str, level: str = "INFO"):
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "•")
        print(f"{prefix} {message}")

    def test(self, name: str, method: str, endpoint: str, expected_status: int,
             data: Optional[Dict] = None, token: Optional[str] = None,
             headers: Optional[Dict] = None,
             check_response: Optional[callable] = None) -> tuple[bool, Any]:
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}/{endpoint}"
        req_headers = {'Content-Type': 'application/json'}
        if token:
            req_headers['Authorization'] = f'Bearer {token}'
        if headers:
            req_headers.update(headers)

        self.log(f"Test #{self.tests_run}: {name}", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=req_headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=req_headers, timeout=15)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=req_headers, timeout=15)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=req_headers, timeout=15)
            elif method == 'DELETE':
                response = requests.delete(url, headers=req_headers, timeout=15)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            response_data = {}
            try:
                response_data = response.json()
            except Exception:
                pass

            if success:
                # Additional response checks
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
                    self.log(f"  Response: {response_data}", "FAIL")
                self.failures.append(f"{name}: Expected {expected_status}, got {response.status_code}")
                self.tests_failed += 1

            return success, response_data

        except Exception as e:
            self.log(f"  FAILED - Error: {str(e)}", "FAIL")
            self.failures.append(f"{name}: {str(e)}")
            self.tests_failed += 1
            return False, {}

    def login(self, email: str, password: str) -> Optional[str]:
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
            self.log(f"  Login successful, token obtained", "PASS")
            return data['token']
        self.log(f"  Login failed", "FAIL")
        return None

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("TEST SUMMARY - FASE 4")
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
    print("KAIN NUSANTARA - FASE 4 BACKEND TESTING")
    print("SO Status 2-level SSOT: STAGE (parent) + SUB-STATUS (child)")
    print("="*70)
    print()

    # ========== AUTHENTICATION ==========
    print("\n" + "="*70)
    print("PHASE 1: AUTHENTICATION")
    print("="*70)
    
    runner.admin_token = runner.login("admin@kainnusantara.id", "demo12345")
    if not runner.admin_token:
        print("❌ CRITICAL: Admin login failed. Cannot continue.")
        return 1
    
    runner.sales_token = runner.login("sales@kainnusantara.id", "demo12345")
    runner.manager_token = runner.login("manager@kainnusantara.id", "demo12345")

    # ========== FASE 4: MIGRATION SCRIPT IDEMPOTENCY ==========
    print("\n" + "="*70)
    print("PHASE 2: MIGRATION SCRIPT IDEMPOTENCY")
    print("="*70)
    
    runner.log("Running migration script: python scripts/migrate_so_status.py", "INFO")
    try:
        result = subprocess.run(
            ["python", "scripts/migrate_so_status.py"],
            cwd="/app/backend",
            capture_output=True,
            text=True,
            timeout=30
        )
        
        runner.tests_run += 1
        if result.returncode == 0:
            runner.tests_passed += 1
            runner.log("Migration script executed successfully (exit code 0)", "PASS")
            runner.log(f"Output: {result.stdout}", "INFO")
            
            # Check for "MIGRASI BERSIH" in output
            if "MIGRASI BERSIH" in result.stdout and "invalid=0" in result.stdout:
                runner.tests_passed += 1
                runner.log("Migration clean: all SOs have valid stage", "PASS")
            else:
                runner.tests_failed += 1
                runner.log("Migration not clean: some SOs have invalid stage", "FAIL")
                runner.failures.append("Migration script: not clean")
        else:
            runner.tests_failed += 1
            runner.log(f"Migration script failed (exit code {result.returncode})", "FAIL")
            runner.log(f"Error: {result.stderr}", "FAIL")
            runner.failures.append(f"Migration script failed: {result.stderr}")
    except Exception as e:
        runner.tests_run += 1
        runner.tests_failed += 1
        runner.log(f"Migration script error: {str(e)}", "FAIL")
        runner.failures.append(f"Migration script error: {str(e)}")

    # ========== FASE 4: GET /api/sales-orders - STAGE + SUB_STATUS FIELDS ==========
    print("\n" + "="*70)
    print("PHASE 3: GET /api/sales-orders - STAGE + SUB_STATUS")
    print("="*70)
    
    runner.log("Testing GET /api/sales-orders with X-Entity-Id: all", "INFO")
    success, orders = runner.test(
        "GET sales-orders (all entities, verify stage+sub_status)",
        "GET",
        "sales-orders",
        200,
        token=runner.admin_token,
        headers={"X-Entity-Id": "all"},
        check_response=lambda r: (
            isinstance(r, list) and
            len(r) > 0 and
            all('stage' in o and 'sub_status' in o for o in r)
        )
    )
    
    if success and orders:
        runner.log(f"  Found {len(orders)} orders", "INFO")
        runner.log("  All orders have 'stage' and 'sub_status' fields ✓", "PASS")
        
        # Check stage values are valid
        valid_stages = {"Reserved", "Approved", "Confirmed", "Picked", "Shipped", "Delivered", "Cancelled"}
        invalid_stages = [o for o in orders if o.get('stage') not in valid_stages]
        
        if not invalid_stages:
            runner.tests_passed += 1
            runner.log(f"  All stages are valid ✓", "PASS")
        else:
            runner.tests_failed += 1
            runner.log(f"  Found {len(invalid_stages)} orders with invalid stage", "FAIL")
            runner.failures.append(f"Invalid stages found in {len(invalid_stages)} orders")
        
        # Sample orders by status
        runner.log("\n  Sample orders by status:", "INFO")
        status_samples = {}
        for order in orders:
            status = order.get('status')
            if status not in status_samples:
                status_samples[status] = order
        
        for status, order in status_samples.items():
            runner.log(f"    {status} -> stage={order.get('stage')}, sub_status={order.get('sub_status')}", "INFO")

    # ========== FASE 4: STAGE MAPPING CORRECTNESS ==========
    print("\n" + "="*70)
    print("PHASE 4: STAGE MAPPING CORRECTNESS")
    print("="*70)
    
    if orders:
        runner.log("Verifying stage mapping for different statuses...", "INFO")
        
        # Test cases: status -> expected (stage, sub_status_contains)
        test_cases = [
            ("reserved", "Reserved", ["siap_disahkan", "menunggu_validasi"]),
            ("waiting_approval", "Reserved", ["menunggu_approval", "menunggu_validasi"]),
            ("waiting_stock", "Reserved", ["menunggu_stok"]),
            ("approved", "Approved", ["siap_confirm", "menunggu_stok"]),  # depends on backorder
            ("confirmed", "Confirmed", ["siap_pick"]),
            ("shipped", "Shipped", []),
            ("done", "Delivered", []),
            ("cancelled", "Cancelled", ["dibatalkan"]),
        ]
        
        for status, expected_stage, expected_subs in test_cases:
            matching_orders = [o for o in orders if o.get('status') == status]
            if matching_orders:
                order = matching_orders[0]
                actual_stage = order.get('stage')
                actual_subs = order.get('sub_status', [])
                
                runner.tests_run += 1
                if actual_stage == expected_stage:
                    runner.tests_passed += 1
                    runner.log(f"  {status} -> {actual_stage} ✓", "PASS")
                    
                    # Check sub_status
                    if expected_subs:
                        if any(sub in actual_subs for sub in expected_subs):
                            runner.log(f"    sub_status: {actual_subs} (contains expected) ✓", "PASS")
                        else:
                            runner.log(f"    sub_status: {actual_subs} (expected one of {expected_subs})", "WARN")
                else:
                    runner.tests_failed += 1
                    runner.log(f"  {status} -> {actual_stage} (expected {expected_stage}) ❌", "FAIL")
                    runner.failures.append(f"Stage mapping: {status} -> {actual_stage} (expected {expected_stage})")
            else:
                runner.log(f"  No orders with status={status} found", "WARN")

    # ========== FASE 4: GET /api/sales-orders/{id} - SINGLE ORDER ==========
    print("\n" + "="*70)
    print("PHASE 5: GET /api/sales-orders/{id} - SINGLE ORDER")
    print("="*70)
    
    if orders and len(orders) > 0:
        test_order = orders[0]
        runner.test_order_id = test_order['id']
        
        runner.log(f"Testing GET /api/sales-orders/{runner.test_order_id}", "INFO")
        success, order_detail = runner.test(
            "GET sales-orders/{id} (verify stage+sub_status)",
            "GET",
            f"sales-orders/{runner.test_order_id}",
            200,
            token=runner.admin_token,
            check_response=lambda r: (
                'stage' in r and
                'sub_status' in r and
                isinstance(r['sub_status'], list)
            )
        )
        
        if success:
            runner.log(f"  Order {order_detail.get('number')}: stage={order_detail.get('stage')}, sub_status={order_detail.get('sub_status')}", "INFO")

    # ========== FASE 4: TRANSITION ENDPOINTS UPDATE STAGE ==========
    print("\n" + "="*70)
    print("PHASE 6: TRANSITION ENDPOINTS UPDATE STAGE")
    print("="*70)
    
    # Find a waiting_approval order to test approve transition
    waiting_approval_orders = [o for o in orders if o.get('status') == 'waiting_approval']
    
    if waiting_approval_orders:
        test_order = waiting_approval_orders[0]
        runner.log(f"Testing POST /api/sales-orders/{test_order['id']}/approve", "INFO")
        
        success, approved_order = runner.test(
            "POST sales-orders/{id}/approve (verify stage=Approved)",
            "POST",
            f"sales-orders/{test_order['id']}/approve",
            200,
            token=runner.admin_token,
            check_response=lambda r: (
                r.get('status') == 'approved' and
                r.get('stage') == 'Approved'
            )
        )
        
        if success:
            runner.log(f"  After approve: status={approved_order.get('status')}, stage={approved_order.get('stage')}", "PASS")
            
            # Now test confirm transition
            runner.log(f"\nTesting POST /api/sales-orders/{test_order['id']}/confirm", "INFO")
            success, confirmed_order = runner.test(
                "POST sales-orders/{id}/confirm (verify stage=Confirmed)",
                "POST",
                f"sales-orders/{test_order['id']}/confirm",
                200,
                token=runner.admin_token,
                check_response=lambda r: (
                    r.get('status') == 'confirmed' and
                    r.get('stage') == 'Confirmed'
                )
            )
            
            if success:
                runner.log(f"  After confirm: status={confirmed_order.get('status')}, stage={confirmed_order.get('stage')}", "PASS")
    else:
        runner.log("No waiting_approval orders found, skipping transition test", "WARN")

    # ========== FASE 4: BUG POIN 14 - GUIDING 409 ==========
    print("\n" + "="*70)
    print("PHASE 7: BUG POIN 14 - GUIDING 409 (Invalid Transition)")
    print("="*70)
    
    # Find a waiting_stock order to test invalid transition
    waiting_stock_orders = [o for o in orders if o.get('status') == 'waiting_stock']
    
    if waiting_stock_orders:
        test_order = waiting_stock_orders[0]
        runner.log(f"Testing invalid transition: POST /api/sales-orders/{test_order['id']}/approve", "INFO")
        runner.log(f"  Order status: {test_order.get('status')}, stage: {test_order.get('stage')}", "INFO")
        
        success, error_response = runner.test(
            "POST sales-orders/{id}/approve on waiting_stock (should 409 with guiding message)",
            "POST",
            f"sales-orders/{test_order['id']}/approve",
            409,
            token=runner.admin_token,
            check_response=lambda r: (
                isinstance(r, dict) and
                'detail' in r and
                isinstance(r['detail'], dict) and
                r['detail'].get('code') == 'INVALID_TRANSITION' and
                'current_stage' in r['detail'] and
                'current_status' in r['detail'] and
                'allowed_from' in r['detail'] and
                'message' in r['detail']
            )
        )
        
        if success:
            detail = error_response.get('detail', {})
            runner.log(f"  Guiding 409 response:", "PASS")
            runner.log(f"    code: {detail.get('code')}", "INFO")
            runner.log(f"    current_status: {detail.get('current_status')}", "INFO")
            runner.log(f"    current_stage: {detail.get('current_stage')}", "INFO")
            runner.log(f"    allowed_from: {detail.get('allowed_from')}", "INFO")
            runner.log(f"    message: {detail.get('message')}", "INFO")
    else:
        runner.log("No waiting_stock orders found, trying with confirmed order...", "WARN")
        
        # Try with a confirmed order (invalid to approve)
        confirmed_orders = [o for o in orders if o.get('status') == 'confirmed']
        if confirmed_orders:
            test_order = confirmed_orders[0]
            runner.log(f"Testing invalid transition: POST /api/sales-orders/{test_order['id']}/approve", "INFO")
            
            success, error_response = runner.test(
                "POST sales-orders/{id}/approve on confirmed (should 409 with guiding message)",
                "POST",
                f"sales-orders/{test_order['id']}/approve",
                409,
                token=runner.admin_token,
                check_response=lambda r: (
                    isinstance(r, dict) and
                    'detail' in r and
                    isinstance(r['detail'], dict) and
                    r['detail'].get('code') == 'INVALID_TRANSITION'
                )
            )
            
            if success:
                detail = error_response.get('detail', {})
                runner.log(f"  Guiding 409 response received ✓", "PASS")
                runner.log(f"    message: {detail.get('message')}", "INFO")

    # ========== FASE 4: NO 5XX REGRESSIONS ==========
    print("\n" + "="*70)
    print("PHASE 8: NO 5XX REGRESSIONS (SO Lifecycle)")
    print("="*70)
    
    runner.log("Testing SO lifecycle endpoints for 5xx errors...", "INFO")
    
    # Test GET /api/sales-orders
    runner.test(
        "GET sales-orders (no 5xx)",
        "GET",
        "sales-orders",
        200,
        token=runner.admin_token
    )
    
    # Test GET /api/sales-orders/{id}
    if runner.test_order_id:
        runner.test(
            "GET sales-orders/{id} (no 5xx)",
            "GET",
            f"sales-orders/{runner.test_order_id}",
            200,
            token=runner.admin_token
        )
    
    # Test GET /api/sales-orders/stats/summary
    runner.test(
        "GET sales-orders/stats/summary (no 5xx)",
        "GET",
        "sales-orders/stats/summary",
        200,
        token=runner.admin_token
    )

    # ========== PRINT SUMMARY ==========
    runner.print_summary()
    
    return 0 if runner.tests_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
