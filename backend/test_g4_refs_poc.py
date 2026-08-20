#!/usr/bin/env python3
"""POC FASE G-4 — **RELASI DOKUMEN, NOMOR REFERENSI & TANDA TANGAN**.

Masalah nyata pemilik yang harus dibuktikan selesai:
*"SO customer pending → KN harus PO ke supplier → banyak surat lahir tapi saling tidak
mereferensikan → tracking & penelusuran retur susah."*

Yang dibuktikan lewat HTTP nyata (bukan unit test):

  1. Peta jenis dokumen + kosakata relasi tersedia untuk UI; RBAC backfill dijaga.
  2. Dokumen turunan yang LAHIR lewat aplikasi otomatis menaut ke induknya — DUA ARAH
     (PO→GRN, PO→Tagihan Supplier), sehingga bisa ditelusuri dari sisi mana pun.
  3. Sakelar `docref.autolink_enabled` benar-benar berpengaruh (bukan tombol palsu).
  4. **Jejak Dokumen bisa dimulai dari dokumen mana pun** — termasuk dari tengah rantai
     (Tagihan Supplier, Kwitansi) — dan kedalamannya configurable.
  5. Dokumen CETAK menyebut nomor referensinya (blok "Referensi Dokumen") + QR ke
     halaman Jejak Dokumen; keduanya bisa dimatikan admin lewat Pusat Pengaturan.
  6. Backfill data lama IDEMPOTEN: dry-run tidak mengubah apa pun, apply aman diulang.
  7. Tanda tangan elektronik: bernama (nama + jabatan + waktu + hash), statusnya
     terlihat di daftar dokumen, dan verifikasi publik (QR) bekerja tanpa login.
  8. **BUKTI-MERAH**: invarian INV-REF-01 & INV-REF-02 benar-benar MEMERAH saat
     pelanggaran disuntik, lalu kembali hijau setelah dipulihkan.
  9. Seluruh artefak POC dibersihkan → nol residu, invarian global tetap hijau.

Jalankan:  python backend/test_g4_refs_poc.py
"""
import asyncio
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
_made = {"pos": [], "bills": [], "tasks": [], "signatures": [], "requests": []}


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


def cfg_set(tok: str, key: str, value, reason: str = "POC G-4") -> bool:
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


def make_po(tok: str, qty: float = 5.0, label: str = "POC G-4") -> dict:
    """PO nyata lewat API (supplier & gudang dari seed). Nilai kecil → tanpa approval."""
    prods = requests.get(f"{BASE}/products", headers=H(tok), timeout=30).json()
    plist = prods if isinstance(prods, list) else prods.get("items", [])
    sups = requests.get(f"{BASE}/suppliers", headers=H(tok), timeout=30).json()
    slist = sups if isinstance(sups, list) else sups.get("items", [])
    # FASE E-7 (E7a) mendaftarkan setiap badan usaha grup sebagai baris PEMASOK
    # bertipe `entity` supaya pembelian antar-PT bisa dideteksi. Sejak itu
    # `slist[0]` bisa jatuh ke "CV Kanda Suka" — dan pagar E7a BENAR menolak PO
    # biasa ke badan usaha sendiri (409, menuntun ke layar Antar Entitas). Jadi POC
    # ini harus memilih pemasok LUAR secara eksplisit; memakai indeks 0 membuat
    # hasil uji bergantung pada urutan data, bukan pada perilaku yang diuji.
    slist = [s for s in slist if (s.get("partner_kind") or "external") != "entity"]
    if not slist:
        raise SystemExit("tidak ada pemasok luar (non-entitas grup) di data demo")
    whs = requests.get(f"{BASE}/warehouses", headers=H(tok), timeout=30).json()
    wlist = whs if isinstance(whs, list) else whs.get("items", [])
    p, s, w = plist[0], slist[0], wlist[0]
    body = {"supplier_id": s["id"], "supplier_name": s.get("name", ""),
            "warehouse_id": w["id"], "notes": label,
            "items": [{"product_id": p["id"], "quantity": qty,
                       "unit": p.get("base_unit") or "meter", "price": 50000,
                       "expected_grade": "A"}]}
    r = requests.post(f"{BASE}/purchase-orders", headers=H(tok), json=body, timeout=60)
    if r.status_code not in (200, 201):
        print(f"{R}gagal membuat PO: {r.status_code} {r.text[:300]}{X}")
        sys.exit(1)
    po = r.json()
    _made["pos"].append(po["id"])
    return po


def tasks_of_po(tok: str, po_id: str) -> list:
    r = requests.get(f"{BASE}/wms/tasks", headers=H(tok), params={"flow_type": "inbound"}, timeout=40)
    rows = r.json()
    rows = rows if isinstance(rows, list) else rows.get("items", [])
    return [t for t in rows if t.get("po_id") == po_id]


def refs_of(tok: str, doc_type: str, doc_id: str) -> list:
    r = requests.get(f"{BASE}/documents/refs/{doc_type}/{doc_id}", headers=H(tok), timeout=30)
    return r.json().get("refs", []) if r.status_code == 200 else []


def has_ref(rows: list, rel: str, doc_type: str, doc_id: str = "") -> bool:
    return any(x.get("rel") == rel and x.get("doc_type") == doc_type
               and (not doc_id or x.get("doc_id") == doc_id) for x in rows)


def integrity(only: str = "") -> tuple:
    """Jalankan gate invarian; return (exit_code, output).

    `only` = lapisan relevan (mis. `docref`) untuk blok BUKTI-MERAH yang memang
    hanya menguji keluarga INV-REF. Klaim GLOBAL tetap eksekusi LENGKAP.
    """
    cmd = [sys.executable, "/app/scripts/verify_data_integrity.py"]
    if only:
        cmd.append(f"--only={only}")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return proc.returncode, proc.stdout + proc.stderr


def inv_state(out: str, inv: str) -> str:
    """Ambil status satu invarian dari keluaran gate: PASS / FAIL / ?"""
    for ln in out.splitlines():
        if inv in ln:
            if "[PASS]" in ln:
                return "PASS"
            if "[FAIL]" in ln:
                return "FAIL"
    return "?"


async def _db():
    """Klien Mongo BARU untuk setiap pemanggilan.

    Penting: `backend/db.py` membuat satu klien Motor yang terikat pada event-loop
    pertama. POC memanggil `asyncio.run()` beberapa kali (loop baru setiap kali),
    sehingga memakai klien global menghasilkan `RuntimeError: Event loop is closed`.
    """
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli[os.environ.get("DB_NAME", "test_database")], cli


def dbrun(fn):
    """Jalankan satu fungsi async yang menerima `db` pada loop & klien sendiri."""
    async def _wrap():
        db, cli = await _db()
        try:
            return await fn(db)
        finally:
            cli.close()
    return asyncio.run(_wrap())


def run(coro):
    return asyncio.run(coro)


def main() -> int:  # noqa: C901 — POC memang panjang & berurutan
    tok = {k: login(k) for k in USERS}
    admin, manager, sales, warehouse = tok["admin"], tok["manager"], tok["sales"], tok["warehouse"]

    keys = ["docref.autolink_enabled", "docref.trace_max_depth", "docref.require_parent",
            "docref.show_in_pdf", "docref.qr_in_pdf", "docref.pdf_max_refs"]
    original = {k: cfg_get(admin, k) for k in keys}

    # ── TEST 1 ───────────────────────────────────────────────────────────────
    head("TEST 1 — Peta jenis dokumen, kosakata relasi, dan RBAC")
    r = requests.get(f"{BASE}/documents/ref-types", headers=H(admin), timeout=30)
    data = r.json() if r.status_code == 200 else {}
    types = data.get("types", [])
    ok(r.status_code == 200 and len(types) >= 18,
       f"peta relasi memuat {len(types)} jenis dokumen (SO/PO/GRN/Faktur/Kwitansi/Retur/…)")
    ok(any(t["doc_type"] == "vendor_bill" and t["needs_parent"] for t in types),
       "tagihan supplier ditandai WAJIB punya induk (bahan INV-REF-01)")
    ok(len(data.get("rel_labels", {})) >= 12,
       f"kosakata relasi berlabel Bahasa Indonesia ({len(data.get('rel_labels', {}))} relasi)")
    ok(requests.post(f"{BASE}/documents/refs/backfill?dry_run=true",
                     headers=H(sales), timeout=60).status_code == 403,
       "sales DITOLAK menjalankan backfill relasi (403)")
    ok(requests.get(f"{BASE}/documents/trace-search", headers=H(warehouse),
                    params={"q": "SO-00"}, timeout=30).status_code == 200,
       "warehouse tetap boleh MENCARI & menelusuri dokumen (read-only)")

    # ── TEST 2 ───────────────────────────────────────────────────────────────
    head("TEST 2 — Dokumen turunan yang LAHIR lewat aplikasi menaut otomatis (dua arah)")
    po = make_po(admin, qty=5.0)
    po_id, po_no = po["id"], po.get("po_number")
    tasks = tasks_of_po(admin, po_id)
    _made["tasks"] += [t["id"] for t in tasks]
    ok(len(tasks) >= 1, f"PO {po_no} dibuat + {len(tasks)} tugas penerimaan (GRN) terbentuk")

    grn_refs = refs_of(admin, "grn", tasks[0]["id"]) if tasks else []
    ok(has_ref(grn_refs, "parent", "purchase_order", po_id),
       "GRN menunjuk PO induknya", f"{len(grn_refs)} referensi")
    po_refs = refs_of(admin, "purchase_order", po_id)
    ok(has_ref(po_refs, "child", "grn", tasks[0]["id"] if tasks else ""),
       "PO menunjuk balik ke GRN-nya (arah kedua)", f"{len(po_refs)} referensi")

    bill_body = {"po_id": po_id, "match_mode": "ordered", "supplier_invoice_no": "POC-G4-001",
                 "items": [{"product_id": po["items"][0]["product_id"],
                            "billed_qty": 5.0, "price": 50000}],
                 "notes": "POC G-4", "submit_now": False}
    rb = requests.post(f"{BASE}/vendor-bills", headers=H(admin), json=bill_body, timeout=60)
    bill = rb.json() if rb.status_code in (200, 201) else {}
    if bill.get("id"):
        _made["bills"].append(bill["id"])
    ok(bool(bill.get("id")), f"Tagihan supplier dibuat: {bill.get('bill_number', '-')}",
       "" if bill.get("id") else rb.text[:200])
    b_refs = refs_of(admin, "vendor_bill", bill.get("id", "x"))
    ok(has_ref(b_refs, "parent", "purchase_order", po_id),
       "Tagihan supplier menunjuk PO-nya (3-way match bisa ditelusuri)")
    po_refs2 = refs_of(admin, "purchase_order", po_id)
    ok(has_ref(po_refs2, "child", "vendor_bill", bill.get("id", "")),
       "PO menunjuk balik ke tagihan supplier")

    # ── TEST 3 ───────────────────────────────────────────────────────────────
    head("TEST 3 — Sakelar `docref.autolink_enabled` BENAR-BENAR berpengaruh")
    ok(cfg_set(admin, "docref.autolink_enabled", False), "admin mematikan penautan otomatis")
    po_off = make_po(admin, qty=4.0, label="POC G-4 autolink off")
    tasks_off = tasks_of_po(admin, po_off["id"])
    _made["tasks"] += [t["id"] for t in tasks_off]
    off_refs = refs_of(admin, "grn", tasks_off[0]["id"]) if tasks_off else []
    ok(len(off_refs) == 0,
       "dengan sakelar MATI, dokumen baru TIDAK menaut (konfigurasi nyata, bukan hiasan)",
       f"{len(off_refs)} referensi")
    ok(cfg_set(admin, "docref.autolink_enabled", True), "sakelar dinyalakan kembali")
    po_on = make_po(admin, qty=3.0, label="POC G-4 autolink on")
    tasks_on = tasks_of_po(admin, po_on["id"])
    _made["tasks"] += [t["id"] for t in tasks_on]
    on_refs = refs_of(admin, "grn", tasks_on[0]["id"]) if tasks_on else []
    ok(has_ref(on_refs, "parent", "purchase_order", po_on["id"]),
       "sakelar HIDUP → dokumen baru kembali menaut otomatis")

    # ── TEST 4 ───────────────────────────────────────────────────────────────
    head("TEST 4 — Jejak Dokumen bisa dimulai dari dokumen MANA PUN")
    rt = requests.get(f"{BASE}/documents/trace/vendor_bill/{bill.get('id', 'x')}",
                      headers=H(admin), timeout=40)
    tr = rt.json() if rt.status_code == 200 else {}
    node_types = {n["doc_type"] for n in tr.get("nodes", [])}
    ok(rt.status_code == 200 and tr.get("anchor", {}).get("doc_type") == "vendor_bill",
       "penelusuran dimulai dari TENGAH rantai (tagihan supplier) — bukan hanya dari SO/PO")
    ok({"purchase_order", "grn"} <= node_types,
       "dari tagihan supplier terlihat PO dan penerimaan barangnya",
       f"{len(tr.get('nodes', []))} dokumen · {len(tr.get('edges', []))} relasi")

    # data LAMA (hasil seed + backfill) juga tertelusur dari kwitansi
    recs = requests.get(f"{BASE}/ar-receipts", headers=H(admin), timeout=40).json()
    rlist = recs if isinstance(recs, list) else recs.get("items", [])
    rec = rlist[0] if rlist else None
    deep_types = set()
    if rec:
        r4 = requests.get(f"{BASE}/documents/trace/ar_receipt/{rec['id']}", headers=H(admin),
                          timeout=40).json()
        deep_types = {n["doc_type"] for n in r4.get("nodes", [])}
        ok("sales_order" in deep_types and len(deep_types) >= 3,
           f"dari Kwitansi {rec.get('number')} rantai lama ikut tertelusur",
           " · ".join(sorted(deep_types)))
        # kedalaman configurable
        ok(cfg_set(admin, "docref.trace_max_depth", 1), "admin membatasi kedalaman jejak = 1")
        shallow = requests.get(f"{BASE}/documents/trace/ar_receipt/{rec['id']}",
                               headers=H(admin), timeout=40).json()
        ok(len(shallow.get("nodes", [])) < len(r4.get("nodes", [])),
           "kedalaman 1 memang memangkas graf (aturan dibaca dari registry, bukan hardcode)",
           f"{len(shallow.get('nodes', []))} vs {len(r4.get('nodes', []))} dokumen")
        cfg_set(admin, "docref.trace_max_depth", original["docref.trace_max_depth"] or 4)
    else:
        ok(False, "tidak ada kwitansi di seed untuk uji rantai lama")

    srch = requests.get(f"{BASE}/documents/trace-search", headers=H(admin),
                        params={"q": "SO-000"}, timeout=30).json()
    ok(isinstance(srch, list) and len(srch) >= 1,
       f"pencarian dokumen lintas jenis mengembalikan {len(srch) if isinstance(srch, list) else 0} hasil")

    # ── TEST 5 ───────────────────────────────────────────────────────────────
    head("TEST 5 — Dokumen CETAK menyebut referensinya + QR Jejak Dokumen")
    sos = requests.get(f"{BASE}/sales-orders", headers=H(admin), timeout=40).json()
    solist = sos if isinstance(sos, list) else sos.get("items", [])
    so_with_refs = None
    for s in solist:
        if refs_of(admin, "sales_order", s["id"]):
            so_with_refs = s
            break
    ok(bool(so_with_refs), "ada pesanan ber-referensi untuk diuji cetak",
       so_with_refs.get("number") if so_with_refs else "")

    def render_html(doc_type: str, sid: str) -> str:
        rr = requests.get(f"{BASE}/pdf/render/{doc_type}/{sid}", headers={
            **H(admin), "Accept": "text/html",
            "Origin": "https://kn.poc.test"}, params={"format": "html"}, timeout=90)
        return rr.text if rr.status_code == 200 else ""

    BLOCK = '<div class="refs">'   # penanda blok nyata (kelas CSS selalu ada di <style>)
    html = render_html("invoice", so_with_refs["id"]) if so_with_refs else ""
    ok(BLOCK in html and "Merujuk:" in html,
       "PDF/HTML memuat blok 'Referensi Dokumen' berisi nomor surat terkait")
    ok("jejak-dokumen" in html or "data:image/png;base64" in html,
       "QR menuju halaman Jejak Dokumen ikut tercetak")

    ok(cfg_set(admin, "docref.qr_in_pdf", False), "admin mematikan QR pada dokumen cetak")
    html_noqr = render_html("invoice", so_with_refs["id"]) if so_with_refs else ""
    ok(BLOCK in html_noqr and "Scan QR" not in html_noqr,
       "QR hilang tetapi nomor referensi TETAP tercetak (dua sakelar terpisah)")
    cfg_set(admin, "docref.qr_in_pdf", True)

    ok(cfg_set(admin, "docref.show_in_pdf", False), "admin mematikan blok referensi")
    html_off = render_html("invoice", so_with_refs["id"]) if so_with_refs else ""
    ok(BLOCK not in html_off and len(html_off) > 500,
       "blok referensi benar-benar hilang dari dokumen cetak (dokumen tetap tercetak)")
    cfg_set(admin, "docref.show_in_pdf", True)

    # PDF biner tetap terbentuk (mesin PDF tidak rusak oleh blok baru)
    rpdf = requests.get(f"{BASE}/pdf/render/invoice/{so_with_refs['id']}", headers=H(admin),
                        params={"format": "pdf"}, timeout=120)
    ok(rpdf.status_code == 200 and rpdf.content[:4] == b"%PDF",
       f"PDF asli tetap terbentuk ({len(rpdf.content) // 1024} KB)")

    # ── TEST 6 ───────────────────────────────────────────────────────────────
    head("TEST 6 — Backfill data lama IDEMPOTEN (dry-run tidak mengubah apa pun)")
    d0 = requests.post(f"{BASE}/documents/refs/backfill?dry_run=false", headers=H(admin),
                       timeout=180).json()
    d1 = requests.post(f"{BASE}/documents/refs/backfill?dry_run=true", headers=H(admin),
                       timeout=180).json()
    ok(d1.get("would_add", -1) == 0,
       f"sesudah apply, dry-run bersih: 0 relasi tertinggal dari {d1.get('candidates')} kandidat",
       f"apply menulis {d0.get('written')} tautan (termasuk PO yang dibuat saat sakelar mati)")

    async def strip_bill_refs(db):
        await db.vendor_bills.update_one({"id": bill["id"]}, {"$set": {"refs": []}})
        await db.purchase_orders.update_one(
            {"id": po_id}, {"$pull": {"refs": {"doc_id": bill["id"]}}})
    dbrun(strip_bill_refs)
    d2 = requests.post(f"{BASE}/documents/refs/backfill?dry_run=true", headers=H(admin),
                       timeout=180).json()
    ok(d2.get("would_add", 0) >= 1, "setelah relasi dihapus, dry-run melaporkan kekurangan",
       f"would_add={d2.get('would_add')}")
    d3 = requests.post(f"{BASE}/documents/refs/backfill?dry_run=false", headers=H(admin),
                       timeout=180).json()
    ok(d3.get("written", 0) >= 1, f"apply memulihkan {d3.get('written')} tautan")
    b_refs2 = refs_of(admin, "vendor_bill", bill["id"])
    ok(has_ref(b_refs2, "parent", "purchase_order", po_id), "relasi tagihan↔PO kembali utuh")
    d4 = requests.post(f"{BASE}/documents/refs/backfill?dry_run=true", headers=H(admin),
                       timeout=180).json()
    ok(d4.get("would_add", -1) == 0, "apply kedua tidak menduplikasi (idempotent)")

    # ── TEST 7 ───────────────────────────────────────────────────────────────
    head("TEST 7 — Tanda tangan elektronik bernama + status di daftar dokumen")
    lst = requests.get(f"{BASE}/pdf/documents/sales_order", headers=H(admin),
                       params={"limit": 200}, timeout=60).json()
    row = next((d for d in lst.get("documents", []) if d["source_id"] == so_with_refs["id"]), None)
    ok(bool(row) and row.get("esignable") is True and row.get("signed") is False,
       "daftar dokumen menampilkan status tanda tangan (belum ditandatangani)")

    rq = requests.post(f"{BASE}/esign/request", headers=H(admin), timeout=60, json={
        "doc_type": "sales_order", "source_id": so_with_refs["id"],
        "signer_name": "Budi Santoso", "signer_role": "Direktur",
        "signer_contact": "0811000111"})
    req = rq.json() if rq.status_code == 200 else {}
    if req.get("request_id"):
        _made["requests"].append(req["request_id"])
    otp = req.get("reveal_code") or req.get("simulated") or ""
    if isinstance(otp, dict):
        otp = otp.get("code", "")
    ok(bool(req.get("request_id")), "permintaan tanda tangan dibuat (kanal simulasi)",
       req.get("channel", ""))
    signed = {}
    if req.get("request_id") and otp:
        rv = requests.post(f"{BASE}/esign/verify", headers=H(admin), timeout=60, json={
            "request_id": req["request_id"], "otp": str(otp),
            "signature_b64": "iVBORw0KGgoAAAANSUhEUg=="})
        signed = rv.json() if rv.status_code == 200 else {}
    ok(bool(signed.get("verification_code")) and len(signed.get("doc_hash", "")) == 64,
       "dokumen ditandatangani: kode verifikasi + hash SHA-256 tersimpan",
       signed.get("verification_code", ""))
    if signed.get("verification_code"):
        _made["signatures"].append(signed["verification_code"])

    lst2 = requests.get(f"{BASE}/pdf/documents/sales_order", headers=H(admin),
                        params={"limit": 200}, timeout=60).json()
    row2 = next((d for d in lst2.get("documents", []) if d["source_id"] == so_with_refs["id"]), None)
    ok(bool(row2) and row2.get("signed") is True and row2.get("sign_count", 0) >= 1,
       "status di daftar dokumen berubah menjadi SUDAH ditandatangani",
       f"kode {row2.get('verification_code') if row2 else '-'}")

    pv = requests.get(f"{BASE}/esign/verify/{signed.get('verification_code', 'X')}", timeout=30)
    pj = pv.json() if pv.status_code == 200 else {}
    ok(pj.get("valid") is True and pj.get("signers"),
       "verifikasi PUBLIK (tanpa login) mengembalikan dokumen + daftar penandatangan",
       f"{pj.get('doc_label')} {pj.get('number')}")
    ok(any(s.get("role") == "Direktur" and s.get("signed_at") for s in pj.get("signers", [])),
       "blok tanda tangan menyebut JABATAN + WAKTU (bukan sekadar nama)")

    html_sig = render_html("sales_order", so_with_refs["id"])
    ok("DOKUMEN TERVERIFIKASI ELEKTRONIK" in html_sig and "Direktur" in html_sig,
       "dokumen cetak menampilkan blok tanda tangan bernama + jabatan")

    # ── TEST 8 ───────────────────────────────────────────────────────────────
    head("TEST 8 — BUKTI-MERAH: invarian INV-REF benar-benar bisa MEMERAH")
    code0, out0 = integrity()
    ok(code0 == 0 and inv_state(out0, "INV-REF-01") == "PASS"
       and inv_state(out0, "INV-REF-02") == "PASS",
       "keadaan awal: INV-REF-01 & INV-REF-02 HIJAU")

    async def orphan_bill(db):
        await db.vendor_bills.update_one({"id": bill["id"]}, {"$set": {"refs": []}})
        await db.purchase_orders.update_one(
            {"id": po_id}, {"$pull": {"refs": {"doc_id": bill["id"]}}})
    dbrun(orphan_bill)
    code1, out1 = integrity("docref")
    ok(inv_state(out1, "INV-REF-01") == "FAIL" and code1 != 0,
       "tagihan supplier dijadikan YATIM → INV-REF-01 MERAH (gate memblokir)")
    requests.post(f"{BASE}/documents/refs/backfill?dry_run=false", headers=H(admin), timeout=180)
    code2, out2 = integrity("docref")
    ok(inv_state(out2, "INV-REF-01") == "PASS", "setelah dipulihkan → INV-REF-01 kembali HIJAU")

    async def one_way(db):
        await db.purchase_orders.update_one({"id": po_id}, {"$push": {"refs": {
            "rel": "child", "doc_type": "vendor_bill", "doc_id": _made["bills"][0],
            "doc_number": "PALSU-SATU-ARAH", "note": "suntikan bukti-merah", "at": "poc"}}})
        await db.vendor_bills.update_one(
            {"id": _made["bills"][0]}, {"$pull": {"refs": {"doc_id": po_id}}})
    dbrun(one_way)
    code3, out3 = integrity("docref")
    ok(inv_state(out3, "INV-REF-02") == "FAIL",
       "relasi dibuat SATU ARAH → INV-REF-02 MERAH (jejak tidak bisa dibaca balik)")

    async def heal(db):
        await db.purchase_orders.update_one(
            {"id": po_id}, {"$pull": {"refs": {"doc_number": "PALSU-SATU-ARAH"}}})
    dbrun(heal)
    requests.post(f"{BASE}/documents/refs/backfill?dry_run=false", headers=H(admin), timeout=180)
    code4, out4 = integrity("docref")
    ok(inv_state(out4, "INV-REF-02") == "PASS" and inv_state(out4, "INV-REF-03") == "PASS",
       "dipulihkan → INV-REF-02 & INV-REF-03 HIJAU (invarian bukan hiasan)")

    # ── CLEANUP ──────────────────────────────────────────────────────────────
    head("CLEANUP — kembalikan lingkungan ke keadaan semula (nol residu)")
    for k, v in original.items():
        if v is not None:
            cfg_set(admin, k, v, reason="pulihkan setelah POC G-4")
    ok(all(cfg_get(admin, k) == v for k, v in original.items() if v is not None),
       "seluruh konfigurasi dokumen dipulihkan ke nilai semula")

    async def purge(db):
        n = 0
        ids = _made["pos"]
        # lepas jejak ke dokumen POC dari dokumen manapun (dua arah) sebelum menghapus
        for coll in ("purchase_orders", "vendor_bills", "wms_tasks", "sales_orders",
                     "purchase_requisitions", "makloon_orders"):
            await db[coll].update_many(
                {}, {"$pull": {"refs": {"doc_id": {"$in": ids + _made["bills"] + _made["tasks"]}}}})
        for coll, key in (("vendor_bills", _made["bills"]), ("wms_tasks", _made["tasks"]),
                          ("purchase_orders", ids)):
            res = await db[coll].delete_many({"id": {"$in": key}})
            n += res.deleted_count
        await db.journal_entries.delete_many({"source_id": {"$in": ids + _made["bills"]}})
        # Penerimaan barang menulis mutasi ber-`source_document` = nomor/id PO.
        await db.inventory_movements.delete_many({"source_document": {"$in": ids}})
        await db.inventory_movements.delete_many({"reference_id": {"$in": ids}})
        await db.document_signatures.delete_many(
            {"verification_code": {"$in": _made["signatures"]}})
        await db.esign_requests.delete_many({"id": {"$in": _made["requests"]}})
        await db.audit_logs.delete_many({"entity_id": {"$in": ids + _made["bills"]}})
        await db.audit_logs.delete_many({"action": "doc_refs_backfill"})
        await db.notifications.delete_many({"action_id": {"$in": ids}})
        await db.config_values.delete_many({"reason": {"$regex": "POC G-4"}})
        await db.config_values.delete_many({"reason": "pulihkan setelah POC G-4"})
        return n

    purged = dbrun(purge)
    ok(purged >= len(_made["pos"]), f"{purged} artefak POC dihapus dari database")

    code5, out5 = integrity()
    ok(code5 == 0, "invarian global tetap HIJAU setelah pembersihan (nol residu)",
       [ln for ln in out5.splitlines() if "PASS " in ln and "|" in ln][-1:] and
       [ln for ln in out5.splitlines() if "PASS " in ln and "|" in ln][-1].strip() or "")

    head("RINGKASAN")
    total = _stats["pass"] + _stats["fail"]
    print(f"  PASS {_stats['pass']} / FAIL {_stats['fail']}  (total {total})")
    if _stats["fail"] == 0:
        print(f"\n{G}{B}✓ POC FASE G-4 HIJAU 100% — relasi dokumen, referensi cetak, "
              f"dan tanda tangan terbukti.{X}")
        return 0
    print(f"\n{R}{B}✗ POC FASE G-4 GAGAL — {_stats['fail']} pemeriksaan merah.{X}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
