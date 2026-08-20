"""POC EPIC5 — endpoint reorder "sering dibeli customer ini" + RBAC."""
import sys
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


def main():
    admin, sales, wh = login("admin@kainnusantara.id"), login("sales@kainnusantara.id"), login("warehouse@kainnusantara.id")
    custs = requests.get(f"{BASE}/customers", headers=H(admin)).json()
    # customer dgn >=1 order
    target = None
    for c in custs:
        ords = requests.get(f"{BASE}/sales-orders", headers=H(admin)).json()
        ords = ords if isinstance(ords, list) else ords.get("items", [])
        if any(o.get("customer_id") == c["id"] for o in ords):
            target = c
            break
    ok(target is not None, "Ada customer dgn order historis")

    print("\n=== reorder endpoint ===")
    r = requests.get(f"{BASE}/sales-orders/frequent-products", headers=H(sales), params={"customer_id": target["id"], "limit": 5})
    ok(r.status_code == 200, f"GET reorder (sales) 200 ({r.status_code})")
    rows = r.json()
    ok(isinstance(rows, list) and len(rows) > 0, f"reorder mengembalikan produk ({len(rows)})")
    if rows:
        x = rows[0]
        ok("reorder_count" in x and x["reorder_count"] >= 1, f"ada reorder_count ({x.get('reorder_count')})")
        ok("reorder_total_qty" in x, "ada reorder_total_qty")
        ok(all(k in x for k in ("id", "name", "sku", "price", "base_unit")), "data produk terkini disertakan")
        # urut desc by frequency
        counts = [it.get("reorder_count", 0) for it in rows]
        ok(counts == sorted(counts, reverse=True), f"terurut desc by frekuensi {counts}")

    print("\n=== edge & RBAC ===")
    ok(requests.get(f"{BASE}/sales-orders/frequent-products", headers=H(admin), params={"customer_id": "tidak_ada"}).json() == [],
       "customer tanpa order → [] kosong")
    ok(requests.get(f"{BASE}/sales-orders/frequent-products", headers=H(admin)).status_code == 200,
       "tanpa customer_id → 200 (graceful, bukan 422)")
    ok(requests.get(f"{BASE}/sales-orders/frequent-products", headers=H(wh), params={"customer_id": target["id"]}).status_code == 200,
       "warehouse (punya order:view) → 200")

    print(f"\n{'='*48}\n  HASIL: PASS {P} | FAIL {F}\n{'='*48}")
    sys.exit(1 if F else 0)


if __name__ == "__main__":
    main()
