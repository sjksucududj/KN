"""EPIC7-A — AR / Piutang Aging (read/derived report).

SSOT: diturunkan dari `sales_orders` + `payments[]` (SAMA dengan credit engine &
collection_worklist). Reuse helper `customer_service` agar TIDAK terjadi drift:
  `_order_grand_total`, `_order_paid`, `order_payment_method`, `_term_days`,
  `_parse_dt`, `DEAD_STATUSES`, `NON_AR_METHODS`.

Buckets aging (berdasar hari telat jatuh tempo):
  current (belum jatuh tempo), 1-30, 31-60, 61-90, 90+.

Denda (late fee) = **ESTIMASI informasional** (tidak posting ke order/GL),
configurable via `system_settings.ar` (`denda_rate_pct_per_month`, `grace_days`).
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
import math

from db import db
from services.config_service import get_effective_settings
from services.customer_service import (
    _order_grand_total as order_grand_total,
    _order_paid as order_paid,
    order_payment_method,
    _term_days as term_days,
    _parse_dt as parse_dt,
    DEAD_STATUSES,
    NON_AR_METHODS,
)

EPS = 0.01
BUCKET_KEYS = ["current", "b1_30", "b31_60", "b61_90", "b90_plus"]
WARNING_RATIO = 0.8
OVERDUE_BLOCK_DAYS = 14


async def get_ar_config(entity_id: Optional[str] = None,
                        customer_id: Optional[str] = None) -> Dict[str, Any]:
    """Kebijakan denda & kelompok umur piutang yang BERLAKU.

    FASE G-0 — dibaca lewat `config_resolver` sehingga bisa berbeda **per pelanggan**
    (global -> entitas -> pelanggan), lengkap dengan lapisan asal untuk ditampilkan ke user.
    Fallback ke `system_settings` lama tetap terjaga oleh resolver.
    """
    from services.config_resolver import resolve
    ctx = {"entity_id": entity_id, "customer_id": customer_id}
    rate = await resolve("ar.denda_rate_pct_per_month", ctx)
    grace = await resolve("ar.grace_days", ctx)
    buckets = await resolve("ar.aging_buckets", ctx)
    try:
        edges = sorted(int(float(x)) for x in (buckets["value"] or [30, 60, 90]))
    except (TypeError, ValueError):
        edges = [30, 60, 90]
    return {
        "denda_rate_pct_per_month": float(rate["value"] or 0),
        "grace_days": int(float(grace["value"] or 0)),
        "aging_buckets": edges,
        "source": {"denda_rate_pct_per_month": rate["source_label"],
                   "grace_days": grace["source_label"],
                   "aging_buckets": buckets["source_label"]},
    }


def _bucket(days_late: int, edges: Optional[List[int]] = None) -> str:
    """Kolom umur piutang. `edges` CONFIGURABLE dari `ar.aging_buckets`."""
    if days_late <= 0:
        return "current"
    e = sorted(edges or [30, 60, 90])
    for idx, edge in enumerate(e):
        if days_late <= edge:
            return BUCKET_KEYS[idx + 1] if idx + 1 < len(BUCKET_KEYS) else BUCKET_KEYS[-1]
    return BUCKET_KEYS[-1]


def _denda_estimate(outstanding: float, days_late: int, cfg: Dict[str, Any]) -> float:
    rate = float(cfg.get("denda_rate_pct_per_month", 0) or 0)
    eff = days_late - int(cfg.get("grace_days", 0) or 0)
    if rate <= 0 or eff <= 0 or outstanding <= EPS:
        return 0.0
    months = math.ceil(eff / 30)
    return round(outstanding * (rate / 100.0) * months, 2)


def _empty_buckets() -> Dict[str, float]:
    return {k: 0.0 for k in BUCKET_KEYS}


def _credit_status(credit_limit: float, ar_outstanding: float, max_overdue_days: int,
                   manual_status: str) -> str:
    status = "active"
    near = credit_limit > 0 and ar_outstanding >= WARNING_RATIO * credit_limit
    over = credit_limit > 0 and ar_outstanding >= credit_limit
    if near or max_overdue_days > 0:
        status = "warning"
    if over or max_overdue_days > OVERDUE_BLOCK_DAYS:
        status = "blocked"
    if manual_status == "blocked":
        status = "blocked"
    return status


async def _load_scope(entity_id: Optional[Any], sales_id: Optional[str]):
    """Ambil customers (terfilter) + map sales-name dalam minimal query.

    FASE E-0 (L9) — `entity_id` sekarang boleh berupa:
      * `str`  → satu entitas (isolasi ketat),
      * `dict` → filter Mongo siap pakai (mis. `{"$in": [...]}` untuk mode gabungan),
      * `None`/`"all"` → tanpa filter (hanya untuk peran lintas-entitas).
    """
    cust_filter: Dict[str, Any] = {}
    if isinstance(entity_id, dict):
        cust_filter["entity_id"] = entity_id
    elif entity_id and entity_id != "all":
        cust_filter["entity_id"] = entity_id
    if sales_id:
        cust_filter["assigned_sales_id"] = sales_id
    customers = await db.customers.find(
        cust_filter,
        {"_id": 0, "id": 1, "name": 1, "assigned_sales_id": 1, "payment_profile": 1,
         "credit_limit": 1, "status": 1, "entity_id": 1, "deposit_balance": 1},
    ).to_list(5000)
    sales_ids = {c.get("assigned_sales_id") for c in customers if c.get("assigned_sales_id")}
    smap = {}
    if sales_ids:
        for u in await db.users.find({"id": {"$in": list(sales_ids)}}, {"_id": 0, "id": 1, "name": 1}).to_list(2000):
            smap[u["id"]] = u.get("name", "")
    return customers, smap


def _eligible_outstanding(o: Dict[str, Any]):
    """Return outstanding bila order termasuk AR terbuka, else None."""
    if o.get("status") in DEAD_STATUSES or o.get("payment_status") == "paid":
        return None
    if order_payment_method(o) in NON_AR_METHODS:
        return None
    outstanding = round(order_grand_total(o) - order_paid(o), 2)
    if outstanding <= EPS:
        return None
    return outstanding


async def aging_report(entity_id: Optional[str] = None, sales_id: Optional[str] = None,
                       as_of: Optional[str] = None) -> Dict[str, Any]:
    """Ringkasan aging piutang: totals per-bucket + baris per-customer.

    FASE G-3 — kolom denda tidak lagi hanya ESTIMASI: setiap baris juga membawa
    **nota denda NYATA** (`penalty_*`) hasil FASE G-2 sehingga angka di laporan bisa
    diklik menuju dokumennya (dan terlihat mana yang masih usulan, sudah terbit,
    dibebaskan, atau dibayar).
    """
    now = parse_dt(as_of) or datetime.now(timezone.utc)
    # FASE E-0 (L9) — normalisasi: kebijakan (config) selalu dibaca dengan entitas
    # SKALAR; filter query boleh berupa dict `{"$in": [...]}` untuk mode gabungan.
    _cfg_entity = entity_id if isinstance(entity_id, str) and entity_id != "all" else None
    if isinstance(entity_id, dict):
        _one = (entity_id.get("$in") or [])
        _cfg_entity = _one[0] if len(_one) == 1 else None
    cfg = await get_ar_config(_cfg_entity)
    cust_cfg: Dict[str, Dict[str, Any]] = {}
    customers, smap = await _load_scope(entity_id, sales_id)
    cmap = {c["id"]: c for c in customers}
    cust_ids = list(cmap.keys())

    per_customer: Dict[str, Dict[str, Any]] = {}
    totals = {**_empty_buckets(), "total": 0.0, "overdue": 0.0, "denda": 0.0,
              "orders": 0, "customers": 0,
              # FASE G-3 — nota denda nyata (dokumen), bukan estimasi
              "penalty_docs": 0, "penalty_draft": 0.0, "penalty_issued": 0.0,
              "penalty_waived": 0.0, "penalty_paid": 0.0, "penalty_actual": 0.0}

    if cust_ids:
        orders = await db.sales_orders.find(
            {"customer_id": {"$in": cust_ids}},
            {"_id": 0, "id": 1, "number": 1, "customer_id": 1, "customer_name": 1,
             "status": 1, "payment_status": 1, "grand_total": 1, "total_amount": 1,
             "payments": 1, "created_at": 1, "payment_term_code": 1,
             "payment_term_days": 1, "payment_profile_method": 1},
        ).to_list(20000)

        # Nota denda nyata untuk seluruh pesanan pelanggan dalam SATU query.
        from services import penalty_service as penalties
        pen_by_doc = await penalties.for_docs([o.get("id") for o in orders])

        for o in orders:
            outstanding = _eligible_outstanding(o)
            if outstanding is None:
                continue
            cid = o.get("customer_id")
            cust = cmap.get(cid, {})
            created = parse_dt(o.get("created_at")) or now
            due = created + timedelta(days=term_days(cust, o))
            days_late = (now - due).days
            # FASE G-0 — kelompok umur & denda kini bisa berbeda PER PELANGGAN
            # (global → entitas → pelanggan) lewat config_resolver.
            ccfg = cust_cfg.get(cid)
            if ccfg is None:
                ccfg = await get_ar_config(_cfg_entity, cid)
                cust_cfg[cid] = ccfg
            bucket = _bucket(days_late, ccfg.get("aging_buckets"))
            denda = _denda_estimate(outstanding, days_late, ccfg)
            pen_rows = pen_by_doc.get(o.get("id")) or []
            pen = penalties.summarize(pen_rows)

            row = per_customer.get(cid)
            if not row:
                row = {
                    "customer_id": cid,
                    "customer_name": o.get("customer_name") or cust.get("name", ""),
                    "assigned_sales_id": cust.get("assigned_sales_id", ""),
                    "assigned_sales_name": smap.get(cust.get("assigned_sales_id", ""), ""),
                    "credit_limit": round(float(cust.get("credit_limit", 0) or 0), 2),
                    "deposit_balance": round(float(cust.get("deposit_balance", 0) or 0), 2),
                    **_empty_buckets(),
                    "outstanding": 0.0, "overdue": 0.0, "denda": 0.0,
                    "oldest_days": 0, "orders": 0,
                    "penalty_docs": 0, "penalty_draft": 0.0, "penalty_issued": 0.0,
                    "penalty_waived": 0.0, "penalty_paid": 0.0, "penalty_actual": 0.0,
                    "_manual_status": cust.get("status", ""),
                }
                per_customer[cid] = row
            row[bucket] = round(row[bucket] + outstanding, 2)
            row["outstanding"] = round(row["outstanding"] + outstanding, 2)
            row["orders"] += 1
            if days_late > 0:
                row["overdue"] = round(row["overdue"] + outstanding, 2)
                row["oldest_days"] = max(row["oldest_days"], days_late)
            row["denda"] = round(row["denda"] + denda, 2)
            for key, val in (("penalty_docs", pen["count"]),
                             ("penalty_draft", pen["draft_amount"]),
                             ("penalty_issued", pen["issued_outstanding"]),
                             ("penalty_waived", pen["waived_amount"]),
                             ("penalty_paid", pen["paid_amount"]),
                             ("penalty_actual", pen["actual_amount"])):
                row[key] = round(row[key] + val, 2) if isinstance(val, float) else row[key] + val
                totals[key] = round(totals[key] + val, 2) if isinstance(val, float) else totals[key] + val

            totals[bucket] = round(totals[bucket] + outstanding, 2)
            totals["total"] = round(totals["total"] + outstanding, 2)
            totals["orders"] += 1
            if days_late > 0:
                totals["overdue"] = round(totals["overdue"] + outstanding, 2)
            totals["denda"] = round(totals["denda"] + denda, 2)

    rows: List[Dict[str, Any]] = []
    for row in per_customer.values():
        row["credit_status"] = _credit_status(
            row["credit_limit"], row["outstanding"], row["oldest_days"], row.pop("_manual_status", ""))
        row["available_credit"] = (round(max(row["credit_limit"] - row["outstanding"], 0), 2)
                                   if row["credit_limit"] > 0 else None)
        # Selisih antara denda ESTIMASI dan denda yang benar-benar sudah jadi dokumen —
        # inilah "pekerjaan yang belum dilakukan" (belum dibuatkan nota).
        row["denda_undocumented"] = round(max(row["denda"] - row["penalty_actual"], 0), 2)
        rows.append(row)
    rows.sort(key=lambda r: r["outstanding"], reverse=True)
    totals["customers"] = len(rows)
    totals["denda_undocumented"] = round(
        max(totals["denda"] - totals["penalty_actual"], 0), 2)

    from services import penalty_service as _pen
    # FASE E-0 (L9) — laporan WAJIB menyebut entitasnya. Dulu `entity_id` selalu "all"
    # dan totalnya identik untuk KSC/KANDA/ALL (Rp 20.260.900) karena konteks tak dibaca.
    ent_scalar = entity_id if isinstance(entity_id, str) else None
    ent_ids = (entity_id or {}).get("$in", []) if isinstance(entity_id, dict) else (
        [ent_scalar] if ent_scalar and ent_scalar != "all" else [])
    ent_name = ""
    if len(ent_ids) == 1:
        ent = await db.business_entities.find_one({"id": ent_ids[0]}, {"_id": 0})
        ent_name = (ent or {}).get("short_name") or (ent or {}).get("legal_name") or ent_ids[0]
    elif ent_ids:
        names = []
        async for e in db.business_entities.find({"id": {"$in": ent_ids}}, {"_id": 0}):
            names.append(e.get("short_name") or e.get("legal_name") or e.get("id"))
        ent_name = "Gabungan: " + " + ".join(sorted(names))
    else:
        ent_name = "Semua Entitas (gabungan)"
    return {
        "as_of": now.isoformat(),
        "entity_id": ent_ids[0] if len(ent_ids) == 1 else "all",
        "entity_ids": ent_ids,
        "entity_name": ent_name,
        "is_consolidated": len(ent_ids) != 1,
        "config": cfg,
        # FASE G-3 — kebijakan denda yang BERLAKU ikut dikirim supaya layar bisa
        # menjelaskan kenapa estimasi & nota denda bisa berbeda (dasar hitung, tenggang).
        "penalty_policy": await _pen.penalty_policy(ent_ids[0] if len(ent_ids) == 1 else ""),
        "totals": totals,
        "customers": rows,
    }


async def orders_due_soon(offsets: List[int], entity_id: Optional[str] = None,
                          sales_id: Optional[str] = None,
                          as_of: Optional[str] = None) -> List[Dict[str, Any]]:
    """PS-21 — daftar order AR yang jatuh tempo **tepat** pada offset hari tertentu.

    `offsets` dihitung sebagai `hari_lewat` (`now - due`): `-3` = 3 hari sebelum
    jatuh tempo (H-3), `0` = hari-H, `1` = H+1.

    Memakai helper yang SAMA dengan `aging_report` (`_eligible_outstanding`,
    `term_days`) sehingga angka piutang tidak pernah drift (R3).
    """
    wanted = {int(o) for o in (offsets or [])}
    if not wanted:
        return []
    now = parse_dt(as_of) or datetime.now(timezone.utc)
    customers, smap = await _load_scope(entity_id, sales_id)
    cmap = {c["id"]: c for c in customers}
    if not cmap:
        return []
    orders = await db.sales_orders.find(
        {"customer_id": {"$in": list(cmap.keys())}},
        {"_id": 0, "id": 1, "number": 1, "customer_id": 1, "customer_name": 1,
         "status": 1, "payment_status": 1, "grand_total": 1, "total_amount": 1,
         "payments": 1, "created_at": 1, "payment_term_code": 1,
         "payment_term_days": 1, "payment_profile_method": 1, "entity_id": 1},
    ).to_list(20000)

    rows: List[Dict[str, Any]] = []
    for o in orders:
        outstanding = _eligible_outstanding(o)
        if outstanding is None:
            continue
        cust = cmap.get(o.get("customer_id"), {})
        created = parse_dt(o.get("created_at")) or now
        due = created + timedelta(days=term_days(cust, o))
        offset = (now.date() - due.date()).days
        if offset not in wanted:
            continue
        rows.append({
            "order_id": o.get("id"), "number": o.get("number", ""),
            "customer_id": o.get("customer_id"),
            "customer_name": o.get("customer_name") or cust.get("name", ""),
            "assigned_sales_id": cust.get("assigned_sales_id", ""),
            "assigned_sales_name": smap.get(cust.get("assigned_sales_id", ""), ""),
            "entity_id": o.get("entity_id"),
            "outstanding": outstanding,
            "due_date": due.date().isoformat(),
            "offset": offset,
        })
    rows.sort(key=lambda r: (-r["offset"], -r["outstanding"]))
    return rows


async def customer_aging_detail(customer_id: str, as_of: Optional[str] = None,
                               entity_ids: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Rincian per-order untuk satu customer (untuk drill-down).

    FASE G-3 — tiap baris membawa **nota denda nyata** pesanan itu (nomor, status, jurnal)
    sehingga kolom denda di laporan bisa diklik ke dokumennya, plus penanda pesanan mana
    yang dendanya masih sekadar estimasi (belum pernah dibuatkan nota).

    FASE E-0 (L9) — `entity_ids` = pagar anti-IDOR: bila diisi, pelanggan di luar
    entitas itu dianggap TIDAK ADA (404 di router).
    """
    cust_q: Dict[str, Any] = {"id": customer_id}
    if entity_ids:
        cust_q["entity_id"] = {"$in": list(entity_ids)}
    customer = await db.customers.find_one(
        cust_q,
        {"_id": 0, "id": 1, "name": 1, "assigned_sales_id": 1, "payment_profile": 1,
         "credit_limit": 1, "status": 1, "deposit_balance": 1, "entity_id": 1},
    )
    if not customer:
        return None
    now = parse_dt(as_of) or datetime.now(timezone.utc)
    cfg = await get_ar_config(customer_id=customer_id)
    orders = await db.sales_orders.find(
        {"customer_id": customer_id}, {"_id": 0}
    ).to_list(5000)

    from services import penalty_service as penalties
    from services import payment_plan_service as plans
    pen_by_doc = await penalties.for_docs([o.get("id") for o in orders])

    items: List[Dict[str, Any]] = []
    totals = {**_empty_buckets(), "total": 0.0, "overdue": 0.0, "denda": 0.0,
              "penalty_docs": 0, "penalty_draft": 0.0, "penalty_issued": 0.0,
              "penalty_waived": 0.0, "penalty_paid": 0.0, "penalty_actual": 0.0}
    all_penalties: List[Dict[str, Any]] = []
    plan_rows: List[Dict[str, Any]] = []
    for o in orders:
        outstanding = _eligible_outstanding(o)
        if outstanding is None:
            continue
        created = parse_dt(o.get("created_at")) or now
        due = created + timedelta(days=term_days(customer, o))
        days_late = (now - due).days
        bucket = _bucket(days_late, cfg.get("aging_buckets"))
        denda = _denda_estimate(outstanding, days_late, cfg)
        pen_rows = pen_by_doc.get(o.get("id")) or []
        pen = penalties.summarize(pen_rows)
        plan = await plans.get_active("sales_order", o.get("id", ""))
        if plan:
            nd = plans.next_due(plan) or {}
            plan_rows.append({
                "plan_id": plan["id"], "plan_number": plan.get("number", ""),
                "order_id": o.get("id"), "order_number": o.get("number") or o.get("id"),
                "mode_label": plan.get("mode_label", ""),
                "next_due_date": nd.get("due_date", ""),
                "overdue_count": len(plans.overdue_lines(plan)),
            })
        for p in pen_rows:
            all_penalties.append({**p, "order_number": o.get("number") or o.get("id")})
        items.append({
            "order_id": o.get("id"),
            "order_number": o.get("number") or o.get("id"),
            "grand_total": round(order_grand_total(o), 2),
            "paid_total": round(order_paid(o), 2),
            "outstanding": outstanding,
            "due_date": due.date().isoformat(),
            "days_late": days_late,
            "bucket": bucket,
            "overdue": days_late > 0,
            "denda_estimate": denda,
            # FASE G-3 — dokumen denda nyata pada pesanan ini
            "penalties": [{"id": p.get("id"), "number": p.get("number"),
                           "status": p.get("status"), "status_label": p.get("status_label", ""),
                           "amount": round(float(p.get("amount") or 0), 2),
                           "paid_amount": round(float(p.get("paid_amount") or 0), 2),
                           "due_date": p.get("due_date", ""),
                           "line_label": p.get("line_label", ""),
                           "je_number": p.get("je_number", ""),
                           "reason_label": p.get("reason_label", "")} for p in pen_rows],
            "penalty_docs": pen["count"],
            "penalty_actual": pen["actual_amount"],
            "penalty_draft": pen["draft_amount"],
            "penalty_issued": pen["issued_outstanding"],
            "penalty_undocumented": round(max(denda - pen["actual_amount"], 0), 2),
            "has_plan": bool(plan),
            "plan_number": (plan or {}).get("number", ""),
            "payment_status": o.get("payment_status") or "unpaid",
            "created_at": o.get("created_at"),
        })
        totals[bucket] = round(totals[bucket] + outstanding, 2)
        totals["total"] = round(totals["total"] + outstanding, 2)
        totals["denda"] = round(totals["denda"] + denda, 2)
        totals["penalty_docs"] += pen["count"]
        for key, src in (("penalty_draft", "draft_amount"),
                         ("penalty_issued", "issued_outstanding"),
                         ("penalty_waived", "waived_amount"),
                         ("penalty_paid", "paid_amount"),
                         ("penalty_actual", "actual_amount")):
            totals[key] = round(totals[key] + pen[src], 2)
        if days_late > 0:
            totals["overdue"] = round(totals["overdue"] + outstanding, 2)
    items.sort(key=lambda r: r["days_late"], reverse=True)
    all_penalties.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    totals["denda_undocumented"] = round(max(totals["denda"] - totals["penalty_actual"], 0), 2)

    return {
        "customer_id": customer["id"],
        "customer_name": customer.get("name", ""),
        "credit_limit": round(float(customer.get("credit_limit", 0) or 0), 2),
        "deposit_balance": round(float(customer.get("deposit_balance", 0) or 0), 2),
        "config": cfg,
        "penalty_policy": await penalties.penalty_policy(customer_id=customer_id),
        "totals": totals,
        "items": items,
        "penalties": all_penalties,
        "plans": plan_rows,
    }
