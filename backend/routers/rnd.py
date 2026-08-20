"""FASE F — Router **R&D & DESAIN** (Spesifikasi · Labdip/Proofing · Laporan).

Satu pintu untuk alur yang sebelumnya TIDAK ADA di sistem (KN_18 PS-12/13/14/18/19):
spesifikasi R&D → sample labdip/proofing ke ≥1 supplier → round rnd 1..n ber-bukti →
penilaian → keputusan pemenang → kontrak harga + barang supplier → PR/PO.

RBAC: `rnd` (view/create/submit/assess/decide/manage). Keputusan sensitif (ACC
spesifikasi, pilih pemenang) DIJAGA LAGI oleh kebijakan `rnd.*_roles` di dalam
layanan, sehingga wewenang tidak bisa dilangkahi lewat endpoint.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

import domain_registry as dr
from db import db
from dependencies import audit, current_user, require_permission
from entity_scope import assert_entity_access, entity_ctx, resolve_list_scope
from schemas_rnd import (IssueMaterialBody, ReasonBody, RoundAssessBody, RoundOpenBody,
                         RoundSubmitBody, SampleDecideBody, SampleInput, SamplePatch,
                         SampleSendBody, SpecApproveBody, SpecInput, SpecPatch)
from services import approval_matrix_service as amx  # PS-20 — matriks persetujuan mengikat
from services import rnd_gate
from services import rnd_kpi_export as kpi_export
from services import rnd_kpi_service as kpi
from services import rnd_sample_service as smp
from services import rnd_sla_service as sla_svc
from services import rnd_spec_service as spec_svc
from services import scheduler_service as sched_svc
from services.rnd_spec_service import RndError

router = APIRouter(prefix="/api")


def _err(exc: Exception, code: int = 400) -> HTTPException:
    return HTTPException(status_code=code, detail=str(exc))


async def _spec_guard(spec_id: str, ctx) -> Dict[str, Any]:
    doc = await spec_svc.get_spec(spec_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Spesifikasi tidak ditemukan.")
    assert_entity_access(doc, "md_specs", ctx)
    return doc


async def _sample_guard(sample_id: str, ctx) -> Dict[str, Any]:
    doc = await smp.get_sample(sample_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Permintaan sample tidak ditemukan.")
    assert_entity_access(doc, "md_samples", ctx)
    return doc


# PS-18 — laporan PENILAIAN ORANG (KPI desainer & papan eskalasi) bukan data sample
# biasa: isinya nilai kerja rekan sekantor. `rnd.view` saja tidak cukup karena sales &
# gudang pun memilikinya (mereka perlu melihat permintaan sample, bukan rapor orang).
# Karena itu dibatasi ke peran yang memang menilai — selaras dengan menu "Desainer"
# yang juga hanya tampil untuk admin & manager.
APPRAISAL_ROLES = ("admin", "manager")


def _assert_appraisal_role(actor: Dict[str, Any]) -> None:
    if (actor or {}).get("role") not in APPRAISAL_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Laporan penilaian desainer hanya untuk manager & admin. "
                   "Peran lain tetap bisa melihat permintaan sample dan hasil round-nya "
                   "di menu R&D.")


# ═══ META ══════════════════════════════════════════════════════════════════
@router.get("/rnd/meta")
async def rnd_meta(request: Request, entity_id: str = Query("")) -> Dict[str, Any]:
    """Enum, kebijakan yang BERLAKU, label alasan & statistik untuk layar R&D."""
    await require_permission(request, "rnd", "view")
    ctx = await entity_ctx(request)
    eid = entity_id or ctx.active_entity_id
    scope_spec = resolve_list_scope("md_specs", {}, ctx, entity_id or None)
    scope_smp = resolve_list_scope("md_samples", {}, ctx, entity_id or None)
    return {
        "policy": await rnd_gate.policy(eid),
        "reasons": smp.reasons(),
        "sample_types": dr.enum_items("sample_type"),
        "lifecycles": dr.enum_items("lifecycle"),
        "spec_statuses": list(spec_svc.SPEC_STATUSES),
        "sample_statuses": list(smp.SAMPLE_STATUSES),
        "round_results": list(smp.ROUND_RESULTS),
        "spec_stats": await spec_svc.stats(scope_spec),
        "sample_stats": await smp.stats(scope_smp),
    }


# ═══ SPESIFIKASI (md_specs) ════════════════════════════════════════════════
@router.get("/rnd/specs")
async def list_specs(request: Request, entity_id: Optional[str] = Query(None),
                     q: str = Query(""), status: str = Query(""),
                     lifecycle: str = Query(""),
                     line: str = Query("", description="FASE L — penyaring lini"),
                     limit: int = Query(200, ge=1, le=500)) -> Dict[str, Any]:
    actor = await require_permission(request, "rnd", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("md_specs", {}, ctx, entity_id)
    # FASE L — pagar lini di daftar spesifikasi (dan di `stats` supaya kartu &
    # daftar tidak pernah bercerita beda).
    from services import line_scope as _lines
    scope = _lines.narrow(scope, actor, line)
    rows = await spec_svc.list_specs(scope, q=q, status=status, lifecycle=lifecycle, limit=limit)
    return {"count": len(rows), "items": rows, "stats": await spec_svc.stats(scope)}


@router.post("/rnd/specs")
async def create_spec(payload: SpecInput, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "rnd", "create")
    ctx = await entity_ctx(request)
    try:
        doc = await spec_svc.create_spec(payload.model_dump(), entity_id=ctx.active_entity_id,
                                        actor=actor.get("name", ""))
    except RndError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_spec_created", "md_specs", doc["id"],
                {"number": doc["number"], "title": doc["title"]})
    return doc


@router.get("/rnd/specs/{spec_id}")
async def get_spec(spec_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "rnd", "view")
    ctx = await entity_ctx(request)
    doc = await _spec_guard(spec_id, ctx)
    doc["samples"] = await smp.list_samples({"spec_id": spec_id}, limit=50)
    if doc.get("product_id"):
        doc["product"] = await db.products.find_one({"id": doc["product_id"]}, {"_id": 0})
    return doc


@router.patch("/rnd/specs/{spec_id}")
async def patch_spec(spec_id: str, payload: SpecPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "rnd", "create")
    ctx = await entity_ctx(request)
    await _spec_guard(spec_id, ctx)
    try:
        doc = await spec_svc.patch_spec(spec_id, payload.model_dump(exclude_unset=True),
                                       actor.get("name", ""))
    except RndError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_spec_updated", "md_specs", spec_id,
                payload.model_dump(exclude_unset=True))
    return doc


@router.post("/rnd/specs/{spec_id}/submit")
async def submit_spec(spec_id: str, request: Request) -> Dict[str, Any]:
    # Pengaju spesifikasi (termasuk sales) BOLEH mengajukan miliknya sendiri untuk
    # persetujuan — karena itu izinnya `create`, bukan `submit` (yang dipakai operasi
    # sample ke supplier).
    actor = await require_permission(request, "rnd", "create")
    ctx = await entity_ctx(request)
    await _spec_guard(spec_id, ctx)
    try:
        doc = await spec_svc.submit_spec(spec_id, actor.get("name", ""))
    except RndError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_spec_submitted", "md_specs", spec_id,
                {"number": doc.get("number")})
    return doc


@router.post("/rnd/specs/{spec_id}/approve")
async def approve_spec(spec_id: str, payload: SpecApproveBody, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "rnd", "assess")
    ctx = await entity_ctx(request)
    doc = await _spec_guard(spec_id, ctx)
    # PS-20 (D-14) — matriks persetujuan MENGIKAT untuk tahap "ACC Desain".
    ev = await amx.guard("design_acc", actor, doc, doc.get("entity_id", ""), action="approve")
    try:
        res = await spec_svc.approve_spec(spec_id, payload.model_dump(), actor)
    except RndError as exc:
        raise _err(exc) from exc
    await amx.record(stage="design_acc", action="approve", actor=actor, doc=doc,
                     entity_id=doc.get("entity_id", ""), level=ev.get("level", 1),
                     level_label=ev.get("level_label", ""), outcome="disetujui",
                     note=payload.note or "", enforced=ev.get("enforced", True))
    await audit(actor.get("name", ""), "rnd_spec_approved", "md_specs", spec_id,
                {"number": res["spec"].get("number"), "product": res["product"].get("sku")},
                reason=payload.note or "")
    return res


@router.post("/rnd/specs/{spec_id}/reject")
async def reject_spec(spec_id: str, payload: ReasonBody, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "rnd", "assess")
    ctx = await entity_ctx(request)
    cur = await _spec_guard(spec_id, ctx)
    ev = await amx.guard("design_acc", actor, cur, cur.get("entity_id", ""), action="reject")
    try:
        doc = await spec_svc.reject_spec(spec_id, payload.reason, actor)
    except RndError as exc:
        raise _err(exc) from exc
    await amx.record(stage="design_acc", action="reject", actor=actor, doc=cur,
                     entity_id=cur.get("entity_id", ""), level=ev.get("level", 1),
                     level_label=ev.get("level_label", ""), outcome="ditolak",
                     note=payload.reason or "", enforced=ev.get("enforced", True))
    await audit(actor.get("name", ""), "rnd_spec_rejected", "md_specs", spec_id,
                {"number": doc.get("number")}, reason=payload.reason)
    return doc


@router.post("/rnd/specs/{spec_id}/release-product")
async def release_product(spec_id: str, payload: ReasonBody, request: Request) -> Dict[str, Any]:
    """Rilis ke produksi → produk BOLEH dipesan/dijual (lifecycle `produksi`)."""
    actor = await require_permission(request, "rnd", "decide")
    ctx = await entity_ctx(request)
    await _spec_guard(spec_id, ctx)
    try:
        res = await spec_svc.release_product(spec_id, actor, payload.note or payload.reason)
    except RndError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_product_released", "products",
                res["product"].get("id", ""),
                {"sku": res["product"].get("sku"), "lifecycle": "produksi"},
                reason=payload.reason)
    return res


# ═══ PERMINTAAN SAMPLE (md_samples) ════════════════════════════════════════
@router.get("/rnd/samples")
async def list_samples(request: Request, entity_id: Optional[str] = Query(None),
                       q: str = Query(""), status: str = Query(""),
                       sample_type: str = Query(""), spec_id: str = Query(""),
                       line: str = Query("", description="FASE L — penyaring lini"),
                       limit: int = Query(200, ge=1, le=500)) -> Dict[str, Any]:
    actor = await require_permission(request, "rnd", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("md_samples", {}, ctx, entity_id)
    from services import line_scope as _lines
    scope = _lines.narrow(scope, actor, line)   # FASE L
    rows = await smp.list_samples(scope, q=q, status=status, sample_type=sample_type,
                                  spec_id=spec_id, limit=limit)
    return {"count": len(rows), "items": rows, "stats": await smp.stats(scope)}


@router.post("/rnd/samples")
async def create_sample(payload: SampleInput, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "rnd", "create")
    ctx = await entity_ctx(request)
    try:
        doc = await smp.create_sample(payload.model_dump(), entity_id=ctx.active_entity_id,
                                      actor=actor.get("name", ""))
    except RndError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_sample_created", "md_samples", doc["id"],
                {"number": doc["number"], "type": doc["sample_type"]})
    return doc


@router.get("/rnd/samples/{sample_id}")
async def get_sample(sample_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "rnd", "view")
    ctx = await entity_ctx(request)
    doc = await _sample_guard(sample_id, ctx)
    if doc.get("spec_id"):
        doc["spec"] = await spec_svc.get_spec(doc["spec_id"])
    return doc


@router.patch("/rnd/samples/{sample_id}")
async def patch_sample(sample_id: str, payload: SamplePatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "rnd", "create")
    ctx = await entity_ctx(request)
    await _sample_guard(sample_id, ctx)
    try:
        doc = await smp.patch_sample(sample_id, payload.model_dump(exclude_unset=True),
                                     actor.get("name", ""))
    except RndError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_sample_updated", "md_samples", sample_id,
                payload.model_dump(exclude_unset=True))
    return doc


@router.post("/rnd/samples/{sample_id}/send")
async def send_sample(sample_id: str, payload: SampleSendBody, request: Request) -> Dict[str, Any]:
    """Kirim permintaan ke ≥1 supplier sekaligus (hasilnya bisa dibandingkan)."""
    actor = await require_permission(request, "rnd", "submit")
    ctx = await entity_ctx(request)
    await _sample_guard(sample_id, ctx)
    try:
        doc = await smp.send_sample(sample_id, payload.supplier_ids,
                                    due_date=payload.due_date, note=payload.note,
                                    actor=actor.get("name", ""))
    except RndError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_sample_sent", "md_samples", sample_id,
                {"number": doc.get("number"), "suppliers": payload.supplier_ids})
    return doc


@router.post("/rnd/samples/{sample_id}/rounds")
async def open_round(sample_id: str, payload: RoundOpenBody, request: Request) -> Dict[str, Any]:
    """Buka round berikutnya (rnd 2, 3, …) setelah hasil `revisi`."""
    actor = await require_permission(request, "rnd", "submit")
    ctx = await entity_ctx(request)
    await _sample_guard(sample_id, ctx)
    try:
        doc = await smp.open_round(sample_id, payload.supplier_id, due_date=payload.due_date,
                                   note=payload.note, reason=payload.reason, actor=actor)
    except RndError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_round_opened", "md_samples", sample_id,
                {"supplier_id": payload.supplier_id}, reason=payload.reason or "")
    return doc


@router.post("/rnd/samples/{sample_id}/rounds/{round_id}/attachments")
async def upload_round_file(sample_id: str, round_id: str, request: Request,
                            file: UploadFile = File(...)) -> Dict[str, Any]:
    actor = await require_permission(request, "rnd", "submit")
    ctx = await entity_ctx(request)
    await _sample_guard(sample_id, ctx)
    data = await file.read()
    try:
        meta = await smp.add_attachment(sample_id, round_id, file.filename or "bukti",
                                        file.content_type or "", data, actor.get("name", ""))
    except (RndError, ValueError) as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_round_attachment", "md_samples", sample_id,
                {"round_id": round_id, "file": meta.get("filename")})
    return meta


@router.get("/rnd/samples/{sample_id}/rounds/{round_id}/attachments/{file_id}")
async def download_round_file(sample_id: str, round_id: str, file_id: str, request: Request):
    await require_permission(request, "rnd", "view")
    ctx = await entity_ctx(request)
    await _sample_guard(sample_id, ctx)
    try:
        data, ctype = await smp.get_attachment(sample_id, round_id, file_id)
    except RndError as exc:
        raise _err(exc, 404) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Berkas fisik tidak ditemukan.")
    return Response(content=data, media_type=ctype,
                    headers={"Cache-Control": "private, max-age=300"})


@router.post("/rnd/samples/{sample_id}/rounds/{round_id}/submit")
async def submit_round(sample_id: str, round_id: str, payload: RoundSubmitBody,
                       request: Request) -> Dict[str, Any]:
    """Setor hasil round — lampiran + catatan WAJIB (PS-18)."""
    actor = await require_permission(request, "rnd", "submit")
    ctx = await entity_ctx(request)
    await _sample_guard(sample_id, ctx)
    try:
        doc = await smp.submit_round(sample_id, round_id, payload.model_dump(),
                                     actor.get("name", ""))
    except RndError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_round_submitted", "md_samples", sample_id,
                {"round_id": round_id}, reason=payload.note or "")
    return doc


@router.post("/rnd/samples/{sample_id}/rounds/{round_id}/assess")
async def assess_round(sample_id: str, round_id: str, payload: RoundAssessBody,
                       request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "rnd", "assess")
    ctx = await entity_ctx(request)
    await _sample_guard(sample_id, ctx)
    try:
        doc = await smp.assess_round(sample_id, round_id, payload.model_dump(), actor)
    except RndError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_round_assessed", "md_samples", sample_id,
                {"round_id": round_id, "result": payload.result, "score": payload.score},
                reason=payload.note or "")
    return doc


@router.post("/rnd/samples/{sample_id}/decide")
async def decide_sample(sample_id: str, payload: SampleDecideBody,
                        request: Request) -> Dict[str, Any]:
    """Pilih pemenang → kontrak harga (Fase E) + barang supplier terbentuk."""
    actor = await require_permission(request, "rnd", "decide")
    ctx = await entity_ctx(request)
    cur = await _sample_guard(sample_id, ctx)
    # PS-20 (D-14) — tahap "ACC Sample" kini mengikat (matriks persetujuan divisi).
    ev = await amx.guard("sample_acc", actor, cur, cur.get("entity_id", ""), action="approve")
    try:
        doc = await smp.decide_sample(sample_id, payload.model_dump(), actor)
    except RndError as exc:
        raise _err(exc) from exc
    await amx.record(stage="sample_acc", action="approve", actor=actor, doc=cur,
                     entity_id=cur.get("entity_id", ""), level=ev.get("level", 1),
                     level_label=ev.get("level_label", ""),
                     outcome=f"diputus: {doc.get('decision', {}).get('supplier_name', '')}".strip(),
                     note=payload.note or payload.reason_code or "",
                     enforced=ev.get("enforced", True))
    await audit(actor.get("name", ""), "rnd_sample_decided", "md_samples", sample_id,
                {"number": doc.get("number"), "decision": doc.get("decision")},
                reason=payload.note or payload.reason_code)
    return doc


@router.post("/rnd/samples/{sample_id}/issue-material")
async def issue_material(sample_id: str, payload: IssueMaterialBody,
                         request: Request) -> Dict[str, Any]:
    """PS-19 — ambil bahan dari roll: stok gudang BERKURANG (satu angka stok)."""
    actor = await require_permission(request, "rnd", "submit")
    ctx = await entity_ctx(request)
    await _sample_guard(sample_id, ctx)
    try:
        res = await smp.issue_material(sample_id, payload.model_dump(), actor.get("name", ""))
    except RndError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_sample_material_issued", "md_samples", sample_id,
                {"issue": res["issue"]}, reason=payload.note or "")
    return res


@router.post("/rnd/samples/{sample_id}/cancel")
async def cancel_sample(sample_id: str, payload: ReasonBody, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "rnd", "manage")
    ctx = await entity_ctx(request)
    await _sample_guard(sample_id, ctx)
    try:
        doc = await smp.cancel_sample(sample_id, payload.reason, actor.get("name", ""))
    except RndError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_sample_cancelled", "md_samples", sample_id,
                {"number": doc.get("number")}, reason=payload.reason)
    return doc


# ═══ LAPORAN ═══════════════════════════════════════════════════════════════
@router.get("/rnd/reports/performer")
async def performer_report(request: Request,
                           entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Kinerja pelaksana R&D: jumlah ACC, rata-rata hari per round, skor rata-rata."""
    await require_permission(request, "rnd", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("md_samples", {}, ctx, entity_id)
    rows = await smp.performer_report(scope)
    return {"count": len(rows), "items": rows, "stats": await smp.stats(scope)}


@router.get("/rnd/reports/designer-kpi")
async def designer_kpi_report(request: Request,
                              entity_id: Optional[str] = Query(None),
                              period: str = Query("all", description="month|30d|90d|all"),
                              division: str = Query("", description="filter divisi (PS-17)"),
                              ) -> Dict[str, Any]:
    """PS-18 — **KPI Desainer**: on-time, rework, keterlambatan & grade komposit.

    Semua angka lahir dari jejak round yang sudah wajib ber-bukti — tidak ada input
    manual. Bobot & penalti grade diambil dari Pusat Pengaturan (`rnd.kpi_*`).
    PS-17: `division` menyaring baris ke satu divisi (peringkat tetap global).
    """
    actor = await require_permission(request, "rnd", "view")
    _assert_appraisal_role(actor)
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("md_samples", {}, ctx, entity_id)
    eid = entity_id if entity_id and entity_id != "all" else ctx.active_entity_id
    return await kpi.designer_kpi(scope, period=period, entity_id=eid or "",
                                  division=division)


@router.get("/rnd/reports/my-kpi")
async def my_designer_kpi(request: Request,
                          entity_id: Optional[str] = Query(None),
                          period: str = Query("30d", description="month|30d|90d|all"),
                          ) -> Dict[str, Any]:
    """PS-18 — **KPI Saya**: kartu penilaian MILIK SENDIRI untuk layar Profil Saya.

    Sengaja TANPA `require_permission`: setiap orang berhak melihat nilainya sendiri.
    Yang dijaga adalah kebalikannya — penyaringan nama dilakukan di SERVER sehingga
    nilai rekan **tidak mungkin** ikut terkirim. Dari tim hanya dikembalikan angka
    gabungan (rata-rata & jumlah) plus posisi peringkat, tanpa nama siapa pun.
    """
    user = await current_user(request)
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("md_samples", {}, ctx, entity_id)
    eid = entity_id if entity_id and entity_id != "all" else ctx.active_entity_id
    return await kpi.my_kpi(scope, name=user.get("name", ""), period=period,
                            entity_id=eid or "")


@router.get("/rnd/reports/designer-kpi/trend")
async def designer_kpi_trend_report(request: Request,
                                    entity_id: Optional[str] = Query(None),
                                    months: int = Query(6, ge=3, le=12),
                                    metric: str = Query("grade", description="grade|avg_score"),
                                    ) -> Dict[str, Any]:
    """PS-18 lanjutan — **Tren nilai desainer per bulan** untuk grafik.

    Titik grafik memakai `compute_grade` yang SAMA dengan tabel KPI, hanya round
    disaring per bulan → tren "nilai bila dinilai dari pekerjaan bulan itu".
    """
    actor = await require_permission(request, "rnd", "view")
    _assert_appraisal_role(actor)
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("md_samples", {}, ctx, entity_id)
    eid = entity_id if entity_id and entity_id != "all" else ctx.active_entity_id
    return await kpi.designer_kpi_trend(scope, months=months, metric=metric,
                                        entity_id=eid or "")


@router.get("/rnd/reports/designer-kpi/export")
async def export_designer_kpi(request: Request,
                              entity_id: Optional[str] = Query(None),
                              period: str = Query("all"),
                              format: str = Query("xlsx", description="csv|xlsx|pdf"),
                              ) -> Response:
    """Unduh laporan KPI desainer (CSV / Excel / PDF) untuk dibawa ke rapat bulanan.

    Angka diambil dari fungsi yang SAMA dengan layar, jadi berkas dan layar tidak
    mungkin berbeda.
    """
    actor = await require_permission(request, "rnd", "view")
    _assert_appraisal_role(actor)
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("md_samples", {}, ctx, entity_id)
    eid = entity_id if entity_id and entity_id != "all" else ctx.active_entity_id
    rep = await kpi.designer_kpi(scope, period=period, entity_id=eid or "")
    ent = await db.business_entities.find_one({"id": eid}, {"_id": 0, "name": 1}) or {}
    try:
        data, fname, media = kpi_export.render(rep, format, ent.get("name", ""))
    except ValueError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_designer_kpi_exported", "md_samples",
                "designer-kpi", {"format": format, "period": rep.get("period"),
                                 "rows": rep.get("count")})
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.get("/rnd/reports/designer-kpi/report")
async def designer_kpi_report_pdf(request: Request,
                                  designer: str = Query(..., description="Nama desainer"),
                                  entity_id: Optional[str] = Query(None),
                                  period: str = Query("all"),
                                  format: str = Query("pdf", description="pdf"),
                                  note: str = Query("", max_length=1200,
                                                    description="Catatan evaluasi (opsional)"),
                                  ) -> Response:
    """PS-18 lanjutan — **Rapor per-desainer** (1 halaman PDF) untuk lampiran evaluasi.

    Berisi grade + metrik kunci + pembanding tim AGREGAT + riwayat round terbaru untuk
    SATU orang, plus kotak **Catatan Evaluasi** (opsional, ditulis penilai sebelum
    unduh). Sumber angka sama dengan layar (`my_kpi`), jadi tidak ada hitungan kedua.
    """
    actor = await require_permission(request, "rnd", "view")
    _assert_appraisal_role(actor)
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("md_samples", {}, ctx, entity_id)
    eid = entity_id if entity_id and entity_id != "all" else ctx.active_entity_id
    mine = await kpi.my_kpi(scope, name=designer, period=period, entity_id=eid or "")
    ent = await db.business_entities.find_one({"id": eid}, {"_id": 0, "name": 1}) or {}
    try:
        data, fname, media = kpi_export.render_designer_report(
            mine, format, ent.get("name", ""), note=note)
    except ValueError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "rnd_designer_report_exported", "md_samples",
                "designer-kpi-report", {"designer": designer, "period": mine.get("period"),
                                        "has_note": bool((note or "").strip()),
                                        "grade": (mine.get("me") or {}).get("grade_letter")})
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.get("/rnd/sla/board")
async def sla_board(request: Request,
                    entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Papan eskalasi SLA: round yang masih berjalan tetapi sudah lewat tenggat."""
    actor = await require_permission(request, "rnd", "view")
    _assert_appraisal_role(actor)
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("md_samples", {}, ctx, entity_id)
    eid = entity_id if entity_id and entity_id != "all" else ctx.active_entity_id
    return await sla_svc.board(scope, entity_id=eid or "")


@router.post("/rnd/sla/escalate")
async def run_sla_escalation(request: Request) -> Dict[str, Any]:
    """Jalankan eskalasi SLA SEKARANG (tanpa menunggu jadwal 07:35 WIB).

    Idempotent: notifikasi disaring sekali per hari per round, jadi menekan tombol
    ini berulang kali tidak membanjiri manager/admin.
    """
    actor = await require_permission(request, "rnd", "manage")
    run = await sched_svc.run_job("rnd_sla_escalation", trigger="manual",
                                  actor=actor.get("name", ""))
    await audit(actor.get("name", ""), "rnd_sla_escalation_run", "md_samples", "sla",
                {"status": run.get("status"), "created": run.get("created"),
                 "scanned": run.get("scanned")})
    return run


@router.get("/rnd/lifecycle-board")
async def lifecycle_board(request: Request,
                          entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Papan lifecycle produk — berapa produk di setiap tahap & mana yang belum sah dijual."""
    await require_permission(request, "rnd", "view")
    ctx = await entity_ctx(request)
    eid = entity_id or ctx.active_entity_id
    rows = await db.products.find(
        {}, {"_id": 0, "id": 1, "sku": 1, "name": 1, "lifecycle": 1, "spec_id": 1,
             "status": 1}).to_list(5000)
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for p in rows:
        buckets.setdefault(rnd_gate.lifecycle_of(p), []).append(p)
    return {
        "enforcement": await rnd_gate.enforcement_mode(eid),
        "counts": {k: len(v) for k, v in buckets.items()},
        "not_orderable": [p for p in rows if not rnd_gate.is_orderable(p)][:200],
        "total": len(rows),
    }
