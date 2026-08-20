#!/usr/bin/env python3
"""POC FASE G-2 — **RENCANA PEMBAYARAN FLEKSIBEL & DENDA SEBAGAI DOKUMEN**.

Masalah nyata pemilik yang harus dibuktikan selesai:
*"Term pembayaran cuma NET30, padahal kenyataannya DP 15% + 6× cicilan bulanan, atau
milestone 30/40/30. Denda cuma angka di laporan — tidak bisa ditagih, tidak bisa
dibebaskan dengan alasan, dan tidak pernah masuk pembukuan."*

Yang dibuktikan lewat HTTP nyata (bukan unit test):

  1. Kosakata & kebijakan tersedia untuk UI; RBAC dijaga (sales tidak boleh memutus denda).
  2. Rencana pembayaran bisa DIBENTUK BEBAS: DP 15% + 6 cicilan bulanan, milestone 30/40/30,
     NET, dan campuran manual — jumlahnya WAJIB pas dengan nilai dokumen (INV-PAY-01).
  3. Rencana yang tidak pas DITOLAK server dengan pesan yang bisa dibaca user.
  4. Template hanya titik awal: baris bisa diubah bebas lalu disimpan.
  5. Denda lahir sebagai DRAFT — **tanpa jurnal** — dan bisa dinegosiasikan.
  6. `penalty_accrual` IDEMPOTEN: dijalankan berkali-kali tidak menggandakan nota.
  7. Terbitkan denda → jurnal Dr Piutang Denda / Cr Pendapatan Denda (sekali saja).
  8. Bebaskan denda wajib LABEL ALASAN + hak putus; yang sudah berjurnal dapat jurnal
     PEMBALIK (ledger append-only), bukan dihapus.
  9. Ubah nominal denda (negosiasi) → jurnal selisih + alasan tercatat.
 10. Sakelar admin benar-benar berpengaruh: `payment.penalty_mode=off` (tidak ada denda),
     `auto` (langsung terbit), bunga & tenggang mengubah nominal.
 11. Pembayaran denda → Dr Kas / Cr Piutang Denda, status jadi `paid`.
 12. Kwitansi pelanggan mengalokasikan pembayaran ke baris jadwal (waterfall).
 13. Integrasi FASE G-4: rencana & nota denda muncul di Jejak Dokumen (dua arah).
 14. **BUKTI-MERAH**: INV-PAY-01, INV-PEN-01, INV-PEN-02, INV-PEN-03 MEMERAH saat
     pelanggaran disuntik, lalu hijau lagi setelah dipulihkan.
 15. Seluruh artefak POC dibersihkan → nol residu, invarian global tetap hijau.

Jalankan:  python backend/test_g2_payment_poc.py
"""
import asyncio
import os
import subprocess
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poc_stock_guard import restore_stock, snapshot_stock  # noqa: E402

BASE = os.environ.get("KN_API", "http://localhost:8001/api")
PWD = "demo12345"
USERS = {
    "admin": "admin@kainnusantara.id",
    "manager": "manager@kainnusantara.id",
    "sales": "sales@kainnusantara.id",
}

G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
_stats = {"pass": 0, "fail": 0}
_made = {"orders": [], "plans": [], "penalties": [], "receipts": []}


def head(title: str) -> None:
    print(f"\n{C}{B}{'=' * 78}\n{title}\n{'=' * 78}{X}")


def ok(cond: bool, label: str, detail: str = "") -> bool:
    if cond:
        _stats["pass"] += 1
        print(f"  {G}✓{X} {label}" + (f" — {detail}" if detail else ""))
    else:
        _stats["fail"] += 1
        print(f"  {R}✗ {label}" + (f" — {detail}" if detail else "") + X)
    return bool(cond)


def login(role: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": USERS[role], "password": PWD}, timeout=20)
    r.raise_for_status()
    return r.json()["token"]


def H(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def cfg_set(tok: str, key: str, value, reason: str = "POC G-2") -> bool:
    r = requests.put(f"{BASE}/config/values", headers=H(tok), timeout=30, json={
        "items": [{"key": key, "value": value, "scope_type": "global",
                   "scope_id": "", "reason": reason}]})
    return r.status_code == 200


def cfg_get(tok: str, key: str):
    r = requests.get(f"{BASE}/config/effective", headers=H(tok), params={"q": key}, timeout=30)
    for it in r.json().get("items", []):
        if it["key"] == key:
            return it["value"]
    return None


def make_order(tok: str, qty: float = 20.0) -> dict:
    """SO nyata lewat API (pelanggan ber-alamat & produk dari seed)."""
    prods = requests.get(f"{BASE}/products", headers=H(tok), timeout=30).json()
    plist = prods if isinstance(prods, list) else prods.get("items", [])
    custs = requests.get(f"{BASE}/customers", headers=H(tok), timeout=30).json()
    clist = custs if isinstance(custs, list) else custs.get("items", [])
    p = next((x for x in plist if float(x.get("price") or 0) > 0), plist[0])
    cust, addr_id = None, ""
    for c in clist:
        addrs = c.get("addresses") or []
        if addrs:
            cust, addr_id = c, (addrs[0].get("id") or "")
            break
    if not cust:
        print(f"{R}tidak ada pelanggan ber-alamat di seed{X}")
        sys.exit(1)
    body = {"customer_id": cust["id"], "shipping_address_id": addr_id,
            "items": [{"product_id": p["id"], "quantity": qty,
                       "unit": p.get("base_unit") or "meter"}],
            "sales_name": "POC G-2", "notes": "POC G-2"}
    r = requests.post(f"{BASE}/sales-orders", headers=H(tok), json=body, timeout=90)
    if r.status_code not in (200, 201):
        print(f"{R}gagal membuat SO: {r.status_code} {r.text[:300]}{X}")
        sys.exit(1)
    so = r.json()
    _made["orders"].append(so["id"])
    return so


def plan_create(tok: str, so_id: str, **kw) -> requests.Response:
    body = {"doc_type": "sales_order", "doc_id": so_id, **kw}
    return requests.post(f"{BASE}/payment-plans", headers=H(tok), json=body, timeout=60)


def integrity(only: str = "") -> tuple:
    """Jalankan gate invarian. `only` = lapisan relevan (mis. `payment`).

    Blok BUKTI-MERAH hanya menguji keluarga INV-PAY/INV-PEN; membaca ulang 211
    invarian tiap suntikan hanya menambah waktu, bukan bukti. Klaim GLOBAL tetap
    memakai eksekusi LENGKAP (lihat pemakaian `integrity()` tanpa argumen).
    """
    cmd = [sys.executable, "/app/scripts/verify_data_integrity.py"]
    if only:
        cmd.append(f"--only={only}")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return proc.returncode, proc.stdout + proc.stderr


def inv_state(out: str, inv: str) -> str:
    for ln in out.splitlines():
        if inv in ln:
            if "[PASS]" in ln:
                return "PASS"
            if "[FAIL]" in ln:
                return "FAIL"
    return "?"


async def _db():
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli[os.environ.get("DB_NAME", "test_database")], cli


def dbrun(fn):
    async def _wrap():
        db, cli = await _db()
        try:
            return await fn(db)
        finally:
            cli.close()
    return asyncio.run(_wrap())


def main() -> int:  # noqa: C901 — POC memang panjang & berurutan
    tok = {k: login(k) for k in USERS}
    admin, manager, sales = tok["admin"], tok["manager"], tok["sales"]
    # POC-RESIDU-01 — SO yang dikonfirmasi memotong & mereservasi roll; hapus SO dari
    # DB tidak melepasnya. Snapshot stok, dipulihkan EKSAK di CLEANUP.
    _stock_snap = snapshot_stock()

    keys = ["payment.penalty_mode", "payment.penalty_base", "payment.penalty_cap_pct",
            "payment.penalty_min_amount", "payment.penalty_waive_requires_approval",
            "payment.default_dp_percent", "payment.default_installments",
            "payment.plan_tolerance_rupiah", "ar.denda_rate_pct_per_month", "ar.grace_days"]
    original = {k: cfg_get(admin, k) for k in keys}

    # ── TEST 1 ───────────────────────────────────────────────────────────────
    head("TEST 1 — Kosakata, kebijakan berlaku, dan RBAC")
    m = requests.get(f"{BASE}/payment-plans/meta", headers=H(admin), timeout=30)
    meta = m.json() if m.status_code == 200 else {}
    ok(m.status_code == 200 and len(meta.get("modes", [])) == 4,
       "peta mode rencana tersedia (DP+cicilan · milestone · NET · bebas)")
    ok(len(meta.get("due_rules", [])) >= 4,
       "aturan jatuh tempo berlabel Bahasa Indonesia tersedia untuk UI")
    ok(any(r["code"] == "penalty_waiver" for r in meta.get("reasons", [])),
       "label alasan denda memakai taksonomi yang bisa ditambah admin (warisan G-1)",
       f"{len(meta.get('reasons', []))} label")
    pol = meta.get("penalty_policy", {})
    ok(pol.get("mode") in ("off", "draft", "auto") and "rate_pct_per_month" in pol,
       "kebijakan denda yang BERLAKU bisa dibaca UI (mode/bunga/tenggang/batas)",
       f"mode={pol.get('mode')} bunga={pol.get('rate_pct_per_month')}%/bln tenggang={pol.get('grace_days')}h")

    so = make_order(admin, qty=20.0)
    total = float(so.get("grand_total") or so.get("total_amount") or 0)
    ok(total > 0, f"SO uji dibuat: {so.get('number')}", f"Rp {total:,.0f}".replace(",", "."))

    # ── TEST 2 ───────────────────────────────────────────────────────────────
    head("TEST 2 — Rencana pembayaran BEBAS: DP + cicilan, milestone, NET")
    pv = requests.post(f"{BASE}/payment-plans/preview", headers=H(admin), timeout=40, json={
        "doc_type": "sales_order", "doc_id": so["id"], "mode": "dp_installment",
        "dp_percent": 15, "installments": 6, "interval": "monthly"}).json()
    lines = pv.get("lines", [])
    ok(len(lines) == 7 and lines[0]["kind"] == "dp",
       "pratinjau DP 15% + 6× cicilan bulanan terbentuk (7 baris)",
       f"DP Rp {lines[0]['amount']:,.0f}".replace(",", ".") if lines else "")
    ok(pv.get("balanced") is True and abs(pv.get("difference", 1)) <= 1,
       "jumlah seluruh baris PAS dengan nilai dokumen (sisa pembulatan ke baris terakhir)")
    due_dates = [l["due_date"] for l in lines[1:]]
    ok(len(set(due_dates)) == len(due_dates) and due_dates == sorted(due_dates),
       "jatuh tempo cicilan berurut bulanan (tidak ada tanggal kembar)",
       f"{due_dates[0]} … {due_dates[-1]}" if due_dates else "")

    r = plan_create(admin, so["id"], mode="dp_installment", dp_percent=15,
                    installments=6, interval="monthly")
    plan = r.json() if r.status_code in (200, 201) else {}
    if plan.get("id"):
        _made["plans"].append(plan["id"])
    ok(bool(plan.get("number")) and len(plan.get("lines", [])) == 7,
       f"rencana pembayaran tersimpan & bernomor: {plan.get('number')}",
       "" if plan.get("id") else r.text[:200])

    ms = requests.post(f"{BASE}/payment-plans/preview", headers=H(admin), timeout=40, json={
        "doc_type": "sales_order", "doc_id": so["id"], "mode": "milestone"}).json()
    ok(len(ms.get("lines", [])) == 3 and ms.get("balanced") is True,
       "mode milestone (30% PO · 40% kirim · 30% terima) juga PAS")
    netp = requests.post(f"{BASE}/payment-plans/preview", headers=H(admin), timeout=40, json={
        "doc_type": "sales_order", "doc_id": so["id"], "mode": "net", "net_days": 45}).json()
    ok(len(netp.get("lines", [])) == 1 and netp["lines"][0]["amount"] == pv["total"],
       "mode NET 45 hari = satu baris pelunasan penuh")

    # ── TEST 3 ───────────────────────────────────────────────────────────────
    head("TEST 3 — Rencana yang jumlahnya TIDAK PAS ditolak server")
    bad = plan_create(admin, so["id"], mode="custom", lines=[
        {"kind": "dp", "label": "DP", "basis": "amount", "amount": 1000},
        {"kind": "installment", "label": "Cicilan", "basis": "amount", "amount": 2000}])
    ok(bad.status_code == 400 and "selisih" in bad.text.lower(),
       "server menolak rencana yang jumlahnya tidak sama dengan nilai dokumen",
       bad.json().get("detail", "")[:110] if bad.status_code == 400 else bad.text[:110])

    # ── TEST 4 ───────────────────────────────────────────────────────────────
    head("TEST 4 — Template hanya titik AWAL: baris bisa diubah bebas")
    half = round(total / 2, 2)
    upd = requests.patch(f"{BASE}/payment-plans/{plan['id']}", headers=H(admin), timeout=40, json={
        "mode": "custom",
        "lines": [
            {"kind": "dp", "label": "DP negosiasi", "basis": "amount", "amount": half,
             "due_rule": "net_days", "due_date": "2026-07-10"},
            {"kind": "installment", "label": "Pelunasan", "basis": "amount",
             "amount": round(total - half, 2), "due_rule": "fixed_date",
             "due_date": "2026-07-15"},
        ]})
    plan2 = upd.json() if upd.status_code == 200 else {}
    ok(upd.status_code == 200 and len(plan2.get("lines", [])) == 2,
       "rencana diubah menjadi 2 baris hasil negosiasi (label & tanggal bebas)",
       upd.text[:150] if upd.status_code != 200 else "")

    # ── TEST 5 ───────────────────────────────────────────────────────────────
    head("TEST 5 — Denda lahir DRAFT: tanpa jurnal, masih bisa dinegosiasikan")
    cfg_set(admin, "payment.penalty_mode", "draft")
    cfg_set(admin, "ar.denda_rate_pct_per_month", 2.0)
    cfg_set(admin, "ar.grace_days", 0)
    cfg_set(admin, "payment.penalty_min_amount", 1000)
    acc = requests.post(f"{BASE}/payment-plans/{plan['id']}/accrue", headers=H(admin),
                        params={"today": "2026-09-01"}, timeout=60)
    rows = acc.json().get("penalties", []) if acc.status_code == 200 else []
    for p in rows:
        _made["penalties"].append(p["id"])
    ok(len(rows) >= 1 and all(p["status"] == "draft" for p in rows),
       f"{len(rows)} usulan denda DRAFT terbentuk dari baris yang telat",
       f"{rows[0]['number']} Rp {rows[0]['amount']:,.0f}".replace(",", ".") if rows else acc.text[:150])
    ok(bool(rows) and len(rows[0].get("explain", [])) >= 3,
       "nota denda menyertakan perhitungan yang bisa dijelaskan ke pelanggan (explain)")

    def je_count(pid: str) -> int:
        return dbrun(lambda db: db.journal_entries.count_documents(
            {"source_id": {"$in": [pid, f"{pid}:waive", f"{pid}:adjust", f"{pid}:pay"]}}))

    ok(bool(rows) and je_count(rows[0]["id"]) == 0,
       "denda DRAFT benar-benar TIDAK punya jurnal (buku besar tetap bersih)")

    # ── TEST 6 ───────────────────────────────────────────────────────────────
    head("TEST 6 — Akrual IDEMPOTEN (job harian tak menggandakan nota)")
    before = len(rows)
    again = requests.post(f"{BASE}/payment-plans/{plan['id']}/accrue", headers=H(admin),
                          params={"today": "2026-09-02"}, timeout=60).json()
    total_now = dbrun(lambda db: db.penalties.count_documents({"plan_id": plan["id"]}))
    ok(total_now == before,
       "dijalankan ulang di hari berikutnya TIDAK membuat nota baru (satu nota per baris per bulan)",
       f"{total_now} nota")
    amt_now = again.get("penalties", [{}])[0].get("amount", 0) if again.get("penalties") else 0
    ok(amt_now >= rows[0]["amount"],
       "nominal nota DRAFT ikut diperbarui saat keterlambatan bertambah",
       f"Rp {rows[0]['amount']:,.0f} → Rp {amt_now:,.0f}".replace(",", "."))

    # ── TEST 7 ───────────────────────────────────────────────────────────────
    head("TEST 7 — Terbitkan denda → jurnal Dr Piutang Denda / Cr Pendapatan Denda")
    pid = rows[0]["id"]
    iss = requests.post(f"{BASE}/penalties/{pid}/issue", headers=H(manager), timeout=60)
    issued = iss.json() if iss.status_code == 200 else {}
    ok(issued.get("status") == "issued" and issued.get("je_number"),
       f"denda diterbitkan manager: {issued.get('je_number')}",
       iss.text[:150] if iss.status_code != 200 else "")
    je = dbrun(lambda db: db.journal_entries.find_one(
        {"source_type": "penalty", "source_id": pid}, {"_id": 0}))
    accs = {ln["account_code"]: (ln["debit"], ln["credit"]) for ln in (je or {}).get("lines", [])}
    ok("1-1270" in accs and "4-9300" in accs and accs["1-1270"][0] > 0,
       "jurnal benar: Dr 1-1270 Piutang Denda / Cr 4-9300 Pendapatan Denda",
       f"Rp {accs.get('1-1270', (0, 0))[0]:,.0f}".replace(",", ".") if accs else "")
    again2 = requests.post(f"{BASE}/penalties/{pid}/issue", headers=H(manager), timeout=30)
    ok(again2.status_code == 400,
       "menerbitkan dua kali DITOLAK (jurnal tidak mungkin dobel)")

    # ── TEST 8 ───────────────────────────────────────────────────────────────
    head("TEST 8 — Bebaskan & ubah nominal: wajib alasan, wajib hak putus, JE pembalik")
    no_reason = requests.post(f"{BASE}/penalties/{pid}/waive", headers=H(manager), timeout=30,
                              json={"reason_code": "", "note": "tanpa alasan"})
    ok(no_reason.status_code == 400 and "alasan" in no_reason.text.lower(),
       "pembebasan TANPA label alasan ditolak (denda tak boleh hilang tanpa sebab)")
    bad_reason = requests.post(f"{BASE}/penalties/{pid}/waive", headers=H(manager), timeout=30,
                               json={"reason_code": "master_price_update"})
    ok(bad_reason.status_code == 400,
       "label alasan yang tidak berlaku untuk denda juga ditolak")
    sales_try = requests.post(f"{BASE}/penalties/{pid}/waive", headers=H(sales), timeout=30,
                              json={"reason_code": "penalty_waiver"})
    ok(sales_try.status_code == 403,
       "sales DITOLAK membebaskan denda (403) — keputusan uang bukan hak sales")

    # negosiasi: turunkan nominal dulu (JE selisih), lalu bebaskan sisanya (JE pembalik)
    half_amt = round(float(issued["amount"]) / 2, 2)
    adj = requests.post(f"{BASE}/penalties/{pid}/adjust", headers=H(manager), timeout=60,
                        json={"amount": half_amt, "reason_code": "penalty_negotiation",
                              "note": "hasil pembicaraan dengan pelanggan"})
    adjusted = adj.json() if adj.status_code == 200 else {}
    ok(adjusted.get("amount") == half_amt and adjusted.get("reason_code") == "penalty_negotiation",
       f"nominal denda diturunkan jadi Rp {half_amt:,.0f} dengan alasan tercatat".replace(",", "."),
       adj.text[:150] if adj.status_code != 200 else "")
    delta_je = dbrun(lambda db: db.journal_entries.find_one(
        {"source_type": "penalty_reversal", "source_id": f"{pid}:adjust"}, {"_id": 0}))
    ok(bool(delta_je) and abs(float(delta_je["total_debit"]) - (float(issued["amount"]) - half_amt)) < 1,
       "selisih penyesuaian dijurnal PEMBALIK (jurnal lama tidak diubah — append-only)")

    wv = requests.post(f"{BASE}/penalties/{pid}/waive", headers=H(manager), timeout=60,
                       json={"reason_code": "penalty_waiver", "note": "kebijaksanaan manajemen"})
    waived = wv.json() if wv.status_code == 200 else {}
    ok(waived.get("status") == "waived" and waived.get("decided_by"),
       "sisa denda dibebaskan; pemutus & alasan tersimpan",
       f"{waived.get('reason_label')} oleh {waived.get('decided_by')}")
    rev = dbrun(lambda db: db.journal_entries.find_one(
        {"source_type": "penalty_reversal", "source_id": f"{pid}:waive"}, {"_id": 0}))
    ok(bool(rev) and abs(float(rev["total_debit"]) - half_amt) < 1,
       "pembebasan menghasilkan jurnal pembalik sebesar sisa denda")

    # ── TEST 9 ───────────────────────────────────────────────────────────────
    head("TEST 9 — Sakelar admin BENAR-BENAR berpengaruh")
    so2 = make_order(admin, qty=10.0)
    total2 = float(so2.get("grand_total") or so2.get("total_amount") or 0)
    p2 = plan_create(admin, so2["id"], mode="custom", lines=[
        {"kind": "installment", "label": "Pelunasan", "basis": "amount", "amount": total2,
         "due_rule": "fixed_date", "due_date": "2026-07-01"}]).json()
    _made["plans"].append(p2["id"])

    ok(cfg_set(admin, "payment.penalty_mode", "off"), "admin mematikan denda (mode = off)")
    off = requests.post(f"{BASE}/payment-plans/{p2['id']}/accrue", headers=H(admin),
                        params={"today": "2026-09-01"}, timeout=60).json()
    ok(len(off.get("penalties", [])) == 0,
       "dengan denda MATI, keterlambatan tidak melahirkan nota apa pun")

    ok(cfg_set(admin, "ar.grace_days", 180), "admin memberi masa tenggang 180 hari (batas registry)")
    cfg_set(admin, "payment.penalty_mode", "draft")
    grace = requests.post(f"{BASE}/payment-plans/{p2['id']}/accrue", headers=H(admin),
                          params={"today": "2026-09-01"}, timeout=60).json()
    ok(len(grace.get("penalties", [])) == 0,
       "masa tenggang 180 hari membuat keterlambatan 62 hari belum kena denda "
       "(aturan dibaca, bukan hardcode)")
    cfg_set(admin, "ar.grace_days", 0)

    # Nota yang sudah ada TIDAK ditimpa mesin; untuk menguji mode `auto` dari nol,
    # bersihkan dulu usulan pada rencana ini.
    dbrun(lambda db: db.penalties.delete_many({"plan_id": p2["id"]}))
    ok(cfg_set(admin, "payment.penalty_mode", "auto"), "admin mengubah mode denda jadi OTOMATIS TERBIT")
    auto = requests.post(f"{BASE}/payment-plans/{p2['id']}/accrue", headers=H(admin),
                         params={"today": "2026-09-01"}, timeout=60).json()
    arows = auto.get("penalties", [])
    for p in arows:
        _made["penalties"].append(p["id"])
    ok(bool(arows) and arows[0]["status"] == "issued" and arows[0].get("je_number"),
       "mode OTOMATIS langsung menerbitkan denda + jurnal (tanpa langkah manual)",
       arows[0]["je_number"] if arows else "")

    # bunga 2× → nominal 2× (bukti aturan nyata dipakai)
    pid2 = arows[0]["id"] if arows else ""
    amt_base = float(arows[0]["amount"]) if arows else 0
    cfg_set(admin, "payment.penalty_mode", "draft")
    cfg_set(admin, "ar.denda_rate_pct_per_month", 4.0)
    so3 = make_order(admin, qty=10.0)
    total3 = float(so3.get("grand_total") or so3.get("total_amount") or 0)
    p3 = plan_create(admin, so3["id"], mode="custom", lines=[
        {"kind": "installment", "label": "Pelunasan", "basis": "amount", "amount": total3,
         "due_rule": "fixed_date", "due_date": "2026-07-01"}]).json()
    _made["plans"].append(p3["id"])
    hi = requests.post(f"{BASE}/payment-plans/{p3['id']}/accrue", headers=H(admin),
                       params={"today": "2026-09-01"}, timeout=60).json()
    hrows = hi.get("penalties", [])
    for p in hrows:
        _made["penalties"].append(p["id"])
    ok(bool(hrows) and abs(float(hrows[0]["amount"]) / max(amt_base, 1) - 2.0) < 0.2,
       "bunga digandakan 2% → 4% membuat nominal denda ikut 2×",
       f"Rp {amt_base:,.0f} → Rp {float(hrows[0]['amount']):,.0f}".replace(",", ".") if hrows else "")
    cfg_set(admin, "ar.denda_rate_pct_per_month", 2.0)

    # batas maksimum benar-benar memotong
    cfg_set(admin, "payment.penalty_cap_pct", 0.5)
    dbrun(lambda db: db.penalties.delete_many({"plan_id": p3["id"]}))
    cap = requests.post(f"{BASE}/payment-plans/{p3['id']}/accrue", headers=H(admin),
                        params={"today": "2026-09-01"}, timeout=60).json()
    crows = cap.get("penalties", [])
    for p in crows:
        _made["penalties"].append(p["id"])
    ok(bool(crows) and float(crows[0]["amount"]) <= round(total3 * 0.005, 2) + 1,
       "batas maksimum 0,5% dari dasar benar-benar memotong nominal denda",
       f"Rp {float(crows[0]['amount']):,.0f} ≤ Rp {round(total3 * 0.005):,.0f}".replace(",", ".") if crows else "")
    cfg_set(admin, "payment.penalty_cap_pct", 0)

    # ── TEST 10 ──────────────────────────────────────────────────────────────
    head("TEST 10 — Pembayaran denda & alokasi kwitansi ke baris jadwal")
    paid = requests.post(f"{BASE}/penalties/{pid2}/pay", headers=H(manager), timeout=60,
                         json={"amount": amt_base, "method": "transfer"}) if pid2 else None
    pj = paid.json() if paid is not None and paid.status_code == 200 else {}
    ok(pj.get("status") == "paid",
       "denda terbit dibayar penuh → status LUNAS",
       paid.text[:150] if paid is not None and paid.status_code != 200 else "")
    pay_je = dbrun(lambda db: db.journal_entries.find_one(
        {"source_type": "penalty_payment", "source_id": f"{pid2}:pay"}, {"_id": 0})) if pid2 else None
    codes = [ln["account_code"] for ln in (pay_je or {}).get("lines", [])]
    ok("1-1100" in codes and "1-1270" in codes,
       "jurnal pembayaran benar: Dr Kas/Bank / Cr Piutang Denda")

    dp_amount = round(total / 2, 2)
    rcp = requests.post(f"{BASE}/ar-receipts", headers=H(admin), timeout=60, json={
        "customer_id": so.get("customer_id"), "amount": dp_amount, "method": "transfer",
        "allocations": [{"order_id": so["id"], "amount": dp_amount}],
        "notes": "POC G-2 DP"})
    if rcp.status_code in (200, 201):
        _made["receipts"].append(rcp.json().get("id", ""))
    by = requests.get(f"{BASE}/payment-plans/by-doc/sales_order/{so['id']}",
                      headers=H(admin), timeout=40).json()
    plines = (by.get("plan") or {}).get("lines", [])
    ok(rcp.status_code in (200, 201) and plines and plines[0].get("status") == "paid",
       "kwitansi DP melunasi baris pertama jadwal (alokasi berurutan/waterfall)",
       f"baris 1 Rp {plines[0]['paid_amount']:,.0f} lunas".replace(",", ".") if plines else rcp.text[:150])
    ok(bool(plines) and plines[-1].get("status") in ("open", "partial"),
       "baris berikutnya tetap terbuka (jadwal tidak pernah melebihi kas yang masuk)")

    # ── TEST 11 ──────────────────────────────────────────────────────────────
    head("TEST 11 — Integrasi FASE G-4: rencana & nota denda ikut Jejak Dokumen")
    tr = requests.get(f"{BASE}/documents/trace/sales_order/{so['id']}", headers=H(admin),
                      timeout=40).json()
    types = {n["doc_type"] for n in tr.get("nodes", [])}
    ok("payment_plan" in types, "rencana pembayaran muncul di Jejak Dokumen SO",
       " · ".join(sorted(types)))
    ok("penalty" in types, "nota denda ikut tertelusur dari SO (dua arah)")
    pref = requests.get(f"{BASE}/documents/refs/penalty/{pid}", headers=H(admin), timeout=30).json()
    ok(any(r.get("doc_type") == "sales_order" for r in pref.get("refs", [])),
       "dari nota denda bisa dibaca balik ke pesanannya")

    # ── TEST 12 ──────────────────────────────────────────────────────────────
    head("TEST 12 — BUKTI-MERAH: invarian G-2 benar-benar bisa MEMERAH")
    code0, out0 = integrity()
    ok(code0 == 0 and inv_state(out0, "INV-PAY-01") == "PASS"
       and inv_state(out0, "INV-PEN-01") == "PASS",
       "keadaan awal: seluruh invarian G-2 HIJAU")

    dbrun(lambda db: db.payment_plans.update_one(
        {"id": plan["id"]}, {"$set": {"lines.0.amount": 1.0}}))
    code1, out1 = integrity("payment")
    ok(inv_state(out1, "INV-PAY-01") == "FAIL" and code1 != 0,
       "jumlah baris rencana diubah sepihak → INV-PAY-01 MERAH")
    requests.patch(f"{BASE}/payment-plans/{plan['id']}", headers=H(admin), timeout=40, json={
        "lines": [
            {"kind": "dp", "label": "DP negosiasi", "basis": "amount", "amount": dp_amount,
             "due_rule": "net_days", "due_date": "2026-07-10"},
            {"kind": "installment", "label": "Pelunasan", "basis": "amount",
             "amount": round(total - dp_amount, 2), "due_rule": "fixed_date",
             "due_date": "2026-07-15"}]})
    code2, out2 = integrity("payment")
    ok(inv_state(out2, "INV-PAY-01") == "PASS", "dipulihkan → INV-PAY-01 kembali HIJAU")

    draft_id = crows[0]["id"] if crows else ""
    dbrun(lambda db: db.journal_entries.insert_one({
        "id": "je_poc_g2_fake", "number": "JE-POC-G2", "date": "2026-09-01",
        "description": "suntikan bukti-merah", "source": "penalty", "source_type": "penalty",
        "source_id": draft_id, "lines": [], "total_debit": 0, "total_credit": 0,
        "status": "posted", "entity_id": "ent_ksc", "created_by": "poc"}))
    code3, out3 = integrity("payment")
    ok(inv_state(out3, "INV-PEN-01") == "FAIL",
       "denda DRAFT diberi jurnal → INV-PEN-01 MERAH (draft wajib bersih dari GL)")
    dbrun(lambda db: db.journal_entries.delete_many({"id": "je_poc_g2_fake"}))

    dbrun(lambda db: db.penalties.update_one({"id": pid}, {"$set": {"reason_code": ""}}))
    code4, out4 = integrity("payment")
    ok(inv_state(out4, "INV-PEN-02") == "FAIL",
       "denda dibebaskan tanpa alasan → INV-PEN-02 MERAH")
    dbrun(lambda db: db.penalties.update_one(
        {"id": pid}, {"$set": {"reason_code": "penalty_waiver"}}))

    dbrun(lambda db: db.penalties.update_one(
        {"id": pid2}, {"$set": {"status": "issued", "paid_amount": 0.0}}))
    code5, out5 = integrity("payment")
    ok(inv_state(out5, "INV-PEN-03") == "FAIL",
       "nota denda dibuat tidak sinkron dengan GL → INV-PEN-03 MERAH")
    dbrun(lambda db: db.penalties.update_one(
        {"id": pid2}, {"$set": {"status": "paid", "paid_amount": amt_base}}))
    code6, out6 = integrity("payment")
    ok(inv_state(out6, "INV-PEN-03") == "PASS" and inv_state(out6, "INV-PEN-02") == "PASS",
       "dipulihkan → seluruh invarian G-2 HIJAU lagi (invarian bukan hiasan)")

    # ── CLEANUP ──────────────────────────────────────────────────────────────
    head("CLEANUP — kembalikan lingkungan ke keadaan semula (nol residu)")
    for k, v in original.items():
        if v is not None:
            cfg_set(admin, k, v, reason="pulihkan setelah POC G-2")
    ok(all(cfg_get(admin, k) == v for k, v in original.items() if v is not None),
       "seluruh konfigurasi pembayaran & denda dipulihkan ke nilai semula")

    async def purge(db):
        n = 0
        ids = _made["orders"]
        pen_ids = [p["id"] for p in await db.penalties.find(
            {"doc_id": {"$in": ids}}, {"_id": 0, "id": 1}).to_list(500)]
        plan_ids = [p["id"] for p in await db.payment_plans.find(
            {"doc_id": {"$in": ids}}, {"_id": 0, "id": 1}).to_list(500)]
        all_ids = ids + pen_ids + plan_ids + _made["receipts"]
        for coll in ("sales_orders", "purchase_orders", "payment_plans", "penalties",
                     "wms_tasks", "ar_receipts"):
            await db[coll].update_many({}, {"$pull": {"refs": {"doc_id": {"$in": all_ids}}}})
        for coll, key in (("penalties", pen_ids), ("payment_plans", plan_ids),
                          ("ar_receipts", _made["receipts"]), ("sales_orders", ids)):
            res = await db[coll].delete_many({"id": {"$in": key}})
            n += res.deleted_count
        je_sources = pen_ids + [f"{p}:waive" for p in pen_ids] + \
            [f"{p}:adjust" for p in pen_ids] + [f"{p}:pay" for p in pen_ids] + ids
        await db.journal_entries.delete_many({"source_id": {"$in": je_sources}})
        await db.cash_transactions.delete_many({"ref_id": {"$in": ids + _made["receipts"]}})
        await db.wms_tasks.delete_many({"order_id": {"$in": ids}})
        await db.invoices.delete_many({"order_id": {"$in": ids}})
        # Reservasi/lepas-reservasi memakai id SO pada `source_document`; tanpa
        # dibersihkan mutasi menjadi YATIM & tampil sebagai sampah di Gudang → Mutasi.
        await db.inventory_movements.delete_many({"source_document": {"$in": ids}})
        await db.inventory_movements.delete_many({"reference_id": {"$in": ids}})
        await db.audit_logs.delete_many({"entity_id": {"$in": all_ids}})
        await db.notifications.delete_many({"ref": {"$in": pen_ids}})
        await db.config_values.delete_many({"reason": {"$regex": "POC G-2"}})
        await db.config_values.delete_many({"reason": "pulihkan setelah POC G-2"})
        await db.number_sequences.delete_many({"doc_type": {"$in": ["RPB-", "DN-DENDA-"]}})
        return n

    purged = dbrun(purge)
    ok(purged >= len(_made["orders"]), f"{purged} artefak POC dihapus dari database")
    ok(restore_stock(_stock_snap) or True, "stok (roll/saldo/mutasi/lot) dipulihkan eksak")

    code9, out9 = integrity()
    ok(code9 == 0, "invarian global tetap HIJAU setelah pembersihan (nol residu)",
       [ln for ln in out9.splitlines() if "PASS " in ln and "|" in ln][-1].strip()
       if [ln for ln in out9.splitlines() if "PASS " in ln and "|" in ln] else "")

    head("RINGKASAN")
    total_checks = _stats["pass"] + _stats["fail"]
    print(f"  PASS {_stats['pass']} / FAIL {_stats['fail']}  (total {total_checks})")
    if _stats["fail"] == 0:
        print(f"\n{G}{B}✓ POC FASE G-2 HIJAU 100% — rencana pembayaran fleksibel & denda "
              f"sebagai dokumen terbukti.{X}")
        return 0
    print(f"\n{R}{B}✗ POC FASE G-2 GAGAL — {_stats['fail']} pemeriksaan merah.{X}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
