"""AR Aging router (EPIC7-A) — Piutang / Accounts Receivable Aging.

Akses: admin/manager (finance). Respons: OBJEK/ARRAY telanjang (kontrak KN3).

Read-only/derived — KECUALI satu aksi sengaja: **membuatkan nota denda** untuk piutang
telat (FASE G-3, permintaan #2 pemilik). Sebelumnya kolom denda hanya estimasi yang tidak
bisa ditagih; sekarang laporannya membawa nota denda NYATA (FASE G-2) dan bisa menerbitkan
usulan denda langsung dari layar penagihan.

FASE E-0 (L9) — cakupan entitas: dulu `aging_report(entity_id=None)` selalu dipanggil
tanpa konteks sehingga `entity_id` respons selalu `"all"` dan total piutang KSC/KANDA/ALL
identik (Rp 20.260.900 — dua PT dicampur). Sekarang entitas diambil dari `entity_ctx`,
param `entity_id` divalidasi ∈ allowed, dan `all` hanya untuk peran lintas-entitas.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from dependencies import audit, require_any_permission, require_permission
from entity_scope import entity_ctx, resolve_scope_ids, scope_value
from services import ar_aging_service

router = APIRouter(prefix="/api")

# AUDIT SALES vs ADMIN SALES / PERAN (2026-08-15) — SIAPA BOLEH MEMBACA AGING PIUTANG.
#
# Dulu: `require_role(request, ["manager"])` → hanya manajer & admin (rank ≥ manajer).
# Kenyataan yang terukur: peran `finance` memegang menu **Aging Piutang** (`ar-aging`
# di `frontend/src/config/roles.js`) DAN memegang izin `penalty.issue` — jadi ia berhak
# MENERBITKAN nota denda dari layar ini, tetapi tidak berhak MELIHAT layarnya. Yang
# terlihat kasir: menu terbuka, tabel kosong, satu bilah merah. Persis kelas cacat
# "menu terlihat, datanya 403" yang dicari `scripts/audit_sales_roles_ux.py`.
#
# Sekarang: berbasis IZIN, bukan pangkat peran —
#   `accounting.view` (manajer/admin: sisi buku) ATAU `penalty.issue` (finance: yang
#   menerbitkan denda dari aging). Sales TIDAK ikut terbuka: ia hanya punya
#   `penalty.view`/`ar_receipt.view`, bukan dua izin di atas. Ini penting — aging
#   memuat piutang SELURUH pelanggan badan usaha, sedangkan sales dibatasi
#   kepemilikan datanya sendiri (E8.4).
AGING_READ = [("accounting", "view"), ("penalty", "issue")]


@router.get("/ar/aging")
async def ar_aging(
    request: Request,
    entity_id: Optional[str] = Query(None),
    sales_id: Optional[str] = Query(None),
    as_of: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Ringkasan aging piutang (totals per-bucket + baris per-customer + denda nyata)."""
    await require_any_permission(request, AGING_READ)
    ctx = await entity_ctx(request)
    scope = scope_value(ctx, entity_id)
    return await ar_aging_service.aging_report(entity_id=scope, sales_id=sales_id, as_of=as_of)


@router.post("/ar/aging/{customer_id}/accrue-penalties")
async def ar_aging_accrue(customer_id: str, request: Request,
                          today: str = Query("")) -> Dict[str, Any]:
    """Ubah denda ESTIMASI pelanggan ini menjadi **nota denda** (dokumen) yang bisa ditagih.

    Memakai mesin FASE G-2: nota lahir sebagai `draft` (belum menyentuh buku besar) supaya
    masih bisa dinegosiasikan / dibebaskan dengan alasan. Idempotent per periode — ditekan
    berkali-kali tidak menggandakan nota.
    """
    actor = await require_permission(request, "penalty", "issue")
    ctx = await entity_ctx(request)
    ids = resolve_scope_ids(ctx)
    if await ar_aging_service.customer_aging_detail(customer_id, entity_ids=ids) is None:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan untuk entitas ini")
    from services import penalty_service as penalties
    rows = await penalties.accrue_customer(customer_id, today=today or None,
                                           actor_name=actor.get("name", ""))
    await audit(actor.get("name", ""), "ar_aging_penalty_accrued", "customers", customer_id,
                {"penalties": [r.get("number") for r in rows], "count": len(rows)})
    return {"customer_id": customer_id, "count": len(rows), "penalties": rows,
            "detail": await ar_aging_service.customer_aging_detail(customer_id,
                                                                  as_of=today or None,
                                                                  entity_ids=ids)}


@router.get("/ar/aging/{customer_id}")
async def ar_aging_detail(customer_id: str, request: Request,
                          as_of: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Rincian aging per-order untuk satu customer (drill-down + nota denda per pesanan)."""
    await require_any_permission(request, AGING_READ)
    ctx = await entity_ctx(request)
    detail = await ar_aging_service.customer_aging_detail(
        customer_id, as_of=as_of, entity_ids=resolve_scope_ids(ctx))
    if detail is None:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan untuk entitas ini")
    return detail
