"""API test (Fase M3) — Makloon Orders end-to-end via HTTP.
Jalankan: cd /app/backend && python test_makloon_order_api.py
"""
import requests, json, os
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

BASE = "http://localhost:8001/api"
P, F = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
res = {"p": 0, "f": 0}


def chk(name, cond, extra=""):
    res["p" if cond else "f"] += 1
    print(f"  [{P if cond else F}] {name}" + (f"  ({extra})" if extra else ""))
    return cond


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": "demo12345"})
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def _ensure_material_stock(need_kg: float, product_id: str = "prod_benang_katun",
                           warehouse_id: str = "wh_surabaya", entity_id: str = "ent_ksc"):
    """Fixture: pastikan stok bahan cukup (seed menyisakan 40 kg setelah order contoh).

    Tanpa ini skrip gagal karena kekurangan stok — bukan karena bug fitur.
    """
    import asyncio
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    async def _top_up():
        from db import db
        from services.roll_service import create_inbound_roll
        from services import gl_service
        bal = await db.inventory_balances.find_one(
            {"product_id": product_id, "warehouse_id": warehouse_id,
             "owner_entity_id": entity_id}, {"_id": 0}) or {}
        avail = float(bal.get("available_qty") or 0)
        if avail >= need_kg:
            return 0.0
        add = round(need_kg - avail + 5, 2)
        await create_inbound_roll(product_id, warehouse_id, entity_id, add,
                                  lot="QA-TOPUP", unit="kg", acquired_via="initial",
                                  ref_id="qa_makloon_api", unit_cost=51500.0,
                                  created_by="qa")
        # Stok fixture harus ikut ter-jurnal agar GL 1-1300 == subledger roll
        # (kalau tidak, invarian GL-3 memunculkan drift palsu).
        await gl_service.post_inventory_opening_balance(
            actor_name="qa_fixture", tag=f"qa_topup_{int(datetime.now().timestamp())}")
        return add

    added = asyncio.run(_top_up())
    if added:
        print(f"  [fixture] stok bahan ditambah {added} kg agar skenario 50 kg bisa jalan")


def _balances_snapshot(warehouse_id: str = "wh_surabaya", entity_id: str = "ent_ksc"):
    """Saldo awal produk terkait → assert DELTA (bukan absolut) agar tidak flaky."""
    from pymongo import MongoClient
    cli = MongoClient(os.environ["MONGO_URL"])
    mdb = cli[os.environ["DB_NAME"]]

    def _avail(pid):
        b = mdb.inventory_balances.find_one({"product_id": pid, "warehouse_id": warehouse_id,
                                             "owner_entity_id": entity_id}) or {}
        return float(b.get("available_qty") or 0)

    return {"grey": _avail("prod_grey_katun"), "sisa": _avail("prod_benang_sisa")}


def run():
    admin = login("admin@kainnusantara.id")
    wh = login("warehouse@kainnusantara.id")
    sales = login("sales@kainnusantara.id")
    print("\n=== M3 MAKLOON ORDER API TEST ===")
    _ensure_material_stock(50.0)
    BEFORE = _balances_snapshot()

    # ── permission gate ──
    chk("sales GET /makloon-orders → 403",
        requests.get(f"{BASE}/makloon-orders", headers=H(sales)).status_code == 403)
    chk("unauth GET /makloon-orders → 401",
        requests.get(f"{BASE}/makloon-orders").status_code == 401)
    chk("warehouse cannot create (403)",
        requests.post(f"{BASE}/makloon-orders", headers=H(wh), json={
            "material_product_id": "prod_benang_katun", "material_qty": 10,
            "steps": [{"process_type": "tenun"}]}).status_code == 403)

    # ── create (process_only, 1 step Tenun) ──
    payload = {
        "mode": "process_only",
        "material_product_id": "prod_benang_katun",
        "material_qty": 50, "material_unit": "kg",
        "from_warehouse_id": "wh_surabaya", "target_warehouse_id": "wh_surabaya",
        "steps": [{
            "process_type": "tenun", "makloon_id": "mak_seed_tenun",
            "recipe_id": "prcp_seed_tenun",
            "input_product_id": "prod_benang_katun", "output_product_id": "prod_grey_katun",
            "yield_factor": 3.8, "yield_override_reason": "Yield historis mesin ATBM (Fase D)",
            "waste_pct": 4, "byproduct_pct": 2, "tariff": 3500,
        }],
        "notes": "QA order test",
    }
    r = requests.post(f"{BASE}/makloon-orders", headers=H(admin), json=payload)
    chk("admin create order → 200", r.status_code == 200, f"status={r.status_code} {r.text[:150]}")
    if r.status_code != 200:
        return
    order = r.json()
    mko = order["id"]
    chk("order has mko_number", bool(order.get("mko_number")), order.get("mko_number"))
    chk("order status = draft", order.get("status") == "draft", order.get("status"))
    step = order["steps"][0]
    exp_out = step["expected_output_qty"]   # 50*3.8*0.96 = 182.4
    chk("forecast expected_output ≈ 182.4", abs(exp_out - 182.4) < 0.1, f"exp={exp_out}")
    chk("step makloon_name enriched", step.get("makloon_name") == "PT Tenun Nusantara Jaya", step.get("makloon_name"))

    # ── list shows it ──
    lst = requests.get(f"{BASE}/makloon-orders", headers=H(admin)).json()
    chk("list contains new order", any(o["id"] == mko for o in lst), f"count={len(lst)}")

    # ── issue step 1 (warehouse can issue) ──
    r = requests.post(f"{BASE}/makloon-orders/{mko}/issue", headers=H(wh), json={"step_seq": 1})
    chk("warehouse issue step 1 → 200", r.status_code == 200, f"status={r.status_code} {r.text[:150]}")
    if r.status_code == 200:
        o = r.json()
        st = o["steps"][0]
        chk("step status = issued", st.get("status") == "issued", st.get("status"))
        chk("material_value = 50*51500 = 2,575,000", abs(st.get("material_value", 0) - 2575000) < 1,
            f"val={st.get('material_value')}")
        chk("order status = in_process", o.get("status") == "in_process", o.get("status"))

    # subcon qty on benang balance (via stock-buckets? use detail)
    det = requests.get(f"{BASE}/makloon-orders/{mko}", headers=H(admin)).json()
    chk("detail: step subcon_qty = 50", abs(det["steps"][0].get("subcon_qty", 0) - 50) < 0.1,
        f"subcon={det['steps'][0].get('subcon_qty')}")

    # double issue → 409
    chk("re-issue same step → 409",
        requests.post(f"{BASE}/makloon-orders/{mko}/issue", headers=H(admin),
                      json={"step_seq": 1}).status_code == 409)

    # ── receive step 1 (rolls with manual LOT) ──
    # receive missing rolls → 400
    chk("receive without rolls → 400",
        requests.post(f"{BASE}/makloon-orders/{mko}/receive", headers=H(admin),
                      json={"step_seq": 1, "actual_output_qty": 182, "tariff": 637000}).status_code == 400)
    recv = {"step_seq": 1, "actual_output_qty": 182, "actual_byproduct_qty": 1,
            "tariff": 637000, "aux_cost": 0, "ppn": 0,
            "byproduct_lot": "SISA-T1",
            "rolls": [{"lot": "GREY-MKO-1", "length": 100, "grade": "A"},
                      {"lot": "GREY-MKO-2", "length": 82, "grade": "A"}]}
    r = requests.post(f"{BASE}/makloon-orders/{mko}/receive", headers=H(wh), json=recv)
    chk("warehouse receive step 1 → 200", r.status_code == 200, f"status={r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        o = r.json()
        st = o["steps"][0]
        chk("step status = received", st.get("status") == "received", st.get("status"))
        chk("order status = completed", o.get("status") == "completed", o.get("status"))
        wip = 2575000 + 637000            # material + service
        sisa_val = 51500                  # 1 kg benang sisa @ WAC 51,500
        out_val = wip - sisa_val          # output menyerap sisa WIP
        chk("output_value = wip - sisa = 3,160,500", abs(st.get("output_value", 0) - out_val) < 1,
            f"val={st.get('output_value')}")
        chk("byproduct_value = 51,500 (1kg benang sisa @ WAC)", abs(st.get("byproduct_value", 0) - sisa_val) < 1,
            f"by={st.get('byproduct_value')}")
        chk("2 output lots created", len(st.get("lots", [])) == 2, f"lots={len(st.get('lots', []))}")
        c = o.get("costing", {})
        chk("costing hpp_output = 3,160,500", abs(c.get("hpp_output", 0) - out_val) < 1, f"hpp={c.get('hpp_output')}")
        chk("costing byproduct_credit = 51,500", abs(c.get("byproduct_credit", 0) - sisa_val) < 1, f"bc={c.get('byproduct_credit')}")
        chk("costing hpp_per_unit = 3160500/182", abs(c.get("hpp_per_unit", 0) - round(out_val/182, 2)) < 1,
            f"hpp_u={c.get('hpp_per_unit')}")

    # ── grey stock now available (+182) + byproduct roll ──
    from pymongo import MongoClient
    cli = MongoClient(os.environ["MONGO_URL"]); mdb = cli[os.environ["DB_NAME"]]
    grey_avail = mdb.inventory_balances.find_one({"product_id": "prod_grey_katun",
                                                  "warehouse_id": "wh_surabaya", "owner_entity_id": "ent_ksc"})
    # Barang sisa kini produk tersendiri (prod_benang_sisa) → grey = output saja (+182).
    # Assert DELTA (bukan absolut) agar skrip tetap sah pada DB yang sudah dipakai.
    grey_now = float((grey_avail or {}).get("available_qty") or 0)
    chk("grey available bertambah 182 (output saja)", abs((grey_now - BEFORE["grey"]) - 182) < 0.5,
        f"delta={round(grey_now - BEFORE['grey'], 2)}")
    sisa_bal = mdb.inventory_balances.find_one({"product_id": "prod_benang_sisa",
                                                "warehouse_id": "wh_surabaya", "owner_entity_id": "ent_ksc"})
    sisa_now = float((sisa_bal or {}).get("available_qty") or 0)
    chk("benang sisa (produk tersendiri) bertambah 1 kg", abs((sisa_now - BEFORE["sisa"]) - 1) < 0.5,
        f"delta={round(sisa_now - BEFORE['sisa'], 2)}")
    # FASE C — `roll.lot` kini berisi NOMOR LOT resmi; kode lot manual tersimpan di
    # `inventory_lots.legacy_lot_codes` → cari roll sisa lewat lot tersebut.
    lot_doc = mdb.inventory_lots.find_one({"legacy_lot_codes": "SISA-T1",
                                           "product_id": "prod_benang_sisa"})
    remnant = mdb.inventory_rolls.count_documents(
        {"is_remnant": True, "product_id": "prod_benang_sisa",
         "lot_id": (lot_doc or {}).get("id", "-")})
    chk("byproduct remnant roll created on benang_sisa", remnant >= 1, f"count={remnant}")

    # ── scorecard now has_data ──
    sc = requests.get(f"{BASE}/makloons/mak_seed_tenun/scorecard", headers=H(admin)).json()
    chk("scorecard has_data = true", sc.get("has_data") is True, f"has_data={sc.get('has_data')}")
    m = sc.get("metrics", {})
    chk("scorecard realized_yield ≈ 182/50 = 3.64", m.get("realized_yield") and abs(m["realized_yield"] - 3.64) < 0.05,
        f"yield={m.get('realized_yield')}")

    # ── Makloon 360 shows order + service bill ──
    m360 = requests.get(f"{BASE}/makloons/mak_seed_tenun", headers=H(admin)).json()
    chk("Makloon 360 order_count >= 1", m360.get("order_count", 0) >= 1, f"count={m360.get('order_count')}")
    chk("Makloon 360 service_bills >= 1", len(m360.get("service_bills", [])) >= 1,
        f"bills={len(m360.get('service_bills', []))}")

    # ── GL balanced for subcon sources ──
    jes = list(mdb.journal_entries.find({"source_type": {"$in": ["subcon_issue", "subcon_service", "subcon_receipt"]},
                                         "source_id": {"$regex": mko}}))
    # service source_id is bill id; fetch separately
    bills = list(mdb.vendor_bills.find({"makloon_order_id": mko}))
    for b in bills:
        jes += list(mdb.journal_entries.find({"source_type": "subcon_service", "source_id": b["id"]}))
    allbal = all(abs(je.get("total_debit", 0) - je.get("total_credit", 0)) < 0.01 for je in jes)
    chk("all subcon JE balanced", allbal and len(jes) >= 3, f"je_count={len(jes)}")
    # WIP net 0
    wip_delta = 0.0
    for je in jes:
        for l in je.get("lines", []):
            if l.get("account_code") == "1-1350":
                wip_delta += float(l.get("debit", 0) or 0) - float(l.get("credit", 0) or 0)
    chk("WIP 1-1350 net = 0", abs(wip_delta) < 0.01, f"delta={round(wip_delta,2)}")

    # ── cancel a fresh order (draft) ──
    r2 = requests.post(f"{BASE}/makloon-orders", headers=H(admin), json=payload)
    mko2 = r2.json()["id"]
    rc = requests.post(f"{BASE}/makloon-orders/{mko2}/cancel", headers=H(admin), json={"reason": "test batal"})
    chk("cancel draft order → 200", rc.status_code == 200, f"status={rc.status_code}")
    chk("cancelled status", rc.json().get("status") == "cancelled", rc.json().get("status"))
    # cannot cancel completed
    chk("cancel completed order → 409",
        requests.post(f"{BASE}/makloon-orders/{mko}/cancel", headers=H(admin), json={"reason": "x"}).status_code == 409)

    cli.close()
    print(f"\n=== HASIL: {res['p']} PASS / {res['f']} FAIL ===\n")


if __name__ == "__main__":
    run()
