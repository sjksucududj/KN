"""Reporting router: Manager Dashboard KPIs.

F0-E — Multi-Entity: semua laporan ter-scope per entitas.
- `sales_orders` di-scope via `entity_id` (resolve_list_scope).
- `inventory_balances`/`inventory_movements` di-scope via `owner_entity_id`.
- `warehouses` SHARED (kapasitas fisik), tetapi stok per-entitas (balances ter-scope).
Param `entity_id`:
  - tidak diisi  → entitas AKTIF (header X-Entity-Id), atau semua-allowed bila view_all.
  - "all"        → semua entitas yang diizinkan (oversight admin/manager).
  - "<id>"       → entitas spesifik (harus ∈ allowed, else 403).
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request, Query
from db import db
from dependencies import require_permission
from core_utils import safe_doc
from entity_scope import entity_ctx, resolve_list_scope
from services import sales_ownership   # FASE E-8 (E8.4/US11) — "Pesanan Saya"

router = APIRouter(prefix="/api")


@router.get("/reports/stock-aging")
async def stock_aging(request: Request, days_threshold: int = 30,
                      entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Products with no inventory movement in last N days (per entitas pemilik stok)."""
    await require_permission(request, "product", "view")
    ctx = await entity_ctx(request)
    bal_scope = resolve_list_scope("inventory_balances", {"on_hand_qty": {"$gt": 0}}, ctx, entity_id)
    balances = await db.inventory_balances.find(bal_scope, {"_id": 0}).to_list(1000)
    warehouses = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(100)}
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(1000)}
    result = []
    for balance in balances:
        product = products.get(balance["product_id"], {})
        warehouse = warehouses.get(balance["warehouse_id"], {})
        mv_scope = resolve_list_scope(
            "inventory_movements",
            {"product_id": balance["product_id"], "warehouse_id": balance["warehouse_id"]},
            ctx, entity_id,
        )
        last_movement = safe_doc(
            await db.inventory_movements.find_one(mv_scope, {"_id": 0}, sort=[("timestamp", -1)])
        )
        last_movement_date = last_movement.get("timestamp") if last_movement else None
        days_since = None
        if last_movement_date:
            try:
                last_dt = datetime.fromisoformat(last_movement_date.replace("Z", "+00:00"))
                days_since = (datetime.now(timezone.utc) - last_dt).days
            except Exception:
                pass
        is_aging = days_since is None or days_since >= days_threshold
        if is_aging:
            result.append({
                "product_id": balance["product_id"],
                "product_name": product.get("name", "Unknown"),
                "sku": product.get("sku", ""),
                "category": product.get("category", ""),
                "warehouse_id": balance["warehouse_id"],
                "warehouse_name": warehouse.get("name", "Unknown"),
                "warehouse_city": warehouse.get("city", ""),
                "on_hand_qty": balance.get("on_hand_qty", 0),
                "available_qty": balance.get("available_qty", 0),
                "reserved_qty": balance.get("reserved_qty", 0),
                "last_movement_date": last_movement_date,
                "days_since_movement": days_since,
                "estimated_value": float(product.get("price", 0)) * float(balance.get("on_hand_qty", 0)),
            })
    return sorted(result, key=lambda x: (x.get("days_since_movement") or 9999), reverse=True)


@router.get("/reports/reservation-funnel")
async def reservation_funnel(request: Request,
                             entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Orders grouped by status with conversion rates (per entitas)."""
    await require_permission(request, "order", "view")
    ctx = await entity_ctx(request)
    match = resolve_list_scope("sales_orders", {}, ctx, entity_id)
    status_order = [
        "draft", "reserved", "waiting_approval", "approved", "confirmed",
        "partially_picked", "picked", "partially_shipped", "shipped", "done",
        "cancelled", "expired"
    ]
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$status", "count": {"$sum": 1}, "total_amount": {"$sum": "$total_amount"}}},
        {"$sort": {"_id": 1}}
    ]
    raw = await db.sales_orders.aggregate(pipeline).to_list(100)
    counts = {r["_id"]: {"count": r["count"], "total_amount": r.get("total_amount", 0)} for r in raw}
    total = sum(v["count"] for v in counts.values())
    active_total = sum(v["count"] for k, v in counts.items() if k not in ["cancelled", "expired"])
    funnel = []
    for status in status_order:
        if status in counts:
            funnel.append({
                "status": status,
                "count": counts[status]["count"],
                "percentage": round(counts[status]["count"] / total * 100, 1) if total > 0 else 0,
                "total_amount": round(counts[status].get("total_amount", 0), 0),
            })
    for status, data in counts.items():
        if status not in status_order:
            funnel.append({
                "status": status, "count": data["count"],
                "percentage": round(data["count"] / total * 100, 1) if total > 0 else 0,
                "total_amount": round(data.get("total_amount", 0), 0),
            })
    return {"funnel": funnel, "total_orders": total, "active_orders": active_total}


@router.get("/reports/order-velocity")
async def order_velocity(request: Request, days: int = 30,
                         entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Orders per day for last N days + totals (per entitas)."""
    await require_permission(request, "order", "view")
    ctx = await entity_ctx(request)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    scope = resolve_list_scope("sales_orders", {"created_at": {"$gte": cutoff}}, ctx, entity_id)
    orders = await db.sales_orders.find(scope, {"_id": 0}).to_list(10000)
    # Build full day range
    all_days: Dict[str, Dict[str, Any]] = {}
    for i in range(days):
        day = (datetime.now(timezone.utc) - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        all_days[day] = {"date": day, "count": 0, "total_amount": 0.0, "cancelled": 0, "done": 0}
    for order in orders:
        day = order.get("created_at", "")[:10]
        if day in all_days:
            all_days[day]["count"] += 1
            all_days[day]["total_amount"] += float(order.get("total_amount", 0))
            if order.get("status") == "cancelled":
                all_days[day]["cancelled"] += 1
            if order.get("status") == "done":
                all_days[day]["done"] += 1
    return {
        "velocity": list(all_days.values()),
        "total_orders": len(orders),
        "avg_per_day": round(len(orders) / days, 1) if days > 0 else 0,
        "total_revenue": round(sum(float(o.get("total_amount", 0)) for o in orders
                                   if o.get("status") not in ["cancelled", "expired"]), 0),
        "period_days": days,
    }


@router.get("/reports/top-customers")
async def top_customers(request: Request, limit: int = 10,
                        entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Top customers by revenue + order count (per entitas).

    FASE E-8 (E8.4 · US11) — ikut aturan kepemilikan: sales lapangan melihat pelanggan
    teratas **dari pesanannya sendiri**. Sebelumnya laporan ini membocorkan pelanggan
    & nilai belanja milik rekan satu PT, padahal daftar pesanannya sudah dibatasi —
    laporan adalah pintu belakang yang paling mudah terlupakan.
    """
    actor = await require_permission(request, "order", "view")
    ctx = await entity_ctx(request)
    match = resolve_list_scope(
        "sales_orders", {"status": {"$nin": ["cancelled", "expired", "draft"]}}, ctx, entity_id)
    match = sales_ownership.apply_scope(match, actor)
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$customer_id",
            "customer_name": {"$first": "$customer_name"},
            "order_count": {"$sum": 1},
            "total_revenue": {"$sum": "$total_amount"},
            "last_order_date": {"$max": "$created_at"}
        }},
        {"$sort": {"total_revenue": -1}},
        {"$limit": limit}
    ]
    result = await db.sales_orders.aggregate(pipeline).to_list(limit)
    return [
        {
            "customer_id": r["_id"],
            "customer_name": r["customer_name"],
            "order_count": r["order_count"],
            "total_revenue": round(r["total_revenue"], 0),
            "last_order_date": r.get("last_order_date"),
        }
        for r in result
    ]


@router.get("/reports/warehouse-utilization")
async def warehouse_utilization(request: Request,
                                entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Warehouse utilization: on_hand vs total capacity (stok per entitas pemilik)."""
    await require_permission(request, "warehouse", "view")
    ctx = await entity_ctx(request)
    warehouses = await db.warehouses.find({}, {"_id": 0}).to_list(100)
    result = []
    for warehouse in warehouses:
        total_capacity = 0.0
        for zone in warehouse.get("zones", []):
            for rack in zone.get("racks", []):
                for bin_ in rack.get("bins", []):
                    total_capacity += float(bin_.get("capacity", 0))
        bal_scope = resolve_list_scope(
            "inventory_balances", {"warehouse_id": warehouse["id"]}, ctx, entity_id)
        balances = await db.inventory_balances.find(bal_scope, {"_id": 0}).to_list(1000)
        on_hand_total = sum(float(b.get("on_hand_qty", 0)) for b in balances)
        reserved_total = sum(float(b.get("reserved_qty", 0)) for b in balances)
        available_total = sum(float(b.get("available_qty", 0)) for b in balances)
        # Product count
        product_ids = list({b["product_id"] for b in balances if float(b.get("on_hand_qty", 0)) > 0})
        products = await db.products.find(
            {"id": {"$in": product_ids}}, {"_id": 0, "id": 1, "name": 1, "sku": 1}
        ).to_list(100)
        utilization_pct = round(on_hand_total / total_capacity * 100, 1) if total_capacity > 0 else 0
        result.append({
            "warehouse_id": warehouse["id"],
            "warehouse_name": warehouse["name"],
            "warehouse_city": warehouse.get("city", ""),
            "total_capacity": total_capacity,
            "on_hand_qty": on_hand_total,
            "reserved_qty": reserved_total,
            "available_qty": available_total,
            "utilization_pct": utilization_pct,
            "product_count": len(product_ids),
            "products": products[:5],
            "lat": warehouse.get("lat"),
            "lng": warehouse.get("lng"),
        })
    return sorted(result, key=lambda x: x["utilization_pct"], reverse=True)


@router.get("/reports/summary")
async def dashboard_summary(request: Request,
                            entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Executive summary for manager dashboard (per entitas)."""
    await require_permission(request, "order", "view")
    ctx = await entity_ctx(request)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    so_base = resolve_list_scope("sales_orders", {}, ctx, entity_id)
    # Today's orders
    orders_today = await db.sales_orders.count_documents({**so_base, "created_at": {"$gte": today}})
    # This month's revenue
    pipeline_rev = [
        {"$match": {**so_base, "created_at": {"$gte": month_ago}, "status": {"$nin": ["cancelled", "expired"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
    ]
    rev_result = await db.sales_orders.aggregate(pipeline_rev).to_list(1)
    monthly_revenue = rev_result[0]["total"] if rev_result else 0
    # Pending approvals
    pending_approvals = await db.sales_orders.count_documents({**so_base, "status": "waiting_approval"})
    # Low stock (available < 100) — per entitas pemilik
    inv_base = resolve_list_scope("inventory_balances", {}, ctx, entity_id)
    low_stock = await db.inventory_balances.count_documents({**inv_base, "available_qty": {"$lt": 100, "$gt": 0}})
    # Cycle count pending (operasional gudang — global; tidak entity-scoped di codebase ini)
    pending_cc = await db.cycle_count_sessions.count_documents({"status": "submitted"})
    return {
        "orders_today": orders_today,
        "monthly_revenue": round(monthly_revenue, 0),
        "pending_approvals": pending_approvals,
        "low_stock_items": low_stock,
        "pending_cycle_counts": pending_cc,
    }
