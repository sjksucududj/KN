"""R6.6 — ESKALASI BERTINGKAT alert yang belum ditindak.

MASALAH: alert penting bisa terabaikan (tidak dibaca) tanpa ada yang menaikkan ke atasan.

SOLUSI: job berkala memindai notifikasi **belum dibaca** dengan severity >= ambang yang
sudah melewati batas waktu (`after_hours`) lalu membuat notifikasi ESKALASI baru untuk
level di atasnya:

    sales / warehouse  →  manager  →  admin  →  (berhenti)

DESAIN
- Notifikasi induk ditandai `escalation_level=1` + `escalated_to` + `escalated_at`
  sehingga TIDAK pernah dieskalasi dua kali (idempotent, tanpa perlu dedupe waktu).
- Notifikasi eskalasi adalah notifikasi biasa (severity **critical**) sehingga:
  (a) tampil di bell penerima level atas, (b) tetap dikirim WhatsApp seketika walau
  mode pengiriman = Ringkasan (critical bypass), (c) bisa dieskalasi lagi ke level
  berikutnya oleh job yang sama → rantai otomatis, dibatasi `max_level`.
- Aksi inline (mis. approve PO) ikut disalin agar atasan bisa langsung menindak.
- Notifikasi yang sudah ditujukan ke `admin` tidak punya level di atasnya → dilewati.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from db import db
from core_utils import now_iso
from services.notification_service import create_notification
from services.wa_alert_service import SEVERITY_RANK, raw_settings

logger = logging.getLogger("alerts.escalation")

# Rantai eskalasi peran (role penerima notifikasi → role di atasnya).
ESCALATION_CHAIN = {
    "sales": "manager",
    "warehouse": "manager",
    "manager": "admin",
    "all": "admin",
    "": "admin",
}
TOP_ROLES = ("admin",)
MAX_PER_RUN = 40          # pagar anti-flood per eksekusi

DEFAULT_ESCALATION = {
    "enabled": True,
    "after_hours": 8,       # batas waktu belum ditindak (1..72)
    "min_severity": "warning",
    "max_level": 2,         # kedalaman rantai maksimum (1..3)
}


async def effective_config() -> Dict[str, Any]:
    st = await raw_settings()
    return {**DEFAULT_ESCALATION, **(st.get("escalation") or {})}


def _hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _age_hours(created_at: str) -> float:
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)


async def job_escalation_scan() -> Dict[str, Any]:
    """Naikkan alert penting yang belum dibaca melewati batas waktu ke level di atasnya."""
    cfg = await effective_config()
    if not cfg.get("enabled", True):
        return {"created": 0, "scanned": 0, "detail": "eskalasi dinonaktifkan di pengaturan"}

    after_hours = float(cfg.get("after_hours", 8) or 8)
    max_level = int(cfg.get("max_level", 2) or 2)
    min_rank = SEVERITY_RANK.get(cfg.get("min_severity", "warning"), 2)
    cutoff = _hours_ago(after_hours)

    candidates = await db.notifications.find({
        "read": False,
        "created_at": {"$lt": cutoff},
        "$or": [{"escalation_level": {"$exists": False}}, {"escalation_level": 0}],
    }, {"_id": 0}).sort("created_at", 1).to_list(500)

    created = skipped_top = skipped_depth = 0
    for n in candidates:
        if created >= MAX_PER_RUN:
            break
        if SEVERITY_RANK.get(n.get("severity", "info"), 1) < min_rank:
            continue
        role = (n.get("recipient_role") or "all")
        if role in TOP_ROLES:
            skipped_top += 1
            continue
        next_role = ESCALATION_CHAIN.get(role)
        if not next_role:
            skipped_top += 1
            continue
        depth = int(n.get("escalation_depth", 0) or 0) + 1
        if depth > max_level:
            skipped_depth += 1
            continue

        age = _age_hours(n.get("created_at", ""))
        note = await create_notification(
            notif_type="escalation",
            ref=f"escal:{n.get('id')}:{depth}",
            title=f"ESKALASI: {n.get('title', '')}",
            body=(f"Belum ditindak {age:.0f} jam (batas {after_hours:.0f} jam) oleh "
                  f"{role}. {n.get('body', '')}"),
            severity="critical",
            link=n.get("link", ""),
            entity_id=n.get("entity_id"),
            recipient_role=next_role,
            action_type=n.get("action_type", ""),
            action_id=n.get("action_id", ""),
            action_role=next_role,
            dedupe_scope="day",
        )
        if not note:
            continue
        # Jejak rantai pada notifikasi eskalasi + tandai induk agar tidak berulang.
        await db.notifications.update_one({"id": note["id"]}, {"$set": {
            "escalation_depth": depth,
            "escalated_from": n.get("id"),
            "escalated_from_role": role,
        }})
        await db.notifications.update_one({"id": n.get("id")}, {"$set": {
            "escalation_level": 1,
            "escalated_at": now_iso(),
            "escalated_to": next_role,
            "escalation_notif_id": note["id"],
        }})
        created += 1

    detail = (f"{created} alert dieskalasi (>{after_hours:.0f} jam belum dibaca) "
              f"dari {len(candidates)} kandidat"
              + (f" \u00b7 {skipped_top} sudah di level tertinggi" if skipped_top else "")
              + (f" \u00b7 {skipped_depth} melewati batas level" if skipped_depth else ""))
    return {"created": created, "scanned": len(candidates), "detail": detail}


async def escalation_stats() -> Dict[str, Any]:
    """KPI ringkas untuk UI: jumlah eskalasi hari ini + yang masih menunggu."""
    day = now_iso()[:10]
    today = await db.notifications.count_documents(
        {"type": "escalation", "created_at": {"$gte": day}})
    open_esc = await db.notifications.count_documents({"type": "escalation", "read": False})
    cfg = await effective_config()
    pending = await db.notifications.count_documents({
        "read": False,
        "created_at": {"$lt": _hours_ago(float(cfg.get("after_hours", 8) or 8))},
        "$or": [{"escalation_level": {"$exists": False}}, {"escalation_level": 0}],
        "severity": {"$in": [s for s, r in SEVERITY_RANK.items()
                             if r >= SEVERITY_RANK.get(cfg.get("min_severity", "warning"), 2)]},
        "recipient_role": {"$nin": list(TOP_ROLES)},
    })
    return {"today": today, "open": open_esc, "pending_next_scan": pending,
            "enabled": bool(cfg.get("enabled", True)),
            "after_hours": cfg.get("after_hours", 8),
            "min_severity": cfg.get("min_severity", "warning"),
            "max_level": cfg.get("max_level", 2)}
