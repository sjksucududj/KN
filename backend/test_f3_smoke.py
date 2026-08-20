"""F3 smoke test — Special Order MTO: approve→auto-SKU, manual create-sku, convert-to-SO."""
import os, sys, json, requests

BU = open("/app/frontend/.env").read()
BU = [l for l in BU.splitlines() if l.startswith("REACT_APP_BACKEND_URL")][0].split("=", 1)[1].strip()
API = f"{BU}/api"


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    d = r.json()
    return d["token"], d["user"], d.get("entity_context", {})


def H(tok, entity=None):
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    if entity:
        h["X-Entity-Id"] = entity
    return h


def main():
    tok, user, ctx = login("manager@kainnusantara.id", "demo12345")
    ent = ctx.get("active_entity_id")
    print(f"[OK] login manager · entity={ent}")

    # pick a customer in active entity
    custs = requests.get(f"{API}/customers", headers=H(tok)).json()
    items = custs.get("items", custs) if isinstance(custs, dict) else custs
    cust = next((c for c in items if c.get("entity_id") == ent), items[0])
    print(f"[OK] customer={cust['id']} ({cust.get('name')}) entity={cust.get('entity_id')}")

    # 1) create special order > threshold (15jt) submit_for_approval
    payload = {
        "customer_id": cust["id"],
        "entity_id": cust.get("entity_id", ent),
        "custom_item": {
            "description": "Kain Custom Jacquard Emas (smoke test)",
            "specifications": {"color": "Emas", "motif": "Jacquard", "grade": "A", "lebar": "1.5m"},
            "quantity": 100,
            "unit": "meter",
            "target_price": 200000,
            "notes": "test MTO"
        },
        "expected_delivery": "2026-08-01T00:00:00+00:00",
        "notes": "smoke f3",
        "submit_for_approval": True,
    }
    r = requests.post(f"{API}/special-orders", headers=H(tok), json=payload)
    assert r.status_code == 200, f"create SO failed {r.status_code}: {r.text}"
    so = r.json()
    print(f"[OK] special_order created {so['number']} status={so['status']} total={so['total_amount']}")
    assert so["status"] == "pending_approval", f"expected pending_approval got {so['status']}"

    # 2) approve → auto-create SKU
    r = requests.post(f"{API}/special-orders/{so['id']}/approve", headers=H(tok), json={"notes": "ok"})
    assert r.status_code == 200, f"approve failed {r.status_code}: {r.text}"
    so2 = r.json()
    print(f"[OK] approved status={so2['status']} linked_product_id={so2.get('linked_product_id')} sku={so2.get('linked_product_sku')}")
    assert so2["status"] == "confirmed"
    assert so2.get("linked_product_id"), "AUTO-SKU FAILED: no linked_product_id after approve"

    # verify product exists
    prod = requests.get(f"{API}/products", headers=H(tok)).json()
    plist = prod.get("items", prod) if isinstance(prod, dict) else prod
    found = next((p for p in plist if p["id"] == so2["linked_product_id"]), None)
    print(f"[OK] product exists in catalog: {bool(found)} sku={(found or {}).get('sku')} price={(found or {}).get('price')}")
    assert found, "linked product not in /products"

    # 3) idempotent manual create-sku
    r = requests.post(f"{API}/special-orders/{so['id']}/create-sku", headers=H(tok), json={})
    assert r.status_code == 200, f"create-sku failed {r.status_code}: {r.text}"
    cs = r.json()
    assert cs["product"]["id"] == so2["linked_product_id"], "create-sku NOT idempotent (different product)"
    print(f"[OK] create-sku idempotent → same product {cs['product']['id']}")

    # 4) convert-to-so
    r = requests.post(f"{API}/special-orders/{so['id']}/convert-to-so", headers=H(tok), json={})
    assert r.status_code == 200, f"convert-to-so failed {r.status_code}: {r.text}"
    cv = r.json()
    sales_order = cv["sales_order"]
    so3 = cv["special_order"]
    print(f"[OK] converted → SO {sales_order['number']} status={sales_order['status']} source_so={sales_order.get('source_special_order_id')}")
    assert sales_order.get("source_special_order_id") == so["id"], "SO not linked to special order"
    assert so3.get("linked_sales_order_id") == sales_order["id"], "special order not linked to SO"

    # 5) convert again → should reject (idempotent guard)
    r = requests.post(f"{API}/special-orders/{so['id']}/convert-to-so", headers=H(tok), json={})
    print(f"[OK] re-convert blocked: status={r.status_code} detail={r.json().get('detail')}")
    assert r.status_code == 400, "re-convert should be blocked"

    print("\n=== ALL F3 SMOKE CHECKS PASSED ===")


if __name__ == "__main__":
    main()
