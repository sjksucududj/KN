"""FASE G-6 — **POC BUKTI-MERAH** untuk 11 User Story (US1..US11).

Bukan sekadar test unit — ini POC yang menjalankan skenario nyata dari plan
`docs/KN_36_PLAN_FASE_G6_ANTAR_ENTITAS.md` di atas backend, membuktikan bahwa:

  * US1  — antar-PT diperlakukan JUAL-BELI (bukan pindah gudang)
  * US2  — dokumen kembar lahir (PO internal ↔ SO/SJ/Invoice)
  * US3  — 3 dokumen sisi penjual saling menunjuk
  * US4  — harga khusus dari kontrak internal (`fixed_price`) — ubah kontrak, ubah harga
  * US5  — saldo antar-PT kapan saja
  * US6  — settlement/netting satu dokumen menutup banyak transaksi
  * US7  — margin antar-PT dieliminasi konsolidasi (unrealized profit)
  * US8  — barang tetap lewat jalur gudang biasa
  * US9  — ambang persetujuan admin
  * US10 — jejak dokumen dua arah + timeline
  * US11 — isolasi lintas-PT (PT ketiga → 403) + invarian INV-IC-01..05

Jalankan: `pytest -xvs /app/backend/tests/test_g6_poc.py`

Bila SEMUA pass, fase G-6 siap ditutup.
"""
from __future__ import annotations

import asyncio
import sys
import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
MANAGER = {"email": "manager@kainnusantara.id", "password": "demo12345"}
WAREHOUSE = {"email": "warehouse@kainnusantara.id", "password": "demo12345"}


def _login(creds: dict) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json=creds)
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin_client():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def manager_client():
    return _login(MANAGER)


@pytest.fixture(scope="module")
def warehouse_client():
    return _login(WAREHOUSE)


@pytest.fixture(scope="module", autouse=True)
def clean_slate():
    """Bersihkan koleksi G-6 sebelum POC, lalu PULIHKAN keadaan semula setelahnya.

    POC ini memindahkan kepemilikan roll (US8b — jembatan gudang), jadi ia WAJIB
    mengembalikan stok persis seperti sebelum uji (POC-RESIDU-01): tanpa itu setiap
    `gate.sh --full` akan menyusutkan stok demo dan melahirkan roll potongan tak
    bertuan.

    Ia juga menghapus dokumen G-6 supaya hitungan asersinya deterministik — dan
    karena data demo G-6 (dari `seed_realistic.seed_interco`) ikut terhapus, dokumen
    + jurnal + eliminasi + tugas gudang demo itu **disnapshot lalu dipulihkan** di
    akhir. Kalau tidak: jurnal demo hilang sementara roll-nya sudah pindah PT →
    WARN `INV-GL-DRIFT` muncul sampai seseorang menjalankan seed ulang (persis
    yang terjadi sebelum pemulihan ini dipasang).
    """
    import os
    from pymongo import MongoClient
    sys.path.insert(0, "/app/backend")
    from poc_stock_guard import snapshot_stock, restore_stock

    client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "test_database")]

    JE_Q = {"source_type": {"$in": ["interco_transaction", "interco_settlement"]}}
    ELIM_Q = {"source_g6_pair_id": {"$exists": True}}
    TRF_Q = {"interco_pair_id": {"$ne": None}}
    CONTRACT_Q = {"partner_kind": "entity"}

    # FASE G-6b — dokumen turunan (retur & faktur pajak internal) WAJIB ikut
    # disingkirkan+dipulihkan. Kalau tidak: transaksi induknya hilang sementara
    # returnya tinggal, dan INV-IC-07/08 memerah karena menaut pair yang tak ada.
    RET_Q = {}
    FKT_Q = {"source_type": "interco"}
    JE_RET_Q = {"source_type": "interco_return"}
    TRF_RET_Q = {"interco_return_pair_id": {"$ne": None}}

    def _wipe():
        for c in ("interco_transactions", "interco_accounts", "interco_settlements",
                  "interco_returns"):
            db[c].delete_many({})
        db.tax_invoices.delete_many(FKT_Q)
        db.tax_invoices_in.delete_many(FKT_Q)
        db.intercompany_eliminations.delete_many(ELIM_Q)
        db.journal_entries.delete_many(JE_Q)
        db.journal_entries.delete_many(JE_RET_Q)
        db.warehouse_transfers.delete_many(TRF_RET_Q)
        db.supplier_contracts.delete_many(
            {"partner_kind": "entity", "notes": {"$regex": "^POC-G6"}})
        # Tugas gudang yang lahir dari transaksi antar-PT (jembatan US8)
        db.warehouse_transfers.delete_many(TRF_Q)

    # ── snapshot keadaan G-6 milik data demo ────────────────────────────────
    before = {
        "interco_transactions": list(db.interco_transactions.find({})),
        "interco_accounts": list(db.interco_accounts.find({})),
        "interco_settlements": list(db.interco_settlements.find({})),
        "interco_returns": list(db.interco_returns.find({})),
        "tax_invoices": list(db.tax_invoices.find(FKT_Q)),
        "tax_invoices_in": list(db.tax_invoices_in.find(FKT_Q)),
        "intercompany_eliminations": list(db.intercompany_eliminations.find(ELIM_Q)),
        "journal_entries": list(db.journal_entries.find(
            {"source_type": {"$in": ["interco_transaction", "interco_settlement",
                                     "interco_return"]}})),
        "warehouse_transfers": list(db.warehouse_transfers.find(
            {"$or": [TRF_Q, TRF_RET_Q]})),
        "supplier_contracts": list(db.supplier_contracts.find(CONTRACT_Q)),
    }
    _wipe()
    stock = snapshot_stock()
    yield
    _wipe()
    restore_stock(stock)
    # ── pulihkan dokumen demo G-6 apa adanya (termasuk _id) ────────────────
    pulih = 0
    for coll, docs in before.items():
        if not docs:
            continue
        ids = [d["_id"] for d in docs]
        db[coll].delete_many({"_id": {"$in": ids}})
        db[coll].insert_many(docs, ordered=False)
        pulih += len(docs)
    if pulih:
        print(f"\n  [poc-g6] data demo antar-PT dipulihkan ({pulih} dokumen) — nol residu.")


STATE: dict = {}   # dipakai lintas-test (POC ordered)


# ═══════════════════════════════════════════════════════════════════════════
# US1 — antar-PT diperlakukan jual-beli (bukan pindah gudang)
# ═══════════════════════════════════════════════════════════════════════════
def test_US1_meta_menyebut_jual_beli(admin_client):
    r = admin_client.get(f"{BASE}/api/interco/meta")
    assert r.status_code == 200
    m = r.json()
    # Ada mode harga → tanda ini "jual-beli", bukan sekadar mutasi gudang.
    assert m["pricing_modes"], "pricing_modes wajib ada (indikasi jual-beli)"
    # Ada 8 status siklus jual-beli
    assert len(m["statuses"]) >= 6


# ═══════════════════════════════════════════════════════════════════════════
# US4 — Harga dari kontrak internal (fixed_price) — SIAPKAN kontrak dulu
# ═══════════════════════════════════════════════════════════════════════════
def test_US4_setup_internal_contract(admin_client):
    """Terbitkan kontrak internal PT-KSC (penjual) ↔ CV-Kanda (pembeli)
    untuk Batik Mega dengan tariff_rate = 60.000/yard."""
    payload = {
        "contract_type": "internal",
        "partner_id": "ent_kanda",
        "partner_name": "CV Kanda Suka",
        "title": "POC-G6 · Harga Internal Batik Mega",
        "product_id": "prod_batik_mega",
        "tariff_basis": "lumpsum",
        "tariff_rate": 60000,
        "tariff_qty_source": "output",
        "status": "active",
        "notes": "POC-G6 kontrak harga internal",
    }
    r = admin_client.post(f"{BASE}/api/supplier-contracts", json=payload,
                          headers={"X-Entity-Id": "ent_ksc"})
    assert r.status_code in (200, 201), r.text
    STATE["contract_id"] = r.json()["id"]
    assert r.json()["partner_kind"] == "entity"


def test_US4_fixed_price_ambil_harga_kontrak(admin_client):
    """Terbitkan transaksi fixed_price → HARUS memakai tariff_rate 60.000."""
    r = admin_client.post(
        f"{BASE}/api/interco/transactions",
        json={
            "seller_entity_id": "ent_ksc",
            "buyer_entity_id": "ent_kanda",
            "pricing_mode": "fixed_price",
            "items": [{"product_id": "prod_batik_mega", "quantity": 10}],
            "submit_now": True,
        },
    )
    assert r.status_code == 200, r.text
    seller = r.json()["seller"]
    assert seller["items"][0]["unit_price"] == 60000.0, "harga wajib ikut kontrak"
    assert seller["items"][0]["price_source"] == "fixed_price"
    STATE["us4_pair_id"] = r.json()["pair_id"]
    STATE["us4_seller_id"] = seller["id"]
    STATE["us4_buyer_id"] = r.json()["buyer"]["id"]
    # 10 * 60000 = 600.000 + PPN 11% = 666.000
    assert seller["subtotal"] == 600000.0
    assert seller["tax_amount"] == 66000.0
    assert seller["grand_total"] == 666000.0


def test_US4_fixed_price_ubah_kontrak_ubah_harga_baru(admin_client):
    """Ubah tariff_rate kontrak → transaksi BARU pakai harga baru."""
    cid = STATE["contract_id"]
    r = admin_client.patch(f"{BASE}/api/supplier-contracts/{cid}",
                           json={"tariff_rate": 75000})
    assert r.status_code == 200
    r2 = admin_client.post(
        f"{BASE}/api/interco/transactions",
        json={
            "seller_entity_id": "ent_ksc",
            "buyer_entity_id": "ent_kanda",
            "pricing_mode": "fixed_price",
            "items": [{"product_id": "prod_batik_mega", "quantity": 4}],
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["seller"]["items"][0]["unit_price"] == 75000.0


# ═══════════════════════════════════════════════════════════════════════════
# US2 & US3 — dokumen kembar
# ═══════════════════════════════════════════════════════════════════════════
def test_US2_US3_dokumen_kembar(admin_client):
    pair_id = STATE["us4_pair_id"]
    r = admin_client.get(f"{BASE}/api/interco/transactions/{STATE['us4_seller_id']}")
    assert r.status_code == 200
    doc = r.json()
    seller, buyer = doc["seller"], doc["buyer"]
    assert seller["role"] == "seller" and buyer["role"] == "buyer"
    assert seller["pair_id"] == buyer["pair_id"] == pair_id
    # Saling menunjuk
    assert seller["counterpart_id"] == buyer["id"]
    assert buyer["counterpart_id"] == seller["id"]
    # Nomor kembar tercatat di masing-masing dokumen
    assert seller["counterpart_number"] == buyer["number"]
    assert buyer["counterpart_number"] == seller["number"]


# ═══════════════════════════════════════════════════════════════════════════
# US5 — Saldo antar-PT
# ═══════════════════════════════════════════════════════════════════════════
def test_US5_saldo_antar_pt(admin_client):
    r = admin_client.get(f"{BASE}/api/interco/accounts")
    assert r.status_code == 200
    rows = r.json()
    # Ada baris receivable KSC→Kanda dan payable Kanda→KSC
    rec = [a for a in rows if a["role"] == "receivable"
           and a["from_entity_id"] == "ent_ksc" and a["to_entity_id"] == "ent_kanda"]
    pay = [a for a in rows if a["role"] == "payable"
           and a["from_entity_id"] == "ent_kanda" and a["to_entity_id"] == "ent_ksc"]
    assert rec and pay, "saldo receivable & payable wajib ada"
    # INV-IC-02: sama besar
    assert abs(rec[0]["outstanding"] - pay[0]["outstanding"]) < 0.01


# ═══════════════════════════════════════════════════════════════════════════
# US6 — Settlement/netting menutup banyak transaksi
# ═══════════════════════════════════════════════════════════════════════════
def test_US6_netting_dua_transaksi(admin_client):
    # Terbitkan 1 transaksi tambahan yang langsung confirmed supaya jelas ada ≥2.
    admin_client.post(
        f"{BASE}/api/interco/transactions",
        json={
            "seller_entity_id": "ent_ksc",
            "buyer_entity_id": "ent_kanda",
            "pricing_mode": "at_cost",
            "items": [{"product_id": "prod_batik_mega",
                       "quantity": 5, "unit_price": 20000}],
            "submit_now": True,
        },
    )
    # Ambil semua transaksi open KSC→Kanda
    r = admin_client.get(
        f"{BASE}/api/interco/transactions",
        params={"role": "seller", "entity_id": "ent_ksc"})
    open_docs = [d for d in r.json()
                 if d["seller_entity_id"] == "ent_ksc"
                 and d["buyer_entity_id"] == "ent_kanda"
                 and d["status"] in ("confirmed", "shipped", "received", "invoiced")]
    assert len(open_docs) >= 2, "butuh ≥2 transaksi open untuk demo netting"
    picks = [{"interco_id": d["id"]} for d in open_docs[:2]]
    r2 = admin_client.post(
        f"{BASE}/api/interco/settlements",
        json={"payer_entity_id": "ent_kanda", "payee_entity_id": "ent_ksc",
              "transactions": picks, "method": "netting"},
    )
    assert r2.status_code == 200, r2.text
    settlement = r2.json()
    # Kedua transaksi tercatat di applied
    assert len(settlement["applied"]) == 2
    # Cek: kedua transaksi berstatus settled
    for p in picks:
        d = admin_client.get(
            f"{BASE}/api/interco/transactions/{p['interco_id']}").json()
        assert d["seller"]["status"] == "settled"
        assert d["buyer"]["status"] == "settled"


# ═══════════════════════════════════════════════════════════════════════════
# US9 — Ambang persetujuan admin
# ═══════════════════════════════════════════════════════════════════════════
def test_US9_high_value_perlu_admin(manager_client):
    """Manager submit_now transaksi > ambang 100 jt → DITOLAK."""
    r = manager_client.post(
        f"{BASE}/api/interco/transactions",
        json={
            "seller_entity_id": "ent_ksc",
            "buyer_entity_id": "ent_kanda",
            "pricing_mode": "at_cost",
            "items": [{"product_id": "prod_batik_mega",
                       "quantity": 10, "unit_price": 15000000}],
            "submit_now": True,
        },
    )
    # Manager: rank=1, high-value threshold=100jt → butuh admin(rank=2) → 400
    assert r.status_code == 400, r.text
    body = r.json()
    assert "persetujuan" in body["detail"].lower() or "admin" in body["detail"].lower()


def test_US9_high_value_admin_boleh(admin_client):
    """Admin boleh submit high-value langsung."""
    r = admin_client.post(
        f"{BASE}/api/interco/transactions",
        json={
            "seller_entity_id": "ent_ksc",
            "buyer_entity_id": "ent_kanda",
            "pricing_mode": "at_cost",
            "items": [{"product_id": "prod_batik_mega",
                       "quantity": 10, "unit_price": 15000000}],
            "submit_now": True,
        },
    )
    assert r.status_code == 200, r.text
    STATE["us9_pair_id"] = r.json()["pair_id"]


# ═══════════════════════════════════════════════════════════════════════════
# US10 — Jejak dokumen dua arah
# ═══════════════════════════════════════════════════════════════════════════
def test_US10_jejak_dokumen_dua_arah(admin_client):
    r = admin_client.get(
        f"{BASE}/api/interco/transactions/{STATE['us4_seller_id']}")
    d = r.json()
    s, b = d["seller"], d["buyer"]
    # Cek referensi silang
    assert s["counterpart_id"] == b["id"]
    assert b["counterpart_id"] == s["id"]
    # Cek timeline: minimum ada created_at & confirmed_at (submit_now=True)
    assert s.get("created_at")
    assert s.get("confirmed_at")
    # settlement history nyambung
    r2 = admin_client.get(f"{BASE}/api/interco/settlements",
                           params={"entity_id": "ent_ksc"})
    settlements = r2.json()
    assert any(any(app["interco_id"] in (s["id"], b["id"])
                   for app in st.get("applied", []))
               for st in settlements), "settlement tidak tercermin di dokumen"


# ═══════════════════════════════════════════════════════════════════════════
# US11 — Isolasi lintas-PT + invarian
# ═══════════════════════════════════════════════════════════════════════════
def test_US11_isolasi_lintas_pt(warehouse_client):
    """Warehouse user coba `create` (butuh 'create'), ditolak 403.
    Warehouse dibolehkan view/ship/receive saja per permissions_config.
    """
    r = warehouse_client.post(
        f"{BASE}/api/interco/transactions",
        json={
            "seller_entity_id": "ent_ksc",
            "buyer_entity_id": "ent_kanda",
            "pricing_mode": "at_cost",
            "items": [{"product_id": "prod_batik_mega",
                       "quantity": 1, "unit_price": 10000}],
        },
    )
    assert r.status_code == 403, r.text


def test_US11_invarian_INV_IC_01_02_04_05():
    """Panggil MongoDB langsung untuk verifikasi invarian akuntansi."""
    import os
    from pymongo import MongoClient
    client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "test_database")]

    # INV-IC-01: setiap JE interco seimbang
    cnt_unbal = 0
    for je in db.journal_entries.find(
            {"source_type": {"$in": ["interco_transaction",
                                      "interco_settlement"]},
             "status": "posted"}):
        if abs((je.get("total_debit") or 0) - (je.get("total_credit") or 0)) > 0.01:
            cnt_unbal += 1
    assert cnt_unbal == 0, f"{cnt_unbal} JE tidak seimbang (INV-IC-01 FAIL)"

    # INV-IC-02: IC-AR total = IC-AP total
    ar = 0.0; ap = 0.0
    for je in db.journal_entries.find(
            {"source_type": {"$in": ["interco_transaction",
                                      "interco_settlement"]},
             "status": "posted"}):
        for line in je.get("lines", []):
            if line["account_code"] == "1-1250":
                ar += line["debit"] - line["credit"]
            if line["account_code"] == "2-1250":
                ap += line["credit"] - line["debit"]
    assert abs(ar - ap) < 0.01, \
        f"INV-IC-02 FAIL: IC-AR net={ar:,.2f} != IC-AP net={ap:,.2f}"

    # INV-IC-04: interco_accounts.outstanding == recomputed dari transaksi terbuka
    for acc in db.interco_accounts.find({"role": "receivable"}):
        docs = list(db.interco_transactions.find({
            "seller_entity_id": acc["from_entity_id"],
            "buyer_entity_id": acc["to_entity_id"],
            "role": "seller",
            "status": {"$in": ["confirmed", "shipped", "received", "invoiced"]},
        }))
        gross = sum(d.get("grand_total", 0) for d in docs)
        settled = sum(d.get("settled_amount", 0) for d in docs)
        expected = gross - settled
        assert abs(expected - acc.get("outstanding", 0)) < 0.01, \
            f"INV-IC-04 FAIL: {acc['id']} outstanding={acc['outstanding']} != {expected}"

    # INV-IC-05: PPN Keluaran (2-1200) == PPN Masukan (1-1500) untuk interco_transaction
    out_ppn = in_ppn = 0.0
    for je in db.journal_entries.find(
            {"source_type": "interco_transaction", "status": "posted"}):
        for line in je.get("lines", []):
            if line["account_code"] == "2-1200":
                out_ppn += line["credit"]
            if line["account_code"] == "1-1500":
                in_ppn += line["debit"]
    assert abs(out_ppn - in_ppn) < 0.01, \
        f"INV-IC-05 FAIL: PPN Keluaran={out_ppn} != PPN Masukan={in_ppn}"


# ═══════════════════════════════════════════════════════════════════════════
# US7 — Unrealized profit elimination (KONSOLIDASI GRUP)
# ═══════════════════════════════════════════════════════════════════════════
def _db():
    import os
    from pymongo import MongoClient
    client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return client[os.environ.get("DB_NAME", "test_database")]


def test_US7_unrealized_profit_eliminated(admin_client):
    """Margin antar-PT WAJIB tereliminasi di konsolidasi — TANPA menekan tombol.

    Sejak eliminasi disinkronkan otomatis saat transaksi dikonfirmasi/dilunasi,
    `sync-g6` menjadi alat **backfill/verifikasi**: dia boleh melaporkan
    `created=0` selama SEMUA pair sudah tertutup. Yang diuji di sini adalah
    kebenarannya, bukan siapa yang menekan tombol:

      * setiap pair non-draf punya TEPAT SATU entri eliminasi yang seimbang;
      * entri itu mengeliminasi pendapatan sebesar `subtotal`;
      * bila ada margin (harga jual > HPP) ada baris **unrealized profit** di 1-1300.
    """
    r = admin_client.post(f"{BASE}/api/consolidation/sync-g6")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pairs_seen"] >= 1
    assert (body["created"] + body["updated"] + body["skipped_existing"]) >= 1, \
        "sync harus melihat pair yang sudah/baru tereliminasi"

    db = _db()
    pairs = list(db.interco_transactions.find(
        {"role": "seller", "status": {"$nin": ["draft", "cancelled"]}}))
    assert pairs, "butuh minimal satu pair aktif"
    for p in pairs:
        elims = list(db.intercompany_eliminations.find(
            {"source_g6_pair_id": p["pair_id"]}))
        assert len(elims) == 1, \
            f"pair {p.get('number')} harus punya 1 eliminasi, ada {len(elims)}"
        e = elims[0]
        assert e["balanced"] is True, f"eliminasi {e['id']} tidak seimbang"
        rev = sum(l["debit"] for l in e["lines"] if l["account_code"] == "4-1000")
        assert abs(rev - float(p.get("subtotal") or 0)) < 0.01, \
            "pendapatan intra-grup harus dieliminasi penuh"
        cogs = sum(l["credit"] for l in e["lines"] if l["account_code"] == "5-1000")
        margin = round(float(p.get("subtotal") or 0) - cogs, 2)
        inv_credit = sum(l["credit"] for l in e["lines"]
                         if l["account_code"] in ("1-1300", "1-1310"))
        inv_debit = sum(l["debit"] for l in e["lines"]
                        if l["account_code"] in ("1-1300", "1-1310"))
        if margin > 0.005:
            assert abs(inv_credit - margin) < 0.01, \
                "unrealized profit harus mengurangi nilai persediaan pembeli"
        elif margin < -0.005:
            assert abs(inv_debit - abs(margin)) < 0.01, \
                "jual di bawah HPP harus menaikkan kembali nilai persediaan"


def test_US7b_eliminasi_ikut_mengecil_setelah_settlement(admin_client):
    """Sesudah lunas, eliminasi TIDAK boleh lagi menghapus IC-AR/IC-AP.

    Bukti-merah untuk bug klasik "eliminasi sekali jadi": entri auto yang dibuat
    saat konfirmasi memuat sisa piutang antar-PT; setelah settlement sisa itu
    NOL, jadi baris IC-AR/IC-AP harus hilang — kalau tidak, neraca konsolidasi
    menghapus saldo yang sudah tidak ada.
    """
    db = _db()
    settled = list(db.interco_transactions.find({"role": "seller", "status": "settled"}))
    assert settled, "POC US6 seharusnya sudah melunasi minimal satu transaksi"
    for p in settled:
        e = db.intercompany_eliminations.find_one({"source_g6_pair_id": p["pair_id"]})
        assert e, f"pair lunas {p.get('number')} tetap harus punya eliminasi margin"
        ic_lines = [l for l in e["lines"] if l["account_code"] in ("1-1250", "2-1250")]
        assert not ic_lines, \
            f"eliminasi {e['id']} masih menghapus IC-AR/IC-AP padahal sudah lunas"
        assert e["balanced"] is True


def test_US8b_jembatan_gudang_tanpa_dobel_jurnal(admin_client):
    """US8 — barang berjalan lewat TUGAS GUDANG, jurnal TIDAK dobel.

    Sebelum jembatan ini: memindahkan barangnya berarti membuat transfer antar-PT
    yang memposting jurnal at-cost M-3 **lagi**, sehingga IC-AR/IC-AP & persediaan
    tercatat dua kali untuk satu barang. Yang dibuktikan di sini:
      1. tugas gudang lahir menaut `interco_pair_id`;
      2. saat disetujui, `je_intercompany.posted == False` dengan alasan tercatat;
      3. TIDAK ada jurnal `inter_company_transfer` untuk transfer itu;
      4. roll di PT pembeli **dinilai ulang** ke harga beli internal (GL == subledger);
      5. status pair maju otomatis ke `received` (bukan tombol manual).
    """
    db = _db()
    avail = sum(float(r.get("length_remaining") or 0) for r in db.inventory_rolls.find(
        {"product_id": "prod_batik_mega", "owner_entity_id": "ent_ksc",
         "status": "available"}))
    assert avail >= 5, f"butuh stok available ≥5 yard di KSC (ada {avail})"

    r = admin_client.post(
        f"{BASE}/api/interco/transactions",
        json={"seller_entity_id": "ent_ksc", "buyer_entity_id": "ent_kanda",
              "pricing_mode": "fixed_price",
              "items": [{"product_id": "prod_batik_mega", "quantity": 5}],
              "submit_now": True},
    )
    assert r.status_code == 200, r.text
    pair = r.json()["pair_id"]
    sid = r.json()["seller"]["id"]
    unit_price = r.json()["seller"]["items"][0]["unit_price"]
    subtotal = r.json()["seller"]["subtotal"]
    STATE["us8b_seller_id"] = sid
    STATE["us8b_pair"] = pair

    def _sub_value(entity_id: str) -> float:
        return round(sum(float(x.get("length_remaining") or 0) *
                         float(x.get("unit_cost") or x.get("base_unit_cost") or 0)
                         for x in db.inventory_rolls.find(
                             {"owner_entity_id": entity_id,
                              "status": {"$in": ["available", "reserved", "committed",
                                                  "picked", "packed", "quarantine", "hold"]}})), 2)

    before_buyer = _sub_value("ent_kanda")

    r2 = admin_client.post(
        f"{BASE}/api/interco/transactions/{sid}/warehouse-task", json={"note": ""})
    assert r2.status_code == 200, r2.text
    trf = r2.json()
    assert trf["interco_pair_id"] == pair
    STATE["trf_id"] = trf["id"]

    # Tugas ganda harus DITOLAK (satu perpindahan fisik per transaksi)
    r_dup = admin_client.post(
        f"{BASE}/api/interco/transactions/{sid}/warehouse-task", json={"note": ""})
    assert r_dup.status_code == 400, r_dup.text

    r3 = admin_client.post(f"{BASE}/api/transfers/{trf['id']}/approve",
                           json={"approved_by": "Budi Santoso"})
    assert r3.status_code == 200, r3.text
    je = r3.json()["je_intercompany"]
    assert je["posted"] is False, "jurnal at-cost M-3 TIDAK boleh diposting lagi"
    assert "G-6" in (je.get("skipped_reason") or ""), je
    assert je["revalued_rolls"] >= 1

    assert db.journal_entries.count_documents(
        {"source_type": "inter_company_transfer",
         "source_id": {"$regex": trf["id"]}}) == 0, "ada jurnal dobel at-cost"

    moved = list(db.inventory_rolls.find({"acquired.ref_id": trf["id"],
                                          "owner_entity_id": "ent_kanda"}))
    assert moved, "roll tidak berpindah ke PT pembeli"
    for m in moved:
        assert abs(float(m["unit_cost"]) - float(unit_price)) < 0.01, \
            "roll pembeli wajib dinilai ulang ke harga beli internal"

    after_buyer = _sub_value("ent_kanda")
    assert abs((after_buyer - before_buyer) - subtotal) < 1.0, \
        (f"kenaikan nilai subledger pembeli {after_buyer - before_buyer:,.2f} harus "
         f"sama dengan nilai dokumen {subtotal:,.2f} (GL 1-1300 == subledger)")

    d = admin_client.get(f"{BASE}/api/interco/transactions/{sid}").json()
    assert d["seller"]["status"] == "received"
    assert d["buyer"]["status"] == "received"
    assert d["seller"].get("warehouse_transfer_code") == trf["code"]

    # Jurnal yang MENGIKUTI BARANG: HPP penjual + transit→persediaan pembeli
    def _gl(entity_id: str, code: str) -> float:
        tot = 0.0
        for je in db.journal_entries.find(
                {"source_type": "interco_transaction", "entity_id": entity_id,
                 "source_id": {"$regex": f"^{pair}:"}}):
            for l in je.get("lines", []):
                if l["account_code"] == code:
                    tot += float(l.get("debit") or 0) - float(l.get("credit") or 0)
        return round(tot, 2)

    assert db.journal_entries.count_documents(
        {"source_type": "interco_transaction", "source_id": f"{pair}:cogs"}) == 1
    assert db.journal_entries.count_documents(
        {"source_type": "interco_transaction", "source_id": f"{pair}:receipt"}) == 1
    assert abs(_gl("ent_kanda", "1-1310")) < 0.01, \
        "saldo 'dalam perjalanan' harus nol setelah barang diterima"
    assert abs(_gl("ent_kanda", "1-1300") - subtotal) < 0.01, \
        "GL persediaan pembeli harus naik sebesar nilai dokumen (== subledger)"
    assert _gl("ent_ksc", "1-1300") < 0, "persediaan penjual harus berkurang saat barang keluar"


def test_US8c_jurnal_pair_bisa_dibaca_layar(admin_client):
    """Endpoint bukti akuntansi per pair (dipakai Detail Panel).

    Bug yang ditutup: layar memanggil `/api/gl/entries` yang TIDAK ADA sehingga
    blok jurnal diam-diam kosong — user tidak pernah melihat buktinya.

    Sekaligus mengunci **pemisahan waktu**: transaksi yang barangnya belum berjalan
    punya jurnal dokumen (penjual & pembeli) tetapi BELUM punya jurnal HPP/penerimaan.
    """
    sid = STATE["us4_seller_id"]
    r = admin_client.get(f"{BASE}/api/interco/transactions/{sid}/journal")
    assert r.status_code == 200, r.text
    j = r.json()
    for side in ("seller", "buyer"):
        assert j[side], f"jurnal buku {side} wajib ada"
        tot_d = sum(l["debit"] for l in j[side]["lines"])
        tot_c = sum(l["credit"] for l in j[side]["lines"])
        assert abs(tot_d - tot_c) < 0.01, f"jurnal {side} tidak seimbang"
    # Pembeli mencatat barang DALAM PERJALANAN (1-1310), bukan persediaan (1-1300)
    kode_pembeli = {l["account_code"] for l in j["buyer"]["lines"]}
    assert "1-1310" in kode_pembeli, "pembeli harus memakai Persediaan Dalam Perjalanan"
    assert "1-1300" not in kode_pembeli, "persediaan pembeli belum boleh naik"
    assert j["cogs"] is None, "HPP penjual baru boleh ada setelah barang keluar"
    assert j["receipt"] is None, "jurnal penerimaan baru ada setelah barang diterima"
    assert j["eliminations"], "eliminasi grup wajib terlihat dari layar"
    assert isinstance(j["settlement_entries"], list)
    assert isinstance(j["warehouse_tasks"], list)

    # Pair yang barangnya SUDAH berpindah: HPP + penerimaan ada, transit bersih
    sid2 = STATE["us8b_seller_id"]
    j2 = admin_client.get(f"{BASE}/api/interco/transactions/{sid2}/journal").json()
    assert j2["cogs"], "HPP penjual wajib ada setelah barang keluar gudang"
    assert j2["receipt"], "jurnal penerimaan wajib ada setelah barang diterima"
    assert j2["warehouse_tasks"], "tugas gudang wajib terlihat di layar"
    kode_receipt = {l["account_code"] for l in j2["receipt"]["lines"]}
    assert {"1-1300", "1-1310"} <= kode_receipt, "penerimaan = transit → persediaan"


def test_US8d_receive_manual_tanpa_barang_ditolak(admin_client):
    """"Tandai Diterima" tidak boleh mendahului barangnya.

    Kalau status bisa dimajukan tanpa perpindahan fisik, persediaan pembeli naik
    untuk barang yang tidak ada di gudang mana pun (drift GL↔subledger).
    """
    r = admin_client.post(
        f"{BASE}/api/interco/transactions",
        json={"seller_entity_id": "ent_ksc", "buyer_entity_id": "ent_kanda",
              "pricing_mode": "at_cost",
              "items": [{"product_id": "prod_batik_mega", "quantity": 1,
                         "unit_price": 30000}],
              "submit_now": True},
    )
    assert r.status_code == 200, r.text
    sid = r.json()["seller"]["id"]
    rs = admin_client.post(f"{BASE}/api/interco/transactions/{sid}/ship", json={"note": ""})
    assert rs.status_code == 200, rs.text
    rr = admin_client.post(f"{BASE}/api/interco/transactions/{sid}/receive", json={"note": ""})
    assert rr.status_code == 400, rr.text
    detail = rr.json()["detail"].lower()
    assert "tugas gudang" in detail, detail


def test_US9b_batal_membalik_jurnal_dengan_alasan(admin_client):
    """Batal setelah dikonfirmasi WAJIB ber-alasan & membalik jurnal dua buku.

    Sebelumnya `cancel` hanya mengganti status: pendapatan + piutang antar-PT
    tetap tinggal di buku untuk transaksi yang sudah dibatalkan.
    """
    db = _db()
    r = admin_client.post(
        f"{BASE}/api/interco/transactions",
        json={"seller_entity_id": "ent_ksc", "buyer_entity_id": "ent_kanda",
              "pricing_mode": "at_cost",
              "items": [{"product_id": "prod_batik_mega", "quantity": 2,
                         "unit_price": 50000}],
              "submit_now": True},
    )
    assert r.status_code == 200, r.text
    pair = r.json()["pair_id"]
    sid = r.json()["seller"]["id"]
    assert db.intercompany_eliminations.count_documents({"source_g6_pair_id": pair}) == 1

    r0 = admin_client.post(f"{BASE}/api/interco/transactions/{sid}/cancel",
                           json={"note": ""})
    assert r0.status_code == 400, "batal tanpa alasan harus ditolak"
    assert "alasan" in r0.json()["detail"].lower()

    r1 = admin_client.post(f"{BASE}/api/interco/transactions/{sid}/cancel",
                           json={"note": "Salah PT pembeli — dibatalkan Keuangan"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["reversed_journals"] >= 2

    revs = list(db.journal_entries.find(
        {"source_type": "interco_transaction",
         "source_id": {"$regex": f"^{pair}:.*:reversal$"}}))
    assert len(revs) >= 2
    for je in revs:
        assert abs(float(je["total_debit"]) - float(je["total_credit"])) < 0.01

    # Dampak bersih pair ini NOL di semua akun (jurnal + pembalikannya)
    net = {}
    for je in db.journal_entries.find(
            {"source_type": "interco_transaction",
             "source_id": {"$regex": f"^{pair}:"}}):
        for l in je.get("lines", []):
            net[l["account_code"]] = round(
                net.get(l["account_code"], 0.0) + float(l["debit"]) - float(l["credit"]), 2)
    for code, v in net.items():
        assert abs(v) < 0.01, f"akun {code} masih bergerak {v} setelah pembatalan"

    assert db.intercompany_eliminations.count_documents(
        {"source_g6_pair_id": pair}) == 0, "eliminasi pair yang dibatalkan harus hilang"


# ═══════════════════════════════════════════════════════════════════════════
# US8 — Barang tetap lewat jalur gudang (tanpa dobel mutasi)
# ═══════════════════════════════════════════════════════════════════════════
def test_US8_no_double_stock_mutation():
    """Setelah confirm interco, TIDAK boleh ada mutasi stok otomatis
    dari G-6 (mutasi fisik tetap lewat warehouse_transfers). Cek: tidak
    ada `stock_movements` dengan source_type='interco_transaction'.
    """
    import os
    from pymongo import MongoClient
    client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "test_database")]
    cnt = db.stock_movements.count_documents({"source_type": "interco_transaction"})
    assert cnt == 0, (
        f"G-6 tidak boleh membuat mutasi stok otomatis (ditemukan {cnt}). "
        f"Mutasi fisik tetap lewat warehouse_transfers.")


# ═══════════════════════════════════════════════════════════════════════════
# BUKTI-MERAH — invarian INV-IC-01..06 WAJIB memerah saat dilanggar
# ═══════════════════════════════════════════════════════════════════════════
def _integrity_ic():
    """Jalankan lapisan invarian antar-PT saja; balikkan (returncode, output)."""
    import subprocess
    p = subprocess.run(
        [sys.executable, "/app/scripts/verify_data_integrity.py", "--only=interco"],
        capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout + p.stderr


def test_ZY_bukti_merah_invarian_ic():
    """Invarian yang tidak pernah bisa memerah = invarian palsu.

    Untuk tiap invarian: suntik SATU pelanggaran nyata di database → pastikan
    lapisan `--only=interco` melaporkan FAIL untuk invarian ITU → pulihkan dan
    pastikan hijau lagi.
    """
    db = _db()
    rc, out = _integrity_ic()
    assert "FAIL 0" in out, f"kondisi awal harus hijau:\n{out[-2500:]}"

    # ── INV-IC-03: geser nilai eliminasi (unrealized profit salah) ──────────
    e = db.intercompany_eliminations.find_one(
        {"source_g6_pair_id": {"$exists": True, "$ne": None}})
    assert e, "butuh entri eliminasi G-6"
    lines_asli = e["lines"]
    rusak = [dict(l) for l in lines_asli]
    for l in rusak:
        if l["account_code"] == "4-1000":
            l["debit"] = round(float(l["debit"]) + 12345.0, 2)
            break
    db.intercompany_eliminations.update_one({"id": e["id"]}, {"$set": {"lines": rusak}})
    rc, out = _integrity_ic()
    assert "INV-IC-03" in out and "[FAIL]" in out, f"INV-IC-03 tidak memerah:\n{out[-2500:]}"
    db.intercompany_eliminations.update_one({"id": e["id"]}, {"$set": {"lines": lines_asli}})

    # ── INV-IC-04: geser saldo pasangan PT ─────────────────────────────────
    acc = db.interco_accounts.find_one({"role": "receivable"})
    assert acc, "butuh saldo pasangan PT"
    asli = float(acc.get("outstanding") or 0)
    db.interco_accounts.update_one({"id": acc["id"]},
                                   {"$set": {"outstanding": round(asli + 777777, 2)}})
    rc, out = _integrity_ic()
    assert "INV-IC-04" in out and "[FAIL]" in out, f"INV-IC-04 tidak memerah:\n{out[-2500:]}"
    db.interco_accounts.update_one({"id": acc["id"]}, {"$set": {"outstanding": asli}})

    # ── INV-IC-06: suntik jurnal at-cost dobel untuk tugas gudang tertaut ──
    trf_id = STATE.get("trf_id")
    assert trf_id, "butuh tugas gudang dari US8b"
    db.journal_entries.insert_one({
        "id": "je_poc_g6_dobel", "number": "JE-POC-G6-DOBEL",
        "date": "2026-07-30", "source_type": "inter_company_transfer",
        "source_id": f"{trf_id}:src", "entity_id": "ent_ksc", "status": "posted",
        "lines": [{"account_code": "1-1250", "debit": 1000.0, "credit": 0.0},
                  {"account_code": "1-1300", "debit": 0.0, "credit": 1000.0}],
        "total_debit": 1000.0, "total_credit": 1000.0,
        "description": "POC bukti-merah dobel posting", "created_by": "poc",
    })
    rc, out = _integrity_ic()
    assert "INV-IC-06" in out and "[FAIL]" in out, f"INV-IC-06 tidak memerah:\n{out[-2500:]}"
    db.journal_entries.delete_one({"id": "je_poc_g6_dobel"})

    # ── INV-IC-01: hapus jurnal buku pembeli (dokumen membebani satu PT) ───
    pair = STATE["us4_pair_id"]
    je_buyer = db.journal_entries.find_one(
        {"source_type": "interco_transaction", "source_id": f"{pair}:buyer"})
    assert je_buyer, "butuh jurnal buku pembeli"
    db.journal_entries.delete_one({"_id": je_buyer["_id"]})
    rc, out = _integrity_ic()
    assert "INV-IC-01" in out and "[FAIL]" in out, f"INV-IC-01 tidak memerah:\n{out[-2500:]}"
    db.journal_entries.insert_one(je_buyer)

    # ── pulih total ────────────────────────────────────────────────────────
    rc, out = _integrity_ic()
    assert "FAIL 0" in out, f"gagal pulih setelah bukti-merah:\n{out[-3000:]}"
    assert rc == 0


def test_ZZ_poc_ringkasan(admin_client):
    """Ringkasan akhir: total dokumen G-6, saldo, settlement, eliminasi."""
    import os
    from pymongo import MongoClient
    client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "test_database")]
    ict = db.interco_transactions.count_documents({})
    ica = db.interco_accounts.count_documents({})
    ics = db.interco_settlements.count_documents({})
    el = db.intercompany_eliminations.count_documents(
        {"source_g6_pair_id": {"$exists": True, "$ne": None}})
    print(f"\n\n=== POC G-6 RINGKASAN ===")
    print(f"  interco_transactions: {ict}")
    print(f"  interco_accounts:     {ica}")
    print(f"  interco_settlements:  {ics}")
    print(f"  eliminations G-6:     {el}")
    assert ict > 0 and ica > 0 and ics > 0 and el > 0
