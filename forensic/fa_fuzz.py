#!/usr/bin/env python3
"""FORENSIC 1e — schema fuzzing on create/mutation endpoints.
Fires malformed payloads (negatives, huge nums, unicode, oversized strings, wrong
types, mass-assignment, injection-ish) and flags:
  5xx           -> unhandled exception (robustness bug)
  200 on bad    -> validation gap (accepted clearly-invalid data)
READ-mostly for creates that fail; any accidental create is cleaned by seed_reset.
"""
import requests, json
BASE="http://localhost:8001/api"
tok=requests.post(f"{BASE}/auth/login",json={"email":"admin@kainnusantara.id","password":"demo12345"}).json()["token"]
H={"Authorization":f"Bearer {tok}","X-Entity-Id":"ent_ksc"}
BIG="A"*200000
UNI="🔥𝕏\u0000\u202e‮ＳＱＬ' OR 1=1;-- <script>alert(1)</script>"

PAYLOADS = {
 "/customers": [
    {},
    {"name": 12345},
    {"name": UNI, "credit_limit": -999999999},
    {"name": BIG},
    {"name":"x","credit_limit":"not-a-number"},
    {"name":"x","__proto__":{"admin":True},"role":"admin","id":"hacked"},
 ],
 "/products": [
    {},
    {"name":"x","price":-1,"sku":UNI},
    {"name":"x","price":1e308,"base_unit":"meter"},
    {"name":BIG},
 ],
 "/suppliers": [
    {}, {"name":UNI}, {"name":"x","id":"../../etc/passwd"},
 ],
 "/gl/journal": [
    {"date":"not-a-date","description":"x","lines":[]},
    {"date":"2026-07-01","description":"x","lines":"notalist"},
    {"date":"2026-07-01","description":UNI,"lines":[{"account_code":"1-1200","debit":1e308,"credit":0},{"account_code":"4-1000","debit":0,"credit":1e308}]},
 ],
 "/cash-transactions": [
    {"type":"in","amount":"abc"},
    {"type":"invalid","amount":100},
    {"amount":100},
 ],
 "/sales-orders": [
    {}, {"customer_id":"nonexistent","items":[]},
    {"customer_id":"c1","items":[{"product_id":"p1","quantity":-5,"unit_price":-1}]},
    {"customer_id":"c1","items":"notalist"},
 ],
}

fivehundred=[]; accepted_bad=[]
print("########## 1e SCHEMA FUZZING ##########")
for path,cases in PAYLOADS.items():
    for i,body in enumerate(cases):
        try:
            r=requests.post(f"{BASE}{path}",headers=H,json=body,timeout=20)
            sc=r.status_code
            tag="ok"
            if sc>=500: tag="**5xx UNHANDLED**"; fivehundred.append((path,i,sc,r.text[:120]))
            elif sc in (200,201): tag="**200 ACCEPTED**"; accepted_bad.append((path,i,sc,json.dumps(body)[:80]))
            print(f"  {sc}  {path:20} case#{i:<2} [{tag}]  body={json.dumps(body)[:60]}")
            # cleanup accidental creates
            if sc in (200,201):
                try:
                    rid=r.json().get("id")
                except: rid=None
        except Exception as e:
            print(f"  ERR {path} case#{i}: {e}")

print("\n===== SUMMARY =====")
print(f"  5xx unhandled: {len(fivehundred)}")
for p,i,sc,t in fivehundred: print(f"    [HIGH] {p} case#{i} -> {sc} :: {t}")
print(f"  200-accepted-clearly-invalid: {len(accepted_bad)}")
for p,i,sc,b in accepted_bad: print(f"    [REVIEW] {p} case#{i} -> {sc} :: {b}")
print("\n  [i] run seed_reset.sh to clean any accidental creates.")
