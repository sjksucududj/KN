"""FASE G-4 — **RELASI DOKUMEN TERSIMPAN** (`refs[]` dua arah) + Jejak Dokumen.

MASALAH NYATA PEMILIK
---------------------
*"SO customer pending → KN harus PO ke supplier → banyak surat lahir tapi saling
tidak mereferensikan → tracking & penelusuran retur susah."*

Sebelum fase ini relasi antar dokumen hanya **diturunkan saat dibaca**
(`document_relations_service`) dan hanya untuk 2 jangkar (SO & PO). Akibatnya:

* dokumen di tengah rantai (Faktur, Kwitansi, Nota Retur, Vendor Bill) **buntu** —
  tidak bisa dipakai sebagai titik masuk penelusuran;
* dokumen cetak tidak pernah menyebut nomor referensinya, sehingga penerima kertas
  tidak bisa menghubungkan surat satu dengan lainnya;
* tidak ada satu pun invarian yang bisa berkata "dokumen turunan ini yatim".

Fase ini menyimpan relasi sebagai **data** di setiap dokumen:

    refs: [{rel, doc_type, doc_id, doc_number, note, at}]

`rel` memakai kosakata tetap (lihat `REL_INVERSE`) dan **selalu ditulis dua arah**,
sehingga penelusuran bisa dimulai dari dokumen mana pun. Penulisan terjadi di titik
LAHIR dokumen (bukan batch semalam), plus `backfill()` idempotent untuk data lama.

Kenapa tidak menghapus `document_relations_service`? Karena layar lama (timeline SO/PO)
memakainya dan bentuk "stage" itu masih berguna. G-4 menambah lapisan **fakta tersimpan**
di bawahnya; keduanya tidak saling meniadakan dan invarian INV-REF menjaga agar fakta
tersimpan tidak tertinggal dari kenyataan.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core_utils import now_iso, safe_doc
from db import db
from services.config_resolver import resolve

# ── Kosakata relasi ─────────────────────────────────────────────────────────
# `rel` dibaca dari sudut pandang PEMILIK dokumen terhadap TARGET-nya.
REL_INVERSE: Dict[str, str] = {
    "parent": "child",
    "child": "parent",
    "amends": "amended_by",
    "amended_by": "amends",
    "corrects": "corrected_by",
    "corrected_by": "corrects",
    "reverses": "reversed_by",
    "reversed_by": "reverses",
    "settles": "settled_by",
    "settled_by": "settles",
    "fulfills": "fulfilled_by",
    "fulfilled_by": "fulfills",
    "issued": "issued_by",
    "issued_by": "issued",
    "replaces": "replaced_by",
    "replaced_by": "replaces",
}

REL_LABEL: Dict[str, str] = {
    "parent": "Berasal dari",
    "child": "Menurunkan",
    "amends": "Mengamandemen",
    "amended_by": "Diamandemen oleh",
    "corrects": "Mengoreksi",
    "corrected_by": "Dikoreksi oleh",
    "reverses": "Membalik",
    "reversed_by": "Dibalik oleh",
    "settles": "Melunasi",
    "settled_by": "Dilunasi oleh",
    "fulfills": "Memenuhi",
    "fulfilled_by": "Dipenuhi oleh",
    "issued": "Menerbitkan",
    "issued_by": "Diterbitkan oleh",
    "replaces": "Mengganti",
    "replaced_by": "Diganti oleh",
    "applied_to": "Diterapkan ke",
}

# Relasi yang menandakan "saya lahir dari dokumen lain" → dipakai INV-REF-01.
PARENT_RELS = {"parent", "amends", "corrects", "reverses", "settles", "fulfills", "issued_by"}


# ── Peta jenis dokumen (SATU tempat; jangan disalin ke skrip lain) ──────────
def _T(doc_type: str, collection: str, number: str, label: str,
       view: str = "", focus_type: str = "", order: int = 50,
       needs_parent: bool = False, filter_: Optional[Dict[str, Any]] = None,
       source_fk: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Satu baris peta dokumen.

    `source_fk` = kolom penghubung NYATA yang menandakan dokumen ini memang LAHIR
    dari dokumen lain (mis. `wms_tasks.po_id`). Dipakai INV-REF-01 supaya invarian
    JUJUR: surat yang punya sumber wajib menaut sumbernya, sedangkan dokumen yang
    sah berdiri sendiri (penerimaan tanpa PO, kwitansi uang muka tanpa alokasi,
    tagihan biaya langsung tanpa PO) tidak dituduh yatim. Tanpa pembedaan ini gate
    akan memerah karena transaksi yang benar — dan gate yang "memerah palsu" cepat
    diabaikan orang.
    """
    return {"doc_type": doc_type, "collection": collection, "number": number,
            "label": label, "view": view, "focus_type": focus_type or doc_type,
            "order": order, "needs_parent": needs_parent, "filter": filter_ or {},
            "source_fk": list(source_fk or [])}


DOC_TYPES: Dict[str, Dict[str, Any]] = {d["doc_type"]: d for d in [
    _T("special_order", "special_orders", "number", "Special Order", "special-orders", order=5),
    _T("purchase_requisition", "purchase_requisitions", "number", "Purchase Requisition",
       "purchase-requisitions", order=10),
    _T("rfq", "rfqs", "number", "Permintaan Penawaran (RFQ)", "rfq", order=12),
    _T("supplier_contract", "supplier_contracts", "contract_number", "Kontrak Supplier",
       "supplier-contracts", order=14),
    _T("purchase_order", "purchase_orders", "po_number", "Purchase Order", "purchasing", order=20),
    _T("grn", "wms_tasks", "id", "Penerimaan Barang (GRN)", "operations", order=25,
       needs_parent=True, filter_={"flow_type": "inbound"}, source_fk=["po_id"]),
    _T("landed_cost", "landed_cost_vouchers", "number", "Voucher Landed Cost", "landed-cost",
       order=27, needs_parent=True, source_fk=["po_ids"]),
    _T("vendor_bill", "vendor_bills", "bill_number", "Tagihan Supplier (Kontrabon)",
       "vendor-bills", order=30, needs_parent=True, source_fk=["po_id", "makloon_order_id"]),
    # FASE G-7 — kontrabon: satu dokumen menggabungkan banyak faktur supplier satu siklus.
    _T("contra_bon", "contra_bons", "number", "Kontrabon (Tukar Faktur)", "contra-bons",
       order=31),
    _T("purchase_return", "purchase_returns", "number", "Retur Beli", "purchase-returns",
       order=32, needs_parent=True, source_fk=["po_id"]),
    _T("makloon_order", "makloon_orders", "mko_number", "Order Makloon", "makloon-orders", order=35),
    _T("sales_order", "sales_orders", "number", "Sales Order", "orders", order=40),
    _T("picking_task", "wms_tasks", "id", "Tugas Pengambilan", "operations", order=42,
       needs_parent=True, filter_={"flow_type": "outbound"}, source_fk=["order_id"]),
    _T("shipment", "shipments", "shipment_no", "Surat Jalan / Pengiriman", "orders",
       order=44, needs_parent=True, source_fk=["order_id"]),
    _T("tax_invoice", "tax_invoices", "number", "Faktur Pajak", "tax-invoices",
       order=46, needs_parent=True, source_fk=["order_id", "replaces_id"]),
    _T("ar_receipt", "ar_receipts", "number", "Kwitansi / Pembayaran", "customers-crm",
       order=48, needs_parent=True, source_fk=["allocations"]),
    _T("sales_return", "sales_returns", "number", "Retur Jual", "sales-returns",
       order=50, needs_parent=True, source_fk=["order_id"]),
    _T("doc_amendment", "doc_amendments", "number", "Amandemen Dokumen", "amendments",
       order=52, needs_parent=True, source_fk=["doc_id"]),
    _T("credit_note", "credit_notes", "number", "Nota Kredit / Debit", "amendments",
       order=54, needs_parent=True, source_fk=["order_id", "amendment_id"]),
    # FASE G-2 — jadwal bayar & nota denda adalah DOKUMEN (bisa ditelusuri & dicetak).
    _T("payment_plan", "payment_plans", "number", "Rencana Pembayaran", "payment-plans",
       order=56, needs_parent=True, source_fk=["doc_id"]),
    _T("penalty", "penalties", "number", "Nota Denda Keterlambatan", "payment-plans",
       order=58, needs_parent=True, source_fk=["doc_id"]),
    # FASE G-3 — keputusan selisih pembayaran (lebih/kurang bayar) juga DOKUMEN bernomor.
    _T("payment_variance", "payment_variance_decisions", "number",
       "Keputusan Selisih Pembayaran", "payment-plans", order=59, needs_parent=True,
       source_fk=["receipt_id", "bill_id"]),
    _T("warehouse_transfer", "warehouse_transfers", "code", "Surat Jalan Transfer",
       "transfers", order=60),
    # FASE G-6 — antar-PT adalah JUAL-BELI: dokumen kembar (SO/SJ/Invoice internal di
    # penjual, PO internal/Vendor Bill di pembeli) + settlement/netting. Tanpa
    # terdaftar di sini, dokumen antar-PT tidak bisa ditelusuri/dicetak dari Pusat
    # Dokumen dan jejak "barangnya pindah lewat tugas gudang mana" berhenti.
    _T("interco_transaction", "interco_transactions", "number",
       "Transaksi Antar-PT (Jual-Beli Internal)", "interco-transactions", order=64),
    _T("interco_settlement", "interco_settlements", "number",
       "Settlement Antar-PT (Netting)", "interco-transactions", order=65),
    # FASE G-6b — retur antar-PT (dokumen kembar nota retur ↔ nota kredit internal)
    # & faktur pajak MASUKAN internal (pasangan faktur keluaran di PT penjual).
    _T("interco_return", "interco_returns", "number",
       "Retur Antar-PT", "interco-transactions", order=66),
    _T("input_tax_invoice", "tax_invoices_in", "number",
       "Faktur Pajak Masukan", "input-tax", order=67),
    _T("cycle_count", "cycle_count_sessions", "number", "Stock Opname", "cycle-count", order=62),
    # FASE F — R&D: spesifikasi & permintaan sample adalah DOKUMEN bernomor yang
    # menjadi HULU rantai (spec → sample → kontrak → PO). Tanpa ini kontrak harga
    # tidak bisa menjawab "harga ini dari mana".
    _T("md_spec", "md_specs", "number", "Spesifikasi Produk (R&D)", "rnd-specs", order=2),
    _T("md_sample", "md_samples", "number", "Permintaan Sample (Labdip/Proofing)",
       "rnd-samples", order=3, needs_parent=False, source_fk=["spec_id"]),
    # FASE G-9 — kasus keuangan adalah DOKUMEN bernomor: sumbernya (kwitansi/mutasi/tagihan)
    # dan dokumen turunannya (jurnal/kas/nota denda) harus bisa ditelusuri dua arah.
    _T("finance_case", "finance_cases", "number", "Kasus Keuangan", "finance-cases",       order=61, needs_parent=False),
    # FASE G-7 — pembayaran kontrabon adalah SATU transaksi kas untuk banyak faktur.
    # Tanpa jenis dokumen ini, jejak "uang keluarnya lewat mana" berhenti di kontrabon
    # dan petugas harus mencari sendiri di layar Kas & Bank.
    _T("cash_transaction", "cash_transactions", "number", "Transaksi Kas / Bank",
       "cash-bank", order=63, needs_parent=False),
    # FASE E-7 (E7d) — permintaan internal adalah HULU transaksi antar-PT: tanpa
    # terdaftar di sini, pertanyaan "transaksi antar-PT ini untuk siapa/kenapa"
    # berhenti di catatan bebas.
    _T("internal_request", "internal_requests", "number",
       "Permintaan Internal (Antar-PT)", "internal-requests", order=6),
    # FASE E-7 (E7f) — pinjaman uang antar-PT (dokumen kembar piutang ↔ utang).
    _T("interco_loan", "interco_loans", "number",
       "Pinjaman Antar-PT", "interco-transactions", order=68),
]}

# Koleksi → doc_type kanonik (untuk PDF doc_type yang berbagi koleksi, mis. `invoice`
# & `delivery_note` sama-sama berasal dari `sales_orders`).
COLLECTION_TO_TYPE: Dict[str, str] = {}
for _d in DOC_TYPES.values():
    if not _d["filter"]:
        COLLECTION_TO_TYPE.setdefault(_d["collection"], _d["doc_type"])


class RefsError(ValueError):
    """Kesalahan relasi dokumen dengan pesan siap tampil (Bahasa Indonesia)."""


# ── Konfigurasi (registry FASE G-0 — tidak ada angka hardcode) ──────────────
async def _cfg(key: str, entity_id: str = "") -> Any:
    res = await resolve(key, {"entity_id": entity_id or ""})
    return res["value"]


async def autolink_enabled(entity_id: str = "") -> bool:
    return bool(await _cfg("docref.autolink_enabled", entity_id))


async def trace_max_depth(entity_id: str = "") -> int:
    return int(await _cfg("docref.trace_max_depth", entity_id))


async def parent_required(entity_id: str = "") -> bool:
    """Dipakai INV-REF-01: apakah dokumen turunan WAJIB punya induk hidup."""
    return bool(await _cfg("docref.require_parent", entity_id))


async def pdf_options(entity_id: str = "") -> Dict[str, Any]:
    """Opsi blok referensi pada dokumen cetak (dibaca `services/pdf_service.py`)."""
    return {
        "show": bool(await _cfg("docref.show_in_pdf", entity_id)),
        "qr": bool(await _cfg("docref.qr_in_pdf", entity_id)),
        "max": int(await _cfg("docref.pdf_max_refs", entity_id)),
    }


# ── Util dokumen ────────────────────────────────────────────────────────────
def type_of_collection(collection: str) -> str:
    return COLLECTION_TO_TYPE.get(collection, "")


def _meta(doc_type: str) -> Dict[str, Any]:
    meta = DOC_TYPES.get(doc_type)
    if not meta:
        raise RefsError(f"Jenis dokumen '{doc_type}' belum terdaftar di peta relasi.")
    return meta


async def load_doc(doc_type: str, doc_id: str) -> Optional[Dict[str, Any]]:
    meta = _meta(doc_type)
    row = await db[meta["collection"]].find_one({"id": doc_id}, {"_id": 0})
    return safe_doc(row) if row else None


def number_of(doc_type: str, doc: Dict[str, Any]) -> str:
    """Nomor dokumen yang LAYAK DICETAK.

    `wms_tasks` tidak punya nomor manusiawi (hanya id teknis `wms_xxx`) — kalau id itu
    ikut tercetak di kop dokumen, pembaca kertas melihat sampah. Karena itu tugas
    gudang diberi nomor turunan yang bisa dibaca (`GRN-XXXXXX` / `PICK-XXXXXX`) sambil
    tetap merujuk id aslinya di data.
    """
    meta = DOC_TYPES.get(doc_type) or {}
    field = meta.get("number") or "number"
    if doc_type in ("grn", "picking_task"):
        prefix = "GRN" if doc_type == "grn" else "PICK"
        tail = str(doc.get("id") or "")[-6:].upper()
        return f"{prefix}-{tail}" if tail else prefix
    return str(doc.get(field) or doc.get("number") or doc.get("id") or "")


def _title_of(doc_type: str, doc: Dict[str, Any]) -> str:
    for k in ("customer_name", "supplier_name", "makloon_name", "product_name",
              "partner_name", "warehouse_name", "reason_label", "description"):
        if doc.get(k):
            return str(doc[k])
    return DOC_TYPES.get(doc_type, {}).get("label", doc_type)


def _amount_of(doc: Dict[str, Any]) -> float:
    for k in ("grand_total", "total_amount", "amount", "gross_amount", "net_amount",
              "total_est_amount"):
        if doc.get(k) not in (None, ""):
            try:
                return float(doc[k])
            except (TypeError, ValueError):
                continue
    return 0.0


def _date_of(doc: Dict[str, Any]) -> str:
    for k in ("created_at", "receipt_date", "faktur_date", "order_date", "bill_date", "date"):
        if doc.get(k):
            return str(doc[k])
    return ""


def node_of(doc_type: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    meta = DOC_TYPES.get(doc_type, {})
    return {
        "key": f"{doc_type}:{doc.get('id')}",
        "doc_type": doc_type, "doc_id": doc.get("id"),
        "label": meta.get("label", doc_type),
        "number": number_of(doc_type, doc),
        "title": _title_of(doc_type, doc),
        "status": doc.get("status") or doc.get("payment_status") or "",
        "date": _date_of(doc),
        "amount": _amount_of(doc),
        "entity_id": doc.get("entity_id") or "",
        "link": {"view": meta.get("view", ""), "focus_type": meta.get("focus_type", doc_type),
                 "focus_id": doc.get("id")},
        "order": meta.get("order", 50),
    }


# ── Penulisan relasi (dua arah, idempotent) ────────────────────────────────
def _same(a: Dict[str, Any], rel: str, doc_type: str, doc_id: str) -> bool:
    return (a.get("rel") == rel and a.get("doc_type") == doc_type
            and a.get("doc_id") == doc_id)


async def _push_ref(holder_type: str, holder_id: str, ref: Dict[str, Any]) -> bool:
    """Tulis 1 ref ke dokumen pemilik bila belum ada. Return True bila menambah."""
    meta = _meta(holder_type)
    coll = db[meta["collection"]]
    holder = await coll.find_one({"id": holder_id}, {"_id": 0, "refs": 1})
    # CATATAN: proyeksi `{_id:0, refs:1}` mengembalikan **dict kosong** untuk dokumen
    # yang belum punya `refs` — dan dict kosong itu falsy. Karena itu perbandingannya
    # WAJIB `is None`, bukan `not holder` (bug ini membuat backfill "berhasil" 0 tautan).
    if holder is None:
        return False
    for existing in holder.get("refs") or []:
        if _same(existing, ref["rel"], ref["doc_type"], ref["doc_id"]):
            return False
    await coll.update_one({"id": holder_id},
                          {"$push": {"refs": ref}, "$set": {"updated_at": now_iso()}})
    return True


async def link(src: Tuple[str, str], dst: Tuple[str, str], rel: str,
               note: str = "", force: bool = False) -> Dict[str, Any]:
    """Tautkan dua dokumen **dua arah**.

    `src` melihat `dst` sebagai `rel`; `dst` otomatis melihat `src` sebagai
    `REL_INVERSE[rel]`. Aman dipanggil berulang (dedupe by rel+target).

    Dipakai di titik LAHIR dokumen turunan; kegagalan tidak boleh menggagalkan
    transaksi bisnis (pemanggil membungkus dengan try/except).
    """
    if rel not in REL_INVERSE:
        raise RefsError(f"Relasi '{rel}' tidak dikenal. Pilihan: {', '.join(sorted(REL_INVERSE))}.")
    src_type, src_id = src
    dst_type, dst_id = dst
    if not (src_id and dst_id):
        return {"linked": 0, "reason": "id kosong"}
    src_doc = await load_doc(src_type, src_id)
    dst_doc = await load_doc(dst_type, dst_id)
    if not src_doc or not dst_doc:
        return {"linked": 0, "reason": "dokumen tidak ditemukan"}
    if not force and not await autolink_enabled(src_doc.get("entity_id") or ""):
        return {"linked": 0, "reason": "autolink dimatikan admin"}

    at = now_iso()
    a = await _push_ref(src_type, src_id, {
        "rel": rel, "doc_type": dst_type, "doc_id": dst_id,
        "doc_number": number_of(dst_type, dst_doc), "note": note, "at": at})
    b = await _push_ref(dst_type, dst_id, {
        "rel": REL_INVERSE[rel], "doc_type": src_type, "doc_id": src_id,
        "doc_number": number_of(src_type, src_doc), "note": note, "at": at})
    return {"linked": int(a) + int(b), "src": f"{src_type}:{src_id}", "dst": f"{dst_type}:{dst_id}",
            "rel": rel}


async def link_child(parent: Tuple[str, str], child: Tuple[str, str],
                     note: str = "", force: bool = False) -> Dict[str, Any]:
    """Gula sintaksis: dokumen turunan menunjuk induknya (`parent`) dan sebaliknya."""
    return await link(child, parent, "parent", note=note, force=force)


async def safe_link(src: Tuple[str, str], dst: Tuple[str, str], rel: str,
                    note: str = "") -> None:
    """Versi `link()` untuk dipasang di jalur transaksi bisnis.

    Penautan referensi adalah pelengkap jejak, BUKAN syarat sahnya transaksi:
    kegagalan (dokumen belum tersimpan, koleksi baru, dsb.) tidak boleh membatalkan
    pembuatan surat jalan/faktur/kwitansi. Karena itu semua galat ditelan di sini —
    dan `INV-REF-01/02` yang akan berteriak bila ada relasi yang tertinggal.
    """
    try:
        await link(src, dst, rel, note=note)
    except Exception:  # noqa: BLE001
        return


async def refs_of(doc_type: str, doc_id: str, resolve_targets: bool = True) -> Dict[str, Any]:
    """Daftar referensi sebuah dokumen + status hidup/mati targetnya."""
    doc = await load_doc(doc_type, doc_id)
    if not doc:
        raise RefsError("Dokumen tidak ditemukan.")
    out: List[Dict[str, Any]] = []
    for r in doc.get("refs") or []:
        row = dict(r)
        row["rel_label"] = REL_LABEL.get(r.get("rel", ""), r.get("rel", ""))
        row["label"] = DOC_TYPES.get(r.get("doc_type", ""), {}).get("label", r.get("doc_type", ""))
        row["known_type"] = r.get("doc_type") in DOC_TYPES
        if resolve_targets and row["known_type"]:
            tgt = await load_doc(r["doc_type"], r["doc_id"])
            row["alive"] = bool(tgt)
            if tgt:
                row["doc_number"] = number_of(r["doc_type"], tgt)
                row["status"] = tgt.get("status") or ""
                row["link"] = node_of(r["doc_type"], tgt)["link"]
        out.append(row)
    return {"doc_type": doc_type, "doc_id": doc_id,
            "number": number_of(doc_type, doc), "refs": out,
            "anchor": node_of(doc_type, doc)}


# ── Penelusuran (graf dari jangkar mana pun) ───────────────────────────────
async def trace(doc_type: str, doc_id: str, depth: Optional[int] = None) -> Dict[str, Any]:
    """Telusuri seluruh rantai dokumen dari jangkar mana pun (BFS atas `refs[]`).

    Kedalaman dibatasi `docref.trace_max_depth` (configurable) supaya graf besar
    tidak membekukan UI; sisa simpul dilaporkan lewat `truncated`.
    """
    anchor_doc = await load_doc(doc_type, doc_id)
    if not anchor_doc:
        raise RefsError("Dokumen tidak ditemukan.")
    max_depth = int(depth or await trace_max_depth(anchor_doc.get("entity_id") or ""))
    max_depth = max(1, min(max_depth, 8))

    seen: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    edge_seen = set()
    queue: List[Tuple[str, str, int]] = [(doc_type, doc_id, 0)]
    anchor_key = f"{doc_type}:{doc_id}"
    truncated = 0

    while queue:
        cur_type, cur_id, level = queue.pop(0)
        key = f"{cur_type}:{cur_id}"
        if key in seen:
            continue
        cur_doc = await load_doc(cur_type, cur_id)
        if not cur_doc:
            continue
        node = node_of(cur_type, cur_doc)
        node["level"] = level
        node["is_anchor"] = key == anchor_key
        seen[key] = node
        if level >= max_depth:
            truncated += len(cur_doc.get("refs") or [])
            continue
        for r in cur_doc.get("refs") or []:
            t, i = r.get("doc_type"), r.get("doc_id")
            if not t or not i or t not in DOC_TYPES:
                continue
            ekey = "|".join(sorted([key, f"{t}:{i}"]))
            if ekey not in edge_seen:
                edge_seen.add(ekey)
                edges.append({"from": key, "to": f"{t}:{i}", "rel": r.get("rel", ""),
                              "rel_label": REL_LABEL.get(r.get("rel", ""), r.get("rel", "")),
                              "note": r.get("note", "")})
            if f"{t}:{i}" not in seen:
                queue.append((t, i, level + 1))

    nodes = sorted(seen.values(), key=lambda n: (n["order"], n.get("date") or ""))
    groups: List[Dict[str, Any]] = []
    for n in nodes:
        g = next((x for x in groups if x["doc_type"] == n["doc_type"]), None)
        if not g:
            g = {"doc_type": n["doc_type"], "label": n["label"],
                 "order": n["order"], "docs": []}
            groups.append(g)
        g["docs"].append(n)
    groups.sort(key=lambda g: g["order"])

    return {"anchor": seen.get(anchor_key), "doc_type": doc_type, "doc_id": doc_id,
            "depth": max_depth, "nodes": nodes, "edges": edges, "groups": groups,
            "node_count": len(nodes), "edge_count": len(edges), "truncated": truncated}


async def reference_line(doc_type: str, doc_id: str, limit: int = 6) -> Dict[str, Any]:
    """Baris "Merujuk: SO-0012 · PR-00021" untuk kop dokumen cetak.

    Urutan sengaja mengutamakan dokumen INDUK (asal-usul) karena itu yang dicari
    pembaca kertas; turunan/pelunasan menyusul bila masih ada tempat.
    """
    try:
        data = await refs_of(doc_type, doc_id, resolve_targets=True)
    except RefsError:
        return {"text": "", "items": []}
    items: List[Dict[str, str]] = []
    for r in data["refs"]:
        num = r.get("doc_number") or ""
        # Dokumen yang sudah tidak ada TIDAK dicetak — kertas tidak boleh menunjuk hantu.
        if not num or r.get("alive") is False:
            continue
        items.append({"rel": r.get("rel", ""), "rel_label": r.get("rel_label", ""),
                      "label": r.get("label", ""), "number": num,
                      "doc_type": r.get("doc_type", ""), "doc_id": r.get("doc_id", "")})
    items.sort(key=lambda x: (0 if x["rel"] in PARENT_RELS else 1,
                              DOC_TYPES.get(x["doc_type"], {}).get("order", 50)))
    seen_num = set()
    uniq = []
    for it in items:
        if it["number"] in seen_num:
            continue
        seen_num.add(it["number"])
        uniq.append(it)
    shown = uniq[: max(1, int(limit or 6))]
    return {"text": " · ".join(x["number"] for x in shown),
            "items": shown, "total": len(uniq), "hidden": max(0, len(uniq) - len(shown))}


# ── Pencarian dokumen (titik masuk layar Jejak Dokumen) ────────────────────
async def search(q: str, limit: int = 20, entity_id: str = "") -> List[Dict[str, Any]]:
    """Cari dokumen lintas jenis berdasarkan nomor / nama pihak."""
    ql = (q or "").strip()
    if len(ql) < 2:
        return []
    import re as _re
    rx = _re.compile(_re.escape(ql), _re.I)
    out: List[Dict[str, Any]] = []
    for meta in sorted(DOC_TYPES.values(), key=lambda m: m["order"]):
        if len(out) >= limit:
            break
        flt: Dict[str, Any] = dict(meta["filter"])
        or_clauses: List[Dict[str, Any]] = [
            {meta["number"]: rx}, {"customer_name": rx}, {"supplier_name": rx}]
        flt["$or"] = or_clauses
        if entity_id and entity_id != "all":
            flt["entity_id"] = entity_id
        try:
            rows = await db[meta["collection"]].find(flt, {"_id": 0}).limit(5).to_list(5)
        except Exception:  # noqa: BLE001 — koleksi belum ada di DB baru
            continue
        for row in rows:
            node = node_of(meta["doc_type"], safe_doc(row))
            node["ref_count"] = len(row.get("refs") or [])
            out.append(node)
    return out[:limit]


# ── Backfill data lama (idempotent, aman diulang) ──────────────────────────
async def _iter(collection: str, flt: Dict[str, Any], fields: Sequence[str]):
    proj = {"_id": 0, "id": 1}
    for f in fields:
        proj[f] = 1
    async for row in db[collection].find(flt, proj):
        yield row


async def backfill(dry_run: bool = True) -> Dict[str, Any]:
    """Bentuk `refs[]` dari kolom penghubung yang SUDAH ada di dokumen lama.

    Tidak mengarang relasi: setiap aturan memakai foreign key nyata yang memang
    dipakai mesin (mis. `shipments.order_id`). Idempotent — menjalankan berkali-kali
    tidak menduplikasi karena `_push_ref` melakukan dedupe.
    """
    plan: List[Dict[str, str]] = []

    async def rule(src_type: str, dst_type: str, rel: str, collection: str,
                   fk: str, flt: Optional[Dict[str, Any]] = None, note: str = "") -> None:
        base = dict(flt or {})
        base[fk] = {"$nin": [None, ""]}
        async for row in _iter(collection, base, [fk]):
            plan.append({"src_type": src_type, "src_id": row["id"], "dst_type": dst_type,
                         "dst_id": row[fk], "rel": rel, "note": note})

    # Rantai pembelian
    await rule("purchase_order", "purchase_requisition", "parent",
               "purchase_requisitions", "po_id", note="PR sumber PO")
    await rule("grn", "purchase_order", "parent", "wms_tasks", "po_id",
               flt={"flow_type": "inbound"}, note="penerimaan dari PO")
    await rule("vendor_bill", "purchase_order", "parent", "vendor_bills", "po_id",
               note="tagihan atas PO")
    await rule("purchase_return", "purchase_order", "reverses", "purchase_returns", "po_id",
               note="retur atas PO")
    await rule("makloon_order", "purchase_order", "parent", "makloon_orders", "po_id")
    await rule("makloon_order", "supplier_contract", "fulfills", "makloon_orders", "contract_id",
               note="kontrak makloon")
    await rule("vendor_bill", "makloon_order", "settles", "vendor_bills", "makloon_order_id",
               note="tagihan jasa makloon")

    # Rantai penjualan
    await rule("sales_order", "special_order", "parent", "sales_orders",
               "source_special_order_id", note="berasal dari Special Order")
    await rule("picking_task", "sales_order", "parent", "wms_tasks", "order_id",
               flt={"flow_type": "outbound"}, note="pengambilan untuk SO")
    await rule("shipment", "sales_order", "parent", "shipments", "order_id",
               note="pengiriman atas SO")
    await rule("tax_invoice", "sales_order", "parent", "tax_invoices", "order_id",
               note="faktur atas SO")
    await rule("tax_invoice", "tax_invoice", "replaces", "tax_invoices", "replaces_id",
               note="faktur pengganti")
    await rule("sales_return", "sales_order", "reverses", "sales_returns", "order_id",
               note="retur atas SO")
    await rule("credit_note", "sales_order", "corrects", "credit_notes", "order_id")
    await rule("credit_note", "doc_amendment", "issued_by", "credit_notes", "amendment_id")
    await rule("doc_amendment", "sales_order", "amends", "doc_amendments", "doc_id")
    # FASE G-2 — rencana pembayaran & nota denda menaut dokumen sumbernya.
    await rule("payment_plan", "sales_order", "parent", "payment_plans", "doc_id",
               note="jadwal pembayaran dokumen ini")
    await rule("penalty", "sales_order", "parent", "penalties", "doc_id",
               note="denda keterlambatan")

    # Landed cost menaut BANYAK PO (array) — ditangani terpisah.
    async for row in db.landed_cost_vouchers.find({"po_ids": {"$exists": True}},
                                                  {"_id": 0, "id": 1, "po_ids": 1}):
        for poid in row.get("po_ids") or []:
            plan.append({"src_type": "landed_cost", "src_id": row["id"],
                         "dst_type": "purchase_order", "dst_id": poid,
                         "rel": "parent", "note": "biaya masuk untuk PO"})

    # Kwitansi menaut BANYAK order lewat alokasi.
    async for row in db.ar_receipts.find({}, {"_id": 0, "id": 1, "allocations": 1}):
        for alloc in row.get("allocations") or []:
            if alloc.get("order_id"):
                plan.append({"src_type": "ar_receipt", "src_id": row["id"],
                             "dst_type": "sales_order", "dst_id": alloc["order_id"],
                             "rel": "settles", "note": "pembayaran dialokasikan"})

    would, wrote, skipped = 0, 0, 0
    for p in plan:
        if dry_run:
            src = await load_doc(p["src_type"], p["src_id"])
            dst = await load_doc(p["dst_type"], p["dst_id"])
            if not src or not dst:
                skipped += 1
                continue
            have = any(_same(r, p["rel"], p["dst_type"], p["dst_id"])
                       for r in (src.get("refs") or []))
            if not have:
                would += 1
            continue
        res = await link((p["src_type"], p["src_id"]), (p["dst_type"], p["dst_id"]),
                         p["rel"], note=p["note"], force=True)
        wrote += int(res.get("linked", 0))
        if not res.get("linked"):
            skipped += 1

    return {"dry_run": dry_run, "candidates": len(plan), "would_add": would,
            "written": wrote, "skipped": skipped}


# ── Bahan invarian INV-REF (dibaca `scripts/verify_data_integrity.py`) ─────
def _has_source(row: Dict[str, Any], fks: Sequence[str]) -> bool:
    """True bila dokumen memang punya kolom penghubung berisi (lahir dari dokumen lain)."""
    if not fks:
        return True  # tidak ada info FK → tetap wajib menaut (perilaku ketat sebelumnya)
    for f in fks:
        val = row.get(f)
        if isinstance(val, (list, tuple)):
            if any(bool(v) for v in val):
                return True
        elif val not in (None, "", 0):
            return True
    return False


async def orphan_children(limit: int = 50) -> List[Dict[str, Any]]:
    """Dokumen turunan yang TIDAK punya satu pun referensi induk yang hidup.

    Dokumen yang memang berdiri sendiri (tidak punya kolom sumber apa pun — mis.
    penerimaan barang tanpa PO, kwitansi uang muka tanpa alokasi invoice) TIDAK
    dilaporkan yatim: lihat `standalone_children()` untuk angka transparansinya.
    """
    bad: List[Dict[str, Any]] = []
    for meta in DOC_TYPES.values():
        if not meta["needs_parent"]:
            continue
        flt = dict(meta["filter"])
        proj = {"_id": 0, "id": 1, "refs": 1, meta["number"]: 1}
        for f in meta.get("source_fk") or []:
            proj[f] = 1
        async for row in db[meta["collection"]].find(flt, proj):
            if not _has_source(row, meta.get("source_fk") or []):
                continue
            parents = [r for r in (row.get("refs") or [])
                       if r.get("rel") in PARENT_RELS and r.get("doc_id")]
            alive = False
            for p in parents:
                if p.get("doc_type") in DOC_TYPES and await load_doc(p["doc_type"], p["doc_id"]):
                    alive = True
                    break
            if not alive:
                bad.append({"doc_type": meta["doc_type"], "doc_id": row["id"],
                            "number": row.get(meta["number"]) or row["id"]})
                if len(bad) >= limit:
                    return bad
    return bad


async def standalone_children(limit: int = 200) -> List[Dict[str, Any]]:
    """Dokumen turunan yang SAH tanpa induk (tidak punya kolom sumber sama sekali).

    Dilaporkan eksplisit oleh gate & `scripts/audit_doc_refs.py` supaya tidak menjadi
    tempat sembunyi: kalau angka ini melonjak, ada jalur pembuatan dokumen yang lupa
    menyimpan kolom sumbernya.
    """
    out: List[Dict[str, Any]] = []
    for meta in DOC_TYPES.values():
        if not meta["needs_parent"] or not meta.get("source_fk"):
            continue
        flt = dict(meta["filter"])
        proj = {"_id": 0, "id": 1, meta["number"]: 1}
        for f in meta["source_fk"]:
            proj[f] = 1
        async for row in db[meta["collection"]].find(flt, proj):
            if _has_source(row, meta["source_fk"]):
                continue
            out.append({"doc_type": meta["doc_type"], "doc_id": row["id"],
                        "number": row.get(meta["number"]) or row["id"]})
            if len(out) >= limit:
                return out
    return out


async def one_way_refs(limit: int = 50) -> List[Dict[str, Any]]:
    """Relasi yang hanya ada di satu sisi (tidak bisa ditelusuri balik)."""
    bad: List[Dict[str, Any]] = []
    for meta in DOC_TYPES.values():
        flt = dict(meta["filter"])
        flt["refs"] = {"$exists": True, "$ne": []}
        async for row in db[meta["collection"]].find(flt, {"_id": 0, "id": 1, "refs": 1}):
            for r in row.get("refs") or []:
                t, i = r.get("doc_type"), r.get("doc_id")
                if not t or not i or t not in DOC_TYPES:
                    continue
                tgt = await load_doc(t, i)
                if not tgt:
                    continue  # target mati → urusan INV-REF-01, bukan dua arah
                back = [b for b in (tgt.get("refs") or [])
                        if b.get("doc_id") == row["id"] and b.get("doc_type") == meta["doc_type"]]
                if not back:
                    bad.append({"from": f"{meta['doc_type']}:{row['id']}",
                                "to": f"{t}:{i}", "rel": r.get("rel", "")})
                    if len(bad) >= limit:
                        return bad
    return bad
