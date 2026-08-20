#!/usr/bin/env python3
"""fix_i18n_id.py — CODEMOD: terjemahkan label antarmuka ke Bahasa Indonesia.

Kenapa codemod dan bukan cari-ganti biasa
-----------------------------------------
`sed`/replace-all berbahaya di repo ini: kata seperti `available`, `draft`,
`pending` juga hidup sebagai **nilai status di backend**, **kunci objek**,
**data-testid**, dan **className**. Mengganti semuanya = merusak logika.

Codemod ini memakai **pemindai yang sama** dengan `audit_i18n_id.py`, sehingga
hanya rentang teks yang BENAR-BENAR dilihat pengguna yang diubah:
teks JSX antar-tag · nilai prop teks (`label=` / `placeholder=` / `title:` …) ·
string sebagai anak JSX (`{"…"}`). Di luar rentang itu, berkas tidak disentuh.

Tabel terjemahan = `scripts/i18n_table_id.py` (data terpisah, mudah di-review).

Pakai:
    python scripts/fix_i18n_id.py            # pratinjau (tidak menulis)
    python scripts/fix_i18n_id.py --apply    # tulis perubahan
    python scripts/fix_i18n_id.py --self-test  # bukti-merah: codemod tidak boleh
                                               # menyentuh kunci/testid/className
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from i18n_table_id import TABEL  # noqa: E402

_spec = importlib.util.spec_from_file_location("aud", ROOT / "scripts" / "audit_i18n_id.py")
_aud = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_aud)

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; B = "\033[1m"; X = "\033[0m"


def _spans(src: str):
    """Rentang (mulai, akhir, teks) untuk setiap string yang dilihat pengguna.

    Memakai regex yang SAMA dengan audit agar tidak ada celah antara "yang
    diperiksa" dan "yang diubah" — celah itulah yang membuat sapuan bahasa
    sebelumnya selalu kembali berbahasa Inggris.
    """
    out = []
    for rx, grup in ((_aud.RE_PROP, None), (_aud.RE_JSX, 1), (_aud.RE_BRACE, 1),
                     (_aud.RE_JSX_PRE, 1), (_aud.RE_JSX_POST, 1)):
        for m in rx.finditer(src):
            if grup is None:
                idx = next((i for i in (3, 4, 5) if m.group(i) is not None), None)
                if idx is None:
                    continue
            else:
                idx = grup
            teks = m.group(idx)
            if not teks:
                continue
            out.append((m.start(idx), m.end(idx), teks))
    # urut menurun agar penggantian tidak menggeser offset berikutnya
    out.sort(key=lambda t: -t[0])
    return out


def proses_sumber(src: str):
    """Kembalikan (sumber_baru, daftar_perubahan)."""
    ubah = []
    for mulai, akhir, teks in _spans(src):
        if "${" in teks:
            # Template literal: terjemahkan tiap potongan teks di antara `${...}`
            # TANPA menyentuh isi interpolasinya (itu kode).
            bagian = re.split(r"(\$\{[^{}]*\})", teks)
            berubah = False
            for i, bag in enumerate(bagian):
                if bag.startswith("${"):
                    continue
                inti = bag.strip()
                baru = TABEL.get(inti)
                if not baru or baru == inti:
                    continue
                depan = bag[: len(bag) - len(bag.lstrip())]
                belakang = bag[len(bag.rstrip()):]
                bagian[i] = depan + baru + belakang
                ubah.append((inti, baru))
                berubah = True
            if berubah:
                src = src[:mulai] + "".join(bagian) + src[akhir:]
            continue
        inti = teks.strip()
        baru = TABEL.get(inti)
        if not baru or baru == inti:
            continue
        # pertahankan spasi/indent asli di dalam rentang
        depan = teks[: len(teks) - len(teks.lstrip())]
        belakang = teks[len(teks.rstrip()):]
        src = src[:mulai] + depan + baru + belakang + src[akhir:]
        ubah.append((inti, baru))
    return src, ubah


def jalankan(base: Path, apply: bool):
    total, per_file = 0, {}
    for root, _dirs, files in os.walk(base):
        rel = os.path.relpath(root, base).replace(os.sep, "/")
        if any(s in rel for s in _aud.LEWATI_DIR):
            continue
        for f in sorted(files):
            if not f.endswith((".jsx", ".js")) or f in _aud.LEWATI_FILE:
                continue
            p = Path(root) / f
            src = p.read_text(encoding="utf-8")
            baru, ubah = proses_sumber(src)
            if not ubah:
                continue
            per_file[str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)] = ubah
            total += len(ubah)
            if apply:
                p.write_text(baru, encoding="utf-8")
    return total, per_file


def _spans_py(src: str):
    """Rentang string teks antarmuka di berkas Python backend (label/pesan)."""
    out = []
    for m in _aud.RE_PY_TEKS.finditer(src):
        idx = 2 if m.group(2) is not None else 3
        out.append((m.start(idx), m.end(idx), m.group(idx)))
    out.sort(key=lambda t: -t[0])
    return out


def proses_backend(src: str):
    ubah = []
    for mulai, akhir, teks in _spans_py(src):
        inti = teks.strip()
        baru = TABEL.get(inti)
        if not baru or baru == inti:
            continue
        src = src[:mulai] + baru + src[akhir:]
        ubah.append((inti, baru))
    return src, ubah


def jalankan_backend(base: Path, apply: bool):
    """Teks yang DIKIRIM backend ke antarmuka (mis. langkah onboarding)."""
    total, per_file = 0, {}
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _aud.BE_LEWATI_DIR]
        for f in sorted(files):
            if not f.endswith(".py") or any(s in f for s in _aud.BE_LEWATI):
                continue
            p = Path(root) / f
            src = p.read_text(encoding="utf-8")
            baru, ubah = proses_backend(src)
            if not ubah:
                continue
            per_file[str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)] = ubah
            total += len(ubah)
            if apply:
                p.write_text(baru, encoding="utf-8")
    return total, per_file


def self_test() -> int:
    """BUKTI-MERAH: codemod HANYA boleh menyentuh teks yang dilihat pengguna."""
    print(f"{C}{B}== SELF-TEST fix_i18n_id (codemod tidak boleh merusak kode) =={X}")
    kasus = [
        ("teks JSX diterjemahkan",
         '<span>Available</span>', '<span>Tersedia</span>'),
        ("prop label diterjemahkan",
         'const a = { label: "Picked" };', 'const a = { label: "Sudah Diambil" };'),
        ("kunci objek TIDAK diubah",
         'const m = { Available: 1, draft: 2 };', 'const m = { Available: 1, draft: 2 };'),
        ("data-testid TIDAK diubah",
         '<i data-testid="stock-Available" />', '<i data-testid="stock-Available" />'),
        ("className TIDAK diubah",
         '<div className="Available Draft" />', '<div className="Available Draft" />'),
        ("nilai status backend TIDAK diubah",
         'if (so.status === "Draft") return;', 'if (so.status === "Draft") return;'),
        ("import path TIDAK diubah",
         'import X from "./Draft";', 'import X from "./Draft";'),
        ("teks yang sudah Indonesia dibiarkan",
         '<b>Tersedia</b>', '<b>Tersedia</b>'),
    ]
    ok = 0
    for nama, masuk, harus in kasus:
        keluar, _ = proses_sumber(masuk)
        lolos = keluar == harus
        ok += lolos
        tag = f"{G}PASS{X}" if lolos else f"{R}FAIL{X}"
        print(f"  [{tag}] {nama}")
        if not lolos:
            print(f"          harus : {harus}\n          hasil : {keluar}")
    # Backend: hanya nilai kunci teks yang boleh berubah, bukan kunci/enum.
    kasus_py = [
        ("BE: nilai 'label' diterjemahkan",
         '{"id": "x", "label": "Confirmed"}', '{"id": "x", "label": "Terkonfirmasi"}'),
        ("BE: nilai 'id'/enum TIDAK diubah",
         '{"id": "Confirmed", "status": "Confirmed"}', '{"id": "Confirmed", "status": "Confirmed"}'),
        ("BE: nama variabel TIDAK diubah",
         'Confirmed = 1  # label: bukan string', 'Confirmed = 1  # label: bukan string'),
    ]
    for nama, masuk, harus in kasus_py:
        keluar, _ = proses_backend(masuk)
        lolos = keluar == harus
        ok += lolos
        tag = f"{G}PASS{X}" if lolos else f"{R}FAIL{X}"
        print(f"  [{tag}] {nama}")
        if not lolos:
            print(f"          harus : {harus}\n          hasil : {keluar}")
    total_kasus = len(kasus) + len(kasus_py)
    print(f"\n  {ok}/{total_kasus} skenario lulus.")
    if ok != total_kasus:
        print(f"  {R}{B}✗ SELF-TEST GAGAL — codemod tidak aman dipakai.{X}\n")
        return 1
    print(f"  {G}{B}✓ SELF-TEST HIJAU — codemod hanya menyentuh teks pengguna.{X}\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Codemod label antarmuka → Bahasa Indonesia.")
    ap.add_argument("--apply", action="store_true", help="tulis perubahan ke berkas")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    total, per_file = jalankan(_aud.FE_SRC, a.apply)
    tb, pb = jalankan_backend(_aud.BE_SRC, a.apply)
    total += tb
    per_file.update(pb)
    mode = "DITERAPKAN" if a.apply else "PRATINJAU (tidak ditulis)"
    print(f"{C}{B}CODEMOD BAHASA — {mode}{X}")
    if not a.quiet:
        for f in sorted(per_file):
            print(f"  {Y}{f}{X}")
            for lama, baru in per_file[f]:
                print(f"     “{lama[:46]}” → {G}“{baru[:46]}”{X}")
    print(f"\n  {total} penggantian di {len(per_file)} berkas.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
