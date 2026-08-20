"""R3 — Backend API Testing for Inventory ownership/location + regrade + cross-entity transfer.

Tests:
  1. POST /api/sales-returns/{id}/settle with return_warehouse_id → quarantine rolls with owner/location separation
  2. GET /api/sales-returns/{id}/quarantine → enriched data (owner_entity_name, warehouse_name, product_name, sku)
  3. POST /api/sales-returns/{id}/quarantine/release with regrade → roll status, grade, regraded_from
  4. POST /api/sales-returns/{id}/rolls/{roll_id}/transfer-ownership → owner changes, warehouse stays, JE posted
  5. Guards: transfer on quarantine roll → 400, transfer to same owner → 400
  6. Dashboard integrity: metrics.available_qty == Σ /api/inventory/balances available_qty
"""
import os
import sys
import requests

API = os.environ.get("REACT_APP_BACKEND_URL", "https://return-reconcile-r3.preview.emergentagent.com") + "/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {extra}")


def login():
    print("\n[AUTH] Logging in as admin...")
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    token = r.json()["token"]
    print(f"  ✅ Login successful")
    return {"Authorization": f"Bearer {token}"}


def get_eligible_orders(h):
    """Get sales orders eligible for returns (confirmed/shipped/done with qty >= 5)."""
    r = requests.get(f"{API}/sales-orders", headers=h, timeout=30)
    orders = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    ok_statuses = {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
    eligible = [
        x for x in orders
        if x.get("status") in ok_statuses
        and any(float(it.get("quantity", 0) or 0) >= 5 for it in (x.get("items") or []))
    ]
    return eligible


def create_return(h, orders, qty=1):
    """Create a return from the first eligible order."""
    for o in orders:
        items = [it for it in o["items"] if float(it.get("quantity", 0) or 0) >= qty]
        if not items:
            continue
        it = items[0]
        r = requests.post(
            f"{API}/sales-returns",
            headers=h,
            timeout=30,
            json={
                "order_id": o["id"],
                "return_type": "retur",
                "items": [
                    {
                        "product_id": it["product_id"],
                        "product_name": it.get("product_name", ""),
                        "quantity_returned": qty,
                        "unit": it.get("unit", "meter"),
                        "reason": "R3 test",
                        "condition": "ok",
                    }
                ],
                "notes": "R3 backend test",
            },
        )
        if r.status_code == 200:
            return r.json()
    return None


def inspect_return(h, return_id, defects):
    """Submit → Approve → Start Inspect → Complete Inspect with 4-point grading."""
    requests.post(f"{API}/sales-returns/{return_id}/submit", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{return_id}/approve", headers=h, json={"notes": ""}, timeout=30)
    requests.post(f"{API}/sales-returns/{return_id}/inspect/start", headers=h, timeout=30)
    return requests.post(
        f"{API}/sales-returns/{return_id}/inspect/complete",
        headers=h,
        timeout=30,
        json={
            "inspections": [
                {"index": 0, "defects": defects, "condition": "ok", "accepted_qty": 1}
            ],
            "notes": "4-point inspection",
        },
    ).json()


def test_settle_with_warehouse(h, orders, warehouses, entities):
    """Test 1: Settle refund with return_warehouse_id → owner/location separation."""
    print("\n[TEST 1] Settle refund → pilih LOKASI gudang; OWNER = entity SO")
    
    ret = create_return(h, orders)
    if not ret:
        check("Create return for test 1", False, "No eligible orders")
        return None
    
    return_id = ret["id"]
    inspect_return(h, return_id, [{"point_value": 1, "count": 2}])  # grade A
    
    # Choose last warehouse as destination (likely different from default)
    dest_wh = warehouses[-1]["id"]
    
    r = requests.post(
        f"{API}/sales-returns/{return_id}/settle",
        headers=h,
        timeout=30,
        json={"outcome": "refund", "return_warehouse_id": dest_wh},
    )
    check("POST /api/sales-returns/{id}/settle → 200", r.status_code == 200, f"Status: {r.status_code}")
    
    if r.status_code != 200:
        return None
    
    settled = r.json()
    check("Status → refund_settled", settled.get("status") == "refund_settled", f"Status: {settled.get('status')}")
    
    so_entity = settled.get("entity_id")
    check("return_warehouse_id saved", settled.get("return_warehouse_id") == dest_wh, f"Got: {settled.get('return_warehouse_id')}")
    check("return_owner_entity_id = entity SO", settled.get("return_owner_entity_id") == so_entity, f"Got: {settled.get('return_owner_entity_id')}")
    
    # Get quarantine rolls
    q_resp = requests.get(f"{API}/sales-returns/{return_id}/quarantine", headers=h, timeout=30)
    check("GET /api/sales-returns/{id}/quarantine → 200", q_resp.status_code == 200, f"Status: {q_resp.status_code}")
    
    quarantine_rolls = q_resp.json() if q_resp.status_code == 200 else []
    check("Quarantine rolls created", isinstance(quarantine_rolls, list) and len(quarantine_rolls) >= 1, f"Got: {len(quarantine_rolls)} rolls")
    
    if not quarantine_rolls:
        return None
    
    roll = quarantine_rolls[0]
    check("roll.warehouse_id = selected location", roll.get("warehouse_id") == dest_wh, f"Got: {roll.get('warehouse_id')}")
    check("roll.owner_entity_id = entity SO", roll.get("owner_entity_id") == so_entity, f"Got: {roll.get('owner_entity_id')}")
    check("Enrichment: owner_entity_name present", bool(roll.get("owner_entity_name")), f"Got: {roll.get('owner_entity_name')}")
    check("Enrichment: warehouse_name present", bool(roll.get("warehouse_name")), f"Got: {roll.get('warehouse_name')}")
    check("Enrichment: product_name present", bool(roll.get("product_name")), f"Got: {roll.get('product_name')}")
    check("Enrichment: sku present", "sku" in roll, f"Got: {roll.get('sku')}")
    
    return {"return_id": return_id, "roll": roll, "so_entity": so_entity, "dest_wh": dest_wh}


def test_regrade_on_release(h, test1_data):
    """Test 2: Release quarantine with regrade A→B."""
    print("\n[TEST 2] Release karantina + REGRADE A→B")
    
    if not test1_data:
        check("Test 2 prerequisite (test 1 data)", False, "Test 1 failed")
        return
    
    return_id = test1_data["return_id"]
    roll = test1_data["roll"]
    
    r = requests.post(
        f"{API}/sales-returns/{return_id}/quarantine/release",
        headers=h,
        timeout=30,
        json={"decisions": [{"roll_id": roll["id"], "action": "release", "grade": "B"}]},
    )
    check("POST /api/sales-returns/{id}/quarantine/release → 200", r.status_code == 200, f"Status: {r.status_code}")
    
    if r.status_code != 200:
        return
    
    released = r.json()
    check("quarantine_released = True", released.get("quarantine_released") is True, f"Got: {released.get('quarantine_released')}")
    
    # Get updated quarantine rolls
    q_resp = requests.get(f"{API}/sales-returns/{return_id}/quarantine", headers=h, timeout=30)
    updated_rolls = q_resp.json() if q_resp.status_code == 200 else []
    updated_roll = next((x for x in updated_rolls if x["id"] == roll["id"]), {})
    
    check("Roll status → available", updated_roll.get("status") == "available", f"Got: {updated_roll.get('status')}")
    check("Grade final = B (regraded)", updated_roll.get("grade") == "B", f"Got: {updated_roll.get('grade')}")
    check("regraded_from = A recorded", updated_roll.get("regraded_from") == "A", f"Got: {updated_roll.get('regraded_from')}")
    
    return updated_roll


def test_cross_entity_transfer(h, test1_data, updated_roll, entities):
    """Test 3: Cross-entity ownership transfer (owner changes, location stays, JE posted)."""
    print("\n[TEST 3] Cross-entity transfer kepemilikan roll retur")
    
    if not test1_data or not updated_roll:
        check("Test 3 prerequisite", False, "Previous tests failed")
        return
    
    return_id = test1_data["return_id"]
    roll_id = updated_roll["id"]
    so_entity = test1_data["so_entity"]
    dest_wh = test1_data["dest_wh"]
    
    # Find different entity
    dest_entity = next((e["id"] for e in entities if e["id"] != so_entity), None)
    check("Different entity available for transfer", bool(dest_entity), f"Entities: {[e['id'] for e in entities]}")
    
    if not dest_entity:
        return
    
    r = requests.post(
        f"{API}/sales-returns/{return_id}/rolls/{roll_id}/transfer-ownership",
        headers=h,
        timeout=30,
        json={"dest_entity_id": dest_entity, "notes": "R3 backend test transfer"},
    )
    check("POST /api/sales-returns/{id}/rolls/{roll_id}/transfer-ownership → 200", r.status_code == 200, f"Status: {r.status_code}, Body: {r.text[:200]}")
    
    if r.status_code != 200:
        return
    
    transfer_result = r.json()
    transferred_roll = transfer_result.get("roll", {})
    
    check("Roll owner_entity_id → dest_entity", transferred_roll.get("owner_entity_id") == dest_entity, f"Got: {transferred_roll.get('owner_entity_id')}")
    check("Roll warehouse_id UNCHANGED", transferred_roll.get("warehouse_id") == dest_wh, f"Got: {transferred_roll.get('warehouse_id')}")
    check("Roll status → available (after transfer)", transferred_roll.get("status") == "available", f"Got: {transferred_roll.get('status')}")
    
    je = transfer_result.get("je", {})
    check("JE inter-company posted", je.get("posted") is True, f"Got: {je.get('posted')}")
    check("JE has pair_id (2 books)", bool(je.get("pair_id")), f"Got: {je.get('pair_id')}")


def test_guard_transfer_quarantine(h, orders, warehouses, entities):
    """Test 4: Guard - transfer roll still in quarantine → 400."""
    print("\n[TEST 4] Guard: transfer roll yang masih 'quarantine' ditolak")
    
    ret = create_return(h, orders)
    if not ret:
        check("Create return for test 4", False, "No eligible orders")
        return
    
    return_id = ret["id"]
    inspect_return(h, return_id, [{"point_value": 1, "count": 2}])
    
    dest_wh = warehouses[-1]["id"]
    requests.post(
        f"{API}/sales-returns/{return_id}/settle",
        headers=h,
        timeout=30,
        json={"outcome": "refund", "return_warehouse_id": dest_wh},
    )
    
    q_resp = requests.get(f"{API}/sales-returns/{return_id}/quarantine", headers=h, timeout=30)
    quarantine_rolls = q_resp.json() if q_resp.status_code == 200 else []
    
    if not quarantine_rolls:
        check("Quarantine roll exists for test 4", False, "No quarantine rolls")
        return
    
    qroll = quarantine_rolls[0]
    so_entity = ret.get("entity_id")
    dest_entity = next((e["id"] for e in entities if e["id"] != so_entity), None)
    
    if not dest_entity:
        check("Different entity for test 4", False, "Only one entity")
        return
    
    r = requests.post(
        f"{API}/sales-returns/{return_id}/rolls/{qroll['id']}/transfer-ownership",
        headers=h,
        timeout=30,
        json={"dest_entity_id": dest_entity},
    )
    check("Transfer quarantine roll → 400", r.status_code == 400, f"Status: {r.status_code}, Body: {r.text[:200]}")


def test_guard_transfer_same_entity(h, orders, warehouses, entities):
    """Test 5: Guard - transfer to same entity → 400."""
    print("\n[TEST 5] Guard: transfer ke entitas pemilik sendiri ditolak")
    
    ret = create_return(h, orders)
    if not ret:
        check("Create return for test 5", False, "No eligible orders")
        return
    
    return_id = ret["id"]
    inspect_return(h, return_id, [{"point_value": 1, "count": 2}])
    
    dest_wh = warehouses[-1]["id"]
    requests.post(
        f"{API}/sales-returns/{return_id}/settle",
        headers=h,
        timeout=30,
        json={"outcome": "refund", "return_warehouse_id": dest_wh},
    )
    
    q_resp = requests.get(f"{API}/sales-returns/{return_id}/quarantine", headers=h, timeout=30)
    quarantine_rolls = q_resp.json() if q_resp.status_code == 200 else []
    
    if not quarantine_rolls:
        check("Quarantine roll exists for test 5", False, "No quarantine rolls")
        return
    
    qroll = quarantine_rolls[0]
    so_entity = ret.get("entity_id")
    
    # Release first to make it available
    requests.post(
        f"{API}/sales-returns/{return_id}/quarantine/release",
        headers=h,
        timeout=30,
        json={"decisions": [{"roll_id": qroll["id"], "action": "release"}]},
    )
    
    # Try to transfer to same entity
    r = requests.post(
        f"{API}/sales-returns/{return_id}/rolls/{qroll['id']}/transfer-ownership",
        headers=h,
        timeout=30,
        json={"dest_entity_id": so_entity},
    )
    check("Transfer to same entity → 400", r.status_code == 400, f"Status: {r.status_code}, Body: {r.text[:200]}")


def test_dashboard_integrity(h):
    """Test 6: Dashboard metrics.available_qty == Σ /api/inventory/balances available_qty."""
    print("\n[TEST 6] Dashboard integrity: metrics == Σ balances")
    
    # Get dashboard metrics
    dash_resp = requests.get(f"{API}/dashboard", headers=h, timeout=30)
    check("GET /api/dashboard → 200", dash_resp.status_code == 200, f"Status: {dash_resp.status_code}")
    
    if dash_resp.status_code != 200:
        return
    
    dashboard = dash_resp.json()
    metrics = dashboard.get("metrics", {})
    dash_available = float(metrics.get("available_qty", 0) or 0)
    dash_reserved = float(metrics.get("reserved_qty", 0) or 0)
    
    # Get inventory balances
    bal_resp = requests.get(f"{API}/inventory/balances", headers=h, timeout=30)
    check("GET /api/inventory/balances → 200", bal_resp.status_code == 200, f"Status: {bal_resp.status_code}")
    
    if bal_resp.status_code != 200:
        return
    
    balances = bal_resp.json()
    bal_items = balances if isinstance(balances, list) else balances.get("items", [])
    
    sum_available = sum(float(b.get("available_qty", 0) or 0) for b in bal_items)
    sum_reserved = sum(float(b.get("reserved_qty", 0) or 0) for b in bal_items)
    
    # Allow small floating point differences
    available_match = abs(dash_available - sum_available) < 0.01
    reserved_match = abs(dash_reserved - sum_reserved) < 0.01
    
    check("metrics.available_qty == Σ balances.available_qty (INV-2)", available_match, f"Dashboard: {dash_available}, Sum: {sum_available}")
    check("metrics.reserved_qty == Σ balances.reserved_qty (INV-3)", reserved_match, f"Dashboard: {dash_reserved}, Sum: {sum_reserved}")


def main():
    print("=" * 60)
    print("R3 Backend API Testing")
    print("=" * 60)
    
    try:
        h = login()
    except Exception as e:
        print(f"❌ Login failed: {e}")
        sys.exit(1)
    
    # Get prerequisite data
    print("\n[SETUP] Loading prerequisite data...")
    try:
        orders = get_eligible_orders(h)
        print(f"  ✅ Found {len(orders)} eligible orders")
        
        ents_resp = requests.get(f"{API}/entities", headers=h, timeout=30)
        entities = ents_resp.json() if isinstance(ents_resp.json(), list) else ents_resp.json().get("items", [])
        print(f"  ✅ Found {len(entities)} entities")
        
        whs_resp = requests.get(f"{API}/warehouses", headers=h, timeout=30)
        warehouses = whs_resp.json() if isinstance(whs_resp.json(), list) else whs_resp.json().get("items", [])
        print(f"  ✅ Found {len(warehouses)} warehouses")
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        sys.exit(1)
    
    if not orders:
        check("Prerequisite: eligible orders", False, "No eligible orders found")
        print("\n" + "=" * 60)
        print(f"RESULTS: PASS={PASS}  FAIL={FAIL}")
        print("=" * 60)
        sys.exit(1)
    
    if len(entities) < 2:
        check("Prerequisite: >= 2 entities", False, f"Only {len(entities)} entity found")
        print("\n" + "=" * 60)
        print(f"RESULTS: PASS={PASS}  FAIL={FAIL}")
        print("=" * 60)
        sys.exit(1)
    
    if not warehouses:
        check("Prerequisite: warehouses", False, "No warehouses found")
        print("\n" + "=" * 60)
        print(f"RESULTS: PASS={PASS}  FAIL={FAIL}")
        print("=" * 60)
        sys.exit(1)
    
    # Run tests
    test1_data = test_settle_with_warehouse(h, orders, warehouses, entities)
    updated_roll = test_regrade_on_release(h, test1_data) if test1_data else None
    test_cross_entity_transfer(h, test1_data, updated_roll, entities)
    test_guard_transfer_quarantine(h, orders, warehouses, entities)
    test_guard_transfer_same_entity(h, orders, warehouses, entities)
    test_dashboard_integrity(h)
    
    print("\n" + "=" * 60)
    print(f"RESULTS: PASS={PASS}  FAIL={FAIL}")
    print("=" * 60)
    
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
