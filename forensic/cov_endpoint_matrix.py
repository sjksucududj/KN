"""cov_endpoint_matrix.py — AUDIT: map every API route -> HIT/MISS from coverage.

Cross-references AST-extracted routes (method+path+handler line span) in
/app/backend/routers/*.py against coverage executed_lines from the corpus run.
An endpoint is HIT if ANY line of its handler body executed during the corpus.
MISS = never exercised by the ENTIRE historical test corpus + forensic scripts.
"""
import ast
import json
import os
import glob

COV = json.load(open("/app/coverage_data/cov_backend.json"))
ROUTERS_DIR = "/app/backend/routers"
METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def prefix_of(tree):
    """Find router = APIRouter(prefix=...)."""
    pref = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            fname = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if fname == "APIRouter":
                for kw in node.value.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        pref = kw.value.value
    return pref


def routes_in(path):
    src = open(path).read()
    tree = ast.parse(src)
    pref = prefix_of(tree)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            fn = dec.func
            if not isinstance(fn, ast.Attribute):
                continue
            attr = fn.attr.lower()
            methods = []
            rpath = None
            if attr in METHODS:
                methods = [attr.upper()]
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    rpath = dec.args[0].value
            elif attr == "api_route":
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    rpath = dec.args[0].value
                for kw in dec.keywords:
                    if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                        methods = [e.value.upper() for e in kw.value.elts
                                   if isinstance(e, ast.Constant)]
            if rpath is None or not methods:
                continue
            body_start = node.body[0].lineno if node.body else node.lineno
            end = node.end_lineno or body_start
            for m in methods:
                out.append({
                    "method": m, "path": pref + rpath, "func": node.name,
                    "line_start": body_start, "line_end": end,
                })
    return out


def main():
    all_rows = []
    per_router = {}
    for f in sorted(glob.glob(f"{ROUTERS_DIR}/*.py")):
        rel = "routers/" + os.path.basename(f)
        execset = set(COV["files"].get(rel, {}).get("executed_lines", []))
        rows = routes_in(f)
        hit = miss = 0
        for r in rows:
            body_lines = set(range(r["line_start"], r["line_end"] + 1))
            r["hit"] = bool(body_lines & execset)
            r["router"] = os.path.basename(f)
            all_rows.append(r)
            if r["hit"]:
                hit += 1
            else:
                miss += 1
        per_router[os.path.basename(f)] = {"total": len(rows), "hit": hit, "miss": miss}

    total = len(all_rows)
    hits = sum(1 for r in all_rows if r["hit"])
    misses = total - hits
    print(f"=== ENDPOINT-HIT MATRIX ===")
    print(f"TOTAL routes analyzed : {total}")
    print(f"HIT (exercised)       : {hits} ({round(100*hits/total,1)}%)")
    print(f"MISS (never executed) : {misses} ({round(100*misses/total,1)}%)")
    print()
    print("=== ROUTERS WITH MOST UNTESTED ENDPOINTS ===")
    ranked = sorted(per_router.items(), key=lambda kv: kv[1]["miss"], reverse=True)
    for name, s in ranked:
        if s["miss"] > 0:
            print(f"  {name:34} miss={s['miss']:3d} / {s['total']:3d}")

    json.dump({
        "summary": {"total": total, "hit": hits, "miss": misses},
        "per_router": per_router,
        "routes": all_rows,
    }, open("/app/coverage_data/endpoint_matrix.json", "w"), indent=2)
    print("\n[written] /app/coverage_data/endpoint_matrix.json")


if __name__ == "__main__":
    main()
