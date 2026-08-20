"""QC 4-Point Inspection router — Fase 6.2 (P1).

Inspeksi per-roll saat QC (task qc_pending): catat poin defect (4-point) + GSM/lebar
aktual → set Grade roll (A/B/C, ambang configurable). Tanpa aksi karantina otomatis.

Permission: pakai modul `wms` (sejalan dengan QC queue/keputusan existing).
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from db import db
from dependencies import require_permission, audit
from core_utils import safe_doc
from schemas import RollGradeOverrideIn, RollInspectionInput
from services.qc_inspection_service import rolls_for_task, inspect_roll, grade_thresholds
from services.lot_service import LotError
from services import grade_service
from domain_registry import DomainValidationError
from entity_scope import entity_ctx, assert_entity_access

router = APIRouter(prefix="/api")


@router.get("/qc/grade-thresholds")
async def get_grade_thresholds(request: Request, entity_id: str = None) -> Dict[str, Any]:
    """Ambang grade 4-point aktif (untuk preview di UI)."""
    await require_permission(request, "wms", "view")
    return await grade_thresholds(entity_id)


@router.get("/inbound/qc/tasks/{task_id}/rolls")
async def list_task_rolls(task_id: str, request: Request) -> List[Dict[str, Any]]:
    """Roll milik 1 inbound task untuk diinspeksi (per qc_task_id)."""
    await require_permission(request, "wms", "view")
    task = await db.wms_tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Inbound task tidak ditemukan")
    return await rolls_for_task(task_id)


@router.post("/inbound/rolls/{roll_id}/inspect")
async def inspect(roll_id: str, payload: RollInspectionInput, request: Request) -> Dict[str, Any]:
    """Catat inspeksi 4-point pada 1 roll → hitung poin & set grade."""
    actor = await require_permission(request, "wms", "update")
    roll = safe_doc(await db.inventory_rolls.find_one({"id": roll_id}, {"_id": 0}))
    if not roll:
        raise HTTPException(status_code=404, detail="Roll tidak ditemukan")
    assert_entity_access(roll, "inventory_rolls", await entity_ctx(request))  # S#074 IDOR-WRITE

    # FASE G-0 — `qc.four_point_enabled` DULU setting mati (0 consumer). Sekarang benar-benar
    # mengendalikan alur: bila dimatikan, inspeksi 4-point tidak dipakai dan grade ditetapkan
    # lewat "Set Grade Manual" (endpoint /grade-override) agar tidak ada dua sumber kebenaran.
    from services.config_resolver import value_of as _cfg_value
    if not bool(await _cfg_value("qc.four_point_enabled",
                                 {"entity_id": roll.get("owner_entity_id")})):
        raise HTTPException(
            status_code=400,
            detail=("Inspeksi 4-Point dimatikan di Pengaturan → Kualitas (QC). "
                    "Tetapkan grade lewat 'Set Grade Manual' pada roll ini, atau aktifkan "
                    "kembali 'Aktifkan inspeksi 4-Point'."))

    defects = [d.dict() for d in (payload.defects or [])]
    for d in defects:
        if int(d.get("point_value", 0) or 0) not in (1, 2, 3, 4):
            raise HTTPException(status_code=400, detail="point_value defect harus 1..4")
        if int(d.get("count", 0) or 0) < 0:
            raise HTTPException(status_code=400, detail="count defect tak boleh negatif")

    try:
        result = await inspect_roll(roll, defects, payload.gsm_actual, payload.width_actual,
                                    payload.note or "", actor,
                                    supplier_lot=payload.supplier_lot, dye_lot=payload.dye_lot,
                                    shade_ref=payload.shade_ref)
    except LotError as exc:   # FASE C · D-27 mode `block` → pesan dapat ditindak
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor["name"], "roll_inspected", "inventory_roll", roll_id,
                {"roll_no": roll.get("roll_no"), "points": result["points"],
                 "grade": result["grade"], "lot": (result.get("lot") or {}).get("lot_number", "")})
    return result


# ─── Fase A · PS-09/D-23 — Tata kelola perubahan grade roll ───────────────────

@router.get("/inventory/rolls/{roll_id}/grade-history")
async def roll_grade_history(roll_id: str, request: Request) -> Dict[str, Any]:
    """Riwayat perubahan grade satu roll (before → after, sumber, alasan, aktor)."""
    await require_permission(request, "wms", "view")
    roll = safe_doc(await db.inventory_rolls.find_one({"id": roll_id}, {"_id": 0}))
    if not roll:
        raise HTTPException(status_code=404, detail="Roll tidak ditemukan")
    history = await grade_service.grade_history(roll_id)
    return {"roll_id": roll_id, "roll_no": roll.get("roll_no", ""),
            "grade": roll.get("grade", ""), "grade_source": roll.get("grade_source", ""),
            "grade_updated_at": roll.get("grade_updated_at", ""),
            "count": len(history), "history": history}


@router.post("/inventory/rolls/{roll_id}/grade-override")
async def roll_grade_override(roll_id: str, payload: RollGradeOverrideIn,
                              request: Request) -> Dict[str, Any]:
    """Koreksi grade roll TANPA inspeksi — hanya manager/admin, alasan WAJIB (D-23).

    Jalur normal perubahan grade adalah inspeksi QC; endpoint ini untuk koreksi
    salah input / kasus darurat dan SELALU menulis `grade_history` + audit log.
    """
    actor = await require_permission(request, "wms", "approve")   # admin & manager saja
    roll = safe_doc(await db.inventory_rolls.find_one({"id": roll_id}, {"_id": 0}))
    if not roll:
        raise HTTPException(status_code=404, detail="Roll tidak ditemukan")
    assert_entity_access(roll, "inventory_rolls", await entity_ctx(request))
    try:
        result = await grade_service.set_roll_grade(
            roll_id, payload.grade, source="manager_override",
            reason=payload.reason, actor=actor,
            extra={"roll_no": roll.get("roll_no", "")})
    except DomainValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return result
