#!/usr/bin/env python3
"""INV-UI-04 — Field TURUNAN (hanya ada di respons DETAIL) tak boleh dibaca dari
respons DAFTAR.

KELAS BUG YANG DICEGAH (nyata, ditemukan uji layar sesi 2026-08-15)
==================================================================
`KN-E9-SUPPLY-INVISIBLE` (P1 senyap). Pita **"Dipenuhi dari Badan Usaha Lain"**
(FASE E-9 · E9.2 · user story US23/US24 — *"kekurangannya diambil dari CV Kanda Suka
lewat KSC/IC-00006"*) **TIDAK PERNAH tampil** di layar selama berbulan-bulan,
padahal backend sudah benar dan POC E-9 hijau 44/44.

Sebabnya bukan logika bisnis, melainkan **aliran data di layar**:

* `interco_supply` adalah field **turunan** — dihitung saat `GET /sales-orders/{id}`
  (menelusuri `interco_transactions.source_order_id` + status tugas gudang) dan
  sengaja TIDAK disertakan di respons DAFTAR supaya daftar tidak menembak N+1 query.
* Tetapi `OrderDetailPanel` membacanya dari prop `order` yang berasal dari respons
  **DAFTAR** (`GET /dashboard` → `orders[]`, satu panggilan untuk seluruh aplikasi).
* `(sel.interco_supply || []).length > 0` karena itu SELALU 0 → blok JSX-nya
  di-skip tanpa error, tanpa layar merah, tanpa apa pun di konsol.

Kenapa gate lama tak menangkapnya: seluruh pagar memeriksa **backend** (endpoint
detail memang mengembalikan field itu → POC PASS), sedangkan yang salah adalah
**dari mana layar mengambilnya**. Risiko nyata di lapangan: orang menerbitkan
permintaan beli KEDUA untuk barang yang sudah di jalan dari PT saudara.

ATURAN (STATIK, tak butuh backend)
==================================
Untuk setiap field pada `DERIVED_FIELDS`: berkas frontend yang MEMBACA field itu
WAJIB juga memuat pemanggilan endpoint DETAIL-nya di berkas yang sama — artinya ia
mengambil datanya sendiri, bukan menumpang objek hasil daftar.

Berkas yang hanya MENERUSKAN field sebagai nilai awal (`fallback={...}`) tetap sah
karena tidak menjadikannya satu-satunya sumber; pola itu dikecualikan lewat
`PASSTHROUGH_PATTERNS`.

Melanggar → MERAH: sebut berkas, nomor baris, dan endpoint yang seharusnya dipanggil.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import FRONTEND, Guard  # noqa: E402

SRC = FRONTEND / "src"

#: field turunan → (pola pemanggilan endpoint detail yang sah, penjelasan singkat)
#:
#: Cara menambah entri: begitu sebuah endpoint DETAIL menghitung field yang TIDAK
#: dikembalikan endpoint daftarnya, daftarkan di sini. Biayanya satu baris dan
#: menutup satu kelas bug "blok JSX yang sunyi selamanya".
DERIVED_FIELDS = {
    "interco_supply": (
        re.compile(r"/sales-orders/\$\{[^}]+\}"),
        "GET /api/sales-orders/{id} (FASE E-9 · E9.2 · US23/US24 — "
        "pita 'Dipenuhi dari Badan Usaha Lain')",
    ),
}

#: Pola yang menandakan field hanya DITERUSKAN sebagai nilai awal, bukan dijadikan
#: satu-satunya sumber data (mis. `fallback={sel.interco_supply}`).
PASSTHROUGH_PATTERNS = (
    re.compile(r"fallback=\{[^}]*\}"),
)

#: Awalan baris komentar (JS & JSX). Komentar yang MENJELASKAN field turunan justru
#: yang paling kita inginkan ada — jadi ia tidak boleh dihitung sebagai "bacaan".
#: Komentar dibuang lewat `_strip_comments()` (bukan hanya dicek awalan barisnya)
#: supaya komentar BLOK berbaris-banyak — yang justru dipakai untuk menjelaskan
#: kenapa field ini rawan — tidak memerahkan pagarnya sendiri.
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"//[^\n]*")


def _strip_comments(text: str) -> str:
    """Kosongkan isi komentar TANPA menggeser nomor baris (spasi, newline dijaga)."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    return LINE_COMMENT.sub(blank, BLOCK_COMMENT.sub(blank, text))

SKIP_DIRS = {"node_modules", "build", "__tests__"}


def _files():
    for path in sorted(SRC.rglob("*.jsx")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path
    for path in sorted(SRC.rglob("*.js")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def main() -> int:
    g = Guard("INV-UI-04",
              "Field turunan dibaca dari sumbernya sendiri (bukan dari respons daftar)")

    for field, (detail_call, endpoint_desc) in DERIVED_FIELDS.items():
        # `\b` di kiri agar `x.interco_supply` & `"interco_supply"` tertangkap,
        # tetapi `order_interco_supply_panel` (nama testid) TIDAK dianggap bacaan.
        reader = re.compile(r"(?<![\w-])" + re.escape(field) + r"(?![\w-])")
        pemakai = 0
        for path in _files():
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue
            # Deteksi bacaan dilakukan pada teks TANPA komentar; deteksi pemanggilan
            # endpoint tetap pada teks asli (komentar tak pernah memalsukan fetch).
            text = _strip_comments(raw)
            if not reader.search(text):
                continue
            pemakai += 1
            g.bump()
            if detail_call.search(raw):
                continue                        # mengambil datanya sendiri → sah
            lines = [i for i, ln in enumerate(text.split("\n"), start=1)
                     if reader.search(ln)
                     and not any(p.search(ln) for p in PASSTHROUGH_PATTERNS)]
            if not lines:
                continue                        # hanya meneruskan nilai awal → sah
            rel = path.relative_to(SRC)
            g.add(f"{rel}:{lines[0]} — membaca field turunan `{field}` tetapi berkas ini "
                  f"tidak pernah memanggil {endpoint_desc}. Field itu TIDAK ADA di "
                  f"respons daftar (mis. `GET /dashboard` → `orders[]`), jadi blok JSX-nya "
                  f"akan diam-diam kosong selamanya — tanpa error, tanpa layar merah. "
                  f"Ambil sendiri lewat endpoint detail di komponen ini.")
        g.bump()
        if pemakai == 0:
            g.add(f"Tidak ada berkas frontend yang memakai `{field}`. Kalau pita/panelnya "
                  f"memang dihapus, hapus juga entrinya dari DERIVED_FIELDS supaya pagar "
                  f"ini tidak menjaga sesuatu yang sudah tidak ada.")

    return g.finish()


if __name__ == "__main__":
    raise SystemExit(main())
