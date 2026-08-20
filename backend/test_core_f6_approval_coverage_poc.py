#!/usr/bin/env python3
"""POC FASE F-6 — **SATU PINTU PERSETUJUAN YANG BENAR-BENAR SATU**.

Keputusan pemilik (2026-08-17): dari dua pilihan §F-5 nomor 1 — *"hidupkan mesin
persetujuan generik ATAU cabut endpoint+izinnya"* — bukti kode memilih **CABUT**, lalu
menggantinya dengan yang nyata. POC ini membuktikan KEDUA sisi keputusan itu, dengan
angka, lewat HTTP & MongoDB sungguhan.

KENAPA CABUT (semuanya terukur, bukan dibaca dari dokumen)
==========================================================
* `create_approval_request()` **nol pemanggil** → koleksi `approval_requests` selalu
  kosong (0 dok), sementara `POST /approval-requests/{id}/approve|reject` ADA dan izin
  `approval.approve` dipegang admin & manajer: wewenang di kertas tanpa dokumen.
* **Nol pemakai di layar**: tak satu pun berkas frontend memanggil `/approval-requests`.
* Menghidupkannya melanggar arsitektur: setiap persetujuan nyata diputuskan di endpoint
  dokumennya sendiri; mesin generik akan menjadi **jalur penulisan status kedua**.
* Endpoint generiknya membaca tanpa saringan badan usaha (pada `get` bahkan
  `resolve_scope_ids()` dihitung lalu tidak dipakai) → pagar multi-PT bocor di fitur mati.

GANTINYA — DAN INI YANG PENTING
-------------------------------
Sapuan bukti (endpoint `approve|reject|verify|decide` di KODE + status menunggu di DATA)
menemukan **14 antrean keputusan nyata** yang tak pernah dihitung: transfer gudang,
kontrabon (verifikasi/persetujuan/sengketa), permintaan internal & retur antar-PT,
tagihan supplier, biaya masuk, uang muka + pertanggungjawabannya, klaim makloon, buka
periode, cuti, lembur. Selama itu KPI "Persetujuan Menunggu" tetap berbohong — hanya
dengan selisih yang lebih kecil (**17 dari 22**).

YANG DIBUKTIKAN
---------------
G1 PENSIUN NYATA: route generik hilang (404), izin `approval.approve` tidak ada lagi di
   matriks izin admin & manajer, dan tak ada kode yang memakai koleksi matinya.
G2 KEMAMPUAN TIDAK HILANG: membaca antrean tetap boleh (`/approvals/backlog`,
   `/approvals/queue` 200) dan aturan ambang (`/approval-rules`) tetap bisa diatur.
G3 ANGKA JUJUR: KPI beranda == `/approvals/backlog` == hitung-ulang MANDIRI dari MongoDB
   (query ditulis ulang di POC ini, bukan mengimpor QUEUES).
G4 ANTREAN BARU BUKAN HIASAN: tiap antrean baru yang berisi menyebut NOMOR dokumen yang
   bisa dicari orang + layar tujuan yang ADA di `AppViewRouter.jsx`.
G5 BUKTI-MERAH: satu dokumen transfer `waiting_approval` disuntikkan → total WAJIB naik 1
   dan barisnya muncul di `oldest`; dokumen dihapus → total kembali. Kalau angka tak
   bergerak, antrean itu hanya hiasan.
G6 ANTI DOBEL-HITUNG: `customer_prices` yang menunggu SUDAH terhitung lewat
   `price_approvals` tertaut → tidak boleh ikut ditambahkan (KPI tak boleh melebih-lebih).
G7 TERSARING BADAN USAHA: angka per PT ≤ angka gabungan dan jumlahnya bisa dijelaskan.
G8 PENJAGANYA BISA MEMERAH: `verify_approval_queues.py --self-test` (15 kasus) lulus.
G9 NOL RESIDU (DIUKUR): seluruh koleksi tersentuh kembali ke keadaan awal.

Usage:  python backend/test_core_f6_approval_coverage_poc.py
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

import httpx

sys.path.insert(0, str(ROOT / "scripts" / "guardrails"))
from _common import DbSnapshot

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
PWD = "demo12345"
G, R, Y, B, DIM, X = ("\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[2m", "\033[0m")

#: Koleksi yang tersentuh POC ini (fixture transfer + jejak login).
TOUCHED = ["warehouse_transfers", "audit_logs", "sessions", "login_attempts"]
#: Hitung-ulang MANDIRI: 26 antrean, ditulis ULANG di sini dengan sengaja supaya POC ini
#: menjadi OPINI KEDUA — bukan cermin `approval_backlog_service.QUEUES` yang sedang diuji.
RECOUNT: Dict[str, tuple] = {
    "sales_order": ("sales_orders", {"$or": [{"status": "waiting_approval"},
                                             {"pending_approvals.status": "pending"}]}),
    "purchase_order": ("purchase_orders", {"status": "waiting_approval"}),
    "price": ("price_approvals", {"status": "pending",
                                  "$or": [{"so_id": ""}, {"so_id": None},
                                          {"so_id": {"$exists": False}}]}),
    "purchase_requisition": ("purchase_requisitions", {"status": "pending_approval"}),
    "sales_return": ("sales_returns", {"status": "pending_approval"}),
    "purchase_return": ("purchase_returns", {"status": "pending_approval"}),
    "amendment": ("doc_amendments", {"status": "pending_approval"}),
    "interco": ("interco_transactions", {"status": "waiting_approval"}),
    "cycle_count": ("cycle_count_sessions", {"status": "submitted"}),
    "rnd_spec": ("md_specs", {"status": "review"}),
    "rnd_sample": ("md_samples", {"status": {"$in": ["in_progress", "assessed"]},
                                  "decision.supplier_id": {"$in": ["", None]}}),
    "special_order": ("special_orders", {"status": "pending_approval"}),
    # FASE F-6 — yang dulu tak terhitung
    "transfer": ("warehouse_transfers", {"status": "waiting_approval"}),
    "contra_bon_verify": ("contra_bons", {"status": "submitted"}),
    "contra_bon_approve": ("contra_bons", {"status": "verified"}),
    "contra_bon_dispute": ("contra_bons", {"status": "disputed"}),
    "internal_request": ("internal_requests", {"status": "submitted"}),
    "interco_return": ("interco_returns", {"status": "draft"}),
    "vendor_bill": ("vendor_bills", {"status": "pending_approval"}),
    "landed_cost": ("landed_cost_vouchers", {"status": "pending_approval"}),
    "cash_advance": ("cash_advances", {"status": {"$in": ["pending_atasan",
                                                          "pending_pimpinan",
                                                          "pending_finance"]}}),
    "cash_advance_settlement": ("cash_advance_settlements", {"status": "submitted"}),
    "makloon_claim": ("makloon_orders", {"steps.claim.status": "pending_approval"}),
    "period_unlock": ("period_unlock_requests", {"status": "pending"}),
    "hr_leave": ("hr_leave_requests", {"status": "pending"}),
    "hr_overtime": ("hr_overtime", {"status": "pending"}),
    # FASE F-6.7 — 4 antrean yang lahir saat UTANG ALUR dibayar. Ditulis ULANG di sini
    # (bukan mengimpor QUEUES) supaya POC ini tetap menjadi OPINI KEDUA.
    "hr_payroll": ("hr_payroll_runs", {"status": "pending_approval"}),
    "design_gallery": ("design_gallery", {"status": "pending_approval"}),
    "payment_variance": ("ar_receipts", {"status": {"$ne": "void"},
                                         "variance.needs_decision": True,
                                         "variance.decision_id": ""}),
    "so_verify": ("sales_orders", {"status": {"$in": ["reserved", "waiting_stock"]},
                                   "verification.status": {"$ne": "verified"},
                                   "pending_approvals.status": {"$ne": "pending"}}),
}

#: Antrean yang LAHIR di fase ini (dipakai G4 & laporan penutup).
BARU = ["transfer", "contra_bon_verify", "contra_bon_approve", "contra_bon_dispute",
        "internal_request", "interco_return", "vendor_bill", "landed_cost",
        "cash_advance", "cash_advance_settlement", "makloon_claim", "period_unlock",
        "hr_leave", "hr_overtime"]

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


def login(email: str, entity: str = "ent_ksc") -> httpx.Client:
    c = httpx.Client(base_url=BASE, timeout=60.0)
    r = c.post("/api/auth/login", json={"email": email, "password": PWD})
    r.raise_for_status()
    c.headers.update({"Authorization": f"Bearer {r.json()['token']}", "X-Entity-Id": entity})
    return c


def views_in_router() -> set:
    txt = (ROOT / "frontend/src/AppViewRouter.jsx").read_text(encoding="utf-8")
    return set(re.findall(r'activeView\s*===\s*"([\w-]+)"', txt))


def doc_counts(db) -> Dict[str, int]:
    return {c: db[c].count_documents({}) for c in TOUCHED}


def recount(db) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for key, (coll, query) in RECOUNT.items():
        try:
            out[key] = db[coll].count_documents(query)
        except Exception:  # noqa: BLE001
            out[key] = 0
    return out


def main() -> int:
    print(f"{B}{'=' * 78}\n  POC FASE F-6 — SATU PINTU PERSETUJUAN YANG BENAR-BENAR SATU\n"
          f"  {BASE}\n{'=' * 78}{X}")
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=4000)[
        os.environ.get("DB_NAME", "test_database")]
    db.command("ping")

    # Sidik jari & snapshot SEBELUM login (login menulis audit_logs + sessions).
    base_counts = doc_counts(db)
    snap = DbSnapshot(db, collections=TOUCHED).take()
    mgr = login("manager@kainnusantara.id", "all")
    adm = login("admin@kainnusantara.id", "all")
    # Mode "Semua Entitas" hanya-lihat (FASE E-3): setiap TULIS di mode itu ditolak 409
    # oleh pagar tulis SEBELUM sampai ke router — jadi probe "route sudah dicabut?" wajib
    # memakai klien ber-entitas nyata, kalau tidak 409-nya menutupi 404 yang dicari.
    mgr_pt = login("manager@kainnusantara.id", "ent_ksc")

    try:
        # ── G1 pensiun nyata ─────────────────────────────────────────────────
        print(f"\n{B}▶ G1 — mesin persetujuan generik BENAR-BENAR pensiun{X}")
        for path in ("/api/approval-requests", "/api/approval-requests/pending-count",
                     "/api/approval-requests/appreq_x"):
            r = mgr.get(path)
            ok(r.status_code == 404, f"GET {path} → 404 (route dicabut)", f"→ {r.status_code}")
        r = mgr_pt.post("/api/approval-requests/appreq_x/approve", json={"notes": "x"})
        ok(r.status_code == 404, "POST /approval-requests/{id}/approve → 404", f"→ {r.status_code}")
        r = mgr_pt.post("/api/approval-requests/appreq_x/reject", json={"reason": "x"})
        ok(r.status_code == 404, "POST /approval-requests/{id}/reject → 404", f"→ {r.status_code}")
        for who, cl in (("manager", mgr), ("admin", adm)):
            me = cl.get("/api/auth/me")
            perms = (me.json() or {}).get("permissions") or {}
            appr = perms.get("approval") or []
            ok("approve" not in appr,
               f"izin `approval.approve` tidak ada lagi di matriks {who}", f"approval={appr}")
            ok("view" in appr or who == "admin",
               f"{who} TETAP boleh MEMBACA antrean (`approval.view`)", f"approval={appr}")
        src = ""
        for sub in ("routers", "services"):
            for f in (ROOT / "backend" / sub).glob("*.py"):
                src += f.read_text(encoding="utf-8")
        ok("db.approval_requests" not in src,
           "tak ada kode backend yang memakai koleksi mati `approval_requests`")
        ok(not (ROOT / "backend/routers/approval_requests.py").exists(),
           "berkas router generik sudah tidak ada")
        ok(db.approval_requests.count_documents({}) == 0,
           "koleksi `approval_requests` memang kosong (bukan data yang dibuang)")

        # ── G2 kemampuan yang nyata TIDAK hilang ─────────────────────────────
        print(f"\n{B}▶ G2 — yang dicabut hanya yang mati; kemampuan nyata tetap{X}")
        r = mgr.get("/api/approvals/backlog", params={"oldest": 25})
        if not ok(r.status_code == 200, "GET /approvals/backlog → 200", f"→ {r.status_code}"):
            return 1
        backlog = r.json()
        ok(mgr.get("/api/approvals/queue").status_code == 200,
           "GET /approvals/queue (antrean SO) tetap 200")
        rr = adm.get("/api/approval-rules")
        ok(rr.status_code == 200 and isinstance(rr.json(), list),
           "aturan ambang (`/approval-rules`) tetap bisa dibaca & diatur pemilik",
           f"{len(rr.json()) if rr.status_code == 200 else rr.status_code} aturan")

        # ── G3 angka jujur (tiga sumber, satu angka) ─────────────────────────
        print(f"\n{B}▶ G3 — KPI beranda == backlog == hitung-ulang mandiri{X}")
        mandiri = recount(db)
        total_mandiri = sum(mandiri.values())
        ok(backlog["total"] == total_mandiri,
           "total backlog == hitung-ulang MANDIRI dari MongoDB",
           f"api={backlog['total']} mandiri={total_mandiri}")
        home = mgr.get("/api/home/manager")
        ok(home.status_code == 200, "GET /home/manager → 200", f"→ {home.status_code}")
        hp = home.json() if home.status_code == 200 else {}
        ok(hp.get("approvals_pending") == backlog["total"],
           "KPI beranda manajer == total backlog (satu sumber)",
           f"kpi={hp.get('approvals_pending')} backlog={backlog['total']}")
        by_key = {i["key"]: i["count"] for i in backlog.get("all_items") or []}
        beda = {k: (by_key.get(k), v) for k, v in mandiri.items() if by_key.get(k, 0) != v}
        ok(not beda, "setiap baris antrean cocok dengan hitungan mandiri", f"{beda}")
        ok(len(by_key) == len(RECOUNT),
           "jumlah baris antrean backend == jumlah antrean yang diketahui POC",
           f"backend={len(by_key)} poc={len(RECOUNT)}")

        # ── G4 antrean baru bukan hiasan ─────────────────────────────────────
        print(f"\n{B}▶ G4 — antrean baru menyebut dokumen NYATA & layar yang ada{X}")
        views = views_in_router()
        terisi = [k for k in BARU if by_key.get(k, 0) > 0]
        ok(bool(terisi), "ada antrean baru yang memang berisi dokumen di data demo",
           f"{terisi}")
        rows_all = backlog.get("oldest") or []
        hantu = sorted({i["view"] for i in (backlog.get("all_items") or [])
                        if i["view"] not in views})
        ok(not hantu, "tiap baris antrean menunjuk layar yang ADA di AppViewRouter",
           f"{hantu}")
        for k in terisi:
            rows = [o for o in rows_all if o["key"] == k]
            if not rows:
                continue
            ok(all(o.get("number") for o in rows),
               f"antrean `{k}` menyebut nomor dokumen yang bisa dicari orang",
               f"{[o['number'] for o in rows][:2]}")
        ok(all(o.get("days_waiting", -1) >= 0 for o in rows_all),
           "umur tunggu tiap baris tidak negatif")

        # ── G5 BUKTI-MERAH: angkanya benar-benar hidup ───────────────────────
        print(f"\n{B}▶ G5 — BUKTI-MERAH: suntik 1 transfer menunggu → angka WAJIB bergerak{X}")
        fixture = {
            "id": "trn_poc_f6_fixture", "code": "KSC/TRF-POCF6",
            "transfer_kind": "intra_entity", "entity_id": "ent_ksc",
            "source_warehouse_id": "wh_jakarta", "dest_warehouse_id": "wh_bandung",
            "source_warehouse_name": "Gudang Jakarta Utara",
            "dest_warehouse_name": "Gudang Bandung Kota",
            "status": "waiting_approval", "items": [], "notes": "fixture POC F-6",
            "requested_by": "POC", "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        db.warehouse_transfers.insert_one(dict(fixture))
        r2 = mgr.get("/api/approvals/backlog", params={"oldest": 25}).json()
        naik = r2["total"] - backlog["total"]
        ok(naik == 1, "total backlog naik TEPAT 1 setelah dokumen menunggu dibuat",
           f"{backlog['total']} → {r2['total']}")
        b2 = {i["key"]: i["count"] for i in r2.get("all_items") or []}
        ok(b2.get("transfer", 0) == by_key.get("transfer", 0) + 1,
           "kenaikan terjadi di baris `transfer` (bukan di baris lain)",
           f"transfer {by_key.get('transfer', 0)} → {b2.get('transfer', 0)}")
        row = next((o for o in (r2.get("oldest") or [])
                    if o.get("id") == fixture["id"]), None)
        ok(bool(row), "dokumennya muncul di daftar 'paling lama menunggu'",
           f"{(row or {}).get('number')} · {(row or {}).get('title')}")
        ok(bool(row) and row.get("view") in views and row.get("days_waiting", 0) > 0,
           "barisnya punya layar tujuan nyata + umur tunggu terhitung",
           f"view={(row or {}).get('view')} umur={(row or {}).get('days_waiting')}h")
        kpi2 = mgr.get("/api/home/manager").json().get("approvals_pending")
        ok(kpi2 == r2["total"], "KPI beranda ikut bergerak (bukan angka mati)",
           f"kpi={kpi2} backlog={r2['total']}")
        db.warehouse_transfers.delete_one({"id": fixture["id"]})
        r3 = mgr.get("/api/approvals/backlog").json()
        ok(r3["total"] == backlog["total"], "dokumen dihapus → total kembali seperti awal",
           f"{r3['total']} == {backlog['total']}")

        # ── G6 anti dobel-hitung ─────────────────────────────────────────────
        print(f"\n{B}▶ G6 — ANTI DOBEL-HITUNG (harga langganan sudah terhitung lewat harga khusus){X}")
        cp = list(db.customer_prices.find({"status": "pending_approval"}, {"_id": 0}))
        if cp:
            tertaut = [c for c in cp if c.get("price_approval_id")]
            ok(len(tertaut) == len(cp),
               "tiap harga langganan yang menunggu punya `price_approval_id`",
               f"{len(tertaut)}/{len(cp)}")
            pa_ids = {c["price_approval_id"] for c in tertaut}
            counted = db.price_approvals.count_documents(
                {"id": {"$in": list(pa_ids)}, "status": "pending"})
            ok(counted == len(pa_ids),
               "pasangannya memang sudah dihitung baris antrean `price`",
               f"{counted}/{len(pa_ids)}")
            ok(backlog["total"] == total_mandiri,
               "total TIDAK ikut bertambah karena harga langganan (nol dobel-hitung)")
        else:
            ok(True, "tidak ada harga langganan menunggu di data ini (lewati)", "0 dok")
        ids_semua = []
        for key, (coll, query) in RECOUNT.items():
            for d in db[coll].find(query, {"_id": 0, "id": 1}).limit(500):
                ids_semua.append((coll, d.get("id"), key))
        kunci = [(c, i) for c, i, _k in ids_semua]
        ok(len(kunci) == len(set(kunci)),
           "tak ada satu dokumen pun yang dihitung dua antrean",
           f"{len(kunci)} dokumen unik")

        # ── G7 tersaring badan usaha ─────────────────────────────────────────
        print(f"\n{B}▶ G7 — angka tersaring badan usaha (bukan angka grup yang dipakai ulang){X}")
        ksc = mgr.get("/api/approvals/backlog", params={"entity_id": "ent_ksc"}).json()
        gab = mgr.get("/api/approvals/backlog").json()
        ok(ksc["total"] <= gab["total"],
           "angka satu PT ≤ angka gabungan", f"KSC={ksc['total']} gabungan={gab['total']}")
        ok(ksc["total"] > 0, "PT utama memang punya antrean (uji tidak kosong palsu)",
           f"KSC={ksc['total']}")

        # ── G8 penjaganya bisa memerah ───────────────────────────────────────
        print(f"\n{B}▶ G8 — penjaga INV-APPR-01 terbukti bisa MEMERAH{X}")
        st = subprocess.run(
            [sys.executable, str(ROOT / "scripts/guardrails/verify_approval_queues.py"),
             "--self-test"], capture_output=True, text=True, timeout=120)
        ok(st.returncode == 0, "self-test penjaga antrean LULUS (15 kasus bukti-merah)",
           (st.stdout or st.stderr).strip().splitlines()[-1][:80] if st.stdout else "")
        gg = subprocess.run(
            [sys.executable, str(ROOT / "scripts/guardrails/verify_approval_queues.py")],
            capture_output=True, text=True, timeout=180)
        ok(gg.returncode == 0, "penjaga antrean HIJAU pada kode & data saat ini",
           [ln for ln in (gg.stdout or "").splitlines() if "cek lolos" in ln][:1])
    finally:
        snap.restore()

    # ── G9 nol residu (DIUKUR) ───────────────────────────────────────────────
    print(f"\n{B}▶ G9 — nol residu setelah POC (DIUKUR, bukan diklaim){X}")
    now = doc_counts(db)
    sisa = {c: (base_counts[c], now[c]) for c in base_counts if base_counts[c] != now[c]}
    ok(not sisa, "seluruh koleksi tersentuh kembali ke jumlah awal (INV-GATE-01)",
       f"{sisa}" if sisa else f"{len(base_counts)} koleksi identik")

    print(f"\n{B}{'=' * 78}{X}")
    print(f"  HASIL: {G}{PASS} PASS{X} · {R}{FAIL} FAIL{X} dari {PASS + FAIL} pemeriksaan")
    print(f"{B}{'=' * 78}{X}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
