"""R0 — Return Policy Engine (Master Data).

Fondasi modul retur (R0 dari RETURNS_ANALYSIS.md §K). Bertanggung jawab atas:

- **Supplier return policy** (embedded di `suppliers.return_policy`) + klasifikasi
  asal barang `origin_type` (local|import) + override per-PO (`import_flag`).
- **Sales return policy** (koleksi `sales_return_policies`, prefix `srp_`) —
  aturan berdiri sendiri dengan scope global / category / customer.
- **Deadline derivation** (linked): `return_deadline = tgl_referensi + window_days`.
- **Eligibility check** untuk retur jual (blok/peringatan bila di luar window).
- **Snapshot policy** ke dokumen retur agar auditable.

Fungsi murni-orchestration (async I/O ke DB), tanpa JSX/HTTP — mudah diuji.
Semua tanggal disimpan/dihitung sebagai ISO-8601 string (kontrak KN3).
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta

from db import db
from core_utils import now_iso

# Mode refund retur BELI (KN → supplier)
SUPPLIER_REFUND_MODES = ("cash", "ap_credit", "none")
ORIGIN_TYPES = ("local", "import")

# Default cerdas untuk kebijakan retur supplier bila belum diisi.
DEFAULT_SUPPLIER_POLICY: Dict[str, Any] = {
    "window_days": 30,
    "refund_modes": ["ap_credit"],
    "returnable_to_supplier": True,
    "rma_required": False,
    "restocking_fee_pct": 0.0,
    "condition_requirements": "",
    "custom_fields": {},
    "valid_from": "",
    "valid_until": "",
    "notes": "",
}

# Default kebijakan retur jual (dipakai bila tak ada policy match sama sekali).
DEFAULT_SALES_POLICY: Dict[str, Any] = {
    "id": "",
    "name": "Default (sistem)",
    "scope": "global",
    "scope_ref": "",
    "window_days": 30,
    "allowed_return_types": ["retur", "bs", "penggantian", "komplain", "garansi"],
    "allowed_outcomes": ["refund", "store_credit", "nego", "reject"],
    "restocking_fee_pct": 0.0,
    "require_inspection": True,
    "enforce_window": False,
    "link_to_supplier_window": False,
    "condition_requirements": "",
    "custom_fields": {},
    "is_default": True,
}


# ─── Util tanggal ────────────────────────────────────────────────────────────

def parse_dt(value: Any) -> Optional[datetime]:
    """Parse ISO string → datetime tz-aware (UTC). None bila gagal/kosong."""
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except (ValueError, TypeError):
        return None


def compute_deadline(base_date: Any, window_days: int) -> str:
    """Hitung deadline = base_date + window_days (ISO). "" bila base_date invalid."""
    base = parse_dt(base_date)
    if not base:
        return ""
    try:
        wd = int(window_days or 0)
    except (ValueError, TypeError):
        wd = 0
    return (base + timedelta(days=wd)).isoformat()


def _is_policy_active(policy: Dict[str, Any], on: Optional[datetime] = None) -> bool:
    """Cek masa berlaku policy (valid_from/valid_until)."""
    on = on or datetime.now(timezone.utc)
    vf = parse_dt(policy.get("valid_from"))
    vu = parse_dt(policy.get("valid_until"))
    if vf and on < vf:
        return False
    if vu and on > vu:
        return False
    return True


# ─── Supplier return policy ──────────────────────────────────────────────────

def normalize_supplier_policy(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Gabungkan default + policy tersimpan → objek policy lengkap & aman."""
    out = dict(DEFAULT_SUPPLIER_POLICY)
    out["custom_fields"] = {}
    if isinstance(raw, dict):
        for k in out:
            if k in raw and raw[k] is not None:
                out[k] = raw[k]
    # Normalisasi refund_modes ke subset kanonik (tetap izinkan kosong → none).
    modes = out.get("refund_modes") or []
    out["refund_modes"] = [m for m in modes if m in SUPPLIER_REFUND_MODES] or ["ap_credit"]
    try:
        out["window_days"] = int(out.get("window_days") or 0)
    except (ValueError, TypeError):
        out["window_days"] = 0
    try:
        out["restocking_fee_pct"] = float(out.get("restocking_fee_pct") or 0)
    except (ValueError, TypeError):
        out["restocking_fee_pct"] = 0.0
    out["returnable_to_supplier"] = bool(out.get("returnable_to_supplier", True))
    out["rma_required"] = bool(out.get("rma_required", False))
    if not isinstance(out.get("custom_fields"), dict):
        out["custom_fields"] = {}
    return out


def resolve_effective_origin(supplier: Dict[str, Any],
                             po: Optional[Dict[str, Any]] = None) -> str:
    """Asal barang efektif: override PO (`import_flag`) menang atas supplier.origin_type."""
    if po is not None:
        flag = po.get("import_flag")
        if flag is True:
            return "import"
        if flag is False:
            return "local"
    ot = (supplier or {}).get("origin_type") or "local"
    return ot if ot in ORIGIN_TYPES else "local"


def resolve_supplier_return_policy(supplier: Dict[str, Any],
                                   po: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Kembalikan policy retur supplier efektif + info asal barang + rekomendasi.

    Aturan cerdas (RETURNS_ANALYSIS §J): bila `import` & `returnable_to_supplier=false`
    → alur retur beli DILEWATI, barang defect diarahkan ke **regrade + jual lokal**.
    """
    policy = normalize_supplier_policy((supplier or {}).get("return_policy"))
    origin = resolve_effective_origin(supplier, po)
    returnable = bool(policy.get("returnable_to_supplier", True))
    # Impor yang tak returnable → rekomendasi regrade + jual lokal.
    recommend_regrade_local = (origin == "import" and not returnable)
    return {
        "supplier_id": (supplier or {}).get("id", ""),
        "supplier_name": (supplier or {}).get("name", ""),
        "origin_type": origin,
        "country": (supplier or {}).get("country", "") or "",
        "policy": policy,
        "returnable_to_supplier": returnable,
        "recommend_regrade_local": recommend_regrade_local,
        "resolved_at": now_iso(),
    }


# ─── Sales return policy resolution ──────────────────────────────────────────

async def _load_active_sales_policies(entity_id: str = "") -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"status": {"$ne": "inactive"}}
    if entity_id:
        # FASE E-4 (E4.3) — `"all"` ikut dianggap GLOBAL supaya kebijakan yang sudah
        # distempel migrasi tetap terbaca (dulu hanya ""/None yang dihitung global).
        q["$or"] = [{"entity_id": entity_id}, {"entity_id": ""}, {"entity_id": None},
                    {"entity_id": "all"}]
    rows = await db.sales_return_policies.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [r for r in rows if _is_policy_active(r)]


async def resolve_sales_return_policy(customer_id: str = "",
                                      categories: Optional[List[str]] = None,
                                      entity_id: str = "") -> Dict[str, Any]:
    """Pilih policy retur jual TERBAIK (prioritas: customer > category > global).

    Bila tak ada yang cocok → default sistem (window 30 hari, inspect wajib,
    window tidak dipaksa/hanya peringatan)."""
    policies = await _load_active_sales_policies(entity_id)
    categories = [c for c in (categories or []) if c]

    by_customer = [p for p in policies if p.get("scope") == "customer"
                   and p.get("scope_ref") == customer_id and customer_id]
    by_category = [p for p in policies if p.get("scope") == "category"
                   and p.get("scope_ref") in categories]
    by_global = [p for p in policies if p.get("scope") == "global"]

    for bucket in (by_customer, by_category, by_global):
        if bucket:
            # FASE E-4 (E4.3) — pada tingkat cakupan yang SAMA, kebijakan khusus badan
            # usaha MENANG atas kebijakan global; sesudah itu baru yang terbaru
            # (daftar sudah terurut created_at desc). Tanpa aturan ini kebijakan global
            # yang dibuat belakangan bisa mengalahkan kebijakan khusus badan usaha.
            own = [p for p in bucket
                   if entity_id and str(p.get("entity_id") or "") == entity_id]
            return {**(own[0] if own else bucket[0]), "is_default": False}
    return dict(DEFAULT_SALES_POLICY)


def snapshot_sales_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    """Snapshot ringkas policy untuk disematkan ke dokumen retur (auditable)."""
    keys = ("id", "name", "scope", "scope_ref", "window_days", "allowed_return_types",
            "allowed_outcomes", "restocking_fee_pct", "require_inspection",
            "enforce_window", "link_to_supplier_window", "condition_requirements",
            "custom_fields", "is_default")
    snap = {k: policy.get(k) for k in keys if k in policy}
    snap["snapshot_at"] = now_iso()
    return snap


# ─── Deadline (linked) + Eligibility retur jual ─────────────────────────────

def _order_reference_date(order: Dict[str, Any]) -> str:
    """Tanggal acuan jendela retur = saat barang dikirim ke customer.
    Prioritas: dispatched_at → shipped_at → confirmed_at → approved_at → created_at."""
    for k in ("dispatched_at", "shipped_at", "delivered_at",
              "confirmed_at", "approved_at", "created_at"):
        if order.get(k):
            return order[k]
    return ""


async def _linked_supplier_deadline(order: Dict[str, Any],
                                    window_fallback: int) -> Dict[str, Any]:
    """Coba turunkan deadline dari window supplier asal barang (linked).

    Best-effort: telusuri roll yang men-sumber SO ini (earmarked/reserved) →
    supplier + tanggal terima; ambil window TERKETAT. Bila tak dapat → None.
    """
    order_id = order.get("id", "")
    # Kumpulkan kandidat supplier dari PO yang produk-nya ada di order (best-effort).
    product_ids = [it.get("product_id") for it in (order.get("items") or []) if it.get("product_id")]
    if not product_ids:
        return {"deadline": "", "supplier_id": "", "window_days": window_fallback, "source": "none"}

    # Cari PO terbaru yang memuat produk-produk ini (sebagai proxy asal beli).
    po = await db.purchase_orders.find_one(
        {"items.product_id": {"$in": product_ids},
         "status": {"$in": ["receiving", "partial", "completed", "closed", "closed_short"]}},
        {"_id": 0}, sort=[("created_at", -1)])
    if not po or not po.get("supplier_id"):
        return {"deadline": "", "supplier_id": "", "window_days": window_fallback, "source": "none"}

    supplier = await db.suppliers.find_one({"id": po["supplier_id"]}, {"_id": 0})
    if not supplier:
        return {"deadline": "", "supplier_id": po.get("supplier_id", ""),
                "window_days": window_fallback, "source": "none"}

    resolved = resolve_supplier_return_policy(supplier, po)
    win = int(resolved["policy"].get("window_days") or window_fallback)
    receipt = po.get("last_received_at") or po.get("updated_at") or po.get("created_at")
    return {
        "deadline": compute_deadline(receipt, win),
        "supplier_id": supplier.get("id", ""),
        "supplier_name": supplier.get("name", ""),
        "po_number": po.get("po_number", ""),
        "receipt_date": receipt,
        "window_days": win,
        "origin_type": resolved.get("origin_type"),
        "returnable_to_supplier": resolved.get("returnable_to_supplier"),
        "source": "supplier_linked",
    }


async def check_sales_return_eligibility(order: Dict[str, Any],
                                         return_type: str = "",
                                         on_date: Any = None) -> Dict[str, Any]:
    """Evaluasi kelayakan retur jual untuk sebuah order pada `on_date` (default now).

    Mengembalikan: policy terpilih (+snapshot), deadline, sisa hari, apakah dalam
    window, apakah diblok (enforce), daftar peringatan, dan deadline supplier-linked
    (informasional) bila policy `link_to_supplier_window`.
    """
    now = parse_dt(on_date) or datetime.now(timezone.utc)
    categories = list({it.get("category") for it in (order.get("items") or []) if it.get("category")})
    policy = await resolve_sales_return_policy(
        customer_id=order.get("customer_id", ""),
        categories=categories,
        entity_id=order.get("entity_id", ""),
    )

    ref_date = _order_reference_date(order)
    window_days = int(policy.get("window_days") or 0)
    deadline = compute_deadline(ref_date, window_days)

    # Deadline linked ke supplier (opsional) — bisa lebih ketat.
    supplier_linked: Dict[str, Any] = {}
    if policy.get("link_to_supplier_window"):
        supplier_linked = await _linked_supplier_deadline(order, window_days)
        sl_deadline = supplier_linked.get("deadline") or ""
        if sl_deadline:
            # Deadline efektif = yang paling ketat (paling awal).
            d1, d2 = parse_dt(deadline), parse_dt(sl_deadline)
            if d1 and d2:
                deadline = min(d1, d2).isoformat()
            elif d2:
                deadline = sl_deadline

    dl = parse_dt(deadline)
    within_window = True
    days_remaining: Optional[int] = None
    if dl:
        within_window = now <= dl
        days_remaining = (dl - now).days

    warnings: List[str] = []
    # Cek jenis retur diizinkan
    type_ok = True
    if return_type:
        allowed = policy.get("allowed_return_types") or []
        type_ok = return_type in allowed
        if not type_ok:
            warnings.append(
                f"Jenis retur '{return_type}' tidak diizinkan oleh kebijakan '{policy.get('name')}'.")
    if not ref_date:
        warnings.append("Tanggal pengiriman order tidak diketahui — deadline tak dapat dihitung.")
    if dl and not within_window:
        msg = (f"Di luar jendela retur ({window_days} hari). "
               f"Deadline {deadline[:10]}.")
        warnings.append(msg)

    enforce = bool(policy.get("enforce_window"))
    blocked = bool(enforce and dl is not None and not within_window)
    eligible = type_ok and (within_window or not enforce)

    return {
        "order_id": order.get("id", ""),
        "order_number": order.get("number", ""),
        "customer_id": order.get("customer_id", ""),
        "eligible": eligible,
        "blocked": blocked,
        "within_window": within_window,
        "reference_date": ref_date,
        "window_days": window_days,
        "deadline": deadline,
        "days_remaining": days_remaining,
        "require_inspection": bool(policy.get("require_inspection", True)),
        "restocking_fee_pct": float(policy.get("restocking_fee_pct") or 0),
        "allowed_return_types": policy.get("allowed_return_types") or [],
        "allowed_outcomes": policy.get("allowed_outcomes") or [],
        "supplier_linked": supplier_linked or None,
        "warnings": warnings,
        "policy": snapshot_sales_policy(policy),
        "evaluated_at": now_iso(),
    }
