#!/usr/bin/env python3
"""
POC ISOLASI — FASE D: MAKLOON RANTAI PROSES (PS-03/PS-04/PS-08/PS-11)
=====================================================================
Membuktikan CORE Fase D lewat **HTTP API nyata** + assert **DB nyata** SEBELUM UI
(wizard) dibangun. Tidak ada mock, tidak ada angka karangan.

Keputusan pemilik yang diuji (sesi 2026-07-25):
  * **D-07** — semua basis tarif didukung & bisa custom (pick · kg · meter/yard +
    biaya screen/repeat · lumpsum · formula bebas) → tarif dihitung mesin, bukan diketik.
  * **D-05** — susut standar per **mitra/kontrak** (bukan default global).
  * **D-09** — selisih di luar toleransi → klaim dengan **semua tindakan** tersedia
    (potong bon / tagih ganti rugi / terima dengan catatan) + **approval manager/admin**.
  * **D-04** — output boleh kg atau meter/yard: konversi universal di titik input.

Cakupan (user story pemilik → bukti teknis):
  1. Kebijakan makloon configurable (toleransi, mode kontrak, peran penyetuju) + RBAC.
  2. Kontrak mitra `supplier_contracts` (nomor per entitas `KSC/SCT-#####`) basis bebas.
  3. Simulasi tarif auditable: pick (PPI), kg (catch-weight), meter + screen/repeat,
     formula custom, tagihan minimum.
  4. Estimasi output berbasis **GSM + lebar + susut** dengan angka antara; override
     yield hanya dengan alasan.
  5. Order makloon **3 langkah & 3 mitra**; rantai dipaksa (output N = input N+1);
     produk output wajib; override yield tanpa alasan ditolak.
  6. Issue dengan **satuan mitra** (ton → kg) + jejak konversi tersimpan.
  7. Receive: tarif dihitung dari kontrak memakai qty aktual + vendor bill + GL.
  8. Selisih vs estimasi → klaim OTOMATIS terbuka (di luar toleransi kontrak).
  9. Klaim: warehouse mengajukan, manager menyetujui; sales ditolak; potong bon
     mengurangi vendor bill + jurnal Dr Hutang/Cr Pendapatan Klaim.
 10. Receive langkah 2 dengan laporan mitra dalam **kg** (produk base meter) → konversi.
 11. Klaim `tagih_ganti` → jurnal Dr Piutang Klaim Mitra / Cr Pendapatan Klaim.
 12. Klaim `terima_catatan` → TIDAK ada jurnal (kerugian sudah terserap ke HPP).
 13. HPP berjenjang per langkah + HPP akhir.
 14. Genealogi lot Fase C tetap utuh (lot output punya induk lot bahan).
 15. Mode kontrak `block` menolak order tanpa kontrak; mode `warn` memberi peringatan.
 16. Registry enum (tariff_basis/claim_action/claim_status) in_use + daftar klaim &
     skor mitra.

Jalankan: cd /app && python backend/test_fase_d_makloon_poc.py
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

MARK = "FASEDPOC"
P_YARN, P_GREY, P_PFD, P_FIN, P_SISA = (
    "prod_fased_yarn", "prod_fased_grey", "prod_fased_pfd", "prod_fased_fin", "prod_fased_sisa")
PRODUCTS = [P_YARN, P_GREY, P_PFD, P_FIN, P_SISA]
MK_TENUN, MK_PRE, MK_CELUP, MK_NOCT = (
    "mak_fased_tenun", "mak_fased_pre", "mak_fased_celup", "mak_fased_nocontract")
MAKLOONS = [MK_TENUN, MK_PRE, MK_CELUP, MK_NOCT]

YARN_COST = 50000.0          # Rp/kg
YARN_QTY = 200.0             # kg tersedia untuk POC

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
    orders = await db.makloon_orders.find({"notes": {"$regex": MARK}}, {"_id": 0, "id": 1,
                                                                        "mko_number": 1}).to_list(200)
    oids = [o["id"] for o in orders]
    for oid in oids:
        await db.journal_entries.delete_many({"source_id": {"$regex": oid}})
    bills = await db.vendor_bills.find({"makloon_order_id": {"$in": oids}},
                                       {"_id": 0, "id": 1}).to_list(200)
    for b in bills:
        await db.journal_entries.delete_many({"source_id": b["id"]})
    await db.vendor_bills.delete_many({"makloon_order_id": {"$in": oids}})
    await db.makloon_orders.delete_many({"id": {"$in": oids}})
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
    await db.supplier_contracts.delete_many({"notes": {"$regex": MARK}})
    await db.makloons.delete_many({"id": {"$in": MAKLOONS}})
    await db.notifications.delete_many({"type": {"$in": ["makloon_claim", "makloon_claim_approval"]}})


async def make_masters(db):
    base = {"category": "Kain", "price": 0.0, "harga_pokok": 0.0, "entity_id": ENTITY,
            "status": "active", "grade": "A", "created_at": now_iso(), "updated_at": now_iso()}
    specs = [
        (P_YARN, "POCD-YARN", "POC Benang Katun", "kg", "yarn", "woven", 0, 0, YARN_COST, None),
        (P_GREY, "POCD-GREY", "POC Kain Grey", "yard", "grey", "woven", 120.0, 1.15, 0.0,
         {"ppi": 60, "epi": 70, "warp_count": "30s", "weft_count": "30s"}),
        (P_PFD, "POCD-PFD", "POC Kain PFD", "meter", "pfd", "woven", 130.0, 1.5, 0.0, None),
        (P_FIN, "POCD-FIN", "POC Kain Finished", "meter", "finished", "woven", 135.0, 1.5, 0.0, None),
        (P_SISA, "POCD-SISA", "POC Benang Sisa", "kg", "yarn", "woven", 0, 0, 0.0, None),
    ]
    for pid, sku, name, unit, stage, ftype, gsm, lebar, hpp, cons in specs:
        doc = {**base, "id": pid, "sku": sku, "name": name, "base_unit": unit, "stage": stage,
               "fabric_type": ftype, "gramasi": gsm, "lebar": lebar, "harga_pokok": hpp}
        if cons:
            doc["construction"] = cons
        await db.products.update_one({"id": pid}, {"$set": doc}, upsert=True)
    partners = [(MK_TENUN, "POC Mitra Tenun", ["tenun"]),
                (MK_PRE, "POC Mitra Pre-Treatment", ["pre_treatment"]),
                (MK_CELUP, "POC Mitra Celup", ["celup"]),
                (MK_NOCT, "POC Mitra Tanpa Kontrak", ["tenun"])]
    for mid, name, procs in partners:
        await db.makloons.update_one({"id": mid}, {"$set": {
            "id": mid, "code": f"MAK-{mid[-4:]}", "name": name, "process_types": procs,
            "entity_id": ENTITY, "status": "active", "default_tariff": 0.0,
            "created_at": now_iso(), "updated_at": now_iso()}}, upsert=True)
    from services.roll_service import create_inbound_roll
    await create_inbound_roll(P_YARN, WH, ENTITY, YARN_QTY, lot=f"{MARK}-YARN", unit="kg",
                              acquired_via="initial", ref_id=MARK, unit_cost=YARN_COST,
                              created_by="poc", lot_source="manual")


async def gl_lines(db, source_type, source_id_like):
    jes = await db.journal_entries.find({"source_type": source_type,
                                         "source_id": {"$regex": source_id_like}},
                                        {"_id": 0}).to_list(50)
    return jes


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
    head("TEST 1 — Kebijakan makloon configurable (D-05/D-09) + RBAC")
    r = s.get(f"{API}/supplier-contracts/policy", timeout=30)
    pol = r.json() if r.ok else {}
    if r.ok and {"variance_tolerance_pct", "contract_mode", "claim_approval_roles",
                 "auto_claim"} <= set(pol):
        ok(f"Kebijakan makloon tersedia (toleransi {pol['variance_tolerance_pct']}% · "
           f"mode kontrak {pol['contract_mode']} · penyetuju {pol['claim_approval_roles']})")
    else:
        bad(f"Kebijakan makloon tidak lengkap: {r.status_code} {r.text[:200]}")
    r = s.put(f"{API}/supplier-contracts/policy",
              json={"variance_tolerance_pct": 3, "contract_mode": "warn", "auto_claim": True,
                    "claim_approval_roles": ["manager", "admin"]}, timeout=30)
    ok("Admin dapat mengubah kebijakan makloon tanpa deploy") if r.ok else \
        bad(f"Admin gagal ubah kebijakan: {r.status_code} {r.text[:200]}")
    r = s_sales.put(f"{API}/supplier-contracts/policy", json={"variance_tolerance_pct": 50}, timeout=30)
    ok("Sales DITOLAK mengubah kebijakan makloon (403)") if r.status_code == 403 else \
        bad(f"Sales seharusnya 403, dapat {r.status_code}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 2 — Kontrak mitra: basis tarif BEBAS + susut & toleransi per kontrak (D-05/D-07)")

    def mk_contract(payload):
        return s.post(f"{API}/supplier-contracts", json={**payload, "notes": MARK,
                                                         "entity_id": ENTITY}, timeout=30)

    r = mk_contract({"contract_type": "makloon", "partner_id": MK_TENUN, "process_type": "tenun",
                     "product_id": P_GREY, "input_product_id": P_YARN, "title": "Tenun per pick",
                     "tariff_basis": "pick", "tariff_rate": 12, "shrinkage_pct": 5,
                     "tolerance_pct": 3, "lead_time_days": 10})
    ct_tenun = r.json() if r.ok else {}
    if r.ok and str(ct_tenun.get("contract_number", "")).startswith("KSC/SCT-"):
        ok(f"Kontrak tenun (basis pick) dibuat: {ct_tenun['contract_number']} · susut 5% · toleransi 3%")
    else:
        bad(f"Gagal membuat kontrak tenun: {r.status_code} {r.text[:250]}")

    r = mk_contract({"contract_type": "makloon", "partner_id": MK_PRE,
                     "process_type": "pre_treatment", "product_id": P_PFD,
                     "title": "Pre-treatment per kg", "tariff_basis": "kg", "tariff_rate": 8000,
                     "shrinkage_pct": 2, "tolerance_pct": 4})
    ct_pre = r.json() if r.ok else {}
    ok(f"Kontrak pre-treatment (basis kg) dibuat: {ct_pre.get('contract_number')}") if r.ok else \
        bad(f"Gagal membuat kontrak pre-treatment: {r.status_code} {r.text[:250]}")

    r = mk_contract({"contract_type": "makloon", "partner_id": MK_CELUP, "process_type": "celup",
                     "product_id": P_FIN, "title": "Celup per meter + screen/repeat",
                     "tariff_basis": "meter", "tariff_rate": 3500, "shrinkage_pct": 3,
                     "tolerance_pct": 2, "min_charge": 1000000,
                     "aux_fees": [{"code": "screen", "label": "Biaya screen", "basis": "per_color",
                                   "amount": 150000},
                                  {"code": "repeat", "label": "Biaya repeat", "basis": "per_repeat",
                                   "amount": 50000}]})
    ct_celup = r.json() if r.ok else {}
    ok(f"Kontrak celup (meter + screen/repeat + min charge) dibuat: {ct_celup.get('contract_number')}") \
        if r.ok else bad(f"Gagal membuat kontrak celup: {r.status_code} {r.text[:250]}")

    r = mk_contract({"contract_type": "makloon", "partner_id": MK_TENUN, "process_type": "tenun",
                     "tariff_basis": "hasta"})
    ok("Basis tarif tidak dikenal DITOLAK dengan pesan jelas") if r.status_code == 400 else \
        bad(f"Basis tarif ngawur seharusnya 400, dapat {r.status_code}")
    r = mk_contract({"contract_type": "makloon", "partner_id": MK_TENUN, "process_type": "sablon_x",
                     "tariff_basis": "meter", "tariff_rate": 1})
    ok("Jenis proses di luar registry DITOLAK (400)") if r.status_code == 400 else \
        bad(f"Proses ngawur seharusnya 400, dapat {r.status_code}")

    r = s.post(f"{API}/supplier-contracts/resolve",
               params={"partner_id": MK_TENUN, "process_type": "tenun", "product_id": P_GREY},
               timeout=30)
    body = r.json() if r.ok else {}
    ok("Resolver kontrak aktif menemukan kontrak paling spesifik") \
        if body.get("found") and body["contract"]["id"] == ct_tenun.get("id") else \
        bad(f"Resolver kontrak gagal: {r.status_code} {str(body)[:200]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 3 — Simulasi tarif AUDITABLE: pick · kg · meter+screen/repeat · formula custom")
    r = s.post(f"{API}/supplier-contracts/tariff-preview",
               json={"contract_id": ct_tenun.get("id"), "product_id": P_GREY, "qty": 100},
               timeout=30)
    tp = r.json() if r.ok else {}
    exp_pick = 100 * 0.9144 * 60 * 12          # yard→meter → ×PPI → ×tarif
    if r.ok and near(tp.get("amount"), exp_pick) and tp.get("basis") == "pick" and tp.get("explain"):
        ok(f"Tarif basis PICK benar: 100 yard → {tp['basis_qty']:.1f} pick·meter → "
           f"Rp {tp['amount']:,.0f} (≈ Rp {exp_pick:,.0f}) + rincian langkah hitung")
    else:
        bad(f"Tarif pick salah: {r.status_code} {str(tp)[:300]}")

    r = s.post(f"{API}/supplier-contracts/tariff-preview",
               json={"contract_id": ct_pre.get("id"), "product_id": P_GREY, "qty": 100,
                     "tariff_basis": "kg", "tariff_rate": 8000}, timeout=30)
    tp_kg = r.json() if r.ok else {}
    exp_kg = 100 * (120 * 1.15 / 1000) * 0.9144 * 8000
    if r.ok and near(tp_kg.get("amount"), exp_kg):
        ok(f"Tarif basis KG memakai catch-weight GSM×lebar: {tp_kg['basis_qty']:.2f} kg → "
           f"Rp {tp_kg['amount']:,.0f}")
    else:
        bad(f"Tarif kg salah: {r.status_code} {str(tp_kg)[:300]} (harusnya ≈ {exp_kg:,.0f})")

    r = s.post(f"{API}/supplier-contracts/tariff-preview",
               json={"contract_id": ct_celup.get("id"), "product_id": P_FIN, "qty": 500,
                     "colors": 3, "repeats": 2}, timeout=30)
    tp_c = r.json() if r.ok else {}
    exp_c = 500 * 3500 + 3 * 150000 + 2 * 50000
    if r.ok and near(tp_c.get("amount"), exp_c) and len(tp_c.get("aux_breakdown", [])) == 2:
        ok(f"Tarif meter + biaya screen(3 warna) & repeat(2) = Rp {tp_c['amount']:,.0f}")
    else:
        bad(f"Tarif celup salah: {r.status_code} {str(tp_c)[:300]} (harusnya {exp_c:,.0f})")

    r = s.post(f"{API}/supplier-contracts/tariff-preview",
               json={"product_id": P_FIN, "qty": 100, "tariff_basis": "custom",
                     "tariff_rate": 1000, "tariff_formula": "qty_base * rate * 1.1"}, timeout=30)
    tp_f = r.json() if r.ok else {}
    ok(f"Formula CUSTOM kontrak dipakai (Rp {tp_f.get('amount', 0):,.0f} = qty × tarif × 1,1)") \
        if r.ok and near(tp_f.get("amount"), 110000) else \
        bad(f"Formula custom gagal: {r.status_code} {str(tp_f)[:300]}")

    r = s.post(f"{API}/supplier-contracts/tariff-preview",
               json={"contract_id": ct_celup.get("id"), "product_id": P_FIN, "qty": 10}, timeout=30)
    tp_min = r.json() if r.ok else {}
    ok("Tagihan minimum kontrak berlaku (min_charge)") \
        if r.ok and tp_min.get("min_charge_applied") and near(tp_min.get("amount"), 1000000) else \
        bad(f"Min charge tidak diterapkan: {str(tp_min)[:250]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 4 — Estimasi output berbasis GSM + lebar + susut (PS-03) & override yield")
    r = s.post(f"{API}/makloon-orders/estimate",
               json={"input_product_id": P_YARN, "output_product_id": P_GREY,
                     "makloon_id": MK_TENUN, "process_type": "tenun", "input_qty": 200},
               timeout=30)
    est = r.json() if r.ok else {}
    kg_per_yard = (120 * 1.15 / 1000) * 0.9144
    exp_yard = 200 * 0.95 / kg_per_yard
    e = est.get("estimate", {})
    if r.ok and e.get("method") == "gsm" and near(e.get("expected_output_qty"), exp_yard) \
            and len(e.get("explain", [])) >= 3:
        ok(f"Estimasi GSM: 200 kg − susut 5% = {e['kg_effective']} kg → "
           f"{e['expected_output_qty']:.1f} yard ({len(e['explain'])} baris angka antara)")
    else:
        bad(f"Estimasi GSM salah: {r.status_code} {str(est)[:400]} (harusnya ≈{exp_yard:.1f})")
    ok(f"Susut diambil dari KONTRAK mitra: {est.get('shrinkage_source')}") \
        if "kontrak" in str(est.get("shrinkage_source", "")) else \
        bad(f"Susut tidak dari kontrak: {est.get('shrinkage_source')}")
    ok(f"Toleransi selisih diambil dari kontrak: {est.get('tolerance_pct')}%") \
        if near(est.get("tolerance_pct"), 3, 0.001) else \
        bad(f"Toleransi salah: {est.get('tolerance_pct')}")

    r = s.post(f"{API}/makloon-orders/estimate",
               json={"input_product_id": P_YARN, "output_product_id": P_GREY,
                     "makloon_id": MK_TENUN, "process_type": "tenun", "input_qty": 200,
                     "yield_factor": 3.8, "yield_override_reason": "Mesin lama, yield historis"},
               timeout=30)
    est2 = (r.json() or {}).get("estimate", {}) if r.ok else {}
    ok("Override yield (dengan alasan) dipakai + susut kontrak tetap berlaku (200×3,8−5% = 722)") \
        if est2.get("method") == "yield_override" and near(est2.get("expected_output_qty"), 722) else \
        bad(f"Override yield gagal: {str(est2)[:250]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 5 — Order makloon 3 LANGKAH & 3 MITRA (PS-04) dengan kontrak & estimasi")
    steps = [
        {"process_type": "tenun", "makloon_id": MK_TENUN, "input_product_id": P_YARN,
         "output_product_id": P_GREY, "byproduct_product_id": P_SISA, "byproduct_pct": 1},
        {"process_type": "pre_treatment", "target_use": "dye", "makloon_id": MK_PRE,
         "input_product_id": P_GREY, "output_product_id": P_PFD},
        {"process_type": "celup", "makloon_id": MK_CELUP, "input_product_id": P_PFD,
         "output_product_id": P_FIN, "colors": 3, "repeats": 2},
    ]
    payload = {"mode": "process_only", "material_product_id": P_YARN, "material_qty": YARN_QTY,
               "material_unit": "kg", "from_warehouse_id": WH, "target_warehouse_id": WH,
               "entity_id": ENTITY, "notes": f"{MARK} rantai 3 langkah", "steps": steps}
    r = s.post(f"{API}/makloon-orders", json=payload, timeout=60)
    order = r.json() if r.ok else {}
    if not r.ok:
        bad(f"Order 3 langkah GAGAL dibuat: {r.status_code} {r.text[:400]}")
        print("\nPOC dihentikan — core order tidak terbentuk.")
        await cleanup(db)
        return False
    mko_id = order["id"]
    partners = {st["makloon_id"] for st in order["steps"]}
    ok(f"Order {order['mko_number']} dibuat: {len(order['steps'])} langkah · {len(partners)} mitra") \
        if len(order["steps"]) == 3 and len(partners) == 3 else \
        bad(f"Order tidak sesuai: {len(order.get('steps', []))} langkah / {len(partners)} mitra")
    st1, st2, st3 = order["steps"]
    ok("Setiap langkah tertaut kontrak aktif (contract_id + nomor kontrak)") \
        if all(x.get("contract_id") and x.get("contract_number") for x in order["steps"]) else \
        bad(f"Ada langkah tanpa kontrak: {[x.get('contract_number') for x in order['steps']]}")
    ok(f"Susut & toleransi per langkah dari kontrak: {[ (x['shrinkage_pct'], x['tolerance_pct']) for x in order['steps'] ]}") \
        if (st1["shrinkage_pct"], st1["tolerance_pct"]) == (5, 3) and \
           (st2["shrinkage_pct"], st2["tolerance_pct"]) == (2, 4) and \
           (st3["shrinkage_pct"], st3["tolerance_pct"]) == (3, 2) else \
        bad(f"Susut/toleransi tidak mengikuti kontrak: "
            f"{[(x['shrinkage_pct'], x['tolerance_pct']) for x in order['steps']]}")
    ok(f"Estimasi langkah 1 berbasis GSM = {st1['expected_output_qty']:.1f} yard") \
        if near(st1["expected_output_qty"], exp_yard) else \
        bad(f"Estimasi langkah 1 salah: {st1['expected_output_qty']} (≈{exp_yard:.1f})")
    ok("Rantai tersambung: input langkah 2 = output langkah 1 (qty & produk)") \
        if st2["input_product_id"] == P_GREY and near(st2["input_qty"], st1["expected_output_qty"]) else \
        bad(f"Rantai langkah 2 salah: {st2['input_product_id']} {st2['input_qty']}")
    ok(f"Rencana tarif per langkah memakai basis kontrak: "
       f"{[x['tariff_basis'] for x in order['steps']]}") \
        if [x["tariff_basis"] for x in order["steps"]] == ["pick", "kg", "meter"] else \
        bad(f"Basis tarif langkah salah: {[x['tariff_basis'] for x in order['steps']]}")
    ok("HPP berjenjang disiapkan (costing.steps 3 baris)") \
        if len(order.get("costing", {}).get("steps", [])) == 3 else \
        bad(f"costing.steps tidak lengkap: {order.get('costing')}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 6 — Aturan wajib: rantai putus · output kosong · override yield tanpa alasan")
    bad_chain = [dict(steps[0]), {"process_type": "celup", "makloon_id": MK_CELUP,
                                  "input_product_id": P_YARN, "output_product_id": P_FIN}]
    r = s.post(f"{API}/makloon-orders", json={**payload, "notes": f"{MARK} putus",
                                              "steps": bad_chain}, timeout=30)
    ok("Rantai terputus (input langkah 2 ≠ output langkah 1) DITOLAK 400 + pesan jelas") \
        if r.status_code == 400 and "rantai" in r.text.lower() else \
        bad(f"Rantai putus seharusnya 400, dapat {r.status_code} {r.text[:200]}")
    r = s.post(f"{API}/makloon-orders",
               json={**payload, "notes": f"{MARK} no-output",
                     "steps": [{"process_type": "tenun", "makloon_id": MK_TENUN,
                                "input_product_id": P_YARN}]}, timeout=30)
    ok("Langkah tanpa produk OUTPUT DITOLAK 400 (KN_18 §5.2)") \
        if r.status_code == 400 and "output" in r.text.lower() else \
        bad(f"Output kosong seharusnya 400, dapat {r.status_code} {r.text[:200]}")
    r = s.post(f"{API}/makloon-orders",
               json={**payload, "notes": f"{MARK} yield",
                     "steps": [{**steps[0], "yield_factor": 3.8}]}, timeout=30)
    ok("Override yield TANPA alasan DITOLAK 400 (PS-03 auditable)") \
        if r.status_code == 400 and "alasan" in r.text.lower() else \
        bad(f"Yield tanpa alasan seharusnya 400, dapat {r.status_code} {r.text[:200]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 7 — Issue langkah 1 memakai SATUAN MITRA (ton) + jejak konversi (PS-08/D-07)")
    r = s_wh.post(f"{API}/makloon-orders/{mko_id}/issue",
                  json={"step_seq": 1, "from_warehouse_id": WH, "doc_uom": "ton", "doc_qty": 0.2},
                  timeout=60)
    o = r.json() if r.ok else {}
    stp1 = o.get("steps", [{}])[0] if o else {}
    trail = stp1.get("issue_uom_trail") or {}
    if r.ok and near(stp1.get("input_qty"), 200, 0.001) and near(trail.get("factor"), 1000, 0.001):
        ok(f"Warehouse issue 0,2 ton → 200 kg (faktor {trail.get('factor')} · sumber "
           f"{trail.get('source')}) & jejak tersimpan")
    else:
        bad(f"Issue dengan satuan mitra gagal: {r.status_code} {r.text[:300]}")
    ok(f"Nilai bahan ke WIP-at-vendor = Rp {stp1.get('material_value', 0):,.0f}") \
        if near(stp1.get("material_value"), YARN_QTY * YARN_COST) else \
        bad(f"material_value salah: {stp1.get('material_value')}")
    bal = await db.inventory_balances.find_one({"product_id": P_YARN, "warehouse_id": WH,
                                                "owner_entity_id": ENTITY}, {"_id": 0})
    ok(f"Stok benang pindah ke bucket subcon: {bal.get('subcon_qty')} kg (available "
       f"{bal.get('available_qty')})") if near(bal.get("subcon_qty"), 200, 0.001) else \
        bad(f"Bucket subcon salah: {bal}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 8 — Receive langkah 1: tarif DIHITUNG kontrak + selisih memicu klaim (PS-11)")
    actual1 = 1450.0
    r = s_wh.post(f"{API}/makloon-orders/{mko_id}/receive",
                  json={"step_seq": 1, "actual_output_qty": actual1, "actual_byproduct_qty": 2,
                        "output_warehouse_id": WH, "byproduct_lot": f"{MARK}-SISA",
                        "rolls": [{"lot": f"{MARK}-G1", "length": 700, "grade": "A",
                                   "dye_lot": f"{MARK}-DL1"},
                                  {"lot": f"{MARK}-G2", "length": 750, "grade": "A",
                                   "dye_lot": f"{MARK}-DL1"}]}, timeout=90)
    o = r.json() if r.ok else {}
    if not r.ok:
        bad(f"Receive langkah 1 GAGAL: {r.status_code} {r.text[:400]}")
        await cleanup(db)
        return False
    stp1 = o["steps"][0]
    exp_tariff1 = actual1 * 0.9144 * 60 * 12
    ok(f"Ongkos jasa dihitung mesin dari kontrak (bukan diketik): Rp {stp1['tariff']:,.0f} "
       f"= {stp1['tariff_actual']['basis_qty']:.0f} pick·meter × Rp 12") \
        if near(stp1["tariff"], exp_tariff1) and stp1["tariff_actual"]["source"] == "contract" else \
        bad(f"Tarif aktual salah: {stp1.get('tariff')} (≈{exp_tariff1:,.0f}) "
            f"src={stp1.get('tariff_actual', {}).get('source')}")
    bill = await db.vendor_bills.find_one({"makloon_order_id": mko_id, "step_seq": 1}, {"_id": 0})
    ok(f"Tagihan jasa mitra terbit {bill['bill_number']} Rp {bill['grand_total']:,.0f}") \
        if bill and near(bill["grand_total"], stp1["tariff"]) else \
        bad(f"Vendor bill jasa tidak sesuai: {bill}")
    var1 = stp1.get("variance", {})
    ok(f"Selisih terhitung: {var1.get('variance_pct')}% (aktual {actual1} vs estimasi "
       f"{stp1['expected_output_qty']:.1f} {stp1['output_unit']}) — melewati toleransi 3%") \
        if var1.get("level") == "shortfall" and var1.get("claim_required") else \
        bad(f"Selisih tidak terdeteksi: {var1}")
    claim1 = stp1.get("claim", {})
    ok(f"Klaim OTOMATIS terbuka (status={claim1.get('status')}, usulan Rp "
       f"{claim1.get('amount_suggested', 0):,.0f})") if claim1.get("status") == "open" else \
        bad(f"Klaim tidak terbuka otomatis: {claim1}")

    # Genealogi lot (Fase C tetap utuh) — roll output makloon lahir dengan lot_id + induk
    roll = await db.inventory_rolls.find_one({"product_id": P_GREY, "acquired.ref_id": mko_id},
                                             {"_id": 0})
    lot = await db.inventory_lots.find_one({"id": (roll or {}).get("lot_id")}, {"_id": 0}) if roll else None
    ok(f"Lot output {lot['lot_number']} punya induk lot bahan (genealogi Fase C utuh)") \
        if lot and lot.get("parent_lot_ids") else \
        bad(f"Genealogi lot output hilang: roll={bool(roll)} lot={lot and lot.get('lot_number')}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 9 — Klaim: RBAC pengajuan & persetujuan + POTONG BON (D-09)")
    amount1 = round(float(claim1.get("amount_suggested") or 0), 2)
    r = s_sales.post(f"{API}/makloon-orders/{mko_id}/claim",
                     json={"step_seq": 1, "action": "potong_bon", "amount": amount1,
                           "reason": "coba"}, timeout=30)
    ok("Sales DITOLAK mengajukan klaim (403)") if r.status_code == 403 else \
        bad(f"Sales seharusnya 403, dapat {r.status_code}")
    r = s_wh.post(f"{API}/makloon-orders/{mko_id}/claim",
                  json={"step_seq": 1, "action": "potong_bon", "amount": amount1,
                        "reason": "Hasil kurang 55 yard di luar toleransi kontrak"}, timeout=30)
    o = r.json() if r.ok else {}
    ok(f"Warehouse mengajukan potong bon Rp {amount1:,.0f} → menunggu persetujuan") \
        if r.ok and o["steps"][0]["claim"]["status"] == "pending_approval" else \
        bad(f"Pengajuan klaim gagal: {r.status_code} {r.text[:250]}")
    r = s_wh.post(f"{API}/makloon-orders/{mko_id}/claim/approve",
                  json={"step_seq": 1, "note": "saya setujui sendiri"}, timeout=30)
    ok("Warehouse DITOLAK menyetujui klaim (403 — hanya manager/admin)") \
        if r.status_code == 403 else bad(f"Warehouse approve seharusnya 403, dapat {r.status_code}")
    bill_before = await db.vendor_bills.find_one({"id": bill["id"]}, {"_id": 0})
    r = s_mgr.post(f"{API}/makloon-orders/{mko_id}/claim/approve",
                   json={"step_seq": 1, "note": "Disetujui — potong tagihan mitra"}, timeout=60)
    o = r.json() if r.ok else {}
    cl = o.get("steps", [{}])[0].get("claim", {}) if o else {}
    ok(f"Manager menyetujui klaim → status {cl.get('status')} · efek "
       f"{cl.get('effect', {}).get('accounting_effect')}") \
        if r.ok and cl.get("status") == "approved" else \
        bad(f"Approve klaim gagal: {r.status_code} {r.text[:300]}")
    bill_after = await db.vendor_bills.find_one({"id": bill["id"]}, {"_id": 0})
    ok(f"Tagihan mitra dipotong: Rp {bill_before['grand_total']:,.0f} → "
       f"Rp {bill_after['grand_total']:,.0f} (claim_deduction {bill_after.get('claim_deduction')})") \
        if near(bill_after["grand_total"], bill_before["grand_total"] - amount1) else \
        bad(f"Vendor bill tidak dipotong: {bill_before['grand_total']} → {bill_after['grand_total']}")
    jes = await gl_lines(db, "makloon_claim", mko_id)
    je1 = next((j for j in jes if j["source_id"].endswith(":1")), None)
    codes = {l["account_code"]: (l["debit"], l["credit"]) for l in (je1 or {}).get("lines", [])}
    ok(f"Jurnal potong bon benar: Dr 2-1100 Rp {codes.get('2-1100', (0, 0))[0]:,.0f} / "
       f"Cr 4-9200 Rp {codes.get('4-9200', (0, 0))[1]:,.0f}") \
        if je1 and near(codes.get("2-1100", (0, 0))[0], amount1) and \
        near(codes.get("4-9200", (0, 0))[1], amount1) else \
        bad(f"Jurnal potong bon salah: {codes}")
    r = s_mgr.post(f"{API}/makloon-orders/{mko_id}/claim/approve",
                   json={"step_seq": 1, "note": "dobel"}, timeout=30)
    ok("Persetujuan ulang klaim yang sama DITOLAK (400 — idempoten)") \
        if r.status_code == 400 else bad(f"Approve dobel seharusnya 400, dapat {r.status_code}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 10 — Langkah 2: mitra melapor dalam KG (produk base meter) → konversi universal (D-04)")
    r = s_wh.post(f"{API}/makloon-orders/{mko_id}/issue",
                  json={"step_seq": 2, "from_warehouse_id": WH}, timeout=60)
    ok("Issue langkah 2 (grey → mitra pre-treatment) berhasil") if r.ok else \
        bad(f"Issue langkah 2 gagal: {r.status_code} {r.text[:250]}")
    o = r.json() if r.ok else {}
    st2 = o["steps"][1] if o else {}
    kg_per_m_pfd = 130 * 1.5 / 1000
    doc_kg = 170.0
    base_m = round(doc_kg * round(1 / kg_per_m_pfd, 8), 2)
    half = round(base_m / 2, 2)
    rolls2 = [{"lot": f"{MARK}-P1", "length": half, "grade": "A"},
              {"lot": f"{MARK}-P2", "length": round(base_m - half, 2), "grade": "A"}]
    r = s_wh.post(f"{API}/makloon-orders/{mko_id}/receive",
                  json={"step_seq": 2, "output_uom": "kg", "output_doc_qty": doc_kg,
                        "output_warehouse_id": WH, "rolls": rolls2}, timeout=90)
    o = r.json() if r.ok else {}
    if not r.ok:
        bad(f"Receive langkah 2 gagal: {r.status_code} {r.text[:400]}")
    else:
        st2 = o["steps"][1]
        tr = st2.get("receive_uom_trail") or {}
        ok(f"Laporan mitra {doc_kg} kg dikonversi ke {st2['actual_output_qty']} meter "
           f"(faktor {tr.get('factor')} · sumber {tr.get('source')})") \
            if near(st2["actual_output_qty"], base_m, 0.001) and tr.get("doc_uom") == "kg" else \
            bad(f"Konversi receive salah: {st2.get('actual_output_qty')} vs {base_m} · {tr}")
        exp_t2 = doc_kg * 8000
        ok(f"Tarif basis KG dihitung dari qty aktual: Rp {st2['tariff']:,.0f}") \
            if near(st2["tariff"], exp_t2, 0.03) else \
            bad(f"Tarif langkah 2 salah: {st2.get('tariff')} (≈{exp_t2:,.0f})")
        ok(f"Selisih langkah 2 terdeteksi ({st2['variance']['variance_pct']}% vs toleransi "
           f"{st2['variance']['tolerance_pct']}%) → klaim {st2['claim']['status']}") \
            if st2["claim"]["status"] in ("open", "none") else \
            bad(f"Status klaim langkah 2 tak terduga: {st2['claim']}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 11 — Klaim TAGIH GANTI RUGI (piutang klaim mitra) — D-09")
    if (o.get("steps", [{}, {}])[1].get("claim", {}).get("status")) == "open":
        amount2 = round(float(o["steps"][1]["claim"].get("amount_suggested") or 0), 2) or 100000.0
    else:
        amount2 = 100000.0
    r = s_mgr.post(f"{API}/makloon-orders/{mko_id}/claim",
                   json={"step_seq": 2, "action": "tagih_ganti", "amount": amount2,
                         "reason": "Kekurangan hasil melebihi toleransi kontrak — tagih mitra"},
                   timeout=30)
    ok("Manager mengajukan tagih ganti rugi") if r.ok else \
        bad(f"Pengajuan tagih ganti gagal: {r.status_code} {r.text[:250]}")
    r = s.post(f"{API}/makloon-orders/{mko_id}/claim/approve",
               json={"step_seq": 2, "note": "Setuju tagih ganti rugi"}, timeout=60)
    o2 = r.json() if r.ok else {}
    jes = await gl_lines(db, "makloon_claim", mko_id)
    je2 = next((j for j in jes if j["source_id"].endswith(":2")), None)
    codes2 = {l["account_code"]: (l["debit"], l["credit"]) for l in (je2 or {}).get("lines", [])}
    ok(f"Jurnal ganti rugi: Dr 1-1260 Piutang Klaim Rp {codes2.get('1-1260', (0, 0))[0]:,.0f} / "
       f"Cr 4-9200 Rp {codes2.get('4-9200', (0, 0))[1]:,.0f}") \
        if je2 and near(codes2.get("1-1260", (0, 0))[0], amount2) else \
        bad(f"Jurnal ganti rugi salah: {codes2}")
    bill2 = await db.vendor_bills.find_one({"makloon_order_id": mko_id, "step_seq": 2}, {"_id": 0})
    ok("Tagihan jasa langkah 2 TIDAK dipotong (ganti rugi ≠ potong bon)") \
        if bill2 and not bill2.get("claim_deduction") else \
        bad(f"Tagihan langkah 2 seharusnya utuh: {bill2 and bill2.get('claim_deduction')}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 12 — Langkah 3: tarif meter + screen/repeat, klaim TERIMA DENGAN CATATAN")
    r = s_wh.post(f"{API}/makloon-orders/{mko_id}/issue",
                  json={"step_seq": 3, "from_warehouse_id": WH}, timeout=60)
    ok("Issue langkah 3 (PFD → mitra celup)") if r.ok else \
        bad(f"Issue langkah 3 gagal: {r.status_code} {r.text[:250]}")
    o = r.json() if r.ok else {}
    st3 = o["steps"][2] if o else {}
    exp3 = float(st3.get("expected_output_qty") or 0)
    actual3 = round(exp3 * 0.90, 2)          # sengaja 10% di bawah estimasi (toleransi 2%)
    r = s_wh.post(f"{API}/makloon-orders/{mko_id}/receive",
                  json={"step_seq": 3, "actual_output_qty": actual3, "colors": 3, "repeats": 2,
                        "output_warehouse_id": WH,
                        "rolls": [{"lot": f"{MARK}-F1", "length": actual3, "grade": "A"}]},
                  timeout=90)
    o = r.json() if r.ok else {}
    if not r.ok:
        bad(f"Receive langkah 3 gagal: {r.status_code} {r.text[:400]}")
    else:
        st3 = o["steps"][2]
        exp_t3 = actual3 * 3500 + 3 * 150000 + 2 * 50000
        ok(f"Tarif langkah 3 (meter + screen 3 warna + repeat 2) = Rp {st3['tariff']:,.0f}") \
            if near(st3["tariff"], exp_t3) else \
            bad(f"Tarif langkah 3 salah: {st3.get('tariff')} (≈{exp_t3:,.0f})")
        ok(f"Klaim langkah 3 terbuka otomatis ({st3['variance']['variance_pct']}% < −2%)") \
            if st3["claim"]["status"] == "open" else bad(f"Klaim langkah 3: {st3['claim']}")
    je_before = len(await gl_lines(db, "makloon_claim", mko_id))
    r = s_mgr.post(f"{API}/makloon-orders/{mko_id}/claim",
                   json={"step_seq": 3, "action": "terima_catatan", "amount": 0,
                         "reason": "Susut wajar musim hujan — diterima, standar kontrak ditinjau"},
                   timeout=30)
    ok("Pengajuan 'terima dengan catatan' diterima") if r.ok else \
        bad(f"Pengajuan terima_catatan gagal: {r.status_code} {r.text[:250]}")
    r = s.post(f"{API}/makloon-orders/{mko_id}/claim/approve",
               json={"step_seq": 3, "note": "Diterima apa adanya"}, timeout=60)
    o3 = r.json() if r.ok else {}
    cl3 = o3.get("steps", [{}, {}, {}])[2].get("claim", {}) if o3 else {}
    je_after = len(await gl_lines(db, "makloon_claim", mko_id))
    ok("Terima dengan catatan: TIDAK ada jurnal baru (kerugian sudah terserap ke HPP) "
       f"+ jejak alasan tersimpan") \
        if cl3.get("status") == "approved" and je_after == je_before and \
        cl3.get("effect", {}).get("accounting_effect") == "none" else \
        bad(f"terima_catatan salah: status={cl3.get('status')} je {je_before}→{je_after} "
            f"efek={cl3.get('effect')}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 13 — HPP BERJENJANG per langkah + HPP akhir (PS-04)")
    r = s.get(f"{API}/makloon-orders/{mko_id}", timeout=30)
    det = r.json() if r.ok else {}
    cost = det.get("costing", {})
    cs_steps = cost.get("steps", [])
    hpp_txt = ", ".join(f"{c['seq']}:{c['hpp_per_unit']:,.0f}/{c['output_unit']}" for c in cs_steps)
    ok(f"Rincian HPP per langkah tersedia: {hpp_txt}") \
        if len(cs_steps) == 3 and all(c["hpp_per_unit"] > 0 for c in cs_steps) else \
        bad(f"HPP berjenjang tidak lengkap: {cs_steps}")
    chain_ok = all(
        near(cs_steps[i]["output_value"],
             cs_steps[i]["material_value"] + cs_steps[i]["service_value"] +
             cs_steps[i]["aux_cost"] - cs_steps[i]["byproduct_value"], 0.001)
        for i in range(len(cs_steps)))
    ok("Nilai output tiap langkah = bahan + jasa + aux − sisa (rekonsiliasi WIP)") if chain_ok else \
        bad(f"Rekonsiliasi nilai langkah gagal: {cs_steps}")
    ok(f"HPP akhir Rp {cost.get('hpp_output', 0):,.0f} · HPP/unit Rp "
       f"{cost.get('hpp_per_unit', 0):,.0f}/{det.get('final_output_unit')}") \
        if cost.get("hpp_output", 0) > 0 and cost.get("hpp_per_unit", 0) > 0 else \
        bad(f"HPP akhir kosong: {cost}")
    ok(f"Status order = {det.get('status')} (semua langkah diterima)") \
        if det.get("status") == "completed" else bad(f"Status order: {det.get('status')}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 14 — Mode kontrak: `block` menolak order tanpa kontrak · `warn` memberi peringatan")
    s.put(f"{API}/supplier-contracts/policy", json={"contract_mode": "block"}, timeout=30)
    single = [{"process_type": "tenun", "makloon_id": MK_NOCT, "input_product_id": P_YARN,
               "output_product_id": P_GREY}]
    r = s.post(f"{API}/makloon-orders", json={**payload, "material_qty": 5,
                                              "notes": f"{MARK} block", "steps": single}, timeout=30)
    ok("Mode `block`: order tanpa kontrak aktif DITOLAK 400 dengan pesan yang bisa ditindak") \
        if r.status_code == 400 and "kontrak" in r.text.lower() else \
        bad(f"Mode block seharusnya 400, dapat {r.status_code} {r.text[:200]}")
    s.put(f"{API}/supplier-contracts/policy", json={"contract_mode": "warn"}, timeout=30)
    r = s.post(f"{API}/makloon-orders", json={**payload, "material_qty": 5,
                                              "notes": f"{MARK} warn", "steps": single}, timeout=30)
    ow = r.json() if r.ok else {}
    ok(f"Mode `warn`: order tetap dibuat + peringatan tercatat ({len(ow.get('warnings', []))} pesan)") \
        if r.ok and ow.get("warnings") else \
        bad(f"Mode warn gagal: {r.status_code} {r.text[:250]}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 15 — Registry enum · daftar klaim · skor mitra · proteksi hapus kontrak")
    r = s.get(f"{API}/enums", timeout=30)
    enums = r.json() if r.ok else {}
    raw = enums.get("enums", {}) if isinstance(enums, dict) else {}
    reg = raw if isinstance(raw, dict) else {e["name"]: e for e in raw}
    tb = reg.get("tariff_basis", {})
    tb_vals = {v["value"] for v in tb.get("values", [])}
    ok("Enum tariff_basis in_use & memuat lumpsum + custom (D-07 configurable)") \
        if tb.get("in_use") and {"lumpsum", "custom", "pick", "kg"} <= tb_vals else \
        bad(f"Enum tariff_basis belum lengkap: {tb_vals} in_use={tb.get('in_use')}")
    ok("Enum claim_action & claim_status aktif (in_use) di registry") \
        if reg.get("claim_action", {}).get("in_use") and reg.get("claim_status", {}).get("in_use") else \
        bad(f"Enum klaim belum in_use: {list(reg.keys())[:12]}")
    r = s_mgr.get(f"{API}/makloon-orders/claims", params={"status": "approved"}, timeout=30)
    claims = r.json() if r.ok else []
    ours = [c for c in claims if c.get("mko_id") == mko_id]
    ok(f"Daftar klaim lintas order untuk layar persetujuan: {len(ours)} klaim disetujui pada order ini") \
        if len(ours) == 3 else bad(f"Daftar klaim tidak sesuai: {len(ours)} dari {len(claims)}")
    r = s.get(f"{API}/makloon-orders/claims/stats", timeout=30)
    stt = r.json() if r.ok else {}
    ok(f"Statistik klaim: approved {stt.get('approved')} · nilai Rp {stt.get('approved_amount', 0):,.0f}") \
        if stt.get("approved", 0) >= 3 else bad(f"Statistik klaim salah: {stt}")
    r = s_mgr.get(f"{API}/makloon-partners/scorecard", timeout=30)
    score = r.json() if r.ok else []
    mine = [x for x in score if x["makloon_id"] in (MK_TENUN, MK_PRE, MK_CELUP)]
    ok(f"Skor mitra terbentuk dari selisih & klaim ({len(mine)} mitra POC terdaftar)") \
        if len(mine) == 3 and all(x["avg_variance_pct"] is not None for x in mine) else \
        bad(f"Skor mitra tidak lengkap: {mine}")
    r = s.delete(f"{API}/supplier-contracts/{ct_tenun.get('id')}", timeout=30)
    ok("Kontrak yang sudah dipakai order TIDAK bisa dihapus (409) — jejak audit aman") \
        if r.status_code == 409 else bad(f"Hapus kontrak terpakai seharusnya 409, dapat {r.status_code}")

    # ══════════════════════════════════════════════════════════════════════
    head("TEST 16 — Kebersihan data: artifact POC dibersihkan (invarian global tetap hijau)")
    await cleanup(db)
    left_rolls = await db.inventory_rolls.count_documents({"product_id": {"$in": PRODUCTS}})
    left_orders = await db.makloon_orders.count_documents({"notes": {"$regex": MARK}})
    left_je = await db.journal_entries.count_documents({"source_id": {"$regex": mko_id}})
    ok("Semua artifact POC dihapus (roll/order/jurnal/kontrak/mitra)") \
        if left_rolls == 0 and left_orders == 0 and left_je == 0 else \
        bad(f"Sisa artifact: rolls={left_rolls} orders={left_orders} je={left_je}")

    print("\n" + "=" * 64)
    print(f"  \033[92mPASS {len(PASS)}\033[0m  |  \033[91mFAIL {len(FAIL)}\033[0m")
    if FAIL:
        print("\n  Gagal:")
        for f in FAIL:
            print(f"   - {f}")
    else:
        print("  \033[92m\033[1mPOC FASE D HIJAU — makloon rantai proses terbukti.\033[0m")
    print("=" * 64)
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
