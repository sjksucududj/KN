"""PS-17/PS-20 — Divisi sebagai aktor R&D (D-13) + MATRIKS PERSETUJUAN MENGIKAT (D-14).

SSOT daftar divisi/jabatan R&D dan MATRIKS PERSETUJUAN per tahap.

PS-17 (D-13): cakupan divisi sengaja DIBATASI ke R&D (keputusan pemilik 3a) — divisi
TIDAK mengubah hak akses/menu global; admin & manager tetap super-role.

PS-20 (D-14 — keputusan pemilik sesi ini): matriks di bawah **BUKAN lagi sekadar
rujukan tampilan**. Setiap tahap sekarang punya `levels` (tingkat persetujuan +
peran yang berwenang) yang DITEGAKKAN oleh `services/approval_matrix_service.py`
pada endpoint aslinya:

  design_acc       → POST /api/rnd/specs/{id}/approve|reject
  sample_acc       → POST /api/rnd/samples/{id}/decide
  po_custom        → POST /api/special-orders/{id}/approve|reject  (2 tingkat)
  purchase_request → POST /api/purchase-requisitions/{id}/approve|reject

"Direksi" TIDAK menjadi peran/divisi baru (keputusan pemilik: cukup **admin** yang
bertindak sebagai Direksi) sehingga RBAC global tetap utuh.
"""
from typing import Any, Dict, List

# 1 user/orang = 1 divisi (D-13 poin 4a). `id` dipakai internal, `name` untuk tampilan.
RND_DIVISIONS: List[Dict[str, str]] = [
    {"id": "sample", "name": "Sample",
     "desc": "Pembuatan & penilaian sample/labdip (round proofing)."},
    {"id": "designer", "name": "Designer",
     "desc": "Perancang motif, pattern, dan artwork."},
    {"id": "rnd", "name": "RnD",
     "desc": "Riset material & spesifikasi produk."},
    {"id": "socmed", "name": "Socmed",
     "desc": "Konten kreatif & media sosial."},
    {"id": "md", "name": "MD",
     "desc": "Merchandising / pengembangan lini produk."},
    {"id": "admin_sales", "name": "Admin Sales",
     "desc": "Administrasi penjualan & order."},
    {"id": "finance", "name": "Finance",
     "desc": "Keuangan & pembayaran."},
]

DIVISION_BY_ID: Dict[str, Dict[str, str]] = {d["id"]: d for d in RND_DIVISIONS}
DIVISION_IDS = set(DIVISION_BY_ID)


def division_name(div_id: str) -> str:
    return DIVISION_BY_ID.get(div_id or "", {}).get("name", "")


# ── Label peran dalam bahasa pemilik usaha (dipakai pesan penolakan & UI) ─────
ROLE_LABELS: Dict[str, str] = {
    "admin": "Direksi/Admin",
    "manager": "Manager",
    "sales": "Sales",
    "warehouse": "Gudang",
}


def role_label(role: str) -> str:
    return ROLE_LABELS.get((role or "").strip().lower(), (role or "").title())


def roles_label(roles: List[str]) -> str:
    return " atau ".join(role_label(r) for r in (roles or []) if r)


# Kunci ambang (registry `config_catalog_approval_matrix.py`) untuk tingkat Direksi.
DIREKSI_MIN_KEY = "approval.po_custom_direksi_min"

# Matriks persetujuan (D-13 poin 2a) — `approvers` = LABEL tampilan (kompatibel PS-17),
# `levels` = penegakan nyata (PS-20 / D-14).
APPROVER_MATRIX: List[Dict[str, Any]] = [
    {"stage": "design_acc", "label": "ACC Desain",
     "approvers": ["Manager"],
     "note": "Pengesahan desain sebelum dipakai untuk proofing/produk.",
     "doc_type": "rnd_spec", "doc_label": "Spesifikasi Desain",
     "collection": "md_specs", "view": "rnd-specs",
     "levels": [{"level": 1, "label": "Manager", "roles": ["manager", "admin"]}]},
    {"stage": "sample_acc", "label": "ACC Sample",
     "approvers": ["Manager"],
     "note": "Keputusan hasil round sample (ACC / revisi / tolak).",
     "doc_type": "rnd_sample", "doc_label": "Permintaan Sample",
     "collection": "md_samples", "view": "rnd-samples",
     "levels": [{"level": 1, "label": "Manager", "roles": ["manager", "admin"]}]},
    {"stage": "po_custom", "label": "PO Custom",
     "approvers": ["Manager", "Direksi"],
     "note": "Manager menyetujui; naik ke Direksi bila nilai besar.",
     "doc_type": "special_order", "doc_label": "Pesanan Khusus (PO Custom)",
     "collection": "special_orders", "view": "special-orders",
     "levels": [{"level": 1, "label": "Manager", "roles": ["manager", "admin"]},
                {"level": 2, "label": "Direksi", "roles": ["admin"],
                 "min_amount_key": DIREKSI_MIN_KEY}]},
    {"stage": "purchase_request", "label": "Permintaan Pembelian (PR)",
     "approvers": ["Manager"],
     "note": "Persetujuan PR bahan / kebutuhan sample.",
     "doc_type": "purchase_requisition", "doc_label": "Permintaan Pembelian",
     "collection": "purchase_requisitions", "view": "purchase-requisitions",
     "levels": [{"level": 1, "label": "Manager", "roles": ["manager", "admin"]}]},
]

STAGE_BY_ID: Dict[str, Dict[str, Any]] = {s["stage"]: s for s in APPROVER_MATRIX}
STAGE_IDS = tuple(s["stage"] for s in APPROVER_MATRIX)


def stage_label(stage: str) -> str:
    return STAGE_BY_ID.get(stage or "", {}).get("label", stage or "")
