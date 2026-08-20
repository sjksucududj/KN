"""R6.5 — Scheduler (APScheduler) untuk alert & notifikasi terjadwal.

DESAIN
- **AsyncIOScheduler** zona **Asia/Jakarta** (WIB) → jadwal harian 08:00 WIB benar-benar
  08:00 WIB, bukan UTC.
- **Guard single-instance**: uvicorn `--reload` menjalankan proses reloader + worker;
  hanya worker yang menjalankan lifespan. Untuk aman ganda, dipakai LOCK dengan
  heartbeat di `system_settings` scope='alerts' (field `lock`). Proses lain yang
  melihat lock masih segar (<180s) TIDAK menjalankan scheduler-nya.
- **Registry job** dideklarasikan sekali (`JOBS`); jadwal & on/off dapat diubah user
  lewat API tanpa mengubah kode.
- Setiap eksekusi dicatat di `sys_scheduler_runs` (histori: durasi, status, jumlah
  notifikasi dibuat, pesan WA ter-antre, error).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso
from services import alert_service as alerts
from services import alert_ops_service as ops        # PS-21 — job operasional
from services import digest_service as digest
from services import escalation_service as escalation
from services import penalty_service as penalties      # FASE G-2 — akrual denda
from services import finance_case_scan as cases        # FASE G-9 — pemindai kasus keuangan
from services import contra_bon_reminder as contrabon  # FASE G-7 — pengingat tukar faktur
from services import interco_reminder as icreminder    # FASE G-6b — pengingat settlement antar-PT
from services import period_unlock_service as punlock   # FASE G-5 — auto-tutup jendela unlock periode
from services import rnd_sla_service as rndsla          # PS-18 — eskalasi SLA sample R&D
from services import approval_reminder as aprem          # 2026-08-15 — pengingat antrean persetujuan
from services import wa_alert_service as wa

logger = logging.getLogger("scheduler")

SETTINGS_SCOPE = "alerts"
TZ = "Asia/Jakarta"
LOCK_TTL_SECONDS = 180
HEARTBEAT_SECONDS = 60
LOCK_RETRY_SECONDS = 30    # coba ambil-alih lock berkala bila sedang dipegang proses lain
_OWNER = f"{os.uname().nodename}:{os.getpid()}"

_scheduler = None          # AsyncIOScheduler | None
_owns_lock = False


# ═══ Registry job ═══════════════════════════════════════════════════════════
JOBS: List[Dict[str, Any]] = [
    {"id": "ar_overdue", "label": "Piutang Jatuh Tempo (AR)",
     "description": "Pindai piutang pelanggan yang lewat jatuh tempo (umur piutang) → notifikasi manager & sales pemegang akun.",
     "kind": "daily", "hour": 8, "minute": 0, "fn": alerts.job_ar_overdue,
     "link": "ar-aging"},
    {"id": "ap_due", "label": "Hutang Supplier Jatuh Tempo (AP)",
     "description": "Tagihan supplier terposting yang jatuh tempo <= 7 hari atau sudah lewat (berdasarkan termin pembayaran supplier).",
     "kind": "daily", "hour": 8, "minute": 5, "fn": alerts.job_ap_due,
     "link": "vendor-bills"},
    {"id": "depreciation_due", "label": "Reminder Penyusutan Aset",
     "description": "Ingatkan bila penyusutan bulan lalu belum dijalankan untuk aset tetap aktif.",
     "kind": "daily", "hour": 8, "minute": 10, "fn": alerts.job_depreciation_due,
     "link": "fixed-assets"},
    {"id": "budget_alert", "label": "Peringatan Anggaran",
     "description": "Anggaran yang TERLAMPAUI atau mendekati batas (realisasi + komitmen PO) per entitas.",
     "kind": "daily", "hour": 8, "minute": 15, "fn": alerts.job_budget_alert,
     "link": "budget"},
    {"id": "production_stalled", "label": "Perintah Kerja Produksi Tertunda",
     "description": "WO dirilis > 3 hari belum selesai, WO draf > 7 hari, atau WO dengan bahan kurang.",
     "kind": "daily", "hour": 8, "minute": 20, "fn": alerts.job_production_stalled,
     "link": "production"},
    {"id": "ops_stalled", "label": "Tugas Gudang Tertunda",
     "description": "Tugas barang masuk/keluar terbuka > 2 hari, diringkas per gudang & arah.",
     "kind": "interval", "interval_hours": 4, "fn": alerts.job_ops_stalled,
     "link": "operations"},
    {"id": "event_scan", "label": "Pindai Event Sistem",
     "description": "Stok menipis, reservasi mendekati kedaluwarsa, dan pesanan/PO menunggu persetujuan.",
     "kind": "interval", "interval_hours": 4, "fn": alerts.job_event_scan,
     "link": "operations"},
    # ── R6.6 ──────────────────────────────────────────────────────────────
    {"id": "escalation_scan", "label": "Eskalasi Alert Belum Ditindak",
     "description": "Peringatan penting yang belum dibaca melewati batas waktu dinaikkan otomatis ke atasan (sales/gudang → manager → admin).",
     "kind": "interval", "interval_hours": 2, "fn": escalation.job_escalation_scan,
     "link": ""},
    {"id": "daily_digest", "label": "Ringkasan Harian (WhatsApp)",
     "description": "Gabungkan seluruh alert hari ini menjadi SATU pesan ringkas per penerima — mencegah staf kebanjiran notifikasi.",
     "kind": "daily", "hour": 8, "minute": 30, "fn": digest.job_daily_digest,
     "link": ""},
    # ── PS-21 (quick win operasional) ─────────────────────────────────────
    {"id": "po_arrival", "label": "Barang PO Datang",
     "description": "Penerimaan barang PO (GR) yang selesai dalam 24 jam terakhir → beri tahu MD/manager, gudang, dan sales yang punya pesanan pendingan atas produk itu.",
     "kind": "interval", "interval_hours": 2, "fn": ops.job_po_arrival,
     "link": "purchasing"},
    {"id": "backorder_ready", "label": "Barang Pendingan Siap",
     "description": "Order dengan pendingan (backorder) yang stoknya sudah tersedia di gudang → beri tahu sales pemegang akun agar bisa follow-up pelanggan.",
     "kind": "interval", "interval_hours": 2, "fn": ops.job_backorder_ready,
     "link": "orders"},
    {"id": "ar_due_soon", "label": "Piutang Mendekati Jatuh Tempo (H-3/H-1/H/H+1)",
     "description": "Ingatkan piutang tepat pada H-3, H-1, hari-H, dan H+1 (melengkapi 'Piutang Jatuh Tempo' yang memindai umur piutang lama). Penyaringan ganda harian mencegah pesan dobel.",
     "kind": "daily", "hour": 7, "minute": 55, "fn": ops.job_ar_due_soon,
     "link": "ar-aging"},
    # ── FASE G-2 ──────────────────────────────────────────────────────────
    {"id": "penalty_accrual", "label": "Hitung Denda Keterlambatan",
     "description": "Pindai seluruh rencana pembayaran aktif; cicilan/milestone yang melewati jatuh tempo + masa tenggang dibuatkan USULAN nota denda (draft, tanpa jurnal) agar masih bisa dinegosiasikan. Idempotent: satu nota per baris per bulan.",
     "kind": "daily", "hour": 7, "minute": 45, "fn": penalties.job_penalty_accrual,
     "link": "payment-plans"},
    # ── FASE G-9 ──────────────────────────────────────────────────────────
    {"id": "finance_case_scan", "label": "Pindai Kasus Keuangan",
     "description": "Cari uang yang nyangkut lalu buatkan kasusnya sendiri: titipan dana tak dikenal yang menganggur lebih lama dari batas, dan pembayaran pelanggan yang terlihat dobel. Kasus yang melewati batas waktu (SLA) dinaikkan ke manager lalu admin. Idempotent: dijalankan berkali-kali tidak menggandakan kasus.",
     "kind": "daily", "hour": 8, "minute": 25, "fn": cases.job_finance_case_scan,
     "link": "finance-cases"},
    # ── FASE G-7 ──────────────────────────────────────────────────────────
    {"id": "contra_bon_reminder", "label": "Pengingat Tukar Faktur (Kontrabon)",
     "description": "Ingatkan H-n sebelum jadwal tukar faktur tiap supplier, berisi jumlah penerimaan barang yang belum ditagih dan tagihan yang siap dikontrabon. Sekaligus menaikkan kontrabon yang menunggu verifikasi/persetujuan lebih lama dari batas waktunya. Idempotent: satu notifikasi per hari per supplier/kontrabon.",
     "kind": "daily", "hour": 7, "minute": 30, "fn": contrabon.job_contra_bon_reminder,
     "link": "contra-bons"},
    # ── FASE G-6b ─────────────────────────────────────────────────────────
    {"id": "interco_settlement_reminder", "label": "Pengingat Settlement Antar-PT",
     "description": "Ingatkan Keuangan bila saldo satu pasangan PT tidak bergerak lebih lama dari batas di Pusat Pengaturan (antar_entitas.settlement_reminder_days). MENGINGATKAN, bukan memaksa — netting tetap dijalankan manual lewat tombol 'Buat Settlement' (keputusan pemilik). Umur saldo dihitung dari aktivitas NYATA (dokumen & settlement terakhir), bukan dari kapan barisnya terakhir dihitung ulang. Idempotent: satu notifikasi per hari per pasangan PT.",
     "kind": "daily", "hour": 7, "minute": 40, "fn": icreminder.job_interco_settlement_reminder,
     "link": "interco-transactions"},
    # ── FASE G-5 ──────────────────────────────────────────────────────────
    {"id": "period_unlock_auto_close", "label": "Tutup Otomatis Jendela Buka Periode",
     "description": "Tutup sendiri jendela 'Buka Periode (Unlock)' yang sudah lewat batas waktu (config periode.unlock_window_hours). Jendela yang sempat dipakai memposting jurnal mundur ditandai 'reclosed' + closing-nya jadi 'basi' agar admin bisa Tutup Ulang; yang tak terpakai jadi 'expired'. Idempotent: hanya menyentuh unlock yang benar-benar sudah lewat.",
     "kind": "interval", "interval_hours": 1, "fn": punlock.job_period_unlock_auto_close,
     "link": "period-unlock"},
    # ── PS-18 ─────────────────────────────────────────────────────────────
    {"id": "rnd_sla_escalation", "label": "Eskalasi SLA Sample R&D",     "description": "Round sample labdip/proofing yang masih berjalan tetapi sudah lewat tenggat diberitahukan ke manager setiap hari; bila keterlambatannya sudah mencapai batas di Pusat Pengaturan (rnd.sla_escalate_admin_days, bawaan 3 hari) notifikasi ikut dinaikkan ke admin/pemilik. Permintaan yang sudah diputus atau dibatalkan dilewati. Idempotent: satu notifikasi per hari per round, jadi boleh dijalankan berkali-kali.",
     "kind": "daily", "hour": 7, "minute": 35, "fn": rndsla.job_rnd_sla_escalation,
     "link": "rnd-reports"},
    # ── PENGINGAT ANTREAN PERSETUJUAN (permintaan pemilik 2026-08-15) ──────
    {"id": "approval_backlog_reminder", "label": "Pengingat Keputusan yang Menunggu",
     "description": "Ingatkan manajer setiap pagi tentang dokumen yang menunggu "
                    "KEPUTUSANNYA paling lama — bukan sekadar jumlah, tetapi nomor "
                    "dokumen, jenis, dan sudah berapa hari menunggu (mis. 'PO-00010 · "
                    "Palembang Silk House — menunggu 12 hari'). Sumber angkanya SAMA "
                    "dengan KPI beranda & Pusat Persetujuan (services/"
                    "approval_backlog_service.py) sehingga tidak mungkin berbeda. "
                    "Ambang umur diatur pemilik di Pusat Pengaturan "
                    "(approval.reminder_min_days, bawaan 2 hari); bila umur dokumen "
                    "sudah ≥ 2× ambang, notifikasi ikut dinaikkan ke admin/pemilik "
                    "karena antreannya bukan menumpuk lagi tetapi MANDEK. Idempotent: "
                    "satu notifikasi per hari per badan usaha.",
     "kind": "daily", "hour": 7, "minute": 45, "fn": aprem.job_approval_backlog_reminder,
     "link": "approval-inbox"},
]
JOB_MAP: Dict[str, Dict[str, Any]] = {j["id"]: j for j in JOBS}


def job_defaults(job: Dict[str, Any]) -> Dict[str, Any]:
    if job["kind"] == "daily":
        return {"enabled": True, "hour": job["hour"], "minute": job["minute"]}
    return {"enabled": True, "interval_hours": job["interval_hours"]}


async def effective_config() -> Dict[str, Dict[str, Any]]:
    """Gabungan default kode + override tersimpan (per job)."""
    st = await wa.raw_settings()
    saved = st.get("jobs") or {}
    out: Dict[str, Dict[str, Any]] = {}
    for job in JOBS:
        cfg = {**job_defaults(job), **(saved.get(job["id"]) or {})}
        out[job["id"]] = cfg
    return out


def schedule_label(job: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    if job["kind"] == "daily":
        return f"Harian {int(cfg.get('hour', 0)):02d}:{int(cfg.get('minute', 0)):02d} WIB"
    return f"Setiap {int(cfg.get('interval_hours', 4))} jam"


# ═══ Histori eksekusi ═══════════════════════════════════════════════════════
async def run_job(job_id: str, trigger: str = "schedule",
                  actor: str = "System") -> Dict[str, Any]:
    """Jalankan 1 job + catat histori. Tidak pernah raise (kecuali job_id tak dikenal)."""
    job = JOB_MAP.get(job_id)
    if not job:
        raise ValueError(f"Job '{job_id}' tidak dikenal.")
    started = time.perf_counter()
    doc: Dict[str, Any] = {
        "id": new_id("srun"), "job_id": job_id, "job_label": job["label"],
        "trigger": trigger, "actor": actor, "started_at": now_iso(),
        "status": "running", "created": 0, "scanned": 0, "wa_queued": 0,
        "detail": "", "error": "", "duration_ms": 0, "finished_at": "",
    }
    wa_before = await db.sys_wa_outbox.count_documents({})
    try:
        res = await job["fn"]()
        wa_after = await db.sys_wa_outbox.count_documents({})
        doc.update({
            "status": "success",
            "created": int(res.get("created", 0) or 0),
            "scanned": int(res.get("scanned", 0) or 0),
            "detail": str(res.get("detail", "") or ""),
            "wa_queued": max(0, wa_after - wa_before),
        })
    except Exception as exc:  # noqa: BLE001 — job gagal tidak boleh mematikan scheduler
        logger.warning("[scheduler] job %s gagal: %s", job_id, exc)
        doc.update({"status": "failed", "error": str(exc)})
    doc["duration_ms"] = int((time.perf_counter() - started) * 1000)
    doc["finished_at"] = now_iso()
    await db.sys_scheduler_runs.insert_one(dict(doc))
    return doc


async def last_runs() -> Dict[str, Dict[str, Any]]:
    """Run terakhir per job (untuk kolom 'Terakhir jalan')."""
    out: Dict[str, Dict[str, Any]] = {}
    for job in JOBS:
        row = await db.sys_scheduler_runs.find_one(
            {"job_id": job["id"]}, {"_id": 0}, sort=[("started_at", -1)])
        if row:
            out[job["id"]] = row
    return out


async def runs_history(job_id: Optional[str] = None, limit: int = 60) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if job_id:
        q["job_id"] = job_id
    return await db.sys_scheduler_runs.find(q, {"_id": 0}).sort("started_at", -1).to_list(int(limit))


# ═══ Lock single-instance ═════════════════════════════════════════════════
def _epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def _owner_alive(owner: str) -> bool:
    """Apakah proses pemegang lock masih hidup?

    Uvicorn `--reload` mematikan worker lama tanpa membersihkan lock, sehingga
    heartbeat bisa terlihat "segar" padahal prosesnya sudah tidak ada → scheduler
    tidak pernah menyala lagi. Untuk owner di NODE INI kita cek `/proc/<pid>`;
    owner dari node lain dianggap hidup (hanya TTL heartbeat yang berlaku).
    """
    try:
        node, pid = str(owner).rsplit(":", 1)
    except ValueError:
        return True
    if node != os.uname().nodename:
        return True
    return os.path.exists(f"/proc/{pid}")


async def _try_acquire_lock() -> bool:
    doc = await db.system_settings.find_one({"scope": SETTINGS_SCOPE}, {"_id": 0, "lock": 1}) or {}
    lock = doc.get("lock") or {}
    fresh = (_epoch() - float(lock.get("heartbeat", 0) or 0)) < LOCK_TTL_SECONDS
    owner = lock.get("owner") or ""
    if fresh and owner != _OWNER and _owner_alive(owner):
        logger.info("[scheduler] lock dipegang %s — instance ini tidak menjadwalkan job.",
                    owner)
        return False
    if fresh and owner != _OWNER:
        # Heartbeat masih segar tetapi PROSES pemegangnya sudah mati (mis. akibat
        # hot-reload uvicorn) → ambil alih sekarang, jangan tunggu TTL habis.
        logger.info("[scheduler] lock basi (proses %s mati) — diambil alih %s.", owner, _OWNER)
    await db.system_settings.update_one(
        {"scope": SETTINGS_SCOPE},
        {"$set": {"lock": {"owner": _OWNER, "heartbeat": _epoch(), "since": now_iso()}},
         "$setOnInsert": {"id": new_id("set"), "scope": SETTINGS_SCOPE,
                          "created_at": now_iso()}},
        upsert=True)
    return True


async def _heartbeat() -> None:
    await db.system_settings.update_one(
        {"scope": SETTINGS_SCOPE}, {"$set": {"lock.owner": _OWNER, "lock.heartbeat": _epoch()}})


# ═══ Start / reschedule ══════════════════════════════════════════════════
async def _apply_jobs() -> int:
    """(Re)daftarkan semua job sesuai konfigurasi efektif. Return jumlah job aktif."""
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    if _scheduler is None:
        return 0
    cfg_all = await effective_config()
    active = 0
    for job in JOBS:
        jid = job["id"]
        cfg = cfg_all[jid]
        try:
            _scheduler.remove_job(jid)
        except Exception:  # noqa: BLE001 — belum terdaftar
            pass
        if not cfg.get("enabled", True):
            continue
        if job["kind"] == "daily":
            trigger = CronTrigger(hour=int(cfg.get("hour", 8)),
                                  minute=int(cfg.get("minute", 0)), timezone=TZ)
        else:
            trigger = IntervalTrigger(hours=int(cfg.get("interval_hours", 4)), timezone=TZ)
        _scheduler.add_job(run_job, trigger=trigger, id=jid, args=[jid],
                           kwargs={"trigger": "schedule"}, replace_existing=True,
                           max_instances=1, coalesce=True, misfire_grace_time=3600)
        active += 1
    return active


async def _boot_scheduler() -> Dict[str, Any]:
    """Buat & jalankan AsyncIOScheduler (dipakai saat startup maupun saat ambil-alih lock)."""
    global _scheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    _scheduler = AsyncIOScheduler(timezone=TZ)
    active = await _apply_jobs()
    _scheduler.add_job(_heartbeat, trigger=IntervalTrigger(seconds=HEARTBEAT_SECONDS),
                       id="__heartbeat__", replace_existing=True, max_instances=1)
    _scheduler.start()
    logger.info("[scheduler] aktif (%s job) zona %s · owner=%s", active, TZ, _OWNER)
    return {"started": True, "jobs": active, "timezone": TZ, "owner": _OWNER}


async def _lock_retry_loop() -> None:
    """Coba ambil-alih lock berkala sampai scheduler benar-benar menyala.

    Tanpa loop ini, satu kali gagal ambil lock (mis. worker lama baru mati) membuat
    scheduler MATI PERMANEN sampai service di-restart manual.
    """
    global _owns_lock
    while True:
        await asyncio.sleep(LOCK_RETRY_SECONDS)
        if _scheduler is not None and _scheduler.running:
            return
        try:
            if await _try_acquire_lock():
                _owns_lock = True
                await _boot_scheduler()
                return
        except Exception as exc:  # noqa: BLE001 — retry berikutnya
            logger.warning("[scheduler] retry lock gagal: %s", exc)


async def start_scheduler() -> Dict[str, Any]:
    """Dipanggil dari lifespan server. Aman bila dipanggil ulang (idempotent)."""
    global _scheduler, _owns_lock
    if _scheduler is not None and _scheduler.running:
        return {"started": True, "already": True, "owner": _OWNER}
    if os.environ.get("KN_DISABLE_SCHEDULER") == "1":
        logger.info("[scheduler] dinonaktifkan via KN_DISABLE_SCHEDULER=1")
        return {"started": False, "reason": "disabled_by_env"}
    _owns_lock = await _try_acquire_lock()
    if not _owns_lock:
        asyncio.create_task(_lock_retry_loop())  # noqa: RUF006 — task siklus hidup app
        return {"started": False, "reason": "lock_held_by_other",
                "retry_in_seconds": LOCK_RETRY_SECONDS}
    return await _boot_scheduler()


async def reschedule() -> Dict[str, Any]:
    """Terapkan ulang jadwal setelah pengaturan diubah user."""
    if _scheduler is None or not _scheduler.running:
        return {"rescheduled": False, "reason": "scheduler_not_running"}
    active = await _apply_jobs()
    return {"rescheduled": True, "jobs": active}


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass
    _scheduler = None


def _next_run(job_id: str) -> str:
    if _scheduler is None:
        return ""
    try:
        j = _scheduler.get_job(job_id)
    except Exception:  # noqa: BLE001
        return ""
    if not j or not getattr(j, "next_run_time", None):
        return ""
    return j.next_run_time.isoformat()


async def jobs_status() -> Dict[str, Any]:
    """Status lengkap untuk UI admin: jadwal, on/off, run terakhir, run berikutnya."""
    cfg_all = await effective_config()
    lasts = await last_runs()
    rows: List[Dict[str, Any]] = []
    for job in JOBS:
        jid = job["id"]
        cfg = cfg_all[jid]
        last = lasts.get(jid) or {}
        rows.append({
            "id": jid, "label": job["label"], "description": job["description"],
            "kind": job["kind"], "link": job.get("link", ""),
            "enabled": bool(cfg.get("enabled", True)),
            "hour": cfg.get("hour"), "minute": cfg.get("minute"),
            "interval_hours": cfg.get("interval_hours"),
            "schedule_label": schedule_label(job, cfg),
            "next_run": _next_run(jid),
            "last_run_at": last.get("started_at", ""),
            "last_status": last.get("status", ""),
            "last_created": last.get("created", 0),
            "last_detail": last.get("detail", ""),
            "last_error": last.get("error", ""),
            "last_duration_ms": last.get("duration_ms", 0),
        })
    return {
        "running": bool(_scheduler is not None and _scheduler.running),
        "owner": _OWNER if _owns_lock else "",
        "timezone": TZ,
        "jobs": rows,
        "generated_at": now_iso(),
    }


async def summary() -> Dict[str, Any]:
    """KPI ringkas untuk header view admin."""
    day = now_iso()[:10]
    runs_today = await db.sys_scheduler_runs.count_documents({"started_at": {"$gte": day}})
    failed_today = await db.sys_scheduler_runs.count_documents(
        {"started_at": {"$gte": day}, "status": "failed"})
    notif_today = await db.notifications.count_documents({"created_at": {"$gte": day}})
    unread = await db.notifications.count_documents({"read": False})
    cfg_all = await effective_config()
    enabled = sum(1 for c in cfg_all.values() if c.get("enabled", True))
    return {
        "jobs_total": len(JOBS), "jobs_enabled": enabled,
        "runs_today": runs_today, "failed_today": failed_today,
        "notifications_today": notif_today, "notifications_unread": unread,
        "wa": await wa.outbox_stats(),
        "delivery_mode": (await wa.raw_settings())["wa"].get("delivery_mode", "instant"),
        "escalation": await escalation.escalation_stats(),
        "running": bool(_scheduler is not None and _scheduler.running),
        "generated_at": now_iso(),
    }


async def run_all(trigger: str = "manual", actor: str = "System") -> Dict[str, Any]:
    """Jalankan SEMUA job aktif berurutan (tombol 'Jalankan Semua')."""
    cfg_all = await effective_config()
    results = []
    for job in JOBS:
        if not cfg_all[job["id"]].get("enabled", True):
            continue
        results.append(await run_job(job["id"], trigger=trigger, actor=actor))
        await asyncio.sleep(0)  # beri ruang event loop
    return {"runs": results, "created": sum(r.get("created", 0) for r in results),
            "failed": sum(1 for r in results if r.get("status") == "failed")}
