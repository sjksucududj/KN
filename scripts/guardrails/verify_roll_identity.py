#!/usr/bin/env python3
"""INV-ROLL-01 — IDENTITAS ROLL: setiap roll punya NOMOR SENDIRI & satuannya.

KELAS BUG YANG DICEGAH (semua terukur pada data demo 2026-08-18, 59 roll)
========================================================================
Nomor roll (`roll_no`) adalah identitas kain di dunia nyata: ia dicetak di label,
dipindai di rak, dicari di layar, dan dipakai mencocokkan fisik ↔ sistem. Ternyata
nomor itu dibuat di SEMBILAN tempat dengan EMPAT cara berbeda dan tak pernah dijaga:

1. **NAMA FIELD MELENCENG** (`KN-ROLL-NO-DRIFT`). `services/return_service.py`
   menulis nomor ke `roll_number`, sementara enam pembuat lain dan SELURUH
   konsumennya memakai `roll_no` (Daftar Roll, Buku Besar Persediaan, pencarian
   `build_search(["roll_no", …])`, ekspor CSV, label, pegging, potong-roll).
   Akibatnya **setiap roll hasil retur pelanggan tampil TANPA nomor** dan tak bisa
   dicari. Terukur: 1 dari 59 roll kosong nomor + kosong satuan.
   Drift-nya bertahan lama justru karena field yang salah **punya pembacanya
   sendiri**: `ReturnQuarantinePanel.jsx` membaca `r.roll_number`, dan dua service
   menulis `roll_no or roll_number` sebagai kompensasi — jadi satu layar tampak
   benar sementara layar lain kosong. Tidak ada error, tidak ada uji yang gagal.

2. **NOMOR KEMBAR.** Tiga cara penomoran bisa memberi nomor SAMA ke kain BERBEDA:
   `generate_rolls_from_balances` memakai penghitung LOKAL (`seq={"n":0}`, selalu
   mulai `RL-00001` tiap pemanggilan) · penerimaan gudang memakai
   `count_documents({})+1` (menabrak begitu ada roll di-consume/dihapus atau
   ber-prefix lain) · potongan roll menyalin dokumen induk (`dict(roll)`) sehingga
   MEWARISI nomor induknya. Terukur: **3 nomor dipakai 10 roll**, termasuk
   `RL-00002` yang dipegang DUA badan usaha (KSC 140 yard & Kanda 7 yard) dan
   `RL-00042` yang dipakai 4 roll. Operator yang memindai "RL-00002" tak bisa tahu
   kain mana yang ia pegang — nomor berhenti menjadi identitas, dan tak ada satu
   pun angka/galat yang memberi tahu.

LAPISAN PEMERIKSAAN
===================
KODE (statik, atas `backend/routers`, `backend/services`, `frontend/src`):
  K1 `roll_number` tidak boleh dipakai lagi (kunci dict, key objek JS, atau
     pembacaan `.roll_number`) — satu nama untuk satu hal.
  K2 setiap `inventory_rolls.insert_one/insert_many` WAJIB menyebut `roll_no`
     dalam fungsi yang sama (atau lewat pintu `insert_child_roll`), supaya pembuat
     roll BARU tidak bisa lupa memberi nomor.
  K3 nomor tidak boleh dibuat dari **hitungan dokumen**, **nilai acak**, atau
     **penghitung lokal** — hanya dari pengalokasi bersama (`next_roll_no` /
     `child_roll_no`) atau nomor yang dikirim pengguna.

DATA (bila MongoDB terjangkau):
  D1 tiap roll punya `roll_no` tak kosong · D2 tiap roll punya `unit` tak kosong
  D3 tak ada dokumen yang masih menyimpan `roll_number`
  D4 tak ada nomor kembar (satu nomor = satu roll)

CATATAN DETEKTOR (pelajaran §P7 dipakai TERBALIK di sini)
========================================================
§P7 menyimpulkan "konstruksi KODE dinilai dari sumber TERSTRIP". Untuk penjaga ini
justru tidak boleh: kunci dict Python (`"roll_number": …`) HIDUP di dalam literal
string, jadi mengupas string akan membuat penjaga ini buta pada bug utamanya.
Yang harus diupas di sini hanya **komentar & docstring** — kalau tidak, komentar
yang MENJELASKAN bug lama (ada di `return_service.py` & skrip migrasi) akan
dituduh sebagai bug itu sendiri. Keduanya menjadi kasus self-test permanen.

    python scripts/guardrails/verify_roll_identity.py
    python scripts/guardrails/verify_roll_identity.py --self-test
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BACKEND, FRONTEND, G, R, Y, C, B, X  # noqa: E402

SCAN_DIRS = [BACKEND / "routers", BACKEND / "services", FRONTEND / "src"]
SUFFIXES = {".py", ".js", ".jsx"}
# Skrip seed di AKAR ikut diperiksa: ia membuat roll berbentuk produksi, dan justru
# di sanalah pembuat roll ke-10 bersembunyi — `seed_qc_quarantine_examples()` memakai
# `count_documents({})+1` sehingga nomornya menabrak pengalokasi atomik (terukur
# RL-00043 dipakai 2 roll pada seed pertama sesudah perbaikan). Cakupan yang hanya
# `backend/` + `frontend/` akan HIJAU sementara data demo tetap rusak.
SCAN_FILES = sorted((BACKEND.parent).glob("seed_*.py"))

# Berkas yang SAH menyebut nama lama (mereka justru yang memperbaikinya).
ALLOW_FILES = {"verify_roll_identity.py", "migrate_roll_no_canonical.py"}

DRIFT_RE = re.compile(r"""["']roll_number["']\s*:|\.roll_number\b|\broll_number\s*:""")
INSERT_RE = re.compile(r"\binventory_rolls\.insert_(?:one|many)\s*\(")
DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+\w+")
ROLL_NO_ASSIGN_RE = re.compile(r"""["']roll_no["']\s*:\s*([^,\n]+)""")
FORBIDDEN_PRODUCERS = (
    ("count_documents", "hitungan dokumen (menabrak begitu ada roll dihapus/di-consume)"),
    ("new_id(", "nilai acak (tidak berurutan & tak bisa ditebak operator)"),
)
LOCAL_SEQ_RE = re.compile(r"""["']roll_no["']\s*:\s*f?["'][^"']*\{\s*(?!await)(?:seq|roll_seq|i|n|idx)\b""")


def strip_comments_only(src: str, py: bool) -> str:
    """Buang KOMENTAR & docstring, TAPI PERTAHANKAN literal string biasa.

    Kunci dict (`"roll_number": …`) adalah literal string, jadi ia harus tetap ada
    agar bisa dinilai; sedangkan komentar yang MENJELASKAN bug lama tidak boleh
    dituduh sebagai bug. Panjang baris dipertahankan supaya nomor baris tetap tepat.
    """
    out: List[str] = []
    i, n = 0, len(src)
    while i < n:
        c, nxt = src[i], (src[i + 1] if i + 1 < n else "")
        two, three = src[i:i + 2], src[i:i + 3]
        if py and c == "#":
            while i < n and src[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if not py and two == "//":
            while i < n and src[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if not py and two == "/*":
            while i < n and src[i:i + 2] != "*/":
                out.append("\n" if src[i] == "\n" else " ")
                i += 1
            out.append("  ")
            i += 2
            continue
        if py and three in ('"""', "'''"):
            q = three
            out.append("   ")
            i += 3
            while i < n and src[i:i + 3] != q:
                out.append("\n" if src[i] == "\n" else " ")
                i += 1
            out.append("   ")
            i += 3
            continue
        if c in ("'", '"', "`"):
            q = c
            out.append(c)
            i += 1
            while i < n:
                if src[i] == "\\":
                    out.append(src[i:i + 2])
                    i += 2
                    continue
                out.append(src[i])
                if src[i] == q:
                    i += 1
                    break
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def scan_source(src: str, rel: str) -> List[Tuple[int, str, str]]:
    """→ [(baris, pesan, potongan kode)] pelanggaran K1..K3 pada satu berkas."""
    py = rel.endswith(".py")
    code = strip_comments_only(src, py)
    lines = code.split("\n")
    raw_lines = src.split("\n")
    found: List[Tuple[int, str, str]] = []

    for idx, ln in enumerate(lines, start=1):
        # K1 — nama field yang melenceng.
        if DRIFT_RE.search(ln):
            found.append((idx, "K1 memakai `roll_number` — nama kanonik nomor roll "
                               "adalah `roll_no` (dipakai semua layar, CSV & pencarian)",
                          raw_lines[idx - 1].strip()))
        # K3 — nomor dibuat dari sumber yang tidak boleh.
        m = ROLL_NO_ASSIGN_RE.search(ln)
        if m:
            rhs = m.group(1)
            for token, why in FORBIDDEN_PRODUCERS:
                if token in rhs:
                    found.append((idx, f"K3 nomor roll dibuat dari {why}; pakai "
                                       f"`next_roll_no()` / `child_roll_no()`",
                                  raw_lines[idx - 1].strip()))
        if LOCAL_SEQ_RE.search(ln):
            found.append((idx, "K3 nomor roll dari penghitung LOKAL (selalu mulai dari 1 "
                               "tiap pemanggilan → menabrak nomor yang sudah ada); pakai "
                               "`next_roll_no()`",
                          raw_lines[idx - 1].strip()))

    # K2 — setiap penyimpanan roll harus menyebut `roll_no` di fungsi yang sama.
    for idx, ln in enumerate(lines, start=1):
        if not INSERT_RE.search(ln):
            continue
        start = 0
        for back in range(idx - 1, -1, -1):
            if DEF_RE.match(lines[back]):
                start = back
                break
        window = "\n".join(lines[start:idx])
        if "roll_no" not in window and "insert_child_roll" not in window:
            found.append((idx, "K2 menyimpan roll TANPA menyebut `roll_no` di fungsi ini "
                               "— pembuat roll baru wajib memberi nomor (atau lewat "
                               "`insert_child_roll()`)", raw_lines[idx - 1].strip()))
    return found


def files_to_scan() -> List[Path]:
    out: List[Path] = [f for f in SCAN_FILES if f.is_file()]
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if (p.suffix in SUFFIXES and p.is_file()
                    and p.name not in ALLOW_FILES
                    and "node_modules" not in str(p)
                    and not p.name.startswith("test_")
                    and not p.name.endswith("_test.py")):
                out.append(p)
    return out


def check_data() -> Tuple[List[str], int, bool]:
    """Lapisan DATA (D1..D4). → (pelanggaran, jumlah_roll, mongo_terjangkau)."""
    try:
        if not os.environ.get("MONGO_URL"):
            # Kenyamanan saat dijalankan tangan (gate.sh sendiri sudah meng-export-nya).
            from dotenv import load_dotenv
            load_dotenv(BACKEND / ".env")
        from pymongo import MongoClient
        cli = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=2500)
        db = cli[os.environ.get("DB_NAME", "test_database")]
        db.command("ping")
    except Exception:  # noqa: BLE001
        return [], 0, False

    viol: List[str] = []
    coll = db.inventory_rolls
    total = coll.count_documents({})
    missing_no = list(coll.find(
        {"$or": [{"roll_no": {"$in": [None, ""]}}, {"roll_no": {"$exists": False}}]},
        {"_id": 0, "id": 1, "origin_type": 1}).limit(10))
    if missing_no:
        viol.append(f"D1 {len(missing_no)}+ roll TANPA `roll_no` "
                    f"(mis. {', '.join(str(d.get('id')) for d in missing_no[:5])}) — "
                    f"tampil kosong di layar & CSV, tak bisa dicari")
    missing_unit = list(coll.find(
        {"$or": [{"unit": {"$in": [None, ""]}}, {"unit": {"$exists": False}}]},
        {"_id": 0, "id": 1}).limit(10))
    if missing_unit:
        viol.append(f"D2 {len(missing_unit)}+ roll TANPA `unit` "
                    f"(mis. {', '.join(str(d.get('id')) for d in missing_unit[:5])})")
    legacy = coll.count_documents({"roll_number": {"$exists": True}})
    if legacy:
        viol.append(f"D3 {legacy} roll masih menyimpan field lama `roll_number` — "
                    f"jalankan `python scripts/migrate_roll_no_canonical.py`")
    dups = list(coll.aggregate([
        {"$group": {"_id": "$roll_no", "n": {"$sum": 1}, "ids": {"$push": "$id"}}},
        {"$match": {"n": {"$gt": 1}}}, {"$sort": {"n": -1}}, {"$limit": 10}]))
    if dups:
        detail = "; ".join(f"{d['_id']}×{d['n']}" for d in dups[:5])
        viol.append(f"D4 {len(dups)} nomor dipakai lebih dari satu roll ({detail}) — "
                    f"nomor pada label berhenti menjadi identitas")
    return viol, total, True


def self_test() -> int:
    """Bukti-merah + anti tuduh palsu (kedua arah wajib)."""
    print(f"{C}{B}== SELF-TEST INV-ROLL-01 (penjaga harus bisa MEMERAH) =={X}")
    bad = 0

    merah = [
        ('"roll_number": f"RTN-{ret[\'number\'][-5:]}-{product_id[-4:]}",\n', "probe.py",
         "K1", "nama field melenceng (`roll_number`) di dict Python"),
        ('<td>{r.roll_number}</td>\n', "probe.jsx",
         "K1", "layar membaca `.roll_number`"),
        ('async def make(self):\n    doc = {"id": new_id("roll"), "length": 5}\n'
         '    await db.inventory_rolls.insert_one(doc)\n', "probe.py",
         "K2", "menyimpan roll tanpa nomor"),
        ('async def rcv(self):\n    seq = await db.inventory_rolls.count_documents({})\n'
         '    doc = {"roll_no": f"RL-{count_documents(x):05d}"}\n'
         '    await db.inventory_rolls.insert_one(doc)\n', "probe.py",
         "K3", "nomor dari hitungan dokumen"),
        ('async def mk(self):\n    doc = {"roll_no": f"RL-{new_id(\'r\')[-6:].upper()}"}\n'
         '    await db.inventory_rolls.insert_one(doc)\n', "probe.py",
         "K3", "nomor dari nilai acak"),
        ('def _make_roll(self):\n    return {"roll_no": f"RL-{seq[\'n\']:05d}"}\n', "probe.py",
         "K3", "nomor dari penghitung lokal"),
    ]
    for src, rel, tag, apa in merah:
        got = scan_source(src, rel)
        if not any(m.startswith(tag) for _, m, _ in got):
            print(f"  {R}[FAIL]{X} SELF-TEST {tag}: TIDAK menangkap — {apa}")
            bad += 1
        else:
            print(f"  {G}[PASS]{X} {tag} tertangkap — {apa}")

    aman = [
        ('# Baris ini dulu menulis "roll_number": nama yang salah. Sekarang `roll_no`.\n'
         'x = 1\n', "probe.py", "komentar Python yang MENJELASKAN bug lama"),
        ('"""Dulu `roll_number`; kini `roll_no`."""\nx = 1\n', "probe.py",
         "docstring yang menyebut nama lama"),
        ('// dulu membaca r.roll_number — sekarang r.roll_no\nconst a = r.roll_no;\n',
         "probe.jsx", "komentar JS yang menyebut nama lama"),
        ('async def cut(self):\n    child = dict(roll)\n'
         '    child = await insert_child_roll(child, roll)\n', "probe.py",
         "potongan roll lewat pintu `insert_child_roll`"),
        ('async def mk(self):\n    doc = {"roll_no": await next_roll_no()}\n'
         '    await db.inventory_rolls.insert_one(doc)\n', "probe.py",
         "nomor dari pengalokasi bersama"),
        ('async def mk(self):\n    doc = {"roll_no": payload.roll_no or await next_roll_no()}\n'
         '    await db.inventory_rolls.insert_one(doc)\n', "probe.py",
         "nomor dari pengguna dengan cadangan pengalokasi"),
        ('const label = r.roll_no || r.id;\n', "probe.jsx", "membaca nomor kanonik"),
        ('async def rd(self):\n    r = await db.inventory_rolls.find_one({"roll_no": no})\n',
         "probe.py", "MEMBACA roll (bukan menyimpan)"),
    ]
    for src, rel, apa in aman:
        got = scan_source(src, rel)
        if got:
            print(f"  {R}[FAIL]{X} SELF-TEST: menuduh palsu — {apa}: {got[0][1]}")
            bad += 1
        else:
            print(f"  {G}[PASS]{X} tidak menuduh — {apa}")

    if bad:
        print(f"\n  {R}{B}✗ SELF-TEST GAGAL ({bad}) — penjaga tak boleh dipakai menilai.{X}\n")
        return 1
    print(f"\n  {G}{B}✓ SELF-TEST: {len(merah)} pelanggaran tertangkap & "
          f"{len(aman)} kasus sah tidak dituduh.{X}\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test and self_test() != 0:
        return 1

    print(f"{C}{B}== INV-ROLL-01 — identitas roll (nomor sendiri & satuan) =={X}")
    findings: List[Tuple[str, int, str, str]] = []
    files = files_to_scan()
    for p in files:
        rel = str(p.relative_to(BACKEND.parent))
        for ln, msg, code in scan_source(p.read_text(encoding="utf-8", errors="ignore"), rel):
            findings.append((rel, ln, msg, code))

    data_viol, total, mongo_ok = check_data()
    print(f"  berkas kode diperiksa: {len(files)}  ·  "
          + (f"roll di basis data: {total}" if mongo_ok
             else f"{Y}basis data tak terjangkau — lapisan DATA dilewati{X}"))

    if not findings and not data_viol:
        print(f"\n  {G}{B}✓ 0 pelanggaran — satu nama (`roll_no`), satu pengalokasi, "
              f"satu nomor per roll.{X}\n")
        return 0

    print(f"\n  {R}{B}✗ {len(findings) + len(data_viol)} pelanggaran:{X}")
    for rel, ln, msg, code in findings:
        print(f"    {R}✗{X} {rel}:{ln} — {msg}")
        print(f"        {Y}{code}{X}")
    for v in data_viol:
        print(f"    {R}✗{X} [DATA] {v}")
    print(f"\n  {Y}→ Nomor roll HANYA dari `roll_service.next_roll_no()` "
          f"(roll baru) atau `insert_child_roll()` (potongan). "
          f"Data lama: `python scripts/migrate_roll_no_canonical.py`.{X}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
