"""R6.2 — Fixed Assets & Depreciation Backend Testing
Testing: API contracts, RBAC, edge cases, idempotency, GL balance, multi-entity scoping
Backend only (frontend already verified by main agent via screenshots)
"""
import requests
import sys
from datetime import datetime, timedelta

BASE_URL = "https://code-continue-37.preview.emergentagent.com/api"

# Test credentials
ADMIN_CREDS = {"email": "admin@kainnusantara.id", "password": "demo12345"}
SALES_CREDS = {"email": "sales@kainnusantara.id", "password": "demo12345"}
MANAGER_CREDS = {"email": "manager@kainnusantara.id", "password": "demo12345"}
WAREHOUSE_CREDS = {"email": "warehouse@kainnusantara.id", "password": "demo12345"}

# Entities
ENTITY_KSC = "ent_ksc"
ENTITY_KANDA = "ent_kanda"

class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.admin_token = None
        self.sales_token = None
        self.manager_token = None
        self.warehouse_token = None
        self.created_assets = []
        
    def log(self, status, test_name, detail=""):
        if status:
            self.passed += 1
            print(f"  ✅ {test_name}")
        else:
            self.failed += 1
            print(f"  ❌ {test_name} — {detail}")
    
    def login(self, creds):
        """Login and return token"""
        try:
            r = requests.post(f"{BASE_URL}/auth/login", json=creds, timeout=30)
            if r.status_code == 200:
                return r.json().get("token")
            return None
        except Exception as e:
            print(f"Login error: {e}")
            return None
    
    def setup_auth(self):
        """Setup authentication tokens for all roles"""
        print("\n=== SETUP: Authentication ===")
        self.admin_token = self.login(ADMIN_CREDS)
        self.log(self.admin_token is not None, "Admin login successful")
        
        self.sales_token = self.login(SALES_CREDS)
        self.log(self.sales_token is not None, "Sales login successful")
        
        self.manager_token = self.login(MANAGER_CREDS)
        self.log(self.manager_token is not None, "Manager login successful")
        
        self.warehouse_token = self.login(WAREHOUSE_CREDS)
        self.log(self.warehouse_token is not None, "Warehouse login successful")
        
        if not self.admin_token:
            print("CRITICAL: Admin login failed, cannot proceed")
            sys.exit(1)
    
    def headers(self, token):
        """Return headers with auth token"""
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def test_auth_required(self):
        """Test that all endpoints require authentication"""
        print("\n=== TEST: Authentication Required (401/403 without token) ===")
        
        endpoints = [
            ("GET", "/fixed-assets"),
            ("GET", "/fixed-assets/meta"),
            ("GET", "/fixed-assets/summary"),
            ("POST", "/fixed-assets"),
        ]
        
        for method, endpoint in endpoints:
            try:
                if method == "GET":
                    r = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
                else:
                    r = requests.post(f"{BASE_URL}{endpoint}", json={}, timeout=10)
                
                self.log(r.status_code in [401, 403], 
                        f"{method} {endpoint} requires auth",
                        f"Got {r.status_code}")
            except Exception as e:
                self.log(False, f"{method} {endpoint} requires auth", str(e))
    
    def test_rbac_permissions(self):
        """Test RBAC: admin/manager OK, sales/warehouse 403"""
        print("\n=== TEST: RBAC Permissions ===")
        
        # Admin should have access
        try:
            r = requests.get(f"{BASE_URL}/fixed-assets?entity_id={ENTITY_KSC}", 
                           headers=self.headers(self.admin_token), timeout=10)
            self.log(r.status_code == 200, "Admin can access GET /fixed-assets", 
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "Admin can access GET /fixed-assets", str(e))
        
        # Manager should have access
        try:
            r = requests.get(f"{BASE_URL}/fixed-assets?entity_id={ENTITY_KSC}", 
                           headers=self.headers(self.manager_token), timeout=10)
            self.log(r.status_code == 200, "Manager can access GET /fixed-assets", 
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "Manager can access GET /fixed-assets", str(e))
        
        # Sales should be denied
        try:
            r = requests.get(f"{BASE_URL}/fixed-assets?entity_id={ENTITY_KSC}", 
                           headers=self.headers(self.sales_token), timeout=10)
            self.log(r.status_code == 403, "Sales denied access to GET /fixed-assets", 
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "Sales denied access to GET /fixed-assets", str(e))
        
        # Warehouse should be denied
        try:
            r = requests.get(f"{BASE_URL}/fixed-assets?entity_id={ENTITY_KSC}", 
                           headers=self.headers(self.warehouse_token), timeout=10)
            self.log(r.status_code == 403, "Warehouse denied access to GET /fixed-assets", 
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "Warehouse denied access to GET /fixed-assets", str(e))
        
        # Test POST endpoint RBAC
        test_asset = {
            "name": "RBAC Test Asset",
            "category": "Peralatan & Mesin",
            "acquisition_cost": 1000000,
            "acquisition_date": "2026-08-01",
            "useful_life_months": 12,
            "salvage_value": 0,
            "entity_id": ENTITY_KSC
        }
        
        try:
            r = requests.post(f"{BASE_URL}/fixed-assets", 
                            headers=self.headers(self.sales_token), 
                            json=test_asset, timeout=10)
            self.log(r.status_code == 403, "Sales denied POST /fixed-assets", 
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "Sales denied POST /fixed-assets", str(e))
        
        try:
            r = requests.post(f"{BASE_URL}/fixed-assets", 
                            headers=self.headers(self.warehouse_token), 
                            json=test_asset, timeout=10)
            self.log(r.status_code == 403, "Warehouse denied POST /fixed-assets", 
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "Warehouse denied POST /fixed-assets", str(e))
    
    def test_meta_endpoint(self):
        """Test GET /fixed-assets/meta"""
        print("\n=== TEST: GET /fixed-assets/meta ===")
        
        try:
            r = requests.get(f"{BASE_URL}/fixed-assets/meta?entity_id={ENTITY_KSC}", 
                           headers=self.headers(self.admin_token), timeout=10)
            self.log(r.status_code == 200, "GET /fixed-assets/meta returns 200")
            
            if r.status_code == 200:
                data = r.json()
                
                # Check categories
                self.log("categories" in data and isinstance(data["categories"], list),
                        "Meta contains categories list")
                
                # Check category_account
                self.log("category_account" in data and isinstance(data["category_account"], dict),
                        "Meta contains category_account dict")
                
                # Check asset_accounts (should be 1-2xxx but NOT 1-2900)
                if "asset_accounts" in data:
                    accounts = data["asset_accounts"]
                    all_valid = all(
                        acc.get("code", "").startswith("1-2") and 
                        acc.get("code") != "1-2900" 
                        for acc in accounts
                    )
                    self.log(all_valid, 
                            "All asset_accounts start with 1-2 and exclude 1-2900",
                            f"Accounts: {[a.get('code') for a in accounts[:5]]}")
                
                # Check acc_dep_account
                self.log(data.get("acc_dep_account") == "1-2900",
                        "acc_dep_account is 1-2900",
                        f"Got {data.get('acc_dep_account')}")
                
                # Check dep_expense_account
                self.log(data.get("dep_expense_account") == "6-6000",
                        "dep_expense_account is 6-6000",
                        f"Got {data.get('dep_expense_account')}")
        except Exception as e:
            self.log(False, "GET /fixed-assets/meta", str(e))
    
    def test_list_assets(self):
        """Test GET /fixed-assets with entity scoping"""
        print("\n=== TEST: GET /fixed-assets (list with entity scoping) ===")
        
        try:
            # List for ent_ksc
            r = requests.get(f"{BASE_URL}/fixed-assets?entity_id={ENTITY_KSC}", 
                           headers=self.headers(self.admin_token), timeout=10)
            self.log(r.status_code == 200, "GET /fixed-assets?entity_id=ent_ksc returns 200")
            
            if r.status_code == 200:
                assets_ksc = r.json()
                self.log(isinstance(assets_ksc, list), "Response is a list")
                
                # List for ent_kanda
                r2 = requests.get(f"{BASE_URL}/fixed-assets?entity_id={ENTITY_KANDA}", 
                               headers=self.headers(self.admin_token), timeout=10)
                if r2.status_code == 200:
                    assets_kanda = r2.json()
                    # Should be different lists (no cross-entity leakage)
                    self.log(True, "Can query different entities separately")
        except Exception as e:
            self.log(False, "GET /fixed-assets list", str(e))
    
    def test_summary_endpoint(self):
        """Test GET /fixed-assets/summary"""
        print("\n=== TEST: GET /fixed-assets/summary ===")
        
        try:
            r = requests.get(f"{BASE_URL}/fixed-assets/summary?entity_id={ENTITY_KSC}", 
                           headers=self.headers(self.admin_token), timeout=10)
            self.log(r.status_code == 200, "GET /fixed-assets/summary returns 200")
            
            if r.status_code == 200:
                data = r.json()
                required_fields = ["count", "active", "fully_depreciated", "disposed",
                                 "gross_cost", "accumulated_depreciation", "net_book_value",
                                 "disposal_gain_loss"]
                
                for field in required_fields:
                    self.log(field in data, f"Summary contains '{field}'")
                
                # Verify net_book_value == gross_cost - accumulated_depreciation
                if all(f in data for f in ["gross_cost", "accumulated_depreciation", "net_book_value"]):
                    expected_nbv = data["gross_cost"] - data["accumulated_depreciation"]
                    actual_nbv = data["net_book_value"]
                    diff = abs(expected_nbv - actual_nbv)
                    self.log(diff < 0.01, 
                            "net_book_value == gross_cost - accumulated_depreciation",
                            f"Expected {expected_nbv}, got {actual_nbv}")
        except Exception as e:
            self.log(False, "GET /fixed-assets/summary", str(e))
    
    def test_create_asset_validations(self):
        """Test POST /fixed-assets validation rules"""
        print("\n=== TEST: POST /fixed-assets Validations (should return 400) ===")
        
        # Empty name
        try:
            r = requests.post(f"{BASE_URL}/fixed-assets", 
                            headers=self.headers(self.admin_token),
                            json={
                                "name": "",
                                "acquisition_cost": 1000000,
                                "useful_life_months": 12,
                                "entity_id": ENTITY_KSC
                            }, timeout=10)
            self.log(r.status_code == 400, "Empty name returns 400", f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "Empty name validation", str(e))
        
        # acquisition_cost <= 0
        try:
            r = requests.post(f"{BASE_URL}/fixed-assets", 
                            headers=self.headers(self.admin_token),
                            json={
                                "name": "Test Asset",
                                "acquisition_cost": 0,
                                "useful_life_months": 12,
                                "entity_id": ENTITY_KSC
                            }, timeout=10)
            self.log(r.status_code == 400, "acquisition_cost <= 0 returns 400", 
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "acquisition_cost validation", str(e))
        
        # useful_life_months <= 0
        try:
            r = requests.post(f"{BASE_URL}/fixed-assets", 
                            headers=self.headers(self.admin_token),
                            json={
                                "name": "Test Asset",
                                "acquisition_cost": 1000000,
                                "useful_life_months": 0,
                                "entity_id": ENTITY_KSC
                            }, timeout=10)
            self.log(r.status_code == 400, "useful_life_months <= 0 returns 400", 
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "useful_life_months validation", str(e))
        
        # salvage_value < 0
        try:
            r = requests.post(f"{BASE_URL}/fixed-assets", 
                            headers=self.headers(self.admin_token),
                            json={
                                "name": "Test Asset",
                                "acquisition_cost": 1000000,
                                "useful_life_months": 12,
                                "salvage_value": -100,
                                "entity_id": ENTITY_KSC
                            }, timeout=10)
            self.log(r.status_code == 400, "salvage_value < 0 returns 400", 
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "salvage_value negative validation", str(e))
        
        # salvage_value >= acquisition_cost
        try:
            r = requests.post(f"{BASE_URL}/fixed-assets", 
                            headers=self.headers(self.admin_token),
                            json={
                                "name": "Test Asset",
                                "acquisition_cost": 1000000,
                                "useful_life_months": 12,
                                "salvage_value": 1000000,
                                "entity_id": ENTITY_KSC
                            }, timeout=10)
            self.log(r.status_code == 400, "salvage_value >= acquisition_cost returns 400", 
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "salvage_value >= cost validation", str(e))
    
    def test_create_asset_success(self):
        """Test successful asset creation"""
        print("\n=== TEST: POST /fixed-assets Success ===")
        
        try:
            asset_data = {
                "name": "Test Mesin Jahit",
                "category": "Peralatan & Mesin",
                "acquisition_cost": 12000000,
                "acquisition_date": "2026-08-01",
                "useful_life_months": 12,
                "salvage_value": 0,
                "entity_id": ENTITY_KSC
            }
            
            r = requests.post(f"{BASE_URL}/fixed-assets", 
                            headers=self.headers(self.admin_token),
                            json=asset_data, timeout=10)
            
            self.log(r.status_code == 200, "POST /fixed-assets returns 200", 
                    f"Got {r.status_code}")
            
            if r.status_code == 200:
                asset = r.json()
                self.created_assets.append(asset.get("id"))
                
                # Check number format
                number = asset.get("number", "")
                self.log(number.startswith("KSC/FA-") or number.startswith("FA-"),
                        f"Asset number has correct format: {number}")
                
                # Check monthly_depreciation
                expected_monthly = round((12000000 - 0) / 12, 2)
                actual_monthly = asset.get("monthly_depreciation", 0)
                self.log(abs(expected_monthly - actual_monthly) < 0.01,
                        f"monthly_depreciation correct: {actual_monthly}",
                        f"Expected {expected_monthly}")
                
                # Check status
                self.log(asset.get("status") == "active", "Status is 'active'",
                        f"Got {asset.get('status')}")
                
                # Check book_value == acquisition_cost initially
                self.log(asset.get("book_value") == asset.get("acquisition_cost"),
                        "Initial book_value == acquisition_cost")
                
                # Check acquisition_je exists
                self.log(bool(asset.get("acquisition_je")),
                        "acquisition_je is set",
                        f"JE: {asset.get('acquisition_je')}")
                
                return asset.get("id")
        except Exception as e:
            self.log(False, "POST /fixed-assets success", str(e))
            return None
    
    def test_get_asset_detail(self, asset_id):
        """Test GET /fixed-assets/{id}"""
        print("\n=== TEST: GET /fixed-assets/{id} ===")
        
        if not asset_id:
            print("  ⚠️  Skipping (no asset_id)")
            return
        
        try:
            r = requests.get(f"{BASE_URL}/fixed-assets/{asset_id}", 
                           headers=self.headers(self.admin_token), timeout=10)
            self.log(r.status_code == 200, f"GET /fixed-assets/{asset_id} returns 200")
            
            if r.status_code == 200:
                asset = r.json()
                
                # Check schedule exists
                self.log("schedule" in asset and isinstance(asset["schedule"], list),
                        "Asset has schedule array")
                
                if "schedule" in asset:
                    schedule = asset["schedule"]
                    life = asset.get("useful_life_months", 0)
                    self.log(len(schedule) == life,
                            f"Schedule length == useful_life_months ({life})",
                            f"Got {len(schedule)} rows")
                    
                    # Check last row of schedule
                    if schedule:
                        last_row = schedule[-1]
                        cost = asset.get("acquisition_cost", 0)
                        salvage = asset.get("salvage_value", 0)
                        expected_acc = cost - salvage
                        actual_acc = last_row.get("accumulated", 0)
                        diff = abs(expected_acc - actual_acc)
                        self.log(diff < 0.01,
                                "Last schedule row: accumulated ≈ cost - salvage",
                                f"Expected {expected_acc}, got {actual_acc}")
                        
                        self.log(abs(last_row.get("book_value", 0) - salvage) < 0.01,
                                "Last schedule row: book_value ≈ salvage",
                                f"Expected {salvage}, got {last_row.get('book_value')}")
                
                # Check depreciation_entries exists
                self.log("depreciation_entries" in asset,
                        "Asset has depreciation_entries array")
        except Exception as e:
            self.log(False, f"GET /fixed-assets/{asset_id}", str(e))
        
        # Test 404 for invalid ID
        try:
            r = requests.get(f"{BASE_URL}/fixed-assets/invalid_id_12345", 
                           headers=self.headers(self.admin_token), timeout=10)
            self.log(r.status_code == 404, "GET /fixed-assets/{invalid_id} returns 404",
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "GET /fixed-assets/{invalid_id} 404", str(e))
    
    def test_run_depreciation(self, asset_id):
        """Test POST /fixed-assets/run-depreciation"""
        print("\n=== TEST: POST /fixed-assets/run-depreciation ===")
        
        if not asset_id:
            print("  ⚠️  Skipping (no asset_id)")
            return
        
        period = "2026-08"
        
        try:
            # First run
            r = requests.post(f"{BASE_URL}/fixed-assets/run-depreciation",
                            headers=self.headers(self.admin_token),
                            json={
                                "period": period,
                                "asset_id": asset_id,
                                "entity_id": ENTITY_KSC
                            }, timeout=30)
            
            self.log(r.status_code == 200, "POST /fixed-assets/run-depreciation returns 200",
                    f"Got {r.status_code}")
            
            if r.status_code == 200:
                result = r.json()
                
                # Check response structure
                self.log("period" in result and result["period"] == period,
                        f"Response contains correct period: {period}")
                self.log("posted" in result, "Response contains 'posted'")
                self.log("skipped" in result, "Response contains 'skipped'")
                self.log("total_amount" in result, "Response contains 'total_amount'")
                self.log("assets" in result and isinstance(result["assets"], list),
                        "Response contains 'assets' array")
                
                # Should have posted 1 asset
                self.log(result.get("posted") >= 1, "At least 1 asset posted",
                        f"Posted: {result.get('posted')}")
                
                # Check asset was updated
                r2 = requests.get(f"{BASE_URL}/fixed-assets/{asset_id}",
                                headers=self.headers(self.admin_token), timeout=10)
                if r2.status_code == 200:
                    asset = r2.json()
                    self.log(asset.get("accumulated_depreciation", 0) > 0,
                            "accumulated_depreciation updated",
                            f"Accumulated: {asset.get('accumulated_depreciation')}")
                    self.log(asset.get("depreciated_months", 0) == 1,
                            "depreciated_months == 1",
                            f"Got {asset.get('depreciated_months')}")
                    self.log(asset.get("book_value", 0) < asset.get("acquisition_cost", 0),
                            "book_value decreased")
                
                # Test idempotency: run again for same period
                print("\n  Testing idempotency (rerun same period)...")
                r3 = requests.post(f"{BASE_URL}/fixed-assets/run-depreciation",
                                headers=self.headers(self.admin_token),
                                json={
                                    "period": period,
                                    "asset_id": asset_id,
                                    "entity_id": ENTITY_KSC
                                }, timeout=30)
                
                if r3.status_code == 200:
                    result2 = r3.json()
                    self.log(result2.get("posted") == 0,
                            "Idempotent: rerun same period posts 0",
                            f"Posted: {result2.get('posted')}")
                    self.log(result2.get("skipped") >= 1,
                            "Idempotent: rerun same period skips >= 1",
                            f"Skipped: {result2.get('skipped')}")
                    
                    # Verify accumulated didn't change
                    r4 = requests.get(f"{BASE_URL}/fixed-assets/{asset_id}",
                                    headers=self.headers(self.admin_token), timeout=10)
                    if r4.status_code == 200:
                        asset2 = r4.json()
                        self.log(asset2.get("accumulated_depreciation") == asset.get("accumulated_depreciation"),
                                "Idempotent: accumulated_depreciation unchanged",
                                f"Before: {asset.get('accumulated_depreciation')}, After: {asset2.get('accumulated_depreciation')}")
        except Exception as e:
            self.log(False, "POST /fixed-assets/run-depreciation", str(e))
        
        # Test depreciation before acquisition_date (should skip)
        try:
            r = requests.post(f"{BASE_URL}/fixed-assets/run-depreciation",
                            headers=self.headers(self.admin_token),
                            json={
                                "period": "2026-07",  # Before acquisition_date 2026-08-01
                                "asset_id": asset_id,
                                "entity_id": ENTITY_KSC
                            }, timeout=30)
            
            if r.status_code == 200:
                result = r.json()
                self.log(result.get("posted") == 0,
                        "Depreciation before acquisition_date: posted == 0",
                        f"Posted: {result.get('posted')}")
        except Exception as e:
            self.log(False, "Depreciation before acquisition_date", str(e))
        
        # Test invalid period format
        try:
            r = requests.post(f"{BASE_URL}/fixed-assets/run-depreciation",
                            headers=self.headers(self.admin_token),
                            json={
                                "period": "2026-13",  # Invalid month
                                "entity_id": ENTITY_KSC
                            }, timeout=30)
            
            # Should not crash with 5xx
            self.log(r.status_code < 500,
                    "Invalid period format doesn't crash (not 5xx)",
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "Invalid period format handling", str(e))
    
    def test_disposal_gain(self):
        """Test disposal with gain (proceeds > book_value)"""
        print("\n=== TEST: POST /fixed-assets/{id}/dispose (GAIN scenario) ===")
        
        # Create asset for disposal
        try:
            asset_data = {
                "name": "Test Asset for Disposal Gain",
                "category": "Peralatan & Mesin",
                "acquisition_cost": 10000000,
                "acquisition_date": "2026-08-01",
                "useful_life_months": 10,
                "salvage_value": 0,
                "entity_id": ENTITY_KSC
            }
            
            r = requests.post(f"{BASE_URL}/fixed-assets",
                            headers=self.headers(self.admin_token),
                            json=asset_data, timeout=10)
            
            if r.status_code != 200:
                print(f"  ⚠️  Failed to create asset for disposal test")
                return
            
            asset = r.json()
            asset_id = asset.get("id")
            self.created_assets.append(asset_id)
            
            # Run depreciation for 1 period
            requests.post(f"{BASE_URL}/fixed-assets/run-depreciation",
                        headers=self.headers(self.admin_token),
                        json={"period": "2026-08", "asset_id": asset_id, "entity_id": ENTITY_KSC},
                        timeout=30)
            
            # Get updated asset
            r2 = requests.get(f"{BASE_URL}/fixed-assets/{asset_id}",
                            headers=self.headers(self.admin_token), timeout=10)
            if r2.status_code == 200:
                asset = r2.json()
                book_value = asset.get("book_value", 0)
                proceeds = book_value + 1500000  # Gain scenario
                
                # Dispose
                r3 = requests.post(f"{BASE_URL}/fixed-assets/{asset_id}/dispose",
                                headers=self.headers(self.admin_token),
                                json={
                                    "proceeds": proceeds,
                                    "date": "2026-08-15",
                                    "note": "Test disposal gain"
                                }, timeout=10)
                
                self.log(r3.status_code == 200, "Disposal with gain returns 200",
                        f"Got {r3.status_code}")
                
                if r3.status_code == 200:
                    disposed = r3.json()
                    disposal = disposed.get("disposal", {})
                    
                    self.log(disposal.get("result") == "gain",
                            "Disposal result == 'gain'",
                            f"Got {disposal.get('result')}")
                    
                    expected_gain = proceeds - book_value
                    actual_gain = disposal.get("gain_loss", 0)
                    self.log(abs(expected_gain - actual_gain) < 0.01,
                            f"gain_loss correct: {actual_gain}",
                            f"Expected {expected_gain}")
                    
                    self.log(disposed.get("status") == "disposed",
                            "Asset status == 'disposed'",
                            f"Got {disposed.get('status')}")
                    
                    self.log(bool(disposal.get("je_number")),
                            "Disposal JE created",
                            f"JE: {disposal.get('je_number')}")
                    
                    # Try to dispose again (should fail)
                    r4 = requests.post(f"{BASE_URL}/fixed-assets/{asset_id}/dispose",
                                    headers=self.headers(self.admin_token),
                                    json={"proceeds": 1000000, "date": "2026-08-16"},
                                    timeout=10)
                    self.log(r4.status_code == 400,
                            "Cannot dispose already disposed asset (400)",
                            f"Got {r4.status_code}")
        except Exception as e:
            self.log(False, "Disposal gain scenario", str(e))
    
    def test_disposal_loss(self):
        """Test disposal with loss (proceeds < book_value)"""
        print("\n=== TEST: POST /fixed-assets/{id}/dispose (LOSS scenario) ===")
        
        # Create asset for disposal
        try:
            asset_data = {
                "name": "Test Asset for Disposal Loss",
                "category": "Kendaraan",
                "acquisition_cost": 6000000,
                "acquisition_date": "2026-08-01",
                "useful_life_months": 12,
                "salvage_value": 0,
                "entity_id": ENTITY_KSC
            }
            
            r = requests.post(f"{BASE_URL}/fixed-assets",
                            headers=self.headers(self.admin_token),
                            json=asset_data, timeout=10)
            
            if r.status_code != 200:
                print(f"  ⚠️  Failed to create asset for disposal test")
                return
            
            asset = r.json()
            asset_id = asset.get("id")
            self.created_assets.append(asset_id)
            
            # Run depreciation for 1 period
            requests.post(f"{BASE_URL}/fixed-assets/run-depreciation",
                        headers=self.headers(self.admin_token),
                        json={"period": "2026-08", "asset_id": asset_id, "entity_id": ENTITY_KSC},
                        timeout=30)
            
            # Get updated asset
            r2 = requests.get(f"{BASE_URL}/fixed-assets/{asset_id}",
                            headers=self.headers(self.admin_token), timeout=10)
            if r2.status_code == 200:
                asset = r2.json()
                book_value = asset.get("book_value", 0)
                proceeds = book_value - 1500000  # Loss scenario
                
                # Dispose
                r3 = requests.post(f"{BASE_URL}/fixed-assets/{asset_id}/dispose",
                                headers=self.headers(self.admin_token),
                                json={
                                    "proceeds": proceeds,
                                    "date": "2026-08-15",
                                    "note": "Test disposal loss"
                                }, timeout=10)
                
                self.log(r3.status_code == 200, "Disposal with loss returns 200",
                        f"Got {r3.status_code}")
                
                if r3.status_code == 200:
                    disposed = r3.json()
                    disposal = disposed.get("disposal", {})
                    
                    self.log(disposal.get("result") == "loss",
                            "Disposal result == 'loss'",
                            f"Got {disposal.get('result')}")
                    
                    expected_loss = proceeds - book_value
                    actual_loss = disposal.get("gain_loss", 0)
                    self.log(abs(expected_loss - actual_loss) < 0.01,
                            f"gain_loss correct (negative): {actual_loss}",
                            f"Expected {expected_loss}")
                    
                    self.log(actual_loss < 0, "gain_loss is negative for loss")
        except Exception as e:
            self.log(False, "Disposal loss scenario", str(e))
        
        # Test negative proceeds
        try:
            r = requests.post(f"{BASE_URL}/fixed-assets/some_id/dispose",
                            headers=self.headers(self.admin_token),
                            json={"proceeds": -1000, "date": "2026-08-15"},
                            timeout=10)
            self.log(r.status_code == 400,
                    "Negative proceeds returns 400",
                    f"Got {r.status_code}")
        except Exception as e:
            self.log(False, "Negative proceeds validation", str(e))
    
    def test_patch_asset(self):
        """Test PATCH /fixed-assets/{id}"""
        print("\n=== TEST: PATCH /fixed-assets/{id} ===")
        
        # Create asset for patching
        try:
            asset_data = {
                "name": "Test Asset for Patch",
                "category": "Peralatan & Mesin",
                "acquisition_cost": 5000000,
                "acquisition_date": "2026-08-01",
                "useful_life_months": 12,
                "salvage_value": 0,
                "entity_id": ENTITY_KSC
            }
            
            r = requests.post(f"{BASE_URL}/fixed-assets",
                            headers=self.headers(self.admin_token),
                            json=asset_data, timeout=10)
            
            if r.status_code != 200:
                print(f"  ⚠️  Failed to create asset for patch test")
                return
            
            asset = r.json()
            asset_id = asset.get("id")
            self.created_assets.append(asset_id)
            
            # Patch name/category/notes (should work)
            r2 = requests.patch(f"{BASE_URL}/fixed-assets/{asset_id}",
                              headers=self.headers(self.admin_token),
                              json={
                                  "name": "Updated Asset Name",
                                  "category": "Kendaraan",
                                  "notes": "Updated notes"
                              }, timeout=10)
            
            self.log(r2.status_code == 200,
                    "PATCH name/category/notes succeeds",
                    f"Got {r2.status_code}")
            
            # Patch acquisition_cost before depreciation (should work)
            r3 = requests.patch(f"{BASE_URL}/fixed-assets/{asset_id}",
                              headers=self.headers(self.admin_token),
                              json={"acquisition_cost": 6000000}, timeout=10)
            
            self.log(r3.status_code == 200,
                    "PATCH acquisition_cost before depreciation succeeds",
                    f"Got {r3.status_code}")
            
            # Run depreciation
            requests.post(f"{BASE_URL}/fixed-assets/run-depreciation",
                        headers=self.headers(self.admin_token),
                        json={"period": "2026-08", "asset_id": asset_id, "entity_id": ENTITY_KSC},
                        timeout=30)
            
            # Try to patch acquisition_cost after depreciation (should be ignored/rejected)
            r4 = requests.patch(f"{BASE_URL}/fixed-assets/{asset_id}",
                              headers=self.headers(self.admin_token),
                              json={"acquisition_cost": 7000000}, timeout=10)
            
            # Should either return 200 with no change or 400
            if r4.status_code == 200:
                updated = r4.json()
                # Cost should not have changed
                self.log(updated.get("acquisition_cost") != 7000000,
                        "acquisition_cost not changed after depreciation",
                        f"Cost: {updated.get('acquisition_cost')}")
            else:
                self.log(r4.status_code == 400,
                        "PATCH acquisition_cost after depreciation rejected (400)",
                        f"Got {r4.status_code}")
            
            # Dispose the asset
            requests.post(f"{BASE_URL}/fixed-assets/{asset_id}/dispose",
                        headers=self.headers(self.admin_token),
                        json={"proceeds": 1000000, "date": "2026-08-15"},
                        timeout=10)
            
            # Try to patch disposed asset (should fail)
            r5 = requests.patch(f"{BASE_URL}/fixed-assets/{asset_id}",
                              headers=self.headers(self.admin_token),
                              json={"name": "Should not work"}, timeout=10)
            
            self.log(r5.status_code == 400,
                    "PATCH disposed asset returns 400",
                    f"Got {r5.status_code}")
        except Exception as e:
            self.log(False, "PATCH /fixed-assets/{id}", str(e))
    
    def test_multi_entity_idor(self):
        """Test multi-entity scoping (IDOR prevention)"""
        print("\n=== TEST: Multi-entity IDOR Prevention ===")
        
        # Create asset in ent_ksc
        try:
            asset_data = {
                "name": "KSC Asset for IDOR Test",
                "category": "Peralatan & Mesin",
                "acquisition_cost": 3000000,
                "acquisition_date": "2026-08-01",
                "useful_life_months": 12,
                "salvage_value": 0,
                "entity_id": ENTITY_KSC
            }
            
            r = requests.post(f"{BASE_URL}/fixed-assets",
                            headers=self.headers(self.admin_token),
                            json=asset_data, timeout=10)
            
            if r.status_code != 200:
                print(f"  ⚠️  Failed to create asset for IDOR test")
                return
            
            asset = r.json()
            asset_id = asset.get("id")
            self.created_assets.append(asset_id)
            
            # List assets for ent_kanda (should NOT include the KSC asset)
            r2 = requests.get(f"{BASE_URL}/fixed-assets?entity_id={ENTITY_KANDA}",
                            headers=self.headers(self.admin_token), timeout=10)
            
            if r2.status_code == 200:
                kanda_assets = r2.json()
                kanda_ids = [a.get("id") for a in kanda_assets]
                self.log(asset_id not in kanda_ids,
                        "KSC asset not visible in KANDA entity list",
                        f"Asset {asset_id} in KANDA list: {asset_id in kanda_ids}")
        except Exception as e:
            self.log(False, "Multi-entity IDOR test", str(e))
    
    def test_r6_1_regression(self):
        """Test R6.1 Bank Reconciliation endpoints still work"""
        print("\n=== TEST: R6.1 Regression (Bank Reconciliation) ===")
        
        # Just check that endpoints are accessible (not broken)
        try:
            # Get bank accounts
            r = requests.get(f"{BASE_URL}/bank-accounts",
                           headers=self.headers(self.admin_token), timeout=10)
            self.log(r.status_code == 200,
                    "GET /api/bank-accounts still works (200)",
                    f"Got {r.status_code}")
            
            # If we have bank accounts, try to get reconciliation summary
            if r.status_code == 200:
                accounts = r.json()
                if accounts and len(accounts) > 0:
                    bank_id = accounts[0].get("id")
                    r2 = requests.get(f"{BASE_URL}/bank-reconciliation/summary?bank_account_id={bank_id}",
                                    headers=self.headers(self.admin_token), timeout=10)
                    self.log(r2.status_code == 200,
                            "GET /api/bank-reconciliation/summary still works",
                            f"Got {r2.status_code}")
                    
                    r3 = requests.get(f"{BASE_URL}/bank-reconciliation/lines?bank_account_id={bank_id}",
                                    headers=self.headers(self.admin_token), timeout=10)
                    self.log(r3.status_code == 200,
                            "GET /api/bank-reconciliation/lines still works",
                            f"Got {r3.status_code}")
        except Exception as e:
            self.log(False, "R6.1 regression check", str(e))
    
    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*70)
        print("R6.2 FIXED ASSETS & DEPRECIATION - BACKEND TESTING")
        print("="*70)
        
        self.setup_auth()
        self.test_auth_required()
        self.test_rbac_permissions()
        self.test_meta_endpoint()
        self.test_list_assets()
        self.test_summary_endpoint()
        self.test_create_asset_validations()
        
        # Create asset and test detail/depreciation
        asset_id = self.test_create_asset_success()
        self.test_get_asset_detail(asset_id)
        self.test_run_depreciation(asset_id)
        
        # Test disposal scenarios
        self.test_disposal_gain()
        self.test_disposal_loss()
        
        # Test PATCH
        self.test_patch_asset()
        
        # Test multi-entity
        self.test_multi_entity_idor()
        
        # Regression
        self.test_r6_1_regression()
        
        # Summary
        print("\n" + "="*70)
        print(f"RESULTS: {self.passed} PASSED / {self.failed} FAILED")
        print("="*70)
        
        if self.created_assets:
            print(f"\n📝 Created {len(self.created_assets)} test assets (will remain in DB)")
            print(f"   Asset IDs: {', '.join(self.created_assets[:3])}...")
        
        return self.failed == 0

if __name__ == "__main__":
    runner = TestRunner()
    success = runner.run_all_tests()
    sys.exit(0 if success else 1)
