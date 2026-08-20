#!/usr/bin/env python3
"""FASE D — Migrasi IDEMPOTEN order makloon lama → struktur rantai proses.

Rujukan: `docs/KN_24_PLAN_FASE_D_MAKLOON.md` · KN_18 §5.2 (perubahan `makloon_orders`).

Yang dilakukan (aman & idempoten — jalankan berkali-kali, `changed=0` pada run kedua):
  1. `steps[]` lama mendapat field Fase D yang hilang (additive, tanpa mengarang angka):
     `shrinkage_pct` (= waste_pct lama), `shrinkage_source`, `tolerance_pct`
     (kebijakan global saat migrasi), `contract_id`/`contract_number` kosong,
     `tariff_basis` = "lumpsum" bila tarif diketik manual + `tariff_plan` jejak minimal,
     `claim` kosong, `input_lot_ids`/`output_lot_ids` diturunkan dari `lots[]`,
     `variance` dihitung dari data yang ADA (estimasi vs aktual) untuk langkah `received`.
  2. `claim_summary` order + `costing.steps[]` (HPP berjenjang) dibentuk ulang dari data.
  3. Kebijakan makloon (`system_settings` scope `makloon`) dipastikan ada.

TIDAK membuat kontrak palsu: order lama tetap tanpa `contract_id` (jejak jujur).

Jalankan: python backend/scripts/migrate_fase_d_contracts.py [--dry-run]
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from db import db                     # noqa: E402
from core_utils import now_iso, parse_decimal   # noqa: E402
from services import contract_service as cs     # noqa: E402
from services import makloon_calc_service as mcalc  # noqa: E402
from services import makloon_claim_service as mclaim  # noqa: E402
from services.makloon_order_service import _recompute_status_and_costing  # noqa: E402

G, Y, C, R, X, B = "\033[92m", "\033[93m", "\033[96m", "\033[91m", "\033[0m", "\033[1m"


async def migrate(dry_run: bool = False) -> dict:
    stats = {"orders": 0, "steps_backfilled": 0, "orders_updated": 0,
             "claims_initialized": 0, "variance_computed": 0, "policy_created": 0}
    if not dry_run:
        created = await cs.ensure_defaults(actor="migrate_fase_d")
        stats["policy_created"] = 1 if created else 0
    settings = await cs.get_settings()
    default_tol = parse_decimal(settings.get("variance_tolerance_pct"))

    orders = await db.makloon_orders.find({}, {"_id": 0}).to_list(20000)
    for order in orders:
        stats["orders"] += 1
        changed = False
        for s in order.get("steps", []):
            if "shrinkage_pct" not in s:
                s["shrinkage_pct"] = parse_decimal(s.get("waste_pct") or 0)
                s["shrinkage_source"] = "data lama (waste_pct langkah)"
                changed = True
                stats["steps_backfilled"] += 1
            if s.get("tolerance_pct") in (None, ""):
                s["tolerance_pct"] = default_tol
                changed = True
            for key, val in (("contract_id", ""), ("contract_number", ""),
                             ("yield_override_reason", ""), ("output_lot_id", "")):
                if key not in s:
                    s[key] = val
                    changed = True
            if not s.get("tariff_basis"):
                s["tariff_basis"] = "lumpsum"
                s["tariff_rate"] = parse_decimal(s.get("tariff") or 0, 2)
                s["tariff_plan"] = {
                    "basis": "lumpsum", "rate": parse_decimal(s.get("tariff") or 0, 2),
                    "basis_qty": 1.0, "basis_uom": "lumpsum",
                    "amount": parse_decimal(s.get("tariff") or 0, 2),
                    "source": "migration", "explain": ["Ongkos jasa diketik manual (data lama)"],
                }
                changed = True
            if "input_lot_ids" not in s or "output_lot_ids" not in s:
                out_ids = sorted({l.get("lot_id") for l in (s.get("lots") or []) if l.get("lot_id")})
                s.setdefault("input_lot_ids", [])
                s["output_lot_ids"] = out_ids
                if out_ids and not s.get("output_lot_id"):
                    s["output_lot_id"] = out_ids[0]
                changed = True
            if s.get("status") == "received" and not s.get("variance"):
                var = mcalc.evaluate_variance(
                    expected_qty=s.get("expected_output_qty"),
                    actual_qty=s.get("actual_output_qty"),
                    tolerance_pct=s.get("tolerance_pct") or default_tol,
                    unit=s.get("output_unit") or "",
                    unit_value=s.get("output_unit_cost") or 0)
                s["variance"] = var
                stats["variance_computed"] += 1
                changed = True
            if not s.get("claim"):
                # Data lama TIDAK otomatis membuka klaim (jangan menagih retroaktif);
                # hanya struktur kosong + hasil evaluasi agar layar konsisten.
                s["claim"] = mclaim.build_claim_from_variance(s.get("variance") or {},
                                                              auto_open=False)
                stats["claims_initialized"] += 1
                changed = True
        if "claim_summary" not in order or not order.get("costing", {}).get("steps"):
            changed = True
        if changed:
            _recompute_status_and_costing(order)
            order["claim_summary"] = mclaim.summarize(order)
            order["updated_at"] = now_iso()
            stats["orders_updated"] += 1
            if not dry_run:
                await db.makloon_orders.replace_one({"id": order["id"]}, order)
    stats["changed"] = stats["orders_updated"] + stats["policy_created"]
    return stats


async def main() -> int:
    ap = argparse.ArgumentParser(description="Migrasi idempoten Fase D (makloon rantai proses)")
    ap.add_argument("--dry-run", action="store_true", help="hanya laporkan, tidak menulis")
    args = ap.parse_args()
    print(f"{C}{B}\n=== MIGRASI FASE D — MAKLOON RANTAI PROSES "
          f"{'(DRY-RUN)' if args.dry_run else ''} ==={X}")
    st = await migrate(dry_run=args.dry_run)
    print(f"  order diperiksa           : {st['orders']}")
    print(f"  langkah di-backfill       : {st['steps_backfilled']}")
    print(f"  selisih dihitung ulang    : {st['variance_computed']}")
    print(f"  struktur klaim disiapkan  : {st['claims_initialized']}")
    print(f"  order diperbarui          : {st['orders_updated']}")
    print(f"  kebijakan makloon dibuat  : {st['policy_created']}")
    if st["changed"] == 0:
        print(f"{G}  changed=0 — idempoten (aman dijalankan ulang).{X}")
    else:
        print(f"{Y}  changed={st['changed']} — jalankan ulang untuk membuktikan idempotensi.{X}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
