#!/usr/bin/env python3
"""FORENSIC 1c — N+1 query static detection (AST) + endpoint latency probe."""
import ast, sys, time, requests
from pathlib import Path
from collections import defaultdict

DIRS=[Path("/app/backend/routers"),Path("/app/backend/services")]

def is_db_query_await(node):
    # await db.<coll>.find_one(...) / .find(...) / .aggregate(...) / .count_documents(...)
    if not isinstance(node, ast.Await): return False
    call=node.value
    if not isinstance(call, ast.Call): return False
    f=call.func
    if isinstance(f, ast.Attribute) and f.attr in ("find_one","find","count_documents","aggregate","to_list","distinct"):
        # check chain contains db
        cur=f
        while isinstance(cur, ast.Attribute): cur=cur.value
        if isinstance(cur, ast.Name) and cur.id=="db": return True
        # db[coll].find
        if isinstance(f.value, ast.Subscript) and isinstance(f.value.value, ast.Name) and f.value.value.id=="db": return True
    return False

hits=[]
for D in DIRS:
    for pyf in sorted(D.glob("*.py")):
        try: tree=ast.parse(pyf.read_text())
        except: continue
        for loop in ast.walk(tree):
            if isinstance(loop,(ast.For,ast.AsyncFor)):
                for n in ast.walk(loop):
                    if is_db_query_await(n):
                        # find_one inside loop is classic N+1
                        call=n.value.func.attr if isinstance(n.value.func,ast.Attribute) else "?"
                        if call in ("find_one","find","aggregate","count_documents"):
                            hits.append((pyf.name, getattr(n,'lineno','?'), call))
print("########## 1c N+1 QUERY PATTERNS (db query inside loop) ##########")
byfile=defaultdict(list)
for fn,ln,call in hits: byfile[fn].append((ln,call))
for fn in sorted(byfile):
    calls=byfile[fn]
    print(f"  {fn}: {len(calls)} in-loop db calls -> lines {[f'{l}:{c}' for l,c in sorted(calls)][:8]}")
print(f"  TOTAL in-loop db-query sites: {len(hits)} across {len(byfile)} files")

print("\n########## 1c ENDPOINT LATENCY (admin) ##########")
BASE="http://localhost:8001/api"
tok=requests.post(f"{BASE}/auth/login",json={"email":"admin@kainnusantara.id","password":"demo12345"}).json()["token"]
H={"Authorization":f"Bearer {tok}","X-Entity-Id":"ent_ksc"}
eps=["/sales-orders","/purchase-orders","/products","/customers","/inventory/balances",
     "/dashboard/summary","/crm/leads","/reports/stock-aging","/vendor-bills/payables/summary",
     "/finance/bi?year=2026","/wms/tasks","/ar/aging","/gl/journal"]
for e in eps:
    try:
        t=time.monotonic(); r=requests.get(f"{BASE}{e}",headers=H,timeout=30); dt=(time.monotonic()-t)*1000
        n=""
        try:
            b=r.json(); n=f"{len(b)} items" if isinstance(b,list) else "obj"
        except: n=""
        flag=" <== SLOW" if dt>800 else ""
        print(f"  {r.status_code}  {dt:7.1f}ms  {e:42} {n}{flag}")
    except Exception as ex:
        print(f"  ERR {e}: {ex}")
