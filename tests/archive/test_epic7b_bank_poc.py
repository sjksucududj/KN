"""POC EPIC7-B — Kas & Bank: akun, saldo, ledger, reconcile, RBAC."""
import requests

BASE = "http://localhost:8001/api"
P = F = 0


def ok(c, m):
    global P, F
    P += 1 if c else 0
    F += 0 if c else 1
    print(f"  [{'PASS' if c else 'FAIL'}] {m}")


def login(e):
    return requests.post(f"{BASE}/auth/login", json={"email": e, "password": "demo12345"}).json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


def approx(a, b, eps=1.0):
    return abs(float(a) - float(b)) <= eps


def main():
    admin = login("admin@kainnusantara.id")
    manager = login("manager@kainnusantara.id")
    sales = login("sales@kainnusantara.id")

    print("=== LIST accounts (admin) ===")
    r = requests.get(f"{BASE}/bank-accounts", headers=H(admin))
    ok(r.status_code == 200, f"GET /bank-accounts 200 ({r.status_code})")
    accs = r.json()
    ok(isinstance(accs, list) and len(accs) >= 3, f"≥3 akun bank terseed ({len(accs)})")
    ok(all("balance" in a and "txn_count" in a and "account_type" in a for a in accs), "akun punya balance/txn_count/type")
    ok(all(a["account_type"] in ("bank", "cash") for a in accs), "account_type valid")

    # invarian saldo: balance == opening + Σin - Σout (via inflow/outflow)
    inv = all(approx(a["balance"], a["opening_balance"] + a["inflow"] - a["outflow"]) for a in accs)
    ok(inv, "invarian: balance == opening + inflow − outflow")

    kas_ksc = next((a for a in accs if a["id"] == "bank_kas_ksc"), None)
    ok(kas_ksc is not None and approx(kas_ksc["balance"], 9750000), f"Kas Kecil KSC balance benar ({kas_ksc and kas_ksc['balance']})")

    print("\n=== LEDGER + running balance ===")
    aid = kas_ksc["id"]
    rl = requests.get(f"{BASE}/bank-accounts/{aid}/ledger", headers=H(admin))
    ok(rl.status_code == 200, f"GET ledger 200 ({rl.status_code})")
    led = rl.json()
    txns = led.get("transactions", [])
    ok(len(txns) == kas_ksc["txn_count"], f"jumlah txn ledger == txn_count ({len(txns)})")
    ok(all("running_balance" in t for t in txns), "tiap txn punya running_balance")
    if txns:
        # txn terbaru (paling atas) running_balance == saldo akun
        ok(approx(txns[0]["running_balance"], led["balance"]), "running_balance txn terbaru == saldo akun")

    print("\n=== CREATE account + post txn + balance update ===")
    rc = requests.post(f"{BASE}/bank-accounts", headers=H(admin), json={
        "name": "POC Mandiri Giro", "account_type": "bank", "bank_name": "Mandiri",
        "account_number": "999", "opening_balance": 1000000})
    ok(rc.status_code == 200, f"POST create account 200 ({rc.status_code})")
    new_id = rc.json()["id"]
    ok(approx(rc.json()["balance"], 1000000), "akun baru balance == opening")
    # post cash txn ke akun ini
    rt = requests.post(f"{BASE}/cash-transactions", headers=H(admin), json={
        "cash_type": "kas_kecil", "direction": "in", "amount": 250000,
        "category": "transfer", "description": "POC top-up", "entity_id": "ent_ksc",
        "account_id": new_id})
    ok(rt.status_code == 200, f"POST cash-transaction (account_id) 200 ({rt.status_code})")
    txn_id = rt.json()["id"]
    ok(rt.json().get("account_id") == new_id, "cash txn menyimpan account_id")
    # balance akun harus naik 250rb
    after = requests.get(f"{BASE}/bank-accounts", headers=H(admin)).json()
    acc_after = next(a for a in after if a["id"] == new_id)
    ok(approx(acc_after["balance"], 1250000), f"saldo akun naik (1.000.000+250.000=1.250.000 → {acc_after['balance']})")

    print("\n=== RECONCILE toggle ===")
    rr = requests.post(f"{BASE}/cash-transactions/{txn_id}/reconcile", headers=H(admin), json={"reconciled": True})
    ok(rr.status_code == 200 and rr.json().get("reconciled") is True, "reconcile=true OK")
    acc2 = next(a for a in requests.get(f"{BASE}/bank-accounts", headers=H(admin)).json() if a["id"] == new_id)
    ok(approx(acc2["reconciled_balance"], 1250000), f"reconciled_balance termasuk txn terekonsiliasi ({acc2['reconciled_balance']})")
    ru = requests.post(f"{BASE}/cash-transactions/{txn_id}/reconcile", headers=H(admin), json={"reconciled": False})
    ok(ru.status_code == 200 and ru.json().get("reconciled") is False, "reconcile=false OK")

    print("\n=== PATCH + RBAC + edge ===")
    rp = requests.patch(f"{BASE}/bank-accounts/{new_id}", headers=H(admin), json={"name": "POC Mandiri Giro 2", "is_active": False})
    ok(rp.status_code == 200 and rp.json()["name"] == "POC Mandiri Giro 2" and rp.json()["is_active"] is False, "PATCH update/deactivate OK")
    ok(requests.get(f"{BASE}/bank-accounts", headers=H(manager)).status_code == 200, "manager -> list 200")
    ok(requests.get(f"{BASE}/bank-accounts", headers=H(sales)).status_code == 403, "sales -> list 403")
    ok(requests.get(f"{BASE}/bank-accounts/nope/ledger", headers=H(admin)).status_code == 404, "ledger akun tak dikenal -> 404")
    ok(requests.post(f"{BASE}/cash-transactions/nope/reconcile", headers=H(admin), json={"reconciled": True}).status_code == 404, "reconcile txn tak dikenal -> 404")

    print("\n" + "=" * 48)
    print(f"  HASIL: PASS {P} | FAIL {F}")
    print("=" * 48)
    return 0 if F == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
