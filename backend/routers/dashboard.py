"""Dashboard router: main metrics + overview."""
from typing import Any, Dict
from fastapi import APIRouter, Request
from db import db
from core_utils import safe_doc
from dependencies import current_user
from services.inventory_service import expire_old_reservations
from services import sales_ownership          # FASE E-8 (E8.4/US11) — "Pesanan Saya"
from entity_scope import entity_ctx, resolve_list_scope

router = APIRouter(prefix="/api")


@router.get("/dashboard")
async def dashboard(request: Request, entity_id: str = None) -> Dict[str, Any]:
    expired = await expire_old_reservations()
    # Multi-Entity (Fase 0): orders & customers di-scope per entitas; produk,
    # gudang & stok bersifat SHARED lintas-entitas (lihat KN_14 §7).
    # KONSISTENSI (RC-7/INV-4/INV-5): pakai resolve_list_scope yang sama dgn
    # GET /sales-orders → tanpa header/param = entitas AKTIF; header X-Entity-Id:all
    # (view_all) = semua entitas yang diizinkan. KPI dashboard SELALU == list.
    ctx = await entity_ctx(request)
    actor = await current_user(request)
    scope = resolve_list_scope("sales_orders", {}, ctx, entity_id)
    # FASE E-8 (E8.4 · US11) — KEPEMILIKAN SALES WAJIB IKUT DI SINI JUGA.
    # Layar "Pesanan" tidak memanggil `GET /sales-orders`; ia memakai `orders[]`
    # dari respons dasbor ini (`hooks/useAppActions.js` — satu panggilan untuk
    # seluruh aplikasi). Karena dasbor dulu hanya menyaring per BADAN USAHA,
    # sales lapangan tetap melihat pesanan rekannya di layar (mis. `sales@`
    # melihat `SO-0008` milik `sales2@`) dan kartu TOTAL menghitung 9, padahal
    # `GET /sales-orders` sudah benar mengembalikan 8. Inilah kelas bug yang
    # diperingatkan `services/sales_ownership.py`: definisi "pesanan saya"
    # tercecer di satu tempat saja sudah cukup untuk membocorkan pipeline rekan.
    # `apply_scope` hanya mengikat peran `sales`; sales_admin/finance/manager/
    # admin/warehouse tetap melihat keseluruhan pesanan seperti sebelumnya.
    order_scope = sales_ownership.apply_scope(scope, actor)
    products_raw = await db.products.find({}, {"_id": 0}).to_list(100)
    orders_raw = await db.sales_orders.find(order_scope, {"_id": 0}).sort("created_at", -1).to_list(20)
    # FASE E-4 (E4.1) — gudang KHUSUS badan usaha lain tidak ikut ke dasbor:
    # kalau ikut, angka "Gudang Aktif" & pemilih gudang di layar menawarkan
    # gudang yang haram dipakai badan usaha aktif.
    from services import warehouse_scope_service as whscope
    wh_filter = whscope.usable_query(ctx.active_entity_id)
    warehouses_raw = await db.warehouses.find(wh_filter, {"_id": 0}).to_list(100)
    customers_raw = await db.customers.find(scope, {"_id": 0}).to_list(100)
    products = [safe_doc(p) for p in products_raw if p]
    orders = [safe_doc(o) for o in orders_raw if o]
    wh_names = await whscope.entity_name_map()
    warehouses = [whscope.decorate(safe_doc(w), wh_names, ctx.active_entity_id)
                  for w in warehouses_raw if w]
    customers = [safe_doc(c) for c in customers_raw if c]
    # G9 fix (RC-7): active_orders dihitung dari SELURUH order via count_documents,
    # BUKAN dari window 20 order terakhir (yang membuat KPI salah saat >20 order).
    # E8.4 — ikut `order_scope` supaya kartu "Pesanan Aktif" tidak pernah lebih besar
    # dari daftar di bawahnya (angka yang tak cocok = pengguna berhenti percaya).
    active_orders = await db.sales_orders.count_documents(
        {**order_scope, "status": {"$nin": ["done", "cancelled", "expired"]}}
    )
    total_products = await db.products.count_documents({})
    total_warehouses = await db.warehouses.count_documents(wh_filter)
    total_customers = await db.customers.count_documents(scope)
    # INV-2/INV-3 (RC-7) — KPI stok dashboard SELALU konsisten dgn GET /inventory/balances:
    # agregasi dari koleksi inventory_balances yang di-SCOPE sama (owner_entity_id).
    # Sebelumnya memakai product_summary() TANPA scope → menghitung stok LINTAS-entitas
    # (mis. roll yang kepemilikannya sudah dipindah lintas-PT via R3 ownership transfer),
    # sehingga KPI > Σbalances (drift 1 meter). Kini keduanya seragam per-entitas aktif.
    bal_scope = resolve_list_scope("inventory_balances", {}, ctx, entity_id)
    bal_docs = await db.inventory_balances.find(bal_scope, {"_id": 0}).to_list(5000)
    per_prod: Dict[str, Dict[str, float]] = {}
    total_available = 0.0
    total_reserved = 0.0
    for b in bal_docs:
        pid = b.get("product_id")
        av = float(b.get("available_qty", 0) or 0)
        rv = float(b.get("reserved_qty", 0) or 0)
        d = per_prod.setdefault(pid, {"on_hand_qty": 0.0, "reserved_qty": 0.0,
                                      "available_qty": 0.0, "roll_count": 0,
                                      "on_hand_roll_count": 0})
        d["available_qty"] += av
        d["reserved_qty"] += rv
        d["on_hand_qty"] += float(b.get("on_hand_qty", 0) or 0)
        d["roll_count"] += int(b.get("roll_count", 0) or 0)
        d["on_hand_roll_count"] += int(b.get("on_hand_roll_count", 0) or 0)
        total_available += av
        total_reserved += rv
    for product in products:
        s = per_prod.get(product["id"], {"on_hand_qty": 0.0, "reserved_qty": 0.0,
                                         "available_qty": 0.0, "roll_count": 0,
                                         "on_hand_roll_count": 0})
        product.update({k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.items()})
    total_available = round(total_available, 2)
    total_reserved = round(total_reserved, 2)
    return {
        "expired_released": expired,
        "metrics": {
            "products": total_products,
            "warehouses": total_warehouses,
            "customers": total_customers,
            "available_qty": total_available,
            "reserved_qty": total_reserved,
            "active_orders": active_orders,
        },
        "products": products,
        "orders": orders,
        "warehouses": warehouses,
        "customers": customers,
    }
