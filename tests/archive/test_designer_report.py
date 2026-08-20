"""
Quick test to check designer KPI report endpoint with note parameter
Tests FEATURE 1: Ringkasan Rapor (Designer Report with Evaluation Note)
"""
import requests
import sys

BASE_URL = "https://po-grid-layout.preview.emergentagent.com"
ENTITY_ID = "ent_ksc"

def login(email: str, password: str) -> str:
    """Login and return token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password}
    )
    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code}")
        sys.exit(1)
    data = response.json()
    return data["token"]

def get_headers(token: str):
    """Get request headers"""
    return {
        "Authorization": f"Bearer {token}",
        "X-Entity-Id": ENTITY_ID,
        "Content-Type": "application/json"
    }

def main():
    print("🔍 Testing Designer Report with Note Parameter...")
    
    # Login as manager
    print("\n1. Logging in as manager...")
    manager_token = login("manager@kainnusantara.id", "demo12345")
    print("✅ Manager login successful")
    
    # Get designer KPI list to find a designer name
    print("\n2. Getting designer KPI list...")
    response = requests.get(
        f"{BASE_URL}/api/rnd/reports/designer-kpi",
        headers=get_headers(manager_token),
        params={"entity_id": ENTITY_ID, "period": "all"}
    )
    if response.status_code != 200:
        print(f"❌ Failed to get KPI list: {response.status_code}")
        sys.exit(1)
    
    kpi_data = response.json()
    items = kpi_data.get("items", [])
    if not items:
        print("⚠️  No designers found in KPI data")
        sys.exit(0)
    
    designer_name = items[0].get("designer", "")
    print(f"✅ Found designer: {designer_name}")
    
    # Test 1: Report with note
    print(f"\n3. Testing report download with note for {designer_name}...")
    note = "Evaluasi triwulan oke"
    response = requests.get(
        f"{BASE_URL}/api/rnd/reports/designer-kpi/report",
        headers=get_headers(manager_token),
        params={
            "designer": designer_name,
            "period": "all",
            "note": note,
            "entity_id": ENTITY_ID
        }
    )
    
    if response.status_code != 200:
        print(f"❌ Report with note failed: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        sys.exit(1)
    
    # Check content type
    content_type = response.headers.get("content-type", "")
    if "application/pdf" not in content_type:
        print(f"❌ Wrong content type: {content_type}")
        sys.exit(1)
    
    # Check PDF signature
    if not response.content.startswith(b"%PDF"):
        print(f"❌ Response doesn't start with %PDF")
        sys.exit(1)
    
    print(f"✅ Report with note: 200, application/pdf, {len(response.content)} bytes")
    
    # Test 2: Report with empty note
    print(f"\n4. Testing report download with empty note...")
    response = requests.get(
        f"{BASE_URL}/api/rnd/reports/designer-kpi/report",
        headers=get_headers(manager_token),
        params={
            "designer": designer_name,
            "period": "all",
            "note": "",
            "entity_id": ENTITY_ID
        }
    )
    
    if response.status_code != 200:
        print(f"❌ Report with empty note failed: {response.status_code}")
        sys.exit(1)
    
    if not response.content.startswith(b"%PDF"):
        print(f"❌ Response doesn't start with %PDF")
        sys.exit(1)
    
    print(f"✅ Report with empty note: 200, application/pdf, {len(response.content)} bytes")
    
    # Test 3: Sales token should get 403
    print(f"\n5. Testing sales token (should get 403)...")
    sales_token = login("sales@kainnusantara.id", "demo12345")
    response = requests.get(
        f"{BASE_URL}/api/rnd/reports/designer-kpi/report",
        headers=get_headers(sales_token),
        params={
            "designer": designer_name,
            "period": "all",
            "note": "test"
        }
    )
    
    if response.status_code != 403:
        print(f"❌ Expected 403 for sales, got {response.status_code}")
        sys.exit(1)
    
    print(f"✅ Sales token correctly rejected: 403")
    
    # Test 4: Note over 1200 chars should get 422
    print(f"\n6. Testing note over 1200 chars (should get 422)...")
    long_note = "x" * 1201
    response = requests.get(
        f"{BASE_URL}/api/rnd/reports/designer-kpi/report",
        headers=get_headers(manager_token),
        params={
            "designer": designer_name,
            "period": "all",
            "note": long_note
        }
    )
    
    if response.status_code != 422:
        print(f"❌ Expected 422 for long note, got {response.status_code}")
        sys.exit(1)
    
    print(f"✅ Long note correctly rejected: 422")
    
    print("\n" + "="*60)
    print("✅ ALL BACKEND TESTS PASSED")
    print("="*60)

if __name__ == "__main__":
    main()
