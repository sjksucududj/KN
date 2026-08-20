"""F2 — Multi-bucket Stock: operasi WIP & Hold (Pending SO) + papan bucket.

ADDITIVE di atas engine roll-as-SSOT (roll_service). Bucket WIP & Hold sudah
didukung rebuild_balance (status roll 'wip'/'hold' → wip_qty/hold_qty). Service ini
menambah OPERASI transisi roll (FEFO + split) + papan ringkasan per produk:
  - Hold: available → hold (soft hold / tahan untuk Pending SO). Release: hold → available.
  - WIP:  available → wip (mulai proses). Complete: wip → available.

Catatan ATP: hold & wip = bucket FISIK (masuk on_hand) tapi BUKAN available →
otomatis keluar dari ATP (atp = available + incoming). SSOT-safe (tanpa $inc balance).
"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from db import db
from core_utils import now_iso, new_id
from services.roll_service import rebuild_balance, insert_child_roll

# F2b — horizon default ATP future-aware (hari). Incoming dengan ETA dalam horizon
# dihitung sebagai "janji aman"; di luar horizon ditampilkan tapi tak menambah ATP.
DEFAULT_ATP_HORIZON_DAYS = 14
ACTIVE_BACKORDER_STATUSES = ["waiting_stock", "reserved", "waiting_approval", "approved", "confirmed"]
OPEN_PO_STATUSES = ["pending", "created", "approved", "sent"]

# Bucket yang ditampilkan di papan (urutan tampil)
BOARD_BUCKETS = [
    "available_qty", "reserved_qty", "committed_qty", "picked_qty", "packed_qty",
    "hold_qty", "wip_qty", "subcon_qty", "quarantine_qty", "blocked_qty", "damaged_qty",
    "in_transit_inbound_qty", "in_transit_transfer_qty", "in_transit_intercompany_qty",
    "in_transit_sales_qty",
]
DERIVED = ["on_hand_qty", "in_transit_qty", "incoming_qty", "on_order_qty", "owned_qty", "atp_qty"]


def _fefo_sort(rolls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(rolls, key=lambda r: (r.get("created_at", ""), -float(r.get("length_remaining", 0) or 0)))


async def move_rolls_by_qty(product_id: str, warehouse_id: str, owner_entity_id: str,
                            qty: float, from_status: str, to_status: str,
                            ref: Optional[Dict[str, Any]] = None,
                            movement_type: str = "bucket_move") -> Dict[str, Any]:
    """Pindahkan `qty` roll product×warehouse×owner dari from_status → to_status (FEFO, split)."""
    qty = round(float(qty), 2)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Qty harus lebih dari 0")
    rolls = await db.inventory_rolls.find(
        {"product_id": product_id, "warehouse_id": warehouse_id, "owner_entity_id": owner_entity_id,
         "status": from_status, "length_remaining": {"$gt": 0}}, {"_id": 0}).to_list(10000)
    rolls = _fefo_sort(rolls)
    total = sum(float(r["length_remaining"]) for r in rolls)
    if total + 0.01 < qty:
        raise HTTPException(
            status_code=409,
            detail=f"Stok '{from_status}' tidak cukup (tersedia {round(total,2)} dari {qty}).")
    remaining = qty
    moved: List[Dict[str, Any]] = []
    for roll in rolls:
        if remaining <= 0.01:
            break
        rlen = float(roll["length_remaining"])
        if rlen <= remaining + 0.01:
            await db.inventory_rolls.update_one(
                {"id": roll["id"]},
                {"$set": {"status": to_status, "bucket_ref": ref, "updated_at": now_iso()}})
            mid, mlen = roll["id"], rlen
        else:
            await db.inventory_rolls.update_one(
                {"id": roll["id"]},
                {"$set": {"length_remaining": round(rlen - remaining, 2),
                          "length_initial": round(float(roll["length_initial"]) - remaining, 2),
                          "updated_at": now_iso()}})
            child = dict(roll)
            child.pop("_id", None)
            child.update({"id": new_id("roll"), "length_initial": round(remaining, 2),
                          "length_remaining": round(remaining, 2), "status": to_status,
                          "bucket_ref": ref, "is_remnant": False,
                          "created_at": now_iso(), "updated_at": now_iso()})
            child = await insert_child_roll(child, roll)
            mid, mlen = child["id"], remaining
        moved.append({"roll_id": mid, "lot": roll.get("lot", ""), "length": round(mlen, 2),
                      "unit": roll.get("unit", "meter")})
        await db.inventory_movements.insert_one({
            "id": new_id("mov"), "product_id": product_id, "warehouse_id": warehouse_id,
            "owner_entity_id": owner_entity_id, "movement_type": movement_type,
            "quantity": round(mlen, 2), "unit": roll.get("unit", "meter"),
            "lot": roll.get("lot", ""), "roll_id": mid,
 # FASE U — satu baris mutasi menunjuk SATU roll fisik.
 "qty_rolls": (1 if mid else None),
            "source_document": (ref or {}).get("id", to_status), "timestamp": now_iso()})
        remaining -= mlen
    await rebuild_balance(product_id, warehouse_id, owner_entity_id)
    return {"moved": round(qty - max(remaining, 0), 2), "rolls": moved}


async def move_rolls_by_ref(ref_id: str, to_status: str,
                            movement_type: str = "bucket_move") -> Dict[str, Any]:
    """Kembalikan semua roll dengan bucket_ref.id == ref_id ke `to_status` (clear bucket_ref)."""
    rolls = await db.inventory_rolls.find({"bucket_ref.id": ref_id}, {"_id": 0}).to_list(10000)
    if not rolls:
        raise HTTPException(status_code=404, detail="Tidak ada roll untuk referensi ini")
    segments = set()
    total = 0.0
    for r in rolls:
        await db.inventory_rolls.update_one(
            {"id": r["id"]},
            {"$set": {"status": to_status, "bucket_ref": None, "updated_at": now_iso()}})
        qty = float(r.get("length_remaining", 0) or 0)
        total += qty
        segments.add((r["product_id"], r["warehouse_id"], r["owner_entity_id"]))
        await db.inventory_movements.insert_one({
            "id": new_id("mov"), "product_id": r["product_id"], "warehouse_id": r["warehouse_id"],
            "owner_entity_id": r["owner_entity_id"], "movement_type": movement_type,
            "quantity": round(qty, 2), "unit": r.get("unit", "meter"), "lot": r.get("lot", ""),
            "roll_id": r["id"],
            # FASE U — satu baris mutasi menunjuk SATU roll fisik.
            "qty_rolls": (1 if r["id"] else None), "source_document": ref_id, "timestamp": now_iso()})
    for p, w, o in segments:
        await rebuild_balance(p, w, o)
    return {"released": round(total, 2), "rolls": len(rolls), "ref_id": ref_id}


# ── Operasi tingkat tinggi ───────────────────────────────────────────────────

async def hold_stock(data: Dict[str, Any], actor_name: str) -> Dict[str, Any]:
    hold_id = new_id("hold")
    ref = {"type": "hold", "id": hold_id, "reason": (data.get("reason") or "").strip(),
           "hold_type": (data.get("hold_type") or "general").strip() or "general",
           "ref_type": data.get("ref_type") or "", "ref_id": data.get("ref_id") or "",
           "expires_at": data.get("expires_at") or "", "created_by": actor_name,
           "created_at": now_iso()}
    res = await move_rolls_by_qty(
        data["product_id"], data["warehouse_id"], data["owner_entity_id"],
        data["quantity"], "available", "hold", ref, movement_type="hold")
    return {**res, "hold_id": hold_id, "ref": ref}


async def release_hold(hold_id: str) -> Dict[str, Any]:
    return await move_rolls_by_ref(hold_id, "available", movement_type="hold_release")


async def start_wip(data: Dict[str, Any], actor_name: str) -> Dict[str, Any]:
    wip_id = new_id("wip")
    ref = {"type": "wip", "id": wip_id, "note": (data.get("note") or "").strip(),
           "created_by": actor_name, "created_at": now_iso()}
    res = await move_rolls_by_qty(
        data["product_id"], data["warehouse_id"], data["owner_entity_id"],
        data["quantity"], "available", "wip", ref, movement_type="wip_start")
    return {**res, "wip_id": wip_id, "ref": ref}


async def complete_wip(wip_id: str) -> Dict[str, Any]:
    return await move_rolls_by_ref(wip_id, "available", movement_type="wip_complete")


# ── M2 (Makloon/Subcon) — WIP-at-vendor bucket ───────────────────────────────

async def _value_of_moved(moved: List[Dict[str, Any]]) -> float:
    """Nilai (WAC) total dari roll yang baru dipindah = Σ length × unit_cost roll.
    Dibaca dari roll aktual agar posting GL PERSIS = perubahan subledger (anti-drift)."""
    ids = [m.get("roll_id") for m in moved if m.get("roll_id")]
    if not ids:
        return 0.0
    rolls = await db.inventory_rolls.find({"id": {"$in": ids}}, {"_id": 0}).to_list(10000)
    total = 0.0
    for r in rolls:
        uc = float(r.get("unit_cost") or r.get("base_unit_cost") or 0)
        total += float(r.get("length_remaining", 0) or 0) * uc
    return round(total, 2)


async def issue_to_subcon(product_id: str, warehouse_id: str, owner_entity_id: str,
                          qty: float, ref: Dict[str, Any]) -> Dict[str, Any]:
    """Keluarkan bahan milik KN ke mitra makloon: roll `available` → `subcon`.
    Fisik pindah ke vendor namun tetap OWNED (on_hand/owned), keluar dari ATP.
    Mengembalikan qty dipindah + NILAI WAC (untuk posting GL Dr WIP/Cr Persediaan)."""
    res = await move_rolls_by_qty(
        product_id, warehouse_id, owner_entity_id, qty, "available", "subcon",
        ref, movement_type="subcon_issue")
    res["value"] = await _value_of_moved(res.get("rolls", []))
    return res


async def consume_subcon_by_ref(ref_id: str, movement_type: str = "subcon_consume") -> Dict[str, Any]:
    """Konsumsi (retire) semua roll `subcon` dengan bucket_ref.id == ref_id.
    Bahan bertransformasi jadi output → roll input di-retire (status 'consumed',
    length 0) sehingga hilang dari semua bucket. Kembalikan qty & nilai terkonsumsi."""
    rolls = await db.inventory_rolls.find(
        {"bucket_ref.id": ref_id, "status": "subcon"}, {"_id": 0}).to_list(10000)
    segments = set()
    total_qty = 0.0
    total_val = 0.0
    for r in rolls:
        qty = float(r.get("length_remaining", 0) or 0)
        uc = float(r.get("unit_cost") or r.get("base_unit_cost") or 0)
        total_qty += qty
        total_val += qty * uc
        segments.add((r["product_id"], r["warehouse_id"], r["owner_entity_id"]))
        await db.inventory_rolls.update_one(
            {"id": r["id"]},
            {"$set": {"status": "consumed", "length_remaining": 0.0,
                      "consumed_ref": ref_id, "updated_at": now_iso()}})
        await db.inventory_movements.insert_one({
            "id": new_id("mov"), "product_id": r["product_id"], "warehouse_id": r["warehouse_id"],
            "owner_entity_id": r["owner_entity_id"], "movement_type": movement_type,
            "quantity": round(qty, 2), "unit": r.get("unit", "meter"), "lot": r.get("lot", ""),
            "lot_id": r.get("lot_id", ""),
            "roll_id": r["id"],
            # FASE U — satu baris mutasi menunjuk SATU roll fisik.
            "qty_rolls": (1 if r["id"] else None), "source_document": ref_id, "timestamp": now_iso()})
    for p, w, o in segments:
        await rebuild_balance(p, w, o)
    return {"consumed_qty": round(total_qty, 2), "consumed_value": round(total_val, 2),
            "roll_count": len(rolls), "ref_id": ref_id,
            # FASE C — lot bahan yang dikonsumsi → dipakai sebagai INDUK lot output
            "lot_ids": sorted({r.get("lot_id") for r in rolls if r.get("lot_id")})}


async def subcon_qty_by_ref(ref_id: str) -> float:
    """Total qty roll subcon aktif untuk sebuah referensi (mko/step)."""
    rolls = await db.inventory_rolls.find(
        {"bucket_ref.id": ref_id, "status": "subcon"},
        {"_id": 0, "length_remaining": 1}).to_list(10000)
    return round(sum(float(r.get("length_remaining", 0) or 0) for r in rolls), 2)


# ── Papan bucket & daftar hold/wip ───────────────────────────────────────────

async def _enrich_maps():
    warehouses = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(100)}
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(2000)}
    entities = {e["id"]: e for e in await db.business_entities.find({}, {"_id": 0}).to_list(100)}
    return warehouses, products, entities


async def bucket_board(scope: Dict[str, Any], product_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Ringkasan multi-bucket per PRODUK (rollup) + breakdown per gudang. Ter-scope owner."""
    q = dict(scope or {})
    if product_id:
        q["product_id"] = product_id
    balances = await db.inventory_balances.find(q, {"_id": 0}).to_list(5000)
    warehouses, products, entities = await _enrich_maps()
    all_fields = BOARD_BUCKETS + DERIVED
    by_product: Dict[str, Dict[str, Any]] = {}
    for b in balances:
        pid = b["product_id"]
        p = products.get(pid, {})
        grp = by_product.setdefault(pid, {
            "product_id": pid, "sku": p.get("sku", ""), "product_name": p.get("name", ""),
            "category": p.get("category", ""), "base_unit": p.get("base_unit", "meter"),
            "totals": {f: 0.0 for f in all_fields}, "warehouses": []})
        wh = warehouses.get(b.get("warehouse_id"), {})
        ent = entities.get(b.get("owner_entity_id"), {})
        row = {f: round(float(b.get(f, 0) or 0), 2) for f in all_fields}
        row.update({
            "warehouse_id": b.get("warehouse_id"), "warehouse_name": wh.get("name", ""),
            "warehouse_city": wh.get("city", ""),
            "owner_entity_id": b.get("owner_entity_id"),
            "owner_entity_name": ent.get("short_name") or ent.get("legal_name", b.get("owner_entity_id", "")),
        })
        grp["warehouses"].append(row)
        for f in all_fields:
            grp["totals"][f] = round(grp["totals"][f] + row[f], 2)
    out = list(by_product.values())
    out.sort(key=lambda x: x["product_name"])
    return out


async def list_rolls_in_bucket(scope: Dict[str, Any], status: str) -> List[Dict[str, Any]]:
    """Daftar roll aktif pada bucket tertentu (hold/wip) ter-scope owner."""
    q = dict(scope or {})
    q["status"] = status
    rolls = await db.inventory_rolls.find(q, {"_id": 0}).sort("updated_at", -1).to_list(5000)
    warehouses, products, entities = await _enrich_maps()
    # Group per bucket_ref.id (1 hold/wip = banyak roll)
    grouped: Dict[str, Dict[str, Any]] = {}
    for r in rolls:
        ref = r.get("bucket_ref") or {}
        rid = ref.get("id") or r["id"]
        p = products.get(r.get("product_id"), {})
        wh = warehouses.get(r.get("warehouse_id"), {})
        ent = entities.get(r.get("owner_entity_id"), {})
        g = grouped.setdefault(rid, {
            "ref_id": rid, "status": status,
            "product_id": r.get("product_id"), "sku": p.get("sku", ""), "product_name": p.get("name", ""),
            "warehouse_id": r.get("warehouse_id"), "warehouse_name": wh.get("name", ""),
            "owner_entity_id": r.get("owner_entity_id"),
            "owner_entity_name": ent.get("short_name") or ent.get("legal_name", r.get("owner_entity_id", "")),
            "unit": r.get("unit", "meter"), "quantity": 0.0, "roll_count": 0,
            "reason": ref.get("reason", ""), "note": ref.get("note", ""),
            "hold_type": ref.get("hold_type", "general"),
            "ref_type": ref.get("ref_type", ""), "ref_doc_id": ref.get("ref_id", ""),
            "expires_at": ref.get("expires_at", ""), "created_by": ref.get("created_by", ""),
            "created_at": ref.get("created_at", r.get("updated_at", "")),
        })
        g["quantity"] = round(g["quantity"] + float(r.get("length_remaining", 0) or 0), 2)
        g["roll_count"] += 1
    out = list(grouped.values())
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out



# ── F2b: ATP Future-Aware + Pending SO (supply/demand) ───────────────────────

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    """Parse ISO date/datetime → aware datetime (UTC). None bila kosong/invalid."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


async def _open_po_incoming(product_id: str, owner_entity_id: str) -> List[Dict[str, Any]]:
    """Baris PO terbuka (belum jadi roll) utk product×entitas → incoming supply.
    Mengembalikan list {po_number, po_id, qty, eta, warehouse_id} urut ETA naik."""
    pos = await db.purchase_orders.find(
        {"status": {"$in": OPEN_PO_STATUSES}},
        {"_id": 0, "id": 1, "po_number": 1, "items": 1, "entity_id": 1,
         "expected_delivery_date": 1, "warehouse_id": 1},
    ).to_list(2000)
    out: List[Dict[str, Any]] = []
    for po in pos:
        if po.get("entity_id") and po.get("entity_id") != owner_entity_id:
            continue
        for it in po.get("items", []):
            if it.get("product_id") == product_id:
                qty = float(it.get("quantity", it.get("qty", 0)) or 0)
                if qty > 0.01:
                    out.append({
                        "po_number": po.get("po_number", ""), "po_id": po.get("id", ""),
                        "qty": round(qty, 2), "eta": po.get("expected_delivery_date") or "",
                        "warehouse_id": po.get("warehouse_id", ""),
                    })
    out.sort(key=lambda x: (x["eta"] or "9999-12-31"))
    return out


# Status transaksi antar-PT yang barangnya BELUM masuk gudang pembeli — inilah yang
# layak disebut "janji pasokan". `received`/`invoiced`/`settled` sudah jadi roll nyata,
# jadi menghitungnya lagi akan menjanjikan barang dua kali.
INCOMING_INTERCO_STATUSES = ["draft", "confirmed", "shipped"]


async def _open_interco_incoming(product_id: str, owner_entity_id: str) -> List[Dict[str, Any]]:
    """E9.2 — pasokan yang sedang dijanjikan PT LAIN (pembelian internal antar-PT).

    CACAT YANG DITUTUP: Papan Pending SO dulu hanya melihat PO supplier, sehingga
    kekurangan stok yang SUDAH diurus lewat pembelian internal tetap tampil
    "belum tertutup" (uncovered). Akibatnya Admin Sales/pembelian bisa menerbitkan
    PR/PO kedua untuk barang yang sebenarnya sudah dijanjikan PT sebelah.
    """
    docs = await db.interco_transactions.find(
        {"role": "buyer", "buyer_entity_id": owner_entity_id,
         "status": {"$in": INCOMING_INTERCO_STATUSES},
         "items.product_id": product_id},
        {"_id": 0, "id": 1, "number": 1, "items": 1, "doc_date": 1, "due_date": 1,
         "status": 1, "seller_entity_id": 1, "seller_entity_name": 1,
         "source_order_id": 1, "source_order_number": 1,
         "warehouse_transfer_status": 1},
    ).to_list(2000)
    out: List[Dict[str, Any]] = []
    for d in docs:
        for it in d.get("items", []):
            if it.get("product_id") != product_id:
                continue
            qty = float(it.get("quantity", it.get("qty", 0)) or 0)
            if qty <= 0.01:
                continue
            out.append({
                "source": "interco",
                "po_number": d.get("number", ""),   # kolom lama dipakai layar apa adanya
                "po_id": d.get("id", ""),
                "interco_id": d.get("id", ""),
                "interco_number": d.get("number", ""),
                "interco_status": d.get("status", ""),
                "from_entity_id": d.get("seller_entity_id", ""),
                "from_entity_name": d.get("seller_entity_name", ""),
                "source_order_id": d.get("source_order_id", ""),
                "source_order_number": d.get("source_order_number", ""),
                "qty": round(qty, 2),
                "eta": d.get("due_date") or d.get("doc_date") or "",
                "warehouse_id": "",
            })
    out.sort(key=lambda x: (x["eta"] or "9999-12-31"))
    return out


async def _incoming_supply(product_id: str, owner_entity_id: str) -> List[Dict[str, Any]]:
    """Seluruh pasokan yang sedang berjalan: PO supplier + pembelian internal antar-PT."""
    rows = [{**r, "source": r.get("source") or "po"}
            for r in await _open_po_incoming(product_id, owner_entity_id)]
    rows += await _open_interco_incoming(product_id, owner_entity_id)
    rows.sort(key=lambda x: (x["eta"] or "9999-12-31"))
    return rows


async def _pending_demand_lines(product_id: str, owner_entity_id: str) -> List[Dict[str, Any]]:
    """Baris backorder (Pending SO) aktif utk product×entitas → demand."""
    sos = await db.sales_orders.find(
        {"has_backorder": True, "entity_id": owner_entity_id,
         "status": {"$in": ACTIVE_BACKORDER_STATUSES},
         "backorders.product_id": product_id},
        {"_id": 0, "id": 1, "number": 1, "customer_name": 1, "customer_city": 1,
         "backorders": 1, "created_at": 1},
    ).sort("created_at", 1).to_list(500)
    out: List[Dict[str, Any]] = []
    for so in sos:
        for bo in so.get("backorders", []):
            if bo.get("product_id") != product_id:
                continue
            qty = float(bo.get("backorder_qty", 0) or 0)
            if qty <= 0.01 or bo.get("status") == "fulfilled":
                continue
            out.append({
                "order_id": so.get("id", ""), "order_number": so.get("number", ""),
                "customer_name": so.get("customer_name", ""),
                "customer_city": bo.get("customer_city") or so.get("customer_city", ""),
                "qty": round(qty, 2),
                "created_at": bo.get("created_at") or so.get("created_at", ""),
            })
    return out


def _match_supply(need: float, incoming: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Cocokkan demand `need` ke incoming (urut ETA) → coverage + promise_date (ETA
    saat kumulatif incoming menutupi need)."""
    total_incoming = round(sum(i["qty"] for i in incoming), 2)
    promise_date = ""
    cum = 0.0
    for i in incoming:
        cum += i["qty"]
        if cum + 0.01 >= need:
            promise_date = i["eta"]
            break
    if total_incoming + 0.01 >= need:
        coverage = "covered"            # incoming cukup menutupi
    elif total_incoming > 0.01:
        coverage = "partial"
    else:
        coverage = "uncovered"          # tak ada incoming → perlu PR/PO
    return {"coverage": coverage, "promise_date": promise_date,
            "incoming_total": total_incoming,
            "covered_qty": round(min(need, total_incoming), 2),
            "uncovered_qty": round(max(0.0, need - total_incoming), 2)}


async def atp_detail(scope: Dict[str, Any], product_id: str,
                     owner_entity_id: Optional[str] = None,
                     horizon_days: int = DEFAULT_ATP_HORIZON_DAYS) -> Dict[str, Any]:
    """Detail ATP future-aware untuk satu produk: available + incoming(horizon) −
    pending demand. Menyediakan breakdown supply (PO+ETA) & demand (Pending SO)."""
    q = dict(scope or {})
    q["product_id"] = product_id
    balances = await db.inventory_balances.find(q, {"_id": 0}).to_list(5000)
    available = round(sum(float(b.get("available_qty", 0) or 0) for b in balances), 2)
    reserved = round(sum(float(b.get("reserved_qty", 0) or 0) for b in balances), 2)
    owner = owner_entity_id
    if not owner:
        ent = q.get("owner_entity_id")
        owner = ent if isinstance(ent, str) else (balances[0].get("owner_entity_id") if balances else "")
    products = {p["id"]: p for p in await db.products.find({"id": product_id}, {"_id": 0}).to_list(2)}
    p = products.get(product_id, {})

    # E9.2 — ATP ikut menghitung pasokan dari PT sebelah (pembelian internal), bukan
    # hanya PO supplier. Tanpa ini barang yang sudah dijanjikan PT lain tampak tidak ada.
    incoming = await _incoming_supply(product_id, owner) if owner else []
    pending = await _pending_demand_lines(product_id, owner) if owner else []

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=max(1, int(horizon_days or DEFAULT_ATP_HORIZON_DAYS)))
    for i in incoming:
        eta_dt = _parse_dt(i["eta"])
        i["within_horizon"] = bool(eta_dt and eta_dt <= horizon)
    incoming_in_horizon = round(sum(i["qty"] for i in incoming if i.get("within_horizon")), 2)
    incoming_total = round(sum(i["qty"] for i in incoming), 2)
    pending_total = round(sum(pp["qty"] for pp in pending), 2)

    atp_now = round(available - pending_total, 2)
    atp_horizon = round(available + incoming_in_horizon - pending_total, 2)
    return {
        "product_id": product_id, "sku": p.get("sku", ""), "product_name": p.get("name", ""),
        "base_unit": p.get("base_unit", "meter"), "owner_entity_id": owner,
        "available": available, "reserved": reserved,
        "incoming": incoming, "incoming_in_horizon": incoming_in_horizon,
        "incoming_total": incoming_total,
        "pending_demand": pending, "pending_total": pending_total,
        "atp_now": atp_now, "atp_horizon": atp_horizon, "horizon_days": horizon_days,
    }


async def pending_so_board(scope: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Papan Pending SO: semua backorder aktif (ter-scope) + pencocokan ke incoming
    supply (PO+ETA) → coverage & promise_date. Reuse data backorder SO (tanpa koleksi baru)."""
    q = dict(scope or {})
    q["has_backorder"] = True
    q["status"] = {"$in": ACTIVE_BACKORDER_STATUSES}
    sos = await db.sales_orders.find(q, {
        "_id": 0, "id": 1, "number": 1, "customer_name": 1, "customer_city": 1,
        "entity_id": 1, "backorders": 1, "created_at": 1, "status": 1,
    }).sort("created_at", 1).to_list(2000)
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(2000)}
    entities = {e["id"]: e for e in await db.business_entities.find({}, {"_id": 0}).to_list(100)}
    # cache incoming per (product, entity) agar tak query berulang
    incoming_cache: Dict[str, List[Dict[str, Any]]] = {}
    rows: List[Dict[str, Any]] = []
    for so in sos:
        ent = so.get("entity_id", "")
        for bo in so.get("backorders", []):
            qty = float(bo.get("backorder_qty", 0) or 0)
            if qty <= 0.01 or bo.get("status") == "fulfilled":
                continue
            pid = bo.get("product_id")
            ck = f"{pid}|{ent}"
            if ck not in incoming_cache:
                incoming_cache[ck] = await _incoming_supply(pid, ent)
            match = _match_supply(qty, incoming_cache[ck])
            # E9.2 — sebutkan SIAPA yang menjanjikan: PO supplier atau PT sebelah.
            ic_rows = [i for i in incoming_cache[ck] if i.get("source") == "interco"]
            match["interco_promises"] = [{
                "interco_id": i.get("interco_id", ""),
                "interco_number": i.get("interco_number", ""),
                "from_entity_id": i.get("from_entity_id", ""),
                "from_entity_name": i.get("from_entity_name", ""),
                "qty": i.get("qty", 0), "eta": i.get("eta", ""),
                "status": i.get("interco_status", ""),
                "source_order_number": i.get("source_order_number", ""),
            } for i in ic_rows]
            match["interco_incoming"] = round(sum(float(i.get("qty") or 0) for i in ic_rows), 2)
            p = products.get(pid, {})
            e = entities.get(ent, {})
            rows.append({
                "backorder_id": bo.get("id", ""),
                "order_id": so.get("id", ""), "order_number": so.get("number", ""),
                "order_status": so.get("status", ""),
                "customer_name": so.get("customer_name", ""),
                "customer_city": bo.get("customer_city") or so.get("customer_city", ""),
                "product_id": pid, "sku": p.get("sku", "") or bo.get("sku", ""),
                "product_name": p.get("name", "") or bo.get("product_name", ""),
                "unit": p.get("base_unit", "meter"),
                "owner_entity_id": ent,
                "owner_entity_name": e.get("short_name") or e.get("legal_name", ent),
                "requested_qty": round(float(bo.get("requested_qty", 0) or 0), 2),
                "reserved_qty": round(float(bo.get("reserved_qty", 0) or 0), 2),
                "backorder_qty": round(qty, 2),
                "created_at": bo.get("created_at") or so.get("created_at", ""),
                **match,
            })
    # urut: uncovered dulu (paling berisiko), lalu partial, lalu covered; tertua dulu
    rank = {"uncovered": 0, "partial": 1, "covered": 2}
    rows.sort(key=lambda r: (rank.get(r["coverage"], 9), r.get("created_at", "")))
    return rows
