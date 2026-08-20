"""UOMs router: CRUD unit of measure.

FASE U (D1) — master satuan menjadi **kosakata satuan yang sesungguhnya**: tiap baris
membawa `aliases[]` berisi kata yang benar-benar tersimpan di dokumen (`yard`, `kg`,
`meter`, `roll`, `panel`). Dua pagar yang wajib ada di sini, bukan di layar:
  1. alias/kode tidak boleh KEMBAR antar baris — kalau kembar, satu kata satuan
     menunjuk dua baris master dan pembulatan/faktor jadi tak tentu (409 menuntun);
  2. cache kosakata dibuang setiap kali master ditulis (`uom_service.invalidate_vocab`),
     supaya satuan yang baru ditambah pemilik langsung dikenali seluruh sistem tanpa
     restart — pola yang sama dengan `master_registry.invalidate()` di FASE T.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc
from schemas import GenericPatch, UOMPayload
from services import uom_service

router = APIRouter(prefix="/api")

PATCHABLE = ["code", "name", "base_type", "precision", "status", "factor_to_base",
             "aliases", "factor_per_document"]


def _clean_aliases(raw: Any) -> List[str]:
    """Huruf kecil, tanpa spasi ganda, unik, tanpa kosong (urutan dipertahankan)."""
    out: List[str] = []
    for a in (raw or []):
        s = " ".join(str(a or "").split()).strip().lower()
        if s and s not in out:
            out.append(s)
    return out


async def _assert_no_alias_clash(aliases: List[str], code: str, skip_id: str = "") -> None:
    """Satu kata satuan hanya boleh menunjuk SATU baris master."""
    if not aliases:
        return
    rows = await db.uoms.find({}, {"_id": 0}).to_list(500)
    for r in rows:
        if skip_id and r.get("id") == skip_id:
            continue
        milik = {str(r.get("code") or "").lower(), str(r.get("name") or "").lower()}
        milik |= {str(a or "").lower() for a in (r.get("aliases") or [])}
        milik.discard("")
        bentrok = sorted(set(aliases) & milik)
        if bentrok:
            raise HTTPException(
                status_code=409,
                detail=(f"Alias {', '.join(bentrok)} sudah dipakai satuan "
                        f"{r.get('code')} ({r.get('name')}). Satu kata satuan hanya boleh "
                        f"menunjuk satu baris master — hapus alias itu dari salah satu."))
    if str(code or "").lower() in aliases:
        raise HTTPException(status_code=422,
                            detail="Alias tidak boleh sama dengan kode satuannya sendiri.")


@router.get("/uoms")
async def list_uoms(request: Request) -> List[Dict[str, Any]]:
    # INV-AUTH-01 (KN-076-AUTH-MASTER-LEAK P1): master data WAJIB login.
    await require_permission(request, "uom", "view")
    return await db.uoms.find({}, {"_id": 0}).sort("code", 1).to_list(100)


@router.get("/uoms/vocab")
async def uom_vocab(request: Request) -> Dict[str, Any]:
    """Kosakata satuan efektif: {kata → kode master}. Dipakai layar & gate INV-UOM-02."""
    await require_permission(request, "uom", "view")
    vocab = await uom_service.load_vocab()
    return {
        "words": {k: v.get("code") for k, v in sorted(vocab.items())},
        "rows": [{"code": r.get("code"), "name": r.get("name"),
                  "base_type": r.get("base_type"), "precision": r.get("precision"),
                  "factor_to_base": r.get("factor_to_base"),
                  "factor_per_document": bool(r.get("factor_per_document")),
                  "aliases": r.get("aliases") or []}
                 for r in await uom_service.load_uom_rows()
                 if (r.get("status") or "active") == "active"],
    }


@router.post("/uoms")
async def create_uom(payload: UOMPayload, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "uom", "create")
    if await db.uoms.find_one({"code": payload.code}, {"_id": 0}):
        raise HTTPException(status_code=409, detail="Kode UOM sudah ada")
    data = payload.model_dump()
    data["aliases"] = _clean_aliases(data.get("aliases"))
    await _assert_no_alias_clash(data["aliases"], data.get("code", ""))
    uom = {**data, "id": new_id("uom"), "status": "active", "created_at": now_iso()}
    await db.uoms.insert_one(uom)
    uom_service.invalidate_vocab()
    await audit(actor["name"], "uom_created", "uom", uom["id"], uom)
    return safe_doc(uom)


@router.patch("/uoms/{uom_id}")
async def update_uom(uom_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "uom", "update")
    data = {k: v for k, v in payload.data.items() if k in PATCHABLE}
    if "factor_to_base" in data:                              # S#074 VAL-UOM
        try:
            if float(data["factor_to_base"]) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="factor_to_base harus angka > 0")
    if "precision" in data:
        try:
            if int(data["precision"]) < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="precision harus angka >= 0")
    if "aliases" in data:
        if isinstance(data["aliases"], str):                  # "yard, yd" dari layar
            data["aliases"] = data["aliases"].split(",")
        data["aliases"] = _clean_aliases(data["aliases"])
        cur = await db.uoms.find_one({"id": uom_id}, {"_id": 0}) or {}
        await _assert_no_alias_clash(data["aliases"],
                                     data.get("code") or cur.get("code", ""), skip_id=uom_id)
    if "factor_per_document" in data:
        data["factor_per_document"] = bool(data["factor_per_document"])
    data["updated_at"] = now_iso()
    uom = await db.uoms.find_one_and_update(
        {"id": uom_id}, {"$set": data},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    if not uom:
        raise HTTPException(status_code=404, detail="UOM tidak ditemukan")
    uom_service.invalidate_vocab()
    await audit(actor["name"], "uom_updated", "uom", uom_id, uom)
    return uom


@router.delete("/uoms/{uom_id}")
async def delete_uom(uom_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "uom", "delete")
    cur = await db.uoms.find_one({"id": uom_id}, {"_id": 0})
    if not cur:
        raise HTTPException(status_code=404, detail="UOM tidak ditemukan")
    # FASE U — satuan yang MASIH DIPAKAI dokumen tidak boleh dinonaktifkan (aturan yang
    # sama dengan tahap proses di FASE T). Kalau dibiarkan: dokumen lama menyebut satuan
    # yang tak ada lagi di kosakata → pemilih satuan tidak menawarkannya, faktor tak
    # terselesaikan, dan gate INV-UOM-02 memerah karena data yang SUDAH tersimpan.
    words = [cur.get("code"), cur.get("name")] + list(cur.get("aliases") or [])
    usage = await uom_service.count_unit_usage([w for w in words if w])
    if usage:
        total = sum(usage.values())
        rinci = ", ".join(f"{k} {v}" for k, v in sorted(usage.items()))
        raise HTTPException(
            status_code=409,
            detail=(f"Satuan {cur.get('code')} masih dipakai {total} dokumen ({rinci}). "
                    f"Nonaktifkan hanya setelah dokumen itu tidak memakainya lagi — "
                    f"kalau tidak, angka di dokumen lama kehilangan satuannya."))
    uom = await db.uoms.find_one_and_update(
        {"id": uom_id},
        {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    uom_service.invalidate_vocab()
    await audit(actor["name"], "uom_deactivated", "uom", uom_id, uom)
    return uom
