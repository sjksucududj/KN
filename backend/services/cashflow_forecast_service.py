"""FINANCE — Proyeksi Arus Kas (Cash Flow Forecast) (EPIC P1-3).

Proyeksi likuiditas ke depan dari:
- INFLOW  : piutang (AR) belum lunas dari sales_orders, jatuh tempo = created_at
            + term_days (customer/order).
- OUTFLOW : hutang (AP) belum lunas dari vendor_bills (posted/paid partial),
            jatuh tempo = due_date.
Dikelompokkan ke bucket waktu + posisi kas kumulatif dari saldo kas GL awal.
"""
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from db import db
from core_utils import now_iso
from services import financial_statement_service as fs
from services.vendor_bill_service import bill_financials
from services.cash_flow_service import CASH_CODES

EPS = 0.005
PAYABLE_BILL_STATUSES = ["posted", "paid"]
DEAD_SO = {"cancelled", "draft", "rejected", "expired"}
NON_AR_METHODS = {"tunai", "cash"}

BUCKETS = [
    ("overdue", "Jatuh Tempo (Lewat)", -10**9, -1),
    ("d0_30", "0–30 hari", 0, 30),
    ("d31_60", "31–60 hari", 31, 60),
    ("d61_90", "61–90 hari", 61, 90),
    ("d90_plus", "> 90 hari", 91, 10**9),
]


def _parse(dt: Any) -> Optional[datetime]:
    if not dt:
        return None
    try:
        d = datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _bucket_key(days: int) -> str:
    for key, _lbl, lo, hi in BUCKETS:
        if lo <= days <= hi:
            return key
    return "d90_plus"


async def _cash_now(scope: Optional[Dict[str, Any]]) -> float:
    agg = await fs._aggregate(scope, None, include_closing=True)
    total = 0.0
    for code in CASH_CODES:
        v = agg.get(code, {"debit": 0.0, "credit": 0.0})
        total += float(v.get("debit", 0) or 0) - float(v.get("credit", 0) or 0)
    return round(total, 2)


async def cashflow_forecast(scope: Optional[Dict[str, Any]] = None,
                            entity_id: Optional[str] = None) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    cash_now = await _cash_now(scope)

    # Peta term_days per customer utk estimasi jatuh tempo AR.
    cust_rows = await db.customers.find({}, {"_id": 0, "id": 1, "payment_profile": 1}).to_list(20000)
    term_map = {c["id"]: int((c.get("payment_profile") or {}).get("term_days", 30) or 30)
                for c in cust_rows}

    buckets: Dict[str, Dict[str, Any]] = {
        k: {"key": k, "label": lbl, "inflow": 0.0, "outflow": 0.0}
        for k, lbl, _lo, _hi in BUCKETS
    }
    ar_items: List[Dict[str, Any]] = []
    ap_items: List[Dict[str, Any]] = []

    # ── INFLOW (AR) ──
    soq: Dict[str, Any] = {**(scope or {})}
    orders = await db.sales_orders.find(soq, {
        "_id": 0, "id": 1, "number": 1, "customer_id": 1, "customer_name": 1,
        "status": 1, "payment_status": 1, "grand_total": 1, "total_amount": 1,
        "paid_total": 1, "created_at": 1, "payment_term_code": 1,
    }).to_list(50000)
    for o in orders:
        if o.get("status") in DEAD_SO or o.get("payment_status") == "paid":
            continue
        grand = float(o.get("grand_total", 0) or 0) or float(o.get("total_amount", 0) or 0)
        outstanding = round(grand - float(o.get("paid_total", 0) or 0), 2)
        if outstanding <= EPS:
            continue
        created = _parse(o.get("created_at")) or now
        due = created + timedelta(days=term_map.get(o.get("customer_id"), 30))
        days = (due - now).days
        bk = _bucket_key(days)
        buckets[bk]["inflow"] = round(buckets[bk]["inflow"] + outstanding, 2)
        ar_items.append({"number": o.get("number"), "party": o.get("customer_name", ""),
                         "amount": outstanding, "due_date": due.date().isoformat(),
                         "days_to_due": days, "bucket": bk})

    # ── OUTFLOW (AP) ──
    vbq: Dict[str, Any] = {"status": {"$in": PAYABLE_BILL_STATUSES}, **(scope or {})}
    bills = await db.vendor_bills.find(vbq, {"_id": 0}).to_list(20000)
    for b in bills:
        fin = bill_financials(b)
        out = fin["outstanding"]
        if out <= EPS:
            continue
        due = _parse(b.get("due_date")) or _parse(b.get("bill_date")) or now
        days = (due - now).days
        bk = _bucket_key(days)
        buckets[bk]["outflow"] = round(buckets[bk]["outflow"] + out, 2)
        ap_items.append({"number": b.get("bill_number"), "party": b.get("supplier_name", ""),
                         "amount": out, "due_date": (due.date().isoformat() if due else ""),
                         "days_to_due": days, "bucket": bk})

    ordered = []
    running = cash_now
    total_in = total_out = 0.0
    for key, lbl, _lo, _hi in BUCKETS:
        b = buckets[key]
        net = round(b["inflow"] - b["outflow"], 2)
        running = round(running + net, 2)
        total_in += b["inflow"]
        total_out += b["outflow"]
        ordered.append({**b, "net": net, "cumulative_cash": running})

    ar_items.sort(key=lambda x: x["days_to_due"])
    ap_items.sort(key=lambda x: x["days_to_due"])
    return {
        "cash_now": cash_now,
        "buckets": ordered,
        "total_inflow": round(total_in, 2),
        "total_outflow": round(total_out, 2),
        "net_flow": round(total_in - total_out, 2),
        "projected_cash": running,
        "ar_items": ar_items[:100],
        "ap_items": ap_items[:100],
        "generated_at": now_iso(),
    }
