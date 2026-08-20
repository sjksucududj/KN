"""PS-18 — **ESKALASI SLA SAMPLE R&D** (dari papan pasif menjadi pengingat aktif).

MASALAH NYATA
-------------
Tenggat round sample sudah dihitung (`rnd.round_sla_days`) dan round yang lewat tenggat
sudah ditandai merah di "Papan SLA Round". Tetapi papan itu **PASIF**: kalau tidak ada
yang membuka layarnya, keterlambatan bisa berumur berminggu-minggu tanpa ada yang tahu —
sementara pelanggan menunggu kabar sample.

DESAIN (kebijakan disetujui pemilik)
------------------------------------
* **Bertingkat.** Setiap hari, round yang masih berjalan tetapi lewat tenggat
  diberitahukan ke **manager**. Bila keterlambatannya sudah ≥ `rnd.sla_escalate_admin_days`
  (bawaan 3 hari), notifikasi **juga dinaikkan ke admin/pemilik** — jadi keterlambatan
  berat tidak berhenti di satu meja.
* **Idempotent.** `dedupe_scope="day"` + `ref` per round → job boleh dijalankan berkali-kali
  dalam sehari (otomatis maupun tombol "Jalankan") tanpa menggandakan pesan.
* **Kanal yang sudah ada.** Memakai `notification_service.create_notification`, yang
  otomatis meneruskan ke WhatsApp lewat `wa_alert_service` — tanpa mesin notifikasi baru.
* **Tidak berisik.** Permintaan yang sudah **diputus** atau **dibatalkan** dilewati:
  pemenang sudah dipilih, tidak ada lagi yang menunggu round pesaing.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from db import db
from services import notification_service as notif
from services import rnd_kpi_service as kpi

COLL = "md_samples"
LINK = "rnd-reports"

STATE_LABEL = {
    "open": "menunggu hasil supplier",
    "submitted": "menunggu penilaian manager",
}


def _tier(days: int, admin_days: int) -> str:
    """`manager` = keterlambatan biasa · `admin` = sudah harus naik ke pemilik."""
    return "admin" if days >= max(int(admin_days or 0), 1) else "manager"


async def overdue_rounds(query: Optional[Dict[str, Any]] = None, *,
                         entity_id: str = "") -> List[Dict[str, Any]]:
    """Round R&D yang MASIH berjalan tetapi sudah lewat tenggat (terurut paling parah).

    Dipakai dua-duanya: layar (papan eskalasi) dan job penjadwal — supaya angka di UI
    dan isi notifikasi tidak mungkin berbeda.
    """
    flt: Dict[str, Any] = dict(query or {})
    flt.setdefault("status", {"$nin": list(kpi.CLOSED_SAMPLE_STATUSES)})
    today = date.today()
    admin_cache: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    rows = await db[COLL].find(flt, {
        "_id": 0, "id": 1, "number": 1, "title": 1, "sample_type": 1, "status": 1,
        "entity_id": 1, "created_by": 1, "customer_id": 1, "rounds": 1,
    }).to_list(5000)
    for s in rows:
        ent = str(s.get("entity_id") or "")
        if ent not in admin_cache:
            admin_cache[ent] = int((await kpi.weights(ent))["escalate_admin_days"])
        admin_days = admin_cache[ent]
        for rd in (s.get("rounds") or []):
            state = str(rd.get("status") or "")
            if state not in kpi.RUNNING_ROUND_STATUSES:
                continue
            late = kpi.days_late(rd, today)
            if late <= 0:
                continue
            out.append({
                "sample_id": s.get("id", ""), "number": s.get("number", ""),
                "title": s.get("title", ""), "sample_type": s.get("sample_type", ""),
                "entity_id": ent,
                "round_id": rd.get("id", ""), "round_no": int(rd.get("round_no") or 0),
                "supplier_id": rd.get("supplier_id", ""),
                "supplier_name": rd.get("supplier_name", ""),
                "designer": kpi.designer_of(s, rd),
                "due_date": str(rd.get("due_date") or "")[:10],
                "days_late": late, "round_status": state,
                "state_label": STATE_LABEL.get(state, state),
                "escalate_admin_days": admin_days,
                "tier": _tier(late, admin_days),
            })
    out.sort(key=lambda r: (-int(r["days_late"]), str(r["number"]), int(r["round_no"])))
    return out


async def board(query: Optional[Dict[str, Any]] = None, *,
                entity_id: str = "") -> Dict[str, Any]:
    """Papan eskalasi untuk layar: daftar + ringkasan tingkatannya."""
    rows = await overdue_rounds(query, entity_id=entity_id)
    w = await kpi.weights(entity_id)
    return {
        "count": len(rows), "items": rows,
        "manager_count": sum(1 for r in rows if r["tier"] == "manager"),
        "admin_count": sum(1 for r in rows if r["tier"] == "admin"),
        "worst_days_late": max([int(r["days_late"]) for r in rows], default=0),
        "escalate_admin_days": int(w["escalate_admin_days"]),
        "round_sla_days": int(w["round_sla_days"]),
    }


def _body(row: Dict[str, Any], *, for_admin: bool = False) -> str:
    late = int(row["days_late"])
    head = (f"Round {row['round_no']} permintaan {row['number']} "
            f"({row['title']}) ke {row['supplier_name'] or 'supplier'} "
            f"sudah TERLAMBAT {late} hari — tenggat {row['due_date']}, "
            f"keadaan: {row['state_label']}.")
    who = f" Penanggung jawab: {row['designer']}." if row.get("designer") else ""
    if for_admin:
        tail = (f" Keterlambatan sudah melewati {row['escalate_admin_days']} hari sehingga "
                "dinaikkan ke admin/pemilik. Mohon putuskan: tegur supplier, ganti supplier, "
                "atau mundurkan janji ke pelanggan.")
    else:
        tail = (" Segera tagih supplier atau nilai hasil yang sudah masuk supaya "
                "janji ke pelanggan tidak ikut mundur.")
    return head + who + tail


# ═════════════════════════════════════════════════════════════════════════════
#  JOB SCHEDULER — terdaftar di `scheduler_service.JOBS` (id: rnd_sla_escalation)
# ═════════════════════════════════════════════════════════════════════════════
async def job_rnd_sla_escalation() -> Dict[str, Any]:
    """Eskalasi harian round sample yang lewat tenggat (manager → admin bertingkat)."""
    rows = await overdue_rounds()
    created = 0
    to_admin = 0
    for row in rows:
        late = int(row["days_late"])
        naik = row["tier"] == "admin"
        n = await notif.create_notification(
            notif_type="rnd_sla_overdue",
            title=f"Sample terlambat: {row['number']} round {row['round_no']}",
            body=_body(row), severity="critical" if naik else "warning",
            link=LINK, entity_id=row["entity_id"] or None, recipient_role="manager",
            ref=f"rndsla:{row['round_id']}", dedupe_scope="day")
        created += 1 if n else 0
        if naik:
            to_admin += 1
            na = await notif.create_notification(
                notif_type="rnd_sla_escalated",
                title=(f"ESKALASI {late} hari: sample {row['number']} "
                       f"round {row['round_no']}"),
                body=_body(row, for_admin=True), severity="critical",
                link=LINK, entity_id=row["entity_id"] or None, recipient_role="admin",
                ref=f"rndslaadm:{row['round_id']}", dedupe_scope="day")
            created += 1 if na else 0
    detail = (f"{len(rows)} round lewat tenggat · {to_admin} dinaikkan ke admin"
              if rows else "Tidak ada round R&D yang lewat tenggat")
    return {"created": created, "scanned": len(rows), "detail": detail,
            "overdue": len(rows), "escalated_to_admin": to_admin}
