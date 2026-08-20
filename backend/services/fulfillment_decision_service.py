"""FASE E-8 (E8.10b#4 · US16) — **KEPUTUSAN PEMENUHAN** milik Admin Sales.

Satu pintu untuk tiga jalan yang selama ini tersebar di lima layar:

  1. **Ambil dari PT lain**   → Permintaan Internal (PIN) + jadikan transaksi antar-PT
                                (mesin G-6, dokumen kembar) **bertaut ke pesanannya**.
  2. **Reorder ke supplier**  → PR dari SO (`restock_service`, jejak dua arah).
  3. **Tahan untuk barang masuk** → catat keputusan menunggu + tanggal janji dari PO
                                yang sudah di jalan (backorder tetap mesin yang bekerja).

PRINSIP: **tidak ada mesin baru.** Modul ini hanya menyatukan mesin yang sudah
terbukti + MENCATAT keputusannya pada pesanan (`sales_orders.fulfillment_decision`)
supaya pertanyaan "kenapa pesanan ini menunggu?" terjawab di layar, bukan di ingatan
orang. Karena keputusannya menempel pada dokumen pesanan, tidak ada koleksi baru.

WEWENANG: seluruh jalur di sini adalah wewenang PENUH Admin Sales — tanpa persetujuan
manajer (keputusan pemilik E8.10b#4). Satu-satunya kunci yang bisa menahan adalah
ambang rupiah antar-PT di Pusat Pengaturan (bawaan: tidak mengunci Admin Sales).
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import now_iso, safe_doc

MODES = ("interco", "reorder", "wait")


class FulfillmentError(Exception):
    """Kegagalan ber-alasan (dipetakan ke 400/409 oleh router)."""


async def _order(order_id: str) -> Dict[str, Any]:
    o = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    if not o:
        raise FulfillmentError("Pesanan tidak ditemukan.")
    return o


async def shortages(order: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Baris yang kurang stok pada satu pesanan — dari papan pending SO yang sudah ada."""
    from services import stock_bucket_service as sbs
    board = await sbs.pending_so_board({"entity_id": order.get("entity_id")})
    return [b for b in board if b.get("order_id") == order["id"]]


async def options(order: Dict[str, Any]) -> Dict[str, Any]:
    """Tiga pilihan + kelayakannya masing-masing (supaya tombol tidak mati tanpa alasan)."""
    from services.internal_request_service import availability
    from services import restock_service

    kurang = await shortages(order)
    buyer = order.get("entity_id") or ""

    # Kandidat PT sumber: yang punya stok cukup untuk SETIAP baris kurang.
    ent_rows = await db.business_entities.find(
        {"status": "active"}, {"_id": 0, "id": 1, "short_name": 1, "legal_name": 1}).to_list(200)
    kandidat: List[Dict[str, Any]] = []
    for ent in ent_rows:
        if ent["id"] == buyer:
            continue
        lines, cukup_semua = [], bool(kurang)
        for b in kurang:
            av = await availability(b["product_id"], buyer)
            punya = round(float((av.get("by_entity") or {}).get(ent["id"], 0.0)), 4)
            cukup = punya + 0.0001 >= float(b["backorder_qty"])
            cukup_semua = cukup_semua and cukup
            lines.append({"product_id": b["product_id"], "product_name": b["product_name"],
                          "needed": b["backorder_qty"], "available": punya, "enough": cukup})
        kandidat.append({
            "entity_id": ent["id"],
            "entity_name": ent.get("short_name") or ent.get("legal_name") or ent["id"],
            "enough": cukup_semua, "lines": lines,
        })
    kandidat.sort(key=lambda c: (not c["enough"], c["entity_name"]))

    state = {}
    try:
        state = await restock_service.order_restock_state(order["id"])
    except Exception:  # noqa: BLE001 — panel tetap harus tampil walau kandidat gagal dihitung
        state = {}

    incoming = round(sum(float(b.get("incoming_total") or 0) for b in kurang), 4)
    promise = next((b.get("promise_date") for b in kurang if b.get("promise_date")), "")

    return {
        "order_id": order["id"], "order_number": order.get("number"),
        "customer_name": order.get("customer_name"),
        "entity_id": buyer,
        "shortages": kurang,
        "decision": order.get("fulfillment_decision") or None,
        "options": {
            "interco": {
                "available": any(c["enough"] for c in kandidat),
                "candidates": kandidat,
                "reason": ("" if any(c["enough"] for c in kandidat) else
                           "Belum ada badan usaha grup yang stoknya cukup untuk semua baris."),
            },
            "reorder": {
                "available": bool(kurang),
                "open_pr_number": (state or {}).get("open_pr_number", ""),
                "reason": ("" if kurang else "Tidak ada kekurangan pada pesanan ini."),
            },
            "wait": {
                "available": incoming > 0,
                "incoming_total": incoming,
                "promise_date": promise,
                "reason": ("" if incoming > 0 else
                           "Tidak ada barang masuk terjadwal — pilih ambil dari PT lain "
                           "atau reorder ke supplier."),
            },
        },
    }


async def _record(order_id: str, decision: Dict[str, Any]) -> None:
    await db.sales_orders.update_one(
        {"id": order_id},
        {"$set": {"fulfillment_decision": decision, "updated_at": now_iso()},
         "$push": {"status_history": {
             "status": "fulfillment_decision", "stage": decision["mode"],
             "timestamp": decision["at"], "user": decision["by"],
             "note": decision["summary"]}}})


async def decide(order_id: str, mode: str, actor: Dict[str, Any], *,
                 source_entity_id: str = "", note: str = "",
                 product_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    if mode not in MODES:
        raise FulfillmentError(f"Mode pemenuhan tidak dikenal: {mode}")
    order = await _order(order_id)
    kurang = await shortages(order)
    if product_ids:
        kurang = [b for b in kurang if b["product_id"] in set(product_ids)]
    if not kurang:
        raise FulfillmentError(
            "Tidak ada kekurangan yang perlu diputuskan pada pesanan ini "
            "(papan pending SO tidak menemukan baris backorder aktif).")

    hasil: Dict[str, Any] = {}
    if mode == "interco":
        hasil = await _take_from_other_entity(order, kurang, actor, source_entity_id, note)
    elif mode == "reorder":
        hasil = await _reorder_supplier(order, kurang, actor, note)
    else:
        hasil = await _wait_incoming(order, kurang, actor, note)

    decision = {
        "mode": mode, "by": actor.get("name", ""), "by_id": actor.get("id", ""),
        "by_role": actor.get("role", ""), "at": now_iso(),
        "note": (note or "").strip()[:400],
        "summary": hasil["summary"],
        "ref_type": hasil.get("ref_type", ""), "ref_id": hasil.get("ref_id", ""),
        "ref_number": hasil.get("ref_number", ""),
        "products": [b["product_id"] for b in kurang],
    }
    await _record(order["id"], decision)
    return {"order_id": order["id"], "order_number": order.get("number"),
            "decision": decision, **hasil}


async def _take_from_other_entity(order, kurang, actor, source_entity_id, note):
    """PIN → transaksi antar-PT, bertaut pesanan (E8.12: `source_order_id`)."""
    from services import internal_request_service as irs
    if not source_entity_id:
        raise FulfillmentError(
            "Pilih badan usaha sumber dulu — daftar kandidat beserta stok & kesiapan "
            "harga internalnya ada di panel pemenuhan.")
    payload = {
        "items": [{"product_id": b["product_id"], "quantity": b["backorder_qty"],
                   "notes": f"kekurangan {order.get('number')}"} for b in kurang],
        "reason": (note or f"Memenuhi kekurangan pesanan {order.get('number')} "
                           f"({order.get('customer_name')})")[:400],
        "notes": note or "",
        "source_order_id": order["id"],
    }
    try:
        # `cross_entity=False`: Admin Sales BUKAN peran lintas-entitas — sumber tidak
        # ditulis saat membuat permintaan, melainkan saat mengesahkannya di bawah.
        req = await irs.create(payload, actor, order.get("entity_id") or "", cross_entity=False)
        pair = await irs.convert(req["id"], actor, source_entity_id=source_entity_id,
                                 submit_now=True,
                                 notes=f"Pemenuhan {order.get('number')}")
    except irs.InternalRequestError as exc:
        raise FulfillmentError(str(exc)) from exc

    ic = (pair.get("interco") or {}) if isinstance(pair, dict) else {}
    buyer_doc = ic.get("buyer") or {}
    seller_doc = ic.get("seller") or {}
    nomor = buyer_doc.get("number") or seller_doc.get("number") or ""

    # E8.12/A8 — JEJAK DUA ARAH pesanan ⇄ transaksi antar-PT. Tanpa ini pertanyaan
    # "transaksi antar-PT ini untuk pesanan siapa?" hanya terjawab dari catatan bebas.
    from services import doc_refs_service as refs
    for ict_id in (buyer_doc.get("id", ""), seller_doc.get("id", "")):
        if ict_id:
            await refs.safe_link(("interco_transaction", ict_id),
                                 ("sales_order", order["id"]), "fulfills",
                                 note=f"kekurangan {order.get('number')}")
    return {
        "ref_type": "interco_transaction",
        "ref_id": buyer_doc.get("id", "") or seller_doc.get("id", ""),
        "ref_number": nomor,
        "internal_request": {"id": req["id"], "number": req.get("number")},
        "interco": {"pair_id": ic.get("pair_id", ""),
                    "buyer_number": buyer_doc.get("number", ""),
                    "seller_number": seller_doc.get("number", ""),
                    "grand_total": seller_doc.get("grand_total", 0)},
        "summary": (f"Kekurangan diambil dari PT lain lewat {nomor or 'transaksi antar-PT'} "
                    f"(permintaan {req.get('number')})"),
    }


async def _reorder_supplier(order, kurang, actor, note):
    """PR dari SO — mesin `restock_service` (jejak dua arah `source_ref_id`)."""
    from services import restock_service
    items = [{"product_id": b["product_id"], "quantity": b["backorder_qty"],
              "unit": b.get("unit", ""), "note": f"kekurangan {order.get('number')}"}
             for b in kurang]
    try:
        res = await restock_service.request_repeat_restock(
            order["id"], items, actor,
            reason=(note or f"Reorder untuk memenuhi {order.get('number')}")[:300],
            notes=note or "", submit_now=True)
    except restock_service.RestockError as exc:
        raise FulfillmentError(str(exc)) from exc
    pr = res.get("requisition") or res.get("pr") or res
    nomor = pr.get("number") or pr.get("pr_number") or ""
    return {"ref_type": "purchase_requisition", "ref_id": pr.get("id", ""),
            "ref_number": nomor, "requisition": pr,
            "summary": f"Reorder ke supplier lewat {nomor or 'permintaan pembelian'}"}


async def _wait_incoming(order, kurang, actor, note):
    """Tahan untuk barang masuk: tegaskan janji tanggal dari PO yang sudah di jalan."""
    incoming = round(sum(float(b.get("incoming_total") or 0) for b in kurang), 4)
    promise = next((b.get("promise_date") for b in kurang if b.get("promise_date")), "")
    if incoming <= 0:
        raise FulfillmentError(
            "Tidak ada barang masuk terjadwal untuk baris ini — menahan berarti pesanan "
            "menggantung. Pilih ambil dari PT lain atau reorder ke supplier.")
    return {"ref_type": "incoming_supply", "ref_id": "", "ref_number": "",
            "incoming_total": incoming, "promise_date": promise,
            "summary": (f"Ditahan menunggu barang masuk {incoming:g} "
                        + (f"· janji {str(promise)[:10]}" if promise else "")).strip()}
