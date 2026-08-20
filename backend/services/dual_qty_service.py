"""FASE U — DUA SATUAN (jumlah roll + ukuran) · satu pintu untuk semua dokumen.

Permintaan pemilik: *"catat roll dan yard/kg dan panel — jadi ada 2 satuan yang
ditulis... dan ini seharusnya sudah ada di semuanya, di WMS, di sales, di SO dll."*

BENTUK DATA (sengaja hanya SATU field baru — bukan field kembar)
===============================================================
Setiap baris dokumen yang menyebut jumlah kain mendapat `qty_rolls: int | None`.
Angka kedua memakai field yang SUDAH ada (`quantity` + `unit`). Jadi tidak ada dua
tempat menyimpan "berapa yard" — kelas bug termahal di repo ini (§1 rencana).

  * `qty_rolls = None`  → baris/dokumen ini tidak menyebut jumlah roll (dokumen LAMA).
    Di layar WAJIB tampil **"—"**, bukan "0 roll" (0 roll berarti "tidak ada gulungan").
  * `qty_rolls = 0`     → memang nol gulungan (mis. sisa potongan tanpa roll utuh).

DARI MANA ANGKANYA (§U.D rencana — dihitung, bukan diketik, kecuali rencana)
===========================================================================
  PO · PR · RFQ · SO       : DIKETIK (saat memesan, jumlah roll memang perkiraan)
  penerimaan (`wms_tasks`) : DIHITUNG dari roll yang benar-benar dibuat
  PO `items[].received_rolls`: turunan (akumulasi dari penerimaan)
  pengiriman/retur         : DIHITUNG dari roll yang dipilih (`roll_ids`/alokasi)
  makloon `steps[]`        : roll masuk/keluar per langkah

FAKTOR PER DOKUMEN (keputusan pemilik 2026-08-19)
=================================================
"Panjang 1 PANEL berbeda per pesanan" → baris dokumen boleh membawa
`unit_factor` + `unit_factor_to` (mis. 1 panel = 1,6 yard). Supaya ini TIDAK menjadi
pintu ke-3 untuk konversi satuan, hak itu datang dari MASTER: hanya satuan yang
ber-`uoms.factor_per_document = true` yang boleh dibawa per baris. Satuan lain →
ditolak 400 dengan kalimat yang menuntun ke Master Data → UOM.
"""
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from db import db
from services import uom_service


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


async def assert_line_factor_allowed(unit: str, factor: Optional[float],
                                     factor_to: str = "") -> None:
    """Pagar faktor per dokumen (400 bila satuannya tidak berhak membawa faktor)."""
    if factor in (None, "", 0):
        return
    vocab = await uom_service.load_vocab()
    row = vocab.get(str(unit or "").strip().lower())
    if not row:
        raise HTTPException(
            status_code=400,
            detail=(f"Satuan “{unit}” tidak dikenal master satuan, jadi faktor per "
                    f"dokumen tidak bisa dipakai. Tambahkan satuannya di "
                    f"Master Data → UOM lebih dulu."))
    if not bool(row.get("factor_per_document")):
        raise HTTPException(
            status_code=400,
            detail=(f"Satuan {row.get('code')} tidak mengizinkan faktor per dokumen. "
                    f"Faktor tetap milik master (Master Data → UOM) atau konversi per "
                    f"produk; hanya satuan bertanda “faktor per dokumen” (mis. PANEL) "
                    f"yang boleh membawa faktornya sendiri di baris dokumen."))
    if factor_to:
        if str(factor_to).strip().lower() not in vocab:
            raise HTTPException(
                status_code=400,
                detail=(f"Satuan tujuan faktor “{factor_to}” tidak ada di master satuan."))


async def stamp(item_in: Any, *, rolls: Optional[int] = None) -> Dict[str, Any]:
    """Stempel dua satuan untuk SATU baris dokumen.

    `rolls` diisi pemanggil bila angkanya DIHITUNG (penerimaan/pengiriman/retur);
    kalau tidak, dipakai nilai yang diketik pengguna. Kunci `qty_rolls` SELALU
    ditulis (boleh `None`) supaya baris baru tidak pernah "tidak punya kolom" —
    dokumen lama tetap dibedakan karena fieldnya memang tidak ada di sana.
    """
    unit = str(_get(item_in, "unit", "") or "")
    factor = _get(item_in, "unit_factor")
    factor_to = str(_get(item_in, "unit_factor_to", "") or "")
    await assert_line_factor_allowed(unit, factor, factor_to)
    out: Dict[str, Any] = {}
    if rolls is not None:
        out["qty_rolls"] = int(rolls)
    else:
        raw = _get(item_in, "qty_rolls")
        out["qty_rolls"] = None if raw in (None, "") else int(raw)
    if factor not in (None, "", 0):
        out["unit_factor"] = float(factor)
        out["unit_factor_to"] = factor_to or unit
    return out


def measure_equivalent(line: Dict[str, Any], to_unit: str = "") -> Optional[float]:
    """Ukuran baris dalam satuan `unit_factor_to` (mis. panel → yard). None bila tak ada.

    Dipakai layar/PDF untuk menjawab "12 panel itu berapa yard **pada pesanan ini**"
    tanpa menebak: faktornya tertulis di barisnya sendiri.
    """
    f = line.get("unit_factor")
    if not f:
        return None
    target = (line.get("unit_factor_to") or "").strip().lower()
    if to_unit and target and target != str(to_unit).strip().lower():
        return None
    try:
        qty = float(line.get("quantity") or line.get("qty") or 0)
        return round(qty * float(f), 4)
    except (TypeError, ValueError):
        return None


async def rolls_of_ids(roll_ids: Optional[List[str]]) -> Optional[int]:
    """Jumlah roll dari daftar id yang BENAR-BENAR ada (bukan panjang daftar mentah)."""
    ids = [str(x) for x in (roll_ids or []) if x]
    if not ids:
        return None
    return await db.inventory_rolls.count_documents({"id": {"$in": ids}})


async def rolls_of_order_line(order_id: str, product_id: str) -> Optional[int]:
    """Jumlah roll yang teralokasi/terkirim untuk satu baris pesanan (turunan)."""
    if not order_id or not product_id:
        return None
    n = await db.inventory_rolls.count_documents(
        {"product_id": product_id,
         "$or": [{"reserved_ref.order_id": order_id}, {"reserved_ref.id": order_id},
                 {"earmarked_for": order_id}]})
    return n or None


# ═════════════════════════════════════════════════════════════════════════════
# BACKFILL — satu implementasi dipakai DUA pemanggil
# (`scripts/migrate_qty_rolls.py` untuk basis data lama · `seed_realistic.py`
#  untuk data demo). Kalau dua pemanggil punya salinan aturannya sendiri, angka
# demo dan angka produksi akan menyimpang tanpa ada yang tahu — kelas bug yang
# sama dengan dua daftar benih satuan (K1) yang baru ditutup di fase ini.
# ═════════════════════════════════════════════════════════════════════════════
import math  # noqa: E402


async def _avg_roll_len(dbx, product_id: str) -> float:
    """Panjang roll RATA-RATA nyata untuk satu produk (0 bila belum ada roll)."""
    rows = await dbx.inventory_rolls.find(
        {"product_id": product_id, "length_initial": {"$gt": 0}},
        {"_id": 0, "length_initial": 1}).to_list(500)
    if not rows:
        return 0.0
    vals = [float(r.get("length_initial") or 0) for r in rows]
    return round(sum(vals) / len(vals), 4) if vals else 0.0


async def backfill(dbx, *, demo_plan: bool = False, dry_run: bool = False) -> Dict[str, int]:
    """Isi `qty_rolls` (dan `secondary_measures`) DARI ROLL NYATA — bukan menebak.

    Aturan (dan alasan tiap aturan):
      * `inventory_movements` : baris yang menunjuk satu `roll_id` = **1 roll**.
      * `wms_tasks`           : jumlah roll yang lahir dari tugas itu (`grn_task_id`).
      * `purchase_orders`     : `items[].received_rolls` = roll nyata ber-`po_id` + produk.
      * retur (jual/beli/antar-PT) : dari `roll_ids` yang memang dipilih.
      * `warehouse_transfers` : dari daftar `rolls[]` yang direservasi.
      * `shipments`           : dari daftar `rolls[]` yang keluar gudang.
      * `makloon_orders`      : `steps[].qty_rolls_out` dari `lots[]` hasil terima.
      * `inventory_rolls`     : `secondary_measures.kg` dari `weight_kg` yang sudah ada.
      * `demo_plan=True` (HANYA untuk data demo): baris RENCANA (PO/PR/SO/RFQ/antar-PT/
        permintaan internal) diberi perkiraan jumlah roll dari panjang roll RATA-RATA
        NYATA produk itu (dibulatkan ke atas, minimal 1). Ini sengaja **tidak** dipakai
        pada basis data sungguhan: menebak rencana orang lain lebih berbahaya daripada
        membiarkan kolomnya "—".
    """
    stat: Dict[str, int] = {}

    def bump(k: str, n: int = 1):
        if n:
            stat[k] = stat.get(k, 0) + n

    # 1. mutasi — satu baris = satu roll
    q = {"roll_id": {"$nin": ["", None]}, "qty_rolls": {"$exists": False}}
    n = await dbx.inventory_movements.count_documents(q)
    if n and not dry_run:
        await dbx.inventory_movements.update_many(q, {"$set": {"qty_rolls": 1}})
    bump("inventory_movements", n)

    # 2. tugas gudang — roll yang benar-benar lahir dari tugas penerimaan itu
    async for t in dbx.wms_tasks.find({"qty_rolls": {"$in": [None, ""]}},
                                      {"_id": 0, "id": 1}):
        cnt = await dbx.inventory_rolls.count_documents({"grn_task_id": t["id"]})
        if cnt:
            if not dry_run:
                await dbx.wms_tasks.update_one({"id": t["id"]},
                                               {"$set": {"qty_rolls": cnt}})
            bump("wms_tasks")

    # 3. PO — received_rolls (turunan) + (demo) rencana qty_rolls
    async for po in dbx.purchase_orders.find({}, {"_id": 0, "id": 1, "items": 1}):
        upd: Dict[str, Any] = {}
        for i, it in enumerate(po.get("items") or []):
            pid = it.get("product_id")
            if it.get("received_rolls") in (None, "") and pid:
                cnt = await dbx.inventory_rolls.count_documents(
                    {"po_id": po["id"], "product_id": pid})
                if cnt:
                    upd[f"items.{i}.received_rolls"] = cnt
            if demo_plan and it.get("qty_rolls") in (None, "") and pid:
                avg = await _avg_roll_len(dbx, pid)
                if avg > 0:
                    upd[f"items.{i}.qty_rolls"] = max(
                        1, math.ceil(float(it.get("quantity") or 0) / avg))
        if upd:
            if not dry_run:
                await dbx.purchase_orders.update_one({"id": po["id"]}, {"$set": upd})
            bump("purchase_orders", len(upd))

    # 4. retur & dokumen ber-`roll_ids`/`rolls[]`
    for coll, src_field in (("sales_returns", "roll_ids"),
                            ("purchase_returns", "roll_ids"),
                            ("interco_returns", "roll_ids"),
                            ("warehouse_transfers", "rolls")):
        async for doc in dbx[coll].find({}, {"_id": 0, "id": 1, "items": 1}):
            upd: Dict[str, Any] = {}
            for i, it in enumerate(doc.get("items") or []):
                if it.get("qty_rolls") not in (None, ""):
                    continue
                raw = it.get(src_field) or []
                cnt = len([x for x in raw if x])
                if cnt:
                    upd[f"items.{i}.qty_rolls"] = cnt
            if upd:
                if not dry_run:
                    await dbx[coll].update_one({"id": doc["id"]}, {"$set": upd})
                bump(coll, len(upd))

    # 5. surat jalan — roll yang keluar gudang. Data lama/demo bisa tidak menyimpan
    #    daftar `rolls[]`; dalam mode DEMO angkanya diperkirakan dari panjang roll
    #    rata-rata NYATA produk itu (di basis data sungguhan sengaja dibiarkan "—").
    async for sh in dbx.shipments.find({"qty_rolls": {"$in": [None, ""]}},
                                       {"_id": 0, "id": 1, "rolls": 1, "qty": 1,
                                        "product_id": 1}):
        cnt = len([r for r in (sh.get("rolls") or []) if r])
        if not cnt and demo_plan and sh.get("product_id"):
            avg = await _avg_roll_len(dbx, sh["product_id"])
            qty = float(sh.get("qty") or 0)
            if avg > 0 and qty > 0:
                cnt = max(1, math.ceil(qty / avg))
        if cnt:
            if not dry_run:
                await dbx.shipments.update_one({"id": sh["id"]},
                                               {"$set": {"qty_rolls": cnt}})
            bump("shipments")

    # 6. SPK makloon — roll hasil per langkah
    async for mk in dbx.makloon_orders.find({}, {"_id": 0, "id": 1, "steps": 1}):
        upd: Dict[str, Any] = {}
        for i, st in enumerate(mk.get("steps") or []):
            if st.get("qty_rolls_out") in (None, ""):
                cnt = len([x for x in (st.get("lots") or []) if x])
                if cnt:
                    upd[f"steps.{i}.qty_rolls_out"] = cnt
            if demo_plan and st.get("qty_rolls") in (None, ""):
                pid = st.get("input_product_id")
                avg = await _avg_roll_len(dbx, pid) if pid else 0.0
                if avg > 0:
                    upd[f"steps.{i}.qty_rolls"] = max(
                        1, math.ceil(float(st.get("input_qty") or 0) / avg))
        if upd:
            if not dry_run:
                await dbx.makloon_orders.update_one({"id": mk["id"]}, {"$set": upd})
            bump("makloon_orders", len(upd))

    # 7. roll — ukuran kedua (kg) dari berat yang SUDAH tercatat
    async for r in dbx.inventory_rolls.find(
            {"weight_kg": {"$gt": 0}, "secondary_measures": {"$in": [None, {}]}},
            {"_id": 0, "id": 1, "weight_kg": 1}):
        if not dry_run:
            await dbx.inventory_rolls.update_one(
                {"id": r["id"]},
                {"$set": {"secondary_measures": {"kg": round(float(r["weight_kg"]), 3)}}})
        bump("inventory_rolls")

    # 8. (DEMO saja) baris RENCANA lain
    if demo_plan:
        for coll in ("sales_orders", "purchase_requisitions", "rfqs",
                     "interco_transactions", "internal_requests"):
            async for doc in dbx[coll].find({}, {"_id": 0, "id": 1, "items": 1}):
                upd: Dict[str, Any] = {}
                for i, it in enumerate(doc.get("items") or []):
                    if it.get("qty_rolls") not in (None, ""):
                        continue
                    pid = it.get("product_id")
                    avg = await _avg_roll_len(dbx, pid) if pid else 0.0
                    qty = float(it.get("quantity") or it.get("qty") or 0)
                    if avg > 0 and qty > 0:
                        upd[f"items.{i}.qty_rolls"] = max(1, math.ceil(qty / avg))
                if upd:
                    if not dry_run:
                        await dbx[coll].update_one({"id": doc["id"]}, {"$set": upd})
                    bump(coll, len(upd))
    return stat
