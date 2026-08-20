#!/usr/bin/env python3
"""
Backend API Test — Laporan Perubahan Ekuitas (Statement of Changes in Equity)
==============================================================================
Tests the new 4th financial statement endpoint.

Test Coverage:
1. GET /api/finance/equity-changes → HTTP 200 with proper structure
2. Verify calculations: movement_total == end_total - begin_total
3. Verify component calculations: movement == end - begin
4. Verify "__pl__" component exists (Laba Rugi Periode Berjalan)
5. RECONCILIATION: equity-changes end_total == balance-sheet equity_total
6. CSV export endpoint
7. AUTH: 401/403 without token
"""
import os
import sys
import requests
from datetime import datetime

BASE = "https://kn123-backend-fixes.preview.emergentagent.com"
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


class EquityChangesTest:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.entity_id = "ent_ksc"
        self.start = "2026-01-01"
        self.end = "2026-12-31"
        
    def login(self):
        """Login as admin"""
        try:
            r = self.session.post(
                f"{API}/auth/login",
                json={"email": "admin@kainnusantara.id", "password": "demo12345"},
                timeout=30
            )
            if r.status_code != 200:
                bad(f"Login failed: {r.status_code} {r.text[:100]}")
                return False
            data = r.json()
            self.token = data.get("token")
            if not self.token:
                bad("Login response missing 'token' field")
                return False
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            ok("Login admin@kainnusantara.id")
            return True
        except Exception as e:
            bad(f"Login exception: {e}")
            return False
    
    def test_equity_changes_endpoint(self):
        """TEST 1: GET /api/finance/equity-changes returns 200 with proper structure"""
        info("\n=== TEST 1: Equity Changes Endpoint Structure ===")
        
        try:
            r = self.session.get(
                f"{API}/finance/equity-changes",
                params={"entity_id": self.entity_id, "start": self.start, "end": self.end},
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Equity changes endpoint failed: {r.status_code} {r.text[:200]}")
                return None
            
            ok("GET /api/finance/equity-changes returns 200")
            
            data = r.json()
            
            # Check required fields
            required_fields = ["period", "components", "begin_total", "movement_total", "end_total", "net_income"]
            missing = [f for f in required_fields if f not in data]
            if missing:
                bad(f"Missing required fields: {missing}")
                return None
            ok(f"Response contains all required fields: {required_fields}")
            
            # Check period
            period = data.get("period", {})
            if period.get("start") == self.start and period.get("end") == self.end:
                ok(f"Period correct: {self.start} to {self.end}")
            else:
                bad(f"Period mismatch: expected {self.start}-{self.end}, got {period}")
            
            # Check components structure
            components = data.get("components", [])
            if not components:
                bad("No components in response")
                return None
            
            ok(f"Found {len(components)} equity components")
            
            # Verify each component has required fields
            for i, comp in enumerate(components):
                required_comp_fields = ["code", "name", "begin", "movement", "end"]
                missing_comp = [f for f in required_comp_fields if f not in comp]
                if missing_comp:
                    bad(f"Component {i} missing fields: {missing_comp}")
                    return None
            
            ok("All components have required fields (code, name, begin, movement, end)")
            
            return data
            
        except Exception as e:
            bad(f"Equity changes endpoint exception: {e}")
            return None
    
    def test_calculations(self, data):
        """TEST 2: Verify calculations are correct"""
        info("\n=== TEST 2: Verify Calculations ===")
        
        try:
            begin_total = float(data.get("begin_total", 0))
            movement_total = float(data.get("movement_total", 0))
            end_total = float(data.get("end_total", 0))
            
            # Test: movement_total == round(end_total - begin_total, 2)
            expected_movement = round(end_total - begin_total, 2)
            if abs(movement_total - expected_movement) < 0.01:
                ok(f"movement_total ({movement_total}) == end_total - begin_total ({expected_movement})")
            else:
                bad(f"movement_total ({movement_total}) != end_total - begin_total ({expected_movement})")
            
            # Test each component: movement == round(end - begin, 2)
            components = data.get("components", [])
            all_correct = True
            for comp in components:
                begin = float(comp.get("begin", 0))
                movement = float(comp.get("movement", 0))
                end = float(comp.get("end", 0))
                expected_mov = round(end - begin, 2)
                
                if abs(movement - expected_mov) >= 0.01:
                    bad(f"Component {comp['code']}: movement ({movement}) != end - begin ({expected_mov})")
                    all_correct = False
            
            if all_correct:
                ok(f"All {len(components)} components have correct movement calculations")
            
            return True
            
        except Exception as e:
            bad(f"Calculation verification exception: {e}")
            return False
    
    def test_pl_component(self, data):
        """TEST 3: Verify __pl__ component exists"""
        info("\n=== TEST 3: Verify P&L Component ===")
        
        try:
            components = data.get("components", [])
            pl_comp = next((c for c in components if c.get("code") == "__pl__"), None)
            
            if not pl_comp:
                bad("Component with code '__pl__' not found")
                return False
            
            ok(f"Found __pl__ component: {pl_comp.get('name')}")
            
            # Check name contains "Laba" or "Rugi"
            name = pl_comp.get("name", "")
            if "Laba" in name or "Rugi" in name:
                ok(f"__pl__ component name is appropriate: '{name}'")
            else:
                bad(f"__pl__ component name doesn't contain 'Laba' or 'Rugi': '{name}'")
            
            return True
            
        except Exception as e:
            bad(f"P&L component verification exception: {e}")
            return False
    
    def test_reconciliation(self, equity_data):
        """TEST 4: RECONCILIATION with balance sheet"""
        info("\n=== TEST 4: Reconciliation with Balance Sheet ===")
        
        try:
            # Get balance sheet for same date
            r = self.session.get(
                f"{API}/finance/balance-sheet",
                params={"entity_id": self.entity_id, "as_of": self.end},
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"Balance sheet endpoint failed: {r.status_code} {r.text[:200]}")
                return False
            
            ok("GET /api/finance/balance-sheet returns 200")
            
            bs_data = r.json()
            bs_equity_total = float(bs_data.get("equity_total", 0))
            eq_end_total = float(equity_data.get("end_total", 0))
            
            # They must match
            if abs(bs_equity_total - eq_end_total) < 0.01:
                ok(f"RECONCILIATION PASSED: Balance sheet equity_total ({bs_equity_total}) == equity-changes end_total ({eq_end_total})")
            else:
                bad(f"RECONCILIATION FAILED: Balance sheet equity_total ({bs_equity_total}) != equity-changes end_total ({eq_end_total})")
            
            return True
            
        except Exception as e:
            bad(f"Reconciliation exception: {e}")
            return False
    
    def test_csv_export(self):
        """TEST 5: CSV export endpoint"""
        info("\n=== TEST 5: CSV Export ===")
        
        try:
            r = self.session.get(
                f"{API}/finance/equity-changes/export.csv",
                params={"entity_id": self.entity_id, "start": self.start, "end": self.end},
                timeout=30
            )
            
            if r.status_code != 200:
                bad(f"CSV export failed: {r.status_code} {r.text[:200]}")
                return False
            
            ok("GET /api/finance/equity-changes/export.csv returns 200")
            
            # Check content type
            content_type = r.headers.get("content-type", "")
            if "csv" in content_type.lower() or "text" in content_type.lower():
                ok(f"Content-Type is CSV: {content_type}")
            else:
                bad(f"Content-Type is not CSV: {content_type}")
            
            # Check content starts with expected header
            content = r.text
            if "Laporan Perubahan Ekuitas" in content:
                ok("CSV content starts with 'Laporan Perubahan Ekuitas'")
            else:
                bad("CSV content doesn't start with expected header")
            
            # Check it has some data
            lines = content.strip().split("\n")
            if len(lines) > 3:
                ok(f"CSV has {len(lines)} lines")
            else:
                bad(f"CSV has only {len(lines)} lines (expected more)")
            
            return True
            
        except Exception as e:
            bad(f"CSV export exception: {e}")
            return False
    
    def test_auth_protection(self):
        """TEST 6: Auth protection - 401/403 without token"""
        info("\n=== TEST 6: Auth Protection ===")
        
        try:
            # Create session without auth
            unauth_session = requests.Session()
            
            r = unauth_session.get(
                f"{API}/finance/equity-changes",
                params={"entity_id": self.entity_id, "start": self.start, "end": self.end},
                timeout=30
            )
            
            if r.status_code in [401, 403]:
                ok(f"Unauthenticated request returns {r.status_code} (correct)")
            else:
                bad(f"Unauthenticated request returns {r.status_code} (expected 401 or 403)")
            
            return True
            
        except Exception as e:
            bad(f"Auth protection test exception: {e}")
            return False
    
    def run_all_tests(self):
        """Run all backend tests"""
        print("\n" + "="*70)
        print("  BACKEND API TEST — Laporan Perubahan Ekuitas")
        print("="*70)
        
        if not self.login():
            return False
        
        # Test 1: Endpoint structure
        equity_data = self.test_equity_changes_endpoint()
        if not equity_data:
            return False
        
        # Test 2: Calculations
        self.test_calculations(equity_data)
        
        # Test 3: P&L component
        self.test_pl_component(equity_data)
        
        # Test 4: Reconciliation
        self.test_reconciliation(equity_data)
        
        # Test 5: CSV export
        self.test_csv_export()
        
        # Test 6: Auth protection
        self.test_auth_protection()
        
        return True


def main():
    tester = EquityChangesTest()
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
