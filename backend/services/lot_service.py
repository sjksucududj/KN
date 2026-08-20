"""FASE C — LOT KELAS SATU (`inventory_lots`) · SSOT identitas batch & genealogi.

Rujukan: `docs/KN_23_PLAN_FASE_C_LOT.md` · KN_18 §5.1 & PS-10 · KN_15 §5.

Keputusan pemilik yang dieksekusi di sini:
  * **D-10** — format nomor `LOT-YYMM-####`, granularitas **per batch penerimaan/proses**
    (satu lot boleh menaungi banyak roll).
  * **D-26** — nomor lot **per entitas** (`KSC/LOT-2607-0001`), konsisten dengan SO/PO;
    memakai `next_doc_number` (sequence atomik per entitas+bulan, deletion-safe).
  * **D-27** — penegakan lot **bisa dikonfigurasi**: default `warn` (TIDAK memblokir
    operasi gudang, sesuai keputusan pemilik) dan dapat dinaikkan ke `block` tanpa deploy.

Prinsip (jangan dilanggar):
  1. SSOT fisik tetap `inventory_rolls`. Lot = identitas batch yang menaungi roll.
     Agregat lot (roll_count/qty) SELALU dihitung ulang dari roll — tidak pernah `$inc`.
  2. Genealogi dua arah (`parent_lot_ids` ⇄ `child_lot_ids`) dan WAJIB bebas siklus.
  3. Semua jalur pembuatan roll memakai `resolve_or_create()` sehingga tidak ada lot liar
     dan string lot lama tetap tersimpan di `legacy_lot_codes` (jejak migrasi).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import domain_registry as dr
from core_utils import (DEFAULT_ENTITY_ID, new_id, next_doc_number, now_iso,
                        parse_decimal, safe_doc)
from db import db

COLL = "inventory_lots"
ROLLS = "inventory_rolls"
SETTINGS_SCOPE = "lot"

# `KSC/LOT-2607-0001` (per entitas · D-26) atau `LOT-2607-0001` (legacy/global)
LOT_NUMBER_RE = re.compile(r"^(?:[A-Z0-9]+/)?LOT-\d{4}-\d{4,}$")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "enforcement_mode": "warn",        # warn | block (D-27)
    "require_supplier_lot": True,      # wajib diisi di form GR/QC
    "require_dye_lot": True,
    "auto_create_on_receiving": True,  # 1 batch penerimaan = 1 lot (per dye lot)
    "status_on_receipt": "karantina",
    "number_format": "LOT-YYMM-####",
}

# Sumber pembentukan lot (dipakai `inventory_lots.source`) — label untuk UI.
SOURCE_LABELS: Dict[str, str] = {s["value"]: s["label"] for s in dr.LOT_SOURCES}


class LotError(Exception):
    """Pelanggaran aturan lot (dipetakan ke HTTP 400 di router)."""


# ═══════════════════════════════════════════════════════════════════════════
# 1. PENGATURAN (D-27 — configurable tanpa deploy)
# ═══════════════════════════════════════════════════════════════════════════
async def get_settings(entity_id: str = "") -> Dict[str, Any]:
    """Kebijakan efektif. FASE E-4 (E4.5): bila `entity_id` diisi, setelan khusus
    badan usaha itu MENIMPA nilai global — dulu satu nilai memaksa seluruh grup.
    Tanpa `entity_id` perilakunya identik dengan sebelumnya (nol risiko regresi).
    """
    doc = await db.system_settings.find_one({"scope": SETTINGS_SCOPE}, {"_id": 0}) or {}
    out = dict(DEFAULT_SETTINGS)
    for key in DEFAULT_SETTINGS:
        if doc.get(key) is not None:
            out[key] = doc[key]
    out["updated_at"] = doc.get("updated_at", "")
    out["updated_by"] = doc.get("updated_by", "")
    if entity_id and entity_id != "all":
        from services.config_resolver import entity_overlay
        ovr = await entity_overlay(SETTINGS_SCOPE, entity_id) or {}
        for _k, _v in ovr.items():
            if _k in DEFAULT_SETTINGS:
                out[_k] = _v
        out["entity_id"] = entity_id
        # Daftar kunci yang benar-benar ditimpa — dipakai UI untuk lencana asal nilai.
        out["entity_overrides"] = sorted(_k for _k in ovr if _k in DEFAULT_SETTINGS)
    return out


async def update_settings(payload: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    cur = await get_settings()
    nxt = dict(cur)
    mode = (payload.get("enforcement_mode") or "").strip().lower()
    if mode:
        if mode not in ("warn", "block"):
            raise LotError("Mode penegakan lot harus 'warn' (peringatan) atau 'block' (menolak).")
        nxt["enforcement_mode"] = mode
    for flag in ("require_supplier_lot", "require_dye_lot", "auto_create_on_receiving"):
        if payload.get(flag) is not None:
            nxt[flag] = bool(payload[flag])
    if payload.get("status_on_receipt"):
        st = str(payload["status_on_receipt"]).strip()
        if not dr.is_valid("lot_status", st):
            raise LotError(f"Status lot '{st}' tidak dikenal. Pilihan: "
                           f"{', '.join(dr.values_of('lot_status'))}")
        nxt["status_on_receipt"] = st
    await db.system_settings.update_one(
        {"scope": SETTINGS_SCOPE},
        {"$set": {**{k: nxt[k] for k in DEFAULT_SETTINGS},
                  "updated_at": now_iso(), "updated_by": actor},
         "$setOnInsert": {"id": new_id("set"), "scope": SETTINGS_SCOPE}},
        upsert=True)
    return await get_settings()


async def ensure_defaults(actor: str = "bootstrap", dry_run: bool = False) -> bool:
    """Buat dokumen pengaturan lot bila belum ada (idempoten). True bila dibuat."""
    if await db.system_settings.find_one({"scope": SETTINGS_SCOPE}, {"_id": 0, "id": 1}):
        return False
    if dry_run:
        return True
    await db.system_settings.insert_one({
        "id": new_id("set"), "scope": SETTINGS_SCOPE, **DEFAULT_SETTINGS,
        "created_at": now_iso(), "updated_at": now_iso(), "updated_by": actor})
    return True


def capture_warnings(supplier_lot: str, dye_lot: str,
                     settings: Dict[str, Any]) -> List[str]:
    """Peringatan kelengkapan traceability (D-27 mode `warn`)."""
    out: List[str] = []
    if settings.get("require_supplier_lot") and not (supplier_lot or "").strip():
        out.append("Nomor lot supplier (supplier_lot) belum diisi — jejak asal barang "
                   "tidak lengkap untuk penarikan/recall.")
    if settings.get("require_dye_lot") and not (dye_lot or "").strip():
        out.append("Dye lot / shade belum diisi — keseragaman warna tidak dapat dijamin "
                   "saat pengiriman.")
    return out


async def guard_capture(supplier_lot: str, dye_lot: str,
                        settings: Optional[Dict[str, Any]] = None) -> List[str]:
    """Kembalikan peringatan; MENOLAK hanya bila mode penegakan = `block`."""
    st = settings or await get_settings()
    warns = capture_warnings(supplier_lot, dye_lot, st)
    if warns and st.get("enforcement_mode") == "block":
        raise LotError(" ".join(warns) + " (Mode penegakan lot = blokir.)")
    return warns


# ═══════════════════════════════════════════════════════════════════════════
# 2. PENOMORAN (D-10 + D-26)
# ═══════════════════════════════════════════════════════════════════════════
async def next_lot_number(entity_id: str = "") -> str:
    """`{KODE}/LOT-YYMM-####` — sequence atomik per (entitas, bulan)."""
    ym = datetime.now(timezone.utc).strftime("%y%m")
    return await next_doc_number(COLL, "lot_number", f"LOT-{ym}-", width=4,
                                entity_id=entity_id or DEFAULT_ENTITY_ID)


def is_valid_lot_number(value: Any) -> bool:
    return bool(LOT_NUMBER_RE.match(str(value or "").strip()))


# ═══════════════════════════════════════════════════════════════════════════
# 3. PEMBUATAN & PENCARIAN LOT
# ═══════════════════════════════════════════════════════════════════════════
async def _product(product_id: str) -> Dict[str, Any]:
    prod = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not prod:
        raise LotError(f"Produk '{product_id}' tidak ditemukan — lot wajib menunjuk produk master.")
    return prod


async def get_lot(lot_id: str) -> Dict[str, Any]:
    lot = await db[COLL].find_one({"id": lot_id}, {"_id": 0})
    if not lot:
        lot = await db[COLL].find_one({"lot_number": lot_id}, {"_id": 0})
    if not lot:
        raise LotError(f"Lot '{lot_id}' tidak ditemukan.")
    return safe_doc(lot)


async def find_by_number(lot_number: str) -> Optional[Dict[str, Any]]:
    if not (lot_number or "").strip():
        return None
    return await db[COLL].find_one({"lot_number": lot_number.strip()}, {"_id": 0})


async def create_lot(*, product_id: str, owner_entity_id: str = "", warehouse_id: str = "",
                     source: str = "manual", source_ref: Optional[Dict[str, Any]] = None,
                     supplier_lot: str = "", dye_lot: str = "", shade_ref: str = "",
                     supplier_id: str = "", supplier_name: str = "",
                     process: Optional[Dict[str, Any]] = None,
                     parent_lot_ids: Optional[List[str]] = None,
                     status: str = "", note: str = "", legacy_code: str = "",
                     lot_number: str = "", actor: str = "System") -> Dict[str, Any]:
    """Buat 1 dokumen lot + tautkan genealogi (bebas siklus)."""
    prod = await _product(product_id)
    owner = owner_entity_id or DEFAULT_ENTITY_ID
    src = (source or "manual").strip()
    if not dr.is_valid("lot_source", src):
        raise LotError(f"Sumber lot '{src}' tidak dikenal. Pilihan: "
                       f"{', '.join(dr.values_of('lot_source'))}")
    st = (status or "released").strip()
    if not dr.is_valid("lot_status", st):
        raise LotError(f"Status lot '{st}' tidak dikenal. Pilihan: "
                       f"{', '.join(dr.values_of('lot_status'))}")
    number = (lot_number or "").strip() or await next_lot_number(owner)
    if await find_by_number(number):
        raise LotError(f"Nomor lot '{number}' sudah dipakai.")
    snap = dr.roll_domain_snapshot(prod)
    doc: Dict[str, Any] = {
        "id": new_id("lot"),
        "lot_number": number,
        "entity_id": owner,               # dipakai sequence nomor (scope_field)
        "owner_entity_id": owner,         # kepemilikan (selaras roll · KN_15)
        "product_id": product_id,
        "sku": prod.get("sku", ""),
        "product_name": prod.get("name", ""),
        "warehouse_id": warehouse_id or "",
        "unit": prod.get("base_unit", "meter"),
        "stage": snap["stage"],
        "fabric_type": snap["fabric_type"],
        "source": src,
        "source_ref": source_ref or {"type": "", "id": "", "number": ""},
        "supplier_lot": (supplier_lot or "").strip(),
        "dye_lot": (dye_lot or "").strip(),
        "shade_ref": (shade_ref or "").strip(),
        "supplier_id": supplier_id or "",
        "supplier_name": supplier_name or "",
        "process": process or {"process_type": "", "partner_id": "", "partner_name": ""},
        "parent_lot_ids": [],
        "child_lot_ids": [],
        "lot_status": st,
        "status_history": [{"status": st, "reason": "Lot dibentuk", "actor": actor,
                            "at": now_iso()}],
        "roll_count": 0, "active_roll_count": 0,
        "qty_initial": 0.0, "qty_remaining": 0.0, "qty_available": 0.0,
        "status_breakdown": {},
        "legacy_lot_codes": [legacy_code.strip()] if (legacy_code or "").strip() else [],
        "note": note or "",
        "created_at": now_iso(), "updated_at": now_iso(),
        "created_by": actor, "created_by_name": actor,
    }
    await db[COLL].insert_one(dict(doc))
    for pid in parent_lot_ids or []:
        await link_parent(doc["id"], pid)
    return await get_lot(doc["id"])


async def resolve_or_create(*, product_id: str, owner_entity_id: str = "",
                            warehouse_id: str = "", lot_code: str = "",
                            source: str = "manual",
                            source_ref: Optional[Dict[str, Any]] = None,
                            supplier_lot: str = "", dye_lot: str = "",
                            supplier_id: str = "", supplier_name: str = "",
                            status: str = "", actor: str = "System",
                            process: Optional[Dict[str, Any]] = None,
                            parent_lot_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """IDEMPOTEN — kembalikan lot untuk sebuah roll/batch.

    Urutan resolusi:
      1. `lot_code` == nomor lot yang ada & produk+owner cocok → pakai lot itu.
      2. `lot_code` string lama (mis. `LOT-PO-00007`) → lot dengan `legacy_lot_codes`
         yang sama untuk (produk, owner) → pakai; belum ada → buat lot baru dan
         simpan string lama sebagai jejak.
      3. `lot_code` kosong → lot baru (nomor per entitas).
    """
    owner = owner_entity_id or DEFAULT_ENTITY_ID
    code = (lot_code or "").strip()
    if code:
        exist = await find_by_number(code)
        if exist and exist.get("product_id") == product_id and \
                exist.get("owner_entity_id") == owner:
            return safe_doc(exist)
        legacy = await db[COLL].find_one(
            {"legacy_lot_codes": code, "product_id": product_id,
             "owner_entity_id": owner}, {"_id": 0})
        if legacy:
            return safe_doc(legacy)
    if source_ref and source_ref.get("id"):
        # 1 batch dokumen + 1 dye lot = 1 lot (granularitas D-10)
        q = {"source_ref.id": source_ref["id"], "product_id": product_id,
             "owner_entity_id": owner, "dye_lot": (dye_lot or "").strip()}
        same = await db[COLL].find_one(q, {"_id": 0})
        if same:
            if code and code not in (same.get("legacy_lot_codes") or []):
                await db[COLL].update_one({"id": same["id"]},
                                          {"$addToSet": {"legacy_lot_codes": code}})
                return await get_lot(same["id"])
            return safe_doc(same)
    return await create_lot(
        product_id=product_id, owner_entity_id=owner, warehouse_id=warehouse_id,
        source=source, source_ref=source_ref, supplier_lot=supplier_lot,
        dye_lot=dye_lot, supplier_id=supplier_id, supplier_name=supplier_name,
        status=status, legacy_code=code if not is_valid_lot_number(code) else "",
        actor=actor, process=process, parent_lot_ids=parent_lot_ids)


# ═══════════════════════════════════════════════════════════════════════════
# 4. AGREGAT (selalu turunan dari roll — tidak pernah $inc)
# ═══════════════════════════════════════════════════════════════════════════
DEAD_STATUSES = {"sold", "scrapped"}


async def recompute(lot_id: str) -> Dict[str, Any]:
    lot = await db[COLL].find_one({"id": lot_id}, {"_id": 0})
    if not lot:
        raise LotError(f"Lot '{lot_id}' tidak ditemukan.")
    rolls = await db[ROLLS].find({"lot_id": lot_id},
                                {"_id": 0, "id": 1, "status": 1, "length_initial": 1,
                                 "length_remaining": 1}).to_list(20000)
    breakdown: Dict[str, float] = {}
    qty_init = qty_rem = qty_avail = 0.0
    active = 0
    for r in rolls:
        st = r.get("status") or "unknown"
        rem = float(r.get("length_remaining") or 0)
        qty_init += float(r.get("length_initial") or 0)
        qty_rem += rem
        breakdown[st] = round(breakdown.get(st, 0.0) + rem, 3)
        if st == "available":
            qty_avail += rem
        if st not in DEAD_STATUSES:
            active += 1
    patch = {"roll_count": len(rolls), "active_roll_count": active,
             "qty_initial": round(qty_init, 3), "qty_remaining": round(qty_rem, 3),
             "qty_available": round(qty_avail, 3), "status_breakdown": breakdown,
             "updated_at": now_iso()}
    await db[COLL].update_one({"id": lot_id}, {"$set": patch})
    # Ledger append-only: lengkapi `lot_id` pada movement roll lot ini yang belum
    # berjejak (mis. dibuat jalur lama) — hanya MENAMBAH field jejak, angka tak diubah.
    roll_ids = [r["id"] for r in rolls]
    if roll_ids:
        await db.inventory_movements.update_many(
            {"roll_id": {"$in": roll_ids},
             "$or": [{"lot_id": {"$exists": False}}, {"lot_id": None}, {"lot_id": ""}]},
            {"$set": {"lot_id": lot_id}})
    return await get_lot(lot_id)


async def recompute_many(lot_ids: List[str]) -> int:
    done = 0
    for lid in {l for l in lot_ids if l}:
        try:
            await recompute(lid)
            done += 1
        except LotError:
            continue
    return done


async def attach_rolls(lot_id: str, roll_ids: List[str], *,
                       set_lot_string: bool = True,
                       actor: str = "System") -> Dict[str, Any]:
    """Tautkan roll ke lot (memindahkan dari lot lama bila ada) + hitung agregat."""
    lot = await get_lot(lot_id)
    rolls = await db[ROLLS].find({"id": {"$in": list(roll_ids)}}, {"_id": 0}).to_list(20000)
    if len(rolls) != len(set(roll_ids)):
        missing = set(roll_ids) - {r["id"] for r in rolls}
        raise LotError(f"Roll tidak ditemukan: {', '.join(sorted(missing))}")
    bad = [r["id"] for r in rolls
           if r.get("product_id") != lot["product_id"]
           or (r.get("owner_entity_id") or DEFAULT_ENTITY_ID) != lot["owner_entity_id"]]
    if bad:
        raise LotError("Lot tidak boleh lintas produk/pemilik. Roll bermasalah: "
                       f"{', '.join(bad[:5])}")
    previous = {r.get("lot_id") for r in rolls if r.get("lot_id")}
    patch: Dict[str, Any] = {"lot_id": lot["id"], "updated_at": now_iso()}
    if set_lot_string:
        patch["lot"] = lot["lot_number"]
        if lot.get("dye_lot"):
            patch["dye_lot"] = lot["dye_lot"]
    await db[ROLLS].update_many({"id": {"$in": [r["id"] for r in rolls]}}, {"$set": patch})
    await db.inventory_movements.update_many(
        {"roll_id": {"$in": [r["id"] for r in rolls]}, "lot_id": {"$in": [None, ""]}},
        {"$set": {"lot_id": lot["id"]}})
    await recompute_many([lot["id"], *previous])
    return await get_lot(lot["id"])


# ═══════════════════════════════════════════════════════════════════════════
# 5. GENEALOGI (parent ⇄ child, bebas siklus)
# ═══════════════════════════════════════════════════════════════════════════
async def _ids_upstream(lot_id: str, limit: int = 200) -> set:
    seen, queue = set(), [lot_id]
    while queue and len(seen) < limit:
        cur = queue.pop()
        if cur in seen:
            continue
        seen.add(cur)
        doc = await db[COLL].find_one({"id": cur}, {"_id": 0, "parent_lot_ids": 1}) or {}
        queue.extend(doc.get("parent_lot_ids") or [])
    return seen


async def _ids_downstream(lot_id: str, limit: int = 200) -> set:
    seen, queue = set(), [lot_id]
    while queue and len(seen) < limit:
        cur = queue.pop()
        if cur in seen:
            continue
        seen.add(cur)
        doc = await db[COLL].find_one({"id": cur}, {"_id": 0, "child_lot_ids": 1}) or {}
        queue.extend(doc.get("child_lot_ids") or [])
    return seen


async def link_parent(child_id: str, parent_id: str) -> None:
    """Tautkan parent→child dua arah; menolak siklus & tautan ke diri sendiri."""
    if child_id == parent_id:
        raise LotError("Lot tidak boleh menjadi induk dirinya sendiri.")
    child = await get_lot(child_id)
    parent = await get_lot(parent_id)
    if parent["id"] in await _ids_downstream(child["id"]):
        raise LotError(f"Menolak siklus genealogi: lot {parent['lot_number']} sudah berada "
                       f"di bawah {child['lot_number']}.")
    await db[COLL].update_one({"id": child["id"]},
                             {"$addToSet": {"parent_lot_ids": parent["id"]},
                              "$set": {"updated_at": now_iso()}})
    await db[COLL].update_one({"id": parent["id"]},
                             {"$addToSet": {"child_lot_ids": child["id"]},
                              "$set": {"updated_at": now_iso()}})


# ═══════════════════════════════════════════════════════════════════════════
# 6. AKSI GENEALOGI: SPLIT · MERGE · REWORK
# ═══════════════════════════════════════════════════════════════════════════
async def split_lot(lot_id: str, *, roll_ids: List[str], reason: str = "",
                    dye_lot: str = "", warehouse_id: str = "",
                    actor: str = "System") -> Dict[str, Any]:
    """Pecah sebagian roll dari sebuah lot menjadi lot anak (split)."""
    lot = await get_lot(lot_id)
    all_rolls = await db[ROLLS].find({"lot_id": lot["id"]}, {"_id": 0, "id": 1}).to_list(20000)
    all_ids = {r["id"] for r in all_rolls}
    picked = [r for r in dict.fromkeys(roll_ids or []) if r]
    if not picked:
        raise LotError("Pilih minimal 1 roll untuk dipecah.")
    outside = [r for r in picked if r not in all_ids]
    if outside:
        raise LotError(f"Roll bukan milik lot ini: {', '.join(outside[:5])}")
    if len(picked) >= len(all_ids):
        raise LotError("Split harus menyisakan minimal 1 roll di lot asal — untuk memindah "
                       "seluruh roll gunakan Rework atau Merge.")
    child = await create_lot(
        product_id=lot["product_id"], owner_entity_id=lot["owner_entity_id"],
        warehouse_id=warehouse_id or lot.get("warehouse_id", ""), source="split",
        source_ref={"type": "lot", "id": lot["id"], "number": lot["lot_number"]},
        supplier_lot=lot.get("supplier_lot", ""),
        dye_lot=(dye_lot or lot.get("dye_lot", "")), shade_ref=lot.get("shade_ref", ""),
        supplier_id=lot.get("supplier_id", ""), supplier_name=lot.get("supplier_name", ""),
        status=lot.get("lot_status", "released"),
        note=(reason or f"Split dari {lot['lot_number']}"),
        parent_lot_ids=[lot["id"]], actor=actor)
    await attach_rolls(child["id"], picked, actor=actor)
    return {"parent": await get_lot(lot["id"]), "child": await get_lot(child["id"]),
            "moved_rolls": len(picked)}


async def merge_lots(lot_ids: List[str], *, reason: str = "", dye_lot: str = "",
                     warehouse_id: str = "", actor: str = "System") -> Dict[str, Any]:
    """Gabung ≥2 lot (produk & pemilik sama) menjadi satu lot baru (merge)."""
    uniq = [l for l in dict.fromkeys(lot_ids or []) if l]
    if len(uniq) < 2:
        raise LotError("Merge memerlukan minimal 2 lot.")
    lots = [await get_lot(l) for l in uniq]
    if len({l["product_id"] for l in lots}) > 1:
        raise LotError("Merge hanya boleh untuk lot dengan produk yang sama.")
    if len({l["owner_entity_id"] for l in lots}) > 1:
        raise LotError("Merge hanya boleh untuk lot dengan pemilik (entitas) yang sama.")
    base = lots[0]
    merged = await create_lot(
        product_id=base["product_id"], owner_entity_id=base["owner_entity_id"],
        warehouse_id=warehouse_id or base.get("warehouse_id", ""), source="merge",
        source_ref={"type": "lot", "id": base["id"],
                    "number": ", ".join(l["lot_number"] for l in lots)},
        supplier_lot=next((l.get("supplier_lot") for l in lots if l.get("supplier_lot")), ""),
        dye_lot=dye_lot or next((l.get("dye_lot") for l in lots if l.get("dye_lot")), ""),
        supplier_id=base.get("supplier_id", ""), supplier_name=base.get("supplier_name", ""),
        status="hold_shade" if len({l.get("dye_lot", "") for l in lots}) > 1 else
               base.get("lot_status", "released"),
        note=(reason or "Merge lot: " + ", ".join(l["lot_number"] for l in lots)),
        parent_lot_ids=[l["id"] for l in lots], actor=actor)
    moved = 0
    for l in lots:
        rolls = await db[ROLLS].find({"lot_id": l["id"]}, {"_id": 0, "id": 1}).to_list(20000)
        if rolls:
            await attach_rolls(merged["id"], [r["id"] for r in rolls], actor=actor)
            moved += len(rolls)
        await db[COLL].update_one({"id": l["id"]},
                                 {"$set": {"merged_into": merged["id"],
                                           "updated_at": now_iso()}})
    return {"lot": await get_lot(merged["id"]), "sources": [l["lot_number"] for l in lots],
            "moved_rolls": moved}


async def rework_lot(lot_id: str, *, process_type: str, roll_ids: Optional[List[str]] = None,
                     partner_id: str = "", partner_name: str = "", to_stage: str = "",
                     reason: str = "", dye_lot: str = "", actor: str = "System") -> Dict[str, Any]:
    """Bentuk lot anak hasil proses ulang / lanjutan (rework).

    `to_stage` opsional: bila diisi, transisi divalidasi memakai state machine
    Fase A (`domain_registry.resolve_transition`) sehingga tidak ada lompatan stage liar.
    """
    lot = await get_lot(lot_id)
    if not dr.is_valid("process_type", process_type):
        raise LotError(f"Jenis proses '{process_type}' tidak dikenal. Pilihan: "
                       f"{', '.join(dr.values_of('process_type'))}")
    target = (to_stage or "").strip()
    if target:
        check = dr.check_transition(lot.get("stage"), process_type, None,
                                    lot.get("fabric_type"), target)
        if not check.get("ok"):
            raise LotError(check.get("message") or
                           f"Transisi {lot.get('stage')} → {target} via {process_type} tidak sah.")
    rolls = await db[ROLLS].find({"lot_id": lot["id"]}, {"_id": 0, "id": 1}).to_list(20000)
    picked = [r for r in (roll_ids or [r2["id"] for r2 in rolls]) if r]
    child = await create_lot(
        product_id=lot["product_id"], owner_entity_id=lot["owner_entity_id"],
        warehouse_id=lot.get("warehouse_id", ""), source="rework",
        source_ref={"type": "lot", "id": lot["id"], "number": lot["lot_number"]},
        supplier_lot=lot.get("supplier_lot", ""),
        dye_lot=dye_lot or lot.get("dye_lot", ""), shade_ref=lot.get("shade_ref", ""),
        process={"process_type": process_type, "partner_id": partner_id,
                 "partner_name": partner_name},
        status="in_process", note=(reason or f"Rework {process_type} dari {lot['lot_number']}"),
        parent_lot_ids=[lot["id"]], actor=actor)
    if target:
        await db[COLL].update_one({"id": child["id"]}, {"$set": {"stage": target}})
    if picked:
        await attach_rolls(child["id"], picked, actor=actor)
        if target:
            await db[ROLLS].update_many({"id": {"$in": picked}},
                                       {"$set": {"stage": target, "updated_at": now_iso()}})
    await set_status(lot["id"], "rework", reason or f"Rework → {child['lot_number']}", actor)
    return {"parent": await get_lot(lot["id"]), "child": await get_lot(child["id"]),
            "moved_rolls": len(picked)}


async def set_status(lot_id: str, status: str, reason: str = "",
                     actor: str = "System") -> Dict[str, Any]:
    lot = await get_lot(lot_id)
    st = (status or "").strip()
    if not dr.is_valid("lot_status", st):
        raise LotError(f"Status lot '{st}' tidak dikenal. Pilihan: "
                       f"{', '.join(dr.values_of('lot_status'))}")
    entry = {"status": st, "status_before": lot.get("lot_status", ""),
             "reason": reason or "", "actor": actor, "at": now_iso()}
    await db[COLL].update_one({"id": lot["id"]},
                             {"$set": {"lot_status": st, "updated_at": now_iso()},
                              "$push": {"status_history": entry}})
    return await get_lot(lot["id"])


async def patch_lot(lot_id: str, payload: Dict[str, Any],
                    actor: str = "System") -> Dict[str, Any]:
    """Ubah data identitas lot (supplier_lot/dye_lot/shade/note/gudang)."""
    lot = await get_lot(lot_id)
    allowed = ("supplier_lot", "dye_lot", "shade_ref", "note", "warehouse_id",
               "supplier_id", "supplier_name")
    patch = {k: (str(v).strip() if isinstance(v, str) else v)
             for k, v in (payload or {}).items() if k in allowed and v is not None}
    if not patch:
        raise LotError("Tidak ada perubahan yang sah untuk disimpan.")
    patch["updated_at"] = now_iso()
    patch["updated_by"] = actor
    await db[COLL].update_one({"id": lot["id"]}, {"$set": patch})
    if patch.get("dye_lot"):
        await db[ROLLS].update_many({"lot_id": lot["id"]},
                                   {"$set": {"dye_lot": patch["dye_lot"],
                                             "updated_at": now_iso()}})
    return await get_lot(lot["id"])


# ═══════════════════════════════════════════════════════════════════════════
# 7. DAFTAR & STATISTIK
# ═══════════════════════════════════════════════════════════════════════════
def _rx(term: str) -> Dict[str, Any]:
    return {"$regex": re.escape(term), "$options": "i"}


async def list_lots(query: Dict[str, Any], *, q: str = "", limit: int = 200,
                    skip: int = 0, sort: str = "-created_at") -> List[Dict[str, Any]]:
    flt = dict(query or {})
    if q:
        flt["$or"] = [{"lot_number": _rx(q)}, {"supplier_lot": _rx(q)},
                      {"dye_lot": _rx(q)}, {"sku": _rx(q)}, {"product_name": _rx(q)},
                      {"legacy_lot_codes": _rx(q)}, {"note": _rx(q)}]
    field = sort.lstrip("-") or "created_at"
    direction = -1 if sort.startswith("-") else 1
    rows = await db[COLL].find(flt, {"_id": 0}).sort(field, direction).skip(
        max(0, int(skip))).to_list(max(1, min(int(limit), 1000)))
    return [safe_doc(r) for r in rows]


async def count_lots(query: Dict[str, Any]) -> int:
    return await db[COLL].count_documents(dict(query or {}))


async def stats(query: Dict[str, Any]) -> Dict[str, Any]:
    """Ringkasan untuk kartu KPI + hitungan roll tanpa lot (bukti keputusan 2 = warn)."""
    lots = await db[COLL].find(dict(query or {}),
                              {"_id": 0, "lot_status": 1, "source": 1, "qty_remaining": 1,
                               "roll_count": 1, "supplier_lot": 1, "dye_lot": 1}).to_list(20000)
    by_status: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    qty = rolls = incomplete = 0.0
    for l in lots:
        by_status[l.get("lot_status", "?")] = by_status.get(l.get("lot_status", "?"), 0) + 1
        by_source[l.get("source", "?")] = by_source.get(l.get("source", "?"), 0) + 1
        qty += float(l.get("qty_remaining") or 0)
        rolls += int(l.get("roll_count") or 0)
        if not (l.get("supplier_lot") or "").strip() or not (l.get("dye_lot") or "").strip():
            incomplete += 1
    owner = (query or {}).get("owner_entity_id")
    roll_q: Dict[str, Any] = {"lot_id": {"$in": [None, ""]}}
    if owner:
        roll_q["owner_entity_id"] = owner
    rolls_without_lot = await db[ROLLS].count_documents(roll_q)
    return {"total": len(lots), "by_status": by_status, "by_source": by_source,
            "qty_remaining": round(qty, 3), "rolls_in_lots": int(rolls),
            "incomplete_capture": int(incomplete),
            "rolls_without_lot": rolls_without_lot,
            "settings": await get_settings()}


async def rolls_of(lot_id: str, limit: int = 500) -> List[Dict[str, Any]]:
    rows = await db[ROLLS].find(
        {"lot_id": lot_id},
        {"_id": 0, "id": 1, "roll_no": 1, "status": 1, "grade": 1, "length_initial": 1,
         "length_remaining": 1, "unit": 1, "warehouse_id": 1, "bin_id": 1, "dye_lot": 1,
         "stage": 1, "reserved_ref": 1, "earmarked_for": 1, "weight_kg": 1,
         "created_at": 1}).sort("roll_no", 1).to_list(limit)
    return [safe_doc(r) for r in rows]
