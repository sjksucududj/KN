#!/usr/bin/env python3
"""
FORENSIC AUDIT — STAGE 4: write-side cross-entity IDOR (empirical, reversible) +
role-exploitability cross-reference for the /{id} no-guard surface.

(a) Empirical: as sales@ent_ksc, PATCH a customer owned by ent_kanda (reversible),
    and POST request-special-price on an ent_kanda sales-order. Confirm the server
    permits cross-entity WRITE. Reverts customer change afterwards.
(b) Static cross-ref: for each flagged WRITE /{id} endpoint, extract
    require_permission(module,action) and mark whether SALES or WAREHOUSE
    (non-cross-entity roles) hold that permission -> genuinely exploitable set.
"""
import os, re, ast, json, requests, sys
from pathlib import Path
sys.path.insert(0,"/app/backend")
from entity_scope import SCOPED_COLLECTIONS
from permissions_config import DEFAULT_PERMISSIONS
from pymongo import MongoClient

BASE="http://localhost:8001/api"
db=MongoClient(os.environ.get("MONGO_URL","mongodb://localhost:27017"))[os.environ.get("DB_NAME","test_database")]
OTHER="ent_kanda"
def login(role):
    r=requests.post(f"{BASE}/auth/login",json={"email":f"{role}@kainnusantara.id","password":"demo12345"},timeout=15)
    return (r.json()["token"],r.json()["user"]) if r.status_code==200 else (None,None)

print("########## (a) EMPIRICAL WRITE-SIDE CROSS-ENTITY IDOR ##########")
stoken,su=login("sales")
H={"Authorization":f"Bearer {stoken}"}
print(f"  sales scope allowed={su.get('allowed_entity_ids')}")

# A1: PATCH ent_kanda customer (reversible)
cust=db.customers.find_one({"entity_id":OTHER},{"_id":0,"id":1,"notes":1,"name":1})
if cust:
    cid=cust["id"]; orig=cust.get("notes","")
    marker="FORENSIC_XENTITY_PROBE"
    r=requests.patch(f"{BASE}/customers/{cid}",headers=H,json={"notes":marker},timeout=15)
    print(f"  sales PATCH /customers/{cid} (owner={OTHER}, name={cust.get('name')}) -> {r.status_code}")
    if r.status_code==200:
        after=db.customers.find_one({"id":cid},{"_id":0,"notes":1})
        if after.get("notes")==marker:
            print(f"  [HIGH] CONFIRMED cross-entity WRITE: sales modified ent_kanda customer notes!")
            # revert
            requests.patch(f"{BASE}/customers/{cid}",headers=H,json={"notes":orig},timeout=15)
            db.customers.update_one({"id":cid},{"$set":{"notes":orig}})
            print(f"  [i] reverted notes to original.")
        else:
            print(f"  [.. ] 200 but DB notes not changed ({after.get('notes')!r}) — not confirmed")
    else:
        print(f"  [OK  ] blocked ({r.status_code})")
else:
    print("  [SKIP] no ent_kanda customer")

# A2: request-special-price on ent_kanda SO (creates a price_approval; low harm, note it)
so=db.sales_orders.find_one({"entity_id":OTHER},{"_id":0,"id":1,"items":1})
if so and so.get("items"):
    sid=so["id"]; pid=so["items"][0].get("product_id")
    r=requests.post(f"{BASE}/sales-orders/{sid}/request-special-price",headers=H,
                    json={"product_id":pid,"requested_price":1,"reason":"forensic probe"},timeout=15)
    print(f"  sales POST /sales-orders/{sid}/request-special-price (owner={OTHER}) -> {r.status_code}")
    if r.status_code in (200,201):
        print(f"  [HIGH] CONFIRMED: sales created price-approval on ent_kanda SO (cross-entity write).")
else:
    print("  [SKIP] no ent_kanda SO with items")

print("\n########## (b) ROLE-EXPLOITABILITY CROSS-REF (WRITE /{id} no-guard) ##########")
ROUTERS=Path("/app/backend/routers"); MUT={"post","put","patch","delete"}
SCOPE_GUARDS={"assert_entity_access","apply_entity_scope","resolve_list_scope","resolve_scope_ids","can_access_customer","scope_query","_scope_query"}
def collections_used(func):
    cols=set()
    for n in ast.walk(func):
        if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=="db": cols.add(n.attr)
        if isinstance(n,ast.Subscript) and isinstance(n.value,ast.Name) and n.value.id=="db" and isinstance(n.slice,ast.Constant): cols.add(n.slice.value)
    return cols
def perm_args(func):
    """Return list of (module,action) from require_permission(request, module, action)."""
    out=[]
    for n in ast.walk(func):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="require_permission":
            a=[x.value for x in n.args if isinstance(x,ast.Constant)]
            if len(a)>=2: out.append((a[0],a[1]))
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="require_role":
            out.append(("<role>", ",".join(x.value for x in n.args if isinstance(x,ast.Constant))))
    return out
def route_decos(func):
    r=[]
    for dec in func.decorator_list:
        if isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute):
            o=dec.func.value; m=dec.func.attr.lower()
            if isinstance(o,ast.Name) and o.id in("router","api","app") and m in({"get"}|MUT):
                p=dec.args[0].value if dec.args and isinstance(dec.args[0],ast.Constant) else ""
                r.append((m,p))
    return r
def called(func):
    s=set()
    for n in ast.walk(func):
        if isinstance(n,ast.Call):
            f=n.func
            if isinstance(f,ast.Name): s.add(f.id)
            elif isinstance(f,ast.Attribute): s.add(f.attr)
    return s

sales_perm=DEFAULT_PERMISSIONS["sales"]; wh_perm=DEFAULT_PERMISSIONS["warehouse"]
def holds(permset,mod,act): return act in permset.get(mod,[]) or "*" in permset.get(mod,[])

exploitable=[]; admin_only=[]; norole=[]
for pyf in sorted(ROUTERS.glob("*.py")):
    if pyf.name=="__init__.py": continue
    tree=ast.parse(pyf.read_text())
    for func in ast.walk(tree):
        if not isinstance(func,(ast.AsyncFunctionDef,ast.FunctionDef)): continue
        routes=route_decos(func)
        if not routes: continue
        cols=collections_used(func) & SCOPED_COLLECTIONS
        if not cols: continue
        if called(func) & SCOPE_GUARDS: continue
        perms=perm_args(func)
        for m,p in routes:
            if m not in MUT or "{" not in p: continue
            tag=f"{m.upper():6} {p}"
            if not perms:
                norole.append((tag,func.name)); continue
            se=any(holds(sales_perm,mod,act) for mod,act in perms if mod!="<role>")
            we=any(holds(wh_perm,mod,act) for mod,act in perms if mod!="<role>")
            if se or we:
                who=[]; who+=["sales"] if se else []; who+=["warehouse"] if we else []
                exploitable.append((tag,func.name,perms,who))
            else:
                admin_only.append((tag,func.name,perms))

print(f"\n  >>> EXPLOITABLE by non-cross-entity role (sales/warehouse hold the permission): {len(exploitable)}")
for tag,fn,perms,who in sorted(exploitable):
    print(f"   [HIGH] {tag}  ({fn})  perm={perms} exploitable_by={who}")
print(f"\n  --- admin/manager-only permission (lower risk; those roles are cross-entity): {len(admin_only)}")
for tag,fn,perms in sorted(admin_only):
    print(f"     {tag} ({fn}) perm={perms}")
print(f"\n  --- mutation w/o require_permission (uses current_user+role_satisfies etc): {len(norole)}")
for tag,fn in sorted(norole):
    print(f"     {tag} ({fn})")
