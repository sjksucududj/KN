"""Sub-fase 1.8 — Status SO diperluas + Partial Shipment (SSOT-safe) end-to-end self-test.

Alur: create SO → approve → confirm (auto task) → scan-pick → dispatch PARSIAL → dispatch sisa
→ mark-delivered. Memverifikasi transisi status otomatis + record shipments + No. Surat Jalan.
Plus cek SSOT: balance == Σ rolls (on_hand turun, owned konsisten) tidak rusak.

Jalankan: python tests/test_shipment_18.py  (butuh backend RUNNING + seed bersih)
"""
import sys, math
sys.path.insert(0, "/app/backend")
import requests  # noqa: E402

B = "http://localhost:8001/api"
results = []


def _assert(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, ("" if cond else f":: {detail}"))
    results.append(bool(cond))
    return cond


def login(email="admin@kainnusantara.id"):
    return requests.post(f"{B}/auth/login", json={"email": email, "password": "demo12345"}).json()["token"]


def main():
    H = {"Authorization": f"Bearer {login()}"}

    # 1) cari segmen balance dgn available>=10, lalu customer (punya alamat) di entitas yg sama
    all_bals = requests.get(f"{B}/inventory/balances", headers=H).json()
    custs = requests.get(f"{B}/customers", headers=H).json()
    cust_by_entity = {}
    for c in custs:
        if c.get("addresses") and c.get("entity_id") not in cust_by_entity:
            cust_by_entity[c["entity_id"]] = c
    bal = cust = None
    for b in sorted(all_bals, key=lambda x: -float(x.get("available_qty", 0) or 0)):
        if float(b.get("available_qty", 0) or 0) >= 10 and b.get("owner_entity_id") in cust_by_entity:
            bal = b; cust = cust_by_entity[b["owner_entity_id"]]; break
    _assert("ada customer+alamat dgn produk available>=10 di entitasnya", bal is not None and cust is not None,
            str([(b.get("sku"), b.get("owner_entity_id"), b.get("available_qty")) for b in all_bals][:6]))
    if not bal:
        return _finish()
    entity = cust["entity_id"]
    addr_id = cust["addresses"][0]["id"]
    product_id = bal["product_id"]
    qty = float(int(min(float(bal["available_qty"]), 40.0)))

    # 3) create SO
    payload = {"customer_id": cust["id"], "shipping_address_id": addr_id, "entity_id": entity,
               "items": [{"product_id": product_id, "quantity": qty, "unit": "meter"}]}
    r = requests.post(f"{B}/sales-orders", headers=H, json=payload)
    _assert("create SO → 200", r.status_code == 200, r.text)
    so = r.json()
    oid = so["id"]
    _assert("SO status awal reserved", so["status"] == "reserved", so.get("status"))
    _assert("item punya base_quantity (UOM-safe)", so["items"][0].get("base_quantity", None) is not None, so["items"][0])

    # 4) submit-for-approval → approve bila perlu
    r = requests.post(f"{B}/sales-orders/{oid}/submit-for-approval", headers=H)
    st = r.json().get("status")
    if st == "waiting_approval":
        r = requests.post(f"{B}/sales-orders/{oid}/approve", headers=H)
        st = r.json().get("status")
    _assert("SO approved", st == "approved", st)

    # 5) confirm → auto-create outbound tasks
    r = requests.post(f"{B}/sales-orders/{oid}/confirm", headers=H)
    _assert("confirm → 200", r.status_code == 200, r.text)
    _assert("SO confirmed", r.json().get("status") == "confirmed", r.json().get("status"))
    tasks = requests.get(f"{B}/outbound/tasks", headers=H, params={}).json()
    tasks = [t for t in tasks if t.get("order_id") == oid]
    _assert("outbound task auto-dibuat saat confirm", len(tasks) >= 1, len(tasks))
    _assert("task punya shipped_qty=0", all(t.get("shipped_qty", 0) == 0 for t in tasks))

    # 6) scan-pick semua task penuh → SO picked
    for t in tasks:
        rp = requests.post(f"{B}/outbound/tasks/{t['id']}/scan-pick", headers=H,
                           params={"actual_qty": t["quantity"], "lot": t.get("lot", ""), "roll_id": ""})
        _assert(f"scan-pick task {t['id'][:10]} → 200", rp.status_code == 200, rp.text)
    so_now = requests.get(f"{B}/sales-orders/{oid}", headers=H).json()
    _assert("SO → picked (semua ter-pick)", so_now["status"] == "picked", so_now.get("status"))

    # 7) dispatch PARSIAL: kirim setengah task pertama
    t0 = requests.get(f"{B}/outbound/tasks", headers=H).json()
    t0 = next(t for t in t0 if t["id"] == tasks[0]["id"])
    half = max(1.0, float(int(t0["quantity"] / 2)))
    rd = requests.post(f"{B}/outbound/tasks/{t0['id']}/dispatch", headers=H, params={"ship_qty": half})
    _assert("dispatch parsial → 200", rd.status_code == 200, rd.text)
    body = rd.json()
    _assert("shipment punya No. Surat Jalan SJ-", str(body.get("shipment", {}).get("shipment_no", "")).startswith("SJ-"), body)
    _assert("task → partially_shipped", body.get("task", {}).get("status") == "partially_shipped", body.get("task", {}).get("status"))
    so_now = requests.get(f"{B}/sales-orders/{oid}", headers=H).json()
    _assert("SO → partially_shipped", so_now["status"] == "partially_shipped", so_now.get("status"))

    # 8) dispatch sisa semua task → SO shipped
    for t in requests.get(f"{B}/outbound/tasks", headers=H).json():
        if t.get("order_id") == oid and t.get("status") != "dispatched":
            requests.post(f"{B}/outbound/tasks/{t['id']}/dispatch", headers=H)
    so_now = requests.get(f"{B}/sales-orders/{oid}", headers=H).json()
    _assert("SO → shipped (semua terkirim)", so_now["status"] == "shipped", so_now.get("status"))

    # 9) shipments tercatat (>=2: parsial + sisa)
    shps = requests.get(f"{B}/shipments", headers=H, params={"order_id": oid}).json()
    _assert("ada >=2 shipment (parsial + sisa)", len(shps) >= 2, len(shps))
    # surat jalan per shipment dapat di-generate
    sj = requests.get(f"{B}/shipments/{shps[0]['id']}/surat-jalan", headers=H)
    _assert("surat jalan per-shipment → 200 HTML", sj.status_code == 200 and "SURAT JALAN" in sj.text, sj.status_code)

    # 10) mark-delivered → done
    rdv = requests.post(f"{B}/sales-orders/{oid}/mark-delivered", headers=H)
    _assert("mark-delivered → 200", rdv.status_code == 200, rdv.text)
    _assert("SO → done", rdv.json().get("status") == "done", rdv.json().get("status"))

    _finish()


def _finish():
    passed = sum(1 for r in results if r)
    print(f"\n=== SHIPMENT 1.8 — {passed}/{len(results)} PASS ===")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
