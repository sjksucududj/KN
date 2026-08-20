"""Costing service (EPIC3A) — Weighted Average Cost (WAC) per produk/entitas.

SSOT cost = `inventory_rolls.unit_cost` (sudah termasuk landed cost via
landed_cost_service; lihat `base_unit_cost` + Σ landed). WAC = rata-rata
tertimbang cost-per-unit dengan bobot `length_remaining` (stok hidup).

Prioritas sumber cost (margin-aware EPIC4):
  1. Roll cost (unit_cost / base_unit_cost) tertimbang length_remaining.
  2. Fallback `products.harga_pokok` (HPP manual) bila tak ada roll bercost.
  3. 0 (ditandai source="none") → line tanpa cost (EPIC4 boleh skip margin cap).
"""
from typing import Any, Dict, List, Optional
import time

from db import db

# Status roll yang dihitung sebagai "stok hidup" untuk WAC.
LIVE_ROLL_STATUSES = {"available", "reserved", "committed", "picked", "packed", "quarantine"}

# P2-4 — cache WAC ber-TTL pendek. WAC bergantung pada inventory_rolls (berubah
# saat GR/fulfillment), BUKAN pada pembayaran AR → aman di-cache singkat untuk
# memangkas recompute berulang (admin_home N×komisi, sales_home 6×history).
_WAC_TTL = 5.0
_WAC_CACHE: Dict[tuple, tuple] = {}  # (product_id, entity_id) -> (expires_at, result)


def invalidate_wac_cache() -> None:
    """Kosongkan cache WAC (panggil setelah perubahan cost/roll bila perlu real-time)."""
    _WAC_CACHE.clear()


def _roll_cost(r: Dict[str, Any]) -> float:
    uc = r.get("unit_cost")
    if uc not in (None, 0, 0.0):
        return float(uc)
    b = r.get("base_unit_cost")
    if b not in (None, 0, 0.0):
        return float(b)
    return 0.0


async def wac_for_product(
    product_id: str,
    entity_id: Optional[str] = None,
    product: Optional[Dict[str, Any]] = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Hitung WAC 1 produk. entity_id opsional → cost per kepemilikan entitas."""
    cache_key = (product_id, entity_id or "")
    if use_cache:
        hit = _WAC_CACHE.get(cache_key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
    if product is None:
        product = await db.products.find_one({"id": product_id}, {"_id": 0}) or {}
    query: Dict[str, Any] = {"product_id": product_id, "status": {"$in": list(LIVE_ROLL_STATUSES)}}
    if entity_id:
        query["owner_entity_id"] = entity_id
    rolls = await db.inventory_rolls.find(query, {"_id": 0}).to_list(5000)

    total_len = 0.0
    total_val = 0.0
    base_val = 0.0      # R5.5 — Σ(base_unit_cost×len) untuk memisah komponen landed cost
    costed_len = 0.0
    for r in rolls:
        ln = float(r.get("length_remaining", 0) or 0)
        if ln <= 0:
            continue
        total_len += ln
        cost = _roll_cost(r)
        if cost > 0:
            costed_len += ln
            total_val += cost * ln
            # base_unit_cost = HPP sebelum landed; bila kosong anggap = cost (landed 0).
            b = float(r.get("base_unit_cost") or 0) or cost
            base_val += b * ln

    price = float(product.get("price", 0) or 0)
    hpp_manual = float(product.get("harga_pokok", 0) or 0)

    if costed_len > 0:
        wac = total_val / costed_len
        source = "roll" if costed_len >= total_len - 0.001 else "roll_partial"
    elif hpp_manual > 0:
        wac = hpp_manual
        source = "harga_pokok"
    else:
        wac = 0.0
        source = "none"

    # R5.5 — pisahkan WAC menjadi base + landed cost (basis valuasi retur/regrade/write-off).
    if costed_len > 0:
        wac_base = round(base_val / costed_len, 2)
        wac_landed = round(max(wac - wac_base, 0.0), 2)
    else:
        wac_base = round(wac, 2)
        wac_landed = 0.0
    landed_included = wac_landed > 0.005

    margin_amount = round(price - wac, 2) if wac > 0 else None
    margin_pct = round((margin_amount / price) * 100, 2) if (wac > 0 and price > 0) else None

    result = {
        "product_id": product_id,
        "sku": product.get("sku", ""),
        "name": product.get("name", ""),
        "category": product.get("category", ""),
        "base_unit": product.get("base_unit", "meter"),
        "entity_id": entity_id,
        "wac": round(wac, 2),
        "wac_base": wac_base,          # R5.5 — HPP dasar (sebelum landed cost)
        "wac_landed": wac_landed,      # R5.5 — komponen landed cost (freight/duty/handling)
        "landed_included": landed_included,  # R5.5 — true bila WAC mengandung landed cost
        "source": source,
        "qty_on_hand": round(total_len, 2),
        "qty_costed": round(costed_len, 2),
        "price": round(price, 2),
        "margin_amount": margin_amount,
        "margin_pct": margin_pct,
    }
    if use_cache:
        _WAC_CACHE[cache_key] = (time.monotonic() + _WAC_TTL, result)
    return result


async def wac_all(entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """WAC seluruh produk aktif (untuk tabel margin / laporan)."""
    products = await db.products.find({"status": "active"}, {"_id": 0}).to_list(2000)
    out = []
    for p in products:
        out.append(await wac_for_product(p["id"], entity_id=entity_id, product=p))
    out.sort(key=lambda x: x["name"])
    return out
