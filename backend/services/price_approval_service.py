"""Sub-fase 1.7 + F1b — bagian **BERSAMA** alur Harga Khusus (`price_approvals`).

DUA pintu masuk memakai SATU mesin persetujuan (keputusan pemilik: "jangan duplikasi"):
  1. **Sales mengajukan potongan** dari POS / layar Persetujuan Harga
     → `routers/price_approvals.py`.
  2. **Admin/manager menetapkan harga langganan** di Daftar Harga per Pelanggan yang
     jatuh DI BAWAH batas bawah (harga PT/HPP)
     → `services/customer_price_service.py`.

Yang dipusatkan di sini supaya tidak ada dua definisi yang bisa berbeda diam-diam:
  · normalisasi `valid_until` (akhir hari, bukan tengah malam);
  · arti "aturan masih berlaku" (`is_active`);
  · bentuk dokumen (`build_doc`) + field turunan untuk layar (`decorate`);
  · notifikasi ke approver saat ada pengajuan menunggu;
  · **efek lanjutan keputusan** (`after_decision`) — mengaktifkan / menolak record
    Daftar Harga per Pelanggan yang menunggu keputusan itu.

Koleksi tetap `price_approvals` (prefix `pra_`) — tidak ada koleksi persetujuan baru.
"""
from typing import Any, Dict, List, Optional

from core_utils import new_id, now_iso, rupiah
from db import db
from services.notification_service import create_notification

COLL = "price_approvals"
PREFIX = "pra"

SCOPE_STANDING = "standing"
SCOPE_ORDER = "order"

SOURCE_SALES = "sales_request"
SOURCE_PRICELIST = "customer_pricelist"
SOURCE_LABEL = {
    SOURCE_SALES: "Pengajuan sales",
    SOURCE_PRICELIST: "Daftar Harga per Pelanggan",
}

STATUS_LABEL = {
    "draft": "Draf", "pending": "Menunggu", "approved": "Disetujui",
    "rejected": "Ditolak", "superseded": "Digantikan", "cancelled": "Dibatalkan",
    # F1b — aturan yang diakhiri approver (promo selesai / kesepakatan dibatalkan).
    "revoked": "Diakhiri",
}

EDITABLE_STATUSES = {"draft", "pending"}
DECIDABLE_STATUSES = {"pending"}


# ─── Tanggal & keberlakuan ─────────────────────────────────────────
def norm_until(value: str) -> str:
    """'YYYY-MM-DD' → akhir hari UTC agar tidak dianggap kadaluarsa di hari itu."""
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) == 10 and v.count("-") == 2:
        return f"{v}T23:59:59+00:00"
    return v


def is_active(r: Dict[str, Any], now: Optional[str] = None) -> bool:
    """Aturan harga khusus yang DISETUJUI dan sedang berlaku pada `now`."""
    if (r or {}).get("status") != "approved":
        return False
    now = now or now_iso()
    vf = r.get("valid_from") or ""
    vu = r.get("valid_until") or ""
    if vf and vf > now:
        return False
    if vu and vu < now:
        return False
    return True


def decorate(r: Dict[str, Any]) -> Dict[str, Any]:
    """Field turunan untuk layar: diskon %, hemat/unit, kadaluarsa, asal pengajuan."""
    if not r:
        return r
    normal = float(r.get("normal_price", 0) or 0)
    req = float(r.get("requested_price", 0) or 0)
    r["discount_percent"] = round((normal - req) / normal * 100, 2) if normal > 0 else 0.0
    r["savings_per_unit"] = round(normal - req, 2)
    vu = r.get("valid_until") or ""
    r["is_expired"] = bool(r.get("status") == "approved" and vu and vu < now_iso())
    src = r.get("source") or SOURCE_SALES
    r["source"] = src
    r["source_label"] = SOURCE_LABEL.get(src, src)
    r["from_pricelist"] = src == SOURCE_PRICELIST
    r["status_label"] = STATUS_LABEL.get(r.get("status") or "", r.get("status") or "")
    # Aturan STANDING yang masih disetujui boleh diakhiri approver (lihat /revoke).
    r["can_revoke"] = bool(r.get("status") == "approved"
                           and (r.get("scope") or SCOPE_STANDING) != SCOPE_ORDER)
    r["attachments"] = [a for a in (r.get("attachments") or []) if not a.get("is_deleted")]
    return r


# ─── Bentuk dokumen ────────────────────────────────────────────────
def build_doc(*, customer: Dict[str, Any], product: Dict[str, Any], entity_id: str,
              requested_price: float, requester: Dict[str, Any],
              normal_price: Optional[float] = None, min_quantity: float = 0.0,
              reason: str = "", valid_until: str = "", status: str = "pending",
              scope: str = SCOPE_STANDING, so_id: str = "", override: bool = False,
              source: str = SOURCE_SALES,
              extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """SATU bentuk dokumen `price_approvals` untuk kedua pintu masuk."""
    sc = SCOPE_ORDER if str(scope or "").strip().lower() == SCOPE_ORDER else SCOPE_STANDING
    doc: Dict[str, Any] = {
        "id": new_id(PREFIX),
        "entity_id": entity_id,
        "customer_id": customer.get("id", ""), "customer_name": customer.get("name", ""),
        "product_id": product.get("id", ""), "sku": product.get("sku", ""),
        "product_name": product.get("name", ""),
        "normal_price": round(float(normal_price if normal_price is not None
                                    else (product.get("price") or 0)), 2),
        "requested_price": round(float(requested_price or 0), 2),
        "min_quantity": round(float(min_quantity or 0), 2),
        "unit": product.get("base_unit", "meter"),
        "reason": (reason or "").strip(),
        "valid_from": now_iso(),
        "valid_until": "" if sc == SCOPE_ORDER else norm_until(valid_until),
        "status": status,
        "scope": sc,
        "source": source,
        "so_id": (so_id or "").strip(),
        "is_override": bool(override),
        "attachments": [],
        "requested_by": requester.get("id"), "requested_by_name": requester.get("name", ""),
        "approved_by": None, "approved_by_name": None,
        "decision_notes": "", "decided_at": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    doc.update(extra or {})
    return doc


async def insert(doc: Dict[str, Any]) -> Dict[str, Any]:
    await db[COLL].insert_one(dict(doc))
    return doc


async def notify_pending(doc: Dict[str, Any], *, why: str = "") -> None:
    """Beri tahu approver bahwa ada harga menunggu keputusan (dedupe per pengajuan)."""
    unit = doc.get("unit", "meter")
    await create_notification(
        notif_type="price_approval_pending",
        ref=f"pra_pending:{doc.get('id', '')}",
        title=f"Harga menunggu persetujuan: {doc.get('product_name') or doc.get('sku')}",
        body=(f"{doc.get('customer_name', '')} · {rupiah(doc.get('requested_price') or 0)}/{unit} "
              f"(pembanding {rupiah(doc.get('normal_price') or 0)}/{unit}). "
              f"Diajukan {doc.get('requested_by_name') or '—'}. {why}").strip(),
        severity="warning",
        link="price-approvals",
        entity_id=doc.get("entity_id"),
        recipient_role="manager",
        action_type="price_approval_view",
        action_id=doc.get("id", ""),
        action_role="manager",
    )


# ─── Pintu masuk 2: harga langganan di bawah batas ────────────────
async def open_for_customer_price(*, customer_price: Dict[str, Any],
                                  customer: Dict[str, Any], product: Dict[str, Any],
                                  guard: Dict[str, Any],
                                  requester: Dict[str, Any]) -> Dict[str, Any]:
    """Buka pengajuan Harga Khusus untuk satu record Daftar Harga per Pelanggan.

    Sengaja MEMAKAI koleksi & layar persetujuan yang sudah ada: manajer tidak perlu
    belajar antrean baru, dan jejak keputusan harga tetap di satu tempat.
    """
    reason = (customer_price.get("note") or "").strip()
    why = guard.get("summary") or ""
    doc = build_doc(
        customer=customer, product=product, entity_id=customer_price.get("entity_id", ""),
        requested_price=customer_price.get("sell_price", 0),
        requester=requester,
        normal_price=guard.get("floor") or guard.get("entity_reference") or 0,
        reason=(f"Harga langganan pelanggan. {reason}".strip()
                if reason else "Harga langganan pelanggan."),
        valid_until=(customer_price.get("valid_until") or ""),
        status="pending", scope=SCOPE_STANDING, source=SOURCE_PRICELIST,
        extra={
            "customer_price_id": customer_price.get("id", ""),
            "guard": {k: guard.get(k) for k in
                      ("floor", "floor_from", "threshold", "basis", "basis_label",
                       "entity_reference", "has_entity_price", "hpp", "global_price",
                       "gap", "gap_pct", "margin_pct", "reasons", "summary",
                       "tolerance_pct")},
            "valid_from": customer_price.get("valid_from") or now_iso(),
        },
    )
    await insert(doc)
    await notify_pending(doc, why=why)
    return doc


async def pending_for_customer_price(cp_id: str) -> Optional[Dict[str, Any]]:
    return await db[COLL].find_one(
        {"customer_price_id": cp_id, "status": "pending"}, {"_id": 0})


async def cancel_for_customer_price(cp_id: str, actor_name: str = "") -> int:
    """Pengajuan ikut BATAL bila record harga langganannya dinonaktifkan.

    Ditulis jujur sebagai `cancelled` (bukan "ditolak") supaya laporan tidak
    menuduh manajer menolak sesuatu yang sebenarnya ditarik pengajunya.
    """
    res = await db[COLL].update_many(
        {"customer_price_id": cp_id, "status": "pending"},
        {"$set": {"status": "cancelled", "decision_notes": f"Dibatalkan oleh {actor_name}".strip(),
                  "decided_at": now_iso(), "updated_at": now_iso()}})
    return res.modified_count


# ─── Efek lanjutan keputusan ──────────────────────────────────────
async def after_decision(approval: Dict[str, Any], actor: Dict[str, Any],
                         decision: str) -> Dict[str, Any]:
    """Dipanggil router SETELAH approve/reject tersimpan.

    Bila pengajuan berasal dari Daftar Harga per Pelanggan, record harga langganannya
    diaktifkan (approve) atau ditandai ditolak (reject). Impor `customer_price_service`
    dilakukan di dalam fungsi supaya tidak ada impor siklik.
    """
    cp_id = (approval or {}).get("customer_price_id") or ""
    if not cp_id:
        return {}
    from services import customer_price_service as cps  # noqa: WPS433 — hindari siklik
    return await cps.apply_approval_decision(cp_id, decision, approval, actor)


async def standing_for(entity_id: str, customer_id: str, product_ids: List[str],
                       as_of: Optional[str] = None,
                       quantity_map: Optional[Dict[str, float]] = None,
                       ) -> Dict[str, Dict[str, Any]]:
    """Aturan STANDING yang disetujui & berlaku per produk (1 query).

    Dipakai resolver harga supaya angka di layar POS SAMA dengan angka yang
    tersimpan di pesanan — dulu layar memanggil endpoint ini satu-satu per produk.

    PENGECUALIAN PENTING: pengajuan yang LAHIR dari Daftar Harga per Pelanggan
    (`customer_price_id` terisi) TIDAK dihitung sebagai aturan tersendiri. Ia hanya
    JEJAK KEPUTUSAN untuk record harga langganan; kalau ikut dihitung, harga yang
    sama muncul dua kali dan layar salah melabeli sumbernya "Harga khusus"
    padahal itu harga langganan pelanggan.
    """
    ids = [p for p in dict.fromkeys(product_ids or []) if p]
    if not (entity_id and customer_id and ids):
        return {}
    rows = await db[COLL].find(
        {"entity_id": entity_id, "customer_id": customer_id,
         "product_id": {"$in": ids}, "status": "approved",
         "scope": {"$ne": SCOPE_ORDER},
         "$or": [{"customer_price_id": {"$exists": False}}, {"customer_price_id": ""},
                 {"customer_price_id": None}]},
        {"_id": 0}).sort("decided_at", -1).to_list(500)
    now = as_of or now_iso()
    qty_map = quantity_map or {}
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        pid = r.get("product_id")
        if pid in out or not is_active(r, now):
            continue
        qty = qty_map.get(pid)
        if qty is not None and float(qty) < float(r.get("min_quantity", 0) or 0):
            continue
        out[pid] = r
    return out
