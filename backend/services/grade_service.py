"""Grade governance service — Fase A · PS-09 · D-01/D-19/D-23.

SATU-SATUNYA pintu perubahan `inventory_rolls.grade` (R3/SSOT). Semua jalur
(inspeksi QC 4-point, release karantina retur, override manager/admin) WAJIB
lewat `set_roll_grade()` supaya:
  * nilai grade selalu berasal dari enum resmi (`domain_registry`),
  * setiap perubahan menulis `grade_history[]` (before → after, sumber, alasan, aktor),
  * override manual hanya untuk manager/admin dan WAJIB beralasan (D-23),
  * jejak audit tercatat di koleksi `audit_logs`.
"""
from typing import Any, Dict, List, Optional

import domain_registry as dr
from core_utils import now_iso, safe_doc
from db import db

OVERRIDE_ROLES = ("admin", "manager")   # D-23


def normalize_or_raise(raw: Any, field_label: str = "Grade") -> str:
    """Normalisasi grade ke enum resmi; lempar DomainValidationError bila tak sah."""
    norm = dr.normalize_grade(raw)
    if norm["value"] is None:
        raise dr.DomainValidationError(
            f"{field_label} '{raw}' tidak sah. Pilihan (terbaik→terburuk): "
            f"{', '.join(dr.values_of('grade'))}.")
    return norm["value"]


def can_override(actor: Optional[Dict[str, Any]]) -> bool:
    return str((actor or {}).get("role", "")).lower() in OVERRIDE_ROLES


def history_entry(grade_before: Optional[str], grade_after: str, source: str,
                  reason: str, actor: Optional[Dict[str, Any]] = None,
                  extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Bangun satu entri `grade_history` (dipakai juga oleh service lain)."""
    actor = actor or {}
    rank_before = dr.grade_rank(grade_before)
    rank_after = dr.grade_rank(grade_after)
    entry = {
        "grade_before": grade_before or "",
        "grade_after": grade_after,
        "rank_before": rank_before,
        "rank_after": rank_after,
        "direction": ("turun" if (rank_before is not None and rank_after is not None
                                  and rank_after > rank_before)
                      else "naik" if (rank_before is not None and rank_after is not None
                                      and rank_after < rank_before)
                      else "tetap"),
        "source": source,
        "source_label": dr.label_of("grade_change_source", source),
        "reason": (reason or "").strip(),
        "changed_by": actor.get("name", ""),
        "changed_by_id": actor.get("id", ""),
        "changed_by_role": actor.get("role", ""),
        "changed_at": now_iso(),
    }
    if extra:
        entry.update(extra)
    return entry


async def set_roll_grade(roll_id: str, new_grade: Any, *, source: str, reason: str = "",
                        actor: Optional[Dict[str, Any]] = None,
                        extra: Optional[Dict[str, Any]] = None,
                        write_audit: bool = True) -> Dict[str, Any]:
    """Ubah grade sebuah roll dengan jejak lengkap (PS-09).

    `source` WAJIB salah satu enum `grade_change_source`. Untuk
    `manager_override`: aktor wajib admin/manager DAN `reason` wajib diisi (D-23).
    """
    if not dr.is_valid("grade_change_source", source):
        raise dr.DomainValidationError(
            f"Sumber perubahan grade '{source}' tidak sah. "
            f"Pilihan: {', '.join(dr.values_of('grade_change_source'))}.")
    grade_after = normalize_or_raise(new_grade)

    if source == "manager_override":
        if not can_override(actor):
            raise PermissionError(
                "Hanya manager/admin yang boleh mengubah grade tanpa inspeksi (D-23).")
        if not (reason or "").strip():
            raise dr.DomainValidationError(
                "Alasan wajib diisi saat override grade tanpa inspeksi (D-23).")

    roll = await db.inventory_rolls.find_one({"id": roll_id}, {"_id": 0})
    if not roll:
        raise LookupError(f"Roll {roll_id} tidak ditemukan")

    grade_before = roll.get("grade") or ""
    entry = history_entry(grade_before, grade_after, source, reason, actor, extra)
    updated = await db.inventory_rolls.find_one_and_update(
        {"id": roll_id},
        {"$set": {"grade": grade_after, "grade_source": source,
                  "grade_updated_at": entry["changed_at"], "updated_at": now_iso()},
         "$push": {"grade_history": entry}},
        projection={"_id": 0}, return_document=True)

    if write_audit:
        from dependencies import audit
        await audit((actor or {}).get("name", "system"), "roll_grade_changed",
                    "inventory_roll", roll_id,
                    {"grade_before": grade_before, "grade_after": grade_after,
                     "source": source, "reason": entry["reason"],
                     "roll_no": roll.get("roll_no", ""), "product_id": roll.get("product_id", "")})

    return {"roll": safe_doc(updated), "grade_before": grade_before,
            "grade_after": grade_after, "history_entry": entry}


async def grade_history(roll_id: str) -> List[Dict[str, Any]]:
    roll = await db.inventory_rolls.find_one({"id": roll_id}, {"_id": 0, "grade_history": 1,
                                                              "grade": 1, "roll_no": 1})
    return list((roll or {}).get("grade_history", []) or [])


def resolve_expected_grade(payload_grade: Any, product: Optional[Dict[str, Any]] = None,
                           *, allow_derive: bool = False) -> Dict[str, Any]:
    """Resolusi `expected_grade` dokumen pembelian (D-19).

    * Jalur manusia (`allow_derive=False`): grade WAJIB dipilih — tidak ada default.
    * Jalur turunan sistem (PR→PO, call-off, award RFQ) boleh menurunkan dari master
      produk dengan penanda `source="derived_product"` supaya tetap dapat diaudit.
    """
    raw = str(payload_grade or "").strip()
    if raw:
        return {"grade": normalize_or_raise(raw, "Grade yang diharapkan"), "source": "input"}
    if allow_derive:
        derived = dr.normalize_grade((product or {}).get("grade"))["value"]
        if derived:
            return {"grade": derived, "source": "derived_product"}
        return {"grade": "", "source": "unset"}
    raise dr.DomainValidationError(
        "Grade yang diharapkan wajib dipilih untuk setiap item (tidak ada nilai default) — "
        f"pilihan: {', '.join(dr.values_of('grade'))}.")


async def stamp_expected_grade(items: List[Dict[str, Any]], *, allow_derive: bool = True,
                               context: str = "dokumen") -> List[Dict[str, Any]]:
    """Isi/validasi `expected_grade` pada baris item dokumen pembelian (D-19).

    * `allow_derive=False` (jalur manusia): setiap baris WAJIB sudah memilih grade.
    * `allow_derive=True` (jalur turunan sistem: PR→PO, call-off, award RFQ):
      grade diturunkan dari master produk dan ditandai `expected_grade_source`.
    """
    pids = [str(it.get("product_id") or "") for it in items if it.get("product_id")]
    prods: Dict[str, Any] = {}
    if pids:
        prods = {p["id"]: p for p in await db.products.find(
            {"id": {"$in": pids}}, {"_id": 0, "id": 1, "grade": 1}).to_list(1000)}
    for idx, it in enumerate(items, start=1):
        try:
            res = resolve_expected_grade(it.get("expected_grade"),
                                        prods.get(str(it.get("product_id") or "")),
                                        allow_derive=allow_derive)
        except dr.DomainValidationError as exc:
            raise dr.DomainValidationError(f"Item #{idx} {context}: {exc.message}")
        it["expected_grade"] = res["grade"]
        it["expected_grade_source"] = res["source"]
    return items
