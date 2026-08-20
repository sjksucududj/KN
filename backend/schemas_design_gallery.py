"""HRD H5 schemas — Design Gallery (motif kain) + AI auto-tag.

Di-re-export via `schemas.py`. Koleksi `design_gallery` (entity-scoped). Upload
gambar via storage lokal (services.storage_service). Lihat memory/PLAN_HRD.md §H5
(keputusan 3a) + §10b HR-Q5 (AI Anthropic Claude langsung, graceful).
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class GalleryInput(BaseModel):
    """Buat entri motif: judul + cerita/deskripsi + tags + (opsional) link produk.

    FASE F (PS-14) — diperluas menjadi MASTER DESAIN: kode unik, jenis desain, dan
    atribut printing (repeat, jumlah warna, jumlah screen). Semua opsional supaya
    entri galeri HRD yang lama tetap sah dibuat tanpa perubahan.
    """
    title: str = ""
    story: str = ""
    tags: List[str] = []
    product_id: str = ""             # opsional: tautan ke produk (SKU/varian)
    code: str = ""                   # kode desain (unik per entitas)
    design_type: str = "motif"       # motif | pattern | artwork
    repeat_cm: Optional[float] = None
    color_count: Optional[int] = None
    screen_count: Optional[int] = None
    line_code: str = ""              # FASE L — lini kerja MD (kosong = semua lini)


class GalleryUpdate(BaseModel):
    """Update parsial entri motif / master desain."""
    title: Optional[str] = None
    story: Optional[str] = None
    tags: Optional[List[str]] = None
    product_id: Optional[str] = None
    code: Optional[str] = None
    design_type: Optional[str] = None
    repeat_cm: Optional[float] = None
    color_count: Optional[int] = None
    screen_count: Optional[int] = None
    line_code: Optional[str] = None   # FASE L
    status: Optional[str] = None      # draft | approved | retired


class DesignVersionIn(BaseModel):
    """Naikkan versi desain (artwork direvisi) — versi lama tetap terarsip."""
    note: str = ""
    repeat_cm: Optional[float] = None
    color_count: Optional[int] = None
    screen_count: Optional[int] = None


class DesignApproveIn(BaseModel):
    note: str = ""


class DesignRatingIn(BaseModel):
    """Set/ubah rating bintang 1–5 untuk sebuah desain (1 nilai per penilai)."""
    stars: int
    note: str = ""


class DesignRejectIn(BaseModel):
    """Alasan pengembalian desain ke draf — WAJIB."""
    reason: str = Field(min_length=3, max_length=500)
