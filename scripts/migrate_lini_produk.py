#!/usr/bin/env python3
"""migrate_lini_produk.py — FASE L: seed master **Lini Produk** + isi `line_code` data lama.

KENAPA BERKAS INI ADA
=====================
Data lama tidak pernah menyimpan "lini" (pembagian kerja MD: woven / knit /
printing). Begitu 12 layar mendapat penyaring lini dan akun bisa dipagari per
lini, dokumen tanpa `line_code` akan:
  * tidak pernah muncul di chip lini mana pun (pemilik menyebutnya "data hilang"), dan
  * membuat papan PO per lini (FASE P) kosong selamanya.

Jadi migrasi ini menebak lini untuk data lama — dan **mengakui bahwa itu tebakan**:
setiap produk dicetak beserta ALASAN tebakannya, plus penanda `PERIKSA` untuk
tebakan yang lemah. Laporannya ditulis ke
`docs/LAPORAN_MIGRASI_LINI_PRODUK.md` supaya pemilik bisa mengoreksinya **lewat
layar** (Master Produk → kolom Lini), bukan lewat skrip. Fase L baru boleh ditutup
setelah daftar itu ditinjau (RENCANA_EKSEKUSI_MD_ERP.md §L.E butir 2).

ATURAN TEBAKAN (persis rencana §L.E, dengan satu penajaman yang diukur)
----------------------------------------------------------------------
1. `fabric_type == "knit"`                                  → **knit**
2. `design_id` terisi                                       → **printing**
3. `motif` terisi DAN motif itu bukan penanda "tanpa motif"  → **printing**
   Penajaman: `Polos`, `-`, `None`, `Plain`, kosong **tidak** dihitung sebagai
   motif. Rencana menulis "motif tidak kosong", tetapi data demo menyimpan
   `motif="Polos"` (= polos/tanpa motif) pada 1 produk dan `motif="None"` /
   `"-"` pada 5 produk. Menghitungnya sebagai printing berarti mengirim kain
   polos ke papan printing — salah yang bisa dilihat mata, jadi dikoreksi di
   sini dan dicatat di laporan (bukan diam-diam).
4. sisanya                                                   → **woven**

`PERIKSA` ditandai untuk kain yang motifnya biasanya **ditenun**, bukan dicetak
(Tenun · Songket · Ulos · Lurik · Endek · Batik tulis · Kombinasi): mesin tidak
bisa membedakan motif tenun dari motif cetak, dan justru di situ tebakan paling
sering salah.

SIFAT
-----
* **Idempotent**: baris master di-*upsert* per `code`, produk yang SUDAH punya
  `line_code` tidak pernah ditimpa (koreksi manual pemilik menang atas mesin).
* `--dry-run` mencetak rencana tanpa menulis; dijalankan dua kali harus identik.
* Melaporkan jumlah baris SEBELUM & SESUDAH untuk setiap koleksi yang disentuh
  (aturan "setiap migrasi disertai hitung baris", plan.md §6).

Pakai:
    python scripts/migrate_lini_produk.py --dry-run
    python scripts/migrate_lini_produk.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv                                    # noqa: E402
load_dotenv(ROOT / "backend" / ".env")

from motor.motor_asyncio import AsyncIOMotorClient                # noqa: E402

GLOBAL_ID = "all"
REPORT_PATH = ROOT / "docs" / "LAPORAN_MIGRASI_LINI_PRODUK.md"

# ── Baris master (global). Sama dengan benih `domain_registry.PRODUCT_LINES`
#    supaya tidak ada dua daftar; benih hanya cadangan bila koleksi kosong. ──
SEED_LINES: List[Dict[str, Any]] = [
    {"code": "woven", "name": "Woven (Tenun)", "sort": 1, "active": True,
     "fabric_type_required": "woven", "measure_unit_default": "yard",
     "stage_sequence": ["yarn", "tenun", "celup", "inspect"],
     "sample_types_default": ["labdip"],
     "notes": "Kain tenun polos/bermotif tenun. Satuan kendali meter (fabric_type woven)."},
    {"code": "knit", "name": "Knit (Rajut)", "sort": 2, "active": True,
     "fabric_type_required": "knit", "measure_unit_default": "kg",
     "stage_sequence": ["yarn", "rajut", "celup", "inspect"],
     "sample_types_default": ["labdip"],
     "notes": "Kain rajut. Satuan kendali kg (fabric_type knit)."},
    {"code": "printing", "name": "Printing", "sort": 3, "active": True,
     # SENGAJA kosong: kain print bisa woven maupun knit (INV-LINE-02 tidak mengikat).
     "fabric_type_required": "", "measure_unit_default": "yard",
     "stage_sequence": ["proofing", "pfp", "screen", "printing", "inspect"],
     "sample_types_default": ["proofing", "labdip"],
     "notes": "Kain cetak (screen/rotary/digital). Bisa woven maupun knit."},
]

NO_MOTIF = {"", "-", "none", "polos", "plain", "n/a", "null"}
REVIEW_CATEGORIES = {"tenun", "songket", "ulos", "lurik", "endek", "kombinasi", "batik"}

def guess_line(prod: Dict[str, Any]) -> Tuple[str, str, bool]:
    """→ (kode lini, alasan yang bisa dibaca manusia, perlu ditinjau?)."""
    fabric = str(prod.get("fabric_type") or "").strip().lower()
    motif = str(prod.get("motif") or "").strip()
    design = str(prod.get("design_id") or "").strip()
    category = str(prod.get("category") or "").strip().lower()
    if fabric == "knit":
        return "knit", "jenis kain knit (fabric_type=knit)", False
    if design:
        return "printing", f"punya kode desain (design_id={design})", False
    if motif.lower() not in NO_MOTIF:
        review = any(cat in category for cat in REVIEW_CATEGORIES)
        alasan = f"motif terisi (“{motif}”)"
        if review:
            alasan += f" — tetapi kategori “{prod.get('category')}” biasanya motif DITENUN, bukan dicetak"
        return "printing", alasan, review
    return "woven", (f"tanpa motif (motif=“{motif or '-'}”) & tanpa desain" if not fabric
                     else f"kain {fabric} tanpa motif & tanpa desain"), False


async def seed_master(db, dry: bool) -> Tuple[int, int]:
    """Upsert 3 baris master GLOBAL. → (dibuat, diperbarui)."""
    created = updated = 0
    for i, row in enumerate(SEED_LINES):
        existing = await db.product_lines.find_one(
            {"code": row["code"], "entity_id": {"$in": [GLOBAL_ID, "", None]}}, {"_id": 0})
        if existing:
            # Hanya melengkapi field yang HILANG — nilai yang sudah disunting
            # pemilik (nama, urutan, satuan usulan) tidak boleh ditimpa mesin.
            patch = {k: v for k, v in row.items() if k not in existing}
            if patch and not dry:
                await db.product_lines.update_one({"id": existing["id"]}, {"$set": patch})
            updated += 1 if patch else 0
            continue
        doc = {"id": f"pline_{row['code']}", "entity_id": GLOBAL_ID, **row,
               "created_at": _now(), "updated_at": _now()}
        if not dry:
            await db.product_lines.insert_one(doc)
        created += 1
    return created, updated


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


async def fill_products(db, dry: bool) -> Tuple[List[Dict[str, Any]], Dict[str, int],
                                               Dict[str, str]]:
    """Isi `products.line_code` untuk produk yang belum bergolong lini.

    → (baris laporan, tally per lini, peta `product_id → lini` HASIL AKHIR).
    Peta terakhir dipakai `backfill_documents` supaya **`--dry-run` meramalkan
    angka yang sama** dengan jalannya yang sungguhan; tanpa itu dry-run selalu
    melaporkan "0 dokumen" (karena produknya memang belum ditulis) dan pemilik
    tidak bisa memakai dry-run untuk memutuskan apa pun.
    """
    rows: List[Dict[str, Any]] = []
    tally: Dict[str, int] = {}
    planned: Dict[str, str] = {}
    async for p in db.products.find({}, {"_id": 0}):
        current = str(p.get("line_code") or "").strip().lower()
        if current:
            rows.append({"sku": p.get("sku", ""), "name": p.get("name", ""),
                         "line": current, "reason": "sudah terisi — tidak diubah",
                         "review": False, "changed": False})
            tally[current] = tally.get(current, 0) + 1
            planned[p["id"]] = current
            continue
        line, reason, review = guess_line(p)
        if not dry:
            await db.products.update_one({"id": p["id"]},
                                         {"$set": {"line_code": line, "updated_at": _now()}})
        planned[p["id"]] = line
        rows.append({"sku": p.get("sku", ""), "name": p.get("name", ""), "line": line,
                     "reason": reason, "review": review, "changed": True})
        tally[line] = tally.get(line, 0) + 1
    return rows, tally, planned


async def backfill_documents(db, dry: bool,
                             prod_line: Dict[str, str]) -> List[Tuple[str, int, int]]:
    """Stempel dokumen lama lewat SATU PINTU `services/line_scope.backfill`.

    Rumusnya SENGAJA tidak ditulis di sini: `seed_realistic.py` memakai pintu yang
    sama, jadi basis data hasil seed dan hasil migrasi mustahil punya arti berbeda
    untuk `line_codes[]` (kalau dua rumus, gate INV-LINE-01 bisa hijau di satu
    basis data dan merah di yang lain — dan yang salah tidak akan kelihatan).

    Satu tebakan yang HANYA milik migrasi ditambahkan sesudahnya: sample lama
    ber-`sample_type="proofing"` diberi lini `printing`, karena proofing memang
    hanya ada di lini printing (lihat `sample_types_default` di master). Itu tebakan
    atas data lama, bukan aturan sistem — karena itu tidak ikut ke pintu bersama.
    """
    from services import line_scope as lines            # noqa: PLC0415 — butuh sys.path
    out = await lines.backfill(db, prod_line, dry=dry)
    extra = 0
    async for smp in db.md_samples.find({}, {"_id": 0, "id": 1, "line_code": 1,
                                             "sample_type": 1, "product_id": 1,
                                             "spec_id": 1}):
        if str(smp.get("line_code") or "").strip():
            continue
        if prod_line.get(smp.get("product_id")):
            continue
        if str(smp.get("sample_type") or "").lower() != "proofing":
            continue
        extra += 1
        if not dry:
            await db.md_samples.update_one({"id": smp["id"]},
                                           {"$set": {"line_code": "printing"}})
    if extra:
        out = [(c, t + extra if c == "md_samples" else t, n) for c, t, n in out]
    return out


async def normalize_users(db, dry: bool) -> int:
    """`allowed_line_codes` dibuat EKSPLISIT (`[]` = semua lini).

    Field yang absen dan field `[]` berarti sama bagi `line_scope`, tetapi
    membuatnya eksplisit membuat layar "Akun & Akses" bisa membedakan "belum
    pernah diatur" dari "sengaja semua lini" tanpa menebak.
    """
    q = {"allowed_line_codes": {"$exists": False}}
    n = await db.users.count_documents(q)
    if n and not dry:
        await db.users.update_many(q, {"$set": {"allowed_line_codes": []}})
    return n


def write_report(rows: List[Dict[str, Any]], tally: Dict[str, int],
                 docs: List[Tuple[str, int, int]], dry: bool) -> None:
    review = [r for r in rows if r["review"]]
    lines = [
        "# Laporan Migrasi Lini Produk (FASE L)",
        "",
        f"> Dibuat otomatis oleh `scripts/migrate_lini_produk.py`"
        f"{' (--dry-run — belum ada yang ditulis)' if dry else ''}.",
        "> Lini adalah **pembagian kerja MD**, bukan jenis kain. Data lama tidak pernah",
        "> menyimpannya, jadi baris di bawah adalah **tebakan mesin** yang WAJIB ditinjau",
        "> manusia. Koreksi dilakukan **lewat layar** Master Produk (kolom *Lini*) —",
        "> bukan dengan menjalankan skrip lagi (skrip tidak menimpa nilai yang sudah ada).",
        "",
        "## Ringkasan",
        "",
        "| Lini | Jumlah produk |",
        "|---|---|",
    ]
    for code in sorted(tally):
        lines.append(f"| `{code}` | {tally[code]} |")
    lines += [
        "",
        f"**Perlu ditinjau: {len(review)} produk** (motif yang biasanya DITENUN, bukan dicetak).",
        "",
        "## Perlu ditinjau lebih dulu",
        "",
        "| SKU | Nama | Lini usulan | Alasan |",
        "|---|---|---|---|",
    ]
    for r in review:
        lines.append(f"| `{r['sku']}` | {r['name']} | **{r['line']}** | {r['reason']} |")
    if not review:
        lines.append("| — | — | — | tidak ada |")
    lines += ["", "## Seluruh produk", "",
              "| SKU | Nama | Lini | Alasan | Diubah migrasi? |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| `{r['sku']}` | {r['name']} | {r['line']} | {r['reason']} | "
                     f"{'ya' if r['changed'] else 'tidak'} |")
    lines += ["", "## Dokumen yang ikut distempel", "",
              "| Koleksi | Dokumen disentuh | Total dokumen |", "|---|---|---|"]
    for coll, touched, total in docs:
        lines.append(f"| `{coll}` | {touched} | {total} |")
    lines += [
        "",
        "## Cara mengoreksi (untuk pemilik)",
        "",
        "1. Buka **Master Produk** (Admin → Produk).",
        "2. Pakai chip **Lini** untuk melihat isi tiap lini.",
        "3. Buka produk yang salah → ubah **Lini** → Simpan.",
        "   Pagar `INV-LINE-02` akan menolak kombinasi yang bertentangan",
        "   (mis. lini `knit` untuk kain `woven`) beserta alasannya.",
        "4. Lini baru (mis. **Denim**) ditambah di **Pengaturan → Master → Lini Produk**;",
        "   chip-nya langsung muncul di 12 layar tanpa perubahan kode.",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


async def main(dry: bool) -> int:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    print("=" * 84)
    print("  MIGRASI FASE L — master Lini Produk + `line_code` untuk data lama"
          + ("   [DRY RUN]" if dry else ""))
    print("=" * 84)

    before_master = await db.product_lines.count_documents({})
    created, updated = await seed_master(db, dry)
    after_master = await db.product_lines.count_documents({})
    print(f"\n1) Master `product_lines`: sebelum={before_master} → sesudah={after_master} "
          f"(dibuat {created} · dilengkapi {updated})")
    for row in SEED_LINES:
        print(f"   · {row['code']:9s} fabric_wajib={row['fabric_type_required'] or '(bebas)':7s} "
              f"satuan_usulan={row['measure_unit_default']:5s} tahap={'→'.join(row['stage_sequence'])}")

    rows, tally, planned = await fill_products(db, dry)
    changed = sum(1 for r in rows if r["changed"])
    print(f"\n2) Produk: {len(rows)} baris · diisi migrasi {changed} · "
          f"sudah terisi {len(rows) - changed}")
    for code in sorted(tally):
        print(f"   · {code:9s} {tally[code]:3d} produk")
    review = [r for r in rows if r["review"]]
    if review:
        print(f"\n   ⚠ {len(review)} produk PERLU DITINJAU (motif biasanya ditenun, bukan dicetak):")
        for r in review:
            print(f"     - {r['sku']:16s} → {r['line']:8s} | {r['reason']}")

    docs = await backfill_documents(db, dry, planned)
    print("\n3) Dokumen distempel (baris + turunan `line_codes[]`):")
    for coll, touched, total in docs:
        if total:
            print(f"   · {coll:24s} {touched:4d} / {total:4d} dokumen")

    n_users = await normalize_users(db, dry)
    print(f"\n4) Akun: `allowed_line_codes` dibuat eksplisit pada {n_users} akun "
          f"(kosong = SEMUA lini — bawaan, tanpa regresi)")

    write_report(rows, tally, docs, dry)
    print(f"\n5) Laporan ditulis: {REPORT_PATH.relative_to(ROOT)}")
    print("\nSELESAI" + (" (dry-run: tidak ada perubahan disimpan)" if dry else ""))
    print("Tinjau laporan, lalu koreksi lini yang salah LEWAT LAYAR Master Produk.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Migrasi FASE L — lini produk")
    ap.add_argument("--dry-run", action="store_true", help="cetak rencana tanpa menulis")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.dry_run)))
