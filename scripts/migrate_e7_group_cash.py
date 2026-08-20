#!/usr/bin/env python3
"""FASE E-7 (E7e · keputusan pemilik 3a) — **MIGRASI KAS TINGKAT GRUP → PER BADAN USAHA**.

Keputusan pemilik: *“Kas/rekening tingkat grup DIHAPUS: setiap uang wajib milik satu
entitas.”* Kodenya sudah dipagari (`services/cash_entity_service`), tetapi data LAMA
tidak boleh dipindah dengan tebakan — uang adalah angka yang dipakai pemilik untuk
mengambil keputusan.

Karena itu skrip ini **dua tahap**:

    python scripts/migrate_e7_group_cash.py --report     # usulan + BUKTI per baris, tanpa menulis
    python scripts/migrate_e7_group_cash.py --apply      # baru menulis

Bukti pemetaan dicari berlapis (yang paling kuat dulu):

  1. `ref_type`/`ref_id` → dokumen aslinya (kwitansi AR, kontrabon, tagihan supplier,
     kasus keuangan, retur) → `entity_id` dokumen itu;
  2. `source_entity_id` (sudah pernah ditulis beberapa jalur sebagai jejak);
  3. **prefix nomor dokumen** yang tertulis di uraian (mis. “Penerimaan KSC/AR-00003”)
     → badan usaha ber-`doc_prefix` KSC;
  4. `account_id` → rekening yang sudah punya badan usaha.

Baris yang **tidak bisa dibuktikan** TIDAK dipindah diam-diam: ia dibuatkan **kasus di
Pusat Kasus Keuangan** (`case_type="salah_entitas"`) supaya ada orang yang memutuskan,
dan ditandai `needs_entity_mapping=True` agar tetap terlihat.

Rekening tingkat grup (mis. “Kas Besar Grup”): dibuatkan **cermin per badan usaha**
(`<nama> — <ENT>`), transaksinya dipindah ke cermin masing-masing, lalu rekening grup
dinonaktifkan (`is_active=False`, `retired_by="E7e"`) — TIDAK dihapus, karena riwayat
rekonsiliasi bank menunjuk id-nya.
"""
import argparse
import asyncio
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

GROUP_VALUES = ["all", "", None]
REF_COLLECTIONS = {
    "ar_receipt": "ar_receipts",
    "ar_refund": "ar_receipts",
    "vendor_bill": "vendor_bills",
    "contra_bon": "contra_bons",
    "finance_case": "finance_cases",
    "sales_return": "sales_returns",
    "purchase_return": "purchase_returns",
    "cash_advance": "cash_advances",
    "cash_advance_settlement": "cash_advance_settlements",
    "interco_settlement": "interco_settlements",
    "payment_plan": "payment_plans",
}

GREEN, RED, YEL, DIM, RST = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[0m"


def _fmt(n: float) -> str:
    return f"Rp {n:,.0f}".replace(",", ".")


async def _entities(db) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    rows = await db.business_entities.find({}, {"_id": 0}).to_list(200)
    by_id = {r["id"]: r for r in rows}
    by_prefix = {str(r.get("doc_prefix") or "").upper(): r["id"] for r in rows if r.get("doc_prefix")}
    return by_id, by_prefix


async def _owner_of(db, txn: Dict[str, Any], by_prefix: Dict[str, str]) -> Dict[str, Any]:
    """Pemilik uang + bukti kenapa. `entity_id=""` berarti tidak terbukti."""
    ref_type = (txn.get("ref_type") or "").strip()
    ref_id = (txn.get("ref_id") or "").strip()
    coll = REF_COLLECTIONS.get(ref_type)
    if coll and ref_id:
        doc = await db[coll].find_one({"id": ref_id}, {"_id": 0, "entity_id": 1, "number": 1})
        ent = (doc or {}).get("entity_id") or ""
        if ent and ent not in GROUP_VALUES:
            return {"entity_id": ent, "evidence": f"{ref_type} {(doc or {}).get('number') or ref_id} milik {ent}"}

    src = (txn.get("source_entity_id") or txn.get("owner_entity_id") or "").strip()
    if src and src not in GROUP_VALUES:
        return {"entity_id": src, "evidence": f"jejak source_entity_id={src}"}

    text = f"{txn.get('description', '')} {txn.get('notes', '')}"
    m = re.search(r"\b([A-Z][A-Z0-9]{1,9})/", text)
    if m and m.group(1).upper() in by_prefix:
        pref = m.group(1).upper()
        return {"entity_id": by_prefix[pref], "evidence": f"nomor dokumen ber-prefix {pref} di uraian"}

    acc_id = (txn.get("account_id") or "").strip()
    if acc_id:
        acc = await db.bank_accounts.find_one({"id": acc_id}, {"_id": 0, "entity_id": 1, "name": 1})
        ent = (acc or {}).get("entity_id") or ""
        if ent and ent not in GROUP_VALUES:
            return {"entity_id": ent, "evidence": f"rekening {(acc or {}).get('name') or acc_id} milik {ent}"}

    return {"entity_id": "", "evidence": "tidak ada bukti pemilik (butuh keputusan orang)"}


async def _mirror_account(db, acc: Dict[str, Any], entity_id: str, apply: bool,
                          by_id: Dict[str, Dict[str, Any]]) -> str:
    """Cermin rekening grup untuk satu badan usaha (idempotent)."""
    short = (by_id.get(entity_id) or {}).get("short_name") or entity_id.replace("ent_", "").upper()
    mirror_id = f"{acc['id']}_{entity_id.replace('ent_', '')}"
    existing = await db.bank_accounts.find_one({"id": mirror_id}, {"_id": 0, "id": 1})
    if existing:
        return mirror_id
    doc = {
        **{k: v for k, v in acc.items() if k not in ("id", "_id")},
        "id": mirror_id,
        "name": f"{acc.get('name', 'Kas')} — {short}",
        "entity_id": entity_id,
        "opening_balance": 0.0,           # saldo awal tetap di rekening lama (jejak)
        "note": (f"Dibuat migrasi E7e dari rekening tingkat grup "
                 f"“{acc.get('name', '')}” ({acc['id']}). Saldo awal tidak dipindah."),
        "is_active": True,
        "migrated_from": acc["id"],
    }
    if apply:
        await db.bank_accounts.insert_one(doc)
    return mirror_id


async def main() -> int:
    ap = argparse.ArgumentParser(description="Migrasi kas tingkat grup → per badan usaha (E7e)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--report", action="store_true", help="tampilkan usulan + bukti, TANPA menulis")
    g.add_argument("--apply", action="store_true", help="terapkan pemetaan")
    args = ap.parse_args()
    apply = bool(args.apply)

    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "test_database")]
    by_id, by_prefix = await _entities(db)

    print(f"\n{'='*78}\n  MIGRASI E7e — KAS TINGKAT GRUP → PER BADAN USAHA "
          f"({'TERAPKAN' if apply else 'LAPORAN SAJA'})\n{'='*78}")

    txns = await db.cash_transactions.find(
        {"entity_id": {"$in": GROUP_VALUES}}, {"_id": 0}).sort("txn_date", 1).to_list(5000)
    accs = await db.bank_accounts.find({"entity_id": {"$in": GROUP_VALUES}}, {"_id": 0}).to_list(200)

    if not txns and not accs:
        print(f"{GREEN}  ✓ Tidak ada kas tingkat grup. Tidak ada yang perlu dimigrasikan.{RST}\n")
        client.close()
        return 0

    print(f"\n  Transaksi kas tingkat grup : {len(txns)}")
    print(f"  Rekening tingkat grup      : {len(accs)}"
          + (f"  → {', '.join(a.get('name', a['id']) for a in accs)}" if accs else ""))

    mapped: List[Dict[str, Any]] = []
    unmapped: List[Dict[str, Any]] = []
    for t in txns:
        res = await _owner_of(db, t, by_prefix)
        row = {**t, "_owner": res["entity_id"], "_evidence": res["evidence"]}
        (mapped if res["entity_id"] else unmapped).append(row)

    # ── BARIS YANG PERLU DIPINDAH REKENINGNYA SAJA ──────────────────────────
    # Ditemukan POC F-1b (2026-08-15): baris yang pemiliknya sudah DIPUTUSKAN ORANG
    # lewat kasus keuangan `salah_entitas` mendapat `entity_id` yang benar, tetapi
    # `account_id`-nya MASIH menunjuk rekening tingkat grup. Akibatnya rekening grup
    # selamanya "masih dipakai" sehingga tak pernah bisa dinonaktifkan, dan uang yang
    # sudah punya pemilik tetap duduk di rekening yang konsepnya sudah dihapus.
    # Sapuan kedua ini menutupnya: pemiliknya tidak ditebak lagi (sudah pasti),
    # yang dipindah hanya rekeningnya ke CERMIN badan usaha itu.
    repoint: List[Dict[str, Any]] = []
    if accs:
        repoint = await db.cash_transactions.find(
            {"account_id": {"$in": [a["id"] for a in accs]},
             "entity_id": {"$nin": GROUP_VALUES}}, {"_id": 0}).to_list(5000)

    print(f"\n{'-'*78}\n  USULAN PEMETAAN (bukti per baris)\n{'-'*78}")
    print(f"  {'NOMOR':<14}{'TANGGAL':<12}{'ARAH':<5}{'NOMINAL':>16}  PEMILIK      BUKTI")
    for r in mapped:
        short = (by_id.get(r["_owner"]) or {}).get("short_name") or r["_owner"]
        print(f"  {r.get('number', ''):<14}{str(r.get('txn_date', ''))[:10]:<12}"
              f"{r.get('direction', ''):<5}{_fmt(float(r.get('amount') or 0)):>16}  "
              f"{GREEN}{short:<12}{RST} {DIM}{r['_evidence']}{RST}")
    for r in unmapped:
        print(f"  {r.get('number', ''):<14}{str(r.get('txn_date', ''))[:10]:<12}"
              f"{r.get('direction', ''):<5}{_fmt(float(r.get('amount') or 0)):>16}  "
              f"{RED}{'?':<12}{RST} {YEL}{r['_evidence']}{RST}")

    print(f"\n  Terbukti pemiliknya : {GREEN}{len(mapped)}{RST}")
    print(f"  Belum terbukti      : {RED if unmapped else GREEN}{len(unmapped)}{RST}"
          + ("  → akan dibuatkan KASUS di Pusat Kasus Keuangan" if unmapped else ""))
    if repoint:
        print(f"  Pemilik sudah pasti, rekeningnya masih grup : {YEL}{len(repoint)}{RST}"
              f"  → dipindah ke cermin rekening badan usahanya")

    if not apply:
        print(f"\n{YEL}  Ini LAPORAN saja — belum ada yang ditulis. Jalankan ulang dengan "
              f"--apply bila usulan di atas sudah benar.{RST}\n")
        client.close()
        return 0

    # ── TERAPKAN ────────────────────────────────────────────────────────────
    acc_by_id = {a["id"]: a for a in accs}
    moved = 0
    for r in mapped:
        upd: Dict[str, Any] = {"entity_id": r["_owner"],
                               "migrated_by": "E7e",
                               "migration_evidence": r["_evidence"]}
        acc_id = (r.get("account_id") or "").strip()
        if acc_id in acc_by_id:
            upd["account_id"] = await _mirror_account(db, acc_by_id[acc_id], r["_owner"],
                                                      True, by_id)
            upd["migrated_from_account_id"] = acc_id
        await db.cash_transactions.update_one({"id": r["id"]}, {"$set": upd})
        moved += 1

    # Sapuan kedua: pemilik sudah pasti, hanya rekeningnya yang masih tingkat grup.
    repointed = 0
    for r in repoint:
        acc_id = (r.get("account_id") or "").strip()
        ent = (r.get("entity_id") or "").strip()
        if acc_id not in acc_by_id or not ent:
            continue
        mirror = await _mirror_account(db, acc_by_id[acc_id], ent, True, by_id)
        await db.cash_transactions.update_one({"id": r["id"]}, {"$set": {
            "account_id": mirror, "migrated_from_account_id": acc_id,
            "migrated_by": "E7e",
            "migration_evidence": (r.get("migration_note")
                                   or "pemilik sudah ditetapkan; rekening dipindah ke cermin")}})
        repointed += 1

    cases = 0
    for r in unmapped:
        await db.cash_transactions.update_one({"id": r["id"]}, {"$set": {
            "needs_entity_mapping": True, "migration_note": r["_evidence"]}})
        try:
            from services import finance_case_service as fcs
            existing = await db.finance_cases.find_one(
                {"source.id": r["id"], "case_type": "salah_entitas"}, {"_id": 0, "id": 1})
            if existing:
                continue
            await fcs.create_case({
                "case_type": "salah_entitas",
                "title": f"Kas tanpa pemilik badan usaha: {r.get('number', '')}",
                "description": (
                    f"Migrasi E7e tidak bisa membuktikan uang ini milik badan usaha mana "
                    f"({r['_evidence']}). Uraian: {r.get('description', '')}. "
                    f"Tentukan pemiliknya, lalu perbaiki `entity_id` transaksi ini."),
                "amount": float(r.get("amount") or 0),
                "entity_id": "",
                "source": {"type": "cash_transaction", "id": r["id"],
                           "number": r.get("number", "")},
            }, {"id": "system", "name": "Migrasi E7e", "role": "admin"}, active_entity="")
            cases += 1
        except Exception as exc:  # noqa: BLE001
            print(f"{YEL}  [warn] kasus keuangan untuk {r.get('number')} gagal dibuat: {exc}{RST}")

    retired = 0
    for a in accs:
        left = await db.cash_transactions.count_documents(
            {"account_id": a["id"], "status": {"$ne": "void"}})
        if left == 0:
            await db.bank_accounts.update_one({"id": a["id"]}, {"$set": {
                "is_active": False, "retired_by": "E7e",
                "note": ((a.get("note") or "") +
                         " · Dinonaktifkan migrasi E7e: kas tingkat grup dihapus "
                         "(setiap rekening wajib milik satu badan usaha).").strip()}})
            retired += 1
        else:
            print(f"{YEL}  [info] rekening {a.get('name')} masih dipakai {left} transaksi "
                  f"yang belum terbukti pemiliknya — belum dinonaktifkan.{RST}")

    print(f"\n{'-'*78}\n  HASIL\n{'-'*78}")
    print(f"  Transaksi dipindah ke badan usaha : {GREEN}{moved}{RST}")
    print(f"  Rekening dipindah ke cermin        : {GREEN}{repointed}{RST}"
          f"{DIM}  (pemiliknya sudah pasti sebelumnya){RST}")
    print(f"  Kasus keuangan dibuat             : {cases}")
    print(f"  Rekening grup dinonaktifkan       : {retired} / {len(accs)}")
    sisa = await db.cash_transactions.count_documents(
        {"entity_id": {"$in": GROUP_VALUES}, "status": {"$ne": "void"}})
    print(f"  Sisa transaksi tingkat grup        : "
          f"{GREEN if sisa == 0 else RED}{sisa}{RST}\n")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
