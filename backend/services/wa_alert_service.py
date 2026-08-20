"""R6.5 — Kanal WhatsApp untuk notifikasi/alert (Kain Nusantara).

Alur: notifikasi in-app dibuat → (bila diaktifkan) dorong ke WhatsApp lewat
provider pluggable `services/wa/` (`simulated` | `meta_cloud` | `fonnte`).

DESAIN PENTING
- **Mode default = `simulated`**: pesan TIDAK dikirim ke jaringan, tetapi TETAP
  dicatat lengkap di **Outbox WA** (`sys_wa_outbox`) berisi tujuan + isi pesan,
  sehingga user bisa memverifikasi apa yang AKAN terkirim sebelum mengisi kredensial.
- Tidak pernah melempar exception ke pemanggil (alert tak boleh menggagalkan transaksi).
- Anti-spam: hanya severity >= `min_severity` (default `warning`) dan dedupe per
  (dedupe_key notifikasi, nomor tujuan) → maksimal 1 pesan per hari per tujuan.
- Penerima: nomor user sesuai role penerima notifikasi (dari `users.phone`, fallback
  `hr_employees.phone`) DAN/ATAU satu nomor PIC override di pengaturan.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso, safe_doc
from services.wa import get_wa_provider

logger = logging.getLogger("alerts.whatsapp")

SETTINGS_SCOPE = "alerts"
SEVERITY_RANK = {"info": 1, "warning": 2, "critical": 3}
# Role yang menerima broadcast saat notifikasi ditujukan ke "all" (batasi spam).
BROADCAST_ROLES = ["admin", "manager"]

DEFAULT_WA = {
    "enabled": False,
    "provider": "simulated",
    "phone_number_id": "",
    "template_name": "",
    "template_lang": "id",
    "sender": "",
    "pic_number": "",
    "send_to_roles": True,
    "min_severity": "warning",
    # R6.6 — mode pengiriman: "instant" = 1 pesan per alert (bisa membanjiri),
    # "digest" = alert digabung jadi 1 pesan ringkas harian (job `daily_digest`).
    "delivery_mode": "instant",
    # Alert PENTING (critical) tetap dikirim seketika walau mode digest.
    "critical_bypass": True,
}
DELIVERY_MODES = ("instant", "digest")
SECRET_FIELDS = ("access_token", "fonnte_token")


# ═══ Nomor telepon Indonesia ═════════════════════════════════════════════════
def format_id_phone(phone: str) -> str:
    """Normalkan nomor Indonesia ke format E.164 tanpa '+': 08xx → 628xx."""
    if not phone:
        return ""
    cleaned = re.sub(r"\D", "", str(phone))
    if not cleaned:
        return ""
    if cleaned.startswith("0"):
        return "62" + cleaned[1:]
    if cleaned.startswith("62"):
        return cleaned
    if cleaned.startswith("8"):
        return "62" + cleaned
    return cleaned


def valid_phone(phone: str) -> bool:
    p = format_id_phone(phone)
    return p.startswith("62") and 10 <= len(p) <= 15


# ═══ Pengaturan ══════════════════════════════════════════════════════════════
async def raw_settings() -> Dict[str, Any]:
    doc = await db.system_settings.find_one({"scope": SETTINGS_SCOPE}, {"_id": 0}) or {}
    wa = {**DEFAULT_WA, **(doc.get("wa") or {})}
    return {"scope": SETTINGS_SCOPE, "jobs": doc.get("jobs") or {}, "wa": wa,
            "escalation": doc.get("escalation") or {},
            "updated_at": doc.get("updated_at", "")}


def mask_wa(wa: Dict[str, Any]) -> Dict[str, Any]:
    """Buang kredensial dari respons API (hanya kirim penanda `has_*`)."""
    out = {k: v for k, v in wa.items() if k not in SECRET_FIELDS}
    out["has_access_token"] = bool(wa.get("access_token"))
    out["has_fonnte_token"] = bool(wa.get("fonnte_token"))
    out["configured"] = bool(
        (wa.get("provider") == "meta_cloud" and wa.get("access_token") and wa.get("phone_number_id"))
        or (wa.get("provider") == "fonnte" and wa.get("fonnte_token"))
    )
    return out


# ═══ Penerima ════════════════════════════════════════════════════════════════
async def _phone_for_user(user: Dict[str, Any]) -> str:
    """users.phone → fallback hr_employees.phone (profil karyawan tertaut)."""
    if user.get("phone"):
        return str(user["phone"])
    emp = await db.hr_employees.find_one({"user_id": user.get("id")}, {"_id": 0, "phone": 1})
    return str((emp or {}).get("phone") or "")


async def resolve_recipients(notif: Dict[str, Any], wa: Dict[str, Any]) -> List[Dict[str, str]]:
    """Daftar {name, role, phone} penerima WhatsApp untuk 1 notifikasi (unik per nomor)."""
    out: List[Dict[str, str]] = []
    seen = set()

    def _add(name: str, role: str, phone: str):
        p = format_id_phone(phone)
        if not p or p in seen or not valid_phone(p):
            return
        seen.add(p)
        out.append({"name": name, "role": role, "phone": p})

    if wa.get("send_to_roles", True):
        target_user = notif.get("recipient_user")
        role = notif.get("recipient_role") or "all"
        q: Dict[str, Any] = {"status": "active"}
        if target_user:
            q["id"] = target_user
        elif role == "all":
            q["role"] = {"$in": BROADCAST_ROLES}
        else:
            # role penerima + admin (admin selalu tahu kondisi kritikal)
            q["role"] = {"$in": list({role, "admin"})}
        users = await db.users.find(q, {"_id": 0, "id": 1, "name": 1, "role": 1,
                                       "phone": 1}).to_list(200)
        for u in users:
            _add(u.get("name", ""), u.get("role", ""), await _phone_for_user(u))

    if wa.get("pic_number"):
        _add("PIC Notifikasi", "pic", wa["pic_number"])
    return out


# ═══ Outbox + pengiriman ═════════════════════════════════════════════════════
def compose_text(notif: Dict[str, Any]) -> str:
    sev = (notif.get("severity") or "info").upper()
    tag = {"CRITICAL": "🔴 PENTING", "WARNING": "🟠 PERHATIAN"}.get(sev, "ℹ️ INFO")
    return (f"*KAIN NUSANTARA ERP* · {tag}\n"
            f"*{notif.get('title', '')}*\n{notif.get('body', '')}")


async def _dispatch(wa: Dict[str, Any], phone: str, text: str,
                    notif: Dict[str, Any]) -> Dict[str, Any]:
    """Kirim via provider terpilih. Return {status, provider, error, message_id}."""
    provider_name = wa.get("provider") or "simulated"
    if provider_name == "simulated":
        logger.info("[WA:simulated] → %s :: %s", phone, notif.get("title", ""))
        return {"status": "simulated", "provider": "simulated", "error": "", "message_id": ""}
    settings = {k: v for k, v in wa.items()}
    provider = get_wa_provider(provider_name, settings)
    try:
        if provider_name == "meta_cloud" and wa.get("template_name"):
            res = await provider.send_template(
                phone, wa["template_name"],
                [notif.get("title", ""), notif.get("body", "")],
                lang=wa.get("template_lang", "id"))
        else:
            res = await provider.send_message(phone, text)
    except Exception as exc:  # noqa: BLE001 — alert tak boleh menggagalkan apa pun
        logger.warning("[WA:%s] exception: %s", provider_name, exc)
        return {"status": "failed", "provider": provider_name, "error": str(exc), "message_id": ""}
    return {"status": "sent" if res.get("status") == "sent" else "failed",
            "provider": provider_name, "error": res.get("error", ""),
            "message_id": res.get("message_id", "") or ""}


async def push_notification(notif: Dict[str, Any]) -> Dict[str, Any]:
    """Dorong 1 notifikasi ke WhatsApp (best-effort, tidak pernah raise)."""
    try:
        st = await raw_settings()
        wa = st["wa"]
        if not wa.get("enabled"):
            return {"queued": 0, "skipped": "wa_disabled"}
        min_rank = SEVERITY_RANK.get(wa.get("min_severity", "warning"), 2)
        sev = notif.get("severity", "info")
        if SEVERITY_RANK.get(sev, 1) < min_rank:
            return {"queued": 0, "skipped": "severity_below_min"}
        # R6.6 — mode Ringkasan: alert per-item TIDAK dikirim seketika (digabung oleh
        # job `daily_digest`), kecuali severity critical bila `critical_bypass` aktif.
        if wa.get("delivery_mode", "instant") == "digest" \
                and not (sev == "critical" and wa.get("critical_bypass", True)):
            return {"queued": 0, "skipped": "digest_mode"}
        recipients = await resolve_recipients(notif, wa)
        if not recipients:
            return {"queued": 0, "skipped": "no_recipient_phone"}
        text = compose_text(notif)
        day = now_iso()[:10]
        base_key = notif.get("dedupe_key") or f"{notif.get('type')}:{notif.get('ref')}:{day}"
        queued = 0
        for r in recipients:
            key = f"{base_key}|{r['phone']}"
            if await db.sys_wa_outbox.find_one({"dedupe_key": key}, {"_id": 1}):
                continue
            res = await _dispatch(wa, r["phone"], text, notif)
            await db.sys_wa_outbox.insert_one({
                "id": new_id("waout"), "dedupe_key": key,
                "to": r["phone"], "to_name": r["name"], "to_role": r["role"],
                "notification_id": notif.get("id", ""), "notif_type": notif.get("type", ""),
                "severity": notif.get("severity", "info"),
                "title": notif.get("title", ""), "text": text,
                "provider": res["provider"], "status": res["status"],
                "error": res["error"], "message_id": res["message_id"],
                "entity_id": notif.get("entity_id"),
                "created_at": now_iso(),
                "sent_at": now_iso() if res["status"] in ("sent", "simulated") else "",
            })
            queued += 1
        return {"queued": queued, "recipients": len(recipients),
                "provider": wa.get("provider", "simulated")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[WA] push gagal: %s", exc)
        return {"queued": 0, "error": str(exc)}


async def send_test(phone: str, text: str = "") -> Dict[str, Any]:
    """Kirim pesan uji ke 1 nomor (dicatat di outbox). Dipakai tombol 'Tes Kirim'."""
    st = await raw_settings()
    wa = st["wa"]
    p = format_id_phone(phone)
    if not valid_phone(p):
        raise ValueError("Nomor WhatsApp tidak valid. Contoh: 081234567890.")
    notif = {"id": "", "type": "wa_test", "ref": f"test:{now_iso()}",
             "severity": "warning", "title": "Tes notifikasi WhatsApp",
             "body": text or "Ini pesan uji dari Kain Nusantara ERP. Bila diterima, kanal WhatsApp siap."}
    body = compose_text(notif)
    res = await _dispatch(wa, p, body, notif)
    doc = {
        "id": new_id("waout"), "dedupe_key": f"wa_test:{p}:{now_iso()}",
        "to": p, "to_name": "Tes Manual", "to_role": "test",
        "notification_id": "", "notif_type": "wa_test", "severity": "warning",
        "title": notif["title"], "text": body, "provider": res["provider"],
        "status": res["status"], "error": res["error"], "message_id": res["message_id"],
        "entity_id": None, "created_at": now_iso(),
        "sent_at": now_iso() if res["status"] in ("sent", "simulated") else "",
    }
    await db.sys_wa_outbox.insert_one(dict(doc))
    return safe_doc(doc)


async def retry_outbox(outbox_id: str) -> Optional[Dict[str, Any]]:
    """Coba kirim ulang 1 baris outbox yang gagal."""
    row = await db.sys_wa_outbox.find_one({"id": outbox_id}, {"_id": 0})
    if not row:
        return None
    st = await raw_settings()
    notif = {"id": row.get("notification_id", ""), "type": row.get("notif_type", ""),
             "severity": row.get("severity", "info"), "title": row.get("title", ""),
             "body": ""}
    res = await _dispatch(st["wa"], row["to"], row.get("text", ""), notif)
    await db.sys_wa_outbox.update_one({"id": outbox_id}, {"$set": {
        "status": res["status"], "provider": res["provider"], "error": res["error"],
        "message_id": res["message_id"], "retried_at": now_iso(),
        "sent_at": now_iso() if res["status"] in ("sent", "simulated") else row.get("sent_at", ""),
    }})
    return await db.sys_wa_outbox.find_one({"id": outbox_id}, {"_id": 0})


async def outbox_list(status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    return await db.sys_wa_outbox.find(q, {"_id": 0}).sort("created_at", -1).to_list(int(limit))


async def outbox_stats() -> Dict[str, Any]:
    day = now_iso()[:10]
    rows = await db.sys_wa_outbox.find({}, {"_id": 0, "status": 1, "created_at": 1}).to_list(20000)
    by_status: Dict[str, int] = {}
    today = 0
    for r in rows:
        by_status[r.get("status", "?")] = by_status.get(r.get("status", "?"), 0) + 1
        if (r.get("created_at") or "").startswith(day):
            today += 1
    return {"total": len(rows), "today": today, "by_status": by_status}
