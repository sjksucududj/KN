"""EPIC 1 — Agregasi Home/landing per role (Control Tower / Performa Saya).

Reuse service existing (sales_force, customer credit, reorder, approvals).
Payload SALES sengaja TANPA biaya/HPP (role tightening EPIC 1).
"""
from calendar import monthrange
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db import db
from services import sales_force_service as sf
from services.customer_service import (
    compute_customer_credit,
    _order_grand_total,
    DEAD_STATUSES,
)
from services.purchase_requisition_service import reorder_suggestions


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _today_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _month_progress() -> tuple:
    now = datetime.now(timezone.utc)
    return now.day, monthrange(now.year, now.month)[1]


async def sales_home(sales_id: str, entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Performa Saya — komisi MTD (akrual+proyeksi), target & capaian, customer+kredit,
    penagihan, order terbaru. TANPA biaya/HPP."""
    period = _current_month()
    comm = await sf.compute_commission(sales_id, period, entity_id)
    kpi = comm["kpi"]
    history = await sf.commission_history(sales_id, "month", period, 6, entity_id)

    day, dim = _month_progress()
    projection = round(comm["total_incentive"] / day * dim, 2) if day else comm["total_incentive"]

    # Customer saya + kredit
    cust_filter: Dict[str, Any] = {"assigned_sales_id": sales_id}
    if entity_id and entity_id != "all":
        cust_filter["entity_id"] = entity_id
    customers = await db.customers.find(cust_filter, {"_id": 0}).to_list(2000)
    cust_rows: List[Dict[str, Any]] = []
    for c in customers:
        cc = await compute_customer_credit(c)
        cust_rows.append({
            "id": c["id"], "name": c.get("name", ""),
            "credit_limit": cc["credit_limit"], "ar_outstanding": cc["ar_outstanding"],
            "overdue_amount": cc["overdue_amount"], "status": cc["status"],
        })
    cust_rows.sort(key=lambda r: r["overdue_amount"], reverse=True)
    collections = [r for r in cust_rows if r["overdue_amount"] > 0][:8]

    # Order terbaru (tanpa biaya)
    recent_orders: List[Dict[str, Any]] = []
    cust_ids = [c["id"] for c in customers]
    if cust_ids:
        cmap = {c["id"]: c.get("name", "") for c in customers}
        raw = await db.sales_orders.find(
            {"customer_id": {"$in": cust_ids}}, {"_id": 0}
        ).sort("created_at", -1).to_list(8)
        for o in raw:
            recent_orders.append({
                "id": o.get("id"), "number": o.get("number"),
                "customer_name": cmap.get(o.get("customer_id"), ""),
                "grand_total": _order_grand_total(o),
                "status": o.get("status"), "payment_status": o.get("payment_status"),
                "created_at": o.get("created_at"),
            })

    return {
        "period": period,
        "commission": {
            "mtd_accrual": comm["total_incentive"],
            "projection_month_end": projection,
            "projection_full": comm.get("projection_full", comm["total_incentive"]),
            "strategy": comm.get("strategy", "per_sku"),
            "breakdown": comm.get("breakdown", []),
            "base_amount": comm["base_amount"],
            "applied_rate": comm["applied_rate"],
            "bonus_new_customer": comm["bonus_new_customer"],
        },
        "target": {"amount": comm["target_amount"], "achievement_pct": comm["achievement_pct"]},
        "kpi": {
            "total_sales": kpi["total_sales"],
            "total_collected": kpi["total_collected"],
            "collection_rate": kpi["collection_rate"],
            "ar_outstanding": kpi["ar_outstanding"],
            "overdue_amount": kpi["overdue_amount"],
            "orders_count": kpi["orders_count"],
            "customers_count": kpi["customers_count"],
            "new_customers": kpi["new_customers"],
            "avg_order_value": kpi["avg_order_value"],
        },
        "history": history,
        "customers": cust_rows[:10],
        "collections": collections,
        "recent_orders": recent_orders,
    }


async def manager_home(period: Optional[str] = None, entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Manager Home (Dasbor Manajer) — tiga pertanyaan manajer setiap pagi:

    1. **Apa yang menunggu tanda tangan saya?** → antrean persetujuan, dirinci per jenis.
    2. **Tim saya di mana posisinya?** → target vs capaian + papan peringkat.
    3. **Apa yang sudah TERLAMBAT hari ini?** → piutang lewat tempo, round R&D lewat
       tenggat, tugas gudang tertunda, work order mandek.

    Semua angka dihitung dari data nyata; tidak ada satu pun yang diketik manual.
    """
    period = period or _current_month()
    board = await sf.leaderboard(period, entity_id)
    totals = {
        "total_sales": round(sum(r["total_sales"] for r in board), 2),
        "total_collected": round(sum(r["total_collected"] for r in board), 2),
        "ar_outstanding": round(sum(r["ar_outstanding"] for r in board), 2),
        "overdue_amount": round(sum(r["overdue_amount"] for r in board), 2),
    }
    target_total = 0.0
    team: List[Dict[str, Any]] = []
    for r in board:
        tgt = await sf._target_collection_for(r["sales_id"], period)  # noqa: SLF001
        target_total += tgt
        team.append({
            **r,
            "target_collection": round(tgt, 2),
            "achievement_pct": (round(r["total_collected"] / tgt * 100, 1) if tgt else None),
        })
    achievement = round(totals["total_collected"] / target_total * 100, 2) if target_total else 0
    # SATU sumber angka: KPI & daftar rincian dihitung sekali (dulu dua sumber → 0 vs 6).
    approvals = await approval_backlog(entity_id)
    day, days_in_month = _month_progress()
    return {
        "period": period,
        "leaderboard": board,
        "team": team,
        "totals": totals,
        "target": {"amount": round(target_total, 2), "achievement_pct": achievement,
                   "month_progress_pct": round(day / days_in_month * 100, 1),
                   "day": day, "days_in_month": days_in_month},
        "approvals_pending": approvals["total"],
        "approvals": approvals,
        "late_today": await _late_today(entity_id, totals["overdue_amount"]),
        "designers": await _designer_snapshot(entity_id),
    }


# ─── Dasbor Manajer: potongan-potongan yang bisa ditindak ────────────────────
def _scope(entity_id: Optional[str]) -> Dict[str, Any]:
    return {"entity_id": entity_id} if entity_id and entity_id != "all" else {}


async def approval_backlog(entity_id: Optional[str]) -> Dict[str, Any]:
    """Antrean persetujuan NYATA — definisinya tinggal di SATU tempat.

    CACAT YANG DITUTUP (terukur 2026-08-15, ditemukan lewat audit peran): KPI beranda
    "Persetujuan Menunggu" memakai `approval_service.get_pending_approvals_count()`
    yang menghitung koleksi `approval_requests` — koleksi yang TIDAK PERNAH diisi
    siapa pun (`create_approval_request()` nol pemanggil). Angkanya SELALU 0 sementara
    daftar rincian di layar yang sama berbunyi 6 dan kenyataan di basis data 16.
    Orang yang pekerjaannya menyetujui membaca "0" lalu pulang.

    Definisinya sekarang di `services/approval_backlog_service.py` supaya KPI beranda,
    rincian beranda, DAN ringkasan Pusat Persetujuan membaca sumber yang sama
    (dijaga INV-HOME-01).
    """
    from services import approval_backlog_service as abl
    # `with_oldest` — beranda tidak hanya butuh ANGKA: yang membuat orang bertindak
    # adalah "PO-00010 · menunggu 12 hari" (kartu "Paling Lama Menunggu").
    return await abl.backlog(entity_id, with_oldest=True, oldest_limit=5)


async def _late_today(entity_id: Optional[str], ar_overdue: float = 0.0) -> Dict[str, Any]:
    """Keterlambatan yang BERJALAN hari ini — dari empat sumber yang paling sering macet."""
    from datetime import timedelta

    from services import rnd_sla_service as rnd_sla

    scope = _scope(entity_id)
    now = datetime.now(timezone.utc)
    d2 = (now - timedelta(days=2)).isoformat()
    d3 = (now - timedelta(days=3)).isoformat()

    rnd_board = await rnd_sla.board(dict(scope), entity_id=entity_id or "")
    wms_stalled = await db.wms_tasks.count_documents({
        **scope, "status": {"$nin": ["completed", "cancelled", "dispatched"]},
        "created_at": {"$lt": d2}})
    wo_stalled = await db.mfg_work_orders.count_documents({
        **scope, "status": "released", "released_at": {"$lt": d3}})

    rows = [
        {"key": "ar", "label": "Piutang lewat jatuh tempo", "view": "ar-aging",
         "count": None, "amount": round(float(ar_overdue or 0), 2),
         "hint": "Tagih pelanggan atau ajukan rencana bayar"},
        {"key": "rnd", "label": "Round sample R&D lewat tenggat", "view": "designer-kpi",
         "count": int(rnd_board.get("count") or 0), "amount": None,
         "hint": (f"{rnd_board.get('admin_count') or 0} sudah dinaikkan ke admin · "
                  f"terlama {rnd_board.get('worst_days_late') or 0} hari")},
        {"key": "wms", "label": "Tugas gudang terbuka > 2 hari", "view": "operations",
         "count": int(wms_stalled), "amount": None,
         "hint": "Barang masuk/keluar belum diselesaikan petugas"},
        {"key": "production", "label": "Perintah Kerja dirilis > 3 hari", "view": "production",
         "count": int(wo_stalled), "amount": None,
         "hint": "Produksi berjalan lebih lama dari rencana"},
    ]
    total = sum(int(r["count"] or 0) for r in rows)
    return {"total_items": total,
            "ar_overdue_amount": round(float(ar_overdue or 0), 2),
            "rnd_overdue": int(rnd_board.get("count") or 0),
            "rnd_escalated_admin": int(rnd_board.get("admin_count") or 0),
            "wms_stalled": int(wms_stalled), "wo_stalled": int(wo_stalled),
            "rows": [r for r in rows if (r["count"] or 0) > 0 or (r["amount"] or 0) > 0],
            "all_rows": rows}


async def _designer_snapshot(entity_id: Optional[str]) -> Dict[str, Any]:
    """Cuplikan kinerja desainer 30 hari (PS-18) — manajer MD memimpin divisi ini."""
    from services import rnd_kpi_service as rnd_kpi

    rep = await rnd_kpi.designer_kpi(_scope(entity_id), period="30d",
                                     entity_id=entity_id or "")
    return {
        "period_label": rep["period_label"],
        "count": rep["count"],
        "summary": rep["summary"],
        "top": [{"designer": r["designer"], "rank": r["rank"],
                 "grade_letter": r["grade_letter"], "grade_score": r["grade_score"],
                 "on_time_pct": r["on_time_pct"], "rework_pct": r["rework_pct"],
                 "late_total": r["late_total"], "overdue_now": r["overdue_now"]}
                for r in rep["items"][:5]],
    }


async def admin_home(entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Admin Control Tower — penjualan hari/MTD, AR aging ringkas, approval pending,
    low-stock/reorder, ringkasan payout insentif."""
    period = _current_month()
    board = await sf.leaderboard(period, entity_id)

    sales_mtd = round(sum(r["total_sales"] for r in board), 2)
    collected_mtd = round(sum(r["total_collected"] for r in board), 2)
    ar_total = round(sum(r["ar_outstanding"] for r in board), 2)
    overdue_total = round(sum(r["overdue_amount"] for r in board), 2)

    # Penjualan hari ini
    scope: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        scope["entity_id"] = entity_id
    today_orders = await db.sales_orders.find(
        {**scope, "created_at": {"$regex": f"^{_today_prefix()}"}}, {"_id": 0}
    ).to_list(4000)
    live_today = [o for o in today_orders if o.get("status") not in DEAD_STATUSES]
    today_sales = round(sum(_order_grand_total(o) for o in live_today), 2)

    # KPI "Persetujuan Menunggu" di Control Tower memakai antrean NYATA yang sama
    # dengan Beranda Manajer, plus rinciannya supaya bisa diklik ke tempat kerjanya
    # (dulu: satu angka dari koleksi generik yang tak pernah terisi → selalu 0).
    approvals = await approval_backlog(entity_id)

    reorder = await reorder_suggestions(entity_id)
    reorder_items = reorder.get("items", [])

    payout = 0.0
    for r in board:
        c = await sf.compute_commission(r["sales_id"], period, entity_id)
        payout += c["total_incentive"]

    top_overdue = sorted(board, key=lambda r: r["overdue_amount"], reverse=True)[:5]

    return {
        "period": period,
        "sales": {
            "today": today_sales, "today_orders": len(live_today),
            "mtd": sales_mtd, "collected_mtd": collected_mtd,
        },
        "ar": {"outstanding": ar_total, "overdue": overdue_total},
        "approvals_pending": approvals["total"],
        "approvals": approvals,
        "low_stock": {"count": len(reorder_items), "items": reorder_items[:8]},
        "incentive_payout": round(payout, 2),
        "leaderboard_top": board[:5],
        "top_overdue": [
            {"sales_name": r.get("sales_name", ""), "overdue_amount": r["overdue_amount"],
             "ar_outstanding": r["ar_outstanding"]}
            for r in top_overdue
        ],
    }
