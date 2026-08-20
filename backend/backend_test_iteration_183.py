#!/usr/bin/env python3
"""Backend testing for iteration 183 - Additional FASE F requirements.

Tests:
1. GET /api/inventory/movements?movement_type=sample_issue (new filtering param)
2. GET /api/onboarding for 4 roles (Indonesian localization)
3. Backend regression (main endpoints health check)
"""
import os
import sys
import requests

BASE = os.environ.get("BASE_URL", "https://nusantara-staging-1.preview.emergentagent.com/api")
CREDS = {
    "admin": ("admin@kainnusantara.id", "demo12345"),
    "sales": ("sales@kainnusantara.id", "demo12345"),
    "warehouse": ("warehouse@kainnusantara.id", "demo12345"),
    "manager": ("manager@kainnusantara.id", "demo12345"),
}

PASS = 0
FAIL = 0
FAILURES = []


def ok(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label} :: {extra}")
        print(f"  ❌ {label} — {extra}")


def login(role):
    email, pwd = CREDS[role]
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}, timeout=25)
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("session_token")
    assert tok, f"no token for {role}: {r.text[:200]}"
    return {"Authorization": f"Bearer {tok}"}


def get(h, path, **params):
    return requests.get(f"{BASE}{path}", headers=h, params=params or None, timeout=40)


def test_movement_type_filter(warehouse):
    print("\n=== TEST: GET /api/inventory/movements?movement_type=sample_issue ===")
    
    # Test without filter - should return all movements
    r = get(warehouse, "/inventory/movements")
    ok("GET /inventory/movements (no filter) 200", r.status_code == 200, r.text[:200])
    all_movs = r.json() if r.status_code == 200 else []
    if isinstance(all_movs, dict):
        all_movs = all_movs.get("items", [])
    total_count = len(all_movs)
    ok("movements list not empty", total_count > 0, f"count={total_count}")
    print(f"    · Total movements: {total_count}")
    
    # Test with movement_type=sample_issue filter
    r2 = get(warehouse, "/inventory/movements", movement_type="sample_issue")
    ok("GET /inventory/movements?movement_type=sample_issue 200", r2.status_code == 200, r2.text[:200])
    filtered = r2.json() if r2.status_code == 200 else []
    if isinstance(filtered, dict):
        filtered = filtered.get("items", [])
    
    ok("filtered list contains only sample_issue", 
       all(m.get("movement_type") == "sample_issue" for m in filtered),
       f"types found: {set(m.get('movement_type') for m in filtered)}")
    
    ok("sample_issue count is 1 (per baseline)", len(filtered) == 1, f"count={len(filtered)}")
    
    if filtered:
        sample = filtered[0]
        qty = sample.get("quantity", sample.get("qty"))
        ok("sample_issue has negative quantity", float(qty or 0) == -3.0, f"qty={qty}")
        ok("sample_issue references KSC/SMP-00001", 
           sample.get("source_document") == "KSC/SMP-00001",
           f"ref={sample.get('source_document')}")
        print(f"    · sample_issue: qty={qty}, ref={sample.get('source_document')}")
    
    # Test pagination with filter
    r3 = get(warehouse, "/inventory/movements", movement_type="sample_issue", page=1, page_size=10)
    ok("movement_type filter works with pagination", r3.status_code == 200, r3.text[:200])


def test_onboarding_localization(tokens):
    print("\n=== TEST: GET /api/onboarding - Indonesian localization ===")
    
    forbidden_words = [
        "task queue", "inbound", "outbound", "Advance", "confirmed", "dispatched",
        "Check", "Process", "Complete", "Create", "first", "next stage"
    ]
    
    for role in ["admin", "sales", "warehouse", "manager"]:
        r = get(tokens[role], "/onboarding")
        ok(f"GET /onboarding ({role}) 200", r.status_code == 200, r.text[:200])
        
        if r.status_code != 200:
            continue
            
        data = r.json()
        text = str(data).lower()
        
        # Check for Indonesian phrases
        indonesian_phrases = [
            "cek", "proses", "lanjutkan", "buat", "selesaikan", "tugas", 
            "barang masuk", "barang keluar", "pesanan", "terkirim", "terkonfirmasi"
        ]
        has_indonesian = any(phrase in text for phrase in indonesian_phrases)
        ok(f"onboarding ({role}) contains Indonesian text", has_indonesian, 
           f"sample: {text[:150]}")
        
        # Check for forbidden English words (except 'Scan' which is allowed)
        found_forbidden = [w for w in forbidden_words if w.lower() in text and "scan" not in w.lower()]
        ok(f"onboarding ({role}) has no forbidden English words", 
           len(found_forbidden) == 0,
           f"found: {found_forbidden}")
        
        print(f"    · {role}: {len(str(data))} chars, Indonesian={has_indonesian}")


def test_backend_regression(admin):
    print("\n=== TEST: Backend regression - main endpoints ===")
    
    endpoints = [
        "/sales-orders",
        "/purchase-orders",
        "/inventory/balances",
        "/inventory/rolls",
        "/inventory/movements",
        "/wms/tasks",
        "/warehouse-transfers",
        "/cycle-count/sessions",
        "/uom-conversions/catalog",
        "/uom-conversions/rules",
        "/uom-conversions/usage",
        "/purchase-returns",
        "/products",
        "/onboarding",
        "/rnd/meta",
        "/rnd/specs",
        "/rnd/samples",
        "/supplier-contracts",
        "/documents/ref-types",
    ]
    
    for endpoint in endpoints:
        r = get(admin, endpoint)
        ok(f"GET {endpoint} returns 200", r.status_code == 200, 
           f"status={r.status_code} {r.text[:100]}")
        
        if r.status_code == 200:
            data = r.json()
            has_data = bool(data)
            if isinstance(data, dict):
                has_data = bool(data.get("items") or data.get("types") or data.get("rules") or 
                              data.get("catalog") or data.get("usage") or data.get("policy") or
                              data.get("sessions") or len(data) > 0)
            ok(f"GET {endpoint} returns data", has_data, f"empty response")


def test_data_baseline(admin):
    print("\n=== TEST: Data baseline verification ===")
    
    # Check sales_orders count
    r = get(admin, "/sales-orders")
    if r.status_code == 200:
        orders = r.json()
        if isinstance(orders, dict):
            orders = orders.get("items", [])
        ok("sales_orders count = 9 (baseline)", len(orders) == 9, f"count={len(orders)}")
    
    # Check inventory_movements count
    r = get(admin, "/inventory/movements")
    if r.status_code == 200:
        movements = r.json()
        if isinstance(movements, dict):
            movements = movements.get("items", [])
        ok("inventory_movements count = 39 (baseline)", len(movements) == 39, f"count={len(movements)}")
    
    # Check products count
    r = get(admin, "/products")
    if r.status_code == 200:
        products = r.json()
        if isinstance(products, dict):
            products = products.get("items", [])
        ok("products count = 18 (baseline)", len(products) == 18, f"count={len(products)}")


def main():
    print("=" * 80)
    print("BACKEND TESTING - Iteration 183 - FASE F Additional Requirements")
    print("=" * 80)
    
    tokens = {}
    for role in ["admin", "sales", "warehouse", "manager"]:
        tokens[role] = login(role)
    
    test_movement_type_filter(tokens["warehouse"])
    test_onboarding_localization(tokens)
    test_backend_regression(tokens["admin"])
    test_data_baseline(tokens["admin"])
    
    print("\n" + "=" * 80)
    print(f"RESULTS: PASS {PASS} / FAIL {FAIL}")
    if FAILURES:
        print("\nFAILURES:")
        for f in FAILURES:
            print(f"  · {f}")
    print("=" * 80)
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"\nFATAL ERROR: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
