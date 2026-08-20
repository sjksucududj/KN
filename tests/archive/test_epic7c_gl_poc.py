"""POC EPIC7-C — Chart of Accounts + General Ledger.

User stories diuji:
- Bagan akun baku terseed (5 tipe, normal balance benar, akun kunci ada).
- CoA CRUD: buat akun, kode duplikat 400, hapus akun sistem 400, hapus akun custom OK.
- Auto-posting idempotent dari SSOT (sales_orders + cash_transactions); sync 2× tidak double.
- Trial balance SEIMBANG (Σdebit == Σkredit) & ada saldo akun kunci.
- Jurnal manual: seimbang OK, tidak seimbang 400, akun header 400, akun nonpostable 400.
- Buku besar 1 akun: running balance konsisten dgn saldo trial balance.
- Void jurnal manual OK; void jurnal otomatis 400.
- RBAC: sales & warehouse TIDAK punya akses akuntansi (403); admin/manager punya.
"""
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
    warehouse = login("warehouse@kainnusantara.id")

    # ─── CoA baku ────────────────────────────────────────────────────────────
    print("=== Chart of Accounts (baku) ===")
    r = requests.get(f"{BASE}/gl/accounts", headers=H(admin))
    ok(r.status_code == 200, f"GET /gl/accounts 200 ({r.status_code})")
    accs = r.json()
    ok(isinstance(accs, list) and len(accs) >= 30, f"≥30 akun baku terseed ({len(accs)})")
    types = {a["type"] for a in accs}
    ok(types == {"asset", "liability", "equity", "income", "expense"}, f"5 tipe akun ada ({types})")
    amap = {a["code"]: a for a in accs}
    for code in ["1-1100", "1-1200", "2-1100", "2-1200", "3-1000", "4-1000", "5-1000", "6-4000"]:
        ok(code in amap, f"akun kunci {code} ada")
    ok(amap["1-1200"]["normal_balance"] == "debit", "Piutang normal_balance=debit")
    ok(amap["4-1000"]["normal_balance"] == "credit", "Pendapatan normal_balance=credit")
    ok(amap["1-1100"]["is_postable"] and not amap["1-0000"]["is_postable"], "header (1-0000) non-postable, detail (1-1100) postable")
    ok(amap["1-1100"].get("system") is True, "akun baku ber-flag system")

    # ─── CoA CRUD ────────────────────────────────────────────────────────────
    print("\n=== CoA CRUD + guard ===")
    new_code = "6-5500"
    requests.delete(f"{BASE}/gl/accounts/{new_code}", headers=H(admin))  # bersihkan bila ada
    rc = requests.post(f"{BASE}/gl/accounts", headers=H(admin), json={
        "code": new_code, "name": "Beban Pemasaran POC", "type": "expense", "parent_code": "6-0000"})
    ok(rc.status_code == 200, f"POST akun baru 200 ({rc.status_code})")
    ok(rc.json().get("normal_balance") == "debit", "akun expense baru normal_balance=debit")
    rdup = requests.post(f"{BASE}/gl/accounts", headers=H(admin), json={
        "code": new_code, "name": "dup", "type": "expense"})
    ok(rdup.status_code == 400, f"kode duplikat ditolak 400 ({rdup.status_code})")
    rsys = requests.delete(f"{BASE}/gl/accounts/1-1100", headers=H(admin))
    ok(rsys.status_code == 400, f"hapus akun sistem ditolak 400 ({rsys.status_code})")
    rdel = requests.delete(f"{BASE}/gl/accounts/{new_code}", headers=H(admin))
    ok(rdel.status_code == 200, f"hapus akun custom (belum dipakai) OK ({rdel.status_code})")

    # ─── Auto-posting idempotent ─────────────────────────────────────────────
    print("\n=== Auto-posting (sync) idempotent ===")
    s1 = requests.post(f"{BASE}/gl/sync", headers=H(admin))
    ok(s1.status_code == 200, f"POST /gl/sync 200 ({s1.status_code})")
    sum1 = requests.get(f"{BASE}/gl/summary", headers=H(admin)).json()
    count1 = sum1["journal_count"]
    ok(count1 >= 15, f"≥15 jurnal otomatis terposting ({count1})")
    s2 = requests.post(f"{BASE}/gl/sync", headers=H(admin)).json()
    ok(s2.get("total") == 0, f"sync ke-2 tidak posting ulang (total={s2.get('total')})")
    count2 = requests.get(f"{BASE}/gl/summary", headers=H(admin)).json()["journal_count"]
    ok(count1 == count2, f"jumlah jurnal stabil setelah sync ulang ({count1}=={count2})")

    # ─── Trial balance ───────────────────────────────────────────────────────
    print("\n=== Neraca Saldo (trial balance) ===")
    tb = requests.get(f"{BASE}/gl/trial-balance", headers=H(admin))
    ok(tb.status_code == 200, f"GET /gl/trial-balance 200 ({tb.status_code})")
    tbd = tb.json()
    ok(tbd["balanced"] is True, f"trial balance SEIMBANG (D={tbd['total_debit']:,.0f} K={tbd['total_credit']:,.0f})")
    ok(approx(tbd["total_debit"], tbd["total_credit"]), "Σdebit == Σkredit")
    rows = {r["code"]: r for r in tbd["rows"]}
    ok("1-1200" in rows and rows["1-1200"]["debit_balance"] > 0, "Piutang Usaha bersaldo debit")
    ok("4-1000" in rows and rows["4-1000"]["credit_balance"] > 0, "Pendapatan Penjualan bersaldo kredit")

    # ─── Manual journal entry + validasi ─────────────────────────────────────
    print("\n=== Jurnal manual + validasi balance ===")
    je = requests.post(f"{BASE}/gl/journal", headers=H(admin), json={
        "description": "POC penyesuaian", "lines": [
            {"account_code": "6-2000", "debit": 1000000, "credit": 0},
            {"account_code": "1-1100", "debit": 0, "credit": 1000000},
        ]})
    ok(je.status_code == 200, f"POST jurnal seimbang 200 ({je.status_code})")
    je_id = je.json()["id"]
    ok(approx(je.json()["total_debit"], 1000000) and "JE-" in str(je.json()["number"]), "jurnal punya number JE- & total benar")
    bad = requests.post(f"{BASE}/gl/journal", headers=H(admin), json={
        "lines": [{"account_code": "6-2000", "debit": 1000000, "credit": 0},
                  {"account_code": "1-1100", "debit": 0, "credit": 900000}]})
    ok(bad.status_code == 400, f"jurnal tidak seimbang ditolak 400 ({bad.status_code})")
    hdr = requests.post(f"{BASE}/gl/journal", headers=H(admin), json={
        "lines": [{"account_code": "1-0000", "debit": 500000, "credit": 0},
                  {"account_code": "1-1100", "debit": 0, "credit": 500000}]})
    ok(hdr.status_code == 400, f"jurnal ke akun header ditolak 400 ({hdr.status_code})")

    # ─── Account ledger drill-down ───────────────────────────────────────────
    print("\n=== Buku Besar per akun ===")
    led = requests.get(f"{BASE}/gl/accounts/1-1100/ledger", headers=H(admin))
    ok(led.status_code == 200, f"GET /gl/accounts/1-1100/ledger 200 ({led.status_code})")
    ld = led.json()
    ok(len(ld["lines"]) > 0 and all("running_balance" in l for l in ld["lines"]), "tiap baris buku besar punya running_balance")
    # bandingkan dgn trial balance SEGAR (hindari drift akibat jurnal manual di atas)
    rows2 = {r["code"]: r for r in requests.get(f"{BASE}/gl/trial-balance", headers=H(admin)).json()["rows"]}
    ok(approx(ld["balance"], rows2["1-1100"]["debit_balance"] - rows2["1-1100"]["credit_balance"]),
       "saldo buku besar 1-1100 == saldo trial balance")

    # ─── Void manual vs auto ─────────────────────────────────────────────────
    print("\n=== Void jurnal ===")
    rv = requests.post(f"{BASE}/gl/journal/{je_id}/void", headers=H(admin))
    ok(rv.status_code == 200 and rv.json()["status"] == "void", f"void jurnal manual OK ({rv.status_code})")
    autos = [e for e in requests.get(f"{BASE}/gl/journal", headers=H(admin), params={"source": "sales_order"}).json()]
    if autos:
        rva = requests.post(f"{BASE}/gl/journal/{autos[0]['id']}/void", headers=H(admin))
        ok(rva.status_code == 400, f"void jurnal otomatis ditolak 400 ({rva.status_code})")

    # ─── Filter & manager access ─────────────────────────────────────────────
    print("\n=== Filter sumber + akses manager ===")
    fl = requests.get(f"{BASE}/gl/journal", headers=H(manager), params={"source": "cash_transaction"})
    ok(fl.status_code == 200 and all(e["source_type"] == "cash_transaction" for e in fl.json()), "manager: filter source=cash_transaction benar")
    ok(requests.get(f"{BASE}/gl/trial-balance", headers=H(manager)).status_code == 200, "manager akses trial-balance OK")

    # ─── RBAC negatif ────────────────────────────────────────────────────────
    print("\n=== RBAC (sales & warehouse ditolak) ===")
    ok(requests.get(f"{BASE}/gl/accounts", headers=H(sales)).status_code == 403, "sales GET /gl/accounts 403")
    ok(requests.get(f"{BASE}/gl/trial-balance", headers=H(sales)).status_code == 403, "sales GET /gl/trial-balance 403")
    ok(requests.post(f"{BASE}/gl/journal", headers=H(sales), json={"lines": []}).status_code == 403, "sales POST jurnal 403")
    ok(requests.get(f"{BASE}/gl/accounts", headers=H(warehouse)).status_code == 403, "warehouse GET /gl/accounts 403")

    print(f"\n{'='*54}\n  PASS {P}  |  FAIL {F}\n{'='*54}")
    return F == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
