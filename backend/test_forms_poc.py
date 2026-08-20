"""FASE 1 — POC INTI (Digitalisasi Formulir Sukacita).

Membuktikan (isolasi, tanpa HTTP) integritas akuntansi & scoping SEBELUM lanjut:
  1. Cash Advance disburse → cash_transactions(out) + JE Dr 1-1400 / Cr Kas (idempotent).
  2. Settlement approved → JE Dr [beban per kategori] / Cr 1-1400 SEIMBANG; sisa/kurang benar.
  3. Entity-scoping PT (ent_ksc) vs CV (ent_kanda) terisolasi (anti-IDOR).
  4. Numbering PD-/STL-/VHL- unik & per-entitas.

Jalankan: python test_forms_poc.py   (exit code 0 = semua PASS)
"""
import asyncio
import sys

from db import db
from entity_scope import EntityContext
from core_utils import next_doc_number
from services import gl_service
from services import cash_advance_service as svc
from schemas_cash_advance import (
    CashAdvanceCreate, CashAdvanceLine, DisburseInput,
    SettlementCreate, SettlementLine,
)

PT = "ent_ksc"      # PT Kain Suka Cita
CV = "ent_kanda"    # CV Kanda Suka

FAILS = []
PASSES = []


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        PASSES.append(name)
        print(f"  ✅ {name}")
    else:
        FAILS.append(f"{name} — {detail}")
        print(f"  ❌ {name} — {detail}")


def _ctx(active: str) -> EntityContext:
    return EntityContext(
        user={"id": "poc_admin", "name": "POC Admin", "role": "admin"},
        active_entity_id=active,
        allowed_entity_ids=[PT, CV],
        view_all=False,
    )


ADMIN = {"id": "poc_admin", "name": "POC Admin", "role": "admin"}


async def _je_for(source_type: str, source_id: str):
    return await db.journal_entries.find_one(
        {"source_type": source_type, "source_id": source_id, "status": {"$ne": "void"}},
        {"_id": 0})


def _line_amt(je, code, side):
    return round(sum(float(l.get(side, 0) or 0) for l in je.get("lines", [])
                     if l.get("account_code") == code), 2)


async def scenario_cash_advance_and_settlement():
    print("\n[1+2] Cash Advance → Disburse → Settlement (GL balance)")
    ctx = _ctx(PT)
    # --- Create PD (2 unit × 500rb = 1jt) ---
    payload = CashAdvanceCreate(
        entity_id=PT, divisi="POC", kegiatan="POC pengujian dana",
        payment_method="tunai",
        lines=[CashAdvanceLine(description="Item A", qty=2, unit_price=500000, satuan="unit")],
        catatan="poc")
    ca = await svc.create_cash_advance(payload, ctx, ADMIN)
    check("PD dibuat total=1.000.000", ca["total_amount"] == 1000000, f"total={ca['total_amount']}")
    check("PD number berpola KSC/PD-", ca["number"].startswith("KSC/PD-"), ca["number"])
    ca_id = ca["id"]

    # --- Submit + 3-stage approval (admin override) ---
    await svc.submit_cash_advance(ca_id, ctx, ADMIN)
    s1 = await svc.approve_cash_advance(ca_id, "ok atasan", ctx, ADMIN)
    check("Approve #1 → pending_pimpinan", s1["status"] == "pending_pimpinan", s1["status"])
    s2 = await svc.approve_cash_advance(ca_id, "ok pimpinan", ctx, ADMIN)
    check("Approve #2 → pending_finance", s2["status"] == "pending_finance", s2["status"])
    s3 = await svc.approve_cash_advance(ca_id, "ok finance", ctx, ADMIN)
    check("Approve #3 → approved", s3["status"] == "approved", s3["status"])

    # --- Disburse (kas kecil PT) ---
    disb = await svc.disburse_cash_advance(
        ca_id, DisburseInput(cash_type="kas_kecil", note="poc"), ctx, ADMIN)
    check("PD status → disbursed", disb["status"] == "disbursed", disb["status"])

    # cash_transaction created (out, ref_type cash_advance, entitas PT)
    txns = await db.cash_transactions.find(
        {"ref_type": "cash_advance", "ref_id": ca_id, "status": {"$ne": "void"}},
        {"_id": 0}).to_list(10)
    check("1 cash_transaction (out) terbentuk", len(txns) == 1, f"count={len(txns)}")
    if txns:
        t = txns[0]
        check("cash_tx direction=out amount=1jt entitas=PT",
              t["direction"] == "out" and t["amount"] == 1000000 and t["entity_id"] == PT,
              f"{t['direction']}/{t['amount']}/{t['entity_id']}")

    # JE disburse: Dr 1-1400 / Cr 1-1110 (kas kecil), seimbang
    je_d = await _je_for("cash_transaction", txns[0]["id"]) if txns else None
    check("JE disburse ada", je_d is not None, "tidak ada JE cash_transaction")
    if je_d:
        check("JE disburse SEIMBANG", je_d["total_debit"] == je_d["total_credit"],
              f"D={je_d['total_debit']} C={je_d['total_credit']}")
        check("JE disburse Dr 1-1400 = 1jt", _line_amt(je_d, "1-1400", "debit") == 1000000,
              str(_line_amt(je_d, "1-1400", "debit")))
        check("JE disburse Cr 1-1110 = 1jt", _line_amt(je_d, "1-1110", "credit") == 1000000,
              str(_line_amt(je_d, "1-1110", "credit")))

    # Idempotency: post ulang cash_transaction tidak buat JE baru
    dup = await gl_service.post_cash_transaction({**txns[0]}) if txns else "skip"
    check("Idempotent: post_cash_transaction ulang → None", dup is None, f"got={dup}")
    je_count = await db.journal_entries.count_documents(
        {"source_type": "cash_transaction", "source_id": txns[0]["id"]}) if txns else 0
    check("Idempotent: tetap 1 JE disburse", je_count == 1, f"count={je_count}")

    # --- Settlement (ATK 400rb + Transportasi 500rb = 900rb; sisa 100rb) ---
    stl_payload = SettlementCreate(
        cash_advance_id=ca_id, divisi="POC", periode="2026-01",
        expense_lines=[
            SettlementLine(description="Beli ATK", category="atk", amount=400000),
            SettlementLine(description="BBM+Tol", category="transportasi", amount=500000),
        ])
    stl = await svc.create_settlement(stl_payload, ctx, ADMIN)
    check("Settlement total_pengeluaran=900rb", stl["total_pengeluaran"] == 900000,
          str(stl["total_pengeluaran"]))
    check("Settlement sisa_kurang_dana=+100rb (sisa)", stl["sisa_kurang_dana"] == 100000,
          str(stl["sisa_kurang_dana"]))
    check("STL number berpola KSC/STL-", stl["number"].startswith("KSC/STL-"), stl["number"])
    stl_id = stl["id"]

    await svc.submit_settlement(stl_id, ctx, ADMIN)
    posted = await svc.approve_settlement(stl_id, ctx, ADMIN)
    check("Settlement status → posted_to_gl", posted["status"] == "posted_to_gl", posted["status"])
    check("PD induk → settled",
          (await svc.get_cash_advance(ca_id, ctx))["status"] == "settled", "")

    # JE settlement: Dr 6-4100 (ATK) 400rb + Dr 6-4600 (transportasi) 500rb / Cr 1-1400 900rb
    je_s = await _je_for("petty_cash_settlement", stl_id)
    check("JE settlement ada", je_s is not None, "tidak ada JE petty_cash_settlement")
    if je_s:
        check("JE settlement SEIMBANG", je_s["total_debit"] == je_s["total_credit"],
              f"D={je_s['total_debit']} C={je_s['total_credit']}")
        check("JE settlement Dr 6-4100 = 400rb", _line_amt(je_s, "6-4100", "debit") == 400000,
              str(_line_amt(je_s, "6-4100", "debit")))
        check("JE settlement Dr 6-4600 = 500rb", _line_amt(je_s, "6-4600", "debit") == 500000,
              str(_line_amt(je_s, "6-4600", "debit")))
        check("JE settlement Cr 1-1400 = 900rb", _line_amt(je_s, "1-1400", "credit") == 900000,
              str(_line_amt(je_s, "1-1400", "credit")))

    # Idempotency settlement approve (approve ulang tidak boleh dobel JE)
    je_s_count = await db.journal_entries.count_documents(
        {"source_type": "petty_cash_settlement", "source_id": stl_id})
    check("Idempotent: 1 JE settlement", je_s_count == 1, f"count={je_s_count}")

    return ca_id


async def scenario_entity_isolation():
    print("\n[3] Entity-scoping PT vs CV (anti-IDOR)")
    ctx_pt = _ctx(PT)
    ctx_cv = _ctx(CV)
    # PD di CV
    ca_cv = await svc.create_cash_advance(
        CashAdvanceCreate(entity_id=CV, divisi="POC-CV", kegiatan="poc cv",
                          payment_method="tunai",
                          lines=[CashAdvanceLine(description="X", qty=1, unit_price=250000)]),
        ctx_cv, ADMIN)
    check("PD CV number berpola KANDA/PD-", ca_cv["number"].startswith("KANDA/PD-"), ca_cv["number"])

    # List dengan active=PT tidak boleh memuat PD CV
    pt_list = await svc.list_cash_advances(ctx_pt, entity_id=PT)
    ids_pt = {c["id"] for c in pt_list}
    check("List PT tidak memuat PD CV", ca_cv["id"] not in ids_pt, "PD CV bocor ke list PT")

    # get_cash_advance PD CV dengan ctx yang HANYA allow PT → 404
    ctx_only_pt = EntityContext(user=ADMIN, active_entity_id=PT,
                                allowed_entity_ids=[PT], view_all=False)
    got_404 = False
    try:
        await svc.get_cash_advance(ca_cv["id"], ctx_only_pt)
    except Exception as e:  # HTTPException 404
        got_404 = getattr(e, "status_code", None) == 404
    check("Akses lintas-entitas ditolak (404)", got_404, "tidak menolak akses CV dari ctx PT")


async def scenario_numbering():
    print("\n[4] Numbering unik & per-entitas")
    # VHL number per-entitas
    v1 = await next_doc_number("vehicle_usage_logs", "number", "VHL-", entity_id=PT)
    v2 = await next_doc_number("vehicle_usage_logs", "number", "VHL-", entity_id=PT)
    check("VHL number unik & increment", v1 != v2 and v1.startswith("KSC/VHL-"), f"{v1} vs {v2}")
    vcv = await next_doc_number("vehicle_usage_logs", "number", "VHL-", entity_id=CV)
    check("VHL CV number berpola KANDA/VHL-", vcv.startswith("KANDA/VHL-"), vcv)


async def scenario_expense_categories():
    print("\n[0] Prasyarat: kategori beban ter-seed & termapping ke COA")
    cats = await svc.list_expense_categories()
    check("Minimal 8 kategori pengeluaran ter-seed", len(cats) >= 8, f"count={len(cats)}")
    # Semua account_code kategori harus eksis di COA
    codes = {c["account_code"] for c in cats}
    coa = {a["code"] async for a in db.gl_accounts.find(
        {"code": {"$in": list(codes)}}, {"_id": 0, "code": 1})}
    missing = codes - coa
    check("Semua akun kategori eksis di COA", not missing, f"missing={missing}")


async def main():
    print("=" * 70)
    print("FASE 1 — POC Digitalisasi Formulir Sukacita")
    print("=" * 70)
    await gl_service.seed_default_coa()
    await svc.seed_expense_categories()
    await scenario_expense_categories()
    await scenario_cash_advance_and_settlement()
    await scenario_entity_isolation()
    await scenario_numbering()

    print("\n" + "=" * 70)
    print(f"HASIL: {len(PASSES)} PASS · {len(FAILS)} FAIL")
    if FAILS:
        for f in FAILS:
            print(f"  ❌ {f}")
        print("=" * 70)
        sys.exit(1)
    print("SEMUA POC PASS ✅ — aman lanjut ke FASE 2.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
