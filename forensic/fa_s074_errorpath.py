"""fa_s074_errorpath.py — AUDIT S074 P#1: comprehensive error-branch sweep.

Enumerate EVERY mutation route with a {id} path param (all routers) and probe it
as admin with a BOGUS id + permissive body. Proper handling -> 4xx (404/400/409).
BUG -> HTTP 500 (unhandled exception leaking). Comprehensive successor of
fa_error_branch_500.py: covers ALL {id} handlers (wrapped or not).

Also flags 200-on-bogus-id (silent success / delete-noop class). READ-mostly.
"""
import ast
import glob
import re
import requests

BASE = "http://localhost:8001/api"
ROOT = "http://localhost:8001"
MUT = {"post", "put", "patch", "delete"}
BODY = {"reason": "audit", "notes": "audit", "amount": 1, "decision": "accept",
        "data": {"notes": "audit"}, "qty": 1, "sku": "x", "grade": "A",
        "requested_price": 1, "product_id": "x", "confirm": "x"}


def login():
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": "admin@kainnusantara.id", "password": "demo12345"}, timeout=15)
    return r.json()["token"]


def enumerate_id_routes():
    routes = []
    for f in sorted(glob.glob("/app/backend/routers/*.py")):
        src = open(f).read()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                if dec.func.attr.lower() not in MUT:
                    continue
                if not (dec.args and isinstance(dec.args[0], ast.Constant)):
                    continue
                route = dec.args[0].value
                if "{" not in route:
                    continue
                body = ast.get_source_segment(src, node) or ""
                wrapped = "try:" in body
                full = "/api" + route if not route.startswith("/api") else route
                routes.append((dec.func.attr.upper(), full, node.name, wrapped,
                               f.split("/")[-1]))
    return routes


def main():
    tok = login()
    H = {"Authorization": f"Bearer {tok}"}
    routes = enumerate_id_routes()
    seen = set()
    crashes, noop200, ok4xx, other = [], [], [], []
    for m, path, fn, wrapped, mod in routes:
        key = (m, path)
        if key in seen:
            continue
        seen.add(key)
        url = ROOT + re.sub(r"\{[a-zA-Z_]+\}", "BOGUS_AUDIT_ID", path)
        try:
            r = requests.request(m, url, headers=H, json=BODY, timeout=15)
        except Exception as e:
            print(f"  EXC {m} {path}: {e}")
            continue
        sc = r.status_code
        if sc == 500:
            crashes.append((m, path, fn, wrapped, mod, r.text[:120]))
            print(f"  [500!] {m:6} {path}  ({fn} @ {mod}, wrapped={wrapped})")
        elif sc in (200, 201):
            noop200.append((m, path, fn, mod))
            print(f"  [200 ] {m:6} {path}  ({fn}) <- success on BOGUS id (verify: noop/leak?)")
        elif sc in (400, 401, 403, 404, 409, 422):
            ok4xx.append((m, path, sc))
        else:
            other.append((m, path, sc))
    print("\n" + "=" * 70)
    print(f"total {len(seen)} unique mutation /{{id}} routes probed w/ bogus id")
    print(f"  proper 4xx      : {len(ok4xx)}")
    print(f"  500 CRASHES     : {len(crashes)}")
    print(f"  200 on bogus id : {len(noop200)}")
    print(f"  other           : {len(other)} {other[:8]}")
    if crashes:
        print("\n--- HTTP 500 (unhandled exception on bogus id) ---")
        for m, p, fn, w, mod, t in crashes:
            print(f"  {m:6} {p}  ({fn} @ {mod}) wrapped={w}  :: {t}")
    if noop200:
        print("\n--- 200 on bogus id (candidate silent-noop / misleading success) ---")
        for m, p, fn, mod in noop200:
            print(f"  {m:6} {p}  ({fn} @ {mod})")


if __name__ == "__main__":
    main()
