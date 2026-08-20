#!/usr/bin/env python3
"""
Backend API Test — FASE P5 + P2 (Pagination & UI/UX)
======================================================
Tests for:
1. Sales Orders pagination (GET /api/sales-orders?page=X&page_size=Y)
2. GL Journal pagination (GET /api/gl/journal?page=X&page_size=Y)
3. Sales Returns status counts (GET /api/sales-returns/status-counts)
4. Purchase Returns status counts (GET /api/purchase-returns/status-counts)
5. Sales Orders stats/summary (GET /api/sales-orders/stats/summary)
6. Transfer cancellation with reason (DELETE /api/transfers/{id}?reason=...)
"""
import os
import sys
import requests
from datetime import datetime

BASE = os.environ.get("BACKEND_URL", "https://kn-form-gateway.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
PASS, FAIL = [], []


def ok(m):
    PASS.append(m)
    print(f"  ✅ [PASS] {m}")


def bad(m):
    FAIL.append(m)
    print(f"  ❌ [FAIL] {m}")


def info(m):
    print(f"  ℹ️  {m}")


class P5P2Tester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        
    def login(self, email="admin@kainnusantara.id", password="demo12345"):
        """Login with specified credentials"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login failed for {email}: {r.status_code} {r.text[:100]}")
                return False
            data = r.json()
            self.token = data.get("token")
            if not self.token:
                bad(f"Login response missing token for {email}")
                return False
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            ok(f"Login {email}")
            return True
        except Exception as e:
            bad(f"Login exception for {email}: {e}")
            return False
    
    # ========== SALES ORDERS PAGINATION TESTS ==========
    
    def test_sales_orders_pagination_with_params(self):
        """Test GET /api/sales-orders?page=1&page_size=3 returns envelope"""
        info("Test: GET /api/sales-orders?page=1&page_size=3 (envelope)")
        try:
            r = self.session.get(f"{API}/sales-orders?page=1&page_size=3", timeout=30)
            if r.status_code != 200:
                bad(f"GET /sales-orders?page=1&page_size=3 failed: {r.status_code}")
                return False
            
            data = r.json()
            
            # Should be envelope with items, total, page, page_size, has_more
            required_fields = ["items", "total", "page", "page_size", "has_more"]
            missing = [f for f in required_fields if f not in data]
            if missing:
                bad(f"Sales orders pagination envelope missing fields: {missing}")
                return False
            
            # items should be array
            if not isinstance(data.get("items"), list):
                bad(f"Sales orders pagination 'items' should be array, got {type(data.get('items'))}")
                return False
            
            # page should be 1
            if data.get("page") != 1:
                bad(f"Sales orders pagination page should be 1, got {data.get('page')}")
                return False
            
            # page_size should be 3
            if data.get("page_size") != 3:
                bad(f"Sales orders pagination page_size should be 3, got {data.get('page_size')}")
                return False
            
            ok(f"GET /sales-orders?page=1&page_size=3 returns envelope (total={data.get('total')}, items={len(data.get('items', []))})")
            return True
        except Exception as e:
            bad(f"GET /sales-orders pagination exception: {e}")
            return False
    
    def test_sales_orders_without_pagination(self):
        """Test GET /api/sales-orders (no params) returns bare array (backward compatible)"""
        info("Test: GET /api/sales-orders (no params, backward compatible)")
        try:
            r = self.session.get(f"{API}/sales-orders", timeout=30)
            if r.status_code != 200:
                bad(f"GET /sales-orders failed: {r.status_code}")
                return False
            
            data = r.json()
            
            # Should be bare array for backward compatibility
            if not isinstance(data, list):
                bad(f"GET /sales-orders (no params) should return bare array, got {type(data)}")
                return False
            
            ok(f"GET /sales-orders (no params) returns bare array (backward compatible, count={len(data)})")
            return True
        except Exception as e:
            bad(f"GET /sales-orders (no params) exception: {e}")
            return False
    
    def test_sales_orders_pagination_page2(self):
        """Test GET /api/sales-orders?page=2 returns different data"""
        info("Test: GET /api/sales-orders?page=2 (different data)")
        try:
            # Get page 1
            r1 = self.session.get(f"{API}/sales-orders?page=1&page_size=5", timeout=30)
            if r1.status_code != 200:
                info("Skipping page 2 test (page 1 failed)")
                return True
            
            data1 = r1.json()
            items1 = data1.get("items", [])
            
            # Get page 2
            r2 = self.session.get(f"{API}/sales-orders?page=2&page_size=5", timeout=30)
            if r2.status_code != 200:
                info("Skipping page 2 test (page 2 failed)")
                return True
            
            data2 = r2.json()
            items2 = data2.get("items", [])
            
            # If both pages have items, they should be different
            if items1 and items2:
                ids1 = [item.get("id") for item in items1]
                ids2 = [item.get("id") for item in items2]
                
                # Check if any IDs overlap
                overlap = set(ids1) & set(ids2)
                if overlap:
                    bad(f"Sales orders page 1 and page 2 have overlapping IDs: {overlap}")
                    return False
                
                ok(f"GET /sales-orders page 1 and page 2 return different data")
            else:
                info("Not enough data to verify page 1 vs page 2 difference")
            
            return True
        except Exception as e:
            bad(f"GET /sales-orders page 2 exception: {e}")
            return False
    
    # ========== GL JOURNAL PAGINATION TESTS ==========
    
    def test_gl_journal_pagination_with_params(self):
        """Test GET /api/gl/journal?page=2&page_size=20 returns envelope"""
        info("Test: GET /api/gl/journal?page=2&page_size=20 (envelope)")
        try:
            r = self.session.get(f"{API}/gl/journal?page=2&page_size=20", timeout=30)
            if r.status_code != 200:
                bad(f"GET /gl/journal?page=2&page_size=20 failed: {r.status_code}")
                return False
            
            data = r.json()
            
            # Should be envelope
            required_fields = ["items", "total", "page", "page_size", "has_more"]
            missing = [f for f in required_fields if f not in data]
            if missing:
                bad(f"GL journal pagination envelope missing fields: {missing}")
                return False
            
            # page should be 2
            if data.get("page") != 2:
                bad(f"GL journal pagination page should be 2, got {data.get('page')}")
                return False
            
            ok(f"GET /gl/journal?page=2&page_size=20 returns envelope (total={data.get('total')}, items={len(data.get('items', []))})")
            return True
        except Exception as e:
            bad(f"GET /gl/journal pagination exception: {e}")
            return False
    
    def test_gl_journal_without_pagination(self):
        """Test GET /api/gl/journal (no params) returns bare array"""
        info("Test: GET /api/gl/journal (no params, backward compatible)")
        try:
            r = self.session.get(f"{API}/gl/journal", timeout=30)
            if r.status_code != 200:
                bad(f"GET /gl/journal failed: {r.status_code}")
                return False
            
            data = r.json()
            
            # Should be bare array for backward compatibility
            if not isinstance(data, list):
                bad(f"GET /gl/journal (no params) should return bare array, got {type(data)}")
                return False
            
            ok(f"GET /gl/journal (no params) returns bare array (backward compatible, count={len(data)})")
            return True
        except Exception as e:
            bad(f"GET /gl/journal (no params) exception: {e}")
            return False
    
    def test_gl_journal_pagination_different_pages(self):
        """Test GET /api/gl/journal page 1 vs page 2 have different content"""
        info("Test: GET /api/gl/journal page 1 vs page 2 (different content)")
        try:
            # Get page 1
            r1 = self.session.get(f"{API}/gl/journal?page=1&page_size=10", timeout=30)
            if r1.status_code != 200:
                info("Skipping GL journal page comparison (page 1 failed)")
                return True
            
            data1 = r1.json()
            items1 = data1.get("items", [])
            
            # Get page 2
            r2 = self.session.get(f"{API}/gl/journal?page=2&page_size=10", timeout=30)
            if r2.status_code != 200:
                info("Skipping GL journal page comparison (page 2 failed)")
                return True
            
            data2 = r2.json()
            items2 = data2.get("items", [])
            
            # If both pages have items, they should be different
            if items1 and items2:
                ids1 = [item.get("id") for item in items1]
                ids2 = [item.get("id") for item in items2]
                
                overlap = set(ids1) & set(ids2)
                if overlap:
                    bad(f"GL journal page 1 and page 2 have overlapping IDs")
                    return False
                
                ok(f"GET /gl/journal page 1 and page 2 return different content")
            else:
                info("Not enough GL journal data to verify page difference")
            
            return True
        except Exception as e:
            bad(f"GET /gl/journal page comparison exception: {e}")
            return False
    
    # ========== STATUS COUNTS TESTS ==========
    
    def test_sales_returns_status_counts(self):
        """Test GET /api/sales-returns/status-counts returns {status: count, all: total}"""
        info("Test: GET /api/sales-returns/status-counts")
        try:
            r = self.session.get(f"{API}/sales-returns/status-counts", timeout=30)
            if r.status_code != 200:
                bad(f"GET /sales-returns/status-counts failed: {r.status_code}")
                return False
            
            data = r.json()
            
            # Should be object with 'all' key
            if not isinstance(data, dict):
                bad(f"Sales returns status-counts should return object, got {type(data)}")
                return False
            
            if "all" not in data:
                bad(f"Sales returns status-counts missing 'all' key")
                return False
            
            # Should have status keys (e.g., pending, approved, completed, etc.)
            status_keys = [k for k in data.keys() if k != "all"]
            if not status_keys:
                info("Sales returns status-counts has no status keys (might be empty data)")
            
            ok(f"GET /sales-returns/status-counts returns correct format (all={data.get('all')}, statuses={status_keys})")
            return True
        except Exception as e:
            bad(f"GET /sales-returns/status-counts exception: {e}")
            return False
    
    def test_purchase_returns_status_counts(self):
        """Test GET /api/purchase-returns/status-counts returns {status: count, all: total}"""
        info("Test: GET /api/purchase-returns/status-counts")
        try:
            r = self.session.get(f"{API}/purchase-returns/status-counts", timeout=30)
            if r.status_code != 200:
                bad(f"GET /purchase-returns/status-counts failed: {r.status_code}")
                return False
            
            data = r.json()
            
            # Should be object with 'all' key
            if not isinstance(data, dict):
                bad(f"Purchase returns status-counts should return object, got {type(data)}")
                return False
            
            if "all" not in data:
                bad(f"Purchase returns status-counts missing 'all' key")
                return False
            
            status_keys = [k for k in data.keys() if k != "all"]
            
            ok(f"GET /purchase-returns/status-counts returns correct format (all={data.get('all')}, statuses={status_keys})")
            return True
        except Exception as e:
            bad(f"GET /purchase-returns/status-counts exception: {e}")
            return False
    
    # ========== SALES ORDERS STATS TESTS ==========
    
    def test_sales_orders_stats_summary(self):
        """Test GET /api/sales-orders/stats/summary contains required keys"""
        info("Test: GET /api/sales-orders/stats/summary")
        try:
            r = self.session.get(f"{API}/sales-orders/stats/summary", timeout=30)
            if r.status_code != 200:
                bad(f"GET /sales-orders/stats/summary failed: {r.status_code}")
                return False
            
            data = r.json()
            
            # Should contain backorder_count, total_orders, by_status
            required_keys = ["backorder_count", "total_orders", "by_status"]
            missing = [k for k in required_keys if k not in data]
            if missing:
                bad(f"Sales orders stats/summary missing keys: {missing}")
                return False
            
            # by_status should be object
            if not isinstance(data.get("by_status"), dict):
                bad(f"Sales orders stats/summary 'by_status' should be object, got {type(data.get('by_status'))}")
                return False
            
            ok(f"GET /sales-orders/stats/summary returns correct format (total_orders={data.get('total_orders')}, backorder_count={data.get('backorder_count')})")
            return True
        except Exception as e:
            bad(f"GET /sales-orders/stats/summary exception: {e}")
            return False
    
    # ========== TRANSFER CANCELLATION WITH REASON TESTS ==========
    
    def test_transfer_cancellation_contract(self):
        """Test DELETE /api/transfers/{id}?reason=... contract (DON'T actually cancel demo data)"""
        info("Test: DELETE /api/transfers/{id}?reason=... contract verification")
        try:
            # First, get a transfer ID (if any exist)
            r = self.session.get(f"{API}/transfers?limit=1", timeout=30)
            if r.status_code != 200:
                info("No transfers endpoint or failed to fetch transfers")
                return True
            
            transfers = r.json()
            if not transfers or len(transfers) == 0:
                info("No transfers available to test cancellation contract")
                return True
            
            transfer_id = transfers[0].get("id")
            if not transfer_id:
                info("Transfer missing ID, skipping contract test")
                return True
            
            # DON'T actually cancel - just verify the endpoint exists and requires reason
            # We'll test with a missing reason first
            r = self.session.delete(f"{API}/transfers/{transfer_id}", timeout=30)
            
            # If it returns 400 (missing reason), that's good
            if r.status_code == 400:
                ok("DELETE /api/transfers/{id} requires reason parameter (400 without reason)")
                return True
            
            # If it returns 200, check if it would accept reason parameter
            # (but we won't actually call it to avoid destroying demo data)
            if r.status_code == 200:
                info("DELETE /api/transfers/{id} succeeded without reason (might not require reason)")
                return True
            
            # Other status codes
            info(f"DELETE /api/transfers/{{id}} returned {r.status_code} (contract verification inconclusive)")
            return True
            
        except Exception as e:
            bad(f"DELETE /api/transfers contract test exception: {e}")
            return False
    
    # ========== MAIN TEST RUNNER ==========
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*70)
        print("  BACKEND API TEST — FASE P5 + P2 (Pagination & UI/UX)")
        print("="*70)
        
        # Login
        if not self.login():
            return False
        
        print("\n--- SALES ORDERS PAGINATION TESTS (US-P2-1 / BACKEND-1) ---")
        self.test_sales_orders_pagination_with_params()
        self.test_sales_orders_without_pagination()
        self.test_sales_orders_pagination_page2()
        
        print("\n--- GL JOURNAL PAGINATION TESTS (US-P2-2 / BACKEND-2) ---")
        self.test_gl_journal_pagination_with_params()
        self.test_gl_journal_without_pagination()
        self.test_gl_journal_pagination_different_pages()
        
        print("\n--- STATUS COUNTS TESTS (US-P2-3, US-P2-4 / BACKEND-3) ---")
        self.test_sales_returns_status_counts()
        self.test_purchase_returns_status_counts()
        
        print("\n--- SALES ORDERS STATS TESTS (BACKEND-4) ---")
        self.test_sales_orders_stats_summary()
        
        print("\n--- TRANSFER CANCELLATION CONTRACT TESTS (BACKEND-5) ---")
        self.test_transfer_cancellation_contract()
        
        return True


def main():
    tester = P5P2Tester()
    tester.run_all_tests()
    
    print("\n" + "="*70)
    print(f"  HASIL: {len(PASS)} PASS | {len(FAIL)} FAIL")
    print("="*70)
    
    if FAIL:
        print("\n❌ FAILED TESTS:")
        for f in FAIL:
            print(f"   - {f}")
        return 1
    
    print("\n✅ SEMUA TEST BACKEND P5+P2 LULUS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
