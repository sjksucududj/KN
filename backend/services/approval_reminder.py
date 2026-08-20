"""services/approval_reminder.py — PENGINGAT HARIAN "keputusan yang menunggu Anda".

MASALAH NYATA YANG DISELESAIKAN
==============================
Sesi ini menutup `KN-F3-KPI-LIES`: KPI beranda dulu berbunyi **0** padahal 17 dokumen
menunggu keputusan. Angka itu sekarang benar — tetapi angka yang benar **hanya bekerja
kalau orangnya membuka layar**. Manajer yang tidak membuka aplikasi hari itu tetap tidak
tahu bahwa `PO-00010` sudah menunggu 12 hari. Pemilik meminta: *"beri manajer pengingat
harian berisi dokumen yang menunggu keputusannya paling lama"*.

CARA KERJANYA (menumpang infrastruktur yang SUDAH ADA — tidak membangun ulang)
-----------------------------------------------------------------------------
* Antrean & umur tunggu dibaca dari **satu sumber** `approval_backlog_service`
  (`QUEUES` + `AGING_META`) — sumber yang sama dengan KPI beranda, Pusat Persetujuan,
  dan gate `INV-HOME-01`. Jadi pengingat MUSTAHIL menyebut angka yang beda dari layar.
* Notifikasinya dibuat `notification_service.create_notification(dedupe_scope="day")`
  → **idempotent**: dijalankan berkali-kali sehari tidak menggandakan.
* Penjadwalannya dipasang di registry `scheduler_service.JOBS` (`approval_backlog_reminder`)
  sehingga pemilik bisa mengubah jam / mematikannya dari layar **Penjadwal** tanpa kode.
* Ambangnya dikendalikan pemilik lewat Pusat Pengaturan:
  `approval.reminder_min_days` (bawaan 2 hari) — dokumen yang baru masuk hari ini tidak
  perlu langsung diteriaki; yang sudah menua wajib.

KEPADA SIAPA
-----------
Satu notifikasi per badan usaha untuk peran **manager** (pemutus rutin) dan, bila ada
dokumen yang usianya sudah ≥ 2× ambang, salinan untuk **admin/pemilik** — eskalasi
karena berarti antrean sudah benar-benar mandek. Peran lain tidak dikirimi: mengirim
pekerjaan ke orang yang tidak berwenang memutuskan hanya melatih orang mengabaikan
notifikasi.
"""
from typing import Any, Dict, List, Optional

from db import db
from services import approval_backlog_service as abl
from services.config_resolver import value_of
from services.notification_service import create_notification

#: Maksimal dokumen yang disebut di badan notifikasi (sisanya diringkas "+N lagi").
MAX_DISEBUT = 3


async def _min_days(entity_id: Optional[str]) -> int:
    try:
        raw = await value_of("approval.reminder_min_days",
                             {"entity_id": entity_id} if entity_id else None)
        return max(0, int(float(raw)))
    except Exception:  # noqa: BLE001 — setting belum ada → pakai bawaan aman
        return 2


async def _entities() -> List[str]:
    """Badan usaha aktif. Pengingat dikirim PER badan usaha supaya angkanya bisa dipakai."""
    try:
        rows = await db.business_entities.find(
            {"status": {"$ne": "archived"}}, {"_id": 0, "id": 1}).to_list(200)
        return [r["id"] for r in rows if r.get("id")]
    except Exception:  # noqa: BLE001
        return []


def _ringkas(rows: List[Dict[str, Any]]) -> str:
    """Badan notifikasi: sebut dokumennya, bukan sekadar jumlah."""
    baris = [f"• {r['number']} · {r['queue_label'].replace(' menunggu ACC', '')} · "
             f"{r['title'][:38]} — menunggu {r['days_waiting']} hari"
             for r in rows[:MAX_DISEBUT]]
    sisa = len(rows) - MAX_DISEBUT
    if sisa > 0:
        baris.append(f"• +{sisa} dokumen lain menunggu")
    return "\n".join(baris)


async def remind_entity(entity_id: str) -> Dict[str, Any]:
    """Hitung & kirim pengingat untuk SATU badan usaha. Dipisah supaya bisa diuji."""
    min_days = await _min_days(entity_id)
    data = await abl.backlog(entity_id, with_oldest=True, oldest_limit=25)
    tua = [r for r in (data.get("oldest") or []) if r["days_waiting"] >= min_days]
    if not tua:
        return {"entity_id": entity_id, "total": data.get("total", 0),
                "min_days": min_days, "matched": 0, "created": 0, "escalated": 0}

    tertua = tua[0]
    title = (f"{len(tua)} dokumen menunggu keputusan — tertua "
             f"{tertua['days_waiting']} hari")
    body = (_ringkas(tua) + f"\n\nBuka Pusat Persetujuan untuk memutuskan "
            f"({data.get('total', 0)} dokumen menunggu di badan usaha ini).")
    # `critical` bila sudah 2× ambang: antrean bukan lagi "menumpuk", tapi mandek.
    escalate = tertua["days_waiting"] >= max(1, min_days) * 2
    note = await create_notification(
        notif_type="approval_backlog", ref=f"approval_backlog:{entity_id}",
        title=title, body=body, severity="critical" if escalate else "warning",
        link="approval-inbox", entity_id=entity_id, recipient_role="manager",
        dedupe_scope="day",
    )
    created = 1 if note else 0
    escalated = 0
    if escalate:
        note2 = await create_notification(
            notif_type="approval_backlog", ref=f"approval_backlog_admin:{entity_id}",
            title=f"Antrean persetujuan MANDEK — tertua {tertua['days_waiting']} hari",
            body=(body + "\n\nDinaikkan ke admin/pemilik karena umurnya sudah "
                  f"≥ 2× ambang pengingat ({min_days} hari)."),
            severity="critical", link="approval-inbox", entity_id=entity_id,
            recipient_role="admin", dedupe_scope="day",
        )
        escalated = 1 if note2 else 0
    return {"entity_id": entity_id, "total": data.get("total", 0), "min_days": min_days,
            "matched": len(tua), "created": created, "escalated": escalated,
            "oldest_days": tertua["days_waiting"], "oldest_number": tertua["number"]}


async def job_approval_backlog_reminder() -> Dict[str, Any]:
    """JOB harian: ingatkan pemutus tentang keputusan yang paling lama menunggu."""
    hasil = [await remind_entity(eid) for eid in await _entities()]
    return {
        "entities": len(hasil),
        "notified": sum(h["created"] for h in hasil),
        "escalated": sum(h["escalated"] for h in hasil),
        "detail": hasil,
    }
