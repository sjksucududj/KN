#!/usr/bin/env python3
"""audit_md_erp_readiness.py — ALAT UKUR KEADAAN untuk RENCANA_EKSEKUSI_MD_ERP.md.

KENAPA BERKAS INI ADA
=====================
Rencana v1 (`RENCANA_EKSEKUSI_MD_ERP.md`, sesi 2026-08-18 pagi) menulis puluhan
klaim "SUDAH ADA" / "belum ada" dalam bentuk PROSA. Prosa tidak bisa memerah.
Saat rencana itu dibaca ulang beberapa jam kemudian, **tujuh** klaimnya sudah
tidak cocok dengan kenyataan basis data & kode (mis. `uoms` diklaim berisi 6
satuan — nyatanya 4; `color_library.system` diklaim baru "KN" — nyatanya sudah
memuat TCX/TPX Pantone; `qc_inspections` diklaim koleksi aktif — nyatanya 0
dokumen dan tak pernah ditulis siapa pun).

Kelas kesalahan itu mahal: agen berikutnya membangun di atas angka yang salah,
lalu "menemukan" bahwa fondasinya beda — biasanya setelah separuh fase jadi.

Berkas ini mengubah seluruh klaim itu menjadi PENGUKURAN yang bisa diulang:

    python scripts/audit_md_erp_readiness.py            # laporan lengkap
    python scripts/audit_md_erp_readiness.py --fase L   # satu fase saja
    python scripts/audit_md_erp_readiness.py --strict    # exit 1 bila ada DRIFT

TIGA STATUS (sengaja dibedakan)
-------------------------------
  [SELESAI] fakta yang sudah benar / fase yang sudah mendarat.
  [BELUM  ] memang belum dikerjakan (bukan kesalahan — ini peta pekerjaan).
  [DRIFT  ] ADA YANG TIDAK KONSISTEN HARI INI, terlepas dari rencana MD ERP.
            `--strict` hanya memerah pada DRIFT, supaya alat ini tidak
            "memerah palsu" hanya karena fase belum dikerjakan.

Alat ini HANYA MEMBACA (tidak menulis DB, tidak menyentuh berkas).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
BE = ROOT / "backend"
FE = ROOT / "frontend" / "src"

G, Y, R, C, B, X = ("\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m")

SELESAI, BELUM, DRIFT = "SELESAI", "BELUM  ", "DRIFT  "
rows: List[Tuple[str, str, str, str]] = []      # (fase, status, judul, keterangan)


def add(fase: str, status: str, judul: str, ket: str = "") -> None:
    rows.append((fase, status, judul, ket))


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def files(root: Path, suffixes: Tuple[str, ...]) -> List[Path]:
    out: List[Path] = []
    for p in root.rglob("*"):
        if p.suffix in suffixes and "__pycache__" not in p.parts and "node_modules" not in p.parts:
            out.append(p)
    return out


# ── sumber kebenaran statik (dibaca sebagai teks supaya alat ini tidak
#    mengimpor backend & tidak butuh event loop FastAPI) ──────────────────────
SRC = {
    "entity_scope": read(BE / "entity_scope.py"),
    "write_guard": read(BE / "entity_write_guard.py"),
    "doc_refs": read(BE / "services" / "doc_refs_service.py"),
    "masters": read(BE / "services" / "entity_master_service.py"),
    "indexes": read(BE / "indexes.py"),
    "residue": read(ROOT / "scripts" / "gate_residue.py"),
    "registry_md": read(ROOT / "ENTITY_REGISTRY.md"),
    "domain": read(BE / "domain_registry.py"),
    "perms": read(BE / "permissions_config.py"),
    "queues": read(BE / "services" / "approval_backlog_service.py"),
    "gate": read(ROOT / "scripts" / "gate.sh"),
    "notif": read(BE / "services" / "notification_service.py"),
    # FASE L: definisi kolom/field master DIPINDAH ke berkas data terpisah
    # (`masterFieldsConfig.js`) sesuai §3.3/§4.2 rencana — layar hanya memakainya.
    # Alat ukur ikut membaca keduanya; kalau tidak, relokasi yang MEMANG diminta
    # rencana akan terbaca sebagai kemunduran.
    "fe_masters": (read(FE / "features" / "settings" / "masters" / "EntityMastersView.jsx")
                   + read(FE / "features" / "settings" / "masters" / "masterFieldsConfig.js")),
    "fe_nav": read(FE / "config" / "navStructure.js") + read(FE / "config" / "navMeta.js"),
    "fe_router": read(FE / "AppViewRouter.jsx"),
    "core_utils": read(BE / "core_utils.py"),
}

# Koleksi baru yang direncanakan MD ERP. `kind`:
#   master   → dikelola `entity_master_service` (baris global "all" + override)
#   dokumen  → dokumen bernomor (wajib masuk DOC_TYPES + gate residu)
NEW_COLLECTIONS: Dict[str, Dict[str, Any]] = {
    "product_lines":    {"fase": "L", "kind": "master",  "master_kind": "product-lines"},
    "process_stages":   {"fase": "T", "kind": "master",  "master_kind": "process-stages"},
    "sample_types":     {"fase": "S", "kind": "master",  "master_kind": "sample-types"},
    "complaint_reasons": {"fase": "I", "kind": "master", "master_kind": "complaint-reasons"},
    "inspections":      {"fase": "I", "kind": "dokumen", "prefix": "INS-"},
    "design_requests":  {"fase": "D", "kind": "dokumen", "prefix": "DSR-"},
}

# FASE U — koleksi yang WAJIB punya `qty_rolls` (jumlah gulungan) di samping
# `quantity`+`unit`. Nilai = "items" (di dalam baris) atau "root".
QTY_ROLLS_TARGETS: Dict[str, str] = {
    "purchase_orders": "items", "purchase_requisitions": "items",
    "sales_orders": "items", "sales_returns": "items", "purchase_returns": "items",
    "warehouse_transfers": "items", "interco_transactions": "items",
    "interco_returns": "items", "internal_requests": "items", "rfqs": "items",
    "wms_tasks": "root", "shipments": "root", "inventory_movements": "root",
    "makloon_orders": "steps", "inspections": "lines",
}

# FASE L — 12 layar yang WAJIB punya penyaring lini (path relatif ke frontend/src).
LINE_FILTER_SCREENS: List[str] = [
    "features/admin/AdminView.jsx",                       # Master Produk
    "features/orders/OrdersView.jsx",                     # Pesanan
    "features/admin/PurchaseOrderManagement.jsx",         # Pesanan Pembelian
    "features/purchasing/PurchaseRequisitions.jsx",       # PR
    "features/rnd/RndSamplesView.jsx",                    # Sample
    "features/rnd/RndSpecsView.jsx",                      # Spesifikasi
    "features/rnd/RndDesignsView.jsx",                    # Desain
    "features/wms/InventoryStockView.jsx",                # Roll / Stok
    "features/transfers/InterCompanyTransfers.jsx",       # Transfer
    "features/sales/SalesReturns.jsx",                    # Retur jual
    "features/purchasing/PurchaseReturns.jsx",            # Retur beli
    "features/purchasing/MakloonOrdersView.jsx",          # Makloon
]


# ═══════════════════════════════════════════════════════════════════════════
# A. PAGAR ENTITAS untuk koleksi baru (12 titik sambung)
# ═══════════════════════════════════════════════════════════════════════════
def cek_pagar_entitas(existing: Dict[str, int]) -> None:
    for coll, meta in NEW_COLLECTIONS.items():
        fase, kind = meta["fase"], meta["kind"]
        ada = coll in existing
        n = existing.get(coll, 0)
        add(fase, SELESAI if ada else BELUM, f"koleksi `{coll}` lahir",
            f"{n} dokumen" if ada else "belum ada di basis data")

        # 1. terdaftar SCOPED (mesin scoping F0-C)
        scoped = bool(re.search(rf'"{coll}"', SRC["entity_scope"]))
        add(fase, SELESAI if scoped else BELUM, f"  · `{coll}` ∈ entity_scope",
            "SCOPED_COLLECTIONS/SCOPE_FIELD" if scoped else
            "WAJIB: entity_scope.SCOPED_COLLECTIONS (+SCOPE_FIELD bila field beda)")

        # 2. master berlapis → wajib INHERITED_GLOBAL_VALUES + MasterSpec
        if kind == "master":
            inh = bool(re.search(rf'"{coll}":\s*\[', SRC["entity_scope"]))
            add(fase, SELESAI if inh else BELUM, f"  · `{coll}` ∈ INHERITED_GLOBAL_VALUES",
                'baris global "all" terlihat semua badan usaha' if inh else
                'WAJIB: ["all", "", None] — kalau tidak, baris global HILANG dari layar')
            mk = meta["master_kind"]
            spec = f'"{mk}": MasterSpec(' in SRC["masters"]
            add(fase, SELESAI if spec else BELUM, f"  · MasterSpec `{mk}`",
                "terdaftar" if spec else "WAJIB: entity_master_service.MASTERS")
            fe_col = f'"{mk}": [' in SRC["fe_masters"]
            add(fase, SELESAI if fe_col else BELUM, f"  · kolom layar master `{mk}` (FE)",
                "COLUMNS/CREATE_FIELDS ada" if fe_col else
                "WAJIB: EntityMastersView COLUMNS + CREATE_FIELDS — tanpa ini tabelnya KOSONG")

        # 3. dokumen bernomor → DOC_TYPES + gate residu + nomor per badan usaha
        if kind == "dokumen":
            dt = f'"{coll}"' in SRC["doc_refs"]
            add(fase, SELESAI if dt else BELUM, f"  · `{coll}` ∈ doc_refs.DOC_TYPES",
                "bisa ditelusuri & dicetak" if dt else
                "WAJIB: _T(...) di DOC_TYPES — kalau tidak, jejak dokumen berhenti")
            res = f'"{coll}"' in SRC["residue"]
            add(fase, SELESAI if res else BELUM, f"  · `{coll}` ∈ gate_residue.WATCH",
                "residu POC terpantau" if res else
                "WAJIB: scripts/gate_residue.py WATCH — POC akan meninggalkan sampah tak terlihat")
            svc = read(BE / "services" / f"{coll[:-1]}_service.py") or \
                read(BE / "services" / f"{coll}_service.py")
            bernomor = "next_doc_number(" in svc and "entity_id=" in svc
            add(fase, SELESAI if bernomor else BELUM,
                f"  · nomor `{coll}` per badan usaha",
                f"next_doc_number(..., entity_id=…) → KSC/{meta['prefix']}00001" if bernomor
                else f"WAJIB: next_doc_number(..., prefix=\"{meta['prefix']}\", entity_id=…)")

        # 4. index
        idx = f'"{coll}": [' in SRC["indexes"]
        add(fase, SELESAI if idx else BELUM, f"  · index `{coll}`",
            "terdaftar di indexes.py" if idx else "WAJIB: backend/indexes.py")

        # 5. ENTITY_REGISTRY.md (CHECK 8 validate_compliance membacanya LANGSUNG)
        reg = f"`{coll}`" in SRC["registry_md"] or re.search(
            rf"^#{{2,4}}\s+{coll}\b", SRC["registry_md"], re.M) is not None
        add(fase, SELESAI if reg else BELUM, f"  · `{coll}` ∈ ENTITY_REGISTRY.md",
            "terdokumentasi" if reg else
            "WAJIB: kalau tidak, CHECK 8 validate_compliance.py MEMERAH")


# ═══════════════════════════════════════════════════════════════════════════
# B. FASE L — LINI PRODUK
# ═══════════════════════════════════════════════════════════════════════════
async def cek_fase_l(db, existing) -> None:
    n_prod = await db.products.count_documents({})
    n_line = await db.products.count_documents({"line_code": {"$nin": [None, ""]}})
    add("L", SELESAI if n_line == n_prod and n_prod else BELUM,
        "products.line_code terisi", f"{n_line}/{n_prod} produk")
    n_user = await db.users.count_documents({})
    n_allow = await db.users.count_documents({"allowed_line_codes": {"$exists": True}})
    add("L", SELESAI if n_allow else BELUM, "users.allowed_line_codes",
        f"{n_allow}/{n_user} akun (kosong = semua lini — itu memang bawaannya)")
    svc = (BE / "services" / "line_scope.py").exists()
    add("L", SELESAI if svc else BELUM, "services/line_scope.py",
        "ada" if svc else "WAJIB: tiru services/product_exclusivity.py (query + assert)")
    enum = "product_line" in SRC["domain"]
    add("L", SELESAI if enum else BELUM, "enum `product_line` di /api/enums",
        "ada" if enum else "WAJIB: dari master (lihat jembatan FASE T), bukan hardcode")
    comp = (FE / "components" / "LineFilter.jsx").exists()
    add("L", SELESAI if comp else BELUM, "komponen <LineFilter/>",
        "ada" if comp else "WAJIB: satu komponen untuk 12 layar")
    pakai = [s for s in LINE_FILTER_SCREENS if "LineFilter" in read(FE / s)]
    add("L", SELESAI if len(pakai) == len(LINE_FILTER_SCREENS) else BELUM,
        "penyaring lini di 12 layar", f"{len(pakai)}/{len(LINE_FILTER_SCREENS)} layar")
    # DRIFT: literal lini di frontend (nilai lini WAJIB dari master, bukan diketik).
    #
    # Versi pertama detektor ini menandai SETIAP berkas yang memuat kata
    # "woven"/"knit"/"printing" — dan 6 dari 6 temuannya ternyata SAH, karena
    # kata itu di sana berarti `fabric_type` (fisika kain), bukan lini. Penjaga
    # yang menuduh palsu akan diabaikan orang, lalu berhenti menjaga apa pun
    # (pelajaran yang sama dengan `ux_audit` di FASE P5). Jadi sekarang literal
    # hanya dihitung bila BARISNYA memang berbicara soal LINI: menyebut
    # `line_code` / `line_codes` / `allowed_line_codes` / `product_line`.
    # Pola dipersempit lagi sesudah diuji ke kode: mencari "baris yang menyebut lini"
    # masih menuduh palsu satu berkas — `AdminView` menyimpan SELURUH state form
    # produk dalam satu baris panjang, sehingga `fabric_type: "woven"` (sah) berdiri
    # sebaris dengan `line_code: ""` (juga sah). Yang benar-benar salah hanyalah
    # nilai lini yang DILEKATKAN ke field lini, jadi itulah yang dicari.
    LINE_LITERAL = re.compile(
        r"(line_code|line_codes|allowed_line_codes|lineFilter|product_line)"
        r"""[^\n]{0,40}?["'](woven|knit|printing)["']""")
    literal = []
    for p in files(FE, (".js", ".jsx")):
        if "LineFilter" in p.name:
            continue
        for ln in read(p).splitlines():
            if LINE_LITERAL.search(ln):
                literal.append(f"{p.relative_to(FE).as_posix()}: {ln.strip()[:70]}")
                break
    add("L", BELUM if literal else SELESAI, "literal lini di frontend",
        f"{len(literal)} baris menuliskan kode lini langsung (harus dari master "
        f"`product_lines` lewat useDomainEnums): {' · '.join(literal[:3])}"
        if literal else "tidak ada — seluruh nilai lini datang dari master")


# ═══════════════════════════════════════════════════════════════════════════
# C. FASE T — TAHAPAN PROSES
# ═══════════════════════════════════════════════════════════════════════════
async def cek_fase_t(db, existing) -> None:
    br = (BE / "services" / "master_registry.py").exists()
    add("T", SELESAI if br else BELUM, "services/master_registry.py (jembatan master↔registry)",
        "ada" if br else "WAJIB: satu pembaca (master hidup + fallback seed domain_registry)")
    proc = re.findall(r'\{"value": "([a-z_]+)",\s+"label": "[^"]*",\s+"fabric_type"',
                      SRC["domain"])
    add("T", SELESAI if "screen" in proc else BELUM, "proses `screen` di registry",
        f"PROCESS_TYPES = {proc}")
    n_mk = await db.makloon_orders.count_documents({})
    n_sc = await db.makloon_orders.count_documents({"steps.stage_code": {"$exists": True}})
    add("T", SELESAI if n_mk and n_sc == n_mk else BELUM, "makloon_orders.steps[].stage_code",
        f"{n_sc}/{n_mk} SPK")
    # DRIFT: dua kosakata yang sering dikira satu
    stages = re.findall(r'\{"value": "([a-z]+)",\s+"label": "[^"]*",\s+"order"', SRC["domain"])
    add("T", SELESAI, "dua kosakata terpisah (INFORMASI, bukan tugas)",
        f"STAGES(kain)={stages} · PROCESS_TYPES(proses)={proc} — "
        "daftar pemilik (benang·tenun·celup·pfp·screen·inspect) MENCAMPUR keduanya")


# ═══════════════════════════════════════════════════════════════════════════
# D. FASE U — DUA SATUAN
# ═══════════════════════════════════════════════════════════════════════════
async def cek_fase_u(db, existing) -> None:
    rows = await db.uoms.find({}, {"_id": 0}).to_list(200)
    kode = sorted([u.get("code", "") for u in rows])
    add("U", SELESAI if {"KG", "PANEL"} <= set(kode) else BELUM, "master satuan KG & PANEL",
        f"uoms = {kode}")
    # DRIFT NYATA: satuan yang dipakai dokumen vs KOSAKATA master.
    # FASE U — kosakata master = `code` ∪ `name` ∪ `aliases[]` baris AKTIF. Sebelum ini
    # pengukur hanya melihat `code`, jadi ia menuduh `yard`/`meter` "tidak ada di master"
    # padahal itu memang kata yang dipakai dokumen dan sekarang terdaftar sebagai alias
    # baris `YRD`/`MTR`. Alat ukur yang menuduh palsu akan diabaikan (pelajaran FASE P5).
    dipakai = set()
    for coll, f in (("inventory_rolls", "unit"), ("inventory_movements", "unit"),
                    ("wms_tasks", "unit"), ("sales_orders", "items.unit")):
        if coll in existing:
            for v in await db[coll].distinct(f):
                if isinstance(v, str) and v:
                    dipakai.add(v)
    norm = set()
    for r in rows:
        if (r.get("status") or "active") != "active":
            continue
        for k in [r.get("code"), r.get("name")] + list(r.get("aliases") or []):
            if isinstance(k, str) and k.strip():
                norm.add(k.strip().lower())
    hilang = sorted(u for u in dipakai if u.lower() not in norm)
    add("U", DRIFT if hilang else SELESAI, "satuan dokumen ⊆ master satuan (kode/nama/alias)",
        f"dipakai dokumen={sorted(dipakai)} · TIDAK ADA di master={hilang} "
        "(konversi tetap jalan lewat uom_service.CANON/WEIGHT_CANON, "
        "tetapi pemilih satuan di layar & /api/uoms tidak menawarkannya)"
        if hilang else f"semua satuan terdaftar (lewat alias): {sorted(dipakai)} · "
                       f"kosakata master {len(norm)} kata · gate INV-UOM-02 menjaganya")
    # cakupan qty_rolls
    sudah, belum = [], []
    for coll, tempat in QTY_ROLLS_TARGETS.items():
        if coll not in existing:
            continue
        field = {"items": "items.qty_rolls", "steps": "steps.qty_rolls",
                 "lines": "lines.qty_rolls", "root": "qty_rolls"}[tempat]
        (sudah if await db[coll].count_documents({field: {"$exists": True}}) else belum).append(coll)
    add("U", SELESAI if not belum else BELUM, "cakupan `qty_rolls`",
        f"sudah={len(sudah)} · belum={len(belum)}/{len(QTY_ROLLS_TARGETS)} → {belum}")
    comp = (FE / "components" / "QtyDual.jsx").exists()
    add("U", SELESAI if comp else BELUM, "komponen <QtyDual/>",
        "ada" if comp else "WAJIB: satu komponen (gate INV-QTY-01 melarang rangkai manual)")
    helper = "def qty_dual(" in SRC["core_utils"]
    add("U", SELESAI if helper else BELUM, "core_utils.qty_dual()",
        "ada" if helper else "WAJIB: dipakai PDF & CSV supaya enam tampilan satu kalimat")


# ═══════════════════════════════════════════════════════════════════════════
# E. FASE S — SAMPLING
# ═══════════════════════════════════════════════════════════════════════════
async def cek_fase_s(db, existing) -> None:
    n = await db.md_samples.count_documents({})
    lama = await db.md_samples.count_documents({"sample_type": {"$exists": True}})
    baru = await db.md_samples.count_documents({"sample_types": {"$exists": True}})
    add("S", SELESAI if baru == n and lama == 0 else BELUM,
        "md_samples.sample_types[] menggantikan sample_type",
        f"total={n} · field lama masih di {lama} dokumen · field baru di {baru}")
    st = re.search(r"SAMPLE_TYPES[^\[]*\[(.*?)\]\n", SRC["domain"], re.S)
    isi = re.findall(r'"value": "([a-z_]+)"', st.group(1)) if st else []
    add("S", SELESAI if "handfeel" in isi else BELUM, "jenis `handfeel` terdaftar",
        f"SAMPLE_TYPES = {isi}")
    bulk = await db.md_samples.count_documents({"sample_type": "bulk_sample"}) + \
        await db.md_samples.count_documents({"sample_types": "bulk_sample"})
    add("S", SELESAI, "pemakaian `bulk_sample` (untuk keputusan pemilik #4)",
        f"{bulk} dokumen memakainya → kandidat dinonaktifkan")
    tc = await db.md_samples.count_documents({"rounds.type_code": {"$exists": True}})
    add("S", SELESAI if tc else BELUM, "rounds[].type_code (iterasi per jenis)",
        f"{tc}/{n} dokumen")
    so = await db.md_samples.count_documents({"so_id": {"$nin": [None, ""]}})
    add("S", SELESAI if so else BELUM, "md_samples.so_id terisi (tautan pesanan)",
        f"{so}/{n} — form belum punya isiannya")
    fin = await db.md_samples.count_documents({"finished_at": {"$exists": True}})
    add("S", SELESAI if fin else BELUM, "penanda `finished_at`/`delivered_at`",
        f"{fin}/{n} dokumen")
    sistem = sorted(await db.color_library.distinct("system"))
    add("S", SELESAI if {"TCX", "TPX"} & set(sistem) else BELUM,
        "pustaka warna sudah memuat sistem Pantone",
        f"color_library.system = {sistem} (TCX/TPX = kode Pantone → klaim "
        "rencana v1 'baru KN' SALAH)")
    # pembaca `sample_type` yang wajib ikut diubah saat migrasi
    pembaca_be = [p.relative_to(BE).as_posix() for p in files(BE, (".py",))
                  if "sample_type" in read(p) and not p.name.startswith(("backend_test", "test_"))]
    pembaca_fe = [p.relative_to(FE).as_posix() for p in files(FE, (".js", ".jsx"))
                  if "sample_type" in read(p)]
    add("S", SELESAI if baru == n and lama == 0 else BELUM,
        "pembaca `sample_type` yang wajib ikut migrasi",
        f"backend={len(pembaca_be)} berkas · frontend={len(pembaca_fe)} berkas "
        f"→ {', '.join(pembaca_be[:6])}…")
    # D7 — nomor dokumen demo: pola per badan usaha + KEUNIKAN
    pola = {"md_samples": (r"^[A-Z]+/SMP-\d{5}$", "number"),
            "md_specs": (r"^[A-Z]+/SPEC-\d{5}$", "number"),
            "supplier_contracts": (r"^[A-Z]+/SCT-\d{5}$", "contract_number")}
    salah: Dict[str, int] = {}
    dobel: Dict[str, List[str]] = {}
    for coll, (rx, fld) in pola.items():
        if coll not in existing:
            continue
        vals = [d.get(fld) or "" for d in await db[coll].find({}, {"_id": 0, fld: 1}).to_list(1000)]
        salah[coll] = sum(1 for v in vals if not re.match(rx, v))
        dup = sorted({v for v in vals if vals.count(v) > 1 and v})
        if dup:
            dobel[coll] = dup
    rusak = any(salah.values()) or bool(dobel)
    add("S", DRIFT if rusak else SELESAI, "nomor dokumen demo: pola + keunikan",
        f"menyimpang dari pola={salah} · NOMOR GANDA={ {k: len(v) for k, v in dobel.items()} } "
        f"contoh={sum(list(dobel.values()), [])[:4]} → sumbernya "
        "`scripts/seed_rnd_kpi_demo.py` menulis `number` dengan f-string "
        "(f\"KSC/SMP-H{back}{designer[:2].upper()}\") alih-alih "
        "`core_utils.next_doc_number()` — dua desainer ber-awalan huruf sama "
        "menghasilkan NOMOR DOKUMEN KEMBAR"
        if rusak else f"semua nomor sesuai pola & unik: {list(pola)}")


# ═══════════════════════════════════════════════════════════════════════════
# F. FASE I — INSPEKSI / QC
# ═══════════════════════════════════════════════════════════════════════════
async def cek_fase_i(db, existing) -> None:
    add("I", DRIFT if "qc_inspections" in SRC["entity_scope"] and
        "qc_inspections" not in existing else SELESAI,
        "koleksi hantu `qc_inspections`",
        "terdaftar SCOPED di entity_scope tetapi 0 dokumen & tak pernah ditulis "
        "siapa pun (grep: hanya muncul di entity_scope.py) → putuskan: dipakai "
        "sebagai nama koleksi FASE I, atau dicabut dari registry"
        if "qc_inspections" in SRC["entity_scope"] and "qc_inspections" not in existing
        else "tidak ada")
    # DUA bentuk `inventory_rolls.inspection` yang hidup hari ini
    qc4 = await db.inventory_rolls.count_documents({"inspection.thresholds": {"$exists": True},
                                                    "inspection.points": {"$gt": 0}})
    retur = await db.inventory_rolls.count_documents({"inspection.disposition": {"$exists": True}})
    add("I", SELESAI, "penulis hasil inspeksi yang SUDAH ADA (jangan dibuat pintu ke-3)",
        f"qc_inspection_service (4-point, ber-grade_service) → {qc4} roll · "
        f"return_service (kondisi/disposisi, grade saat roll LAHIR) → {retur} roll · "
        "keduanya menulis field `inventory_rolls.inspection` dengan BENTUK BERBEDA")
    gh = await db.inventory_rolls.count_documents({"grade_history": {"$exists": True}})
    insp = await db.inventory_rolls.count_documents({"inspection": {"$nin": [None, {}]}})
    add("I", SELESAI, "acuan gate INV-QC-02 (grade ↔ dokumen)",
        f"roll ber-grade_history={gh} · roll ber-inspection={insp} → gate WAJIB "
        "mengecualikan grade SAAT ROLL LAHIR (retur karantina) karena itu bukan "
        "PERUBAHAN grade")
    perm = '"inspection"' in SRC["perms"]
    add("I", SELESAI if perm else BELUM, "izin resource `inspection`",
        "ada di permissions_config" if perm else
        "WAJIB: permissions_config.DEFAULT_PERMISSIONS (admin/manager/warehouse/sales_admin)")
    kebijakan = "color_mismatch_action" in read(BE / "config_catalog_ops.py") or \
        "color_mismatch_action" in read(BE / "config_catalog_core.py")
    add("I", SELESAI if kebijakan else BELUM, "kebijakan `qc.color_mismatch_action`",
        "ada di katalog konfigurasi" if kebijakan else
        "WAJIB: katalog config (abaikan|peringatkan|tahan) — keputusan pemilik #5")
    ms = await db.sales_returns.count_documents({"goods_arrived_at": {"$exists": True}})
    add("I", SELESAI if ms else BELUM, "milestone retur (SJ toko → sampai → inspect)",
        f"{ms}/{await db.sales_returns.count_documents({})} dokumen retur jual")
    # D6 — label relasi yang tidak punya kebalikan → link() menolaknya
    inv = re.search(r"REL_INVERSE: Dict\[str, str\] = \{(.*?)\n\}", SRC["doc_refs"], re.S)
    lab = re.search(r"REL_LABEL: Dict\[str, str\] = \{(.*?)\n\}", SRC["doc_refs"], re.S)
    k_inv = set(re.findall(r'"([a-z_]+)":', inv.group(1))) if inv else set()
    k_lab = set(re.findall(r'"([a-z_]+)":', lab.group(1))) if lab else set()
    yatim = sorted(k_lab - k_inv)
    add("I", DRIFT if yatim else SELESAI, "kosakata relasi dokumen utuh (REL_LABEL ⊆ REL_INVERSE)",
        f"REL_INVERSE={len(k_inv)} nilai · REL_LABEL={len(k_lab)} label · "
        f"label tanpa kebalikan={yatim} → `link(rel=…)` MELEMPAR RefsError untuk nilai itu "
        "(betulkan saat menaut acuan sample di FASE I)"
        if yatim else f"{len(k_inv)} nilai relasi, semuanya berpasangan")


# ═══════════════════════════════════════════════════════════════════════════
# G. FASE P / D / N / M
# ═══════════════════════════════════════════════════════════════════════════
async def cek_fase_pdnm(db, existing) -> None:
    n_po = await db.purchase_orders.count_documents({})
    sp = await db.purchase_orders.count_documents({"stage_progress": {"$exists": True}})
    add("P", SELESAI if sp == n_po and n_po else BELUM, "purchase_orders.stage_progress[]",
        f"{sp}/{n_po} PO")
    sn = await db.purchase_orders.count_documents({"sales_name": {"$nin": [None, ""]}})
    add("P", SELESAI if sn else BELUM, "purchase_orders.sales_name (dirunut, bukan diketik)",
        f"{sn}/{n_po} PO")
    # DRIFT: rantai PO→PR→SO yang dibutuhkan Fase P
    pr_po = await db.purchase_requisitions.count_documents({"po_ids": {"$nin": [None, [], ""]}})
    n_pr = await db.purchase_requisitions.count_documents({})
    po_pr = await db.purchase_orders.count_documents({"pr_id": {"$nin": [None, ""]}})
    src = await db.purchase_requisitions.distinct("source")
    add("P", DRIFT if po_pr == 0 else SELESAI, "rantai PO → PR → SO untuk `sales_name`",
        f"PR→PO: {pr_po}/{n_pr} PR menyimpan po_ids · PO→PR: {po_pr}/{n_po} PO "
        f"menyimpan pr_id (TIDAK ADA) · PR.source={src} (belum ada `so_repeat` di "
        "data demo, walau restock_service.PR_SOURCE menulisnya) → FASE P wajib "
        "membuat tautannya DULU, kalau tidak `sales_name` mustahil dirunut")
    dr_svc = (BE / "services" / "design_request_service.py").exists()
    add("D", SELESAI if dr_svc else BELUM, "services/design_request_service.py",
        "ada" if dr_svc else "belum")
    q_design = '"design_request"' in SRC["queues"]
    add("D", SELESAI if q_design else BELUM, "antrean keputusan `design_request`",
        "terdaftar di QUEUES" if q_design else
        "WAJIB: approval_backlog_service.QUEUES — gate INV-APPR-01 memerah tanpa ini")
    kode = sorted(c for c in await db.design_gallery.distinct("code") if c)
    kosong = await db.design_gallery.count_documents({"code": ""})
    add("D", DRIFT if kosong else SELESAI, "design_gallery.code terisi",
        f"kode terpakai={kode} · {kosong} dokumen ber-kode KOSONG → layar "
        "permintaan desain akan menampilkan '—' untuk artwork itu" if kosong else "penuh")
    aud = (BE / "services" / "notification_audience.py").exists()
    add("N", SELESAI if aud else BELUM, "services/notification_audience.py",
        "ada" if aud else "WAJIB: alamat berbasis WEWENANG + DIVISI")
    perm_arg = "recipient_permission" in SRC["notif"]
    add("N", SELESAI if perm_arg else BELUM, "create_notification(recipient_permission=…)",
        "ada" if perm_arg else "WAJIB: hari ini hanya recipient_role / recipient_user")
    semua = await db.notifications.count_documents({"recipient_role": "all"})
    per_tipe: Dict[str, int] = {}
    async for d in db.notifications.find({"recipient_role": "all"}, {"_id": 0, "type": 1}):
        per_tipe[d.get("type", "?")] = per_tipe.get(d.get("type", "?"), 0) + 1
    add("N", DRIFT if semua else SELESAI, 'notifikasi ber-alamat "semua peran"',
        f"{semua} dokumen → {per_tipe} (setiap peran, termasuk finance, melihatnya)")
    ar = await db.notifications.count_documents({"type": "ar_due_soon"})
    add("N", SELESAI, "ar_due_soon di kotak siapa",
        f"{ar} notifikasi di data demo · penerima di kode = sales pemegang akun + "
        "manager (finance TIDAK termasuk) — lihat alert_ops_service.job_ar_due_soon")
    so_notif = await db.notifications.count_documents({"type": {"$regex": "special_order"}})
    add("N", SELESAI if so_notif else BELUM, "notifikasi PO custom (special_orders)",
        f"{so_notif} notifikasi untuk {await db.special_orders.count_documents({})} dokumen")
    n_lc = await db.makloon_orders.count_documents({"line_code": {"$nin": [None, ""]}})
    add("M", SELESAI if n_lc else BELUM, "makloon_orders.line_code",
        f"{n_lc}/{await db.makloon_orders.count_documents({})} SPK")


# ═══════════════════════════════════════════════════════════════════════════
# H. KONTRAK UI/UX — yang WAJIB dipatuhi layar baru (bukan diubah)
# ═══════════════════════════════════════════════════════════════════════════
def cek_ui_kontrak() -> None:
    wajib = {
        "components/FormModal.jsx": "INV-UI-05 — tombol Buat = pop-up",
        "components/DetailModal.jsx": "INV-UI-08 — panel rincian = pop-up",
        "components/ErrorNotice.jsx": "INV-UI-03 — error tak boleh senyap",
        "components/KNSelect.jsx": "P6 — dropdown seragam",
        "components/ConfirmModal.jsx": "INV-UI-06 — alert/confirm peramban dilarang",
        "hooks/usePagedList.js": "P2 — paginasi server + fetchAll untuk CSV",
        "utils/csvExport.js": "INV-UI-07 — unduh CSV daftar berhalaman",
        "hooks/useDomainEnums.js": "R7 — enum HANYA dari /api/enums",
        "utils/entityLabel.js": "INV-UI-02 — id entitas tak boleh tampil",
    }
    for path, alasan in wajib.items():
        ada = (FE / path).exists()
        add("UI", SELESAI if ada else DRIFT, f"pakai ulang `{path}`", alasan)
    gates = re.findall(r"INV-[A-Z]+-\d+", SRC["gate"])
    add("UI", SELESAI, "gate UI/UX yang menjaga tampilan tidak berubah",
        f"{len(set(gates))} invarian terdaftar di scripts/gate.sh: "
        f"{', '.join(sorted(set(g for g in gates if g.startswith(('INV-UI', 'INV-UX', 'INV-ROLE', 'INV-HOME')))))}")


# ═══════════════════════════════════════════════════════════════════════════
async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fase", default="", help="L T U S I P D N M UI (boleh digabung, mis. LTU)")
    ap.add_argument("--strict", action="store_true", help="exit 1 bila ada DRIFT")
    args = ap.parse_args()

    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = cli[os.environ.get("DB_NAME", "test_database")]
    names = await db.list_collection_names()
    existing: Dict[str, int] = {}
    for n in names:
        existing[n] = await db[n].count_documents({})

    cek_pagar_entitas(existing)
    await cek_fase_l(db, existing)
    await cek_fase_t(db, existing)
    await cek_fase_u(db, existing)
    await cek_fase_s(db, existing)
    await cek_fase_i(db, existing)
    await cek_fase_pdnm(db, existing)
    cek_ui_kontrak()

    pilih = set(args.fase.upper()) if args.fase else None
    if args.fase and "UI" in args.fase.upper():
        pilih = (pilih or set()) | {"UI"}

    print(f"\n{B}{'=' * 96}{X}")
    print(f"{B}  KESIAPAN MD ERP — pengukuran {len(rows)} fakta "
          f"(basis data `{db.name}`, {len(names)} koleksi){X}")
    print(f"{B}{'=' * 96}{X}")
    fase_now = ""
    n_sel = n_bel = n_dri = 0
    urut = {f: i for i, f in enumerate(["L", "T", "U", "S", "I", "P", "D", "N", "M", "UI"])}
    for fase, status, judul, ket in sorted(rows, key=lambda r: urut.get(r[0], 99)):
        if pilih and fase not in pilih and not (fase == "UI" and "UI" in (pilih or ())):
            continue
        if fase != fase_now:
            print(f"\n{C}── FASE {fase} {'─' * (88 - len(fase))}{X}")
            fase_now = fase
        warna = {SELESAI: G, BELUM: Y, DRIFT: R}[status]
        print(f"  {warna}[{status}]{X} {judul}")
        if ket:
            for chunk in _wrap(ket, 84):
                print(f"            {chunk}")
    for _f, s, _j, _k in rows:
        n_sel += s == SELESAI
        n_bel += s == BELUM
        n_dri += s == DRIFT
    print(f"\n{B}{'=' * 96}{X}")
    print(f"  {G}SELESAI={n_sel}{X}   {Y}BELUM={n_bel}{X}   {R}DRIFT={n_dri}{X}")
    print(f"  DRIFT = tidak konsisten HARI INI (perlu diputuskan/dibetulkan saat fase terkait).")
    print(f"{B}{'=' * 96}{X}\n")
    return 1 if (args.strict and n_dri) else 0


def _wrap(text: str, width: int) -> List[str]:
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
