"""routers/pdf.py — Endpoint render dokumen PDF/HTML + kelola template & branding."""
from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import Response, HTMLResponse
from pydantic import BaseModel

from db import db
from dependencies import require_permission
from entity_scope import entity_ctx, assert_entity_access, resolve_list_scope
from services import pdf_service as svc
from services.pdf_resolvers import DOC_REGISTRY
import json as _json

router = APIRouter(prefix="/api/pdf", tags=["pdf"])


def _summarize_doc(r: Dict[str, Any]) -> Dict[str, Any]:
    """Ringkasan lintas-koleksi untuk Pusat Dokumen (field bervariasi per doc_type)."""
    number = (r.get("number") or r.get("po_number") or r.get("so_number") or r.get("order_number")
              or r.get("bill_number") or r.get("receipt_number") or r.get("return_number")
              or r.get("transfer_number") or r.get("code") or r.get("id"))
    date = (r.get("date") or r.get("order_date") or r.get("bill_date") or r.get("receipt_date")
            or r.get("created_at") or "")
    party = (r.get("customer_name") or r.get("supplier_name") or r.get("vendor_name")
             or r.get("makloon_name") or r.get("to_warehouse_name") or r.get("warehouse_name") or "")
    amount = (r.get("total_amount") or r.get("grand_total") or r.get("total")
              or r.get("amount") or r.get("net_total") or 0)
    return {"number": number, "date": str(date)[:10], "party": party,
            "amount": amount, "status": r.get("status") or ""}


def _origin(request: Request) -> str:
    """URL publik aplikasi untuk QR & tautan pada dokumen cetak.

    FASE G-4 — dulu fungsi ini HANYA membaca header `Origin`/`Referer`, sehingga
    render non-browser (cetak batch, penjadwal, kiriman WhatsApp, integrasi) mencetak
    QR tanpa host — tidak bisa dibuka dari HP pemegang kertas. Sekarang ada rantai
    fallback tunggal di `services/app_url.py`.
    """
    from services.app_url import public_app_url
    return public_app_url(request)


class TemplateSave(BaseModel):
    config: Dict[str, Any]


class BrandingSave(BaseModel):
    company_name: str | None = None
    address: str | None = None
    phone: str | None = None
    npwp: str | None = None
    logo_b64: str | None = None
    signatures: List[Dict[str, Any]] | None = None


class PreviewReq(BaseModel):
    doc_type: str
    source_id: str | None = None
    entity_id: str | None = None
    config: Dict[str, Any] | None = None


@router.get("/doc-types")
async def list_doc_types(request: Request) -> List[Dict[str, Any]]:
    await require_permission(request, "document", "view")
    return [{"doc_type": k, "label": v["label"], "esignable": v.get("esignable", False),
             "collection": v["collection"], "module": v["module"]} for k, v in DOC_REGISTRY.items()]


@router.get("/render/{doc_type}/{source_id}")
async def render_document(doc_type: str, source_id: str, request: Request,
                          format: str = Query("pdf"), entity_id: str = Query(None),
                          download: bool = Query(True)):
    await require_permission(request, "document", "print")
    ctx = await entity_ctx(request)
    reg = DOC_REGISTRY.get(doc_type)
    if not reg:
        raise HTTPException(status_code=404, detail=f"Jenis dokumen '{doc_type}' tidak dikenal")
    source = await db[reg["collection"]].find_one({"id": source_id}, {"_id": 0})
    if not source:
        raise HTTPException(status_code=404, detail="Dokumen sumber tidak ditemukan")
    assert_entity_access(source, reg["collection"], ctx)
    try:
        content, media, built = await svc.render_document(
            doc_type, source_id, entity_id or source.get("entity_id"),
            fmt=format, public_base=_origin(request))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Gagal render dokumen: {e}")
    if format == "html":
        return HTMLResponse(content=content)
    num = (built["doc"].get("number") or source_id).replace("/", "-")
    disp = "attachment" if download else "inline"
    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": f'{disp}; filename="{doc_type}-{num}.pdf"'})


@router.get("/sample/{doc_type}")
async def get_sample(doc_type: str, request: Request, entity_id: str = Query(None)) -> Dict[str, Any]:
    """Ambil 1 dokumen contoh (id + nomor) untuk pratinjau/unduh di Template Designer."""
    await require_permission(request, "pdf_template", "view")
    reg = DOC_REGISTRY.get(doc_type)
    if not reg:
        raise HTTPException(status_code=404, detail="Jenis dokumen tidak dikenal")
    q: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    sample = await db[reg["collection"]].find_one(q, {"_id": 0, "id": 1, "entity_id": 1, "number": 1})
    if not sample:
        return {"doc_type": doc_type, "source_id": None, "entity_id": entity_id, "number": None,
                "label": reg["label"]}
    return {"doc_type": doc_type, "source_id": sample.get("id"),
            "entity_id": sample.get("entity_id") or entity_id, "number": sample.get("number"),
            "label": reg["label"]}


@router.get("/documents/{doc_type}")
async def list_documents(doc_type: str, request: Request,
                         entity_id: str = Query(None), q: str = Query(""),
                         limit: int = Query(100)) -> Dict[str, Any]:
    """Daftar dokumen (Pusat Dokumen) + ringkasan status e-sign & pengiriman."""
    await require_permission(request, "document", "view")
    ctx = await entity_ctx(request)
    reg = DOC_REGISTRY.get(doc_type)
    if not reg:
        raise HTTPException(status_code=404, detail="Jenis dokumen tidak dikenal")
    coll = reg["collection"]
    query = resolve_list_scope(coll, {}, ctx, entity_id)
    rows = await db[coll].find(query, {"_id": 0}).sort("created_at", -1).to_list(int(limit))
    ids = [r.get("id") for r in rows if r.get("id")]

    sig_rows = await db.document_signatures.find(
        {"doc_type": doc_type, "source_id": {"$in": ids}, "status": "signed"},
        {"_id": 0, "source_id": 1, "verification_code": 1, "signer_name": 1}).to_list(2000)
    sig_map: Dict[str, List[Dict[str, Any]]] = {}
    for s in sig_rows:
        sig_map.setdefault(s["source_id"], []).append(s)

    del_rows = await db.document_deliveries.find(
        {"doc_type": doc_type, "source_id": {"$in": ids}},
        {"_id": 0, "source_id": 1, "status": 1, "sent_at": 1, "channel": 1, "to": 1}
    ).sort("created_at", -1).to_list(3000)
    del_map: Dict[str, Dict[str, Any]] = {}
    for d in del_rows:
        del_map.setdefault(d["source_id"], d)  # pertama = terbaru (sort desc)

    ql = (q or "").strip().lower()
    # FASE G-4 — doc_type PDF bisa berbagi koleksi (invoice/delivery_note/picking_list
    # semuanya dari `sales_orders`). Untuk menautkan baris ke layar Jejak Dokumen, UI
    # butuh doc_type KANONIK koleksinya — dihitung sekali di sini, bukan ditebak di FE.
    from services import doc_refs_service as _refs
    trace_type = (doc_type if doc_type in _refs.DOC_TYPES
                  else _refs.type_of_collection(coll))
    out: List[Dict[str, Any]] = []
    for r in rows:
        summ = _summarize_doc(r)
        if ql and ql not in _json.dumps(summ, default=str, ensure_ascii=False).lower():
            continue
        sid = r.get("id")
        sigs = sig_map.get(sid, [])
        out.append({**summ, "source_id": sid, "entity_id": r.get("entity_id"),
                    "esignable": reg.get("esignable", False),
                    "signed": len(sigs) > 0, "sign_count": len(sigs),
                    "verification_code": (sigs[0]["verification_code"] if sigs else None),
                    "trace_type": trace_type, "ref_count": len(r.get("refs") or []),
                    "last_delivery": del_map.get(sid)})
    return {"doc_type": doc_type, "label": reg["label"], "count": len(out),
            "trace_type": trace_type, "documents": out}


@router.get("/templates/{doc_type}")
async def get_template(doc_type: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "pdf_template", "view")
    if doc_type not in DOC_REGISTRY:
        raise HTTPException(status_code=404, detail="Jenis dokumen tidak dikenal")
    return {"doc_type": doc_type, "config": await svc.get_template_cfg(doc_type),
            "defaults": svc.DEFAULT_TEMPLATE_CFG}


@router.put("/templates/{doc_type}")
async def put_template(doc_type: str, payload: TemplateSave, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "pdf_template", "manage")
    if doc_type not in DOC_REGISTRY:
        raise HTTPException(status_code=404, detail="Jenis dokumen tidak dikenal")
    cfg = await svc.save_template_cfg(doc_type, payload.config, actor.get("name", ""))
    return {"doc_type": doc_type, "config": cfg}


@router.get("/branding/{entity_id}")
async def get_branding(entity_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "pdf_template", "view")
    return await svc.get_branding(entity_id)


@router.put("/branding/{entity_id}")
async def put_branding(entity_id: str, payload: BrandingSave, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "pdf_template", "manage")
    return await svc.save_branding(entity_id, payload.model_dump(exclude_none=True), actor.get("name", ""))


@router.post("/preview")
async def preview(payload: PreviewReq, request: Request):
    await require_permission(request, "pdf_template", "view")
    ctx = await entity_ctx(request)
    reg = DOC_REGISTRY.get(payload.doc_type)
    if not reg:
        raise HTTPException(status_code=404, detail="Jenis dokumen tidak dikenal")
    source_id = payload.source_id
    entity_id = payload.entity_id
    if not source_id:
        # ambil contoh dokumen pertama yang bisa diakses user
        q = {}
        if entity_id and entity_id != "all":
            q["entity_id"] = entity_id
        sample = await db[reg["collection"]].find_one(q, {"_id": 0, "id": 1, "entity_id": 1})
        if not sample:
            raise HTTPException(status_code=404, detail=f"Belum ada data '{reg['label']}' untuk pratinjau. Buat dokumen dulu.")
        source_id = sample["id"]
        entity_id = entity_id or sample.get("entity_id")
    try:
        html, _, _ = await svc.render_document(
            payload.doc_type, source_id, entity_id, fmt="html",
            cfg_override=payload.config, public_base=_origin(request))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Gagal pratinjau: {e}")
    return HTMLResponse(content=html)
