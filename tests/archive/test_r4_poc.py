"""R4 — Retur Jual↔Beli link + Supplier RMA lifecycle + goods_back/regrade + policy impor — POC.

Membuktikan (semua via HTTP API, DB nyata):
  [1] Chain: retur jual (settle refund → roll karantina) → BUAT retur beli tertaut (2 arah).
      Alur RMA: approve = gate (stok/DN BELUM) → ship-to-supplier → supplier-accept(ap_credit)
      → finalisasi (roll returned_supplier + Nota Debit + AP + GL).
  [2] Supplier TOLAK → goods_back: barang kembali ke KN (roll available) + REGRADE A→B, TANPA Nota Debit.
  [3] Kebijakan IMPOR (§J): supplier impor & returnable_to_supplier=false → create retur beli 400
      (rekomendasi regrade+jual lokal); dengan bypass_import_policy=true → lolos.
  [4] Regression alur DIRECT (supplier_flow=false): approve langsung → approved + Nota Debit + stok.
  [5] Guards: accept sebelum ship → 400; goods-back sebelum reject → 400; ship pada retur DIRECT → 400.

Jalankan: python test_r4_poc.py
"""
import os
import sys
import requests

API = f"{os.environ.get('R4_BASE', 'http://localhost:8001')}/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  \u2705 {name}")
    else:
        FAIL += 1; print(f"  \u274c {name}  {extra}")


def login():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30); r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def as_list(r):
    j = r.json()
    return j if isinstance(j, list) else j.get("items", [])


def eligible(h):
    o = as_list(requests.get(f"{API}/sales-orders", headers=h, timeout=30))
    ok = {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
    return [x for x in o if x.get("status") in ok and
            any(float(it.get("quantity", 0) or 0) >= 5 for it in (x.get("items") or []))]


def make_settled_return(h, orders, dest_wh):
    """Buat 1 retur jual → inspect → settle refund → kembalikan (sr_doc, quarantine_rolls)."""
    for o in orders:
        its = [it for it in o["items"] if float(it.get("quantity", 0) or 0) >= 1]
        if not its:
            continue
        it = its[0]
        r = requests.post(f"{API}/sales-returns", headers=h, timeout=30, json={
            "order_id": o["id"], "return_type": "retur",
            "items": [{"product_id": it["product_id"], "product_name": it.get("product_name", ""),
                       "quantity_returned": 1, "unit": it.get("unit", "meter"),
                       "reason": "R4", "condition": "ok"}], "notes": "R4"})
        if r.status_code != 200:
            continue
        rid = r.json()["id"]
        requests.post(f"{API}/sales-returns/{rid}/submit", headers=h, timeout=30)
        requests.post(f"{API}/sales-returns/{rid}/approve", headers=h, json={"notes": ""}, timeout=30)
        requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
        requests.post(f"{API}/sales-returns/{rid}/inspect/complete", headers=h, timeout=30,
                      json={"inspections": [{"index": 0, "defects": [{"point_value": 1, "count": 2}],
                                             "condition": "ok", "accepted_qty": 1}], "notes": "4pt"})
        s = requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30,
                          json={"outcome": "refund", "return_warehouse_id": dest_wh}).json()
        q = requests.get(f"{API}/sales-returns/{rid}/quarantine", headers=h, timeout=30).json()
        if isinstance(q, list) and q:
            return s, q
    return None, []


def main():
    h = login()
    orders = eligible(h)
    whs = as_list(requests.get(f"{API}/warehouses", headers=h, timeout=30))
    suppliers = as_list(requests.get(f"{API}/suppliers", headers=h, timeout=30))
    local_sup = next((s for s in suppliers if (s.get("origin_type") or "local") != "import"), None)
    print(f"== R4 POC == (orders={len(orders)} warehouses={len(whs)} suppliers={len(suppliers)})")
    if not orders or not whs or not local_sup:
        check("prasyarat data (orders + warehouse + supplier lokal)", False); sys.exit(1)
    dest_wh = whs[-1]["id"]

    # ── [1] Chain + RMA accept (ap_credit) ──
    print("\n[1] Chain retur jual→beli + RMA: request→ship→accept(ap_credit)")
    sr, q = make_settled_return(h, orders, dest_wh)
    check("retur jual settled + roll karantina", bool(sr) and bool(q), str(sr)[:100])
    sr_id, roll = sr["id"], q[0]
    cr = requests.post(f"{API}/sales-returns/{sr_id}/create-purchase-return", headers=h, timeout=30,
                       json={"supplier_id": local_sup["id"], "reason": "cacat dari customer"})
    check("create-purchase-return → 200", cr.status_code == 200, f"{cr.status_code} {cr.text[:160]}")
    pr = cr.json() if cr.status_code == 200 else {}
    pr_id = pr.get("id")
    check("PR supplier_flow=True", pr.get("supplier_flow") is True, str(pr.get("supplier_flow")))
    check("PR supplier_status=requested_supplier", pr.get("supplier_status") == "requested_supplier", str(pr.get("supplier_status")))
    check("PR origin_sales_return_id tertaut", pr.get("origin_sales_return_id") == sr_id, str(pr.get("origin_sales_return_id")))
    check("PR origin_sales_return_number terisi", bool(pr.get("origin_sales_return_number")), str(pr.get("origin_sales_return_number")))
    sr_after = requests.get(f"{API}/sales-returns/{sr_id}", headers=h, timeout=30).json()
    check("SR linked_purchase_return_id 2-arah", sr_after.get("linked_purchase_return_id") == pr_id, str(sr_after.get("linked_purchase_return_id")))
    check("SR linked_purchase_return_number", sr_after.get("linked_purchase_return_number") == pr.get("number"), str(sr_after.get("linked_purchase_return_number")))

    ap = requests.post(f"{API}/purchase-returns/{pr_id}/approve", headers=h, timeout=30, json={"notes": ""}).json()
    check("approve (RMA gate) → status approved", ap.get("status") == "approved", str(ap.get("status")))
    check("approve RMA: stok BELUM disesuaikan", ap.get("stock_adjusted") in (False, None), str(ap.get("stock_adjusted")))
    check("approve RMA: supplier_status tetap requested", ap.get("supplier_status") == "requested_supplier", str(ap.get("supplier_status")))
    check("approve RMA: belum ada Nota Debit", not ap.get("debit_note_number"), str(ap.get("debit_note_number")))

    sh = requests.post(f"{API}/purchase-returns/{pr_id}/ship-to-supplier", headers=h, timeout=30,
                       json={"carrier": "JNE", "tracking_no": "TRK1"}).json()
    check("ship-to-supplier → shipped_supplier", sh.get("supplier_status") == "shipped_supplier", str(sh.get("supplier_status")))

    ac = requests.post(f"{API}/purchase-returns/{pr_id}/supplier-accept", headers=h, timeout=30,
                       json={"outcome": "ap_credit"}).json()
    check("supplier-accept → accepted_supplier", ac.get("supplier_status") == "accepted_supplier", str(ac.get("supplier_status")))
    check("accept: supplier_outcome=ap_credit", ac.get("supplier_outcome") == "ap_credit", str(ac.get("supplier_outcome")))
    check("accept: Nota Debit terbit", bool(ac.get("debit_note_number")), str(ac.get("debit_note_number")))
    check("accept: stok disesuaikan", ac.get("stock_adjusted") is True, str(ac.get("stock_adjusted")))
    qroll = requests.get(f"{API}/sales-returns/{sr_id}/quarantine", headers=h, timeout=30).json()
    rr = next((x for x in qroll if x["id"] == roll["id"]), {})
    check("roll dikonsumsi (returned_supplier)", rr.get("status") == "returned_supplier", str(rr.get("status")))

    # ── [2] Supplier reject → goods_back + regrade ──
    print("\n[2] Supplier TOLAK → goods_back + REGRADE A\u2192B (tanpa Nota Debit)")
    sr2, q2 = make_settled_return(h, orders, dest_wh)
    roll2 = q2[0]
    pr2 = requests.post(f"{API}/sales-returns/{sr2['id']}/create-purchase-return", headers=h, timeout=30,
                        json={"supplier_id": local_sup["id"]}).json()
    pr2_id = pr2.get("id")
    requests.post(f"{API}/purchase-returns/{pr2_id}/approve", headers=h, timeout=30, json={})
    requests.post(f"{API}/purchase-returns/{pr2_id}/ship-to-supplier", headers=h, timeout=30, json={})
    rj = requests.post(f"{API}/purchase-returns/{pr2_id}/supplier-reject", headers=h, timeout=30,
                       json={"reason": "kualitas tak sesuai klaim"}).json()
    check("supplier-reject → rejected_supplier", rj.get("supplier_status") == "rejected_supplier", str(rj.get("supplier_status")))
    gb = requests.post(f"{API}/purchase-returns/{pr2_id}/goods-back", headers=h, timeout=30,
                       json={"regrade": [{"roll_id": roll2["id"], "grade": "B"}]}).json()
    check("goods-back → supplier_status=goods_back", gb.get("supplier_status") == "goods_back", str(gb.get("supplier_status")))
    check("goods-back: TANPA Nota Debit", not gb.get("debit_note_number"), str(gb.get("debit_note_number")))
    q2b = requests.get(f"{API}/sales-returns/{sr2['id']}/quarantine", headers=h, timeout=30).json()
    rr2 = next((x for x in q2b if x["id"] == roll2["id"]), {})
    check("roll kembali available", rr2.get("status") == "available", str(rr2.get("status")))
    check("roll regrade → grade B", rr2.get("grade") == "B", str(rr2.get("grade")))
    check("roll regraded_from = A", rr2.get("regraded_from") == "A", str(rr2.get("regraded_from")))

    # ── [3] Kebijakan IMPOR (§J) ──
    print("\n[3] Kebijakan IMPOR (§J): impor & tak-returnable → blok; bypass → lolos")
    imp = requests.post(f"{API}/suppliers", headers=h, timeout=30, json={
        "name": "R4 Import NonReturnable", "origin_type": "import", "country": "CN",
        "return_policy": {"returnable_to_supplier": False, "refund_modes": ["ap_credit"]}}).json()
    imp_id = imp.get("id")
    check("supplier impor dibuat", bool(imp_id), str(imp)[:120])
    prod_id = orders[0]["items"][0]["product_id"]
    blk = requests.post(f"{API}/purchase-returns", headers=h, timeout=30, json={
        "supplier_id": imp_id, "warehouse_id": dest_wh,
        "items": [{"product_id": prod_id, "quantity": 1, "price": 1000, "reason": "cacat"}]})
    check("create retur beli impor → 400 (blok §J)", blk.status_code == 400, f"{blk.status_code} {blk.text[:160]}")
    check("pesan blok sebut regrade/impor", ("regrade" in blk.text.lower() or "impor" in blk.text.lower()), blk.text[:120])
    byp = requests.post(f"{API}/purchase-returns", headers=h, timeout=30, json={
        "supplier_id": imp_id, "warehouse_id": dest_wh, "bypass_import_policy": True,
        "items": [{"product_id": prod_id, "quantity": 1, "price": 1000, "reason": "cacat"}]})
    check("bypass_import_policy=true → 200 (lolos)", byp.status_code == 200, f"{byp.status_code} {byp.text[:160]}")

    # ── [4] Regression alur DIRECT ──
    print("\n[4] Regression alur DIRECT (supplier_flow=false) → approve = stok+DN+GL")
    bals = as_list(requests.get(f"{API}/inventory/balances", headers=h, timeout=30))
    seg = next((b for b in bals if float(b.get("available_qty", 0) or 0) >= 2), None)
    direct_ok = False
    if seg:
        src = requests.get(f"{API}/purchase-returns/source-rolls", headers=h, timeout=30, params={
            "product_id": seg["product_id"], "warehouse_id": seg.get("warehouse_id"),
            "entity_id": seg.get("owner_entity_id")})
        srolls = (src.json().get("rolls") if src.status_code == 200 and isinstance(src.json(), dict) else []) or []
        if srolls:
            rid0 = srolls[0].get("id") or srolls[0].get("roll_id")
            dpr = requests.post(f"{API}/purchase-returns", headers=h, timeout=30, json={
                "supplier_id": local_sup["id"], "warehouse_id": seg.get("warehouse_id"),
                "entity_id": seg.get("owner_entity_id"), "submit_now": True,
                "items": [{"product_id": seg["product_id"], "quantity": 1, "roll_ids": [rid0], "reason": "cacat"}]})
            if dpr.status_code == 200:
                dpr_id = dpr.json()["id"]
                da = requests.post(f"{API}/purchase-returns/{dpr_id}/approve", headers=h, timeout=30, json={}).json()
                check("DIRECT approve → approved", da.get("status") == "approved", str(da.get("status")))
                check("DIRECT approve → Nota Debit terbit", bool(da.get("debit_note_number")), str(da.get("debit_note_number")))
                check("DIRECT approve → stok disesuaikan", da.get("stock_adjusted") is True, str(da.get("stock_adjusted")))
                check("DIRECT supplier_status=accepted_supplier", da.get("supplier_status") == "accepted_supplier", str(da.get("supplier_status")))
                direct_ok = True
                globals()["_DIRECT_PR_ID"] = dpr_id
    if not direct_ok:
        check("prasyarat DIRECT (roll available)", False, "tidak ada roll available untuk uji direct")

    # ── [5] Guards ──
    print("\n[5] Guards transisi RMA")
    # accept sebelum ship
    sr3, q3 = make_settled_return(h, orders, dest_wh)
    pr3 = requests.post(f"{API}/sales-returns/{sr3['id']}/create-purchase-return", headers=h, timeout=30,
                        json={"supplier_id": local_sup["id"]}).json()
    requests.post(f"{API}/purchase-returns/{pr3['id']}/approve", headers=h, timeout=30, json={})
    g1 = requests.post(f"{API}/purchase-returns/{pr3['id']}/supplier-accept", headers=h, timeout=30, json={"outcome": "ap_credit"})
    check("accept sebelum ship → 400", g1.status_code == 400, f"{g1.status_code} {g1.text[:120]}")
    # goods-back sebelum reject (pr3 masih requested)
    g2 = requests.post(f"{API}/purchase-returns/{pr3['id']}/goods-back", headers=h, timeout=30, json={})
    check("goods-back sebelum reject → 400", g2.status_code == 400, f"{g2.status_code} {g2.text[:120]}")
    # ship pada retur DIRECT
    if globals().get("_DIRECT_PR_ID"):
        g3 = requests.post(f"{API}/purchase-returns/{globals()['_DIRECT_PR_ID']}/ship-to-supplier", headers=h, timeout=30, json={})
        check("ship pada retur DIRECT → 400", g3.status_code == 400, f"{g3.status_code} {g3.text[:120]}")

    print(f"\n=== HASIL R4: PASS={PASS}  FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
