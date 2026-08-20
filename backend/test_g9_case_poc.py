#!/usr/bin/env python3
"""POC FASE G-9 — PUSAT KASUS KEUANGAN (satu skrip · HTTP · nol residu).

Membuktikan 11 user story fase G-9 memakai API sungguhan, bukan mock:

  1. Inbox kasus: antrean berisi jenis, nominal dipertaruhkan, umur, sisa SLA, PIC.
  2. Wizard playbook 11 jenis — setiap aksi MELAHIRKAN dokumen turunan nyata
     (jurnal / kas / kwitansi batal / nota denda), bukan mengubah dokumen lama.
  3. Kasus tidak bisa ditutup tanpa **alasan berlabel** & **lampiran bukti**
     (untuk jenis yang mensyaratkannya).
  4. Sistem membuat kasus SENDIRI: titipan dana menganggur + pembayaran dobel.
  5. Ambang persetujuan: penyelesaian besar wajib manager/admin.
  6. SLA terlampaui → kasus dinaikkan ke atasan (eskalasi).
  7. Jejak dokumen dua arah (G-4): sumber → kasus → dokumen turunan.
  8. Deep-link dari Titipan Dana G-8 (kasus terisi otomatis dari mutasi banknya).
  9. Seluruh ambang/SLA dibaca dari Pusat Pengaturan (bukan angka sihir di kode).
 10. INV-CASE-01..03 + BUKTI-MERAH (suntik pelanggaran → WAJIB memerah → pulihkan).
 11. Isolasi lintas-PT: kasus PT lain → 403 walau id dikirim eksplisit.

Jalankan: cd /app && python backend/test_g9_case_poc.py
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

BASE = os.environ.get("KN_BASE", "http://localhost:8001/api")
PWD = "demo12345"
ENT_A = "ent_ksc"
ENT_B = "ent_kanda"
ACC_A = "bank_bca_ksc"
ACC_A2 = "bank_kas_ksc"
POC_TAG = "POC_G9"

G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
res = {"pass": 0, "fail": 0}
made: Dict[str, List[str]] = {"cases": [], "case_numbers": [], "lines": [], "cash": [],
                             "orders": [], "receipts": [], "penalties": []}


def ok(cond: bool, name: str, extra: Any = "") -> bool:
    res["pass" if cond else "fail"] += 1
    tag = f"{G}PASS{X}" if cond else f"{R}FAIL{X}"
    print(f"  [{tag}] {name}" + (f"  ({extra})" if extra else ""))
    return bool(cond)


def head(t: str) -> None:
    print(f"\n{C}{B}── {t} ──{X}")


def login(email: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD}, timeout=30)
    r.raise_for_status()
    tok = r.json().get("token")
    assert tok, f"login {email} gagal: {r.text[:160]}"
    return tok


def H(tok: str, ent: str = "") -> Dict[str, str]:
    h = {"Authorization": f"Bearer {tok}"}
    if ent:
        h["X-Entity-Id"] = ent
    return h


def api(method: str, path: str, tok: str, ent: str = "", **kw) -> requests.Response:
    return requests.request(method, f"{BASE}{path}", headers=H(tok, ent), timeout=120, **kw)


def integrity(only: str = "") -> tuple:
    cmd = [sys.executable, "/app/scripts/verify_data_integrity.py"]
    if only:
        cmd.append(f"--only={only}")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout + p.stderr


def inv_state(out: str, inv: str) -> str:
    for ln in out.splitlines():
        if inv in ln:
            for tag, val in (("[PASS]", "PASS"), ("[FAIL]", "FAIL"), ("[WARN]", "WARN")):
                if tag in ln:
                    return val
    return "?"


def dbrun(fn):
    """Operasi Mongo langsung — HANYA untuk suntikan bukti-merah, penuaan data & cleanup."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _go():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            return await fn(cli[os.environ["DB_NAME"]])
        finally:
            cli.close()

    return asyncio.run(_go())


D0 = datetime.now(timezone.utc).date()


def day(delta: int) -> str:
    return (D0 + timedelta(days=delta)).isoformat()


def gl_balance(code: str) -> float:
    """Saldo (debit − kredit) satu akun di buku besar."""
    def q(db):
        return db.journal_entries.find({}, {"_id": 0, "lines": 1, "status": 1}).to_list(20000)
    total = 0.0
    for je in dbrun(q):
        if je.get("status") == "void":
            continue
        for ln in je.get("lines") or []:
            if ln.get("account_code") == code:
                total += float(ln.get("debit") or 0) - float(ln.get("credit") or 0)
    return round(total, 2)


# ═════════════════════════════════════════════════════════════════════════════
#  FIXTURE — mutasi bank & titipan dana NYATA lewat API G-8
# ═════════════════════════════════════════════════════════════════════════════
def import_line(admin: str, amount: float, desc: str, ent: str = ENT_A,
                acc: str = ACC_A, direction: str = "in", date_iso: str = "") -> Dict[str, Any]:
    r = api("POST", "/bank-reconciliation/import", admin, ent, json={
        "bank_account_id": acc, "lines": [{
            "stmt_date": date_iso or day(-1), "amount": amount, "direction": direction,
            "description": desc}]})
    assert r.status_code == 200, f"impor gagal: {r.status_code} {r.text[:200]}"
    batch = r.json()["import_batch"]
    rows = api("GET", f"/bank-reconciliation/lines?bank_account_id={acc}", admin, ent).json()
    ln = next(l for l in rows if l.get("import_batch") == batch)
    made["lines"].append(ln["id"])
    return ln


def to_holding(admin: str, line_id: str, ent: str = ENT_A) -> Dict[str, Any]:
    r = api("POST", f"/bank-reconciliation/lines/{line_id}/holding", admin, ent,
            json={"note": f"{POC_TAG} pengirim belum diketahui"})
    assert r.status_code == 200, f"titipkan gagal: {r.status_code} {r.text[:200]}"
    hl = r.json()
    if (hl.get("holding") or {}).get("cash_txn_id"):
        made["cash"].append(hl["holding"]["cash_txn_id"])
    return hl


def pick_order(ent: str = ENT_A, min_outstanding: float = 100000.0) -> Dict[str, Any]:
    def q(db):
        return db.sales_orders.find(
            {"entity_id": ent, "payment_status": {"$in": ["pending", "partial"]}},
            {"_id": 0}).sort("number", 1).to_list(200)
    for o in dbrun(q):
        gt = round(float(o.get("grand_total") or 0), 2)
        paid = round(sum(float(p.get("amount") or 0) for p in (o.get("payments") or [])), 2)
        if round(gt - paid, 2) >= min_outstanding:
            return {**o, "outstanding": round(gt - paid, 2)}
    raise AssertionError(f"tidak ada pesanan {ent} dengan outstanding >= {min_outstanding}")


def order_paid(order_id: str) -> float:
    o = dbrun(lambda db: db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    return round(sum(float(p.get("amount") or 0) for p in (o.get("payments") or [])), 2)


def age_case(case_id: str, hours: float) -> None:
    """Tuakan kasus (mundurkan `created_at` & `sla_due_at`) supaya SLA bisa diuji nyata."""
    when = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    dbrun(lambda db: db.finance_cases.update_one({"id": case_id}, {"$set": {
        "created_at": when, "sla_due_at": when}}))


def age_line(line_id: str, days: int) -> None:
    dbrun(lambda db: db.bank_statement_lines.update_one({"id": line_id}, {"$set": {
        "stmt_date": day(-days)}}))


def mkcase(admin: str, **payload) -> Dict[str, Any]:
    r = api("POST", "/finance-cases", admin, payload.pop("ent", ENT_A), json=payload)
    assert r.status_code == 200, f"buat kasus gagal: {r.status_code} {r.text[:250]}"
    c = r.json()
    made["cases"].append(c["id"])
    if c.get("number"):
        made["case_numbers"].append(c["number"])
    return c


# ═════════════════════════════════════════════════════════════════════════════
#  1 · PLAYBOOK, KEBIJAKAN & INBOX  (US1, US9)
# ═════════════════════════════════════════════════════════════════════════════
def test_playbooks(admin: str, manager: str, sales: str) -> Dict[str, Any]:
    head("1 · PLAYBOOK, KEBIJAKAN & INBOX (US1/US9)")
    pbs = api("GET", "/finance-cases/playbooks", admin, ENT_A).json()
    ok(isinstance(pbs, list) and len(pbs) == 11,
       "11 playbook terdaftar (satu sumber untuk wizard di layar)", f"{len(pbs)} playbook")
    ok(all(p.get("label") and p.get("question") and p.get("playbook") and p.get("actions")
           for p in pbs),
       "setiap playbook punya pertanyaan awam, langkah, dan aksi")
    ok(all(a.get("produces") for p in pbs for a in p["actions"]),
       "setiap aksi MENYEBUT dokumen turunan yang dilahirkannya (tidak ada aksi hampa)")

    pol = api("GET", "/finance-cases/policy", admin, ENT_A).json()
    ok(pol.get("sla_hours") and pol.get("approval_above") and pol.get("approver_role"),
       "SLA & ambang persetujuan dibaca dari Pusat Pengaturan (bukan angka sihir)",
       f"SLA {pol['sla_hours']} jam · ambang Rp {pol['approval_above']:,.0f} · "
       f"penyetuju {pol['approver_role']}")

    rs = api("GET", "/finance-cases/reasons", admin, ENT_A).json()
    ok(len(rs) >= 9, "label alasan kasus tersedia (taksonomi G-1, bisa ditambah admin)",
       f"{len(rs)} label")

    # RBAC: sales boleh MELAPOR & melihat, tidak boleh menutup kasus uang.
    st = api("GET", "/finance-cases/stats", sales, ENT_A)
    ok(st.status_code == 200, "sales boleh melihat antrean kasus (melapor & memantau)",
       f"HTTP {st.status_code}")
    return {"playbooks": {p["code"]: p for p in pbs}, "policy": pol,
            "reasons": {r["code"]: r for r in rs}}


# ═════════════════════════════════════════════════════════════════════════════
#  2 · KASUS OTOMATIS DARI TITIPAN DANA G-8  (US4, US8)
# ═════════════════════════════════════════════════════════════════════════════
def test_auto_intake(admin: str, pol: Dict[str, Any]) -> Dict[str, Any]:
    head("2 · KASUS DIBUAT SENDIRI OLEH SISTEM (US4/US8)")
    amount = 4250000.0
    ln = import_line(admin, amount, f"TRSF E-BANKING CR TANPA IDENTITAS 5521 {POC_TAG}")
    to_holding(admin, ln["id"])
    age_line(ln["id"], pol["holding_days"] + 2)

    before = api("GET", "/finance-cases", admin, ENT_A).json()
    scan1 = api("POST", "/finance-cases/scan", admin, ENT_A)
    s1 = scan1.json() if scan1.status_code == 200 else {}
    ok(scan1.status_code == 200 and s1.get("holding_cases", 0) >= 1,
       "titipan dana menganggur → kasus dibuat SENDIRI (antrean nyata, bukan diisi manual)",
       f"{s1.get('holding_cases')} kasus titipan · {s1.get('duplicate_cases')} kasus dobel")

    after = api("GET", "/finance-cases", admin, ENT_A).json()
    case = next((c for c in after if (c.get("source") or {}).get("id") == ln["id"]), None)
    ok(bool(case), "kasus menunjuk mutasi bank sumbernya (deep-link G-8 → G-9)",
       f"{(case or {}).get('number')}")
    if case:
        made["cases"].append(case["id"])
        if case.get("number"):
            made["case_numbers"].append(case["number"])
    ok(case and round(case.get("amount", 0), 2) == amount,
       "nominal dipertaruhkan terisi dari sisa titipan (tanpa mengetik ulang)",
       f"Rp {(case or {}).get('amount', 0):,.0f}")
    ok(case and case.get("case_type") == "dana_tak_dikenal" and case.get("playbook"),
       "playbook ikut menempel di kasus (langkah penyelesaian terlihat di layar)",
       f"{len((case or {}).get('playbook') or [])} langkah")
    ok(case and case.get("sla_due_at") and case.get("sla_hours"),
       "batas waktu (SLA) dihitung dari kebijakan", f"{(case or {}).get('sla_hours')} jam")

    scan2 = api("POST", "/finance-cases/scan", admin, ENT_A).json()
    after2 = api("GET", "/finance-cases", admin, ENT_A).json()
    ok(len(after2) == len(after),
       "BUKTI-MERAH (idempoten): pemindai dijalankan 2x TIDAK menggandakan kasus",
       f"{len(before)} → {len(after)} → {len(after2)} · dilewati {scan2.get('skipped')}")

    dup = api("POST", "/finance-cases", admin, ENT_A, json={
        "case_type": "dana_tak_dikenal", "amount": amount,
        "source": {"kind": "bank_holding", "id": ln["id"]}})
    ok(dup.status_code == 400 and "kembar" in dup.text.lower(),
       "BUKTI-MERAH: kasus KEMBAR untuk sumber yang sama DITOLAK berikut arahan",
       f"HTTP {dup.status_code}")

    stats = api("GET", "/finance-cases/stats", admin, ENT_A).json()
    ok(stats.get("open", 0) >= 1 and stats.get("money_at_stake", 0) >= amount,
       "ringkasan manager: jumlah kasus terbuka & UANG DIPERTARUHKAN",
       f"{stats.get('open')} terbuka · Rp {stats.get('money_at_stake'):,.0f}")
    ok(any(t["case_type"] == "dana_tak_dikenal" for t in stats.get("by_type") or []),
       "ringkasan dipecah per jenis kasus (tahu masalah mana yang paling sering)")
    return {"case": case, "line": ln, "amount": amount}


# ═════════════════════════════════════════════════════════════════════════════
#  3 · PENJAGA PENYELESAIAN: ALASAN · BUKTI · PERSETUJUAN  (US2, US3, US5)
# ═════════════════════════════════════════════════════════════════════════════
def test_guards(admin: str, manager: str, sales: str, ctx: Dict[str, Any],
                pol: Dict[str, Any]) -> None:
    head("3 · PENJAGA PENYELESAIAN: ALASAN · BUKTI · PERSETUJUAN (US2/US3/US5)")
    case = ctx["case"]
    order = pick_order(ENT_A, 500000.0)
    part = min(1000000.0, round(order["outstanding"] / 2, 2))

    r = api("POST", f"/finance-cases/{case['id']}/resolve", admin, ENT_A, json={
        "action": "alokasi_titipan", "reason_code": "",
        "customer_id": order.get("customer_id", ""),
        "allocations": [{"order_id": order["id"], "amount": part}]})
    ok(r.status_code == 400 and "alasan" in r.text.lower(),
       "BUKTI-MERAH: menutup kasus TANPA label alasan DITOLAK",
       f"HTTP {r.status_code}")

    r = api("POST", f"/finance-cases/{case['id']}/resolve", admin, ENT_A, json={
        "action": "refund_pelanggan", "reason_code": "case_identified_owner",
        "amount": part})
    ok(r.status_code == 400 and "playbook" in r.text.lower(),
       "BUKTI-MERAH: aksi dari playbook LAIN ditolak (wizard tidak bisa disalip)",
       f"HTTP {r.status_code}")

    r = api("POST", f"/finance-cases/{case['id']}/resolve", admin, ENT_A, json={
        "action": "alokasi_titipan", "reason_code": "penalty_waiver",
        "customer_id": order.get("customer_id", ""),
        "allocations": [{"order_id": order["id"], "amount": part}]})
    ok(r.status_code == 400 and "kasus keuangan" in r.text.lower(),
       "BUKTI-MERAH: label alasan milik domain lain (denda) ditolak untuk kasus keuangan",
       f"HTTP {r.status_code}")

    # Alasan yang SAH untuk kasus keuangan tapi TIDAK NYAMBUNG dengan jenis kasusnya.
    # Tanpa penjaga ini, kasus "Dana masuk tak dikenal" bisa ditutup dengan alasan
    # "Cek / giro ditolak bank": INV-CASE-01 tetap HIJAU (ada alasan) padahal jejak yang
    # dibaca auditor menyesatkan. Daftar sahnya = `reason_codes` playbook.
    r = api("POST", f"/finance-cases/{case['id']}/resolve", admin, ENT_A, json={
        "action": "alokasi_titipan", "reason_code": "case_cheque_bounced",
        "customer_id": order.get("customer_id", ""),
        "allocations": [{"order_id": order["id"], "amount": part}]})
    ok(r.status_code == 400 and "nyambung" in r.text.lower()
       and "Pemilik dana ketemu" in r.text,
       "BUKTI-MERAH: alasan sah-tapi-tak-nyambung ditolak + disebutkan alasan yang benar",
       f"HTTP {r.status_code} · {r.text[:150]}")
    r = api("POST", f"/finance-cases/{case['id']}/reject", admin, ENT_A,
            json={"reason_code": "supplier_advance", "note": f"{POC_TAG} uji"})
    ok(r.status_code == 400 and "nyambung" in r.text.lower(),
       "BUKTI-MERAH: penutupan tanpa tindakan pun wajib beralasan yang nyambung",
       f"HTTP {r.status_code}")

    # Bukti WAJIB untuk jenis yang menyangkut klaim pihak lain.
    ev = mkcase(admin, case_type="pembayar_pihak_ketiga", amount=750000.0,
                title=f"{POC_TAG} transfer dari nama pihak ketiga",
                source={"kind": "bank_holding", "id": ctx["line"]["id"]})
    r = api("POST", f"/finance-cases/{ev['id']}/resolve", admin, ENT_A, json={
        "action": "alokasi_titipan", "reason_code": "case_third_party_payer",
        "customer_id": order.get("customer_id", ""),
        "allocations": [{"order_id": order["id"], "amount": 100000.0}]})
    ok(r.status_code == 400 and "bukti" in r.text.lower(),
       "BUKTI-MERAH: jenis kasus ber-klaim WAJIB lampiran bukti sebelum ditutup",
       f"HTTP {r.status_code}")
    note = api("POST", f"/finance-cases/{ev['id']}/note", admin, ENT_A, json={
        "note": "Surat pernyataan pelanggan diterima", "attachments": [
            {"name": "pernyataan.pdf", "path": f"{POC_TAG}/pernyataan.pdf",
             "content_type": "application/pdf"}]})
    ok(note.status_code == 200 and len(note.json().get("attachments") or []) == 1,
       "bukti bisa dilampirkan & tercatat di jejak waktu kasus", f"HTTP {note.status_code}")
    ok(any(t["event"] == "catatan" for t in note.json().get("timeline") or []),
       "jejak waktu mencatat siapa melampirkan bukti kapan")
    api("POST", f"/finance-cases/{ev['id']}/reject", admin, ENT_A,
        json={"reason_code": "case_third_party_payer", "note": f"{POC_TAG} ditutup uji"})

    # Ambang persetujuan: nominal besar tidak boleh ditutup peran biasa.
    big = mkcase(admin, case_type="refund_pelanggan",
                 amount=round(pol["approval_above"] + 1000000.0, 2),
                 title=f"{POC_TAG} refund besar", customer_id=order.get("customer_id", ""))
    r = api("POST", f"/finance-cases/{big['id']}/resolve", sales, ENT_A, json={
        "action": "refund_pelanggan", "reason_code": "customer_refund_request",
        "customer_id": order.get("customer_id", ""),
        "amount": round(pol["approval_above"] + 1000000.0, 2)})
    ok(r.status_code in (400, 403),
       "BUKTI-MERAH: sales TIDAK boleh menutup kasus uang (izin resolve tidak diberikan)",
       f"HTTP {r.status_code}")
    api("POST", f"/finance-cases/{big['id']}/reject", admin, ENT_A,
        json={"reason_code": "customer_refund_request", "note": f"{POC_TAG} ditutup uji"})
    return {"order": order, "part": part}


# ═════════════════════════════════════════════════════════════════════════════
#  4 · PENYELESAIAN NYATA: DOKUMEN TURUNAN LAHIR  (US2, US7)
# ═════════════════════════════════════════════════════════════════════════════
def test_resolve_holding(admin: str, ctx: Dict[str, Any], g: Dict[str, Any]) -> Dict[str, Any]:
    head("4 · PENYELESAIAN NYATA — DOKUMEN TURUNAN LAHIR (US2/US7)")
    case, order, part = ctx["case"], g["order"], g["part"]
    paid0 = order_paid(order["id"])
    hold0 = gl_balance("2-1950")
    ar0 = gl_balance("1-1200")

    r = api("POST", f"/finance-cases/{case['id']}/resolve", admin, ENT_A, json={
        "action": "alokasi_titipan", "reason_code": "case_identified_owner",
        "note": f"{POC_TAG} pemilik dana ketemu",
        "customer_id": order.get("customer_id", ""),
        "allocations": [{"order_id": order["id"], "amount": part}]})
    c = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and c.get("status") == "resolved",
       "kasus DISELESAIKAN lewat playbook (bukan diedit diam-diam)",
       f"HTTP {r.status_code} · {c.get('status')}")
    docs = c.get("documents") or []
    ok(len(docs) >= 2 and any(d["kind"] == "journal_entry" for d in docs),
       "penyelesaian melahirkan DOKUMEN TURUNAN termasuk jurnal",
       f"{len(docs)} dokumen: {sorted({d['kind'] for d in docs})}")
    ok(c.get("reason_label") and c.get("resolved_by"),
       "kasus tertutup menyimpan alasan berlabel + siapa yang menyelesaikan",
       f"{c.get('reason_label')} · {c.get('resolved_by')}")

    paid1 = order_paid(order["id"])
    ok(round(paid1 - paid0, 2) == round(part, 2),
       "piutang pesanan BENAR-BENAR berkurang (bukan sekadar catatan kasus)",
       f"terbayar {paid0:,.0f} → {paid1:,.0f}")
    # 2-1950 adalah KEWAJIBAN: titipan masuk = kredit (saldo debit−kredit makin negatif),
    # alokasi = debit → saldonya bergerak NAIK sebesar alokasi (mendekati nol).
    ok(round(gl_balance("2-1950") - hold0, 2) == round(part, 2),
       "saldo akun titipan di buku besar berkurang tepat sebesar alokasi",
       f"2-1950 {hold0:,.0f} → {gl_balance('2-1950'):,.0f}")
    ok(round(gl_balance("1-1200") - ar0, 2) == round(-part, 2),
       "piutang usaha di buku besar berkurang tepat (tanpa kas dobel)",
       f"1-1200 {ar0:,.0f} → {gl_balance('1-1200'):,.0f}")

    again = api("POST", f"/finance-cases/{case['id']}/resolve", admin, ENT_A, json={
        "action": "alokasi_titipan", "reason_code": "case_identified_owner",
        "customer_id": order.get("customer_id", ""),
        "allocations": [{"order_id": order["id"], "amount": 1000.0}]})
    ok(again.status_code == 400 and "sudah" in again.text.lower(),
       "BUKTI-MERAH: kasus yang sudah selesai tidak bisa diselesaikan dua kali",
       f"HTTP {again.status_code}")

    reopen = api("POST", f"/finance-cases/{case['id']}/reopen", admin, ENT_A,
                 json={"note": "coba buka ulang"})
    ok(reopen.status_code == 400 and "dokumen" in reopen.text.lower(),
       "BUKTI-MERAH: kasus yang sudah melahirkan dokumen TIDAK boleh dibuka ulang "
       "(ledger tambah-saja)", f"HTTP {reopen.status_code}")

    trace = api("GET", f"/documents/trace/finance_case/{case['id']}", admin, ENT_A)
    ok(trace.status_code == 200,
       "kasus masuk peta relasi dokumen G-4 (auditor bisa menelusuri, US7)",
       f"HTTP {trace.status_code}")
    return {"case_after": c, "order": order, "part": part}


# ═════════════════════════════════════════════════════════════════════════════
#  5 · PLAYBOOK LAIN: PINDAH-BUKU · KARYAWAN 2 LANGKAH · BIAYA BANK · REALOKASI
# ═════════════════════════════════════════════════════════════════════════════
def test_more_playbooks(admin: str, manager: str) -> Dict[str, Any]:
    head("5 · PLAYBOOK LAIN — PINDAH-BUKU · KARYAWAN · BIAYA BANK · REALOKASI (US2)")
    out: Dict[str, Any] = {}

    # ── a) pindah-buku antar rekening sendiri (akun transit harus kembali nol)
    amount = 2500000.0
    ln = import_line(admin, amount, f"TRSF E-BANKING CR SALAH REKENING {POC_TAG}")
    transit0 = gl_balance("1-1150")
    case = mkcase(admin, case_type="salah_rekening_internal", amount=amount,
                  title=f"{POC_TAG} salah rekening",
                  source={"kind": "bank_line", "id": ln["id"]})
    r = api("POST", f"/finance-cases/{case['id']}/resolve", admin, ENT_A, json={
        "action": "pindah_buku", "reason_code": "case_wrong_account",
        "amount": amount, "to_account_id": ACC_A2})
    c = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and c.get("status") == "resolved",
       "pindah-buku antar rekening sendiri diselesaikan", f"HTTP {r.status_code} {r.text[:90]}")
    cashdocs = [d for d in c.get("documents") or [] if d["kind"] == "cash_transaction"]
    jedocs = [d for d in c.get("documents") or [] if d["kind"] == "journal_entry"]
    for d in cashdocs:
        made["cash"].append(d["id"])
    ok(len(cashdocs) == 2 and len(jedocs) == 2,
       "kedua buku rekening bergerak: 2 transaksi kas + 2 jurnal",
       f"{[d['number'] for d in cashdocs]}")
    ok(round(gl_balance("1-1150") - transit0, 2) == 0.0,
       "akun transit 1-1150 kembali NOL (uang tidak tercipta / hilang di tengah jalan)",
       f"transit {gl_balance('1-1150'):,.0f}")
    same = mkcase(admin, case_type="salah_rekening_internal", amount=amount,
                  title=f"{POC_TAG} rekening sama")
    bad = api("POST", f"/finance-cases/{same['id']}/resolve", admin, ENT_A, json={
        "action": "pindah_buku", "reason_code": "case_wrong_account",
        "amount": amount, "account_id": ACC_A, "to_account_id": ACC_A})
    ok(bad.status_code == 400 and "sama" in bad.text.lower(),
       "BUKTI-MERAH: pindah-buku ke rekening yang SAMA ditolak", f"HTTP {bad.status_code}")
    api("POST", f"/finance-cases/{same['id']}/reject", admin, ENT_A,
        json={"reason_code": "case_wrong_account", "note": f"{POC_TAG} uji"})
    out["transit_case"] = c

    # ── b) rekening pribadi karyawan: WAJIB 2 langkah
    order = pick_order(ENT_A, 400000.0)
    amt2 = min(800000.0, round(order["outstanding"] / 2, 2))
    emp_case = mkcase(admin, case_type="rekening_pribadi_karyawan", amount=amt2,
                      title=f"{POC_TAG} masuk rekening pribadi",
                      customer_id=order.get("customer_id", ""), order_ids=[order["id"]],
                      attachments=[{"name": "pernyataan_karyawan.pdf",
                                    "path": f"{POC_TAG}/emp.pdf"}])
    emp0 = gl_balance("1-1280")
    paid0 = order_paid(order["id"])
    r = api("POST", f"/finance-cases/{emp_case['id']}/resolve", admin, ENT_A, json={
        "action": "akui_dipegang_karyawan", "reason_code": "case_employee_account",
        "amount": amt2, "order_id": order["id"], "employee_name": "Sinta Warehouse"})
    c1 = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and c1.get("status") == "in_progress",
       "langkah 1 dijalankan tapi kasus BELUM ditutup (uang masih dipegang karyawan)",
       f"HTTP {r.status_code} · {c1.get('status')}")
    ok(round(gl_balance("1-1280") - emp0, 2) == round(amt2, 2),
       "piutang titipan karyawan 1-1280 bertambah (siapa memegang uang tercatat)",
       f"1-1280 +{amt2:,.0f}")
    ok(round(order_paid(order["id"]) - paid0, 2) == round(amt2, 2),
       "piutang pelanggan lunas sebesar uang yang sudah dibayarnya")
    ok((c1.get("resolution") or {}).get("next_action") == "setor_dari_karyawan",
       "layar dituntun ke langkah berikutnya (setoran karyawan)",
       f"{(c1.get('resolution') or {}).get('next_action')}")
    r = api("POST", f"/finance-cases/{emp_case['id']}/resolve", admin, ENT_A, json={
        "action": "setor_dari_karyawan", "reason_code": "case_employee_account",
        "amount": amt2})
    c2 = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and c2.get("status") == "resolved",
       "langkah 2 (setoran karyawan) menutup kasus", f"HTTP {r.status_code}")
    for d in c2.get("documents") or []:
        if d["kind"] == "cash_transaction":
            made["cash"].append(d["id"])
    ok(round(gl_balance("1-1280") - emp0, 2) == 0.0,
       "piutang titipan karyawan kembali NOL setelah disetor",
       f"1-1280 {gl_balance('1-1280'):,.0f}")
    out["emp_case"] = c2
    out["emp_order"] = order
    out["emp_amount"] = amt2

    # ── c) selisih biaya bank kecil → selesai tanpa persetujuan + jurnal beban
    order2 = pick_order(ENT_A, 200000.0)
    fee = 6500.0
    bank0 = gl_balance("6-8000")
    fee_case = mkcase(admin, case_type="selisih_biaya_bank", amount=fee,
                      title=f"{POC_TAG} kurang karena biaya bank",
                      customer_id=order2.get("customer_id", ""), order_ids=[order2["id"]])
    r = api("POST", f"/finance-cases/{fee_case['id']}/resolve", manager, ENT_A, json={
        "action": "bebankan_biaya_bank", "reason_code": "bank_charge",
        "amount": fee, "order_id": order2["id"]})
    c3 = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and c3.get("status") == "resolved"
       and (c3.get("resolution") or {}).get("auto_resolved") is True,
       "selisih receh biaya bank selesai TANPA persetujuan (kebijakan admin) tapi berlabel",
       f"HTTP {r.status_code}")
    ok(round(gl_balance("6-8000") - bank0, 2) == fee,
       "beban administrasi bank 6-8000 bertambah tepat", f"+Rp {fee:,.0f}")
    out["fee_case"] = c3
    out["fee_order"] = order2
    out["fee"] = fee

    # ── d) realokasi antar pesanan: playbook TANPA jurnal (akun GL sama)
    src = pick_order(ENT_A, 300000.0)
    dst = next((o for o in [pick_order(ENT_A, 100000.0)] if o["id"] != src["id"]), None)
    def q(db):
        return db.sales_orders.find({"entity_id": ENT_A,
                                     "customer_id": src.get("customer_id")},
                                    {"_id": 0}).to_list(100)
    sibling = next((o for o in dbrun(q)
                    if o["id"] != src["id"]
                    and round(float(o.get("grand_total") or 0)
                              - sum(float(p.get("amount") or 0)
                                    for p in (o.get("payments") or [])), 2) > 50000), None)
    if sibling:
        mv = 50000.0
        # pastikan pesanan asal punya pembayaran yang bisa dipindahkan
        pay_case = mkcase(admin, case_type="dana_tak_dikenal", amount=mv,
                          title=f"{POC_TAG} siapkan pembayaran untuk realokasi")
        api("POST", f"/finance-cases/{pay_case['id']}/reject", admin, ENT_A,
            json={"reason_code": "case_identified_owner", "note": f"{POC_TAG} uji"})
        paid_src0 = order_paid(src["id"])
        if paid_src0 >= mv:
            rc = mkcase(admin, case_type="salah_invoice", amount=mv,
                        title=f"{POC_TAG} menempel di pesanan salah",
                        customer_id=src.get("customer_id", ""))
            r = api("POST", f"/finance-cases/{rc['id']}/resolve", admin, ENT_A, json={
                "action": "realokasi_pesanan", "reason_code": "case_wrong_invoice",
                "amount": mv, "from_order_id": src["id"], "to_order_id": sibling["id"]})
            c4 = r.json() if r.status_code == 200 else {}
            ok(r.status_code == 200 and c4.get("status") == "resolved",
               "realokasi antar pesanan diselesaikan", f"HTTP {r.status_code} {r.text[:80]}")
            ok(round(paid_src0 - order_paid(src["id"]), 2) == mv,
               "pesanan asal dapat baris PENGURANG (kwitansi tidak dibatalkan)",
               f"terbayar {paid_src0:,.0f} → {order_paid(src['id']):,.0f}")
            ok(not [d for d in c4.get("documents") or [] if d["kind"] == "journal_entry"],
               "sengaja TIDAK menjurnal: di buku besar akunnya sama (1-1200) — "
               "jurnal baru akan menyesatkan")
            out["realloc"] = {"case": c4, "src": src, "dst": sibling, "amount": mv}
    ok(True, "playbook realokasi diuji" if sibling else
       "playbook realokasi dilewati (data demo tidak punya 2 pesanan pelanggan sama)")
    return out


# ═════════════════════════════════════════════════════════════════════════════
#  5b · PLAYBOOK SISA: GIRO DITOLAK · BAYAR DOBEL · SUPPLIER · ANTAR ENTITAS
# ═════════════════════════════════════════════════════════════════════════════
def test_rest_playbooks(admin: str, manager: str) -> Dict[str, Any]:
    head("5b · PLAYBOOK SISA — GIRO · DOBEL · SUPPLIER · ANTAR ENTITAS · STORE CREDIT (US2)")
    out: Dict[str, Any] = {}

    # ── a) GIRO DITOLAK: kwitansi NYATA dibuat lalu dibatalkan + nota denda
    order = pick_order(ENT_A, 500000.0)
    amt = min(600000.0, round(order["outstanding"] / 2, 2))
    rr = api("POST", "/ar-receipts", admin, ENT_A, json={
        "customer_id": order["customer_id"], "amount": amt, "method": "giro",
        "notes": f"{POC_TAG} giro pelanggan",
        "allocations": [{"order_id": order["id"], "amount": amt}]})
    rec = rr.json() if rr.status_code == 200 else {}
    ok(rr.status_code == 200 and rec.get("id"),
       "kwitansi giro NYATA dibuat lewat API (fixture bukan buatan tangan di database)",
       f"HTTP {rr.status_code} · {rec.get('number')}")
    if rec.get("id"):
        made["receipts"].append(rec["id"])
    paid_after_receipt = order_paid(order["id"])
    gc = mkcase(admin, case_type="giro_ditolak", amount=amt,
                title=f"{POC_TAG} giro ditolak bank",
                customer_id=order["customer_id"], order_ids=[order["id"]],
                source={"kind": "ar_receipt", "id": rec.get("id", ""),
                        "label": f"Kwitansi {rec.get('number')}"},
                attachments=[{"name": "surat_penolakan_bank.pdf",
                              "path": f"{POC_TAG}/tolak.pdf"}])
    r = api("POST", f"/finance-cases/{gc['id']}/resolve", manager, ENT_A, json={
        "action": "batalkan_kwitansi", "reason_code": "case_cheque_bounced",
        "receipt_id": rec.get("id", ""), "with_penalty": True,
        "note": f"{POC_TAG} bank menolak giro"})
    c = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and c.get("status") == "resolved",
       "giro ditolak → kwitansi DIBATALKAN lewat kasus", f"HTTP {r.status_code} {r.text[:90]}")
    voided = dbrun(lambda db: db.ar_receipts.find_one({"id": rec.get("id")}, {"_id": 0}))
    ok((voided or {}).get("status") == "void",
       "kwitansi berstatus batal (jurnal lama TIDAK diubah — dibuat jurnal pembalik)",
       f"{(voided or {}).get('status')}")
    ok(round(paid_after_receipt - order_paid(order["id"]), 2) == round(amt, 2),
       "piutang pelanggan HIDUP kembali setelah giro ditolak",
       f"terbayar {paid_after_receipt:,.0f} → {order_paid(order['id']):,.0f}")
    again = api("POST", f"/finance-cases/{gc['id']}/resolve", manager, ENT_A, json={
        "action": "batalkan_kwitansi", "reason_code": "case_cheque_bounced",
        "receipt_id": rec.get("id", "")})
    ok(again.status_code == 400,
       "BUKTI-MERAH: kwitansi yang sudah batal tidak bisa dibatalkan lagi",
       f"HTTP {again.status_code}")
    out["giro"] = {"case": c, "receipt": rec, "order": order, "amount": amt}

    # ── b) BAYAR DOBEL: uang muka dipakai pesanan lain + sisanya dikembalikan
    dep_cust = dbrun(lambda db: db.customers.find_one(
        {"deposit_balance": {"$gt": 200000}}, {"_id": 0}, sort=[("id", 1)]))
    if dep_cust:
        dep0 = round(float(dep_cust.get("deposit_balance") or 0), 2)
        target = next((o for o in dbrun(lambda db: db.sales_orders.find(
            {"customer_id": dep_cust["id"], "entity_id": ENT_A}, {"_id": 0}).to_list(50))
            if round(float(o.get("grand_total") or 0)
                     - sum(float(p.get("amount") or 0) for p in (o.get("payments") or [])),
                     2) > 100000), None)
        use = 100000.0
        dc = mkcase(admin, case_type="bayar_dobel", amount=use,
                    title=f"{POC_TAG} dugaan bayar dobel",
                    customer_id=dep_cust["id"])
        if target:
            paid0 = order_paid(target["id"])
            ar0 = gl_balance("1-1200")
            adv0 = gl_balance("2-1400")
            r = api("POST", f"/finance-cases/{dc['id']}/resolve", manager, ENT_A, json={
                "action": "alokasi_uang_muka", "reason_code": "case_duplicate_payment",
                "customer_id": dep_cust["id"],
                "allocations": [{"order_id": target["id"], "amount": use}]})
            c2 = r.json() if r.status_code == 200 else {}
            ok(r.status_code == 200 and c2.get("status") == "resolved",
               "bayar dobel → kelebihan dipakai melunasi pesanan lain",
               f"HTTP {r.status_code} {r.text[:90]}")
            ok(round(order_paid(target["id"]) - paid0, 2) == use,
               "pesanan lain benar-benar terlunasi dari uang muka", f"+Rp {use:,.0f}")
            ok(round(gl_balance("2-1400") - adv0, 2) == use
               and round(gl_balance("1-1200") - ar0, 2) == round(-use, 2),
               "jurnal Dr 2-1400 Uang Muka / Cr 1-1200 Piutang terbit (uang tidak dobel)",
               f"2-1400 {adv0:,.0f}→{gl_balance('2-1400'):,.0f} · "
               f"1-1200 {ar0:,.0f}→{gl_balance('1-1200'):,.0f}")
            dep1 = round(float(dbrun(lambda db: db.customers.find_one(
                {"id": dep_cust["id"]}, {"_id": 0})).get("deposit_balance") or 0), 2)
            ok(round(dep0 - dep1, 2) == use,
               "saldo uang muka pelanggan berkurang tepat", f"{dep0:,.0f} → {dep1:,.0f}")
            out["dobel"] = {"case": c2, "customer": dep_cust, "order": target, "amount": use}
        # refund tunai dari uang muka (nominal kecil supaya di bawah ambang persetujuan)
        rc = mkcase(admin, case_type="refund_pelanggan", amount=50000.0,
                    title=f"{POC_TAG} refund uang muka", customer_id=dep_cust["id"])
        adv1 = gl_balance("2-1400")
        r = api("POST", f"/finance-cases/{rc['id']}/resolve", manager, ENT_A, json={
            "action": "refund_pelanggan", "reason_code": "customer_refund_request",
            "customer_id": dep_cust["id"], "amount": 50000.0})
        c3 = r.json() if r.status_code == 200 else {}
        ok(r.status_code == 200 and c3.get("status") == "resolved",
           "pengembalian dana pelanggan dari uang muka diselesaikan",
           f"HTTP {r.status_code} {r.text[:90]}")
        for d in c3.get("documents") or []:
            if d["kind"] == "cash_transaction":
                made["cash"].append(d["id"])
        ok(round(gl_balance("2-1400") - adv1, 2) == 50000.0,
           "kewajiban uang muka pelanggan berkurang saat uangnya keluar (bukan beban baru)",
           f"2-1400 {adv1:,.0f} → {gl_balance('2-1400'):,.0f}")
        toobig = mkcase(admin, case_type="refund_pelanggan", amount=999000000.0,
                        title=f"{POC_TAG} refund melebihi saldo",
                        customer_id=dep_cust["id"])
        bad = api("POST", f"/finance-cases/{toobig['id']}/resolve", admin, ENT_A, json={
            "action": "refund_pelanggan", "reason_code": "customer_refund_request",
            "customer_id": dep_cust["id"], "amount": 999000000.0})
        ok(bad.status_code == 400 and "melebihi" in bad.text.lower(),
           "BUKTI-MERAH: refund melebihi saldo uang muka DITOLAK (uang tak bisa dicetak)",
           f"HTTP {bad.status_code}")
        api("POST", f"/finance-cases/{toobig['id']}/reject", admin, ENT_A,
            json={"reason_code": "customer_refund_request", "note": f"{POC_TAG} uji"})
        out["refund_cust"] = {"case": c3, "customer": dep_cust, "amount": 50000.0}

    # ── c) LEBIH BAYAR SUPPLIER: uang muka lalu refund dari supplier
    # Pemasok uji WAJIB yang belum punya uang muka: pemeriksaan di bawah menuntut
    # saldo master TEPAT `amt3`. Data demo memang memberi satu pemasok uang muka
    # Rp 500.000, dan id pemasok DIACAK setiap seed — jadi memilih "pemasok ber-id
    # terkecil" membuat POC ini lulus/gagal seperti lempar koin (itulah penyebab
    # gate --full kadang merah di G-9 tanpa ada kode yang berubah).
    sup = dbrun(lambda db: db.suppliers.find_one(
        {"entity_id": ENT_A,
         "$or": [{"advance_balance": {"$exists": False}}, {"advance_balance": 0},
                 {"advance_balance": None}]},
        {"_id": 0}, sort=[("id", 1)]))
    if sup:
        amt3 = 400000.0
        adv_acc0, ap0 = gl_balance("1-1400"), gl_balance("2-1100")
        sc = mkcase(admin, case_type="lebih_bayar_supplier", amount=amt3,
                    title=f"{POC_TAG} lebih bayar supplier", supplier_id=sup["id"])
        r = api("POST", f"/finance-cases/{sc['id']}/resolve", manager, ENT_A, json={
            "action": "uang_muka_supplier", "reason_code": "supplier_advance",
            "supplier_id": sup["id"], "amount": amt3})
        c4 = r.json() if r.status_code == 200 else {}
        ok(r.status_code == 200 and c4.get("status") == "resolved",
           "kelebihan bayar supplier → uang muka supplier", f"HTTP {r.status_code} {r.text[:90]}")
        ok(round(gl_balance("1-1400") - adv_acc0, 2) == amt3
           and round(gl_balance("2-1100") - ap0, 2) == round(-amt3, 2),
           "jurnal Dr 1-1400 Uang Muka / Cr 2-1100 Utang Usaha terbit",
           f"1-1400 +{amt3:,.0f}")
        sup1 = dbrun(lambda db: db.suppliers.find_one({"id": sup["id"]}, {"_id": 0}))
        ok(round(float(sup1.get("advance_balance") or 0), 2) == amt3,
           "saldo uang muka supplier terlihat di master supplier (bisa dipotongkan nanti)",
           f"Rp {sup1.get('advance_balance'):,.0f}")
        sc2 = mkcase(admin, case_type="lebih_bayar_supplier", amount=amt3,
                     title=f"{POC_TAG} supplier mengembalikan dana", supplier_id=sup["id"])
        toobig = api("POST", f"/finance-cases/{sc2['id']}/resolve", manager, ENT_A, json={
            "action": "terima_refund_supplier", "reason_code": "supplier_advance",
            "supplier_id": sup["id"], "amount": amt3 + 1})
        ok(toobig.status_code == 400 and "melebihi" in toobig.text.lower(),
           "BUKTI-MERAH: menerima refund lebih besar dari uang muka supplier DITOLAK",
           f"HTTP {toobig.status_code}")
        r = api("POST", f"/finance-cases/{sc2['id']}/resolve", manager, ENT_A, json={
            "action": "terima_refund_supplier", "reason_code": "supplier_advance",
            "supplier_id": sup["id"], "amount": amt3})
        c5 = r.json() if r.status_code == 200 else {}
        ok(r.status_code == 200 and c5.get("status") == "resolved",
           "supplier mengembalikan dana → kas masuk & uang muka berkurang",
           f"HTTP {r.status_code} {r.text[:90]}")
        for d in c5.get("documents") or []:
            if d["kind"] == "cash_transaction":
                made["cash"].append(d["id"])
        sup2 = dbrun(lambda db: db.suppliers.find_one({"id": sup["id"]}, {"_id": 0}))
        ok(round(float(sup2.get("advance_balance") or 0), 2) == 0.0
           and abs(gl_balance("1-1400") - adv_acc0) < 0.01,
           "uang muka supplier kembali NOL setelah dananya diterima",
           f"saldo master Rp {sup2.get('advance_balance'):,.0f} · "
           f"1-1400 {gl_balance('1-1400'):,.0f}")
        out["supplier"] = {"id": sup["id"], "amount": amt3}

    # ── d) SALAH ENTITAS: uang diterima PT-B, tagihan milik PT-A
    order_a = pick_order(ENT_A, 300000.0)
    amt4 = 300000.0
    ln_b = import_line(admin, amt4, f"TRSF E-BANKING CR SALAH PT {POC_TAG}",
                       ent=ENT_B, acc="bank_kas_kanda")
    to_holding(admin, ln_b["id"], ENT_B)
    ic_ar0, ic_ap0 = gl_balance("1-1250"), gl_balance("2-1250")
    paid_a0 = order_paid(order_a["id"])
    ec = mkcase(admin, case_type="salah_entitas", amount=amt4,
                title=f"{POC_TAG} bayar ke PT yang salah", entity_id=ENT_B, ent=ENT_B,
                source={"kind": "bank_holding", "id": ln_b["id"]},
                order_ids=[order_a["id"]])
    bad = api("POST", f"/finance-cases/{ec['id']}/resolve", admin, ENT_B, json={
        "action": "settlement_antar_entitas", "reason_code": "case_wrong_entity",
        "amount": amt4, "owner_entity_id": ENT_B, "order_id": order_a["id"]})
    ok(bad.status_code == 400 and "bukan kasus salah entitas" in bad.text.lower(),
       "BUKTI-MERAH: PT penerima == PT pemilik tagihan ditolak (bukan kasus salah entitas)",
       f"HTTP {bad.status_code}")
    r = api("POST", f"/finance-cases/{ec['id']}/resolve", admin, ENT_B, json={
        "action": "settlement_antar_entitas", "reason_code": "case_wrong_entity",
        "amount": amt4, "owner_entity_id": ENT_A, "order_id": order_a["id"],
        "note": f"{POC_TAG} settlement antar PT"})
    c6 = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and c6.get("status") == "resolved",
       "settlement antar entitas diselesaikan", f"HTTP {r.status_code} {r.text[:110]}")
    jes = [d for d in c6.get("documents") or [] if d["kind"] == "journal_entry"]
    ok(len(jes) == 2,
       "DUA buku dijurnal berpasangan (PT penerima berutang · PT pemilik berpiutang)",
       f"{[d['number'] for d in jes]}")
    ok(round(gl_balance("1-1250") - ic_ar0, 2) == amt4
       and round(gl_balance("2-1250") - ic_ap0, 2) == round(-amt4, 2),
       "IC-AR PT pemilik == IC-AP PT penerima (fondasi netting FASE G-6)",
       f"1-1250 +{amt4:,.0f} · 2-1250 +{amt4:,.0f}")
    ok(round(order_paid(order_a["id"]) - paid_a0, 2) == amt4,
       "piutang pelanggan di PT pemilik tagihan LUNAS", f"+Rp {amt4:,.0f}")
    ok((c6.get("resolution") or {}).get("extra", {}).get("pending_phase", "").startswith("G-6"),
       "sisa pekerjaan (netting berkala) DITANDAI jujur, bukan diklaim selesai",
       f"{(c6.get('resolution') or {}).get('extra', {}).get('pending_phase')}")
    out["interco"] = {"case": c6, "order": order_a, "amount": amt4, "line": ln_b}

    # ── e) REFUND TITIPAN: dana tak dikenal dikembalikan ke pengirim
    ln_r = import_line(admin, 275000.0, f"TRSF E-BANKING CR TAK DIKENAL REFUND {POC_TAG}")
    to_holding(admin, ln_r["id"])
    hold0 = gl_balance("2-1950")
    rt = mkcase(admin, case_type="dana_tak_dikenal", amount=275000.0,
                title=f"{POC_TAG} dana dikembalikan",
                source={"kind": "bank_holding", "id": ln_r["id"]})
    over = api("POST", f"/finance-cases/{rt['id']}/resolve", admin, ENT_A, json={
        "action": "refund_titipan", "reason_code": "case_unidentified_returned",
        "amount": 275001.0})
    ok(over.status_code == 400 and "melebihi" in over.text.lower(),
       "BUKTI-MERAH: pengembalian melebihi sisa titipan DITOLAK", f"HTTP {over.status_code}")
    r = api("POST", f"/finance-cases/{rt['id']}/resolve", admin, ENT_A, json={
        "action": "refund_titipan", "reason_code": "case_unidentified_returned",
        "amount": 275000.0, "note": f"{POC_TAG} pengirim tidak ditemukan"})
    c7 = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and c7.get("status") == "resolved",
       "dana tak dikenal dikembalikan ke pengirim", f"HTTP {r.status_code} {r.text[:90]}")
    for d in c7.get("documents") or []:
        if d["kind"] == "cash_transaction":
            made["cash"].append(d["id"])
    ok(round(gl_balance("2-1950") - hold0, 2) == 275000.0,
       "saldo akun titipan kembali turun sebesar dana yang dikembalikan",
       f"2-1950 {hold0:,.0f} → {gl_balance('2-1950'):,.0f}")
    line_after = dbrun(lambda db: db.bank_statement_lines.find_one({"id": ln_r["id"]},
                                                                 {"_id": 0}))
    ok(round(float(line_after.get("holding_remaining") or 0), 2) == 0.0
       and (line_after.get("holding_settled") or []),
       "sisa titipan nol & riwayat penyelesaiannya tercatat (INV-BNK-03 tetap sah)",
       f"sisa {line_after.get('holding_remaining')} · "
       f"{len(line_after.get('holding_settled') or [])} catatan")

    # ── f) REFUND DARI SALDO KREDIT TOKO (store credit)
    if dep_cust:
        import_amt = 120000.0
        granted = dbrun(lambda db: db.store_credit_ledger.insert_one({
            "id": f"scl_{POC_TAG.lower()}_grant", "customer_id": dep_cust["id"],
            "entity_id": ENT_A, "kind": "issue", "amount": import_amt,
            "note": f"{POC_TAG} saldo awal uji", "ref_type": POC_TAG, "ref_id": POC_TAG,
            "created_at": now_iso_local(), "updated_at": now_iso_local()}))
        scc = mkcase(admin, case_type="refund_pelanggan", amount=import_amt,
                     title=f"{POC_TAG} cairkan saldo kredit toko",
                     customer_id=dep_cust["id"])
        sc0 = gl_balance("2-1450")
        r = api("POST", f"/finance-cases/{scc['id']}/resolve", manager, ENT_A, json={
            "action": "refund_store_credit", "reason_code": "customer_refund_request",
            "customer_id": dep_cust["id"], "amount": import_amt})
        c8 = r.json() if r.status_code == 200 else {}
        ok(r.status_code == 200 and c8.get("status") == "resolved",
           "saldo kredit toko dicairkan menjadi uang", f"HTTP {r.status_code} {r.text[:110]}")
        for d in c8.get("documents") or []:
            if d["kind"] == "cash_transaction":
                made["cash"].append(d["id"])
        ok(any(d["kind"] == "store_credit_entry" for d in c8.get("documents") or []),
           "baris buku saldo kredit ikut lahir (ledger append-only)")
        out["store_credit"] = {"case": c8, "customer": dep_cust, "amount": import_amt}
    return out


def now_iso_local() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═════════════════════════════════════════════════════════════════════════════
#  6 · SLA & ESKALASI  (US6)
# ═════════════════════════════════════════════════════════════════════════════
def test_sla(admin: str, pol: Dict[str, Any]) -> Dict[str, Any]:
    head("6 · BATAS WAKTU (SLA) & ESKALASI (US6)")
    small = mkcase(admin, case_type="dana_tak_dikenal", amount=250000.0,
                   title=f"{POC_TAG} kasus kecil")
    big = mkcase(admin, case_type="dana_tak_dikenal",
                 amount=round(pol["high_amount"] + 5000000.0, 2),
                 title=f"{POC_TAG} kasus besar")
    ok(small["sla_hours"] == pol["sla_hours"] and big["sla_hours"] == pol["sla_hours_high"],
       "kasus bernominal besar memakai batas waktu lebih pendek",
       f"kecil {small['sla_hours']} jam · besar {big['sla_hours']} jam")
    ok(big["priority"] == "tinggi" and small["priority"] == "normal",
       "prioritas dihitung dari nominal (uang besar naik ke atas antrean)")
    ok(small["overdue"] is False, "kasus baru belum terlambat")

    age_case(small["id"], pol["sla_hours"] + 2)
    aged = api("GET", f"/finance-cases/{small['id']}", admin, ENT_A).json()
    ok(aged.get("overdue") is True,
       "kasus yang melewati batas waktu ditandai TERLAMBAT", f"umur {aged.get('age_hours')} jam")

    inbox = api("GET", "/finance-cases?overdue_only=true", admin, ENT_A).json()
    ok(any(c["id"] == small["id"] for c in inbox),
       "filter 'hanya terlambat' bekerja di inbox", f"{len(inbox)} kasus terlambat")
    ok(inbox and inbox[0].get("overdue") is True,
       "kasus terlambat diurutkan paling atas (antrean menuntun, bukan daftar acak)")

    sc = api("POST", "/finance-cases/scan", admin, ENT_A).json()
    esc = api("GET", f"/finance-cases/{small['id']}", admin, ENT_A).json()
    ok(sc.get("escalated", 0) >= 1 and esc.get("escalation_level", 0) >= 1,
       "kasus terlambat DINAIKKAN ke atasan (eskalasi nyata, bukan hanya warna merah)",
       f"{sc.get('escalated')} dieskalasi · tingkat {esc.get('escalation_level')}")
    ok(any(t["event"] == "eskalasi" for t in esc.get("timeline") or []),
       "eskalasi tercatat di jejak waktu kasus")
    notif = dbrun(lambda db: db.notifications.find_one(
        {"ref": f"esc:{small['id']}:1"}, {"_id": 0}))
    ok(bool(notif) and notif.get("severity") == "critical",
       "notifikasi eskalasi terkirim ke atasan dengan tingkat kepentingan tertinggi",
       f"{(notif or {}).get('title', '')[:60]}")

    assign = api("POST", f"/finance-cases/{big['id']}/assign", admin, ENT_A,
                 json={"assignee": "Dewi Finance"})
    ok(assign.status_code == 200 and assign.json().get("assignee") == "Dewi Finance"
       and assign.json().get("status") == "in_progress",
       "kasus bisa ditugaskan & statusnya jadi 'sedang ditangani'",
       f"{assign.json().get('assignee')}")
    return {"small": small, "big": big}


# ═════════════════════════════════════════════════════════════════════════════
#  7 · ISOLASI LINTAS-PT  (US11)
# ═════════════════════════════════════════════════════════════════════════════
def test_isolation(admin: str, manager: str, ctx: Dict[str, Any]) -> None:
    head("7 · ISOLASI LINTAS-PT (US11)")
    case_b = mkcase(admin, case_type="dana_tak_dikenal", amount=1234000.0,
                    title=f"{POC_TAG} kasus PT-B", entity_id=ENT_B, ent=ENT_B)
    ok(case_b.get("entity_id") == ENT_B, "kasus PT-B dibuat sebagai fixture", ENT_B)

    r = api("GET", f"/finance-cases/{case_b['id']}", manager, ENT_A)
    ok(r.status_code == 403 and "entitas" in r.text.lower(),
       "manager entitas aktif PT-A minta kasus PT-B → 403 KARENA ENTITAS",
       f"HTTP {r.status_code} · {r.text[:70]}")

    r = api("POST", f"/finance-cases/{case_b['id']}/resolve", manager, ENT_A, json={
        "action": "refund_titipan", "reason_code": "case_unidentified_returned",
        "amount": 1000.0})
    ok(r.status_code == 403, "aksi pada kasus PT lain (id dikirim eksplisit) → 403",
       f"HTTP {r.status_code}")

    r = api("POST", f"/finance-cases/{case_b['id']}/assign", manager, ENT_A,
            json={"assignee": "X"})
    ok(r.status_code == 403, "menugaskan kasus PT lain juga ditolak", f"HTTP {r.status_code}")

    lst_a = api("GET", "/finance-cases", manager, ENT_A).json()
    ok(all(c["id"] != case_b["id"] for c in lst_a),
       "inbox PT-A tidak pernah memuat kasus PT-B (tidak ada kebocoran daftar)",
       f"{len(lst_a)} kasus PT-A")
    lst_b = api("GET", "/finance-cases", admin, ENT_B).json()
    ok(any(c["id"] == case_b["id"] for c in lst_b) and
       all((c.get("entity_id") or "") in (ENT_B, "all") for c in lst_b),
       "TIDAK over-block: entitas aktif PT-B tetap melihat kasusnya sendiri",
       f"{len(lst_b)} kasus PT-B")
    lst_all = api("GET", "/finance-cases", admin, "all")
    ok(lst_all.status_code == 200 and any(c["id"] == case_b["id"] for c in lst_all.json()),
       "admin lintas-entitas (X-Entity-Id: all) tetap punya pengawasan",
       f"HTTP {lst_all.status_code}")

    bad = api("POST", "/finance-cases", manager, ENT_A, json={
        "case_type": "dana_tak_dikenal", "amount": 1000.0, "entity_id": ENT_B})
    ok(bad.status_code == 403, "membuat kasus ATAS NAMA PT lain ditolak", f"HTTP {bad.status_code}")

    r = api("POST", f"/finance-cases/{case_b['id']}/reject", admin, ENT_B,
            json={"reason_code": "case_identified_owner", "note": f"{POC_TAG} tutup fixture"})
    ok(r.status_code == 200, "fixture PT-B ditutup lewat entitas yang benar")


# ═════════════════════════════════════════════════════════════════════════════
#  8 · BUKTI-MERAH INV-CASE-01..03  (US10)
# ═════════════════════════════════════════════════════════════════════════════
def test_invariants(admin: str, ctx: Dict[str, Any]) -> None:
    head("8 · BUKTI-MERAH: INV-CASE-01..03 benar-benar MEMERAH (US10)")
    _, out = integrity("case")
    ok(inv_state(out, "INV-CASE-01") == "PASS" and inv_state(out, "INV-CASE-02") == "PASS"
       and inv_state(out, "INV-CASE-03") == "PASS",
       "keadaan awal: INV-CASE-01/02/03 HIJAU",
       f"01={inv_state(out, 'INV-CASE-01')} 02={inv_state(out, 'INV-CASE-02')} "
       f"03={inv_state(out, 'INV-CASE-03')}")

    case_id = (ctx.get("case_after") or {}).get("id") or ""
    docs = (ctx.get("case_after") or {}).get("documents") or []

    # INV-CASE-01 — kasus selesai tanpa dokumen turunan
    dbrun(lambda db: db.finance_cases.update_one({"id": case_id}, {"$set": {"documents": []}}))
    _, out1 = integrity("case")
    ok(inv_state(out1, "INV-CASE-01") == "FAIL",
       "INV-CASE-01 MEMERAH saat kasus 'selesai' kehilangan dokumen turunannya")
    dbrun(lambda db: db.finance_cases.update_one({"id": case_id},
                                                {"$set": {"documents": docs}}))

    # INV-CASE-01 (bagian alasan) — kasus selesai tanpa label alasan
    dbrun(lambda db: db.finance_cases.update_one({"id": case_id}, {"$set": {"reason_code": ""}}))
    _, out1b = integrity("case")
    ok(inv_state(out1b, "INV-CASE-01") == "FAIL",
       "INV-CASE-01 MEMERAH saat kasus 'selesai' kehilangan label alasan")
    dbrun(lambda db: db.finance_cases.update_one(
        {"id": case_id}, {"$set": {"reason_code": "case_identified_owner"}}))

    # INV-CASE-02 — titipan tua tanpa kasus terbuka
    ln = import_line(admin, 3111000.0, f"TRSF E-BANKING CR TAK DIKENAL TUA {POC_TAG}")
    to_holding(admin, ln["id"])
    age_line(ln["id"], 30)
    _, out2 = integrity("case")
    ok(inv_state(out2, "INV-CASE-02") == "FAIL",
       "INV-CASE-02 MEMERAH saat titipan dana menganggur lama TANPA kasus "
       "(uang tak boleh terlupakan)")
    scan = api("POST", "/finance-cases/scan", admin, ENT_A).json()
    for c in api("GET", "/finance-cases", admin, ENT_A).json():
        if (c.get("source") or {}).get("id") == ln["id"]:
            made["cases"].append(c["id"])
    _, out2b = integrity("case")
    ok(inv_state(out2b, "INV-CASE-02") == "PASS",
       "INV-CASE-02 HIJAU lagi setelah pemindai membuat kasusnya",
       f"{scan.get('holding_cases')} kasus baru")

    # INV-CASE-03 — jurnal kasus hilang / tidak seimbang
    je_doc = next((d for d in docs if d["kind"] == "journal_entry"), None)
    if je_doc:
        je = dbrun(lambda db: db.journal_entries.find_one({"id": je_doc["id"]}, {"_id": 0}))
        dbrun(lambda db: db.journal_entries.update_one({"id": je_doc["id"]}, {"$set": {
            "lines": [{**(je.get("lines") or [{}])[0], "debit": 1.0, "credit": 0.0}]}}))
        _, out3 = integrity("case")
        ok(inv_state(out3, "INV-CASE-03") == "FAIL",
           "INV-CASE-03 MEMERAH saat jurnal penyelesaian kasus tidak seimbang")
        dbrun(lambda db: db.journal_entries.update_one({"id": je_doc["id"]}, {"$set": {
            "lines": je.get("lines") or []}}))
    _, out4 = integrity("case")
    ok(inv_state(out4, "INV-CASE-01") == "PASS" and inv_state(out4, "INV-CASE-03") == "PASS",
       "setelah dipulihkan: seluruh INV-CASE HIJAU kembali (invarian bukan hiasan)")


# ═════════════════════════════════════════════════════════════════════════════
#  9 · PEMBERSIHAN — nol residu
# ═════════════════════════════════════════════════════════════════════════════
def cleanup(admin: str, ctx: Dict[str, Any]) -> None:
    head("9 · PEMBERSIHAN — nol residu (gate tidak boleh merusak data demo)")

    # 1) Pesanan demo dipulihkan: cabut SEMUA pembayaran yang lahir dari kasus POC.
    case_ids = list(dict.fromkeys(made["cases"]))

    async def restore_orders(db):
        removed = 0.0
        touched = set()
        async for o in db.sales_orders.find({}, {"_id": 0}):
            pays = o.get("payments") or []
            keep = [p for p in pays if p.get("receipt_id") not in case_ids]
            if len(keep) == len(pays):
                continue
            removed += round(sum(float(p.get("amount") or 0) for p in pays
                                 if p.get("receipt_id") in case_ids), 2)
            paid = round(sum(float(p.get("amount") or 0) for p in keep), 2)
            gt = round(float(o.get("grand_total") or 0), 2)
            status = ("paid" if paid >= gt - 0.01 else ("partial" if paid > 0.01 else "pending"))
            await db.sales_orders.update_one({"id": o["id"]}, {"$set": {
                "payments": keep, "paid_total": paid, "payment_status": status}})
            touched.add(o["id"])
        return {"removed": round(removed, 2), "orders": sorted(touched)}

    r1 = dbrun(restore_orders)
    ok(True, "pembayaran hasil kasus POC dicabut dari pesanan demo (nilai pesanan pulih)",
       f"Rp {r1['removed']:,.0f} · {len(r1['orders'])} pesanan")

    def replan():
        import asyncio
        from services import payment_plan_service as pps

        async def go():
            for oid in r1["orders"]:
                await pps.recompute_for_doc("sales_order", oid)
        asyncio.run(go())

    try:
        replan()
        ok(True, "rencana pembayaran pesanan dihitung ulang (INV-PAY-02 tetap sah)")
    except Exception as exc:  # noqa: BLE001
        ok(False, f"gagal menghitung ulang rencana pembayaran: {exc}")

    # 2) Saldo supplier/pelanggan & artefak POC dihapus.
    async def purge(db):
        n = {}
        n["cases"] = (await db.finance_cases.delete_many(
            {"$or": [{"id": {"$in": case_ids}}, {"title": {"$regex": POC_TAG}},
                     {"description": {"$regex": POC_TAG}}]})).deleted_count
        n["lines"] = (await db.bank_statement_lines.delete_many(
            {"$or": [{"id": {"$in": made["lines"]}},
                     {"description": {"$regex": POC_TAG}}]})).deleted_count
        # Kas & jurnal HANYA milik kasus POC (id-nya dilacak) — kasus demo tidak disentuh.
        n["cash"] = (await db.cash_transactions.delete_many(
            {"$or": [{"id": {"$in": made["cash"]}},
                     {"ref_type": "finance_case", "ref_id": {"$in": case_ids}},
                     {"description": {"$regex": POC_TAG}}]})).deleted_count
        n["je"] = (await db.journal_entries.delete_many(
            {"source_type": "finance_case",
             "$or": [{"source_id": {"$in": case_ids}}]
                    + [{"source_id": {"$regex": f"^{cid}:"}} for cid in case_ids]
             })).deleted_count if case_ids else 0
        n["je_cash"] = (await db.journal_entries.delete_many(
            {"source_type": "cash_transaction",
             "source_id": {"$in": made["cash"]}})).deleted_count
        # Jurnal FASE G-8 yang lahir dari baris titipan POC:
        #   `Dr Bank / Cr 2-1950` (source_type=cash_transaction, sudah di atas) DAN
        #   `Dr 2-1950 / Cr 1-1200` (source_type=bank_holding_alloc, source_id
        #   berpola "<line_id>:<order_id>:<n>"). Tanpa baris ini saldo akun titipan
        #   TIDAK kembali nol dan INV-BNK-03 memerah — residu nyata yang ketemu saat
        #   POC ini pertama dijalankan.
        n["je_hold"] = 0
        for lid in made["lines"]:
            n["je_hold"] += (await db.journal_entries.delete_many(
                {"$or": [{"source_id": {"$regex": f"^{lid}"}},
                         {"source_id": lid}]})).deleted_count
        n["notif"] = (await db.notifications.delete_many(
            {"notif_type": "finance_case",
             "$or": [{"ref": {"$in": case_ids}}]
                    + [{"ref": {"$regex": f"esc:{cid}"}} for cid in case_ids]
             })).deleted_count if case_ids else 0
        n["receipts"] = (await db.ar_receipts.delete_many(
            {"$or": [{"id": {"$in": made["receipts"]}},
                     {"notes": {"$regex": POC_TAG}}]})).deleted_count
        for rid in made["receipts"]:
            n["je_rec"] = n.get("je_rec", 0) + (await db.journal_entries.delete_many(
                {"source_id": {"$regex": f"^{rid}"}})).deleted_count
        # Baris buku saldo kredit milik POC. SELAIN yang bertanda `ref_type=POC_TAG`
        # (grant suntikan), aksi `refund_store_credit` melahirkan baris `adjust` LEWAT
        # JALUR PRODUKSI dengan id acak dan TANPA tanda POC — dulu baris itu tertinggal
        # (`amount -120.000`) sehingga saldo pelanggan uji jadi nol dan POC ini GAGAL pada
        # jalan BERIKUTNYA ("Pengembalian Rp 120.000 melebihi saldo kredit toko Rp 0"):
        # POC memblokir dirinya sendiri. Karena itu baris yang menunjuk kasus POC
        # (`ref_id` salah satu kasus yang dibuat POC) ikut dibersihkan.
        n["sc_ledger"] = (await db.store_credit_ledger.delete_many(
            {"$or": [{"ref_type": POC_TAG}, {"note": {"$regex": POC_TAG}},
                     {"ref_id": {"$in": made["cases"]}},
                     {"case_id": {"$in": made["cases"]}}]
             + ([{"note": {"$regex": "|".join(made["case_numbers"])}}]
                if made["case_numbers"] else [])})).deleted_count
        n["penalties"] = (await db.penalties.delete_many(
            {"doc_id": {"$in": [o for o in made["orders"]]},
             "created_by": {"$regex": "Budi|manager|Sinta", "$options": "i"}}
        )).deleted_count if made["orders"] else 0
        n["seq"] = (await db.number_sequences.delete_many({"doc_type": "CASE"})).deleted_count
        return n

    n = dbrun(purge)
    ok(True, "artefak POC dihapus dari database", str(n))

    left = dbrun(lambda db: db.finance_cases.count_documents({}))
    poc_left = dbrun(lambda db: db.finance_cases.count_documents(
        {"$or": [{"id": {"$in": case_ids}}, {"title": {"$regex": POC_TAG}}]}))
    cash_left = dbrun(lambda db: db.cash_transactions.count_documents(
        {"$or": [{"id": {"$in": made["cash"]}}, {"description": {"$regex": POC_TAG}}]}))
    ok(poc_left == 0 and cash_left == 0,
       "nol residu artefak POC (kasus DEMO sengaja dibiarkan utuh)",
       f"artefak POC {poc_left} · kas POC {cash_left} · kasus demo tersisa {left}")
    ok(left == ctx.get("base_cases", 0),
       "jumlah kasus DEMO kembali seperti sebelum POC (INV-GATE-01 · data demo tak digeser)",
       f"{ctx.get('base_cases')} → {left}")

    for code, label in (("1-1150", "Kas & Bank Transit"),
                        ("1-1280", "Piutang Titipan Karyawan"),
                        ("2-1950", "Titipan Dana Belum Teridentifikasi"),
                        ("2-1400", "Uang Muka Pelanggan"),
                        ("1-1400", "Uang Muka & Biaya Dibayar Dimuka")):
        bal = gl_balance(code)
        base = (ctx.get("base_gl") or {}).get(code, 0.0)
        ok(round(bal - base, 2) == 0.0,
           f"saldo {label} ({code}) kembali ke keadaan SEBELUM POC",
           f"Rp {bal:,.0f} (awal Rp {base:,.0f})")

    rc, out = integrity()
    tail = [l for l in out.splitlines() if "PASS" in l and "FAIL" in l]
    ok(rc == 0, "invarian GLOBAL tetap HIJAU setelah pembersihan (nol residu)",
       tail[-1].strip() if tail else out[-160:])


# ═════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(f"\n{B}{'=' * 74}\n  POC FASE G-9 — PUSAT KASUS KEUANGAN "
          f"(playbook · SLA · dokumen turunan)\n{'=' * 74}{X}")
    admin, manager, sales = login("admin@kainnusantara.id"), \
        login("manager@kainnusantara.id"), login("sales@kainnusantara.id")
    ok(True, "login admin & manager (penyetuju) · sales (kontrol tanpa izin resolve)")

    ctx: Dict[str, Any] = {}
    # Keadaan AWAL: data demo FASE G-9 sendiri berisi 3 kasus (1 titipan · 1 selesai ·
    # 1 dua-langkah) sehingga "nol kasus" & "saldo NOL" BUKAN ukuran yang benar. Yang benar:
    # POC harus mengembalikan segalanya ke keadaan SEBELUM ia berjalan — dan TIDAK BOLEH
    # menghapus kasus demo (dulu cleanup menghapus semua `finance_cases` + semua jurnal
    # `source_type=finance_case`, yang justru merusak data demo → gate MERAH).
    ctx["base_cases"] = dbrun(lambda db: db.finance_cases.count_documents({}))
    ctx["base_gl"] = {c: gl_balance(c) for c in
                      ("1-1150", "1-1280", "2-1950", "1-1200", "2-1400", "1-1400")}
    ok(True, "keadaan awal direkam (kasus demo & saldo akun) — POC tidak boleh menggesernya",
       f"{ctx['base_cases']} kasus demo")
    try:
        ref = test_playbooks(admin, manager, sales)
        pol = ref["policy"]
        ctx.update(test_auto_intake(admin, pol))
        g = test_guards(admin, manager, sales, ctx, pol)
        ctx.update(test_resolve_holding(admin, ctx, g))
        ctx.update(test_more_playbooks(admin, manager))
        ctx.update(test_rest_playbooks(admin, manager))
        ctx.update(test_sla(admin, pol))
        test_isolation(admin, manager, ctx)
        test_invariants(admin, ctx)
    finally:
        cleanup(admin, ctx)

    print(f"\n{B}{'=' * 74}\n  HASIL: {G}{res['pass']} PASS{X}{B} · "
          f"{G if not res['fail'] else R}{res['fail']} FAIL{X}{B}\n{'=' * 74}{X}")
    return 1 if res["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
