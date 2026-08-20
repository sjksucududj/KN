"""
Comprehensive RFID Backend API Testing (Fase 5)
Tests all RFID endpoints, RBAC, SSOT regression, gate logic, and data integrity
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://warehouse-fase-b.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@kainnusantara.id"
WAREHOUSE_EMAIL = "warehouse@kainnusantara.id"
PASSWORD = "demo12345"
ENTITY_ID = "ent_ksc"

class RFIDAPITester:
    def __init__(self):
        self.admin_token = None
        self.warehouse_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.stock_before = {}
        self.stock_after = {}

    def log(self, message, level="INFO"):
        """Log test messages"""
        prefix = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "FAIL": "❌",
            "WARN": "⚠️"
        }.get(level, "•")
        print(f"{prefix} {message}")

    def run_test(self, name, method, endpoint, expected_status, token=None, data=None, params=None, headers=None):
        """Run a single API test"""
        url = f"{BASE_URL}{endpoint}"
        req_headers = {'Content-Type': 'application/json', 'X-Entity-Id': ENTITY_ID}
        if token:
            req_headers['Authorization'] = f'Bearer {token}'
        if headers:
            req_headers.update(headers)

        self.tests_run += 1
        self.log(f"Testing: {name}", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=req_headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=req_headers, params=params, timeout=30)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=req_headers, params=params, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=req_headers, params=params, timeout=30)

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"PASSED - {name} (Status: {response.status_code})", "SUCCESS")
                return True, response
            else:
                self.tests_failed += 1
                self.failed_tests.append(name)
                self.log(f"FAILED - {name} (Expected {expected_status}, got {response.status_code})", "FAIL")
                try:
                    error_detail = response.json()
                    self.log(f"  Error: {error_detail}", "FAIL")
                except Exception:
                    self.log(f"  Response: {response.text[:200]}", "FAIL")
                return False, response

        except Exception as e:
            self.tests_failed += 1
            self.failed_tests.append(name)
            self.log(f"FAILED - {name} (Exception: {str(e)})", "FAIL")
            return False, None

    def test_login(self):
        """Test login for both admin and warehouse users"""
        self.log("\n=== AUTHENTICATION ===", "INFO")
        
        # Admin login
        success, response = self.run_test(
            "Login Admin",
            "POST",
            "/auth/login",
            200,
            data={"email": ADMIN_EMAIL, "password": PASSWORD}
        )
        if success and response:
            self.admin_token = response.json().get('token')
            self.log(f"  Admin token obtained", "SUCCESS")
        
        # Warehouse login
        success, response = self.run_test(
            "Login Warehouse",
            "POST",
            "/auth/login",
            200,
            data={"email": WAREHOUSE_EMAIL, "password": PASSWORD}
        )
        if success and response:
            self.warehouse_token = response.json().get('token')
            self.log(f"  Warehouse token obtained", "SUCCESS")
        
        return bool(self.admin_token and self.warehouse_token)

    def capture_stock_snapshot(self, label="before"):
        """Capture current stock quantities for SSOT verification"""
        self.log(f"\n=== CAPTURING STOCK SNAPSHOT ({label.upper()}) ===", "INFO")
        
        # Get inventory balances summary
        success, response = self.run_test(
            f"Get Inventory Summary ({label})",
            "GET",
            "/inventory/summary",
            200,
            token=self.warehouse_token
        )
        
        if success and response:
            data = response.json()
            snapshot = {
                'available_qty': data.get('available_qty', 0),
                'reserved_qty': data.get('reserved_qty', 0),
                'timestamp': datetime.now().isoformat()
            }
            
            if label == "before":
                self.stock_before = snapshot
            else:
                self.stock_after = snapshot
            
            self.log(f"  Available: {snapshot['available_qty']}, Reserved: {snapshot['reserved_qty']}", "INFO")
            return True
        return False

    def verify_ssot_unchanged(self):
        """Verify SSOT: stock quantities must be unchanged after RFID operations"""
        self.log("\n=== SSOT VERIFICATION ===", "INFO")
        
        if not self.stock_before or not self.stock_after:
            self.log("  Cannot verify SSOT - missing snapshots", "WARN")
            return False
        
        available_unchanged = abs(self.stock_before['available_qty'] - self.stock_after['available_qty']) < 0.01
        reserved_unchanged = abs(self.stock_before['reserved_qty'] - self.stock_after['reserved_qty']) < 0.01
        
        if available_unchanged and reserved_unchanged:
            self.tests_passed += 1
            self.log(f"PASSED - SSOT: Stock quantities unchanged", "SUCCESS")
            self.log(f"  Available: {self.stock_before['available_qty']} → {self.stock_after['available_qty']}", "SUCCESS")
            self.log(f"  Reserved: {self.stock_before['reserved_qty']} → {self.stock_after['reserved_qty']}", "SUCCESS")
            return True
        else:
            self.tests_failed += 1
            self.failed_tests.append("SSOT Verification")
            self.log(f"FAILED - SSOT: Stock quantities changed!", "FAIL")
            self.log(f"  Available: {self.stock_before['available_qty']} → {self.stock_after['available_qty']}", "FAIL")
            self.log(f"  Reserved: {self.stock_before['reserved_qty']} → {self.stock_after['reserved_qty']}", "FAIL")
            return False

    def test_summary(self):
        """Test GET /api/rfid/summary"""
        self.log("\n=== RFID SUMMARY ===", "INFO")
        
        success, response = self.run_test(
            "RFID Summary",
            "GET",
            "/rfid/summary",
            200,
            token=self.warehouse_token
        )
        
        if success and response:
            data = response.json()
            required_fields = ['tags_total', 'tags_active', 'untagged_rolls', 'devices_total', 
                             'devices_online', 'reads_today', 'alerts_today']
            
            all_present = all(field in data for field in required_fields)
            if all_present:
                self.log(f"  All required fields present", "SUCCESS")
                self.log(f"  Tags: {data['tags_active']}/{data['tags_total']}, Devices: {data['devices_online']}/{data['devices_total']}", "INFO")
                self.log(f"  Reads today: {data['reads_today']}, Alerts: {data['alerts_today']}", "INFO")
            else:
                missing = [f for f in required_fields if f not in data]
                self.log(f"  Missing fields: {missing}", "WARN")
        
        return success

    def test_tags_list(self):
        """Test GET /api/rfid/tags"""
        self.log("\n=== RFID TAGS LIST ===", "INFO")
        
        success, response = self.run_test(
            "Tags List (active)",
            "GET",
            "/rfid/tags",
            200,
            token=self.warehouse_token,
            params={"status": "active"}
        )
        
        if success and response:
            data = response.json()
            self.log(f"  Active tags count: {data.get('count', 0)}", "INFO")
            
            if data.get('tags'):
                tag = data['tags'][0]
                required_fields = ['id', 'epc', 'roll_id', 'sku', 'product_name', 'status']
                all_present = all(field in tag for field in required_fields)
                if all_present:
                    self.log(f"  Tag structure valid", "SUCCESS")
                else:
                    missing = [f for f in required_fields if f not in tag]
                    self.log(f"  Missing tag fields: {missing}", "WARN")
        
        return success

    def test_untagged_rolls(self):
        """Test GET /api/rfid/untagged-rolls"""
        self.log("\n=== UNTAGGED ROLLS ===", "INFO")
        
        success, response = self.run_test(
            "Untagged Rolls",
            "GET",
            "/rfid/untagged-rolls",
            200,
            token=self.warehouse_token
        )
        
        if success and response:
            data = response.json()
            self.log(f"  Untagged rolls count: {data.get('count', 0)}", "INFO")
        
        return success

    def test_devices_list(self):
        """Test GET /api/rfid/devices"""
        self.log("\n=== RFID DEVICES LIST ===", "INFO")
        
        success, response = self.run_test(
            "Devices List",
            "GET",
            "/rfid/devices",
            200,
            token=self.warehouse_token
        )
        
        if success and response:
            data = response.json()
            self.log(f"  Devices count: {data.get('count', 0)}", "INFO")
            
            if data.get('devices'):
                device = data['devices'][0]
                required_fields = ['id', 'code', 'name', 'type', 'status', 'warehouse_id']
                all_present = all(field in device for field in required_fields)
                if all_present:
                    self.log(f"  Device structure valid", "SUCCESS")
                else:
                    missing = [f for f in required_fields if f not in device]
                    self.log(f"  Missing device fields: {missing}", "WARN")
        
        return success

    def test_rbac_device_create(self):
        """Test RBAC: warehouse role must get 403 on device create"""
        self.log("\n=== RBAC: DEVICE CREATE ===", "INFO")
        
        # Warehouse should be blocked (403)
        success, response = self.run_test(
            "Device Create (warehouse - should fail)",
            "POST",
            "/rfid/devices",
            403,
            token=self.warehouse_token,
            data={
                "name": "Test Device",
                "type": "gate",
                "warehouse_id": "wh_jakarta"
            }
        )
        
        return success

    def test_rbac_device_patch(self):
        """Test RBAC: warehouse role must get 403 on device patch"""
        self.log("\n=== RBAC: DEVICE PATCH ===", "INFO")
        
        # Get a device first
        _, response = self.run_test(
            "Get Devices for RBAC test",
            "GET",
            "/rfid/devices",
            200,
            token=self.warehouse_token
        )
        
        if response and response.json().get('devices'):
            device_id = response.json()['devices'][0]['id']
            
            # Warehouse should be blocked (403)
            success, _ = self.run_test(
                "Device Patch (warehouse - should fail)",
                "PATCH",
                f"/rfid/devices/{device_id}",
                403,
                token=self.warehouse_token,
                data={"status": "offline"}
            )
            return success
        
        self.log("  No devices found for RBAC test", "WARN")
        return False

    def test_rbac_device_delete(self):
        """Test RBAC: warehouse role must get 403 on device delete"""
        self.log("\n=== RBAC: DEVICE DELETE ===", "INFO")
        
        # Get a device first
        _, response = self.run_test(
            "Get Devices for RBAC test",
            "GET",
            "/rfid/devices",
            200,
            token=self.warehouse_token
        )
        
        if response and response.json().get('devices'):
            device_id = response.json()['devices'][0]['id']
            
            # Warehouse should be blocked (403)
            success, _ = self.run_test(
                "Device Delete (warehouse - should fail)",
                "DELETE",
                f"/rfid/devices/{device_id}",
                403,
                token=self.warehouse_token
            )
            return success
        
        self.log("  No devices found for RBAC test", "WARN")
        return False

    def test_admin_device_crud(self):
        """Test admin can create, patch, and delete devices"""
        self.log("\n=== ADMIN DEVICE CRUD ===", "INFO")
        
        # Create
        success, response = self.run_test(
            "Device Create (admin)",
            "POST",
            "/rfid/devices",
            200,
            token=self.admin_token,
            data={
                "code": "TEST-GATE-001",
                "name": "Test Gate",
                "type": "gate",
                "direction": "out",
                "warehouse_id": "wh_jakarta",
                "location": "Test Dock"
            }
        )
        
        if not success or not response:
            return False
        
        device_id = response.json().get('id')
        if not device_id:
            self.log("  No device ID returned", "FAIL")
            return False
        
        # Patch
        success, response = self.run_test(
            "Device Patch (admin)",
            "PATCH",
            f"/rfid/devices/{device_id}",
            200,
            token=self.admin_token,
            data={"status": "offline"}
        )
        
        if success and response:
            if response.json().get('status') == 'offline':
                self.log(f"  Device status updated to offline", "SUCCESS")
            else:
                self.log(f"  Device status not updated", "WARN")
        
        # Delete
        success, _ = self.run_test(
            "Device Delete (admin)",
            "DELETE",
            f"/rfid/devices/{device_id}",
            200,
            token=self.admin_token
        )
        
        return success

    def test_gate_simulation(self):
        """Test gate simulation logic (GREEN/RED/INFO)"""
        self.log("\n=== GATE SIMULATION ===", "INFO")
        
        # Get gates and tagged rolls
        _, dev_response = self.run_test(
            "Get Devices for Gate Test",
            "GET",
            "/rfid/devices",
            200,
            token=self.warehouse_token
        )
        
        _, tags_response = self.run_test(
            "Get Tags for Gate Test",
            "GET",
            "/rfid/tags",
            200,
            token=self.warehouse_token,
            params={"status": "active"}
        )
        
        if not (dev_response and tags_response):
            self.log("  Cannot test gate simulation - missing data", "WARN")
            return False
        
        devices = dev_response.json().get('devices', [])
        tags = tags_response.json().get('tags', [])
        
        gate_out = next((d for d in devices if d['type'] == 'gate' and d['direction'] == 'out'), None)
        
        if not gate_out:
            self.log("  No gate-out device found", "WARN")
            return False
        
        if not tags:
            self.log("  No active tags found", "WARN")
            return False
        
        # Test with first available tagged roll
        roll_id = tags[0]['roll_id']
        
        success, response = self.run_test(
            "Gate Simulate",
            "POST",
            "/rfid/gate/simulate",
            200,
            token=self.warehouse_token,
            data={
                "device_id": gate_out['id'],
                "roll_id": roll_id
            }
        )
        
        if success and response:
            data = response.json()
            result = data.get('result')
            reason = data.get('reason', '')
            
            if result in ['green', 'red', 'info']:
                self.log(f"  Gate result: {result.upper()} - {reason}", "SUCCESS")
            else:
                self.log(f"  Unexpected gate result: {result}", "WARN")
        
        return success

    def test_reader_scan(self):
        """Test reader scan operation"""
        self.log("\n=== READER SCAN ===", "INFO")
        
        # Get readers
        _, response = self.run_test(
            "Get Devices for Reader Test",
            "GET",
            "/rfid/devices",
            200,
            token=self.warehouse_token
        )
        
        if not response:
            return False
        
        devices = response.json().get('devices', [])
        reader = next((d for d in devices if d['type'] in ['fixed_reader', 'handheld'] and d['status'] == 'online'), None)
        
        if not reader:
            self.log("  No online reader found", "WARN")
            return False
        
        success, response = self.run_test(
            "Reader Scan",
            "POST",
            "/rfid/reader/scan",
            200,
            token=self.warehouse_token,
            data={"device_id": reader['id']}
        )
        
        if success and response:
            data = response.json()
            scanned = data.get('scanned', 0)
            self.log(f"  Scanned {scanned} tags", "INFO")
        
        return success

    def test_reads_list(self):
        """Test GET /api/rfid/reads with filters"""
        self.log("\n=== RFID READS ===", "INFO")
        
        # All reads
        success, response = self.run_test(
            "Reads List (all)",
            "GET",
            "/rfid/reads",
            200,
            token=self.warehouse_token,
            params={"limit": 50}
        )
        
        if success and response:
            data = response.json()
            self.log(f"  Total reads: {data.get('count', 0)}", "INFO")
        
        # Red alerts only
        success, response = self.run_test(
            "Reads List (result=red)",
            "GET",
            "/rfid/reads",
            200,
            token=self.warehouse_token,
            params={"result": "red"}
        )
        
        if success and response:
            data = response.json()
            self.log(f"  Red alerts: {data.get('count', 0)}", "INFO")
        
        return success

    def test_locations(self):
        """Test GET /api/rfid/locations"""
        self.log("\n=== RFID LOCATIONS ===", "INFO")
        
        success, response = self.run_test(
            "Locations",
            "GET",
            "/rfid/locations",
            200,
            token=self.warehouse_token
        )
        
        if success and response:
            data = response.json()
            items = data.get('items', [])
            self.log(f"  Location items: {data.get('count', 0)}", "INFO")
            
            if items:
                # Check for drift detection
                states = {item['state'] for item in items}
                self.log(f"  States found: {states}", "INFO")
                
                drift_items = [item for item in items if item['state'] == 'drift']
                if drift_items:
                    self.log(f"  Drift detected: {len(drift_items)} items", "INFO")
        
        return success

    def test_encode_retire_flow(self):
        """Test encode and retire tag flow"""
        self.log("\n=== ENCODE/RETIRE FLOW ===", "INFO")
        
        # Get an active tag to retire
        _, response = self.run_test(
            "Get Tags for Encode/Retire Test",
            "GET",
            "/rfid/tags",
            200,
            token=self.warehouse_token,
            params={"status": "active"}
        )
        
        if not response or not response.json().get('tags'):
            self.log("  No active tags found", "WARN")
            return False
        
        tag = response.json()['tags'][0]
        tag_id = tag['id']
        roll_id = tag['roll_id']
        
        # Retire the tag
        success, _ = self.run_test(
            "Retire Tag",
            "DELETE",
            f"/rfid/tags/{tag_id}",
            200,
            token=self.warehouse_token
        )
        
        if not success:
            return False
        
        # Verify roll appears in untagged
        _, response = self.run_test(
            "Check Untagged Rolls",
            "GET",
            "/rfid/untagged-rolls",
            200,
            token=self.warehouse_token
        )
        
        if response:
            rolls = response.json().get('rolls', [])
            if any(r['id'] == roll_id for r in rolls):
                self.log(f"  Roll {roll_id} now in untagged list", "SUCCESS")
            else:
                self.log(f"  Roll {roll_id} not found in untagged list", "WARN")
        
        # Re-encode the roll
        success, response = self.run_test(
            "Re-encode Tag",
            "POST",
            "/rfid/tags/encode",
            200,
            token=self.warehouse_token,
            data={"roll_id": roll_id}
        )
        
        if success and response:
            new_tag = response.json()
            if new_tag.get('epc') and new_tag.get('roll_id') == roll_id:
                self.log(f"  Roll re-encoded with EPC: {new_tag['epc']}", "SUCCESS")
            else:
                self.log(f"  Re-encode response invalid", "WARN")
        
        return success

    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "="*60, "INFO")
        self.log("RFID COMPREHENSIVE TEST SUMMARY", "INFO")
        self.log("="*60, "INFO")
        self.log(f"Total Tests: {self.tests_run}", "INFO")
        self.log(f"Passed: {self.tests_passed}", "SUCCESS")
        self.log(f"Failed: {self.tests_failed}", "FAIL" if self.tests_failed > 0 else "INFO")
        
        if self.tests_failed > 0:
            self.log("\nFailed Tests:", "FAIL")
            for test in self.failed_tests:
                self.log(f"  - {test}", "FAIL")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"\nSuccess Rate: {success_rate:.1f}%", "SUCCESS" if success_rate >= 90 else "WARN")
        self.log("="*60, "INFO")
        
        return 0 if self.tests_failed == 0 else 1


def main():
    """Main test runner"""
    print("\n" + "="*60)
    print("RFID SIMULATOR (FASE 5) - COMPREHENSIVE BACKEND API TESTS")
    print("="*60)
    
    tester = RFIDAPITester()
    
    # Authentication
    if not tester.test_login():
        print("\n❌ Login failed, stopping tests")
        return 1
    
    # Capture stock snapshot BEFORE RFID operations
    tester.capture_stock_snapshot("before")
    
    # Summary & Basic Endpoints
    tester.test_summary()
    tester.test_tags_list()
    tester.test_untagged_rolls()
    tester.test_devices_list()
    
    # RBAC Tests
    tester.test_rbac_device_create()
    tester.test_rbac_device_patch()
    tester.test_rbac_device_delete()
    
    # Admin CRUD
    tester.test_admin_device_crud()
    
    # Gate & Reader Operations
    tester.test_gate_simulation()
    tester.test_reader_scan()
    tester.test_reads_list()
    
    # Locations & Drift
    tester.test_locations()
    
    # Encode/Retire Flow
    tester.test_encode_retire_flow()
    
    # Capture stock snapshot AFTER RFID operations
    tester.capture_stock_snapshot("after")
    
    # CRITICAL: Verify SSOT (stock unchanged)
    tester.verify_ssot_unchanged()
    
    # Print summary
    return tester.print_summary()


if __name__ == "__main__":
    sys.exit(main())
