"""FASE G-9 — PUSAT KASUS KEUANGAN (Finance Exception Desk).

MASALAH NYATA
-------------
Uang tidak selalu masuk rapi. Pelanggan salah transfer rekening, transfer ke rekening
pribadi karyawan, bayar dua kali, bayar invoice yang salah, nominal terpotong biaya bank,
giro ditolak, atau uang masuk tanpa identitas. Sebelum fase ini penyelesaiannya hidup di
kepala orang keuangan: tanpa antrean, tanpa SLA, tanpa bukti, dan sering lewat **edit
senyap**. FASE G-8 menutup satu ujungnya (dana tak dikenal masuk akun titipan 2-1950
berikut jurnalnya) — tetapi titipan itu belum punya tempat untuk **diselesaikan**.

DESAIN
------
Satu **kasus bernomor** (`<ENT>/CASE-#####`) per masalah, dengan **playbook** per jenis
(lihat `finance_case_playbooks.py`). Penyelesaian:
1. wajib **alasan berlabel** (taksonomi G-1 `amendment_reasons.applies_to='finance_case'`),
2. wajib **lampiran bukti** untuk jenis yang menyangkut klaim pihak lain,
3. wajib **persetujuan** bila nominalnya di atas ambang (Pusat Pengaturan),
4. selalu **melahirkan dokumen turunan** nyata (jurnal / kas / kwitansi / nota denda),
5. tercatat **dua arah** di peta relasi dokumen (G-4) sehingga auditor bisa menelusuri.

Antreannya **nyata**: `scan()` membuat kasus sendiri dari titipan dana yang menganggur
dan pembayaran yang terlihat dobel — bukan menunggu orang mengetik kasus.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from core_utils import new_id, next_doc_number, now_iso, safe_doc, rupiah
from db import db
from services import finance_case_actions as acts
from services.config_resolver import value_of
from services.finance_case_playbooks import (
    BY_CODE, CASE_TYPES, PLAYBOOKS, action_or_fail, playbook_or_fail,
)

COLL = "finance_cases"
REASON_DOC_TYPE = "finance_case"          # `amendment_reasons.applies_to` (taksonomi G-1)
GROUP_ENTITY = "all"
EPS = 0.01
OPEN_STATUSES = ("open", "in_progress")
STATUSES = ("open", "in_progress", "resolved", "rejected")

CFG_KEYS = (
    "case.sla_hours", "case.sla_hours_high", "case.high_amount_threshold",
    "case.require_evidence", "case.require_approval_above", "case.approver_role",
    "case.refund_max_amount", "case.duplicate_window_days", "case.holding_case_after_days",
    "case.auto_bank_charge_max", "case.escalate_on_sla_breach", "case.auto_scan_enabled",
)


class CaseError(ValueError):
    """Kesalahan kasus keuangan dengan pesan siap tampil (Bahasa Indonesia)."""


def _rp(v: Any) -> str:
    """Alias tipis ke `core_utils.rupiah` — satu sumber format uang untuk seluruh backend."""
    return rupiah(v)


def _round(n: Any) -> float:
    return round(float(n or 0), 2)


# ═════════════════════════════════════════════════════════════════════════════
#  KONFIGURASI (Pusat Pengaturan — tidak ada angka sihir di kode)
# ═════════════════════════════════════════════════════════════════════════════
async def policy(entity_id: str = "") -> Dict[str, Any]:
    ctx = {"entity_id": entity_id or ""}
    raw = {k.split(".", 1)[1]: await value_of(k, ctx) for k in CFG_KEYS}
    return {
        "sla_hours": int(raw.get("sla_hours") or 24),
        "sla_hours_high": int(raw.get("sla_hours_high") or 8),
        "high_amount": float(raw.get("high_amount_threshold") or 0),
        "require_evidence": bool(raw.get("require_evidence")),
        "approval_above": float(raw.get("require_approval_above") or 0),
        "approver_role": str(raw.get("approver_role") or "manager").lower(),
        "refund_max": float(raw.get("refund_max_amount") or 0),
        "dup_window_days": int(raw.get("duplicate_window_days") or 7),
        "holding_days": int(raw.get("holding_case_after_days") or 3),
        "auto_charge_max": float(raw.get("auto_bank_charge_max") or 0),
        "escalate": bool(raw.get("escalate_on_sla_breach")),
        "auto_scan": bool(raw.get("auto_scan_enabled")),
    }


def priority_of(amount: float, pol: Dict[str, Any]) -> str:
    high = float(pol.get("high_amount") or 0)
    return "tinggi" if high > 0 and _round(amount) >= high else "normal"


def sla_hours_of(amount: float, pol: Dict[str, Any]) -> int:
    return int(pol["sla_hours_high"] if priority_of(amount, pol) == "tinggi"
               else pol["sla_hours"])


def _due_at(created_at: str, hours: int) -> str:
    try:
        base = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        base = datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return (base + timedelta(hours=int(hours or 0))).isoformat()


def _age_hours(created_at: str) -> float:
    try:
        base = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - base).total_seconds() / 3600.0, 2)


# ═════════════════════════════════════════════════════════════════════════════
#  LABEL ALASAN & BENTUK KASUS
# ═════════════════════════════════════════════════════════════════════════════
async def reasons() -> List[Dict[str, Any]]:
    from services.amendment_service import ensure_reasons
    await ensure_reasons()
    rows = await db.amendment_reasons.find(
        {"applies_to": REASON_DOC_TYPE, "status": {"$ne": "inactive"}}, {"_id": 0}
    ).sort("label", 1).to_list(100)
    return [safe_doc(r) for r in rows]


async def _reason_labels(codes: List[str]) -> str:
    """Nama-nama label yang sah, untuk pesan penolakan yang MENUNTUN (bukan kode mentah)."""
    if not codes:
        return ""
    rows = await db.amendment_reasons.find(
        {"code": {"$in": list(codes)}}, {"_id": 0, "code": 1, "label": 1}).to_list(50)
    by = {r["code"]: r.get("label") or r["code"] for r in rows}
    return ", ".join(f"\u201c{by.get(c, c)}\u201d" for c in codes)


async def _reason_or_fail(code: str, case_type: str = "") -> Dict[str, Any]:
    """Label alasan WAJIB ada, aktif, milik domain kasus keuangan, DAN nyambung dengan
    jenis kasusnya.

    Kenapa syarat terakhir ditambahkan (temuan penutupan FASE G-9): tanpa itu, kasus
    “Dana masuk tak dikenal” bisa ditutup dengan alasan “Cek / giro ditolak bank”.
    INV-CASE-01 tetap HIJAU karena ia hanya memeriksa ADA alasan, sehingga jejak yang
    dibaca auditor justru menyesatkan. Daftar sahnya = `reason_codes` pada playbook
    (satu sumber kebenaran di `services/finance_case_playbooks.py`).
    """
    code = (code or "").strip()
    if not code:
        raise CaseError(
            "Alasan penyelesaian wajib dipilih — keputusan atas uang harus berlabel "
            "supaya bisa dibaca auditor.")
    row = await db.amendment_reasons.find_one({"code": code}, {"_id": 0})
    if not row or row.get("status") == "inactive":
        raise CaseError(f"Label alasan '{code}' tidak ada / tidak aktif")
    applies = row.get("applies_to") or []
    if REASON_DOC_TYPE not in applies:
        raise CaseError(
            f"Label alasan '{row.get('label', code)}' bukan untuk kasus keuangan")
    allowed = list((BY_CODE.get(case_type or "", {}) or {}).get("reason_codes") or [])
    if allowed and code not in allowed:
        pb_label = BY_CODE.get(case_type, {}).get("label", case_type)
        raise CaseError(
            f"Alasan \u201c{row.get('label', code)}\u201d tidak nyambung dengan jenis kasus "
            f"\u201c{pb_label}\u201d. Alasan yang sah untuk jenis ini: "
            f"{await _reason_labels(allowed)}.")
    return row


def _scope_q(entity_ids: Optional[List[str]]) -> Dict[str, Any]:
    if entity_ids is None:
        return {}
    ids = list(entity_ids)
    if GROUP_ENTITY not in ids:
        ids.append(GROUP_ENTITY)
    return {"entity_id": {"$in": ids}}


async def _enrich(c: Dict[str, Any], pol: Dict[str, Any]) -> Dict[str, Any]:
    pb = BY_CODE.get(c.get("case_type"), {})
    hours = sla_hours_of(c.get("amount"), pol)
    due = c.get("sla_due_at") or _due_at(c.get("created_at", now_iso()), hours)
    overdue = (c.get("status") in OPEN_STATUSES
               and str(due) < now_iso())
    return {
        **safe_doc(c),
        "case_type_label": pb.get("label", c.get("case_type", "")),
        "playbook": pb.get("playbook", []),
        "actions": pb.get("actions", []),
        "moves_cash": bool(pb.get("moves_cash", True)),
        "needs_evidence": bool(pb.get("needs_evidence")),
        "reason_codes": list(pb.get("reason_codes") or []),
        "priority": priority_of(c.get("amount"), pol),
        "sla_hours": hours,
        "sla_due_at": due,
        "age_hours": _age_hours(c.get("created_at", now_iso())),
        "overdue": bool(overdue),
    }


async def get(case_id: str, entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    c = await db[COLL].find_one({"id": case_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Kasus tidak ditemukan")
    ent = c.get("entity_id") or ""
    if entity_ids is not None and ent and ent != GROUP_ENTITY and ent not in entity_ids:
        raise HTTPException(status_code=403, detail="Tidak berwenang atas kasus entitas ini")
    return await _enrich(c, await policy(ent))


async def list_cases(entity_ids: Optional[List[str]] = None, status: str = "",
                     case_type: str = "", assignee: str = "", overdue_only: bool = False,
                     limit: int = 200) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {**_scope_q(entity_ids)}
    if status:
        q["status"] = status
    if case_type:
        q["case_type"] = case_type
    if assignee:
        q["assignee"] = assignee
    rows = await db[COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(int(limit or 200))
    pol = await policy((entity_ids or [""])[0] if entity_ids else "")
    out = [await _enrich(r, pol) for r in rows]
    if overdue_only:
        out = [r for r in out if r["overdue"]]
    # prioritas tinggi & terlambat naik ke atas antrean
    out.sort(key=lambda r: (0 if r["overdue"] else 1,
                            0 if r["priority"] == "tinggi" else 1,
                            str(r.get("created_at") or "")))
    return out


async def stats(entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    rows = await list_cases(entity_ids, limit=2000)
    open_rows = [r for r in rows if r["status"] in OPEN_STATUSES]
    return {
        "total": len(rows),
        "open": len(open_rows),
        "in_progress": len([r for r in rows if r["status"] == "in_progress"]),
        "resolved": len([r for r in rows if r["status"] == "resolved"]),
        "rejected": len([r for r in rows if r["status"] == "rejected"]),
        "overdue": len([r for r in open_rows if r["overdue"]]),
        "money_at_stake": _round(sum(r.get("amount") or 0 for r in open_rows)),
        "oldest_age_hours": max([r["age_hours"] for r in open_rows], default=0),
        "by_type": [
            {"case_type": t, "label": BY_CODE[t]["label"],
             "open": len([r for r in open_rows if r["case_type"] == t]),
             "total": len([r for r in rows if r["case_type"] == t])}
            for t in CASE_TYPES
            if any(r["case_type"] == t for r in rows)
        ],
    }


# ═════════════════════════════════════════════════════════════════════════════
#  SIKLUS: BUAT → TINDAK → SELESAI / TOLAK
# ═════════════════════════════════════════════════════════════════════════════
def _event(event: str, label: str, actor: str = "", note: str = "") -> Dict[str, Any]:
    return {"event": event, "label": label, "actor": actor, "note": note, "at": now_iso()}


async def create_case(payload: Dict[str, Any], actor: Dict[str, Any],
                      entity_ids: Optional[List[str]] = None,
                      active_entity: str = "", auto: str = "") -> Dict[str, Any]:
    pb = playbook_or_fail(payload.get("case_type", ""))
    ent = (payload.get("entity_id") or active_entity or "").strip()
    if entity_ids is not None and ent and ent != GROUP_ENTITY and ent not in entity_ids:
        raise HTTPException(status_code=403, detail="Tidak berwenang membuat kasus entitas ini")
    src = payload.get("source") or {}
    if src.get("id"):
        dup = await db[COLL].find_one(
            {"case_type": pb["code"], "source.id": src["id"],
             "status": {"$in": list(OPEN_STATUSES)}}, {"_id": 0})
        if dup:
            raise CaseError(
                f"Sumber ini sudah punya kasus {dup.get('number')} yang belum selesai — "
                "buka kasus itu, jangan membuat kasus kembar.")
    pol = await policy(ent)
    amount = _round(payload.get("amount"))
    number = await next_doc_number(COLL, "number", "CASE-", entity_id=ent or None)
    now = now_iso()
    doc: Dict[str, Any] = {
        "id": new_id("fcs"), "number": number, "entity_id": ent,
        "case_type": pb["code"], "case_type_label": pb["label"],
        "title": (payload.get("title") or pb["label"]).strip(),
        "description": (payload.get("description") or "").strip(),
        "amount": amount,
        "customer_id": payload.get("customer_id") or "",
        "supplier_id": payload.get("supplier_id") or "",
        "order_ids": list(payload.get("order_ids") or []),
        "source": {"kind": src.get("kind") or "manual", "id": src.get("id") or "",
                   "label": src.get("label") or ""},
        "status": "open", "assignee": payload.get("assignee") or "",
        "attachments": list(payload.get("attachments") or []),
        "sla_hours": sla_hours_of(amount, pol),
        "sla_due_at": _due_at(now, sla_hours_of(amount, pol)),
        "escalation_level": 0, "escalated_at": "",
        "reason_code": "", "reason_label": "",
        "resolution": {}, "documents": [],
        "approved_by": "", "approved_at": "",
        "resolved_by": "", "resolved_at": "",
        "auto_source": auto,
        "timeline": [_event("dibuka", f"Kasus dibuka: {pb['label']}"
                            + (f" (otomatis · {auto})" if auto else ""),
                            actor.get("name", ""), (payload.get("description") or "")[:200])],
        "refs": [],
        "created_by": actor.get("name", ""), "created_at": now, "updated_at": now,
    }
    await db[COLL].insert_one(dict(doc))
    await _link_source(doc)
    await _notify_new(doc)
    return await get(doc["id"], entity_ids)


async def _link_source(doc: Dict[str, Any]) -> None:
    """FASE G-4 — kasus adalah DOKUMEN: menaut sumbernya dua arah."""
    try:
        from services import doc_refs_service as refs
        src = doc.get("source") or {}
        mapping = {"ar_receipt": "ar_receipt", "vendor_bill": "vendor_bill"}
        dst_type = mapping.get(src.get("kind") or "")
        if dst_type and src.get("id"):
            await refs.safe_link(("finance_case", doc["id"]), (dst_type, src["id"]),
                                 "parent", note="kasus keuangan atas dokumen ini")
        for oid in doc.get("order_ids") or []:
            await refs.safe_link(("finance_case", doc["id"]), ("sales_order", oid),
                                 "settles", note="kasus keuangan pesanan ini")
    except Exception:  # noqa: BLE001 — jejak relasi pelengkap, bukan syarat sah
        pass


async def _notify_new(doc: Dict[str, Any]) -> None:
    try:
        from services.notification_service import create_notification
        await create_notification(
            notif_type="finance_case", severity="warning",
            title=f"Kasus keuangan baru: {doc['case_type_label']}",
            body=(f"{doc['number']} · {_rp(doc.get('amount'))} · "
                  f"batas waktu {doc.get('sla_hours')} jam."),
            link="finance-cases", entity_id=doc.get("entity_id") or None,
            recipient_role="manager", ref=doc["id"],
            action_type="finance_case", action_id=doc["id"], action_role="manager")
    except Exception:  # noqa: BLE001
        pass


async def _touch(case_id: str, sets: Dict[str, Any], event: Dict[str, Any]) -> None:
    await db[COLL].update_one({"id": case_id}, {
        "$set": {**sets, "updated_at": now_iso()}, "$push": {"timeline": event}})


async def add_note(case_id: str, note: str, attachments: List[Dict[str, Any]],
                   actor: Dict[str, Any],
                   entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    c = await get(case_id, entity_ids)
    if c["status"] in ("resolved", "rejected"):
        raise CaseError("Kasus sudah ditutup — buka kembali dulu bila perlu ditambah catatan")
    sets: Dict[str, Any] = {}
    if attachments:
        sets["attachments"] = list(c.get("attachments") or []) + list(attachments)
    label = "Catatan ditambahkan"
    if attachments:
        label = f"Bukti dilampirkan ({len(attachments)} berkas)"
    await _touch(case_id, sets, _event("catatan", label, actor.get("name", ""), note))
    return await get(case_id, entity_ids)


async def assign(case_id: str, assignee: str, actor: Dict[str, Any],
                 entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    c = await get(case_id, entity_ids)
    if c["status"] in ("resolved", "rejected"):
        raise CaseError("Kasus sudah ditutup")
    name = (assignee or "").strip()
    await _touch(case_id,
                 {"assignee": name,
                  "status": "in_progress" if c["status"] == "open" else c["status"]},
                 _event("ditugaskan", f"Penanggung jawab: {name or '(dikosongkan)'}",
                        actor.get("name", "")))
    return await get(case_id, entity_ids)


def _assert_evidence(case: Dict[str, Any], pb: Dict[str, Any], pol: Dict[str, Any],
                     extra: List[Dict[str, Any]]) -> None:
    if not (pb.get("needs_evidence") and pol["require_evidence"]):
        return
    if (case.get("attachments") or []) or extra:
        return
    raise CaseError(
        f"Jenis kasus '{pb['label']}' wajib disertai lampiran bukti (mis. foto bukti "
        "transfer atau surat pernyataan) sebelum bisa ditutup.")


def _assert_authority(action: Dict[str, Any], amount: float, pol: Dict[str, Any],
                      actor: Dict[str, Any]) -> str:
    """Ambang nominal & peran untuk penyelesaian yang memindahkan uang keluar."""
    role = (actor.get("role") or "").lower()
    need = pol["approver_role"] or "manager"
    limit = float(pol["approval_above"] or 0)
    amt = _round(amount)
    if limit <= 0 or amt < limit:
        return ""
    if role not in (need, "admin"):
        raise CaseError(
            f"Penyelesaian {_rp(amt)} melebihi ambang persetujuan {_rp(limit)} — "
            f"wajib diputus {need} atau admin. Tugaskan kasus ini ke penyetuju.")
    cap = float(pol["refund_max"] or 0)
    if action.get("sensitive") and cap > 0 and amt > cap + EPS and role != "admin":
        raise CaseError(
            f"Nominal {_rp(amt)} melebihi batas keputusan {need} ({_rp(cap)}) — "
            "harus admin/direksi.")
    return need


async def resolve(case_id: str, payload: Dict[str, Any], actor: Dict[str, Any],
                  entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Jalankan aksi playbook → dokumen turunan nyata → kasus ditutup."""
    case = await get(case_id, entity_ids)
    if case["status"] in ("resolved", "rejected"):
        raise CaseError(f"Kasus {case['number']} sudah berstatus {case['status']}")
    pb = playbook_or_fail(case["case_type"])
    action = action_or_fail(case["case_type"], payload.get("action", ""))
    pol = await policy(case.get("entity_id") or "")
    reason = await _reason_or_fail(payload.get("reason_code", ""),
                                   case.get("case_type", ""))
    _assert_evidence(case, pb, pol, payload.get("attachments") or [])

    amount = _round(payload.get("amount") or case.get("amount"))
    if payload.get("allocations"):
        amount = _round(sum(float(a.get("amount") or 0) for a in payload["allocations"]))
    # Selisih biaya bank kecil boleh selesai tanpa persetujuan (kebijakan admin).
    auto_ok = (case["case_type"] == "selisih_biaya_bank"
               and amount <= float(pol["auto_charge_max"] or 0) + EPS)
    approver = "" if auto_ok else _assert_authority(action, amount, pol, actor)

    try:
        res = await acts.execute(action["code"], case, {**payload, "amount": amount}, actor)
    except acts.CaseActionError as e:
        raise CaseError(str(e)) from e
    docs = res.get("documents") or []
    if not docs:
        raise CaseError(
            "Penyelesaian tidak melahirkan dokumen apa pun — kasus TIDAK ditutup supaya "
            "tidak ada perubahan senyap. Periksa masukan lalu coba lagi.")
    if pb["moves_cash"] and not any(d.get("kind") == "journal_entry" for d in docs):
        raise CaseError(
            "Playbook ini wajib melahirkan jurnal, tetapi tidak ada jurnal yang terbit. "
            "Kasus tidak ditutup (INV-CASE-03).")

    hold = bool(res.get("hold"))                    # playbook 2 langkah (mis. karyawan)
    now = now_iso()
    resolution = {
        "action": action["code"], "action_label": action["label"],
        "effect": action["effect"], "produces": action["produces"],
        "amount": _round(res.get("amount") or amount),
        "note": (payload.get("note") or "").strip(),
        "extra": res.get("extra") or {},
        "next_action": res.get("next_action") or "",
        "auto_resolved": bool(auto_ok),
        "at": now, "by": actor.get("name", ""),
    }
    sets: Dict[str, Any] = {
        "status": "in_progress" if hold else "resolved",
        "reason_code": reason["code"], "reason_label": reason["label"],
        "resolution": {**(case.get("resolution") or {}), **resolution},
        "documents": list(case.get("documents") or []) + docs,
        "approved_by": (actor.get("name", "") if approver else case.get("approved_by", "")),
        "approved_at": (now if approver else case.get("approved_at", "")),
    }
    if payload.get("attachments"):
        sets["attachments"] = list(case.get("attachments") or []) + payload["attachments"]
    if not hold:
        sets.update({"resolved_by": actor.get("name", ""), "resolved_at": now})
    label = (f"Langkah dijalankan: {action['label']}" if hold
             else f"Kasus diselesaikan: {action['label']}")
    await _touch(case_id, sets,
                 _event("selesai" if not hold else "langkah", label, actor.get("name", ""),
                        f"{reason['label']} · {_rp(resolution['amount'])} · "
                        f"{len(docs)} dokumen turunan"))
    await _link_documents(case_id, docs)
    return await get(case_id, entity_ids)


async def _link_documents(case_id: str, docs: List[Dict[str, Any]]) -> None:
    try:
        from services import doc_refs_service as refs
        for d in docs:
            if d.get("kind") == "order_payment" and d.get("id"):
                await refs.safe_link(("finance_case", case_id), ("sales_order", d["id"]),
                                     "settles", note="dilunasi lewat penyelesaian kasus")
            if d.get("kind") == "ar_receipt" and d.get("id"):
                await refs.safe_link(("finance_case", case_id), ("ar_receipt", d["id"]),
                                     "parent", note="kwitansi yang dikoreksi kasus ini")
    except Exception:  # noqa: BLE001
        pass


async def reject(case_id: str, reason_code: str, note: str, actor: Dict[str, Any],
                 entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    case = await get(case_id, entity_ids)
    if case["status"] in ("resolved", "rejected"):
        raise CaseError(f"Kasus {case['number']} sudah berstatus {case['status']}")
    reason = await _reason_or_fail(reason_code, case.get("case_type", ""))
    if not (note or "").strip():
        raise CaseError("Penjelasan wajib diisi saat kasus ditutup tanpa tindakan")
    await _touch(case_id, {
        "status": "rejected", "reason_code": reason["code"],
        "reason_label": reason["label"], "resolved_by": actor.get("name", ""),
        "resolved_at": now_iso(),
    }, _event("ditolak", f"Kasus ditutup tanpa tindakan: {reason['label']}",
              actor.get("name", ""), note))
    return await get(case_id, entity_ids)


async def reopen(case_id: str, note: str, actor: Dict[str, Any],
                 entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    case = await get(case_id, entity_ids)
    if case["status"] not in ("resolved", "rejected"):
        raise CaseError("Kasus ini masih terbuka")
    if case.get("documents"):
        raise CaseError(
            "Kasus yang sudah melahirkan dokumen tidak boleh dibuka ulang (ledger "
            "tambah-saja). Buat kasus baru untuk tindak lanjutnya.")
    await _touch(case_id, {"status": "in_progress", "resolved_by": "", "resolved_at": ""},
                 _event("dibuka_ulang", "Kasus dibuka kembali", actor.get("name", ""), note))
    return await get(case_id, entity_ids)
