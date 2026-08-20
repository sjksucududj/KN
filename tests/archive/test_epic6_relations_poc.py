"""POC EPIC6 — Document Relations / Process Timeline + deep-link metadata + RBAC."""
import requests

BASE = "http://localhost:8001/api"
P, F = 0, 0


def ok(c, m):
    global P, F
    P += 1 if c else 0
    F += 0 if c else 1
    print(f"  [{'PASS' if c else 'FAIL'}] {m}")


def login(e):
    return requests.post(f"{BASE}/auth/login", json={"email": e, "password": "demo12345"}).json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


def stages_map(data):
    return {s["key"]: s for s in data.get("stages", [])}


def main():
    admin, sales = login("admin@kainnusantara.id"), login("sales@kainnusantara.id")

    print("=== SALES_ORDER chain (so_001) ===")
    r = requests.get(f"{BASE}/documents/relations/sales_order/so_001", headers=H(admin))
    ok(r.status_code == 200, f"GET sales_order relations 200 ({r.status_code})")
    d = r.json()
    ok(d.get("doc_type") == "sales_order", "doc_type=sales_order")
    ok(d.get("anchor", {}).get("number") == "SO-0001", f"anchor number SO-0001 ({d.get('anchor',{}).get('number')})")
    sm = stages_map(d)
    expected = ["order", "shipment", "tax", "payment", "commission"]
    ok(all(k in sm for k in expected), f"semua stage SO ada ({list(sm.keys())})")
    ok(len(sm["order"]["docs"]) == 1, "stage order tepat 1 anchor")
    ok(len(sm["shipment"]["docs"]) >= 1, f"ada shipment ({len(sm['shipment']['docs'])})")
    ship = sm["shipment"]["docs"][0]
    ok(ship["link"]["kind"] == "url" and "/surat-jalan" in (ship["link"]["doc_url"] or ""), "shipment punya doc_url surat-jalan")
    ok(len(sm["payment"]["docs"]) >= 1, f"ada AR receipt ({len(sm['payment']['docs'])})")
    pay = sm["payment"]["docs"][0]
    ok(pay["type"] == "ar_receipt" and pay["amount"] is not None, "AR node punya amount terapply")
    anchor_link = sm["order"]["docs"][0]["link"]
    ok(anchor_link["view"] == "orders" and anchor_link["focus_type"] == "sales_order", "anchor deep-link -> orders/focus")
    ok("empty_hint" in sm["tax"], "stage kosong (tax) tetap punya empty_hint (no dead-end)")

    print("\n=== PURCHASE_ORDER chain (po_009, ter-link PR) ===")
    r = requests.get(f"{BASE}/documents/relations/purchase_order/po_009", headers=H(admin))
    ok(r.status_code == 200, f"GET purchase_order relations 200 ({r.status_code})")
    d = r.json()
    sm = stages_map(d)
    expected = ["requisition", "po", "grn", "landed_cost", "bill"]
    ok(all(k in sm for k in expected), f"semua stage PO ada ({list(sm.keys())})")
    ok(len(sm["requisition"]["docs"]) == 1, f"PR sumber ter-link ({len(sm['requisition']['docs'])})")
    pr = sm["requisition"]["docs"][0]
    ok(pr["type"] == "purchase_requisition" and pr["link"]["view"] == "purchase-requisitions", "PR node deep-link -> purchase-requisitions")
    ok(len(sm["grn"]["docs"]) >= 1, f"ada GRN/penerimaan ({len(sm['grn']['docs'])})")
    ok(sm["grn"]["docs"][0]["link"]["view"] == "operations", "GRN node deep-link -> operations")
    ok(sm["po"]["docs"][0]["link"]["view"] == "purchasing", "PO anchor deep-link -> purchasing")

    print("\n=== RBAC & edge ===")
    ok(requests.get(f"{BASE}/documents/relations/purchase_order/po_009", headers=H(sales)).status_code == 403,
       "sales -> purchase_order relations = 403")
    ok(requests.get(f"{BASE}/documents/relations/sales_order/so_001", headers=H(sales)).status_code == 200,
       "sales -> sales_order relations = 200")
    ok(requests.get(f"{BASE}/documents/relations/foobar/x", headers=H(admin)).status_code == 400,
       "doc_type invalid = 400")
    ok(requests.get(f"{BASE}/documents/relations/sales_order/nope", headers=H(admin)).status_code == 404,
       "id tidak dikenal = 404")

    print("\n" + "=" * 48)
    print(f"  HASIL: PASS {P} | FAIL {F}")
    print("=" * 48)
    return 0 if F == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
