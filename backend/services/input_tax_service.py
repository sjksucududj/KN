"""Faktur Pajak Masukan (tax_invoices_in) service — Fase 5.5 / P0-3.

Mencatat Faktur Pajak Masukan (Input VAT) dari Vendor Bill ber-PPN agar PPN
Masukan dapat dikreditkan terhadap PPN Keluaran (compliance PKP).

Keputusan desain owner:
  - Sumber  : Vendor Bill (DPP/PPN sudah dihitung di bill, mirror PO P0-1).
  - NSFP    : Nomor Seri Faktur Pajak supplier disimpan + DEDUPE (cegah ganda).
              (tanpa flag creditable — semua faktur tercatat dianggap dikreditkan.)
  - Rekap   : PPN Masukan vs Keluaran per periode (YYYY-MM) → posisi kurang/lebih bayar.

Lifecycle: recorded → cancelled. (Tanpa approval: hanya merekam dokumen pajak
eksternal; kewajiban finansial sudah dibuat oleh Vendor Bill.)
"""
from typing import Any, Dict, List, Optional
from db import db
from core_utils import now_iso

# Vendor bill yang AP-relevan (lihat vendor_bill_service.AP_BILL_STATUSES).
ELIGIBLE_BILL_STATUSES = {"posted", "paid"}
ACTIVE_INPUT_STATUSES = {"recorded"}


async def next_input_number() -> str:
    """Number series internal FPM-NNNNN (cegah duplikat via max existing)."""
    last = await db.tax_invoices_in.find_one(
        {}, {"_id": 0, "number": 1}, sort=[("number", -1)])
    n = 0
    if last and isinstance(last.get("number"), str) and last["number"].startswith("FPM-"):
        try:
            n = int(last["number"].split("-")[1])
        except (ValueError, IndexError):
            n = await db.tax_invoices_in.count_documents({})
    else:
        n = await db.tax_invoices_in.count_documents({})
    return f"FPM-{n + 1:05d}"


def normalize_nsfp(nsfp: Optional[str]) -> str:
    """Ambil digit saja dari NSFP supplier untuk dedupe (abaikan format titik/strip)."""
    return "".join(ch for ch in (nsfp or "") if ch.isdigit())


def format_nsfp_display(nsfp: Optional[str]) -> str:
    """Tampilkan NSFP 16-digit sebagai NNN-NN.NN-NNNNNNNN bila cukup digit."""
    d = normalize_nsfp(nsfp)
    if len(d) >= 16:
        d = d[:16]
        return f"{d[:3]}-{d[3:5]}.{d[5:7]}-{d[7:]}"
    return (nsfp or "").strip()


def period_of(iso_date: Optional[str]) -> str:
    """Periode pajak YYYY-MM dari tanggal faktur (default sekarang)."""
    s = (iso_date or "") or now_iso()
    return s[:7]


async def find_active_duplicate_nsfp(nsfp_digits: str, exclude_id: str = "") -> Optional[Dict[str, Any]]:
    """Cari Faktur Masukan AKTIF (recorded) dengan NSFP sama (cegah ganda)."""
    if not nsfp_digits:
        return None
    q: Dict[str, Any] = {"nsfp_digits": nsfp_digits, "status": {"$in": list(ACTIVE_INPUT_STATUSES)}}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    return await db.tax_invoices_in.find_one(q, {"_id": 0, "number": 1, "nsfp": 1})


def snapshot_from_bill(bill: Dict[str, Any]) -> Dict[str, Any]:
    """Salin field pajak & referensi dari Vendor Bill ke Faktur Masukan."""
    return {
        "vendor_bill_id": bill.get("id", ""),
        "bill_number": bill.get("bill_number", ""),
        "supplier_invoice_no": bill.get("supplier_invoice_no", ""),
        "po_id": bill.get("po_id", ""),
        "po_number": bill.get("po_number", ""),
        "supplier_id": bill.get("supplier_id", ""),
        "supplier_name": bill.get("supplier_name", ""),
        "supplier_npwp": bill.get("supplier_npwp", ""),
        "entity_id": bill.get("entity_id", ""),
        "dpp": round(float(bill.get("dpp", 0) or 0), 2),
        "ppn_rate": float(bill.get("ppn_rate", 0) or 0),
        "ppn_mode": bill.get("ppn_mode", "excluded"),
        "ppn_amount": round(float(bill.get("ppn_amount", 0) or 0), 2),
        "grand_total": round(float(bill.get("grand_total", 0) or 0), 2),
    }


async def eligible_vendor_bills(entity_id: str = "") -> List[Dict[str, Any]]:
    """Vendor Bill ber-PPN (posted/paid) yang BELUM punya Faktur Masukan aktif."""
    q: Dict[str, Any] = {
        "status": {"$in": list(ELIGIBLE_BILL_STATUSES)},
        "ppn_amount": {"$gt": 0},
        "$or": [
            {"input_faktur_status": {"$exists": False}},
            {"input_faktur_status": {"$nin": list(ACTIVE_INPUT_STATUSES)}},
        ],
    }
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    bills = await db.vendor_bills.find(q, {"_id": 0}).sort("bill_date", -1).to_list(500)
    rows = []
    for b in bills:
        rows.append({
            "vendor_bill_id": b.get("id"),
            "bill_number": b.get("bill_number"),
            "supplier_invoice_no": b.get("supplier_invoice_no", ""),
            "supplier_id": b.get("supplier_id", ""),
            "supplier_name": b.get("supplier_name", ""),
            "supplier_npwp": b.get("supplier_npwp", ""),
            "po_number": b.get("po_number", ""),
            "entity_id": b.get("entity_id", ""),
            "bill_date": b.get("bill_date", ""),
            "dpp": round(float(b.get("dpp", 0) or 0), 2),
            "ppn_rate": float(b.get("ppn_rate", 0) or 0),
            "ppn_amount": round(float(b.get("ppn_amount", 0) or 0), 2),
            "grand_total": round(float(b.get("grand_total", 0) or 0), 2),
        })
    return rows


async def vat_summary(period: str = "", entity_id: str = "") -> Dict[str, Any]:
    """Rekap PPN Masukan vs Keluaran untuk satu periode (YYYY-MM).

    Keluaran = Σ ppn_amount Faktur Pajak Jual (tax_invoices, status != batal).
    Masukan  = Σ ppn_amount Faktur Pajak Masukan (tax_invoices_in, status recorded).
    Net      = Keluaran − Masukan → >0 KURANG BAYAR (setor), <0 LEBIH BAYAR (kredit).
    """
    period = (period or now_iso()[:7]).strip()

    def _in_period(doc: Dict[str, Any]) -> bool:
        return (doc.get("faktur_date", "") or "")[:7] == period

    out_q: Dict[str, Any] = {"status": {"$ne": "batal"}}
    in_q: Dict[str, Any] = {"status": {"$in": list(ACTIVE_INPUT_STATUSES)}}
    if entity_id and entity_id != "all":
        out_q["entity_id"] = entity_id
        in_q["entity_id"] = entity_id

    out_docs = [d for d in await db.tax_invoices.find(out_q, {"_id": 0}).to_list(5000) if _in_period(d)]
    in_docs = [d for d in await db.tax_invoices_in.find(in_q, {"_id": 0}).to_list(5000) if _in_period(d)]

    keluaran_ppn = round(sum(float(d.get("ppn_amount", 0) or 0) for d in out_docs), 2)
    keluaran_dpp = round(sum(float(d.get("dpp", 0) or 0) for d in out_docs), 2)
    masukan_ppn = round(sum(float(d.get("ppn_amount", 0) or 0) for d in in_docs), 2)
    masukan_dpp = round(sum(float(d.get("dpp", 0) or 0) for d in in_docs), 2)

    net = round(keluaran_ppn - masukan_ppn, 2)
    if net > 0.01:
        position, position_label = "kurang_bayar", "PPN Kurang Bayar (setor ke negara)"
    elif net < -0.01:
        position, position_label = "lebih_bayar", "PPN Lebih Bayar (kredit dibawa ke periode berikutnya)"
    else:
        position, position_label = "nihil", "PPN Nihil"

    # ringkas Masukan per supplier
    by_supplier: Dict[str, Dict[str, Any]] = {}
    for d in in_docs:
        key = d.get("supplier_name") or "—"
        s = by_supplier.setdefault(key, {"supplier_name": key, "ppn": 0.0, "dpp": 0.0, "count": 0})
        s["ppn"] = round(s["ppn"] + float(d.get("ppn_amount", 0) or 0), 2)
        s["dpp"] = round(s["dpp"] + float(d.get("dpp", 0) or 0), 2)
        s["count"] += 1

    return {
        "period": period,
        "keluaran": {"ppn": keluaran_ppn, "dpp": keluaran_dpp, "count": len(out_docs)},
        "masukan": {"ppn": masukan_ppn, "dpp": masukan_dpp, "count": len(in_docs)},
        "net_ppn": net,
        "position": position,
        "position_label": position_label,
        "masukan_by_supplier": sorted(by_supplier.values(), key=lambda s: -s["ppn"]),
    }
