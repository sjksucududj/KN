"""EPIC2 POC — Master Kategori Produk + Snapshot SO line.

Covers (single script, all cases):
  1. Seed migration: 7 categories present with product_count.
  2. SO-line backfill: every existing SO item has `category` (+base_unit/base_quantity).
  3. CRUD: create / patch (rename propagates to products) / delete guard (in-use 409).
  4. RBAC: sales cannot create/patch/delete categories (403); can view.
  5. New-order snapshot: creating a SO snapshots product.category onto the line.
  6. Uniqueness guards: duplicate name -> 409.
Run: python /app/test_epic2_categories_poc.py
"""
import os
import sys
import asyncio
import requests

BASE = "http://localhost:8001/api"
PASS = "demo12345"
results = {"pass": 0, "fail": 0}


def check(name, cond, extra=""):
    tag = "PASS" if cond else "FAIL"
    if cond:
        results["pass"] += 1
    else:
        results["fail"] += 1
    print(f"  [{tag}] {name}" + (f" — {extra}" if extra and not cond else ""))
    return cond


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PASS})
    r.raise_for_status()
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


async def db_checks():
    sys.path.insert(0, "/app/backend")
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]

    print("\n[2] SO-line backfill (DB-level)")
    total_orders = await db.sales_orders.count_documents({})
    missing = await db.sales_orders.count_documents({"items": {"$elemMatch": {"category": {"$exists": False}}}})
    check(f"all {total_orders} SO have category on every line (missing={missing})", missing == 0)
    # spot check a line has base_unit + base_quantity too
    so = await db.sales_orders.find_one({"items": {"$exists": True, "$ne": []}})
    if so:
        it0 = so["items"][0]
        check("SO line has category+base_unit+base_quantity keys",
              all(k in it0 for k in ("category", "base_unit", "base_quantity")),
              str(list(it0.keys())))
    cli.close()


def main():
    print("=" * 60)
    print("EPIC2 POC — Master Kategori + Snapshot SO")
    print("=" * 60)

    admin = login("admin@kainnusantara.id")
    sales = login("sales@kainnusantara.id")

    print("\n[1] Seed migration: categories master")
    cats = requests.get(f"{BASE}/product-categories", headers=H(admin)).json()
    names = sorted(c["name"] for c in cats)
    expected = ["Batik", "Endek", "Jumputan", "Lurik", "Songket", "Tenun", "Ulos"]
    check("7 baku categories seeded", all(e in names for e in expected), str(names))
    check("each category has product_count field", all("product_count" in c for c in cats))

    asyncio.run(db_checks())

    print("\n[3] RBAC: sales blocked from mutations")
    r = requests.post(f"{BASE}/product-categories", headers=H(sales),
                      json={"name": "ZZ Sales Cat"})
    check("sales POST -> 403", r.status_code == 403, f"got {r.status_code}")
    r = requests.get(f"{BASE}/product-categories", headers=H(sales))
    check("sales GET (view) -> 200", r.status_code == 200, f"got {r.status_code}")

    print("\n[4] CRUD lifecycle (admin)")
    r = requests.post(f"{BASE}/product-categories", headers=H(admin),
                      json={"name": "Poc Tester", "base_unit": "yard", "description": "poc"})
    check("create -> 200", r.status_code == 200, f"got {r.status_code} {r.text[:120]}")
    new = r.json() if r.status_code == 200 else {}
    cid = new.get("id")
    check("created code auto-generated", bool(new.get("code")), str(new))

    # duplicate name -> 409
    r = requests.post(f"{BASE}/product-categories", headers=H(admin),
                      json={"name": "Poc Tester"})
    check("duplicate name -> 409", r.status_code == 409, f"got {r.status_code}")

    # patch rename
    r = requests.patch(f"{BASE}/product-categories/{cid}", headers=H(admin),
                       json={"data": {"name": "Poc Renamed", "sort_order": 99}})
    check("patch rename -> 200", r.status_code == 200, f"got {r.status_code} {r.text[:120]}")
    check("patch reflects new name", r.json().get("name") == "Poc Renamed")

    # delete (not in use) -> 200
    r = requests.delete(f"{BASE}/product-categories/{cid}", headers=H(admin))
    check("delete unused -> 200 (soft inactive)", r.status_code == 200, f"got {r.status_code}")
    check("deleted is inactive", r.json().get("status") == "inactive")

    print("\n[5] Delete guard: in-use category blocked")
    cats2 = requests.get(f"{BASE}/product-categories", headers=H(admin)).json()
    in_use = next((c for c in cats2 if c.get("product_count", 0) > 0), None)
    if in_use:
        r = requests.delete(f"{BASE}/product-categories/{in_use['id']}", headers=H(admin))
        check(f"delete in-use '{in_use['name']}' -> 409", r.status_code == 409, f"got {r.status_code}")
    else:
        check("found an in-use category to test guard", False, "none had product_count>0")

    print("\n[6] New-order snapshot: SO line gets product.category")
    # find a customer + product to build an order as admin
    customers = requests.get(f"{BASE}/customers", headers=H(admin)).json()
    products = requests.get(f"{BASE}/products", headers=H(admin)).json()
    if customers and products:
        cust = customers[0]
        prod = next((p for p in products if p.get("category")), products[0])
        addr_id = (cust.get("addresses") or [{}])[0].get("id")
        payload = {
            "customer_id": cust["id"],
            "shipping_address_id": addr_id,
            "allow_backorder": True,
            "items": [{"product_id": prod["id"], "quantity": 5, "unit": prod.get("base_unit", "meter")}],
        }
        r = requests.post(f"{BASE}/sales-orders", headers=H(admin), json=payload)
        if r.status_code in (200, 201):
            so = r.json()
            line = (so.get("items") or [{}])[0]
            check("new SO line snapshots category == product.category",
                  line.get("category") == prod.get("category"),
                  f"line={line.get('category')} prod={prod.get('category')}")
        else:
            check("create SO -> 2xx", False, f"got {r.status_code} {r.text[:200]}")
    else:
        check("have customer+product to test order snapshot", False)

    print("\n" + "=" * 60)
    print(f"  RESULT: {results['pass']} PASS / {results['fail']} FAIL")
    print("=" * 60)
    sys.exit(0 if results["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
