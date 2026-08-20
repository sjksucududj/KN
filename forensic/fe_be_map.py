"""fe_be_map.py — AUDIT #073 Phase D: map frontend API calls vs backend routes.

Finds: (1) ORPHAN backend endpoints never called by FE (dead code / hidden
attack surface), (2) how many of the 91 never-tested endpoints are ALSO
FE-orphans, (3) DEAD FE calls to non-existent BE routes.
"""
import json
import re
import glob
import os

FE_DIR = "/app/frontend/src"
MATRIX = json.load(open("/app/coverage_data/endpoint_matrix.json"))


def norm(path):
    """Normalize a path to a shape: strip /api, replace {x}/${x} params with {} , drop query & trailing slash."""
    p = path.split("?")[0]
    if p.startswith("/api"):
        p = p[4:]
    p = re.sub(r"\$\{[^}]+\}", "{}", p)      # ${id}
    p = re.sub(r"\{[a-zA-Z_]+\}", "{}", p)   # {id}
    p = re.sub(r"/+$", "", p)
    return p or "/"


# ── FE calls ──────────────────────────────────────────────────────────────────
fe_paths = set()
fe_raw = []
call_re = re.compile(r"\$\{API\}(/[^\s`'\"\)]+)")
for f in glob.glob(f"{FE_DIR}/**/*.js*", recursive=True):
    src = open(f, errors="ignore").read()
    for m in call_re.finditer(src):
        raw = m.group(1)
        fe_paths.add(norm(raw))
        fe_raw.append((os.path.relpath(f, FE_DIR), raw))

# ── BE routes ─────────────────────────────────────────────────────────────────
be_routes = MATRIX["routes"]
be_shapes = {}
for r in be_routes:
    s = norm(r["path"])
    be_shapes.setdefault(s, []).append(r)

fe_shapes = set(fe_paths)

# ORPHAN BE: shape present in BE but not called by FE
orphan = []
for s, rs in be_shapes.items():
    if s not in fe_shapes:
        orphan.append((s, rs))

# DEAD FE: FE shape with no BE route
dead_fe = [s for s in fe_shapes if s not in be_shapes]

# Orphans that are ALSO never-tested (dark)
orphan_and_dark = []
for s, rs in orphan:
    if all(not r["hit"] for r in rs):
        orphan_and_dark.append((s, rs))

print("=== FE↔BE MAP ===")
print(f"FE distinct API path-shapes called : {len(fe_shapes)}")
print(f"BE distinct route path-shapes       : {len(be_shapes)}")
print(f"ORPHAN BE shapes (no FE caller)      : {len(orphan)}")
print(f"  ...of which ALSO never-tested(dark): {len(orphan_and_dark)}")
print(f"DEAD FE shapes (no BE route)          : {len(dead_fe)}")

print("\n=== ORPHAN + DARK (BE endpoints with NEITHER a test NOR a FE caller) ===")
for s, rs in sorted(orphan_and_dark):
    methods = sorted({r["method"] for r in rs})
    print(f"  {','.join(methods):18} {s}")

print("\n=== DEAD FE CALLS (FE path shape not matching any BE route) ===")
for s in sorted(dead_fe):
    print(f"  {s}")

json.dump({
    "fe_shapes": sorted(fe_shapes),
    "orphan_be": sorted(s for s, _ in orphan),
    "orphan_and_dark": sorted(s for s, _ in orphan_and_dark),
    "dead_fe": sorted(dead_fe),
}, open("/app/coverage_data/fe_be_map.json", "w"), indent=2)
print("\n[written] /app/coverage_data/fe_be_map.json")
