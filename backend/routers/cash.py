"""Cash Management router (Fase 3 — Pengelolaan Kas).

Koleksi kanonik: `cash_transactions` (prefix cash_).
- kas_kecil : kas operasional per ENTITAS (entity_id spesifik)
- kas_besar : kas gabungan grup (entity_id = "all")
direction: in (masuk) | out (keluar). Saldo = Σ(in) − Σ(out).
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc
from entity_scope import entity_ctx, resolve_scope_ids
from schemas import CashTransactionCreate
from services import cash_entity_service

router = APIRouter(prefix="/api")

VALID_TYPES = {"kas_kecil", "kas_besar"}
VALID_DIRECTIONS = {"in", "out"}


async def _next_cash_number(entity_id: str = "") -> str:
    """Nomor kas. FASE E-7 (E7.4): kas selalu milik satu badan usaha, jadi nomornya
    memakai deret per badan usaha (E1.7) — dua PT tidak lagi berebut satu deret."""
    from core_utils import next_doc_number
    return await next_doc_number("cash_transactions", "number", "CASH-",
                                 entity_id=(entity_id or None))


@router.get("/cash-transactions")
async def list_cash_transactions(
    request: Request, entity_id: str = None, cash_type: str = None, direction: str = None
) -> List[Dict[str, Any]]:
    """List transaksi kas (filter entitas/jenis/arah).

    FASE E-7 (E7.4): kas tingkat grup DIHAPUS, jadi tidak ada lagi klausa "kas_besar
    selalu tampil lintas-entitas" — itu justru yang membuat uang satu PT terbaca PT
    lain. Sisa data lama ber-`entity_id="all"` tetap TERLIHAT (jangan hilang diam-diam)
    tetapi hanya untuk peran lintas-entitas, dan layar menegur agar dimigrasikan.
    """
    actor = await require_permission(request, "cash", "view")
    ctx = await entity_ctx(request)
    entities = resolve_scope_ids(ctx, entity_id)
    or_clauses: List[Dict[str, Any]] = [{"entity_id": {"$in": entities}}]
    if (actor or {}).get("role") in ("admin", "manager"):
        or_clauses.append({"entity_id": {"$in": ["all", "", None]}})
    query: Dict[str, Any] = {"status": {"$ne": "void"}, "$or": or_clauses}
    if cash_type:
        query["cash_type"] = cash_type
    if direction:
        query["direction"] = direction
    rows = await db.cash_transactions.find(query, {"_id": 0}).sort("txn_date", -1).to_list(500)
    return rows


@router.get("/cash-transactions/summary")
async def cash_summary(request: Request, entity_id: str = None) -> Dict[str, Any]:
    """Ringkasan saldo kas kecil & kas besar/bank — KEDUANYA ter-scope badan usaha.

    FASE E-7 (E7.4): dulu `kas_besar` dijumlahkan lintas grup tanpa filter apa pun,
    sehingga kartu "Kas Besar" di layar PT Kain Suka Cita memperlihatkan uang CV Kanda
    Suka. Sekarang keduanya memakai scope yang sama, dan sisa data tingkat grup
    dilaporkan TERPISAH (`group_cash_pending`) agar bisa ditegur, bukan disembunyikan.
    """
    await require_permission(request, "cash", "view")
    ctx = await entity_ctx(request)
    entities = resolve_scope_ids(ctx, entity_id)

    def _agg(rows: List[Dict[str, Any]]) -> Dict[str, float]:
        cin = sum(float(r.get("amount", 0) or 0) for r in rows if r.get("direction") == "in")
        cout = sum(float(r.get("amount", 0) or 0) for r in rows if r.get("direction") == "out")
        return {"in": round(cin, 2), "out": round(cout, 2), "balance": round(cin - cout, 2), "count": len(rows)}

    all_rows = await db.cash_transactions.find({"status": {"$ne": "void"}}, {"_id": 0}).to_list(2000)
    kecil_q = [r for r in all_rows if r.get("cash_type") == "kas_kecil"
               and r.get("entity_id") in entities]
    besar_q = [r for r in all_rows if r.get("cash_type") == "kas_besar"
               and r.get("entity_id") in entities]

    # breakdown kas kecil per entitas (untuk konteks "all")
    per_entity: Dict[str, Dict[str, float]] = {}
    for r in all_rows:
        if r.get("cash_type") != "kas_kecil":
            continue
        eid = r.get("entity_id", "")
        if eid not in entities:
            continue
        per_entity.setdefault(eid, {"in": 0.0, "out": 0.0})
        per_entity[eid]["in" if r.get("direction") == "in" else "out"] += float(r.get("amount", 0) or 0)
    for eid, v in per_entity.items():
        v["balance"] = round(v["in"] - v["out"], 2)
        v["in"] = round(v["in"], 2)
        v["out"] = round(v["out"], 2)

    return {
        "scope": entity_id or ("all" if ctx.view_all else ctx.active_entity_id),
        "kas_kecil": _agg(kecil_q),
        "kas_besar": _agg(besar_q),
        "kas_kecil_per_entity": per_entity,
        # E7.4 — sisa data kas tingkat grup (harus nol setelah migrasi dijalankan).
        "group_cash_pending": await cash_entity_service.group_cash_pending(db),
    }


@router.post("/cash-transactions")
async def create_cash_transaction(payload: CashTransactionCreate, request: Request) -> Dict[str, Any]:
    """Catat transaksi kas masuk/keluar."""
    actor = await require_permission(request, "cash", "create")
    ctx = await entity_ctx(request)
    if payload.cash_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail="cash_type harus kas_kecil atau kas_besar")
    if payload.direction not in VALID_DIRECTIONS:
        raise HTTPException(status_code=400, detail="direction harus in atau out")
    if float(payload.amount or 0) <= 0:
        raise HTTPException(status_code=400, detail="Nominal harus lebih dari 0")

    # FASE E-7 (E7.4) — kas tingkat grup DIHAPUS: `kas_besar` tetap berarti
    # "buku bank/transfer", tetapi uangnya WAJIB milik satu badan usaha. Sebelum ini
    # kode di sini memaksa `entity_id="all"` sehingga penerimaan piutang KSC tidak
    # pernah muncul di kas KSC (13 dari 19 transaksi demo terkena).
    from services.cash_entity_service import assert_owned
    entity_id = assert_owned(payload.entity_id or ctx.active_entity_id,
                             what="Transaksi kas")

    number = await _next_cash_number(entity_id)
    doc = {
        "id": new_id("cash"),
        "number": number,
        "cash_type": payload.cash_type,
        "direction": payload.direction,
        "amount": round(float(payload.amount), 2),
        "category": payload.category.strip(),
        "description": payload.description.strip(),
        "entity_id": entity_id,
        "ref_type": payload.ref_type,
        "ref_id": payload.ref_id,
        "txn_date": payload.txn_date or now_iso(),
        "account_id": getattr(payload, "account_id", "") or "",
        "reconciled": False,
        "status": "posted",
        "created_by": payload.created_by,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.cash_transactions.insert_one(doc)
    await audit(actor["name"], "cash_transaction_created", "cash_transaction", doc["id"], {
        "number": number, "cash_type": doc["cash_type"], "direction": doc["direction"],
        "amount": doc["amount"], "entity_id": entity_id,
    })
    return safe_doc(doc)


@router.post("/cash-transactions/{txn_id}/void")
async def void_cash_transaction(txn_id: str, request: Request) -> Dict[str, Any]:
    """Batalkan/void transaksi kas (saldo tidak lagi dihitung)."""
    actor = await require_permission(request, "cash", "delete")
    txn = await db.cash_transactions.find_one({"id": txn_id}, {"_id": 0})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaksi kas tidak ditemukan")
    if txn.get("status") == "void":
        raise HTTPException(status_code=409, detail="Transaksi sudah di-void")
    updated = await db.cash_transactions.find_one_and_update(
        {"id": txn_id}, {"$set": {"status": "void", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    await audit(actor["name"], "cash_transaction_voided", "cash_transaction", txn_id, {})
    return safe_doc(updated)
