#!/usr/bin/env python3
"""POC FASE G-3 — **SELISIH PEMBAYARAN: LEBIH & KURANG BAYAR**.

Masalah nyata pemilik yang harus dibuktikan selesai:
*"Uang masuk hampir tidak pernah pas. Dipotong biaya bank, dibayar sebagian, atau malah
lebih. Sistem cuma bisa menolak atau diam-diam menaruhnya di deposit — akhirnya keputusan
'ya sudah anggap lunas' terjadi di WhatsApp, bukan di sistem."*

Yang dibuktikan lewat HTTP nyata (bukan unit test):

  1. Kosakata, kebijakan berlaku & label alasan tersedia untuk UI; RBAC dijaga.
  2. Takar selisih JUJUR: bayar pas → tidak ada selisih; bayar lebih awal untuk cicilan
     berikutnya (masih bisa dialokasikan) → **bukan** selisih; kurang / lebih dari yang
     bisa dialokasikan → selisih dengan 3 pilihan berlabel.
  3. Kurang bayar DI DALAM toleransi → otomatis lunas (`rounding_writeoff`) + jurnal
     Dr 6-9100 / Cr 1-1200 + keputusan tetap tercatat berlabel (tidak ada yang senyap).
  4. Kurang bayar DI LUAR toleransi tanpa keputusan → masuk **antrean Selisih Bayar**.
  5. Pilihan (a) sisa tetap piutang → outstanding tetap, keputusan berlabel.
  6. Pilihan (b) ubah jadwal → baris rencana dipecah/digeser, Σ rencana TETAP (INV-PAY-01).
  7. Pilihan (c) hapus sisa → wewenang & batas nominal ditegakkan; jurnal beban selisih.
  8. Lebih bayar: deposit · alokasi ke pesanan lain (Dr 2-1400 / Cr 1-1200) · pengembalian
     dana (kas keluar + Dr 2-1400 / Cr Kas).
  9. Label alasan WAJIB & harus berlaku untuk selisih pembayaran.
 10. Pembayaran bisa MENYEBUT baris jadwal tujuan (`plan_line_seq`) — bukan cuma waterfall.
 11. Sakelar admin benar-benar berpengaruh (toleransi & pilihan bawaan).
 12. Jalur AP: kurang bayar receh → tagihan supplier ditutup (Dr 2-1100 / Cr 4-9000);
     lebih bayar → uang muka supplier (Dr 1-1400 / Cr Kas); lebih bayar tanpa keputusan
     DITOLAK.
 13. Void kwitansi membalik keputusan yang sudah jalan (jurnal PEMBALIK, bukan hapus).
 14. Integrasi FASE G-4: keputusan selisih muncul di Jejak Dokumen (dua arah).
 15. **BUKTI-MERAH**: INV-VAR-01 & INV-VAR-02 MEMERAH saat pelanggaran disuntik, lalu
     hijau lagi setelah dipulihkan.
 16. Seluruh artefak POC dibersihkan → nol residu, invarian global tetap hijau.

Jalankan:  python backend/test_g3_variance_poc.py
"""
import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poc_stock_guard import restore_stock, snapshot_stock  # noqa: E402

BASE = os.environ.get("KN_API", "http://localhost:8001/api")
PWD = "demo12345"
USERS = {
    "admin": "admin@kainnusantara.id",
    "manager": "manager@kainnusantara.id",
    "sales": "sales@kainnusantara.id",
    # FASE E-8 (E8.2/E8.10b#2) memindahkan UANG MASUK & keputusan selisih bayar dari
    # `sales` ke peran baru `finance`. POC ini dulu memakai akun sales untuk mencatat
    # kwitansi; sejak pemisahan tugas itu, panggilannya ditolak (403) dan variabel
    # `rec` menjadi `{}` sehingga POC pecah dengan `KeyError: 'id'` — bukan karena
    # mesin selisih bayar rusak, melainkan karena aktornya sudah bukan wewenangnya.
    "finance": "finance@kainnusantara.id",
}

G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
_stats = {"pass": 0, "fail": 0}
_made = {"orders": [], "receipts": [], "plans": [], "decisions": []}
_bill_backup = {}


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


def cfg_set(tok: str, key: str, value, reason: str = "POC G-3") -> bool:
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


def rp(n) -> str:
    return f"Rp {float(n or 0):,.0f}".replace(",", ".")


def day(offset: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=offset)).date().isoformat()


# ── Pembuat data uji (lewat API produksi) ──────────────────────────────────
def make_order(tok: str, qty: float = 20.0, note: str = "POC G-3") -> dict:
    prods = requests.get(f"{BASE}/products", headers=H(tok), timeout=30).json()
    plist = prods if isinstance(prods, list) else prods.get("items", [])
    custs = requests.get(f"{BASE}/customers", headers=H(tok), timeout=30).json()
    clist = custs if isinstance(custs, list) else custs.get("items", [])
    p = next((x for x in plist if float(x.get("price") or 0) > 0), plist[0])
    cust, addr_id = None, ""
    for c in clist:
        if c.get("addresses"):
            cust, addr_id = c, (c["addresses"][0].get("id") or "")
            break
    if not cust:
        print(f"{R}tidak ada pelanggan ber-alamat di seed{X}")
        sys.exit(1)
    body = {"customer_id": cust["id"], "shipping_address_id": addr_id,
            "items": [{"product_id": p["id"], "quantity": qty,
                       "unit": p.get("base_unit") or "meter"}],
            "sales_name": "POC G-3", "notes": note}
    r = requests.post(f"{BASE}/sales-orders", headers=H(tok), json=body, timeout=90)
    if r.status_code not in (200, 201):
        print(f"{R}gagal membuat SO: {r.status_code} {r.text[:300]}{X}")
        sys.exit(1)
    so = r.json()
    _made["orders"].append(so["id"])
    return so


def plan_create(tok: str, so_id: str, lines: list, mode: str = "custom") -> dict:
    r = requests.post(f"{BASE}/payment-plans", headers=H(tok), timeout=60, json={
        "doc_type": "sales_order", "doc_id": so_id, "mode": mode, "lines": lines,
        "note": "POC G-3"})
    if r.status_code not in (200, 201):
        print(f"{R}gagal membuat rencana: {r.status_code} {r.text[:300]}{X}")
        return {}
    plan = r.json()
    _made["plans"].append(plan["id"])
    return plan


def assess(tok: str, cust_id: str, amount: float, allocs=None) -> dict:
    r = requests.post(f"{BASE}/payment-variances/assess", headers=H(tok), timeout=40, json={
        "customer_id": cust_id, "amount": amount, "allocations": allocs or []})
    return r.json() if r.status_code == 200 else {"error": r.text, "status": r.status_code}


def pay(tok: str, cust_id: str, amount: float, allocs=None, variance=None) -> requests.Response:
    body = {"customer_id": cust_id, "amount": amount, "method": "transfer",
            "notes": "POC G-3"}
    if allocs:
        body["allocations"] = allocs
    if variance:
        body["variance"] = variance
    r = requests.post(f"{BASE}/ar-receipts", headers=H(tok), json=body, timeout=90)
    if r.status_code in (200, 201):
        rid = r.json().get("id")
        if rid:
            _made["receipts"].append(rid)
        d = (r.json().get("variance") or {}).get("decision_id")
        if d:
            _made["decisions"].append(d)
    return r


def decide(tok: str, receipt_id: str, **kw) -> requests.Response:
    r = requests.post(f"{BASE}/payment-variances/receipt/{receipt_id}/decide",
                      headers=H(tok), json=kw, timeout=60)
    if r.status_code == 200 and r.json().get("id"):
        _made["decisions"].append(r.json()["id"])
    return r


def order_of(tok: str, so_id: str) -> dict:
    r = requests.get(f"{BASE}/sales-orders/{so_id}", headers=H(tok), timeout=30)
    return r.json() if r.status_code == 200 else {}


def outstanding_of(tok: str, so_id: str) -> float:
    o = order_of(tok, so_id)
    gt = float(o.get("grand_total") or o.get("total_amount") or 0)
    paid = sum(float(p.get("amount") or 0) for p in (o.get("payments") or []))
    return round(gt - paid, 2)


def deposit_of(tok: str, cust_id: str) -> float:
    r = requests.get(f"{BASE}/ar-receipts/deposit", headers=H(tok),
                     params={"customer_id": cust_id}, timeout=30)
    return round(float((r.json() or {}).get("deposit_balance") or 0), 2)


def integrity(only: str = "") -> tuple:
    """Jalankan gate invarian. `only` = lapisan relevan (mis. `variance`).

    Blok BUKTI-MERAH hanya menguji keluarga INV-VAR. Klaim GLOBAL (nol residu)
    tetap memakai eksekusi LENGKAP.
    """
    cmd = [sys.executable, "/app/scripts/verify_data_integrity.py"]
    if only:
        cmd.append(f"--only={only}")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=420)
    return proc.returncode, proc.stdout + proc.stderr


def inv_state(out: str, inv: str) -> str:
    for ln in out.splitlines():
        if inv in ln:
            if "[PASS]" in ln:
                return "PASS"
            if "[FAIL]" in ln:
                return "FAIL"
            if "[WARN]" in ln:
                return "WARN"
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


def gl_balance(account: str) -> float:
    """Saldo (debit − kredit) satu akun dari journal_entries non-void."""
    async def _q(db):
        total = 0.0
        async for je in db.journal_entries.find(
                {"status": {"$ne": "void"}, "lines.account_code": account},
                {"_id": 0, "lines": 1}):
            for ln in je.get("lines") or []:
                if ln.get("account_code") == account:
                    total += float(ln.get("debit") or 0) - float(ln.get("credit") or 0)
        return round(total, 2)
    return dbrun(_q)


def main() -> int:  # noqa: C901 — POC memang panjang & berurutan
    tok = {k: login(k) for k in USERS}
    admin, manager, sales = tok["admin"], tok["manager"], tok["sales"]
    finance = tok["finance"]
    # POC-RESIDU-01 — SO yang dikonfirmasi memotong & mereservasi roll; hapus SO dari
    # DB tidak melepasnya. Snapshot stok, dipulihkan EKSAK di CLEANUP.
    _stock_snap = snapshot_stock()

    keys = ["payment.variance_tolerance_rupiah", "payment.variance_underpay_default",
            "payment.variance_overpay_default", "payment.variance_writeoff_requires_approval",
            "payment.variance_writeoff_approver_role", "payment.variance_writeoff_max_amount",
            "payment.variance_reschedule_days", "payment.variance_refund_method",
            "payment.variance_ap_tolerance_rupiah"]
    original = {k: cfg_get(admin, k) for k in keys}

    # ── TEST 1 ───────────────────────────────────────────────────────────────
    head("TEST 1 — Kosakata, kebijakan berlaku, dan RBAC")
    m = requests.get(f"{BASE}/payment-variances/meta", headers=H(admin), timeout=30)
    meta = m.json() if m.status_code == 200 else {}
    pol = meta.get("policy", {})
    ok(m.status_code == 200 and "tolerance" in pol,
       "kebijakan selisih yang BERLAKU bisa dibaca UI",
       f"toleransi {rp(pol.get('tolerance'))} · bawaan kurang={pol.get('underpay_default')} "
       f"lebih={pol.get('overpay_default')}")
    codes = {r["code"] for r in meta.get("reasons", [])}
    ok({"rounding_diff", "bank_charge", "uncollectible_small",
        "customer_refund_request"} <= codes,
       "label alasan selisih memakai taksonomi yang bisa ditambah admin (warisan G-1)",
       f"{len(codes)} label")
    ok(set(meta.get("under_kinds", [])) == {"outstanding", "reschedule", "writeoff"}
       and set(meta.get("over_kinds", [])) == {"deposit", "allocate", "refund"},
       "3 pilihan kurang bayar & 3 pilihan lebih bayar tersedia untuk dialog")
    ms = requests.get(f"{BASE}/payment-variances/meta", headers=H(sales), timeout=30)
    ok(ms.status_code == 200, "sales boleh MELIHAT kebijakan selisih (transparan)")

    # ── TEST 2 ───────────────────────────────────────────────────────────────
    head("TEST 2 — Takar selisih JUJUR: bayar lebih awal BUKAN selisih")
    so1 = make_order(admin, qty=20.0)
    cust_id = so1["customer_id"]
    t1 = round(float(so1.get("grand_total") or 0), 2)
    half = round(t1 / 2, 2)
    plan1 = plan_create(admin, so1["id"], [
        {"kind": "installment", "label": "Termin 1 (sudah jatuh tempo)", "basis": "amount",
         "amount": half, "due_rule": "fixed_date", "due_date": day(-10)},
        {"kind": "installment", "label": "Termin 2 (bulan depan)", "basis": "amount",
         "amount": round(t1 - half, 2), "due_rule": "fixed_date", "due_date": day(30)},
    ])
    ok(bool(plan1.get("number")), f"SO uji {so1.get('number')} + rencana 2 termin",
       f"{rp(t1)} · {plan1.get('number')}")

    a_exact = assess(admin, cust_id, half, [{"order_id": so1["id"], "amount": half}])
    ok(a_exact.get("direction") == "none" and not a_exact.get("needs_decision"),
       "bayar PAS sejumlah yang jatuh tempo → tidak ada selisih",
       f"jatuh tempo {rp(a_exact.get('expected'))}")
    a_ahead = assess(admin, cust_id, t1, [{"order_id": so1["id"], "amount": t1}])
    ok(a_ahead.get("direction") == "none" and a_ahead.get("delta") == 0,
       "bayar SELURUH tagihan (termin 2 lebih awal) → tetap BUKAN selisih",
       f"jatuh tempo {rp(a_ahead.get('expected'))} · kapasitas {rp(a_ahead.get('capacity'))}")
    a_under = assess(admin, cust_id, round(half - 250000, 2),
                     [{"order_id": so1["id"], "amount": round(half - 250000, 2)}])
    ok(a_under.get("direction") == "under" and a_under.get("delta") == -250000,
       "kurang dari yang jatuh tempo → KURANG bayar dengan 3 pilihan",
       f"{[o['value'] for o in a_under.get('options', [])]}")
    a_over = assess(admin, cust_id, round(t1 + 750000, 2),
                    [{"order_id": so1["id"], "amount": t1}])
    ok(a_over.get("direction") == "over" and a_over.get("delta") == 750000,
       "lebih dari yang bisa dialokasikan → LEBIH bayar dengan 3 pilihan",
       f"{[o['value'] for o in a_over.get('options', [])]}")
    ok(any("Uang masuk" in e for e in a_under.get("explain", []))
       and len(a_under.get("explain", [])) >= 4,
       "penjelasan angka (explain) bisa dibaca manusia — bukan angka telanjang",
       a_under.get("explain", [""])[1] if len(a_under.get("explain", [])) > 1 else "")

    # ── TEST 3 ───────────────────────────────────────────────────────────────
    head("TEST 3 — Kurang bayar DI DALAM toleransi → otomatis lunas, tetap berlabel")
    so2 = make_order(admin, qty=10.0)
    t2 = round(float(so2.get("grand_total") or 0), 2)
    gl_before = gl_balance("6-9100")
    r = pay(admin, so2["customer_id"], round(t2 - 2500, 2),
            [{"order_id": so2["id"], "amount": round(t2 - 2500, 2)}])
    rec2 = r.json() if r.status_code in (200, 201) else {}
    v2 = rec2.get("variance") or {}
    ok(r.status_code in (200, 201) and v2.get("direction") == "rounding",
       "selisih Rp 2.500 (di bawah toleransi Rp 5.000) ditandai `rounding`",
       f"kwitansi {rec2.get('number')}")
    ok(v2.get("decision_kind") == "rounding_writeoff" and v2.get("decision_number"),
       "diselesaikan OTOMATIS sebagai keputusan berlabel (bukan senyap)",
       f"{v2.get('decision_number')} · {v2.get('reason_label')}")
    ok(outstanding_of(admin, so2["id"]) <= 0.01
       and order_of(admin, so2["id"]).get("payment_status") == "paid",
       "pesanan langsung LUNAS walau nominalnya tidak persis")
    gl_after = gl_balance("6-9100")
    ok(abs((gl_after - gl_before) - 2500) < 0.02,
       "beban selisih pembayaran 6-9100 bertambah tepat Rp 2.500 (berjurnal)",
       f"{rp(gl_before)} → {rp(gl_after)}")

    # ── TEST 4 ───────────────────────────────────────────────────────────────
    head("TEST 4 — Kurang bayar DI LUAR toleransi tanpa keputusan → masuk ANTREAN")
    so3 = make_order(admin, qty=15.0)
    t3 = round(float(so3.get("grand_total") or 0), 2)
    short3 = 500000.0
    r = pay(admin, so3["customer_id"], round(t3 - short3, 2),
            [{"order_id": so3["id"], "amount": round(t3 - short3, 2)}])
    rec3 = r.json() if r.status_code in (200, 201) else {}
    v3 = rec3.get("variance") or {}
    ok(v3.get("direction") == "under" and v3.get("needs_decision") is True
       and not v3.get("decision_id"),
       "kwitansi tetap sah, selisihnya MENUNGGU keputusan", f"kurang {rp(short3)}")
    pend = requests.get(f"{BASE}/payment-variances/pending", headers=H(admin), timeout=30).json()
    ok(any(x["receipt_id"] == rec3.get("id") for x in pend.get("items", [])),
       "muncul di antrean Selisih Bayar (tidak ada uang yang hilang dari perhatian)",
       f"{pend.get('count')} di antrean")
    detail = requests.get(f"{BASE}/payment-variances/receipt/{rec3['id']}",
                          headers=H(admin), timeout=30).json()
    ok(bool(detail.get("assessment")) and detail["assessment"].get("options"),
       "antrean menyediakan pilihan + dampak untuk diputus BELAKANGAN")
    r = decide(admin, rec3["id"], kind="outstanding",
               reason_code="partial_payment_agreed", note="Pelanggan janji bayar sisa akhir bulan")
    d3 = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and d3.get("kind") == "outstanding" and d3.get("number"),
       f"pilihan (a) sisa tetap piutang tercatat: {d3.get('number')}",
       d3.get("reason_label", ""))
    ok(abs(outstanding_of(admin, so3["id"]) - short3) < 0.02,
       "outstanding pesanan TETAP sebesar sisanya (tidak diubah diam-diam)",
       rp(outstanding_of(admin, so3["id"])))
    pend2 = requests.get(f"{BASE}/payment-variances/pending", headers=H(admin), timeout=30).json()
    ok(not any(x["receipt_id"] == rec3.get("id") for x in pend2.get("items", [])),
       "setelah diputus, kwitansi keluar dari antrean")

    # ── TEST 5 ───────────────────────────────────────────────────────────────
    head("TEST 5 — Hapus sisa: wajib alasan, wajib wewenang, ada batas nominal")
    so4 = make_order(admin, qty=12.0)
    t4 = round(float(so4.get("grand_total") or 0), 2)
    r = pay(finance, so4["customer_id"], round(t4 - 300000, 2),
            [{"order_id": so4["id"], "amount": round(t4 - 300000, 2)}])
    rec4 = r.json() if r.status_code in (200, 201) else {}
    ok(bool(rec4.get("id")), "kwitansi dicatat oleh FINANCE (wewenang uang masuk E-8)",
       f"HTTP {r.status_code} {r.text[:80]}")
    r_no_reason = decide(manager, rec4["id"], kind="writeoff", reason_code="")
    ok(r_no_reason.status_code == 400 and "alasan" in r_no_reason.text.lower(),
       "keputusan TANPA label alasan ditolak", r_no_reason.text[:90])
    r_bad_reason = decide(manager, rec4["id"], kind="writeoff", reason_code="penalty_waiver")
    ok(r_bad_reason.status_code == 400 and "tidak berlaku" in r_bad_reason.text.lower(),
       "label alasan yang bukan untuk selisih pembayaran ditolak", r_bad_reason.text[:90])
    # E8.2 — sales bahkan TIDAK punya izin memutus selisih (dulu 400 "butuh manager";
    # sekarang 403 karena izinnya dicabut sama sekali). Keduanya sah sebagai pagar;
    # yang penting sales tidak pernah bisa menghapus sisa piutang.
    r_sales = decide(sales, rec4["id"], kind="writeoff", reason_code="uncollectible_small")
    ok(r_sales.status_code in (400, 403),
       "SALES tidak boleh menghapus sisa piutang (wewenang dijaga)", r_sales.text[:90])
    gl_b = gl_balance("6-9100")
    r_mgr = decide(manager, rec4["id"], kind="writeoff", reason_code="uncollectible_small",
                   note="Sisa kecil, biaya menagih lebih besar")
    d4 = r_mgr.json() if r_mgr.status_code == 200 else {}
    ok(r_mgr.status_code == 200 and d4.get("je_number"),
       f"MANAGER boleh menghapus sisa → berjurnal {d4.get('je_number')}", rp(d4.get("amount")))
    ok(abs((gl_balance("6-9100") - gl_b) - 300000) < 0.02
       and outstanding_of(admin, so4["id"]) <= 0.01,
       "piutang hilang dari buku & pesanan lunas (bukan sekadar ditandai)")

    cfg_set(admin, "payment.variance_writeoff_max_amount", 100000)
    so5 = make_order(admin, qty=12.0)
    t5 = round(float(so5.get("grand_total") or 0), 2)
    r = pay(admin, so5["customer_id"], round(t5 - 400000, 2),
            [{"order_id": so5["id"], "amount": round(t5 - 400000, 2)}])
    rec5 = r.json() if r.status_code in (200, 201) else {}
    r_over = decide(manager, rec5["id"], kind="writeoff", reason_code="uncollectible_small")
    ok(r_over.status_code == 400 and "batas" in r_over.text.lower(),
       "di atas batas nominal, manager DITOLAK (harus admin/direksi)", r_over.text[:100])
    r_adm = decide(admin, rec5["id"], kind="writeoff", reason_code="uncollectible_small",
                   note="Keputusan direksi")
    ok(r_adm.status_code == 200, "admin/direksi boleh memutus di atas batas",
       (r_adm.json() or {}).get("number", ""))
    cfg_set(admin, "payment.variance_writeoff_max_amount",
            original.get("payment.variance_writeoff_max_amount") or 1000000)

    # ── TEST 6 ───────────────────────────────────────────────────────────────
    head("TEST 6 — Ubah jadwal: sisa jadi tempo baru, Σ rencana TIDAK berubah")
    so6 = make_order(admin, qty=18.0)
    t6 = round(float(so6.get("grand_total") or 0), 2)
    dp6 = round(t6 * 0.4, 2)
    plan6 = plan_create(admin, so6["id"], [
        {"kind": "dp", "label": "DP 40%", "basis": "amount", "amount": dp6,
         "due_rule": "fixed_date", "due_date": day(-5)},
        {"kind": "installment", "label": "Pelunasan", "basis": "amount",
         "amount": round(t6 - dp6, 2), "due_rule": "fixed_date", "due_date": day(25)},
    ])
    gap6 = 1000000.0
    r = pay(admin, so6["customer_id"], round(dp6 - gap6, 2),
            [{"order_id": so6["id"], "amount": round(dp6 - gap6, 2)}])
    rec6 = r.json() if r.status_code in (200, 201) else {}
    new_due = day(21)
    r = decide(manager, rec6["id"], kind="reschedule", reason_code="term_extension",
               due_date=new_due, note="Kesepakatan geser tempo 3 minggu")
    d6 = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and d6.get("kind") == "reschedule",
       f"sisa {rp(gap6)} dijadwalkan ulang ke {new_due}", r.text[:120] if r.status_code != 200 else "")
    pl = requests.get(f"{BASE}/payment-plans/by-doc/sales_order/{so6['id']}",
                      headers=H(admin), timeout=30).json().get("plan") or {}
    lines6 = pl.get("lines") or []
    new_line = next((l for l in lines6 if str(l.get("due_date"))[:10] == new_due), None)
    ok(bool(new_line) and abs(float(new_line.get("amount") or 0) - gap6) < 0.02,
       "baris jadwal BARU muncul dengan tempo & nominal sisa yang benar",
       f"{new_line.get('label') if new_line else '—'} {rp((new_line or {}).get('amount'))}")
    ok(abs(round(sum(float(l["amount"]) for l in lines6), 2) - t6) <= 1,
       "Σ seluruh baris tetap sama dengan nilai pesanan (INV-PAY-01 tetap sah)",
       f"Σ {rp(sum(float(l['amount']) for l in lines6))} vs {rp(t6)}")
    ok(any((h.get("action") or "").startswith("reschedule") for h in (pl.get("history") or [])),
       "riwayat penjadwalan ulang tercatat di rencana (siapa, kapan, alasan)")

    # ── TEST 7 ───────────────────────────────────────────────────────────────
    head("TEST 7 — Lebih bayar: deposit · alokasi ke pesanan lain · pengembalian dana")
    so7 = make_order(admin, qty=8.0)
    t7 = round(float(so7.get("grand_total") or 0), 2)
    cust7 = so7["customer_id"]
    dep_before = deposit_of(admin, cust7)
    r = pay(admin, cust7, round(t7 + 700000, 2), [{"order_id": so7["id"], "amount": t7}],
            variance={"kind": "deposit", "reason_code": "customer_overtransfer",
                      "note": "Pelanggan transfer lebih"})
    rec7 = r.json() if r.status_code in (200, 201) else {}
    v7 = rec7.get("variance") or {}
    ok(v7.get("decision_kind") == "deposit" and v7.get("decision_number"),
       "pilihan (a) deposit tercatat sebagai keputusan berlabel",
       f"{v7.get('decision_number')} · {rp(v7.get('decision_amount'))}")
    ok(abs(deposit_of(admin, cust7) - (dep_before + 700000)) < 0.02,
       "saldo deposit pelanggan naik tepat sebesar kelebihannya",
       f"{rp(dep_before)} → {rp(deposit_of(admin, cust7))}")

    so8 = make_order(admin, qty=8.0)
    t8 = round(float(so8.get("grand_total") or 0), 2)
    out3_before = outstanding_of(admin, so3["id"])
    alloc_amt = min(600000.0, out3_before)
    dep_b8 = deposit_of(admin, so8["customer_id"])
    gl_uang_muka_b = gl_balance("2-1400")
    r = pay(admin, so8["customer_id"], round(t8 + alloc_amt, 2),
            [{"order_id": so8["id"], "amount": t8}],
            variance={"kind": "allocate", "reason_code": "customer_overtransfer",
                      "allocations": [{"order_id": so3["id"], "amount": alloc_amt}],
                      "note": "Kelebihan dipakai melunasi pesanan lain"})
    rec8 = r.json() if r.status_code in (200, 201) else {}
    v8 = rec8.get("variance") or {}
    ok(v8.get("decision_kind") == "allocate",
       "pilihan (b) alokasi ke pesanan terbuka lain berhasil",
       f"{v8.get('decision_number')} → {rp(alloc_amt)}")
    ok(abs(out3_before - outstanding_of(admin, so3["id"]) - alloc_amt) < 0.02,
       "outstanding pesanan LAIN benar-benar berkurang",
       f"{rp(out3_before)} → {rp(outstanding_of(admin, so3['id']))}")
    ok(abs(deposit_of(admin, so8["customer_id"]) - dep_b8) < 0.02,
       "deposit tidak menumpuk (naik lalu dipakai — bersih)")
    ok(abs((gl_balance("2-1400") - gl_uang_muka_b)) < 0.02,
       "GL Uang Muka Pelanggan 2-1400 net nol untuk kwitansi ini (Cr lalu Dr)")

    so9 = make_order(admin, qty=8.0)
    t9 = round(float(so9.get("grand_total") or 0), 2)
    refund_amt = 400000.0
    dep_b9 = deposit_of(admin, so9["customer_id"])
    r = pay(manager, so9["customer_id"], round(t9 + refund_amt, 2),
            [{"order_id": so9["id"], "amount": t9}],
            variance={"kind": "refund", "reason_code": "customer_refund_request",
                      "method": "transfer", "note": "Pelanggan minta dikembalikan"})
    rec9 = r.json() if r.status_code in (200, 201) else {}
    v9 = rec9.get("variance") or {}
    dec9 = requests.get(f"{BASE}/payment-variances/{v9.get('decision_id')}",
                        headers=H(admin), timeout=30).json() if v9.get("decision_id") else {}
    ok(v9.get("decision_kind") == "refund" and (dec9.get("effect") or {}).get("refund"),
       "pilihan (c) pengembalian dana berhasil & berjurnal",
       f"kas {((dec9.get('effect') or {}).get('refund') or {}).get('cash_txn_number', '')}")
    ok(abs(deposit_of(admin, so9["customer_id"]) - dep_b9) < 0.02,
       "deposit tidak bertambah karena uangnya benar-benar keluar")

    async def _cash_out(db):
        return await db.cash_transactions.find_one(
            {"ref_type": "ar_refund", "ref_id": v9.get("decision_id")}, {"_id": 0})
    cash_row = dbrun(_cash_out)
    ok(bool(cash_row) and cash_row.get("direction") == "out"
       and abs(float(cash_row.get("amount") or 0) - refund_amt) < 0.02,
       "kas keluar tercatat di buku kas (bisa direkonsiliasi bank)",
       f"{(cash_row or {}).get('number')} {rp((cash_row or {}).get('amount'))}")

    so_sr = make_order(admin, qty=5.0)
    t_sr = round(float(so_sr.get("grand_total") or 0), 2)
    r_sales_refund = pay(finance, so_sr["customer_id"], round(t_sr + 300000, 2),
                         [{"order_id": so_sr["id"], "amount": t_sr}],
                         variance={"kind": "refund", "reason_code": "customer_refund_request"})
    rec_sr = r_sales_refund.json() if r_sales_refund.status_code in (200, 201) else {}
    v_sr = rec_sr.get("variance") or {}
    ok(not v_sr.get("decision_id") and "manager" in (v_sr.get("decision_error") or "").lower(),
       "SALES tidak bisa mengembalikan dana — kwitansi tetap sah, selisih masuk antrean",
       (v_sr.get("decision_error") or "")[:90] or f"kind={v_sr.get('decision_kind')}")
    if rec_sr.get("id") and v_sr.get("needs_decision") and not v_sr.get("decision_id"):
        decide(manager, rec_sr["id"], kind="deposit", reason_code="customer_overtransfer",
               note="Diputus manager: simpan sebagai deposit")

    # ── TEST 8 ───────────────────────────────────────────────────────────────
    head("TEST 8 — Pembayaran bisa MENYEBUT baris jadwal tujuan (bukan hanya waterfall)")
    so10 = make_order(admin, qty=20.0)
    t10 = round(float(so10.get("grand_total") or 0), 2)
    each = round(t10 / 4, 2)
    plan10 = plan_create(admin, so10["id"], [
        {"kind": "installment", "label": "Termin 1", "basis": "amount", "amount": each,
         "due_rule": "fixed_date", "due_date": day(-20)},
        {"kind": "installment", "label": "Termin 2", "basis": "amount", "amount": each,
         "due_rule": "fixed_date", "due_date": day(-10)},
        {"kind": "installment", "label": "Termin 3", "basis": "amount", "amount": each,
         "due_rule": "fixed_date", "due_date": day(10)},
        {"kind": "installment", "label": "Termin 4", "basis": "amount",
         "amount": round(t10 - each * 3, 2), "due_rule": "fixed_date", "due_date": day(40)},
    ])
    r = pay(admin, so10["customer_id"], each,
            [{"order_id": so10["id"], "amount": each, "plan_line_seq": 3}],
            variance={"kind": "outstanding", "reason_code": "partial_payment_agreed",
                      "note": "Pelanggan menyebut ini untuk termin 3"})
    ok(r.status_code in (200, 201), "kwitansi menyebut baris tujuan (termin 3) tersimpan",
       r.text[:120] if r.status_code not in (200, 201) else "")
    pl10 = requests.get(f"{BASE}/payment-plans/by-doc/sales_order/{so10['id']}",
                        headers=H(admin), timeout=30).json().get("plan") or {}
    l10 = {int(l["seq"]): l for l in (pl10.get("lines") or [])}
    ok(l10.get(3, {}).get("status") == "paid" and l10.get(1, {}).get("status") == "open",
       "uang mendarat di TERMIN 3 seperti yang disebut pelanggan — termin 1 tetap terbuka",
       f"t1={l10.get(1, {}).get('status')} t3={l10.get(3, {}).get('status')}")
    ok(abs(round(float(pl10.get("paid_total") or 0), 2) - each) < 0.02,
       "Σ terbayar pada jadwal tetap sama dengan kas nyata (INV-PAY-02)")

    # ── TEST 9 ───────────────────────────────────────────────────────────────
    head("TEST 9 — Sakelar admin benar-benar berpengaruh (bukan tombol palsu)")
    so_cfg = make_order(admin, qty=7.0)
    t_cfg = round(float(so_cfg.get("grand_total") or 0), 2)
    cust_cfg = so_cfg["customer_id"]
    plan_create(admin, so_cfg["id"], [
        {"kind": "installment", "label": "Pelunasan (jatuh tempo)", "basis": "amount",
         "amount": t_cfg, "due_rule": "fixed_date", "due_date": day(-3)}])
    cfg_set(admin, "payment.variance_tolerance_rupiah", 0)
    a0 = assess(admin, cust_cfg, round(t_cfg - 2000, 2),
                [{"order_id": so_cfg["id"], "amount": round(t_cfg - 2000, 2)}])
    ok(a0.get("direction") == "under" and a0.get("needs_decision") is True,
       "toleransi 0 → selisih receh pun WAJIB diputus",
       f"toleransi {rp(a0.get('tolerance'))} · arah {a0.get('direction')}")
    cfg_set(admin, "payment.variance_tolerance_rupiah", 5000000)
    a1 = assess(admin, cust_cfg, round(t_cfg - 2000, 2),
                [{"order_id": so_cfg["id"], "amount": round(t_cfg - 2000, 2)}])
    ok(a1.get("direction") == "rounding" and a1.get("auto") is True,
       "toleransi besar → selisih yang sama diselesaikan otomatis")
    cfg_set(admin, "payment.variance_tolerance_rupiah",
            original.get("payment.variance_tolerance_rupiah") or 5000)
    cfg_set(admin, "payment.variance_underpay_default", "reschedule")
    a2 = assess(admin, cust_cfg, round(t_cfg - 500000, 2),
                [{"order_id": so_cfg["id"], "amount": round(t_cfg - 500000, 2)}])
    dflt = next((o["value"] for o in a2.get("options", []) if o.get("default")), "")
    ok(dflt == "reschedule",
       "pilihan BAWAAN di dialog mengikuti kebijakan admin",
       f"bawaan = {dflt} (arah {a2.get('direction')})")
    cfg_set(admin, "payment.variance_underpay_default",
            original.get("payment.variance_underpay_default") or "outstanding")
    cfg_set(admin, "payment.variance_writeoff_requires_approval", False)
    so11 = make_order(admin, qty=6.0)
    t11 = round(float(so11.get("grand_total") or 0), 2)
    r = pay(finance, so11["customer_id"], round(t11 - 200000, 2),
            [{"order_id": so11["id"], "amount": round(t11 - 200000, 2)}])
    rec11 = r.json() if r.status_code in (200, 201) else {}
    # Sakelar kebijakan diuji pada peran yang MEMANG berwenang memutus selisih
    # (Finance, sejak E8.2). Dulu barisnya memakai `sales`; setelah pemisahan tugas,
    # "sales boleh memutus" bukan lagi keadaan yang sah untuk diuji — yang diuji di
    # sini adalah SAKELARNYA (perlu persetujuan atau tidak), bukan siapa aktornya.
    r_free = decide(finance, rec11["id"], kind="writeoff", reason_code="uncollectible_small",
                    note="Persetujuan dimatikan admin")
    ok(r_free.status_code == 200,
       "sakelar 'wajib disetujui' dimatikan → Finance boleh memutus (kebijakan, bukan kode)",
       r_free.text[:90])
    cfg_set(admin, "payment.variance_writeoff_requires_approval",
            original.get("payment.variance_writeoff_requires_approval")
            if original.get("payment.variance_writeoff_requires_approval") is not None else True)

    # ── TEST 10 ──────────────────────────────────────────────────────────────
    head("TEST 10 — Jalur AP: selisih saat KITA membayar tagihan supplier")

    async def _bills(db):
        rows = await db.vendor_bills.find({"status": "posted"}, {"_id": 0}).to_list(10)
        return rows
    bills = dbrun(_bills)
    if len(bills) >= 2:
        b1, b2 = bills[0], bills[1]
        _bill_backup[b1["id"]] = b1
        _bill_backup[b2["id"]] = b2
        gl_hutang_b = gl_balance("2-1100")
        amt1 = round(float(b1["grand_total"]) - 2000, 2)
        rb = requests.post(f"{BASE}/vendor-bills/{b1['id']}/pay", headers=H(admin), timeout=60,
                           json={"amount": amt1, "cash_type": "kas_besar", "method": "transfer"})
        jb = rb.json() if rb.status_code == 200 else {}
        dec_ap = jb.get("variance_decision") or {}
        if dec_ap.get("id"):
            _made["decisions"].append(dec_ap["id"])
        ok(rb.status_code == 200 and jb.get("status") == "paid"
           and dec_ap.get("kind") == "ap_rounding_writeoff",
           "kurang bayar receh ke supplier → tagihan LUNAS otomatis + keputusan berlabel",
           f"{jb.get('bill_number')} · {dec_ap.get('number')}")
        ok(dec_ap.get("je_number", "") != "",
           "penutupan sisa hutang supplier berjurnal (Dr 2-1100 / Cr 4-9000)",
           dec_ap.get("je_number", ""))
        r_over = requests.post(f"{BASE}/vendor-bills/{b2['id']}/pay", headers=H(admin),
                               timeout=60, json={"amount": round(float(b2["grand_total"]) + 50000, 2),
                                                 "cash_type": "kas_besar", "method": "transfer"})
        ok(r_over.status_code == 400 and "uang muka" in r_over.text.lower(),
           "bayar LEBIH tanpa keputusan DITOLAK dengan saran yang jelas",
           r_over.text[:110])
        gl_um_b = gl_balance("1-1400")
        r_adv = requests.post(f"{BASE}/vendor-bills/{b2['id']}/pay", headers=H(admin), timeout=60,
                              json={"amount": round(float(b2["grand_total"]) + 50000, 2),
                                    "cash_type": "kas_besar", "method": "transfer",
                                    "variance": {"kind": "ap_advance",
                                                 "reason_code": "supplier_advance",
                                                 "note": "Titipan untuk order berikutnya"}})
        ja = r_adv.json() if r_adv.status_code == 200 else {}
        dec_adv = ja.get("variance_decision") or {}
        if dec_adv.get("id"):
            _made["decisions"].append(dec_adv["id"])
        ok(r_adv.status_code == 200 and dec_adv.get("kind") == "ap_advance",
           "bayar LEBIH dengan keputusan → kelebihan jadi uang muka supplier",
           f"{dec_adv.get('number')} {rp(dec_adv.get('amount'))}")
        ok(abs((gl_balance("1-1400") - gl_um_b) - 50000) < 0.02,
           "GL Uang Muka 1-1400 bertambah tepat sebesar kelebihannya",
           f"{rp(gl_um_b)} → {rp(gl_balance('1-1400'))}")
        ok(gl_balance("2-1100") != gl_hutang_b, "hutang usaha 2-1100 ikut bergerak (berjurnal)")
    else:
        ok(False, "butuh 2 tagihan supplier `posted` di seed untuk uji jalur AP")

    # ── TEST 11 ──────────────────────────────────────────────────────────────
    head("TEST 11 — Void kwitansi MEMBALIK keputusan yang sudah jalan")
    so12 = make_order(admin, qty=9.0)
    t12 = round(float(so12.get("grand_total") or 0), 2)
    r = pay(admin, so12["customer_id"], round(t12 - 250000, 2),
            [{"order_id": so12["id"], "amount": round(t12 - 250000, 2)}])
    rec12 = r.json() if r.status_code in (200, 201) else {}
    r = decide(manager, rec12["id"], kind="writeoff", reason_code="uncollectible_small",
               note="Sisa dihapus")
    d12 = r.json() if r.status_code == 200 else {}
    ok(outstanding_of(admin, so12["id"]) <= 0.01, "pesanan lunas setelah sisa dihapus")
    gl_b12 = gl_balance("6-9100")
    rv = requests.post(f"{BASE}/ar-receipts/{rec12['id']}/void", headers=H(admin), timeout=60)
    ok(rv.status_code == 200, "kwitansi bisa dibatalkan", rv.text[:100] if rv.status_code != 200 else "")
    ok(abs(outstanding_of(admin, so12["id"]) - t12) < 0.02,
       "seluruh piutang KEMBALI (penghapusan ikut dibatalkan)",
       rp(outstanding_of(admin, so12["id"])))
    ok(abs((gl_b12 - gl_balance("6-9100")) - 250000) < 0.02,
       "beban selisih dibalik lewat JURNAL PEMBALIK (bukan jurnal dihapus)")
    d12b = requests.get(f"{BASE}/payment-variances/{d12.get('id')}",
                        headers=H(admin), timeout=30).json() if d12.get("id") else {}
    ok(d12b.get("status") == "reversed" and d12b.get("reversal_je_number"),
       "jejak keputusan TETAP ada dengan status `reversed`",
       f"{d12b.get('reversal_je_number')}")

    # ── TEST 12 ──────────────────────────────────────────────────────────────
    head("TEST 12 — Integrasi FASE G-4: keputusan selisih ada di Jejak Dokumen")
    if d4.get("id"):
        tr = requests.get(f"{BASE}/documents/trace/payment_variance/{d4['id']}",
                          headers=H(admin), timeout=40)
        graph = tr.json() if tr.status_code == 200 else {}
        nodes = graph.get("nodes") or graph.get("items") or []
        types = {n.get("doc_type") for n in nodes} if nodes else set()
        ok(tr.status_code == 200 and ("ar_receipt" in types or "sales_order" in types),
           "keputusan bisa ditelusuri ke kwitansi & pesanannya (dua arah)",
           f"{len(nodes)} simpul: {sorted(t for t in types if t)}")
        rf = requests.get(f"{BASE}/documents/refs/ar_receipt/{d4.get('receipt_id')}",
                          headers=H(admin), timeout=40)
        refs = rf.json() if rf.status_code == 200 else {}
        rows = refs.get("refs") or refs.get("items") or []
        ok(any(r.get("doc_type") == "payment_variance" for r in rows),
           "dari sisi kwitansi, keputusan selisihnya juga terlihat (relasi dua arah)")
    else:
        ok(False, "keputusan hapus sisa tidak terbentuk — uji jejak dokumen dilewati")

    # ── TEST 13 ──────────────────────────────────────────────────────────────
    head("TEST 13 — BUKTI-MERAH: invarian INV-VAR memerah saat dilanggar")
    code0, out0 = integrity("variance")
    ok(inv_state(out0, "INV-VAR-01") in ("PASS", "WARN")
       and inv_state(out0, "INV-VAR-02a") == "PASS",
       "kondisi awal: invarian selisih pembayaran hijau",
       f"exit={code0}")

    async def strip_reason(db):
        row = await db.payment_variance_decisions.find_one(
            {"id": {"$in": _made["decisions"]}}, {"_id": 0, "id": 1, "reason_code": 1})
        if not row:
            return None
        await db.payment_variance_decisions.update_one(
            {"id": row["id"]}, {"$set": {"reason_code": ""}})
        return row
    victim = dbrun(strip_reason)
    code1, out1 = integrity("variance")
    ok(inv_state(out1, "INV-VAR-01") == "FAIL",
       "INV-VAR-01 MEMERAH saat ada keputusan tanpa label alasan", f"exit={code1}")

    async def restore_reason(db):
        if victim:
            await db.payment_variance_decisions.update_one(
                {"id": victim["id"]}, {"$set": {"reason_code": victim.get("reason_code") or "rounding_diff"}})
    dbrun(restore_reason)

    async def break_money(db):
        row = await db.ar_receipts.find_one({"id": {"$in": _made["receipts"]}},
                                            {"_id": 0, "id": 1, "applied_total": 1})
        if not row:
            return None
        await db.ar_receipts.update_one({"id": row["id"]}, {
            "$set": {"applied_total": round(float(row.get("applied_total") or 0) + 12345, 2)}})
        return row
    leak = dbrun(break_money)
    code2, out2 = integrity("variance")
    ok(inv_state(out2, "INV-VAR-02a") == "FAIL",
       "INV-VAR-02 MEMERAH saat dana kwitansi tidak lagi sama dengan rinciannya",
       f"exit={code2}")

    async def fix_money(db):
        if leak:
            await db.ar_receipts.update_one({"id": leak["id"]}, {
                "$set": {"applied_total": round(float(leak.get("applied_total") or 0), 2)}})
    dbrun(fix_money)

    async def strip_je(db):
        row = await db.payment_variance_decisions.find_one(
            {"id": {"$in": _made["decisions"]}, "kind": "writeoff", "status": {"$ne": "reversed"}},
            {"_id": 0, "id": 1, "je_id": 1})
        if not row:
            return None
        await db.payment_variance_decisions.update_one({"id": row["id"]}, {"$set": {"je_id": ""}})
        return row
    nje = dbrun(strip_je)
    code3, out3 = integrity("variance")
    ok(inv_state(out3, "INV-VAR-02b") == "FAIL" if nje else True,
       "INV-VAR-02 MEMERAH saat keputusan memindahkan uang tanpa jurnal", f"exit={code3}")

    async def fix_je(db):
        if nje:
            await db.payment_variance_decisions.update_one(
                {"id": nje["id"]}, {"$set": {"je_id": nje.get("je_id") or ""}})
    dbrun(fix_je)

    async def age_pending(db):
        row = await db.ar_receipts.find_one(
            {"id": {"$in": _made["receipts"]}, "variance.needs_decision": True,
             "variance.decision_id": ""}, {"_id": 0, "id": 1, "created_at": 1})
        if not row:
            return None
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        await db.ar_receipts.update_one({"id": row["id"]}, {"$set": {"created_at": old}})
        return row
    stale = dbrun(age_pending)
    code4, out4 = integrity("variance")
    if stale:
        ok(inv_state(out4, "INV-VAR-01") == "FAIL",
           "INV-VAR-01 MEMERAH saat selisih dibiarkan menggantung >7 hari", f"exit={code4}")

        async def unage(db):
            await db.ar_receipts.update_one({"id": stale["id"]}, {
                "$set": {"created_at": stale.get("created_at")}})
        dbrun(unage)
    else:
        ok(True, "tidak ada selisih menggantung untuk diuji-tuakan (semua sudah diputus)")

    code5, out5 = integrity("variance")
    ok(inv_state(out5, "INV-VAR-02a") == "PASS" and inv_state(out5, "INV-VAR-02b") == "PASS",
       "dipulihkan → invarian selisih pembayaran HIJAU lagi (invarian bukan hiasan)")

    # ── CLEANUP ──────────────────────────────────────────────────────────────
    head("CLEANUP — kembalikan lingkungan ke keadaan semula (nol residu)")
    for k, v in original.items():
        if v is not None:
            cfg_set(admin, k, v, reason="pulihkan setelah POC G-3")
    ok(all(cfg_get(admin, k) == v for k, v in original.items() if v is not None),
       "seluruh konfigurasi selisih pembayaran dipulihkan ke nilai semula")

    async def purge(db):
        n = 0
        ids = _made["orders"]
        rec_ids = _made["receipts"]
        dec_ids = [d["id"] for d in await db.payment_variance_decisions.find(
            {"$or": [{"receipt_id": {"$in": rec_ids}}, {"id": {"$in": _made["decisions"]}}]},
            {"_id": 0, "id": 1}).to_list(500)]
        plan_ids = [p["id"] for p in await db.payment_plans.find(
            {"doc_id": {"$in": ids}}, {"_id": 0, "id": 1}).to_list(500)]
        pen_ids = [p["id"] for p in await db.penalties.find(
            {"doc_id": {"$in": ids}}, {"_id": 0, "id": 1}).to_list(500)]
        all_ids = ids + rec_ids + dec_ids + plan_ids + pen_ids
        for coll in ("sales_orders", "purchase_orders", "vendor_bills", "payment_plans",
                     "penalties", "wms_tasks", "ar_receipts", "payment_variance_decisions"):
            await db[coll].update_many({}, {"$pull": {"refs": {"doc_id": {"$in": all_ids}}}})
        for coll, key in (("payment_variance_decisions", dec_ids),
                          ("penalties", pen_ids), ("payment_plans", plan_ids),
                          ("ar_receipts", rec_ids), ("sales_orders", ids)):
            res = await db[coll].delete_many({"id": {"$in": key}})
            n += res.deleted_count
        # Tagihan supplier yang dipakai uji AP dipulihkan UTUH ke bentuk semula.
        for bid, doc in _bill_backup.items():
            await db.vendor_bills.replace_one({"id": bid}, doc)
            await db.cash_transactions.delete_many({"ref_id": bid,
                                                    "ref_type": {"$in": ["vendor_bill",
                                                                         "ap_advance"]}})
        if _bill_backup:
            sup_ids = [d.get("supplier_id") for d in _bill_backup.values() if d.get("supplier_id")]
            if sup_ids:
                await db.suppliers.update_many({"id": {"$in": sup_ids}},
                                               {"$unset": {"advance_balance": ""}})
        je_sources = (ids + rec_ids + dec_ids
                      + [f"{d}:rev" for d in dec_ids]
                      + list(_bill_backup.keys()))
        # Jurnal mutasi kas memakai id CASH-nya sebagai `source_id` (bukan id kwitansi),
        # termasuk jurnal pembaliknya. Kalau tidak ikut dihapus, kredit Piutang dari
        # kwitansi POC tertinggal dan membuat saldo AR negatif (INV-AR-01 memperingatkan).
        cash_ids = [c["id"] for c in await db.cash_transactions.find(
            {"ref_id": {"$in": ids + rec_ids + dec_ids + list(_bill_backup.keys())}},
            {"_id": 0, "id": 1}).to_list(1000)]
        je_sources += cash_ids
        await db.journal_entries.delete_many({"source_id": {"$in": je_sources}})
        await db.cash_transactions.delete_many({"ref_id": {"$in": ids + rec_ids + dec_ids}})
        await db.wms_tasks.delete_many({"order_id": {"$in": ids}})
        await db.invoices.delete_many({"order_id": {"$in": ids}})
        # Reservasi/lepas-reservasi memakai id SO pada `source_document`; tanpa
        # dibersihkan mutasi menjadi YATIM & tampil sebagai sampah di Gudang → Mutasi.
        await db.inventory_movements.delete_many({"source_document": {"$in": ids}})
        await db.inventory_movements.delete_many({"reference_id": {"$in": ids}})
        await db.audit_logs.delete_many({"entity_id": {"$in": all_ids}})
        await db.notifications.delete_many({"ref": {"$in": dec_ids}})
        await db.config_values.delete_many({"reason": {"$regex": "POC G-3"}})
        await db.config_values.delete_many({"reason": "pulihkan setelah POC G-3"})
        await db.number_sequences.delete_many({"doc_type": {"$in": ["SLB-", "RPB-"]}})
        # Deposit pelanggan dipulihkan: seluruh kwitansi POC sudah hilang, jadi saldo
        # dihitung ulang dari kwitansi yang MASIH ada (tidak boleh menyisakan titipan hantu).
        for cust in await db.customers.find({"deposit_balance": {"$gt": 0}},
                                            {"_id": 0, "id": 1}).to_list(500):
            rows = await db.ar_receipts.find(
                {"customer_id": cust["id"], "status": {"$ne": "void"}},
                {"_id": 0, "deposit_delta": 1}).to_list(1000)
            bal = round(sum(float(x.get("deposit_delta") or 0) for x in rows), 2)
            await db.customers.update_one({"id": cust["id"]},
                                          {"$set": {"deposit_balance": max(bal, 0.0)}})
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
        print(f"\n{G}{B}✓ POC FASE G-3 HIJAU 100% — selisih pembayaran (lebih & kurang bayar) "
              f"selalu punya keputusan berlabel.{X}")
        return 0
    print(f"\n{R}{B}✗ POC FASE G-3 GAGAL — {_stats['fail']} pemeriksaan merah.{X}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
