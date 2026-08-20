"""Inventory service: reservation expiry projections & document rendering.

Alokasi/reservasi stok kini SEPENUHNYA berbasis roll (roll-as-SSOT, KN_15) —
lihat services/roll_service.py. Fungsi lama berbasis $inc balance (allocate_stock/
atomic_reserve/rollback_reservations) telah DIHAPUS (D4) karena melanggar SSOT.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from db import db
from core_utils import now_iso, new_id, rupiah


async def product_summary(product_id: str) -> Dict[str, float]:
    balances = await db.inventory_balances.find({"product_id": product_id}, {"_id": 0}).to_list(100)
    return {
        "on_hand_qty": sum(float(b.get("on_hand_qty", 0)) for b in balances),
        "reserved_qty": sum(float(b.get("reserved_qty", 0)) for b in balances),
        "available_qty": sum(float(b.get("available_qty", 0)) for b in balances),
        # F2 (UoM SSOT) — jumlah roll agregat lintas gudang/owner (1 produk = 1 base_unit)
        "roll_count": sum(int(b.get("roll_count", 0) or 0) for b in balances),
        "on_hand_roll_count": sum(int(b.get("on_hand_roll_count", 0) or 0) for b in balances),
    }


async def expire_old_reservations() -> int:
    """Expire reservations older than 3 days (release di level ROLL — KN_15)."""
    cutoff = datetime.now(timezone.utc)
    orders = await db.sales_orders.find(
        {
            "status": {"$in": ["reserved", "waiting_approval", "approved", "waiting_stock"]},
            "reservation_expires_at": {"$lte": cutoff.isoformat()},
        },
        {"_id": 0},
    ).to_list(200)
    expired = 0
    from services.roll_service import release_order_rolls
    from services.so_status import stage_fields
    for order in orders:
        await release_order_rolls(order["id"])
        _exp_set = {"status": "expired", "allocations": [], "backorders": [],
                    "has_backorder": False, "updated_at": now_iso()}
        # F4 — stage/sub_status: expired → Cancelled/kedaluwarsa.
        _exp_set.update(stage_fields({**order, **_exp_set}))
        await db.sales_orders.update_one(
            {"id": order["id"]},
            {"$set": _exp_set}
        )
        from dependencies import audit
        await audit(
            "system", "reservation_expired", "sales_order",
            order["id"], {"status": "expired"}, "3 hari reservasi terlewati"
        )
        # Gelombang 1 F-1 — jurnal balik bila order sempat berjurnal (best-effort).
        try:
            from services import gl_service
            await gl_service.reverse_order_journals(order["id"], reason="reservasi kedaluwarsa")
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).error("Gagal reversal GL utk order expired %s: %s", order["id"], exc)
        expired += 1
    return expired


def jsonable(value: Any) -> Any:
    """Recursively convert MongoDB documents to JSON-safe types."""
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


async def _resolve_template(document_type: str, entity_id: str = "") -> Optional[Dict[str, Any]]:
    """Template cetak yang BERLAKU untuk satu badan usaha (override → global).

    FASE E-4 (E4.2). Dipisah jadi fungsi sendiri supaya jalur "kop surat siapa yang
    dipakai" bisa diuji langsung tanpa merender seluruh HTML.
    """
    from services import entity_master_service as ems
    return await ems.resolve_row("document-templates", document_type, entity_id)


async def render_order_html(
    order_id: str, document_type: str, template_override: Optional[Dict[str, Any]] = None
) -> str:
    """Render an order as printable HTML based on document type and template."""
    from core_utils import safe_doc
    order = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")
    customer = safe_doc(await db.customers.find_one({"id": order["customer_id"]}, {"_id": 0})) or {}
    
    # Safe get shipping_address_id with fallback
    shipping_address_id = order.get("shipping_address_id")
    if shipping_address_id and customer:
        address = next(
            (a for a in customer.get("addresses", []) if a["id"] == shipping_address_id),
            customer.get("addresses", [{}])[0] if customer.get("addresses") else {}
        )
    else:
        # Fallback to first address if shipping_address_id not set
        address = customer.get("addresses", [{}])[0] if customer and customer.get("addresses") else {}
    
    title_map = {
        "surat_jalan": "SURAT JALAN",
        "invoice": "INVOICE",
        "receipt": "RECEIPT",
        "surat_barang_keluar": "SURAT BARANG KELUAR",
        "surat_penerimaan_barang": "SURAT PENERIMAAN BARANG"
    }
    template = template_override or safe_doc(
        # FASE E-4 (E4.2) — template mengikuti BADAN USAHA pemilik dokumen: override
        # badan usaha menang, kalau tidak ada baru pakai template global. Dulu
        # `find_one({"document_type": ...})` bisa mengambil kop surat badan usaha lain.
        await _resolve_template(document_type, str(order.get("entity_id") or ""))
    ) or {}
    section_order = template.get("section_order") or ["header", "customer", "items", "allocation", "signature", "footer"]
    orientation = template.get("orientation", "portrait")
    margin_mm = int(template.get("margin_mm", 12))
    paper_size = template.get("paper_size", "A4")
    logo_html = (
        f"<img src='{template.get('logo_url')}' style='height:48px;object-fit:contain'/>"
        if template.get("logo_url")
        else "<h1>Kain Nusantara</h1>"
    )
    # Defensive rendering: dokumen TIDAK BOLEH 500 karena field display opsional
    # hilang (mis. allocation tanpa warehouse_city). Selalu pakai .get() + fallback.
    def _money(v):
        try:
            return f"{rupiah(float(v or 0))}"
        except (TypeError, ValueError):
            return "Rp 0"

    rows = "".join(
        f"<tr><td>{item.get('sku','')}</td><td>{item.get('product_name','')}</td>"
        f"<td>{item.get('quantity', item.get('qty',''))}</td>"
        f"<td>{item.get('unit','')}</td><td>{_money(item.get('price'))}</td>"
        f"<td>{_money(item.get('subtotal'))}</td></tr>"
        for item in order.get("items", [])
    )

    def _alloc_li(a):
        wh = a.get("warehouse_name") or a.get("warehouse_id") or "-"
        city = a.get("warehouse_city")
        loc = f"{wh} ({city})" if city else wh
        qty = a.get("quantity", a.get("qty", ""))
        unit = next((i.get("unit", "") for i in order.get("items", [])
                     if i.get("product_id") == a.get("product_id")), "")
        return f"<li>{loc} — {qty} {unit}</li>"

    allocation_rows = "".join(_alloc_li(a) for a in order.get("allocations", []))

    # Fase 1B — ringkasan pajak/diskon (tampil bila order punya breakdown grand_total)
    has_breakdown = order.get("grand_total") is not None
    if has_breakdown:
        srows = [f"<tr><td>Subtotal (bruto)</td><td class='r'>{_money(order.get('total_amount'))}</td></tr>"]
        if float(order.get("discount_total", 0) or 0) > 0:
            srows.append(f"<tr><td>Diskon</td><td class='r'>− {_money(order.get('discount_total'))}</td></tr>")
            srows.append(f"<tr><td>Subtotal Netto (DPP)</td><td class='r'>{_money(order.get('net_subtotal'))}</td></tr>")
        if float(order.get("ppn_amount", 0) or 0) > 0:
            srows.append(f"<tr><td>PPN {float(order.get('ppn_rate', 0) or 0):g}%</td><td class='r'>{_money(order.get('ppn_amount'))}</td></tr>")
        grand = order.get("grand_total", order.get("total_amount"))
        term = order.get("payment_term_name") or order.get("payment_term_code")
        totals_html = (
            f"<table class='totals'><tbody>{''.join(srows)}"
            f"<tr class='grand'><td><b>GRAND TOTAL</b></td><td class='r'><b>{_money(grand)}</b></td></tr>"
            f"</tbody></table>"
            + (f"<p class='muted'>Term Pembayaran: {term}</p>" if term else "")
        )
    else:
        totals_html = f"<h2>Total: {_money(order.get('total_amount'))}</h2>"

    sections = {
        "header": (
            f"<div class='top'><div>{logo_html}<p class='muted'>"
            f"{template.get('header', 'Enterprise Textile Warehouse')}</p></div>"
            f"<div><h2>{title_map.get(document_type, document_type)}</h2>"
            f"<p>{order.get('number','')}</p><p>{datetime.now(timezone.utc).strftime('%d %b %Y')}</p></div></div>"
        ),
        "customer": (
            f"<section><h3>Customer & Tujuan</h3><p><b>{customer.get('name','-')}</b> — {customer.get('pic_name','')}<br/>"
            f"{address.get('label','Alamat')} | {address.get('recipient_name','')} | {address.get('phone','')}<br/>"
            f"{address.get('address','')}, {address.get('city','')}</p></section>"
        ),
        "items": (
            f"<section><h3>Item</h3><table><thead><tr><th>SKU</th><th>Barang</th><th>Qty</th>"
            f"<th>Unit</th><th>Harga</th><th>Subtotal</th></tr></thead><tbody>{rows}</tbody></table>"
            f"{totals_html}</section>"
        ),
        "allocation": f"<section><h3>Fulfillment Gudang</h3><ul>{allocation_rows}</ul></section>",
        "signature": (
            f"<div class='sign'><div><p>{template.get('signature_left', 'Disiapkan Oleh')}</p>"
            f"<br/><br/><b>Warehouse</b></div>"
            f"<div><p>{template.get('signature_right', 'Diterima Oleh')}</p>"
            f"<br/><br/><b>{address.get('recipient_name', customer.get('pic_name',''))}</b></div></div>"
        ),
        "footer": f"<footer>{template.get('footer', 'Barang diterima dalam kondisi baik.')}</footer>",
    }
    body_html = "".join(sections.get(section, "") for section in section_order)
    return f"""
    <html><head><title>{title_map.get(document_type, document_type)} {order['number']}</title>
    <style>@page{{size:{paper_size} {orientation}; margin:{margin_mm}mm}} body{{font-family:Arial,sans-serif;padding:0;color:#111}} .top{{display:flex;justify-content:space-between;border-bottom:2px solid #111;padding-bottom:16px}} table{{width:100%;border-collapse:collapse;margin-top:18px}} td,th{{border:1px solid #ddd;padding:10px;text-align:left}} .muted{{color:#555}} .sign{{display:flex;justify-content:space-between;margin-top:56px}} section{{margin-top:22px}} footer{{margin-top:34px;border-top:1px solid #ddd;padding-top:12px;color:#555}} .totals{{width:auto;min-width:300px;margin-left:auto;margin-top:14px}} .totals td{{border:none;padding:4px 10px}} .totals td.r{{text-align:right}} .totals tr.grand td{{border-top:2px solid #111;font-size:15px}}</style></head>
    <body>{body_html}</body></html>
    """
