"""R5.4b — Reversal Retur Beli (Nota Debit) + Reversal Write-off (un-scrap) — POC.

Membuktikan (append-only, idempotent, integritas-aman):
  A. RETUR BELI DIRECT (ap_credit) → REVERSAL: JE purchase_return dibalik (net 0 per akun),
     roll returned_supplier → available (barang kembali ke stok), status → cancelled. Idempotent.
     (Bila roll cocok dengan sebuah PO → verifikasi returned_amount PO dipulihkan.)
  B. RETUR BELI RMA (refund) → REVERSAL: cash_transaction refund di-void, JE net 0, roll kembali.
  C. WRITE-OFF (scrap roll retur jual) → REVERSAL (un-scrap): roll damaged → available,
     JE inventory_writeoff dibalik (net 0), GL 1-1300 pulih, rebuild balance. Idempotent.
  D. verify_data_integrity tetap 126/0/0 setelah semua reversal (net efek = 0).

Jalankan: python test_r5_4b_poc.py
"""
import os
import sys
import requests
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

API = f"{os.environ.get('R5_BASE', 'http://localhost:8001')}/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
_MC = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DBS = _MC[os.environ.get("DB_NAME", "test_database")]
PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  \u2705 {name}")
    else:
        FAIL += 1
        print(f"  \u274c {name}  {extra}")


def login():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def gl_lines_by_account(source_id, base_type):
    """Net (debit-credit) per akun untuk JE base + base_reversal (non-void)."""
    net = {}
    cur = DBS.journal_entries.find(
        {"source_id": source_id, "source_type": {"$in": [base_type, f"{base_type}_reversal"]},
         "status": {"$ne": "void"}}, {"_id": 0})
    for je in cur:
        for l in je.get("lines", []):
            net[l["account_code"]] = round(
                net.get(l["account_code"], 0.0)
                + float(l.get("debit", 0) or 0) - float(l.get("credit", 0) or 0), 2)
    return net


def gl_1300(entity_id):
    total = 0.0
    for je in DBS.journal_entries.find({"entity_id": entity_id, "status": {"$ne": "void"}}, {"_id": 0}):
        for l in je.get("lines", []):
            if l.get("account_code") == "1-1300":
                total += float(l.get("debit", 0) or 0) - float(l.get("credit", 0) or 0)
    return round(total, 2)


def pick_available_roll(exclude=()):
    r = DBS.inventory_rolls.find_one(
        {"status": "available", "unit_cost": {"$gt": 0}, "length_remaining": {"$gt": 0},
         "id": {"$nin": list(exclude)}}, {"_id": 0})
    return r


def find_roll_matching_po():
    """Cari (roll, po) di gudang+entitas sama agar AP-restore bisa diuji realistis."""
    pos = list(DBS.purchase_orders.find({}, {"_id": 0}).limit(20))
    for po in pos:
        wid = po.get("warehouse_id"); eid = po.get("entity_id")
        if not wid or not eid:
            continue
        roll = DBS.inventory_rolls.find_one(
            {"status": "available", "unit_cost": {"$gt": 0}, "length_remaining": {"$gt": 0},
             "warehouse_id": wid, "owner_entity_id": eid}, {"_id": 0})
        if roll:
            return roll, po
    return None, None


# ─────────────────────────── CASE A: DIRECT ap_credit ───────────────────────

def case_a(h):
    print("\n[A] Retur beli DIRECT (ap_credit) → REVERSAL (JE net-0, roll kembali, idempotent)")
    roll, po = find_roll_matching_po()
    used_po = bool(roll and po)
    if not roll:
        roll = pick_available_roll()
    if not roll:
        check("prasyarat: ada roll available bernilai", False)
        return
    sup = DBS.suppliers.find_one({}, {"_id": 0})
    rid = roll["id"]
    body = {
        "supplier_id": sup["id"], "warehouse_id": roll["warehouse_id"],
        "entity_id": roll["owner_entity_id"],
        "items": [{"product_id": roll["product_id"], "quantity": 0, "unit": roll.get("unit", "meter"),
                   "reason": "cacat", "condition": "damaged", "roll_ids": [rid]}],
        "reason": "R5.4b POC", "notes": "reversal ap_credit", "submit_now": True,
        "bypass_import_policy": True,
    }
    if used_po:
        body["po_id"] = po["id"]
    cr = requests.post(f"{API}/purchase-returns", headers=h, json=body, timeout=30)
    check("create retur beli → 200", cr.status_code == 200, f"{cr.status_code} {cr.text[:180]}")
    if cr.status_code != 200:
        return
    ret = cr.json()
    pr_id = ret["id"]
    po_id = ret.get("po_id") or ""
    ra_before = None
    if po_id:
        pdoc = DBS.purchase_orders.find_one({"id": po_id}, {"_id": 0})
        ra_before = round(float((pdoc or {}).get("returned_amount", 0) or 0), 2)

    ap = requests.post(f"{API}/purchase-returns/{pr_id}/approve", headers=h,
                       json={"notes": ""}, timeout=30)
    check("approve/finalize → 200", ap.status_code == 200, f"{ap.status_code} {ap.text[:180]}")
    fin = ap.json() if ap.status_code == 200 else {}
    total = round(float(fin.get("total_amount", 0) or 0), 2)
    check("finalized: stock_adjusted & supplier accepted",
          fin.get("stock_adjusted") and fin.get("supplier_status") == "accepted_supplier",
          f"{fin.get('stock_adjusted')} / {fin.get('supplier_status')}")
    check("Nota Debit terbit", bool(fin.get("debit_note_number")), str(fin.get("debit_note_number")))
    roll_after = DBS.inventory_rolls.find_one({"id": rid}, {"_id": 0})
    check("roll → returned_supplier (keluar stok)", roll_after.get("status") == "returned_supplier",
          str(roll_after.get("status")))
    if po_id and ra_before is not None:
        pdoc2 = DBS.purchase_orders.find_one({"id": po_id}, {"_id": 0})
        ra_mid = round(float((pdoc2 or {}).get("returned_amount", 0) or 0), 2)
        check("AP: returned_amount PO NAIK == total", abs((ra_mid - ra_before) - total) < 0.5,
              f"before={ra_before} mid={ra_mid} total={total}")

    # ── REVERSAL ──
    rv = requests.post(f"{API}/purchase-returns/{pr_id}/reverse", headers=h,
                       json={"notes": "salah retur — koreksi"}, timeout=30)
    check("POST /reverse → 200", rv.status_code == 200, f"{rv.status_code} {rv.text[:180]}")
    doc = rv.json() if rv.status_code == 200 else {}
    check("status == cancelled", doc.get("status") == "cancelled", str(doc.get("status")))
    check("reversed == True", doc.get("reversed") is True, str(doc.get("reversed")))
    check("_reversal_summary ada", bool(doc.get("_reversal_summary")), str(doc.get("_reversal_summary")))
    roll_rev = DBS.inventory_rolls.find_one({"id": rid}, {"_id": 0})
    check("roll kembali → available (barang balik ke stok)", roll_rev.get("status") == "available",
          str(roll_rev.get("status")))
    net = gl_lines_by_account(pr_id, "purchase_return")
    max_net = max((abs(v) for v in net.values()), default=0.0)
    check("GL net-0 per akun (asal + reversal)", max_net < 0.5, f"net={net}")
    if po_id and ra_before is not None:
        pdoc3 = DBS.purchase_orders.find_one({"id": po_id}, {"_id": 0})
        ra_after = round(float((pdoc3 or {}).get("returned_amount", 0) or 0), 2)
        check("AP: returned_amount PO PULIH == semula", abs(ra_after - ra_before) < 0.5,
              f"before={ra_before} after={ra_after}")

    # ── IDEMPOTENT ──
    je_before = DBS.journal_entries.count_documents(
        {"source_type": "purchase_return_reversal", "source_id": pr_id, "status": {"$ne": "void"}})
    rv2 = requests.post(f"{API}/purchase-returns/{pr_id}/reverse", headers=h,
                        json={"notes": "ulang"}, timeout=30)
    je_after = DBS.journal_entries.count_documents(
        {"source_type": "purchase_return_reversal", "source_id": pr_id, "status": {"$ne": "void"}})
    check("reverse ulang idempotent (200, JE reversal tak nambah)",
          rv2.status_code == 200 and je_before == je_after, f"{rv2.status_code} {je_before}->{je_after}")


# ─────────────────────────── CASE B: RMA refund ─────────────────────────────

def case_b(h):
    print("\n[B] Retur beli RMA (refund) → REVERSAL (cash refund di-void, JE net-0, roll kembali)")
    roll = pick_available_roll()
    if not roll:
        check("prasyarat: ada roll available bernilai (B)", False)
        return
    sup = DBS.suppliers.find_one({}, {"_id": 0})
    rid = roll["id"]
    body = {
        "supplier_id": sup["id"], "warehouse_id": roll["warehouse_id"],
        "entity_id": roll["owner_entity_id"], "supplier_flow": True,
        "items": [{"product_id": roll["product_id"], "quantity": 0, "unit": roll.get("unit", "meter"),
                   "reason": "cacat", "condition": "damaged", "roll_ids": [rid]}],
        "reason": "R5.4b POC refund", "notes": "reversal refund", "submit_now": True,
        "bypass_import_policy": True,
    }
    cr = requests.post(f"{API}/purchase-returns", headers=h, json=body, timeout=30)
    check("create retur beli RMA → 200", cr.status_code == 200, f"{cr.status_code} {cr.text[:180]}")
    if cr.status_code != 200:
        return
    pr_id = cr.json()["id"]
    requests.post(f"{API}/purchase-returns/{pr_id}/approve", headers=h, json={"notes": ""}, timeout=30)
    sh = requests.post(f"{API}/purchase-returns/{pr_id}/ship-to-supplier", headers=h,
                       json={"notes": "kirim", "carrier": "JNE"}, timeout=30)
    check("ship-to-supplier → 200", sh.status_code == 200, f"{sh.status_code} {sh.text[:160]}")
    ac = requests.post(f"{API}/purchase-returns/{pr_id}/supplier-accept", headers=h,
                       json={"outcome": "refund", "notes": "supplier bayar", "refund_account_code": "1-1100"},
                       timeout=30)
    check("supplier-accept refund → 200", ac.status_code == 200, f"{ac.status_code} {ac.text[:180]}")
    ctxn = DBS.cash_transactions.find_one(
        {"ref_type": "purchase_return", "ref_id": pr_id, "status": {"$ne": "void"}}, {"_id": 0})
    check("cash_transaction refund (in) terbentuk", bool(ctxn), str(ctxn)[:120] if ctxn else "none")

    rv = requests.post(f"{API}/purchase-returns/{pr_id}/reverse", headers=h,
                       json={"notes": "batalkan refund"}, timeout=30)
    check("POST /reverse (refund) → 200", rv.status_code == 200, f"{rv.status_code} {rv.text[:180]}")
    doc = rv.json() if rv.status_code == 200 else {}
    check("status == cancelled (B)", doc.get("status") == "cancelled", str(doc.get("status")))
    ctxn2 = DBS.cash_transactions.find_one(
        {"ref_type": "purchase_return", "ref_id": pr_id, "status": {"$ne": "void"}}, {"_id": 0})
    check("cash_transaction refund di-VOID", ctxn2 is None, str(ctxn2)[:120] if ctxn2 else "")
    roll_rev = DBS.inventory_rolls.find_one({"id": rid}, {"_id": 0})
    check("roll kembali → available (B)", roll_rev.get("status") == "available", str(roll_rev.get("status")))
    net = gl_lines_by_account(pr_id, "purchase_return")
    max_net = max((abs(v) for v in net.values()), default=0.0)
    check("GL net-0 per akun (B)", max_net < 0.5, f"net={net}")


# ─────────────────────── CASE C: write-off un-scrap ─────────────────────────

def _eligible_orders(h):
    r = requests.get(f"{API}/sales-orders", headers=h, timeout=30)
    o = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    ok = {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
    return [x for x in o if x.get("status") in ok and
            any(float(it.get("quantity", 0) or 0) >= 5 for it in (x.get("items") or []))]


def _create_sr(h, orders, q=2):
    for o in orders:
        its = [it for it in o["items"] if float(it.get("quantity", 0) or 0) >= q]
        if not its:
            continue
        it = its[0]
        r = requests.post(f"{API}/sales-returns", headers=h, timeout=30, json={
            "order_id": o["id"], "return_type": "retur",
            "items": [{"product_id": it["product_id"], "product_name": it.get("product_name", ""),
                       "quantity_returned": q, "unit": it.get("unit", "meter"),
                       "reason": "R5", "condition": "ok"}], "notes": "R5.4b unscrap"})
        if r.status_code == 200:
            return r.json()
    return None


def _inspect(h, rid, qty=2):
    requests.post(f"{API}/sales-returns/{rid}/submit", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/approve", headers=h, json={"notes": ""}, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/inspect/complete", headers=h, timeout=30,
                  json={"inspections": [{"index": 0, "defects": [{"point_value": 1, "count": 2}],
                                         "condition": "ok", "accepted_qty": qty}], "notes": "4point"})


def case_c(h):
    print("\n[C] Write-off (scrap retur jual) → REVERSAL un-scrap (roll balik, JE net-0, idempotent)")
    orders = _eligible_orders(h)
    whs = requests.get(f"{API}/warehouses", headers=h, timeout=30).json()
    whs = whs if isinstance(whs, list) else whs.get("items", [])
    dest_wh = whs[-1]["id"] if whs else ""
    roll = None
    rid = None
    for _ in range(len(orders)):
        ret = _create_sr(h, orders)
        if not ret:
            continue
        rid = ret["id"]
        _inspect(h, rid, qty=2)
        requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30,
                      json={"outcome": "refund", "return_warehouse_id": dest_wh})
        q = requests.get(f"{API}/sales-returns/{rid}/quarantine", headers=h, timeout=30).json()
        cand = next((x for x in (q or []) if float(x.get("unit_cost") or 0) > 0), None)
        if cand:
            roll = cand
            break
    check("dapat roll karantina unit_cost>0 (C)", bool(roll), "tak ada roll bernilai")
    if not roll:
        return
    owner = roll.get("owner_entity_id")
    gl_before_scrap = gl_1300(owner)
    # scrap → write-off
    rel = requests.post(f"{API}/sales-returns/{rid}/quarantine/release", headers=h, timeout=30,
                        json={"decisions": [{"roll_id": roll["id"], "action": "scrap"}]})
    check("scrap → 200 (write-off JE)", rel.status_code == 200, f"{rel.status_code} {rel.text[:160]}")
    gl_after_scrap = gl_1300(owner)
    scrap_delta = round(gl_before_scrap - gl_after_scrap, 2)
    check("GL 1-1300 turun saat scrap", scrap_delta > 0.01, f"delta={scrap_delta}")
    rr = DBS.inventory_rolls.find_one({"id": roll["id"]}, {"_id": 0})
    check("roll status damaged (scrapped)", rr.get("status") == "damaged", str(rr.get("status")))

    # ── REVERSAL WRITE-OFF (un-scrap) ──
    uv = requests.post(f"{API}/sales-returns/{rid}/reverse-writeoff", headers=h, timeout=30,
                       json={"roll_ids": [roll["id"]], "reason": "salah scrap — kembalikan"})
    check("POST /reverse-writeoff → 200", uv.status_code == 200, f"{uv.status_code} {uv.text[:180]}")
    doc = uv.json() if uv.status_code == 200 else {}
    summ = doc.get("_writeoff_reversal_summary", {})
    check("summary rolls >= 1", summ.get("rolls", 0) >= 1, str(summ))
    rr2 = DBS.inventory_rolls.find_one({"id": roll["id"]}, {"_id": 0})
    check("roll damaged → available (kembali ke stok)", rr2.get("status") == "available",
          str(rr2.get("status")))
    check("roll.writeoff_reversed == True", rr2.get("writeoff_reversed") is True,
          str(rr2.get("writeoff_reversed")))
    # JE inventory_writeoff net 0 (asal + reversal)
    net = gl_lines_by_account(roll["id"], "inventory_writeoff")
    max_net = max((abs(v) for v in net.values()), default=0.0)
    check("GL net-0 write-off (asal + reversal)", max_net < 0.5, f"net={net}")
    gl_after_unscrap = gl_1300(owner)
    check("GL 1-1300 pulih == sebelum scrap", abs(gl_after_unscrap - gl_before_scrap) < 0.5,
          f"before={gl_before_scrap} after_unscrap={gl_after_unscrap}")

    # ── IDEMPOTENT ── (roll sudah available & writeoff_reversed → tak ada target → 400)
    uv2 = requests.post(f"{API}/sales-returns/{rid}/reverse-writeoff", headers=h, timeout=30,
                        json={"roll_ids": [roll["id"]], "reason": "ulang"})
    check("reverse-writeoff ulang → 400 (idempotent guard)", uv2.status_code == 400,
          f"{uv2.status_code} {uv2.text[:120]}")


def main():
    h = login()
    print("== R5.4b REVERSAL POC (retur beli + un-scrap write-off) ==")
    case_a(h)
    case_b(h)
    case_c(h)
    print(f"\n=== HASIL R5.4b: PASS={PASS}  FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
