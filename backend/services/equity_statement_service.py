"""FINANCE — Laporan Perubahan Ekuitas (Statement of Changes in Equity).

Diturunkan dari `balance_sheet()` untuk periode [start, end] sehingga SELALU
rekonsiliasi dengan Neraca. Setiap komponen ekuitas menampilkan Saldo Awal,
Pergerakan, dan Saldo Akhir; ditambah komponen "Laba (Rugi) Periode Berjalan"
(laba belum ditutup dari P&L). Ter-scope per entitas.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core_utils import now_iso
from services import financial_statement_service as fs


def _prev_day(d: str) -> str:
    dt = datetime.fromisoformat(f"{d[:10]}T00:00:00")
    return (dt - timedelta(days=1)).strftime("%Y-%m-%d")


async def equity_statement(start: Optional[str] = None, end: Optional[str] = None,
                           scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    bs_end = await fs.balance_sheet(as_of=end, scope=scope)
    end_map = {l["code"]: l for l in bs_end["equity"]["lines"]}
    end_ce = float(bs_end["equity"].get("current_earnings", 0) or 0)
    end_total = float(bs_end.get("equity_total", 0) or 0)

    begin_map: Dict[str, Any] = {}
    begin_ce = 0.0
    begin_total = 0.0
    if start:
        bs_begin = await fs.balance_sheet(as_of=_prev_day(start), scope=scope)
        begin_map = {l["code"]: l for l in bs_begin["equity"]["lines"]}
        begin_ce = float(bs_begin["equity"].get("current_earnings", 0) or 0)
        begin_total = float(bs_begin.get("equity_total", 0) or 0)

    codes = sorted(set(begin_map) | set(end_map))
    components: List[Dict[str, Any]] = []
    for code in codes:
        b = float((begin_map.get(code) or {}).get("amount", 0) or 0)
        e = float((end_map.get(code) or {}).get("amount", 0) or 0)
        name = (end_map.get(code) or begin_map.get(code) or {}).get("name", code)
        components.append({"code": code, "name": name,
                           "begin": round(b, 2), "movement": round(e - b, 2), "end": round(e, 2)})

    # Komponen laba berjalan (belum ditutup) — dari P&L
    components.append({
        "code": "__pl__", "name": "Laba (Rugi) Periode Berjalan",
        "begin": round(begin_ce, 2), "movement": round(end_ce - begin_ce, 2), "end": round(end_ce, 2),
    })

    return {
        "period": {"start": start or "", "end": end or ""},
        "components": components,
        "begin_total": round(begin_total, 2),
        "movement_total": round(end_total - begin_total, 2),
        "end_total": round(end_total, 2),
        "net_income": round(end_ce - begin_ce, 2),
        "generated_at": now_iso(),
    }
