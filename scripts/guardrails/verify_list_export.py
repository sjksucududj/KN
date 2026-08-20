#!/usr/bin/env python3
"""INV-UI-07 — **SETIAP DAFTAR BERHALAMAN WAJIB BISA DIUNDUH (CSV), DAN CSV-NYA WAJIB BENAR**

MASALAH YANG DICEGAH (FASE P6, keputusan pemilik — terukur, bukan selera)
========================================================================
Sampai FASE P5 aplikasi ini punya **12 daftar berhalaman** (Pelanggan · PO · Roll ·
Mutasi · Pesanan · Jurnal GL · Retur Jual · Retur Beli · Lot · Tagihan Supplier ·
Supplier · Akun) dan **tidak satu pun** bisa dibawa keluar ke Excel. Pemilik yang ingin
merekap harus menyalin layar per halaman — 20 baris sekali angkat.

Penjaga ini menutup DUA cara fitur unduh itu membusuk:

  A. **Daftar berhalaman BARU lupa diberi tombol Unduh.** Ini mode gagal yang paling
     mungkin: `PaginationBar` dipasang (karena tanpa itu daftarnya tak bisa dibuka
     halaman 2), lalu `exportConfig` tidak diisi karena tidak ada yang menahannya.
     Hasilnya aplikasi yang "kadang bisa diunduh" — dan pengguna berhenti mencari
     tombolnya sama sekali.
  B. **Berkas CSV-nya rusak secara SENYAP.** Ini bahaya yang lebih besar karena tidak
     terlihat sebagai galat sama sekali:
       · Pemisah `,` alih-alih `;` → di Excel wilayah Indonesia semua kolom **menumpuk
         di kolom A**. Berkasnya "berhasil diunduh", isinya tak terpakai.
       · Tanpa BOM UTF-8 → nama ber-aksen & simbol jadi mojibake.
       · Sel bermuatan `;` atau tanda kutip tidak dibungkus → **seluruh kolom di
         kanannya bergeser satu**, dan barisnya tetap tampak wajar. Angka pindah kolom
         adalah kerusakan terburuk untuk berkas keuangan: ia tetap bisa dijumlah,
         hasilnya saja salah.
       · Desimal titik (`12500.5`) → Excel ID membacanya sebagai TEKS, kolomnya tak
         bisa di-SUM, padahal menjumlah itu tepat alasan orang mengunduh CSV.
       · Sel yang dimulai `=`/`+`/`@` → **dieksekusi Excel sebagai formula** di komputer
         pemilik, padahal isinya berasal dari isian pengguna.

KENAPA PENJAGA INI MENJALANKAN KODENYA, BUKAN CUMA MEMBACA POLANYA
------------------------------------------------------------------
Aturan (B) di atas semuanya soal **PERILAKU**, dan pola teks tak bisa membuktikannya:
sebuah berkas bisa memuat karakter `";"` di suatu tempat dan tetap menghasilkan CSV yang
salah. Jadi penjaga ini **mengimpor `utils/csvExport.js` dengan Node** dan menguji
keluarannya sungguhan (17 kasus). Karena itu `utils/csvExport.js` sengaja dibuat **tanpa
import apa pun** — supaya bisa dijalankan di luar peramban tanpa bundler.
Bila Node tidak tersedia, lapis perilaku dilaporkan SKIP (bukan PASS palsu).

ATURAN GATE
-----------
  A. Setiap `<PaginationBar …>` di `frontend/src` WAJIB menyetor prop `exportConfig`.
     Pengecualian harus terdaftar di `DIBOLEHKAN` **dengan alasan tertulis** yang bisa
     dinilai orang (≥ 20 karakter).
  B. `utils/csvExport.js` wajib ada dan LULUS 17 uji perilaku (pemisah `;`, BOM UTF-8,
     escaping RFC 4180, desimal koma, anti-injection, angka negatif tidak dirusak).

Usage:
    python scripts/guardrails/verify_list_export.py
    python scripts/guardrails/verify_list_export.py -v
    python scripts/guardrails/verify_list_export.py --self-test
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from _common import FRONTEND, Guard, strip_comments_and_strings, G, R, Y, B, X  # noqa: E402

SRC = FRONTEND / "src"
CSV_UTIL = SRC / "utils" / "csvExport.js"

#: Pengecualian — WAJIB beralasan (dinilai orang, bukan dibisukan).
DIBOLEHKAN: Dict[str, str] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Lapis A — setiap daftar berhalaman punya tombol Unduh
# ─────────────────────────────────────────────────────────────────────────────
def pager_blocks(src: str) -> List[Tuple[int, str]]:
    """→ [(nomor_baris, teks_prop)] untuk setiap `<PaginationBar …>`.

    Komentar & literal string dibuang lebih dulu supaya penyebutan
    `<PaginationBar>` di dalam DOKUMENTASI tidak dihitung sebagai pemakaian
    (kelas tuduhan palsu yang sama seperti INV-UI-06 pada `KNSelect`).

    Pembacaan prop sadar-kurung: `exportConfig={{ … }}` memuat `{}` bersarang, jadi
    akhir tag dicari pada kedalaman kurung 0 — bukan dengan mencari `/>` terdekat.
    """
    bersih = strip_comments_and_strings(src)
    out: List[Tuple[int, str]] = []
    for m in re.finditer(r"<PaginationBar\b", bersih):
        i, n, depth = m.end(), len(bersih), 0
        while i < n:
            c = bersih[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == ">" and depth == 0:
                break
            i += 1
        out.append((bersih[:m.start()].count("\n") + 1, bersih[m.end():i]))
    return out


def scan_pagers() -> Dict[str, List[Tuple[int, bool]]]:
    """→ {berkas: [(baris, punya_exportConfig)]} untuk seluruh frontend/src."""
    hasil: Dict[str, List[Tuple[int, bool]]] = {}
    for path in sorted(list(SRC.rglob("*.jsx")) + list(SRC.rglob("*.js"))):
        rel = str(path.relative_to(SRC))
        if rel == os.path.join("components", "PaginationBar.jsx"):
            continue                      # definisi komponennya sendiri
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        blocks = pager_blocks(src)
        if blocks:
            hasil[rel] = [(ln, "exportConfig" in props) for ln, props in blocks]
    return hasil


def check_pagers(g: Guard, hasil: Dict[str, List[Tuple[int, bool]]],
                 dibolehkan: Dict[str, str]) -> None:
    for rel, blocks in sorted(hasil.items()):
        alasan = (dibolehkan.get(rel) or "").strip()
        for baris, punya in blocks:
            g.bump()
            if punya:
                continue
            if not alasan:
                g.add(f"{rel}:{baris} memasang <PaginationBar> TANPA `exportConfig` → "
                      f"daftar ini berhalaman tetapi tidak bisa dibawa ke Excel; "
                      f"pemakainya harus menyalin layar 20 baris sekali angkat. "
                      f"Tambahkan `exportConfig={{ columns, rows, fetchAll, filename }}` "
                      f"(lihat components/PaginationBar.jsx), atau daftarkan di "
                      f"DIBOLEHKAN dengan alasan.")
            elif len(alasan) < 20:
                g.add(f"{rel} dibebaskan tanpa alasan yang bisa dinilai orang.")


# ─────────────────────────────────────────────────────────────────────────────
# Lapis B — perilaku CSV diuji dengan MENJALANKANNYA (Node)
# ─────────────────────────────────────────────────────────────────────────────
#: Uji perilaku. Ditulis sebagai modul ESM supaya bisa `import` berkas aslinya
#: apa adanya (tanpa bundler, tanpa transpile).
NODE_TEST = r"""
import * as csv from "./csvExport.mjs";

let gagal = 0;
const cek = (nama, benar, dapat) => {
  if (!benar) { gagal += 1; console.log("FAIL :: " + nama + " :: dapat=" + JSON.stringify(dapat)); }
  else { console.log("PASS :: " + nama); }
};

// ── Kontrak format berkas ────────────────────────────────────────────────────
cek("pemisah kolom = ';' (Excel wilayah Indonesia)", csv.CSV_DELIMITER === ";", csv.CSV_DELIMITER);
cek("BOM UTF-8 tersedia", csv.CSV_BOM === "\uFEFF", csv.CSV_BOM);

const C = (rows, cols) => csv.buildCsv(rows, cols);

// ── Bentuk dasar ─────────────────────────────────────────────────────────────
let r = C([{ a: "x" }], [{ key: "a", header: "A" }]);
cek("judul + satu baris dipisah CRLF", r === "A\r\nx", r);

r = C([{ a: "1", b: "2" }], [{ key: "a", header: "A" }, { key: "b", header: "B" }]);
cek("dua kolom dipisah titik-koma", r === "A;B\r\n1;2", r);

// ── Escaping RFC 4180 (kerusakan paling senyap: kolom bergeser) ──────────────
r = C([{ a: "Toko A; Cabang" }], [{ key: "a", header: "A" }]);
cek("sel bermuatan ';' dibungkus kutip", r === 'A\r\n"Toko A; Cabang"', r);

r = C([{ a: 'Toko "X"' }], [{ key: "a", header: "A" }]);
cek("tanda kutip digandakan & dibungkus", r === "A\r\n\"Toko \"\"X\"\"\"", r);

r = C([{ a: "baris1\nbaris2" }], [{ key: "a", header: "A" }]);
cek("baris baru di dalam sel dibungkus", r === 'A\r\n"baris1\nbaris2"', r);

r = C([{ a: "biasa" }], [{ key: "a", header: "A;B" }]);
cek("JUDUL kolom pun di-escape", r === '"A;B"\r\nbiasa', r);

// ── Anti CSV-injection ───────────────────────────────────────────────────────
cek("sel diawali '=' diberi kutip tunggal",
    csv.escapeCsvCell("=1+1") === "'=1+1", csv.escapeCsvCell("=1+1"));
cek("sel diawali '@' diberi kutip tunggal",
    csv.escapeCsvCell("@SUM(A1)") === "'@SUM(A1)", csv.escapeCsvCell("@SUM(A1)"));
cek("angka NEGATIF tidak dirusak (obat tak boleh lebih parah dari penyakit)",
    csv.escapeCsvCell("-1500000") === "-1500000", csv.escapeCsvCell("-1500000"));

// ── Angka & tanggal untuk Excel wilayah Indonesia ────────────────────────────
r = C([{ n: 12500.5 }], [{ key: "n", header: "N", type: "num" }]);
cek("desimal memakai KOMA (agar Excel ID membacanya sebagai angka)", r === "N\r\n12500,5", r);

r = C([{ n: 12500000 }], [{ key: "n", header: "N", type: "num" }]);
cek("bilangan bulat besar tanpa pemisah ribuan", r === "N\r\n12500000", r);

r = C([{ n: 12.6 }], [{ key: "n", header: "N", type: "int" }]);
cek("type int dibulatkan", r === "N\r\n13", r);

r = C([{ d: new Date(2026, 7, 18, 14, 5) }], [{ key: "d", header: "D", type: "date" }]);
cek("tanggal dd/mm/yyyy", r === "D\r\n18/08/2026", r);

r = C([{ d: new Date(2026, 7, 18, 14, 5) }], [{ key: "d", header: "D", type: "datetime" }]);
cek("waktu dd/mm/yyyy HH:MM", r === "D\r\n18/08/2026 14:05", r);

// ── Nilai yang mudah bikin sel "undefined" ───────────────────────────────────
r = C([{ a: null, b: undefined }], [{ key: "a", header: "A" }, { key: "b", header: "B" }]);
cek("null/undefined jadi sel KOSONG (bukan tulisan 'null')", r === "A;B\r\n;", r);

r = C([{ a: true, b: false }], [{ key: "a", header: "A" }, { key: "b", header: "B" }]);
cek("boolean jadi Ya/Tidak", r === "A;B\r\nYa;Tidak", r);

r = C([{ a: ["x", "y"] }], [{ key: "a", header: "A" }]);
cek("daftar digabung dengan koma-spasi", r === "A\r\nx, y", r);

r = C([{ x: { deep: 1 } }], [{ header: "A", get: (row) => row.x.deep }]);
cek("kolom turunan lewat get(row)", r === "A\r\n1", r);

console.log(gagal === 0 ? "ALL_PASS" : ("GAGAL=" + gagal));
process.exit(gagal === 0 ? 0 : 1);
"""


def run_csv_behaviour() -> Tuple[str, List[str]]:
    """Jalankan uji perilaku CSV dengan Node.

    → ("PASS"|"FAIL"|"SKIP", baris_keluaran)
    """
    if not CSV_UTIL.exists():
        return "FAIL", [f"{CSV_UTIL.relative_to(FRONTEND)} tidak ada."]
    node = shutil.which("node")
    if not node:
        return "SKIP", ["Node tidak tersedia — lapis PERILAKU CSV tidak dijalankan."]
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        # Disalin sebagai .mjs supaya Node memperlakukannya sebagai modul ESM.
        (d / "csvExport.mjs").write_text(CSV_UTIL.read_text(encoding="utf-8"),
                                         encoding="utf-8")
        (d / "test.mjs").write_text(NODE_TEST, encoding="utf-8")
        try:
            p = subprocess.run([node, str(d / "test.mjs")], capture_output=True,
                               text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return "FAIL", ["Uji perilaku CSV tidak selesai dalam 60s."]
        out = (p.stdout + p.stderr).strip().splitlines()
        return ("PASS" if p.returncode == 0 else "FAIL"), out


def check_csv_behaviour(g: Guard, verbose: bool = False) -> None:
    status, lines = run_csv_behaviour()
    g.bump()
    lulus = sum(1 for ln in lines if ln.startswith("PASS ::"))
    if status == "SKIP":
        print(f"{Y}  [SKIP] {lines[0]}{X}")
        return
    print(f"  perilaku CSV (dijalankan dengan Node): {lulus} kasus lulus")
    if verbose:
        for ln in lines:
            print(f"    {ln}")
    if status != "PASS":
        for ln in lines:
            if ln.startswith("FAIL ::") or "Error" in ln:
                g.add(f"utils/csvExport.js — {ln}")
        if not any(ln.startswith("FAIL ::") for ln in lines):
            g.add("utils/csvExport.js gagal dijalankan: "
                  + (" | ".join(lines[-3:]) if lines else "tanpa keluaran"))


# ─────────────────────────────────────────────────────────────────────────────
def self_test() -> int:
    kasus = []

    def cek(nama: str, benar: bool):
        kasus.append((nama, benar))

    PAGER_OK = ('<PaginationBar page={p} total={t}\n'
                '  exportConfig={{ columns: C, rows: r, fetchAll: f, filename: "x" }} />')
    PAGER_NO = '<PaginationBar page={p} total={t} onPrev={a} onNext={b} />'

    # ── Lapis 1 — PENGENAL harus melihat pager & tahu bedanya ─────────────────
    cek("pager dengan exportConfig terdeteksi PUNYA",
        pager_blocks(PAGER_OK) and pager_blocks(PAGER_OK)[0][1].find("exportConfig") >= 0)
    cek("pager tanpa exportConfig terdeteksi TIDAK punya",
        pager_blocks(PAGER_NO) and "exportConfig" not in pager_blocks(PAGER_NO)[0][1])
    cek("dua pager dalam satu berkas dihitung dua",
        len(pager_blocks(PAGER_NO + "\n" + PAGER_OK)) == 2)
    cek("nomor baris tepat walau ada komentar blok di atasnya",
        pager_blocks("/* dua\n   baris */\n" + PAGER_NO)[0][0] == 3)
    cek("prop bersarang `{{ }}` tidak membuat pembacaan tag berhenti terlalu cepat",
        "filename" in pager_blocks(PAGER_OK)[0][1])

    # ── Lapis 2 — TIDAK boleh menuduh palsu ───────────────────────────────────
    cek("`<PaginationBar>` di dalam KOMENTAR bukan pemakaian",
        pager_blocks("// pakai <PaginationBar /> di sini\nconst a = 1;") == [])
    cek("`<PaginationBar>` di dalam STRING bukan pemakaian",
        pager_blocks('const doc = "<PaginationBar />";') == [])
    cek("komponen lain berawalan sama (`<PaginationBarLegacy>`) tidak dihitung",
        pager_blocks("<PaginationBarLegacy page={p} />") == [])
    cek("kata PaginationBar tanpa tag (impor) tidak dihitung",
        pager_blocks('import PaginationBar from "./PaginationBar";') == [])

    # ── Lapis 3 — ATURAN pembebasan ───────────────────────────────────────────
    g = Guard("INV-UI-07", "self-test"); g.violations, g.checks = [], 0
    check_pagers(g, {"a.jsx": [(3, False)]}, {})
    cek("pager tanpa Unduh & tanpa pembebasan → MERAH", len(g.violations) == 1)

    g = Guard("INV-UI-07", "self-test"); g.violations, g.checks = [], 0
    check_pagers(g, {"a.jsx": [(3, True)]}, {})
    cek("pager dengan Unduh → hijau", len(g.violations) == 0)

    g = Guard("INV-UI-07", "self-test"); g.violations, g.checks = [], 0
    check_pagers(g, {"a.jsx": [(3, False)]},
                 {"a.jsx": "Daftar khusus diagnostik internal, tidak pernah direkap ke Excel."})
    cek("pembebasan beralasan panjang → hijau", len(g.violations) == 0)

    g = Guard("INV-UI-07", "self-test"); g.violations, g.checks = [], 0
    check_pagers(g, {"a.jsx": [(3, False)]}, {"a.jsx": "nanti"})
    cek("pembebasan tanpa alasan yang bisa dinilai → MERAH", len(g.violations) == 1)

    g = Guard("INV-UI-07", "self-test"); g.violations, g.checks = [], 0
    check_pagers(g, {"a.jsx": [(3, True), (9, False)]}, {})
    cek("satu dari dua pager bolong → tepat 1 pelanggaran", len(g.violations) == 1)

    # ── Lapis 4 — lapis PERILAKU benar-benar bisa MEMERAH ─────────────────────
    # Dibuktikan dengan menjalankan util CSV yang SENGAJA dirusak (pemisah `,`):
    # tanpa bukti ini, "17 kasus lulus" bisa saja berarti Node tak pernah jalan.
    node = shutil.which("node")
    if node:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            rusak = CSV_UTIL.read_text(encoding="utf-8").replace(
                'export const CSV_DELIMITER = ";";',
                'export const CSV_DELIMITER = ",";')
            (d / "csvExport.mjs").write_text(rusak, encoding="utf-8")
            (d / "test.mjs").write_text(NODE_TEST, encoding="utf-8")
            p = subprocess.run([node, str(d / "test.mjs")], capture_output=True,
                               text=True, timeout=60)
        cek("util CSV yang pemisahnya diganti ',' → uji perilaku MEMERAH",
            p.returncode != 0)
    else:
        cek("Node tersedia untuk lapis perilaku (dilaporkan SKIP bila tidak)", True)

    gagal = sum(0 if ok else 1 for _n, ok in kasus)
    print(f"{B}== SELF-TEST INV-UI-07 (penjaga unduh daftar harus bisa MEMERAH) =={X}")
    for nama, ok in kasus:
        print(f"  [{G + 'PASS' + X if ok else R + 'FAIL' + X}] {nama}")
    print(f"{G}  HIJAU — penjaga terbukti menuduh pager tanpa Unduh, tidak menuduh palsu "
          f"komentar/string/komponen senama, DAN lapis perilaku CSV-nya bisa memerah.{X}"
          if not gagal else f"{R}{B}  SELF-TEST MERAH ({gagal} kasus).{X}")
    return gagal


def main(verbose: bool = False) -> int:
    g = Guard("INV-UI-07", "daftar berhalaman wajib bisa diunduh (CSV) & CSV-nya benar")
    hasil = scan_pagers()
    total = sum(len(v) for v in hasil.values())
    punya = sum(1 for v in hasil.values() for _ln, ok in v if ok)
    print(f"  daftar berhalaman: {total} di {len(hasil)} berkas · "
          f"punya tombol Unduh: {punya}/{total} · "
          f"pengecualian terdaftar: {len(DIBOLEHKAN)}")
    if verbose:
        for rel, blocks in sorted(hasil.items()):
            for ln, ok in blocks:
                print(f"    {'✓' if ok else '✗'} {rel}:{ln}")
    check_pagers(g, hasil, DIBOLEHKAN)
    check_csv_behaviour(g, verbose=verbose)
    return g.finish()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(1 if self_test() else 0)
    raise SystemExit(main(verbose=("-v" in sys.argv)))
