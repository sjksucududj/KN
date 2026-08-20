#!/usr/bin/env python3
"""
POC ISOLASI — FASE F-1: PENERIMAAN BERBASIS **SATUAN SUPPLIER**
================================================================
Membuktikan CORE Fase F-1 lewat **HTTP API nyata** + assert **DB nyata** SEBELUM UI
dibangun. Tidak ada mock, tidak ada angka karangan. **Self-cleanup** di akhir agar
`scripts/verify_data_integrity.py` tetap pristine.

Masalah yang dibuktikan selesai
-------------------------------
Sebelum F-1, `POST /api/inbound/tasks/{id}/scan-receive` hanya menerima `actual_qty`
dalam satuan KN. Surat jalan supplier memakai satuan supplier (`cone`, `roll`, `lembar`)
sehingga operator mengalikan sendiri (25 cone × 1,89 kg). Salah ketik tak terdeteksi,
asal angka stok tidak terlacak.

Keputusan desain yang diuji
---------------------------
  * **F1-01** `doc_uom` + `doc_qty` opsional; diisi ⇒ server konversi, `actual_qty` diabaikan.
  * **F1-02** prioritas faktor: satuan sama → **barang supplier** (`conv_factor`) →
    **registry global** → gagal ⇒ 400 **actionable**.
  * **F1-03** jejak konversi WAJIB (`scan_log[].uom_trail` + `receive_uom_trails[]`).
  * **F1-04** `GET …/uom-options` (opsi satuan + faktor + hint + sisa 2 satuan).
  * **F1-05** `POST …/preview-uom` (pratinjau tanpa menulis).
  * **F1-06** pesan penolakan menyebut **kedua satuan**.
  * **F1-07** roll fisik tetap fisik (Σroll ≈ qty diterima) — GR complete tetap jalan.
  * **F1-08** kebijakan `system_settings` scope `receiving` (off|optional|prefer …).

Cakupan user story (US-F1..US-F8)
---------------------------------
  US-F1  terima memakai satuan supplier (cone) → stok bertambah dalam satuan KN (kg)
  US-F2  pratinjau konversi live sebelum submit
  US-F3  sisa PO tampil dalam dua satuan
  US-F4  satuan tanpa faktor ⇒ pesan yang memberi tahu langkah perbaikan
  US-F5  jejak konversi tersimpan & bisa diaudit (faktor, sumber, siapa, kapan)
  US-F6  kebijakan bisa diubah tanpa deploy (off ⇒ satuan supplier ditolak)
  US-F7  melebihi sisa + toleransi ⇒ ditolak, pesan menyebut kedua satuan
  US-F8  cara lama (langsung satuan KN) TETAP jalan (regresi 0)

Jalankan: cd /app && python backend/test_fase_f1_receiving_uom_poc.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

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

MARK = "FASEF1POC"
SUP = "sup_fasef1_yarn"
P_YARN = "prod_fasef1_yarn"      # base_unit kg   · supplier jual per CONE
P_FAB = "prod_fasef1_fabric"     # base_unit yard · supplier jual per ROLL
PRODUCTS = [P_YARN, P_FAB]

# Angka nyata (bukan karangan): 1 cone benang 30s = 1,89 kg · 1 roll kain = 40 yard
CONE_KG = 1.89
ROLL_YARD = 40.0
YARN_PO_QTY = 120.0              # kg  (PO dalam satuan KN)
FAB_PO_QTY = 400.0               # yard

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


def near(a, b, tol=0.011):
    try:
        return abs(float(a) - float(b)) <= tol
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


# ═══════════════════════════════════════════════════════════════════════════
# SETUP / CLEANUP
# ═══════════════════════════════════════════════════════════════════════════
async def cleanup(db):
    pos = await db.purchase_orders.find({"notes": {"$regex": MARK}}, {"_id": 0, "id": 1}).to_list(200)
    po_ids = [p["id"] for p in pos]
    # Jurnal Goods Receipt memakai `source_id` = id **wms_task** (bukan PO) → ambil dulu.
    tasks = await db.wms_tasks.find({"po_id": {"$in": po_ids}}, {"_id": 0, "id": 1}).to_list(500)
    task_ids = [t["id"] for t in tasks]
    for sid in po_ids + task_ids:
        await db.journal_entries.delete_many({"source_id": {"$regex": sid}})
    await db.journal_entries.delete_many({"source_id": {"$in": po_ids + task_ids}})
    await db.audit_logs.delete_many({"entity_id": {"$in": po_ids + task_ids}})
    await db.wms_tasks.delete_many({"po_id": {"$in": po_ids}})
    await db.purchase_orders.delete_many({"id": {"$in": po_ids}})
    await db.vendor_bills.delete_many({"po_id": {"$in": po_ids}})
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
    await db.supplier_items.delete_many({"supplier_id": SUP})
    await db.products.delete_many({"id": {"$in": PRODUCTS}})
    await db.suppliers.delete_many({"id": SUP})


async def make_masters(db):
    base = {"category": "Kain", "price": 0.0, "entity_id": ENTITY, "status": "active",
            "grade": "A", "reorder_point": 0.0, "reorder_qty": 0.0,
            "created_at": now_iso(), "updated_at": now_iso()}
    specs = [
        (P_YARN, "POCF1-YARN", "POC-F1 Benang Katun 30s", "kg", "yarn", 0, 0, 78000.0),
        (P_FAB, "POCF1-FAB", "POC-F1 Kain Grey Katun", "yard", "grey", 120.0, 1.15, 34000.0),
    ]
    for pid, sku, name, unit, stage, gsm, lebar, hpp in specs:
        await db.products.update_one({"id": pid}, {"$set": {
            **base, "id": pid, "sku": sku, "name": name, "base_unit": unit, "stage": stage,
            "fabric_type": "woven", "gramasi": gsm, "lebar": lebar, "harga_pokok": hpp}},
            upsert=True)
    await db.suppliers.update_one({"id": SUP}, {"$set": {
        "id": SUP, "code": "SUP-F1P", "name": "POC-F1 Supplier Benang Cone", "city": "Solo",
        "pic_name": "Bpk. Uji F1", "phone": "0812-9000-0011", "npwp": "",
        "entity_id": ENTITY, "status": "active",
        "created_at": now_iso(), "updated_at": now_iso()}}, upsert=True)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════
def create_po(s, product_id, qty, unit, price, note_suffix=""):
    body = {"supplier_id": SUP, "warehouse_id": WH,
            "items": [{"product_id": product_id, "quantity": qty, "unit": unit,
                       "price": price, "expected_grade": "A"}],
            "notes": f"{MARK} {note_suffix}".strip()}
    r = s.post(f"{API}/purchase-orders", json=body, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"PO gagal {r.status_code}: {r.text[:300]}")
    po = r.json()
    for _ in range(6):
        if po.get("status") != "waiting_approval":
            break
        ra = s.post(f"{API}/purchase-orders/{po['id']}/approve",
                    json={"notes": f"{MARK} approve"}, timeout=60)
        if ra.status_code != 200:
            break
        po = ra.json()
    return s.get(f"{API}/purchase-orders/{po['id']}", timeout=30).json()


def inbound_task(s, po_id, product_id):
    rows = s.get(f"{API}/inbound/tasks", timeout=30).json()
    hits = [t for t in rows if t.get("po_id") == po_id and t.get("product_id") == product_id]
    return hits[0] if hits else None


def set_policy(s, **kw):
    r = s.put(f"{API}/receiving/uom-settings", json=kw, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"set policy gagal {r.status_code}: {r.text[:200]}")
    return r.json()


# ═══════════════════════════════════════════════════════════════════════════
# TES
# ═══════════════════════════════════════════════════════════════════════════
async def run():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    s = sess()
    wh = sess("warehouse@kainnusantara.id")

    head("TEST 0 — Persiapan master (produk · supplier · bersihkan sisa POC lama)")
    await cleanup(db)
    await make_masters(db)
    ok("Master POC siap (2 produk: benang/kg & kain/yard · 1 supplier)")

    # ── kembalikan kebijakan ke default agar tes deterministik ─────────────
    pol = set_policy(s, supplier_uom_input_mode="prefer",
                     require_supplier_item_for_supplier_uom=True,
                     block_over_remaining=True)
    if pol.get("supplier_uom_input_mode") == "prefer":
        ok("F1-08: kebijakan penerimaan dapat diatur lewat API (scope `receiving`)")
    else:
        bad(f"F1-08: kebijakan tidak tersimpan ({pol})")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 1 — Barang supplier: benang dijual per CONE (1 cone = 1,89 kg)")
    r = s.post(f"{API}/supplier-items", json={
        "supplier_id": SUP, "product_id": P_YARN, "supplier_sku": "F1-YARN-30S",
        "supplier_item_name": "Cotton Combed 30s Cone 1,89 Kg",
        "supplier_uom": "cone", "conv_factor": CONE_KG, "last_price": 147420,
        "moq": 10, "lead_time_days": 7, "expected_grade": "A",
        "notes": f"{MARK} benang per cone", "entity_id": ENTITY}, timeout=30)
    if r.status_code != 200:
        bad(f"Barang supplier benang gagal dibuat ({r.status_code} {r.text[:200]})")
        return
    sit_yarn = r.json()
    ok(f"Barang supplier benang: {sit_yarn['supplier_sku']} · 1 cone = {sit_yarn['conv_factor']:g} kg")

    r = s.post(f"{API}/supplier-items", json={
        "supplier_id": SUP, "product_id": P_FAB, "supplier_sku": "F1-FAB-ROLL",
        "supplier_item_name": "Grey Cotton Roll 40 Yard", "supplier_uom": "roll",
        "conv_factor": ROLL_YARD, "last_price": 1360000, "expected_grade": "A",
        "notes": f"{MARK} kain per roll", "entity_id": ENTITY}, timeout=30)
    if r.status_code != 200:
        bad(f"Barang supplier kain gagal dibuat ({r.status_code} {r.text[:200]})")
        return
    ok(f"Barang supplier kain: F1-FAB-ROLL · 1 roll = {ROLL_YARD:g} yard")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 2 — PO manual ikut membawa jejak barang supplier ke task inbound")
    po_yarn = create_po(s, P_YARN, YARN_PO_QTY, "kg", 78000, "benang")
    item = (po_yarn.get("items") or [{}])[0]
    if item.get("supplier_item_id") == sit_yarn["id"] and item.get("supplier_uom") == "cone":
        ok(f"Baris PO {po_yarn['po_number']} distempel barang supplier "
           f"({item['supplier_sku']} · satuan {item['supplier_uom']})")
    else:
        bad(f"Baris PO tidak membawa jejak barang supplier: {item}")

    task = inbound_task(s, po_yarn["id"], P_YARN)
    if not task:
        bad("Task inbound untuk PO benang tidak terbentuk")
        return
    if task.get("supplier_uom") == "cone" and near(task.get("supplier_conv_factor"), CONE_KG):
        ok("Task inbound membawa satuan & faktor supplier (siap input satuan supplier)")
    else:
        bad(f"Task inbound tidak membawa satuan supplier: {task.get('supplier_uom')}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 3 — US-F1/US-F3/F1-04: opsi satuan + sisa dalam DUA satuan")
    r = s.get(f"{API}/inbound/tasks/{task['id']}/uom-options", timeout=30)
    if r.status_code != 200:
        bad(f"uom-options gagal ({r.status_code} {r.text[:200]})")
        return
    opt = r.json()
    codes = [o["value"] for o in opt["options"]]
    if "cone" in codes and "kg" in codes:
        ok(f"Opsi satuan berisi satuan KN + satuan supplier: {codes}")
    else:
        bad(f"Opsi satuan kurang: {codes}")
    if opt.get("default_uom") == "cone":
        ok("Mode `prefer`: satuan supplier menjadi default (operator tak perlu ganti)")
    else:
        bad(f"default_uom seharusnya 'cone' pada mode prefer (dapat {opt.get('default_uom')})")
    cone_opt = next((o for o in opt["options"] if o["value"] == "cone"), {})
    if near(cone_opt.get("factor"), CONE_KG):
        ok(f"Faktor cone→kg dari barang supplier: {cone_opt['factor']:g} (hint: {cone_opt['hint']})")
    else:
        bad(f"Faktor cone salah: {cone_opt}")
    exp_rem_cone = round(YARN_PO_QTY / CONE_KG, 2)
    if near(opt.get("remaining_qty"), YARN_PO_QTY, 0.02) and near(cone_opt.get("remaining"), exp_rem_cone, 0.02):
        ok(f"Sisa PO tampil 2 satuan: {opt['remaining_qty']:g} kg ≈ {cone_opt['remaining']:g} cone")
    else:
        bad(f"Sisa 2 satuan salah: kg={opt.get('remaining_qty')} cone={cone_opt.get('remaining')}")
    if (opt.get("supplier_item") or {}).get("supplier_sku") == "F1-YARN-30S":
        ok("Penamaan supplier (kode + nama + grade dijanjikan) tersedia untuk layar penerimaan")
    else:
        bad(f"supplier_item tidak dikembalikan: {opt.get('supplier_item')}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 4 — US-F2/F1-05: pratinjau konversi TANPA menulis")
    r = s.post(f"{API}/inbound/tasks/{task['id']}/preview-uom",
               json={"doc_uom": "cone", "doc_qty": 25}, timeout=30)
    if r.status_code != 200:
        bad(f"preview-uom gagal ({r.status_code} {r.text[:200]})")
        return
    pv = r.json()
    expect_kg = round(25 * CONE_KG, 2)
    if near(pv["trail"]["task_qty"], expect_kg):
        ok(f"Pratinjau: 25 cone = {pv['trail']['task_qty']:g} kg (harusnya {expect_kg:g})")
    else:
        bad(f"Pratinjau salah hitung: {pv['trail']}")
    if pv["trail"]["source"] == "supplier_item":
        ok("Sumber faktor = `supplier_item` (prioritas F1-02 benar)")
    else:
        bad(f"Sumber faktor salah: {pv['trail']['source']}")
    if pv.get("level") == "ok" and not pv.get("over_remaining"):
        ok(f"Pratinjau menandai aman (sisa {pv['remaining_qty']:g} kg ≈ "
           f"{pv['remaining_in_doc_uom']:g} cone)")
    else:
        bad(f"Pratinjau seharusnya aman: {pv}")
    fresh = await db.wms_tasks.find_one({"id": task["id"]}, {"_id": 0, "received_qty": 1,
                                                            "scan_log": 1})
    if float(fresh.get("received_qty") or 0) == 0 and not (fresh.get("scan_log") or []):
        ok("Pratinjau TIDAK menulis apa pun ke database (read-only terbukti)")
    else:
        bad(f"Pratinjau menulis ke DB: received={fresh.get('received_qty')}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 5 — US-F1/F1-01: scan-receive memakai SATUAN SUPPLIER (25 cone)")
    r = wh.post(f"{API}/inbound/tasks/{task['id']}/scan-receive",
                json={"product_id": P_YARN, "doc_uom": "cone", "doc_qty": 25,
                      "lot": f"{MARK}-L1", "dye_lot": f"{MARK}-L1", "grade": "A",
                      "bin_id": "A1-01"}, timeout=60)
    if r.status_code != 200:
        bad(f"scan-receive satuan supplier gagal ({r.status_code} {r.text[:300]})")
        return
    t1 = r.json()
    if near(t1.get("received_qty"), expect_kg):
        ok(f"received_qty tersimpan dalam SATUAN KN: {t1['received_qty']:g} kg "
           f"(operator hanya mengetik 25 cone)")
    else:
        bad(f"received_qty salah: {t1.get('received_qty')} (harusnya {expect_kg:g})")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 6 — US-F5/F1-03: jejak konversi WAJIB tersimpan & auditable")
    doc = await db.wms_tasks.find_one({"id": task["id"]}, {"_id": 0})
    scan = (doc.get("scan_log") or [])[-1]
    trail = scan.get("uom_trail") or {}
    need = ("doc_uom", "doc_qty", "task_uom", "task_qty", "base_uom", "base_qty",
            "factor", "source", "converted_at", "supplier_item_id", "supplier_sku")
    missing = [k for k in need if not trail.get(k) and trail.get(k) != 0]
    if not missing:
        ok(f"scan_log[].uom_trail lengkap: {trail['doc_qty']:g} {trail['doc_uom']} → "
           f"{trail['task_qty']:g} {trail['task_uom']} (faktor {trail['factor']:g} · "
           f"{trail['source']} · {trail['supplier_sku']})")
    else:
        bad(f"Jejak konversi tidak lengkap, field hilang: {missing}")
    trails = doc.get("receive_uom_trails") or []
    if len(trails) == 1 and trails[0].get("scan_id") == scan.get("id") and trails[0].get("actor"):
        ok(f"receive_uom_trails[] terakumulasi & tertaut scan_id + aktor ({trails[0]['actor']})")
    else:
        bad(f"receive_uom_trails tidak benar: {trails}")
    if near(trail.get("base_qty"), expect_kg):
        ok(f"Jejak juga menyimpan qty dalam satuan DASAR produk: {trail['base_qty']:g} kg")
    else:
        bad(f"base_qty salah: {trail.get('base_qty')}")
    au = await db.audit_logs.find_one({"entity_id": task["id"], "action": "inbound_scan_receive"},
                                     {"_id": 0}, sort=[("timestamp", -1)])
    au_det = (au or {}).get("after") or {}
    if au_det.get("doc_uom") == "cone" and near(au_det.get("doc_qty"), 25):
        ok(f"Audit log mencatat satuan & qty surat jalan + sumber faktor "
           f"({au_det.get('uom_source')} · faktor {au_det.get('factor')})")
    else:
        bad(f"Audit log tidak mencatat jejak satuan: {au_det}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 7 — US-F3: sisa PO berkurang & tetap tampil dalam dua satuan")
    opt2 = s.get(f"{API}/inbound/tasks/{task['id']}/uom-options", timeout=30).json()
    rem_kg = round(YARN_PO_QTY - expect_kg, 2)
    cone2 = next((o for o in opt2["options"] if o["value"] == "cone"), {})
    if near(opt2.get("remaining_qty"), rem_kg, 0.02):
        ok(f"Sisa setelah terima: {opt2['remaining_qty']:g} kg ≈ {cone2.get('remaining')} cone")
    else:
        bad(f"Sisa tidak sinkron: {opt2.get('remaining_qty')} (harusnya {rem_kg:g})")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 8 — US-F8: cara LAMA (langsung satuan KN) tetap jalan (regresi 0)")
    rest_kg = round(YARN_PO_QTY - expect_kg, 2)
    r = wh.post(f"{API}/inbound/tasks/{task['id']}/scan-receive",
                json={"product_id": P_YARN, "actual_qty": rest_kg,
                      "lot": f"{MARK}-L1", "bin_id": "A1-01"}, timeout=60)
    if r.status_code == 200 and near(r.json().get("received_qty"), YARN_PO_QTY, 0.02):
        ok(f"scan-receive tanpa doc_uom tetap diterima: total {r.json()['received_qty']:g} kg")
    else:
        bad(f"Regresi cara lama: {r.status_code} {r.text[:200]}")
    doc = await db.wms_tasks.find_one({"id": task["id"]}, {"_id": 0})
    if len(doc.get("scan_log") or []) == 2 and len(doc.get("receive_uom_trails") or []) == 1:
        ok("Scan tanpa satuan supplier TIDAK menambah jejak konversi (hanya bila relevan)")
    else:
        bad(f"Jejak tidak proporsional: scans={len(doc.get('scan_log') or [])} "
            f"trails={len(doc.get('receive_uom_trails') or [])}")
    if doc.get("status") == "qc_check":
        ok("Task naik ke `qc_check` setelah qty PO terpenuhi (alur lama utuh)")
    else:
        bad(f"Status task tidak naik: {doc.get('status')}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 9 — F1-07: GR complete + roll fisik tetap jalan (stok bertambah)")
    r = wh.post(f"{API}/inbound/tasks/{task['id']}/complete",
                json={"dye_lot": f"{MARK}-L1", "grade": "A",
                      "supplier_lot": "SLOT-F1-001"}, timeout=90)
    if r.status_code == 200:
        ok("Selesaikan penerimaan (GR complete) berhasil setelah input satuan supplier")
    else:
        bad(f"GR complete gagal: {r.status_code} {r.text[:300]}")
    rolls = await db.inventory_rolls.find({"product_id": P_YARN}, {"_id": 0}).to_list(50)
    tot_kg = round(sum(float(x.get("weight_kg") or 0) for x in rolls), 2)
    if rolls and near(tot_kg, YARN_PO_QTY, 0.5):
        ok(f"{len(rolls)} roll benang terbentuk dengan total {tot_kg:g} kg (= qty PO)")
    else:
        bad(f"Roll/berat tidak sesuai: {len(rolls)} roll, {tot_kg} kg")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 10 — US-F7/F1-06: melebihi sisa ⇒ ditolak, pesan menyebut DUA satuan")
    po_fab = create_po(s, P_FAB, FAB_PO_QTY, "yard", 34000, "kain")
    tfab = inbound_task(s, po_fab["id"], P_FAB)
    if not tfab:
        bad("Task inbound kain tidak terbentuk")
        return
    ok(f"PO kain {po_fab['po_number']} · {FAB_PO_QTY:g} yard (= {FAB_PO_QTY / ROLL_YARD:g} roll)")
    r = wh.post(f"{API}/inbound/tasks/{tfab['id']}/scan-receive",
                json={"product_id": P_FAB, "doc_uom": "roll", "doc_qty": 12,
                      "lot": f"{MARK}-F1", "bin_id": "B1-01"}, timeout=60)
    msg = (r.json() or {}).get("detail", "") if r.status_code == 400 else ""
    if r.status_code == 400 and "roll" in msg and "yard" in msg:
        ok(f"12 roll (480 yard) DITOLAK 400 & pesan menyebut kedua satuan → \"{msg[:150]}\"")
    else:
        bad(f"Over-receipt tidak ditolak dengan pesan 2 satuan: {r.status_code} {msg[:200]}")
    r = wh.post(f"{API}/inbound/tasks/{tfab['id']}/scan-receive",
                json={"product_id": P_FAB, "doc_uom": "roll", "doc_qty": 10,
                      "lot": f"{MARK}-F1", "bin_id": "B1-01"}, timeout=60)
    if r.status_code == 200 and near(r.json().get("received_qty"), FAB_PO_QTY, 0.02):
        ok(f"10 roll diterima = {r.json()['received_qty']:g} yard (tepat qty PO)")
    else:
        bad(f"Terima 10 roll gagal: {r.status_code} {r.text[:200]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 11 — US-F4: satuan tanpa faktor ⇒ pesan yang MEMBERI TAHU langkah perbaikan")
    po2 = create_po(s, P_FAB, 100, "yard", 34000, "kain-2")
    t2 = inbound_task(s, po2["id"], P_FAB)
    r = wh.post(f"{API}/inbound/tasks/{t2['id']}/scan-receive",
                json={"product_id": P_FAB, "doc_uom": "bale", "doc_qty": 3}, timeout=60)
    d = (r.json() or {}).get("detail", "") if r.status_code == 400 else ""
    if r.status_code == 400 and "Barang Supplier" in d:
        ok(f"Satuan 'bale' (tak terdaftar) ditolak dengan arahan → \"{d[:140]}\"")
    else:
        bad(f"Satuan tak terdaftar tidak ditolak/pesan tidak actionable: {r.status_code} {d[:200]}")
    r = wh.post(f"{API}/inbound/tasks/{t2['id']}/scan-receive",
                json={"product_id": P_FAB, "doc_uom": "roll", "doc_qty": 0}, timeout=60)
    if r.status_code == 400:
        ok("doc_qty = 0 ditolak 400 dengan pesan Indonesia (bukan 422 detail Pydantic)")
    else:
        bad(f"doc_qty 0 tidak ditolak 400: {r.status_code} {r.text[:160]}")
    r = wh.post(f"{API}/inbound/tasks/{t2['id']}/preview-uom",
                json={"doc_uom": "roll", "doc_qty": 0}, timeout=30)
    d0 = (r.json() or {}).get("detail", "") if r.status_code == 400 else ""
    if r.status_code == 400 and "lebih besar dari 0" in d0:
        ok(f"Pratinjau doc_qty = 0 ditolak 400 beralasan → \"{d0[:80]}\"")
    else:
        bad(f"Pratinjau doc_qty 0 tidak 400 beralasan: {r.status_code} {r.text[:160]}")
    r = wh.post(f"{API}/inbound/tasks/{t2['id']}/preview-uom",
                json={"doc_uom": "", "doc_qty": 5}, timeout=30)
    if r.status_code == 400 and "wajib diisi" in (r.json() or {}).get("detail", ""):
        ok("Pratinjau tanpa satuan ditolak 400 beralasan (bukan 422)")
    else:
        bad(f"Pratinjau tanpa satuan tidak 400 beralasan: {r.status_code} {r.text[:160]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 12 — F1-02 fallback registry: satuan DASAR produk tetap bisa dipakai")
    r = s.get(f"{API}/inbound/tasks/{t2['id']}/uom-options", timeout=30).json()
    if "yard" in [o["value"] for o in r["options"]]:
        ok("Satuan dasar produk selalu tersedia sebagai opsi (jalur registry)")
    else:
        bad(f"Satuan dasar tidak ada di opsi: {[o['value'] for o in r['options']]}")
    r = wh.post(f"{API}/inbound/tasks/{t2['id']}/preview-uom",
                json={"doc_uom": "yard", "doc_qty": 50}, timeout=30)
    if r.status_code == 200 and r.json()["trail"]["source"] == "same_unit":
        ok("Satuan sama dengan satuan PO → sumber `same_unit`, faktor 1 (tanpa aturan tambahan)")
    else:
        bad(f"Jalur same_unit gagal: {r.status_code} {r.text[:200]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 13 — US-F6/F1-08: kebijakan `off` mematikan input satuan supplier")
    set_policy(s, supplier_uom_input_mode="off")
    r = wh.post(f"{API}/inbound/tasks/{t2['id']}/scan-receive",
                json={"product_id": P_FAB, "doc_uom": "roll", "doc_qty": 1}, timeout=60)
    d = (r.json() or {}).get("detail", "") if r.status_code == 400 else ""
    if r.status_code == 400 and "DIMATIKAN" in d.upper():
        ok("Mode `off`: input satuan supplier ditolak dengan penjelasan kebijakan")
    else:
        bad(f"Mode off tidak menolak: {r.status_code} {d[:160]}")
    o = s.get(f"{API}/inbound/tasks/{t2['id']}/uom-options", timeout=30).json()
    if [x["value"] for x in o["options"]] == [o["task_uom"]] and o["default_uom"] == o["task_uom"]:
        ok("Mode `off`: opsi satuan menyusut ke satuan KN saja (UI konsisten dgn kebijakan)")
    else:
        bad(f"Mode off tidak menyusutkan opsi: {[x['value'] for x in o['options']]}")
    set_policy(s, supplier_uom_input_mode="optional")
    o = s.get(f"{API}/inbound/tasks/{t2['id']}/uom-options", timeout=30).json()
    if o["default_uom"] == o["task_uom"] and len(o["options"]) >= 2:
        ok("Mode `optional`: satuan supplier tersedia tapi default tetap satuan KN")
    else:
        bad(f"Mode optional salah: default={o['default_uom']} opts={len(o['options'])}")
    r = s.put(f"{API}/receiving/uom-settings", json={"supplier_uom_input_mode": "ngawur"}, timeout=30)
    if r.status_code == 400:
        ok("Mode tak dikenal ditolak 400 (kebijakan tidak bisa dirusak)")
    else:
        bad(f"Mode ngawur diterima: {r.status_code}")
    set_policy(s, supplier_uom_input_mode="prefer")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 14 — RBAC & pagar entitas")
    r = wh.get(f"{API}/inbound/tasks/{t2['id']}/uom-options", timeout=30)
    if r.status_code == 200:
        ok("Warehouse BOLEH melihat opsi satuan (dia yang menerima barang)")
    else:
        bad(f"Warehouse ditolak melihat opsi satuan: {r.status_code}")
    r = wh.put(f"{API}/receiving/uom-settings", json={"supplier_uom_input_mode": "off"}, timeout=30)
    if r.status_code == 403:
        ok("Warehouse DITOLAK 403 mengubah kebijakan penerimaan (hanya admin/manager)")
    else:
        bad(f"Warehouse bisa mengubah kebijakan: {r.status_code}")
    sl = sess("sales@kainnusantara.id")
    r = sl.get(f"{API}/inbound/tasks/{t2['id']}/uom-options", timeout=30)
    if r.status_code == 403:
        ok("Sales DITOLAK 403 mengakses opsi satuan penerimaan (bukan wewenangnya)")
    else:
        bad(f"Sales bisa mengakses opsi satuan: {r.status_code}")
    r = s.get(f"{API}/inbound/tasks/wms_tidak_ada/uom-options", timeout=30)
    if r.status_code == 404:
        ok("Task tidak ada → 404 (bukan 500)")
    else:
        bad(f"Task tidak ada tidak 404: {r.status_code}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 15 — INV-RCV-01..03 hijau pada data POC (sebelum dibersihkan)")
    tasks = await db.wms_tasks.find({"flow_type": "inbound"}, {"_id": 0}).to_list(5000)
    bad_trail, bad_sum, bad_src = [], [], []
    for t in tasks:
        for sc in t.get("scan_log") or []:
            tr = sc.get("uom_trail") or {}
            if not tr:
                continue
            if not (tr.get("doc_uom") and tr.get("task_uom") and float(tr.get("factor") or 0) > 0):
                bad_trail.append(f"{t.get('id')}/{sc.get('id')}")
            if not near(float(tr.get("doc_qty") or 0) * float(tr.get("factor") or 0),
                        float(tr.get("task_qty") or 0), 0.05):
                bad_sum.append(f"{t.get('id')}/{sc.get('id')}")
            if tr.get("source") not in ("same_unit", "supplier_item", "fixed_uom",
                                        "product_override", "global_rule",
                                        "formula_gsm_width", "hop_base"):
                bad_src.append(f"{t.get('id')}:{tr.get('source')}")
    if not bad_trail:
        ok(f"INV-RCV-01: semua jejak konversi penerimaan lengkap ({len(tasks)} task diperiksa)")
    else:
        bad(f"INV-RCV-01 gagal: {bad_trail[:5]}")
    if not bad_sum:
        ok("INV-RCV-02: doc_qty × faktor == task_qty pada semua jejak (matematika konsisten)")
    else:
        bad(f"INV-RCV-02 gagal: {bad_sum[:5]}")
    if not bad_src:
        ok("INV-RCV-03: sumber faktor selalu dari daftar sah (tidak ada faktor 'karangan')")
    else:
        bad(f"INV-RCV-03 gagal: {bad_src[:5]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 16 — Kebersihan data: artifact POC dibersihkan")
    await cleanup(db)
    left = (await db.supplier_items.count_documents({"supplier_id": SUP})
            + await db.purchase_orders.count_documents({"notes": {"$regex": MARK}})
            + await db.products.count_documents({"id": {"$in": PRODUCTS}}))
    if left == 0:
        ok("Semua artifact POC dihapus (invarian global tetap pristine)")
    else:
        bad(f"Masih ada {left} artifact POC tertinggal")
    client.close()


def main():
    print("=" * 64)
    print("  POC FASE F-1 — PENERIMAAN BERBASIS SATUAN SUPPLIER")
    print("=" * 64)
    try:
        asyncio.run(run())
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        bad(f"EXCEPTION: {exc}")
    print("\n" + "=" * 64)
    print(f"  \033[92mPASS {len(PASS)}\033[0m  |  \033[91mFAIL {len(FAIL)}\033[0m")
    if FAIL:
        print("\033[91m\033[1m  POC FASE F-1 MERAH — perbaiki dulu sebelum menyentuh UI.\033[0m")
        for f in FAIL:
            print(f"    - {f}")
    else:
        print("\033[92m\033[1m  POC FASE F-1 HIJAU — penerimaan satuan supplier terbukti.\033[0m")
    print("=" * 64)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
