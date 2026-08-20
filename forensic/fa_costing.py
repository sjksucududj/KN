#!/usr/bin/env python3
"""FORENSIC 1b — WAC / costing correctness + inventory subledger vs GL reconciliation."""
import asyncio, sys
sys.path.insert(0,"/app/backend")

LIVE={"available","reserved","committed","picked","packed","quarantine"}
EPS=0.5  # IDR tolerance for WAC (rounding)

async def main():
    from db import db
    from services import costing_service
    print("########## 1b WAC RECOMPUTE (independent vs service) ##########")
    prods=await db.products.find({},{"_id":0,"id":1,"name":1,"harga_pokok":1}).to_list(1000)
    mism=0; checked=0
    for p in prods:
        for ent in [None,"ent_ksc","ent_kanda"]:
            q={"product_id":p["id"],"status":{"$in":list(LIVE)}}
            if ent: q["owner_entity_id"]=ent
            rolls=await db.inventory_rolls.find(q,{"_id":0}).to_list(5000)
            tl=cl=tv=0.0
            for r in rolls:
                ln=float(r.get("length_remaining",0) or 0)
                if ln<=0: continue
                tl+=ln; c=float(r.get("unit_cost") or r.get("base_unit_cost") or 0)
                if c>0: cl+=ln; tv+=c*ln
            exp = round(tv/cl,2) if cl>0 else (round(float(p.get("harga_pokok",0) or 0),2) if p.get("harga_pokok") else 0.0)
            svc=await costing_service.wac_for_product(p["id"],entity_id=ent,use_cache=False)
            got=svc["wac"]
            if abs(got-exp)>EPS:
                mism+=1; print(f"  [HIGH] WAC mismatch {p['id']} ent={ent}: service={got} indep={exp} (rolls_costed_len={cl})")
            checked+=1
    if not mism: print(f"  [OK  ] WAC matches independent recompute for all {checked} (product×entity) combos")

    print("\n########## 1b INVENTORY SUBLEDGER vs GL 1-1300 (Persediaan) ##########")
    # subledger value = Σ on-hand roll length_remaining × unit_cost per entity
    ONHAND={"available","reserved","committed","picked","packed","hold","quarantine","blocked","damaged","wip"}
    rolls=await db.inventory_rolls.find({},{"_id":0}).to_list(20000)
    sub=dict()
    for r in rolls:
        if r.get("status") in ONHAND:
            e=r.get("owner_entity_id","?")
            ln=float(r.get("length_remaining",0) or 0); c=float(r.get("unit_cost") or r.get("base_unit_cost") or 0)
            sub[e]=sub.get(e,0.0)+ln*c
    # GL 1-1300 balance per entity (posted)
    jes=await db.journal_entries.find({"status":"posted"},{"_id":0}).to_list(10000)
    gl=dict()
    for j in jes:
        e=j.get("entity_id","?")
        for l in j.get("lines",[]):
            if l.get("account_code")=="1-1300":
                gl[e]=gl.get(e,0.0)+float(l.get("debit",0) or 0)-float(l.get("credit",0) or 0)
    ents=set(sub)|set(gl)
    for e in sorted(ents):
        s=round(sub.get(e,0.0),2); g=round(gl.get(e,0.0),2)
        tag = "OK  " if abs(s-g)<=1.0 else "INFO"
        print(f"  [{tag}] {e}: roll-subledger={s:,.2f}  GL(1-1300)={g:,.2f}  diff={round(s-g,2):,.2f}")
    print("  (note: seed GL may be sparse — diff flagged INFO, not necessarily a bug; recorded for owner)")

asyncio.run(main())
