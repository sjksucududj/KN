"""EPIC 6 — Document Relations / Process Timeline service.

Membangun graf relasi antar-dokumen (read-only) untuk Document Hub + deep-link.
Tidak menyimpan apa pun; semua relasi diturunkan dari field penghubung yang sudah ada:

  Sales chain (anchor = sales_order):
    [SpecialOrder*] -> SalesOrder -> Shipment(order_id) -> TaxInvoice(order_id)
      -> AR Receipt(allocations.order_id) -> Komisi (navigational, on-collection)

  Purchase chain (anchor = purchase_order):
    PurchaseRequisition(po_id) -> PurchaseOrder -> GRN(wms_tasks po_id+inbound)
      -> LandedCost(landed_cost_vouchers po_ids) -> VendorBill(vendor_bills po_id)

Tiap node membawa `link` agar frontend dapat deep-link (navigasi view in-app atau buka
dokumen/print via doc_url). Stage yang kosong tetap dikembalikan (no dead-end) dengan
`docs: []` + `empty_hint`.
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import safe_doc


def _link(
    kind: str = "view",
    view: Optional[str] = None,
    nav_id: Optional[str] = None,
    focus_type: Optional[str] = None,
    focus_id: Optional[str] = None,
    doc_url: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "kind": kind,                       # "view" | "url" | "none"
        "view": view,                       # activeView target di App.js
        "nav_id": nav_id or view,           # nav id sidebar (untuk active state)
        "focus_type": focus_type,           # untuk auto-open di view tujuan
        "focus_id": focus_id,
        "doc_url": doc_url,                 # relatif ke /api (frontend prefix API base)
    }


def _node(
    *,
    type: str,
    id: Optional[str],
    number: Optional[str],
    title: str,
    status: Optional[str] = None,
    date: Optional[str] = None,
    amount: Optional[float] = None,
    meta: Optional[str] = None,
    link: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "type": type,
        "id": id,
        "number": number,
        "title": title,
        "status": status,
        "date": date,
        "amount": amount,
        "meta": meta,
        "link": link or _link(kind="none"),
    }


def _po_total(po: Dict[str, Any]) -> Optional[float]:
    if po.get("total_amount") is not None:
        return float(po.get("total_amount") or 0)
    total = 0.0
    for it in po.get("items", []) or []:
        qty = float(it.get("quantity", it.get("qty", 0)) or 0)
        price = float(it.get("price", it.get("unit_price", 0)) or 0)
        total += qty * price
    return round(total, 2) if total else None


# ─────────────────────────── SALES ORDER CHAIN ───────────────────────────
async def _sales_order_stages(order: Dict[str, Any]) -> List[Dict[str, Any]]:
    oid = order["id"]
    stages: List[Dict[str, Any]] = []

    # Stage 0 (opsional) — sumber Special Order bila ada link eksplisit.
    sso_id = order.get("source_special_order_id")
    if sso_id:
        sso = safe_doc(await db.special_orders.find_one({"id": sso_id}, {"_id": 0}))
        if sso:
            stages.append({
                "key": "source", "label": "Pesanan Khusus (sumber)",
                "docs": [_node(
                    type="special_order", id=sso["id"], number=sso.get("number"),
                    title=sso.get("customer_name") or sso.get("type") or "Special Order",
                    status=sso.get("status"), date=sso.get("created_at"),
                    amount=sso.get("total_amount"),
                    link=_link(view="special-orders", focus_type="special_order", focus_id=sso["id"]),
                )],
            })

    # Stage 1 — Sales Order (anchor).
    stages.append({
        "key": "order", "label": "Pesanan Penjualan",
        "docs": [_node(
            type="sales_order", id=oid, number=order.get("number"),
            title=order.get("customer_name") or "Sales Order",
            status=order.get("status"), date=order.get("created_at"),
            amount=order.get("grand_total", order.get("total_amount")),
            meta=f"Sales: {order.get('sales_name') or '—'}",
            link=_link(view="orders", focus_type="sales_order", focus_id=oid),
        )],
    })

    # Stage 2 — Pengiriman (Surat Jalan).
    shipments = await db.shipments.find({"order_id": oid}, {"_id": 0}).sort("created_at", 1).to_list(200)
    stages.append({
        "key": "shipment", "label": "Pengiriman (Surat Jalan)",
        "empty_hint": "Belum ada pengiriman.",
        "docs": [_node(
            type="shipment", id=s["id"], number=s.get("shipment_no"),
            title=f"{s.get('product_name') or s.get('sku') or 'Item'} · {s.get('warehouse_name') or ''}".strip(" ·"),
            status="parsial" if s.get("is_partial") else (s.get("status") or "shipped"),
            date=s.get("created_at"),
            meta=f"{s.get('qty')} {s.get('unit') or ''}".strip(),
            link=_link(kind="url", doc_url=f"/shipments/{s['id']}/surat-jalan",
                       view="orders", focus_type="sales_order", focus_id=oid),
        ) for s in shipments],
    })

    # Stage 3 — Faktur Pajak.
    tax = await db.tax_invoices.find({"order_id": oid}, {"_id": 0}).sort("created_at", 1).to_list(50)
    stages.append({
        "key": "tax", "label": "Faktur Pajak",
        "empty_hint": "Belum ada Faktur Pajak (opsional).",
        "docs": [_node(
            type="tax_invoice", id=t["id"], number=t.get("number"),
            title=t.get("nsfp") and f"NSFP {t.get('nsfp')}" or "Faktur Pajak",
            status=t.get("status"), date=t.get("created_at"),
            amount=t.get("ppn_amount"),
            link=_link(view="tax-invoices", focus_type="tax_invoice", focus_id=t["id"],
                       doc_url=f"/tax-invoices/{t['id']}/document"),
        ) for t in tax],
    })

    # Stage 4 — Pembayaran (AR Receipt) yang dialokasikan ke order ini.
    receipts = await db.ar_receipts.find({"allocations.order_id": oid}, {"_id": 0}).sort("receipt_date", 1).to_list(100)
    rec_docs = []
    for r in receipts:
        applied = 0.0
        for a in r.get("allocations", []) or []:
            if a.get("order_id") == oid:
                applied += float(a.get("applied", 0) or 0)
        rec_docs.append(_node(
            type="ar_receipt", id=r["id"], number=r.get("number"),
            title=f"Pembayaran {r.get('method') or ''}".strip(),
            status=r.get("status"), date=r.get("receipt_date"),
            amount=round(applied, 2),
            meta=f"Total terima {r.get('amount')}",
            link=_link(view="customers-crm", focus_type="ar_receipt", focus_id=r["id"]),
        ))
    stages.append({
        "key": "payment", "label": "Pembayaran (AR)",
        "empty_hint": "Belum ada pembayaran tercatat.",
        "docs": rec_docs,
    })

    # Stage 5 — Komisi (navigational; on-collection per EPIC4 = level sales×periode).
    paid = order.get("payment_status") in ("partial", "paid")
    stages.append({
        "key": "commission", "label": "Komisi Sales",
        "empty_hint": "Komisi diakui saat tertagih (on-collection).",
        "docs": ([_node(
            type="commission", id=None, number=None,
            title=f"Komisi on-collection · {order.get('sales_name') or 'Sales'}",
            status=order.get("payment_status"),
            meta="Lihat rincian komisi per-SKU (Performa Saya / Sales Force)",
            link=_link(view="sales-home", nav_id="home", focus_type="commission",
                       focus_id=order.get("sales_name") or ""),
        )] if paid else []),
    })

    return stages


# ─────────────────────────── PURCHASE ORDER CHAIN ───────────────────────────
async def _purchase_order_stages(po: Dict[str, Any]) -> List[Dict[str, Any]]:
    poid = po["id"]
    stages: List[Dict[str, Any]] = []

    # Stage 0 — Purchase Requisition (sumber) via pr.po_id.
    pr = safe_doc(await db.purchase_requisitions.find_one({"po_id": poid}, {"_id": 0}))
    stages.append({
        "key": "requisition", "label": "Permintaan Pembelian (sumber)",
        "empty_hint": "PO ini tidak berasal dari PR.",
        "docs": ([_node(
            type="purchase_requisition", id=pr["id"], number=pr.get("number"),
            title=pr.get("warehouse_name") or pr.get("reason") or "Requisition",
            status=pr.get("status"), date=pr.get("created_at"),
            amount=pr.get("total_est_amount"),
            link=_link(view="purchase-requisitions", focus_type="purchase_requisition", focus_id=pr["id"]),
        )] if pr else []),
    })

    # Stage 1 — Purchase Order (anchor).
    stages.append({
        "key": "po", "label": "Pesanan Pembelian",
        "docs": [_node(
            type="purchase_order", id=poid, number=po.get("po_number"),
            title=po.get("supplier_name") or "Purchase Order",
            status=po.get("status"), date=po.get("created_at"),
            amount=_po_total(po),
            link=_link(view="purchasing", focus_type="purchase_order", focus_id=poid),
        )],
    })

    # Stage 2 — Penerimaan Barang (GRN) via wms_tasks inbound.
    tasks = await db.wms_tasks.find(
        {"po_id": poid, "flow_type": "inbound"}, {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    stages.append({
        "key": "grn", "label": "Penerimaan Barang (GRN)",
        "empty_hint": "Belum ada penerimaan barang.",
        "docs": [_node(
            type="grn", id=tk["id"], number=(tk.get("id") or "")[:14],
            title=f"{tk.get('product_name') or tk.get('sku') or 'Item'} · {tk.get('warehouse_name') or ''}".strip(" ·"),
            status=tk.get("status"), date=tk.get("completed_at") or tk.get("created_at"),
            meta=f"Diterima {tk.get('received_qty', 0)}/{tk.get('expected_qty', tk.get('quantity', 0))} {tk.get('unit') or ''}".strip(),
            link=_link(view="operations", nav_id="operations", focus_type="grn", focus_id=tk["id"]),
        ) for tk in tasks],
    })

    # Stage 3 — Landed Cost (voucher po_ids).
    vouchers = await db.landed_cost_vouchers.find({"po_ids": poid}, {"_id": 0}).sort("created_at", 1).to_list(100)
    stages.append({
        "key": "landed_cost", "label": "Landed Cost",
        "empty_hint": "Belum ada voucher landed cost.",
        "docs": [_node(
            type="landed_cost", id=v["id"], number=v.get("number") or v.get("voucher_number"),
            title=v.get("description") or "Landed Cost Voucher",
            status=v.get("status"), date=v.get("created_at"),
            amount=v.get("total_amount"),
            link=_link(view="landed-cost", focus_type="landed_cost", focus_id=v["id"]),
        ) for v in vouchers],
    })

    # Stage 4 — Vendor Bill (po_id).
    bills = await db.vendor_bills.find({"po_id": poid}, {"_id": 0}).sort("created_at", 1).to_list(100)
    stages.append({
        "key": "bill", "label": "Vendor Bill",
        "empty_hint": "Belum ada vendor bill.",
        "docs": [_node(
            type="vendor_bill", id=b["id"], number=b.get("number") or b.get("bill_number"),
            title=b.get("supplier_name") or "Vendor Bill",
            status=b.get("status") or b.get("payment_status"), date=b.get("created_at"),
            amount=b.get("total_amount") or b.get("amount"),
            link=_link(view="vendor-bills", focus_type="vendor_bill", focus_id=b["id"]),
        ) for b in bills],
    })

    return stages


# ─────────────────────────── PUBLIC ───────────────────────────
SUPPORTED = {"sales_order": "sales_orders", "purchase_order": "purchase_orders"}


async def build_relations(doc_type: str, doc_id: str) -> Optional[Dict[str, Any]]:
    """Return {doc_type, anchor, stages[]} atau None bila dokumen tak ditemukan."""
    if doc_type == "sales_order":
        order = safe_doc(await db.sales_orders.find_one({"id": doc_id}, {"_id": 0}))
        if not order:
            return None
        stages = await _sales_order_stages(order)
        anchor = {"type": "sales_order", "id": order["id"], "number": order.get("number"),
                  "title": order.get("customer_name"), "status": order.get("status")}
        return {"doc_type": doc_type, "anchor": anchor, "stages": stages}

    if doc_type == "purchase_order":
        po = safe_doc(await db.purchase_orders.find_one({"id": doc_id}, {"_id": 0}))
        if not po:
            return None
        stages = await _purchase_order_stages(po)
        anchor = {"type": "purchase_order", "id": po["id"], "number": po.get("po_number"),
                  "title": po.get("supplier_name"), "status": po.get("status")}
        return {"doc_type": doc_type, "anchor": anchor, "stages": stages}

    return None
