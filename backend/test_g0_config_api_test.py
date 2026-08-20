#!/usr/bin/env python3
"""
Backend API Testing for FASE G-0 Configuration Center (Pusat Pengaturan)
Tests config API endpoints with permission validation
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://kn-deep-link.preview.emergentagent.com/api"

class ConfigAPITester:
    def __init__(self):
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.failures = []

    def run_test(self, name, method, endpoint, expected_status, token=None, data=None, params=None):
        """Run a single API test"""
        url = f"{BASE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return True, response.json()
                except Exception:
                    return True, {}
            else:
                self.failures.append(f"{name}: Expected {expected_status}, got {response.status_code}")
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    resp_json = response.json()
                    print(f"   Response: {resp_json}")
                    return False, resp_json
                except Exception:
                    print(f"   Response: {response.text[:200]}")
                    return False, {}

        except Exception as e:
            self.failures.append(f"{name}: {str(e)}")
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def login(self, role):
        """Login and get token for a role"""
        email = f"{role}@kainnusantara.id"
        password = "demo12345"
        
        success, response = self.run_test(
            f"Login as {role}",
            "POST",
            "/auth/login",
            200,
            data={"email": email, "password": password}
        )
        
        if success and 'token' in response:
            self.tokens[role] = response['token']
            return True
        return False

    def test_backend_1_registry_caps(self):
        """BACKEND-1: GET /api/config/registry - check caps and editable_count"""
        print("\n" + "="*70)
        print("BACKEND-1: Registry Caps & Editable Count")
        print("="*70)
        
        # Test admin
        success, response = self.run_test(
            "Admin GET /config/registry",
            "GET",
            "/config/registry",
            200,
            token=self.tokens.get('admin')
        )
        
        if success:
            caps = response.get('caps', {})
            editable_count = caps.get('editable_count', 0)
            settings_manage = caps.get('settings_manage', False)
            impact_apply = caps.get('impact_apply', False)
            
            print(f"   Admin caps: settings_manage={settings_manage}, impact_apply={impact_apply}, editable_count={editable_count}")
            
            if editable_count == 96 and settings_manage and impact_apply:
                print("   ✅ Admin has correct permissions (96 editable, both caps true)")
            else:
                self.failures.append(f"Admin caps incorrect: expected editable_count=96, got {editable_count}")
                print(f"   ❌ Admin caps incorrect: expected 96 editable, got {editable_count}")
        
        # Test manager
        success, response = self.run_test(
            "Manager GET /config/registry",
            "GET",
            "/config/registry",
            200,
            token=self.tokens.get('manager')
        )
        
        if success:
            caps = response.get('caps', {})
            editable_count = caps.get('editable_count', 0)
            settings_manage = caps.get('settings_manage', False)
            impact_apply = caps.get('impact_apply', False)
            
            print(f"   Manager caps: settings_manage={settings_manage}, impact_apply={impact_apply}, editable_count={editable_count}")
            
            if editable_count == 31 and not settings_manage and not impact_apply:
                print("   ✅ Manager has correct permissions (31 editable, both caps false)")
            else:
                self.failures.append(f"Manager caps incorrect: expected editable_count=31, got {editable_count}")
                print(f"   ❌ Manager caps incorrect: expected 31 editable, got {editable_count}")
        
        # Test sales
        success, response = self.run_test(
            "Sales GET /config/registry",
            "GET",
            "/config/registry",
            200,
            token=self.tokens.get('sales')
        )
        
        if success:
            caps = response.get('caps', {})
            editable_count = caps.get('editable_count', 0)
            
            print(f"   Sales editable_count: {editable_count}")
            
            if editable_count == 0:
                print("   ✅ Sales has correct permissions (0 editable)")
            else:
                self.failures.append(f"Sales caps incorrect: expected editable_count=0, got {editable_count}")
                print(f"   ❌ Sales caps incorrect: expected 0 editable, got {editable_count}")
        
        # Test warehouse
        success, response = self.run_test(
            "Warehouse GET /config/registry",
            "GET",
            "/config/registry",
            200,
            token=self.tokens.get('warehouse')
        )
        
        if success:
            caps = response.get('caps', {})
            editable_count = caps.get('editable_count', 0)
            
            print(f"   Warehouse editable_count: {editable_count}")
            
            if editable_count == 0:
                print("   ✅ Warehouse has correct permissions (0 editable)")
            else:
                self.failures.append(f"Warehouse caps incorrect: expected editable_count=0, got {editable_count}")
                print(f"   ❌ Warehouse caps incorrect: expected 0 editable, got {editable_count}")

    def test_backend_2_effective_table_shape(self):
        """BACKEND-2: GET /api/config/effective?group=pajak - check row_shape & columns"""
        print("\n" + "="*70)
        print("BACKEND-2: Effective Config with Table Shape")
        print("="*70)
        
        success, response = self.run_test(
            "Admin GET /config/effective?group=pajak",
            "GET",
            "/config/effective",
            200,
            token=self.tokens.get('admin'),
            params={'group': 'pajak'}
        )
        
        if success:
            items = response.get('items', [])
            pph_item = next((item for item in items if item.get('key') == 'tax.pph_items'), None)
            
            if pph_item:
                row_shape = pph_item.get('row_shape', '')
                columns = pph_item.get('columns', [])
                
                print(f"   tax.pph_items row_shape: {row_shape}")
                print(f"   tax.pph_items columns count: {len(columns)}")
                
                if row_shape == 'list' and len(columns) == 5:
                    print("   ✅ tax.pph_items has correct row_shape='list' and 5 columns")
                else:
                    self.failures.append(f"tax.pph_items shape incorrect: row_shape={row_shape}, columns={len(columns)}")
                    print(f"   ❌ tax.pph_items shape incorrect: expected row_shape='list' and 5 columns")
            else:
                self.failures.append("tax.pph_items not found in pajak group")
                print("   ❌ tax.pph_items not found in pajak group")

    def test_backend_3_manager_hr_edit(self):
        """BACKEND-3: PUT /api/config/values as manager for hr.overtime.multiplier - should be 200"""
        print("\n" + "="*70)
        print("BACKEND-3: Manager Edit HR Setting (Allowed)")
        print("="*70)
        
        # First, get current value
        success, response = self.run_test(
            "Manager GET current hr.overtime.multiplier",
            "GET",
            "/config/effective",
            200,
            token=self.tokens.get('manager'),
            params={'group': 'sdm'}
        )
        
        current_value = 1.5
        if success:
            items = response.get('items', [])
            hr_item = next((item for item in items if item.get('key') == 'hr.overtime.multiplier'), None)
            if hr_item:
                current_value = hr_item.get('value', 1.5)
                print(f"   Current value: {current_value}")
        
        # Try to update (use a different value temporarily)
        test_value = 1.6 if current_value == 1.5 else 1.5
        
        success, response = self.run_test(
            "Manager PUT /config/values for hr.overtime.multiplier",
            "PUT",
            "/config/values",
            200,
            token=self.tokens.get('manager'),
            data={
                "items": [{
                    "key": "hr.overtime.multiplier",
                    "value": test_value,
                    "scope_type": "global",
                    "scope_id": "",
                    "reason": "Test update by manager"
                }]
            }
        )
        
        if success:
            print("   ✅ Manager can edit hr.overtime.multiplier (has hr.manage_payroll)")
            
            # Restore original value
            self.run_test(
                "Manager RESTORE hr.overtime.multiplier to 1.5",
                "PUT",
                "/config/values",
                200,
                token=self.tokens.get('manager'),
                data={
                    "items": [{
                        "key": "hr.overtime.multiplier",
                        "value": 1.5,
                        "scope_type": "global",
                        "scope_id": "",
                        "reason": "Restore to default after test"
                    }]
                }
            )

    def test_backend_4_manager_tax_forbidden(self):
        """BACKEND-4: PUT /api/config/values as manager for tax.ppn_rate - should be 403"""
        print("\n" + "="*70)
        print("BACKEND-4: Manager Edit Tax Setting (Forbidden)")
        print("="*70)
        
        success, response = self.run_test(
            "Manager PUT /config/values for tax.ppn_rate (should be 403)",
            "PUT",
            "/config/values",
            403,
            token=self.tokens.get('manager'),
            data={
                "items": [{
                    "key": "tax.ppn_rate",
                    "value": 11,
                    "scope_type": "global",
                    "scope_id": "",
                    "reason": "Test forbidden update"
                }]
            }
        )
        
        if success:
            detail = response.get('detail', '')
            if 'settings.manage' in detail or 'tidak bisa Anda ubah' in detail:
                print(f"   ✅ Manager correctly forbidden with permission message: {detail}")
            else:
                print(f"   ⚠️  Got 403 but message unclear: {detail}")

    def test_backend_5_admin_not_used_setting(self):
        """BACKEND-5: PUT /api/config/values for hr.ptkp_table (status not_used) - should be 400"""
        print("\n" + "="*70)
        print("BACKEND-5: Admin Edit Not-Used Setting (Should Explain Why)")
        print("="*70)
        
        success, response = self.run_test(
            "Admin PUT /config/values for hr.ptkp_table (should be 400)",
            "PUT",
            "/config/values",
            400,
            token=self.tokens.get('admin'),
            data={
                "items": [{
                    "key": "hr.ptkp_table",
                    "value": {"TK0": 54000000},
                    "scope_type": "global",
                    "scope_id": "",
                    "reason": "Test not_used setting"
                }]
            }
        )
        
        if success:
            detail = response.get('detail', '')
            if 'TER' in detail or 'tidak dipakai' in detail:
                print(f"   ✅ Admin correctly blocked with explanation: {detail}")
            else:
                print(f"   ⚠️  Got 400 but explanation unclear: {detail}")

    def test_backend_6_warehouse_all_forbidden(self):
        """BACKEND-6: PUT /api/config/values as warehouse - should be 403"""
        print("\n" + "="*70)
        print("BACKEND-6: Warehouse Edit Any Setting (Forbidden)")
        print("="*70)
        
        success, response = self.run_test(
            "Warehouse PUT /config/values for any key (should be 403)",
            "PUT",
            "/config/values",
            403,
            token=self.tokens.get('warehouse'),
            data={
                "items": [{
                    "key": "tax.ppn_rate",
                    "value": 11,
                    "scope_type": "global",
                    "scope_id": "",
                    "reason": "Test warehouse forbidden"
                }]
            }
        )
        
        if success:
            print("   ✅ Warehouse correctly forbidden from editing any config")

def main():
    print("\n" + "="*70)
    print("FASE G-0 Configuration Center Backend API Tests")
    print("="*70)
    
    tester = ConfigAPITester()
    
    # Login all roles
    print("\n" + "="*70)
    print("AUTHENTICATION")
    print("="*70)
    
    for role in ['admin', 'manager', 'sales', 'warehouse']:
        if not tester.login(role):
            print(f"❌ Failed to login as {role}, stopping tests")
            return 1
    
    # Run all backend tests
    tester.test_backend_1_registry_caps()
    tester.test_backend_2_effective_table_shape()
    tester.test_backend_3_manager_hr_edit()
    tester.test_backend_4_manager_tax_forbidden()
    tester.test_backend_5_admin_not_used_setting()
    tester.test_backend_6_warehouse_all_forbidden()
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {tester.tests_run}")
    print(f"Tests passed: {tester.tests_passed}")
    print(f"Tests failed: {tester.tests_run - tester.tests_passed}")
    
    if tester.failures:
        print("\n❌ FAILURES:")
        for failure in tester.failures:
            print(f"  - {failure}")
    
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())
