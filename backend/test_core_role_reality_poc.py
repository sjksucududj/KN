#!/usr/bin/env python3
"""POC **CEK KENYATAAN PERAN** — utang migrasi (ii) FASE E-8/E-6.

Membuktikan satu janji: *daftar "akun `manager` yang sebenarnya Admin Sales/Finance"
dihitung dari JEJAK NYATA dan bisa diterapkan dengan aman.*

APA YANG DIBUKTIKAN
===================
R1  **Menemukan yang salah.** Akun warisan `Rudi Hartono` (peran `manager`, tetapi
    jejaknya hanya verifikasi pesanan · proses retur · penagihan antar-PT)
    disimpulkan `kuasa_berlebih` dengan usulan **Admin Sales** — beserta bukti
    per kegiatan (izin yang dipakai, berapa kali, contoh nomor dokumen).
R2  **TIDAK salah-tuduh.** `Dewi Rahayu` juga `manager`, tetapi ia benar-benar
    menyetujui nilai, menerbitkan denda, dan membuat jurnal → **`sesuai`**.
    Tanpa cek ini "temuan" bisa hanya berarti "semua manajer dicurigai".
R3  **Tanpa jejak = tanpa usulan.** Akun yang belum dipakai tidak diturunkan
    perannya hanya karena sunyi.
R4  **Admin tidak dinilai dari aktivitas** (pagar "admin terakhir").
R5  **Pisah tugas (SD2).** Akun yang mengerjakan alur pesanan DAN uang/pajak
    sekaligus tidak punya satu peran pelaksana pun yang menampungnya →
    `pisah_tugas` + usulan dua akun.
R6  **Di luar peran.** Jejak yang peran sekarang tidak boleh lakukan (mis. `sales`
    menerbitkan faktur pajak) muncul sebagai `di_luar_peran` dan ditandai per baris.
R7  **Laporan ini bukan untuk semua orang**: `sales`/`sales_admin`/`finance` → 403.
R8  **Terap hanya untuk peran USULAN.** Peran lain ditolak 400 dengan kalimat yang
    menuntun — satu salah-klik tidak boleh memindahkan wewenang ke arah yang tak
    pernah dihitung. Peran yang sama juga ditolak.
R9  **Terap yang sah** mengubah peran, **mencabut sesi**, menulis jejak
    `role_reclassified` berisi POTRET BUKTI, dan laporan ikut berubah jadi `sesuai`.
R10 **BUKTI-MERAH (sabotase in-process).** Usulan dihitung dari matriks izin
    sungguhan: begitu `order.verify` dicabut dari `sales_admin`, usulan untuk Rudi
    HARUS berubah (bukan tetap "Admin Sales" karena ditulis di tabel kedua).

Semua percobaan tulis dipulihkan; jejak audit yang lahir dihapus (INV-GATE-01).

Jalankan: `python backend/test_core_role_reality_poc.py`  (butuh backend hidup + seed)
"""
import asyncio
import os
import sys
from pathlib import Path

import httpx

BE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BE_DIR))

try:                                              # pragma: no cover
    from dotenv import load_dotenv
    load_dotenv(BE_DIR / ".env")
except Exception:                                 # noqa: BLE001
    pass

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
PWD = "demo12345"
ENT_A = "ent_ksc"
LEGACY = "user_manager_02"        # Rudi Hartono — `manager` yang pekerjaannya Admin Sales
REAL_MANAGER = "user_manager_01"  # Dewi Rahayu — manajer sungguhan
SALES = "user_sales_01"           # Ayu Permatasari

GREEN, RED, YEL, CYAN, RST = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[0m"
RESULTS = []
TOKENS = []
POC_AUDIT_IDS = []                # baris audit yang SENGAJA dibuat POC ini


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    tag = f"{GREEN}PASS{RST}" if ok else f"{RED}FAIL{RST}"
    print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))
    return bool(ok)


def head(text):
    print(f"\n{CYAN}\033[1m{text}{RST}")


def client(email, entity=ENT_A):
    cl = httpx.Client(base_url=BASE, timeout=90.0)
    r = cl.post("/api/auth/login", json={"email": email, "password": PWD})
    r.raise_for_status()
    body = r.json()
    cl.headers.update({"Authorization": f"Bearer {body['token']}",
                       "X-Entity-Id": entity})
    TOKENS.append(body["token"])
    return cl


def _mongo():
    """Koneksi sendiri: klien motor global terikat event loop pertama."""
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(os.environ["MONGO_URL"])


async def _audit_ids():
    cl = _mongo()
    try:
        db = cl[os.environ["DB_NAME"]]
        return {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
    finally:
        cl.close()


async def _insert_audit(rows):
    cl = _mongo()
    try:
        db = cl[os.environ["DB_NAME"]]
        await db.audit_logs.insert_many(rows)
        POC_AUDIT_IDS.extend(r["id"] for r in rows)
    finally:
        cl.close()


async def _delete_audit(ids):
    cl = _mongo()
    try:
        db = cl[os.environ["DB_NAME"]]
        await db.audit_logs.delete_many({"id": {"$in": list(ids)}})
    finally:
        cl.close()


async def _set_role(user_id, role):
    cl = _mongo()
    try:
        db = cl[os.environ["DB_NAME"]]
        await db.users.update_one({"id": user_id}, {"$set": {"role": role}})
    finally:
        cl.close()


async def _cleanup(before_ids, role_restore):
    """INV-GATE-01 — POC tidak boleh meninggalkan residu."""
    cl = _mongo()
    try:
        db = cl[os.environ["DB_NAME"]]
        for uid, role in role_restore.items():
            await db.users.update_one({"id": uid}, {"$set": {"role": role}})
        await db.sessions.delete_many({"token": {"$in": TOKENS}})
        now_ids = {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
        baru = now_ids - before_ids
        if baru:
            await db.audit_logs.delete_many({"id": {"$in": list(baru)}})
        sisa = await db.audit_logs.count_documents({"id": {"$in": list(baru)}})
        return len(baru), sisa
    finally:
        cl.close()


def report(cl, **params):
    r = cl.get("/api/access/role-reality", params=params or None)
    r.raise_for_status()
    return r.json()


def row_of(rep, user_id):
    for r in rep.get("rows", []):
        if r["user_id"] == user_id:
            return r
    return {}


# ─── R1–R4 · kesimpulan dasar ────────────────────────────────────────────────
def a_findings(adm):
    head("LANGKAH 1 — menemukan yang salah TANPA salah-tuduh (R1–R4)")
    rep = report(adm)
    check("laporan menyebut metodenya di layar (bukan angka turun dari langit)",
          "jejak" in (rep.get("method") or "").lower(),
          (rep.get("method") or "")[:60] + "…")

    rudi = row_of(rep, LEGACY)
    check("R1 · akun warisan `manager` ditemukan sebagai KUASA BERLEBIH",
          rudi.get("verdict") == "kuasa_berlebih",
          f"{rudi.get('name')} → {rudi.get('verdict')}")
    check("R1 · usulannya Admin Sales (peran pelaksana yang tepat)",
          rudi.get("suggested_role") == "sales_admin",
          f"usul={rudi.get('suggested_role_label')}")
    izin = {e["permission"] for e in rudi.get("evidence", [])}
    check("R1 · buktinya memuat izin yang benar-benar dipakai",
          {"order.verify", "sales_return.update", "interco.invoice"} <= izin,
          " · ".join(sorted(izin)))
    contoh = [s for e in rudi.get("evidence", []) for s in e.get("samples", [])]
    check("R1 · bukti menyebut NOMOR DOKUMEN nyata (bisa dicek pemilik)",
          any(s.startswith(("SO-", "SRET-", "KSC/")) for s in contoh),
          " · ".join(contoh[:4]))
    check("R1 · kesimpulan dijelaskan dengan kalimat manusia",
          "Admin Sales" in (rudi.get("headline") or ""),
          (rudi.get("headline") or "")[:70])
    check("R1 · nama badan usaha tampil sebagai NAMA SINGKAT (INV-UI-02)",
          rudi.get("home_entity_name") == "KSC"
          and not str(rudi.get("home_entity_name")).startswith("ent_"),
          f"home={rudi.get('home_entity_name')}")

    dewi = row_of(rep, REAL_MANAGER)
    check("R2 · manajer SUNGGUHAN tidak ikut dituduh (bukti-merah pembeda)",
          dewi.get("verdict") == "sesuai" and not dewi.get("suggested_role"),
          f"{dewi.get('name')} → {dewi.get('verdict')}")
    dewi_izin = {e["permission"] for e in dewi.get("evidence", [])}
    check("R2 · alasannya terlihat: ia memakai izin khusus manajer",
          bool(dewi_izin & {"order.approve", "penalty.issue", "accounting.create",
                            "sales_return.approve", "price_approval.approve"}),
          " · ".join(sorted(dewi_izin & {"order.approve", "penalty.issue",
                                         "accounting.create", "sales_return.approve",
                                         "price_approval.approve"})))

    sunyi = [r for r in rep["rows"] if r["activity_total"] == 0]
    check("R3 · akun tanpa jejak TIDAK diberi usulan (sistem tidak menebak)",
          bool(sunyi) and all(r["verdict"] == "tanpa_jejak" and not r["suggested_role"]
                              for r in sunyi),
          f"{len(sunyi)} akun sunyi")

    admins = [r for r in rep["rows"] if r["role"] == "admin"]
    check("R4 · admin sistem tidak diusulkan turun peran",
          bool(admins) and all(not r["suggested_role"] for r in admins),
          f"{len(admins)} admin")

    s = rep.get("summary", {})
    check("ringkasan konsisten dengan barisnya",
          s.get("accounts") == len(rep["rows"])
          and s.get("kuasa_berlebih") == sum(1 for r in rep["rows"]
                                             if r["verdict"] == "kuasa_berlebih"),
          f"{s.get('accounts')} akun · {s.get('perlu_ditinjau')} perlu ditinjau")
    check("cakupan dilaporkan jujur (kegiatan belum dipetakan tetap disebut)",
          isinstance(rep.get("unmapped_actions"), list)
          and rep.get("activities_mapped", 0) >= 30,
          f"{rep.get('activities_mapped')} dipetakan · "
          f"{len(rep.get('unmapped_actions') or [])} belum")
    return rep


# ─── R5 · pisah tugas ────────────────────────────────────────────────────────
def b_segregation(adm):
    head("LANGKAH 2 — satu orang mengerjakan pesanan DAN uang/pajak (R5)")
    rows = [
        {"id": "audit_poc_rr_sod_1", "user_id": LEGACY, "user_name": "Rudi Hartono",
         "action": "ar_receipt_created", "resource": "ar_receipt",
         "resource_id": "poc_rr_ar", "details": {"number": "KSC/AR-POC"},
         "timestamp": "2026-08-01T02:00:00+00:00", "scope_entity_id": ENT_A},
        {"id": "audit_poc_rr_sod_2", "user_id": LEGACY, "user_name": "Rudi Hartono",
         "action": "tax_invoice_issued", "resource": "tax_invoice",
         "resource_id": "poc_rr_fkt", "details": {"number": "KSC/FKT-POC"},
         "timestamp": "2026-08-02T02:00:00+00:00", "scope_entity_id": ENT_A},
    ]
    asyncio.run(_insert_audit(rows))
    rudi = row_of(report(adm), LEGACY)
    check("R5 · kesimpulannya berubah menjadi PERLU PISAH TUGAS",
          rudi.get("verdict") == "pisah_tugas", f"→ {rudi.get('verdict')}")
    check("R5 · tidak ada satu peran pun yang diusulkan (memang harus dua akun)",
          not rudi.get("suggested_role"), f"usul={rudi.get('suggested_role') or '—'}")
    split = {s["domain"]: s["suggested_role"] for s in rudi.get("split", [])}
    check("R5 · alur pesanan diusulkan ke Admin Sales",
          split.get("alur_pesanan") == "sales_admin", str(split))
    check("R5 · uang & pajak diusulkan ke Finance",
          split.get("uang_pajak") == "finance", str(split))
    check("R5 · alasannya menyebut jalan keluarnya: DUA akun",
          "dua akun" in (rudi.get("headline") or "").lower()
          and "uang/pajak" in (rudi.get("headline") or "").lower(),
          (rudi.get("headline") or "")[:100])
    asyncio.run(_delete_audit([r["id"] for r in rows]))
    check("R5 · keadaan kembali seperti semula setelah jejak uji dihapus",
          row_of(report(adm), LEGACY).get("verdict") == "kuasa_berlebih")


# ─── R6 · di luar peran ──────────────────────────────────────────────────────
def c_beyond_role(adm):
    head("LANGKAH 3 — jejak yang peran sekarang TIDAK boleh lakukan (R6)")
    rows = [
        {"id": "audit_poc_rr_beyond_1", "user_id": SALES,
         "user_name": "Ayu Permatasari", "action": "tax_invoice_issued",
         "resource": "tax_invoice", "resource_id": "poc_rr_fkt2",
         "details": {"number": "KSC/FKT-POC2"},
         "timestamp": "2026-08-03T02:00:00+00:00", "scope_entity_id": ENT_A},
    ]
    asyncio.run(_insert_audit(rows))
    ayu = row_of(report(adm), SALES)
    check("R6 · sales yang pernah menerbitkan faktur pajak → DI LUAR PERAN",
          ayu.get("verdict") == "di_luar_peran", f"→ {ayu.get('verdict')}")
    ditandai = [e for e in ayu.get("evidence", []) if e.get("beyond_current_role")]
    check("R6 · baris buktinya ditandai satu per satu (bukan hanya kesimpulan)",
          any(e["permission"] == "tax_invoice.create" for e in ditandai),
          " · ".join(e["permission"] for e in ditandai))
    check("R6 · usulannya peran yang memang boleh melakukannya",
          ayu.get("suggested_role") in ("finance", "manager", "admin"),
          f"usul={ayu.get('suggested_role_label')}")
    asyncio.run(_delete_audit([r["id"] for r in rows]))
    check("R6 · sales kembali `sesuai` setelah jejak uji dihapus",
          row_of(report(adm), SALES).get("verdict") == "sesuai")


# ─── R7 · siapa boleh membaca laporan ────────────────────────────────────────
def d_permission(sales, sa, fin):
    head("LANGKAH 4 — laporan wewenang bukan untuk semua orang (R7)")
    for nama, cl in (("sales", sales), ("Admin Sales", sa), ("Finance", fin)):
        r = cl.get("/api/access/role-reality")
        check(f"R7 · {nama} DITOLAK membaca laporan cek peran",
              r.status_code == 403, f"HTTP {r.status_code}")
        r2 = cl.post(f"/api/access/role-reality/{LEGACY}/apply",
                     json={"role": "sales_admin"})
        check(f"R7 · {nama} DITOLAK menerapkan perubahan peran",
              r2.status_code == 403, f"HTTP {r2.status_code}")


# ─── R8/R9 · terap ───────────────────────────────────────────────────────────
def e_apply(adm):
    head("LANGKAH 5 — menerapkan usulan dengan aman (R8/R9)")
    r = adm.post(f"/api/access/role-reality/{LEGACY}/apply", json={"role": "finance"})
    detail = str((r.json() or {}).get("detail", ""))
    check("R8 · peran yang BUKAN usulan ditolak",
          r.status_code == 400, f"HTTP {r.status_code}")
    check("R8 · penolakannya MENUNTUN (menyebut usulan yang sah & jalur manual)",
          "Admin Sales" in detail and "formulir akun" in detail, detail[:90])

    r = adm.post(f"/api/access/role-reality/{LEGACY}/apply", json={"role": "manager"})
    check("R8 · peran yang sama dengan sekarang juga ditolak",
          r.status_code == 400, f"HTTP {r.status_code}")

    r = adm.post(f"/api/access/role-reality/{LEGACY}/apply",
                 json={"role": "sales_admin", "note": "POC cek peran"})
    ok = r.status_code == 200
    body = r.json() if ok else {}
    check("R9 · usulan yang sah berhasil diterapkan", ok, f"HTTP {r.status_code}")
    check("R9 · pesannya menyebut peran lama → peran baru",
          "Manajer" in (body.get("message") or "")
          and "Admin Sales" in (body.get("message") or ""),
          (body.get("message") or "")[:90])
    check("R9 · sesinya dicabut supaya izin baru benar-benar berlaku",
          "sesi dicabut" in (body.get("message") or ""),
          f"sessions_revoked={body.get('sessions_revoked')}")

    after = row_of(report(adm), LEGACY)
    check("R9 · laporan ikut berubah: akun itu kini `sesuai`",
          after.get("role") == "sales_admin" and after.get("verdict") == "sesuai",
          f"{after.get('role')} → {after.get('verdict')}")

    jejak = asyncio.run(_find_audit("role_reclassified"))
    check("R9 · jejak audit `role_reclassified` tertulis", bool(jejak))
    # `dependencies.audit()` menyimpan rinciannya di kolom **`after`** (bukan
    # `details` seperti baris seed) — dua bentuk baris audit yang hidup bersama di
    # repo ini. POC membaca keduanya supaya tidak lulus karena salah kolom.
    det = (jejak or {}).get("after") or (jejak or {}).get("details") or {}
    check("R9 · jejaknya menyimpan POTRET BUKTI (bisa dijawab 6 bulan kemudian)",
          det.get("from_role") == "manager" and det.get("to_role") == "sales_admin"
          and len(det.get("evidence") or []) >= 3,
          f"{len(det.get('evidence') or [])} baris bukti tersimpan")

    asyncio.run(_set_role(LEGACY, "manager"))
    check("R9 · keadaan dipulihkan (peran dikembalikan ke manager)",
          row_of(report(adm), LEGACY).get("role") == "manager")


async def _find_audit(action):
    cl = _mongo()
    try:
        db = cl[os.environ["DB_NAME"]]
        return await db.audit_logs.find_one({"action": action}, {"_id": 0})
    finally:
        cl.close()


# ─── R10 · bukti-merah: usulan lahir dari matriks izin sungguhan ─────────────
def f_red_proof():
    head("LANGKAH 6 — BUKTI-MERAH: sabotase matriks izin harus mengubah usulan (R10)")

    async def run():
        import copy
        from services import role_reality_service as svc

        cl = _mongo()
        db = cl[os.environ["DB_NAME"]]
        try:
            rep = await svc.build_report()
            semula = next((r for r in rep["rows"] if r["user_id"] == LEGACY), {})

            # Matriks YANG BENAR-BENAR BERLAKU: baris `permission_settings` bila ada
            # (pemilik boleh menyuntingnya di Pusat Pengaturan), jika tidak ada baru
            # bawaan kode. Sabotase harus menyerang yang berlaku — kalau tidak,
            # "bukti-merah" hanya menguji cabang yang tidak dipakai.
            rec = await db.permission_settings.find_one({"id": "default"}, {"_id": 0})
            asli_db = copy.deepcopy(rec.get("matrix")) if rec and rec.get("matrix") else None
            asli_kode = svc.DEFAULT_PERMISSIONS
            try:
                if asli_db is not None:
                    rusak = copy.deepcopy(asli_db)
                    rusak["sales_admin"]["order"] = [
                        a for a in rusak["sales_admin"]["order"] if a != "verify"]
                    await db.permission_settings.update_one(
                        {"id": "default"}, {"$set": {"matrix": rusak}})
                else:
                    rusak = copy.deepcopy(asli_kode)
                    rusak["sales_admin"]["order"] = [
                        a for a in rusak["sales_admin"]["order"] if a != "verify"]
                    svc.DEFAULT_PERMISSIONS = rusak
                rep2 = await svc.build_report()
                disabotase = next((r for r in rep2["rows"]
                                   if r["user_id"] == LEGACY), {})
            finally:
                if asli_db is not None:
                    await db.permission_settings.update_one(
                        {"id": "default"}, {"$set": {"matrix": asli_db}})
                else:
                    svc.DEFAULT_PERMISSIONS = asli_kode
            rep3 = await svc.build_report()
            pulih = next((r for r in rep3["rows"] if r["user_id"] == LEGACY), {})
            sumber = "baris permission_settings" if asli_db is not None else "bawaan kode"
            return semula, disabotase, pulih, sumber
        finally:
            cl.close()

    semula, sabot, pulih, sumber = asyncio.run(run())
    check("R10 · sebelum sabotase: usulan = Admin Sales",
          semula.get("suggested_role") == "sales_admin",
          f"usul={semula.get('suggested_role')} · matriks dari {sumber}")
    check("R10 · setelah `order.verify` dicabut dari Admin Sales, usulan BERUBAH "
          "(usulan memang dibaca dari matriks izin, bukan tabel kedua)",
          sabot.get("suggested_role") != "sales_admin",
          f"usul={sabot.get('suggested_role') or '—'} · "
          f"kesimpulan={sabot.get('verdict')}")
    check("R10 · matriks dipulihkan → usulan kembali Admin Sales",
          pulih.get("suggested_role") == "sales_admin",
          f"usul={pulih.get('suggested_role')}")


def main():
    print(f"{CYAN}\033[1m{'=' * 78}\n  POC CEK KENYATAAN PERAN — utang migrasi (ii) "
          f"FASE E-8\n  {BASE}\n{'=' * 78}{RST}")
    audit_before = asyncio.run(_audit_ids())
    role_restore = {LEGACY: "manager"}
    try:
        adm = client("admin@kainnusantara.id")
        sales = client("sales@kainnusantara.id")
        sa = client("salesadmin@kainnusantara.id")
        fin = client("finance@kainnusantara.id")
    except Exception as exc:  # noqa: BLE001
        print(f"{RED}Tidak bisa login: {exc}{RST}")
        return 1

    try:
        a_findings(adm)
        b_segregation(adm)
        c_beyond_role(adm)
        d_permission(sales, sa, fin)
        e_apply(adm)
        f_red_proof()
    finally:
        print(f"\n{YEL}── CLEANUP (INV-GATE-01: nol residu){RST}")
        dihapus, sisa = asyncio.run(_cleanup(audit_before, role_restore))
        check("CLEANUP: nol residu audit_logs & sessions · peran dipulihkan",
              sisa == 0, f"dihapus={dihapus} sisa={sisa}")

    ok = sum(1 for _, o, _ in RESULTS if o)
    bad = [n for n, o, _ in RESULTS if not o]
    print(f"\n{CYAN}{'=' * 78}{RST}")
    print(f"  {GREEN if not bad else RED}{ok}/{len(RESULTS)} PASS{RST}")
    if bad:
        print(f"{RED}  GAGAL:{RST}")
        for n in bad:
            print(f"   - {n}")
    print(f"{CYAN}{'=' * 78}{RST}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
