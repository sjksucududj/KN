#!/usr/bin/env python3
"""
POC ISOLASI — FASE C: LOT KELAS SATU (`inventory_lots`) · D-10 / D-26 / D-27
============================================================================
Membuktikan CORE Fase C lewat **HTTP API nyata** + assert **DB nyata** SEBELUM UI
dibangun. Tidak ada mock, tidak ada data palsu.

Cakupan (user story pemilik → bukti teknis):
  1. Penomoran lot **per entitas** `KSC/LOT-YYMM-####` (D-26) + deret terpisah per PT.
  2. Penerimaan (GR) otomatis membentuk lot **per dye lot** (D-10, granularitas batch),
     `supplier_lot` tersimpan, roll mendapat `lot_id`, agregat = Σ roll.
  3. Penegakan **configurable** (D-27): mode `warn` (default) hanya memperingatkan;
     mode `block` menolak GR tanpa supplier_lot/dye_lot → lalu dikembalikan ke `warn`.
  4. Idempoten: menerima batch dengan nomor lot yang sama TIDAK membuat lot dobel.
  5. **Split** lot: sebagian roll → lot anak, genealogi dua arah, agregat benar,
     dan split seluruh roll DITOLAK dengan pesan jelas.
  6. **Merge** lot: ≥2 lot → 1 lot baru dengan 2 induk; lintas produk DITOLAK.
  7. **Rework**: lot anak + proses + validasi transisi stage (stage ilegal ditolak).
  8. **Anti-siklus** genealogi (tidak boleh membuat lingkaran induk↔anak).
  9. **Silsilah** (`/genealogy`): nodes + edges + dokumen sumber + rantai stage.
 10. **Recall** (`/recall`): lot → roll → SO → pelanggan (dengan kontak) + total.
 11. **Label/QR** (`/label`): payload ZPL memakai `label_printer_service` existing.
 12. Registry enum (`/api/enums`) memuat `lot_source` & `lot_status` sebagai in_use.
 13. RBAC: sales boleh melihat, TIDAK boleh mengubah pengaturan penegakan.
 14. Migrasi idempoten (`lot_migration.run_all` dry-run → changed=0) & tidak ada roll
     tanpa lot setelah backfill.
 15. Daftar/filter/paginasi lot + endpoint roll tanpa lot (penambalan data).

Jalankan: cd /app && python backend/test_fase_c_lot_poc.py
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
ENTITY2 = "ent_kanda"
WAREHOUSE = "wh_jakarta"

MARK = "FASECPOC"
PROD_A = "prod_fasec_a"
PROD_B = "prod_fasec_b"

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


def login(email="admin@kainnusantara.id", password="demo12345"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


async def cleanup(db):
    lots = await db.inventory_lots.find({"$or": [{"product_id": {"$in": [PROD_A, PROD_B]}},
                                                {"note": {"$regex": MARK}}]},
                                        {"_id": 0, "id": 1}).to_list(500)
    lot_ids = [l["id"] for l in lots]
    await db.inventory_lots.delete_many({"id": {"$in": lot_ids}})
    await db.inventory_lots.delete_many({"product_id": {"$in": [PROD_A, PROD_B]}})
    await db.inventory_rolls.delete_many({"product_id": {"$in": [PROD_A, PROD_B]}})
    await db.inventory_movements.delete_many({"product_id": {"$in": [PROD_A, PROD_B]}})
    await db.inventory_balances.delete_many({"product_id": {"$in": [PROD_A, PROD_B]}})
    await db.wms_tasks.delete_many({"mark": MARK})
    await db.products.delete_many({"id": {"$in": [PROD_A, PROD_B]}})
    await db.sales_orders.delete_many({"mark": MARK})
    await db.customers.delete_many({"mark": MARK})
    # lepas jejak genealogi ke lot yang sudah dihapus (jaga INV-LOT-03 tetap hijau)
    if lot_ids:
        await db.inventory_lots.update_many(
            {}, {"$pull": {"parent_lot_ids": {"$in": lot_ids}}})
        await db.inventory_lots.update_many(
            {}, {"$pull": {"child_lot_ids": {"$in": lot_ids}}})


async def make_products(db):
    for pid, sku, name in ((PROD_A, "POC-LOT-A", "Kain POC Lot A"),
                           (PROD_B, "POC-LOT-B", "Kain POC Lot B")):
        await db.products.update_one({"id": pid}, {"$set": {
            "id": pid, "sku": sku, "name": name, "category": "Kain", "base_unit": "meter",
            "price": 60000.0, "harga_pokok": 0.0, "entity_id": ENTITY, "status": "active",
            "stage": "finished", "fabric_type": "woven", "gramasi": 180.0, "lebar": 1.15,
            "grade": "A", "created_at": now_iso(),
        }}, upsert=True)


async def insert_inbound_task(db, qty, product_id, task_lot="", dye_lot="", unit="meter"):
    tid = f"wms_{MARK.lower()}_{int(datetime.now().timestamp() * 1000000) % 100000000}"
    await db.wms_tasks.insert_one({
        "id": tid, "mark": MARK, "flow_type": "inbound", "source_type": "manual_poc",
        "po_id": "", "po_number": f"POC-{MARK}",
        "product_id": product_id, "product_name": "Kain POC Lot", "sku": "POC-LOT",
        "expected_qty": qty, "received_qty": qty, "quantity": qty,
        "unit": unit, "warehouse_id": WAREHOUSE, "warehouse_name": "Gudang Jakarta Utara",
        "warehouse_city": "Jakarta", "supplier_name": "Supplier POC",
        "entity_id": ENTITY,
        "bin_id": "", "batch": "", "lot": task_lot, "roll_id": "",
        "dye_lot": dye_lot, "grade": "A",
        "status": "qc_check",
        "stages": ["waiting_goods", "receiving", "qc_check", "put_away", "completed"],
        "scan_log": [], "escalation": None,
        "created_by": "poc", "created_at": now_iso(), "updated_at": now_iso(),
    })
    return tid


async def main():  # noqa: C901 — satu skrip POC lengkap (sesuai protokol repo)
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {login()}"})
    ok("Login admin@kainnusantara.id")

    await cleanup(db)
    await make_products(db)

    # pastikan mode default warn (tidak memblokir) sebelum uji
    s.put(f"{API}/lots/settings", json={"enforcement_mode": "warn",
                                       "require_supplier_lot": True,
                                       "require_dye_lot": True}, timeout=30)

    # ═══ 1. PENOMORAN PER ENTITAS (D-26) ═══════════════════════════════════
    head("TEST 1 — Penomoran lot per entitas KSC/LOT-YYMM-#### (D-26)")
    import re
    ym = datetime.now(timezone.utc).strftime("%y%m")
    r = s.post(f"{API}/lots", json={"product_id": PROD_A, "owner_entity_id": ENTITY,
                                    "warehouse_id": WAREHOUSE, "supplier_lot": "SUP-001",
                                    "dye_lot": "DL-POC-1", "note": f"{MARK} manual"}, timeout=30)
    if r.status_code != 200:
        bad(f"POST /lots gagal: {r.status_code} {r.text[:200]}")
        return summary()
    lot1 = r.json()
    if re.match(rf"^KSC/LOT-{ym}-\d{{4}}$", lot1["lot_number"]):
        ok(f"Format nomor lot per entitas benar: {lot1['lot_number']}")
    else:
        bad(f"Format nomor lot salah: {lot1['lot_number']} (harap KSC/LOT-{ym}-####)")
    r2 = s.post(f"{API}/lots", json={"product_id": PROD_A, "owner_entity_id": ENTITY,
                                     "warehouse_id": WAREHOUSE, "supplier_lot": "SUP-002",
                                     "dye_lot": "DL-POC-2", "note": f"{MARK} manual2"}, timeout=30)
    lot2 = r2.json()
    n1 = int(lot1["lot_number"].split("-")[-1])
    n2 = int(lot2["lot_number"].split("-")[-1])
    if n2 == n1 + 1:
        ok(f"Sequence bulanan berurutan & atomik: {lot1['lot_number']} → {lot2['lot_number']}")
    else:
        bad(f"Sequence tidak berurutan: {n1} → {n2}")
    r3 = s.post(f"{API}/lots", json={"product_id": PROD_A, "owner_entity_id": ENTITY2,
                                     "warehouse_id": WAREHOUSE, "supplier_lot": "SUP-K1",
                                     "dye_lot": "DL-K", "note": f"{MARK} kanda"}, timeout=30)
    if r3.status_code == 200 and r3.json()["lot_number"].startswith("KANDA/LOT-"):
        ok(f"Entitas kedua punya deret sendiri: {r3.json()['lot_number']}")
    else:
        bad(f"Deret entitas kedua salah: {r3.status_code} {r3.text[:150]}")
    if lot1.get("lot_status") == "released" and lot1.get("stage") == "finished":
        ok("Lot menyimpan snapshot domain (stage) + status mutu awal")
    else:
        bad(f"Snapshot domain/status lot salah: {lot1.get('stage')}/{lot1.get('lot_status')}")

    # ═══ 2. GR MEMBENTUK LOT PER DYE LOT (D-10) ════════════════════════════
    head("TEST 2 — Penerimaan (GR) membentuk lot per dye lot + roll ber-lot_id")
    tid = await insert_inbound_task(db, 100, PROD_A)
    r = s.post(f"{API}/inbound/tasks/{tid}/complete", json={
        "supplier_lot": "SUP-GR-777", "shade_ref": "SHADE-A",
        "rolls": [{"length": 60, "dye_lot": "DL-RED", "grade": "A", "defects": []},
                  {"length": 40, "dye_lot": "DL-BLUE", "grade": "A", "defects": []}]}, timeout=60)
    if r.status_code != 200:
        bad(f"GR complete gagal: {r.status_code} {r.text[:250]}")
    else:
        body = r.json()
        gr_lots = body.get("lots") or []
        if len(gr_lots) == 2:
            ok(f"1 batch × 2 dye lot → 2 lot: {[l['lot_number'] for l in gr_lots]}")
        else:
            bad(f"Jumlah lot GR tidak 2: {gr_lots}")
        rolls = await db.inventory_rolls.find({"product_id": PROD_A},
                                             {"_id": 0, "lot_id": 1, "dye_lot": 1,
                                              "lot": 1, "supplier_lot": 1,
                                              "length_remaining": 1}).to_list(50)
        if rolls and all(x.get("lot_id") for x in rolls):
            ok(f"Semua {len(rolls)} roll GR punya lot_id (tidak ada roll liar)")
        else:
            bad(f"Ada roll GR tanpa lot_id: {rolls}")
        if all(x.get("supplier_lot") == "SUP-GR-777" for x in rolls):
            ok("supplier_lot tersimpan di roll (jejak asal barang)")
        else:
            bad(f"supplier_lot tidak tersimpan: {[x.get('supplier_lot') for x in rolls]}")
        red = next((l for l in gr_lots if l["dye_lot"] == "DL-RED"), None)
        if red:
            det = s.get(f"{API}/lots/{red['id']}", timeout=30).json()
            db_rolls = await db.inventory_rolls.find({"lot_id": red["id"]},
                                                    {"_id": 0, "length_remaining": 1}).to_list(50)
            expect = round(sum(float(x["length_remaining"]) for x in db_rolls), 3)
            if abs(float(det.get("qty_remaining") or 0) - expect) < 0.01 and \
                    det.get("roll_count") == len(db_rolls):
                ok(f"Agregat lot == Σ roll ({det['roll_count']} roll · {det['qty_remaining']})")
            else:
                bad(f"Agregat lot salah: {det.get('roll_count')}/{det.get('qty_remaining')} "
                    f"vs {len(db_rolls)}/{expect}")
            if det.get("shade_ref") == "SHADE-A":
                ok("shade_ref tersimpan pada lot (keseragaman warna)")
            else:
                bad(f"shade_ref tidak tersimpan: {det.get('shade_ref')}")
            if det.get("lot_status") == "karantina":
                ok("Lot penerimaan masuk status karantina (menunggu QC)")
            else:
                info(f"Status lot penerimaan: {det.get('lot_status')} (qc_on_receipt mungkin off)")

    # ═══ 3. PENEGAKAN CONFIGURABLE (D-27) ══════════════════════════════════
    head("TEST 3 — Penegakan lot configurable: warn (default) vs block (D-27)")
    tid2 = await insert_inbound_task(db, 25, PROD_A)
    r = s.post(f"{API}/inbound/tasks/{tid2}/complete", json={}, timeout=60)
    if r.status_code == 200 and r.json().get("lot_warnings"):
        ok(f"Mode warn: GR TETAP jalan + peringatan jelas ({len(r.json()['lot_warnings'])} pesan)")
        info(f"   → {r.json()['lot_warnings'][0][:90]}")
    elif r.status_code == 200:
        bad("Mode warn: GR jalan tapi TIDAK ada peringatan kelengkapan lot")
    else:
        bad(f"Mode warn seharusnya tidak memblokir GR: {r.status_code} {r.text[:200]}")
    s.put(f"{API}/lots/settings", json={"enforcement_mode": "block"}, timeout=30)
    tid3 = await insert_inbound_task(db, 15, PROD_A)
    r = s.post(f"{API}/inbound/tasks/{tid3}/complete", json={}, timeout=60)
    if r.status_code == 400 and "lot" in r.text.lower():
        ok("Mode block: GR tanpa supplier_lot/dye_lot DITOLAK dengan pesan jelas")
    else:
        bad(f"Mode block tidak menolak: {r.status_code} {r.text[:200]}")
    r = s.post(f"{API}/inbound/tasks/{tid3}/complete", json={
        "supplier_lot": "SUP-BLOCK-1",
        "rolls": [{"length": 15, "dye_lot": "DL-GREEN", "grade": "A"}]}, timeout=60)
    if r.status_code == 200:
        ok("Mode block: GR dengan data lot LENGKAP diterima")
    else:
        bad(f"GR lengkap ditolak di mode block: {r.status_code} {r.text[:200]}")
    back = s.put(f"{API}/lots/settings", json={"enforcement_mode": "warn"}, timeout=30)
    if back.status_code == 200 and back.json()["enforcement_mode"] == "warn":
        ok("Pengaturan dapat dikembalikan ke warn tanpa deploy")
    else:
        bad(f"Gagal kembali ke warn: {back.status_code} {back.text[:150]}")

    # ═══ 4. IDEMPOTENSI RESOLUSI LOT ═══════════════════════════════════════
    head("TEST 4 — Idempoten: batch dengan nomor lot sama tidak membuat lot dobel")
    first = await db.inventory_lots.find_one({"product_id": PROD_A, "dye_lot": "DL-RED"},
                                            {"_id": 0, "id": 1, "lot_number": 1})
    before = await db.inventory_lots.count_documents({"product_id": PROD_A})
    tid4 = await insert_inbound_task(db, 30, PROD_A)
    r = s.post(f"{API}/inbound/tasks/{tid4}/complete", json={
        "supplier_lot": "SUP-GR-777", "lot_number": first["lot_number"],
        "rolls": [{"length": 30, "dye_lot": "DL-RED", "grade": "A"}]}, timeout=60)
    after = await db.inventory_lots.count_documents({"product_id": PROD_A})
    if r.status_code == 200 and after == before:
        ok(f"Penerimaan lanjutan menempel ke lot yang sama ({first['lot_number']}) — tanpa lot dobel")
    else:
        bad(f"Lot dobel terbentuk: sebelum {before} sesudah {after} ({r.status_code})")

    # ═══ 5. SPLIT ══════════════════════════════════════════════════════════
    head("TEST 5 — Split lot: sebagian roll → lot anak (genealogi dua arah)")
    lot_red = await db.inventory_lots.find_one({"product_id": PROD_A, "dye_lot": "DL-RED"},
                                              {"_id": 0})
    red_rolls = await db.inventory_rolls.find({"lot_id": lot_red["id"]},
                                              {"_id": 0, "id": 1}).to_list(50)
    r = s.post(f"{API}/lots/{lot_red['id']}/split",
               json={"roll_ids": [x["id"] for x in red_rolls], "reason": f"{MARK} split all"},
               timeout=30)
    if r.status_code == 400 and "minimal 1 roll" in r.text.lower():
        ok("Split SELURUH roll ditolak dengan pesan jelas (arahkan ke rework/merge)")
    else:
        bad(f"Split seluruh roll tidak ditolak: {r.status_code} {r.text[:180]}")
    r = s.post(f"{API}/lots/{lot_red['id']}/split",
               json={"roll_ids": [red_rolls[0]["id"]], "reason": f"{MARK} split 1 roll",
                     "dye_lot": "DL-RED-B"}, timeout=30)
    if r.status_code != 200:
        bad(f"Split gagal: {r.status_code} {r.text[:200]}")
        child_id = ""
    else:
        out = r.json()
        child_id = out["child"]["id"]
        parent, child = out["parent"], out["child"]
        if child["parent_lot_ids"] == [parent["id"]] and child["id"] in parent["child_lot_ids"]:
            ok(f"Genealogi dua arah terbentuk: {parent['lot_number']} → {child['lot_number']}")
        else:
            bad(f"Genealogi tidak dua arah: {child.get('parent_lot_ids')} / {parent.get('child_lot_ids')}")
        moved = await db.inventory_rolls.find_one({"id": red_rolls[0]["id"]},
                                                 {"_id": 0, "lot_id": 1, "dye_lot": 1})
        if moved["lot_id"] == child_id and moved["dye_lot"] == "DL-RED-B":
            ok("Roll pindah ke lot anak + dye_lot anak ikut diperbarui")
        else:
            bad(f"Roll tidak pindah dengan benar: {moved}")
        p_db = await db.inventory_lots.find_one({"id": parent["id"]},
                                               {"_id": 0, "roll_count": 1, "qty_remaining": 1})
        p_rolls = await db.inventory_rolls.find({"lot_id": parent["id"]},
                                               {"_id": 0, "length_remaining": 1}).to_list(50)
        if p_db["roll_count"] == len(p_rolls) and abs(
                p_db["qty_remaining"] - round(sum(float(x["length_remaining"]) for x in p_rolls), 3)) < 0.01:
            ok("Agregat lot induk & anak di-recompute (bukan $inc)")
        else:
            bad(f"Agregat induk tidak konsisten: {p_db} vs {len(p_rolls)} roll")

    # ═══ 6. MERGE ══════════════════════════════════════════════════════════
    head("TEST 6 — Merge lot: 2 lot → 1 lot baru dengan 2 induk")
    blue = await db.inventory_lots.find_one({"product_id": PROD_A, "dye_lot": "DL-BLUE"}, {"_id": 0})
    green = await db.inventory_lots.find_one({"product_id": PROD_A, "dye_lot": "DL-GREEN"}, {"_id": 0})
    r = s.post(f"{API}/lots/merge", json={"lot_ids": [blue["id"], green["id"]],
                                          "reason": f"{MARK} merge shade"}, timeout=30)
    if r.status_code != 200:
        bad(f"Merge gagal: {r.status_code} {r.text[:200]}")
        merged_id = ""
    else:
        out = r.json()
        merged = out["lot"]
        merged_id = merged["id"]
        if set(merged["parent_lot_ids"]) == {blue["id"], green["id"]}:
            ok(f"Lot hasil merge punya 2 induk: {merged['lot_number']}")
        else:
            bad(f"Induk merge salah: {merged['parent_lot_ids']}")
        moved = await db.inventory_rolls.count_documents({"lot_id": merged_id})
        left = await db.inventory_rolls.count_documents({"lot_id": {"$in": [blue["id"], green["id"]]}})
        if moved == out["moved_rolls"] and left == 0:
            ok(f"Seluruh {moved} roll pindah ke lot gabungan; lot sumber kosong")
        else:
            bad(f"Perpindahan roll merge salah: pindah {moved}, tersisa {left}")
        if merged.get("lot_status") == "hold_shade":
            ok("Merge lintas dye lot otomatis berstatus hold_shade (peringatan warna)")
        else:
            info(f"Status lot merge: {merged.get('lot_status')}")
    lot_b = s.post(f"{API}/lots", json={"product_id": PROD_B, "owner_entity_id": ENTITY,
                                        "warehouse_id": WAREHOUSE, "supplier_lot": "SUP-B",
                                        "dye_lot": "DL-B", "note": f"{MARK} produk lain"},
                   timeout=30).json()
    r = s.post(f"{API}/lots/merge", json={"lot_ids": [lot_red["id"], lot_b["id"]]}, timeout=30)
    if r.status_code == 400 and "produk" in r.text.lower():
        ok("Merge lintas produk DITOLAK (lot tidak boleh campur produk)")
    else:
        bad(f"Merge lintas produk tidak ditolak: {r.status_code} {r.text[:180]}")

    # ═══ 7. REWORK ═════════════════════════════════════════════════════════
    head("TEST 7 — Rework: lot anak berproses + validasi transisi stage")
    r = s.post(f"{API}/lots/{lot_red['id']}/rework",
               json={"process_type": "tenun", "to_stage": "grey",
                     "reason": f"{MARK} transisi ilegal"}, timeout=30)
    if r.status_code == 400:
        ok("Transisi stage ilegal (finished --tenun--> grey) DITOLAK oleh state machine Fase A")
    else:
        bad(f"Transisi ilegal tidak ditolak: {r.status_code} {r.text[:180]}")
    r = s.post(f"{API}/lots/{lot_red['id']}/rework",
               json={"process_type": "finishing", "partner_name": "Mitra POC",
                     "reason": f"{MARK} rework finishing"}, timeout=30)
    if r.status_code != 200:
        bad(f"Rework gagal: {r.status_code} {r.text[:200]}")
        rework_child = ""
    else:
        out = r.json()
        rework_child = out["child"]["id"]
        if out["child"]["source"] == "rework" and \
                out["child"]["process"]["process_type"] == "finishing":
            ok(f"Lot rework terbentuk dengan jejak proses: {out['child']['lot_number']}")
        else:
            bad(f"Metadata rework salah: {out['child'].get('source')} {out['child'].get('process')}")
        if out["parent"]["lot_status"] == "rework":
            ok("Lot induk otomatis berstatus rework (jejak status tersimpan)")
        else:
            bad(f"Status induk tidak rework: {out['parent'].get('lot_status')}")

    # ═══ 8. ANTI-SIKLUS ════════════════════════════════════════════════════
    head("TEST 8 — Genealogi menolak siklus (induk↔anak berputar)")
    if rework_child:
        r = s.post(f"{API}/lots/{rework_child}/rework",
                   json={"process_type": "finishing", "reason": f"{MARK} cucu"}, timeout=30)
        grand = r.json().get("child", {}).get("id", "") if r.status_code == 200 else ""
        if grand:
            # coba jadikan cucu sebagai INDUK dari lot_red (harus ditolak)
            from services import lot_service as _ls  # noqa: E402
            try:
                await _ls.link_parent(lot_red["id"], grand)
                bad("Siklus genealogi TIDAK ditolak (bahaya: silsilah bisa berputar)")
            except _ls.LotError as exc:
                ok(f"Siklus ditolak: {str(exc)[:80]}")
        else:
            bad(f"Gagal membuat lot cucu untuk uji siklus: {r.status_code} {r.text[:150]}")

    # ═══ 9. SILSILAH ═══════════════════════════════════════════════════════
    head("TEST 9 — Silsilah lot (/genealogy): nodes + edges + dokumen sumber")
    r = s.get(f"{API}/lots/{lot_red['id']}/genealogy", timeout=30)
    if r.status_code != 200:
        bad(f"Genealogy gagal: {r.status_code} {r.text[:200]}")
    else:
        g = r.json()
        if len(g["nodes"]) >= 3 and g["descendant_count"] >= 2:
            ok(f"Silsilah memuat {len(g['nodes'])} node ({g['descendant_count']} turunan)")
        else:
            bad(f"Silsilah kurang lengkap: {len(g['nodes'])} node, turunan {g['descendant_count']}")
        if g["edges"] and all({"from", "to"} <= set(e) for e in g["edges"]):
            ok(f"Edges silsilah siap render ({len(g['edges'])} relasi)")
        else:
            bad(f"Edges tidak valid: {g.get('edges')}")
        docs = g.get("documents") or []
        if any(d.get("ref_type") == "wms_task" for d in docs):
            ok("Dokumen sumber (penerimaan/GR) tampil pada silsilah")
        else:
            bad(f"Dokumen sumber tidak terbaca: {docs[:2]}")
        if g.get("chain"):
            ok(f"Rantai stage terbaca: {' → '.join(c['stage'] for c in g['chain'])}")
        else:
            bad("Rantai stage kosong")

    # ═══ 10. RECALL ════════════════════════════════════════════════════════
    head("TEST 10 — Recall: lot → roll → SO → pelanggan")
    await db.customers.update_one({"id": f"cust_{MARK.lower()}"}, {"$set": {
        "id": f"cust_{MARK.lower()}", "mark": MARK, "name": "Toko POC Recall",
        "phone": "0811222333", "contact_person": "Bu Ani", "city": "Jakarta",
        "entity_id": ENTITY, "status": "active", "created_at": now_iso()}}, upsert=True)
    so_id = f"so_{MARK.lower()}"
    await db.sales_orders.update_one({"id": so_id}, {"$set": {
        "id": so_id, "mark": MARK, "number": f"SO-{MARK}", "customer_id": f"cust_{MARK.lower()}",
        "customer_name": "Toko POC Recall", "customer_city": "Jakarta", "status": "reserved",
        "entity_id": ENTITY, "grand_total": 1000000.0, "items": [], "allocations": [],
        "created_at": now_iso()}}, upsert=True)
    target_roll = await db.inventory_rolls.find_one({"lot_id": lot_red["id"]}, {"_id": 0, "id": 1})
    if not target_roll:
        # setelah split/rework, roll berada di lot TURUNAN → recall wajib menjangkaunya
        scope = s.get(f"{API}/lots/{lot_red['id']}/recall", timeout=30).json()
        target_roll = (scope.get("rolls") or [{}])[0] if scope.get("rolls") else None
    if not target_roll or not target_roll.get("id"):
        bad("Tidak ada roll dalam cakupan lot untuk uji recall (data POC tidak lengkap)")
    else:
        await db.inventory_rolls.update_one({"id": target_roll["id"]}, {"$set": {
            "status": "reserved", "reserved_ref": {"type": "sales_order", "id": so_id}}})
        r = s.get(f"{API}/lots/{lot_red['id']}/recall", timeout=30)
        if r.status_code != 200:
            bad(f"Recall gagal: {r.status_code} {r.text[:200]}")
        else:
            rec = r.json()
            if any(o["id"] == so_id for o in rec["orders"]):
                ok(f"Recall menemukan SO terdampak ({rec['totals']['orders']} order) "
                   "termasuk lewat lot TURUNAN (split/rework)")
            else:
                bad(f"SO terdampak tidak ditemukan: {rec.get('orders')}")
            cust = rec["customers"][0] if rec["customers"] else {}
            if cust.get("customer_name") == "Toko POC Recall" and cust.get("phone") == "0811222333":
                ok("Recall menyertakan pelanggan + kontak untuk tindakan cepat")
            else:
                bad(f"Data pelanggan recall tidak lengkap: {cust}")
            if rec["totals"]["rolls"] >= 1 and rec["totals"]["lots"] >= 1:
                ok(f"Total dampak: {rec['totals']['rolls']} roll · {rec['totals']['lots']} lot "
                   f"· sisa {rec['totals']['qty_remaining']}")
            else:
                bad(f"Total recall janggal: {rec['totals']}")

    # ═══ 11. LABEL / QR ════════════════════════════════════════════════════
    head("TEST 11 — Label lot (ZPL/QR) memakai label_printer_service existing")
    r = s.post(f"{API}/lots/{lot_red['id']}/label", json={"format": "zpl", "qty": 2}, timeout=30)
    if r.status_code == 200:
        lab = r.json()
        if lab.get("format") == "zpl" and lot_red["lot_number"] in lab.get("content", "") and \
                lab["lot"]["qr_value"] == lot_red["lot_number"]:
            ok("Label ZPL berisi nomor lot + nilai QR = nomor lot")
        else:
            bad(f"Isi label tidak sesuai: {str(lab)[:160]}")
        if lab["meta"]["qty"] == 2:
            ok("Jumlah cetak label mengikuti permintaan (qty=2)")
        else:
            bad(f"qty label salah: {lab['meta'].get('qty')}")
    else:
        bad(f"Label gagal: {r.status_code} {r.text[:200]}")

    # ═══ 12. REGISTRY ENUM ═════════════════════════════════════════════════
    head("TEST 12 — Registry enum: lot_source & lot_status in_use (tanpa hardcode FE)")
    en = s.get(f"{API}/enums", timeout=30).json()
    src = (en.get("enums") or {}).get("lot_source") or {}
    stt = (en.get("enums") or {}).get("lot_status") or {}
    if src.get("in_use") and len(src.get("values") or []) >= 8:
        ok(f"Enum lot_source aktif ({len(src['values'])} nilai)")
    else:
        bad(f"Enum lot_source belum aktif/kurang: {src.get('in_use')} {len(src.get('values') or [])}")
    if stt.get("in_use") and any(v["value"] == "hold_shade" for v in stt.get("values", [])):
        ok("Enum lot_status aktif (termasuk hold_shade)")
    else:
        bad(f"Enum lot_status belum aktif: {stt.get('in_use')}")
    if (en.get("decisions") or {}).get("D-26") and (en.get("decisions") or {}).get("D-27"):
        ok("Keputusan D-26 & D-27 tercatat di registry (dokumen = kode)")
    else:
        bad("Keputusan D-26/D-27 belum ada di registry")

    # ═══ 13. RBAC ══════════════════════════════════════════════════════════
    head("TEST 13 — RBAC: sales boleh lihat, tidak boleh ubah penegakan")
    s2 = requests.Session()
    s2.headers.update({"Authorization": f"Bearer {login('sales@kainnusantara.id')}"})
    rv = s2.get(f"{API}/lots", timeout=30)
    rw = s2.put(f"{API}/lots/settings", json={"enforcement_mode": "block"}, timeout=30)
    if rv.status_code == 200:
        ok("Sales dapat MELIHAT daftar lot (traceability transparan)")
    else:
        bad(f"Sales tidak bisa melihat lot: {rv.status_code}")
    if rw.status_code == 403:
        ok("Sales DITOLAK saat mengubah pengaturan penegakan lot (403)")
    else:
        bad(f"RBAC bocor: sales dapat mengubah pengaturan ({rw.status_code})")

    # ═══ 14. MIGRASI IDEMPOTEN ═════════════════════════════════════════════
    head("TEST 14 — Migrasi/backfill idempoten & tidak ada roll tanpa lot")
    from services import lot_migration  # noqa: E402
    res = await lot_migration.run_all(actor="POC", dry_run=True)
    if res["changed"] == 0:
        ok("Migrasi dry-run melaporkan changed=0 (idempoten)")
    else:
        bad(f"Migrasi masih menemukan pekerjaan: {res}")
    orphan = await db.inventory_rolls.count_documents(
        {"$or": [{"lot_id": {"$exists": False}}, {"lot_id": None}, {"lot_id": ""}]})
    if orphan == 0:
        ok("0 roll tanpa lot di seluruh database (backfill penuh · keputusan #3)")
    else:
        bad(f"{orphan} roll masih tanpa lot")
    legacy = await db.inventory_lots.find_one({"source": "migration",
                                              "legacy_lot_codes": {"$ne": []}},
                                             {"_id": 0, "legacy_lot_codes": 1})
    if legacy:
        ok(f"String lot lama tersimpan sebagai jejak: {legacy['legacy_lot_codes'][:2]}")
    else:
        bad("Jejak string lot lama tidak ditemukan")

    # ═══ 15. DAFTAR · FILTER · PAGINASI · ROLL TANPA LOT ═══════════════════
    head("TEST 15 — Daftar/filter/paginasi lot + endpoint roll tanpa lot")
    r = s.get(f"{API}/lots", params={"q": "DL-RED", "product_id": PROD_A}, timeout=30)
    if r.status_code == 200 and isinstance(r.json(), list):
        ok(f"Filter pencarian lot bekerja ({len(r.json())} hasil untuk 'DL-RED')")
    else:
        bad(f"Filter lot gagal: {r.status_code} {str(r.text)[:150]}")
    r = s.get(f"{API}/lots", params={"page": 1, "page_size": 5}, timeout=30)
    body = r.json() if r.status_code == 200 else {}
    if isinstance(body, dict) and body.get("page_size") == 5 and "total" in body:
        ok(f"Paginasi lot mengikuti kontrak repo (total {body['total']})")
    else:
        bad(f"Envelope paginasi salah: {str(body)[:150]}")
    r = s.get(f"{API}/lots/stats", timeout=30)
    st = r.json() if r.status_code == 200 else {}
    if st.get("total", 0) > 0 and st.get("rolls_without_lot") == 0:
        ok(f"Statistik lot: {st['total']} lot · 0 roll tanpa lot · "
           f"{st.get('incomplete_capture')} lot data belum lengkap")
    else:
        bad(f"Statistik lot janggal: {str(st)[:180]}")
    r = s.get(f"{API}/lots/unassigned-rolls", timeout=30)
    if r.status_code == 200 and r.json().get("total") == 0:
        ok("Endpoint roll tanpa lot mengembalikan 0 (data bersih)")
    else:
        bad(f"Endpoint unassigned-rolls janggal: {r.status_code} {str(r.text)[:150]}")
    rr = await db.inventory_rolls.find_one({"lot_id": {"$nin": [None, ""]}}, {"_id": 0, "id": 1})
    r = s.get(f"{API}/rolls/{rr['id']}/lot", timeout=30)
    if r.status_code == 200 and r.json().get("lot", {}).get("lot_number"):
        ok(f"Detail roll → lot ({r.json()['lot']['lot_number']}) tersedia untuk layar gudang")
    else:
        bad(f"Endpoint roll→lot gagal: {r.status_code} {str(r.text)[:150]}")

    # ═══ BERSIHKAN ARTIFACT ════════════════════════════════════════════════
    # POC memakai produk/SO/roll sintetis. Bila ditinggal, invarian global
    # (PPN order, balance == Σ roll, drift GL) akan MERAH karena data uji.
    # Gunakan `--keep` bila ingin memeriksa hasilnya di UI.
    if "--keep" in sys.argv:
        info("Artifact POC DIPERTAHANKAN (--keep) — jalankan ulang tanpa --keep untuk bersih")
    else:
        await cleanup(db)
        left = await db.inventory_lots.count_documents({"product_id": {"$in": [PROD_A, PROD_B]}})
        if left == 0:
            ok("Artifact POC dibersihkan (invarian global tetap bersih)")
        else:
            bad(f"Artifact POC masih tersisa: {left} lot")

    return summary()


def summary():
    print("\n" + "=" * 64)
    print(f"  \033[92mPASS {len(PASS)}\033[0m  |  \033[91mFAIL {len(FAIL)}\033[0m")
    if FAIL:
        print("\n  Gagal:")
        for f in FAIL:
            print(f"   - {f}")
        return 1
    print("  \033[92m\033[1mPOC FASE C HIJAU — core lot kelas satu terbukti.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
