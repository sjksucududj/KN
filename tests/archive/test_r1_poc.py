"""R1 — Sales Return State Machine + 4 Outcomes + Partial — POC/integration test.

Membuktikan:
  1. Lifecycle: draft → pending_approval → approved → inspecting → inspected → settle
  2. Guard: transisi invalid ditolak (settle sebelum inspect, inspect sebelum approve)
  3. Empat outcome: refund / store_credit / nego / reject (state terminal benar)
  4. Efek finansial: CN dibuat saat SETTLE (bukan approve); nego tanpa gerak stok
  5. Partial per item: reject sebagian item + settle_qty sebagian

Jalankan: python test_r1_poc.py
"""
import os
import sys
import requests

API = f"{os.environ.get('R1_BASE', 'http://localhost:8001')}/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✅ {name}")
    else:
        FAIL += 1; print(f"  ❌ {name}  {extra}")


def login():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30); r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def eligible_orders(h):
    r = requests.get(f"{API}/sales-orders", headers=h, timeout=30)
    orders = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    ok = {"confirmed", "partially_picked", "picked", "partially_shipped", "shipped", "done"}
    # butuh item dgn qty cukup besar agar bisa dipakai berulang
    res = []
    for o in orders:
        its = [it for it in (o.get("items") or []) if float(it.get("quantity", 0) or 0) >= 5]
        if its:
            res.append(o)
    return res


def try_create(h, orders, rtype="retur", qty=1, nitems=1):
    """Coba buat retur di salah satu order sampai berhasil (hindari batas retur)."""
    for o in orders:
        items = [{
            "product_id": it.get("product_id"), "product_name": it.get("product_name", ""),
            "quantity_returned": qty, "unit": it.get("unit", "meter"),
            "reason": "R1 POC", "condition": "ok",
        } for it in o["items"][:nitems] if float(it.get("quantity", 0) or 0) >= qty]
        if len(items) < nitems:
            continue
        r = requests.post(f"{API}/sales-returns", headers=h, timeout=30,
                          json={"order_id": o["id"], "return_type": rtype, "items": items, "notes": "R1"})
        if r.status_code == 200:
            return r.json()
    return None


def to_inspected(h, rid, rec="refund"):
    requests.post(f"{API}/sales-returns/{rid}/submit", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/approve", headers=h, json={"notes": ""}, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/inspect/complete", headers=h, timeout=30,
                  json={"inspections": [{"index": 0, "grade": "A", "condition": "ok",
                                         "recommended_outcome": rec, "accepted_qty": 1}], "notes": "ok"})


def main():
    h = login()
    orders = eligible_orders(h)
    print(f"== R1 POC == (eligible orders: {len(orders)})")
    if not orders:
        check("ada order eligible", False); print(f"PASS={PASS} FAIL={FAIL}"); sys.exit(1)

    # ── 1. Lifecycle + guards ──
    print("\n[1] Lifecycle + guards")
    ret = try_create(h, orders); check("create return → draft", ret and ret["status"] == "draft", str(ret)[:150])
    rid = ret["id"]
    g = requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, json={"outcome": "refund"}, timeout=30)
    check("guard: settle dari draft ditolak (400)", g.status_code == 400, f"{g.status_code}")
    r = requests.post(f"{API}/sales-returns/{rid}/submit", headers=h, timeout=30)
    check("submit → pending_approval", r.json().get("status") == "pending_approval")
    g = requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
    check("guard: inspect dari pending ditolak (400)", g.status_code == 400, f"{g.status_code}")
    r = requests.post(f"{API}/sales-returns/{rid}/approve", headers=h, json={"notes": "ok"}, timeout=30)
    ad = r.json()
    check("approve → approved", ad.get("status") == "approved")
    check("approve TIDAK buat CN (baru saat settle)", not ad.get("credit_note_number"), str(ad.get("credit_note_number")))
    check("approve TIDAK adjust stok", not ad.get("stock_adjusted"))
    r = requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
    check("inspect start → inspecting", r.json().get("status") == "inspecting")
    r = requests.post(f"{API}/sales-returns/{rid}/inspect/complete", headers=h, timeout=30,
                      json={"inspections": [{"index": 0, "grade": "A", "condition": "ok",
                                             "recommended_outcome": "refund", "accepted_qty": 1}]})
    ins = r.json()
    check("inspect complete → inspected", ins.get("status") == "inspected")
    check("hasil inspeksi tersimpan per item", bool((ins["items"][0] or {}).get("inspection")))
    r = requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30, json={"outcome": "refund"})
    sd = r.json()
    check("settle refund → refund_settled", sd.get("status") == "refund_settled", r.text[:150])
    check("refund settle buat Credit Note", bool(sd.get("credit_note_number")))
    check("refund settle adjust stok", sd.get("stock_adjusted") is True)
    r2 = requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30, json={"outcome": "refund"})
    check("settle idempotent", r2.status_code == 200 and r2.json().get("credit_note_number") == sd.get("credit_note_number"))

    # ── 2. store_credit ──
    print("\n[2] Outcome store_credit → credit_settled")
    ret2 = try_create(h, orders); check("create #2", bool(ret2), str(ret2)[:120])
    if ret2:
        to_inspected(h, ret2["id"], "store_credit")
        sc = requests.post(f"{API}/sales-returns/{ret2['id']}/settle", headers=h, timeout=30,
                           json={"outcome": "store_credit"}).json()
        check("→ credit_settled", sc.get("status") == "credit_settled", str(sc)[:150])
        check("CN settlement=store_credit", (sc.get("settlement") or {}).get("settlement") == "store_credit", str(sc.get("settlement")))
        check("store_credit_amount tercatat (ledger R5)", (sc.get("settlement") or {}).get("store_credit_amount", 0) > 0)

    # ── 3. nego (tanpa gerak stok) ──
    print("\n[3] Outcome nego → nego_settled (tanpa gerak stok)")
    ret3 = try_create(h, orders); check("create #3", bool(ret3))
    if ret3:
        to_inspected(h, ret3["id"], "nego")
        ng = requests.post(f"{API}/sales-returns/{ret3['id']}/settle", headers=h, timeout=30,
                           json={"outcome": "nego"}).json()
        check("→ nego_settled", ng.get("status") == "nego_settled", str(ng)[:150])
        check("nego TIDAK adjust stok", not ng.get("stock_adjusted"))
        check("nego buat CN diskon", bool(ng.get("credit_note_number")))

    # ── 4. reject ──
    print("\n[4] Outcome reject → rejected")
    ret4 = try_create(h, orders); check("create #4", bool(ret4))
    if ret4:
        requests.post(f"{API}/sales-returns/{ret4['id']}/submit", headers=h, timeout=30)
        rj = requests.post(f"{API}/sales-returns/{ret4['id']}/reject", headers=h, timeout=30,
                           json={"notes": "tidak sesuai klaim"}).json()
        check("reject → rejected", rj.get("status") == "rejected", str(rj)[:120])
        check("outcome=reject", rj.get("outcome") == "reject")

    # ── 5. partial per item ──
    print("\n[5] Partial: reject item ke-2 + settle_qty sebagian item ke-1")
    ret5 = try_create(h, orders, qty=2, nitems=2)
    if ret5 and len(ret5.get("items", [])) >= 2:
        rid5 = ret5["id"]
        requests.post(f"{API}/sales-returns/{rid5}/submit", headers=h, timeout=30)
        requests.post(f"{API}/sales-returns/{rid5}/approve", headers=h, json={"notes": ""}, timeout=30)
        requests.post(f"{API}/sales-returns/{rid5}/inspect/start", headers=h, timeout=30)
        requests.post(f"{API}/sales-returns/{rid5}/inspect/complete", headers=h, timeout=30, json={"inspections": []})
        pt = requests.post(f"{API}/sales-returns/{rid5}/settle", headers=h, timeout=30, json={
            "outcome": "refund",
            "item_decisions": [{"index": 0, "settle_qty": 1}, {"index": 1, "outcome": "reject"}]}).json()
        check("partial settle → refund_settled", pt.get("status") == "refund_settled", str(pt)[:150])
        check("item[0] settled_qty=1", abs(float(pt["items"][0].get("settled_qty", 0)) - 1) < 0.01, str(pt["items"][0].get("settled_qty")))
        check("item[1] outcome=reject", pt["items"][1].get("settle_outcome") == "reject")
    else:
        print("     (lewati: tak ada order multi-item qty>=2)")

    print(f"\n=== HASIL R1: PASS={PASS}  FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
