#!/usr/bin/env python3
"""POC FASE F — **R&D & DESAIN** (Spesifikasi · Labdip · Proofing · Lifecycle Produk).

Masalah nyata pemilik yang dibuktikan selesai:
*"KN tidak membeli dari katalog supplier — KN meminta supplier MEMBUAT barang sesuai
spesifikasi. Alur nyatanya: R&D bikin spesifikasi → pilih desain → labdip/proofing ke
beberapa supplier → sample dinilai (rnd 1, 2, 3 sampai ACC) → pemenang dipilih → harga
jadi kontrak → baru boleh PR/PO. Sebelum fase ini alur itu TIDAK ADA di sistem: enum
`sample_type` & `lifecycle` terdaftar tetapi nol penulis, dan produk 'konsep' tetap bisa
dijual."*

Yang dibuktikan lewat HTTP nyata (bukan unit test):

  1. Kosakata & kebijakan R&D terbaca UI; RBAC 4 role benar (sales mengajukan, manager memutus).
  2. Spesifikasi: draft → ajukan → ACC → **produk lahir** berstatus BELUM boleh dijual.
  3. **Uang tidak keluar untuk barang belum sah**: SO, PR, dan PO atas produk itu DITOLAK
     dengan pesan yang bisa ditindak — sementara PR atas produk lama tetap BERHASIL
     (bukti tidak ada regresi pada alur yang sudah jalan).
  4. Sakelar `rnd.lifecycle_enforcement` benar-benar berpengaruh (bukan tombol palsu).
  5. Labdip dikirim ke **2 supplier sekaligus** → tiap supplier punya round sendiri.
  6. Round tidak bisa ditutup **tanpa lampiran** maupun **tanpa catatan** (PS-18).
  7. Hasil `revisi` membuka **rnd 2**; ACC wajib skor; batas `rnd.max_rounds` ditegakkan
     dan hanya bisa dilewati manager DENGAN alasan tertulis.
  8. Keputusan pemenang **melahirkan kontrak harga + barang supplier**, dan `sample_ref`
     kontrak menunjuk balik ke nomor sample (menutup placeholder Fase E).
  9. **Proofing wajib kode desain**; master desain punya kode, versi, dan pengesahan.
 10. Rilis ke produksi membuat produk **akhirnya boleh dijual** (katalog & papan lifecycle).
 11. Ambil bahan sample = **mutasi stok NYATA** `sample_issue` (stok gudang berkurang)
     DAN **berjurnal** Dr 6-7000 Beban Sample & Pengembangan / Cr 1-1300 Persediaan.
 12. Jejak Dokumen (G-4) menyambung kontrak → sample → spesifikasi.
 13. **BUKTI-MERAH**: INV-RND-01/02/04/05/07 benar-benar MEMERAH saat pelanggaran disuntik,
     lalu kembali hijau setelah dipulihkan.
 14. Seluruh artefak POC dibersihkan → nol residu, invarian global tetap hijau.

Jalankan:  python backend/test_fase_f_rnd_poc.py
"""
import asyncio
import io
import os
import subprocess
import sys

import requests

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
_made = {"specs": [], "samples": [], "products": [], "contracts": [], "items": [],
         "designs": [], "prs": [], "movements": [], "journals": []}
_roll_backup = {}


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


def HF(tok: str) -> dict:
    """Header untuk multipart (JANGAN set Content-Type — requests yang mengisi boundary)."""
    return {"Authorization": f"Bearer {tok}"}


def cfg_set(tok: str, key: str, value, reason: str = "POC FASE F") -> bool:
    r = requests.put(f"{BASE}/config/values", headers=H(tok), timeout=30, json={
        "items": [{"key": key, "value": value, "scope_type": "global",
                   "scope_id": "", "reason": reason}]})
    return r.status_code == 200


def cfg_get(tok: str, key: str):
    r = requests.get(f"{BASE}/config/effective", headers=H(tok), params={"q": key}, timeout=30)
    for it in r.json().get("items", []):
        if it["key"] == key:
            return it["value"]
    return None


def integrity(only: str = "") -> tuple:
    """Jalankan gate invarian. `only` = lapisan yang relevan (mis. `rnd`).

    KENAPA ADA `only` (terukur 2026-07-29): eksekusi LENGKAP menilai 211
    invarian. Pada blok BUKTI-MERAH di bawah, yang diuji HANYA keluarga
    INV-RND, jadi 211 invarian dibaca ulang 5× tanpa menambah bukti apa pun —
    satu POC ini saja membakar puluhan detik di `gate.sh --full`. Klaim GLOBAL
    ("invarian global HIJAU" / "nol residu") TETAP memakai eksekusi LENGKAP.
    """
    cmd = [sys.executable, "/app/scripts/verify_data_integrity.py"]
    if only:
        cmd.append(f"--only={only}")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout + p.stderr


def inv_state(out: str, inv: str) -> str:
    for ln in out.splitlines():
        if inv in ln:
            if "[PASS]" in ln:
                return "PASS"
            if "[FAIL]" in ln:
                return "FAIL"
            if "[WARN]" in ln:
                return "WARN"
    return "?"


async def _db():
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli[os.environ.get("DB_NAME", "test_database")], cli


def dbrun(fn):
    async def _wrap():
        db, cli = await _db()
        try:
            return await fn(db)
        finally:
            cli.close()
    return asyncio.run(_wrap())


PNG_1PX = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
           b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
           b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


def upload_proof(tok: str, sample_id: str, round_id: str, name: str = "hasil.png") -> dict:
    r = requests.post(f"{BASE}/rnd/samples/{sample_id}/rounds/{round_id}/attachments",
                      headers=HF(tok), timeout=60,
                      files={"file": (name, io.BytesIO(PNG_1PX), "image/png")})
    return {"code": r.status_code, "body": r.json() if r.status_code < 300 else r.text}


def main() -> int:  # noqa: C901 — POC memang panjang & berurutan
    tok = {k: login(k) for k in USERS}
    admin, manager, sales, wh = tok["admin"], tok["manager"], tok["sales"], tok["warehouse"]
    cfg_keys = ["rnd.lifecycle_enforcement", "rnd.max_rounds",
                "rnd.require_design_for_proofing", "rnd.require_attachment_on_round"]
    original = {k: cfg_get(admin, k) for k in cfg_keys}

    # ── TEST 1 ───────────────────────────────────────────────────────────────
    head("TEST 1 — Kosakata R&D, kebijakan berlaku, dan RBAC 4 role")
    m = requests.get(f"{BASE}/rnd/meta", headers=H(admin), timeout=30)
    meta = m.json() if m.status_code == 200 else {}
    pol = meta.get("policy", {})
    ok(m.status_code == 200 and "lifecycle_enforcement" in pol,
       "kebijakan R&D yang BERLAKU bisa dibaca UI",
       f"penegakan={pol.get('lifecycle_enforcement')} · max_rounds={pol.get('max_rounds')} "
       f"· SLA={pol.get('round_sla_days')} hari")
    types = {t["value"] for t in meta.get("sample_types", [])}
    lifes = {t["value"] for t in meta.get("lifecycles", [])}
    ok({"labdip", "proofing", "bulk_sample"} <= types,
       "enum jenis sample HIDUP (labdip · proofing · bulk_sample)", str(sorted(types)))
    ok({"konsep", "labdip", "proofing", "disetujui", "produksi", "dihentikan"} <= lifes,
       "enum lifecycle produk HIDUP (dulu terdaftar tapi nol penulis)")
    ok(len(meta.get("reasons", [])) >= 5,
       "alasan keputusan pemenang terkendali (bukan teks bebas)",
       f"{len(meta.get('reasons', []))} label")
    for role, t in (("sales", sales), ("warehouse", wh), ("manager", manager)):
        rr = requests.get(f"{BASE}/rnd/meta", headers=H(t), timeout=30)
        ok(rr.status_code == 200, f"{role} boleh MELIHAT modul R&D", f"HTTP {rr.status_code}")
    rr = requests.post(f"{BASE}/rnd/specs", headers=H(wh), timeout=30,
                       json={"title": "coba", "target": {"fabric_type": "woven"}})
    ok(rr.status_code == 403, "warehouse TIDAK boleh membuat spesifikasi (RBAC)",
       f"HTTP {rr.status_code}")

    # ── TEST 2 ───────────────────────────────────────────────────────────────
    head("TEST 2 — Spesifikasi R&D: draft → ajukan → ACC → PRODUK LAHIR (belum boleh dijual)")
    colors = requests.get(f"{BASE}/color-library", headers=H(admin), timeout=30).json()
    clist = colors if isinstance(colors, list) else colors.get("items", [])
    ok(len(clist) > 0, "pustaka warna tersedia sebagai sumber warna target (PS-13)",
       f"{len(clist)} warna")
    color = clist[0]
    bad = requests.post(f"{BASE}/rnd/specs", headers=H(admin), timeout=30, json={
        "title": "POC Spek tanpa jenis kain", "target": {"stage": "finished"}})
    ok(bad.status_code == 400, "spesifikasi tanpa jenis kain DITOLAK (INV-DOMAIN-02 dijaga di hulu)",
       f"HTTP {bad.status_code}")
    bad2 = requests.post(f"{BASE}/rnd/specs", headers=H(admin), timeout=30, json={
        "title": "POC warna liar", "target": {"stage": "finished", "fabric_type": "woven",
                                              "gramasi": 120, "lebar": 115},
        "color_target": {"code": "WARNA-NGAWUR-999"}})
    ok(bad2.status_code == 400, "warna target di luar Pustaka Warna DITOLAK (tidak boleh teks bebas)",
       f"HTTP {bad2.status_code}")
    r = requests.post(f"{BASE}/rnd/specs", headers=H(sales), timeout=30, json={
        "title": "POC Katun Premium Warna Khusus",
        "category": "Katun", "base_unit": "meter", "sku_hint": "POC-RND-001",
        "sample_type_hint": "labdip",
        "target": {"stage": "finished", "fabric_type": "woven", "gramasi": 135,
                   "lebar": 115, "grade": "A", "epi": 60, "ppi": 58},
        "color_target": {"color_id": color["id"]},
        "target_price": 48000, "notes": "Permintaan pelanggan: warna khusus, GSM 135"})
    ok(r.status_code == 200, "sales BOLEH mengajukan spesifikasi baru (divisi sales → R&D)",
       f"HTTP {r.status_code} {r.text[:120] if r.status_code != 200 else ''}")
    spec = r.json()
    _made["specs"].append(spec["id"])
    ok(spec["number"].endswith(tuple("0123456789")) and "/SPEC-" in spec["number"],
       "spesifikasi bernomor per entitas", spec["number"])
    ok(spec["status"] == "draft" and spec["lifecycle"] == "konsep",
       "spesifikasi baru = draft & lifecycle konsep")
    ok(spec["color_target"]["code"] == color["code"],
       "warna target ter-snapshot dari pustaka", f"{color['code']} {color['name']}")

    bad3 = requests.post(f"{BASE}/rnd/specs/{spec['id']}/approve", headers=H(sales),
                         timeout=30, json={})
    ok(bad3.status_code == 403, "sales TIDAK boleh meng-ACC spesifikasinya sendiri (RBAC)",
       f"HTTP {bad3.status_code}")
    s2 = requests.post(f"{BASE}/rnd/specs/{spec['id']}/submit", headers=H(sales), timeout=30)
    ok(s2.status_code == 200 and s2.json()["status"] == "review",
       "spesifikasi diajukan untuk persetujuan", f"status {s2.json().get('status')}")
    ap = requests.post(f"{BASE}/rnd/specs/{spec['id']}/approve", headers=H(manager),
                       timeout=60, json={"sku": "POC-RND-001", "name": "POC Katun Premium 135gsm",
                                         "price": 52000, "note": "Sesuai target pelanggan"})
    ok(ap.status_code == 200, "manager meng-ACC spesifikasi",
       f"HTTP {ap.status_code} {ap.text[:160] if ap.status_code != 200 else ''}")
    res = ap.json() if ap.status_code == 200 else {}
    prod = res.get("product") or {}
    if prod.get("id"):
        _made["products"].append(prod["id"])
    ok(prod.get("sku") == "POC-RND-001" and prod.get("lifecycle") == "disetujui",
       "produk LAHIR dari ACC spesifikasi, berstatus `disetujui` (BELUM boleh dijual)",
       f"{prod.get('sku')} · lifecycle {prod.get('lifecycle')}")
    ok(prod.get("spec_id") == spec["id"], "produk menunjuk balik ke spesifikasi asalnya (dua arah)")
    ok(float(prod.get("gramasi") or 0) == 135 and prod.get("fabric_type") == "woven",
       "target teknis spesifikasi terbawa ke produk (GSM & jenis kain)")

    # ── TEST 3 ───────────────────────────────────────────────────────────────
    head("TEST 3 — Barang BELUM sah tidak boleh masuk SO / PR / PO (uang tidak keluar)")
    custs = requests.get(f"{BASE}/customers", headers=H(sales), timeout=30).json()
    cl = custs if isinstance(custs, list) else custs.get("items", [])
    cust = cl[0]
    addr = (cust.get("addresses") or [{}])[0]
    so = requests.post(f"{BASE}/sales-orders", headers=H(sales), timeout=60, json={
        "customer_id": cust["id"], "shipping_address_id": addr.get("id", ""),
        "items": [{"product_id": prod["id"], "quantity": 5, "unit": "meter"}]})
    ok(so.status_code == 400 and "produksi" in so.text.lower() or so.status_code == 400,
       "SO atas produk yang belum dirilis DITOLAK", f"HTTP {so.status_code} · {so.text[:150]}")
    whs = requests.get(f"{BASE}/warehouses", headers=H(admin), timeout=30).json()
    wl = whs if isinstance(whs, list) else whs.get("items", [])
    pr_bad = requests.post(f"{BASE}/purchase-requisitions", headers=H(admin), timeout=60, json={
        "warehouse_id": wl[0]["id"], "reason": "POC gate",
        "items": [{"product_id": prod["id"], "quantity": 10, "unit": "meter", "est_price": 40000}]})
    ok(pr_bad.status_code == 400, "PR atas produk yang belum dirilis DITOLAK",
       f"HTTP {pr_bad.status_code} · {pr_bad.text[:150]}")
    sups = requests.get(f"{BASE}/suppliers", headers=H(admin), timeout=30).json()
    sl = sups if isinstance(sups, list) else sups.get("items", [])
    # FASE E-7 (E7a) mendaftarkan badan usaha grup sebagai baris PEMASOK bertipe
    # `entity`. `sl[0]` bisa jatuh ke sana, dan pagar E7a menolak PO biasa ke badan
    # usaha sendiri lebih dulu (409) — sehingga uji ini seolah gagal padahal yang
    # diuji (gating produk belum rilis) tak pernah sampai dievaluasi. Pilih pemasok
    # LUAR secara eksplisit supaya yang diuji benar-benar lifecycle produk.
    sl = [s for s in sl if (s.get("partner_kind") or "external") != "entity"]
    po_bad = requests.post(f"{BASE}/purchase-orders", headers=H(admin), timeout=60, json={
        "supplier_id": sl[0]["id"], "warehouse_id": wl[0]["id"],
        "items": [{"product_id": prod["id"], "quantity": 10, "unit": "meter",
                   "price": 40000, "expected_grade": "A"}]})
    ok(po_bad.status_code == 400, "PO atas produk yang belum dirilis DITOLAK",
       f"HTTP {po_bad.status_code} · {po_bad.text[:150]}")
    # REGRESI: produk lama (tanpa/ber-lifecycle produksi) HARUS tetap lancar.
    prods_all = requests.get(f"{BASE}/products", headers=H(admin), timeout=30).json()
    seed_prod = next(p for p in prods_all if p["id"] != prod["id"])
    pr_ok = requests.post(f"{BASE}/purchase-requisitions", headers=H(admin), timeout=60, json={
        "warehouse_id": wl[0]["id"], "reason": "POC regresi produk lama",
        "items": [{"product_id": seed_prod["id"], "quantity": 3, "unit": "meter",
                   "est_price": 10000}]})
    ok(pr_ok.status_code == 200,
       "PR atas produk LAMA tetap BERHASIL (nol regresi pada alur yang sudah jalan)",
       f"HTTP {pr_ok.status_code} {pr_ok.text[:120] if pr_ok.status_code != 200 else pr_ok.json().get('number', '')}")
    if pr_ok.status_code == 200:
        _made["prs"].append(pr_ok.json()["id"])

    # ── TEST 4 ───────────────────────────────────────────────────────────────
    head("TEST 4 — Sakelar `rnd.lifecycle_enforcement` NYATA (bukan tombol palsu)")
    ok(cfg_set(admin, "rnd.lifecycle_enforcement", "off"),
       "admin mengubah penegakan lifecycle menjadi `off` lewat Pusat Pengaturan")
    pr_off = requests.post(f"{BASE}/purchase-requisitions", headers=H(admin), timeout=60, json={
        "warehouse_id": wl[0]["id"], "reason": "POC sakelar off",
        "items": [{"product_id": prod["id"], "quantity": 2, "unit": "meter", "est_price": 40000}]})
    ok(pr_off.status_code == 200,
       "dengan penegakan `off`, PR atas produk belum rilis LOLOS → sakelar benar berpengaruh",
       f"HTTP {pr_off.status_code}")
    if pr_off.status_code == 200:
        _made["prs"].append(pr_off.json()["id"])
    ok(cfg_set(admin, "rnd.lifecycle_enforcement", "block"), "penegakan dikembalikan ke `block`")
    pr_re = requests.post(f"{BASE}/purchase-requisitions", headers=H(admin), timeout=60, json={
        "warehouse_id": wl[0]["id"], "reason": "POC sakelar block",
        "items": [{"product_id": prod["id"], "quantity": 2, "unit": "meter", "est_price": 40000}]})
    ok(pr_re.status_code == 400, "setelah dikembalikan ke `block`, PR ditolak lagi")
    if pr_re.status_code == 200:
        _made["prs"].append(pr_re.json()["id"])

    # ── TEST 5 ───────────────────────────────────────────────────────────────
    head("TEST 5 — Labdip dikirim ke 2 SUPPLIER sekaligus (hasil bisa dibandingkan)")
    sp = requests.post(f"{BASE}/rnd/samples", headers=H(admin), timeout=30, json={
        "spec_id": spec["id"], "sample_type": "labdip",
        "title": "Labdip Katun Premium warna khusus",
        "brief": "Cocokkan warna target ±ΔE 1.5", "qty_requested": 3, "unit": "meter"})
    ok(sp.status_code == 200, "permintaan labdip dibuat dari spesifikasi",
       f"HTTP {sp.status_code} {sp.text[:150] if sp.status_code != 200 else sp.json()['number']}")
    sample = sp.json()
    _made["samples"].append(sample["id"])
    ok(sample["spec_number"] == spec["number"] and sample["status"] == "draft",
       "permintaan menaut spesifikasi & berstatus draft")
    sup_a, sup_b = sl[0], sl[1]
    snd = requests.post(f"{BASE}/rnd/samples/{sample['id']}/send", headers=H(admin), timeout=30,
                        json={"supplier_ids": [sup_a["id"], sup_b["id"]],
                              "note": "Mohon kirim swatch 3 meter"})
    ok(snd.status_code == 200, "dikirim ke 2 supplier sekaligus", f"HTTP {snd.status_code}")
    sample = snd.json()
    ok(len(sample["participants"]) == 2 and len(sample["rounds"]) == 2,
       "tiap supplier mendapat round-nya sendiri (rnd 1)",
       f"{len(sample['participants'])} peserta · {len(sample['rounds'])} round")
    ok(all(r["due_date"] for r in sample["rounds"]),
       "tenggat tiap round terisi otomatis dari kebijakan SLA",
       f"tenggat {sample['rounds'][0]['due_date']}")
    r_a = next(r for r in sample["rounds"] if r["supplier_id"] == sup_a["id"])
    r_b = next(r for r in sample["rounds"] if r["supplier_id"] == sup_b["id"])

    # ── TEST 6 ───────────────────────────────────────────────────────────────
    head("TEST 6 — Round TIDAK BISA ditutup tanpa lampiran & tanpa catatan (PS-18)")
    no_file = requests.post(f"{BASE}/rnd/samples/{sample['id']}/rounds/{r_a['id']}/submit",
                            headers=H(admin), timeout=30, json={"note": "sudah dikerjakan"})
    ok(no_file.status_code == 400 and "lampiran" in no_file.text.lower(),
       "setor hasil TANPA lampiran bukti DITOLAK", no_file.text[:130])
    up = upload_proof(admin, sample["id"], r_a["id"], "labdip-a.png")
    ok(up["code"] == 200, "lampiran bukti (foto hasil) terunggah",
       f"HTTP {up['code']} {up['body'].get('filename') if up['code'] == 200 else up['body']}")
    no_note = requests.post(f"{BASE}/rnd/samples/{sample['id']}/rounds/{r_a['id']}/submit",
                            headers=H(admin), timeout=30, json={"note": ""})
    ok(no_note.status_code == 400 and "catatan" in no_note.text.lower(),
       "setor hasil TANPA catatan DITOLAK", no_note.text[:130])
    sub_a = requests.post(f"{BASE}/rnd/samples/{sample['id']}/rounds/{r_a['id']}/submit",
                          headers=H(admin), timeout=30,
                          json={"note": "Warna sedikit lebih tua, handfeel bagus",
                                "measurements": {"delta_e": 2.4, "gsm_actual": 133,
                                                 "shrinkage_pct": 2.0},
                                "cost": 150000})
    ok(sub_a.status_code == 200, "hasil round 1 supplier A tersimpan dengan bukti + hasil ukur",
       f"HTTP {sub_a.status_code}")
    got = next(r for r in sub_a.json()["rounds"] if r["id"] == r_a["id"])
    ok(got["status"] == "submitted" and float(got["measurements"].get("delta_e")) == 2.4,
       "hasil ukur objektif tercatat (ΔE, GSM aktual, susut)",
       f"ΔE {got['measurements'].get('delta_e')} · GSM {got['measurements'].get('gsm_actual')}")

    # ── TEST 7 ───────────────────────────────────────────────────────────────
    head("TEST 7 — Penilaian: revisi → rnd 2 · ACC wajib skor · batas iterasi ditegakkan")
    noscore = requests.post(
        f"{BASE}/rnd/samples/{sample['id']}/rounds/{r_a['id']}/assess",
        headers=H(manager), timeout=30, json={"result": "acc"})
    ok(noscore.status_code == 400 and "skor" in noscore.text.lower(),
       "ACC tanpa SKOR ditolak (kinerja harus bisa dibandingkan antar periode)",
       noscore.text[:120])
    as_a = requests.post(f"{BASE}/rnd/samples/{sample['id']}/rounds/{r_a['id']}/assess",
                         headers=H(manager), timeout=30,
                         json={"result": "revisi", "score": 70,
                               "note": "Turunkan 1 tingkat, ΔE masih 2.4"})
    ok(as_a.status_code == 200, "round 1 supplier A dinilai `revisi`", f"HTTP {as_a.status_code}")
    r2 = requests.post(f"{BASE}/rnd/samples/{sample['id']}/rounds", headers=H(admin), timeout=30,
                       json={"supplier_id": sup_a["id"], "note": "Perbaikan warna"})
    ok(r2.status_code == 200, "round 2 (rnd 2) dibuka untuk supplier A", f"HTTP {r2.status_code}")
    sample = r2.json()
    r_a2 = max([r for r in sample["rounds"] if r["supplier_id"] == sup_a["id"]],
               key=lambda r: r["round_no"])
    ok(r_a2["round_no"] == 2, "nomor round berurut per supplier (rnd 1 → rnd 2)")
    upload_proof(admin, sample["id"], r_a2["id"], "labdip-a-rev.png")
    requests.post(f"{BASE}/rnd/samples/{sample['id']}/rounds/{r_a2['id']}/submit",
                  headers=H(admin), timeout=30,
                  json={"note": "Warna sudah pas, ΔE 0.9", "cost": 120000,
                        "measurements": {"delta_e": 0.9, "gsm_actual": 135}})
    acc = requests.post(f"{BASE}/rnd/samples/{sample['id']}/rounds/{r_a2['id']}/assess",
                        headers=H(manager), timeout=30,
                        json={"result": "acc", "score": 92, "note": "Disetujui, warna presisi"})
    ok(acc.status_code == 200 and acc.json()["status"] == "assessed",
       "round 2 di-ACC dengan skor → permintaan berstatus `assessed`",
       f"skor 92 · status {acc.json().get('status')}")
    part_a = next(p for p in acc.json()["participants"] if p["supplier_id"] == sup_a["id"])
    ok(part_a["status"] == "acc" and float(part_a["best_score"]) == 92,
       "ringkasan per supplier terhitung (status & skor terbaik)")
    # batas iterasi
    upload_proof(admin, sample["id"], r_b["id"], "labdip-b.png")
    requests.post(f"{BASE}/rnd/samples/{sample['id']}/rounds/{r_b['id']}/submit",
                  headers=H(admin), timeout=30,
                  json={"note": "Warna terlalu muda", "measurements": {"delta_e": 4.8}})
    requests.post(f"{BASE}/rnd/samples/{sample['id']}/rounds/{r_b['id']}/assess",
                  headers=H(manager), timeout=30,
                  json={"result": "revisi", "score": 55, "note": "Perlu perbaikan"})
    ok(cfg_set(admin, "rnd.max_rounds", 1), "batas iterasi disetel 1 round untuk menguji pagar")
    over = requests.post(f"{BASE}/rnd/samples/{sample['id']}/rounds", headers=H(wh), timeout=30,
                         json={"supplier_id": sup_b["id"]})
    ok(over.status_code == 400 and "batas" in over.text.lower(),
       "melebihi batas iterasi DITOLAK untuk peran biasa", over.text[:130])
    over2 = requests.post(f"{BASE}/rnd/samples/{sample['id']}/rounds", headers=H(manager),
                          timeout=30, json={"supplier_id": sup_b["id"],
                                            "reason": "Pelanggan bersedia menunggu 1 kali lagi"})
    ok(over2.status_code == 200,
       "manager boleh melewati batas HANYA dengan alasan tertulis (jejak tersimpan)",
       f"HTTP {over2.status_code}")
    ok(cfg_set(admin, "rnd.max_rounds", original["rnd.max_rounds"] or 3),
       "batas iterasi dikembalikan")

    # ── TEST 8 ───────────────────────────────────────────────────────────────
    head("TEST 8 — Keputusan pemenang MELAHIRKAN kontrak harga + barang supplier (Fase E)")
    nodec = requests.post(f"{BASE}/rnd/samples/{sample['id']}/decide", headers=H(manager),
                          timeout=60, json={"supplier_id": sup_b["id"],
                                            "reason_code": "harga_terbaik", "price": 40000})
    ok(nodec.status_code == 400 and "acc" in nodec.text.lower(),
       "supplier tanpa round ACC TIDAK boleh dijadikan pemenang", nodec.text[:130])
    nosales = requests.post(f"{BASE}/rnd/samples/{sample['id']}/decide", headers=H(sales),
                            timeout=30, json={"supplier_id": sup_a["id"],
                                              "reason_code": "mutu_terbaik", "price": 42000})
    ok(nosales.status_code == 403, "sales TIDAK boleh memutus pemenang (RBAC + kebijakan)",
       f"HTTP {nosales.status_code}")
    dec = requests.post(f"{BASE}/rnd/samples/{sample['id']}/decide", headers=H(manager),
                        timeout=90, json={
                            "supplier_id": sup_a["id"], "reason_code": "warna_paling_dekat",
                            "note": "ΔE 0.9 paling dekat target", "price": 42500,
                            "supplier_sku": "POC-SUP-A-001", "supplier_uom": "meter",
                            "moq": 100, "lead_time_days": 14})
    ok(dec.status_code == 200, "manager memutus pemenang",
       f"HTTP {dec.status_code} {dec.text[:170] if dec.status_code != 200 else ''}")
    sample = dec.json() if dec.status_code == 200 else sample
    d = sample.get("decision") or {}
    if d.get("contract_id"):
        _made["contracts"].append(d["contract_id"])
    if d.get("supplier_item_id"):
        _made["items"].append(d["supplier_item_id"])
    ok(sample.get("status") == "decided" and d.get("reason_label"),
       "permintaan berstatus `decided` dengan alasan berlabel",
       f"{d.get('supplier_name')} · {d.get('reason_label')}")
    ct = requests.get(f"{BASE}/supplier-contracts/{d.get('contract_id')}",
                      headers=H(manager), timeout=30) if d.get("contract_id") else None
    ok(bool(ct) and ct.status_code == 200, "KONTRAK HARGA nyata terbentuk dari keputusan sample",
       f"{d.get('contract_number')}")
    if ct is not None and ct.status_code == 200:
        cj = ct.json()
        cj = cj.get("contract", cj)
        ok(cj.get("sample_ref") == sample["number"],
           "`sample_ref` kontrak menunjuk balik ke nomor sample "
           "(placeholder Fase E akhirnya terisi)", f"{cj.get('sample_ref')}")
        ok(float(cj.get("tariff_rate") or 0) == 42500,
           "harga kesepakatan sample menjadi harga kontrak", f"Rp {cj.get('tariff_rate'):,.0f}")
    ok(bool(d.get("supplier_item_id")),
       "BARANG SUPPLIER (peta SKU versi supplier) ikut terbentuk", d.get("supplier_item_id", ""))

    # ── TEST 9 ───────────────────────────────────────────────────────────────
    head("TEST 9 — Proofing WAJIB kode desain · master desain ber-kode, ber-versi, disahkan")
    nod = requests.post(f"{BASE}/rnd/samples", headers=H(admin), timeout=30, json={
        "sample_type": "proofing", "title": "POC Proofing tanpa desain",
        "color_target": {"color_id": color["id"]}})
    ok(nod.status_code == 400 and "desain" in nod.text.lower(),
       "permintaan proofing TANPA kode desain DITOLAK", nod.text[:130])
    dg = requests.post(f"{BASE}/design-gallery", headers=H(admin), timeout=30, json={
        "title": "POC Motif Parang Modern", "code": "POC-DSG-001", "design_type": "pattern",
        "repeat_cm": 32, "color_count": 4, "screen_count": 4,
        "story": "Motif parang gaya modern untuk proofing POC", "tags": ["parang", "poc"]})
    ok(dg.status_code == 200, "master desain dibuat dengan KODE & atribut printing",
       f"HTTP {dg.status_code} {dg.text[:130] if dg.status_code != 200 else ''}")
    design = dg.json()
    _made["designs"].append(design["id"])
    ok(design.get("code") == "POC-DSG-001" and design.get("version") == 1
       and design.get("status") == "draft",
       "desain punya kode unik, versi 1, status draft",
       f"{design.get('code')} v{design.get('version')}")
    # UTANG ALUR F-6.7 (2026-08-18) — pengesahan tidak lagi bekerja dari `draft`:
    # desain wajib DIAJUKAN lebih dulu, dan syarat kelengkapan (kode + berkas) kini
    # ditagih di langkah "Ajukan" — bukan menumpuk di meja penyetuju. Dua pemeriksaan
    # di bawah SENGAJA diperbarui mengikuti alur baru; maksudnya tetap sama:
    # desain tanpa artwork TIDAK BOLEH menjadi sah, dan yang sah boleh dipakai proofing.
    noapp = requests.post(f"{BASE}/design-gallery/{design['id']}/approve", headers=H(admin),
                          timeout=30, json={})
    ok(noapp.status_code == 400 and ("diajuk" in noapp.text.lower() or "ajukan" in noapp.text.lower()),
       "desain DRAF tak bisa disahkan (harus diajukan dulu)", noapp.text[:120])
    nosub = requests.post(f"{BASE}/design-gallery/{design['id']}/submit", headers=H(admin),
                          timeout=30)
    ok(nosub.status_code == 400 and "berkas" in nosub.text.lower(),
       "desain tanpa berkas artwork TIDAK bisa diajukan (apalagi disahkan)", nosub.text[:120])
    fu = requests.post(f"{BASE}/design-gallery/{design['id']}/files", headers=HF(admin),
                       timeout=60, files={"file": ("artwork.png", io.BytesIO(PNG_1PX), "image/png")})
    ok(fu.status_code == 200, "berkas artwork terunggah ke master desain")
    sub = requests.post(f"{BASE}/design-gallery/{design['id']}/submit", headers=H(admin), timeout=30)
    ok(sub.status_code == 200 and sub.json().get("status") == "pending_approval",
       "desain lengkap DIAJUKAN → masuk antrean pengesahan")
    apd = requests.post(f"{BASE}/design-gallery/{design['id']}/approve", headers=H(admin),
                        timeout=30, json={"note": "Artwork final"})
    ok(apd.status_code == 200 and apd.json().get("status") == "approved",
       "desain disahkan → boleh dipakai proofing")
    vb = requests.post(f"{BASE}/design-gallery/{design['id']}/version", headers=H(admin),
                       timeout=30, json={"note": "Revisi warna ke-2", "color_count": 5})
    ok(vb.status_code == 200 and vb.json().get("version") == 2
       and vb.json().get("status") == "draft",
       "versi desain bisa dinaikkan; versi lama terarsip & status kembali draft",
       f"v{vb.json().get('version')} · {len(vb.json().get('versions', []))} riwayat")
    requests.post(f"{BASE}/design-gallery/{design['id']}/submit", headers=H(admin), timeout=30)
    requests.post(f"{BASE}/design-gallery/{design['id']}/approve", headers=H(admin),
                  timeout=30, json={"note": "v2 final"})
    pf = requests.post(f"{BASE}/rnd/samples", headers=H(admin), timeout=30, json={
        "sample_type": "proofing", "title": "POC Proofing Parang Modern",
        "design_id": design["id"], "design_version": 2,
        "color_target": {"color_id": color["id"]}, "qty_requested": 2, "unit": "meter",
        "brief": "Cek registrasi warna & ketajaman garis"})
    ok(pf.status_code == 200, "permintaan proofing DENGAN desain berhasil dibuat",
       f"HTTP {pf.status_code} {pf.text[:130] if pf.status_code != 200 else pf.json()['number']}")
    proof = pf.json()
    _made["samples"].append(proof["id"])
    ok(proof.get("design_code") == "POC-DSG-001" and proof.get("design_version") == 2,
       "proofing menyimpan snapshot kode & versi desain (bisa ditelusuri ke artwork)")
    dl = requests.delete(f"{BASE}/design-gallery/{design['id']}", headers=H(admin), timeout=30)
    ok(dl.status_code == 400 and "dipakai" in dl.text.lower(),
       "desain yang sudah dipakai permintaan TIDAK bisa dihapus (jejak aman)", dl.text[:120])

    # ── TEST 10 ──────────────────────────────────────────────────────────────
    head("TEST 10 — Rilis ke produksi: produk AKHIRNYA boleh dijual")
    board = requests.get(f"{BASE}/rnd/lifecycle-board", headers=H(manager), timeout=30).json()
    ok(prod["id"] in {p["id"] for p in board.get("not_orderable", [])},
       "papan lifecycle menampilkan produk yang BELUM boleh dijual",
       f"{len(board.get('not_orderable', []))} produk belum rilis · "
       f"penegakan {board.get('enforcement')}")
    cat = requests.get(f"{BASE}/products", headers=H(sales), timeout=30,
                       params={"orderable_only": "true"}).json()
    ok(prod["id"] not in {p["id"] for p in cat},
       "katalog jual (orderable_only) TIDAK memuat produk yang belum rilis",
       f"{len(cat)} produk sah dijual")
    nore = requests.post(f"{BASE}/rnd/specs/{spec['id']}/release-product", headers=H(sales),
                         timeout=30, json={"reason": "coba rilis"})
    ok(nore.status_code == 403, "sales TIDAK boleh merilis produk ke produksi",
       f"HTTP {nore.status_code}")
    rel = requests.post(f"{BASE}/rnd/specs/{spec['id']}/release-product", headers=H(manager),
                        timeout=30, json={"reason": "Sample sudah ACC & kontrak harga terbit"})
    ok(rel.status_code == 200 and rel.json()["product"]["lifecycle"] == "produksi",
       "manager merilis → produk lifecycle `produksi`",
       f"HTTP {rel.status_code} · {rel.json().get('product', {}).get('lifecycle')}")
    cat2 = requests.get(f"{BASE}/products", headers=H(sales), timeout=30,
                        params={"orderable_only": "true"}).json()
    ok(prod["id"] in {p["id"] for p in cat2}, "produk kini MUNCUL di katalog jual")
    pr_now = requests.post(f"{BASE}/purchase-requisitions", headers=H(admin), timeout=60, json={
        "warehouse_id": wl[0]["id"], "reason": "POC setelah rilis",
        "items": [{"product_id": prod["id"], "quantity": 100, "unit": "meter",
                   "est_price": 42500}]})
    ok(pr_now.status_code == 200,
       "PR atas produk yang SUDAH dirilis BERHASIL (alur R&D → pengadaan tersambung)",
       f"HTTP {pr_now.status_code}")
    if pr_now.status_code == 200:
        _made["prs"].append(pr_now.json()["id"])

    # ── TEST 11 ──────────────────────────────────────────────────────────────
    head("TEST 11 — PS-19: ambil bahan sample = MUTASI STOK NYATA (satu angka stok)")
    def _pick_roll(db):
        return db.inventory_rolls.find_one(
            {"status": "available", "length_remaining": {"$gt": 5}}, {"_id": 0})
    roll = dbrun(_pick_roll)
    ok(bool(roll), "ada roll tersedia untuk diambil sebagai bahan sample",
       f"{(roll or {}).get('roll_no')} sisa {(roll or {}).get('length_remaining')}")
    before_len = float(roll["length_remaining"])
    _roll_backup[roll["id"]] = {"length_remaining": before_len, "status": roll["status"]}

    def _bal(db):
        return db.inventory_balances.find_one(
            {"product_id": roll["product_id"], "warehouse_id": roll["warehouse_id"],
             "owner_entity_id": roll["owner_entity_id"]}, {"_id": 0})
    bal_before = dbrun(_bal) or {}
    # Bahan diambil untuk permintaan yang MASIH berjalan (proofing) — bukan yang sudah diputus.
    iss = requests.post(f"{BASE}/rnd/samples/{proof['id']}/issue-material", headers=H(wh),
                        timeout=60, json={"roll_id": roll["id"], "qty": 3,
                                          "note": "Ambil bahan PFP untuk proofing"})
    ok(iss.status_code == 200, "warehouse mengeluarkan 3 unit bahan untuk sample",
       f"HTTP {iss.status_code} {iss.text[:150] if iss.status_code != 200 else ''}")
    if iss.status_code == 200:
        body = iss.json()
        _made["movements"].append(body["movement"]["id"])
        ok(body["movement"]["movement_type"] == "sample_issue"
           and float(body["movement"]["quantity"]) == -3,
           "mutasi stok bertipe `sample_issue` tercatat dengan qty NEGATIF",
           f"{body['movement']['movement_type']} {body['movement']['quantity']}")
        roll_after = dbrun(lambda db: db.inventory_rolls.find_one({"id": roll["id"]}, {"_id": 0}))
        ok(abs(float(roll_after["length_remaining"]) - (before_len - 3)) < 0.01,
           "sisa roll BERKURANG 3 (stok fisik & sistem tetap sama)",
           f"{before_len:g} → {roll_after['length_remaining']:g}")
        bal_after = dbrun(_bal) or {}
        ok(abs(float(bal_after.get("available_qty", 0))
               - (float(bal_before.get("available_qty", 0)) - 3)) < 0.01,
           "saldo stok gudang ikut berkurang (bukan koleksi stok sample kedua)",
           f"available {bal_before.get('available_qty')} → {bal_after.get('available_qty')}")
        mi_sum = round(sum(float(m.get("cost") or 0)
                           for m in body["sample"].get("material_issues") or []), 2)
        ok(abs(float(body["sample"]["cost_total"]) - mi_sum) < 0.01,
           "biaya bahan sample terbawa dari harga roll & terakumulasi ke biaya permintaan",
           f"biaya bahan Rp {body['issue']['cost']:,.0f} · total permintaan "
           f"Rp {body['sample']['cost_total']:,.0f}")
        # ── Bahan keluar gudang WAJIB berjurnal (Dr 6-7000 / Cr 1-1300) ─────────
        cost_iss = round(float(body["issue"]["cost"] or 0), 2)
        je = dbrun(lambda db: db.journal_entries.find_one(
            {"source_type": "rnd_sample_issue", "source_id": body["movement"]["id"]},
            {"_id": 0}))
        if je:
            _made["journals"].append(je["id"])
        ok(bool(je) and abs(float((je or {}).get("total_debit") or 0) - cost_iss) < 0.01,
           "jurnal beban sample terbit senilai bahan yang keluar (persediaan tidak "
           "turun tanpa beban)",
           f"{(je or {}).get('number')} Rp {float((je or {}).get('total_debit') or 0):,.0f} "
           f"vs bahan Rp {cost_iss:,.0f}")
        codes = {ln.get("account_code"): ln for ln in (je or {}).get("lines", [])}
        ok(float((codes.get("6-7000") or {}).get("debit") or 0) > 0
           and float((codes.get("1-1300") or {}).get("credit") or 0) > 0,
           "arah jurnal benar: Dr 6-7000 Beban Sample & Pengembangan / Cr 1-1300 Persediaan",
           f"Dr 6-7000 Rp {float((codes.get('6-7000') or {}).get('debit') or 0):,.0f} · "
           f"Cr 1-1300 Rp {float((codes.get('1-1300') or {}).get('credit') or 0):,.0f}")
        ok(bool(body["issue"].get("journal_number")),
           "nomor jurnal tersimpan di baris pengambilan bahan (bisa ditelusuri auditor)",
           str(body["issue"].get("journal_number")))
    movs = requests.get(f"{BASE}/inventory/movements", headers=H(wh), timeout=30).json()
    mlist = movs if isinstance(movs, list) else movs.get("items", [])
    ok(any(m.get("movement_type") == "sample_issue" for m in mlist),
       "warehouse melihat pengambilan bahan sample di daftar mutasi stok")

    # ── TEST 12 ──────────────────────────────────────────────────────────────
    head("TEST 12 — Jejak Dokumen (G-4): kontrak → sample → spesifikasi")
    if d.get("contract_id"):
        tr = requests.get(f"{BASE}/documents/trace/supplier_contract/{d['contract_id']}",
                          headers=H(manager), timeout=60)
        ok(tr.status_code == 200, "jejak dokumen bisa dimulai dari kontrak",
           f"HTTP {tr.status_code}")
        if tr.status_code == 200:
            body = tr.json()
            nodes = str(body)
            ok(sample["number"] in nodes,
               "rantai jejak menyebut permintaan sample asal harga", sample["number"])
            ok(spec["number"] in nodes,
               "rantai jejak sampai ke SPESIFIKASI R&D (hulu rantai)", spec["number"])
    tr2 = requests.get(f"{BASE}/documents/trace/md_sample/{sample['id']}",
                       headers=H(manager), timeout=60)
    ok(tr2.status_code == 200, "jejak dokumen juga bisa dimulai dari tengah rantai (sample)",
       f"HTTP {tr2.status_code}")

    # ── TEST 13 ──────────────────────────────────────────────────────────────
    head("TEST 13 — BUKTI-MERAH: invarian INV-RND benar-benar MEMERAH saat dilanggar")
    code0, out0 = integrity()
    ok(code0 == 0 and inv_state(out0, "INV-RND-01") == "PASS",
       "sebelum penyuntikan: semua INV-RND HIJAU",
       f"01={inv_state(out0, 'INV-RND-01')} 02={inv_state(out0, 'INV-RND-02')} "
       f"04={inv_state(out0, 'INV-RND-04')} 05={inv_state(out0, 'INV-RND-05')}")

    # (a) INV-RND-01 — hapus alasan keputusan
    dbrun(lambda db: db.md_samples.update_one({"id": sample["id"]},
                                             {"$set": {"decision.reason_code": ""}}))
    _, outa = integrity("rnd")
    ok(inv_state(outa, "INV-RND-01") == "FAIL",
       "INV-RND-01 MEMERAH saat keputusan sample kehilangan alasan")
    dbrun(lambda db: db.md_samples.update_one(
        {"id": sample["id"]}, {"$set": {"decision.reason_code": "warna_paling_dekat"}}))

    # (b) INV-RND-02 — hapus lampiran round yang sudah ditutup
    def _strip(db):
        return db.md_samples.update_one({"id": sample["id"], "rounds.id": r_a2["id"]},
                                       {"$set": {"rounds.$.attachments": []}})
    saved_files = dbrun(lambda db: db.md_samples.find_one(
        {"id": sample["id"]}, {"_id": 0, "rounds": 1}))
    files_a2 = next(r for r in saved_files["rounds"] if r["id"] == r_a2["id"])["attachments"]
    dbrun(_strip)
    _, outb = integrity("rnd")
    ok(inv_state(outb, "INV-RND-02") == "FAIL",
       "INV-RND-02 MEMERAH saat round tertutup kehilangan lampiran bukti")
    dbrun(lambda db: db.md_samples.update_one(
        {"id": sample["id"], "rounds.id": r_a2["id"]},
        {"$set": {"rounds.$.attachments": files_a2}}))

    # (c) INV-RND-04 — produk yang DIPAKAI dokumen dikembalikan ke tahap belum sah
    dbrun(lambda db: db.products.update_one({"id": prod["id"]},
                                           {"$set": {"lifecycle": "labdip"}}))
    _, outc = integrity("rnd")
    ok(inv_state(outc, "INV-RND-04") == "FAIL",
       "INV-RND-04 MEMERAH saat produk yang sudah dipakai PR dikembalikan ke tahap labdip")
    dbrun(lambda db: db.products.update_one({"id": prod["id"]},
                                           {"$set": {"lifecycle": "produksi"}}))

    # (d) INV-RND-05 — hapus mutasi stok pengambilan bahan
    mov_doc = dbrun(lambda db: db.inventory_movements.find_one(
        {"id": _made["movements"][0]}, {"_id": 0})) if _made["movements"] else None
    if mov_doc:
        dbrun(lambda db: db.inventory_movements.delete_one({"id": mov_doc["id"]}))
        _, outd = integrity("rnd")
        ok(inv_state(outd, "INV-RND-05") == "FAIL",
           "INV-RND-05 MEMERAH saat mutasi stok pengambilan bahan sample dihapus "
           "(stok sample ≠ stok gudang)")
        dbrun(lambda db: db.inventory_movements.insert_one(dict(mov_doc)))

    # (e) INV-RND-07 — hapus jurnal beban sample (persediaan turun tanpa beban di GL)
    je_doc = dbrun(lambda db: db.journal_entries.find_one(
        {"id": _made["journals"][0]}, {"_id": 0})) if _made["journals"] else None
    if je_doc:
        dbrun(lambda db: db.journal_entries.delete_one({"id": je_doc["id"]}))
        _, oute = integrity("rnd")
        ok(inv_state(oute, "INV-RND-07") == "FAIL",
           "INV-RND-07 MEMERAH saat jurnal beban bahan sample dihapus "
           "(nilai persediaan turun tanpa beban di GL)")
        dbrun(lambda db: db.journal_entries.insert_one(dict(je_doc)))
    code1, out1 = integrity()
    ok(code1 == 0, "setelah semua dipulihkan: invarian global HIJAU kembali",
       [ln for ln in out1.splitlines() if "PASS " in ln and "|" in ln][-1].strip()
       if [ln for ln in out1.splitlines() if "PASS " in ln and "|" in ln] else "")

    # ── TEST 14 ──────────────────────────────────────────────────────────────
    head("TEST 14 — Laporan kinerja R&D & pembersihan artefak POC (nol residu)")
    rep = requests.get(f"{BASE}/rnd/reports/performer", headers=H(manager), timeout=30)
    ok(rep.status_code == 200 and rep.json()["count"] >= 1,
       "laporan kinerja pelaksana R&D terbentuk dari data nyata",
       f"{rep.json().get('count')} pelaksana · "
       f"{rep.json().get('stats', {}).get('overdue_rounds')} round terlambat")

    for k, v in original.items():
        cfg_set(admin, k, v, reason="pulihkan setelah POC FASE F")

    async def purge(db):
        n = 0
        spec_ids, smp_ids = _made["specs"], _made["samples"]
        pids, cids = _made["products"], _made["contracts"]
        for coll, q in (
            ("md_specs", {"id": {"$in": spec_ids}}),
            ("md_samples", {"id": {"$in": smp_ids}}),
            ("products", {"id": {"$in": pids}}),
            ("supplier_contracts", {"id": {"$in": cids}}),
            ("supplier_items", {"id": {"$in": _made["items"]}}),
            ("design_gallery", {"id": {"$in": _made["designs"]}}),
            ("purchase_requisitions", {"id": {"$in": _made["prs"]}}),
            ("inventory_movements", {"id": {"$in": _made["movements"]}}),
            ("journal_entries", {"id": {"$in": _made["journals"]}}),
        ):
            res = await db[coll].delete_many(q)
            n += res.deleted_count
        # pulihkan roll + saldo stok yang dipakai POC
        for rid, back in _roll_backup.items():
            await db.inventory_rolls.update_one({"id": rid}, {"$set": back})
        if _roll_backup:
            sys.path.insert(0, "/app/backend")
            from services import roll_service  # noqa: WPS433
            for rid in _roll_backup:
                rr = await db.inventory_rolls.find_one({"id": rid}, {"_id": 0})
                if rr:
                    await roll_service.rebuild_balance(rr["product_id"], rr["warehouse_id"],
                                                       rr["owner_entity_id"])
        all_ids = spec_ids + smp_ids + pids + cids + _made["items"] + _made["designs"] \
            + _made["prs"]
        await db.audit_logs.delete_many({"entity_id": {"$in": all_ids}})
        await db.config_values.delete_many({"reason": {"$regex": "POC FASE F"}})
        await db.config_values.delete_many({"reason": "pulihkan setelah POC FASE F"})
        await db.number_sequences.delete_many({"doc_type": {"$in": ["SPEC", "SMP"]}})
        return n

    purged = dbrun(purge)
    ok(purged >= len(_made["specs"]) + len(_made["samples"]),
       f"{purged} artefak POC dihapus dari database")
    code9, out9 = integrity()
    ok(code9 == 0, "invarian global tetap HIJAU setelah pembersihan (nol residu)",
       [ln for ln in out9.splitlines() if "PASS " in ln and "|" in ln][-1].strip()
       if [ln for ln in out9.splitlines() if "PASS " in ln and "|" in ln] else "")

    head("RINGKASAN")
    total = _stats["pass"] + _stats["fail"]
    print(f"  PASS {_stats['pass']} / FAIL {_stats['fail']}  (total {total})")
    if _stats["fail"] == 0:
        print(f"\n{G}{B}✓ POC FASE F HIJAU 100% — alur R&D (spesifikasi → labdip/proofing → "
              f"kontrak) NYATA & barang belum sah tidak bisa dijual.{X}")
        return 0
    print(f"\n{R}{B}✗ POC FASE F GAGAL — {_stats['fail']} pemeriksaan merah.{X}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
