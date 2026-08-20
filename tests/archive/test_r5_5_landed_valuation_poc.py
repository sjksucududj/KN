"""R5.5 — Landed-cost-aware valuation — POC (in-process, deterministic).

Membuktikan bahwa valuasi retur/regrade/write-off memakai WAC yang SUDAH termasuk
landed cost (freight/duty/handling), bukan harga PO mentah:

  A. Setelah landed cost diterapkan ke roll (via landed_cost_service, additive $inc unit_cost),
     costing_service.wac_for_product mengembalikan pecahan basis: wac = wac_base + wac_landed,
     landed_included == True, dan WAC naik dibanding sebelum landed.
  B. gl_service._avg_unit_cost (dipakai return_service utk nilai barang retur / COGS reversal /
     regrade) mengembalikan WAC landed-inclusive yang sama.
  C. Nilai WRITE-OFF (release scrap: qty × roll.unit_cost) memakai unit_cost landed-inclusive,
     sehingga > nilai berbasis harga dasar saja (base_unit_cost). landed_cost_total roll konsisten.
  D. Field basis (base_unit_cost/unit_cost/landed) tersedia utk audit (user story R5.5-3).

Catatan: POC ini memodifikasi cost roll (landed) → JALANKAN seed ulang setelahnya
(dilakukan otomatis oleh runner di bawah bila --reseed, atau panggil manual).
"""
import os
import sys
import asyncio

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from db import db  # noqa: E402
from services import costing_service, landed_cost_service, gl_service  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  \u2705 {name}")
    else:
        FAIL += 1
        print(f"  \u274c {name}  {extra}")


async def pick_product_entity():
    """Cari (product_id, entity_id) dgn >=2 roll hidup ber-cost & landed belum diterapkan."""
    LIVE = ["available", "reserved", "committed", "picked", "packed", "quarantine"]
    rolls = await db.inventory_rolls.find(
        {"status": {"$in": LIVE}, "base_unit_cost": {"$gt": 0}, "length_remaining": {"$gt": 0}},
        {"_id": 0, "id": 1, "product_id": 1, "owner_entity_id": 1, "unit_cost": 1,
         "base_unit_cost": 1, "length_remaining": 1, "length_initial": 1}).to_list(5000)
    groups = {}
    for r in rolls:
        # landed belum diterapkan → unit_cost ~= base_unit_cost
        if abs(float(r.get("unit_cost", 0)) - float(r.get("base_unit_cost", 0))) > 0.01:
            continue
        key = (r["product_id"], r.get("owner_entity_id", ""))
        groups.setdefault(key, []).append(r)
    best = max(groups.items(), key=lambda kv: len(kv[1]), default=(None, []))
    return best


async def main():
    print("== R5.5 LANDED-COST-AWARE VALUATION POC ==")
    (pid, eid), rolls = await pick_product_entity()
    check("prasyarat: ada produk+entitas dgn >=1 roll hidup ber-cost tanpa landed",
          pid is not None and len(rolls) >= 1, f"pid={pid} eid={eid} n={len(rolls)}")
    if not pid:
        print(f"\n=== HASIL R5.5: PASS={PASS} FAIL={FAIL} ===")
        return

    # WAC sebelum landed
    costing_service.invalidate_wac_cache()
    w0 = await costing_service.wac_for_product(pid, entity_id=eid, use_cache=False)
    base_wac = w0["wac"]
    check("sebelum landed: landed_included == False", w0.get("landed_included") is False,
          f"{w0.get('landed_included')} wac_landed={w0.get('wac_landed')}")

    # Terapkan landed cost ~20% dari nilai dasar (via jalur nyata landed_cost_service).
    roll_ids = [r["id"] for r in rolls]
    full = await db.inventory_rolls.find({"id": {"$in": roll_ids}}, {"_id": 0}).to_list(5000)
    base_value = sum(float(r.get("base_unit_cost", 0) or 0) * float(r.get("length_initial", 0) or 0)
                     for r in full)
    total_landed = round(0.20 * base_value, 2)
    alloc = landed_cost_service.compute_allocation(full, total_landed, basis="value")
    updated = await landed_cost_service.apply_allocation_to_rolls("LCV-R55POC", alloc["allocations"])
    check("landed cost diterapkan ke roll (>=1)", updated >= 1, f"updated={updated} total_landed={total_landed}")

    # A) WAC breakdown setelah landed
    costing_service.invalidate_wac_cache()
    w1 = await costing_service.wac_for_product(pid, entity_id=eid, use_cache=False)
    check("A1: landed_included == True setelah landed", w1.get("landed_included") is True,
          f"{w1.get('landed_included')}")
    check("A2: wac_landed > 0", float(w1.get("wac_landed", 0)) > 0, f"wac_landed={w1.get('wac_landed')}")
    check("A3: wac == wac_base + wac_landed",
          abs(float(w1["wac"]) - (float(w1["wac_base"]) + float(w1["wac_landed"]))) < 0.5,
          f"wac={w1['wac']} base={w1['wac_base']} landed={w1['wac_landed']}")
    check("A4: WAC naik dibanding sebelum landed", float(w1["wac"]) > base_wac + 0.01,
          f"before={base_wac} after={w1['wac']}")

    # B) _avg_unit_cost (dipakai return/regrade/COGS-reversal) = WAC landed-inclusive
    avg = await gl_service._avg_unit_cost(pid, eid)
    check("B: gl_service._avg_unit_cost == WAC landed-inclusive", abs(avg - float(w1["wac"])) < 0.5,
          f"avg={avg} wac={w1['wac']}")

    # C) Nilai write-off (qty × unit_cost) memakai unit_cost landed-inclusive > basis harga dasar
    r = await db.inventory_rolls.find_one({"id": roll_ids[0]}, {"_id": 0})
    ln = float(r.get("length_remaining", 0) or 0)
    uc = float(r.get("unit_cost", 0) or 0)
    b = float(r.get("base_unit_cost", 0) or 0)
    wo_amount = round(ln * uc, 2)          # sama dgn release_quarantine: qty_wo * unit_cost
    base_amount = round(ln * b, 2)
    check("C1: unit_cost roll = base + landed (landed masuk ke HPP roll)", uc > b + 0.001,
          f"unit_cost={uc} base={b}")
    check("C2: nilai write-off landed-inclusive > nilai berbasis harga dasar",
          wo_amount > base_amount + 0.01, f"wo={wo_amount} base_only={base_amount}")
    lct = float(r.get("landed_cost_total", 0) or 0)
    li = float(r.get("length_initial", 0) or 0)
    check("C3: landed_cost_total roll konsisten (~ (unit_cost-base) × length_initial)",
          abs(lct - round((uc - b) * li, 2)) < max(1.0, 0.02 * lct), f"lct={lct} calc={round((uc-b)*li,2)}")

    # D) Basis audit tersedia di data roll
    check("D: field audit basis ada (base_unit_cost, unit_cost, landed_cost_total, landed_cost_refs)",
          all(k in r for k in ("base_unit_cost", "unit_cost", "landed_cost_total", "landed_cost_refs")),
          f"keys={[k for k in ('base_unit_cost','unit_cost','landed_cost_total','landed_cost_refs') if k in r]}")

    print(f"\n=== HASIL R5.5: PASS={PASS} FAIL={FAIL} ===")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(1 if FAIL else 0)
