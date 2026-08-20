"""R6.1 — Bank Reconciliation otomatis — POC.

Membuktikan (append-only, GL-safe, idempotent):
  A. Import statement lines (dedup) → tersimpan status unmatched.
  B. Auto-match 1:1 statement↔cash_transaction (arah+nominal+window tanggal): baris cocok jadi matched,
     cash_transaction ditandai reconciled; baris tanpa pasangan tetap unmatched.
  C. Manual unmatch → reconciled dilepas; manual match → tertaut lagi.
  D. Summary: hitung matched/unmatched + selisih statement vs buku.
  E. Idempotent: auto-match ulang tak menambah match.
  F. Ignore baris.
  G. GL-safe: jumlah journal_entries TIDAK berubah oleh proses rekonsiliasi.
"""
import os
import sys
import requests
from pymongo import MongoClient

try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

API = f"{os.environ.get('R5_BASE', 'http://localhost:8001')}/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
DBS = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
    os.environ.get("DB_NAME", "test_database")]
PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  \u2705 {name}")
    else:
        FAIL += 1; print(f"  \u274c {name}  {extra}")


def login():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def mk_txn(h, acct, direction, amount, date):
    body = {"cash_type": "kas_kecil", "direction": direction, "amount": amount,
            "category": "reconcile-poc", "description": f"POC {direction} {amount}",
            "entity_id": "ent_ksc", "account_id": acct, "txn_date": f"{date}T04:00:00",
            "created_by": "poc"}
    r = requests.post(f"{API}/cash-transactions", headers=h, json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    global PASS, FAIL
    h = login()
    print("== R6.1 BANK RECONCILIATION POC ==")
    acct = "bank_bca_ksc"
    je_before = DBS.journal_entries.count_documents({})

    # Buat 3 transaksi buku (cash_transactions) + 1 tanpa pasangan statement.
    t1 = mk_txn(h, acct, "in", 5_000_000, "2026-06-10")
    t2 = mk_txn(h, acct, "out", 1_250_000, "2026-06-11")
    t3 = mk_txn(h, acct, "in", 750_000, "2026-06-12")

    # A) Import statement lines (3 cocok + 1 extra tak cocok). Impor 2x utk uji dedup.
    lines = [
        {"stmt_date": "2026-06-10", "amount": 5_000_000, "direction": "in", "description": "TRSF MASUK", "ref": t1["number"], "external_id": "BCA-1"},
        {"stmt_date": "2026-06-12", "amount": 1_250_000, "direction": "out", "description": "BAYAR VENDOR", "ref": "", "external_id": "BCA-2"},
        {"stmt_date": "2026-06-12", "amount": 750_000, "direction": "in", "description": "SETORAN", "ref": "", "external_id": "BCA-3"},
        {"stmt_date": "2026-06-13", "amount": 999_999, "direction": "out", "description": "BIAYA ADMIN", "ref": "", "external_id": "BCA-4"},
    ]
    imp = requests.post(f"{API}/bank-reconciliation/import", headers=h, timeout=30,
                        json={"bank_account_id": acct, "entity_id": "ent_ksc", "lines": lines})
    check("A1: import → 200", imp.status_code == 200, f"{imp.status_code} {imp.text[:160]}")
    check("A2: 4 baris terimpor", imp.json().get("imported") == 4, str(imp.json()))
    imp2 = requests.post(f"{API}/bank-reconciliation/import", headers=h, timeout=30,
                         json={"bank_account_id": acct, "entity_id": "ent_ksc", "lines": lines})
    check("A3: dedup — impor ulang 0 baru, 4 skip", imp2.json().get("imported") == 0 and imp2.json().get("skipped") == 4,
          str(imp2.json()))

    # B) Auto-match
    am = requests.post(f"{API}/bank-reconciliation/auto-match", headers=h, timeout=30,
                       json={"bank_account_id": acct, "window_days": 3})
    check("B1: auto-match → 200", am.status_code == 200, f"{am.status_code} {am.text[:160]}")
    res = am.json()
    check("B2: 3 baris ter-match (extra tetap unmatched)", res.get("matched") == 3,
          f"matched={res.get('matched')} unmatched_lines={res.get('unmatched_lines')}")
    check("B3: >=1 baris unmatched tersisa", res.get("unmatched_lines") >= 1, str(res))
    for t in (t1, t2, t3):
        d = DBS.cash_transactions.find_one({"id": t["id"]}, {"_id": 0})
        check(f"B4: txn {t['number']} reconciled==True", d.get("reconciled") is True, str(d.get("reconciled")))

    # C) Manual unmatch + match balik (pakai line BCA-1 ↔ t1)
    l1 = DBS.bank_statement_lines.find_one({"external_id": "BCA-1"}, {"_id": 0})
    um = requests.post(f"{API}/bank-reconciliation/lines/{l1['id']}/unmatch", headers=h, timeout=30)
    check("C1: unmatch → 200", um.status_code == 200, um.text[:120])
    d1 = DBS.cash_transactions.find_one({"id": t1["id"]}, {"_id": 0})
    check("C2: txn t1 reconciled dilepas (False)", d1.get("reconciled") is not True, str(d1.get("reconciled")))
    mm = requests.post(f"{API}/bank-reconciliation/lines/{l1['id']}/match", headers=h, timeout=30,
                       json={"txn_id": t1["id"]})
    check("C3: manual match → 200", mm.status_code == 200, mm.text[:120])
    d1b = DBS.cash_transactions.find_one({"id": t1["id"]}, {"_id": 0})
    check("C4: txn t1 reconciled lagi (True)", d1b.get("reconciled") is True, str(d1b.get("reconciled")))

    # D) Summary
    sm = requests.get(f"{API}/bank-reconciliation/summary", headers=h,
                      params={"bank_account_id": acct}, timeout=30)
    check("D1: summary → 200", sm.status_code == 200, sm.text[:120])
    s = sm.json()
    check("D2: matched == 3", s.get("matched") == 3, str(s.get("matched")))
    check("D3: unmatched_lines >= 1", s.get("unmatched_lines") >= 1, str(s.get("unmatched_lines")))
    check("D4: statement.in mencakup 5.75jt", abs(s["statement"]["in"] - 5_750_000) < 1, str(s.get("statement")))

    # E) Idempotent
    am2 = requests.post(f"{API}/bank-reconciliation/auto-match", headers=h, timeout=30,
                        json={"bank_account_id": acct, "window_days": 3})
    check("E: auto-match ulang matched==0", am2.json().get("matched") == 0, str(am2.json()))

    # F) Ignore baris extra (BCA-4)
    l4 = DBS.bank_statement_lines.find_one({"external_id": "BCA-4"}, {"_id": 0})
    ig = requests.post(f"{API}/bank-reconciliation/lines/{l4['id']}/ignore", headers=h, timeout=30)
    check("F1: ignore → 200", ig.status_code == 200, ig.text[:120])
    l4b = DBS.bank_statement_lines.find_one({"external_id": "BCA-4"}, {"_id": 0})
    check("F2: status ignored", l4b.get("status") == "ignored", str(l4b.get("status")))

    # G) GL-safe: journal_entries tak bertambah oleh rekonsiliasi
    je_after = DBS.journal_entries.count_documents({})
    check("G: GL journal_entries TIDAK berubah oleh rekonsiliasi", je_after == je_before,
          f"before={je_before} after={je_after}")

    print(f"\n=== HASIL R6.1: PASS={PASS} FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
