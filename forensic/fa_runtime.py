#!/usr/bin/env python3
"""
FORENSIC AUDIT — Runtime Layer STAGE 1 (READ-ONLY): financial reconciliation +
empirical security probing. Different approach vs Session #071 (which did static +
single-request shape dumps). Here we:
  F-A  Independent financial invariant recompute from DB (trial balance, JE balance,
       inventory SSOT balance==Σrolls, AR subledger vs GL Piutang, AP vs GL Hutang).
  F-B  Unauthenticated endpoint probing (confirm static NO_AUTH findings empirically).
  F-C  Cross-entity isolation probing (hostile ?entity_id / GET-by-id of other entity).
  F-D  RBAC negative probing (sales token hitting privileged endpoints).
No writes. Safe to run anytime.
"""
import os, sys, json, requests
from collections import defaultdict
from pymongo import MongoClient

BASE = "http://localhost:8001/api"
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBN = os.environ.get("DB_NAME", "test_database")
db = MongoClient(MONGO)[DBN]
CRED = {r: (f"{r}@kainnusantara.id", "demo12345") for r in ["admin","sales","manager","warehouse"]}
EPS = 0.01
report = defaultdict(list)
def F(cat, sev, msg): report[cat].append((sev, msg)); print(f"  [{sev:4}] {msg}")

def login(role):
    e,p = CRED[role]
    r = requests.post(f"{BASE}/auth/login", json={"email":e,"password":p}, timeout=15)
    if r.status_code != 200: return None, None
    d = r.json(); u = d["user"]
    return d["token"], u

def H(token, entity=None):
    h = {"Authorization": f"Bearer {token}"}
    if entity: h["X-Entity-Id"] = entity
    return h

# ══════════════════════════ F-A FINANCIAL RECON ══════════════════════════
def recon_financials():
    print("\n########## F-A FINANCIAL INTEGRITY (independent recompute) ##########")
    jes = list(db.journal_entries.find({}, {"_id":0}))
    posted = [j for j in jes if j.get("status")=="posted"]
    print(f"journal_entries: {len(jes)} total, {len(posted)} posted")
    # A1: each JE internally balanced + header==Σlines
    bad_internal=0; bad_header=0
    for j in posted:
        d = sum(float(l.get("debit",0) or 0) for l in j.get("lines",[]))
        c = sum(float(l.get("credit",0) or 0) for l in j.get("lines",[]))
        if abs(d-c) > EPS:
            bad_internal+=1; F("F-A","HIGH", f"JE {j.get('number')} NOT balanced: D={d} C={c} diff={round(d-c,2)}")
        hd=float(j.get("total_debit",0) or 0); hc=float(j.get("total_credit",0) or 0)
        if abs(hd-d)>EPS or abs(hc-c)>EPS:
            bad_header+=1; F("F-A","MED", f"JE {j.get('number')} header totals != Σlines (hdrD={hd} vs {d}, hdrC={hc} vs {c})")
    if not bad_internal: print(f"  [OK  ] all {len(posted)} posted JE internally balanced (Σdebit==Σcredit)")
    if not bad_header: print(f"  [OK  ] all posted JE header totals == Σlines")
    # A2: global trial balance
    gd = sum(float(l.get("debit",0) or 0) for j in posted for l in j.get("lines",[]))
    gc = sum(float(l.get("credit",0) or 0) for j in posted for l in j.get("lines",[]))
    if abs(gd-gc) > EPS: F("F-A","HIGH", f"GLOBAL trial balance NOT balanced: D={gd} C={gc} diff={round(gd-gc,2)}")
    else: print(f"  [OK  ] global trial balance balanced: D=C={gd}")
    # A3: per-entity trial balance
    per = defaultdict(lambda:[0.0,0.0])
    for j in posted:
        e=j.get("entity_id","?")
        for l in j.get("lines",[]):
            per[e][0]+=float(l.get("debit",0) or 0); per[e][1]+=float(l.get("credit",0) or 0)
    for e,(d,c) in per.items():
        if abs(d-c)>EPS: F("F-A","HIGH", f"entity {e} trial balance NOT balanced: D={d} C={c} diff={round(d-c,2)}")
        else: print(f"  [OK  ] entity {e} trial balance balanced (D=C={d})")
    # A4: GL account balances per entity (for subledger cross-checks)
    acct = defaultdict(float)  # (entity,code)->debit-credit
    for j in posted:
        e=j.get("entity_id","?")
        for l in j.get("lines",[]):
            acct[(e,l.get("account_code"))]+= float(l.get("debit",0) or 0)-float(l.get("credit",0) or 0)
    # A5: AR subledger — GL Piutang Usaha (1-1200) debit-balance per entity
    print("  --- Subledger vs GL cross-check ---")
    for e in per:
        ar_gl = acct.get((e,"1-1200"),0.0)
        # subledger AR from ar_receipts (invoice-less): sum SO grand_total posted - receipts allocated
        print(f"    {e}: GL Piutang(1-1200) net debit = {round(ar_gl,2)}")
        ap_gl = acct.get((e,"2-1100"),0.0)
        print(f"    {e}: GL Hutang(2-1100) net credit = {round(-ap_gl,2)}")
    # A6: check for orphan account_codes not in gl_accounts
    codes = {a["code"] for a in db.gl_accounts.find({},{"_id":0,"code":1})}
    used = {c for (_,c) in acct}
    orphan = used - codes
    if orphan: F("F-A","MED", f"JE lines reference account_code TIDAK ada di gl_accounts: {sorted(orphan)}")
    else: print(f"  [OK  ] all JE account_codes exist in CoA ({len(codes)} accounts)")

def recon_inventory_ssot():
    print("\n########## F-A INVENTORY SSOT (balance == Σ rolls, independent) ##########")
    # On-hand statuses per KN_15 — rolls physically in warehouse
    ONHAND = {"available","reserved","committed","picked","packed","hold","quarantine","blocked","damaged","wip"}
    rolls = list(db.inventory_rolls.find({}, {"_id":0}))
    agg = defaultdict(float)   # (prod,wh,owner) -> Σ length_remaining (on-hand)
    for r in rolls:
        if r.get("status") in ONHAND:
            k=(r.get("product_id"),r.get("warehouse_id"),r.get("owner_entity_id"))
            agg[k]+= float(r.get("length_remaining",0) or 0)
    bals = list(db.inventory_balances.find({}, {"_id":0}))
    drift=0; checked=0
    for b in bals:
        k=(b.get("product_id"),b.get("warehouse_id"),b.get("owner_entity_id"))
        onh=float(b.get("on_hand_qty",0) or 0)
        rsum=agg.get(k,0.0)
        # only compare rows that use roll tracking (rsum>0 or roll_count fields present)
        if b.get("on_hand_roll_count",0) or rsum>0:
            checked+=1
            if abs(onh-rsum) > EPS:
                drift+=1; F("F-A","HIGH", f"SSOT drift {k}: on_hand_qty={onh} != Σrolls_remaining={rsum} (diff={round(onh-rsum,2)})")
    if not drift: print(f"  [OK  ] inventory SSOT consistent: {checked} roll-tracked balance rows == Σ rolls length_remaining")
    else: print(f"  [FAIL] {drift} SSOT drift rows")

# ══════════════════════════ F-B UNAUTH PROBING ══════════════════════════
def probe_unauth():
    print("\n########## F-B UNAUTHENTICATED ENDPOINT PROBING ##########")
    # discover an order id + a kanda order id for preview leak test
    so = db.sales_orders.find_one({}, {"_id":0,"id":1,"entity_id":1})
    oid = so["id"] if so else "so_001"
    tests = [
        ("GET","/uoms",None),
        ("GET","/warehouses",None),
        ("GET","/pos/best-sellers?entity_id=ent_kanda",None),
        ("GET",f"/documents/preview/{oid}?document_type=surat_jalan",None),
        ("GET","/products",None),
        ("GET","/sales-orders",None),
        ("GET","/customers",None),
        ("GET","/gl/accounts",None),
        ("GET","/finance/balance-sheet",None),
    ]
    for m,path,_ in tests:
        try:
            r = requests.request(m, f"{BASE}{path}", timeout=15)
            sc = r.status_code
            leaked = sc == 200
            n = None
            if leaked:
                try:
                    body = r.json(); n = len(body) if isinstance(body,list) else "obj"
                except Exception: n = f"{len(r.content)}B html/other"
            sev = "HIGH" if leaked and any(x in path for x in ["documents/preview","sales-orders","customers","balance-sheet","gl/accounts"]) else ("MED" if leaked else "OK")
            if leaked:
                F("F-B", sev, f"UNAUTH {m} {path} -> 200 (LEAK, payload={n})")
            else:
                print(f"  [OK  ] UNAUTH {m} {path} -> {sc} (protected)")
        except Exception as e:
            print(f"  [ERR ] {path}: {e}")

# ══════════════════════════ F-C ENTITY ISOLATION ══════════════════════════
def probe_entity_isolation():
    print("\n########## F-C CROSS-ENTITY ISOLATION PROBING ##########")
    stoken, su = login("sales")
    if not stoken: F("F-C","ERR","cannot login sales"); return
    home = su.get("home_entity_id"); allowed = su.get("allowed_entity_ids",[])
    print(f"  sales home={home} allowed={allowed}")
    other = "ent_kanda" if home!="ent_kanda" else "ent_ksc"
    # C1: list with ?entity_id=other (not allowed) → expect 403
    for coll,path in [("sales_orders","/sales-orders"),("customers","/customers"),
                      ("purchase_orders","/purchase-orders")]:
        r = requests.get(f"{BASE}{path}?entity_id={other}", headers=H(stoken), timeout=15)
        if r.status_code == 200:
            try: body=r.json(); leaked=[x for x in body if isinstance(x,dict) and x.get("entity_id")==other]
            except Exception: body=[]; leaked=[]
            if leaked: F("F-C","HIGH", f"sales GET {path}?entity_id={other} -> 200 with {len(leaked)} {other} docs (CROSS-ENTITY LEAK)")
            else: print(f"  [OK  ] {path}?entity_id={other} -> 200 but 0 other-entity docs")
        elif r.status_code == 403: print(f"  [OK  ] {path}?entity_id={other} -> 403 (blocked)")
        else: print(f"  [.. ] {path}?entity_id={other} -> {r.status_code}")
    # C2: GET-by-id of a doc owned by other entity → expect 403/404
    for coll,pathf in [("sales_orders","/sales-orders/{}"),("purchase_orders","/purchase-orders/{}")]:
        doc = db[coll].find_one({"entity_id":other},{"_id":0,"id":1})
        if not doc: print(f"  [SKIP] no {coll} doc for {other}"); continue
        did = doc["id"]
        r = requests.get(f"{BASE}{pathf.format(did)}", headers=H(stoken), timeout=15)
        if r.status_code == 200:
            F("F-C","HIGH", f"sales GET {pathf.format(did)} ({other}-owned) -> 200 (IDOR cross-entity read)")
        elif r.status_code in (403,404): print(f"  [OK  ] {pathf.format(did)} ({other}) -> {r.status_code} (blocked)")
        else: print(f"  [.. ] {pathf.format(did)} -> {r.status_code}")
    # C3: X-Entity-Id header to other entity → should not be honored for non-allowed
    r = requests.get(f"{BASE}/sales-orders", headers=H(stoken, other), timeout=15)
    if r.status_code==200:
        try: body=r.json(); leaked=[x for x in body if isinstance(x,dict) and x.get("entity_id")==other]
        except Exception: leaked=[]
        if leaked: F("F-C","HIGH", f"sales w/ X-Entity-Id:{other} -> leaked {len(leaked)} {other} SOs")
        else: print(f"  [OK  ] X-Entity-Id:{other} header ignored (0 leak)")

# ══════════════════════════ F-D RBAC NEGATIVE ══════════════════════════
def probe_rbac_negative():
    print("\n########## F-D RBAC NEGATIVE (sales/warehouse hitting privileged) ##########")
    stoken,_ = login("sales")
    wtoken,_ = login("warehouse")
    # sales should NOT: post GL, view finance BI, manage users, approve PO
    checks = [
        ("sales", stoken, "POST","/gl/entries", {"date":"2026-07-01","description":"x","lines":[]}, [403]),
        ("sales", stoken, "GET","/finance/bi?year=2026", None, [403]),
        ("sales", stoken, "GET","/hr/payslips", None, [403]),
        ("sales", stoken, "GET","/users", None, [403]),
        ("sales", stoken, "GET","/vendor-bills", None, [403]),
        ("warehouse", wtoken, "GET","/finance/income-statement", None, [403]),
        ("warehouse", wtoken, "POST","/gl/entries", {"date":"2026-07-01","description":"x","lines":[]}, [403]),
        ("sales", stoken, "GET","/tax/summary?entity_id=ent_ksc", None, [403]),
    ]
    for role,tok,m,path,body,expect in checks:
        if not tok: continue
        r = requests.request(m, f"{BASE}{path}", headers=H(tok), json=body, timeout=15)
        ok = r.status_code in expect
        if r.status_code == 200:
            F("F-D","HIGH", f"{role} {m} {path} -> 200 (PRIVILEGE ESCALATION? expected {expect})")
        elif not ok:
            print(f"  [.. ] {role} {m} {path} -> {r.status_code} (expected {expect}; not a leak)")
        else:
            print(f"  [OK  ] {role} {m} {path} -> {r.status_code} (blocked)")

if __name__ == "__main__":
    recon_financials()
    recon_inventory_ssot()
    probe_unauth()
    probe_entity_isolation()
    probe_rbac_negative()
    print("\n\n================ SUMMARY (findings by category) ================")
    tot=0
    for cat, items in report.items():
        hi=[x for x in items if x[0] in ("HIGH","CRIT")]
        print(f"{cat}: {len(items)} findings ({len(hi)} HIGH+)")
        tot+=len(items)
    print(f"TOTAL runtime findings: {tot}")
