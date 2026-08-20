"""fa_dark_sweep.py — AUDIT #073: exercise ALL 91 never-covered endpoints as admin
to catch 500 crashes (RC-6 direct-key-access class) hiding in untested code.

Strategy: real path-ids substituted where a live doc exists, else dummy id.
Empty/minimal JSON body. We flag: 500 (server crash) and 200 on destructive op
with dummy id (unexpected). 401/403/404/400/409/422 = reached/guarded (OK).
"""
import json
import re
import requests
from pymongo import MongoClient
import os

BASE = "http://localhost:8001/api"
mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]
MATRIX = json.load(open("/app/coverage_data/endpoint_matrix.json"))

# map path-param name -> (collection, id-field) for real id substitution
IDMAP = {
    "template_id": "document_templates", "gallery_id": "design_galleries",
    "rule_id": "approval_rules", "request_id": "approval_requests",
    "customer_id": "customers", "session_id": "cycle_count_sessions",
    "code": "gl_accounts", "employee_id": "hr_employees", "unit_id": "hr_org_units",
    "att_id": None, "leave_id": "hr_leave_requests", "ot_id": "hr_overtime_requests",
    "run_id": "hr_payroll_runs", "task_id": "wms_tasks", "voucher_id": "landed_cost_vouchers",
    "approval_id": "price_approvals", "po_id": "purchase_orders", "return_id": "purchase_returns",
    "rfq_id": "rfqs", "term_id": "payment_terms", "supplier_id": "suppliers",
    "entry_id": None, "record_id": None, "warehouse_id": "warehouses", "uom_id": "uoms",
    "bill_id": "vendor_bills", "product_id": "products",
}


def login():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@kainnusantara.id", "password": "demo12345"}, timeout=15)
    return r.json()["token"]


def real_id(coll):
    if not coll:
        return None
    d = mc[coll].find_one({}, {"_id": 0, "id": 1, "code": 1})
    return (d or {}).get("id") or (d or {}).get("code")


def fill(path):
    def sub(m):
        name = m.group(1)
        rid = real_id(IDMAP.get(name)) if name in IDMAP else None
        return rid or f"dummy_{name}"
    return re.sub(r"\{([a-z_]+)\}", sub, path)


def main():
    tok = login()
    H = {"Authorization": f"Bearer {tok}"}
    miss = [r for r in MATRIX["routes"] if not r["hit"]]
    crashes, ok200_destructive, reached = [], [], 0
    print(f"probing {len(miss)} dark endpoints...\n")
    for r in miss:
        m, path = r["method"], r["path"]
        url = BASE.replace("/api", "") + fill(path)
        try:
            resp = requests.request(m, url, headers=H, json={}, timeout=12)
            sc = resp.status_code
        except Exception as e:
            print(f"  EXC  {m:6} {path}: {e}")
            continue
        if sc == 500:
            crashes.append((m, path, resp.text[:160]))
            print(f"  500! {m:6} {path}  -> {resp.text[:120]}")
        elif sc == 200 and m in ("POST", "DELETE", "PATCH", "PUT") and "dummy_" in url:
            ok200_destructive.append((m, path))
            print(f"  200? {m:6} {path} (destructive on dummy id)")
        else:
            reached += 1
    print("\n" + "=" * 66)
    print(f"dark endpoints probed : {len(miss)}")
    print(f"500 crashes           : {len(crashes)}")
    print(f"200-on-dummy (suspect): {len(ok200_destructive)}")
    print(f"reached/guarded (ok)  : {reached}")
    if crashes:
        print("\nCRASHES (500):")
        for m, p, t in crashes:
            print(f"  {m} {p}\n     {t}")
    if ok200_destructive:
        print("\n200-ON-DUMMY:")
        for m, p in ok200_destructive:
            print(f"  {m} {p}")


if __name__ == "__main__":
    main()
