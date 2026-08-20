"""EPIC 1 POC — role tightening (sales) + home endpoints (sales/admin/manager)."""
import json
import requests

BASE = "http://localhost:8001/api"
PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": "demo12345"}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


def find_cost(obj):
    """Cari kata biaya/HPP di payload (rekursif)."""
    BAD = ("cost", "hpp", "margin", "base_unit_cost", "purchase_price", "buy_price", "landed")
    hits = []

    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                lk = str(k).lower()
                if any(b in lk for b in BAD):
                    hits.append(f"{path}.{k}")
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o[:3]):
                walk(v, f"{path}[{i}]")

    walk(obj)
    return hits


print("=" * 60)
print("EPIC 1 POC — Role Experience & Home")
print("=" * 60)

sales = login("sales@kainnusantara.id")
admin = login("admin@kainnusantara.id")
manager = login("manager@kainnusantara.id")
print("Login OK (sales/admin/manager)\n")

# ── 1) Permission matrix: sales TIDAK lagi punya modul biaya/back-office ──
print("[1] Permission matrix (sales tightened)")
pm = requests.get(f"{BASE}/permissions", headers=H(admin), timeout=15)
matrix = pm.json().get("matrix", pm.json()) if pm.status_code == 200 else {}
sales_mods = set((matrix.get("sales") or {}).keys())
for revoked in ["purchase_order", "purchase_requisition", "vendor_bill", "landed_cost", "input_tax", "rfq"]:
    check(f"sales TANPA modul '{revoked}'", revoked not in sales_mods, f"(ada: {sales_mods})")
check("sales price_approval tanpa 'delete'",
      "delete" not in (matrix.get("sales", {}).get("price_approval") or []),
      f"({matrix.get('sales', {}).get('price_approval')})")
check("sales TETAP punya 'inventory' (stok read)", "inventory" in sales_mods)
check("sales TETAP punya 'order'", "order" in sales_mods)

# ── 2) Enforcement: sales 403 di endpoint biaya, admin 200 ──
print("\n[2] Enforcement endpoint biaya (sales ditolak, admin boleh)")
COST_EP = [
    ("/purchase-orders", "purchase_order"),
    ("/vendor-bills/payables/summary", "vendor_bill"),
    ("/landed-costs/payables/summary", "landed_cost"),
    ("/input-tax-invoices/eligible-bills", "input_tax"),
    ("/rfqs", "rfq"),
    ("/purchase-requisitions", "purchase_requisition"),
]
for path, mod in COST_EP:
    rs = requests.get(f"{BASE}{path}", headers=H(sales), timeout=15)
    check(f"sales GET {path} -> ditolak (403)", rs.status_code == 403, f"(dapat {rs.status_code})")
    ra = requests.get(f"{BASE}{path}", headers=H(admin), timeout=15)
    check(f"admin GET {path} -> boleh (200)", ra.status_code == 200, f"(dapat {ra.status_code})")

# ── 3) Home Sales (Performa Saya) — TANPA biaya ──
print("\n[3] /home/sales (Performa Saya, tanpa biaya)")
hs = requests.get(f"{BASE}/home/sales", headers=H(sales), timeout=20)
check("GET /home/sales -> 200", hs.status_code == 200, f"(dapat {hs.status_code})")
if hs.status_code == 200:
    d = hs.json()
    for key in ["commission", "target", "kpi", "history", "customers", "collections", "recent_orders"]:
        check(f"payload punya '{key}'", key in d)
    check("commission.mtd_accrual ada", "mtd_accrual" in d.get("commission", {}))
    check("commission.projection_month_end ada", "projection_month_end" in d.get("commission", {}))
    hits = find_cost(d)
    check("TIDAK ada field biaya/HPP di payload sales", len(hits) == 0, f"(hits: {hits})")

# ── 4) Home Admin (Control Tower) ──
print("\n[4] /home/admin (Control Tower)")
ha = requests.get(f"{BASE}/home/admin", headers=H(admin), timeout=20)
check("GET /home/admin (admin) -> 200", ha.status_code == 200, f"(dapat {ha.status_code})")
if ha.status_code == 200:
    d = ha.json()
    for key in ["sales", "ar", "approvals_pending", "low_stock", "incentive_payout", "leaderboard_top"]:
        check(f"payload punya '{key}'", key in d)
hs_block = requests.get(f"{BASE}/home/admin", headers=H(sales), timeout=15)
check("sales GET /home/admin -> ditolak (403)", hs_block.status_code == 403, f"(dapat {hs_block.status_code})")

# ── 5) Home Manager ──
print("\n[5] /home/manager")
hm = requests.get(f"{BASE}/home/manager", headers=H(manager), timeout=20)
check("GET /home/manager (manager) -> 200", hm.status_code == 200, f"(dapat {hm.status_code})")
if hm.status_code == 200:
    d = hm.json()
    for key in ["leaderboard", "totals", "target", "approvals_pending"]:
        check(f"payload punya '{key}'", key in d)

print("\n" + "=" * 60)
print(f"RESULT: {PASS} PASS / {FAIL} FAIL")
print("=" * 60)
