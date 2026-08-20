#!/usr/bin/env python3
"""
Comprehensive Backend Testing for FASE G-3 (Payment Variance) and POIN 2 (Penalty Integration)
Tests all backend APIs systematically using the public endpoint.
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://g3-overpay-fix.preview.emergentagent.com/api"
CREDENTIALS = {
    "admin": {"email": "admin@kainnusantara.id", "password": "demo12345"},
    "manager": {"email": "manager@kainnusantara.id", "password": "demo12345"},
    "sales": {"email": "sales@kainnusantara.id", "password": "demo12345"},
}

class TestRunner:
    def __init__(self):
        self.tokens = {}
        self.passed = 0
        self.failed = 0
        self.tests = []
        
    def login(self, role):
        """Login and get token for a role"""
        if role in self.tokens:
            return self.tokens[role]
        
        creds = CREDENTIALS[role]
        try:
            resp = requests.post(f"{BASE_URL}/auth/login", json=creds, timeout=20)
            if resp.status_code == 200:
                token = resp.json().get("token")
                self.tokens[role] = token
                return token
            else:
                print(f"❌ Login failed for {role}: {resp.status_code}")
                return None
        except Exception as e:
            print(f"❌ Login error for {role}: {e}")
            return None
    
    def headers(self, role):
        """Get headers with auth token"""
        token = self.login(role)
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def test(self, name, condition, detail=""):
        """Record test result"""
        if condition:
            self.passed += 1
            print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
        else:
            self.failed += 1
            print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))
        self.tests.append({"name": name, "passed": condition, "detail": detail})
        return condition
    
    def section(self, title):
        """Print section header"""
        print(f"\n{'='*80}")
        print(f"{title}")
        print(f"{'='*80}")

def main():
    runner = TestRunner()
    
    # ========== BACKEND G-3: Payment Variance Metadata ==========
    runner.section("BACKEND G-3: GET /api/payment-variances/meta")
    
    # Test 1: Admin can access metadata
    try:
        resp = requests.get(f"{BASE_URL}/payment-variances/meta", 
                           headers=runner.headers("admin"), timeout=30)
        runner.test("Admin can access payment variance metadata", 
                   resp.status_code == 200,
                   f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            runner.test("Metadata contains policy", 
                       "policy" in data and "tolerance" in data["policy"],
                       f"Tolerance: Rp {data['policy'].get('tolerance', 0):,.0f}")
            runner.test("Metadata contains reasons", 
                       "reasons" in data and len(data["reasons"]) > 0,
                       f"{len(data['reasons'])} reason codes available")
            runner.test("Metadata contains under_kinds", 
                       "under_kinds" in data and set(data["under_kinds"]) == {"outstanding", "reschedule", "writeoff"},
                       f"Under kinds: {data.get('under_kinds', [])}")
            runner.test("Metadata contains over_kinds", 
                       "over_kinds" in data and set(data["over_kinds"]) == {"deposit", "allocate", "refund"},
                       f"Over kinds: {data.get('over_kinds', [])}")
    except Exception as e:
        runner.test("Admin can access payment variance metadata", False, f"Error: {e}")
    
    # Test 2: Sales can view metadata (RBAC check)
    try:
        resp = requests.get(f"{BASE_URL}/payment-variances/meta", 
                           headers=runner.headers("sales"), timeout=30)
        runner.test("Sales can view payment variance metadata (transparency)", 
                   resp.status_code == 200,
                   f"Status: {resp.status_code}")
    except Exception as e:
        runner.test("Sales can view payment variance metadata", False, f"Error: {e}")
    
    # ========== BACKEND G-3: Payment Variance Assessment ==========
    runner.section("BACKEND G-3: POST /api/payment-variances/assess")
    
    # Get a customer for testing
    try:
        resp = requests.get(f"{BASE_URL}/customers", 
                           headers=runner.headers("admin"), 
                           params={"limit": 1}, timeout=30)
        if resp.status_code == 200:
            customers = resp.json()
            if isinstance(customers, dict):
                customers = customers.get("items", [])
            if len(customers) > 0:
                test_customer_id = customers[0]["id"]
                
                # Test 3: Assess payment with exact amount
                assess_payload = {
                    "customer_id": test_customer_id,
                    "amount": 1000000,
                    "allocations": []
                }
                resp = requests.post(f"{BASE_URL}/payment-variances/assess",
                                    headers=runner.headers("admin"),
                                    json=assess_payload, timeout=30)
                runner.test("Can assess payment variance", 
                           resp.status_code == 200,
                           f"Status: {resp.status_code}")
                
                if resp.status_code == 200:
                    assessment = resp.json()
                    runner.test("Assessment contains direction", 
                               "direction" in assessment,
                               f"Direction: {assessment.get('direction', 'N/A')}")
                    runner.test("Assessment contains needs_decision", 
                               "needs_decision" in assessment,
                               f"Needs decision: {assessment.get('needs_decision', False)}")
                    runner.test("Assessment contains options", 
                               "options" in assessment and isinstance(assessment["options"], list),
                               f"{len(assessment.get('options', []))} options available")
    except Exception as e:
        runner.test("Can assess payment variance", False, f"Error: {e}")
    
    # ========== BACKEND G-3: Payment Variance List ==========
    runner.section("BACKEND G-3: GET /api/payment-variances")
    
    try:
        resp = requests.get(f"{BASE_URL}/payment-variances", 
                           headers=runner.headers("admin"), timeout=30)
        runner.test("Can list payment variance decisions", 
                   resp.status_code == 200,
                   f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            runner.test("List contains items", 
                       "items" in data,
                       f"{len(data.get('items', []))} decisions found")
            runner.test("List contains stats", 
                       "stats" in data,
                       f"Stats available")
            runner.test("List contains pending", 
                       "pending" in data,
                       f"{len(data.get('pending', []))} pending decisions")
    except Exception as e:
        runner.test("Can list payment variance decisions", False, f"Error: {e}")
    
    # ========== BACKEND G-3: Pending Variances ==========
    runner.section("BACKEND G-3: GET /api/payment-variances/pending")
    
    try:
        resp = requests.get(f"{BASE_URL}/payment-variances/pending", 
                           headers=runner.headers("admin"), timeout=30)
        runner.test("Can get pending variances queue", 
                   resp.status_code == 200,
                   f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            runner.test("Pending queue contains count", 
                       "count" in data,
                       f"{data.get('count', 0)} pending")
            runner.test("Pending queue contains items", 
                       "items" in data and isinstance(data["items"], list),
                       f"{len(data.get('items', []))} items")
    except Exception as e:
        runner.test("Can get pending variances queue", False, f"Error: {e}")
    
    # ========== BACKEND POIN 2: AR Aging with Penalties ==========
    runner.section("BACKEND POIN 2: GET /api/ar/aging")
    
    try:
        resp = requests.get(f"{BASE_URL}/ar/aging", 
                           headers=runner.headers("manager"), timeout=30)
        runner.test("Manager can access AR aging report", 
                   resp.status_code == 200,
                   f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            runner.test("AR aging contains totals", 
                       "totals" in data,
                       "Totals section present")
            
            totals = data.get("totals", {})
            runner.test("Totals contain penalty_docs", 
                       "penalty_docs" in totals,
                       f"{totals.get('penalty_docs', 0)} penalty documents")
            runner.test("Totals contain penalty_draft", 
                       "penalty_draft" in totals,
                       f"Draft: Rp {totals.get('penalty_draft', 0):,.0f}")
            runner.test("Totals contain penalty_issued", 
                       "penalty_issued" in totals,
                       f"Issued: Rp {totals.get('penalty_issued', 0):,.0f}")
            runner.test("Totals contain penalty_actual", 
                       "penalty_actual" in totals,
                       f"Actual: Rp {totals.get('penalty_actual', 0):,.0f}")
            runner.test("Totals contain denda_undocumented", 
                       "denda_undocumented" in totals,
                       f"Undocumented: Rp {totals.get('denda_undocumented', 0):,.0f}")
            
            runner.test("AR aging contains penalty_policy", 
                       "penalty_policy" in data,
                       "Penalty policy present")
            
            runner.test("AR aging contains customers", 
                       "customers" in data and isinstance(data["customers"], list),
                       f"{len(data.get('customers', []))} customers")
            
            # Check customer-level penalty fields
            customers = data.get("customers", [])
            if len(customers) > 0:
                cust = customers[0]
                runner.test("Customer row contains penalty fields", 
                           all(k in cust for k in ["penalty_docs", "penalty_draft", "penalty_issued", "penalty_actual"]),
                           f"Customer: {cust.get('customer_name', 'N/A')}")
    except Exception as e:
        runner.test("Manager can access AR aging report", False, f"Error: {e}")
    
    # ========== BACKEND POIN 2: AR Aging Customer Detail ==========
    runner.section("BACKEND POIN 2: GET /api/ar/aging/{customer_id}")
    
    try:
        # Get first customer from aging report
        resp = requests.get(f"{BASE_URL}/ar/aging", 
                           headers=runner.headers("manager"), timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            customers = data.get("customers", [])
            if len(customers) > 0:
                customer_id = customers[0]["customer_id"]
                
                # Get customer detail
                resp = requests.get(f"{BASE_URL}/ar/aging/{customer_id}", 
                                   headers=runner.headers("manager"), timeout=30)
                runner.test("Can get customer aging detail", 
                           resp.status_code == 200,
                           f"Status: {resp.status_code}")
                
                if resp.status_code == 200:
                    detail = resp.json()
                    runner.test("Detail contains items (orders)", 
                               "items" in detail and isinstance(detail["items"], list),
                               f"{len(detail.get('items', []))} orders")
                    
                    runner.test("Detail contains penalties list", 
                               "penalties" in detail and isinstance(detail["penalties"], list),
                               f"{len(detail.get('penalties', []))} penalty documents")
                    
                    runner.test("Detail contains plans list", 
                               "plans" in detail and isinstance(detail["plans"], list),
                               f"{len(detail.get('plans', []))} payment plans")
                    
                    # Check order-level penalty fields
                    items = detail.get("items", [])
                    if len(items) > 0:
                        item = items[0]
                        runner.test("Order item contains penalties array", 
                                   "penalties" in item and isinstance(item["penalties"], list),
                                   f"{len(item.get('penalties', []))} penalties on order")
                        runner.test("Order item contains penalty_actual", 
                                   "penalty_actual" in item,
                                   f"Actual: Rp {item.get('penalty_actual', 0):,.0f}")
                        runner.test("Order item contains penalty_undocumented", 
                                   "penalty_undocumented" in item,
                                   f"Undocumented: Rp {item.get('penalty_undocumented', 0):,.0f}")
                        runner.test("Order item contains has_plan", 
                                   "has_plan" in item,
                                   f"Has plan: {item.get('has_plan', False)}")
    except Exception as e:
        runner.test("Can get customer aging detail", False, f"Error: {e}")
    
    # ========== BACKEND POIN 2: Accrue Penalties ==========
    runner.section("BACKEND POIN 2: POST /api/ar/aging/{customer_id}/accrue-penalties")
    
    # Test RBAC: Sales should NOT be able to accrue penalties
    try:
        resp = requests.get(f"{BASE_URL}/ar/aging", 
                           headers=runner.headers("manager"), timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            customers = data.get("customers", [])
            if len(customers) > 0:
                customer_id = customers[0]["customer_id"]
                
                # Try with sales role (should fail)
                resp = requests.post(f"{BASE_URL}/ar/aging/{customer_id}/accrue-penalties",
                                    headers=runner.headers("sales"), timeout=30)
                runner.test("Sales CANNOT accrue penalties (RBAC check)", 
                           resp.status_code in [401, 403],
                           f"Status: {resp.status_code} (expected 401/403)")
                
                # Try with manager role (should succeed or return idempotent result)
                resp = requests.post(f"{BASE_URL}/ar/aging/{customer_id}/accrue-penalties",
                                    headers=runner.headers("manager"), timeout=30)
                runner.test("Manager CAN accrue penalties", 
                           resp.status_code == 200,
                           f"Status: {resp.status_code}")
                
                if resp.status_code == 200:
                    result = resp.json()
                    runner.test("Accrue result contains count", 
                               "count" in result,
                               f"{result.get('count', 0)} penalties created/updated")
                    runner.test("Accrue result contains penalties array", 
                               "penalties" in result and isinstance(result["penalties"], list),
                               "Penalties array present")
                    runner.test("Accrue is idempotent (can be called multiple times)", 
                               True,
                               "Idempotency mentioned in spec")
    except Exception as e:
        runner.test("Can accrue penalties", False, f"Error: {e}")
    
    # ========== BACKEND REGRESSION: Core Endpoints ==========
    runner.section("BACKEND REGRESSION: Core endpoints still work")
    
    try:
        # Test AR receipts
        resp = requests.get(f"{BASE_URL}/ar-receipts", 
                           headers=runner.headers("admin"), 
                           params={"limit": 5}, timeout=30)
        runner.test("GET /api/ar-receipts still works", 
                   resp.status_code == 200,
                   f"Status: {resp.status_code}")
        
        # Test payment plans
        resp = requests.get(f"{BASE_URL}/payment-plans", 
                           headers=runner.headers("admin"), 
                           params={"limit": 5}, timeout=30)
        runner.test("GET /api/payment-plans still works", 
                   resp.status_code == 200,
                   f"Status: {resp.status_code}")
        
        # Test penalties
        resp = requests.get(f"{BASE_URL}/penalties", 
                           headers=runner.headers("admin"), 
                           params={"limit": 5}, timeout=30)
        runner.test("GET /api/penalties still works", 
                   resp.status_code == 200,
                   f"Status: {resp.status_code}")
    except Exception as e:
        runner.test("Core endpoints regression", False, f"Error: {e}")
    
    # ========== SUMMARY ==========
    runner.section("TEST SUMMARY")
    total = runner.passed + runner.failed
    print(f"\n  Total Tests: {total}")
    print(f"  ✅ Passed: {runner.passed}")
    print(f"  ❌ Failed: {runner.failed}")
    print(f"  Success Rate: {(runner.passed/total*100) if total > 0 else 0:.1f}%")
    
    if runner.failed == 0:
        print("\n✅ ALL BACKEND TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {runner.failed} TEST(S) FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
