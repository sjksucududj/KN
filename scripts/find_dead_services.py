#!/usr/bin/env python3
"""find_dead_services.py — KN3: temukan modul service yang benar-benar tak terpakai.
Parse import lintas backend (termasuk multiline parenthesized — pelajaran A3 Torado)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
SERVICES = BACKEND / "services"

service_mods = {f.stem for f in SERVICES.glob("*.py") if f.stem != "__init__"}
used = set()
for py in BACKEND.rglob("*.py"):
    if "__pycache__" in str(py):
        continue
    text = py.read_text(encoding="utf-8", errors="ignore")
    for mod in service_mods:
        if py == SERVICES / f"{mod}.py":
            continue
        if re.search(rf'\bservices\.{mod}\b', text) or re.search(rf'\bfrom services\.{mod}\b', text):
            used.add(mod)
        for m in re.finditer(r'from services import ([^\n(]+)', text):
            if mod in re.split(r'[,\s]+', m.group(1)):
                used.add(mod)
        for m in re.finditer(r'from services import \(([^)]*)\)', text, re.DOTALL):
            if mod in re.split(r'[,\s]+', m.group(1)):
                used.add(mod)

unused = sorted(service_mods - used)
print(f"Total service modules: {len(service_mods)}  |  Used: {len(used)}")
print(f"\n=== SERVICE TIDAK TERPAKAI ({len(unused)}) ===")
for m in unused:
    print(f"  {m}.py ({(SERVICES / f'{m}.py').stat().st_size} bytes)")
if not unused:
    print("  none")
