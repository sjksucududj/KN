"""delivery_service.py — Pengiriman dokumen via WhatsApp (mode simulasi default) +
riwayat pengiriman + pengaturan integrasi.
"""
from __future__ import annotations
import re
from typing import Any, Dict, Optional

from db import db
from core_utils import new_id, now_iso, safe_doc
from services import pdf_service as pdfsvc
from services.pdf_resolvers import DOC_REGISTRY
from services.esign_service import public_base, doc_number
from services.wa import get_wa_provider, available_providers

SETTINGS_ID = "whatsapp"


def normalize_phone(raw: str, default_cc: str = "62") -> str:
    p = re.sub(r"[^\d+]", "", raw or "")
    if p.startswith("+"):
        p = p[1:]
    if p.startswith("0"):
        p = default_cc + p[1:]
    elif p and not p.startswith(default_cc) and len(p) <= 11:
        p = default_cc + p
    return p


async def get_settings() -> Dict[str, Any]:
    row = await db.integration_settings.find_one({"id": SETTINGS_ID}, {"_id": 0}) or {}
    return {
        "id": SETTINGS_ID,
        "provider": row.get("provider", "simulated"),
        "simulate": row.get("simulate", True),
        "enabled": row.get("enabled", True),
        "phone_number_id": row.get("phone_number_id", ""),
        "default_country_code": row.get("default_country_code", "62"),
        "sender_label": row.get("sender_label", "Kain Nusantara"),
        "has_token": bool(row.get("access_token")),
        "available_providers": available_providers(),
    }


async def save_settings(data: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    upd: Dict[str, Any] = {}
    for k in ["provider", "simulate", "enabled", "phone_number_id", "default_country_code", "sender_label"]:
        if data.get(k) is not None:
            upd[k] = data[k]
    if data.get("access_token"):  # hanya update bila diisi (jangan timpa dengan kosong)
        upd["access_token"] = data["access_token"]
    await db.integration_settings.update_one(
        {"id": SETTINGS_ID},
        {"$set": {"id": SETTINGS_ID, **upd, "updated_by": actor, "updated_at": now_iso()}},
        upsert=True,
    )
    return await get_settings()


async def send_whatsapp(doc_type: str, source_id: str, entity_id: Optional[str],
                        to: str, caption: str, message: str, actor: str,
                        trigger: Optional[str] = None, auto: bool = False,
                        rule_id: Optional[str] = None) -> Dict[str, Any]:
    reg = DOC_REGISTRY.get(doc_type)
    if not reg:
        raise ValueError("Jenis dokumen tidak dikenal")
    if not (to or "").strip():
        raise ValueError("Nomor WhatsApp tujuan wajib diisi")
    settings = await get_settings()
    if not settings["enabled"]:
        raise ValueError("Integrasi WhatsApp dinonaktifkan")

    # Render PDF sebagai lampiran (validasi pipeline; di mode simulasi tak dikirim nyata).
    try:
        pdf, _ctype, built = await pdfsvc.render_document(
            doc_type, source_id, entity_id, fmt="pdf", public_base=public_base())
    except LookupError as exc:
        raise LookupError(str(exc))
    number = doc_number(built["source"]) or source_id
    eid = entity_id or built["source"].get("entity_id")
    phone = normalize_phone(to, settings["default_country_code"])

    provider_name = "simulated" if settings["simulate"] else settings["provider"]
    prov_settings = dict(settings)
    # sertakan token asli untuk provider nyata
    row = await db.integration_settings.find_one({"id": SETTINGS_ID}, {"_id": 0}) or {}
    prov_settings["access_token"] = row.get("access_token", "")
    provider = get_wa_provider(provider_name, prov_settings)

    doc_meta = {"doc_type": doc_type, "number": number, "label": reg["label"],
                "filename": f"{doc_type}-{number}.pdf", "size": len(pdf)}
    cap = caption or f"{reg['label']} {number}"
    # Templating sederhana untuk caption (dipakai aturan auto-kirim & manual).
    cap = (cap.replace("{number}", str(number))
              .replace("{label}", reg["label"])
              .replace("{doc_type}", doc_type))
    res = await provider.send_document(phone, doc_meta, pdf, cap)

    rec = {
        "id": new_id("wadlv"), "doc_type": doc_type, "source_id": source_id, "entity_id": eid,
        "channel": "whatsapp", "to": phone, "caption": cap, "message": message or "",
        "status": res.get("status", "sent"), "provider": res.get("provider", provider_name),
        "simulated": res.get("simulated", provider_name == "simulated"),
        "message_id": res.get("message_id"), "error": res.get("error"),
        "attachment_name": doc_meta["filename"], "attachment_size": doc_meta["size"],
        "trigger": trigger, "auto": bool(auto), "rule_id": rule_id,
        "sent_at": now_iso(), "created_at": now_iso(), "sent_by": actor,
    }
    await db.document_deliveries.insert_one(rec)
    return safe_doc(rec)


async def list_deliveries(doc_type: str, source_id: str):
    rows = await db.document_deliveries.find(
        {"doc_type": doc_type, "source_id": source_id},
        {"_id": 0}).sort("created_at", -1).to_list(100)
    return safe_doc(rows)


# ─── Recipient resolver ──────────────────────────────────────────────────────
# Pemetaan jenis dokumen → lawan-bicara (untuk auto-fill nomor & auto-kirim).
_CUSTOMER_DOCS = {"sales_order", "quotation", "ar_receipt", "sales_return", "special_order"}
_SUPPLIER_DOCS = {"purchase_order", "vendor_bill", "purchase_return"}
_MAKLOON_DOCS = {"makloon_spk"}


async def _phone_from_ref(collection: str, ref_id: Optional[str]) -> tuple[str, str]:
    if not ref_id:
        return "", ""
    try:
        row = await db[collection].find_one({"id": ref_id}, {"_id": 0}) or {}
    except Exception:  # noqa: BLE001
        return "", ""
    phone = row.get("phone") or row.get("whatsapp") or ""
    if not phone:
        contacts = row.get("contacts") or []
        primary = next((c for c in contacts if c.get("is_primary") and c.get("phone")), None)
        anyc = next((c for c in contacts if c.get("phone")), None)
        phone = (primary or anyc or {}).get("phone", "")
    name = row.get("name") or row.get("legal_name") or row.get("company_name") or ""
    return phone, name


async def resolve_recipient(doc_type: str, source_id: str,
                            entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Cari nomor WA lawan-bicara dokumen (customer/supplier/makloon)."""
    reg = DOC_REGISTRY.get(doc_type)
    if not reg:
        return {"phone": "", "name": "", "mode": None}
    src = await db[reg["collection"]].find_one({"id": source_id}, {"_id": 0}) or {}
    phone = (src.get("customer_phone") or src.get("supplier_phone")
             or src.get("vendor_phone") or src.get("phone") or "")
    name = (src.get("customer_name") or src.get("supplier_name")
            or src.get("vendor_name") or src.get("makloon_name") or "")
    mode = None
    if doc_type in _CUSTOMER_DOCS:
        mode = "customer"
        if not phone:
            phone, nm = await _phone_from_ref("customers", src.get("customer_id"))
            name = name or nm
    elif doc_type in _SUPPLIER_DOCS:
        mode = "supplier"
        if not phone:
            phone, nm = await _phone_from_ref("suppliers", src.get("supplier_id"))
            name = name or nm
    elif doc_type in _MAKLOON_DOCS:
        mode = "supplier"
        if not phone:
            phone, nm = await _phone_from_ref("makloons", src.get("makloon_id"))
            name = name or nm
    settings = await get_settings()
    return {"phone": normalize_phone(phone, settings["default_country_code"]) if phone else "",
            "raw_phone": phone, "name": name, "mode": mode}


# ─── Auto-send rules (aturan kirim otomatis) ─────────────────────────────────
RULES_COLL = "wa_auto_rules"
_RULE_FIELDS = ("doc_type", "event", "recipient_mode", "fixed_number",
                "caption_template", "enabled")


async def list_rules() -> list:
    rows = await db[RULES_COLL].find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return safe_doc(rows)


async def create_rule(data: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    if not data.get("doc_type"):
        raise ValueError("Jenis dokumen wajib dipilih")
    if not data.get("event"):
        raise ValueError("Pemicu (event) wajib dipilih")
    if data.get("doc_type") not in DOC_REGISTRY:
        raise ValueError("Jenis dokumen tidak dikenal")
    mode = data.get("recipient_mode", "customer")
    if mode == "fixed" and not (data.get("fixed_number") or "").strip():
        raise ValueError("Nomor tetap wajib diisi untuk mode 'nomor tetap'")
    rule = {
        "id": new_id("warule"),
        "doc_type": data["doc_type"], "event": data["event"],
        "recipient_mode": mode, "fixed_number": (data.get("fixed_number") or "").strip(),
        "caption_template": (data.get("caption_template") or "").strip(),
        "enabled": bool(data.get("enabled", True)),
        "created_by": actor, "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db[RULES_COLL].insert_one(rule)
    return safe_doc(rule)


async def update_rule(rule_id: str, data: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    upd: Dict[str, Any] = {}
    for k in _RULE_FIELDS:
        if data.get(k) is not None:
            upd[k] = data[k]
    if "fixed_number" in upd:
        upd["fixed_number"] = (upd["fixed_number"] or "").strip()
    if "caption_template" in upd:
        upd["caption_template"] = (upd["caption_template"] or "").strip()
    if "enabled" in upd:
        upd["enabled"] = bool(upd["enabled"])
    upd["updated_at"] = now_iso()
    upd["updated_by"] = actor
    res = await db[RULES_COLL].update_one({"id": rule_id}, {"$set": upd})
    if res.matched_count == 0:
        raise LookupError("Aturan tidak ditemukan")
    row = await db[RULES_COLL].find_one({"id": rule_id}, {"_id": 0})
    return safe_doc(row)


async def delete_rule(rule_id: str) -> Dict[str, Any]:
    res = await db[RULES_COLL].delete_one({"id": rule_id})
    if res.deleted_count == 0:
        raise LookupError("Aturan tidak ditemukan")
    return {"deleted": True, "id": rule_id}


async def dispatch_event(doc_type: str, source_id: str, event: str,
                         entity_id: Optional[str] = None,
                         actor: str = "system") -> Dict[str, Any]:
    """Jalankan aturan auto-kirim yang cocok untuk (doc_type, event).

    Best-effort & non-blocking: kegagalan satu aturan tidak menggagalkan lainnya.
    """
    try:
        settings = await get_settings()
    except Exception:  # noqa: BLE001
        return {"dispatched": 0, "reason": "settings_error"}
    if not settings.get("enabled"):
        return {"dispatched": 0, "reason": "disabled"}
    rules = await db[RULES_COLL].find(
        {"doc_type": doc_type, "event": event, "enabled": True}, {"_id": 0}).to_list(50)
    sent, skipped = [], []
    for rule in rules:
        if rule.get("recipient_mode") == "fixed":
            to = rule.get("fixed_number", "")
        else:
            rec = await resolve_recipient(doc_type, source_id, entity_id)
            to = rec.get("raw_phone") or rec.get("phone") or ""
        if not to:
            skipped.append({"rule_id": rule["id"], "reason": "no_recipient"})
            continue
        try:
            res = await send_whatsapp(doc_type, source_id, entity_id, to,
                                      rule.get("caption_template", ""), "", actor,
                                      trigger=event, auto=True, rule_id=rule["id"])
            sent.append(res)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"rule_id": rule["id"], "reason": str(exc)})
    return {"dispatched": len(sent), "skipped": skipped, "deliveries": sent}
