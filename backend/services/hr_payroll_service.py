"""HRD H4 — Payroll & Payslip engine + run lifecycle.

Port dari H-POC (scripts/poc_hrd.py) yang TERVALIDASI: BPJS, PPh21 TER bulanan,
jurnal SEIMBANG, komisi accrue_then_settle (anti double-count). Config-driven via
`system_settings.hr` (get_hr_settings). Koleksi kanonik (entity-scoped):
`hr_payroll_runs` (prun_), `hr_payslips` (slip_).

TER tables = PMK 168/2023 (bulanan), kategori A/B/C menurut PTKP. Disimpan sebagai
(batas_atas_inklusif, tarif). Penghasilan bruto <= batas → tarif tsb. (lapis pertama match).
"""
from typing import Any, Dict, List, Optional, Tuple

from db import db
from core_utils import new_id, now_iso, next_doc_number, safe_doc
from services import hr_service

INF = float("inf")
WORK_HOURS_DIVISOR = 173  # jam kerja/bulan (rumus upah-sejam Kepmenaker)

# ── PPh21 TER bulanan (PMK 168/2023) — (upper_inclusive, rate) ─────────────────
TER_A: List[Tuple[float, float]] = [
    (5_400_000, 0.0), (5_650_000, 0.0025), (5_950_000, 0.005), (6_300_000, 0.0075),
    (6_750_000, 0.01), (7_500_000, 0.0125), (8_550_000, 0.015), (9_650_000, 0.0175),
    (10_750_000, 0.02), (11_250_000, 0.025), (11_600_000, 0.03), (12_500_000, 0.035),
    (13_750_000, 0.04), (15_100_000, 0.045), (16_950_000, 0.05), (19_750_000, 0.06),
    (24_150_000, 0.07), (26_450_000, 0.08), (29_550_000, 0.09), (33_450_000, 0.10),
    (38_450_000, 0.11), (44_550_000, 0.12), (52_050_000, 0.13), (61_250_000, 0.14),
    (72_650_000, 0.15), (86_350_000, 0.16), (102_650_000, 0.17), (122_050_000, 0.18),
    (145_150_000, 0.19), (172_550_000, 0.20), (204_650_000, 0.21), (242_050_000, 0.22),
    (285_550_000, 0.23), (335_550_000, 0.24), (392_150_000, 0.25), (455_550_000, 0.26),
    (525_850_000, 0.27), (603_050_000, 0.28), (687_150_000, 0.29), (778_250_000, 0.30),
    (876_350_000, 0.31), (981_450_000, 0.32), (1_100_000_000, 0.33), (INF, 0.34),
]
TER_B: List[Tuple[float, float]] = [
    (6_200_000, 0.0), (6_500_000, 0.0025), (6_850_000, 0.005), (7_300_000, 0.0075),
    (9_200_000, 0.01), (10_750_000, 0.0125), (11_250_000, 0.015), (11_600_000, 0.02),
    (12_600_000, 0.025), (13_600_000, 0.03), (14_950_000, 0.035), (16_950_000, 0.04),
    (19_750_000, 0.05), (24_150_000, 0.06), (26_450_000, 0.07), (29_550_000, 0.08),
    (33_450_000, 0.09), (38_450_000, 0.10), (44_550_000, 0.11), (52_050_000, 0.12),
    (61_250_000, 0.13), (72_650_000, 0.14), (86_350_000, 0.15), (102_650_000, 0.16),
    (122_050_000, 0.17), (145_150_000, 0.18), (172_550_000, 0.19), (204_650_000, 0.20),
    (242_050_000, 0.21), (285_550_000, 0.22), (335_550_000, 0.23), (392_150_000, 0.24),
    (455_550_000, 0.25), (525_850_000, 0.26), (603_050_000, 0.27), (687_150_000, 0.28),
    (778_250_000, 0.29), (876_350_000, 0.30), (981_450_000, 0.31), (INF, 0.34),
]
TER_C: List[Tuple[float, float]] = [
    (6_600_000, 0.0), (6_950_000, 0.0025), (7_350_000, 0.005), (7_800_000, 0.0075),
    (8_850_000, 0.01), (9_800_000, 0.0125), (10_950_000, 0.015), (11_200_000, 0.0175),
    (12_600_000, 0.02), (13_600_000, 0.025), (14_950_000, 0.03), (16_950_000, 0.035),
    (19_750_000, 0.04), (24_150_000, 0.05), (26_450_000, 0.06), (29_550_000, 0.07),
    (33_450_000, 0.08), (38_450_000, 0.09), (44_550_000, 0.10), (52_050_000, 0.11),
    (61_250_000, 0.12), (72_650_000, 0.13), (86_350_000, 0.14), (102_650_000, 0.15),
    (122_050_000, 0.16), (145_150_000, 0.17), (172_550_000, 0.18), (204_650_000, 0.19),
    (242_050_000, 0.20), (285_550_000, 0.21), (335_550_000, 0.22), (392_150_000, 0.23),
    (455_550_000, 0.24), (525_850_000, 0.25), (603_050_000, 0.26), (687_150_000, 0.27),
    (778_250_000, 0.28), (876_350_000, 0.29), (981_450_000, 0.30), (1_100_000_000, 0.31), (INF, 0.34),
]
TER_TABLES = {"A": TER_A, "B": TER_B, "C": TER_C}
PTKP_TO_TER = {
    "TK0": "A", "TK1": "A", "K0": "A",
    "TK2": "B", "TK3": "B", "K1": "B", "K2": "B",
    "K3": "C",
}


def ter_rate(category: str, gross: float) -> float:
    table = TER_TABLES.get(category, TER_A)
    for upper, rate in table:
        if gross <= upper:
            return rate
    return table[-1][1]


def _pct(v: Any) -> float:
    """Config menyimpan rate sebagai persen (1.0 = 1%)."""
    return float(v or 0) / 100.0


def _sum_allowances(allowances: Any) -> float:
    if isinstance(allowances, (int, float)):
        return round(float(allowances), 2)
    total = 0.0
    if isinstance(allowances, list):
        for a in allowances:
            if isinstance(a, dict):
                total += float(a.get("amount", 0) or 0)
            elif isinstance(a, (int, float)):
                total += float(a)
    return round(total, 2)


def bpjs_breakdown(base: float, emp: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[Dict, Dict, float, float]:
    b = cfg.get("bpjs", {})
    # FASE G-0 — `hr.feature_toggles.bpjs_kesehatan` & `bpjs_ketenagakerjaan` DULU tidak
    # pernah dibaca mesin payroll (setting tersembunyi tanpa efek). Sekarang benar-benar
    # mematikan komponen terkait pada slip gaji bila toggle-nya dimatikan.
    toggles = cfg.get("feature_toggles", {}) or {}
    kes_on = bool(toggles.get("bpjs_kesehatan", True))
    tk_on = bool(toggles.get("bpjs_ketenagakerjaan", True))
    kes_ceil = float(b.get("kes_ceiling") or INF)
    jp_ceil = float(b.get("jp_ceiling") or INF)
    kes_base = min(base, kes_ceil)
    jp_base = min(base, jp_ceil)
    # JKK kelas risiko per karyawan (default kelas II) → rate dari jkk_classes.
    jkk_class = emp.get("jkk_risk_class") or "II"
    jkk_rate = 0.0
    for c in cfg.get("jkk_classes", []):
        if str(c.get("class")) == str(jkk_class):
            jkk_rate = _pct(c.get("rate"))
            break
    emp_b = {
        "kesehatan": round(kes_base * _pct(b.get("kes_rate_employee")), 2) if kes_on else 0.0,
        "jht": round(base * _pct(b.get("jht_rate_employee")), 2) if tk_on else 0.0,
        "jp": round(jp_base * _pct(b.get("jp_rate_employee")), 2) if tk_on else 0.0,
    }
    er_b = {
        "kesehatan": round(kes_base * _pct(b.get("kes_rate_employer")), 2) if kes_on else 0.0,
        "jht": round(base * _pct(b.get("jht_rate_employer")), 2) if tk_on else 0.0,
        "jp": round(jp_base * _pct(b.get("jp_rate_employer")), 2) if tk_on else 0.0,
        "jkk": round(base * jkk_rate, 2) if tk_on else 0.0,
        "jkm": round(base * _pct(b.get("jkm_rate_employer")), 2) if tk_on else 0.0,
    }
    return emp_b, er_b, round(sum(emp_b.values()), 2), round(sum(er_b.values()), 2)


async def _period_overtime_min(emp_id: str, period: str, entity_id: str) -> int:
    q: Dict[str, Any] = {"employee_id": emp_id, "date": {"$regex": f"^{period}"}}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    rows = await db.hr_attendance.find(q, {"_id": 0, "overtime_min": 1}).to_list(400)
    return int(sum(int(r.get("overtime_min") or 0) for r in rows))


async def _period_filed_overtime_min(emp_id: str, period: str, entity_id: str) -> int:
    """Lembur FORMAL (H3) yang sudah di-approve untuk periode ini → menit.

    Sumber: koleksi `hr_overtime` (pengajuan lembur manual/terjadwal), terpisah dari
    lembur otomatis hasil clock-in/out (hr_attendance.overtime_min). Keduanya
    dijumlahkan di compute_payslip & ditampilkan terpisah agar transparan (anti-ambiguitas).
    """
    q: Dict[str, Any] = {"employee_id": emp_id, "status": "approved", "period": period}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    rows = await db.hr_overtime.find(q, {"_id": 0, "minutes": 1}).to_list(400)
    return int(sum(int(r.get("minutes") or 0) for r in rows))


def _overtime_amount(base: float, overtime_min: int, cfg: Dict[str, Any]) -> float:
    ot = cfg.get("overtime", {}) or {}
    mult = float(ot.get("multiplier", 1.5) or 1.5)
    divisor = int(ot.get("hours_divisor", WORK_HOURS_DIVISOR) or WORK_HOURS_DIVISOR)
    if base <= 0 or overtime_min <= 0:
        return 0.0
    hourly = base / divisor
    return round((overtime_min / 60.0) * hourly * mult, 2)


async def _commission_for(emp: Dict[str, Any], period: str, entity_id: str) -> float:
    uid = emp.get("user_id")
    if not uid:
        return 0.0
    u = await db.users.find_one({"id": uid}, {"_id": 0, "role": 1})
    if not u or u.get("role") != "sales":
        return 0.0
    try:
        from services import sales_force_service as sf
        res = await sf.compute_commission(uid, period, entity_id=entity_id)
        return round(float(res.get("total_incentive", 0) or 0), 2)
    except Exception:
        return 0.0


async def compute_payslip(emp: Dict[str, Any], period: str, entity_id: str,
                          cfg: Dict[str, Any]) -> Dict[str, Any]:
    base = float(emp.get("base_salary") or 0)
    allowances = _sum_allowances(emp.get("allowances"))
    ot_auto = await _period_overtime_min(emp["id"], period, entity_id)
    ot_filed = await _period_filed_overtime_min(emp["id"], period, entity_id)
    ot_min = ot_auto + ot_filed
    overtime = _overtime_amount(base, ot_min, cfg)
    commission = await _commission_for(emp, period, entity_id)
    salary_earnings = round(base + allowances + overtime, 2)
    gross = round(salary_earnings + commission, 2)
    emp_b, er_b, emp_total, er_total = bpjs_breakdown(base, emp, cfg)
    ptkp = emp.get("ptkp_status") or "TK0"
    category = PTKP_TO_TER.get(ptkp, "A")
    # FASE G-0 — `hr.feature_toggles.pph21` kini benar-benar mengendalikan pemotongan PPh 21
    # (sebelumnya toggle ini tersimpan tetapi tidak pernah diperiksa mesin payroll).
    _pph21_on = bool((cfg.get("feature_toggles", {}) or {}).get("pph21", True))
    rate = ter_rate(category, gross) if (cfg.get("ter_enabled", True) and _pph21_on) else 0.0
    pph21 = round(gross * rate, 2)
    net = round(gross - emp_total - pph21, 2)
    return {
        "employee_id": emp["id"], "employee_name": emp.get("name", ""),
        "user_id": emp.get("user_id", ""), "position": emp.get("position_name", ""),
        "ptkp_status": ptkp, "ter_category": category, "pph21_rate": rate,
        "base_salary": round(base, 2), "allowances": allowances,
        "overtime_min": ot_min, "overtime_auto_min": ot_auto, "overtime_filed_min": ot_filed,
        "overtime": overtime, "commission": commission,
        "salary_earnings": salary_earnings, "gross": gross,
        "bpjs_emp": emp_b, "bpjs_er": er_b,
        "bpjs_emp_total": emp_total, "bpjs_er_total": er_total,
        "pph21": pph21, "net": net,
        "bank": {"bank_name": emp.get("bank_name", ""), "acc_no": emp.get("bank_acc_no", ""),
                 "acc_name": emp.get("bank_acc_name", "")},
    }


def _empty_totals() -> Dict[str, float]:
    return {"employees": 0, "salary_earnings": 0.0, "commission": 0.0, "gross": 0.0,
            "bpjs_emp": 0.0, "bpjs_er": 0.0, "pph21": 0.0, "net": 0.0}


def _accumulate(totals: Dict[str, float], s: Dict[str, Any]) -> None:
    totals["employees"] += 1
    totals["salary_earnings"] += s["salary_earnings"]
    totals["commission"] += s["commission"]
    totals["gross"] += s["gross"]
    totals["bpjs_emp"] += s["bpjs_emp_total"]
    totals["bpjs_er"] += s["bpjs_er_total"]
    totals["pph21"] += s["pph21"]
    totals["net"] += s["net"]


def _round_totals(t: Dict[str, float]) -> Dict[str, float]:
    return {k: (v if k == "employees" else round(v, 2)) for k, v in t.items()}


async def _active_employees(entity_id: str) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"status": "active"}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    rows = await db.hr_employees.find(q, {"_id": 0}).to_list(2000)
    return [safe_doc(r) for r in rows]


async def preview_run(entity_id: str, period: str) -> Dict[str, Any]:
    # FASE E-4 (E4.5) — BPJS/PPh21/lembur mengikuti badan usaha yang digaji.
    cfg = await hr_service.get_hr_settings(entity_id)
    emps = await _active_employees(entity_id)
    slips: List[Dict[str, Any]] = []
    totals = _empty_totals()
    for emp in emps:
        s = await compute_payslip(emp, period, entity_id, cfg)
        slips.append(s)
        _accumulate(totals, s)
    slips.sort(key=lambda x: x["employee_name"])
    return {"entity_id": entity_id, "period": period,
            "commission_mode": cfg.get("payroll_commission_mode", "accrue_then_settle"),
            "payslips": slips, "totals": _round_totals(totals), "count": len(slips)}


async def existing_run(entity_id: str, period: str) -> Optional[Dict[str, Any]]:
    return safe_doc(await db.hr_payroll_runs.find_one(
        {"entity_id": entity_id, "period": period, "status": {"$ne": "void"}}, {"_id": 0}))


async def create_run(entity_id: str, period: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    if not entity_id or entity_id == "all" or not period:
        raise ValueError("Payroll run butuh entitas spesifik & periode (mis. 2026-06).")
    found = await existing_run(entity_id, period)
    if found:
        return await get_run(found["id"])
    prev = await preview_run(entity_id, period)
    if prev["count"] == 0:
        raise ValueError("Tidak ada karyawan aktif pada entitas ini.")
    number = await next_doc_number("hr_payroll_runs", "number", "PR-", entity_id=entity_id)
    run_id = new_id("prun")
    run = {
        "id": run_id, "number": number, "entity_id": entity_id, "period": period,
        "status": "draft", "commission_mode": prev["commission_mode"],
        "totals": prev["totals"], "gl_posted": False, "journal_id": "", "journal_number": "",
        "incentive_journal_id": "", "paid_journal_id": "", "paid_journal_number": "",
        "approved_by": "", "approved_at": "", "posted_at": "", "paid_at": "",
        "created_by": actor.get("name", "system"), "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.hr_payroll_runs.insert_one(run)
    slip_docs = []
    for s in prev["payslips"]:
        sid = new_id("slip")
        snum = await next_doc_number("hr_payslips", "number", "SLIP-", entity_id=entity_id)
        slip_docs.append({
            "id": sid, "number": snum, "run_id": run_id, "entity_id": entity_id, "period": period,
            "status": "draft", "pdf_url": "", **s,
            "created_at": now_iso(), "updated_at": now_iso(),
        })
    if slip_docs:
        await db.hr_payslips.insert_many(slip_docs)
    return await get_run(run_id)


async def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    run = safe_doc(await db.hr_payroll_runs.find_one({"id": run_id}, {"_id": 0}))
    if not run:
        return None
    slips = [safe_doc(s) for s in await db.hr_payslips.find(
        {"run_id": run_id}, {"_id": 0}).sort("employee_name", 1).to_list(5000)]
    run["payslips"] = slips
    return run


async def list_runs(scope: Dict[str, Any], status: Optional[str] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = dict(scope or {})
    if status:
        q["status"] = status
    rows = await db.hr_payroll_runs.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [safe_doc(r) for r in rows]


async def _set_run(run_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    patch["updated_at"] = now_iso()
    await db.hr_payroll_runs.update_one({"id": run_id}, {"$set": patch})
    await db.hr_payslips.update_many({"run_id": run_id}, {"$set": {"status": patch.get("status", "draft"),
                                                                  "updated_at": now_iso()}}
                                     if "status" in patch else {"$set": {"updated_at": now_iso()}})
    return await get_run(run_id)


# ── UTANG ALUR F-6.7 (dibayar 2026-08-18): payroll punya langkah "Ajukan" ─────
# MASALAH: pengesahan payroll dulu bekerja langsung dari status `draft`, sehingga
# draf yang MASIH DIKERJAKAN HR tidak bisa dibedakan dari yang siap disahkan. Dua
# akibatnya nyata: (a) penyetuju tidak punya cara tahu mana yang menunggu dirinya —
# ia harus menebak dari daftar draf; (b) antrean "menunggu persetujuan" TIDAK BISA
# menghitung payroll tanpa ikut menghitung pekerjaan orang lain, jadi payroll
# sengaja dibebaskan dari penjaga antrean (`DOOR_EXEMPT` di
# `scripts/guardrails/verify_approval_queues.py`) dengan alasan bertanda "UTANG ALUR".
# Sekarang alurnya: draft → (Ajukan) pending_approval → approved → posted → paid,
# dan `pending_approval` itulah yang dihitung antrean `hr_payroll`.
async def submit_run(run_id: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    """draft → pending_approval (HR menyatakan payroll ini SIAP disahkan)."""
    run = await db.hr_payroll_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise ValueError("Payroll run tidak ditemukan.")
    if run["status"] != "draft":
        raise ValueError(f"Hanya payroll draf yang bisa diajukan (status sekarang: "
                         f"'{run['status']}').")
    if not await db.hr_payslips.count_documents({"run_id": run_id}):
        raise ValueError("Payroll ini belum punya slip gaji — hitung dulu sebelum diajukan.")
    return await _set_run(run_id, {
        "status": "pending_approval",
        "submitted_by": actor.get("name", "system"), "submitted_at": now_iso(),
        "reject_reason": "", "rejected_by": "", "rejected_at": ""})


async def approve_run(run_id: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    run = await db.hr_payroll_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise ValueError("Payroll run tidak ditemukan.")
    if run["status"] not in ("pending_approval",):
        raise ValueError(
            f"Hanya payroll yang sudah DIAJUKAN bisa disahkan (status sekarang: "
            f"'{run['status']}'). Ajukan dulu dari layar Payroll."
            if run["status"] == "draft" else
            f"Run status '{run['status']}' tidak bisa di-approve.")
    return await _set_run(run_id, {"status": "approved", "approved_by": actor.get("name", "system"),
                                   "approved_at": now_iso()})


async def reject_run(run_id: str, actor: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """pending_approval → draft, dengan ALASAN yang tersimpan di dokumennya.

    Alasan disimpan di dokumen (bukan hanya jejak audit) supaya HR yang membuka
    payrollnya besok tahu apa yang harus diperbaiki tanpa membuka layar lain.
    """
    run = await db.hr_payroll_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise ValueError("Payroll run tidak ditemukan.")
    if run["status"] != "pending_approval":
        raise ValueError(f"Hanya payroll yang sedang diajukan bisa dikembalikan "
                         f"(status sekarang: '{run['status']}').")
    if not (reason or "").strip():
        raise ValueError("Alasan wajib diisi supaya HR tahu apa yang harus diperbaiki.")
    hist = list(run.get("decision_history") or [])
    hist.append({"action": "rejected", "by": actor.get("name", "system"),
                 "at": now_iso(), "reason": reason.strip(),
                 "from_status": "pending_approval", "to_status": "draft"})
    return await _set_run(run_id, {
        "status": "draft", "reject_reason": reason.strip(),
        "rejected_by": actor.get("name", "system"), "rejected_at": now_iso(),
        "decision_history": hist})


async def post_run_gl(run_id: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    from services import gl_service
    run = await get_run(run_id)
    if not run:
        raise ValueError("Payroll run tidak ditemukan.")
    if run["status"] not in ("approved",):
        raise ValueError(f"Run status '{run['status']}' harus 'approved' sebelum posting GL.")
    je = await gl_service.post_payroll_run(run, run.get("payslips", []), actor.get("name", "system"))
    patch = {"status": "posted", "gl_posted": True, "posted_at": now_iso()}
    if je:
        patch["journal_id"] = je.get("id", "")
        patch["journal_number"] = je.get("number", "")
        patch["incentive_journal_id"] = je.get("incentive_journal_id", "")
    return await _set_run(run_id, patch)


async def pay_run(run_id: str, actor: Dict[str, Any], cash_account: Optional[str] = None) -> Dict[str, Any]:
    from services import gl_service
    run = await get_run(run_id)
    if not run:
        raise ValueError("Payroll run tidak ditemukan.")
    if run["status"] not in ("posted",):
        raise ValueError(f"Run status '{run['status']}' harus 'posted' sebelum dibayar.")
    je = await gl_service.pay_payroll_run(run, actor.get("name", "system"), cash_account)
    patch = {"status": "paid", "paid_at": now_iso()}
    if je:
        patch["paid_journal_id"] = je.get("id", "")
        patch["paid_journal_number"] = je.get("number", "")
    return await _set_run(run_id, patch)


async def list_payslips(scope: Dict[str, Any], period: Optional[str] = None,
                        employee_id: Optional[str] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = dict(scope or {})
    if period:
        q["period"] = period
    if employee_id:
        q["employee_id"] = employee_id
    rows = await db.hr_payslips.find(q, {"_id": 0}).sort("period", -1).to_list(2000)
    return [safe_doc(r) for r in rows]


async def get_payslip(slip_id: str) -> Optional[Dict[str, Any]]:
    return safe_doc(await db.hr_payslips.find_one({"id": slip_id}, {"_id": 0}))


async def my_payslips(user: Dict[str, Any], period: Optional[str] = None) -> Dict[str, Any]:
    emp = await db.hr_employees.find_one({"user_id": user["id"]}, {"_id": 0, "id": 1, "name": 1})
    if not emp:
        return {"employee": None, "payslips": []}
    q: Dict[str, Any] = {"employee_id": emp["id"], "status": {"$in": ["posted", "paid", "approved"]}}
    if period:
        q["period"] = period
    rows = await db.hr_payslips.find(q, {"_id": 0}).sort("period", -1).to_list(200)
    return {"employee": {"id": emp["id"], "name": emp.get("name", "")},
            "payslips": [safe_doc(r) for r in rows]}
