"""R2 — Unified Inspect (4-point) + Quarantine — POC/integration test.

Membuktikan:
  1. Inspect reuse engine 4-point → grade dihitung dari defect points (A/B/C)
  2. Rekomendasi outcome diturunkan dari grade (A→refund, B→store_credit, C→nego)
  3. Settle (refund/store_credit) → roll retur masuk QUARANTINE (bukan available)
  4. Release karantina → roll jadi available; scrap → damaged
  5. Nego → tanpa roll karantina (tanpa gerak stok)

Jalankan: python test_r2_poc.py
"""
import os
import sys
import requests

API = f"{os.environ.get('R2_BASE', 'http://localhost:8001')}/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✅ {name}")
    else:
        FAIL += 1; print(f"  ❌ {name}  {extra}")


def login():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30); r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def eligible(h):
    r = requests.get(f"{API}/sales-orders", headers=h, timeout=30)
    o = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    ok = {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
    return [x for x in o if x.get("status") in ok and
            any(float(it.get("quantity", 0) or 0) >= 5 for it in (x.get("items") or []))]


def create(h, orders, q=1):
    for o in orders:
        its = [it for it in o["items"] if float(it.get("quantity", 0) or 0) >= q]
        if not its:
            continue
        it = its[0]
        r = requests.post(f"{API}/sales-returns", headers=h, timeout=30, json={
            "order_id": o["id"], "return_type": "retur",
            "items": [{"product_id": it["product_id"], "product_name": it.get("product_name", ""),
                       "quantity_returned": q, "unit": it.get("unit", "meter"),
                       "reason": "R2", "condition": "ok"}], "notes": "R2"})
        if r.status_code == 200:
            return r.json()
    return None


def inspect(h, rid, defects):
    requests.post(f"{API}/sales-returns/{rid}/submit", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/approve", headers=h, json={"notes": ""}, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
    return requests.post(f"{API}/sales-returns/{rid}/inspect/complete", headers=h, timeout=30,
                         json={"inspections": [{"index": 0, "defects": defects, "condition": "ok",
                                                "accepted_qty": 1}], "notes": "4point"}).json()


def main():
    h = login()
    orders = eligible(h)
    print(f"== R2 POC == (eligible orders: {len(orders)})")
    if not orders:
        check("ada order eligible", False); sys.exit(1)

    # ── 1. Grade dari 4-point + rekomendasi ──
    print("\n[1] 4-point grade + rekomendasi outcome")
    # C: points 48 (>40)
    ret = create(h, orders); check("create #1", bool(ret))
    r = inspect(h, ret["id"], [{"point_value": 4, "count": 12}])   # 48 → C
    ins = r["items"][0].get("inspection", {})
    check("grade C (points>40)", ins.get("grade") == "C", f"grade={ins.get('grade')} pts={ins.get('points')}")
    check("recommended_outcome nego (grade C)", ins.get("recommended_outcome") == "nego", str(ins.get("recommended_outcome")))
    check("points terhitung = 48", abs(float(ins.get("points", 0)) - 48) < 0.01, str(ins.get("points")))

    ret = create(h, orders); r = inspect(h, ret["id"], [{"point_value": 2, "count": 15}])  # 30 → B
    insB = r["items"][0].get("inspection", {})
    check("grade B (21..40)", insB.get("grade") == "B", f"grade={insB.get('grade')} pts={insB.get('points')}")
    check("recommended store_credit (grade B)", insB.get("recommended_outcome") == "store_credit", str(insB.get("recommended_outcome")))

    ret = create(h, orders); r = inspect(h, ret["id"], [{"point_value": 1, "count": 5}])   # 5 → A
    insA = r["items"][0].get("inspection", {})
    check("grade A (<=20)", insA.get("grade") == "A", f"grade={insA.get('grade')} pts={insA.get('points')}")
    check("recommended refund (grade A)", insA.get("recommended_outcome") == "refund", str(insA.get("recommended_outcome")))

    # ── 2. Quarantine entry saat settle refund ──
    print("\n[2] Settle refund → roll masuk QUARANTINE")
    ret = create(h, orders); rid = ret["id"]
    inspect(h, rid, [{"point_value": 1, "count": 2}])  # A
    s = requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, json={"outcome": "refund"}, timeout=30).json()
    check("settle refund → refund_settled", s.get("status") == "refund_settled", str(s)[:120])
    q = requests.get(f"{API}/sales-returns/{rid}/quarantine", headers=h, timeout=30).json()
    check("GET quarantine → 200 (array)", isinstance(q, list) and len(q) >= 1, str(q)[:120])
    check("roll status = quarantine (belum available)", all(r.get("status") == "quarantine" for r in q), str([r.get("status") for r in q]))
    check("roll bawa grade hasil inspeksi", all(r.get("grade") for r in q))

    # ── 3. Release karantina → available ──
    print("\n[3] Release karantina → available")
    rel = requests.post(f"{API}/sales-returns/{rid}/quarantine/release", headers=h, timeout=30,
                        json={"decisions": [], "notes": "approve semua"}).json()
    check("release → quarantine_released", rel.get("quarantine_released") is True, str(rel.get("quarantine_released")))
    q2 = requests.get(f"{API}/sales-returns/{rid}/quarantine", headers=h, timeout=30).json()
    check("roll setelah release = available", all(r.get("status") == "available" for r in q2), str([r.get("status") for r in q2]))

    # ── 4. Scrap decision ──
    print("\n[4] Release dengan action scrap → damaged")
    ret = create(h, orders); rid2 = ret["id"]
    inspect(h, rid2, [{"point_value": 4, "count": 12}])  # C
    requests.post(f"{API}/sales-returns/{rid2}/settle", headers=h, json={"outcome": "store_credit"}, timeout=30)
    q = requests.get(f"{API}/sales-returns/{rid2}/quarantine", headers=h, timeout=30).json()
    check("store_credit juga masuk quarantine", len(q) >= 1 and q[0].get("status") == "quarantine")
    if q:
        rel = requests.post(f"{API}/sales-returns/{rid2}/quarantine/release", headers=h, timeout=30,
                           json={"decisions": [{"roll_id": q[0]["id"], "action": "scrap"}]}).json()
        q3 = requests.get(f"{API}/sales-returns/{rid2}/quarantine", headers=h, timeout=30).json()
        check("roll scrap → damaged", any(r.get("status") == "damaged" for r in q3), str([r.get("status") for r in q3]))

    # ── 5. Nego → tanpa quarantine ──
    print("\n[5] Nego → tanpa roll karantina (tanpa gerak stok)")
    ret = create(h, orders); rid3 = ret["id"]
    inspect(h, rid3, [{"point_value": 4, "count": 12}])
    requests.post(f"{API}/sales-returns/{rid3}/settle", headers=h, json={"outcome": "nego"}, timeout=30)
    q = requests.get(f"{API}/sales-returns/{rid3}/quarantine", headers=h, timeout=30).json()
    check("nego → tidak ada roll karantina", isinstance(q, list) and len(q) == 0, str(q)[:120])

    print(f"\n=== HASIL R2: PASS={PASS}  FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
