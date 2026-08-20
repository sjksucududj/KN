"""FASE E-7 (E7f) — **PINJAMAN UANG ANTAR-PT** (`<ENT>/ICL-#####`).

Keputusan pemilik (E7.7): dua jalur antar-PT yang MEMANG terjadi dibangun — salah
satunya pinjaman uang. Sebelum ini praktiknya "transfer saja dari rekening PT A ke
PT B", lalu uang itu tercatat sebagai entah apa (atau tidak tercatat), sehingga
utang-piutang antar-PT tidak pernah cocok dan konsolidasi menggelembung.

**Dokumen kembar** (pola G-6): satu baris di PT pemberi (`role="lender"`, piutang) dan
satu di PT penerima (`role="borrower"`, utang), saling menunjuk lewat `pair_id`.
Siklus: `draft` → `disbursed` → (`partially_repaid`) → `repaid` · `cancelled`.

Setiap peristiwa uang = mutasi kas KEMBAR + jurnal di DUA buku:

    Pencairan   pemberi : Dr 1-1250 IC-AR / Cr Kas
                penerima: Dr Kas          / Cr 2-1250 IC-AP
    Angsuran    penerima: Dr 2-1250 IC-AP / Cr Kas
                pemberi : Dr Kas          / Cr 1-1250 IC-AR

Bunga **tidak diakru** sistem (pemilik tidak memintanya). `interest_note` ada supaya
kesepakatannya bisa DITULIS & terbaca — lebih jujur kosong daripada angka karangan.
Saldonya masuk papan pasangan PT sebagai saldo NON-DAGANG dan ikut dieliminasi
otomatis di konsolidasi grup.
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, next_doc_number, now_iso, rupiah, safe_doc, timeline_entry
from services import gl_service
from services import interco_money_service as money

COLL = "interco_loans"
EPS = 0.01

STATUS_DRAFT = "draft"
STATUS_DISBURSED = "disbursed"
STATUS_PARTIAL = "partially_repaid"
STATUS_REPAID = "repaid"
STATUS_CANCELLED = "cancelled"
STATUS_LABEL = {
    STATUS_DRAFT: "Draf (belum dicairkan)",
    STATUS_DISBURSED: "Sudah dicairkan",
    STATUS_PARTIAL: "Diangsur sebagian",
    STATUS_REPAID: "Lunas",
    STATUS_CANCELLED: "Dibatalkan",
}
OPEN_STATUSES = (STATUS_DISBURSED, STATUS_PARTIAL)


class LoanError(ValueError):
    """Kesalahan ber-kalimat siap tampil."""


async def _load_pair(pair_id: str) -> Dict[str, Dict[str, Any]]:
    docs = await db[COLL].find({"pair_id": pair_id}, {"_id": 0}).to_list(2)
    if len(docs) != 2:
        raise LoanError("Pasangan dokumen pinjaman tidak lengkap.")
    return {"lender": next(d for d in docs if d.get("role") == "lender"),
            "borrower": next(d for d in docs if d.get("role") == "borrower")}


async def get_pair(pair_id: str) -> Dict[str, Any]:
    p = await _load_pair(pair_id)
    return {"pair_id": pair_id, "lender": safe_doc(p["lender"]),
            "borrower": safe_doc(p["borrower"])}


async def get_one(loan_id: str) -> Optional[Dict[str, Any]]:
    doc = await db[COLL].find_one({"id": loan_id}, {"_id": 0})
    return await get_pair(doc["pair_id"]) if doc else None


async def list_loans(query: Dict[str, Any], limit: int = 300) -> List[Dict[str, Any]]:
    rows = await db[COLL].find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return [safe_doc(r) for r in rows]


async def summary(query: Dict[str, Any]) -> Dict[str, Any]:
    rows = await db[COLL].find(query, {"_id": 0}).to_list(2000)
    by_status: Dict[str, int] = {}
    lent = borrowed = 0.0
    for r in rows:
        by_status[r.get("status", "?")] = by_status.get(r.get("status", "?"), 0) + 1
        if r.get("status") in OPEN_STATUSES:
            if r.get("role") == "lender":
                lent += float(r.get("outstanding") or 0)
            else:
                borrowed += float(r.get("outstanding") or 0)
    return {"total": len(rows), "by_status": by_status,
            "outstanding_lent": round(lent, 2), "outstanding_borrowed": round(borrowed, 2)}


async def create(payload: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    lender = (payload.get("lender_entity_id") or "").strip()
    borrower = (payload.get("borrower_entity_id") or "").strip()
    snaps = await money.assert_pair(lender, borrower, what="Pinjaman antar-PT")
    principal = round(float(payload.get("principal") or 0), 2)
    if principal <= EPS:
        raise LoanError("Jumlah pinjaman harus lebih dari 0.")
    purpose = (payload.get("purpose") or "").strip()
    if len(purpose) < 5:
        raise LoanError(
            "Tujuan pinjaman wajib diisi (minimal 5 huruf) — uang berpindah antar badan "
            "hukum, jadi sebabnya harus bisa dibaca auditor & pemeriksa pajak.")

    pair_id = new_id("iclp")
    lender_id, borrower_id = new_id("icl"), new_id("icl")
    num_l = await next_doc_number(COLL, "number", "ICL-", entity_id=lender)
    num_b = await next_doc_number(COLL, "number", "ICL-", entity_id=borrower)
    ts = now_iso()
    common = {
        "pair_id": pair_id,
        "lender_entity_id": lender, "lender_entity_name": snaps["a"]["name"],
        "borrower_entity_id": borrower, "borrower_entity_name": snaps["b"]["name"],
        "principal": principal, "outstanding": principal, "repaid_amount": 0.0,
        "purpose": purpose,
        "interest_note": (payload.get("interest_note") or "").strip(),
        "agreed_return_date": (payload.get("agreed_return_date") or "").strip(),
        "doc_date": (payload.get("doc_date") or now_iso()[:10]),
        "notes": (payload.get("notes") or "").strip(),
        "status": STATUS_DRAFT, "repayments": [],
        "disbursed_at": "", "disbursed_by": "",
        "timeline": [timeline_entry(STATUS_DRAFT, "Pinjaman antar-PT dibuat",
                                   actor.get("name", ""),
                                   f"{rupiah(principal)} · {purpose}")],
        "created_at": ts, "created_by": actor.get("name", ""),
        "updated_at": ts, "updated_by": actor.get("name", ""),
    }
    await db[COLL].insert_many([
        {**common, "id": lender_id, "number": num_l, "role": "lender",
         "entity_id": lender, "counterpart_id": borrower_id, "counterpart_number": num_b},
        {**common, "id": borrower_id, "number": num_b, "role": "borrower",
         "entity_id": borrower, "counterpart_id": lender_id, "counterpart_number": num_l},
    ])
    return await get_pair(pair_id)


async def _set_pair(pair_id: str, upd: Dict[str, Any],
                    event: Optional[Dict[str, Any]] = None) -> None:
    ops: Dict[str, Any] = {"$set": {**upd, "updated_at": now_iso()}}
    if event:
        ops["$push"] = {"timeline": event}
    await db[COLL].update_many({"pair_id": pair_id}, ops)


async def _approval_gate(entity_id: str, amount: float, actor: Dict[str, Any]) -> None:
    """Ambang persetujuan yang SUDAH ADA dipakai ulang (jangan buat kunci kedua)."""
    from services import config_resolver
    threshold = float(await config_resolver.value_of(
        "antar_entitas.approval_threshold_rupiah", {"entity_id": entity_id}) or 0)
    high_role = str(await config_resolver.value_of(
        "antar_entitas.high_value_approval_role", {"entity_id": entity_id}) or "admin")
    low_role = str(await config_resolver.value_of(
        "antar_entitas.approval_role", {"entity_id": entity_id}) or "manager")
    rank = {"warehouse": 0, "sales": 0, "manager": 1, "admin": 2}
    need = high_role if (threshold and amount >= threshold) else low_role
    if rank.get((actor or {}).get("role", ""), 0) < rank.get(need, 1):
        raise LoanError(
            f"Pencairan {rupiah(amount)} butuh peran minimal “{need}” (ambang "
            f"{rupiah(threshold)} dari Pengaturan → Antar Entitas). Minta orang dengan "
            f"wewenang itu yang mencairkan.")


async def disburse(loan_id: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    doc = await db[COLL].find_one({"id": loan_id}, {"_id": 0})
    if not doc:
        raise LoanError("Pinjaman tidak ditemukan.")
    if doc["status"] != STATUS_DRAFT:
        raise LoanError(f"Hanya draf yang bisa dicairkan (status sekarang: "
                        f"{STATUS_LABEL.get(doc['status'], doc['status'])}).")
    lender, borrower = doc["lender_entity_id"], doc["borrower_entity_id"]
    await money.assert_pair(lender, borrower, what="Pencairan pinjaman antar-PT")
    amount = round(float(doc["principal"]), 2)
    await _approval_gate(lender, amount, actor)

    await money.twin_cash(
        out_entity=lender, in_entity=borrower, amount=amount,
        category="pinjaman antar-PT",
        description=f"Pencairan pinjaman ke {doc['borrower_entity_name']} — {doc['purpose']}",
        ref_type="interco_loan", ref_id=doc["pair_id"], actor=actor.get("name", "system"))
    await money.twin_je(
        source_type="interco_loan", pair_id=doc["pair_id"], suffix="disburse",
        entity_a=lender,
        lines_a=money.pair_line(gl_service.ACC_IC_AR, gl_service.ACC_KAS_BESAR, amount,
                                f"Pinjaman kepada {doc['borrower_entity_name']}"),
        entity_b=borrower,
        lines_b=money.pair_line(gl_service.ACC_KAS_BESAR, gl_service.ACC_IC_AP, amount,
                                f"Pinjaman dari {doc['lender_entity_name']}"),
        label=f"Pinjaman antar-PT {doc.get('number', '')}")

    await _set_pair(doc["pair_id"], {
        "status": STATUS_DISBURSED, "outstanding": amount,
        "disbursed_at": now_iso(), "disbursed_by": actor.get("name", "")},
        timeline_entry(STATUS_DISBURSED, "Pinjaman dicairkan", actor.get("name", ""),
                       f"{rupiah(amount)} berpindah dari {doc['lender_entity_name']} ke "
                       f"{doc['borrower_entity_name']}"))
    await _after_change(doc["pair_id"])
    return await get_pair(doc["pair_id"])


async def repay(loan_id: str, actor: Dict[str, Any], amount: float,
                note: str = "") -> Dict[str, Any]:
    doc = await db[COLL].find_one({"id": loan_id}, {"_id": 0})
    if not doc:
        raise LoanError("Pinjaman tidak ditemukan.")
    if doc["status"] not in OPEN_STATUSES:
        raise LoanError(f"Hanya pinjaman yang sudah dicairkan bisa diangsur (status "
                        f"sekarang: {STATUS_LABEL.get(doc['status'], doc['status'])}).")
    amount = round(float(amount or 0), 2)
    out = round(float(doc.get("outstanding") or 0), 2)
    if amount <= EPS:
        raise LoanError("Nominal angsuran harus lebih dari 0.")
    if amount > out + EPS:
        raise LoanError(f"Angsuran {rupiah(amount)} melebihi sisa pinjaman ({rupiah(out)}).")
    lender, borrower = doc["lender_entity_id"], doc["borrower_entity_id"]
    seq = len(doc.get("repayments") or []) + 1
    ref_id = f"{doc['pair_id']}:rp{seq}"

    await money.twin_cash(
        out_entity=borrower, in_entity=lender, amount=amount,
        category="angsuran pinjaman antar-PT",
        description=(f"Angsuran #{seq} pinjaman ke {doc['lender_entity_name']}"
                     + (f" — {note}" if note else "")),
        ref_type="interco_loan_repayment", ref_id=ref_id, actor=actor.get("name", "system"))
    await money.twin_je(
        source_type="interco_loan_repayment", pair_id=doc["pair_id"], suffix=f"rp{seq}",
        entity_a=borrower,
        lines_a=money.pair_line(gl_service.ACC_IC_AP, gl_service.ACC_KAS_BESAR, amount,
                                f"Angsuran pinjaman ke {doc['lender_entity_name']}"),
        entity_b=lender,
        lines_b=money.pair_line(gl_service.ACC_KAS_BESAR, gl_service.ACC_IC_AR, amount,
                                f"Terima angsuran dari {doc['borrower_entity_name']}"),
        label=f"Angsuran pinjaman antar-PT #{seq}")

    new_out = round(max(out - amount, 0.0), 2)
    status = STATUS_REPAID if new_out <= EPS else STATUS_PARTIAL
    await db[COLL].update_many({"pair_id": doc["pair_id"]}, {
        "$set": {"outstanding": new_out,
                 "repaid_amount": round(float(doc.get("repaid_amount") or 0) + amount, 2),
                 "status": status, "updated_at": now_iso(),
                 "updated_by": actor.get("name", "")},
        "$push": {"repayments": {"seq": seq, "amount": amount, "at": now_iso(),
                                 "by": actor.get("name", ""), "note": (note or "").strip()},
                  "timeline": timeline_entry(
                      status, f"Angsuran #{seq} diterima", actor.get("name", ""),
                      f"{rupiah(amount)} · sisa {rupiah(new_out)}")}})
    await _after_change(doc["pair_id"])
    return await get_pair(doc["pair_id"])


async def cancel(loan_id: str, actor: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    doc = await db[COLL].find_one({"id": loan_id}, {"_id": 0})
    if not doc:
        raise LoanError("Pinjaman tidak ditemukan.")
    if doc["status"] != STATUS_DRAFT:
        raise LoanError(
            "Hanya draf yang bisa dibatalkan. Pinjaman yang uangnya SUDAH berpindah tidak "
            "dihapus — ia dilunasi lewat angsuran supaya jejak uangnya utuh.")
    await _set_pair(doc["pair_id"], {"status": STATUS_CANCELLED, "outstanding": 0.0},
                    timeline_entry(STATUS_CANCELLED, "Pinjaman dibatalkan",
                                   actor.get("name", ""), (reason or "").strip()))
    return await get_pair(doc["pair_id"])


async def _after_change(pair_id: str) -> None:
    """Saldo pasangan PT + eliminasi konsolidasi disegarkan otomatis (bukan tugas manual)."""
    p = await _load_pair(pair_id)
    lender = p["lender"]
    await money.refresh_pair_exposure(lender["lender_entity_id"], lender["borrower_entity_id"])
    await money.sync_non_trade_elimination(
        source_key=f"loan:{pair_id}", pair_id=pair_id,
        from_entity=lender["lender_entity_id"], to_entity=lender["borrower_entity_id"],
        outstanding=float(lender.get("outstanding") or 0),
        label=f"pinjaman {lender.get('number', '')}",
        extra_note=f"Tujuan: {lender.get('purpose', '')}")
