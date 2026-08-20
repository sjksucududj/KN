#!/usr/bin/env python3
"""
Backend API Test — M1 Makloon/Subcon (Fase M1)
===============================================
Comprehensive test covering:
1. Makloons CRUD (GET, POST, PATCH, DELETE)
2. Makloon 360 view (profile + recipes + orders + scorecard)
3. Process Recipes CRUD
4. Process Recipe Forecast (with formula validation)
5. Supplier 360 upgrade (tabbed view)
6. Permission tests (warehouse, sales roles)
7. Validation tests (numeric bounds, required fields)
"""
import os
import sys
import requests
from datetime import datetime

BASE = os.environ.get("BACKEND_URL", "https://subcon-preview.preview.emergentagent.com").rstrip("/")
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


class MakloonTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.entity_id = None
        self.makloon_id = None
        self.recipe_id = None
        self.supplier_id = None
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
    
    def setup_references(self):
        """Get entity, product references"""
        try:
            # Get entity
            r = self.session.get(f"{API}/entities", timeout=30)
            if r.status_code == 200:
                entities = r.json()
                if entities:
                    self.entity_id = entities[0]["id"]
            
            # Get a product for recipe testing
            r = self.session.get(f"{API}/products?limit=1", timeout=30)
            if r.status_code == 200:
                products = r.json()
                if products:
                    self.product_id = products[0]["id"]
            
            # Get a supplier for 360 testing
            r = self.session.get(f"{API}/suppliers?limit=1", timeout=30)
            if r.status_code == 200:
                suppliers = r.json()
                if suppliers:
                    self.supplier_id = suppliers[0]["id"]
            
            ok(f"Setup references: entity={self.entity_id[:8] if self.entity_id else 'N/A'}, product={self.product_id[:8] if self.product_id else 'N/A'}")
            return True
        except Exception as e:
            bad(f"Setup references exception: {e}")
            return False
    
    # ========== MAKLOON TESTS ==========
    
    def test_list_makloons(self):
        """Test GET /api/makloons - should return 3 seeded makloons"""
        info("Test: GET /api/makloons (list)")
        try:
            r = self.session.get(f"{API}/makloons", timeout=30)
            if r.status_code != 200:
                bad(f"GET /makloons failed: {r.status_code}")
                return False
            
            data = r.json()
            if not isinstance(data, list):
                bad(f"GET /makloons should return array, got {type(data)}")
                return False
            
            if len(data) < 3:
                bad(f"Expected at least 3 seeded makloons, got {len(data)}")
                return False
            
            # Check for seeded makloons
            codes = [m.get("code") for m in data]
            if "MAK-00001" in codes and "MAK-00002" in codes and "MAK-00003" in codes:
                ok(f"GET /makloons returns {len(data)} makloons (3 seeded found)")
            else:
                bad(f"Seeded makloons not found. Codes: {codes[:5]}")
                return False
            
            # Save a makloon ID for later tests
            if data:
                self.makloon_id = data[0]["id"]
            
            return True
        except Exception as e:
            bad(f"GET /makloons exception: {e}")
            return False
    
    def test_list_makloons_with_filters(self):
        """Test GET /api/makloons with status and entity_id filters"""
        info("Test: GET /api/makloons with filters")
        try:
            # Test status filter
            r = self.session.get(f"{API}/makloons?status=active", timeout=30)
            if r.status_code != 200:
                bad(f"GET /makloons?status=active failed: {r.status_code}")
                return False
            
            data = r.json()
            if not isinstance(data, list):
                bad(f"GET /makloons?status=active should return array")
                return False
            
            ok(f"GET /makloons?status=active returns {len(data)} makloons")
            
            # Test entity_id filter if we have one
            if self.entity_id:
                r = self.session.get(f"{API}/makloons?entity_id={self.entity_id}", timeout=30)
                if r.status_code == 200:
                    ok(f"GET /makloons?entity_id filter works")
            
            return True
        except Exception as e:
            bad(f"GET /makloons filters exception: {e}")
            return False
    
    def test_create_makloon(self):
        """Test POST /api/makloons - create new makloon"""
        info("Test: POST /api/makloons (create)")
        try:
            payload = {
                "name": f"QA Test Makloon {datetime.now().strftime('%H%M%S')}",
                "city": "Jakarta",
                "process_types": ["celup", "finishing"],
                "default_tariff": 2500,
                "lead_time_days": 7,
                "capacity_per_month": 1000
            }
            
            r = self.session.post(f"{API}/makloons", json=payload, timeout=30)
            if r.status_code != 200:
                bad(f"POST /makloons failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            if not data.get("id") or not data.get("code"):
                bad(f"POST /makloons response missing id or code")
                return False
            
            if not data["code"].startswith("MAK-"):
                bad(f"Makloon code should start with MAK-, got {data['code']}")
                return False
            
            ok(f"POST /makloons created {data['code']}")
            self.makloon_id = data["id"]  # Save for later tests
            return True
        except Exception as e:
            bad(f"POST /makloons exception: {e}")
            return False
    
    def test_create_makloon_validation(self):
        """Test POST /api/makloons validation (missing name, negative values)"""
        info("Test: POST /api/makloons validation")
        try:
            # Test missing name
            r = self.session.post(f"{API}/makloons", json={"name": ""}, timeout=30)
            if r.status_code != 400:
                bad(f"POST /makloons with empty name should return 400, got {r.status_code}")
                return False
            ok("POST /makloons validates empty name (400)")
            
            # Test negative default_tariff (should be rejected or coerced to 0)
            r = self.session.post(
                f"{API}/makloons",
                json={"name": "Test", "default_tariff": -100},
                timeout=30
            )
            if r.status_code == 422:
                ok("POST /makloons rejects negative default_tariff (422)")
            elif r.status_code == 200:
                data = r.json()
                if data.get("default_tariff", 0) >= 0:
                    ok("POST /makloons coerces negative default_tariff to 0")
                else:
                    bad(f"POST /makloons accepted negative default_tariff")
            else:
                bad(f"POST /makloons with negative tariff unexpected status: {r.status_code}")
            
            return True
        except Exception as e:
            bad(f"POST /makloons validation exception: {e}")
            return False
    
    def test_get_makloon_360(self):
        """Test GET /api/makloons/{id} - Makloon 360 view"""
        info("Test: GET /api/makloons/{id} (360 view)")
        if not self.makloon_id:
            bad("No makloon_id available for 360 test")
            return False
        
        try:
            r = self.session.get(f"{API}/makloons/{self.makloon_id}", timeout=30)
            if r.status_code != 200:
                bad(f"GET /makloons/{{id}} failed: {r.status_code}")
                return False
            
            data = r.json()
            
            # Check required 360 fields
            required_fields = ["id", "name", "code", "recipes", "orders", "service_bills", "scorecard"]
            missing = [f for f in required_fields if f not in data]
            if missing:
                bad(f"Makloon 360 missing fields: {missing}")
                return False
            
            # Check scorecard structure
            scorecard = data.get("scorecard", {})
            if not isinstance(scorecard, dict):
                bad(f"Scorecard should be dict, got {type(scorecard)}")
                return False
            
            if "has_data" not in scorecard:
                bad("Scorecard missing has_data field")
                return False
            
            # Scorecard should have has_data=false until M3 (no orders yet)
            if scorecard.get("has_data") == False:
                ok(f"GET /makloons/{{id}} returns 360 view with scorecard (has_data=false, correct for M1)")
            else:
                ok(f"GET /makloons/{{id}} returns 360 view with scorecard (has_data={scorecard.get('has_data')})")
            
            return True
        except Exception as e:
            bad(f"GET /makloons/{{id}} exception: {e}")
            return False
    
    def test_update_makloon(self):
        """Test PATCH /api/makloons/{id}"""
        info("Test: PATCH /api/makloons/{id}")
        if not self.makloon_id:
            bad("No makloon_id available for update test")
            return False
        
        try:
            payload = {
                "data": {
                    "city": "Bandung Updated",
                    "default_tariff": 3000
                }
            }
            
            r = self.session.patch(f"{API}/makloons/{self.makloon_id}", json=payload, timeout=30)
            if r.status_code != 200:
                bad(f"PATCH /makloons/{{id}} failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            if data.get("city") != "Bandung Updated":
                bad(f"PATCH /makloons/{{id}} city not updated")
                return False
            
            ok(f"PATCH /makloons/{{id}} updated successfully")
            return True
        except Exception as e:
            bad(f"PATCH /makloons/{{id}} exception: {e}")
            return False
    
    def test_get_makloon_scorecard(self):
        """Test GET /api/makloons/{id}/scorecard"""
        info("Test: GET /api/makloons/{id}/scorecard")
        if not self.makloon_id:
            bad("No makloon_id available for scorecard test")
            return False
        
        try:
            r = self.session.get(f"{API}/makloons/{self.makloon_id}/scorecard", timeout=30)
            if r.status_code != 200:
                bad(f"GET /makloons/{{id}}/scorecard failed: {r.status_code}")
                return False
            
            data = r.json()
            if "has_data" not in data:
                bad("Scorecard missing has_data field")
                return False
            
            ok(f"GET /makloons/{{id}}/scorecard returns scorecard (has_data={data.get('has_data')})")
            return True
        except Exception as e:
            bad(f"GET /makloons/{{id}}/scorecard exception: {e}")
            return False
    
    def test_delete_makloon(self):
        """Test DELETE /api/makloons/{id} - soft delete"""
        info("Test: DELETE /api/makloons/{id} (soft delete)")
        if not self.makloon_id:
            bad("No makloon_id available for delete test")
            return False
        
        try:
            r = self.session.delete(f"{API}/makloons/{self.makloon_id}", timeout=30)
            if r.status_code != 200:
                bad(f"DELETE /makloons/{{id}} failed: {r.status_code}")
                return False
            
            data = r.json()
            if data.get("status") != "inactive":
                bad(f"DELETE /makloons/{{id}} should set status=inactive, got {data.get('status')}")
                return False
            
            ok(f"DELETE /makloons/{{id}} soft-deactivated (status=inactive)")
            return True
        except Exception as e:
            bad(f"DELETE /makloons/{{id}} exception: {e}")
            return False
    
    # ========== PROCESS RECIPE TESTS ==========
    
    def test_list_recipes(self):
        """Test GET /api/process-recipes - should return 2 seeded recipes"""
        info("Test: GET /api/process-recipes (list)")
        try:
            r = self.session.get(f"{API}/process-recipes", timeout=30)
            if r.status_code != 200:
                bad(f"GET /process-recipes failed: {r.status_code}")
                return False
            
            data = r.json()
            if not isinstance(data, list):
                bad(f"GET /process-recipes should return array, got {type(data)}")
                return False
            
            if len(data) < 2:
                bad(f"Expected at least 2 seeded recipes, got {len(data)}")
                return False
            
            # Check enriched fields
            if data:
                recipe = data[0]
                enriched_fields = ["input_sku", "input_unit", "output_sku", "output_unit", "default_makloon_name"]
                missing = [f for f in enriched_fields if f not in recipe]
                if missing:
                    bad(f"Recipe missing enriched fields: {missing}")
                    return False
                
                ok(f"GET /process-recipes returns {len(data)} recipes with enriched data")
                self.recipe_id = recipe["id"]
            
            return True
        except Exception as e:
            bad(f"GET /process-recipes exception: {e}")
            return False
    
    def test_list_recipes_with_filters(self):
        """Test GET /api/process-recipes with filters"""
        info("Test: GET /api/process-recipes with filters")
        try:
            # Test process_type filter
            r = self.session.get(f"{API}/process-recipes?process_type=tenun", timeout=30)
            if r.status_code != 200:
                bad(f"GET /process-recipes?process_type failed: {r.status_code}")
                return False
            ok("GET /process-recipes?process_type filter works")
            
            # Test status filter
            r = self.session.get(f"{API}/process-recipes?status=active", timeout=30)
            if r.status_code != 200:
                bad(f"GET /process-recipes?status failed: {r.status_code}")
                return False
            ok("GET /process-recipes?status filter works")
            
            return True
        except Exception as e:
            bad(f"GET /process-recipes filters exception: {e}")
            return False
    
    def test_create_recipe(self):
        """Test POST /api/process-recipes"""
        info("Test: POST /api/process-recipes (create)")
        if not self.product_id:
            info("No product_id available, skipping recipe creation")
            return True
        
        try:
            payload = {
                "name": f"QA Test Recipe {datetime.now().strftime('%H%M%S')}",
                "process_type": "celup",
                "input_product_id": self.product_id,
                "output_product_id": self.product_id,
                "yield_factor": 0.95,
                "waste_pct": 5,
                "byproduct_pct": 2
            }
            
            r = self.session.post(f"{API}/process-recipes", json=payload, timeout=30)
            if r.status_code != 200:
                bad(f"POST /process-recipes failed: {r.status_code} {r.text[:200]}")
                return False
            
            data = r.json()
            if not data.get("id"):
                bad(f"POST /process-recipes response missing id")
                return False
            
            ok(f"POST /process-recipes created recipe")
            self.recipe_id = data["id"]
            return True
        except Exception as e:
            bad(f"POST /process-recipes exception: {e}")
            return False
    
    def test_create_recipe_validation(self):
        """Test POST /api/process-recipes validation"""
        info("Test: POST /api/process-recipes validation")
        try:
            # Test missing name
            r = self.session.post(f"{API}/process-recipes", json={"name": ""}, timeout=30)
            if r.status_code != 400:
                bad(f"POST /process-recipes with empty name should return 400, got {r.status_code}")
                return False
            ok("POST /process-recipes validates empty name (400)")
            
            # Test out-of-range waste_pct (should be 0-100)
            r = self.session.post(
                f"{API}/process-recipes",
                json={"name": "Test", "waste_pct": 150},
                timeout=30
            )
            if r.status_code == 422:
                ok("POST /process-recipes rejects waste_pct > 100 (422)")
            elif r.status_code == 200:
                bad(f"POST /process-recipes should reject waste_pct=150")
            
            return True
        except Exception as e:
            bad(f"POST /process-recipes validation exception: {e}")
            return False
    
    def test_update_recipe(self):
        """Test PATCH /api/process-recipes/{id}"""
        info("Test: PATCH /api/process-recipes/{id}")
        if not self.recipe_id:
            info("No recipe_id available, skipping update test")
            return True
        
        try:
            payload = {
                "data": {
                    "yield_factor": 0.98,
                    "waste_pct": 2
                }
            }
            
            r = self.session.patch(f"{API}/process-recipes/{self.recipe_id}", json=payload, timeout=30)
            if r.status_code != 200:
                bad(f"PATCH /process-recipes/{{id}} failed: {r.status_code}")
                return False
            
            ok(f"PATCH /process-recipes/{{id}} updated successfully")
            return True
        except Exception as e:
            bad(f"PATCH /process-recipes/{{id}} exception: {e}")
            return False
    
    def test_delete_recipe(self):
        """Test DELETE /api/process-recipes/{id}"""
        info("Test: DELETE /api/process-recipes/{id}")
        if not self.recipe_id:
            info("No recipe_id available, skipping delete test")
            return True
        
        try:
            r = self.session.delete(f"{API}/process-recipes/{self.recipe_id}", timeout=30)
            if r.status_code != 200:
                bad(f"DELETE /process-recipes/{{id}} failed: {r.status_code}")
                return False
            
            data = r.json()
            if data.get("status") != "inactive":
                bad(f"DELETE /process-recipes/{{id}} should set status=inactive")
                return False
            
            ok(f"DELETE /process-recipes/{{id}} soft-deactivated")
            return True
        except Exception as e:
            bad(f"DELETE /process-recipes/{{id}} exception: {e}")
            return False
    
    # ========== FORECAST TESTS ==========
    
    def test_forecast_basic(self):
        """Test POST /api/process-recipes/forecast - basic calculation"""
        info("Test: POST /api/process-recipes/forecast (basic)")
        try:
            payload = {
                "input_qty": 100,
                "yield_factor": 0.95,
                "waste_pct": 5,
                "byproduct_pct": 2
            }
            
            r = self.session.post(f"{API}/process-recipes/forecast", json=payload, timeout=30)
            if r.status_code != 200:
                bad(f"POST /process-recipes/forecast failed: {r.status_code}")
                return False
            
            data = r.json()
            required = ["expected_output", "expected_byproduct", "formula_used", "warnings"]
            missing = [f for f in required if f not in data]
            if missing:
                bad(f"Forecast response missing fields: {missing}")
                return False
            
            # Check calculation: expected_output = 100 * 0.95 * (1 - 5/100) = 90.25
            expected_output = data.get("expected_output")
            if abs(expected_output - 90.25) > 0.01:
                bad(f"Forecast calculation incorrect: expected ~90.25, got {expected_output}")
                return False
            
            ok(f"POST /process-recipes/forecast returns correct calculation (output={expected_output})")
            return True
        except Exception as e:
            bad(f"POST /process-recipes/forecast exception: {e}")
            return False
    
    def test_forecast_with_formula(self):
        """Test POST /api/process-recipes/forecast with custom formula"""
        info("Test: POST /api/process-recipes/forecast (with formula)")
        try:
            payload = {
                "input_qty": 100,
                "yield_factor": 0.95,
                "waste_pct": 5,
                "byproduct_pct": 2,
                "formula": "input_qty * yield_factor * (1 - waste_pct/100)"
            }
            
            r = self.session.post(f"{API}/process-recipes/forecast", json=payload, timeout=30)
            if r.status_code != 200:
                bad(f"POST /process-recipes/forecast with formula failed: {r.status_code}")
                return False
            
            data = r.json()
            if data.get("formula_used") != payload["formula"]:
                bad(f"Forecast should use provided formula")
                return False
            
            ok(f"POST /process-recipes/forecast with formula works")
            return True
        except Exception as e:
            bad(f"POST /process-recipes/forecast with formula exception: {e}")
            return False
    
    def test_forecast_invalid_formula(self):
        """Test POST /api/process-recipes/forecast with invalid formula"""
        info("Test: POST /api/process-recipes/forecast (invalid formula)")
        try:
            payload = {
                "input_qty": 100,
                "yield_factor": 0.95,
                "waste_pct": 5,
                "formula": "__import__('os').system('ls')"  # Malicious formula
            }
            
            r = self.session.post(f"{API}/process-recipes/forecast", json=payload, timeout=30)
            if r.status_code != 200:
                bad(f"POST /process-recipes/forecast with invalid formula failed: {r.status_code}")
                return False
            
            data = r.json()
            # Should have warnings and use fallback
            if not data.get("warnings"):
                bad(f"Forecast with invalid formula should have warnings")
                return False
            
            if data.get("formula_used"):
                bad(f"Forecast with invalid formula should use fallback (empty formula_used)")
                return False
            
            ok(f"POST /process-recipes/forecast handles invalid formula safely (warnings + fallback)")
            return True
        except Exception as e:
            bad(f"POST /process-recipes/forecast invalid formula exception: {e}")
            return False
    
    def test_forecast_out_of_range(self):
        """Test POST /api/process-recipes/forecast with out-of-range values"""
        info("Test: POST /api/process-recipes/forecast (out-of-range)")
        try:
            payload = {
                "input_qty": 100,
                "waste_pct": 150  # Out of range (should be 0-100)
            }
            
            r = self.session.post(f"{API}/process-recipes/forecast", json=payload, timeout=30)
            if r.status_code == 422:
                ok("POST /process-recipes/forecast rejects out-of-range waste_pct (422)")
            elif r.status_code == 200:
                bad(f"POST /process-recipes/forecast should reject waste_pct=150")
            else:
                bad(f"POST /process-recipes/forecast unexpected status: {r.status_code}")
            
            return True
        except Exception as e:
            bad(f"POST /process-recipes/forecast out-of-range exception: {e}")
            return False
    
    # ========== SUPPLIER 360 TESTS ==========
    
    def test_supplier_360(self):
        """Test GET /api/suppliers/{id}/360"""
        info("Test: GET /api/suppliers/{id}/360")
        if not self.supplier_id:
            info("No supplier_id available, skipping 360 test")
            return True
        
        try:
            r = self.session.get(f"{API}/suppliers/{self.supplier_id}/360", timeout=30)
            if r.status_code != 200:
                bad(f"GET /suppliers/{{id}}/360 failed: {r.status_code}")
                return False
            
            data = r.json()
            
            # Check required 360 fields
            required = ["id", "name", "purchase_orders", "vendor_bills", "returns", "scorecard", 
                       "po_count", "bill_count", "return_count"]
            missing = [f for f in required if f not in data]
            if missing:
                bad(f"Supplier 360 missing fields: {missing}")
                return False
            
            ok(f"GET /suppliers/{{id}}/360 returns complete 360 view (PO count={data.get('po_count')})")
            return True
        except Exception as e:
            bad(f"GET /suppliers/{{id}}/360 exception: {e}")
            return False
    
    # ========== PERMISSION TESTS ==========
    
    def test_warehouse_permissions(self):
        """Test warehouse role permissions (can GET but not POST/PATCH/DELETE)"""
        info("Test: Warehouse role permissions")
        
        # Login as warehouse
        if not self.login("warehouse@kainnusantara.id", "demo12345"):
            return False
        
        try:
            # Should be able to GET
            r = self.session.get(f"{API}/makloons", timeout=30)
            if r.status_code != 200:
                bad(f"Warehouse should be able to GET /makloons, got {r.status_code}")
                return False
            ok("Warehouse can GET /makloons")
            
            # Should NOT be able to POST
            r = self.session.post(
                f"{API}/makloons",
                json={"name": "Test"},
                timeout=30
            )
            if r.status_code != 403:
                bad(f"Warehouse POST /makloons should return 403, got {r.status_code}")
                return False
            ok("Warehouse cannot POST /makloons (403)")
            
            # Should NOT be able to PATCH
            if self.makloon_id:
                r = self.session.patch(
                    f"{API}/makloons/{self.makloon_id}",
                    json={"data": {"city": "Test"}},
                    timeout=30
                )
                if r.status_code != 403:
                    bad(f"Warehouse PATCH /makloons should return 403, got {r.status_code}")
                    return False
                ok("Warehouse cannot PATCH /makloons (403)")
            
            # Should NOT be able to DELETE
            if self.makloon_id:
                r = self.session.delete(f"{API}/makloons/{self.makloon_id}", timeout=30)
                if r.status_code != 403:
                    bad(f"Warehouse DELETE /makloons should return 403, got {r.status_code}")
                    return False
                ok("Warehouse cannot DELETE /makloons (403)")
            
            return True
        except Exception as e:
            bad(f"Warehouse permissions exception: {e}")
            return False
        finally:
            # Re-login as admin
            self.login("admin@kainnusantara.id", "demo12345")
    
    def test_sales_permissions(self):
        """Test sales role permissions (no makloon access)"""
        info("Test: Sales role permissions")
        
        # Login as sales
        if not self.login("sales@kainnusantara.id", "demo12345"):
            return False
        
        try:
            # Should NOT have access to makloons
            r = self.session.get(f"{API}/makloons", timeout=30)
            if r.status_code != 403:
                bad(f"Sales GET /makloons should return 403, got {r.status_code}")
                return False
            ok("Sales has no access to /makloons (403)")
            
            return True
        except Exception as e:
            bad(f"Sales permissions exception: {e}")
            return False
        finally:
            # Re-login as admin
            self.login("admin@kainnusantara.id", "demo12345")
    
    # ========== UNAUTHENTICATED TESTS ==========
    
    def test_unauthenticated_access(self):
        """Test unauthenticated access returns 401/403"""
        info("Test: Unauthenticated access")
        
        # Save current token
        saved_token = self.session.headers.get("Authorization")
        
        try:
            # Remove auth header
            self.session.headers.pop("Authorization", None)
            
            r = self.session.get(f"{API}/makloons", timeout=30)
            if r.status_code not in [401, 403]:
                bad(f"Unauthenticated GET /makloons should return 401/403, got {r.status_code}")
                return False
            
            ok(f"Unauthenticated access returns {r.status_code}")
            return True
        except Exception as e:
            bad(f"Unauthenticated access exception: {e}")
            return False
        finally:
            # Restore auth header
            if saved_token:
                self.session.headers["Authorization"] = saved_token
    
    # ========== MAIN TEST RUNNER ==========
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*70)
        print("  BACKEND API TEST — M1 Makloon/Subcon")
        print("="*70)
        
        # Login and setup
        if not self.login():
            return False
        
        if not self.setup_references():
            return False
        
        print("\n--- MAKLOON TESTS ---")
        self.test_list_makloons()
        self.test_list_makloons_with_filters()
        self.test_create_makloon()
        self.test_create_makloon_validation()
        self.test_get_makloon_360()
        self.test_update_makloon()
        self.test_get_makloon_scorecard()
        # Note: Delete test is last as it deactivates the makloon
        
        print("\n--- PROCESS RECIPE TESTS ---")
        self.test_list_recipes()
        self.test_list_recipes_with_filters()
        self.test_create_recipe()
        self.test_create_recipe_validation()
        self.test_update_recipe()
        # Note: Delete test is last
        
        print("\n--- FORECAST TESTS ---")
        self.test_forecast_basic()
        self.test_forecast_with_formula()
        self.test_forecast_invalid_formula()
        self.test_forecast_out_of_range()
        
        print("\n--- SUPPLIER 360 TESTS ---")
        self.test_supplier_360()
        
        print("\n--- PERMISSION TESTS ---")
        self.test_warehouse_permissions()
        self.test_sales_permissions()
        self.test_unauthenticated_access()
        
        print("\n--- CLEANUP TESTS (DELETE) ---")
        self.test_delete_recipe()
        self.test_delete_makloon()
        
        return True


def main():
    tester = MakloonTester()
    tester.run_all_tests()
    
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
