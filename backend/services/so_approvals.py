"""F5 — Unified Approval SSOT pada Sales Order (`pending_approvals[]`).

Satu sumber kebenaran untuk SEMUA persetujuan SO: `nilai` (threshold nilai order),
`kredit` (over-credit / bypass blokir kredit), `special_price` (harga khusus).
Aturan inti (KEPUTUSAN OWNER §2.4):
  SO TIDAK boleh naik ke stage **Approved** sampai SEMUA entri `pending_approvals`
  berstatus `approved`. Koleksi detail (`price_approvals`, `credit_overrides`) tetap
  dipakai sebagai bukti/rincian, tapi STATUS keputusan DICERMINKAN di sini (1 SSOT).

ADDITIVE & idempotent: field `pending_approvals` embedded di dokumen `sales_orders`
(bukan koleksi baru). `so_status.derive_stage_substatus` membaca daftar ini untuk
menurunkan sub-status (menunggu_approval_nilai/kredit/harga).
"""
from typing import Any, Dict, List, Optional
from core_utils import new_id, now_iso

APPROVAL_TYPES = {"nilai", "kredit", "special_price"}

# Hirarki role approver — SATU sumber: `backend/role_registry.py` (FASE E-8/E8.1).
# Dulu angkanya ditulis ulang di sini dan di `config_service.role_satisfies`, jadi
# menambah peran `sales_admin`/`finance` berarti dua tempat harus diingat.
from role_registry import ROLE_RANK  # noqa: E402  (dipakai di bawah)

TYPE_LABELS = {
    "nilai": "Approval Nilai Order",
    "kredit": "Approval Kredit (Over-limit)",
    "special_price": "Approval Harga Khusus",
}


def make_approval(
    atype: str,
    required_role: str = "manager",
    reason: str = "",
    requested_by: str = "",
    requested_by_id: str = "",
    ref_id: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Bangun 1 entri pending_approval (status awal `pending`)."""
    entry = {
        "id": new_id("soappr"),
        "type": atype if atype in APPROVAL_TYPES else "nilai",
        "required_role": required_role or "manager",
        "status": "pending",
        "reason": (reason or "").strip(),
        "requested_by": requested_by or "",
        "requested_by_id": requested_by_id or "",
        "requested_at": now_iso(),
        "decided_by": None,
        "decided_by_id": None,
        "decided_at": None,
        "decision_notes": "",
        "evidence": [],
        "ref_id": ref_id,
    }
    entry.update(extra)
    return entry


def summarize(order: Dict[str, Any]) -> Dict[str, Any]:
    """Ringkas state gate approval dari `pending_approvals`."""
    pa: List[Dict[str, Any]] = order.get("pending_approvals") or []
    pending = [p for p in pa if p.get("status") == "pending"]
    rejected = [p for p in pa if p.get("status") == "rejected"]
    req_role: Optional[str] = None
    best = 0
    for p in pending:
        r = p.get("required_role")
        if ROLE_RANK.get(r, 0) > best:
            best = ROLE_RANK.get(r, 0)
            req_role = r
    return {
        "total": len(pa),
        "has_pending": bool(pending),
        "has_rejected": bool(rejected),
        "all_resolved": len(pending) == 0,           # tak ada yang menunggu keputusan
        "all_approved": len(pending) == 0 and len(rejected) == 0,
        "pending_count": len(pending),
        "rejected_count": len(rejected),
        "required_role": req_role,
        "pending_types": [p.get("type") for p in pending],
    }


def require_validation_default(settings: Optional[Dict[str, Any]]) -> bool:
    """Apakah SO wajib divalidasi admin/manager sebelum Confirmed (KEPUTUSAN OWNER §1.7).
    Default WAJIB (True); bisa dimatikan via settings.sales.require_so_validation=False."""
    s = (settings or {}).get("sales", {}) if settings else {}
    return bool(s.get("require_so_validation", True))


def approval_fields(order: Dict[str, Any], require_validation: bool = True) -> Dict[str, Any]:
    """Hitung `approval_required` + `required_approval_role` dari pending_approvals
    digabung kebijakan validasi admin. Dipakai $set ke dokumen SO."""
    s = summarize(order)
    requires = s["has_pending"]
    req_role = s["required_role"]
    if require_validation and not requires:
        # Validasi admin tetap diperlukan walau tak ada approval spesifik (siap_disahkan).
        requires = True
        req_role = req_role or order.get("required_approval_role") or "manager"
    return {
        "approval_required": bool(requires),
        "required_approval_role": req_role,
    }


def all_approved(order: Dict[str, Any]) -> bool:
    """True bila tak ada entri pending/rejected (boleh naik ke Approved)."""
    return summarize(order)["all_approved"]


def public_view(order: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Daftar pending_approvals diperkaya label untuk FE (read-only)."""
    out: List[Dict[str, Any]] = []
    for p in (order.get("pending_approvals") or []):
        d = dict(p)
        d["type_label"] = TYPE_LABELS.get(p.get("type"), p.get("type"))
        d["evidence"] = [a for a in (p.get("evidence") or []) if not a.get("is_deleted")]
        out.append(d)
    return out


async def backfill_pending_approvals(database) -> Dict[str, int]:
    """F5 — sinkronkan SSOT `pending_approvals` untuk SO lama (ADDITIVE & idempotent).

    - SO 'open' (reserved/waiting_approval/waiting_stock/draft) dengan `approval_required`
      tapi belum punya entri pending → buat 1 entri `nilai` (validasi admin) supaya muncul
      di Pusat Persetujuan & konsisten dgn model F5.
    - Pastikan field `pending_approvals` (list) & `credit_hold` (bool) selalu ada.
    TIDAK mengubah SO yang sudah punya pending_approvals. Aman dijalankan berkali-kali.
    """
    OPEN = ("reserved", "waiting_approval", "waiting_stock", "draft")
    updated = 0
    total = 0
    async for o in database.sales_orders.find({}, {"_id": 0}):
        total += 1
        pa = o.get("pending_approvals")
        sets: Dict[str, Any] = {}
        if pa is None:
            pa = []
            sets["pending_approvals"] = pa
        if "credit_hold" not in o:
            sets["credit_hold"] = False
        if (((o.get("status") == "waiting_approval")
                or (o.get("status") in OPEN and o.get("approval_required")))
                and not any(p.get("status") == "pending" for p in pa)):
            pa = list(pa) + [make_approval(
                "nilai", required_role=o.get("required_approval_role") or "manager",
                reason="Validasi nilai order (sinkronisasi F5).",
                requested_by=o.get("sales_name", ""),
                amount=float(o.get("grand_total", o.get("total_amount", 0)) or 0))]
            sets["pending_approvals"] = pa
        if sets:
            sets["updated_at"] = now_iso()
            await database.sales_orders.update_one({"id": o["id"]}, {"$set": sets})
            updated += 1
    return {"updated": updated, "total": total}
