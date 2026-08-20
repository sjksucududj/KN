"""PS-20 — Produk eksklusif per sales ("PO sendiri").

SSOT visibilitas & kepemilikan produk eksklusif. **Filter WAJIB di backend** (bukan
sekadar disembunyikan di UI) agar tidak bisa ditembus lewat API — sesuai KN_18 §PS-20.

Model data pada dokumen `products`:
  * `exclusivity`     : "umum" (default) | "sales_tertentu"
  * `owner_sales_ids` : List[str] — user id sales pemilik (relevan bila eksklusif)

Aturan visibilitas:
  * `umum`            → semua role & semua sales melihat.
  * `sales_tertentu`  → HANYA sales pemilik (`owner_sales_ids`) yang melihat/menjual.
                        Role non-sales (admin/manager/warehouse) TETAP melihat semua
                        (butuh untuk kelola master & operasi gudang/laporan).
  * Produk lama tanpa field `exclusivity` dianggap `umum` (backward-compatible).
"""
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

EXCLUSIVE = "sales_tertentu"
GENERAL = "umum"
VALID = {GENERAL, EXCLUSIVE}


def is_restricted_role(actor: Optional[Dict[str, Any]]) -> bool:
    """Hanya role `sales` yang dibatasi. Selain itu (admin/manager/warehouse) lihat semua."""
    return (actor or {}).get("role") == "sales"


def visibility_query(actor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Fragmen filter Mongo untuk katalog/POS/pencarian yang menghormati eksklusivitas.

    * non-sales → `{}` (lihat semua).
    * sales     → produk `umum`/legacy (field absen) ATAU produk yang dia miliki.
    """
    if not is_restricted_role(actor):
        return {}
    uid = (actor or {}).get("id")
    return {"$or": [
        {"exclusivity": {"$ne": EXCLUSIVE}},   # $ne juga cocok utk dokumen tanpa field (legacy)
        {"owner_sales_ids": uid},
    ]}


def can_view(actor: Optional[Dict[str, Any]], product: Optional[Dict[str, Any]]) -> bool:
    """Apakah `actor` boleh melihat/menjual `product` menurut aturan eksklusivitas."""
    if not is_restricted_role(actor):
        return True
    if (product or {}).get("exclusivity") != EXCLUSIVE:
        return True
    return (actor or {}).get("id") in ((product or {}).get("owner_sales_ids") or [])


def assert_can_order(actor: Optional[Dict[str, Any]], product: Optional[Dict[str, Any]]) -> None:
    """SO dari item eksklusif hanya boleh dibuat pemiliknya (atau role non-sales).

    Melempar HTTP 403 (pesan Indonesia) bila sales bukan pemilik.
    """
    if can_view(actor, product):
        return
    name = (product or {}).get("name") or (product or {}).get("sku") or "produk ini"
    raise HTTPException(
        status_code=403,
        detail=(f"Produk '{name}' eksklusif milik sales lain — Anda tidak berhak menjualnya."),
    )


def filter_visible(actor: Optional[Dict[str, Any]], products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Saring daftar produk di memori (untuk sumber yang tak lewat query Mongo langsung)."""
    if not is_restricted_role(actor):
        return products
    return [p for p in products if can_view(actor, p)]


async def normalize(db, data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalisasi + validasi field eksklusivitas SEBELUM simpan (create/update).

    * `exclusivity` di luar enum → default `umum`.
    * `umum`           → `owner_sales_ids` dikosongkan.
    * `sales_tertentu` → owner divalidasi HARUS user aktif ber-role `sales`; minimal 1.
    Mengubah `data` in-place & mengembalikannya. Melempar HTTP 400 bila tak sah.
    """
    if "exclusivity" not in data and "owner_sales_ids" not in data:
        return data  # tidak menyentuh eksklusivitas pada patch parsial
    exc = str(data.get("exclusivity", GENERAL) or GENERAL).strip().lower()
    if exc not in VALID:
        exc = GENERAL
    if exc == GENERAL:
        data["exclusivity"] = GENERAL
        data["owner_sales_ids"] = []
        return data
    ids = [str(x) for x in (data.get("owner_sales_ids") or []) if str(x).strip()]
    ids = list(dict.fromkeys(ids))  # unik, jaga urutan
    if ids:
        valid_ids = {
            u["id"] for u in await db.users.find(
                {"id": {"$in": ids}, "role": "sales", "status": "active"}, {"_id": 0, "id": 1}
            ).to_list(len(ids) + 1)
        }
        ids = [i for i in ids if i in valid_ids]
    if not ids:
        raise HTTPException(
            status_code=400,
            detail="Produk eksklusif wajib punya minimal 1 sales pemilik yang valid.",
        )
    data["exclusivity"] = EXCLUSIVE
    data["owner_sales_ids"] = ids
    return data
