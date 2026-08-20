"""POC FASE 5 — Alur Approval Terpadu (pending_approvals SSOT) + RBAC + storage LOKAL.

Menguji END-TO-END via API live (http://localhost:8001):
  1. Login admin/manager/sales (RBAC).
  2. Sales buat SO  -> ada entri 'nilai' (validasi) pending; SO belum Approved.
  3. Sales ajukan Harga Khusus -> entri 'special_price' pending + price_approvals doc.
  4. Sales DILARANG decide / approve order (403).
  5. Unggah bukti (storage LOKAL) -> download balik OK.
  6. Manager approve special_price -> harga item ter-update + totals recompute.
  7. /approvals/queue: manager lihat antrian; sales 403.
  8. Manager approve 'nilai' -> SEMUA approved -> SO auto-advance ke Approved.
  9. Over-credit: SO TETAP tersimpan (bukan 409) + credit_hold + entri 'kredit'.
 10. Manager approve 'kredit' -> credit_hold lepas.

Jalankan: python /app/test_f5_approval_poc.py
"""
import base64
import sys
import requests

BASE = "http://localhost:8001/api"
PW = "demo12345"
ENTITY = "ent_ksc"
# 1x1 PNG valid (transparan)
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(("  [PASS] " if cond else "  [FAIL] ") + name + ("" if cond else f"  -> {detail}"))


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}", "X-Entity-Id": ENTITY}


def main():
    print("\n=== POC FASE 5 — Unified Approval + RBAC + local storage ===\n")
    admin = login("admin@kainnusantara.id")
    manager = login("manager@kainnusantara.id")
    sales = login("sales@kainnusantara.id")
    check("login admin/manager/sales", all([admin, manager, sales]))

    prods = requests.get(f"{BASE}/products", headers=H(sales), timeout=30).json()
    prod = next((p for p in prods if (p.get("entity_id") in (ENTITY, None, "")) or True), prods[0])
    custs = requests.get(f"{BASE}/customers", headers=H(sales), timeout=30).json()
    cust = next((c for c in custs if c["id"] == "cust_butik_bali"), custs[0])
    addr_id = (cust.get("addresses") or [{}])[0].get("id", "")
    base_unit = prod.get("base_unit", "meter")
    price = float(prod.get("price", 0) or 0)
    check("ada produk, customer & alamat", bool(prod and cust and addr_id),
          f"prod={bool(prod)} cust={bool(cust)} addr={addr_id}")

    # ── 2) Sales buat SO kecil ────────────────────────────────────────────────
    payload = {
        "customer_id": cust["id"], "shipping_address_id": addr_id,
        "items": [{"product_id": prod["id"], "quantity": 5, "unit": base_unit}],
        "sales_name": "Ayu Permatasari", "allow_backorder": True,
        "confirm_mixed_lot": True, "entity_id": ENTITY,
    }
    r = requests.post(f"{BASE}/sales-orders", headers=H(sales), json=payload, timeout=60)
    check("sales buat SO -> 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    if r.status_code != 200:
        return summarize()
    so = r.json(); oid = so["id"]
    pa = so.get("pending_approvals", [])
    check("SO butuh validasi/approval (gate aktif)",
          so.get("approval_required") is True or len(pa) > 0,
          f"approval_required={so.get('approval_required')} pa={pa}")
    check("SO belum Approved", so["status"] in ("reserved", "waiting_stock", "waiting_approval", "draft"), so["status"])

    # ── 3) Sales ajukan harga khusus ────────────────────────────────────────
    special_price = round(max(1.0, price * 0.8), 2)
    r = requests.post(f"{BASE}/sales-orders/{oid}/request-special-price", headers=H(sales),
                      json={"item_index": 0, "requested_price": special_price, "reason": "Nego customer besar"}, timeout=30)
    check("request-special-price -> 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    so = r.json()
    sp = [p for p in so.get("pending_approvals", []) if p["type"] == "special_price" and p["status"] == "pending"]
    check("entri special_price ditambahkan", len(sp) == 1, str(so.get("pending_approvals")))
    # price_approvals doc dibuat (referensi)
    pr = requests.get(f"{BASE}/price-approvals", headers=H(manager), params={"status": "pending"}, timeout=30).json()
    check("price_approvals doc tertaut SO dibuat", any(x.get("so_id") == oid for x in (pr if isinstance(pr, list) else [])),
          f"count={len(pr) if isinstance(pr, list) else 'n/a'}")

    # ── 4) RBAC: sales DILARANG decide / approve order ─────────────────────────
    if sp:
        r = requests.post(f"{BASE}/sales-orders/{oid}/approvals/{sp[0]['id']}/decide", headers=H(sales),
                          json={"decision": "approve"}, timeout=30)
        check("sales decide approval -> 403", r.status_code == 403, f"{r.status_code} {r.text[:200]}")
    r = requests.post(f"{BASE}/sales-orders/{oid}/approve", headers=H(sales), timeout=30)
    check("sales approve order -> 403", r.status_code == 403, f"{r.status_code} {r.text[:200]}")

    # ── 5) Unggah bukti (storage LOKAL) + download ────────────────────────────
    if sp:
        files = {"file": ("bukti.png", PNG, "image/png")}
        r = requests.post(f"{BASE}/sales-orders/{oid}/approvals/{sp[0]['id']}/evidence", headers=H(sales),
                          files=files, timeout=60)
        check("unggah bukti (local storage) -> 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
        if r.status_code == 200:
            att = r.json()
            rd = requests.get(
                f"{BASE}/sales-orders/{oid}/approvals/{sp[0]['id']}/evidence/{att['id']}/download",
                headers=H(sales), timeout=30)
            check("download bukti -> 200 + bytes", rd.status_code == 200 and len(rd.content) > 0,
                  f"{rd.status_code} len={len(rd.content)}")

    # ── 6) Manager approve special_price -> harga item ter-update ─────────────
    if sp:
        r = requests.post(f"{BASE}/sales-orders/{oid}/approvals/{sp[0]['id']}/decide", headers=H(manager),
                          json={"decision": "approve", "notes": "OK"}, timeout=30)
        check("manager approve special_price -> 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
        so = r.json()
        check("harga item ter-update ke harga khusus",
              abs(float(so["items"][0]["price"]) - special_price) < 1.0,
              f"price={so['items'][0]['price']} expected~{special_price}")

    # ── 7) /approvals/queue: manager lihat; sales 403 ─────────────────────────
    r = requests.get(f"{BASE}/approvals/queue", headers=H(manager), timeout=30)
    check("manager GET /approvals/queue -> 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    q = r.json() if r.status_code == 200 else []
    check("queue memuat SO kita (nilai pending)", any(x.get("order_id") == oid for x in q), f"n={len(q)}")
    r = requests.get(f"{BASE}/approvals/queue", headers=H(sales), timeout=30)
    check("sales GET /approvals/queue -> 403", r.status_code == 403, str(r.status_code))

    # ── 8) Manager approve SEMUA entri tersisa -> SO Approved ────────────────
    so = requests.get(f"{BASE}/sales-orders/{oid}", headers=H(manager), timeout=30).json()
    for _ in range(8):
        pend = [p for p in so.get("pending_approvals", []) if p["status"] == "pending"]
        if not pend:
            break
        rr = requests.post(f"{BASE}/sales-orders/{oid}/approvals/{pend[0]['id']}/decide", headers=H(manager),
                           json={"decision": "approve"}, timeout=30)
        if rr.status_code != 200:
            check("decide entri pending -> 200", False, f"{rr.status_code} {rr.text[:200]}")
            break
        so = rr.json()
    check("semua approval diputuskan (tak ada pending)",
          all(p["status"] != "pending" for p in so.get("pending_approvals", [])),
          str([(p["type"], p["status"]) for p in so.get("pending_approvals", [])]))
    check("SO auto-advance ke Approved (semua approved)", so.get("status") == "approved",
          f"status={so.get('status')}")

    # ── 9) Over-credit: SO tetap tersimpan (bukan 409) ────────────────────────
    if price > 0:
        big_qty = int(40_000_000 / price) + 50
    else:
        big_qty = 100000
    payload2 = {
        "customer_id": cust["id"], "shipping_address_id": addr_id,
        "items": [{"product_id": prod["id"], "quantity": big_qty, "unit": base_unit}],
        "sales_name": "Ayu Permatasari", "allow_backorder": True,
        "confirm_mixed_lot": True, "entity_id": ENTITY,
    }
    r = requests.post(f"{BASE}/sales-orders", headers=H(sales), json=payload2, timeout=60)
    check("over-credit SO TETAP tersimpan (bukan 409)", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    if r.status_code == 200:
        so2 = r.json(); oid2 = so2["id"]
        check("over-credit: credit_hold = True", so2.get("credit_hold") is True, str(so2.get("credit_hold")))
        kr = [p for p in so2.get("pending_approvals", []) if p["type"] == "kredit" and p["status"] == "pending"]
        check("over-credit: entri 'kredit' pending", len(kr) >= 1, str(so2.get("pending_approvals")))
        # ── 10) Manager approve kredit -> credit_hold lepas ───────────────────
        if kr:
            r = requests.post(f"{BASE}/sales-orders/{oid2}/approvals/{kr[0]['id']}/decide", headers=H(manager),
                              json={"decision": "approve"}, timeout=30)
            check("manager approve 'kredit' -> 200", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
            so2 = r.json()
            check("credit_hold lepas setelah approve kredit", so2.get("credit_hold") is False, str(so2.get("credit_hold")))

    return summarize()


def summarize():
    total = len(RESULTS); passed = sum(RESULTS); failed = total - passed
    print(f"\n=== SUMMARY: {passed}/{total} PASS, {failed} FAIL ===\n")
    return failed == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
