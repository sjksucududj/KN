"""Warehouse Transfer router: multi-warehouse transfer workflow with approval."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pymongo import ReturnDocument
from db import db
from services import dual_qty_service as _dual  # FASE U — dua satuan (roll + ukuran)
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc, next_doc_number
from schemas import TransferCreate, TransferApprove, TransferReject, TransferStatusUpdate, InterCompanyTransferCreate
from entity_scope import entity_ctx, resolve_scope_ids
from services import line_scope              # FASE L — pagar & penyaring lini produk
from services.roll_service import (
    reserve_rolls_for_transfer, execute_ownership_transfer, release_transfer_rolls,
    resolve_stock_owner, reserve_rolls_for_wh_transfer, dispatch_wh_transfer_rolls,
    receive_wh_transfer_rolls, release_wh_transfer_rolls,
)
from services import gl_service

router = APIRouter(prefix="/api")


# Allowed status transitions
STATUS_TRANSITIONS = {
    "draft": ["waiting_approval", "cancelled"],
    "waiting_approval": ["approved", "rejected", "cancelled"],
    "approved": ["picking", "cancelled"],
    "picking": ["staging", "cancelled"],
    "staging": ["dispatched", "cancelled"],
    "dispatched": ["completed", "cancelled"],
    "completed": [],
    "rejected": [],
    "cancelled": []
}


def _validate_status_transition(current: str, new: str) -> bool:
    """Check if status transition is valid."""
    return new in STATUS_TRANSITIONS.get(current, [])


# ─── FASE E-0 (E0.8b / L13-L14) — cakupan entitas untuk transfer gudang ──────
# Sebelumnya SELURUH endpoint `/api/transfers*` tidak punya cakupan entitas sama
# sekali: gudang PT Kain Suka Cita bisa membuka `TRF-00003` dengan konteks CV Kanda
# Suka (HTTP 200), dan `warehouse_transfers` tak terdaftar di `SCOPED_COLLECTIONS`.
#
# Aturan khusus (transfer bisa ANTAR-entitas, jadi bukan filter satu field):
#   * transfer INTRA-entitas  → terlihat hanya oleh entitas `entity_id`.
#   * transfer ANTAR-entitas  → terlihat oleh **kedua** entitas
#                               (`source_entity_id` ATAU `dest_entity_id` ∈ allowed),
#     tetapi hanya entitas ASAL yang boleh menyetujui pengiriman dan entitas
#     TUJUAN yang boleh menerima (dijaga `_assert_transfer_side`).

def _transfer_scope_clause(ids):
    """Klausa Mongo: transfer yang boleh DILIHAT oleh daftar entitas `ids`."""
    return {"$or": [
        {"entity_id": {"$in": list(ids)}},
        {"source_entity_id": {"$in": list(ids)}},
        {"dest_entity_id": {"$in": list(ids)}},
    ]}


def _transfer_entities(transfer):
    """Entitas yang terlibat pada satu transfer (intra & antar-entitas)."""
    out = {transfer.get("entity_id"), transfer.get("source_entity_id"),
           transfer.get("dest_entity_id")}
    return {e for e in out if e}


async def _guard_transfer(request: Request, transfer_id: str, side: str = "any"):
    """Ambil transfer + tegakkan cakupan entitas. 404 bila di luar entitas yang boleh.

    `side="source"` → hanya entitas ASAL (menyetujui/mengirim/membatalkan).
    `side="dest"`   → hanya entitas TUJUAN (menerima).
    """
    ctx = await entity_ctx(request)
    ids = set(resolve_scope_ids(ctx))
    transfer = await db.warehouse_transfers.find_one({"id": transfer_id}, {"_id": 0})
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer tidak ditemukan")
    if not (_transfer_entities(transfer) & ids):
        raise HTTPException(status_code=404, detail="Transfer tidak ditemukan untuk entitas ini")
    if transfer.get("transfer_kind") == "inter_entity" and side in ("source", "dest"):
        need = transfer.get("source_entity_id") if side == "source" else transfer.get("dest_entity_id")
        if need and need not in ids:
            label = "asal" if side == "source" else "tujuan"
            raise HTTPException(
                status_code=403,
                detail=f"Hanya entitas {label} transfer ini yang boleh melakukan aksi tersebut.")
    return transfer, ctx


@router.get("/transfers")
async def list_transfers(
    request: Request,
    status: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    transfer_kind: Optional[str] = Query(None),
    line: str = Query("", description="FASE L — penyaring lini (koma untuk multi)"),
) -> List[Dict[str, Any]]:
    """List all transfers with optional filtering by status, warehouse, or transfer_kind."""
    actor = await require_permission(request, "transfer", "view")
    ctx = await entity_ctx(request)
    query_filter = dict(_transfer_scope_clause(resolve_scope_ids(ctx)))
    if status:
        query_filter["status"] = status
    if transfer_kind:
        # record lama tanpa field → dianggap intra_entity
        if transfer_kind == "intra_entity":
            query_filter["transfer_kind"] = {"$ne": "inter_entity"}
        else:
            query_filter["transfer_kind"] = transfer_kind
    if warehouse_id:
        query_filter = {"$and": [query_filter, {"$or": [
            {"source_warehouse_id": warehouse_id},
            {"dest_warehouse_id": warehouse_id},
        ]}]}
    
    transfers = await db.warehouse_transfers.find(
        line_scope.narrow(query_filter, actor, line, field=line_scope.LINES_FIELD),
        {"_id": 0}).sort("created_at", -1).to_list(200)
    
    # Enrich with warehouse/entity names and product details
    warehouses = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(100)}
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(1000)}
    entities = {e["id"]: e for e in await db.business_entities.find({}, {"_id": 0}).to_list(100)}
    
    def _ent_name(eid):
        e = entities.get(eid, {})
        return e.get("short_name") or e.get("legal_name") or (eid or "")
    
    for transfer in transfers:
        transfer["transfer_kind"] = transfer.get("transfer_kind", "intra_entity")
        transfer["source_warehouse_name"] = warehouses.get(transfer.get("source_warehouse_id"), {}).get("name", "")
        transfer["dest_warehouse_name"] = warehouses.get(transfer.get("dest_warehouse_id"), {}).get("name", "")
        transfer["source_entity_name"] = _ent_name(transfer.get("source_entity_id"))
        transfer["dest_entity_name"] = _ent_name(transfer.get("dest_entity_id"))
        for item in transfer.get("items", []):
            prod = products.get(item["product_id"], {})
            item.setdefault("sku", prod.get("sku", ""))
            item.setdefault("product_name", prod.get("name", ""))
    
    return transfers


@router.post("/transfers")
async def create_transfer(payload: TransferCreate, request: Request) -> Dict[str, Any]:
    """
    Create a new warehouse transfer.
    
    Default status: waiting_approval
    Requires permission: transfer.create
    """
    actor = await require_permission(request, "transfer", "create")
    
    # Validate warehouses exist
    source_wh = await db.warehouses.find_one({"id": payload.source_warehouse_id}, {"_id": 0})
    dest_wh = await db.warehouses.find_one({"id": payload.dest_warehouse_id}, {"_id": 0})
    
    if not source_wh:
        raise HTTPException(status_code=404, detail="Source warehouse tidak ditemukan")
    if not dest_wh:
        raise HTTPException(status_code=404, detail="Destination warehouse tidak ditemukan")
    if payload.source_warehouse_id == payload.dest_warehouse_id:
        raise HTTPException(status_code=400, detail="Source dan destination warehouse harus berbeda")
    
    # Validate products and items
    if not payload.items or len(payload.items) == 0:
        raise HTTPException(status_code=400, detail="Items tidak boleh kosong")

    ctx = await entity_ctx(request)
    prefer_owner = payload.owner_entity_id or (
        "" if getattr(ctx, "view_all", False) else (ctx.active_entity_id or "")
    )
    # E4.1 — transfer internal: KEDUA gudang harus boleh dipakai badan usaha ini.
    # (Jembatan gudang ANTAR badan usaha punya rutenya sendiri:
    #  `POST /api/transfers/inter-company` — di sana gudang lawan memang sah.)
    from services import warehouse_scope_service as whscope
    await whscope.assert_usable(payload.source_warehouse_id,
                               prefer_owner or ctx.active_entity_id,
                               action="mengambil barang dari sini",
                               field_label="Gudang asal")
    await whscope.assert_usable(payload.dest_warehouse_id,
                               prefer_owner or ctx.active_entity_id,
                               action="mengirim barang ke sini",
                               field_label="Gudang tujuan")

    transfer_id = new_id("trn")
    # FASE E-1 (E1.7) — nomor dokumen PER BADAN USAHA. Sebelum ini semua transfer
    # memakai satu deret grup ("TRF-00001") sehingga dua badan usaha berebut nomor
    # yang sama dan nomornya melompat-lompat di mata pengguna.
    code = await next_doc_number("warehouse_transfers", "code", "TRF-",
                                 entity_id=prefer_owner or ctx.active_entity_id or None)

    # Roll-as-SSOT (KN_15 §9): reservasi roll di gudang sumber SAAT create (kunci stok).
    items_out: List[Dict[str, Any]] = []
    try:
        for item in payload.items:
            prod = await db.products.find_one({"id": item.product_id}, {"_id": 0})
            if not prod:
                raise HTTPException(status_code=404, detail=f"Product {item.product_id} tidak ditemukan")
            if item.qty <= 0:
                raise HTTPException(status_code=400, detail="Qty harus lebih dari 0")
            owner = await resolve_stock_owner(item.product_id, payload.source_warehouse_id, prefer_owner)
            reserved = await reserve_rolls_for_wh_transfer(
                item.product_id, payload.source_warehouse_id, owner, item.qty, transfer_id
            )
            roll_refs = [{
                "roll_id": r["id"], "roll_no": r.get("roll_no"), "lot": r.get("lot"),
                "length": float(r.get("length_remaining", 0) or 0),
            } for r in reserved]
            lots = sorted({r.get("lot") for r in reserved if r.get("lot")})
            item_doc = item.model_dump()
            item_doc.update({
                "owner_entity_id": owner, "sku": prod.get("sku", ""),
                "product_name": prod.get("name", ""), "lots": lots, "rolls": roll_refs,
                # FASE L — snapshot lini kerja MD (dipakai penyaring layar Transfer).
                "line_code": str(prod.get("line_code") or "").strip().lower(),
                # FASE U — jumlah roll DIHITUNG dari roll yang benar-benar direservasi.
                **(await _dual.stamp(item, rolls=len(roll_refs))),
            })
            items_out.append(item_doc)
    except HTTPException:
        # rollback reservasi parsial bila ada item gagal
        await release_wh_transfer_rolls(transfer_id)
        raise

    transfer = {
        "id": transfer_id,
        "code": code,
        "transfer_kind": "intra_entity",
        # FASE E-0 (L14) — stempel entitas WAJIB agar transfer intra tidak terbaca
        # oleh entitas lain (registry `SCOPED_COLLECTIONS`).
        "entity_id": prefer_owner or ctx.active_entity_id,
        "source_warehouse_id": payload.source_warehouse_id,
        "dest_warehouse_id": payload.dest_warehouse_id,
        "status": "waiting_approval",
        "items": items_out,
        "line_codes": line_scope.codes_from_items(items_out),   # FASE L
        "notes": payload.notes,
        "requested_by": payload.requested_by,
        "approved_by": None,
        "approved_at": None,
        "rejected_by": None,
        "rejected_at": None,
        "rejected_reason": None,
        "created_at": now_iso(),
        "updated_at": now_iso()
    }
    
    await db.warehouse_transfers.insert_one(transfer)
    await audit(actor["name"], "transfer_created", "transfer", transfer["id"],
                {"code": code, "items": len(items_out)})
    
    return safe_doc(transfer)


@router.post("/transfers/inter-company")
async def create_inter_company_transfer(payload: InterCompanyTransferCreate, request: Request) -> Dict[str, Any]:
    """Sub-fase 1.5 — Minta transfer kepemilikan antar-entitas (B→E) dari preview POS.

    Permission: order:create (dimulai oleh Sales sebagai bagian alur pemenuhan).
    Persetujuan B (transfer:approve) yang akan MEMINDAHKAN kepemilikan (KN_15 §7).
    Reservasi roll milik B (status=reserved, ref=transfer) agar tak dobel-jual.
    """
    actor = await require_permission(request, "order", "create")

    if payload.source_entity_id == payload.dest_entity_id:
        raise HTTPException(status_code=400, detail="Entitas sumber dan tujuan harus berbeda")
    # FASE E-0 (L13) — pemohon wajib berwenang atas SALAH SATU sisi transaksi.
    _ctx = await entity_ctx(request)
    _allowed = set(resolve_scope_ids(_ctx))
    if not ({payload.source_entity_id, payload.dest_entity_id} & _allowed):
        raise HTTPException(status_code=403,
                            detail="Anda tidak berwenang atas entitas pada transfer ini")
    src_ent = await db.business_entities.find_one({"id": payload.source_entity_id}, {"_id": 0})
    dst_ent = await db.business_entities.find_one({"id": payload.dest_entity_id}, {"_id": 0})
    if not src_ent:
        raise HTTPException(status_code=404, detail="Entitas sumber tidak ditemukan")
    if not dst_ent:
        raise HTTPException(status_code=404, detail="Entitas tujuan tidak ditemukan")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Items tidak boleh kosong")

    transfer_id = new_id("trn")
    # FASE E-1 (E1.7) — nomor per badan usaha ASAL barang (pemilik dokumennya).
    code = await next_doc_number("warehouse_transfers", "code", "TRF-",
                                 entity_id=payload.source_entity_id or None)

    items_out: List[Dict[str, Any]] = []
    wh_ids: List[str] = []
    try:
        for it in payload.items:
            prod = await db.products.find_one({"id": it.product_id}, {"_id": 0})
            if not prod:
                raise HTTPException(status_code=404, detail=f"Produk {it.product_id} tidak ditemukan")
            if it.quantity <= 0:
                raise HTTPException(status_code=400, detail="Qty harus lebih dari 0")
            reserved = await reserve_rolls_for_transfer(
                it.product_id, payload.source_entity_id, it.quantity, transfer_id
            )
            roll_refs = [{
                "roll_id": r["id"], "roll_no": r.get("roll_no"), "lot": r.get("lot"),
                "warehouse_id": r.get("warehouse_id"), "length": float(r.get("length_remaining", 0) or 0),
            } for r in reserved]
            lots = sorted({r.get("lot") for r in reserved if r.get("lot")})
            for r in reserved:
                if r.get("warehouse_id"):
                    wh_ids.append(r["warehouse_id"])
            items_out.append({
                "product_id": it.product_id, "qty": round(it.quantity, 2), "unit": it.unit,
                "sku": prod.get("sku", ""), "product_name": prod.get("name", ""),
                "lots": lots, "rolls": roll_refs,
                "line_code": str(prod.get("line_code") or "").strip().lower(),   # FASE L
                # FASE U — jumlah roll transfer DIHITUNG dari roll yang benar-benar
                # direservasi (bukan diketik): satu fakta, satu sumber.
                **(await _dual.stamp(it, rolls=len(roll_refs))),
            })
    except HTTPException:
        # rollback reservasi parsial bila ada item gagal
        await release_transfer_rolls(transfer_id)
        raise

    primary_wh = wh_ids[0] if wh_ids else ""
    # FASE G-6 — tautan ke transaksi antar-PT (bila ada). Divalidasi supaya penanda
    # anti dobel-posting tidak bisa dipakai sembarangan.
    interco_pair_id = (payload.interco_pair_id or "").strip()
    interco_number = ""
    interco_id_ref = ""
    if interco_pair_id:
        ict = await db.interco_transactions.find_one(
            {"pair_id": interco_pair_id, "role": "seller"}, {"_id": 0})
        if not ict:
            raise HTTPException(status_code=404,
                                detail="Transaksi antar-PT (pair) tidak ditemukan.")
        if ict.get("status") in ("draft", "cancelled"):
            raise HTTPException(
                status_code=400,
                detail="Transaksi antar-PT belum dikonfirmasi/sudah dibatalkan — "
                       "barang tidak boleh berjalan tanpa dokumen sah.")
        if (ict["seller_entity_id"] != payload.source_entity_id
                or ict["buyer_entity_id"] != payload.dest_entity_id):
            await release_transfer_rolls(transfer_id)
            raise HTTPException(
                status_code=400,
                detail="Arah transfer tidak sama dengan transaksi antar-PT "
                       f"(seharusnya {ict['seller_entity_id']} → {ict['buyer_entity_id']}).")
        interco_number = ict.get("number", "")
        interco_id_ref = ict.get("id", "")
    transfer = {
        "id": transfer_id,
        "code": code,
        "transfer_kind": "inter_entity",
        # FASE E-0 (L14) — transfer antar-entitas WAJIB ber-`entity_id` (registry
        # `SCOPED_COLLECTIONS`). Pemiliknya = entitas ASAL barang; entitas tujuan
        # tetap melihat dokumen ini lewat `dest_entity_id` (lihat `_transfer_scope_clause`).
        "entity_id": payload.source_entity_id,
        "source_entity_id": payload.source_entity_id,
        "dest_entity_id": payload.dest_entity_id,
        # Ownership-in-place (Sub-fase 1.5): gudang sumber = tujuan (tak ada pindah fisik)
        "source_warehouse_id": primary_wh,
        "dest_warehouse_id": primary_wh,
        "status": "waiting_approval",
        "items": items_out,
        "line_codes": line_scope.codes_from_items(items_out),   # FASE L
        "transfer_price": payload.transfer_price,
        "linked_order_id": payload.linked_order_id,
        "interco_pair_id": interco_pair_id or None,
        "interco_id": interco_id_ref or None,
        "interco_number": interco_number,
        "notes": payload.notes,
        "requested_by": payload.requested_by or actor["name"],
        "approved_by": None, "approved_at": None,
        "rejected_by": None, "rejected_at": None, "rejected_reason": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.warehouse_transfers.insert_one(transfer)
    await audit(actor["name"], "inter_company_transfer_requested", "transfer", transfer_id, {
        "source": payload.source_entity_id, "dest": payload.dest_entity_id,
        "items": [{"product_id": i["product_id"], "qty": i["qty"]} for i in items_out],
        "linked_order_id": payload.linked_order_id,
    })
    return safe_doc(transfer)


@router.get("/transfers/{transfer_id}")
async def get_transfer_detail(transfer_id: str, request: Request) -> Dict[str, Any]:
    """Get detailed transfer information."""
    await require_permission(request, "transfer", "view")
    _t, _ctx = await _guard_transfer(request, transfer_id)   # FASE E-0 (L13)
    transfer = safe_doc(_t)
    
    # Enrich with warehouse and product details
    warehouses = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(100)}
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(1000)}
    
    transfer["source_warehouse_name"] = warehouses.get(transfer["source_warehouse_id"], {}).get("name", "")
    transfer["dest_warehouse_name"] = warehouses.get(transfer["dest_warehouse_id"], {}).get("name", "")
    
    for item in transfer.get("items", []):
        prod = products.get(item["product_id"], {})
        item["sku"] = prod.get("sku", "")
        item["product_name"] = prod.get("name", "")
    
    return transfer


@router.post("/transfers/{transfer_id}/approve")
async def approve_transfer(transfer_id: str, payload: TransferApprove, request: Request) -> Dict[str, Any]:
    """
    Approve a transfer.
    
    Status: waiting_approval → approved
    Requires permission: transfer.approve
    """
    actor = await require_permission(request, "transfer", "approve")
    transfer, _ctx = await _guard_transfer(request, transfer_id, side="source")  # FASE E-0 (L13)
    if transfer["status"] != "waiting_approval":
        raise HTTPException(status_code=400, detail=f"Transfer tidak bisa diapprove (status: {transfer['status']})")
    
    # Sub-fase 1.5 — inter-company: APPROVE = pindahkan kepemilikan B→E (S3, 1 langkah) → status completed.
    if transfer.get("transfer_kind") == "inter_entity":
        result = await execute_ownership_transfer(transfer)
        interco_pair_id = transfer.get("interco_pair_id")
        interco_return_pair_id = transfer.get("interco_return_pair_id")
        if interco_return_pair_id:
            # FASE G-6b — perpindahan BALIK milik RETUR antar-PT. Sama seperti arah
            # jualnya: jurnal at-cost M-3 DILEWATI (nota retur sudah memposting
            # pembalikan piutang/utang), roll dinilai ulang KEMBALI ke harga
            # perolehan asli penjual agar GL 1-1300 == subledger.
            from services import interco_return_service as _icret
            bridge = await _icret.on_return_task_executed(transfer, actor["name"])
            je_result = {
                "posted": False,
                "skipped_reason": (
                    "Jurnal sudah diposting oleh retur antar-PT "
                    f"{transfer.get('interco_return_number') or interco_return_pair_id} "
                    "(FASE G-6b). Memposting at-cost M-3 lagi akan menggandakan "
                    "pembalikan IC-AR/IC-AP & persediaan."),
                "interco_return_pair_id": interco_return_pair_id,
                "revalued_rolls": bridge.get("revalued_rolls", 0),
                "returned_cost": bridge.get("returned_cost", 0),
                "interco_status": bridge.get("status", ""),
            }
        elif interco_pair_id:
            # FASE G-6 — perpindahan fisik milik transaksi JUAL-BELI antar-PT.
            # Jurnal at-cost M-3 SENGAJA DILEWATI: jurnal harga jual (IC-AR/Pendapatan
            # di penjual, Persediaan/IC-AP di pembeli) sudah diposting saat transaksi
            # dikonfirmasi. Kalau tetap diposting, satu barang tercatat DUA KALI.
            from services import interco_service as _ics
            bridge = await _ics.on_warehouse_task_executed(transfer, actor["name"])
            je_result = {
                "posted": False,
                "skipped_reason": (
                    "Jurnal sudah diposting oleh transaksi antar-PT "
                    f"{transfer.get('interco_number') or interco_pair_id} (FASE G-6, harga jual). "
                    "Memposting at-cost M-3 lagi akan menggandakan IC-AR/IC-AP & persediaan."),
                "interco_pair_id": interco_pair_id,
                "revalued_rolls": bridge.get("revalued_rolls", 0),
                "interco_status": bridge.get("status", ""),
            }
        else:
            # M-3 — Post JE at-cost di kedua buku PT (idempotent).
            je_result = await gl_service.post_intercompany_transfer({
                **transfer, "approved_at": now_iso(),
            })
        updated = await db.warehouse_transfers.find_one_and_update(
            {"id": transfer_id},
            {"$set": {"status": "completed", "approved_by": payload.approved_by,
                      "approved_at": now_iso(), "ownership_moved": result,
                      "je_intercompany": je_result, "updated_at": now_iso()}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER,
        )
        await audit(actor["name"], "inter_company_transfer_executed", "transfer", transfer_id,
                    {"approved_by": payload.approved_by, **result,
                     "je_posted": je_result.get("posted"),
                     "je_total": je_result.get("total", 0),
                     "je_pair_id": je_result.get("pair_id", "")})
        return safe_doc(updated)

    updated = await db.warehouse_transfers.find_one_and_update(
        {"id": transfer_id},
        {
            "$set": {
                "status": "approved",
                "approved_by": payload.approved_by,
                "approved_at": now_iso(),
                "updated_at": now_iso()
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    
    await audit(actor["name"], "transfer_approved", "transfer", transfer_id, {"approved_by": payload.approved_by})
    
    return safe_doc(updated)


@router.post("/transfers/{transfer_id}/reject")
async def reject_transfer(transfer_id: str, payload: TransferReject, request: Request) -> Dict[str, Any]:
    """
    Reject a transfer.
    
    Status: waiting_approval → rejected
    Requires permission: transfer.reject
    """
    actor = await require_permission(request, "transfer", "reject")
    transfer, _ctx = await _guard_transfer(request, transfer_id, side="source")  # FASE E-0 (L13)
    if transfer["status"] != "waiting_approval":
        raise HTTPException(status_code=400, detail=f"Transfer tidak bisa direject (status: {transfer['status']})")
    
    # Sub-fase 1.5 — inter-company: lepas reservasi roll di entitas sumber.
    if transfer.get("transfer_kind") == "inter_entity":
        await release_transfer_rolls(transfer_id)
    else:
        # Intra-entity: lepas roll yang direservasi saat create → available lagi di gudang asal.
        await release_wh_transfer_rolls(transfer_id)

    updated = await db.warehouse_transfers.find_one_and_update(
        {"id": transfer_id},
        {
            "$set": {
                "status": "rejected",
                "rejected_by": payload.rejected_by,
                "rejected_at": now_iso(),
                "rejected_reason": payload.reason,
                "updated_at": now_iso()
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    
    await audit(actor["name"], "transfer_rejected", "transfer", transfer_id, {"rejected_by": payload.rejected_by, "reason": payload.reason})
    
    return safe_doc(updated)


@router.post("/transfers/{transfer_id}/status")
async def update_transfer_status(transfer_id: str, payload: TransferStatusUpdate, request: Request) -> Dict[str, Any]:
    """
    Update transfer status (workflow progression).
    
    Valid transitions:
    - approved → picking
    - picking → staging
    - staging → dispatched
    - dispatched → completed
    - any → cancelled (requires cancel permission)
    
    Inventory impact:
    - dispatched: reduce source warehouse on_hand, increase in_transit
    - completed: reduce source in_transit, increase dest on_hand
    """
    actor = await require_permission(request, "transfer", "update")
    # FASE E-0 (L13) — status berjalan di sisi yang berhak: `completed` (terima barang)
    # milik entitas TUJUAN, sisanya milik entitas ASAL.
    _side = "dest" if payload.status == "completed" else "source"
    transfer, _ctx = await _guard_transfer(request, transfer_id, side=_side)
    current_status = transfer["status"]
    new_status = payload.status
    
    # Validate transition
    if not _validate_status_transition(current_status, new_status):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status transition: {current_status} → {new_status}"
        )
    
    # Roll-as-SSOT (KN_15 §9 / KN_16 §7) — transfer antar-gudang memindahkan ROLL,
    # BUKAN $inc balance. Balance selalu di-rebuild dari rolls oleh roll_service.
    if transfer.get("transfer_kind") != "inter_entity":
        if new_status == "dispatched":
            # reserved → in_transit_transfer (keluar dari gudang sumber)
            await dispatch_wh_transfer_rolls(transfer_id, source_document=f"transfer_{transfer['code']}")
        elif new_status == "completed":
            # in_transit_transfer → available @ gudang tujuan (owner tetap)
            await receive_wh_transfer_rolls(
                transfer_id, transfer["dest_warehouse_id"],
                source_document=f"transfer_{transfer['code']}",
            )
    
    # Update transfer status
    updated = await db.warehouse_transfers.find_one_and_update(
        {"id": transfer_id},
        {
            "$set": {
                "status": new_status,
                "updated_at": now_iso()
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    
    await audit(
        actor["name"],
        "transfer_status_changed",
        "transfer",
        transfer_id,
        {"from": current_status, "to": new_status, "updated_by": payload.updated_by}
    )
    
    return safe_doc(updated)


@router.delete("/transfers/{transfer_id}")
async def cancel_transfer(transfer_id: str, request: Request,
                          reason: str = Query("", max_length=500)) -> Dict[str, Any]:
    """
    Cancel a transfer (soft delete via status change).
    
    Can only cancel if status is not completed, rejected, or already cancelled.
    Requires permission: transfer.cancel

    FASE P5 — `reason` (opsional di API, WAJIB di layar): pembatalan transfer melepas
    roll yang tertahan, jadi keputusannya berdampak stok dan harus bisa
    dipertanggungjawabkan. Layar selalu mengirimkannya; API dibuat opsional supaya
    pemanggil lama (POC isolasi E-0) tidak berubah artinya. Alasannya BENAR-BENAR
    disimpan (`cancelled_reason` + audit log) — menanyakan alasan lalu membuangnya
    hanya membuat pengguna mengarang jawaban.
    """
    actor = await require_permission(request, "transfer", "cancel")
    transfer, _ctx = await _guard_transfer(request, transfer_id, side="source")  # FASE E-0 (L13)
    if transfer["status"] in ["completed", "rejected", "cancelled"]:
        raise HTTPException(status_code=400, detail=f"Transfer tidak bisa dibatalkan (status: {transfer['status']})")
    
    # Lepas roll yang tertahan (reserved ATAU in_transit_transfer) → available di gudang asal.
    if transfer.get("transfer_kind") == "inter_entity":
        await release_transfer_rolls(transfer_id)
    else:
        await release_wh_transfer_rolls(transfer_id)

    updated = await db.warehouse_transfers.find_one_and_update(
        {"id": transfer_id},
        {
            "$set": {
                "status": "cancelled",
                "cancelled_by": actor["name"],
                "cancelled_at": now_iso(),
                "cancelled_reason": (reason or "").strip(),
                "updated_at": now_iso()
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    
    await audit(actor["name"], "transfer_cancelled", "transfer", transfer_id,
                {"reason": (reason or "").strip()})
    
    return safe_doc(updated)
