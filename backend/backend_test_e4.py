#!/usr/bin/env python3
"""
Backend API Test — FASE E-4 (Warehouse Scoping & Entity Pricing)
=================================================================
Comprehensive test covering:
1. E4.1 Warehouse Scoping (shared/dedicated warehouses)
2. E4.7 Entity-specific Pricing (price overrides per entity)
3. Permission tests (role-based access)
4. Data cleanliness (restore demo data after tests)

Based on test_core_e4_poc.py (41/41 passing)
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests

BASE = os.environ.get("BACKEND_URL", "https://kn-entity-scoped.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
PW = "demo12345"
ADMIN = "admin@kainnusantara.id"
SALES_KSC = "sales@kainnusantara.id"      # home ent_ksc
SALES_KANDA = "sales3@kainnusantara.id"   # home ent_kanda
WAREHOUSE = "warehouse@kainnusantara.id"

KSC, KANDA = "ent_ksc", "ent_kanda"
WH_SHARED = "wh_jakarta"        # shared
WH_KSC = "wh_bandung"           # dedicated to KSC
WH_KANDA = "wh_tangerang"       # dedicated to Kanda
WH_SBY = "wh_surabaya"          # shared, contains KSC stock

PROD_TEST = "prod_denim_selvedge"   # not used in demo prices
SKU_TEST = "DNM-BDG-001"
PROD_DEMO_KANDA = "prod_batik_mega"  # has Kanda price from seed

PASS, FAIL = [], []
CLEAN_WAREHOUSES = []
CLEAN_PRICES = []
CLEAN_SESSIONS = []


def ok(m):
    PASS.append(m)
    print(f"  ✅ [PASS] {m}")


def bad(m):
    FAIL.append(m)
    print(f"  ❌ [FAIL] {m}")


def info(m):
    print(f"  ℹ️  {m}")


def login(email: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": PW}, timeout=30)
    if r.status_code != 200:
        bad(f"Login {email}: {r.status_code} {r.text[:200]}")
        return None
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}",
                      "Content-Type": "application/json"})
    ok(f"Login {email}")
    return s


def h(entity: str) -> dict:
    return {"X-Entity-Id": entity}


def guides(resp: requests.Response, *needles: str) -> bool:
    """Check if error message contains guiding text"""
    try:
        detail = (resp.json() or {}).get("detail", "")
    except Exception:
        return False
    if not isinstance(detail, str):
        return False
    return all(n.lower() in detail.lower() for n in needles)


def grid_row(sess: requests.Session, entity_id: str, product_id: str) -> dict:
    r = sess.get(f"{API}/pricelist", params={"entity_id": entity_id}, timeout=60)
    if r.status_code != 200:
        return {}
    for row in r.json().get("rows", []):
        if row["product_id"] == product_id:
            return row
    return {}


# ========== E4.1 WAREHOUSE TESTS ==========

def test_warehouse_visibility(admin, sales_ksc, sales_kanda):
    """Test E4.1.1-2: Warehouse filtering by entity"""
    info("Test: E4.1.1-2 Warehouse visibility per entity")
    
    # Sales KSC should see KSC warehouse, not Kanda warehouse
    a = sales_ksc.get(f"{API}/warehouses", timeout=30)
    if a.status_code != 200:
        bad(f"GET /warehouses failed for sales_ksc: {a.status_code}")
        return False
    
    ids_a = {w["id"] for w in (a.json() or [])}
    if WH_KSC in ids_a and WH_KANDA not in ids_a:
        ok("Sales KSC sees KSC warehouse, not Kanda warehouse")
    else:
        bad(f"Sales KSC warehouse visibility incorrect: {sorted(ids_a)}")
        return False
    
    # Sales Kanda should see Kanda warehouse, not KSC warehouse
    b = sales_kanda.get(f"{API}/warehouses", timeout=30)
    if b.status_code != 200:
        bad(f"GET /warehouses failed for sales_kanda: {b.status_code}")
        return False
    
    ids_b = {w["id"] for w in (b.json() or [])}
    if WH_KANDA in ids_b and WH_KSC not in ids_b:
        ok("Sales Kanda sees Kanda warehouse, not KSC warehouse")
    else:
        bad(f"Sales Kanda warehouse visibility incorrect: {sorted(ids_b)}")
        return False
    
    # Shared warehouse visible to both
    if WH_SHARED in ids_a and WH_SHARED in ids_b:
        ok("Shared warehouse visible to both entities")
    else:
        bad("Shared warehouse not visible to both entities")
        return False
    
    # Admin with scope=all sees all warehouses
    all_r = admin.get(f"{API}/warehouses", params={"scope": "all"},
                      headers=h(KANDA), timeout=30)
    if all_r.status_code != 200:
        bad(f"GET /warehouses?scope=all failed: {all_r.status_code}")
        return False
    
    rows = {w["id"]: w for w in (all_r.json() or [])}
    if len(rows) >= 4:
        ok(f"Admin ?scope=all sees all warehouses ({len(rows)} total)")
    else:
        bad(f"Admin ?scope=all should see at least 4 warehouses, got {len(rows)}")
        return False
    
    # Check usable_by_active flag
    if rows.get(WH_KSC, {}).get("usable_by_active") is False:
        ok("usable_by_active flag correct for KSC warehouse when context is Kanda")
    else:
        bad("usable_by_active flag incorrect")
        return False
    
    return True


def test_warehouse_write_guard(admin, wh_user):
    """Test E4.1.3-4: 403 when using dedicated warehouse of other entity"""
    info("Test: E4.1.3-4 Warehouse write guards")
    
    # Stock opname in Kanda warehouse as KSC user
    r = wh_user.post(f"{API}/cycle-count/sessions", headers=h(KSC),
                     json={"warehouse_id": WH_KANDA, "name": f"test-{uuid.uuid4().hex[:6]}"},
                     timeout=30)
    if r.status_code == 403 and guides(r, "khusus", "pilih gudang lain"):
        ok("Stock opname in other entity's warehouse returns 403 with guidance")
    else:
        bad(f"Stock opname guard failed: {r.status_code} {r.text[:200]}")
        return False
    
    # Transfer to Kanda warehouse as KSC user
    r = wh_user.post(f"{API}/transfers", headers=h(KSC), json={
        "source_warehouse_id": WH_SHARED, "dest_warehouse_id": WH_KANDA,
        "items": [{"product_id": PROD_TEST, "qty": 1}], "notes": "test"}, timeout=30)
    if r.status_code == 403 and guides(r, "khusus"):
        ok("Transfer to other entity's warehouse returns 403 with guidance")
    else:
        bad(f"Transfer guard failed: {r.status_code} {r.text[:200]}")
        return False
    
    # PO with Kanda warehouse as KSC user
    r = admin.post(f"{API}/purchase-orders", headers=h(KSC), json={
        "supplier_name": "Test Supplier", "warehouse_id": WH_KANDA,
        "items": [{"product_id": PROD_TEST, "quantity": 5, "unit_price": 100000}],
    }, timeout=30)
    if r.status_code == 403 and guides(r, "khusus"):
        ok("PO with other entity's warehouse returns 403 with guidance")
    else:
        bad(f"PO guard failed: {r.status_code} {r.text[:200]}")
        return False
    
    # Positive control: shared warehouse should work
    r = wh_user.post(f"{API}/cycle-count/sessions", headers=h(KSC),
                     json={"warehouse_id": WH_SHARED, "name": f"test-{uuid.uuid4().hex[:6]}"},
                     timeout=30)
    if r.status_code in (200, 201):
        ok("Shared warehouse accessible (positive control)")
        if r.json().get("id"):
            CLEAN_SESSIONS.append(r.json()["id"])
    else:
        bad(f"Shared warehouse should be accessible: {r.status_code}")
        return False
    
    return True


def test_dedication_guard(admin):
    """Test E4.1.5: Cannot make warehouse dedicated if it has stock from other entities"""
    info("Test: E4.1.5 Dedication guard (prevent stranding stock)")
    
    # Get occupancy of Surabaya warehouse
    occ = admin.get(f"{API}/warehouses/{WH_SBY}/occupancy", timeout=30)
    if occ.status_code != 200:
        bad(f"GET /warehouses/{{id}}/occupancy failed: {occ.status_code}")
        return False
    
    owners = {o["entity_id"]: o for o in occ.json().get("owners", [])}
    if KSC in owners and owners[KSC]["rolls"] > 0:
        ok(f"Surabaya warehouse occupancy readable: {owners[KSC]['rolls']} rolls from KSC")
    else:
        bad("Surabaya warehouse occupancy incorrect")
        return False
    
    # Try to make it dedicated to Kanda only (should fail - has KSC stock)
    r = admin.patch(f"{API}/warehouses/{WH_SBY}", headers=h(KANDA),
                    json={"data": {"sharing_mode": "dedicated", "entity_ids": [KANDA]}},
                    timeout=30)
    if r.status_code == 409 and guides(r, "roll", "terkurung"):
        ok("Making warehouse dedicated with other entity's stock returns 409 with details")
    else:
        bad(f"Dedication guard failed: {r.status_code} {r.text[:250]}")
        return False
    
    # Include stock owner in entity_ids (should succeed)
    r = admin.patch(f"{API}/warehouses/{WH_SBY}", headers=h(KANDA),
                    json={"data": {"sharing_mode": "dedicated", "entity_ids": [KANDA, KSC]}},
                    timeout=30)
    if r.status_code == 200 and set(r.json().get("entity_ids", [])) == {KANDA, KSC}:
        ok("Making warehouse dedicated with stock owners included succeeds")
    else:
        bad(f"Dedication with owners failed: {r.status_code} {r.text[:200]}")
        return False
    
    # Restore to shared mode
    back = admin.patch(f"{API}/warehouses/{WH_SBY}", headers=h(KANDA),
                       json={"data": {"sharing_mode": "shared", "entity_ids": []}}, timeout=30)
    if back.status_code == 200 and back.json().get("sharing_mode") == "shared":
        ok("Surabaya warehouse restored to shared mode (cleanup)")
    else:
        bad(f"Failed to restore Surabaya warehouse: {back.status_code}")
        return False
    
    return True


def test_new_warehouse_default(admin, sales_ksc):
    """Test E4.1.6: New warehouse defaults to dedicated mode for active entity"""
    info("Test: E4.1.6 New warehouse defaults to dedicated")
    
    code = f"TEST-{uuid.uuid4().hex[:5].upper()}"
    r = admin.post(f"{API}/warehouses", headers=h(KANDA), json={
        "code": code, "name": f"Test Warehouse {code}", "city": "Test City"}, timeout=30)
    
    if r.status_code not in (200, 201):
        bad(f"POST /warehouses failed: {r.status_code} {r.text[:200]}")
        return False
    
    doc = r.json()
    CLEAN_WAREHOUSES.append(doc["id"])
    
    if doc.get("sharing_mode") == "dedicated" and doc.get("entity_ids") == [KANDA]:
        ok(f"New warehouse defaults to dedicated mode for active entity ({code})")
    else:
        bad(f"New warehouse mode incorrect: {doc.get('sharing_mode')}, {doc.get('entity_ids')}")
        return False
    
    # Other entity should not see it
    seen = {w["id"] for w in sales_ksc.get(f"{API}/warehouses", timeout=30).json()}
    if doc["id"] not in seen:
        ok("Other entity does not see new dedicated warehouse")
    else:
        bad("Other entity should not see new dedicated warehouse")
        return False
    
    return True


def test_warehouse_scope_all_permission(admin, sales_ksc):
    """Test E4.1.2: scope=all only for admin/manager/warehouse, not sales"""
    info("Test: E4.1.2 scope=all permission")
    
    # Admin should be able to use scope=all
    r = admin.get(f"{API}/warehouses", params={"scope": "all"}, timeout=30)
    if r.status_code == 200:
        ok("Admin can use scope=all")
    else:
        bad(f"Admin scope=all failed: {r.status_code}")
        return False
    
    # Sales should get 403
    r = sales_ksc.get(f"{API}/warehouses", params={"scope": "all"}, timeout=30)
    if r.status_code == 403:
        ok("Sales cannot use scope=all (403)")
    else:
        bad(f"Sales scope=all should return 403, got {r.status_code}")
        return False
    
    return True


# ========== E4.7 PRICING TESTS ==========

def test_price_isolation(admin, sales_ksc, sales_kanda):
    """Test E4.7.8-9: Same product, different prices per entity"""
    info("Test: E4.7.8-9 Price isolation per entity")
    
    row_kanda = grid_row(admin, KANDA, PROD_DEMO_KANDA)
    row_ksc = grid_row(admin, KSC, PROD_DEMO_KANDA)
    
    if not row_kanda or not row_ksc:
        bad("Failed to get price grid rows")
        return False
    
    # Kanda should have entity price
    if row_kanda.get("entity_price") not in (None, 0) and row_kanda.get("price_source") == "entity":
        ok(f"Kanda uses entity price: {row_kanda.get('entity_price')} (source: entity)")
    else:
        bad(f"Kanda price incorrect: {row_kanda}")
        return False
    
    # KSC should use global price
    if row_ksc.get("entity_price") is None and row_ksc.get("price_source") == "global":
        ok(f"KSC uses global price: {row_ksc.get('effective_price')} (source: global)")
    else:
        bad(f"KSC price incorrect: {row_ksc}")
        return False
    
    # Effective prices should differ
    if row_kanda.get("effective_price") != row_ksc.get("effective_price"):
        ok("Effective prices differ between entities for same product")
    else:
        bad("Effective prices should differ between entities")
        return False
    
    # Grid should have three price columns
    required = ["global_price", "entity_price", "effective_price", "price_source"]
    if all(k in row_kanda for k in required):
        ok("Grid includes all three price columns + source")
    else:
        bad(f"Grid missing price columns: {[k for k in required if k not in row_kanda]}")
        return False
    
    return True


def test_price_lifecycle(admin):
    """Test E4.7.10-12: Set price, schedule price, revert to global"""
    info("Test: E4.7.10-12 Price lifecycle")
    
    before = grid_row(admin, KANDA, PROD_TEST)
    if before.get("entity_price") is not None:
        info(f"Test product already has entity price, cleaning up first")
        admin.delete(f"{API}/pricelist/override/{PROD_TEST}",
                     params={"entity_id": KANDA}, headers=h(KANDA), timeout=30)
        before = grid_row(admin, KANDA, PROD_TEST)
    
    if before.get("entity_price") is None:
        ok(f"Test product starts with global price: {before.get('global_price')}")
    else:
        bad("Test product should start with global price")
        return False
    
    # Set entity price
    r = admin.post(f"{API}/pricelist", headers=h(KANDA), json={
        "product_id": PROD_TEST, "sell_price": 158000, "entity_id": KANDA,
        "valid_from": datetime.now(timezone.utc).date().isoformat(),
        "note": "Test E4.7"}, timeout=30)
    
    if r.status_code not in (200, 201):
        bad(f"POST /pricelist failed: {r.status_code} {r.text[:200]}")
        return False
    
    CLEAN_PRICES.append(r.json()["id"])
    ok("Entity price set successfully")
    
    after = grid_row(admin, KANDA, PROD_TEST)
    if after.get("entity_price") == 158000 and after.get("price_source") == "entity":
        ok("Effective price uses entity price immediately")
    else:
        bad(f"Price not applied: {after}")
        return False
    
    # Set second price (should close first)
    r2 = admin.post(f"{API}/pricelist", headers=h(KANDA), json={
        "product_id": PROD_TEST, "sell_price": 162000, "entity_id": KANDA,
        "valid_from": datetime.now(timezone.utc).date().isoformat(),
        "note": "Test E4.7 revision"}, timeout=30)
    
    if r2.status_code in (200, 201):
        CLEAN_PRICES.append(r2.json()["id"])
        ok("Second price set successfully")
    else:
        bad(f"Second price failed: {r2.status_code}")
        return False
    
    # Check that first price was closed
    recs = admin.get(f"{API}/pricelist/records",
                     params={"product_id": PROD_TEST, "entity_id": KANDA}, timeout=30).json()
    closed = [x for x in recs if x["id"] == CLEAN_PRICES[0] and x.get("valid_until")]
    if closed:
        ok("First price auto-closed when second price set (history preserved)")
    else:
        bad("First price should be auto-closed")
        return False
    
    # Latest price should win
    if grid_row(admin, KANDA, PROD_TEST).get("effective_price") == 162000:
        ok("Latest price wins")
    else:
        bad("Latest price should win")
        return False
    
    # Schedule future price
    start = (datetime.now(timezone.utc) + timedelta(days=20)).date().isoformat()
    r3 = admin.post(f"{API}/pricelist", headers=h(KANDA), json={
        "product_id": PROD_TEST, "sell_price": 175000, "entity_id": KANDA,
        "valid_from": start, "note": "Test E4.7 scheduled"}, timeout=30)
    
    if r3.status_code in (200, 201):
        CLEAN_PRICES.append(r3.json()["id"])
        ok("Scheduled price set successfully")
    else:
        bad(f"Scheduled price failed: {r3.status_code}")
        return False
    
    sched = grid_row(admin, KANDA, PROD_TEST)
    if sched.get("effective_price") == 162000 and sched.get("scheduled_count", 0) >= 1:
        ok("Scheduled price does not affect current price")
    else:
        bad(f"Scheduled price should not affect current: {sched}")
        return False
    
    # Revert to global
    rev = admin.delete(f"{API}/pricelist/override/{PROD_TEST}",
                       params={"entity_id": KANDA}, headers=h(KANDA), timeout=30)
    
    if rev.status_code == 200 and rev.json().get("reverted") is True:
        ok("Revert to global succeeds")
    else:
        bad(f"Revert failed: {rev.status_code} {rev.text[:200]}")
        return False
    
    back = grid_row(admin, KANDA, PROD_TEST)
    if back.get("entity_price") is None and back.get("price_source") == "global":
        ok("Product reverted to global price")
    else:
        bad(f"Product should revert to global: {back}")
        return False
    
    # History should be preserved
    hist = admin.get(f"{API}/pricelist/records",
                     params={"product_id": PROD_TEST, "entity_id": KANDA}, timeout=30).json()
    if len(hist) >= 3:
        ok(f"Price history preserved ({len(hist)} records)")
    else:
        bad(f"Price history should have at least 3 records, got {len(hist)}")
        return False
    
    return True


def test_price_chain(admin, sales_kanda, sales_ksc):
    """Test E4.7.13: Price chain in customer quotes"""
    info("Test: E4.7.13 Price chain in customer quotes")
    
    # Get customers
    try:
        from pymongo import MongoClient
        cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[os.environ.get("DB_NAME", "test_database")]
        cust_kanda = db.customers.find_one({"entity_id": KANDA}, {"_id": 0, "id": 1})
        cust_ksc = db.customers.find_one({"entity_id": KSC}, {"_id": 0, "id": 1})
    except Exception as e:
        info(f"Could not get customers from DB: {e}")
        return True  # Skip test
    
    if not cust_kanda or not cust_ksc:
        info("No demo customers found, skipping price chain test")
        return True
    
    # Quote for Kanda customer
    q1 = sales_kanda.get(f"{API}/customer-prices/quote",
                         params={"customer_id": cust_kanda["id"],
                                 "product_ids": PROD_DEMO_KANDA}, timeout=30)
    
    if q1.status_code != 200:
        bad(f"Customer quote failed: {q1.status_code}")
        return False
    
    p1 = (q1.json().get("prices") or {}).get(PROD_DEMO_KANDA, {})
    if p1.get("source") == "entity":
        ok(f"Kanda customer quote uses entity price ({p1.get('price')})")
    else:
        bad(f"Kanda quote should use entity price: {p1}")
        return False
    
    # Quote for KSC customer (product without override)
    q2 = sales_ksc.get(f"{API}/customer-prices/quote",
                       params={"customer_id": cust_ksc["id"],
                               "product_ids": PROD_TEST}, timeout=30)
    
    if q2.status_code != 200:
        bad(f"KSC customer quote failed: {q2.status_code}")
        return False
    
    p2 = (q2.json().get("prices") or {}).get(PROD_TEST, {})
    if p2.get("source") == "global":
        ok("KSC customer quote uses global price for product without override")
    else:
        bad(f"KSC quote should use global price: {p2}")
        return False
    
    # Quote should include price breakdown
    if p1.get("global_price") is not None and p1.get("entity_price") is not None:
        ok("Quote includes price breakdown (global + entity)")
    else:
        bad("Quote should include price breakdown")
        return False
    
    return True


def test_csv_export_import(admin):
    """Test E4.7.14: CSV export and import"""
    info("Test: E4.7.14 CSV export/import")
    
    # Export CSV
    r = admin.get(f"{API}/pricelist/export",
                  params={"entity_id": KANDA, "only_with_price": True}, timeout=60)
    
    if r.status_code != 200:
        bad(f"CSV export failed: {r.status_code}")
        return False
    
    text = r.text
    if "harga_entitas" in text and "172500" in text:
        ok("CSV export includes entity prices")
    else:
        bad(f"CSV export incorrect: {text[:160]}")
        return False
    
    # Import CSV with Indonesian number format
    csv_text = (
        "sku;nama_produk;harga_global;harga_entitas;berlaku_dari;berlaku_sampai;catatan\n"
        f"{SKU_TEST};Test Product;165.000;171.500;;;Test import\n"
        "BTK-MEGA-002;Batik;185.000;;;;no price - should skip\n"
        "INVALID-SKU;Invalid;1;99.000;;;unknown product\n"
    )
    
    imp = admin.post(f"{API}/pricelist/import", headers=h(KANDA),
                     json={"entity_id": KANDA, "csv_text": csv_text}, timeout=60)
    
    if imp.status_code != 200:
        bad(f"CSV import failed: {imp.status_code} {imp.text[:250]}")
        return False
    
    body = imp.json()
    if body.get("applied") == 1:
        ok("CSV import applied 1 row (skipped rows without price)")
    else:
        bad(f"CSV import should apply 1 row, got {body.get('applied')}")
        return False
    
    # Check imported price
    row = grid_row(admin, KANDA, PROD_TEST)
    if row.get("entity_price") == 171500:
        ok("Indonesian number format '171.500' parsed correctly as 171500")
    else:
        bad(f"Imported price incorrect: {row.get('entity_price')}")
        return False
    
    # Check that row without price was skipped
    row2 = grid_row(admin, KANDA, "prod_batik_mega_merah")
    if row2.get("entity_price") is None:
        ok("Row without price was skipped (did not clear existing prices)")
    else:
        bad("Row without price should be skipped")
        return False
    
    # Check error reporting
    if any("INVALID-SKU" in e for e in body.get("errors", [])):
        ok("Unknown SKU reported in errors")
    else:
        bad("Unknown SKU should be reported in errors")
        return False
    
    # Clean up imported prices
    for rec in admin.get(f"{API}/pricelist/records",
                         params={"product_id": PROD_TEST, "entity_id": KANDA},
                         timeout=30).json():
        if rec["id"] not in CLEAN_PRICES:
            CLEAN_PRICES.append(rec["id"])
    
    return True


# ========== CLEANUP ==========

def cleanup():
    """Clean up test data"""
    info("Cleaning up test data...")
    
    try:
        from pymongo import MongoClient
        cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[os.environ.get("DB_NAME", "test_database")]
        
        removed = {"warehouses": 0, "entity_prices": 0, "cycle_count_sessions": 0}
        
        for wid in CLEAN_WAREHOUSES:
            removed["warehouses"] += db.warehouses.delete_many({"id": wid}).deleted_count
        
        for pid in CLEAN_PRICES:
            removed["entity_prices"] += db.entity_prices.delete_many({"id": pid}).deleted_count
        
        # Clean up any remaining test prices
        removed["entity_prices"] += db.entity_prices.delete_many(
            {"entity_id": KANDA, "product_id": PROD_TEST}).deleted_count
        
        for sid in CLEAN_SESSIONS:
            removed["cycle_count_sessions"] += db.cycle_count_sessions.delete_many(
                {"id": sid}).deleted_count
        
        ok(f"Cleanup: {removed}")
        return True
    except Exception as e:
        bad(f"Cleanup failed: {e}")
        return False


# ========== MAIN ==========

def main():
    print("\n" + "="*70)
    print("  BACKEND API TEST — FASE E-4")
    print("  Warehouse Scoping & Entity Pricing")
    print("="*70)
    
    # Login
    admin = login(ADMIN)
    sales_ksc = login(SALES_KSC)
    sales_kanda = login(SALES_KANDA)
    wh_user = login(WAREHOUSE)
    
    if not all([admin, sales_ksc, sales_kanda, wh_user]):
        bad("Login failed for one or more users")
        return 1
    
    try:
        print("\n--- E4.1 WAREHOUSE SCOPING TESTS ---")
        test_warehouse_visibility(admin, sales_ksc, sales_kanda)
        test_warehouse_scope_all_permission(admin, sales_ksc)
        test_warehouse_write_guard(admin, wh_user)
        test_dedication_guard(admin)
        test_new_warehouse_default(admin, sales_ksc)
        
        print("\n--- E4.7 ENTITY PRICING TESTS ---")
        test_price_isolation(admin, sales_ksc, sales_kanda)
        test_price_lifecycle(admin)
        test_price_chain(admin, sales_kanda, sales_ksc)
        test_csv_export_import(admin)
        
    finally:
        print("\n--- CLEANUP ---")
        cleanup()
    
    print("\n" + "="*70)
    print(f"  HASIL: {len(PASS)} PASS | {len(FAIL)} FAIL")
    print("="*70)
    
    if FAIL:
        print("\n❌ FAILED TESTS:")
        for f in FAIL:
            print(f"   - {f}")
        return 1
    
    print("\n✅ SEMUA TEST BACKEND LULUS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
