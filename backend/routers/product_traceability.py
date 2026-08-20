"""Traceability Asal Barang (S#2026-07-21).

Menyediakan:
- GET /api/products/{product_id}/purchase-history
    → "Kartu Asal Produk": riwayat pembelian per event penerimaan
      (tanggal, supplier, PO, invoice, lot, qty, harga, roll) — untuk tracking.
- GET /api/purchase-returns/source-rolls
    → daftar roll available yang bisa diretur, difilter asal (supplier/PO/lot)
      — untuk retur PRESISI per roll/lot.

Sumber kebenaran: inventory_rolls (denormalisasi asal) + fallback join purchase_orders.

**F0-C (entity scoping)** — `inventory_rolls` & `purchase_orders` adalah koleksi
SCOPED. Sebelumnya param `entity_id` hanya *opsional filter*: bila FE tidak
mengirimnya, query berjalan LINTAS-ENTITAS sehingga user PT A bisa melihat roll
dan nama supplier/PO milik PT B (kebocoran nyata, bukan teori). Kini pemilihan
cakupan dilakukan `resolve_list_scope()` — satu sumber kebenaran yang sama
dipakai seluruh router: tanpa param → entitas AKTIF · param eksplisit → wajib
∈ allowed (else 403) · `all` → hanya untuk role lintas-entitas.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Request, Query
from db import db
from dependencies import require_permission
from entity_scope import EntityContext, entity_ctx, resolve_list_scope

router = APIRouter(prefix="/api")


def _fnum(v) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


async def _po_supplier_index(po_ids: List[str],
                             ctx: Optional[EntityContext] = None) -> Dict[str, Dict[str, Any]]:
    """Index PO untuk enrich (nomor PO + supplier).

    Dibatasi ke entitas yang BOLEH diakses user (`allowed_entity_ids`) agar nama
    supplier/nomor PO milik PT lain tidak ikut terbawa lewat jalur enrichment.
    """
    ids = [p for p in {*po_ids} if p]
    if not ids:
        return {}
    q: Dict[str, Any] = {"id": {"$in": ids}}
    if ctx is not None:
        q["entity_id"] = {"$in": list(ctx.allowed_entity_ids)}
    pos = await db.purchase_orders.find(
        q,
        {"_id": 0, "id": 1, "po_number": 1, "supplier_id": 1, "supplier_name": 1, "created_at": 1},
    ).to_list(1000)
    return {p["id"]: p for p in pos}


@router.get("/products/{product_id}/purchase-history")
async def product_purchase_history(
    request: Request,
    product_id: str,
    entity_id: Optional[str] = Query(None, description="Filter owner entity (opsional)"),
    ctx: EntityContext = Depends(entity_ctx),
) -> Dict[str, Any]:
    """Kartu Asal Produk — dikelompokkan per event penerimaan (PO×lot)."""
    await require_permission(request, "product", "view")

    q = resolve_list_scope("inventory_rolls", {"product_id": product_id}, ctx, entity_id)
    rolls = await db.inventory_rolls.find(q, {"_id": 0}).to_list(20000)

    po_idx = await _po_supplier_index(
        [r.get("po_id") or (r.get("acquired") or {}).get("ref_id") for r in rolls], ctx)

    groups: Dict[tuple, Dict[str, Any]] = {}
    for r in rolls:
        acq = r.get("acquired") or {}
        po_id = r.get("po_id") or acq.get("ref_id") or ""
        via = acq.get("via", "initial")
        po = po_idx.get(po_id, {})
        supplier_name = r.get("supplier_name") or po.get("supplier_name") or (
            "Stok Awal" if via in ("initial", "seed") else "-")
        supplier_id = r.get("supplier_id") or po.get("supplier_id") or ""
        po_number = r.get("po_number") or po.get("po_number") or ("—" if via in ("initial", "seed") else po_id)
        date = r.get("received_date") or acq.get("date") or r.get("created_at") or ""
        lot = r.get("lot") or "-"
        key = (po_id or via, lot)

        g = groups.get(key)
        if not g:
            g = groups[key] = {
                "source_type": "purchase" if via in ("inbound", "purchase") else via,
                "date": date,
                "supplier_id": supplier_id,
                "supplier_name": supplier_name,
                "po_id": po_id,
                "po_number": po_number,
                "vendor_bill_id": r.get("vendor_bill_id", ""),
                "supplier_invoice_no": r.get("supplier_invoice_no", ""),
                "lot": lot,
                "unit": r.get("unit", "meter"),
                "qty_received": 0.0,
                "qty_remaining": 0.0,
                "roll_count": 0,
                "grades": set(),
                "landed_cost_total": 0.0,
                "_cost_sum": 0.0,
                "_cost_n": 0,
                "rolls": [],
            }
        if date and (not g["date"] or date < g["date"]):
            g["date"] = date
        if not g["supplier_invoice_no"] and r.get("supplier_invoice_no"):
            g["supplier_invoice_no"] = r["supplier_invoice_no"]
            g["vendor_bill_id"] = r.get("vendor_bill_id", g["vendor_bill_id"])
        g["qty_received"] = round(g["qty_received"] + _fnum(r.get("length_initial")), 2)
        g["qty_remaining"] = round(g["qty_remaining"] + _fnum(r.get("length_remaining")), 2)
        g["roll_count"] += 1
        if r.get("grade"):
            g["grades"].add(r["grade"])
        uc = _fnum(r.get("unit_cost") or r.get("base_unit_cost"))
        if uc > 0:
            g["_cost_sum"] += uc
            g["_cost_n"] += 1
        g["landed_cost_total"] = round(g["landed_cost_total"] + _fnum(r.get("landed_cost_total")), 2)
        g["rolls"].append({
            "roll_id": r.get("id"),
            "roll_no": r.get("roll_no", ""),
            "lot": lot,
            "status": r.get("status", ""),
            "qty_received": _fnum(r.get("length_initial")),
            "qty_remaining": _fnum(r.get("length_remaining")),
            "unit_cost": uc,
            "grade": r.get("grade", ""),
        })

    events: List[Dict[str, Any]] = []
    for g in groups.values():
        g["avg_unit_cost"] = round(g["_cost_sum"] / g["_cost_n"], 2) if g["_cost_n"] else 0.0
        g["grades"] = sorted(g["grades"])
        g.pop("_cost_sum", None)
        g.pop("_cost_n", None)
        events.append(g)
    events.sort(key=lambda e: (e.get("date") or ""), reverse=True)

    total_recv = round(sum(e["qty_received"] for e in events), 2)
    total_rem = round(sum(e["qty_remaining"] for e in events), 2)
    suppliers = sorted({e["supplier_name"] for e in events if e["supplier_name"] and e["supplier_name"] != "-"})
    prod = await db.products.find_one({"id": product_id}, {"_id": 0, "name": 1, "sku": 1, "base_unit": 1})

    return {
        "product_id": product_id,
        "product_name": (prod or {}).get("name", ""),
        "sku": (prod or {}).get("sku", ""),
        "summary": {
            "total_received": total_recv,
            "total_remaining": total_rem,
            "event_count": len(events),
            "supplier_count": len(suppliers),
            "suppliers": suppliers,
        },
        "events": events,
    }


async def build_returnable_rolls(product_id, supplier_id=None, po_id=None, warehouse_id=None,
                                 entity_id=None, ctx: Optional[EntityContext] = None):
    """Logika returnable rolls (dipakai juga oleh router purchase_returns agar
    route statis '/purchase-returns/source-rolls' menang atas '/{return_id}').

    `ctx` WAJIB dikirim oleh router (F0-C). Tanpa ctx, roll lintas-entitas bisa
    ikut terpilih untuk diretur — retur PT A memotong stok PT B.
    """
    q: Dict[str, Any] = {"product_id": product_id, "status": "available", "length_remaining": {"$gt": 0}}
    # FASE E-9 (E9.5) — penyaring asal barang dilonggarkan. Roll yang pernah melewati
    # RETUR PELANGGAN dan PERPINDAHAN KEPEMILIKAN antar-PT dulu tidak pernah muncul di
    # sini: `acquired` ditimpa menjadi `{"via":"transfer"}` sehingga jejak PO-nya hilang,
    # dan roll retur dibuat tanpa `supplier_id`. Sekarang tiga jalan dibaca:
    #   (1) field roll sendiri (diwarisi saat retur pelanggan dibuat),
    #   (2) riwayat perolehan `acquired_history[]` (append-only saat pindah kepemilikan),
    #   (3) silsilah LOT sebagai cadangan untuk data lama.
    ands: List[Dict[str, Any]] = []
    if supplier_id:
        sup_or: List[Dict[str, Any]] = [{"supplier_id": supplier_id}]
        lot_ids = [l["id"] for l in await db.inventory_lots.find(
            {"supplier_id": supplier_id}, {"_id": 0, "id": 1}).to_list(20000)]
        if lot_ids:
            sup_or.append({"lot_id": {"$in": lot_ids}})
        ands.append({"$or": sup_or})
    if po_id:
        ands.append({"$or": [{"po_id": po_id}, {"acquired.ref_id": po_id},
                             {"acquired_history.ref_id": po_id},
                             {"acquired_history.po_id": po_id}]})
    if ands:
        q["$and"] = ands
    if warehouse_id:
        q["warehouse_id"] = warehouse_id
    if ctx is not None:
        q = resolve_list_scope("inventory_rolls", q, ctx, entity_id)
    elif entity_id and entity_id != "all":
        q["owner_entity_id"] = entity_id
    rolls = await db.inventory_rolls.find(q, {"_id": 0}).to_list(20000)
    po_idx = await _po_supplier_index(
        [r.get("po_id") or (r.get("acquired") or {}).get("ref_id") for r in rolls], ctx)
    items = []
    for r in rolls:
        po = po_idx.get(r.get("po_id") or (r.get("acquired") or {}).get("ref_id") or "", {})
        items.append({
            "roll_id": r.get("id"), "roll_no": r.get("roll_no", ""), "lot": r.get("lot", ""),
            "dye_lot": r.get("dye_lot", ""), "qty_remaining": _fnum(r.get("length_remaining")),
            "unit": r.get("unit", "meter"), "unit_cost": _fnum(r.get("unit_cost") or r.get("base_unit_cost")),
            "grade": r.get("grade", ""), "warehouse_id": r.get("warehouse_id", ""),
            "supplier_id": r.get("supplier_id") or po.get("supplier_id", ""),
            "supplier_name": r.get("supplier_name") or po.get("supplier_name", ""),
            "po_number": r.get("po_number") or po.get("po_number", ""),
            "supplier_invoice_no": r.get("supplier_invoice_no", ""),
            "received_date": r.get("received_date") or (r.get("acquired") or {}).get("date", ""),
        })
    items.sort(key=lambda x: (x.get("received_date") or "", x.get("roll_no") or ""))
    total = round(sum(i["qty_remaining"] for i in items), 2)
    return {"product_id": product_id, "count": len(items), "total_returnable": total, "rolls": items}
