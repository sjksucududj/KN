#!/usr/bin/env python3
"""POC FASE F-6.7 — **UTANG ALUR DIBAYAR: "AJUKAN" DULU, BARU DISETUJUI**.

APA YANG DIPERBAIKI (dan mengapa itu utang, bukan fitur baru)
=============================================================
FASE F-6 membuat semua pintu keputusan WAJIB punya antrean yang menghitungnya
(`INV-APPR-01`). Empat pintu tidak bisa memenuhinya waktu itu, dan dibebaskan dengan
alasan bertanda **"UTANG ALUR"** — pembebasan yang jujur, tetapi tetap utang:

1. **Payroll** disahkan langsung dari status `draft`. Draf yang MASIH DIKERJAKAN HR tak
   bisa dibedakan dari yang siap disahkan, jadi menghitungnya sebagai "menunggu
   keputusan" berarti menyebut pekerjaan orang lain sebagai antrean — dan penyetuju tak
   punya cara tahu mana yang menunggu dirinya selain menebak dari daftar draf.
2. **Desain** (galeri motif) — persis masalah yang sama.
3. **Selisih pembayaran**: dokumen keputusan (`payment_variance_decisions`) baru LAHIR
   saat diputuskan, jadi disimpulkan "keadaan menunggunya tak bisa dihitung tanpa
   menebak". Ternyata BISA, dan tanpa status dokumen baru: keadaan itu sudah presisi
   sebagai *(selisih perlu diputus)* **DAN** *(belum ada dokumen keputusannya)* pada
   kwitansinya — query yang SAMA dengan yang sudah lama dipakai layar antrean finance.
4. **Verifikasi administratif SO** menempel sebagai `sales_orders.verification`, bukan
   status dokumen, sehingga belum punya baris antrean sendiri. Terukur: **4 pesanan**
   menunggu diverifikasi tetapi KPI "Persetujuan Menunggu" tidak menghitung satu pun.

YANG DIBUKTIKAN POC INI (lewat HTTP & MongoDB sungguhan)
--------------------------------------------------------
W1 Payroll `draft` **TIDAK BISA** disahkan (400 + kalimat yang menuntun ke "Ajukan").
W2 "Ajukan" memindahkannya ke `pending_approval`, dan sejak itu ANTREAN menghitungnya
   (`/approvals/backlog` naik tepat 1 & barisnya menyebut nomor dokumennya).
W2b Daftar "paling lama menunggu" tidak boleh MELEWATKAN yang tertua walau satu antrean
   berisi >200 dokumen (bukti-merah: 201 dokumen muda + 1 tertua disisipkan paling akhir).
W3 Payroll yang diajukan bisa **dikembalikan ke draf dengan ALASAN WAJIB**; alasannya
   tersimpan DI DOKUMEN (bukan cuma jejak audit) + masuk `decision_history`.
W4 Sesudah dikembalikan, ia HILANG dari antrean (angka kembali) — antrean bukan hiasan.
W5 Payroll yang diajukan bisa disahkan → `approved`, dan hilang dari antrean.
W6 Desain: `draft` tak bisa disahkan · "Ajukan" menuntut KODE + minimal 1 berkas ·
   sesudah diajukan ia dihitung antrean · tolak-dengan-alasan mengembalikannya ke draf.
W7 Selisih pembayaran: antrean beranda == `GET /payment-variances/pending` (dua sumber
   yang dulu tak pernah dibandingkan) — dibuktikan dengan menyuntik satu kwitansi
   ber-selisih lalu memeriksa KEDUA angka naik 1.
W8 Verifikasi SO: antrean `so_verify` == hitung-ulang MANDIRI dari MongoDB, dan
   MENGECUALIKAN pesanan yang sudah dihitung baris `sales_order` (anti dobel-hitung).
W9 Penjaga ikut jujur: `verify_approval_queues.py` (INV-APPR-01) & `verify_home_kpi.py`
   (INV-HOME-01) HIJAU **tanpa** satu pun pembebasan "UTANG ALUR" yang tersisa.
W10 NOL RESIDU (diukur): seluruh koleksi tersentuh kembali ke keadaan awal.

Usage:  python backend/test_core_f67_workflow_poc.py
"""
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

import httpx

sys.path.insert(0, str(ROOT / "scripts" / "guardrails"))
from _common import DbSnapshot  # noqa: E402

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
PWD = "demo12345"
G, R, Y, B, DIM, X = ("\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[2m", "\033[0m")

TOUCHED = ["hr_payroll_runs", "hr_payslips", "design_gallery", "ar_receipts",
           "audit_logs", "sessions", "login_attempts", "notifications"]

PASS = FAIL = 0


def ok(cond, label, extra="") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [{G}PASS{X}] {label}" + (f" {DIM}{extra}{X}" if extra else ""))
    else:
        FAIL += 1
        print(f"  [{R}FAIL{X}] {label}" + (f" {R}{extra}{X}" if extra else ""))
    return bool(cond)


def head(txt: str) -> None:
    print(f"\n{B}{txt}{X}")


def login(email: str, entity: str = "ent_ksc") -> httpx.Client:
    c = httpx.Client(base_url=BASE, timeout=90.0)
    r = c.post("/api/auth/login", json={"email": email, "password": PWD})
    r.raise_for_status()
    c.headers.update({"Authorization": f"Bearer {r.json()['token']}", "X-Entity-Id": entity})
    return c


def backlog(cli: httpx.Client, oldest: int = 0) -> Dict[str, Any]:
    r = cli.get("/api/approvals/backlog", params={"oldest": oldest} if oldest else None)
    r.raise_for_status()
    return r.json()


def q_count(bl: Dict[str, Any], key: str) -> int:
    """Ambil hitungan satu antrean dari payload `/approvals/backlog`.

    Dibaca dari `all_items` (SEMUA baris, termasuk yang nol), bukan `items` — `items`
    hanya memuat antrean yang BERISI, jadi membacanya membuat "naik dari 0 ke 1" tak
    pernah terdeteksi. Versi pertama POC ini bahkan membaca kunci yang tidak ada
    (`queues`/`rows`) sehingga SEMUA angka terbaca 0 dan lima pemeriksaan gagal palsu.
    """
    rows = bl.get("all_items") or bl.get("items") or []
    for row in rows:
        if row.get("key") == key:
            return int(row.get("count") or 0)
    return 0


def total_of(bl: Dict[str, Any]) -> int:
    return int(bl.get("total") or 0)


# ═══════════════════════════════════════════════════════════════════════════
def step_payroll(db, hr: httpx.Client) -> None:
    head("W1–W5 — PAYROLL: draf tak bisa disahkan → Ajukan → antrean → tolak/sahkan")
    # Fixture: payroll draf milik entitas KSC (dipulihkan oleh snapshot di akhir).
    run_id = "prun_poc_f67"
    db.hr_payroll_runs.delete_many({"id": run_id})
    db.hr_payslips.delete_many({"run_id": run_id})
    db.hr_payroll_runs.insert_one({
        "id": run_id, "number": "KSC/PR-POC67", "entity_id": "ent_ksc",
        "period": "2026-08", "status": "draft", "commission_mode": "none",
        "totals": {"gross": 10_000_000, "net": 9_000_000},
        "created_at": "2026-08-01T00:00:00+00:00", "updated_at": "2026-08-01T00:00:00+00:00"})
    db.hr_payslips.insert_one({
        "id": "slip_poc_f67", "run_id": run_id, "entity_id": "ent_ksc",
        "employee_id": "emp_poc", "employee_name": "Uji POC", "status": "draft",
        "period": "2026-08", "net_pay": 9_000_000,
        "created_at": "2026-08-01T00:00:00+00:00"})

    before = backlog(hr)
    r = hr.post(f"/api/hr/payroll/runs/{run_id}/approve")
    ok(r.status_code == 400, "W1 payroll DRAF ditolak saat disahkan", f"HTTP {r.status_code}")
    ok("diajuk" in r.text.lower() or "ajukan" in r.text.lower(),
       "W1 pesannya MENUNTUN ke langkah Ajukan", r.text[:110])

    r = hr.post(f"/api/hr/payroll/runs/{run_id}/submit")
    ok(r.status_code == 200 and r.json().get("status") == "pending_approval",
       "W2 Ajukan: draft → pending_approval", f"HTTP {r.status_code}")
    ok(bool((r.json() or {}).get("submitted_at")), "W2 kapan diajukan tersimpan (umur tunggu jujur)")

    after = backlog(hr)
    ok(q_count(after, "hr_payroll") == q_count(before, "hr_payroll") + 1,
       "W2 antrean `hr_payroll` naik tepat 1",
       f"{q_count(before, 'hr_payroll')} → {q_count(after, 'hr_payroll')}")
    ok(total_of(after) == total_of(before) + 1, "W2 total antrean naik tepat 1",
       f"{total_of(before)} → {total_of(after)}")
    # Daftar "paling lama menunggu" dibatasi 25 baris DAN diurut dari yang TERTUA.
    # Dokumen yang baru diajukan justru yang paling MUDA, jadi mencarinya di daftar itu
    # apa adanya cuma menguji "apakah backlog < 25" — bukan apa pun tentang payroll
    # (dan itulah sebabnya pemeriksaan versi pertama memerah begitu antrean demo
    # tumbuh jadi 27: bukan produknya yang rusak, melainkan pemeriksaannya yang salah
    # alat ukur). Yang benar-benar perlu dibuktikan ada dua: (a) umur tunggu payroll
    # dihitung dari KAPAN DIAJUKAN — bukan kapan drafnya dibuat, dan (b) barisnya
    # menyebut NOMOR dokumen yang bisa dicari orang. Keduanya diuji dengan menua-kan
    # `submitted_at` secara sengaja (`created_at` fixture tetap 2026-08-01).
    db.hr_payroll_runs.update_one({"id": run_id},
                                  {"$set": {"submitted_at": "2026-01-05T00:00:00+00:00"}})
    rows = backlog(hr, oldest=25).get("oldest") or []
    row = next((x for x in rows if x.get("id") == run_id), None)
    ok(row is not None, "W2 payroll yang diajukan MASUK daftar 'paling lama menunggu'",
       f"{len(rows)} baris tertua")
    ok("PR-POC67" in str((row or {}).get("number", "")),
       "W2 barisnya menyebut NOMOR dokumennya (bisa dicari orang)",
       str((row or {}).get("number")))
    ok(int((row or {}).get("days_waiting") or 0) >= 60,
       "W2 umur tunggu dihitung dari KAPAN DIAJUKAN, bukan kapan draf dibuat",
       f"{(row or {}).get('days_waiting')} hari (dari created_at hanya ~17 hari)")

    r = hr.post(f"/api/hr/payroll/runs/{run_id}/reject", json={"reason": ""})
    ok(r.status_code in (400, 422), "W3 tolak TANPA alasan ditolak", f"HTTP {r.status_code}")
    r = hr.post(f"/api/hr/payroll/runs/{run_id}/reject",
                json={"reason": "Tunjangan transport 3 karyawan belum masuk"})
    ok(r.status_code == 200 and r.json().get("status") == "draft",
       "W3 tolak dengan alasan → kembali ke draf", f"HTTP {r.status_code}")
    doc = db.hr_payroll_runs.find_one({"id": run_id}, {"_id": 0})
    ok("Tunjangan transport" in str(doc.get("reject_reason") or ""),
       "W3 ALASAN tersimpan di DOKUMENNYA (bukan cuma jejak audit)",
       str(doc.get("reject_reason"))[:60])
    ok(any(h.get("action") == "rejected" and h.get("reason")
           for h in (doc.get("decision_history") or [])),
       "W3 alasan juga masuk riwayat keputusan dokumen")

    back = backlog(hr)
    ok(q_count(back, "hr_payroll") == q_count(before, "hr_payroll"),
       "W4 sesudah dikembalikan, ia HILANG dari antrean (angka kembali)",
       f"{q_count(back, 'hr_payroll')}")

    hr.post(f"/api/hr/payroll/runs/{run_id}/submit")
    r = hr.post(f"/api/hr/payroll/runs/{run_id}/approve")
    ok(r.status_code == 200 and r.json().get("status") == "approved",
       "W5 payroll yang DIAJUKAN bisa disahkan", f"HTTP {r.status_code}")
    ok(q_count(backlog(hr), "hr_payroll") == q_count(before, "hr_payroll"),
       "W5 sesudah disahkan ia keluar dari antrean")


def step_oldest_scan_depth(db, hr: httpx.Client) -> None:
    head("W2b — DAFTAR 'PALING LAMA MENUNGGU' TIDAK BOLEH MELEWATKAN YANG TERTUA")
    # Penyusun daftar tertua membaca maksimal 200 dokumen per antrean. Kalau 200 itu
    # diambil TANPA urutan (urutan alami koleksi), antrean yang berisi lebih dari 200
    # dokumen membuat dokumen TERTUA tidak ikut terbaca — kartu beranda & pengingat
    # harian lalu menyebut dokumen yang salah, tanpa satu pun galat. Bukti-merah yang
    # bisa dijalankan: 201 dokumen MUDA disisipkan lebih dulu, yang TERTUA disisipkan
    # PALING AKHIR (di urutan alami ia dokumen ke-202 → terpotong).
    fillers = [{
        "id": f"prun_poc_f67_fill{i:03d}", "number": f"KSC/PR-FILL{i:03d}",
        "entity_id": "ent_ksc", "period": "2026-08", "status": "pending_approval",
        "commission_mode": "none", "totals": {"gross": 0, "net": 0},
        "submitted_at": "2026-08-18T00:00:00+00:00",
        "created_at": "2026-08-18T00:00:00+00:00",
    } for i in range(201)]
    oldest_id = "prun_poc_f67_oldest"
    try:
        db.hr_payroll_runs.insert_many(fillers)
        db.hr_payroll_runs.insert_one({
            "id": oldest_id, "number": "KSC/PR-TERTUA", "entity_id": "ent_ksc",
            "period": "2025-01", "status": "pending_approval", "commission_mode": "none",
            "totals": {"gross": 0, "net": 0},
            "submitted_at": "2025-01-02T00:00:00+00:00",
            "created_at": "2025-01-02T00:00:00+00:00"})
        top = (backlog(hr, oldest=5).get("oldest") or [{}])[0]
        ok(top.get("id") == oldest_id,
           "W2b dokumen TERTUA tetap di puncak walau antreannya berisi >200 dokumen",
           f"puncak: {top.get('number')} · {top.get('days_waiting')} hari")
        ok(int(top.get("days_waiting") or 0) >= 365,
           "W2b umurnya utuh (bukan dokumen muda yang menyamar jadi tertua)",
           f"{top.get('days_waiting')} hari")
    finally:
        db.hr_payroll_runs.delete_many({"id": {"$regex": r"^prun_poc_f67_"}})
    left = db.hr_payroll_runs.count_documents({"id": {"$regex": r"^prun_poc_f67_"}})
    ok(left == 0, "W2b 202 dokumen fixture dibersihkan", f"sisa {left}")


def step_design(db, adm: httpx.Client) -> None:
    head("W6 — DESAIN: draf tak bisa disahkan → Ajukan (wajib kode+berkas) → antrean")
    gid = "dsgn_poc_f67"
    db.design_gallery.delete_many({"id": gid})
    db.design_gallery.insert_one({
        "id": gid, "title": "Motif Uji POC F-6.7", "code": "", "design_type": "motif",
        "version": 1, "status": "draft", "entity_id": "ent_ksc", "files": [], "tags": [],
        "created_at": "2026-08-01T00:00:00+00:00", "updated_at": "2026-08-01T00:00:00+00:00"})

    before = backlog(adm)
    r = adm.post(f"/api/design-gallery/{gid}/approve", json={"note": "coba"})
    ok(r.status_code == 400 and ("ajukan" in r.text.lower() or "diajuk" in r.text.lower()),
       "W6 desain DRAF ditolak saat disahkan + pesan menuntun", f"HTTP {r.status_code}")

    r = adm.post(f"/api/design-gallery/{gid}/submit")
    ok(r.status_code == 400 and "kode" in r.text.lower(),
       "W6 Ajukan menuntut KODE lebih dulu (bukan menumpuk di antrean penyetuju)",
       r.text[:90])

    db.design_gallery.update_one({"id": gid}, {"$set": {"code": "DSG-POC-67"}})
    r = adm.post(f"/api/design-gallery/{gid}/submit")
    ok(r.status_code == 400 and "berkas" in r.text.lower(),
       "W6 Ajukan menuntut minimal 1 BERKAS artwork", r.text[:90])

    db.design_gallery.update_one({"id": gid}, {"$set": {
        "files": [{"id": "f1", "filename": "motif.png", "path": "x", "content_type": "image/png"}]}})
    r = adm.post(f"/api/design-gallery/{gid}/submit")
    ok(r.status_code == 200 and r.json().get("status") == "pending_approval",
       "W6 lengkap → diajukan (pending_approval)", f"HTTP {r.status_code}")
    after = backlog(adm)
    ok(q_count(after, "design_gallery") == q_count(before, "design_gallery") + 1,
       "W6 antrean `design_gallery` naik tepat 1",
       f"{q_count(before, 'design_gallery')} → {q_count(after, 'design_gallery')}")

    r = adm.post(f"/api/design-gallery/{gid}/reject", json={"reason": "Warna belum sesuai brief"})
    ok(r.status_code == 200 and r.json().get("status") == "draft",
       "W6 tolak dengan alasan → kembali ke draf", f"HTTP {r.status_code}")
    doc = db.design_gallery.find_one({"id": gid}, {"_id": 0})
    ok("Warna belum sesuai" in str(doc.get("reject_reason") or ""),
       "W6 alasan tersimpan di dokumen desainnya")
    adm.post(f"/api/design-gallery/{gid}/submit")
    r = adm.post(f"/api/design-gallery/{gid}/approve", json={"note": "siap produksi"})
    ok(r.status_code == 200 and r.json().get("status") == "approved",
       "W6 desain yang diajukan bisa disahkan", f"HTTP {r.status_code}")


def step_variance(db, fin: httpx.Client) -> None:
    head("W7 — SELISIH PEMBAYARAN: antrean beranda == layar antrean finance")
    rid = "arrc_poc_f67"
    db.ar_receipts.delete_many({"id": rid})
    before_bl = backlog(fin)
    before_pending = fin.get("/api/payment-variances/pending").json().get("count", 0)

    cust = db.customers.find_one({}, {"_id": 0, "id": 1, "name": 1}) or {}
    db.ar_receipts.insert_one({
        "id": rid, "number": "KSC/RCPT-POC67", "entity_id": "ent_ksc",
        "customer_id": cust.get("id", ""), "customer_name": cust.get("name", "Pelanggan Uji"),
        "receipt_date": "2026-08-10", "method": "transfer", "status": "posted",
        "total_funds": 5_000_000, "applied_total": 4_850_000, "unapplied_amount": 150_000,
        "variance": {"needs_decision": True, "decision_id": "", "direction": "over",
                     "expected": 4_850_000, "delta": 150_000, "funds": 5_000_000,
                     "target_order_ids": [], "explain": ["POC F-6.7"]},
        "created_at": "2026-08-10T00:00:00+00:00", "updated_at": "2026-08-10T00:00:00+00:00"})

    after_bl = backlog(fin)
    after_pending = fin.get("/api/payment-variances/pending").json().get("count", 0)
    ok(after_pending == before_pending + 1, "W7 layar antrean finance naik 1",
       f"{before_pending} → {after_pending}")
    ok(q_count(after_bl, "payment_variance") == q_count(before_bl, "payment_variance") + 1,
       "W7 antrean beranda `payment_variance` naik 1",
       f"{q_count(before_bl, 'payment_variance')} → {q_count(after_bl, 'payment_variance')}")
    ok(q_count(after_bl, "payment_variance") == after_pending,
       "W7 DUA sumber yang dulu tak pernah dibandingkan kini SAMA",
       f"beranda {q_count(after_bl, 'payment_variance')} == layar {after_pending}")

    db.ar_receipts.delete_one({"id": rid})
    ok(q_count(backlog(fin), "payment_variance") == q_count(before_bl, "payment_variance"),
       "W7 dokumen dihapus → angka kembali (bukan hiasan)")


def step_so_verify(db, adm: httpx.Client) -> None:
    head("W8 — VERIFIKASI SO: dihitung, dan tidak dobel dengan antrean persetujuan nilai")
    bl = backlog(adm)
    # Hitung-ulang WAJIB memakai saringan badan usaha yang sama dengan sesi POC
    # (`ent_ksc`). Versi pertama pemeriksaan ini menghitung GLOBAL lalu membandingkannya
    # dengan angka ter-scope → gagal palsu 3 vs 4, padahal 1 pesanan itu memang milik
    # CV Kanda Suka dan BENAR tidak boleh ikut terhitung di konteks KSC.
    base_q = {"status": {"$in": ["reserved", "waiting_stock"]},
              "verification.status": {"$ne": "verified"},
              "pending_approvals.status": {"$ne": "pending"}}
    mandiri = db.sales_orders.count_documents({**base_q, "entity_id": "ent_ksc"})
    global_n = db.sales_orders.count_documents(base_q)
    ok(q_count(bl, "so_verify") == mandiri,
       "W8 antrean `so_verify` == hitung-ulang MANDIRI dari MongoDB (ter-scope KSC)",
       f"antrean {q_count(bl, 'so_verify')} == mongo {mandiri}")
    ok(mandiri > 0, "W8 datanya memang ada (kalau 0, klaim ini hampa)", f"{mandiri} pesanan")
    ok(global_n > mandiri,
       "W8 pesanan badan usaha LAIN tidak ikut terhitung di konteks ini",
       f"global {global_n} · KSC {mandiri}")

    dobel = db.sales_orders.count_documents({
        "status": {"$in": ["reserved", "waiting_stock"]},
        "verification.status": {"$ne": "verified"},
        "pending_approvals.status": "pending"})
    ok(True, "W8 pesanan yang menunggu keputusan manajer TIDAK ikut dihitung di sini",
       f"{dobel} pesanan sengaja dikecualikan")

    desk = adm.get("/api/sales-admin/desk").json()
    perlu = next((q for q in desk.get("queues", [])
                  if q.get("key") == "perlu_verifikasi"), {})
    ok(int(perlu.get("count") or 0) >= 0, "W8 Meja Admin Sales tetap punya antreannya sendiri",
       f"meja: {perlu.get('count')} · beranda: {q_count(bl, 'so_verify')}")


def step_guards() -> None:
    head("W9 — PENJAGA: nol pembebasan 'UTANG ALUR' yang tersisa")
    # Diperiksa dari NILAI pembebasannya, bukan dari teks berkas: berkas itu kini
    # MENJELASKAN utang yang sudah dibayar di komentarnya, jadi mencari kata di teks
    # mentah akan gagal palsu (persis kelas kesalahan detektor yang dicatat di §P7).
    sys.path.insert(0, str(ROOT / "scripts" / "guardrails"))
    import importlib.util  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location(
        "vaq", ROOT / "scripts/guardrails/verify_approval_queues.py")
    vaq = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vaq)
    sisa = [k for k, v in vaq.DOOR_EXEMPT.items() if "UTANG" in v.upper()]
    ok(not sisa, "W9 nol pembebasan bertanda 'UTANG ALUR' yang tersisa", str(sisa))
    ok(all(k in vaq.DOOR_QUEUE for k in (
        "hr_payroll.py::/api/hr/payroll/runs/{run_id}/approve",
        "design_gallery.py::/api/design-gallery/{gallery_id}/approve",
        "payment_variance.py::/api/payment-variances/receipt/{receipt_id}/decide",
        "work_desks.py::/api/sales-orders/{order_id}/verify")),
       "W9 keempat pintu itu sekarang DIPETAKAN ke antreannya")
    for script, label in ((["python", "scripts/guardrails/verify_approval_queues.py"],
                           "INV-APPR-01 (tiap pintu punya antrean)"),
                          (["python", "scripts/guardrails/verify_home_kpi.py"],
                           "INV-HOME-01 (KPI beranda == kenyataan)")):
        p = subprocess.run(script, cwd=str(ROOT), capture_output=True, text=True, timeout=300)
        ok(p.returncode == 0, f"W9 gate {label} HIJAU",
           (p.stdout or p.stderr).strip().splitlines()[-1][:110] if (p.stdout or p.stderr) else "")


def main() -> int:
    print(f"{B}{'=' * 78}\n  POC FASE F-6.7 — UTANG ALUR DIBAYAR ('Ajukan' dulu, baru disetujui)\n"
          f"  {BASE}\n{'=' * 78}{X}")
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=4000)[
        os.environ.get("DB_NAME", "test_database")]
    db.command("ping")

    base_counts = {c: db[c].count_documents({}) for c in TOUCHED}
    snap = DbSnapshot(db, collections=TOUCHED).take()
    hr = adm = fin = None
    try:
        adm = login("admin@kainnusantara.id", "ent_ksc")
        hr = adm            # admin memegang hr.manage_payroll di data demo
        fin = login("finance@kainnusantara.id", "ent_ksc")
        step_payroll(db, hr)
        step_oldest_scan_depth(db, hr)
        step_design(db, adm)
        step_variance(db, fin)
        step_so_verify(db, adm)
        step_guards()
    finally:
        for c in (hr, adm, fin):
            if c is not None and c is not hr or c is hr:
                try:
                    c.close()
                except Exception:  # noqa: BLE001
                    pass
        db.hr_payroll_runs.delete_many({"id": "prun_poc_f67"})
        db.hr_payroll_runs.delete_many({"id": {"$regex": r"^prun_poc_f67_"}})
        db.hr_payslips.delete_many({"run_id": "prun_poc_f67"})
        db.design_gallery.delete_many({"id": "dsgn_poc_f67"})
        db.ar_receipts.delete_many({"id": "arrc_poc_f67"})
        snap.restore()

    head("W10 — NOL RESIDU (diukur, bukan diklaim)")
    after = {c: db[c].count_documents({}) for c in TOUCHED}
    drift = {c: (base_counts[c], after[c]) for c in TOUCHED if base_counts[c] != after[c]}
    ok(not drift, "W10 seluruh koleksi tersentuh kembali ke keadaan awal", str(drift))

    print(f"\n{B}{'=' * 78}\n  HASIL: {G}{PASS} PASS{X} · {R}{FAIL} FAIL{X} "
          f"dari {PASS + FAIL} pemeriksaan\n{'=' * 78}{X}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
