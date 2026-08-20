"""
Backend Test: F0-A Entity Identity & Context (Multi-Entity Foundation)
========================================================================

Tests the multi-entity foundation implementation including:
1. POST /api/auth/login returns entity_context with proper structure
2. Entity distribution per role (Model 1 - silo selling)
3. GET /api/auth/me honors X-Entity-Id header
4. Backend isolation - sales users cannot operate on disallowed entities
5. GET /api/auth/context returns entity context
6. GET /api/entities returns 2 entities with enriched fields
7. Regression testing - existing auth still works
8. Regression testing - existing protected endpoints still work
"""
import requests
import sys
from typing import Dict, Any, Optional

# Use PUBLIC endpoint
BASE_URL = "https://po-pdf-sender.preview.emergentagent.com/api"

# Test credentials
CREDENTIALS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "manager": {"email": "manager@kainnusantara.id", "password": "demo12345"},
    "sales": {"email": "sales@kainnusantara.id", "password": "demo12345"},
    "sales3": {"email": "sales3@kainnusantara.id", "password": "demo12345"},
    "warehouse": {"email": "warehouse@kainnusantara.id", "password": "demo12345"},
}

# Entity IDs
ENT_KSC = "ent_ksc"
ENT_KANDA = "ent_kanda"


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
        
    def test(self, name: str, condition: bool, details: str = ""):
        """Record a test result"""
        self.tests.append({"name": name, "passed": condition, "details": details})
        if condition:
            self.passed += 1
            print(f"  ✅ PASS: {name}")
            if details:
                print(f"      {details}")
        else:
            self.failed += 1
            print(f"  ❌ FAIL: {name}")
            if details:
                print(f"      {details}")
    
    def summary(self):
        """Print test summary"""
        total = self.passed + self.failed
        print(f"\n{'='*70}")
        print(f"TEST SUMMARY: {self.passed}/{total} passed, {self.failed}/{total} failed")
        print(f"{'='*70}")
        return self.failed == 0


def login(email: str, password: str) -> Dict[str, Any]:
    """Login and return full response"""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password},
        timeout=10
    )
    if response.status_code != 200:
        raise Exception(f"Login failed for {email}: {response.status_code} - {response.text}")
    return response.json()


def headers(token: str, entity_id: Optional[str] = None) -> Dict[str, str]:
    """Build request headers"""
    h = {"Authorization": f"Bearer {token}"}
    if entity_id:
        h["X-Entity-Id"] = entity_id
    return h


def test_login_entity_context(runner: TestRunner):
    """Test 1: POST /api/auth/login returns entity_context"""
    print("\n" + "="*70)
    print("TEST 1: Login Returns Entity Context")
    print("="*70)
    
    # Login as admin
    admin_response = login(**CREDENTIALS["admin"])
    
    # Check entity_context exists
    runner.test(
        "Login response contains entity_context",
        "entity_context" in admin_response,
        f"Keys in response: {list(admin_response.keys())}"
    )
    
    if "entity_context" not in admin_response:
        return
    
    ec = admin_response["entity_context"]
    
    # Check required keys in entity_context
    required_keys = ["home_entity_id", "allowed_entity_ids", "active_entity_id", "can_switch_entity", "entities"]
    for key in required_keys:
        runner.test(
            f"entity_context has '{key}'",
            key in ec,
            f"entity_context keys: {list(ec.keys())}"
        )
    
    # Check user object has entity fields
    user = admin_response.get("user", {})
    runner.test(
        "user has home_entity_id",
        "home_entity_id" in user,
        f"user.home_entity_id = {user.get('home_entity_id')}"
    )
    
    runner.test(
        "user has allowed_entity_ids",
        "allowed_entity_ids" in user,
        f"user.allowed_entity_ids = {user.get('allowed_entity_ids')}"
    )
    
    # Check password_hash is NOT exposed
    runner.test(
        "user does NOT expose password_hash",
        "password_hash" not in user,
        "Security check: password_hash should not be in response"
    )


def test_entity_distribution(runner: TestRunner):
    """Test 2: Entity distribution per role (Model 1)"""
    print("\n" + "="*70)
    print("TEST 2: Entity Distribution Per Role (Model 1)")
    print("="*70)
    
    # Test admin - cross-entity access
    admin_resp = login(**CREDENTIALS["admin"])
    admin_ec = admin_resp.get("entity_context", {})
    admin_user = admin_resp.get("user", {})
    
    runner.test(
        "admin home_entity_id = ent_ksc",
        admin_user.get("home_entity_id") == ENT_KSC,
        f"Got: {admin_user.get('home_entity_id')}"
    )
    
    runner.test(
        "admin allowed_entity_ids = [ent_ksc, ent_kanda]",
        set(admin_ec.get("allowed_entity_ids", [])) == {ENT_KSC, ENT_KANDA},
        f"Got: {admin_ec.get('allowed_entity_ids')}"
    )
    
    runner.test(
        "admin can_switch_entity = True",
        admin_ec.get("can_switch_entity") is True,
        f"Got: {admin_ec.get('can_switch_entity')}"
    )
    
    # Test manager - cross-entity access
    manager_resp = login(**CREDENTIALS["manager"])
    manager_ec = manager_resp.get("entity_context", {})
    
    runner.test(
        "manager can_switch_entity = True",
        manager_ec.get("can_switch_entity") is True,
        f"Got: {manager_ec.get('can_switch_entity')}"
    )
    
    runner.test(
        "manager allowed_entity_ids includes both entities",
        set(manager_ec.get("allowed_entity_ids", [])) == {ENT_KSC, ENT_KANDA},
        f"Got: {manager_ec.get('allowed_entity_ids')}"
    )
    
    # Test sales - locked to ent_ksc
    sales_resp = login(**CREDENTIALS["sales"])
    sales_ec = sales_resp.get("entity_context", {})
    sales_user = sales_resp.get("user", {})
    
    runner.test(
        "sales home_entity_id = ent_ksc",
        sales_user.get("home_entity_id") == ENT_KSC,
        f"Got: {sales_user.get('home_entity_id')}"
    )
    
    runner.test(
        "sales allowed_entity_ids = [ent_ksc] only",
        sales_ec.get("allowed_entity_ids") == [ENT_KSC],
        f"Got: {sales_ec.get('allowed_entity_ids')}"
    )
    
    runner.test(
        "sales can_switch_entity = False",
        sales_ec.get("can_switch_entity") is False,
        f"Got: {sales_ec.get('can_switch_entity')}"
    )
    
    # Test sales3 - locked to ent_kanda
    sales3_resp = login(**CREDENTIALS["sales3"])
    sales3_ec = sales3_resp.get("entity_context", {})
    sales3_user = sales3_resp.get("user", {})
    
    runner.test(
        "sales3 home_entity_id = ent_kanda",
        sales3_user.get("home_entity_id") == ENT_KANDA,
        f"Got: {sales3_user.get('home_entity_id')}"
    )
    
    runner.test(
        "sales3 allowed_entity_ids = [ent_kanda] only",
        sales3_ec.get("allowed_entity_ids") == [ENT_KANDA],
        f"Got: {sales3_ec.get('allowed_entity_ids')}"
    )
    
    # Test warehouse - locked to ent_ksc
    wh_resp = login(**CREDENTIALS["warehouse"])
    wh_ec = wh_resp.get("entity_context", {})
    
    runner.test(
        "warehouse allowed_entity_ids = [ent_ksc] only",
        wh_ec.get("allowed_entity_ids") == [ENT_KSC],
        f"Got: {wh_ec.get('allowed_entity_ids')}"
    )


def test_auth_me_header(runner: TestRunner):
    """Test 3: GET /api/auth/me honors X-Entity-Id header"""
    print("\n" + "="*70)
    print("TEST 3: /auth/me Honors X-Entity-Id Header")
    print("="*70)
    
    # Login as admin
    admin_resp = login(**CREDENTIALS["admin"])
    admin_token = admin_resp["token"]
    
    # Test without header - should return home entity
    me_default = requests.get(
        f"{BASE_URL}/auth/me",
        headers=headers(admin_token),
        timeout=10
    ).json()
    
    runner.test(
        "admin /auth/me without header returns active_entity_id = ent_ksc (home)",
        me_default.get("entity_context", {}).get("active_entity_id") == ENT_KSC,
        f"Got: {me_default.get('entity_context', {}).get('active_entity_id')}"
    )
    
    # Test with X-Entity-Id header - should switch to ent_kanda
    me_kanda = requests.get(
        f"{BASE_URL}/auth/me",
        headers=headers(admin_token, ENT_KANDA),
        timeout=10
    ).json()
    
    runner.test(
        "admin /auth/me with X-Entity-Id=ent_kanda returns active_entity_id = ent_kanda",
        me_kanda.get("entity_context", {}).get("active_entity_id") == ENT_KANDA,
        f"Got: {me_kanda.get('entity_context', {}).get('active_entity_id')}"
    )


def test_backend_isolation(runner: TestRunner):
    """Test 4: Backend isolation - sales cannot operate on disallowed entities"""
    print("\n" + "="*70)
    print("TEST 4: Backend Isolation (Sales Cannot Access Disallowed Entity)")
    print("="*70)
    
    # Login as sales (allowed only ent_ksc)
    sales_resp = login(**CREDENTIALS["sales"])
    sales_token = sales_resp["token"]
    
    # Try to force ent_kanda via header - should be IGNORED
    me_force = requests.get(
        f"{BASE_URL}/auth/me",
        headers=headers(sales_token, ENT_KANDA),
        timeout=10
    ).json()
    
    runner.test(
        "sales with X-Entity-Id=ent_kanda is IGNORED, active stays ent_ksc",
        me_force.get("entity_context", {}).get("active_entity_id") == ENT_KSC,
        f"Got: {me_force.get('entity_context', {}).get('active_entity_id')} (should be ent_ksc, not ent_kanda)"
    )


def test_auth_context(runner: TestRunner):
    """Test 5: GET /api/auth/context returns entity context"""
    print("\n" + "="*70)
    print("TEST 5: /auth/context Returns Entity Context")
    print("="*70)
    
    # Login as admin
    admin_resp = login(**CREDENTIALS["admin"])
    admin_token = admin_resp["token"]
    
    # Test /auth/context without header
    ctx_default = requests.get(
        f"{BASE_URL}/auth/context",
        headers=headers(admin_token),
        timeout=10
    )
    
    runner.test(
        "/auth/context returns 200",
        ctx_default.status_code == 200,
        f"Got status: {ctx_default.status_code}"
    )
    
    if ctx_default.status_code == 200:
        ctx_data = ctx_default.json()
        runner.test(
            "/auth/context returns active_entity_id",
            "active_entity_id" in ctx_data,
            f"Got keys: {list(ctx_data.keys())}"
        )
    
    # Test /auth/context with X-Entity-Id header
    ctx_kanda = requests.get(
        f"{BASE_URL}/auth/context",
        headers=headers(admin_token, ENT_KANDA),
        timeout=10
    )
    
    if ctx_kanda.status_code == 200:
        ctx_kanda_data = ctx_kanda.json()
        runner.test(
            "/auth/context honors X-Entity-Id header",
            ctx_kanda_data.get("active_entity_id") == ENT_KANDA,
            f"Got: {ctx_kanda_data.get('active_entity_id')}"
        )


def test_entities_endpoint(runner: TestRunner):
    """Test 6: GET /api/entities returns enriched entity data"""
    print("\n" + "="*70)
    print("TEST 6: /entities Returns Enriched Entity Data")
    print("="*70)
    
    # Login as admin
    admin_resp = login(**CREDENTIALS["admin"])
    admin_token = admin_resp["token"]
    
    # Get entities
    entities_resp = requests.get(
        f"{BASE_URL}/entities",
        headers=headers(admin_token),
        timeout=10
    )
    
    runner.test(
        "/entities returns 200",
        entities_resp.status_code == 200,
        f"Got status: {entities_resp.status_code}"
    )
    
    if entities_resp.status_code != 200:
        return
    
    entities = entities_resp.json()
    entities_map = {e["id"]: e for e in entities}
    
    runner.test(
        "/entities returns at least 2 entities",
        len(entities) >= 2,
        f"Got {len(entities)} entities"
    )
    
    runner.test(
        "/entities includes ent_ksc",
        ENT_KSC in entities_map,
        f"Entity IDs: {list(entities_map.keys())}"
    )
    
    runner.test(
        "/entities includes ent_kanda",
        ENT_KANDA in entities_map,
        f"Entity IDs: {list(entities_map.keys())}"
    )
    
    # Check enriched fields on ent_ksc
    if ENT_KSC in entities_map:
        ksc = entities_map[ENT_KSC]
        enriched_fields = ["currency", "coa_template", "incentive_payer", "numbering_scheme"]
        
        for field in enriched_fields:
            runner.test(
                f"ent_ksc has enriched field '{field}'",
                field in ksc,
                f"Value: {ksc.get(field)}"
            )
        
        runner.test(
            "ent_ksc incentive_payer = sales_entity (Model 1)",
            ksc.get("incentive_payer") == "sales_entity",
            f"Got: {ksc.get('incentive_payer')}"
        )
    
    # Check is_pkp in entity_context.entities
    admin_ec = admin_resp.get("entity_context", {})
    ec_entities = {e["id"]: e for e in admin_ec.get("entities", [])}
    
    if ENT_KSC in ec_entities:
        runner.test(
            "entity_context.entities[ent_ksc].is_pkp = True",
            ec_entities[ENT_KSC].get("is_pkp") is True,
            f"Got: {ec_entities[ENT_KSC].get('is_pkp')}"
        )
    
    if ENT_KANDA in ec_entities:
        runner.test(
            "entity_context.entities[ent_kanda].is_pkp = False",
            ec_entities[ENT_KANDA].get("is_pkp") is False,
            f"Got: {ec_entities[ENT_KANDA].get('is_pkp')}"
        )


def test_auth_regression(runner: TestRunner):
    """Test 7: Regression - existing auth still works"""
    print("\n" + "="*70)
    print("TEST 7: Auth Regression Tests")
    print("="*70)
    
    # Test valid login
    try:
        admin_resp = login(**CREDENTIALS["admin"])
        token = admin_resp.get("token")
        
        runner.test(
            "Valid login returns token",
            token is not None and token.startswith("sess_"),
            f"Token prefix: {token[:5] if token else 'None'}"
        )
    except Exception as e:
        runner.test("Valid login returns token", False, f"Exception: {str(e)}")
    
    # Test invalid password
    invalid_resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": "admin@kainnusantara.id", "password": "wrongpassword"},
        timeout=10
    )
    
    runner.test(
        "Invalid password returns 401",
        invalid_resp.status_code == 401,
        f"Got status: {invalid_resp.status_code}"
    )
    
    # Test logout
    if token:
        logout_resp = requests.post(
            f"{BASE_URL}/auth/logout",
            headers=headers(token),
            timeout=10
        )
        
        runner.test(
            "Logout returns 200",
            logout_resp.status_code == 200,
            f"Got status: {logout_resp.status_code}"
        )


def test_protected_endpoint_regression(runner: TestRunner):
    """Test 8: Regression - protected endpoints still work"""
    print("\n" + "="*70)
    print("TEST 8: Protected Endpoint Regression")
    print("="*70)
    
    # Login as admin
    admin_resp = login(**CREDENTIALS["admin"])
    admin_token = admin_resp["token"]
    
    # Test a protected endpoint - /api/home/admin
    home_resp = requests.get(
        f"{BASE_URL}/home/admin",
        headers=headers(admin_token),
        timeout=10
    )
    
    runner.test(
        "Protected endpoint /home/admin returns 200 for admin",
        home_resp.status_code == 200,
        f"Got status: {home_resp.status_code}"
    )
    
    # Test another protected endpoint - /api/sales-orders
    so_resp = requests.get(
        f"{BASE_URL}/sales-orders",
        headers=headers(admin_token),
        timeout=10
    )
    
    runner.test(
        "Protected endpoint /sales-orders returns 200 for admin",
        so_resp.status_code == 200,
        f"Got status: {so_resp.status_code}"
    )


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("F0-A ENTITY IDENTITY & CONTEXT - BACKEND TEST SUITE")
    print("="*70)
    print(f"Testing against: {BASE_URL}")
    print("="*70)
    
    runner = TestRunner()
    
    try:
        test_login_entity_context(runner)
        test_entity_distribution(runner)
        test_auth_me_header(runner)
        test_backend_isolation(runner)
        test_auth_context(runner)
        test_entities_endpoint(runner)
        test_auth_regression(runner)
        test_protected_endpoint_regression(runner)
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    success = runner.summary()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
