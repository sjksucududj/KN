"""FASE G-6b — **RETUR ANTAR-PT** (jalan resmi setelah barangnya sudah berpindah).

MASALAH NYATA
-------------
G-6 hanya punya **pembatalan**, dan pembatalan sengaja DITOLAK begitu barangnya
benar-benar berpindah lewat tugas gudang ("batalkan lewat retur, bukan pembatalan
dokumen"). Tetapi jalur retur itu belum pernah ada — jadi kalau CV Kanda menerima
kain yang salah warna dari PT KSC, tidak ada dokumen sah untuk mengembalikannya:
barangnya nyangkut di gudang pembeli, utang antar-PT tetap penuh, dan satu-satunya
"jalan keluar" adalah mengedit angka — tepatnya yang dilarang aturan repo #7
(ledger append-only) dan G-1 (tidak ada edit senyap).

DESAIN (mencerminkan G-6, bukan menciptakan pola baru)
------------------------------------------------------
* **Dokumen kembar** juga: satu di PT pembeli (`role="returner"` — nota retur /
  debit note internal) dan satu di PT penjual (`role="receiver"` — nota kredit
  internal), saling menunjuk `return_pair_id` + `refs` ke transaksi asalnya (G-4).
* **Jurnal dipisah persis seperti G-6**: sisi DOKUMEN saat disetujui, sisi BARANG
  saat tugas gudang selesai. Karena itu `1-1310 Persediaan Dalam Perjalanan`
  dipakai lagi (arah berlawanan) dan selalu bersaldo nol setelah barang tiba.
* **Dual-control**: pembuat retur ≠ penyetuju. Retur mengurangi piutang/utang
  nyata, jadi ia mengikuti aturan pemisahan tugas yang sama dengan kontrabon G-7.
* **Nilai buku dipulihkan**: roll yang kembali dinilai ulang ke harga perolehan
  ASLI penjual (tersimpan di `cost_basis.previous_unit_cost` saat barangnya dulu
  berpindah) — tanpa ini GL `1-1300` penjual akan naik sebesar harga jual internal
  dan berselisih abadi dari subledger roll.
* **Dokumen pajak tidak diedit**: bila transaksinya ber-PPN dan fakturnya sudah
  terbit, faktur ditandai **perlu pengganti** (praktik e-Faktur), bukan diubah.

Siklus: `draft → approved → completed` (+ `cancelled`).
Invarian: **INV-IC-08** (di `scripts/verify_data_integrity.py`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core_utils import new_id, next_doc_number, now_iso, rupiah, safe_doc, timeline_entry
from db import db
from services import dual_qty_service as _dual  # FASE U — dua satuan (roll + ukuran)
from services import gl_service
from services import interco_service as ics

EPS = 0.01
COLL = "interco_returns"

STATUSES = ("draft", "approved", "completed", "cancelled")
STATUS_LABEL = {
    "draft": "Draf",
    "approved": "Disetujui",
    "completed": "Barang Sudah Kembali",
    "cancelled": "Dibatalkan",
}
# Status yang IKUT MENGURANGI saldo antar-PT (uangnya sudah berubah).
COUNTED = ("approved", "completed")
# Transaksi asal yang boleh diretur — barangnya sudah berpindah.
RETURNABLE_ORIGIN = ("received", "invoiced", "settled", "returned")


class IntercoReturnError(Exception):
    """Pelanggaran aturan retur antar-PT (→ HTTP 400 di router)."""


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# APA YANG MASIH BISA DIRETUR
# ═══════════════════════════════════════════════════════════════════════════
async def _returned_qty_map(origin_pair_id: str) -> Dict[str, float]:
    """Jumlah per produk yang SUDAH diretur (status disetujui / selesai)."""
    out: Dict[str, float] = {}
    rows = await db[COLL].find(
        {"origin_pair_id": origin_pair_id, "role": "returner",
         "status": {"$in": list(COUNTED)}}, {"_id": 0, "items": 1}).to_list(500)
    for r in rows:
        for it in r.get("items", []):
            pid = it.get("product_id", "")
            out[pid] = round(out.get(pid, 0.0) + float(it.get("quantity") or 0), 4)
    return out


async def _candidate_rolls(owner_entity_id: str, product_id: str) -> List[Dict[str, Any]]:
    """E9.4 — roll NYATA milik PT pembeli yang bisa dikirim balik ke PT penjual.

    Roll hasil retur pelanggan (`origin_type="return"`, lot `RTN-…`) diletakkan di
    atas: barang yang diretur pelanggan itulah yang seharusnya kembali ke pemasok
    internalnya. Dulu pemilihannya FEFO per produk, jadi **roll bagus terkirim balik
    dan roll cacat tinggal di gudang sendiri** — nilai & grade-nya berbeda, dan
    pelanggan berikutnya yang menanggung akibatnya.
    """
    if not owner_entity_id or not product_id:
        return []
    rolls = await db.inventory_rolls.find(
        {"product_id": product_id, "owner_entity_id": owner_entity_id,
         "status": "available", "length_remaining": {"$gt": 0}},
        {"_id": 0, "id": 1, "roll_no": 1, "lot": 1, "grade": 1,
         "length_remaining": 1, "unit": 1, "warehouse_id": 1, "origin_type": 1,
         "return_id": 1, "condition": 1, "unit_cost": 1, "created_at": 1}).to_list(5000)
    out: List[Dict[str, Any]] = []
    for r in rolls:
        is_ret = (r.get("origin_type") == "return") or str(r.get("lot", "")).startswith("RTN-")
        out.append({
            "roll_id": r["id"],
            "roll_no": r.get("roll_no", ""),
            "lot": r.get("lot", ""),
            "grade": r.get("grade", ""),
            "condition": r.get("condition", ""),
            "qty": round(float(r.get("length_remaining") or 0), 2),
            "unit": r.get("unit", ""),
            "warehouse_id": r.get("warehouse_id", ""),
            "unit_cost": round(float(r.get("unit_cost") or 0), 2),
            "is_customer_return": bool(is_ret),
            "sales_return_id": r.get("return_id", ""),
        })
    out.sort(key=lambda x: (0 if x["is_customer_return"] else 1, x["lot"], x["roll_no"]))
    return out


async def returnable(interco_id: str) -> Dict[str, Any]:
    """Baris yang masih bisa diretur + ALASAN bila belum boleh (untuk layar)."""
    doc = await db[ics.COLL_ICT].find_one({"id": interco_id}, {"_id": 0})
    if not doc:
        raise IntercoReturnError("Transaksi tidak ditemukan.")
    seller, buyer = await ics._pair_docs(doc["pair_id"])
    done = await _returned_qty_map(doc["pair_id"])

    reason = ""
    if seller.get("status") not in RETURNABLE_ORIGIN:
        reason = ("Retur hanya untuk barang yang SUDAH berpindah. Transaksi ini masih "
                  f"berstatus “{ics.STATUS_LABEL.get(seller.get('status'), seller.get('status'))}” — "
                  "selama barangnya belum jalan, pakai **Batalkan** (jurnalnya dibalik).")
    else:
        task = await db.warehouse_transfers.find_one(
            {"interco_pair_id": doc["pair_id"], "status": "completed"}, {"_id": 0, "code": 1})
        if not task:
            reason = ("Barangnya belum pernah berpindah lewat tugas gudang — tidak ada yang "
                      "bisa dikembalikan. Pakai **Batalkan** untuk membatalkan dokumennya.")

    lines: List[Dict[str, Any]] = []
    for it in seller.get("items", []):
        total = round(float(it.get("quantity") or 0), 4)
        ret = round(done.get(it.get("product_id", ""), 0.0), 4)
        rollable = await _candidate_rolls(seller["buyer_entity_id"], it.get("product_id", ""))
        on_hand = round(sum(r["qty"] for r in rollable), 2)
        from_return = round(sum(r["qty"] for r in rollable if r["is_customer_return"]), 2)
        qty_returnable = round(max(total - ret, 0.0), 4)
        warn = ""
        # E9.4b — layar tidak boleh menawarkan retur yang PASTI gagal di langkah
        # berikutnya. `qty_returnable` hanya bicara soal dokumen; barangnya sendiri
        # harus benar-benar ada di gudang PT pembeli.
        if qty_returnable > 0.0001 and on_hand + 0.01 < qty_returnable:
            warn = (f"Barangnya belum semuanya kembali: hanya {on_hand:g} {it.get('unit','')} "
                    f"yang tersedia di gudang, sedangkan yang boleh diretur menurut dokumen "
                    f"{qty_returnable:g}. Selesaikan retur pelanggan / lepas karantina dulu.")
        elif qty_returnable > 0.0001 and from_return <= 0.01 and on_hand > 0.01:
            warn = ("Tidak ada roll hasil retur pelanggan (lot RTN-…) untuk barang ini — "
                    "kalau Anda lanjut, roll stok biasa yang akan dikirim balik. "
                    "Pilih roll secara sadar.")
        lines.append({
            "product_id": it.get("product_id"),
            "sku": it.get("sku", ""),
            "product_name": it.get("product_name", ""),
            "unit": it.get("unit", ""),
            "unit_price": float(it.get("unit_price") or 0),
            "qty_total": total,
            "qty_returned": ret,
            "qty_returnable": qty_returnable,
            # E9.4 — kandidat roll NYATA supaya yang dikirim balik bukan hasil FEFO acak.
            "rolls": rollable,
            "qty_on_hand": on_hand,
            "qty_from_customer_return": from_return,
            "warning": warn,
        })
    open_lines = [l for l in lines if l["qty_returnable"] > 0]
    if not reason and not open_lines:
        reason = "Seluruh barang pada transaksi ini sudah diretur."

    return {
        "interco_id": interco_id,
        "pair_id": doc["pair_id"],
        "origin_number": seller.get("number", ""),
        "seller_entity_id": seller["seller_entity_id"],
        "seller_entity_name": seller.get("seller_entity_name", ""),
        "buyer_entity_id": seller["buyer_entity_id"],
        "buyer_entity_name": seller.get("buyer_entity_name", ""),
        "tax_apply": bool(seller.get("tax_apply")),
        "tax_rate": float(seller.get("tax_rate") or 0),
        "lines": lines,
        "can_return": bool(not reason),
        "blocked_reason": reason,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CREATE (dokumen kembar retur)
# ═══════════════════════════════════════════════════════════════════════════
async def create(payload: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    interco_id = (payload.get("interco_id") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 5:
        raise IntercoReturnError(
            "Alasan retur wajib diisi (minimal 5 huruf) — retur mengubah piutang & utang "
            "antar-PT, jadi sebabnya harus tercatat.")
    info = await returnable(interco_id)
    if not info["can_return"]:
        raise IntercoReturnError(info["blocked_reason"])

    by_pid = {l["product_id"]: l for l in info["lines"]}
    items: List[Dict[str, Any]] = []
    for row in payload.get("items") or []:
        pid = (row.get("product_id") or "").strip()
        qty = round(float(row.get("quantity") or 0), 4)
        if not pid or qty <= 0:
            continue
        src = by_pid.get(pid)
        if not src:
            raise IntercoReturnError(f"Produk {pid} tidak ada pada transaksi asal.")
        if qty > src["qty_returnable"] + 0.0001:
            raise IntercoReturnError(
                f"{src['sku'] or pid}: jumlah retur {qty} melebihi yang masih bisa "
                f"diretur ({src['qty_returnable']} {src['unit']}).")
        items.append({
            "product_id": pid,
            "sku": src["sku"],
            "product_name": src["product_name"],
            "unit": src["unit"],
            "quantity": qty,
            "unit_price": src["unit_price"],
            "line_subtotal": round(qty * src["unit_price"], 2),
            # E9.4 — roll yang DIPILIH untuk dikirim balik (kalau kosong: mesin
            # mengutamakan roll hasil retur pelanggan, bukan FEFO acak).
            "roll_ids": [str(x) for x in (row.get("roll_ids") or []) if x],
            "notes": (row.get("notes") or "").strip(),
            # FASE U — jumlah roll retur antar-PT = roll yang benar-benar dipilih.
            "qty_rolls": await _dual.rolls_of_ids(row.get("roll_ids")),
        })
    if not items:
        raise IntercoReturnError("Minimal satu baris barang harus diretur.")

    subtotal = round(sum(i["line_subtotal"] for i in items), 2)
    tax_apply = bool(info["tax_apply"])
    tax_rate = float(info["tax_rate"] or 0)
    tax_amount = round(subtotal * (tax_rate / 100.0), 2) if tax_apply else 0.0
    grand = round(subtotal + tax_amount, 2)

    rp_id = new_id("icrp")
    ret_id = new_id("icr")
    rcv_id = new_id("icr")
    num_returner = await next_doc_number(COLL, "number", "ICR-",
                                        entity_id=info["buyer_entity_id"])
    num_receiver = await next_doc_number(COLL, "number", "ICR-",
                                        entity_id=info["seller_entity_id"])
    ts = now_iso()
    # FASE E-7 (E7.6) — dokumen retur ikut membawa `pair_id` (alias `return_pair_id`)
    # dan `qty_total`. Alasannya bukan kosmetik: mesin generik antar-PT (papan pasangan,
    # tautan dokumen G-4, ringkasan layar) membaca `pair_id`/`qty_total` seperti pada
    # `interco_transactions`; tanpa alias itu, retur selalu tampil "null" dan orang
    # menyimpulkan datanya rusak padahal hanya beda nama kolom.
    qty_total = round(sum(float(i.get("quantity") or 0) for i in items), 4)
    # E9.6 — rantai retur: retur PELANGGAN yang memicu retur antar-PT ini. Disebut
    # eksplisit oleh pemanggil, atau disimpulkan dari roll yang dipilih (roll hasil
    # retur pelanggan membawa `return_id`-nya sendiri).
    src_sr_id = (payload.get("source_sales_return_id") or "").strip()
    if not src_sr_id:
        picked = [rid for it in items for rid in (it.get("roll_ids") or [])]
        if picked:
            r = await db.inventory_rolls.find_one(
                {"id": {"$in": picked}, "origin_type": "return"},
                {"_id": 0, "return_id": 1}) or {}
            src_sr_id = (r.get("return_id") or "").strip()
    src_sr_number = ""
    if src_sr_id:
        _sr = await db.sales_returns.find_one({"id": src_sr_id},
                                             {"_id": 0, "number": 1}) or {}
        src_sr_number = _sr.get("number", "")
    common = {
        "return_pair_id": rp_id,
        "pair_id": rp_id,
        "qty_total": qty_total,
        "origin_pair_id": info["pair_id"],
        "origin_number": info["origin_number"],
        "source_sales_return_id": src_sr_id,
        "source_sales_return_number": src_sr_number,
        "seller_entity_id": info["seller_entity_id"],
        "seller_entity_name": info["seller_entity_name"],
        "buyer_entity_id": info["buyer_entity_id"],
        "buyer_entity_name": info["buyer_entity_name"],
        "items": items,
        "subtotal": subtotal,
        "tax_apply": tax_apply,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "grand_total": grand,
        "returned_cost": 0.0,
        "reason": reason,
        "notes": (payload.get("notes") or "").strip(),
        "doc_date": payload.get("doc_date") or _today(),
        "status": "draft",
        "warehouse_transfer_id": "",
        "warehouse_transfer_code": "",
        "warehouse_transfer_status": "",
        "timeline": [timeline_entry("draft", "Retur antar-PT dibuat", actor or "system",
                                    f"{len(items)} baris · {rupiah(grand)} · {reason}")],
        "created_at": ts, "created_by": actor,
        "updated_at": ts, "updated_by": actor,
    }
    returner = {**common, "id": ret_id, "number": num_returner, "role": "returner",
                "entity_id": info["buyer_entity_id"], "counterpart_id": rcv_id,
                "counterpart_number": num_receiver}
    receiver = {**common, "id": rcv_id, "number": num_receiver, "role": "receiver",
                "entity_id": info["seller_entity_id"], "counterpart_id": ret_id,
                "counterpart_number": num_returner}
    await db[COLL].insert_many([returner, receiver])
    await _link_refs(rp_id)
    return await get_pair(rp_id)


async def _pair_docs(return_pair_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    docs = await db[COLL].find({"return_pair_id": return_pair_id}, {"_id": 0}).to_list(2)
    if len(docs) != 2:
        raise IntercoReturnError("Pasangan dokumen retur tidak lengkap.")
    returner = next(d for d in docs if d.get("role") == "returner")
    receiver = next(d for d in docs if d.get("role") == "receiver")
    return returner, receiver


async def get_pair(return_pair_id: str) -> Dict[str, Any]:
    returner, receiver = await _pair_docs(return_pair_id)
    # E7.6 — `pair_id` dikirim juga di tingkat pasangan supaya konsumen generik
    # (papan pasangan PT, tautan dokumen) tidak perlu tahu kolomnya bernama lain.
    return {"return_pair_id": return_pair_id, "pair_id": return_pair_id,
            "qty_total": round(float(returner.get("qty_total") or 0), 4),
            "returner": safe_doc(returner), "receiver": safe_doc(receiver)}


async def backfill_pair_aliases() -> int:
    """E7.6 — lengkapi dokumen retur LAMA dengan `pair_id` + `qty_total` (idempotent).

    Hanya menambah kolom turunan (bukan mengubah nomor/nilai), jadi aman dijalankan
    setiap kali server hidup. Nomor dokumen TIDAK pernah ditulis ulang di sini —
    nomor adalah rujukan hukum; yang salah seri hanya data demo dan itu dibuat ulang
    lewat `seed_realistic.py`.
    """
    n = 0
    async for d in db[COLL].find(
            {"$or": [{"pair_id": {"$exists": False}}, {"qty_total": {"$exists": False}}]},
            {"_id": 0, "id": 1, "return_pair_id": 1, "items": 1}):
        await db[COLL].update_one({"id": d["id"]}, {"$set": {
            "pair_id": d.get("return_pair_id", ""),
            "qty_total": round(sum(float(i.get("quantity") or 0)
                                   for i in (d.get("items") or [])), 4)}})
        n += 1
    return n


async def get_one(ret_id: str) -> Optional[Dict[str, Any]]:
    doc = await db[COLL].find_one({"id": ret_id}, {"_id": 0})
    if not doc:
        return None
    return await get_pair(doc["return_pair_id"])


async def list_returns(scope_entity_ids: List[str], entity_id: str = "",
                       status: str = "", origin_pair_id: str = "",
                       limit: int = 200) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    elif scope_entity_ids:
        q["entity_id"] = {"$in": scope_entity_ids}
    if status:
        q["status"] = status
    if origin_pair_id:
        q["origin_pair_id"] = origin_pair_id
    rows = await db[COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return [safe_doc(r) for r in rows]


async def _link_refs(return_pair_id: str) -> None:
    try:
        from services import doc_refs_service as _refs
        returner, receiver = await _pair_docs(return_pair_id)
        seller, buyer = await ics._pair_docs(returner["origin_pair_id"])
        await _refs.safe_link(("interco_return", returner["id"]),
                              ("interco_return", receiver["id"]), "child",
                              note="Dokumen kembar retur antar-PT (nota retur ↔ nota kredit)")
        await _refs.safe_link(("interco_return", returner["id"]),
                              ("interco_transaction", buyer["id"]), "parent",
                              note="Retur atas transaksi antar-PT")
        await _refs.safe_link(("interco_return", receiver["id"]),
                              ("interco_transaction", seller["id"]), "parent",
                              note="Nota kredit retur antar-PT")
        # FASE E-9 (E9.6) — sambungan rantai retur: retur PELANGGAN yang memicu
        # retur antar-PT ini. Tanpa tautan ini tidak ada satu layar pun yang bisa
        # menjawab "kain retur dari Customer A akhirnya ke mana?".
        sr_id = (returner.get("source_sales_return_id") or "").strip()
        if sr_id:
            await _refs.safe_link(("sales_return", sr_id),
                                  ("interco_return", returner["id"]), "child",
                                  note="Barang retur pelanggan dikembalikan ke badan usaha pemasok")
    except Exception as exc:  # noqa: BLE001
        print(f"[interco_return] tautan dokumen gagal {return_pair_id}: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
# APPROVE — sisi DOKUMEN (uang berubah; barangnya belum tentu jalan)
# ═══════════════════════════════════════════════════════════════════════════
async def approve(ret_id: str, actor_user: Dict[str, Any]) -> Dict[str, Any]:
    doc = await db[COLL].find_one({"id": ret_id}, {"_id": 0})
    if not doc:
        raise IntercoReturnError("Dokumen retur tidak ditemukan.")
    if doc["status"] != "draft":
        raise IntercoReturnError(
            f"Hanya draf yang bisa disetujui (status sekarang: "
            f"{STATUS_LABEL.get(doc['status'], doc['status'])}).")
    approver = (actor_user or {}).get("name", "")
    creator = (doc.get("created_by") or "").strip()
    if creator and approver and creator == approver:
        raise IntercoReturnError(
            "Pembuat retur tidak boleh menyetujui returnya sendiri (pemisahan tugas). "
            "Minta rekan lain dengan wewenang persetujuan.")

    rp = doc["return_pair_id"]
    returner, receiver = await _pair_docs(rp)
    await _post_doc_gl(rp, approver)
    ts = now_iso()
    await db[COLL].update_many(
        {"return_pair_id": rp},
        {"$set": {"status": "approved", "approved_at": ts, "approved_by": approver,
                  "updated_at": ts, "updated_by": approver},
         "$push": {"timeline": timeline_entry(
             "approved", "Retur disetujui — jurnal pembalik terbit di dua buku",
             approver, rupiah(returner.get("grand_total")))}})
    await _refresh_origin(returner)
    return await get_pair(rp)


async def _refresh_origin(ret_doc: Dict[str, Any]) -> None:
    """Hitung ulang akumulasi retur pada dokumen kembar transaksi ASAL + saldo + eliminasi."""
    origin_pair = ret_doc["origin_pair_id"]
    rows = await db[COLL].find(
        {"origin_pair_id": origin_pair, "role": "returner",
         "status": {"$in": list(COUNTED)}}, {"_id": 0}).to_list(500)
    r_sub = round(sum(float(r.get("subtotal") or 0) for r in rows), 2)
    r_tax = round(sum(float(r.get("tax_amount") or 0) for r in rows), 2)
    r_tot = round(sum(float(r.get("grand_total") or 0) for r in rows), 2)
    r_cost = round(sum(float(r.get("returned_cost") or 0) for r in rows), 2)
    r_qty = round(sum(float(i.get("quantity") or 0)
                      for r in rows for i in r.get("items", [])), 4)

    seller, buyer = await ics._pair_docs(origin_pair)
    grand = float(seller.get("grand_total") or 0)
    settled = float(seller.get("settled_amount") or 0)
    upd: Dict[str, Any] = {
        "returned_subtotal": r_sub, "returned_tax": r_tax, "returned_amount": r_tot,
        "returned_cost": r_cost, "returned_qty": r_qty,
        "return_count": len(rows), "updated_at": now_iso(),
    }
    # Nilai dokumen TIDAK diedit (append-only). Bila retur + pelunasan sudah menutup
    # seluruh nilainya, statusnya maju ke `returned` supaya saldo tidak lagi terbuka.
    if seller.get("status") in ics.OPEN_STATUSES and r_tot + settled >= grand - EPS:
        upd["status"] = "returned"
        upd["returned_at"] = now_iso()
    await db[ics.COLL_ICT].update_many({"pair_id": origin_pair}, {"$set": upd})

    await ics._update_account_balance(seller["seller_entity_id"], seller["buyer_entity_id"])
    await ics._sync_group_elimination(origin_pair)

    # Faktur pajak yang sudah terbit tidak diedit — ditandai perlu PENGGANTI.
    if float(seller.get("tax_amount") or 0) > EPS:
        try:
            from services import interco_tax_service as tax
            await tax.flag_needs_replacement(
                origin_pair,
                note=(f"Retur {rupiah(r_tot)} sesudah faktur pajak terbit — terbitkan "
                      f"Faktur Pengganti dengan DPP bersih."))
        except Exception as exc:  # noqa: BLE001
            print(f"[interco_return] tandai faktur pajak gagal: {exc}")


async def _post_doc_gl(return_pair_id: str, actor: str) -> Dict[str, Any]:
    """Jurnal sisi DOKUMEN retur (idempotent per `{rp}:seller` / `{rp}:buyer`).

    Buku PENJUAL (menerima barang kembali, menerbitkan nota kredit):
      Dr 4-1000 Pendapatan            = subtotal retur
      Dr 2-1200 PPN Keluaran          = PPN retur (bila ber-PPN)
        Cr 1-1250 IC-AR                 = total retur

    Buku PEMBELI (mengembalikan barang):
      Dr 2-1250 IC-AP                 = total retur
        Cr 1-1310 Persediaan Dalam Perjalanan = subtotal retur
        Cr 1-1500 PPN Masukan                 = PPN retur (bila ber-PPN)

    Akun transit dipakai supaya persediaan pembeli baru turun ketika barangnya
    BENAR-BENAR keluar gudang (lihat `on_return_task_executed`) — pola yang sama
    dengan arah penjualannya.
    """
    returner, receiver = await _pair_docs(return_pair_id)
    if await gl_service._already_posted("interco_return", f"{return_pair_id}:seller") or \
       await gl_service._already_posted("interco_return", f"{return_pair_id}:buyer"):
        return {"posted": False, "reason": "sudah diposting"}
    subtotal = float(returner.get("subtotal") or 0)
    tax_amt = float(returner.get("tax_amount") or 0)
    grand = float(returner.get("grand_total") or 0)
    if grand <= EPS:
        return {"posted": False, "reason": "nilai nol"}
    ent_s = returner["seller_entity_id"]
    ent_b = returner["buyer_entity_id"]
    date = now_iso()
    label_s = receiver.get("number", "")
    label_b = returner.get("number", "")

    lines_s: List[Dict[str, Any]] = [
        {"account_code": gl_service.ACC_PENDAPATAN, "debit": subtotal, "credit": 0.0,
         "description": f"Pembatalan pendapatan antar-PT (retur {label_s})"},
    ]
    if tax_amt > EPS:
        lines_s.append({"account_code": gl_service.ACC_PPN_OUT, "debit": tax_amt,
                        "credit": 0.0,
                        "description": f"Koreksi PPN Keluaran retur antar-PT {label_s}"})
    lines_s.append({"account_code": gl_service.ACC_IC_AR, "debit": 0.0, "credit": grand,
                    "description": f"Piutang antar-PT berkurang karena retur {label_s}"})
    await gl_service._insert_entry(
        lines=lines_s, description=f"Nota kredit retur antar-PT {label_s}",
        date=date, source_type="interco_return",
        source_id=f"{return_pair_id}:seller", entity_id=ent_s,
        created_by=actor or "system", source_label=label_s)

    lines_b: List[Dict[str, Any]] = [
        {"account_code": gl_service.ACC_IC_AP, "debit": grand, "credit": 0.0,
         "description": f"Utang antar-PT berkurang karena retur {label_b}"},
        {"account_code": gl_service.ACC_PERSEDIAAN_TRANSIT, "debit": 0.0,
         "credit": subtotal,
         "description": f"Barang retur antar-PT dalam perjalanan {label_b}"},
    ]
    if tax_amt > EPS:
        lines_b.append({"account_code": gl_service.ACC_PPN_IN, "debit": 0.0,
                        "credit": tax_amt,
                        "description": f"Koreksi PPN Masukan retur antar-PT {label_b}"})
    await gl_service._insert_entry(
        lines=lines_b, description=f"Nota retur antar-PT {label_b}",
        date=date, source_type="interco_return",
        source_id=f"{return_pair_id}:buyer", entity_id=ent_b,
        created_by=actor or "system", source_label=label_b)
    return {"posted": True, "total": grand}


# ═══════════════════════════════════════════════════════════════════════════
# TUGAS GUDANG RETUR (barang benar-benar kembali)
# ═══════════════════════════════════════════════════════════════════════════
async def create_warehouse_task(ret_id: str, actor: str) -> Dict[str, Any]:
    """Terbitkan tugas gudang ARAH BALIK (pembeli → penjual) untuk retur."""
    from fastapi import HTTPException
    from services.roll_service import reserve_rolls_for_transfer, release_transfer_rolls

    doc = await db[COLL].find_one({"id": ret_id}, {"_id": 0})
    if not doc:
        raise IntercoReturnError("Dokumen retur tidak ditemukan.")
    if doc["status"] != "approved":
        raise IntercoReturnError(
            "Setujui returnya dulu — barang tidak boleh berjalan tanpa dokumen yang sah.")
    rp = doc["return_pair_id"]
    existing = await db.warehouse_transfers.find_one(
        {"interco_return_pair_id": rp, "status": {"$nin": ["rejected", "cancelled"]}},
        {"_id": 0, "code": 1, "status": 1})
    if existing:
        raise IntercoReturnError(
            f"Tugas gudang {existing.get('code')} sudah ada untuk retur ini "
            f"(status {existing.get('status')}).")

    returner, receiver = await _pair_docs(rp)
    transfer_id = new_id("trn")
    # FASE E-1 (E1.7) — nomor per badan usaha yang MENGEMBALIKAN barang.
    code = await next_doc_number("warehouse_transfers", "code", "TRF-",
                                 entity_id=returner.get("buyer_entity_id") or None)
    items_out: List[Dict[str, Any]] = []
    wh_ids: List[str] = []
    try:
        for it in returner.get("items", []):
            # E9.4 — kirim balik roll yang DIPILIH; kalau pengguna tidak memilih,
            # utamakan roll hasil retur pelanggan (lot RTN-…) sebelum FEFO biasa.
            reserved = await reserve_rolls_for_transfer(
                it["product_id"], returner["buyer_entity_id"],
                float(it["quantity"]), transfer_id,
                roll_ids=it.get("roll_ids") or None,
                prefer_origin_type="return")
            roll_refs = [{
                "roll_id": r["id"], "roll_no": r.get("roll_no"), "lot": r.get("lot"),
                "warehouse_id": r.get("warehouse_id"),
                "length": float(r.get("length_remaining", 0) or 0),
            } for r in reserved]
            for r in reserved:
                if r.get("warehouse_id"):
                    wh_ids.append(r["warehouse_id"])
            items_out.append({
                "product_id": it["product_id"], "qty": round(float(it["quantity"]), 2),
                "unit": it.get("unit", "meter"), "sku": it.get("sku", ""),
                "product_name": it.get("product_name", ""),
                "lots": sorted({r.get("lot") for r in reserved if r.get("lot")}),
                "rolls": roll_refs,
                "interco_unit_price": float(it.get("unit_price") or 0),
            })
    except HTTPException as exc:
        await release_transfer_rolls(transfer_id)
        raise IntercoReturnError(str(exc.detail)) from exc
    except Exception:
        await release_transfer_rolls(transfer_id)
        raise

    primary_wh = wh_ids[0] if wh_ids else ""
    transfer = {
        "id": transfer_id, "code": code, "transfer_kind": "inter_entity",
        # Arah BALIK: pembeli mengirim, penjual menerima.
        "entity_id": returner["buyer_entity_id"],   # FASE E-0 (L14) — pemilik = pengirim
        "source_entity_id": returner["buyer_entity_id"],
        "dest_entity_id": returner["seller_entity_id"],
        "source_warehouse_id": primary_wh, "dest_warehouse_id": primary_wh,
        "status": "waiting_approval", "items": items_out,
        "transfer_price": float(returner.get("subtotal") or 0),
        "linked_order_id": None,
        "interco_return_pair_id": rp,
        "interco_return_id": returner["id"],
        "interco_return_number": returner.get("number", ""),
        "interco_pair_id": None,
        "notes": (f"Pengembalian barang retur antar-PT {returner.get('number', '')} "
                  f"(atas {returner.get('origin_number', '')})"),
        "requested_by": actor or "system",
        "approved_by": None, "approved_at": None,
        "rejected_by": None, "rejected_at": None, "rejected_reason": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    from services import line_scope as _lines            # FASE L
    await _lines.stamp_doc(db, transfer)
    await db.warehouse_transfers.insert_one(dict(transfer))
    # E9.6 — kalau pengguna tidak memilih roll, sambungan ke retur pelanggan baru
    # bisa disimpulkan SEKARANG (dari roll yang benar-benar direservasi mesin).
    if not (returner.get("source_sales_return_id") or "").strip():
        picked = [rr["roll_id"] for it in items_out for rr in (it.get("rolls") or [])]
        if picked:
            r = await db.inventory_rolls.find_one(
                {"id": {"$in": picked}, "origin_type": "return"},
                {"_id": 0, "return_id": 1}) or {}
            sr_id = (r.get("return_id") or "").strip()
            if sr_id:
                _sr = await db.sales_returns.find_one({"id": sr_id},
                                                     {"_id": 0, "number": 1}) or {}
                await db[COLL].update_many(
                    {"return_pair_id": rp},
                    {"$set": {"source_sales_return_id": sr_id,
                              "source_sales_return_number": _sr.get("number", ""),
                              "updated_at": now_iso()}})
                try:
                    from services import doc_refs_service as _refs
                    await _refs.safe_link(("sales_return", sr_id),
                                          ("interco_return", returner["id"]), "child",
                                          note="Barang retur pelanggan dikembalikan ke badan usaha pemasok")
                except Exception as exc:  # noqa: BLE001
                    print(f"[interco_return] tautan retur pelanggan gagal: {exc}")
    await db[COLL].update_many(
        {"return_pair_id": rp},
        {"$set": {"warehouse_transfer_id": transfer_id, "warehouse_transfer_code": code,
                  "warehouse_transfer_status": "waiting_approval", "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry(
             "warehouse_task", f"Tugas gudang retur {code} terbit", actor or "system",
             "Gudang penerima yang menyetujui perpindahan barangnya kembali.")}})
    try:
        from services import doc_refs_service as _refs
        await _refs.safe_link(("interco_return", returner["id"]),
                              ("warehouse_transfer", transfer_id), "child",
                              note="Perpindahan fisik barang retur antar-PT")
    except Exception as exc:  # noqa: BLE001
        print(f"[interco_return] tautan tugas gudang gagal: {exc}")
    return safe_doc(transfer)


async def on_return_task_executed(transfer: Dict[str, Any], actor: str) -> Dict[str, Any]:
    """Dipanggil `routers/transfers.py` sesudah kepemilikan roll kembali ke penjual.

    Tiga hal WAJIB terjadi:
      1. Roll dinilai ulang KEMBALI ke harga perolehan asli penjual
         (`cost_basis.previous_unit_cost`) — kalau tidak, persediaan penjual naik
         sebesar harga jual internal dan GL 1-1300 berselisih abadi dari subledger.
      2. Jurnal BARANG diposting: transit→keluar di pembeli, persediaan←HPP di penjual.
      3. Status retur maju ke `completed` + akumulasi biaya retur dicatat supaya
         eliminasi konsolidasi ikut mengecil (INV-IC-03).
    """
    rp = transfer.get("interco_return_pair_id") or ""
    if not rp:
        return {"revalued_rolls": 0, "status": ""}
    returner, receiver = await _pair_docs(rp)
    rolls = await db.inventory_rolls.find(
        {"acquired.ref_id": transfer["id"],
         "owner_entity_id": transfer.get("dest_entity_id")},
        {"_id": 0, "id": 1, "product_id": 1, "unit_cost": 1, "base_unit_cost": 1,
         "length_remaining": 1, "cost_basis": 1}).to_list(10000)

    revalued = 0
    cost_back = 0.0
    carry_out = 0.0
    for r in rolls:
        cb = r.get("cost_basis") or {}
        prev = float(cb.get("previous_unit_cost") or 0)
        length = float(r.get("length_remaining") or 0)
        target = prev if prev > 0 else float(r.get("unit_cost") or 0)
        cost_back += length * target
        # Nilai yang BENAR-BENAR keluar dari persediaan pembeli = nilai tercatat roll
        # itu sekarang (sebelum dinilai ulang). Untuk roll hasil pembelian internal
        # biasa, angka ini sama dengan harga internalnya. Untuk roll hasil RETUR
        # PELANGGAN yang sudah dihapus-bukukan (mis. `damaged` → 0), angkanya jauh
        # lebih kecil — dan itulah yang harus dikreditkan, bukan harga jual internal.
        carry_out += length * float(r.get("unit_cost") or 0)
        await db.inventory_rolls.update_one({"id": r["id"]}, {"$set": {
            "unit_cost": round(target, 2),
            "base_unit_cost": round(target, 2),
            "cost_basis": {
                "source": "interco_return",
                "interco_pair_id": "",
                "returned_from_pair_id": returner.get("origin_pair_id", ""),
                "interco_return_pair_id": rp,
                "interco_return_number": returner.get("number", ""),
                "previous_unit_cost": float(r.get("unit_cost") or 0),
                "at": now_iso(),
            },
            "updated_at": now_iso(),
        }})
        revalued += 1
    cost_back = round(cost_back, 2)
    carry_out = round(carry_out, 2)

    gl = await _post_goods_gl(rp, actor, cost_back, carry_out)
    ts = now_iso()
    # Nilai barang yang berpindah DICATAT di dokumen (termasuk bila nol) supaya
    # "tidak ada jurnal" bisa dibedakan dari "lupa menjurnal" — invarian INV-IC-08
    # membaca angka ini, bukan menebak dari harga jual internal.
    _ret_value = round(float(returner.get("subtotal") or 0), 2)
    await db[COLL].update_many(
        {"return_pair_id": rp},
        {"$set": {"goods_out_value": carry_out, "goods_in_value": cost_back,
                  "goods_value_gap": round(_ret_value - carry_out, 2),
                  "updated_at": ts}})
    await db[COLL].update_many(
        {"return_pair_id": rp},
        {"$set": {"status": "completed", "completed_at": ts, "completed_by": actor,
                  "warehouse_transfer_status": "completed",
                  "returned_cost": cost_back, "updated_at": ts},
         "$push": {"timeline": timeline_entry(
             "completed", "Barang sudah kembali ke PT penjual", actor,
             f"{revalued} roll dinilai ulang ke harga perolehan asli "
             f"({rupiah(cost_back)})")}})
    refreshed = await db[COLL].find_one({"return_pair_id": rp, "role": "returner"},
                                        {"_id": 0})
    await _refresh_origin(refreshed or returner)
    return {"revalued_rolls": revalued, "returned_cost": cost_back,
            "status": "completed", "return_pair_id": rp, "gl": gl}


async def _post_goods_gl(return_pair_id: str, actor: str, cost_back: float,
                         carry_out: float) -> Dict[str, Any]:
    """Jurnal sisi BARANG retur (idempotent).

    Buku PEMBELI: Dr 1-1310 Transit / Cr 1-1300 Persediaan  = **nilai tercatat roll
                  yang keluar** (`carry_out`), bukan harga jual internalnya.
    Buku PENJUAL: Dr 1-1300 Persediaan / Cr 5-1000 HPP      = biaya perolehan asli

    KENAPA `carry_out`, BUKAN `subtotal` (FASE E-9 · E9.4):
    dulu sisi barang pembeli dikreditkan sebesar `subtotal` retur (harga internal),
    dengan asumsi diam-diam bahwa roll yang dikembalikan SELALU roll hasil pembelian
    internal yang nilainya = harga internal. Sejak E9.4 yang dikembalikan justru
    **roll hasil retur pelanggan** — dan roll itu bisa sudah dihapus-bukukan menjadi
    Rp 0 (kondisi `damaged`). Mengkreditkan 1-1300 sebesar harga internal untuk roll
    bernilai nol membuat GL persediaan pembeli **berselisih abadi** dari subledger-nya
    (kelas cacat INV-GL-DRIFT). Jadi yang dijurnal adalah nilai yang benar-benar hilang
    dari persediaan; selisih terhadap nilai retur disimpan sebagai `goods_value_gap`
    pada dokumen retur agar Finance bisa melihatnya dan memutuskan perlakuannya.
    Bila tidak ada nilai yang berpindah (barang sudah nol), TIDAK ada jurnal palsu.
    """
    returner, receiver = await _pair_docs(return_pair_id)
    out: Dict[str, Any] = {"goods_out": 0.0, "goods_in": 0.0}
    date = now_iso()
    if carry_out > EPS and not await gl_service._already_posted(
            "interco_return", f"{return_pair_id}:goods_out"):
        lines = gl_service._balanced_pair(
            gl_service.ACC_PERSEDIAAN_TRANSIT, gl_service.ACC_PERSEDIAAN, carry_out,
            f"Barang retur keluar gudang pembeli {returner.get('number', '')}")
        await gl_service._insert_entry(
            lines=lines,
            description=f"Barang retur antar-PT keluar {returner.get('number', '')}",
            date=date, source_type="interco_return",
            source_id=f"{return_pair_id}:goods_out",
            entity_id=returner["buyer_entity_id"], created_by=actor or "system",
            source_label=returner.get("number", ""))
        out["goods_out"] = carry_out
    if cost_back > EPS and not await gl_service._already_posted(
            "interco_return", f"{return_pair_id}:goods_in"):
        lines = gl_service._balanced_pair(
            gl_service.ACC_PERSEDIAAN, gl_service.ACC_HPP, round(cost_back, 2),
            f"Barang retur masuk kembali ke gudang penjual {receiver.get('number', '')} "
            f"(harga perolehan asli)")
        await gl_service._insert_entry(
            lines=lines,
            description=f"Barang retur antar-PT diterima {receiver.get('number', '')}",
            date=date, source_type="interco_return",
            source_id=f"{return_pair_id}:goods_in",
            entity_id=returner["seller_entity_id"], created_by=actor or "system",
            source_label=receiver.get("number", ""))
        out["goods_in"] = round(cost_back, 2)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# BATAL (hanya draf — sesudah disetujui jurnalnya sudah hidup)
# ═══════════════════════════════════════════════════════════════════════════
async def cancel(ret_id: str, actor: str, reason: str = "") -> Dict[str, Any]:
    doc = await db[COLL].find_one({"id": ret_id}, {"_id": 0})
    if not doc:
        raise IntercoReturnError("Dokumen retur tidak ditemukan.")
    if doc["status"] != "draft":
        raise IntercoReturnError(
            "Retur yang sudah disetujui tidak bisa dibatalkan — jurnalnya sudah hidup di "
            "dua buku. Terbitkan transaksi antar-PT baru bila barangnya mau dikirim ulang.")
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise IntercoReturnError("Alasan pembatalan retur wajib diisi (minimal 5 huruf).")
    await db[COLL].update_many(
        {"return_pair_id": doc["return_pair_id"]},
        {"$set": {"status": "cancelled", "cancel_reason": reason,
                  "cancelled_by": actor, "cancelled_at": now_iso(),
                  "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry("cancelled", "Draf retur dibatalkan",
                                              actor, reason)}})
    return await get_pair(doc["return_pair_id"])


async def meta() -> Dict[str, Any]:
    return {"statuses": [{"value": s, "label": STATUS_LABEL[s]} for s in STATUSES]}
