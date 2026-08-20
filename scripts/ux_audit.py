#!/usr/bin/env python3
"""
ux_audit.py — Kain Nusantara (KN3) UX Baseline Enforcer
=======================================================
Mengubah `docs/UX_USABILITY_STANDARD.md` dari prosa menjadi cek EXECUTABLE.
Scan `frontend/src/features` + `components` (kecuali `components/ui` = primitif shadcn)
untuk pelanggaran baseline UX yang sering jadi sumber "jelek tapi lolos":

  E1  Tabel data tanpa LOADING state            (ERROR — hanya untuk layar yang MENARIK datanya sendiri)
  E2  Tabel data tanpa penanganan KOSONG        (ERROR)
  E3  Chart (recharts) tanpa EMPTY-state guard  (ERROR)
  E4  Dropdown `<select>` bawaan peramban       (ERROR — naik dari W2 pada FASE P6)
  W1  Kolom uang tanpa `tabular-nums`           (WARN  — backlog presisi angka)
  W3  Elemen interaktif tanpa data-testid       (WARN  — testability)
  W4  Chart tanpa <Tooltip>                     (WARN)
  W5  Tabel kosong DIAM (ada penjaga panjang, tak ada kalimat)  (WARN — FASE P5)

PERUBAHAN FASE P5 — kenapa aturan E1/E2 dibuat SADAR-RUJUKAN
------------------------------------------------------------
Versi pertama menilai tiap berkas SENDIRI-SENDIRI dengan pencocokan teks. Diukur pada
22 ERROR yang dilaporkannya, sebagian besar ternyata **tuduhan palsu** — dan penjaga
yang menuduh palsu akan dimatikan orang, bukan dipatuhi:

  · **E1 dituduhkan ke komponen PENAMPIL.** `FinanceTowerParts`, `BudgetParts`,
    `FinancialStatementsParts`, `ProductionParts`, `IntercoDetailParts`,
    `AmendmentImpactCard` menerima datanya lewat **props** dan tidak memanggil API sama
    sekali (`axios` = 0). Komponen begitu **tidak mungkin** tahu "sedang memuat" —
    yang tahu adalah induknya, dan induknya (`FinanceTowerView`, `ProductionView`, …)
    memang sudah punya `loading` + skeleton. Menuruti tuduhan ini akan memaksa prop
    `loading` palsu di belasan berkas: kode bertambah, layar tidak berubah sedikit pun.
    → E1 sekarang hanya berlaku bila berkasnya MENARIK data sendiri
      (`axios`/`apiClient`/`usePagedList`/`useQuery`/`fetch`).

  · **E2 tidak mengenali bentuk penjaga yang benar-benar dipakai repo ini.** Regex lama
    hanya mencari `length === 0` / `!x.length`, sehingga `{active.length > 0 && …}`
    (PeriodUnlockCard), `const hasLines = (section.lines||[]).length > 0`
    (FinancialStatementsParts), dan penjaga yang berada di komponen ANAK
    (`FinanceTowerView` → `FinanceTowerParts` yang memuat `<EmptyState … "Belum ada
    aktivitas GL tahun ini">`) semuanya dibaca "tanpa empty state".
    → E2 sekarang menerima bentuk-bentuk itu DAN menelusuri satu lapis ke komponen anak
      bernama `*Table/List/Rows/Parts/Grid/Panel/Card/Board/Tab`.

  · **Beda "kosong yang menjelaskan" vs "kosong yang diam" hilang.** `{rows.length > 0 &&
    <table/>}` memang tidak menabrak, tetapi pengguna melihat area kosong tanpa tahu
    apakah datanya belum ada, masih dimuat, atau gagal. Itu nyata, tapi bukan sekelas
    "tabel tanpa penjaga sama sekali" → jadi **W5**, bukan ERROR. Memberi label yang
    proporsional membuat angka ERROR bisa dipercaya (dan karena itu bisa dijadikan gate).

Sebelum P5 audit ini **tidak pernah punya `--self-test`** dan **tidak terdaftar di
`gate.sh`** — jadi angkanya tidak pernah dibuktikan bisa memerah, dan tidak ada yang
mencegahnya memburuk. Keduanya ditutup di fase ini.

Usage:
    python scripts/ux_audit.py               # ringkasan (exit 0)
    python scripts/ux_audit.py --strict      # exit 1 bila ada ERROR (untuk gate)
    python scripts/ux_audit.py --file features/orders/OrdersView.jsx
    python scripts/ux_audit.py --self-test   # bukti-merah kedua arah
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"
SCAN_DIRS = [SRC / "features", SRC / "components"]
sys.path.insert(0, str(ROOT / "scripts" / "guardrails"))
from _common import strip_comments_and_strings  # noqa: E402
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

# *Field / *Input components render FORM CONTROLS (radio/checkbox/text), not data
# tables — exempt them from the table loading/empty baseline (E1/E2).
FORM_HINTS = ("Form", "Modal", "Dialog", "Drawer", "Editor", "Create", "Edit", "Wizard",
              "Panel", "Uploader", "Field", "Input", "Login", "QuickView", "Settings")

#: Berkas ini MENARIK datanya sendiri → wajib punya keadaan "sedang memuat".
SELF_FETCH = re.compile(r"axios\.|apiClient|usePagedList|useQuery\s*\(|\bfetch\s*\(")
#: Penanda keadaan "sedang memuat/memproses" — WAJIB berbentuk KODE, bukan kata dalam
#: kalimat, dan harus toleran terhadap NAMA BERIMBUHAN.
#: Dua tuduhan palsu yang diukur saat menyusun aturan ini:
#:   · `components/PeriodUnlockCard.jsx` LOLOS hanya karena kalimat JSX "…tidak ada
#:     jendela **posting** mundur yang terbuka." padahal kartunya `return null` selama
#:     memuat (muncul tiba-tiba tanpa kerangka). Teks JSX bukan literal string, jadi
#:     pembersih komentar/string tidak menolong → penanda harus DIPAKAI dalam ekspresi.
#:   · `features/hr/AttendanceView.jsx` DITUDUH tanpa loading padahal punya
#:     `loadingDaily` / `loadingRecap` / `savingManual` — pola kaku `\bloading\b` tidak
#:     mengenali nama berimbuhan, dan memaksa orang menamai state-nya persis "loading"
#:     hanya demi menyenangkan pemeriksa.
_PENDING = r"(?:loading|busy|submitting|saving|posting|pending|importing|exporting)"
#: Penanda berbentuk KELAS CSS — hidup di dalam literal string (`className="… animate-pulse"`),
#: jadi WAJIB dicari pada teks MENTAH. (Dicari pada sumber yang string-nya sudah dibuang,
#: kerangka `animate-pulse` yang baru ditambahkan pun tak akan terlihat — terukur pada
#: `PeriodUnlockCard` sesaat setelah kerangkanya dipasang.)
LOADING_CLASS = re.compile(r"animate-pulse|animate-spin")
#: Penanda berbentuk KODE — dicari pada sumber tanpa komentar & string.
LOADING_CODE = re.compile(
    r"<Skeleton|<Spinner|\bSkeleton\b|\bSpinner\b|\bLoader2?\b"
    r"|set\w*" + _PENDING + r"\w*\s*\("
    r"|\b\w*" + _PENDING + r"\w*\s*(?:\?|&&|\|\||\)|,|\}|===|!==|=[^=])",
    re.I)
#: Penjaga panjang daftar (semua bentuk yang benar-benar dipakai repo ini).
ZERO_GUARD = re.compile(r"length\s*===?\s*0|length\s*!==?\s*0|length\s*<\s*1|"
                        r"length\s*>\s*0|length\s*\?|\.length\s*&&|!\s*[\w.]*\.length")
#: Kalimat yang MENJELASKAN kekosongan kepada pengguna. Pola `belum …` dibuat GENERIK
#: setelah memeriksa temuan W5 satu per satu: layar-layar itu SUDAH menjelaskan
#: kekosongannya, hanya dengan kata lain — "Jadwal penyusutan belum TERSEDIA untuk aset
#: ini", "Belum PERNAH dijalankan.", "Registry belum BERISI enum". Mengharuskan satu
#: pilihan kata ("belum ada") berarti menuduh layar yang justru sudah benar, dan penjaga
#: yang menuduh palsu akan dimatikan orang.
#: Konsekuensi yang diterima sadar: berkas yang memuat kata "belum" untuk hal LAIN bisa
#: lolos E2. Risiko itu kecil (E2 hanya menyala bila TIDAK ADA penjaga panjang sekalian)
#: dan jauh lebih murah daripada 8 tuduhan palsu yang membuat orang berhenti percaya.
EMPTY_MSG = re.compile(r"\bbelum\s+\w+|\btidak\s+ada\b|\btidak\s+tersedia\b|\btak\s+ada\b|"
                       r"kosong|nihil|sudah\s+tertaut|sudah\s+lengkap|<EmptyState|EmptyState\b",
                       re.I)
#: PANEL YANG SENGAJA MENYEMBUNYIKAN DIRI saat tak ada yang perlu dikatakan
#: (`if (!over.length) return null`). Ini pola yang BENAR, bukan gap: pita peringatan
#: anggaran tanpa peringatan, atau grafik jejak dokumen tanpa jejak, sebaiknya TIDAK
#: memakan ruang layar hanya untuk mengumumkan bahwa dirinya kosong.
SELF_HIDING = re.compile(r"(?:!\s*[\w.]*\.length|\.length\s*===?\s*0"
                         r"|\.length\s*===?\s*0\s*&&[^\n]*\.length\s*===?\s*0)"
                         r"[^\n]{0,60}\)\s*return null")
#: Komponen anak yang wajar menampung tabel/daftar → ditelusuri satu lapis.
CHILD_LISTISH = re.compile(r"<([A-Z][A-Za-z0-9]*(?:Table|List|Rows|Parts|Grid|Panel|"
                           r"Card|Board|Tab|Tabs|Summary|Breakdown))\b")
#: Pemanggilan pemformat uang.
MONEY_CALL = re.compile(r"formatCurrency\s*\(|fmtIDR\s*\(|compactIDR\s*\(|\brp\s*\(|\bidr\s*\(")
#: Konteks KOLOM — tempat angka memang harus berbaris rapi.
COLUMN_CTX = re.compile(r"<t[dh]\b|text-right|grid-cols|\bjustify-between\b")

_SRC_CACHE = {}


def component_source(name: str) -> str:
    """Isi berkas komponen `name`, '' bila tak ditemukan (di-cache)."""
    if name in _SRC_CACHE:
        return _SRC_CACHE[name]
    teks = ""
    for cand in SRC.rglob(f"{name}.jsx"):
        teks = cand.read_text(encoding="utf-8", errors="ignore")
        break
    _SRC_CACHE[name] = teks
    return teks


def rel(p):
    return str(p.relative_to(SRC))


def child_explains_empty(t: str) -> bool:
    """Komponen anak yang merender daftar sudah menjelaskan kekosongan?"""
    for m in CHILD_LISTISH.finditer(t):
        if EMPTY_MSG.search(component_source(m.group(1))):
            return True
    return False


def analyze_text(t: str, filename: str = "X.jsx"):
    """Kembalikan list (severity, code, msg) untuk SATU berkas.

    Dipisah dari `analyze(path)` supaya bisa diuji langsung oleh `--self-test`
    tanpa menyentuh berkas nyata.
    """
    findings = []
    is_form = any(h in filename for h in FORM_HINTS)

    # Penilaian yang menyangkut KODE (adakah state memuat? adakah penjaga panjang?)
    # dilakukan pada sumber yang komentar & literal string-nya SUDAH DIBUANG. Tanpa ini
    # kata "posting"/"loading" yang cuma muncul di kalimat penjelasan dihitung sebagai
    # bukti adanya indikator — terukur pada `components/PeriodUnlockCard.jsx`, yang
    # sebenarnya `return null` selama memuat (kartu muncul tiba-tiba tanpa kerangka).
    kode = strip_comments_and_strings(t)

    renders_rows = bool(re.search(r'<table', t) or re.search(r'\.map\(\s*\(?\w+', t))
    has_table = bool(re.search(r'<table|<tbody|role=["\']table', t)) or (
        renders_rows and re.search(r'<tr|<td|grid|divide-y', t))

    has_loading = bool(LOADING_CLASS.search(t)) or bool(LOADING_CODE.search(kode))
    self_fetch = bool(SELF_FETCH.search(kode))
    # Kalimat kekosongan justru HARUS dicari di teks mentah — ia memang sebuah string
    # yang dibaca pengguna ("Belum ada data").
    has_empty_msg = bool(EMPTY_MSG.search(t)) or child_explains_empty(t)
    has_zero_guard = bool(ZERO_GUARD.search(kode))

    if has_table and not is_form:
        # E1 — hanya untuk layar yang menarik datanya sendiri. Komponen penampil
        # (data lewat props) tidak bisa tahu "sedang memuat"; induknya yang dinilai.
        if self_fetch and not has_loading:
            findings.append(("ERROR", "E1", "Tabel data tanpa LOADING state (berkas ini menarik data sendiri)"))
        if not has_empty_msg:
            if SELF_HIDING.search(kode):
                pass    # panel sengaja tak dirender saat kosong → pola yang benar
            elif has_zero_guard:
                findings.append(("WARN", "W5", "Kosong DIAM — ada penjaga panjang tapi tak ada kalimat penjelas"))
            else:
                findings.append(("ERROR", "E2", "Tabel data tanpa penanganan KOSONG (tanpa penjaga & tanpa kalimat)"))

    # Chart (recharts) — hanya jika import recharts / elemen chart JSX (BUKAN ikon BarChart2)
    if re.search(r'from\s+["\']recharts["\']|<(Line|Area|Pie|Radar)Chart\b|<BarChart[\s>]', t):
        if not (has_empty_msg or has_zero_guard):
            findings.append(("ERROR", "E3", "Chart tanpa EMPTY-state guard"))
        if 'Tooltip' not in t:
            findings.append(("WARN", "W4", "Chart tanpa <Tooltip>"))

    # ── W1 — UANG DI KOLOM tanpa `tabular-nums` ─────────────────────────────
    # Standarnya (docs/UX_USABILITY_STANDARD.md) berbunyi "**KOLOM** uang tanpa
    # tabular-nums": gunanya supaya digit pada tabel angka BERBARIS rapi sehingga
    # ribuan/ratusan mudah dibandingkan sekilas. Versi pertama kehilangan kata "kolom"
    # dan hanya bertanya "apakah berkas ini menampilkan uang dan tak punya tabular-nums
    # di mana pun" → 28 berkas ditandai, padahal sebagian besar hanya menyebut nominal
    # DI DALAM KALIMAT ("Store Credit: Rp 250.000", "Kontrak akan terbit dengan harga
    # Rp 1.2 jt"). Pada kalimat, angka proporsional justru lebih enak dibaca dan tidak
    # ada yang perlu diluruskan. Sekarang yang diperiksa hanya nominal yang berada di
    # KONTEKS KOLOM (<td>/<th>/text-right/baris grid), dan barisnya disebutkan.
    for i, ln in enumerate(t.split("\n"), start=1):
        if not MONEY_CALL.search(ln) or "tabular-nums" in ln:
            continue
        if not COLUMN_CTX.search(ln):
            continue
        findings.append(("WARN", "W1",
                         f"baris {i}: nominal di kolom tanpa `tabular-nums` "
                         f"(digit tidak berbaris rapi saat dibandingkan)"))
        break   # satu temuan per berkas cukup untuk daftar kerja

    # ── E4 — DROPDOWN `<select>` BAWAAN PERAMBAN (naik dari W2, FASE P6) ────────
    # Kenapa sekarang ERROR: 13 dropdown bawaan terakhir (di 9 berkas) sudah dikonversi
    # ke `components/KNSelect.jsx`, yang memang sudah dipakai **182 berkas** lain. Selama
    # aturannya hanya WARN, dropdown bawaan berikutnya tetap bisa masuk tanpa menahan
    # gate — dan campuran dua macam dropdown itulah yang membuat aplikasi terasa bukan
    # satu produk: yang bawaan tidak bisa diketik untuk mencari, tampilannya berbeda di
    # tiap sistem operasi, dan di Android membuka roda putar sebesar layar.
    #
    # DIBACA DARI `kode` (komentar & string sudah dibuang), BUKAN teks mentah. Versi
    # pertama memindai `t` dan langsung MENUDUH PALSU `components/KNSelect.jsx` —
    # justru berkas PENGGANTINYA — karena docstring-nya menjelaskan kalimat
    # "`<select>` bawaan bisa diberi aria-label langsung". Ini terukur, bukan dugaan:
    # setelah 13 konversi selesai, `<select` di seluruh `frontend/src` tinggal 1 dan
    # satu-satunya itu ada DI DALAM KOMENTAR. Penjaga yang menuduh berkas yang benar
    # akan "diperbaiki" orang dengan cara menghapus penjelasannya — kerugian ganda.
    if re.search(r"<select[\s>/]", kode):
        findings.append(("ERROR", "E4", "Dropdown `<select>` bawaan peramban — "
                                        "pakai `components/KNSelect.jsx`"))

    # Interaktif tanpa testid (hanya bila file punya banyak tombol)
    n_btn = len(re.findall(r'<(button|Button)\b', t))
    n_testid = len(re.findall(r'data-testid', t))
    if n_btn >= 3 and n_testid == 0:
        findings.append(("WARN", "W3", f"{n_btn} tombol, 0 data-testid (sulit dites)"))
    return findings


def analyze(path):
    return analyze_text(path.read_text(encoding="utf-8", errors="ignore"), path.name)


TABLE = ('<table><tbody>{rows.map((r) => (<tr><td>{r.a}</td></tr>))}</tbody></table>')


def self_test() -> int:
    """Bukti-merah DUA ARAH: harus memerah untuk gap nyata, dan TIDAK menuduh palsu."""
    kasus = []

    def cek(nama, kondisi):
        kasus.append((nama, bool(kondisi)))

    def codes(t, fn="X.jsx"):
        return {c for _s, c, _m in analyze_text(t, fn)}

    # ── harus MEMERAH ────────────────────────────────────────────────────────
    cek("tabel tanpa penjaga & tanpa kalimat → E2",
        "E2" in codes(TABLE))
    cek("layar yang fetch sendiri tanpa loading → E1",
        "E1" in codes('const r = await axios.get("/x"); ' + TABLE))
    cek("chart tanpa penjaga kosong → E3",
        "E3" in codes('import { BarChart } from "recharts"; <BarChart data={d} />'))
    cek("uang DI KOLOM tanpa tabular-nums → W1",
        "W1" in codes('<td className="text-right">{formatCurrency(x)}</td>'))
    cek("uang di dalam KALIMAT → bukan W1 (angka proporsional lebih enak dibaca)",
        "W1" not in codes('<p>Store Credit: {formatCurrency(bal)}</p>\n' + TABLE))
    cek("uang di kolom yang SUDAH tabular-nums → bukan W1",
        "W1" not in codes('<td className="text-right tabular-nums">{formatCurrency(x)}</td>'))
    cek("native select → E4",
        "E4" in codes('<select><option/></select>' + TABLE))
    cek("native select yang menutup sendiri (`<select />`) → E4",
        "E4" in codes('<select />' + TABLE))

    # ── TIDAK boleh menuduh palsu (kasus NYATA dari repo ini) ────────────────
    cek("komponen PENAMPIL (data via props, tanpa axios) tidak dituduh E1",
        "E1" not in codes('export default function P({rows}) { return (' + TABLE + '); }'))
    cek("penjaga `length > 0` + kalimat → tidak ada E2",
        "E2" not in codes('{rows.length > 0 ? ' + TABLE + ' : <p>Belum ada data</p>}'))
    cek("kalimat kosong via <EmptyState> → tidak ada E2",
        "E2" not in codes('{!rows.length ? <EmptyState/> : ' + TABLE + '}'))
    cek("penjaga ada tapi TANPA kalimat → W5 (bukan E2)",
        codes('{rows.length > 0 && ' + TABLE + '}') >= {"W5"}
        and "E2" not in codes('{rows.length > 0 && ' + TABLE + '}'))
    cek("kalimat 'belum tersedia' dihitung sbg penjelasan kosong → bukan W5/E2",
        {"W5", "E2"}.isdisjoint(
            codes('{rows.length === 0 ? <p>Jadwal belum tersedia.</p> : ' + TABLE + '}')))
    cek("panel sengaja menyembunyikan diri saat kosong (return null) → bukan W5",
        "W5" not in codes('if (!groups.length) return null;\n' + TABLE))
    cek("kekosongan dijelaskan di komponen ANAK → tidak ada E2 (delegasi)",
        "E2" not in codes('<FinanceTowerParts rows={rows} />' + TABLE))
    cek("berkas form/modal dikecualikan dari E1/E2",
        codes(TABLE, "SupplierFormModal.jsx") == set()
        or {"E1", "E2"}.isdisjoint(codes(TABLE, "SupplierFormModal.jsx")))
    cek("layar fetch + skeleton → tidak ada E1",
        "E1" not in codes('await axios.get("/x"); {loading ? <div className="animate-pulse"/> : ' + TABLE + '}'))
    # Kasus NYATA FASE P6: `components/KNSelect.jsx` — berkas PENGGANTI dropdown bawaan —
    # dituduh E4 oleh versi pertama karena docstring-nya MENYEBUT `<select>`.
    cek("kata `<select>` di dalam KOMENTAR → bukan E4 (kasus KNSelect.jsx sendiri)",
        "E4" not in codes('/** `<select>` bawaan bisa diberi aria-label langsung. */\n'
                          'export function KNSelect() { return <Select />; }'))
    cek("kata `<select>` di dalam STRING → bukan E4",
        "E4" not in codes('const pesan = "jangan pakai <select> bawaan";'))
    cek("komponen shadcn <SelectTrigger>/<Select> → bukan E4 (huruf besar, beda elemen)",
        "E4" not in codes('<Select><SelectTrigger/><SelectValue/></Select>'))
    cek("variabel bernama `selected`/`selectedRow` → bukan E4",
        "E4" not in codes('const selectedRow = rows[0]; const selected = 1;'))

    gagal = sum(0 if ok else 1 for _n, ok in kasus)
    print(f"{B}== SELF-TEST ux_audit (baseline UX harus bisa MEMERAH & tak menuduh palsu) =={X}")
    for nama, ok in kasus:
        print(f"  [{G + 'PASS' + X if ok else R + 'FAIL' + X}] {nama}")
    print(f"{G}  HIJAU — audit terbukti menangkap gap nyata tanpa menuduh komponen penampil.{X}"
          if not gagal else f"{R}{B}  SELF-TEST MERAH ({gagal} kasus).{X}")
    return gagal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--file")
    ap.add_argument("--self-test", action="store_true", dest="selftest")
    args = ap.parse_args()

    if args.selftest:
        return 1 if self_test() else 0

    files = []
    if args.file:
        files = [SRC / args.file]
    else:
        for d in SCAN_DIRS:
            for f in d.rglob("*.jsx"):
                if "/ui/" in str(f).replace("\\", "/"):
                    continue
                files.append(f)
    files = sorted(set(files))

    total_err = total_warn = 0
    err_files = []
    print(f"\n{B}{C}KN3 — UX BASELINE AUDIT ({len(files)} file){X}\n")
    for f in files:
        fnd = analyze(f)
        if not fnd:
            continue
        errs = [x for x in fnd if x[0] == "ERROR"]
        warns = [x for x in fnd if x[0] == "WARN"]
        total_err += len(errs); total_warn += len(warns)
        if errs:
            err_files.append(rel(f))
        head = f"{R}●{X}" if errs else f"{Y}○{X}"
        print(f"{head} {B}{rel(f)}{X}")
        for sev, code, msg in fnd:
            c = R if sev == "ERROR" else Y
            print(f"    {c}[{sev} {code}]{X} {msg}")

    print(f"\n{B}{'='*60}{X}")
    print(f"  {R}ERROR {total_err}{X}  |  {Y}WARN {total_warn}{X}  (di {len(files)} file)")
    print(f"{B}{'='*60}{X}")
    if total_err:
        print(f"\n  {R}{B}{len(err_files)} file melanggar baseline UX (loading/empty/chart).{X}")
        for rf in err_files:
            print(f"    {R}·{X} {rf}")
    else:
        print(f"\n  {G}{B}Tidak ada pelanggaran ERROR baseline UX.{X}")
    print()
    if args.strict and total_err:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
