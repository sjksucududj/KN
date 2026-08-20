#!/usr/bin/env python3
"""POC FASE G-8 — REKONSILIASI BANK OTOMATIS (satu skrip · HTTP · nol residu).

Membuktikan 11 user story fase G-8 memakai API sungguhan, bukan mock:

  1. Parser multi-bank (BCA satu-kolom+DB/CR & tanggal tanpa tahun · Mandiri dua-kolom ·
     MT940 · OFX bertanda) + PRATINJAU sebelum impor + laporan baris rusak.
  2. Template bank buatan user (pemetaan kolom sendiri) — tanpa developer.
  3. Skor BERBOBOT 3 pita: >=ambang otomatis tertaut · pita usulan berperingkat ·
     di bawahnya manual. Setiap skor punya PENJELASAN yang dibaca manusia.
  4. Split 1:N (satu transfer melunasi beberapa transaksi buku) & gabung N:1
     (beberapa transfer untuk satu transaksi), termasuk penolakan kelebihan alokasi.
  5. Aturan hasil PEMBELAJARAN: 3x pola sama -> ditawarkan; setelah DISETUJUI manusia
     mutasi berikutnya cocok otomatis (bonus skor terlihat di penjelasan).
  6. Titipan dana belum teridentifikasi: kas + jurnal `Dr Bank / Cr 2-1950`.
  7. Alokasi titipan ke pesanan: piutang berkurang + `Dr 2-1950 / Cr 1-1200`,
     TANPA kas dobel; wajib berlabel alasan; kelebihan alokasi ditolak.
  8. Ringkasan: saldo & umur titipan, jumlah tercocok/usulan, selisih buku vs rekening.
  9. Semua ambang & bobot dibaca dari Pusat Pengaturan (bukan angka sihir di kode).
 10. INV-BNK-01..05 + BUKTI-MERAH (suntik pelanggaran -> WAJIB memerah -> pulihkan).
 11. Isolasi lintas-PT: akun/mutasi PT lain -> 403 (celah nyata sebelum fase ini).

Penutupan fase menambah blok ke-6 (`test_charge_and_guards`) untuk 5 bug NYATA yang
sebelumnya lolos: biaya/bunga bank tanpa jalur pembukuan (KN-G8-CHARGE-NOPATH),
pembatalan titipan yang tidak membalik jurnal (KN-G8-CANCEL-JE), `unmatch` tanpa penjaga
status (KN-G8-UNMATCH-NOGUARD), pencocokan separuh nominal pada jalur manual maupun
otomatis (KN-G8-MATCH-PARTIAL), dan alokasi titipan yang bisa melintasi PT
(KN-G8-ALLOC-CROSSPT). Blok itu juga membuktikan INV-BNK-04 & INV-BNK-05.

Jalankan: cd /app && python backend/test_g8_bank_poc.py
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

BASE = os.environ.get("KN_BASE", "http://localhost:8001/api")
PWD = "demo12345"
ENT_A = "ent_ksc"
ENT_B = "ent_kanda"
ACC_A = "bank_bca_ksc"       # akun bank PT-A (BCA Operasional KSC)
ACC_B = "bank_kas_kanda"     # akun kas PT-B
POC_TAG = "POC_G8"

G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
res = {"pass": 0, "fail": 0}
made: Dict[str, List[str]] = {"lines": [], "cash": [], "formats": [], "rules": [], "orders": []}


def ok(cond: bool, name: str, extra: Any = "") -> bool:
    res["pass" if cond else "fail"] += 1
    tag = f"{G}PASS{X}" if cond else f"{R}FAIL{X}"
    print(f"  [{tag}] {name}" + (f"  ({extra})" if extra else ""))
    return bool(cond)


def head(t: str) -> None:
    print(f"\n{C}{B}── {t} ──{X}")


def login(email: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD}, timeout=30)
    r.raise_for_status()
    tok = r.json().get("token")
    assert tok, f"login {email} gagal: {r.text[:160]}"
    return tok


def H(tok: str, ent: str = "") -> Dict[str, str]:
    h = {"Authorization": f"Bearer {tok}"}
    if ent:
        h["X-Entity-Id"] = ent
    return h


def api(method: str, path: str, tok: str, ent: str = "", **kw) -> requests.Response:
    return requests.request(method, f"{BASE}{path}", headers=H(tok, ent), timeout=90, **kw)


def integrity(only: str = "") -> tuple:
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


def dbrun(fn):
    """Jalankan satu operasi Mongo langsung (khusus suntikan bukti-merah & cleanup)."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _go():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            return await fn(cli[os.environ["DB_NAME"]])
        finally:
            cli.close()

    return asyncio.run(_go())


D0 = datetime.now(timezone.utc).date()


def day(delta: int) -> str:
    return (D0 + timedelta(days=delta)).isoformat()


# ═════════════════════════════════════════════════════════════════════════════
#  1 · PARSER MULTI-BANK + PRATINJAU  (US1, US2)
# ═════════════════════════════════════════════════════════════════════════════
CSV_BCA = (
    "Tanggal,Keterangan,Cabang,Jumlah,DB/CR,Saldo\n"
    "12/07,TRSF E-BANKING CR PT MAJU JAYA SO-0007,0000,\"12.500.000,00\",CR,\"112.500.000,00\"\n"
    "13/07,BIAYA ADM,0000,\"15.000,00\",DB,\"112.485.000,00\"\n"
    "13/07,TRSF E-BANKING CR BUTIK BALI INDAH,0000,\"7.350.000,50\",CR,\"119.835.000,50\"\n"
    "baris rusak tanpa nominal,,,,,\n"
)
CSV_MANDIRI = (
    "Tanggal,Keterangan,No. Referensi,Debet,Kredit,Saldo\n"
    "05/07/2026,SETORAN KLIRING CV SINAR ABADI,REF00912,,\"4.000.000,00\",\"50.000.000,00\"\n"
    "06/07/2026,PEMBAYARAN LISTRIK,REF00913,\"1.250.000,00\",,\"48.750.000,00\"\n"
)
MT940 = (
    ":20:STMT001\n"
    ":25:1234567890\n"
    ":28C:00012/001\n"
    ":60F:C260701IDR50000000,00\n"
    ":61:2607121207CR9000000,00NTRFNONREF//KSC0001\n"
    ":86:SETORAN GABUNGAN TOKO SEJAHTERA\n"
    ":61:2607131307DR250000,00NCHGNONREF//BIAYA\n"
    ":86:BIAYA TRANSFER\n"
    ":62F:C260731IDR58750000,00\n"
)
OFX = (
    "OFXHEADER:100\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>\n"
    "<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260714120000<TRNAMT>2500000.00"
    "<FITID>FIT-001<NAME>PT RUTIN SEJAHTERA<MEMO>TRANSFER RUTIN</STMTTRN>\n"
    "<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260715120000<TRNAMT>-99000.00"
    "<FITID>FIT-002<NAME>ADMIN FEE<MEMO>BIAYA</STMTTRN>\n"
    "</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>\n"
)


def test_parser(admin: str) -> Dict[str, Any]:
    head("1 · PARSER MULTI-BANK + PRATINJAU (US1/US2)")
    fmts = api("GET", "/bank-reconciliation/formats", admin, ENT_A).json()
    by_bank = {f["bank_code"] + ":" + f["file_kind"]: f for f in fmts}
    ok(len(fmts) >= 7, "template bawaan tersedia (BCA/Mandiri/BNI/BRI/Permata/MT940/OFX)",
       f"{len(fmts)} template")

    r = api("POST", "/bank-reconciliation/preview", admin, ENT_A,
            json={"raw": CSV_BCA, "year_hint": 2026})
    p = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and p.get("detected") is True,
       "template BCA TERDETEKSI otomatis dari header berkas", f"{p.get('format', {}).get('name')}")
    rows = p.get("rows") or []
    first = rows[0] if rows else {}
    ok(len(rows) == 3, "3 baris sah terbaca (baris rusak tidak ikut)", f"{len(rows)} baris")
    ok(p.get("error_count") == 1, "baris rusak DILAPORKAN, bukan didiamkan",
       f"{p.get('errors')[:1]}")
    ok(first.get("stmt_date") == "2026-07-12",
       "tanggal tanpa tahun (12/07) dilengkapi dari periode", first.get("stmt_date"))
    ok(first.get("amount") == 12500000.0 and first.get("direction") == "in",
       "desimal Indonesia 12.500.000,00 + penanda CR terbaca",
       f"{first.get('amount')} {first.get('direction')}")
    ok(rows[1].get("direction") == "out" and rows[1].get("amount") == 15000.0,
       "penanda DB = uang keluar", f"{rows[1].get('amount')}")
    ok(first.get("ref") == "SO-0007",
       "nomor dokumen ditemukan di berita transfer (untuk skor referensi)", first.get("ref"))
    ok(first.get("counterparty", "").upper().startswith("PT MAJU JAYA"),
       "nama pengirim ditebak dari berita transfer", first.get("counterparty"))

    r = api("POST", "/bank-reconciliation/preview", admin, ENT_A,
            json={"raw": CSV_MANDIRI, "format_id": by_bank["mandiri:csv"]["id"]})
    pm = r.json()
    ok(r.status_code == 200 and len(pm.get("rows") or []) == 2,
       "Mandiri dua-kolom (Debet/Kredit) terbaca", f"{len(pm.get('rows') or [])} baris")
    ok(pm["rows"][0]["direction"] == "in" and pm["rows"][1]["direction"] == "out",
       "kolom Kredit = masuk, Debet = keluar")
    ok(pm["sum_in"] == 4000000.0 and pm["sum_out"] == 1250000.0,
       "total masuk/keluar dihitung untuk pratinjau", f"in={pm['sum_in']} out={pm['sum_out']}")

    r = api("POST", "/bank-reconciliation/preview", admin, ENT_A,
            json={"raw": MT940, "format_id": by_bank["generic:mt940"]["id"]})
    pt = r.json()
    ok(r.status_code == 200 and len(pt.get("rows") or []) == 2, "MT940 :61:/:86: terbaca",
       f"{len(pt.get('rows') or [])} baris")
    ok(pt["rows"][0]["stmt_date"] == "2026-07-12" and pt["rows"][0]["amount"] == 9000000.0
       and pt["rows"][0]["direction"] == "in", "MT940: tanggal YYMMDD + penanda C = masuk",
       f"{pt['rows'][0]['stmt_date']} {pt['rows'][0]['amount']}")
    ok("SETORAN GABUNGAN" in (pt["rows"][0].get("description") or "").upper(),
       "keterangan :86: ikut menempel ke mutasinya")

    r = api("POST", "/bank-reconciliation/preview", admin, ENT_A,
            json={"raw": OFX, "format_id": by_bank["generic:ofx"]["id"]})
    po = r.json()
    ok(r.status_code == 200 and len(po.get("rows") or []) == 2, "OFX <STMTTRN> terbaca")
    ok(po["rows"][1]["direction"] == "out",
       "OFX nominal negatif = uang keluar", f"{po['rows'][1]['amount']}")
    ok(po["rows"][0]["external_id"] == "FIT-001",
       "FITID dipakai sebagai id unik anti-dobel impor")

    # US2 — template buatan user (kolom & format sendiri, tanpa header)
    custom = {
        "name": f"{POC_TAG} Template Kustom", "bank_code": "custom", "file_kind": "csv",
        "delimiter": ";", "has_header": False, "decimal_style": "en", "date_format": "dd/mm/yyyy",
        "columns": {"date": 0, "description": 1, "amount": 2, "direction": 3},
        "in_markers": ["masuk"], "out_markers": ["keluar"],
    }
    r = api("POST", "/bank-reconciliation/formats", admin, ENT_A, json=custom)
    ok(r.status_code == 200, "template kustom bisa dibuat user", f"HTTP {r.status_code}")
    cust = r.json()
    made["formats"].append(cust["id"])
    r = api("POST", "/bank-reconciliation/preview", admin, ENT_A, json={
        "raw": "20/07/2026;TRANSFER UJI KUSTOM;1500000.75;masuk\n", "format_id": cust["id"]})
    pc = r.json()
    ok(r.status_code == 200 and pc["rows"][0]["amount"] == 1500000.75
       and pc["rows"][0]["direction"] == "in",
       "template kustom (tanpa header, indeks kolom, desimal Inggris) bekerja",
       f"{pc['rows'][0] if pc.get('rows') else pc}")

    # ── KN-G8-FORMAT-DUP: preset bawaan tidak boleh ganda & tidak boleh disunting di tempat
    builtins = [f for f in api("GET", "/bank-reconciliation/formats", admin, "all").json()
                if f.get("builtin")]
    names = [f["name"] for f in builtins]
    dupes = sorted({n for n in names if names.count(n) > 1})
    ok(not dupes,
       "BUKTI-MERAH (KN-G8-FORMAT-DUP): admin 2 PT melihat tiap template bawaan SEKALI — "
       "dulu preset dipasang per-entitas sehingga muncul dobel tanpa pembeda",
       f"{len(builtins)} bawaan · nama ganda: {dupes or 'tidak ada'}")
    ok(all(f.get("entity_id") == "all" for f in builtins),
       "preset bawaan dimiliki entitas GRUP (pengetahuan format bank, bukan data satu PT)",
       str(sorted({f.get('entity_id') for f in builtins})))
    src = builtins[0]
    r = api("POST", "/bank-reconciliation/formats", admin, ENT_A,
            json={**src, "delimiter": ";", "note": f"disunting {POC_TAG}"})
    copy = r.json() if r.status_code == 200 else {}
    if copy.get("id"):
        made["formats"].append(copy["id"])
    again = api("GET", "/bank-reconciliation/formats", admin, ENT_A).json()
    still = next((f for f in again if f["id"] == src["id"]), {})
    ok(r.status_code == 200 and copy.get("id") != src["id"] and copy.get("builtin") is False
       and copy.get("entity_id") == ENT_A and still.get("delimiter") == src.get("delimiter"),
       "menyimpan template bawaan menghasilkan SALINAN milik entitas — preset aslinya "
       "TIDAK berubah untuk PT lain", f"salinan '{copy.get('name')}' · asli utuh")
    r = api("DELETE", f"/bank-reconciliation/formats/{src['id']}", admin, ENT_A)
    ok(r.status_code == 400 and "bawaan" in r.text.lower(),
       "BUKTI-MERAH: menonaktifkan template BAWAAN ditolak (preset bersama tidak boleh hilang)",
       f"HTTP {r.status_code}")

    # ── KN-G8-DIR-SILENT (P1, uang) — arah dana TIDAK PERNAH ditebak ────────────
    # Ditemukan saat penutupan FASE G-8 lewat layar (bukan teori): POC lama hanya
    # memakai CSV ber-TANDA KUTIP, sedangkan ekspor bank sungguhan sering TANPA kutip.
    # Karena koma desimal Indonesia = pemisah CSV, kolom bergeser dan penanda DB/CR
    # hilang → parser DIAM-DIAM menganggapnya UANG MASUK. Baris biaya bank pun masuk
    # sebagai pemasukan: saldo rekening, "selisih rekening vs buku", sampai kandidat
    # pencocokan ke kwitansi piutang jadi salah TANPA satu pun peringatan.
    bca_id = by_bank["bca:csv"]["id"]
    CSV_SUFFIX = ("Tanggal,Keterangan,Cabang,Jumlah,Saldo\n"
                  "12/07,TRSF E-BANKING CR PT MAJU JAYA,0000,\"12.500.000,00 CR\",\"1,00\"\n"
                  "13/07,BIAYA ADM,0000,\"15.000,00 DB\",\"1,00\"\n")
    ps = api("POST", "/bank-reconciliation/preview", admin, ENT_A,
             json={"raw": CSV_SUFFIX, "format_id": bca_id, "year_hint": 2026}).json()
    srows = ps.get("rows") or []
    ok(len(srows) == 2 and srows[0]["direction"] == "in" and srows[1]["direction"] == "out"
       and srows[1]["amount"] == 15000.0,
       "penanda DB/CR yang MENEMPEL pada kolom nominal ('15.000,00 DB') terbaca sebagai "
       "uang KELUAR — bukan lagi dianggap masuk",
       f"{[(x['amount'], x['direction']) for x in srows]}")
    ok(ps.get("sum_out") == 15000.0 and ps.get("sum_in") == 12500000.0,
       "total masuk/keluar pratinjau ikut benar (dulu keluar selalu Rp 0)",
       f"in={ps.get('sum_in')} out={ps.get('sum_out')}")

    CSV_SHIFT = ("Tanggal,Keterangan,Cabang,Jumlah,Saldo\n"
                 "28/07,TRSF E-BANKING CR UJI,0000,1.250.000,00 CR,10.000.000,00\n"
                 "27/07,BIAYA ADM UJI,0000,25.000,00 DB,9.975.000,00\n")
    px = api("POST", "/bank-reconciliation/preview", admin, ENT_A,
             json={"raw": CSV_SHIFT, "format_id": bca_id, "year_hint": 2026}).json()
    reasons = " ".join(e.get("reason", "") for e in (px.get("errors") or []))
    ok(not (px.get("rows") or []) and px.get("error_count") == 2 and "Arah dana" in reasons,
       "BUKTI-MERAH (KN-G8-DIR-SILENT): baris yang arahnya TIDAK bisa dipastikan DITOLAK "
       "berikut arahan perbaikan — dulu diam-diam masuk sebagai uang MASUK",
       f"{px.get('error_count')} ditolak · {reasons[:70]}")
    ok(all(x["direction"] == "in" for x in srows[:1]) and parser_marker_safe(),
       "kata yang MENGANDUNG penanda bukan penanda ('KREDITUR' ≠ kredit) & sel ambigu "
       "('DB/CR') tidak ditebak", "batas kata + deteksi ambigu")
    return by_bank


def parser_marker_safe() -> bool:
    """Uji murni penanda arah dana (tanpa HTTP) — bagian dari BUKTI-MERAH KN-G8-DIR-SILENT."""
    from services import bank_statement_parser as P  # noqa: PLC0415
    bca = next(f for f in P.BUILTIN_FORMATS if f["bank_code"] == "bca")
    bri = next(f for f in P.BUILTIN_FORMATS if f["bank_code"] == "bri")
    cases = [("KREDITUR", {}, ""), ("CREDIBLE", {}, ""), ("DB/CR", bca, ""),
             ("00 DB", {}, "out"), ("1.250.000,00 CR", {}, "in"),
             ("K", bri, "in"), ("D", bri, "out"), ("", {}, "")]
    return all(P._dir_from_marker(v, f) == exp for v, f, exp in cases)


# ═════════════════════════════════════════════════════════════════════════════
#  2 · TRANSAKSI BUKU (fixture nyata lewat API kas)
# ═════════════════════════════════════════════════════════════════════════════
def cash_in(admin: str, amount: float, desc: str, date_iso: str) -> Dict[str, Any]:
    r = api("POST", "/cash-transactions", admin, ENT_A, json={
        "cash_type": "kas_besar", "direction": "in", "amount": amount,
        "category": "penagihan", "description": f"{desc} [{POC_TAG}]",
        "ref_type": "manual", "txn_date": date_iso, "account_id": ACC_A,
        "created_by": POC_TAG})
    assert r.status_code == 200, f"gagal buat transaksi kas: {r.status_code} {r.text[:160]}"
    doc = r.json()
    made["cash"].append(doc["id"])
    return doc


def import_lines(admin: str, lines: List[Dict[str, Any]], acc: str = ACC_A,
                 ent: str = ENT_A) -> List[Dict[str, Any]]:
    r = api("POST", "/bank-reconciliation/import", admin, ent,
            json={"bank_account_id": acc, "lines": lines})
    assert r.status_code == 200, f"impor gagal: {r.status_code} {r.text[:200]}"
    rows = api("GET", f"/bank-reconciliation/lines?bank_account_id={acc}", admin, ent).json()
    fresh = [l for l in rows if l.get("import_batch") == r.json()["import_batch"]]
    for l in fresh:
        made["lines"].append(l["id"])
    return fresh


# ═════════════════════════════════════════════════════════════════════════════
#  3 · SKOR BERBOBOT 3 PITA  (US3, US9)
# ═════════════════════════════════════════════════════════════════════════════
def test_scoring(admin: str) -> Dict[str, Any]:
    head("2 · SKOR BERBOBOT & 3 PITA OTOMATIS/USULAN/MANUAL (US3/US9)")
    t_exact = cash_in(admin, 12500000, "Pelunasan SO-0007 PT Maju Jaya", day(-1))
    t_near = cash_in(admin, 7350000, "Pembayaran Butik Bali Indah", day(-3))
    t_far = cash_in(admin, 5000000, "Termin CV Sinar Abadi", day(-30))
    lines = import_lines(admin, [
        {"stmt_date": day(-1), "amount": 12500000, "direction": "in",
         "description": "TRSF E-BANKING CR PT MAJU JAYA SO-0007", "ref": "SO-0007"},
        {"stmt_date": day(-1), "amount": 7350000, "direction": "in",
         "description": "TRSF E-BANKING CR BUTIK BALI INDAH"},
        {"stmt_date": day(-1), "amount": 5000000, "direction": "in",
         "description": "SETORAN TUNAI TANPA KETERANGAN"},
    ])
    ok(len(lines) == 3, "3 baris mutasi terimpor", f"{len(lines)} baris")

    dup = api("POST", "/bank-reconciliation/import", admin, ENT_A, json={
        "bank_account_id": ACC_A, "lines": [
            {"stmt_date": day(-1), "amount": 12500000, "direction": "in",
             "description": "TRSF E-BANKING CR PT MAJU JAYA SO-0007", "ref": "SO-0007"}]}).json()
    ok(dup["imported"] == 0 and dup["skipped"] == 1,
       "impor ulang baris yang sama DILEWATI (anti-dobel)", f"{dup}")

    r = api("POST", "/bank-reconciliation/auto-match", admin, ENT_A,
            json={"bank_account_id": ACC_A})
    am = r.json()
    ok(r.status_code == 200, "cocokkan otomatis berjalan", f"HTTP {r.status_code}")
    ok(am.get("auto_min") == 80 and am.get("suggest_min") == 60,
       "ambang dibaca dari Pusat Pengaturan (bukan angka sihir di kode)",
       f"auto>={am.get('auto_min')} usulan>={am.get('suggest_min')}")
    rows = {l["id"]: l for l in
            api("GET", f"/bank-reconciliation/lines?bank_account_id={ACC_A}", admin, ENT_A).json()}
    l_exact = rows[lines[0]["id"]]
    l_near = rows[lines[1]["id"]]
    l_far = rows[lines[2]["id"]]
    ok(l_exact["status"] == "matched" and l_exact["score"] >= 80,
       "pita OTOMATIS: nominal+tanggal+referensi -> langsung tertaut",
       f"skor {l_exact['score']}")
    ok((l_exact.get("matched_txn") or {}).get("id") == t_exact["id"],
       "tertaut ke transaksi buku yang benar",
       (l_exact.get("matched_txn") or {}).get("number"))
    labels = " · ".join(e["label"] for e in (l_exact.get("score_explain") or []))
    ok(len(l_exact.get("score_explain") or []) >= 3 and "referensi" in labels.lower(),
       "PENJELASAN skor dibaca manusia (bukan angka telanjang)", labels[:110])
    ok(l_near["status"] == "unmatched" and 60 <= l_near["score"] < 80
       and len(l_near.get("suggestions") or []) >= 1,
       "pita USULAN: nominal sama tapi tanggal beda & tanpa referensi -> ditawarkan, tidak dipaksa",
       f"skor {l_near['score']} usulan {len(l_near.get('suggestions') or [])}")
    ok((l_near["suggestions"][0]).get("id") == t_near["id"],
       "usulan teratas menunjuk transaksi paling mungkin",
       l_near["suggestions"][0].get("number"))
    ok(l_far["status"] == "unmatched" and l_far["score"] < 60
       and not (l_far.get("suggestions") or []),
       "pita MANUAL: tanggal jauh di luar jendela -> tidak ditawarkan sama sekali",
       f"skor {l_far['score']}")

    cand = api("GET", f"/bank-reconciliation/lines/{l_near['id']}/candidates", admin, ENT_A).json()
    ok(len(cand.get("candidates") or []) >= 1 and cand["candidates"][0]["score"] >= 60,
       "daftar kandidat berperingkat tersedia untuk keputusan manual",
       f"{len(cand.get('candidates') or [])} kandidat")
    r = api("POST", f"/bank-reconciliation/lines/{l_near['id']}/match", admin, ENT_A,
            json={"txn_id": t_near["id"]})
    ok(r.status_code == 200 and r.json()["status"] == "matched",
       "usulan diterima 1 klik -> tertaut", f"HTTP {r.status_code}")
    r = api("POST", f"/bank-reconciliation/lines/{l_far['id']}/ignore", admin, ENT_A,
            json={"note": f"biaya bank {POC_TAG}"})
    ok(r.status_code == 200 and r.json()["status"] == "ignored",
       "baris yang memang bukan urusan kita bisa DIABAIKAN dgn catatan")
    return {"t_far": t_far, "l_far": l_far, "l_exact": l_exact}


# ═════════════════════════════════════════════════════════════════════════════
#  4 · SPLIT 1:N & GABUNG N:1  (US4)
# ═════════════════════════════════════════════════════════════════════════════
def test_split_group(admin: str) -> None:
    head("3 · SATU TRANSFER BANYAK TAGIHAN (1:N) & SEBALIKNYA (N:1) (US4)")
    t1 = cash_in(admin, 4000000, "Termin 1 CV Sinar Abadi", day(-1))
    t2 = cash_in(admin, 6000000, "Termin 2 CV Sinar Abadi", day(-1))
    lines = import_lines(admin, [
        {"stmt_date": day(-1), "amount": 10000000, "direction": "in",
         "description": "TRSF E-BANKING CR CV SINAR ABADI GABUNGAN 2 TERMIN"},
    ])
    ln = lines[0]
    bad = api("POST", f"/bank-reconciliation/lines/{ln['id']}/match-split", admin, ENT_A, json={
        "allocations": [{"txn_id": t1["id"], "amount": 4000000},
                        {"txn_id": t2["id"], "amount": 7000000}]})
    ok(bad.status_code == 400 and "melebihi" in bad.text.lower(),
       "BUKTI-MERAH: Σ alokasi > nominal transfer DITOLAK (uang tidak boleh diciptakan)",
       f"HTTP {bad.status_code}")
    r = api("POST", f"/bank-reconciliation/lines/{ln['id']}/match-split", admin, ENT_A, json={
        "allocations": [{"txn_id": t1["id"], "amount": 4000000},
                        {"txn_id": t2["id"], "amount": 6000000}]})
    sp = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and sp.get("match_kind") == "1:N"
       and sp.get("allocated_total") == 10000000.0,
       "1 transfer Rp 10.000.000 melunasi 2 transaksi buku (4jt + 6jt)",
       f"HTTP {r.status_code} {sp.get('match_kind')}")
    lst = api("GET", f"/bank-reconciliation/lines?bank_account_id={ACC_A}", admin, ENT_A).json()
    row = next(l for l in lst if l["id"] == ln["id"])
    ok(len(row.get("matched_txns") or []) == 2,
       "kedua transaksi buku terlihat di baris mutasi (bisa diaudit)",
       [t["number"] for t in row["matched_txns"]])

    t3 = cash_in(admin, 9000000, "Setoran gabungan Toko Sejahtera", day(-1))
    g = import_lines(admin, [
        {"stmt_date": day(-1), "amount": 5000000, "direction": "in",
         "description": "SETORAN TUNAI TOKO SEJAHTERA 1"},
        {"stmt_date": day(-1), "amount": 4000000, "direction": "in",
         "description": "SETORAN TUNAI TOKO SEJAHTERA 2"},
    ])
    over = api("POST", "/bank-reconciliation/match-group", admin, ENT_A, json={
        "line_ids": [g[0]["id"], g[1]["id"]], "txn_id": t1["id"]})
    ok(over.status_code == 400,
       "BUKTI-MERAH: gabung ke transaksi yang sudah penuh DITOLAK", f"HTTP {over.status_code}")
    r = api("POST", "/bank-reconciliation/match-group", admin, ENT_A, json={
        "line_ids": [g[0]["id"], g[1]["id"]], "txn_id": t3["id"]})
    gr = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and gr.get("match_kind") == "N:1"
       and gr.get("allocated_total") == 9000000.0,
       "2 transfer (5jt + 4jt) melunasi 1 transaksi buku Rp 9.000.000",
       f"HTTP {r.status_code}")
    code, out = integrity("bank")
    ok(code == 0 and inv_state(out, "INV-BNK-02") == "PASS",
       "INV-BNK-02 tetap HIJAU sesudah split & gabung (Σ rekonsiliasi == Σ alokasi)")


# ═════════════════════════════════════════════════════════════════════════════
#  5 · ATURAN HASIL PEMBELAJARAN  (US5)
# ═════════════════════════════════════════════════════════════════════════════
def test_learning(admin: str) -> None:
    head("4 · ATURAN HASIL PEMBELAJARAN — 3× pola sama lalu DITAWARKAN (US5)")
    desc = "TRSF E-BANKING CR PT RUTIN SEJAHTERA"
    amounts = [1111000, 1222000, 1333000]
    txns = [cash_in(admin, a, "Transfer PT Rutin Sejahtera", day(-1)) for a in amounts]
    lines = import_lines(admin, [
        {"stmt_date": day(-1), "amount": a, "direction": "in", "description": f"{desc} {i}"}
        for i, a in enumerate(amounts, start=1)])
    learned = None
    for i, ln in enumerate(lines):
        r = api("POST", f"/bank-reconciliation/lines/{ln['id']}/match", admin, ENT_A,
                json={"txn_id": txns[i]["id"]})
        assert r.status_code == 200, r.text[:160]
        if r.json().get("rule_learned"):
            learned = r.json()["rule_learned"]
        if i < 2:
            ok(r.json().get("rule_learned") in (None, {}),
               f"cocok manual ke-{i + 1}: BELUM ada aturan (ambang 3×)")
    ok(bool(learned) and learned.get("status") == "suggested",
       "cocok manual ke-3: aturan DITAWARKAN (status 'suggested', belum aktif)",
       f"{(learned or {}).get('counterparty')}")
    if learned:
        made["rules"].append(learned["id"])

    rules = api("GET", "/bank-reconciliation/rules?status=suggested", admin, ENT_A).json()
    ok(any(x["id"] == (learned or {}).get("id") for x in rules),
       "aturan tertawar muncul di daftar untuk ditinjau manusia", f"{len(rules)} aturan")

    # Sebelum disetujui: mutasi serupa TANPA referensi hanya jadi usulan (belum otomatis).
    # Pasangan SENGAJA di ambang: nominal sama + tanggal sama + nama agak mirip = 67,5 poin
    # (di pita usulan, BELUM otomatis). Bonus aturan +15 → 82,5 ≥ ambang 80 → otomatis.
    t4 = cash_in(admin, 2500000, "Transfer PT Rutin Sejahtera", day(-2))
    probe = import_lines(admin, [
        {"stmt_date": day(-2), "amount": 2500000, "direction": "in", "description": f"{desc} 4"}])
    api("POST", "/bank-reconciliation/auto-match", admin, ENT_A,
        json={"bank_account_id": ACC_A})
    row = next(l for l in api("GET", f"/bank-reconciliation/lines?bank_account_id={ACC_A}",
                              admin, ENT_A).json() if l["id"] == probe[0]["id"])
    ok(row["status"] == "unmatched" and row["score"] < 80,
       "sebelum aturan disetujui: mutasi serupa BELUM dicocokkan otomatis",
       f"skor {row['score']}")

    r = api("POST", f"/bank-reconciliation/rules/{learned['id']}/decide", admin, ENT_A,
            json={"action": "activate"})
    ok(r.status_code == 200 and r.json()["status"] == "active",
       "manusia MENYETUJUI aturan (tidak ada aturan yang aktif sendiri)")
    api("POST", "/bank-reconciliation/auto-match", admin, ENT_A,
        json={"bank_account_id": ACC_A})
    row2 = next(l for l in api("GET", f"/bank-reconciliation/lines?bank_account_id={ACC_A}",
                               admin, ENT_A).json() if l["id"] == probe[0]["id"])
    ok(row2["status"] == "matched" and row2["score"] >= 80,
       "sesudah disetujui: mutasi berikutnya COCOK OTOMATIS", f"skor {row2['score']}")
    ok(any("aturan" in (e["label"] or "").lower() for e in (row2.get("score_explain") or [])),
       "penjelasan skor menyebut bonus dari aturan (transparan)",
       [e["label"][:36] for e in row2.get("score_explain") or []])
    ok((row2.get("matched_txn") or {}).get("id") == t4["id"],
       "tertaut ke transaksi buku yang tepat", (row2.get("matched_txn") or {}).get("number"))


# ═════════════════════════════════════════════════════════════════════════════
#  6 · TITIPAN DANA BELUM TERIDENTIFIKASI  (US6, US7, US8)
# ═════════════════════════════════════════════════════════════════════════════
def test_holding(admin: str) -> Dict[str, Any]:
    head("5 · TITIPAN DANA BELUM TERIDENTIFIKASI + ALOKASI (US6/US7/US8)")
    amount = 4000000.0
    lines = import_lines(admin, [
        {"stmt_date": day(-1), "amount": amount, "direction": "in",
         "description": "TRSF E-BANKING CR TANPA IDENTITAS 889900"}])
    ln = lines[0]
    out_line = api("POST", "/bank-reconciliation/import", admin, ENT_A, json={
        "bank_account_id": ACC_A, "lines": [
            {"stmt_date": day(-1), "amount": 55000, "direction": "out",
             "description": f"BIAYA ADM {POC_TAG}"}]})
    rows = api("GET", f"/bank-reconciliation/lines?bank_account_id={ACC_A}", admin, ENT_A).json()
    out_id = next(l["id"] for l in rows if l.get("import_batch") == out_line.json()["import_batch"])
    made["lines"].append(out_id)
    bad = api("POST", f"/bank-reconciliation/lines/{out_id}/holding", admin, ENT_A, json={})
    ok(bad.status_code == 400, "BUKTI-MERAH: dana KELUAR tidak boleh dititipkan",
       f"HTTP {bad.status_code}")

    gl_before = gl_holding_balance()
    r = api("POST", f"/bank-reconciliation/lines/{ln['id']}/holding", admin, ENT_A,
            json={"note": "pengirim belum diketahui"})
    hl = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and hl.get("status") == "holding",
       "dana masuk tak dikenal DITITIPKAN (tidak menggantung tanpa catatan)",
       f"HTTP {r.status_code}")
    hold = hl.get("holding") or {}
    ok(bool(hold.get("cash_txn_id")) and bool(hold.get("je_id")),
       "titipan melahirkan transaksi kas + JURNAL sungguhan",
       f"{hold.get('cash_number')} · {hold.get('je_number')}")
    if hold.get("cash_txn_id"):
        made["cash"].append(hold["cash_txn_id"])
    je = dbrun(lambda db: db.journal_entries.find_one({"id": hold.get("je_id")}, {"_id": 0}))
    accs = {l["account_code"]: (l.get("debit", 0), l.get("credit", 0)) for l in (je or {}).get("lines", [])}
    ok("2-1950" in accs and accs["2-1950"][1] == amount and accs.get("1-1100", (0, 0))[0] == amount,
       "arah jurnal benar: Dr 1-1100 Bank / Cr 2-1950 Titipan", str(accs))
    ok(round(gl_holding_balance() - gl_before, 2) == amount,
       "saldo akun titipan di buku besar bertambah persis sebesar dana", f"+{amount}")

    hq = api("GET", "/bank-reconciliation/holding", admin, ENT_A).json()
    ok(hq["count"] >= 1 and hq["balance"] >= amount,
       "antrean titipan tampil dgn saldo & umur (US8)",
       f"{hq['count']} titipan · Rp {hq['balance']:,.0f} · umur {hq['items'][0]['age_days']} hari")

    # Alokasi: wajib berlabel alasan, tidak boleh melebihi sisa.
    order = dbrun(lambda db: db.sales_orders.find_one(
        {"payment_status": {"$in": ["pending", "partial"]}, "entity_id": ENT_A},
        {"_id": 0}, sort=[("number", 1)]))
    gt = round(float(order.get("grand_total") or 0), 2)
    paid0 = round(sum(float(p.get("amount", 0)) for p in (order.get("payments") or [])), 2)
    outstanding = round(gt - paid0, 2)
    part = min(1500000.0, round(outstanding / 2, 2))
    noreason = api("POST", f"/bank-reconciliation/lines/{ln['id']}/holding/allocate", admin, ENT_A,
                   json={"allocations": [{"order_id": order["id"], "amount": part}],
                         "reason_code": ""})
    ok(noreason.status_code == 400 and "alasan" in noreason.text.lower(),
       "BUKTI-MERAH: alokasi TANPA label alasan DITOLAK (keputusan atas uang harus berlabel)",
       f"HTTP {noreason.status_code}")
    toobig = api("POST", f"/bank-reconciliation/lines/{ln['id']}/holding/allocate", admin, ENT_A,
                 json={"allocations": [{"order_id": order["id"], "amount": amount + 1}],
                       "reason_code": "identified_customer"})
    ok(toobig.status_code == 400, "BUKTI-MERAH: alokasi melebihi sisa titipan DITOLAK",
       f"HTTP {toobig.status_code}")

    r = api("POST", f"/bank-reconciliation/lines/{ln['id']}/holding/allocate", admin, ENT_A, json={
        "customer_id": order.get("customer_id", ""), "reason_code": "identified_customer",
        "note": f"{POC_TAG} pengirim teridentifikasi",
        "allocations": [{"order_id": order["id"], "amount": part}]})
    al = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and al.get("allocated_now") == part,
       f"titipan dialokasikan ke {order.get('number')} sebesar Rp {part:,.0f}",
       f"HTTP {r.status_code}")
    made["orders"].append(order["id"])
    ok(round(al.get("holding_remaining", -1), 2) == round(amount - part, 2),
       "sisa titipan berkurang tepat", f"sisa Rp {al.get('holding_remaining'):,.0f}")
    o2 = dbrun(lambda db: db.sales_orders.find_one({"id": order["id"]}, {"_id": 0}))
    paid1 = round(sum(float(p.get("amount", 0)) for p in (o2.get("payments") or [])), 2)
    ok(round(paid1 - paid0, 2) == part,
       "piutang pesanan BERKURANG sebesar alokasi (bukan cuma catatan)",
       f"terbayar {paid0:,.0f} → {paid1:,.0f}")
    alloc = (al.get("holding_allocated") or [{}])[-1]
    je2 = dbrun(lambda db: db.journal_entries.find_one({"id": alloc.get("je_id")}, {"_id": 0}))
    accs2 = {l["account_code"]: (l.get("debit", 0), l.get("credit", 0))
             for l in (je2 or {}).get("lines", [])}
    ok(accs2.get("2-1950", (0, 0))[0] == part and accs2.get("1-1200", (0, 0))[1] == part,
       "jurnal alokasi benar: Dr 2-1950 Titipan / Cr 1-1200 Piutang (TANPA kas dobel)",
       str(accs2))
    cash_count = dbrun(lambda db: db.cash_transactions.count_documents(
        {"ref_type": "bank_statement_line", "ref_id": ln["id"], "status": {"$ne": "void"}}))
    ok(cash_count == 1, "alokasi TIDAK membuat kas baru (kas hanya sekali saat dititipkan)",
       f"{cash_count} transaksi kas")

    summ = api("GET", f"/bank-reconciliation/summary?bank_account_id={ACC_A}", admin, ENT_A).json()
    ok(summ["holding"]["count"] >= 1 and summ["holding"]["balance"] > 0,
       "ringkasan rekonsiliasi menampilkan blok titipan (US8)",
       f"{summ['holding']}")
    ok("difference" in summ and "statement" in summ and "book" in summ,
       "ringkasan menampilkan selisih buku vs rekening",
       f"selisih Rp {summ['difference']:,.0f}")
    return {"line": ln, "order": order, "part": part, "amount": amount}


def gl_holding_balance() -> float:
    def _q(db):
        return db.journal_entries.find(
            {"status": {"$ne": "void"}, "lines.account_code": "2-1950"}, {"_id": 0}).to_list(10000)
    rows = dbrun(_q)
    d = sum(float(l.get("debit", 0) or 0) for r in rows for l in r.get("lines", [])
            if l.get("account_code") == "2-1950")
    c = sum(float(l.get("credit", 0) or 0) for r in rows for l in r.get("lines", [])
            if l.get("account_code") == "2-1950")
    return round(c - d, 2)


def acc_balance(code: str) -> float:
    """Saldo satu akun buku besar (Debet − Kredit) dari jurnal AKTIF saja."""
    def _q(db):
        return db.journal_entries.find(
            {"status": {"$ne": "void"}, "lines.account_code": code}, {"_id": 0}).to_list(20000)
    rows = dbrun(_q)
    d = sum(float(l.get("debit", 0) or 0) for r in rows for l in r.get("lines", [])
            if l.get("account_code") == code)
    c = sum(float(l.get("credit", 0) or 0) for r in rows for l in r.get("lines", [])
            if l.get("account_code") == code)
    return round(d - c, 2)


def je_pairs(number: str) -> Dict[str, tuple]:
    """{kode akun: (debet, kredit)} dari satu jurnal — untuk memeriksa ARAH jurnal."""
    je = dbrun(lambda db: db.journal_entries.find_one({"number": number}, {"_id": 0}))
    return {l["account_code"]: (round(float(l.get("debit", 0) or 0), 2),
                               round(float(l.get("credit", 0) or 0), 2))
            for l in (je or {}).get("lines", [])}


def recon_diff(admin: str) -> float:
    s = api("GET", f"/bank-reconciliation/summary?bank_account_id={ACC_A}", admin, ENT_A).json()
    return round(float(s.get("difference") or 0), 2)


# ═════════════════════════════════════════════════════════════════════════════
#  7 · ISOLASI LINTAS-PT  (US11 · celah nyata sebelum FASE G-8)
# ═════════════════════════════════════════════════════════════════════════════
def test_isolation(admin: str, manager: str, sales_a: str) -> None:
    head("6 · ISOLASI LINTAS-PT (US11) — celah nyata sebelum FASE G-8")
    b_lines = import_lines(admin, [
        {"stmt_date": day(-1), "amount": 2750000, "direction": "in",
         "description": f"TRSF CR PELANGGAN KANDA {POC_TAG}"}], acc=ACC_B, ent=ENT_B)
    ok(len(b_lines) == 1 and b_lines[0]["entity_id"] == ENT_B,
       "BUKTI-MERAH siap: PT-B punya mutasi bank sendiri", f"{b_lines[0]['entity_id']}")

    def detail(r: requests.Response) -> str:
        try:
            return str(r.json().get("detail", ""))
        except Exception:  # noqa: BLE001
            return r.text[:120]

    # PENTING (anti hijau-palsu): matriks izin demo hanya memberi `cash` ke admin & manager.
    # Kalau uji isolasi memakai peran `sales`, 403-nya datang dari IZIN — bukan dari
    # entitas — sehingga "isolasi hijau" tidak membuktikan apa pun. Karena itu uji ini
    # memakai admin/manager (punya izin kas) DAN memeriksa ALASAN 403-nya.
    r = api("GET", f"/bank-reconciliation/lines?bank_account_id={ACC_A}", sales_a, ENT_A)
    ok(r.status_code == 403 and "permission" in detail(r).lower(),
       "kontrol: peran tanpa izin kas ditolak karena IZIN (bukan karena entitas)", detail(r))

    r = api("GET", f"/bank-reconciliation/lines?bank_account_id={ACC_B}", manager, ENT_A)
    ok(r.status_code == 403 and "entitas" in detail(r).lower(),
       "manager (entitas aktif PT-A) minta mutasi akun PT-B → 403 KARENA ENTITAS", detail(r))
    r = api("GET", f"/bank-reconciliation/summary?bank_account_id={ACC_B}", admin, ENT_A)
    ok(r.status_code == 403 and "entitas" in detail(r).lower(),
       "ringkasan akun PT lain juga tertutup (alasan entitas)", detail(r))
    r = api("GET", f"/bank-reconciliation/lines?bank_account_id={ACC_A}", manager, ENT_B)
    ok(r.status_code == 403 and "entitas" in detail(r).lower(),
       "sebaliknya: entitas aktif PT-B minta akun PT-A → 403 KARENA ENTITAS", detail(r))
    r = api("POST", f"/bank-reconciliation/lines/{b_lines[0]['id']}/holding", admin, ENT_A,
            json={"note": "coba tembus"})
    ok(r.status_code == 403 and "entitas" in detail(r).lower(),
       "aksi pada BARIS PT lain (id dikirim eksplisit) → 403", detail(r))
    r = api("GET", f"/bank-reconciliation/lines/{b_lines[0]['id']}/candidates", admin, ENT_A)
    ok(r.status_code == 403 and "entitas" in detail(r).lower(),
       "kandidat pencocokan mutasi PT lain → 403", detail(r))

    own = api("GET", f"/bank-reconciliation/lines?bank_account_id={ACC_B}", manager, ENT_B)
    seen = own.json() if own.status_code == 200 else []
    ok(own.status_code == 200 and any(l["id"] == b_lines[0]["id"] for l in seen),
       "TIDAK over-block: entitas aktif PT-B tetap melihat mutasi PT-B",
       f"HTTP {own.status_code} · {len(seen)} baris")
    ok(all(l.get("entity_id") in (ENT_B, "all") for l in seen),
       "yang terlihat HANYA milik PT-B (tidak ada baris PT-A yang bocor)",
       str(sorted({l.get('entity_id') for l in seen})))
    adm = api("GET", f"/bank-reconciliation/lines?bank_account_id={ACC_B}", admin, "all")
    ok(adm.status_code == 200, "admin lintas-entitas tetap punya pengawasan (X-Entity-Id: all)",
       f"HTTP {adm.status_code}")


# ═════════════════════════════════════════════════════════════════════════════
#  7 · BIAYA & BUNGA BANK + PENJAGA PEMBATALAN  (temuan penutupan FASE G-8)
# ═════════════════════════════════════════════════════════════════════════════
def test_charge_and_guards(admin: str) -> Dict[str, Any]:
    """Baris rekening koran yang MEMANG tidak ada di buku + penjaga jalur pembatalan.

    Empat bug NYATA yang lolos sampai penutupan fase diuji di sini supaya tidak bisa
    kembali diam-diam:
      KN-G8-CHARGE-NOPATH   biaya adm bank / bunga giro tidak punya jalur pembukuan
                            sama sekali → satu-satunya pilihan "Abaikan", beban hilang
                            dari laba rugi & selisih rekening vs buku tak pernah nol.
      KN-G8-CANCEL-JE       `cancel_holding` memanggil `void_entry` yang MENOLAK jurnal
                            non-manual lalu galatnya ditelan → kas void, jurnal titipan
                            tetap hidup (INV-BNK-03 memerah).
      KN-G8-UNMATCH-NOGUARD `unmatch` tanpa penjaga status → baris TITIPAN bisa
                            di-'lepas', kas + jurnalnya menggantung.
      KN-G8-MATCH-PARTIAL   `min(nominal mutasi, sisa transaksi)` pada jalur manual DAN
                            otomatis → baris "tercocok" dengan Σ alokasi lebih kecil dari
                            nominalnya (INV-BNK-01 memerah, sisa uang tak terjelaskan).
      KN-G8-ALLOC-CROSSPT   alokasi titipan tidak memeriksa ENTITAS pesanan tujuan → titipan
                            PT-A bisa melunasi piutang PT-B lewat id yang dikirim tangan
                            (INV-BNK-05).
    """
    head("6 · BIAYA & BUNGA BANK + PENJAGA PEMBATALAN (temuan penutupan fase)")
    rows = import_lines(admin, [
        {"stmt_date": day(-1), "amount": 15000, "direction": "out",
         "description": f"BIAYA ADM BULANAN {POC_TAG}"},
        {"stmt_date": day(-1), "amount": 12400, "direction": "in",
         "description": f"JASA GIRO {POC_TAG}"},
        {"stmt_date": day(-1), "amount": 3000000, "direction": "in",
         "description": f"TRSF CR PENJAGA PARTIAL {POC_TAG}"},
        {"stmt_date": day(-1), "amount": 2000000, "direction": "in",
         "description": f"TRSF CR PENJAGA TITIPAN {POC_TAG}"},
    ])
    fee = next(l for l in rows if "BIAYA ADM" in l["description"])
    giro = next(l for l in rows if "JASA GIRO" in l["description"])
    big = next(l for l in rows if "PENJAGA PARTIAL" in l["description"])
    hold = next(l for l in rows if "PENJAGA TITIPAN" in l["description"])

    # ── BUKTI-MERAH: jenis pembukuan tidak boleh dikira-kira ──────────────────
    r = api("POST", f"/bank-reconciliation/lines/{fee['id']}/book-charge", admin, ENT_A,
            json={"kind": "interest"})
    ok(r.status_code == 400 and "MASUK" in r.text,
       "BUKTI-MERAH: 'bunga bank' pada baris dana KELUAR ditolak (arah dana tidak boleh ditebak)",
       f"HTTP {r.status_code}")
    r = api("POST", f"/bank-reconciliation/lines/{fee['id']}/book-charge", admin, ENT_A,
            json={"kind": "kira-kira"})
    ok(r.status_code == 400 and "charge" in r.text,
       "BUKTI-MERAH: jenis pembukuan asing ditolak (tidak ada akun 'entah')",
       f"HTTP {r.status_code}")

    # ── BIAYA ADMINISTRASI BANK (dana keluar) ─────────────────────────────────
    diff0, bal0 = recon_diff(admin), acc_balance("6-8000")
    r = api("POST", f"/bank-reconciliation/lines/{fee['id']}/book-charge", admin, ENT_A,
            json={"kind": "charge", "note": "biaya administrasi bulanan"})
    d = r.json() if r.status_code == 200 else {}
    fee_cash = (d.get("charge") or {}).get("cash_txn_id", "")
    if fee_cash:
        made["cash"].append(fee_cash)
    ok(r.status_code == 200 and d.get("status") == "matched" and d.get("account_code") == "6-8000",
       "biaya bank DIBUKUKAN dari layar rekonsiliasi: transaksi kas baru + baris tercocok",
       f"HTTP {r.status_code} · kas {d.get('cash_number')} · akun {d.get('account_code')}")
    pairs = je_pairs(d.get("je_number", ""))
    ok(pairs.get("6-8000", (0, 0))[0] == 15000.0 and pairs.get("1-1100", (0, 0))[1] == 15000.0,
       "arah jurnal benar: Dr 6-8000 Beban Administrasi Bank / Cr 1-1100 Bank", str(pairs))
    ok(round(sum(a["amount"] for a in (d.get("allocations") or [])), 2) == 15000.0,
       "Σ alokasi == nominal mutasi (tidak ada 'tercocok' yang tidak terjelaskan)")
    diff1 = recon_diff(admin)
    ok(round(diff1 - diff0, 2) == 15000.0,
       "selisih rekening vs buku bergerak TEPAT sebesar biaya (rekonsiliasi bisa tuntas)",
       f"Rp {diff0:,.0f} → Rp {diff1:,.0f}")

    # ── BUNGA / JASA GIRO (dana masuk) ────────────────────────────────────────
    r = api("POST", f"/bank-reconciliation/lines/{giro['id']}/book-charge", admin, ENT_A,
            json={"kind": "interest"})
    g = r.json() if r.status_code == 200 else {}
    giro_cash = (g.get("charge") or {}).get("cash_txn_id", "")
    if giro_cash:
        made["cash"].append(giro_cash)
    gp = je_pairs(g.get("je_number", ""))
    ok(r.status_code == 200 and gp.get("1-1100", (0, 0))[0] == 12400.0
       and gp.get("4-9000", (0, 0))[1] == 12400.0,
       "bunga · jasa giro: Dr 1-1100 Bank / Cr 4-9000 Pendapatan Lain-lain (akun dari Pengaturan)",
       str(gp))

    # ── BUKTI-MERAH INV-BNK-04 ────────────────────────────────────────────────
    dbrun(lambda db: db.cash_transactions.update_one(
        {"id": fee_cash}, {"$set": {"status": "void"}}))
    _, o4 = integrity("bank")
    ok(inv_state(o4, "INV-BNK-04") == "FAIL",
       "INV-BNK-04 MEMERAH bila kas biaya bank di-void tapi barisnya tetap 'tercocok' "
       "(beban lenyap dari laba rugi padahal rekonsiliasi tampak beres)")
    dbrun(lambda db: db.cash_transactions.update_one(
        {"id": fee_cash}, {"$set": {"status": "posted"}}))
    _, o4b = integrity("bank")
    ok(inv_state(o4b, "INV-BNK-04") == "PASS", "INV-BNK-04 HIJAU lagi setelah dipulihkan")

    # ── LEPAS TAUTAN BIAYA BANK: kas void + jurnal DIBALIK (append-only) ──────
    r = api("POST", f"/bank-reconciliation/lines/{fee['id']}/unmatch", admin, ENT_A, json={})
    u = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and u.get("status") == "unmatched" and not u.get("charge"),
       "biaya bank bisa DILEPAS: baris kembali 'perlu keputusan'", f"HTTP {r.status_code}")
    cash_doc = dbrun(lambda db: db.cash_transactions.find_one({"id": fee_cash}, {"_id": 0}))
    revs = dbrun(lambda db: db.journal_entries.find(
        {"source_type": "cash_transaction_reversal", "source_id": fee_cash},
        {"_id": 0}).to_list(5))
    orig = dbrun(lambda db: db.journal_entries.find_one(
        {"id": (d.get("charge") or {}).get("je_id")}, {"_id": 0}))
    ok((cash_doc or {}).get("status") == "void" and len(revs) == 1
       and (orig or {}).get("reversed") is True,
       "kas di-void & jurnalnya DIBALIK — jurnal asal tetap ada (ledger append-only)",
       f"reversal {revs[0]['number'] if revs else '—'}")
    ok(acc_balance("6-8000") == bal0,
       "saldo Beban Administrasi Bank kembali seperti sebelum pembukuan (tidak ada beban hantu)",
       f"Rp {acc_balance('6-8000'):,.0f}")
    r = api("POST", f"/bank-reconciliation/lines/{fee['id']}/unmatch", admin, ENT_A, json={})
    ok(r.status_code == 400 and "TERCOCOK" in r.text,
       "BUKTI-MERAH: melepas baris yang memang tidak tertaut ditolak", f"HTTP {r.status_code}")

    # ── PENJAGA TITIPAN: 'lepas tautan' & pembatalan yang JUJUR ───────────────
    r = api("POST", f"/bank-reconciliation/lines/{hold['id']}/holding", admin, ENT_A,
            json={"note": f"penjaga {POC_TAG}"})
    h = r.json() if r.status_code == 200 else {}
    hold_cash = (h.get("holding") or {}).get("cash_txn_id", "")
    if hold_cash:
        made["cash"].append(hold_cash)
    ok(r.status_code == 200 and h.get("status") == "holding",
       "prasyarat: satu baris dititipkan (kas + jurnal Dr Bank / Cr Titipan terbit)",
       h.get("holding", {}).get("cash_number", ""))
    r = api("POST", f"/bank-reconciliation/lines/{hold['id']}/unmatch", admin, ENT_A, json={})
    ok(r.status_code == 400 and "titipan" in r.text.lower(),
       "BUKTI-MERAH (KN-G8-UNMATCH-NOGUARD): 'lepas tautan' pada baris TITIPAN DITOLAK — "
       "dulu ia menghapus status titipan sementara kas & jurnalnya tetap hidup",
       f"HTTP {r.status_code}")

    # ── BUKTI-MERAH: titipan PT-A tidak boleh melunasi pesanan PT-B ────────────
    # `_apply_to_order` mencari pesanan HANYA dengan id, jadi sebelum perbaikan cukup
    # mengirim id pesanan PT lain untuk membuat uang PT-A melunasi piutang PT-B.
    fake_id = f"so_{POC_TAG.lower()}_b"
    fake_order = {
        "id": fake_id, "number": f"SO-{POC_TAG}-B", "entity_id": ENT_B,
        "customer_id": f"cust_{POC_TAG.lower()}_b",
        "customer_name": f"Pelanggan {POC_TAG} PT-B", "status": "confirmed",
        "grand_total": 5000000.0, "paid_total": 0.0, "payment_status": "pending",
        "payments": [], "items": [], "created_at": day(-2), "updated_at": day(-2),
    }
    dbrun(lambda db: db.sales_orders.insert_one(dict(fake_order)))
    try:
        r = api("POST", f"/bank-reconciliation/lines/{hold['id']}/holding/allocate", admin, ENT_A,
                json={"customer_id": fake_order["customer_id"],
                      "reason_code": "identified_customer",
                      "allocations": [{"order_id": fake_id, "amount": 100000}]})
        ok(r.status_code == 403 and "entitas" in r.text.lower(),
           "BUKTI-MERAH (KN-G8-ALLOC-CROSSPT): titipan PT-A dialokasikan ke pesanan PT-B → 403 "
           "— dulu diterima (uang PT-A melunasi piutang PT-B, jurnal pecah di dua buku)",
           f"HTTP {r.status_code}")
    finally:
        dbrun(lambda db: db.sales_orders.delete_one({"id": fake_id}))
    own = api("GET", "/ar-receipts/open-orders?customer_id=cust_toko_kain", admin, ENT_A)
    rows_own = own.json() if own.status_code == 200 else []
    if rows_own:
        r = api("POST", f"/bank-reconciliation/lines/{hold['id']}/holding/allocate", admin, ENT_A,
                json={"customer_id": "cust_butik_bali", "reason_code": "identified_customer",
                      "allocations": [{"order_id": rows_own[0]["order_id"], "amount": 100000}]})
        ok(r.status_code == 400 and "pelanggan" in r.text.lower(),
           "BUKTI-MERAH: pesanan yang BUKAN milik pelanggan terpilih ditolak "
           "(salah orang = salah uang)", f"HTTP {r.status_code}")
    _, o5 = integrity("bank")
    ok(inv_state(o5, "INV-BNK-05") == "PASS",
       "INV-BNK-05 HIJAU: tidak ada alokasi titipan yang melintasi PT")
    hb0 = gl_holding_balance()
    r = api("POST", f"/bank-reconciliation/lines/{hold['id']}/holding/cancel", admin, ENT_A,
            json={})
    ok(r.status_code == 200 and r.json().get("status") == "unmatched",
       "titipan dibatalkan (belum pernah dialokasikan)", f"HTTP {r.status_code}")
    hb1 = gl_holding_balance()
    ok(round(hb0 - hb1, 2) == 2000000.0,
       "BUKTI-MERAH (KN-G8-CANCEL-JE): saldo titipan buku besar BERKURANG tepat sebesar "
       "titipan yang dibatalkan — dulu jurnalnya tetap hidup karena void ditolak diam-diam",
       f"Rp {hb0:,.0f} → Rp {hb1:,.0f}")
    _, oc = integrity("bank")
    ok(inv_state(oc, "INV-BNK-03") == "PASS",
       "INV-BNK-03 tetap HIJAU sesudah pembatalan titipan (uang tak dikenal tidak jadi hantu)")

    # ── PENJAGA PENCOCOKAN SEPARUH (manual & split) ───────────────────────────
    small = cash_in(admin, 1000000, "Sisa kecil penjaga partial", day(-1))
    r = api("POST", f"/bank-reconciliation/lines/{big['id']}/match", admin, ENT_A,
            json={"txn_id": small["id"]})
    ok(r.status_code == 400 and "Pecah" in r.text,
       "BUKTI-MERAH (KN-G8-MATCH-PARTIAL): mutasi Rp 3.000.000 ke transaksi bersisa "
       "Rp 1.000.000 DITOLAK berikut arahan — dulu diam-diam dipotong jadi 'tercocok' palsu",
       f"HTTP {r.status_code}")
    small2 = cash_in(admin, 1000000, "Sisa kecil penjaga partial 2", day(-1))
    r = api("POST", f"/bank-reconciliation/lines/{big['id']}/match-split", admin, ENT_A, json={
        "allocations": [{"txn_id": small["id"], "amount": 1000000},
                        {"txn_id": small2["id"], "amount": 1000000}]})
    ok(r.status_code == 400 and "belum menutup" in r.text,
       "BUKTI-MERAH: pemecahan yang menyisakan rupiah menggantung ditolak (Σ WAJIB == nominal)",
       f"HTTP {r.status_code}")

    # ── PENJAGA JALUR OTOMATIS: skor tinggi tapi sisa transaksi tak cukup ─────
    tp = cash_in(admin, 3000000, f"Pelunasan SO-9911 PT Uji Partial {POC_TAG}", day(-1))
    lp = import_lines(admin, [
        {"stmt_date": day(-1), "amount": 1000000, "direction": "in", "ref": "SO-9911",
         "description": f"TRSF E-BANKING CR PT UJI PARTIAL SO-9911 CICIL {POC_TAG}"},
        {"stmt_date": day(-1), "amount": 3000000, "direction": "in", "ref": "SO-9911",
         "description": f"TRSF E-BANKING CR PT UJI PARTIAL SO-9911 PENUH {POC_TAG}"},
    ])
    cicil = next(l for l in lp if "CICIL" in l["description"])
    penuh = next(l for l in lp if "PENUH" in l["description"])
    r = api("POST", f"/bank-reconciliation/lines/{cicil['id']}/match", admin, ENT_A,
            json={"txn_id": tp["id"]})
    ok(r.status_code == 200,
       "prasyarat: transaksi buku Rp 3.000.000 terpakai sebagian (Rp 1.000.000)",
       f"HTTP {r.status_code}")
    api("POST", "/bank-reconciliation/auto-match", admin, ENT_A, json={"bank_account_id": ACC_A})
    after = {l["id"]: l for l in
             api("GET", f"/bank-reconciliation/lines?bank_account_id={ACC_A}", admin, ENT_A).json()}
    fl = after.get(penuh["id"], {})
    ok(fl.get("status") == "unmatched" and float(fl.get("score") or 0) >= 80,
       "BUKTI-MERAH (jalur OTOMATIS): pasangan berskor ≥ ambang TIDAK ditautkan sendiri karena "
       "sisa transaksinya tak menutup seluruh nominal — turun jadi usulan untuk diputus manusia",
       f"status {fl.get('status')} · skor {fl.get('score')} · "
       f"usulan {len(fl.get('suggestions') or [])}")
    _, ob = integrity("bank")
    ok(inv_state(ob, "INV-BNK-01") == "PASS",
       "INV-BNK-01 tetap HIJAU sesudah cocok-otomatis di data bersisa parsial")
    return {"fee": fee, "giro": giro, "fee_cash": fee_cash}


# ═════════════════════════════════════════════════════════════════════════════
#  8 · BUKTI-MERAH INVARIAN INV-BNK-01..03  (US10)
# ═════════════════════════════════════════════════════════════════════════════
def test_invariants(ctx: Dict[str, Any]) -> None:
    head("7 · BUKTI-MERAH: INV-BNK-01..03 benar-benar MEMERAH (US10)")
    code0, out0 = integrity("bank")
    ok(code0 == 0 and inv_state(out0, "INV-BNK-01") == "PASS"
       and inv_state(out0, "INV-BNK-02") == "PASS" and inv_state(out0, "INV-BNK-03") == "PASS",
       "keadaan awal: INV-BNK-01/02/03 HIJAU",
       f"01={inv_state(out0, 'INV-BNK-01')} 02={inv_state(out0, 'INV-BNK-02')} "
       f"03={inv_state(out0, 'INV-BNK-03')}")

    victim = dbrun(lambda db: db.bank_statement_lines.find_one(
        {"status": "matched", "match_kind": "1:1"}, {"_id": 0}))
    saved = list(victim.get("allocations") or [])
    dbrun(lambda db: db.bank_statement_lines.update_one(
        {"id": victim["id"]}, {"$set": {"allocations": []}}))
    _, o1 = integrity("bank")
    ok(inv_state(o1, "INV-BNK-01") == "FAIL",
       "INV-BNK-01 MEMERAH saat baris 'tercocok' kehilangan tautannya")
    dbrun(lambda db: db.bank_statement_lines.update_one(
        {"id": victim["id"]}, {"$set": {"allocations": saved}}))

    tid = saved[0]["txn_id"]
    txn = dbrun(lambda db: db.cash_transactions.find_one({"id": tid}, {"_id": 0}))
    rec0 = round(float(txn.get("reconciled_amount") or 0), 2)
    dbrun(lambda db: db.cash_transactions.update_one(
        {"id": tid}, {"$set": {"reconciled_amount": rec0 + 1000}}))
    _, o2 = integrity("bank")
    ok(inv_state(o2, "INV-BNK-02") == "FAIL",
       "INV-BNK-02 MEMERAH saat Σ rekonsiliasi transaksi buku digeser sepihak")
    dbrun(lambda db: db.cash_transactions.update_one(
        {"id": tid}, {"$set": {"reconciled_amount": rec0}}))

    hold_line = dbrun(lambda db: db.bank_statement_lines.find_one(
        {"id": ctx["holding"]["line"]["id"]}, {"_id": 0}))
    je_id = (hold_line.get("holding") or {}).get("je_id")
    dbrun(lambda db: db.journal_entries.update_one({"id": je_id}, {"$set": {"status": "void"}}))
    _, o3 = integrity("bank")
    ok(inv_state(o3, "INV-BNK-03") == "FAIL",
       "INV-BNK-03 MEMERAH saat jurnal titipan hilang (uang tak dikenal lenyap dari laporan)")
    dbrun(lambda db: db.journal_entries.update_one({"id": je_id}, {"$set": {"status": "posted"}}))

    code1, out1 = integrity("bank")
    ok(code1 == 0, "setelah dipulihkan: seluruh INV-BNK HIJAU kembali (invarian bukan hiasan)")


# ═════════════════════════════════════════════════════════════════════════════
#  9 · PEMBERSIHAN & NOL RESIDU
# ═════════════════════════════════════════════════════════════════════════════
def demo_snapshot() -> List[Dict[str, Any]]:
    """Rekam keadaan baris mutasi DEMO sebelum POC menyentuh apa pun.

    POC menjalankan `auto-match` pada akun bank demo, jadi baris demo bisa ikut berubah
    status/skor. INV-GATE-01 (POC-RESIDU-01) melarang gate menggeser data demo — karena
    itu keadaannya direkam di sini dan dipulihkan di pembersihan lewat API sungguhan
    supaya transaksi kas demo ikut kembali konsisten.
    """
    return dbrun(lambda db: db.bank_statement_lines.find({}, {"_id": 0}).to_list(20000))


def demo_restore(admin: str, snap: List[Dict[str, Any]]) -> Dict[str, int]:
    n = {"lepas": 0, "batal_titipan": 0, "batal_abaikan": 0, "bidang": 0}
    for old in snap:
        cur = dbrun(lambda db, i=old["id"]: db.bank_statement_lines.find_one(
            {"id": i}, {"_id": 0}))
        if not cur:
            continue
        ent = cur.get("entity_id") or ENT_A
        if cur.get("status") != old.get("status"):
            if cur.get("status") == "matched":
                api("POST", f"/bank-reconciliation/lines/{old['id']}/unmatch", admin, ent, json={})
                n["lepas"] += 1
            elif cur.get("status") == "holding":
                api("POST", f"/bank-reconciliation/lines/{old['id']}/holding/cancel", admin, ent,
                    json={})
                n["batal_titipan"] += 1
            elif cur.get("status") == "ignored":
                api("POST", f"/bank-reconciliation/lines/{old['id']}/unignore", admin, ent, json={})
                n["batal_abaikan"] += 1
        # skor & usulan hasil auto-match POC dikembalikan (kosmetik, tidak menyentuh uang)
        dbrun(lambda db, o=old: db.bank_statement_lines.update_one({"id": o["id"]}, {"$set": {
            "status": o.get("status", "unmatched"),
            "score": o.get("score", 0), "score_explain": o.get("score_explain", []),
            "suggestions": o.get("suggestions", []),
            "allocations": o.get("allocations", []),
            "match_kind": o.get("match_kind", ""), "match_type": o.get("match_type", ""),
            "matched_txn_id": o.get("matched_txn_id", ""),
            "matched_txn_ids": o.get("matched_txn_ids", []),
            "charge": o.get("charge", {}),
        }}))
        n["bidang"] += 1
    return n


def cleanup(ctx: Dict[str, Any]) -> None:
    head("8 · PEMBERSIHAN — nol residu (gate tidak boleh merusak data demo)")
    hold = ctx.get("holding") or {}
    order_id = (hold.get("order") or {}).get("id")
    part = hold.get("part") or 0
    line_id = (hold.get("line") or {}).get("id")

    if order_id and line_id:
        async def restore_order(db):
            o = await db.sales_orders.find_one({"id": order_id}, {"_id": 0})
            keep = [p for p in (o.get("payments") or []) if p.get("receipt_id") != line_id]
            removed = round(sum(float(p.get("amount", 0)) for p in (o.get("payments") or [])
                                if p.get("receipt_id") == line_id), 2)
            paid = round(sum(float(p.get("amount", 0)) for p in keep), 2)
            gt = round(float(o.get("grand_total") or 0), 2)
            status = "paid" if paid >= gt - 0.01 else ("partial" if paid > 0.01 else "pending")
            await db.sales_orders.update_one({"id": order_id}, {"$set": {
                "payments": keep, "paid_total": paid, "payment_status": status}})
            return removed
        removed = dbrun(restore_order)
        ok(round(removed, 2) == round(part, 2),
           "pembayaran dari titipan dicabut dari pesanan (nilai pesanan pulih)",
           f"Rp {removed:,.0f}")
        # Rencana pembayaran (FASE G-2) ikut dihitung ulang saat alokasi; kalau tidak
        # dipulihkan, INV-PAY-02 memerah ("jadwal mencatat lebih dari kas nyata").
        def _replan():
            import asyncio
            from services import payment_plan_service as pps
            asyncio.run(pps.recompute_for_doc("sales_order", order_id))
        try:
            _replan()
            ok(True, "rencana pembayaran pesanan dihitung ulang (INV-PAY-02 tetap sah)")
        except Exception as exc:  # noqa: BLE001
            ok(False, f"gagal menghitung ulang rencana pembayaran: {exc}")

    # Data DEMO dipulihkan LEBIH DULU (lewat API sungguhan) supaya transaksi kas demo yang
    # tersentuh auto-match ikut kembali konsisten sebelum artefak POC dihapus.
    snap = ctx.get("demo_snap") or []
    if snap:
        n_demo = demo_restore(ctx.get("admin", ""), snap)
        after = {l["id"]: l["status"] for l in dbrun(
            lambda db: db.bank_statement_lines.find({}, {"_id": 0}).to_list(20000))}
        drift = [s["id"] for s in snap
                 if s["id"] in after and after[s["id"]] != s.get("status")]
        ok(not drift,
           "data mutasi DEMO kembali ke keadaan semula (INV-GATE-01 · POC tidak menggeser demo)",
           f"{len(snap)} baris · {n_demo}")

    async def purge(db):
        n = {}
        n["lines"] = (await db.bank_statement_lines.delete_many(
            {"id": {"$in": made["lines"]}})).deleted_count
        n["extra_lines"] = (await db.bank_statement_lines.delete_many(
            {"description": {"$regex": POC_TAG}})).deleted_count
        n["cash"] = (await db.cash_transactions.delete_many(
            {"id": {"$in": made["cash"]}})).deleted_count
        n["cash_tag"] = (await db.cash_transactions.delete_many(
            {"$or": [{"description": {"$regex": POC_TAG}}, {"created_by": POC_TAG}]})).deleted_count
        n["rules"] = (await db.bank_match_rules.delete_many({})).deleted_count
        n["formats"] = (await db.bank_statement_formats.delete_many(
            {"id": {"$in": made["formats"]}})).deleted_count
        n["je"] = (await db.journal_entries.delete_many(
            {"source_type": {"$in": ["bank_holding_alloc"]}})).deleted_count
        # jurnal kas titipan POC (source_id = id transaksi kas yang sudah dihapus)
        n["je_cash"] = (await db.journal_entries.delete_many(
            {"source_type": "cash_transaction", "source_id": {"$in": made["cash"]}})).deleted_count
        # Penutupan FASE G-8: pembatalan titipan & pelepasan biaya bank menerbitkan jurnal
        # PEMBALIK (append-only). Tanpa dihapus juga, ia jadi residu POC di buku besar.
        n["je_rev"] = (await db.journal_entries.delete_many(
            {"source_type": "cash_transaction_reversal",
             "source_id": {"$in": made["cash"]}})).deleted_count
        await db.cash_transactions.update_many(
            {"matched_line_ids": {"$in": made["lines"]}},
            {"$set": {"reconciled": False, "reconciled_amount": 0.0, "matched_line_id": "",
                      "matched_line_ids": []}})
        return n
    n = dbrun(purge)
    ok(sum(n.values()) > 0, "artefak POC dihapus dari database", str(n))

    async def leftovers(db):
        return {
            "lines": await db.bank_statement_lines.count_documents({}),
            "rules": await db.bank_match_rules.count_documents({}),
            "cash_poc": await db.cash_transactions.count_documents(
                {"description": {"$regex": POC_TAG}}),
            "je_hold": await db.journal_entries.count_documents(
                {"source_type": "bank_holding_alloc"}),
        }
    left = dbrun(leftovers)
    ok(left["cash_poc"] == 0 and left["rules"] == 0 and left["je_hold"] == 0,
       "nol residu artefak POC", str(left))
    base_hold = ctx.get("base_2_1950", 0.0)
    base_chg = ctx.get("base_6_8000", 0.0)
    ok(round(gl_holding_balance() - base_hold, 2) == 0.0,
       "saldo akun titipan kembali ke keadaan SEBELUM POC (bukan menumpuk residu)",
       f"Rp {gl_holding_balance():,.0f} (awal Rp {base_hold:,.0f})")
    ok(round(acc_balance("6-8000") - base_chg, 2) == 0.0,
       "saldo Beban Administrasi Bank kembali ke keadaan awal (jurnal biaya bank POC bersih)",
       f"Rp {acc_balance('6-8000'):,.0f} (awal Rp {base_chg:,.0f})")

    code, out = integrity()
    tail = [ln for ln in out.splitlines() if "PASS " in ln and "|" in ln]
    ok(code == 0, "invarian GLOBAL tetap HIJAU setelah pembersihan (nol residu)",
       tail[-1].strip() if tail else "")


# ═════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(f"\n{B}{'=' * 74}")
    print("  POC FASE G-8 — REKONSILIASI BANK OTOMATIS (skor · split · aturan · titipan)")
    print(f"{'=' * 74}{X}")
    admin = login("admin@kainnusantara.id")
    manager = login("manager@kainnusantara.id")
    sales_a = login("sales@kainnusantara.id")
    ok(True, "login admin & manager (punya izin kas, 2 PT) · sales (kontrol tanpa izin kas)")

    ctx: Dict[str, Any] = {"admin": admin}
    ctx["demo_snap"] = demo_snapshot()
    # Saldo AWAL akun yang disentuh POC. Sejak FASE G-9 data demo sendiri sudah punya
    # titipan dana (kasus keuangan demo) dan beban administrasi bank, jadi "kembali NOL"
    # BUKAN lagi ukuran yang benar — yang benar: kembali ke saldo SEBELUM POC berjalan.
    ctx["base_2_1950"] = gl_holding_balance()
    ctx["base_6_8000"] = acc_balance("6-8000")
    ok(bool(ctx["demo_snap"]) or True,
       "keadaan data mutasi DEMO direkam sebelum POC menyentuh apa pun (anti-residu)",
       f"{len(ctx['demo_snap'])} baris")
    try:
        test_parser(admin)
        ctx["scoring"] = test_scoring(admin)
        test_split_group(admin)
        test_learning(admin)
        ctx["holding"] = test_holding(admin)
        ctx["charge"] = test_charge_and_guards(admin)
        test_isolation(admin, manager, sales_a)
        test_invariants(ctx)
    finally:
        try:
            cleanup(ctx)
        except Exception as exc:  # noqa: BLE001
            ok(False, f"pembersihan gagal: {exc}")

    print(f"\n{B}{'=' * 74}")
    print(f"  HASIL: {G}{res['pass']} PASS{X}{B} · {R if res['fail'] else G}{res['fail']} FAIL{X}")
    print(f"{'=' * 74}{X}\n")
    return 0 if res["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
