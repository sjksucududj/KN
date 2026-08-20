"""Outbound Picking router (extra): shipments list + Surat Jalan document generators.

Dipisah dari `routers/outbound_picking.py` agar file router di bawah batas guardrail.
Semua endpoint memakai prefix /api yang sama; tidak ada konflik path dengan router utama.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from db import db
from dependencies import require_permission
from entity_scope import entity_ctx, resolve_list_scope
from core_utils import safe_doc, rupiah

router = APIRouter(prefix="/api")


@router.get("/shipments")
async def list_shipments(request: Request, order_id: str = None) -> List[Dict[str, Any]]:
    """Daftar shipment (surat jalan) — Sub-fase 1.8."""
    await require_permission(request, "wms", "view")
    ctx = await entity_ctx(request)
    query = {}
    if order_id:
        query["order_id"] = order_id
    query = resolve_list_scope("shipments", query, ctx)
    shipments = await db.shipments.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return shipments


@router.get("/shipments/{shipment_id}/surat-jalan")
async def shipment_surat_jalan(shipment_id: str, request: Request):
    """Surat Jalan per-shipment (Sub-fase 1.8)."""
    from datetime import datetime, timezone
    from fastapi.responses import HTMLResponse
    await require_permission(request, "wms", "view")
    shp = safe_doc(await db.shipments.find_one({"id": shipment_id}, {"_id": 0}))
    if not shp:
        raise HTTPException(status_code=404, detail="Shipment tidak ditemukan")
    order = safe_doc(await db.sales_orders.find_one({"id": shp["order_id"]}, {"_id": 0})) or {}
    ship_addr = order.get("shipping_address", {}) or {}
    roll_rows = "".join(
        f"<tr><td>{r.get('roll_id','')}</td><td>{r.get('lot','-')}</td>"
        f"<td style='text-align:right'>{r.get('length',0)} {r.get('unit','')}</td></tr>"
        for r in shp.get("rolls", [])
    ) or "<tr><td colspan='3'>-</td></tr>"
    partial_banner = (
        f"<div class='split-info'><strong>Pengiriman Parsial:</strong> Surat jalan ini mengirim "
        f"<strong>{shp.get('qty',0)} {shp.get('unit','')}</strong> dari order {order.get('number','')}. "
        f"Sisa menyusul pada surat jalan berikutnya.</div>"
        if shp.get("is_partial") else ""
    )
    html = f"""
    <html><head><title>Surat Jalan {shp['shipment_no']}</title>
    <style>
      @page {{size:A4 portrait;margin:12mm}} body{{font-family:Arial,sans-serif;color:#111}}
      .header{{display:flex;justify-content:space-between;border-bottom:2px solid #111;padding-bottom:16px;margin-bottom:20px}}
      h1{{margin:0;font-size:24px}} h2{{margin:10px 0;font-size:18px}}
      table{{width:100%;border-collapse:collapse;margin-top:14px}}
      td,th{{border:1px solid #ddd;padding:9px;text-align:left}} th{{background:#f5f5f5}}
      .split-info{{background:#fff3cd;border:1px solid #ffc107;padding:10px;margin:14px 0;border-radius:5px}}
      .signature{{display:flex;justify-content:space-between;margin-top:60px;text-align:center}}
      footer{{margin-top:36px;border-top:1px solid #ddd;padding-top:12px;color:#555;font-size:12px}}
    </style></head><body>
      <div class="header">
        <div><h1>Kain Nusantara</h1><p style="color:#555">Enterprise Textile Warehouse</p></div>
        <div style="text-align:right"><h2>SURAT JALAN</h2>
          <p><strong>{shp['shipment_no']}</strong></p>
          <p>{datetime.now(timezone.utc).strftime('%d %b %Y')}</p>
          <p style="color:#555">Order: {order.get('number','')}</p></div>
      </div>
      {partial_banner}
      <div><h3>Informasi Pengiriman</h3>
        <p><strong>Customer:</strong> {order.get('customer_name','')}</p>
        <p><strong>Alamat:</strong> {ship_addr.get('address','')}, {ship_addr.get('city','')}</p>
        <p><strong>Penerima:</strong> {ship_addr.get('recipient_name','')} | {ship_addr.get('phone','')}</p>
        <p><strong>Gudang Pengirim:</strong> {shp.get('warehouse_name','')} ({shp.get('warehouse_city','')})</p>
      </div>
      <h3>Barang yang Dikirim — {shp.get('product_name','')} ({shp.get('sku','')})</h3>
      <p>Total: <strong>{shp.get('qty',0)} {shp.get('unit','')}</strong> dalam {len(shp.get('rolls',[]))} roll</p>
      <table><thead><tr><th>Roll ID</th><th>Lot</th><th>Panjang</th></tr></thead>
        <tbody>{roll_rows}</tbody></table>
      <div class="signature">
        <div><p>Dikirim Oleh</p><br/><br/><p><strong>_________________</strong></p><p>Warehouse Staff</p></div>
        <div><p>Diterima Oleh</p><br/><br/><p><strong>_________________</strong></p><p>Customer / Kurir</p></div>
      </div>
      <footer><p>Dokumen dibuat otomatis oleh Kain Nusantara WMS. Mohon cek kelengkapan saat penerimaan.</p></footer>
    </body></html>
    """
    return HTMLResponse(content=html)


@router.get("/outbound/so/{order_id}/surat-jalan")
async def generate_surat_jalan(order_id: str, request: Request, warehouse_id: str = None):
    """
    Generate Surat Jalan for dispatched outbound tasks.
    
    If warehouse_id specified, generate for that warehouse only.
    Otherwise, generate summary document showing all warehouses.
    """
    from datetime import datetime, timezone
    
    await require_permission(request, "wms", "view")
    
    order = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    if not order:
        raise HTTPException(status_code=404, detail="Sales Order tidak ditemukan")
    
    # Get dispatched / partially-shipped outbound tasks (Sub-fase 1.8)
    query = {
        "order_id": order_id,
        "flow_type": "outbound",
        "status": {"$in": ["dispatched", "partially_shipped"]}
    }
    if warehouse_id:
        query["warehouse_id"] = warehouse_id
    
    tasks = await db.wms_tasks.find(query, {"_id": 0}).to_list(100)
    
    if not tasks:
        raise HTTPException(status_code=400, detail="Belum ada barang yang dikirim untuk order ini")
    
    # Group by warehouse
    warehouses_data = {}
    for task in tasks:
        wh_id = task["warehouse_id"]
        if wh_id not in warehouses_data:
            warehouses_data[wh_id] = {
                "warehouse_name": task.get("warehouse_name", ""),
                "warehouse_city": task.get("warehouse_city", ""),
                "items": []
            }
        warehouses_data[wh_id]["items"].append(task)
    
    # If specific warehouse requested, show only that
    if warehouse_id and warehouse_id in warehouses_data:
        wh_data = warehouses_data[warehouse_id]
        items_rows = ""
        for task in wh_data["items"]:
            items_rows += f"""
            <tr>
                <td>{task.get('sku', '')}</td>
                <td>{task.get('product_name', '')}</td>
                <td>{task.get('quantity', 0.0)}</td>
                <td>{task.get('unit', '')}</td>
                <td>{task.get('batch', '-')}</td>
                <td>{task.get('lot', '-')}</td>
            </tr>
            """
        
        total_tasks = len(warehouses_data)
        task_number = list(warehouses_data.keys()).index(warehouse_id) + 1
        
        html = f"""
        <html>
        <head>
            <title>Surat Jalan - {order['number']}</title>
            <style>
                @page {{size: A4 portrait; margin: 12mm}}
                body {{font-family: Arial, sans-serif; padding: 0; color: #111}}
                .header {{display: flex; justify-content: space-between; border-bottom: 2px solid #111; padding-bottom: 16px; margin-bottom: 20px}}
                h1 {{margin: 0; font-size: 24px}}
                h2 {{margin: 10px 0; font-size: 18px}}
                table {{width: 100%; border-collapse: collapse; margin-top: 18px}}
                td, th {{border: 1px solid #ddd; padding: 10px; text-align: left}}
                th {{background: #f5f5f5; font-weight: bold}}
                .info-section {{margin: 20px 0}}
                .split-info {{background: #fff3cd; border: 1px solid #ffc107; padding: 10px; margin: 15px 0; border-radius: 5px}}
                .signature {{display: flex; justify-content: space-between; margin-top: 60px}}
                .signature div {{text-align: center}}
                footer {{margin-top: 40px; border-top: 1px solid #ddd; padding-top: 12px; color: #555; font-size: 12px}}
            </style>
        </head>
        <body>
            <div class="header">
                <div>
                    <h1>Kain Nusantara</h1>
                    <p style="color: #555; margin: 5px 0">Enterprise Textile Warehouse</p>
                </div>
                <div style="text-align: right">
                    <h2>SURAT JALAN</h2>
                    <p style="margin: 5px 0"><strong>{order['number']}</strong></p>
                    <p style="margin: 5px 0">{datetime.now(timezone.utc).strftime('%d %b %Y')}</p>
                </div>
            </div>
            
            <div class="split-info">
                <strong>⚠️ Pengiriman Split:</strong> Surat jalan ini adalah <strong>bagian {task_number} dari {total_tasks}</strong> pengiriman untuk order {order['number']}.
                Total keseluruhan order: {rupiah(order.get('total_amount', 0))}
            </div>
            
            <div class="info-section">
                <h3>Informasi Pengiriman</h3>
                <p><strong>Customer:</strong> {order.get('customer_name', '')}</p>
                <p><strong>Alamat Pengiriman:</strong> {order.get('shipping_address', {}).get('address', '')}, {order.get('shipping_address', {}).get('city', '')}</p>
                <p><strong>Penerima:</strong> {order.get('shipping_address', {}).get('recipient_name', '')}</p>
                <p><strong>Telepon:</strong> {order.get('shipping_address', {}).get('phone', '')}</p>
            </div>
            
            <div class="info-section">
                <h3>Gudang Pengirim</h3>
                <p><strong>{wh_data['warehouse_name']}</strong> ({wh_data['warehouse_city']})</p>
            </div>
            
            <h3>Barang yang Dikirim</h3>
            <table>
                <thead>
                    <tr>
                        <th>SKU</th>
                        <th>Nama Produk</th>
                        <th>Qty</th>
                        <th>Unit</th>
                        <th>Batch</th>
                        <th>Lot</th>
                    </tr>
                </thead>
                <tbody>
                    {items_rows}
                </tbody>
            </table>
            
            <div class="signature">
                <div>
                    <p>Dikirim Oleh</p>
                    <br/><br/>
                    <p><strong>_________________</strong></p>
                    <p>Warehouse Staff</p>
                </div>
                <div>
                    <p>Diterima Oleh</p>
                    <br/><br/>
                    <p><strong>_________________</strong></p>
                    <p>Customer / Kurir</p>
                </div>
            </div>
            
            <footer>
                <p>Dokumen ini dibuat secara otomatis oleh sistem Kain Nusantara WMS.</p>
                <p>Barang dikirim dalam kondisi baik. Mohon cek kelengkapan saat penerimaan.</p>
            </footer>
        </body>
        </html>
        """
    else:
        # Summary document for all warehouses
        warehouse_sections = ""
        for idx, (wh_id, wh_data) in enumerate(warehouses_data.items(), 1):
            items_list = "<ul>"
            for task in wh_data["items"]:
                items_list += f"<li>{task.get('sku', '')} - {task.get('product_name', '')} ({task.get('quantity', 0)} {task.get('unit', '')})</li>"
            items_list += "</ul>"
            
            warehouse_sections += f"""
            <div style="margin: 20px 0; border-left: 4px solid #007AFF; padding-left: 15px">
                <h4>Pengiriman {idx}: {wh_data['warehouse_name']} ({wh_data['warehouse_city']})</h4>
                {items_list}
            </div>
            """
        
        html = f"""
        <html>
        <head>
            <title>Summary Surat Jalan - {order['number']}</title>
            <style>
                @page {{size: A4 portrait; margin: 12mm}}
                body {{font-family: Arial, sans-serif; padding: 0; color: #111}}
                .header {{display: flex; justify-content: space-between; border-bottom: 2px solid #111; padding-bottom: 16px; margin-bottom: 20px}}
                h1 {{margin: 0; font-size: 24px}}
                h2 {{margin: 10px 0; font-size: 18px}}
                .info-section {{margin: 20px 0}}
                .split-info {{background: #fff3cd; border: 1px solid #ffc107; padding: 15px; margin: 20px 0; border-radius: 5px}}
                footer {{margin-top: 40px; border-top: 1px solid #ddd; padding-top: 12px; color: #555; font-size: 12px}}
            </style>
        </head>
        <body>
            <div class="header">
                <div>
                    <h1>Kain Nusantara</h1>
                    <p style="color: #555; margin: 5px 0">Enterprise Textile Warehouse</p>
                </div>
                <div style="text-align: right">
                    <h2>SUMMARY SURAT JALAN</h2>
                    <p style="margin: 5px 0"><strong>{order['number']}</strong></p>
                    <p style="margin: 5px 0">{datetime.now(timezone.utc).strftime('%d %b %Y')}</p>
                </div>
            </div>
            
            <div class="split-info">
                <h3>⚠️ Pengiriman Multi-Warehouse</h3>
                <p>Order ini dikirim dari <strong>{len(warehouses_data)} gudang berbeda</strong>.</p>
                <p>Total Order: <strong>{rupiah(order.get('total_amount', 0))}</strong></p>
            </div>
            
            <div class="info-section">
                <h3>Informasi Customer</h3>
                <p><strong>{order.get('customer_name', '')}</strong></p>
                <p>{order.get('shipping_address', {}).get('address', '')}, {order.get('shipping_address', {}).get('city', '')}</p>
                <p>Penerima: {order.get('shipping_address', {}).get('recipient_name', '')} | {order.get('shipping_address', {}).get('phone', '')}</p>
            </div>
            
            <h3>Detail Pengiriman Per Gudang</h3>
            {warehouse_sections}
            
            <footer>
                <p>Dokumen summary ini menjelaskan bahwa order {order['number']} di-split ke {len(warehouses_data)} surat jalan terpisah.</p>
                <p>Setiap gudang akan mencetak surat jalan individual dengan detail barang masing-masing.</p>
            </footer>
        </body>
        </html>
        """
    
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)
