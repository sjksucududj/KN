"""FASE E-7 (E7.4 · keputusan pemilik 3a) — **KAS TINGKAT GRUP DIHAPUS**.

## Keadaan sebelum fase ini (terbukti sesi 2026-08-11)
`13 dari 19` `cash_transactions` ber-`entity_id="all"` — termasuk penerimaan piutang
`KSC/AR-0000x` yang jelas-jelas uang PT Kain Suka Cita — plus satu rekening
**“Kas Besar Grup”** (`bank_kas_besar`, `entity_id="all"`). Penyebabnya bukan salah
input: **kodenya sendiri** yang memaksa `entity_id="all"` setiap kali
`cash_type="kas_besar"` (transfer/giro/QRIS) di 5 tempat berbeda.

Akibat nyata: laporan keuangan per PT **tidak utuh**. Uang masuk KSC tidak muncul
di kas KSC, arus kas per PT salah, dan rekonsiliasi bank mencampur dua badan hukum
di satu buku.

## Keputusan pemilik (E7.7 jawaban 3a)
> “Kas/rekening tingkat grup DIHAPUS: setiap uang wajib milik satu entitas.”

Jadi `cash_type` (kas_kecil / kas_besar) tetap dipakai sebagai **jenis buku**
(tunai vs bank) — yang dihapus adalah **kepemilikan grup**. Setiap transaksi kas dan
setiap rekening wajib menyebut satu badan usaha.

Modul ini adalah SATU tempat aturan itu ditegakkan, supaya lima tempat penulisan kas
(kwitansi AR · kontrabon · kasus keuangan · refund retur · entri kas manual) tidak
lagi punya tafsir masing-masing.

Migrasi data lama: `scripts/migrate_e7_group_cash.py --report` lalu `--apply`.
"""
from typing import Any, Dict, Optional

from fastapi import HTTPException

GROUP_SENTINELS = ("all", "", None, "group")

MIGRATION_HINT = (
    "Data lama yang masih tercatat di tingkat grup dipetakan lewat "
    "`python scripts/migrate_e7_group_cash.py --report` (lihat usulan + buktinya) "
    "lalu `--apply`."
)


def is_group_level(entity_id: Any) -> bool:
    """Apakah nilai entitas ini berarti “milik grup” (yang sudah tidak boleh lagi)?"""
    return str(entity_id or "").strip().lower() in ("all", "", "group")


def assert_owned(entity_id: Any, *, what: str = "Transaksi kas") -> str:
    """Pastikan uang ini punya PEMILIK. Mengembalikan entity_id yang sudah bersih.

    Kalimatnya menuntun (bukan galat buntu): orang yang sedang di mode “Semua
    Entitas” hanya perlu memilih badan usahanya dulu.
    """
    eid = str(entity_id or "").strip()
    if is_group_level(eid):
        raise HTTPException(
            status_code=409,
            detail=(f"{what} wajib milik SATU badan usaha — kas tingkat grup sudah "
                    f"dihapus (keputusan pemilik: setiap uang harus punya pemilik, "
                    f"supaya laporan keuangan tiap PT utuh). Pilih badan usaha Anda "
                    f"dulu di pemilih badan usaha (mode “Semua Entitas” hanya untuk "
                    f"melihat), lalu ulangi. {MIGRATION_HINT}"))
    return eid


def resolve_owner(*candidates: Any, what: str = "Transaksi kas") -> str:
    """Ambil pemilik pertama yang sah dari beberapa kandidat (dokumen → konteks)."""
    for c in candidates:
        if not is_group_level(c):
            return str(c).strip()
    return assert_owned(None, what=what)


async def group_cash_pending(db) -> Dict[str, Any]:
    """Berapa banyak sisa data kas tingkat grup — dipakai UI untuk menegur JUJUR.

    Angka ini sengaja dikirim ke layar Kas & Bank: pagar baru hanya mencegah data
    grup BARU; data lama tidak boleh hilang diam-diam, ia harus terlihat sampai
    dipetakan lewat skrip migrasi.
    """
    q = {"entity_id": {"$in": ["all", "", None]}}
    txn = await db.cash_transactions.count_documents({**q, "status": {"$ne": "void"}})
    acc = await db.bank_accounts.count_documents(q)
    amount = 0.0
    if txn:
        async for r in db.cash_transactions.find(
                {**q, "status": {"$ne": "void"}}, {"_id": 0, "amount": 1, "direction": 1}):
            amount += float(r.get("amount") or 0) * (1 if r.get("direction") == "in" else -1)
    return {
        "transactions": txn,
        "accounts": acc,
        "net_amount": round(amount, 2),
        "hint": MIGRATION_HINT if (txn or acc) else "",
    }


def stamp_source_entity(doc: Dict[str, Any], source_entity_id: Optional[str]) -> Dict[str, Any]:
    """Simpan entitas ASAL dokumen (jejak, bukan pengganti `entity_id`)."""
    if source_entity_id and not is_group_level(source_entity_id):
        doc["source_entity_id"] = str(source_entity_id).strip()
    return doc
