#!/usr/bin/env python3
"""
Backend API Test — FASE B: UOM Conversion System
=================================================
Comprehensive test covering:
1. UOM Catalog (units, dimensions, kinds, settings)
2. UOM Rules CRUD (GET, POST, PATCH, status toggle)
3. UOM Settings (tolerance configuration)
4. UOM Conversion (with trail tracking - D-07)
5. Variance checking (warn/block levels)
6. Usage tracking (document trail audit)
7. RBAC (admin/manager/sales permissions)
8. Decimal comma support (PS-15/R5)
9. Validation tests (factor 0, duplicate rules, cross-dimension)
"""
import os
import sys
import requests
from datetime import datetime

BASE = os.environ.get("BACKEND_URL", "https://grade-registry-qa.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
PASS, FAIL = [], []
TEST_SUFFIX = datetime.now().strftime("%H%M%S")


def ok(m):
    PASS.append(m)
    print(f"  ✅ [PASS] {m}")


def bad(m):
    FAIL.append(m)
    print(f"  ❌ [FAIL] {m}")


def info(m):
    print(f"  ℹ️  {m}")


class UomTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.role = None
        self.test_rule_id = None
        self.product_id = None
        
    def login(self, email="admin@kainnusantara.id", password="demo12345"):
        """Login with specified credentials"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login failed for {email}: {r.status_code}")
                return False
            data = r.json()
            self.token = data.get("token")
            if not self.token:
                bad(f"Login response missing token for {email}")
                return False
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            self.role = email.split("@")[0]
            ok(f"Login {self.role}")
            return True
        except Exception as e:
            bad(f"Login exception for {email}: {e}")
            return False
    
    def get_product(self):
        """Get a product for conversion testing"""
        try:
            r = self.session.get(f"{API}/products?limit=1", timeout=30)
            if r.status_code == 200:
                products = r.json()
                items = products.get("items", products) if isinstance(products, dict) else products
                if items:
                    self.product_id = items[0]["id"]
                    ok(f"Got product {items[0].get('sku', 'N/A')}")
                    return items[0]
            return None
        except Exception as e:
            bad(f"Get product exception: {e}")
            return None
    
    def test_catalog(self):
        """Test GET /api/uom-conversions/catalog"""
        info("Testing UOM Catalog...")
        try:
            r = self.session.get(f"{API}/uom-conversions/catalog", timeout=30)
            if r.status_code != 200:
                bad(f"Catalog GET failed: {r.status_code}")
                return False
            
            data = r.json()
            units = data.get("units", [])
            dimensions = data.get("dimensions", [])
            kinds = data.get("kinds", [])
            settings = data.get("settings", {})
            
            if len(units) >= 20:
                ok(f"Catalog has ≥20 units ({len(units)} found)")
            else:
                bad(f"Catalog has <20 units ({len(units)} found)")
            
            if len(dimensions) >= 4:
                ok(f"Catalog has ≥4 dimensions ({len(dimensions)} found)")
            else:
                bad(f"Catalog has <4 dimensions ({len(dimensions)} found)")
            
            required_units = ["meter", "yard", "kg", "roll", "cone", "bale", "lbs", "m2"]
            unit_codes = [u["code"] for u in units]
            missing = [u for u in required_units if u not in unit_codes]
            if not missing:
                ok(f"All required textile units present")
            else:
                bad(f"Missing textile units: {missing}")
            
            if "warn_pct" in settings and "block_pct" in settings:
                ok(f"Settings included in catalog (warn={settings.get('warn_pct')}%, block={settings.get('block_pct')}%)")
            else:
                bad(f"Settings missing from catalog")
            
            return True
        except Exception as e:
            bad(f"Catalog test exception: {e}")
            return False
    
    def test_rules_list(self):
        """Test GET /api/uom-conversions/rules"""
        info("Testing UOM Rules List...")
        try:
            r = self.session.get(f"{API}/uom-conversions/rules", timeout=30)
            if r.status_code != 200:
                bad(f"Rules GET failed: {r.status_code}")
                return False
            
            data = r.json()
            rules = data.get("rules", [])
            total = data.get("total", 0)
            active = data.get("active", 0)
            
            if len(rules) >= 14:
                ok(f"Rules list has ≥14 rules ({len(rules)} found, {active} active)")
            else:
                bad(f"Rules list has <14 rules ({len(rules)} found)")
            
            # Check for standard physics rules
            pairs = [(r["from_unit"], r["to_unit"]) for r in rules]
            required_pairs = [("yard", "meter"), ("lbs", "kg"), ("dozen", "piece")]
            missing_pairs = [p for p in required_pairs if p not in pairs]
            if not missing_pairs:
                ok(f"Standard physics rules present (yard→meter, lbs→kg, dozen→piece)")
            else:
                bad(f"Missing standard rules: {missing_pairs}")
            
            # Check for formula rule
            formula_rules = [r for r in rules if r.get("kind") == "formula"]
            if formula_rules:
                ok(f"Formula rules present ({len(formula_rules)} found)")
            else:
                bad(f"No formula rules found")
            
            return True
        except Exception as e:
            bad(f"Rules list test exception: {e}")
            return False
    
    def test_create_rule(self):
        """Test POST /api/uom-conversions/rules with validations"""
        info("Testing UOM Rule Creation...")
        try:
            # Test 1: Create valid rule with decimal comma
            r = self.session.post(
                f"{API}/uom-conversions/rules",
                json={
                    "from_unit": "bale",
                    "to_unit": "kg",
                    "kind": "pack",
                    "factor": "100,5",  # Decimal comma
                    "note": f"TEST-{TEST_SUFFIX} bale to kg"
                },
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                self.test_rule_id = data.get("id")
                factor = float(data.get("factor", 0))
                if abs(factor - 100.5) < 0.01:
                    ok(f"Rule created with decimal comma factor (100,5 → {factor})")
                else:
                    bad(f"Rule factor incorrect: expected 100.5, got {factor}")
            else:
                bad(f"Rule creation failed: {r.status_code} - {r.text[:100]}")
                return False
            
            # Test 2: Duplicate rule should fail
            r = self.session.post(
                f"{API}/uom-conversions/rules",
                json={
                    "from_unit": "bale",
                    "to_unit": "kg",
                    "kind": "pack",
                    "factor": "200",
                    "note": f"TEST-{TEST_SUFFIX} duplicate"
                },
                timeout=30
            )
            if r.status_code == 400:
                ok(f"Duplicate rule rejected (400)")
            else:
                bad(f"Duplicate rule not rejected: {r.status_code}")
            
            # Test 3: Factor 0 should fail
            r = self.session.post(
                f"{API}/uom-conversions/rules",
                json={
                    "from_unit": "box",
                    "to_unit": "piece",
                    "kind": "pack",
                    "factor": "0",
                    "note": f"TEST-{TEST_SUFFIX} zero factor"
                },
                timeout=30
            )
            if r.status_code in (400, 422):
                ok(f"Zero factor rejected ({r.status_code})")
            else:
                bad(f"Zero factor not rejected: {r.status_code}")
            
            # Test 4: Same unit should fail
            r = self.session.post(
                f"{API}/uom-conversions/rules",
                json={
                    "from_unit": "kg",
                    "to_unit": "kg",
                    "kind": "fixed",
                    "factor": "1",
                    "note": f"TEST-{TEST_SUFFIX} same unit"
                },
                timeout=30
            )
            if r.status_code == 400:
                ok(f"Same unit rule rejected (400)")
            else:
                bad(f"Same unit rule not rejected: {r.status_code}")
            
            # Test 5: Fixed cross-dimension should fail
            r = self.session.post(
                f"{API}/uom-conversions/rules",
                json={
                    "from_unit": "meter",
                    "to_unit": "gram",
                    "kind": "fixed",
                    "factor": "138",
                    "note": f"TEST-{TEST_SUFFIX} cross dimension"
                },
                timeout=30
            )
            if r.status_code == 400 and "formula" in r.text.lower():
                ok(f"Fixed cross-dimension rejected with formula suggestion")
            else:
                bad(f"Fixed cross-dimension not properly rejected: {r.status_code}")
            
            return True
        except Exception as e:
            bad(f"Rule creation test exception: {e}")
            return False
    
    def test_update_rule(self):
        """Test PATCH /api/uom-conversions/rules/{id}"""
        info("Testing UOM Rule Update...")
        if not self.test_rule_id:
            info("Skipping update test (no test rule created)")
            return True
        
        try:
            r = self.session.patch(
                f"{API}/uom-conversions/rules/{self.test_rule_id}",
                json={
                    "factor": "105,75",  # Decimal comma
                    "note": f"TEST-{TEST_SUFFIX} updated"
                },
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                factor = float(data.get("factor", 0))
                if abs(factor - 105.75) < 0.01:
                    ok(f"Rule updated with decimal comma (105,75 → {factor})")
                else:
                    bad(f"Rule update factor incorrect: {factor}")
            else:
                bad(f"Rule update failed: {r.status_code}")
                return False
            
            return True
        except Exception as e:
            bad(f"Rule update test exception: {e}")
            return False
    
    def test_toggle_rule(self):
        """Test POST /api/uom-conversions/rules/{id}/status"""
        info("Testing UOM Rule Status Toggle...")
        if not self.test_rule_id:
            info("Skipping toggle test (no test rule created)")
            return True
        
        try:
            # Deactivate
            r = self.session.post(
                f"{API}/uom-conversions/rules/{self.test_rule_id}/status",
                params={"status": "inactive"},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "inactive":
                    ok(f"Rule deactivated successfully")
                else:
                    bad(f"Rule status not inactive: {data.get('status')}")
            else:
                bad(f"Rule deactivation failed: {r.status_code}")
                return False
            
            # Reactivate
            r = self.session.post(
                f"{API}/uom-conversions/rules/{self.test_rule_id}/status",
                params={"status": "active"},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "active":
                    ok(f"Rule reactivated successfully")
                else:
                    bad(f"Rule status not active: {data.get('status')}")
            else:
                bad(f"Rule reactivation failed: {r.status_code}")
                return False
            
            return True
        except Exception as e:
            bad(f"Rule toggle test exception: {e}")
            return False
    
    def test_settings(self):
        """Test GET+PUT /api/uom-conversions/settings"""
        info("Testing UOM Settings...")
        try:
            # Get current settings
            r = self.session.get(f"{API}/uom-conversions/settings", timeout=30)
            if r.status_code != 200:
                bad(f"Settings GET failed: {r.status_code}")
                return False
            
            current = r.json()
            ok(f"Settings retrieved (warn={current.get('warn_pct')}%, block={current.get('block_pct')}%)")
            
            # Test invalid settings (warn > block)
            r = self.session.put(
                f"{API}/uom-conversions/settings",
                json={"warn_pct": "9", "block_pct": "3"},
                timeout=30
            )
            if r.status_code == 400:
                ok(f"Invalid settings rejected (warn > block)")
            else:
                bad(f"Invalid settings not rejected: {r.status_code}")
            
            # Test valid settings with decimal comma
            r = self.session.put(
                f"{API}/uom-conversions/settings",
                json={
                    "warn_pct": "1,5",
                    "block_pct": "3",
                    "allow_override": True,
                    "precision": 2
                },
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                warn = float(data.get("warn_pct", 0))
                if abs(warn - 1.5) < 0.01:
                    ok(f"Settings updated with decimal comma (1,5 → {warn})")
                else:
                    bad(f"Settings warn_pct incorrect: {warn}")
            else:
                bad(f"Settings update failed: {r.status_code}")
                return False
            
            # Restore default settings
            r = self.session.put(
                f"{API}/uom-conversions/settings",
                json={
                    "warn_pct": "2",
                    "block_pct": "5",
                    "allow_override": True,
                    "precision": 2
                },
                timeout=30
            )
            if r.status_code == 200:
                ok(f"Settings restored to default")
            else:
                info(f"Warning: Could not restore default settings")
            
            return True
        except Exception as e:
            bad(f"Settings test exception: {e}")
            return False
    
    def test_convert(self, product):
        """Test POST /api/uom-conversions/convert"""
        info("Testing UOM Conversion...")
        if not product:
            info("Skipping conversion test (no product)")
            return True
        
        try:
            # Test 1: Standard conversion (yard → meter)
            r = self.session.post(
                f"{API}/uom-conversions/convert",
                json={
                    "product_id": product["id"],
                    "qty": "10,5",  # Decimal comma
                    "from_unit": "yard",
                    "to_unit": "meter"
                },
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                doc_qty = float(data.get("doc_qty", 0))
                base_qty = float(data.get("base_qty", 0))
                factor = float(data.get("factor", 0))
                source = data.get("source", "")
                
                if abs(doc_qty - 10.5) < 0.01:
                    ok(f"Conversion accepts decimal comma (10,5 → {doc_qty})")
                else:
                    bad(f"Conversion doc_qty incorrect: {doc_qty}")
                
                if abs(base_qty - 9.6) < 0.1:
                    ok(f"Yard to meter conversion correct (10.5 yd ≈ {base_qty} m)")
                else:
                    bad(f"Yard to meter conversion incorrect: {base_qty}")
                
                # Check trail fields (D-07)
                required_fields = ["doc_uom", "doc_qty", "base_uom", "base_qty", "factor", "source", "converted_at"]
                missing = [f for f in required_fields if f not in data]
                if not missing:
                    ok(f"Conversion trail complete (D-07)")
                else:
                    bad(f"Conversion trail missing fields: {missing}")
            else:
                bad(f"Conversion failed: {r.status_code}")
                return False
            
            # Test 2: Unknown unit should fail
            r = self.session.post(
                f"{API}/uom-conversions/convert",
                json={
                    "product_id": product["id"],
                    "qty": "5",
                    "from_unit": "gallon",
                    "to_unit": "meter"
                },
                timeout=30
            )
            if r.status_code == 400 and "aturan" in r.text.lower():
                ok(f"Unknown unit rejected with Indonesian message")
            else:
                bad(f"Unknown unit not properly rejected: {r.status_code}")
            
            return True
        except Exception as e:
            bad(f"Conversion test exception: {e}")
            return False
    
    def test_variance(self):
        """Test POST /api/uom-conversions/check-variance"""
        info("Testing Variance Check...")
        try:
            # Test 1: OK level (1% difference)
            r = self.session.post(
                f"{API}/uom-conversions/check-variance",
                json={"expected": "100", "actual": "101"},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("level") == "ok":
                    ok(f"Variance 1% → OK level")
                else:
                    bad(f"Variance 1% level incorrect: {data.get('level')}")
            else:
                bad(f"Variance check failed: {r.status_code}")
                return False
            
            # Test 2: Warn level (2.5% difference)
            r = self.session.post(
                f"{API}/uom-conversions/check-variance",
                json={"expected": "100", "actual": "102,5"},  # Decimal comma
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("level") == "warn":
                    ok(f"Variance 2.5% → warn level")
                else:
                    bad(f"Variance 2.5% level incorrect: {data.get('level')}")
            else:
                bad(f"Variance check failed: {r.status_code}")
                return False
            
            # Test 3: Block level (6% difference)
            r = self.session.post(
                f"{API}/uom-conversions/check-variance",
                json={"expected": "100", "actual": "106"},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("level") == "block":
                    ok(f"Variance 6% → block level")
                    if "%" in data.get("message", "") and "blokir" in data.get("message", "").lower():
                        ok(f"Block message explains action in Indonesian")
                    else:
                        bad(f"Block message unclear: {data.get('message', '')[:50]}")
                else:
                    bad(f"Variance 6% level incorrect: {data.get('level')}")
            else:
                bad(f"Variance check failed: {r.status_code}")
                return False
            
            return True
        except Exception as e:
            bad(f"Variance test exception: {e}")
            return False
    
    def test_usage(self):
        """Test GET /api/uom-conversions/usage"""
        info("Testing Usage Tracking...")
        try:
            r = self.session.get(
                f"{API}/uom-conversions/usage",
                params={"limit": 20},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Usage GET failed: {r.status_code}")
                return False
            
            data = r.json()
            usage = data.get("usage", [])
            
            if len(usage) > 0:
                ok(f"Usage tracking returns document trails ({len(usage)} found)")
                
                # Check trail fields
                sample = usage[0]
                required = ["doc_uom", "base_uom", "factor", "source"]
                missing = [f for f in required if f not in sample]
                if not missing:
                    ok(f"Usage trail contains required fields")
                else:
                    bad(f"Usage trail missing fields: {missing}")
            else:
                info(f"No usage trails found (may be empty database)")
            
            return True
        except Exception as e:
            bad(f"Usage test exception: {e}")
            return False
    
    def test_rbac_forbidden(self):
        """Test that non-admin roles cannot modify rules/settings"""
        info(f"Testing RBAC for {self.role}...")
        try:
            # Test 1: Cannot create rule
            r = self.session.post(
                f"{API}/uom-conversions/rules",
                json={
                    "from_unit": "pack",
                    "to_unit": "piece",
                    "kind": "pack",
                    "factor": "10"
                },
                timeout=30
            )
            if r.status_code == 403:
                ok(f"{self.role} cannot create rules (403)")
            else:
                bad(f"{self.role} rule creation not forbidden: {r.status_code}")
            
            # Test 2: Cannot update settings
            r = self.session.put(
                f"{API}/uom-conversions/settings",
                json={"warn_pct": "10"},
                timeout=30
            )
            if r.status_code == 403:
                ok(f"{self.role} cannot update settings (403)")
            else:
                bad(f"{self.role} settings update not forbidden: {r.status_code}")
            
            # Test 3: CAN read rules (transparency)
            r = self.session.get(f"{API}/uom-conversions/rules", timeout=30)
            if r.status_code == 200:
                ok(f"{self.role} can read rules (200)")
            else:
                bad(f"{self.role} cannot read rules: {r.status_code}")
            
            # Test 4: CAN read catalog
            r = self.session.get(f"{API}/uom-conversions/catalog", timeout=30)
            if r.status_code == 200:
                ok(f"{self.role} can read catalog (200)")
            else:
                bad(f"{self.role} cannot read catalog: {r.status_code}")
            
            return True
        except Exception as e:
            bad(f"RBAC test exception: {e}")
            return False


def main():
    print("=" * 80)
    print("  BACKEND API TEST — FASE B: UOM Conversion System")
    print("=" * 80)
    print(f"  Base URL: {BASE}")
    print(f"  Test Suffix: {TEST_SUFFIX}")
    print("=" * 80)
    
    # Test as admin (full access)
    print("\n[ADMIN TESTS]")
    admin = UomTester()
    if not admin.login("admin@kainnusantara.id", "demo12345"):
        print("\n❌ Admin login failed, cannot continue")
        return 1
    
    product = admin.get_product()
    admin.test_catalog()
    admin.test_rules_list()
    admin.test_create_rule()
    admin.test_update_rule()
    admin.test_toggle_rule()
    admin.test_settings()
    admin.test_convert(product)
    admin.test_variance()
    admin.test_usage()
    
    # Test as manager (read-only for UOM)
    print("\n[MANAGER TESTS - RBAC]")
    manager = UomTester()
    if manager.login("manager@kainnusantara.id", "demo12345"):
        manager.test_rbac_forbidden()
    else:
        info("Manager login failed, skipping manager RBAC tests")
    
    # Test as sales (read-only for UOM)
    print("\n[SALES TESTS - RBAC]")
    sales = UomTester()
    if sales.login("sales@kainnusantara.id", "demo12345"):
        sales.test_rbac_forbidden()
    else:
        info("Sales login failed, skipping sales RBAC tests")
    
    # Summary
    print("\n" + "=" * 80)
    print(f"  RESULTS: {len(PASS)} PASS · {len(FAIL)} FAIL")
    print("=" * 80)
    
    if FAIL:
        print("\n[FAILURES]")
        for f in FAIL:
            print(f"  ❌ {f}")
    
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
