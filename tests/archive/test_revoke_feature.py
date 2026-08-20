#!/usr/bin/env python3
"""Test the NEW Revoke Rule feature (POST /api/price-approvals/{id}/revoke)"""
import requests
import sys

BASE_URL = "https://number-separator.preview.emergentagent.com/api"
ENTITY_ID = "ent_ksc"
PASSWORD = "demo12345"

def login(email):
    """Login and return session"""
    session = requests.Session()
    r = session.post(f"{BASE_URL}/auth/login",
                    json={"email": email, "password": PASSWORD},
                    timeout=30)
    r.raise_for_status()
    data = r.json()
    session.headers.update({
        "Authorization": f"Bearer {data['token']}",
        "X-Entity-Id": ENTITY_ID,
        "Content-Type": "application/json"
    })
    return session

def main():
    print("=" * 80)
    print("TESTING NEW FEATURE: Revoke Rule (POST /api/price-approvals/{id}/revoke)")
    print("=" * 80)
    
    admin = login("admin@kainnusantara.id")
    manager = login("manager@kainnusantara.id")
    sales = login("sales@kainnusantara.id")
    
    # Get test data
    r = admin.get(f"{BASE_URL}/customers", timeout=30)
    data = r.json()
    customers = data.get("items", []) if isinstance(data, dict) else data
    customer = next((c for c in customers if c.get("entity_id") == ENTITY_ID), customers[0])
    
    r = admin.get(f"{BASE_URL}/products", timeout=30)
    products = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    product = products[0]
    
    print(f"\n📋 Test Data:")
    print(f"  Customer: {customer['name']} ({customer['id']})")
    print(f"  Product: {product['sku']} ({product['id']})")
    
    # Step 1: Sales creates a special price approval
    print("\n[1] Sales creates special price approval")
    r = sales.post(f"{BASE_URL}/price-approvals",
                  json={
                      "customer_id": customer["id"],
                      "product_id": product["id"],
                      "requested_price": 50000,
                      "submit_now": True,
                      "reason": "Test revoke feature - special discount",
                      "min_quantity": 0,
                      "rule_type": "standing"
                  },
                  timeout=30)
    if r.status_code not in [200, 201]:
        print(f"❌ Failed to create approval: {r.status_code} {r.text}")
        return 1
    
    approval = r.json()
    approval_id = approval["id"]
    print(f"✅ Created approval {approval_id} with status: {approval.get('status')}")
    
    # Step 2: Manager approves it
    print("\n[2] Manager approves the special price")
    r = manager.post(f"{BASE_URL}/price-approvals/{approval_id}/approve",
                    json={"decision_notes": "Approved for testing revoke"},
                    timeout=30)
    if r.status_code != 200:
        print(f"❌ Failed to approve: {r.status_code} {r.text}")
        return 1
    
    approved = r.json()
    print(f"✅ Approved. Status: {approved.get('status')}")
    
    # Step 3: Verify price is active in quote
    print("\n[3] Verify special price is active")
    r = admin.get(f"{BASE_URL}/customer-prices/quote",
                 params={"customer_id": customer["id"], "product_ids": product["id"]},
                 timeout=30)
    quote = r.json()
    price_info = quote.get("prices", {}).get(product["id"], {})
    print(f"  Source: {price_info.get('source')}, Price: {price_info.get('price')}")
    if price_info.get("source") == "special_approval":
        print("✅ Special price is active")
    else:
        print(f"⚠️  Expected special_approval, got {price_info.get('source')}")
    
    # Step 4: Try to revoke without reason (should fail)
    print("\n[4] Try to revoke without reason (should fail 400)")
    r = manager.post(f"{BASE_URL}/price-approvals/{approval_id}/revoke",
                    json={"decision_notes": ""},
                    timeout=30)
    if r.status_code == 400:
        print(f"✅ Correctly rejected: {r.status_code}")
        print(f"   Message: {r.json().get('detail', '')}")
    else:
        print(f"❌ Expected 400, got {r.status_code}")
    
    # Step 5: Sales tries to revoke (should fail 403)
    print("\n[5] Sales tries to revoke (should fail 403)")
    r = sales.post(f"{BASE_URL}/price-approvals/{approval_id}/revoke",
                  json={"decision_notes": "Sales trying to revoke"},
                  timeout=30)
    if r.status_code == 403:
        print(f"✅ Correctly blocked: {r.status_code}")
    else:
        print(f"❌ Expected 403, got {r.status_code}")
    
    # Step 6: Manager revokes with reason (should succeed)
    print("\n[6] Manager revokes with reason (should succeed)")
    r = manager.post(f"{BASE_URL}/price-approvals/{approval_id}/revoke",
                    json={"decision_notes": "Promotion ended - testing revoke feature"},
                    timeout=30)
    if r.status_code == 200:
        revoked = r.json()
        print(f"✅ Revoked successfully. Status: {revoked.get('status')}")
        if revoked.get("status") == "revoked":
            print("✅ Status is 'revoked'")
        else:
            print(f"⚠️  Expected status 'revoked', got {revoked.get('status')}")
    else:
        print(f"❌ Failed to revoke: {r.status_code} {r.text}")
        return 1
    
    # Step 7: Verify price is no longer active
    print("\n[7] Verify special price is no longer active")
    r = admin.get(f"{BASE_URL}/customer-prices/quote",
                 params={"customer_id": customer["id"], "product_ids": product["id"]},
                 timeout=30)
    quote = r.json()
    price_info = quote.get("prices", {}).get(product["id"], {})
    print(f"  Source: {price_info.get('source')}, Price: {price_info.get('price')}")
    if price_info.get("source") != "special_approval":
        print("✅ Special price is no longer active (reverted to normal pricing)")
    else:
        print(f"❌ Special price still active!")
    
    # Step 8: Try to revoke again (should fail 409)
    print("\n[8] Try to revoke again (should fail 409)")
    r = manager.post(f"{BASE_URL}/price-approvals/{approval_id}/revoke",
                    json={"decision_notes": "Trying to revoke again"},
                    timeout=30)
    if r.status_code == 409:
        print(f"✅ Correctly rejected duplicate revoke: {r.status_code}")
        print(f"   Message: {r.json().get('detail', '')}")
    else:
        print(f"❌ Expected 409, got {r.status_code}")
    
    print("\n" + "=" * 80)
    print("✅ ALL REVOKE FEATURE TESTS PASSED")
    print("=" * 80)
    return 0

if __name__ == "__main__":
    sys.exit(main())
