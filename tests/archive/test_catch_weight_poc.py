"""POC Fase 8 — Catch-weight / Dual-UoM pembelian.

Membuktikan (pilihan owner): faktor default per-produk (gramasi×lebar atau kg_per_meter)
+ override AKTUAL saat Goods Receipt, dan PO bisa dibeli per 'kg' ATAU 'meter' per item.

Bagian A — fungsi murni (uom_service): product_kg_per_meter, convert kg↔meter,
            resolve_roll_measures (semua kasus: task kg / task meter; berat saja /
            panjang saja / keduanya / kosong).
Bagian B — E2E API NYATA: buat produk catch-weight → PO per kg → GR multi-roll
            dengan berat aktual → cek roll.weight_kg + length(meter) + balance + received_qty(kg).
            Juga PO per meter dengan override berat aktual saat GR.

Pakai data sandbox; dibersihkan di akhir. Backend harus running di :8001.
"""
import asyncio
import sys
import os
import httpx

sys.path.insert(0, "/app/backend")
from db import db                                                   # noqa: E402
from services.uom_service import (                                  # noqa: E402
    product_kg_per_meter, convert, to_base, resolve_roll_measures, load_fixed_factors,
)

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


def approx(a, b, tol=0.05):
    return abs(float(a) - float(b)) <= tol


async def part_a_pure():
    print("\n── Bagian A — fungsi murni konversi catch-weight ──")
    factors = await load_fixed_factors()

    # gramasi 200 gsm × lebar 1.5 m / 1000 = 0.3 kg/m
    p = {"id": "p1", "sku": "CW-1", "base_unit": "meter", "gramasi": 200, "lebar": 1.5}
    check("kg/m dari gramasi×lebar = 0.3", approx(product_kg_per_meter(p), 0.3), product_kg_per_meter(p))

    # kg_per_meter eksplisit menang
    p2 = {"id": "p2", "base_unit": "meter", "gramasi": 200, "lebar": 1.5, "kg_per_meter": 0.25}
    check("kg_per_meter eksplisit menang = 0.25", approx(product_kg_per_meter(p2), 0.25), product_kg_per_meter(p2))

    # tanpa data berat → 0
    check("tanpa gramasi/lebar/kg_per_meter → 0", product_kg_per_meter({"base_unit": "meter"}) == 0.0)

    # convert: 30 kg → meter (kg/m=0.3) = 100 m ; 100 m → kg = 30 kg
    check("convert 30kg → 100m", approx(convert(p, 30, "kg", "meter", factors), 100), convert(p, 30, "kg", "meter", factors))
    check("convert 100m → 30kg", approx(convert(p, 100, "meter", "kg", factors), 30), convert(p, 100, "meter", "kg", factors))
    check("to_base 30kg → 100m", approx(to_base(p, 30, "kg", factors), 100))

    # resolve_roll_measures — task 'kg'
    m = resolve_roll_measures(p, "kg", length_in=0, weight_in=30, fixed_factors=factors)
    check("task kg, berat saja 30kg → weight=30, length=100m, task_qty=30",
          approx(m["weight_kg"], 30) and approx(m["length_base"], 100) and approx(m["task_qty"], 30), m)

    # task kg, KEDUANYA (catch-weight aktual: 31kg & 98m, beda dari teoretis 0.3)
    m = resolve_roll_measures(p, "kg", length_in=98, weight_in=31, fixed_factors=factors)
    check("task kg, berat+panjang aktual → weight=31, length=98 (override teoretis)",
          approx(m["weight_kg"], 31) and approx(m["length_base"], 98), m)
    check("task kg, task_qty = berat (31)", approx(m["task_qty"], 31), m["task_qty"])

    # task kg, panjang saja → weight diturunkan
    m = resolve_roll_measures(p, "kg", length_in=50, weight_in=0, fixed_factors=factors)
    check("task kg, panjang 50m saja → weight=15 (50×0.3), length=50",
          approx(m["weight_kg"], 15) and approx(m["length_base"], 50), m)

    # task meter — panjang saja → weight estimasi
    m = resolve_roll_measures(p, "meter", length_in=120, weight_in=0, fixed_factors=factors)
    check("task meter, 120m saja → length=120, weight=36 (estimasi)",
          approx(m["length_base"], 120) and approx(m["weight_kg"], 36) and approx(m["task_qty"], 120), m)

    # task meter — berat aktual override (catch-weight)
    m = resolve_roll_measures(p, "meter", length_in=120, weight_in=37.5, fixed_factors=factors)
    check("task meter, 120m + berat aktual 37.5kg → weight=37.5 (override)", approx(m["weight_kg"], 37.5), m)

    # task kg tanpa faktor & tanpa panjang → error
    pnf = {"id": "pnf", "base_unit": "meter"}
    try:
        resolve_roll_measures(pnf, "kg", 0, 10, factors)
        check("task kg tanpa faktor & tanpa panjang → error", False, "tidak raise")
    except Exception:
        check("task kg tanpa faktor & tanpa panjang → error 400", True)

    # task kg tanpa faktor TAPI panjang aktual diisi → boleh (length aktual, weight=10)
    m = resolve_roll_measures(pnf, "kg", length_in=40, weight_in=10, fixed_factors=factors)
    check("task kg tanpa faktor + panjang aktual 40m → length=40, weight=10",
          approx(m["length_base"], 40) and approx(m["weight_kg"], 10), m)


async def login(client):
    r = await client.post(f"{BASE}/auth/login", json={"email": "admin@kainnusantara.id", "password": "demo12345"})
    return r.json()["token"]


async def part_b_e2e():
    print("\n── Bagian B — E2E API: produk catch-weight → PO per-kg → GR berat aktual ──")
    created = {"products": [], "pos": []}
    async with httpx.AsyncClient(timeout=30) as client:
        tok = await login(client)
        H = {"Authorization": f"Bearer {tok}"}

        wh = (await client.get(f"{BASE}/warehouses", headers=H)).json()[0]["id"]

        # 1) Produk catch-weight: gramasi 250, lebar 1.6 → kg/m = 0.4
        sku = f"POC-CW-{os.getpid()}"
        pr = await client.post(f"{BASE}/products", headers=H, json={
            "sku": sku, "name": "POC Catch-Weight Kain", "category": "Kain",
            "base_unit": "meter", "price": 50000, "harga_pokok": 30000,
            "gramasi": 250, "lebar": 1.6,
        })
        check("buat produk catch-weight (gramasi/lebar)", pr.status_code == 200, pr.text[:200])
        prod = pr.json()
        created["products"].append(prod["id"])
        check("produk: kg/m teoretis 0.4 (250×1.6/1000)", approx(250 * 1.6 / 1000, 0.4))

        # 2) PO dibeli per KG: 200 kg @ Rp 80.000/kg (kecil → tanpa approval)
        po_res = await client.post(f"{BASE}/purchase-orders", headers=H, json={
            "supplier_name": "POC Supplier CW", "warehouse_id": wh,
            "items": [{"product_id": prod["id"], "quantity": 200, "unit": "kg", "price": 80000}],
        })
        check("buat PO item per 'kg'", po_res.status_code == 200, po_res.text[:200])
        po = po_res.json()
        created["pos"].append(po["id"])
        item = po["items"][0]
        check("PO item unit = kg", item.get("unit") == "kg", item.get("unit"))
        # quantity_base = 200 kg / 0.4 = 500 m
        check("PO item quantity_base = 500 m (200kg ÷ 0.4)", approx(item.get("quantity_base", 0), 500), item.get("quantity_base"))
        check("PO subtotal GROSS = 200×80000 = 16.000.000", approx(item.get("subtotal", 0), 16_000_000), item.get("subtotal"))

        # 3) Inbound task untuk PO (unit kg)
        if po.get("status") == "waiting_approval":
            check("PO kecil tak butuh approval (status pending)", False, f"status={po.get('status')}")
        tasks = (await client.get(f"{BASE}/inbound/tasks", headers=H)).json()
        task = next((t for t in tasks if t.get("po_id") == po["id"]), None)
        check("inbound task terbuat (unit kg)", task is not None and task.get("unit") == "kg",
              task.get("unit") if task else None)

        # 4) Receive penuh 200 kg (scan) lalu advance ke qc_check/put_away
        await client.post(f"{BASE}/inbound/tasks/{task['id']}/scan-receive", headers=H,
                          json={"product_id": prod["id"], "actual_qty": 200, "bin_id": "A1-01"})
        task = next((t for t in (await client.get(f"{BASE}/inbound/tasks", headers=H)).json() if t["id"] == task["id"]), None)
        check("setelah scan 200kg, task siap complete (qc_check/put_away)",
              task and task.get("status") in ("qc_check", "put_away"), task.get("status") if task else None)

        # 5) Complete GR dengan 2 roll + BERAT AKTUAL (catch-weight). Total 200 kg.
        #    Roll-1: 120 kg (panjang aktual 290 m). Roll-2: 80 kg (panjang dihitung 80/0.4=200 m).
        comp = await client.post(f"{BASE}/inbound/tasks/{task['id']}/complete", headers=H, json={
            "rolls": [
                {"weight": 120, "length": 290, "dye_lot": "DL-CW-1", "grade": "A"},
                {"weight": 80, "dye_lot": "DL-CW-2", "grade": "A"},
            ]
        })
        check("complete GR catch-weight (2 roll, total 200kg)", comp.status_code == 200, comp.text[:250])

        # 6) Cek roll: weight_kg tersimpan + length meter
        rolls = (await client.get(f"{BASE}/inventory/rolls", headers=H, params={"product_id": prod["id"]})).json()
        rolls = rolls if isinstance(rolls, list) else rolls.get("items", [])
        rolls = [r for r in rolls if r.get("product_id") == prod["id"]]
        check("2 roll terbuat", len(rolls) == 2, len(rolls))
        total_w = round(sum(float(r.get("weight_kg", 0)) for r in rolls), 2)
        total_len = round(sum(float(r.get("length_initial", 0)) for r in rolls), 2)
        check("Σ weight_kg roll = 200 kg", approx(total_w, 200), total_w)
        # Roll-1 panjang aktual 290 (override), Roll-2 = 80/0.4 = 200 → total 490 m
        check("Σ length roll = 490 m (290 aktual + 200 turunan)", approx(total_len, 490), total_len)
        r1 = next((r for r in rolls if r.get("dye_lot") == "DL-CW-1"), None)
        check("roll-1 weight_kg=120 & length=290 (catch-weight aktual)",
              r1 and approx(r1.get("weight_kg"), 120) and approx(r1.get("length_initial"), 290), r1)

        # 7) PO item received_qty akumulasi dalam SATUAN ORDER (kg) = 200
        po2 = (await client.get(f"{BASE}/purchase-orders/{po['id']}", headers=H)).json()
        check("PO received_qty = 200 (kg, satuan order)", approx(po2["items"][0].get("received_qty", 0), 200),
              po2["items"][0].get("received_qty"))

    # cleanup sandbox
    for pid in created["pos"]:
        await db.purchase_orders.delete_one({"id": pid})
    for prid in created["products"]:
        rolls = await db.inventory_rolls.find({"product_id": prid}, {"_id": 0, "id": 1}).to_list(100)
        await db.inventory_rolls.delete_many({"product_id": prid})
        await db.inventory_movements.delete_many({"product_id": prid})
        await db.inventory_balances.delete_many({"product_id": prid})
        await db.wms_tasks.delete_many({"product_id": prid})
        await db.products.delete_one({"id": prid})
    print("  (sandbox dibersihkan)")


async def main():
    await part_a_pure()
    await part_b_e2e()
    print(f"\n  RESULT: {PASS} PASS / {FAIL} FAIL")
    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
