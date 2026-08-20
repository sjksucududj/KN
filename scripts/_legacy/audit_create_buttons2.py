#!/usr/bin/env python3
"""Audit lanjutan tombol CREATE:
 - Deteksi setter modal (setShowX/setOpenX/setXModal/setCreating...) yg dipanggil dari tombol create,
   TAPI state-nya TIDAK dirender kondisional (popup takkan muncul).
 - Deteksi tombol create yg NAVIGATE (setView/onNavigate/navigate) -> bukan popup (kandidat keluhan user).
"""
import re, pathlib

ROOT = pathlib.Path("/app/frontend/src/features")
CREATE_CTX = re.compile(r"(Buat|Tambah|\+\s*[A-Z]|Baru|<Plus\b)")

nav_buttons, dead_state = [], []

for f in sorted(ROOT.rglob("*.jsx")):
    src = f.read_text(encoding="utf-8", errors="ignore")
    rel = str(f.relative_to("/app/frontend/src"))
    # kumpulkan state useState -> setter
    setters = {}  # setterName -> stateName
    for m in re.finditer(r"const\s*\[\s*(\w+)\s*,\s*(set\w+)\s*\]\s*=\s*useState", src):
        setters[m.group(2)] = m.group(1)

    for m in re.finditer(r"<(button|Button)\b[\s\S]*?</\1>", src):
        blk = m.group(0)
        if not CREATE_CTX.search(blk):
            continue
        line = src[:m.start()].count("\n") + 1
        tid = re.search(r'data-testid="([^"]+)"', blk)
        tid = tid.group(1) if tid else "(no-testid)"
        # NAVIGATE?
        if re.search(r"\b(setView|setActiveView|onNavigate|navigate|setPage|setTab)\s*\(", blk):
            nav_buttons.append((rel, line, tid))
        # cari setter yg dipanggil di dalam tombol
        for setter, state in setters.items():
            if re.search(rf"\b{setter}\s*\(\s*(true|!{state}\b|\{{)", blk):
                # apakah state dirender kondisional di file?
                rendered = bool(re.search(rf"\{{\s*{state}\s*&&", src) or
                                re.search(rf"open=\{{\s*!?{state}\b", src) or
                                re.search(rf"\b{state}\s*\?\s*<", src) or
                                re.search(rf"(show|open|visible|isOpen)=\{{\s*{state}\b", src) or
                                re.search(rf"\b{state}\s*&&\s*<", src))
                if not rendered:
                    dead_state.append((rel, line, tid, f"{setter}->{state} (state tak dirender?)"))

def dump(t, rows):
    print(f"\n===== {t} ({len(rows)}) =====")
    seen=set()
    for r in rows:
        k=(r[0],r[2] if len(r)>2 else "")
        print("  "+"  ".join(str(x) for x in r))

dump("B1. CREATE BUTTON -> setter modal tapi STATE TAK DIRENDER (popup takkan muncul)", dead_state)
dump("B2. CREATE BUTTON -> NAVIGATE (buka halaman, bukan popup)", nav_buttons)
