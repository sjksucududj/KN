"""QC 4-Point Inspection service — Fase 6.2 (P1).

Inspeksi objektif per-roll saat QC (task qc_pending): hitung total poin defect
(metode 4-point sederhana) → tentukan Grade (A/B/C) via ambang configurable, dan
catat GSM & lebar AKTUAL per roll.

Keputusan desain owner:
  - Skor: TOTAL poin defect saja (Σ point_value × count) — tanpa normalisasi per luas.
  - Grade (Fase A · D-01): poin ≤ a_max → A, ≤ a1_max → A1, ≤ a2_max → A2,
    ≤ b_max → B, > b_max → BS. Ambang dari Settings `qc.grade_thresholds`;
    konfigurasi lama (hanya a_max & b_max) di-interpolasi agar batas A & B TIDAK berubah.
  - GSM/Lebar aktual: dicatat saja (tanpa pass/fail otomatis).
  - Hasil: set `roll.grade` dari inspeksi (tanpa aksi karantina otomatis).
"""
from typing import Any, Dict, List, Optional
from db import db
from core_utils import now_iso, safe_doc
from services.config_service import get_effective_settings

VALID_POINTS = {1, 2, 3, 4}


async def grade_thresholds(entity_id: Optional[str] = None) -> Dict[str, float]:
    """Ambang poin → grade (5 tingkat, D-01).

    Backward-compatible: bila Settings hanya berisi `a_max` & `b_max` (skema lama
    A/B/C), ambang A1 & A2 di-interpolasi merata di antara keduanya sehingga batas
    grade A dan grade B TETAP sama seperti sebelumnya.
    """
    settings = await get_effective_settings(entity_id)
    qc = settings.get("qc", {}) or {}
    th = qc.get("grade_thresholds", {}) or {}
    a_max = float(th.get("a_max", 20.0) or 20.0)
    b_max = float(th.get("b_max", 40.0) or 40.0)
    span = max(b_max - a_max, 0.0)
    a1_max = float(th.get("a1_max") or (a_max + span / 3.0))
    a2_max = float(th.get("a2_max") or (a_max + 2.0 * span / 3.0))
    return {"a_max": a_max, "a1_max": round(a1_max, 2), "a2_max": round(a2_max, 2),
            "b_max": b_max}


def compute_points(defects: List[Dict[str, Any]]) -> float:
    """Total poin = Σ (point_value × count). point_value harus 1..4."""
    total = 0.0
    for d in defects or []:
        pv = int(d.get("point_value", 0) or 0)
        cnt = int(d.get("count", 0) or 0)
        if pv in VALID_POINTS and cnt > 0:
            total += pv * cnt
    return round(total, 2)


def grade_from_points(points: float, th: Dict[str, float]) -> str:
    """Poin defect → grade enum resmi (A|A1|A2|B|BS) sesuai D-01."""
    if points <= th["a_max"]:
        return "A"
    if points <= th.get("a1_max", th["a_max"]):
        return "A1"
    if points <= th.get("a2_max", th["b_max"]):
        return "A2"
    if points <= th["b_max"]:
        return "B"
    return "BS"


async def inspect_roll(roll: Dict[str, Any], defects: List[Dict[str, Any]],
                       gsm_actual: Optional[float], width_actual: Optional[float],
                       note: str, actor: Dict[str, Any],
                       supplier_lot: str = "", dye_lot: str = "",
                       shade_ref: str = "") -> Dict[str, Any]:
    """Catat inspeksi 4-point pada 1 roll → hitung poin & grade → update roll.

    FASE C (D-10/PS-10) — inspeksi adalah titik input LOT kedua setelah penerimaan:
    `supplier_lot` / `dye_lot` / `shade_ref` yang diisi petugas QC disimpan ke lot
    (SSOT `inventory_lots`) dan roll, plus jejak `lot_id` di dokumen inspeksi.
    Penegakan mengikuti pengaturan (`warn` = hanya peringatan, `block` = menolak).
    """
    from services import lot_service as lots
    lot_settings = await lots.get_settings()
    lot_doc: Dict[str, Any] = {}
    if roll.get("lot_id"):
        try:
            lot_doc = await lots.get_lot(roll["lot_id"])
        except lots.LotError:
            lot_doc = {}
    eff_supplier_lot = (supplier_lot or "").strip() or lot_doc.get("supplier_lot", "") or \
        roll.get("supplier_lot", "")
    eff_dye_lot = (dye_lot or "").strip() or roll.get("dye_lot", "") or lot_doc.get("dye_lot", "")
    lot_warnings = await lots.guard_capture(eff_supplier_lot, eff_dye_lot, lot_settings)
    if lot_doc:
        patch: Dict[str, Any] = {}
        if (supplier_lot or "").strip():
            patch["supplier_lot"] = supplier_lot.strip()
        if (dye_lot or "").strip():
            patch["dye_lot"] = dye_lot.strip()
        if (shade_ref or "").strip():
            patch["shade_ref"] = shade_ref.strip()
        if patch:
            lot_doc = await lots.patch_lot(lot_doc["id"], patch,
                                           actor.get("name", "QC"))
    if (supplier_lot or "").strip():
        await db.inventory_rolls.update_one(
            {"id": roll["id"]}, {"$set": {"supplier_lot": supplier_lot.strip(),
                                          "updated_at": now_iso()}})

    th = await grade_thresholds(roll.get("owner_entity_id"))
    points = compute_points(defects)
    grade = grade_from_points(points, th)

    norm_defects = [{
        "point_value": int(d.get("point_value", 0) or 0),
        "count": int(d.get("count", 0) or 0),
        "note": d.get("note", ""),
    } for d in (defects or []) if int(d.get("point_value", 0) or 0) in VALID_POINTS and int(d.get("count", 0) or 0) > 0]

    inspection = {
        "points": points, "grade": grade,
        "defects": norm_defects,
        "gsm_actual": (float(gsm_actual) if gsm_actual not in (None, "") else None),
        "width_actual": (float(width_actual) if width_actual not in (None, "") else None),
        "thresholds": th, "note": note or "",
        # FASE C — jejak lot pada dokumen inspeksi (PS-10: inspeksi wajib berlot)
        "lot_id": lot_doc.get("id", "") or roll.get("lot_id", ""),
        "lot_number": lot_doc.get("lot_number", "") or roll.get("lot", ""),
        "supplier_lot": eff_supplier_lot, "dye_lot": eff_dye_lot,
        "shade_ref": (shade_ref or "").strip() or lot_doc.get("shade_ref", ""),
        "lot_warnings": lot_warnings,
        "inspected_by": actor.get("name", "Admin"),
        "inspected_by_id": actor.get("id", ""),
        "inspected_at": now_iso(),
    }
    # Fase A · PS-09/D-23 — grade HANYA berubah lewat jalur tercatat:
    # tulis riwayat (before → after) + audit lewat `grade_service` (SSOT grade roll).
    from services import grade_service
    grade_result = await grade_service.set_roll_grade(
        roll["id"], grade, source="qc_inspection",
        reason=f"Inspeksi 4-point: {points} poin (ambang A≤{th['a_max']}, B≤{th['b_max']})",
        actor=actor, extra={"points": points, "inspection_note": note or ""})
    updated = await db.inventory_rolls.find_one_and_update(
        {"id": roll["id"]},
        {"$set": {"defects": norm_defects, "inspection": inspection,
                  "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=True)
    return {"roll": safe_doc(updated), "points": points, "grade": grade, "thresholds": th,
            "grade_before": grade_result["grade_before"],
            "grade_history_entry": grade_result["history_entry"],
            # FASE C — lot & peringatan kelengkapan ditampilkan di panel inspeksi
            "lot": {"id": inspection["lot_id"], "lot_number": inspection["lot_number"],
                    "supplier_lot": inspection["supplier_lot"],
                    "dye_lot": inspection["dye_lot"], "shade_ref": inspection["shade_ref"],
                    "lot_status": lot_doc.get("lot_status", "")},
            "lot_warnings": lot_warnings}


async def rolls_for_task(task_id: str) -> List[Dict[str, Any]]:
    """Roll yang menunggu/inspeksi untuk sebuah inbound task (per qc_task_id)."""
    rolls = await db.inventory_rolls.find(
        {"qc_task_id": task_id}, {"_id": 0}).sort("roll_no", 1).to_list(500)
    prod_ids = list({r.get("product_id") for r in rolls if r.get("product_id")})
    prods = {p["id"]: p for p in await db.products.find(
        {"id": {"$in": prod_ids}}, {"_id": 0}).to_list(500)}
    lot_ids = list({r.get("lot_id") for r in rolls if r.get("lot_id")})
    lots = {l["id"]: l for l in await db.inventory_lots.find(
        {"id": {"$in": lot_ids}},
        {"_id": 0, "id": 1, "lot_number": 1, "supplier_lot": 1, "dye_lot": 1,
         "shade_ref": 1, "lot_status": 1}).to_list(500)}
    out = []
    for r in rolls:
        prod = prods.get(r.get("product_id"), {})
        insp = r.get("inspection") or {}
        lot = lots.get(r.get("lot_id"), {})
        out.append({
            "id": r["id"], "roll_no": r.get("roll_no"),
            "product_id": r.get("product_id"), "sku": prod.get("sku", ""),
            "product_name": prod.get("name", ""),
            "gsm_standard": prod.get("gramasi", None), "width_standard": prod.get("lebar", None),
            "length_initial": r.get("length_initial"), "unit": r.get("unit"),
            "grade": r.get("grade", ""), "status": r.get("status", ""),
            "inspected": bool(insp.get("inspected_at")),
            "inspection": insp,
            # FASE C — identitas lot per roll (dipakai form inspeksi QC)
            "lot_id": r.get("lot_id", ""),
            "lot_number": lot.get("lot_number", "") or r.get("lot", ""),
            "supplier_lot": r.get("supplier_lot", "") or lot.get("supplier_lot", ""),
            "dye_lot": r.get("dye_lot", "") or lot.get("dye_lot", ""),
            "shade_ref": lot.get("shade_ref", ""),
            "lot_status": lot.get("lot_status", ""),
        })
    return out
