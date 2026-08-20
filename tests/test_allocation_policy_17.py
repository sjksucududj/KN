"""Sub-fase 1.7 — Allocation Policy R1/R2/R3/R4 Configurable (POC self-test).

Menguji planner `_build_allocation_plan` (READ-ONLY) terhadap skenario lot:
  R1  single-lot preference (1 lot cukup)
  R2  mixed-lot exception (qty > lot tunggal terbesar, total cukup)
  R3  lot_selection: fefo (lot tertua) vs smallest_fit
  R4  strict_single (tidak boleh campur → parsial dari 1 lot)
      allow_mixed (campur tanpa konfirmasi)
  + allocation_explanation hadir (CLARITY)

Tidak menyentuh DB — murni logika planner pada list roll sintetis.
"""
import sys
sys.path.insert(0, "/app/backend")

from services.roll_service import _build_allocation_plan, DEFAULT_ALLOCATION_POLICY  # noqa: E402

WAREHOUSES = {
    "wh_bdg": {"id": "wh_bdg", "name": "Gudang Bandung", "city": "Bandung"},
    "wh_jkt": {"id": "wh_jkt", "name": "Gudang Jakarta", "city": "Jakarta"},
}


def roll(rid, lot, length, wh="wh_bdg", created="2026-01-01", earmark=None):
    return {"id": rid, "lot": lot, "length_remaining": length, "warehouse_id": wh,
            "created_at": created, "roll_no": rid, "earmarked_for": earmark}


def pol(**over):
    return {**DEFAULT_ALLOCATION_POLICY, **over}


def _assert(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, ("" if cond else f":: {detail}"))
    return cond


def main():
    results = []

    # R1 — satu lot cukup (L1=50, L2=30, minta 40 → harus single dari L1)
    rolls = [roll("r1", "L1", 50, created="2026-01-02"), roll("r2", "L2", 30, created="2026-01-01")]
    p = _build_allocation_plan(rolls, 40, "Bandung", WAREHOUSES, pol())
    results.append(_assert("R1 single-lot mode", p["lot_mode"] == "single", p))
    results.append(_assert("R1 reserved==40", abs(p["reserved_qty"] - 40) < 0.01, p))
    results.append(_assert("R1 no confirmation", p["requires_confirmation"] is False, p))
    results.append(_assert("R1 explanation present", bool(p["explanation"]), p))

    # R3 fefo — dua lot cukup (L1 oldest=2026-01-01=60, L2=2026-02-01=60), minta 50 → pilih L1 (tertua)
    rolls = [roll("a", "L1", 60, created="2026-01-01"), roll("b", "L2", 60, created="2026-02-01")]
    p = _build_allocation_plan(rolls, 50, "Bandung", WAREHOUSES, pol(lot_selection="fefo"))
    results.append(_assert("R3 fefo picks oldest lot L1", p["lots_used"] == ["L1"], p))

    # R3 smallest_fit — L1=100(old), L2=60(new), minta 50 → smallest fit = L2
    rolls = [roll("a", "L1", 100, created="2026-01-01"), roll("b", "L2", 60, created="2026-02-01")]
    p = _build_allocation_plan(rolls, 50, "Bandung", WAREHOUSES, pol(lot_selection="smallest_fit"))
    results.append(_assert("R3 smallest_fit picks L2", p["lots_used"] == ["L2"], p))

    # R2 — mixed exception (L1=30, L2=30, minta 50 → tak ada lot tunggal cukup, total 60 cukup → mixed)
    rolls = [roll("a", "L1", 30, created="2026-01-01"), roll("b", "L2", 30, created="2026-02-01")]
    p = _build_allocation_plan(rolls, 50, "Bandung", WAREHOUSES, pol(lot_mode="prefer_single"))
    results.append(_assert("R2 mixed lot mode", p["lot_mode"] == "mixed", p))
    results.append(_assert("R2 prefer_single requires confirmation", p["requires_confirmation"] is True, p))
    results.append(_assert("R2 reserved==50", abs(p["reserved_qty"] - 50) < 0.01, p))
    results.append(_assert("R2 two lots used (FEFO order)", p["lots_used"] == ["L1", "L2"], p))

    # allow_mixed — sama tapi tanpa konfirmasi
    p = _build_allocation_plan(rolls, 50, "Bandung", WAREHOUSES, pol(lot_mode="allow_mixed"))
    results.append(_assert("allow_mixed no confirmation", p["requires_confirmation"] is False, p))
    results.append(_assert("allow_mixed still mixed", p["lot_mode"] == "mixed", p))

    # R4 strict_single — L1=30, L2=30, minta 50 → hanya 1 lot (30), sisa 20 backorder, single, no confirm
    p = _build_allocation_plan(rolls, 50, "Bandung", WAREHOUSES, pol(lot_mode="strict_single"))
    results.append(_assert("strict_single single mode", p["lot_mode"] == "single", p))
    results.append(_assert("strict_single reserved==30", abs(p["reserved_qty"] - 30) < 0.01, p))
    results.append(_assert("strict_single backorder==20", abs(p["backorder_qty"] - 20) < 0.01, p))
    results.append(_assert("strict_single no confirmation", p["requires_confirmation"] is False, p))

    # Partial — total < Q (L1=30 only), minta 50 → reserved 30, backorder 20
    rolls = [roll("a", "L1", 30, created="2026-01-01")]
    p = _build_allocation_plan(rolls, 50, "Bandung", WAREHOUSES, pol())
    results.append(_assert("partial reserved==30", abs(p["reserved_qty"] - 30) < 0.01, p))
    results.append(_assert("partial backorder==20", abs(p["backorder_qty"] - 20) < 0.01, p))

    # Earmark awareness (planner tetap pakai rolls yang diberikan; filter earmark di _available_rolls_for_order)
    # location_pref fewest_splits — pilih roll besar dulu (L1 punya 1x100 vs 2x... ) — verifikasi urutan
    rolls = [roll("small", "L1", 10, created="2026-01-01"), roll("big", "L1", 100, created="2026-01-02")]
    p = _build_allocation_plan(rolls, 50, "Bandung", WAREHOUSES, pol(location_pref="fewest_splits"))
    first_id = p["ordered_rolls"][0]["id"] if p["ordered_rolls"] else None
    results.append(_assert("fewest_splits picks big roll first", first_id == "big", first_id))

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n=== ALLOCATION POLICY 1.7 — {passed}/{total} PASS ===")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
