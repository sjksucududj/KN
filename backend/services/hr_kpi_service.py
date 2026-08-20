"""HRD H5 services — KPI Design (input manual per karyawan/periode + rekap).

Koleksi kanonik (entity-scoped): `hr_kpi` (hkpi_). Keputusan owner 2a: metrik
bebas (nama metrik, target, aktual, skor, catatan, bobot). Skor auto bila kosong:
`round(min(actual/target,1.5)*100)` (guard target>0). Lihat PLAN_HRD §H5.
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso, safe_doc


def compute_score(target: float, actual: float, score: Optional[float] = None) -> float:
    """Skor 0–150. Bila `score` diisi eksplisit → pakai itu (clamp 0..150).
    Bila None → auto: min(actual/target,1.5)*100 (guard target>0)."""
    if score is not None:
        try:
            return round(max(0.0, min(float(score), 150.0)), 1)
        except (TypeError, ValueError):
            pass
    try:
        t = float(target or 0)
        a = float(actual or 0)
    except (TypeError, ValueError):
        return 0.0
    if t <= 0:
        return 0.0
    return round(min(a / t, 1.5) * 100, 1)


async def submit_kpi(emp: Dict[str, Any], payload: Dict[str, Any], actor_name: str) -> Dict[str, Any]:
    metric = (payload.get("metric") or "").strip()
    if not metric:
        raise ValueError("Nama metrik KPI wajib diisi.")
    period = (payload.get("period") or "")[:7]
    if len(period) != 7 or period[4] != "-":
        raise ValueError("Periode harus format YYYY-MM.")
    target = float(payload.get("target") or 0)
    actual = float(payload.get("actual") or 0)
    score = compute_score(target, actual, payload.get("score"))
    entity_id = emp.get("entity_id", "")
    doc = {
        "id": new_id("hkpi"),
        "employee_id": emp["id"], "employee_name": emp.get("name", ""),
        "entity_id": entity_id, "period": period,
        "metric": metric, "target": round(target, 2), "actual": round(actual, 2),
        "score": score, "weight": float(payload.get("weight") or 1),
        "note": payload.get("note", ""), "status": "recorded",
        "created_by": actor_name, "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.hr_kpi.insert_one(doc)
    return safe_doc(doc)


async def update_kpi(kpi_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    from pymongo import ReturnDocument
    cur = await db.hr_kpi.find_one({"id": kpi_id}, {"_id": 0})
    if not cur:
        raise ValueError("Data KPI tidak ditemukan.")
    updates: Dict[str, Any] = {}
    for f in ("metric", "period", "note"):
        if patch.get(f) is not None:
            updates[f] = patch[f]
    for f in ("target", "actual", "weight"):
        if patch.get(f) is not None:
            updates[f] = float(patch[f])
    # hitung ulang skor: pakai nilai baru bila ada, fallback ke tersimpan
    new_target = updates.get("target", cur.get("target"))
    new_actual = updates.get("actual", cur.get("actual"))
    if "score" in patch:  # explicit (boleh None → auto)
        updates["score"] = compute_score(new_target, new_actual, patch.get("score"))
    elif any(k in updates for k in ("target", "actual")):
        updates["score"] = compute_score(new_target, new_actual, None)
    if not updates:
        raise ValueError("Tidak ada field valid untuk diupdate.")
    updates["updated_at"] = now_iso()
    doc = await db.hr_kpi.find_one_and_update(
        {"id": kpi_id}, {"$set": updates},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    return safe_doc(doc)


async def delete_kpi(kpi_id: str) -> Dict[str, Any]:
    cur = await db.hr_kpi.find_one({"id": kpi_id}, {"_id": 0})
    if not cur:
        raise ValueError("Data KPI tidak ditemukan.")
    await db.hr_kpi.delete_one({"id": kpi_id})
    return {"id": kpi_id, "deleted": True}


async def list_kpi(scope: Dict[str, Any], employee_id: Optional[str] = None,
                   period: Optional[str] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = dict(scope or {})
    if employee_id:
        q["employee_id"] = employee_id
    if period:
        q["period"] = period
    rows = await db.hr_kpi.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return [safe_doc(r) for r in rows]


async def my_kpi(emp: Dict[str, Any]) -> Dict[str, Any]:
    rows = await db.hr_kpi.find(
        {"employee_id": emp["id"]}, {"_id": 0}).sort("period", -1).to_list(500)
    rows = [safe_doc(r) for r in rows]
    periods = sorted({r.get("period", "") for r in rows if r.get("period")}, reverse=True)
    latest_period = periods[0] if periods else ""
    latest = [r for r in rows if r.get("period") == latest_period]
    avg = _weighted_avg(latest)
    return {
        "employee": {"id": emp["id"], "name": emp.get("name", "")},
        "latest_period": latest_period, "latest_score": avg,
        "latest": latest, "all": rows, "periods": periods,
    }


def _weighted_avg(rows: List[Dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    tw = sum(float(r.get("weight") or 1) for r in rows) or 1
    s = sum(float(r.get("score") or 0) * float(r.get("weight") or 1) for r in rows)
    return round(s / tw, 1)
