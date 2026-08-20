"""R6.2 — GL Balance & JE Verification
Verify that trial balance is balanced and JE entries are correct
"""
import requests
import sys

BASE_URL = "https://code-continue-37.preview.emergentagent.com/api"
ADMIN_CREDS = {"email": "admin@kainnusantara.id", "password": "demo12345"}

def login():
    r = requests.post(f"{BASE_URL}/auth/login", json=ADMIN_CREDS, timeout=30)
    if r.status_code == 200:
        return r.json().get("token")
    return None

def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def main():
    print("\n=== R6.2 GL BALANCE & JE VERIFICATION ===\n")
    
    token = login()
    if not token:
        print("❌ Login failed")
        sys.exit(1)
    
    passed = 0
    failed = 0
    
    # Check trial balance endpoint
    try:
        r = requests.get(f"{BASE_URL}/gl/trial-balance", 
                        headers=headers(token), timeout=30)
        
        if r.status_code == 200:
            print("✅ GET /api/gl/trial-balance accessible")
            passed += 1
            
            data = r.json()
            
            # Check if trial balance is balanced
            if "summary" in data:
                summary = data["summary"]
                total_debit = summary.get("total_debit", 0)
                total_credit = summary.get("total_credit", 0)
                diff = abs(total_debit - total_credit)
                
                if diff < 0.01:
                    print(f"✅ Trial balance is balanced (debit={total_debit}, credit={total_credit})")
                    passed += 1
                else:
                    print(f"❌ Trial balance NOT balanced (debit={total_debit}, credit={total_credit}, diff={diff})")
                    failed += 1
            else:
                print("⚠️  Trial balance response doesn't have 'summary' field")
        else:
            print(f"❌ GET /api/gl/trial-balance failed: {r.status_code}")
            failed += 1
    except Exception as e:
        print(f"❌ Trial balance check error: {e}")
        failed += 1
    
    # Check journal entries endpoint
    try:
        r = requests.get(f"{BASE_URL}/gl/journal-entries?limit=10", 
                        headers=headers(token), timeout=30)
        
        if r.status_code == 200:
            print("✅ GET /api/gl/journal-entries accessible")
            passed += 1
            
            entries = r.json()
            if isinstance(entries, list):
                # Check if any fixed asset related JEs exist
                fa_entries = [je for je in entries if je.get("source_type", "").startswith("fixed_asset")]
                
                if fa_entries:
                    print(f"✅ Found {len(fa_entries)} fixed asset related JE entries")
                    passed += 1
                    
                    # Verify first FA JE is balanced
                    je = fa_entries[0]
                    lines = je.get("lines", [])
                    total_debit = sum(l.get("debit", 0) for l in lines)
                    total_credit = sum(l.get("credit", 0) for l in lines)
                    diff = abs(total_debit - total_credit)
                    
                    if diff < 0.01:
                        print(f"✅ Sample FA JE is balanced (JE: {je.get('number')})")
                        passed += 1
                    else:
                        print(f"❌ Sample FA JE NOT balanced (debit={total_debit}, credit={total_credit})")
                        failed += 1
                else:
                    print("⚠️  No fixed asset JE entries found (might be expected if no assets created)")
        else:
            print(f"❌ GET /api/gl/journal-entries failed: {r.status_code}")
            failed += 1
    except Exception as e:
        print(f"❌ Journal entries check error: {e}")
        failed += 1
    
    # Check specific FA accounts exist in COA
    try:
        r = requests.get(f"{BASE_URL}/gl/accounts", 
                        headers=headers(token), timeout=30)
        
        if r.status_code == 200:
            print("✅ GET /api/gl/accounts accessible")
            passed += 1
            
            accounts = r.json()
            if isinstance(accounts, list):
                codes = [a.get("code") for a in accounts]
                
                # Check for key FA accounts
                if "1-2900" in codes:
                    print("✅ Account 1-2900 (Accumulated Depreciation) exists")
                    passed += 1
                else:
                    print("❌ Account 1-2900 (Accumulated Depreciation) NOT found")
                    failed += 1
                
                if "6-6000" in codes:
                    print("✅ Account 6-6000 (Depreciation Expense) exists")
                    passed += 1
                else:
                    print("❌ Account 6-6000 (Depreciation Expense) NOT found")
                    failed += 1
                
                if "4-9100" in codes:
                    print("✅ Account 4-9100 (Gain on Disposal) exists")
                    passed += 1
                else:
                    print("⚠️  Account 4-9100 (Gain on Disposal) NOT found")
                
                if "6-9500" in codes:
                    print("✅ Account 6-9500 (Loss on Disposal) exists")
                    passed += 1
                else:
                    print("⚠️  Account 6-9500 (Loss on Disposal) NOT found")
        else:
            print(f"❌ GET /api/gl/accounts failed: {r.status_code}")
            failed += 1
    except Exception as e:
        print(f"❌ GL accounts check error: {e}")
        failed += 1
    
    print(f"\n=== GL VERIFICATION: {passed} PASSED / {failed} FAILED ===\n")
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
