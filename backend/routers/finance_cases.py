"""FASE G-9 — Router **PUSAT KASUS KEUANGAN** (Finance Exception Desk).

Satu pintu untuk: daftar playbook (sumber wizard di layar), inbox kasus, ringkasan,
tindakan (tugaskan · catatan/bukti · selesaikan · tolak · buka ulang), pemindai kasus
otomatis, dan label alasan (taksonomi G-1).

RBAC: modul izin baru **`finance_case`**
  * `view`    → inbox, detail, ringkasan, playbook, label alasan
  * `create`  → buat kasus manual, tambah catatan/bukti, tugaskan, jalankan pemindai
  * `resolve` → selesaikan / tolak / buka ulang kasus

ISOLASI ENTITAS: setiap endpoint menghitung `entity_ids` lewat `resolve_scope_ids(ctx)`
lalu meneruskannya ke service — kasus milik PT lain menghasilkan **403**, termasuk bila
id-nya dikirim eksplisit.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from dependencies import audit, require_permission
from entity_scope import EntityContext, entity_ctx, resolve_scope_ids
from schemas_finance_case import (
    CaseAssignInput, CaseCreate, CaseNoteInput, CaseRejectInput, CaseResolveInput,
)
from services import finance_case_scan as scanner
from services import finance_case_service as svc
from services.finance_case_playbooks import PLAYBOOKS

router = APIRouter(prefix="/api")


def _ids(ctx: EntityContext, entity_id: Optional[str] = None) -> List[str]:
    return resolve_scope_ids(ctx, entity_id)


def _bad(e: Exception) -> None:
    if isinstance(e, HTTPException):
        raise e
    raise HTTPException(status_code=400, detail=str(e))


# ── Referensi (playbook & label alasan) ──────────────────────────────────────
@router.get("/finance-cases/playbooks")
async def list_playbooks(request: Request) -> List[Dict[str, Any]]:
    """Daftar 11 playbook — dipakai wizard di layar supaya langkahnya satu sumber."""
    await require_permission(request, "finance_case", "view")
    return PLAYBOOKS


@router.get("/finance-cases/reasons")
async def list_reasons(request: Request) -> List[Dict[str, Any]]:
    await require_permission(request, "finance_case", "view")
    return await svc.reasons()


@router.get("/finance-cases/policy")
async def get_policy(request: Request,
                     ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    """Kebijakan berlaku (SLA, ambang persetujuan, jendela duplikat) dari Pusat Pengaturan."""
    await require_permission(request, "finance_case", "view")
    return await svc.policy(ctx.active_entity_id or "")


@router.get("/finance-cases/stats")
async def get_stats(request: Request,
                    ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    await require_permission(request, "finance_case", "view")
    return await svc.stats(_ids(ctx))


# ── Inbox & detail ───────────────────────────────────────────────────────────
@router.get("/finance-cases")
async def list_cases(request: Request, ctx: EntityContext = Depends(entity_ctx),
                     status: str = Query("", description="open|in_progress|resolved|rejected"),
                     case_type: str = Query(""), assignee: str = Query(""),
                     overdue_only: bool = Query(False),
                     limit: int = Query(200, ge=1, le=1000)) -> List[Dict[str, Any]]:
    await require_permission(request, "finance_case", "view")
    try:
        return await svc.list_cases(_ids(ctx), status, case_type, assignee,
                                    overdue_only, limit)
    except Exception as e:  # noqa: BLE001
        _bad(e)


@router.get("/finance-cases/{case_id}")
async def get_case(case_id: str, request: Request,
                   ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    await require_permission(request, "finance_case", "view")
    try:
        return await svc.get(case_id, _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)


@router.post("/finance-cases")
async def create_case(payload: CaseCreate, request: Request,
                      ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "finance_case", "create")
    try:
        case = await svc.create_case(payload.model_dump(), actor, _ids(ctx),
                                     ctx.active_entity_id or "")
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(actor.get("name", ""), "finance_case_created", "finance_case", case["id"],
                {"number": case["number"], "case_type": case["case_type"],
                 "amount": case["amount"]})
    return case


# ── Tindakan ────────────────────────────────────────────────────────────────
@router.post("/finance-cases/{case_id}/assign")
async def assign_case(case_id: str, payload: CaseAssignInput, request: Request,
                      ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "finance_case", "create")
    try:
        case = await svc.assign(case_id, payload.assignee, actor, _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(actor.get("name", ""), "finance_case_assigned", "finance_case", case_id,
                {"assignee": payload.assignee})
    return case


@router.post("/finance-cases/{case_id}/note")
async def add_note(case_id: str, payload: CaseNoteInput, request: Request,
                   ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "finance_case", "create")
    try:
        case = await svc.add_note(case_id, payload.note, payload.attachments, actor, _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(actor.get("name", ""), "finance_case_note_added", "finance_case", case_id,
                {"attachments": len(payload.attachments or [])})
    return case


@router.post("/finance-cases/{case_id}/resolve")
async def resolve_case(case_id: str, payload: CaseResolveInput, request: Request,
                       ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "finance_case", "resolve")
    body = payload.model_dump()
    body["allocations"] = [a.model_dump() for a in (payload.allocations or [])]
    try:
        case = await svc.resolve(case_id, body, actor, _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(actor.get("name", ""), "finance_case_resolved", "finance_case", case_id,
                {"number": case["number"], "action": payload.action,
                 "reason_code": payload.reason_code,
                 "documents": len(case.get("documents") or []),
                 "status": case.get("status")})
    return case


@router.post("/finance-cases/{case_id}/reject")
async def reject_case(case_id: str, payload: CaseRejectInput, request: Request,
                      ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "finance_case", "resolve")
    try:
        case = await svc.reject(case_id, payload.reason_code, payload.note, actor, _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(actor.get("name", ""), "finance_case_rejected", "finance_case", case_id,
                {"reason_code": payload.reason_code})
    return case


@router.post("/finance-cases/{case_id}/reopen")
async def reopen_case(case_id: str, payload: CaseNoteInput, request: Request,
                      ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "finance_case", "resolve")
    try:
        case = await svc.reopen(case_id, payload.note, actor, _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(actor.get("name", ""), "finance_case_reopened", "finance_case", case_id, {})
    return case


# ── Pemindai otomatis ────────────────────────────────────────────────────────
@router.post("/finance-cases/scan")
async def run_scan(request: Request) -> Dict[str, Any]:
    """Cari titipan dana menganggur & pembayaran dobel → buat kasusnya (idempoten)."""
    actor = await require_permission(request, "finance_case", "create")
    try:
        res = await scanner.scan(actor.get("name", "sistem"))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(actor.get("name", ""), "finance_case_scanned", "finance_case", "scan", res)
    return res
