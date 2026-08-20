#!/usr/bin/env python3
"""INV-UI-09 — Pemilih (pemicu + pop-up di satu komponen) WAJIB merender pop-upnya
lewat **portal**, dan pop-up mentah tidak boleh lahir di dalam `<label>`.

KELAS BUG YANG DICEGAH (terukur 2026-08-19, ditemukan saat menutup FASE T)
=========================================================================
`components/ProductSelect.jsx`, `components/MakloonSelect.jsx`, dan
`components/PantoneFinder.jsx` adalah **pemicu + pop-up dalam satu komponen**:
tombol `field` + modal pemilih. Ketiganya dipakai di dalam `<Field>` yang merender
**`<label>`** (Wizard Order Makloon, Order Makloon, Resep Proses, Kontrak Mitra,
Master Produk, Template Produk, …). Aktivasi `<label>` **diteruskan peramban** ke
kontrol yang dilabeli, dan kontrol itu adalah tombol pemicunya sendiri. Jadi:

    pengguna klik baris produk → produk TERPILIH (benar)
                              → label meneruskan klik ke tombol pemicu
                              → `setOpen(true)` → pop-up **terbuka kembali**,
                                kotak carinya kosong seperti baru dibuka.

Yang dilihat pengguna: setiap kali memilih produk/mitra/warna, pop-up "tidak mau
menutup" dan harus ditekan × dulu; selama itu tombol berikutnya (mis. **Lanjut**
di wizard) tertutup lapisan pop-up. Tidak ada galat apa pun — jadi tidak ada yang
bisa dicari di log. Bug ini hidup di **3 komponen × 9 tempat pakai**.

Kenapa `e.stopPropagation()` di kartu pop-up TIDAK menolong: React memasang
pendengarnya di **akar** dokumen, sedangkan `<label>` berada di antara target klik
dan akar — peristiwa nyata sudah melewati label lebih dulu, dan aktivasi label
adalah perilaku PERAMBAN, bukan perambatan React. Perbaikan yang benar secara
struktural: pop-up dirender **di luar** `<label>` lewat `createPortal(…, document.body)`.

ATURAN (STATIK, tidak butuh backend)
====================================
  A. Berkas "pemilih" = punya prop `triggerTestId` (tombol pemicu milik sendiri)
     **dan** merender lapisan pop-up sendiri (`className` memuat `fixed inset-0`
     + `bg-black/`). Di berkas seperti itu, setiap render bersyarat komponen
     pop-up (`…Modal` / `…Picker` / `…Finder` / `…Sheet` / `…Drawer`) WAJIB
     melewati `createPortal(`.
  B. `<label>` mentah tidak boleh MEMUAT lapisan pop-up (`fixed inset-0` +
     `bg-black/`) di dalam bloknya — itu bentuk lain dari kelas bug yang sama,
     ditulis langsung di layar alih-alih lewat komponen pemilih.

Yang SENGAJA tidak dituduh:
  * berkas pop-up murni (modal tanpa pemicu sendiri) — mis. `FormModal`,
    `DetailModal`, modal per-layar: pop-up itu bukan anak `<label>`;
  * pemicu tanpa pop-up (mis. `KNSelect` — Radix sudah ber-portal sendiri);
  * penyebutan `triggerTestId` yang hanya ada di KOMENTAR/STRING (dokumentasi).

Jalankan:
    python scripts/guardrails/verify_picker_portal.py
    python scripts/guardrails/verify_picker_portal.py --self-test
"""
import os
import re
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from _common import FRONTEND, Guard, strip_comments_and_strings, B, G, R, X  # noqa: E402

SRC = FRONTEND / "src"

# Lapisan pop-up: `fixed inset-0` + latar gelap. Keduanya wajib, supaya panel
# "fixed" biasa (mis. bilah melayang) tidak ikut dituduh.
OVERLAY_CLASS = re.compile(r"className=\"[^\"]*fixed\s+inset-0[^\"]*bg-black/", re.S)
# Nama komponen pop-up yang lazim di repo ini.
POPUP_COMPONENT = re.compile(
    r"^<([A-Z]\w*(?:Modal|Picker|Finder|Sheet|Drawer))\b")
# Render bersyarat: `{open && …` · `{open ? …`
COND_RENDER = re.compile(r"\{\s*(\w+)\s*(?:&&|\?)\s*")


def _tepat_sesudah(stripped: str, pos: int) -> str:
    """Potongan sesudah `&&`/`?` dengan spasi & tanda kurung pembuka dibuang.

    Penting: penilaian HARUS pada elemen yang PERSIS menyusul syaratnya. Versi
    pertama penjaga ini memakai jendela 400 karakter, dan itu membuatnya menuduh
    tiga berkas yang SUDAH benar — `{value ? valueName : label}` (teks tombol)
    dianggap render pop-up hanya karena pop-up ber-portal muncul beberapa baris
    di bawahnya. Pelajaran INV-UI-05: penjaga yang menuduh palsu akan diabaikan.
    """
    t = stripped[pos: pos + 600].lstrip()
    while t.startswith("("):
        t = t[1:].lstrip()
    return t


def _buang_komentar(src: str) -> str:
    """Kosongkan KOMENTAR saja — literal string TETAP utuh.

    Dibutuhkan karena penanda lapisan pop-up hidup DI DALAM string
    (`className="fixed inset-0 … bg-black/50"`), jadi `strip_comments_and_strings`
    tidak bisa dipakai untuk aturan B. Tanpa pembuang komentar ini, penjaga
    menuduh berkasnya sendiri: catatan dokumentasi yang menulis kata `<label>`
    dihitung sebagai elemen label sungguhan (terjadi pada tiga berkas pemilih
    yang justru SUDAH diperbaiki).
    """
    out = []
    i, n = 0, len(src)
    while i < n:
        c, nxt = src[i], (src[i + 1] if i + 1 < n else "")
        if c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if c == "/" and nxt == "*":
            while i < n and not (src[i] == "*" and i + 1 < n and src[i + 1] == "/"):
                out.append("\n" if src[i] == "\n" else " ")
                i += 1
            out.append("  ")
            i += 2
            continue
        if c in ("'", '"', "`"):
            quote = c
            out.append(c)
            i += 1
            while i < n:
                out.append(src[i])
                if src[i] == "\\":
                    i += 2
                    if i - 1 < n:
                        out.append(src[i - 1])
                    continue
                if src[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _is_picker_file(src: str, stripped: str) -> bool:
    """Pemicu + pop-up dalam satu berkas (lihat aturan A)."""
    has_trigger = "triggerTestId" in stripped
    has_overlay = bool(OVERLAY_CLASS.search(_buang_komentar(src)))
    return has_trigger and has_overlay


def analyze_text(src: str) -> List[str]:
    """Kembalikan daftar alasan pelanggaran (kosong = hijau). Fungsi murni → bisa di-self-test."""
    out: List[str] = []
    stripped = strip_comments_and_strings(src)

    # ── Aturan A — pemilih wajib ber-portal ───────────────────────────────────
    if _is_picker_file(src, stripped):
        for m in COND_RENDER.finditer(stripped):
            tail = _tepat_sesudah(stripped, m.end())
            if tail.startswith("createPortal("):
                continue                      # sudah benar: pop-up keluar dari <label>
            comp = POPUP_COMPONENT.match(tail)
            if not comp:
                continue                      # yang dirender bukan pop-up (teks/lencana)
            out.append(
                f"pop-up <{comp.group(1)}> dirender langsung (`{{{m.group(1)} && …}}`) di "
                f"berkas pemilih ber-`triggerTestId`. Komponen ini dipakai di dalam "
                f"<Field> = <label>, jadi klik memilih akan DITERUSKAN peramban ke tombol "
                f"pemicunya dan pop-up terbuka kembali. Bungkus dengan "
                f"createPortal(<{comp.group(1)} … />, document.body).")

    # ── Aturan B — `<label>` mentah tidak boleh memuat lapisan pop-up ─────────
    kode = _buang_komentar(src)
    for m in re.finditer(r"<label\b", kode):
        end = kode.find("</label>", m.end())
        blok = kode[m.start(): end if end != -1 else len(kode)]
        if OVERLAY_CLASS.search(blok):
            out.append(
                "ada lapisan pop-up (`fixed inset-0 … bg-black/…`) DI DALAM blok <label>. "
                "Aktivasi label diteruskan ke kontrol yang dilabeli, jadi pop-up ini akan "
                "terbuka kembali setiap kali penggunanya mengklik isinya. Render lewat "
                "createPortal ke document.body (atau keluarkan dari <label>).")
    return out


def scan() -> Tuple[Dict[str, List[str]], int]:
    hasil: Dict[str, List[str]] = {}
    diperiksa = 0
    for path in sorted(SRC.rglob("*.jsx")):
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        stripped = strip_comments_and_strings(src)
        if _is_picker_file(src, stripped) or "<label" in src:
            diperiksa += 1
        v = analyze_text(src)
        if v:
            hasil[str(path.relative_to(SRC))] = v
    return hasil, diperiksa


def main() -> int:
    g = Guard("INV-UI-09", "pemilih (pemicu+pop-up) wajib ber-portal · pop-up bukan anak <label>")
    hasil, diperiksa = scan()
    pickers = [str(p.relative_to(SRC)) for p in sorted(SRC.rglob("*.jsx"))
               if _is_picker_file(p.read_text(encoding="utf-8", errors="ignore"),
                                  strip_comments_and_strings(
                                      p.read_text(encoding="utf-8", errors="ignore")))]
    g.bump(diperiksa)
    print(f"  berkas diperiksa: {diperiksa} · komponen pemilih (pemicu+pop-up): "
          f"{len(pickers)} → {', '.join(pickers) if pickers else '—'}")
    for rel, alasan in sorted(hasil.items()):
        for a in alasan:
            g.add(f"{rel} — {a}")
    return g.finish()


# ─────────────────────────────────────────────────────────────────────────────
# SELF-TEST — penjaga wajib bisa MEMERAH pada pelanggaran buatan, dan wajib
# TIDAK menuduh bentuk yang sah (pelajaran INV-UI-05 & ux_audit: penjaga yang
# menuduh palsu akan diabaikan, lalu berhenti menjaga apa pun).
# ─────────────────────────────────────────────────────────────────────────────
OVERLAY = ('<div className="fixed inset-0 z-[200] flex items-center justify-center '
           'bg-black/50 p-4">')


def _picker(render: str, extra_import: str = "") -> str:
    return (f"import {{ useState }} from 'react';\n{extra_import}"
            "export default function FooSelect({ triggerTestId = 'foo-trigger' }) {\n"
            "  const [open, setOpen] = useState(false);\n"
            "  return (<>\n"
            "    <button type=\"button\" data-testid={triggerTestId} "
            "onClick={() => setOpen(true)} className=\"field\">pilih…</button>\n"
            f"    {render}\n"
            "  </>);\n}\n"
            f"function FooPickerModal() {{ return ({OVERLAY}<div/></div>); }}\n")


def self_test() -> int:
    kasus: List[Tuple[str, bool]] = []

    def cek(nama: str, benar: bool):
        kasus.append((nama, benar))

    # ── Lapis 1 — HARUS MEMERAH ───────────────────────────────────────────────
    cek("pemilih merender pop-up langsung (`{open && <FooPickerModal/>}`) → MERAH",
        len(analyze_text(_picker("{open && <FooPickerModal onClose={x} />}"))) == 1)
    cek("bentuk ternary juga tertangkap",
        len(analyze_text(_picker("{open ? <FooPickerModal /> : null}"))) == 1)
    cek("dibungkus tanda kurung pun tetap tertangkap",
        len(analyze_text(_picker("{open && (\n      <FooPickerModal />\n    )}"))) == 1)
    cek("lapisan pop-up MENTAH di dalam <label> → MERAH",
        len(analyze_text("function V(){return (<label className=\"block\">"
                         f"<span>Warna</span>{OVERLAY}<div/></div></label>);}}")) == 1)

    # ── Lapis 2 — TIDAK boleh menuduh palsu ───────────────────────────────────
    cek("pemilih memakai createPortal → hijau",
        analyze_text(_picker("{open && createPortal(<FooPickerModal />, document.body)}",
                             "import { createPortal } from 'react-dom';\n")) == [])
    cek("berkas pop-up MURNI (tanpa pemicu ber-triggerTestId) → tidak dituduh",
        analyze_text("export default function BarModal({ onClose }) { return ("
                     f"{OVERLAY}<div/></div>); }}") == [])
    cek("pemicu TANPA pop-up sendiri (mis. KNSelect/Radix) → tidak dituduh",
        analyze_text("export default function KNSelect({ triggerTestId }) { return ("
                     "<button data-testid={triggerTestId} />); }") == [])
    cek("`triggerTestId` hanya disebut di KOMENTAR → tidak dituduh",
        analyze_text("/* triggerTestId dipakai komponen lain */\n"
                     "export default function BarModal(){ return ("
                     f"{OVERLAY}<div/></div>); }}") == [])
    cek("`triggerTestId` hanya di dalam STRING → tidak dituduh",
        analyze_text("const doc = 'triggerTestId';\nexport default function BarModal(){"
                     f" return ({OVERLAY}<div/></div>); }}") == [])
    cek("<label> berisi input biasa (tanpa lapisan pop-up) → hijau",
        analyze_text("function V(){return (<label className=\"block\">"
                     "<span>Nama</span><input className=\"field\"/></label>);}") == [])
    cek("lapisan pop-up di dalam <div> (bukan <label>) → hijau",
        analyze_text(f"function V(){{return (<div>{OVERLAY}<div/></div></div>);}}") == [])
    cek("panel `fixed` tanpa latar gelap (bilah melayang) → bukan pop-up, hijau",
        analyze_text("function V(){return (<label><div className=\"fixed inset-0 "
                     "pointer-events-none\"/></label>);}") == [])
    cek("pemilih yang merender LENCANA bersyarat (bukan pop-up) → hijau",
        analyze_text(_picker("{open && <span className=\"badge\">buka</span>}")) == [])
    cek("kata `<label>` yang hanya ada di KOMENTAR tidak dihitung elemen label",
        analyze_text("/* dipakai di dalam <Field> yang merender <label> */\n"
                     "export default function BarModal(){ return ("
                     f"{OVERLAY}<div/></div>); }}") == [])
    cek("pemilih ber-portal YANG punya catatan `<label>` di komentarnya → hijau",
        analyze_text(_picker("{open && createPortal(<FooPickerModal />, document.body)}",
                             "// pop-up keluar dari <label> lewat portal\n"
                             "import { createPortal } from 'react-dom';\n")) == [])

    # ── Lapis 3 — kode NYATA repo ini harus hijau ─────────────────────────────
    nyata, _ = scan()
    cek(f"kode nyata saat ini HIJAU ({len(nyata)} berkas melanggar)", not nyata)

    gagal = sum(0 if ok else 1 for _n, ok in kasus)
    print(f"{B}== SELF-TEST INV-UI-09 (pemilih wajib ber-portal) =={X}")
    for nama, ok in kasus:
        print(f"  [{G + 'PASS' + X if ok else R + 'FAIL' + X}] {nama}")
    if gagal:
        print(f"{R}{B}  SELF-TEST MERAH ({gagal} kasus).{X}")
        if nyata:
            for rel, alasan in sorted(nyata.items()):
                print(f"    ✗ {rel}: {alasan[0][:120]}")
    else:
        print(f"{G}  HIJAU — penjaga menangkap pop-up yang lahir di dalam <label> "
              f"(3 bentuk render) tanpa menuduh pop-up murni, pemicu ber-portal, "
              f"komentar, string, maupun panel melayang.{X}")
    return gagal


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(1 if self_test() else 0)
    raise SystemExit(main())
