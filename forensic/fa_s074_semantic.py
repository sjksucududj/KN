"""fa_s074_semantic.py — AUDIT S074 P#1: VALUE-LEVEL semantic assertions.

Goal: many endpoints are only 'hit' (HTTP 200) but never asserted for CORRECTNESS.
This probe asserts GL/finance correctness at the DATA level and empirically
re-grounds META-GATE-GL (unbalanced JE survives the integrity gate).

Mostly READ-ONLY. The META-GATE step inserts ONE synthetic JE then deletes it.
"""
import asyncio
import os
import subprocess
import sys

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from db import db
from services import gl_service as gl

findings = []


def F(fid, sev, title, ev):
    findings.append((fid, sev, title, ev))
    print(f"[{sev}] {fid}: {title}\n   -> {ev}", flush=True)


async def s1_global_je_balance():
    print("\n=== S1: GLOBAL JE balance (every posted JE: Sdebit==Scredit) ===")
    bad = []
    total = 0
    async for je in db.journal_entries.find({"status": "posted"}, {"_id": 0}):
        total += 1
        d = round(sum(float(l.get("debit", 0)) for l in je.get("lines", [])), 2)
        c = round(sum(float(l.get("credit", 0)) for l in je.get("lines", [])), 2)
        td = round(float(je.get("total_debit", 0)), 2)
        tc = round(float(je.get("total_credit", 0)), 2)
        if abs(d - c) > 0.01 or abs(td - tc) > 0.01:
            bad.append((je.get("number"), je.get("source_type"), d, c, td, tc))
    print(f"   posted JE scanned={total} unbalanced={len(bad)}")
    for b in bad[:15]:
        print("   UNBAL", b)
    if bad:
        F("DATA-UNBAL-JE", "P0", "Ada journal_entries posted yang TIDAK seimbang",
          f"{len(bad)} JE dengan Sdebit!=Scredit di DB bersih: {bad[:5]}")
    else:
        print("   OK: semua JE posted seimbang (di DB bersih)")


async def s2_trial_balance_per_entity():
    print("\n=== S2: Trial balance per entity (Sdebit==Scredit across posted JE) ===")
    for eid in ["ent_ksc", "ent_kanda"]:
        d = c = 0.0
        async for je in db.journal_entries.find({"status": "posted", "entity_id": eid}, {"_id": 0, "lines": 1}):
            for l in je.get("lines", []):
                d += float(l.get("debit", 0))
                c += float(l.get("credit", 0))
        d, c = round(d, 2), round(c, 2)
        status = "OK" if abs(d - c) < 0.01 else "IMBALANCE"
        print(f"   {eid}: Sdebit={d:,.2f} Scredit={c:,.2f} -> {status}")
        if abs(d - c) >= 0.01:
            F("TB-IMBALANCE", "P0", f"Trial balance {eid} tidak seimbang",
              f"Sdebit={d} != Scredit={c} (delta {round(d-c,2)})")


async def s3_inventory_recon():
    print("\n=== S3: Inventory reconciliation (physical roll value vs GL 1-1300) ===")
    try:
        rec = await gl.inventory_reconciliation()
    except Exception as e:
        print(f"   inventory_reconciliation error: {e}")
        return None
    import json
    print("   " + json.dumps(rec, default=str)[:900])
    return rec


async def s4_meta_gate_gl():
    """Empirically re-ground META-GATE-GL: insert an unbalanced JE, run the gate,
    show it still passes ('SEMUA INVARIAN VALID'), then delete the synthetic JE."""
    print("\n=== S4: META-GATE-GL (does integrity gate catch unbalanced JE?) ===")
    # 4a. Static: does verify_data_integrity even check JE balance / trial balance?
    src = open("/app/scripts/verify_data_integrity.py").read()
    hits = [k for k in ("total_debit", "total_credit", "trial_balance", "trial-balance",
                        "debit == credit", "Sdebit", "neraca saldo") if k in src]
    print(f"   gate source references to JE-balance/trial-balance: {hits or 'NONE'}")
    # 4b. Dynamic mutation: inject unbalanced JE
    synth = {
        "id": "AUDIT_S074_UNBAL", "number": "AUDIT-UNBAL-JE", "date": "2026-03-01",
        "description": "AUDIT S074 mutation: debit 1000 != credit 1",
        "source": "audit", "source_type": "audit", "source_id": "AUDIT_S074_UNBAL",
        "lines": [{"account_code": "1-1100", "debit": 1000.0, "credit": 0.0},
                  {"account_code": "4-1000", "debit": 0.0, "credit": 1.0}],
        "total_debit": 1000.0, "total_credit": 1.0, "status": "posted",
        "entity_id": "ent_ksc", "created_by": "audit", "created_at": "2026-03-01T00:00:00+00:00",
    }
    await db.journal_entries.delete_many({"id": "AUDIT_S074_UNBAL"})
    await db.journal_entries.insert_one(dict(synth))
    try:
        p = subprocess.run([sys.executable, "/app/scripts/verify_data_integrity.py"],
                           capture_output=True, text=True, timeout=120)
        out = (p.stdout or "") + (p.stderr or "")
        gate_green = "SEMUA INVARIAN VALID" in out
        tail = "\n".join([l for l in out.splitlines() if "PASS" in l or "FAIL" in l][-3:])
        print(f"   gate exit={p.returncode} green={gate_green}\n   {tail}")
        if not hits and gate_green:
            F("META-GATE-GL", "P1",
              "CI gate BUTA terhadap keseimbangan jurnal (unbalanced JE survives)",
              f"verify_data_integrity.py tidak punya cek JE-balance/trial-balance (grep=NONE). "
              f"Disuntik JE debit 1000 != credit 1 -> gate TETAP hijau (exit {p.returncode}, "
              f"'SEMUA INVARIAN VALID'). Akar mengapa RET-2/PRET-GL/VB-CANCEL-GL/DATA-UNBAL lolos CI.")
    finally:
        await db.journal_entries.delete_many({"id": "AUDIT_S074_UNBAL"})
        print("   [cleanup] synthetic unbalanced JE removed")


async def main():
    for fn in (s1_global_je_balance, s2_trial_balance_per_entity, s3_inventory_recon, s4_meta_gate_gl):
        try:
            await fn()
        except Exception as e:
            import traceback
            print(f"[EXC] {fn.__name__}: {e}\n{traceback.format_exc()[-600:]}")
    print("\n" + "=" * 66)
    print(f"SEMANTIC PROBE: {len(findings)} finding(s)")
    for fid, sev, title, _ in findings:
        print(f"  [{sev}] {fid}: {title}")


if __name__ == "__main__":
    asyncio.run(main())
