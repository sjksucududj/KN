"""FINANCE — Analisis Profitabilitas / Margin (EPIC P0-2 · R5.6).

Margin REALISASI dari baris Sales Order (revenue = line_total) dikurangi COGS
berbasis **WAC** (Weighted Average Cost) per produk/entitas (costing_service).
Agregasi 5 dimensi sekaligus dalam 1 pass: produk, kategori, pelanggan, sales, **per-PT (entitas)**.
Plus tren bulanan (revenue/cogs/margin). Ter-scope per entitas via `scope`.

R5.6 — COGS dipecah menjadi **HPP Dasar** (`cogs_base`) + **Landed cost** (`cogs_landed`)
memakai pecahan WAC dari costing_service (wac_base / wac_landed). Total COGS = base + landed.
"""
from typing import Any, Dict, List, Optional, Tuple

from db import db
from core_utils import now_iso
from services.costing_service import wac_for_product

EPS = 0.005
# Status SO yang dianggap penjualan (revenue-recognized / dalam pemenuhan).
SOLD_STATUSES = ["confirmed", "reserved", "partially_shipped", "shipped", "done"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _pct(margin: float, revenue: float) -> Optional[float]:
    return round(margin / revenue * 100, 1) if revenue > EPS else None


def _bump(bucket: Dict[str, Dict[str, Any]], key: str, name: str,
          revenue: float, cogs_base: float, cogs_landed: float, qty: float) -> None:
    row = bucket.get(key)
    if not row:
        row = {"key": key, "name": name, "revenue": 0.0, "cogs_base": 0.0,
               "cogs_landed": 0.0, "qty": 0.0, "orders": set()}
        bucket[key] = row
    row["revenue"] += revenue
    row["cogs_base"] += cogs_base
    row["cogs_landed"] += cogs_landed
    row["qty"] += qty


def _finalize(bucket: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in bucket.values():
        rev = round(row["revenue"], 2)
        cb = round(row["cogs_base"], 2)
        cl = round(row["cogs_landed"], 2)
        cogs = round(cb + cl, 2)
        margin = round(rev - cogs, 2)
        out.append({
            "key": row["key"], "name": row["name"],
            "revenue": rev, "cogs_base": cb, "cogs_landed": cl, "cogs": cogs,
            "landed_included": cl > EPS,
            "margin": margin, "margin_pct": _pct(margin, rev),
            "qty": round(row["qty"], 2),
            "orders": len(row["orders"]),
        })
    out.sort(key=lambda r: r["margin"], reverse=True)
    return out


async def profitability(start: Optional[str] = None, end: Optional[str] = None,
                        scope: Optional[Dict[str, Any]] = None,
                        entity_id: Optional[str] = None) -> Dict[str, Any]:
    q: Dict[str, Any] = {"status": {"$in": SOLD_STATUSES}, **(scope or {})}
    date_f: Dict[str, str] = {}
    if start:
        date_f["$gte"] = start if "T" in start else f"{start}T00:00:00"
    if end:
        date_f["$lte"] = end if "T" in end else f"{end}T23:59:59.999999"
    if date_f:
        q["created_at"] = date_f

    orders = await db.sales_orders.find(q, {"_id": 0}).to_list(50000)

    # Peta customer -> assigned sales (atribusi bila SO tak simpan sales_name).
    cust_ids = list({o.get("customer_id") for o in orders if o.get("customer_id")})
    cmap: Dict[str, Dict[str, Any]] = {}
    if cust_ids:
        cust_rows = await db.customers.find(
            {"id": {"$in": cust_ids}}, {"_id": 0, "id": 1, "name": 1,
             "assigned_sales_id": 1, "assigned_sales_name": 1}).to_list(20000)
        cmap = {c["id"]: c for c in cust_rows}

    # Peta entitas (per-PT) -> nama.
    ent_ids = list({o.get("entity_id") or entity_id for o in orders if (o.get("entity_id") or entity_id)})
    emap: Dict[str, str] = {}
    if ent_ids:
        ent_rows = await db.business_entities.find(
            {"id": {"$in": ent_ids}}, {"_id": 0, "id": 1, "short_name": 1, "legal_name": 1}).to_list(200)
        emap = {e["id"]: (e.get("short_name") or e.get("legal_name") or e["id"]) for e in ent_rows}

    by_product: Dict[str, Dict[str, Any]] = {}
    by_category: Dict[str, Dict[str, Any]] = {}
    by_customer: Dict[str, Dict[str, Any]] = {}
    by_sales: Dict[str, Dict[str, Any]] = {}
    by_entity: Dict[str, Dict[str, Any]] = {}
    monthly: Dict[str, Dict[str, float]] = {}
    wac_cache: Dict[str, Tuple[float, float]] = {}   # ck -> (wac_base, wac_landed)
    tot_rev = tot_base = tot_landed = tot_qty = 0.0
    order_ids = set()

    for o in orders:
        oid = o.get("id")
        ent = o.get("entity_id") or entity_id
        ent_name = emap.get(ent or "", ent or "(Tanpa PT)")
        cid = o.get("customer_id") or ""
        cust = cmap.get(cid, {})
        cust_name = o.get("customer_name") or cust.get("name") or "(Tanpa Pelanggan)"
        sales_name = (o.get("sales_name") or cust.get("assigned_sales_name")
                      or "(Tanpa Sales)")
        sales_key = o.get("assigned_sales_id") or cust.get("assigned_sales_id") or sales_name
        created = str(o.get("created_at") or "")
        mkey = created[:7]  # YYYY-MM

        for it in o.get("items", []):
            pid = it.get("product_id") or ""
            qty = float(it.get("quantity", 0) or 0)
            revenue = float(it.get("line_total", it.get("subtotal", 0)) or 0)
            if qty <= 0 and revenue <= 0:
                continue
            ck = f"{pid}::{ent or ''}"
            if ck in wac_cache:
                wb, wl = wac_cache[ck]
            else:
                w = await wac_for_product(pid, entity_id=ent)
                wac = float(w.get("wac", 0) or 0)
                wb = float(w.get("wac_base", 0) or 0)
                wl = float(w.get("wac_landed", 0) or 0)
                if wac <= 0:
                    wb = float(it.get("unit_cost", 0) or 0)  # fallback snapshot roll
                    wl = 0.0
                elif wb <= 0 and wl <= 0:
                    wb = wac  # tak ada pecahan → semua dasar
                wac_cache[ck] = (wb, wl)
            cogs_base = round(wb * qty, 2)
            cogs_landed = round(wl * qty, 2)

            _bump(by_product, pid, it.get("product_name") or pid, revenue, cogs_base, cogs_landed, qty)
            by_product[pid]["orders"].add(oid)
            cat = it.get("category") or "(Tanpa Kategori)"
            _bump(by_category, cat, cat, revenue, cogs_base, cogs_landed, qty)
            by_category[cat]["orders"].add(oid)
            _bump(by_customer, cid or cust_name, cust_name, revenue, cogs_base, cogs_landed, qty)
            by_customer[cid or cust_name]["orders"].add(oid)
            _bump(by_sales, sales_key, sales_name, revenue, cogs_base, cogs_landed, qty)
            by_sales[sales_key]["orders"].add(oid)
            _bump(by_entity, ent or "(none)", ent_name, revenue, cogs_base, cogs_landed, qty)
            by_entity[ent or "(none)"]["orders"].add(oid)

            m = monthly.setdefault(mkey, {"revenue": 0.0, "cogs_base": 0.0, "cogs_landed": 0.0})
            m["revenue"] += revenue
            m["cogs_base"] += cogs_base
            m["cogs_landed"] += cogs_landed
            tot_rev += revenue
            tot_base += cogs_base
            tot_landed += cogs_landed
            tot_qty += qty
            order_ids.add(oid)

    trend = []
    for mk in sorted(monthly.keys()):
        rev = round(monthly[mk]["revenue"], 2)
        cb = round(monthly[mk]["cogs_base"], 2)
        cl = round(monthly[mk]["cogs_landed"], 2)
        cg = round(cb + cl, 2)
        mm = int(mk[5:7]) if len(mk) >= 7 and mk[5:7].isdigit() else 0
        trend.append({"month": mk, "label": f"{MONTHS[mm - 1]} {mk[:4]}" if mm else mk,
                      "revenue": rev, "cogs_base": cb, "cogs_landed": cl, "cogs": cg,
                      "margin": round(rev - cg, 2)})

    tot_rev = round(tot_rev, 2)
    tot_base = round(tot_base, 2)
    tot_landed = round(tot_landed, 2)
    tot_cogs = round(tot_base + tot_landed, 2)
    gross = round(tot_rev - tot_cogs, 2)
    return {
        "period": {"start": start or "", "end": end or ""},
        "totals": {
            "revenue": tot_rev, "cogs_base": tot_base, "cogs_landed": tot_landed,
            "cogs": tot_cogs, "landed_included": tot_landed > EPS,
            "margin": gross, "margin_pct": _pct(gross, tot_rev),
            "qty": round(tot_qty, 2), "orders": len(order_ids),
        },
        "by_product": _finalize(by_product),
        "by_category": _finalize(by_category),
        "by_customer": _finalize(by_customer),
        "by_sales": _finalize(by_sales),
        "by_entity": _finalize(by_entity),
        "monthly": trend,
        "cost_basis": "WAC (incl. landed cost)",
        "generated_at": now_iso(),
    }
