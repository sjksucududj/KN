"""R0 — Return Policy Engine — POC/integration test (backend, via HTTP API).

Membuktikan fondasi R0 bekerja end-to-end:
  1. Supplier origin (impor/lokal) + embedded return policy (extensible + custom_fields)
  2. Resolusi kebijakan retur supplier (+ rekomendasi regrade lokal utk impor non-returnable)
  3. Update policy supplier (PATCH)
  4. Sales Return Policy CRUD (global + category) + resolusi prioritas
  5. Eligibility retur jual (deadline derivation dari tgl kirim + window)
  6. Snapshot policy + return_deadline tersimpan di dokumen retur jual saat create

Jalankan: python test_r0_poc.py
"""
import os
import sys
import requests

BASE = os.environ.get("R0_BASE", "http://localhost:8001")
API = f"{BASE}/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}

PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {extra}")


def login():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    tok = r.json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def main():
    h = login()
    print("== R0 POC ==")

    # ── 1. Create supplier IMPORT + return policy (non-returnable) ──
    print("\n[1] Supplier impor + return policy (custom_fields extensible)")
    payload = {
        "name": "PT Import Test R0",
        "city": "Shanghai",
        "goods_type": "kain premium",
        "origin_type": "import",
        "country": "China",
        "return_policy": {
            "window_days": 60,
            "refund_modes": ["ap_credit", "none"],
            "returnable_to_supplier": False,
            "rma_required": True,
            "restocking_fee_pct": 15.5,
            "condition_requirements": "Kemasan asli, belum dipotong",
            "custom_fields": {"min_klaim_meter": 5, "butuh_foto": True},
            "notes": "Impor — sulit retur LN",
        },
    }
    r = requests.post(f"{API}/suppliers", json=payload, headers=h, timeout=30)
    check("POST /suppliers (import) → 200", r.status_code == 200, r.text[:200])
    sup = r.json()
    sup_id = sup.get("id", "")
    check("origin_type tersimpan = import", sup.get("origin_type") == "import")
    check("country tersimpan = China", sup.get("country") == "China")
    rp = sup.get("return_policy") or {}
    check("return_policy.window_days = 60", rp.get("window_days") == 60)
    check("return_policy.returnable_to_supplier = False", rp.get("returnable_to_supplier") is False)
    check("return_policy.custom_fields tersimpan (extensible)",
          (rp.get("custom_fields") or {}).get("min_klaim_meter") == 5, str(rp.get("custom_fields")))
    check("restocking_fee_pct = 15.5", abs(float(rp.get("restocking_fee_pct", 0)) - 15.5) < 0.01)

    # ── 2. Resolve supplier return policy → rekomendasi regrade lokal ──
    print("\n[2] Resolusi kebijakan retur supplier (impor non-returnable → regrade lokal)")
    r = requests.get(f"{API}/suppliers/{sup_id}/return-policy", headers=h, timeout=30)
    check("GET /suppliers/{id}/return-policy → 200", r.status_code == 200, r.text[:200])
    res = r.json()
    check("origin_type=import", res.get("origin_type") == "import")
    check("recommend_regrade_local = True (impor non-returnable)",
          res.get("recommend_regrade_local") is True, str(res))

    # ── 3. Update supplier return policy (PATCH) ──
    print("\n[3] Update supplier return policy (PATCH)")
    r = requests.patch(f"{API}/suppliers/{sup_id}",
                       json={"data": {"return_policy": {"window_days": 90,
                                                        "returnable_to_supplier": True,
                                                        "refund_modes": ["cash"]}}},
                       headers=h, timeout=30)
    check("PATCH supplier return_policy → 200", r.status_code == 200, r.text[:200])
    rp2 = (r.json() or {}).get("return_policy") or {}
    check("window_days terupdate = 90", rp2.get("window_days") == 90)
    check("refund_modes ternormalisasi = [cash]", rp2.get("refund_modes") == ["cash"], str(rp2.get("refund_modes")))

    # ── 4. Sales return policy CRUD (global + category) ──
    print("\n[4] Sales Return Policy CRUD + resolusi prioritas")
    r = requests.post(f"{API}/sales-return-policies", headers=h, timeout=30, json={
        "name": "Global 14 hari", "scope": "global", "window_days": 14,
        "enforce_window": True, "require_inspection": True,
    })
    check("POST global policy → 200", r.status_code == 200, r.text[:200])
    gpol = r.json()
    check("global window_days=14", gpol.get("window_days") == 14)

    # category policy — pakai kategori yang ada di produk order (Batik)
    r = requests.post(f"{API}/sales-return-policies", headers=h, timeout=30, json={
        "name": "Kategori Batik 45 hari", "scope": "category", "scope_ref": "Batik",
        "window_days": 45, "enforce_window": False,
        "custom_fields": {"catatan": "batik butuh cek motif"},
    })
    check("POST category policy → 200", r.status_code == 200, r.text[:200])
    catpol = r.json()

    # invalid: category tanpa scope_ref → 400
    r = requests.post(f"{API}/sales-return-policies", headers=h, timeout=30, json={
        "name": "bad", "scope": "category", "scope_ref": "",
    })
    check("POST category tanpa scope_ref → 400", r.status_code == 400, r.text[:120])

    # list
    r = requests.get(f"{API}/sales-return-policies", headers=h, timeout=30)
    check("GET /sales-return-policies → 200 (array)", r.status_code == 200 and isinstance(r.json(), list))
    names = [p.get("name") for p in r.json()]
    check("kedua policy muncul di list", "Global 14 hari" in names and "Kategori Batik 45 hari" in names)

    # ── 5. Eligibility retur jual (deadline derivation) ──
    print("\n[5] Eligibility retur jual + deadline derivation")
    # ambil order yang sudah dikirim/selesai
    r = requests.get(f"{API}/sales-orders", headers=h, timeout=30)
    orders = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    fulfilled = [o for o in orders if o.get("status") in
                 ("done", "shipped", "partially_shipped", "confirmed", "picked")]
    check("ada order fulfilled untuk uji eligibility", len(fulfilled) > 0, f"total={len(orders)}")
    if fulfilled:
        oid = fulfilled[0]["id"]
        r = requests.get(f"{API}/sales-return-policies/eligibility",
                         params={"order_id": oid, "return_type": "retur"}, headers=h, timeout=30)
        check("GET eligibility → 200", r.status_code == 200, r.text[:200])
        el = r.json()
        check("eligibility punya field deadline", "deadline" in el, str(el)[:200])
        check("eligibility punya field within_window", "within_window" in el)
        check("policy snapshot ter-resolve", bool(el.get("policy")), str(el.get("policy"))[:200])
        check("window_days ter-resolve (>0)", int(el.get("window_days", 0)) > 0, str(el.get("window_days")))
        print(f"     → resolved policy='{el.get('policy',{}).get('name')}', "
              f"window={el.get('window_days')}, deadline={str(el.get('deadline'))[:10]}, "
              f"eligible={el.get('eligible')}, within={el.get('within_window')}")

        # ── 6. Create sales return → snapshot + deadline tersimpan ──
        print("\n[6] Create retur jual → policy_snapshot + return_deadline tersimpan")
        # ambil 1 item dari order untuk retur qty kecil
        order = next((o for o in fulfilled if o["id"] == oid), fulfilled[0])
        items = order.get("items", [])
        if items:
            it = items[0]
            body = {
                "order_id": oid,
                "return_type": "retur",
                "items": [{
                    "product_id": it.get("product_id"),
                    "product_name": it.get("product_name", ""),
                    "quantity_returned": 1,
                    "unit": it.get("unit", "meter"),
                    "reason": "POC R0",
                    "condition": "damaged",
                }],
                "notes": "R0 POC return",
            }
            r = requests.post(f"{API}/sales-returns", json=body, headers=h, timeout=30)
            check("POST /sales-returns → 200", r.status_code == 200, r.text[:250])
            if r.status_code == 200:
                ret = r.json()
                check("return_deadline tersimpan di dokumen", "return_deadline" in ret, str(ret.keys()))
                check("policy_snapshot tersimpan di dokumen", bool(ret.get("policy_snapshot")),
                      str(ret.get("policy_snapshot"))[:200])
                check("policy_eligibility tersimpan di dokumen", "policy_eligibility" in ret)
                print(f"     → return {ret.get('number')} deadline={str(ret.get('return_deadline'))[:10]} "
                      f"policy='{ret.get('policy_snapshot',{}).get('name')}'")
        else:
            check("order punya items", False)

    # cleanup: nonaktifkan policy & supplier uji (biar seed tetap bersih)
    print("\n[cleanup] nonaktifkan data uji")
    requests.delete(f"{API}/sales-return-policies/{gpol['id']}", headers=h, timeout=30)
    requests.delete(f"{API}/sales-return-policies/{catpol['id']}", headers=h, timeout=30)
    requests.delete(f"{API}/suppliers/{sup_id}", headers=h, timeout=30)

    print(f"\n=== HASIL: PASS={PASS}  FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
