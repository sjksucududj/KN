"""Depth #3 — Supplier Intelligence: Price-List resolution + Scorecard.

Modul ini menambahkan kecerdasan pemasok di atas master `suppliers`:

- Price-List (koleksi `supplier_price_lists`, prefix `spl_`): harga beli per
  (supplier, product) lengkap dengan UOM, MOQ (`min_qty`), lead-time per produk,
  dan masa berlaku (`valid_from`/`valid_until`).
- `resolve_price()` — cari harga aktif & masih berlaku TERBAIK untuk auto-isi
  PO / konversi PR. Fallback ke `harga_pokok`/`price` produk bila tak ada entri.
  Unit mengikuti UOM entri price-list (default = base_unit produk) sehingga
  pembelian konsisten dengan UOM engine yang sudah ada (Sub-fase 1.13).
- `compute_scorecard()` — metrik dari data NYATA (tanpa input manual):
  `purchase_orders` (+ penerimaan via `wms_tasks`/`last_received_at`) dan
  `purchase_returns` (reject). Menghasilkan on-time rate, avg lead-time,
  fill-rate, reject/quality rate, total spend, dan rating komposit 0-5.

Fungsi murni-orchestration (async I/O ke DB), tanpa JSX/HTTP — mudah diuji.
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from db import db
from core_utils import now_iso, safe_doc

# Status PO yang TIDAK dihitung dalam scorecard (tak jadi transaksi).
NON_COUNTED_PO = {"cancelled", "rejected"}
# Status PO yang sudah/sedang menerima barang (punya data penerimaan).
RECEIVED_PO_STATUS = {"receiving", "partial", "completed", "closed_short"}
# Status retur yang dihitung sebagai reject nyata.
COUNTED_RETURN_STATUS_EXCLUDE = {"cancelled", "rejected", "draft"}


def _parse_dt(value: Any) -> Optional[datetime]:
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


# ─── Price-List resolution ───────────────────────────────────────────────────

async def resolve_price(supplier_id: str, product_id: str, qty: float = 0.0) -> Dict[str, Any]:
    """Resolusi harga beli untuk (supplier, product, qty).

    Aturan pilih: entri `active`, masih dalam masa berlaku, `min_qty <= qty`
    (MOQ tercapai; qty=0 mengabaikan filter MOQ). Bila beberapa cocok →
    pilih tier `min_qty` terbesar yang <= qty, lalu harga termurah.

    Fallback: bila tak ada entri → harga_pokok/price produk (source=product_fallback).
    """
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    base_unit = (product or {}).get("base_unit", "meter")
    result: Dict[str, Any] = {
        "found": False, "supplier_id": supplier_id, "product_id": product_id,
        "price": 0.0, "unit": base_unit, "lead_time_days": 0,
        "min_qty": 0.0, "valid_until": "", "currency": "IDR",
        "entry_id": "", "source": "none",
    }

    if supplier_id and product_id:
        now = datetime.now(timezone.utc)
        entries = await db.supplier_price_lists.find(
            {"supplier_id": supplier_id, "product_id": product_id, "status": "active"},
            {"_id": 0}).to_list(100)
        valid: List[Dict[str, Any]] = []
        date_ok: List[Dict[str, Any]] = []
        for e in entries:
            vf = _parse_dt(e.get("valid_from"))
            vu = _parse_dt(e.get("valid_until"))
            if vf and now < vf:               # belum berlaku
                continue
            if vu and now > vu:               # kadaluarsa
                continue
            date_ok.append(e)
            mq = float(e.get("min_qty", 0) or 0)
            if mq > float(qty or 0):           # MOQ belum tercapai (qty=0 → hanya tier MOQ 0)
                continue
            valid.append(e)
        # Bila qty di bawah semua MOQ tier → pakai tier MOQ TERKECIL sbg harga acuan.
        if not valid and date_ok:
            date_ok.sort(key=lambda x: float(x.get("min_qty", 0) or 0))
            valid = [date_ok[0]]
        if valid:
            # Tier MOQ terbesar yang memenuhi qty (diskon terbaik), lalu harga termurah.
            valid.sort(key=lambda x: (-float(x.get("min_qty", 0) or 0),
                                      float(x.get("price", 0) or 0)))
            best = valid[0]
            lead = int(best.get("lead_time_days", 0) or 0)
            if lead <= 0:
                sup = await db.suppliers.find_one(
                    {"id": supplier_id}, {"_id": 0, "lead_time_days": 1})
                lead = int((sup or {}).get("lead_time_days", 0) or 0)
            result.update({
                "found": True,
                "price": float(best.get("price", 0) or 0),
                "unit": best.get("unit") or base_unit,
                "lead_time_days": lead,
                "min_qty": float(best.get("min_qty", 0) or 0),
                "valid_until": best.get("valid_until", "") or "",
                "currency": best.get("currency", "IDR") or "IDR",
                "entry_id": best.get("id", ""),
                "source": "price_list",
            })
            return result

    # Fallback ke produk (+ lead-time default supplier bila ada).
    if product:
        fallback_price = float(product.get("harga_pokok", 0) or product.get("price", 0) or 0)
        lead = 0
        if supplier_id:
            sup = await db.suppliers.find_one(
                {"id": supplier_id}, {"_id": 0, "lead_time_days": 1})
            lead = int((sup or {}).get("lead_time_days", 0) or 0)
        result.update({
            "price": round(fallback_price, 2), "unit": base_unit,
            "lead_time_days": lead, "source": "product_fallback",
        })
    return result


# ─── Scorecard (computed from real PO + receiving + returns) ─────────────────

async def _po_receipt_date(po: Dict[str, Any]) -> Optional[datetime]:
    """Tanggal penerimaan aktual sebuah PO.

    Prioritas: `last_received_at` → task inbound terbaru yang sudah diterima
    (`completed`/`qc_pending`/`put_away`) → `updated_at` PO.
    """
    rd = _parse_dt(po.get("last_received_at"))
    if rd:
        return rd
    task = await db.wms_tasks.find_one(
        {"po_id": po.get("id"), "flow_type": "inbound",
         "status": {"$in": ["completed", "qc_pending", "put_away"]}},
        {"_id": 0, "updated_at": 1}, sort=[("updated_at", -1)])
    if task and task.get("updated_at"):
        return _parse_dt(task["updated_at"])
    return _parse_dt(po.get("updated_at"))


async def compute_scorecard(supplier_id: str) -> Optional[Dict[str, Any]]:
    """Hitung scorecard supplier dari data transaksi nyata."""
    sup = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not sup:
        return None

    pos = await db.purchase_orders.find(
        {"supplier_id": supplier_id, "status": {"$nin": list(NON_COUNTED_PO)}},
        {"_id": 0}).sort("created_at", -1).to_list(1000)

    total_spend = 0.0
    ordered_qty = 0.0
    received_qty = 0.0
    on_time = 0
    delivered_pos = 0          # PO dengan tanggal terima + expected (basis on-time)
    lead_times: List[int] = []
    rows: List[Dict[str, Any]] = []

    for po in pos:
        total_spend += float(po.get("total_amount", 0) or 0)
        po_ordered = sum(float(it.get("quantity", 0) or 0) for it in po.get("items", []))
        po_received = sum(float(it.get("received_qty", 0) or 0) for it in po.get("items", []))
        is_received_stage = po.get("status") in RECEIVED_PO_STATUS
        # Fill metrics hanya dari PO yang SUDAH masuk tahap penerimaan (adil:
        # PO pending/waiting belum berkesempatan diterima → tidak menurunkan fill-rate).
        if is_received_stage:
            ordered_qty += po_ordered
            received_qty += po_received

        row = {
            "po_id": po.get("id"), "po_number": po.get("po_number"),
            "status": po.get("status"),
            "total_amount": round(float(po.get("total_amount", 0) or 0), 2),
            "ordered_qty": round(po_ordered, 2), "received_qty": round(po_received, 2),
            "expected_delivery_date": po.get("expected_delivery_date", "") or "",
            "on_time": None, "lead_time_days": None,
        }
        if is_received_stage and po_received > 0:
            rdate = await _po_receipt_date(po)
            cdate = _parse_dt(po.get("created_at"))
            edate = _parse_dt(po.get("expected_delivery_date"))
            if rdate and cdate:
                lt = (rdate - cdate).days
                if lt >= 0:
                    lead_times.append(lt)
                    row["lead_time_days"] = lt
            if rdate and edate:
                delivered_pos += 1
                is_on_time = rdate.date() <= edate.date()
                row["on_time"] = is_on_time
                if is_on_time:
                    on_time += 1
        rows.append(row)

    # Reject nyata dari retur beli (Nota Debit).
    rets = await db.purchase_returns.find(
        {"supplier_id": supplier_id,
         "status": {"$nin": list(COUNTED_RETURN_STATUS_EXCLUDE)}},
        {"_id": 0}).to_list(1000)
    rejected_qty = 0.0
    for r in rets:
        rejected_qty += sum(float(it.get("quantity", 0) or 0) for it in r.get("items", []))

    on_time_rate = round(on_time / delivered_pos, 4) if delivered_pos else None
    avg_lead = round(sum(lead_times) / len(lead_times), 1) if lead_times else None
    fill_rate = round(min(received_qty / ordered_qty, 1.0), 4) if ordered_qty else None
    reject_rate = round(rejected_qty / received_qty, 4) if received_qty else None
    quality_rate = round(max(1 - reject_rate, 0.0), 4) if reject_rate is not None else None

    # Rating komposit (0-5) — hanya dari metrik yang tersedia (bobot dinormalisasi).
    comps: List[float] = []
    weights: List[float] = []
    if on_time_rate is not None:
        comps.append(on_time_rate); weights.append(0.40)
    if quality_rate is not None:
        comps.append(quality_rate); weights.append(0.35)
    if fill_rate is not None:
        comps.append(fill_rate); weights.append(0.25)
    rating = None
    if comps:
        rating = round(sum(c * w for c, w in zip(comps, weights)) / sum(weights) * 5, 1)

    return {
        "supplier_id": supplier_id,
        "supplier_name": sup.get("name", ""),
        "supplier_code": sup.get("code", ""),
        "lead_time_days_default": int(sup.get("lead_time_days", 0) or 0),
        "has_data": len(pos) > 0,
        "metrics": {
            "total_pos": len(pos),
            "delivered_pos": delivered_pos,
            "total_spend": round(total_spend, 2),
            "ordered_qty": round(ordered_qty, 2),
            "received_qty": round(received_qty, 2),
            "rejected_qty": round(rejected_qty, 2),
            "return_count": len(rets),
            "on_time_rate": on_time_rate,
            "avg_lead_time_days": avg_lead,
            "fill_rate": fill_rate,
            "reject_rate": reject_rate,
            "quality_rate": quality_rate,
            "rating": rating,
        },
        "purchase_orders": rows,
        "generated_at": now_iso(),
    }


# ─── Supplier 360 (profil + PO + Tagihan + Retur + Scorecard) ────────────────

# Status PO yang dianggap "terbuka" (belum tuntas / masih menimbulkan komitmen).
_PO_CLOSED = {"completed", "closed", "closed_short", "cancelled", "rejected"}


async def supplier_360(supplier_id: str) -> Optional[Dict[str, Any]]:
    """Agregasi 'Supplier 360': profil + PO + tagihan + retur + scorecard +
    ringkasan keuangan (AP/hutang), daftar dokumen, daftar harga & riwayat harga."""
    from services.vendor_bill_service import bill_financials  # hindari import melingkar

    sup = safe_doc(await db.suppliers.find_one({"id": supplier_id}, {"_id": 0}))
    if not sup:
        return None
    pos = await db.purchase_orders.find(
        {"supplier_id": supplier_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    bills = await db.vendor_bills.find(
        {"supplier_id": supplier_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    rets = await db.purchase_returns.find(
        {"supplier_id": supplier_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    price_list = await db.supplier_price_lists.find(
        {"supplier_id": supplier_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    scorecard = await compute_scorecard(supplier_id)

    now = datetime.now(timezone.utc)
    cur_year = str(now.year)

    # ── Ringkasan keuangan (AP / hutang) dari vendor bills ──
    ap_outstanding = 0.0
    overdue_amount = 0.0
    overdue_days = 0
    paid_total = 0.0
    for b in bills:
        fin = bill_financials(b)
        out = float(fin.get("outstanding", 0) or 0)
        b["outstanding"] = out
        b["pay_status"] = fin.get("pay_status")
        b["grand_total"] = fin.get("grand_total", b.get("grand_total", 0))
        paid_total += float(b.get("amount_paid", 0) or 0)
        status = (b.get("status") or "").lower()
        if status in {"posted", "paid"} and out > 0.01:
            ap_outstanding += out
            due = _parse_dt(b.get("due_date"))
            if due and due < now:
                overdue_amount += out
                overdue_days = max(overdue_days, (now - due).days)

    po_total_value = round(sum(float(p.get("total_amount", 0) or 0) for p in pos), 2)
    open_po_value = round(sum(
        float(p.get("total_amount", 0) or 0) for p in pos
        if (p.get("status") or "").lower() not in _PO_CLOSED), 2)
    purchase_ytd = round(sum(
        float(p.get("total_amount", 0) or 0) for p in pos
        if str(p.get("created_at", "")).startswith(cur_year)), 2)

    sc_metrics = (scorecard or {}).get("metrics", {}) if scorecard else {}
    sup["finance"] = {
        "ap_outstanding": round(ap_outstanding, 2),
        "overdue_amount": round(overdue_amount, 2),
        "overdue_days": overdue_days,
        "open_po_value": open_po_value,
        "po_total_value": po_total_value,
        "purchase_ytd": purchase_ytd,
        "paid_total": round(paid_total, 2),
        "bill_total": round(sum(float(b.get("grand_total", 0) or 0) for b in bills), 2),
        "payment_term_code": sup.get("payment_term_code") or "",
        "lead_time_days": sup.get("lead_time_days") or 0,
        "avg_lead_time_days": sc_metrics.get("avg_lead_time_days"),
        "open_po_count": sum(1 for p in pos if (p.get("status") or "").lower() not in _PO_CLOSED),
        "rating": sc_metrics.get("rating"),
    }

    # ── Daftar harga (pricelist) + riwayat harga per produk (dari item PO) ──
    price_history: Dict[str, Dict[str, Any]] = {}
    for p in pos:
        for it in (p.get("items") or []):
            pid = it.get("product_id")
            if not pid:
                continue
            price = float(it.get("price", 0) or 0)
            if price <= 0:
                continue
            bucket = price_history.setdefault(pid, {
                "product_id": pid,
                "product_name": it.get("product_name") or it.get("sku") or pid,
                "sku": it.get("sku"),
                "unit": it.get("unit"),
                "entries": [],
            })
            bucket["entries"].append({
                "po_number": p.get("po_number") or p.get("id"),
                "po_id": p.get("id"),
                "date": p.get("created_at"),
                "price": round(price, 2),
                "qty": float(it.get("quantity", 0) or 0),
                "unit": it.get("unit"),
            })
    # ringkas: harga terakhir + jumlah titik histori
    price_history_list = []
    for pid, bucket in price_history.items():
        entries = sorted(bucket["entries"], key=lambda e: str(e.get("date") or ""), reverse=True)
        prices = [e["price"] for e in entries]
        price_history_list.append({
            **bucket,
            "entries": entries,
            "last_price": entries[0]["price"] if entries else None,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "points": len(entries),
        })
    price_history_list.sort(key=lambda x: (x.get("product_name") or "").lower())

    # ── Daftar dokumen gabungan (untuk tab Dokumen) ──
    documents: List[Dict[str, Any]] = []
    for p in pos:
        documents.append({
            "doc_type": "purchase_order", "label": "Pesanan Pembelian",
            "source_id": p.get("id"), "number": p.get("po_number") or p.get("id"),
            "date": p.get("created_at"), "status": p.get("status"),
            "amount": float(p.get("total_amount", 0) or 0), "entity_id": p.get("entity_id"),
        })
    for b in bills:
        documents.append({
            "doc_type": "vendor_bill", "label": "Vendor Bill",
            "source_id": b.get("id"), "number": b.get("bill_number") or b.get("id"),
            "date": b.get("created_at"), "status": b.get("status"),
            "amount": float(b.get("grand_total", 0) or 0), "entity_id": b.get("entity_id"),
        })
    for r in rets:
        documents.append({
            "doc_type": "purchase_return", "label": "Retur Beli",
            "source_id": r.get("id"), "number": r.get("debit_note_number") or r.get("number") or r.get("id"),
            "date": r.get("created_at"), "status": r.get("status"),
            "amount": float(r.get("total_amount", 0) or 0), "entity_id": r.get("entity_id"),
        })
    documents.sort(key=lambda d: str(d.get("date") or ""), reverse=True)

    sup["purchase_orders"] = pos
    sup["po_count"] = len(pos)
    sup["po_total_value"] = po_total_value
    sup["vendor_bills"] = bills
    sup["bill_count"] = len(bills)
    sup["bill_total"] = sup["finance"]["bill_total"]
    sup["returns"] = rets
    sup["return_count"] = len(rets)
    sup["price_list"] = price_list
    sup["price_list_count"] = len(price_list)
    sup["price_history"] = price_history_list
    sup["documents"] = documents
    sup["scorecard"] = scorecard
    return sup


# ─── Price-deviation guard (Depth #3 — approval bila harga PO > price-list) ────

async def assess_price_deviation(supplier_id: str, items: List[Dict[str, Any]],
                                 threshold_pct: float = 10.0) -> Dict[str, Any]:
    """Bandingkan harga item PO terhadap harga price-list supplier (acuan).

    `items` = list {product_id, sku?, product_name?, price, quantity}.
    Hanya entri price-list (source=price_list) yang dianggap acuan; bila produk
    tak punya price-list supplier, item dilewati (tak bisa dinilai menyimpang).
    Flag bila ada item dengan kenaikan harga > `threshold_pct`%.
    """
    flagged_items: List[Dict[str, Any]] = []
    max_pct = 0.0
    for it in items:
        price = float(it.get("price", 0) or 0)
        qty = float(it.get("quantity", 0) or 0)
        if price <= 0:
            continue
        resolved = await resolve_price(supplier_id, it.get("product_id", ""), qty)
        if resolved.get("source") != "price_list":
            continue  # tak ada acuan price-list → tak dinilai
        ref = float(resolved.get("price", 0) or 0)
        if ref <= 0:
            continue
        pct = round((price - ref) / ref * 100, 2)
        if pct > float(threshold_pct):
            max_pct = max(max_pct, pct)
            flagged_items.append({
                "product_id": it.get("product_id", ""),
                "sku": it.get("sku", ""),
                "product_name": it.get("product_name", ""),
                "price": round(price, 2),
                "ref_price": round(ref, 2),
                "unit": resolved.get("unit", ""),
                "deviation_pct": pct,
            })
    return {
        "flagged": bool(flagged_items),
        "threshold_pct": round(float(threshold_pct), 2),
        "max_deviation_pct": round(max_pct, 2),
        "items": flagged_items,
    }
