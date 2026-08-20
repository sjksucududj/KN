"""R6.2 — Fixed Assets & Depresiasi (straight-line) + disposal gain/loss — POC.

Membuktikan (GL-safe, idempotent, self-balancing):
  A. Create aset → posting perolehan (Dr <akun aset> / Cr 1-1100 Kas/Bank), JE seimbang.
  B. Run depreciation periode → Dr 6-6000 / Cr 1-2900 sebesar (cost−salvage)/life; accumulated & book_value update.
  C. Idempotent: rerun periode sama → 0 posting.
  D. Multi-periode akumulasi bertambah linear.
  E. Disposal GAIN (proceeds > book value) → JE seimbang + akun Laba 4-9100 dikredit.
  F. Disposal LOSS (proceeds < book value) → JE seimbang + akun Rugi 6-9500 didebit.
  G. Subledger: accumulated aset == Σ entri penyusutan.
  H. GL: trial balance tetap seimbang (Σdebit == Σkredit) global.
  Cleanup: hapus semua data yang dibuat POC → state pristine (integrity 126/0/0).
"""
import os
import sys
import re
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
ENTITY = "ent_ksc"


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


def je_by_source(source_type, source_id):
    return DBS.journal_entries.find_one(
        {"source_type": source_type, "source_id": source_id, "status": {"$ne": "void"}}, {"_id": 0})


def je_balanced(je):
    if not je:
        return False
    d = round(sum(float(l.get("debit", 0) or 0) for l in je.get("lines", [])), 2)
    c = round(sum(float(l.get("credit", 0) or 0) for l in je.get("lines", [])), 2)
    return abs(d - c) < 0.01 and abs(d - float(je.get("total_debit", 0) or 0)) < 0.01


def line_amt(je, code, side):
    for l in (je or {}).get("lines", []):
        if l.get("account_code") == code:
            return round(float(l.get(side, 0) or 0), 2)
    return 0.0


def create_asset(h, name, cost, life, salvage=0, category="Peralatan & Mesin", acq_date="2026-07-01"):
    body = {"name": name, "category": category, "acquisition_cost": cost,
            "useful_life_months": life, "salvage_value": salvage,
            "acquisition_date": acq_date, "entity_id": ENTITY}
    r = requests.post(f"{API}/fixed-assets", headers=h, json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def run_dep(h, period, asset_id=None):
    body = {"period": period, "entity_id": ENTITY}
    if asset_id:
        body["asset_id"] = asset_id
    r = requests.post(f"{API}/fixed-assets/run-depreciation", headers=h, json=body, timeout=60)
    r.raise_for_status()
    return r.json()


def dispose(h, asset_id, proceeds, date="2026-10-01"):
    r = requests.post(f"{API}/fixed-assets/{asset_id}/dispose", headers=h,
                      json={"proceeds": proceeds, "date": date, "note": "POC disposal"}, timeout=30)
    return r


def main():
    h = login()
    print("== R6.2 FIXED ASSETS & DEPRECIATION POC ==")
    created = []
    try:
        # A) Create asset 1 (gain scenario): cost 12jt, life 12 → monthly 1jt
        a1 = create_asset(h, "Mesin Jahit Industri", 12_000_000, 12)
        created.append(a1["id"])
        check("A1: asset dibuat (status active)", a1.get("status") == "active", str(a1.get("status")))
        check("A2: monthly_depreciation == 1.000.000", abs(a1.get("monthly_depreciation", 0) - 1_000_000) < 1, str(a1.get("monthly_depreciation")))
        acq = je_by_source("fixed_asset_acquisition", a1["id"])
        check("A3: JE perolehan terposting & seimbang", je_balanced(acq), str(acq))
        check("A4: perolehan Dr akun aset (1-2100)=12jt", line_amt(acq, "1-2100", "debit") == 12_000_000, str(acq and acq.get("lines")))
        check("A5: perolehan Cr Kas/Bank (1-1100)=12jt", line_amt(acq, "1-1100", "credit") == 12_000_000, "")

        # B) Depreciation period 2026-07
        r1 = run_dep(h, "2026-07", a1["id"])
        check("B1: 1 aset tersusutkan", r1.get("posted") == 1, str(r1))
        check("B2: amount periode == 1jt", abs(r1.get("total_amount", 0) - 1_000_000) < 1, str(r1))
        dep_je = je_by_source("fixed_asset_depreciation", f"{a1['id']}:2026-07")
        check("B3: JE penyusutan seimbang", je_balanced(dep_je), str(dep_je))
        check("B4: Dr Beban Penyusutan 6-6000=1jt", line_amt(dep_je, "6-6000", "debit") == 1_000_000, "")
        check("B5: Cr Akumulasi 1-2900=1jt", line_amt(dep_je, "1-2900", "credit") == 1_000_000, "")

        # C) Idempotent rerun periode sama
        r1b = run_dep(h, "2026-07", a1["id"])
        check("C: rerun periode sama → 0 posting", r1b.get("posted") == 0, str(r1b))

        # D) Periode 2026-08 → akumulasi 2jt
        run_dep(h, "2026-08", a1["id"])
        a1x = requests.get(f"{API}/fixed-assets/{a1['id']}", headers=h, timeout=30).json()
        check("D1: accumulated == 2jt", abs(a1x.get("accumulated_depreciation", 0) - 2_000_000) < 1, str(a1x.get("accumulated_depreciation")))
        check("D2: book_value == 10jt", abs(a1x.get("book_value", 0) - 10_000_000) < 1, str(a1x.get("book_value")))
        check("D3: subledger accumulated == Σ entri", abs(sum(e["amount"] for e in a1x.get("depreciation_entries", [])) - a1x.get("accumulated_depreciation", 0)) < 1, str(a1x.get("depreciation_entries")))

        # E) Disposal GAIN: proceeds 11,5jt vs book 10jt → gain 1,5jt
        dr = dispose(h, a1["id"], 11_500_000)
        check("E1: dispose → 200", dr.status_code == 200, dr.text[:160])
        dj = dr.json().get("disposal", {})
        check("E2: result == gain", dj.get("result") == "gain", str(dj))
        check("E3: gain_loss == +1,5jt", abs(dj.get("gain_loss", 0) - 1_500_000) < 1, str(dj))
        dje = je_by_source("fixed_asset_disposal", a1["id"])
        check("E4: JE disposal seimbang", je_balanced(dje), str(dje))
        check("E5: Cr Laba Pelepasan 4-9100=1,5jt", line_amt(dje, "4-9100", "credit") == 1_500_000, str(dje and dje.get("lines")))
        check("E6: Dr Akumulasi 1-2900=2jt (hapus)", line_amt(dje, "1-2900", "debit") == 2_000_000, "")
        check("E7: Cr Aset 1-2100=12jt (hapus)", line_amt(dje, "1-2100", "credit") == 12_000_000, "")
        check("E8: Dr Kas/Bank 1-1100=11,5jt (proceeds)", line_amt(dje, "1-1100", "debit") == 11_500_000, "")

        # F) Disposal LOSS: asset 2 cost 6jt life 12 → monthly 500rb; 1 periode; proceeds 4jt vs book 5,5jt → loss 1,5jt
        a2 = create_asset(h, "Laptop Kantor", 6_000_000, 12, category="Inventaris & Perabot Kantor")
        created.append(a2["id"])
        run_dep(h, "2026-07", a2["id"])
        dr2 = dispose(h, a2["id"], 4_000_000)
        check("F1: dispose asset2 → 200", dr2.status_code == 200, dr2.text[:160])
        dj2 = dr2.json().get("disposal", {})
        check("F2: result == loss", dj2.get("result") == "loss", str(dj2))
        check("F3: gain_loss == -1,5jt", abs(dj2.get("gain_loss", 0) + 1_500_000) < 1, str(dj2))
        dje2 = je_by_source("fixed_asset_disposal", a2["id"])
        check("F4: JE disposal2 seimbang", je_balanced(dje2), str(dje2))
        check("F5: Dr Rugi Pelepasan 6-9500=1,5jt", line_amt(dje2, "6-9500", "debit") == 1_500_000, str(dje2 and dje2.get("lines")))

        # G) Asset2 dipakai kategori Inventaris → akun aset 1-2300
        check("G: aset2 akun 1-2300", a2.get("gl_account_asset") == "1-2300", str(a2.get("gl_account_asset")))

        # H) Trial balance global tetap seimbang
        jes = list(DBS.journal_entries.find({"status": {"$ne": "void"}}, {"_id": 0}))
        td = round(sum(float(l.get("debit", 0) or 0) for je in jes for l in je.get("lines", [])), 2)
        tc = round(sum(float(l.get("credit", 0) or 0) for je in jes for l in je.get("lines", [])), 2)
        check("H: trial balance seimbang (Σdebit==Σkredit)", abs(td - tc) < 0.5, f"debit={td} credit={tc}")

    finally:
        # Cleanup — hapus semua data POC (aset + entri + JE terkait) → pristine.
        for aid in created:
            DBS.journal_entries.delete_many({"source_id": {"$regex": f"^{re.escape(aid)}"},
                                             "source_type": {"$in": ["fixed_asset_acquisition",
                                                                      "fixed_asset_depreciation",
                                                                      "fixed_asset_disposal"]}})
            DBS.fin_depreciation_entries.delete_many({"asset_id": aid})
            DBS.fin_fixed_assets.delete_many({"id": aid})
        print(f"  \U0001f9f9 cleanup: {len(created)} aset + JE/entri terkait dihapus")

    print(f"\n=== HASIL R6.2: PASS={PASS} FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
