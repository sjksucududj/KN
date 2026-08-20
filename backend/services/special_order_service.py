"""Special Order Service - Sub-fase 1.12

Handles business logic for Special Orders (custom products not in catalog).
Simple approval: amount > threshold requires manager approval.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List
from db import db
from core_utils import new_id, now_iso, safe_doc, parse_decimal
import domain_registry as _dr        # Fase A · R7 — SSOT domain (stamp defaults)

# Gambar default produk custom (sama dengan default ProductPayload)
_DEFAULT_PRODUCT_IMAGE = (
    "https://images.unsplash.com/photo-1774679817333-decf0d988dd5"
    "?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85"
)

# Simple approval threshold (IDR)
APPROVAL_THRESHOLD = 10_000_000

# Status constants (aligned with SO)
STATUS_DRAFT = "draft"
STATUS_PENDING_APPROVAL = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_CONFIRMED = "confirmed"
STATUS_IN_PRODUCTION = "in_production"
STATUS_READY = "ready"
STATUS_SHIPPED = "shipped"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"


async def generate_special_order_number() -> str:
    """Generate unique Special Order number: SORD-YYMMDD-XXXX"""
    today = datetime.now(timezone.utc).strftime("%y%m%d")
    prefix = f"SORD-{today}"
    
    # Get highest sequence for today
    latest = await db.special_orders.find_one(
        {"number": {"$regex": f"^{prefix}"}},
        sort=[("number", -1)]
    )
    
    if latest:
        last_num = int(latest["number"].split("-")[-1])
        seq = last_num + 1
    else:
        seq = 1
    
    return f"{prefix}-{seq:04d}"


async def evaluate_special_order_approval(total_amount: float, current_status: str) -> str:
    """Determine initial status based on amount.
    
    Returns:
        - 'draft' if amount <= threshold
        - 'pending_approval' if amount > threshold
    """
    if current_status != STATUS_DRAFT:
        return current_status
    
    if total_amount > APPROVAL_THRESHOLD:
        return STATUS_PENDING_APPROVAL
    
    return STATUS_DRAFT


async def can_approve_special_order(special_order: Dict[str, Any], user_role: str) -> bool:
    """Check if user can approve special order.
    
    Args:
        special_order: Special order document
        user_role: Current user's role
    
    Returns:
        True if user can approve (manager/admin)
    """
    if special_order["status"] != STATUS_PENDING_APPROVAL:
        return False
    
    return user_role in ["manager", "admin"]


async def approve_special_order(special_order_id: str, approved_by: str) -> Dict[str, Any]:
    """Approve special order and transition to confirmed status.
    
    Args:
        special_order_id: Special order ID
        approved_by: User email who approved
    
    Returns:
        Updated special order document
    """
    result = await db.special_orders.find_one_and_update(
        {"id": special_order_id, "status": STATUS_PENDING_APPROVAL},
        {
            "$set": {
                "status": STATUS_CONFIRMED,
                "approved_by": approved_by,
                "approved_at": now_iso(),
                "updated_at": now_iso()
            }
        },
        return_document=True
    )
    
    if not result:
        raise ValueError("Special order not found or not in pending_approval status")
    
    result.pop("_id", None)
    # F3 (2.a) — auto-create Product SKU saat approve (best-effort, idempotent).
    # Kegagalan pembuatan SKU TIDAK boleh menggagalkan approval (status sudah confirmed).
    try:
        await create_sku_from_special_order(special_order_id, created_by=approved_by)
    except Exception:  # noqa: BLE001 — SKU best-effort; manual fallback tersedia via endpoint
        pass
    # Re-fetch agar field linkage (linked_product_id/sku) ikut terkirim ke FE.
    refreshed = await db.special_orders.find_one({"id": special_order_id}, {"_id": 0})
    return refreshed or result


async def reject_special_order(special_order_id: str, rejected_by: str, reason: str) -> Dict[str, Any]:
    """Reject special order.
    
    Args:
        special_order_id: Special order ID
        rejected_by: User email who rejected
        reason: Rejection reason
    
    Returns:
        Updated special order document
    """
    result = await db.special_orders.find_one_and_update(
        {"id": special_order_id, "status": STATUS_PENDING_APPROVAL},
        {
            "$set": {
                "status": STATUS_CANCELLED,
                "rejected_by": rejected_by,
                "rejected_at": now_iso(),
                "reject_reason": reason,
                "updated_at": now_iso()
            }
        },
        return_document=True
    )
    
    if not result:
        raise ValueError("Special order not found or not in pending_approval status")
    
    result.pop("_id", None)
    return result


async def _generate_custom_sku(base: str) -> str:
    """Hasilkan SKU unik untuk produk custom MTO. `base` mis. nomor SORD.
    Tambah suffix angka bila bentrok dengan produk yang sudah ada."""
    candidate = base
    suffix = 0
    while await db.products.find_one({"sku": candidate}, {"_id": 0, "id": 1}):
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


async def create_sku_from_special_order(special_order_id: str,
                                        created_by: str = "system") -> Dict[str, Any]:
    """F3 (2.a) — Materialisasi Product SKU dari Special Order MTO (idempotent).

    Dipanggil otomatis saat approve (status → confirmed) dan dapat dipicu manual.
    Bila special order sudah punya `linked_product_id`, kembalikan produk existing.
    """
    so = await db.special_orders.find_one({"id": special_order_id}, {"_id": 0})
    if not so:
        raise ValueError("Special order tidak ditemukan")

    # Idempotent — sudah pernah dibuat SKU-nya.
    if so.get("linked_product_id"):
        existing = await db.products.find_one({"id": so["linked_product_id"]}, {"_id": 0})
        if existing:
            return safe_doc(existing)

    # Hanya boleh setelah disetujui (confirmed) atau tahap setelahnya.
    if so.get("status") not in (STATUS_CONFIRMED, STATUS_IN_PRODUCTION,
                                STATUS_READY, STATUS_SHIPPED, STATUS_DONE):
        raise ValueError(
            "SKU hanya dapat dibuat untuk special order yang sudah disetujui (confirmed).")

    ci = so.get("custom_item", {}) or {}
    specs = ci.get("specifications", {}) or {}

    def _spec(*keys, default=""):
        """Ambil nilai spesifikasi case-insensitive (mis. 'color'/'Warna')."""
        for k in keys:
            for variant in (k, k.lower(), k.capitalize(), k.upper()):
                val = specs.get(variant)
                if val not in (None, ""):
                    return str(val)
        return default

    number = so.get("number", "") or ""
    sku_base = f"MTO-{number.replace('SORD-', '')}" if number else f"MTO-{new_id('x')[-8:]}"
    sku = await _generate_custom_sku(sku_base)

    # Fase A · PS-02/PS-03 — SKU custom WAJIB tetap membawa field domain tekstil.
    # Nilai diambil dari spesifikasi special order bila ada; TIDAK dikarang bila
    # tidak ada (produk ditandai needs_review + domain_gaps agar dilengkapi user).
    def _spec_num(*keys) -> float:
        try:
            return parse_decimal(_spec(*keys, default="") or 0)
        except ValueError:
            return 0.0

    product = {
        "id": new_id("prod"),
        "sku": sku,
        "name": ci.get("description") or f"Custom {number}".strip(),
        "category": _spec("category", "kategori", default="Custom"),
        "variant": _spec("variant", "varian", default="Custom"),
        "color": _spec("color", "warna", default="Natural"),
        "motif": _spec("motif", default="Polos"),
        "grade": _spec("grade", default="A"),
        "supplier": _spec("supplier", default="Internal"),
        "base_unit": ci.get("unit") or "meter",
        "price": float(ci.get("target_price", 0) or 0),
        "harga_pokok": 0.0,
        "gramasi": _spec_num("gramasi", "gsm"),
        "lebar": _spec_num("lebar", "width"),
        "stage": _spec("stage", "tahap", default=""),
        "fabric_type": _spec("fabric_type", "jenis_kain", "jeniskain", default=""),
        "yarn_count": _spec("yarn_count", "nomor_benang", default=""),
        "kg_per_meter": 0.0,
        "reorder_point": 0.0,
        "reorder_qty": 0.0,
        "image": _DEFAULT_PRODUCT_IMAGE,
        "status": "active",
        "uom_conversions": [],
        "template_id": "",
        "variant_attrs": specs if isinstance(specs, dict) else {},
        "batch_lot_rolls": [],
        # F3 — metadata MTO (jejak asal special order)
        "is_custom": True,
        "source_special_order_id": so["id"],
        "source_special_order_number": number,
        "entity_id": so.get("entity_id", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    _dr.stamp_domain_defaults(product, source="special_order")
    await db.products.insert_one(product)

    await db.special_orders.update_one(
        {"id": special_order_id},
        {"$set": {
            "linked_product_id": product["id"],
            "linked_product_sku": sku,
            "linked_product_name": product["name"],
            "sku_created_at": now_iso(),
            "sku_created_by": created_by,
            "updated_at": now_iso(),
        }})
    return safe_doc(product)


async def transition_special_order_status(
    special_order_id: str,
    new_status: str,
    updated_by: str
) -> Dict[str, Any]:
    """Transition special order to new status.
    
    Valid transitions:
    - confirmed → in_production (purchasing started)
    - in_production → ready (item produced/received)
    - ready → shipped (dispatched to customer)
    - shipped → done (delivered)
    
    Args:
        special_order_id: Special order ID
        new_status: Target status
        updated_by: User email
    
    Returns:
        Updated special order document
    """
    VALID_TRANSITIONS = {
        STATUS_CONFIRMED: [STATUS_IN_PRODUCTION],
        STATUS_IN_PRODUCTION: [STATUS_READY],
        STATUS_READY: [STATUS_SHIPPED],
        STATUS_SHIPPED: [STATUS_DONE],
    }
    
    special_order = await db.special_orders.find_one({"id": special_order_id})
    if not special_order:
        raise ValueError("Special order not found")
    
    current_status = special_order["status"]
    
    if new_status not in VALID_TRANSITIONS.get(current_status, []):
        raise ValueError(
            f"Invalid status transition: {current_status} → {new_status}"
        )
    
    result = await db.special_orders.find_one_and_update(
        {"id": special_order_id},
        {
            "$set": {
                "status": new_status,
                "updated_at": now_iso(),
                "updated_by": updated_by
            },
            "$push": {
                "status_history": {
                    "status": new_status,
                    "timestamp": now_iso(),
                    "user": updated_by
                }
            }
        },
        return_document=True
    )
    
    result.pop("_id", None)
    return result
