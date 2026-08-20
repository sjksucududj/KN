"""fa_error_branch_500.py — AUDIT #073 F1: empirically test the ERROR BRANCH
(not-found / invalid) of route handlers that call a service WITHOUT try/except.

Sends a bogus path-id as admin. Proper handling -> 404/400/409. BUG -> 500
(unhandled ValueError/exception leaking as Internal Server Error). This exercises
never-tested error branches of otherwise-"hit" endpoints.
"""
import ast
import glob
import os
import re
import requests

BASE = "http://localhost:8001/api"


def login():
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": "admin@kainnusantara.id", "password": "demo12345"}, timeout=15)
    return r.json()["token"]


def unwrapped_handlers():
    """Return list of (method, path) for route handlers that call a service and
    have a {id} path param and NO try/except (candidate 500-on-error)."""
    out = []
    METH = {"get", "post", "put", "patch", "delete"}
    for f in glob.glob("/app/backend/routers/*.py"):
        src = open(f).read()
        tree = ast.parse(src)
        prefix = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                fn = node.value.func
                if getattr(fn, "id", None) == "APIRouter" or getattr(fn, "attr", None) == "APIRouter":
                    for kw in node.value.keywords:
                        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                            prefix = kw.value.value
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr in METH):
                    continue
                if not (dec.args and isinstance(dec.args[0], ast.Constant)):
                    continue
                path = prefix + dec.args[0].value
                if "{" not in path:
                    continue
                body = ast.get_source_segment(src, node) or ""
                calls_svc = ("_service." in body or "svc." in body or "service." in body
                             or "pay." in body)
                if calls_svc and "try:" not in body:
                    out.append((dec.func.attr.upper(), path))
    return out


def main():
    tok = login()
    H = {"Authorization": f"Bearer {tok}"}
    handlers = unwrapped_handlers()
    # only test non-GET mutation actions & GET details with bogus id
    crashes, ok = [], 0
    tested = 0
    seen = set()
    for m, path in handlers:
        key = (m, path)
        if key in seen:
            continue
        seen.add(key)
        url = BASE.replace("/api", "") + re.sub(r"\{[a-z_]+\}", "BOGUS_AUDIT_ID", path)
        try:
            r = requests.request(m, url, headers=H, json={}, timeout=12)
        except Exception as e:
            print(f"  EXC {m} {path}: {e}")
            continue
        tested += 1
        if r.status_code == 500:
            crashes.append((m, path))
            print(f"  500! {m:6} {path}")
        else:
            ok += 1
    print("\n" + "=" * 60)
    print(f"unwrapped handlers w/ id param tested: {tested}")
    print(f"  proper 4xx (ok): {ok}")
    print(f"  500 crashes    : {len(crashes)}")
    if crashes:
        print("\nERROR-BRANCH 500 (unhandled exception on bogus id):")
        for m, p in crashes:
            print(f"  {m} {p}")


if __name__ == "__main__":
    main()
