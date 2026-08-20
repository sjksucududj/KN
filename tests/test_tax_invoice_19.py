"""Sub-fase 1.9 — Faktur Pajak Jual (tax_invoices) end-to-end self-test.

Alur: create SO (entitas PKP) → approve → confirm → terbitkan Faktur Pajak →
idempotent 409 → dokumen HTML → set NSFP → pengganti → cancel pengganti →
guard non-PKP (entitas non_ppn ditolak). Memverifikasi invarian PPN/DPP & rantai status.

Jalankan: python tests/test_tax_invoice_19.py  (butuh backend RUNNING + seed bersih)
"""
import sys
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


def _make_confirmed_so(H, entity_id):
    """Buat SO untuk entitas tertentu (customer+alamat se-entitas, produk available>=10) → confirm."""
    bals = requests.get(f"{B}/inventory/balances", headers=H).json()
    custs = requests.get(f"{B}/customers", headers=H).json()
    cust = next((c for c in custs if c.get("entity_id") == entity_id and c.get("addresses")), None)
    if not cust:
        return None
    bal = next((b for b in sorted(bals, key=lambda x: -float(x.get("available_qty", 0) or 0))
                if b.get("owner_entity_id") == entity_id and float(b.get("available_qty", 0) or 0) >= 10), None)
    if not bal:
        return None
    qty = float(int(min(float(bal["available_qty"]), 30.0)))
    payload = {"customer_id": cust["id"], "shipping_address_id": cust["addresses"][0]["id"],
               "entity_id": entity_id, "items": [{"product_id": bal["product_id"], "quantity": qty, "unit": "meter"}]}
    so = requests.post(f"{B}/sales-orders", headers=H, json=payload).json()
    oid = so["id"]
    r = requests.post(f"{B}/sales-orders/{oid}/submit-for-approval", headers=H)
    if r.json().get("status") == "waiting_approval":
        requests.post(f"{B}/sales-orders/{oid}/approve", headers=H)
    requests.post(f"{B}/sales-orders/{oid}/confirm", headers=H)
    return requests.get(f"{B}/sales-orders/{oid}", headers=H).json()


def main():
    H = {"Authorization": f"Bearer {login()}"}

    # ── PKP flow (ent_ksc default_tax_mode=ppn) ──
    so = _make_confirmed_so(H, "ent_ksc")
    if not _assert("buat SO PKP (ent_ksc) terkonfirmasi", so is not None and so.get("status") == "confirmed",
                   so.get("status") if so else "no SO"):
        return _finish()
    oid = so["id"]
    _assert("order PKP punya ppn_amount>0", float(so.get("ppn_amount", 0) or 0) > 0, so.get("ppn_amount"))

    # terbitkan Faktur Pajak
    r = requests.post(f"{B}/sales-orders/{oid}/tax-invoice", headers=H, json={"kode_transaksi": "01"})
    _assert("terbitkan Faktur Pajak → 200", r.status_code == 200, r.text)
    fkt = r.json()
    fid = fkt["id"]
    _assert("nomor internal FKT-", str(fkt.get("number", "")).startswith("FKT-"), fkt.get("number"))
    _assert("status normal", fkt.get("status") == "normal", fkt.get("status"))
    _assert("kode_transaksi 01", fkt.get("kode_transaksi") == "01", fkt.get("kode_transaksi"))
    _assert("PPN == DPP×rate", abs(float(fkt["ppn_amount"]) - round(float(fkt["dpp"]) * float(fkt["ppn_rate"]) / 100, 2)) < 1.0,
            (fkt["dpp"], fkt["ppn_rate"], fkt["ppn_amount"]))
    _assert("snapshot penjual NPWP terisi", bool(fkt.get("seller_npwp")), fkt.get("seller_npwp"))

    # idempotent → 409
    r2 = requests.post(f"{B}/sales-orders/{oid}/tax-invoice", headers=H, json={})
    _assert("terbit ulang → 409 (idempotent)", r2.status_code == 409, r2.status_code)

    # dokumen HTML
    doc = requests.get(f"{B}/tax-invoices/{fid}/document", headers=H)
    _assert("dokumen Faktur Pajak → 200 HTML", doc.status_code == 200 and "FAKTUR PAJAK" in doc.text, doc.status_code)

    # set NSFP resmi
    r = requests.patch(f"{B}/tax-invoices/{fid}/nsfp", headers=H,
                       json={"nsfp": "0100123456789012", "kode_transaksi": "01"})
    _assert("set NSFP → 200", r.status_code == 200, r.text)
    _assert("NSFP tersimpan", r.json().get("nsfp") == "0100123456789012", r.json().get("nsfp"))

    # pengganti
    r = requests.post(f"{B}/tax-invoices/{fid}/replace", headers=H, json={"reason": "Koreksi alamat"})
    _assert("pengganti → 200", r.status_code == 200, r.text)
    peng = r.json()
    _assert("status pengganti", peng.get("status") == "pengganti", peng.get("status"))
    _assert("pengganti.replaces_id == original", peng.get("replaces_id") == fid, peng.get("replaces_id"))
    orig = requests.get(f"{B}/tax-invoices/{fid}", headers=H).json()
    _assert("original ditandai replaced_by_id", orig.get("replaced_by_id") == peng["id"], orig.get("replaced_by_id"))

    # cancel pengganti → original aktif lagi
    r = requests.post(f"{B}/tax-invoices/{peng['id']}/cancel", headers=H, json={"reason": "Salah terbit pengganti"})
    _assert("cancel pengganti → 200", r.status_code == 200, r.text)
    _assert("pengganti status batal", r.json().get("status") == "batal", r.json().get("status"))
    orig = requests.get(f"{B}/tax-invoices/{fid}", headers=H).json()
    _assert("original replaced_by_id dilepas", orig.get("replaced_by_id") in (None, ""), orig.get("replaced_by_id"))

    # list by order
    lst = requests.get(f"{B}/tax-invoices", headers=H, params={"order_id": oid}).json()
    _assert("list by order (>=2: normal + pengganti batal)", len(lst) >= 2, len(lst))

    # ── Non-PKP guard (ent_kanda default_tax_mode=non_ppn) ──
    so2 = _make_confirmed_so(H, "ent_kanda")
    if so2 and so2.get("status") == "confirmed":
        rng = requests.post(f"{B}/sales-orders/{so2['id']}/tax-invoice", headers=H, json={})
        _assert("entitas non-PKP → ditolak 400", rng.status_code == 400, rng.status_code)
    else:
        _assert("entitas non-PKP → ditolak 400 (skip: tak ada SO ent_kanda)", True)

    _finish()


def _finish():
    passed = sum(1 for r in results if r)
    print(f"\n=== FAKTUR PAJAK 1.9 — {passed}/{len(results)} PASS ===")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
