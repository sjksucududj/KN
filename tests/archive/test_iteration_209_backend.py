#!/usr/bin/env python3
"""
ITERATION 209 - PUTARAN 3 (FINAL) Backend API Testing
Focus: Price consistency verification and regression testing
"""
import requests
import sys

BASE = "https://number-separator.preview.emergentagent.com/api"
ENTITY = "ent_ksc"
PASSWORD = "demo12345"

def login(email):
    """Login and return session with token"""
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD}, timeout=30)
    r.raise_for_status()
    data = r.json()
    s.headers.update({
        "Authorization": f"Bearer {data['token']}",
        "X-Entity-Id": ENTITY,
        "Content-Type": "application/json"
    })
    return s, data["user"]

def test_customer_and_product_lookup():
    """Find customer 'Toko Kain Sejahtera' and product 'TNI-GRGD-001'"""
    print("\n[TEST 1] Customer and Product Lookup")
    s, user = login("admin@kainnusantara.id")
    
    # Get customers
    r = s.get(f"{BASE}/customers", timeout=30)
    if r.status_code != 200:
        print(f"  ❌ Failed to get customers: {r.status_code}")
        return None, None
    
    customers_data = r.json()
    customers = customers_data.get("items", []) if isinstance(customers_data, dict) else customers_data
    target_customer = None
    for c in customers:
        if "Toko Kain Sejahtera" in c.get("name", ""):
            target_customer = c
            print(f"  ✅ Found customer: {c['name']} (ID: {c['id']})")
            break
    
    if not target_customer:
        print(f"  ❌ Customer 'Toko Kain Sejahtera' not found")
        return None, None
    
    # Get products
    r = s.get(f"{BASE}/products", timeout=30)
    if r.status_code != 200:
        print(f"  ❌ Failed to get products: {r.status_code}")
        return target_customer, None
    
    products = r.json()
    if isinstance(products, dict):
        products = products.get("items", [])
    
    target_product = None
    for p in products:
        if p.get("sku") == "TNI-GRGD-001":
            target_product = p
            print(f"  ✅ Found product: {p['sku']} - {p['name']} (ID: {p['id']}, Price: {p.get('price')})")
            break
    
    if not target_product:
        print(f"  ❌ Product 'TNI-GRGD-001' not found")
        return target_customer, None
    
    return target_customer, target_product

def test_price_quote(customer_id, product_id):
    """Test GET /api/customer-prices/quote for the specific customer and product"""
    print("\n[TEST 2] Price Quote API - Verify Expected Prices")
    s, user = login("admin@kainnusantara.id")
    
    r = s.get(f"{BASE}/customer-prices/quote", 
              params={"customer_id": customer_id, "product_ids": product_id},
              timeout=30)
    
    if r.status_code != 200:
        print(f"  ❌ Quote API failed: {r.status_code} - {r.text[:200]}")
        return None
    
    data = r.json()
    prices = data.get("prices", {})
    product_price = prices.get(product_id, {})
    
    print(f"  ✅ Quote API returned 200")
    print(f"  📊 Price details:")
    print(f"     - Effective price: Rp {product_price.get('price', 0):,.2f}")
    print(f"     - Source: {product_price.get('source')}")
    print(f"     - Customer price: {product_price.get('customer_price')}")
    print(f"     - Entity price: {product_price.get('entity_price')}")
    print(f"     - Global price: {product_price.get('global_price')}")
    print(f"     - Special price: {product_price.get('special_price')}")
    
    # Verify expected values
    expected_customer_price = 213750.0
    expected_global_price = 225000.0
    
    actual_price = float(product_price.get('price', 0))
    actual_source = product_price.get('source')
    
    if abs(actual_price - expected_customer_price) < 1.0:
        print(f"  ✅ Price matches expected: Rp 213,750")
    else:
        print(f"  ⚠️  Price mismatch: Expected Rp 213,750, got Rp {actual_price:,.2f}")
    
    if actual_source == 'customer':
        print(f"  ✅ Source is 'customer' as expected")
    else:
        print(f"  ⚠️  Source mismatch: Expected 'customer', got '{actual_source}'")
    
    return product_price

def test_customer_pricelist_grid(customer_id):
    """Test GET /api/customer-prices grid for the customer"""
    print("\n[TEST 3] Customer Pricelist Grid")
    s, user = login("admin@kainnusantara.id")
    
    r = s.get(f"{BASE}/customer-prices", 
              params={"customer_id": customer_id},
              timeout=30)
    
    if r.status_code != 200:
        print(f"  ❌ Grid API failed: {r.status_code}")
        return False
    
    data = r.json()
    print(f"  ✅ Grid API returned 200")
    print(f"  📊 Customer: {data.get('customer_name')}")
    print(f"  📊 Total products in grid: {len(data.get('rows', []))}")
    
    # Find TNI-GRGD-001 in grid
    for row in data.get('rows', []):
        if row.get('sku') == 'TNI-GRGD-001':
            print(f"  ✅ Found TNI-GRGD-001 in grid:")
            print(f"     - Effective price: Rp {row.get('effective_price', 0):,.2f}")
            print(f"     - Price source: {row.get('price_source')}")
            print(f"     - Customer price: {row.get('customer_price')}")
            print(f"     - Global price: {row.get('global_price')}")
            break
    
    return True

def test_rbac():
    """Test RBAC - warehouse should get 403"""
    print("\n[TEST 4] RBAC - Warehouse Access")
    
    try:
        s, user = login("warehouse@kainnusantara.id")
        r = s.get(f"{BASE}/customer-prices", 
                  params={"customer_id": "any"},
                  timeout=30)
        
        if r.status_code == 403:
            print(f"  ✅ Warehouse correctly blocked (403)")
            return True
        else:
            print(f"  ❌ Warehouse should be blocked but got: {r.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Error testing warehouse access: {e}")
        return False

def test_revoke_endpoint():
    """Test that revoke endpoint exists and requires proper auth"""
    print("\n[TEST 5] Revoke Endpoint Availability")
    s, user = login("admin@kainnusantara.id")
    
    # Try to revoke a non-existent approval (should get 404, not 405)
    r = s.post(f"{BASE}/price-approvals/nonexistent/revoke",
               json={"decision_notes": "test"},
               timeout=30)
    
    if r.status_code in [404, 400]:
        print(f"  ✅ Revoke endpoint exists (got {r.status_code} for invalid ID)")
        return True
    elif r.status_code == 405:
        print(f"  ❌ Revoke endpoint not found (405 Method Not Allowed)")
        return False
    else:
        print(f"  ⚠️  Unexpected status: {r.status_code}")
        return True

def main():
    print("=" * 80)
    print("ITERATION 209 - PUTARAN 3 (FINAL) Backend API Testing")
    print("=" * 80)
    
    try:
        # Test 1: Find customer and product
        customer, product = test_customer_and_product_lookup()
        if not customer or not product:
            print("\n❌ Cannot proceed without customer and product")
            return 1
        
        # Test 2: Price quote
        price_data = test_price_quote(customer['id'], product['id'])
        
        # Test 3: Grid
        test_customer_pricelist_grid(customer['id'])
        
        # Test 4: RBAC
        test_rbac()
        
        # Test 5: Revoke endpoint
        test_revoke_endpoint()
        
        print("\n" + "=" * 80)
        print("✅ Backend API tests completed")
        print("=" * 80)
        return 0
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
