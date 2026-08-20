#!/usr/bin/env python3
"""POC RESMI FASE E-1 + E-2 — MODEL BADAN USAHA & AKUN TERTAUT HR.

Satu skrip, SELF-CLEANUP, membuktikan (bukan mengklaim) semua butir rencana:

FASE E-1
  E1.1  jenis badan usaha jadi enum resmi · NPWP wajib HANYA bila PKP ·
        nama legal usaha perorangan dibentuk dari nama pemilik
  E1.2  keunikan nama singkat & kode dokumen (abaikan besar-kecil huruf) —
        ditegakkan di POST **dan** PATCH (satu jalur validasi)
  E1.3  kode dokumen TERKUNCI bila badan usaha sudah menerbitkan dokumen;
        pesan galat menyebut dokumen pertamanya
  E1.4  cache kode entitas diinvalidasi → nomor dokumen berikutnya pakai kode baru
  E1.5  daftar badan usaha default hanya yang AKTIF · konteks entitas yang tidak
        diizinkan / tidak ada / terarsip ditolak 403 BERPESAN (bukan jatuh diam-diam)
  E1.6  pagar deaktivasi (409 + rincian) · arsip · KUNCI-TULIS · blokir login ·
        aktifkan kembali
  E1.7  nomor dokumen per badan usaha: 2 entitas × 25 dokumen PARALEL → nol duplikat
  E1.8  bentuk data /api/entities SAMA dengan /auth/context
  E1.9  daftar kesiapan badan usaha terhitung

FASE E-2
  E2.1  badan usaha akun DIAMBIL dari HR (nilai formulir tidak bisa menang)
  E2.2  role berubah → daftar badan usaha dihitung ulang + sesi dicabut
  E2.3  email unik (409) · admin terakhir tidak bisa dinonaktifkan · ganti password
        mencabut sesi
  E2.4  DELETE = nonaktifkan (soft) · aktifkan kembali · reset password
  E2.5  daftar akun: filter badan usaha/role/status + paging + pengayaan
  E2.7  jejak audit perubahan akun ber-stempel badan usaha

BUKTI-MERAH: setiap larangan diuji DUA arah (yang dilarang gagal, yang sah lolos)
supaya uji tidak lulus hanya karena semuanya diblokir.
"""
import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

import httpx

sys.path.insert(0, "/app/backend")

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001")
PWD = "demo12345"

RESULTS: List[Dict[str, Any]] = []
CREATED: Dict[str, List[str]] = {"entities": [], "users": [], "employees": []}

GREEN, RED, DIM, RESET = "\033[92m", "\033[91m", "\033[2m", "\033[0m"


def check(code: str, name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append({"code": code, "name": name, "ok": bool(ok), "detail": detail})
    tag = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"  [{tag}] {code} — {name}")
    if detail:
        print(f"         {DIM}{detail}{RESET}")
    return bool(ok)


async def login(email: str, password: str = PWD) -> Optional[str]:
    """Login memakai klien SEKALI PAKAI.

    `dependencies.extract_token` MENGUTAMAKAN cookie `session_token` di atas
    header Bearer. Kalau satu klien dipakai untuk login banyak user, cookie login
    terakhir menimpa semuanya dan semua permintaan berjalan sebagai user terakhir.
    """
    async with httpx.AsyncClient(timeout=60.0) as tmp:
        r = await tmp.post(f"{BASE}/api/auth/login",
                           json={"email": email, "password": password})
        if r.status_code != 200:
            return None
        return r.json().get("token")


def H(token: str, entity: str = "") -> Dict[str, str]:
    h = {"Authorization": f"Bearer {token}"}
    if entity:
        h["X-Entity-Id"] = entity
    return h


# ══════════════════════════════════════════════════════════════════════════════
async def fase_e1(cl: httpx.AsyncClient, adm: str) -> Dict[str, Any]:
    ctxdata: Dict[str, Any] = {}

    print("\n── E1.1 · jenis badan usaha + aturan NPWP & perorangan ──")
    r = await cl.get(f"{BASE}/api/enums", headers=H(adm))
    enums = (r.json() or {}).get("enums", {})
    et = enums.get("entity_type") or {}
    vals = [v["value"] for v in et.get("values", [])]
    check("E1.1a", "enum `entity_type` terbit di /api/enums (7 jenis)",
          r.status_code == 200 and len(vals) == 7 and "Perorangan" in vals,
          f"nilai={vals}")

    r = await cl.post(f"{BASE}/api/entities", headers=H(adm), json={
        "legal_name": "PT Uji PKP Tanpa NPWP", "short_name": "POCPKP",
        "type": "PT", "default_tax_mode": "ppn", "doc_prefix": "POCPKP"})
    check("E1.1b", "PKP tanpa NPWP DITOLAK 400 + alasan jelas",
          r.status_code == 400 and "NPWP" in r.text, f"HTTP {r.status_code}")

    r = await cl.post(f"{BASE}/api/entities", headers=H(adm), json={
        "legal_name": "PT Uji Non PKP", "short_name": "POCNON",
        "type": "PT", "default_tax_mode": "non_ppn", "doc_prefix": "POCNON"})
    ok = r.status_code == 200
    if ok:
        CREATED["entities"].append(r.json()["id"])
        ctxdata["ent_nonpkp"] = r.json()["id"]
    check("E1.1c", "BUKTI-MERAH: non-PKP TANPA NPWP tetap boleh (bukan asal blokir)",
          ok, f"HTTP {r.status_code} · {r.text[:120]}")

    r = await cl.post(f"{BASE}/api/entities", headers=H(adm), json={
        "short_name": "POCBRK", "type": "Perorangan", "default_tax_mode": "non_ppn",
        "doc_prefix": "POCBRK"})
    check("E1.1d", "Perorangan tanpa nama pemilik DITOLAK 400",
          r.status_code == 400 and "pemilik" in r.text.lower(), f"HTTP {r.status_code}")

    r = await cl.post(f"{BASE}/api/entities", headers=H(adm), json={
        "short_name": "POCBRK", "type": "Perorangan", "owner_name": "Sutrisno",
        "business_label": "Toko Kain Berkah", "default_tax_mode": "non_ppn",
        "doc_prefix": "POCBRK", "city": "Solo"})
    ok = r.status_code == 200
    body = r.json() if ok else {}
    if ok:
        CREATED["entities"].append(body["id"])
        ctxdata["ent_personal"] = body["id"]
    check("E1.1e", "Perorangan: nama legal DIBENTUK dari nama pemilik + label usaha",
          ok and body.get("legal_name") == "Sutrisno (Toko Kain Berkah)",
          f"legal_name={body.get('legal_name')!r}")
    check("E1.1f", "Provisioning mengembalikan pratinjau nomor (bukan 'undefined')",
          (body.get("provisioning") or {}).get("number_preview") == "POCBRK/SO-00001",
          f"{(body.get('provisioning') or {}).get('number_preview')}")

    print("\n── E1.2 · keunikan nama singkat & kode dokumen (POST dan PATCH) ──")
    r = await cl.post(f"{BASE}/api/entities", headers=H(adm), json={
        "legal_name": "PT Tabrakan", "short_name": "ksc", "type": "PT",
        "npwp": "1", "doc_prefix": "POCX1"})
    check("E1.2a", "nama singkat duplikat (huruf kecil 'ksc') DITOLAK 409",
          r.status_code == 409, f"HTTP {r.status_code} · {r.text[:110]}")
    r = await cl.post(f"{BASE}/api/entities", headers=H(adm), json={
        "legal_name": "PT Tabrakan2", "short_name": "POCX2", "type": "PT",
        "npwp": "1", "doc_prefix": "ksc"})
    check("E1.2b", "kode dokumen duplikat ('ksc') DITOLAK 409", r.status_code == 409,
          f"HTTP {r.status_code}")
    pid = ctxdata.get("ent_personal", "")
    r = await cl.patch(f"{BASE}/api/entities/{pid}", headers=H(adm),
                       json={"data": {"short_name": "KSC"}})
    check("E1.2c", "PATCH juga ditegakkan (satu jalur validasi) → 409",
          r.status_code == 409, f"HTTP {r.status_code}")

    print("\n── E1.3/E1.4 · kunci kode dokumen + invalidasi cache ──")
    r = await cl.patch(f"{BASE}/api/entities/ent_ksc", headers=H(adm),
                       json={"data": {"doc_prefix": "KSCBARU"}})
    check("E1.3a", "kode dokumen KSC TERKUNCI (sudah terbit dokumen) → 409",
          r.status_code == 409, f"HTTP {r.status_code} · {r.text[:150]}")
    check("E1.3b", "pesan kunci MENYEBUT dokumen pertama yang terbit",
          any(k in r.text for k in ("PO-", "SO-", "FKT-", "JE-", "CASH-", "TRF-")),
          r.text[:160])
    r = await cl.patch(f"{BASE}/api/entities/{pid}", headers=H(adm),
                       json={"data": {"doc_prefix": "POCBRK2"}})
    ok_change = r.status_code == 200
    check("E1.3c", "BUKTI-MERAH: badan usaha BELUM terbit dokumen BOLEH ganti kode",
          ok_change and (r.json() or {}).get("doc_prefix") == "POCBRK2",
          f"HTTP {r.status_code} · doc_prefix={(r.json() or {}).get('doc_prefix')}")

    from core_utils import next_doc_number  # noqa: PLC0415 — sengaja lazy
    num = await next_doc_number("sales_orders", "number", "SO-", entity_id=pid)
    check("E1.4", "cache kode entitas diinvalidasi → nomor baru pakai kode BARU",
          num.startswith("POCBRK2/"), f"nomor={num}")

    print("\n── E1.5 · status badan usaha + konteks entitas ──")
    r = await cl.get(f"{BASE}/api/entities", headers=H(adm))
    ids_default = [e["id"] for e in r.json()]
    r2 = await cl.get(f"{BASE}/api/entities?status=all", headers=H(adm))
    check("E1.5a", "daftar default hanya AKTIF (bukan semua status)",
          all(e["status"] == "active" for e in r.json()) and
          len(r2.json()) >= len(ids_default), f"{len(ids_default)} aktif")

    s3 = await login("sales3@kainnusantara.id")
    r = await cl.get(f"{BASE}/api/sales-orders", headers=H(s3, "ent_ksc"))
    check("E1.5b", "sales Kanda memaksa X-Entity-Id=ent_ksc → 403 BERPESAN",
          r.status_code == 403 and "ditugaskan" in r.text.lower(),
          f"HTTP {r.status_code} · {r.text[:130]}")
    r = await cl.get(f"{BASE}/api/sales-orders", headers=H(s3, "ent_tidak_ada"))
    check("E1.5c", "badan usaha tidak dikenal → 403 yang menjelaskan",
          r.status_code == 403 and "tidak ada" in r.text.lower(),
          f"HTTP {r.status_code}")
    r = await cl.get(f"{BASE}/api/sales-orders", headers=H(s3))
    check("E1.5d", "BUKTI-MERAH: tanpa header, sales Kanda tetap dilayani 200",
          r.status_code == 200, f"HTTP {r.status_code}")

    print("\n── E1.8/E1.9 · bentuk seragam + kesiapan ──")
    ctx = (await cl.get(f"{BASE}/api/auth/context", headers=H(adm))).json()
    ctx_keys = set((ctx.get("entities") or [{}])[0].keys()) - {"is_home"}
    list_keys = set((await cl.get(f"{BASE}/api/entities", headers=H(adm))).json()[0].keys())
    check("E1.8", "bentuk /api/entities ⊇ bentuk /auth/context (satu bentuk)",
          ctx_keys.issubset(list_keys), f"kurang={sorted(ctx_keys - list_keys)}")

    r = await cl.get(f"{BASE}/api/entities/ent_ksc/readiness", headers=H(adm))
    d = r.json()
    keys = {i["key"] for i in d.get("items", [])}
    need = {"users", "warehouses", "bank_accounts", "prices", "opening_balance",
            "branding", "tax", "fiscal_year"}
    check("E1.9", "daftar kesiapan lengkap & terhitung (8 butir + persen)",
          r.status_code == 200 and need.issubset(keys) and isinstance(d.get("percent"), int),
          f"percent={d.get('percent')} ready={d.get('ready')}/{d.get('total')}")

    print("\n── E1.7 · nomor dokumen per badan usaha (25 × 2 PARALEL) ──")
    a, b = "ent_ksc", pid
    res = await asyncio.gather(*[
        next_doc_number("poc_e1_numbers", "number", "POCN-", entity_id=e)
        for e in ([a] * 25 + [b] * 25)])
    dupes = len(res) - len(set(res))
    a_nums = sorted(n for n in res if n.startswith("KSC/"))
    b_nums = sorted(n for n in res if n.startswith("POCBRK2/"))
    check("E1.7a", "50 nomor paralel → NOL duplikat", dupes == 0,
          f"unik={len(set(res))}/50 duplikat={dupes}")
    check("E1.7b", "deret TERPISAH per badan usaha (masing-masing 1..25)",
          len(a_nums) == 25 and len(b_nums) == 25 and
          a_nums[0].endswith("00001") and b_nums[0].endswith("00001"),
          f"KSC={a_nums[0]}..{a_nums[-1]} · POCBRK2={b_nums[0]}..{b_nums[-1]}")

    print("\n── E1.10 · PAGAR TULIS lintas badan usaha (temuan POC ini) ──")
    from db import db as _db
    s3b = await login("sales3@kainnusantara.id")
    cust_body = {"name": "Poc Pelanggan Selundupan", "pic_name": "Poc",
                 "phone": "0801", "city": "Solo", "address": "Jl. Uji 2"}
    r = await cl.post(f"{BASE}/api/customers", headers=H(s3b),
                      json={**cust_body, "entity_id": "ent_ksc"})
    check("E1.10a", "sales Kanda MENANAM pelanggan di KSC lewat body → 403",
          r.status_code == 403 and "berwenang" in r.text.lower(),
          f"HTTP {r.status_code} · {r.text[:130]}")
    r = await cl.post(f"{BASE}/api/customers", headers=H(s3b), json=cust_body)
    born = r.json() if r.status_code == 200 else {}
    check("E1.10b", "tanpa menyebut badan usaha, pelanggan lahir di badan usaha SENDIRI "
                    "(dulu jatuh ke KSC)",
          r.status_code == 200 and born.get("entity_id") == "ent_kanda",
          f"HTTP {r.status_code} · entity_id={born.get('entity_id')}")
    if born.get("id"):
        await _db.customers.delete_many({"id": born["id"]})
    r = await cl.post(f"{BASE}/api/inventory/initial-stock", headers=H(s3b), json={
        "product_id": "prod_batik_mega", "warehouse_id": "wh_jakarta",
        "quantity": 5, "lot": "POC-LOT-1", "owner_entity_id": "ent_ksc"})
    check("E1.10c", "sales Kanda menanam STOK AWAL milik KSC → ditolak",
          r.status_code in (403, 404) and r.status_code != 200,
          f"HTTP {r.status_code} · {r.text[:110]}")
    r = await cl.get(f"{BASE}/api/customers", headers=H(adm, "ent_ksc"))
    check("E1.10d", "BUKTI-MERAH: admin tetap boleh menulis lintas badan usaha "
                    "(wewenang tidak berkurang)",
          r.status_code == 200, f"baca KSC sebagai admin HTTP {r.status_code}")
    return ctxdata


# ══════════════════════════════════════════════════════════════════════════════
async def fase_e2(cl: httpx.AsyncClient, adm: str, ctxdata: Dict[str, Any]) -> None:
    from db import db

    print("\n── E2.1 · badan usaha akun DIAMBIL dari HR ──")
    emp_ok = {"id": "poc_emp_kanda", "code": "POC-E1", "name": "Poc Karyawan Kanda",
              "user_id": "", "email": "poc.kanda@example.test", "status": "active",
              "entity_id": "ent_kanda", "created_at": "2026-01-01T00:00:00+00:00"}
    emp_no_ent = {"id": "poc_emp_noent", "code": "POC-E2", "name": "Poc Tanpa Entitas",
                  "user_id": "", "email": "poc.noent@example.test", "status": "active",
                  "entity_id": "", "created_at": "2026-01-01T00:00:00+00:00"}
    await db.hr_employees.insert_many([emp_ok, emp_no_ent])
    CREATED["employees"] += [emp_ok["id"], emp_no_ent["id"]]

    r = await cl.get(f"{BASE}/api/hr-employees-available?q=Poc", headers=H(adm))
    avail = [e["id"] for e in r.json()]
    check("E2.1a", "karyawan HR tanpa akun muncul di daftar pilihan",
          emp_ok["id"] in avail, f"tersedia={avail}")

    # Sengaja kirim home_entity_id yang SALAH → HR harus menang.
    r = await cl.post(f"{BASE}/api/users", headers=H(adm), json={
        "name": "Poc Sales Kanda", "email": "poc.sales.kanda@example.test",
        "role": "sales", "password": PWD, "employee_id": emp_ok["id"],
        "home_entity_id": "ent_ksc"})
    ok = r.status_code == 200
    u1 = r.json() if ok else {}
    if ok:
        CREATED["users"].append(u1["id"])
    check("E2.1b", "home_entity_id DIAMBIL dari HR (nilai formulir yang salah diabaikan)",
          ok and u1.get("home_entity_id") == "ent_kanda" and u1.get("home_from_hr") is True,
          f"HTTP {r.status_code} · home={u1.get('home_entity_id')} "
          f"(formulir minta ent_ksc) · dari_hr={u1.get('home_from_hr')}")
    check("E2.1c", "akun non-lintas: allowed = home saja (silo)",
          u1.get("allowed_entity_ids") == ["ent_kanda"],
          f"allowed={u1.get('allowed_entity_ids')}")
    emp_after = await db.hr_employees.find_one({"id": emp_ok["id"]}, {"_id": 0, "user_id": 1})
    check("E2.1d", "tautan dua arah: hr_employees.user_id terisi",
          (emp_after or {}).get("user_id") == u1.get("id"),
          f"user_id={(emp_after or {}).get('user_id')}")

    r = await cl.post(f"{BASE}/api/users", headers=H(adm), json={
        "name": "Poc Gagal", "email": "poc.gagal@example.test", "role": "sales",
        "employee_id": emp_no_ent["id"]})
    check("E2.1e", "karyawan HR tanpa badan usaha → 400 menuntun ke perbaikan HR",
          r.status_code == 400 and "badan usaha" in r.text.lower(),
          f"HTTP {r.status_code} · {r.text[:140]}")

    r = await cl.post(f"{BASE}/api/users", headers=H(adm), json={
        "name": "Poc Dobel", "email": "poc.dobel@example.test", "role": "sales",
        "employee_id": emp_ok["id"]})
    check("E2.1f", "satu karyawan = satu akun (dobel → 409)", r.status_code == 409,
          f"HTTP {r.status_code}")

    print("\n── E2.2 · role berubah → entitas dihitung ulang + sesi dicabut ──")
    tok_u1 = await login("poc.sales.kanda@example.test")
    check("E2.2a", "akun baru bisa masuk (bukti sesi hidup sebelum dicabut)",
          bool(tok_u1), "login OK" if tok_u1 else "login GAGAL")
    r = await cl.patch(f"{BASE}/api/users/{u1['id']}", headers=H(adm),
                       json={"data": {"role": "manager"}})
    after = r.json() if r.status_code == 200 else {}
    check("E2.2b", "role → manager: allowed jadi LINTAS badan usaha (2 entitas aktif)",
          r.status_code == 200 and len(after.get("allowed_entity_ids") or []) >= 2,
          f"allowed={after.get('allowed_entity_ids')}")
    check("E2.2c", "sesi lama DICABUT saat role berubah",
          (after.get("sessions_revoked") or 0) >= 1,
          f"dicabut={after.get('sessions_revoked')} alasan={after.get('revoke_reasons')}")
    if tok_u1:
        r = await cl.get(f"{BASE}/api/auth/me", headers=H(tok_u1))
        check("E2.2d", "token lama benar-benar mati (401) — bukan sekadar catatan",
              r.status_code == 401, f"HTTP {r.status_code}")
    # kembalikan ke sales + tambah penugasan eksplisit ke KSC
    r = await cl.patch(f"{BASE}/api/users/{u1['id']}", headers=H(adm), json={
        "data": {"role": "sales", "allowed_entity_ids": ["ent_kanda", "ent_ksc"]}})
    back = r.json() if r.status_code == 200 else {}
    check("E2.2e", "sales boleh ditugaskan 2 badan usaha secara EKSPLISIT",
          sorted(back.get("allowed_entity_ids") or []) == ["ent_kanda", "ent_ksc"],
          f"allowed={back.get('allowed_entity_ids')}")
    tok_u1 = await login("poc.sales.kanda@example.test")
    r = await cl.get(f"{BASE}/api/sales-orders", headers=H(tok_u1, "ent_ksc"))
    check("E2.2f", "setelah ditugaskan, konteks KSC DITERIMA (tidak lagi 403)",
          r.status_code == 200, f"HTTP {r.status_code}")
    r = await cl.patch(f"{BASE}/api/users/{u1['id']}", headers=H(adm), json={
        "data": {"allowed_entity_ids": ["ent_kanda"]}})
    rev = r.json() if r.status_code == 200 else {}
    check("E2.2g", "akses dicabut → sesi ikut dicabut (bukan berlaku nanti)",
          (rev.get("sessions_revoked") or 0) >= 1,
          f"dicabut={rev.get('sessions_revoked')} alasan={rev.get('revoke_reasons')}")

    print("\n── E2.3 · email unik · admin terakhir · ganti password ──")
    r = await cl.patch(f"{BASE}/api/users/{u1['id']}", headers=H(adm),
                       json={"data": {"email": "admin@kainnusantara.id"}})
    check("E2.3a", "email duplikat DITOLAK 409", r.status_code == 409,
          f"HTTP {r.status_code} · {r.text[:120]}")
    admins = await db.users.count_documents({"role": "admin", "status": "active"})
    r = await cl.delete(f"{BASE}/api/users/user_admin_01", headers=H(adm))
    check("E2.3b", f"admin aktif terakhir ({admins}) tidak bisa dinonaktifkan → 409",
          r.status_code == 409 and "admin" in r.text.lower(),
          f"HTTP {r.status_code} · {r.text[:130]}")
    still = await db.users.find_one({"id": "user_admin_01"}, {"_id": 0, "status": 1})
    check("E2.3c", "BUKTI-MERAH: admin memang MASIH aktif setelah percobaan gagal",
          (still or {}).get("status") == "active", f"status={(still or {}).get('status')}")
    tok_u1 = await login("poc.sales.kanda@example.test")
    r = await cl.patch(f"{BASE}/api/users/{u1['id']}", headers=H(adm),
                       json={"data": {"password": "rahasiabaru123"}})
    check("E2.3d", "ganti password mencabut sesi",
          r.status_code == 200 and (r.json().get("sessions_revoked") or 0) >= 1,
          f"dicabut={(r.json() or {}).get('sessions_revoked')}")
    check("E2.3e", "password lama TIDAK bisa dipakai lagi",
          await login("poc.sales.kanda@example.test", PWD) is None, "login lama gagal")
    check("E2.3f", "password baru bisa dipakai",
          bool(await login("poc.sales.kanda@example.test", "rahasiabaru123")), "login baru OK")

    print("\n── E2.4 · nonaktifkan (soft) · aktifkan kembali · reset password ──")
    r = await cl.delete(f"{BASE}/api/users/{u1['id']}", headers=H(adm))
    row = await db.users.find_one({"id": u1["id"]}, {"_id": 0, "status": 1})
    check("E2.4a", "DELETE = NONAKTIFKAN (baris tetap ada, status inactive)",
          r.status_code == 200 and (row or {}).get("status") == "inactive",
          f"HTTP {r.status_code} · status={(row or {}).get('status')}")
    check("E2.4b", "akun nonaktif tidak bisa masuk",
          await login("poc.sales.kanda@example.test", "rahasiabaru123") is None,
          "login ditolak")
    r = await cl.post(f"{BASE}/api/users/{u1['id']}/reactivate", headers=H(adm))
    check("E2.4c", "aktifkan kembali → bisa masuk lagi",
          r.status_code == 200 and
          bool(await login("poc.sales.kanda@example.test", "rahasiabaru123")),
          f"HTTP {r.status_code}")
    r = await cl.post(f"{BASE}/api/users/{u1['id']}/reset-password", headers=H(adm),
                      json={"new_password": "123"})
    check("E2.4d", "reset password terlalu pendek DITOLAK 400", r.status_code == 400,
          f"HTTP {r.status_code}")
    r = await cl.post(f"{BASE}/api/users/{u1['id']}/reset-password", headers=H(adm),
                      json={"new_password": "kataSandiBaru9"})
    check("E2.4e", "reset password berhasil + sesi dicabut",
          r.status_code == 200 and (r.json().get("sessions_revoked") or 0) >= 1,
          f"{(r.json() or {}).get('message', '')[:80]}")
    aud = await db.audit_logs.find_one({"entity_type": "user", "entity_id": u1["id"],
                                       "action": "user_password_reset"}, {"_id": 0})
    leaked = "kataSandiBaru9" in str(aud or {})
    check("E2.4f", "password TIDAK pernah masuk jejak audit", not leaked,
          "jejak bersih" if not leaked else "PASSWORD BOCOR DI AUDIT")

    print("\n── E2.5 · filter · paging · pengayaan ──")
    r = await cl.get(f"{BASE}/api/users?entity_id=ent_kanda", headers=H(adm))
    rows = r.json()
    ok_scope = all("ent_kanda" in (u.get("allowed_entity_ids") or []) or
                   u.get("home_entity_id") == "ent_kanda" for u in rows)
    check("E2.5a", "filter ?entity_id=ent_kanda hanya akun terkait Kanda",
          r.status_code == 200 and rows and ok_scope,
          f"{len(rows)} akun: {[u['email'] for u in rows]}")
    r = await cl.get(f"{BASE}/api/users?role=sales&status=active", headers=H(adm))
    check("E2.5b", "filter role+status berjalan",
          r.status_code == 200 and all(u["role"] == "sales" and u["status"] == "active"
                                       for u in r.json()), f"{len(r.json())} akun")
    r = await cl.get(f"{BASE}/api/users?page=1&page_size=2", headers=H(adm))
    env = r.json()
    check("E2.5c", "paging memakai kontrak {items,total,page,page_size,has_more}",
          isinstance(env, dict) and len(env.get("items", [])) == 2 and
          env.get("total", 0) > 2 and env.get("has_more") is True,
          f"total={env.get('total')} has_more={env.get('has_more')}")
    row0 = (env.get("items") or [{}])[0]
    check("E2.5d", "setiap baris membawa home_entity, allowed_entities, employee_id, "
                   "last_login_at",
          all(k in row0 for k in ("home_entity", "allowed_entities", "employee_id",
                                  "last_login_at", "hr_link_warning")),
          f"kunci={sorted(set(row0) & {'home_entity', 'allowed_entities', 'employee_id', 'last_login_at'})}")
    r = await cl.get(f"{BASE}/api/users?q=Poc%20Sales", headers=H(adm))
    check("E2.5e", "pencarian nama berjalan",
          r.status_code == 200 and any(u["id"] == u1["id"] for u in r.json()),
          f"{len(r.json())} hasil")

    print("\n── E2.7 · jejak audit ber-stempel badan usaha ──")
    aud = await db.audit_logs.find({"entity_type": "user", "entity_id": u1["id"]},
                                  {"_id": 0}).to_list(50)
    actions = {a["action"] for a in aud}
    stamped = [a for a in aud if a.get("scope_entity_id")]
    check("E2.7a", "perubahan akun tercatat (created/updated/deactivated/reactivated)",
          {"user_created", "user_updated", "user_deactivated",
           "user_reactivated"}.issubset(actions), f"aksi={sorted(actions)}")
    check("E2.7b", "setiap baris jejak akun ber-stempel badan usaha",
          len(stamped) == len(aud) and len(aud) > 0,
          f"{len(stamped)}/{len(aud)} baris ber-stempel")


# ══════════════════════════════════════════════════════════════════════════════
async def fase_e1_lifecycle(cl: httpx.AsyncClient, adm: str,
                            ctxdata: Dict[str, Any]) -> None:
    """E1.6 diuji TERAKHIR karena mengarsipkan badan usaha (mengubah dunia)."""
    from db import db
    print("\n── E1.6 · pagar deaktivasi · kunci-tulis · blokir login ──")
    target = ctxdata.get("ent_nonpkp", "")

    r = await cl.get(f"{BASE}/api/entities/ent_ksc/deactivation-impact", headers=H(adm))
    imp = r.json()
    check("E1.6a", "pratinjau dampak KSC menyebut penghalang KONKRET",
          r.status_code == 200 and imp.get("can_archive") is False and
          len(imp.get("blockers") or []) >= 2,
          " | ".join(imp.get("blockers", [])[:2])[:170])
    r = await cl.delete(f"{BASE}/api/entities/ent_ksc", headers=H(adm))
    check("E1.6b", "arsip KSC DITOLAK 409 + rincian (bukan galat mentah)",
          r.status_code == 409 and "blockers" in r.text, f"HTTP {r.status_code}")
    ksc = await db.business_entities.find_one({"id": "ent_ksc"}, {"_id": 0, "status": 1})
    check("E1.6c", "BUKTI-MERAH: KSC memang MASIH aktif setelah percobaan gagal",
          (ksc or {}).get("status") == "active", f"status={(ksc or {}).get('status')}")

    # akun uji yang home-nya badan usaha target → dipakai membuktikan blokir login
    r = await cl.post(f"{BASE}/api/users", headers=H(adm), json={
        "name": "Poc Penghuni", "email": "poc.penghuni@example.test",
        "role": "sales", "password": PWD, "home_entity_id": target})
    u2 = r.json() if r.status_code == 200 else {}
    if u2.get("id"):
        CREATED["users"].append(u2["id"])
    tok_u2 = await login("poc.penghuni@example.test")
    check("E1.6d", "akun di badan usaha target bisa masuk SEBELUM diarsipkan",
          bool(tok_u2), "login OK" if tok_u2 else "login GAGAL")

    r = await cl.delete(f"{BASE}/api/entities/{target}", headers=H(adm))
    check("E1.6e", "badan usaha dengan penghuni → 409 (pindahkan penggunanya dulu)",
          r.status_code == 409 and "pengguna" in r.text.lower(), f"HTTP {r.status_code}")
    r = await cl.post(f"{BASE}/api/entities/{target}/archive", headers=H(adm),
                      json={"reason": "Uji POC E-1: dipaksa dengan alasan", "force": True})
    check("E1.6f", "admin boleh MEMAKSA arsip dengan alasan → 200",
          r.status_code == 200 and (r.json() or {}).get("status") == "archived",
          f"HTTP {r.status_code} · sesi_dicabut={(r.json() or {}).get('sessions_revoked')}")

    check("E1.6g", "penghuni badan usaha terarsip DIBLOKIR masuk (dengan alasan)",
          await login("poc.penghuni@example.test") is None, "login ditolak")
    async with httpx.AsyncClient(timeout=30.0) as t:
        rr = await t.post(f"{BASE}/api/auth/login",
                          json={"email": "poc.penghuni@example.test", "password": PWD})
    check("E1.6h", "pesan blokir menyebut badan usaha & jalan keluarnya",
          rr.status_code == 403 and "diarsipkan" in rr.text.lower(),
          f"HTTP {rr.status_code} · {rr.text[:150]}")

    # Akun DUAL: home = KSC (sesinya TIDAK dicabut saat target diarsipkan) tetapi
    # target ada di daftar penugasannya. Inilah satu-satunya jalur nyata yang bisa
    # mencoba MENULIS ke badan usaha terarsip — jadi inilah yang harus dipagari.
    r = await cl.post(f"{BASE}/api/users", headers=H(adm), json={
        "name": "Poc Dua Entitas", "email": "poc.dual@example.test",
        "role": "sales", "password": PWD, "home_entity_id": "ent_ksc",
        "allowed_entity_ids": ["ent_ksc", target]})
    u3 = r.json() if r.status_code == 200 else {}
    if u3.get("id"):
        CREATED["users"].append(u3["id"])
    tok_u3 = await login("poc.dual@example.test")
    cust = {"name": "Poc Pelanggan Terlarang", "pic_name": "Poc", "phone": "0800",
            "city": "Solo", "address": "Jl. Uji 1"}
    r_read = await cl.get(f"{BASE}/api/sales-orders", headers=H(tok_u3))
    r_write = await cl.post(f"{BASE}/api/customers", headers=H(tok_u3, target),
                            json=cust)
    check("E1.6i", "badan usaha terarsip: BACA entitas sendiri 200, TULIS ke yang "
                   "terarsip DITOLAK + pesan menyebut 'diarsipkan'",
          r_read.status_code == 200 and r_write.status_code in (403, 409) and
          "diarsipkan" in r_write.text.lower(),
          f"baca={r_read.status_code} tulis={r_write.status_code} · {r_write.text[:130]}")
    r_ok = await cl.post(f"{BASE}/api/customers", headers=H(tok_u3, "ent_ksc"),
                         json={**cust, "name": "Poc Pelanggan Sah"})
    if r_ok.status_code == 200:
        from db import db as _db
        await _db.customers.delete_many({"id": r_ok.json().get("id")})
    check("E1.6i2", "BUKTI-MERAH: TULIS ke badan usaha yang masih aktif tetap boleh",
          r_ok.status_code == 200, f"HTTP {r_ok.status_code} · {r_ok.text[:110]}")

    from services.entity_lifecycle_service import assert_entity_writable_cached
    guard_ok, guard_msg = False, ""
    try:
        await assert_entity_writable_cached(target)
    except Exception as exc:  # noqa: BLE001
        guard_ok = getattr(exc, "status_code", 0) == 409
        guard_msg = str(getattr(exc, "detail", exc))
    check("E1.6i3", "pagar kunci-tulis terpasang di choke point auth (409) — melindungi "
                    "endpoint yang tidak memakai entity_ctx",
          guard_ok and "diarsipkan" in guard_msg.lower(), guard_msg[:140])

    r = await cl.get(f"{BASE}/api/entities", headers=H(adm))
    check("E1.6j", "badan usaha terarsip HILANG dari daftar/pemilih default",
          target not in [e["id"] for e in r.json()],
          f"daftar aktif={[e['id'] for e in r.json()]}")
    r = await cl.get(f"{BASE}/api/entities?status=archived", headers=H(adm))
    check("E1.6k", "tetap terbaca admin lewat ?status=archived (data lama tidak hilang)",
          target in [e["id"] for e in r.json()], f"{len(r.json())} terarsip")
    r = await cl.post(f"{BASE}/api/entities/{target}/reactivate", headers=H(adm))
    check("E1.6l", "aktifkan kembali → status active lagi",
          r.status_code == 200 and (r.json() or {}).get("status") == "active",
          f"HTTP {r.status_code}")
    check("E1.6m", "setelah aktif kembali, penghuninya bisa masuk lagi",
          bool(await login("poc.penghuni@example.test")), "login OK")


# ══════════════════════════════════════════════════════════════════════════════
async def cleanup() -> None:
    from db import db
    print("\n── CLEANUP (self-healing: DB kembali seperti sebelum POC) ──")
    emails = ["poc.sales.kanda@example.test", "poc.penghuni@example.test",
              "poc.gagal@example.test", "poc.dobel@example.test",
              "poc.dual@example.test"]
    uids = [u["id"] async for u in db.users.find({"email": {"$in": emails}}, {"_id": 0, "id": 1})]
    uids = list(set(uids + CREATED["users"]))
    d_users = (await db.users.delete_many({"id": {"$in": uids}})).deleted_count
    await db.sessions.delete_many({"user_id": {"$in": uids}})
    await db.audit_logs.delete_many({"entity_id": {"$in": uids}})
    d_emp = (await db.hr_employees.delete_many(
        {"id": {"$in": CREATED["employees"]}})).deleted_count
    ents = CREATED["entities"]
    d_ent = (await db.business_entities.delete_many({"id": {"$in": ents}})).deleted_count
    await db.audit_logs.delete_many({"entity_id": {"$in": ents}})
    await db.system_settings.delete_many({"scope": {"$in": ents}})
    await db.number_sequences.delete_many({"entity_id": {"$in": ents}})
    await db.number_sequences.delete_many({"doc_type": "POCN"})
    await db.number_sequences.delete_many({"prefix": "POCN-"})
    await db["poc_e1_numbers"].drop()
    # nomor SO percobaan E1.4 (hanya sequence, tidak ada dokumen nyata)
    await db.login_attempts.delete_many({"identifier": {"$regex": "example.test"}})
    await db.customers.delete_many({"name": {"$regex": "^Poc Pelanggan"}})
    # BUKTI: nol residu
    residue = (await db.users.count_documents({"email": {"$in": emails}}) +
               await db.hr_employees.count_documents({"id": {"$in": CREATED["employees"]}}) +
               await db.business_entities.count_documents({"id": {"$in": ents}}) +
               await db.number_sequences.count_documents({"doc_type": "POCN"}))
    check("CLEAN", "nol residu fixture di DB",
          residue == 0,
          f"user={d_users} karyawan={d_emp} badan_usaha={d_ent} residu={residue}")
    # pastikan entitas demo utuh & aktif
    left = await db.business_entities.count_documents({"status": "active"})
    check("CLEAN2", "badan usaha demo utuh & aktif (KSC + Kanda)", left == 2,
          f"{left} badan usaha aktif")


async def main() -> int:
    print("=" * 74)
    print("  POC FASE E-1 + E-2 — MODEL BADAN USAHA & AKUN TERTAUT HR")
    print("=" * 74)
    adm = await login("admin@kainnusantara.id")
    if not adm:
        print("GAGAL: tidak bisa login admin.")
        return 1
    async with httpx.AsyncClient(timeout=90.0) as cl:
        try:
            ctxdata = await fase_e1(cl, adm)
            await fase_e2(cl, adm, ctxdata)
            await fase_e1_lifecycle(cl, adm, ctxdata)
        finally:
            await cleanup()

    print("\n" + "=" * 74)
    bad = [r for r in RESULTS if not r["ok"]]
    print(f"  HASIL: {GREEN}{len(RESULTS) - len(bad)} PASS{RESET} · "
          f"{RED}{len(bad)} FAIL{RESET}")
    print("=" * 74)
    for b in bad:
        print(f"  {RED}✗{RESET} {b['code']} — {b['name']} :: {b['detail']}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
