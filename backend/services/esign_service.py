"""esign_service.py — Logika e-sign: request OTP, verifikasi + simpan tanda tangan,
verifikasi publik. Dokumen ter-hash (SHA-256) untuk anti-tamper; QR/kode publik
di-attach ke PDF via pdf_service._attach_esign.
"""
from __future__ import annotations
import hashlib
import json
import os
import random
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from db import db
from core_utils import new_id, now_iso, safe_doc
from services import pdf_service as pdfsvc
from services.pdf_resolvers import DOC_REGISTRY
from services.otp import get_otp_channel

OTP_TTL_MIN = 10
MAX_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def gen_otp() -> str:
    return f"{random.randint(0, 999999):06d}"


def hash_otp(code: str) -> str:
    return hashlib.sha256(f"esign-otp::{code}".encode()).hexdigest()


def gen_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def public_base() -> str:
    """URL publik aplikasi untuk tautan verifikasi tanda tangan (QR di kertas).

    FASE G-4 — memakai resolver bersama `services/app_url.py` supaya QR verifikasi
    selalu absolut, termasuk saat dokumen dirender oleh job/penjadwal (tanpa header
    Origin). QR relatif = pemegang kertas tidak bisa memverifikasi apa pun.
    """
    from services.app_url import configured_app_url
    return configured_app_url()


def doc_number(src: Dict[str, Any]) -> Optional[str]:
    for k in ("number", "po_number", "so_number", "order_number", "bill_number",
              "receipt_number", "return_number", "transfer_number", "code", "id"):
        if src.get(k):
            return src[k]
    return None


def _doc_hash_from_built(built: dict) -> str:
    doc = {k: v for k, v in (built.get("doc") or {}).items() if k != "esign"}
    payload = json.dumps(doc, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def compute_doc_hash(doc_type: str, source_id: str, entity_id: Optional[str]) -> Tuple[str, dict]:
    built = await pdfsvc.build_document(doc_type, source_id, entity_id, public_base=public_base())
    return _doc_hash_from_built(built), built


async def create_request(doc_type: str, source_id: str, entity_id: Optional[str],
                         signer_name: str, signer_role: str, signer_contact: str,
                         requested_by: str, channel: Optional[str] = None) -> Dict[str, Any]:
    reg = DOC_REGISTRY.get(doc_type)
    if not reg:
        raise ValueError("Jenis dokumen tidak dikenal")
    if not reg.get("esignable"):
        raise ValueError("Dokumen ini tidak mendukung tanda tangan elektronik")
    if not (signer_name or "").strip():
        raise ValueError("Nama penandatangan wajib diisi")
    source = await db[reg["collection"]].find_one({"id": source_id}, {"_id": 0, "id": 1, "entity_id": 1})
    if not source:
        raise LookupError("Dokumen sumber tidak ditemukan")
    eid = entity_id or source.get("entity_id")
    otp = gen_otp()
    req = {
        "id": new_id("esreq"), "doc_type": doc_type, "source_id": source_id, "entity_id": eid,
        "signer_name": signer_name.strip(), "signer_role": (signer_role or "").strip(),
        "signer_contact": (signer_contact or "").strip(),
        "otp_hash": hash_otp(otp),
        "otp_expires_at": (_now() + timedelta(minutes=OTP_TTL_MIN)).isoformat(),
        "status": "pending", "attempts": 0, "channel": (channel or "simulated"),
        "requested_by": requested_by, "created_at": now_iso(),
    }
    await db.esign_requests.insert_one(req)
    ch = get_otp_channel(channel)
    send_res = await ch.send(req["signer_contact"] or req["signer_name"], otp,
                             purpose=f"Tanda tangan {reg['label']} {source_id}")
    out = {"request_id": req["id"], "channel": ch.name, "expires_at": req["otp_expires_at"],
           "signer_name": req["signer_name"], "doc_label": reg["label"]}
    for k in ("simulated", "reveal_code", "message", "to"):
        if k in send_res:
            out[k] = send_res[k]
    return out


async def verify_and_sign(request_id: str, otp: str, signature_b64: str, ip: str = "") -> Dict[str, Any]:
    req = await db.esign_requests.find_one({"id": request_id}, {"_id": 0})
    if not req:
        raise LookupError("Permintaan tanda tangan tidak ditemukan")
    if req["status"] == "verified":
        raise ValueError("Permintaan ini sudah selesai ditandatangani")
    if req["status"] in ("expired", "cancelled"):
        raise ValueError("Permintaan tidak berlaku — minta OTP ulang")
    try:
        exp = datetime.fromisoformat(req["otp_expires_at"])
    except (ValueError, TypeError):
        exp = _now()
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp <= _now():
        await db.esign_requests.update_one({"id": request_id}, {"$set": {"status": "expired"}})
        raise ValueError("Kode OTP kedaluwarsa — minta OTP ulang")
    if req.get("attempts", 0) >= MAX_ATTEMPTS:
        await db.esign_requests.update_one({"id": request_id}, {"$set": {"status": "cancelled"}})
        raise ValueError("Terlalu banyak percobaan salah — minta OTP ulang")
    if hash_otp(str(otp).strip()) != req["otp_hash"]:
        await db.esign_requests.update_one({"id": request_id}, {"$inc": {"attempts": 1}})
        raise ValueError("Kode OTP salah")
    if not (signature_b64 or "").strip():
        raise ValueError("Gambar tanda tangan wajib diisi")

    doc_hash, _built = await compute_doc_hash(req["doc_type"], req["source_id"], req["entity_id"])
    existing = await db.document_signatures.find_one(
        {"doc_type": req["doc_type"], "source_id": req["source_id"], "status": "signed"},
        {"_id": 0, "verification_code": 1})
    code = (existing or {}).get("verification_code") or gen_code()
    sig = {
        "id": new_id("esig"), "request_id": request_id, "doc_type": req["doc_type"],
        "source_id": req["source_id"], "entity_id": req["entity_id"],
        "signer_name": req["signer_name"], "signer_role": req.get("signer_role", ""),
        "signature_b64": signature_b64, "doc_hash": doc_hash, "verification_code": code,
        "status": "signed", "signed_at": now_iso(), "ip": ip, "channel": req.get("channel", "simulated"),
    }
    await db.document_signatures.insert_one(sig)
    await db.esign_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "verified", "verified_at": now_iso(), "verification_code": code}})
    return {"status": "signed", "verification_code": code, "signed_at": sig["signed_at"],
            "signer_name": sig["signer_name"], "doc_hash": doc_hash,
            "verify_url": f"{public_base()}/verify-document/{code}"}


async def list_signatures(doc_type: str, source_id: str):
    sigs = await db.document_signatures.find(
        {"doc_type": doc_type, "source_id": source_id, "status": "signed"},
        {"_id": 0, "signature_b64": 0}).sort("signed_at", 1).to_list(50)
    return safe_doc(sigs)


async def public_verify(code: str) -> Dict[str, Any]:
    sigs = await db.document_signatures.find(
        {"verification_code": code, "status": "signed"},
        {"_id": 0, "signature_b64": 0}).sort("signed_at", 1).to_list(50)
    if not sigs:
        return {"valid": False, "code": code}
    first = sigs[0]
    reg = DOC_REGISTRY.get(first["doc_type"], {})
    number = None
    coll = reg.get("collection")
    if coll:
        src = await db[coll].find_one({"id": first["source_id"]}, {"_id": 0})
        if src:
            number = doc_number(src)
    ent = await db.business_entities.find_one(
        {"id": first.get("entity_id")}, {"_id": 0, "legal_name": 1, "short_name": 1}) or {}
    return {
        "valid": True, "code": code, "doc_type": first["doc_type"],
        "doc_label": reg.get("label", first["doc_type"]), "number": number,
        "entity_name": ent.get("legal_name") or ent.get("short_name") or "",
        "doc_hash": first.get("doc_hash"), "signed_at": first.get("signed_at"),
        "signers": [{"name": s["signer_name"], "role": s.get("signer_role", ""),
                     "signed_at": s.get("signed_at")} for s in sigs],
        "verify_url": f"{public_base()}/verify-document/{code}",
    }
