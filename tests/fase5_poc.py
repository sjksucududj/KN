"""F5 POC — validasi end-to-end Unified Approval + RBAC (lokal, localhost:8001).

Cakupan user-story:
  1. RBAC: SALES tak bisa input diskon (diskon dipaksa 0 saat create).
  2. Over-credit TIDAK 409: SO tetap dibuat + entri pending_approval `kredit` + credit_hold.
  3. Sales ajukan special price (detail SO) → entri `special_price` pending; harga item belum berubah.
  4. RBAC: SALES 403 di /approve & /decide & /approvals/queue.
  5. Admin decide special_price approve → harga item berubah + total recompute.
  6. approve_order DIBLOKIR 409 (APPROVAL_PENDING) saat masih ada kredit/harga pending.
  7. Admin decide kredit approve → credit_hold clear.
  8. Saat SEMUA approved → SO otomatis naik ke stage Approved.
  9. Queue approver menampilkan entri pending lintas SO.
"""
import sys
import requests

BASE = "http://localhost:8001/api"
PW = "demo12345"
results = []


def log(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    print("=== F5 POC — Unified Approval + RBAC ===")
    sales = login("sales@kainnusantara.id")
    admin = login("admin@kainnusantara.id")
    print("login OK (sales, admin)")

    # data
    custs = requests.get(f"{BASE}/customers", headers=H(sales), timeout=30).json()
    prods = requests.get(f"{BASE}/products", headers=H(sales), timeout=30).json()
    if not custs or not prods:
        print("NO customers/products for sales — abort"); sys.exit(1)
    cust = custs[0]
    prod = next((p for p in prods if float(p.get("price", 0) or 0) > 0), prods[0])
    addr_id = (cust.get("addresses") or [{}])[0].get("id", "")
    print(f"customer={cust['name']} price={prod.get('price')} credit_limit={cust.get('credit_limit')}")

    # ── 1. RBAC discount removed: sales create SO dengan discount_percent 20 ──
    body = {
        "customer_id": cust["id"], "shipping_address_id": addr_id,
        "items": [{"product_id": prod["id"], "quantity": 5, "unit": prod.get("base_unit", "meter"),
                   "discount_percent": 20}],
        "order_discount_percent": 15, "allow_backorder": True, "confirm_mixed_lot": True,
        "sales_name": "Sales Demo",
    }
    r = requests.post(f"{BASE}/sales-orders", headers=H(sales), json=body, timeout=60)
    if r.status_code != 200:
        log("1. create SO (sales)", False, f"HTTP {r.status_code}: {r.text[:200]}"); _finish(); return
    so = r.json()
    so_id = so["id"]
    item0 = so["items"][0]
    log("1. SALES discount dipaksa 0 (item)", float(item0.get("discount_percent", -1)) == 0,
        f"item.discount_percent={item0.get('discount_percent')}")
    log("1b. SALES order_discount dipaksa 0", float(so.get("order_discount_percent", -1)) == 0,
        f"order_discount_percent={so.get('order_discount_percent')}")
    print(f"   SO={so['number']} grand_total={so.get('grand_total')} stage={so.get('stage')} status={so.get('status')}")

    # ── 2. Over-credit non-blocking: SO besar yang melebihi limit ──
    big_qty = 100000  # paksa nilai sangat besar > limit kredit
    body2 = {
        "customer_id": cust["id"], "shipping_address_id": addr_id,
        "items": [{"product_id": prod["id"], "quantity": big_qty, "unit": prod.get("base_unit", "meter")}],
        "allow_backorder": True, "confirm_mixed_lot": True, "sales_name": "Sales Demo",
    }
    r2 = requests.post(f"{BASE}/sales-orders", headers=H(sales), json=body2, timeout=60)
    over_ok = r2.status_code == 200
    log("2. Over-credit TIDAK diblokir 409", over_ok, f"HTTP {r2.status_code}")
    so2 = r2.json() if over_ok else {}
    so2_id = so2.get("id")
    pa2 = so2.get("pending_approvals", []) if over_ok else []
    has_kredit = any(p.get("type") == "kredit" and p.get("status") == "pending" for p in pa2)
    log("2b. Entri pending_approval `kredit` dibuat", has_kredit,
        f"credit_hold={so2.get('credit_hold')} types={[p.get('type') for p in pa2]}")

    # ── 3. Sales ajukan special price pada SO #1 ──
    sp_body = {"item_index": 0, "requested_price": round(float(item0["price"]) * 0.7, 2),
               "reason": "Nego customer loyal, kompetitor lebih murah."}
    r3 = requests.post(f"{BASE}/sales-orders/{so_id}/request-special-price", headers=H(sales), json=sp_body, timeout=60)
    sp_ok = r3.status_code == 200
    log("3. Sales ajukan special price", sp_ok, f"HTTP {r3.status_code}: {r3.text[:160] if not sp_ok else ''}")
    so_after = r3.json() if sp_ok else {}
    pa1 = so_after.get("pending_approvals", [])
    sp_entry = next((p for p in pa1 if p.get("type") == "special_price"), None)
    log("3b. Harga item BELUM berubah (sebelum approve)",
        sp_ok and float(so_after["items"][0]["price"]) == float(item0["price"]),
        f"price now={so_after.get('items',[{}])[0].get('price') if sp_ok else '?'}")

    # ── 4. RBAC: sales tak bisa approve / decide / lihat queue ──
    ra = requests.post(f"{BASE}/sales-orders/{so_id}/approve", headers=H(sales), timeout=30)
    log("4. SALES /approve → 403", ra.status_code == 403, f"HTTP {ra.status_code}")
    if sp_entry:
        rd = requests.post(f"{BASE}/sales-orders/{so_id}/approvals/{sp_entry['id']}/decide",
                           headers=H(sales), json={"decision": "approve"}, timeout=30)
        log("4b. SALES /decide → 403", rd.status_code == 403, f"HTTP {rd.status_code}")
    rq = requests.get(f"{BASE}/approvals/queue", headers=H(sales), timeout=30)
    log("4c. SALES /approvals/queue → 403", rq.status_code == 403, f"HTTP {rq.status_code}")

    # ── 5. Admin approve_order DIBLOKIR (masih ada special_price pending) ──
    rab = requests.post(f"{BASE}/sales-orders/{so_id}/approve", headers=H(admin), timeout=30)
    blocked = rab.status_code == 409 and (rab.json().get("detail", {}).get("code") == "APPROVAL_PENDING")
    log("5. approve_order DIBLOKIR saat ada approval pending", blocked,
        f"HTTP {rab.status_code} code={rab.json().get('detail',{}).get('code') if rab.status_code==409 else '-'}")

    # ── 6. Admin queue terlihat + decide special_price approve → harga berubah ──
    rq2 = requests.get(f"{BASE}/approvals/queue", headers=H(admin), timeout=30)
    queue = rq2.json() if rq2.status_code == 200 else []
    log("6. ADMIN queue menampilkan entri pending", rq2.status_code == 200 and len(queue) >= 1,
        f"queue size={len(queue)}")
    if sp_entry:
        rdec = requests.post(f"{BASE}/sales-orders/{so_id}/approvals/{sp_entry['id']}/decide",
                             headers=H(admin), json={"decision": "approve", "notes": "OK margin masih sehat."}, timeout=60)
        dok = rdec.status_code == 200
        so_dec = rdec.json() if dok else {}
        new_price = float(so_dec.get("items", [{}])[0].get("price", -1)) if dok else -1
        log("6b. Admin approve special_price → harga item BERUBAH", dok and abs(new_price - sp_body["requested_price"]) < 0.01,
            f"new_price={new_price} expected={sp_body['requested_price']}")
        # invarian: total_amount == Σ subtotal
        if dok:
            inv = abs(sum(float(it["price"]) * float(it["quantity"]) for it in so_dec["items"]) - float(so_dec["total_amount"])) < 1
            log("6c. Invarian total_amount = Σ(price×qty)", inv, f"total_amount={so_dec.get('total_amount')}")

    # ── 7. SO #1: putuskan SEMUA approval tersisa → SO naik ke Approved ──
    so1_now = requests.get(f"{BASE}/sales-orders/{so_id}", headers=H(admin), timeout=30).json()
    for p in list(so1_now.get("pending_approvals", [])):
        if p.get("status") != "pending":
            continue
        requests.post(f"{BASE}/sales-orders/{so_id}/approvals/{p['id']}/decide",
                      headers=H(admin), json={"decision": "approve", "notes": "ok"}, timeout=60)
    so1_now = requests.get(f"{BASE}/sales-orders/{so_id}", headers=H(admin), timeout=30).json()
    log("7. SO#1 naik ke stage Approved setelah SEMUA approval approved",
        so1_now.get("stage") == "Approved" and so1_now.get("status") == "approved",
        f"stage={so1_now.get('stage')} status={so1_now.get('status')}")

    # ── 8. SO #2 (over-credit) decide kredit approve → credit_hold clear ──
    if so2_id:
        kentry = next((p for p in pa2 if p.get("type") == "kredit"), None)
        if kentry:
            rk = requests.post(f"{BASE}/sales-orders/{so2_id}/approvals/{kentry['id']}/decide",
                               headers=H(admin), json={"decision": "approve", "notes": "Disetujui, ada jaminan."}, timeout=60)
            so2_dec = rk.json() if rk.status_code == 200 else {}
            log("8. Admin approve kredit → credit_hold clear",
                rk.status_code == 200 and so2_dec.get("credit_hold") in (False, None),
                f"HTTP {rk.status_code} credit_hold={so2_dec.get('credit_hold')}")

    _finish()


def _finish():
    total = len(results)
    passed = sum(1 for x in results if x)
    print(f"\n=== RESULT: {passed}/{total} PASS ===")
    sys.exit(0 if passed == total else 2)


if __name__ == "__main__":
    main()
