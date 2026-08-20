#!/usr/bin/env python3
"""F-4c POC — group/join sales split insentif.
Membuktikan:
  1. Order ber-sales_team menyimpan tim & lolos validasi.
  2. Komisi terbagi sesuai split_pct (PIC 60 : co 40) — RATIO benar.
  3. Tim MENGGANTIKAN atribusi assigned_sales (customer Moda di-assign ke sales_01,
     tapi sales_01 TIDAK ada di tim → delta komisi sales_01 = 0 dari order ini).
  4. Validasi sales_team: Σ≠100 → 400, tanpa PIC → 400, duplikat → 400.
"""
import sys, requests

BASE = "http://localhost:8001/api"
PERIOD = "2026-06"
PIC = "user_sales_02"   # Bima — 60%
CO = "user_sales_03"    # Citra — 40%
OUTSIDER = "user_sales_01"  # Ayu — assigned ke Moda, TAPI tak di tim


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": "demo12345"})
    r.raise_for_status()
    return r.json()["token"]


def comm(tok, sid):
    r = requests.get(f"{BASE}/sales/commission", params={"sales_id": sid, "period": PERIOD},
                     headers={"Authorization": f"Bearer {tok}"})
    r.raise_for_status()
    d = r.json()
    return float(d.get("projection_full", d.get("total", 0)) or 0)


def main():
    admin = login("admin@kainnusantara.id")
    H = {"Authorization": f"Bearer {admin}"}

    base_pic = comm(admin, PIC)
    base_co = comm(admin, CO)
    base_out = comm(admin, OUTSIDER)
    print(f"[baseline] PIC={base_pic} CO={base_co} OUTSIDER={base_out}")

    order = {
        "customer_id": "cust_moda_surabaya", "shipping_address_id": "addr_003",
        "entity_id": "all", "allow_backorder": True, "sales_name": "Tim Bima & Citra",
        "items": [{"product_id": "prod_batik_mega", "quantity": 10, "unit": "meter"}],
        "sales_team": [
            {"sales_id": PIC, "name": "Bima Saputra", "role": "pic", "split_pct": 60},
            {"sales_id": CO, "name": "Citra Lestari", "role": "co", "split_pct": 40},
        ],
    }
    r = requests.post(f"{BASE}/sales-orders", json=order, headers=H)
    assert r.status_code == 200, f"create group order failed: {r.status_code} {r.text}"
    so = r.json()
    oid, onum = so["id"], so["number"]
    print(f"[create] group order {onum} ok; stored sales_team={so.get('sales_team')}")
    assert len(so.get("sales_team") or []) == 2, "sales_team not stored"

    # bayar penuh agar komisi terkumpul (engine on-collection)
    rp = requests.post(f"{BASE}/sales-orders/{oid}/simulate-payment", json={"amount": 0}, headers=H)
    assert rp.status_code == 200, f"simulate-payment failed: {rp.status_code} {rp.text}"
    print("[pay] full payment simulated")

    after_pic = comm(admin, PIC)
    after_co = comm(admin, CO)
    after_out = comm(admin, OUTSIDER)
    d_pic = round(after_pic - base_pic, 2)
    d_co = round(after_co - base_co, 2)
    d_out = round(after_out - base_out, 2)
    print(f"[delta] PIC(60%)={d_pic}  CO(40%)={d_co}  OUTSIDER={d_out}  sum={round(d_pic+d_co,2)}")

    ok = True
    if not (d_pic > 0 and d_co > 0):
        print("FAIL: komisi tim harus > 0"); ok = False
    # ratio 60:40 → d_pic/0.6 == d_co/0.4
    if d_pic > 0 and d_co > 0:
        norm_pic, norm_co = d_pic / 0.6, d_co / 0.4
        if abs(norm_pic - norm_co) / max(norm_pic, 1) > 0.01:
            print(f"FAIL: ratio bukan 60:40 (norm {norm_pic} vs {norm_co})"); ok = False
        else:
            print(f"PASS: ratio 60:40 terverifikasi (base komisi order ~{round(norm_pic,2)})")
    if abs(d_out) > 0.01:
        print(f"FAIL: OUTSIDER (assigned sales) harusnya 0 dari order tim, dapat {d_out}"); ok = False
    else:
        print("PASS: tim MENGGANTIKAN atribusi assigned_sales (sales_01 = 0)")

    # ── Validasi negatif ──
    def expect_400(team, label):
        bad = {**order, "sales_team": team}
        rr = requests.post(f"{BASE}/sales-orders", json=bad, headers=H)
        if rr.status_code == 400:
            print(f"PASS: validasi '{label}' → 400 ({rr.json().get('detail')})")
            return True
        print(f"FAIL: validasi '{label}' harus 400, dapat {rr.status_code}")
        return False

    ok &= expect_400([{"sales_id": PIC, "role": "pic", "split_pct": 70},
                      {"sales_id": CO, "role": "co", "split_pct": 40}], "Σ=110≠100")
    ok &= expect_400([{"sales_id": PIC, "role": "co", "split_pct": 60},
                      {"sales_id": CO, "role": "co", "split_pct": 40}], "tanpa PIC")
    ok &= expect_400([{"sales_id": PIC, "role": "pic", "split_pct": 50},
                      {"sales_id": PIC, "role": "co", "split_pct": 50}], "duplikat sales_id")

    print("\n" + ("✅ F-4c POC PASS" if ok else "❌ F-4c POC FAIL"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
