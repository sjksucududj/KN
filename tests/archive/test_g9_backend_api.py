#!/usr/bin/env python3
"""Backend API Testing for FASE G-9 — Pusat Kasus Keuangan"""
import requests
import sys

BASE_URL = "https://hahabannamaka-test.preview.emergentagent.com/api"
CREDENTIALS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "manager": {"email": "manager@kainnusantara.id", "password": "demo12345"},
    "sales": {"email": "sales@kainnusantara.id", "password": "demo12345"},
}

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add(self, name, passed, details=""):
        self.tests.append({"name": name, "passed": passed, "details": details})
        if passed:
            self.passed += 1
            print(f"✅ PASS: {name}")
        else:
            self.failed += 1
            print(f"❌ FAIL: {name} - {details}")
        if details and passed:
            print(f"   {details}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*70}")
        print(f"BACKEND TEST RESULTS: {self.passed}/{total} PASSED")
        print(f"{'='*70}")
        return 0 if self.failed == 0 else 1

def login(role="admin"):
    """Login and get token"""
    try:
        creds = CREDENTIALS.get(role, CREDENTIALS["admin"])
        r = requests.post(f"{BASE_URL}/auth/login", json=creds, timeout=30)
        r.raise_for_status()
        token = r.json().get("token")
        return token
    except Exception as e:
        print(f"❌ Login failed for {role}: {e}")
        return None

def headers(token, entity_id="ent_ksc"):
    """Get headers with token and entity"""
    h = {"Authorization": f"Bearer {token}"}
    if entity_id:
        h["X-Entity-Id"] = entity_id
    return h

def test_backend():
    result = TestResult()
    
    # Login
    print("\n=== AUTHENTICATION ===")
    admin_token = login("admin")
    result.add("Admin login", admin_token is not None, f"Token: {admin_token[:20]}..." if admin_token else "")
    
    manager_token = login("manager")
    result.add("Manager login", manager_token is not None)
    
    sales_token = login("sales")
    result.add("Sales login", sales_token is not None)
    
    if not admin_token:
        print("Cannot proceed without admin token")
        return result.summary()
    
    # US1 & US9: Playbooks, Policy, Stats
    print("\n=== US1 & US9: PLAYBOOKS, POLICY, STATS ===")
    try:
        r = requests.get(f"{BASE_URL}/finance-cases/playbooks", headers=headers(admin_token), timeout=30)
        playbooks = r.json() if r.status_code == 200 else []
        result.add("GET /finance-cases/playbooks", 
                   r.status_code == 200 and len(playbooks) == 11,
                   f"Status: {r.status_code}, Count: {len(playbooks)}")
    except Exception as e:
        result.add("GET /finance-cases/playbooks", False, str(e))
    
    try:
        r = requests.get(f"{BASE_URL}/finance-cases/policy", headers=headers(admin_token), timeout=30)
        policy = r.json() if r.status_code == 200 else {}
        result.add("GET /finance-cases/policy", 
                   r.status_code == 200 and "sla_hours" in policy and "approval_above" in policy,
                   f"SLA: {policy.get('sla_hours')}h, Approval: Rp {policy.get('approval_above'):,.0f}")
    except Exception as e:
        result.add("GET /finance-cases/policy", False, str(e))
    
    try:
        r = requests.get(f"{BASE_URL}/finance-cases/stats", headers=headers(admin_token), timeout=30)
        stats = r.json() if r.status_code == 200 else {}
        result.add("GET /finance-cases/stats", 
                   r.status_code == 200 and "open" in stats and "money_at_stake" in stats,
                   f"Open: {stats.get('open')}, Money: Rp {stats.get('money_at_stake', 0):,.0f}")
    except Exception as e:
        result.add("GET /finance-cases/stats", False, str(e))
    
    try:
        r = requests.get(f"{BASE_URL}/finance-cases/reasons", headers=headers(admin_token), timeout=30)
        reasons = r.json() if r.status_code == 200 else []
        result.add("GET /finance-cases/reasons", 
                   r.status_code == 200 and len(reasons) >= 9,
                   f"Count: {len(reasons)}")
    except Exception as e:
        result.add("GET /finance-cases/reasons", False, str(e))
    
    # US1: List cases with filters
    print("\n=== US1: LIST CASES & FILTERS ===")
    try:
        r = requests.get(f"{BASE_URL}/finance-cases", headers=headers(admin_token), timeout=30)
        cases = r.json() if r.status_code == 200 else []
        result.add("GET /finance-cases (all)", 
                   r.status_code == 200 and isinstance(cases, list),
                   f"Total cases: {len(cases)}")
        
        # Test filters
        r = requests.get(f"{BASE_URL}/finance-cases?status=open", headers=headers(admin_token), timeout=30)
        open_cases = r.json() if r.status_code == 200 else []
        result.add("GET /finance-cases?status=open", 
                   r.status_code == 200,
                   f"Open cases: {len(open_cases)}")
        
        r = requests.get(f"{BASE_URL}/finance-cases?overdue_only=true", headers=headers(admin_token), timeout=30)
        overdue_cases = r.json() if r.status_code == 200 else []
        result.add("GET /finance-cases?overdue_only=true", 
                   r.status_code == 200,
                   f"Overdue cases: {len(overdue_cases)}")
        
        # Get a case detail
        if cases:
            case_id = cases[0]["id"]
            r = requests.get(f"{BASE_URL}/finance-cases/{case_id}", headers=headers(admin_token), timeout=30)
            case_detail = r.json() if r.status_code == 200 else {}
            result.add(f"GET /finance-cases/{{id}}", 
                       r.status_code == 200 and "number" in case_detail,
                       f"Case: {case_detail.get('number')}, Status: {case_detail.get('status')}")
    except Exception as e:
        result.add("GET /finance-cases", False, str(e))
    
    # US4: Scan (idempotent)
    print("\n=== US4: AUTO SCAN (IDEMPOTENT) ===")
    try:
        r = requests.post(f"{BASE_URL}/finance-cases/scan", headers=headers(admin_token), json={}, timeout=60)
        scan_result = r.json() if r.status_code == 200 else {}
        result.add("POST /finance-cases/scan", 
                   r.status_code == 200,
                   f"Holding: {scan_result.get('holding_cases', 0)}, Duplicate: {scan_result.get('duplicate_cases', 0)}, Skipped: {scan_result.get('skipped', 0)}")
    except Exception as e:
        result.add("POST /finance-cases/scan", False, str(e))
    
    # US10: Create new case
    print("\n=== US10: CREATE NEW CASE ===")
    try:
        new_case_data = {
            "case_type": "dana_tak_dikenal",
            "title": "Test case - dana tak dikenal",
            "amount": 500000,
            "description": "Testing case creation"
        }
        r = requests.post(f"{BASE_URL}/finance-cases", headers=headers(admin_token), json=new_case_data, timeout=30)
        new_case = r.json() if r.status_code == 200 else {}
        created_case_id = new_case.get("id")
        result.add("POST /finance-cases (create)", 
                   r.status_code == 200 and "id" in new_case,
                   f"Created: {new_case.get('number')}")
        
        # US10: Assign case
        if created_case_id:
            r = requests.post(f"{BASE_URL}/finance-cases/{created_case_id}/assign", 
                            headers=headers(admin_token), 
                            json={"assignee": "Test User"}, timeout=30)
            result.add("POST /finance-cases/{{id}}/assign", 
                       r.status_code == 200,
                       f"Assigned to: Test User")
            
            # US10: Add note
            r = requests.post(f"{BASE_URL}/finance-cases/{created_case_id}/note", 
                            headers=headers(admin_token), 
                            json={"note": "Test note", "attachments": []}, timeout=30)
            result.add("POST /finance-cases/{{id}}/note", 
                       r.status_code == 200,
                       "Note added")
            
            # US10: Reject case (cleanup)
            r = requests.post(f"{BASE_URL}/finance-cases/{created_case_id}/reject", 
                            headers=headers(admin_token), 
                            json={"reason_code": "case_identified_owner", "note": "Test cleanup"}, timeout=30)
            result.add("POST /finance-cases/{{id}}/reject", 
                       r.status_code == 200,
                       "Case rejected")
    except Exception as e:
        result.add("POST /finance-cases (create)", False, str(e))
    
    # US11: Cross-entity isolation
    print("\n=== US11: CROSS-ENTITY ISOLATION ===")
    try:
        # Create case in ent_kanda
        new_case_data = {
            "case_type": "dana_tak_dikenal",
            "title": "Test case PT-B",
            "amount": 300000,
            "entity_id": "ent_kanda"
        }
        r = requests.post(f"{BASE_URL}/finance-cases", 
                         headers=headers(admin_token, "ent_kanda"), 
                         json=new_case_data, timeout=30)
        case_b = r.json() if r.status_code == 200 else {}
        case_b_id = case_b.get("id")
        
        if case_b_id:
            # Try to access from ent_ksc (should fail)
            r = requests.get(f"{BASE_URL}/finance-cases/{case_b_id}", 
                           headers=headers(manager_token, "ent_ksc"), timeout=30)
            result.add("Cross-entity isolation (403 expected)", 
                       r.status_code == 403,
                       f"Status: {r.status_code}")
            
            # Access with 'all' entity (should work)
            r = requests.get(f"{BASE_URL}/finance-cases/{case_b_id}", 
                           headers=headers(admin_token, "all"), timeout=30)
            result.add("Admin with X-Entity-Id: all can access", 
                       r.status_code == 200,
                       f"Status: {r.status_code}")
            
            # Cleanup
            requests.post(f"{BASE_URL}/finance-cases/{case_b_id}/reject", 
                         headers=headers(admin_token, "ent_kanda"), 
                         json={"reason_code": "case_identified_owner", "note": "Test cleanup"}, timeout=30)
    except Exception as e:
        result.add("Cross-entity isolation", False, str(e))
    
    # US3: Guards - test validation
    print("\n=== US3: GUARDS & VALIDATION ===")
    try:
        # Create a case for testing guards
        new_case_data = {
            "case_type": "pembayar_pihak_ketiga",
            "title": "Test guards",
            "amount": 750000
        }
        r = requests.post(f"{BASE_URL}/finance-cases", headers=headers(admin_token), json=new_case_data, timeout=30)
        guard_case = r.json() if r.status_code == 200 else {}
        guard_case_id = guard_case.get("id")
        
        if guard_case_id:
            # Try to resolve without reason_code (should fail)
            r = requests.post(f"{BASE_URL}/finance-cases/{guard_case_id}/resolve", 
                            headers=headers(admin_token), 
                            json={"action": "alokasi_titipan", "reason_code": ""}, timeout=30)
            result.add("Guard: resolve without reason_code (400 expected)", 
                       r.status_code == 400 and "alasan" in r.text.lower(),
                       f"Status: {r.status_code}")
            
            # Try to resolve without evidence (should fail for this case type)
            r = requests.post(f"{BASE_URL}/finance-cases/{guard_case_id}/resolve", 
                            headers=headers(admin_token), 
                            json={"action": "alokasi_titipan", "reason_code": "case_third_party_payer"}, timeout=30)
            result.add("Guard: resolve without evidence (400 expected)", 
                       r.status_code == 400 and "bukti" in r.text.lower(),
                       f"Status: {r.status_code}")
            
            # Cleanup
            requests.post(f"{BASE_URL}/finance-cases/{guard_case_id}/reject", 
                         headers=headers(admin_token), 
                         json={"reason_code": "case_third_party_payer", "note": "Test cleanup"}, timeout=30)
    except Exception as e:
        result.add("Guards & validation", False, str(e))
    
    # US7: Document trace
    print("\n=== US7: DOCUMENT TRACE ===")
    try:
        # Get a resolved case
        r = requests.get(f"{BASE_URL}/finance-cases?status=resolved", headers=headers(admin_token), timeout=30)
        resolved_cases = r.json() if r.status_code == 200 else []
        if resolved_cases:
            case_id = resolved_cases[0]["id"]
            r = requests.get(f"{BASE_URL}/documents/trace/finance_case/{case_id}", 
                           headers=headers(admin_token), timeout=30)
            result.add("GET /documents/trace/finance_case/{{id}}", 
                       r.status_code == 200,
                       f"Status: {r.status_code}")
    except Exception as e:
        result.add("Document trace", False, str(e))
    
    # RBAC: Sales should have view access but not resolve
    print("\n=== RBAC: SALES PERMISSIONS ===")
    try:
        r = requests.get(f"{BASE_URL}/finance-cases/stats", headers=headers(sales_token), timeout=30)
        result.add("Sales can view stats", 
                   r.status_code == 200,
                   f"Status: {r.status_code}")
        
        r = requests.get(f"{BASE_URL}/finance-cases", headers=headers(sales_token), timeout=30)
        result.add("Sales can view cases list", 
                   r.status_code == 200,
                   f"Status: {r.status_code}")
    except Exception as e:
        result.add("Sales RBAC", False, str(e))
    
    return result.summary()

if __name__ == "__main__":
    sys.exit(test_backend())
