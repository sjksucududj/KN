"""FASE G-9 — PEMINDAI KASUS OTOMATIS + PEMERIKSA INVARIAN.

Kenapa ada pemindai: kalau kasus hanya bisa dibuat manual, antrean bergantung pada
kerajinan orang mengetik — dan uang yang nyangkut justru yang paling mudah dilupakan.
Dua sumber temuan yang sudah ada datanya di sistem:

1. **Titipan dana G-8 yang menganggur** (`bank_statement_lines.status='holding'`,
   `holding_remaining > 0`) lebih lama dari `case.holding_case_after_days`.
2. **Pembayaran yang terlihat dobel**: dua kwitansi pelanggan sama, nominal sama, di
   dalam `case.duplicate_window_days`.

Plus **eskalasi SLA**: kasus yang lewat batas waktu dinaikkan ke atasan memakai pola
notifikasi bertingkat yang sama dengan alert operasional (R6.6).

Fungsi `*_violations()` di bawah dipakai `scripts/verify_data_integrity.py`
(**INV-CASE-01..03**) — sengaja ditaruh dekat mesinnya supaya invarian dan pelaksananya
tidak pernah bercerita beda.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core_utils import now_iso, rupiah
from db import db
from services import finance_case_service as svc

COLL = svc.COLL
OPEN = list(svc.OPEN_STATUSES)


def _d(s: Any) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except (TypeError, ValueError):
        return None


def _rp(v: Any) -> str:
    """Alias tipis ke `core_utils.rupiah` — satu sumber format uang untuk seluruh backend."""
    return rupiah(v)


async def _has_open_case(case_type: str, source_id: str) -> bool:
    return bool(await db[COLL].find_one(
        {"case_type": case_type, "source.id": source_id, "status": {"$in": OPEN}},
        {"_id": 1}))


# ═════════════════════════════════════════════════════════════════════════════
#  1 · TITIPAN DANA MENGANGGUR → KASUS
# ═════════════════════════════════════════════════════════════════════════════
async def aged_holding_lines(days: int) -> List[Dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=int(days or 0)))
    rows = await db.bank_statement_lines.find(
        {"status": "holding"}, {"_id": 0}).to_list(5000)
    out = []
    for r in rows:
        rem = round(float(r.get("holding_remaining", r.get("amount")) or 0), 2)
        d = _d(r.get("stmt_date"))
        if rem > 0.01 and d and d <= cutoff:
            out.append({**r, "remaining": rem, "age_days": (cutoff - d).days + int(days or 0)})
    return out


# ═════════════════════════════════════════════════════════════════════════════
#  2 · PEMBAYARAN DOBEL → KASUS
# ═════════════════════════════════════════════════════════════════════════════
async def duplicate_receipts(window_days: int) -> List[Dict[str, Any]]:
    """Kwitansi kembar: pelanggan sama + nominal sama + di dalam jendela hari.

    Yang dilaporkan adalah kwitansi **kedua** (yang lebih baru) karena itulah uang yang
    perlu diputus: dikembalikan atau dipakai untuk pesanan lain.
    """
    rows = await db.ar_receipts.find(
        {"status": {"$ne": "void"}}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    seen: Dict[str, List[Dict[str, Any]]] = {}
    dupes: List[Dict[str, Any]] = []
    for r in rows:
        key = f"{r.get('customer_id')}|{round(float(r.get('amount') or 0), 2)}"
        prev = seen.setdefault(key, [])
        d2 = _d(r.get("receipt_date") or r.get("created_at"))
        for p in prev:
            d1 = _d(p.get("receipt_date") or p.get("created_at"))
            if d1 and d2 and abs((d2 - d1).days) <= int(window_days or 0):
                dupes.append({**r, "twin_id": p.get("id"), "twin_number": p.get("number")})
                break
        prev.append(r)
    return dupes


# ═════════════════════════════════════════════════════════════════════════════
#  3 · ESKALASI SLA
# ═════════════════════════════════════════════════════════════════════════════
async def _escalate(case: Dict[str, Any]) -> bool:
    level = int(case.get("escalation_level") or 0)
    if level >= 2:
        return False
    target = "manager" if level == 0 else "admin"
    try:
        from services.notification_service import create_notification
        await create_notification(
            notif_type="finance_case", severity="critical",
            title=f"ESKALASI: Kasus keuangan terlambat — {case.get('case_type_label', '')}",
            body=(f"{case.get('number')} · {_rp(case.get('amount'))} · batas waktu "
                  f"{case.get('sla_hours')} jam terlewat. Perlu keputusan {target}."),
            link="finance-cases", entity_id=case.get("entity_id") or None,
            recipient_role=target, ref=f"esc:{case.get('id')}:{level + 1}",
            dedupe_scope="day", action_type="finance_case", action_id=case.get("id", ""),
            action_role=target)
    except Exception:  # noqa: BLE001
        return False
    await db[COLL].update_one({"id": case["id"]}, {
        "$set": {"escalation_level": level + 1, "escalated_at": now_iso(),
                 "updated_at": now_iso()},
        "$push": {"timeline": {"event": "eskalasi", "actor": "sistem",
                              "label": f"Melewati batas waktu → dinaikkan ke {target}",
                              "note": "", "at": now_iso()}}})
    return True


# ═════════════════════════════════════════════════════════════════════════════
#  PEMINDAI (job harian & tombol manual)
# ═════════════════════════════════════════════════════════════════════════════
async def scan(actor_name: str = "sistem") -> Dict[str, Any]:
    """Idempoten: dijalankan berkali-kali tidak menggandakan kasus."""
    pol = await svc.policy("")
    made_holding = made_dup = escalated = 0
    skipped = 0
    if not pol["auto_scan"]:
        return {"enabled": False, "holding_cases": 0, "duplicate_cases": 0,
                "escalated": 0, "skipped": 0,
                "note": "Pembuatan kasus otomatis dimatikan di Pusat Pengaturan"}

    actor = {"name": actor_name, "role": "admin"}
    for ln in await aged_holding_lines(pol["holding_days"]):
        if await _has_open_case("dana_tak_dikenal", ln["id"]):
            skipped += 1
            continue
        try:
            await svc.create_case({
                "case_type": "dana_tak_dikenal",
                "title": f"Dana masuk tak dikenal {_rp(ln['remaining'])}",
                "description": (f"Titipan dana dari mutasi bank \"{ln.get('description', '')}\" "
                                f"(pihak: {ln.get('counterparty') or 'tidak diketahui'}) "
                                f"sudah menganggur {ln['age_days']} hari."),
                "amount": ln["remaining"], "entity_id": ln.get("entity_id") or "",
                "customer_id": ln.get("customer_id") or "",
                "source": {"kind": "bank_holding", "id": ln["id"],
                           "label": f"Mutasi {ln.get('stmt_date', '')} · "
                                    f"{ln.get('description', '')[:60]}"},
            }, actor, None, ln.get("entity_id") or "", auto="titipan menganggur")
            made_holding += 1
        except (svc.CaseError, ValueError):
            skipped += 1

    for r in await duplicate_receipts(pol["dup_window_days"]):
        if await _has_open_case("bayar_dobel", r["id"]):
            skipped += 1
            continue
        try:
            await svc.create_case({
                "case_type": "bayar_dobel",
                "title": f"Dugaan pembayaran dobel {_rp(r.get('amount'))}",
                "description": (f"Kwitansi {r.get('number')} bernominal sama dengan "
                                f"{r.get('twin_number')} dari pelanggan yang sama di dalam "
                                f"{pol['dup_window_days']} hari."),
                "amount": round(float(r.get("amount") or 0), 2),
                "entity_id": r.get("entity_id") or "",
                "customer_id": r.get("customer_id") or "",
                "source": {"kind": "ar_receipt", "id": r["id"],
                           "label": f"Kwitansi {r.get('number')}"},
            }, actor, None, r.get("entity_id") or "", auto="kwitansi kembar")
            made_dup += 1
        except (svc.CaseError, ValueError):
            skipped += 1

    if pol["escalate"]:
        for c in await svc.list_cases(None, limit=2000):
            if c["status"] in svc.OPEN_STATUSES and c["overdue"] and await _escalate(c):
                escalated += 1

    return {"enabled": True, "holding_cases": made_holding, "duplicate_cases": made_dup,
            "escalated": escalated, "skipped": skipped, "at": now_iso()}


async def job_finance_case_scan() -> Dict[str, Any]:
    """Job penjadwal (harian) — dipanggil `services/scheduler_service.py`."""
    return await scan("penjadwal")


# ═════════════════════════════════════════════════════════════════════════════
#  PEMERIKSA INVARIAN (dipakai scripts/verify_data_integrity.py)
# ═════════════════════════════════════════════════════════════════════════════
async def resolved_without_documents(limit: int = 20) -> List[Dict[str, Any]]:
    """INV-CASE-01 — kasus `resolved` wajib punya dokumen turunan + alasan + penyelesai."""
    bad = []
    async for c in db[COLL].find({"status": "resolved"}, {"_id": 0}):
        missing = []
        if not (c.get("documents") or []):
            missing.append("dokumen turunan")
        if not (c.get("reason_code") or ""):
            missing.append("alasan berlabel")
        if not (c.get("resolved_by") or ""):
            missing.append("penyelesai")
        if missing:
            bad.append({"number": c.get("number"), "id": c.get("id"),
                        "missing": ", ".join(missing)})
        if len(bad) >= limit:
            break
    return bad


async def aged_holding_without_case(limit: int = 20) -> List[Dict[str, Any]]:
    """INV-CASE-02 — titipan dana menganggur > N hari WAJIB punya kasus terbuka."""
    pol = await svc.policy("")
    bad = []
    for ln in await aged_holding_lines(pol["holding_days"]):
        if not await _has_open_case("dana_tak_dikenal", ln["id"]):
            bad.append({"line_id": ln["id"], "amount": ln["remaining"],
                        "stmt_date": ln.get("stmt_date"),
                        "description": (ln.get("description") or "")[:60]})
        if len(bad) >= limit:
            break
    return bad


async def resolved_without_journal(limit: int = 20) -> List[Dict[str, Any]]:
    """INV-CASE-03 — kasus yang memindahkan uang wajib punya jurnal seimbang.

    Playbook `moves_cash=False` (realokasi antar pesanan) dikecualikan dengan sengaja:
    di buku besar akunnya sama (1-1200 Piutang), jadi jurnal baru justru menyesatkan.
    """
    from services.finance_case_playbooks import BY_CODE
    bad = []
    async for c in db[COLL].find({"status": "resolved"}, {"_id": 0}):
        pb = BY_CODE.get(c.get("case_type")) or {}
        if not pb.get("moves_cash", True):
            continue
        jes = [d for d in (c.get("documents") or []) if d.get("kind") == "journal_entry"]
        if not jes:
            bad.append({"number": c.get("number"), "case_type": c.get("case_type"),
                        "reason": "tidak ada jurnal"})
            if len(bad) >= limit:
                break
            continue
        for j in jes:
            je = await db.journal_entries.find_one({"id": j.get("id")}, {"_id": 0})
            if not je:
                bad.append({"number": c.get("number"), "reason": f"jurnal {j.get('id')} hilang"})
                break
            dr = round(sum(float(x.get("debit") or 0) for x in je.get("lines") or []), 2)
            cr = round(sum(float(x.get("credit") or 0) for x in je.get("lines") or []), 2)
            if abs(dr - cr) > 0.01:
                bad.append({"number": c.get("number"),
                            "reason": f"jurnal {je.get('number')} tidak seimbang "
                                      f"(D {dr} vs K {cr})"})
                break
        if len(bad) >= limit:
            break
    return bad
