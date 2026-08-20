"""Blanket / Contract PO service (P2 — call-off).

Aturan owner:
  1.c komitmen = kuantitas per item + plafon nilai (GROSS Rp).
  2.a tiap call-off = PO anak (approval + receiving normal) — dibuat oleh router via _create_po_core.
  3.b harga call-off boleh override (alasan WAJIB + audit).
  4.b call-off melebihi sisa → DIIZINKAN tapi WAJIB approval (force_approval).
  5.a kontrak kadaluarsa / kuantitas / nilai habis → 'closed/expired/exhausted' → call-off DITOLAK.

Drawdown dihitung LIVE dari PO anak (po_type='call_off', parent_po_id, status ∉ {cancelled,rejected}),
basis GROSS (Σ qty×price) konsisten dgn invarian total_amount. Cache disimpan untuk display.
Service ini TIDAK membuat PO anak (hindari import siklik); router meng-orkestrasi pembuatan.
"""
from datetime import date
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from db import db
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID, timeline_entry, next_doc_number, rupiah
from request_context import active_entity_or

EPS = 1e-6
CALLOFF_EXCLUDE_STATUSES = {"cancelled", "rejected"}


def _today_iso() -> str:
    return date.today().isoformat()


async def _resolve_supplier(supplier_id: str, supplier_name: str, supplier_contact: str) -> Tuple[str, str, str, str]:
    sid, sname, scontact, snpwp = "", (supplier_name or "").strip(), supplier_contact or "", ""
    if supplier_id:
        s = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
        if not s:
            raise HTTPException(status_code=404, detail="Supplier tidak ditemukan")
        sid, sname, snpwp = s["id"], s.get("name", ""), s.get("npwp", "")
        if not scontact:
            scontact = " | ".join([x for x in [s.get("pic_name", ""), s.get("phone", "")] if x])
    if not sname:
        raise HTTPException(status_code=400, detail="Supplier wajib dipilih atau diisi")
    # FASE E-7 (E7.2) — kontrak Blanket PO adalah komitmen beli ke pemasok LUAR.
    # Ke badan usaha grup, komitmen harganya adalah **kontrak internal** (menu Antar
    # Entitas); kalau lewat sini, call-off-nya akan melahirkan PO biasa dan margin
    # antar-PT tidak pernah dieliminasi. Nama bebas pun ikut dicocokkan supaya tidak
    # ada pintu belakang.
    from services import group_partner_service as _grp
    await _grp.assert_supplier_not_group_entity(
        {"id": sid, "name": sname, "npwp": snpwp} if sid else {"name": sname, "npwp": snpwp},
        doc_label="Kontrak Blanket PO")
    return sid, sname, scontact, snpwp


async def create_blanket(payload, actor: Dict[str, Any]) -> Dict[str, Any]:
    """Buat kontrak Blanket PO (po_type='blanket', status 'active'). Tanpa inbound task."""
    wh = await db.warehouses.find_one({"id": payload.warehouse_id}, {"_id": 0})
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse tidak ditemukan")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Kontrak harus punya minimal 1 item")
    sid, sname, scontact, snpwp = await _resolve_supplier(
        payload.supplier_id, payload.supplier_name, payload.supplier_contact)

    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(1000)}
    items: List[Dict[str, Any]] = []
    seen = set()
    for it in payload.items:
        p = products.get(it.product_id)
        if not p:
            raise HTTPException(status_code=404, detail=f"Produk {it.product_id} tidak ditemukan")
        if it.product_id in seen:
            raise HTTPException(status_code=400, detail=f"Produk {p.get('sku')} duplikat dalam kontrak")
        seen.add(it.product_id)
        if float(it.contract_qty or 0) <= 0:
            raise HTTPException(status_code=400, detail=f"Qty kontrak {p.get('sku')} harus > 0")
        items.append({
            "product_id": p["id"], "sku": p.get("sku", ""), "product_name": p.get("name", ""),
            "unit": it.unit or p.get("base_unit", "meter"), "base_unit": p.get("base_unit", "meter"),
            "contract_qty": round(float(it.contract_qty), 2),
            "contract_price": round(float(it.contract_price or p.get("price", 0) or 0), 2),
            "called_qty": 0.0, "remaining_qty": round(float(it.contract_qty), 2),
        })

    # FASE E-1 (E1.10) — kontrak blanket milik badan usaha konteks bila tak disebut.
    entity_id = payload.entity_id or active_entity_or(DEFAULT_ENTITY_ID)
    valid_from = (payload.valid_from or "").strip()
    valid_until = (payload.valid_until or "").strip()
    if valid_until and valid_from and valid_until < valid_from:
        raise HTTPException(status_code=400, detail="valid_until tidak boleh sebelum valid_from")
    cap = round(float(payload.contract_value_cap or 0), 2)
    if cap <= 0:
        cap = round(sum(i["contract_qty"] * i["contract_price"] for i in items), 2)

    po_number = await next_doc_number("purchase_orders", "po_number", "PO-", entity_id=entity_id)
    actor_name = payload.created_by or actor.get("name", "Admin")
    doc = {
        "id": new_id("po"), "po_number": po_number, "po_type": "blanket",
        "supplier_id": sid, "supplier_name": sname, "supplier_contact": scontact, "supplier_npwp": snpwp,
        "warehouse_id": payload.warehouse_id, "warehouse_name": wh.get("name", ""),
        "warehouse_city": wh.get("city", ""),
        "contract_items": items, "contract_value_cap": cap, "value_called": 0.0,
        "valid_from": valid_from, "valid_until": valid_until,
        "status": "active", "contract_status": "active",
        "notes": payload.notes or "", "entity_id": entity_id,
        # display helpers (bukan AP — status 'active' di luar AP_LIABILITY_STATUSES)
        "total_amount": cap, "grand_total": cap,
        "timeline": [timeline_entry("created", "Kontrak Blanket PO dibuat", actor_name,
                                    f"{len(items)} item · plafon {rupiah(cap)}")],
        "version": 1, "amendments": [],
        "created_by": actor_name, "created_by_id": actor.get("id", ""),
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    # Fase A · PS-09/D-19 — Blanket/kontrak: grade diturunkan dari master produk.
    from services import grade_service
    await grade_service.stamp_expected_grade(doc.get("items", []), allow_derive=True,
                                             context="Blanket PO")
    from services import line_scope as _lines            # FASE L
    await _lines.stamp_doc(db, doc)
    await db.purchase_orders.insert_one(doc)
    return safe_doc(await db.purchase_orders.find_one({"id": doc["id"]}, {"_id": 0}))


async def _aggregate_calloffs(blanket_id: str):
    """Σ ordered qty per produk + Σ total_amount(GROSS) dari call-off aktif (non batal/tolak)."""
    calloffs = await db.purchase_orders.find(
        {"parent_po_id": blanket_id, "po_type": "call_off",
         "status": {"$nin": list(CALLOFF_EXCLUDE_STATUSES)}},
        {"_id": 0, "items": 1, "total_amount": 1, "id": 1, "po_number": 1,
         "status": 1, "created_at": 1, "approval_required": 1, "approval_reason": 1}).to_list(500)
    qty_by_prod: Dict[str, float] = {}
    value_called = 0.0
    for co in calloffs:
        for it in co.get("items", []):
            qty_by_prod[it["product_id"]] = qty_by_prod.get(it["product_id"], 0.0) + float(it.get("quantity", 0) or 0)
        value_called += float(co.get("total_amount", 0) or 0)
    return qty_by_prod, round(value_called, 2), calloffs


def _derive_status(blanket: Dict[str, Any], items_enriched: List[Dict[str, Any]], value_called: float) -> str:
    if blanket.get("status") == "closed":
        return "closed"
    vu = (blanket.get("valid_until") or "").strip()
    if vu and vu < _today_iso():
        return "expired"
    cap = float(blanket.get("contract_value_cap", 0) or 0)
    qty_exhausted = bool(items_enriched) and all(i["remaining_qty"] <= EPS for i in items_enriched)
    value_exhausted = cap > 0 and value_called >= cap - EPS
    if qty_exhausted or value_exhausted:
        return "exhausted"
    return "active"


async def recompute_blanket_drawdown(blanket: Dict[str, Any], persist: bool = True) -> Dict[str, Any]:
    """Hitung called/remaining per item + nilai terpakai/sisa + status turunan (5.a)."""
    qty_by_prod, value_called, calloffs = await _aggregate_calloffs(blanket["id"])
    enriched: List[Dict[str, Any]] = []
    for it in blanket.get("contract_items", []):
        called = round(qty_by_prod.get(it["product_id"], 0.0), 2)
        remaining = round(max(float(it.get("contract_qty", 0) or 0) - called, 0.0), 2)
        enriched.append({
            "product_id": it["product_id"], "sku": it.get("sku", ""), "product_name": it.get("product_name", ""),
            "unit": it.get("unit", "meter"), "base_unit": it.get("base_unit", "meter"),
            "contract_qty": round(float(it.get("contract_qty", 0) or 0), 2),
            "contract_price": round(float(it.get("contract_price", 0) or 0), 2),
            "called_qty": called, "remaining_qty": remaining,
        })
    cap = float(blanket.get("contract_value_cap", 0) or 0)
    value_remaining = round(max(cap - value_called, 0.0), 2)
    derived = _derive_status(blanket, enriched, value_called)
    result = {
        "contract_items": enriched, "value_called": value_called, "value_remaining": value_remaining,
        "contract_value_cap": round(cap, 2), "contract_status": derived,
        "call_off_count": len(calloffs),
        "call_offs": sorted(calloffs, key=lambda c: c.get("created_at", ""), reverse=True),
    }
    if persist:
        await db.purchase_orders.update_one({"id": blanket["id"]}, {"$set": {
            "contract_items": enriched, "value_called": value_called,
            "contract_status": derived, "updated_at": now_iso()}})
    return result


async def prepare_call_off(blanket_id: str, payload, actor: Dict[str, Any]) -> Dict[str, Any]:
    """Validasi call-off & susun payload PO anak. Mengembalikan flag force_approval (4.b)."""
    blanket = await db.purchase_orders.find_one({"id": blanket_id}, {"_id": 0})
    if not blanket:
        raise HTTPException(status_code=404, detail="Blanket PO tidak ditemukan")
    if blanket.get("po_type") != "blanket":
        raise HTTPException(status_code=400, detail="PO ini bukan kontrak Blanket PO")

    draw = await recompute_blanket_drawdown(blanket, persist=True)
    cstatus = draw["contract_status"]
    if cstatus != "active":  # 5.a
        msg = {"expired": "Kontrak sudah kadaluarsa", "exhausted": "Kuantitas/nilai kontrak sudah habis",
               "closed": "Kontrak sudah ditutup"}.get(cstatus, "Kontrak tidak aktif")
        raise HTTPException(status_code=400, detail=f"{msg} — call-off baru ditolak (aturan 5.a).")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Call-off harus punya minimal 1 item")

    cmap = {i["product_id"]: i for i in draw["contract_items"]}
    over_call, over_items, has_override = False, [], False
    new_gross, out_items, seen = 0.0, [], set()
    for it in payload.items:
        ci = cmap.get(it.product_id)
        if not ci:
            raise HTTPException(status_code=400,
                                detail=f"Produk {it.product_id} tidak ada dalam kontrak — gunakan PO standar.")
        if it.product_id in seen:
            raise HTTPException(status_code=400, detail=f"Produk {ci['sku']} duplikat dalam call-off")
        seen.add(it.product_id)
        qty = float(it.quantity or 0)
        if qty <= 0:
            raise HTTPException(status_code=400, detail=f"Qty {ci['sku']} harus > 0")
        price = float(it.price or 0)
        if price <= 0:
            price = float(ci["contract_price"])
        elif abs(price - float(ci["contract_price"])) > 0.01:  # 3.b override
            has_override = True
        new_gross += qty * price
        if qty > ci["remaining_qty"] + EPS:  # 4.b over-call (qty)
            over_call = True
            over_items.append(f"{ci['sku']} (minta {qty:g}, sisa {ci['remaining_qty']:g})")
        out_items.append({"product_id": it.product_id, "quantity": qty,
                          "unit": it.unit or ci["unit"], "price": round(price, 2),
                          "discount_percent": float(it.discount_percent or 0)})

    if has_override and not (payload.price_override_reason or "").strip():
        raise HTTPException(status_code=400, detail="Override harga call-off wajib menyertakan alasan (aturan 3.b).")
    if draw["contract_value_cap"] > 0 and new_gross > draw["value_remaining"] + EPS:  # 4.b over-call (nilai)
        over_call = True
        over_items.append(f"nilai (minta {rupiah(new_gross)}, sisa {rupiah(draw['value_remaining'])})")

    from schemas import PurchaseOrderCreate
    po_payload = PurchaseOrderCreate(
        supplier_id=blanket.get("supplier_id", ""),
        supplier_name=blanket.get("supplier_name", ""),
        supplier_contact=blanket.get("supplier_contact", ""),
        warehouse_id=payload.warehouse_id or blanket["warehouse_id"],
        items=out_items,
        expected_delivery_date=payload.expected_delivery_date or "",
        notes=payload.notes or "",
        created_by=payload.created_by or actor.get("name", "Admin"),
        entity_id=blanket.get("entity_id", ""),
        order_discount_percent=float(payload.order_discount_percent or 0),
        tax_mode=payload.tax_mode or "",
    )
    return {
        "blanket": blanket, "po_payload": po_payload,
        "force_approval": over_call, "force_reason": "blanket_overcall",
        "over_items": over_items, "has_override": has_override,
        "price_override_reason": (payload.price_override_reason or "").strip(),
    }


async def list_blankets(entity_id: str = None,
                        scope: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Daftar Blanket PO + drawdown ringkas (called/remaining/status)."""
    q: Dict[str, Any] = dict(scope or {})
    q["po_type"] = "blanket"
    if scope is None and entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    blankets = await db.purchase_orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    out = []
    for b in blankets:
        draw = await recompute_blanket_drawdown(b, persist=True)
        b["contract_items"] = draw["contract_items"]
        b["value_called"] = draw["value_called"]
        b["value_remaining"] = draw["value_remaining"]
        b["contract_status"] = draw["contract_status"]
        b["call_off_count"] = draw["call_off_count"]
        out.append(b)
    return out


async def close_blanket(blanket_id: str, reason: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    """Tutup kontrak Blanket secara manual (call-off baru ditolak)."""
    blanket = await db.purchase_orders.find_one({"id": blanket_id}, {"_id": 0})
    if not blanket:
        raise HTTPException(status_code=404, detail="Blanket PO tidak ditemukan")
    if blanket.get("po_type") != "blanket":
        raise HTTPException(status_code=400, detail="PO ini bukan kontrak Blanket PO")
    if blanket.get("status") == "closed":
        raise HTTPException(status_code=400, detail="Kontrak sudah ditutup")
    await db.purchase_orders.update_one({"id": blanket_id}, {"$set": {
        "status": "closed", "contract_status": "closed", "close_reason": reason,
        "closed_by": actor.get("name", "Admin"), "closed_at": now_iso(), "updated_at": now_iso()},
        "$push": {"timeline": timeline_entry("closed", "Kontrak ditutup", actor.get("name", "Admin"), reason or "")}})
    updated = await db.purchase_orders.find_one({"id": blanket_id}, {"_id": 0})
    return await recompute_blanket_drawdown(updated, persist=True) | {"po": safe_doc(updated)}
