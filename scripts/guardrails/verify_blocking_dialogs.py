#!/usr/bin/env python3
"""INV-UI-06 — **DIALOG BAWAAN PERAMBAN (`alert`/`confirm`/`prompt`) DILARANG**

MASALAH YANG DICEGAH (FASE P5, `PERF_UX_AUDIT.md` — terukur, bukan selera)
=========================================================================
Sebelum fase ini ada **61 dialog bawaan peramban** di `frontend/src`:
`alert()` **36×** (6 berkas, 30 di antaranya di layar gudang), `confirm()` **21×**
(16 berkas), `prompt()` **4×**. Kenapa itu bukan sekadar "kurang cantik":

  1. **Memblokir seluruh thread JavaScript.** Selama kotaknya terbuka tidak ada yang
     bisa dirender — termasuk indikator "sedang menyimpan". Operator gudang yang
     memegang pemindai menyimpulkan aplikasi hang lalu menekan tombol dua kali.
  2. **Tidak bisa diberi konteks.** Hanya teks polos: tak ada nomor dokumen tebal, tak
     ada nominal ber-format, tak ada warna bahaya. Untuk "Batalkan penerimaan
     KW-00007 (Rp 12.500.000)?" justru konteks itu yang menentukan keputusan.
  3. **Tidak bisa menuntut alasan.** `confirm()` hanya Ya/Batal, `prompt()` bisa diisi
     spasi & tak bisa divalidasi — padahal aksi yang membalik uang/stok wajib beralasan.
     Di `AccountList` `prompt()` bahkan dipakai meminta **kata sandi tanpa penyamaran**.
  4. **Bisa dibungkam permanen.** Peramban menawarkan "jangan tampilkan dialog lagi";
     sesudah itu `confirm()` mengembalikan `false` **tanpa bertanya** → tombol tampak
     mati tanpa sebab yang bisa dilihat pengguna. Di sebagian iOS/PWA sudah diabaikan.
  5. **Tak bisa diuji.** Agen uji & Playwright tidak melihat DOM apa pun, sehingga alur
     kritis (batalkan transfer, void kwitansi) tidak bisa diverifikasi otomatis.

GANTINYA (standar tunggal)
--------------------------
  · **galat/gagal** → `components/ErrorNotice` — bilah MENEMPEL, ditutup manual
    (keputusan pemilik: operator gudang tidak boleh melewatkannya);
  · **berhasil**    → `utils/feedback.notifySuccess()` → toast yang hilang sendiri;
  · **pertanyaan**  → `services/confirmService.askConfirm / askReason / askText`
    (satu `<ConfirmHost/>` di root; `askReason` menuntut alasan tertulis,
    `askText` mendukung `inputType: "password"`).

ATURAN GATE
-----------
  A. Tidak boleh ada pemanggilan `alert(`/`confirm(`/`prompt(` bawaan peramban
     (dengan atau tanpa `window.`) di `frontend/src`. Pengecualian WAJIB terdaftar di
     `DIBOLEHKAN` **dengan alasan tertulis** yang bisa dinilai orang.
  B. `<ConfirmHost/>` WAJIB ter-mount di akar aplikasi (`src/index.js`). Tanpa itu
     `askConfirm()` tidak menampilkan apa pun → seluruh tombol "hapus/batalkan" akan
     tampak mati. Penjaga ini menutup mode gagal yang paling senyap dari penggantinya.

KENAPA KOMENTAR & STRING DIBERSIHKAN LEBIH DULU (pelajaran sesi ini)
--------------------------------------------------------------------
Pengukuran pertama dengan `grep` polos menghasilkan **dua tuduhan palsu**:
  · `label: "Instan — 1 pesan per alert (real-time)"` → kata "alert" DI DALAM STRING;
  · `async function confirm() { … }` di `ReturnSettleModal` → fungsi yang KEBETULAN
    bernama `confirm`, sama sekali bukan dialog peramban.
Penjaga yang menuduh palsu akan dimatikan orang, jadi: komentar & literal string
dibuang lebih dulu, dan nama yang **dideklarasikan di berkas itu sendiri**
(`function confirm`, `const prompt = …`) dianggap milik berkas — bukan milik peramban.

Usage:
    python scripts/guardrails/verify_blocking_dialogs.py
    python scripts/guardrails/verify_blocking_dialogs.py -v
    python scripts/guardrails/verify_blocking_dialogs.py --self-test
"""
import os
import re
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from _common import FRONTEND, Guard, strip_comments_and_strings, G, R, B, X  # noqa: E402

SRC = FRONTEND / "src"

NAMES = ("alert", "confirm", "prompt")

#: Pemanggilan telanjang: `alert(`, `confirm(`. `(?<![\w.$])` menolak `askConfirm(`
#: (didahului huruf) dan `obj.alert(` (didahului titik).
CALL_BARE = re.compile(r"(?<![\w.$])(alert|confirm|prompt)\s*\(")
#: Bentuk `window.alert(` — di sini titik memang sah, jadi dicocokkan terpisah.
CALL_WINDOW = re.compile(r"(?<![\w.$])window\s*\.\s*(alert|confirm|prompt)\s*\(")
#: Nama yang DIDEKLARASIKAN di berkas itu sendiri → bukan dialog peramban.
DECL = re.compile(r"(?:function\s+|const\s+|let\s+|var\s+)(alert|confirm|prompt)\b")

#: Pengecualian — WAJIB beralasan (dinilai orang, bukan dibisukan).
DIBOLEHKAN: Dict[str, str] = {}


def find_calls(src: str) -> List[Tuple[int, str]]:
    """→ [(nomor_baris, nama)] pemanggilan dialog peramban pada satu berkas."""
    bersih = strip_comments_and_strings(src)
    lokal = {m.group(1) for m in DECL.finditer(bersih)}
    hits: List[Tuple[int, str]] = []
    seen = set()
    for rx in (CALL_WINDOW, CALL_BARE):
        for m in rx.finditer(bersih):
            nama = m.group(1)
            # `window.alert(` juga cocok dengan CALL_BARE pada posisi berbeda; dedupe
            # berdasarkan posisi nama supaya satu pemanggilan tidak dihitung dua kali.
            pos = m.start(1)
            if pos in seen:
                continue
            seen.add(pos)
            if nama in lokal and rx is CALL_BARE:
                continue          # fungsi/variabel milik berkas ini sendiri
            hits.append((bersih[:pos].count("\n") + 1, nama))
    return sorted(hits)


def scan() -> Dict[str, List[Tuple[int, str]]]:
    hasil: Dict[str, List[Tuple[int, str]]] = {}
    for path in sorted(list(SRC.rglob("*.jsx")) + list(SRC.rglob("*.js"))):
        rel = str(path.relative_to(SRC))
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        hits = find_calls(src)
        if hits:
            hasil[rel] = hits
    return hasil


def check_calls(g: Guard, hasil: Dict[str, List[Tuple[int, str]]],
                dibolehkan: Dict[str, str]) -> None:
    for rel, hits in sorted(hasil.items()):
        alasan = (dibolehkan.get(rel) or "").strip()
        for baris, nama in hits:
            g.bump()
            if not alasan:
                ganti = {
                    "alert": "`ErrorNotice` (galat) atau `notifySuccess()` (berhasil)",
                    "confirm": "`askConfirm()` / `askReason()` (services/confirmService)",
                    "prompt": "`askReason()` / `askText()` (services/confirmService)",
                }[nama]
                g.add(f"{rel}:{baris} memakai `{nama}()` bawaan peramban → memblokir "
                      f"seluruh halaman, tak bisa diberi konteks/alasan, bisa dibungkam "
                      f"permanen oleh peramban, dan tak terlihat oleh agen uji. "
                      f"Pakai {ganti}; bila memang harus, daftarkan di DIBOLEHKAN "
                      f"dengan alasan.")
            elif len(alasan) < 20:
                g.add(f"{rel} dibebaskan tanpa alasan yang bisa dinilai orang.")


def check_host(g: Guard, index_src: str) -> None:
    g.bump()
    if "ConfirmHost" not in index_src:
        g.add("src/index.js tidak me-mount `<ConfirmHost/>` → `askConfirm()/askReason()` "
              "tidak menampilkan apa pun dan SETIAP tombol hapus/batalkan akan tampak "
              "mati tanpa pesan. Tambahkan `<ConfirmHost />` di sebelah `<Toaster />`.")
        return
    if not re.search(r"<ConfirmHost\s*/?>", index_src):
        g.add("src/index.js menyebut ConfirmHost tetapi tidak me-render `<ConfirmHost />`.")


def self_test() -> int:
    kasus = []

    def cek(nama: str, benar: bool):
        kasus.append((nama, benar))

    # ── Lapis 1 — PENGENAL harus MEMERAH untuk dialog peramban ────────────────
    cek("alert telanjang terdeteksi",
        find_calls('function f() { alert("x"); }') == [(1, "alert")])
    cek("window.alert terdeteksi (dan hanya SEKALI)",
        find_calls('window.alert("x");') == [(1, "alert")])
    cek("window.confirm dalam if terdeteksi",
        find_calls('if (!window.confirm("x")) return;') == [(1, "confirm")])
    cek("window.prompt terdeteksi",
        find_calls('const a = window.prompt("x");') == [(1, "prompt")])
    cek("nomor baris tepat walau ada komentar blok di atasnya",
        find_calls('/* dua\n   baris */\nalert("x");') == [(3, "alert")])

    # ── Lapis 2 — TIDAK boleh menuduh palsu (kasus NYATA dari repo ini) ───────
    cek("kata 'alert' di dalam string label → bukan pelanggaran",
        find_calls('const o = { label: "Instan — 1 pesan per alert (real-time)" };') == [])
    cek("fungsi yang KEBETULAN bernama confirm → bukan pelanggaran",
        find_calls("async function confirm() { return 1; }\nconst x = confirm();") == [])
    cek("askConfirm()/askReason() → bukan pelanggaran",
        find_calls("await askConfirm({}); await askReason({}); await askText({});") == [])
    cek("metode pada objek lain (`api.confirm()`) → bukan pelanggaran",
        find_calls("api.confirm({});") == [])
    cek("komentar yang MENYEBUT alert() → bukan pelanggaran",
        find_calls('// dulu alert("x") — sekarang ErrorNotice\nlet y = 1;') == [])
    cek("nama komponen <ConfirmModal> → bukan pelanggaran",
        find_calls("return <ConfirmModal open={x} />;") == [])
    cek("template literal: teks diabaikan, `${confirm()}` TETAP terdeteksi",
        find_calls("const s = `abc alert( def ${confirm()}`;") == [(1, "confirm")])

    # ── Lapis 3 — ATURAN (pembebasan & <ConfirmHost/>) ────────────────────────
    g = Guard("INV-UI-06", "self-test"); g.violations, g.checks = [], 0
    check_calls(g, {"a.jsx": [(3, "alert")]}, {})
    cek("pelanggaran tanpa pembebasan → MERAH", len(g.violations) == 1)

    g = Guard("INV-UI-06", "self-test"); g.violations, g.checks = [], 0
    check_calls(g, {"a.jsx": [(3, "alert")]},
                {"a.jsx": "Skrip debug khusus pengembang, tidak ikut bundel produksi."})
    cek("pembebasan beralasan panjang → hijau", len(g.violations) == 0)

    g = Guard("INV-UI-06", "self-test"); g.violations, g.checks = [], 0
    check_calls(g, {"a.jsx": [(3, "alert")]}, {"a.jsx": "perlu"})
    cek("pembebasan tanpa alasan yang bisa dinilai → MERAH", len(g.violations) == 1)

    g = Guard("INV-UI-06", "self-test"); g.violations, g.checks = [], 0
    check_host(g, "root.render(<App />);")
    cek("index.js tanpa <ConfirmHost/> → MERAH", len(g.violations) == 1)

    g = Guard("INV-UI-06", "self-test"); g.violations, g.checks = [], 0
    check_host(g, "import ConfirmHost from '@/components/ConfirmHost';\n<ConfirmHost />")
    cek("index.js dengan <ConfirmHost/> → hijau", len(g.violations) == 0)

    gagal = sum(0 if ok else 1 for _n, ok in kasus)
    print(f"{B}== SELF-TEST INV-UI-06 (penjaga dialog blokir harus bisa MEMERAH) =={X}")
    for nama, ok in kasus:
        print(f"  [{G + 'PASS' + X if ok else R + 'FAIL' + X}] {nama}")
    print(f"{G}  HIJAU — penjaga terbukti menuduh dialog peramban DAN tidak menuduh "
          f"palsu string/komentar/fungsi senama.{X}" if not gagal
          else f"{R}{B}  SELF-TEST MERAH ({gagal} kasus).{X}")
    return gagal


def main(verbose: bool = False) -> int:
    g = Guard("INV-UI-06", "dialog bawaan peramban (alert/confirm/prompt) dilarang")
    hasil = scan()
    total = sum(len(v) for v in hasil.values())
    print(f"  dialog peramban ditemukan: {total} di {len(hasil)} berkas "
          f"(alert/confirm/prompt) · pengecualian terdaftar: {len(DIBOLEHKAN)}")
    if verbose:
        for rel, hits in sorted(hasil.items()):
            for baris, nama in hits:
                print(f"    {rel}:{baris} {nama}()")
    check_calls(g, hasil, DIBOLEHKAN)
    index_js = SRC / "index.js"
    check_host(g, index_js.read_text(encoding="utf-8") if index_js.exists() else "")
    return g.finish()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(1 if self_test() else 0)
    raise SystemExit(main(verbose=("-v" in sys.argv)))
