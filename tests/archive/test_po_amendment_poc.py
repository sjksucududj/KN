"""POC Phase 7.2 — PO Amendment / Version History.

Membuktikan endpoint `POST /api/purchase-orders/{po_id}/amend` (keputusan owner
1.c/2.a/3.b/4.a/5.a):
  - 1.c  : boleh ubah item/supplier/tanggal/catatan.
  - 2.a  : SELALU re-approval dari awal (chain dibangun ulang).
  - 3.b  : boleh saat partial receiving — qty tak boleh < received, item ber-penerimaan tak bisa dihapus,
           gudang tak bisa diganti bila sudah ada penerimaan.
  - 4.a  : simpan snapshot penuh + diff tiap versi (version increment).
  - 5.a  : alasan WAJIB + audit.
  - Idempotency: re-amend tidak menduplikasi inbound task; expected_qty ikut ter-update.

E2E API NYATA (backend harus running di :8001). Data sandbox dibersihkan di akhir.
"""
import asyncio
import os
import sys

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


async def make_product(client, H):
    sku = f"POC-AMEND-{os.getpid()}"
    r = await client.post(f"{BASE}/products", headers=H, json={
        "sku": sku, "name": "POC Amendment Kain", "category": "Kain",
        "base_unit": "meter", "price": 50000, "harga_pokok": 30000,
    })
    return r.json()


async def make_po(client, H, wh, prod, qty=100, price=50000, supplier="POC Supplier Amend"):
    r = await client.post(f"{BASE}/purchase-orders", headers=H, json={
        "supplier_name": supplier, "warehouse_id": wh,
        "items": [{"product_id": prod["id"], "quantity": qty, "unit": "meter", "price": price}],
    })
    return r


async def main():
    created = {"products": [], "pos": []}
    async with httpx.AsyncClient(timeout=30) as client:
        tok = await login(client)
        H = {"Authorization": f"Bearer {tok}"}
        whs = (await client.get(f"{BASE}/warehouses", headers=H)).json()
        wh = whs[0]["id"]
        wh2 = whs[1]["id"] if len(whs) > 1 else wh
        prod = await make_product(client, H)
        created["products"].append(prod["id"])

        # ── Case 0: 404 untuk PO tidak ada ──
        print("\n── Case 0 — PO tidak ditemukan ──")
        r = await client.post(f"{BASE}/purchase-orders/nope-xxx/amend", headers=H, json={"reason": "x"})
        check("amend PO non-exist → 404", r.status_code == 404, f"{r.status_code} {r.text[:120]}")

        # ── Case A: reason WAJIB (5.a) ──
        print("\n── Case A — alasan wajib ──")
        po = (await make_po(client, H, wh, prod, qty=100, price=50000)).json()  # 5jt → pending
        created["pos"].append(po["id"])
        check("PO kecil → status pending (tanpa approval)", po.get("status") == "pending", po.get("status"))
        check("PO awal version = 1", po.get("version") == 1, po.get("version"))
        r = await client.post(f"{BASE}/purchase-orders/{po['id']}/amend", headers=H, json={"reason": "   "})
        check("amend tanpa reason → 400", r.status_code == 400, f"{r.status_code} {r.text[:120]}")

        # ── Case B: amend dasar (ubah qty + harga) → version++, snapshot + diff (4.a) ──
        print("\n── Case B — amend dasar: snapshot + diff + version ──")
        r = await client.post(f"{BASE}/purchase-orders/{po['id']}/amend", headers=H, json={
            "reason": "Koreksi qty & harga dari supplier",
            "items": [{"product_id": prod["id"], "quantity": 150, "unit": "meter", "price": 55000}],
            "notes": "revisi-1",
        })
        check("amend dasar → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
        amended = r.json()
        check("version naik ke 2", amended.get("version") == 2, amended.get("version"))
        check("amendments length = 1", len(amended.get("amendments", [])) == 1, len(amended.get("amendments", [])))
        amd = (amended.get("amendments") or [{}])[0]
        check("amendment.reason tersimpan", amd.get("reason") == "Koreksi qty & harga dari supplier", amd.get("reason"))
        check("amendment.snapshot_before.version = 1", (amd.get("snapshot_before") or {}).get("version") == 1,
              (amd.get("snapshot_before") or {}).get("version"))
        snap_items = (amd.get("snapshot_before") or {}).get("items") or []
        check("snapshot_before menyimpan qty lama (100)", snap_items and approx(snap_items[0].get("quantity"), 100),
              snap_items[0].get("quantity") if snap_items else None)
        changes = amd.get("changes") or []
        fields = {c.get("field") for c in changes}
        check("diff berisi perubahan qty item", "item_qty" in fields, fields)
        check("diff berisi perubahan harga item", "item_price" in fields, fields)
        check("diff berisi perubahan total (GROSS)", "total" in fields, fields)
        check("item qty ter-update ke 150", approx(amended["items"][0]["quantity"], 150), amended["items"][0]["quantity"])
        check("item price ter-update ke 55000", approx(amended["items"][0]["price"], 55000), amended["items"][0]["price"])
        check("status tetap pending (di bawah threshold)", amended.get("status") == "pending", amended.get("status"))
        # timeline ada event amended
        ev = [t.get("event") for t in amended.get("timeline", [])]
        check("timeline punya event 'amended'", "amended" in ev, ev)

        # ── Case C: idempotent inbound tasks (tidak duplikat; expected_qty ter-update) ──
        print("\n── Case C — inbound task idempotent ──")
        tasks = (await client.get(f"{BASE}/inbound/tasks", headers=H)).json()
        po_tasks = [t for t in tasks if t.get("po_id") == po["id"] and t.get("status") not in ("cancelled", "completed")]
        check("hanya 1 inbound task aktif untuk PO (tanpa duplikat)", len(po_tasks) == 1, len(po_tasks))
        check("expected_qty task ter-update ke 150", po_tasks and approx(po_tasks[0].get("expected_qty"), 150),
              po_tasks[0].get("expected_qty") if po_tasks else None)

        # ── Case D: re-approval reset (2.a) — amend ke total besar (>100jt) ──
        print("\n── Case D — re-approval reset penuh ──")
        r = await client.post(f"{BASE}/purchase-orders/{po['id']}/amend", headers=H, json={
            "reason": "Tambah volume besar → wajib approval ulang",
            "items": [{"product_id": prod["id"], "quantity": 3000, "unit": "meter", "price": 50000}],  # 150jt
        })
        check("amend besar → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
        big = r.json()
        check("status kembali waiting_approval", big.get("status") == "waiting_approval", big.get("status"))
        check("approval_required = True", big.get("approval_required") is True, big.get("approval_required"))
        check("approval_chain dibangun ulang (≥1 level)", len(big.get("approval_chain", [])) >= 1, big.get("approval_chain"))
        check("approval_status = pending", big.get("approval_status") == "pending", big.get("approval_status"))
        check("required_approval_role = manager", big.get("required_approval_role") == "manager",
              big.get("required_approval_role"))
        check("version naik ke 3", big.get("version") == 3, big.get("version"))
        # inbound task 0-diterima dihapus saat butuh re-approval
        tasks2 = (await client.get(f"{BASE}/inbound/tasks", headers=H)).json()
        active2 = [t for t in tasks2 if t.get("po_id") == po["id"] and t.get("status") not in ("cancelled", "completed")]
        check("inbound task aktif dihapus saat menunggu re-approval", len(active2) == 0, len(active2))

        # ── Case E: guard partial receiving (3.b) ──
        print("\n── Case E — guard partial receiving ──")
        po_e = (await make_po(client, H, wh, prod, qty=200, price=50000)).json()
        created["pos"].append(po_e["id"])
        # Simulasikan penerimaan sebagian langsung di DB (received_qty=80) → status partial.
        await db.purchase_orders.update_one(
            {"id": po_e["id"]}, {"$set": {"items.0.received_qty": 80, "status": "partial"}})
        # E1: turunkan qty < received → 400
        r = await client.post(f"{BASE}/purchase-orders/{po_e['id']}/amend", headers=H, json={
            "reason": "coba turunkan di bawah diterima",
            "items": [{"product_id": prod["id"], "quantity": 30, "unit": "meter", "price": 50000}]})
        check("E1: qty 30 < received 80 → 400", r.status_code == 400, f"{r.status_code} {r.text[:150]}")
        # E2: hapus item yang sudah diterima → 400
        r = await client.post(f"{BASE}/purchase-orders/{po_e['id']}/amend", headers=H, json={
            "reason": "coba hapus item diterima", "items": []})
        check("E2: hapus item ber-penerimaan → 400", r.status_code == 400, f"{r.status_code} {r.text[:150]}")
        # E3: ganti gudang saat sudah ada penerimaan → 400
        if wh2 != wh:
            r = await client.post(f"{BASE}/purchase-orders/{po_e['id']}/amend", headers=H, json={
                "reason": "coba ganti gudang", "warehouse_id": wh2})
            check("E3: ganti gudang saat ada receipt → 400", r.status_code == 400, f"{r.status_code} {r.text[:150]}")
        else:
            check("E3: dilewati (hanya 1 gudang tersedia)", True)
        # E4: naikkan qty ≥ received (300) → boleh
        r = await client.post(f"{BASE}/purchase-orders/{po_e['id']}/amend", headers=H, json={
            "reason": "tambah qty di atas diterima", "notes": "ok",
            "items": [{"product_id": prod["id"], "quantity": 300, "unit": "meter", "price": 50000}]})
        check("E4: naikkan qty 300 ≥ received 80 → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
        if r.status_code == 200:
            ee = r.json()
            check("E4: received_qty lama (80) dipertahankan", approx(ee["items"][0].get("received_qty"), 80),
                  ee["items"][0].get("received_qty"))

        # ── Case F: status terminal tak bisa diamandemen ──
        print("\n── Case F — status terminal ditolak ──")
        po_f = (await make_po(client, H, wh, prod, qty=10, price=50000)).json()
        created["pos"].append(po_f["id"])
        await client.post(f"{BASE}/purchase-orders/{po_f['id']}/cancel", headers=H)
        r = await client.post(f"{BASE}/purchase-orders/{po_f['id']}/amend", headers=H, json={"reason": "x"})
        check("amend PO cancelled → 400", r.status_code == 400, f"{r.status_code} {r.text[:150]}")

    # ── cleanup sandbox ──
    for pid in created["pos"]:
        await db.purchase_orders.delete_one({"id": pid})
        await db.wms_tasks.delete_many({"po_id": pid})
    for prid in created["products"]:
        await db.products.delete_one({"id": prid})
        await db.wms_tasks.delete_many({"product_id": prid})
    print("  (sandbox dibersihkan)")

    print(f"\n  RESULT: {PASS} PASS / {FAIL} FAIL")
    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
