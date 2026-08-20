#!/usr/bin/env python3
"""INV-UI-05 — **TOMBOL "BUAT" HARUS MEMUNCULKAN POP-UP, BUKAN FORM MENYELIP**

MASALAH YANG DIUKUR (FASE P4, `PERF_UX_AUDIT.md`)
================================================
Tombol "+ Buat/Tambah" di layar-layar KN berperilaku TIGA cara berbeda:
  1. **modal**   — memunculkan pop-up (yang diinginkan pemilik: konsisten & tak menggeser tabel),
  2. **inline**  — menyelipkan form di tengah halaman sehingga daftar data terdorong ke bawah;
                   pengguna kehilangan konteks & sering tak sadar formnya terbuka di bawah lipatan,
  3. **navigate**— pindah halaman penuh (sah untuk alur kompleks, mis. Pesanan Khusus).
Ketidakkonsistenan ini yang membuat orang mengira tombolnya "tidak berfungsi".

CARA MENILAI (statik, tanpa backend)
------------------------------------
Untuk setiap berkas `frontend/src/features/**/*.jsx`:
  · kumpulkan `useState` → pasangan (state, setter);
  · cari tombol yang teksnya menyatakan MEMBUAT (Buat/Tambah/Baru/`<Plus`) dan meng-`set…(true)`;
  · lihat bagaimana state itu DIRENDER: bila blok render memuat penanda pop-up
    (`FormModal`, `modal-overlay`, `fixed inset-0`, `role="dialog"`, `m-sheet-wrap`) → **modal**;
    bila tidak → **inline**;
  · tombol yang memanggil navigasi (`onNavigate`/`setView`/…) → **navigate**.

ATURAN GATE
-----------
  A. Tidak boleh ada create **inline** baru: setiap berkas inline WAJIB terdaftar di
     `INLINE_DIBOLEHKAN` **dengan alasan tertulis** (mis. "form di dalam wizard").
  B. Setiap create **navigate** WAJIB terdaftar di `NAVIGATE_DISETUJUI` dengan alasan
     (keputusan pemilik: alur kompleks tetap halaman) — supaya "pindah halaman" adalah
     pilihan sadar, bukan kebetulan.
  C. Tombol create yang meng-`set…(true)` tetapi state-nya TIDAK PERNAH dirender =
     **tombol mati** (klik → tak terjadi apa pun) → MERAH.

Usage:
    python scripts/audit_create_modal.py            # gate
    python scripts/audit_create_modal.py -v         # + rincian tiap tombol
    python scripts/audit_create_modal.py --self-test # bukti-merah (tanpa berkas nyata)
"""
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "guardrails"))
from _common import Guard, G, R, Y, B, X  # noqa: E402

SRC = ROOT / "frontend" / "src"
FEATURES = SRC / "features"

#: teks/penanda yang menyatakan tombol ini MEMBUAT sesuatu.
CREATE_TEXT = re.compile(r"(Buat\b|Tambah\b|Baru\b|<Plus\b|Ajukan\b)")
#: penanda blok render berupa POP-UP.
MODAL_MARKERS = ("FormModal", "modal-overlay", "fixed inset-0", 'role="dialog"',
                 "m-sheet-wrap", "<Dialog", "ConfirmModal")
#: Komponen anak yang JELAS pop-up dari namanya (`<SupplierFormModal …>`, `<MakloonWizard …>`).
#: Tanpa ini penjaga menuduh PALSU layar yang justru sudah benar — dan penjaga yang menuduh
#: palsu akan dimatikan orang. Terukur saat menulis gate ini: 7 layar (CustomerList, RFQ,
#: Blanket PO, Landed Cost, Vendor Bills, Permintaan Internal, MobileQuickView) sudah memakai
#: `<XxxModal open={state}>` tetapi tertuduh "inline" hanya karena nama komponennya berada
#: SEBELUM posisi `open={state}` yang dijadikan titik awal jendela pembacaan.
MODAL_COMPONENT = re.compile(r"<[A-Z][A-Za-z0-9]*(?:Modal|Dialog|Drawer|Sheet|Wizard)\b")
#: Nama state yang memang berarti "pintu terbuka" (bukan wadah data form).
STATE_TOGGLE = re.compile(r"^(show|open|is|modal|creating|editing|adding|wizard|new)",
                          re.IGNORECASE)
NAV_CALL = re.compile(r"\b(onNavigate|setActiveView|setView|navigate|onOpenDocument)\s*\(")

#: Penanda "blok ini memang FORM" (ada isian yang bisa diketik/dipilih).
FORM_MARKERS = re.compile(r"<input|className=\"field\"|<textarea|<KNSelect|<Input\b|<Select\b")

#: Nama komponen anak yang WAJAR menampung form (bukan tabel/kartu informasi).
CHILD_FORMISH = re.compile(r"<([A-Z][A-Za-z0-9]*(?:Form|Fields|Editor|Panel|Card|Box|Entry))\b")

#: Semua komponen anak yang dirender di blok (untuk ditelusuri ke berkasnya).
CHILD_ANY = re.compile(r"<([A-Z][A-Za-z0-9]*)\b")

_COMP_CACHE: Dict[str, str] = {}


def component_source(name: str) -> str:
    """Isi berkas komponen `name` (`Name.jsx`), '' bila tak ditemukan.

    KENAPA PERLU MENELUSURI ANAK (celah nyata yang ditemukan sesi P5, terukur):
    `InventoryStockView` membuka form stok awal lewat `<InitialStockForm …/>` — sebuah
    form INLINE yang menyelipkan kartu di tengah halaman. Penjaga versi pertama
    **tidak melihatnya**: (1) nama komponennya berakhiran "Form", bukan "Modal", jadi
    tidak dianggap pop-up — itu benar; tetapi (2) saringan "apakah blok ini form?"
    mencari `<input`/`<KNSelect` **di berkas induk**, sementara seluruh isiannya berada
    di berkas ANAK. Akibatnya blok itu disimpulkan "bukan form" lalu dilewati diam-diam,
    dan gate melaporkan **inline 0** padahal masih ada satu form menyelip.
    Pelajarannya sama dengan kelas bug INV-IC-04: penjaga yang hanya memeriksa apa yang
    kelihatan di permukaan tidak bisa memerah untuk hal yang disembunyikan satu lapis.
    """
    if name in _COMP_CACHE:
        return _COMP_CACHE[name]
    teks = ""
    for cand in SRC.rglob(f"{name}.jsx"):
        teks = cand.read_text(encoding="utf-8", errors="ignore")
        break
    _COMP_CACHE[name] = teks
    return teks


def blok_punya_form(blok: str) -> bool:
    """Blok render ini benar-benar FORM? Menelusuri satu lapis ke komponen anak."""
    if FORM_MARKERS.search(blok):
        return True
    for m in CHILD_FORMISH.finditer(blok):
        if FORM_MARKERS.search(component_source(m.group(1))):
            return True
    return False


def blok_punya_modal(blok: str) -> bool:
    """Blok render ini pop-up? Penanda langsung, ATAU komponen anaknya yang pop-up.

    Menelusuri anak juga mencegah tuduhan PALSU arah sebaliknya: komponen bernama
    `GRCatchWeightModal`/`PeggingModal` sudah tertangkap dari namanya, tetapi anak yang
    namanya netral (mis. `CheckoutDrawerBody`) bisa saja membungkus `modal-overlay`
    di dalam berkasnya sendiri.
    """
    if any(mk in blok for mk in MODAL_MARKERS) or MODAL_COMPONENT.search(blok):
        return True
    for m in CHILD_ANY.finditer(blok):
        isi = component_source(m.group(1))
        if isi and any(mk in isi for mk in MODAL_MARKERS):
            return True
    return False

#: Create INLINE yang memang dibiarkan — WAJIB beralasan (dinilai orang, bukan dibisukan).
INLINE_DIBOLEHKAN: Dict[str, str] = {}

#: Create NAVIGATE yang disetujui pemilik (alur kompleks tetap halaman penuh).
NAVIGATE_DISETUJUI: Dict[str, str] = {
    "features/home/SalesHome.jsx":
        "Buat pesanan penjualan = alur panjang (pilih pelanggan → roll → harga → ongkos → "
        "syarat bayar). Keputusan pemilik: alur create kompleks tetap halaman.",
    "features/inventory/CycleCount.jsx":
        "Sesi stock opname = pekerjaan berjam-jam di gudang (scan per roll), bukan satu form.",
    "features/pettycash/CashAdvancesView.jsx":
        "Pengajuan dana punya banyak baris rincian + lampiran → halaman penuh.",
    "features/pettycash/SettlementsView.jsx":
        "Pertanggungjawaban mencocokkan realisasi vs pengajuan baris demi baris → halaman penuh.",
    "features/purchasing/PurchaseRequisitions.jsx":
        "PR multi-baris + saran reorder + pemilihan supplier → halaman penuh.",
    "features/sales/SpecialOrders.jsx":
        "Pesanan khusus (MTO) = spesifikasi desain + termin + jadwal produksi → halaman penuh "
        "(disepakati eksplisit di PERF_UX_AUDIT.md §P4).",
}


def read_files() -> List[Tuple[str, str]]:
    out = []
    for f in sorted(FEATURES.rglob("*.jsx")):
        out.append((str(f.relative_to(SRC)), f.read_text(encoding="utf-8", errors="ignore")))
    return out


def state_setters(src: str) -> Dict[str, str]:
    """`setter → state` dari seluruh `useState` di berkas."""
    return {m.group(2): m.group(1) for m in
            re.finditer(r"const\s*\[\s*(\w+)\s*,\s*(set\w+)\s*\]\s*=\s*useState", src)}


def render_kind(src: str, state: str) -> str:
    """Bagaimana `state` dirender: 'modal' | 'inline' | 'none'.

    Jendela pembacaan dimulai **300 karakter SEBELUM** kecocokan supaya nama komponen
    pop-up yang ditulis lebih dulu (`<CustomerFormModal open={showForm} …>`) ikut terbaca.
    Pola `if (state) return <Form…/>` dihitung **inline** (form menukar seluruh halaman —
    daftar datanya hilang, konteks pengguna ikut hilang).
    """
    st = re.escape(state)
    kinds = []
    pola = (rf"\{{\s*{st}\s*&&", rf"\{{\s*{st}\?\.\w+\s*&&", rf"open=\{{\s*{st}\b",
            rf"\b{st}\s*\?\s*<", rf"show=\{{\s*{st}\b", rf"isOpen=\{{\s*{st}\b",
            rf"open=\{{\s*!!\s*{st}\b")
    for p in pola:
        for m in re.finditer(p, src):
            awal = max(0, m.start() - 300)
            blok = src[awal: m.start() + 2500]
            kinds.append("modal" if blok_punya_modal(blok) else "inline")
    for m in re.finditer(rf"if\s*\(\s*{st}\s*\)\s*\{{", src):
        kinds.append("inline")   # form menukar halaman
    if not kinds:
        return "none"
    return "modal" if "modal" in kinds and "inline" not in kinds else (
        "inline" if "inline" in kinds else "modal")


def scan(files: List[Tuple[str, str]]) -> Dict[str, List[tuple]]:
    """→ {'modal'|'inline'|'navigate'|'mati': [(berkas, baris, testid, state)]}"""
    hasil: Dict[str, List[tuple]] = {"modal": [], "inline": [], "navigate": [], "mati": []}
    for rel, src in files:
        setters = state_setters(src)
        terlihat = set()
        for m in re.finditer(r"<(button|Button)\b[\s\S]{0,1600}?</\1>", src):
            blk = m.group(0)
            if not CREATE_TEXT.search(blk):
                continue
            baris = src[:m.start()].count("\n") + 1
            tid = re.search(r'data-testid="([^"]+)"', blk)
            tid = tid.group(1) if tid else "(tanpa-testid)"
            if NAV_CALL.search(blk):
                hasil["navigate"].append((rel, baris, tid, ""))
                continue
            for setter, state in setters.items():
                if not re.search(rf"\b{setter}\s*\(\s*(true|!\s*{state}\b|\{{)", blk):
                    continue
                # `setForm({...})` bukan "membuka pintu" — itu wadah DATA form. Tanpa
                # saringan ini penjaga menuduh palsu tombol yang justru sudah benar
                # (terukur: `CategoryManager` & `CashManagementView` mengisi data form).
                if not STATE_TOGGLE.search(state) and not re.search(
                        rf"\b{setter}\s*\(\s*(true|!\s*{state}\b)", blk):
                    continue
                kind = render_kind(src, state)
                terlihat.add(state)
                hasil[{"modal": "modal", "inline": "inline", "none": "mati"}[kind]].append(
                    (rel, baris, tid, state))
                break
        # ── SAPUAN KEDUA: form yang dibuka LEWAT FUNGSI (bukan setter langsung di tombol).
        # Tanpa ini `onClick={() => bukaForm()}` membuat form inline lolos dari penjaga.
        for setter, state in setters.items():
            if state in terlihat or not STATE_TOGGLE.search(state):
                continue
            if not re.search(rf"\b{setter}\s*\(\s*true\s*\)", src):
                continue
            if render_kind(src, state) != "inline":
                continue
            # hanya hitung bila blok yang dibuka memang FORM (ada input/field ATAU
            # komponen anak yang isinya form), supaya panel/informasi yang dibuka-tutup
            # tidak dituduh sebagai form create — dan supaya form yang isiannya dipindah
            # ke berkas anak tidak lolos diam-diam (celah yang ditemukan sesi P5).
            m2 = re.search(rf"\{{\s*{re.escape(state)}\s*&&", src)
            blok = src[m2.start(): m2.start() + 2500] if m2 else ""
            if not blok_punya_form(blok):
                continue
            baris = src[:(m2.start() if m2 else 0)].count("\n") + 1
            hasil["inline"].append((rel, baris, "(dibuka lewat fungsi)", state))
    return hasil


def check(g: Guard, hasil: Dict[str, List[tuple]],
          inline_ok: Dict[str, str], nav_ok: Dict[str, str]) -> None:
    for rel, baris, tid, state in hasil["inline"]:
        g.bump()
        alasan = (inline_ok.get(rel) or "").strip()
        if not alasan:
            g.add(f"{rel}:{baris} tombol create `{tid}` membuka form **INLINE** (state "
                  f"`{state}`) → form menyelip di tengah halaman & mendorong daftar ke bawah. "
                  f"Pakai `FormModal`, atau daftarkan di INLINE_DIBOLEHKAN dengan alasan.")
        elif len(alasan) < 20:
            g.add(f"{rel} dibebaskan tanpa alasan yang bisa dinilai orang.")
    for rel, baris, tid, _s in hasil["navigate"]:
        g.bump()
        alasan = (nav_ok.get(rel) or "").strip()
        if not alasan:
            g.add(f"{rel}:{baris} tombol create `{tid}` PINDAH HALAMAN tanpa keputusan "
                  f"tercatat → daftarkan di NAVIGATE_DISETUJUI (alur kompleks) atau ubah "
                  f"jadi pop-up.")
        elif len(alasan) < 20:
            g.add(f"{rel} (navigate) dibebaskan tanpa alasan yang bisa dinilai orang.")
    for rel, baris, tid, state in hasil["mati"]:
        g.bump()
        g.add(f"{rel}:{baris} TOMBOL MATI: `{tid}` menyalakan `{state}` tetapi state itu "
              f"tidak pernah dirender → klik tidak memunculkan apa pun.")


def self_test() -> int:
    kasus = []

    def jalankan(nama, hasil, inline_ok, nav_ok, harap):
        g = Guard("INV-UI-05", "self-test")
        g.violations, g.checks = [], 0
        check(g, hasil, inline_ok, nav_ok)
        kasus.append((nama, harap, len(g.violations)))

    kosong = {"modal": [], "inline": [], "navigate": [], "mati": []}
    jalankan("semua create sudah modal → hijau",
             {**kosong, "modal": [("a.jsx", 1, "t", "s")]}, {}, {}, 0)
    jalankan("create INLINE tanpa alasan → merah",
             {**kosong, "inline": [("a.jsx", 9, "add-btn", "showForm")]}, {}, {}, 1)
    jalankan("create INLINE dengan alasan panjang → hijau",
             {**kosong, "inline": [("a.jsx", 9, "add-btn", "showForm")]},
             {"a.jsx": "Form ini bagian dari wizard bertahap."}, {}, 0)
    jalankan("create NAVIGATE tanpa keputusan tercatat → merah",
             {**kosong, "navigate": [("b.jsx", 3, "go-btn", "")]}, {}, {}, 1)
    jalankan("create NAVIGATE disetujui pemilik → hijau",
             {**kosong, "navigate": [("b.jsx", 3, "go-btn", "")]}, {},
             {"b.jsx": "Alur kompleks: banyak baris & lampiran, tetap halaman."}, 0)
    jalankan("TOMBOL MATI (state tak pernah dirender) → merah",
             {**kosong, "mati": [("c.jsx", 5, "dead-btn", "showX")]}, {}, {}, 1)
    jalankan("pembebasan tanpa alasan (terlalu pendek) → merah",
             {**kosong, "inline": [("a.jsx", 9, "add-btn", "showForm")]},
             {"a.jsx": "ya"}, {}, 1)

    gagal = 0
    print(f"{B}== SELF-TEST INV-UI-05 (penjaga create-modal harus bisa MEMERAH) =={X}")
    for nama, harap, got in kasus:
        ok = harap == got
        gagal += 0 if ok else 1
        print(f"  [{G + 'PASS' + X if ok else R + 'FAIL' + X}] {nama}  "
              f"(harap={harap}, dapat={got})")

    # ── LAPIS 2 — PENGENAL (scanner) -----------------------------------------
    # Celah nyata yang ditemukan sesi P5: form INLINE yang isiannya dipindah ke berkas
    # ANAK (`<InitialStockForm/>`, `<POCreateForm/>`, `<PriceApprovalForm/>`) LOLOS dari
    # penjaga, sehingga gate melaporkan "inline 0" padahal masih ada 3. Kasus di bawah
    # menguji pengenalnya langsung — termasuk arah sebaliknya (jangan menuduh palsu).
    _COMP_CACHE["PalsuAnakForm"] = '<input className="field" />'
    _COMP_CACHE["AnakTabelPalsu"] = "<table><tbody /></table>"
    _COMP_CACHE["AnakNetralTapiModal"] = 'return <div className="modal-overlay">isi</div>;'
    scan_kasus = [
        ("isian ADA di berkas induk → FORM", blok_punya_form('<input className="field" />'), True),
        ("isian dipindah ke berkas ANAK → tetap FORM (celah P5 tertutup)",
         blok_punya_form("<PalsuAnakForm a={1} />"), True),
        ("anak berisi TABEL → bukan form (anti tuduh palsu)",
         blok_punya_form("<AnakTabelPalsu />"), False),
        ("anak bernama netral tapi isinya modal-overlay → MODAL (anti tuduh palsu)",
         blok_punya_modal("<AnakNetralTapiModal />"), True),
        ("kartu biasa tanpa penanda pop-up → bukan modal",
         blok_punya_modal('<div className="section-card" />'), False),
    ]
    for nama, got, harap in scan_kasus:
        ok = bool(got) == bool(harap)
        gagal += 0 if ok else 1
        print(f"  [{G + 'PASS' + X if ok else R + 'FAIL' + X}] {nama}  "
              f"(harap={harap}, dapat={bool(got)})")

    print(f"{G}  HIJAU — penjaga terbukti menuduh form yang menyelip.{X}" if not gagal
          else f"{R}{B}  SELF-TEST MERAH.{X}")
    return gagal


def main(verbose: bool = False) -> int:
    g = Guard("INV-UI-05", "tombol Buat memunculkan pop-up yang konsisten")
    hasil = scan(read_files())
    print(f"  create → modal: {len(hasil['modal'])} · inline: {len(hasil['inline'])} · "
          f"navigate: {len(hasil['navigate'])} · tombol mati: {len(hasil['mati'])}")
    if verbose:
        for kind in ("inline", "navigate", "mati", "modal"):
            for rel, baris, tid, state in hasil[kind]:
                print(f"    {kind:8s} {rel}:{baris} {tid} {state}")
    check(g, hasil, INLINE_DIBOLEHKAN, NAVIGATE_DISETUJUI)
    return g.finish()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(1 if self_test() else 0)
    sys.exit(main(verbose=("-v" in sys.argv)))
