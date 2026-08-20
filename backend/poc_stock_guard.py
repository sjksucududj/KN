"""poc_stock_guard — pulihkan STOK setelah POC fase (menutup **POC-RESIDU-01**).

MASALAH NYATA (terukur 2026-07-29, ditemukan checkpoint residu FASE POC yang baru):
satu `bash scripts/gate.sh --full` dari seed bersih meninggalkan

    inventory_rolls                     53 → 75   (+22 roll)
    prod_batik_mega|wh_jakarta.reserved 50 → 173
    prod_batik_mega|wh_jakarta.available 435 → 307
    prod_batik_mega|wh_bandung.reserved  20 → 109

Akibat yang dilihat pemakai: **stok tersedia menyusut** dan muncul roll-roll
potongan tak bertuan setiap kali gate dijalankan.

AKAR MASALAH: POC G-0/G-1/G-2/G-3 mengonfirmasi Sales Order sungguhan. Konfirmasi
SO mengalokasikan roll dan **memotong** roll bila qty tidak bulat (roll cut
MELAHIRKAN roll baru). Cleanup POC lalu menghapus SO **langsung dari MongoDB**,
sehingga:
  * reservasi pada roll tidak pernah dilepas (`status` tetap reserved/committed);
  * roll hasil potongan tidak pernah digabung ulang;
  * `inventory_balances` (proyeksi dari roll) ikut bergeser permanen.

KENAPA RESTORE, BUKAN "HAPUS YANG BARU": memotong roll bukan operasi yang bisa
dibalik per-dokumen (satu roll jadi dua, nomor & sisa berubah). Satu-satunya
pemulihan yang EKSAK adalah snapshot sebelum uji lalu restore sesudahnya —
pola yang sudah dipakai `scripts/guardrails/_common.py::DbSnapshot` untuk
guardrail runtime. Modul ini memakai pola yang sama, tetapi hanya untuk koleksi
STOK supaya POC tetap bebas membuat dokumen lain.

PENGAMAN: hanya berjalan bila `DB_NAME` mengandung `test`/`demo`/`dev`, atau
`KN_GATE_ALLOW_RESTORE=1`. Jadi tidak mungkin menyentuh basis data produksi.
Set `KN_GATE_NO_RESTORE=1` untuk MENGUKUR kebocoran (restore dimatikan).

Pemakaian di POC:

    from poc_stock_guard import snapshot_stock, restore_stock

    _STOCK = snapshot_stock()          # sebelum POC menulis apa pun
    ...
    restore_stock(_STOCK)             # di bagian CLEANUP, setelah dokumen POC dihapus
"""
import os
from typing import Any, Dict, List, Optional

G, Y, R, X = "\033[92m", "\033[93m", "\033[91m", "\033[0m"

# POC dijalankan sebagai skrip lepas (lewat HTTP), jadi env belum tentu memuat
# backend/.env. Muat di sini supaya nama DB yang dipakai SAMA dengan backend —
# kalau tidak, pengaman "hanya DB uji" salah menolak dan restore tak pernah jalan
# (pernah terjadi: DB_NAME='' → restore DIMATIKAN, residu tetap ada).
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:  # noqa: BLE001 — dotenv opsional
    pass


def _db_name() -> str:
    return (os.environ.get("DB_NAME") or "test_database").strip('"')


# Hanya koleksi STOK. Dokumen bisnis (SO/PO/jurnal/…) tetap tanggung jawab
# cleanup masing-masing POC supaya kesalahan cleanup tidak tersembunyi.
STOCK_COLLECTIONS = ["inventory_rolls", "inventory_balances", "inventory_movements",
                     "inventory_lots"]


def _restore_allowed() -> bool:
    if os.environ.get("KN_GATE_NO_RESTORE") == "1":
        print(f"{Y}  [poc-stock] KN_GATE_NO_RESTORE=1 — restore stok DIMATIKAN "
              f"(mode ukur kebocoran).{X}")
        return False
    if os.environ.get("KN_GATE_ALLOW_RESTORE") == "1":
        return True
    name = _db_name().lower()
    if any(tag in name for tag in ("test", "demo", "dev")):
        return True
    print(f"{Y}  [poc-stock] DB_NAME='{name}' bukan basis data uji — restore stok "
          f"DIMATIKAN (set KN_GATE_ALLOW_RESTORE=1 bila memang disengaja).{X}")
    return False


def _db():
    from pymongo import MongoClient
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017").strip('"')
    return MongoClient(url, serverSelectionTimeoutMS=5000)[_db_name()]


def snapshot_stock(collections: Optional[List[str]] = None) -> Dict[str, Any]:
    """Simpan isi koleksi stok apa adanya (termasuk `_id`) agar restore EKSAK."""
    cols = collections or STOCK_COLLECTIONS
    snap: Dict[str, Any] = {"__enabled__": _restore_allowed(), "data": {}}
    if not snap["__enabled__"]:
        return snap
    try:
        db = _db()
        for c in cols:
            snap["data"][c] = list(db[c].find({}))
        total = sum(len(v) for v in snap["data"].values())
        print(f"  [poc-stock] snapshot {total} dokumen stok dari {len(cols)} koleksi "
              f"— akan dipulihkan di CLEANUP.")
    except Exception as exc:  # noqa: BLE001
        print(f"{Y}  [poc-stock] snapshot GAGAL ({exc}) — restore dilewati.{X}")
        snap["__enabled__"] = False
    return snap


def restore_stock(snap: Optional[Dict[str, Any]]) -> bool:
    """Pulihkan koleksi stok ke keadaan snapshot. Return True bila benar-benar pulih."""
    if not snap or not snap.get("__enabled__") or not snap.get("data"):
        return False
    try:
        db = _db()
        for c, docs in snap["data"].items():
            db[c].delete_many({})
            if docs:
                db[c].insert_many(docs, ordered=False)
        total = sum(len(v) for v in snap["data"].values())
        print(f"  {G}[poc-stock] stok dipulihkan EKSAK ({total} dokumen, "
              f"{len(snap['data'])} koleksi) — nol residu roll & saldo.{X}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"{R}  [poc-stock] restore GAGAL: {exc}{X}")
        return False
