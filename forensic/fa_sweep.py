#!/usr/bin/env python3
"""
FORENSIC AUDIT — Runtime STAGE 2: EXHAUSTIVE sweeps (READ-ONLY).
 (1) Unauthenticated GET sweep across ALL parameterless GET routes (from OpenAPI).
 (2) Cross-entity IDOR sweep across ALL single-param GET /{id} routes, substituting
     real ent_kanda-owned document IDs while authenticated as a sales user whose
     scope is ONLY ent_ksc. Any 200 that returns an ent_kanda doc = isolation breach.
No writes.
"""
import os, re, json, requests
from collections import defaultdict
from pymongo import MongoClient

BASE="http://localhost:8001/api"
db = MongoClient(os.environ.get("MONGO_URL","mongodb://localhost:27017"))[os.environ.get("DB_NAME","test_database")]
OTHER="ent_kanda"; SELF="ent_ksc"
findings=[]
def F(sev,code,msg): findings.append((sev,code,msg)); print(f"  [{sev:4}] {code:16} {msg}")

def login(role):
    r=requests.post(f"{BASE}/auth/login",json={"email":f"{role}@kainnusantara.id","password":"demo12345"},timeout=15)
    return (r.json()["token"], r.json()["user"]) if r.status_code==200 else (None,None)

oa=requests.get("http://localhost:8001/openapi.json",timeout=15).json()
paths=oa.get("paths",{})

# ───────────── (1) UNAUTH SWEEP ─────────────
print("\n########## UNAUTH SWEEP (all parameterless GET) ##########")
unauth_leaks=0; protected=0
for p,methods in sorted(paths.items()):
    if "get" not in methods: continue
    if "{" in p: continue                 # skip param routes here
    if not p.startswith("/api/"): continue
    try:
        r=requests.get(f"http://localhost:8001{p}",timeout=15)
    except Exception as e:
        print(f"  [ERR ] {p}: {e}"); continue
    if r.status_code==200:
        try: b=r.json(); n=len(b) if isinstance(b,list) else ("obj" if isinstance(b,dict) else "?")
        except Exception: n=f"{len(r.content)}B"
        # classify sensitivity
        sensitive = any(k in p for k in ["sales-order","customer","supplier","gl","finance","vendor-bill",
            "ar/","bank","cash","tax","payroll","payslip","hr/","landed","invoice","purchase","incentive",
            "journal","closing","consolidat","price-approval","report","dashboard","crm","stock"])
        sev = "HIGH" if sensitive else "MED"
        F(sev,"UNAUTH_GET", f"{p} -> 200 (payload={n})")
        unauth_leaks+=1
    else:
        protected+=1
print(f"  --- unauth leaks: {unauth_leaks} | protected: {protected} ---")

# ───────────── (2) CROSS-ENTITY IDOR SWEEP ─────────────
print("\n########## CROSS-ENTITY IDOR SWEEP (sales@ent_ksc reading ent_kanda docs) ##########")
stoken, su = login("sales")
print(f"  sales scope: home={su.get('home_entity_id')} allowed={su.get('allowed_entity_ids')}")
H={"Authorization":f"Bearer {stoken}"}

# curated: single-param path template -> (collection, id_field)
IDMAP = {
    "/api/sales-orders/{order_id}": ("sales_orders","id"),
    "/api/purchase-orders/{po_id}": ("purchase_orders","id"),
    "/api/vendor-bills/{bill_id}": ("vendor_bills","id"),
    "/api/tax-invoices/{fkt_id}": ("tax_invoices","id"),
    "/api/sales-returns/{return_id}": ("sales_returns","id"),
    "/api/purchase-returns/{return_id}": ("purchase_returns","id"),
    "/api/landed-costs/{voucher_id}": ("landed_costs","id"),
    "/api/transfers/{transfer_id}": ("transfers","id"),
    "/api/cycle-count/sessions/{session_id}": ("cycle_count_sessions","id"),
    "/api/customers/{customer_id}": ("customers","id"),
    "/api/suppliers/{supplier_id}": ("suppliers","id"),
    "/api/approval-requests/{request_id}": ("approval_requests","id"),
    "/api/price-approvals/{approval_id}": ("price_approvals","id"),
    "/api/rfqs/{rfq_id}": ("rfqs","id"),
    "/api/purchase-requisitions/{pr_id}": ("purchase_requisitions","id"),
    "/api/special-orders/{special_id}": ("special_orders","id"),
    "/api/hr/payslips/{slip_id}": ("hr_payslips","id"),
}
# also try composite/context endpoints known from static scan
EXTRA = {
    "/api/sales-orders/{order_id}": ["/api/sales-orders/{}/invoices"],
    "/api/purchase-orders/{po_id}": ["/api/purchase-orders/{}/billing-context",
                                     "/api/purchase-orders/{}/landed-cost-context"],
    "/api/customers/{customer_id}": ["/api/customers/{}/360","/api/customers/{}/credit-status",
                                     "/api/ar/aging/{}"],
    "/api/suppliers/{supplier_id}": ["/api/suppliers/{}/scorecard","/api/suppliers/{}/price-list"],
}

def kanda_id(coll, idf):
    d = db[coll].find_one({"entity_id":OTHER},{"_id":0,idf:1})
    if not d:
        d = db[coll].find_one({"owner_entity_id":OTHER},{"_id":0,idf:1})
    return d.get(idf) if d else None

tested=0; leaks=0; skipped=0
seen_coll={}
for tmpl,(coll,idf) in IDMAP.items():
    if tmpl not in paths and not any(tmpl==k for k in paths):
        # still test if base collection GET exists via {id}
        pass
    kid = kanda_id(coll, idf); seen_coll[coll]=kid
    if not kid:
        print(f"  [SKIP] no {OTHER} doc in {coll} for {tmpl}"); skipped+=1; continue
    url = "http://localhost:8001"+re.sub(r"\{[^}]+\}", kid, tmpl)
    r = requests.get(url, headers=H, timeout=15); tested+=1
    if r.status_code==200:
        # confirm returned doc is the other-entity doc
        try: body=r.json(); ent=body.get("entity_id") or body.get("owner_entity_id") if isinstance(body,dict) else None
        except Exception: ent="?"
        F("HIGH","IDOR_XENTITY", f"sales GET {tmpl} [{coll} {kid} owner={OTHER}] -> 200 (entity_in_body={ent})")
        leaks+=1
    elif r.status_code in (403,404):
        print(f"  [OK  ] {tmpl} [{coll}] -> {r.status_code} (blocked)")
    else:
        print(f"  [.. ] {tmpl} [{coll}] -> {r.status_code}")

# composite endpoints
print("  --- composite / context endpoints ---")
for base,(_c) in [(k,v) for k,v in IDMAP.items() if k in EXTRA]:
    coll,idf = IDMAP[base]; kid=seen_coll.get(coll) or kanda_id(coll,idf)
    if not kid: continue
    for ex in EXTRA[base]:
        url="http://localhost:8001"+ex.format(kid)
        r=requests.get(url,headers=H,timeout=15); tested+=1
        if r.status_code==200:
            F("HIGH","IDOR_XENTITY", f"sales GET {ex} [{coll} {kid} {OTHER}] -> 200 (cross-entity data)")
            leaks+=1
        elif r.status_code in (403,404): print(f"  [OK  ] {ex} -> {r.status_code}")
        else: print(f"  [.. ] {ex} -> {r.status_code}")

print(f"\n  --- IDOR tested={tested} leaks={leaks} skipped={skipped} ---")

print("\n================ STAGE-2 SUMMARY ================")
c=defaultdict(int)
for sev,code,_ in findings: c[(sev,code)]+=1
for (sev,code),n in sorted(c.items()): print(f"  {sev:4} {code:16} {n}")
print(f"  TOTAL: {len(findings)}")
