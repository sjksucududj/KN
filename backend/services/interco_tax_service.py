"""FASE G-6b — **FAKTUR PAJAK INTERNAL** untuk transaksi antar-PT ber-PPN.

MASALAH NYATA
-------------
G-6 sudah menghitung PPN antar-PT dengan benar **di jurnal** (PPN Keluaran di buku
penjual == PPN Masukan di buku pembeli, INV-IC-05). Tetapi jurnal bukan dokumen
pajak. Kalau PT KSC menjual ke CV Kanda ber-PPN 11%, kedua PT tetap wajib punya
**faktur pajak yang bisa dicetak, dilaporkan, dan direkap** — penjual sebagai
Faktur Pajak Keluaran, pembeli sebagai Faktur Pajak Masukan yang dikreditkan.
Sebelum modul ini, PPN antar-PT tidak pernah muncul di **Pusat Pajak** (rekap
`vat_summary` hanya melihat `tax_invoices` dari pesanan penjualan dan
`tax_invoices_in` dari tagihan supplier) → posisi PPN kurang/lebih bayar tiap PT
SALAH untuk semua transaksi internal.

DESAIN (kenapa begini)
----------------------
* **Tidak membuat koleksi baru.** Dokumen internal masuk ke koleksi pajak yang
  SUDAH ADA — `tax_invoices` (keluaran) & `tax_invoices_in` (masukan) — dengan
  penanda `source_type="interco"` + `interco_pair_id`. Konsekuensi langsung:
  rekap `vat_summary`, layar Pusat Pajak, dan Faktur Masukan otomatis ikut
  memperhitungkannya tanpa satu baris kode tambahan di sana.
* **Kembar, seperti dokumen G-6 lainnya.** Satu dokumen per PT, saling menunjuk
  (`counterpart_faktur_id`) + `refs` dua arah ke transaksinya (G-4).
* **Angka diambil dari transaksi, bukan diketik ulang.** DPP = subtotal −
  subtotal yang sudah diretur; PPN = tax_amount − PPN yang sudah diretur
  (lihat `interco_return_service`). Jadi faktur pajak tidak pernah lebih besar
  dari nilai yang benar-benar terjadi.
* **Retur mengubah angka pajak** ⇒ faktur yang sudah terbit ditandai
  `needs_replacement` dan layar menawarkan **Faktur Pengganti** (praktik
  e-Faktur), bukan diam-diam mengedit dokumen yang sudah terbit.

Invarian: **INV-IC-07** (di `scripts/verify_data_integrity.py`).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core_utils import new_id, next_doc_number, now_iso, rupiah, safe_doc, timeline_entry
from db import db
from services import interco_service as ics
from services.input_tax_service import next_input_number, normalize_nsfp, period_of

EPS = 0.01
COLL_OUT = "tax_invoices"       # Faktur Pajak Keluaran (penjual)
COLL_IN = "tax_invoices_in"     # Faktur Pajak Masukan (pembeli)

# Faktur pajak mengikuti FAKTUR INTERNAL — jadi hanya sah setelah dokumen
# dagangnya terbit (status `invoiced`) atau sudah lunas.
ISSUABLE_STATUSES = ("invoiced", "settled")
ACTIVE_OUT = ("normal", "pengganti")
ACTIVE_IN = ("recorded",)


class IntercoTaxError(Exception):
    """Pelanggaran aturan faktur pajak internal (→ HTTP 400 di router)."""


# ═══════════════════════════════════════════════════════════════════════════
# Utilitas
# ═══════════════════════════════════════════════════════════════════════════
async def _entity_full(entity_id: str) -> Dict[str, Any]:
    ent = await db.business_entities.find_one({"id": entity_id}, {"_id": 0}) or {}
    name = ent.get("legal_name") or ent.get("name") or ent.get("short_name") or ""
    addr = ", ".join([p for p in [ent.get("address", ""), ent.get("city", "")] if p])
    return {"id": entity_id, "name": name, "npwp": ent.get("npwp", ""), "address": addr}


def _net_amounts(seller: Dict[str, Any]) -> Dict[str, float]:
    """Nilai pajak BERSIH: nilai dokumen dikurangi bagian yang sudah diretur."""
    dpp = round(float(seller.get("subtotal") or 0)
                - float(seller.get("returned_subtotal") or 0), 2)
    ppn = round(float(seller.get("tax_amount") or 0)
                - float(seller.get("returned_tax") or 0), 2)
    return {"dpp": max(dpp, 0.0), "ppn": max(ppn, 0.0),
            "total": round(max(dpp, 0.0) + max(ppn, 0.0), 2)}


def _items_for_faktur(seller: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in seller.get("items", []):
        qty = float(it.get("quantity") or 0)
        price = float(it.get("unit_price") or 0)
        out.append({
            "product_name": it.get("product_name", ""),
            "sku": it.get("sku", ""),
            "quantity": qty,
            "unit": it.get("unit", ""),
            "price": price,
            "subtotal": round(qty * price, 2),
            "discount_amount": 0.0,
            "line_total": round(qty * price, 2),
        })
    return out


async def _active_out(pair_id: str) -> Optional[Dict[str, Any]]:
    return await db[COLL_OUT].find_one(
        {"interco_pair_id": pair_id, "status": {"$in": list(ACTIVE_OUT)},
         "replaced_by_id": None},
        {"_id": 0})


async def _active_in(pair_id: str) -> Optional[Dict[str, Any]]:
    return await db[COLL_IN].find_one(
        {"interco_pair_id": pair_id, "status": {"$in": list(ACTIVE_IN)}},
        {"_id": 0})


# ═══════════════════════════════════════════════════════════════════════════
# STATE untuk layar (kenapa tombol aktif / kenapa tidak)
# ═══════════════════════════════════════════════════════════════════════════
async def state(pair_id: str) -> Dict[str, Any]:
    """Keadaan faktur pajak internal satu pair + ALASAN bila belum bisa terbit.

    Layar WAJIB bisa menjelaskan kenapa tombolnya mati — bukan sekadar mati.
    """
    seller, buyer = await ics._pair_docs(pair_id)
    out = await _active_out(pair_id)
    inn = await _active_in(pair_id)
    net = _net_amounts(seller)

    reason = ""
    if not seller.get("tax_apply") or float(seller.get("tax_amount") or 0) <= EPS:
        reason = ("Transaksi ini TANPA PPN (mode "
                  f"'{seller.get('ppn_mode', 'ikut_pkp')}' / penjual non-PKP) — "
                  "tidak ada faktur pajak yang perlu diterbitkan.")
    elif seller.get("status") not in ISSUABLE_STATUSES:
        reason = ("Terbitkan **Faktur Internal** dulu (tombol di baris transaksi). "
                  "Faktur pajak mengikuti faktur dagangnya, bukan sebaliknya.")
    elif net["ppn"] <= EPS:
        reason = ("Seluruh nilai transaksi sudah diretur — tidak ada DPP yang tersisa "
                  "untuk difakturkan.")

    needs_replacement = bool(
        out and (abs(float(out.get("dpp") or 0) - net["dpp"]) > EPS
                 or abs(float(out.get("ppn_amount") or 0) - net["ppn"]) > EPS))

    return {
        "pair_id": pair_id,
        "tax_apply": bool(seller.get("tax_apply")),
        "tax_rate": float(seller.get("tax_rate") or 0),
        "ppn_mode": seller.get("ppn_mode", ""),
        "net_dpp": net["dpp"],
        "net_ppn": net["ppn"],
        "net_total": net["total"],
        "out": safe_doc(out) if out else None,
        "in": safe_doc(inn) if inn else None,
        "can_issue": bool(not out and not reason),
        "blocked_reason": reason,
        "needs_replacement": needs_replacement,
        "seller_entity_name": seller.get("seller_entity_name", ""),
        "buyer_entity_name": seller.get("buyer_entity_name", ""),
    }


# ═══════════════════════════════════════════════════════════════════════════
# TERBITKAN (kembar: keluaran penjual + masukan pembeli)
# ═══════════════════════════════════════════════════════════════════════════
async def issue(pair_id: str, actor: str = "", nsfp: str = "",
                kode_transaksi: str = "01", faktur_date: str = "",
                replaces: Optional[Dict[str, Any]] = None,
                replace_reason: str = "") -> Dict[str, Any]:
    """Terbitkan PASANGAN faktur pajak internal untuk satu transaksi antar-PT."""
    seller, buyer = await ics._pair_docs(pair_id)
    st = await state(pair_id)
    if st["blocked_reason"]:
        raise IntercoTaxError(st["blocked_reason"])
    if replaces is None and st["out"]:
        raise IntercoTaxError(
            f"Faktur pajak internal {st['out'].get('number')} sudah terbit untuk "
            f"transaksi ini. Gunakan **Faktur Pengganti** bila angkanya berubah.")

    net = _net_amounts(seller)
    ent_s = await _entity_full(seller["seller_entity_id"])
    ent_b = await _entity_full(seller["buyer_entity_id"])
    fdate = faktur_date or seller.get("invoiced_at") or now_iso()
    items = _items_for_faktur(seller)
    rate = float(seller.get("tax_rate") or 0)
    is_pengganti = replaces is not None

    out_id = new_id("fkt")
    in_id = new_id("fpm")
    out_number = await next_doc_number(COLL_OUT, "number", "FKT-",
                                      entity_id=seller["seller_entity_id"])
    in_number = await next_input_number()
    nsfp_raw = (nsfp or "").strip()

    shared_tax = {
        "interco_pair_id": pair_id,
        "interco_seller_id": seller["id"],
        "interco_buyer_id": buyer["id"],
        "interco_seller_number": seller.get("number", ""),
        "interco_buyer_number": buyer.get("number", ""),
        "source_type": "interco",
        "is_internal": True,
        "dpp": net["dpp"],
        "ppn_rate": rate,
        "ppn_mode": "excluded",
        "ppn_amount": net["ppn"],
        "grand_total": net["total"],
    }

    # ── Buku PENJUAL: Faktur Pajak KELUARAN ──────────────────────────────
    out_doc: Dict[str, Any] = {
        "id": out_id,
        "number": out_number,
        "nsfp": nsfp_raw,
        "kode_transaksi": (kode_transaksi or "01").strip(),
        "status": "pengganti" if is_pengganti else "normal",
        "replaces_id": (replaces or {}).get("id"),
        "replaced_by_id": None,
        "cancel_reason": "",
        "replace_reason": (replace_reason or "").strip(),
        "faktur_date": fdate,
        # Dokumen internal tidak lahir dari pesanan penjualan — `order_id` kosong,
        # `order_number` memakai nomor transaksi antar-PT supaya layar tetap jujur.
        "order_id": "",
        "order_number": seller.get("number", ""),
        "entity_id": seller["seller_entity_id"],
        "seller_name": ent_s["name"],
        "seller_npwp": ent_s["npwp"],
        "seller_address": ent_s["address"],
        "customer_id": ent_b["id"],
        "customer_name": ent_b["name"],
        "customer_npwp": ent_b["npwp"],
        "customer_address": ent_b["address"],
        "has_customer_npwp": bool(ent_b["npwp"]),
        "items": items,
        "total_amount": float(seller.get("subtotal") or 0),
        "discount_total": round(float(seller.get("returned_subtotal") or 0), 2),
        "net_subtotal": net["dpp"],
        "dpp_nilai_lain": False,
        "effective_rate": rate,
        "is_pkp": True,
        "counterpart_faktur_id": in_id,
        "counterpart_faktur_number": in_number,
        "created_by": actor or "system",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        **shared_tax,
    }

    # ── Buku PEMBELI: Faktur Pajak MASUKAN ───────────────────────────────
    in_doc: Dict[str, Any] = {
        "id": in_id,
        "number": in_number,
        "nsfp": nsfp_raw or out_number,   # tanpa NSFP DJP → pakai nomor faktur internal
        "nsfp_digits": normalize_nsfp(nsfp_raw),
        "kode_transaksi": (kode_transaksi or "01").strip(),
        "status": "recorded",
        "faktur_date": fdate,
        "period": period_of(fdate),
        "entity_id": seller["buyer_entity_id"],
        # Lawan transaksi = PT penjual (diperlakukan seperti supplier di buku pembeli).
        "supplier_id": seller["seller_entity_id"],
        "supplier_name": ent_s["name"],
        "supplier_npwp": ent_s["npwp"],
        "vendor_bill_id": "",
        "bill_number": buyer.get("number", ""),
        "supplier_invoice_no": seller.get("number", ""),
        "po_id": "",
        "po_number": buyer.get("number", ""),
        "counterpart_faktur_id": out_id,
        "counterpart_faktur_number": out_number,
        "notes": ("Faktur Pajak Masukan internal (antar-PT) — pasangan dari "
                  f"{out_number} di buku {ent_s['name']}."),
        "timeline": [timeline_entry(
            "recorded", "Faktur Pajak Masukan internal dicatat", actor or "system",
            f"{seller.get('number', '')} · DPP {rupiah(net['dpp'])} · "
            f"PPN {rupiah(net['ppn'])}")],
        "created_by": actor or "system",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        **shared_tax,
    }

    await db[COLL_OUT].insert_one(dict(out_doc))
    await db[COLL_IN].insert_one(dict(in_doc))

    if is_pengganti:
        await db[COLL_OUT].update_one(
            {"id": replaces["id"]},
            {"$set": {"replaced_by_id": out_id, "updated_at": now_iso()}})

    await _stamp_pair(pair_id, out_doc, in_doc)
    await _link(pair_id, seller, buyer, out_doc, in_doc)
    return {"out": safe_doc(out_doc), "in": safe_doc(in_doc)}


async def _stamp_pair(pair_id: str, out_doc: Optional[Dict[str, Any]],
                      in_doc: Optional[Dict[str, Any]], status: str = "issued") -> None:
    """Cap nomor faktur pajak di KEDUA dokumen kembar (biar terlihat di daftar)."""
    upd: Dict[str, Any] = {
        "tax_faktur_status": status,
        "tax_faktur_out_id": (out_doc or {}).get("id", ""),
        "tax_faktur_out_number": (out_doc or {}).get("number", ""),
        "tax_faktur_in_id": (in_doc or {}).get("id", ""),
        "tax_faktur_in_number": (in_doc or {}).get("number", ""),
        "updated_at": now_iso(),
    }
    await db[ics.COLL_ICT].update_many({"pair_id": pair_id}, {"$set": upd})


async def _link(pair_id: str, seller: Dict[str, Any], buyer: Dict[str, Any],
                out_doc: Dict[str, Any], in_doc: Dict[str, Any]) -> None:
    try:
        from services import doc_refs_service as _refs
        await _refs.safe_link(("tax_invoice", out_doc["id"]),
                              ("interco_transaction", seller["id"]), "parent",
                              note="Faktur pajak keluaran atas transaksi antar-PT")
        await _refs.safe_link(("input_tax_invoice", in_doc["id"]),
                              ("interco_transaction", buyer["id"]), "parent",
                              note="Faktur pajak masukan atas transaksi antar-PT")
        await _refs.safe_link(("tax_invoice", out_doc["id"]),
                              ("input_tax_invoice", in_doc["id"]), "child",
                              note="Pasangan faktur pajak internal (keluaran ↔ masukan)")
    except Exception as exc:  # noqa: BLE001 — jejak, bukan syarat sah dokumen
        print(f"[interco_tax] tautan dokumen gagal {pair_id}: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
# PENGGANTI & BATAL (append-only: dokumen lama tidak pernah diedit)
# ═══════════════════════════════════════════════════════════════════════════
async def replace(pair_id: str, reason: str, actor: str = "") -> Dict[str, Any]:
    """Terbitkan Faktur Pajak PENGGANTI memakai angka bersih terbaru (sesudah retur)."""
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise IntercoTaxError(
            "Alasan penggantian faktur pajak wajib diisi (minimal 5 huruf) — "
            "dokumen pajak tidak boleh berubah tanpa sebab yang tercatat.")
    out = await _active_out(pair_id)
    if not out:
        raise IntercoTaxError("Belum ada faktur pajak internal yang bisa diganti.")
    inn = await _active_in(pair_id)
    if inn:
        await db[COLL_IN].update_one(
            {"id": inn["id"]},
            {"$set": {"status": "cancelled", "cancel_reason": f"Diganti: {reason}",
                      "cancelled_by": actor or "system", "cancelled_at": now_iso(),
                      "updated_at": now_iso()},
             "$push": {"timeline": timeline_entry(
                 "replaced", "Diganti faktur masukan baru", actor or "system", reason)}})
    return await issue(pair_id, actor=actor, nsfp=out.get("nsfp", ""),
                       kode_transaksi=out.get("kode_transaksi", "01"),
                       replaces=out, replace_reason=reason)


async def cancel(pair_id: str, reason: str, actor: str = "") -> Dict[str, Any]:
    """Batalkan pasangan faktur pajak internal (wajib alasan)."""
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise IntercoTaxError("Alasan pembatalan faktur pajak wajib diisi (minimal 5 huruf).")
    out = await _active_out(pair_id)
    inn = await _active_in(pair_id)
    if not out and not inn:
        raise IntercoTaxError("Tidak ada faktur pajak internal aktif untuk transaksi ini.")
    if out:
        await db[COLL_OUT].update_one(
            {"id": out["id"]},
            {"$set": {"status": "batal", "cancel_reason": reason, "updated_at": now_iso()}})
    if inn:
        await db[COLL_IN].update_one(
            {"id": inn["id"]},
            {"$set": {"status": "cancelled", "cancel_reason": reason,
                      "cancelled_by": actor or "system", "cancelled_at": now_iso(),
                      "updated_at": now_iso()},
             "$push": {"timeline": timeline_entry(
                 "cancelled", "Faktur masukan internal dibatalkan", actor or "system", reason)}})
    await _stamp_pair(pair_id, None, None, status="cancelled")
    return await state(pair_id)


# ═══════════════════════════════════════════════════════════════════════════
# RETUR → tandai faktur perlu pengganti (tidak diedit diam-diam)
# ═══════════════════════════════════════════════════════════════════════════
async def flag_needs_replacement(pair_id: str, note: str = "") -> None:
    out = await _active_out(pair_id)
    if not out:
        return
    await db[COLL_OUT].update_one(
        {"id": out["id"]},
        {"$set": {"needs_replacement": True,
                  "needs_replacement_note": note or "Ada retur antar-PT sesudah faktur terbit.",
                  "updated_at": now_iso()}})
    await db[ics.COLL_ICT].update_many(
        {"pair_id": pair_id},
        {"$set": {"tax_faktur_status": "needs_replacement", "updated_at": now_iso()}})
