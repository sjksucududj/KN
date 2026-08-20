#!/usr/bin/env python3
"""POC — **PENGINGAT ANTREAN PERSETUJUAN** (permintaan pemilik 2026-08-15).

*"Beri manajer pengingat harian berisi dokumen yang menunggu keputusannya paling lama."*

KENAPA POC INI ADA
==================
Sesi ini membuat KPI "Persetujuan Menunggu" berhenti berbohong (0 → 17). Tetapi angka
yang benar **hanya bekerja kalau orangnya membuka layar**. Manajer yang tidak membuka
aplikasi tetap tidak tahu `PRET-00001` sudah menunggu 6 hari. Pengingat harian menutup
celah itu — dan pengingat adalah fitur yang paling mudah "hijau tapi bohong": ia bisa
mengirim angka basi, mengabaikan ambang yang diatur pemilik, atau menggandakan diri
setiap kali penjadwal jalan. Karena itu keempatnya diuji dengan HTTP & job NYATA.

YANG DIBUKTIKAN
---------------
G1 **UMUR TUNGGU** benar & bisa dipakai: `GET /approvals/backlog?oldest=N` mengurutkan
   dari yang paling lama, tiap baris menyebut nomor dokumen + jenis + umur (hari),
   antreannya memang punya hitungan > 0, dan `view` tujuannya ADA di layar.
G2 **PENGINGAT NYATA**: job membuat notifikasi per badan usaha untuk peran `manager`,
   berisi NOMOR dokumen tertua (bukan cuma jumlah), ber-`link` ke Pusat Persetujuan.
G3 **ESKALASI**: bila umur dokumen ≥ 2× ambang, salinan dinaikkan ke `admin`.
G4 **IDEMPOTENT**: penjadwal boleh jalan berkali-kali sehari — tidak menggandakan.
G5 **AMBANG PEMILIK DIHORMATI (BUKTI-MERAH)**: ambang dinaikkan lewat API Pusat
   Pengaturan (`approval.reminder_min_days`) → pengingat WAJIB berhenti menyebut
   dokumen yang lebih muda dari ambang. Tanpa bagian ini, "hijau" hanya berarti
   "job berhasil mengirim sesuatu".
G6 **SAMPAI KE ORANG YANG BERWENANG**: manajer melihatnya di `GET /notifications`,
   peran `sales` TIDAK.
G7 **NOL RESIDU**: seluruh koleksi yang tersentuh pulih (INV-GATE-01).

Usage:  python backend/test_core_approval_reminder_poc.py
"""
import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

import httpx  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "guardrails"))
from _common import DbSnapshot  # noqa: E402

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
PWD = "demo12345"
G, R, Y, B, DIM, X = ("\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[2m", "\033[0m")
# Koleksi yang tersentuh POC ini. `sessions` & `audit_logs` masuk daftar karena
# SETIAP `POST /auth/login` menulis satu sesi + satu baris jejak audit — dan
# snapshot HARUS diambil SEBELUM login (lihat catatan di `main()`), kalau tidak
# ketiga baris login itu tak pernah bisa dipulihkan (akar gate merah 2026-08-16).
TOUCHED = ["notifications", "audit_logs", "login_attempts", "sessions",
           "config_values", "system_settings"]

PASS = FAIL = 0


def ok(cond, label, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [{G}PASS{X}] {label}" + (f" {DIM}{extra}{X}" if extra else ""))
    else:
        FAIL += 1
        print(f"  [{R}FAIL{X}] {label}" + (f" {R}{extra}{X}" if extra else ""))
    return cond


def login(email, entity="ent_ksc"):
    c = httpx.Client(base_url=BASE, timeout=60.0)
    r = c.post("/api/auth/login", json={"email": email, "password": PWD})
    r.raise_for_status()
    c.headers.update({"Authorization": f"Bearer {r.json()['token']}", "X-Entity-Id": entity})
    return c


def doc_counts(db, colls=None):
    """Jumlah dokumen per koleksi — dipakai G7 untuk MENGUKUR residu, bukan mengklaimnya."""
    return {c: db[c].count_documents({}) for c in (colls or TOUCHED)}


def residu(base, db):
    """Selisih jumlah dokumen vs keadaan awal: {koleksi: (awal, sekarang)}."""
    now = doc_counts(db)
    return {c: (base[c], now[c]) for c in base if base[c] != now[c]}


def views_in_router():
    txt = (ROOT / "frontend/src/AppViewRouter.jsx").read_text(encoding="utf-8")
    return set(re.findall(r'activeView\s*===\s*"([\w-]+)"', txt))


async def run_job():
    """Jalankan job SUNGGUHAN. Semua pemanggilan berada di SATU event loop.

    (Pelajaran saat menulis POC ini: `asyncio.run()` dipanggil berkali-kali membuat
    loop BARU tiap kali, sedangkan klien Motor terikat ke loop pertama → panggilan
    kedua gagal diam-diam dan `_entities()` mengembalikan daftar kosong sehingga job
    "berhasil" tanpa mengirim apa pun. Kalau POC-nya sendiri yang keliru seperti ini,
    hijaunya tidak berarti apa-apa.)
    """
    from services import approval_reminder as aprem
    return await aprem.job_approval_backlog_reminder()


async def main() -> int:
    print(f"{B}{'=' * 78}\n  POC PENGINGAT ANTREAN PERSETUJUAN  ·  {BASE}\n{'=' * 78}{X}")
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=4000)[
        os.environ.get("DB_NAME", "test_database")]
    db.command("ping")

    # ── INV-GATE-01: sidik jari & snapshot HARUS diambil SEBELUM login ────────
    # Akar gate merah 2026-08-16: snapshot dulu diambil SETELAH tiga login di bawah,
    # sehingga 3 baris `audit_logs` (+3 sesi) yang ditulis `POST /auth/login` berada
    # DI LUAR jendela snapshot → `restore()` tak mungkin menghapusnya → tiap
    # `gate.sh --full` meninggalkan +3 dok permanen. Urutan ini bagian dari uji.
    base = doc_counts(db)
    snap = DbSnapshot(db, collections=TOUCHED).take()

    mgr = login("manager@kainnusantara.id")
    adm = login("admin@kainnusantara.id", "all")
    sales = login("sales@kainnusantara.id")

    try:
        # ── G1 umur tunggu ────────────────────────────────────────────────
        print(f"\n{B}▶ G1 — umur tunggu: dokumen paling lama, bukan sekadar jumlah{X}")
        r = mgr.get("/api/approvals/backlog", params={"oldest": 8})
        if not ok(r.status_code == 200, "GET /approvals/backlog?oldest=8 → 200",
                  f"→ {r.status_code}"):
            return 1
        data = r.json()
        rows = data.get("oldest") or []
        counts = {i["key"]: i["count"] for i in data.get("all_items") or []}
        views = views_in_router()
        ok(bool(rows), f"ada dokumen menunggu untuk diingatkan", f"({len(rows)} baris)")
        ok(all(x["days_waiting"] >= y["days_waiting"] for x, y in zip(rows, rows[1:])),
           "diurutkan dari yang PALING LAMA menunggu",
           str([x["days_waiting"] for x in rows]))
        ok(all(x.get("number") for x in rows),
           "tiap baris menyebut NOMOR dokumen (bisa dicari orang)")
        ok(all(x.get("days_waiting", -1) >= 0 for x in rows), "umur tunggu tidak negatif")
        yatim = [x["key"] for x in rows if counts.get(x["key"], 0) <= 0]
        ok(not yatim, "tiap baris berasal dari antrean yang memang dihitung", f"{yatim}")
        hantu = sorted({x["view"] for x in rows if x["view"] not in views})
        ok(not hantu, "tujuan klik tiap baris ADA sebagai layar", f"{hantu}")
        tertua = rows[0] if rows else {}

        # ── G2/G3 pengingat & eskalasi ────────────────────────────────────
        print(f"\n{B}▶ G2/G3 — job membuat pengingat NYATA + eskalasi{X}")
        db.notifications.delete_many({"type": "approval_backlog"})
        hasil = await run_job()
        ok(hasil.get("notified", 0) > 0, "job mengirim pengingat",
           f"{ {k: v for k, v in hasil.items() if k != 'detail'} }")
        notes = list(db.notifications.find({"type": "approval_backlog"}, {"_id": 0}))
        mgr_notes = [n for n in notes if n["recipient_role"] == "manager"]
        ok(bool(mgr_notes), "ada notifikasi untuk peran manager", f"({len(mgr_notes)})")
        ok(all(n["link"] == "approval-inbox" for n in notes),
           "tiap pengingat menuntun ke Pusat Persetujuan")
        if tertua:
            n_ksc = next((n for n in mgr_notes if n.get("entity_id") == "ent_ksc"), None)
            ok(bool(n_ksc) and tertua["number"] in (n_ksc or {}).get("body", ""),
               f"badan pengingat menyebut dokumen tertua ({tertua.get('number')})",
               f"{(n_ksc or {}).get('title', '')}")
            ok(bool(n_ksc) and str(tertua["days_waiting"]) in (n_ksc or {}).get("title", ""),
               "judul pengingat menyebut umur dokumen tertua",
               f"{(n_ksc or {}).get('title', '')}")
        esc = [n for n in notes if n["recipient_role"] == "admin"]
        ok(hasil.get("escalated", 0) == len(esc),
           "eskalasi ke admin sesuai laporan job (umur ≥ 2× ambang)",
           f"escalated={hasil.get('escalated')} · notifikasi admin={len(esc)}")
        if esc:
            ok(all(n["severity"] == "critical" for n in esc),
               "notifikasi eskalasi bertingkat `critical`")

        # ── G4 idempotent ─────────────────────────────────────────────────
        print(f"\n{B}▶ G4 — penjadwal boleh jalan berkali-kali sehari{X}")
        sebelum = db.notifications.count_documents({"type": "approval_backlog"})
        h2 = await run_job()
        ok(h2.get("notified", 0) == 0 and h2.get("escalated", 0) == 0,
           "jalan kedua TIDAK membuat pengingat baru",
           f"{ {k: v for k, v in h2.items() if k != 'detail'} }")
        ok(db.notifications.count_documents({"type": "approval_backlog"}) == sebelum,
           "jumlah notifikasi tetap (dedupe harian)", f"{sebelum}")

        # ── G5 BUKTI-MERAH: ambang pemilik ────────────────────────────────
        print(f"\n{B}▶ G5 — BUKTI-MERAH: ambang di Pusat Pengaturan benar-benar dipakai{X}")
        # 60 = batas maksimum yang divalidasi registry (`max=60`). Memakai 999 ditolak
        # 400 oleh API — bukti tambahan bahwa ambangnya benar-benar setting bernorma,
        # bukan angka bebas yang diterima apa saja.
        put = adm.put("/api/config/values", json={"items": [{
            "key": "approval.reminder_min_days", "value": 60,
            "scope_type": "global", "scope_id": "",
            "reason": "POC pengingat antrean — bukti-merah ambang"}]})
        ok(put.status_code == 200, "ambang dinaikkan lewat API Pusat Pengaturan (60 hari)",
           f"→ {put.status_code} {put.text[:120] if put.status_code != 200 else ''}")
        db.notifications.delete_many({"type": "approval_backlog"})
        h3 = await run_job()
        ok(h3.get("notified", 0) == 0,
           "dengan ambang 60 hari → NOL pengingat (job menuruti pemilik)",
           f"{ {k: v for k, v in h3.items() if k != 'detail'} }")
        ok(all(d["min_days"] == 60 for d in h3.get("detail") or []),
           "job memang membaca ambang dari Pusat Pengaturan (bukan angka keras)",
           f"{[d['min_days'] for d in h3.get('detail') or []]}")
        adm.post("/api/config/values/reset", json={
            "key": "approval.reminder_min_days", "scope_type": "global", "scope_id": ""})
        db.notifications.delete_many({"type": "approval_backlog"})
        h4 = await run_job()
        ok(h4.get("notified", 0) > 0, "ambang dipulihkan → pengingat kembali jalan",
           f"notified={h4.get('notified')}")

        # ── G6 sampai ke orang yang berwenang ─────────────────────────────
        print(f"\n{B}▶ G6 — pengingat sampai ke pemutus, bukan ke semua orang{X}")
        mn = [n for n in mgr.get("/api/notifications").json()
              if n.get("type") == "approval_backlog"]
        sn = [n for n in sales.get("/api/notifications").json()
              if n.get("type") == "approval_backlog"]
        ok(bool(mn), "manajer melihat pengingatnya di lonceng notifikasi", f"({len(mn)})")
        ok(not sn, "peran sales TIDAK dikirimi pekerjaan yang bukan wewenangnya",
           f"({len(sn)})")

        # ── job terdaftar di penjadwal (bisa diatur pemilik tanpa kode) ────
        print(f"\n{B}▶ G6b — job terdaftar di layar Penjadwal{X}")
        jobs = adm.get("/api/scheduler/jobs").json()
        jl = jobs if isinstance(jobs, list) else (jobs.get("jobs") or jobs.get("items") or [])
        j = next((x for x in jl if x.get("id") == "approval_backlog_reminder"), None)
        ok(bool(j), "job `approval_backlog_reminder` ada di registry penjadwal",
           f"{(j or {}).get('label', '')} · {(j or {}).get('kind', '')} "
           f"{(j or {}).get('hour', '')}:{(j or {}).get('minute', '')}")
    finally:
        snap.restore()

    print(f"\n{B}▶ G7 — nol residu setelah POC (DIUKUR, bukan diklaim){X}")
    sisa = residu(base, db)
    ok(not sisa, "seluruh koleksi tersentuh kembali ke jumlah awal (INV-GATE-01)",
       f"{sisa}" if sisa else f"{len(base)} koleksi identik")

    # BUKTI-MERAH untuk pengukurnya sendiri: sebelum perbaikan ini G7 hanya berbunyi
    # `ok(True, ...)` — hijau abadi yang tak mengukur apa pun, dan justru di bawahnya
    # tersembunyi residu +3 `audit_logs`. Sentinel di bawah membuktikan pengukur
    # BISA memerah; kalau tidak, hijaunya tak berarti apa-apa.
    sentinel = {"id": "poc_reminder_residue_sentinel", "actor": "poc",
                "action": "sentinel", "entity_type": "gate", "entity_id": "INV-GATE-01"}
    db.audit_logs.insert_one(sentinel)
    ok("audit_logs" in residu(base, db),
       "BUKTI-MERAH: pengukur residu MEMERAH saat 1 dokumen sengaja nyangkut")
    db.audit_logs.delete_one({"_id": sentinel["_id"]})
    ok(not residu(base, db), "sentinel bukti-merah ikut dibersihkan (POC ini nol residu)")

    print(f"\n{B}{'=' * 78}{X}")
    print(f"  HASIL: {G}{PASS} PASS{X} · {R}{FAIL} FAIL{X} dari {PASS + FAIL} pemeriksaan")
    print(f"{B}{'=' * 78}{X}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
