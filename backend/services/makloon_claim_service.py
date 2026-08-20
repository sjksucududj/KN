"""FASE D — SELISIH & KLAIM MAKLOON (PS-11 · keputusan **D-09**).

SSOT (KN_18 §5.3): klaim disimpan **di dalam** `makloon_orders.steps[].claim`
(bukan koleksi baru) — turunannya: vendor bill (potong bon) + jurnal GL.

Keputusan pemilik: **semua tindakan tersedia** dan **wajib approval manager/admin**:
  * `potong_bon`     — kurangi tagihan jasa mitra → Dr Hutang Usaha / Cr Pendapatan Klaim.
  * `tagih_ganti`    — tagih ganti rugi → Dr Piutang Klaim Mitra / Cr Pendapatan Klaim.
  * `terima_catatan` — diterima apa adanya: TIDAK ada jurnal baru karena kerugian sudah
    terserap ke HPP output saat penerimaan (WIP di-clear penuh ke persediaan). Alasan
    wajib dicatat agar audit jelas.

Alur status: `open` (otomatis saat selisih lewat toleransi) → `pending_approval`
(diajukan dengan tindakan+nilai) → `approved` (dieksekusi) | `rejected`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import domain_registry as dr
from core_utils import now_iso, parse_decimal, safe_doc, rupiah
from db import db
from services import contract_service as cs
from services import gl_service as gl
from services import notification_service as notif

COLL = "makloon_orders"

CLAIM_STATUSES = ("none", "open", "pending_approval", "approved", "rejected")
ACTIONS = tuple(a["value"] for a in dr.CLAIM_ACTIONS)   # potong_bon|tagih_ganti|terima_catatan


class ClaimError(Exception):
    """Pelanggaran aturan klaim (dipetakan ke HTTP 400/403 di router)."""


def _find_step(order: Dict[str, Any], seq: int) -> Dict[str, Any]:
    for s in order.get("steps", []):
        if int(s.get("seq")) == int(seq):
            return s
    raise ClaimError(f"Langkah {seq} tidak ada pada order makloon ini.")


async def _get_order(mko_id: str) -> Dict[str, Any]:
    o = await db[COLL].find_one({"id": mko_id}, {"_id": 0})
    if not o:
        raise ClaimError("Order makloon tidak ditemukan.")
    return o


def blank_claim() -> Dict[str, Any]:
    return {"status": "none", "required": False, "action": "", "amount": 0.0,
            "amount_suggested": 0.0, "reason": "", "history": []}


def build_claim_from_variance(variance: Dict[str, Any], *, auto_open: bool = True) -> Dict[str, Any]:
    """Bentuk objek klaim dari hasil evaluasi selisih (dipakai saat receive)."""
    claim = blank_claim()
    claim.update({
        "variance_qty": variance.get("variance_qty"),
        "variance_pct": variance.get("variance_pct"),
        "tolerance_pct": variance.get("tolerance_pct"),
        "shortfall_qty": variance.get("shortfall_qty"),
        "unit": variance.get("unit", ""),
        "unit_value": variance.get("unit_value", 0.0),
        "amount_suggested": variance.get("shortfall_value", 0.0),
        "message": variance.get("message", ""),
    })
    if variance.get("claim_required"):
        claim["required"] = True
        claim["status"] = "open" if auto_open else "none"
        claim["opened_at"] = now_iso()
        claim["history"] = [{"at": now_iso(), "event": "opened", "actor": "system",
                             "note": variance.get("message", "")}]
    return claim


async def notify_claim_opened(order: Dict[str, Any], step: Dict[str, Any]) -> None:
    """Eskalasi ke penyetuju (mesin notifikasi R6.5/R6.6) — best-effort."""
    claim = step.get("claim") or {}
    settings = await cs.get_settings()
    roles = settings.get("claim_approval_roles") or ["manager", "admin"]
    for role in roles:
        try:
            await notif.create_notification(
                notif_type="makloon_claim",
                title=f"Selisih makloon {order.get('mko_number')} langkah {step.get('seq')}",
                body=(f"{step.get('makloon_name') or 'Mitra'} · {claim.get('message') or ''} "
                      f"Perlu keputusan: potong bon / tagih ganti rugi / terima dengan catatan."),
                severity="warning", link="makloon-orders",
                entity_id=order.get("entity_id"), recipient_role=role,
                ref=f"{order.get('id')}:{step.get('seq')}",
                action_type="makloon_claim", action_id=order.get("id"), action_role=role)
        except Exception:  # noqa: BLE001 — notifikasi tidak boleh menggagalkan transaksi
            pass


async def propose_claim(mko_id: str, seq: int, *, action: str, amount: Any = None,
                        reason: str = "", actor: str = "system") -> Dict[str, Any]:
    """Ajukan tindakan klaim (butuh persetujuan manager/admin sebelum dieksekusi)."""
    action = (action or "").strip().lower()
    if action not in ACTIONS:
        raise ClaimError(f"Tindakan klaim harus salah satu: {', '.join(ACTIONS)}.")
    order = await _get_order(mko_id)
    step = _find_step(order, seq)
    claim = step.get("claim") or blank_claim()
    if claim.get("status") == "approved":
        raise ClaimError("Klaim langkah ini sudah disetujui & dieksekusi.")
    if not reason.strip():
        raise ClaimError("Alasan klaim wajib diisi (jejak audit D-09).")
    amt = parse_decimal(amount if amount is not None else claim.get("amount_suggested") or 0, 2)
    if action != "terima_catatan" and amt <= 0:
        raise ClaimError("Nilai klaim harus lebih besar dari 0 untuk potong bon / ganti rugi.")
    if action == "terima_catatan":
        amt = 0.0
    claim.update({"status": "pending_approval", "action": action, "amount": amt,
                  "reason": reason.strip(), "proposed_by": actor, "proposed_at": now_iso()})
    claim.setdefault("history", []).append(
        {"at": now_iso(), "event": "proposed", "actor": actor,
         "note": f"{dr.label_of('claim_action', action)} · {rupiah(amt)} · {reason.strip()}"})
    step["claim"] = claim
    await _save(order)
    for role in (await cs.get_settings()).get("claim_approval_roles", ["manager", "admin"]):
        try:
            await notif.create_notification(
                notif_type="makloon_claim_approval",
                title=f"Persetujuan klaim makloon {order.get('mko_number')} langkah {seq}",
                body=f"{dr.label_of('claim_action', action)} · {rupiah(amt)} · {reason.strip()}",
                severity="warning", link="makloon-orders", entity_id=order.get("entity_id"),
                recipient_role=role, ref=f"claimapv:{mko_id}:{seq}",
                action_type="makloon_claim_approve", action_id=mko_id, action_role=role)
        except Exception:  # noqa: BLE001
            pass
    return safe_doc(order)


async def approve_claim(mko_id: str, seq: int, *, actor: str = "system",
                        actor_role: str = "", note: str = "") -> Dict[str, Any]:
    """Setujui & EKSEKUSI klaim (GL + potong tagihan). Hanya peran penyetuju."""
    settings = await cs.get_settings()
    roles = [r.lower() for r in settings.get("claim_approval_roles", ["manager", "admin"])]
    if actor_role and actor_role.lower() not in roles:
        raise ClaimError(f"Hanya peran {', '.join(roles)} yang boleh menyetujui klaim makloon.")
    order = await _get_order(mko_id)
    step = _find_step(order, seq)
    claim = step.get("claim") or blank_claim()
    if claim.get("status") != "pending_approval":
        raise ClaimError("Tidak ada pengajuan klaim yang menunggu persetujuan pada langkah ini.")
    action = claim.get("action")
    amount = parse_decimal(claim.get("amount"), 2)
    effect: Dict[str, Any] = {"action": action, "amount": amount, "journal_id": "",
                              "bill_id": "", "accounting_effect": "none"}

    if action == "potong_bon":
        bill_id = step.get("service_bill_id") or ""
        if not bill_id:
            raise ClaimError("Tidak ada tagihan jasa pada langkah ini — potong bon tidak bisa "
                             "dijalankan. Pilih 'tagih ganti rugi' atau 'terima dengan catatan'.")
        bill = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
        if not bill:
            raise ClaimError("Tagihan jasa makloon tidak ditemukan.")
        grand = parse_decimal(bill.get("grand_total"), 2)
        paid = parse_decimal(bill.get("amount_paid"), 2)
        max_deduct = round(grand - paid, 2)
        if amount > max_deduct:
            raise ClaimError(f"Potongan {rupiah(amount)} melebihi sisa tagihan {rupiah(max_deduct)}.")
        je = await gl.post_makloon_claim(mko_id=mko_id, step_seq=seq,
                                         entity_id=order.get("entity_id", ""), action=action,
                                         amount=amount,
                                         label=f"{order.get('mko_number')} step{seq}")
        await db.vendor_bills.update_one({"id": bill_id}, {
            "$set": {"net_amount": round(parse_decimal(bill.get("net_amount"), 2) - amount, 2),
                     "grand_total": round(grand - amount, 2),
                     "claim_deduction": round(parse_decimal(bill.get("claim_deduction"), 2) + amount, 2),
                     "updated_at": now_iso()},
            "$push": {"deductions": {"at": now_iso(), "amount": amount, "by": actor,
                                     "reason": claim.get("reason", ""),
                                     "mko_id": mko_id, "step_seq": seq}}})
        effect.update({"journal_id": (je or {}).get("id", ""), "bill_id": bill_id,
                       "accounting_effect": "ap_reduced",
                       "bill_new_total": round(grand - amount, 2)})
    elif action == "tagih_ganti":
        je = await gl.post_makloon_claim(mko_id=mko_id, step_seq=seq,
                                         entity_id=order.get("entity_id", ""), action=action,
                                         amount=amount,
                                         label=f"{order.get('mko_number')} step{seq}")
        effect.update({"journal_id": (je or {}).get("id", ""),
                       "accounting_effect": "claim_receivable"})
    else:  # terima_catatan
        effect["accounting_effect"] = "none"
        effect["note"] = ("Kerugian sudah terserap ke HPP output saat penerimaan "
                          "(WIP di-clear penuh) — tidak ada jurnal tambahan.")

    claim.update({"status": "approved", "approved_by": actor, "approved_at": now_iso(),
                  "approval_note": note, "effect": effect})
    claim.setdefault("history", []).append(
        {"at": now_iso(), "event": "approved", "actor": actor,
         "note": note or dr.label_of("claim_action", action)})
    step["claim"] = claim
    await _save(order)
    await _close_claim_notices(mko_id, "disetujui", actor)
    return safe_doc(order)


async def reject_claim(mko_id: str, seq: int, *, reason: str, actor: str = "system",
                       actor_role: str = "") -> Dict[str, Any]:
    settings = await cs.get_settings()
    roles = [r.lower() for r in settings.get("claim_approval_roles", ["manager", "admin"])]
    if actor_role and actor_role.lower() not in roles:
        raise ClaimError(f"Hanya peran {', '.join(roles)} yang boleh menolak klaim makloon.")
    if not (reason or "").strip():
        raise ClaimError("Alasan penolakan wajib diisi.")
    order = await _get_order(mko_id)
    step = _find_step(order, seq)
    claim = step.get("claim") or blank_claim()
    if claim.get("status") != "pending_approval":
        raise ClaimError("Tidak ada pengajuan klaim yang menunggu persetujuan pada langkah ini.")
    claim.update({"status": "rejected", "rejected_by": actor, "rejected_at": now_iso(),
                  "rejected_reason": reason.strip()})
    claim.setdefault("history", []).append(
        {"at": now_iso(), "event": "rejected", "actor": actor, "note": reason.strip()})
    step["claim"] = claim
    await _save(order)
    await _close_claim_notices(mko_id, "ditolak", actor)
    return safe_doc(order)


async def _close_claim_notices(mko_id: str, outcome: str, actor: str) -> None:
    """Padamkan notifikasi klaim yang sudah diputus (lonceng tidak boleh berbohong)."""
    for atype in ("makloon_claim_approve", "makloon_claim"):
        try:
            await notif.resolve_action(atype, mko_id, outcome=outcome, actor=actor)
        except Exception:  # noqa: BLE001
            continue


async def _save(order: Dict[str, Any]) -> None:
    order["updated_at"] = now_iso()
    order["claim_summary"] = summarize(order)
    await db[COLL].replace_one({"id": order["id"]}, order)


def summarize(order: Dict[str, Any]) -> Dict[str, Any]:
    open_n = pending = approved = rejected = 0
    amount = 0.0
    for s in order.get("steps", []):
        c = s.get("claim") or {}
        st = c.get("status")
        if st == "open":
            open_n += 1
        elif st == "pending_approval":
            pending += 1
        elif st == "approved":
            approved += 1
            amount += parse_decimal(c.get("amount"), 2)
        elif st == "rejected":
            rejected += 1
    return {"open": open_n, "pending_approval": pending, "approved": approved,
            "rejected": rejected, "approved_amount": round(amount, 2),
            "needs_action": open_n + pending}


async def list_claims(query: Dict[str, Any], *, status: str = "",
                      limit: int = 200) -> List[Dict[str, Any]]:
    """Daftar klaim lintas order (layar persetujuan manajer)."""
    flt = dict(query or {})
    rows = await db[COLL].find(flt, {"_id": 0}).sort("created_at", -1).to_list(1000)
    out: List[Dict[str, Any]] = []
    for o in rows:
        for s in o.get("steps", []):
            c = s.get("claim") or {}
            if c.get("status") in (None, "", "none"):
                continue
            if status and c.get("status") != status:
                continue
            out.append({
                "mko_id": o.get("id"), "mko_number": o.get("mko_number"),
                "entity_id": o.get("entity_id"), "step_seq": s.get("seq"),
                "process_type": s.get("process_type"),
                "makloon_id": s.get("makloon_id"), "makloon_name": s.get("makloon_name"),
                "output_name": s.get("output_name"), "output_unit": s.get("output_unit"),
                "expected_output_qty": s.get("expected_output_qty"),
                "actual_output_qty": s.get("actual_output_qty"),
                "contract_id": s.get("contract_id", ""),
                "contract_number": s.get("contract_number", ""),
                "service_bill_id": s.get("service_bill_id", ""),
                "claim": c, "received_at": s.get("received_at", ""),
            })
            if len(out) >= limit:
                return out
    return out


async def claim_stats(query: Dict[str, Any]) -> Dict[str, Any]:
    rows = await list_claims(query, limit=1000)
    total_amount = round(sum(parse_decimal((r["claim"] or {}).get("amount"), 2)
                             for r in rows if (r["claim"] or {}).get("status") == "approved"), 2)
    return {
        "total": len(rows),
        "open": len([r for r in rows if r["claim"].get("status") == "open"]),
        "pending_approval": len([r for r in rows if r["claim"].get("status") == "pending_approval"]),
        "approved": len([r for r in rows if r["claim"].get("status") == "approved"]),
        "rejected": len([r for r in rows if r["claim"].get("status") == "rejected"]),
        "approved_amount": total_amount,
    }


async def partner_scorecard(entity_filter: Optional[Dict[str, Any]] = None,
                            limit: int = 50) -> List[Dict[str, Any]]:
    """Skor mitra: jumlah langkah, rata-rata selisih, klaim, nilai klaim (PS-11)."""
    rows = await db[COLL].find(entity_filter or {}, {"_id": 0}).to_list(2000)
    acc: Dict[str, Dict[str, Any]] = {}
    for o in rows:
        for s in o.get("steps", []):
            mid = s.get("makloon_id") or ""
            if not mid or s.get("status") != "received":
                continue
            a = acc.setdefault(mid, {"makloon_id": mid, "makloon_name": s.get("makloon_name", ""),
                                     "steps": 0, "variance_sum": 0.0, "variance_n": 0,
                                     "claims": 0, "claim_amount": 0.0, "on_target": 0})
            a["steps"] += 1
            c = s.get("claim") or {}
            pct = c.get("variance_pct")
            if pct is not None:
                a["variance_sum"] += float(pct)
                a["variance_n"] += 1
                if abs(float(pct)) <= float(c.get("tolerance_pct") or 0):
                    a["on_target"] += 1
            if c.get("status") in ("open", "pending_approval", "approved"):
                a["claims"] += 1
            if c.get("status") == "approved":
                a["claim_amount"] += parse_decimal(c.get("amount"), 2)
    out = []
    for a in acc.values():
        avg = round(a["variance_sum"] / a["variance_n"], 2) if a["variance_n"] else None
        out.append({**a, "avg_variance_pct": avg,
                    "claim_amount": round(a["claim_amount"], 2),
                    "on_target_pct": round(a["on_target"] / a["steps"] * 100, 1) if a["steps"] else None})
    out.sort(key=lambda r: (-(r["claims"] or 0), -(r["steps"] or 0)))
    return out[:limit]
