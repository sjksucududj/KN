#!/usr/bin/env python3
"""POC FASE T — TAHAPAN PROSES (termasuk **SCREEN**/kasa): master yang bisa bertambah,
tahap yang tidak mengubah kain, dan angka SPK lama yang TIDAK bergeser.

Permintaan pemilik (sesi 2026-08-19): *"screen merupakan salah satu proses di makloon
(tahapan), maka tahapan makloon juga dibuatkan masternya, lalu setiap tahapan itu
memiliki pekerjaan di makloon siapa."* Ditambah keputusan sesi ini:
**1c** kain boleh bergerak ATAU tidak (dipilih per langkah) · **2b** re-screen kain jadi
juga sah · **3b** mitra wajib hanya DIPERINGATKAN (gate yang memerah) · **4a** nilai
proses di layar WAJIB dari master.

SEMBILAN HAL YANG DIBUKTIKAN DI SINI (RENCANA_EKSEKUSI_MD_ERP.md §T.E)
=====================================================================
  T1  Tahap BARU ("Sanforize") ditambah lewat API master → langsung muncul di
      `/api/enums` (enum `process_stage`) DAN di pemilih langkah SPK
      (`/api/process-stages`) tanpa satu baris kode diubah & tanpa restart.
  T2a Tahap `screen` sebagai **JASA MURNI**: `Issue` DITOLAK dengan kalimat menuntun
      (kain tidak boleh bergerak), `Catat Jasa` melahirkan tagihan mitra + jurnal,
      **kain tidak berubah** (qty keluar = qty masuk), tidak ada roll baru, dan
      `estimate.explain[]` menyebut ALASANNYA.
  T2b Tahap `screen` dengan **kain dikirim**: `Issue` boleh, `Terima Hasil` menuntut
      roll, tetapi estimasinya tetap `no_transform` (qty keluar = qty masuk) dan
      biaya jasanya MASUK HPP kain.
  T3  Menonaktifkan / mengganti kode tahap yang MASIH dipakai SPK → DITOLAK 409
      dengan menyebut jumlah pemakainya (INV-DOMAIN-06 aturan A).
  T4  REGRESI: SPK gaya lama (hanya `process_type`, tanpa `stage_code`) menghasilkan
      `expected_output_qty`, `explain[]`, dan biaya **identik** dengan SPK seed yang
      lahir sebelum FASE T.
  T5  Override per badan usaha: tahap khusus CV Kanda Suka TIDAK muncul di PT Kain
      Suka Cita (pagar entitas berlaku juga untuk kosakata).
  T6  BUKTI-MERAH: tahap `needs_vendor=true` tanpa satu pun mitra terdaftar membuat
      gate `INV-DOMAIN-06` MEMERAH (exit 1) — lalu hijau lagi setelah dibereskan.
  T7  SPK berisi jasa murni SAJA (tanpa langkah kain sesudahnya) → selesai dengan
      jurnal Dr 5-1200 / Cr 1-1350, sehingga WIP kembali NOL (uang tidak menguap).
  T8  Mitra WAJIB (`needs_vendor`) tanpa mitra dipilih → SPK tetap bisa disimpan
      (keputusan 3b) tetapi membawa `warnings[]` yang menyebutnya.
  T9  NOL RESIDU: seluruh data uji dibersihkan **dan stok dipulihkan EKSAK**
      (roll · lot · mutasi · saldo) — POC aman dijalankan berulang.

Jalankan:  cd /app && python backend/test_core_tahapan_poc.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poc_stock_guard import restore_stock, snapshot_stock  # noqa: E402

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PW = "demo12345"
ADMIN = "admin@kainnusantara.id"
ENT_A = "ent_ksc"
ENT_B = "ent_kanda"
WH = "wh_surabaya"

PASS = 0
FAIL = 0


def ok(cond: bool, label: str, extra: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f"\n         → {extra}" if extra else ""))
    return bool(cond)


def login(email: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": PW}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:300]}"
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}",
                      "Content-Type": "application/json"})
    return s


def h(entity: str) -> dict:
    return {"X-Entity-Id": entity}


def _db():
    from pymongo import MongoClient
    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli[os.environ.get("DB_NAME", "test_database")]


def enum_values(sess, entity: str, name: str) -> list:
    r = sess.get(f"{BASE}/api/enums", headers=h(entity), timeout=30)
    assert r.status_code == 200, f"/api/enums: {r.status_code} {r.text[:200]}"
    return [v.get("value") for v in
            (r.json().get("enums", {}).get(name, {}).get("values") or [])]


def stage_options(sess, entity: str, line: str = "") -> list:
    url = f"{BASE}/api/process-stages" + (f"?line={line}" if line else "")
    r = sess.get(url, headers=h(entity), timeout=30)
    assert r.status_code == 200, f"/api/process-stages: {r.status_code} {r.text[:200]}"
    return r.json()


def gate_exit() -> int:
    """Jalankan gate INV-DOMAIN-06 sungguhan (bukan menirunya) → exit code."""
    p = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "guardrails",
                                                     "verify_master_stages.py")],
                       capture_output=True, text=True, cwd=ROOT, timeout=180)
    return p.returncode


def make_order(sess, steps: list, qty: float, material: str, note: str) -> requests.Response:
    return sess.post(f"{BASE}/api/makloon-orders", headers=h(ENT_A), timeout=60, json={
        "mode": "process_only", "material_product_id": material,
        "material_qty": qty, "material_unit": "yard",
        "from_warehouse_id": WH, "target_warehouse_id": WH,
        "notes": note, "entity_id": ENT_A, "steps": steps,
    })


def main() -> int:  # noqa: C901 — POC linear supaya mudah dibaca sebagai bukti
    tag = uuid.uuid4().hex[:6]
    db = _db()
    # T2b menjalankan alur kain SUNGGUHAN (Issue → Terima Hasil): itu MELAHIRKAN roll,
    # lot & mutasi baru yang tidak bisa dibalik per-dokumen (roll hasil terima punya
    # nomor & lot sendiri, saldo ikut bergeser). Terukur 2026-08-19: satu kali POC ini
    # meninggalkan `inventory_movements` +3 · `inventory_rolls` +2 · `inventory_lots` +1,
    # yang lalu membuat `verify_data_integrity` memerah kuning (drift persediaan vs GL
    # 1-1300 Δ750.000) dan menjatuhkan gate INV-GATE-01 + POC G-6b. Satu-satunya
    # pemulihan yang EKSAK adalah snapshot→restore koleksi stok (pola POC-RESIDU-01).
    stock_snap = snapshot_stock()
    stock_before = {c: db[c].count_documents({}) for c in
                    ("inventory_rolls", "inventory_lots", "inventory_movements",
                     "inventory_balances")}
    audit_before = {d["id"] for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
    made_orders: list = []
    made_stages: list = []
    made_makloons: list = []
    admin = login(ADMIN)

    print("=" * 84)
    print("  POC FASE T — TAHAPAN PROSES (master bertambah · screen tak ubah kain · regresi)")
    print("=" * 84)

    # ══ T1. Tahap BARU lewat API master → muncul di enum & pemilih SPK ═══════
    print("\n── T1. Admin menambah tahap 'Sanforize' (tanpa programmer) ──")
    code_new = f"sanforize{tag}"
    r = admin.post(f"{BASE}/api/entity-masters/process-stages", headers=h(ENT_A), timeout=30,
                   json={"code": code_new, "name": f"Sanforize {tag}", "kind": "makloon",
                         "seq": 85, "applies_to_lines": ["woven"], "needs_vendor": True,
                         "process_type": "finishing", "changes_stage": False,
                         "from_stage": "finished", "to_stage": "finished",
                         "tariff_basis_default": "lumpsum",
                         "material_flow": "either", "material_flow_default": "moves",
                         "notes": "Tahap uji POC FASE T", "entity_id": "all"})
    created = r.status_code in (200, 201)
    ok(created, "tahap baru dibuat lewat API master", f"{r.status_code} {r.text[:200]}")
    if created:
        made_stages.append(r.json().get("id", ""))
    ok(code_new in enum_values(admin, ENT_A, "process_stage"),
       "tahap baru langsung ada di /api/enums (enum `process_stage`) — tanpa restart")
    opts = stage_options(admin, ENT_A)
    ok(code_new in [o["value"] for o in opts],
       "tahap baru langsung ada di pemilih langkah SPK (/api/process-stages)",
       str([o["value"] for o in opts]))
    woven_opts = [o["value"] for o in stage_options(admin, ENT_A, "woven")]
    print_opts = [o["value"] for o in stage_options(admin, ENT_A, "printing")]
    ok(code_new in woven_opts and code_new not in print_opts,
       "penyaring lini bekerja: tahap khusus `woven` tak muncul di lini `printing`",
       f"woven={woven_opts} printing={print_opts}")
    ok("screen" in print_opts and "screen" not in woven_opts,
       "tahap `screen` muncul di lini printing (dan bukan di woven)",
       f"printing={print_opts}")
    ok("inspect" not in [o["value"] for o in opts],
       "tahap `inspect` (inspeksi internal) TIDAK ditawarkan sbg langkah SPK "
       "(tak ada mitra/tarif → jalan buntu)")

    # ══ T2a. SCREEN sebagai JASA MURNI (kain tidak bergerak) ════════════════
    print("\n── T2a. Staf printing membuat SPK berisi tahap Screen (jasa murni) ──")
    pfp = db.products.find_one({"id": "prod_pfp_katun"}, {"_id": 0, "id": 1, "base_unit": 1})
    bal = db.inventory_balances.find_one({"product_id": "prod_pfp_katun",
                                          "warehouse_id": WH, "owner_entity_id": ENT_A},
                                         {"_id": 0, "available_qty": 1})
    avail = float((bal or {}).get("available_qty") or 0)
    ok(bool(pfp), "produk PFP (input tahap screen) tersedia di data demo")
    qty_scr = 10.0
    r = make_order(admin, [{"stage_code": "screen", "material_flow": "service_only",
                            "makloon_id": "mak_seed_screen",
                            "input_product_id": "prod_pfp_katun", "colors": 2}],
                   qty_scr, "prod_pfp_katun", f"POC-T {tag} screen jasa murni")
    o_scr = r.json() if r.status_code in (200, 201) else {}
    ok(bool(o_scr.get("id")), "SPK tahap Screen (jasa murni) tersimpan",
       f"{r.status_code} {r.text[:300]}")
    if o_scr.get("id"):
        made_orders.append(o_scr["id"])
    st = (o_scr.get("steps") or [{}])[0]
    ok(st.get("stage_code") == "screen" and st.get("stage_label"),
       "langkah membawa `stage_code`+`stage_label` dari master", str(st.get("stage_code")))
    ok(st.get("changes_stage") is False,
       "master memberi tahu mesin bahwa tahap ini TIDAK mengubah kain")
    ok(st.get("material_flow") == "service_only",
       "aliran kain langkah = jasa murni (pilihan langkah dihormati)",
       str(st.get("material_flow")))
    est = st.get("estimate") or {}
    ok(est.get("method") == "no_transform",
       "estimasi memakai metode `no_transform` (rumus GSM dipotong)", str(est.get("method")))
    ok(abs(float(st.get("expected_output_qty") or 0) - qty_scr) < 0.001,
       f"KAIN TIDAK BERUBAH: qty keluar = qty masuk ({qty_scr:g})",
       f"expected={st.get('expected_output_qty')}")
    ok(float(est.get("shrinkage_pct", -1)) == 0.0 and float(st.get("waste_pct", -1)) == 0.0,
       "susut dipaksa 0% (tersimpan di langkah, bukan hanya di estimasi)",
       f"est={est.get('shrinkage_pct')} step={st.get('waste_pct')}")
    expl = " | ".join(est.get("explain") or [])
    ok("TIDAK mengubah kain" in expl and "JASA MURNI" in expl.upper(),
       "explain[] menyebut ALASANNYA (tak mengubah kain · jasa murni)", expl[:200])
    ok(st.get("output_product_id") == "prod_pfp_katun",
       "produk output diisi otomatis = kain yang sama (tak perlu produk hasil baru)")

    print("   · Issue harus DITOLAK (kain tidak boleh bergerak di langkah jasa murni)")
    r = admin.post(f"{BASE}/api/makloon-orders/{o_scr.get('id')}/issue", headers=h(ENT_A),
                   timeout=30, json={"step_seq": 1, "from_warehouse_id": WH})
    ok(r.status_code == 409, "Issue ditolak 409", f"{r.status_code} {r.text[:200]}")
    ok("Catat Jasa" in r.text or "JASA MURNI" in r.text,
       "penolakan menuntun ke aksi yang benar (\"Catat Jasa\")", r.text[:200])

    print("   · Catat Jasa: tagihan mitra + jurnal lahir, roll TIDAK lahir")
    rolls_before = db.inventory_rolls.count_documents({})
    r = admin.post(f"{BASE}/api/makloon-orders/{o_scr.get('id')}/record-service",
                   headers=h(ENT_A), timeout=60,
                   json={"step_seq": 1, "colors": 2, "aux_cost": 0, "ppn": 0,
                         "supplier_invoice_no": f"POC-T-{tag}",
                         "note": "2 kasa untuk motif uji POC"})
    served = r.status_code == 200
    ok(served, "Catat Jasa berhasil", f"{r.status_code} {r.text[:300]}")
    o_scr2 = r.json() if served else {}
    st2 = (o_scr2.get("steps") or [{}])[0]
    ok(st2.get("status") == "received", "langkah selesai (status `received`)",
       str(st2.get("status")))
    ok(abs(float(st2.get("actual_output_qty") or 0) - qty_scr) < 0.001,
       "qty aktual = qty masuk (kain benar-benar tidak berubah)")
    ok(not (st2.get("lots") or []), "TIDAK ada roll/lot baru yang lahir")
    ok(db.inventory_rolls.count_documents({}) == rolls_before,
       "jumlah roll di gudang tidak bergerak sama sekali")
    svc_value = float(st2.get("service_value") or 0)
    ok(svc_value > 0, f"biaya jasa MASUK BUKU: Rp {svc_value:,.0f}")
    bill = db.vendor_bills.find_one({"id": st2.get("service_bill_id")}, {"_id": 0})
    ok(bool(bill) and bill.get("service_only") is True,
       "tagihan mitra lahir & ditandai `service_only`", str((bill or {}).get("bill_number")))
    je = db.journal_entries.find_one({"source_type": "subcon_service",
                                      "source_id": st2.get("service_bill_id")}, {"_id": 0})
    accs = {l.get("account_code") for l in ((je or {}).get("lines") or [])}
    ok(bool(je) and "1-1350" in accs and "2-1100" in accs,
       "jurnal Dr 1-1350 WIP / Cr 2-1100 Hutang terbentuk", str(sorted(accs)))
    ok(float(o_scr2.get("service_absorption_pending") or 0) == 0.0
       and float((o_scr2.get("costing") or {}).get("service_unabsorbed") or 0) == svc_value,
       "SPK ini tidak punya langkah kain → jasanya dibebankan, bukan digantung (T7)",
       f"pending={o_scr2.get('service_absorption_pending')} "
       f"unabsorbed={(o_scr2.get('costing') or {}).get('service_unabsorbed')}")
    je2 = db.journal_entries.find_one(
        {"source_type": "subcon_service_unabsorbed",
         "source_id": f"{o_scr.get('id')}:service_unabsorbed"}, {"_id": 0})
    accs2 = {l.get("account_code") for l in ((je2 or {}).get("lines") or [])}
    ok(bool(je2) and accs2 == {"5-1200", "1-1350"},
       "T7 — jurnal Dr 5-1200 / Cr 1-1350 keluar: WIP kembali NOL", str(sorted(accs2)))

    # ══ T2b. SCREEN dengan kain DIKIRIM (pilihan lain dari master `either`) ══
    print("\n── T2b. Tahap Screen yang sama, tetapi kainnya DIKIRIM (moves) ──")
    qty_mv = 8.0
    if avail < (qty_scr + qty_mv + 5):
        print(f"  [SKIP] stok PFP {avail:g} yard kurang untuk T2b")
    else:
        r = make_order(admin, [{"stage_code": "screen", "material_flow": "moves",
                                "makloon_id": "mak_seed_screen",
                                "input_product_id": "prod_pfp_katun",
                                "tariff_basis": "lumpsum", "tariff_rate": 400000}],
                       qty_mv, "prod_pfp_katun", f"POC-T {tag} screen kain dikirim")
        o_mv = r.json() if r.status_code in (200, 201) else {}
        ok(bool(o_mv.get("id")), "SPK Screen dengan kain dikirim tersimpan",
           f"{r.status_code} {r.text[:300]}")
        if o_mv.get("id"):
            made_orders.append(o_mv["id"])
        smv = (o_mv.get("steps") or [{}])[0]
        ok(smv.get("material_flow") == "moves",
           "master `either` menghormati pilihan langkah = kain dikirim")
        ok((smv.get("estimate") or {}).get("method") == "no_transform"
           and abs(float(smv.get("expected_output_qty") or 0) - qty_mv) < 0.001,
           "kain tetap TIDAK berubah walau dikirim (qty keluar = qty masuk)")
        r = admin.post(f"{BASE}/api/makloon-orders/{o_mv.get('id')}/issue", headers=h(ENT_A),
                       timeout=60, json={"step_seq": 1, "from_warehouse_id": WH})
        ok(r.status_code == 200, "Issue BOLEH untuk aliran `moves`",
           f"{r.status_code} {r.text[:200]}")
        r = admin.post(f"{BASE}/api/makloon-orders/{o_mv.get('id')}/record-service",
                       headers=h(ENT_A), timeout=30, json={"step_seq": 1, "tariff": 1000})
        ok(r.status_code == 409,
           "Catat Jasa DITOLAK untuk langkah yang memindahkan kain (aksi tidak tertukar)",
           f"{r.status_code} {r.text[:200]}")
        r = admin.post(f"{BASE}/api/makloon-orders/{o_mv.get('id')}/receive", headers=h(ENT_A),
                       timeout=60, json={"step_seq": 1, "actual_output_qty": qty_mv,
                                         "output_warehouse_id": WH,
                                         "rolls": [{"lot": f"POC-SCR-{tag}",
                                                    "length": qty_mv, "grade": "A"}]})
        rec = r.status_code == 200
        ok(rec, "Terima Hasil berhasil (roll kembali utuh)", f"{r.status_code} {r.text[:300]}")
        if rec:
            s3 = (r.json().get("steps") or [{}])[0]
            hpp = float(s3.get("output_value") or 0)
            mat = float(s3.get("material_value") or 0)
            svc = float(s3.get("service_value") or 0)
            ok(abs(hpp - (mat + svc)) < 1.0,
               f"biaya jasa kasa MASUK HPP kain: {mat:,.0f} + {svc:,.0f} = {hpp:,.0f}")

    # ══ T3. Tahap yang MASIH dipakai tidak bisa dinonaktifkan ═══════════════
    print("\n── T3. Menonaktifkan tahap yang masih dipakai SPK ──")
    row = db.process_stages.find_one({"code": "screen", "entity_id": "all"}, {"_id": 0, "id": 1})
    n_users = db.makloon_orders.count_documents({"steps.stage_code": "screen"})
    ok(n_users > 0, f"tahap `screen` memang sedang dipakai {n_users} SPK")
    r = admin.patch(f"{BASE}/api/entity-masters/process-stages/{(row or {}).get('id')}",
                    headers={**h(ENT_A), "X-Entity-Id": "all"}, timeout=30,
                    json={"data": {"active": False}})
    ok(r.status_code == 409, "penonaktifan DITOLAK 409", f"{r.status_code} {r.text[:250]}")
    ok(str(n_users) in r.text,
       "penolakan menyebut JUMLAH pemakainya (bukan sekadar 'tidak boleh')", r.text[:250])
    still = db.process_stages.find_one({"code": "screen", "entity_id": "all"},
                                       {"_id": 0, "active": 1})
    ok((still or {}).get("active") is not False, "tahapnya tetap aktif di basis data")

    # ══ T4. REGRESI — SPK gaya lama menghasilkan angka IDENTIK ══════════════
    print("\n── T4. Manajer membuka SPK lama: angkanya tidak boleh bergeser ──")
    seed_o = db.makloon_orders.find_one({"mko_number": "MKO-00001"}, {"_id": 0})
    seed_step = ((seed_o or {}).get("steps") or [{}])[0]
    seed_est = seed_step.get("estimate") or {}
    benang = db.products.find_one({"sku": "BNG-KTN-001"}, {"_id": 0, "id": 1})
    ok(bool(seed_est), "SPK seed MKO-00001 (lahir sebelum FASE T) ditemukan")
    # Sengaja TIDAK memeriksa stok: membuat SPK tidak memindahkan stok apa pun
    # (bahan baru bergerak saat Issue), dan uji ini hanya membandingkan ANGKA
    # estimasi/tarifnya. Memeriksa stok di sini hanya akan membuat uji regresi
    # paling penting fase ini sering dilewati begitu data demo terpakai.
    if seed_est and benang:
        r = make_order(admin, [{
            # SENGAJA gaya lama: hanya `process_type`, TANPA `stage_code`.
            "process_type": seed_step.get("process_type"),
            "makloon_id": seed_step.get("makloon_id"),
            "recipe_id": seed_step.get("recipe_id") or "",
            "input_product_id": seed_step.get("input_product_id"),
            "output_product_id": seed_step.get("output_product_id"),
            "byproduct_product_id": seed_step.get("byproduct_product_id") or "",
            "yield_factor": seed_step.get("yield_factor") or 0,
            "yield_override_reason": seed_step.get("yield_override_reason") or "",
            "waste_pct": seed_step.get("waste_pct"),
            "byproduct_pct": seed_step.get("byproduct_pct") or 0,
            "tariff": 3500,
        }], float(seed_o.get("material_qty") or 30), seed_step.get("input_product_id"),
            f"POC-T {tag} regresi gaya lama")
        o_reg = r.json() if r.status_code in (200, 201) else {}
        ok(bool(o_reg.get("id")), "SPK gaya lama tetap bisa dibuat",
           f"{r.status_code} {r.text[:300]}")
        if o_reg.get("id"):
            made_orders.append(o_reg["id"])
        sreg = (o_reg.get("steps") or [{}])[0]
        ereg = sreg.get("estimate") or {}
        ok(abs(float(ereg.get("expected_output_qty") or 0)
               - float(seed_est.get("expected_output_qty") or -1)) < 0.001,
           f"expected_output_qty IDENTIK ({seed_est.get('expected_output_qty')})",
           f"baru={ereg.get('expected_output_qty')}")
        ok((ereg.get("explain") or []) == (seed_est.get("explain") or []),
           "explain[] IDENTIK baris per baris",
           f"lama={seed_est.get('explain')}\n           baru={ereg.get('explain')}")
        ok(ereg.get("method") == seed_est.get("method")
           and float(ereg.get("shrinkage_pct") or -1) == float(seed_est.get("shrinkage_pct") or -2)
           and float(ereg.get("kg_effective") or -1) == float(seed_est.get("kg_effective") or -2),
           "metode, susut & berat efektif IDENTIK")
        # Yang dibandingkan adalah RENCANA lawan RENCANA. `steps[].tariff` BERGANTI ARTI
        # sepanjang hidup langkah: saat lahir ia rencana, saat `receive` ia diganti
        # tagihan mitra yang sungguhan (MKO-00001 sudah selesai → 381.500 = 3.500 × 109
        # yard hasil nyata, sementara rencananya 500.000 karena tagihan minimum kontrak).
        # Membandingkan rencana SPK baru dengan angka aktual SPK lama akan selalu memerah
        # dan menuduh mesin estimasi untuk hal yang bukan urusannya. Rencana yang lahir
        # bersama langkah tetap tersimpan utuh di `tariff_plan`/`tariff_base_equivalent`.
        def _plan_amount(step: dict) -> float:
            plan = step.get("tariff_plan") or {}
            if plan.get("amount") is not None:
                return float(plan["amount"] or 0)
            return float((step.get("tariff_base_equivalent") or {}).get("amount") or 0)

        ok(abs(_plan_amount(sreg) - _plan_amount(seed_step)) < 1.0,
           f"biaya jasa RENCANA IDENTIK (Rp {_plan_amount(seed_step):,.0f})",
           f"baru={_plan_amount(sreg)} · aktual SPK lama (sesudah terima) "
           f"{seed_step.get('tariff')}")
        ok(seed_step.get("tariff_original") == sreg.get("tariff_original"),
           "dasar tarif yang lahir bersama langkah IDENTIK (basis · tarif · qty · satuan)",
           f"lama={seed_step.get('tariff_original')} baru={sreg.get('tariff_original')}")
        ok(sreg.get("stage_code") == "tenun" and sreg.get("changes_stage") is True,
           "tahapnya DICARI dari `process_type` (jembatan kompatibilitas bekerja)",
           str(sreg.get("stage_code")))
        ok(sreg.get("material_flow") == "moves",
           "langkah gaya lama tetap memindahkan kain (arti dokumen tidak berubah)")
    else:
        print("  [SKIP] SPK seed MKO-00001 / produk benang tidak ada — uji regresi dilewati")

    # ══ T5. Override per badan usaha ════════════════════════════════════════
    print("\n── T5. Tahap khusus satu badan usaha tidak bocor ke badan usaha lain ──")
    code_b = f"kalander{tag}"
    r = admin.post(f"{BASE}/api/entity-masters/process-stages", headers=h(ENT_B), timeout=30,
                   json={"code": code_b, "name": f"Kalander {tag}", "kind": "makloon",
                         "seq": 95, "needs_vendor": False, "process_type": "finishing",
                         "changes_stage": False, "from_stage": "finished",
                         "to_stage": "finished", "material_flow": "service_only",
                         "material_flow_default": "service_only",
                         "applies_to_lines": [], "entity_id": ENT_B})
    made_b = r.status_code in (200, 201)
    ok(made_b, "tahap khusus CV Kanda Suka dibuat", f"{r.status_code} {r.text[:200]}")
    if made_b:
        made_stages.append(r.json().get("id", ""))
    vals_b = enum_values(admin, ENT_B, "process_stage")
    vals_a = enum_values(admin, ENT_A, "process_stage")
    ok(code_b in vals_b, "tahap itu terlihat di badan usaha pemiliknya")
    ok(code_b not in vals_a, "tahap itu TIDAK bocor ke PT Kain Suka Cita", f"dapat {vals_a}")
    ok(all(c in vals_a and c in vals_b for c in ("tenun", "screen", "printing")),
       "baris GLOBAL tetap terlihat di kedua badan usaha")

    # ══ T6. BUKTI-MERAH gate: needs_vendor tanpa mitra terdaftar ════════════
    print("\n── T6. Bukti-merah: tahap ber-mitra tanpa satu pun mitra terdaftar ──")
    ok(gate_exit() == 0, "gate INV-DOMAIN-06 HIJAU sebelum uji")
    code_dead = f"kasarotary{tag}"
    r = admin.post(f"{BASE}/api/entity-masters/process-stages", headers=h(ENT_A), timeout=30,
                   json={"code": code_dead, "name": f"Rotary Engraving {tag}",
                         "kind": "makloon", "seq": 96, "needs_vendor": True,
                         "process_type": "lainnya", "changes_stage": False,
                         "from_stage": "pfp", "to_stage": "pfp",
                         "material_flow": "service_only",
                         "material_flow_default": "service_only",
                         "applies_to_lines": [], "entity_id": "all"})
    dead_id = r.json().get("id", "") if r.status_code in (200, 201) else ""
    ok(bool(dead_id), "tahap ber-mitra tanpa mitra dibuat (form TIDAK memblokir — 3b)",
       f"{r.status_code} {r.text[:200]}")
    ok(gate_exit() == 1,
       "gate INV-DOMAIN-06 MEMERAH — kelalaian terlihat di tempat yang benar")

    # T8 — SPK dengan tahap itu tetap bisa disimpan, tetapi memperingatkan.
    if float((bal or {}).get("available_qty") or 0) >= 3:
        r = make_order(admin, [{"stage_code": code_dead, "material_flow": "service_only",
                                "input_product_id": "prod_pfp_katun",
                                "tariff_basis": "lumpsum", "tariff_rate": 100000}],
                       2.0, "prod_pfp_katun", f"POC-T {tag} tanpa mitra")
        o_w = r.json() if r.status_code in (200, 201) else {}
        ok(bool(o_w.get("id")), "T8 — SPK tanpa mitra TETAP tersimpan (keputusan 3b)",
           f"{r.status_code} {r.text[:250]}")
        if o_w.get("id"):
            made_orders.append(o_w["id"])
        warns = " | ".join(o_w.get("warnings") or [])
        ok("mitra" in warns.lower(),
           "…tetapi membawa peringatan yang menyebut mitra belum dipilih", warns[:200])

    # "Dibereskan" harus berarti dibereskan SELURUHNYA. Menghapus baris masternya lebih
    # dulu sementara SPK uji T8 masih menunjuk `stage_code` itu justru memicu pelanggaran
    # LAIN yang sah: aturan A gate (tahap yang masih dipakai dokumen tidak boleh hilang).
    # Gatenya benar; urutan bersih-bersihnya yang salah. Jadi dokumen pemakainya dihapus
    # dulu, baru tahapnya — dan setelah itu barulah gate berhak hijau.
    for oid in list(made_orders):
        if db.makloon_orders.count_documents({"id": oid, "steps.stage_code": code_dead}):
            db.makloon_orders.delete_one({"id": oid})
            db.vendor_bills.delete_many({"makloon_order_id": oid})
            made_orders.remove(oid)
    if dead_id:
        db.process_stages.delete_one({"id": dead_id})
    ok(db.makloon_orders.count_documents({"steps.stage_code": code_dead}) == 0,
       "tidak ada SPK yang masih menunjuk tahap uji (dokumen dibereskan lebih dulu)")
    ok(gate_exit() == 0, "gate HIJAU lagi setelah tahap tanpa mitra dibereskan")

    # ══ T9. Nol residu ══════════════════════════════════════════════════════
    print("\n── T9. Bersih-bersih (POC harus bisa dijalankan berulang) ──")
    removed = 0
    for oid in made_orders:
        removed += db.makloon_orders.delete_many({"id": oid}).deleted_count
        removed += db.vendor_bills.delete_many({"makloon_order_id": oid}).deleted_count
        removed += db.journal_entries.delete_many(
            {"source_id": {"$regex": f"^{oid}"}}).deleted_count
        removed += db.document_relations.delete_many(
            {"$or": [{"from_id": oid}, {"to_id": oid}]}).deleted_count
    for sid in made_stages:
        if sid:
            removed += db.process_stages.delete_many({"id": sid}).deleted_count
    removed += db.process_stages.delete_many({"code": {"$regex": tag}}).deleted_count
    for mid in made_makloons:
        removed += db.makloons.delete_many({"id": mid}).deleted_count
    removed += db.inventory_rolls.delete_many({"lot": {"$regex": tag}}).deleted_count
    removed += db.inventory_lots.delete_many({"lot_code": {"$regex": tag}}).deleted_count
    new_audit = {d["id"] for d in db.audit_logs.find({}, {"_id": 0, "id": 1})} - audit_before
    audit_removed = (db.audit_logs.delete_many({"id": {"$in": list(new_audit)}}).deleted_count
                     if new_audit else 0)
    ok(removed >= 3, f"data uji dibersihkan ({removed} dokumen · {audit_removed} jejak audit)")
    ok(db.process_stages.count_documents({"code": {"$regex": tag}}) == 0,
       "tidak ada tahap uji yang tertinggal")
    ok(db.makloon_orders.count_documents({"notes": {"$regex": tag}}) == 0,
       "tidak ada SPK uji yang tertinggal")

    # Roll/lot/mutasi yang lahir dari alur kain SUNGGUHAN dipulihkan EKSAK — bukan
    # "dihapus yang baru" (memotong/menerima roll tidak bisa dibalik per-dokumen).
    restore_stock(stock_snap)
    stock_after = {c: db[c].count_documents({}) for c in stock_before}
    drift = {c: (stock_before[c], stock_after[c]) for c in stock_before
             if stock_before[c] != stock_after[c]}
    ok(not drift, "stok dipulihkan EKSAK — nol residu roll · lot · mutasi · saldo",
       f"masih bergeser: {drift}")

    print("\n" + "=" * 84)
    print(f"  HASIL: {PASS} PASS · {FAIL} FAIL")
    print("=" * 84)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
