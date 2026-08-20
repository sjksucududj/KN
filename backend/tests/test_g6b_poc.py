"""FASE G-6b — **POC BUKTI-MERAH** 4 lanjutan Transaksi Antar Entitas.

Menguji lewat HTTP nyata (bukan unit test) empat kemampuan baru + invariannya:

  A. **Faktur Pajak Internal**  — keluaran penjual & masukan pembeli terbit
     BERPASANGAN, masuk rekap PPN tiap PT, dan hanya untuk transaksi ber-PPN.
  B. **Retur Antar-PT**         — jalan resmi sesudah barangnya berpindah:
     dokumen kembar, dual-control (pembuat ≠ penyetuju), jurnal pembalik dua buku,
     saldo antar-PT berkurang, roll dinilai ulang ke harga perolehan asli.
  C. **Pengingat Settlement**   — notifikasi NYATA (mengingatkan, bukan memaksa);
     umur saldo dihitung dari aktivitas nyata, bukan dari `updated_at`. Termasuk
     **KN-G6-ICA-CLOBBER**: pasangan PT yang berdagang DUA ARAH tidak boleh
     kehilangan saldo arah pertama saat arah kedua dihitung ulang.
  D. **Rapor Margin Grup**      — margin dipecah realized vs unrealized dari data
     roll nyata, dan angka yang dieliminasi konsolidasi == yang belum terealisasi.

Ditambah **BUKTI-MERAH**: pelanggaran disuntik → invarian INV-IC-03/07/08 WAJIB
MEMERAH → lalu dipulihkan. Tanpa itu, invarian bisa "hijau tapi hampa".

POC ini **tidak meninggalkan residu**: seluruh dokumen yang ia buat dihapus dan
data demo dipulihkan di akhir (dibuktikan test terakhir).

Jalankan: `cd /app/backend && python -m pytest tests/test_g6b_poc.py -q`
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
MANAGER = {"email": "manager@kainnusantara.id", "password": "demo12345"}
SALES = {"email": "sales@kainnusantara.id", "password": "demo12345"}
EPS = 0.01
STATE: dict = {}


def _login(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json=creds)
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}",
                      # Dokumen kembar hidup di DUA PT — layar & POC memakai
                      # konteks "Semua Entitas" supaya keduanya terlihat.
                      "X-Entity-Id": "all"})
    return s


def _db():
    from pymongo import MongoClient
    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli[os.environ.get("DB_NAME", "test_database")]


@pytest.fixture(scope="module")
def adm():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def mgr():
    return _login(MANAGER)


@pytest.fixture(scope="module")
def sales():
    return _login(SALES)


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    """Catat garis dasar, lalu HAPUS hanya dokumen yang dibuat POC ini."""
    db = _db()
    STATE["base_fkt"] = {d["id"] for d in db.tax_invoices.find({}, {"id": 1})}
    STATE["base_fpm"] = {d["id"] for d in db.tax_invoices_in.find({}, {"id": 1})}
    STATE["base_ret"] = {d["id"] for d in db.interco_returns.find({}, {"id": 1})}
    STATE["base_notif"] = {d["id"] for d in db.notifications.find({}, {"id": 1})}
    # Bagian C4 menerbitkan transaksi antar-PT arah balik (draf, tanpa jurnal)
    # untuk membuktikan saldo arah pertama tidak tertimpa. Dokumennya WAJIB
    # lenyap dan baris saldo dipulihkan EKSAK — kalau tidak, POC ini sendiri
    # meninggalkan residu seperti POC E-7 dulu.
    STATE["base_ict"] = {d["id"] for d in db.interco_transactions.find({}, {"id": 1})}
    STATE["base_ica"] = list(db.interco_accounts.find({}))
    yield
    # Faktur pajak & retur yang lahir dari POC → dihapus (draf retur tak berjurnal).
    new_fkt = [d["id"] for d in db.tax_invoices.find({}, {"id": 1})
               if d["id"] not in STATE["base_fkt"]]
    new_fpm = [d["id"] for d in db.tax_invoices_in.find({}, {"id": 1})
               if d["id"] not in STATE["base_fpm"]]
    new_ret = [d["id"] for d in db.interco_returns.find({}, {"id": 1})
               if d["id"] not in STATE["base_ret"]]
    new_notif = [d["id"] for d in db.notifications.find({}, {"id": 1})
                 if d["id"] not in STATE["base_notif"]]
    new_ict = [d["id"] for d in db.interco_transactions.find({}, {"id": 1})
               if d["id"] not in STATE["base_ict"]]
    if new_fkt:
        db.tax_invoices.delete_many({"id": {"$in": new_fkt}})
    if new_fpm:
        db.tax_invoices_in.delete_many({"id": {"$in": new_fpm}})
    if new_ret:
        db.interco_returns.delete_many({"id": {"$in": new_ret}})
    if new_notif:
        db.notifications.delete_many({"id": {"$in": new_notif}})
    if new_ict:
        db.interco_transactions.delete_many({"id": {"$in": new_ict}})
    if STATE.get("base_ica"):
        db.interco_accounts.delete_many({})
        db.interco_accounts.insert_many(STATE["base_ica"])
    # Cap faktur pajak pada transaksi yang dipakai POC dipulihkan.
    if STATE.get("tax_pair"):
        db.interco_transactions.update_many(
            {"pair_id": STATE["tax_pair"]},
            {"$set": {"tax_faktur_status": "", "tax_faktur_out_id": "",
                      "tax_faktur_out_number": "", "tax_faktur_in_id": "",
                      "tax_faktur_in_number": ""}})


def _txs(client):
    r = client.get(f"{BASE}/api/interco/transactions")
    assert r.status_code == 200, r.text
    return r.json()


def _integrity(only: str = "interco") -> str:
    out = subprocess.run(
        [sys.executable, "/app/scripts/verify_data_integrity.py", "--only", only],
        capture_output=True, text=True, cwd="/app")
    return out.stdout


# ═════════════════════════════════════════════════════════════════════════════
#  A. FAKTUR PAJAK INTERNAL  (tiap test MANDIRI — POC dijalankan paralel)
# ═════════════════════════════════════════════════════════════════════════════
def test_a1_alasan_terbaca_saat_belum_boleh_terbit(adm):
    """Tombol mati WAJIB punya alasan yang bisa dibaca manusia."""
    # Kandidatnya harus transaksi draf yang MEMANG ber-PPN (`tax_apply`). Dulu baris
    # ini mengambil "draf penjual pertama yang ditemukan"; sejak data demo memuat
    # transaksi dengan PENJUAL non-PKP (mode `ikut_pkp` → tanpa PPN), pilihan itu bisa
    # jatuh ke transaksi yang alasan blokirnya memang BUKAN "Faktur Internal belum
    # dibuat" melainkan "tanpa PPN". Uji ini jadi memerah bukan karena pesannya hilang,
    # tetapi karena ia menguji transaksi yang salah. Sama seperti test A2, saring
    # `tax_apply` supaya yang diuji benar-benar urutan syarat faktur pajak internal.
    draft = next((t for t in _txs(adm)
                  if t["role"] == "seller" and t["status"] == "draft"
                  and t.get("tax_apply")), None)
    assert draft, "data demo harus punya satu transaksi draf ber-PPN"
    st = adm.get(f"{BASE}/api/interco/transactions/{draft['id']}/tax-invoice").json()
    assert st["can_issue"] is False
    assert "Faktur Internal" in st["blocked_reason"], st
    r = adm.post(f"{BASE}/api/interco/transactions/{draft['id']}/tax-invoice",
                 json={"nsfp": "", "kode_transaksi": "01"})
    assert r.status_code == 400
    assert "Faktur Internal" in r.json()["detail"]


def test_a2_siklus_faktur_pajak_internal_penuh(adm):
    """Terbit berpasangan → masuk rekap PPN dua PT → tidak bisa dobel → batal."""
    cand = next((t for t in _txs(adm)
                 if t["role"] == "seller" and t["status"] in ("settled", "invoiced")
                 and t.get("tax_apply") and not t.get("tax_faktur_out_number")), None)
    assert cand, "butuh satu transaksi ber-PPN sudah difakturkan tanpa faktur pajak"
    STATE["tax_pair"] = cand["pair_id"]
    tid = cand["id"]

    r = adm.post(f"{BASE}/api/interco/transactions/{tid}/tax-invoice",
                 json={"nsfp": "", "kode_transaksi": "01"})
    assert r.status_code == 200, r.text
    out, inn = r.json()["out"], r.json()["in"]
    assert out["entity_id"] == cand["seller_entity_id"]
    assert inn["entity_id"] == cand["buyer_entity_id"]
    assert abs(out["ppn_amount"] - inn["ppn_amount"]) < EPS
    assert abs(out["dpp"] - inn["dpp"]) < EPS
    assert out["counterpart_faktur_number"] == inn["number"]
    assert out["ppn_amount"] > 0

    # Nilai fase ini: PPN antar-PT akhirnya IKUT di rekap kurang/lebih bayar tiap PT.
    vs = adm.get(f"{BASE}/api/tax/vat-summary",
                 params={"entity_id": cand["seller_entity_id"]}).json()
    assert vs["keluaran"]["ppn"] >= out["ppn_amount"] - EPS, vs
    vb = adm.get(f"{BASE}/api/tax/vat-summary",
                 params={"entity_id": cand["buyer_entity_id"]}).json()
    assert vb["masukan"]["ppn"] >= inn["ppn_amount"] - EPS, vb
    lst = adm.get(f"{BASE}/api/input-tax-invoices").json()
    assert any(x["number"] == inn["number"] for x in lst), \
        "faktur masukan internal harus tampil di daftar Faktur Pajak Masukan"

    # Tidak boleh terbit dua kali & pengganti wajib ber-alasan.
    again = adm.post(f"{BASE}/api/interco/transactions/{tid}/tax-invoice",
                     json={"nsfp": "", "kode_transaksi": "01"})
    assert again.status_code == 400 and "sudah terbit" in again.json()["detail"]
    bad = adm.post(f"{BASE}/api/interco/transactions/{tid}/tax-invoice/replace",
                   json={"reason": "abc"})
    assert bad.status_code == 400 and "Alasan" in bad.json()["detail"]

    # Bukti-merah INV-IC-07: PPN masukan digeser → invarian WAJIB memerah.
    db = _db()
    db.tax_invoices_in.update_one({"number": inn["number"]},
                                  {"$inc": {"ppn_amount": 12345.0}})
    try:
        red = _integrity()
        assert "INV-IC-07" in red and "FAIL" in red, red[-1200:]
    finally:
        db.tax_invoices_in.update_one({"number": inn["number"]},
                                      {"$inc": {"ppn_amount": -12345.0}})
    assert "FAIL 0" in _integrity()

    # Batalkan (ber-alasan) — sekaligus membersihkan jejak POC.
    c = adm.post(f"{BASE}/api/interco/transactions/{tid}/tax-invoice/cancel",
                 json={"reason": "Pembersihan POC — dokumen uji"})
    assert c.status_code == 200, c.text
    assert c.json()["out"] is None and c.json()["in"] is None


def test_a3_faktur_pajak_internal_tidak_bisa_diganti_dari_jalur_pesanan(adm):
    """Jalur pengganti umum memuat pesanan penjualan — internal tidak punya itu.

    Sebelum penjaga ini, pengguna hanya melihat 404 'Order tidak ditemukan'.
    """
    db = _db()
    f = db.tax_invoices.find_one({"source_type": "interco",
                                  "status": {"$in": ["normal", "pengganti"]}},
                                 {"_id": 0, "id": 1})
    if not f:
        pytest.skip("tidak ada faktur pajak internal aktif pada data demo")
    r = adm.post(f"{BASE}/api/tax-invoices/{f['id']}/replace", json={"reason": "uji"})
    assert r.status_code == 400
    assert "Antar Entitas" in r.json()["detail"]


# ═════════════════════════════════════════════════════════════════════════════
#  B. RETUR ANTAR-PT
# ═════════════════════════════════════════════════════════════════════════════
def test_b1_penjaga_retur(adm):
    """Belum berpindah → pakai Batalkan · melebihi sisa → ditolak · alasan wajib."""
    belum = next((t for t in _txs(adm) if t["role"] == "seller"
                  and t.get("warehouse_transfer_status") != "completed"
                  and t["status"] in ("draft", "confirmed")), None)
    assert belum, "butuh satu transaksi yang barangnya belum berpindah"
    info = adm.get(f"{BASE}/api/interco/transactions/{belum['id']}/returnable").json()
    assert info["can_return"] is False and "Batalkan" in info["blocked_reason"]

    done = next(t for t in _txs(adm) if t["role"] == "seller"
                and t.get("warehouse_transfer_status") == "completed")
    inf2 = adm.get(f"{BASE}/api/interco/transactions/{done['id']}/returnable").json()
    assert inf2["can_return"] is True, inf2
    line = inf2["lines"][0]
    assert line["qty_returned"] > 0, "data demo sudah punya retur sebagian"
    assert abs(line["qty_returnable"] - (line["qty_total"] - line["qty_returned"])) < 0.001

    over = adm.post(f"{BASE}/api/interco/returns", json={
        "interco_id": done["id"],
        "items": [{"product_id": line["product_id"],
                   "quantity": line["qty_returnable"] + 5}],
        "reason": "Uji batas jumlah retur"})
    assert over.status_code == 400 and "melebihi" in over.json()["detail"]

    noreason = adm.post(f"{BASE}/api/interco/returns", json={
        "interco_id": done["id"],
        "items": [{"product_id": line["product_id"], "quantity": 1}],
        "reason": "x"})
    assert noreason.status_code == 400 and "Alasan retur" in noreason.json()["detail"]


def test_b2_dual_control_dan_draf_tanpa_jurnal(adm):
    """Pembuat ≠ penyetuju; draf tidak boleh berjurnal; draf bisa dibatalkan."""
    done = next(t for t in _txs(adm) if t["role"] == "seller"
                and t.get("warehouse_transfer_status") == "completed")
    info = adm.get(f"{BASE}/api/interco/transactions/{done['id']}/returnable").json()
    line = next(l for l in info["lines"] if l["qty_returnable"] > 0)
    r = adm.post(f"{BASE}/api/interco/returns", json={
        "interco_id": done["id"],
        "items": [{"product_id": line["product_id"], "quantity": 1}],
        "reason": "Uji pemisahan tugas POC"})
    assert r.status_code == 200, r.text
    ret = r.json()["returner"]
    assert ret["status"] == "draft"
    assert r.json()["receiver"]["number"] != ret["number"], "dokumen kembar wajib beda nomor"

    bad = adm.post(f"{BASE}/api/interco/returns/{ret['id']}/approve", json={"note": ""})
    assert bad.status_code == 400 and "sendiri" in bad.json()["detail"]

    db = _db()
    n = db.journal_entries.count_documents(
        {"source_type": "interco_return",
         "source_id": {"$regex": f"^{ret['return_pair_id']}:"}})
    assert n == 0, "draf tidak boleh berjurnal — uang belum berubah"

    c = adm.post(f"{BASE}/api/interco/returns/{ret['id']}/cancel",
                 json={"reason": "Pembersihan POC — draf uji"})
    assert c.status_code == 200 and c.json()["returner"]["status"] == "cancelled"


def test_b3_siklus_retur_demo_penuh(adm):
    """Retur data demo: 4 blok jurnal seimbang, saldo berkurang, roll dinilai ulang."""
    rows = adm.get(f"{BASE}/api/interco/returns").json()
    done = [r for r in rows if r["status"] == "completed" and r["role"] == "returner"]
    assert done, f"data demo harus punya satu retur selesai (dapat {len(rows)} baris)"
    # FASE E-9 — data demo kini punya DUA retur selesai dengan sifat berbeda:
    #   (a) retur barang normal  → nilai perolehan asli > 0, ada jurnal sisi barang;
    #   (b) retur barang hasil RETUR PELANGGAN yang sudah dihapus-bukukan (Rp 0)
    #       → tidak ada nilai barang yang berpindah, jadi sengaja TANPA jurnal barang.
    # Uji ini menguji siklus (a); yang (b) dijaga POC FASE E-9 + INV-IC-08 (yang kini
    # menuntut kesesuaian dua arah antara nilai tercatat dan ada/tidaknya jurnal).
    valued = [r for r in done if float(r.get("returned_cost") or 0) > 0]
    assert valued, "data demo harus punya satu retur selesai bernilai (returned_cost > 0)"
    ret = valued[0]
    assert ret["warehouse_transfer_status"] == "completed"
    assert float(ret["returned_cost"]) > 0, "biaya perolehan asli wajib tercatat"

    db = _db()
    for blk in ("seller", "buyer", "goods_out", "goods_in"):
        je = db.journal_entries.find_one(
            {"source_type": "interco_return",
             "source_id": f"{ret['return_pair_id']}:{blk}"},
            {"_id": 0, "total_debit": 1, "total_credit": 1})
        assert je, f"jurnal retur blok {blk} tidak ada"
        assert abs(je["total_debit"] - je["total_credit"]) < EPS

    origin = next(t for t in _txs(adm)
                  if t["pair_id"] == ret["origin_pair_id"] and t["role"] == "seller")
    assert abs(float(origin["returned_amount"]) - float(ret["grand_total"])) < EPS
    for a in adm.get(f"{BASE}/api/interco/accounts").json():
        assert float(a["outstanding"]) <= float(a["gross_amount"]) + EPS

    # Roll kembali ke harga perolehan ASLI (kalau tidak: GL persediaan ≠ subledger).
    trf = db.warehouse_transfers.find_one(
        {"interco_return_pair_id": ret["return_pair_id"], "status": "completed"},
        {"_id": 0, "id": 1})
    assert trf
    rolls = list(db.inventory_rolls.find(
        {"acquired.ref_id": trf["id"], "owner_entity_id": ret["seller_entity_id"]},
        {"_id": 0, "cost_basis": 1}))
    assert rolls, "roll retur harus kembali ke PT penjual"
    for rr in rolls:
        cb = rr.get("cost_basis") or {}
        assert cb.get("source") == "interco_return"
        assert not cb.get("interco_pair_id"), \
            "tanda pair dilepas supaya tidak dihitung lagi sebagai stok antar-PT"


def test_b4_bukti_merah_inv_ic_08(adm):
    """Suntik retur melebihi transaksi asal → INV-IC-08 WAJIB memerah."""
    db = _db()
    ret = db.interco_returns.find_one({"status": "completed", "role": "returner"},
                                      {"_id": 0, "id": 1, "items": 1})
    assert ret, "butuh retur selesai pada data demo"
    orig = float(ret["items"][0]["quantity"])
    db.interco_returns.update_one({"id": ret["id"]},
                                  {"$set": {"items.0.quantity": orig + 9999}})
    try:
        red = _integrity()
        assert "INV-IC-08" in red and "FAIL" in red, red[-1200:]
    finally:
        db.interco_returns.update_one({"id": ret["id"]},
                                      {"$set": {"items.0.quantity": orig}})
    assert "FAIL 0" in _integrity()


# ═════════════════════════════════════════════════════════════════════════════
#  C. PENGINGAT SETTLEMENT (mengingatkan, bukan memaksa)
# ═════════════════════════════════════════════════════════════════════════════
def test_c1_umur_saldo_dari_aktivitas_nyata_dan_pengingat_terkirim(adm):
    """KN-G6-IDLE-FAKE: umur dari aktivitas nyata + notifikasi benar-benar ada."""
    accs = adm.get(f"{BASE}/api/interco/accounts").json()
    assert accs
    for a in accs:
        assert "last_activity_at" in a, "baris saldo wajib menyimpan aktivitas terakhir"
        assert a.get("reminder_limit_days") is not None
    data = adm.get(f"{BASE}/api/interco/reminders").json()
    assert {"rows", "overdue", "checked"}.issubset(data.keys())
    for r in data["rows"]:
        assert r["idle_days"] >= 0 and r["limit_days"] >= 0

    payables = [a for a in accs if a["role"] == "payable" and float(a["outstanding"]) > EPS]
    assert payables, "butuh satu pasangan PT dengan utang terbuka"
    a = payables[0]
    r = adm.post(f"{BASE}/api/interco/accounts/{a['from_entity_id']}/"
                 f"{a['to_entity_id']}/remind", json={"note": ""})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["notified"] is True and d["outstanding"] > 0
    db = _db()
    n = db.notifications.find_one({"type": "interco_settlement_idle"},
                                  {"_id": 0, "body": 1, "link": 1})
    assert n, "notifikasi pengingat harus benar-benar ada (bukan hanya respons OK)"
    assert n["link"] == "interco-transactions"
    assert "tidak bergerak" in n["body"] and "Buat Settlement" in n["body"]

    again = adm.post(f"{BASE}/api/interco/accounts/{a['from_entity_id']}/"
                     f"{a['to_entity_id']}/remind", json={"note": ""}).json()
    assert again["deduped"] is True, "pengingat yang belum dibaca tidak dikirim dua kali"


def test_c2_pasangan_tanpa_saldo_ditolak_dengan_kalimat_jelas(adm):
    """Pengingat untuk saldo nol adalah pesan palsu — harus ditolak, bukan dikirim."""
    accs = adm.get(f"{BASE}/api/interco/accounts").json()
    assert accs
    payer = accs[0]["from_entity_id"]
    r = adm.post(f"{BASE}/api/interco/accounts/{payer}/ent_tidak_ada_poc/remind",
                 json={"note": ""})
    assert r.status_code == 400, r.text
    assert "sudah nol" in r.json()["detail"]


def test_c3_job_pengingat_terdaftar(adm):
    """Fungsi pengingat harus benar-benar terjadwal, bukan kode mati."""
    data = adm.get(f"{BASE}/api/scheduler/jobs").json()
    jobs = data.get("jobs") if isinstance(data, dict) else data
    ids = [j["id"] for j in jobs]
    assert "interco_settlement_reminder" in ids, ids


def test_c4_dua_arah_dagang_tidak_saling_menimpa_saldo(adm):
    """KN-G6-ICA-CLOBBER: dagang DUA ARAH tidak boleh menghapus utang yang nyata.

    Cacat aslinya: id baris saldo dulu `ica_{X}_{Y}` **tanpa penanda peran**, jadi
    piutang arah A→B dan utang arah B→A menempati SATU dokumen. Begitu pasangan PT
    yang sama berdagang arah balik — hal yang normal lewat Permintaan Internal
    ("stok saya habis, kirim dari PT sebelah", POC E-7d) — recompute arah kedua
    MENIMPA arah pertama dan utang Rp 1.766.010 pada data demo menjadi Rp 0 **tanpa
    satu pun pesan**. Cukup satu DRAF arah balik untuk melakukannya, dan tidak satu
    pun dari 229 invarian menangkapnya (INV-IC-02/04 hanya memeriksa baris yang ADA,
    bukan baris yang HILANG).
    """
    accs = adm.get(f"{BASE}/api/interco/accounts").json()
    payables = [a for a in accs if a["role"] == "payable" and float(a["outstanding"]) > EPS]
    assert payables, "butuh satu pasangan PT dengan utang terbuka"
    ap = payables[0]
    debtor, creditor = ap["from_entity_id"], ap["to_entity_id"]
    before = float(ap["outstanding"])

    # ARAH BALIK: PT yang berutang sekarang menjual ke PT penagihnya. Draf lalu
    # DIBATALKAN — jalur paling bersih yang memicu hitung-ulang arah balik tanpa
    # satu rupiah pun berpindah (draf tidak berjurnal). Pemicu yang sama muncul di
    # dunia nyata pada PINJAMAN & PINDAH ASET antar-PT
    # (`interco_money_service.refresh_pair_exposure` menghitung KEDUA arah
    # berurutan) — dulu panggilan kedua selalu menimpa yang pertama.
    src = next(t for t in _txs(adm) if t["role"] == "seller"
               and t["seller_entity_id"] == creditor and t["buyer_entity_id"] == debtor
               and t.get("items"))
    pid = src["items"][0]["product_id"]
    r = adm.post(f"{BASE}/api/interco/transactions", json={
        "seller_entity_id": debtor, "buyer_entity_id": creditor,
        "pricing_mode": "at_cost",
        "items": [{"product_id": pid, "quantity": 1}]})
    assert r.status_code == 200, r.text
    rev_pair = r.json()["pair_id"]
    rev_id = r.json()["seller"]["id"]
    STATE["c4_pair"] = rev_pair
    c = adm.post(f"{BASE}/api/interco/transactions/{rev_id}/cancel",
                 json={"note": "Pembersihan POC — pemicu hitung ulang arah balik"})
    assert c.status_code == 200, c.text

    # ── INI YANG PALING PENTING: uangnya tidak boleh hilang ─────────────────
    after = adm.get(f"{BASE}/api/interco/accounts").json()
    still = next((a for a in after if a["id"] == ap["id"]), None)
    assert still, f"baris utang {ap['id']} HILANG setelah arah balik dihitung ulang"
    assert abs(float(still["outstanding"]) - before) < EPS, (
        f"utang Rp {before:,.2f} tertimpa menjadi Rp {float(still['outstanding']):,.2f} "
        f"hanya karena arah balik dihitung ulang — inilah KN-G6-ICA-CLOBBER")

    # Identitas baris WAJIB memuat arah dagang + peran; kalau tidak, tabrakan pasti
    # terulang begitu ada arah balik.
    assert ap["id"].endswith("_ap"), ap["id"]
    assert ap.get("pair_key") == f"{creditor}>{debtor}", ap
    mirror = next((a for a in accs if a["role"] == "receivable"
                   and a.get("pair_key") == ap.get("pair_key")), None)
    assert mirror and mirror["id"].endswith("_ar"), "cermin piutang wajib ada & ber-peran"
    assert abs(float(mirror["outstanding"]) - before) < EPS

    # Arah balik punya barisnya SENDIRI (bukan menumpang baris arah pertama).
    rev_key = f"{debtor}>{creditor}"
    rev_rows = [a for a in after if a.get("pair_key") == rev_key]
    assert len(rev_rows) == 2, f"arah balik wajib punya piutang+utang sendiri: {rev_rows}"
    assert {a["role"] for a in rev_rows} == {"receivable", "payable"}
    assert ap["id"] not in {a["id"] for a in rev_rows}

    # Tidak boleh ada dua baris beperan sama yang berbagi satu arah dagang.
    seen = set()
    for a in after:
        k = (a["role"], a.get("pair_key"))
        assert k not in seen, f"dua baris {a['role']} berbagi arah {a.get('pair_key')}"
        seen.add(k)

    # Pengingat tetap menemukan utang yang benar (bukan “saldo sudah nol”).
    rem = adm.get(f"{BASE}/api/interco/reminders").json()
    assert any(x["payer_entity_id"] == debtor and x["payee_entity_id"] == creditor
               and abs(float(x["outstanding"]) - before) < EPS for x in rem["rows"]), rem

    # Bersihkan draf arah balik lalu pastikan invarian tetap hijau.
    db = _db()
    db.interco_transactions.delete_many({"pair_id": rev_pair})
    assert "FAIL 0" in _integrity()


# ═════════════════════════════════════════════════════════════════════════════
#  D. RAPOR MARGIN GRUP
# ═════════════════════════════════════════════════════════════════════════════
def test_d1_identitas_margin_dan_eliminasi(adm):
    """margin = jual − HPP · unrealized + realized = margin · eliminasi = unrealized."""
    rep = adm.get(f"{BASE}/api/interco/margin-report").json()
    t = rep["totals"]
    assert abs(t["margin"] - (t["subtotal"] - t["cost"])) < 0.05
    assert abs(t["margin"] - (t["unrealized_margin"] + t["realized_margin"])) < 0.05
    # Eliminasi konsolidasi menghapus LABA antar-PT yang belum terealisasi. Margin
    # NEGATIF (rugi) TIDAK dieliminasi — konservatisme — tetapi wajib dilaporkan
    # terpisah (`unrealized_loss` + alasannya), bukan hilang diam-diam.
    assert abs(t["elimination_gap"]) < 0.05, \
        f"eliminasi {t['eliminated_unrealized']} != laba belum terealisasi {t['unrealized_profit']}"
    assert abs(t["unrealized_margin"]
               - (t["unrealized_profit"] - t["unrealized_loss"])) < 0.05
    if t.get("unrealized_loss", 0) > 0.05:
        assert t.get("loss_not_eliminated") and t.get("loss_reason"), \
            "rugi belum terealisasi wajib diberi keterangan, bukan didiamkan"
    assert rep["rows"], "rapor margin tidak boleh kosong pada data demo"
    for r in rep["rows"]:
        assert 0.0 <= r["unsold_ratio"] <= 1.0
        assert abs(r["margin"] - (r["subtotal"] - r["cost"])) < 0.05
        assert abs(r["unrealized_margin"] - r["margin"] * r["unsold_ratio"]) < 0.05
        assert abs(r["elimination_gap"]) < 0.05, r["number"]


def test_d2_retur_keluar_dari_hitungan_margin(adm):
    """Barang yang diretur bukan penjualan intra-grup lagi — nilainya harus lepas."""
    rows = adm.get(f"{BASE}/api/interco/returns").json()
    ret = next((r for r in rows if r["status"] == "completed"
                and r["role"] == "returner"), None)
    assert ret, "butuh retur selesai pada data demo"
    origin = next(t for t in _txs(adm)
                  if t["pair_id"] == ret["origin_pair_id"] and t["role"] == "seller")
    rep = adm.get(f"{BASE}/api/interco/margin-report").json()
    mrow = next(r for r in rep["rows"] if r["pair_id"] == ret["origin_pair_id"])
    assert abs(mrow["subtotal"]
               - (float(origin["subtotal"]) - float(origin["returned_subtotal"]))) < 0.05
    assert mrow["returned_subtotal"] > 0


def test_d3_bukti_merah_inv_ic_03(adm):
    """Suntik rasio belum-terjual yang salah → INV-IC-03 WAJIB memerah."""
    db = _db()
    e = db.intercompany_eliminations.find_one(
        {"source_g6_pair_id": {"$exists": True, "$ne": None},
         "g6_unsold_ratio": {"$exists": True}},
        {"_id": 0, "id": 1, "g6_unsold_ratio": 1})
    assert e, "entri eliminasi G-6 wajib menyimpan rasio yang dipakainya"
    old = e["g6_unsold_ratio"]
    db.intercompany_eliminations.update_one({"id": e["id"]},
                                            {"$set": {"g6_unsold_ratio": 0.42}})
    try:
        red = _integrity()
        assert "INV-IC-03" in red and "FAIL" in red, red[-1200:]
    finally:
        db.intercompany_eliminations.update_one({"id": e["id"]},
                                                {"$set": {"g6_unsold_ratio": old}})
    assert "FAIL 0" in _integrity()


# ═════════════════════════════════════════════════════════════════════════════
#  E. RBAC + NOL RESIDU
# ═════════════════════════════════════════════════════════════════════════════
def test_e1_sales_tidak_boleh_menyentuh_retur_antar_pt(sales):
    r1 = sales.get(f"{BASE}/api/interco/returns")
    assert r1.status_code == 403, r1.text
    r2 = sales.post(f"{BASE}/api/interco/returns",
                    json={"interco_id": "x", "items": [], "reason": "coba"})
    assert r2.status_code == 403


def test_e2_invarian_global_hijau_dan_nol_residu(adm):
    out = subprocess.run(
        [sys.executable, "/app/scripts/verify_data_integrity.py"],
        capture_output=True, text=True, cwd="/app").stdout
    assert "FAIL 0" in out and "WARN 0" in out, out[-2500:]
    db = _db()
    live = db.interco_returns.count_documents(
        {"status": {"$in": ["draft", "approved"]},
         "id": {"$nin": list(STATE.get("base_ret") or [])}})
    assert live == 0, "POC tidak boleh meninggalkan retur menggantung"
