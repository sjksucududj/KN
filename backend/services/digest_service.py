"""R6.6 — RINGKASAN HARIAN (Daily Digest) untuk kanal WhatsApp.

MASALAH yang diselesaikan: pada mode `instant`, setiap alert dikirim sebagai 1 pesan
WhatsApp ke setiap penerima → 1 hari bisa puluhan pesan (mis. 52 pesan/hari di data demo)
→ staf kebanjiran notifikasi dan alert penting jadi tenggelam.

SOLUSI: satu pesan RINGKAS per penerima per hari yang MENGGABUNGKAN alert sejenis
(dikelompokkan per tipe, diurut tingkat kepentingan) + contoh 1 judul per kelompok.

DESAIN
- Digest dibangun dari koleksi `notifications` (SSOT alert in-app) untuk HARI INI,
  di-scope sesuai penerima (recipient_role ∈ {role, "all"} ATAU recipient_user == user.id)
  — identik dengan aturan scoping bell di `routers/notifications.py`.
- Dedupe: `digest:<YYYY-MM-DD>|<nomor>` → maksimal **1 digest per nomor per hari**
  (job boleh dijalankan berulang tanpa spam).
- Digest TIDAK membuat notifikasi in-app baru: bell tetap menampilkan item individual
  (di sana detail & aksi inline berada). Digest murni kanal WhatsApp.
- Mode `digest` (pengaturan `wa.delivery_mode`) menekan pengiriman per-alert; alert
  severity `critical` tetap dikirim langsung bila `wa.critical_bypass` aktif.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso
from services import wa_alert_service as wa

logger = logging.getLogger("alerts.digest")

MAX_GROUPS = 8          # maksimal kelompok yang ditulis di pesan (sisanya diringkas)
MAX_SCAN = 1000         # pagar jumlah notifikasi yang dipindai per penerima
SEV_ICON = {"critical": "\U0001F534", "warning": "\U0001F7E0", "info": "\u2139\uFE0F"}

# Label ramah-manusia per tipe notifikasi (fallback: tipe mentah dirapikan).
GROUP_LABEL = {
    "ar_overdue": "Piutang jatuh tempo",
    "ap_due": "Hutang supplier jatuh tempo",
    "depreciation_due": "Reminder penyusutan aset",
    "budget_alert": "Anggaran over/mendekati batas",
    "production_stalled": "Work Order produksi tertunda",
    "ops_stalled": "Tugas gudang tertunda",
    "low_stock": "Stok menipis",
    "reservation_expiring": "Reservasi mendekati kedaluwarsa",
    "order_approval": "Order menunggu persetujuan",
    "po_approval": "PO menunggu persetujuan",
    "order_split": "Order split antar gudang",
    "escalation": "ESKALASI belum ditindak",
    "wa_test": "Tes kanal WhatsApp",
}


def group_label(notif_type: str) -> str:
    if notif_type in GROUP_LABEL:
        return GROUP_LABEL[notif_type]
    return (notif_type or "lainnya").replace("_", " ").capitalize()


def _today() -> str:
    return now_iso()[:10]


def _fmt_tanggal(day: str) -> str:
    bulan = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
             "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    try:
        y, m, d = day.split("-")
        return f"{int(d)} {bulan[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return day


# ═══ Penerima digest ═════════════════════════════════════════════════════════
async def digest_recipients(wa_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Daftar penerima unik per nomor: user aktif ber-nomor + nomor PIC (opsional).

    PIC menerima digest ber-scope `admin` (pandangan menyeluruh).
    """
    out: List[Dict[str, Any]] = []
    seen = set()

    def _add(name: str, role: str, phone: str, user_id: Optional[str]):
        p = wa.format_id_phone(phone)
        if not p or p in seen or not wa.valid_phone(p):
            return
        seen.add(p)
        out.append({"name": name, "role": role, "phone": p, "user_id": user_id})

    if wa_cfg.get("send_to_roles", True):
        users = await db.users.find(
            {"status": "active"},
            {"_id": 0, "id": 1, "name": 1, "role": 1, "phone": 1}).to_list(300)
        for u in users:
            phone = await wa._phone_for_user(u)  # noqa: SLF001 — helper internal modul kembar
            _add(u.get("name", ""), u.get("role", ""), phone, u.get("id"))
    if wa_cfg.get("pic_number"):
        _add("PIC Notifikasi", "admin", wa_cfg["pic_number"], None)
    return out


# ═══ Pengelompokan ═══════════════════════════════════════════════════════════
async def summarize_for(user_id: Optional[str], role: str, day: str,
                        min_rank: int) -> Dict[str, Any]:
    """Kelompokkan notifikasi HARI INI yang terlihat oleh 1 penerima.

    Aturan scope SELARAS `wa_alert_service.resolve_recipients`:
    - `admin` menerima salinan SEMUA alert (admin selalu tahu kondisi kritikal),
    - peran lain hanya alert yang ditujukan ke perannya, ke \"all\", atau ke dirinya.
    Dengan begitu isi ringkasan == apa yang akan diterima orang itu pada mode instan.
    """
    q: Dict[str, Any] = {"created_at": {"$gte": day}}
    if role != "admin":
        scope: List[Dict[str, Any]] = [{"recipient_role": {"$in": [role, "all"]}}]
        if user_id:
            scope.append({"recipient_user": user_id})
        q["$or"] = scope
    rows = await db.notifications.find(
        q, {"_id": 0, "type": 1, "title": 1, "severity": 1, "read": 1}).to_list(MAX_SCAN)

    groups: Dict[str, Dict[str, Any]] = {}
    total = unread = 0
    for r in rows:
        sev = r.get("severity", "info")
        if wa.SEVERITY_RANK.get(sev, 1) < min_rank:
            continue
        total += 1
        if not r.get("read"):
            unread += 1
        key = r.get("type") or "lainnya"
        g = groups.setdefault(key, {"type": key, "label": group_label(key), "count": 0,
                                    "rank": 0, "severity": "info", "sample": ""})
        g["count"] += 1
        rank = wa.SEVERITY_RANK.get(sev, 1)
        if rank > g["rank"]:
            g["rank"], g["severity"] = rank, sev
        if not g["sample"]:
            g["sample"] = r.get("title", "")
    ordered = sorted(groups.values(), key=lambda g: (-g["rank"], -g["count"], g["label"]))
    return {"groups": ordered, "total": total, "unread": unread}


def compose_digest(recipient: Dict[str, Any], summary: Dict[str, Any], day: str) -> str:
    """Susun teks WhatsApp ringkas (satu pesan menggantikan puluhan pesan per-alert)."""
    lines = ["*KAIN NUSANTARA ERP* \u00b7 \U0001F4CB RINGKASAN HARIAN",
             f"{_fmt_tanggal(day)} \u00b7 {recipient['name']} ({recipient['role']})", ""]
    shown = summary["groups"][:MAX_GROUPS]
    for g in shown:
        icon = SEV_ICON.get(g["severity"], SEV_ICON["info"])
        lines.append(f"{icon} *{g['label']}* \u2014 {g['count']}")
        if g["sample"]:
            lines.append(f"   \u2022 {g['sample'][:70]}")
    sisa = len(summary["groups"]) - len(shown)
    if sisa > 0:
        lines.append(f"\u2026 dan {sisa} kelompok alert lain.")
    lines += ["", f"Total {summary['total']} alert ({summary['unread']} belum dibaca).",
              "Detail & tindak lanjut ada di menu Notifikasi aplikasi."]
    return "\n".join(lines)


# ═══ Job ═════════════════════════════════════════════════════════════════════
async def job_daily_digest() -> Dict[str, Any]:
    """Kirim 1 pesan ringkasan per penerima (dedupe harian). Tidak pernah raise."""
    st = await wa.raw_settings()
    cfg = st["wa"]
    if not cfg.get("enabled"):
        return {"created": 0, "scanned": 0,
                "detail": "kanal WhatsApp nonaktif — ringkasan tidak dikirim"}
    day = _today()
    min_rank = wa.SEVERITY_RANK.get(cfg.get("min_severity", "warning"), 2)
    recipients = await digest_recipients(cfg)
    sent = skipped_empty = skipped_dupe = 0
    for r in recipients:
        key = f"digest:{day}|{r['phone']}"
        if await db.sys_wa_outbox.find_one({"dedupe_key": key}, {"_id": 1}):
            skipped_dupe += 1
            continue
        summary = await summarize_for(r.get("user_id"), r.get("role", ""), day, min_rank)
        if summary["total"] == 0:
            skipped_empty += 1
            continue
        text = compose_digest(r, summary, day)
        top_sev = summary["groups"][0]["severity"] if summary["groups"] else "info"
        notif = {"id": "", "type": "daily_digest", "severity": top_sev,
                 "title": f"Ringkasan harian {_fmt_tanggal(day)}", "body": text}
        res = await wa._dispatch(cfg, r["phone"], text, notif)  # noqa: SLF001
        await db.sys_wa_outbox.insert_one({
            "id": new_id("waout"), "dedupe_key": key,
            "to": r["phone"], "to_name": r["name"], "to_role": r.get("role", ""),
            "notification_id": "", "notif_type": "daily_digest", "severity": top_sev,
            "title": notif["title"], "text": text,
            "provider": res["provider"], "status": res["status"],
            "error": res["error"], "message_id": res["message_id"],
            "entity_id": None, "created_at": now_iso(),
            "sent_at": now_iso() if res["status"] in ("sent", "simulated") else "",
            "digest_groups": len(summary["groups"]), "digest_alerts": summary["total"],
        })
        sent += 1
    detail = (f"{sent} ringkasan terkirim dari {len(recipients)} penerima "
              f"(dilewati: {skipped_dupe} sudah dikirim hari ini, {skipped_empty} tanpa alert)")
    return {"created": sent, "scanned": len(recipients), "detail": detail}


async def preview_digest(role: str = "admin", user_id: Optional[str] = None) -> Dict[str, Any]:
    """Pratinjau isi digest hari ini (dipakai UI sebelum mengaktifkan mode Ringkasan)."""
    st = await wa.raw_settings()
    cfg = st["wa"]
    day = _today()
    min_rank = wa.SEVERITY_RANK.get(cfg.get("min_severity", "warning"), 2)
    summary = await summarize_for(user_id, role, day, min_rank)
    who = {"name": "Pratinjau", "role": role}
    return {"day": day, "role": role, "groups": summary["groups"],
            "total": summary["total"], "unread": summary["unread"],
            "text": compose_digest(who, summary, day) if summary["total"] else "",
            "min_severity": cfg.get("min_severity", "warning"),
            "delivery_mode": cfg.get("delivery_mode", "instant"),
            "wa_enabled": bool(cfg.get("enabled"))}
