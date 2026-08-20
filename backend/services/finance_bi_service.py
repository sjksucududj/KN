"""FINANCE — BI Keuangan (dashboard analitik) diturunkan dari GL.

Menyediakan data untuk dashboard: tren bulanan (12 bln), KPI YTD, rasio kunci,
dan perbandingan antar entitas (PT). Semua angka operasional memakai
`income_statement` (yang MENGECUALIKAN jurnal penutup), sedangkan rasio neraca
memakai `balance_sheet` (menyertakan jurnal penutup) — konsisten dengan modul
Laporan Keuangan & Tutup Buku.
"""
import calendar
from typing import Any, Dict, List, Optional

from db import db
from services import financial_statement_service as fs

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
                "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _month_bounds(year: int, m: int):
    last = calendar.monthrange(year, m)[1]
    return f"{year}-{m:02d}-01", f"{year}-{m:02d}-{last:02d}"


def _section_total(sections: List[Dict[str, Any]], key: str) -> float:
    for s in sections:
        if s.get("key") == key:
            return float(s.get("total", 0) or 0)
    return 0.0


async def _entity_names(entity_ids: List[str]) -> List[Dict[str, str]]:
    rows = await db.business_entities.find(
        {"id": {"$in": list(entity_ids)}},
        {"_id": 0, "id": 1, "short_name": 1, "legal_name": 1, "is_group": 1},
    ).to_list(200)
    out = []
    for r in rows:
        if r.get("is_group"):
            continue
        out.append({"id": r["id"], "name": r.get("short_name") or r.get("legal_name") or r["id"]})
    return out


async def finance_bi(year: int, scope: Optional[Dict[str, Any]],
                     entity_ids: List[str]) -> Dict[str, Any]:
    # ── Tren bulanan (operasional) ──
    monthly: List[Dict[str, Any]] = []
    ytd_rev = ytd_cogs = ytd_opex = 0.0
    for m in range(1, 13):
        s, e = _month_bounds(year, m)
        stmt = await fs.income_statement(start=s, end=e, scope=scope)
        rev = float(stmt.get("revenue_total", 0) or 0)
        cogs = float(stmt.get("cogs_total", 0) or 0)
        opex = float(stmt.get("opex_total", 0) or 0)
        monthly.append({
            "month": f"{year}-{m:02d}",
            "label": MONTH_LABELS[m - 1],
            "revenue": rev,
            "cogs": cogs,
            "opex": opex,
            "expense": round(cogs + opex, 2),
            "gross_profit": round(rev - cogs, 2),
            "net_income": float(stmt.get("net_income", 0) or 0),
        })
        ytd_rev += rev
        ytd_cogs += cogs
        ytd_opex += opex

    ytd_rev = round(ytd_rev, 2)
    ytd_cogs = round(ytd_cogs, 2)
    ytd_opex = round(ytd_opex, 2)
    ytd_expense = round(ytd_cogs + ytd_opex, 2)
    ytd_gross = round(ytd_rev - ytd_cogs, 2)
    ytd_net = round(ytd_rev - ytd_expense, 2)
    gross_margin = round(ytd_gross / ytd_rev * 100, 1) if ytd_rev > 0 else 0.0
    net_margin = round(ytd_net / ytd_rev * 100, 1) if ytd_rev > 0 else 0.0

    # ── Rasio neraca (posisi akhir tahun, termasuk jurnal penutup) ──
    bs = await fs.balance_sheet(as_of=f"{year}-12-31", scope=scope)
    current_assets = _section_total(bs.get("assets", {}).get("sections", []), "current")
    current_liab = _section_total(bs.get("liabilities", {}).get("sections", []), "current")
    assets_total = float(bs.get("assets_total", 0) or 0)
    liabilities_total = float(bs.get("liabilities_total", 0) or 0)
    equity_total = float(bs.get("equity_total", 0) or 0)
    current_ratio = round(current_assets / current_liab, 2) if abs(current_liab) > 0.005 else None
    debt_to_equity = round(liabilities_total / equity_total, 2) if abs(equity_total) > 0.005 else None

    # ── Perbandingan antar entitas (PT) ──
    comparison: List[Dict[str, Any]] = []
    names = await _entity_names(entity_ids)
    for ent in names:
        eid = ent["id"]
        st = await fs.income_statement(start=f"{year}-01-01", end=f"{year}-12-31",
                                       scope={"entity_id": eid})
        rev = float(st.get("revenue_total", 0) or 0)
        exp = round(float(st.get("cogs_total", 0) or 0) + float(st.get("opex_total", 0) or 0), 2)
        comparison.append({
            "entity_id": eid,
            "name": ent["name"],
            "revenue": rev,
            "expense": exp,
            "net_income": float(st.get("net_income", 0) or 0),
            "net_margin": float(st.get("net_margin", 0) or 0),
        })
    comparison.sort(key=lambda x: x["revenue"], reverse=True)

    return {
        "year": year,
        "monthly": monthly,
        "kpi": {
            "revenue": ytd_rev,
            "cogs": ytd_cogs,
            "opex": ytd_opex,
            "expense": ytd_expense,
            "gross_profit": ytd_gross,
            "net_income": ytd_net,
            "gross_margin": gross_margin,
            "net_margin": net_margin,
        },
        "ratios": {
            "gross_margin": gross_margin,
            "net_margin": net_margin,
            "current_ratio": current_ratio,
            "debt_to_equity": debt_to_equity,
            "current_assets": round(current_assets, 2),
            "current_liabilities": round(current_liab, 2),
            "assets_total": round(assets_total, 2),
            "liabilities_total": round(liabilities_total, 2),
            "equity_total": round(equity_total, 2),
        },
        "entity_comparison": comparison,
        "multi_entity": len(comparison) > 1,
    }
