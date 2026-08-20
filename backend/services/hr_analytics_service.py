"""HRD H6 service — HR Analytics (Dashboard BI SDM).

Agregasi read-only lintas koleksi HR (entity-scoped) untuk dashboard `cs-bi-hrd`:
- Headcount (total, per tipe pekerja, per departemen, new hires)
- Attendance rate (per periode bulan)
- Turnover (separations / headcount; new hires)
- Payroll cost (dari hr_payroll_runs.totals; tren per periode)
- Overtime trend (hr_overtime approved per periode)
- Statutory payable: BPJS (emp+er) & PPh21 (dari run periode terpilih)

Semua angka aman (defensive .get). Pola scoping = reporting.py (resolve_list_scope).
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from db import db
from entity_scope import resolve_list_scope

WIB = timezone(timedelta(hours=7))

# Pemetaan status absensi → kategori ringkas
PRESENT = {"hadir"}
LATE = {"telat"}
LEAVE = {"cuti", "izin"}
ABSENT = {"alpha"}
OFF = {"libur"}


def _cur_month() -> str:
    return datetime.now(WIB).strftime("%Y-%m")


def _month_range(end_period: str, n: int) -> List[str]:
    """n bulan berakhir di end_period (inklusif), urut menaik. mis. ('2026-07',6)."""
    try:
        y, m = int(end_period[:4]), int(end_period[5:7])
    except (ValueError, IndexError):
        y, m = datetime.now(WIB).year, datetime.now(WIB).month
    out: List[str] = []
    for i in range(n - 1, -1, -1):
        yy, mm = y, m - i
        while mm <= 0:
            mm += 12
            yy -= 1
        out.append(f"{yy:04d}-{mm:02d}")
    return out


async def hr_summary(ctx, entity_id: Optional[str], period: Optional[str] = None) -> Dict[str, Any]:
    emp_scope = resolve_list_scope("hr_employees", {}, ctx, entity_id)
    att_scope = resolve_list_scope("hr_attendance", {}, ctx, entity_id)
    pay_scope = resolve_list_scope("hr_payroll_runs", {}, ctx, entity_id)
    ot_scope = resolve_list_scope("hr_overtime", {}, ctx, entity_id)

    # ── Periode tersedia (payroll ∪ overtime ∪ bulan absensi ∪ bulan berjalan) ──
    pay_periods = await db.hr_payroll_runs.distinct("period", pay_scope)
    ot_periods = await db.hr_overtime.distinct("period", ot_scope)
    att_dates = await db.hr_attendance.distinct("date", att_scope)
    att_months = {d[:7] for d in att_dates if d}
    periods = sorted(
        {p for p in pay_periods if p} | {p for p in ot_periods if p} | att_months | {_cur_month()},
        reverse=True,
    )
    # Default periode terpilih: utamakan UX dashboard yang "penuh" —
    # periode payroll TERBARU yang JUGA punya data absensi (hindari default ke
    # bulan yang cuma ada run payroll tanpa absensi → tampil 0% & terkesan kosong).
    if period and period in periods:
        sel = period
    else:
        pay_valid = sorted(p for p in pay_periods if p)
        pay_with_att = [p for p in pay_valid if p in att_months]
        if pay_with_att:
            sel = pay_with_att[-1]
        elif pay_valid:
            sel = pay_valid[-1]
        elif att_months:
            sel = sorted(att_months)[-1]
        elif periods:
            sel = periods[0]
        else:
            sel = _cur_month()

    # ── Headcount ──
    employees = await db.hr_employees.find(emp_scope, {"_id": 0}).to_list(5000)
    active = [e for e in employees if (e.get("status") or "active") == "active"]
    org_units = {o["id"]: o.get("name", "—")
                 for o in await db.hr_org_units.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)}
    by_type: Dict[str, int] = {}
    by_dept: Dict[str, int] = {}
    for e in active:
        by_type[e.get("employment_type") or "lainnya"] = by_type.get(e.get("employment_type") or "lainnya", 0) + 1
        dname = org_units.get(e.get("department_id"), "Tanpa Departemen")
        by_dept[dname] = by_dept.get(dname, 0) + 1
    now = datetime.now(WIB)
    d30 = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    d90 = (now - timedelta(days=90)).strftime("%Y-%m-%d")

    def _join(e):
        return (e.get("join_date") or "")[:10]

    new_30 = sum(1 for e in active if _join(e) and _join(e) >= d30)
    new_90 = sum(1 for e in active if _join(e) and _join(e) >= d90)
    headcount = {
        "total": len(active),
        "new_hires_30d": new_30,
        "new_hires_90d": new_90,
        "by_type": [{"type": k, "count": v} for k, v in sorted(by_type.items(), key=lambda x: -x[1])],
        "by_department": [{"name": k, "count": v} for k, v in sorted(by_dept.items(), key=lambda x: -x[1])],
    }

    # ── Attendance (periode terpilih) ──
    att_rows = await db.hr_attendance.find(
        {**att_scope, "date": {"$regex": f"^{sel}"}}, {"_id": 0}).to_list(20000)
    present = sum(1 for a in att_rows if a.get("status") in PRESENT)
    late = sum(1 for a in att_rows if a.get("status") in LATE)
    leave = sum(1 for a in att_rows if a.get("status") in LEAVE)
    alpha = sum(1 for a in att_rows if a.get("status") in ABSENT)
    off = sum(1 for a in att_rows if a.get("status") in OFF)
    work_records = present + late + alpha
    late_mins = [float(a.get("late_min") or 0) for a in att_rows if a.get("status") in LATE]
    attendance = {
        "period": sel,
        "present": present, "late": late, "leave": leave, "alpha": alpha, "off": off,
        "total": len(att_rows),
        "attendance_rate": round((present + late) / work_records * 100, 1) if work_records else 0.0,
        "punctuality_rate": round(present / (present + late) * 100, 1) if (present + late) else 0.0,
        "avg_late_min": round(sum(late_mins) / len(late_mins), 1) if late_mins else 0.0,
        "by_status": [
            {"status": "Hadir", "count": present}, {"status": "Telat", "count": late},
            {"status": "Cuti/Izin", "count": leave}, {"status": "Alpha", "count": alpha},
        ],
    }

    # ── Turnover (separations = status non-active pada periode; new hires periode) ──
    separations = sum(1 for e in employees if (e.get("status") or "active") != "active"
                      and (e.get("updated_at") or "")[:7] == sel)
    hires_period = sum(1 for e in active if _join(e)[:7] == sel)
    base_hc = len(active) or 1
    turnover = {
        "period": sel, "separations": separations, "headcount": len(active),
        "new_hires": hires_period,
        "turnover_rate": round(separations / base_hc * 100, 1),
    }

    # ── Payroll cost (run periode terpilih) + tren ──
    run = await db.hr_payroll_runs.find_one({**pay_scope, "period": sel}, {"_id": 0})
    t = (run or {}).get("totals", {}) or {}
    payroll = {
        "period": sel, "has_run": bool(run),
        "status": (run or {}).get("status", ""),
        "employees": int(t.get("employees") or 0),
        "gross": round(float(t.get("gross") or 0), 0),
        "net": round(float(t.get("net") or 0), 0),
        "bpjs_emp": round(float(t.get("bpjs_emp") or 0), 0),
        "bpjs_er": round(float(t.get("bpjs_er") or 0), 0),
        "bpjs_total": round(float(t.get("bpjs_emp") or 0) + float(t.get("bpjs_er") or 0), 0),
        "pph21": round(float(t.get("pph21") or 0), 0),
        "commission": round(float(t.get("commission") or 0), 0),
    }
    all_runs = await db.hr_payroll_runs.find(pay_scope, {"_id": 0, "period": 1, "totals": 1}).to_list(1000)
    runs_by_period: Dict[str, Dict[str, Any]] = {}
    for r in all_runs:
        rt = r.get("totals", {}) or {}
        runs_by_period[r.get("period", "")] = {
            "gross": round(float(rt.get("gross") or 0), 0),
            "net": round(float(rt.get("net") or 0), 0),
            "bpjs_total": round(float(rt.get("bpjs_emp") or 0) + float(rt.get("bpjs_er") or 0), 0),
            "pph21": round(float(rt.get("pph21") or 0), 0),
            "employees": int(rt.get("employees") or 0),
        }
    trend_months = _month_range(sel, 6)
    payroll_trend = [{"period": m, **(runs_by_period.get(m) or {"gross": 0, "net": 0, "bpjs_total": 0, "pph21": 0, "employees": 0})}
                     for m in trend_months]

    # ── Overtime trend (approved minutes per periode) ──
    ot_rows = await db.hr_overtime.find({**ot_scope, "status": "approved"}, {"_id": 0}).to_list(20000)
    ot_by_period: Dict[str, Dict[str, float]] = {}
    for o in ot_rows:
        p = o.get("period") or (o.get("date") or "")[:7]
        b = ot_by_period.setdefault(p, {"minutes": 0.0, "count": 0})
        b["minutes"] += float(o.get("minutes") or 0)
        b["count"] += 1
    overtime_trend = []
    for m in trend_months:
        b = ot_by_period.get(m, {"minutes": 0.0, "count": 0})
        overtime_trend.append({"period": m, "minutes": round(b["minutes"], 0),
                               "hours": round(b["minutes"] / 60, 1), "count": int(b["count"])})

    statutory = {
        "period": sel,
        "bpjs_emp": payroll["bpjs_emp"], "bpjs_er": payroll["bpjs_er"],
        "bpjs_total": payroll["bpjs_total"], "pph21": payroll["pph21"],
    }

    return {
        "period": sel, "periods": periods,
        "headcount": headcount, "attendance": attendance, "turnover": turnover,
        "payroll": payroll, "payroll_trend": payroll_trend,
        "overtime_trend": overtime_trend, "statutory": statutory,
    }
