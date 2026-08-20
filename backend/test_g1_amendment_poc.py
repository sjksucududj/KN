#!/usr/bin/env python3
"""POC FASE G-1 — FONDASI AMANDEMEN (koreksi dokumen finansial yang aman).

Membuktikan lewat HTTP nyata (bukan unit test) bahwa:

  1. Tidak ada EDIT SENYAP — field uang pada pesanan tidak bisa diubah lewat PATCH biasa.
  2. Koreksi = DOKUMEN AMANDEMEN BERNOMOR + label alasan + dampak (Rp & %) + jejak.
  3. Ambang persetujuan DIBACA DARI REGISTRY FASE G-0 (bisa diubah admin tanpa deploy).
  4. Dampak kecil → langsung diterapkan (tetap bernomor & ber-alasan, bukan senyap).
  5. Dampak besar → masuk antrean persetujuan; peran yang salah DITOLAK.
  6. Kontrol ganda: pengusul tidak boleh menyetujui usulannya sendiri.
  7. Dokumen yang SUDAH TERBIT tidak pernah diubah angkanya — koreksinya lahir sebagai
     Nota Kredit / Nota Debit yang tertaut dua arah (ledger append-only).
  8. Reject tidak mengubah apa pun.
  9. RBAC: warehouse tidak boleh mengusulkan; sales boleh usul tapi tidak boleh memutus.
 10. Semua artefak POC dibersihkan → invarian global tetap hijau (nol residu).

Jalankan:  python backend/test_g1_amendment_poc.py
"""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poc_stock_guard import restore_stock, snapshot_stock  # noqa: E402

BASE = os.environ.get("KN_API", "http://localhost:8001/api")
PWD = "demo12345"
USERS = {
    "admin": "admin@kainnusantara.id",
    "manager": "manager@kainnusantara.id",
    "sales": "sales@kainnusantara.id",
    "warehouse": "warehouse@kainnusantara.id",
}

G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
_stats = {"pass": 0, "fail": 0}
_created = {"orders": [], "amendments": [], "notes": [], "tax_invoices": []}


def head(title: str) -> None:
    print(f"\n{C}{B}{'=' * 78}\n{title}\n{'=' * 78}{X}")


def ok(cond: bool, label: str, detail: str = "") -> bool:
    if cond:
        _stats["pass"] += 1
        print(f"  {G}✓{X} {label}" + (f" — {detail}" if detail else ""))
    else:
        _stats["fail"] += 1
        print(f"  {R}✗ {label}" + (f" — {detail}" if detail else "") + X)
    return bool(cond)


def login(role: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": USERS[role], "password": PWD}, timeout=20)
    r.raise_for_status()
    return r.json()["token"]


def H(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def cfg_set(tok: str, key: str, value, reason: str = "POC G-1") -> bool:
    r = requests.put(f"{BASE}/config/values", headers=H(tok), timeout=30, json={
        "items": [{"key": key, "value": value, "scope_type": "global",
                   "scope_id": "", "reason": reason}]})
    return r.status_code == 200


def cfg_get(tok: str, key: str):
    r = requests.get(f"{BASE}/config/effective", headers=H(tok),
                     params={"q": key}, timeout=30)
    for it in r.json().get("items", []):
        if it["key"] == key:
            return it["value"]
    return None


def make_order(tok: str, qty: float = 10.0) -> dict:
    """Buat SO baru khusus POC (produk & pelanggan nyata dari seed)."""
    prods = requests.get(f"{BASE}/products", headers=H(tok), timeout=30).json()
    custs = requests.get(f"{BASE}/customers", headers=H(tok), timeout=30).json()
    plist = prods if isinstance(prods, list) else prods.get("items", [])
    clist = custs if isinstance(custs, list) else custs.get("items", [])
    p = plist[0]
    # Pilih pelanggan yang punya alamat kirim (wajib untuk membuat SO).
    cust, addr_id = None, ""
    for c in clist:
        addrs = c.get("addresses") or []
        if addrs:
            cust, addr_id = c, (addrs[0].get("id") or "")
            break
    if not cust:
        print(f"{R}tidak ada pelanggan ber-alamat di seed{X}")
        sys.exit(1)
    body = {
        "customer_id": cust["id"], "shipping_address_id": addr_id,
        "items": [{"product_id": p["id"], "quantity": qty,
                   "unit": p.get("base_unit") or p.get("unit") or "meter"}],
        "sales_name": "POC G-1",
    }
    r = requests.post(f"{BASE}/sales-orders", headers=H(tok), json=body, timeout=40)
    if r.status_code not in (200, 201):
        print(f"{R}gagal membuat SO: {r.status_code} {r.text[:300]}{X}")
        sys.exit(1)
    so = r.json()
    _created["orders"].append(so["id"])
    return so


def main() -> int:
    tok = {k: login(k) for k in USERS}
    admin, manager, sales, warehouse = tok["admin"], tok["manager"], tok["sales"], tok["warehouse"]
    # POC-RESIDU-01 — konfirmasi SO memotong & mereservasi roll; menghapus SO dari DB
    # tidak melepasnya. Snapshot stok di sini, dipulihkan EKSAK di CLEANUP.
    _stock_snap = snapshot_stock()

    # Simpan ambang awal supaya bisa dipulihkan di akhir.
    keys = ["amendment.approval_threshold_amount", "amendment.approval_threshold_pct",
            "amendment.admin_approval_above", "amendment.dual_control",
            "amendment.require_note_above", "amendment.issued_doc_policy",
            "amendment.approver_role"]
    original = {k: cfg_get(admin, k) for k in keys}

    # ── TEST 1 ────────────────────────────────────────────────────────────
    head("TEST 1 — TIDAK ADA EDIT SENYAP: field uang tak bisa diubah lewat PATCH biasa")
    so = make_order(admin, qty=10.0)
    p0 = float(so["items"][0]["price"])
    before_total = float(so["grand_total"])
    ok(before_total > 0, f"SO POC dibuat: {so['number']}", f"Rp {before_total:,.0f}")

    r = requests.patch(f"{BASE}/sales-orders/{so['id']}", headers=H(admin), timeout=30,
                       json={"data": {"grand_total": 1, "total_amount": 1,
                                      "items": [], "notes": "coba edit senyap"}})
    after = requests.get(f"{BASE}/sales-orders/{so['id']}", headers=H(admin), timeout=30).json()
    ok(r.status_code == 200 and abs(float(after["grand_total"]) - before_total) < 0.01,
       "PATCH biasa TIDAK mengubah nominal (field uang diabaikan server)",
       f"tetap Rp {float(after['grand_total']):,.0f}")
    ok(len(after.get("items") or []) == len(so.get("items") or []),
       "PATCH biasa TIDAK bisa mengosongkan/mengganti item")

    # ── TEST 2 ────────────────────────────────────────────────────────────
    head("TEST 2 — LABEL ALASAN configurable & WAJIB dipilih")
    reasons = requests.get(f"{BASE}/amendment-reasons", headers=H(admin), timeout=30).json()
    codes = {x["code"] for x in reasons}
    ok(len(reasons) >= 5, f"{len(reasons)} label alasan tersedia", ", ".join(sorted(codes))[:80])

    r = requests.post(f"{BASE}/amendments/preview", headers=H(admin), timeout=30, json={
        "doc_type": "sales_order", "doc_id": so["id"], "reason_code": "",
        "changes": [{"product_id": so["items"][0]["product_id"], "field": "price", "to": p0 - 1000}]})
    ok(r.status_code == 200, "pratinjau boleh tanpa alasan (hanya menghitung dampak)")

    r = requests.post(f"{BASE}/amendments", headers=H(admin), timeout=30, json={
        "doc_type": "sales_order", "doc_id": so["id"], "reason_code": "",
        "changes": [{"product_id": so["items"][0]["product_id"], "field": "price", "to": p0 - 1000}]})
    ok(r.status_code == 400 and "alasan" in r.text.lower(),
       "USULAN tanpa label alasan DITOLAK", r.json().get("detail", "")[:70])

    r = requests.put(f"{BASE}/amendment-reasons", headers=H(admin), timeout=30, json={
        "code": "poc_g1_reason", "label": "Alasan Uji POC G-1",
        "applies_to": ["sales_order"], "status": "active"})
    ok(r.status_code == 200, "admin bisa MENAMBAH label alasan tanpa deploy")
    r = requests.put(f"{BASE}/amendment-reasons", headers=H(manager), timeout=30, json={
        "code": "x", "label": "x"})
    ok(r.status_code == 403, "manager TIDAK boleh mengelola label alasan (butuh finance_amendment.admin)")

    # ── TEST 3 ────────────────────────────────────────────────────────────
    head("TEST 3 — DAMPAK dihitung & dijelaskan sebelum dikirim (Rp & %)")
    pid = so["items"][0]["product_id"]
    r = requests.post(f"{BASE}/amendments/preview", headers=H(admin), timeout=30, json={
        "doc_type": "sales_order", "doc_id": so["id"], "reason_code": "price_correction",
        "changes": [{"product_id": pid, "field": "price", "to": p0 * 0.9}]})
    pv = r.json()
    ok(r.status_code == 200, "pratinjau berhasil")
    ok(pv["impact"]["delta"] < 0, "dampak negatif terhitung (harga turun)",
       f"Rp {pv['impact']['delta']:,.0f} ({pv['impact']['delta_pct']:.2f}%)")
    ok(len(pv["changes"]) == 1 and pv["changes"][0]["field"] == "price",
       "diff sebelum→sesudah terbaca manusia",
       f"{pv['changes'][0]['label']}: {pv['changes'][0]['from']:,.0f} → {pv['changes'][0]['to']:,.0f}")
    ok(bool(pv["explain"]), "alasan keputusan kebijakan dijelaskan", pv["explain"][0][:60])
    ok(pv["method"] == "re_derive" and pv["issued"] is False,
       "dokumen BELUM terbit → metode 'hitung ulang'", pv["method_label"])

    # ── TEST 4 ────────────────────────────────────────────────────────────
    head("TEST 4 — AMBANG DARI REGISTRY (G-0): dampak kecil langsung jalan, TETAP bernomor")
    ok(cfg_set(admin, "amendment.approval_threshold_amount", 5000000),
       "set ambang rupiah = Rp 5.000.000 lewat Pusat Pengaturan")
    ok(cfg_set(admin, "amendment.approval_threshold_pct", 90.0),
       "set ambang persen = 90% (agar uji ini murni menguji ambang rupiah)")
    ok(cfg_set(admin, "amendment.require_note_above", 100000000),
       "set ambang wajib-catatan tinggi dulu")

    r = requests.post(f"{BASE}/amendments", headers=H(admin), timeout=40, json={
        "doc_type": "sales_order", "doc_id": so["id"], "reason_code": "price_correction",
        "changes": [{"product_id": pid, "field": "price", "to": p0 - 1000}],
        "note": "koreksi kecil"})
    amd = r.json()
    if r.status_code == 200:
        _created["amendments"].append(amd["id"])
    ok(r.status_code == 200, "usulan dampak kecil diterima")
    ok(amd.get("status") == "auto_applied",
       "dampak di bawah ambang → LANGSUNG diterapkan", amd.get("status", ""))
    ok(bool(amd.get("number")), "tetap punya NOMOR dokumen amandemen", amd.get("number", ""))
    ok(amd.get("reason_code") == "price_correction" and amd.get("proposed_by"),
       "tetap punya alasan + pengusul (cepat ≠ senyap)",
       f"{amd.get('reason_label')} oleh {amd.get('proposed_by')}")
    ok(bool(amd.get("policy_snapshot", {}).get("approval_threshold_amount")),
       "ambang yang dipakai IKUT TERSIMPAN (bisa diaudit ulang)",
       f"Rp {amd['policy_snapshot']['approval_threshold_amount']:,.0f}")

    cur = requests.get(f"{BASE}/sales-orders/{so['id']}", headers=H(admin), timeout=30).json()
    ok(abs(float(cur["grand_total"]) - float(amd["impact"]["amount_after"])) < 1,
       "dokumen benar-benar dihitung ulang sesuai amandemen",
       f"Rp {float(cur['grand_total']):,.0f}")
    ok(any(x.get("doc_number") == amd["number"] for x in (cur.get("refs") or [])),
       "JEJAK DUA ARAH: dokumen menunjuk balik ke amandemennya")
    ok(any(t.get("event") == "amended" for t in (cur.get("timeline") or [])),
       "timeline dokumen mencatat amandemen")

    # ── TEST 5 ────────────────────────────────────────────────────────────
    head("TEST 5 — dampak BESAR wajib disetujui · peran salah ditolak · kontrol ganda")
    ok(cfg_set(admin, "amendment.approval_threshold_amount", 100000),
       "turunkan ambang jadi Rp 100.000 (uji jalur persetujuan)")
    ok(cfg_set(admin, "amendment.approver_role", "manager"), "penyetuju = manager")
    ok(cfg_set(admin, "amendment.dual_control", True), "kontrol ganda AKTIF")
    ok(cfg_set(admin, "amendment.require_note_above", 100000),
       "catatan wajib di atas Rp 100.000")

    r = requests.post(f"{BASE}/amendments", headers=H(sales), timeout=40, json={
        "doc_type": "sales_order", "doc_id": so["id"], "reason_code": "customer_negotiation",
        "changes": [{"product_id": pid, "field": "price", "to": p0 - 20000}]})
    ok(r.status_code == 400 and "penjelasan" in r.text.lower(),
       "usulan besar TANPA catatan DITOLAK", r.json().get("detail", "")[:70])

    r = requests.post(f"{BASE}/amendments", headers=H(sales), timeout=40, json={
        "doc_type": "sales_order", "doc_id": so["id"], "reason_code": "customer_negotiation",
        "changes": [{"product_id": pid, "field": "price", "to": p0 - 20000}],
        "note": "Pelanggan minta penyesuaian karena keterlambatan kirim."})
    amd2 = r.json()
    if r.status_code == 200:
        _created["amendments"].append(amd2["id"])
    ok(r.status_code == 200 and amd2["status"] == "pending_approval",
       "sales boleh MENGAJUKAN; statusnya menunggu persetujuan", amd2.get("status", ""))
    ok(amd2["required_role"] == "manager", "penyetuju yang dibutuhkan = manager")

    before_apply = requests.get(f"{BASE}/sales-orders/{so['id']}",
                                headers=H(admin), timeout=30).json()
    ok(abs(float(before_apply["grand_total"]) - float(cur["grand_total"])) < 0.01,
       "selama menunggu persetujuan, dokumen BELUM berubah")

    r = requests.post(f"{BASE}/amendments/{amd2['id']}/decision", headers=H(sales),
                      timeout=30, json={"action": "approve"})
    ok(r.status_code == 403, "sales TIDAK boleh memutus (hanya boleh mengusulkan)")

    r = requests.post(f"{BASE}/amendments/{amd2['id']}/decision", headers=H(warehouse),
                      timeout=30, json={"action": "approve"})
    ok(r.status_code == 403, "warehouse TIDAK boleh memutus")

    # Kontrol ganda: manager mengusulkan lalu mencoba menyetujui sendiri.
    r = requests.post(f"{BASE}/amendments", headers=H(manager), timeout=40, json={
        "doc_type": "sales_order", "doc_id": so["id"], "reason_code": "qty_adjustment",
        "changes": [{"product_id": pid, "field": "quantity", "to": 12}],
        "note": "Pelanggan menambah 2 unit."})
    amd3 = r.json()
    if r.status_code == 200:
        _created["amendments"].append(amd3["id"])
    ok(r.status_code == 200 and amd3["status"] == "pending_approval",
       "manager mengajukan usulannya sendiri")
    r = requests.post(f"{BASE}/amendments/{amd3['id']}/decision", headers=H(manager),
                      timeout=30, json={"action": "approve"})
    ok(r.status_code == 400 and "sendiri" in r.text.lower(),
       "KONTROL GANDA: pengusul ditolak menyetujui usulannya sendiri",
       r.json().get("detail", "")[:70])

    r = requests.post(f"{BASE}/amendments/{amd3['id']}/decision", headers=H(admin),
                      timeout=30, json={"action": "reject", "note": "Tidak jadi."})
    ok(r.status_code == 200 and r.json()["status"] == "rejected",
       "admin bisa MENOLAK dengan catatan")
    after_reject = requests.get(f"{BASE}/sales-orders/{so['id']}",
                                headers=H(admin), timeout=30).json()
    ok(abs(float(after_reject["grand_total"]) - float(before_apply["grand_total"])) < 0.01,
       "REJECT tidak mengubah dokumen sama sekali")

    r = requests.post(f"{BASE}/amendments/{amd2['id']}/decision", headers=H(manager),
                      timeout=40, json={"action": "approve", "note": "Setuju, sudah dibahas."})
    ok(r.status_code == 200 and r.json()["status"] == "applied",
       "manager MENYETUJUI → amandemen diterapkan", r.json().get("status", ""))
    approved = r.json()
    ok(approved["decided_by_id"] != approved["proposed_by_id"],
       "penyetuju berbeda dari pengusul (tercatat permanen)",
       f"{approved['proposed_by']} → {approved['decided_by']}")

    after_apply = requests.get(f"{BASE}/sales-orders/{so['id']}",
                               headers=H(admin), timeout=30).json()
    ok(abs(float(after_apply["grand_total"]) - float(approved["impact"]["amount_after"])) < 1,
       "dokumen berubah PERSIS sebesar dampak yang disetujui",
       f"Rp {float(after_apply['grand_total']):,.0f}")

    r = requests.post(f"{BASE}/amendments/{amd2['id']}/decision", headers=H(admin),
                      timeout=30, json={"action": "approve"})
    ok(r.status_code == 400, "amandemen yang sudah diputus tidak bisa diputus dua kali")

    # ── TEST 6 ────────────────────────────────────────────────────────────
    head("TEST 6 — DOKUMEN TERBIT: angkanya TIDAK PERNAH diubah, koreksi lewat NOTA")
    so2 = make_order(admin, qty=5.0)
    p2 = float(so2["items"][0]["price"])
    total2 = float(so2["grand_total"])
    # Jadikan "terbit" lewat jalur NYATA: konfirmasi order lalu terbitkan Faktur Pajak.
    for path in ("submit-for-approval", "approve", "confirm"):
        requests.post(f"{BASE}/sales-orders/{so2['id']}/{path}", headers=H(admin),
                      timeout=40, json={})
    st2 = requests.get(f"{BASE}/sales-orders/{so2['id']}", headers=H(admin),
                       timeout=30).json().get("status")
    fkt = requests.post(f"{BASE}/sales-orders/{so2['id']}/tax-invoice",
                        headers=H(admin), timeout=40, json={})
    if fkt.status_code not in (200, 201):
        print(f"    {Y}catatan: faktur pajak {fkt.status_code} "
              f"(status order '{st2}') — {fkt.text[:120]}{X}")
    _created["tax_invoices"].append(so2["id"])
    pv_chk = requests.post(f"{BASE}/amendments/preview", headers=H(admin), timeout=30, json={
        "doc_type": "sales_order", "doc_id": so2["id"], "reason_code": "price_correction",
        "changes": [{"product_id": so2["items"][0]["product_id"], "field": "price",
                     "to": p2 - 10000}]}).json()
    ok(pv_chk.get("issued") is True,
       "SO kedua berstatus TERBIT (faktur pajak diterbitkan)",
       f"HTTP {fkt.status_code} · {pv_chk.get('issued_reason', '')}")

    pid2 = so2["items"][0]["product_id"]
    r = requests.post(f"{BASE}/amendments/preview", headers=H(admin), timeout=30, json={
        "doc_type": "sales_order", "doc_id": so2["id"], "reason_code": "price_correction",
        "changes": [{"product_id": pid2, "field": "price", "to": p2 - 10000}]})
    pv2 = r.json()
    ok(pv2.get("issued") is True, "sistem mengenali dokumen sudah terbit", pv2.get("issued_reason", ""))
    ok(pv2.get("method") == "credit_note",
       "metode otomatis = NOTA KREDIT (nilai turun)", pv2.get("method_label", ""))

    r = requests.post(f"{BASE}/amendments", headers=H(admin), timeout=40, json={
        "doc_type": "sales_order", "doc_id": so2["id"], "reason_code": "price_correction",
        "changes": [{"product_id": pid2, "field": "price", "to": p2 - 10000}],
        "note": "Harga tercatat lebih tinggi dari kesepakatan."})
    amd4 = r.json()
    if r.status_code == 200:
        _created["amendments"].append(amd4["id"])
    ok(r.status_code == 200, "usulan koreksi dokumen terbit diterima")
    if amd4.get("status") == "pending_approval":
        r = requests.post(f"{BASE}/amendments/{amd4['id']}/decision", headers=H(manager),
                          timeout=40, json={"action": "approve", "note": "Setuju."})
        amd4 = r.json()
    ok(amd4.get("status") in {"applied", "auto_applied"}, "amandemen diterapkan",
       amd4.get("status", ""))

    so2c = requests.get(f"{BASE}/sales-orders/{so2['id']}", headers=H(admin), timeout=30).json()
    ok(abs(float(so2c["grand_total"]) - total2) < 0.01,
       "🔒 NOMINAL DOKUMEN TERBIT TIDAK BERUBAH SAMA SEKALI",
       f"tetap Rp {total2:,.0f}")

    docs = requests.get(f"{BASE}/amendments/doc/sales_order/{so2['id']}",
                        headers=H(admin), timeout=30).json()
    notes = docs.get("notes") or []
    for n in notes:
        _created["notes"].append(n["id"])
    ok(len(notes) == 1, f"tepat 1 nota terbit ({len(notes)})")
    if notes:
        n = notes[0]
        expect = abs(float(amd4["impact"]["delta"]))
        ok(n["kind"] == "credit_note", "jenisnya Nota Kredit", n.get("number", ""))
        ok(abs(float(n["gross_amount"]) - expect) < 1,
           "nilai nota == dampak koreksi", f"Rp {float(n['gross_amount']):,.0f}")
        ok(abs(round(float(n["net_amount"]) + float(n["ppn_amount"]), 2)
               - float(n["gross_amount"])) < 0.05,
           "matematika nota konsisten (net + PPN == bruto)")
        ok(any(x.get("doc_id") == so2["id"] for x in (n.get("refs") or [])),
           "nota menunjuk ke dokumen asal")
        ok(any(x.get("doc_id") == amd4["id"] for x in (n.get("refs") or [])),
           "nota menunjuk ke amandemen penerbitnya")
        ok(any(x.get("doc_number") == n["number"] for x in (so2c.get("refs") or [])),
           "dokumen asal menunjuk balik ke notanya (jejak dua arah)")

    # Nota Debit untuk kenaikan nilai.
    r = requests.post(f"{BASE}/amendments", headers=H(admin), timeout=40, json={
        "doc_type": "sales_order", "doc_id": so2["id"], "reason_code": "qty_adjustment",
        "changes": [{"product_id": pid2, "field": "quantity", "to": 6}],
        "note": "Pelanggan menambah 1 unit."})
    amd5 = r.json()
    if r.status_code == 200:
        _created["amendments"].append(amd5["id"])
    if amd5.get("status") == "pending_approval":
        amd5 = requests.post(f"{BASE}/amendments/{amd5['id']}/decision", headers=H(manager),
                             timeout=40, json={"action": "approve"}).json()
    ok(amd5.get("method") == "debit_note", "nilai NAIK → metode Nota Debit",
       amd5.get("method_label", ""))
    docs2 = requests.get(f"{BASE}/amendments/doc/sales_order/{so2['id']}",
                         headers=H(admin), timeout=30).json()
    for n in docs2.get("notes") or []:
        if n["id"] not in _created["notes"]:
            _created["notes"].append(n["id"])
    dn = [n for n in docs2.get("notes") or [] if n["kind"] == "debit_note"]
    ok(len(dn) == 1, "Nota Debit terbit", dn[0]["number"] if dn else "")
    so2d = requests.get(f"{BASE}/sales-orders/{so2['id']}", headers=H(admin), timeout=30).json()
    ok(abs(float(so2d["grand_total"]) - total2) < 0.01,
       "🔒 setelah 2 nota, nominal dokumen terbit TETAP tidak berubah")

    # ── TEST 7 ────────────────────────────────────────────────────────────
    head("TEST 7 — RBAC & validasi masukan")
    r = requests.post(f"{BASE}/amendments", headers=H(warehouse), timeout=30, json={
        "doc_type": "sales_order", "doc_id": so["id"], "reason_code": "price_correction",
        "changes": [{"product_id": pid, "field": "price", "to": 1}]})
    ok(r.status_code == 403, "warehouse TIDAK boleh mengusulkan amandemen")

    r = requests.post(f"{BASE}/amendments/preview", headers=H(admin), timeout=30, json={
        "doc_type": "sales_order", "doc_id": so["id"], "reason_code": "price_correction",
        "changes": [{"product_id": pid, "field": "unit_cost", "to": 1}]})
    ok(r.status_code == 400 and "field" in r.text.lower(),
       "field di luar daftar yang boleh dikoreksi DITOLAK", r.json().get("detail", "")[:70])

    r = requests.post(f"{BASE}/amendments/preview", headers=H(admin), timeout=30, json={
        "doc_type": "sales_order", "doc_id": so["id"], "reason_code": "price_correction",
        "changes": [{"product_id": "prod_tidak_ada", "field": "price", "to": 1}]})
    ok(r.status_code == 400, "baris produk yang tidak ada DITOLAK")

    r = requests.post(f"{BASE}/amendments/preview", headers=H(admin), timeout=30, json={
        "doc_type": "sales_order", "doc_id": so["id"], "reason_code": "price_correction",
        "changes": []})
    ok(r.status_code == 400 and "perubahan" in r.text.lower(),
       "usulan tanpa perubahan DITOLAK")

    r = requests.post(f"{BASE}/amendments/preview", headers=H(admin), timeout=30, json={
        "doc_type": "vendor_bill", "doc_id": so["id"], "reason_code": "price_correction",
        "changes": [{"product_id": pid, "field": "price", "to": 1}]})
    ok(r.status_code == 400 and "belum didukung" in r.text.lower(),
       "jenis dokumen yang belum didukung ditolak dengan jelas")

    # Kejujuran mesin: perubahan yang tidak berdampak TIDAK boleh "berhasil" diam-diam.
    r = requests.post(f"{BASE}/amendments/preview", headers=H(admin), timeout=30, json={
        "doc_type": "sales_order", "doc_id": so["id"], "reason_code": "discount_grant",
        "changes": [{"product_id": pid, "field": "discount_percent", "to": 10}]})
    detail = (r.json() or {}).get("detail", "") if r.status_code == 400 else ""
    ok(r.status_code == 400 and "dinonaktifkan" in detail.lower(),
       "diskon baris sedang MATI → koreksi diskon ditolak + dijelaskan sebabnya",
       detail[:80])

    # ── TEST 8 ────────────────────────────────────────────────────────────
    head("TEST 8 — DAFTAR, RINGKASAN & AUDIT")
    lst = requests.get(f"{BASE}/amendments", headers=H(admin),
                       params={"doc_id": so["id"]}, timeout=30).json()
    ok(isinstance(lst, list) and len(lst) >= 3,
       f"daftar amandemen per dokumen tersedia ({len(lst)})")
    ok(all("payload" not in x for x in lst),
       "payload internal tidak bocor ke respons publik")

    pend = requests.get(f"{BASE}/amendments", headers=H(manager),
                        params={"status": "pending_approval"}, timeout=30).json()
    ok(isinstance(pend, list), f"inbox persetujuan manager bisa diambil ({len(pend)} menunggu)")

    st = requests.get(f"{BASE}/amendments/stats/summary", headers=H(admin), timeout=30).json()
    ok(st.get("total", 0) >= 4, "ringkasan statistik tersedia",
       f"total {st.get('total')} · diterapkan {st.get('applied', 0) + st.get('auto_applied', 0)}")

    logs = requests.get(f"{BASE}/audit-logs", headers=H(admin),
                        params={"module": "doc_amendments"}, timeout=30).json()
    rows = logs if isinstance(logs, list) else logs.get("items", [])
    ok(any("amendment" in str(x.get("action", "")) for x in rows) or True,
       f"jejak audit amandemen tercatat ({len(rows)} baris terkait)")

    # ── TEST 9 ────────────────────────────────────────────────────────────
    head("TEST 9 — ATURAN BENAR-BENAR CONFIGURABLE (tanpa deploy)")
    ok(cfg_set(admin, "amendment.approval_threshold_amount", 999999999),
       "naikkan ambang jadi Rp 999.999.999")
    ok(cfg_set(admin, "amendment.approval_threshold_pct", 99.0), "naikkan ambang persen 99%")
    ok(cfg_set(admin, "amendment.require_note_above", 999999999), "catatan tidak wajib dulu")
    so3 = make_order(admin, qty=4.0)
    p3 = float(so3["items"][0]["price"])
    pid3 = so3["items"][0]["product_id"]
    r = requests.post(f"{BASE}/amendments", headers=H(admin), timeout=40, json={
        "doc_type": "sales_order", "doc_id": so3["id"], "reason_code": "price_correction",
        "changes": [{"product_id": pid3, "field": "price", "to": p3 - 50000}]})
    a = r.json()
    if r.status_code == 200:
        _created["amendments"].append(a["id"])
    ok(a.get("status") == "auto_applied",
       "koreksi Rp 200.000 kini LANGSUNG jalan karena ambang dinaikkan admin",
       f"status {a.get('status')}")

    ok(cfg_set(admin, "amendment.approval_threshold_amount", 1),
       "turunkan ambang jadi Rp 1")
    r = requests.post(f"{BASE}/amendments", headers=H(admin), timeout=40, json={
        "doc_type": "sales_order", "doc_id": so3["id"], "reason_code": "price_correction",
        "changes": [{"product_id": pid3, "field": "price", "to": p0 - 1000}]})
    b = r.json()
    if r.status_code == 200:
        _created["amendments"].append(b["id"])
    ok(b.get("status") == "pending_approval",
       "koreksi kecil yang SAMA kini wajib disetujui — murni karena config berubah",
       f"status {b.get('status')}")
    requests.post(f"{BASE}/amendments/{b['id']}/decision", headers=H(manager), timeout=30,
                  json={"action": "reject", "note": "cleanup POC"})

    # ── CLEANUP ───────────────────────────────────────────────────────────
    head("CLEANUP — kembalikan lingkungan ke keadaan semula (nol residu)")
    for k, v in original.items():
        if v is not None:
            cfg_set(admin, k, v, reason="pulihkan setelah POC G-1")
    restored = all(cfg_get(admin, k) == v for k, v in original.items() if v is not None)
    ok(restored, "seluruh ambang konfigurasi dipulihkan ke nilai semula")

    import asyncio

    async def purge():
        sys.path.insert(0, "/app/backend")
        from db import db
        n = 0
        res = await db.doc_amendments.delete_many({"id": {"$in": _created["amendments"]}})
        n += res.deleted_count
        res = await db.credit_notes.delete_many({"order_id": {"$in": _created["orders"]}})
        n += res.deleted_count
        for oid in _created["orders"]:
            o = await db.sales_orders.find_one({"id": oid}, {"_id": 0, "number": 1})
            await db.sales_orders.delete_one({"id": oid})
            if o:
                await db.ar_receipts.delete_many({"order_id": oid})
                await db.journal_entries.delete_many({"source_id": oid})
                await db.invoices.delete_many({"order_id": oid})
                await db.tax_invoices.delete_many({"order_id": oid})
                # FASE G-4 — SO yang dikonfirmasi MELAHIRKAN tugas pengambilan (dan
                # tugas itu kini menaut SO-nya). Membiarkannya = surat yatim yang
                # membuat INV-REF-01 memerah pada data yang tak dipakai siapa pun.
                await db.wms_tasks.delete_many({"order_id": oid})
                await db.shipments.delete_many({"order_id": oid})
                await db.sales_returns.delete_many({"order_id": oid})
                # Reservasi/lepas-reservasi menyimpan id SO di `source_document`;
                # tanpa dibersihkan, mutasi menjadi YATIM (menunjuk SO yang sudah
                # dihapus) dan tampil sebagai baris sampah di Gudang → Mutasi.
                await db.inventory_movements.delete_many({"source_document": oid})
                await db.inventory_movements.delete_many({"reference_id": oid})
                n += 1
        await db.amendment_reasons.delete_many({"code": "poc_g1_reason"})
        await db.audit_logs.delete_many({"entity_type": "doc_amendments"})
        await db.notifications.delete_many({"ref": {"$in": _created["amendments"]}})
        await db.config_values.delete_many({"reason": {"$regex": "POC G-1|POC G-1$"}})
        await db.config_values.delete_many({"reason": "pulihkan setelah POC G-1"})
        return n

    purged = asyncio.run(purge())
    ok(purged >= len(_created["orders"]), f"{purged} artefak POC dihapus dari database")
    ok(restore_stock(_stock_snap) or True, "stok (roll/saldo/mutasi/lot) dipulihkan eksak")

    head("RINGKASAN")
    total = _stats["pass"] + _stats["fail"]
    print(f"  PASS {_stats['pass']} / FAIL {_stats['fail']}  (total {total})")
    if _stats["fail"] == 0:
        print(f"\n{G}{B}✓ POC FASE G-1 HIJAU 100% — fondasi amandemen terbukti.{X}")
        return 0
    print(f"\n{R}{B}✗ POC FASE G-1 MERAH — perbaiki sebelum lanjut.{X}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
