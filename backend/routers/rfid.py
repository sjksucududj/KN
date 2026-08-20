"""RFID router (Fase 5 — SIMULATOR).

Endpoint prefix /api. Perizinan:
- GET (baca)            → wms:view
- encode/retire/scan    → wms:scan  (warehouse/manager/admin)
- device write & seed   → role admin (infra)
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from dependencies import require_permission, require_role, audit
from entity_scope import entity_ctx, resolve_scope_ids
import services.rfid_service as rfid

router = APIRouter(prefix="/api")


# ─── Payloads ────────────────────────────────────────────────────────────────
class EncodePayload(BaseModel):
    roll_id: str
    epc: Optional[str] = None


class AutoEncodePayload(BaseModel):
    warehouse_id: Optional[str] = None


class DevicePayload(BaseModel):
    code: Optional[str] = None
    name: str
    type: str                      # gate | fixed_reader | handheld
    direction: Optional[str] = None  # in | out (gate saja)
    warehouse_id: str
    location: Optional[str] = None
    status: Optional[str] = None


class DevicePatch(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    direction: Optional[str] = None
    type: Optional[str] = None


class GateSimPayload(BaseModel):
    device_id: str
    roll_id: str


class ReaderScanPayload(BaseModel):
    device_id: str


# ─── Summary ─────────────────────────────────────────────────────────────────
@router.get("/rfid/summary")
async def get_summary(request: Request, warehouse_id: Optional[str] = None,
                      entity_id: Optional[str] = None) -> Dict[str, Any]:
    await require_permission(request, "wms", "view")
    ctx = await entity_ctx(request)
    scope = resolve_scope_ids(ctx, entity_id)
    return await rfid.rfid_summary(scope, warehouse_id)


# ─── Tags ────────────────────────────────────────────────────────────────────
@router.get("/rfid/tags")
async def get_tags(request: Request, warehouse_id: Optional[str] = None,
                   status: Optional[str] = None, entity_id: Optional[str] = None) -> Dict[str, Any]:
    await require_permission(request, "wms", "view")
    ctx = await entity_ctx(request)
    scope = resolve_scope_ids(ctx, entity_id)
    tags = await rfid.list_tags(scope, warehouse_id, status)
    return {"count": len(tags), "tags": tags}


@router.get("/rfid/untagged-rolls")
async def get_untagged(request: Request, warehouse_id: Optional[str] = None,
                       entity_id: Optional[str] = None) -> Dict[str, Any]:
    await require_permission(request, "wms", "view")
    ctx = await entity_ctx(request)
    scope = resolve_scope_ids(ctx, entity_id)
    rolls = await rfid.untagged_rolls(scope, warehouse_id)
    return {"count": len(rolls), "rolls": rolls}


@router.post("/rfid/tags/encode")
async def post_encode(payload: EncodePayload, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "wms", "scan")
    ctx = await entity_ctx(request)
    scope = resolve_scope_ids(ctx, None)
    tag = await rfid.encode_tag(payload.roll_id, scope, payload.epc, actor["name"])
    await audit(actor["name"], "rfid_tag_encoded", "rfid_tag", tag["id"],
                {"epc": tag["epc"], "roll_id": payload.roll_id})
    return tag


@router.post("/rfid/tags/auto-encode")
async def post_auto_encode(payload: AutoEncodePayload, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "wms", "scan")
    ctx = await entity_ctx(request)
    scope = resolve_scope_ids(ctx, None)
    res = await rfid.auto_encode(scope, payload.warehouse_id, actor["name"])
    await audit(actor["name"], "rfid_auto_encode", "rfid_tag", "batch", {"encoded": res["encoded"]})
    return res


@router.delete("/rfid/tags/{tag_id}")
async def delete_tag(tag_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "wms", "scan")
    ctx = await entity_ctx(request)
    scope = resolve_scope_ids(ctx, None)
    res = await rfid.retire_tag(tag_id, scope)
    await audit(actor["name"], "rfid_tag_retired", "rfid_tag", tag_id, {})
    return res


# ─── Devices ─────────────────────────────────────────────────────────────────
@router.get("/rfid/devices")
async def get_devices(request: Request, warehouse_id: Optional[str] = None) -> Dict[str, Any]:
    await require_permission(request, "wms", "view")
    devs = await rfid.list_devices(warehouse_id)
    return {"count": len(devs), "devices": devs}


@router.post("/rfid/devices")
async def post_device(payload: DevicePayload, request: Request) -> Dict[str, Any]:
    actor = await require_role(request, ["admin"])
    dev = await rfid.create_device(payload.model_dump(), actor["name"])
    await audit(actor["name"], "rfid_device_created", "rfid_device", dev["id"], {"code": dev["code"]})
    return dev


@router.patch("/rfid/devices/{device_id}")
async def patch_device(device_id: str, payload: DevicePatch, request: Request) -> Dict[str, Any]:
    actor = await require_role(request, ["admin"])
    dev = await rfid.update_device(device_id, payload.model_dump(exclude_none=True))
    await audit(actor["name"], "rfid_device_updated", "rfid_device", device_id, {})
    return dev


@router.delete("/rfid/devices/{device_id}")
async def del_device(device_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_role(request, ["admin"])
    res = await rfid.delete_device(device_id)
    await audit(actor["name"], "rfid_device_deleted", "rfid_device", device_id, {})
    return res


@router.post("/rfid/devices/seed-defaults")
async def post_seed_devices(request: Request) -> Dict[str, Any]:
    actor = await require_role(request, ["admin"])
    res = await rfid.seed_default_devices(actor["name"])
    await audit(actor["name"], "rfid_devices_seeded", "rfid_device", "batch", {"created": res["created"]})
    return res


# ─── Reads / Gate / Scan ─────────────────────────────────────────────────────
@router.get("/rfid/reads")
async def get_reads(request: Request, device_id: Optional[str] = None, result: Optional[str] = None,
                    read_type: Optional[str] = None, warehouse_id: Optional[str] = None,
                    limit: int = 100) -> Dict[str, Any]:
    await require_permission(request, "wms", "view")
    reads = await rfid.list_reads(device_id, result, read_type, warehouse_id, min(limit, 300))
    return {"count": len(reads), "reads": reads}


@router.post("/rfid/gate/simulate")
async def post_gate_simulate(payload: GateSimPayload, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "wms", "scan")
    ctx = await entity_ctx(request)
    scope = resolve_scope_ids(ctx, None)
    read = await rfid.gate_simulate(payload.device_id, payload.roll_id, scope)
    if read.get("result") == "red":
        await audit(actor["name"], "rfid_gate_alert", "rfid_read", read["id"],
                    {"reason": read.get("reason"), "roll_id": payload.roll_id})
    return read


@router.post("/rfid/reader/scan")
async def post_reader_scan(payload: ReaderScanPayload, request: Request) -> Dict[str, Any]:
    await require_permission(request, "wms", "scan")
    ctx = await entity_ctx(request)
    scope = resolve_scope_ids(ctx, None)
    return await rfid.reader_scan(payload.device_id, scope)


# ─── Locations ───────────────────────────────────────────────────────────────
@router.get("/rfid/locations")
async def get_locations(request: Request, warehouse_id: Optional[str] = None,
                        entity_id: Optional[str] = None) -> Dict[str, Any]:
    await require_permission(request, "wms", "view")
    ctx = await entity_ctx(request)
    scope = resolve_scope_ids(ctx, entity_id)
    items = await rfid.rfid_locations(scope, warehouse_id)
    return {"count": len(items), "items": items}
