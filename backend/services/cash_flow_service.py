"""FINANCE — Laporan Arus Kas (Cash Flow Statement) metode TAK LANGSUNG.

Diturunkan sepenuhnya dari `journal_entries` (SSOT double-entry), konsisten dgn
Laba-Rugi & Neraca. Prinsip identitas kas:

    ΔKas = -Δ(Aset non-kas) + Δ(Kewajiban) + Δ(Ekuitas + Laba/Rugi P&L)

Karena setiap jurnal seimbang (Σdebit = Σkredit), untuk SETIAP akun non-kas
kontribusi kas = -(Δ(debit−credit)) dan totalnya PASTI = Δ saldo kas. Jurnal
penutup (source_type="closing") DIKECUALIKAN (tak menyentuh kas; menjaga label
Laba bersih tetap operasional & ekuitas hanya gerakan modal riil).

Klasifikasi:
- Operasi   : Laba bersih (akun P&L) + perubahan modal kerja (aset lancar
              non-kas 1-1xxx & kewajiban lancar 2-1xxx).
- Investasi : perubahan aset tetap/non-lancar (1-2xxx dst).
- Pendanaan : perubahan ekuitas (3-xxxx) + kewajiban jangka panjang (2-2xxx+).
"""
from typing import Any, Dict, List, Optional

from core_utils import now_iso
from services import financial_statement_service as fs

EPS = 0.005
CASH_CODES = {"1-1100", "1-1110"}  # Kas Besar/Bank + Kas Kecil (kas & setara kas)


def _is_cash(code: str) -> bool:
    return code in CASH_CODES


def _raw(agg: Dict[str, Dict[str, float]], code: str) -> float:
    v = agg.get(code, {"debit": 0.0, "credit": 0.0})
    return float(v.get("debit", 0) or 0) - float(v.get("credit", 0) or 0)


async def cash_flow_statement(start: Optional[str] = None, end: Optional[str] = None,
                              scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    amap = await fs._accounts_map()

    begin_agg: Dict[str, Dict[str, float]] = {}
    if start:
        begin_agg = await fs._aggregate(scope, {"$lt": fs._day_start(start)}, include_closing=False)
    end_filter = {"$lte": fs._day_end(end)} if end else None
    end_agg = await fs._aggregate(scope, end_filter, include_closing=False)

    codes = set(begin_agg) | set(end_agg)

    operating_wc: List[Dict[str, Any]] = []
    investing: List[Dict[str, Any]] = []
    financing: List[Dict[str, Any]] = []
    net_income = 0.0
    begin_cash = 0.0
    end_cash = 0.0

    for code in codes:
        acc = amap.get(code, {})
        atype = acc.get("type", "")
        name = acc.get("name", code)
        d_raw = _raw(end_agg, code) - _raw(begin_agg, code)
        cash_effect = round(-d_raw, 2)

        if _is_cash(code):
            begin_cash += _raw(begin_agg, code)
            end_cash += _raw(end_agg, code)
            continue

        if abs(cash_effect) <= EPS:
            continue

        line = {"code": code, "name": name, "amount": cash_effect}
        if atype in ("income", "expense"):
            net_income = round(net_income + cash_effect, 2)
        elif atype == "asset":
            if code.startswith("1-2"):
                investing.append(line)
            else:
                operating_wc.append(line)
        elif atype == "liability":
            if code.startswith("2-1"):
                operating_wc.append(line)
            else:
                financing.append(line)
        elif atype == "equity":
            financing.append(line)

    for arr in (operating_wc, investing, financing):
        arr.sort(key=lambda x: x["code"])

    wc_total = round(sum(l["amount"] for l in operating_wc), 2)
    operating_total = round(net_income + wc_total, 2)
    investing_total = round(sum(l["amount"] for l in investing), 2)
    financing_total = round(sum(l["amount"] for l in financing), 2)
    net_change = round(operating_total + investing_total + financing_total, 2)
    end_cash_r = round(end_cash, 2)
    begin_cash_r = round(begin_cash, 2)
    computed_end = round(begin_cash_r + net_change, 2)

    return {
        "period": {"start": start or "", "end": end or ""},
        "operating": {
            "label": "Arus Kas dari Aktivitas Operasi",
            "net_income": net_income,
            "net_income_label": "Laba bersih (basis akrual)",
            "working_capital": operating_wc,
            "total": operating_total,
        },
        "investing": {
            "label": "Arus Kas dari Aktivitas Investasi",
            "lines": investing,
            "total": investing_total,
        },
        "financing": {
            "label": "Arus Kas dari Aktivitas Pendanaan",
            "lines": financing,
            "total": financing_total,
        },
        "net_change": net_change,
        "begin_cash": begin_cash_r,
        "end_cash": computed_end,
        "end_cash_actual": end_cash_r,
        "reconciled": abs(computed_end - end_cash_r) < 0.5,
        "generated_at": now_iso(),
    }
