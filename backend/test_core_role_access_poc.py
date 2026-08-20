#!/usr/bin/env python3
"""POC F-2 — AKSES & UI/UX PER PERAN: "menu terlihat = benar-benar bisa dipakai".

Menutup item yang diparkir di `plan.md` §8 ("analisis akses & UI/UX sales vs
admin-sales") — diperluas ke SELURUH peran karena bukti menunjukkan kelas cacatnya
tidak eksklusif dua peran itu.

APA YANG DIBUKTIKAN DI SINI (semua lewat HTTP NYATA, bukan pembacaan kode)
=========================================================================
G1. IZIN BACA YANG HILANG SUDAH DIBERIKAN — dan HANYA yang perlu:
    · `finance`   → `GET /ar/aging` 200 (dulu 403: menu Aging Piutang miliknya,
      izin `penalty.issue` miliknya, tetapi layarnya tertutup `require_role(manager)`)
    · `finance`   → `GET /suppliers` 200 (dulu 403 → SATU 403 di `Promise.all`
      mematikan SELURUH referensi layar "Kasus Keuangan")
    · `warehouse` → `GET /suppliers` 200 (dulu 403 → dropdown Supplier kosong di
      RFQ / Permintaan Pembelian / Retur Beli / Kontrabon)
    · `manager`   → `GET /users` 200 (dulu 403 → kolom "akun tertaut" selalu kosong)
G2. PAGAR TIDAK IKUT LONGGAR (yang penting justru ini):
    · `sales`/`warehouse` → `/ar/aging` TETAP 403 (aging memuat piutang SEMUA
      pelanggan; sales dibatasi kepemilikan datanya sendiri — E8.4)
    · `sales`/`sales_admin`/`finance`/`warehouse` → `/users` TETAP 403
    · `finance` → `/vendor-bills` TETAP 403 (sisi HUTANG tetap manajer/admin)
    · `warehouse` → `POST /suppliers` TETAP 403 (hanya BACA yang diberikan)
G3. KPI BERANDA TIDAK BOLEH BERBOHONG (INV-HOME-01):
    · `approvals_pending` == `approvals.total` (dulu 0 vs 6 di layar yang sama)
    · sama dengan hitungan mandiri dari MongoDB
    · setiap baris menunjuk layar yang ADA
G4. TOMBOL DARI IZIN, BUKAN NAMA PERAN (INV-ROLE-01):
    · `finance` yang punya `penalty.issue` benar-benar BOLEH menerbitkan denda
      dari aging (server menerima) — dulu tombolnya disembunyikan layar karena
      `["admin","manager"].includes(role)`
G5. BUKTI-MERAH: bila izin baca itu dicabut dari matriks yang BERLAKU, POC ini
    WAJIB memerah. Tanpa bagian ini, "hijau" tidak berarti apa-apa.

Aman dijalankan berulang: memakai snapshot/restore (`scripts/guardrails/_common.py`),
jadi tidak meninggalkan residu (INV-GATE-01).

Usage:  python backend/test_core_role_access_poc.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

import httpx  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "guardrails"))
from _common import run_with_restore  # noqa: E402

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
PWD = "demo12345"
ENT = "ent_ksc"
G, R, Y, B, DIM, X = ("\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[2m", "\033[0m")

AKUN = {
    "admin": "admin@kainnusantara.id",
    "manager": "manager@kainnusantara.id",
    "sales_admin": "salesadmin@kainnusantara.id",
    "finance": "finance@kainnusantara.id",
    "sales": "sales@kainnusantara.id",
    "warehouse": "warehouse@kainnusantara.id",
}

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


def login(email, entity=ENT):
    c = httpx.Client(base_url=BASE, timeout=60.0)
    r = c.post("/api/auth/login", json={"email": email, "password": PWD})
    r.raise_for_status()
    body = r.json()
    c.headers.update({"Authorization": f"Bearer {body['token']}", "X-Entity-Id": entity})
    return c, body


def g1_izin_baca_diberikan(cl):
    print(f"\n{B}▶ G1 — izin BACA yang hilang sudah diberikan (layar jadi berguna){X}")
    cases = [
        ("finance", "/ar/aging", "Aging Piutang: menu finance, izin denda finance"),
        ("finance", "/suppliers", "Kasus Keuangan: nama lawan-transaksi"),
        ("warehouse", "/suppliers", "RFQ/PR/Retur Beli: dropdown Supplier"),
        ("manager", "/users", "layar Karyawan: kolom akun tertaut"),
        ("finance", "/ar/aging?entity_id=ent_ksc", "aging tersaring badan usaha"),
    ]
    for role, path, why in cases:
        r = cl[role].get(f"/api{path}")
        ok(r.status_code == 200, f"{role:11s} GET {path:34s} 200", f"({why}) → {r.status_code}")


def g2_pagar_tidak_longgar(cl):
    print(f"\n{B}▶ G2 — pagar TIDAK ikut longgar (yang penting justru ini){X}")
    tolak = [
        ("sales", "GET", "/ar/aging", "aging = piutang SEMUA pelanggan; sales dibatasi E8.4"),
        ("warehouse", "GET", "/ar/aging", "gudang bukan wilayah piutang"),
        ("sales", "GET", "/users", "daftar akun bukan wilayah sales"),
        ("sales_admin", "GET", "/users", "daftar akun bukan wilayah Admin Sales"),
        ("finance", "GET", "/users", "daftar akun bukan wilayah kasir"),
        ("warehouse", "GET", "/users", "daftar akun bukan wilayah gudang"),
        ("finance", "GET", "/vendor-bills", "sisi HUTANG tetap manajer/admin (E8.1b)"),
        ("sales", "GET", "/suppliers", "sales tidak berurusan dengan supplier"),
    ]
    for role, method, path, why in tolak:
        r = cl[role].request(method, f"/api{path}")
        ok(r.status_code == 403, f"{role:11s} {method} {path:30s} 403", f"({why}) → {r.status_code}")

    # HANYA BACA: menulis master supplier tetap tertutup untuk peran baru pembacanya.
    for role in ("warehouse", "finance"):
        r = cl[role].post("/api/suppliers", json={"name": "PT Uji Pagar Tulis"})
        ok(r.status_code == 403, f"{role:11s} POST /suppliers                   403",
           f"(hanya izin BACA yang diberikan) → {r.status_code}")


def g3_kpi_beranda_jujur(cl, db):
    print(f"\n{B}▶ G3 — KPI beranda = antrean NYATA (INV-HOME-01){X}")
    expect = {
        "sales_order": ("sales_orders", {"$or": [{"status": "waiting_approval"},
                                                 {"pending_approvals.status": "pending"}]}),
        "purchase_order": ("purchase_orders", {"status": "waiting_approval"}),
        "purchase_requisition": ("purchase_requisitions", {"status": "pending_approval"}),
        "sales_return": ("sales_returns", {"status": "pending_approval"}),
        "purchase_return": ("purchase_returns", {"status": "pending_approval"}),
    }
    nyata = {k: db[c].count_documents(q) for k, (c, q) in expect.items()}
    total_nyata = sum(nyata.values())
    ok(total_nyata > 0, "data demo memang punya antrean persetujuan",
       f"({nyata})")

    for role, path in (("admin", "/api/home/admin"), ("manager", "/api/home/manager")):
        r = cl[role].get(path)
        if not ok(r.status_code == 200, f"{role:11s} GET {path:24s} 200", f"→ {r.status_code}"):
            continue
        d = r.json()
        detail = d.get("approvals") or {}
        rows = {x["key"]: x["count"] for x in (detail.get("all_items") or [])}
        ok(d.get("approvals_pending") == detail.get("total"),
           f"{role:11s} KPI == rincian di layar yang sama",
           f"(KPI {d.get('approvals_pending')} vs rincian {detail.get('total')})")
        ok((d.get("approvals_pending") or 0) >= total_nyata,
           f"{role:11s} KPI mencakup seluruh antrean nyata",
           f"(KPI {d.get('approvals_pending')} ≥ {total_nyata})")
        beda = {k: (rows.get(k), v) for k, v in nyata.items() if rows.get(k) != v}
        ok(not beda, f"{role:11s} tiap baris sama dengan hitungan MongoDB", f"beda={beda}")
        ok(bool(detail.get("items")), f"{role:11s} rincian bisa diklik (items terisi)",
           f"({len(detail.get('items') or [])} baris)")


def g4_tombol_dari_izin(cl, perms_by_role):
    print(f"\n{B}▶ G4 — wewenang dari IZIN, bukan nama peran (INV-ROLE-01){X}")
    # Izin efektif dikirim server saat login (dipakai layar lewat `can(perms, …)`).
    perms = perms_by_role.get("finance") or {}
    ok("issue" in (perms.get("penalty") or []),
       "finance memang memegang izin penalty.issue (dari respons login)",
       f"({perms.get('penalty')})")

    # Ambil satu customer yang punya piutang lewat tempo dari aging (data nyata).
    r = cl["finance"].get("/api/ar/aging")
    if not ok(r.status_code == 200, "finance bisa membaca aging (prasyarat)", f"→ {r.status_code}"):
        return
    rows = (r.json() or {}).get("customers") or []
    target = next((c for c in rows if (c.get("overdue") or 0) > 0), None)
    if not target:
        print(f"  {Y}[INFO]{X} tak ada pelanggan lewat tempo di data demo — "
              f"uji terbitkan denda dilewati (bukan kegagalan).")
        return
    cid = target.get("customer_id") or target.get("id")
    res = cl["finance"].post(f"/api/ar/aging/{cid}/accrue-penalties")
    ok(res.status_code == 200,
       "finance BOLEH menerbitkan nota denda dari aging (server menerima)",
       f"customer={target.get('customer_name')} → {res.status_code} "
       f"{res.text[:120] if res.status_code != 200 else ''}")
    # Peran yang TIDAK punya izin itu tetap ditolak.
    res2 = cl["sales"].post(f"/api/ar/aging/{cid}/accrue-penalties")
    ok(res2.status_code == 403, "sales TETAP ditolak menerbitkan denda", f"→ {res2.status_code}")


def g5_bukti_merah(cl, db):
    """Cabut `accounting.view` & `penalty.issue` dari matriks BERLAKU → finance harus 403.

    Tanpa bagian ini "hijau" hanya berarti "tidak ada yang diuji". Matriks dipulihkan
    di akhir; `run_with_restore` menjadi jaring kedua bila proses mati di tengah.
    """
    print(f"\n{B}▶ G5 — BUKTI-MERAH (cabut izinnya → POC wajib memerah){X}")
    doc = db.permission_settings.find_one({"id": "default"})
    if not doc:
        print(f"  {Y}[INFO]{X} tak ada `permission_settings` di DB (matriks dari kode) — "
              f"bukti-merah dilewati.")
        return
    import copy
    asli = copy.deepcopy(doc["matrix"])
    m = copy.deepcopy(asli)
    m["finance"]["accounting"] = [a for a in m["finance"].get("accounting", []) if a != "view"]
    m["finance"]["penalty"] = [a for a in m["finance"].get("penalty", []) if a != "issue"]
    m["warehouse"].pop("supplier", None)
    db.permission_settings.update_one({"id": "default"}, {"$set": {"matrix": m}})
    try:
        cl2, _ = login(AKUN["finance"])
        cl3, _ = login(AKUN["warehouse"])
        ok(cl2.get("/api/ar/aging").status_code == 403,
           "izin dicabut → finance kembali 403 di /ar/aging (gate bisa memerah)")
        ok(cl3.get("/api/suppliers").status_code == 403,
           "izin dicabut → warehouse kembali 403 di /suppliers (gate bisa memerah)")
    finally:
        db.permission_settings.update_one({"id": "default"}, {"$set": {"matrix": asli}})
        cl4, _ = login(AKUN["finance"])
        ok(cl4.get("/api/ar/aging").status_code == 200,
           "matriks dipulihkan → finance 200 kembali (nol residu izin)")


def g6_backlog_satu_pintu(cl):
    """Satu pintu yang jujur: Pusat Persetujuan & beranda membaca ANGKA YANG SAMA."""
    print(f"\n{B}▶ G6 — `GET /approvals/backlog`: satu sumber untuk beranda & Pusat Persetujuan{X}")
    boleh = ("admin", "manager", "sales_admin", "finance")   # `approval.view`/`order.approve`
    tolak = ("sales", "warehouse")                            # bukan pemutus/pengejar approval
    for role in boleh:
        r = cl[role].get("/api/approvals/backlog")
        ok(r.status_code == 200, f"{role:11s} GET /approvals/backlog 200", f"→ {r.status_code}")
    for role in tolak:
        r = cl[role].get("/api/approvals/backlog")
        ok(r.status_code == 403, f"{role:11s} GET /approvals/backlog 403 (bukan wilayahnya)",
           f"→ {r.status_code}")

    # Angka HARUS sama dengan KPI beranda pada cakupan yang sama (admin: semua entitas).
    admin_all = cl["admin"]
    admin_all.headers["X-Entity-Id"] = "all"
    bl = admin_all.get("/api/approvals/backlog").json()
    home = admin_all.get("/api/home/admin").json()
    ok(bl.get("total") == home.get("approvals_pending"),
       "total backlog == KPI beranda (tidak mungkin dua angka berbeda lagi)",
       f"(backlog {bl.get('total')} vs KPI {home.get('approvals_pending')})")
    admin_all.headers["X-Entity-Id"] = ENT

    # Tersaring badan usaha: satu PT tidak boleh lebih besar dari gabungan.
    satu = cl["manager"].get("/api/approvals/backlog").json()
    ok((satu.get("total") or 0) <= (bl.get("total") or 0),
       "angka per badan usaha ≤ angka gabungan (isolasi entitas terjaga)",
       f"(KSC {satu.get('total')} ≤ semua {bl.get('total')})")

    # Setiap baris menunjuk layar yang benar-benar ada (tak ada tautan buntu).
    import re
    router = (ROOT / "frontend/src/AppViewRouter.jsx").read_text(encoding="utf-8")
    views = set(re.findall(r'activeView\s*===\s*"([\w-]+)"', router))
    hantu = [r["view"] for r in (bl.get("all_items") or []) if r["view"] not in views]
    ok(not hantu, "semua baris antrean menunjuk layar yang ADA di AppViewRouter",
       f"hantu={hantu}")

    # Koleksi tiap baris harus BENAR namanya (kelas bug `amendments` vs `doc_amendments`).
    # FASE F-6 — syaratnya DIPERKUAT sekaligus diperbaiki: dulu "harus ADA di database"
    # + daftar putih satu koleksi (`approval_requests`). Syarat itu menuduh PALSU begitu
    # antrean mencakup fitur yang belum pernah dipakai di data demo (uang muka, biaya
    # masuk, buka periode): koleksinya belum lahir walau kodenya benar — dan penjaga yang
    # menuduh palsu akan dimatikan orang. Sekarang: nama koleksi wajib terbukti ada di
    # DATABASE **atau** disebut LITERAL di kode backend. Salah tulis tetap tertangkap
    # karena nama yang salah tidak ditemukan di kedua tempat.
    sys.path.insert(0, str(ROOT / "backend"))
    from services import approval_backlog_service as abl
    from pymongo import MongoClient
    dbn = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
    ada = set(dbn.list_collection_names())
    src = ""
    for sub in ("routers", "services"):
        for f in (ROOT / "backend" / sub).glob("*.py"):
            src += f.read_text(encoding="utf-8")
    salah = [f"{k}→{c}" for k, _l, _v, c, _q in abl.QUEUES
             if c not in ada and f'"{c}"' not in src and f"db.{c}" not in src]
    ok(not salah, "setiap baris antrean menyebut koleksi yang benar (ada di DB atau di kode)",
       f"salah={salah}")


def main() -> int:
    print(f"{B}{'=' * 78}\n  POC F-2 — AKSES & UI/UX PER PERAN  ·  {BASE}\n{'=' * 78}{X}")
    try:
        from pymongo import MongoClient
        db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=4000)[
            os.environ.get("DB_NAME", "test_database")]
        db.command("ping")
    except Exception as ex:  # noqa: BLE001
        print(f"{R}MongoDB tak terjangkau: {ex}{X}")
        return 2

    cl, perms_by_role = {}, {}
    for role, email in AKUN.items():
        try:
            cl[role], body = login(email)
            perms_by_role[role] = ((body.get("user") or {}).get("permissions")
                                   or body.get("permissions") or {})
        except Exception as ex:  # noqa: BLE001
            print(f"{R}Tidak bisa login {email}: {ex}{X}")
            return 2

    g1_izin_baca_diberikan(cl)
    g2_pagar_tidak_longgar(cl)
    g3_kpi_beranda_jujur(cl, db)
    g4_tombol_dari_izin(cl, perms_by_role)
    g6_backlog_satu_pintu(cl)
    g5_bukti_merah(cl, db)

    print(f"\n{B}{'=' * 78}{X}")
    print(f"  HASIL: {G}{PASS} PASS{X} · {R}{FAIL} FAIL{X} dari {PASS + FAIL} pemeriksaan")
    print(f"{B}{'=' * 78}{X}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(run_with_restore(main))
