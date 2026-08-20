"""FASE G-8 — Router **REKONSILIASI BANK** (parser multi-bank · skor · split · titipan).

Satu pintu untuk: template format bank, pratinjau impor, impor berkas, cocokkan otomatis
(3 pita: otomatis / usulan / manual), kandidat berperingkat, cocok manual 1:1, split 1:N,
gabung N:1, aturan hasil pembelajaran, dan **titipan dana belum teridentifikasi**.

RBAC: memakai modul izin `cash` yang SUDAH ADA (tidak menambah modul izin baru).
  * `cash:view`   → melihat mutasi, skor, usulan, ringkasan, aturan
  * `cash:create` → impor, cocokkan, titipkan, alokasikan titipan, memutus aturan

ISOLASI ENTITAS: setiap endpoint menghitung `entity_ids` lewat `resolve_scope_ids(ctx)`
lalu meneruskannya ke service. Akun/baris/transaksi milik PT lain → **403**, termasuk bila
id-nya dikirim eksplisit. Sebelum FASE G-8 celah ini terbuka (lihat POC G-8 bukti-merah).

Respons OBJEK/ARRAY telanjang (konsisten dgn `bank.py`).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from dependencies import audit, require_permission
from entity_scope import EntityContext, entity_ctx, resolve_scope_ids
from services import bank_recon_service as svc

router = APIRouter(prefix="/api")


def _ids(ctx: EntityContext, entity_id: Optional[str] = None) -> List[str]:
    return resolve_scope_ids(ctx, entity_id)


def _actor_name(actor: Dict[str, Any]) -> str:
    return actor.get("name", actor.get("email", ""))


# ── Skema masukan ────────────────────────────────────────────────────────────
class StatementLineIn(BaseModel):
    stmt_date: str = ""
    amount: float = 0
    direction: str = "out"
    description: str = ""
    ref: Optional[str] = ""
    external_id: Optional[str] = ""


class StatementImportInput(BaseModel):
    bank_account_id: str
    entity_id: Optional[str] = ""
    lines: List[StatementLineIn] = Field(default_factory=list)


class RawImportInput(BaseModel):
    bank_account_id: str
    raw: str = ""
    format_id: Optional[str] = ""
    fmt: Optional[Dict[str, Any]] = None
    year_hint: Optional[int] = 0


class PreviewInput(BaseModel):
    raw: str = ""
    format_id: Optional[str] = ""
    fmt: Optional[Dict[str, Any]] = None
    year_hint: Optional[int] = 0


class AutoMatchInput(BaseModel):
    bank_account_id: str
    window_days: Optional[int] = None
    amount_tol: Optional[float] = None


class ManualMatchInput(BaseModel):
    txn_id: str


class SplitInput(BaseModel):
    allocations: List[Dict[str, Any]] = Field(default_factory=list)


class GroupInput(BaseModel):
    line_ids: List[str] = Field(default_factory=list)
    txn_id: str


class IgnoreInput(BaseModel):
    note: Optional[str] = ""


class BookChargeInput(BaseModel):
    """FASE G-8 — baris rekening koran yang memang tidak ada di buku.

    `kind`: `charge` (biaya administrasi/transfer bank, dana KELUAR) atau
    `interest` (bunga · jasa giro, dana MASUK).
    """
    kind: str = "charge"
    note: Optional[str] = ""


class HoldingInput(BaseModel):
    note: Optional[str] = ""


class HoldingAllocateInput(BaseModel):
    customer_id: Optional[str] = ""
    reason_code: str = ""
    note: Optional[str] = ""
    allocations: List[Dict[str, Any]] = Field(default_factory=list)


class RuleDecisionInput(BaseModel):
    action: str = "activate"      # activate | reject | suspend


class FormatInput(BaseModel):
    id: Optional[str] = ""
    name: str = ""
    bank_code: Optional[str] = "generic"
    file_kind: Optional[str] = "csv"
    delimiter: Optional[str] = ","
    has_header: Optional[bool] = True
    skip_rows: Optional[int] = 0
    decimal_style: Optional[str] = "auto"
    date_format: Optional[str] = "auto"
    columns: Dict[str, Any] = Field(default_factory=dict)
    in_markers: List[str] = Field(default_factory=list)
    out_markers: List[str] = Field(default_factory=list)
    header_signature: List[str] = Field(default_factory=list)
    note: Optional[str] = ""
    active: Optional[bool] = True


def _bad(e: Exception):
    if isinstance(e, HTTPException):
        raise e
    raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════ TEMPLATE FORMAT BANK ════════════════════════════════
@router.get("/bank-reconciliation/formats")
async def list_formats(request: Request, ctx: EntityContext = Depends(entity_ctx),
                       entity_id: str = Query(None)) -> List[Dict[str, Any]]:
    actor = await require_permission(request, "cash", "view")
    return await svc.list_formats(_ids(ctx, entity_id), ctx.active_entity_id, _actor_name(actor))


@router.post("/bank-reconciliation/formats")
async def upsert_format(payload: FormatInput, request: Request,
                        ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.upsert_format(payload.model_dump(exclude_none=True),
                                      ctx.active_entity_id, _actor_name(actor), _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_format_saved", "bank_statement_format",
                res.get("id", ""), {"name": res.get("name", "")})
    return res


@router.delete("/bank-reconciliation/formats/{format_id}")
async def delete_format(format_id: str, request: Request,
                        ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        await svc.delete_format(format_id, _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_format_deleted", "bank_statement_format", format_id, {})
    return {"ok": True, "id": format_id}


@router.post("/bank-reconciliation/preview")
async def preview_statement(payload: PreviewInput, request: Request,
                            ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    await require_permission(request, "cash", "view")
    try:
        return await svc.preview(payload.raw, payload.format_id or "", payload.fmt,
                                 _ids(ctx), ctx.active_entity_id, int(payload.year_hint or 0))
    except Exception as e:  # noqa: BLE001
        _bad(e)


# ═══════════════════════ IMPOR ═══════════════════════════════════════════════
@router.post("/bank-reconciliation/import")
async def import_statement(payload: StatementImportInput, request: Request,
                           ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.import_lines(payload.bank_account_id, payload.entity_id or "",
                                     [l.model_dump() for l in payload.lines],
                                     _actor_name(actor), _ids(ctx), ctx.active_entity_id)
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_statement_imported", "bank_account",
                payload.bank_account_id, {"imported": res["imported"], "skipped": res["skipped"]})
    return res


@router.post("/bank-reconciliation/import-file")
async def import_file(payload: RawImportInput, request: Request,
                      ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.import_raw(payload.bank_account_id, payload.raw,
                                   payload.format_id or "", payload.fmt, _ids(ctx),
                                   ctx.active_entity_id, _actor_name(actor),
                                   int(payload.year_hint or 0))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_statement_imported_file", "bank_account",
                payload.bank_account_id,
                {"imported": res["imported"], "skipped": res["skipped"],
                 "format": res.get("format_name", "")})
    return res


# ═══════════════════════ PENCOCOKAN ══════════════════════════════════════════
@router.post("/bank-reconciliation/auto-match")
async def auto_match(payload: AutoMatchInput, request: Request,
                     ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.auto_match(payload.bank_account_id, _ids(ctx), payload.window_days,
                                   payload.amount_tol, _actor_name(actor), ctx.active_entity_id)
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_auto_matched", "bank_account",
                payload.bank_account_id, res)
    return res


@router.get("/bank-reconciliation/lines")
async def list_lines(request: Request, ctx: EntityContext = Depends(entity_ctx),
                     bank_account_id: str = Query(...), status: str = Query(None),
                     start: str = Query(None), end: str = Query(None),
                     entity_id: str = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "cash", "view")
    try:
        return await svc.list_lines(bank_account_id, _ids(ctx, entity_id), status, start, end)
    except Exception as e:  # noqa: BLE001
        _bad(e)


@router.get("/bank-reconciliation/lines/{line_id}/candidates")
async def line_candidates(line_id: str, request: Request,
                          ctx: EntityContext = Depends(entity_ctx),
                          limit: int = Query(8)) -> Dict[str, Any]:
    await require_permission(request, "cash", "view")
    try:
        return await svc.candidates(line_id, _ids(ctx), limit)
    except Exception as e:  # noqa: BLE001
        _bad(e)


@router.get("/bank-reconciliation/summary")
async def recon_summary(request: Request, ctx: EntityContext = Depends(entity_ctx),
                        bank_account_id: str = Query(...), start: str = Query(None),
                        end: str = Query(None), entity_id: str = Query(None)) -> Dict[str, Any]:
    await require_permission(request, "cash", "view")
    try:
        return await svc.summary(bank_account_id, _ids(ctx, entity_id), start, end)
    except Exception as e:  # noqa: BLE001
        _bad(e)


@router.post("/bank-reconciliation/lines/{line_id}/match")
async def match_line(line_id: str, payload: ManualMatchInput, request: Request,
                     ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.manual_match(line_id, payload.txn_id, _actor_name(actor), _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_line_matched", "bank_statement_line", line_id,
                {"txn_id": payload.txn_id})
    return res


@router.post("/bank-reconciliation/lines/{line_id}/match-split")
async def match_split(line_id: str, payload: SplitInput, request: Request,
                      ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.match_split(line_id, payload.allocations, _actor_name(actor), _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_line_split_matched", "bank_statement_line", line_id,
                {"allocations": len(payload.allocations)})
    return res


@router.post("/bank-reconciliation/match-group")
async def match_group(payload: GroupInput, request: Request,
                      ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.match_group(payload.line_ids, payload.txn_id, _actor_name(actor), _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_lines_group_matched", "cash_transaction",
                payload.txn_id, {"lines": len(payload.line_ids)})
    return res


@router.post("/bank-reconciliation/lines/{line_id}/unmatch")
async def unmatch_line(line_id: str, request: Request,
                       ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.unmatch(line_id, _actor_name(actor), _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_line_unmatched", "bank_statement_line", line_id, {})
    return res


@router.post("/bank-reconciliation/lines/{line_id}/ignore")
async def ignore_line(line_id: str, payload: IgnoreInput, request: Request,
                      ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.ignore_line(line_id, _actor_name(actor), _ids(ctx), payload.note or "")
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_line_ignored", "bank_statement_line", line_id,
                {"note": payload.note or ""})
    return res


@router.post("/bank-reconciliation/lines/{line_id}/unignore")
async def unignore_line(line_id: str, request: Request,
                        ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.unignore_line(line_id, _actor_name(actor), _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_line_unignored", "bank_statement_line", line_id, {})
    return res


# ═══════════════════════ BIAYA / BUNGA BANK ══════════════════════════════════
@router.post("/bank-reconciliation/lines/{line_id}/book-charge")
async def book_charge(line_id: str, payload: BookChargeInput, request: Request,
                      ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    """Baris rekening koran tanpa pasangan di buku (biaya adm bank / bunga · jasa giro)
    dibukukan langsung: transaksi kas + jurnal terbit, lalu baris tertaut ke kas itu."""
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.book_charge(line_id, payload.kind, payload.note or "",
                                    _actor_name(actor), _ids(ctx), ctx.active_entity_id)
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_line_booked_charge", "bank_statement_line", line_id,
                {"kind": payload.kind, "account_code": res.get("account_code", ""),
                 "cash_number": res.get("cash_number", "")})
    return res


# ═══════════════════════ ATURAN PEMBELAJARAN ═════════════════════════════════
@router.get("/bank-reconciliation/rules")
async def list_rules(request: Request, ctx: EntityContext = Depends(entity_ctx),
                     bank_account_id: str = Query(None), status: str = Query(None),
                     entity_id: str = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "cash", "view")
    return await svc.list_rules(_ids(ctx, entity_id), bank_account_id or "", status or "")


@router.post("/bank-reconciliation/rules/{rule_id}/decide")
async def decide_rule(rule_id: str, payload: RuleDecisionInput, request: Request,
                      ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.decide_rule(rule_id, payload.action, _actor_name(actor), _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_rule_decided", "bank_match_rule", rule_id,
                {"action": payload.action})
    return res


# ═══════════════════════ TITIPAN DANA ════════════════════════════════════════
@router.get("/bank-reconciliation/holding")
async def holding_queue(request: Request, ctx: EntityContext = Depends(entity_ctx),
                        bank_account_id: str = Query(None),
                        entity_id: str = Query(None)) -> Dict[str, Any]:
    await require_permission(request, "cash", "view")
    return await svc.holding_summary(_ids(ctx, entity_id), bank_account_id or "")


@router.post("/bank-reconciliation/lines/{line_id}/holding")
async def to_holding(line_id: str, payload: HoldingInput, request: Request,
                     ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.to_holding(line_id, payload.note or "", _actor_name(actor),
                                   _ids(ctx), ctx.active_entity_id)
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_line_to_holding", "bank_statement_line", line_id,
                {"note": payload.note or ""})
    return res


@router.post("/bank-reconciliation/lines/{line_id}/holding/allocate")
async def allocate_holding(line_id: str, payload: HoldingAllocateInput, request: Request,
                           ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.allocate_holding(line_id, payload.allocations, payload.customer_id or "",
                                         payload.reason_code, payload.note or "",
                                         _actor_name(actor), _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_holding_allocated", "bank_statement_line", line_id,
                {"allocated": res.get("allocated_now"), "reason_code": payload.reason_code})
    return res


@router.post("/bank-reconciliation/lines/{line_id}/holding/cancel")
async def cancel_holding(line_id: str, request: Request,
                         ctx: EntityContext = Depends(entity_ctx)) -> Dict[str, Any]:
    actor = await require_permission(request, "cash", "create")
    try:
        res = await svc.cancel_holding(line_id, _actor_name(actor), _ids(ctx))
    except Exception as e:  # noqa: BLE001
        _bad(e)
    await audit(_actor_name(actor), "bank_holding_cancelled", "bank_statement_line", line_id, {})
    return res
