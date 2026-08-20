"""FASE F (PS-12) — **Penjaga lifecycle produk** + resolver kebijakan R&D.

Masalah nyata yang diselesaikan: sebelum fase ini `products.lifecycle` hanya ADA di
`domain_registry` (`in_use: False`) tanpa satu pun penulis/pembaca. Artinya sistem
MENGKLAIM punya daur hidup produk (konsep → labdip/proofing → disetujui → produksi)
padahal produk konsep tetap bisa dijual & dibeli. Modul ini menjadikannya nyata.

Aturan pengaman (KN_31 §1 — supaya G-0…G-4 tidak rusak):
  * `lifecycle` KOSONG/tidak ada = **data lama** = dianggap `produksi` (boleh dipesan).
    Karena itu 17 produk seed & seluruh SO/PR/PO lama TIDAK mungkin ikut terblokir.
  * Penegakan **configurable** lewat registry FASE G-0 (`rnd.lifecycle_enforcement`):
    `off` (abaikan) · `warn` (izinkan + catat peringatan) · `block` (tolak 400).
  * SATU fungsi penjaga dipakai 4 titik (SO · PR · PO · katalog). Tidak ada logika
    lifecycle yang tersebar — supaya tidak ada dua sumber kebenaran.
"""
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException

from services.config_resolver import value_of

# Satu-satunya lifecycle yang boleh dipesan/dijual.
ORDERABLE: set = {"produksi"}

# Alasan penolakan yang bisa DITINDAK user (bukan "error" buntu).
_REASON = {
    "konsep": "masih konsep R&D (belum ada sample yang disetujui)",
    "labdip": "sedang tahap labdip (menunggu hasil sample warna)",
    "proofing": "sedang tahap proofing (menunggu hasil sample printing)",
    "disetujui": "spesifikasinya sudah disetujui tetapi BELUM dirilis ke produksi",
    "dihentikan": "sudah dihentikan (discontinued)",
}

POLICY_KEYS = (
    "rnd.lifecycle_enforcement",
    "rnd.new_product_default_lifecycle",
    "rnd.spec_approval_roles",
    "rnd.sample_decision_roles",
    "rnd.max_rounds",
    "rnd.round_sla_days",
    "rnd.require_attachment_on_round",
    "rnd.require_design_for_proofing",
    "rnd.auto_contract_on_decide",
    "rnd.sample_material_from_stock",
    # PS-18 — eskalasi SLA otomatis + bobot nilai (grade) desainer.
    "rnd.sla_escalate_admin_days",
    "rnd.kpi_weight_on_time",
    "rnd.kpi_weight_score",
    "rnd.kpi_weight_acc",
    "rnd.kpi_penalty_rework",
    "rnd.kpi_penalty_overdue",
)


async def policy(entity_id: str = "") -> Dict[str, Any]:
    """Seluruh kebijakan R&D yang BERLAKU (registry FASE G-0, berlapis per entitas)."""
    ctx = {"entity_id": entity_id or ""}
    out: Dict[str, Any] = {}
    for key in POLICY_KEYS:
        out[key.split(".", 1)[1]] = await value_of(key, ctx)
    return out


async def enforcement_mode(entity_id: str = "") -> str:
    mode = await value_of("rnd.lifecycle_enforcement", {"entity_id": entity_id or ""})
    return str(mode or "block").strip().lower()


def lifecycle_of(product: Optional[Dict[str, Any]]) -> str:
    """Lifecycle efektif. Kosong/None → `produksi` (kompatibilitas data lama)."""
    raw = str((product or {}).get("lifecycle") or "").strip().lower()
    return raw or "produksi"


def is_orderable(product: Optional[Dict[str, Any]]) -> bool:
    return lifecycle_of(product) in ORDERABLE


def _label(product: Dict[str, Any]) -> str:
    lc = lifecycle_of(product)
    name = product.get("name") or product.get("sku") or product.get("id") or "produk"
    sku = product.get("sku") or ""
    head = f"{name}" + (f" ({sku})" if sku else "")
    return f"{head} — {_REASON.get(lc, lc)}"


async def assert_orderable(products: Iterable[Dict[str, Any]], *, entity_id: str = "",
                           where: str = "dokumen") -> List[str]:
    """Tolak/peringatkan pemakaian produk yang belum sah dipesan.

    Return daftar peringatan (mode `warn`). Mode `block` melempar HTTP 400 dengan
    pesan yang menyebut produk & alasannya, plus jalan keluarnya (rilis ke produksi).
    """
    rows = [p for p in (products or []) if p]
    bad = [p for p in rows if not is_orderable(p)]
    if not bad:
        return []
    mode = await enforcement_mode(entity_id)
    if mode == "off":
        return []
    detail = "; ".join(_label(p) for p in bad[:5])
    msg = (f"{len(bad)} produk belum boleh masuk {where}: {detail}. "
           "Selesaikan dulu alur R&D (Spesifikasi → Sample → Rilis ke Produksi) "
           "atau ubah kebijakan di Pusat Pengaturan → R&D & Desain.")
    if mode == "warn":
        return [msg]
    raise HTTPException(status_code=400, detail=msg)


async def assert_orderable_ids(product_ids: Iterable[str], *, entity_id: str = "",
                               where: str = "dokumen") -> List[str]:
    """Versi by-id (dipakai jalur yang belum memuat dokumen produk)."""
    ids = [i for i in {str(x) for x in (product_ids or [])} if i]
    if not ids:
        return []
    from db import db
    rows = await db.products.find(
        {"id": {"$in": ids}},
        {"_id": 0, "id": 1, "sku": 1, "name": 1, "lifecycle": 1},
    ).to_list(len(ids) + 1)
    return await assert_orderable(rows, entity_id=entity_id, where=where)


async def default_new_lifecycle(entity_id: str = "") -> str:
    """Lifecycle produk yang dibuat LANGSUNG dari Master Produk (bukan lewat R&D).

    Default `produksi` supaya alur master data lama tetap berjalan apa adanya.
    """
    val = await value_of("rnd.new_product_default_lifecycle", {"entity_id": entity_id or ""})
    return str(val or "produksi").strip().lower()
