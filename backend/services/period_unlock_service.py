"""FASE G-5 — UNLOCK PERIODE BEROTORITAS ("wajib dua orang & menutup sendiri").

Alur resmi membuka periode tertutup untuk posting/koreksi MUNDUR:

    usul (reason WAJIB)  →  setujui (pengusul ≠ penyetuju — DUAL CONTROL)
      →  jendela berbatas waktu (config `periode.unlock_window_hours`, bawaan 24 jam)
        →  setiap JE yang lahir di jendela ditandai `backdated_in_unlock: <plu_id>`
          →  lewat batas = AUTO-RECLOSE (job `period_unlock_auto_close` / manual)

Koleksi `period_unlock_requests` (prefix `plu_`). Per-entitas (buku terpisah per PT).

Penjaga NYATA-nya ada di `gl_service.enforce_closed_period_guard` (dipanggil oleh
`_insert_entry` & `create_manual_entry`): TANPA jendela unlock aktif, posting ke
periode `closed` DITOLAK (hard-lock) — bukan sekadar peringatan seperti dulu.

Invarian:
- **INV-CLS-01**: tak ada JE di periode `closed` (dibuat SETELAH tutup) tanpa
  `backdated_in_unlock` — dijaga guard + gate.
- **INV-CLS-02**: tiap unlock yang disetujui punya `reason` + pengusul ≠ penyetuju.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso, safe_doc
from services import closing_service as cs
from services.config_resolver import value_of

COLL = "period_unlock_requests"
TERMINAL = ("expired", "reclosed", "rejected")


# ─── util waktu ───────────────────────────────────────────────────────
def _as_dt(iso: Any) -> Optional[datetime]:
    if isinstance(iso, datetime):
        return iso if iso.tzinfo else iso.replace(tzinfo=timezone.utc)
    if not iso:
        return None
    try:
        s = str(iso).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _cfg_int(key: str, entity_id: Optional[str], fallback: int) -> int:
    try:
        return int(await value_of(key, {"entity_id": entity_id}))
    except (TypeError, ValueError):
        return fallback


# ─── query ────────────────────────────────────────────────────
async def list_requests(entity_id: Optional[str] = None,
                        status: Optional[str] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    if status:
        q["status"] = status
    rows = await db[COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    now = _now()
    # Tampilkan sisa waktu jendela (untuk UI countdown) tanpa menulis DB.
    for r in rows:
        wu = _as_dt(r.get("window_until"))
        r["is_active_now"] = bool(r.get("status") == "approved" and wu and wu > now)
        r["window_seconds_left"] = int((wu - now).total_seconds()) if (wu and wu > now) else 0
    return rows


async def active_unlocks(entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Unlock yang SEDANG aktif (approved & belum lewat batas). Dipakai banner & guard."""
    q: Dict[str, Any] = {"status": "approved"}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    now = _now()
    out: List[Dict[str, Any]] = []
    async for r in db[COLL].find(q, {"_id": 0}):
        wu = _as_dt(r.get("window_until"))
        if wu and wu > now:
            r["window_seconds_left"] = int((wu - now).total_seconds())
            out.append(r)
    return out


async def find_active_unlock(entity_id: str, date_iso: str) -> Optional[Dict[str, Any]]:
    """Unlock aktif yang MENCAKUP tanggal `date_iso` untuk entitas ini (guard GL)."""
    d = (date_iso or "")[:10]
    if not d or not entity_id:
        return None
    now = _now()
    async for r in db[COLL].find({"entity_id": entity_id, "status": "approved"}, {"_id": 0}):
        wu = _as_dt(r.get("window_until"))
        if not (wu and wu > now):
            continue
        if r.get("start_date", "") <= d <= r.get("end_date", ""):
            return r
    return None


async def get_request(plu_id: str) -> Optional[Dict[str, Any]]:
    return await db[COLL].find_one({"id": plu_id}, {"_id": 0})


# ─── aksi: usul / setujui / tolak ────────────────────────────────────
async def _closed_record(entity_id: str, period_type: str, period_key: str,
                        start: str, end: str) -> Optional[Dict[str, Any]]:
    """Cari period_closings status='closed' yang cocok/mencakup periode ini."""
    # Prioritas: match persis (type+key). Fallback: closing yang mencakup rentang.
    rec = await db.period_closings.find_one(
        {"entity_id": entity_id, "period_type": period_type,
         "period_key": period_key, "status": "closed"}, {"_id": 0})
    if rec:
        return rec
    async for r in db.period_closings.find(
            {"entity_id": entity_id, "status": "closed"}, {"_id": 0}):
        if r.get("start_date", "") <= start and end <= r.get("end_date", ""):
            return r
    return None


async def request_unlock(*, period_type: str, period_key: str, entity_id: str,
                         reason: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    if period_type not in ("month", "year"):
        raise ValueError("period_type harus 'month' atau 'year'.")
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Alasan membuka periode WAJIB diisi.")
    start, end = await cs.period_bounds(period_type, period_key, entity_id)
    closing = await _closed_record(entity_id, period_type, period_key, start, end)
    if not closing:
        raise ValueError(
            "Periode ini belum ditutup (atau sudah dibuka) — tidak perlu izin buka periode.")

    # Batas mundur: tak boleh membuka periode yang ditutup terlalu lama.
    max_days = await _cfg_int("periode.max_days_after_close", entity_id, 7)
    if max_days > 0:
        closed_at = _as_dt(closing.get("closed_at")) or _as_dt(closing.get("created_at"))
        if closed_at and (_now() - closed_at) > timedelta(days=max_days):
            raise ValueError(
                f"Periode ditutup lebih dari {max_days} hari lalu — di luar batas mundur "
                f"membuka periode. Ubah 'Batas mundur usul buka periode' bila perlu.")

    # Cegah usul ganda yang masih hidup untuk periode yang sama.
    dup = await db[COLL].find_one(
        {"entity_id": entity_id, "period_type": period_type, "period_key": period_key,
         "status": {"$in": ["pending", "approved"]}}, {"_id": 0})
    if dup:
        raise ValueError(
            f"Sudah ada usul buka periode {closing.get('period_label', period_key)} "
            f"berstatus {dup['status']} — tidak bisa mengajukan dua kali.")

    doc = {
        "id": new_id("plu"),
        "entity_id": entity_id,
        "period_type": period_type,
        "period_key": period_key,
        "period_label": closing.get("period_label", period_key),
        "start_date": start,
        "end_date": end,
        "closing_id": closing.get("id"),
        "reason": reason,
        "status": "pending",
        "requested_by": actor.get("name", "system"),
        "requested_by_id": actor.get("id", ""),
        "requested_at": now_iso(),
        "approved_by": None, "approved_by_id": None, "approved_at": None,
        "window_hours": None, "window_until": None,
        "reject_reason": "", "rejected_by": None, "rejected_at": None,
        "je_ids": [],
        "reclosed_at": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db[COLL].insert_one(dict(doc))
    return safe_doc(doc)


async def approve_request(plu_id: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    rec = await db[COLL].find_one({"id": plu_id}, {"_id": 0})
    if not rec:
        raise ValueError("Usul buka periode tidak ditemukan.")
    if rec.get("status") != "pending":
        raise ValueError(f"Usul ini berstatus '{rec.get('status')}' — hanya usul 'pending' yang bisa disetujui.")
    # DUAL CONTROL: pengusul tidak boleh menyetujui usulnya sendiri.
    if actor.get("id") and actor.get("id") == rec.get("requested_by_id"):
        raise ValueError(
            "Kontrol ganda: pengusul tidak boleh menyetujui usulnya sendiri. "
            "Minta admin/manager LAIN untuk menyetujui.")

    hours = await _cfg_int("periode.unlock_window_hours", rec.get("entity_id"), 24)
    approved_at = _now()
    window_until = approved_at + timedelta(hours=hours)
    upd = {
        "status": "approved",
        "approved_by": actor.get("name", "system"),
        "approved_by_id": actor.get("id", ""),
        "approved_at": approved_at.isoformat(),
        "window_hours": hours,
        "window_until": window_until.isoformat(),
        "updated_at": now_iso(),
    }
    await db[COLL].update_one({"id": plu_id}, {"$set": upd})
    return await db[COLL].find_one({"id": plu_id}, {"_id": 0})


async def reject_request(plu_id: str, actor: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    rec = await db[COLL].find_one({"id": plu_id}, {"_id": 0})
    if not rec:
        raise ValueError("Usul buka periode tidak ditemukan.")
    if rec.get("status") != "pending":
        raise ValueError("Hanya usul 'pending' yang bisa ditolak.")
    await db[COLL].update_one(
        {"id": plu_id},
        {"$set": {"status": "rejected", "reject_reason": (reason or "").strip(),
                  "rejected_by": actor.get("name", "system"),
                  "rejected_at": now_iso(), "updated_at": now_iso()}})
    return await db[COLL].find_one({"id": plu_id}, {"_id": 0})


async def register_backdated_je(plu_id: str, je_id: str) -> None:
    """Catat JE yang lahir dalam jendela unlock (dipanggil gl_service)."""
    if not plu_id or not je_id:
        return
    await db[COLL].update_one(
        {"id": plu_id},
        {"$addToSet": {"je_ids": je_id}, "$set": {"updated_at": now_iso()}})


# ─── auto-reclose (tutup sendiri saat waktunya habis) ──────────────────────
async def reclose_expired(notify: bool = True) -> Dict[str, Any]:
    """Tutup jendela unlock yang sudah lewat batas waktu.

    approved & window_until <= now → status `reclosed` (bila sempat ada JE mundur)
    atau `expired` (bila tidak ada). Bila ada JE mundur, closing-nya sudah otomatis
    ditandai STALE oleh `gl_service._mark_stale_closings` → admin bisa 'Tutup Ulang'.
    """
    now = _now()
    closed = 0
    async for r in db[COLL].find({"status": "approved"}, {"_id": 0}):
        wu = _as_dt(r.get("window_until"))
        if wu and wu > now:
            continue  # masih aktif
        had_je = bool(r.get("je_ids"))
        new_status = "reclosed" if had_je else "expired"
        await db[COLL].update_one(
            {"id": r["id"]},
            {"$set": {"status": new_status, "reclosed_at": now_iso(),
                      "updated_at": now_iso()}})
        closed += 1
        if notify:
            try:
                from services import notification_service as notif
                await notif.create_notification(
                    notif_type="period_unlock_reclosed",
                    title=f"Periode {r.get('period_label', r.get('period_key'))} terkunci lagi",
                    body=(f"Jendela buka periode berakhir. "
                          + (f"{len(r.get('je_ids') or [])} jurnal mundur diposting — "
                             f"periode perlu 'Tutup Ulang' agar laporan sinkron."
                             if had_je else "Tidak ada jurnal mundur diposting.")),
                    severity="warning" if had_je else "info",
                    link="period-unlock", entity_id=r.get("entity_id") or None,
                    recipient_role="admin", ref=f"plureclose:{r['id']}",
                    dedupe_scope="day")
            except Exception:  # noqa: BLE001 — notifikasi best-effort
                pass
    return {"created": 0, "scanned": closed, "reclosed": closed,
            "detail": f"{closed} jendela unlock ditutup otomatis", "at": now_iso()}


async def job_period_unlock_auto_close() -> Dict[str, Any]:
    """Wrapper untuk scheduler (JOBS registry)."""
    return await reclose_expired(notify=True)
