"""POC P2 — Blanket / Contract PO (call-off).

Membuktikan endpoint blanket + call-off sesuai keputusan owner:
  - 1.c : komitmen = kuantitas per item + plafon nilai (GROSS Rp).
  - 2.a : tiap call-off = PO anak (po_type='call_off', approval + receiving normal).
  - 3.b : harga call-off boleh override (alasan WAJIB + audit).
  - 4.b : call-off melebihi sisa (qty/nilai) DIIZINKAN tapi WAJIB approval.
  - 5.a : kontrak kadaluarsa / qty / nilai habis / ditutup → call-off baru DITOLAK.
  - Drawdown LIVE: cancel call-off mengembalikan sisa.

E2E API NYATA (backend :8001). Data sandbox dibersihkan di akhir.
"""
import asyncio
import os
import sys
from datetime import date, timedelta

import httpx

sys.path.insert(0, "/app/backend")
from db import db  # noqa: E402

BASE = "http://localhost:8001/api"
PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} — {detail}")


def approx(a, b, tol=0.5):
    return abs(float(a) - float(b)) <= tol


async def login(client, email="admin@kainnusantara.id"):
    r = await client.post(f"{BASE}/auth/login", json={"email": email, "password": "demo12345"})
    return r.json()["token"]


async def make_product(client, H, suffix, price=50000):
    sku = f"POC-BLK-{os.getpid()}-{suffix}"
    r = await client.post(f"{BASE}/products", headers=H, json={
        "sku": sku, "name": f"POC Blanket Kain {suffix}", "category": "Kain",
        "base_unit": "meter", "price": price, "harga_pokok": 30000})
    return r.json()


async def make_blanket(client, H, wh, items, cap=0.0, valid_until="", valid_from=None):
    return await client.post(f"{BASE}/purchase-orders/blanket", headers=H, json={
        "supplier_name": "POC Supplier Blanket", "warehouse_id": wh,
        "items": items, "contract_value_cap": cap,
        "valid_from": valid_from if valid_from is not None else date.today().isoformat(),
        "valid_until": valid_until, "notes": "kontrak POC"})


async def call_off(client, H, blanket_id, items, override_reason="", **kw):
    body = {"items": items, "price_override_reason": override_reason}
    body.update(kw)
    return await client.post(f"{BASE}/purchase-orders/{blanket_id}/call-off", headers=H, json=body)


async def get_po(client, H, po_id):
    return (await client.get(f"{BASE}/purchase-orders/{po_id}", headers=H)).json()


def find_item(contract_items, pid):
    return next((i for i in contract_items if i["product_id"] == pid), None)


async def main():
    created = {"products": [], "pos": []}
    async with httpx.AsyncClient(timeout=40) as client:
        tok = await login(client)
        H = {"Authorization": f"Bearer {tok}"}
        whs = (await client.get(f"{BASE}/warehouses", headers=H)).json()
        wh = whs[0]["id"]
        pA = await make_product(client, H, "A", 50000)
        pB = await make_product(client, H, "B", 40000)
        created["products"] += [pA["id"], pB["id"]]

        # ── Case 0 — buat kontrak Blanket (1.c) ──
        print("\n── Case 0 — buat Blanket PO ──")
        rb = await make_blanket(client, H, wh, items=[
            {"product_id": pA["id"], "contract_qty": 1000, "contract_price": 50000},
            {"product_id": pB["id"], "contract_qty": 500, "contract_price": 40000},
        ])  # cap default = 1000*50000 + 500*40000 = 70.000.000
        check("create blanket → 200", rb.status_code == 200, f"{rb.status_code} {rb.text[:160]}")
        blanket = rb.json()
        created["pos"].append(blanket["id"])
        check("po_type = blanket", blanket.get("po_type") == "blanket", blanket.get("po_type"))
        check("status awal active", blanket.get("status") == "active", blanket.get("status"))
        check("contract_items = 2", len(blanket.get("contract_items", [])) == 2)
        check("cap default = 70jt", approx(blanket.get("contract_value_cap"), 70_000_000, 1),
              blanket.get("contract_value_cap"))

        # ── Case 1 — detail drawdown awal ──
        print("\n── Case 1 — drawdown awal (called=0) ──")
        det = await get_po(client, H, blanket["id"])
        ia = find_item(det["contract_items"], pA["id"])
        check("A called_qty=0", approx(ia["called_qty"], 0), ia.get("called_qty"))
        check("A remaining=1000", approx(ia["remaining_qty"], 1000), ia.get("remaining_qty"))
        check("value_called=0", approx(det["value_called"], 0), det.get("value_called"))
        check("value_remaining=70jt", approx(det["value_remaining"], 70_000_000, 1), det.get("value_remaining"))
        check("contract_status active", det.get("contract_status") == "active", det.get("contract_status"))

        # ── Case 2 — call-off normal (2.a) dalam sisa → PO anak pending ──
        print("\n── Case 2 — call-off normal → PO anak ──")
        rc = await call_off(client, H, blanket["id"],
                            items=[{"product_id": pA["id"], "quantity": 100}])  # 100 @ 50000 = 5jt
        check("call-off → 200", rc.status_code == 200, f"{rc.status_code} {rc.text[:160]}")
        co1 = rc.json()
        created["pos"].append(co1["id"])
        check("call-off po_type=call_off", co1.get("po_type") == "call_off", co1.get("po_type"))
        check("call-off parent linkage", co1.get("parent_po_id") == blanket["id"], co1.get("parent_po_id"))
        check("call-off pakai harga kontrak 50000", approx(co1["items"][0]["price"], 50000),
              co1["items"][0]["price"])
        check("call-off kecil → pending (tanpa approval)", co1.get("status") == "pending", co1.get("status"))
        check("call-off buat inbound task (pending)", True)
        det = await get_po(client, H, blanket["id"])
        ia = find_item(det["contract_items"], pA["id"])
        check("A called=100 setelah call-off", approx(ia["called_qty"], 100), ia.get("called_qty"))
        check("A remaining=900", approx(ia["remaining_qty"], 900), ia.get("remaining_qty"))
        check("value_called=5jt", approx(det["value_called"], 5_000_000, 1), det.get("value_called"))

        # ── Case 3 — override harga (3.b): tanpa alasan→400, dengan alasan→200 ──
        print("\n── Case 3 — override harga ──")
        r = await call_off(client, H, blanket["id"],
                           items=[{"product_id": pB["id"], "quantity": 50, "price": 45000}])
        check("override tanpa alasan → 400", r.status_code == 400, f"{r.status_code} {r.text[:120]}")
        r = await call_off(client, H, blanket["id"],
                           items=[{"product_id": pB["id"], "quantity": 50, "price": 45000}],
                           override_reason="harga spot naik")
        check("override dengan alasan → 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
        if r.status_code == 200:
            co2 = r.json()
            created["pos"].append(co2["id"])
            check("override harga tersimpan 45000", approx(co2["items"][0]["price"], 45000),
                  co2["items"][0]["price"])

        # ── Case 4 — over-call QTY (4.b) → diizinkan tapi WAJIB approval ──
        print("\n── Case 4 — over-call qty → force approval ──")
        det = await get_po(client, H, blanket["id"])
        rem_a = find_item(det["contract_items"], pA["id"])["remaining_qty"]  # 900
        r = await call_off(client, H, blanket["id"],
                           items=[{"product_id": pA["id"], "quantity": rem_a + 50}])
        check("over-call qty → 200 (diizinkan)", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
        if r.status_code == 200:
            co3 = r.json()
            created["pos"].append(co3["id"])
            check("over-call → waiting_approval", co3.get("status") == "waiting_approval", co3.get("status"))
            check("over-call → approval_required", co3.get("approval_required") is True)
            check("over-call → reason mengandung blanket_overcall",
                  "blanket_overcall" in (co3.get("approval_reason") or ""), co3.get("approval_reason"))

        # ── Case 5 — produk di luar kontrak → 400 ──
        print("\n── Case 5 — produk luar kontrak ──")
        pC = await make_product(client, H, "C", 30000)
        created["products"].append(pC["id"])
        r = await call_off(client, H, blanket["id"], items=[{"product_id": pC["id"], "quantity": 10}])
        check("produk luar kontrak → 400", r.status_code == 400, f"{r.status_code} {r.text[:120]}")

        # ── Case 6 — cancel call-off mengembalikan drawdown ──
        print("\n── Case 6 — cancel call-off restore sisa ──")
        det_before = await get_po(client, H, blanket["id"])
        rem_b_before = find_item(det_before["contract_items"], pB["id"])["remaining_qty"]
        rc = await call_off(client, H, blanket["id"], items=[{"product_id": pB["id"], "quantity": 30}])
        co_cancel = rc.json()
        created["pos"].append(co_cancel["id"])
        det_mid = await get_po(client, H, blanket["id"])
        rem_b_mid = find_item(det_mid["contract_items"], pB["id"])["remaining_qty"]
        check("sisa B turun setelah call-off", approx(rem_b_mid, rem_b_before - 30), f"{rem_b_mid} vs {rem_b_before-30}")
        await client.post(f"{BASE}/purchase-orders/{co_cancel['id']}/cancel", headers=H)
        det_after = await get_po(client, H, blanket["id"])
        rem_b_after = find_item(det_after["contract_items"], pB["id"])["remaining_qty"]
        check("sisa B kembali setelah cancel", approx(rem_b_after, rem_b_before), f"{rem_b_after} vs {rem_b_before}")

        # ── Case 7 — qty habis → exhausted → call-off ditolak (5.a) ──
        print("\n── Case 7 — exhausted qty → tolak ──")
        rb2 = await make_blanket(client, H, wh, items=[
            {"product_id": pA["id"], "contract_qty": 100, "contract_price": 50000}])  # cap 5jt
        blk2 = rb2.json()
        created["pos"].append(blk2["id"])
        r = await call_off(client, H, blk2["id"], items=[{"product_id": pA["id"], "quantity": 100}])  # habiskan
        check("call-off habiskan qty → 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
        if r.status_code == 200:
            created["pos"].append(r.json()["id"])
        det2 = await get_po(client, H, blk2["id"])
        check("kontrak jadi exhausted", det2.get("contract_status") == "exhausted", det2.get("contract_status"))
        r = await call_off(client, H, blk2["id"], items=[{"product_id": pA["id"], "quantity": 10}])
        check("call-off saat exhausted → 400 (5.a)", r.status_code == 400, f"{r.status_code} {r.text[:120]}")

        # ── Case 8 — kontrak kadaluarsa → call-off ditolak (5.a) ──
        print("\n── Case 8 — expired → tolak ──")
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        last_month = (date.today() - timedelta(days=30)).isoformat()
        rb3 = await make_blanket(client, H, wh, items=[
            {"product_id": pA["id"], "contract_qty": 100, "contract_price": 50000}],
            valid_from=last_month, valid_until=yesterday)
        blk3 = rb3.json()
        created["pos"].append(blk3["id"])
        det3 = await get_po(client, H, blk3["id"])
        check("kontrak expired (valid_until lampau)", det3.get("contract_status") == "expired",
              det3.get("contract_status"))
        r = await call_off(client, H, blk3["id"], items=[{"product_id": pA["id"], "quantity": 10}])
        check("call-off saat expired → 400 (5.a)", r.status_code == 400, f"{r.status_code} {r.text[:120]}")

        # ── Case 9 — over-call NILAI (4.b) → force approval ──
        print("\n── Case 9 — over-call nilai → force approval ──")
        rb4 = await make_blanket(client, H, wh, items=[
            {"product_id": pA["id"], "contract_qty": 1000, "contract_price": 50000}],
            cap=10_000_000)  # plafon 10jt (qty besar, nilai jadi pengikat)
        blk4 = rb4.json()
        created["pos"].append(blk4["id"])
        r = await call_off(client, H, blk4["id"], items=[{"product_id": pA["id"], "quantity": 100}])  # 5jt, OK
        if r.status_code == 200:
            created["pos"].append(r.json()["id"])
        check("call-off 5jt dalam plafon → pending", r.json().get("status") == "pending", r.json().get("status"))
        # sisa nilai 5jt; minta 150 @50000 = 7.5jt > sisa, tapi qty 150 < 900 (qty masih cukup) → over-call nilai
        r = await call_off(client, H, blk4["id"], items=[{"product_id": pA["id"], "quantity": 150}])
        check("over-call nilai → 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
        if r.status_code == 200:
            co_val = r.json()
            created["pos"].append(co_val["id"])
            check("over-call nilai → waiting_approval", co_val.get("status") == "waiting_approval",
                  co_val.get("status"))
            check("over-call nilai → reason blanket_overcall",
                  "blanket_overcall" in (co_val.get("approval_reason") or ""), co_val.get("approval_reason"))

        # ── Case 10 — close manual → call-off ditolak ──
        print("\n── Case 10 — close kontrak manual ──")
        rb5 = await make_blanket(client, H, wh, items=[
            {"product_id": pA["id"], "contract_qty": 100, "contract_price": 50000}])
        blk5 = rb5.json()
        created["pos"].append(blk5["id"])
        rcl = await client.post(f"{BASE}/purchase-orders/{blk5['id']}/close-contract", headers=H,
                                json={"reason": "tutup awal"})
        check("close-contract → 200", rcl.status_code == 200, f"{rcl.status_code} {rcl.text[:120]}")
        det5 = await get_po(client, H, blk5["id"])
        check("status jadi closed", det5.get("status") == "closed", det5.get("status"))
        r = await call_off(client, H, blk5["id"], items=[{"product_id": pA["id"], "quantity": 10}])
        check("call-off saat closed → 400 (5.a)", r.status_code == 400, f"{r.status_code} {r.text[:120]}")

        # ── Case 11 — blanket TIDAK muncul di list PO standar; call_off muncul ──
        print("\n── Case 11 — pemisahan list ──")
        std_list = (await client.get(f"{BASE}/purchase-orders", headers=H)).json()
        std_ids = {p["id"] for p in std_list}
        check("blanket TIDAK di list PO standar", blanket["id"] not in std_ids)
        check("call_off MUNCUL di list PO standar", co1["id"] in std_ids)
        blk_list = (await client.get(f"{BASE}/purchase-orders/blanket", headers=H)).json()
        blk_ids = {b["id"] for b in blk_list}
        check("blanket muncul di list blanket", blanket["id"] in blk_ids)

        # ── Cleanup ──
        for pid in created["pos"]:
            await db.wms_tasks.delete_many({"po_id": pid})
            await db.purchase_orders.delete_one({"id": pid})
        for prid in created["products"]:
            await db.products.delete_one({"id": prid})
            await db.inventory_balances.delete_many({"product_id": prid})
        print("\n  (sandbox dibersihkan)")

    print(f"\n  RESULT: {PASS} PASS / {FAIL} FAIL")
    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
