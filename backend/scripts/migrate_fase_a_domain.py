#!/usr/bin/env python3
"""migrate_fase_a_domain.py — MIGRASI IDEMPOTEN Fase A (Fondasi Domain Tekstil).

Rujukan: `docs/KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md` (PS-01/02/03/09, §11)
         `docs/KN_19_PLAN_FASE_A_FONDASI_DOMAIN.md`

Apa yang dikerjakan (ADDITIVE, tidak menghapus data):
  1. `products` & `product_templates`
     - `stage`       : dinormalisasi ke enum (alias `greige`→`grey`); hilang/tidak dikenal → `finished`
     - `fabric_type` : hilang/tidak dikenal → **`woven`** (keputusan **D-20**) + tanda `fabric_type_migrated`
     - `grade`       : dinormalisasi ke enum resmi A|A1|A2|B|BS (mis. `A+`→`A`, `C`→`BS`);
                       nilai yang tak bisa dipetakan disimpan di `grade_legacy` lalu di-set `A`
     - `needs_review`/`needs_review_reasons` : dihitung dari aturan kelengkapan per stage
                       (GSM+lebar ≥ grey untuk woven, `yarn_count` untuk stage yarn)
  2. `inventory_rolls`
     - `grade`       : dinormalisasi ke enum; perubahan dicatat di `grade_history[]`
                       dengan `source="migration"` (PS-09) — TANPA duplikat saat dijalankan ulang
     - `stage` & `fabric_type` : snapshot dari master produk bila belum ada

Idempoten: hanya menulis bila ada perbedaan nyata; menjalankan dua kali menghasilkan
`changed=0` pada eksekusi kedua (diverifikasi POC `backend/test_fase_a_poc.py`).

Jalankan:
    cd /app/backend && python scripts/migrate_fase_a_domain.py            # terapkan
    cd /app/backend && python scripts/migrate_fase_a_domain.py --dry-run  # simulasi
"""
import asyncio
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import domain_registry as dr  # noqa: E402
from core_utils import now_iso  # noqa: E402

DRY = "--dry-run" in sys.argv


def _domain_patch(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Hitung `$set` minimal agar dokumen produk/template patuh domain Fase A."""
    patch: Dict[str, Any] = {}

    stage = dr.normalize_stage(doc.get("stage")) or "finished"
    if doc.get("stage") != stage:
        patch["stage"] = stage

    fabric = dr.normalize_fabric_type(doc.get("fabric_type"))
    if fabric is None:
        fabric = "woven"                        # D-20
        patch["fabric_type"] = fabric
        patch["fabric_type_migrated"] = True    # jejak: nilai hasil migrasi, bukan input user
    elif doc.get("fabric_type") != fabric:
        patch["fabric_type"] = fabric

    norm = dr.normalize_grade(doc.get("grade"))
    grade = norm["value"]
    if grade is None:
        if str(doc.get("grade") or "").strip():
            patch["grade_legacy"] = str(doc.get("grade"))
        grade = "A"
    if doc.get("grade") != grade:
        patch["grade"] = grade
    if norm["legacy"] and doc.get("grade_legacy") != norm["legacy"]:
        patch["grade_legacy"] = norm["legacy"]

    merged = {**doc, **patch}
    check = dr.validate_product(merged)
    # `needs_review` = ada field wajib yang belum lengkap (error) ATAU disarankan (warning).
    needs_review = bool(check["needs_review"] or check["errors"])
    if bool(doc.get("needs_review")) != needs_review:
        patch["needs_review"] = needs_review
    if list(doc.get("needs_review_reasons") or []) != check["needs_review_reasons"]:
        patch["needs_review_reasons"] = check["needs_review_reasons"]
    # Kelengkapan wajib yang tidak bisa ditebak sistem (mis. GSM woven, yarn_count)
    # dicatat sebagai `domain_gaps` agar terlihat di UI & invarian — tanpa mengarang nilai.
    gaps = [e for e in check["errors"]]
    if list(doc.get("domain_gaps") or []) != gaps:
        patch["domain_gaps"] = gaps
    return patch


async def _migrate_collection(db, name: str) -> Dict[str, int]:
    docs: List[Dict[str, Any]] = await db[name].find({}, {"_id": 0}).to_list(20000)
    changed = 0
    for doc in docs:
        patch = _domain_patch(doc)
        if not patch:
            continue
        changed += 1
        if not DRY:
            patch["updated_at"] = now_iso()
            await db[name].update_one({"id": doc["id"]}, {"$set": patch})
    return {"total": len(docs), "changed": changed}


async def _migrate_rolls(db) -> Dict[str, int]:
    rolls = await db.inventory_rolls.find({}, {"_id": 0}).to_list(50000)
    prod_ids = list({r.get("product_id") for r in rolls if r.get("product_id")})
    prods = {p["id"]: p for p in await db.products.find(
        {"id": {"$in": prod_ids}}, {"_id": 0, "id": 1, "stage": 1, "fabric_type": 1}).to_list(20000)}
    changed = regraded = 0
    for r in rolls:
        patch: Dict[str, Any] = {}
        push = None
        prod = prods.get(r.get("product_id"), {})

        norm = dr.normalize_grade(r.get("grade"))
        grade = norm["value"] or "A"
        if r.get("grade") != grade:
            patch["grade"] = grade
            patch["grade_source"] = "migration"
            # Catat riwayat HANYA sekali (idempoten): cek entri migrasi yang sudah ada.
            already = any(h.get("source") == "migration" and h.get("grade_after") == grade
                          for h in (r.get("grade_history") or []))
            if not already:
                push = {"grade_history": {
                    "grade_before": r.get("grade") or "",
                    "grade_after": grade,
                    "rank_before": dr.grade_rank(r.get("grade")),
                    "rank_after": dr.grade_rank(grade),
                    "direction": "tetap",
                    "source": "migration",
                    "source_label": dr.label_of("grade_change_source", "migration"),
                    "reason": "Normalisasi grade ke enum resmi (Fase A · D-01)",
                    "changed_by": "migration",
                    "changed_by_id": "",
                    "changed_by_role": "system",
                    "changed_at": now_iso(),
                }}
                regraded += 1

        stage = dr.normalize_stage(prod.get("stage")) or "finished"
        if not r.get("stage"):
            patch["stage"] = stage
        fabric = dr.normalize_fabric_type(prod.get("fabric_type")) or "woven"
        if not r.get("fabric_type"):
            patch["fabric_type"] = fabric

        if not patch:
            continue
        changed += 1
        if not DRY:
            patch["updated_at"] = now_iso()
            update: Dict[str, Any] = {"$set": patch}
            if push:
                update["$push"] = push
            await db.inventory_rolls.update_one({"id": r["id"]}, update)
    return {"total": len(rolls), "changed": changed, "regraded": regraded}


async def _verify(db) -> int:
    """Invarian ringkas pasca-migrasi (detail lengkap ada di verify_data_integrity)."""
    problems = 0
    valid_stage, valid_fabric, valid_grade = (dr.values_of("stage"), dr.values_of("fabric_type"),
                                             dr.values_of("grade"))
    for coll in ("products", "product_templates"):
        bad_stage = await db[coll].count_documents({"stage": {"$nin": valid_stage}})
        bad_fabric = await db[coll].count_documents({"fabric_type": {"$nin": valid_fabric}})
        bad_grade = await db[coll].count_documents(
            {"grade": {"$exists": True, "$nin": valid_grade}})
        print(f"   {coll:<20} stage_invalid={bad_stage} fabric_invalid={bad_fabric} "
              f"grade_invalid={bad_grade}")
        problems += bad_stage + bad_fabric + bad_grade
    bad_roll_grade = await db.inventory_rolls.count_documents({"grade": {"$nin": valid_grade}})
    no_stage = await db.inventory_rolls.count_documents(
        {"$or": [{"stage": {"$exists": False}}, {"stage": ""}]})
    print(f"   inventory_rolls      grade_invalid={bad_roll_grade} tanpa_stage={no_stage}")
    problems += bad_roll_grade + no_stage
    return problems


async def _run() -> int:
    from db import db
    mode = "DRY-RUN (tanpa tulis)" if DRY else "TERAPKAN"
    print(f"\n=== MIGRASI FASE A — FONDASI DOMAIN TEKSTIL ({mode}) ===\n")

    prod = await _migrate_collection(db, "products")
    print(f"1. products          : {prod['changed']}/{prod['total']} dokumen diperbarui")
    tpl = await _migrate_collection(db, "product_templates")
    print(f"2. product_templates : {tpl['changed']}/{tpl['total']} dokumen diperbarui")
    rolls = await _migrate_rolls(db)
    print(f"3. inventory_rolls   : {rolls['changed']}/{rolls['total']} roll diperbarui "
          f"({rolls['regraded']} riwayat grade dicatat)")

    print("\n=== VERIFIKASI ===")
    problems = 0 if DRY else await _verify(db)
    total_changed = prod["changed"] + tpl["changed"] + rolls["changed"]
    print(f"\nRingkasan: changed={total_changed} · masalah_invarian={problems}")
    if problems:
        print("❌ MIGRASI BELUM BERSIH — periksa dokumen bermasalah di atas.")
        return 1
    print("✅ Migrasi selesai & idempoten (jalankan ulang → changed=0).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
