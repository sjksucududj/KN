"""
F-4b — POS advanced recommendations, dihitung dari histori `sales_orders` (TANPA AI, TANPA koleksi baru).
- best_sellers: produk terlaris (frekuensi order > volume > revenue).
- frequently_bought_together: produk yang sering muncul di order yang sama (market-basket).
- substitutes: alternatif in-stock saat produk habis (kategori sama, prioritas grade sama).
"""
from typing import Any, Dict, List, Optional

from db import db
from services.customer_service import DEAD_STATUSES
from services.inventory_service import product_summary


async def _live_orders(entity_id: Optional[str]) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    orders = await db.sales_orders.find(q, {"_id": 0, "items": 1, "status": 1, "id": 1}).to_list(8000)
    return [o for o in orders if o.get("status") not in DEAD_STATUSES]


async def _enrich(pid: str, extra: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    p = await db.products.find_one({"id": pid}, {"_id": 0})
    if not p:
        return None
    summ = await product_summary(pid)
    return {
        "product_id": pid,
        "sku": p.get("sku"),
        "product_name": p.get("name"),
        "category": p.get("category"),
        "color": p.get("color"),
        "grade": p.get("grade"),
        "image": p.get("image"),
        "price": float(p.get("price", 0) or 0),
        "base_unit": p.get("base_unit"),
        "available_qty": round(float(summ.get("available_qty", 0) or 0), 2),
        **extra,
    }


async def best_sellers(entity_id: Optional[str] = None, limit: int = 8) -> List[Dict[str, Any]]:
    orders = await _live_orders(entity_id)
    agg: Dict[str, Dict[str, float]] = {}
    for o in orders:
        counted = set()
        for it in (o.get("items") or []):
            pid = it.get("product_id")
            if not pid:
                continue
            a = agg.setdefault(pid, {"order_count": 0.0, "qty": 0.0, "revenue": 0.0})
            a["qty"] += float(it.get("base_quantity") or it.get("quantity") or 0)
            a["revenue"] += float(it.get("line_total") or it.get("subtotal") or 0)
            if pid not in counted:
                a["order_count"] += 1
                counted.add(pid)
    ranked = sorted(agg.items(), key=lambda kv: (kv[1]["order_count"], kv[1]["qty"], kv[1]["revenue"]), reverse=True)
    out: List[Dict[str, Any]] = []
    for pid, a in ranked:
        row = await _enrich(pid, {
            "order_count": int(a["order_count"]),
            "qty_sold": round(a["qty"], 2),
            "revenue": round(a["revenue"], 2),
        })
        if row:
            out.append(row)
        if len(out) >= limit:
            break
    return out


async def frequently_bought_together(product_id: str, entity_id: Optional[str] = None, limit: int = 6) -> List[Dict[str, Any]]:
    orders = await _live_orders(entity_id)
    co: Dict[str, int] = {}
    for o in orders:
        pids = [it.get("product_id") for it in (o.get("items") or []) if it.get("product_id")]
        if product_id not in pids:
            continue
        for pid in set(p for p in pids if p != product_id):
            co[pid] = co.get(pid, 0) + 1
    ranked = sorted(co.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    out: List[Dict[str, Any]] = []
    for pid, cnt in ranked:
        row = await _enrich(pid, {"together_count": cnt})
        if row:
            out.append(row)
    return out


async def substitutes(product_id: str, entity_id: Optional[str] = None, limit: int = 6) -> List[Dict[str, Any]]:
    """Alternatif in-stock saat produk OOS. Tiered: kategori sama > grade sama > populer.
    Selalu hanya mengembalikan produk yang masih ADA stok (available_qty > 0)."""
    base = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not base:
        return []
    cands = await db.products.find(
        {"id": {"$ne": product_id}, "status": {"$ne": "inactive"}}, {"_id": 0}
    ).to_list(300)
    scored = []
    for p in cands:
        summ = await product_summary(p["id"])
        avail = float(summ.get("available_qty", 0) or 0)
        if avail <= 0:
            continue
        same_cat = p.get("category") == base.get("category")
        same_grade = p.get("grade") == base.get("grade")
        reason = "kategori" if same_cat else ("grade" if same_grade else "populer")
        score = (2 if same_cat else 0) + (1 if same_grade else 0)
        scored.append((score, avail, same_cat, same_grade, reason, p))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    out: List[Dict[str, Any]] = []
    for score, avail, same_cat, same_grade, reason, p in scored[:limit]:
        row = await _enrich(p["id"], {"same_category": same_cat, "same_grade": same_grade, "match_reason": reason})
        if row:
            out.append(row)
    return out
