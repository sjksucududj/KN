"""M1 — Makloon service: Makloon 360 + scorecard proses (dari data nyata).

Data sumber (sebagian baru terisi mulai Fase M3):
- `makloon_orders` — order makloon (header + steps[]). Kosong sampai M3 → metrik 0/None.
- `vendor_bills` — tagihan jasa ber-`makloon_id` (kosong sampai M3).
- `process_recipes` — resep dgn `default_makloon_id` = makloon ini.

Didesain tahan-kosong (has_data=False) agar tetap valid sebelum transaksi ada.
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import now_iso, safe_doc


async def _makloon_orders_for(makloon_id: str) -> List[Dict[str, Any]]:
    return await db.makloon_orders.find(
        {"steps.makloon_id": makloon_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)


async def compute_makloon_scorecard(makloon_id: str) -> Optional[Dict[str, Any]]:
    """Scorecard proses makloon dari step order nyata (yield realisasi, on-time)."""
    mk = await db.makloons.find_one({"id": makloon_id}, {"_id": 0})
    if not mk:
        return None
    orders = await _makloon_orders_for(makloon_id)

    steps: List[Dict[str, Any]] = []
    for o in orders:
        for s in o.get("steps", []):
            if s.get("makloon_id") == makloon_id:
                steps.append(s)

    received = [s for s in steps if s.get("status") in ("received", "completed") and float(s.get("actual_output_qty", 0) or 0) > 0]
    total_input = sum(float(s.get("input_qty", 0) or 0) for s in received)
    total_output = sum(float(s.get("actual_output_qty", 0) or 0) for s in received)
    total_expected = sum(float(s.get("expected_output_qty", 0) or 0) for s in received)
    total_byproduct = sum(float(s.get("actual_byproduct_qty", 0) or 0) for s in received)
    total_service = sum(float(s.get("tariff", 0) or 0) for s in steps)

    realized_yield = round(total_output / total_input, 4) if total_input else None
    yield_attainment = round(total_output / total_expected, 4) if total_expected else None

    return {
        "makloon_id": makloon_id,
        "makloon_name": mk.get("name", ""),
        "makloon_code": mk.get("code", ""),
        "has_data": len(received) > 0,
        "metrics": {
            "total_orders": len(orders),
            "total_steps": len(steps),
            "received_steps": len(received),
            "total_input_qty": round(total_input, 3),
            "total_output_qty": round(total_output, 3),
            "total_byproduct_qty": round(total_byproduct, 3),
            "realized_yield": realized_yield,
            "yield_attainment": yield_attainment,
            "total_service_cost": round(total_service, 2),
        },
        "generated_at": now_iso(),
    }


async def makloon_360(makloon_id: str) -> Optional[Dict[str, Any]]:
    """Profil makloon + riwayat order + tagihan jasa + resep terhubung + scorecard +
    ringkasan keuangan (hutang jasa/AP) + daftar dokumen (SPK + tagihan)."""
    from datetime import datetime, timezone
    from services.vendor_bill_service import bill_financials  # hindari import melingkar

    mk = safe_doc(await db.makloons.find_one({"id": makloon_id}, {"_id": 0}))
    if not mk:
        return None
    orders = await _makloon_orders_for(makloon_id)
    bills = await db.vendor_bills.find({"makloon_id": makloon_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    recipes = await db.process_recipes.find(
        {"default_makloon_id": makloon_id, "status": "active"}, {"_id": 0}).sort("created_at", -1).to_list(200)
    scorecard = await compute_makloon_scorecard(makloon_id)

    now = datetime.now(timezone.utc)
    ap_outstanding = 0.0
    overdue_amount = 0.0
    overdue_days = 0
    bill_total = 0.0
    for b in bills:
        fin = bill_financials(b)
        out = float(fin.get("outstanding", 0) or 0)
        b["outstanding"] = out
        b["pay_status"] = fin.get("pay_status")
        b["grand_total"] = fin.get("grand_total", b.get("grand_total", 0))
        bill_total += float(b.get("grand_total", 0) or 0)
        status = (b.get("status") or "").lower()
        if status in {"posted", "paid"} and out > 0.01:
            ap_outstanding += out
            due = None
            dv = b.get("due_date")
            if dv:
                try:
                    due = datetime.fromisoformat(str(dv).replace("Z", "+00:00"))
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    due = None
            if due and due < now:
                overdue_amount += out
                overdue_days = max(overdue_days, (now - due).days)

    open_statuses = {"draft", "pending", "in_progress", "in_process", "processing", "diproses", "waiting", "partial", "sent", "issued"}
    open_orders = [o for o in orders if (o.get("status") or "").lower() in open_statuses]
    sc_metrics = (scorecard or {}).get("metrics", {}) if scorecard else {}

    mk["finance"] = {
        "service_ap_outstanding": round(ap_outstanding, 2),
        "overdue_amount": round(overdue_amount, 2),
        "overdue_days": overdue_days,
        "service_bill_total": round(bill_total, 2),
        "total_service_cost": sc_metrics.get("total_service_cost"),
        "open_order_count": len(open_orders),
        "default_tariff": mk.get("default_tariff"),
        "tariff_unit": mk.get("tariff_unit"),
        "lead_time_days": mk.get("lead_time_days") or 0,
    }

    documents: List[Dict[str, Any]] = []
    for o in orders:
        documents.append({
            "doc_type": "makloon_spk", "label": "SPK Makloon",
            "source_id": o.get("id"), "number": o.get("mko_number") or o.get("id"),
            "date": o.get("created_at"), "status": o.get("status"),
            "amount": float(o.get("total_tariff", o.get("grand_total", 0)) or 0), "entity_id": o.get("entity_id"),
        })
    for b in bills:
        documents.append({
            "doc_type": "vendor_bill", "label": "Tagihan Jasa",
            "source_id": b.get("id"), "number": b.get("bill_number") or b.get("id"),
            "date": b.get("created_at") or b.get("bill_date"), "status": b.get("status"),
            "amount": float(b.get("grand_total", 0) or 0), "entity_id": b.get("entity_id"),
        })
    documents.sort(key=lambda d: str(d.get("date") or ""), reverse=True)

    mk["orders"] = orders
    mk["order_count"] = len(orders)
    mk["service_bills"] = bills
    mk["bill_total"] = round(bill_total, 2)
    mk["bill_count"] = len(bills)
    mk["recipes"] = recipes
    mk["recipe_count"] = len(recipes)
    mk["documents"] = documents
    mk["scorecard"] = scorecard
    return mk
