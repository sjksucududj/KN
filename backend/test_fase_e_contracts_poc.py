#!/usr/bin/env python3
"""
POC ISOLASI — FASE E: SOURCING BERBASIS KONTRAK (PS-06 · E-01/E-02/E-03)
========================================================================
Membuktikan CORE Fase E lewat **HTTP API nyata** + assert **DB nyata** SEBELUM UI
dibangun. Tidak ada mock, tidak ada angka karangan. Self-cleanup di akhir agar
`scripts/verify_data_integrity.py` tetap pristine.

Keputusan pemilik yang diuji (sesi 2026-07-26):
  * **E-01** — `supplier_items` WAJIB mendukung **impor massal** (CSV + XLSX), bukan
    hanya CRUD manual: pratinjau → validasi baris (alasan per baris) → commit.
  * **E-02** — kunci logis **(supplier_id, supplier_sku)** unik ⇒ impor **idempotent**
    (jalan ke-2: `created=0`, `updated=N`).
  * **E-03** — konversi satuan supplier → satuan dasar KN disimpan eksplisit.
  * PR baris ber-mode `makloon` → **1 klik membuka Wizard Makloon ter-prefill**
    (bahan/mitra/kontrak/qty diturunkan dari Resep Proses secara terbalik).

Cakupan (user story pemilik → bukti teknis):
  1. Kontrak PEMBELIAN (`contract_type=purchase`) per supplier×produk + validitas + MOQ.
  2. Resolver kontrak aktif: paling spesifik menang; kontrak kedaluwarsa diabaikan.
  3. `supplier_items` CRUD + kunci unik (supplier + kode) ditegakkan.
  4. Pencarian barang KN dari **KODE SUPPLIER** (`/supplier-items/lookup`).
  5. Impor massal CSV: pratinjau menolak baris invalid dengan ALASAN (SKU KN tak ada,
     faktor konversi ≤ 0, duplikat dalam berkas, supplier_sku kosong).
  6. Impor commit + **idempotent** (jalan ke-2 created=0/updated=N) + unggah **XLSX**.
  7. PR CAMPUR: baris `purchase` + baris `makloon` dalam satu PR; validasi mode.
  8. Realisasi SEBAGIAN → PO: hanya baris purchase terpilih; PO membawa jejak sourcing
     (contract_id, supplier_item_id, supplier_sku, harga dari kontrak, expected_grade).
  9. Status realisasi turunan: open → partially_realized → realized (PR `converted`).
 10. Prefill Wizard Makloon dari baris PR (reverse lookup resep) + realisasi ke Order Makloon
     yang tertaut PR (`pr_id`/`pr_line_no`).
 11. Idempotensi & pagar: realisasi ulang baris yang penuh ditolak; output langkah akhir
     wajib = produk yang diminta PR.
 12. Budget Control R6.3 tetap berlaku pada PO hasil realisasi (mode `block` menolak).
 13. RBAC: warehouse boleh lihat barang supplier tapi TIDAK boleh impor/ubah;
     sales tidak punya akses sama sekali; sales tidak boleh realisasi.
 14. Proteksi hapus: barang supplier yang sudah dipakai PO → 409.
 15. Invarian INV-SRC-01..05 hijau setelah semua transaksi.

Jalankan: cd /app && python backend/test_fase_e_contracts_poc.py
"""
import asyncio
import io
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

BASE = os.environ.get("BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
ENTITY = "ent_ksc"
WH = "wh_jakarta"

MARK = "FASEEPOC"
SUP_A, SUP_B = "sup_fasee_a", "sup_fasee_b"
MK_TENUN = "mak_fasee_tenun"
P_YARN, P_GREY, P_DYE = "prod_fasee_yarn", "prod_fasee_grey", "prod_fasee_dye"
PRODUCTS = [P_YARN, P_GREY, P_DYE]
RECIPE = "prcp_fasee_tenun"
YARN_COST = 52000.0
YARN_QTY = 400.0

PASS, FAIL = [], []


def ok(m):
    PASS.append(m)
    print(f"  \u2705 [PASS] {m}")


def bad(m):
    FAIL.append(m)
    print(f"  \u274c [FAIL] {m}")


def info(m):
    print(f"  \u2139  {m}")


def head(m):
    print(f"\n\033[96m\033[1m{m}\033[0m")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now(timezone.utc).date().isoformat()


def plus_days(n):
    return (datetime.now(timezone.utc).date() + timedelta(days=n)).isoformat()


def near(a, b, tol=0.02):
    try:
        return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))
    except (TypeError, ValueError):
        return False


def login(email="admin@kainnusantara.id", password="demo12345"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def sess(email="admin@kainnusantara.id"):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {login(email)}"})
    return s


# ── Setup / cleanup ──────────────────────────────────────────────────────────
async def cleanup(db):
    prs = await db.purchase_requisitions.find({"reason": {"$regex": MARK}},
                                              {"_id": 0, "id": 1}).to_list(200)
    pr_ids = [p["id"] for p in prs]
    pos = await db.purchase_orders.find(
        {"$or": [{"source_pr_id": {"$in": pr_ids}}, {"notes": {"$regex": MARK}}]},
        {"_id": 0, "id": 1}).to_list(200)
    po_ids = [p["id"] for p in pos]
    for pid in po_ids:
        await db.journal_entries.delete_many({"source_id": {"$regex": pid}})
    await db.wms_tasks.delete_many({"reference_id": {"$in": po_ids}})
    await db.inbound_tasks.delete_many({"po_id": {"$in": po_ids}}) if "inbound_tasks" in await db.list_collection_names() else None
    await db.purchase_orders.delete_many({"id": {"$in": po_ids}})
    await db.purchase_requisitions.delete_many({"id": {"$in": pr_ids}})

    mkos = await db.makloon_orders.find({"notes": {"$regex": MARK}}, {"_id": 0, "id": 1}).to_list(200)
    mko_ids = [m["id"] for m in mkos]
    for oid in mko_ids:
        await db.journal_entries.delete_many({"source_id": {"$regex": oid}})
    bills = await db.vendor_bills.find({"makloon_order_id": {"$in": mko_ids}},
                                       {"_id": 0, "id": 1}).to_list(200)
    for b in bills:
        await db.journal_entries.delete_many({"source_id": b["id"]})
    await db.vendor_bills.delete_many({"makloon_order_id": {"$in": mko_ids}})
    await db.makloon_orders.delete_many({"id": {"$in": mko_ids}})

    lots = await db.inventory_lots.find({"product_id": {"$in": PRODUCTS}},
                                        {"_id": 0, "id": 1}).to_list(500)
    lot_ids = [x["id"] for x in lots]
    await db.inventory_lots.delete_many({"product_id": {"$in": PRODUCTS}})
    if lot_ids:
        await db.inventory_lots.update_many({}, {"$pull": {"parent_lot_ids": {"$in": lot_ids}}})
        await db.inventory_lots.update_many({}, {"$pull": {"child_lot_ids": {"$in": lot_ids}}})
    await db.inventory_rolls.delete_many({"product_id": {"$in": PRODUCTS}})
    await db.inventory_movements.delete_many({"product_id": {"$in": PRODUCTS}})
    await db.inventory_balances.delete_many({"product_id": {"$in": PRODUCTS}})
    await db.products.delete_many({"id": {"$in": PRODUCTS}})
    await db.supplier_items.delete_many({"supplier_id": {"$in": [SUP_A, SUP_B]}})
    await db.supplier_contracts.delete_many({"notes": {"$regex": MARK}})
    await db.suppliers.delete_many({"id": {"$in": [SUP_A, SUP_B]}})
    await db.makloons.delete_many({"id": MK_TENUN})
    await db.process_recipes.delete_many({"id": RECIPE})
    await db.budgets.delete_many({"note": {"$regex": MARK}})


async def make_masters(db):
    base = {"category": "Kain", "price": 0.0, "entity_id": ENTITY, "status": "active",
            "grade": "A", "created_at": now_iso(), "updated_at": now_iso()}
    specs = [
        (P_YARN, "POCE-YARN", "POC-E Benang Katun 30s", "kg", "yarn", 0, 0, YARN_COST),
        (P_GREY, "POCE-GREY", "POC-E Kain Grey Katun", "yard", "grey", 120.0, 1.15, 0.0),
        (P_DYE, "POCE-DYE", "POC-E Obat Celup Reaktif", "kg", "yarn", 0, 0, 95000.0),
    ]
    for pid, sku, name, unit, stage, gsm, lebar, hpp in specs:
        await db.products.update_one({"id": pid}, {"$set": {
            **base, "id": pid, "sku": sku, "name": name, "base_unit": unit, "stage": stage,
            "fabric_type": "woven", "gramasi": gsm, "lebar": lebar, "harga_pokok": hpp,
            "reorder_point": 0.0, "reorder_qty": 0.0}}, upsert=True)
    for sid, name, city in ((SUP_A, "POC-E Supplier Benang Utama", "Bandung"),
                            (SUP_B, "POC-E Supplier Kimia", "Surabaya")):
        await db.suppliers.update_one({"id": sid}, {"$set": {
            "id": sid, "code": f"SUP-{sid[-3:]}", "name": name, "city": city,
            "pic_name": "Bpk. Uji", "phone": "0812-9000-0001", "npwp": "",
            "entity_id": ENTITY, "status": "active",
            "created_at": now_iso(), "updated_at": now_iso()}}, upsert=True)
    await db.makloons.update_one({"id": MK_TENUN}, {"$set": {
        "id": MK_TENUN, "code": "MAK-POCE", "name": "POC-E Mitra Tenun", "process_types": ["tenun"],
        "entity_id": ENTITY, "status": "active", "default_tariff": 0.0,
        "created_at": now_iso(), "updated_at": now_iso()}}, upsert=True)
    await db.process_recipes.update_one({"id": RECIPE}, {"$set": {
        "id": RECIPE, "name": "POC-E Tenun: Benang → Grey", "process_type": "tenun",
        "input_product_id": P_YARN, "input_stage": "yarn",
        "output_product_id": P_GREY, "output_stage": "grey",
        "yield_factor": 3.8, "waste_pct": 4, "byproduct_pct": 2,
        "default_makloon_id": MK_TENUN, "default_tariff": 0.0, "tariff_unit": "output",
        "aux_cost_default": 0, "formula": "", "entity_id": ENTITY, "status": "active",
        "created_at": now_iso(), "updated_at": now_iso()}}, upsert=True)
    from services.roll_service import create_inbound_roll
    await create_inbound_roll(P_YARN, WH, ENTITY, YARN_QTY, lot=f"{MARK}-YARN", unit="kg",
                              acquired_via="initial", ref_id=MARK, unit_cost=YARN_COST,
                              created_by="poc", lot_source="manual")


async def main():  # noqa: C901 — satu skrip POC lengkap (protokol repo)
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await cleanup(db)
    await make_masters(db)

    s = sess()
    ok("Login admin@kainnusantara.id")
    s_mgr = sess("manager@kainnusantara.id")
    s_wh = sess("warehouse@kainnusantara.id")
    s_sales = sess("sales@kainnusantara.id")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 1 — Kontrak PEMBELIAN (contract_type=purchase) per supplier × produk")

    def mk_contract(payload):
        return s.post(f"{API}/supplier-contracts",
                      json={**payload, "notes": MARK, "entity_id": ENTITY}, timeout=30)

    r = mk_contract({"contract_type": "purchase", "partner_id": SUP_A,
                     "title": "Kontrak benang katun 30s 2026", "product_id": P_YARN,
                     "tariff_basis": "kg", "tariff_rate": 49500, "tariff_qty_source": "input",
                     "moq": 100, "lead_time_days": 7, "payment_term_code": "NET30",
                     "valid_from": today(), "valid_to": plus_days(180)})
    ct_yarn = r.json() if r.ok else {}
    if r.ok and str(ct_yarn.get("contract_number", "")).startswith("KSC/SCT-") \
            and ct_yarn.get("contract_type") == "purchase":
        ok(f"Kontrak pembelian dibuat: {ct_yarn['contract_number']} · kg @ Rp 49.500 · MOQ 100")
    else:
        bad(f"Gagal membuat kontrak pembelian: {r.status_code} {r.text[:250]}")

    # Kontrak GENERIK (tanpa product_id) untuk supplier yang sama → harus KALAH spesifisitas
    r = mk_contract({"contract_type": "purchase", "partner_id": SUP_A,
                     "title": "Kontrak umum supplier A", "tariff_basis": "kg",
                     "tariff_rate": 55000, "valid_from": today(), "valid_to": plus_days(180)})
    ct_generic = r.json() if r.ok else {}
    ok("Kontrak pembelian GENERIK (tanpa produk) dibuat sebagai pembanding") if r.ok else \
        bad(f"Gagal buat kontrak generik: {r.status_code} {r.text[:200]}")

    # Kontrak KEDALUWARSA → harus diabaikan resolver
    r = mk_contract({"contract_type": "purchase", "partner_id": SUP_B, "product_id": P_DYE,
                     "title": "Kontrak obat celup (kedaluwarsa)", "tariff_basis": "kg",
                     "tariff_rate": 1000, "valid_from": plus_days(-90), "valid_to": plus_days(-2)})
    ct_expired = r.json() if r.ok else {}
    ok("Kontrak kedaluwarsa dibuat sebagai kasus uji resolver") if r.ok else \
        bad(f"Gagal buat kontrak kedaluwarsa: {r.status_code} {r.text[:200]}")

    r = s.get(f"{API}/supplier-contracts", params={"contract_type": "purchase",
                                                   "entity_id": ENTITY}, timeout=30)
    rows = r.json() if r.ok else []
    mine = [c for c in rows if MARK in (c.get("notes") or "")]
    ok(f"Filter contract_type=purchase mengembalikan {len(mine)} kontrak POC") if len(mine) == 3 else \
        bad(f"Filter kontrak pembelian salah: {len(mine)} (harap 3)")

    r = s.get(f"{API}/supplier-contracts/stats", params={"entity_id": ENTITY}, timeout=30)
    st = r.json() if r.ok else {}
    ok(f"Statistik kontrak: total {st.get('total')} · pembelian {st.get('purchase')} · "
       f"makloon {st.get('makloon')}") if r.ok and st.get("purchase", 0) >= 3 else \
        bad(f"Statistik kontrak tidak memuat kontrak pembelian: {st}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 2 — Resolver kontrak aktif: paling spesifik menang · kedaluwarsa diabaikan")
    r = s.post(f"{API}/supplier-contracts/resolve",
               params={"partner_id": SUP_A, "contract_type": "purchase", "product_id": P_YARN},
               timeout=30)
    res = r.json() if r.ok else {}
    got = (res.get("contract") or {}).get("id") if isinstance(res, dict) else None
    if r.ok and got == ct_yarn.get("id"):
        ok("Resolver memilih kontrak PER-PRODUK (spesifik) di atas kontrak generik")
    else:
        bad(f"Resolver salah pilih: {r.status_code} {str(res)[:250]}")

    r = s.post(f"{API}/supplier-contracts/resolve",
               params={"partner_id": SUP_B, "contract_type": "purchase", "product_id": P_DYE},
               timeout=30)
    res = r.json() if r.ok else {}
    empty = (not res) or (res.get("found") is False) or not res.get("contract")
    ok("Kontrak KEDALUWARSA diabaikan resolver (tak ada kontrak aktif)") if empty else \
        bad(f"Kontrak kedaluwarsa masih ter-resolve: {str(res)[:200]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 3 — `supplier_items`: CRUD + kunci unik (supplier_id, supplier_sku) · E-02")
    r = s.post(f"{API}/supplier-items", json={
        "supplier_id": SUP_A, "sku": "POCE-YARN", "supplier_sku": "TX-COT-30S",
        "supplier_item_name": "Cotton Combed 30s Cone 1,89kg", "supplier_uom": "cone",
        "conv_factor": 1.89, "last_price": 93555, "moq": 20, "lead_time_days": 7,
        "expected_grade": "A", "entity_id": ENTITY}, timeout=30)
    it_yarn = r.json() if r.ok else {}
    if r.ok and it_yarn.get("id", "").startswith("sit_") and it_yarn.get("product_id") == P_YARN:
        ok(f"Barang supplier dibuat: {it_yarn['supplier_sku']} → {it_yarn['sku']} "
           f"(1 cone = {it_yarn['conv_factor']} kg · E-03)")
    else:
        bad(f"Gagal buat barang supplier: {r.status_code} {r.text[:250]}")

    r = s.post(f"{API}/supplier-items", json={
        "supplier_id": SUP_A, "sku": "POCE-YARN", "supplier_sku": "TX-COT-30S",
        "entity_id": ENTITY}, timeout=30)
    ok("Kode supplier DUPLIKAT ditolak 400 (kunci unik supplier+kode ditegakkan)") \
        if r.status_code == 400 else bad(f"Duplikat seharusnya 400, dapat {r.status_code}")

    r = s.post(f"{API}/supplier-items", json={
        "supplier_id": SUP_B, "sku": "POCE-YARN", "supplier_sku": "TX-COT-30S",
        "supplier_item_name": "Benang 30s (supplier lain)", "entity_id": ENTITY}, timeout=30)
    ok("Kode SAMA di SUPPLIER LAIN diizinkan (kunci = supplier + kode)") if r.ok else \
        bad(f"Kode sama supplier lain seharusnya boleh: {r.status_code} {r.text[:200]}")
    it_dup_other = r.json() if r.ok else {}

    r = s.patch(f"{API}/supplier-items/{it_yarn.get('id')}",
                json={"last_price": 94500, "notes": "harga naik Juli"}, timeout=30)
    ok("Barang supplier bisa diubah (harga terakhir & catatan)") \
        if r.ok and near(r.json().get("last_price"), 94500) else \
        bad(f"Gagal ubah barang supplier: {r.status_code} {r.text[:200]}")

    r = s.post(f"{API}/supplier-items", json={
        "supplier_id": SUP_A, "sku": "POCE-YARN", "supplier_sku": "TX-BAD",
        "conv_factor": 0, "entity_id": ENTITY}, timeout=30)
    ok("Faktor konversi 0 ditolak (satuan tidak boleh ditebak · E-03)") \
        if r.status_code == 422 or r.status_code == 400 else \
        bad(f"conv_factor=0 seharusnya ditolak, dapat {r.status_code}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 4 — Pencarian barang KN dari KODE SUPPLIER (kasus nyata operator)")
    r = s.get(f"{API}/supplier-items/lookup",
              params={"supplier_sku": "TX-COT-30S", "supplier_id": SUP_A}, timeout=30)
    found = r.json() if r.ok else {}
    if r.ok and (found.get("item") or {}).get("product_id") == P_YARN:
        ok(f"Kode supplier 'TX-COT-30S' → {found['item']['sku']} "
           f"{found['item']['product_name']} (terjemahan otomatis)")
    else:
        bad(f"Lookup kode supplier gagal: {r.status_code} {r.text[:250]}")

    r = s.get(f"{API}/supplier-items/lookup",
              params={"supplier_sku": "TIDAK-ADA-999", "supplier_id": SUP_A}, timeout=30)
    ok("Kode supplier tak dikenal → 404 dengan pesan yang bisa ditindak") \
        if r.status_code == 404 else bad(f"Lookup tak dikenal seharusnya 404, dapat {r.status_code}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 5 — IMPOR MASSAL: template + pratinjau menolak baris invalid dgn ALASAN (E-01)")
    r = s.get(f"{API}/supplier-items/import-template", timeout=30)
    tpl = r.text if r.ok else ""
    ok("Template CSV bisa diunduh (header + contoh baris)") \
        if r.ok and "supplier_sku" in tpl and "conv_factor" in tpl else \
        bad(f"Template CSV tidak valid: {r.status_code} {tpl[:120]}")

    csv_mixed = "\n".join([
        "supplier_sku,supplier_item_name,sku,supplier_uom,conv_factor,last_price,moq,lead_time_days,expected_grade",
        "TX-COT-30S,Cotton Combed 30s Cone,POCE-YARN,cone,1.89,94500,20,7,A",       # update
        "TX-GREY-115,Grey Cotton 115cm,POCE-GREY,roll,45,0,1,10,A",                  # create
        "TX-DYE-RED,Reactive Red,POCE-XXX,kg,1,50000,,,",                            # SKU KN tak ada
        "TX-BADCONV,Bad Conv,POCE-GREY,roll,0,1000,,,",                              # faktor 0
        ",Tanpa Kode,POCE-GREY,roll,1,1000,,,",                                      # supplier_sku kosong
        "TX-GREY-115,Duplikat Dalam Berkas,POCE-GREY,roll,45,0,,,",                  # duplikat
    ])
    r = s.post(f"{API}/supplier-items/import",
               json={"supplier_id": SUP_A, "entity_id": ENTITY, "csv_text": csv_mixed,
                     "dry_run": True}, timeout=60)
    pv = r.json() if r.ok else {}
    if r.ok and pv.get("total") == 6 and pv.get("valid") == 2 and pv.get("invalid") == 4:
        ok(f"Pratinjau impor: {pv['valid']} valid ({pv['will_create']} baru · "
           f"{pv['will_update']} update) · {pv['invalid']} ditolak")
    else:
        bad(f"Pratinjau impor tidak sesuai: {str(pv)[:400]}")
    reasons = " | ".join(e.get("error", "") for e in (pv.get("errors") or []))
    checks = [("POCE-XXX" in reasons or "tidak ada" in reasons.lower(), "SKU KN tak ada"),
              ("konversi" in reasons.lower(), "faktor konversi ≤ 0"),
              ("supplier_sku" in reasons.lower(), "supplier_sku kosong"),
              ("duplikat" in reasons.lower(), "duplikat dalam berkas")]
    missing = [label for cond, label in checks if not cond]
    ok("Setiap baris invalid punya ALASAN spesifik (SKU KN, faktor, kode kosong, duplikat)") \
        if not missing else bad(f"Alasan baris invalid kurang: {missing} · {reasons[:300]}")
    cnt = await db.supplier_items.count_documents({"supplier_id": SUP_A})
    ok("Pratinjau TIDAK menulis apa pun ke database (dry_run murni)") if cnt == 1 else \
        bad(f"dry_run menulis data: {cnt} baris (harap 1)")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 6 — IMPOR commit + IDEMPOTEN (E-02) + unggah berkas XLSX")
    csv_valid = "\n".join([
        "supplier_sku,supplier_item_name,sku,supplier_uom,conv_factor,last_price,moq,lead_time_days,expected_grade",
        "TX-COT-30S,Cotton Combed 30s Cone,POCE-YARN,cone,1.89,94500,20,7,A",
        "TX-GREY-115,Grey Cotton 115cm,POCE-GREY,roll,45,1530000,1,10,A",
    ])
    r = s.post(f"{API}/supplier-items/import",
               json={"supplier_id": SUP_A, "entity_id": ENTITY, "csv_text": csv_valid,
                     "dry_run": False}, timeout=60)
    c1 = r.json() if r.ok else {}
    ok(f"Commit impor: {c1.get('created')} baru + {c1.get('updated')} diperbarui") \
        if r.ok and c1.get("created") == 1 and c1.get("updated") == 1 else \
        bad(f"Commit impor tidak sesuai: {str(c1)[:300]}")

    r = s.post(f"{API}/supplier-items/import",
               json={"supplier_id": SUP_A, "entity_id": ENTITY, "csv_text": csv_valid,
                     "dry_run": False}, timeout=60)
    c2 = r.json() if r.ok else {}
    ok("Impor ULANG **idempotent**: created=0 · updated=2 (kunci supplier+kode)") \
        if r.ok and c2.get("created") == 0 and c2.get("updated") == 2 else \
        bad(f"Impor kedua tidak idempotent: {str(c2)[:300]}")

    # Pemisah ';' (Excel Indonesia) harus terdeteksi otomatis
    csv_semi = "supplier_sku;supplier_item_name;sku;supplier_uom;conv_factor;last_price\n" \
               "TX-DYE-RED;Reactive Red 3BS;POCE-DYE;kg;1;95000"
    r = s.post(f"{API}/supplier-items/import",
               json={"supplier_id": SUP_B, "entity_id": ENTITY, "csv_text": csv_semi,
                     "dry_run": False}, timeout=60)
    c3 = r.json() if r.ok else {}
    ok("CSV dengan pemisah ';' (Excel ID) terdeteksi otomatis → 1 baris masuk") \
        if r.ok and c3.get("created") == 1 else \
        bad(f"CSV ';' gagal: {r.status_code} {str(c3)[:250]}")

    # Unggah XLSX nyata (multipart) — header alias Indonesia
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["kode_supplier", "nama_barang_supplier", "sku", "satuan_supplier",
                   "faktor_konversi", "harga"])
        ws.append(["TX-GREY-150", "Grey Cotton 150cm", "POCE-GREY", "roll", 50, 1700000])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        r = s.post(f"{API}/supplier-items/import-file",
                   params={"supplier_id": SUP_A, "entity_id": ENTITY, "dry_run": False},
                   files={"file": ("barang.xlsx", buf.getvalue(),
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                   timeout=60)
        cx = r.json() if r.ok else {}
        ok("Unggah XLSX (header alias Indonesia) berhasil → 1 baris baru") \
            if r.ok and cx.get("created") == 1 else \
            bad(f"Unggah XLSX gagal: {r.status_code} {str(cx)[:250]}")
    except ImportError:  # pragma: no cover
        info("openpyxl tidak tersedia — uji XLSX dilewati")

    r = s.get(f"{API}/supplier-items/stats", params={"entity_id": ENTITY}, timeout=30)
    stt = r.json() if r.ok else {}
    ok(f"Statistik barang supplier: total {stt.get('total')} · aktif {stt.get('active')} · "
       f"{stt.get('suppliers')} supplier") if r.ok and stt.get("total", 0) >= 5 else \
        bad(f"Statistik barang supplier tidak sesuai: {stt}")

    r = s.get(f"{API}/supplier-items", params={"supplier_id": SUP_A, "q": "GREY-115",
                                               "entity_id": ENTITY}, timeout=30)
    hits = r.json() if r.ok else []
    ok("Pencarian bebas (q) menemukan barang supplier berdasarkan kode") \
        if r.ok and any(h.get("supplier_sku") == "TX-GREY-115" for h in hits) else \
        bad(f"Pencarian q gagal: {r.status_code} {str(hits)[:200]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 7 — PR CAMPUR: baris `purchase` + baris `makloon` dalam SATU PR")
    r = s.post(f"{API}/purchase-requisitions", json={
        "entity_id": ENTITY, "warehouse_id": WH,
        "reason": f"{MARK} kebutuhan campur beli + makloon",
        "needed_by_date": plus_days(21), "submit_now": True,
        "preferred_supplier_id": SUP_A,
        "items": [
            {"product_id": P_YARN, "quantity": 150, "unit": "kg", "est_price": 0,
             "fulfillment_mode": "purchase", "note": "benang untuk tenun"},
            {"product_id": P_DYE, "quantity": 20, "unit": "kg", "est_price": 95000,
             "fulfillment_mode": "purchase", "note": "obat celup"},
            {"product_id": P_GREY, "quantity": 380, "unit": "yard", "est_price": 0,
             "fulfillment_mode": "makloon", "note": "grey dibuat via makloon tenun"},
        ]}, timeout=60)
    pr = r.json() if r.ok else {}
    if r.ok and pr.get("number", "").startswith("PR-") and len(pr.get("items", [])) == 3:
        modes = [i.get("fulfillment_mode") for i in pr["items"]]
        lines = [i.get("line_no") for i in pr["items"]]
        ok(f"PR campur dibuat {pr['number']} · mode per baris {modes} · line_no {lines}")
    else:
        bad(f"Gagal buat PR campur: {r.status_code} {r.text[:300]}")
    pr_id = pr.get("id", "")

    if pr.get("status") != "approved":
        r = s_mgr.post(f"{API}/purchase-requisitions/{pr_id}/approve", json={"notes": "OK"}, timeout=30)
        pr = r.json() if r.ok else pr
    ok(f"PR berstatus '{pr.get('status')}' & siap direalisasikan") \
        if pr.get("status") == "approved" else bad(f"PR belum approved: {pr.get('status')}")

    r = s.get(f"{API}/purchase-requisitions/{pr_id}/sourcing", timeout=30)
    sv = r.json() if r.ok else {}
    if r.ok and sv.get("summary", {}).get("realization_status") == "open" \
            and sv["summary"].get("purchase_lines") == 2 and sv["summary"].get("makloon_lines") == 1:
        ok("Ringkasan sourcing: status `open` · 2 baris pembelian · 1 baris makloon")
    else:
        bad(f"Ringkasan sourcing salah: {str(sv)[:300]}")

    r = s.post(f"{API}/purchase-requisitions", json={
        "entity_id": ENTITY, "warehouse_id": WH, "reason": f"{MARK} validasi mode",
        "items": [{"description": "Barang non-katalog", "quantity": 5, "unit": "pcs",
                   "est_price": 1000, "fulfillment_mode": "makloon"}]}, timeout=30)
    ok("Baris `makloon` tanpa produk katalog DITOLAK 400 (output makloon harus SKU jelas)") \
        if r.status_code == 400 else bad(f"Seharusnya 400, dapat {r.status_code} {r.text[:200]}")

    r = s.post(f"{API}/purchase-requisitions", json={
        "entity_id": ENTITY, "warehouse_id": WH, "reason": f"{MARK} validasi mode 2",
        "items": [{"product_id": P_YARN, "quantity": 5, "unit": "kg", "est_price": 1000,
                   "fulfillment_mode": "impor_langsung"}]}, timeout=30)
    ok("Mode pemenuhan tak dikenal DITOLAK 400 dengan daftar pilihan") \
        if r.status_code == 400 else bad(f"Seharusnya 400, dapat {r.status_code} {r.text[:200]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 8 — Realisasi SEBAGIAN → PO: jejak kontrak + barang supplier + harga kontrak")
    r = s.post(f"{API}/purchase-requisitions/{pr_id}/realize-po", json={
        "supplier_id": SUP_A, "warehouse_id": WH, "line_nos": [1],
        "notes": f"{MARK} realisasi baris 1"}, timeout=60)
    out = r.json() if r.ok else {}
    po1 = out.get("po") or {}
    if r.ok and "PO-" in po1.get("po_number", "") and len(po1.get("items", [])) == 1:
        it = po1["items"][0]
        ok(f"PO {po1['po_number']} dibuat dari baris 1 saja (1 item, bukan seluruh PR)")
        if it.get("contract_id") == ct_yarn.get("id") and near(it.get("price"), 49500):
            ok(f"Harga baris PO dari KONTRAK {it.get('contract_number')}: Rp {it['price']:,.0f}/kg "
               f"(bukan harga master Rp {YARN_COST:,.0f})")
        else:
            bad(f"Harga/kontrak baris PO salah: price={it.get('price')} contract={it.get('contract_id')}")
        if it.get("supplier_item_id") == it_yarn.get("id") and it.get("supplier_sku") == "TX-COT-30S":
            ok(f"Baris PO membawa NAMA & KODE versi supplier: {it['supplier_sku']} — "
               f"{it.get('supplier_item_name')}")
        else:
            bad(f"Jejak barang supplier tidak tersimpan di baris PO: {str(it)[:250]}")
        ok(f"Grade yang dijanjikan tersimpan: {it.get('expected_grade')}") \
            if it.get("expected_grade") else bad("expected_grade tidak tersimpan di baris PO")
        ok(f"Jejak penentuan harga auditable ({len(it.get('sourcing_explain') or [])} langkah, "
           f"sumber={it.get('price_source')})") if it.get("sourcing_explain") else \
            bad("sourcing_explain kosong — penentuan harga tidak auditable")
    else:
        bad(f"Realisasi ke PO gagal: {r.status_code} {r.text[:400]}")

    prd = out.get("pr") or {}
    if prd.get("realization_status") == "partially_realized":
        ok(f"Status PR turunan = `partially_realized` "
           f"({prd['realization']['realized_lines']}/{prd['realization']['total_lines']} baris)")
    else:
        bad(f"Status realisasi PR salah: {prd.get('realization_status')}")

    r = s.post(f"{API}/purchase-requisitions/{pr_id}/realize-po", json={
        "supplier_id": SUP_A, "warehouse_id": WH, "line_nos": [1]}, timeout=30)
    ok("Realisasi ULANG baris yang sudah penuh DITOLAK 400 (anti dobel-PO)") \
        if r.status_code == 400 else bad(f"Seharusnya 400, dapat {r.status_code} {r.text[:200]}")

    # Realisasi baris 2 (obat celup, supplier B tanpa kontrak aktif → harga est PR)
    r = s.post(f"{API}/purchase-requisitions/{pr_id}/realize-po", json={
        "supplier_id": SUP_B, "warehouse_id": WH, "line_nos": [2],
        "notes": f"{MARK} realisasi baris 2"}, timeout=60)
    out2 = r.json() if r.ok else {}
    po2 = out2.get("po") or {}
    if r.ok and po2.get("po_number"):
        it2 = (po2.get("items") or [{}])[0]
        ok(f"PO kedua {po2['po_number']} untuk supplier berbeda (baris 2) — "
           f"harga Rp {it2.get('price'):,.0f} sumber `{it2.get('price_source')}`")
        ok("Kontrak KEDALUWARSA tidak dipakai (harga jatuh ke estimasi PR)") \
            if it2.get("price_source") != "contract" else \
            bad("Harga memakai kontrak kedaluwarsa — resolver bocor")
    else:
        bad(f"Realisasi baris 2 gagal: {r.status_code} {r.text[:300]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 9 — Prefill Wizard Makloon dari baris PR (1 klik) + realisasi ke Order Makloon")
    r = s.get(f"{API}/purchase-requisitions/{pr_id}/makloon-prefill",
              params={"line_no": 3}, timeout=30)
    pre = r.json() if r.ok else {}
    if r.ok and pre.get("ready") and pre.get("payload"):
        pl = pre["payload"]
        exp_mat = round(380 / (3.8 * 0.96), 2)
        ok(f"Prefill siap: bahan {pl.get('material_name')} {pl.get('material_qty')} "
           f"{pl.get('material_unit')} · mitra {pl['steps'][0].get('makloon_name')} · "
           f"proses {pl['steps'][0].get('process_type')}")
        ok(f"Qty bahan diturunkan dari resep (target 380 ÷ faktor efektif ≈ {exp_mat:g})") \
            if near(pl.get("material_qty"), exp_mat, 0.03) else \
            bad(f"Qty bahan prefill salah: {pl.get('material_qty')} (harap ≈ {exp_mat})")
        ok(f"Rantai prefill benar: input {pl['steps'][0].get('input_product_id')} → "
           f"output {pl['steps'][0].get('output_product_id')} (= produk yang diminta PR)") \
            if pl["steps"][0].get("output_product_id") == P_GREY and \
            pl["steps"][0].get("input_product_id") == P_YARN else \
            bad(f"Rantai prefill salah: {str(pl['steps'][0])[:200]}")
        ok(f"Jejak perhitungan prefill auditable ({len(pre.get('explain') or [])} langkah)") \
            if pre.get("explain") else bad("explain prefill kosong")
    else:
        bad(f"Prefill makloon gagal: {r.status_code} {r.text[:400]}")

    payload = dict(pre.get("payload") or {})
    payload["notes"] = f"{MARK} realisasi makloon dari PR"
    r = s.post(f"{API}/purchase-requisitions/{pr_id}/realize-makloon",
               json={"line_no": 3, "payload": payload}, timeout=60)
    rm = r.json() if r.ok else {}
    mko = rm.get("makloon_order") or {}
    if r.ok and mko.get("mko_number", "").startswith("MKO-"):
        ok(f"Order Makloon {mko['mko_number']} dibuat dari baris PR 3 "
           f"(estimasi {rm.get('expected_output_qty')} yard)")
        ok(f"Order Makloon tertaut PR: pr_number={mko.get('pr_number')} "
           f"baris={mko.get('pr_line_no')}") \
            if mko.get("pr_id") == pr_id and int(mko.get("pr_line_no") or 0) == 3 else \
            bad(f"Tautan PR pada order makloon hilang: {mko.get('pr_id')}/{mko.get('pr_line_no')}")
        step = (mko.get("steps") or [{}])[0]
        ok(f"Langkah makloon memakai mitra & resep dari prefill "
           f"({step.get('makloon_name')} · {step.get('process_type')})") \
            if step.get("makloon_id") == MK_TENUN else \
            bad(f"Mitra langkah salah: {step.get('makloon_id')}")
    else:
        bad(f"Realisasi ke makloon gagal: {r.status_code} {r.text[:400]}")

    prd = rm.get("pr") or {}
    if prd.get("realization_status") == "realized" and prd.get("status") == "converted":
        ok("Semua baris terealisasi → status realisasi `realized` & PR jadi `converted`")
    else:
        bad(f"Status akhir PR salah: realization={prd.get('realization_status')} "
            f"status={prd.get('status')}")
    if prd.get("po_ids") and len(prd["po_ids"]) == 2 and len(prd.get("makloon_order_ids") or []) == 1:
        ok(f"Jejak realisasi lengkap: {len(prd['po_ids'])} PO + "
           f"{len(prd['makloon_order_ids'])} Order Makloon")
    else:
        bad(f"Jejak realisasi tidak lengkap: po={prd.get('po_ids')} mko={prd.get('makloon_order_ids')}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 10 — Pagar realisasi: output langkah akhir wajib = produk yang diminta PR")
    r = s.post(f"{API}/purchase-requisitions", json={
        "entity_id": ENTITY, "warehouse_id": WH, "reason": f"{MARK} pagar output",
        "submit_now": True,
        "items": [{"product_id": P_GREY, "quantity": 100, "unit": "yard",
                   "fulfillment_mode": "makloon"}]}, timeout=60)
    pr2 = r.json() if r.ok else {}
    pr2_id = pr2.get("id", "")
    if pr2.get("status") != "approved":
        rr = s_mgr.post(f"{API}/purchase-requisitions/{pr2_id}/approve", json={}, timeout=30)
        pr2 = rr.json() if rr.ok else pr2
    bad_payload = {
        "mode": "process_only", "material_product_id": P_YARN, "material_qty": 30,
        "material_unit": "kg", "from_warehouse_id": WH, "target_warehouse_id": WH,
        "entity_id": ENTITY, "notes": f"{MARK} pagar",
        "steps": [{"process_type": "tenun", "makloon_id": MK_TENUN, "recipe_id": RECIPE,
                   "input_product_id": P_YARN, "output_product_id": P_DYE}],
    }
    r = s.post(f"{API}/purchase-requisitions/{pr2_id}/realize-makloon",
               json={"line_no": 1, "payload": bad_payload}, timeout=30)
    ok("Output langkah akhir ≠ produk PR DITOLAK 400 (jejak kebutuhan→realisasi tak putus)") \
        if r.status_code == 400 else bad(f"Seharusnya 400, dapat {r.status_code} {r.text[:250]}")

    r = s.post(f"{API}/purchase-requisitions/{pr2_id}/realize-po",
               json={"supplier_id": SUP_A, "warehouse_id": WH}, timeout=30)
    ok("Realisasi ke PO pada PR yang semua barisnya `makloon` DITOLAK 400 dgn pesan jelas") \
        if r.status_code == 400 else bad(f"Seharusnya 400, dapat {r.status_code} {r.text[:250]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 11 — Budget Control R6.3 tetap berlaku pada PO hasil realisasi PR")
    r = s.get(f"{API}/finance/budget-rules", params={"entity_id": ENTITY}, timeout=30)
    rules_before = r.json() if r.ok else {}
    info(f"Aturan anggaran awal: mode={rules_before.get('mode')} "
         f"enforce_po_create={rules_before.get('enforce_po_create')}")
    year = datetime.now(timezone.utc).year
    month = datetime.now(timezone.utc).month
    r = s.post(f"{API}/finance/budgets", json={
        "entity_id": ENTITY, "dimension": "account", "key": "1-1300",
        "year": year, "month": month, "amount": 1000.0,
        "note": f"{MARK} anggaran ketat"}, timeout=30)
    budget_made = r.ok
    budget_id = (r.json() or {}).get("id", "") if r.ok else ""
    ok("Anggaran ketat (Rp 1.000) dibuat untuk akun Persediaan 1-1300") if budget_made else \
        info(f"Pembuatan anggaran dilewati: {r.status_code} {r.text[:200]}")
    r = s.put(f"{API}/finance/budget-rules", json={"entity_id": ENTITY, "mode": "block",
                                                   "enforce_po_create": True}, timeout=30)
    rules_set = r.ok
    ok("Mode anggaran diubah ke `block` tanpa deploy") if rules_set else \
        info(f"Gagal set mode block: {r.status_code} {r.text[:200]}")

    r = s.post(f"{API}/purchase-requisitions", json={
        "entity_id": ENTITY, "warehouse_id": WH, "reason": f"{MARK} uji anggaran",
        "submit_now": True, "preferred_supplier_id": SUP_A,
        "items": [{"product_id": P_YARN, "quantity": 100, "unit": "kg",
                   "fulfillment_mode": "purchase"}]}, timeout=60)
    pr3 = r.json() if r.ok else {}
    pr3_id = pr3.get("id", "")
    if pr3.get("status") != "approved":
        rr = s_mgr.post(f"{API}/purchase-requisitions/{pr3_id}/approve", json={}, timeout=30)
        pr3 = rr.json() if rr.ok else pr3
    r = s.post(f"{API}/purchase-requisitions/{pr3_id}/realize-po",
               json={"supplier_id": SUP_A, "warehouse_id": WH, "notes": f"{MARK} over budget"},
               timeout=60)
    if budget_made and rules_set:
        ok("PO hasil realisasi PR DITOLAK 400 karena melampaui anggaran (R6.3 konsisten)") \
            if r.status_code == 400 and "nggaran" in r.text else \
            bad(f"Anggaran tidak menahan realisasi PR: {r.status_code} {r.text[:250]}")
    else:
        info("Uji block anggaran dilewati (aturan/anggaran tak bisa dipasang)")
    # kembalikan aturan seperti semula agar tidak mengganggu data lain
    s.put(f"{API}/finance/budget-rules", json={
        "entity_id": ENTITY, "mode": rules_before.get("mode", "warn"),
        "enforce_po_create": bool(rules_before.get("enforce_po_create", True))}, timeout=30)
    if budget_id:
        s.delete(f"{API}/finance/budgets/{budget_id}", timeout=30)
    await db.budgets.delete_many({"note": {"$regex": MARK}})
    r = s.post(f"{API}/purchase-requisitions/{pr3_id}/realize-po",
               json={"supplier_id": SUP_A, "warehouse_id": WH, "notes": f"{MARK} setelah anggaran"},
               timeout=60)
    ok("Setelah anggaran dinormalkan, realisasi PR→PO berhasil (tidak ada efek samping)") \
        if r.ok else bad(f"Realisasi setelah reset anggaran gagal: {r.status_code} {r.text[:250]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 12 — RBAC: warehouse lihat-saja · sales tanpa akses · realisasi butuh izin")
    r = s_wh.get(f"{API}/supplier-items", params={"entity_id": ENTITY}, timeout=30)
    ok("Warehouse BOLEH melihat Barang Supplier (butuh saat penerimaan)") if r.ok else \
        bad(f"Warehouse seharusnya bisa lihat: {r.status_code}")
    r = s_wh.post(f"{API}/supplier-items", json={
        "supplier_id": SUP_A, "sku": "POCE-YARN", "supplier_sku": "TX-WH", "entity_id": ENTITY},
        timeout=30)
    ok("Warehouse DITOLAK 403 membuat Barang Supplier") if r.status_code == 403 else \
        bad(f"Warehouse create seharusnya 403, dapat {r.status_code}")
    r = s_wh.post(f"{API}/supplier-items/import",
                  json={"supplier_id": SUP_A, "entity_id": ENTITY, "csv_text": csv_valid,
                        "dry_run": True}, timeout=30)
    ok("Warehouse DITOLAK 403 melakukan impor massal") if r.status_code == 403 else \
        bad(f"Warehouse import seharusnya 403, dapat {r.status_code}")
    r = s_sales.get(f"{API}/supplier-items", params={"entity_id": ENTITY}, timeout=30)
    ok("Sales DITOLAK 403 melihat Barang Supplier (data komersial pembelian)") \
        if r.status_code == 403 else bad(f"Sales seharusnya 403, dapat {r.status_code}")
    r = s_sales.post(f"{API}/purchase-requisitions/{pr_id}/realize-po",
                     json={"supplier_id": SUP_A, "warehouse_id": WH}, timeout=30)
    ok("Sales DITOLAK 403 merealisasikan PR ke PO") if r.status_code == 403 else \
        bad(f"Sales realize-po seharusnya 403, dapat {r.status_code}")
    r = s_mgr.get(f"{API}/purchase-requisitions/{pr_id}/sourcing", timeout=30)
    ok("Manager bisa melihat ringkasan sourcing PR") if r.ok else \
        bad(f"Manager sourcing gagal: {r.status_code}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 13 — Proteksi jejak audit: barang supplier & kontrak terpakai tidak bisa dihapus")
    fresh = await db.supplier_items.find_one({"id": it_yarn.get("id")}, {"_id": 0})
    ok(f"usage_count barang supplier naik setelah dipakai PO ({fresh.get('usage_count')}×) "
       f"& harga terakhir tersinkron Rp {fresh.get('last_price'):,.0f}") \
        if fresh and int(fresh.get("usage_count") or 0) >= 1 else \
        bad(f"usage_count tidak naik: {str(fresh)[:200]}")
    r = s.delete(f"{API}/supplier-items/{it_yarn.get('id')}", timeout=30)
    ok("Barang supplier yang sudah dipakai PO DITOLAK dihapus (409)") if r.status_code == 409 else \
        bad(f"Hapus seharusnya 409, dapat {r.status_code} {r.text[:200]}")
    r = s.delete(f"{API}/supplier-contracts/{ct_yarn.get('id')}", timeout=30)
    ok("Kontrak pembelian yang sudah dipakai PO DITOLAK dihapus (409)") if r.status_code == 409 else \
        bad(f"Hapus kontrak seharusnya 409, dapat {r.status_code} {r.text[:200]}")
    r = s.delete(f"{API}/supplier-items/{it_dup_other.get('id')}", timeout=30)
    ok("Barang supplier yang BELUM dipakai boleh dihapus") if r.ok else \
        bad(f"Hapus barang tak terpakai gagal: {r.status_code} {r.text[:200]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 14 — Invarian INV-SRC-01..05 hijau pada data POC (sebelum dibersihkan)")
    sys.path.insert(0, "/app/backend")
    from services.pr_sourcing_service import compute_realization
    prfin = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    summ = compute_realization(prfin)
    ok("Ringkasan realisasi turunan konsisten dengan yang tersimpan") \
        if summ["realization_status"] == prfin.get("realization_status") else \
        bad(f"Drift status realisasi: {summ['realization_status']} vs {prfin.get('realization_status')}")
    tot_real = round(sum(float(i.get("realized_qty") or 0) for i in prfin["items"]), 2)
    tot_need = round(sum(float(i.get("quantity") or 0) for i in prfin["items"]), 2)
    ok(f"Realisasi penuh & tidak berlebih: {tot_real:g} dari {tot_need:g} unit") \
        if abs(tot_real - tot_need) < 0.02 else \
        bad(f"Realisasi tidak cocok: {tot_real} vs {tot_need}")
    dangling = []
    po_ids_db = {p["id"] for p in await db.purchase_orders.find({}, {"_id": 0, "id": 1}).to_list(50000)}
    mko_ids_db = {m["id"] for m in await db.makloon_orders.find({}, {"_id": 0, "id": 1}).to_list(20000)}
    for itx in prfin["items"]:
        for rr2 in (itx.get("realizations") or []):
            pool = po_ids_db if rr2["type"] == "purchase_order" else mko_ids_db
            if rr2["ref_id"] not in pool:
                dangling.append(rr2["ref_id"])
    ok("Semua jejak realisasi menunjuk dokumen yang ADA (INV-SRC-04)") if not dangling else \
        bad(f"Jejak realisasi menggantung: {dangling[:3]}")
    keys = [(x["supplier_id"], x["supplier_sku"]) for x in
            await db.supplier_items.find({}, {"_id": 0, "supplier_id": 1, "supplier_sku": 1}).to_list(50000)]
    ok(f"Kunci (supplier, kode) unik pada {len(keys)} barang supplier (INV-SRC-05)") \
        if len(keys) == len(set(keys)) else bad("Ada kunci (supplier, kode) duplikat")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 15 — Kebersihan data: artifact POC dibersihkan (invarian global tetap hijau)")
    await cleanup(db)
    left = (await db.supplier_items.count_documents({"supplier_id": {"$in": [SUP_A, SUP_B]}})
            + await db.supplier_contracts.count_documents({"notes": {"$regex": MARK}})
            + await db.purchase_requisitions.count_documents({"reason": {"$regex": MARK}})
            + await db.products.count_documents({"id": {"$in": PRODUCTS}})
            + await db.makloon_orders.count_documents({"notes": {"$regex": MARK}}))
    ok("Semua artifact POC dihapus (kontrak/barang supplier/PR/PO/order makloon/produk)") \
        if left == 0 else bad(f"Masih ada {left} artifact POC tertinggal")

    print("\n" + "=" * 64)
    print(f"  \033[92mPASS {len(PASS)}\033[0m  |  \033[91mFAIL {len(FAIL)}\033[0m")
    if FAIL:
        print("\033[91m\033[1m  POC FASE E GAGAL — perbaiki sebelum lanjut FE.\033[0m")
        for f in FAIL:
            print(f"   - {f}")
    else:
        print("\033[92m\033[1m  POC FASE E HIJAU — sourcing berbasis kontrak terbukti.\033[0m")
    print("=" * 64)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
