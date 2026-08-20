"""Label Printer router: Generate ZPL/ESC-POS label commands."""
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from db import db
from dependencies import require_permission, audit
from core_utils import safe_doc
from services.label_printer_service import generate_label

router = APIRouter(prefix="/api")


class LabelGenerateRequest(BaseModel):
    product_id: str
    warehouse_id: str = ""
    format: str = "zpl"  # "zpl" or "escpos"
    qty: int = 1
    barcode_value: str = ""  # Optional custom barcode


@router.post("/labels/generate")
async def generate_product_label(payload: LabelGenerateRequest, request: Request) -> Dict[str, Any]:
    """
    Generate label command for a product.
    
    Requires permission: label.generate
    Returns ZPL or ESC/POS command string that can be copied or downloaded.
    """
    actor = await require_permission(request, "label", "generate")
    
    # Validate format
    if payload.format.lower() not in ["zpl", "escpos"]:
        raise HTTPException(status_code=400, detail="Format harus 'zpl' atau 'escpos'")
    
    # Validate qty
    if payload.qty < 1 or payload.qty > 100:
        raise HTTPException(status_code=400, detail="Qty harus antara 1-100")
    
    # Fetch product
    product = safe_doc(await db.products.find_one({"id": payload.product_id}, {"_id": 0}))
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    
    # Fetch warehouse (optional context)
    warehouse_name = ""
    if payload.warehouse_id:
        warehouse = safe_doc(await db.warehouses.find_one({"id": payload.warehouse_id}, {"_id": 0}))
        if warehouse:
            warehouse_name = f"{warehouse.get('name', '')} ({warehouse.get('code', '')})"
    
    # Generate label
    try:
        result = generate_label(
            format_type=payload.format,
            sku=product.get("sku", ""),
            product_name=product.get("name", ""),
            warehouse=warehouse_name,
            price=product.get("price", 0),
            barcode_value=payload.barcode_value or product.get("sku", ""),
            qty=payload.qty
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Audit log
    await audit(
        actor["name"],
        "label_generated",
        "product",
        payload.product_id,
        {
            "format": payload.format,
            "qty": payload.qty,
            "warehouse_id": payload.warehouse_id,
            "sku": product.get("sku", "")
        }
    )
    
    return result


@router.post("/labels/preview")
async def preview_label(
    payload: Dict[str, Any],
    request: Request
) -> Dict[str, Any]:
    """
    Generate label command with custom data (not tied to specific product).
    
    Useful for testing or custom label generation.
    Requires permission: label.generate
    
    Payload:
    {
        "format": "zpl" | "escpos",
        "sku": "string",
        "product_name": "string",
        "warehouse": "string (optional)",
        "price": float (optional),
        "barcode_value": "string (optional)",
        "qty": int (default 1)
    }
    """
    actor = await require_permission(request, "label", "generate")
    
    format_type = payload.get("format", "zpl")
    sku = payload.get("sku", "")
    product_name = payload.get("product_name", "")
    warehouse = payload.get("warehouse", "")
    price = float(payload.get("price", 0))
    barcode_value = payload.get("barcode_value", "")
    qty = int(payload.get("qty", 1))
    
    if not sku or not product_name:
        raise HTTPException(status_code=400, detail="SKU dan product_name wajib diisi")
    
    if format_type.lower() not in ["zpl", "escpos"]:
        raise HTTPException(status_code=400, detail="Format harus 'zpl' atau 'escpos'")
    
    if qty < 1 or qty > 100:
        raise HTTPException(status_code=400, detail="Qty harus antara 1-100")
    
    try:
        result = generate_label(
            format_type=format_type,
            sku=sku,
            product_name=product_name,
            warehouse=warehouse,
            price=price,
            barcode_value=barcode_value,
            qty=qty
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    await audit(
        actor["name"],
        "label_preview_generated",
        "label",
        "preview",
        {"format": format_type, "qty": qty, "sku": sku}
    )
    
    return result
