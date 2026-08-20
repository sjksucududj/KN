#!/usr/bin/env python3
"""Codemod sekali-pakai: seragamkan format uang di pesan pengguna → `rupiah()`.

MASALAH (terukur, temuan penutupan FASE G-9):
  Pesan yang dibaca pengguna dibangun di banyak berkas dengan gaya campur:
    A. `f"Rp {x:,.0f}"`                        → gaya INGGRIS: "Rp 5,131,200"  ← SALAH
    B. `f"Rp {x:,.0f}".replace(",", ".")`      → benar, tetapi diulang-ulang
    C. helper `_rp()` lokal (disalin di 3 service FASE G-9)
  Gaya A tidak pernah terlihat selama bug KN-G9-ERR-SILENT hidup (bilah error tidak
  dirender). Begitu error ditampilkan, "Σ alokasi Rp 999,000,000" muncul di antarmuka
  yang seluruhnya Bahasa Indonesia.

YANG DILAKUKAN:
  `Rp {<expr>:,.0f}` / `Rp{<expr>:,}` / `Rp {<expr>:,}`  →  `{rupiah(<expr>)}`
  lalu menambahkan impor `rupiah` bila belum ada, dan membuang `.replace(",", ".")`
  yang jadi mubazir tepat sesudah f-string yang seluruh angkanya sudah lewat `rupiah()`.

BATASAN SENGAJA (biar aman):
  · hanya menyentuh pola di dalam f-string yang `<expr>`-nya TIDAK memuat `{`, `}`, atau `"`;
  · TIDAK menyentuh angka non-uang (mis. `{qty:,.2f}` tanpa "Rp");
  · TIDAK menyentuh berkas uji/POC (biar bukti-merah tetap membandingkan apa adanya).

Pemakaian:
    python scripts/_codemod_rupiah.py --dry-run
    python scripts/_codemod_rupiah.py --apply
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

# `Rp` + spasi opsional + `{expr:,[.Nf]}`  → `{rupiah(expr)}`
MONEY_RX = re.compile(r"Rp\s?\{([^{}\"']+?):,(?:\.\d+f)?\}")

# core_utils.py DIKECUALIKAN: di situlah `rupiah()` didefinisikan — menulis ulang
# pola di dalamnya akan membuat fungsi memanggil dirinya sendiri.
SKIP_PARTS = ("test", "poc", "__pycache__", "backend_test", "core_utils.py")


def targets():
    for p in sorted(BACKEND.rglob("*.py")):
        rel = str(p.relative_to(BACKEND)).lower()
        if any(s in rel for s in SKIP_PARTS):
            continue
        yield p


def ensure_import(text: str) -> str:
    if re.search(r"\brupiah\b", text.split("\n\n")[0]) and "import" in text[:2000]:
        pass
    # sudah diimpor?
    if re.search(r"from core_utils import [^\n]*\brupiah\b", text):
        return text
    m = re.search(r"^from core_utils import (.+)$", text, re.MULTILINE)
    if m:
        names = m.group(1)
        if names.rstrip().endswith("("):          # impor multi-baris
            return text.replace(m.group(0), m.group(0) + "\n    rupiah,", 1)
        return text.replace(m.group(0), f"from core_utils import {names}, rupiah", 1)
    # belum pernah impor core_utils: taruh sesudah blok impor pertama
    lines = text.split("\n")
    last = 0
    for i, ln in enumerate(lines[:80]):
        if ln.startswith(("import ", "from ")):
            last = i
    lines.insert(last + 1, "from core_utils import rupiah")
    return "\n".join(lines)


def main() -> int:
    apply = "--apply" in sys.argv
    total_hits = 0
    touched = []
    for p in targets():
        text = p.read_text(encoding="utf-8")
        hits = MONEY_RX.findall(text)
        if not hits:
            continue
        new = MONEY_RX.sub(lambda m: "{rupiah(%s)}" % m.group(1).strip(), text)
        # `.replace(",", ".")` jadi mubazir bila f-string-nya tak lagi punya `:,`
        new = re.sub(r'(f"[^"\n]*\{rupiah\([^"\n]*")\.replace\(",", "\."\)', r"\1", new)
        new = re.sub(r"(f'[^'\n]*\{rupiah\([^'\n]*')\.replace\(\",\", \"\.\"\)", r"\1", new)
        new = ensure_import(new)
        total_hits += len(hits)
        touched.append((str(p.relative_to(ROOT)), len(hits)))
        if apply:
            p.write_text(new, encoding="utf-8")
    for rel, n in touched:
        print(f"  {n:3d}  {rel}")
    print(f"\n{'DITERAPKAN' if apply else 'DRY-RUN'}: {total_hits} pola uang di "
          f"{len(touched)} berkas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
