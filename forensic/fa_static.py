#!/usr/bin/env python3
"""
FORENSIC AUDIT — Static Layer v2 (AST endpoint-guard analysis w/ transitive helper resolution).

Improvement over v1: many handlers authenticate through LOCAL helper functions
(e.g. _emp_for_user -> current_user). We compute, per module, which local
functions transitively provide AUTH / PERMISSION / SCOPE guards, then treat
calls to those helpers as guards. Drastically cuts false positives.

READ-ONLY. No fixes.
"""
import ast, re, json
from pathlib import Path
from collections import Counter

ROUTERS_DIR = Path("/app/backend/routers")
AUTH_PRIMS = {"current_user", "require_permission", "require_role", "entity_ctx", "_emp_for_user"}
PERM_PRIMS = {"require_permission", "require_role"}
SCOPE_PRIMS = {"entity_ctx", "apply_entity_scope", "resolve_list_scope",
               "resolve_scope_ids", "assert_entity_access"}
MUT = {"post", "put", "patch", "delete"}
# Endpoints intentionally public / alternative-auth (documented by-design)
KNOWN_PUBLIC = {
    ("auth.py", "login"), ("auth.py", "logout"), ("auth.py", "register"),
    ("hr_attendance.py", "ingest_attendance"),  # device_token auth
}

findings = []
def add(sev, code, fn, route, detail):
    findings.append({"sev": sev, "code": code, "file": fn, "route": route, "detail": detail})

def called_names(node):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name): out.add(f.id)
            elif isinstance(f, ast.Attribute): out.add(f.attr)
        elif isinstance(n, ast.Name): out.add(n.id)
        elif isinstance(n, ast.Attribute): out.add(n.attr)
    return out

def route_decorators(func):
    routes = []
    for dec in func.decorator_list:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
            obj = dec.func.value
            method = dec.func.attr.lower()
            objname = obj.id if isinstance(obj, ast.Name) else ""
            if objname in ("router", "api", "app") and method in ({"get"} | MUT):
                path = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else ""
                routes.append((method, path))
    return routes

def sig_names(func):
    out = set()
    for d in func.args.defaults + func.args.kw_defaults:
        if d is not None: out |= called_names(d)
    for a in func.args.args + func.args.kwonlyargs:
        if a.annotation is not None: out |= called_names(a.annotation)
    return out

total=mut_c=get_c=byid=0
for pyf in sorted(ROUTERS_DIR.glob("*.py")):
    if pyf.name == "__init__.py": continue
    tree = ast.parse(pyf.read_text(encoding="utf-8"))
    funcs = {f.name: f for f in ast.walk(tree)
             if isinstance(f, (ast.AsyncFunctionDef, ast.FunctionDef))}
    calls = {name: called_names(fn) for name, fn in funcs.items()}

    # Fixpoint: which local funcs transitively provide AUTH / PERM / SCOPE
    def closure(prims):
        prov = {n for n, c in calls.items() if c & prims}
        changed = True
        while changed:
            changed = False
            for n, c in calls.items():
                if n in prov: continue
                if c & prov:
                    prov.add(n); changed = True
        return prov | prims
    AUTH = closure(AUTH_PRIMS); PERM = closure(PERM_PRIMS); SCOPE = closure(SCOPE_PRIMS)

    for name, func in funcs.items():
        routes = route_decorators(func)
        if not routes: continue
        allnames = called_names(func) | sig_names(func)
        has_auth = bool(allnames & AUTH)
        has_perm = bool(allnames & PERM)
        has_scope = bool(allnames & SCOPE)
        for method, path in routes:
            total += 1
            is_mut = method in MUT
            is_by_id = bool(re.search(r"\{[^}]+\}", path))
            if is_mut: mut_c += 1
            else: get_c += 1
            if (pyf.name, name) in KNOWN_PUBLIC: continue
            label = f"{method.upper():6} {path}  ({name})"
            if not has_auth:
                add("HIGH" if is_mut else "MED", "NO_AUTH", pyf.name, label,
                    "Tidak ada guard auth (transitif) → cek endpoint TANPA autentikasi.")
                continue
            if is_mut and not has_perm:
                add("MED", "MUT_NO_PERM", pyf.name, label,
                    "Mutation ter-autentikasi tapi TANPA require_permission/require_role.")
            if (not is_mut) and is_by_id and ("assert_entity_access" not in allnames) and (not has_scope):
                byid += 1
                add("LOW", "IDOR_GET_BY_ID", pyf.name, label,
                    "GET /{id} tanpa assert_entity_access & tanpa entity scope.")

print(json.dumps({"total_routes": total, "mutation": mut_c, "get": get_c, "findings": len(findings)}, indent=2))
order = {"CRIT":0,"HIGH":1,"MED":2,"LOW":3}
findings.sort(key=lambda x:(order.get(x["sev"],9), x["code"], x["file"]))
print("\n===== FINDINGS =====")
for f in findings:
    print(f"[{f['sev']:4}] {f['code']:14} {f['file']:24} {f['route']}")
c = Counter((f["sev"], f["code"]) for f in findings)
print("\n===== COUNTS =====")
for (sev, code), n in sorted(c.items(), key=lambda kv:(order.get(kv[0][0],9), kv[0][1])):
    print(f"  {sev:4} {code:16} {n}")
