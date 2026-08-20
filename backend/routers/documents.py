"""Documents router: templates CRUD + document generation + barcode labels.

FASE G-4 menambahkan lapisan **relasi dokumen tersimpan** (`refs[]`):
`/documents/trace/...` (graf dari jangkar mana pun), `/documents/refs/...`,
pencarian dokumen lintas jenis, dan backfill idempotent untuk data lama.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc
from schemas import BarcodeGenerate, DocumentGenerate, GenericPatch, TemplatePayload
from services.inventory_service import render_order_html
from services.document_relations_service import build_relations, SUPPORTED as RELATION_TYPES
from services import doc_refs_service as refs_svc
from entity_scope import assert_entity_access, entity_ctx, resolve_scope_ids

router = APIRouter(prefix="/api")

# Permission module per anchor doc-type (EPIC6 document hub / process timeline).
_RELATION_PERMISSION = {"sales_order": "order", "purchase_order": "purchase_order"}

# ─── FASE E-0 (E0.8c / L18-L19) — pagar entitas untuk dokumen ────────────────
# Bukti audit: sales CV Kanda Suka bisa MENCETAK Surat Jalan `SO-0007` milik
# PT Kain Suka Cita (HTTP 200, HTML lengkap) dan sales KSC bisa melihat jejak
# `SO-0002` Kanda beserta nama pelanggannya. Cetak/jejak dokumen PT lain kini 404.
#
# Peta jenis dokumen → koleksi tempat entitasnya disimpan.
_DOC_COLLECTION = {
    "sales_order": "sales_orders", "purchase_order": "purchase_orders",
    "purchase_requisition": "purchase_requisitions", "shipment": "shipments",
    "tax_invoice": "tax_invoices", "tax_invoice_in": "tax_invoices_in",
    "ar_receipt": "ar_receipts", "sales_return": "sales_returns",
    "purchase_return": "purchase_returns", "vendor_bill": "vendor_bills",
    "credit_note": "credit_notes", "contra_bon": "contra_bons",
    "interco_transaction": "interco_transactions", "interco_return": "interco_returns",
    "penalty": "penalties", "payment_plan": "payment_plans",
    "makloon_order": "makloon_orders", "special_order": "special_orders",
    "landed_cost": "landed_costs", "wms_task": "wms_tasks",
    "warehouse_transfer": "warehouse_transfers", "rfq": "rfqs",
}

# Koleksi yang mungkin memuat satu `source_id` dokumen cetak (Surat Jalan / Invoice).
_PRINTABLE_SOURCES = ("sales_orders", "shipments", "wms_tasks", "purchase_orders")


async def _assert_doc_entity(request: Request, doc_type: str, doc_id: str) -> None:
    """404 bila dokumen jangkar bukan milik entitas yang boleh dilihat pengguna."""
    coll = _DOC_COLLECTION.get(doc_type)
    if not coll:
        return
    ctx = await entity_ctx(request)
    doc = await db[coll].find_one({"id": doc_id}, {"_id": 0, "entity_id": 1,
                                                  "owner_entity_id": 1,
                                                  "source_entity_id": 1,
                                                  "dest_entity_id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    ids = set(resolve_scope_ids(ctx))
    involved = {doc.get("entity_id"), doc.get("owner_entity_id"),
                doc.get("source_entity_id"), doc.get("dest_entity_id")}
    involved = {e for e in involved if e}
    if involved and not (involved & ids):
        raise HTTPException(status_code=404,
                            detail="Dokumen tidak ditemukan untuk entitas ini")
    if not involved:
        assert_entity_access(doc, coll, ctx)


async def _assert_printable_entity(request: Request, source_id: str) -> None:
    """Pagar entitas untuk `documents/preview|generate` yang hanya menerima `source_id`."""
    ctx = await entity_ctx(request)
    ids = set(resolve_scope_ids(ctx))
    for coll in _PRINTABLE_SOURCES:
        doc = await db[coll].find_one({"id": source_id},
                                      {"_id": 0, "entity_id": 1, "owner_entity_id": 1})
        if not doc:
            continue
        ent = doc.get("entity_id") or doc.get("owner_entity_id")
        if ent and ent not in ids:
            raise HTTPException(status_code=404,
                                detail="Dokumen tidak ditemukan untuk entitas ini")
        return


@router.get("/documents/trace/{doc_type}/{doc_id}")
async def document_trace(doc_type: str, doc_id: str, request: Request,
                         depth: int = Query(0, ge=0, le=8)) -> Dict[str, Any]:
    """FASE G-4 — **Jejak Dokumen**: seluruh rantai dokumen dari jangkar MANA PUN.

    Berbeda dengan `/documents/relations/...` (turunan, hanya SO & PO), endpoint ini
    membaca relasi yang benar-benar TERSIMPAN di `refs[]` sehingga Faktur, Kwitansi,
    Retur, Tagihan Supplier, atau Nota Kredit pun bisa jadi titik masuk penelusuran.
    """
    await require_permission(request, "document", "view")
    await _assert_doc_entity(request, doc_type, doc_id)     # FASE E-0 (L19)
    try:
        return await refs_svc.trace(doc_type, doc_id, depth=depth or None)
    except refs_svc.RefsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/documents/refs/{doc_type}/{doc_id}")
async def document_refs(doc_type: str, doc_id: str, request: Request) -> Dict[str, Any]:
    """Daftar referensi satu dokumen (induk & turunan) + status hidup targetnya."""
    await require_permission(request, "document", "view")
    await _assert_doc_entity(request, doc_type, doc_id)     # FASE E-0 (L19)
    try:
        return await refs_svc.refs_of(doc_type, doc_id)
    except refs_svc.RefsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/documents/trace-search")
async def document_trace_search(request: Request, q: str = Query("", min_length=0),
                                entity_id: str = Query(""),
                                limit: int = Query(20, ge=1, le=50)) -> List[Dict[str, Any]]:
    """Cari dokumen lintas jenis (nomor / pelanggan / supplier) untuk layar Jejak Dokumen."""
    await require_permission(request, "document", "view")
    ctx = await entity_ctx(request)
    ids = resolve_scope_ids(ctx, entity_id or None)
    # Pencarian lintas-jenis hanya di dalam entitas yang boleh dilihat (FASE E-0/L19).
    out = []
    for eid in ids:
        out.extend(await refs_svc.search(q, limit=limit, entity_id=eid))
    return out[:limit]


@router.get("/documents/ref-types")
async def document_ref_types(request: Request) -> Dict[str, Any]:
    """Jenis dokumen yang ikut dalam graf relasi + kosakata relasinya (untuk UI)."""
    await require_permission(request, "document", "view")
    types = [{"doc_type": m["doc_type"], "label": m["label"], "order": m["order"],
              "needs_parent": m["needs_parent"], "view": m["view"]}
             for m in sorted(refs_svc.DOC_TYPES.values(), key=lambda x: x["order"])]
    return {"types": types, "rel_labels": refs_svc.REL_LABEL}


@router.post("/documents/refs/backfill")
async def document_refs_backfill(request: Request,
                                 dry_run: bool = Query(True)) -> Dict[str, Any]:
    """Bentuk relasi dokumen lama dari kolom penghubung yang sudah ada (idempotent).

    `dry_run=true` (default) hanya MENGHITUNG; tidak ada satu pun dokumen berubah.
    """
    actor = await require_permission(request, "pdf_template", "manage")
    result = await refs_svc.backfill(dry_run=dry_run)
    if not dry_run:
        await audit(actor.get("name", ""), "doc_refs_backfill", "document", "refs", result)
    return result


@router.get("/documents/relations/{doc_type}/{doc_id}")
async def document_relations(doc_type: str, doc_id: str, request: Request) -> Dict[str, Any]:
    """EPIC6 — Graf relasi antar-dokumen (process timeline / document hub).

    sales_order → SpecialOrder*/SO/Shipment/Faktur/AR/Komisi.
    purchase_order → PR/PO/GRN/LandedCost/VendorBill. Stage kosong tetap dikembalikan
    (no dead-end). RBAC mengikuti modul anchor (order vs purchase_order, action view).
    """
    if doc_type not in RELATION_TYPES:
        raise HTTPException(status_code=400, detail="doc_type tidak didukung (sales_order|purchase_order)")
    await require_permission(request, _RELATION_PERMISSION[doc_type], "view")
    await _assert_doc_entity(request, doc_type, doc_id)     # FASE E-0 (L19)
    result = await build_relations(doc_type, doc_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    return result


@router.get("/document-templates")
async def list_templates(request: Request,
                         layered: bool = Query(False)) -> List[Dict[str, Any]]:
    """Template cetak yang BERLAKU untuk badan usaha aktif (FASE E-4 · E4.2).

    Bawaan: baris EFEKTIF (override badan usaha menutupi global) supaya layar cetak
    tidak menampilkan dua "Template Invoice Standard". `layered=true` memperlihatkan
    kedua lapisan beserta lencana asalnya — dipakai layar Master per Badan Usaha.
    """
    await require_permission(request, "template", "view")
    from services import entity_master_service as ems
    ctx = await entity_ctx(request)
    if layered:
        return (await ems.list_layered("document-templates", ctx))["rows"]
    return await ems.effective_rows("document-templates", ctx.active_entity_id)


@router.post("/document-templates")
async def create_template(payload: TemplatePayload, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "template", "create")
    template = {**payload.model_dump(), "id": new_id("tmpl"), "status": "active",
                "created_by": actor["name"], "created_at": now_iso()}
    await db.document_templates.insert_one(template)
    await audit(actor["name"], "template_created", "document_template", template["id"], template)
    return safe_doc(template)


@router.patch("/document-templates/{template_id}")
async def update_template(template_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "template", "update")
    allowed = ["document_type", "name", "header", "footer", "columns", "logo_url",
               "paper_size", "orientation", "margin_mm", "signature_left", "signature_right",
               "section_order", "status"]
    data = {k: v for k, v in payload.data.items() if k in allowed}
    data["updated_at"] = now_iso()
    template = await db.document_templates.find_one_and_update(
        {"id": template_id}, {"$set": data},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")
    await audit(actor["name"], "template_updated", "document_template", template_id, data)
    return template


@router.delete("/document-templates/{template_id}")
async def delete_template(template_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "template", "delete")
    template = await db.document_templates.find_one_and_update(
        {"id": template_id},
        {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")
    await audit(actor["name"], "template_deactivated", "document_template", template_id, template)
    return template


@router.post("/documents/generate")
async def generate_document(payload: DocumentGenerate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "document", "create")
    await _assert_printable_entity(request, payload.source_id)   # FASE E-0 (L18)
    html_content = await render_order_html(payload.source_id, payload.document_type)
    doc = {
        "id": new_id("doc"),
        "document_type": payload.document_type,
        "source_id": payload.source_id,
        "html": html_content,
        "created_by": actor["name"],
        "created_at": now_iso(),
    }
    await db.generated_documents.insert_one(doc)
    await audit(actor["name"], "document_generated", "document", doc["id"],
                {"document_type": payload.document_type, "source_id": payload.source_id})
    return safe_doc(doc)


@router.get("/documents/preview/{order_id}")
async def preview_document(order_id: str, request: Request, document_type: str = "surat_jalan") -> HTMLResponse:
    # INV-AUTH-01 (KN-076-AUTH-DOC-PREVIEW P0): dokumen bisnis WAJIB login + izin view.
    await require_permission(request, "document", "view")
    await _assert_printable_entity(request, order_id)            # FASE E-0 (L18)
    html_content = await render_order_html(order_id, document_type)
    return HTMLResponse(content=html_content)


@router.post("/documents/barcode")
async def generate_barcode(payload: BarcodeGenerate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "document", "create")
    if payload.target_type == "product":
        product = safe_doc(await db.products.find_one({"id": payload.target_id}, {"_id": 0}))
        if not product:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
        label_html = f"""
        <html><head><style>body{{font-family:Arial,sans-serif;margin:0;padding:4px}}
        .label{{width:80mm;padding:6px;border:1px solid #ccc;text-align:center}}
        h3{{margin:0;font-size:11px}} p{{margin:2px 0;font-size:9px}} .barcode{{font-size:22px;letter-spacing:4px}}</style></head>
        <body><div class='label'><h3>{product.get('name','-')}</h3><div class='barcode'>||| {product.get('sku','')} |||</div>
        <p>SKU: {product.get('sku','')}</p><p>{product.get('category','')} | {product.get('variant','')} | {product.get('color','')}</p>
        <p>Grade: {product.get('grade','')} | Supplier: {product.get('supplier','')}</p></div></body></html>
        """
        await audit(actor["name"], "barcode_generated", "product", payload.target_id,
                    {"label_size": payload.label_size})
        return {"label_html": label_html, "target_type": payload.target_type, "target_id": payload.target_id}
    elif payload.target_type == "wms_task":
        task = safe_doc(await db.wms_tasks.find_one({"id": payload.target_id}, {"_id": 0}))
        if not task:
            raise HTTPException(status_code=404, detail="WMS task tidak ditemukan")
        label_html = f"""
        <html><head><style>body{{font-family:Arial,sans-serif;margin:0;padding:4px}}
        .label{{width:80mm;padding:6px;border:1px solid #ccc;text-align:center}}
        h3{{margin:0;font-size:11px}} p{{margin:2px 0;font-size:9px}} .barcode{{font-size:22px;letter-spacing:4px}}</style></head>
        <body><div class='label'><h3>{task.get('product_name','-')}</h3><div class='barcode'>||| {task.get('sku','')} |||</div>
        <p>Batch: {task.get('batch','-')} | Lot: {task.get('lot','-')} | Roll: {task.get('roll_id','-')}</p>
        <p>Bin: {task.get('bin_id','-')} | WH: {task.get('warehouse_name','-')}</p>
        <p>Task: {str(task.get('id',''))[:12]} | {str(task.get('flow_type','')).upper()}</p></div></body></html>
        """
        await audit(actor["name"], "barcode_generated", "wms_task", payload.target_id,
                    {"label_size": payload.label_size})
        return {"label_html": label_html, "target_type": payload.target_type, "target_id": payload.target_id}
    raise HTTPException(status_code=400, detail="target_type tidak valid")
