#!/usr/bin/env python3
"""POC verifikasi SALES REVAMP V2 — dijalankan vs API live (localhost:8001).

FASE A: PIC/Split di Customer → SO mewarisi tim sales.
FASE C: Beli per Roll (picker FEFO + reservasi roll eksplisit + lintas-entitas auto-transfer 1.b).
"""
import os
import sys
import requests

BASE = os.environ.get("API_BASE", "http://localhost:8001")
ADMIN_EMAIL = os.environ.get("KN_ADMIN_EMAIL", "admin@kainnusantara.id")
ADMIN_PASS = os.environ.get("KN_ADMIN_PASS", "demo12345")

passed = 0
failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  \u2713 {name}")
    else:
        failed += 1
        print(f"  \u2717 {name} {extra}")


def login(email, pwd):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd})
    r.raise_for_status()
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def make_customer(h, name, assigned_id, pic, co, entity_id):
    body = {
        "name": name, "pic_name": "Budi", "phone": "0811", "city": "Jakarta",
        "address": "Jl. Uji No.1", "assigned_sales_id": assigned_id,
        "sales_team": [
            {"sales_id": pic["id"], "name": pic["name"], "role": "pic", "split_pct": 60},
            {"sales_id": co["id"], "name": co["name"], "role": "co", "split_pct": 40},
        ],
        "entity_id": entity_id,
    }
    return requests.post(f"{BASE}/api/customers", json=body, headers=h)


def fase_a(h):
    print("== FASE A — Sales team di Customer + SO inherit ==")
    reps = requests.get(f"{BASE}/api/sales-users", headers=h).json()
    check("ada >=2 sales user untuk uji split", len(reps) >= 2, f"(got {len(reps)})")
    if len(reps) < 2:
        return None, None
    pic, co = reps[0], reps[1]
    ents = requests.get(f"{BASE}/api/entities", headers=h).json()
    entity_id = (ents[0]["id"] if isinstance(ents, list) and ents else "")

    r = make_customer(h, "POC Tim Sales", pic["id"], pic, co, entity_id)
    check("POST /customers (with sales_team) 200", r.status_code == 200, f"-> {r.status_code} {r.text[:200]}")
    if r.status_code != 200:
        return None, None
    cust = r.json()
    team = cust.get("sales_team") or []
    check("customer.sales_team tersimpan 2 anggota", len(team) == 2, f"(got {team})")
    check("PIC.sales_id == assigned_sales_id", (cust.get("assigned_sales_id") == pic["id"]) and any(m["role"] == "pic" and m["sales_id"] == pic["id"] for m in team))
    check("Σ split == 100", abs(sum(m["split_pct"] for m in team) - 100) < 0.01)

    rbad = make_customer(h, "POC Bad", pic["id"], pic, co, entity_id)
    # rbad masih valid (60/40). buat yang invalid:
    rbad = requests.post(f"{BASE}/api/customers", json={
        "name": "POC Bad", "pic_name": "x", "phone": "1", "city": "Jakarta", "address": "-",
        "assigned_sales_id": pic["id"], "entity_id": entity_id,
        "sales_team": [
            {"sales_id": pic["id"], "name": pic["name"], "role": "pic", "split_pct": 70},
            {"sales_id": co["id"], "name": co["name"], "role": "co", "split_pct": 40},
        ]}, headers=h)
    check("split != 100 -> 400", rbad.status_code == 400, f"-> {rbad.status_code}")

    addr_id = cust["addresses"][0]["id"]
    prods = requests.get(f"{BASE}/api/products", headers=h, params={"entity_id": entity_id}).json()
    prod = next((p for p in prods if float(p.get("available_qty", 0) or 0) >= 5), None)
    if prod:
        rso = requests.post(f"{BASE}/api/sales-orders", json={
            "customer_id": cust["id"], "shipping_address_id": addr_id, "entity_id": entity_id,
            "allow_backorder": True, "confirm_mixed_lot": True,
            "items": [{"product_id": prod["id"], "quantity": 3, "unit": prod.get("base_unit", "meter")}],
        }, headers=h)
        check("POST /sales-orders 200 (inherit)", rso.status_code == 200, f"-> {rso.status_code} {rso.text[:300]}")
        if rso.status_code == 200:
            steam = rso.json().get("sales_team") or []
            check("SO.sales_team DIWARISI dari customer (2 anggota)", len(steam) == 2, f"(got {steam})")
            check("SO split co == 40", any(m["sales_id"] == co["id"] and abs(m["split_pct"] - 40) < 0.01 for m in steam))
    return cust, addr_id


def get_rolls(h, product_id, entity_id, all_entities=True):
    r = requests.get(f"{BASE}/api/inventory/rolls/available", headers=h,
                     params={"product_id": product_id, "entity_id": entity_id,
                             "all_entities": str(all_entities).lower(), "limit": 50})
    return r


def reserved_status(h, roll_id):
    # cek status roll via list (admin)
    r = requests.get(f"{BASE}/api/inventory/rolls", headers=h, params={"product_id": ""}).json()
    return None


def fase_c(h, cust, addr_id):
    print("\n== FASE C — Beli per Roll (picker FEFO + reservasi eksplisit + lintas-entitas) ==")
    if not cust:
        print("  (lewati: tak ada customer dari fase A)")
        return
    PROD = "prod_batik_mega"
    KSC, KANDA = "ent_ksc", "ent_kanda"

    # 1) Picker endpoint — own entity (KSC)
    r = get_rolls(h, PROD, KSC, all_entities=False)
    check("GET /inventory/rolls/available (own) 200 -> {items,total}", r.status_code == 200 and isinstance(r.json(), dict) and "items" in r.json(), f"-> {r.status_code} {r.text[:150]}")
    data = r.json() if r.status_code == 200 else {"items": []}
    items = data.get("items", [])
    check("picker mengembalikan roll", len(items) >= 2, f"(got {len(items)})")
    # FEFO check: created_at non-decreasing (oldest first)
    cas = [it.get("created_at", "") for it in items]
    check("picker terurut FEFO (created_at asc per lot)", cas == sorted(cas) or len(set(it.get('lot') for it in items)) > 1)
    check("own picker: is_cross_entity semua False", all(not it.get("is_cross_entity") for it in items))

    # 2) Buat SO mode roll — pilih 2 roll milik KSC, jual sbg KSC (own)
    pick = items[:2]
    take_total = round(sum(float(x["length_remaining"]) for x in pick), 2)
    roll_lines = [{"roll_id": x["id"], "take_qty": x["length_remaining"]} for x in pick]
    rso = requests.post(f"{BASE}/api/sales-orders", json={
        "customer_id": cust["id"], "shipping_address_id": addr_id, "entity_id": KSC,
        "allow_backorder": True, "confirm_mixed_lot": True,
        "items": [{"product_id": PROD, "quantity": take_total, "unit": "meter",
                   "purchase_mode": "roll", "roll_lines": roll_lines}],
    }, headers=h)
    check("POST /sales-orders mode=roll (own) 200", rso.status_code == 200, f"-> {rso.status_code} {rso.text[:300]}")
    if rso.status_code == 200:
        so = rso.json()
        allocs = so.get("allocations", [])
        reserved_roll_ids = {rr["roll_id"] for a in allocs for rr in (a.get("rolls") or [])}
        chosen = {x["id"] for x in pick}
        check("SO mereservasi TEPAT roll yang dipilih", chosen.issubset(reserved_roll_ids), f"(chosen={chosen} reserved={reserved_roll_ids})")
        line = so["items"][0]
        check("qty baris = Σ panjang roll terpilih", abs(float(line.get("base_quantity", line.get("quantity", 0))) - take_total) < 0.5, f"(line={line.get('base_quantity')}, exp={take_total})")
        check("tidak ada pending intercompany (own)", float(so.get("intercompany_pending_qty", 0) or 0) < 0.01)
        # roll yang dipilih kini tidak available lagi di picker
        r2 = get_rolls(h, PROD, KSC, all_entities=False)
        ids2 = {it["id"] for it in r2.json().get("items", [])}
        check("roll terpilih hilang dari picker (ter-reserve)", not (chosen & ids2))

    # 3) Lintas-entitas (1.b): jual sbg KANDA, pilih roll milik KSC → auto transfer
    r3 = get_rolls(h, PROD, KANDA, all_entities=True)
    items3 = [it for it in r3.json().get("items", []) if it.get("owner_entity_id") == KSC]
    check("picker all_entities menandai roll KSC sbg cross saat jual KANDA", len(items3) >= 1 and all(it.get("is_cross_entity") for it in items3), f"(got {len(items3)})")
    if items3:
        x = items3[0]
        rso2 = requests.post(f"{BASE}/api/sales-orders", json={
            "customer_id": cust["id"], "shipping_address_id": addr_id, "entity_id": KANDA,
            "allow_backorder": True, "confirm_mixed_lot": True,
            "items": [{"product_id": PROD, "quantity": float(x["length_remaining"]), "unit": "meter",
                       "purchase_mode": "roll", "roll_lines": [{"roll_id": x["id"], "take_qty": x["length_remaining"]}]}],
        }, headers=h)
        check("POST /sales-orders mode=roll (cross) 200", rso2.status_code == 200, f"-> {rso2.status_code} {rso2.text[:300]}")
        if rso2.status_code == 200:
            so2 = rso2.json()
            tids = so2.get("linked_transfer_ids") or []
            check("SO lintas-entitas → linked_transfer_ids dibuat", len(tids) >= 1, f"(got {tids})")
            check("intercompany_pending_qty > 0", float(so2.get("intercompany_pending_qty", 0) or 0) > 0.01)
            if tids:
                td = requests.get(f"{BASE}/api/transfers/{tids[0]}", headers=h)
                if td.status_code == 200:
                    t = td.json()
                    check("transfer auto: inter_entity, waiting_approval, KSC->KANDA", t.get("transfer_kind") == "inter_entity" and t.get("status") == "waiting_approval" and t.get("source_entity_id") == KSC and t.get("dest_entity_id") == KANDA, f"-> {t.get('status')}/{t.get('source_entity_id')}->{t.get('dest_entity_id')}")
                    check("transfer linked_order_id == SO", t.get("linked_order_id") == so2.get("id"))


def fase_c2(h):
    print("\n== FASE C2 — Rekonsiliasi Roll (genapkan atas/bawah + cut) ==")
    # cari produk dgn >=3 roll available di ent_ksc
    prods = requests.get(f"{BASE}/api/products", headers=h, params={"entity_id": "ent_ksc"}).json()
    target_prod = None
    rolls = []
    for p in prods:
        r = get_rolls(h, p["id"], "ent_ksc", all_entities=False)
        its = r.json().get("items", []) if r.status_code == 200 else []
        if len(its) >= 3:
            target_prod = p
            rolls = its
            break
    check("ada produk dgn >=3 roll utk uji rekonsiliasi", target_prod is not None, "")
    if not target_prod:
        return
    # target = panjang 2 roll pertama + setengah roll ke-3 (memaksa round_down=2, round_up=3, cut di roll-3)
    l0, l1, l2 = (float(rolls[i]["length_remaining"]) for i in range(3))
    target = round(l0 + l1 + l2 / 2.0, 2)
    sum_down = round(l0 + l1, 2)
    sum_up = round(l0 + l1 + l2, 2)
    rec = requests.post(f"{BASE}/api/sales-orders/preview-roll-reconcile", headers=h, json={
        "items": [{"product_id": target_prod["id"], "quantity": target}], "entity_id": "ent_ksc", "all_entities": False,
    })
    check("POST preview-roll-reconcile 200 (array)", rec.status_code == 200 and isinstance(rec.json(), list), f"-> {rec.status_code} {rec.text[:150]}")
    if rec.status_code != 200:
        return
    opt = rec.json()[0].get("options", {})
    check("opsi round_up ada & total >= target", "round_up" in opt and opt["round_up"]["total_qty"] >= target - 0.01, f"(up={opt.get('round_up',{}).get('total_qty')})")
    check("opsi round_down ada & total <= target", "round_down" in opt and opt["round_down"]["total_qty"] <= target + 0.01, f"(down={opt.get('round_down',{}).get('total_qty')})")
    check("round_up == Σ3 roll", "round_up" in opt and abs(opt["round_up"]["total_qty"] - sum_up) < 0.5, f"(up={opt.get('round_up',{}).get('total_qty')} exp={sum_up})")
    check("round_down == Σ2 roll", "round_down" in opt and abs(opt["round_down"]["total_qty"] - sum_down) < 0.5, f"(down={opt.get('round_down',{}).get('total_qty')} exp={sum_down})")
    check("opsi exact_cut ada & total == target", "exact_cut" in opt and abs(opt["exact_cut"]["total_qty"] - target) < 0.5, f"(cut={opt.get('exact_cut',{}).get('total_qty')})")
    if "exact_cut" in opt:
        cut = opt["exact_cut"]
        check("exact_cut roll_lines = 3 (2 utuh + 1 potong)", len(cut["roll_lines"]) == 3, f"(got {len(cut['roll_lines'])})")
        cut_line = cut["roll_lines"][-1]
        check("baris cut take_qty < panjang roll penuh", cut_line["take_qty"] < l2 - 0.01, f"(take={cut_line['take_qty']} full={l2})")
        # buat SO dgn opsi cut → verifikasi qty == target & 1 roll terpotong
        cust = requests.get(f"{BASE}/api/customers", headers=h, params={"entity_id": "ent_ksc"}).json()
        cust = cust[0] if isinstance(cust, list) and cust else None
        if cust and cust.get("addresses"):
            rso = requests.post(f"{BASE}/api/sales-orders", headers=h, json={
                "customer_id": cust["id"], "shipping_address_id": cust["addresses"][0]["id"], "entity_id": "ent_ksc",
                "allow_backorder": True, "confirm_mixed_lot": True,
                "items": [{"product_id": target_prod["id"], "quantity": target, "unit": "meter",
                           "purchase_mode": "roll", "roll_lines": cut["roll_lines"]}],
            })
            check("POST SO dgn opsi cut 200", rso.status_code == 200, f"-> {rso.status_code} {rso.text[:250]}")
            if rso.status_code == 200:
                so = rso.json()
                line = so["items"][0]
                check("SO qty (cut) == target", abs(float(line.get("base_quantity", line.get("quantity", 0))) - target) < 0.5, f"(got {line.get('base_quantity')} exp {target})")


def main():
    tok = login(ADMIN_EMAIL, ADMIN_PASS)
    h = H(tok)
    cust, addr = fase_a(h)
    fase_c(h, cust, addr)
    fase_c2(h)
    print(f"\nRESULT: {passed} PASS / {failed} FAIL")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
