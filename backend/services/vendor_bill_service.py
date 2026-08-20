"""Vendor Bill service (Fase 5.2 — P0-2) — 3-Way Matching PO ↔ GR ↔ Bill.

Koleksi kanonik: `vendor_bills` (prefix vbill_). Nomor dokumen: VB-NNNNN.

Prinsip:
- AP (hutang) berbasis Vendor Bill yang sudah *posted*. PO tetap menyimpan
  ringkasan billed/unbilled (informasional) tanpa mengubah invarian PO lama.
- 3-way matching: PO (ordered) ↔ GR (received_qty per item) ↔ Bill (billed_qty),
  dengan toleransi qty & harga yang configurable di settings.purchasing.
- INVARIAN-SAFE: item.subtotal = price × billed_qty (GROSS); total_amount = Σ subtotal.
  Diskon & PPN disimpan di field terpisah (mengikuti pola PO P0-1).
"""
from typing import Any, Dict, List, Optional
from db import db
from core_utils import now_iso

# Status bill yang dipakai dedupe nomor invoice supplier (semua yang belum batal).
ACTIVE_BILL_STATUSES = {"draft", "pending_approval", "posted", "paid"}
# Status bill yang "menahan"/me-reserve qty tagih (cegah over-billing lintas bill).
# DRAFT TIDAK me-reserve (work-in-progress) agar draft terbengkalai tak memblokir
# penagihan sah; integritas dijaga via re-evaluasi match saat submit.
BILLED_RESERVE_STATUSES = {"pending_approval", "posted", "paid"}
# Status bill yang menimbulkan hutang (AP) — sudah resmi diakui.
AP_BILL_STATUSES = {"posted", "paid"}
TERMINAL_BILL_STATUSES = {"cancelled", "paid"}


async def already_billed_map(po_id: str, exclude_bill_id: Optional[str] = None) -> Dict[str, float]:
    """Σ billed_qty per product_id dari bill yang me-RESERVE qty (pending/posted/paid)
    pada satu PO. Dipakai untuk mencegah over-billing lintas beberapa tagihan."""
    q: Dict[str, Any] = {"po_id": po_id, "status": {"$in": list(BILLED_RESERVE_STATUSES)}}
    if exclude_bill_id:
        q["id"] = {"$ne": exclude_bill_id}
    out: Dict[str, float] = {}
    async for b in db.vendor_bills.find(q, {"_id": 0, "items": 1}):
        for it in b.get("items", []):
            pid = it.get("product_id")
            out[pid] = out.get(pid, 0.0) + float(it.get("billed_qty", 0) or 0)
    return {k: round(v, 4) for k, v in out.items()}


def _variance_pct(actual: float, base: float) -> float:
    if base <= 0:
        return 0.0
    return round((actual - base) / base * 100.0, 2)


def evaluate_match(
    po: Dict[str, Any],
    priced_items: List[Dict[str, Any]],
    match_mode: str,
    billed_so_far: Dict[str, float],
    qty_tol: float,
    price_tol: float,
) -> Dict[str, Any]:
    """Hitung 3-way match per item + agregat. PURE (tak menyentuh DB).

    `priced_items` = hasil compute_order_pricing (punya `quantity`==billed_qty,
    `price`, `subtotal`, dll) + field `billed_qty`. Mengembalikan dict:
      { items: [...enriched dgn `match`], match_status, exceptions, within_tolerance }

    Aturan:
      - base_qty = received_qty (mode 'received', 3-way ketat) atau ordered (mode 'ordered').
      - remaining = base_qty − already_billed. billed > remaining + tol → OVER_BILLED (blocked).
      - |price − po_price| / po_price > price_tol → PRICE_VARIANCE (warning, butuh approval).
    """
    po_items = {it.get("product_id"): it for it in po.get("items", [])}
    enriched: List[Dict[str, Any]] = []
    exceptions: List[Dict[str, Any]] = []
    blocked = False
    warning = False
    for bi in priced_items:
        pid = bi.get("product_id")
        po_it = po_items.get(pid, {})
        ordered = float(po_it.get("quantity", 0) or 0)
        received = float(po_it.get("received_qty", 0) or 0)
        prior = float(billed_so_far.get(pid, 0) or 0)
        billed = float(bi.get("billed_qty", bi.get("quantity", 0)) or 0)
        po_price = float(po_it.get("price", 0) or 0)
        price = float(bi.get("price", po_price) or 0)
        base_qty = received if match_mode == "received" else ordered
        remaining = round(base_qty - prior, 4)

        messages: List[str] = []
        # ── qty match ──
        qty_status = "ok"
        tol_qty = abs(remaining) * (qty_tol / 100.0)
        if billed > remaining + tol_qty + 1e-6:
            qty_status = "over_billed"
            blocked = True
            msg = (f"Tagih {billed:g} melebihi sisa yang boleh ditagih {remaining:g} "
                   f"({'diterima' if match_mode == 'received' else 'dipesan'}) + toleransi {qty_tol:g}%")
            messages.append(msg)
            exceptions.append({"product_id": pid, "sku": po_it.get("sku", ""),
                               "product_name": po_it.get("product_name", ""),
                               "type": "qty_over_billed", "detail": msg})
        elif billed > remaining + 1e-6:
            qty_status = "within_tolerance"
            warning = True
            msg = f"Tagih {billed:g} sedikit di atas sisa {remaining:g} namun dalam toleransi {qty_tol:g}%"
            messages.append(msg)
            exceptions.append({"product_id": pid, "sku": po_it.get("sku", ""),
                               "product_name": po_it.get("product_name", ""),
                               "type": "qty_within_tolerance", "detail": msg})

        # ── price match ──
        price_status = "ok"
        pvar = _variance_pct(price, po_price)
        if po_price > 0 and abs(pvar) > price_tol + 1e-6:
            price_status = "price_variance"
            warning = True
            msg = f"Harga {price:g} menyimpang {pvar:+g}% dari harga PO {po_price:g} (toleransi ±{price_tol:g}%)"
            messages.append(msg)
            exceptions.append({"product_id": pid, "sku": po_it.get("sku", ""),
                               "product_name": po_it.get("product_name", ""),
                               "type": "price_variance", "detail": msg})

        item = dict(bi)
        item.update({
            "sku": bi.get("sku") or po_it.get("sku", ""),
            "product_name": bi.get("product_name") or po_it.get("product_name", ""),
            "ordered_qty": ordered,
            "received_qty": received,
            "already_billed_qty": prior,
            "remaining_qty": remaining,
            "po_price": po_price,
            "match": {
                "qty_status": qty_status,
                "price_status": price_status,
                "qty_remaining": remaining,
                "price_variance_pct": pvar,
                "messages": messages,
            },
        })
        enriched.append(item)

    match_status = "blocked" if blocked else ("warning" if warning else "matched")
    return {
        "items": enriched,
        "match_status": match_status,
        "exceptions": exceptions,
        "within_tolerance": not blocked,
    }


def bill_financials(bill: Dict[str, Any]) -> Dict[str, Any]:
    """Hitung AP per bill: grand_total (incl PPN) − amount_paid = outstanding."""
    grand = float(bill.get("grand_total", 0) or 0)
    if grand <= 0:
        grand = float(bill.get("total_amount", 0) or 0)
    paid = float(bill.get("amount_paid", 0) or 0)
    outstanding = round(max(grand - paid, 0.0), 2)
    if paid <= 0.01:
        pay_status = "unpaid"
    elif outstanding <= 0.01:
        pay_status = "paid"
    else:
        pay_status = "partial"
    return {
        "grand_total": round(grand, 2),
        "amount_paid": round(paid, 2),
        "outstanding": outstanding,
        "payment_status": pay_status,
    }


async def next_bill_number() -> str:
    """Number series VB-NNNNN (cegah duplikat via max existing)."""
    last = await db.vendor_bills.find_one({}, {"_id": 0, "bill_number": 1}, sort=[("bill_number", -1)])
    n = 0
    if last and isinstance(last.get("bill_number"), str) and last["bill_number"].startswith("VB-"):
        try:
            n = int(last["bill_number"].split("-")[1])
        except (ValueError, IndexError):
            n = await db.vendor_bills.count_documents({})
    else:
        n = await db.vendor_bills.count_documents({})
    return f"VB-{n + 1:05d}"


async def sync_po_billing(po_id: str) -> Dict[str, Any]:
    """Hitung ulang ringkasan billed PO dari bill yang sudah AP (posted/paid).
    Tidak mengubah invarian PO; hanya menambah field ringkasan informasional."""
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        return {}
    billed_total = 0.0
    bill_count = 0
    billed_qty: Dict[str, float] = {}
    async for b in db.vendor_bills.find(
        {"po_id": po_id, "status": {"$in": list(AP_BILL_STATUSES)}}, {"_id": 0}
    ):
        billed_total += float(b.get("grand_total", 0) or 0)
        bill_count += 1
        for it in b.get("items", []):
            pid = it.get("product_id")
            billed_qty[pid] = billed_qty.get(pid, 0.0) + float(it.get("billed_qty", 0) or 0)
    grand = float(po.get("grand_total", 0) or po.get("total_amount", 0) or 0)
    summary = {
        "billed_total": round(billed_total, 2),
        "bill_count": bill_count,
        "unbilled_total": round(max(grand - billed_total, 0.0), 2),
    }
    await db.purchase_orders.update_one(
        {"id": po_id},
        {"$set": {**summary, "billed_qty_map": billed_qty, "updated_at": now_iso()}},
    )
    return summary


async def build_billing_context(po: Dict[str, Any]) -> Dict[str, Any]:
    """Susun konteks penagihan PO untuk pre-fill form Vendor Bill (per item:
    ordered / received / already_billed / billable)."""
    billed = await already_billed_map(po["id"])
    items = []
    for it in po.get("items", []):
        pid = it.get("product_id")
        ordered = float(it.get("quantity", 0) or 0)
        received = float(it.get("received_qty", 0) or 0)
        prior = float(billed.get(pid, 0) or 0)
        items.append({
            "product_id": pid,
            "sku": it.get("sku", ""),
            "product_name": it.get("product_name", ""),
            "unit": it.get("unit", "meter"),
            "ordered_qty": ordered,
            "received_qty": received,
            "already_billed_qty": round(prior, 4),
            "billable_received": round(max(received - prior, 0.0), 4),
            "billable_ordered": round(max(ordered - prior, 0.0), 4),
            "po_price": float(it.get("price", 0) or 0),
            "discount_percent": float(it.get("discount_percent", 0) or 0),
        })
    return {
        "po_id": po["id"],
        "po_number": po.get("po_number", ""),
        "supplier_id": po.get("supplier_id", ""),
        "supplier_name": po.get("supplier_name", ""),
        "supplier_npwp": po.get("supplier_npwp", ""),
        "warehouse_id": po.get("warehouse_id", ""),
        "warehouse_name": po.get("warehouse_name", ""),
        "entity_id": po.get("entity_id", ""),
        "po_status": po.get("status", ""),
        "tax_mode": po.get("tax_mode", ""),
        "ppn_rate": float(po.get("ppn_rate", 0) or 0),
        "items": items,
    }
