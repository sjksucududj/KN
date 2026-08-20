"""fa_edge_branches.py — AUDIT #073 F1: white-box exercise of never-taken FINANCIAL
branches in gl_service (Dijkstra: untaken branch = unverified behaviour).

Directly calls gl_service with synthetic inputs to trigger edge branches, asserts
correctness. Cleans up its own synthetic journal_entries. READ-mostly.
"""
import asyncio
import sys
sys.path.insert(0, "/app/backend")

from db import db
from services import gl_service as gl

findings = []


def finding(fid, sev, title, ev):
    findings.append((fid, sev, title, ev))
    print(f"[{sev}] {fid}: {title}\n     -> {ev}", flush=True)


async def cleanup(source_ids):
    for sid in source_ids:
        await db.journal_entries.delete_many({"source_id": sid})


async def test_cogs_zero():
    """Branch gl_service:645 `if total_cogs <= EPS: return None`.
    Revenue-eligible sale whose cost is unknown (no rolls, no snapshot, WAC=0)
    -> revenue posted but COGS skipped -> margin overstated + inventory not relieved."""
    print("\n=== EDGE: revenue-eligible sale with UNKNOWN cost (COGS-zero branch) ===")
    sid = "AUDIT_COGSZERO_001"
    await cleanup([sid])
    order = {
        "id": sid, "number": "AUDIT-SO-COGS0", "status": "shipped",  # revenue eligible
        "entity_id": "ent_ksc",
        "payment_term_code": "net30",           # AR (not cash)
        "grand_total": 1_110_000.0, "ppn_amount": 110_000.0,
        "items": [{"product_id": "NONEXISTENT_PROD_AUDIT", "quantity": 10,
                   "base_quantity": 10, "price": 100_000.0, "subtotal": 1_000_000.0}],
        "created_at": "2026-03-01T00:00:00+00:00",
    }
    rev_je = await gl.post_sales_order(order)
    cogs_je = await gl.post_order_cogs(order)
    rev_ok = rev_je is not None
    cogs_posted = cogs_je is not None
    print(f"     revenue_JE={'posted' if rev_ok else 'none'} cogs_JE={'posted' if cogs_posted else 'SKIPPED'}")
    if rev_ok and not cogs_posted:
        # confirm revenue amount booked
        rev_amt = rev_je.get("total_credit")
        finding("COGS-ZERO", "P2-MED",
                "Penjualan revenue-eligible dgn cost=0 membukukan PENDAPATAN tanpa HPP (silent)",
                f"post_sales_order membukukan Pendapatan Rp {rev_amt:,.0f} (JE {rev_je.get('number')}), "
                f"tetapi post_order_cogs return None (total_cogs<=EPS) -> HPP TIDAK dicatat & Persediaan "
                f"tak direlief di GL. Margin kotor overstated bila produk ber-cost 0/unknown. "
                f"Cabang gl_service.py:645 tak pernah diuji korpus.")
    else:
        print("     (no gap: cost resolved or cogs posted)")
    await cleanup([sid])


async def test_manual_entry_validation():
    """Branches gl_service:439-443 — reject negative & malformed lines."""
    print("\n=== EDGE: manual journal validation guards (L439-443) ===")

    class P:  # minimal payload duck-type
        def __init__(self, lines, date="2026-03-01", description="audit", entity_id="ent_ksc"):
            self.lines = lines; self.date = date; self.description = description
            self.entity_id = entity_id; self.source_label = "AUDIT"
    actor = {"id": "u", "name": "Audit"}
    cases = [
        ("negative-debit", [{"account_code": "1-1100", "debit": -100, "credit": 0},
                            {"account_code": "4-1000", "debit": 0, "credit": -100}]),
        ("both-sides", [{"account_code": "1-1100", "debit": 100, "credit": 100},
                        {"account_code": "4-1000", "debit": 0, "credit": 0}]),
        ("unbalanced", [{"account_code": "1-1100", "debit": 100, "credit": 0},
                        {"account_code": "4-1000", "debit": 0, "credit": 50}]),
    ]
    for name, lines in cases:
        try:
            je = await gl.create_manual_entry(P(lines), actor, entity_id="ent_ksc")
            finding("GL-VAL", "P2",
                    f"create_manual_entry MENERIMA jurnal invalid ({name})",
                    f"lines={lines} -> JE {je.get('number') if je else je} (seharusnya ditolak).")
            if je:
                await db.journal_entries.delete_many({"id": je.get("id")})
        except Exception as e:
            print(f"     {name}: rejected OK ({type(e).__name__}: {str(e)[:60]})")


async def test_void_idempotency():
    """Branch gl_service:497 — void an already-void entry."""
    print("\n=== EDGE: void already-void entry (L497) ===")

    class P:
        def __init__(self):
            self.lines = [{"account_code": "1-1100", "debit": 1000, "credit": 0},
                          {"account_code": "4-9000", "debit": 0, "credit": 1000}]
            self.date = "2026-03-01"; self.description = "audit-void"; self.entity_id = "ent_ksc"
            self.source_label = "AUDIT-VOID"
    actor = {"id": "u", "name": "Audit"}
    je = await gl.create_manual_entry(P(), actor, entity_id="ent_ksc")
    jid = je["id"]
    v1 = await gl.void_entry(jid, actor)
    v2 = await gl.void_entry(jid, actor)
    tb_effect = await db.journal_entries.find_one({"id": jid}, {"_id": 0, "status": 1})
    print(f"     void1={bool(v1)} void2={bool(v2)} final_status={tb_effect.get('status')}")
    if tb_effect.get("status") != "void":
        finding("GL-VOID", "P2", "void_entry tidak menandai status void dengan benar",
                f"status akhir={tb_effect.get('status')}")
    await db.journal_entries.delete_many({"id": jid})


async def test_ic_transfer_same_entity():
    """Branch gl_service:703 — inter-company transfer src==dst guard."""
    print("\n=== EDGE: IC transfer src==dst guard (L703) ===")
    t = {"id": "AUDIT_IC_SAME", "source_entity_id": "ent_ksc", "dest_entity_id": "ent_ksc",
         "items": [{"product_id": "x", "quantity": 1}]}
    res = await gl.post_intercompany_transfer(t)
    print(f"     result={res}")
    # Expect graceful skip (dict with note or None), NOT a crash / balanced-bad JE
    await db.journal_entries.delete_many({"source_id": "AUDIT_IC_SAME"})


async def main():
    for fn in (test_cogs_zero, test_manual_entry_validation, test_void_idempotency,
               test_ic_transfer_same_entity):
        try:
            await fn()
        except Exception as e:
            import traceback
            print(f"[EXC] {fn.__name__}: {e}\n{traceback.format_exc()[-500:]}")
    print("\n" + "=" * 66)
    print(f"EDGE-BRANCH PROBE: {len(findings)} finding(s)")
    for fid, sev, title, _ in findings:
        print(f"  [{sev}] {fid}: {title}")


if __name__ == "__main__":
    asyncio.run(main())
