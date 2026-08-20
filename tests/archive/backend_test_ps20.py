#!/usr/bin/env python3
"""Backend API Testing for PS-20 (D-14) — MATRIKS PERSETUJUAN DIVISI MENGIKAT.

Tests the enforced approver matrix with 4 stages:
  - design_acc (ACC Desain)
  - sample_acc (ACC Sample)
  - po_custom (PO Custom) with 2-level approval
  - purchase_request (PR)

Plus segregation of duties (SoD), retroactivity switch, and audit trail.
"""
import requests
import sys
from typing import Dict, Any, Optional
from datetime import date, timedelta

BASE_URL = "https://kain-rnd-org.preview.emergentagent.com/api"
ENTITY_ID = "ent_ksc"
PASSWORD = "demo12345"

class PS20Tester:
    def __init__(self):
        self.admin_session = requests.Session()
        self.manager_session = requests.Session()
        self.sales_session = requests.Session()
        self.warehouse_session = requests.Session()
        
        self.admin_token = None
        self.manager_token = None
        self.sales_token = None
        self.warehouse_token = None
        
        self.admin_user = None
        self.manager_user = None
        
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def log(self, message: str, status: str = "info"):
        """Log test messages"""
        symbols = {"pass": "✅", "fail": "❌", "info": "🔍", "warn": "⚠️"}
        print(f"{symbols.get(status, '•')} {message}")

    def run_test(self, name: str, test_func) -> bool:
        """Run a single test and track results"""
        self.tests_run += 1
        self.log(f"Testing {name}...", "info")
        try:
            test_func()
            self.tests_passed += 1
            self.log(f"PASSED: {name}", "pass")
            return True
        except AssertionError as e:
            self.log(f"FAILED: {name} - {str(e)}", "fail")
            self.failed_tests.append({"test": name, "error": str(e)})
            return False
        except Exception as e:
            self.log(f"ERROR: {name} - {str(e)}", "fail")
            self.failed_tests.append({"test": name, "error": f"Exception: {str(e)}"})
            return False

    def login(self, email: str, password: str, session: requests.Session) -> tuple:
        """Login and return (token, user_data)"""
        response = session.post(
            f"{BASE_URL}/auth/login",
            json={"email": email, "password": password},
            timeout=30
        )
        assert response.status_code == 200, f"Login failed for {email}: {response.status_code}"
        data = response.json()
        assert "token" in data, f"No token in login response for {email}"
        
        # Set headers for this session
        session.headers.update({
            "Authorization": f"Bearer {data['token']}",
            "X-Entity-Id": ENTITY_ID,
            "Content-Type": "application/json"
        })
        
        return data["token"], data.get("user", {})

    def setup_auth(self):
        """Setup authentication for all roles"""
        self.log("Setting up authentication for all roles...", "info")
        
        self.admin_token, self.admin_user = self.login(
            "admin@kainnusantara.id", PASSWORD, self.admin_session)
        self.log(f"Admin logged in: {self.admin_user.get('name')}", "pass")
        
        self.manager_token, self.manager_user = self.login(
            "manager@kainnusantara.id", PASSWORD, self.manager_session)
        self.log(f"Manager logged in: {self.manager_user.get('name')}", "pass")
        
        self.sales_token, _ = self.login(
            "sales@kainnusantara.id", PASSWORD, self.sales_session)
        self.log("Sales logged in", "pass")
        
        self.warehouse_token, _ = self.login(
            "warehouse@kainnusantara.id", PASSWORD, self.warehouse_session)
        self.log("Warehouse logged in", "pass")

    # ═══ TEST 1: GET /api/approvals/matrix ═══
    def test_matrix_manager_200(self):
        """Test GET /api/approvals/matrix returns 200 for manager with 4 stages"""
        response = self.manager_session.get(f"{BASE_URL}/approvals/matrix", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify structure
        assert "stages" in data, "Missing 'stages' key"
        assert "config" in data, "Missing 'config' key"
        
        # Verify 4 stages
        stages = {s["stage"]: s for s in data["stages"]}
        expected_stages = {"design_acc", "sample_acc", "po_custom", "purchase_request"}
        assert set(stages.keys()) == expected_stages, \
            f"Expected stages {expected_stages}, got {set(stages.keys())}"
        
        # Verify po_custom has 2 levels
        po_custom = stages.get("po_custom", {})
        levels = po_custom.get("levels", [])
        assert len(levels) == 2, \
            f"po_custom should have 2 levels (Manager + Direksi), got {len(levels)}"
        
        # Verify level 1 = Manager (roles: manager, admin)
        assert levels[0].get("roles") == ["manager", "admin"], \
            f"Level 1 should be manager/admin, got {levels[0].get('roles')}"
        
        # Verify level 2 = Direksi (roles: admin only)
        assert levels[1].get("roles") == ["admin"], \
            f"Level 2 should be admin only, got {levels[1].get('roles')}"
        
        # Verify other stages have 1 level with manager/admin
        for stage in ["design_acc", "sample_acc", "purchase_request"]:
            stage_data = stages.get(stage, {})
            stage_levels = stage_data.get("levels", [])
            assert len(stage_levels) >= 1, f"{stage} should have at least 1 level"
            assert stage_levels[0].get("roles") == ["manager", "admin"], \
                f"{stage} level 1 should be manager/admin"
        
        # Verify config
        config = data.get("config", {})
        assert config.get("mode") == "enforce", \
            f"Default mode should be 'enforce', got {config.get('mode')}"
        assert config.get("scope") == "all_pending", \
            f"Default scope should be 'all_pending', got {config.get('scope')}"
        assert config.get("sod") is True, \
            f"Default SoD should be True, got {config.get('sod')}"
        assert float(config.get("po_custom_direksi_min", 0)) > 0, \
            "Direksi threshold should be > 0"
        
        self.log(f"Matrix config: mode={config.get('mode')}, scope={config.get('scope')}, "
                f"sod={config.get('sod')}, direksi_min={config.get('po_custom_direksi_min')}", "info")

    def test_matrix_sales_403(self):
        """Test GET /api/approvals/matrix returns 403 for sales"""
        response = self.sales_session.get(f"{BASE_URL}/approvals/matrix", timeout=30)
        assert response.status_code == 403, \
            f"Sales should get 403, got {response.status_code}"

    def test_matrix_warehouse_403(self):
        """Test GET /api/approvals/matrix returns 403 for warehouse"""
        response = self.warehouse_session.get(f"{BASE_URL}/approvals/matrix", timeout=30)
        assert response.status_code == 403, \
            f"Warehouse should get 403, got {response.status_code}"

    # ═══ TEST 2: GET /api/approvals/my-queue ═══
    def test_my_queue_manager_200(self):
        """Test GET /api/approvals/my-queue returns 200 for manager"""
        response = self.manager_session.get(f"{BASE_URL}/approvals/my-queue", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify structure
        assert "items" in data, "Missing 'items' key"
        assert "counts" in data, "Missing 'counts' key"
        assert "actionable" in data, "Missing 'actionable' key"
        assert "config" in data, "Missing 'config' key"
        
        # Verify counts for all 4 stages
        counts = data.get("counts", {})
        expected_stages = {"design_acc", "sample_acc", "po_custom", "purchase_request"}
        assert set(counts.keys()) == expected_stages, \
            f"Counts should cover all 4 stages, got {set(counts.keys())}"
        
        # Verify items structure
        for item in data.get("items", []):
            assert "stage" in item, "Item missing 'stage'"
            assert "can_decide" in item, "Item missing 'can_decide'"
            assert "required_roles_label" in item, "Item missing 'required_roles_label'"
            assert "days_waiting" in item, "Item missing 'days_waiting'"
            assert "view" in item, "Item missing 'view'"
            assert "level" in item, "Item missing 'level'"
            assert "block_reasons" in item, "Item missing 'block_reasons'"
        
        self.log(f"My queue: {data.get('total', 0)} items, "
                f"{data.get('actionable', 0)} actionable", "info")

    def test_my_queue_stage_filter(self):
        """Test GET /api/approvals/my-queue?stage=design_acc filters correctly"""
        response = self.manager_session.get(
            f"{BASE_URL}/approvals/my-queue",
            params={"stage": "design_acc"},
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # All items should be design_acc
        for item in data.get("items", []):
            assert item.get("stage") == "design_acc", \
                f"Expected design_acc, got {item.get('stage')}"

    def test_my_queue_invalid_stage_400(self):
        """Test GET /api/approvals/my-queue?stage=xxx returns 400"""
        response = self.manager_session.get(
            f"{BASE_URL}/approvals/my-queue",
            params={"stage": "xxx"},
            timeout=30
        )
        assert response.status_code == 400, \
            f"Invalid stage should return 400, got {response.status_code}"

    def test_my_queue_sales_403(self):
        """Test GET /api/approvals/my-queue returns 403 for sales"""
        response = self.sales_session.get(f"{BASE_URL}/approvals/my-queue", timeout=30)
        assert response.status_code == 403, \
            f"Sales should get 403, got {response.status_code}"

    def test_my_queue_warehouse_403(self):
        """Test GET /api/approvals/my-queue returns 403 for warehouse"""
        response = self.warehouse_session.get(f"{BASE_URL}/approvals/my-queue", timeout=30)
        assert response.status_code == 403, \
            f"Warehouse should get 403, got {response.status_code}"

    # ═══ TEST 3: GET /api/approvals/matrix-log ═══
    def test_matrix_log_manager_200(self):
        """Test GET /api/approvals/matrix-log returns 200 with audit trail"""
        response = self.manager_session.get(
            f"{BASE_URL}/approvals/matrix-log",
            params={"limit": 100},
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify structure
        assert "items" in data, "Missing 'items' key"
        
        # Verify item structure
        for item in data.get("items", [])[:5]:  # Check first 5
            assert "stage_label" in item, "Item missing 'stage_label'"
            assert "doc_number" in item, "Item missing 'doc_number'"
            assert "actor_name" in item, "Item missing 'actor_name'"
            assert "actor_role" in item, "Item missing 'actor_role'"
            assert "level" in item, "Item missing 'level'"
            assert "outcome" in item, "Item missing 'outcome'"
            assert "violation" in item, "Item missing 'violation'"
            assert "created_at" in item, "Item missing 'created_at'"
        
        self.log(f"Matrix log: {len(data.get('items', []))} entries", "info")

    def test_matrix_log_violations_filter(self):
        """Test GET /api/approvals/matrix-log?only_violations=true filters violations"""
        response = self.manager_session.get(
            f"{BASE_URL}/approvals/matrix-log",
            params={"only_violations": "true", "limit": 50},
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # All items should have violation=true
        for item in data.get("items", []):
            assert item.get("violation") is True, \
                f"Expected violation=true, got {item.get('violation')}"

    # ═══ TEST 4: ENFORCEMENT - design_acc (ACC Desain) ═══
    def test_design_acc_enforcement(self):
        """Test design_acc enforcement: sales 403, SoD 403, admin 200"""
        # Create a spec as manager
        spec_payload = {
            "title": f"Test Spec PS-20 {date.today().isoformat()}",
            "sample_type_hint": "labdip",
            "target": {
                "fabric_type": "woven",
                "stage": "grey",
                "gramasi": 120,
                "lebar": 115
            },
            "base_unit": "meter",
            "target_price": 55000,
            "sku_hint": "",
            "notes": "Test PS-20 enforcement"
        }
        
        # Create spec
        response = self.manager_session.post(
            f"{BASE_URL}/rnd/specs",
            json=spec_payload,
            timeout=30
        )
        assert response.status_code in (200, 201), \
            f"Failed to create spec: {response.status_code}"
        spec = response.json()
        spec_id = spec["id"]
        
        # Submit spec
        response = self.manager_session.post(
            f"{BASE_URL}/rnd/specs/{spec_id}/submit",
            json={},
            timeout=30
        )
        assert response.status_code == 200, \
            f"Failed to submit spec: {response.status_code}"
        
        # Test 1: Sales tries to approve -> 403
        approve_payload = {
            "sku": f"TEST{date.today().strftime('%m%d')}",
            "name": "Test Kain"
        }
        response = self.sales_session.post(
            f"{BASE_URL}/rnd/specs/{spec_id}/approve",
            json=approve_payload,
            timeout=30
        )
        assert response.status_code == 403, \
            f"Sales should get 403 when approving, got {response.status_code}"
        
        # Test 2: Manager (requester) tries to approve own spec -> 403 (SoD)
        response = self.manager_session.post(
            f"{BASE_URL}/rnd/specs/{spec_id}/approve",
            json=approve_payload,
            timeout=30
        )
        assert response.status_code == 403, \
            f"Manager (requester) should get 403 due to SoD, got {response.status_code}"
        
        # Verify SoD message in Indonesian
        detail = response.json().get("detail", "")
        assert "emisahan tugas" in detail.lower() or "pemisahan tugas" in detail.lower(), \
            f"Expected SoD message in Indonesian, got: {detail}"
        
        # Test 3: Admin (not requester) approves -> 200
        response = self.admin_session.post(
            f"{BASE_URL}/rnd/specs/{spec_id}/approve",
            json=approve_payload,
            timeout=30
        )
        assert response.status_code == 200, \
            f"Admin should be able to approve, got {response.status_code}"
        
        self.log(f"design_acc enforcement verified: sales 403, SoD 403, admin 200", "info")

    # ═══ TEST 5: ENFORCEMENT - purchase_request (PR) ═══
    def test_pr_enforcement(self):
        """Test PR enforcement: warehouse 403, SoD 403, manager 200"""
        # Create PR as warehouse (> Rp 50 juta to require approval)
        pr_payload = {
            "items": [{
                "description": "Test Bahan PS-20",
                "quantity": 500,
                "unit": "meter",
                "est_price": 200000  # Total: Rp 100 juta
            }],
            "entity_id": ENTITY_ID,
            "reason": "Test PS-20 PR enforcement",
            "submit_now": True,
            "source": "manual"
        }
        
        response = self.warehouse_session.post(
            f"{BASE_URL}/purchase-requisitions",
            json=pr_payload,
            timeout=30
        )
        assert response.status_code in (200, 201), \
            f"Failed to create PR: {response.status_code}"
        pr = response.json()
        pr_id = pr["id"]
        
        # Verify status is pending_approval
        assert pr.get("status") == "pending_approval", \
            f"PR should be pending_approval, got {pr.get('status')}"
        
        # Test 1: Warehouse tries to approve own PR -> 403
        response = self.warehouse_session.post(
            f"{BASE_URL}/purchase-requisitions/{pr_id}/approve",
            json={"notes": "Test"},
            timeout=30
        )
        assert response.status_code == 403, \
            f"Warehouse should get 403, got {response.status_code}"
        
        # Test 2: Manager approves -> 200
        response = self.manager_session.post(
            f"{BASE_URL}/purchase-requisitions/{pr_id}/approve",
            json={"notes": "Approved by manager"},
            timeout=30
        )
        assert response.status_code == 200, \
            f"Manager should be able to approve, got {response.status_code}"
        
        self.log(f"PR enforcement verified: warehouse 403, manager 200", "info")

    # ═══ TEST 6: ENFORCEMENT - po_custom (2 levels) ═══
    def test_po_custom_2_levels(self):
        """Test PO Custom 2-level approval: Manager -> Direksi"""
        # Get first customer
        response = self.manager_session.get(f"{BASE_URL}/customers", timeout=30)
        assert response.status_code == 200, "Failed to get customers"
        customers_data = response.json()
        customers = customers_data.get("items", []) if isinstance(customers_data, dict) else customers_data
        assert len(customers) > 0, "No customers found"
        customer = customers[0]
        
        # Create special order >= Rp 100 juta (2 levels required)
        so_payload = {
            "customer_id": customer["id"],
            "entity_id": ENTITY_ID,
            "custom_item": {
                "description": "Test Custom Item PS-20",
                "specifications": {"warna": "indigo"},
                "quantity": 100,
                "unit": "meter",
                "target_price": 2000000,  # Rp 2 juta per meter = Rp 200 juta total
                "notes": "Test 2-level approval"
            },
            "expected_delivery": (date.today() + timedelta(days=30)).isoformat(),
            "notes": "Test PS-20 2-level",
            "submit_for_approval": True
        }
        
        response = self.sales_session.post(
            f"{BASE_URL}/special-orders",
            json=so_payload,
            timeout=30
        )
        assert response.status_code in (200, 201), \
            f"Failed to create special order: {response.status_code}"
        so = response.json()
        so_id = so["id"]
        
        # Verify status is pending_approval
        assert so.get("status") == "pending_approval", \
            f"SO should be pending_approval, got {so.get('status')}"
        
        # Verify approval_chain has 2 levels
        chain = so.get("approval_chain", [])
        assert len(chain) == 2, \
            f"Approval chain should have 2 levels, got {len(chain)}"
        
        # Test 1: Manager approves level 1 -> 200 but status stays pending_approval
        response = self.manager_session.post(
            f"{BASE_URL}/special-orders/{so_id}/approve",
            json={"notes": "Level 1 approved"},
            timeout=30
        )
        assert response.status_code == 200, \
            f"Manager should approve level 1, got {response.status_code}"
        
        # Get updated SO
        response = self.manager_session.get(f"{BASE_URL}/special-orders/{so_id}", timeout=30)
        assert response.status_code == 200, "Failed to get SO"
        so_updated = response.json()
        
        # Verify status is still pending_approval
        assert so_updated.get("status") == "pending_approval", \
            f"Status should stay pending_approval after level 1, got {so_updated.get('status')}"
        
        # Verify approval_level_current is 2
        assert so_updated.get("approval_level_current") == 2, \
            f"Current level should be 2, got {so_updated.get('approval_level_current')}"
        
        # Test 2: Manager tries to approve level 2 -> 403 (only Direksi/admin)
        response = self.manager_session.post(
            f"{BASE_URL}/special-orders/{so_id}/approve",
            json={"notes": "Level 2 by manager"},
            timeout=30
        )
        assert response.status_code == 403, \
            f"Manager should get 403 at level 2, got {response.status_code}"
        
        # Test 3: Admin approves level 2 -> 200 and status becomes confirmed
        response = self.admin_session.post(
            f"{BASE_URL}/special-orders/{so_id}/approve",
            json={"notes": "Level 2 approved by Direksi"},
            timeout=30
        )
        assert response.status_code == 200, \
            f"Admin should approve level 2, got {response.status_code}"
        
        # Get final SO
        response = self.admin_session.get(f"{BASE_URL}/special-orders/{so_id}", timeout=30)
        assert response.status_code == 200, "Failed to get SO"
        so_final = response.json()
        
        # Verify status is confirmed
        assert so_final.get("status") == "confirmed", \
            f"Status should be confirmed after level 2, got {so_final.get('status')}"
        
        self.log(f"PO Custom 2-level verified: Manager L1 -> Admin L2 -> confirmed", "info")

    # ═══ TEST 7: Retroactivity Switch ═══
    def test_retroactivity_switch(self):
        """Test retroactivity switch: new_only mode exempts old documents"""
        # Create PR as manager
        pr_payload = {
            "items": [{
                "description": "Test Retro PR",
                "quantity": 500,
                "unit": "meter",
                "est_price": 200000
            }],
            "entity_id": ENTITY_ID,
            "reason": "Test retroactivity",
            "submit_now": True,
            "source": "manual"
        }
        
        response = self.manager_session.post(
            f"{BASE_URL}/purchase-requisitions",
            json=pr_payload,
            timeout=30
        )
        assert response.status_code in (200, 201), \
            f"Failed to create PR: {response.status_code}"
        pr = response.json()
        pr_id = pr["id"]
        
        # Switch to new_only mode with tomorrow as effective date
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        
        # Set scope to new_only
        response = self.admin_session.put(
            f"{BASE_URL}/config/values",
            json={"items": [{
                "key": "approval.matrix_scope",
                "value": "new_only",
                "scope_type": "global",
                "reason": "Test PS-20 retroactivity"
            }]},
            timeout=30
        )
        assert response.status_code in (200, 201), \
            f"Failed to set scope: {response.status_code}"
        
        # Set effective_from to tomorrow
        response = self.admin_session.put(
            f"{BASE_URL}/config/values",
            json={"items": [{
                "key": "approval.matrix_effective_from",
                "value": tomorrow,
                "scope_type": "global",
                "reason": "Test PS-20 retroactivity"
            }]},
            timeout=30
        )
        assert response.status_code in (200, 201), \
            f"Failed to set effective_from: {response.status_code}"
        
        # Verify matrix reports new_only
        response = self.manager_session.get(f"{BASE_URL}/approvals/matrix", timeout=30)
        assert response.status_code == 200, "Failed to get matrix"
        matrix = response.json()
        assert matrix.get("config", {}).get("scope") == "new_only", \
            "Matrix should report scope=new_only"
        
        # Manager (requester) tries to approve own PR -> should succeed (old document)
        response = self.manager_session.post(
            f"{BASE_URL}/purchase-requisitions/{pr_id}/approve",
            json={"notes": "Retro test"},
            timeout=30
        )
        assert response.status_code == 200, \
            f"Old document should be exempt from SoD in new_only mode, got {response.status_code}"
        
        # Restore defaults
        response = self.admin_session.put(
            f"{BASE_URL}/config/values",
            json={"items": [{
                "key": "approval.matrix_scope",
                "value": "all_pending",
                "scope_type": "global",
                "reason": "Restore default"
            }]},
            timeout=30
        )
        assert response.status_code in (200, 201), "Failed to restore scope"
        
        response = self.admin_session.put(
            f"{BASE_URL}/config/values",
            json={"items": [{
                "key": "approval.matrix_effective_from",
                "value": "",
                "scope_type": "global",
                "reason": "Restore default"
            }]},
            timeout=30
        )
        assert response.status_code in (200, 201), "Failed to restore effective_from"
        
        self.log(f"Retroactivity switch verified: new_only exempts old documents", "info")

    # ═══ TEST 8: Regression ═══
    def test_regression_endpoints(self):
        """Test that existing endpoints still work"""
        # /api/rnd/divisions
        response = self.manager_session.get(f"{BASE_URL}/rnd/divisions", timeout=30)
        assert response.status_code == 200, \
            f"/rnd/divisions should return 200, got {response.status_code}"
        data = response.json()
        assert len(data.get("divisions", [])) == 7, "Should have 7 divisions"
        assert len(data.get("approver_matrix", [])) == 4, "Should have 4 approval stages"
        
        # /api/rnd/divisions/members
        response = self.manager_session.get(f"{BASE_URL}/rnd/divisions/members", timeout=30)
        assert response.status_code == 200, \
            f"/rnd/divisions/members should return 200, got {response.status_code}"
        
        # /api/approvals/queue (old inbox)
        response = self.manager_session.get(f"{BASE_URL}/approvals/queue", timeout=30)
        assert response.status_code == 200, \
            f"/approvals/queue should return 200, got {response.status_code}"
        
        # /api/rnd/reports/designer-kpi
        response = self.manager_session.get(
            f"{BASE_URL}/rnd/reports/designer-kpi",
            params={"period": "all"},
            timeout=30
        )
        assert response.status_code == 200, \
            f"KPI endpoint should return 200, got {response.status_code}"
        
        # /api/purchase-requisitions
        response = self.manager_session.get(f"{BASE_URL}/purchase-requisitions", timeout=30)
        assert response.status_code == 200, \
            f"PR list should return 200, got {response.status_code}"
        
        # /api/special-orders
        response = self.manager_session.get(f"{BASE_URL}/special-orders", timeout=30)
        assert response.status_code == 200, \
            f"Special orders list should return 200, got {response.status_code}"
        
        self.log("Regression tests passed: all existing endpoints work", "info")

    def run_all_tests(self):
        """Run all PS-20 tests"""
        print("\n" + "="*70)
        print("BACKEND API TESTING - PS-20 (D-14)")
        print("MATRIKS PERSETUJUAN DIVISI MENGIKAT")
        print("="*70 + "\n")

        # Setup
        try:
            self.setup_auth()
        except Exception as e:
            self.log(f"Authentication setup failed: {e}", "fail")
            return 1

        # Test 1: Matrix endpoint
        print("\n" + "-"*70)
        print("TEST 1: GET /api/approvals/matrix")
        print("-"*70)
        self.run_test("Matrix endpoint (manager 200)", self.test_matrix_manager_200)
        self.run_test("Matrix endpoint (sales 403)", self.test_matrix_sales_403)
        self.run_test("Matrix endpoint (warehouse 403)", self.test_matrix_warehouse_403)

        # Test 2: My Queue endpoint
        print("\n" + "-"*70)
        print("TEST 2: GET /api/approvals/my-queue")
        print("-"*70)
        self.run_test("My queue (manager 200)", self.test_my_queue_manager_200)
        self.run_test("My queue stage filter", self.test_my_queue_stage_filter)
        self.run_test("My queue invalid stage (400)", self.test_my_queue_invalid_stage_400)
        self.run_test("My queue (sales 403)", self.test_my_queue_sales_403)
        self.run_test("My queue (warehouse 403)", self.test_my_queue_warehouse_403)

        # Test 3: Matrix log
        print("\n" + "-"*70)
        print("TEST 3: GET /api/approvals/matrix-log")
        print("-"*70)
        self.run_test("Matrix log (manager 200)", self.test_matrix_log_manager_200)
        self.run_test("Matrix log violations filter", self.test_matrix_log_violations_filter)

        # Test 4: Enforcement - design_acc
        print("\n" + "-"*70)
        print("TEST 4: ENFORCEMENT - design_acc (ACC Desain)")
        print("-"*70)
        self.run_test("design_acc enforcement (sales 403, SoD 403, admin 200)", 
                     self.test_design_acc_enforcement)

        # Test 5: Enforcement - purchase_request
        print("\n" + "-"*70)
        print("TEST 5: ENFORCEMENT - purchase_request (PR)")
        print("-"*70)
        self.run_test("PR enforcement (warehouse 403, manager 200)", 
                     self.test_pr_enforcement)

        # Test 6: Enforcement - po_custom (2 levels)
        print("\n" + "-"*70)
        print("TEST 6: ENFORCEMENT - po_custom (2 levels)")
        print("-"*70)
        self.run_test("PO Custom 2-level approval (Manager -> Direksi)", 
                     self.test_po_custom_2_levels)

        # Test 7: Retroactivity switch
        print("\n" + "-"*70)
        print("TEST 7: Retroactivity Switch")
        print("-"*70)
        self.run_test("Retroactivity switch (new_only exempts old docs)", 
                     self.test_retroactivity_switch)

        # Test 8: Regression
        print("\n" + "-"*70)
        print("TEST 8: Regression (existing endpoints)")
        print("-"*70)
        self.run_test("Regression endpoints", self.test_regression_endpoints)

        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Total tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Tests failed: {len(self.failed_tests)}")
        print(f"Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print("\nFailed tests:")
            for fail in self.failed_tests:
                print(f"  ❌ {fail['test']}: {fail['error']}")
        
        print("="*70 + "\n")
        
        return 0 if self.tests_passed == self.tests_run else 1

if __name__ == "__main__":
    tester = PS20Tester()
    sys.exit(tester.run_all_tests())
