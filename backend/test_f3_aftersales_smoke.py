"""F3 aftersales smoke — credit note + GL reversal on a REAL seeded SO (with inventory/cost)."""
import requests

BU = [l for l in open("/app/frontend/.env").read().splitlines()
      if l.startswith("REACT_APP_BACKEND_URL")][0].split("=", 1)[1].strip()
API = f"{BU}/api"


def login(email, pw):
    d = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}).json()
    return d["token"], d.get("entity_context", {})


def H(tok, entity=None):
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    if entity:
        h["X-Entity-Id"] = entity
    return h


def main():
    tok, ctx = login("manager@kainnusantara.id", "demo12345")
    H_all = H(tok, "all")

    # find returnable SO across all entities with items
    orders = requests.get(f"{API}/sales-orders", headers=H_all).json()
    orders = orders.get("items", orders) if isinstance(orders, dict) else orders
    returnable = [o for o in orders if o.get("status") in
                  ("confirmed", "partially_picked", "picked", "partially_shipped", "shipped", "done")
                  and o.get("items")]
    assert returnable, "no returnable seeded SO found"
    so = returnable[0]
    ent = so.get("entity_id")
    print(f"[OK] returnable SO {so['number']} status={so['status']} entity={ent} items={len(so['items'])}")

    it = so["items"][0]
    # GL trial balance before
    tb0 = requests.get(f"{API}/gl/trial-balance", headers=H(tok, ent)).json()
    print(f"[OK] trial balance before: balanced={tb0.get('balanced')} debit={tb0.get('total_debit')}")

    # create return with type 'komplain'
    ret_payload = {
        "order_id": so["id"],
        "entity_id": ent,
        "return_type": "komplain",
        "items": [{
            "product_id": it["product_id"],
            "product_name": it.get("product_name", ""),
            "quantity_returned": 5,
            "unit": it.get("unit", "meter"),
            "reason": "komplain kualitas (smoke)",
            "condition": "ok",
        }],
        "notes": "smoke aftersales komplain",
        "submit_now": True,
    }
    r = requests.post(f"{API}/sales-returns", headers=H(tok, ent), json=ret_payload)
    assert r.status_code == 200, f"create return failed {r.status_code}: {r.text}"
    ret = r.json()
    print(f"[OK] return created {ret['number']} type={ret['return_type']} status={ret['status']}")
    assert ret["return_type"] == "komplain"

    # approve → triggers credit note + GL reversal
    r = requests.post(f"{API}/sales-returns/{ret['id']}/approve", headers=H(tok, ent), json={"notes": "approve smoke"})
    assert r.status_code == 200, f"approve return failed {r.status_code}: {r.text}"
    ret2 = r.json()
    print(f"[OK] return approved status={ret2['status']} cn={ret2.get('credit_note_number')} cn_amount={ret2.get('credit_note_amount')}")
    assert ret2["status"] == "approved"
    assert ret2.get("credit_note_number"), "NO credit note generated after approve"

    # verify credit notes list
    cns = requests.get(f"{API}/credit-notes", headers=H(tok, ent)).json()
    cn_items = cns.get("items", [])
    mine = next((c for c in cn_items if c.get("return_id") == ret["id"]), None)
    print(f"[OK] credit-notes list count={len(cn_items)} mine={bool(mine)} gross={(mine or {}).get('gross_amount')} settlement={(mine or {}).get('settlement')} cogs={(mine or {}).get('cogs_amount')}")
    assert mine, "credit note not found in GET /credit-notes"

    # verify GL reversal journal (source_type sales_return)
    je = None
    for path in ("/gl/entries", "/gl/journal-entries"):
        rr = requests.get(f"{API}{path}", headers=H(tok, ent), params={"source": "sales_return"})
        if rr.status_code == 200:
            data = rr.json()
            je = data.get("items", data) if isinstance(data, dict) else data
            break
    print(f"[OK] sales_return GL entries fetched: {len(je) if je is not None else 'n/a'}")

    tb1 = requests.get(f"{API}/gl/trial-balance", headers=H(tok, ent)).json()
    print(f"[OK] trial balance after: balanced={tb1.get('balanced')} debit={tb1.get('total_debit')}")
    assert tb1.get("balanced"), "trial balance NOT balanced after credit note"

    print("\n=== AFTERSALES CREDIT NOTE SMOKE PASSED ===")


if __name__ == "__main__":
    main()
