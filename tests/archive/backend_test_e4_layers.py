#!/usr/bin/env python3
"""
Backend Testing for FASE E-4 (E4.2-E4.6) - Layered Masters & Config
Testing agent iteration for multi-entity ERP system
"""
import requests
import sys
from typing import Dict, Any, List

# Use public endpoint
BASE_URL = "https://gudang-nusantara.preview.emergentagent.com"
ADMIN_EMAIL = "admin@kainnusantara.id"
ADMIN_PASSWORD = "demo12345"

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add_pass(self, test_name: str, details: str = ""):
        self.passed += 1
        self.tests.append({"name": test_name, "status": "PASS", "details": details})
        print(f"✅ PASS: {test_name}")
        if details:
            print(f"   → {details}")
    
    def add_fail(self, test_name: str, details: str = ""):
        self.failed += 1
        self.tests.append({"name": test_name, "status": "FAIL", "details": details})
        print(f"❌ FAIL: {test_name}")
        if details:
            print(f"   → {details}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*70}")
        print(f"TEST SUMMARY: {self.passed}/{total} PASSED")
        print(f"{'='*70}")
        return self.failed == 0


def login() -> Dict[str, str]:
    """Login and return headers with token"""
    print(f"\n🔐 Logging in as {ADMIN_EMAIL}...")
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("token")
            print(f"✅ Login successful")
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        else:
            print(f"❌ Login failed: {response.status_code} - {response.text[:200]}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        sys.exit(1)


def test_be1_layered_masters(headers: Dict[str, str], results: TestResults):
    """BE-1: Test layered master API"""
    print(f"\n{'='*70}")
    print("BE-1: Testing Layered Master API")
    print(f"{'='*70}")
    
    # Track cleanup items
    cleanup_ids = []
    
    try:
        # (a) GET /api/entity-masters with X-Entity-Id: ent_ksc
        print("\n📋 Test: GET /api/entity-masters (summary)")
        response = requests.get(
            f"{BASE_URL}/api/entity-masters",
            headers={**headers, "X-Entity-Id": "ent_ksc"},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            groups = data if isinstance(data, list) else []
            payment_terms_group = next((g for g in groups if g.get("kind") == "payment-terms"), None)
            if payment_terms_group:
                results.add_pass(
                    "GET /api/entity-masters returns groups",
                    f"Found {len(groups)} groups, payment-terms has {payment_terms_group.get('total', 0)} total"
                )
            else:
                results.add_fail("GET /api/entity-masters", "payment-terms group not found")
        else:
            results.add_fail("GET /api/entity-masters", f"Status {response.status_code}: {response.text[:200]}")
        
        # (b) GET /api/entity-masters/payment-terms
        print("\n📋 Test: GET /api/entity-masters/payment-terms")
        response = requests.get(
            f"{BASE_URL}/api/entity-masters/payment-terms",
            headers={**headers, "X-Entity-Id": "ent_ksc"},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            summary = data.get("summary", {})
            rows = data.get("rows", [])
            global_count = summary.get("global", 0)
            entity_count = summary.get("entity", 0)
            
            # Check for global rows
            global_rows = [r for r in rows if r.get("entity_scope") == "global"]
            if global_count >= 6 and len(global_rows) >= 6:
                results.add_pass(
                    "Payment terms has global rows",
                    f"summary.global={global_count}, found {len(global_rows)} global rows"
                )
            else:
                results.add_fail(
                    "Payment terms global rows",
                    f"Expected >=6 global, got summary.global={global_count}, found {len(global_rows)}"
                )
            
            # Check source_label and can_edit_here
            all_global_labeled = all(r.get("source_label") == "Global" for r in global_rows)
            all_global_not_editable = all(r.get("can_edit_here") == False for r in global_rows)
            
            if all_global_labeled:
                results.add_pass("Global rows have source_label='Global'")
            else:
                results.add_fail("Global rows source_label", "Not all global rows have source_label='Global'")
            
            if all_global_not_editable:
                results.add_pass("Global rows have can_edit_here=false")
            else:
                results.add_fail("Global rows can_edit_here", "Not all global rows have can_edit_here=false")
            
            # Find NET30 for override test
            net30_global = next((r for r in rows if r.get("code") == "NET30" and r.get("entity_scope") == "global"), None)
            if not net30_global:
                results.add_fail("Find NET30 global row", "NET30 not found in global rows")
                return
            
            net30_id = net30_global.get("id")
            original_net_days = net30_global.get("net_days")
            print(f"   Found NET30: id={net30_id}, net_days={original_net_days}")
            
        else:
            results.add_fail("GET /api/entity-masters/payment-terms", f"Status {response.status_code}")
            return
        
        # (c) POST override for NET30 with ent_kanda
        print("\n📋 Test: POST override NET30 for ent_kanda")
        response = requests.post(
            f"{BASE_URL}/api/entity-masters/payment-terms/{net30_id}/override",
            headers={**headers, "X-Entity-Id": "ent_kanda"},
            timeout=30
        )
        if response.status_code == 200:
            override_data = response.json()
            override_id = override_data.get("id")
            cleanup_ids.append(("payment_terms", override_id))
            
            if override_data.get("entity_id") == "ent_kanda" and override_data.get("entity_scope") == "entity":
                results.add_pass(
                    "POST override creates entity-specific row",
                    f"override_id={override_id}, entity_id=ent_kanda, source_label={override_data.get('source_label')}"
                )
            else:
                results.add_fail(
                    "POST override entity fields",
                    f"entity_id={override_data.get('entity_id')}, entity_scope={override_data.get('entity_scope')}"
                )
            
            if override_data.get("overrides_id") == net30_id:
                results.add_pass("Override has overrides_id pointing to global row")
            else:
                results.add_fail("Override overrides_id", f"Expected {net30_id}, got {override_data.get('overrides_id')}")
        else:
            results.add_fail("POST override", f"Status {response.status_code}: {response.text[:200]}")
            return
        
        # (d) PATCH override to change net_days
        print("\n📋 Test: PATCH override to change net_days to 45")
        new_net_days = 45
        response = requests.patch(
            f"{BASE_URL}/api/entity-masters/payment-terms/{override_id}",
            headers={**headers, "X-Entity-Id": "ent_kanda"},
            json={"data": {"net_days": new_net_days}},
            timeout=30
        )
        if response.status_code == 200:
            results.add_pass("PATCH override successful", f"Changed net_days to {new_net_days}")
        else:
            results.add_fail("PATCH override", f"Status {response.status_code}: {response.text[:200]}")
        
        # (e) GET /api/payment-terms to verify no duplicates
        print("\n📋 Test: GET /api/payment-terms (effective list, no duplicates)")
        response_kanda = requests.get(
            f"{BASE_URL}/api/payment-terms",
            headers={**headers, "X-Entity-Id": "ent_kanda"},
            timeout=30
        )
        response_ksc = requests.get(
            f"{BASE_URL}/api/payment-terms",
            headers={**headers, "X-Entity-Id": "ent_ksc"},
            timeout=30
        )
        
        if response_kanda.status_code == 200 and response_ksc.status_code == 200:
            kanda_terms = response_kanda.json()
            ksc_terms = response_ksc.json()
            
            # Check for duplicates in Kanda
            kanda_codes = [t.get("code") for t in kanda_terms]
            kanda_unique = len(kanda_codes) == len(set(kanda_codes))
            
            # Check NET30 value in Kanda
            kanda_net30 = next((t for t in kanda_terms if t.get("code") == "NET30"), None)
            kanda_net30_days = kanda_net30.get("net_days") if kanda_net30 else None
            
            # Check NET30 value in KSC (should be original)
            ksc_net30 = next((t for t in ksc_terms if t.get("code") == "NET30"), None)
            ksc_net30_days = ksc_net30.get("net_days") if ksc_net30 else None
            
            if kanda_unique:
                results.add_pass("Kanda payment terms has no duplicate codes", f"{len(kanda_codes)} unique codes")
            else:
                results.add_fail("Kanda payment terms duplicates", f"Found duplicate codes in {kanda_codes}")
            
            if kanda_net30_days == new_net_days:
                results.add_pass("Kanda NET30 uses override value", f"net_days={kanda_net30_days}")
            else:
                results.add_fail("Kanda NET30 value", f"Expected {new_net_days}, got {kanda_net30_days}")
            
            if ksc_net30_days == original_net_days:
                results.add_pass("KSC NET30 uses global value (not affected by Kanda override)", f"net_days={ksc_net30_days}")
            else:
                results.add_fail("KSC NET30 value", f"Expected {original_net_days}, got {ksc_net30_days}")
        else:
            results.add_fail("GET /api/payment-terms", "Failed to get effective lists")
        
        # (f) PATCH global row from entity context (should be 409)
        print("\n📋 Test: PATCH global row from entity context (should be 409)")
        response = requests.patch(
            f"{BASE_URL}/api/entity-masters/payment-terms/{net30_id}",
            headers={**headers, "X-Entity-Id": "ent_kanda"},
            json={"data": {"net_days": 999}},
            timeout=30
        )
        if response.status_code == 409:
            detail = response.json().get("detail", "")
            if "Global" in detail and ("Buat khusus" in detail or "Semua Entitas" in detail):
                results.add_pass("PATCH global from entity context returns 409 with helpful message", detail[:100])
            else:
                results.add_fail("PATCH global error message", f"Message doesn't mention 'Global' or solution: {detail[:100]}")
        else:
            results.add_fail("PATCH global from entity context", f"Expected 409, got {response.status_code}")
        
        # (g) DELETE override (revert to global)
        print("\n📋 Test: DELETE override (revert to global)")
        response = requests.delete(
            f"{BASE_URL}/api/entity-masters/payment-terms/{override_id}",
            headers={**headers, "X-Entity-Id": "ent_kanda"},
            timeout=30
        )
        if response.status_code == 200:
            revert_data = response.json()
            if revert_data.get("fell_back_to_global") == True:
                results.add_pass("DELETE override reverts to global", "fell_back_to_global=true")
                # Remove from cleanup since we already deleted it
                cleanup_ids = [(c, i) for c, i in cleanup_ids if i != override_id]
            else:
                results.add_fail("DELETE override fell_back_to_global", f"Expected true, got {revert_data.get('fell_back_to_global')}")
        else:
            results.add_fail("DELETE override", f"Status {response.status_code}: {response.text[:200]}")
        
        # Verify override is gone
        print("\n📋 Test: Verify override is deleted")
        response = requests.get(
            f"{BASE_URL}/api/entity-masters/payment-terms",
            headers={**headers, "X-Entity-Id": "ent_kanda"},
            timeout=30
        )
        if response.status_code == 200:
            rows = response.json().get("rows", [])
            override_exists = any(r.get("id") == override_id for r in rows)
            if not override_exists:
                results.add_pass("Override successfully deleted")
            else:
                results.add_fail("Override still exists", "Override row still found after DELETE")
        
    except Exception as e:
        results.add_fail("BE-1 Exception", str(e))
    
    finally:
        # Cleanup any remaining overrides
        print("\n🧹 Cleaning up BE-1 test data...")
        for coll, doc_id in cleanup_ids:
            try:
                if coll == "payment_terms":
                    requests.delete(
                        f"{BASE_URL}/api/entity-masters/payment-terms/{doc_id}",
                        headers={**headers, "X-Entity-Id": "ent_kanda"},
                        timeout=10
                    )
                    print(f"   Cleaned up {coll}/{doc_id}")
            except Exception:
                pass


def test_be2_layered_config(headers: Dict[str, str], results: TestResults):
    """BE-2: Test layered config + revert to global"""
    print(f"\n{'='*70}")
    print("BE-2: Testing Layered Config & Revert to Global")
    print(f"{'='*70}")
    
    config_key = "lot.enforcement_mode"
    
    try:
        # (a) GET /api/lots/settings for both entities (should be same initially)
        print("\n📋 Test: GET /api/lots/settings for ent_kanda and ent_ksc")
        response_kanda = requests.get(
            f"{BASE_URL}/api/lots/settings",
            headers={**headers, "X-Entity-Id": "ent_kanda"},
            timeout=30
        )
        response_ksc = requests.get(
            f"{BASE_URL}/api/lots/settings",
            headers={**headers, "X-Entity-Id": "ent_ksc"},
            timeout=30
        )
        
        if response_kanda.status_code == 200 and response_ksc.status_code == 200:
            kanda_mode = response_kanda.json().get("enforcement_mode")
            ksc_mode = response_ksc.json().get("enforcement_mode")
            
            if kanda_mode == ksc_mode:
                results.add_pass("Both entities have same enforcement_mode (global value)", f"mode={kanda_mode}")
                original_mode = kanda_mode
            else:
                results.add_fail("Initial enforcement_mode", f"Kanda={kanda_mode}, KSC={ksc_mode} (should be same)")
                original_mode = kanda_mode
        else:
            results.add_fail("GET /api/lots/settings", "Failed to get settings")
            return
        
        # (b) PUT /api/config/values to set entity-specific value
        print("\n📋 Test: PUT /api/config/values (entity-specific)")
        new_mode = "block" if original_mode != "block" else "warn"
        response = requests.put(
            f"{BASE_URL}/api/config/values",
            headers={**headers, "X-Entity-Id": "ent_kanda"},
            json={
                "items": [{
                    "key": config_key,
                    "value": new_mode,
                    "scope_type": "entity",
                    "scope_id": "ent_kanda",
                    "reason": "Testing E4.5 layered config"
                }]
            },
            timeout=30
        )
        if response.status_code == 200:
            results.add_pass("PUT /api/config/values successful", f"Set {config_key}={new_mode} for ent_kanda")
        else:
            results.add_fail("PUT /api/config/values", f"Status {response.status_code}: {response.text[:200]}")
            return
        
        # (c) Verify Kanda uses new value, KSC uses original
        print("\n📋 Test: Verify entity-specific value is applied")
        response_kanda = requests.get(
            f"{BASE_URL}/api/lots/settings",
            headers={**headers, "X-Entity-Id": "ent_kanda"},
            timeout=30
        )
        response_ksc = requests.get(
            f"{BASE_URL}/api/lots/settings",
            headers={**headers, "X-Entity-Id": "ent_ksc"},
            timeout=30
        )
        
        if response_kanda.status_code == 200 and response_ksc.status_code == 200:
            kanda_mode_after = response_kanda.json().get("enforcement_mode")
            ksc_mode_after = response_ksc.json().get("enforcement_mode")
            
            if kanda_mode_after == new_mode:
                results.add_pass("Kanda uses entity-specific value", f"enforcement_mode={kanda_mode_after}")
            else:
                results.add_fail("Kanda enforcement_mode", f"Expected {new_mode}, got {kanda_mode_after}")
            
            if ksc_mode_after == original_mode:
                results.add_pass("KSC still uses global value (not affected)", f"enforcement_mode={ksc_mode_after}")
            else:
                results.add_fail("KSC enforcement_mode", f"Expected {original_mode}, got {ksc_mode_after}")
        
        # (d) GET /api/config/explain
        print("\n📋 Test: GET /api/config/explain")
        response = requests.get(
            f"{BASE_URL}/api/config/explain",
            headers={**headers, "X-Entity-Id": "ent_kanda"},
            params={"key": config_key, "entity_id": "ent_kanda"},
            timeout=30
        )
        if response.status_code == 200:
            explain_data = response.json()
            source_layer = explain_data.get("source_layer")
            if source_layer == "entity":
                results.add_pass("Config explain shows source_layer='entity'")
            else:
                results.add_fail("Config explain source_layer", f"Expected 'entity', got {source_layer}")
        else:
            results.add_fail("GET /api/config/explain", f"Status {response.status_code}")
        
        # (e) POST /api/config/values/clear to revert to global
        print("\n📋 Test: POST /api/config/values/clear (revert to global)")
        response = requests.post(
            f"{BASE_URL}/api/config/values/clear",
            headers={**headers, "X-Entity-Id": "ent_kanda"},
            json={
                "key": config_key,
                "scope_type": "entity",
                "scope_id": "ent_kanda",
                "reason": "Testing E4.6 revert to global"
            },
            timeout=30
        )
        if response.status_code == 200:
            clear_data = response.json()
            value_now = clear_data.get("value_now")
            if value_now == original_mode:
                results.add_pass("Clear returns value_now as global value", f"value_now={value_now}")
            else:
                results.add_fail("Clear value_now", f"Expected {original_mode}, got {value_now}")
        else:
            results.add_fail("POST /api/config/values/clear", f"Status {response.status_code}: {response.text[:200]}")
        
        # Verify Kanda is back to global value
        print("\n📋 Test: Verify Kanda reverted to global value")
        response = requests.get(
            f"{BASE_URL}/api/lots/settings",
            headers={**headers, "X-Entity-Id": "ent_kanda"},
            timeout=30
        )
        if response.status_code == 200:
            kanda_mode_final = response.json().get("enforcement_mode")
            if kanda_mode_final == original_mode:
                results.add_pass("Kanda reverted to global value", f"enforcement_mode={kanda_mode_final}")
            else:
                results.add_fail("Kanda final enforcement_mode", f"Expected {original_mode}, got {kanda_mode_final}")
        
        # (f) POST /api/config/values/clear with scope_type='global' (should be 400)
        print("\n📋 Test: POST /api/config/values/clear with scope_type='global' (should be 400)")
        response = requests.post(
            f"{BASE_URL}/api/config/values/clear",
            headers={**headers, "X-Entity-Id": "all"},
            json={
                "key": config_key,
                "scope_type": "global",
                "scope_id": ""
            },
            timeout=30
        )
        if response.status_code == 400:
            detail = response.json().get("detail", "")
            if "Global" in detail or "global" in detail:
                results.add_pass("Clear global scope returns 400 with explanation", detail[:100])
            else:
                results.add_fail("Clear global error message", f"Message doesn't explain: {detail[:100]}")
        else:
            results.add_fail("Clear global scope", f"Expected 400, got {response.status_code}")
        
    except Exception as e:
        results.add_fail("BE-2 Exception", str(e))


def main():
    print(f"\n{'='*70}")
    print("BACKEND TESTING - FASE E-4 (E4.2-E4.6)")
    print(f"Testing URL: {BASE_URL}")
    print(f"{'='*70}")
    
    results = TestResults()
    
    # Login
    headers = login()
    
    # Run tests
    test_be1_layered_masters(headers, results)
    test_be2_layered_config(headers, results)
    
    # Print summary
    success = results.summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
