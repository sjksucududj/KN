#!/usr/bin/env python3
"""INV-LINE-01 & INV-LINE-02 — PAGAR LINI PRODUK (FASE L).

KELAS BUG YANG DICEGAH
======================
Lini produk (woven · knit · printing · lini baru berikutnya) adalah **pembagian
kerja MD**: ia menentukan siapa melihat apa, papan mana, dan chip penyaring mana.
Tiga cara gagal yang semuanya SENYAP — tidak ada galat, tidak ada layar merah:

  A. **Kode lini asing.** Dokumen/akun menyimpan `line_code` yang tidak ada di
     master (salah ketik, master dihapus, seed lama). Akibatnya baris itu tidak
     pernah cocok chip mana pun → pekerjaan tak terlihat oleh yang mengerjakannya.
  B. **Turunan yang berbohong.** `line_codes[]` di kepala dokumen adalah turunan
     dari `items[].line_code`. Kalau jalur tulis baru lupa menghitungnya, daftar
     menyaring dengan angka yang tidak sama dengan isi dokumen — kelas bug yang
     sama dengan KN-G6-ICA-CLOBBER (angka tenang-tenang salah).
  C. **Baris yang lupa distempel.** Dokumen lahir dari 12 jalur berbeda (PO manual,
     PO dari PR/RFQ/blanket, transfer dari SO/retur/antar-PT, …). Satu jalur yang
     lupa memanggil `line_scope.stamp_doc()` melahirkan dokumen tanpa lini padahal
     produknya BERLINI.

INV-LINE-02 menjaga hal yang berbeda: lini **tidak boleh bertentangan dengan
fisika kain**. `products.fabric_type` (woven|knit) adalah SSOT rumus & satuan
kendali; lini `woven`/`knit` mengikatnya (`fabric_type_required`), lini `printing`
SENGAJA tidak mengikat (kain print bisa woven maupun knit).

YANG DIPERIKSA
--------------
STATIK  (tanpa basis data)
  S1. Berkas daftar/tulis yang WAJIB memakai `services/line_scope` benar-benar
      memakainya. Penjaga ini memerah bila seseorang menambah endpoint daftar
      dokumen tanpa pagar lini — pagar yang dilewatkan tidak pernah terlihat
      di layar sampai ada staf berpagar yang membukanya.
RUNTIME (Mongo langsung — opini kedua, tidak lewat API yang sedang diuji)
  R1. (A) semua `line_code` dikenal master · termasuk `users.allowed_line_codes`
  R2. (B) `line_codes[]` == turunan dari `items[].line_code`
  R3. (C) baris ber-`product_id` yang produknya berlini WAJIB ber-`line_code`
  R4. INV-LINE-02 — `fabric_type` produk cocok dengan `fabric_type_required` lininya

Resilient: tanpa MONGO_URL / basis data mati → bagian runtime SKIP (exit 0),
bagian statik tetap jalan. Exit 1 hanya bila invarian terbukti dilanggar.

Usage:
    python scripts/guardrails/verify_line_scope.py
    python scripts/guardrails/verify_line_scope.py --self-test   # bukti-merah, tanpa DB
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Guard, G, R, Y, B, X  # noqa: E402

BE = ROOT / "backend"

# ── S1: berkas yang WAJIB memakai `line_scope` + alasan per baris ────────────
#     (alasan ditulis di sini supaya penjaga bisa menjelaskan DIRINYA saat merah)
MUST_USE_LINE_SCOPE: Dict[str, str] = {
    "routers/products.py": "katalog & Master Produk — pagar baca + validasi INV-LINE-02",
    "routers/sales_orders.py": "buat SO — 403 bila produk di luar lini akun",
    "routers/sales_orders_extra.py": "daftar & ringkasan SO — chip lini (kartu == daftar)",
    "routers/purchase_orders.py": "daftar PO + snapshot baris",
    "routers/purchase_requisitions.py": "daftar PR",
    "routers/transfers.py": "daftar & buat transfer",
    "routers/sales_returns.py": "daftar retur jual",
    "routers/purchase_returns.py": "daftar retur beli",
    "routers/inventory.py": "Daftar Roll",
    "routers/lots.py": "daftar lot",
    "routers/wms.py": "tugas gudang",
    "routers/rnd.py": "spesifikasi & sample",
    "routers/makloon_orders.py": "SPK makloon",
    "routers/design_gallery.py": "galeri desain",
    "services/purchase_requisition_service.py": "snapshot baris PR",
    "services/purchase_return_service.py": "snapshot baris retur beli",
    "services/return_service.py": "snapshot baris retur jual + transfer retur",
    "services/makloon_order_service.py": "lini SPK dari produk output",
    "services/rnd_spec_service.py": "lini spesifikasi",
    "services/rnd_sample_service.py": "lini sample (warisi spesifikasi)",
    "services/design_gallery_service.py": "lini desain",
    "services/pr_sourcing_service.py": "PO hasil realisasi PR (stamp_doc)",
    "services/rfq_service.py": "PO hasil award RFQ (stamp_doc)",
    "services/blanket_po_service.py": "blanket PO / call-off (stamp_doc)",
    "services/sales_order_helpers.py": "transfer dari pemenuhan SO (stamp_doc)",
    "services/interco_service.py": "transaksi & transfer antar-PT (stamp_doc)",
    "services/interco_return_service.py": "transfer retur antar-PT (stamp_doc)",
    "services/internal_request_service.py": "permintaan internal antar-PT (stamp_doc)",
    "services/user_admin_service.py": "validasi `allowed_line_codes` ke master",
}

#: Koleksi ber-`items[]` yang wajib konsisten (turunan & snapshot).
ITEM_COLLECTIONS = ("sales_orders", "purchase_orders", "purchase_requisitions",
                    "warehouse_transfers", "sales_returns", "purchase_returns",
                    "interco_transactions", "special_orders", "internal_requests",
                    "rfqs")
#: Koleksi ber-satu-lini.
SINGLE_COLLECTIONS = ("inventory_rolls", "inventory_lots", "wms_tasks", "md_specs",
                      "md_samples", "design_gallery", "makloon_orders")


# ═════════════════════════ INTI MURNI (bisa di-self-test) ═══════════════════
def check_static(sources: Dict[str, str]) -> List[str]:
    """S1 — berkas wajib memakai `line_scope`. `sources` = {path relatif: isi}."""
    bad: List[str] = []
    for rel, why in MUST_USE_LINE_SCOPE.items():
        text = sources.get(rel)
        if text is None:
            bad.append(f"{rel}: berkas tidak ditemukan (pagar lini tidak bisa dinilai)")
            continue
        if "line_scope" not in text:
            bad.append(f"{rel}: tidak menyebut `line_scope` — {why}")
    return bad


def check_unknown_codes(rows: List[Tuple[str, str, List[str]]],
                        valid: set) -> List[str]:
    """R1 — kode lini asing. `rows` = [(label, id, [kode, …]), …]."""
    bad: List[str] = []
    for label, ident, codes in rows:
        for code in codes:
            c = str(code or "").strip().lower()
            if c and c not in valid:
                bad.append(f"{label} {ident}: lini '{c}' tidak ada di master "
                           f"(master: {', '.join(sorted(valid)) or '—'})")
    return bad


def check_derived(docs: List[Tuple[str, str, Dict[str, Any]]]) -> List[str]:
    """R2 — `line_codes[]` WAJIB sama dengan turunan `items[].line_code`."""
    bad: List[str] = []
    for coll, ident, doc in docs:
        items = doc.get("items") or []
        derived = sorted({str((it or {}).get("line_code") or "").strip().lower()
                          for it in items if isinstance(it, dict)
                          and str((it or {}).get("line_code") or "").strip()})
        head = sorted({str(c or "").strip().lower() for c in (doc.get("line_codes") or [])
                       if str(c or "").strip()})
        if derived != head:
            bad.append(f"{coll} {ident}: `line_codes`={head or '[]'} tetapi turunan "
                       f"baris={derived or '[]'} — turunan tidak boleh berbohong")
    return bad


def check_snapshot(docs: List[Tuple[str, str, Dict[str, Any]]],
                   prod_line: Dict[str, str]) -> List[str]:
    """R3 — baris ber-produk-berlini WAJIB ber-`line_code` (jalur lupa stempel)."""
    bad: List[str] = []
    for coll, ident, doc in docs:
        for it in doc.get("items") or []:
            if not isinstance(it, dict):
                continue
            pid = it.get("product_id")
            want = str(prod_line.get(pid, "") or "").strip().lower()
            got = str(it.get("line_code") or "").strip().lower()
            if want and not got:
                bad.append(f"{coll} {ident}: baris produk {pid} tanpa `line_code` "
                           f"padahal produknya lini '{want}' — jalur tulisnya lupa "
                           "memanggil line_scope.stamp_doc()")
    return bad


def check_fabric(products: List[Dict[str, Any]],
                 master: Dict[str, Dict[str, Any]]) -> List[str]:
    """INV-LINE-02 — lini yang mengikat `fabric_type` tidak boleh bertentangan."""
    bad: List[str] = []
    for p in products:
        code = str(p.get("line_code") or "").strip().lower()
        if not code:
            continue
        need = str((master.get(code) or {}).get("fabric_type_required") or "").strip().lower()
        if not need:
            continue
        fabric = str(p.get("fabric_type") or "").strip().lower()
        if fabric and fabric != need:
            bad.append(f"products {p.get('sku') or p.get('id')}: lini '{code}' hanya untuk "
                       f"kain {need}, tetapi fabric_type='{fabric}' (INV-LINE-02)")
    return bad


# ═════════════════════════ ADAPTER BASIS DATA ═══════════════════════════════
async def run_runtime(guard: Guard) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=4000)
    db = client[os.environ.get("DB_NAME", "test_database")]
    await db.command("ping")

    master_rows = await db.product_lines.find({}, {"_id": 0}).to_list(500)
    master = {str(r.get("code") or "").strip().lower(): r for r in master_rows}
    valid = set(master)
    if not valid:
        print(f"{Y}[SKIP]{X} master `product_lines` masih kosong — jalankan "
              "`python scripts/migrate_lini_produk.py` lebih dulu.")
        return

    products = await db.products.find(
        {}, {"_id": 0, "id": 1, "sku": 1, "line_code": 1, "fabric_type": 1}).to_list(5000)
    prod_line = {p["id"]: str(p.get("line_code") or "").strip().lower() for p in products}

    # R1 — kode asing di produk, akun, dokumen ber-items, dokumen ber-satu-lini
    rows: List[Tuple[str, str, List[str]]] = [
        ("products", p.get("sku") or p["id"], [p.get("line_code")]) for p in products]
    for u in await db.users.find({}, {"_id": 0, "id": 1, "email": 1,
                                      "allowed_line_codes": 1}).to_list(2000):
        rows.append(("users", u.get("email") or u["id"], list(u.get("allowed_line_codes") or [])))
    item_docs: List[Tuple[str, str, Dict[str, Any]]] = []
    for coll in ITEM_COLLECTIONS:
        async for doc in db[coll].find({}, {"_id": 0, "id": 1, "number": 1, "code": 1,
                                            "po_number": 1, "items": 1, "line_codes": 1}):
            ident = doc.get("number") or doc.get("po_number") or doc.get("code") or doc.get("id", "?")
            item_docs.append((coll, ident, doc))
            codes = [str((it or {}).get("line_code") or "") for it in (doc.get("items") or [])
                     if isinstance(it, dict)]
            rows.append((coll, ident, codes + list(doc.get("line_codes") or [])))
    for coll in SINGLE_COLLECTIONS:
        async for doc in db[coll].find({}, {"_id": 0, "id": 1, "number": 1, "roll_no": 1,
                                            "lot_number": 1, "line_code": 1}):
            ident = (doc.get("number") or doc.get("roll_no") or doc.get("lot_number")
                     or doc.get("id", "?"))
            rows.append((coll, ident, [doc.get("line_code")]))
    guard.bump(len(rows))
    for v in check_unknown_codes(rows, valid):
        guard.add(v)

    # R2 & R3
    guard.bump(len(item_docs) * 2)
    for v in check_derived(item_docs):
        guard.add(v)
    for v in check_snapshot(item_docs, prod_line):
        guard.add(v)

    # R4 — INV-LINE-02
    guard.bump(len(products))
    for v in check_fabric(products, master):
        guard.add(v)

    print(f"  · master lini: {', '.join(sorted(valid))}")
    print(f"  · diperiksa: {len(products)} produk · {len(item_docs)} dokumen ber-baris · "
          f"{len(rows)} sumber kode lini")


# ═════════════════════════ SELF-TEST (bukti-merah) ══════════════════════════
def self_test() -> int:
    """Penjaga WAJIB bisa memerah untuk pelanggaran buatan — dan HANYA untuk itu."""
    cases: List[Tuple[str, bool]] = []

    def case(label: str, cond: bool) -> None:
        cases.append((label, cond))

    # S1 — statik
    fake_ok = {rel: "from services import line_scope\n" for rel in MUST_USE_LINE_SCOPE}
    case("S1 bersih → 0 pelanggaran", check_static(fake_ok) == [])
    fake_bad = dict(fake_ok)
    fake_bad["routers/products.py"] = "hanya query mongo biasa\n"
    case("S1 memerah bila satu berkas melepas pagar", len(check_static(fake_bad)) == 1)
    fake_missing = dict(fake_ok)
    fake_missing.pop("routers/lots.py")
    case("S1 memerah bila berkas wajib hilang", len(check_static(fake_missing)) == 1)

    valid = {"woven", "knit", "printing"}
    # R1 — kode asing
    case("R1 bersih (kode dikenal + kosong)", check_unknown_codes(
        [("products", "SKU-1", ["woven"]), ("products", "SKU-2", [""]),
         ("users", "a@b.c", [])], valid) == [])
    case("R1 memerah untuk kode asing", len(check_unknown_codes(
        [("products", "SKU-9", ["dnim"])], valid)) == 1)
    case("R1 memerah untuk lini akun yang asing", len(check_unknown_codes(
        [("users", "dewi@kn.id", ["printing", "printng"])], valid)) == 1)

    # R2 — turunan
    ok_doc = {"items": [{"line_code": "woven"}, {"line_code": "printing"}],
              "line_codes": ["printing", "woven"]}
    case("R2 bersih (turunan cocok, urutan tak penting)",
         check_derived([("sales_orders", "SO-1", ok_doc)]) == [])
    case("R2 bersih untuk dokumen tanpa lini sama sekali",
         check_derived([("sales_orders", "SO-2", {"items": [{}], "line_codes": []})]) == [])
    stale = {"items": [{"line_code": "woven"}], "line_codes": ["printing"]}
    case("R2 memerah bila turunan berbohong",
         len(check_derived([("sales_orders", "SO-3", stale)])) == 1)
    missing_head = {"items": [{"line_code": "woven"}]}
    case("R2 memerah bila `line_codes` tidak dihitung",
         len(check_derived([("purchase_orders", "PO-9", missing_head)])) == 1)

    # R3 — snapshot
    prod_line = {"prod_a": "printing", "prod_b": ""}
    case("R3 bersih (baris berlini & produk tanpa lini)", check_snapshot(
        [("sales_orders", "SO-4", {"items": [{"product_id": "prod_a", "line_code": "printing"},
                                             {"product_id": "prod_b"}]})], prod_line) == [])
    case("R3 memerah bila jalur tulis lupa menstempel", len(check_snapshot(
        [("purchase_orders", "PO-5", {"items": [{"product_id": "prod_a"}]})], prod_line)) == 1)

    # R4 — INV-LINE-02
    master = {"woven": {"fabric_type_required": "woven"},
              "knit": {"fabric_type_required": "knit"},
              "printing": {"fabric_type_required": ""}}
    case("R4 bersih (cocok + printing bebas + tanpa lini)", check_fabric(
        [{"sku": "A", "line_code": "woven", "fabric_type": "woven"},
         {"sku": "B", "line_code": "printing", "fabric_type": "knit"},
         {"sku": "C", "line_code": "", "fabric_type": "woven"}], master) == [])
    case("R4 memerah untuk lini knit pada kain woven", len(check_fabric(
        [{"sku": "D", "line_code": "knit", "fabric_type": "woven"}], master)) == 1)
    case("R4 tidak menuduh produk yang fabric_type-nya belum diisi", check_fabric(
        [{"sku": "E", "line_code": "knit", "fabric_type": ""}], master) == [])

    print(f"{B}== SELF-TEST INV-LINE-01/02 (bukti-merah dua arah) =={X}")
    fails = 0
    for label, cond in cases:
        print(f"  {G}[OK]{X} {label}" if cond else f"  {R}[GAGAL]{X} {label}")
        fails += 0 if cond else 1
    if fails:
        print(f"{R}SELF-TEST GAGAL: {fails}/{len(cases)} — penjaga tidak bisa dipercaya.{X}")
        return 1
    print(f"{G}SELF-TEST LULUS: {len(cases)}/{len(cases)} kasus (bersih & pelanggaran).{X}")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    guard = Guard("INV-LINE-01/02", "Pagar lini produk (kode dikenal · turunan jujur · "
                                    "snapshot lengkap · lini vs fisika kain)")
    sources = {rel: (BE / rel).read_text(encoding="utf-8")
               for rel in MUST_USE_LINE_SCOPE if (BE / rel).exists()}
    guard.bump(len(MUST_USE_LINE_SCOPE))
    for v in check_static(sources):
        guard.add(v)
    if os.environ.get("MONGO_URL"):
        try:
            asyncio.run(run_runtime(guard))
        except Exception as exc:  # noqa: BLE001 — DB mati ≠ pelanggaran invarian
            print(f"{Y}[SKIP]{X} bagian runtime dilewati: {type(exc).__name__}: {exc}")
    else:
        print(f"{Y}[SKIP]{X} MONGO_URL tidak tersedia — hanya pemeriksaan statik.")
    return guard.finish()


if __name__ == "__main__":
    raise SystemExit(main())
