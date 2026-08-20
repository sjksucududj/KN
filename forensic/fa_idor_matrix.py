"""fa_idor_matrix.py — AUDIT S074 P#2: 2-WAY cross-entity IDOR matrix.

Session #073 confirmed 14 leaks one direction (ent_kanda-scoped user -> ent_ksc docs).
This probes BOTH directions across the write surface: a user scoped ONLY to entity A
hitting docs owned by entity B, and vice-versa. Confirms leaks are symmetric and not
an artefact of one seed layout.

Classification: 200/201=LEAK(executed) · 400/409=LEAK-REACHED(business logic ran) ·
403=PROTECTED · 404=PROTECTED*(scoped-404) · 422=inconclusive.
DESTRUCTIVE for a few writes -> reseed after.
"""
import os
import sys
import requests

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from core_utils import hash_password, now_iso
from pymongo import MongoClient

BASE = "http://localhost:8001/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def mkuser(uid, email, role, entity):
    db.users.delete_one({"id": uid})
    db.sessions.delete_many({"user_id": uid})
    db.users.insert_one({"id": uid, "name": f"Forensic {role} {entity}", "email": email,
                         "role": role, "status": "active", "home_entity_id": entity,
                         "allowed_entity_ids": [entity],
                         "password_hash": hash_password("demo12345"), "created_at": now_iso()})
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": "demo12345"}, timeout=15)
    return r.json().get("token") if r.status_code == 200 else None


def doc_id(coll, entity, extra=None):
    q = {"entity_id": entity}
    if coll == "inventory_rolls":
        q = {"owner_entity_id": entity}
    if extra:
        q.update(extra)
    d = db[coll].find_one(q, {"_id": 0, "id": 1})
    return d["id"] if d else None


def so_item(entity):
    d = db.sales_orders.find_one({"entity_id": entity, "items.0": {"$exists": True}}, {"_id": 0, "items": 1})
    return d["items"][0].get("product_id") if d and d.get("items") else "x"


def classify(sc):
    if sc == 403:
        return "PROTECTED"
    if sc == 404:
        return "PROTECTED*(404)"
    if sc == 422:
        return "INCONCLUSIVE(422)"
    if sc in (200, 201):
        return "LEAK(executed)"
    if sc in (400, 409):
        return "LEAK-REACHED"
    return f"OTHER({sc})"


def build_tests(target_entity, sales_h, wh_h):
    so = doc_id("sales_orders", target_entity)
    spo = doc_id("special_orders", target_entity)
    sr = doc_id("sales_returns", target_entity)
    pa = doc_id("price_approvals", target_entity)
    cust = doc_id("customers", target_entity)
    roll = doc_id("inventory_rolls", target_entity)
    wtask = doc_id("wms_tasks", target_entity)
    item = so_item(target_entity)
    T = [
        (sales_h, "sales", "PATCH", f"/sales-orders/{so}", {"data": {"notes": "fx"}}, "sales_orders", so),
        (sales_h, "sales", "POST", f"/sales-orders/{so}/request-special-price",
         {"product_id": item, "requested_price": 1, "reason": "fx"}, "sales_orders", so),
        (sales_h, "sales", "POST", f"/sales-orders/{so}/submit-for-approval", {}, "sales_orders", so),
        (sales_h, "sales", "POST", f"/sales-orders/{so}/simulate-payment", {"amount": 1}, "sales_orders", so),
        (sales_h, "sales", "POST", f"/sales-orders/{so}/cancel", {}, "sales_orders", so),
        (sales_h, "sales", "PATCH", f"/special-orders/{spo}", {"data": {"notes": "fx"}}, "special_orders", spo),
        (sales_h, "sales", "POST", f"/sales-returns/{sr}/submit", {}, "sales_returns", sr),
        (sales_h, "sales", "PATCH", f"/price-approvals/{pa}", {"data": {"note": "fx"}}, "price_approvals", pa),
        (sales_h, "sales", "POST", f"/customers/{cust}/addresses", {"label": "fx", "address": "fx"}, "customers", cust),
        (wh_h, "warehouse", "POST", f"/wms/tasks/{wtask}/advance", {}, "wms_tasks", wtask),
        (wh_h, "warehouse", "POST", f"/wms/tasks/{wtask}/scan", {"sku": "x", "qty": 1}, "wms_tasks", wtask),
        (wh_h, "warehouse", "POST", f"/inbound/rolls/{roll}/inspect", {"grade": "A"}, "inventory_rolls", roll),
    ]
    return T


def run_direction(label, attacker_entity, target_entity, sales_tok, wh_tok):
    print(f"\n########## DIRECTION {label}: attacker scoped [{attacker_entity}] -> target docs [{target_entity}] ##########")
    Hs = {"Authorization": f"Bearer {sales_tok}"}
    Hw = {"Authorization": f"Bearer {wh_tok}"}
    tests = build_tests(target_entity, Hs, Hw)
    leaks = []
    prot = []
    skip = []
    for H, role, m, path, body, coll, tgt in tests:
        if not tgt:
            print(f"  [SKIP] {role:9} {m:6} {path} (no target doc)")
            skip.append(path)
            continue
        try:
            r = requests.request(m, f"{BASE}{path}", headers=H, json=body, timeout=20)
        except Exception as e:
            print(f"  [ERR] {path}: {e}")
            continue
        v = classify(r.status_code)
        print(f"  [{v:16}] {role:9} {m:6} {path} -> {r.status_code} ({coll}) {str(r.text)[:60]}")
        if v.startswith("LEAK"):
            leaks.append((role, m, path, r.status_code, coll))
        elif v.startswith("PROTECTED"):
            prot.append((m, path))
        else:
            skip.append(path)
    print(f"  === {label}: LEAK={len(leaks)} PROTECTED={len(prot)} SKIP/INCONCL={len(skip)} ===")
    return leaks, prot, skip


def main():
    sk = mkuser("user_fx_sk", "fx_sk@kn.id", "sales", "ent_ksc")
    wk = mkuser("user_fx_wk", "fx_wk@kn.id", "warehouse", "ent_ksc")
    sn = mkuser("user_fx_sn", "fx_sn@kn.id", "sales", "ent_kanda")
    wn = mkuser("user_fx_wn", "fx_wn@kn.id", "warehouse", "ent_kanda")
    print(f"tokens: ksc_sales={'OK' if sk else 'X'} ksc_wh={'OK' if wk else 'X'} "
          f"kanda_sales={'OK' if sn else 'X'} kanda_wh={'OK' if wn else 'X'}")

    # Direction A: ksc-scoped user -> ent_kanda docs
    la, pa, ska = run_direction("A (KSC->KANDA)", "ent_ksc", "ent_kanda", sk, wk)
    # Direction B: kanda-scoped user -> ent_ksc docs
    lb, pb, skb = run_direction("B (KANDA->KSC)", "ent_kanda", "ent_ksc", sn, wn)

    print("\n" + "=" * 70)
    print("2-WAY IDOR MATRIX SUMMARY")
    print(f"  Direction A (KSC->KANDA): LEAK={len(la)} PROTECTED={len(pa)}")
    print(f"  Direction B (KANDA->KSC): LEAK={len(lb)} PROTECTED={len(pb)}")
    both = set((m, p) for _, m, p, _, _ in la) & set((m, p) for _, m, p, _, _ in lb)
    print(f"  Surfaces leaking in BOTH directions: {len(both)}")
    for m, p in sorted(both):
        print(f"    LEAK<->  {m} {p}")
    onlyA = set((m, p) for _, m, p, _, _ in la) - set((m, p) for _, m, p, _, _ in lb)
    onlyB = set((m, p) for _, m, p, _, _ in lb) - set((m, p) for _, m, p, _, _ in la)
    if onlyA:
        print(f"  Leak only A: {sorted(onlyA)}")
    if onlyB:
        print(f"  Leak only B: {sorted(onlyB)}")

    for uid in ["user_fx_sk", "user_fx_wk", "user_fx_sn", "user_fx_wn"]:
        db.users.delete_one({"id": uid})
        db.sessions.delete_many({"user_id": uid})
    print("\n[i] test users removed. DESTRUCTIVE writes may have mutated docs -> reseed.")


if __name__ == "__main__":
    main()
