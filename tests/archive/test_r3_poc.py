"""R3 — Inventory ownership/location + regrade + cross-entity transfer — POC.

Membuktikan:
  1. Settle refund → user memilih LOKASI gudang penerimaan (return_warehouse_id);
     OWNER roll = entity SO (SSOT: owner vs lokasi terpisah). Enrichment nama tampil.
  2. Release karantina dengan REGRADE (A→B) → grade final berubah + regraded_from terekam.
  3. Cross-entity: pindah KEPEMILIKAN roll retur (available) ke entitas lain →
     owner_entity_id berubah, lokasi TETAP, JE inter-company terposting (idempotent).
  4. Guard: transfer roll yang masih 'quarantine' (belum release) → 400.
  5. Guard: transfer ke entitas yang sama → 400.

Jalankan: python test_r3_poc.py
"""
import os
import sys
import requests

API = f"{os.environ.get('R3_BASE', 'http://localhost:8001')}/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  \u2705 {name}")
    else:
        FAIL += 1; print(f"  \u274c {name}  {extra}")


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
                       "reason": "R3", "condition": "ok"}], "notes": "R3"})
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
    ents = requests.get(f"{API}/entities", headers=h, timeout=30).json()
    ents = ents if isinstance(ents, list) else ents.get("items", [])
    whs = requests.get(f"{API}/warehouses", headers=h, timeout=30).json()
    whs = whs if isinstance(whs, list) else whs.get("items", [])
    print(f"== R3 POC == (orders={len(orders)} entities={len(ents)} warehouses={len(whs)})")
    if not orders or len(ents) < 2 or not whs:
        check("prasyarat data (orders + >=2 entity + warehouse)", False); sys.exit(1)

    # pilih gudang tujuan eksplisit (ambil yang terakhir agar cenderung beda dgn default)
    dest_wh = whs[-1]["id"]

    # ── 1. Settle refund → lokasi dipilih, owner = entity SO ──
    print("\n[1] Settle refund → pilih LOKASI gudang; OWNER = entity SO (SSOT)")
    ret = create(h, orders); rid = ret["id"]
    inspect(h, rid, [{"point_value": 1, "count": 2}])   # grade A
    s = requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30,
                      json={"outcome": "refund", "return_warehouse_id": dest_wh}).json()
    check("settle refund → refund_settled", s.get("status") == "refund_settled", str(s)[:120])
    so_entity = s.get("entity_id")
    check("dokumen simpan return_warehouse_id (lokasi)", s.get("return_warehouse_id") == dest_wh, str(s.get("return_warehouse_id")))
    check("dokumen simpan return_owner_entity_id = entity SO", s.get("return_owner_entity_id") == so_entity, str(s.get("return_owner_entity_id")))
    q = requests.get(f"{API}/sales-returns/{rid}/quarantine", headers=h, timeout=30).json()
    check("roll quarantine dibuat", isinstance(q, list) and len(q) >= 1, str(q)[:120])
    roll = q[0] if q else {}
    check("roll.warehouse_id = lokasi terpilih", roll.get("warehouse_id") == dest_wh, str(roll.get("warehouse_id")))
    check("roll.owner_entity_id = entity SO (owner)", roll.get("owner_entity_id") == so_entity, str(roll.get("owner_entity_id")))
    check("enrichment owner_entity_name ada", bool(roll.get("owner_entity_name")), str(roll.get("owner_entity_name")))
    check("enrichment warehouse_name ada", bool(roll.get("warehouse_name")), str(roll.get("warehouse_name")))

    # ── 2. Release dengan REGRADE (A→B) ──
    print("\n[2] Release karantina + REGRADE A\u2192B")
    rel = requests.post(f"{API}/sales-returns/{rid}/quarantine/release", headers=h, timeout=30,
                        json={"decisions": [{"roll_id": roll["id"], "action": "release", "grade": "B"}]}).json()
    check("release ok", rel.get("quarantine_released") is True, str(rel.get("quarantine_released")))
    q2 = requests.get(f"{API}/sales-returns/{rid}/quarantine", headers=h, timeout=30).json()
    rr = next((x for x in q2 if x["id"] == roll["id"]), {})
    check("roll status available", rr.get("status") == "available", str(rr.get("status")))
    check("grade final = B (regrade)", rr.get("grade") == "B", str(rr.get("grade")))
    check("regraded_from = A terekam", rr.get("regraded_from") == "A", str(rr.get("regraded_from")))

    # ── 3. Cross-entity: pindah kepemilikan roll (available) ──
    print("\n[3] Cross-entity transfer kepemilikan roll retur")
    dest_ent = next((e["id"] for e in ents if e["id"] != so_entity), None)
    check("ada entitas tujuan berbeda", bool(dest_ent), str([e['id'] for e in ents]))
    tr = requests.post(f"{API}/sales-returns/{rid}/rolls/{roll['id']}/transfer-ownership",
                       headers=h, timeout=30, json={"dest_entity_id": dest_ent, "notes": "R3 test"})
    check("transfer-ownership → 200", tr.status_code == 200, f"{tr.status_code} {tr.text[:160]}")
    trj = tr.json() if tr.status_code == 200 else {}
    check("owner roll berpindah ke dest", (trj.get("roll") or {}).get("owner_entity_id") == dest_ent,
          str((trj.get("roll") or {}).get("owner_entity_id")))
    check("lokasi (warehouse) roll TETAP", (trj.get("roll") or {}).get("warehouse_id") == dest_wh,
          str((trj.get("roll") or {}).get("warehouse_id")))
    check("roll kembali available setelah transfer", (trj.get("roll") or {}).get("status") == "available",
          str((trj.get("roll") or {}).get("status")))
    je = trj.get("je") or {}
    check("JE inter-company terposting", je.get("posted") is True, str(je))
    check("JE punya pair_id (2 buku)", bool(je.get("pair_id")), str(je.get("pair_id")))

    # ── 4. Guard: transfer roll masih quarantine → 400 ──
    print("\n[4] Guard: transfer roll yang masih 'quarantine' ditolak")
    ret2 = create(h, orders); rid2 = ret2["id"]
    inspect(h, rid2, [{"point_value": 1, "count": 2}])
    requests.post(f"{API}/sales-returns/{rid2}/settle", headers=h, timeout=30,
                  json={"outcome": "refund", "return_warehouse_id": dest_wh})
    q3 = requests.get(f"{API}/sales-returns/{rid2}/quarantine", headers=h, timeout=30).json()
    if q3:
        qroll = q3[0]
        dest_ent2 = next((e["id"] for e in ents if e["id"] != so_entity), None)
        g = requests.post(f"{API}/sales-returns/{rid2}/rolls/{qroll['id']}/transfer-ownership",
                          headers=h, timeout=30, json={"dest_entity_id": dest_ent2})
        check("transfer roll quarantine → 400", g.status_code == 400, f"{g.status_code} {g.text[:120]}")

    # ── 5. Guard: transfer ke entitas sama → 400 ──
    print("\n[5] Guard: transfer ke entitas pemilik sendiri ditolak")
    # release roll rid2 dulu agar available
    if q3:
        requests.post(f"{API}/sales-returns/{rid2}/quarantine/release", headers=h, timeout=30,
                      json={"decisions": [{"roll_id": q3[0]["id"], "action": "release"}]})
        g2 = requests.post(f"{API}/sales-returns/{rid2}/rolls/{q3[0]['id']}/transfer-ownership",
                           headers=h, timeout=30, json={"dest_entity_id": so_entity})
        check("transfer ke entitas sama → 400", g2.status_code == 400, f"{g2.status_code} {g2.text[:120]}")

    print(f"\n=== HASIL R3: PASS={PASS}  FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
