#!/usr/bin/env python3
"""POC F4 — validasi derivasi STAGE/SUB-STATUS + backfill idempotent (ISOLASI).

Jalankan: cd /app/backend && python scripts/poc_so_status.py
Tujuan: buktikan mapping benar utk SEMUA status SO yang ada + skenario kunci
(normal, nilai besar/waiting_approval, backorder approved, partial pick/ship)
SEBELUM mengubah alur transisi & FE.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.so_status import (  # noqa: E402
    derive_stage_substatus, stage_fields, backfill_so_status, VALID_STAGES,
    STAGE_RESERVED, STAGE_APPROVED, STAGE_CONFIRMED, STAGE_PICKED, STAGE_SHIPPED,
    STAGE_DELIVERED, STAGE_CANCELLED,
)

GREEN, RED, CYAN, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[0m"
_fail = 0


def check(label, got, expected):
    global _fail
    ok = got == expected
    if not ok:
        _fail += 1
    print(f"  {(GREEN+'[PASS]') if ok else (RED+'[FAIL]')}{RESET} {label} → {got}" + ("" if ok else f"  (expected {expected})"))


def scenarios():
    print(f"{CYAN}== 1) Skenario unit (pure mapping) =={RESET}")
    # normal kecil: reserved tanpa approval → Reserved/siap_disahkan
    check("reserved (no approval)", derive_stage_substatus({"status": "reserved"}),
          (STAGE_RESERVED, ["siap_disahkan"]))
    # nilai besar: reserved butuh approval → Reserved/menunggu_validasi
    check("reserved (approval_required)", derive_stage_substatus({"status": "reserved", "approval_required": True}),
          (STAGE_RESERVED, ["menunggu_validasi"]))
    # menunggu approval nilai
    check("waiting_approval (role mgr)", derive_stage_substatus({"status": "waiting_approval", "required_approval_role": "manager"}),
          (STAGE_RESERVED, ["menunggu_approval_nilai"]))
    # approved + stok siap → Approved/siap_confirm
    check("approved (stok siap)", derive_stage_substatus({"status": "approved"}),
          (STAGE_APPROVED, ["siap_confirm"]))
    # approved + backorder → Approved/menunggu_stok (kunci F4!)
    check("approved + backorder", derive_stage_substatus({"status": "approved", "has_backorder": True}),
          (STAGE_APPROVED, ["menunggu_stok"]))
    # pure backorder pra-approval
    check("waiting_stock", derive_stage_substatus({"status": "waiting_stock"}),
          (STAGE_RESERVED, ["menunggu_stok"]))
    # confirmed
    check("confirmed", derive_stage_substatus({"status": "confirmed"}),
          (STAGE_CONFIRMED, ["siap_pick"]))
    # partial pick/ship
    check("partially_picked", derive_stage_substatus({"status": "partially_picked"}),
          (STAGE_PICKED, ["sebagian_dipick"]))
    check("picked", derive_stage_substatus({"status": "picked"}),
          (STAGE_PICKED, ["siap_kirim"]))
    check("partially_shipped", derive_stage_substatus({"status": "partially_shipped"}),
          (STAGE_SHIPPED, ["sebagian_dikirim"]))
    check("shipped", derive_stage_substatus({"status": "shipped"}), (STAGE_SHIPPED, []))
    check("done", derive_stage_substatus({"status": "done"}), (STAGE_DELIVERED, []))
    check("cancelled", derive_stage_substatus({"status": "cancelled"}), (STAGE_CANCELLED, ["dibatalkan"]))


async def db_checks():
    from db import db
    print(f"\n{CYAN}== 2) Derivasi atas SEMUA SO di DB =={RESET}")
    orders = await db.sales_orders.find({}, {"_id": 0, "id": 1, "number": 1, "status": 1,
                                             "has_backorder": 1, "approval_required": 1}).to_list(100000)
    print(f"  total SO: {len(orders)}")
    by_stage = {}
    bad = 0
    for o in orders:
        st, sub = derive_stage_substatus(o)
        by_stage[st] = by_stage.get(st, 0) + 1
        if st not in VALID_STAGES:
            bad += 1
            print(f"  {RED}[FAIL]{RESET} {o.get('number')} status={o.get('status')} → stage tidak valid {st}")
    print("  distribusi stage:", by_stage)
    check("semua SO punya stage valid", bad, 0)

    print(f"\n{CYAN}== 3) Backfill idempotent (2x) =={RESET}")
    r1 = await backfill_so_status(db)
    r2 = await backfill_so_status(db)
    print("  run#1:", r1, "| run#2:", r2)
    check("backfill #1 invalid=0", r1["invalid"], 0)
    check("backfill #2 invalid=0 (idempotent)", r2["invalid"], 0)
    miss = await db.sales_orders.count_documents({"stage": {"$exists": False}})
    check("SO tanpa stage setelah backfill", miss, 0)
    invalid_stored = await db.sales_orders.count_documents({"stage": {"$nin": list(VALID_STAGES)}})
    check("SO dengan stage invalid (stored)", invalid_stored, 0)


async def main():
    scenarios()
    await db_checks()
    print()
    if _fail:
        print(f"{RED}== POC GAGAL: {_fail} cek gagal =={RESET}")
        return 1
    print(f"{GREEN}== POC LULUS: semua cek derivasi & backfill OK =={RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
