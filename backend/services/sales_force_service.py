"""Sales Force service (KN_17 §6) — KPI per salesperson + komisi (pencairan + tiered).

Semua KPI DERIVED dari sales_orders/payments/customers. Komisi default basis PENCAIRAN
(tertagih) + TIERED capaian target (S36).
"""
from typing import Any, Dict, List, Optional
from db import db
from core_utils import safe_doc
from services.customer_service import (
    compute_customer_credit, _order_grand_total, _order_paid, DEAD_STATUSES,
)
from services import costing_service
from services.config_service import get_effective_settings

DEFAULT_TIERS = [
    {"min_achievement": 0, "rate": 1.0},
    {"min_achievement": 80, "rate": 1.5},
    {"min_achievement": 100, "rate": 2.5},
    {"min_achievement": 120, "rate": 3.5},
]


def _in_period(value: Any, period: Optional[str]) -> bool:
    """Cocokkan created_at dengan periode: YYYY-MM (bulan), YYYY-Qn (kuartal), YYYY (tahun)."""
    if not period:
        return True
    v = str(value or "")[:10]
    if len(v) < 7:
        return False
    ym, yr = v[:7], v[:4]
    p = str(period).upper()
    if "-Q" in p:
        try:
            py, q = p.split("-Q")
            q = int(q)
            months = [f"{py}-{m:02d}" for m in range((q - 1) * 3 + 1, (q - 1) * 3 + 4)]
            return ym in months
        except Exception:
            return False
    if len(p) == 4:
        return yr == p
    return ym == p[:7]


def _period_contains(requested: str, month_period: str) -> bool:
    """Apakah target bulanan (YYYY-MM) termasuk dalam periode yang diminta."""
    if not month_period:
        return False
    return _in_period(f"{month_period}-01", requested)


def _expand_periods(period_type: str, anchor: str, count: int) -> List[str]:
    """Daftar `count` periode terakhir (termasuk anchor) untuk tren komisi."""
    out: List[str] = []
    if period_type == "year":
        y = int(anchor[:4])
        out = [str(y - i) for i in range(count)]
    elif period_type == "quarter":
        py, q = anchor.upper().split("-Q")
        y, q = int(py), int(q)
        for _ in range(count):
            out.append(f"{y}-Q{q}")
            q -= 1
            if q < 1:
                q = 4
                y -= 1
    else:  # month
        y, m = int(anchor[:4]), int(anchor[5:7])
        for _ in range(count):
            out.append(f"{y}-{m:02d}")
            m -= 1
            if m < 1:
                m = 12
                y -= 1
    return out


def pick_tier_rate(tiers: List[Dict[str, Any]], achievement: float) -> float:
    rate = 0.0
    best = -1.0
    for t in (tiers or DEFAULT_TIERS):
        mn = float(t.get("min_achievement", 0) or 0)
        if achievement + 1e-9 >= mn and mn >= best:
            best = mn
            rate = float(t.get("rate", 0) or 0)
    return rate


async def sales_kpi(sales_id: str, period: Optional[str] = None, entity_id: Optional[str] = None) -> Dict[str, Any]:
    """KPI salesperson untuk periode (YYYY-MM) atau seluruh waktu bila period kosong."""
    cust_filter: Dict[str, Any] = {"assigned_sales_id": sales_id}
    if entity_id and entity_id != "all":
        cust_filter["entity_id"] = entity_id
    customers = await db.customers.find(cust_filter, {"_id": 0}).to_list(2000)
    cust_ids = [c["id"] for c in customers]

    orders: List[Dict[str, Any]] = []
    if cust_ids:
        orders = await db.sales_orders.find(
            {"customer_id": {"$in": cust_ids}}, {"_id": 0}
        ).to_list(8000)
    live_orders = [o for o in orders if o.get("status") not in DEAD_STATUSES]
    period_orders = [o for o in live_orders if _in_period(o.get("created_at"), period)]

    total_sales = sum(_order_grand_total(o) for o in period_orders)
    total_collected = 0.0
    for o in live_orders:
        for p in (o.get("payments") or []):
            if _in_period(p.get("created_at") or p.get("date"), period):
                total_collected += float(p.get("amount", 0) or 0)

    ar = overdue = 0.0
    blocked = warning = 0
    for c in customers:
        cc = await compute_customer_credit(c)
        ar += cc["ar_outstanding"]
        overdue += cc["overdue_amount"]
        if cc["status"] == "blocked":
            blocked += 1
        elif cc["status"] == "warning":
            warning += 1

    new_customers = len([c for c in customers if _in_period(c.get("created_at"), period)])
    orders_count = len(period_orders)
    aov = total_sales / orders_count if orders_count else 0
    collection_rate = (total_collected / total_sales) if total_sales else 0
    return {
        "sales_id": sales_id,
        "period": period or "all",
        "total_sales": round(total_sales, 2),
        "total_collected": round(total_collected, 2),
        "collection_rate": round(collection_rate, 4),
        "ar_outstanding": round(ar, 2),
        "overdue_amount": round(overdue, 2),
        "customers_count": len(customers),
        "new_customers": new_customers,
        "blocked_customers": blocked,
        "warning_customers": warning,
        "orders_count": orders_count,
        "avg_order_value": round(aov, 2),
    }


async def _target_collection_for(sales_id: str, period: str) -> float:
    """Agregasi target_collection bulanan yang termasuk dalam periode (bulan/kuartal/tahun)."""
    targets = await db.sales_targets.find({"sales_id": sales_id}, {"_id": 0}).to_list(400)
    total = 0.0
    for t in targets:
        if _period_contains(period, t.get("period", "")):
            total += float(t.get("target_collection_amount") or t.get("target_sales_amount") or 0)
    return total


async def _scheme_for(sales_id: str, period: str) -> Dict[str, Any]:
    """Skema insentif: exact period -> skema terbaru sales -> default tiers."""
    scheme = safe_doc(await db.sales_incentives.find_one({"sales_id": sales_id, "period": period}, {"_id": 0}))
    if not scheme:
        scheme = safe_doc(await db.sales_incentives.find_one(
            {"sales_id": sales_id}, {"_id": 0}, sort=[("period", -1)])) or {}
    return scheme


async def compute_commission(sales_id: str, period: str, entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Dispatcher strategi komisi (EPIC4). Mode dari settings.commission.strategy:
      - per_sku (default v2): per-SKU, 3 faktor, margin-aware, on-collection.
      - achievement_tiered (arsip): basis pencairan × tier capaian target (lama).
    """
    settings = await get_effective_settings(entity_id if entity_id and entity_id != "all" else None)
    strategy = (settings.get("commission") or {}).get("strategy", "per_sku")
    if strategy == "achievement_tiered":
        return await _compute_commission_tiered(sales_id, period, entity_id)
    return await _compute_commission_per_sku(sales_id, period, entity_id, settings)


async def _compute_commission_tiered(sales_id: str, period: str, entity_id: Optional[str] = None) -> Dict[str, Any]:
    """ARSIP — Komisi = basis PENCAIRAN (tertagih) x rate tiered capaian target (S36) + bonus."""
    kpi = await sales_kpi(sales_id, period, entity_id)
    scheme = await _scheme_for(sales_id, period)
    basis = scheme.get("basis", "collection")
    base_amount = kpi["total_collected"] if basis != "sales" else kpi["total_sales"]
    target_collection = await _target_collection_for(sales_id, period)
    achievement = (base_amount / target_collection * 100) if target_collection else 0
    tiers = scheme.get("tiers") or DEFAULT_TIERS
    rate = pick_tier_rate(tiers, achievement)
    commission = base_amount * rate / 100
    bonus_new = float(scheme.get("bonus_new_customer", 0) or 0) * kpi["new_customers"]
    total = commission + bonus_new
    return {
        "sales_id": sales_id,
        "period": period,
        "strategy": "achievement_tiered",
        "basis": basis,
        "base_amount": round(base_amount, 2),
        "target_amount": round(target_collection, 2),
        "achievement_pct": round(achievement, 2),
        "applied_rate": rate,
        "commission": round(commission, 2),
        "bonus_new_customer": round(bonus_new, 2),
        "total_incentive": round(total, 2),
        "breakdown": [],
        "projection_full": round(total, 2),
        "kpi": kpi,
    }


async def _load_incentive_rates(entity_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Map category -> rate doc. Prioritas entity spesifik, fallback 'all'."""
    rows = await db.incentive_rates.find({"status": "active"}, {"_id": 0}).to_list(1000)
    by_cat: Dict[str, Dict[str, Any]] = {}
    ent = entity_id if entity_id and entity_id != "all" else None
    for r in rows:
        if r.get("entity_id") == "all":
            by_cat.setdefault(r["category"], r)
    for r in rows:  # entity spesifik menimpa 'all'
        if ent and r.get("entity_id") == ent:
            by_cat[r["category"]] = r
    return by_cat


def _discount_factor(cfg: Dict[str, Any], line: Dict[str, Any], per_unit: float) -> tuple:
    """Kembalikan (effective_per_unit, factor) berdasar mekanik diskon line.

    3 mekanik (configurable): tier_factor | potong_rp | cutoff. Ambang: pct | rp_per_unit.
    """
    qty = float(line.get("quantity", 0) or 0)
    price = float(line.get("price", 0) or 0)
    line_total = float(line.get("line_total", 0) or 0)
    disc_pct = float(line.get("discount_percent", 0) or 0)
    net_unit = (line_total / qty) if qty else price
    disc_rp_per_unit = max(price - net_unit, 0.0)

    thr_type = cfg.get("discount_threshold_type", "pct")
    threshold = float(cfg.get("discount_threshold", 0) or 0)
    over = (disc_pct > threshold) if thr_type == "pct" else (disc_rp_per_unit > threshold)
    if not over:
        return per_unit, 1.0

    mech = cfg.get("discount_mechanic", "tier_factor")
    if mech == "cutoff":
        return per_unit, 0.0
    if mech == "potong_rp":
        return max(per_unit - float(cfg.get("discount_potong_rp", 0) or 0), 0.0), 1.0
    return per_unit, float(cfg.get("discount_factor", 1.0) or 0)  # tier_factor


async def _compute_commission_per_sku(
    sales_id: str, period: str, entity_id: Optional[str], settings: Dict[str, Any]
) -> Dict[str, Any]:
    """Engine per-SKU, 3 faktor, margin-aware, on-collection (EPIC4).

    Untuk tiap order, fraksi terbayar = Σpembayaran-dalam-periode / grand_total (≤1).
    Per line: qty_terbayar = base_quantity × fraksi; komisi = qty × per_unit × factor,
    di-cap oleh margin (margin_cap_pct% × margin line terbayar; pakai WAC EPIC3).
    """
    cfg = settings.get("commission") or {}
    margin_cap_pct_default = float(cfg.get("default_margin_cap_pct", 50.0) or 0)
    kpi = await sales_kpi(sales_id, period, entity_id)
    rates = await _load_incentive_rates(entity_id)
    wac_cache: Dict[str, float] = {}
    prod_cache: Dict[str, Dict[str, Any]] = {}
    ent_for_wac = entity_id if entity_id and entity_id != "all" else None

    async def _live_wac(pid: str) -> float:
        if pid not in wac_cache:
            w = await costing_service.wac_for_product(pid, entity_id=ent_for_wac)
            wac_cache[pid] = float(w.get("wac", 0) or 0)
        return wac_cache[pid]

    async def _hpp(pid: str) -> float:
        if pid not in prod_cache:
            prod_cache[pid] = await db.products.find_one({"id": pid}, {"_id": 0, "harga_pokok": 1}) or {}
        return float(prod_cache[pid].get("harga_pokok", 0) or 0)

    async def cost_for_line(line: Dict[str, Any], pid: str) -> tuple:
        """Cost-at-sale (P2-3). Prioritas: snapshot SO line -> live WAC -> harga_pokok -> unknown.

        Mengembalikan (cost_per_base_unit, cost_known). Bila tak diketahui, margin
        cap TIDAK diterapkan (hindari cap 'raksasa' diam-diam saat WAC=0/stok habis).
        """
        snap = float(line.get("unit_cost", 0) or 0)
        if snap > 0:
            return snap, True
        live = await _live_wac(pid)
        if live > 0:
            return live, True
        hpp = await _hpp(pid)
        if hpp > 0:
            return hpp, True
        return 0.0, False

    cust_filter: Dict[str, Any] = {"assigned_sales_id": sales_id}
    if entity_id and entity_id != "all":
        cust_filter["entity_id"] = entity_id
    customers = await db.customers.find(cust_filter, {"_id": 0, "id": 1}).to_list(2000)
    cust_id_set = {c["id"] for c in customers}
    # F-4c — sertakan order ber-`sales_team` (join/group sales) walau customer-nya tak di-assign ke sales ini.
    order_filter = {"$or": [{"customer_id": {"$in": list(cust_id_set)}}, {"sales_team.sales_id": sales_id}]}
    orders = await db.sales_orders.find(order_filter, {"_id": 0}).to_list(8000)
    live = [o for o in orders if o.get("status") not in DEAD_STATUSES]

    breakdown: Dict[tuple, Dict[str, Any]] = {}
    total = 0.0
    projection_full = 0.0

    for o in live:
        # F-4c — bobot atribusi insentif untuk sales_id pada order ini.
        #   order ber-sales_team → split_pct anggota; selain itu → 1.0 (atribusi assigned_sales lama).
        team = o.get("sales_team") or []
        if team:
            member = next((m for m in team if m.get("sales_id") == sales_id), None)
            if not member:
                continue
            weight = float(member.get("split_pct", 0) or 0) / 100.0
        else:
            if o.get("customer_id") not in cust_id_set:
                continue
            weight = 1.0
        if weight <= 0:
            continue
        gt = _order_grand_total(o)
        if gt <= 0:
            continue
        paid_in_period = sum(
            float(p.get("amount", 0) or 0) for p in (o.get("payments") or [])
            if _in_period(p.get("created_at") or p.get("date"), period)
        )
        frac_paid = min(paid_in_period / gt, 1.0)
        order_in_period = _in_period(o.get("created_at"), period)
        contributes = order_in_period or paid_in_period > 0
        for line in (o.get("items") or []):
            pid = line.get("product_id")
            category = line.get("category", "")
            base_qty = float(line.get("base_quantity", line.get("quantity", 0)) or 0)
            if base_qty <= 0:
                continue
            rate_cfg = rates.get(category)
            per_unit0 = float((rate_cfg or {}).get("per_unit_amount", 0) or 0)
            if per_unit0 <= 0:
                continue
            eff_cfg = {**cfg, **(rate_cfg or {})}
            per_unit, factor = _discount_factor(eff_cfg, line, per_unit0)
            margin_cap_pct = float((rate_cfg or {}).get("margin_cap_pct", margin_cap_pct_default) or 0)

            qty_line = float(line.get("quantity", 0) or 0)
            line_total = float(line.get("line_total", 0) or 0)
            # P3-8: net revenue per BASE unit (konsisten dgn qty_paid base, bukan unit order).
            net_base = (line_total / base_qty) if base_qty else (
                (line_total / qty_line) if qty_line else float(line.get("price", 0) or 0))
            cost, cost_known = await cost_for_line(line, pid)
            unit_margin = net_base - cost  # per base-unit

            def _comm(fr: float) -> float:
                qty_paid = base_qty * fr
                gross = qty_paid * per_unit * factor
                # P2-3: margin cap HANYA bila cost diketahui (cegah cap raksasa diam-diam).
                if margin_cap_pct > 0 and cost_known:
                    cap = (margin_cap_pct / 100.0) * max(qty_paid * unit_margin, 0.0)
                    return max(min(gross, cap), 0.0)
                return max(gross, 0.0)

            line_comm = _comm(frac_paid) * weight
            total += line_comm
            if contributes:
                projection_full += _comm(1.0) * weight

            key = (category, line.get("sku", ""))
            b = breakdown.setdefault(key, {
                "category": category, "sku": line.get("sku", ""),
                "name": line.get("product_name", ""), "qty_base": 0.0, "commission": 0.0,
            })
            b["qty_base"] += base_qty * frac_paid * weight
            b["commission"] += line_comm

    target_collection = await _target_collection_for(sales_id, period)
    achievement = (kpi["total_collected"] / target_collection * 100) if target_collection else 0
    rows = sorted(breakdown.values(), key=lambda x: x["commission"], reverse=True)
    for r in rows:
        r["qty_base"] = round(r["qty_base"], 2)
        r["commission"] = round(r["commission"], 2)

    return {
        "sales_id": sales_id,
        "period": period,
        "strategy": "per_sku",
        "basis": "per_sku_collection",
        "base_amount": round(kpi["total_collected"], 2),
        "target_amount": round(target_collection, 2),
        "achievement_pct": round(achievement, 2),
        "applied_rate": None,
        "commission": round(total, 2),
        "bonus_new_customer": 0.0,
        "total_incentive": round(total, 2),
        "projection_full": round(projection_full, 2),
        "breakdown": rows,
        "kpi": kpi,
    }


async def commission_history(
    sales_id: str, period_type: str = "month", anchor: str = None, count: int = 6, entity_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Tren komisi `count` periode terakhir (untuk grafik multi-periode, S+5a)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if not anchor:
        if period_type == "year":
            anchor = now.strftime("%Y")
        elif period_type == "quarter":
            anchor = f"{now.year}-Q{(now.month - 1) // 3 + 1}"
        else:
            anchor = now.strftime("%Y-%m")
    periods = _expand_periods(period_type, anchor, count)
    rows = []
    for p in reversed(periods):  # urut kronologis
        c = await compute_commission(sales_id, p, entity_id)
        rows.append({
            "period": p,
            "total_sales": c["kpi"]["total_sales"],
            "total_collected": c["kpi"]["total_collected"],
            "achievement_pct": c["achievement_pct"],
            "total_incentive": c["total_incentive"],
        })
    return rows


async def leaderboard(period: Optional[str] = None, entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """KPI semua salesperson, urut total_sales desc (Manager view)."""
    sales_users = await db.users.find({"role": "sales", "status": "active"}, {"_id": 0, "id": 1, "name": 1}).to_list(100)
    rows = []
    for u in sales_users:
        kpi = await sales_kpi(u["id"], period, entity_id)
        kpi["sales_name"] = u.get("name", "")
        rows.append(kpi)
    rows.sort(key=lambda r: r["total_sales"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows
