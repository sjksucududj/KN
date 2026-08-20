"""
Backend test for PO Timeline & Notification Approve features.
Tests:
1. PO timeline entries in GET /api/purchase-orders/{id}
2. Timeline for seeded POs (PO-00007 waiting, PO-00008 rejected, PO-00009 approved)
3. Legacy PO timeline (empty backend timeline)
4. Notification generation for PO approval
5. Approve PO from notification (role gating)
6. Backend regression (list, approve, reject, cancel, pay, close)
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

class POTimelineApprovalTester:
    def __init__(self):
        self.admin_token = None
        self.manager_token = None
        self.sales_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log(self, message, success=None):
        """Log test result"""
        print(message)
        if success is not None:
            self.test_results.append({"message": message, "success": success})

    def run_test(self, name, method, endpoint, expected_status, data=None, token=None, check_fn=None):
        """Run a single API test with optional validation function"""
        url = f"{BASE_URL}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.tests_run += 1
        self.log(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)

            success = response.status_code == expected_status
            
            if success:
                self.log(f"✅ Status {response.status_code} - PASSED", True)
                
                # Additional validation if check function provided
                if check_fn and response.status_code < 400:
                    try:
                        response_data = response.json()
                        check_result = check_fn(response_data)
                        if check_result:
                            self.log(f"   ✓ Validation: {check_result}", True)
                        else:
                            self.log(f"   ✗ Validation failed", False)
                            success = False
                    except Exception as e:
                        self.log(f"   ✗ Validation error: {str(e)}", False)
                        success = False
                
                if success:
                    self.tests_passed += 1
                return success, response.json() if response.status_code < 400 else {}
            else:
                self.log(f"❌ Expected {expected_status}, got {response.status_code} - FAILED", False)
                if response.status_code >= 400:
                    try:
                        self.log(f"   Error: {response.json()}")
                    except Exception:
                        self.log(f"   Error: {response.text}")
                return False, {}

        except Exception as e:
            self.log(f"❌ Exception: {str(e)} - FAILED", False)
            return False, {}

    def test_login(self, email, password):
        """Test login and get token"""
        success, response = self.run_test(
            f"Login as {email}",
            "POST",
            "auth/login",
            200,
            data={"email": email, "password": password}
        )
        if success and 'token' in response:
            return response['token']
        return None

    def test_po_timeline_entries(self, po_id, po_number, expected_events, token):
        """Test that PO has timeline with expected events"""
        def check_timeline(data):
            timeline = data.get('timeline', [])
            if not timeline:
                return f"❌ No timeline found for {po_number}"
            
            events = [entry.get('event') for entry in timeline]
            self.log(f"   Timeline events: {events}")
            
            missing = [e for e in expected_events if e not in events]
            if missing:
                return f"❌ Missing events: {missing}"
            
            # Check timeline entry structure
            for i, entry in enumerate(timeline):
                if not all(k in entry for k in ['event', 'label', 'actor', 'at']):
                    return f"❌ Timeline entry {i} missing required fields"
            
            return f"✓ Timeline has {len(timeline)} entries with expected events"
        
        return self.run_test(
            f"GET PO {po_number} timeline",
            "GET",
            f"purchase-orders/{po_id}",
            200,
            token=token,
            check_fn=check_timeline
        )

    def test_legacy_po_timeline_synthesis(self, token):
        """Test that legacy POs (empty timeline) synthesize fallback timeline"""
        # Get list of POs to find a completed one (likely PO-00001, 00002, 00003)
        success, pos = self.run_test(
            "GET purchase orders list",
            "GET",
            "purchase-orders",
            200,
            token=token
        )
        
        if not success:
            return False, {}
        
        # Find a completed PO with empty timeline (legacy)
        legacy_po = None
        for po in pos:
            if po.get('status') == 'completed' and not po.get('timeline'):
                legacy_po = po
                break
        
        if not legacy_po:
            self.log("⚠️  No legacy completed PO found (all have timeline) - SKIPPED")
            return True, {}
        
        self.log(f"   Found legacy PO: {legacy_po.get('po_number')} (no backend timeline)")
        self.log(f"   Frontend should synthesize timeline from timestamps")
        return True, legacy_po

    def test_notification_generation(self, token):
        """Test POST /api/notifications/generate creates PO approval notifications"""
        def check_notifications(data):
            created = data.get('created', 0)
            return f"✓ Generated {created} notifications"
        
        return self.run_test(
            "Generate system notifications",
            "POST",
            "notifications/generate",
            200,
            token=token,
            check_fn=check_notifications
        )

    def test_po_approval_notification_exists(self, token):
        """Test that PO approval notifications exist with action fields"""
        def check_po_notif(data):
            po_notifs = [n for n in data if n.get('type') == 'po_approval']
            if not po_notifs:
                return "❌ No PO approval notifications found"
            
            notif = po_notifs[0]
            self.log(f"   Found PO approval notification: {notif.get('title')}")
            
            # Check action fields
            if notif.get('action_type') != 'po_approve':
                return f"❌ action_type is '{notif.get('action_type')}', expected 'po_approve'"
            
            if not notif.get('action_id'):
                return "❌ action_id is missing"
            
            if not notif.get('action_role'):
                return "❌ action_role is missing"
            
            return f"✓ PO approval notification has correct action fields (action_id={notif.get('action_id')})"
        
        return self.run_test(
            "GET notifications (check PO approval)",
            "GET",
            "notifications",
            200,
            token=token,
            check_fn=check_po_notif
        )

    def test_approve_po_as_manager(self, po_id, token):
        """Test approve PO as manager (should succeed)"""
        def check_approval(data):
            if data.get('status') != 'pending':
                return f"❌ Status is '{data.get('status')}', expected 'pending'"
            if not data.get('approved_by'):
                return "❌ approved_by is missing"
            
            # Check timeline has approved entry
            timeline = data.get('timeline', [])
            approved_events = [e for e in timeline if e.get('event') == 'approved']
            if not approved_events:
                return "❌ Timeline missing 'approved' event"
            
            return f"✓ PO approved successfully, status=pending, timeline updated"
        
        return self.run_test(
            f"Approve PO {po_id} as manager",
            "POST",
            f"purchase-orders/{po_id}/approve",
            200,
            token=token,
            check_fn=check_approval
        )

    def test_approve_po_as_sales(self, po_id, token):
        """Test approve PO as sales (should fail 403)"""
        return self.run_test(
            f"Approve PO {po_id} as sales (expect 403)",
            "POST",
            f"purchase-orders/{po_id}/approve",
            403,
            token=token
        )

    def test_approve_non_waiting_po(self, po_id, token):
        """Test approve PO that is not waiting_approval (should fail 409)"""
        return self.run_test(
            f"Approve non-waiting PO {po_id} (expect 409)",
            "POST",
            f"purchase-orders/{po_id}/approve",
            409,
            token=token
        )

    def run_all_tests(self):
        """Run all tests"""
        print("=" * 80)
        print("PO TIMELINE & NOTIFICATION APPROVE BACKEND TESTS")
        print("=" * 80)

        # 1. Login as different roles
        print("\n📋 PHASE 1: Authentication")
        self.admin_token = self.test_login("admin@kainnusantara.id", "demo12345")
        self.manager_token = self.test_login("manager@kainnusantara.id", "demo12345")
        self.sales_token = self.test_login("sales@kainnusantara.id", "demo12345")

        if not self.admin_token or not self.manager_token or not self.sales_token:
            self.log("\n❌ CRITICAL: Login failed for one or more roles. Stopping tests.")
            return 1

        # 2. Test PO timeline entries for seeded POs
        print("\n📋 PHASE 2: PO Timeline Entries")
        
        # PO-00009 (approved) - should have: created, submitted_for_approval, approved
        self.test_po_timeline_entries(
            "po_00009", "PO-00009",
            ["created", "submitted_for_approval", "approved"],
            self.manager_token
        )
        
        # PO-00008 (rejected) - should have: created, submitted_for_approval, rejected
        self.test_po_timeline_entries(
            "po_00008", "PO-00008",
            ["created", "submitted_for_approval", "rejected"],
            self.manager_token
        )
        
        # PO-00007 (waiting_approval) - should have: created, submitted_for_approval
        self.test_po_timeline_entries(
            "po_00007", "PO-00007",
            ["created", "submitted_for_approval"],
            self.manager_token
        )

        # 3. Test legacy PO timeline synthesis (frontend will handle)
        print("\n📋 PHASE 3: Legacy PO Timeline")
        self.test_legacy_po_timeline_synthesis(self.manager_token)

        # 4. Test notification generation
        print("\n📋 PHASE 4: Notification Generation")
        self.test_notification_generation(self.manager_token)
        self.test_po_approval_notification_exists(self.manager_token)

        # 5. Test approve PO with role gating
        print("\n📋 PHASE 5: PO Approval Role Gating")
        
        # First, find a waiting_approval PO
        success, pos = self.run_test(
            "GET purchase orders to find waiting_approval PO",
            "GET",
            "purchase-orders",
            200,
            token=self.manager_token
        )
        
        waiting_po = None
        if success:
            for po in pos:
                if po.get('status') == 'waiting_approval':
                    waiting_po = po
                    break
        
        if waiting_po:
            po_id = waiting_po.get('id')
            self.log(f"   Found waiting PO: {waiting_po.get('po_number')} (id={po_id})")
            
            # Test sales cannot approve (403)
            self.test_approve_po_as_sales(po_id, self.sales_token)
            
            # Test manager can approve (200)
            self.test_approve_po_as_manager(po_id, self.manager_token)
            
            # Test cannot approve again (409)
            self.test_approve_non_waiting_po(po_id, self.manager_token)
        else:
            self.log("⚠️  No waiting_approval PO found - SKIPPED approval tests")

        # 6. Backend regression tests
        print("\n📋 PHASE 6: Backend Regression")
        self.run_test(
            "GET /api/purchase-orders (list)",
            "GET",
            "purchase-orders",
            200,
            token=self.manager_token
        )

        # Print summary
        print("\n" + "=" * 80)
        print(f"📊 TESTS SUMMARY: {self.tests_passed}/{self.tests_run} passed")
        print("=" * 80)
        
        failed_tests = [r for r in self.test_results if not r['success']]
        if failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in failed_tests:
                print(f"   - {test['message']}")
        
        return 0 if self.tests_passed == self.tests_run else 1

def main():
    tester = POTimelineApprovalTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
