"""Inbound Receiving router: scan-based receiving with escalation."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, Body
from pymongo import ReturnDocument
from db import db
from services import dual_qty_service as _dual  # FASE U — dua satuan (roll + ukuran)
from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID
from schemas import POReceiveItem, GRCompletePayload
import domain_registry as _dr        # Fase A · R7 — SSOT enum/snapshot domain

router = APIRouter(prefix="/api")


@router.get("/inbound/tasks")
async def list_inbound_tasks(request: Request, status: str = None) -> List[Dict[str, Any]]:
    """List all inbound receiving tasks, optionally filtered by status."""
    await require_permission(request, "wms", "view")
    ctx = await entity_ctx(request)
    
    query = {"flow_type": "inbound", "source_type": "purchase_order"}
    if status:
        query["status"] = status
    query = resolve_list_scope("wms_tasks", query, ctx)
    
    tasks = await db.wms_tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    
    # Enrich with PO info
    po_ids = list(set(t.get("po_id") for t in tasks if t.get("po_id")))
    pos = {p["id"]: p for p in await db.purchase_orders.find({"id": {"$in": po_ids}}, {"_id": 0}).to_list(100)}
    
    for task in tasks:
        if task.get("po_id"):
            po = pos.get(task["po_id"], {})
            task["supplier_name"] = po.get("supplier_name", "")
    
    return tasks


@router.post("/inbound/tasks/{task_id}/scan-receive")
async def scan_receive_item(
    task_id: str,
    payload: POReceiveItem,
    request: Request
) -> Dict[str, Any]:
    """
    Scan and receive item for inbound task.
    
    Updates received_qty and tracks batch/lot/roll/bin.
    If received_qty reaches expected_qty, auto-advance to next stage.
    """
    actor = await require_permission(request, "wms", "update")
    
    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Inbound task tidak ditemukan")
    # INV-ENTITY-01 (KN-076-IDOR-WRITE-INBOUND P1): cegah mutasi task lintas-entitas.
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))
    
    if task.get("flow_type") != "inbound":
        raise HTTPException(status_code=400, detail="Task ini bukan inbound task")
    
    if task["status"] in ["completed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Task sudah selesai atau dibatalkan")
    
    # Validate product match
    if payload.product_id != task["product_id"]:
        raise HTTPException(status_code=400, detail="Product ID tidak sesuai dengan task")

    # ── FASE F-1 (F1-01/F1-02/F1-03) — qty boleh dalam SATUAN SUPPLIER ──────
    # Bila operator mengirim `doc_uom` + `doc_qty` (apa adanya dari surat jalan supplier),
    # server yang mengonversi ke satuan task memakai prioritas: satuan sama → barang
    # supplier (conv_factor) → registry konversi global. Jejak konversi WAJIB disimpan
    # (D-07). `preflight_scan` sekaligus menegakkan toleransi kedatangan Fase 3.
    from services import receiving_uom_service as _rus
    try:
        _pf = await _rus.preflight_scan(task, payload)
    except _rus.ReceivingUomError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    effective_qty, _ruom_trail = _pf["qty"], _pf["trail"]
    new_received_qty, expected_qty = _pf["new_received"], _pf["expected_qty"]
    tol_pct, variance_pct = _pf["tolerance_pct"], _pf["variance_pct"]
    within_tolerance = _pf["within_tolerance"]
    
    # Log scan entry
    scan_entry = {
        "id": new_id("scan"),
        "scan_type": "receive",
        "actual_qty": effective_qty,
        "batch": payload.batch,
        "lot": payload.lot,
        "roll_id": payload.roll_id,
        "bin_id": payload.bin_id,
        "actor": actor["name"],
        "timestamp": now_iso(),
        # FASE F-1 — jejak konversi satuan supplier (kosong bila input satuan KN)
        **({"uom_trail": _ruom_trail} if _ruom_trail else {}),
    }
    
    update_data = {
        "received_qty": new_received_qty,
        "receive_variance_percent": variance_pct,
        "receive_within_tolerance": within_tolerance,
        "receive_tolerance_percent": tol_pct,
        # FASE G-0 — bila kebijakan `receiving.block_over_remaining` dimatikan, penerimaan
        # melebihi PO TETAP diterima namun DITANDAI agar bisa ditindaklanjuti (bukan senyap).
        "over_receipt": bool(_pf.get("over_receipt")),
        "over_receipt_note": _pf.get("over_message", ""),
        "batch": payload.batch or task.get("batch", ""),
        "lot": payload.lot or task.get("lot", ""),
        "dye_lot": payload.dye_lot or task.get("dye_lot", ""),
        "grade": payload.grade or task.get("grade", ""),
        "roll_id": payload.roll_id or task.get("roll_id", ""),
        "bin_id": payload.bin_id or task.get("bin_id", ""),
        "updated_at": now_iso()
    }
    if _ruom_trail:
        # Satuan terakhir yang dipakai operator → dipakai UI untuk mengingat pilihan.
        update_data["last_receive_doc_uom"] = _ruom_trail["doc_uom"]
    
    # If received qty matches expected, auto-advance to receiving status
    if task["status"] == "waiting_goods" and new_received_qty > 0:
        update_data["status"] = "receiving"
    
    # If fully received, mark as ready for QC
    if new_received_qty >= expected_qty:
        update_data["status"] = "qc_check"
        update_data["quantity"] = new_received_qty  # Set final quantity
    
    _push: Dict[str, Any] = {"scan_log": scan_entry}
    if _ruom_trail:
        _push["receive_uom_trails"] = {**_ruom_trail, "scan_id": scan_entry["id"],
                                       "actor": actor["name"]}
    updated_task = await db.wms_tasks.find_one_and_update(
        {"id": task_id},
        {
            "$set": update_data,
            "$push": _push
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    
    await audit(actor["name"], "inbound_scan_receive", "wms_task", task_id, {
        "actual_qty": effective_qty,
        "received_qty": new_received_qty,
        "expected_qty": expected_qty,
        **({"doc_uom": _ruom_trail["doc_uom"], "doc_qty": _ruom_trail["doc_qty"],
            "uom_source": _ruom_trail["source"], "factor": _ruom_trail["factor"]}
           if _ruom_trail else {}),
    })
    
    return safe_doc(updated_task)


@router.post("/inbound/tasks/{task_id}/escalate")
async def escalate_inbound_task(
    task_id: str,
    request: Request,
    reason: str = "Qty tidak sesuai dengan PO"
) -> Dict[str, Any]:
    """
    Escalate inbound task to manager due to qty mismatch or other issues.
    
    Manager can then adjust expected_qty or investigate issue.
    """
    actor = await require_permission(request, "wms", "update")
    
    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Inbound task tidak ditemukan")
    # INV-ENTITY-01 (KN-076-IDOR-WRITE-INBOUND P1): cegah mutasi task lintas-entitas.
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))
    
    escalation = {
        "escalated_by": actor["name"],
        "escalated_at": now_iso(),
        "reason": reason,
        "status": "pending_review",
        "resolved_by": None,
        "resolved_at": None,
        "resolution_notes": ""
    }
    
    updated_task = await db.wms_tasks.find_one_and_update(
        {"id": task_id},
        {
            "$set": {
                "escalation": escalation,
                "status": "escalated",
                "updated_at": now_iso()
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    
    await audit(actor["name"], "inbound_escalated", "wms_task", task_id, {
        "reason": reason,
        "received_qty": task.get("received_qty", 0),
        "expected_qty": task.get("expected_qty", 0)
    })
    
    return safe_doc(updated_task)


@router.post("/inbound/tasks/{task_id}/resolve-escalation")
async def resolve_escalation(
    task_id: str,
    request: Request,
    adjusted_qty: float = None,
    resolution_notes: str = ""
) -> Dict[str, Any]:
    """
    Resolve escalated inbound task (manager only).
    
    Manager can adjust expected_qty to match actual received qty.
    """
    actor = await require_permission(request, "wms", "approve")  # Manager permission
    
    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Inbound task tidak ditemukan")
    # INV-ENTITY-01 (KN-076-IDOR-WRITE-INBOUND P1): cegah mutasi task lintas-entitas.
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))
    
    if not task.get("escalation"):
        raise HTTPException(status_code=400, detail="Task tidak dalam status escalation")
    
    escalation = task["escalation"]
    escalation["status"] = "resolved"
    escalation["resolved_by"] = actor["name"]
    escalation["resolved_at"] = now_iso()
    escalation["resolution_notes"] = resolution_notes
    
    update_data = {
        "escalation": escalation,
        "status": "qc_check",  # Move to QC after resolution
        "updated_at": now_iso()
    }
    
    # If manager adjusts qty, update expected and final quantity
    if adjusted_qty is not None:
        update_data["expected_qty"] = adjusted_qty
        update_data["quantity"] = task.get("received_qty", 0.0)
    
    updated_task = await db.wms_tasks.find_one_and_update(
        {"id": task_id},
        {"$set": update_data},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    
    await audit(actor["name"], "inbound_escalation_resolved", "wms_task", task_id, {
        "adjusted_qty": adjusted_qty,
        "resolution_notes": resolution_notes
    })
    
    return safe_doc(updated_task)


@router.post("/inbound/tasks/{task_id}/complete")
async def complete_inbound_receiving(
    task_id: str,
    request: Request,
    payload: Optional[GRCompletePayload] = Body(default=None),
) -> Dict[str, Any]:
    """
    Complete inbound receiving and update inventory.
    
    This moves task from qc_check → put_away → completed.
    Inventory is updated ONLY when status becomes 'completed'.

    P0-4 — body opsional `GRCompletePayload`: bila `rolls` diisi → buat multi-roll
    (panjang + dye_lot + grade per roll); bila kosong → satu roll dengan dye_lot/grade
    default (dari task/scan atau fallback lot/A). Pemanggilan TANPA body tetap jalan.
    """
    actor = await require_permission(request, "wms", "update")
    
    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Inbound task tidak ditemukan")
    # INV-ENTITY-01 (KN-076-IDOR-WRITE-INBOUND P1): cegah mutasi task lintas-entitas.
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))
    
    if task["status"] not in ["qc_check", "put_away"]:
        raise HTTPException(
            status_code=400,
            detail=f"Task harus dalam status qc_check atau put_away (current: {task['status']})"
        )
    
    # Check if qty is finalized
    final_qty = task.get("quantity", 0.0)
    if final_qty <= 0:
        # Fallback: if quantity wasn't explicitly set, use received_qty
        final_qty = task.get("received_qty", 0.0)
    if final_qty <= 0:
        raise HTTPException(status_code=400, detail="Quantity harus lebih dari 0 untuk complete")
    
    # Advance status — Depth #3a (QC Hold) menentukan tujuan barang.
    # Operator menekan "Selesaikan Penerimaan" → barang masuk inventory.
    # Sub-fase 1.6 — Roll-as-SSOT + Depth #3a — QC Hold/Quarantine.
    from services.roll_service import rebuild_balance
    from services.backorder_service import auto_fulfill_backorders
    from services.config_service import get_effective_settings

    # Owner entity diturunkan dari PO (default entitas utama)
    owner_entity_id = DEFAULT_ENTITY_ID
    po_doc = None
    if task.get("po_id"):
        po_doc = await db.purchase_orders.find_one({"id": task["po_id"]}, {"_id": 0})
        owner_entity_id = (po_doc or {}).get("entity_id") or DEFAULT_ENTITY_ID

    # Depth #3a — bila qc_on_receipt: barang masuk → roll `quarantine` (BUKAN available),
    # task → `qc_pending` (menunggu inspeksi QC). Bila non-aktif: legacy available+completed.
    qc_cfg = await get_effective_settings(owner_entity_id)
    qc_on_receipt = bool((qc_cfg.get("purchasing", {}) or {}).get("qc_on_receipt", True))
    roll_status = "quarantine" if qc_on_receipt else "available"
    next_stage = "qc_pending" if qc_on_receipt else "completed"

    # Buat roll + update PO untuk kedua jalur (available langsung / karantina)
    _uom_trail: Dict[str, Any] = {}
    _variance: Dict[str, Any] = {}
    if next_stage in ("completed", "qc_pending"):

        lot = task.get("lot") or f"LOT-{task.get('po_number', task_id)}"
        # P0-4 — dye_lot & grade aktual (default backward-compatible: dye_lot=lot, grade=A)
        default_dye_lot = (payload.dye_lot if payload else "") or task.get("dye_lot") or lot
        default_grade = (payload.grade if payload else "") or task.get("grade") or "A"

        # Fase 8 (Catch-weight) — roll length dlm BASE unit (meter) + weight_kg AKTUAL.
        product_doc = safe_doc(await db.products.find_one({"id": task["product_id"]}, {"_id": 0})) or {}
        gr_base_unit = product_doc.get("base_unit", "meter")
        gr_task_unit = task.get("unit", "meter")
        from services.uom_service import load_fixed_factors, resolve_roll_measures
        _factors = await load_fixed_factors()
        _is_weight_task = (gr_task_unit or "").strip().lower() == "kg"

        # P0-4 + Fase 8 — payload.rolls → MULTI roll (panjang m + berat kg + dye_lot/grade per roll).
        # Validasi Σ kontribusi (task_qty) ≈ qty diterima (SATUAN task). Bila kosong → satu roll.
        roll_specs: List[Dict[str, Any]] = []
        if payload and payload.rolls:
            measures = [resolve_roll_measures(product_doc, gr_task_unit,
                                              float(r.length or 0), float(r.weight or 0), _factors)
                        for r in payload.rolls]
            total_task = round(sum(m["task_qty"] for m in measures), 2)
            if total_task <= 0:
                raise HTTPException(status_code=400, detail="Total ukuran roll harus lebih dari 0.")
            tol_line = max(0.5, round(final_qty * 0.02, 2))
            if abs(total_task - final_qty) > tol_line:
                raise HTTPException(
                    status_code=400,
                    detail=(f"Total roll ({total_task:g} {gr_task_unit}) tidak cocok dengan qty diterima "
                            f"({final_qty:g} {gr_task_unit}, toleransi ±{tol_line:g})."))
            for r, m in zip(payload.rolls, measures):
                roll_specs.append({
                    "length_base": m["length_base"],
                    "weight_kg": m["weight_kg"],
                    "dye_lot": (r.dye_lot or default_dye_lot),
                    "grade": (r.grade or default_grade),
                    "defects": list(r.defects or []),
                })
        else:
            m = resolve_roll_measures(
                product_doc, gr_task_unit,
                0.0 if _is_weight_task else final_qty,   # length_in (m) utk PO per-panjang
                final_qty if _is_weight_task else 0.0,   # weight_in (kg) utk PO per-berat
                _factors)
            roll_specs.append({
                "length_base": m["length_base"],
                "weight_kg": m["weight_kg"],
                "dye_lot": default_dye_lot,
                "grade": default_grade,
                "defects": [],
            })

        # ── FASE B (D-06/D-07) — jejak konversi + toleransi selisih timbang/ukur ──
        # Bila panjang (base) DAN berat (kg) aktual sama-sama ada, sistem membandingkan
        # berat AKTUAL vs berat hasil konversi (GSM × lebar). Selisih di atas toleransi
        # → peringatan (needs_review) atau DITOLAK (block) sesuai pengaturan user.
        from services import uom_rules_service as _uomr
        # FASE E-4 (E4.5) — toleransi mengikuti badan usaha PEMILIK tugas penerimaan,
        # bukan satu angka untuk seluruh grup.
        _uom_settings = await _uomr.get_settings(str(task.get("entity_id") or ""))
        _sum_len_base = round(sum(s["length_base"] for s in roll_specs), 4)
        _sum_weight = round(sum(s.get("weight_kg") or 0 for s in roll_specs), 4)
        try:
            _uom_trail = await _uomr.convert_with_trail(
                product_doc, final_qty, gr_task_unit, gr_base_unit, context="goods_receipt")
        except _uomr.UomRuleError:
            _uom_trail = {"doc_uom": gr_task_unit, "doc_qty": final_qty,
                          "base_uom": gr_base_unit, "base_qty": _sum_len_base,
                          "factor": None, "source": "unresolved", "rule_id": "",
                          "context": "goods_receipt", "converted_at": now_iso()}
        if _sum_len_base > 0 and _sum_weight > 0:
            try:
                _wt = await _uomr.convert_with_trail(
                    product_doc, _sum_len_base, gr_base_unit, "kg", context="goods_receipt_weight")
                _variance = await _uomr.check_variance(
                    _wt["base_qty"], _sum_weight, _uom_settings,
                    label=f"berat hasil konversi ({_wt['base_qty']:g} kg)")
                _variance["expected_kg"] = _wt["base_qty"]
                _variance["actual_kg"] = _sum_weight
                _variance["factor"] = _wt.get("factor")
            except _uomr.UomRuleError:
                _variance = {}
        _ovr = (getattr(payload, "variance_override_reason", "") or "").strip() if payload else ""
        if _variance.get("level") == "block":
            if not (bool(_uom_settings.get("allow_override")) and _ovr):
                raise HTTPException(status_code=400, detail=(
                    f"{_variance['message']} Perbaiki data, atau lanjutkan dengan mengisi "
                    "alasan override (butuh izin & tercatat di audit)."))
            _variance["override_reason"] = _ovr
            _variance["overridden"] = True

        # P0-5 — base HPP roll dari harga PO saat GR (per BASE unit). Landed cost
        # (Fase 5.4) menambah di atas base ini. Fallback: harga_pokok produk.
        _po_doc = None
        if task.get("po_id"):
            _po_doc = safe_doc(await db.purchase_orders.find_one({"id": task["po_id"]}, {"_id": 0}))
        _po_unit_price = 0.0
        if _po_doc:
            for _it in _po_doc.get("items", []):
                if _it.get("product_id") == task["product_id"]:
                    _po_unit_price = float(_it.get("price", 0) or 0)
                    break
        if _po_unit_price <= 0:
            _po_unit_price = float(product_doc.get("harga_pokok", 0) or 0)
        _total_base = round(sum(s["length_base"] for s in roll_specs), 4)
        if _po_unit_price > 0 and _total_base > 0:
            # total cost (task unit × harga) dibagi total base qty → HPP per base unit
            base_unit_cost = round((final_qty * _po_unit_price) / _total_base, 4)
        else:
            base_unit_cost = None

        # ── FASE C (D-10/D-26/D-27) — LOT kelas satu per batch penerimaan ──────
        # Granularitas D-10: 1 batch penerimaan × 1 dye lot = 1 dokumen `inventory_lots`
        # (satu lot menaungi banyak roll). Idempoten: menyelesaikan GR yang sama tidak
        # membuat lot ganda. Mode penegakan default `warn` → TIDAK memblokir gudang.
        from services import lot_service as _lots
        # FASE E-4 (E4.5) — ketatnya nomor lot juga per badan usaha.
        _lot_settings = await _lots.get_settings(str(task.get("entity_id") or ""))
        _supplier_lot = ((payload.supplier_lot if payload else "") or
                         task.get("supplier_lot") or "").strip()
        _shade_ref = ((payload.shade_ref if payload else "") or "").strip()
        _lot_warnings: List[str] = []
        _distinct_dye = list(dict.fromkeys(s["dye_lot"] for s in roll_specs))
        _lot_by_dye: Dict[str, Dict[str, Any]] = {}
        for _dl in _distinct_dye:
            try:
                _lot_warnings.extend(await _lots.guard_capture(_supplier_lot, _dl, _lot_settings))
            except _lots.LotError as exc:
                # D-27 mode `block`: tolak dengan pesan yang bisa ditindak petugas gudang
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            _lot_by_dye[_dl] = await _lots.resolve_or_create(
                product_id=task["product_id"], owner_entity_id=owner_entity_id,
                warehouse_id=task["warehouse_id"],
                lot_code=((payload.lot_number if payload else "") or
                          (task.get("lot") or "") if len(_distinct_dye) == 1 else ""),
                source="receiving",
                source_ref={"type": "wms_task", "id": task_id,
                            "number": task.get("po_number", "")},
                supplier_lot=_supplier_lot, dye_lot=_dl,
                supplier_id=(po_doc or {}).get("supplier_id", ""),
                supplier_name=((po_doc or {}).get("supplier_name", "") or
                               task.get("supplier_name", "")),
                status=(_lot_settings.get("status_on_receipt", "karantina")
                        if qc_on_receipt else "released"),
                actor=actor.get("name", "System"))
        if _shade_ref:
            for _lt in _lot_by_dye.values():
                await _lots.patch_lot(_lt["id"], {"shade_ref": _shade_ref},
                                      actor.get("name", "System"))
        _lot_warnings = list(dict.fromkeys(_lot_warnings))

        # INV-ROLL-01 — nomor dari sequence atomik bersama (dulu `count_documents()+1`,
        # yang menabrak nomor lama begitu ada roll di-consume/dihapus atau ber-prefix lain).
        from services.roll_service import next_roll_no as _next_roll_no
        is_multi = len(roll_specs) > 1
        for spec in roll_specs:
            spec_len = spec["length_base"]
            _lot_doc = _lot_by_dye.get(spec["dye_lot"]) or {}
            roll_doc = {
                "id": new_id("roll"),
                "product_id": task["product_id"],
                "owner_entity_id": owner_entity_id,
                "ownership_type": "internal",
                "consignor_ref": None,
                "warehouse_id": task["warehouse_id"],
                "bin_id": task.get("bin_id") or None,
                "lot": _lot_doc.get("lot_number") or lot,
                "lot_id": _lot_doc.get("id") or "",
                "supplier_lot": _supplier_lot,
                "dye_lot": spec["dye_lot"],
                "batch": task.get("batch") or (lot.replace("LOT", "BATCH") if lot else ""),
                "roll_no": await _next_roll_no(),
                "length_initial": spec_len,
                "length_remaining": spec_len,
                "unit": gr_base_unit,
                "weight_kg": spec.get("weight_kg", 0.0),   # Fase 8 — catch-weight aktual roll
                "weight_unit": "kg",
                # FASE U (U6) — roll ber-yard yang JUGA ditimbang menyimpan ukuran kedua
                # di field yang sudah ada tapi belum pernah diisi. Kartu roll menampilkan
                # keduanya; tidak ada field kembar yang perlu disinkronkan.
                "secondary_measures": ({"kg": round(float(spec.get("weight_kg") or 0), 3)}
                                       if float(spec.get("weight_kg") or 0) > 0 else None),
                "grade": spec["grade"],
                "defects": spec["defects"],
                # Fase A · PS-02 — snapshot domain produk (INV-DOMAIN-05)
                **_dr.roll_domain_snapshot(product_doc),
                "status": roll_status,
                "qc_task_id": task_id if qc_on_receipt else None,
                "tracking_mode": "barcode",
                "earmarked_for": None,
                "location_type": "warehouse_bin",
                "reserved_ref": None,
                "unit_cost": base_unit_cost,
                "base_unit_cost": base_unit_cost,
                "landed_cost_total": 0.0,
                "landed_cost_refs": [],
                "acquired": {"via": "inbound", "ref_id": task.get("po_id") or task_id, "date": now_iso()},
                # ── Traceability asal barang (denormalisasi, S#2026-07-21) ──────
                "supplier_id": (_po_doc or {}).get("supplier_id", ""),
                "supplier_name": (_po_doc or {}).get("supplier_name", "") or task.get("supplier_name", ""),
                "po_id": task.get("po_id") or "",
                "po_number": task.get("po_number", ""),
                "grn_task_id": task_id,
                "received_date": now_iso(),
                "vendor_bill_id": "",          # diisi saat Vendor Bill di-posting
                "supplier_invoice_no": "",     # diisi saat Vendor Bill di-posting
                "rfid_tag_id": (task.get("roll_id") or None) if not is_multi else None,
                "is_remnant": False,
                "created_at": now_iso(), "updated_at": now_iso(),
                "created_by": actor.get("id") or "system", "created_by_name": actor["name"],
            }
            await db.inventory_rolls.insert_one(dict(roll_doc))

            # Log movement (owner-scoped, link roll)
            await db.inventory_movements.insert_one({
                "id": new_id("mov"),
                "product_id": task["product_id"],
                "warehouse_id": task["warehouse_id"],
                "owner_entity_id": owner_entity_id,
                "movement_type": "inbound_receiving",
                "quantity": spec_len,
                "unit": gr_base_unit,
                # FASE U — satu baris mutasi = SATU roll fisik. Dicatat eksplisit supaya
                # kartu stok bisa menyebut dua satuan tanpa menghitung ulang dari mana pun.
                "qty_rolls": 1,
                "weight_kg": spec.get("weight_kg", 0.0),   # Fase 8 — catch-weight
                "batch": task.get("batch", ""),
                "lot": _lot_doc.get("lot_number") or lot,
                "lot_id": _lot_doc.get("id") or "",
                "roll_id": roll_doc["id"],
                "source_document": f"PO_{task.get('po_number', '')}",
                "timestamp": now_iso()
            })

        # FASE U — jumlah roll yang BENAR-BENAR dibuat (bukan diketik ulang petugas):
        # tersimpan di tugas penerimaan, lalu diakumulasi ke baris PO sebagai turunan.
        # `$inc` TIDAK dipakai di sini: `qty_rolls` sengaja lahir `None` ("belum ada roll
        # yang diterima" ≠ "0 roll"), dan `$inc` pada `None` ditolak MongoDB. Jadi nilai
        # sebelumnya dibaca lalu ditulis — tetap akumulatif untuk penerimaan bertahap.
        _rolls_made = len(roll_specs)
        _fresh = await db.wms_tasks.find_one({"id": task_id}, {"_id": 0, "qty_rolls": 1}) or {}
        await db.wms_tasks.update_one(
            {"id": task_id},
            {"$set": {"qty_rolls": int(_fresh.get("qty_rolls") or 0) + _rolls_made,
                      "updated_at": now_iso()}})

        # Update PO item received_qty (akumulatif) + status
        if task.get("po_id"):
            await db.purchase_orders.update_one(
                {
                    "id": task["po_id"],
                    "items.product_id": task["product_id"]
                },
                {
                    "$inc": {"items.$.received_qty": final_qty},
                    "$set": {
                        "status": "receiving",
                        "last_received_at": now_iso(),
                        "updated_at": now_iso()
                    }
                }
            )
            # FASE U — "berapa roll sudah diterima" = TURUNAN dari roll yang lahir.
            # Ditulis dengan $set (bukan $inc) karena nilai awalnya `None` — lihat alasan
            # di atas. Papan PO & layar PO memakainya tanpa menghitung ulang.
            _po_fresh = await db.purchase_orders.find_one(
                {"id": task["po_id"]}, {"_id": 0, "items": 1}) or {}
            for _ix, _it in enumerate(_po_fresh.get("items", [])):
                if _it.get("product_id") == task["product_id"]:
                    await db.purchase_orders.update_one(
                        {"id": task["po_id"]},
                        {"$set": {f"items.{_ix}.received_rolls":
                                  int(_it.get("received_rolls") or 0) + _rolls_made}})
                    break

            # Depth 1A — hitung ulang status PO (partial/completed) dari received_qty
            from routers.purchase_orders import recompute_po_status
            await recompute_po_status(task["po_id"])

        # Rebuild proyeksi balance segmen (jaga invarian balance == Σ rolls)
        await rebuild_balance(task["product_id"], task["warehouse_id"], owner_entity_id)

        # Gelombang 1 F-3 — GR → GL: Dr Persediaan / Cr GR-IR (best-effort, idempotent per task).
        _gr_value = round(final_qty * _po_unit_price, 2) if _po_unit_price > 0 else 0.0
        if _gr_value > 0:
            try:
                from services import gl_service
                await gl_service.post_goods_receipt(
                    task_id=task_id, entity_id=owner_entity_id, amount=_gr_value,
                    label=task.get("po_number", "") or task_id)
            except Exception as exc:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).error("Gagal posting GL GR task %s: %s", task_id, exc)

        # AUTO-FULFILL backorder hanya bila stok LANGSUNG available (QC non-aktif).
        # Bila qc_on_receipt: barang di karantina → tunggu keputusan QC accept (qc_service).
        if not qc_on_receipt:
            await auto_fulfill_backorders(task["product_id"], owner_entity_id)

        # FASE C — hitung ulang agregat lot (turunan roll, bukan $inc) + simpan jejak
        # lot pada tugas GR agar layar penerimaan & QC bisa menampilkannya.
        await _lots.recompute_many([l["id"] for l in _lot_by_dye.values()])
        _lot_summary = [{"id": l["id"], "lot_number": l["lot_number"],
                         "dye_lot": l.get("dye_lot", "")} for l in _lot_by_dye.values()]
        await db.wms_tasks.update_one({"id": task_id}, {"$set": {
            "lot_ids": [l["id"] for l in _lot_by_dye.values()],
            "lot_numbers": [l["lot_number"] for l in _lot_by_dye.values()],
            "supplier_lot": _supplier_lot,
            "lot_warnings": _lot_warnings,
            "updated_at": now_iso()}})
    
    updated_task = await db.wms_tasks.find_one_and_update(
        {"id": task_id},
        {"$set": {
            "status": next_stage,
            "updated_at": now_iso(),
            # FASE B (D-07) — jejak konversi + hasil cek toleransi tersimpan di tugas GR
            **({"uom_trail": _uom_trail} if _uom_trail else {}),
            **({"conversion_variance": _variance,
                "needs_review": _variance.get("level") in ("warn", "block")}
               if _variance else {}),
            **({"qc_status": "pending", "quarantine_qty": final_qty} if qc_on_receipt else {}),
        }},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    
    await audit(actor["name"], "inbound_completed", "wms_task", task_id, {
        "final_qty": final_qty,
        "status": next_stage,
        "uom_trail": _uom_trail or None,
        "conversion_variance": _variance or None,
    })
    if _variance.get("level") in ("warn", "block"):
        await audit(actor["name"], "uom_variance_flagged", "wms_task", task_id, _variance,
                    "Fase B — selisih konversi vs timbang/ukur aktual di luar toleransi")

    # PS-21 — notifikasi "barang PO datang" SEKETIKA (job po_arrival = jaring pengaman;
    # dedupe harian mencegah pesan dobel). Best-effort: tidak boleh menggagalkan GR.
    try:
        from services import alert_ops_service as _ops
        await _ops.notify_po_arrival({**(updated_task or {}), "received_qty": final_qty})
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("PS-21 notifikasi po_arrival gagal: %s", exc)

    out = safe_doc(updated_task) or {}
    # FASE C — kembalikan lot yang terbentuk + peringatan kelengkapan (mode `warn`)
    if next_stage in ("completed", "qc_pending"):
        out["lots"] = _lot_summary
        out["lot_warnings"] = _lot_warnings
    return out
