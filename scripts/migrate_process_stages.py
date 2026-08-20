#!/usr/bin/env python3
"""FASE T — MIGRASI MASTER TAHAPAN PROSES (`process_stages`) + backfill `steps[].stage_code`.

KENAPA ADA SKRIP INI (dan bukan hanya seed data demo)
=====================================================
`seed_realistic.py` melayani basis data DEMO yang dihapus-ulang. Basis data yang
sudah dipakai tidak boleh dihapus, tetapi tetap harus:
  1. punya 10 baris master tahapan (peta rencana §7 FASE T titik T.A) supaya pemilik
     bisa menambah/mengubah tahap dari layar — bukan menunggu programmer;
  2. punya `steps[].stage_code` pada SPK yang lahir SEBELUM FASE T, supaya papan &
     penyaring tahap tidak melihat langkah "tanpa tahap".

DUA JAMINAN YANG DIPEGANG SKRIP INI
-----------------------------------
* **Idempotent** — dijalankan dua kali hasilnya sama (upsert per `code` pada lapisan
  global). `--dry-run` melaporkan HASIL SUNGGUHAN yang akan terjadi, bukan perkiraan.
* **Angka SPK lama TIDAK bergeser.** Backfill hanya MENAMBAH field turunan
  (`stage_code`, `stage_label`, `changes_stage`, `material_flow`, …). Ia TIDAK
  menyentuh `estimate`, `expected_output_qty`, `tariff*`, `material_value`,
  `output_value`, atau `status`. Itu syarat regresi rencana §7 FASE T ("identik
  byte-per-byte") — dan alasannya nyata: menghitung ulang estimasi lama berarti
  mengubah HPP dokumen yang jurnalnya sudah diposting.

Pemakaian:
    python scripts/migrate_process_stages.py --dry-run
    python scripts/migrate_process_stages.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; B = "\033[1m"; X = "\033[0m"

import domain_registry as dr  # noqa: E402

# SATU daftar, dua pintu masuk (seed data demo & migrasi basis data lama):
# nilainya diambil LANGSUNG dari benih registry supaya tidak mungkin bercabang.
# Kalau daftar ini disalin, cabangnya akan hidup diam-diam — kelas bug yang sama
# dengan `PROCESS_LABELS` hardcode di frontend yang FASE T ini justru menutup.
SEED_STAGES: List[Dict[str, Any]] = [dict(v) for v in dr.enum_items("process_stage")]

MASTER_FIELDS = ("code", "name", "kind", "applies_to_lines", "seq", "active", "notes",
                 "needs_vendor", "process_type", "target_use",
                 "changes_stage", "from_stage", "to_stage", "tariff_basis_default",
                 "material_flow", "material_flow_default")


def _row(seed: Dict[str, Any]) -> Dict[str, Any]:
    code = str(seed.get("code") or seed.get("value") or "").strip().lower()
    out = {k: seed.get(k) for k in MASTER_FIELDS if k in seed}
    out["code"] = code
    out["name"] = seed.get("name") or seed.get("label") or code
    out.setdefault("applies_to_lines", [])
    out.setdefault("active", True)
    out.setdefault("notes", seed.get("description", "") or "")
    return out


async def main() -> int:
    dry = "--dry-run" in sys.argv
    from motor.motor_asyncio import AsyncIOMotorClient
    from core_utils import new_id, now_iso

    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        print(f"{R}MONGO_URL tidak ada — migrasi dibatalkan.{X}")
        return 2
    db = AsyncIOMotorClient(mongo_url)[os.environ.get("DB_NAME", "test_database")]

    print(f"{C}{B}FASE T — MIGRASI TAHAPAN PROSES{X}"
          + (f"  {Y}[DRY-RUN — tidak ada yang ditulis]{X}" if dry else ""))

    # ── 1. Master `process_stages` (lapisan GLOBAL `entity_id="all"`) ─────────
    created, updated, unchanged = [], [], []
    for seed in SEED_STAGES:
        row = _row(seed)
        code = row["code"]
        existing = await db.process_stages.find_one({"code": code, "entity_id": "all"},
                                                    {"_id": 0})
        if not existing:
            created.append(code)
            if not dry:
                await db.process_stages.insert_one({
                    **row, "id": new_id("pstg"), "entity_id": "all",
                    "created_by": "migrate_process_stages", "created_at": now_iso(),
                    "updated_at": now_iso()})
            continue
        # Field yang HILANG diisi; field yang sudah ada TIDAK ditimpa — baris yang
        # sudah disesuaikan pemilik (mis. tarif bawaan sendiri) harus tetap miliknya.
        # PENTING: `[]` pada `applies_to_lines` adalah NILAI BERMAKNA ("berlaku untuk
        # semua lini", aturan yang sama dengan `allowed_line_codes` FASE L) — bukan
        # "belum diisi". Kalau ia dianggap hilang, jalankan-kedua akan selalu melaporkan
        # "dilengkapi" dan laporan idempotensi berhenti bisa dipercaya.
        missing = (None, "")
        patch = {k: v for k, v in row.items()
                 if k != "code" and existing.get(k) in missing and v not in missing}
        if patch:
            updated.append(f"{code}({','.join(sorted(patch))})")
            if not dry:
                await db.process_stages.update_one(
                    {"code": code, "entity_id": "all"},
                    {"$set": {**patch, "updated_at": now_iso()}})
        else:
            unchanged.append(code)
    print(f"  master: {G}{len(created)} dibuat{X} · {Y}{len(updated)} dilengkapi{X} · "
          f"{len(unchanged)} sudah sesuai")
    if created:
        print(f"    + {', '.join(created)}")
    if updated:
        print(f"    ~ {', '.join(updated)}")

    # ── 2. Backfill `steps[].stage_code` pada SPK lama ───────────────────────
    # Peta process_type → tahap dibaca dari master yang BARU SAJA dipastikan ada,
    # bukan dari tabel terpisah. `pre_treatment` dipilah lewat `target_use`.
    rows = await db.process_stages.find({"entity_id": "all"}, {"_id": 0}).to_list(1000)
    if not rows:
        rows = [_row(s) for s in SEED_STAGES]     # dry-run pada DB kosong
    by_pt: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        pt = str(r.get("process_type") or "").strip().lower()
        if pt:
            by_pt.setdefault(pt, []).append(r)

    def pick(pt: str, target_use: str) -> Dict[str, Any]:
        cand = by_pt.get(str(pt or "").strip().lower(), [])
        tu = str(target_use or "").strip().lower()
        if tu:
            exact = [r for r in cand if str(r.get("target_use") or "").lower() == tu]
            if exact:
                cand = exact
        cand = sorted(cand, key=lambda r: (int(r.get("seq") or 0), r.get("code") or ""))
        return cand[0] if cand else {}

    touched, skipped, orphan = 0, 0, []
    async for o in db.makloon_orders.find({}, {"_id": 0, "id": 1, "mko_number": 1, "steps": 1}):
        changed = False
        steps = o.get("steps") or []
        for s in steps:
            if s.get("stage_code"):
                skipped += 1
                continue
            st = pick(s.get("process_type") or "", s.get("target_use") or "")
            if not st:
                orphan.append(f"{o.get('mko_number')}#{s.get('seq')}"
                              f"({s.get('process_type') or '-'})")
                continue
            s["stage_code"] = st.get("code") or ""
            s["stage_label"] = st.get("name") or ""
            s["stage_kind"] = st.get("kind") or "makloon"
            s["stage_seq"] = st.get("seq") or 0
            s["stage_from_stage"] = st.get("from_stage") or ""
            s["stage_to_stage"] = st.get("to_stage") or ""
            s["stage_source"] = "migrate_process_stages (dari process_type)"
            s["changes_stage"] = st.get("changes_stage") is not False
            s["needs_vendor"] = bool(st.get("needs_vendor"))
            # Langkah lama SELALU memindahkan kain — itu satu-satunya cara yang ada
            # sebelum FASE T. Menebak `service_only` di sini akan mengubah arti
            # dokumen yang jurnalnya sudah diposting.
            flow = str(st.get("material_flow") or "moves").lower()
            s["material_flow"] = "moves" if flow in ("moves", "either", "") else flow
            s["material_flow_source"] = "migrasi FASE T (langkah lama = kain bergerak)"
            s.setdefault("absorbed_service_value", 0.0)
            s.setdefault("absorbed_service_steps", [])
            changed = True
        if changed:
            touched += 1
            if not dry:
                await db.makloon_orders.update_one(
                    {"id": o["id"]},
                    {"$set": {"steps": steps, "service_absorption_pending": 0.0}})
    print(f"  SPK: {G}{touched} dokumen di-backfill{X} · {skipped} langkah sudah ber-tahap")
    if orphan:
        print(f"  {Y}{len(orphan)} langkah tidak menemukan tahap yang cocok "
              f"(process_type tak ada di master): {', '.join(orphan[:8])}{X}")
        print(f"  {Y}→ tambahkan tahap untuk jenis proses itu di master, lalu jalankan "
              f"ulang skrip ini.{X}")

    print(f"{G}{B}SELESAI{X}" + (f" {Y}(dry-run — tidak ada yang ditulis){X}" if dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
