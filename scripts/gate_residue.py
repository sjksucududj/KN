#!/usr/bin/env python3
"""
gate_residue.py — GATE ANTI-RESIDU  (INV-GATE-01)
=================================================
Membuktikan bahwa MENJALANKAN GATE tidak mengubah data.

LATAR BELAKANG (kelas bug nyata, terukur 2026-07-26):
  Guardrail runtime memanggil API sungguhan sehingga mengubah data, dan sebelum
  perbaikan tak satu pun punya cleanup. Diukur dari seed bersih, SATU kali
  `gate.sh` meninggalkan:

    · sales_orders     : SO-0006 'reserved/Reserved' -> 'cancelled/Cancelled'  (permanen)
    · inventory_balances:
        prod_songket_palembang/wh_jakarta  available 135->145 · reserved 20->10
        prod_lurik_classic/wh_bandung      available 580->620 · reserved 40->0
    · inventory_movements : 38 -> 40   (+2 release_reservation)
    · audit_logs          : 6  -> 16   (+10)

  Tidak ada satu pun dari 183 invarian yang menangkapnya (semuanya memeriksa
  konsistensi INTERNAL, bukan "apakah gate itu sendiri merusak data").
  Skrip ini menutup celah itu secara permanen.

CARA PAKAI (dipakai otomatis oleh scripts/gate.sh):
    python scripts/gate_residue.py --save     # sebelum gate runtime
    python scripts/gate_residue.py --check    # sesudah gate runtime  (exit 1 bila ada residu)

Sidik jari disimpan di /tmp/kn_gate_residue.json (bukan di repo).
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

G, Y, R, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[1m", "\033[0m"
SNAP = Path(os.environ.get("KN_RESIDUE_FILE", "/tmp/kn_gate_residue.json"))

# Koleksi yang HARUS identik sebelum & sesudah gate runtime.
# audit_logs & notifications SENGAJA disertakan: residu di situ pun berarti gate
# meninggalkan jejak yang tak dibersihkan.
WATCH = [
    "sales_orders", "purchase_orders", "products", "customers",
    "inventory_balances", "inventory_movements", "inventory_rolls",
    "wms_tasks", "audit_logs", "notifications", "shipments",
    "approval_requests", "invoices", "vendor_bills", "ar_receipts",
    # Antar-PT (ditambahkan setelah KN-G6-ICA-CLOBBER): POC E-7d mengubah
    # Permintaan Internal menjadi transaksi antar-PT dan TIDAK membersihkannya,
    # jadi setiap `gate --full` menambah satu dokumen KANDA/IC-##### permanen.
    # Residu itu tak pernah terlihat karena koleksi antar-PT belum dipantau —
    # dan justru residu itulah yang memicu tabrakan saldo dua arah.
    # Catatan sengaja: `interco_accounts` TIDAK dipantau di sini karena ia tabel
    # TURUNAN (lahir sendiri begitu sepasang PT mulai berhubungan, mis. lewat
    # pinjaman antar-PT yang memang append-only). Kebenarannya dijaga INV-IC-04
    # yang kini memeriksa KELENGKAPAN per arah dagang, bukan oleh gate residu.
    "interco_transactions", "interco_settlements", "interco_returns",
    # RETUR (ditambahkan FASE E-9): rantai retur menyentuh tiga koleksi dokumen +
    # lot & nota kredit. POC E-9 membersihkan miliknya sendiri, tetapi tanpa
    # dipantau di sini residu POC lain di jalur retur tetap tak terlihat — dan
    # justru koleksi inilah yang memegang nilai barang & uang balik.
    "sales_returns", "purchase_returns", "credit_notes",
    "inventory_lots", "supplier_contracts",
]
QTY_SUFFIX = "_qty"
# Jejak APPEND-ONLY: POC fase memang menjalankan alur nyata sehingga wajar
# meninggalkan catatan audit/notifikasi. Menghapusnya justru merusak jejak.
# Dengan `--ignore-trails`, pemeriksaan difokuskan ke KEBENARAN DATA
# (dokumen transaksi, stok, status SO) — bukan ke banyaknya jejak.
TRAILS = ["audit_logs", "notifications"]


async def fingerprint():
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "test_database")]
    fp = {"counts": {}, "balances": {}, "so_status": {}}
    for c in WATCH:
        try:
            fp["counts"][c] = await db[c].count_documents({})
        except Exception:
            fp["counts"][c] = -1
    # nilai kuantitas stok (bukan hanya jumlah dokumen — perubahan nilai lebih berbahaya)
    async for b in db.inventory_balances.find({}, {"_id": 0}):
        key = f'{b.get("product_id")}|{b.get("warehouse_id")}'
        fp["balances"][key] = {k: v for k, v in b.items() if k.endswith(QTY_SUFFIX)}
    # status/stage SO (state-machine gate pernah membatalkan order seed)
    async for s in db.sales_orders.find({}, {"_id": 0, "id": 1, "number": 1,
                                             "status": 1, "stage": 1}):
        fp["so_status"][s.get("id")] = [s.get("number"), s.get("status"), s.get("stage")]
    return fp


def _diff(before, after, ignore_trails=False):
    problems = []
    for c, n in before["counts"].items():
        if ignore_trails and c in TRAILS:
            continue
        m = after["counts"].get(c, -1)
        if n != m:
            problems.append(f"koleksi '{c}': {n} -> {m} dok  (selisih {m - n:+d})")
    for k, v in before["balances"].items():
        w = after["balances"].get(k)
        if w is None:
            problems.append(f"balance '{k}' HILANG")
            continue
        for field in set(v) | set(w):
            if v.get(field) != w.get(field):
                problems.append(f"balance '{k}'.{field}: {v.get(field)} -> {w.get(field)}")
    for k, v in before["so_status"].items():
        w = after["so_status"].get(k)
        if w is None:
            problems.append(f"sales_order '{k}' HILANG")
        elif v[1:] != w[1:]:
            problems.append(f"sales_order {v[0]}: {tuple(v[1:])} -> {tuple(w[1:])}")
    return problems


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--ignore-trails", action="store_true",
                    help="abaikan koleksi jejak append-only (audit_logs, notifications)")
    args = ap.parse_args()

    fp = await fingerprint()

    if args.save:
        SNAP.write_text(json.dumps(fp))
        tot = sum(v for v in fp["counts"].values() if v > 0)
        print(f"{G}[residue]{X} sidik jari disimpan "
              f"({tot} dok · {len(fp['balances'])} balance · {len(fp['so_status'])} SO)")
        return 0

    if not args.check:
        ap.print_help()
        return 0

    if not SNAP.exists():
        print(f"{Y}[residue] tak ada sidik jari awal — SKIP "
              f"(jalankan --save sebelum gate runtime).{X}")
        return 0

    before = json.loads(SNAP.read_text())
    problems = _diff(before, fp, ignore_trails=args.ignore_trails)
    scope = " (jejak append-only diabaikan)" if args.ignore_trails else ""
    print(f"\n{B}INV-GATE-01 — apakah menjalankan gate merusak data?{scope}{X}")
    if not problems:
        print(f"  {G}[PASS]{X} nol residu: {len(WATCH)} koleksi, "
              f"{len(fp['balances'])} balance, {len(fp['so_status'])} SO — "
              f"semuanya identik sebelum & sesudah gate.")
        return 0
    print(f"  {R}[FAIL]{X} gate MENINGGALKAN RESIDU ({len(problems)} perubahan):")
    for p in problems[:25]:
        print(f"    {R}✗{X} {p}")
    if len(problems) > 25:
        print(f"    ... dan {len(problems) - 25} perubahan lain")
    print(f"  {Y}→ Guardrail runtime wajib memulihkan data: pakai "
          f"`run_with_restore(main)` / `DbSnapshot` dari scripts/guardrails/_common.py.{X}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
