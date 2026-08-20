"""F0-F + FASE E-1 — Provisioning & VALIDASI badan usaha (SATU JALUR).

Membuat badan usaha siap-pakai dalam satu langkah:
  - **validasi tunggal** (`validate_entity_input`) yang dipakai `POST` MAUPUN
    `PATCH` — sebelum FASE E-1 keduanya punya aturan sendiri sehingga `PATCH`
    bisa menembus keunikan yang ditegakkan `POST` (E1.2),
  - lengkapi default config badan usaha (numbering_scheme, currency, fiscal year),
  - pastikan bagan akun (CoA) tersedia — CoA SHARED by-code, buku terpisah lewat
    `journal_entries.entity_id` (lihat `gl_service`),
  - siapkan penanda config override per-badan-usaha.
Penomoran (CODE/PREFIX-NNNNN) & buku besar otomatis aktif begitu dipakai.
"""
import re
from typing import Any, Dict, Optional

from fastapi import HTTPException

from db import db
from core_utils import invalidate_entity_code, new_id, now_iso
from domain_registry import ENTITY_TYPE_VALUES, PERSONAL_ENTITY_TYPES
from services.entity_context_service import ENTITY_DEFAULTS
from services import entity_lifecycle_service as lifecycle
from services import gl_service

TAX_MODES = ("ppn", "non_ppn")


def _slug_prefix(short_name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]", "", short_name or "").upper()
    return s[:6] or "ENT"


def compose_personal_legal_name(owner_name: str, business_label: str) -> str:
    """E1.1 — nama legal usaha perorangan = nama pemilik + label usaha.

    Usaha perorangan tidak punya badan hukum terpisah, jadi “nama legal”-nya
    adalah nama orangnya. Label usaha (mis. “Toko Kain Berkah”) dipakai sebagai
    nama dagang. Hasil: “Budi Santoso (Toko Kain Berkah)”.
    """
    owner = (owner_name or "").strip()
    label = (business_label or "").strip()
    if owner and label:
        return f"{owner} ({label})"
    return owner or label


async def validate_entity_input(data: Dict[str, Any], *, entity_id: str = "",
                                existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Validasi + normalisasi payload badan usaha. Dipakai POST dan PATCH.

    `existing` diisi saat PATCH supaya aturan bisa membandingkan nilai lama
    (mis. kunci prefix E1.3 hanya berlaku bila prefix BERUBAH).
    Mengembalikan dict berisi HANYA field yang tervalidasi & ternormalisasi.
    """
    prev = dict(existing or {})
    out = dict(data or {})
    is_patch = bool(entity_id)

    def eff(key: str, default: Any = "") -> Any:
        """Nilai efektif setelah patch diterapkan."""
        return out[key] if key in out else prev.get(key, default)

    # ── jenis badan usaha (E1.1) ──
    if "type" in out:
        out["type"] = (out.get("type") or "").strip()
        if out["type"] not in ENTITY_TYPE_VALUES:
            raise HTTPException(
                status_code=400,
                detail=f"Jenis badan usaha “{out['type']}” tidak dikenal. "
                       f"Pilihan: {', '.join(ENTITY_TYPE_VALUES)}.")
    ent_type = eff("type", "PT")

    # ── usaha perorangan: nama legal dibentuk dari nama pemilik + label usaha ──
    if ent_type in PERSONAL_ENTITY_TYPES:
        owner = str(eff("owner_name")).strip()
        label = str(eff("business_label")).strip()
        if not is_patch and not owner:
            raise HTTPException(
                status_code=400,
                detail="Usaha perorangan wajib menyebut nama pemilik — nama legalnya "
                       "adalah nama orangnya, bukan nama PT.")
        composed = compose_personal_legal_name(owner, label)
        if composed:
            out["owner_name"] = owner
            out["business_label"] = label
            out["legal_name"] = composed

    # ── wajib isi ──
    legal_name = str(eff("legal_name")).strip()
    short_name = str(eff("short_name")).strip()
    if not legal_name or not short_name:
        raise HTTPException(status_code=400,
                            detail="Nama legal dan nama singkat wajib diisi.")
    if "legal_name" in out:
        out["legal_name"] = legal_name
    if "short_name" in out:
        out["short_name"] = short_name

    # ── mode pajak & NPWP: WAJIB hanya bila PKP (E1.1) ──
    if "default_tax_mode" in out:
        out["default_tax_mode"] = (out.get("default_tax_mode") or "").strip()
        if out["default_tax_mode"] not in TAX_MODES:
            raise HTTPException(
                status_code=400,
                detail="Mode pajak harus “ppn” (PKP) atau “non_ppn” (non-PKP).")
    if eff("default_tax_mode", "ppn") == "ppn" and not str(eff("npwp")).strip():
        raise HTTPException(
            status_code=400,
            detail="Badan usaha PKP wajib mengisi NPWP karena akan menerbitkan "
                   "faktur pajak. Untuk non-PKP, pilih mode pajak “non_ppn”.")

    # ── keunikan (case-insensitive) ──
    if "short_name" in out:
        await lifecycle.assert_unique("short_name", out["short_name"], exclude_id=entity_id)

    # ── kode dokumen: normalisasi → keunikan → kunci bila sudah terbit dokumen ──
    if "doc_prefix" in out:
        prefix = (out.get("doc_prefix") or "").strip().upper()
        if not prefix:
            prefix = _slug_prefix(short_name)
        if not re.fullmatch(r"[A-Z0-9]{2,10}", prefix):
            raise HTTPException(
                status_code=400,
                detail="Kode dokumen hanya boleh huruf/angka (2–10 karakter), "
                       "mis. KSC atau KANDA — dipakai sebagai awalan nomor dokumen.")
        out["doc_prefix"] = prefix
        await lifecycle.assert_unique("doc_prefix", prefix, exclude_id=entity_id)
        if is_patch:
            await lifecycle.assert_prefix_change_allowed(
                entity_id, prev.get("doc_prefix", ""), prefix)

    if "fiscal_year_start" in out and out["fiscal_year_start"]:
        if not re.fullmatch(r"\d{2}-\d{2}", str(out["fiscal_year_start"])):
            raise HTTPException(status_code=400,
                                detail="Awal tahun fiskal memakai format MM-DD, mis. 01-01.")
    return out


async def provision_entity(payload: Dict[str, Any], actor_name: str) -> Dict[str, Any]:
    data = {k: v for k, v in (payload or {}).items() if v is not None}
    data.setdefault("doc_prefix", "")   # dorong ke jalur validasi/normalisasi prefix
    clean = await validate_entity_input(data)

    entity: Dict[str, Any] = dict(ENTITY_DEFAULTS)
    entity.update(data)
    entity.update(clean)
    entity.update({
        "id": new_id("ent"),
        "status": lifecycle.STATUS_ACTIVE,
        "created_by": actor_name,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    await db.business_entities.insert_one(entity)
    invalidate_entity_code(entity["id"])   # E1.4

    # Bagan akun bersama (idempotent) — semua badan usaha pakai chart yang sama by-code.
    coa_added = await gl_service.seed_default_coa()
    # Penanda config override per-badan-usaha (efektif via get_effective_settings).
    await db.system_settings.update_one(
        {"scope": entity["id"]},
        {"$setOnInsert": {"scope": entity["id"], "created_at": now_iso()},
         "$set": {"updated_at": now_iso()}},
        upsert=True,
    )

    entity.pop("_id", None)
    prefix = entity.get("doc_prefix", "")
    # FASE E-7 (E7.7) — badan usaha baru langsung SALING TERLIHAT sebagai pemasok
    # bertipe "Entitas grup". Tanpa ini, badan usaha yang lahir sesudah fase E-7 tidak
    # punya jangkar pemasoknya dan pagar PO/SO hanya bisa mengenalinya lewat
    # pencocokan nama/NPWP (lapis kedua) — cukup, tapi layarnya jadi kosong.
    group_partners = {}
    try:
        from services import group_partner_service as _grp
        group_partners = await _grp.sync_group_entity_suppliers(actor_name=actor_name)
    except Exception as exc:  # noqa: BLE001 — badan usaha tetap sah walau sinkronisasi gagal
        print(f"[provision] sync pemasok entitas grup dilewati: {exc}")
    return {
        "entity": entity,
        "provisioning": {
            "doc_prefix": prefix,
            "number_preview": f"{prefix}/SO-00001",
            "numbering_scheme": entity.get("numbering_scheme"),
            "is_pkp": entity.get("default_tax_mode") == "ppn",
            "coa_accounts_added": coa_added,
            "coa_shared": True,
            "config_override_created": True,
            "group_partner_suppliers": group_partners,
        },
    }
