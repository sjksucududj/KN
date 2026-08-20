"""Label printer service: Generate ZPL and ESC/POS commands for barcode labels."""
from typing import Dict, Any
from core_utils import rupiah


def _escape_zpl(text: str, max_len: int = 50) -> str:
    """Escape and truncate text for ZPL commands."""
    safe = text.replace("^", "").replace("~", "")[:max_len]
    return safe


def _escape_escpos(text: str, max_len: int = 50) -> str:
    """Escape and truncate text for ESC/POS commands."""
    safe = text.encode('ascii', 'ignore').decode('ascii')[:max_len]
    return safe


def generate_zpl_label(
    sku: str,
    product_name: str,
    warehouse: str = "",
    price: float = 0,
    barcode_value: str = "",
    width_dots: int = 406,  # 4 inch @ 203 DPI
    height_dots: int = 203  # 2 inch @ 203 DPI
) -> str:
    """
    Generate ZPL command for a 4x2 inch label (203 DPI).
    
    Layout:
    - Barcode (Code 128) centered, top section
    - SKU below barcode
    - Product name (max 2 lines, truncated)
    - Warehouse location
    - Price (optional, if > 0)
    """
    if not barcode_value:
        barcode_value = sku
    
    # Escape values
    sku_safe = _escape_zpl(sku, 30)
    name_safe = _escape_zpl(product_name, 45)
    warehouse_safe = _escape_zpl(warehouse, 25)
    
    # Split product name into 2 lines if long
    name_line1 = name_safe[:22]
    name_line2 = name_safe[22:44] if len(name_safe) > 22 else ""
    
    zpl_lines = [
        "^XA",  # Start format
        "^CF0,30",  # Default font, height 30
        "^FO50,20^BY2,3,80^BCN,80,Y,N,N",  # Barcode: Code128, height 80 dots, centered-ish
        f"^FD{barcode_value}^FS",
        "^CF0,20",  # Font for SKU
        f"^FO50,110^FDSKU: {sku_safe}^FS",
        "^CF0,18",  # Font for name
        f"^FO50,135^FD{name_line1}^FS",
    ]
    
    if name_line2:
        zpl_lines.append(f"^FO50,155^FD{name_line2}^FS")
        next_y = 175
    else:
        next_y = 155
    
    if warehouse_safe:
        zpl_lines.append(f"^CF0,16^FO50,{next_y}^FDLokasi: {warehouse_safe}^FS")
        next_y += 20
    
    if price > 0:
        price_str = f"{rupiah(price)}"
        zpl_lines.append(f"^CF0,16^FO50,{next_y}^FDHarga: {price_str}^FS")
    
    zpl_lines.append("^XZ")  # End format
    
    return "\n".join(zpl_lines)


def generate_escpos_label(
    sku: str,
    product_name: str,
    warehouse: str = "",
    price: float = 0,
    barcode_value: str = ""
) -> str:
    """
    Generate ESC/POS command for a simple label.
    
    Uses standard ESC/POS commands for text and Code 128 barcode.
    Note: Command format may vary by printer model; this is a generic template.
    """
    if not barcode_value:
        barcode_value = sku
    
    sku_safe = _escape_escpos(sku, 30)
    name_safe = _escape_escpos(product_name, 40)
    warehouse_safe = _escape_escpos(warehouse, 25)
    
    # ESC/POS commands (hex notation in comments):
    ESC = chr(27)
    GS = chr(29)
    
    lines = [
        f"{ESC}@",  # Initialize printer
        f"{ESC}a\x01",  # Center alignment
        f"{ESC}!\x10",  # Double height
        "KAIN NUSANTARA",
        f"{ESC}!\x00",  # Normal text
        "\n",
        # Barcode (Code 128)
        f"{GS}h\x50",  # Barcode height = 80 dots
        f"{GS}w\x02",  # Barcode width = 2
        f"{GS}H\x02",  # HRI below barcode
        f"{GS}k\x49{chr(len(barcode_value))}{barcode_value}",  # Code 128 barcode
        "\n\n",
        f"{ESC}a\x00",  # Left alignment
        f"{ESC}!\x01",  # Bold
        f"SKU: {sku_safe}",
        f"{ESC}!\x00",
        "\n",
        f"{name_safe[:32]}",
        "\n",
    ]
    
    if len(name_safe) > 32:
        lines.append(f"{name_safe[32:64]}\n")
    
    if warehouse_safe:
        lines.append(f"Lokasi: {warehouse_safe}\n")
    
    if price > 0:
        price_str = f"{rupiah(price)}"
        lines.append(f"Harga: {price_str}\n")
    
    lines.extend([
        "\n",
        f"{ESC}d\x03",  # Feed 3 lines
        f"{GS}V\x00",  # Cut paper (full cut)
    ])
    
    return "".join(lines)


def generate_label(
    format_type: str,
    sku: str,
    product_name: str,
    warehouse: str = "",
    price: float = 0,
    barcode_value: str = "",
    qty: int = 1
) -> Dict[str, Any]:
    """
    Generate label command(s) based on format type.
    
    Args:
        format_type: "zpl" or "escpos"
        sku: Product SKU
        product_name: Product name
        warehouse: Warehouse name/code
        price: Product price
        barcode_value: Custom barcode value (default: use SKU)
        qty: Number of labels to generate
    
    Returns:
        dict with keys: format, content, meta
    """
    if format_type.lower() == "zpl":
        single_label = generate_zpl_label(sku, product_name, warehouse, price, barcode_value)
    elif format_type.lower() == "escpos":
        single_label = generate_escpos_label(sku, product_name, warehouse, price, barcode_value)
    else:
        raise ValueError(f"Unsupported format: {format_type}. Use 'zpl' or 'escpos'.")
    
    # If qty > 1, repeat the label command
    if qty > 1 and format_type.lower() == "zpl":
        # ZPL: use ^PQ command for quantity
        content = single_label.replace("^XZ", f"^PQ{qty},0,1,Y^XZ")
    elif qty > 1 and format_type.lower() == "escpos":
        # ESC/POS: repeat the command
        content = "\n\n".join([single_label for _ in range(qty)])
    else:
        content = single_label
    
    return {
        "format": format_type.lower(),
        "content": content,
        "meta": {
            "sku": sku,
            "product_name": product_name,
            "warehouse": warehouse,
            "price": price,
            "barcode_value": barcode_value or sku,
            "qty": qty,
            "label_size": "4x2 inch (102x51mm)",
            "barcode_type": "Code 128"
        }
    }
