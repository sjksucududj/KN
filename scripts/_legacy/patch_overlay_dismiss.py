#!/usr/bin/env python3
"""Patch semua backdrop modal yang masih memakai onClick={onClose} langsung
menjadi {...overlayDismiss(...)} (gestur utuh: pointerdown + click di backdrop).

Jalan idempotent: bila sudah dipatch, file dilewati.
"""
import re
import sys
from pathlib import Path

SRC = Path("/app/frontend/src")
IMPORT_LINE = 'import { overlayDismiss } from "@/utils/overlayDismiss";'

OVERLAY_MARKERS = ("modal-overlay", "flex items-center justify-center bg-black/")

# handler-handler penutup yang dipakai pada baris backdrop
HANDLERS = [
    "onClick={onClose}",
    "onClick={onCancel}",
    "onClick={closeModal}",
    "onClick={() => setShowPo(false)}",
]

DRY = "--apply" not in sys.argv
changed_files = []

for path in sorted(SRC.rglob("*.jsx")):
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    hits = []
    for i, line in enumerate(lines):
        if not any(m in line for m in OVERLAY_MARKERS):
            continue
        if "e.target === e.currentTarget" in line or "overlayDismiss" in line:
            continue
        for h in HANDLERS:
            if h in line:
                arg = h[len("onClick={"):-1]
                lines[i] = line.replace(h, "{...overlayDismiss(%s)}" % arg)
                hits.append((i + 1, arg))
                break
    if not hits:
        continue

    # sisipkan import setelah blok import terakhir
    if IMPORT_LINE not in text:
        last_import = max(
            idx for idx, l in enumerate(lines)
            if l.startswith("import ") or (l.startswith("} from ") and idx > 0)
        )
        lines.insert(last_import + 1, IMPORT_LINE)

    changed_files.append((str(path.relative_to(SRC)), hits))
    if not DRY:
        path.write_text("\n".join(lines), encoding="utf-8")

print(("DRY-RUN" if DRY else "APPLIED") + f" — {len(changed_files)} berkas:")
for f, hits in changed_files:
    for ln, arg in hits:
        print(f"  {f}:{ln}  ->  overlayDismiss({arg})")
