#!/usr/bin/env python3
"""INV-UI-08 — **PANEL RINCIAN WAJIB POP-UP, BUKAN DISELIPKAN DI BAWAH DAFTAR**

MASALAH YANG DICEGAH (FASE P7 — keluhan pemilik, dilaporkan BERULANG KALI)
=========================================================================
FASE P4 sudah mewajibkan tombol **"Buat/Ubah"** memakai pop-up (`FormModal`), dengan
alasan yang ditulis di berkas itu sendiri: form yang diselipkan di tengah halaman
mendorong daftar data ke bawah lipatan, pengguna tak sadar formnya terbuka, lalu
menyimpulkan "tombolnya tidak berfungsi".

Persoalan yang **SAMA** ternyata masih ada untuk **PANEL RINCIAN** — dan tidak pernah
tercakup penjaga mana pun, karena `INV-UI-05` hanya memeriksa tombol **Buat**. Terukur
pada kode sebelum P7: **9 layar** merender panel rincian sebagai *saudara di bawah
tabelnya*. Pada `ar-aging` (layar yang dilaporkan pemilik) urutannya:

    [tabel Piutang per Pelanggan] → [baris TOTAL] → [catatan kaki 3 baris] → [panel detail]

Jadi ketika pengguna mengklik satu baris, **tidak ada satu pun perubahan yang terlihat
di layar**: rinciannya memang dirender, tetapi di luar pandangan. Semakin panjang
tabelnya, semakin jauh. Yang terjadi berikutnya bisa diprediksi: pengguna menyimpulkan
kliknya tidak berfungsi, lalu mengklik baris LAIN — dan panel di bawah diam-diam
berganti isi tanpa dia tahu. Ini kelas bug yang sama dengan P4: yang rusak bukan
fungsinya, melainkan **umpan balik**-nya, dan tidak ada galat apa pun yang menjelaskan.

ATURAN GATE
-----------
Bila sebuah berkas (a) merender BARIS/DAFTAR, dan (b) merender komponen rincian secara
kondisional berdasarkan state PEMILIHAN (`selected`/`detailId`/`openId`/…), maka
rinciannya WAJIB salah satu dari:

  1. **pop-up** — dibungkus `<DetailModal>`/`<FormModal>`, atau komponennya sendiri
     merender `.modal-overlay` (termasuk bila overlay itu ada di berkas ANAK), atau
     namanya memang `…Modal`/`…Drawer`/`…Sheet`/`…Dialog`; ATAU
  2. **berdampingan (master-detail 2 kolom)** — induk terdekatnya punya kelas grid
     multi-kolom (`lg:grid-cols-[1fr_360px]`, `xl:grid-cols-2`, …), sehingga rincian
     muncul DI SAMPING daftar dan tetap dalam pandangan.

Selain itu = MERAH. Pengecualian harus terdaftar di `DIBOLEHKAN` **dengan alasan
tertulis** yang bisa dinilai orang.

KENAPA PENJAGA INI HARUS MENELUSURI KE BERKAS ANAK & MENGHITUNG INDENTASI
------------------------------------------------------------------------
Dua kesalahan NYATA yang saya buat saat mengukur sebaran masalah ini pertama kali —
keduanya membuat angkanya salah, dan keduanya dijadikan kasus self-test di bawah:

  · **Menuntut `onClick` memanggil setter-nya LANGSUNG.** Nyatanya pemilihan baris
    hampir selalu lewat handler perantara (`openDetail(id)`, `openLot(id)`). Akibatnya
    `ARAgingView` — layar yang justru dilaporkan pemilik — **tidak terdeteksi sama
    sekali**. Penjaga yang melewatkan kasus pelapornya adalah penjaga yang tak berguna.
  · **Mencari nama KELAS CSS (`divide-y`, `grid-cols-…`) di sumber yang STRING-nya
    sudah dibuang.** Nama kelas hanya hidup di dalam string, jadi penandanya selalu
    hilang dan 5 layar lolos. Karena itu: konstruksi KODE dinilai dari sumber terstrip,
    penanda TEKS (kelas CSS) dari sumber MENTAH.

Usage:
    python scripts/guardrails/verify_detail_modal.py
    python scripts/guardrails/verify_detail_modal.py -v
    python scripts/guardrails/verify_detail_modal.py --self-test
"""
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from _common import FRONTEND, Guard, strip_comments_and_strings, G, R, B, X  # noqa: E402

SRC = FRONTEND / "src"

#: State yang berarti "satu baris sedang dipilih".
SEL = re.compile(r"^(selected|sel|detail|active|current|focused|open|expanded|editing|view)\w*$", re.I)
#: Komponen yang berarti "panel rincian".
DETAILISH = re.compile(r"(Detail|Panel|Card|Ledger|Preview|Inspector)")
#: Komponen yang SUDAH berarti pop-up.
MODALISH = re.compile(r"(Modal|Drawer|Sheet|Dialog)")
#: Kelas grid multi-kolom → tata letak master-detail berdampingan.
MULTICOL = re.compile(r"grid-cols-\[[^\]]*[_ ][^\]]*\]|(?:sm|md|lg|xl|2xl):grid-cols-(?:[2-9]|\[)")
#: Penanda berkas ini merender baris/daftar (dicari di sumber MENTAH — kelas CSS).
ROWS_TEXT = re.compile(r"<table|<tbody|<tr\b|divide-y|grid-cols-")

#: Pengecualian — WAJIB beralasan (dinilai orang, bukan dibisukan).
DIBOLEHKAN: Dict[str, str] = {}


def _indent(s: str) -> int:
    return len(s) - len(s.lstrip())


def component_spans(src: str) -> Dict[str, Tuple[int, int]]:
    """→ {NamaKomponen: (awal, akhir)} rentang body di dalam sumber.

    Rentang (bukan potongan teks) karena `strip_comments_and_strings` MEMPERTAHANKAN
    panjang & posisi, jadi offset yang sama bisa dipakai untuk mengambil versi TERSTRIP
    (menilai kode) maupun versi MENTAH (menilai nama kelas CSS, yang hanya hidup di
    dalam string). Tanpa dua pandangan ini, `className="modal-overlay"` tidak pernah
    terlihat dan panel yang SUDAH pop-up akan dituduh sebagai pelanggaran.
    """
    out: Dict[str, Tuple[int, int]] = {}
    for m in re.finditer(r"(?:export\s+)?(?:default\s+)?function\s+([A-Z]\w*)\s*\(", src):
        out.setdefault(m.group(1), (m.end(), m.end() + 12000))
    for m in re.finditer(r"const\s+([A-Z]\w*)\s*=\s*(?:React\.)?(?:memo\()?\s*\(?[^=;]{0,120}=>", src):
        out.setdefault(m.group(1), (m.end(), m.end() + 12000))
    return out


def imports_map(src: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for m in re.finditer(r"import\s+(?:\{([^}]*)\}|(\w+))\s+from\s+[\"']([^\"']+)[\"']", src):
        named, default, path = m.group(1), m.group(2), m.group(3)
        if default:
            out[default] = path
        for n in (named or "").split(","):
            n = n.strip().split(" as ")[-1].strip()
            if n:
                out[n] = path
    return out


def _resolve(path_str: str, from_file: Path):
    if path_str.startswith("@/"):
        base = SRC / path_str[2:]
    elif path_str.startswith("."):
        base = (from_file.parent / path_str).resolve()
    else:
        return None
    for ext in (".jsx", ".js", "/index.jsx", "/index.js"):
        p = Path(str(base) + ext)
        if p.exists():
            return p
    return None


#: Penanda pop-up dalam KODE (dinilai dari sumber terstrip).
OVERLAY_CODE = re.compile(r"<(FormModal|ConfirmModal|DetailModal|Dialog|Drawer|Sheet)\b")
#: Penanda pop-up dalam TEKS: nama kelas CSS hanya hidup di dalam string, jadi harus
#: dicari di sumber MENTAH. Dipersempit ke `className=…` supaya komentar yang sekadar
#: MENYEBUT "modal-overlay" tidak membuat panel dianggap pop-up (itu akan menutupi
#: pelanggaran, bukan menuduh palsu — arah galat yang lebih berbahaya).
OVERLAY_TEXT = re.compile(r"className=[^>]{0,240}?modal-(?:overlay|card)")


def is_popup(comp: str, spans, src: str, raw: str, imps: Dict[str, str], f) -> Tuple[bool, str]:
    """Apakah `comp` menghasilkan pop-up? Menelusuri sampai berkas ANAK."""
    if MODALISH.search(comp):
        return True, f"nama komponen mengandung '{MODALISH.search(comp).group(1)}'"
    span = spans.get(comp)
    if span:
        a, b = span
        if OVERLAY_CODE.search(src[a:b]) or OVERLAY_TEXT.search(raw[a:b]):
            return True, "komponennya merender overlay di berkas ini"
    if f is not None and comp in imps:
        child = _resolve(imps[comp], f)
        if child:
            craw = child.read_text(encoding="utf-8", errors="ignore")
            if OVERLAY_CODE.search(strip_comments_and_strings(craw)) or OVERLAY_TEXT.search(craw):
                return True, f"berkas anak {child.name} merender overlay"
    return False, "tidak menemukan overlay"


def analyze_text(raw: str, f=None, stats=None) -> List[Tuple[int, str, str, str]]:
    """→ [(baris, state, komponen, sebab)] pelanggaran pada SATU berkas.

    `stats` (opsional) diisi hitungan panel yang DIPERIKSA dan lolos, supaya laporan
    gate tidak berbunyi "0 cek lolos" — angka nol di situ tak bisa dibedakan antara
    "semua benar" dan "penjaganya tidak memeriksa apa pun".
    """
    src = strip_comments_and_strings(raw)
    raw_lines = raw.split("\n")
    # (b) berkas ini merender baris? Penanda TEKS → dibaca dari sumber MENTAH.
    if not (re.search(r"\.map\(", src) and ROWS_TEXT.search(raw)):
        return []
    states = {m.group(1) for m in
              re.finditer(r"const\s*\[\s*(\w+)\s*,\s*set\w+\s*\]\s*=\s*useState", src)
              if SEL.match(m.group(1))}
    if not states:
        return []
    bodies, imps = component_spans(src), imports_map(src)

    out: List[Tuple[int, str, str, str]] = []
    for var in sorted(states):
        pat = re.compile(r"\{\s*" + re.escape(var) + r"\s*(?:&&|\?)\s*\(?\s*<(\w+)")
        for m in pat.finditer(src):
            comp = m.group(1)
            if not DETAILISH.search(comp) and not MODALISH.search(comp):
                continue
            line = src[:m.start()].count("\n") + 1
            popup, why = is_popup(comp, bodies, src, raw, imps, f)
            if popup:
                if stats is not None:
                    stats["popup"] = stats.get("popup", 0) + 1
                continue
            # (2) berdampingan? Induk terdekat (indentasi lebih kecil) ber-grid multi-kolom.
            ti = _indent(raw_lines[line - 1])
            side_by_side = False
            for i in range(line - 2, -1, -1):
                s = raw_lines[i]
                if not s.strip():
                    continue
                if _indent(s) < ti and re.search(r"<(div|section|main|aside)\b", s):
                    side_by_side = bool(MULTICOL.search(s))
                    break
            if side_by_side:
                if stats is not None:
                    stats["side"] = stats.get("side", 0) + 1
                continue
            out.append((line, var, comp, why))
    return out


def scan(stats=None) -> Dict[str, List[Tuple[int, str, str, str]]]:
    hasil: Dict[str, List[Tuple[int, str, str, str]]] = {}
    for path in sorted(SRC.rglob("*.jsx")):
        rel = str(path.relative_to(SRC))
        if rel.startswith("components" + os.sep + "ui" + os.sep):
            continue
        v = analyze_text(path.read_text(encoding="utf-8", errors="ignore"), path, stats)
        if v:
            hasil[rel] = v
    return hasil


def check(g: Guard, hasil, dibolehkan: Dict[str, str]) -> None:
    for rel, items in sorted(hasil.items()):
        alasan = (dibolehkan.get(rel) or "").strip()
        for line, var, comp, _why in items:
            g.bump()
            if not alasan:
                g.add(f"{rel}:{line} merender <{comp}> (dipicu state `{var}`) sebagai "
                      f"SAUDARA di bawah daftar → setelah mengklik baris, pengguna tidak "
                      f"melihat perubahan apa pun karena panelnya di luar pandangan; "
                      f"semakin panjang tabelnya semakin jauh. Bungkus dengan "
                      f"`<DetailModal>` (components/DetailModal.jsx) atau letakkan "
                      f"berdampingan dalam grid 2 kolom; bila memang harus, daftarkan di "
                      f"DIBOLEHKAN dengan alasan.")
            elif len(alasan) < 20:
                g.add(f"{rel} dibebaskan tanpa alasan yang bisa dinilai orang.")


# ─────────────────────────────────────────────────────────────────────────────
LIST = ('<div className="divide-y">{rows.map((r) => <div key={r.id}>{r.n}</div>)}</div>')


def self_test() -> int:
    kasus = []

    def cek(nama, benar):
        kasus.append((nama, benar))

    def wrap(inner, head="const [selected, setSelected] = useState(null);"):
        return ("import DetailModal from '../components/DetailModal';\n"
                f"function V() {{\n  {head}\n  return (\n    <div data-testid=\"v\">\n"
                f"      {LIST}\n      {inner}\n    </div>\n  );\n}}\n")

    # ── Lapis 1 — HARUS MEMERAH ───────────────────────────────────────────────
    cek("panel detail di bawah daftar → MERAH",
        len(analyze_text(wrap("{selected && <FooDetailPanel id={selected} />}"))) == 1)
    cek("bentuk ternary juga terdeteksi",
        len(analyze_text(wrap("{selected ? <FooDetailPanel /> : null}"))) == 1)
    cek("state bernama detailId juga dikenali",
        len(analyze_text(wrap("{detailId && <BarDetailPanel />}",
                              "const [detailId, setDetailId] = useState('');"))) == 1)
    cek("state bernama openId juga dikenali",
        len(analyze_text(wrap("{openId && <SpecDetailPanel />}",
                              "const [openId, setOpenId] = useState('');"))) == 1)
    # Kasus NYATA: pemilihan lewat handler perantara, BUKAN setter langsung di onClick.
    cek("pemilihan lewat handler perantara (openDetail) tetap terdeteksi — kasus ARAgingView",
        len(analyze_text(
            "function V() {\n  const [selected, setSelected] = useState(null);\n"
            "  const openDetail = (id) => setSelected(id);\n  return (<div>\n"
            "    <div className=\"divide-y\">{rows.map((r) => "
            "<div key={r.id} onClick={() => openDetail(r.id)}>{r.n}</div>)}</div>\n"
            "    {selected && <CustomerDetail id={selected} />}\n  </div>);\n}")) == 1)
    # Kasus NYATA: tabel berbasis grid — penanda barisnya hanya ada di dalam STRING.
    cek("tabel berbasis grid-cols (kelas hanya ada di STRING) tetap dihitung merender baris",
        len(analyze_text(
            "function V() {\n  const [detail, setDetail] = useState(null);\n  return (<div>\n"
            "    <div className=\"grid grid-cols-[110px_1fr]\">{rows.map((b) => "
            "<span key={b.id}>{b.n}</span>)}</div>\n"
            "    {detail && <VendorBillDetailPanel bill={detail} />}\n  </div>);\n}")) == 1)

    # ── Lapis 2 — TIDAK boleh menuduh palsu ───────────────────────────────────
    cek("dibungkus <DetailModal> → hijau",
        analyze_text(wrap("{selected && (<DetailModal onClose={x}>"
                          "<FooDetailPanel /></DetailModal>)}")) == [])
    cek("komponen bernama …Modal → hijau",
        analyze_text(wrap("{selected && <FooDetailModal />}")) == [])
    cek("komponen bernama …Drawer → hijau",
        analyze_text(wrap("{selected && <FooDetailDrawer />}")) == [])
    cek("master-detail 2 kolom (lg:grid-cols-[1fr_360px]) → hijau",
        analyze_text(
            "function V() {\n  const [selected, setSelected] = useState(null);\n"
            "  return (\n    <div className=\"grid gap-3 lg:grid-cols-[1fr_360px]\">\n"
            "      <div className=\"divide-y\">{rows.map((r) => <b key={r.id}/>)}</div>\n"
            "      {selected && <AmdDetailPanel />}\n    </div>\n  );\n}") == [])
    cek("master-detail 2 kolom (xl:grid-cols-2) → hijau",
        analyze_text(
            "function V() {\n  const [active, setActive] = useState(null);\n"
            "  return (\n    <div className=\"grid grid-cols-1 gap-4 xl:grid-cols-2\">\n"
            "      <div className=\"divide-y\">{rows.map((r) => <b key={r.id}/>)}</div>\n"
            "      {active && <CaseDetailPanel />}\n    </div>\n  );\n}") == [])
    cek("panelnya sendiri merender .modal-overlay di berkas yang sama → hijau",
        analyze_text(wrap("{selected && <FooDetailPanel />}")
                     + "\nfunction FooDetailPanel(){return <div className=\"modal-overlay\"/>;}") == [])
    cek("yang dirender BUKAN panel rincian (mis. <span>) → hijau",
        analyze_text(wrap("{selected && <span>x</span>}")) == [])
    cek("berkas TANPA daftar/baris → bukan urusan penjaga ini",
        analyze_text("function V(){const [selected,setSelected]=useState(null);"
                     "return <div>{selected && <FooDetailPanel/>}</div>;}") == [])
    cek("penyebutan di dalam KOMENTAR tidak dihitung",
        analyze_text(wrap("{/* {selected && <FooDetailPanel />} */}")) == [])
    cek("penyebutan di dalam STRING tidak dihitung",
        analyze_text(wrap("{'{selected && <FooDetailPanel />}'}")) == [])

    # ── Lapis 3 — ATURAN pembebasan ───────────────────────────────────────────
    g = Guard("INV-UI-08", "self-test")
    g.violations, g.checks = [], 0
    check(g, {"a.jsx": [(3, "selected", "FooDetailPanel", "-")]}, {})
    cek("pelanggaran tanpa pembebasan → MERAH", len(g.violations) == 1)

    g = Guard("INV-UI-08", "self-test")
    g.violations, g.checks = [], 0
    check(g, {"a.jsx": [(3, "selected", "FooDetailPanel", "-")]},
          {"a.jsx": "Panel ini memang alur kerja pemindai, bukan rincian sesaat."})
    cek("pembebasan beralasan panjang → hijau", len(g.violations) == 0)

    g = Guard("INV-UI-08", "self-test")
    g.violations, g.checks = [], 0
    check(g, {"a.jsx": [(3, "selected", "FooDetailPanel", "-")]}, {"a.jsx": "nanti"})
    cek("pembebasan tanpa alasan yang bisa dinilai → MERAH", len(g.violations) == 1)

    gagal = sum(0 if ok else 1 for _n, ok in kasus)
    print(f"{B}== SELF-TEST INV-UI-08 (panel rincian wajib pop-up) =={X}")
    for nama, ok in kasus:
        print(f"  [{G + 'PASS' + X if ok else R + 'FAIL' + X}] {nama}")
    print(f"{G}  HIJAU — penjaga menangkap panel yang diselipkan di bawah daftar "
          f"(termasuk dua kasus yang PERNAH ia lewatkan), tanpa menuduh pop-up, "
          f"master-detail 2 kolom, komentar, maupun string.{X}" if not gagal
          else f"{R}{B}  SELF-TEST MERAH ({gagal} kasus).{X}")
    return gagal


def main(verbose: bool = False) -> int:
    g = Guard("INV-UI-08", "panel rincian wajib pop-up (bukan diselipkan di bawah daftar)")
    stats: Dict[str, int] = {}
    hasil = scan(stats)
    total = sum(len(v) for v in hasil.values())
    popup, side = stats.get("popup", 0), stats.get("side", 0)
    # Setiap panel yang diperiksa dihitung sebagai satu cek, termasuk yang LOLOS —
    # supaya "0 pelanggaran" datang bersama bukti bahwa ada yang benar-benar diperiksa.
    g.bump(popup + side)
    print(f"  panel rincian diperiksa: {popup + side + total} → "
          f"pop-up {popup} · berdampingan (2 kolom) {side} · INLINE (pelanggaran) {total}"
          f" · pengecualian terdaftar: {len(DIBOLEHKAN)}")
    if verbose:
        for rel, items in sorted(hasil.items()):
            for line, var, comp, why in items:
                print(f"    ✗ {rel}:{line} {{{var} && <{comp}>}}  [{why}]")
    check(g, hasil, DIBOLEHKAN)
    return g.finish()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(1 if self_test() else 0)
    raise SystemExit(main(verbose=("-v" in sys.argv)))
