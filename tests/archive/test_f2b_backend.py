"""F2b Backend Testing: Future-aware ATP + Pending SO + Delivery Hold + Regressions"""
import requests
import sys
from typing import Dict, Any, Optional

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

# Test credentials
USERS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "warehouse": {"email": "warehouse@kainnusantara.id", "password": "demo12345"},
    "manager": {"email": "manager@kainnusantara.id", "password": "demo12345"},
    "sales": {"email": "sales@kainnusantara.id", "password": "demo12345"},
}


class TestRunner:
    def __init__(self):
        self.tokens: Dict[str, str] = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def login(self, role: str) -> bool:
        """Login and store token for role"""
        if role in self.tokens:
            return True
        
        user = USERS.get(role)
        if not user:
            print(f"❌ Unknown role: {role}")
            return False
        
        print(f"\n🔐 Logging in as {role}...")
        try:
            resp = requests.post(f"{BASE_URL}/auth/login", json=user, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.tokens[role] = data.get("token", "")
                print(f"✅ Login successful for {role}")
                return True
            else:
                print(f"❌ Login failed for {role}: {resp.status_code}")
                return False
        except Exception as e:
            print(f"❌ Login error for {role}: {e}")
            return False

    def test(self, name: str, method: str, endpoint: str, expected_status: int,
             role: str = "admin", headers: Optional[Dict] = None, 
             data: Optional[Dict] = None, params: Optional[Dict] = None,
             validate_fn=None) -> bool:
        """Run a single test"""
        self.tests_run += 1
        print(f"\n🔍 Test #{self.tests_run}: {name}")
        
        if not self.login(role):
            self.tests_failed += 1
            self.failures.append(f"{name}: Login failed for {role}")
            return False
        
        url = f"{BASE_URL}/{endpoint}"
        req_headers = {"Authorization": f"Bearer {self.tokens[role]}"}
        if headers:
            req_headers.update(headers)
        
        try:
            if method == "GET":
                resp = requests.get(url, headers=req_headers, params=params, timeout=15)
            elif method == "POST":
                resp = requests.post(url, headers=req_headers, json=data, timeout=15)
            else:
                print(f"❌ Unsupported method: {method}")
                self.tests_failed += 1
                return False
            
            status_ok = resp.status_code == expected_status
            if not status_ok:
                print(f"❌ FAILED - Expected {expected_status}, got {resp.status_code}")
                print(f"   Response: {resp.text[:200]}")
                self.tests_failed += 1
                self.failures.append(f"{name}: Status {resp.status_code} != {expected_status}")
                return False
            
            # Additional validation
            if validate_fn and resp.status_code == 200:
                try:
                    result = resp.json()
                    validation_result = validate_fn(result)
                    if validation_result is True:
                        print(f"✅ PASSED - Status {resp.status_code}, validation OK")
                        self.tests_passed += 1
                        return True
                    else:
                        print(f"❌ FAILED - Validation failed: {validation_result}")
                        self.tests_failed += 1
                        self.failures.append(f"{name}: {validation_result}")
                        return False
                except Exception as e:
                    print(f"❌ FAILED - Validation error: {e}")
                    self.tests_failed += 1
                    self.failures.append(f"{name}: Validation error - {e}")
                    return False
            
            print(f"✅ PASSED - Status {resp.status_code}")
            self.tests_passed += 1
            return True
            
        except Exception as e:
            print(f"❌ FAILED - Exception: {e}")
            self.tests_failed += 1
            self.failures.append(f"{name}: Exception - {e}")
            return False

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("📊 TEST SUMMARY")
        print("="*70)
        print(f"Total Tests: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {self.tests_failed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0:.1f}%")
        
        if self.failures:
            print("\n❌ FAILURES:")
            for i, failure in enumerate(self.failures, 1):
                print(f"  {i}. {failure}")
        
        print("="*70)


def main():
    runner = TestRunner()
    
    print("="*70)
    print("🧪 F2b BACKEND TESTING")
    print("="*70)
    
    # ========================================================================
    # F2b BACKEND TESTS
    # ========================================================================
    
    print("\n" + "="*70)
    print("🔬 F2b: Pending SO Board")
    print("="*70)
    
    # Test 1: GET /api/stock/pending-so with X-Entity-Id: all
    def validate_pending_so(data):
        if not isinstance(data, list):
            return "Response is not a list"
        
        # Find SO-0009 with Batik Mega Mendung Premium
        so_0009 = None
        for item in data:
            if item.get("order_number") == "SO-0009":
                so_0009 = item
                break
        
        if not so_0009:
            return "SO-0009 not found in pending SO board"
        
        # Validate SO-0009 fields
        if so_0009.get("customer_name") != "Tekstil Medan Jaya":
            return f"SO-0009 customer mismatch: {so_0009.get('customer_name')}"
        
        if so_0009.get("product_id") != "prod_batik_mega":
            return f"SO-0009 product mismatch: {so_0009.get('product_id')}"
        
        if so_0009.get("backorder_qty") != 200:
            return f"SO-0009 backorder_qty mismatch: {so_0009.get('backorder_qty')}"
        
        if so_0009.get("coverage") != "covered":
            return f"SO-0009 coverage mismatch: {so_0009.get('coverage')}"
        
        if not so_0009.get("promise_date"):
            return "SO-0009 promise_date is empty"
        
        incoming_total = so_0009.get("incoming_total", 0)
        if incoming_total < 200:
            return f"SO-0009 incoming_total too low: {incoming_total}"
        
        print(f"   ✓ SO-0009 found: customer={so_0009.get('customer_name')}, "
              f"product={so_0009.get('sku')}, backorder={so_0009.get('backorder_qty')}, "
              f"coverage={so_0009.get('coverage')}, promise_date={so_0009.get('promise_date')}, "
              f"incoming_total={incoming_total}")
        return True
    
    runner.test(
        "F2b: GET /api/stock/pending-so (admin with X-Entity-Id: all)",
        "GET", "stock/pending-so", 200,
        role="admin",
        headers={"X-Entity-Id": "all"},
        validate_fn=validate_pending_so
    )
    
    # Test 2: GET /api/stock/atp for Batik Mega Mendung
    def validate_atp(data):
        if not isinstance(data, dict):
            return "Response is not a dict"
        
        product_id = data.get("product_id")
        if product_id != "prod_batik_mega":
            return f"Product ID mismatch: {product_id}"
        
        available = data.get("available", 0)
        incoming_list = data.get("incoming", [])
        incoming_in_horizon = data.get("incoming_in_horizon", 0)
        pending_demand = data.get("pending_demand", [])
        pending_total = data.get("pending_total", 0)
        atp_now = data.get("atp_now", 0)
        atp_horizon = data.get("atp_horizon", 0)
        
        # Validate incoming list has PO-00009
        po_found = False
        for po in incoming_list:
            if po.get("po_number") == "PO-00009":
                po_found = True
                if po.get("qty") < 800:
                    return f"PO-00009 qty too low: {po.get('qty')}"
                if not po.get("eta"):
                    return "PO-00009 missing ETA"
                print(f"   ✓ PO-00009 found: qty={po.get('qty')}, eta={po.get('eta')}")
                break
        
        if not po_found:
            return "PO-00009 not found in incoming list"
        
        # Validate pending demand has SO-0009
        so_found = False
        for so in pending_demand:
            if so.get("order_number") == "SO-0009":
                so_found = True
                if so.get("qty") != 200:
                    return f"SO-0009 qty mismatch: {so.get('qty')}"
                print(f"   ✓ SO-0009 found in pending demand: qty={so.get('qty')}")
                break
        
        if not so_found:
            return "SO-0009 not found in pending demand"
        
        # Validate arithmetic: atp_horizon == available + incoming_in_horizon - pending_total
        expected_atp_horizon = available + incoming_in_horizon - pending_total
        if abs(atp_horizon - expected_atp_horizon) > 0.1:
            return (f"ATP arithmetic mismatch: atp_horizon={atp_horizon}, "
                   f"expected={expected_atp_horizon} "
                   f"(available={available} + incoming_in_horizon={incoming_in_horizon} - pending_total={pending_total})")
        
        print(f"   ✓ ATP arithmetic OK: available={available}, incoming_in_horizon={incoming_in_horizon}, "
              f"pending_total={pending_total}, atp_now={atp_now}, atp_horizon={atp_horizon}")
        return True
    
    runner.test(
        "F2b: GET /api/stock/atp?product_id=prod_batik_mega&owner_entity_id=ent_ksc",
        "GET", "stock/atp", 200,
        role="admin",
        params={"product_id": "prod_batik_mega", "owner_entity_id": "ent_ksc"},
        headers={"X-Entity-Id": "all"},
        validate_fn=validate_atp
    )
    
    # Test 3: POST /api/stock/hold with delivery hold_type
    print("\n" + "="*70)
    print("🔬 F2b: Delivery Hold")
    print("="*70)
    
    hold_id = None
    
    def validate_hold_create(data):
        nonlocal hold_id
        if not isinstance(data, dict):
            return "Response is not a dict"
        
        hold_id = data.get("hold_id")
        if not hold_id:
            return "hold_id not returned"
        
        ref = data.get("ref", {})
        if ref.get("hold_type") != "delivery":
            return f"hold_type mismatch: {ref.get('hold_type')}"
        
        moved = data.get("moved", 0)
        if moved != 5:
            return f"moved qty mismatch: {moved}"
        
        print(f"   ✓ Delivery hold created: hold_id={hold_id}, moved={moved}, hold_type={ref.get('hold_type')}")
        return True
    
    runner.test(
        "F2b: POST /api/stock/hold (delivery hold_type)",
        "POST", "stock/hold", 200,
        role="admin",
        data={
            "product_id": "prod_batik_mega",
            "warehouse_id": "wh_jakarta",
            "owner_entity_id": "ent_ksc",
            "quantity": 5,
            "reason": "test delivery hold",
            "hold_type": "delivery",
            "ref_type": "sales_order",
            "ref_id": "so_test"
        },
        validate_fn=validate_hold_create
    )
    
    # Test 4: GET /api/stock/holds - verify delivery hold appears
    def validate_holds_list(data):
        if not isinstance(data, list):
            return "Response is not a list"
        
        if not hold_id:
            return "hold_id not set from previous test"
        
        found = False
        for h in data:
            if h.get("ref_id") == hold_id:
                found = True
                if h.get("hold_type") != "delivery":
                    return f"hold_type mismatch in list: {h.get('hold_type')}"
                print(f"   ✓ Delivery hold found in list: hold_id={hold_id}, hold_type={h.get('hold_type')}")
                break
        
        if not found:
            return f"hold_id {hold_id} not found in holds list"
        
        return True
    
    runner.test(
        "F2b: GET /api/stock/holds (verify delivery hold)",
        "GET", "stock/holds", 200,
        role="admin",
        headers={"X-Entity-Id": "all"},
        validate_fn=validate_holds_list
    )
    
    # Test 5: POST /api/stock/hold/{hold_id}/release (cleanup)
    if hold_id:
        runner.test(
            "F2b: POST /api/stock/hold/{hold_id}/release (cleanup)",
            "POST", f"stock/hold/{hold_id}/release", 200,
            role="admin"
        )
    
    # ========================================================================
    # F2 REGRESSION TESTS
    # ========================================================================
    
    print("\n" + "="*70)
    print("🔬 F2 Regression: Stock Buckets")
    print("="*70)
    
    # Test 6: GET /api/stock/buckets
    def validate_buckets(data):
        if not isinstance(data, list):
            return "Response is not a list"
        
        if len(data) == 0:
            return "No products in bucket board"
        
        # Check first product has required fields
        product = data[0]
        required_fields = ["product_id", "product_name", "totals", "warehouses"]
        for field in required_fields:
            if field not in product:
                return f"Missing field: {field}"
        
        totals = product.get("totals", {})
        bucket_fields = ["available_qty", "hold_qty", "wip_qty", "on_hand_qty", "atp_qty"]
        for field in bucket_fields:
            if field not in totals:
                return f"Missing bucket field: {field}"
        
        print(f"   ✓ Bucket board OK: {len(data)} products, sample: {product.get('product_name')}")
        return True
    
    runner.test(
        "F2: GET /api/stock/buckets",
        "GET", "stock/buckets", 200,
        role="admin",
        headers={"X-Entity-Id": "all"},
        validate_fn=validate_buckets
    )
    
    # Test 7: POST /api/stock/hold (general)
    general_hold_id = None
    
    def validate_general_hold(data):
        nonlocal general_hold_id
        general_hold_id = data.get("hold_id")
        if not general_hold_id:
            return "hold_id not returned"
        print(f"   ✓ General hold created: hold_id={general_hold_id}")
        return True
    
    runner.test(
        "F2: POST /api/stock/hold (general)",
        "POST", "stock/hold", 200,
        role="admin",
        data={
            "product_id": "prod_batik_mega",
            "warehouse_id": "wh_jakarta",
            "owner_entity_id": "ent_ksc",
            "quantity": 3,
            "reason": "test general hold"
        },
        validate_fn=validate_general_hold
    )
    
    # Test 8: POST /api/stock/wip/start
    wip_id = None
    
    def validate_wip_start(data):
        nonlocal wip_id
        wip_id = data.get("wip_id")
        if not wip_id:
            return "wip_id not returned"
        print(f"   ✓ WIP started: wip_id={wip_id}")
        return True
    
    runner.test(
        "F2: POST /api/stock/wip/start",
        "POST", "stock/wip/start", 200,
        role="admin",
        data={
            "product_id": "prod_batik_mega",
            "warehouse_id": "wh_jakarta",
            "owner_entity_id": "ent_ksc",
            "quantity": 2,
            "note": "test wip"
        },
        validate_fn=validate_wip_start
    )
    
    # Test 9: POST /api/stock/wip/{wip_id}/complete
    if wip_id:
        runner.test(
            "F2: POST /api/stock/wip/{wip_id}/complete",
            "POST", f"stock/wip/{wip_id}/complete", 200,
            role="admin"
        )
    
    # Test 10: Release general hold (cleanup)
    if general_hold_id:
        runner.test(
            "F2: POST /api/stock/hold/{hold_id}/release (cleanup)",
            "POST", f"stock/hold/{general_hold_id}/release", 200,
            role="admin"
        )
    
    # ========================================================================
    # RBAC REGRESSION TESTS
    # ========================================================================
    
    print("\n" + "="*70)
    print("🔬 RBAC Regression: Permission Tests")
    print("="*70)
    
    # Test 11: warehouse@kainnusantara.id CAN POST /api/stock/hold
    warehouse_hold_id = None
    
    def validate_warehouse_hold(data):
        nonlocal warehouse_hold_id
        warehouse_hold_id = data.get("hold_id")
        if not warehouse_hold_id:
            return "hold_id not returned"
        print(f"   ✓ Warehouse user can create hold: hold_id={warehouse_hold_id}")
        return True
    
    runner.test(
        "RBAC: warehouse@kainnusantara.id CAN POST /api/stock/hold",
        "POST", "stock/hold", 200,
        role="warehouse",
        data={
            "product_id": "prod_batik_mega",
            "warehouse_id": "wh_jakarta",
            "owner_entity_id": "ent_ksc",
            "quantity": 2,
            "reason": "warehouse test hold"
        },
        validate_fn=validate_warehouse_hold
    )
    
    # Cleanup warehouse hold
    if warehouse_hold_id:
        runner.test(
            "RBAC: warehouse release hold (cleanup)",
            "POST", f"stock/hold/{warehouse_hold_id}/release", 200,
            role="warehouse"
        )
    
    # Test 12: manager@kainnusantara.id CAN POST /api/stock/wip/start
    manager_wip_id = None
    
    def validate_manager_wip(data):
        nonlocal manager_wip_id
        manager_wip_id = data.get("wip_id")
        if not manager_wip_id:
            return "wip_id not returned"
        print(f"   ✓ Manager user can start WIP: wip_id={manager_wip_id}")
        return True
    
    runner.test(
        "RBAC: manager@kainnusantara.id CAN POST /api/stock/wip/start",
        "POST", "stock/wip/start", 200,
        role="manager",
        data={
            "product_id": "prod_batik_mega",
            "warehouse_id": "wh_jakarta",
            "owner_entity_id": "ent_ksc",
            "quantity": 2,
            "note": "manager test wip"
        },
        validate_fn=validate_manager_wip
    )
    
    # Cleanup manager wip
    if manager_wip_id:
        runner.test(
            "RBAC: manager complete WIP (cleanup)",
            "POST", f"stock/wip/{manager_wip_id}/complete", 200,
            role="manager"
        )
    
    # Test 13: sales@kainnusantara.id gets 403 on hold operations
    runner.test(
        "RBAC: sales@kainnusantara.id gets 403 on POST /api/stock/hold",
        "POST", "stock/hold", 403,
        role="sales",
        data={
            "product_id": "prod_batik_mega",
            "warehouse_id": "wh_jakarta",
            "owner_entity_id": "ent_ksc",
            "quantity": 1,
            "reason": "sales test hold (should fail)"
        }
    )
    
    # Test 14: sales@kainnusantara.id gets 403 on wip operations
    runner.test(
        "RBAC: sales@kainnusantara.id gets 403 on POST /api/stock/wip/start",
        "POST", "stock/wip/start", 403,
        role="sales",
        data={
            "product_id": "prod_batik_mega",
            "warehouse_id": "wh_jakarta",
            "owner_entity_id": "ent_ksc",
            "quantity": 1,
            "note": "sales test wip (should fail)"
        }
    )
    
    # ========================================================================
    # INV-4/INV-5 FIX REGRESSION TESTS
    # ========================================================================
    
    print("\n" + "="*70)
    print("🔬 INV-4/INV-5 Regression: Entity Scoping Consistency")
    print("="*70)
    
    # Test 15: WITHOUT X-Entity-Id header - consistency check
    def validate_consistency_no_header(data):
        # Get count from list endpoint
        list_resp = requests.get(
            f"{BASE_URL}/sales-orders",
            headers={"Authorization": f"Bearer {runner.tokens['admin']}"},
            timeout=10
        )
        if list_resp.status_code != 200:
            return f"List endpoint failed: {list_resp.status_code}"
        
        list_count = len(list_resp.json())
        
        # Get stats
        stats_resp = requests.get(
            f"{BASE_URL}/sales-orders/stats/summary",
            headers={"Authorization": f"Bearer {runner.tokens['admin']}"},
            timeout=10
        )
        if stats_resp.status_code != 200:
            return f"Stats endpoint failed: {stats_resp.status_code}"
        
        stats_data = stats_resp.json()
        total_orders = stats_data.get("total_orders", 0)
        
        # Calculate active orders from by_status
        by_status = stats_data.get("by_status", {})
        active_statuses = ["reserved", "waiting_approval", "approved", "confirmed", 
                          "waiting_stock", "partially_picked", "picked", "packed", 
                          "partially_shipped", "shipped"]
        active_orders = sum(by_status.get(status, {}).get("count", 0) for status in active_statuses)
        
        print(f"   ✓ WITHOUT header: list_count={list_count}, total_orders={total_orders}, active_orders={active_orders}")
        
        # Consistency check: total_orders should match or be close to list_count
        # (list has limit 200, so if total > 200, list will be capped)
        if total_orders <= 200 and abs(list_count - total_orders) > 0:
            return f"Inconsistency: list_count={list_count} != total_orders={total_orders}"
        
        return True
    
    runner.test(
        "INV-4/INV-5: WITHOUT X-Entity-Id header - consistency check",
        "GET", "sales-orders", 200,
        role="admin",
        validate_fn=validate_consistency_no_header
    )
    
    # Test 16: WITH X-Entity-Id: all header - consistency check
    def validate_consistency_with_header(data):
        # Get count from list endpoint with header
        list_resp = requests.get(
            f"{BASE_URL}/sales-orders",
            headers={"Authorization": f"Bearer {runner.tokens['admin']}", "X-Entity-Id": "all"},
            timeout=10
        )
        if list_resp.status_code != 200:
            return f"List endpoint failed: {list_resp.status_code}"
        
        list_count = len(list_resp.json())
        
        # Get stats with header
        stats_resp = requests.get(
            f"{BASE_URL}/sales-orders/stats/summary",
            headers={"Authorization": f"Bearer {runner.tokens['admin']}", "X-Entity-Id": "all"},
            timeout=10
        )
        if stats_resp.status_code != 200:
            return f"Stats endpoint failed: {stats_resp.status_code}"
        
        stats_data = stats_resp.json()
        total_orders = stats_data.get("total_orders", 0)
        
        # Calculate active orders from by_status
        by_status = stats_data.get("by_status", {})
        active_statuses = ["reserved", "waiting_approval", "approved", "confirmed", 
                          "waiting_stock", "partially_picked", "picked", "packed", 
                          "partially_shipped", "shipped"]
        active_orders = sum(by_status.get(status, {}).get("count", 0) for status in active_statuses)
        
        print(f"   ✓ WITH X-Entity-Id: all: list_count={list_count}, total_orders={total_orders}, active_orders={active_orders}")
        
        # Consistency check
        if total_orders <= 200 and abs(list_count - total_orders) > 0:
            return f"Inconsistency: list_count={list_count} != total_orders={total_orders}"
        
        return True
    
    runner.test(
        "INV-4/INV-5: WITH X-Entity-Id: all header - consistency check",
        "GET", "sales-orders", 200,
        role="admin",
        headers={"X-Entity-Id": "all"},
        validate_fn=validate_consistency_with_header
    )
    
    # ========================================================================
    # SUMMARY
    # ========================================================================
    
    runner.print_summary()
    
    return 0 if runner.tests_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
