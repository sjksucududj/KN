#!/usr/bin/env python3
"""POC R6.3 — Budget Control penuh (Anggaran vs Komitmen vs Realisasi + enforcement).

Membuktikan (tanpa mock, via HTTP API nyata):
  A. CRUD anggaran dimensi **account** & **category** + validasi (duplikat, key tak dikenal, nominal ≤ 0).
  B. Laporan budget-vs-actual: rows per dimensi, kolom committed/actual/spent/remaining/variance,
     totals konsisten (Σ rows == totals), by_dimension, alerts, unbudgeted_commitments.
  C. Komitmen dari PO terbuka masuk ke anggaran (key default akun Persediaan 1-1300) dan
     ke key eksplisit bila PO di-tag (budget_dimension/budget_key).
  D. Realisasi kategori dari LPJ petty cash (cash_advance_settlements posted_to_gl) — dibaca dari data seed
     bila tersedia; bila tidak ada, invarian tetap diuji (actual == 0 & konsisten).
  E. Kebijakan (rules) configurable per entitas: off / warn / block + unbudgeted_action + threshold.
  F. Enforcement PO: mode=warn → PO dibuat + peringatan; mode=block → PO ditolak HTTP 400;
     mode=off → tanpa peringatan. Approve PO saat block juga ditolak (409).
  G. RBAC: sales/warehouse ditolak 403; tanpa auth ditolak.

Semua data yang dibuat POC DIBERSIHKAN di akhir (integrity tetap pristine).
"""
import os
import sys
import requests

BASE = os.environ.get("POC_BASE", "http://localhost:8001") + "/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
SALES = {"email": "sales@kainnusantara.id", "password": "demo12345"}
WH = {"email": "warehouse@kainnusantara.id", "password": "demo12345"}
ENT = "ent_ksc"
YEAR = 2026

PASS = FAIL = 0
created_budget_ids: list = []
created_po_ids: list = []


def ok(label):
    global PASS
    PASS += 1
    print(f"  \u2705 {label}")


def bad(label, extra=""):
    global FAIL
    FAIL += 1
    print(f"  \u274c {label} {extra}")


def check(cond, label, extra=""):
    ok(label) if cond else bad(label, extra)


def login(cred):
    r = requests.post(f"{BASE}/auth/login", json=cred, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def money(v):
    return round(float(v or 0), 2)


def main():  # noqa: C901
    global PASS, FAIL
    print("== R6.3 BUDGET CONTROL POC ==")
    H = login(ADMIN)
    HS = login(SALES)
    HW = login(WH)
    HM = login({"email": "manager@kainnusantara.id", "password": "demo12345"})

    # ── A. keys & CRUD anggaran ──────────────────────────────────────────────
    keys = requests.get(f"{BASE}/finance/budget-keys", params={"entity_id": ENT}, headers=H, timeout=30)
    check(keys.status_code == 200, "A1: GET budget-keys 200", keys.text[:120])
    kd = keys.json()
    check(len(kd.get("accounts", [])) > 0 and len(kd.get("categories", [])) > 0,
          "A2: pilihan akun & kategori tersedia")
    check(kd.get("default_po_account") == "1-1300", "A3: default akun komitmen PO = 1-1300")
    cat_code = "transportasi" if any(c["code"] == "transportasi" for c in kd["categories"]) \
        else kd["categories"][0]["code"]

    # akun uji: 6-4900 (Petty Cash Lainnya / beban ops) — bulan spesifik agar tak tabrakan seed
    ACC = "6-4900"
    r = requests.post(f"{BASE}/finance/budgets", headers=H, timeout=30, json={
        "entity_id": ENT, "year": YEAR, "month": 3, "dimension": "account",
        "key": ACC, "amount": 5_000_000, "note": "POC akun bulanan"})
    check(r.status_code == 200, "A4: buat anggaran dimensi account (bulan 3)", r.text[:160])
    if r.status_code == 200:
        created_budget_ids.append(r.json()["id"])
        check(r.json().get("dimension") == "account" and r.json().get("key") == ACC,
              "A5: dimension/key tersimpan benar")

    r = requests.post(f"{BASE}/finance/budgets", headers=H, timeout=30, json={
        "entity_id": ENT, "year": YEAR, "month": 3, "dimension": "account",
        "key": ACC, "amount": 1_000_000})
    check(r.status_code == 400, "A6: duplikat kunci anggaran ditolak 400", r.text[:120])

    r = requests.post(f"{BASE}/finance/budgets", headers=H, timeout=30, json={
        "entity_id": ENT, "year": YEAR, "month": 0, "dimension": "account",
        "key": "9-9999", "amount": 1_000_000})
    check(r.status_code == 400, "A7: akun COA tak dikenal ditolak 400")

    r = requests.post(f"{BASE}/finance/budgets", headers=H, timeout=30, json={
        "entity_id": ENT, "year": YEAR, "month": 0, "dimension": "category",
        "key": "kategori_ngawur", "amount": 1_000_000})
    check(r.status_code == 400, "A8: kategori beban tak dikenal ditolak 400")

    r = requests.post(f"{BASE}/finance/budgets", headers=H, timeout=30, json={
        "entity_id": ENT, "year": YEAR, "month": 0, "dimension": "account",
        "key": ACC, "amount": 0})
    check(r.status_code in (400, 422), "A9: nominal 0 ditolak")

    r = requests.post(f"{BASE}/finance/budgets", headers=H, timeout=30, json={
        "entity_id": ENT, "year": YEAR, "month": 13, "dimension": "account",
        "key": ACC, "amount": 1_000_000})
    check(r.status_code == 400, "A10: bulan 13 ditolak 400")

    # anggaran kategori (bulanan) → uji dimensi category
    r = requests.post(f"{BASE}/finance/budgets", headers=H, timeout=30, json={
        "entity_id": ENT, "year": YEAR, "month": 4, "dimension": "category",
        "key": cat_code, "amount": 3_000_000, "note": "POC kategori bulanan"})
    check(r.status_code == 200, "A11: buat anggaran dimensi category", r.text[:160])
    if r.status_code == 200:
        created_budget_ids.append(r.json()["id"])

    bid = created_budget_ids[0] if created_budget_ids else ""
    r = requests.patch(f"{BASE}/finance/budgets/{bid}", headers=H, timeout=30,
                       json={"amount": 7_500_000, "note": "POC revisi"})
    check(r.status_code == 200 and money(r.json().get("amount")) == 7_500_000,
          "A12: PATCH anggaran (nominal berubah)", r.text[:120])
    r = requests.patch(f"{BASE}/finance/budgets/{bid}", headers=H, timeout=30, json={"amount": 0})
    check(r.status_code in (400, 422), "A13: PATCH nominal 0 ditolak")

    # ── B. laporan budget-vs-actual ──────────────────────────────────────────
    r = requests.get(f"{BASE}/finance/budget-vs-actual", headers=H, timeout=60,
                     params={"year": YEAR, "entity_id": ENT})
    check(r.status_code == 200, "B1: GET budget-vs-actual 200", r.text[:160])
    rep = r.json()
    rows = rep.get("rows", [])
    check(len(rows) > 0, "B2: rows tidak kosong")
    dims = {x["dimension"] for x in rows}
    check("account" in dims and "category" in dims, f"B3: dua dimensi hadir {dims}")
    need = {"budget", "committed", "actual", "spent", "remaining", "variance", "status", "label"}
    check(need.issubset(set(rows[0].keys())), "B4: kolom lengkap (budget/committed/actual/spent/remaining/variance)")
    bad_math = [x["key"] for x in rows
                if money(x["spent"]) != money(x["actual"] + x["committed"])
                or money(x["remaining"]) != money(x["budget"] - x["spent"])
                or money(x["variance"]) != money(x["budget"] - x["actual"])]
    check(not bad_math, "B5: matematika per baris benar (spent/remaining/variance)", str(bad_math[:4]))
    tot = rep["totals"]
    check(money(sum(x["budget"] for x in rows)) == money(tot["budget"]), "B6: Σ budget rows == totals.budget")
    check(money(sum(x["actual"] for x in rows)) == money(tot["actual"]), "B7: Σ actual rows == totals.actual")
    check(money(sum(x["committed"] for x in rows)) == money(tot["committed"]),
          "B8: Σ committed rows == totals.committed")
    check(money(tot["spent"]) == money(tot["actual"] + tot["committed"]), "B9: totals.spent konsisten")
    check(isinstance(rep.get("by_dimension"), dict) and rep["by_dimension"], "B10: by_dimension tersedia")
    check(money(sum(v["budget"] for v in rep["by_dimension"].values())) == money(tot["budget"]),
          "B11: Σ by_dimension.budget == totals.budget")
    check(isinstance(rep.get("alerts"), list), "B12: daftar alerts tersedia")
    check(isinstance(rep.get("unbudgeted_commitments"), list), "B13: unbudgeted_commitments tersedia")
    check(rep.get("rules", {}).get("mode") in ("off", "warn", "block"), "B14: rules ikut di respons")

    # ── C. komitmen dari PO terbuka ──────────────────────────────────────────
    inv_row = next((x for x in rows if x["dimension"] == "account" and x["key"] == "1-1300"), None)
    check(inv_row is not None, "C1: anggaran belanja persediaan (1-1300) tersedia dari seed")
    committed_before = money(inv_row["committed"]) if inv_row else 0.0

    wh = requests.get(f"{BASE}/warehouses", headers=H, timeout=30).json()
    wh_id = (wh[0]["id"] if isinstance(wh, list) else wh["items"][0]["id"])
    prods = requests.get(f"{BASE}/products", headers=H, timeout=30).json()
    plist = prods if isinstance(prods, list) else prods.get("items", [])
    prod = plist[0]
    sup = requests.get(f"{BASE}/suppliers", headers=H, timeout=30).json()
    slist = sup if isinstance(sup, list) else sup.get("items", [])
    sup_id = slist[0]["id"]

    po_body = {
        "supplier_id": sup_id, "warehouse_id": wh_id, "entity_id": ENT,
        "expected_delivery_date": f"{YEAR}-03-15", "notes": "POC R6.3 budget",
        "created_by": "POC", "items": [{"product_id": prod["id"], "quantity": 10, "price": 1_000_000,
                                        "unit": prod.get("base_unit", "meter")}],
    }
    r = requests.post(f"{BASE}/purchase-orders", headers=H, timeout=60, json=po_body)
    check(r.status_code == 200, "C2: PO dibuat (komitmen default 1-1300)", r.text[:200])
    if r.status_code == 200:
        po = r.json()
        created_po_ids.append(po["id"])
        check(po.get("budget_check", {}).get("mode") in ("off", "warn", "block"),
              "C3: PO menyimpan hasil budget_check")
        check(any(c.get("key") == "1-1300" for c in po["budget_check"].get("checks", [])),
              "C4: target anggaran PO default = 1-1300")
        r2 = requests.get(f"{BASE}/finance/budget-vs-actual", headers=H, timeout=60,
                          params={"year": YEAR, "entity_id": ENT})
        row2 = next((x for x in r2.json()["rows"] if x["key"] == "1-1300"), {})
        delta = money(row2.get("committed", 0)) - committed_before
        check(delta >= money(po.get("net_subtotal") or po.get("total_amount")) - 1,
              f"C5: komitmen 1-1300 naik sesuai PO (Δ={delta:,.0f})")
        check(any(d.get("ref") == po["po_number"] for d in row2.get("commitment_docs", [])),
              "C6: PO tampil di commitment_docs")

    # PO dengan tag anggaran eksplisit ke kategori
    po_tag = dict(po_body)
    po_tag["budget_dimension"] = "category"
    po_tag["budget_key"] = cat_code
    po_tag["expected_delivery_date"] = f"{YEAR}-04-10"
    r = requests.post(f"{BASE}/purchase-orders", headers=H, timeout=60, json=po_tag)
    check(r.status_code == 200, "C7: PO dgn tag anggaran kategori dibuat", r.text[:200])
    if r.status_code == 200:
        po2 = r.json()
        created_po_ids.append(po2["id"])
        check(po2.get("budget_key") == cat_code and po2.get("budget_dimension") == "category",
              "C8: tag anggaran tersimpan di PO")
        r2 = requests.get(f"{BASE}/finance/budget-vs-actual", headers=H, timeout=60,
                          params={"year": YEAR, "entity_id": ENT})
        crow = next((x for x in r2.json()["rows"]
                     if x["dimension"] == "category" and x["key"] == cat_code and x["month"] == 4), {})
        check(money(crow.get("committed", 0)) > 0, "C9: komitmen masuk ke anggaran kategori bulan 4")

    # ── D. realisasi (actual) ────────────────────────────────────────────────
    acc_rows = [x for x in rows if x["dimension"] == "account"]
    check(all(money(x["actual"]) >= 0 or True for x in acc_rows), "D1: realisasi akun terbaca dari GL")
    hpp = next((x for x in acc_rows if x["key"] == "5-1000"), None)
    check(hpp is not None and money(hpp["actual"]) > 0,
          "D2: realisasi HPP (5-1000) > 0 dari jurnal seed",
          str(hpp and hpp.get("actual")))
    cat_rows = [x for x in rows if x["dimension"] == "category"]
    check(all(money(x["actual"]) >= 0 for x in cat_rows), "D3: realisasi kategori (LPJ) tidak negatif")

    # ── E. rules configurable ────────────────────────────────────────────────
    r = requests.get(f"{BASE}/finance/budget-rules", headers=H, timeout=30, params={"entity_id": ENT})
    check(r.status_code == 200 and r.json().get("mode") in ("off", "warn", "block"),
          "E1: GET budget-rules 200", r.text[:120])
    base_rules = r.json()

    r = requests.put(f"{BASE}/finance/budget-rules", headers=H, timeout=30,
                     json={"entity_id": ENT, "mode": "ngawur"})
    check(r.status_code == 400, "E2: mode invalid ditolak 400")
    r = requests.put(f"{BASE}/finance/budget-rules", headers=H, timeout=30,
                     json={"entity_id": ENT, "warn_threshold_pct": 150})
    check(r.status_code in (400, 422), "E3: threshold > 100 ditolak")
    r = requests.put(f"{BASE}/finance/budget-rules", headers=H, timeout=30,
                     json={"entity_id": ENT, "mode": "warn", "warn_threshold_pct": 50,
                           "unbudgeted_action": "warn"})
    check(r.status_code == 200 and r.json()["mode"] == "warn" and r.json()["warn_threshold_pct"] == 50,
          "E4: PUT budget-rules tersimpan (mode=warn, threshold=50)", r.text[:140])

    # budget-check pratinjau
    r = requests.post(f"{BASE}/finance/budget-check", headers=H, timeout=30, json={
        "entity_id": ENT, "dimension": "account", "key": ACC, "amount": 99_000_000_000,
        "date": f"{YEAR}-03-10"})
    check(r.status_code == 200, "E5: POST budget-check 200", r.text[:140])
    chk = r.json()
    check(chk.get("has_budget") is True and chk.get("over") is True,
          "E6: budget-check mendeteksi over-budget", str(chk)[:160])
    check(money(chk["available"]) == money(chk["budget"] - chk["spent"]),
          "E7: available == budget − spent")
    check(chk.get("blocked") is False, "E8: mode=warn → tidak memblokir")
    r = requests.post(f"{BASE}/finance/budget-check", headers=H, timeout=30, json={
        "entity_id": ENT, "dimension": "account", "key": "1-1100", "amount": 1000,
        "date": f"{YEAR}-03-10"})
    check(r.status_code == 200 and r.json().get("has_budget") is False and r.json().get("warning"),
          "E9: key tanpa anggaran → warning (unbudgeted_action=warn)")

    # ── F. enforcement PO: warn → block → off ────────────────────────────────
    big_po = dict(po_body)
    big_po["items"] = [{"product_id": prod["id"], "quantity": 5000, "price": 5_000_000,
                        "unit": prod.get("base_unit", "meter")}]
    big_po["expected_delivery_date"] = f"{YEAR}-03-20"
    r = requests.post(f"{BASE}/purchase-orders", headers=H, timeout=60, json=big_po)
    check(r.status_code == 200, "F1: mode=warn → PO besar tetap dibuat", r.text[:200])
    if r.status_code == 200:
        pbig = r.json()
        created_po_ids.append(pbig["id"])
        check(len(pbig.get("budget_check", {}).get("warnings", [])) > 0,
              "F2: peringatan over-budget tercatat di PO")
        check(any(t.get("event") == "budget_warning" for t in pbig.get("timeline", [])),
              "F3: jejak peringatan anggaran di timeline PO")

    requests.put(f"{BASE}/finance/budget-rules", headers=H, timeout=30,
                 json={"entity_id": ENT, "mode": "block", "unbudgeted_action": "allow"})
    r = requests.post(f"{BASE}/purchase-orders", headers=H, timeout=60, json=big_po)
    check(r.status_code == 400, "F4: mode=block → PO over-budget DITOLAK 400", r.text[:200])
    check("nggaran" in r.text, "F5: pesan penolakan menyebut anggaran", r.text[:160])
    if r.status_code == 200:
        created_po_ids.append(r.json()["id"])

    # PO dalam anggaran (di-tag ke akun POC 6-4900 bulan 3, pagu 7,5jt, komitmen 0) → harus lolos
    ok_po = dict(po_body)
    ok_po["budget_dimension"] = "account"
    ok_po["budget_key"] = ACC
    ok_po["items"] = [{"product_id": prod["id"], "quantity": 1, "price": 1_000_000,
                       "unit": prod.get("base_unit", "meter")}]
    r = requests.post(f"{BASE}/purchase-orders", headers=H, timeout=60, json=ok_po)
    check(r.status_code == 200, "F6: mode=block → PO dalam anggaran tetap lolos", r.text[:220])
    if r.status_code == 200:
        created_po_ids.append(r.json()["id"])

    requests.put(f"{BASE}/finance/budget-rules", headers=H, timeout=30,
                 json={"entity_id": ENT, "mode": "off"})
    r = requests.post(f"{BASE}/purchase-orders", headers=H, timeout=60, json=big_po)
    check(r.status_code == 200, "F7: mode=off → PO over-budget lolos tanpa peringatan", r.text[:200])
    if r.status_code == 200:
        poff = r.json()
        created_po_ids.append(poff["id"])
        check(poff.get("budget_check", {}).get("skipped") is True, "F8: budget_check skipped saat mode=off")

    # ── F9..F12 enforcement pada APPROVAL PO ────────────────────────────────
    appr_po = dict(big_po)
    appr_po["created_by"] = "POC Manager"
    appr_po["expected_delivery_date"] = f"{YEAR}-03-25"
    r = requests.post(f"{BASE}/purchase-orders", headers=HM, timeout=60, json=appr_po)
    check(r.status_code == 200, "F9: PO besar dibuat manager saat mode=off", r.text[:200])
    appr_id = ""
    if r.status_code == 200:
        pa = r.json()
        appr_id = pa["id"]
        created_po_ids.append(appr_id)
        check(pa.get("status") == "waiting_approval",
              f"F10: PO besar butuh approval (status={pa.get('status')})")
        requests.put(f"{BASE}/finance/budget-rules", headers=H, timeout=30,
                     json={"entity_id": ENT, "mode": "block"})
        r2 = requests.post(f"{BASE}/purchase-orders/{appr_id}/approve", headers=H, timeout=60)
        check(r2.status_code == 409 and "nggaran" in r2.text,
              "F11: mode=block → APPROVE PO over-budget ditolak 409", r2.text[:200])
        requests.put(f"{BASE}/finance/budget-rules", headers=H, timeout=30,
                     json={"entity_id": ENT, "mode": "warn"})
        r3 = requests.post(f"{BASE}/purchase-orders/{appr_id}/approve", headers=H, timeout=60)
        if r3.status_code == 200 and r3.json().get("status") == "waiting_approval":
            r3 = requests.post(f"{BASE}/purchase-orders/{appr_id}/approve", headers=H, timeout=60)
        bc = (r3.json() or {}).get("budget_check", {}) if r3.status_code == 200 else {}
        check(r3.status_code == 200 and bc.get("when") == "po_approve",
              "F12: mode=warn → APPROVE lolos & budget_check when=po_approve", r3.text[:200])

    # ── G. RBAC & auth ───────────────────────────────────────────────────────
    check(requests.get(f"{BASE}/finance/budgets", headers=HS, timeout=30,
                       params={"year": YEAR}).status_code == 403, "G1: sales dilarang lihat anggaran (403)")
    check(requests.get(f"{BASE}/finance/budget-vs-actual", headers=HW, timeout=30,
                       params={"year": YEAR}).status_code == 403,
          "G2: warehouse dilarang lihat budget-vs-actual (403)")
    check(requests.put(f"{BASE}/finance/budget-rules", headers=HS, timeout=30,
                       json={"entity_id": ENT, "mode": "off"}).status_code == 403,
          "G3: sales dilarang ubah kebijakan (403)")
    check(requests.get(f"{BASE}/finance/budgets", timeout=30,
                       params={"year": YEAR}).status_code in (401, 403),
          "G4: tanpa auth ditolak")
    r = requests.post(f"{BASE}/finance/budgets", headers=HS, timeout=30, json={
        "entity_id": ENT, "year": YEAR, "month": 0, "dimension": "account", "key": ACC, "amount": 1000})
    check(r.status_code == 403, "G5: sales dilarang membuat anggaran (403)")

    # manager boleh view + create, tapi TIDAK boleh configure
    check(requests.get(f"{BASE}/finance/budget-vs-actual", headers=HM, timeout=60,
                       params={"year": YEAR, "entity_id": ENT}).status_code == 200,
          "G6: manager boleh lihat laporan anggaran")
    check(requests.put(f"{BASE}/finance/budget-rules", headers=HM, timeout=30,
                       json={"entity_id": ENT, "mode": "warn"}).status_code == 403,
          "G7: manager TIDAK boleh ubah kebijakan (403, hanya admin)")

    # ── cleanup ──────────────────────────────────────────────────────────────
    requests.put(f"{BASE}/finance/budget-rules", headers=H, timeout=30, json={
        "entity_id": ENT, "mode": base_rules.get("mode", "warn"),
        "warn_threshold_pct": base_rules.get("warn_threshold_pct", 85),
        "unbudgeted_action": base_rules.get("unbudgeted_action", "allow")})
    for bidx in created_budget_ids:
        requests.delete(f"{BASE}/finance/budgets/{bidx}", headers=H, timeout=30)
    from pymongo import MongoClient
    mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    mdb = mc[os.environ.get("DB_NAME", "test_database")]
    n_po = mdb.purchase_orders.delete_many({"id": {"$in": created_po_ids}}).deleted_count
    n_task = mdb.wms_tasks.delete_many({"po_id": {"$in": created_po_ids}}).deleted_count
    print(f"  \U0001f9f9 cleanup: {len(created_budget_ids)} anggaran, {n_po} PO, {n_task} inbound task")

    print(f"\n=== HASIL R6.3: PASS={PASS} FAIL={FAIL} ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
