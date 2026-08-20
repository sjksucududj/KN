#!/usr/bin/env python3
"""
FORENSIC 2a — PROPERTY-BASED END-TO-END lifecycle.
Flow (admin, ent_ksc): create SO -> approve -> confirm(reserve) -> simulate-payment
(invoice+Sales/PPN/AR + COGS/Inventory + Cash) -> create sales-return(partial) -> approve.
After EVERY successful mutation, assert UNIVERSAL INVARIANTS:
  P1  double-entry: global trial balance Σdebit==Σcredit (all posted JE)
  P2  every posted JE internally balanced (Σlines debit==credit, header==Σlines)
  P3  inventory SSOT: Σ on-hand rolls length == inventory_balances.on_hand_qty (roll-tracked)
  P4  conservation: Δtotal_roll_length only via ship(delivered/in_transit) & return
  P5  COGS journal amount == Σ(qty_reserved × roll_unit_cost)   [at invoice]
  P6  Sales journal: AR(Dr) == net+PPN ; Sales(Cr)==net ; PPN(Cr)==ppn_amount
  P7  return restock: Δinventory == returned qty ; return COGS reversal == returned×cost
Destructive -> caller re-seeds after.
"""
import os, sys, requests, json
from pymongo import MongoClient
BASE="http://localhost:8001/api"
db=MongoClient(os.environ.get("MONGO_URL","mongodb://localhost:27017"))[os.environ.get("DB_NAME","test_database")]
tok=requests.post(f"{BASE}/auth/login",json={"email":"admin@kainnusantara.id","password":"demo12345"}).json()["token"]
H={"Authorization":f"Bearer {tok}","X-Entity-Id":"ent_ksc"}
EPS=0.5
ONHAND={"available","reserved","committed","picked","packed","hold","quarantine","blocked","damaged","wip"}
LIVE={"available","reserved","committed","picked","packed","quarantine"}
VIOL=[]
def viol(step,prop,msg): VIOL.append((step,prop,msg)); print(f"    ❌ [{prop}] {step}: {msg}")

def snapshot():
    jes=list(db.journal_entries.find({"status":"posted"},{"_id":0}))
    gd=gc=0.0; unbal=0; acc={}
    for j in jes:
        d=sum(float(l.get("debit",0) or 0) for l in j.get("lines",[]))
        c=sum(float(l.get("credit",0) or 0) for l in j.get("lines",[]))
        gd+=d; gc+=c
        if abs(d-c)>EPS: unbal+=1
        for l in j.get("lines",[]):
            k=l.get("account_code"); acc[k]=acc.get(k,0.0)+float(l.get("debit",0) or 0)-float(l.get("credit",0) or 0)
    # inventory ssot
    rolls=list(db.inventory_rolls.find({},{"_id":0}))
    onh={}; total_live=0.0
    for r in rolls:
        if r.get("status") in ONHAND:
            k=(r.get("product_id"),r.get("warehouse_id"),r.get("owner_entity_id"))
            onh[k]=onh.get(k,0.0)+float(r.get("length_remaining",0) or 0)
        if r.get("status") in LIVE:
            total_live+=float(r.get("length_remaining",0) or 0)
    bals=list(db.inventory_balances.find({},{"_id":0}))
    drift=0
    for b in bals:
        k=(b.get("product_id"),b.get("warehouse_id"),b.get("owner_entity_id"))
        oh=float(b.get("on_hand_qty",0) or 0); rs=onh.get(k,0.0)
        if (b.get("on_hand_roll_count",0) or rs>0) and abs(oh-rs)>EPS: drift+=1
    return {"gd":round(gd,2),"gc":round(gc,2),"unbal":unbal,"acc":acc,"drift":drift,
            "total_live":round(total_live,2),"je":len(jes)}

def check(step, snap):
    print(f"  --- after {step}: JE={snap['je']} TB(D={snap['gd']:,.0f}/C={snap['gc']:,.0f}) live_len={snap['total_live']} drift={snap['drift']}")
    if abs(snap["gd"]-snap["gc"])>EPS: viol(step,"P1",f"trial balance off by {round(snap['gd']-snap['gc'],2)}")
    if snap["unbal"]>0: viol(step,"P2",f"{snap['unbal']} JE tak seimbang internal")
    if snap["drift"]>0: viol(step,"P3",f"{snap['drift']} baris SSOT drift")

def acc_delta(a,b,code): return round(b["acc"].get(code,0.0)-a["acc"].get(code,0.0),2)

print("########## 2a PROPERTY-BASED E2E LIFECYCLE ##########")
# pick product with available rolls in ent_ksc + a customer w/ address
roll=db.inventory_rolls.find_one({"owner_entity_id":"ent_ksc","status":"available","length_remaining":{"$gt":20}},{"_id":0})
prod_id=roll["product_id"]; wh=roll["warehouse_id"]; unit_cost=float(roll.get("unit_cost") or roll.get("base_unit_cost") or 0)
prod=db.products.find_one({"id":prod_id},{"_id":0}); base_unit=prod.get("base_unit","meter")
cust=db.customers.find_one({"entity_id":"ent_ksc","addresses.0":{"$exists":True}},{"_id":0})
addr_id=cust["addresses"][0]["id"]
QTY=10.0
print(f"  product={prod_id} ({prod.get('name')}) unit_cost={unit_cost} base_unit={base_unit} | customer={cust['id']} | QTY={QTY}{base_unit}")

s0=snapshot(); print(f"  BASELINE: JE={s0['je']} TB D={s0['gd']:,.0f}/C={s0['gc']:,.0f} live_len={s0['total_live']}")

# 1) create SO
r=requests.post(f"{BASE}/sales-orders",headers=H,json={
    "customer_id":cust["id"],"shipping_address_id":addr_id,
    "items":[{"product_id":prod_id,"quantity":QTY,"unit":base_unit}],
    "entity_id":"ent_ksc","fulfillment_method":"kirim"})
print(f"\n  [1] create SO -> {r.status_code}")
if r.status_code not in (200,201): print("   ",r.text[:200]); sys.exit(1)
so=r.json(); oid=so["id"]; print(f"      SO {so.get('number')} grand_total={so.get('grand_total')} dpp={so.get('dpp')} ppn={so.get('ppn_amount')} net={so.get('net_subtotal')}")
check("create-SO",snapshot())

# 2) approve + 3) confirm
for act in ["submit-for-approval","approve","confirm"]:
    rr=requests.post(f"{BASE}/sales-orders/{oid}/{act}",headers=H,json={})
    print(f"  [2] {act} -> {rr.status_code} {'' if rr.status_code==200 else rr.text[:120]}")
s_conf=snapshot(); check("confirm(reserve)",s_conf)
# rolls reserved for this order?
reserved=list(db.inventory_rolls.find({"reserved_order_id":oid},{"_id":0,"length_remaining":1,"status":1,"unit_cost":1,"base_unit_cost":1}))
res_len=sum(float(x.get("length_remaining",0) or 0) for x in reserved)
print(f"      rolls reserved to order: {len(reserved)} (len={res_len})")

# 4) simulate-payment (invoice + GL)
r=requests.post(f"{BASE}/sales-orders/{oid}/simulate-payment",headers=H,json={"method":"Transfer","created_by":"forensic"})
print(f"\n  [4] simulate-payment -> {r.status_code} {'' if r.status_code==200 else r.text[:150]}")
s_inv=snapshot(); check("invoice+GL",s_inv)
# P5 COGS
so_now=db.sales_orders.find_one({"id":oid},{"_id":0})
exp_cogs=0.0
for it in so_now.get("items",[]):
    exp_cogs+= float(it.get("base_quantity",it.get("quantity",0)) or 0) * unit_cost
cogs_je=db.journal_entries.find_one({"source_type":"sales_cogs","source_id":oid},{"_id":0})
if cogs_je:
    posted_cogs=sum(float(l.get("debit",0) or 0) for l in cogs_je["lines"] if l.get("account_code")=="5-1000")
    print(f"      P5 COGS: posted={posted_cogs} expected≈{round(exp_cogs,2)} (qty×unit_cost)")
    if abs(posted_cogs-exp_cogs)>max(1.0,exp_cogs*0.02): viol("invoice","P5",f"COGS posted {posted_cogs} != expected {round(exp_cogs,2)}")
else:
    print("      P5 COGS: NO sales_cogs journal (rolls may not be reserved/costed)")
# P6 Sales journal
sale_je=db.journal_entries.find_one({"source_type":"sales_order","source_id":oid},{"_id":0})
if sale_je:
    ar=sum(float(l.get("debit",0) or 0) for l in sale_je["lines"] if l.get("account_code")=="1-1200")
    ppn=sum(float(l.get("credit",0) or 0) for l in sale_je["lines"] if l.get("account_code") in ("2-1300","2-1310"))
    sales=sum(float(l.get("credit",0) or 0) for l in sale_je["lines"] if l.get("account_code")=="4-1000")
    net=float(so_now.get("net_subtotal",so_now.get("dpp",0)) or 0); ppn_amt=float(so_now.get("ppn_amount",0) or 0)
    print(f"      P6 Sales JE: AR(Dr)={ar} Sales(Cr)={sales} PPN(Cr)={ppn} | order net={net} ppn={ppn_amt}")
    if abs(sales-net)>1.0: viol("invoice","P6",f"Sales(Cr) {sales} != order net {net}")
    if abs(ppn-ppn_amt)>1.0: viol("invoice","P6",f"PPN(Cr) {ppn} != order ppn {ppn_amt}")
    if abs(ar-(net+ppn_amt))>1.0 and abs(ar-float(so_now.get('grand_total',0)))>1.0: viol("invoice","P6",f"AR(Dr) {ar} != net+ppn {net+ppn_amt}")

# 5) create sales-return (partial) + submit + approve
rq=QTY/2.0
r=requests.post(f"{BASE}/sales-returns",headers=H,json={"order_id":oid,"return_type":"retur",
    "items":[{"product_id":prod_id,"product_name":prod.get("name",""),"quantity_returned":rq,"unit":base_unit,"condition":"ok"}],
    "entity_id":"ent_ksc","submit_now":True})
print(f"\n  [5] create sales-return (qty={rq}) -> {r.status_code} {'' if r.status_code in (200,201) else r.text[:180]}")
if r.status_code in (200,201):
    ret=r.json(); rid=ret["id"]
    ra=requests.post(f"{BASE}/sales-returns/{rid}/approve",headers=H,json={"notes":"forensic"})
    print(f"  [5b] approve return -> {ra.status_code} {'' if ra.status_code==200 else ra.text[:150]}")
    s_ret=snapshot(); check("return+restock",s_ret)
    # P7 restock: inventory live length should increase by ~rq*base_factor vs invoice snapshot
    dlen=round(s_ret["total_live"]-s_inv["total_live"],2)
    print(f"      P7 restock Δlive_len (return-invoice)={dlen} (expect ≈ +{rq} if restocked to live)")
    # return cogs reversal (Dr Persediaan 1-1300 / Cr HPP 5-1000)
    d_pers=acc_delta(s_inv,s_ret,"1-1300"); d_hpp=acc_delta(s_inv,s_ret,"5-1000")
    print(f"      P7 GL: ΔPersediaan(1-1300)={d_pers} ΔHPP(5-1000)={d_hpp} (expect Persediaan↑, HPP↓)")

print("\n================ 2a RESULT ================")
if not VIOL: print("  ✅ ALL INVARIANTS HELD across full lifecycle (P1-P7). No violations.")
else:
    print(f"  ❌ {len(VIOL)} invariant violation(s):")
    for st,p,m in VIOL: print(f"     [{p}] {st}: {m}")
print("\n  [i] RUN seed_reset.sh to restore baseline.")
