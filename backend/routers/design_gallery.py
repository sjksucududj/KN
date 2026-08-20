"""HRD H5 router — Design Gallery (motif kain) + upload gambar + AI auto-tag.

Koleksi kanonik (entity-scoped): design_gallery (dsgn_). Keputusan owner 3a.
RBAC: read list/detail/file = hr.view; create/update/delete/upload/autotag = hr.manage_attendance.
Auto-tag AI (Claude) GRACEFUL: bila key kosong → 200 {enabled:false} (BUKAN error).

Path aksi pakai segmen literal (/files, /autotag) agar verify_api_contract 0 ERROR.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, Query, UploadFile, File
from fastapi.responses import Response

from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas_design_gallery import (DesignApproveIn, DesignRatingIn, DesignRejectIn,
                                    DesignVersionIn, GalleryInput, GalleryUpdate)
from services import design_gallery_service as gallery

router = APIRouter(prefix="/api")


async def _perm_view(request: Request) -> Dict[str, Any]:
    """RBAC DUA DIVISI (FASE F): HRD (`hr.view`) **atau** R&D (`rnd.view`).

    Master desain dipakai dua divisi sekaligus — HRD (galeri motif/cerita) dan R&D
    (pattern untuk proofing). Memaksa satu izin akan mematikan salah satu alur,
    karena itu keduanya diterima. Tidak ada wewenang lama yang dicabut.
    """
    try:
        return await require_permission(request, "rnd", "view")
    except HTTPException:
        return await require_permission(request, "hr", "view")


async def _perm_manage(request: Request) -> Dict[str, Any]:
    """Tulis master desain: `rnd.manage` **atau** `hr.manage_attendance` (admin/manager)."""
    try:
        return await require_permission(request, "rnd", "manage")
    except HTTPException:
        return await require_permission(request, "hr", "manage_attendance")


async def _guard(gallery_id: str, ctx) -> Dict[str, Any]:
    doc = await gallery.get_gallery(gallery_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Entri galeri tidak ditemukan.")
    assert_entity_access(doc, "design_gallery", ctx)
    return doc


@router.get("/design-gallery")
async def list_gallery(request: Request, entity_id: Optional[str] = Query(None),
                       tag: Optional[str] = Query(None),
                       q: Optional[str] = Query(None),
                       line: str = Query("", description="FASE L — penyaring lini")) -> List[Dict[str, Any]]:
    viewer = await _perm_view(request)
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("design_gallery", {}, ctx, entity_id)
    # FASE L — galeri desain ikut berpagar lini (artwork printing bukan urusan staf woven).
    from services import line_scope as _lines
    scope = _lines.narrow(scope, viewer, line)
    return await gallery.list_gallery(scope, tag, q, viewer_id=viewer.get("id"))


@router.post("/design-gallery")
async def create_gallery(payload: GalleryInput, request: Request) -> Dict[str, Any]:
    actor = await _perm_manage(request)
    ctx = await entity_ctx(request)
    try:
        doc = await gallery.create_gallery(payload.model_dump(), actor["name"], ctx.active_entity_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "design_gallery_create", "design_gallery", doc["id"],
                {"title": doc["title"]})
    return doc


@router.get("/design-gallery/{gallery_id}")
async def get_gallery(gallery_id: str, request: Request) -> Dict[str, Any]:
    viewer = await _perm_view(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    return await gallery.get_gallery(gallery_id, viewer_id=viewer.get("id"))


@router.put("/design-gallery/{gallery_id}")
async def update_gallery(gallery_id: str, payload: GalleryUpdate, request: Request) -> Dict[str, Any]:
    actor = await _perm_manage(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    patch = payload.model_dump(exclude_unset=True)
    try:
        doc = await gallery.update_gallery(gallery_id, patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "design_gallery_update", "design_gallery", gallery_id, patch)
    return doc


@router.delete("/design-gallery/{gallery_id}")
async def delete_gallery(gallery_id: str, request: Request) -> Dict[str, Any]:
    actor = await _perm_manage(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    try:
        res = await gallery.delete_gallery(gallery_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "design_gallery_delete", "design_gallery", gallery_id, {})
    return res


# ─── Files (upload / serve / delete) ──────────────────────────────────
@router.post("/design-gallery/{gallery_id}/files")
async def upload_gallery_file(gallery_id: str, request: Request,
                              file: UploadFile = File(...)) -> Dict[str, Any]:
    actor = await _perm_manage(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    data = await file.read()
    try:
        fmeta = await gallery.add_file(gallery_id, file.filename or "motif",
                                       file.content_type or "", data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "design_gallery_upload", "design_gallery", gallery_id,
                {"file": fmeta.get("filename")})
    return fmeta


@router.get("/design-gallery/{gallery_id}/files/{file_id}")
async def get_gallery_file(gallery_id: str, file_id: str, request: Request):
    await _perm_view(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    try:
        data, ctype = await gallery.get_file_bytes(gallery_id, file_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File fisik tidak ditemukan.")
    return Response(content=data, media_type=ctype,
                    headers={"Cache-Control": "private, max-age=300"})


@router.delete("/design-gallery/{gallery_id}/files/{file_id}")
async def delete_gallery_file(gallery_id: str, file_id: str, request: Request) -> Dict[str, Any]:
    actor = await _perm_manage(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    try:
        res = await gallery.delete_file(gallery_id, file_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await audit(actor["name"], "design_gallery_delete_file", "design_gallery", gallery_id,
                {"file_id": file_id})
    return res


# ─── AI auto-tag (graceful) ─────────────────────────────────────
@router.post("/design-gallery/{gallery_id}/autotag")
async def autotag_gallery(gallery_id: str, request: Request) -> Dict[str, Any]:
    """Trigger AI auto-tag. Bila AI nonaktif → 200 {enabled:false} (BUKAN error)."""
    actor = await _perm_manage(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    try:
        res = await gallery.autotag(gallery_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "design_gallery_autotag", "design_gallery", gallery_id,
                {"enabled": res.get("enabled"), "error": res.get("error", "")})
    return res


# ─── FASE F (PS-14) — Master desain: versi & pengesahan ──────────────────────
@router.post("/design-gallery/{gallery_id}/version")
async def bump_design_version(gallery_id: str, payload: DesignVersionIn,
                              request: Request) -> Dict[str, Any]:
    """Naikkan versi desain (artwork direvisi). Versi lama tetap terarsip di `versions[]`."""
    actor = await _perm_manage(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    try:
        doc = await gallery.bump_version(gallery_id, payload.model_dump(exclude_unset=True),
                                        actor["name"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "design_version_bumped", "design_gallery", gallery_id,
                {"version": doc.get("version")}, reason=payload.note or "")
    return doc


@router.post("/design-gallery/{gallery_id}/submit")
async def submit_design(gallery_id: str, request: Request) -> Dict[str, Any]:
    """UTANG ALUR F-6.7 — draf desain DIAJUKAN dulu, baru bisa disahkan."""
    actor = await _perm_manage(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    try:
        doc = await gallery.submit_design(gallery_id, actor["name"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "design_submitted", "design_gallery", gallery_id,
                {"code": doc.get("code"), "version": doc.get("version")})
    return doc


@router.post("/design-gallery/{gallery_id}/reject")
async def reject_design(gallery_id: str, payload: DesignRejectIn,
                        request: Request) -> Dict[str, Any]:
    """Kembalikan desain yang diajukan ke draf — ALASAN wajib & tersimpan."""
    actor = await _perm_manage(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    try:
        doc = await gallery.reject_design(gallery_id, actor["name"], payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "design_rejected", "design_gallery", gallery_id,
                {"code": doc.get("code")}, reason=payload.reason)
    return doc


@router.post("/design-gallery/{gallery_id}/approve")
async def approve_design(gallery_id: str, payload: DesignApproveIn,
                         request: Request) -> Dict[str, Any]:
    """Sahkan desain agar boleh dipakai proofing & produk printing (wajib kode + berkas)."""
    actor = await _perm_manage(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    try:
        doc = await gallery.approve_design(gallery_id, actor["name"], payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "design_approved", "design_gallery", gallery_id,
                {"code": doc.get("code"), "version": doc.get("version")},
                reason=payload.note or "")
    return doc


# ─── Rating desain (bintang 1–5, 1 nilai per penilai; admin/manager) ─────────────
@router.post("/design-gallery/{gallery_id}/rating")
async def rate_design(gallery_id: str, payload: DesignRatingIn,
                      request: Request) -> Dict[str, Any]:
    """Set/ubah rating bintang 1–5 milik penilai (admin/manager). Upsert 1 nilai/orang."""
    actor = await _perm_manage(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    try:
        doc = await gallery.set_rating(gallery_id, actor.get("id"), actor.get("name", ""),
                                       payload.stars, payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "design_rated", "design_gallery", gallery_id,
                {"stars": payload.stars, "rating_avg": doc.get("rating_avg"),
                 "rating_count": doc.get("rating_count")}, reason=payload.note or "")
    return doc


@router.delete("/design-gallery/{gallery_id}/rating")
async def unrate_design(gallery_id: str, request: Request) -> Dict[str, Any]:
    """Hapus rating milik penilai yang sedang login."""
    actor = await _perm_manage(request)
    ctx = await entity_ctx(request)
    await _guard(gallery_id, ctx)
    try:
        doc = await gallery.clear_rating(gallery_id, actor.get("id"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "design_unrated", "design_gallery", gallery_id,
                {"rating_avg": doc.get("rating_avg"), "rating_count": doc.get("rating_count")})
    return doc
