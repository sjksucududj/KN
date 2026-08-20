"""Depth #3a — QC Hold / Quarantine saat Goods Receipt.

Alur: barang masuk (GR) → roll `quarantine` (BUKAN langsung available) → inspektur
QC memutuskan per task:
  - ACCEPT (qty): quarantine → available, lalu auto-fulfill backorder.
  - REJECT (qty): pilih disposisi
      • "damaged"  → quarantine → `damaged` (tetap di gudang, tercatat)
      • "return"   → quarantine → `returned_supplier` (keluar on_hand) + buat
                      Purchase Return / Nota Debit (stock_adjusted=True) ke supplier.

SSOT-safe (KN_15 §3.4): semua transisi di LEVEL ROLL (split bila parsial); balance
di-rebuild dari rolls sehingga invarian `on_hand == Σ bucket` & `balance == Σ rolls`
tetap utuh. TIDAK pernah $inc balance langsung.
"""
from typing import Any, Dict, List, Optional
from db import db
from core_utils import now_iso, new_id, DEFAULT_ENTITY_ID, safe_doc
from services.roll_service import rebuild_balance, insert_child_roll

RETURNED_STATUS = "returned_supplier"  # terminal — tidak masuk bucket fisik manapun


async def get_quarantine_rolls(task_id: str) -> List[Dict[str, Any]]:
    return await db.inventory_rolls.find(
        {"qc_task_id": task_id, "status": "quarantine", "length_remaining": {"$gt": 0}},
        {"_id": 0},
    ).to_list(1000)


async def quarantine_qty_for_task(task_id: str) -> float:
    rolls = await get_quarantine_rolls(task_id)
    return round(sum(float(r.get("length_remaining", 0) or 0) for r in rolls), 2)


async def _consume_quarantine(
    qrolls: List[Dict[str, Any]], qty: float, target_status: str,
    owner: str, ref: Dict[str, Any], mov_type: str, extra_set: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Pindahkan `qty` dari roll quarantine (in-place list) → `target_status`.
    Split roll bila parsial. Catat movement. Return {moved_qty, rolls:[...]}."""
    remaining = round(float(qty), 2)
    moved_rolls: List[Dict[str, Any]] = []
    for roll in qrolls:
        if remaining <= 0.01:
            break
        rlen = float(roll.get("length_remaining", 0) or 0)
        if rlen <= 0.01:
            continue
        take = round(min(rlen, remaining), 2)
        set_doc = {"status": target_status, "updated_at": now_iso()}
        if extra_set:
            set_doc.update(extra_set)
        if take >= rlen - 0.01:
            # seluruh roll bertransisi
            await db.inventory_rolls.update_one({"id": roll["id"]}, {"$set": set_doc})
            roll["length_remaining"] = 0.0
            moved_id, moved_len = roll["id"], rlen
        else:
            # parsial → kurangi parent (tetap quarantine), buat child target_status
            await db.inventory_rolls.update_one(
                {"id": roll["id"]},
                {"$set": {"length_remaining": round(rlen - take, 2),
                          "length_initial": round(float(roll["length_initial"]) - take, 2),
                          "updated_at": now_iso()}},
            )
            child = dict(roll)
            child.pop("_id", None)
            child.update({
                "id": new_id("roll"),
                "length_initial": round(take, 2),
                "length_remaining": round(take, 2),
                "is_remnant": False,
                "created_at": now_iso(), "updated_at": now_iso(),
                **set_doc,
            })
            child = await insert_child_roll(child, roll)
            roll["length_remaining"] = round(rlen - take, 2)
            moved_id, moved_len = child["id"], take
        await db.inventory_movements.insert_one({
            "id": new_id("mov"),
            "product_id": roll["product_id"],
            "warehouse_id": roll["warehouse_id"],
            "owner_entity_id": owner,
            "movement_type": mov_type,
            "quantity": round(moved_len, 2),
            "unit": roll.get("unit", "meter"),
            "lot": roll.get("lot", ""),
            "roll_id": moved_id,
            # FASE U — satu baris mutasi menunjuk SATU roll fisik.
            "qty_rolls": (1 if moved_id else None),
            "ref_type": ref.get("type"),
            "ref_id": ref.get("id"),
            "source_document": ref.get("doc", ""),
            "timestamp": now_iso(),
        })
        moved_rolls.append({"roll_id": moved_id, "lot": roll.get("lot", ""), "length": round(moved_len, 2)})
        remaining = round(remaining - take, 2)
    return {"moved_qty": round(qty - max(remaining, 0.0), 2), "rolls": moved_rolls}


async def _next_return_number() -> str:
    from services.purchase_return_service import next_return_number
    return await next_return_number()


async def _create_qc_return(task: Dict[str, Any], po: Optional[Dict[str, Any]], qty: float,
                            reason: str, created_by: str) -> Dict[str, Any]:
    """Buat dokumen Purchase Return (Nota Debit) untuk barang QC-reject yang
    dikembalikan ke supplier. stock_adjusted=True karena roll SUDAH dipindah
    ke returned_supplier oleh QC (approval hanya menerbitkan DN + kurangi AP)."""
    product = safe_doc(await db.products.find_one({"id": task["product_id"]}, {"_id": 0})) or {}
    price = 0.0
    if po:
        for it in po.get("items", []):
            if it.get("product_id") == task["product_id"]:
                price = float(it.get("price", 0) or 0)
                break
    if price <= 0:
        price = float(product.get("price", 0) or 0)
    subtotal = round(price * qty, 2)
    number = await _next_return_number()
    now = now_iso()
    doc = {
        "id": new_id("pret"), "number": number,
        "supplier_id": (po or {}).get("supplier_id", ""),
        "supplier_name": (po or {}).get("supplier_name", ""),
        "po_id": (po or {}).get("id", task.get("po_id")),
        "po_number": (po or {}).get("po_number", task.get("po_number", "")),
        "warehouse_id": task["warehouse_id"],
        "warehouse_name": task.get("warehouse_name", ""),
        "entity_id": (po or {}).get("entity_id", DEFAULT_ENTITY_ID),
        "items": [{
            "product_id": task["product_id"], "sku": product.get("sku", ""),
            "product_name": product.get("name", task.get("product_name", "")),
            "quantity": round(qty, 2), "unit": task.get("unit", product.get("base_unit", "meter")),
            "price": price, "subtotal": subtotal,
            "reason": reason or "QC reject", "condition": "rejected_qc",
        }],
        "total_amount": subtotal,
        "reason": reason or "Ditolak saat inspeksi QC penerimaan",
        "notes": f"Auto dari QC penerimaan task {task['id']}",
        "source": "qc_reject",
        "status": "pending_approval", "stock_adjusted": True,
        "debit_note_number": "",
        "created_by": created_by, "approved_by": None, "approved_at": None,
        "rejected_by": None, "rejected_at": None, "reject_reason": None,
        "created_at": now, "updated_at": now,
    }
    await db.purchase_returns.insert_one(dict(doc))
    from services import doc_refs_service as _refs
    if doc.get("po_id"):
        await _refs.safe_link(("purchase_return", doc["id"]), ("purchase_order", doc["po_id"]),
                              "reverses", note="retur hasil penolakan QC")
    return safe_doc(doc)


async def process_qc_decision(
    task: Dict[str, Any], accept_qty: float, reject_qty: float,
    reject_disposition: str, reason: str, actor: Dict[str, Any],
    accept_grade: str = "A", defects: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Proses keputusan QC untuk 1 inbound task. Lihat docstring modul.

    P0-4 — `accept_grade` & `defects` ditanam ke roll yang lolos (available)
    sebagai grade aktual hasil inspeksi tekstil."""
    task_id = task["id"]
    product_id = task["product_id"]
    warehouse_id = task["warehouse_id"]

    po = None
    owner = DEFAULT_ENTITY_ID
    if task.get("po_id"):
        po = safe_doc(await db.purchase_orders.find_one({"id": task["po_id"]}, {"_id": 0}))
        owner = (po or {}).get("entity_id") or DEFAULT_ENTITY_ID

    # Fase A · PS-09/D-01 — grade hasil inspeksi WAJIB nilai enum resmi (A|A1|A2|B|BS).
    from services import grade_service
    accept_grade = grade_service.normalize_or_raise(accept_grade or "A", "Grade diterima")

    qrolls = await get_quarantine_rolls(task_id)
    total_q = round(sum(float(r.get("length_remaining", 0) or 0) for r in qrolls), 2)
    if total_q <= 0.01:
        raise ValueError("Tidak ada stok karantina untuk task ini.")

    accept_qty = round(float(accept_qty or 0), 2)
    reject_qty = round(float(reject_qty or 0), 2)
    if accept_qty < 0 or reject_qty < 0:
        raise ValueError("Qty tidak boleh negatif.")
    if accept_qty + reject_qty <= 0.01:
        raise ValueError("Tentukan qty terima dan/atau tolak.")
    if accept_qty + reject_qty > total_q + 0.05:
        raise ValueError(
            f"Total terima+tolak ({round(accept_qty + reject_qty, 2)}) melebihi qty karantina ({total_q}).")
    if reject_qty > 0.01 and reject_disposition not in ("damaged", "return"):
        raise ValueError("Disposisi reject harus 'damaged' atau 'return'.")

    doc_ref = task.get("po_number") or task_id
    result: Dict[str, Any] = {
        "task_id": task_id, "product_id": product_id, "warehouse_id": warehouse_id,
        "accepted_qty": 0.0, "rejected_qty": 0.0,
        "reject_disposition": reject_disposition if reject_qty > 0.01 else None,
        "purchase_return": None,
    }

    # Snapshot grade sebelum konsumsi (untuk riwayat before → after, PS-09).
    _grade_before = {r["id"]: (r.get("grade") or "") for r in qrolls if r.get("id")}

    # 1) ACCEPT → available
    if accept_qty > 0.01:
        acc = await _consume_quarantine(
            qrolls, accept_qty, "available", owner,
            {"type": "qc_inspection", "id": task_id, "doc": doc_ref},
            mov_type="qc_accept",
            extra_set={"qc_task_id": None, "qc_passed_at": now_iso(),
                       "grade": accept_grade, "qc_grade": accept_grade,
                       "grade_source": "qc_inspection", "grade_updated_at": now_iso(),
                       "defects": list(defects or [])},
        )
        result["accepted_qty"] = acc["moved_qty"]
        result["accept_grade"] = accept_grade
        # PS-09 — jejak perubahan grade per roll yang lolos QC (before → after).
        for _r in acc.get("rolls", []) or []:
            _rid = _r.get("roll_id") or ""
            _before = _grade_before.get(_rid, "")
            if not _rid or _before == accept_grade:
                continue
            await db.inventory_rolls.update_one(
                {"id": _rid},
                {"$push": {"grade_history": grade_service.history_entry(
                    _before, accept_grade, "qc_inspection",
                    f"Keputusan QC {doc_ref}: diterima {acc['moved_qty']}",
                    actor, {"lot": _r.get("lot", "")})}})

    # 2) REJECT → damaged | returned_supplier (+ Nota Debit)
    if reject_qty > 0.01:
        if reject_disposition == "damaged":
            rej = await _consume_quarantine(
                qrolls, reject_qty, "damaged", owner,
                {"type": "qc_inspection", "id": task_id, "doc": doc_ref},
                mov_type="qc_reject_damaged",
                extra_set={"qc_task_id": None, "qc_rejected_at": now_iso(),
                           "reject_reason": reason or "QC reject"},
            )
            result["rejected_qty"] = rej["moved_qty"]
        else:  # return
            pret = await _create_qc_return(task, po, reject_qty, reason, actor.get("name", "system"))
            rej = await _consume_quarantine(
                qrolls, reject_qty, RETURNED_STATUS, owner,
                {"type": "purchase_return", "id": pret["id"], "doc": pret["number"]},
                mov_type="qc_reject_return",
                extra_set={"qc_task_id": None, "qc_rejected_at": now_iso(),
                           "returned_ref": {"type": "purchase_return", "id": pret["id"]},
                           "reject_reason": reason or "QC reject"},
            )
            result["rejected_qty"] = rej["moved_qty"]
            result["purchase_return"] = {"id": pret["id"], "number": pret["number"],
                                         "supplier_name": pret.get("supplier_name", "")}

    # 3) Rebuild balance segmen terdampak
    await rebuild_balance(product_id, warehouse_id, owner)

    # 4) Auto-fulfill backorder bila ada stok baru available
    if result["accepted_qty"] > 0.01:
        from services.backorder_service import auto_fulfill_backorders
        await auto_fulfill_backorders(product_id, owner)

    # 5) Update task — status + jejak QC
    if result["accepted_qty"] > 0.01:
        new_status = "completed"
    else:
        new_status = "qc_rejected"
    qc_result = ("passed" if result["rejected_qty"] <= 0.01
                 else ("rejected" if result["accepted_qty"] <= 0.01 else "partial"))
    await db.wms_tasks.update_one({"id": task_id}, {"$set": {
        "status": new_status,
        "qc_status": qc_result,
        "qc_accept_qty": result["accepted_qty"],
        "qc_reject_qty": result["rejected_qty"],
        "qc_reject_disposition": result["reject_disposition"],
        "qc_reason": reason or "",
        "qc_by": actor.get("name", "system"),
        "qc_at": now_iso(),
        "updated_at": now_iso(),
    }})

    result["task_status"] = new_status
    result["qc_status"] = qc_result
    return result
