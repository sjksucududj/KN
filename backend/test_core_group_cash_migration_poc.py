#!/usr/bin/env python3
"""POC F-1b — UTANG MIGRASI (i): **KAS TINGKAT GRUP → PER BADAN USAHA** (E7e).

MENGAPA POC INI ADA
===================
`plan.md` §8 mencatat utang: *"pemetaan 13 transaksi 'Kas Besar Grup' ke entitas
pemiliknya (butuh konfirmasi per baris dari pemilik)"*. Alatnya sudah ada
(`scripts/migrate_e7_group_cash.py --report/--apply`) tetapi **belum pernah
dibuktikan bekerja**, dan data demo hari ini **nol** baris tingkat grup — jadi
menjalankan alat itu di data bersih hanya mencetak "tidak ada yang perlu
dimigrasikan". Itu bukan bukti; itu kebetulan.

Utang ini ditutup dengan cara yang bisa diperiksa siapa pun: POC ini **membuat
kembali keadaan warisan** (1 rekening "Kas Besar Grup" + 13 transaksi dengan
empat lapis bukti berbeda + 2 baris yang memang tak terbuktikan), menjalankan
alat migrasi SUNGGUHAN, lalu memeriksa hasilnya baris demi baris. Semuanya
dipulihkan lewat snapshot di akhir (INV-GATE-01: gate tak boleh meninggalkan residu).

YANG DIBUKTIKAN
---------------
G1 `--report` TIDAK MENULIS apa pun (dua kali dijalankan, data tetap sama).
G2 Empat lapis bukti memetakan pemilik dengan BENAR:
   ref dokumen (kwitansi AR) · `source_entity_id` · prefix nomor di uraian · rekening.
G3 Baris TANPA bukti **tidak ditebak**: tetap tingkat grup, ditandai
   `needs_entity_mapping`, dan dibuatkan **kasus keuangan** `salah_entitas`
   supaya ada orang yang memutuskan. (Inilah "konfirmasi per baris" yang diminta
   pemilik — dilakukan lewat layar, bukan tebakan skrip.)
G4 Rekening grup **tidak dihapus** dan **belum dinonaktifkan** selama masih ada
   transaksi yang belum terbukti pemiliknya; setiap badan usaha mendapat
   **cermin rekening** (`… — KSC` / `… — Kanda`) dengan `migrated_from` yang jelas.
G5 IDEMPOTENT: `--apply` kedua tidak menggandakan cermin maupun kasus.
G6 Setelah keputusan orang (2 baris sisa diberi pemilik), `--apply` berikutnya
   **menonaktifkan** rekening grup — utang tertutup TANPA menghapus jejak.
G7 Nol residu: seluruh koleksi yang tersentuh pulih ke keadaan sebelum POC.

Usage:  python backend/test_core_group_cash_migration_poc.py
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(ROOT / "scripts" / "guardrails"))
from _common import DbSnapshot  # noqa: E402

G, R, Y, B, DIM, X = ("\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[2m", "\033[0m")

GROUP_ACC = "bank_kas_besar_grup_poc"
PREFIX = "poc_e7e_"
#: koleksi yang tersentuh POC ini (snapshot & restore eksplisit)
TOUCHED = ["cash_transactions", "bank_accounts", "finance_cases", "audit_logs",
           "notifications", "login_attempts"]

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


def run_migrasi(*args):
    """Jalankan alat migrasi sungguhan sebagai proses terpisah (seperti operator)."""
    cmd = [sys.executable, str(ROOT / "scripts/migrate_e7_group_cash.py"), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=180)
    return p.returncode, p.stdout + p.stderr


def buat_keadaan_warisan(db):
    """13 transaksi tingkat grup + 1 rekening grup, meniru data sebelum FASE E7e."""
    ar_ksc = db.ar_receipts.find_one({"entity_id": "ent_ksc"}, {"_id": 0, "id": 1, "number": 1})
    ar_kanda = db.ar_receipts.find_one({"entity_id": "ent_kanda"}, {"_id": 0, "id": 1, "number": 1})
    acc_ksc = db.bank_accounts.find_one({"entity_id": "ent_ksc"}, {"_id": 0, "id": 1, "name": 1})
    if not (ar_ksc and ar_kanda and acc_ksc):
        return None

    db.bank_accounts.insert_one({
        "id": GROUP_ACC, "name": "Kas Besar Grup", "account_type": "cash",
        "bank_name": "", "account_number": "", "entity_id": "all",
        "opening_balance": 25_000_000.0, "currency": "IDR",
        "note": "warisan sebelum E7e (POC)", "is_active": True,
    })

    rows, harap = [], {}

    def add(n, **kw):
        tid = f"{PREFIX}{n:02d}"
        rows.append({
            "id": tid, "number": f"POC-CASH-{n:02d}", "cash_type": "kas_besar",
            "direction": kw.pop("direction", "in"), "amount": kw.pop("amount", 1_000_000.0),
            "category": "lain", "entity_id": "all", "status": "posted",
            "txn_date": f"2026-07-{n:02d}T03:00:00+00:00", "created_by": "poc",
            "account_id": kw.pop("account_id", GROUP_ACC),
            "ref_type": kw.pop("ref_type", "manual"), "ref_id": kw.pop("ref_id", ""),
            "description": kw.pop("description", "Transaksi warisan tanpa keterangan"),
            **kw,
        })
        return tid

    # lapis 1 — ref dokumen (paling kuat)
    for n in (1, 2):
        harap[add(n, ref_type="ar_receipt", ref_id=ar_ksc["id"],
                  description=f"Penerimaan {ar_ksc['number']}")] = ("ent_ksc", "ref dokumen")
    harap[add(3, ref_type="ar_receipt", ref_id=ar_kanda["id"],
              description=f"Penerimaan {ar_kanda['number']}")] = ("ent_kanda", "ref dokumen")
    # lapis 2 — jejak source_entity_id
    for n in (4, 5, 6):
        harap[add(n, source_entity_id="ent_kanda",
                  description="Setoran tunai (jejak entitas sumber)")] = ("ent_kanda", "source_entity_id")
    # lapis 3 — prefix nomor dokumen di uraian
    for n in (7, 8):
        harap[add(n, description="Pelunasan KANDA/AR-00099 via kas besar")] = ("ent_kanda", "prefix uraian")
    harap[add(9, description="Pelunasan KSC/AR-00099 via kas besar")] = ("ent_ksc", "prefix uraian")
    # lapis 4 — rekening yang sudah punya badan usaha
    for n in (10, 11):
        harap[add(n, account_id=acc_ksc["id"],
                  description="Biaya operasional dibayar dari rekening KSC",
                  direction="out")] = ("ent_ksc", "rekening")
    # tanpa bukti apa pun — WAJIB tidak ditebak
    tanpa_bukti = [add(12, description="Transfer masuk tanpa keterangan"),
                   add(13, description="Setoran tunai tanpa keterangan")]
    for t in tanpa_bukti:
        harap[t] = ("", "tanpa bukti")

    db.cash_transactions.insert_many(rows)
    return {"harap": harap, "tanpa_bukti": tanpa_bukti, "acc_ksc": acc_ksc["id"]}


def main() -> int:
    print(f"{B}{'=' * 78}\n  POC F-1b — MIGRASI KAS TINGKAT GRUP (utang migrasi i)\n{'=' * 78}{X}")
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=4000)[
        os.environ.get("DB_NAME", "test_database")]
    db.command("ping")

    sisa_awal = db.cash_transactions.count_documents({"entity_id": {"$in": ["all", "", None]}})
    print(f"\n{B}▶ G0 — keadaan data hari ini{X}")
    ok(sisa_awal == 0, "data demo saat ini NOL transaksi kas tingkat grup",
       f"(ditemukan {sisa_awal}) — utang ini tentang ALAT-nya, bukan data sekarang")

    snap = DbSnapshot(db, collections=TOUCHED).take()
    try:
        fx = buat_keadaan_warisan(db)
        if not fx:
            print(f"{R}Data demo tidak lengkap (butuh kwitansi AR & rekening KSC).{X}")
            return 2
        harap, tanpa_bukti = fx["harap"], fx["tanpa_bukti"]
        print(f"\n{B}▶ G1 — `--report` tidak boleh menulis apa pun{X}")
        before = list(db.cash_transactions.find({"id": {"$regex": f"^{PREFIX}"}},
                                               {"_id": 0}).sort("id", 1))
        rc, out = run_migrasi("--report")
        ok(rc == 0, "`--report` selesai tanpa galat", f"rc={rc}")
        ok("13" in out, "laporan menyebut 13 transaksi tingkat grup")
        ok("Terbukti pemiliknya" in out and "Belum terbukti" in out,
           "laporan memisahkan yang terbukti vs belum terbukti")
        after = list(db.cash_transactions.find({"id": {"$regex": f"^{PREFIX}"}},
                                               {"_id": 0}).sort("id", 1))
        ok(before == after, "data TIDAK berubah setelah `--report` (mode laporan sungguh read-only)")

        print(f"\n{B}▶ G2 — empat lapis bukti memetakan pemilik dengan benar{X}")
        rc, out = run_migrasi("--apply")
        ok(rc == 0, "`--apply` selesai tanpa galat", f"rc={rc}")
        for tid, (ent, lapis) in sorted(harap.items()):
            doc = db.cash_transactions.find_one({"id": tid}, {"_id": 0})
            if ent:
                ok(doc.get("entity_id") == ent,
                   f"{tid} ({lapis:16s}) → {ent}",
                   f"dapat {doc.get('entity_id')} · bukti: {doc.get('migration_evidence', '—')}")

        print(f"\n{B}▶ G3 — baris tanpa bukti TIDAK ditebak (butuh keputusan orang){X}")
        for tid in tanpa_bukti:
            doc = db.cash_transactions.find_one({"id": tid}, {"_id": 0})
            ok(doc.get("entity_id") in ("all", "", None),
               f"{tid} tetap tingkat grup (tidak ditebak)", f"entity_id={doc.get('entity_id')!r}")
            ok(doc.get("needs_entity_mapping") is True,
               f"{tid} ditandai `needs_entity_mapping` (tetap terlihat)")
            kasus = db.finance_cases.find_one({"source.id": tid, "case_type": "salah_entitas"},
                                              {"_id": 0, "number": 1, "title": 1})
            ok(bool(kasus), f"{tid} dibuatkan kasus keuangan `salah_entitas`",
               f"{(kasus or {}).get('number', '')} {(kasus or {}).get('title', '')}")

        print(f"\n{B}▶ G4 — cermin rekening per badan usaha; rekening grup TIDAK dihapus{X}")
        for ent, short in (("ent_ksc", "KSC"), ("ent_kanda", "Kanda")):
            mir = db.bank_accounts.find_one({"migrated_from": GROUP_ACC, "entity_id": ent},
                                            {"_id": 0, "id": 1, "name": 1, "opening_balance": 1})
            ok(bool(mir), f"cermin rekening untuk {short} dibuat",
               f"{(mir or {}).get('id', '')} · {(mir or {}).get('name', '')}")
            if mir:
                ok(mir.get("opening_balance") == 0.0,
                   f"cermin {short} bersaldo awal 0 (saldo awal tetap di rekening lama)")
        grp = db.bank_accounts.find_one({"id": GROUP_ACC}, {"_id": 0})
        ok(grp is not None, "rekening grup TIDAK dihapus (riwayat rekonsiliasi menunjuk id-nya)")
        ok(grp.get("is_active") is True,
           "rekening grup BELUM dinonaktifkan selama 2 baris belum terbukti pemiliknya",
           f"is_active={grp.get('is_active')}")

        print(f"\n{B}▶ G5 — IDEMPOTENT: `--apply` kedua tidak menggandakan apa pun{X}")
        cermin1 = db.bank_accounts.count_documents({"migrated_from": GROUP_ACC})
        kasus1 = db.finance_cases.count_documents({"case_type": "salah_entitas"})
        rc, _ = run_migrasi("--apply")
        ok(rc == 0, "`--apply` kedua selesai tanpa galat", f"rc={rc}")
        ok(db.bank_accounts.count_documents({"migrated_from": GROUP_ACC}) == cermin1,
           "jumlah cermin rekening tetap", f"{cermin1}")
        ok(db.finance_cases.count_documents({"case_type": "salah_entitas"}) == kasus1,
           "jumlah kasus keuangan tetap (dedup by source.id)", f"{kasus1}")

        print(f"\n{B}▶ G6 — setelah keputusan orang, rekening grup dinonaktifkan{X}")
        # Keputusan pemilik (sesi 2026-08-15: "anda atur saja, ini masih demo"):
        # 2 baris sisa ditetapkan milik KSC — badan usaha pemilik kas besar itu.
        db.cash_transactions.update_many(
            {"id": {"$in": tanpa_bukti}},
            {"$set": {"entity_id": "ent_ksc", "needs_entity_mapping": False,
                      "migration_note": "keputusan pemilik 2026-08-15 (data demo)"}})
        rc, out = run_migrasi("--apply")
        ok(rc == 0, "`--apply` setelah keputusan selesai tanpa galat", f"rc={rc}")
        grp = db.bank_accounts.find_one({"id": GROUP_ACC}, {"_id": 0})
        ok(grp.get("is_active") is False and grp.get("retired_by") == "E7e",
           "rekening grup dinonaktifkan (bukan dihapus) — utang migrasi tertutup",
           f"is_active={grp.get('is_active')} retired_by={grp.get('retired_by')}")
        sisa = db.cash_transactions.count_documents(
            {"entity_id": {"$in": ["all", "", None]}, "status": {"$ne": "void"}})
        ok(sisa == 0, "nol transaksi kas tingkat grup tersisa", f"sisa={sisa}")
    finally:
        snap.restore()

    print(f"\n{B}▶ G7 — nol residu setelah POC{X}")
    ok(db.cash_transactions.count_documents({"id": {"$regex": f"^{PREFIX}"}}) == 0,
       "transaksi POC hilang seluruhnya")
    ok(db.bank_accounts.count_documents({"$or": [{"id": GROUP_ACC},
                                                 {"migrated_from": GROUP_ACC}]}) == 0,
       "rekening grup POC & cerminnya hilang seluruhnya")
    ok(db.cash_transactions.count_documents({"entity_id": {"$in": ["all", "", None]}}) == sisa_awal,
       "jumlah transaksi tingkat grup kembali seperti sebelum POC", f"{sisa_awal}")

    print(f"\n{B}{'=' * 78}{X}")
    print(f"  HASIL: {G}{PASS} PASS{X} · {R}{FAIL} FAIL{X} dari {PASS + FAIL} pemeriksaan")
    print(f"{B}{'=' * 78}{X}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
