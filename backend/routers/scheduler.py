"""R6.5 router — Penjadwal (Scheduler) & Notifikasi + Outbox WhatsApp.

RBAC: permission `scheduler`
  - admin   : view · run · configure
  - manager : view · run
  - sales/warehouse: TIDAK ada akses (403)

Kredensial WhatsApp tidak pernah dikembalikan plaintext (hanya `has_*`).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from db import db
from core_utils import new_id, now_iso
from dependencies import require_permission, audit
from schemas_scheduler import RunJobRequest, SchedulerSettingsUpdate, WaTestRequest
from services import scheduler_service as sched
from services import wa_alert_service as wa
from services import digest_service as digest
from services import escalation_service as escalation

router = APIRouter(prefix="/api")

VALID_PROVIDERS = ("simulated", "meta_cloud", "fonnte")
VALID_SEVERITY = ("info", "warning", "critical")


# ═══ Status & eksekusi job ════════════════════════════════════════════════
@router.get("/scheduler/jobs")
async def list_jobs(request: Request) -> Dict[str, Any]:
    await require_permission(request, "scheduler", "view")
    return await sched.jobs_status()


@router.get("/scheduler/summary")
async def scheduler_summary(request: Request) -> Dict[str, Any]:
    await require_permission(request, "scheduler", "view")
    return await sched.summary()


@router.post("/scheduler/jobs/{job_id}/run")
async def run_job_now(job_id: str, request: Request,
                      payload: Optional[RunJobRequest] = None) -> Dict[str, Any]:
    actor = await require_permission(request, "scheduler", "run")
    if job_id == "all":
        res = await sched.run_all(trigger="manual", actor=actor.get("name", ""))
        await audit(actor["name"], "scheduler_run_all", "scheduler", "all",
                    {"created": res["created"], "failed": res["failed"]})
        return res
    try:
        run = await sched.run_job(job_id, trigger="manual", actor=actor.get("name", ""))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await audit(actor["name"], "scheduler_run", "scheduler", job_id,
                {"status": run["status"], "created": run["created"]})
    return run


@router.get("/scheduler/runs")
async def list_runs(request: Request, job_id: Optional[str] = None,
                    limit: int = 60) -> List[Dict[str, Any]]:
    await require_permission(request, "scheduler", "view")
    return await sched.runs_history(job_id, min(max(int(limit), 1), 300))


# ═══ Pengaturan (jadwal + WhatsApp) ══════════════════════════════════════
@router.get("/scheduler/settings")
async def get_settings(request: Request) -> Dict[str, Any]:
    await require_permission(request, "scheduler", "view")
    st = await wa.raw_settings()
    return {"jobs": await sched.effective_config(), "wa": wa.mask_wa(st["wa"]),
            "escalation": await escalation.effective_config(),
            "providers": list(VALID_PROVIDERS), "severities": list(VALID_SEVERITY),
            "delivery_modes": list(wa.DELIVERY_MODES),
            "timezone": sched.TZ, "updated_at": st.get("updated_at", "")}


@router.get("/scheduler/digest-preview")
async def digest_preview(request: Request, role: str = "admin") -> Dict[str, Any]:
    """Pratinjau isi Ringkasan Harian untuk 1 peran (sebelum mode digest diaktifkan)."""
    await require_permission(request, "scheduler", "view")
    if role not in ("admin", "manager", "sales", "warehouse"):
        raise HTTPException(status_code=400, detail="Peran pratinjau tidak dikenal.")
    return await digest.preview_digest(role=role)


@router.put("/scheduler/settings")
async def update_settings(payload: SchedulerSettingsUpdate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "scheduler", "configure")
    st = await wa.raw_settings()
    set_doc: Dict[str, Any] = {"updated_at": now_iso()}

    # ── Jadwal per job ──
    if payload.jobs:
        jobs = {k: dict(v) for k, v in (st.get("jobs") or {}).items()}
        for jid, cfg in payload.jobs.items():
            if jid not in sched.JOB_MAP:
                raise HTTPException(status_code=400, detail=f"Job '{jid}' tidak dikenal.")
            patch = {k: v for k, v in cfg.model_dump(exclude_unset=True).items() if v is not None}
            jobs[jid] = {**(jobs.get(jid) or {}), **patch}
        set_doc["jobs"] = jobs

    # ── Konfigurasi WhatsApp (kredensial ditangani hati-hati) ──
    if payload.wa:
        cur = dict(st["wa"])
        patch = payload.wa.model_dump(exclude_unset=True)
        if patch.pop("clear_tokens", False):
            cur["access_token"] = ""
            cur["fonnte_token"] = ""
        prov = patch.get("provider")
        if prov and prov not in VALID_PROVIDERS:
            raise HTTPException(status_code=400,
                                detail=f"Provider harus salah satu dari: {', '.join(VALID_PROVIDERS)}.")
        sev = patch.get("min_severity")
        if sev and sev not in VALID_SEVERITY:
            raise HTTPException(status_code=400,
                                detail=f"min_severity harus salah satu dari: {', '.join(VALID_SEVERITY)}.")
        mode = patch.get("delivery_mode")
        if mode and mode not in wa.DELIVERY_MODES:
            raise HTTPException(status_code=400,
                                detail="Mode pengiriman harus 'instant' (per alert) atau "
                                       "'digest' (ringkasan harian).")
        if patch.get("pic_number") and not wa.valid_phone(patch["pic_number"]):
            raise HTTPException(status_code=400,
                                detail="Nomor PIC tidak valid. Contoh: 081234567890.")
        for k, v in patch.items():
            if v is None:
                continue  # None = jangan ubah (khusus token)
            cur[k] = v
        if cur.get("pic_number"):
            cur["pic_number"] = wa.format_id_phone(cur["pic_number"])
        # Validasi kesiapan provider saat WA diaktifkan.
        if cur.get("enabled") and cur.get("provider") == "meta_cloud" \
                and not (cur.get("access_token") and cur.get("phone_number_id")):
            raise HTTPException(status_code=400,
                                detail="Meta Cloud butuh access_token + phone_number_id. "
                                       "Isi kredensial atau pilih provider Simulasi.")
        if cur.get("enabled") and cur.get("provider") == "fonnte" and not cur.get("fonnte_token"):
            raise HTTPException(status_code=400,
                                detail="Fonnte butuh fonnte_token. Isi token atau pilih provider Simulasi.")
        set_doc["wa"] = cur

    # ── Kebijakan eskalasi (R6.6) ──
    if payload.escalation:
        cur_esc = {**escalation.DEFAULT_ESCALATION, **(st.get("escalation") or {})}
        patch_esc = {k: v for k, v in payload.escalation.model_dump(exclude_unset=True).items()
                     if v is not None}
        if "min_severity" in patch_esc and patch_esc["min_severity"] not in VALID_SEVERITY:
            raise HTTPException(status_code=400,
                                detail=f"min_severity eskalasi harus salah satu dari: "
                                       f"{', '.join(VALID_SEVERITY)}.")
        if "after_hours" in patch_esc and not 1 <= int(patch_esc["after_hours"]) <= 72:
            raise HTTPException(status_code=400,
                                detail="Batas waktu eskalasi harus 1–72 jam.")
        if "max_level" in patch_esc and not 1 <= int(patch_esc["max_level"]) <= 3:
            raise HTTPException(status_code=400,
                                detail="Tingkat eskalasi maksimum harus 1–3.")
        cur_esc.update(patch_esc)
        set_doc["escalation"] = cur_esc

    if len(set_doc) == 1:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan dikirim.")

    await db.system_settings.update_one(
        {"scope": wa.SETTINGS_SCOPE},
        {"$set": set_doc, "$setOnInsert": {"id": new_id("set"), "scope": wa.SETTINGS_SCOPE,
                                           "created_at": now_iso()}},
        upsert=True)
    resched = await sched.reschedule()
    new_st = await wa.raw_settings()
    await audit(actor["name"], "scheduler_settings_update", "system_settings", "alerts",
                {"jobs_changed": list((payload.jobs or {}).keys()),
                 "wa_provider": new_st["wa"].get("provider"),
                 "wa_enabled": new_st["wa"].get("enabled"),
                 "delivery_mode": new_st["wa"].get("delivery_mode"),
                 "escalation_changed": bool(payload.escalation),
                 "tokens_changed": bool(payload.wa and (payload.wa.access_token
                                                        or payload.wa.fonnte_token
                                                        or payload.wa.clear_tokens))})
    return {"jobs": await sched.effective_config(), "wa": wa.mask_wa(new_st["wa"]),
            "escalation": await escalation.effective_config(),
            "reschedule": resched, "updated_at": new_st.get("updated_at", "")}


# ═══ Outbox WhatsApp ══════════════════════════════════════════════════════
@router.get("/scheduler/wa-outbox")
async def wa_outbox(request: Request, status: Optional[str] = None,
                    limit: int = 100) -> Dict[str, Any]:
    await require_permission(request, "scheduler", "view")
    return {"items": await wa.outbox_list(status, min(max(int(limit), 1), 500)),
            "stats": await wa.outbox_stats()}


@router.post("/scheduler/wa-outbox/{outbox_id}/retry")
async def wa_retry(outbox_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "scheduler", "run")
    row = await wa.retry_outbox(outbox_id)
    if not row:
        raise HTTPException(status_code=404, detail="Baris outbox tidak ditemukan.")
    await audit(actor["name"], "wa_outbox_retry", "sys_wa_outbox", outbox_id,
                {"status": row.get("status")})
    return row


@router.post("/scheduler/wa-test")
async def wa_test(payload: WaTestRequest, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "scheduler", "configure")
    try:
        row = await wa.send_test(payload.phone, payload.text or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor["name"], "wa_test_send", "sys_wa_outbox", row.get("id", ""),
                {"to": row.get("to"), "status": row.get("status")})
    return row
