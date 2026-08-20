#!/usr/bin/env python3
"""FORENSIC 2b — AR / AP deep audit (reconciliation + full AP GL flow)."""
import os, requests, sys
from pymongo import MongoClient
BASE="http://localhost:8001/api"
db=MongoClient(os.environ.get("MONGO_URL","mongodb://localhost:27017"))[os.environ.get("DB_NAME","test_database")]
tok=requests.post(f"{BASE}/auth/login",json={"email":"admin@kainnusantara.id","password":"demo12345"}).json()["token"]
H={"Authorization":f"Bearer {tok}","X-Entity-Id":"ent_ksc"}
EPS=1.0; F=[]
def viol(p,m): F.append((p,m)); print(f"    ❌ [{p}] {m}")

def gl_net(code, ent=None):
    q={"status":"posted"}
    if ent: q["entity_id"]=ent
    tot=0.0
    for j in db.journal_entries.find(q,{"_id":0,"lines":1}):
        for l in j.get("lines",[]):
            if l.get("account_code")==code: tot+=float(l.get("debit",0) or 0)-float(l.get("credit",0) or 0)
    return round(tot,2)

def tb_balanced():
    d=c=0.0
    for j in db.journal_entries.find({"status":"posted"},{"_id":0,"lines":1}):
        for l in j.get("lines",[]): d+=float(l.get("debit",0) or 0); c+=float(l.get("credit",0) or 0)
    return abs(d-c)<=EPS, round(d-c,2)

print("########## 2b-AR: SUBLEDGER vs GL & AGING ##########")
# AR subledger from SO with payments
for ent in ["ent_ksc","ent_kanda"]:
    ar_gl=gl_net("1-1200",ent)
    # subledger: Σ (grand_total - paid) for orders that were invoiced (have sales JE)
    invoiced_ids={j["source_id"] for j in db.journal_entries.find({"source_type":"sales_order","entity_id":ent},{"_id":0,"source_id":1})}
    sub=0.0
    for o in db.sales_orders.find({"entity_id":ent},{"_id":0,"id":1,"grand_total":1,"payments":1}):
        if o["id"] not in invoiced_ids: continue
        paid=sum(float(p.get("amount",0) or 0) for p in o.get("payments",[]))
        sub+=float(o.get("grand_total",0) or 0)-paid
    sub=round(sub,2)
    tag="OK" if abs(ar_gl-sub)<=EPS else "DIFF"
    print(f"  [{tag}] {ent}: GL Piutang(1-1200) net={ar_gl:,.2f}  subledger Σ(GT-paid)={sub:,.2f}  diff={round(ar_gl-sub,2):,.2f}")
    if tag=="DIFF": viol("AR-RECON",f"{ent} AR GL {ar_gl} != subledger {sub}")

# AR aging bucket sum
r=requests.get(f"{BASE}/ar/aging",headers=H)
print(f"\n  GET /ar/aging -> {r.status_code}")
if r.status_code==200:
    ag=r.json()
    print(f"    aging keys: {list(ag.keys())[:12]}")
    # try to sum buckets vs total
    buckets=ag.get("buckets") or ag.get("aging") or {}
    tot=ag.get("total") or ag.get("total_outstanding") or ag.get("grand_total")
    if isinstance(buckets,dict):
        s=round(sum(float(v or 0) for v in buckets.values() if isinstance(v,(int,float))),2)
        print(f"    Σbuckets={s} total={tot}")
        if tot is not None and abs(s-float(tot))>EPS: viol("AR-AGING",f"Σbuckets {s} != total {tot}")

print("\n########## 2b-AP: FULL VENDOR-BILL GL FLOW (fresh) ##########")
po=db.purchase_orders.find_one({"status":{"$in":["approved","received","partially_received","closed"]},"entity_id":"ent_ksc"},{"_id":0})
if not po:
    po=db.purchase_orders.find_one({"entity_id":"ent_ksc","status":{"$nin":["waiting_approval","rejected","cancelled"]}},{"_id":0})
print(f"  using PO {po.get('po_number')} status={po.get('status')} items={len(po.get('items',[]))}")
items=[{"product_id":it["product_id"],"billed_qty":float(it.get("quantity",0) or 0),"price":float(it.get("price",0) or 0)}
       for it in po.get("items",[]) if float(it.get("quantity",0) or 0)>0]

hut0=gl_net("2-1100","ent_ksc"); ok0,diff0=tb_balanced()
print(f"  baseline GL Hutang(2-1100) net={hut0:,.2f}  TB_balanced={ok0}(diff={diff0})")

r=requests.post(f"{BASE}/vendor-bills",headers=H,json={
    "po_id":po["id"],"items":items,"match_mode":"ordered","supplier_invoice_no":"FRN-AP-001","submit_now":True})
print(f"\n  [AP1] create vendor-bill(submit_now, ordered match) -> {r.status_code} {'' if r.status_code in (200,201) else r.text[:200]}")
if r.status_code in (200,201):
    bill=r.json(); bid=bill["id"]
    print(f"      bill {bill.get('bill_number')} status={bill.get('status')} grand_total={bill.get('grand_total')} ppn={bill.get('ppn_amount')}")
    # approve if pending
    if bill.get("status")=="pending_approval":
        ra=requests.post(f"{BASE}/vendor-bills/{bid}/approve",headers=H,json={})
        print(f"      approve -> {ra.status_code} {'' if ra.status_code==200 else ra.text[:150]}")
        bill=db.vendor_bills.find_one({"id":bid},{"_id":0})
    hut1=gl_net("2-1100","ent_ksc"); ok1,diff1=tb_balanced()
    dhut=round(hut1-hut0,2)  # liability credit → net (debit-credit) DECREASES (more negative)
    print(f"      GL Hutang(2-1100) net={hut1:,.2f} Δ={dhut:,.2f} (expect ↓ ~ -grand_total) | TB_balanced={ok1}(diff={diff1})")
    if not ok1: viol("AP-POST","trial balance NOT balanced after vendor bill post")
    gt=float(bill.get("grand_total",0) or 0)
    if abs(abs(dhut)-gt)>max(EPS,gt*0.02) and bill.get("status") in ("posted","approved"):
        viol("AP-POST",f"ΔHutang {dhut} != -grand_total {gt} (posting mismatch?)")
    # pay
    rp=requests.post(f"{BASE}/vendor-bills/{bid}/pay",headers=H,json={"amount":gt,"method":"Transfer","pay_date":"2026-07-05"})
    print(f"\n  [AP2] pay bill -> {rp.status_code} {'' if rp.status_code==200 else rp.text[:180]}")
    hut2=gl_net("2-1100","ent_ksc"); ok2,diff2=tb_balanced()
    print(f"      GL Hutang(2-1100) net={hut2:,.2f} Δpay={round(hut2-hut1,2):,.2f} (expect ↑ back ~ +grand_total after Dr Hutang) | TB_balanced={ok2}(diff={diff2})")
    if not ok2: viol("AP-PAY","trial balance NOT balanced after payment")
    # over-payment test on same bill
    rop=requests.post(f"{BASE}/vendor-bills/{bid}/pay",headers=H,json={"amount":gt,"method":"Transfer","pay_date":"2026-07-05"})
    print(f"  [AP3] over-pay (bill already paid) -> {rop.status_code} {rop.text[:120]}")
    if rop.status_code in (200,201): viol("AP-OVERPAY","bill sudah lunas tapi pembayaran kedua diterima (over-payment)")

print("\n================ 2b RESULT ================")
if not F: print("  ✅ AR/AP reconciliation & AP GL flow — no violations.")
else:
    for p,m in F: print(f"   ❌ [{p}] {m}")
print("  [i] RUN seed_reset.sh to restore baseline.")
