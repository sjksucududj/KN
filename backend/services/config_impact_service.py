"""FASE G-0 — DAFTAR DAMPAK (Blast-Radius Picker).

Jawaban langsung untuk kekhawatiran pemilik:
> "ya otomatis tapi saya takutnya malah SEMUA invoice terpengaruh. Bagaimana caranya
>  jika user hanya berintensi mengubah 1 invoice itu tapi invoice lain tidak terpengaruh?"

Solusi: koreksi harga master **tidak pernah** menyebar diam-diam. Sistem lebih dulu
menghitung **daftar dokumen terbuka** yang memakai harga itu, menampilkan dampak Rp & %
per dokumen, lalu user **mencentang** mana yang ikut dikoreksi.

Aturan yang dikunci di sini:
1. Default centang = **HANYA dokumen tempat user sedang bekerja** (sisanya kosong).
2. Dokumen yang **tidak** dicentang WAJIB byte-identik setelah operasi (INV-CFG-07) —
   diverifikasi memakai sidik jari SHA-256 sebelum & sesudah.
3. Dokumen yang invoice-nya **sudah terbit** tidak pernah diubah; ia masuk daftar
   terpisah "butuh Nota Kredit/Debit" (append-only ledger, aturan repo #7).
"""
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from core_utils import now_iso, safe_doc
from db import db
from dependencies import audit

# Status SO yang dianggap SUDAH tidak boleh di-re-derive (barang/berkas sudah jalan).
CLOSED_SO_STATUSES = {"cancelled", "expired", "done", "delivered", "shipped", "picked"}
# Field yang tidak diikutkan sidik jari (berubah wajar tanpa perubahan nilai bisnis).
FINGERPRINT_SKIP = {"_id"}


class ImpactError(ValueError):
    """Permintaan tidak sah — pesan siap tampil (Bahasa Indonesia)."""


def fingerprint(doc: Dict[str, Any]) -> str:
    """Sidik jari dokumen untuk membuktikan "tidak tersentuh"."""
    clean = {k: v for k, v in safe_doc(doc or {}).items() if k not in FINGERPRINT_SKIP}
    blob = json.dumps(clean, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def _invoice_count(order_id: str) -> int:
    return await db.invoices.count_documents({"order_id": order_id})


def _line_preview(items: List[Dict[str, Any]], product_id: str, old_price: float,
                  new_price: float) -> Tuple[List[Dict[str, Any]], float]:
    """Baris yang terdampak + total selisih dokumen."""
    lines: List[Dict[str, Any]] = []
    delta_total = 0.0
    for idx, it in enumerate(items or []):
        if it.get("product_id") != product_id:
            continue
        qty = float(it.get("quantity") or 0)
        cur = float(it.get("price") or 0)
        sub_now = round(cur * qty, 2)
        sub_new = round(new_price * qty, 2)
        delta = round(sub_new - sub_now, 2)
        delta_total += delta
        lines.append({
            "index": idx,
            "product_name": it.get("product_name") or it.get("name") or "",
            "quantity": qty,
            "unit": it.get("unit") or "",
            "price_now": cur,
            "price_new": new_price,
            "subtotal_now": sub_now,
            "subtotal_new": sub_new,
            "delta": delta,
            "delta_pct": round((delta / sub_now * 100), 2) if sub_now else 0.0,
            "already_matches": abs(cur - new_price) < 0.005,
        })
    return lines, round(delta_total, 2)


async def preview(product_id: str, new_price: float, current_doc_id: str = "",
                  entity_id: str = "") -> Dict[str, Any]:
    """Hitung Daftar Dampak koreksi harga master — TIDAK menulis apa pun."""
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise ImpactError("Produk tidak ditemukan")
    old_price = float(product.get("price") or 0)
    new_price = round(float(new_price or 0), 2)
    if new_price <= 0:
        raise ImpactError("Harga baru harus lebih besar dari 0")

    q: Dict[str, Any] = {"items.product_id": product_id}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    orders = await db.sales_orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)

    editable: List[Dict[str, Any]] = []
    locked: List[Dict[str, Any]] = []
    for o in orders:
        lines, delta = _line_preview(o.get("items"), product_id, old_price, new_price)
        if not lines:
            continue
        inv = await _invoice_count(o["id"])
        status = (o.get("status") or "").lower()
        row = {
            "doc_type": "sales_order",
            "doc_id": o["id"],
            "doc_number": o.get("number") or o.get("so_number") or o["id"],
            "customer_name": o.get("customer_name", ""),
            "entity_id": o.get("entity_id", ""),
            "date": o.get("created_at", ""),
            "status": status,
            "total_now": float(o.get("total_amount") or 0),
            "total_new": round(float(o.get("total_amount") or 0) + delta, 2),
            "delta": delta,
            "lines": lines,
            "invoice_count": inv,
            "fingerprint": fingerprint(o),
        }
        if inv > 0:
            row["lock_reason"] = (f"Invoice sudah terbit ({inv} dokumen) — angka historis tidak boleh "
                                 f"diubah. Koreksi lewat Nota Kredit/Debit.")
            locked.append(row)
        elif status in CLOSED_SO_STATUSES:
            row["lock_reason"] = (f"Status '{status}' — barang/dokumen sudah berjalan, harga tidak "
                                 f"bisa di-derive ulang. Koreksi lewat Nota Kredit/Debit.")
            locked.append(row)
        else:
            editable.append(row)

    default_selected = [d["doc_id"] for d in editable if d["doc_id"] == current_doc_id]
    return {
        "product": {"id": product["id"], "sku": product.get("sku", ""),
                    "name": product.get("name", ""), "unit": product.get("base_unit", "")},
        "price_now": old_price,
        "price_new": new_price,
        "price_delta": round(new_price - old_price, 2),
        "price_delta_pct": round((new_price - old_price) / old_price * 100, 2) if old_price else 0.0,
        "editable_documents": editable,
        "locked_documents": locked,
        "default_selected": default_selected,
        "summary": {
            "editable_count": len(editable),
            "locked_count": len(locked),
            "editable_delta_total": round(sum(d["delta"] for d in editable), 2),
            "locked_delta_total": round(sum(d["delta"] for d in locked), 2),
            "default_selected_count": len(default_selected),
        },
        "policy": ("Default: HANYA dokumen yang sedang Anda buka yang tercentang. "
                   "Dokumen lain tidak berubah kecuali Anda mencentangnya."),
    }


async def apply(product_id: str, new_price: float, doc_ids: List[str], *,
                reason: str, actor: str, entity_id: str = "",
                update_master: bool = True) -> Dict[str, Any]:
    """Terapkan koreksi harga master **hanya** ke dokumen yang dicentang.

    Membuktikan INV-CFG-07: dokumen yang tidak dicentang diverifikasi byte-identik
    (sidik jari sebelum == sesudah).
    """
    if not (reason or "").strip():
        raise ImpactError("Alasan koreksi harga WAJIB diisi (jejak audit).")
    plan = await preview(product_id, new_price, entity_id=entity_id)
    selected = set(doc_ids or [])
    editable_ids = {d["doc_id"] for d in plan["editable_documents"]}
    invalid = selected - editable_ids
    if invalid:
        raise ImpactError(
            "Dokumen berikut tidak bisa dikoreksi otomatis (invoice sudah terbit atau sudah "
            f"berjalan): {', '.join(sorted(invalid))}")

    before = {d["doc_id"]: d["fingerprint"]
              for d in plan["editable_documents"] + plan["locked_documents"]}
    new_price = plan["price_new"]
    old_price = plan["price_now"]

    if update_master:
        await db.products.update_one(
            {"id": product_id},
            {"$set": {"price": new_price, "updated_at": now_iso()}})
        await audit(actor, "product_price_corrected", "products", product_id,
                    {"price_before": old_price, "price_after": new_price,
                     "documents_updated": sorted(selected)}, reason=reason)

    from services.config_service import compute_order_pricing

    changed: List[Dict[str, Any]] = []
    for row in plan["editable_documents"]:
        if row["doc_id"] not in selected:
            continue
        order = await db.sales_orders.find_one({"id": row["doc_id"]}, {"_id": 0})
        if not order:
            continue
        items = [dict(it) for it in (order.get("items") or [])]
        for it in items:
            if it.get("product_id") == product_id:
                it["price"] = new_price
        priced = await compute_order_pricing(
            items, entity_id=order.get("entity_id"),
            order_discount_percent=float(order.get("order_discount_percent") or 0),
            cfg_section="sales")
        update: Dict[str, Any] = {
            "items": priced["items"],
            "total_amount": priced["total_amount"],
            "net_subtotal": priced["net_subtotal"],
            "dpp": priced["dpp"],
            "ppn_amount": priced["ppn_amount"],
            "grand_total": priced["grand_total"],
            "updated_at": now_iso(),
        }
        await db.sales_orders.update_one({"id": row["doc_id"]}, {"$set": update})
        await audit(actor, "sales_order_price_rederived", "sales_orders", row["doc_id"],
                    {"product_id": product_id, "price_before": old_price,
                     "price_after": new_price, "total_before": row["total_now"],
                     "total_after": priced["total_amount"]}, reason=reason)
        changed.append({"doc_id": row["doc_id"], "doc_number": row["doc_number"],
                        "total_before": row["total_now"], "total_after": priced["total_amount"],
                        "delta": round(priced["total_amount"] - row["total_now"], 2)})

    untouched: List[Dict[str, Any]] = []
    violations: List[str] = []
    for doc_id, fp in before.items():
        if doc_id in selected:
            continue
        doc = await db.sales_orders.find_one({"id": doc_id}, {"_id": 0})
        now_fp = fingerprint(doc or {})
        same = now_fp == fp
        untouched.append({"doc_id": doc_id, "unchanged": same})
        if not same:
            violations.append(doc_id)

    return {
        "product_id": product_id,
        "price_before": old_price,
        "price_after": new_price,
        "master_updated": bool(update_master),
        "changed_documents": changed,
        "untouched_documents": untouched,
        "untouched_verified": not violations,
        "violations": violations,
        "needs_credit_note": [{"doc_id": d["doc_id"], "doc_number": d["doc_number"],
                               "reason": d["lock_reason"], "delta": d["delta"]}
                              for d in plan["locked_documents"]],
        "reason": reason,
        "actor": actor,
        "at": now_iso(),
    }
