#!/usr/bin/env python3
"""
FORENSIC AUDIT — F-D RACE / IDEMPOTENCY (concurrency lens; not in Session #071).
 D1  Doc-number atomicity: fire N concurrent next_doc_number() for same (entity,type)
     and assert ALL returned numbers are UNIQUE (detect init check-then-upsert race
     or lost-update duplicates).
 D2  HTTP double-submit: fire concurrent identical mutations that should be idempotent
     / status-guarded and check exactly-once effect (uses an existing waiting_approval
     PO if present; else reports SKIP).
Runs against the LIVE DB. D1 pollutes number_sequences (harmless; seed_reset resets).
"""
import asyncio, sys, os, threading, requests, time
sys.path.insert(0,"/app/backend")

async def d1_doc_number_race():
    from core_utils import next_doc_number
    from db import db
    print("\n########## D1 DOC-NUMBER ATOMICITY (concurrent next_doc_number) ##########")
    # ensure a fresh sequence key to also exercise the init path
    await db.number_sequences.delete_one({"entity_id":"ent_ksc","doc_type":"FORENSICSEQ"})
    N=40
    async def one(): return await next_doc_number("sales_orders","number","FORENSICSEQ-",entity_id="ent_ksc")
    results = await asyncio.gather(*[one() for _ in range(N)])
    uniq=set(results)
    dups=[x for x in results if results.count(x)>1]
    print(f"  requested {N} concurrent numbers, unique={len(uniq)}")
    if len(uniq)!=N:
        print(f"  [HIGH] DUPLICATE doc numbers under concurrency: {sorted(set(dups))}")
    else:
        print(f"  [OK  ] all {N} numbers unique (atomic sequence holds). sample={sorted(results)[:3]}...{sorted(results)[-1:]}")
    await db.number_sequences.delete_one({"entity_id":"ent_ksc","doc_type":"FORENSICSEQ"})

def d2_http_double_submit():
    from pymongo import MongoClient
    db=MongoClient(os.environ.get("MONGO_URL","mongodb://localhost:27017"))[os.environ.get("DB_NAME","test_database")]
    BASE="http://localhost:8001/api"
    print("\n########## D2 HTTP DOUBLE-SUBMIT (status-guarded idempotency) ##########")
    def login(role):
        return requests.post(f"{BASE}/auth/login",json={"email":f"{role}@kainnusantara.id","password":"demo12345"}).json()["token"]
    admin=login("admin"); manager=login("manager")
    Hm={"Authorization":f"Bearer {manager}"}
    # find a waiting_approval PO in a manager-accessible entity
    po=db.purchase_orders.find_one({"status":"waiting_approval"},{"_id":0,"id":1,"entity_id":1,"required_approval_role":1})
    if not po:
        print("  [SKIP] no waiting_approval PO to test double-approve (would need to create one).")
    else:
        pid=po["id"]
        before_tasks = db.wms_tasks.count_documents({"source_id":pid}) if "wms_tasks" in db.list_collection_names() else 0
        before_je = db.journal_entries.count_documents({"source_id":pid})
        results={}
        def hit(i):
            r=requests.post(f"{BASE}/purchase-orders/{pid}/approve",headers=Hm,timeout=20)
            results[i]=r.status_code
        ts=[threading.Thread(target=hit,args=(i,)) for i in range(6)]
        [t.start() for t in ts]; [t.join() for t in ts]
        ok=[i for i,s in results.items() if s==200]
        print(f"  concurrent approve x6 on PO {pid}: statuses={sorted(results.values())}")
        after_je=db.journal_entries.count_documents({"source_id":pid})
        if len(ok)>1:
            print(f"  [HIGH] {len(ok)} concurrent approvals returned 200 (double-advance risk).")
        else:
            print(f"  [OK  ] exactly {len(ok)} success, rest rejected (status-guard holds).")
        print(f"  journal_entries for PO before={before_je} after={after_je}")

    # D2b: concurrent duplicate AR receipt? too heavy — instead double 'confirm' on a reserved SO (idempotency)
    so=db.sales_orders.find_one({"status":"approved"},{"_id":0,"id":1})
    if so:
        sid=so["id"]; res={}
        def hitc(i):
            r=requests.post(f"{BASE}/sales-orders/{sid}/confirm",headers={"Authorization":f"Bearer {manager}"},timeout=20)
            res[i]=r.status_code
        ts=[threading.Thread(target=hitc,args=(i,)) for i in range(5)]
        [t.start() for t in ts]; [t.join() for t in ts]
        ok=[i for i,s in res.items() if s==200]
        print(f"  concurrent confirm x5 on SO {sid}: statuses={sorted(res.values())} → {len(ok)} success")
        if len(ok)>1: print(f"  [MED ] multiple confirm succeeded (idempotency check needed)")
    else:
        print("  [SKIP] no 'approved' SO for confirm idempotency test")

async def main():
    await d1_doc_number_race()
    # run sync HTTP part in thread executor
    await asyncio.get_event_loop().run_in_executor(None, d2_http_double_submit)

if __name__=="__main__":
    asyncio.run(main())
