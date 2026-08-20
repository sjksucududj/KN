"""FINANCE — Control Tower (Dashboard Keuangan terpadu) (EPIC P1-5).

Satu endpoint agregat untuk dashboard: posisi kas (GL), ringkasan AR & AP + aging,
snapshot Laba-Rugi (MTD & YTD), tren bulanan + rasio (reuse BI), serta daftar
jatuh tempo teratas. Ter-scope per entitas.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db import db
from core_utils import now_iso
from services import financial_statement_service as fs
from services import finance_bi_service as bi
from services import ar_aging_service as ar
from services.vendor_bill_service import bill_financials
from services.cash_flow_service import CASH_CODES

PAYABLE_BILL_STATUSES = ["posted", "paid"]
EPS = 0.005


async def _cash_position(scope: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    amap = await fs._accounts_map()
    agg = await fs._aggregate(scope, None, include_closing=True)
    lines = []
    total = 0.0
    for code in sorted(CASH_CODES):
        v = agg.get(code, {"debit": 0.0, "credit": 0.0})
        bal = round(float(v.get("debit", 0) or 0) - float(v.get("credit", 0) or 0), 2)
        total += bal
        lines.append({"code": code, "name": amap.get(code, {}).get("name", code), "balance": bal})
    return {"total": round(total, 2), "accounts": lines}


async def _ap_summary(scope: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    q: Dict[str, Any] = {"status": {"$in": PAYABLE_BILL_STATUSES}, **(scope or {})}
    bills = await db.vendor_bills.find(q, {"_id": 0}).to_list(20000)
    aging = {"d0_30": 0.0, "d31_60": 0.0, "d61_90": 0.0, "d90_plus": 0.0}
    total = 0.0
    top: List[Dict[str, Any]] = []
    for b in bills:
        out = bill_financials(b)["outstanding"]
        if out <= EPS:
            continue
        total += out
        ref = b.get("due_date") or b.get("bill_date") or b.get("created_at") or ""
        days = 0
        try:
            d = datetime.fromisoformat(str(ref).replace("Z", "+00:00"))
            d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
            days = (now - d).days
        except (ValueError, TypeError):
            days = 0
        bk = "d0_30" if days <= 30 else "d31_60" if days <= 60 else "d61_90" if days <= 90 else "d90_plus"
        aging[bk] = round(aging[bk] + out, 2)
        top.append({"number": b.get("bill_number"), "party": b.get("supplier_name", ""),
                    "amount": out, "days": days})
    top.sort(key=lambda x: x["amount"], reverse=True)
    return {"outstanding": round(total, 2), "aging": aging, "top": top[:5]}


def _pl_snapshot(stmt: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "revenue": stmt.get("revenue_total", 0),
        "cogs": stmt.get("cogs_total", 0),
        "gross_profit": stmt.get("gross_profit", 0),
        "opex": stmt.get("opex_total", 0),
        "net_income": stmt.get("net_income", 0),
        "net_margin": stmt.get("net_margin", 0),
    }


async def finance_tower(scope: Optional[Dict[str, Any]] = None,
                        entity_id: Optional[str] = None,
                        entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    year = now.year
    ym = f"{year}-{now.month:02d}"
    month_start = f"{ym}-01"
    year_start = f"{year}-01-01"
    today = now.date().isoformat()

    cash = await _cash_position(scope)
    mtd = _pl_snapshot(await fs.income_statement(month_start, today, scope))
    ytd = _pl_snapshot(await fs.income_statement(year_start, today, scope))
    ap = await _ap_summary(scope)
    ar_rep = await ar.aging_report(entity_id if entity_id and entity_id != "all" else None)
    ar_tot = ar_rep.get("totals", {})
    bi_data = await bi.finance_bi(year, scope, entity_ids or ([entity_id] if entity_id else []))

    ar_top = [
        {"customer_name": c.get("customer_name", ""), "outstanding": c.get("outstanding", 0),
         "overdue": c.get("overdue", 0), "oldest_days": c.get("oldest_days", 0)}
        for c in ar_rep.get("customers", [])[:5]
    ]

    return {
        "period": {"month": ym, "year": year},
        "cash": cash,
        "ar": {
            "outstanding": ar_tot.get("total", 0),
            "overdue": ar_tot.get("overdue", 0),
            "aging": {
                "current": ar_tot.get("current", 0), "b1_30": ar_tot.get("b1_30", 0),
                "b31_60": ar_tot.get("b31_60", 0), "b61_90": ar_tot.get("b61_90", 0),
                "b90_plus": ar_tot.get("b90_plus", 0),
            },
            "top": ar_top,
        },
        "ap": ap,
        "working_capital": round(cash["total"] + ar_tot.get("total", 0) - ap["outstanding"], 2),
        "pl": {"mtd": mtd, "ytd": ytd},
        "monthly": bi_data.get("monthly", []),
        "ratios": bi_data.get("ratios", {}),
        "entity_comparison": bi_data.get("entity_comparison", []),
        "generated_at": now_iso(),
    }
