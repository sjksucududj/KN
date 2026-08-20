"""routers/esign.py — Tanda tangan elektronik: request OTP, verifikasi+sign,
daftar tanda tangan, dan verifikasi PUBLIK (tanpa login).
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from dependencies import require_permission, audit
from services import esign_service as es

router = APIRouter(prefix="/api/esign", tags=["esign"])


class RequestBody(BaseModel):
    doc_type: str
    source_id: str
    entity_id: Optional[str] = None
    signer_name: str
    signer_role: Optional[str] = ""
    signer_contact: Optional[str] = ""
    channel: Optional[str] = None


class VerifyBody(BaseModel):
    request_id: str
    otp: str
    signature_b64: str


@router.post("/request")
async def request_otp(body: RequestBody, request: Request):
    user = await require_permission(request, "esign", "sign")
    actor = user.get("email") or user.get("name") or user.get("id")
    try:
        return await es.create_request(
            body.doc_type, body.source_id, body.entity_id, body.signer_name,
            body.signer_role, body.signer_contact, actor, body.channel)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/verify")
async def verify(body: VerifyBody, request: Request):
    user = await require_permission(request, "esign", "sign")
    ip = request.client.host if request.client else ""
    try:
        res = await es.verify_and_sign(body.request_id, body.otp, body.signature_b64, ip)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await audit(user.get("email", "-"), "esign.sign", "document_signature",
                res.get("verification_code", ""), {"request_id": body.request_id, **res}, "")
    return res


@router.get("/signatures/{doc_type}/{source_id}")
async def signatures(doc_type: str, source_id: str, request: Request):
    await require_permission(request, "esign", "view")
    return {"signatures": await es.list_signatures(doc_type, source_id)}


@router.get("/verify/{code}")
async def public_verify(code: str):
    """PUBLIK — tanpa autentikasi (dipakai halaman verifikasi + QR)."""
    return await es.public_verify(code)
