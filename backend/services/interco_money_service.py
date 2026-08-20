"""FASE E-7 (E7f + E7g) — **UANG & ASET ANTAR-PT** yang bukan jual-beli.

Dua jalur yang pemilik nyatakan MEMANG terjadi (keputusan E7.7): pinjaman uang
antar-PT dan pindah aset tetap antar-PT. Keduanya melahirkan piutang/utang antar-PT
(IC-AR ↔ IC-AP), jadi keduanya butuh tiga hal yang sama — dan itulah isi modul ini
supaya tidak ditulis dua kali:

  * `twin_cash()` — mutasi kas KEMBAR di dua badan usaha (keluar di satu buku, masuk di
    buku lain) memakai koleksi kas yang sama dengan layar Kas & Bank, sehingga saldo
    rekening ikut bergerak. Idempotent per (ref_type, ref_id, arah).
  * `twin_je()` — jurnal di DUA buku (bukan satu buku "grup"): tiap PT punya neraca
    sendiri. Sejak E7.4 kas tingkat grup dihapus, jadi ini bukan pilihan gaya.
  * `assert_pair()` — pagar pasangan badan usaha (harus beda & keduanya aktif).

Ditambah dua hal yang membuat angkanya JUJUR di laporan grup:
  * `non_trade_outstanding()` — saldo NON-DAGANG dipisah dari saldo jual-beli, karena
    cara melunasinya berbeda (pinjaman diangsur, saldo dagang di-netting).
  * `sync_non_trade_elimination()` — IC-AR ↔ IC-AP non-dagang saling dihapus di
    konsolidasi; tanpa ini neraca grup menggelembung dua kali untuk uang yang tidak
    pernah keluar dari grup.
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, next_doc_number, now_iso, rupiah, safe_doc
from services import gl_service

EPS = 0.01


class IntercoMoneyError(ValueError):
    """Kesalahan ber-kalimat siap tampil (Bahasa Indonesia)."""


async def entity_snapshot(entity_id: str) -> Dict[str, Any]:
    e = await db.business_entities.find_one({"id": entity_id}, {"_id": 0}) or {}
    return {"id": entity_id,
            "name": e.get("short_name") or e.get("legal_name") or entity_id,
            "legal_name": e.get("legal_name", ""),
            "status": e.get("status", "active"), "found": bool(e)}


async def assert_pair(a_entity: str, b_entity: str, *, what: str) -> Dict[str, Dict[str, Any]]:
    """Pagar pasangan badan usaha — dengan kalimat yang menjelaskan sebabnya."""
    if not a_entity or not b_entity:
        raise IntercoMoneyError(f"{what}: kedua badan usaha wajib dipilih.")
    if a_entity == b_entity:
        raise IntercoMoneyError(
            f"{what}: badan usaha pengirim dan penerima harus BERBEDA — kalau sama, itu "
            f"bukan transaksi antar-PT (pakai pindah-buku/mutasi biasa).")
    a = await entity_snapshot(a_entity)
    b = await entity_snapshot(b_entity)
    for snap in (a, b):
        if not snap["found"]:
            raise IntercoMoneyError(f"{what}: badan usaha {snap['id']} tidak ditemukan.")
        if snap["status"] != "active":
            raise IntercoMoneyError(
                f"{what}: “{snap['legal_name'] or snap['name']}” sudah tidak aktif — badan "
                f"usaha yang berhenti beroperasi tidak boleh menerbitkan/menerima dokumen baru.")
    return {"a": a, "b": b}


async def default_cash_account(entity_id: str) -> str:
    acc = await db.bank_accounts.find_one(
        {"entity_id": entity_id, "is_active": {"$ne": False}}, {"_id": 0, "id": 1},
        sort=[("account_type", 1)])
    return (acc or {}).get("id", "")


async def twin_cash(*, out_entity: str, in_entity: str, amount: float, category: str,
                    description: str, ref_type: str, ref_id: str,
                    actor: str = "system", txn_date: str = "") -> Dict[str, Any]:
    """Satu peristiwa uang → DUA mutasi kas (keluar di satu PT, masuk di PT lain)."""
    amount = round(float(amount or 0), 2)
    if amount <= EPS:
        raise IntercoMoneyError("Nominal harus lebih dari 0.")
    out: Dict[str, Any] = {}
    inn: Dict[str, Any] = {}
    for direction, ent in (("out", out_entity), ("in", in_entity)):
        doc = await db.cash_transactions.find_one(
            {"ref_type": ref_type, "ref_id": ref_id, "direction": direction,
             "entity_id": ent, "status": {"$ne": "void"}}, {"_id": 0})
        if not doc:
            doc = {
                "id": new_id("cash"),
                "number": await next_doc_number("cash_transactions", "number", "CASH-",
                                                entity_id=ent),
                # `kas_besar` = buku bank/transfer (BUKAN "milik grup" — lihat E7.4).
                "cash_type": "kas_besar", "direction": direction, "amount": amount,
                "category": category, "description": description, "entity_id": ent,
                "counterparty_entity_id": in_entity if direction == "out" else out_entity,
                "ref_type": ref_type, "ref_id": ref_id,
                "account_id": await default_cash_account(ent),
                "txn_date": txn_date or now_iso(), "reconciled": False, "status": "posted",
                # Jurnalnya dibentuk `twin_je()` (Dr/Cr IC-AR/IC-AP) — jangan diposting
                # ulang sebagai mutasi kas biasa (itu akan menjurnal dua kali).
                "gl_posted": True,
                "created_by": actor, "created_at": now_iso(), "updated_at": now_iso(),
            }
            await db.cash_transactions.insert_one(dict(doc))
        if direction == "out":
            out = doc
        else:
            inn = doc
    return {"out": out, "in": inn}


async def twin_je(*, source_type: str, pair_id: str, suffix: str,
                  entity_a: str, lines_a: List[Dict[str, Any]],
                  entity_b: str, lines_b: List[Dict[str, Any]],
                  label: str, date: str = "") -> Dict[str, Any]:
    """Jurnal di DUA buku (satu per badan usaha). Idempotent per sisi."""
    je_a = await gl_service.post_paired_entry(
        source_type=source_type, source_id=f"{pair_id}:{suffix}:a",
        entity_id=entity_a, lines=lines_a, label=label, date=date)
    je_b = await gl_service.post_paired_entry(
        source_type=source_type, source_id=f"{pair_id}:{suffix}:b",
        entity_id=entity_b, lines=lines_b, label=label, date=date)
    return {"a": je_a, "b": je_b}


def pair_line(debit_acc: str, credit_acc: str, amount: float, desc: str) -> List[Dict[str, Any]]:
    amount = round(float(amount), 2)
    return [
        {"account_code": debit_acc, "debit": amount, "credit": 0.0, "description": desc},
        {"account_code": credit_acc, "debit": 0.0, "credit": amount, "description": desc},
    ]


async def refresh_pair_exposure(entity_a: str, entity_b: str) -> None:
    """Segarkan saldo pasangan PT (memakai mesin G-6 — jangan ada dua rumus saldo).

    Dipanggil untuk KEDUA arah dagang. Sebelum KN-G6-ICA-CLOBBER ditutup, dua
    panggilan berurutan ini saling MENIMPA (id baris saldo dulu tidak memuat
    peran), jadi satu pinjaman/pindah aset antar-PT bisa menghapus utang dagang
    yang nyata. Sekarang tiap arah punya barisnya sendiri.
    """
    try:
        from services import interco_service as ics
        await ics._update_account_balance(entity_a, entity_b)   # noqa: SLF001
        await ics._update_account_balance(entity_b, entity_a)   # noqa: SLF001
    except Exception as exc:  # noqa: BLE001 — dokumen tetap sah; saldo bisa disegarkan lagi
        print(f"[interco_money] segarkan saldo pasangan gagal: {exc}")


async def non_trade_outstanding(from_entity: str, to_entity: str) -> Dict[str, Any]:
    """Piutang NON-DAGANG `from_entity` kepada `to_entity` (pinjaman + pindah aset)."""
    loans = await db.interco_loans.find(
        {"role": "lender", "lender_entity_id": from_entity,
         "borrower_entity_id": to_entity,
         "status": {"$in": ["disbursed", "partially_repaid"]}},
        {"_id": 0, "outstanding": 1}).to_list(2000)
    loan_out = round(sum(float(r.get("outstanding") or 0) for r in loans), 2)
    assets = await db.fin_fixed_assets.find(
        {"transfer.from_entity_id": from_entity, "transfer.to_entity_id": to_entity,
         "transfer.settled": False}, {"_id": 0, "transfer": 1}).to_list(2000)
    asset_out = round(sum(float((r.get("transfer") or {}).get("price") or 0) for r in assets), 2)
    return {"loan_outstanding": loan_out, "loan_count": len(loans),
            "asset_transfer_outstanding": asset_out, "asset_transfer_count": len(assets),
            "non_trade_outstanding": round(loan_out + asset_out, 2)}


async def sync_non_trade_elimination(*, source_key: str, pair_id: str, from_entity: str,
                                     to_entity: str, outstanding: float, label: str,
                                     extra_note: str = "",
                                     accounts: Optional[tuple] = None,
                                     kind_note: str = "") -> Optional[Dict[str, Any]]:
    """Eliminasi konsolidasi IC-AR ↔ IC-AP **non-dagang**. Idempotent; hilang saat nol.

    `accounts=(debit, credit)` dipakai untuk eliminasi yang BUKAN piutang/utang — mis.
    **laba pindah aset** (Dr Laba Pelepasan / Cr Aset): laba dari menjual aset ke PT
    sendiri bukan laba grup, dan nilai aset di grup tidak boleh naik hanya karena
    berpindah tangan di dalam grup.
    """
    outstanding = round(float(outstanding or 0), 2)
    prev = await db.intercompany_eliminations.find_one(
        {"source_non_trade_key": source_key}, {"_id": 0})
    if outstanding <= EPS:
        if prev:
            await db.intercompany_eliminations.delete_one({"id": prev["id"]})
        return None
    debit_acc, credit_acc = accounts or (gl_service.ACC_IC_AP, gl_service.ACC_IC_AR)
    names: Dict[str, str] = {}
    async for a in db.gl_accounts.find(
            {"code": {"$in": [debit_acc, credit_acc]}}, {"_id": 0, "code": 1, "name": 1}):
        names[a["code"]] = a.get("name", "")
    lines = [
        {"account_code": debit_acc, "account_name": names.get(debit_acc, debit_acc),
         "debit": outstanding, "credit": 0.0,
         "description": f"Eliminasi {kind_note or 'utang antar-PT'} · {label}"},
        {"account_code": credit_acc, "account_name": names.get(credit_acc, credit_acc),
         "debit": 0.0, "credit": outstanding,
         "description": f"Eliminasi {kind_note or 'piutang antar-PT'} · {label}"},
    ]
    payload = {
        "name": f"Auto E-7: Eliminasi {label}",
        "entity_from": from_entity, "entity_to": to_entity,
        "effective_date": now_iso()[:10],
        "note": ("Auto-generated FASE E-7 (E7f/E7g): piutang & utang antar-PT dari pinjaman "
                 "uang / pindah aset tetap saling menghapus di konsolidasi karena uangnya "
                 f"tidak pernah keluar dari grup. Saldo terkini {rupiah(outstanding)}. "
                 f"{extra_note}").strip(),
        "lines": lines, "total_debit": outstanding, "total_credit": outstanding,
        "balanced": True, "auto_generated": True,
        "source_non_trade_key": source_key, "source_non_trade_pair_id": pair_id,
        "updated_at": now_iso(),
    }
    if prev:
        await db.intercompany_eliminations.update_one({"id": prev["id"]}, {"$set": payload})
        return safe_doc({**prev, **payload})
    doc = {"id": new_id("icelim"), **payload, "created_by": "system", "created_at": now_iso()}
    await db.intercompany_eliminations.insert_one(dict(doc))
    return safe_doc(doc)
