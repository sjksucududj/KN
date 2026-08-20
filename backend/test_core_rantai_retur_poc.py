"""FASE E-9 — **POC RANTAI JUAL → BELI INTERNAL → RETUR BERANTAI** (skenario pemilik)

Skenario yang dibuktikan ujung-ke-ujung lewat HTTP nyata (bukan unit test):

    Entitas B (CV Kanda Suka) beli dari supplier Toba Craft (PO + penerimaan gudang)
        → Customer A pesan di Entitas A (PT Kain Suka Cita); stok A KOSONG → pesanan
          "menunggu stok"
        → A BELI INTERNAL dari B (dokumen kembar antar-PT + kontrak harga internal)
        → barang berpindah gudang  ⇒  **pesanan Customer A terpenuhi OTOMATIS** (E9.1)
        → Customer A retur ke A (inspeksi grade B → karantina → roll RTN-…)
        → A retur ke B  ⇒  jalur pindah-kepemilikan at-cost **DITOLAK** dengan tuntunan
          (E9.3), yang sah hanya **Retur Antar-PT** dan roll yang dikirim balik adalah
          **roll hasil retur pelanggan** (E9.4)
        → B retur ke supplier ASLINYA  ⇒  jejak `supplier_id`/`po_id` **tidak hilang**
          walau barangnya sudah melewati retur pelanggan + dua kali pindah PT (E9.5)
        → ketiga retur **saling tertaut** dan terbaca satu layar (E9.6)

Enam PUTUS/RISIKO yang ditutup fase ini (`ANALISIS_FLOW_RETUR_BERANTAI.md`):
  R1/E9.1  penerimaan antar-PT tidak memicu `auto_fulfill_backorders`
  R2/E9.2  transaksi antar-PT tidak tertaut pesanan pemicunya
  R3/E9.3  DUA jalan untuk satu peristiwa (at-cost vs retur antar-PT) tanpa rambu
  R4/E9.4  retur antar-PT memilih roll FEFO — roll bagus terkirim, roll cacat tinggal
  R5/E9.5  roll retur tanpa jejak supplier/PO → tidak bisa diretur ke supplier aslinya
  R6/E9.6  ketiga retur tidak saling tertaut

POC ini **memakai master & dokumen miliknya sendiri** (produk `prod_e9_*`, ditandai
`FASEE9POC`) dan **menghapus seluruh jejaknya** di akhir — dibuktikan blok CLEANUP.

Jalankan: cd /app && python backend/test_core_rantai_retur_poc.py
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

# Entitas A = yang menjual ke pelanggan · Entitas B = pemasok internalnya.
ENT_A = "ent_ksc"          # PT Kain Suka Cita
ENT_B = "ent_kanda"        # CV Kanda Suka
WH_B = "wh_tangerang"      # gudang khusus Entitas B
# Supplier & pelanggan uji dicari lewat NAMA, bukan id.
# Alasan: `seed_realistic.py` menerbitkan id pemasok secara acak setiap kali dijalankan
# (`sup_<hex>`), jadi id yang di-hardcode akan basi pada setiap seed ulang — POC harus
# tetap jalan di kontainer baru tanpa disentuh.
SUP_B_NAME = "Toba Craft"           # supplier milik Entitas B
CUST_A_NAME = "Butik Bali Indah"    # pelanggan Entitas A (tidak terblokir kredit)

MARK = "FASEE9POC"
PROD = "prod_e9_rantai"
# Nama produk uji dipakai juga sebagai snapshot di dokumen (nota kredit, baris retur).
# Disimpan sebagai konstanta agar `seed_e9_chain_demo.py` bisa menimpanya — dulu nama ini
# ditulis-keras di badan permintaan sehingga data demo menampilkan nama produk POC.
PROD_NAME = "POC E-9 Kain Rantai Retur"
PO_QTY = 40.0              # yard diterima B dari supplier
SO_QTY = 25.0              # yard dipesan Customer A (stok A = 0 → menunggu stok)
# Entitas A sengaja membeli internal LEBIH BANYAK dari pesanannya, sehingga sesudah
# barang masuk gudang A ada roll **BAGUS** yang tersisa (IC_QTY − SO_QTY). Tanpa roll
# bagus itu, pemilihan FEFO tidak punya pilihan salah untuk dibuat dan uji E9.4
# ("roll bagus terkirim balik, roll cacat tinggal") tidak akan pernah bisa memerah.
IC_QTY = 37.0              # yard dibeli internal A dari B
RET_QTY = 10.0             # yard diretur Customer A
PRICE_SUP = 90000.0        # harga beli B dari supplier
PRICE_INT = 120000.0       # harga jual internal B → A (kontrak internal)
PRICE_CUST = 175000.0      # harga jual A → Customer A

PASS, FAIL = [], []
ST: dict = {}


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


_TOKENS: dict = {}


def sess(email="admin@kainnusantara.id", entity=""):
    """Sesi HTTP untuk satu akun × satu badan usaha.

    Token di-CACHE per akun: POC ini butuh tiga sudut pandang admin (Entitas A,
    Entitas B, gabungan) yang semuanya akun yang sama. Dulu tiap sudut pandang
    melakukan login sendiri, jadi satu jalan-ulang POC = 6 login. Itu boros dan —
    ketika ada proses lain yang sedang menyegarkan data demo — mudah menabrak
    pagar keamanan `MAX_LOGIN_ATTEMPTS` (kunci 15 menit, HTTP 429) yang membuat
    POC gagal karena alasan yang tidak ada hubungannya dengan yang diuji.
    """
    if email not in _TOKENS:
        r = requests.post(f"{API}/auth/login",
                          json={"email": email, "password": "demo12345"}, timeout=30)
        if r.status_code == 429:
            raise SystemExit(
                f"\n  Login {email} terkunci sementara (429): {r.json().get('detail', '')}\n"
                f"  Ini pagar keamanan login, BUKAN kegagalan fitur. Penyebab tersering:\n"
                f"  ada proses lain (seed/gate) yang menghapus-ulang pengguna saat POC login.\n"
                f"  Tunggu sampai kuncinya habis, atau kosongkan `login_attempts`, lalu ulangi.")
        r.raise_for_status()
        _TOKENS[email] = r.json()["token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {_TOKENS[email]}"})
    if entity:
        s.headers.update({"X-Entity-Id": entity})
    return s


# ═══════════════════════════════════════════════════════════════════════════
#  SETUP / CLEANUP
# ═══════════════════════════════════════════════════════════════════════════
async def wipe(db):
    """Hapus SELURUH jejak POC (dipanggil di awal & akhir)."""
    # Dokumen yang menyebut produk POC / bertanda MARK.
    pos = await db.purchase_orders.find({"notes": {"$regex": MARK}},
                                        {"_id": 0, "id": 1}).to_list(200)
    po_ids = [p["id"] for p in pos]
    tasks = await db.wms_tasks.find({"$or": [{"po_id": {"$in": po_ids}},
                                             {"product_id": PROD}]},
                                    {"_id": 0, "id": 1}).to_list(500)
    task_ids = [t["id"] for t in tasks]
    sos = await db.sales_orders.find({"$or": [{"notes": {"$regex": MARK}},
                                              {"items.product_id": PROD}]},
                                     {"_id": 0, "id": 1}).to_list(200)
    so_ids = [s["id"] for s in sos]
    srets = await db.sales_returns.find({"order_id": {"$in": so_ids}},
                                        {"_id": 0, "id": 1}).to_list(200)
    sret_ids = [s["id"] for s in srets]
    icts = await db.interco_transactions.find({"items.product_id": PROD},
                                              {"_id": 0, "id": 1, "pair_id": 1}).to_list(200)
    ict_pairs = [d["pair_id"] for d in icts]
    icrs = await db.interco_returns.find({"items.product_id": PROD},
                                         {"_id": 0, "id": 1, "return_pair_id": 1}).to_list(200)
    icr_pairs = [d["return_pair_id"] for d in icrs]
    prets = await db.purchase_returns.find({"items.product_id": PROD},
                                           {"_id": 0, "id": 1}).to_list(200)
    pret_ids = [p["id"] for p in prets]
    # Id turunan yang JUGA menjadi subjek jejak audit & jurnal. Dulu hanya dokumen
    # induk yang dibersihkan, sehingga tiap jalan-ulang POC meninggalkan ±11 baris
    # `audit_logs` (roll diinspeksi, transfer disetujui, kontrak internal dibuat,
    # produk uji dibuat) — terlihat oleh gate INV-GATE-01 sebagai residu.
    ict_ids = [d["id"] for d in icts]
    icr_ids = [d["id"] for d in icrs]
    trfs = await db.warehouse_transfers.find(
        {"$or": [{"interco_pair_id": {"$in": ict_pairs}},
                 {"interco_return_pair_id": {"$in": icr_pairs}},
                 {"items.product_id": PROD}]}, {"_id": 0, "id": 1}).to_list(500)
    trf_ids = [t["id"] for t in trfs]
    roll_ids = [r["id"] for r in await db.inventory_rolls.find(
        {"product_id": PROD}, {"_id": 0, "id": 1}).to_list(5000)]
    ct_ids = [c["id"] for c in await db.supplier_contracts.find(
        {"notes": {"$regex": MARK}}, {"_id": 0, "id": 1}).to_list(200)]
    cn_ids = [c["id"] for c in await db.credit_notes.find(
        {"return_id": {"$in": sret_ids}}, {"_id": 0, "id": 1}).to_list(200)]

    for sid in po_ids + task_ids + so_ids + sret_ids + pret_ids + ict_pairs + icr_pairs:
        await db.journal_entries.delete_many({"source_id": {"$regex": f"^{sid}"}})
        await db.journal_entries.delete_many({"source_id": sid})
        await db.notifications.delete_many({"ref": {"$regex": sid}})
    # Jejak audit: hapus berdasarkan SELURUH id yang disentuh POC (termasuk turunan)
    # + produk ujinya sendiri, supaya POC benar-benar tidak meninggalkan apa pun.
    audit_ids = (po_ids + task_ids + so_ids + sret_ids + pret_ids + ict_pairs
                 + icr_pairs + ict_ids + icr_ids + trf_ids + roll_ids + ct_ids
                 + cn_ids + [PROD])
    if audit_ids:
        await db.audit_logs.delete_many({"entity_id": {"$in": audit_ids}})
    await db.intercompany_eliminations.delete_many(
        {"source_g6_pair_id": {"$in": ict_pairs}})
    await db.warehouse_transfers.delete_many(
        {"$or": [{"interco_pair_id": {"$in": ict_pairs}},
                 {"interco_return_pair_id": {"$in": icr_pairs}},
                 {"items.product_id": PROD}]})
    await db.interco_transactions.delete_many({"pair_id": {"$in": ict_pairs}})
    await db.interco_returns.delete_many({"return_pair_id": {"$in": icr_pairs}})
    await db.interco_accounts.delete_many({"id": {"$regex": "^ica_e9poc"}})
    await db.purchase_returns.delete_many({"id": {"$in": pret_ids}})
    await db.credit_notes.delete_many({"return_id": {"$in": sret_ids}})
    await db.sales_returns.delete_many({"id": {"$in": sret_ids}})
    await db.shipments.delete_many({"order_id": {"$in": so_ids}})
    await db.sales_orders.delete_many({"id": {"$in": so_ids}})
    await db.wms_tasks.delete_many({"id": {"$in": task_ids}})
    await db.vendor_bills.delete_many({"po_id": {"$in": po_ids}})
    await db.purchase_orders.delete_many({"id": {"$in": po_ids}})
    await db.supplier_contracts.delete_many({"notes": {"$regex": MARK}})
    # Stok & silsilah produk POC
    lots = await db.inventory_lots.find({"product_id": PROD}, {"_id": 0, "id": 1}).to_list(500)
    lot_ids = [x["id"] for x in lots]
    await db.inventory_lots.delete_many({"product_id": PROD})
    if lot_ids:
        await db.inventory_lots.update_many({}, {"$pull": {"parent_lot_ids": {"$in": lot_ids}}})
        await db.inventory_lots.update_many({}, {"$pull": {"child_lot_ids": {"$in": lot_ids}}})
    await db.inventory_rolls.delete_many({"product_id": PROD})
    await db.inventory_movements.delete_many({"product_id": PROD})
    await db.inventory_balances.delete_many({"product_id": PROD})
    await db.products.delete_many({"id": PROD})
    # Saldo antar-PT dihitung ulang dari transaksi yang TERSISA (bukan dihapus buta).
    try:
        from services import interco_service as ics
        await ics._update_account_balance(ENT_B, ENT_A)   # noqa: SLF001
        await ics._update_account_balance(ENT_A, ENT_B)   # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        print(f"  [cleanup] hitung ulang saldo antar-PT gagal: {exc}")
    return {"po": len(po_ids), "so": len(so_ids), "sret": len(sret_ids),
            "ict": len(ict_pairs), "icr": len(icr_pairs), "pret": len(pret_ids)}


def resolve_demo_data(adm_a, adm_b) -> bool:
    """Cari id pemasok & pelanggan uji dari API (bukan id hardcode yang bisa basi)."""
    sups = adm_b.get(f"{API}/suppliers", timeout=30).json()
    sl = sups if isinstance(sups, list) else (sups.get("items") or sups.get("rows") or [])
    sup = next((s for s in sl if (s.get("name") or "").strip() == SUP_B_NAME), None)
    if not sup:
        bad(f"Supplier uji '{SUP_B_NAME}' tidak ada di Entitas B ({len(sl)} pemasok terbaca)")
        return False
    ST["sup_b"] = sup["id"]
    ST["sup_b_name"] = sup.get("name")

    custs = adm_a.get(f"{API}/customers", timeout=30).json()
    cl = custs if isinstance(custs, list) else (custs.get("items") or custs.get("rows") or [])
    cust = next((c for c in cl if (c.get("name") or "").strip() == CUST_A_NAME), None)
    if not cust:
        bad(f"Pelanggan uji '{CUST_A_NAME}' tidak ada di Entitas A ({len(cl)} pelanggan terbaca)")
        return False
    addrs = cust.get("addresses") or []
    addr = next((a["id"] for a in addrs if a.get("is_primary")), None) or (
        addrs[0]["id"] if addrs else "")
    if not addr:
        bad(f"Pelanggan uji '{CUST_A_NAME}' tidak punya alamat kirim")
        return False
    ST["cust_a"] = cust["id"]
    ST["cust_addr"] = addr
    info(f"Data uji: pemasok {ST['sup_b_name']} ({ST['sup_b']}) · "
         f"pelanggan {cust['name']} ({cust['id']}) alamat {addr}")
    return True


async def make_product(db):
    await db.products.update_one({"id": PROD}, {"$set": {
        "id": PROD, "sku": "E9-RANTAI-01",
        "name": PROD_NAME,
        "category": "Kain", "base_unit": "yard", "price": PRICE_CUST,
        "harga_pokok": PRICE_SUP, "stage": "finished", "fabric_type": "woven",
        "gramasi": 140.0, "lebar": 1.15, "grade": "A", "status": "active",
        # Master produk BERSAMA seluruh badan usaha (keputusan E-4) — persis seperti
        # produk data demo: `entity_id` DIKOSONGKAN. Dulu di sini produk uji distempel
        # `ent_kanda`, dan karena produk dikembalikan apa adanya oleh `/api/products`
        # & dashboard, sales PT-A jadi membaca id badan usaha PT-B (gate isolasi merah).
        "entity_id": None, "reorder_point": 0.0, "reorder_qty": 0.0,
        "notes": MARK, "created_at": now_iso(), "updated_at": now_iso()}}, upsert=True)


# ═══════════════════════════════════════════════════════════════════════════
#  LANGKAH 1 — Entitas B beli dari supplier (jejak asal barang lahir di sini)
# ═══════════════════════════════════════════════════════════════════════════
def step1_supplier_receipt(adm_b, wh_b):
    head("LANGKAH 1 — Entitas B (CV Kanda Suka) beli dari supplier Toba Craft")
    r = adm_b.post(f"{API}/purchase-orders", json={
        "supplier_id": ST["sup_b"], "warehouse_id": WH_B,
        "items": [{"product_id": PROD, "quantity": PO_QTY, "unit": "yard",
                   "price": PRICE_SUP, "expected_grade": "A"}],
        "notes": f"{MARK} pembelian awal Entitas B"}, timeout=60)
    if r.status_code != 200:
        bad(f"PO supplier gagal dibuat ({r.status_code} {r.text[:200]})")
        return False
    po = r.json()
    for _ in range(6):
        if po.get("status") != "waiting_approval":
            break
        ra = adm_b.post(f"{API}/purchase-orders/{po['id']}/approve",
                        json={"notes": f"{MARK} approve"}, timeout=60)
        if ra.status_code != 200:
            break
        po = ra.json()
    ST["po"] = po
    ok(f"PO {po.get('po_number')} ke Toba Craft terbit ({PO_QTY:g} yard · status {po.get('status')})")

    rows = adm_b.get(f"{API}/inbound/tasks", timeout=30).json()
    task = next((t for t in rows if t.get("po_id") == po["id"]
                 and t.get("product_id") == PROD), None)
    if not task:
        bad("Tugas penerimaan gudang untuk PO ini tidak terbentuk")
        return False
    rc = wh_b.post(f"{API}/inbound/tasks/{task['id']}/scan-receive",
                   json={"product_id": PROD, "actual_qty": PO_QTY}, timeout=60)
    if rc.status_code != 200:
        bad(f"scan-receive gagal ({rc.status_code} {rc.text[:200]})")
        return False
    rz = wh_b.post(f"{API}/inbound/tasks/{task['id']}/complete",
                   json={"notes": f"{MARK} GR"}, timeout=60)
    if rz.status_code != 200:
        bad(f"Selesaikan penerimaan gagal ({rz.status_code} {rz.text[:200]})")
        return False
    ST["task"] = task
    # Barang masuk KARANTINA dulu (kebijakan QC bawaan) — barang yang belum lolos
    # inspeksi memang tidak boleh dijanjikan ke PT lain. Jadi QC diputuskan di sini,
    # sama seperti yang dilakukan gudang sungguhan.
    rq = wh_b.post(f"{API}/inbound/tasks/{task['id']}/qc-decision", json={
        "accept_qty": PO_QTY, "reject_qty": 0, "accept_grade": "A",
        "reason": f"{MARK} lolos QC"}, timeout=90)
    if rq.status_code != 200:
        bad(f"Keputusan QC penerimaan gagal ({rq.status_code} {rq.text[:200]})")
        return False
    ok(f"Barang diterima gudang {WH_B} & lolos QC — roll milik Entitas B lahir "
       f"dengan jejak supplier & PO")
    return True


# ═══════════════════════════════════════════════════════════════════════════
#  LANGKAH 2 — Customer A pesan di Entitas A; stok A kosong
# ═══════════════════════════════════════════════════════════════════════════
def step2_customer_order(adm_a):
    head("LANGKAH 2 — Customer A pesan di Entitas A, stoknya KOSONG → menunggu stok")
    r = adm_a.post(f"{API}/sales-orders", json={
        "customer_id": ST["cust_a"], "shipping_address_id": ST["cust_addr"],
        "items": [{"product_id": PROD, "quantity": SO_QTY, "unit": "yard",
                   "price": PRICE_CUST}],
        # Backorder DIIZINKAN: inilah pintu masuk keputusan "beli internal atau tidak".
        "allow_backorder": True,
        "sales_name": "Ayu Permatasari",
        "notes": f"{MARK} pesanan Customer A"}, timeout=60)
    if r.status_code != 200:
        bad(f"Pesanan pelanggan gagal dibuat ({r.status_code} {r.text[:300]})")
        return False
    so = r.json()
    ST["so"] = so
    bo = sum(float(b.get("backorder_qty") or 0) for b in (so.get("backorders") or []))
    if so.get("status") == "waiting_stock" and near(bo, SO_QTY):
        ok(f"{so['number']} berstatus MENUNGGU STOK dengan backorder {bo:g} yard "
           f"(stok Entitas A memang nol)")
    else:
        bad(f"Pesanan tidak menunggu stok seperti seharusnya: status={so.get('status')} "
            f"backorder={bo}")
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
#  LANGKAH 3 — A beli internal dari B (E9.2) & barang berpindah (E9.1)
# ═══════════════════════════════════════════════════════════════════════════
def step3_internal_purchase(adm_all, adm_a, wh_b):
    head("LANGKAH 3 — Entitas A beli internal dari Entitas B (E9.2) lalu barang berpindah (E9.1)")
    so = ST["so"]
    # Kontrak harga internal arah B→A untuk produk POC (sistem sengaja tidak menebak harga).
    rc = adm_all.post(f"{API}/supplier-contracts", json={
        "contract_type": "internal",          # jenis kontrak: makloon | purchase | internal
        "partner_kind": "entity", "partner_id": ENT_A, "product_id": PROD,
        "tariff_rate": PRICE_INT, "status": "active",
        "entity_id": ENT_B, "notes": f"{MARK} kontrak harga internal B→A"},
        headers={"X-Entity-Id": ENT_B}, timeout=60)
    if rc.status_code not in (200, 201):
        bad(f"Kontrak harga internal gagal dibuat ({rc.status_code} {rc.text[:250]})")
        return False
    ST["contract"] = rc.json()
    ok(f"Kontrak harga internal {rc.json().get('contract_number')} aktif "
       f"(Rp {PRICE_INT:,.0f}/yard)")

    r = adm_all.post(f"{API}/interco/transactions", json={
        "seller_entity_id": ENT_B, "buyer_entity_id": ENT_A,
        "pricing_mode": "fixed_price",
        "items": [{"product_id": PROD, "quantity": IC_QTY}],
        "source_order_id": so["id"], "source_order_number": so["number"],
        "submit_now": True,
        "notes": f"{MARK} beli internal untuk {so['number']}"}, timeout=60)
    if r.status_code != 200:
        bad(f"Transaksi antar-PT gagal ({r.status_code} {r.text[:300]})")
        return False
    pair = r.json()
    ST["ict"] = pair
    seller_doc, buyer_doc = pair["seller"], pair["buyer"]
    ok(f"Dokumen kembar terbit: {seller_doc['number']} (B) ↔ {buyer_doc['number']} (A) · "
       f"status {seller_doc['status']}")

    # E9.2 — pesanan pemicunya WAJIB terbaca di layar pesanan.
    det = adm_a.get(f"{API}/sales-orders/{so['id']}", timeout=30).json()
    sup = det.get("interco_supply") or []
    hit = next((x for x in sup if x.get("number") == buyer_doc["number"]), None)
    if hit and hit.get("from_entity_name"):
        ok(f"E9.2 · US24 — layar pesanan menyebut asalnya: "
           f"“diambil dari {hit['from_entity_name']} lewat {hit['number']}”")
    else:
        bad(f"Layar pesanan tidak menyebut janji pasokan antar-PT: {sup}")

    # E9.2 — Papan Pending SO ikut menunjukkan janji dari PT lain (sebelum barang masuk).
    board = adm_a.get(f"{API}/stock/pending-so", timeout=60).json()
    rows = board if isinstance(board, list) else board.get("rows", [])
    brow = next((x for x in rows if x.get("order_id") == so["id"]), None)
    proms = (brow or {}).get("interco_promises") or []
    if (brow and proms and near(brow.get("interco_incoming"), IC_QTY)
            and brow.get("coverage") == "covered"):
        ok(f"E9.2 — Papan Pending SO: {brow['coverage']} · dijanjikan {proms[0]['qty']:g} yard "
           f"dari {proms[0]['from_entity_name']} lewat {proms[0]['interco_number']}")
    else:
        bad(f"Papan Pending SO tidak menampilkan janji antar-PT: {brow}")

    # Barang fisik berpindah: tugas gudang → disetujui gudang B.
    rt = adm_all.post(f"{API}/interco/transactions/{seller_doc['id']}/warehouse-task",
                      json={"note": f"{MARK} kirim ke Entitas A"}, timeout=60)
    if rt.status_code != 200:
        bad(f"Tugas gudang antar-PT gagal ({rt.status_code} {rt.text[:250]})")
        return False
    trf = rt.json()
    ST["trf"] = trf
    ra = wh_b.post(f"{API}/transfers/{trf['id']}/approve",
                   json={"notes": f"{MARK} setuju kirim"}, timeout=90)
    if ra.status_code != 200:
        bad(f"Persetujuan transfer gagal ({ra.status_code} {ra.text[:250]})")
        return False
    ok(f"Tugas gudang {trf.get('code')} disetujui — kepemilikan roll pindah B → A")

    # ── INTI E9.1 — pesanan pelanggan terpenuhi OTOMATIS ────────────────────
    after = adm_a.get(f"{API}/sales-orders/{so['id']}", timeout=30).json()
    bo_after = sum(float(b.get("backorder_qty") or 0) for b in (after.get("backorders") or []))
    if after.get("status") != "waiting_stock" and bo_after <= 0.01:
        ok(f"E9.1 · US23 — {so['number']} otomatis terpenuhi begitu barang antar-PT masuk "
           f"(status {after.get('status')} · backorder {bo_after:g}) — TANPA alokasi manual")
    else:
        bad(f"Pesanan TIDAK terpenuhi otomatis: status={after.get('status')} "
            f"backorder={bo_after}")
    ST["so"] = after
    # Saldo utang A→B DIREKAM di sini (bukan dibandingkan absolut nanti): data demo &
    # transaksi antar-PT lain memakai pasangan PT yang sama, jadi angka absolut bukan
    # milik POC ini. Yang harus benar adalah SELISIH akibat returnya sendiri.
    ap = adm_all.get(f"{API}/interco/accounts/{ENT_A}/{ENT_B}",
                     params={"role": "payable"}, timeout=30)
    ST["ap_before"] = float((ap.json() or {}).get("outstanding") or 0) if ap.status_code == 200 else -1.0
    info(f"Utang Entitas A ke Entitas B sebelum retur: Rp {ST['ap_before']:,.0f}")
    return True


async def step3b_notification(db):
    """E9.1 — pemberitahuan ke Admin Sales harus benar-benar ada (bukan sekadar 200).

    Dicari khusus untuk pesanan RUN INI (nomor SO ada di badan pesan) supaya
    pemberitahuan sisa jalan-ulang lama tidak bisa membuat POC hijau palsu.
    """
    so_no = (ST.get("so") or {}).get("number") or ""
    n = await db.notifications.find_one(
        {"type": "interco_receipt_auto_fulfilled", "body": {"$regex": so_no}},
        {"_id": 0, "body": 1, "link": 1, "recipient_role": 1, "title": 1})
    if (n and n.get("recipient_role") == "sales_admin"
            and "terpenuhi" in f"{n.get('title', '')} {n.get('body', '')}"
            and so_no in n.get("body", "")):
        ok(f"E9.1 — Admin Sales diberi tahu & pesanannya disebut: “{n['title'][:70]}…” "
           f"(tautan {n.get('link')})")
    else:
        bad(f"Notifikasi pemenuhan otomatis tidak ada / salah penerima / tak menyebut {so_no}: {n}")


# ═══════════════════════════════════════════════════════════════════════════
#  LANGKAH 4 — Customer A retur ke Entitas A (jejak asal diwariskan · E9.5)
# ═══════════════════════════════════════════════════════════════════════════
def step4_customer_return(adm_a, mgr_a):
    head("LANGKAH 4 — Customer A retur ke Entitas A (inspeksi → karantina → roll RTN)")
    so = ST["so"]
    # Pesanan harus dikonfirmasi dulu — aturan produk: retur hanya dari pesanan yang sah.
    for path in ("submit-for-approval", "approve", "confirm"):
        rr = adm_a.post(f"{API}/sales-orders/{so['id']}/{path}",
                        json={"notes": f"{MARK} {path}"}, timeout=60)
        if rr.status_code == 200:
            so = rr.json() if isinstance(rr.json(), dict) and rr.json().get("id") else so
    cur = adm_a.get(f"{API}/sales-orders/{so['id']}", timeout=30).json()
    if cur.get("status") not in ("confirmed", "partially_picked", "picked",
                                "partially_shipped", "shipped", "done"):
        bad(f"Pesanan tidak sampai status yang bisa diretur (status {cur.get('status')})")
        return False
    ok(f"{cur['number']} berstatus {cur['status']} — barang sudah jadi hak pelanggan")

    r = adm_a.post(f"{API}/sales-returns", json={
        "order_id": so["id"], "return_type": "retur",
        "items": [{"product_id": PROD, "product_name": PROD_NAME,
                   "quantity_returned": RET_QTY, "unit": "yard",
                   "reason": "Warna tidak sesuai contoh", "condition": "damaged"}],
        "notes": f"{MARK} retur Customer A", "submit_now": True}, timeout=60)
    if r.status_code != 200:
        bad(f"Retur pelanggan gagal dibuat ({r.status_code} {r.text[:300]})")
        return False
    sret = r.json()
    ST["sret"] = sret
    ok(f"Retur pelanggan {sret['number']} terbit ({RET_QTY:g} yard · {sret['status']})")

    for path, body in (("approve", {"notes": f"{MARK} setuju"}),
                       ("inspect/start", {"notes": f"{MARK} mulai inspeksi"})):
        rr = mgr_a.post(f"{API}/sales-returns/{sret['id']}/{path}", json=body, timeout=60)
        if rr.status_code != 200:
            bad(f"{path} retur gagal ({rr.status_code} {rr.text[:250]})")
            return False
    rr = mgr_a.post(f"{API}/sales-returns/{sret['id']}/inspect/complete", json={
        "inspections": [{"product_id": PROD, "grade": "B", "condition": "damaged",
                         "disposition": "return_supplier", "accepted_qty": RET_QTY,
                         "note": f"{MARK} kain belang"}],
        "notes": f"{MARK} inspeksi selesai"}, timeout=60)
    if rr.status_code != 200:
        bad(f"Inspeksi retur gagal ({rr.status_code} {rr.text[:250]})")
        return False
    rs = mgr_a.post(f"{API}/sales-returns/{sret['id']}/settle",
                    json={"outcome": "store_credit", "notes": f"{MARK} nota kredit"},
                    timeout=90)
    if rs.status_code != 200:
        bad(f"Penyelesaian retur gagal ({rs.status_code} {rs.text[:250]})")
        return False
    ok("Retur diselesaikan (nota kredit terbit) — barang masuk KARANTINA, bukan langsung stok")

    q = adm_a.get(f"{API}/sales-returns/{sret['id']}/quarantine", timeout=30).json()
    if not q:
        bad("Roll karantina hasil retur tidak terbentuk")
        return False
    roll = q[0]
    ST["rtn_roll"] = roll
    # ── INTI E9.5 — jejak asal barang ikut diwarisi ─────────────────────────
    if roll.get("supplier_id") == ST["sup_b"] and roll.get("po_id") == ST["po"]["id"]:
        ok(f"E9.5 — roll retur {roll.get('roll_number') or roll['id'][-6:]} MEWARISI jejak asal: "
           f"supplier {roll.get('supplier_name') or ST['sup_b_name']} · {roll.get('po_number')}")
    else:
        bad(f"E9.5 — jejak supplier/PO hilang di roll retur: supplier_id={roll.get('supplier_id')} "
            f"po_id={roll.get('po_id')}")
    if roll.get("interco_origin", {}).get("number"):
        ok(f"E9.3 — roll retur tahu asalnya pembelian internal "
           f"{roll['interco_origin']['number']} → jalur at-cost akan diblokir")
    else:
        bad(f"Roll retur tidak mengenali asal pembelian internalnya: {roll.get('interco_origin')}")
    return True


# ═══════════════════════════════════════════════════════════════════════════
#  LANGKAH 5 — A retur ke B: rambu satu jalan (E9.3) + roll benar (E9.4)
# ═══════════════════════════════════════════════════════════════════════════
def step5_interco_return(adm_a, mgr_a, adm_all, wh_b):
    head("LANGKAH 5 — Entitas A retur ke Entitas B (rambu E9.3 + pilihan roll E9.4)")
    sret, roll = ST["sret"], ST["rtn_roll"]
    rel = mgr_a.post(f"{API}/sales-returns/{sret['id']}/quarantine/release", json={
        "decisions": [{"roll_id": roll["id"], "action": "release", "grade": "B"}],
        "notes": f"{MARK} lepas karantina"}, timeout=60)
    if rel.status_code != 200:
        bad(f"Lepas karantina gagal ({rel.status_code} {rel.text[:250]})")
        return False
    ok("Roll retur dilepas dari karantina (grade B) — siap ditindak")

    # ── INTI E9.3 — jalur at-cost WAJIB ditolak dengan tuntunan ─────────────
    blk = mgr_a.post(f"{API}/sales-returns/{sret['id']}/rolls/{roll['id']}/transfer-ownership",
                     json={"dest_entity_id": ENT_B, "notes": f"{MARK} coba at-cost"},
                     timeout=60)
    det = (blk.json() or {}).get("detail", "") if blk.status_code != 200 else ""
    if blk.status_code == 400 and "Retur Antar-PT" in det and "pembelian internal" in det:
        ok(f"E9.3 · US25 — pindah kepemilikan at-cost DITOLAK dengan tuntunan: “{det[:110]}…”")
    else:
        bad(f"E9.3 — jalur at-cost TIDAK diblokir (HTTP {blk.status_code}) {det[:200]}")

    # ── INTI E9.4 — kandidat roll: yang hasil retur pelanggan diutamakan ────
    seller_doc = ST["ict"]["seller"]
    info_r = adm_all.get(f"{API}/interco/transactions/{seller_doc['id']}/returnable",
                         timeout=30).json()
    line = next((l for l in info_r.get("lines", []) if l["product_id"] == PROD), None)
    cand = (line or {}).get("rolls") or []
    rtn_cand = [c for c in cand if c.get("is_customer_return")]
    if rtn_cand and rtn_cand[0]["roll_id"] == roll["id"] and cand[0].get("is_customer_return"):
        ok(f"E9.4 · US26 — kandidat teratas adalah roll hasil retur pelanggan "
           f"({rtn_cand[0]['lot']} · grade {rtn_cand[0]['grade']} · "
           f"{rtn_cand[0]['qty']:g} {rtn_cand[0]['unit']})")
    else:
        bad(f"E9.4 — roll hasil retur pelanggan tidak diutamakan: {cand[:2]}")
    if near(line.get("qty_from_customer_return"), RET_QTY):
        ok(f"E9.4 — layar menyebut {line['qty_from_customer_return']:g} yard berasal dari "
           f"retur pelanggan (bukan stok biasa)")
    else:
        bad(f"E9.4 — ringkasan roll retur salah: {line}")

    rr = adm_all.post(f"{API}/interco/returns", json={
        "interco_id": seller_doc["id"],
        "items": [{"product_id": PROD, "quantity": RET_QTY, "roll_ids": [roll["id"]]}],
        "reason": "Barang diretur pelanggan — dikembalikan ke PT pemasok internal",
        "notes": f"{MARK} retur antar-PT"}, timeout=60)
    if rr.status_code != 200:
        bad(f"Retur antar-PT gagal ({rr.status_code} {rr.text[:300]})")
        return False
    icr = rr.json()["returner"]
    ST["icr"] = icr
    ok(f"Retur antar-PT {icr['number']} ↔ {rr.json()['receiver']['number']} terbit (draf)")
    if icr.get("source_sales_return_id") == sret["id"]:
        ok(f"E9.6 — retur antar-PT membawa asal returnya: {icr.get('source_sales_return_number')}")
    else:
        bad(f"E9.6 — tautan ke retur pelanggan tidak tercatat: {icr.get('source_sales_return_id')}")

    ap = mgr_a.post(f"{API}/interco/returns/{icr['id']}/approve",
                    json={"note": f"{MARK} setuju retur"}, timeout=60)
    if ap.status_code != 200:
        bad(f"Persetujuan retur antar-PT gagal ({ap.status_code} {ap.text[:250]})")
        return False
    tk = adm_all.post(f"{API}/interco/returns/{icr['id']}/warehouse-task",
                      json={"note": f"{MARK} kirim balik"}, timeout=60)
    if tk.status_code != 200:
        bad(f"Tugas gudang retur gagal ({tk.status_code} {tk.text[:250]})")
        return False
    trf = tk.json()
    ST["trf_ret"] = trf
    # Arah balik: barang keluar dari gudang Entitas A → yang berwenang menyetujui
    # pengiriman adalah ENTITAS ASAL transfer, yaitu A (pagar L13 `_guard_transfer`
    # side="source"). Untuk kaki pertama (B→A) yang menyetujui memang B.
    apv = adm_a.post(f"{API}/transfers/{trf['id']}/approve",
                     json={"notes": f"{MARK} kirim balik ke Entitas B"}, timeout=90)
    if apv.status_code != 200:
        bad(f"Persetujuan transfer retur gagal ({apv.status_code} {apv.text[:250]})")
        return False
    ok(f"Tugas gudang retur {trf.get('code')} selesai — kepemilikan roll kembali ke Entitas B")
    return True


async def step5b_verify_roll_back(db):
    """Roll yang kembali harus roll YANG SAMA, dan jejak asalnya tetap utuh."""
    roll = await db.inventory_rolls.find_one({"id": ST["rtn_roll"]["id"]}, {"_id": 0})
    if not roll:
        bad("Roll retur hilang setelah dikembalikan")
        return
    if roll.get("owner_entity_id") == ENT_B:
        ok(f"E9.4 — roll hasil retur pelanggan (lot {roll.get('lot')}) kini milik Entitas B "
           f"— bukan roll bagus dari stok Entitas A")
    else:
        bad(f"Roll tidak berpindah ke Entitas B: owner={roll.get('owner_entity_id')}")
    # Sisi lain dari cacat yang sama: roll BAGUS harus TETAP TINGGAL di Entitas A.
    # (Inilah jebakannya — A memang punya roll bagus yang menganggur saat retur dibuat.)
    good = await db.inventory_rolls.find_one(
        {"product_id": PROD, "owner_entity_id": ENT_A, "status": "available",
         "origin_type": {"$ne": "return"}},
        {"_id": 0, "grade": 1, "length_remaining": 1, "lot": 1})
    if good and near(good.get("length_remaining"), IC_QTY - SO_QTY):
        ok(f"E9.4 — roll BAGUS {good.get('length_remaining'):g} yard (grade "
           f"{good.get('grade')}) TETAP di Entitas A — tidak ikut terkirim balik")
    else:
        bad(f"E9.4 — roll bagus milik Entitas A tidak utuh lagi: {good}")
    if roll.get("supplier_id") == ST["sup_b"] and roll.get("po_id") == ST["po"]["id"]:
        ok("E9.5 — jejak supplier & PO TETAP UTUH setelah dua kali pindah kepemilikan")
    else:
        bad(f"E9.5 — jejak asal hilang: supplier_id={roll.get('supplier_id')} po_id={roll.get('po_id')}")
    hist = roll.get("acquired_history") or []
    if any((h.get("via") == "inbound") for h in hist):
        ok(f"E9.5 — riwayat perolehan tersimpan ({len(hist)} langkah, termasuk penerimaan GRN) "
           f"— `acquired` tidak lagi menghapus jejak")
    else:
        bad(f"E9.5 — riwayat perolehan tidak menyimpan penerimaan GRN: {hist}")
    # E5.3/E-9 — jejak boleh dibaca, tetapi ID TEKNIS badan usaha lawan tidak boleh
    # ikut menempel: roll dikembalikan oleh layar biasa (daftar roll, pegging, kartu
    # riwayat) sehingga satu `ent_*` di sini = kebocoran identitas antar-PT.
    leaked = [f"{k}={v}" for h in hist for k, v in h.items()
              if isinstance(v, str) and v.startswith("ent_")]
    named = [h.get("owner_entity_name") for h in hist if h.get("owner_entity_name")]
    if not leaked and named:
        ok(f"E9.5/E5.3 — riwayat menyebut NAMA badan usaha ({', '.join(sorted(set(named)))}) "
           f"tanpa satu pun id teknis `ent_*`")
    else:
        bad(f"E9.5/E5.3 — id teknis badan usaha bocor di riwayat perolehan: {leaked} "
            f"(nama terbaca: {named})")
    # Saldo antar-PT ikut mengecil (bukan hanya dokumen yang cantik).
    from services import interco_service as ics
    acc = await ics.get_account(ENT_A, ENT_B, role="payable")
    before = float(ST.get("ap_before") or 0)
    out = float(acc.get("outstanding") or 0)
    ret_val = float(ST["icr"].get("grand_total") or 0)
    if before > 0 and near(before - out, ret_val, tol=1.0):
        ok(f"E9-uang — utang Entitas A ke Entitas B turun TEPAT sebesar nilai retur "
           f"(Rp {before:,.0f} → Rp {out:,.0f}; retur Rp {ret_val:,.0f})")
    else:
        bad(f"Penurunan utang antar-PT tidak sesuai nilai retur: sebelum {before} "
            f"sesudah {out} (retur {ret_val})")

    # ── E9.4-uang — sisi BARANG dijurnal sebesar nilai TERCATAT roll, bukan harga
    # jual internalnya. Roll hasil retur pelanggan berkondisi `damaged` sudah
    # dihapus-bukukan jadi Rp 0; mengkreditkan persediaan sebesar harga internal
    # akan membuat GL berselisih abadi dari subledger (INV-GL-DRIFT).
    icr_doc = await db.interco_returns.find_one(
        {"id": ST["icr"]["id"]},
        {"_id": 0, "goods_out_value": 1, "goods_in_value": 1, "goods_value_gap": 1,
         "subtotal": 1})
    jes = await db.journal_entries.find(
        {"source_type": "interco_return",
         "source_id": {"$regex": f"^{ST['icr'].get('return_pair_id', 'x')}:goods"}},
        {"_id": 0, "source_id": 1, "total_debit": 1}).to_list(20)
    go = float((icr_doc or {}).get("goods_out_value") or 0)
    gi = float((icr_doc or {}).get("goods_in_value") or 0)
    gap = float((icr_doc or {}).get("goods_value_gap") or 0)
    if icr_doc and "goods_out_value" in icr_doc and not jes and go <= 0.01 and gi <= 0.01:
        ok(f"E9.4-uang — barang yang kembali sudah bernilai Rp 0 (dihapus-bukukan saat "
           f"retur pelanggan), jadi TIDAK ada jurnal barang palsu; selisih dengan nilai "
           f"retur dicatat jujur sebagai Rp {gap:,.0f}")
    else:
        bad(f"E9.4-uang — sisi barang retur tidak konsisten: nilai tercatat "
            f"out={go} in={gi} gap={gap} · jurnal={[(j['source_id'], j['total_debit']) for j in jes]}")

    # ── E9.6-jejak — nota kredit retur WAJIB tertaut sejak lahir (bukan menunggu
    # backfill saat seed): dokumen yatim membuat penelusuran retur buntu (INV-REF-01).
    cn = await db.credit_notes.find_one({"return_id": ST["sret"]["id"]},
                                        {"_id": 0, "number": 1, "refs": 1})
    rels = {(r.get("rel"), r.get("doc_type")) for r in ((cn or {}).get("refs") or [])}
    if {("corrects", "sales_order"), ("issued_by", "sales_return")} <= rels:
        ok(f"E9.6-jejak — nota kredit {cn['number']} tertaut dua arah sejak lahir "
           f"(ke pesanan & ke retur pelanggan)")
    else:
        bad(f"E9.6-jejak — nota kredit retur lahir sebagai dokumen yatim: {rels}")


# ═══════════════════════════════════════════════════════════════════════════
#  LANGKAH 6 — B retur ke supplier ASLINYA (E9.5) atau menyimpannya
# ═══════════════════════════════════════════════════════════════════════════
def step6_supplier_return(adm_b):
    head("LANGKAH 6 — Entitas B meretur barang itu ke supplier ASLINYA (Toba Craft)")
    roll_id = ST["rtn_roll"]["id"]
    r = adm_b.get(f"{API}/purchase-returns/source-rolls", params={
        "product_id": PROD, "supplier_id": ST["sup_b"], "po_id": ST["po"]["id"],
        "entity_id": ENT_B}, timeout=60)
    if r.status_code != 200:
        bad(f"Kandidat roll retur beli gagal dimuat ({r.status_code} {r.text[:200]})")
        return False
    rolls = r.json().get("rolls", [])
    hit = next((x for x in rolls if x["roll_id"] == roll_id), None)
    if hit:
        ok(f"E9.5 · US28 — roll yang kembali dari Entitas A MUNCUL sebagai kandidat retur ke "
           f"supplier aslinya ({hit.get('supplier_name') or ST['sup_b_name']} · {hit.get('po_number')})")
    else:
        bad(f"E9.5 — roll tidak muncul sebagai kandidat retur ke supplier "
            f"({len(rolls)} kandidat lain)")
        return False

    rp = adm_b.post(f"{API}/purchase-returns", json={
        "supplier_id": ST["sup_b"], "po_id": ST["po"]["id"], "warehouse_id": WH_B,
        "entity_id": ENT_B,
        "items": [{"product_id": PROD, "quantity": hit["qty_remaining"], "unit": "yard",
                   "price": PRICE_SUP, "reason": "cacat", "condition": "damaged",
                   "roll_ids": [roll_id]}],
        "reason": "Kain belang — dikembalikan ke supplier asal",
        "notes": f"{MARK} retur beli", "submit_now": True}, timeout=60)
    if rp.status_code != 200:
        bad(f"Retur beli gagal dibuat ({rp.status_code} {rp.text[:300]})")
        return False
    pret = rp.json()
    ST["pret"] = pret
    ok(f"Retur beli {pret['number']} terbit ke {pret.get('supplier_name')} "
       f"(status {pret.get('status')})")
    if pret.get("origin_interco_return_number"):
        ok(f"E9.6 — retur beli menyebut retur antar-PT asalnya "
           f"({pret['origin_interco_return_number']}) langsung di dokumen yang baru terbit")
    else:
        bad(f"E9.6 — retur beli tidak menyebut retur antar-PT asalnya: "
            f"origin_interco_return_id={pret.get('origin_interco_return_id')}")
    return True


# ═══════════════════════════════════════════════════════════════════════════
#  LANGKAH 7 — satu layar menjawab "kainnya ke mana?" (E9.6)
# ═══════════════════════════════════════════════════════════════════════════
def step7_chain(adm_all, sales_a, wh_user):
    head("LANGKAH 7 — Jejak Retur: satu layar untuk seluruh rantai (E9.6 · US29)")
    for label, doc_id in (("retur pelanggan", ST["sret"]["id"]),
                          ("retur antar-PT", ST["icr"]["id"]),
                          ("retur beli", ST["pret"]["id"])):
        r = adm_all.get(f"{API}/returns/chain/{doc_id}", timeout=30)
        if r.status_code != 200:
            bad(f"Jejak retur dari {label} gagal ({r.status_code} {r.text[:200]})")
            continue
        d = r.json()
        stages = [s["stage"] for s in d.get("steps", [])]
        need = {"sales_return", "interco_return", "purchase_return"}
        if need.issubset(set(stages)):
            ok(f"E9.6 — dibuka dari {label}: rantai utuh ({' → '.join(stages)})")
        else:
            bad(f"E9.6 — rantai tidak utuh saat dibuka dari {label}: {stages}")
    d = adm_all.get(f"{API}/returns/chain/{ST['sret']['id']}", timeout=30).json()
    if d.get("complete") and ST["pret"]["number"] in (d.get("summary") or ""):
        ok(f"E9.6 — ringkasan sekali baca: “{d['summary'][:120]}”")
    else:
        bad(f"Ringkasan rantai tidak lengkap: complete={d.get('complete')} "
            f"summary={d.get('summary')}")
    rolls = d.get("rolls") or []
    if rolls and rolls[0].get("owner_entity_name") and rolls[0].get("po_number"):
        ok(f"E9.6 — layar juga menjawab barangnya di mana: {rolls[0]['qty']:g} "
           f"{rolls[0]['unit']} di {rolls[0]['owner_entity_name']} "
           f"(asal {rolls[0].get('supplier_name')} · {rolls[0]['po_number']})")
    else:
        bad(f"Keadaan fisik barang tidak terbaca di jejak retur: {rolls[:1]}")

    # ── E9.6b — rantai tidak boleh jadi JALAN BUNTU bagi pemegang retur beli ──
    # Peran gudang/pembelian TIDAK punya `sales_return.view`; kalau izin rantai
    # dipaksa ke satu domain, ia 403 tepat di dokumen miliknya sendiri.
    rw = wh_user.get(f"{API}/returns/chain/{ST['pret']['id']}", timeout=30)
    if rw.status_code == 200 and rw.json().get("steps"):
        ok(f"E9.6b — pemegang retur beli (peran gudang, tanpa izin retur jual) BISA "
           f"membuka rantai dokumennya sendiri ({len(rw.json()['steps'])} langkah)")
    else:
        bad(f"E9.6b — peran gudang ditolak di rantai dokumennya sendiri "
            f"(HTTP {rw.status_code} {rw.text[:160]})")

    # ── E9.6c — rantai melintasi badan usaha, tetapi RINCIAN tetangga diringkas ──
    rs = sales_a.get(f"{API}/returns/chain/{ST['sret']['id']}", timeout=30)
    if rs.status_code != 200:
        bad(f"E9.6c — sales Entitas A tidak bisa membuka rantai returnya "
            f"(HTTP {rs.status_code} {rs.text[:160]})")
        return
    body = rs.text
    ds = rs.json()
    pr_step = next((s for s in ds.get("steps", []) if s["stage"] == "purchase_return"), None)
    if pr_step and pr_step.get("redacted") and not pr_step.get("party") \
            and pr_step.get("amount") is None:
        ok(f"E9.6c/E5.3 — sales Entitas A melihat TAHAPNYA ({pr_step['number']}) tetapi "
           f"tidak melihat supplier & nilai milik badan usaha lain")
    else:
        bad(f"E9.6c — rincian retur beli badan usaha lain ikut terbaca sales A: {pr_step}")
    if "ent_kanda" not in body and ST["sup_b_name"] not in body:
        ok(f"E9.6c/E5.3 — nol id teknis `ent_*` & nol nama supplier tetangga di respons "
           f"rantai untuk sales Entitas A")
    else:
        bad("E9.6c — respons rantai untuk sales A masih memuat `ent_kanda` atau nama "
            f"supplier tetangga ({ST['sup_b_name']})")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════
async def run():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    head("LANGKAH 0 — Persiapan (bersihkan sisa POC lama · master produk POC)")
    pre = await wipe(db)
    await make_product(db)
    # Jejak audit ikut dihitung: POC menjalankan alur nyata (inspeksi roll, persetujuan
    # transfer, kontrak internal) yang semuanya menulis `audit_logs`. Kalau tidak
    # dibersihkan, setiap jalan-ulang menumpuk residu permanen — persis yang dijaga
    # gate INV-GATE-01.
    ST["audit_before"] = {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
    ST["notif_before"] = await db.notifications.count_documents({})
    ok(f"Lingkungan POC bersih & produk uji siap (sisa lama dihapus: {pre})")

    adm_all = sess(entity="all")
    adm_a = sess(entity=ENT_A)
    adm_b = sess(entity=ENT_B)
    mgr_a = sess("manager@kainnusantara.id", entity=ENT_A)
    sales_a = sess("sales@kainnusantara.id", entity=ENT_A)
    # Peran gudang: TIDAK punya izin retur jual, tetapi punya izin retur beli —
    # dipakai membuktikan rantai retur bukan jalan buntu baginya (E9.6b).
    wh_user = sess("warehouse@kainnusantara.id", entity=ENT_A)
    # Data demo TIDAK punya akun gudang yang ditugaskan di CV Kanda Suka (akun ber-home
    # Kanda hanya `sales3@`), dan pagar penugasan entitas memang menolak akun gudang KSC
    # menyentuh gudang Kanda — itu perilaku yang benar (FASE E-2). Jadi aksi gudang di
    # Entitas B dijalankan admin yang memang berwenang di kedua badan usaha.
    wh_b = adm_b

    try:
        if not resolve_demo_data(adm_a, adm_b):
            return
        if not step1_supplier_receipt(adm_b, wh_b):
            return
        if not step2_customer_order(adm_a):
            return
        if not step3_internal_purchase(adm_all, adm_a, wh_b):
            return
        await step3b_notification(db)
        if not step4_customer_return(adm_a, mgr_a):
            return
        if not step5_interco_return(adm_a, mgr_a, adm_all, wh_b):
            return
        await step5b_verify_roll_back(db)
        if not step6_supplier_return(adm_b):
            return
        step7_chain(adm_all, sales_a, wh_user)
    finally:
        head("CLEANUP — POC tidak boleh meninggalkan jejak")
        post = await wipe(db)
        left_roll = await db.inventory_rolls.count_documents({"product_id": PROD})
        left_so = await db.sales_orders.count_documents({"items.product_id": PROD})
        left_ict = await db.interco_transactions.count_documents({"items.product_id": PROD})
        left_icr = await db.interco_returns.count_documents({"items.product_id": PROD})
        left_pret = await db.purchase_returns.count_documents({"items.product_id": PROD})
        left_prod = await db.products.count_documents({"id": PROD})
        total = left_roll + left_so + left_ict + left_icr + left_pret + left_prod
        if total == 0:
            ok(f"Nol residu (dihapus: {post})")
        else:
            bad(f"Masih ada residu: roll={left_roll} so={left_so} ict={left_ict} "
                f"icr={left_icr} pret={left_pret} produk={left_prod}")
        # Jejak yang lahir SELAMA POC (termasuk baris `login` & sesi) dihapus dengan
        # pola yang sama seperti POC FASE E-0: bandingkan HIMPUNAN id, bukan jumlah.
        await db.sessions.delete_many({"token": {"$in": list(_TOKENS.values())}})
        audit_now = {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
        new_audit = audit_now - set(ST.get("audit_before") or set())
        if new_audit:
            await db.audit_logs.delete_many({"id": {"$in": list(new_audit)}})
        left_audit = await db.audit_logs.count_documents({"id": {"$in": list(new_audit)}})
        notif_after = await db.notifications.count_documents({})
        d_notif = notif_after - int(ST.get("notif_before") or 0)
        if left_audit == 0 and d_notif == 0:
            ok(f"Nol residu jejak (dihapus {len(new_audit)} baris audit & sesi POC · "
               f"notifikasi kembali seperti semula)")
        else:
            bad(f"POC meninggalkan jejak: audit tersisa {left_audit} · notifikasi +{d_notif}")
        for s in (adm_all, adm_a, adm_b, mgr_a, sales_a, wh_user):
            s.close()


def main() -> int:
    print("=" * 78)
    print("  POC FASE E-9 — RANTAI JUAL → BELI INTERNAL ANTAR-PT → RETUR BERANTAI")
    print("=" * 78)
    asyncio.run(run())
    print("\n" + "=" * 78)
    print(f"  HASIL: \033[92m{len(PASS)} PASS\033[0m · \033[91m{len(FAIL)} FAIL\033[0m "
          f"dari {len(PASS) + len(FAIL)} pemeriksaan")
    for f in FAIL:
        print(f"    \033[91m✗\033[0m {f}")
    print("=" * 78)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
