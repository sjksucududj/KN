"""FASE G-7 — Pemeriksa invarian **KONTRABON** (INV-CB-01..04).

Dipisahkan dari `contra_bon_service.py` supaya satu sumber kebenaran dipakai DUA
pemakai: `scripts/verify_data_integrity.py` (gate) dan uji POC (bukti-merah).
Semua fungsi READ-ONLY: mengembalikan daftar pelanggaran beserta ALASAN yang bisa
dibaca manusia — bukan hanya True/False, supaya gate yang memerah langsung
memberi tahu dokumen mana yang salah.
"""
from typing import Any, Dict, List

from db import db
from services import contra_bon_service as svc

EPS = 0.01
COLL = svc.COLL


def _round(n: Any) -> float:
    return round(float(n or 0), 2)


async def _live_contra_bons() -> List[Dict[str, Any]]:
    """Kontrabon yang masih 'memegang' dokumen (semua kecuali `cancelled`)."""
    return await db[COLL].find(
        {"status": {"$in": list(svc.HOLDING_STATUSES)}}, {"_id": 0}).to_list(2000)


# ── INV-CB-01 ────────────────────────────────────────────────────────────────
async def bills_in_multiple_contra_bons() -> List[Dict[str, Any]]:
    """Satu faktur supplier tidak boleh berada di dua kontrabon yang belum dibatalkan.

    Kalau ini bocor, satu tagihan bisa dibayar dua kali lewat dua siklus berbeda —
    kerugian uang nyata yang tidak akan terlihat di layar mana pun.
    """
    seen: Dict[str, List[str]] = {}
    for cb in await _live_contra_bons():
        for b in (cb.get("bills") or []):
            seen.setdefault(b.get("bill_id", ""), []).append(cb.get("number", cb["id"]))
    return [{"bill_id": bid, "contra_bons": nums, "reason": "faktur ada di >1 kontrabon aktif"}
            for bid, nums in seen.items() if bid and len(nums) > 1]


async def bill_over_applied() -> List[Dict[str, Any]]:
    """Σ nilai yang dikontrabonkan atas satu faktur ≤ nilai faktur itu."""
    per_bill: Dict[str, float] = {}
    for cb in await _live_contra_bons():
        for b in (cb.get("bills") or []):
            bid = b.get("bill_id", "")
            per_bill[bid] = _round(per_bill.get(bid, 0.0) + _round(b.get("applied_amount")))
    bad: List[Dict[str, Any]] = []
    for bid, applied in per_bill.items():
        bill = await db.vendor_bills.find_one({"id": bid}, {"_id": 0, "bill_number": 1,
                                                            "grand_total": 1})
        if not bill:
            bad.append({"bill_id": bid, "applied": applied,
                        "reason": "faktur yang dikontrabonkan sudah tidak ada"})
            continue
        grand = _round(bill.get("grand_total"))
        if applied > grand + EPS:
            bad.append({"bill_id": bid, "bill_number": bill.get("bill_number", ""),
                        "applied": applied, "grand_total": grand,
                        "reason": "nilai dikontrabonkan melebihi nilai faktur"})
    return bad


# ── INV-CB-02 ────────────────────────────────────────────────────────────────
async def totals_mismatch() -> List[Dict[str, Any]]:
    """`net_payable == Σ faktur − Σ potongan` (≥ 0) dan kontrabon lunas == Σ pembayaran."""
    bad: List[Dict[str, Any]] = []
    async for cb in db[COLL].find({}, {"_id": 0}):
        bills = _round(sum(_round(b.get("applied_amount")) for b in (cb.get("bills") or [])))
        ded = _round(sum(_round(d.get("amount")) for d in (cb.get("deductions") or [])))
        paid = _round(sum(_round(p.get("amount")) for p in (cb.get("payments") or [])))
        tot = cb.get("totals") or {}
        net = _round(tot.get("net_payable"))
        if abs(net - _round(bills - ded)) > EPS:
            bad.append({"number": cb.get("number"), "reason": "net_payable tidak sama dengan "
                        f"Σ faktur ({bills}) − Σ potongan ({ded})", "net_payable": net})
            continue
        if net < -EPS:
            bad.append({"number": cb.get("number"), "reason": "nilai bersih negatif",
                        "net_payable": net})
            continue
        if cb.get("status") == "paid" and abs(paid - net) > EPS:
            bad.append({"number": cb.get("number"),
                        "reason": f"status lunas tetapi Σ pembayaran {paid} ≠ nilai bersih {net}"})
            continue
        if paid > net + EPS:
            bad.append({"number": cb.get("number"),
                        "reason": f"Σ pembayaran {paid} melebihi nilai bersih {net}"})
    return bad


async def settlement_mismatch() -> List[Dict[str, Any]]:
    """Uang yang keluar + potongan HARUS benar-benar menempel di subledger faktur.

    Ini invarian yang menutup celah nyata sebelum FASE G-7: retur beli `ap_credit`
    mengurangi Hutang di buku besar tetapi TIDAK pernah mengurangi `vendor_bills`,
    sehingga daftar hutang dan buku besar berbeda tanpa ada yang menutup selisihnya.
    """
    bad: List[Dict[str, Any]] = []
    async for cb in db[COLL].find({"status": "paid"}, {"_id": 0}):
        for b in (cb.get("bills") or []):
            settled = _round(b.get("settled_amount"))
            applied = _round(b.get("applied_amount"))
            if abs(settled - applied) > EPS:
                bad.append({"number": cb.get("number"), "bill": b.get("bill_number"),
                            "reason": f"kontrabon lunas tetapi faktur baru tersettle {settled} "
                                      f"dari {applied}"})
                continue
            bill = await db.vendor_bills.find_one({"id": b.get("bill_id")},
                                                  {"_id": 0, "payments": 1, "bill_number": 1})
            if not bill:
                continue
            via_cb = _round(sum(_round(p.get("amount")) for p in (bill.get("payments") or [])
                                if p.get("contra_bon_id") == cb["id"]))
            if abs(via_cb - applied) > EPS:
                bad.append({"number": cb.get("number"), "bill": b.get("bill_number"),
                            "reason": f"pelunasan tercatat di faktur {via_cb} ≠ "
                                      f"nilai dikontrabonkan {applied}"})
    return bad


# ── INV-CB-03 ────────────────────────────────────────────────────────────────
async def undecided_exceptions() -> List[Dict[str, Any]]:
    """Kontrabon yang sudah melewati verifikasi tak boleh punya selisih tanpa keputusan."""
    past = ("verified", "approved", "scheduled_payment", "paid")
    bad: List[Dict[str, Any]] = []
    async for cb in db[COLL].find({"status": {"$in": list(past)}}, {"_id": 0}):
        decided = {d.get("exception_key") for d in (cb.get("decisions") or [])
                   if d.get("exception_key")}
        for b in (cb.get("bills") or []):
            for e in ((b.get("match") or {}).get("exceptions") or []):
                if e.get("key") not in decided:
                    bad.append({"number": cb.get("number"), "bill": b.get("bill_number"),
                                "exception": e.get("key"), "detail": e.get("detail", ""),
                                "reason": "selisih 3-way di luar toleransi tanpa keputusan berlabel"})
    return bad


async def decisions_without_reason() -> List[Dict[str, Any]]:
    """Setiap keputusan selisih wajib punya label alasan yang TERDAFTAR untuk kontrabon."""
    valid = {r["code"] for r in await db.amendment_reasons.find(
        {"applies_to": svc.REASON_DOC_TYPE}, {"_id": 0, "code": 1}).to_list(200)}
    bad: List[Dict[str, Any]] = []
    async for cb in db[COLL].find({}, {"_id": 0}):
        for d in (cb.get("decisions") or []):
            code = d.get("reason_code") or ""
            if not code or code not in valid:
                bad.append({"number": cb.get("number"), "exception": d.get("exception_key"),
                            "reason_code": code,
                            "reason": "alasan kosong / tidak terdaftar untuk kontrabon"})
    return bad


# ── INV-CB-04 ────────────────────────────────────────────────────────────────
async def deduction_refs_reused() -> List[Dict[str, Any]]:
    """Satu nota debit / uang muka hanya boleh dipotong di SATU kontrabon."""
    seen: Dict[str, List[str]] = {}
    for cb in await _live_contra_bons():
        for d in (cb.get("deductions") or []):
            if d.get("ref_id"):
                seen.setdefault(d["ref_id"], []).append(cb.get("number", cb["id"]))
    return [{"ref_id": ref, "contra_bons": nums,
             "reason": "dokumen potongan dipakai di >1 kontrabon aktif"}
            for ref, nums in seen.items() if len(nums) > 1]


async def deduction_over_source() -> List[Dict[str, Any]]:
    """Nilai potongan tidak boleh melebihi nilai dokumen sumbernya."""
    bad: List[Dict[str, Any]] = []
    for cb in await _live_contra_bons():
        for d in (cb.get("deductions") or []):
            if not d.get("ref_id"):
                continue
            amount = _round(d.get("amount"))
            if d.get("kind") == "purchase_return":
                src = await db.purchase_returns.find_one(
                    {"id": d["ref_id"]}, {"_id": 0, "total_amount": 1, "number": 1, "status": 1})
                cap = _round((src or {}).get("total_amount"))
            else:
                src = await db.cash_transactions.find_one(
                    {"id": d["ref_id"]}, {"_id": 0, "amount": 1, "number": 1})
                cap = _round((src or {}).get("amount"))
            if not src:
                bad.append({"number": cb.get("number"), "ref_id": d["ref_id"],
                            "reason": "dokumen potongan sudah tidak ada"})
            elif amount > cap + EPS:
                bad.append({"number": cb.get("number"), "ref": src.get("number", ""),
                            "amount": amount, "cap": cap,
                            "reason": "potongan melebihi nilai dokumen sumber"})
    return bad


async def makloon_double_deduction() -> List[Dict[str, Any]]:
    """Potongan klaim makloon yang SUDAH menempel di faktur tak boleh jadi potongan lagi.

    Fase D memotong `vendor_bills.grand_total` langsung saat klaim `potong_bon` disetujui
    (berikut jurnal `Dr 2-1100 / Cr 4-9200`). Memotongnya lagi di kontrabon = mengurangi
    hutang dua kali untuk satu kerugian yang sama.
    """
    bad: List[Dict[str, Any]] = []
    for cb in await _live_contra_bons():
        for d in (cb.get("deductions") or []):
            if d.get("kind") in ("makloon_claim", "makloon_potong_bon"):
                bad.append({"number": cb.get("number"), "deduction": d.get("id"),
                            "reason": "potongan klaim makloon sudah menempel di faktur "
                                      "(dobel potong)"})
    return bad


async def deduction_journal_missing() -> List[Dict[str, Any]]:
    """Potongan yang MEMANG butuh jurnal wajib punya jurnal saat sudah diterapkan.

    Sebaliknya, `purchase_return` TIDAK boleh punya jurnal kontrabon: jurnalnya lahir
    saat retur disetujui, jadi jurnal kedua berarti hutang berkurang dua kali.
    """
    bad: List[Dict[str, Any]] = []
    async for cb in db[COLL].find({}, {"_id": 0}):
        for d in (cb.get("deductions") or []):
            if not d.get("applied_at"):
                continue
            src = f"{cb['id']}:{d.get('id')}"
            je = await db.journal_entries.find_one(
                {"source_type": "contra_bon_deduction", "source_id": src}, {"_id": 0, "lines": 1})
            if d.get("posts_gl") and not je:
                bad.append({"number": cb.get("number"), "kind": d.get("kind"),
                            "reason": "potongan sudah diterapkan tetapi tidak berjurnal"})
            if not d.get("posts_gl") and je:
                bad.append({"number": cb.get("number"), "kind": d.get("kind"),
                            "reason": "potongan retur beli TIDAK boleh berjurnal ulang "
                                      "(hutang berkurang dua kali)"})
    return bad


async def stats() -> Dict[str, Any]:
    """Angka ringkas untuk kalimat PASS (bukan sekadar 'oke')."""
    total = await db[COLL].count_documents({})
    paid = await db[COLL].count_documents({"status": "paid"})
    live = len(await _live_contra_bons())
    ded = 0
    async for cb in db[COLL].find({}, {"_id": 0, "deductions": 1}):
        ded += len(cb.get("deductions") or [])
    return {"total": total, "paid": paid, "live": live, "deductions": ded}
