"""Backorder service (Sub-fase 1.6) — auto-fulfill lifecycle.

Saat barang masuk via Goods Receipt (inbound complete) membuat `inventory_rolls`
baru berstatus `available`, service ini mencoba **memenuhi otomatis** Sales Order
yang berstatus `waiting_stock` untuk (produk × entitas penjual) tersebut.

Prinsip:
- FIFO: order paling lama (created_at) dipenuhi lebih dulu (adil + anti-hoarding).
- Owner-scoped: hanya order milik `owner_entity_id` yang sama (jaga invarian D3).
- Reservasi nyata tetap lewat `roll_service.allocate_and_reserve_rolls(allow_partial=True)`
  (atomic find_one_and_update → aman dari race). Sisa yang belum terpenuhi tetap
  tercatat sebagai backorder hingga GR berikutnya.
- Saat seluruh backorder sebuah order terpenuhi → status kembali ke `reserved`
  (lanjut alur approval normal).
"""
from typing import Any, Dict
from db import db
from core_utils import now_iso
from services.roll_service import allocate_and_reserve_rolls

EPS = 0.01


async def auto_fulfill_backorders(product_id: str, owner_entity_id: str) -> Dict[str, Any]:
    """Penuhi otomatis backorder untuk (produk × entitas) setelah stok baru masuk.

    Mengembalikan ringkasan: berapa order disentuh, berapa selesai penuh, total qty
    terpenuhi. Berhenti saat stok available habis (allocate mengembalikan kosong).
    """
    ACTIVE = ["waiting_stock", "reserved", "waiting_approval", "approved", "confirmed"]
    orders = await db.sales_orders.find(
        {"has_backorder": True, "status": {"$in": ACTIVE},
         "entity_id": owner_entity_id, "backorders.product_id": product_id},
        {"_id": 0},
    ).sort("created_at", 1).to_list(500)

    result: Dict[str, Any] = {
        "product_id": product_id, "owner_entity_id": owner_entity_id,
        "orders_touched": 0, "orders_completed": 0, "qty_fulfilled": 0.0,
    }
    stock_exhausted = False

    for order in orders:
        if stock_exhausted:
            break
        order_got = 0.0
        changed = False
        for bo in order.get("backorders", []):
            if bo.get("product_id") != product_id or bo.get("status") == "fulfilled":
                continue
            need = float(bo.get("backorder_qty", 0) or 0)
            if need <= EPS:
                continue
            allocs = await allocate_and_reserve_rolls(
                product_id, need, bo.get("customer_city", ""), owner_entity_id, order["id"],
                allow_partial=True,
            )
            got = round(sum(float(a.get("quantity", 0) or 0) for a in allocs), 2)
            if got <= EPS:
                stock_exhausted = True
                break
            # Update baris backorder
            bo["reserved_qty"] = round(float(bo.get("reserved_qty", 0) or 0) + got, 2)
            bo["backorder_qty"] = round(need - got, 2)
            if bo["backorder_qty"] <= EPS:
                bo["backorder_qty"] = 0.0
                bo["status"] = "fulfilled"
            bo["updated_at"] = now_iso()
            # Update alokasi order + anotasi fulfillment per item
            order["allocations"] = list(order.get("allocations", [])) + allocs
            for it in order.get("items", []):
                if it.get("product_id") == product_id:
                    it["reserved_qty"] = round(float(it.get("reserved_qty", 0) or 0) + got, 2)
                    it["backorder_qty"] = round(max(0.0, float(it.get("backorder_qty", 0) or 0) - got), 2)
            order_got += got
            changed = True
            if got + EPS < need:
                # stok baru tak cukup memenuhi baris ini → habis
                stock_exhausted = True
                break

        if changed:
            still_bo = any(float(b.get("backorder_qty", 0) or 0) > EPS
                           for b in order.get("backorders", []))
            prev_status = order.get("status")
            # Decouple status dari backorder (Sub-fase 1.6.1):
            #  - pure backorder (waiting_stock) → reserved begitu ada porsi ter-reservasi
            #  - status lain (reserved/waiting_approval/approved/confirmed) TIDAK diubah
            new_status = "reserved" if prev_status == "waiting_stock" else prev_status
            _bo_set = {
                "allocations": order["allocations"],
                "items": order["items"],
                "backorders": order["backorders"],
                "has_backorder": still_bo,
                "status": new_status,
                "updated_at": now_iso(),
            }
            # F4 — sinkronkan stage + sub_status (turunan status + backorder final).
            from services.so_status import stage_fields
            _bo_set.update(stage_fields({**order, **_bo_set}))
            await db.sales_orders.update_one({"id": order["id"]}, {"$set": _bo_set})
            # Auto-commit (4a): bila order sudah approved/confirmed, roll backorder yang
            # baru ter-reservasi langsung di-commit mengikuti approval awal (tanpa approval ulang).
            if new_status in ("approved", "confirmed"):
                from services.roll_service import set_order_rolls_status
                await set_order_rolls_status(order["id"], "committed")
            from dependencies import audit
            await audit("system", "backorder_auto_fulfilled", "sales_order", order["id"], {
                "product_id": product_id, "qty_fulfilled": round(order_got, 2),
                "status": new_status, "fully_fulfilled": not still_bo,
                "auto_committed": new_status in ("approved", "confirmed"),
            }, "Auto-fulfill backorder saat barang masuk (GR)")
            result["orders_touched"] += 1
            result["qty_fulfilled"] += order_got
            if not still_bo:
                result["orders_completed"] += 1
            # PS-21 — pendingan yang baru terpenuhi → notifikasi "siap kirim" ke sales
            # pemegang akun (mesin R6.5/R6.6, dedupe harian). Best-effort.
            try:
                from services import alert_ops_service as _ops
                await _ops.notify_backorder_ready(
                    {**order, "status": new_status}, product_id,
                    kind="fulfilled", qty=round(order_got, 2))
            except Exception:  # noqa: BLE001 — notifikasi tidak boleh menggagalkan fulfillment
                pass

    result["qty_fulfilled"] = round(result["qty_fulfilled"], 2)
    return result
