"""
Seed a few AVAILABLE supplier-origin rolls via the REAL receiving flow, so the
RollPickerModal (retur presisi) and Kartu Asal have realistic demo/test data.
Idempotent-ish: only tops up if fewer than target available rolls exist.

Run: cd /app && python seed_returnable_demo.py
"""
import requests

BASE = "http://localhost:8001/api"
SUP = "sup_783209b83eba"   # Cirebon Craft
WH = "wh_jakarta"

# (product_id, qty, price) batches to receive & QC-accept (left AVAILABLE)
BATCHES = [
    ("prod_batik_mega", 150, 120000),
    ("prod_batik_mega", 200, 118000),
    ("prod_tenun_ikat", 180, 95000),
]


def login():
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": "admin@kainnusantara.id", "password": "demo12345"})
    r.raise_for_status()
    return r.json()["token"]


def receive_available(H, product_id, qty, price, tag):
    po = requests.post(f"{BASE}/purchase-orders", json={
        "supplier_id": SUP, "warehouse_id": WH,
        "items": [{"product_id": product_id, "quantity": qty, "unit": "yard", "price": price}],
        "notes": f"demo returnable {tag}",
    }, headers=H).json()
    po_id = po["id"]
    if po.get("approval_required"):
        for _ in range(5):
            ra = requests.post(f"{BASE}/purchase-orders/{po_id}/approve", json={"notes": "ok"}, headers=H)
            if ra.status_code != 200 or ra.json().get("status") != "waiting_approval":
                break
    tasks = [t for t in requests.get(f"{BASE}/inbound/tasks", headers=H).json()
             if t.get("po_id") == po_id and t.get("product_id") == product_id]
    if not tasks:
        print(f"  [WARN] no task for {po.get('po_number')}"); return None
    tid = tasks[0]["id"]
    requests.post(f"{BASE}/inbound/tasks/{tid}/scan-receive",
                  json={"product_id": product_id, "actual_qty": qty, "lot": f"LOT-{tag}",
                        "dye_lot": f"LOT-{tag}", "grade": "A"}, headers=H)
    requests.post(f"{BASE}/inbound/tasks/{tid}/complete", json={}, headers=H)
    rqc = requests.post(f"{BASE}/inbound/tasks/{tid}/qc-decision",
                        json={"accept_qty": qty, "reject_qty": 0, "accept_grade": "A"}, headers=H)
    print(f"  {po.get('po_number')} {product_id} {qty}yd -> QC {rqc.status_code}")
    return po.get("po_number")


def main():
    H = {"Authorization": f"Bearer {login()}"}
    print("Seeding returnable demo rolls (real receiving flow)...")
    for i, (pid, qty, price) in enumerate(BATCHES):
        receive_available(H, pid, qty, price, f"D{i+1}")
    # verify
    for pid in {"prod_batik_mega", "prod_tenun_ikat"}:
        d = requests.get(f"{BASE}/purchase-returns/source-rolls",
                         params={"product_id": pid, "supplier_id": SUP}, headers=H).json()
        print(f"  source-rolls {pid}: count={d.get('count')} returnable={d.get('total_returnable')}")


if __name__ == "__main__":
    main()
