"""
P2 Backend Pagination Testing — OPT-IN Contract Verification

Tests backward compatibility + new pagination envelope for:
- /api/inventory/rolls
- /api/inventory/movements
- /api/purchase-orders
- /api/vendor-bills (+ /status-counts)
- /api/suppliers
- /api/customers
- /api/purchase-returns
- /api/sales-returns
- /api/audit-logs

Contract: WITHOUT ?page/?page_size → original shape (bare array or {items,total})
          WITH ?page/?page_size → envelope {items, total, page, page_size, has_more}
"""
import requests
import sys
from typing import Dict, Any, List

BASE_URL = "https://inventory-perf-2.preview.emergentagent.com"

class PaginationTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def log(self, msg: str, level: str = "INFO"):
        prefix = "✅" if level == "PASS" else "❌" if level == "FAIL" else "🔍"
        print(f"{prefix} {msg}")

    def test(self, name: str, condition: bool, details: str = ""):
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log(f"PASS: {name}", "PASS")
        else:
            self.tests_failed += 1
            self.failures.append(f"{name}: {details}")
            self.log(f"FAIL: {name} - {details}", "FAIL")
        return condition

    def login(self) -> bool:
        """Login and get token"""
        self.log("Logging in as admin@kainnusantara.id...")
        try:
            resp = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": "admin@kainnusantara.id", "password": "demo12345"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("token")
                if self.token:
                    self.log(f"Login successful, token: {self.token[:20]}...")
                    return True
            self.log(f"Login failed: {resp.status_code} - {resp.text}", "FAIL")
            return False
        except Exception as e:
            self.log(f"Login error: {e}", "FAIL")
            return False

    def get(self, endpoint: str, params: Dict[str, Any] = None) -> tuple:
        """Make GET request, return (status, data)"""
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            resp = requests.get(f"{BASE_URL}{endpoint}", headers=headers, params=params, timeout=15)
            return resp.status_code, resp.json() if resp.status_code == 200 else resp.text
        except Exception as e:
            return 0, str(e)

    def test_endpoint_backward_compat(self, endpoint: str, expected_shape: str = "array"):
        """Test endpoint WITHOUT pagination params returns original shape"""
        self.log(f"\n📋 Testing {endpoint} (backward compatibility - no pagination)")
        status, data = self.get(endpoint)
        
        if not self.test(f"{endpoint} - responds 200", status == 200, f"Got {status}"):
            return False
        
        if expected_shape == "array":
            is_array = isinstance(data, list)
            self.test(f"{endpoint} - returns bare array", is_array, 
                     f"Expected list, got {type(data).__name__}")
            if is_array:
                self.log(f"   Array length: {len(data)}")
            return is_array
        elif expected_shape == "object_with_items":
            is_obj = isinstance(data, dict) and "items" in data and "total" in data
            self.test(f"{endpoint} - returns {{items, total}}", is_obj,
                     f"Expected dict with items/total, got {type(data).__name__} with keys {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
            if is_obj:
                self.log(f"   Items: {len(data['items'])}, Total: {data['total']}")
            return is_obj
        return False

    def test_endpoint_pagination(self, endpoint: str, page: int = 1, page_size: int = 5):
        """Test endpoint WITH pagination params returns envelope"""
        self.log(f"\n📋 Testing {endpoint} (with pagination ?page={page}&page_size={page_size})")
        status, data = self.get(endpoint, {"page": page, "page_size": page_size})
        
        if not self.test(f"{endpoint} - responds 200", status == 200, f"Got {status}"):
            return False
        
        # Check envelope structure
        is_envelope = isinstance(data, dict)
        self.test(f"{endpoint} - returns dict", is_envelope, f"Got {type(data).__name__}")
        
        if not is_envelope:
            return False
        
        # Check required fields
        required = ["items", "total", "page", "page_size", "has_more"]
        for field in required:
            self.test(f"{endpoint} - has '{field}'", field in data, f"Missing field: {field}")
        
        # Check types
        if "items" in data:
            self.test(f"{endpoint} - items is list", isinstance(data["items"], list),
                     f"items is {type(data['items']).__name__}")
            self.log(f"   Items count: {len(data['items'])}")
        
        if "total" in data:
            self.test(f"{endpoint} - total is int", isinstance(data["total"], int),
                     f"total is {type(data['total']).__name__}")
            self.log(f"   Total: {data['total']}")
        
        if "page" in data:
            self.test(f"{endpoint} - page is int", isinstance(data["page"], int),
                     f"page is {type(data['page']).__name__}")
            self.test(f"{endpoint} - page equals {page}", data["page"] == page,
                     f"Expected {page}, got {data['page']}")
        
        if "page_size" in data:
            self.test(f"{endpoint} - page_size is int", isinstance(data["page_size"], int),
                     f"page_size is {type(data['page_size']).__name__}")
            self.test(f"{endpoint} - page_size equals {page_size}", data["page_size"] == page_size,
                     f"Expected {page_size}, got {data['page_size']}")
        
        if "has_more" in data:
            self.test(f"{endpoint} - has_more is bool", isinstance(data["has_more"], bool),
                     f"has_more is {type(data['has_more']).__name__}")
            self.log(f"   Has more: {data['has_more']}")
        
        return True

    def test_endpoint_search(self, endpoint: str, search_term: str):
        """Test endpoint search functionality"""
        self.log(f"\n🔍 Testing {endpoint} (search ?q={search_term})")
        status, data = self.get(endpoint, {"page": 1, "page_size": 20, "q": search_term})
        
        if not self.test(f"{endpoint} - search responds 200", status == 200, f"Got {status}"):
            return False
        
        if isinstance(data, dict) and "items" in data and "total" in data:
            self.log(f"   Search results: {len(data['items'])} items, total: {data['total']}")
            return True
        return False

    def test_vendor_bills_status_counts(self):
        """Test /api/vendor-bills/status-counts endpoint"""
        self.log(f"\n📋 Testing /api/vendor-bills/status-counts")
        status, data = self.get("/api/vendor-bills/status-counts")
        
        if not self.test("/api/vendor-bills/status-counts - responds 200", status == 200, f"Got {status}"):
            return False
        
        is_dict = isinstance(data, dict)
        self.test("/api/vendor-bills/status-counts - returns dict", is_dict,
                 f"Got {type(data).__name__}")
        
        if is_dict:
            self.test("/api/vendor-bills/status-counts - has 'all' key", "all" in data,
                     f"Keys: {list(data.keys())}")
            self.log(f"   Status counts: {data}")
        
        return is_dict

    def test_rolls_product_search(self):
        """Test /api/inventory/rolls search by product name"""
        self.log(f"\n🔍 Testing /api/inventory/rolls (search by product name 'batik')")
        status, data = self.get("/api/inventory/rolls", {"page": 1, "page_size": 10, "q": "batik"})
        
        if not self.test("/api/inventory/rolls - product search responds 200", status == 200, f"Got {status}"):
            return False
        
        if isinstance(data, dict) and "total" in data:
            total = data.get("total", 0)
            self.log(f"   Search 'batik' found {total} rolls")
            # Note: total might be 0 if no batik products exist in seed data
            return True
        return False

    def test_page_size_clamping(self):
        """Test page_size is clamped to max 200"""
        self.log(f"\n📋 Testing page_size clamping (request 500, expect max 200)")
        status, data = self.get("/api/inventory/rolls", {"page": 1, "page_size": 500})
        
        if not self.test("page_size clamping - responds 200", status == 200, f"Got {status}"):
            return False
        
        if isinstance(data, dict) and "page_size" in data:
            actual_size = data["page_size"]
            self.test("page_size clamped to 200", actual_size <= 200,
                     f"Expected ≤200, got {actual_size}")
            self.log(f"   Requested 500, got {actual_size}")
            return True
        return False

    def test_invalid_page_defaults(self):
        """Test invalid page defaults to 1"""
        self.log(f"\n📋 Testing invalid page defaults to 1")
        status, data = self.get("/api/inventory/rolls", {"page": "invalid", "page_size": 10})
        
        if not self.test("invalid page - responds 200", status == 200, f"Got {status}"):
            return False
        
        if isinstance(data, dict) and "page" in data:
            actual_page = data["page"]
            self.test("invalid page defaults to 1", actual_page == 1,
                     f"Expected 1, got {actual_page}")
            return True
        return False

    def run_all_tests(self):
        """Run all pagination tests"""
        print("\n" + "="*80)
        print("P2 BACKEND PAGINATION CONTRACT TESTING")
        print("="*80)
        
        if not self.login():
            print("\n❌ Login failed, cannot proceed with tests")
            return False
        
        # Test backward compatibility (no pagination params)
        print("\n" + "="*80)
        print("PHASE 1: BACKWARD COMPATIBILITY (no ?page/?page_size)")
        print("="*80)
        
        self.test_endpoint_backward_compat("/api/inventory/rolls", "array")
        self.test_endpoint_backward_compat("/api/inventory/movements", "array")
        self.test_endpoint_backward_compat("/api/purchase-orders", "array")
        self.test_endpoint_backward_compat("/api/vendor-bills", "array")
        self.test_endpoint_backward_compat("/api/suppliers", "array")
        self.test_endpoint_backward_compat("/api/customers", "array")
        self.test_endpoint_backward_compat("/api/purchase-returns", "object_with_items")
        self.test_endpoint_backward_compat("/api/sales-returns", "object_with_items")
        self.test_endpoint_backward_compat("/api/audit-logs", "array")
        
        # Test pagination envelope (with pagination params)
        print("\n" + "="*80)
        print("PHASE 2: PAGINATION ENVELOPE (with ?page=1&page_size=5)")
        print("="*80)
        
        self.test_endpoint_pagination("/api/inventory/rolls", 1, 5)
        self.test_endpoint_pagination("/api/inventory/movements", 1, 5)
        self.test_endpoint_pagination("/api/purchase-orders", 1, 5)
        self.test_endpoint_pagination("/api/vendor-bills", 1, 5)
        self.test_endpoint_pagination("/api/suppliers", 1, 5)
        self.test_endpoint_pagination("/api/customers", 1, 5)
        self.test_endpoint_pagination("/api/purchase-returns", 1, 5)
        self.test_endpoint_pagination("/api/sales-returns", 1, 5)
        self.test_endpoint_pagination("/api/audit-logs", 1, 5)
        
        # Test page 2 (different items)
        print("\n" + "="*80)
        print("PHASE 3: PAGE 2 (different items)")
        print("="*80)
        
        self.test_endpoint_pagination("/api/inventory/rolls", 2, 5)
        self.test_endpoint_pagination("/api/purchase-orders", 2, 5)
        
        # Test search functionality
        print("\n" + "="*80)
        print("PHASE 4: SEARCH FUNCTIONALITY (?q=)")
        print("="*80)
        
        self.test_endpoint_search("/api/inventory/rolls", "RL")
        self.test_endpoint_search("/api/customers", "CUST")
        self.test_endpoint_search("/api/suppliers", "SUP")
        self.test_endpoint_search("/api/purchase-orders", "PO")
        self.test_endpoint_search("/api/vendor-bills", "VBILL")
        
        # Test special cases
        print("\n" + "="*80)
        print("PHASE 5: SPECIAL CASES")
        print("="*80)
        
        self.test_vendor_bills_status_counts()
        self.test_rolls_product_search()
        self.test_page_size_clamping()
        self.test_invalid_page_defaults()
        
        # Summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Total tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed} ✅")
        print(f"Failed: {self.tests_failed} ❌")
        
        if self.failures:
            print("\n❌ FAILED TESTS:")
            for i, failure in enumerate(self.failures, 1):
                print(f"  {i}. {failure}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"\nSuccess rate: {success_rate:.1f}%")
        
        return self.tests_failed == 0


def main():
    tester = PaginationTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
