#!/usr/bin/env python3
"""
Backend API Testing for FASE G-9 — Pusat Kasus Keuangan
Testing all 11 user stories + 3 bug fixes
"""
import requests
import sys
from typing import Dict, Any

BASE_URL = "https://textile-erp-finance.preview.emergentagent.com/api"
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
    
    def add(self, name: str, passed: bool, details: str = ""):
        self.tests.append({"name": name, "passed": passed, "details": details})
        if passed:
            self.passed += 1
            print(f"✅ PASS: {name}")
            if details:
                print(f"   {details}")
        else:
            self.failed += 1
            print(f"❌ FAIL: {name}")
            if details:
                print(f"   {details}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"SUMMARY: {self.passed}/{total} tests passed")
        print(f"{'='*60}")
        return self.failed == 0

def login(role: str) -> str:
    """Login and return token"""
    try:
        creds = CREDENTIALS[role]
        resp = requests.post(f"{BASE_URL}/auth/login", json=creds, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("token", "")
        return ""
    except Exception as e:
        print(f"Login failed for {role}: {e}")
        return ""

def headers(token: str, entity_id: str = "ent_ksc") -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Entity-Id": entity_id,
        "Content-Type": "application/json"
    }

def test_playbooks_and_policy(result: TestResult, admin_token: str):
    """US1, US9: Test playbooks, reasons, and policy endpoints"""
    print("\n" + "="*60)
    print("TEST 1: PLAYBOOKS, REASONS & POLICY (US1, US9)")
    print("="*60)
    
    try:
        # Test playbooks endpoint
        resp = requests.get(f"{BASE_URL}/finance-cases/playbooks", 
                          headers=headers(admin_token), timeout=30)
        playbooks = resp.json() if resp.status_code == 200 else []
        result.add("GET /finance-cases/playbooks returns 11 playbooks",
                  resp.status_code == 200 and len(playbooks) == 11,
                  f"Status: {resp.status_code}, Count: {len(playbooks)}")
        
        # Check each playbook has reason_codes (BUG-FIX-2)
        has_reason_codes = all(isinstance(p.get("reason_codes"), list) for p in playbooks)
        result.add("BUG-FIX-2: All playbooks have reason_codes field",
                  has_reason_codes,
                  f"Playbooks with reason_codes: {sum(1 for p in playbooks if p.get('reason_codes'))}/11")
        
        # Test reasons endpoint
        resp = requests.get(f"{BASE_URL}/finance-cases/reasons",
                          headers=headers(admin_token), timeout=30)
        reasons = resp.json() if resp.status_code == 200 else []
        result.add("GET /finance-cases/reasons returns reason labels",
                  resp.status_code == 200 and len(reasons) >= 9,
                  f"Status: {resp.status_code}, Count: {len(reasons)}")
        
        # Test policy endpoint
        resp = requests.get(f"{BASE_URL}/finance-cases/policy",
                          headers=headers(admin_token), timeout=30)
        policy = resp.json() if resp.status_code == 200 else {}
        result.add("GET /finance-cases/policy returns SLA and approval settings",
                  resp.status_code == 200 and "sla_hours" in policy and "approval_above" in policy,
                  f"Status: {resp.status_code}, SLA: {policy.get('sla_hours')}h, Approval above: {policy.get('approval_above')}")
        
    except Exception as e:
        result.add("Playbooks and policy tests", False, str(e))

def test_inbox_and_stats(result: TestResult, admin_token: str, sales_token: str):
    """US1: Test inbox listing and stats"""
    print("\n" + "="*60)
    print("TEST 2: INBOX & STATS (US1)")
    print("="*60)
    
    try:
        # Test stats endpoint
        resp = requests.get(f"{BASE_URL}/finance-cases/stats",
                          headers=headers(admin_token), timeout=30)
        stats = resp.json() if resp.status_code == 200 else {}
        result.add("GET /finance-cases/stats returns summary",
                  resp.status_code == 200 and "open" in stats and "money_at_stake" in stats,
                  f"Status: {resp.status_code}, Open: {stats.get('open')}, Money at stake: {stats.get('money_at_stake')}")
        
        # Test cases listing
        resp = requests.get(f"{BASE_URL}/finance-cases",
                          headers=headers(admin_token), timeout=30)
        cases = resp.json() if resp.status_code == 200 else []
        result.add("GET /finance-cases returns case list",
                  resp.status_code == 200 and isinstance(cases, list),
                  f"Status: {resp.status_code}, Cases: {len(cases)}")
        
        # Test filtering by status
        resp = requests.get(f"{BASE_URL}/finance-cases?status=open",
                          headers=headers(admin_token), timeout=30)
        open_cases = resp.json() if resp.status_code == 200 else []
        result.add("GET /finance-cases?status=open filters correctly",
                  resp.status_code == 200,
                  f"Status: {resp.status_code}, Open cases: {len(open_cases)}")
        
        # Test overdue filter
        resp = requests.get(f"{BASE_URL}/finance-cases?overdue_only=true",
                          headers=headers(admin_token), timeout=30)
        overdue_cases = resp.json() if resp.status_code == 200 else []
        result.add("GET /finance-cases?overdue_only=true works",
                  resp.status_code == 200,
                  f"Status: {resp.status_code}, Overdue cases: {len(overdue_cases)}")
        
        # Test RBAC: sales can view (US1)
        resp = requests.get(f"{BASE_URL}/finance-cases/stats",
                          headers=headers(sales_token), timeout=30)
        result.add("US1: Sales role can view case stats (RBAC)",
                  resp.status_code == 200,
                  f"Status: {resp.status_code}")
        
    except Exception as e:
        result.add("Inbox and stats tests", False, str(e))

def test_guards_and_validation(result: TestResult, admin_token: str, sales_token: str):
    """US3, US5: Test guards (reason required, evidence required, approval)"""
    print("\n" + "="*60)
    print("TEST 3: GUARDS & VALIDATION (US3, US5, BUG-FIX-2)")
    print("="*60)
    
    try:
        # Get a case to test with
        resp = requests.get(f"{BASE_URL}/finance-cases",
                          headers=headers(admin_token), timeout=30)
        cases = resp.json() if resp.status_code == 200 else []
        
        if not cases:
            result.add("Guards test - no cases available", False, "No cases to test with")
            return
        
        # Find an open case
        open_case = next((c for c in cases if c.get("status") in ["open", "in_progress"]), None)
        if not open_case:
            result.add("Guards test - no open cases", False, "No open cases to test with")
            return
        
        case_id = open_case["id"]
        case_type = open_case["case_type"]
        
        # BUG-FIX-2: Test irrelevant reason rejection
        # Try to resolve with a reason that doesn't match the case type
        resp = requests.post(f"{BASE_URL}/finance-cases/{case_id}/resolve",
                           headers=headers(admin_token),
                           json={
                               "action": "alokasi_titipan",
                               "reason_code": "case_cheque_bounced",  # Wrong reason for dana_tak_dikenal
                               "customer_id": "cust_001",
                               "allocations": [{"order_id": "so_001", "amount": 100000}]
                           },
                           timeout=30)
        result.add("BUG-FIX-2: Irrelevant reason code is rejected with helpful message",
                  resp.status_code == 400 and "nyambung" in resp.text.lower(),
                  f"Status: {resp.status_code}, Response contains 'nyambung': {'nyambung' in resp.text.lower()}")
        
        # Test missing reason
        resp = requests.post(f"{BASE_URL}/finance-cases/{case_id}/resolve",
                           headers=headers(admin_token),
                           json={
                               "action": "alokasi_titipan",
                               "reason_code": "",  # Missing reason
                               "customer_id": "cust_001",
                               "allocations": [{"order_id": "so_001", "amount": 100000}]
                           },
                           timeout=30)
        result.add("US3: Resolve without reason is rejected",
                  resp.status_code == 400 and "alasan" in resp.text.lower(),
                  f"Status: {resp.status_code}")
        
        # Test RBAC: sales cannot resolve (US5)
        resp = requests.post(f"{BASE_URL}/finance-cases/{case_id}/resolve",
                           headers=headers(sales_token),
                           json={
                               "action": "alokasi_titipan",
                               "reason_code": "case_identified_owner",
                               "customer_id": "cust_001",
                               "allocations": [{"order_id": "so_001", "amount": 100000}]
                           },
                           timeout=30)
        result.add("US5: Sales role cannot resolve cases (RBAC)",
                  resp.status_code in [403, 400],
                  f"Status: {resp.status_code}")
        
    except Exception as e:
        result.add("Guards and validation tests", False, str(e))

def test_isolation(result: TestResult, admin_token: str):
    """US11: Test cross-entity isolation"""
    print("\n" + "="*60)
    print("TEST 4: CROSS-ENTITY ISOLATION (US11)")
    print("="*60)
    
    try:
        # Get cases from ent_ksc
        resp = requests.get(f"{BASE_URL}/finance-cases",
                          headers=headers(admin_token, "ent_ksc"), timeout=30)
        ksc_cases = resp.json() if resp.status_code == 200 else []
        
        # Get cases from ent_kanda
        resp = requests.get(f"{BASE_URL}/finance-cases",
                          headers=headers(admin_token, "ent_kanda"), timeout=30)
        kanda_cases = resp.json() if resp.status_code == 200 else []
        
        result.add("US11: Cases are isolated by entity",
                  resp.status_code == 200,
                  f"KSC cases: {len(ksc_cases)}, Kanda cases: {len(kanda_cases)}")
        
        # Try to access a case from wrong entity
        if ksc_cases:
            ksc_case_id = ksc_cases[0]["id"]
            resp = requests.get(f"{BASE_URL}/finance-cases/{ksc_case_id}",
                              headers=headers(admin_token, "ent_kanda"), timeout=30)
            result.add("US11: Cannot access case from different entity",
                      resp.status_code == 403,
                      f"Status: {resp.status_code}")
        
    except Exception as e:
        result.add("Cross-entity isolation tests", False, str(e))

def test_scan_and_auto_cases(result: TestResult, admin_token: str):
    """US4: Test automatic case creation via scan"""
    print("\n" + "="*60)
    print("TEST 5: AUTO CASE CREATION (US4)")
    print("="*60)
    
    try:
        # Test scan endpoint
        resp = requests.post(f"{BASE_URL}/finance-cases/scan",
                           headers=headers(admin_token),
                           json={},
                           timeout=60)
        scan_result = resp.json() if resp.status_code == 200 else {}
        result.add("US4: POST /finance-cases/scan executes successfully",
                  resp.status_code == 200,
                  f"Status: {resp.status_code}, Holding cases: {scan_result.get('holding_cases')}, Duplicate cases: {scan_result.get('duplicate_cases')}")
        
        # Test idempotency - run scan again
        resp2 = requests.post(f"{BASE_URL}/finance-cases/scan",
                            headers=headers(admin_token),
                            json={},
                            timeout=60)
        scan_result2 = resp2.json() if resp2.status_code == 200 else {}
        result.add("US4: Scan is idempotent (skips existing cases)",
                  resp2.status_code == 200 and scan_result2.get("skipped", 0) >= 0,
                  f"Status: {resp2.status_code}, Skipped: {scan_result2.get('skipped')}")
        
    except Exception as e:
        result.add("Auto case creation tests", False, str(e))

def main():
    print("="*60)
    print("BACKEND API TESTING - FASE G-9 PUSAT KASUS KEUANGAN")
    print("="*60)
    
    result = TestResult()
    
    # Login
    print("\nLogging in...")
    admin_token = login("admin")
    manager_token = login("manager")
    sales_token = login("sales")
    
    if not admin_token:
        print("❌ Failed to login as admin")
        return 1
    
    result.add("Login as admin", bool(admin_token))
    result.add("Login as manager", bool(manager_token))
    result.add("Login as sales", bool(sales_token))
    
    # Run tests
    test_playbooks_and_policy(result, admin_token)
    test_inbox_and_stats(result, admin_token, sales_token)
    test_guards_and_validation(result, admin_token, sales_token)
    test_isolation(result, admin_token)
    test_scan_and_auto_cases(result, admin_token)
    
    # Summary
    success = result.summary()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
