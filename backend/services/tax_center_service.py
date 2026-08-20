"""EPIC 7 — Pusat Pajak (PPN + PPh) service.

Agregasi pajak read-mostly, ENTITY-AWARE & CONFIGURABLE:
- PPN (SPT Masa): reuse `input_tax_service.vat_summary` (Keluaran − Masukan → posisi
  kurang/lebih bayar). Hanya bermakna utk entitas PKP (default_tax_mode='ppn').
- PPh: butir configurable dari `settings.tax.pph_items` (config_service). Tiap butir
  punya `basis`:
    * payroll → otomatis dari `hr_payroll_runs.totals.pph21` (periode+entitas)
    * omzet   → rate% × peredaran bruto (sales_orders periode+entitas)
    * manual  → rate% × DPP yang direkam user (`tax_pph_records`)

Aturan emas: PKP/non-PKP mengikuti konfigurasi ENTITAS (business_entities.default_tax_mode),
di-resolve via config_service.get_effective_settings (sudah men-set tax.is_pkp & ppn_rate=0
utk non-PKP). PPh berlaku lintas PKP/non-PKP (PPh ≠ PPN).
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import now_iso, new_id
from services.config_service import get_effective_settings
from services import input_tax_service

PPH_RECORDS = "tax_pph_records"
_PAYROLL_STATUSES = ["approved", "posted", "paid"]
_ACTIVE_SO_EXCLUDE = {"cancelled", "draft", "rejected"}


def _cur_month() -> str:
    return now_iso()[:7]


def _ent_q(entity_id: Optional[str]) -> Dict[str, Any]:
    return {"entity_id": entity_id} if entity_id and entity_id != "all" else {}


async def list_periods(entity_id: Optional[str]) -> List[str]:
    """Union periode dari faktur keluaran/masukan, payroll, rekam PPh, + bulan berjalan."""
    eq = _ent_q(entity_id)
    out_dates = await db.tax_invoices.distinct("faktur_date", eq)
    in_dates = await db.tax_invoices_in.distinct("faktur_date", eq)
    pay_periods = await db.hr_payroll_runs.distinct("period", eq)
    pph_periods = await db.tax_pph_records.distinct("period", eq)
    months = {(d or "")[:7] for d in out_dates if d} | {(d or "")[:7] for d in in_dates if d}
    months |= {p for p in pay_periods if p} | {p for p in pph_periods if p}
    months.add(_cur_month())
    return sorted({m for m in months if m}, reverse=True)


async def _period_pph21(entity_id: Optional[str], period: str) -> Dict[str, float]:
    """PPh 21 aktual dari payroll run (periode+entitas). dpp=gross, amount=pph21."""
    q = {**_ent_q(entity_id), "period": period, "status": {"$in": _PAYROLL_STATUSES}}
    runs = await db.hr_payroll_runs.find(q, {"_id": 0, "totals": 1}).to_list(1000)
    gross = sum(float((r.get("totals") or {}).get("gross") or 0) for r in runs)
    pph = sum(float((r.get("totals") or {}).get("pph21") or 0) for r in runs)
    return {"dpp": round(gross, 2), "amount": round(pph, 2), "count": len(runs)}


async def _period_omzet(entity_id: Optional[str], period: str) -> float:
    """Peredaran bruto (omzet) periode dari sales_orders (net_subtotal, fallback total)."""
    q = _ent_q(entity_id)
    total = 0.0
    async for so in db.sales_orders.find(
        q, {"_id": 0, "net_subtotal": 1, "total_amount": 1, "grand_total": 1,
            "created_at": 1, "order_date": 1, "status": 1}):
        d = (so.get("order_date") or so.get("created_at") or "")[:7]
        if d != period:
            continue
        if (so.get("status") or "") in _ACTIVE_SO_EXCLUDE:
            continue
        total += float(so.get("net_subtotal") or so.get("total_amount") or so.get("grand_total") or 0)
    return round(total, 2)


async def _pph_records(entity_id: Optional[str], period: str) -> Dict[str, Dict[str, Any]]:
    q = {**_ent_q(entity_id), "period": period}
    rows = await db.tax_pph_records.find(q, {"_id": 0}).to_list(2000)
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        code = r.get("code") or ""
        acc = out.setdefault(code, {"dpp": 0.0, "records": []})
        acc["dpp"] = round(acc["dpp"] + float(r.get("dpp") or 0), 2)
        acc["records"].append(r)
    return out


async def compute_pph(entity_id: Optional[str], period: str,
                      pph_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Hitung tiap butir PPh enabled sesuai basis. Return {items, total}."""
    records = await _pph_records(entity_id, period)
    items: List[Dict[str, Any]] = []
    total = 0.0
    for cfg in pph_items or []:
        if not cfg.get("enabled", True):
            continue
        code = cfg.get("code") or ""
        basis = (cfg.get("basis") or "manual").lower()
        rate = float(cfg.get("rate") or 0)
        dpp = 0.0
        amount = 0.0
        source = ""
        if basis == "payroll":
            p21 = await _period_pph21(entity_id, period)
            dpp, amount = p21["dpp"], p21["amount"]
            source = f"{p21['count']} payroll run (PPh21 aktual/TER)"
        elif basis == "omzet":
            dpp = await _period_omzet(entity_id, period)
            amount = round(dpp * rate / 100.0, 2)
            source = "Peredaran bruto (sales orders)"
        else:  # manual
            rec = records.get(code, {"dpp": 0.0, "records": []})
            dpp = round(float(rec["dpp"]), 2)
            amount = round(dpp * rate / 100.0, 2)
            source = f"{len(rec.get('records', []))} rekaman manual"
        total += amount
        items.append({
            "code": code, "name": cfg.get("name") or code,
            "basis": basis, "rate": rate,
            "dpp": round(dpp, 2), "amount": round(amount, 2),
            "source": source, "editable": basis == "manual",
        })
    return {"items": items, "total": round(total, 2)}


async def tax_summary(entity_id: Optional[str], period: Optional[str]) -> Dict[str, Any]:
    periods = await list_periods(entity_id)
    sel = period if (period and period in periods) else (periods[0] if periods else _cur_month())

    settings = await get_effective_settings(entity_id)
    tax_cfg = settings.get("tax", {}) or {}
    is_pkp = bool(tax_cfg.get("is_pkp", True))

    # Entity meta
    entity_meta: Dict[str, Any] = {"id": entity_id or "all", "name": "Semua Entitas",
                                   "npwp": "", "tax_mode": "ppn" if is_pkp else "non_ppn",
                                   "is_pkp": is_pkp}
    if entity_id and entity_id != "all":
        ent = await db.business_entities.find_one({"id": entity_id}, {"_id": 0})
        if ent:
            entity_meta = {
                "id": ent.get("id"), "name": ent.get("legal_name") or ent.get("short_name") or ent.get("id"),
                "npwp": ent.get("npwp", ""), "tax_mode": ent.get("default_tax_mode", "non_ppn"),
                "is_pkp": ent.get("default_tax_mode") == "ppn",
            }
            is_pkp = entity_meta["is_pkp"]

    # PPN (SPT Masa) — hanya bermakna utk PKP
    ppn = await input_tax_service.vat_summary(period=sel, entity_id=entity_id or "")
    ppn["applicable"] = is_pkp

    # PPh — configurable
    pph = await compute_pph(entity_id, sel, tax_cfg.get("pph_items", []))

    return {
        "period": sel,
        "periods": periods,
        "entity": entity_meta,
        "config": {
            "ppn_rate": float(tax_cfg.get("ppn_rate", 0) or 0),
            "ppn_mode": tax_cfg.get("ppn_mode", "excluded"),
            "efaktur_enabled": bool(tax_cfg.get("efaktur_enabled", False)),
            "is_pkp": is_pkp,
            "pph_items": tax_cfg.get("pph_items", []),
        },
        "ppn": ppn,
        "pph": pph,
    }


# ── Manual PPh records (basis=manual) ────────────────────────────────────────

async def list_pph_records(entity_id: Optional[str], period: Optional[str] = None,
                           code: Optional[str] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {**_ent_q(entity_id)}
    if period:
        q["period"] = period
    if code:
        q["code"] = code
    return await db.tax_pph_records.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)


async def record_pph(entity_id: str, period: str, code: str, name: str,
                     rate: float, dpp: float, note: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    if not (entity_id and entity_id != "all"):
        raise ValueError("Pilih entitas spesifik untuk merekam PPh manual (bukan 'Semua Entitas').")
    if not period or len(period) != 7:
        raise ValueError("Periode harus format YYYY-MM.")
    dpp = round(float(dpp or 0), 2)
    amount = round(dpp * float(rate or 0) / 100.0, 2)
    doc = {
        "id": new_id("pphr"), "entity_id": entity_id, "period": period.strip(),
        "code": (code or "").strip(), "name": (name or code or "").strip(),
        "basis": "manual", "rate": float(rate or 0), "dpp": dpp, "amount": amount,
        "note": (note or "").strip(),
        "created_by": actor.get("name", "system"), "created_by_id": actor.get("id", ""),
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.tax_pph_records.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def delete_pph_record(record_id: str) -> bool:
    res = await db.tax_pph_records.delete_one({"id": record_id})
    return res.deleted_count > 0
