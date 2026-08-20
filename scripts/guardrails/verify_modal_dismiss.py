#!/usr/bin/env python3
"""INV-UI-01 — Modal tidak boleh tertutup sendiri oleh klik dari dropdown ber-portal.

Kelas bug yang dicegah (Sesi Fase E):
  * FASE-E-UI-MODAL-CLOSE (P1): memilih satu opsi pada dropdown (Radix Select/Popover)
    di dalam modal MENUTUP seluruh modal → isian pengguna hilang. Terlihat nyata pada
    modal "Impor Massal Barang Supplier" dan "Realisasi PR → PO".
    Penyebab: isi dropdown Radix dirender lewat **React portal** ke `document.body`.
    Secara DOM ia di luar modal, tetapi pada React event system event tetap MEREMBET
    mengikuti pohon React, sehingga `onClick` di elemen backdrop (penutup modal) ikut
    terpanggil. Ditambah lagi, opsi yang menjorok melewati kartu modal memang berada
    di atas area backdrop, sehingga klik "nyasar" pun bisa menutup modal.

Aturan (STATIK, tidak butuh backend):
  A. Setiap elemen BACKDROP modal (className memuat `modal-overlay`, atau kombinasi
     `fixed inset-0` + `bg-black/`) yang memasang handler penutup WAJIB memakai salah
     satu pengaman:
       - `{...overlayDismiss(...)}`         → helper resmi (frontend/src/utils/overlayDismiss.js)
       - `e.target === e.currentTarget`     → pemeriksaan target manual
  B. Isi dropdown ber-portal (`components/ui/select.jsx` & `components/ui/popover.jsx`)
     WAJIB menghentikan perembetan klik (`stopPropagation`) agar tidak pernah mencapai
     backdrop modal di atasnya.

Melanggar → MERAH: sebut berkas, nomor baris, dan alasannya.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import FRONTEND, Guard  # noqa: E402

SRC = FRONTEND / "src"

# Penanda elemen backdrop modal.
BACKDROP_MARKERS = ("modal-overlay", "m-sheet-wrap")
BACKDROP_TAILWIND = re.compile(r"fixed\s+inset-0[^\"']*bg-black/")

# Handler penutup yang dipasang pada backdrop.
CLOSE_HANDLER = re.compile(r"on(?:Click|MouseDown|PointerDown)=\{")

# Pengaman yang diterima.
SAFE_MARKERS = ("overlayDismiss(", "e.target === e.currentTarget",
                "e.currentTarget === e.target")

# Backdrop yang memang TIDAK berniat menutup apa pun (murni lapisan visual) tak
# punya handler → otomatis lolos, tidak perlu allowlist.

PORTAL_FILES = {
    "components/ui/select.jsx": "SelectContent (Radix Select portal)",
    "components/ui/popover.jsx": "PopoverContent (Radix Popover portal)",
}


def is_backdrop(line: str) -> bool:
    if any(m in line for m in BACKDROP_MARKERS):
        return True
    return bool(BACKDROP_TAILWIND.search(line))


def main() -> int:
    g = Guard("INV-UI-01", "Backdrop modal & dropdown ber-portal (anti auto-close)")

    # ── Aturan A — backdrop wajib pakai pengaman ──────────────────────────────
    for path in sorted(SRC.rglob("*.jsx")):
        try:
            lines = path.read_text(encoding="utf-8").split("\n")
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            if not is_backdrop(line) or not CLOSE_HANDLER.search(line):
                continue
            g.bump()
            if not any(s in line for s in SAFE_MARKERS):
                rel = path.relative_to(SRC)
                g.add(f"{rel}:{i} — backdrop modal menutup lewat handler mentah. "
                      f"Pakai {{...overlayDismiss(onClose)}} (utils/overlayDismiss.js) "
                      f"atau cek `e.target === e.currentTarget`; kalau tidak, klik opsi "
                      f"dropdown ber-portal akan menutup modal & isian pengguna hilang.")

    # ── Aturan B — isi dropdown ber-portal wajib stopPropagation ──────────────
    for rel, what in PORTAL_FILES.items():
        p = SRC / rel
        g.bump()
        if not p.exists():
            g.add(f"{rel} — berkas primitif tidak ditemukan; {what} tak bisa diverifikasi.")
            continue
        if "stopPropagation" not in p.read_text(encoding="utf-8"):
            g.add(f"{rel} — {what} tidak lagi memanggil `stopPropagation()`. Tanpa ini, "
                  f"klik opsi dropdown merembet lewat pohon React ke backdrop modal "
                  f"dan menutup modal induk.")

    return g.finish()


if __name__ == "__main__":
    raise SystemExit(main())
