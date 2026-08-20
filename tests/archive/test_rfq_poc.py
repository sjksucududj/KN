#!/usr/bin/env python3
"""
POC ISOLASI — P1: RFQ / Quotation (sourcing) — Phase 6.1
========================================================
Membuktikan core SEBELUM frontend:

  A. Create RFQ manual (2 item, 2 supplier diundang) → status draft.
  B. Send → open; Quote supplier A & B (harga silang) → status open, total dihitung.
  C. Compare: lowest_per_line benar, total per supplier, recommended_full benar.
  D. Award FULL → 1 PO terbuat (harga supplier menang) + supplier_price_lists upsert.
  E. Award PER-LINE (RFQ ke-2) → 2 PO (split per supplier) + price-list upsert.
  F. Create RFQ dari PR approved (tarik item) → award full → PR jadi 'converted'.
  G. Guard: award ulang → 409.

Isolated: bikin data via API NYATA, assert via DB + cross-endpoint. Idempotent (cleanup).
"""
import asyncio, os, sys, requests
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE = os.environ.get("BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"
MONGO_URL = os.environ["MONGO_URL"]; DB_NAME = os.environ["DB_NAME"]
ENTITY = "ent_ksc"; WH = "wh_jakarta"

PASS, FAIL = [], []
def ok(m): PASS.append(m); print(f"  \u2705 [PASS] {m}")
def bad(m): FAIL.append(m); print(f"  \u274c [FAIL] {m}")
def info(m): print(f"  \u2139  {m}")


def login(email="admin@kainnusantara.id"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "demo12345"}, timeout=30)
    r.raise_for_status(); return r.json()["token"]


async def pick_fixtures(db):
    sups = await db.suppliers.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(10)
    prods = await db.products.find({}, {"_id": 0, "id": 1, "sku": 1}).to_list(10)
    return sups[:2], prods[:2]


async def cleanup(db):
    rfqs = await db.rfqs.find({"title": {"$regex": "RFQPOC"}}, {"_id": 0, "award": 1}).to_list(50)
    po_ids = []
    for r in rfqs:
        po_ids += (r.get("award") or {}).get("po_ids", [])
    if po_ids:
        await db.purchase_orders.delete_many({"id": {"$in": po_ids}})
        await db.wms_tasks.delete_many({"source_id": {"$in": po_ids}})
    await db.rfqs.delete_many({"title": {"$regex": "RFQPOC"}})
    await db.supplier_price_lists.delete_many({"notes": "Auto dari RFQ award", "source": "rfq_award",
                                               "created_by": {"$in": ["Budi Santoso", "Admin"]}})
    await db.purchase_requisitions.delete_many({"reason": {"$regex": "RFQPOC"}})


def create_rfq(s, items, supplier_ids, title, source="manual", pr_id=""):
    body = {"source": source, "pr_id": pr_id, "title": title, "entity_id": ENTITY,
            "warehouse_id": WH, "items": items, "supplier_ids": supplier_ids,
            "needed_by_date": "2099-02-01T00:00:00+00:00"}
    return s.post(f"{API}/rfqs", json=body, timeout=30)


async def main():
    client = AsyncIOMotorClient(MONGO_URL); db = client[DB_NAME]
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {login()}"})
    ok("Login admin")
    await cleanup(db)
    (supA, supB), (p1, p2) = await pick_fixtures(db)
    info(f"Fixtures: supA={supA['name']} supB={supB['name']} | p1={p1['sku']} p2={p2['sku']}")

    # ── A. Create manual ──────────────────────────────────────────────────
    info("TEST A: Create RFQ manual (2 item, 2 supplier)")
    items = [{"product_id": p1["id"], "quantity": 100, "unit": "meter"},
             {"product_id": p2["id"], "quantity": 50, "unit": "meter"}]
    ra = create_rfq(s, items, [supA["id"], supB["id"]], "RFQPOC-manual-1")
    if ra.status_code != 200:
        bad(f"create gagal: {ra.status_code} {ra.text[:200]}"); await _finish(client); return
    rfq = ra.json(); rid = rfq["id"]
    line_ids = [it["line_id"] for it in rfq["items"]]
    if rfq["status"] == "draft" and len(rfq["items"]) == 2 and len(rfq["suppliers"]) == 2:
        ok(f"RFQ {rfq['rfq_number']} draft, 2 item, 2 supplier")
    else:
        bad(f"struktur RFQ salah: {rfq.get('status')}/{len(rfq.get('items',[]))}/{len(rfq.get('suppliers',[]))}")

    # ── B. Send + Quote ───────────────────────────────────────────────────
    info("TEST B: Send → open; Quote A & B (harga silang)")
    rs = s.post(f"{API}/rfqs/{rid}/send", timeout=30)
    ok("Send → open") if rs.status_code == 200 and rs.json()["status"] == "open" else bad(f"send: {rs.status_code}")
    # A murah di p1 (10000) mahal p2 (25000); B mahal p1 (12000) murah p2 (20000)
    qa = s.post(f"{API}/rfqs/{rid}/quote", json={"supplier_id": supA["id"], "lead_time_days": 7,
        "lines": [{"line_id": line_ids[0], "price": 10000}, {"line_id": line_ids[1], "price": 25000}]}, timeout=30)
    qb = s.post(f"{API}/rfqs/{rid}/quote", json={"supplier_id": supB["id"], "lead_time_days": 10,
        "lines": [{"line_id": line_ids[0], "price": 12000}, {"line_id": line_ids[1], "price": 20000}]}, timeout=30)
    if qa.status_code == 200 and qb.status_code == 200:
        rj = qb.json()
        sa = next(x for x in rj["suppliers"] if x["supplier_id"] == supA["id"])
        sb = next(x for x in rj["suppliers"] if x["supplier_id"] == supB["id"])
        # A total = 10000*100 + 25000*50 = 2,250,000 ; B = 12000*100 + 20000*50 = 2,200,000
        if abs(sa["total"] - 2250000) < 1 and abs(sb["total"] - 2200000) < 1:
            ok("Total penawaran A=2.250.000 B=2.200.000 benar")
        else:
            bad(f"total salah: A={sa['total']} B={sb['total']}")
    else:
        bad(f"quote gagal: A={qa.status_code} B={qb.status_code} {qa.text[:120]}")

    # ── C. Compare ────────────────────────────────────────────────────────
    info("TEST C: Compare matriks + lowest + recommended")
    rc = s.get(f"{API}/rfqs/{rid}/compare", timeout=30)
    if rc.status_code == 200:
        cmp = rc.json()
        lpl = cmp["lowest_per_line"]
        ok("Lowest p1 → A") if lpl[line_ids[0]]["supplier_id"] == supA["id"] else bad(f"lowest p1 salah: {lpl[line_ids[0]]}")
        ok("Lowest p2 → B") if lpl[line_ids[1]]["supplier_id"] == supB["id"] else bad(f"lowest p2 salah: {lpl[line_ids[1]]}")
        # recommended_full = total terendah lengkap = B (2.2jt)
        ok("Recommended full → B (total terendah)") if cmp["recommended_full_supplier_id"] == supB["id"] else bad(f"recommended salah: {cmp['recommended_full_supplier_id']}")
        # per-line recommendation: p1→A, p2→B
        la = {x["line_id"]: x["supplier_id"] for x in cmp["recommended_line_awards"]}
        ok("Recommended line awards p1→A p2→B") if la.get(line_ids[0]) == supA["id"] and la.get(line_ids[1]) == supB["id"] else bad(f"line awards salah: {la}")
    else:
        bad(f"compare gagal: {rc.status_code}")

    # ── D. Award FULL → 1 PO + price-list ─────────────────────────────────
    info("TEST D: Award FULL ke B → 1 PO + price-list upsert")
    rd = s.post(f"{API}/rfqs/{rid}/award", json={"mode": "full", "full_supplier_id": supB["id"]}, timeout=30)
    if rd.status_code == 200:
        res = rd.json()
        pos = res.get("pos", [])
        if len(pos) == 1 and res["rfq"]["status"] == "awarded":
            ok(f"Award full → 1 PO {pos[0]['po_number']}, RFQ awarded")
            # PO grand-total mengandung harga B
            po = pos[0]
            ok("PO.source_rfq_id terisi") if po.get("source_rfq_id") == rid else bad("source_rfq_id kosong")
            # price-list upsert utk B/p1
            spl = await db.supplier_price_lists.find_one({"supplier_id": supB["id"], "product_id": p1["id"], "source": "rfq_award"}, {"_id": 0})
            ok("Price-list upsert B/p1 (rfq_award)") if spl and abs(float(spl["price"]) - 12000) < 1 else bad(f"price-list upsert gagal: {spl}")
        else:
            bad(f"award full salah: pos={len(pos)} status={res['rfq']['status']}")
    else:
        bad(f"award full gagal: {rd.status_code} {rd.text[:200]}")

    # ── E. Award PER-LINE → 2 PO ──────────────────────────────────────────
    info("TEST E: RFQ ke-2 → Award PER-LINE (p1→A, p2→B) → 2 PO")
    r2 = create_rfq(s, items, [supA["id"], supB["id"]], "RFQPOC-manual-2")
    rid2 = r2.json()["id"]; lids2 = [it["line_id"] for it in r2.json()["items"]]
    s.post(f"{API}/rfqs/{rid2}/send", timeout=30)
    s.post(f"{API}/rfqs/{rid2}/quote", json={"supplier_id": supA["id"],
        "lines": [{"line_id": lids2[0], "price": 10000}, {"line_id": lids2[1], "price": 25000}]}, timeout=30)
    s.post(f"{API}/rfqs/{rid2}/quote", json={"supplier_id": supB["id"],
        "lines": [{"line_id": lids2[0], "price": 12000}, {"line_id": lids2[1], "price": 20000}]}, timeout=30)
    la_body = {"mode": "line", "line_awards": [
        {"line_id": lids2[0], "supplier_id": supA["id"]},
        {"line_id": lids2[1], "supplier_id": supB["id"]}]}
    re = s.post(f"{API}/rfqs/{rid2}/award", json=la_body, timeout=30)
    if re.status_code == 200:
        pos = re.json().get("pos", [])
        sids = {p["supplier_id"] for p in pos}
        if len(pos) == 2 and sids == {supA["id"], supB["id"]}:
            ok("Award per-line → 2 PO (split A & B)")
        else:
            bad(f"per-line salah: pos={len(pos)} sids={sids}")
    else:
        bad(f"award per-line gagal: {re.status_code} {re.text[:200]}")

    # ── F. RFQ dari PR approved ───────────────────────────────────────────
    info("TEST F: RFQ dari PR approved → award full → PR converted")
    pr = s.post(f"{API}/purchase-requisitions", json={"items": [
        {"product_id": p1["id"], "quantity": 80, "unit": "meter", "est_price": 11000}],
        "warehouse_id": WH, "entity_id": ENTITY, "reason": "RFQPOC kebutuhan",
        "submit_now": True}, timeout=30)
    if pr.status_code != 200:
        bad(f"PR create gagal: {pr.status_code} {pr.text[:150]}")
    else:
        prd = pr.json(); prid = prd["id"]
        if prd["status"] != "approved":
            s.post(f"{API}/purchase-requisitions/{prid}/approve", json={}, timeout=30)
        rpr = create_rfq(s, [], [supA["id"], supB["id"]], "RFQPOC-from-pr", source="pr", pr_id=prid)
        if rpr.status_code == 200 and len(rpr.json()["items"]) == 1:
            ok("RFQ dari PR menarik 1 item")
            ridp = rpr.json()["id"]; lidp = rpr.json()["items"][0]["line_id"]
            s.post(f"{API}/rfqs/{ridp}/send", timeout=30)
            s.post(f"{API}/rfqs/{ridp}/quote", json={"supplier_id": supA["id"], "lines": [{"line_id": lidp, "price": 10500}]}, timeout=30)
            aw = s.post(f"{API}/rfqs/{ridp}/award", json={"mode": "full", "full_supplier_id": supA["id"]}, timeout=30)
            prx = await db.purchase_requisitions.find_one({"id": prid}, {"_id": 0, "status": 1, "po_id": 1})
            if aw.status_code == 200 and prx["status"] == "converted" and prx.get("po_id"):
                ok("Award → PR jadi 'converted' + po_id terisi")
            else:
                bad(f"PR konversi gagal: aw={aw.status_code} status={prx['status']}")
        else:
            bad(f"RFQ dari PR gagal: {rpr.status_code} {rpr.text[:150]}")

    # ── G. Guard award ulang ──────────────────────────────────────────────
    info("TEST G: Award ulang RFQ-1 → 409")
    rg = s.post(f"{API}/rfqs/{rid}/award", json={"mode": "full", "full_supplier_id": supB["id"]}, timeout=30)
    ok("Award ulang → 409") if rg.status_code == 409 else bad(f"harus 409, dapat {rg.status_code}")

    await cleanup(db)
    await _finish(client)


async def _finish(client):
    client.close()
    print("\n" + "=" * 64)
    print(f"  SUMMARY: {len(PASS)} PASS | {len(FAIL)} FAIL")
    print("=" * 64)
    if FAIL:
        print("\n\u274c FAILED:")
        for f in FAIL: print(f"  - {f}")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0 if not FAIL else 1)
