"""Stock Analytics service (Fase 5) — klasifikasi Fast/Slow/Dead + aging + kecepatan jual.

SSOT-safe & READ-ONLY: tidak mengubah stok. Sumber:
- inventory_balances (proyeksi on_hand, sudah di-rebuild dari rolls oleh roll_service)
- inventory_rolls    (umur/aging & nilai persediaan via base_unit_cost / WAC)
- inventory_movements(sinyal PENJUALAN = movement_type 'outbound_ship'; velocity & recency)

Semua entity-scoped via resolve_list_scope (owner_entity_id). Ambang batas CONFIGURABLE
(config_service.inventory.stock_analytics) — tidak ada hardcode.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db import db
from core_utils import safe_doc
from entity_scope import EntityContext, resolve_list_scope
from services.config_service import get_effective_settings
from services.roll_service import PHYSICAL_STATUS_TO_BUCKET

PHYSICAL_STATUSES = set(PHYSICAL_STATUS_TO_BUCKET.keys())

# Sinyal PENJUALAN (arus keluar ke pelanggan) untuk recency & velocity.
# Mencakup jalur live (roll_service.ship_order_rolls → 'outbound_ship') maupun
# data historis/seed ('outbound_dispatch'). Retur ('return_out') = balik masuk → diabaikan.
SALE_MOVEMENT_TYPES = {"outbound_ship", "outbound_dispatch"}

AGING_BUCKETS = [
    ("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90),
    ("91-180", 91, 180), (">180", 181, 10 ** 9),
]


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def _age_bucket(days: int) -> str:
    for name, lo, hi in AGING_BUCKETS:
        if lo <= days <= hi:
            return name
    return ">180"


def _classify(signal_days: Optional[int], fast_max: int, slow_max: int, never_sold: bool) -> str:
    """Fast/Slow/Dead berdasar hari sejak penjualan terakhir (atau umur stok bila belum pernah terjual)."""
    if signal_days is None:
        return "dead"
    if signal_days <= fast_max:
        cls = "fast"
    elif signal_days <= slow_max:
        cls = "slow"
    else:
        cls = "dead"
    # Belum pernah terjual tak boleh disebut "fast" walau stok masih baru.
    if never_sold and cls == "fast":
        cls = "slow"
    return cls


async def product_sales_velocity(
    ctx: EntityContext, entity_id: Optional[str] = None, window_days: int = 90,
) -> Dict[str, Dict[str, Any]]:
    """Kecepatan jual per PRODUK (lintas gudang) dari movement penjualan dalam jendela.
    Sumber tunggal definisi 'penjualan' (SALE_MOVEMENT_TYPES) — dipakai analytics & reorder/ROP.
    Return: {product_id: {sold, avg_daily, last_sale_days}}."""
    now = datetime.now(timezone.utc)
    window_start = now.timestamp() - window_days * 86400
    mv = await db.inventory_movements.find(
        resolve_list_scope("inventory_movements", {}, ctx, entity_id), {"_id": 0}
    ).to_list(100000)
    out: Dict[str, Dict[str, Any]] = {}
    for m in mv:
        if m.get("movement_type") not in SALE_MOVEMENT_TYPES:
            continue
        pid = m.get("product_id")
        dt = _parse_ts(m.get("timestamp"))
        d = out.setdefault(pid, {"sold": 0.0, "avg_daily": 0.0, "last_sale_days": None})
        if dt:
            days = (now - dt).days
            if d["last_sale_days"] is None or days < d["last_sale_days"]:
                d["last_sale_days"] = days
            if dt.timestamp() >= window_start:
                d["sold"] += abs(float(m.get("quantity", 0) or 0))
    for d in out.values():
        d["sold"] = round(d["sold"], 2)
        d["avg_daily"] = round(d["sold"] / window_days, 4) if window_days > 0 else 0.0
    return out



async def compute_stock_analytics(
    ctx: EntityContext,
    entity_id: Optional[str] = None,
    warehouse_id: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    settings = await get_effective_settings(entity_id if entity_id and entity_id != "all" else None)
    sa = (settings.get("inventory", {}) or {}).get("stock_analytics", {}) or {}
    fast_max = int(sa.get("fast_max_days", 30))
    slow_max = int(sa.get("slow_max_days", 90))
    window = int(sa.get("velocity_window_days", 90))
    window_start = now.timestamp() - window * 86400

    # ── Master maps ──────────────────────────────────────────────────────────
    warehouses = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(200)}
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(2000)}

    # ── Balances (on_hand > 0), entity-scoped ─────────────────────────────────
    bal_query: Dict[str, Any] = {"on_hand_qty": {"$gt": 0}}
    if warehouse_id:
        bal_query["warehouse_id"] = warehouse_id
    balances = await db.inventory_balances.find(
        resolve_list_scope("inventory_balances", bal_query, ctx, entity_id), {"_id": 0}
    ).to_list(5000)

    # ── Movements (recency & velocity by 'outbound_ship'), entity-scoped ──────
    mv_query: Dict[str, Any] = {}
    if warehouse_id:
        mv_query["warehouse_id"] = warehouse_id
    movements = await db.inventory_movements.find(
        resolve_list_scope("inventory_movements", mv_query, ctx, entity_id), {"_id": 0}
    ).to_list(50000)
    # seg key = (product, warehouse) → recency/velocity penjualan
    last_sale: Dict[tuple, datetime] = {}
    sold_window: Dict[tuple, float] = {}
    for m in movements:
        if m.get("movement_type") not in SALE_MOVEMENT_TYPES:
            continue
        key = (m.get("product_id"), m.get("warehouse_id"))
        dt = _parse_ts(m.get("timestamp"))
        if dt and (key not in last_sale or dt > last_sale[key]):
            last_sale[key] = dt
        if dt and dt.timestamp() >= window_start:
            sold_window[key] = sold_window.get(key, 0.0) + abs(float(m.get("quantity", 0) or 0))

    # ── Rolls (aging & nilai), entity-scoped ──────────────────────────────────
    roll_query: Dict[str, Any] = {"length_remaining": {"$gt": 0}}
    if warehouse_id:
        roll_query["warehouse_id"] = warehouse_id
    rolls = await db.inventory_rolls.find(
        resolve_list_scope("inventory_rolls", roll_query, ctx, entity_id), {"_id": 0}
    ).to_list(100000)
    # per (product, warehouse): nilai, umur roll tertua ; aging global per bucket
    seg_value: Dict[tuple, float] = {}
    seg_oldest_age: Dict[tuple, int] = {}
    aging: Dict[str, Dict[str, float]] = {name: {"qty": 0.0, "value": 0.0} for name, _, _ in AGING_BUCKETS}
    for r in rolls:
        if r.get("status") not in PHYSICAL_STATUSES:
            continue
        key = (r.get("product_id"), r.get("warehouse_id"))
        length = float(r.get("length_remaining", 0) or 0)
        cost = float(r.get("base_unit_cost", 0) or 0)
        value = length * cost
        seg_value[key] = seg_value.get(key, 0.0) + value
        dt = _parse_ts(r.get("created_at")) or _parse_ts((r.get("acquired") or {}).get("date"))
        age = (now - dt).days if dt else 9999
        if key not in seg_oldest_age or age > seg_oldest_age[key]:
            seg_oldest_age[key] = age
        b = _age_bucket(age)
        aging[b]["qty"] += length
        aging[b]["value"] += value

    # ── Agregasi per PRODUK (lintas gudang di scope) ──────────────────────────
    prod_rows: Dict[str, Dict[str, Any]] = {}
    for b in balances:
        pid = b.get("product_id")
        prod = products.get(pid, {})
        if category and prod.get("category") != category:
            continue
        wh = b.get("warehouse_id")
        key = (pid, wh)
        on_hand = float(b.get("on_hand_qty", 0) or 0)
        row = prod_rows.setdefault(pid, {
            "product_id": pid, "sku": prod.get("sku", ""), "product_name": prod.get("name", ""),
            "category": prod.get("category", ""), "unit": prod.get("base_unit", "meter"),
            "on_hand_qty": 0.0, "value": 0.0, "warehouses": set(),
            "_last_sale": None, "_oldest_age": 0, "sold_window": 0.0,
        })
        row["on_hand_qty"] += on_hand
        row["value"] += seg_value.get(key, 0.0)
        if wh in warehouses:
            row["warehouses"].add(warehouses[wh]["name"])
        row["sold_window"] += sold_window.get(key, 0.0)
        ls = last_sale.get(key)
        if ls and (row["_last_sale"] is None or ls > row["_last_sale"]):
            row["_last_sale"] = ls
        row["_oldest_age"] = max(row["_oldest_age"], seg_oldest_age.get(key, 0))

    rows: List[Dict[str, Any]] = []
    by_class = {c: {"count": 0, "qty": 0.0, "value": 0.0} for c in ("fast", "slow", "dead")}
    total_value = 0.0
    never_sold_count = 0
    for row in prod_rows.values():
        last_sale_dt = row.pop("_last_sale")
        oldest_age = row.pop("_oldest_age")
        never_sold = last_sale_dt is None
        days_since_sale = (now - last_sale_dt).days if last_sale_dt else None
        signal_days = days_since_sale if days_since_sale is not None else oldest_age
        cls = _classify(signal_days, fast_max, slow_max, never_sold)
        avg_daily = row["sold_window"] / window if window > 0 else 0.0
        days_of_supply = round(row["on_hand_qty"] / avg_daily, 1) if avg_daily > 0 else None
        row["warehouses"] = sorted(row["warehouses"])
        row["value"] = round(row["value"], 2)
        row["on_hand_qty"] = round(row["on_hand_qty"], 2)
        row["classification"] = cls
        row["never_sold"] = never_sold
        row["last_sale_date"] = last_sale_dt.isoformat() if last_sale_dt else None
        row["days_since_sale"] = days_since_sale
        row["oldest_age_days"] = oldest_age
        row["sold_qty_window"] = round(row.pop("sold_window"), 2)
        row["avg_daily_sold"] = round(avg_daily, 3)
        row["days_of_supply"] = days_of_supply
        rows.append(row)
        by_class[cls]["count"] += 1
        by_class[cls]["qty"] += row["on_hand_qty"]
        by_class[cls]["value"] += row["value"]
        total_value += row["value"]
        if never_sold:
            never_sold_count += 1

    for c in by_class:
        by_class[c]["qty"] = round(by_class[c]["qty"], 2)
        by_class[c]["value"] = round(by_class[c]["value"], 2)
    for b in aging.values():
        b["qty"] = round(b["qty"], 2)
        b["value"] = round(b["value"], 2)

    # urutkan: dead dulu (paling perlu perhatian), lalu nilai terbesar
    order = {"dead": 0, "slow": 1, "fast": 2}
    rows.sort(key=lambda r: (order.get(r["classification"], 3), -r["value"]))

    return {
        "generated_at": now.isoformat(),
        "thresholds": {"fast_max_days": fast_max, "slow_max_days": slow_max, "velocity_window_days": window},
        "filters": {"entity_id": entity_id or "all", "warehouse_id": warehouse_id, "category": category},
        "summary": {
            "sku_count": len(rows),
            "total_on_hand_value": round(total_value, 2),
            "by_class": by_class,
            "aging_buckets": [{"bucket": name, **aging[name]} for name, _, _ in AGING_BUCKETS],
            "dead_value": by_class["dead"]["value"],
            "dead_skus": by_class["dead"]["count"],
            "never_sold_skus": never_sold_count,
        },
        "rows": rows,
    }
