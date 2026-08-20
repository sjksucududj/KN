"""FASE G-0 — Router Pusat Pengaturan (Config Center).

Satu pintu API untuk seluruh konfigurasi sistem:
  GET  /api/config/registry        — katalog setting + grup (sumber UI generik)
  GET  /api/config/effective       — nilai efektif per grup / hasil pencarian
  GET  /api/config/explain         — "kenapa nilainya begini?" (jejak lapisan)
  POST /api/config/simulate        — "coba dulu" sebelum menyimpan
  PUT  /api/config/values          — simpan (append-only + proyeksi ke mesin lama)
  GET  /api/config/history         — riwayat siapa-ubah-apa-kapan-kenapa
  GET  /api/config/health          — kesehatan wiring (tidak ada tombol palsu)
  POST /api/config/impact-preview  — DAFTAR DAMPAK koreksi harga master
  POST /api/config/impact-apply    — terapkan HANYA ke dokumen yang dicentang
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

import config_registry as registry
from dependencies import audit, current_user, permission_matrix, require_permission
from schemas_config import (
    ConfigBulkValuesIn, ConfigSimulateIn, ConfigValueIn, ImpactApplyIn, ImpactPreviewIn,
)
from services import config_health, config_simulator
from services import config_resolver as resolver

router = APIRouter(prefix="/api/config", tags=["config"])


def _ctx(model: Any) -> Dict[str, Any]:
    return model.model_dump() if model else {}


async def _allowed(user: Dict[str, Any]) -> Dict[str, List[str]]:
    """Izin efektif user saat ini (matriks bisa di-override lewat permission_settings)."""
    matrix = await permission_matrix()
    return matrix.get(user.get("role") or "", {}) or {}


def _may(perms: Dict[str, List[str]], module: str, action: str) -> bool:
    actions = perms.get(module) or []
    return action in actions or "*" in actions


def _may_edit(entry: Dict[str, Any], user: Dict[str, Any], perms: Dict[str, List[str]]) -> bool:
    """Apakah user BERWENANG mengubah setting ini (izin saja, tanpa melihat status).

    Aturannya sengaja MENYALIN wewenang endpoint konfigurasi lama yang dihapus
    di FASE G-0, supaya penggabungan ke satu editor tidak diam-diam mencabut
    (atau menambah) hak siapa pun:
      - admin              → selalu boleh (seperti sebelumnya);
      - `roles`            → peran yang dulu diizinkan endpoint berbasis role
                             (mis. manager pada PUT /lots/settings);
      - `permission`       → izin domain (mis. hr.manage_payroll, uom.update).
    """
    role = user.get("role") or ""
    if role == "admin":
        return True
    if role in (entry.get("roles") or []):
        return True
    module, action = (entry.get("permission") or ["settings", "manage"])[:2]
    if not _may(perms, module, action):
        return False
    # Setting yang memakai izin bawaan `settings.manage` tetap menghormati
    # `owner_role` — perilaku ini sudah ada sebelum FASE G-0 dan dipertahankan.
    if module == "settings" and entry.get("owner_role") == "admin":
        return False
    return True


def _perm_error(entry: Dict[str, Any]) -> str:
    module, action = (entry.get("permission") or ["settings", "manage"])[:2]
    return f"'{entry['label']}' tidak bisa Anda ubah (butuh izin {module}.{action})"


def _can_edit(entry: Dict[str, Any], user: Dict[str, Any], perms: Dict[str, List[str]]) -> bool:
    """Boleh-tidaknya tombol Simpan aktif di UI.

    Yang terlihat bisa diklik = yang benar-benar diizinkan server. Setting
    berstatus `not_used` sengaja tidak bisa diubah siapa pun; alasannya
    ditampilkan pada kartunya sendiri.
    """
    if entry.get("status") != "active":
        return False
    return _may_edit(entry, user, perms)


@router.get("/registry")
async def read_registry(request: Request, group: str = "", q: str = "") -> Dict[str, Any]:
    """Katalog setting (label awam, penjelasan, dampak, tipe, batas, scope, consumer)."""
    user = await current_user(request)
    perms = await _allowed(user)
    entries = registry.search(q) if q else (
        registry.by_group(group) if group else registry.all_entries())
    entries = [{**e, "can_edit": _can_edit(e, user, perms)} for e in entries]
    return {"groups": registry.groups(), "entries": entries, "total": len(entries),
            "scope_levels": registry.SCOPE_LEVELS, "simulators": config_simulator.catalog(),
            # `caps` membuat UI jujur: tab/tombol yang tidak diizinkan server
            # tidak ditampilkan sama sekali (bukan ditampilkan lalu ditolak 403).
            "caps": {
                "settings_manage": _may(perms, "settings", "manage"),
                "impact_apply": _may(perms, "product", "update"),
                "editable_count": sum(1 for e in entries if e["can_edit"]),
            }}


@router.get("/effective")
async def read_effective(request: Request, group: str = "", q: str = "",
                         entity_id: str = "", customer_id: str = "", supplier_id: str = "",
                         product_id: str = "", document_id: str = "") -> Dict[str, Any]:
    """Nilai efektif + lapisan asal untuk satu grup (atau hasil pencarian)."""
    user = await current_user(request)
    perms = await _allowed(user)
    await resolver.apply_due_values()      # aktifkan perubahan berjadwal yang jatuh tempo
    ctx = {"entity_id": entity_id, "customer_id": customer_id, "supplier_id": supplier_id,
           "product_id": product_id, "document_id": document_id}
    items = await resolver.resolve_group(group or None, ctx, term=q)
    for it in items:
        it["can_edit"] = _can_edit(registry.get(it["key"]) or it, user, perms)
    return {"groups": registry.groups(), "context": ctx, "items": items, "total": len(items)}


@router.get("/explain")
async def explain(request: Request, key: str, entity_id: str = "", customer_id: str = "",
                  supplier_id: str = "", product_id: str = "",
                  document_id: str = "") -> Dict[str, Any]:
    """Jejak lapisan: default kode → global → entitas → pelanggan → … dan mana yang menang."""
    await current_user(request)
    entry = registry.get(key)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' tidak ada di registry")
    ctx = {"entity_id": entity_id, "customer_id": customer_id, "supplier_id": supplier_id,
           "product_id": product_id, "document_id": document_id}
    res = await resolver.resolve(key, ctx)
    return {"entry": entry, "context": ctx, **res,
            "layer_order": resolver.LAYER_ORDER,
            "wiring": config_health.check_entry(entry)}


@router.post("/simulate")
async def simulate(payload: ConfigSimulateIn, request: Request) -> Dict[str, Any]:
    """"Coba dulu": jalankan aturan memakai nilai efektif (+ nilai hipotetis) tanpa menyimpan."""
    await current_user(request)
    sim_id = payload.simulator
    if not sim_id:
        entry = registry.get(payload.key)
        if not entry:
            raise HTTPException(status_code=404, detail="Sebutkan `simulator` atau `key` yang sah")
        sim_id = entry.get("simulate") or ""
    if not sim_id:
        raise HTTPException(status_code=400,
                            detail="Setting ini belum punya simulator — lihat 'Kenapa nilainya begini?'")
    try:
        sim = config_simulator.get(sim_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    ctx = _ctx(payload.ctx)
    values: Dict[str, Any] = {}
    trail: List[Dict[str, Any]] = []
    for key in sim["needs"]:
        if key in payload.overrides:
            res = await resolver.resolve(key, ctx, hypothetical=payload.overrides[key])
        else:
            res = await resolver.resolve(key, ctx)
        values[key] = res["value"]
        e = registry.get(key)
        trail.append({"key": key, "label": (e or {}).get("label", key), "value": res["value"],
                      "source_layer": res["source_layer"], "source_label": res["source_label"],
                      "hypothetical": key in payload.overrides})
    out = config_simulator.run(sim_id, values, payload.sample)
    return {**out, "resolved": trail, "context": ctx}


@router.put("/values")
async def write_values(payload: ConfigBulkValuesIn, request: Request) -> Dict[str, Any]:
    """Simpan perubahan (bisa beberapa sekaligus). Append-only + langsung aktif di mesin."""
    actor = await current_user(request)
    perms = await _allowed(actor)
    if not payload.items:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan yang dikirim")
    saved: List[Dict[str, Any]] = []
    for item in payload.items:
        entry = registry.get(item.key)
        if not entry:
            raise HTTPException(status_code=404,
                                detail=f"Setting '{item.key}' tidak ada di registry")
        # Status `not_used` sengaja TIDAK ditangani di sini: resolver yang menolak
        # dengan pesan berisi ALASAN kenapa setting itu tidak dipakai (lebih
        # berguna bagi user daripada sekadar "tidak berwenang").
        if not _may_edit(entry, actor, perms):
            raise HTTPException(status_code=403, detail=_perm_error(entry))
        try:
            row = await resolver.set_value(
                item.key, item.value, scope_type=item.scope_type, scope_id=item.scope_id,
                actor=actor.get("name", ""), actor_id=actor.get("id", ""),
                reason=item.reason, effective_from=item.effective_from, ctx=_ctx(item.ctx))
        except resolver.ConfigWriteError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await audit(actor.get("name", ""), "config_value_changed", "config_values", row["id"],
                    {"key": item.key, "scope": f"{item.scope_type}:{item.scope_id or '-'}",
                     "from": row["prev_value"], "to": row["value"],
                     "effective_from": row["effective_from"]}, reason=item.reason)
        saved.append(row)
    return {"saved": saved, "count": len(saved)}


@router.post("/values/reset")
async def reset_value(payload: ConfigValueIn, request: Request) -> Dict[str, Any]:
    """Kembalikan sebuah setting ke nilai default sistem (tetap tercatat sebagai perubahan)."""
    actor = await current_user(request)
    perms = await _allowed(actor)
    entry = registry.get(payload.key)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Setting '{payload.key}' tidak ada di registry")
    if not _may_edit(entry, actor, perms):
        raise HTTPException(status_code=403, detail=_perm_error(entry))
    try:
        row = await resolver.set_value(
            payload.key, entry["default"], scope_type=payload.scope_type,
            scope_id=payload.scope_id, actor=actor.get("name", ""), actor_id=actor.get("id", ""),
            reason=payload.reason or "Kembalikan ke default sistem")
    except resolver.ConfigWriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor.get("name", ""), "config_value_reset", "config_values", row["id"],
                {"key": payload.key, "to": row["value"]}, reason=row["reason"])
    return row


@router.post("/values/clear")
async def clear_value_layer(payload: ConfigValueIn, request: Request) -> Dict[str, Any]:
    """FASE E-4 (E4.6) — cabut nilai pada satu lapisan → kembali mewarisi lapisan di atasnya.

    Dipakai tombol "Kembalikan ke global" di Pusat Pengaturan. Berbeda dari
    `/values/reset` yang menulis nilai bawaan KODE pada lapisan ini.
    """
    actor = await current_user(request)
    perms = await _allowed(actor)
    entry = registry.get(payload.key)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Setting '{payload.key}' tidak ada di registry")
    if not _may_edit(entry, actor, perms):
        raise HTTPException(status_code=403, detail=_perm_error(entry))
    try:
        row = await resolver.clear_layer(
            payload.key, scope_type=payload.scope_type, scope_id=payload.scope_id,
            actor=actor.get("name", ""), actor_id=actor.get("id", ""),
            reason=payload.reason or "")
    except resolver.ConfigWriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor.get("name", ""), "config_value_cleared", "config_values", row["id"],
                {"key": payload.key, "scope": f"{payload.scope_type}:{payload.scope_id or '-'}",
                 "from": row["prev_value"], "now": row.get("value_now"),
                 "now_source": row.get("source_label_now")}, reason=row["reason"])
    return row


@router.get("/history")
async def read_history(request: Request, key: str = "", scope_type: str = "",
                       scope_id: str = "", limit: int = 100) -> Dict[str, Any]:
    """Riwayat perubahan konfigurasi (append-only, terbaru dulu)."""
    await current_user(request)
    rows = await resolver.history(key, scope_type, scope_id, min(max(int(limit), 1), 500))
    return {"rows": rows, "total": len(rows)}


@router.get("/health")
async def read_health(request: Request) -> Dict[str, Any]:
    """Kesehatan wiring: setiap setting aktif WAJIB punya kode pembaca yang nyata."""
    await require_permission(request, "settings", "view")
    rep = config_health.report()
    pending = await resolver.apply_due_values()
    return {**rep, "scheduled_applied": pending}


@router.post("/impact-preview")
async def impact_preview(payload: ImpactPreviewIn, request: Request) -> Dict[str, Any]:
    """DAFTAR DAMPAK — dokumen terbuka mana saja yang akan berubah bila harga master dikoreksi."""
    await require_permission(request, "product", "view")
    from services import config_impact_service as impact
    try:
        return await impact.preview(payload.product_id, payload.new_price,
                                    payload.current_doc_id, payload.entity_id)
    except impact.ImpactError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/impact-apply")
async def impact_apply(payload: ImpactApplyIn, request: Request) -> Dict[str, Any]:
    """Terapkan koreksi harga master HANYA ke dokumen yang dicentang (INV-CFG-07)."""
    actor = await require_permission(request, "product", "update")
    from services import config_impact_service as impact
    try:
        return await impact.apply(payload.product_id, payload.new_price, payload.doc_ids,
                                  reason=payload.reason, actor=actor.get("name", ""),
                                  entity_id=payload.entity_id,
                                  update_master=payload.update_master)
    except impact.ImpactError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/simulators")
async def list_simulators(request: Request) -> Dict[str, Any]:
    """Daftar simulator yang tersedia + input yang diminta."""
    await current_user(request)
    return {"simulators": config_simulator.catalog()}
