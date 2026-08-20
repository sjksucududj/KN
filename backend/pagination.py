"""P2 — Server-side pagination helpers (opt-in, backward compatible).

Kontrak paginasi (disetujui user):
    { "items": [...], "total": N, "page": p, "page_size": s, "has_more": bool }
Param query: ?page=&page_size=&q=&sort=

OPT-IN: endpoint list yang mendukung paginasi HANYA mengembalikan envelope
di atas bila query param `page` ATAU `page_size` hadir. Bila tidak, endpoint
tetap mengembalikan array telanjang (kompatibel mundur — konsumen lama & gate
`verify_api_contract` tetap aman; CHECK C sudah membaca kedua bentuk).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import Request

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200


def is_paged(request: Request) -> bool:
    """True bila klien meminta paginasi (ada param page / page_size)."""
    qp = request.query_params
    return ("page" in qp) or ("page_size" in qp)


def get_page_params(
    request: Request,
    default_size: int = DEFAULT_PAGE_SIZE,
    max_size: int = MAX_PAGE_SIZE,
) -> Tuple[int, int, str, str]:
    """Ambil (page, page_size, q, sort) dari query string dengan aman."""
    qp = request.query_params

    def _int(name: str, dflt: int) -> int:
        try:
            return int(qp.get(name, dflt))
        except (TypeError, ValueError):
            return dflt

    page = max(1, _int("page", 1))
    page_size = _int("page_size", default_size)
    page_size = max(1, min(page_size, max_size))
    q = (qp.get("q") or "").strip()
    sort = (qp.get("sort") or "").strip()
    return page, page_size, q, sort


def build_search(q: str, fields: Iterable[str]) -> Dict[str, Any]:
    """Bangun filter `$or` regex case-insensitive untuk daftar field.

    Return {} bila q kosong (tidak memfilter apa pun).
    """
    q = (q or "").strip()
    fields = list(fields or [])
    if not q or not fields:
        return {}
    rx = {"$regex": re.escape(q), "$options": "i"}
    return {"$or": [{f: rx} for f in fields]}


def merge_query(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """Gabung dua filter Mongo dengan aman (pakai $and bila keduanya isi)."""
    if not extra:
        return base
    if not base:
        return extra
    return {"$and": [base, extra]}


async def fetch_page(
    collection,
    query: Dict[str, Any],
    page: int,
    page_size: int,
    sort_field: Optional[str] = "created_at",
    sort_dir: int = -1,
    projection: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Hitung total + ambil satu halaman (skip/limit). Return (items, total)."""
    if projection is None:
        projection = {"_id": 0}
    total = await collection.count_documents(query)
    cursor = collection.find(query, projection)
    if sort_field:
        cursor = cursor.sort(sort_field, sort_dir)
    cursor = cursor.skip((page - 1) * page_size).limit(page_size)
    items = await cursor.to_list(page_size)
    return items, total


def envelope(items: List[Any], total: int, page: int, page_size: int) -> Dict[str, Any]:
    """Bungkus hasil sesuai kontrak paginasi."""
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": page * page_size < total,
    }


def paginate_list(
    rows: List[Any],
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    """Paginasi in-memory (untuk list yang sudah ter-enrich/di-hitung penuh).

    Dipakai bila enrichment/sort kompleks sudah dilakukan di Python dan kita
    hanya perlu memotong halaman + mengembalikan envelope.
    """
    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    return envelope(rows[start:end], total, page, page_size)
