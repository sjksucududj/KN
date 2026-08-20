"""Faktur Pajak Jual (tax_invoices) service — Sub-fase 1.9.

Terbitkan Faktur Pajak dari Sales Order (MANUAL, OPSIONAL — pajak tidak wajib).
- Hanya entitas PKP + transaksi kena pajak (ppn_amount > 0).
- Penomoran HYBRID: internal FKT-##### + NSFP resmi 16-digit (diisi menyusul) + kode_transaksi.
- Status: normal | pengganti (revisi) | batal. Snapshot penjual (entitas) & pembeli (customer).
- DPP/PPN diambil dari snapshot pajak order (Fase 1B). Render dokumen defensif (.get()).
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from fastapi import HTTPException
from db import db
from core_utils import new_id, now_iso, safe_doc, next_doc_number

ELIGIBLE_ORDER_STATUSES = {"confirmed", "partially_picked", "picked",
                          "partially_shipped", "shipped", "done"}
KODE_TRANSAKSI_VALID = {"01", "02", "03", "04", "06", "07", "08", "09"}
STATUS_CODE = {"normal": "0", "pengganti": "1"}


def _money(v: Any) -> str:
    try:
        return "Rp " + f"{float(v or 0):,.0f}".replace(",", ".")
    except Exception:
        return "Rp 0"


async def _next_faktur_no(entity_id: Optional[str] = None) -> str:
    return await next_doc_number("tax_invoices", "number", "FKT-", entity_id=entity_id)


def _entity_is_pkp(entity: Dict[str, Any], order: Dict[str, Any]) -> bool:
    if entity and entity.get("default_tax_mode") == "ppn":
        return True
    return bool(order.get("is_pkp")) and float(order.get("ppn_amount", 0) or 0) > 0


def format_nsfp_display(fkt: Dict[str, Any]) -> str:
    """Kode & Nomor Seri Faktur Pajak resmi: {kode}{status_code}.{NNN-NN.NNNNNNNN}."""
    kode = fkt.get("kode_transaksi", "01")
    scode = STATUS_CODE.get(fkt.get("status", "normal"), "0")
    serial = (fkt.get("nsfp") or "").strip()
    if serial:
        digits = "".join(ch for ch in serial if ch.isdigit())
        if len(digits) >= 13:
            body = digits[-13:]
            return f"{kode}{scode}.{body[:3]}-{body[3:5]}.{body[5:]}"
        return serial
    return f"{kode}{scode}.___-__.________ (NSFP belum diisi)"


def _primary_address(customer: Dict[str, Any]) -> Dict[str, Any]:
    addrs = customer.get("addresses", []) or []
    for a in addrs:
        if a.get("is_primary"):
            return a
    return addrs[0] if addrs else {}


def _build_items(order: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for it in order.get("items", []):
        out.append({
            "product_name": it.get("product_name", ""),
            "sku": it.get("sku", ""),
            "quantity": float(it.get("quantity", 0) or 0),
            "unit": it.get("unit", ""),
            "price": float(it.get("price", 0) or 0),
            "subtotal": float(it.get("subtotal", 0) or 0),
            "discount_amount": float(it.get("discount_amount", 0) or 0),
            "line_total": float(it.get("line_total", it.get("subtotal", 0)) or 0),
        })
    return out


def _snapshot_from_order(order: Dict[str, Any], entity: Dict[str, Any],
                        customer: Dict[str, Any]) -> Dict[str, Any]:
    addr = _primary_address(customer)
    seller_addr = f"{entity.get('address','')}, {entity.get('city','')}".strip(", ")
    cust_addr = f"{addr.get('address','')}, {addr.get('city','')}".strip(", ")
    return {
        "entity_id": order.get("entity_id"),
        "seller_name": entity.get("legal_name", "Kain Nusantara"),
        "seller_npwp": entity.get("npwp", ""),
        "seller_address": seller_addr,
        "customer_id": customer.get("id", order.get("customer_id")),
        "customer_name": order.get("customer_name", customer.get("name", "")),
        "customer_npwp": customer.get("npwp", ""),
        "customer_address": cust_addr,
        "has_customer_npwp": bool(customer.get("npwp")),
        "items": _build_items(order),
        "total_amount": float(order.get("total_amount", 0) or 0),
        "discount_total": float(order.get("discount_total", 0) or 0),
        "net_subtotal": float(order.get("net_subtotal", 0) or 0),
        "dpp": float(order.get("dpp", 0) or 0),
        "dpp_nilai_lain": bool(order.get("dpp_nilai_lain")),
        "effective_rate": float(order.get("effective_rate", order.get("ppn_rate", 0)) or 0),
        "ppn_rate": float(order.get("ppn_rate", 0) or 0),
        "ppn_mode": order.get("ppn_mode", "excluded"),
        "ppn_amount": float(order.get("ppn_amount", 0) or 0),
        "grand_total": float(order.get("grand_total", 0) or 0),
        "is_pkp": True,
    }


async def _load_order_entity_customer(order_id: str):
    order = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")
    entity = safe_doc(await db.business_entities.find_one(
        {"id": order.get("entity_id")}, {"_id": 0})) or {}
    customer = safe_doc(await db.customers.find_one(
        {"id": order.get("customer_id")}, {"_id": 0})) or {}
    return order, entity, customer


def _validate_eligibility(order: Dict[str, Any], entity: Dict[str, Any], kode: str):
    if order.get("status") not in ELIGIBLE_ORDER_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Faktur Pajak hanya untuk order terkonfirmasi ke atas (status sekarang: {order.get('status')}).")
    if kode not in KODE_TRANSAKSI_VALID:
        raise HTTPException(status_code=400, detail=f"Kode transaksi tidak valid: {kode}")
    if not _entity_is_pkp(entity, order):
        raise HTTPException(
            status_code=400,
            detail="Entitas non-PKP — Faktur Pajak tidak dapat diterbitkan (pajak tidak wajib untuk entitas ini).")
    if float(order.get("ppn_amount", 0) or 0) <= 0:
        raise HTTPException(
            status_code=400,
            detail="Order tanpa PPN — Faktur Pajak hanya untuk transaksi kena pajak.")


async def issue_tax_invoice(order_id: str, kode_transaksi: Optional[str],
                           faktur_date: Optional[str], nsfp: Optional[str],
                           actor_name: str) -> Dict[str, Any]:
    """Terbitkan Faktur Pajak (status normal) dari order. Idempotent: 1 faktur aktif/order."""
    order, entity, customer = await _load_order_entity_customer(order_id)
    # F-10 — DPP Nilai Lain → kode transaksi default 04 (DPP Nilai Lain, Coretax)
    kode = (kode_transaksi or ("04" if order.get("dpp_nilai_lain") else "01")).strip()
    _validate_eligibility(order, entity, kode)
    existing = await db.tax_invoices.find_one(
        {"order_id": order_id, "status": {"$ne": "batal"}}, {"_id": 0})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Faktur Pajak sudah diterbitkan untuk order ini ({existing.get('number')}). Gunakan Pengganti untuk revisi.")
    fkt = {
        "id": new_id("fkt"),
        "number": await _next_faktur_no(order.get("entity_id")),
        "nsfp": (nsfp or "").strip(),
        "kode_transaksi": kode,
        "status": "normal",
        "replaces_id": None, "replaced_by_id": None, "cancel_reason": "",
        "faktur_date": faktur_date or now_iso(),
        "order_id": order_id, "order_number": order.get("number", ""),
        "created_by": actor_name, "created_at": now_iso(), "updated_at": now_iso(),
        **_snapshot_from_order(order, entity, customer),
    }
    await db.tax_invoices.insert_one(dict(fkt))
    from services import doc_refs_service as _refs
    await _refs.safe_link(("tax_invoice", fkt["id"]), ("sales_order", order_id),
                          "parent", note="faktur pajak atas pesanan")
    return safe_doc(fkt)


async def set_nsfp(fkt_id: str, nsfp: str, kode_transaksi: Optional[str]) -> Dict[str, Any]:
    fkt = safe_doc(await db.tax_invoices.find_one({"id": fkt_id}, {"_id": 0}))
    if not fkt:
        raise HTTPException(status_code=404, detail="Faktur Pajak tidak ditemukan")
    if fkt.get("status") == "batal":
        raise HTTPException(status_code=400, detail="Faktur Pajak batal tidak bisa diubah.")
    upd = {"nsfp": (nsfp or "").strip(), "updated_at": now_iso()}
    if kode_transaksi:
        if kode_transaksi.strip() not in KODE_TRANSAKSI_VALID:
            raise HTTPException(status_code=400, detail=f"Kode transaksi tidak valid: {kode_transaksi}")
        upd["kode_transaksi"] = kode_transaksi.strip()
    await db.tax_invoices.update_one({"id": fkt_id}, {"$set": upd})
    return safe_doc(await db.tax_invoices.find_one({"id": fkt_id}, {"_id": 0}))


async def replace_tax_invoice(fkt_id: str, reason: Optional[str],
                             kode_transaksi: Optional[str], nsfp: Optional[str],
                             actor_name: str) -> Dict[str, Any]:
    """Buat Faktur Pajak PENGGANTI (revisi). Original ditandai replaced."""
    original = safe_doc(await db.tax_invoices.find_one({"id": fkt_id}, {"_id": 0}))
    if not original:
        raise HTTPException(status_code=404, detail="Faktur Pajak tidak ditemukan")
    if original.get("source_type") == "interco":
        # FASE G-6b — faktur pajak INTERNAL tidak lahir dari pesanan penjualan, jadi
        # jalur pengganti ini tidak bisa memuat ordernya. Arahkan ke layarnya sendiri
        # (kalau tidak, pengguna cuma melihat 404 "Order tidak ditemukan").
        raise HTTPException(
            status_code=400,
            detail=("Faktur pajak internal antar-PT diganti dari layar Antar Entitas "
                    "(Pembelian → Hutang Supplier → Antar Entitas → buka transaksinya → "
                    "tombol Faktur Pengganti), supaya pasangan faktur masukan di PT "
                    "pembeli ikut diperbarui."))
    if original.get("status") == "batal":
        raise HTTPException(status_code=400, detail="Faktur Pajak batal tidak bisa diganti.")
    if original.get("replaced_by_id"):
        raise HTTPException(status_code=409, detail="Faktur ini sudah pernah diganti.")
    order, entity, customer = await _load_order_entity_customer(original["order_id"])
    kode = (kode_transaksi or original.get("kode_transaksi")
            or ("04" if order.get("dpp_nilai_lain") else "01")).strip()
    _validate_eligibility(order, entity, kode)
    new_fkt = {
        "id": new_id("fkt"),
        "number": await _next_faktur_no(order.get("entity_id")),
        "nsfp": (nsfp or "").strip(),
        "kode_transaksi": kode,
        "status": "pengganti",
        "replaces_id": original["id"], "replaced_by_id": None,
        "cancel_reason": "", "replace_reason": (reason or "").strip(),
        "faktur_date": now_iso(),
        "order_id": original["order_id"], "order_number": order.get("number", ""),
        "created_by": actor_name, "created_at": now_iso(), "updated_at": now_iso(),
        **_snapshot_from_order(order, entity, customer),
    }
    await db.tax_invoices.insert_one(dict(new_fkt))
    await db.tax_invoices.update_one(
        {"id": original["id"]},
        {"$set": {"replaced_by_id": new_fkt["id"], "updated_at": now_iso()}})
    from services import doc_refs_service as _refs
    await _refs.safe_link(("tax_invoice", new_fkt["id"]), ("sales_order", original["order_id"]),
                          "parent", note="faktur pengganti atas pesanan")
    await _refs.safe_link(("tax_invoice", new_fkt["id"]), ("tax_invoice", original["id"]),
                          "replaces", note=(reason or "faktur pengganti").strip())
    return safe_doc(new_fkt)


async def cancel_tax_invoice(fkt_id: str, reason: str, actor_name: str) -> Dict[str, Any]:
    fkt = safe_doc(await db.tax_invoices.find_one({"id": fkt_id}, {"_id": 0}))
    if not fkt:
        raise HTTPException(status_code=404, detail="Faktur Pajak tidak ditemukan")
    if fkt.get("status") == "batal":
        raise HTTPException(status_code=400, detail="Faktur Pajak sudah batal.")
    if not (reason or "").strip():
        raise HTTPException(status_code=400, detail="Alasan pembatalan wajib diisi.")
    await db.tax_invoices.update_one(
        {"id": fkt_id},
        {"$set": {"status": "batal", "cancel_reason": reason.strip(), "updated_at": now_iso()}})
    # bila faktur ini pengganti, lepas tanda replaced di originalnya agar bisa diterbitkan ulang
    if fkt.get("replaces_id"):
        await db.tax_invoices.update_one(
            {"id": fkt["replaces_id"]},
            {"$set": {"replaced_by_id": None, "updated_at": now_iso()}})
    return safe_doc(await db.tax_invoices.find_one({"id": fkt_id}, {"_id": 0}))


async def render_faktur_html(fkt_id: str) -> str:
    fkt = safe_doc(await db.tax_invoices.find_one({"id": fkt_id}, {"_id": 0}))
    if not fkt:
        raise HTTPException(status_code=404, detail="Faktur Pajak tidak ditemukan")
    rows = "".join(
        f"<tr><td style='text-align:center'>{i + 1}</td>"
        f"<td>{it.get('product_name', '')} <small style='color:#666'>({it.get('sku', '')})</small><br>"
        f"<small style='color:#666'>{it.get('quantity', 0)} {it.get('unit', '')} × {_money(it.get('price', 0))}</small></td>"
        f"<td style='text-align:right'>{_money(it.get('line_total', 0))}</td></tr>"
        for i, it in enumerate(fkt.get("items", []))
    ) or "<tr><td colspan='3'>-</td></tr>"
    status = fkt.get("status", "normal")
    banner = ""
    if status == "pengganti":
        banner = ("<div class='banner pengganti'><strong>FAKTUR PAJAK PENGGANTI</strong> — "
                  f"revisi atas faktur sebelumnya. {fkt.get('replace_reason', '')}</div>")
    elif status == "batal":
        banner = ("<div class='banner batal'><strong>FAKTUR PAJAK DIBATALKAN</strong> — "
                  f"{fkt.get('cancel_reason', '')}</div>")
    fd = (fkt.get("faktur_date", "") or "")[:10]
    npwp_note = "" if fkt.get("has_customer_npwp") else \
        "<p style='color:#B23B14;font-size:11px'>* NPWP pembeli belum diisi.</p>"
    html = f"""
    <html><head><title>Faktur Pajak {fkt.get('number', '')}</title>
    <style>
      @page {{size:A4 portrait;margin:14mm}} body{{font-family:Arial,sans-serif;color:#111;font-size:13px}}
      .head{{text-align:center;border-bottom:2px solid #111;padding-bottom:10px;margin-bottom:14px}}
      .head h1{{margin:0;font-size:20px;letter-spacing:1px}}
      .serial{{font-size:15px;font-weight:bold;margin-top:6px}}
      .meta{{display:flex;justify-content:space-between;margin:14px 0}}
      .box{{width:48%}} .box h3{{margin:0 0 4px;font-size:12px;color:#0058CC;text-transform:uppercase}}
      table{{width:100%;border-collapse:collapse;margin-top:8px}}
      td,th{{border:1px solid #ccc;padding:8px}} th{{background:#f3f3f3;text-align:left}}
      .totals{{margin-top:12px;width:55%;margin-left:45%}}
      .totals td{{border:none;padding:3px 8px}} .totals .grand{{font-weight:bold;font-size:15px;border-top:2px solid #111}}
      .banner{{padding:8px;margin:10px 0;border-radius:4px;font-size:12px}}
      .banner.pengganti{{background:#FFF3CD;border:1px solid #FFC107}}
      .banner.batal{{background:#FDE2E2;border:1px solid #E53935;color:#9B1C1C}}
      .sign{{margin-top:40px;text-align:right}} footer{{margin-top:28px;border-top:1px solid #ddd;padding-top:10px;color:#666;font-size:11px}}
    </style></head><body>
      <div class="head">
        <h1>FAKTUR PAJAK</h1>
        <div class="serial">Kode dan Nomor Seri Faktur Pajak: {format_nsfp_display(fkt)}</div>
        <div style="font-size:11px;color:#666">No. Internal: {fkt.get('number', '')} · Tanggal: {fd}</div>
      </div>
      {banner}
      <div class="meta">
        <div class="box"><h3>Pengusaha Kena Pajak (Penjual)</h3>
          <p><strong>{fkt.get('seller_name', '')}</strong><br>{fkt.get('seller_address', '')}<br>
          NPWP: {fkt.get('seller_npwp', '-')}</p></div>
        <div class="box"><h3>Pembeli Barang Kena Pajak</h3>
          <p><strong>{fkt.get('customer_name', '')}</strong><br>{fkt.get('customer_address', '')}<br>
          NPWP: {fkt.get('customer_npwp', '') or '-'}</p>{npwp_note}</div>
      </div>
      <table><thead><tr><th style="width:34px">No.</th><th>Nama Barang Kena Pajak / Jasa Kena Pajak</th>
        <th style="width:150px;text-align:right">Harga Jual</th></tr></thead>
        <tbody>{rows}</tbody></table>
      <table class="totals">
        <tr><td>Harga Jual (Bruto)</td><td style="text-align:right">{_money(fkt.get('total_amount', 0))}</td></tr>
        <tr><td>Dikurangi Potongan Harga</td><td style="text-align:right">{_money(fkt.get('discount_total', 0))}</td></tr>
        <tr><td>Dasar Pengenaan Pajak (DPP{' — Nilai Lain 11/12' if fkt.get('dpp_nilai_lain') else ''})</td><td style="text-align:right">{_money(fkt.get('dpp', 0))}</td></tr>
        <tr><td>PPN ({fkt.get('ppn_rate', 0)}%)</td><td style="text-align:right">{_money(fkt.get('ppn_amount', 0))}</td></tr>
        <tr class="grand"><td>Total</td><td style="text-align:right">{_money(fkt.get('grand_total', 0))}</td></tr>
      </table>
      <div class="sign"><p>{(fkt.get('seller_address', '').split(',')[-1] or '').strip()}, {fd}</p>
        <br/><br/><p><strong>_______________________</strong></p>
        <p style="font-size:11px">{fkt.get('seller_name', '')}</p></div>
      <footer>Dokumen Faktur Pajak dibuat oleh Kain Nusantara ERP. NSFP resmi diisi setelah alokasi dari DJP/Coretax (e-Faktur).</footer>
    </body></html>
    """
    return html
