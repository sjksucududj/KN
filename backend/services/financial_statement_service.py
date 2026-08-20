"""FINANCE — Laporan Keuangan (Laba-Rugi & Neraca) diturunkan dari GL.

Dua laporan inti, semuanya DITURUNKAN dari `journal_entries` (status != void)
dan master `gl_accounts` — SSOT tunggal, tanpa data duplikat:

- **Laba-Rugi (Income Statement)** untuk periode [start, end]:
    Pendapatan  − Beban Pokok (HPP, kode 5)  = Laba Kotor
    Laba Kotor  − Beban Operasional (kode 6+) = Laba Bersih
- **Neraca (Balance Sheet)** per tanggal (as_of):
    Aset = Kewajiban + Ekuitas
    Ekuitas = akun ekuitas + Laba Tahun Berjalan (income − expense kumulatif s/d as_of).

Karena `cs-closing` (tutup buku) belum ada, "Laba Tahun Berjalan" = akumulasi
laba/rugi sejak awal s/d as_of. Ini membuat neraca SELALU seimbang (invarian
double-entry: Σdebit = Σkredit ⇒ Aset = Kewajiban + Ekuitas + Laba).

Scope entitas: fragmen filter `journal_entries.entity_id` disuntik caller (router),
sehingga buku terpisah per-PT (F0-E) dihormati.
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import now_iso

EPS = 0.005


def _day_start(d: Optional[str]) -> Optional[str]:
    if not d:
        return None
    return d if "T" in d else f"{d}T00:00:00"


def _day_end(d: Optional[str]) -> Optional[str]:
    if not d:
        return None
    return d if "T" in d else f"{d}T23:59:59.999999"


async def _accounts_map() -> Dict[str, Dict[str, Any]]:
    rows = await db.gl_accounts.find({}, {"_id": 0}).to_list(2000)
    return {a["code"]: a for a in rows}


async def _aggregate(scope: Optional[Dict[str, Any]],
                     date_filter: Optional[Dict[str, str]],
                     include_closing: bool = True) -> Dict[str, Dict[str, float]]:
    """Jumlahkan debit/credit per account_code dari jurnal (non-void, ter-scope).

    `include_closing=False` → kecualikan jurnal penutup (source_type="closing"),
    dipakai laporan Laba-Rugi agar angka operasional tetap stabil walau periode
    sudah ditutup. Neraca memakai default (include) agar Laba Ditahan mencerminkan
    hasil closing.
    """
    q: Dict[str, Any] = {"status": {"$ne": "void"}, **(scope or {})}
    if not include_closing:
        q["source_type"] = {"$ne": "closing"}
    if date_filter:
        q["date"] = date_filter
    entries = await db.journal_entries.find(q, {"_id": 0, "lines": 1}).to_list(100000)
    agg: Dict[str, Dict[str, float]] = {}
    for je in entries:
        for ln in je.get("lines", []):
            code = ln.get("account_code")
            if not code:
                continue
            a = agg.setdefault(code, {"debit": 0.0, "credit": 0.0})
            a["debit"] += float(ln.get("debit", 0) or 0)
            a["credit"] += float(ln.get("credit", 0) or 0)
    return agg


# ═════════════════════════════════════════════════════════════════════════════
#  LABA-RUGI (Income Statement)
# ═════════════════════════════════════════════════════════════════════════════

async def income_statement(start: Optional[str] = None, end: Optional[str] = None,
                           scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    amap = await _accounts_map()
    date_filter: Dict[str, str] = {}
    if start:
        date_filter["$gte"] = _day_start(start)
    if end:
        date_filter["$lte"] = _day_end(end)
    agg = await _aggregate(scope, date_filter or None, include_closing=False)

    revenue_lines: List[Dict[str, Any]] = []
    cogs_lines: List[Dict[str, Any]] = []
    opex_lines: List[Dict[str, Any]] = []

    for code, v in agg.items():
        acc = amap.get(code, {})
        atype = acc.get("type", "")
        name = acc.get("name", code)
        if atype == "income":
            amount = round(v["credit"] - v["debit"], 2)  # normal credit
            if abs(amount) > EPS:
                revenue_lines.append({"code": code, "name": name, "amount": amount})
        elif atype == "expense":
            amount = round(v["debit"] - v["credit"], 2)  # normal debit
            if abs(amount) > EPS:
                target = cogs_lines if code.startswith("5") else opex_lines
                target.append({"code": code, "name": name, "amount": amount})

    for arr in (revenue_lines, cogs_lines, opex_lines):
        arr.sort(key=lambda x: x["code"])

    revenue_total = round(sum(l["amount"] for l in revenue_lines), 2)
    cogs_total = round(sum(l["amount"] for l in cogs_lines), 2)
    opex_total = round(sum(l["amount"] for l in opex_lines), 2)
    gross_profit = round(revenue_total - cogs_total, 2)
    operating_profit = round(gross_profit - opex_total, 2)
    net_income = operating_profit  # tanpa pos luar-biasa terpisah (disederhanakan)

    return {
        "period": {"start": start or "", "end": end or ""},
        "sections": [
            {"key": "revenue", "label": "Pendapatan", "lines": revenue_lines, "total": revenue_total},
            {"key": "cogs", "label": "Beban Pokok Penjualan (HPP)", "lines": cogs_lines, "total": cogs_total},
            {"key": "opex", "label": "Beban Operasional", "lines": opex_lines, "total": opex_total},
        ],
        "revenue_total": revenue_total,
        "cogs_total": cogs_total,
        "gross_profit": gross_profit,
        "gross_margin": round(gross_profit / revenue_total * 100, 1) if revenue_total > EPS else 0.0,
        "opex_total": opex_total,
        "operating_profit": operating_profit,
        "net_income": net_income,
        "net_margin": round(net_income / revenue_total * 100, 1) if revenue_total > EPS else 0.0,
        "generated_at": now_iso(),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  NERACA (Balance Sheet)
# ═════════════════════════════════════════════════════════════════════════════

def _asset_group(code: str):
    if code.startswith("1-1"):
        return ("current", "Aset Lancar")
    if code.startswith("1-2"):
        return ("fixed", "Aset Tetap")
    return ("other", "Aset Lainnya")


def _liab_group(code: str):
    if code.startswith("2-1"):
        return ("current", "Kewajiban Lancar")
    return ("other", "Kewajiban Lainnya")


def _net(agg: Dict[str, Dict[str, float]], code: str):
    """Kembalikan (debit_net, credit_net) untuk `code` dari agregat (default 0)."""
    v = agg.get(code, {"debit": 0.0, "credit": 0.0})
    return round(v["debit"] - v["credit"], 2), round(v["credit"] - v["debit"], 2)


def _grouped_sections(items_by_group: Dict[str, List[Dict[str, Any]]],
                      order: List, comparative: bool = False) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    for key, label in order:
        lines = items_by_group.get(key, [])
        lines.sort(key=lambda x: x["code"])
        total = round(sum(l["amount"] for l in lines), 2)
        sec: Dict[str, Any] = {"key": key, "label": label, "lines": lines, "total": total}
        if comparative:
            compare_total = round(sum(l.get("compare_amount", 0.0) for l in lines), 2)
            sec["compare_total"] = compare_total
            sec["delta"] = round(total - compare_total, 2)
        sections.append(sec)
    return [s for s in sections if s["lines"] or s["total"] or s.get("compare_total")]


async def balance_sheet(as_of: Optional[str] = None,
                        compare_as_of: Optional[str] = None,
                        scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Neraca (Balance Sheet) posisi per tanggal `as_of`.

    Bila `compare_as_of` diisi → mode COMPARATIVE: tiap baris & total memuat
    `compare_amount` (posisi pada tanggal pembanding) + `delta` (perubahan).
    Kode akun digabung (union) dari kedua snapshot agar tidak ada baris hilang.
    """
    amap = await _accounts_map()
    agg_main = await _aggregate(scope, {"$lte": _day_end(as_of)} if as_of else None)
    comparative = bool(compare_as_of)
    agg_cmp: Dict[str, Dict[str, float]] = (
        await _aggregate(scope, {"$lte": _day_end(compare_as_of)}) if comparative else {}
    )

    codes = set(agg_main) | set(agg_cmp)

    asset_groups: Dict[str, List[Dict[str, Any]]] = {}
    liab_groups: Dict[str, List[Dict[str, Any]]] = {}
    equity_lines: List[Dict[str, Any]] = []
    income_net = expense_net = 0.0          # periode utama
    income_net_c = expense_net_c = 0.0      # periode pembanding

    def _mk_line(code: str, name: str, amount: float, amount_c: float) -> Dict[str, Any]:
        line = {"code": code, "name": name, "amount": amount}
        if comparative:
            line["compare_amount"] = amount_c
            line["delta"] = round(amount - amount_c, 2)
        return line

    for code in codes:
        acc = amap.get(code, {})
        atype = acc.get("type", "")
        name = acc.get("name", code)
        d_net, c_net = _net(agg_main, code)
        d_net_c, c_net_c = _net(agg_cmp, code)
        if atype == "asset":
            if abs(d_net) > EPS or abs(d_net_c) > EPS:
                gk, _lbl = _asset_group(code)
                asset_groups.setdefault(gk, []).append(_mk_line(code, name, d_net, d_net_c))
        elif atype == "liability":
            if abs(c_net) > EPS or abs(c_net_c) > EPS:
                gk, _lbl = _liab_group(code)
                liab_groups.setdefault(gk, []).append(_mk_line(code, name, c_net, c_net_c))
        elif atype == "equity":
            if abs(c_net) > EPS or abs(c_net_c) > EPS:
                equity_lines.append(_mk_line(code, name, c_net, c_net_c))
        elif atype == "income":
            income_net += c_net
            income_net_c += c_net_c
        elif atype == "expense":
            expense_net += d_net
            expense_net_c += d_net_c

    current_earnings = round(income_net - expense_net, 2)
    current_earnings_c = round(income_net_c - expense_net_c, 2)
    equity_lines.sort(key=lambda x: x["code"])

    asset_order = [("current", "Aset Lancar"), ("fixed", "Aset Tetap"), ("other", "Aset Lainnya")]
    liab_order = [("current", "Kewajiban Lancar"), ("other", "Kewajiban Lainnya")]
    asset_sections = _grouped_sections(asset_groups, asset_order, comparative)
    liab_sections = _grouped_sections(liab_groups, liab_order, comparative)

    assets_total = round(sum(s["total"] for s in asset_sections), 2)
    liabilities_total = round(sum(s["total"] for s in liab_sections), 2)
    equity_accounts_total = round(sum(l["amount"] for l in equity_lines), 2)
    equity_total = round(equity_accounts_total + current_earnings, 2)
    liabilities_equity_total = round(liabilities_total + equity_total, 2)

    result: Dict[str, Any] = {
        "as_of": as_of or now_iso()[:10],
        "comparative": comparative,
        "compare_as_of": compare_as_of or "",
        "assets": {"sections": asset_sections, "total": assets_total},
        "liabilities": {"sections": liab_sections, "total": liabilities_total},
        "equity": {
            "lines": equity_lines,
            "accounts_total": equity_accounts_total,
            "current_earnings": current_earnings,
            "total": equity_total,
        },
        "assets_total": assets_total,
        "liabilities_total": liabilities_total,
        "equity_total": equity_total,
        "liabilities_equity_total": liabilities_equity_total,
        "balanced": abs(assets_total - liabilities_equity_total) < 0.5,
        "generated_at": now_iso(),
    }

    if comparative:
        assets_total_c = round(sum(s.get("compare_total", 0.0) for s in asset_sections), 2)
        liabilities_total_c = round(sum(s.get("compare_total", 0.0) for s in liab_sections), 2)
        equity_accounts_total_c = round(sum(l.get("compare_amount", 0.0) for l in equity_lines), 2)
        equity_total_c = round(equity_accounts_total_c + current_earnings_c, 2)
        liabilities_equity_total_c = round(liabilities_total_c + equity_total_c, 2)
        result["equity"]["compare_accounts_total"] = equity_accounts_total_c
        result["equity"]["compare_current_earnings"] = current_earnings_c
        result["equity"]["compare_total"] = equity_total_c
        result["equity"]["delta_total"] = round(equity_total - equity_total_c, 2)
        result["compare"] = {
            "assets_total": assets_total_c,
            "liabilities_total": liabilities_total_c,
            "equity_total": equity_total_c,
            "liabilities_equity_total": liabilities_equity_total_c,
            "balanced": abs(assets_total_c - liabilities_equity_total_c) < 0.5,
        }
        result["delta"] = {
            "assets_total": round(assets_total - assets_total_c, 2),
            "liabilities_total": round(liabilities_total - liabilities_total_c, 2),
            "equity_total": round(equity_total - equity_total_c, 2),
        }

    return result
