#!/usr/bin/env python3
"""
FORENSIC 1a — Per-endpoint EMPIRICAL confirmation of FC-2 cross-entity IDOR.
Creates two test users scoped ONLY to ent_kanda (sales + warehouse), then hits
by-id endpoints using ent_ksc document IDs. Classification:
  403                 -> PROTECTED (entity guard fired)
  404                 -> PROTECTED* (scoped not-found; noted)
  200                 -> LEAK (executed on cross-entity doc)
  400/409 (business)  -> LEAK-REACHED (handler ran business logic on cross-entity doc = guard absent)
  422                 -> inconclusive payload
Destructive: some writes mutate ent_ksc docs -> caller MUST re-seed after.
"""
import sys, os, requests
sys.path.insert(0,"/app/backend")
from core_utils import hash_password, now_iso
from pymongo import MongoClient
db=MongoClient(os.environ.get("MONGO_URL","mongodb://localhost:27017"))[os.environ.get("DB_NAME","test_database")]
BASE="http://localhost:8001/api"

def mkuser(uid,email,role):
    db.users.delete_one({"id":uid})
    db.users.insert_one({"id":uid,"name":f"Forensic {role}","email":email,"role":role,
        "status":"active","home_entity_id":"ent_kanda","allowed_entity_ids":["ent_kanda"],
        "password_hash":hash_password("demo12345"),"created_at":now_iso()})
    r=requests.post(f"{BASE}/auth/login",json={"email":email,"password":"demo12345"})
    return r.json().get("token") if r.status_code==200 else None

sk=mkuser("user_forensic_sk","forensic_sk@kn.id","sales")
wk=mkuser("user_forensic_wk","forensic_wk@kn.id","warehouse")
print(f"test users -> sales_kanda token={'OK' if sk else 'FAIL'} | warehouse_kanda token={'OK' if wk else 'FAIL'}")
su=requests.post(f"{BASE}/auth/login",json={"email":"forensic_sk@kn.id","password":"demo12345"}).json()["user"]
print(f"sales_kanda scope allowed={su.get('allowed_entity_ids')} (should be ['ent_kanda'])")
Hsk={"Authorization":f"Bearer {sk}"}; Hwk={"Authorization":f"Bearer {wk}"}

def one(coll, q=None):
    d=db[coll].find_one(q or {"entity_id":"ent_ksc"},{"_id":0,"id":1})
    return d["id"] if d else None

# resolve target ent_ksc ids
so=one("sales_orders"); spo=one("special_orders"); sr=one("sales_returns")
pa=one("price_approvals"); roll=one("inventory_rolls",{"owner_entity_id":"ent_ksc"})
wtask=one("wms_tasks"); cust=one("customers")
# specific-status wms tasks
def wtask_status(st):
    d=db.wms_tasks.find_one({"entity_id":"ent_ksc","status":st},{"_id":0,"id":1}); return d["id"] if d else wtask
inbound_task=db.wms_tasks.find_one({"entity_id":"ent_ksc","kind":{"$in":["inbound","receiving"]}},{"_id":0,"id":1})
inbound_task=inbound_task["id"] if inbound_task else wtask

so_item=None
_so=db.sales_orders.find_one({"entity_id":"ent_ksc"},{"_id":0,"items":1})
if _so and _so.get("items"): so_item=_so["items"][0].get("product_id")

TESTS = [
  # (role_header, METHOD, path, body, target_desc)
  (Hsk,"PATCH",f"/sales-orders/{so}",{"data":{"notes":"fx"}},"sales_orders"),
  (Hsk,"POST",f"/sales-orders/{so}/request-special-price",{"product_id":so_item,"requested_price":1,"reason":"fx"},"sales_orders"),
  (Hsk,"POST",f"/sales-orders/{so}/request-credit-approval",{},"sales_orders"),
  (Hsk,"POST",f"/sales-orders/{so}/submit-for-approval",{},"sales_orders"),
  (Hsk,"POST",f"/sales-orders/{so}/release-reservation",{},"sales_orders"),
  (Hsk,"POST",f"/sales-orders/{so}/mark-delivered",{},"sales_orders"),
  (Hsk,"POST",f"/sales-orders/{so}/cancel",{},"sales_orders"),
  (Hsk,"POST",f"/sales-orders/{so}/simulate-payment",{"amount":1},"sales_orders"),
  (Hsk,"PATCH",f"/special-orders/{spo}",{"data":{"notes":"fx"}},"special_orders"),
  (Hsk,"POST",f"/special-orders/{spo}/create-pr",{},"special_orders(→PR)"),
  (Hsk,"POST",f"/sales-returns/{sr}/submit",{},"sales_returns"),
  (Hsk,"PATCH",f"/price-approvals/{pa}",{"data":{"note":"fx"}},"price_approvals"),
  (Hsk,"POST",f"/price-approvals/{pa}/submit",{},"price_approvals"),
  (Hsk,"POST",f"/customers/{cust}/addresses",{"label":"fx","address":"fx"},"customers"),
  # warehouse
  (Hwk,"POST",f"/wms/tasks/{wtask}/advance",{},"wms_tasks"),
  (Hwk,"POST",f"/wms/tasks/{wtask}/scan",{"sku":"x","qty":1},"wms_tasks"),
  (Hwk,"POST",f"/wms/tasks/outbound-from-order/{so}",{},"sales_orders(→WMS)"),
  (Hwk,"POST",f"/inbound/tasks/{inbound_task}/complete",{},"wms_tasks"),
  (Hwk,"POST",f"/inbound/tasks/{inbound_task}/scan-receive",{"sku":"x","qty":1},"wms_tasks"),
  (Hwk,"POST",f"/inbound/tasks/{inbound_task}/qc-decision",{"decision":"accept"},"wms_tasks"),
  (Hwk,"POST",f"/inbound/tasks/{inbound_task}/escalate",{"reason":"fx"},"wms_tasks"),
  (Hwk,"POST",f"/inbound/rolls/{roll}/inspect",{"grade":"A"},"inventory_rolls"),
]

def classify(sc, txt):
    if sc==403: return "PROTECTED"
    if sc==404: return "PROTECTED*(404)"
    if sc==422: return "INCONCLUSIVE(422)"
    if sc in (200,201): return "LEAK(executed)"
    if sc in (400,409): return "LEAK-REACHED(business-logic ran)"
    return f"OTHER({sc})"

print("\n########## 1a EMPIRICAL PER-ENDPOINT (ent_kanda-scoped user hitting ent_ksc docs) ##########")
leaks=[]; prot=[]; skip=[]
for H,m,path,body,desc in TESTS:
    if "None" in path:
        print(f"  [SKIP] {m:6} {path} (no target doc)"); skip.append(path); continue
    try:
        r=requests.request(m,f"{BASE}{path}",headers=H,json=body,timeout=20)
        verdict=classify(r.status_code, r.text)
        role = "sales_kanda" if H is Hsk else "wh_kanda"
        print(f"  [{verdict:28}] {role:11} {m:6} {path}  -> {r.status_code}  ({desc})  {r.text[:70]}")
        if verdict.startswith("LEAK"): leaks.append((m,path,r.status_code,desc))
        elif verdict.startswith("PROTECTED"): prot.append((m,path))
        else: skip.append(path)
    except Exception as e:
        print(f"  [ERR] {path}: {e}")

print(f"\n  === RESULT: LEAK={len(leaks)}  PROTECTED={len(prot)}  SKIP/INCONCL={len(skip)} ===")
for m,p,sc,desc in leaks: print(f"    LEAK  {m} {p} ({sc})")

# cleanup test users
db.users.delete_many({"id":{"$in":["user_forensic_sk","user_forensic_wk"]}})
db.sessions.delete_many({"user_id":{"$in":["user_forensic_sk","user_forensic_wk"]}})
print("\n  [i] test users removed. RUN seed_reset.sh to restore any mutated ent_ksc docs.")
