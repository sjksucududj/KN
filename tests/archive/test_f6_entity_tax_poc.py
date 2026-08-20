"""POC FASE 6 — PPN/Faktur per-entitas + Multi-entitas user + Rekening per-entitas.

Menguji via API live (http://localhost:8001):
  1. Entitas: ent_ksc = PPN (PKP), ent_kanda = non_ppn.
  2. User multi-entitas: create (home + allowed_entity_ids), login → can_switch_entity, update entitas.
  3. SO PPN: entitas PKP + needs_tax_invoice → PPN 11% + flag tersimpan.
  4. SO non-PPN: entitas non_ppn → PPN 0 / is_pkp False.
  5. tax_override=non_ppn di entitas PKP → PPN 0.
  6. Rekening per-entitas: akun ter-scope per entitas + akun grup "all" terlihat lintas.

Jalankan: python /app/test_f6_entity_tax_poc.py
"""
import random
import sys
import requests

BASE = "http://localhost:8001/api"
PW = "demo12345"
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(("  [PASS] " if cond else "  [FAIL] ") + name + ("" if cond else f"  -> {detail}"))


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return r.json()


def H(tok, ent):
    return {"Authorization": f"Bearer {tok}", "X-Entity-Id": ent}


def make_so(tok, ent, cust, addr, prod, **extra):
    pl = {
        "customer_id": cust["id"], "shipping_address_id": addr,
        "items": [{"product_id": prod["id"], "quantity": 3, "unit": prod.get("base_unit", "meter")}],
        "allow_backorder": True, "confirm_mixed_lot": True, "entity_id": ent,
    }
    pl.update(extra)
    return requests.post(f"{BASE}/sales-orders", headers=H(tok, ent), json=pl, timeout=60)


def main():
    print("\n=== POC FASE 6 — PPN/Faktur per-entitas + Multi-entitas + Rekening ===\n")
    admin_t = login("admin@kainnusantara.id")["token"]

    # 1) Entitas + tax mode
    ents = requests.get(f"{BASE}/entities", headers=H(admin_t, "ent_ksc")).json()
    by_id = {e["id"]: e for e in ents}
    ppn_ent = next((e["id"] for e in ents if e.get("default_tax_mode") == "ppn"), None)
    non_ent = next((e["id"] for e in ents if e.get("default_tax_mode") == "non_ppn"), None)
    check("ada entitas PPN & non-PPN", bool(ppn_ent and non_ent), f"ppn={ppn_ent} non={non_ent}")
    if not (ppn_ent and non_ent):
        return summarize()

    # 2) Multi-entitas user
    em = f"sales_f6_{random.randint(10000, 99999)}@kn.id"
    r = requests.post(f"{BASE}/users", headers=H(admin_t, "ent_ksc"),
                      json={"name": "Sales F6 Multi", "email": em, "role": "sales",
                            "home_entity_id": ppn_ent, "allowed_entity_ids": [ppn_ent, non_ent]}, timeout=30)
    check("create user multi-entitas -> 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        u = r.json(); uid = u["id"]
        check("user home_entity_id benar", u.get("home_entity_id") == ppn_ent, str(u.get("home_entity_id")))
        check("user allowed_entity_ids = 2 entitas", set(u.get("allowed_entity_ids", [])) == {ppn_ent, non_ent}, str(u.get("allowed_entity_ids")))
        # login multi-entitas → can_switch
        lg = login(em)
        ec = lg.get("entity_context", {})
        check("login: can_switch_entity True (2 entitas)", ec.get("can_switch_entity") is True, str(ec))
        check("login: entities switcher = 2", len(ec.get("entities", [])) == 2, str(ec.get("entities")))
        # update → kunci ke 1 entitas
        r2 = requests.patch(f"{BASE}/users/{uid}", headers=H(admin_t, "ent_ksc"),
                            json={"data": {"allowed_entity_ids": [ppn_ent]}}, timeout=30)
        check("update user allowed→1 -> 200", r2.status_code == 200, f"{r2.status_code} {r2.text[:200]}")
        if r2.status_code == 200:
            check("after update: allowed = 1 entitas", r2.json().get("allowed_entity_ids") == [ppn_ent], str(r2.json().get("allowed_entity_ids")))
            ec2 = login(em).get("entity_context", {})
            check("login lagi: can_switch_entity False (1 entitas)", ec2.get("can_switch_entity") is False, str(ec2.get("can_switch_entity")))

    # 3-5) SO tax per entitas
    custs = requests.get(f"{BASE}/customers", headers=H(admin_t, "ent_ksc")).json()
    prods = requests.get(f"{BASE}/products", headers=H(admin_t, "ent_ksc")).json()
    prod = prods[0]

    def cust_for(ent):
        c = next((x for x in custs if x.get("entity_id") == ent), None) or custs[0]
        return c, (c.get("addresses") or [{}])[0].get("id", "")

    # PPN entity + needs_tax_invoice
    c1, a1 = cust_for(ppn_ent)
    r = make_so(admin_t, ppn_ent, c1, a1, prod, needs_tax_invoice=True)
    check("SO entitas PKP -> 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        so = r.json()
        check("entitas PKP: PPN 11% > 0", float(so.get("ppn_amount", 0)) > 0 and float(so.get("ppn_rate", 0)) == 11.0, f"ppn={so.get('ppn_amount')} rate={so.get('ppn_rate')}")
        check("needs_tax_invoice tersimpan True", so.get("needs_tax_invoice") is True, str(so.get("needs_tax_invoice")))
        check("tax_mode = ppn", so.get("tax_mode") == "ppn", str(so.get("tax_mode")))

    # non-PPN entity
    c2, a2 = cust_for(non_ent)
    r = make_so(admin_t, non_ent, c2, a2, prod)
    check("SO entitas non-PPN -> 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        so = r.json()
        check("entitas non-PPN: PPN = 0 & is_pkp False", float(so.get("ppn_amount", 1)) == 0 and so.get("is_pkp") is False, f"ppn={so.get('ppn_amount')} pkp={so.get('is_pkp')}")
        check("tax_mode = non_ppn", so.get("tax_mode") == "non_ppn", str(so.get("tax_mode")))

    # tax_override in PPN entity
    r = make_so(admin_t, ppn_ent, c1, a1, prod, tax_override="non_ppn")
    check("SO PKP + tax_override=non_ppn -> 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        so = r.json()
        check("override: PPN dipaksa 0 walau entitas PKP", float(so.get("ppn_amount", 1)) == 0, f"ppn={so.get('ppn_amount')}")

    # 6) Rekening per-entitas
    b1 = requests.get(f"{BASE}/bank-accounts", headers=H(admin_t, ppn_ent), params={"entity_id": ppn_ent}).json()
    b2 = requests.get(f"{BASE}/bank-accounts", headers=H(admin_t, non_ent), params={"entity_id": non_ent}).json()
    own1 = [a for a in b1 if a.get("entity_id") == ppn_ent]
    grp = [a for a in b1 if a.get("entity_id") == "all"]
    check("rekening entitas PKP ada (own)", len(own1) >= 1, str([a.get("name") for a in b1]))
    check("rekening grup 'all' terlihat lintas-entitas", len(grp) >= 1 and any(a.get("entity_id") == "all" for a in b2), "grup tidak terlihat")
    check("rekening ter-scope beda per entitas", set(a.get("id") for a in own1) != set(a.get("id") for a in b2 if a.get("entity_id") == non_ent), "scope sama")

    return summarize()


def summarize():
    total = len(RESULTS); passed = sum(RESULTS); failed = total - passed
    print(f"\n=== SUMMARY: {passed}/{total} PASS, {failed} FAIL ===\n")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
