"""FASE G-0 — CONFIG RESOLVER: nilai efektif berlapis + jejak "kenapa begini" + berlaku-sejak.

Masalah lama: nilai konfigurasi ditimpa langsung di `system_settings` sehingga
(1) tidak ada riwayat, (2) tidak bisa dijadwalkan berlaku tanggal tertentu, dan
(3) user tidak pernah tahu **lapisan mana** yang menentukan nilai yang dia lihat.

Desain:
- Penyimpanan baru `config_values` (prefix `cfgv_`) bersifat **APPEND-ONLY**:
  setiap perubahan = baris baru berisi `value`, `prev_value`, `effective_from`,
  `reason`, `changed_by`. Riwayat, rollback, dan penjadwalan otomatis tersedia.
- Lapisan (kiri kalah, kanan menang):
    default kode → (legacy global) → global → (legacy entitas) → entitas
    → supplier → customer → produk → dokumen
- **Kompatibilitas penuh:** dokumen `system_settings` lama TETAP dibaca sebagai lapisan
  dan setiap penulisan level global/entitas juga **diproyeksikan** ke sana, sehingga
  seluruh mesin lama (yang membaca `system_settings`) langsung ikut berubah tanpa migrasi.

INV-CFG-03: baris `config_values` tidak pernah di-update pada field nilai. Hanya
`applied_at` (penanda bookkeeping proyeksi) yang boleh diisi sekali.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import config_registry as registry
from core_utils import new_id, now_iso
from db import db

COLL = "config_values"

# Lapisan dari paling umum → paling spesifik. Yang paling kanan MENANG.
LAYER_ORDER: List[str] = [
    "code_default",
    "legacy_global",
    "global",
    "legacy_entity",
    "entity",
    "supplier",
    "customer",
    "product",
    "document",
]
LAYER_LABEL = {
    "code_default": "Default sistem",
    "legacy_global": "Global (pengaturan lama)",
    "global": "Global",
    "legacy_entity": "Entitas (pengaturan lama)",
    "entity": "Entitas",
    "supplier": "Supplier",
    "customer": "Pelanggan",
    "product": "Produk",
    "document": "Dokumen",
    "hypothetical": "Simulasi (belum disimpan)",
}
# Lapisan yang berasal dari `config_values` (bisa ditulis lewat API baru).
WRITABLE_LAYERS = ("global", "entity", "supplier", "customer", "product", "document")
CTX_FIELD = {
    "entity": "entity_id",
    "supplier": "supplier_id",
    "customer": "customer_id",
    "product": "product_id",
    "document": "document_id",
}
_MISSING = object()


# ── util ──────────────────────────────────────────────────────────────────
def _dig(doc: Optional[Dict[str, Any]], path: str) -> Any:
    """Ambil nilai dot-path dari dokumen; `_MISSING` bila tak ada."""
    cur: Any = doc or {}
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def _iso_now() -> str:
    return now_iso()


def _as_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _is_due(row: Dict[str, Any], at: datetime) -> bool:
    ef = _as_dt(row.get("effective_from")) or datetime.min.replace(tzinfo=timezone.utc)
    return ef <= at


# ── baca lapisan ───────────────────────────────────────────────────────────
async def _legacy_doc(scope: str) -> Dict[str, Any]:
    return await db.system_settings.find_one({"scope": scope}, {"_id": 0}) or {}


async def _stored_rows(keys: List[str], ctx: Dict[str, Any]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    """Semua baris `config_values` relevan untuk kumpulan kunci + konteks, dikelompokkan
    per (key, scope_type). Diurutkan effective_from lalu created_at (terbaru terakhir)."""
    ors: List[Dict[str, Any]] = [{"scope_type": "global"}]
    for layer, field in CTX_FIELD.items():
        val = (ctx or {}).get(field)
        if val:
            ors.append({"scope_type": layer, "scope_id": val})
    cur = db[COLL].find({"key": {"$in": keys}, "$or": ors}, {"_id": 0})
    out: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    async for row in cur:
        out.setdefault((row["key"], row["scope_type"]), []).append(row)
    for rows in out.values():
        rows.sort(key=lambda r: (str(r.get("effective_from") or ""), str(r.get("created_at") or "")))
    return out


def _pick_effective(rows: List[Dict[str, Any]], at: datetime) -> Tuple[Any, Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """(nilai efektif, baris pemenang, baris terjadwal) dari daftar baris satu scope.

    FASE E-4 (E4.6) — baris ber-`cleared: True` adalah **nisan**: ia menyatakan
    "lapisan ini dikosongkan", bukan "nilainya None". Karena penyimpanan bersifat
    append-only (INV-CFG-03: baris nilai tidak pernah di-update/dihapus), inilah cara
    jujur menyediakan tombol "Kembalikan ke global" tanpa menghapus riwayat.
    """
    due = [r for r in rows if _is_due(r, at)]
    scheduled = [r for r in rows if not _is_due(r, at)]
    if not due:
        return _MISSING, None, scheduled
    winner = due[-1]
    if winner.get("cleared"):
        return _MISSING, winner, scheduled
    return winner.get("value"), winner, scheduled


async def build_layers(key: str, ctx: Optional[Dict[str, Any]] = None,
                       at: Optional[datetime] = None,
                       preloaded: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Susun seluruh lapisan untuk satu kunci (tanpa menentukan pemenang)."""
    entry = registry.require(key)
    ctx = ctx or {}
    at = at or datetime.now(timezone.utc)
    pre = preloaded or {}

    legacy_scope, legacy_path = entry["legacy_scope"], entry["legacy_path"]
    legacy_global = pre.get(f"legacy:{legacy_scope}")
    if legacy_global is None:
        legacy_global = await _legacy_doc(legacy_scope)
    ent_id = ctx.get("entity_id") or ""
    legacy_entity: Dict[str, Any] = {}
    if ent_id and ent_id != "all" and legacy_scope == "global":
        legacy_entity = pre.get(f"legacy:{ent_id}")
        if legacy_entity is None:
            legacy_entity = await _legacy_doc(ent_id)

    rows_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = pre.get("rows") or {}
    if not pre:
        rows_map = await _stored_rows([key], ctx)

    layers: List[Dict[str, Any]] = [{
        "layer": "code_default", "label": LAYER_LABEL["code_default"], "scope_id": "",
        "present": True, "value": entry["default"],
        "note": "Nilai bawaan kode — usulan awal, bukan aturan permanen.",
        "changed_by": "", "changed_at": "", "reason": "", "effective_from": "",
    }]

    lg = _dig(legacy_global, legacy_path)
    layers.append({
        "layer": "legacy_global", "label": LAYER_LABEL["legacy_global"], "scope_id": legacy_scope,
        "present": lg is not _MISSING, "value": None if lg is _MISSING else lg,
        "note": f"Dokumen system_settings scope '{legacy_scope}' (dibaca mesin lama).",
        "changed_by": (legacy_global or {}).get("updated_by", ""),
        "changed_at": (legacy_global or {}).get("updated_at", ""),
        "reason": "", "effective_from": "",
    })

    def _cfgv_layer(layer: str, scope_id: str) -> Dict[str, Any]:
        rows = rows_map.get((key, layer), [])
        if scope_id:
            rows = [r for r in rows if r.get("scope_id") == scope_id]
        val, win, sched = _pick_effective(rows, at)
        cleared = bool(win and win.get("cleared"))
        return {
            "layer": layer, "label": LAYER_LABEL[layer], "scope_id": scope_id,
            "present": val is not _MISSING,
            "value": None if val is _MISSING else val,
            "cleared": cleared,
            "note": ("Dikembalikan ke lapisan di atasnya — tidak lagi diatur di sini."
                     if cleared else
                     ("Diatur lewat Pusat Pengaturan." if win else "Belum diatur pada lapisan ini.")),
            "changed_by": (win or {}).get("changed_by", ""),
            "changed_at": (win or {}).get("changed_at", ""),
            "reason": (win or {}).get("reason", ""),
            "effective_from": (win or {}).get("effective_from", ""),
            "scheduled": [{"value": s.get("value"), "effective_from": s.get("effective_from"),
                           "changed_by": s.get("changed_by", ""), "reason": s.get("reason", "")}
                          for s in sched],
        }

    layers.append(_cfgv_layer("global", ""))

    le = _dig(legacy_entity, legacy_path) if legacy_entity else _MISSING
    layers.append({
        "layer": "legacy_entity", "label": LAYER_LABEL["legacy_entity"], "scope_id": ent_id,
        "present": le is not _MISSING, "value": None if le is _MISSING else le,
        "note": (f"Override entitas di system_settings scope '{ent_id}'." if ent_id
                 else "Tidak ada konteks entitas."),
        "changed_by": (legacy_entity or {}).get("updated_by", ""),
        "changed_at": (legacy_entity or {}).get("updated_at", ""),
        "reason": "", "effective_from": "",
    })

    for layer in ("entity", "supplier", "customer", "product", "document"):
        scope_id = ctx.get(CTX_FIELD[layer]) or ""
        if not scope_id:
            continue
        layers.append(_cfgv_layer(layer, scope_id))

    allowed = set(entry["scopes"])
    for lay in layers:
        if lay["layer"] in WRITABLE_LAYERS and lay["layer"] not in allowed:
            lay["present"] = False
            lay["note"] = ("Lapisan ini tidak didukung untuk setting ini — mesin pembacanya "
                           "belum menghormati level tersebut.")
    return layers


def _decide(layers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Tentukan pemenang (lapisan paling spesifik yang punya nilai) + tandai di explain."""
    rank = {name: i for i, name in enumerate(LAYER_ORDER)}
    winner = None
    for lay in layers:
        if lay.get("present") and (winner is None or rank.get(lay["layer"], -1) >= rank.get(winner["layer"], -1)):
            winner = lay
    for lay in layers:
        lay["winner"] = winner is not None and lay is winner
    return winner or layers[0]


async def resolve(key: str, ctx: Optional[Dict[str, Any]] = None,
                  at: Optional[datetime] = None,
                  hypothetical: Any = _MISSING,
                  preloaded: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Nilai efektif + jejak lengkap. `hypothetical` = nilai simulasi (tidak disimpan)."""
    entry = registry.require(key)
    layers = await build_layers(key, ctx, at, preloaded)
    if hypothetical is not _MISSING:
        layers.append({
            "layer": "hypothetical", "label": LAYER_LABEL["hypothetical"], "scope_id": "",
            "present": True, "value": hypothetical,
            "note": "Nilai yang sedang Anda coba — belum tersimpan.",
            "changed_by": "", "changed_at": "", "reason": "", "effective_from": "",
        })
        for lay in layers:
            lay["winner"] = lay["layer"] == "hypothetical"
        winner = layers[-1]
    else:
        winner = _decide(layers)
    return {
        "key": key,
        "value": winner.get("value"),
        "source_layer": winner["layer"],
        "source_label": winner["label"],
        "type": entry["type"],
        "status": entry["status"],
        "explain": layers,
        "scheduled": [s for lay in layers for s in (lay.get("scheduled") or [])],
    }


async def value_of(key: str, ctx: Optional[Dict[str, Any]] = None) -> Any:
    """Pintasan untuk kode mesin: ambil nilai efektif saja."""
    return (await resolve(key, ctx))["value"]


async def resolve_group(group_id: Optional[str] = None, ctx: Optional[Dict[str, Any]] = None,
                        term: str = "") -> List[Dict[str, Any]]:
    """Nilai efektif untuk sekumpulan setting (satu grup / hasil pencarian) — hemat query."""
    entries = registry.search(term) if term else (
        registry.by_group(group_id) if group_id else registry.all_entries())
    if not entries:
        return []
    keys = [e["key"] for e in entries]
    ctx = ctx or {}
    scopes_needed = {e["legacy_scope"] for e in entries}
    pre: Dict[str, Any] = {"rows": await _stored_rows(keys, ctx)}
    for sc in scopes_needed:
        pre[f"legacy:{sc}"] = await _legacy_doc(sc)
    ent_id = ctx.get("entity_id") or ""
    if ent_id and ent_id != "all":
        pre[f"legacy:{ent_id}"] = await _legacy_doc(ent_id)

    out: List[Dict[str, Any]] = []
    at = datetime.now(timezone.utc)
    for e in entries:
        res = await resolve(e["key"], ctx, at=at, preloaded=pre)
        out.append({**{k: e[k] for k in (
            "key", "group", "label", "help", "impact", "example", "type", "default",
            "min", "max", "step", "options", "unit", "scopes", "consumers", "owner_role",
            "risk", "requires_reason", "status", "not_used_reason", "simulate", "related",
            "row_shape", "columns", "editable")},
            "value": res["value"], "source_layer": res["source_layer"],
            "source_label": res["source_label"], "scheduled": res["scheduled"],
            "is_default": res["source_layer"] == "code_default"})
    return out


# ── tulis (append-only) ─────────────────────────────────────────────────────
class ConfigWriteError(ValueError):
    """Nilai/scope tidak sah — pesan siap tampil ke user (Bahasa Indonesia)."""


async def set_value(key: str, value: Any, *, scope_type: str = "global", scope_id: str = "",
                    actor: str = "system", actor_id: str = "", reason: str = "",
                    effective_from: str = "", ctx: Optional[Dict[str, Any]] = None,
                    approved_by: str = "") -> Dict[str, Any]:
    """Simpan perubahan sebagai baris BARU (append-only) + proyeksikan ke penyimpanan lama."""
    entry = registry.require(key)
    if entry["status"] != "active":
        raise ConfigWriteError(
            f"'{entry['label']}' tidak dipakai sistem saat ini — {entry['not_used_reason']}")
    if scope_type not in entry["scopes"]:
        raise ConfigWriteError(
            f"'{entry['label']}' tidak bisa diatur pada level '{scope_type}'. "
            f"Level yang didukung: {', '.join(entry['scopes'])}.")
    if scope_type != "global" and not scope_id:
        raise ConfigWriteError(f"Level '{scope_type}' wajib menyebut ID sasaran.")
    if entry["requires_reason"] and not (reason or "").strip():
        raise ConfigWriteError(
            f"'{entry['label']}' berisiko tinggi — alasan perubahan WAJIB diisi.")
    try:
        clean = registry.coerce(entry, value)
    except ValueError as exc:
        raise ConfigWriteError(str(exc)) from exc

    eff = (effective_from or "").strip() or _iso_now()
    if _as_dt(eff) is None:
        raise ConfigWriteError("Tanggal 'berlaku sejak' tidak valid (pakai format ISO).")

    prev = await resolve(key, {**(ctx or {}), **_ctx_for(scope_type, scope_id)})
    row = {
        "id": new_id("cfgv"),
        "key": key,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "value": clean,
        "prev_value": prev["value"],
        "prev_source_layer": prev["source_layer"],
        "effective_from": eff,
        "effective_to": "",
        "reason": (reason or "").strip(),
        "changed_by": actor,
        "changed_by_id": actor_id,
        "approved_by": approved_by,
        "risk": entry["risk"],
        "changed_at": _iso_now(),
        "created_at": _iso_now(),
        "applied_at": "",
    }
    await db[COLL].insert_one(dict(row))
    if _is_due(row, datetime.now(timezone.utc)):
        await _project(entry, scope_type, scope_id, clean, actor)
        await db[COLL].update_one({"id": row["id"]}, {"$set": {"applied_at": _iso_now()}})
        row["applied_at"] = row["changed_at"]
    row.pop("_id", None)
    return row


def _ctx_for(scope_type: str, scope_id: str) -> Dict[str, Any]:
    field = CTX_FIELD.get(scope_type)
    return {field: scope_id} if field and scope_id else {}


async def _project(entry: Dict[str, Any], scope_type: str, scope_id: str,
                   value: Any, actor: str) -> None:
    """Tuliskan nilai ke `system_settings` supaya mesin lama langsung ikut berubah.

    Hanya level `global` & `entity` yang punya padanan di penyimpanan lama. Level
    lain (customer/supplier/product/document) HANYA dibaca lewat resolver — karena itu
    registry hanya mengizinkan level tersebut untuk kunci yang mesinnya sudah memakai resolver.
    """
    if scope_type == "global":
        target_scope = entry["legacy_scope"]
    elif scope_type == "entity":
        if entry["legacy_scope"] != "global":
            # FASE E-4 (E4.5) — dokumen setelan operasional (`hr`/`uom`/`lot`/
            # `receiving`/`makloon`) tidak punya varian per badan usaha di
            # penyimpanan lama, jadi TIDAK ada yang bisa diproyeksikan. Override
            # badan usaha tetap berlaku karena pembacanya memakai
            # `entity_overlay()` di atas nilai globalnya.
            return
        target_scope = scope_id
    else:
        return
    await db.system_settings.update_one(
        {"scope": target_scope},
        {"$set": {entry["legacy_path"]: value, "updated_at": _iso_now(), "updated_by": actor},
         "$setOnInsert": {"id": new_id("set"), "scope": target_scope, "created_at": _iso_now()}},
        upsert=True,
    )


async def clear_layer(key: str, *, scope_type: str, scope_id: str = "",
                      actor: str = "system", actor_id: str = "",
                      reason: str = "") -> Dict[str, Any]:
    """FASE E-4 (E4.6) — KOSONGKAN satu lapisan: "Kembalikan ke global".

    Bedanya dengan `values/reset`: `reset` MENULIS nilai bawaan kode pada lapisan ini
    (jadi lapisannya tetap ada dan tetap menang), sementara fungsi ini MENCABUT
    lapisannya sehingga nilai kembali diwarisi dari lapisan yang lebih umum
    (badan usaha → global → bawaan sistem). Itulah yang sebenarnya diminta pengguna
    ketika menekan "kembalikan ke global"; membedakannya mencegah nilai global yang
    sudah disesuaikan pemilik tertimpa angka bawaan kode.

    Tetap append-only: yang ditulis adalah baris NISAN (`cleared: True`), jadi
    riwayat "pernah diatur X lalu dicabut" tidak hilang.
    """
    entry = registry.require(key)
    if scope_type not in WRITABLE_LAYERS:
        raise ConfigWriteError(f"Lapisan '{scope_type}' tidak bisa dikosongkan.")
    if scope_type == "global":
        raise ConfigWriteError(
            "Lapisan Global adalah lapisan terluar — tidak ada 'global' di atasnya. "
            "Pakai 'Kembalikan ke bawaan sistem' bila ingin nilai awal kode.")
    if not scope_id:
        raise ConfigWriteError(f"Lapisan '{scope_type}' wajib menyebut ID sasaran.")

    prev = await resolve(key, _ctx_for(scope_type, scope_id))
    row = {
        "id": new_id("cfgv"), "key": key,
        "scope_type": scope_type, "scope_id": scope_id,
        "value": None, "cleared": True,
        "prev_value": prev["value"], "prev_source_layer": prev["source_layer"],
        "effective_from": _iso_now(), "effective_to": "",
        "reason": (reason or "").strip() or "Kembalikan ke nilai global",
        "changed_by": actor, "changed_by_id": actor_id, "approved_by": "",
        "risk": entry["risk"], "changed_at": _iso_now(), "created_at": _iso_now(),
        "applied_at": _iso_now(),
    }
    await db[COLL].insert_one(dict(row))
    # Bersihkan juga proyeksi di penyimpanan lama, kalau ada — kalau tidak, mesin
    # lama akan tetap membaca angka yang sudah dicabut (bug senyap).
    if scope_type == "entity" and entry["legacy_scope"] == "global":
        await db.system_settings.update_one(
            {"scope": scope_id}, {"$unset": {entry["legacy_path"]: ""}})
    row.pop("_id", None)
    after = await resolve(key, _ctx_for(scope_type, scope_id))
    row["value_now"] = after["value"]
    row["source_layer_now"] = after["source_layer"]
    row["source_label_now"] = after["source_label"]
    return row


def _put(doc: Dict[str, Any], path: str, value: Any) -> None:
    """Tulis nilai ke dot-path (membuat sub-dict bila perlu)."""
    parts = path.split(".")
    cur = doc
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


async def entity_overlay(legacy_scope: str, entity_id: str) -> Dict[str, Any]:
    """FASE E-4 (E4.5) — HANYA nilai yang benar-benar ditimpa satu badan usaha.

    Dokumen setelan operasional (`system_settings{scope:"hr"|"uom"|"lot"|"receiving"|
    "makloon"}`) dulu **hanya bisa global**: BPJS, presisi satuan, ketatnya nomor lot,
    toleransi makloon — satu nilai memaksa seluruh grup. Padahal PT Kain Suka Cita
    (PKP, karyawan tetap) dan CV Kanda Suka (non-PKP, borongan) memang berbeda.

    Fungsi ini mengembalikan dokumen bersarang berisi **hanya** kunci yang lapisan
    pemenangnya = badan usaha. Sengaja tidak mengembalikan seluruh nilai efektif:
    dengan begitu pemanggil cukup menimpa dokumen globalnya (`deep_merge`) dan
    perilaku lama tetap identik bila belum ada override sama sekali — nol risiko
    regresi untuk badan usaha yang tidak mengatur apa pun.
    """
    ent = (entity_id or "").strip()
    if not ent or ent == "all":
        return {}
    entries = [e for e in registry.all_entries()
               if e.get("legacy_scope") == legacy_scope and "entity" in e.get("scopes", [])]
    if not entries:
        return {}
    keys = [e["key"] for e in entries]
    ctx = {"entity_id": ent}
    pre: Dict[str, Any] = {"rows": await _stored_rows(keys, ctx)}
    pre[f"legacy:{legacy_scope}"] = await _legacy_doc(legacy_scope)
    pre[f"legacy:{ent}"] = await _legacy_doc(ent)
    at = datetime.now(timezone.utc)
    out: Dict[str, Any] = {}
    for e in entries:
        res = await resolve(e["key"], ctx, at=at, preloaded=pre)
        if res["source_layer"] in ("entity", "legacy_entity"):
            _put(out, e["legacy_path"], res["value"])
    return out


async def apply_due_values() -> Dict[str, int]:
    """Terapkan perubahan berjadwal yang sudah jatuh tempo (idempotent).

    Dipanggil saat membaca Pusat Pengaturan dan oleh scheduler, sehingga nilai
    "berlaku sejak" otomatis aktif tanpa intervensi manual.
    """
    now = datetime.now(timezone.utc)
    applied = 0
    cur = db[COLL].find({"applied_at": ""}, {"_id": 0})
    pending: List[Dict[str, Any]] = [r async for r in cur if _is_due(r, now)]
    pending.sort(key=lambda r: (str(r.get("effective_from")), str(r.get("created_at"))))
    for row in pending:
        entry = registry.get(row["key"])
        if not entry:
            continue
        await _project(entry, row["scope_type"], row.get("scope_id", ""),
                       row["value"], row.get("changed_by", "scheduler"))
        await db[COLL].update_one({"id": row["id"]}, {"$set": {"applied_at": _iso_now()}})
        applied += 1
    return {"applied": applied, "pending": len(pending) - applied}


async def history(key: str = "", scope_type: str = "", scope_id: str = "",
                  limit: int = 100) -> List[Dict[str, Any]]:
    """Riwayat perubahan (terbaru dulu): siapa, kapan, dari→ke, alasan."""
    q: Dict[str, Any] = {}
    if key:
        q["key"] = key
    if scope_type:
        q["scope_type"] = scope_type
    if scope_id:
        q["scope_id"] = scope_id
    rows = await db[COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(int(limit))
    for r in rows:
        e = registry.get(r["key"])
        r["label"] = e["label"] if e else r["key"]
        r["group"] = e["group"] if e else ""
        r["unit"] = e["unit"] if e else ""
        r["scheduled"] = not _is_due(r, datetime.now(timezone.utc))
    return rows


async def ensure_indexes() -> None:
    """Index minimal untuk pembacaan resolver (idempotent, non-fatal)."""
    try:
        await db[COLL].create_index([("key", 1), ("scope_type", 1), ("scope_id", 1),
                                     ("effective_from", 1)], name="cfgv_lookup", background=True)
        await db[COLL].create_index([("applied_at", 1)], name="cfgv_pending", background=True)
        await db[COLL].create_index([("created_at", -1)], name="cfgv_recent", background=True)
    except Exception:  # noqa: BLE001 — index bentrok tidak boleh menggagalkan request
        pass
