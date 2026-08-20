#!/usr/bin/env python3
"""Audit tombol 'Buat/Tambah/+ ' di frontend:
 - Deteksi tombol dgn intent CREATE (teks Buat/Tambah/Baru/+ atau ikon Plus atau testid create/add/new/tambah/buat)
 - Flag tombol yg TIDAK punya onClick (mati) atau onClick no-op (=> {}, => null, alert(), console)
 - Klasifikasi target: MODAL (setShow*/setOpen*/setModal*/set*Form true) vs NAVIGATE (setView/navigate) vs INLINE (setShowForm toggle) vs UNKNOWN
"""
import re, pathlib

ROOT = pathlib.Path("/app/frontend/src/features")
CREATE_TXT = re.compile(r"(Buat|Tambah|\+\s*[A-Z]|Baru|New\b|Add\b|Create)", re.I)
CREATE_TID = re.compile(r'data-testid="[^"]*(create|add|new|tambah|buat|baru)[^"]*"', re.I)
PLUS_ICON = re.compile(r"<Plus\b")

files = sorted(ROOT.rglob("*.jsx"))
no_onclick, noop, ok_modal, ok_other = [], [], [], []

for f in files:
    src = f.read_text(encoding="utf-8", errors="ignore")
    # pecah menjadi elemen <button ...>...</button> dan <Button ...>...</Button>
    for m in re.finditer(r"<(button|Button)\b[\s\S]*?</\1>", src):
        blk = m.group(0)
        line = src[:m.start()].count("\n") + 1
        has_create = bool(CREATE_TXT.search(blk) or CREATE_TID.search(blk) or PLUS_ICON.search(blk))
        if not has_create:
            continue
        # abaikan tombol yg jelas bukan 'create utama' (mis. add-item di dalam form) -> tetap dilaporkan tapi ditandai
        tid = re.search(r'data-testid="([^"]+)"', blk)
        tid = tid.group(1) if tid else "(no-testid)"
        onclick = re.search(r"onClick=\{([\s\S]*?)\}", blk)
        rel = str(f.relative_to("/app/frontend/src"))
        if not onclick:
            # cek apakah tombol submit di dalam <form onSubmit>
            if re.search(r'type="submit"', blk):
                ok_other.append((rel, line, tid, "submit(form)"))
            else:
                no_onclick.append((rel, line, tid, blk.strip().replace("\n", " ")[:90]))
            continue
        body = onclick.group(1).strip()
        if re.fullmatch(r"\(\)\s*=>\s*\{?\s*\}?", body) or body in ("() => null", "()=>null") or "TODO" in body:
            noop.append((rel, line, tid, body[:80]))
        elif re.search(r"\balert\(|console\.(log|warn)", body):
            noop.append((rel, line, tid, f"alert/console: {body[:70]}"))
        elif re.search(r"setShow|setOpen|setModal|setForm|setCreat|setDialog|setDrawer|setPanel|setActive\w*[Mm]odal|set\w*Open", body):
            ok_modal.append((rel, line, tid, body[:60]))
        else:
            ok_other.append((rel, line, tid, body[:60]))

def dump(title, rows):
    print(f"\n===== {title} ({len(rows)}) =====")
    for r in rows:
        print(f"  {r[0]}:{r[1]}  [{r[2]}]  {r[3]}")

dump("A1. CREATE BUTTON TANPA onClick (kemungkinan MATI / tak muncul popup)", no_onclick)
dump("A2. CREATE BUTTON onClick NO-OP / alert / console (tak buka popup)", noop)
print(f"\n[info] create-buttons OK->modal/state: {len(ok_modal)} | OK->other(navigate/handler/submit): {len(ok_other)}")
