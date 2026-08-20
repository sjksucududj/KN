"""P1 — Performance indexes (idempotent, non-fatal).

Membuat index untuk koleksi terpanas agar query umum menjadi IXSCAN
(bukan COLLSCAN). Dipanggil saat startup via bootstrap.run_bootstrap().

Aman dijalankan berulang: setiap index diberi nama deterministik; bila
sudah ada (atau field belum ada di data) proses tidak menggagalkan startup.
Semua index dibuat non-unique (kecuali yang sudah ada di tempat lain, mis.
products.sku) agar tidak bentrok dengan data seed/legacy.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from pymongo import ASCENDING, DESCENDING

from db import db

logger = logging.getLogger("indexes")

# Tipe: daftar spesifikasi index per koleksi. Setiap index = list (field, arah).
IndexKeys = List[Tuple[str, int]]
A = ASCENDING
D = DESCENDING

INDEX_SPECS: Dict[str, List[IndexKeys]] = {
    # ── Inventory (paling panas) ──────────────────────────────────────────
    "inventory_rolls": [
        [("product_id", A), ("warehouse_id", A), ("owner_entity_id", A), ("status", A)],
        [("status", A), ("length_remaining", A)],
        [("warehouse_id", A), ("status", A)],
        [("owner_entity_id", A), ("status", A)],
        [("product_id", A), ("status", A)],
        [("reserved_ref", A)],
        [("earmarked_for", A)],
        [("rfid_tag_id", A)],
        [("roll_no", A)],
        [("dye_lot", A)],
        [("lot_id", A)],
        [("created_at", D)],
        [("line_code", A), ("status", A)],   # FASE L — penyaring lini di Daftar Roll
    ],
    # ── Fase C — Lot kelas satu (D-10/D-26) ───────────────────────────────
    "inventory_lots": [
        [("lot_number", A)],
        [("owner_entity_id", A), ("created_at", D)],
        [("product_id", A), ("owner_entity_id", A)],
        [("source_ref.id", A), ("product_id", A)],
        [("legacy_lot_codes", A)],
        [("dye_lot", A)],
        [("supplier_lot", A)],
        [("lot_status", A)],
        [("parent_lot_ids", A)],
        [("child_lot_ids", A)],
    ],
    # ── Fase D/E — Kontrak mitra & supplier (D-05/D-07/D-09) ──────────────
    "supplier_contracts": [
        [("contract_number", A)],
        [("entity_id", A), ("created_at", D)],
        [("contract_type", A), ("partner_id", A), ("status", A)],
        [("partner_id", A), ("process_type", A), ("product_id", A)],
        [("status", A), ("valid_to", A)],
    ],
    # ── Fase E — Barang Supplier (katalog versi supplier · E-01/E-02/E-03) ─
    "supplier_items": [
        [("supplier_id", A), ("supplier_sku", A)],
        [("entity_id", A), ("created_at", D)],
        [("supplier_id", A), ("product_id", A), ("status", A)],
        [("product_id", A)],
        [("supplier_sku", A)],
        [("barcode", A)],
    ],
    "inventory_movements": [
        [("product_id", A), ("warehouse_id", A), ("timestamp", D)],
        [("owner_entity_id", A), ("timestamp", D)],
        [("roll_id", A)],
        [("lot_id", A)],
        [("movement_type", A), ("timestamp", D)],
        [("timestamp", D)],
    ],
    "inventory_balances": [
        [("product_id", A), ("warehouse_id", A), ("owner_entity_id", A)],
        [("warehouse_id", A)],
        [("owner_entity_id", A)],
    ],
    # ── Sales & Purchase Orders ───────────────────────────────────────────
    "sales_orders": [
        [("entity_id", A), ("status", A), ("created_at", D)],
        [("customer_id", A), ("created_at", D)],
        [("status", A), ("created_at", D)],
        [("number", A)],
        [("stage", A)],
        [("payment_status", A)],
        [("created_at", D)],
        # FASE L — penyaring lini di daftar & papan. `line_codes` adalah array
        # turunan dari baris; index multikey dipakai chip `?line=` supaya
        # penyaringan tidak COLLSCAN pada daftar terpanas.
        [("line_codes", A)],
    ],
    "purchase_orders": [
        [("entity_id", A), ("status", A), ("created_at", D)],
        [("supplier_id", A), ("created_at", D)],
        [("status", A), ("created_at", D)],
        [("warehouse_id", A), ("status", A)],
        [("line_codes", A)],   # FASE L
        [("po_number", A)],
        [("payment_status", A)],
        [("created_at", D)],
    ],
    "wms_tasks": [
        [("flow_type", A), ("status", A)],
        [("entity_id", A), ("status", A)],
        [("warehouse_id", A), ("status", A)],
        [("po_id", A)],
        [("product_id", A)],
        [("source_type", A), ("status", A)],
        [("created_at", D)],
    ],
    # ── Finance / GL ──────────────────────────────────────────────────────
    "journal_entries": [
        [("entity_id", A), ("date", D)],
        [("source_type", A), ("source_id", A)],
        [("status", A), ("date", D)],
        [("number", A)],
        [("date", D)],
    ],
    "gl_accounts": [
        [("entity_id", A), ("code", A)],
        [("type", A), ("is_active", A)],
        [("parent_code", A)],
    ],
    "gl_postings": [
        [("entity_id", A), ("account_code", A), ("date", D)],
        [("source_type", A), ("source_id", A)],
        [("date", D)],
    ],
    "vendor_bills": [
        [("entity_id", A), ("status", A), ("created_at", D)],
        [("supplier_id", A)],
        [("po_id", A)],
        [("makloon_order_id", A)],
        [("bill_number", A)],
        [("bill_date", D)],
    ],
    "ar_receipts": [
        [("entity_id", A), ("status", A), ("created_at", D)],
        [("customer_id", A)],
        [("number", A)],
        [("receipt_date", D)],
    ],
    "tax_invoices": [
        [("entity_id", A), ("status", A)],
        [("customer_id", A)],
        [("order_id", A)],
        [("number", A)],
        [("faktur_date", D)],
    ],
    # ── Master data ───────────────────────────────────────────────────────
    "customers": [
        [("entity_id", A), ("status", A)],
        [("assigned_sales_id", A)],
        [("customer_group_id", A)],
        [("code", A)],
        [("segment", A)],
    ],
    "suppliers": [
        [("entity_id", A), ("status", A)],
        [("code", A)],
        [("goods_type", A)],
    ],
    "products": [
        [("status", A)],
        [("category", A)],
        [("template_id", A)],
        [("stage", A)],
        [("supplier", A)],
        # FASE L — pagar & penyaring lini dipakai di SETIAP daftar produk
        # (katalog, POS, Master Produk), jadi ini index terpanas fase ini.
        [("line_code", A), ("status", A)],
    ],
    # ── FASE L — master lini produk (berlapis global → badan usaha) ────────
    # `(entity_id, code)` melayani `resolve_list_scope_inherit` + keunikan kunci
    # per lapisan; `(sort, code)` melayani urutan tampilan master & dropdown.
    "product_lines": [
        [("entity_id", A), ("code", A)],
        [("sort", A), ("code", A)],
        [("active", A)],
    ],
    # ── FASE T — master tahapan proses (berlapis global → badan usaha) ────
    # `(entity_id, code)` melayani `resolve_list_scope_inherit` + keunikan kunci per
    # lapisan; `(seq, code)` melayani urutan papan & dropdown langkah SPK;
    # `(process_type)` melayani gate INV-DOMAIN-06 (mencari tahap per jenis proses).
    "process_stages": [
        [("entity_id", A), ("code", A)],
        [("seq", A), ("code", A)],
        [("active", A)],
        [("process_type", A)],
        [("kind", A)],
    ],
    # ── Returns / Requisitions / Transfers / Cycle Count ──────────────────
    "purchase_returns": [
        [("entity_id", A), ("status", A), ("created_at", D)],
        [("supplier_id", A)],
        [("po_id", A)],
        [("number", A)],
    ],
    "sales_returns": [
        [("entity_id", A), ("status", A), ("created_at", D)],
        [("customer_id", A)],
        [("order_id", A)],
        [("number", A)],
    ],
    "purchase_requisitions": [
        [("entity_id", A), ("status", A), ("created_at", D)],
        [("approval_status", A)],
        [("po_id", A)],
        [("number", A)],
        [("line_codes", A)],   # FASE L
    ],
    "special_orders": [
        [("entity_id", A), ("status", A), ("created_at", D)],
        [("customer_id", A)],
        [("number", A)],
    ],
    "warehouse_transfers": [
        [("entity_id", A), ("status", A), ("created_at", D)],
        [("source_warehouse_id", A)],
        [("dest_warehouse_id", A)],
        [("code", A)],
    ],
    "cycle_count_sessions": [
        [("entity_id", A), ("status", A)],
        [("warehouse_id", A)],
        [("number", A)],
    ],
    "makloon_orders": [
        [("entity_id", A), ("status", A)],
        [("po_id", A)],
        [("mko_number", A)],
    ],
    # ── Audit & Notifications ─────────────────────────────────────────────
    "audit_logs": [
        [("entity_id", A), ("timestamp", D)],
        [("resource", A), ("resource_id", A)],
        [("user_id", A)],
        [("timestamp", D)],
    ],
    "notifications": [
        [("recipient_user", A), ("read", A)],
        [("recipient_role", A), ("read", A)],
        [("entity_id", A), ("created_at", D)],
        [("created_at", D)],
        [("dedupe_key", A)],          # R6.5 — dedupe notifikasi per (type, ref, hari)
        [("type", A), ("ref", A), ("read", A)],
    ],
    # ── R6.5 Scheduler & Outbox WhatsApp ──────────────────────────────────
    "sys_scheduler_runs": [
        [("job_id", A), ("started_at", D)],
        [("started_at", D)],
        [("status", A), ("started_at", D)],
    ],
    "sys_wa_outbox": [
        [("dedupe_key", A)],
        [("status", A), ("created_at", D)],
        [("created_at", D)],
        [("notification_id", A)],
    ],
    # FASE F — R&D: spesifikasi & permintaan sample (labdip/proofing)
    "md_specs": [
        [("entity_id", A), ("created_at", D)],
        [("status", A), ("created_at", D)],
        [("number", A)],
        [("product_id", A)],
    ],
    "md_samples": [
        [("entity_id", A), ("created_at", D)],
        [("status", A), ("created_at", D)],
        [("spec_id", A)],
        [("number", A)],
        [("sample_type", A), ("status", A)],
    ],
}


def _index_name(keys: IndexKeys) -> str:
    """Nama index deterministik & pendek (< 128 char)."""
    parts = []
    for field, direction in keys:
        suffix = "1" if direction == ASCENDING else "-1"
        parts.append(f"{field}_{suffix}")
    name = "kn_" + "__".join(parts)
    return name[:120]


async def ensure_performance_indexes() -> dict:
    """Buat semua index performa. Non-fatal & idempotent.

    Return ringkasan {created, existed, failed} untuk logging/verifikasi.
    """
    created = existed = failed = 0
    for collection, specs in INDEX_SPECS.items():
        coll = db[collection]
        # Ambil daftar index yang sudah ada agar hemat & log akurat.
        try:
            existing = set((await coll.index_information()).keys())
        except Exception:  # noqa: BLE001
            existing = set()
        for keys in specs:
            name = _index_name(keys)
            if name in existing:
                existed += 1
                continue
            try:
                await coll.create_index(keys, name=name, background=True)
                created += 1
            except Exception as exc:  # noqa: BLE001 — index bentrok / field issue
                failed += 1
                logger.warning("[indexes] %s.%s gagal: %s", collection, name, exc)
    summary = {"created": created, "existed": existed, "failed": failed}
    logger.info(
        "[indexes] performance indexes → created=%d existed=%d failed=%d",
        created, existed, failed,
    )
    return summary
