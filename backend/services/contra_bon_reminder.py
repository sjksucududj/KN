"""FASE G-7 — **JADWAL TUKAR FAKTUR** per supplier + pengingat otomatis.

MASALAH NYATA
-------------
Supplier tekstil datang menukar faktur pada hari tetap (mis. "setiap Selasa" atau
"tanggal 25"). Kalau hari itu terlewat, fakturnya menumpuk satu siklus penuh dan
pembayaran ikut tertunda — sementara barangnya sudah lama dipakai produksi. Keputusan
pemilik 2026-07-30: *"perlu pengingat"*.

DESAIN
------
* Jadwal disimpan di dokumen supplier (`suppliers.invoice_exchange`) — bukan koleksi baru,
  karena ia memang **atribut supplier**, bukan transaksi.
* `next_exchange_date()` menghitung tanggal siklus berikutnya (mingguan / dua-mingguan /
  bulanan) tanpa perlu tabel kalender.
* Job `contra_bon_reminder` (harian 07:30 WIB, terdaftar di `scheduler_service.JOBS`)
  mengerjakan DUA hal sekaligus:
    1. **H-{reminder_days_before}** sebelum jadwal → notifikasi berisi angka yang bisa
       ditindak: berapa penerimaan barang belum ditagih & berapa tagihan siap dikontrabon.
    2. Kontrabon yang **melewati SLA** verifikasi/persetujuan → notifikasi eskalasi ke
       manager & admin, supaya supplier tidak menunggu tanpa kabar.
* Idempotent: `dedupe_scope="day"` → dijalankan berkali-kali sehari tidak menggandakan
  notifikasi.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core_utils import now_iso, rupiah
from db import db
from services import contra_bon_service as cbs
from services import notification_service as notif

MODES = ("none", "weekly", "biweekly", "monthly")
MODE_LABEL = {
    "none": "Tidak terjadwal",
    "weekly": "Setiap pekan",
    "biweekly": "Dua pekan sekali",
    "monthly": "Bulanan (tanggal tertentu)",
}
WEEKDAY_LABEL = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def _rp(v: Any) -> str:
    return rupiah(v)


def schedule_label(sch: Optional[Dict[str, Any]]) -> str:
    """Kalimat manusia untuk jadwal (dipakai layar & isi notifikasi)."""
    sch = sch or {}
    mode = str(sch.get("mode") or "none")
    if mode == "weekly":
        return f"Setiap {WEEKDAY_LABEL[int(sch.get('weekday', 1)) % 7]}"
    if mode == "biweekly":
        return f"Dua pekan sekali, hari {WEEKDAY_LABEL[int(sch.get('weekday', 1)) % 7]}"
    if mode == "monthly":
        return f"Setiap tanggal {int(sch.get('day_of_month', 25))}"
    return MODE_LABEL["none"]


def next_exchange_date(sch: Optional[Dict[str, Any]],
                       today: Optional[date] = None) -> Optional[date]:
    """Tanggal siklus tukar faktur berikutnya (termasuk HARI INI bila memang harinya)."""
    sch = sch or {}
    mode = str(sch.get("mode") or "none")
    today = today or date.today()
    if mode in ("weekly", "biweekly"):
        target = int(sch.get("weekday", 1)) % 7
        delta = (target - today.weekday()) % 7
        nxt = today + timedelta(days=delta)
        if mode == "biweekly":
            anchor = str(sch.get("anchor_date") or "")
            try:
                base = date.fromisoformat(anchor[:10]) if anchor else nxt
            except ValueError:
                base = nxt
            # Selaraskan tanggal acuan ke HARI (weekday) yang sama dengan `nxt` supaya
            # selisih harinya PASTI kelipatan 7 — mendefinisikan fase 14 hari dengan
            # benar. Tanpa langkah ini, saat weekday acuan ≠ weekday target, ritme
            # 14 hari TAK PERNAH tercapai dengan menambah 7 hari berulang (selisih
            # mod 14 hanya berputar di dua nilai non-nol) → dulu ini bikin loop tak
            # berujung sampai `date value out of range` (BUG seed Kontrabon G-7).
            base = base + timedelta(days=(target - base.weekday()) % 7)
            # Kini selisih pasti kelipatan 7; bila belum sefase 14 hari, geser 1 pekan.
            if (nxt - base).days % 14 != 0:
                nxt = nxt + timedelta(days=7)
        return nxt
    if mode == "monthly":
        dom = min(int(sch.get("day_of_month", 25)), 28)
        if today.day <= dom:
            return date(today.year, today.month, dom)
        nxt_month = today.month + 1
        year = today.year + (1 if nxt_month > 12 else 0)
        nxt_month = 1 if nxt_month > 12 else nxt_month
        return date(year, nxt_month, dom)
    return None


async def set_schedule(supplier_id: str, payload: Dict[str, Any],
                       actor: Dict[str, Any]) -> Dict[str, Any]:
    sup = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not sup:
        raise cbs.ContraBonError("Supplier tidak ditemukan.")
    mode = str(payload.get("mode") or "none")
    if mode not in MODES:
        raise cbs.ContraBonError(
            "Mode jadwal tidak dikenal. Pilihan: " +
            ", ".join(f"\u201c{MODE_LABEL[m]}\u201d" for m in MODES) + ".")
    sch = {
        "mode": mode,
        "weekday": int(payload.get("weekday", 1)) % 7,
        "day_of_month": min(max(int(payload.get("day_of_month", 25)), 1), 28),
        "pic_name": payload.get("pic_name", ""),
        "notes": payload.get("notes", ""),
        "anchor_date": payload.get("anchor_date") or now_iso()[:10],
        "updated_by": actor.get("name", ""), "updated_at": now_iso(),
    }
    await db.suppliers.update_one({"id": supplier_id},
                                  {"$set": {"invoice_exchange": sch, "updated_at": now_iso()}})
    nxt = next_exchange_date(sch)
    return {"supplier_id": supplier_id, "supplier_name": sup.get("name", ""),
            "invoice_exchange": sch, "schedule_label": schedule_label(sch),
            "next_exchange_date": nxt.isoformat() if nxt else ""}


async def schedules(entity_ids: Optional[List[str]] = None,
                    entity_id: str = "") -> Dict[str, Any]:
    """Daftar jadwal tukar faktur seluruh supplier + kesiapan siklus berikutnya (US1)."""
    pol = await cbs.policy(entity_id)
    q: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    elif entity_ids is not None:
        q["entity_id"] = {"$in": list(entity_ids)}
    today = date.today()
    rows: List[Dict[str, Any]] = []
    async for sup in db.suppliers.find(q, {"_id": 0}).sort("name", 1):
        sch = sup.get("invoice_exchange") or {"mode": "none"}
        nxt = next_exchange_date(sch, today)
        days_left = (nxt - today).days if nxt else None
        bills = await cbs.billable_bills(sup["id"], sup.get("entity_id") or entity_id or "")
        gr = await cbs.unbilled_receipts(entity_ids, supplier_id=sup["id"],
                                         entity_id=sup.get("entity_id") or entity_id or "")
        rows.append({
            "supplier_id": sup["id"], "supplier_code": sup.get("code", ""),
            "supplier_name": sup.get("name", ""), "entity_id": sup.get("entity_id", ""),
            "payment_term_code": sup.get("payment_term_code", ""),
            "invoice_exchange": sch, "schedule_label": schedule_label(sch),
            "next_exchange_date": nxt.isoformat() if nxt else "",
            "days_left": days_left,
            "due_reminder": bool(nxt is not None and days_left is not None
                                 and days_left <= int(pol["reminder_days_before"] or 0)),
            "billable_count": len(bills),
            "billable_value": round(sum(b["outstanding"] for b in bills), 2),
            "unbilled_gr_value": gr["total_value"], "unbilled_gr_po_count": gr["po_count"],
        })
    scheduled = [r for r in rows if (r["invoice_exchange"] or {}).get("mode") != "none"]
    return {
        "rows": rows,
        "scheduled_count": len(scheduled),
        "unscheduled_count": len(rows) - len(scheduled),
        "due_soon": [r for r in scheduled if r["due_reminder"]],
        "reminder_days_before": int(pol["reminder_days_before"] or 0),
        "modes": [{"value": m, "label": MODE_LABEL[m]} for m in MODES],
        "weekdays": [{"value": i, "label": WEEKDAY_LABEL[i]} for i in range(7)],
    }


# ═════════════════════════════════════════════════════════════════════════════
#  JOB SCHEDULER
# ═════════════════════════════════════════════════════════════════════════════
async def job_contra_bon_reminder() -> Dict[str, Any]:
    """Pengingat siklus tukar faktur (H-n) + eskalasi kontrabon yang melewati SLA."""
    created = 0
    today = date.today()
    pol_global = await cbs.policy("")
    lead = int(pol_global["reminder_days_before"] or 0)

    # (1) Pengingat jadwal tukar faktur per supplier.
    async for sup in db.suppliers.find({"invoice_exchange.mode": {"$nin": [None, "", "none"]}},
                                       {"_id": 0}):
        sch = sup.get("invoice_exchange") or {}
        nxt = next_exchange_date(sch, today)
        if not nxt:
            continue
        days_left = (nxt - today).days
        if days_left > lead:
            continue
        ent = sup.get("entity_id") or ""
        bills = await cbs.billable_bills(sup["id"], ent)
        gr = await cbs.unbilled_receipts(None, supplier_id=sup["id"], entity_id=ent)
        bills_value = round(sum(b["outstanding"] for b in bills), 2)
        when = "hari ini" if days_left == 0 else f"{days_left} hari lagi ({nxt.isoformat()})"
        body = (f"Tukar faktur {sup.get('name', '')} {when} — {schedule_label(sch)}. "
                f"Siap dikontrabon: {len(bills)} tagihan {_rp(bills_value)}. "
                f"Belum ditagih supplier: {gr['po_count']} PO senilai {_rp(gr['total_value'])}"
                + (f" ({gr['overdue_count']} sudah tertunggak)" if gr["overdue_count"] else "")
                + ".")
        n = await notif.create_notification(
            notif_type="contra_bon_cycle",
            title=f"Jadwal tukar faktur: {sup.get('name', '')}",
            body=body, severity="warning" if gr["overdue_count"] else "info",
            link="contra-bons", entity_id=ent or None, recipient_role="all",
            ref=f"cbcycle:{sup['id']}:{nxt.isoformat()}", dedupe_scope="day")
        created += 1 if n else 0

    # (2) Eskalasi kontrabon yang menunggu terlalu lama.
    async for cb in db[cbs.COLL].find({"status": {"$in": list(cbs.PENDING_STATUSES)}}, {"_id": 0}):
        pol = await cbs.policy(cb.get("entity_id", ""))
        dec = await cbs.decorate(cb, pol)
        sla = dec.get("sla") or {}
        if not sla.get("overdue"):
            continue
        n = await notif.create_notification(
            notif_type="contra_bon_overdue",
            title=f"Kontrabon {dec.get('number')} menunggu terlalu lama",
            body=(f"{dec.get('supplier_name', '')} · status "
                  f"{cbs.STATUS_LABEL.get(dec.get('status', ''), '')} sudah "
                  f"{sla.get('age_days')} hari (batas {sla.get('sla_days')} hari) · nilai bersih "
                  f"{_rp((dec.get('totals') or {}).get('net_payable'))}. Supplier menunggu "
                  "kepastian pembayaran."),
            severity="warning", link="contra-bons",
            entity_id=cb.get("entity_id") or None, recipient_role="manager",
            ref=f"cboverdue:{cb['id']}", dedupe_scope="day")
        created += 1 if n else 0
    return {"notifications": created}
