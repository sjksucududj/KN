"""FASE E-7 (E7.1 · gelombang 2 “E7d”) — **PERMINTAAN INTERNAL** (`<ENT>/PIN-#####`).

## Lubang nyata yang ditutup
Papan stok sudah memberi isyarat jujur *“tersedia 240 yard di badan usaha lain”*
(E5.1), tetapi sales **403 di seluruh menu Antar Entitas** — jadi isyarat itu
berakhir sebagai jalan buntu: penjual tahu barangnya ada di grup, dan satu-satunya
cara memintanya adalah WhatsApp ke rekan di PT lain. Akibatnya:

  * permintaan tidak pernah tercatat → tidak ada antrean, tidak ada jejak, tidak ada
    ukuran “berapa lama PT lain menjawab”;
  * barang kadang dikirim tanpa dokumen antar-PT sama sekali (lalu dipaksa masuk
    lewat PO biasa — persis kebocoran yang dipagari E7.2);
  * pesanan pelanggan menggantung tanpa alasan yang bisa dilacak.

## Bentuk yang dipilih (sesuai keputusan pemilik)
Sales **mengajukan permintaan**, admin/manajer **menjadikannya transaksi Antar-PT**
(mesin G-6 yang sudah ada — JANGAN dibuat ulang). Nomor `<ENT>/PIN-#####` memakai
deret per badan usaha (E1.7) supaya dua PT tidak berebut nomor.

Dua hal yang SENGAJA dijaga di sini:

1. **Sales tidak memilih PT sumber.** Keputusan pemilik di E5.1: rincian stok PT lain
   bukan urusan sales (yang dilihatnya hanya ANGKA gabungan). Karena itu kolom
   `source_entity_id` hanya boleh diisi peran lintas-entitas; sales cukup menyebut
   *barang apa, berapa, untuk apa*. Yang memilih PT sumber adalah admin/manajer saat
   mengubahnya menjadi transaksi antar-PT — dan sejak FASE E-8 pekerjaan itu pindah
   ke Meja Admin Sales (`sales_admin`), bukan ditulis ulang.
2. **Bukti ketersediaan disimpan** (`availability_snapshot`) pada saat mengajukan.
   Stok bergerak; tanpa cuplikan ini, permintaan yang ditolak dua hari kemudian
   terlihat seperti permintaan ngawur.

Ambang `antar_entitas.approval_threshold_rupiah` **tidak diduplikasi** di sini:
ia sudah dijaga `interco_service.create/confirm`. Permintaan internal bukan
dokumen keuangan — ia surat permintaan; yang membentuk piutang/utang antar-PT
tetap transaksi antar-PT-nya.
"""
from typing import Any, Dict, List, Optional

from db import db
from services import dual_qty_service as _dual  # FASE U — dua satuan (roll + ukuran)
from core_utils import new_id, next_doc_number, now_iso, safe_doc, rupiah, timeline_entry
from services import interco_service as ics
from services import line_scope              # FASE L — stempel & pagar lini produk

COLL = "internal_requests"

STATUS_SUBMITTED = "submitted"
STATUS_CONVERTED = "converted"
STATUS_REJECTED = "rejected"
STATUS_CANCELLED = "cancelled"

STATUS_LABEL = {
    STATUS_SUBMITTED: "Menunggu ditindak",
    STATUS_CONVERTED: "Jadi transaksi antar-PT",
    STATUS_REJECTED: "Ditolak",
    STATUS_CANCELLED: "Dibatalkan",
}
OPEN_STATUSES = (STATUS_SUBMITTED,)


class InternalRequestError(ValueError):
    """Kesalahan ber-kalimat siap tampil (Bahasa Indonesia)."""


def _today() -> str:
    return now_iso()[:10]


async def _next_number(entity_id: str) -> str:
    return await next_doc_number(COLL, "number", "PIN-", entity_id=entity_id)


async def _entity_name(entity_id: str) -> str:
    e = await db.business_entities.find_one({"id": entity_id}, {"_id": 0}) or {}
    return e.get("short_name") or e.get("legal_name") or entity_id


async def _product(product_id: str) -> Optional[Dict[str, Any]]:
    return await db.products.find_one(
        {"id": product_id}, {"_id": 0, "id": 1, "sku": 1, "name": 1, "base_unit": 1, "price": 1,
                             "harga_pokok": 1})


# ─── Ketersediaan: angka gabungan untuk semua, rincian per PT hanya untuk lintas-entitas ──
async def availability(product_id: str, requester_entity_id: str) -> Dict[str, Any]:
    """Stok tersedia satu barang: milik sendiri, gabungan grup, dan per badan usaha.

    Pemanggil yang melayani sales WAJIB membuang `by_entity` (keputusan E5.1).
    """
    per: Dict[str, float] = {}
    async for b in db.inventory_balances.find(
            {"product_id": product_id},
            {"_id": 0, "owner_entity_id": 1, "available_qty": 1}):
        ent = b.get("owner_entity_id") or ""
        per[ent] = round(per.get(ent, 0.0) + float(b.get("available_qty") or 0), 4)
    own = round(per.get(requester_entity_id, 0.0), 4)
    group = round(sum(per.values()), 4)
    return {"own_available": own, "group_available": group,
            "other_entities_available": round(max(group - own, 0.0), 4),
            "by_entity": per}


def strip_entity_details(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Buang rincian per badan usaha dari satu dokumen permintaan (untuk peran
    NON lintas-entitas). Angka gabungan tetap dikirim — itu yang memang boleh
    dilihat sales (E5.1), sekaligus alasan permintaannya masuk akal."""
    out = dict(doc or {})
    snap = out.get("availability_snapshot") or []
    out["availability_snapshot"] = [
        {k: v for k, v in row.items() if k != "by_entity"} for row in snap]
    return out


# ─── CREATE ─────────────────────────────────────────────────────────────────
async def create(payload: Dict[str, Any], actor: Dict[str, Any],
                 requester_entity_id: str, cross_entity: bool = False) -> Dict[str, Any]:
    if not requester_entity_id or requester_entity_id == "all":
        raise InternalRequestError(
            "Pilih badan usaha Anda dulu (mode gabungan hanya untuk melihat) — "
            "permintaan internal selalu milik satu badan usaha.")
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 5:
        raise InternalRequestError(
            "Alasan wajib diisi (minimal 5 huruf) — permintaan ini akan menggerakkan "
            "barang milik badan usaha lain, jadi sebabnya harus terbaca oleh yang menindak.")

    source_entity_id = (payload.get("source_entity_id") or "").strip()
    if source_entity_id and not cross_entity:
        raise InternalRequestError(
            "Anda tidak perlu memilih badan usaha sumber — cukup sebutkan barang dan "
            "jumlahnya. Admin/manajer yang menentukan barang diambil dari badan usaha "
            "mana (rincian stok badan usaha lain memang bukan wewenang peran Anda).")
    if source_entity_id == requester_entity_id:
        raise InternalRequestError(
            "Badan usaha sumber tidak boleh sama dengan badan usaha peminta.")
    if source_entity_id:
        src = await db.business_entities.find_one({"id": source_entity_id}, {"_id": 0})
        if not src:
            raise InternalRequestError("Badan usaha sumber tidak ditemukan.")
        if src.get("status", "active") != "active":
            raise InternalRequestError(
                f"“{src.get('legal_name') or source_entity_id}” sudah tidak aktif — "
                f"barang tidak bisa diminta dari badan usaha yang berhenti beroperasi.")

    rows_in = payload.get("items") or []
    items: List[Dict[str, Any]] = []
    snapshot: List[Dict[str, Any]] = []
    est_value = 0.0
    for row in rows_in:
        pid = (row.get("product_id") or "").strip()
        qty = round(float(row.get("quantity") or 0), 4)
        if not pid or qty <= 0:
            raise InternalRequestError("Setiap baris wajib barang & jumlah lebih dari 0.")
        prod = await _product(pid)
        if not prod:
            raise InternalRequestError(f"Barang {pid} tidak ditemukan di master produk.")
        av = await availability(pid, requester_entity_id)
        if av["other_entities_available"] <= 0:
            raise InternalRequestError(
                f"{prod.get('sku') or pid} — tidak ada stok tersedia di badan usaha lain "
                f"saat ini, jadi permintaan internal tidak akan bisa dipenuhi. "
                f"Pakai jalur pembelian ke pemasok (Permintaan Pembelian / PR).")
        est = round(float(prod.get("harga_pokok") or prod.get("price") or 0) * qty, 2)
        est_value = round(est_value + est, 2)
        items.append({
            "product_id": pid, "sku": prod.get("sku", ""),
            "product_name": prod.get("name", ""),
            "unit": prod.get("base_unit", ""),
            "quantity": qty,
            "est_value": est,
            # FASE L — snapshot lini kerja MD. Permintaan internal ("stok saya habis,
            # kirim dari PT sebelah") ikut papan lini yang sama dengan produknya —
            # kalau tidak, permintaan itu tidak muncul di chip lini mana pun.
            "line_code": str(prod.get("line_code") or "").strip().lower(),
            "notes": (row.get("notes") or "").strip(),
            # FASE U — dua satuan (jumlah roll yang diminta dari PT sebelah).
            **(await _dual.stamp({"unit": prod.get("base_unit", ""), **row})),
        })
        snapshot.append({"product_id": pid, "sku": prod.get("sku", ""),
                         "at": now_iso(), **av})
    if not items:
        raise InternalRequestError("Minimal satu barang harus diminta.")

    # Tautan pesanan pelanggan (opsional) — inilah yang membuat “untuk SO mana”
    # terlacak, dan dipakai FASE E-8/E-9 untuk menutup backorder otomatis.
    so_id = (payload.get("source_order_id") or "").strip()
    so_number = ""
    if so_id:
        so = await db.sales_orders.find_one({"id": so_id}, {"_id": 0, "number": 1, "entity_id": 1})
        if not so:
            raise InternalRequestError("Pesanan penjualan (SO) yang dirujuk tidak ditemukan.")
        if so.get("entity_id") != requester_entity_id:
            raise InternalRequestError(
                "SO yang dirujuk bukan milik badan usaha Anda — permintaan internal "
                "hanya boleh menunjuk pesanan sendiri.")
        so_number = so.get("number", "")

    ts = now_iso()
    doc = {
        "id": new_id("pin"),
        "number": await _next_number(requester_entity_id),
        "entity_id": requester_entity_id,
        "requester_entity_name": await _entity_name(requester_entity_id),
        "source_entity_id": source_entity_id,
        "source_entity_name": await _entity_name(source_entity_id) if source_entity_id else "",
        "items": items,
        "est_value": est_value,
        "est_value_basis": "HPP/harga master × jumlah — TAKSIRAN, harga final memakai kontrak internal",
        "reason": reason,
        "needed_date": (payload.get("needed_date") or "").strip(),
        "notes": (payload.get("notes") or "").strip(),
        "source_order_id": so_id,
        "source_order_number": so_number,
        "availability_snapshot": snapshot,
        "status": STATUS_SUBMITTED,
        "requested_by": actor.get("name", ""),
        "requested_by_id": actor.get("id", ""),
        "requested_by_role": actor.get("role", ""),
        "interco_pair_id": "",
        "interco_number_buyer": "",
        "interco_number_seller": "",
        "decided_by": "", "decided_at": "", "decision_reason": "",
        "timeline": [timeline_entry(STATUS_SUBMITTED, "Permintaan internal diajukan",
                                    actor.get("name", ""),
                                    f"{len(items)} barang · taksiran {rupiah(est_value)} · {reason}")],
        "created_at": ts, "created_by": actor.get("name", ""),
        "updated_at": ts, "updated_by": actor.get("name", ""),
    }
    await line_scope.stamp_doc(db, doc)      # FASE L — satu pintu stempel lini
    await db[COLL].insert_one(dict(doc))

    if so_id:  # jejak dua arah: SO ⇄ permintaan internal (mesin G-4)
        from services import doc_refs_service as refs
        await refs.safe_link(("internal_request", doc["id"]), ("sales_order", so_id),
                             "parent", note="permintaan barang dari badan usaha lain")

    await _notify_queue(doc)
    return safe_doc(doc)


async def _notify_queue(doc: Dict[str, Any]) -> None:
    """Antrean tidak berguna kalau tidak ada yang tahu ia bertambah.

    FASE E-8 (E8.8) — `sales_admin` DITAMBAHKAN ke penerima. Antrean "Permintaan
    internal dari sales" kini ada di **Meja Admin Sales** dan dialah yang memilih
    badan usaha sumbernya; kalau pemberitahuannya hanya ke admin/manajer, antrean itu
    hidup di layar orang yang tidak menindaknya.
    """
    try:
        from services import notification_service as notif
        for role in ("admin", "manager", "sales_admin"):
            await notif.create_notification(
                notif_type="internal_request_submitted",
                title=f"Permintaan internal {doc['number']} menunggu ditindak",
                body=(f"{doc['requested_by']} ({doc['requester_entity_name']}) meminta "
                      f"{len(doc['items'])} barang dari badan usaha lain — taksiran "
                      f"{rupiah(doc['est_value'])}. Alasan: {doc['reason']}"),
                severity="info", link="internal-requests",
                entity_id=doc["entity_id"], recipient_role=role, ref=doc["id"])
    except Exception:  # noqa: BLE001 — notifikasi bukan syarat sahnya permintaan
        return


# ─── BACA ───────────────────────────────────────────────────────────────────
async def list_requests(query: Dict[str, Any], limit: int = 300) -> List[Dict[str, Any]]:
    rows = await db[COLL].find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return [safe_doc(r) for r in rows]


async def get_one(req_id: str) -> Optional[Dict[str, Any]]:
    row = await db[COLL].find_one({"id": req_id}, {"_id": 0})
    return safe_doc(row) if row else None


async def _load(req_id: str) -> Dict[str, Any]:
    row = await db[COLL].find_one({"id": req_id}, {"_id": 0})
    if not row:
        raise InternalRequestError("Permintaan internal tidak ditemukan.")
    return row


# ─── KANDIDAT SUMBER (hanya peran lintas-entitas) ───────────────────────────
async def sources(req_id: str) -> Dict[str, Any]:
    """Badan usaha mana yang BISA memenuhi permintaan ini — beserta halangannya.

    Bukan sekadar daftar: setiap kandidat diuji **dua** hal yang biasanya baru
    ketahuan saat tombol ditekan (dan karena itu terasa seperti kerusakan):
      1. stoknya cukup untuk setiap baris, dan
      2. **harga internalnya sudah ada** (mode `fixed_price` menuntut kontrak internal
         aktif per barang). Kalau belum, kalimatnya menuntun membuat kontrak dulu.
    """
    req = await _load(req_id)
    buyer = req["entity_id"]
    ents = await db.business_entities.find({}, {"_id": 0}).to_list(200)
    candidates: List[Dict[str, Any]] = []
    for ent in ents:
        if ent["id"] == buyer:
            continue
        lines: List[Dict[str, Any]] = []
        enough_all = True
        for it in req["items"]:
            av = await availability(it["product_id"], buyer)
            have = round(float(av["by_entity"].get(ent["id"], 0.0)), 4)
            enough = have + 0.0001 >= float(it["quantity"])
            enough_all = enough_all and enough
            lines.append({"product_id": it["product_id"], "sku": it["sku"],
                          "product_name": it["product_name"], "unit": it["unit"],
                          "needed": it["quantity"], "available": have, "enough": enough})
        pricing_mode = str(await ics._config("antar_entitas.pricing_mode", ent["id"])
                           or "fixed_price")
        price_issues: List[str] = []
        price_preview = 0.0
        for it in req["items"]:
            try:
                pr = await ics._resolve_price(ent["id"], buyer, it["product_id"], None,
                                              pricing_mode)
                price_preview = round(
                    price_preview + float(pr["unit_price"]) * float(it["quantity"]), 2)
            except ics.IntercoError as exc:
                price_issues.append(str(exc))
            except Exception as exc:  # noqa: BLE001 — jangan bikin layar mati
                price_issues.append(f"{it['sku'] or it['product_id']}: {exc}")
        candidates.append({
            "entity_id": ent["id"],
            "entity_name": ent.get("short_name") or ent.get("legal_name") or ent["id"],
            "legal_name": ent.get("legal_name", ""),
            "status": ent.get("status", "active"),
            "active": ent.get("status", "active") == "active",
            "lines": lines,
            "stock_enough": enough_all,
            "pricing_mode": pricing_mode,
            "price_ready": not price_issues,
            "price_issues": price_issues,
            "price_preview": price_preview,
            "can_fulfill": bool(enough_all and not price_issues
                                and ent.get("status", "active") == "active"),
        })
    candidates.sort(key=lambda c: (not c["can_fulfill"], c["entity_name"]))
    return {"request": safe_doc(req), "candidates": candidates}


# ─── KEPUTUSAN ──────────────────────────────────────────────────────────────
def _assert_open(req: Dict[str, Any], action: str) -> None:
    if req["status"] not in OPEN_STATUSES:
        raise InternalRequestError(
            f"Permintaan {req['number']} sudah “{STATUS_LABEL.get(req['status'], req['status'])}” "
            f"sehingga tidak bisa {action} lagi.")


async def reject(req_id: str, actor: Dict[str, Any], reason: str) -> Dict[str, Any]:
    req = await _load(req_id)
    _assert_open(req, "ditolak")
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise InternalRequestError(
            "Alasan penolakan wajib diisi (minimal 5 huruf) — peminta perlu tahu "
            "langkah berikutnya (beli ke pemasok? tunggu? ubah jumlah?).")
    await db[COLL].update_one({"id": req_id}, {
        "$set": {"status": STATUS_REJECTED, "decided_by": actor.get("name", ""),
                 "decided_at": now_iso(), "decision_reason": reason,
                 "updated_at": now_iso(), "updated_by": actor.get("name", "")},
        "$push": {"timeline": timeline_entry(STATUS_REJECTED, "Permintaan ditolak",
                                             actor.get("name", ""), reason)}})
    await _notify_requester(req, "ditolak", reason)
    return await get_one(req_id)


async def cancel(req_id: str, actor: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    req = await _load(req_id)
    _assert_open(req, "dibatalkan")
    await db[COLL].update_one({"id": req_id}, {
        "$set": {"status": STATUS_CANCELLED, "decided_by": actor.get("name", ""),
                 "decided_at": now_iso(), "decision_reason": (reason or "").strip(),
                 "updated_at": now_iso(), "updated_by": actor.get("name", "")},
        "$push": {"timeline": timeline_entry(STATUS_CANCELLED, "Permintaan dibatalkan",
                                             actor.get("name", ""), (reason or "").strip())}})
    return await get_one(req_id)


async def convert(req_id: str, actor: Dict[str, Any], *, source_entity_id: str = "",
                  pricing_mode: str = "", ppn_mode: str = "", submit_now: bool = False,
                  notes: str = "") -> Dict[str, Any]:
    """Jadikan permintaan ini **transaksi antar-PT** (mesin G-6) + jejak dua arah.

    Yang lahir di sini adalah dokumen KEMBAR (penjual & pembeli), harga dari kontrak
    internal, PPN/faktur pajak berpasangan, saldo pasangan PT, dan eliminasi margin —
    semuanya sudah ada. Modul ini hanya menyambungkan permintaan → transaksi.
    """
    req = await _load(req_id)
    _assert_open(req, "diproses")
    seller = (source_entity_id or req.get("source_entity_id") or "").strip()
    if not seller:
        raise InternalRequestError(
            "Pilih badan usaha sumber dulu — lihat daftar kandidat beserta stok & "
            "kesiapan harga internalnya pada panel di sebelah.")
    if seller == req["entity_id"]:
        raise InternalRequestError("Badan usaha sumber tidak boleh sama dengan peminta.")

    payload = {
        "seller_entity_id": seller,
        "buyer_entity_id": req["entity_id"],
        "items": [{"product_id": it["product_id"], "quantity": it["quantity"],
                   "notes": it.get("notes", "")} for it in req["items"]],
        "pricing_mode": pricing_mode or "",
        "ppn_mode": ppn_mode or "",
        "notes": (notes or f"Dari permintaan internal {req['number']} — {req['reason']}")[:600],
        "submit_now": bool(submit_now),
        # E7d/E8.12 — jejak permintaan & pesanan pelanggan menempel di transaksinya.
        "source_request_id": req["id"],
        "source_request_number": req["number"],
        "source_order_id": req.get("source_order_id", ""),
        "source_order_number": req.get("source_order_number", ""),
    }
    try:
        pair = await ics.create(payload, actor.get("name", ""), actor_user=actor)
    except ics.IntercoError as exc:
        # Kalimat mesin G-6 sudah menuntun (mis. “buat kontrak internal dulu”),
        # jadi diteruskan apa adanya — jangan ditelan menjadi galat generik.
        raise InternalRequestError(str(exc)) from exc

    seller_doc = pair.get("seller") or {}
    buyer_doc = pair.get("buyer") or {}
    await db[COLL].update_one({"id": req_id}, {
        "$set": {"status": STATUS_CONVERTED,
                 "source_entity_id": seller,
                 "source_entity_name": await _entity_name(seller),
                 "interco_pair_id": pair.get("pair_id", ""),
                 "interco_number_seller": seller_doc.get("number", ""),
                 "interco_number_buyer": buyer_doc.get("number", ""),
                 "decided_by": actor.get("name", ""), "decided_at": now_iso(),
                 "updated_at": now_iso(), "updated_by": actor.get("name", "")},
        "$push": {"timeline": timeline_entry(
            STATUS_CONVERTED, "Jadi transaksi antar-PT", actor.get("name", ""),
            f"{buyer_doc.get('number', '')} ⇄ {seller_doc.get('number', '')} · "
            f"{rupiah(float(seller_doc.get('grand_total') or 0))}")}})

    # Jejak dua arah (mesin G-4): transaksi antar-PT MEMENUHI permintaan internal.
    from services import doc_refs_service as refs
    for ict_id in (buyer_doc.get("id", ""), seller_doc.get("id", "")):
        if ict_id:
            await refs.safe_link(("interco_transaction", ict_id),
                                 ("internal_request", req["id"]), "fulfills",
                                 note=f"permintaan internal {req['number']}")
    await _notify_requester(req, "dijadikan transaksi antar-PT",
                            f"{buyer_doc.get('number', '')} ⇄ {seller_doc.get('number', '')}")
    return {"request": await get_one(req_id), "interco": pair}


async def _notify_requester(req: Dict[str, Any], outcome: str, detail: str) -> None:
    try:
        from services import notification_service as notif
        await notif.create_notification(
            notif_type="internal_request_decided",
            title=f"Permintaan internal {req['number']} {outcome}",
            body=detail[:400], severity="info", link="internal-requests",
            entity_id=req["entity_id"], recipient_role="all",
            recipient_user=req.get("requested_by_id") or None,
            ref=f"{req['id']}:{outcome}")
    except Exception:  # noqa: BLE001
        return


async def summary(query: Dict[str, Any]) -> Dict[str, Any]:
    rows = await db[COLL].find(query, {"_id": 0, "status": 1, "est_value": 1}).to_list(2000)
    by_status: Dict[str, int] = {}
    for r in rows:
        by_status[r.get("status", "?")] = by_status.get(r.get("status", "?"), 0) + 1
    return {
        "total": len(rows),
        "by_status": by_status,
        "open_count": sum(1 for r in rows if r.get("status") in OPEN_STATUSES),
        "open_value": round(sum(float(r.get("est_value") or 0) for r in rows
                                if r.get("status") in OPEN_STATUSES), 2),
    }
