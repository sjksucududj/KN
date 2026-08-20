"""R6.5 — Generator ALERT untuk Scheduler & Notifikasi (Kain Nusantara).

Semua alert dihitung dari DATA NYATA (TANPA mock):
- AR jatuh tempo    → `services/ar_aging_service.aging_report`
- AP jatuh tempo    → `vendor_bills` (posted) + term pembayaran supplier (`payment_terms`)
- Penyusutan aset   → `fin_fixed_assets` vs `fin_depreciation_entries` (periode tertinggal)
- Anggaran          → `services/budget_service.budget_vs_actual` (baris berstatus over/warning)
- Produksi          → `mfg_work_orders` dirilis/draft yang tertunda
- Operasi gudang    → `wms_tasks` outbound/inbound yang tertunda
- Event umum        → `services/notification_service.generate_system_notifications`

Setiap notifikasi ter-dedupe per (type, ref, **HARI**) → menjalankan job berulang
dalam hari yang sama TIDAK menduplikasi notifikasi (idempotent harian).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from db import db
from services.notification_service import create_notification, generate_system_notifications
from core_utils import rupiah

# Ambang batas default (dapat dioverride lewat pengaturan job di masa depan).
AP_DUE_SOON_DAYS = 7      # tagihan supplier yang jatuh tempo <= 7 hari → peringatan
WO_RELEASED_STALE_DAYS = 3  # WO dirilis > 3 hari belum selesai → tertunda
WO_DRAFT_STALE_DAYS = 7     # WO draft > 7 hari belum dirilis → tertunda
TASK_STALE_DAYS = 2         # tugas gudang terbuka > 2 hari → tertunda
MAX_ALERTS_PER_JOB = 40     # pagar anti-spam per job per run

TASK_OPEN_STATUSES = ["created", "pending", "picking", "packing", "qc_pending",
                      "waiting_goods", "receiving", "partially_shipped"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(iso: Any) -> Optional[datetime]:
    if isinstance(iso, datetime):
        return iso if iso.tzinfo else iso.replace(tzinfo=timezone.utc)
    if not iso or not isinstance(iso, str):
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _rp(v: Any) -> str:
    """Alias tipis ke `core_utils.rupiah` — satu sumber format uang untuk seluruh backend."""
    return rupiah(v)


def _period_prev_month() -> str:
    """Periode YYYY-MM bulan LALU (penyusutan biasanya dijalankan setelah tutup bulan)."""
    first_this = _now().replace(day=1)
    prev = first_this - timedelta(days=1)
    return prev.strftime("%Y-%m")


async def _active_entities() -> List[str]:
    ents = await db.business_entities.find(
        {"status": {"$ne": "inactive"}}, {"_id": 0, "id": 1}).to_list(50)
    return [e["id"] for e in ents if e.get("id")]


# ═══ JOB 1 — AR (piutang) jatuh tempo ════════════════════════════════════════
async def job_ar_overdue() -> Dict[str, Any]:
    from services.ar_aging_service import aging_report
    report = await aging_report()
    rows = [r for r in (report.get("customers") or []) if float(r.get("overdue", 0) or 0) > 0]
    rows.sort(key=lambda r: float(r.get("overdue", 0) or 0), reverse=True)
    created = 0
    for r in rows[:MAX_ALERTS_PER_JOB]:
        days = int(r.get("oldest_days", 0) or 0)
        overdue = float(r.get("overdue", 0) or 0)
        sev = "critical" if days > 30 else "warning"
        body = (f"{_rp(overdue)} lewat jatuh tempo (tertua {days} hari) dari "
                f"{r.get('orders', 0)} order. Segera tagih / follow-up.")
        note = await create_notification(
            notif_type="ar_overdue", ref=f"ar_overdue:{r.get('customer_id')}",
            title=f"Piutang jatuh tempo: {r.get('customer_name', '-')}",
            body=body, severity=sev, link="ar-aging", recipient_role="manager",
            dedupe_scope="day",
        )
        if note:
            created += 1
        # Salinan untuk sales pemegang akun (bila ada) agar bisa langsung follow-up.
        sid = r.get("assigned_sales_id") or ""
        if sid:
            note2 = await create_notification(
                notif_type="ar_overdue", ref=f"ar_overdue_sales:{r.get('customer_id')}",
                title=f"Tagih piutang: {r.get('customer_name', '-')}",
                body=body, severity=sev, link="ar-aging", recipient_role="sales",
                recipient_user=sid, dedupe_scope="day",
            )
            if note2:
                created += 1
    return {"created": created, "scanned": len(rows),
            "detail": f"{len(rows)} pelanggan overdue · total {_rp(report.get('totals', {}).get('overdue'))}"}


# ═══ JOB 2 — AP (hutang supplier) jatuh tempo ════════════════════════════════
async def _term_days_map(entity_id: str = "") -> Dict[str, int]:
    """Peta kode syarat bayar → net_days untuk SATU badan usaha.

    FASE E-4 (E4.3): syarat bayar berlapis (global + override badan usaha). Dulu
    fungsi ini membaca seluruh koleksi tanpa lapisan sehingga dua baris ber-kode
    sama saling menimpa secara acak — jatuh tempo AP bisa salah beberapa hari.
    """
    from services import entity_master_service as ems
    rows = await ems.effective_rows("payment-terms", entity_id)
    return {t.get("code", ""): int(t.get("net_days", 0) or 0) for t in rows if t.get("code")}


async def job_ap_due() -> Dict[str, Any]:
    bills = await db.vendor_bills.find(
        {"status": "posted"},
        {"_id": 0, "id": 1, "bill_number": 1, "bill_date": 1, "grand_total": 1,
         "supplier_id": 1, "supplier_name": 1, "entity_id": 1}).to_list(5000)
    if not bills:
        return {"created": 0, "scanned": 0, "detail": "tidak ada tagihan supplier terposting"}
    sup_ids = [b.get("supplier_id") for b in bills if b.get("supplier_id")]
    sups = await db.suppliers.find(
        {"id": {"$in": sup_ids}}, {"_id": 0, "id": 1, "payment_term_code": 1}).to_list(2000)
    sup_term = {s["id"]: s.get("payment_term_code", "") for s in sups}
    # Peta syarat bayar dihitung PER BADAN USAHA (baris global + override-nya).
    tmaps: Dict[str, Dict[str, int]] = {}
    now = _now()
    created, scanned = 0, 0
    for b in bills:
        bd = _parse(b.get("bill_date"))
        if not bd:
            continue
        ent = str(b.get("entity_id") or "")
        if ent not in tmaps:
            tmaps[ent] = await _term_days_map(ent)
        days = tmaps[ent].get(sup_term.get(b.get("supplier_id", ""), ""), 0)
        due = bd + timedelta(days=days)
        left = (due - now).days
        if left > AP_DUE_SOON_DAYS:
            continue
        scanned += 1
        if scanned > MAX_ALERTS_PER_JOB:
            break
        overdue = left < 0
        sev = "critical" if overdue else "warning"
        when = f"LEWAT {abs(left)} hari" if overdue else ("jatuh tempo HARI INI" if left == 0
                                                          else f"jatuh tempo {left} hari lagi")
        note = await create_notification(
            notif_type="ap_due", ref=f"ap_due:{b.get('id')}",
            title=f"Tagihan supplier {when}: {b.get('bill_number', '')}",
            body=(f"{b.get('supplier_name', '')} · {_rp(b.get('grand_total'))} · "
                  f"jatuh tempo {due.date().isoformat()} (term {days} hari)."),
            severity=sev, link="vendor-bills", entity_id=b.get("entity_id"),
            recipient_role="manager", dedupe_scope="day",
        )
        if note:
            created += 1
    return {"created": created, "scanned": scanned,
            "detail": f"{scanned} tagihan jatuh tempo <= {AP_DUE_SOON_DAYS} hari"}


# ═══ JOB 3 — Reminder penyusutan aset tetap ══════════════════════════════════
async def job_depreciation_due() -> Dict[str, Any]:
    period = _period_prev_month()
    assets = await db.fin_fixed_assets.find(
        {"status": "active"}, {"_id": 0, "id": 1, "number": 1, "name": 1,
                               "entity_id": 1, "monthly_depreciation": 1}).to_list(5000)
    if not assets:
        return {"created": 0, "scanned": 0, "detail": "belum ada aset tetap aktif"}
    done = await db.fin_depreciation_entries.find(
        {"period": period}, {"_id": 0, "asset_id": 1}).to_list(20000)
    done_ids = {d.get("asset_id") for d in done}
    pending = [a for a in assets if a.get("id") not in done_ids]
    if not pending:
        return {"created": 0, "scanned": len(assets),
                "detail": f"penyusutan periode {period} sudah lengkap"}
    total = sum(float(a.get("monthly_depreciation", 0) or 0) for a in pending)
    note = await create_notification(
        notif_type="depreciation_due", ref=f"dep_due:{period}",
        title=f"Penyusutan aset periode {period} belum dijalankan",
        body=(f"{len(pending)} aset aktif menunggu penyusutan (estimasi {_rp(total)}). "
              f"Buka Kas & Aset → Aset Tetap → Jalankan Penyusutan Bulanan."),
        severity="warning", link="fixed-assets", recipient_role="manager",
        dedupe_scope="day",
    )
    return {"created": 1 if note else 0, "scanned": len(assets),
            "detail": f"{len(pending)} aset menunggu periode {period}"}


# ═══ JOB 4 — Peringatan anggaran (over / mendekati batas) ════════════════════
async def job_budget_alert() -> Dict[str, Any]:
    from services import budget_service
    year = _now().year
    created, scanned = 0, 0
    for ent in await _active_entities():
        try:
            rep = await budget_service.budget_vs_actual({"entity_id": ent}, year, ent)
        except Exception:  # noqa: BLE001 — jangan gagalkan job karena 1 entitas
            continue
        for row in (rep.get("alerts") or []):
            scanned += 1
            if created >= MAX_ALERTS_PER_JOB:
                break
            over = row.get("status") == "over"
            pct = float(row.get("used_pct", 0) or 0)
            month = int(row.get("month", 0) or 0)
            per = f"{year}-{month:02d}" if month else str(year)
            note = await create_notification(
                notif_type="budget_alert", ref=f"budget:{ent}:{row.get('key')}:{per}",
                title=(f"Anggaran {'TERLAMPAUI' if over else 'mendekati batas'}: "
                       f"{row.get('label') or row.get('key')}"),
                body=(f"Periode {per} · pemakaian {pct:.0f}% dari {_rp(row.get('budget'))} "
                      f"(realisasi {_rp(row.get('actual'))} + komitmen {_rp(row.get('committed'))}). "
                      f"Sisa {_rp(row.get('remaining'))}."),
                severity="critical" if over else "warning", link="budget",
                entity_id=ent, recipient_role="manager", dedupe_scope="day",
            )
            if note:
                created += 1
    return {"created": created, "scanned": scanned,
            "detail": f"{scanned} baris anggaran over/mendekati batas"}


# ═══ JOB 5 — Work Order produksi tertunda ════════════════════════════════════
async def job_production_stalled() -> Dict[str, Any]:
    now = _now()
    wos = await db.mfg_work_orders.find(
        {"status": {"$in": ["draft", "released"]}}, {"_id": 0}).to_list(5000)
    created, scanned = 0, 0
    for w in wos:
        status = w.get("status")
        ref_dt = _parse(w.get("released_at") if status == "released" else w.get("created_at"))
        if not ref_dt:
            continue
        age = (now - ref_dt).days
        limit = WO_RELEASED_STALE_DAYS if status == "released" else WO_DRAFT_STALE_DAYS
        short = [p for p in (w.get("material_plan") or []) if not p.get("sufficient")]
        if age < limit and not short:
            continue
        scanned += 1
        if created >= MAX_ALERTS_PER_JOB:
            break
        if short:
            names = ", ".join((p.get("name") or p.get("material_product_id", "")) for p in short[:3])
            body = (f"{w.get('output_name', '')} {w.get('planned_qty', 0):g} {w.get('output_unit', '')} "
                    f"di {w.get('warehouse_name', '')} — BAHAN KURANG: {names}. "
                    f"Umur {age} hari sejak {'dirilis' if status == 'released' else 'dibuat'}.")
            sev = "critical"
        else:
            body = (f"{w.get('output_name', '')} {w.get('planned_qty', 0):g} {w.get('output_unit', '')} "
                    f"di {w.get('warehouse_name', '')} masih "
                    f"{'DIRILIS' if status == 'released' else 'DRAFT'} setelah {age} hari. "
                    f"Selesaikan atau batalkan.")
            sev = "warning"
        note = await create_notification(
            notif_type="production_stalled", ref=f"wo_stalled:{w.get('id')}",
            title=f"Work Order tertunda: {w.get('wo_number', '')}",
            body=body, severity=sev, link="production", entity_id=w.get("entity_id"),
            recipient_role="warehouse", dedupe_scope="day",
        )
        if note:
            created += 1
    return {"created": created, "scanned": scanned,
            "detail": f"{scanned} Work Order tertunda / bahan kurang"}


# ═══ JOB 6 — Tugas gudang (WMS) tertunda ═════════════════════════════════════
async def job_ops_stalled() -> Dict[str, Any]:
    cutoff = (_now() - timedelta(days=TASK_STALE_DAYS)).isoformat()
    tasks = await db.wms_tasks.find(
        {"status": {"$in": TASK_OPEN_STATUSES}, "created_at": {"$lt": cutoff}},
        {"_id": 0, "id": 1, "flow_type": 1, "warehouse_id": 1, "warehouse_name": 1,
         "order_number": 1, "entity_id": 1, "created_at": 1}).to_list(20000)
    if not tasks:
        return {"created": 0, "scanned": 0,
                "detail": f"tidak ada tugas gudang menganggur > {TASK_STALE_DAYS} hari"}
    # Agregasi per (gudang, arah) agar tidak membanjiri bell dengan 1 notif per tugas.
    groups: Dict[tuple, Dict[str, Any]] = {}
    for t in tasks:
        key = (t.get("warehouse_id", ""), t.get("flow_type", ""))
        g = groups.setdefault(key, {"count": 0, "oldest": None, "orders": [],
                                    "warehouse_name": t.get("warehouse_name", ""),
                                    "entity_id": t.get("entity_id")})
        g["count"] += 1
        dt = _parse(t.get("created_at"))
        if dt and (g["oldest"] is None or dt < g["oldest"]):
            g["oldest"] = dt
        if t.get("order_number") and len(g["orders"]) < 4:
            g["orders"].append(t["order_number"])
    created = 0
    now = _now()
    for (wid, flow), g in groups.items():
        age = (now - g["oldest"]).days if g["oldest"] else TASK_STALE_DAYS
        arah = "Outbound (pengiriman)" if flow == "outbound" else "Inbound (penerimaan)"
        note = await create_notification(
            notif_type="ops_stalled", ref=f"task_stalled:{wid}:{flow}",
            title=f"Tugas gudang tertunda: {g['warehouse_name'] or wid}",
            body=(f"{g['count']} tugas {arah} belum selesai (tertua {age} hari). "
                  + (f"Order: {', '.join(g['orders'])}." if g["orders"] else "")),
            severity="warning", link="operations", entity_id=g.get("entity_id"),
            recipient_role="warehouse", dedupe_scope="day",
        )
        if note:
            created += 1
    return {"created": created, "scanned": len(tasks),
            "detail": f"{len(tasks)} tugas menganggur di {len(groups)} gudang/arah"}


# ═══ JOB 7 — Pindai event umum (stok menipis, reservasi, approval) ═══════════
async def job_event_scan() -> Dict[str, Any]:
    created = await generate_system_notifications()
    return {"created": created, "scanned": 0,
            "detail": "stok menipis · reservasi kedaluwarsa · persetujuan SO/PO"}
