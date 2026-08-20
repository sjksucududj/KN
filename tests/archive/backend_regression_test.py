#!/usr/bin/env python3
"""
Quick Backend Regression Test - GET endpoints only
Tests all critical GET endpoints to ensure no regressions
"""
import requests
import sys

BASE_URL = "http://localhost:8001/api"
CREDENTIALS = {
    "email": "admin@kainnusantara.id",
    "password": "demo12345"
}

def test_backend_regression():
    """Test all critical GET endpoints"""
    print("\n🔍 Starting Backend Regression Tests (GET endpoints only)...\n")
    
    # Login first
    print("1. Testing Login...")
    try:
        login_resp = requests.post(f"{BASE_URL}/auth/login", json=CREDENTIALS, timeout=10)
        if login_resp.status_code != 200:
            print(f"❌ Login failed: {login_resp.status_code}")
            return False
        
        token = login_resp.json().get("token")
        if not token:
            print(f"❌ No token in response: {login_resp.json()}")
            return False
        
        print(f"✅ Login successful, token received")
        headers = {"Authorization": f"Bearer {token}"}
    except Exception as e:
        print(f"❌ Login error: {e}")
        return False
    
    # Test GET endpoints
    endpoints = [
        "/dashboard",
        "/products",
        "/sales-orders",
        "/purchase-orders",
        "/purchase-requisitions",
        "/makloon-orders",
        "/makloon-orders/claims",
        "/supplier-contracts",
        "/supplier-items",
        "/supplier-items/stats",
        "/gl/trial-balance",
        "/inventory/balances"
    ]
    
    passed = 0
    failed = 0
    
    for endpoint in endpoints:
        try:
            url = f"{BASE_URL}{endpoint}"
            print(f"\n2. Testing GET {endpoint}...")
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                print(f"✅ GET {endpoint} - Status 200")
                
                # Special check for trial balance
                if endpoint == "/gl/trial-balance":
                    data = resp.json()
                    if "summary" in data:
                        debits = data["summary"].get("total_debits", 0)
                        credits = data["summary"].get("total_credits", 0)
                        if abs(debits - credits) < 0.01:
                            print(f"✅ Trial balance is balanced: {debits} = {credits}")
                        else:
                            print(f"❌ Trial balance NOT balanced: debits={debits}, credits={credits}")
                            failed += 1
                            continue
                
                passed += 1
            else:
                print(f"❌ GET {endpoint} - Status {resp.status_code}")
                print(f"   Response: {resp.text[:200]}")
                failed += 1
        except Exception as e:
            print(f"❌ GET {endpoint} - Error: {e}")
            failed += 1
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 Backend Regression Test Results:")
    print(f"   ✅ Passed: {passed}/{len(endpoints)}")
    print(f"   ❌ Failed: {failed}/{len(endpoints)}")
    print(f"{'='*60}\n")
    
    return failed == 0

if __name__ == "__main__":
    success = test_backend_regression()
    sys.exit(0 if success else 1)
