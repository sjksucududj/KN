"""FASE E-4 (E4.1) — GUDANG BERSAMA vs GUDANG KHUSUS BADAN USAHA.

KEPUTUSAN PEMILIK #3 (plan.md §0): **campur**. Ada gudang yang dipakai bersama
seluruh badan usaha, ada gudang yang khusus milik satu/beberapa badan usaha.

Bentuk datanya di `warehouses`:
    sharing_mode : "shared"     → boleh dipakai SEMUA badan usaha
                   "dedicated"  → hanya badan usaha pada `entity_ids`
    entity_ids   : ["ent_ksc", ...]   (hanya bermakna saat "dedicated")

Kenapa `entity_ids` (daftar) dan BUKAN `entity_id` (satu pemilik): satu gudang
boleh dipakai 2 badan usaha tanpa dibuka untuk semuanya (mis. dua CV serumpun
berbagi gudang Bekasi, PT lain tidak). Karena itu `warehouses` tetap koleksi
**SHARED** di `entity_scope.SCOPE_FIELD` — pembatasannya relasi banyak-ke-banyak,
bukan satu kolom pemilik.

DUA sisi yang dijaga berkas ini:
  1. **Melihat** — daftar gudang yang dikirim ke layar sudah tersaring, jadi
     pemilih gudang di penerimaan/kirim/transfer/stok/opname tidak pernah
     menawarkan gudang yang haram dipakai (`usable_query`, `list_usable`).
  2. **Menyimpan** — server MENOLAK bila badan usaha aktif memakai gudang yang
     bukan haknya (`assert_usable`). Layar boleh salah; buku tidak boleh.

GUDANG LAMA (tanpa field) dianggap **"shared"**: menambah fitur tidak boleh
mengunci stok yang sudah ada. Migrasi menuliskan nilai eksplisit
(`scripts/migrate_e4_warehouse_sharing.py`).

PAGAR SAAT MENGUBAH MODE: gudang tidak bisa dijadikan "khusus" bila masih
menyimpan stok badan usaha yang tidak didaftarkan — sistem menyebut **jumlah roll
dan nama pemiliknya**, bukan menolak tanpa alasan (`dedication_blockers`).
Tanpa pagar ini, 20 roll bisa terkurung di gudang yang pemiliknya tak boleh masuk.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from core_utils import safe_doc
from db import db

SHARED = "shared"
DEDICATED = "dedicated"
MODES = (SHARED, DEDICATED)

# Gudang demo/lama tanpa field → bersama. Lihat docstring: jangan mengunci data lama.
LEGACY_MODE = SHARED

# Status roll yang masih "ada barangnya di gudang" (dipakai pagar dedikasi).
OCCUPYING_ROLL_STATUSES = ("available", "reserved", "quarantine", "subcon")


# ─── Bentuk data ──────────────────────────────────────────────────────────────
def mode_of(warehouse: Dict[str, Any]) -> str:
    mode = str((warehouse or {}).get("sharing_mode") or "").strip().lower()
    return mode if mode in MODES else LEGACY_MODE


def dedicated_ids(warehouse: Dict[str, Any]) -> List[str]:
    ids = (warehouse or {}).get("entity_ids") or []
    return [str(x) for x in ids if str(x or "").strip()]


def is_usable(warehouse: Dict[str, Any], entity_id: Optional[str]) -> bool:
    """Boleh dipakai badan usaha `entity_id`?

    `""`/`None`/`"all"` = konteks gabungan (admin melihat semua) → semua gudang
    terlihat; pagar TULIS mode gabungan sudah ditangani `entity_write_guard`.
    """
    eid = str(entity_id or "").strip()
    if not eid or eid == "all":
        return True
    if mode_of(warehouse) == SHARED:
        return True
    return eid in dedicated_ids(warehouse)


def usable_query(entity_id: Optional[str]) -> Dict[str, Any]:
    """Filter Mongo "gudang yang boleh dipakai badan usaha ini".

    `sharing_mode` yang belum ada (`$exists: false`) ikut lolos — gudang lama
    bersifat bersama.
    """
    eid = str(entity_id or "").strip()
    if not eid or eid == "all":
        return {}
    return {"$or": [{"sharing_mode": {"$ne": DEDICATED}}, {"entity_ids": eid}]}


# ─── Label untuk layar ────────────────────────────────────────────────────────
async def entity_name_map() -> Dict[str, str]:
    rows = await db.business_entities.find(
        {}, {"_id": 0, "id": 1, "short_name": 1, "legal_name": 1}).to_list(200)
    return {r["id"]: (r.get("short_name") or r.get("legal_name") or r["id"]) for r in rows}


def sharing_label(warehouse: Dict[str, Any], names: Optional[Dict[str, str]] = None) -> str:
    names = names or {}
    if mode_of(warehouse) == SHARED:
        return "Bersama semua badan usaha"
    ids = dedicated_ids(warehouse)
    if not ids:
        return "Khusus — belum ada badan usaha dipilih"
    return "Khusus " + ", ".join(names.get(i, i) for i in ids)


def decorate(warehouse: Dict[str, Any], names: Optional[Dict[str, str]] = None,
             active_entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Field turunan supaya layar tidak perlu menebak aturannya sendiri."""
    if not warehouse:
        return warehouse
    w = dict(warehouse)
    names = names or {}
    w["sharing_mode"] = mode_of(w)
    w["entity_ids"] = dedicated_ids(w)
    w["entity_names"] = [names.get(i, i) for i in w["entity_ids"]]
    w["sharing_label"] = sharing_label(w, names)
    w["is_shared"] = w["sharing_mode"] == SHARED
    w["usable_by_active"] = is_usable(w, active_entity_id)
    return w


async def list_for_entity(entity_id: Optional[str], *, include_unusable: bool = False,
                          only_active: bool = False) -> List[Dict[str, Any]]:
    """Daftar gudang untuk satu badan usaha (sudah didekorasi & terurut)."""
    query: Dict[str, Any] = {} if include_unusable else usable_query(entity_id)
    if only_active:
        query = {**query, "active": {"$ne": False}}
    rows = await db.warehouses.find(query, {"_id": 0}).to_list(500)
    names = await entity_name_map()
    out = [decorate(safe_doc(w), names, entity_id) for w in rows if w]
    out.sort(key=lambda w: (not w.get("usable_by_active", True),
                            str(w.get("code") or ""), str(w.get("name") or "")))
    return out


# ─── Pagar TULIS ──────────────────────────────────────────────────────────────
def wh_label(warehouse: Dict[str, Any]) -> str:
    """Sebut gudang seperti manusia menyebutnya: \"Gudang Bandung Kopo\" \u2014 bukan
    \"Gudang Gudang Bandung Kopo\" (nama gudang di data sudah berawalan 'Gudang')."""
    name = str((warehouse or {}).get("name") or (warehouse or {}).get("code") or "").strip()
    if not name:
        return "Gudang ini"
    return name if name.lower().startswith("gudang") else f"Gudang {name}"


def _deny_message(warehouse: Dict[str, Any], entity_name: str,
                  names: Dict[str, str], action: str) -> str:
    owners = ", ".join(names.get(i, i) for i in dedicated_ids(warehouse)) or "badan usaha lain"
    return (f"{wh_label(warehouse)} khusus untuk "
            f"{owners}, jadi {entity_name} tidak bisa {action}. Pilih gudang lain, "
            "atau ubah mode gudang di menu Gudang (Master) bila memang mau dipakai bersama.")


async def assert_usable(warehouse_id: str, entity_id: Optional[str], *,
                        action: str = "memakainya",
                        field_label: str = "Gudang") -> Dict[str, Any]:
    """Pastikan badan usaha aktif berhak memakai gudang ini. 404 / 403 yang jelas."""
    wid = str(warehouse_id or "").strip()
    if not wid:
        raise HTTPException(status_code=400, detail=f"{field_label} wajib dipilih")
    wh = await db.warehouses.find_one({"id": wid}, {"_id": 0})
    if not wh:
        raise HTTPException(status_code=404, detail=f"{field_label} tidak ditemukan")
    if is_usable(wh, entity_id):
        return safe_doc(wh)
    names = await entity_name_map()
    raise HTTPException(status_code=403,
                        detail=_deny_message(wh, names.get(str(entity_id), str(entity_id)),
                                             names, action))


async def assert_many_usable(warehouse_ids: List[str], entity_id: Optional[str], *,
                             action: str = "memakainya") -> None:
    for wid in [w for w in (warehouse_ids or []) if w]:
        await assert_usable(wid, entity_id, action=action)


# ─── Pagar UBAH MODE (jangan mengurung stok orang lain) ───────────────────────
async def stock_owners(warehouse_id: str) -> Dict[str, Dict[str, Any]]:
    """Siapa saja yang barangnya ada di gudang ini, berapa banyak."""
    out: Dict[str, Dict[str, Any]] = {}
    roll_rows = await db.inventory_rolls.aggregate([
        {"$match": {"warehouse_id": warehouse_id,
                    "status": {"$in": list(OCCUPYING_ROLL_STATUSES)}}},
        {"$group": {"_id": "$owner_entity_id", "rolls": {"$sum": 1},
                    "qty": {"$sum": "$length_remaining"}}},
    ]).to_list(200)
    for r in roll_rows:
        eid = r.get("_id") or ""
        out.setdefault(eid, {"entity_id": eid, "rolls": 0, "qty": 0.0, "balances": 0})
        out[eid]["rolls"] = int(r.get("rolls") or 0)
        out[eid]["qty"] = round(float(r.get("qty") or 0), 2)
    bal_rows = await db.inventory_balances.aggregate([
        {"$match": {"warehouse_id": warehouse_id, "on_hand_qty": {"$gt": 0}}},
        {"$group": {"_id": "$owner_entity_id", "n": {"$sum": 1},
                    "qty": {"$sum": "$on_hand_qty"}}},
    ]).to_list(200)
    for r in bal_rows:
        eid = r.get("_id") or ""
        out.setdefault(eid, {"entity_id": eid, "rolls": 0, "qty": 0.0, "balances": 0})
        out[eid]["balances"] = int(r.get("n") or 0)
        if not out[eid]["qty"]:
            out[eid]["qty"] = round(float(r.get("qty") or 0), 2)
    return out


async def occupancy_report(warehouse_id: str) -> List[Dict[str, Any]]:
    """Isi gudang per badan usaha, siap tampil di layar."""
    owners = await stock_owners(warehouse_id)
    names = await entity_name_map()
    rows = []
    for eid, data in owners.items():
        rows.append({**data, "entity_name": names.get(eid, eid or "tanpa pemilik")})
    rows.sort(key=lambda r: -r["rolls"])
    return rows


async def dedication_blockers(warehouse_id: str, entity_ids: List[str]) -> Dict[str, Any]:
    """Bolehkah gudang ini dijadikan khusus untuk `entity_ids`?

    Menolak bila ada stok milik badan usaha di luar daftar: barangnya akan
    terkurung (pemiliknya tak boleh lagi kirim/terima dari gudang itu).
    """
    allow = {str(e) for e in (entity_ids or [])}
    owners = await stock_owners(warehouse_id)
    names = await entity_name_map()
    stranded = [{**data, "entity_name": names.get(eid, eid or "tanpa pemilik")}
                for eid, data in owners.items() if eid and eid not in allow]
    stranded.sort(key=lambda r: -r["rolls"])
    if not stranded:
        return {"blocked": False, "stranded": [], "message": ""}
    wh = await db.warehouses.find_one({"id": warehouse_id}, {"_id": 0}) or {}
    parts = [f"{r['rolls']} roll milik {r['entity_name']}" if r["rolls"]
             else f"stok milik {r['entity_name']}" for r in stranded]
    return {
        "blocked": True, "stranded": stranded,
        "message": (
            f"{wh_label(wh)} masih menyimpan "
            + " dan ".join(parts) + ". Kalau dijadikan khusus, barang itu terkurung: "
            "pemiliknya tidak bisa lagi kirim atau terima dari gudang ini. "
            "Pilih salah satu — sertakan pemilik stok tersebut dalam daftar, "
            "biarkan gudang ini Bersama, atau pindahkan stoknya lebih dulu."),
    }


def validate_mode(sharing_mode: str, entity_ids: List[str]) -> None:
    """Bentuk nilai yang sah (dipanggil sebelum menyimpan)."""
    mode = str(sharing_mode or "").strip().lower()
    if mode not in MODES:
        raise HTTPException(status_code=400,
                            detail="Mode gudang harus 'shared' (bersama) atau 'dedicated' (khusus)")
    if mode == DEDICATED and not [e for e in (entity_ids or []) if e]:
        raise HTTPException(status_code=400,
                            detail="Gudang khusus wajib memilih minimal satu badan usaha")


async def assert_entities_exist(entity_ids: List[str]) -> None:
    ids = [e for e in (entity_ids or []) if e]
    if not ids:
        return
    found = await db.business_entities.find({"id": {"$in": ids}}, {"_id": 0, "id": 1}).to_list(200)
    missing = sorted(set(ids) - {f["id"] for f in found})
    if missing:
        raise HTTPException(status_code=400,
                            detail=f"Badan usaha tidak ditemukan: {', '.join(missing)}")
