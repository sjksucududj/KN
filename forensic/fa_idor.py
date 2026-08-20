#!/usr/bin/env python3
"""
FORENSIC AUDIT — STAGE 3 static: exhaustive '/{id}' guard surface + money/tz scan.
For EVERY route (GET + mutation) whose path has a param, determine if the handler
enforces entity ownership. Heuristic (AST):
  - fetches a doc by id: find_one({"id": ...}) / find_one_and_update
  - guard present if body references: assert_entity_access OR apply_entity_scope
    OR resolve_list_scope OR the find query dict contains an entity field
Resources considered entity-scoped come from entity_scope.SCOPED_COLLECTIONS.
READ-ONLY.
"""
import ast, re, json
from pathlib import Path
from collections import defaultdict, Counter
import sys
sys.path.insert(0,"/app/backend")
from entity_scope import SCOPED_COLLECTIONS, SCOPE_FIELD

ROUTERS=Path("/app/backend/routers")
MUT={"post","put","patch","delete"}
SCOPE_GUARDS={"assert_entity_access","apply_entity_scope","resolve_list_scope","resolve_scope_ids","can_access_customer","scope_query","_scope_query"}

# infer collection from db.<coll> attribute accesses in handler
def collections_used(func):
    cols=set()
    for n in ast.walk(func):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id=="db":
            cols.add(n.attr)
        # db["coll"]
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id=="db":
            if isinstance(n.slice, ast.Constant): cols.add(n.slice.value)
    return cols

def called(func):
    out=set()
    for n in ast.walk(func):
        if isinstance(n, ast.Call):
            f=n.func
            if isinstance(f,ast.Name): out.add(f.id)
            elif isinstance(f,ast.Attribute): out.add(f.attr)
    return out

def route_decos(func):
    r=[]
    for dec in func.decorator_list:
        if isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute):
            o=dec.func.value; meth=dec.func.attr.lower()
            if isinstance(o,ast.Name) and o.id in ("router","api","app") and meth in ({"get"}|MUT):
                path=dec.args[0].value if dec.args and isinstance(dec.args[0],ast.Constant) else ""
                r.append((meth,path))
    return r

findings=[]
def F(sev,code,msg): findings.append((sev,code,msg))

for pyf in sorted(ROUTERS.glob("*.py")):
    if pyf.name=="__init__.py": continue
    tree=ast.parse(pyf.read_text())
    for func in ast.walk(tree):
        if not isinstance(func,(ast.AsyncFunctionDef,ast.FunctionDef)): continue
        routes=route_decos(func)
        if not routes: continue
        cols=collections_used(func); names=called(func)
        scoped_cols = cols & SCOPED_COLLECTIONS
        has_guard = bool(names & SCOPE_GUARDS)
        for meth,path in routes:
            if "{" not in path: continue
            if not scoped_cols: continue            # touches no entity-scoped collection
            if has_guard: continue                  # has some scope guard
            sev = "HIGH" if meth in MUT else "MED"
            kind = "WRITE_NO_XSCOPE" if meth in MUT else "READ_NO_XSCOPE"
            F(sev, kind, f"{meth.upper():6} {path}  ({func.name}) touches {sorted(scoped_cols)} w/o entity guard")

print("########## EXHAUSTIVE /{id} ENTITY-GUARD SURFACE ##########")
order={"HIGH":0,"MED":1,"LOW":2}
findings.sort(key=lambda x:(order.get(x[0],9),x[1],x[2]))
for sev,code,msg in findings: print(f"  [{sev:4}] {code:16} {msg}")
c=Counter((s,co) for s,co,_ in findings)
print("\n  COUNTS:")
for (s,co),n in sorted(c.items(),key=lambda kv:(order.get(kv[0][0],9),kv[0][1])): print(f"   {s:4} {co:16} {n}")

# ───────────── MONEY / TZ / precision static scan ─────────────
print("\n########## MONEY PRECISION & TIMEZONE STATIC SCAN ##########")
import subprocess
svc=Path("/app/backend/services")
# datetime.now() (naive/local) vs datetime.now(timezone.utc)
naive=0; naive_hits=[]
for pyf in list(svc.glob("*.py"))+list(ROUTERS.glob("*.py")):
    for i,ln in enumerate(pyf.read_text().splitlines(),1):
        if re.search(r"datetime\.now\(\s*\)", ln) or re.search(r"datetime\.utcnow\(\)", ln):
            naive+=1; naive_hits.append(f"{pyf.name}:{i}: {ln.strip()[:90]}")
print(f"  naive datetime.now()/utcnow() occurrences: {naive}")
for h in naive_hits[:25]: print(f"    {h}")
if naive> len(naive_hits[:25]): print(f"    ... +{naive-25} more")
