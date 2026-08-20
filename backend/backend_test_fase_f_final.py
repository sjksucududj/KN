#!/usr/bin/env python3
"""
Backend Test — FASE F Final (Entity Scoping + Localization)
============================================================
Tests:
1. Entity-scoping (F0-C) for 3 fixed endpoints
2. Backend regression - main endpoints return 200
3. Localization - onboarding returns Indonesian labels
"""
import os
import sys
import requests
from typing import Dict, Any, List, Set

BASE = os.environ.get("KN_BASE", "https://wms-inventory-dev.preview.emergentagent.com/api")
PWD = "demo12345"
ENT_A = "ent_ksc"
ENT_B = "ent_kanda"

PASS, FAIL = [], []


def ok(m):
    PASS.append(m)
    print(f"  ✅ [PASS] {m}")


def bad(m):
    FAIL.append(m)
    print(f"  ❌ [FAIL] {m}")


def info(m):
    print(f"  ℹ️  {m}")


def login(email):
    """Login and return token"""
    try:
        r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD}, timeout=30)
        if r.status_code != 200:
            bad(f"Login failed for {email}: {r.status_code}")
            return None
        tok = r.json().get("token") or r.json().get("session_token")
        if not tok:
            bad(f"Login response missing token for {email}")
            return None
        return tok
    except Exception as e:
        bad(f"Login exception for {email}: {e}")
        return None


def get(token, path, params=None, entity_header=None):
    """GET request with auth"""
    h = {"Authorization": f"Bearer {token}"}
    if entity_header:
        h["X-Entity-Id"] = entity_header
    try:
        return requests.get(f"{BASE}{path}", params=params or {}, headers=h, timeout=60)
    except Exception as e:
        bad(f"GET {path} exception: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. Entity-Scoping Tests (F0-C)
# ─────────────────────────────────────────────────────────────────────────────
def test_entity_scoping(tokens: Dict[str, str]):
    """Test entity-scoping for 3 fixed endpoints"""
    print("\n" + "=" * 70)
    print("  1. ENTITY-SCOPING (F0-C) — 3 Fixed Endpoints")
    print("=" * 70)
    
    # Test 1: GET /api/products/{product_id}/purchase-history
    print("\n── 1.1 GET /products/{id}/purchase-history ──")
    # Use a known product that likely has data
    product_id = "prod_batik_mega"  # From seed data
    
    # Sales PT-A (ent_ksc) - should only see PT-A data
    r = get(tokens["sales"], f"/products/{product_id}/purchase-history")
    if r and r.status_code == 200:
        ok(f"sales PT-A → HTTP 200")
        data = r.json()
        events = data.get("events", [])
        info(f"  Found {len(events)} purchase events for PT-A")
    else:
        bad(f"sales PT-A → HTTP {r.status_code if r else 'ERROR'}")
    
    # Sales PT-A requesting PT-B data → should get 403
    r = get(tokens["sales"], f"/products/{product_id}/purchase-history", {"entity_id": ENT_B})
    if r and r.status_code == 403:
        ok(f"sales PT-A requesting entity_id=PT-B → HTTP 403 (anti-IDOR)")
    else:
        bad(f"sales PT-A requesting entity_id=PT-B → HTTP {r.status_code if r else 'ERROR'} (expected 403)")
    
    # Sales PT-A requesting 'all' → should get 200 but only PT-A data
    r = get(tokens["sales"], f"/products/{product_id}/purchase-history", {"entity_id": "all"})
    if r and r.status_code == 200:
        ok(f"sales PT-A requesting entity_id=all → HTTP 200 (non-cross-entity role)")
    else:
        bad(f"sales PT-A requesting entity_id=all → HTTP {r.status_code if r else 'ERROR'}")
    
    # Admin with X-Entity-Id: all → should see both entities
    r = get(tokens["admin"], f"/products/{product_id}/purchase-history", {"entity_id": "all"})
    if r and r.status_code == 200:
        ok(f"admin + entity_id=all → HTTP 200 (cross-entity access)")
        data = r.json()
        events = data.get("events", [])
        info(f"  Admin sees {len(events)} events across all entities")
    else:
        bad(f"admin + entity_id=all → HTTP {r.status_code if r else 'ERROR'}")
    
    # Admin with X-Entity-Id: ent_kanda → should only see PT-B data
    r = get(tokens["admin"], f"/products/{product_id}/purchase-history", entity_header=ENT_B)
    if r and r.status_code == 200:
        ok(f"admin with X-Entity-Id: ent_kanda → HTTP 200")
    else:
        bad(f"admin with X-Entity-Id: ent_kanda → HTTP {r.status_code if r else 'ERROR'}")
    
    # Test 2: GET /api/purchase-returns/source-rolls
    print("\n── 1.2 GET /purchase-returns/source-rolls ──")
    
    # Sales PT-A - should only see PT-A rolls
    r = get(tokens["sales"], "/purchase-returns/source-rolls", {"product_id": product_id})
    if r and r.status_code == 200:
        ok(f"sales PT-A → HTTP 200")
        data = r.json()
        rolls = data.get("rolls", [])
        info(f"  Found {len(rolls)} returnable rolls for PT-A")
    else:
        bad(f"sales PT-A → HTTP {r.status_code if r else 'ERROR'}")
    
    # Sales PT-A requesting PT-B rolls → should get 403
    r = get(tokens["sales"], "/purchase-returns/source-rolls", 
            {"product_id": product_id, "entity_id": ENT_B})
    if r and r.status_code == 403:
        ok(f"sales PT-A requesting entity_id=PT-B → HTTP 403")
    else:
        bad(f"sales PT-A requesting entity_id=PT-B → HTTP {r.status_code if r else 'ERROR'} (expected 403)")
    
    # Admin with entity_id=all → should see both entities
    r = get(tokens["admin"], "/purchase-returns/source-rolls", 
            {"product_id": product_id, "entity_id": "all"})
    if r and r.status_code == 200:
        ok(f"admin + entity_id=all → HTTP 200")
    else:
        bad(f"admin + entity_id=all → HTTP {r.status_code if r else 'ERROR'}")
    
    # Test 3: GET /api/uom-conversions/usage
    print("\n── 1.3 GET /uom-conversions/usage ──")
    
    # Warehouse PT-A - should only see PT-A documents
    r = get(tokens["warehouse"], "/uom-conversions/usage", {"limit": 25})
    if r and r.status_code == 200:
        ok(f"warehouse PT-A → HTTP 200")
        data = r.json()
        usage = data.get("usage", [])
        info(f"  Found {len(usage)} conversion usage records for PT-A")
    else:
        bad(f"warehouse PT-A → HTTP {r.status_code if r else 'ERROR'}")
    
    # Admin with X-Entity-Id: ent_kanda → should only see PT-B documents
    r = get(tokens["admin"], "/uom-conversions/usage", {"limit": 25}, entity_header=ENT_B)
    if r and r.status_code == 200:
        ok(f"admin with X-Entity-Id: ent_kanda → HTTP 200")
    else:
        bad(f"admin with X-Entity-Id: ent_kanda → HTTP {r.status_code if r else 'ERROR'}")
    
    # Admin with X-Entity-Id: all → should see both entities
    r = get(tokens["admin"], "/uom-conversions/usage", {"limit": 25}, entity_header="all")
    if r and r.status_code == 200:
        ok(f"admin with X-Entity-Id: all → HTTP 200")
    else:
        bad(f"admin with X-Entity-Id: all → HTTP {r.status_code if r else 'ERROR'}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Backend Regression Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_backend_regression(token: str):
    """Test main endpoints still return 200 after router changes"""
    print("\n" + "=" * 70)
    print("  2. BACKEND REGRESSION — Main Endpoints")
    print("=" * 70)
    
    endpoints = [
        # Sales
        ("/sales-orders", "Sales Orders"),
        ("/customers", "Customers"),
        # Purchase
        ("/purchase-orders", "Purchase Orders"),
        ("/purchase-returns", "Purchase Returns"),
        ("/suppliers", "Suppliers"),
        # Inventory
        ("/inventory/balances", "Inventory Balances"),
        ("/inventory/rolls", "Inventory Rolls"),
        ("/inventory/movements", "Inventory Movements"),
        # WMS
        ("/wms/tasks", "WMS Tasks"),
        ("/wms/inbound-tasks", "Inbound Tasks"),
        ("/wms/outbound-tasks", "Outbound Tasks"),
        ("/wms/transfers", "Transfers"),
        ("/wms/cycle-count-sessions", "Cycle Count Sessions"),
        # UOM
        ("/uom-conversions/catalog", "UOM Catalog"),
        ("/uom-conversions/rules", "UOM Rules"),
        ("/uom-conversions/usage", "UOM Usage"),
        # Products
        ("/products", "Products"),
        # R&D
        ("/rnd/specs", "R&D Specs"),
        ("/rnd/samples", "R&D Samples"),
        ("/rnd/designs", "R&D Designs"),
    ]
    
    print("\n── Testing Main Endpoints ──")
    errors_5xx = []
    
    for path, name in endpoints:
        r = get(token, path)
        if r:
            if r.status_code == 200:
                ok(f"{name} → HTTP 200")
            elif r.status_code >= 500:
                bad(f"{name} → HTTP {r.status_code} (5xx error)")
                errors_5xx.append((name, r.status_code))
            else:
                # 4xx might be expected (e.g., 404 if no data)
                info(f"{name} → HTTP {r.status_code}")
        else:
            bad(f"{name} → Request failed")
    
    if errors_5xx:
        bad(f"Found {len(errors_5xx)} endpoints with 5xx errors: {errors_5xx}")
    else:
        ok(f"No 5xx errors found in main endpoints")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Localization Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_localization(tokens: Dict[str, str]):
    """Test onboarding endpoint returns Indonesian labels"""
    print("\n" + "=" * 70)
    print("  3. LOCALIZATION — Onboarding Labels")
    print("=" * 70)
    
    # English words that should NOT appear in onboarding
    forbidden_english = [
        "task queue", "inbound", "outbound", "Advance", "confirmed", "dispatched",
        "Check", "Process", "Create", "Scan", "Dispatch", "Review", "Run", "Export"
    ]
    
    # Indonesian words that SHOULD appear
    expected_indonesian = [
        "Cek", "Proses", "Buat", "Lanjutkan", "Kirim", "Tinjau", "Jalankan",
        "antrean", "tugas", "barang masuk", "barang keluar", "gudang", "pesanan"
    ]
    
    for role, email in [("admin", "admin@kainnusantara.id"), 
                        ("sales", "sales@kainnusantara.id"),
                        ("warehouse", "warehouse@kainnusantara.id"),
                        ("manager", "manager@kainnusantara.id")]:
        print(f"\n── Testing {role} onboarding ──")
        r = get(tokens[role], "/onboarding")
        if not r or r.status_code != 200:
            bad(f"{role} onboarding → HTTP {r.status_code if r else 'ERROR'}")
            continue
        
        ok(f"{role} onboarding → HTTP 200")
        data = r.json()
        items = data.get("items", [])
        
        # Check all labels and descriptions
        all_text = ""
        for item in items:
            all_text += item.get("label", "") + " " + item.get("description", "") + " "
        
        # Check for forbidden English words
        found_english = []
        for word in forbidden_english:
            if word.lower() in all_text.lower():
                found_english.append(word)
        
        if found_english:
            bad(f"{role} onboarding contains English words: {found_english}")
        else:
            ok(f"{role} onboarding has NO forbidden English words")
        
        # Check for expected Indonesian words
        found_indonesian = []
        for word in expected_indonesian:
            if word.lower() in all_text.lower():
                found_indonesian.append(word)
        
        if len(found_indonesian) >= 3:  # At least 3 Indonesian words
            ok(f"{role} onboarding contains Indonesian words: {found_indonesian[:5]}")
        else:
            bad(f"{role} onboarding lacks Indonesian words (found: {found_indonesian})")
        
        info(f"  {role} has {len(items)} onboarding tasks")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 70)
    print("  BACKEND TEST — FASE F Final (Entity Scoping + Localization)")
    print("=" * 70)
    
    # Login all users
    print("\n── Login ──")
    tokens = {
        "admin": login("admin@kainnusantara.id"),
        "sales": login("sales@kainnusantara.id"),
        "sales3": login("sales3@kainnusantara.id"),
        "warehouse": login("warehouse@kainnusantara.id"),
        "manager": login("manager@kainnusantara.id"),
    }
    
    if not all(tokens.values()):
        bad("Failed to login all users")
        return 1
    
    ok(f"Logged in {len(tokens)} users")
    
    # Run tests
    test_entity_scoping(tokens)
    test_backend_regression(tokens["admin"])
    test_localization(tokens)
    
    # Summary
    print("\n" + "=" * 70)
    print(f"  RESULTS: ✅ {len(PASS)} PASS · ❌ {len(FAIL)} FAIL")
    print("=" * 70)
    
    if FAIL:
        print("\n❌ FAILED TESTS:")
        for f in FAIL:
            print(f"  - {f}")
    
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
