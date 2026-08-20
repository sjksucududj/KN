"""FASE G-6b — **PENGINGAT SETTLEMENT** saldo antar-PT yang menganggur.

KEPUTUSAN PEMILIK YANG DIHORMATI (2026-07-30 #3)
------------------------------------------------
Ritme settlement tetap **sewaktu-waktu lewat tombol** — TIDAK ADA job yang
melakukan netting otomatis. Yang dijadwalkan hanyalah **pengingat**: bila saldo
satu pasangan PT tidak bergerak lebih lama dari `antar_entitas.settlement_reminder_days`,
Keuangan diberi tahu. Mengingatkan, bukan memaksa.

BUG NYATA YANG IKUT DITUTUP — `KN-G6-IDLE-FAKE`
-----------------------------------------------
`aging_days` sebelumnya dihitung dari `interco_accounts.updated_at`. Field itu
ikut berubah setiap kali saldo **dihitung ulang** (mis. saat pasangan PT yang
sama menerbitkan transaksi baru, saat settlement, atau saat data demo di-seed),
jadi angka "umur" bisa kembali 0 tanpa ada uang yang benar-benar bergerak — dan
sebuah saldo yang menganggur 6 bulan bisa tampak baru. Sekarang umur dihitung
dari **aktivitas nyata**: tanggal dokumen terbuka terakhir dan tanggal settlement
terakhir untuk pasangan itu (`last_activity_at`), sehingga kalimat "menganggur N
hari" berarti apa yang ia katakan.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core_utils import now_iso, rupiah
from db import db
from services import interco_service as ics
from services import notification_service as notif

EPS = 0.01


def _days_since(iso: str) -> int:
    if not iso:
        return 0
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:  # noqa: BLE001
        return 0


async def last_activity_at(seller_entity_id: str, buyer_entity_id: str) -> str:
    """Aktivitas NYATA terakhir pasangan PT: dokumen terbuka & settlement.

    Dipakai untuk "umur saldo" — bukan `updated_at` baris saldo (lihat KN-G6-IDLE-FAKE).
    """
    stamps: List[str] = []
    docs = await db[ics.COLL_ICT].find(
        {"seller_entity_id": seller_entity_id, "buyer_entity_id": buyer_entity_id,
         "role": "seller", "status": {"$in": list(ics.OPEN_STATUSES)}},
        {"_id": 0, "doc_date": 1, "confirmed_at": 1, "created_at": 1,
         "invoiced_at": 1, "received_at": 1}).to_list(2000)
    for d in docs:
        for k in ("invoiced_at", "received_at", "confirmed_at", "created_at", "doc_date"):
            if d.get(k):
                stamps.append(str(d[k])[:10])
                break
    sets = await db[ics.COLL_ICS].find(
        {"$or": [
            {"payer_entity_id": buyer_entity_id, "payee_entity_id": seller_entity_id},
            {"payer_entity_id": seller_entity_id, "payee_entity_id": buyer_entity_id},
        ]}, {"_id": 0, "settle_date": 1, "created_at": 1}).to_list(2000)
    for s in sets:
        stamps.append(str(s.get("settle_date") or s.get("created_at") or "")[:10])
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else ""


async def idle_pairs(scope_entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Pasangan PT yang saldonya menganggur melewati batas config.

    Satu baris per ARAH DAGANG (bukan dua) supaya pengingatnya tidak dobel: kami
    memakai sisi `payable` — pihak yang harus membayar adalah pihak yang perlu
    diingatkan lebih dulu. Bila dua PT berdagang DUA ARAH, keduanya memang punya
    utang masing-masing dan keduanya layak diingatkan; barisnya terpisah karena
    identitas saldo memuat arah dagang (lihat KN-G6-ICA-CLOBBER).
    """
    q: Dict[str, Any] = {"role": "payable"}
    if scope_entity_ids:
        q["$or"] = [{"from_entity_id": {"$in": scope_entity_ids}},
                    {"to_entity_id": {"$in": scope_entity_ids}}]
    rows = await db[ics.COLL_ICA].find(q, {"_id": 0}).to_list(2000)
    out: List[Dict[str, Any]] = []
    for r in rows:
        outstanding = float(r.get("outstanding") or 0)
        if outstanding <= EPS:
            continue
        payer = r.get("from_entity_id", "")        # PT pembeli (yang berutang)
        payee = r.get("to_entity_id", "")          # PT penjual
        limit = int(await ics._config("antar_entitas.settlement_reminder_days", payer) or 30)
        act = r.get("last_activity_at") or await last_activity_at(payee, payer)
        idle = _days_since(act) if act else _days_since(r.get("updated_at", ""))
        row = {
            "ica_id": r.get("id"),
            "payer_entity_id": payer,
            "payer_entity_name": r.get("from_entity_name", ""),
            "payee_entity_id": payee,
            "payee_entity_name": r.get("to_entity_name", ""),
            "outstanding": round(outstanding, 2),
            "open_count": int(r.get("open_count") or 0),
            "last_activity_at": act,
            "idle_days": idle,
            "limit_days": limit,
            "overdue": bool(limit >= 0 and idle >= limit),
        }
        out.append(row)
    out.sort(key=lambda x: (-x["idle_days"], -x["outstanding"]))
    return {"rows": out, "overdue": [r for r in out if r["overdue"]],
            "checked": len(out)}


def _body(row: Dict[str, Any]) -> str:
    since = f" (aktivitas terakhir {row['last_activity_at']})" if row.get("last_activity_at") else ""
    return (f"{row['payer_entity_name']} masih berutang {rupiah(row['outstanding'])} ke "
            f"{row['payee_entity_name']} dari {row['open_count']} dokumen antar-PT, dan "
            f"saldonya tidak bergerak {row['idle_days']} hari{since} — melewati batas "
            f"{row['limit_days']} hari. Buka Saldo Antar-PT lalu tekan "
            f"\u201cBuat Settlement\u201d bila memang sudah waktunya (netting tidak pernah "
            f"dijalankan otomatis).")


async def remind_pair(payer_entity_id: str, payee_entity_id: str,
                      actor: str = "", force: bool = True) -> Dict[str, Any]:
    """Kirim pengingat untuk SATU pasangan PT (tombol \u201cIngatkan\u201d di layar)."""
    acc = await ics.get_account(payer_entity_id, payee_entity_id, role="payable")
    outstanding = float(acc.get("outstanding") or 0)
    if outstanding <= EPS:
        raise ics.IntercoError(
            "Saldo pasangan PT ini sudah nol — tidak ada yang perlu diingatkan.")
    act = await last_activity_at(payee_entity_id, payer_entity_id)
    limit = int(await ics._config("antar_entitas.settlement_reminder_days",
                                 payer_entity_id) or 30)
    idle = _days_since(act) if act else _days_since(acc.get("updated_at", ""))
    row = {
        "payer_entity_id": payer_entity_id,
        "payer_entity_name": acc.get("from_entity_name", ""),
        "payee_entity_id": payee_entity_id,
        "payee_entity_name": acc.get("to_entity_name", ""),
        "outstanding": round(outstanding, 2),
        "open_count": int(acc.get("open_count") or 0),
        "last_activity_at": act, "idle_days": idle, "limit_days": limit,
    }
    n = await notif.create_notification(
        notif_type="interco_settlement_idle",
        title=(f"Saldo antar-PT menganggur: {row['payer_entity_name']} → "
               f"{row['payee_entity_name']}"),
        body=_body(row), severity="warning", link="interco-transactions",
        entity_id=payer_entity_id or None, recipient_role="manager",
        ref=f"icidle:{payer_entity_id}:{payee_entity_id}",
        dedupe_scope="unread" if force else "day")
    return {**row, "notified": bool(n),
            "notification_id": (n or {}).get("id", ""),
            "deduped": n is None,
            "requested_by": actor}


# ═════════════════════════════════════════════════════════════════════════════
#  JOB SCHEDULER — hanya MENGINGATKAN (tidak pernah melakukan netting)
# ═════════════════════════════════════════════════════════════════════════════
async def job_interco_settlement_reminder() -> Dict[str, Any]:
    """Pengingat harian untuk saldo antar-PT yang menganggur melewati batas."""
    data = await idle_pairs(None)
    created = 0
    for row in data["overdue"]:
        n = await notif.create_notification(
            notif_type="interco_settlement_idle",
            title=(f"Saldo antar-PT menganggur: {row['payer_entity_name']} → "
                   f"{row['payee_entity_name']}"),
            body=_body(row), severity="warning", link="interco-transactions",
            entity_id=row["payer_entity_id"] or None, recipient_role="manager",
            ref=f"icidle:{row['payer_entity_id']}:{row['payee_entity_id']}",
            dedupe_scope="day")
        created += 1 if n else 0
    return {"notifications": created, "pairs_checked": data["checked"],
            "pairs_overdue": len(data["overdue"]), "at": now_iso()}
