"""FASE G-6 — Layanan **TRANSAKSI ANTAR ENTITAS** (jual-beli antar-PT dalam grup).

Antar-PT diperlakukan **jual-beli**, bukan pindah gudang. Setiap transaksi lahir
sebagai **dokumen kembar**:
  * PT penjual (`role="seller"`)  — SO + Surat Jalan + Invoice internal
  * PT pembeli (`role="buyer"`)   — PO internal + Vendor Bill internal
Keduanya menunjuk `pair_id` yang sama. Barang fisiknya tetap berjalan lewat jalur
`warehouse_transfers` yang sudah ada (lapisan gudang).

**Invarian yang dijaga di sini:**
  * INV-IC-01 — setiap transaksi punya pasangan jurnal seimbang di DUA buku.
  * INV-IC-02 — IC-AR penjual = IC-AP pembeli untuk pasangan entitas (setelah settlement).
  * INV-IC-04 — `interco_accounts` == Σ transaksi − Σ settlement (tidak drift).
  * INV-IC-05 — PPN keluaran penjual == PPN masukan pembeli (bila ber-PPN); nol bila
                mode `tanpa_ppn`.

Keputusan pemilik (mengikat, 2026-07-30):
  1. Harga = `fixed_price` dari kontrak internal (`supplier_contracts` dengan
     `partner_kind="entity"`). Bila belum ada kontrak untuk barang → transaksi DITOLAK.
  2. PPN per-PT lewat config `antar_entitas.ppn_mode`.
  3. Settlement sewaktu-waktu (tanpa job penjadwal).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core_utils import (
    DEFAULT_ENTITY_ID, MoneyDecimal, new_id, next_doc_number, now_iso, parse_decimal,
    rupiah, safe_doc,
)
from db import db
from services import config_resolver
from services import gl_service
from services.costing_service import wac_for_product

EPS = 0.01

# ── Koleksi ──────────────────────────────────────────────────────────────────
COLL_ICT = "interco_transactions"
COLL_ICA = "interco_accounts"
COLL_ICS = "interco_settlements"

# FASE E-8 (E8.10b#4) — peran yang boleh MELEPAS SENDIRI transaksi antar-PT selama
# nilainya di BAWAH ambang `antar_entitas.approval_threshold_rupiah`.
# Keputusan pemilik: keputusan pemenuhan (termasuk "ambil dari PT lain") adalah
# wewenang penuh Admin Sales tanpa persetujuan manajer — penahannya nilai rupiah,
# bukan jabatan. Daftar ini SENGAJA eksplisit & sempit: menaruh peran lain di sini
# berarti memberi orang itu kuasa memindahkan barang antar badan usaha.
SELF_SERVE_BELOW_THRESHOLD = ("sales_admin",)

# ── Status siklus ────────────────────────────────────────────────────────────
STATUSES = ("draft", "confirmed", "shipped", "received", "invoiced", "settled",
            "returned", "disputed", "cancelled")
STATUS_LABEL = {
    "draft": "Draf",
    "confirmed": "Dikonfirmasi",
    "shipped": "Dikirim",
    "received": "Diterima",
    "invoiced": "Difakturkan",
    "settled": "Lunas",
    # FASE G-6b — seluruh nilainya sudah kembali lewat retur antar-PT (bukan
    # dibatalkan: dokumen & jurnalnya tetap ada, hanya sudah tidak berutang).
    "returned": "Diretur Penuh",
    "disputed": "Sengketa",
    "cancelled": "Dibatalkan",
}
OPEN_STATUSES = ("confirmed", "shipped", "received", "invoiced")

PRICING_MODES = ("fixed_price", "at_cost", "cost_plus_pct")
PPN_MODES = ("ikut_pkp", "tanpa_ppn", "dengan_ppn")


class IntercoError(Exception):
    """Pelanggaran aturan bisnis antar-PT (dipetakan ke HTTP 400 di router)."""


# ═══════════════════════════════════════════════════════════════════════════
# Utils
# ═══════════════════════════════════════════════════════════════════════════
def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


async def _entity_snapshot(entity_id: str) -> Dict[str, str]:
    if not entity_id:
        return {"id": "", "name": "", "is_pkp": False}
    ent = await db.business_entities.find_one(
        {"id": entity_id},
        {"_id": 0, "name": 1, "legal_name": 1, "short_name": 1,
         "is_pkp": 1, "default_tax_mode": 1, "npwp": 1}) or {}
    # PKP flag: prefer explicit `is_pkp`; fallback to default_tax_mode == "ppn".
    is_pkp = ent.get("is_pkp")
    if is_pkp is None:
        is_pkp = (ent.get("default_tax_mode") or "").lower() == "ppn"
    name = ent.get("name") or ent.get("legal_name") or ent.get("short_name") or ""
    return {
        "id": entity_id,
        "name": name,
        "is_pkp": bool(is_pkp),
        "npwp": ent.get("npwp", ""),
    }


async def _product_snapshot(product_id: str) -> Dict[str, str]:
    if not product_id:
        return {"sku": "", "name": "", "base_unit": ""}
    p = await db.products.find_one({"id": product_id},
                                   {"_id": 0, "sku": 1, "name": 1, "base_unit": 1}) or {}
    return {"sku": p.get("sku", ""), "name": p.get("name", ""),
            "base_unit": p.get("base_unit", "")}


async def _config(key: str, entity_id: str = "") -> Any:
    ctx = {"entity_id": entity_id} if entity_id else None
    return await config_resolver.value_of(key, ctx)


# ═══════════════════════════════════════════════════════════════════════════
# Resolusi harga & pajak (keputusan pemilik #1 & #2)
# ═══════════════════════════════════════════════════════════════════════════
async def _find_active_internal_contract(seller_entity_id: str, buyer_entity_id: str,
                                         product_id: str) -> Optional[Dict[str, Any]]:
    """Cari kontrak internal aktif (partner_kind=entity) untuk barang tertentu.

    Kontrak internal disimpan di `supplier_contracts` dengan:
      * `entity_id` = PT penjual (yang punya kontrak jual internal)
      * `partner_kind` = "entity"
      * `partner_id` = PT pembeli
      * `product_id` = barang
      * `status` = "active"
    """
    today = _today()
    doc = await db.supplier_contracts.find_one({
        "entity_id": seller_entity_id,
        "partner_kind": "entity",
        "partner_id": buyer_entity_id,
        "product_id": product_id,
        "status": "active",
    }, {"_id": 0})
    if not doc:
        return None
    vf, vt = doc.get("valid_from") or "", doc.get("valid_to") or ""
    if vf and vf > today:
        return None
    if vt and vt < today:
        return None
    return doc


async def _resolve_price(seller_entity_id: str, buyer_entity_id: str, product_id: str,
                        override_price: Optional[float], pricing_mode: str) -> Dict[str, Any]:
    """Kembalikan harga per unit + sumbernya. RAISE bila fixed_price tanpa kontrak."""
    if override_price is not None and override_price > 0:
        return {"unit_price": round(float(override_price), 2), "source": "override",
                "contract_id": ""}
    contract = await _find_active_internal_contract(
        seller_entity_id, buyer_entity_id, product_id)
    if pricing_mode == "fixed_price":
        if not contract:
            snap = await _product_snapshot(product_id)
            raise IntercoError(
                f"Barang {snap['sku'] or product_id} belum punya harga internal di kontrak "
                f"aktif untuk pasangan PT ini. Buat kontrak internal (partner_kind='entity') "
                f"dengan harga tetap sebelum menerbitkan transaksi.")
        rate = float(contract.get("tariff_rate") or 0)
        if rate <= 0:
            raise IntercoError(
                f"Kontrak internal {contract.get('contract_number', '')} tidak mencantumkan "
                f"harga (tariff_rate). Lengkapi kontrak sebelum menerbitkan transaksi.")
        return {"unit_price": round(rate, 2), "source": "fixed_price",
                "contract_id": contract.get("id", "")}
    if pricing_mode == "at_cost":
        wac = await wac_for_product(product_id, entity_id=seller_entity_id,
                                    use_cache=False)
        cost = round(float(wac.get("wac") or 0), 2)
        if cost <= 0:
            raise IntercoError(
                f"HPP untuk barang di PT penjual belum tersedia. Tidak bisa menerbitkan "
                f"transaksi 'at_cost' tanpa nilai persediaan.")
        return {"unit_price": cost, "source": "at_cost",
                "contract_id": contract.get("id") if contract else ""}
    if pricing_mode == "cost_plus_pct":
        wac = await wac_for_product(product_id, entity_id=seller_entity_id,
                                    use_cache=False)
        cost = float(wac.get("wac") or 0)
        margin_pct = float((contract or {}).get("ppi") or 0)  # simpan margin_pct di kontrak.ppi
        if cost <= 0:
            raise IntercoError("HPP barang belum tersedia untuk mode cost_plus_pct.")
        price = round(cost * (1.0 + margin_pct / 100.0), 2)
        return {"unit_price": price, "source": "cost_plus_pct",
                "contract_id": contract.get("id") if contract else ""}
    raise IntercoError(f"Mode harga '{pricing_mode}' tidak dikenal.")


async def _resolve_tax(seller_entity_id: str, ppn_mode: str) -> Dict[str, Any]:
    """Tarif PPN efektif untuk transaksi. INV-IC-05: kedua sisi harus sama besar."""
    seller = await _entity_snapshot(seller_entity_id)
    if ppn_mode == "tanpa_ppn":
        return {"apply": False, "rate": 0.0, "reason": "config tanpa_ppn"}
    if ppn_mode == "dengan_ppn":
        rate = float(await _config("antar_entitas.ppn_rate_percent", seller_entity_id) or 11.0)
        return {"apply": True, "rate": rate, "reason": "config dengan_ppn"}
    # ikut_pkp (bawaan)
    if seller.get("is_pkp"):
        rate = float(await _config("antar_entitas.ppn_rate_percent", seller_entity_id) or 11.0)
        return {"apply": True, "rate": rate, "reason": "penjual PKP"}
    return {"apply": False, "rate": 0.0, "reason": "penjual non-PKP"}


# ═══════════════════════════════════════════════════════════════════════════
# CREATE / lifecycle
# ═══════════════════════════════════════════════════════════════════════════
async def _next_number(entity_id: str) -> str:
    return await next_doc_number(COLL_ICT, "number", "IC-", entity_id=entity_id)


def _totals_from_items(items: List[Dict[str, Any]], tax_rate: float, tax_apply: bool
                       ) -> Dict[str, float]:
    subtotal = round(sum(float(it["quantity"]) * float(it["unit_price"]) for it in items), 2)
    tax = round(subtotal * (tax_rate / 100.0), 2) if tax_apply else 0.0
    return {"subtotal": subtotal, "tax": tax, "total": round(subtotal + tax, 2)}


async def _assert_may_release(actor_user: Optional[Dict[str, Any]], grand: float,
                             seller_entity_id: str) -> None:
    """Gerbang WEWENANG melepas transaksi antar-PT (dipakai `create(submit_now)` & `confirm`).

    FASE E-8 (E8.10b#4) — DUA CACAT LAMA yang ditutup di sini:

    1. **Peringkat peran adalah angka ajaib.** Dulu tertulis dua kali sebagai
       `{"warehouse":0,"sales":0,"manager":1,"admin":2}`. Dua peran baru E-8 TIDAK ADA
       di peta itu, jadi `sales_admin` jatuh ke peringkat 0 — sama dengan gudang —
       dan setiap "Ambil dari PT lain" ditolak dengan *"butuh persetujuan minimal peran
       manager"*. Sekarang peringkat dibaca dari `role_registry` (INV-ROLE-01).

    2. **Admin Sales terkunci padahal pemilik memberinya wewenang penuh.** Keputusan
       pemilik E8.10b#4: keputusan pemenuhan (termasuk ambil dari PT lain) adalah
       wewenang PENUH Admin Sales **tanpa** persetujuan manajer; satu-satunya penahan
       adalah **ambang rupiah** di Pusat Pengaturan. Karena itu di bawah ambang,
       `sales_admin` memenuhi gerbang nilai-kecil; di atas ambang ia WAJIB naik ke
       peran bernilai besar seperti peran lain. Ambangnya tetap hidup dan bisa
       diturunkan pemilik kapan pun tanpa deploy — bukan pintu yang dibuka permanen.
    """
    from role_registry import role_satisfies

    threshold = float(await _config("antar_entitas.approval_threshold_rupiah",
                                    seller_entity_id) or 0)
    high_role = str(await _config("antar_entitas.high_value_approval_role",
                                   seller_entity_id) or "admin")
    low_role = str(await _config("antar_entitas.approval_role",
                                  seller_entity_id) or "manager")
    actor_role = str((actor_user or {}).get("role") or "")
    besar = float(grand or 0) >= threshold

    if besar:
        if not role_satisfies(actor_role, high_role):
            raise IntercoError(
                f"Transaksi {rupiah(grand)} melewati ambang bernilai besar "
                f"({rupiah(threshold)}). Wajib disetujui peran '{high_role}'.")
        return
    if role_satisfies(actor_role, low_role) or actor_role in SELF_SERVE_BELOW_THRESHOLD:
        return
    raise IntercoError(
        f"Transaksi butuh persetujuan minimal peran '{low_role}'. "
        f"Simpan dulu sebagai draf, lalu minta persetujuan.")


async def create(payload: Dict[str, Any], actor: str = "",
                 actor_user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    seller = (payload.get("seller_entity_id") or "").strip()
    buyer = (payload.get("buyer_entity_id") or "").strip()
    if not seller or not buyer:
        raise IntercoError("PT penjual dan PT pembeli wajib dipilih.")
    if seller == buyer:
        raise IntercoError("PT penjual dan PT pembeli harus berbeda.")

    items_in = payload.get("items") or []
    if not items_in:
        raise IntercoError("Minimal satu barang harus dimasukkan.")

    pricing_mode = (payload.get("pricing_mode") or "").strip().lower() or \
                   (await _config("antar_entitas.pricing_mode", seller) or "fixed_price")
    if pricing_mode not in PRICING_MODES:
        raise IntercoError(f"Mode harga '{pricing_mode}' tidak dikenal.")

    ppn_mode = (payload.get("ppn_mode") or "").strip().lower() or \
               (await _config("antar_entitas.ppn_mode", seller) or "ikut_pkp")
    if ppn_mode not in PPN_MODES:
        raise IntercoError(f"Mode PPN '{ppn_mode}' tidak dikenal.")

    tax = await _resolve_tax(seller, ppn_mode)

    # Resolusi harga per baris
    items: List[Dict[str, Any]] = []
    for it in items_in:
        pid = (it.get("product_id") or "").strip()
        qty = float(it.get("quantity") or 0)
        if not pid or qty <= 0:
            raise IntercoError("Setiap baris wajib produk & jumlah > 0.")
        override = it.get("unit_price")
        override_val = float(override) if override not in (None, "", 0) else None
        pr = await _resolve_price(seller, buyer, pid, override_val, pricing_mode)
        snap = await _product_snapshot(pid)
        items.append({
            "product_id": pid,
            "sku": snap["sku"],
            "product_name": snap["name"],
            "quantity": round(qty, 4),
            "unit": snap["base_unit"],
            "unit_price": pr["unit_price"],
            "price_source": pr["source"],
            "contract_id": pr["contract_id"],
            "line_subtotal": round(qty * pr["unit_price"], 2),
            "notes": (it.get("notes") or "").strip(),
        })

    totals = _totals_from_items(items, tax["rate"], tax["apply"])
    pair_id = new_id("icp")
    seller_id = new_id("ict")
    buyer_id = new_id("ict")
    number_s = await _next_number(seller)
    number_b = await _next_number(buyer)
    doc_date = payload.get("doc_date") or _today()
    due_date = payload.get("due_date") or ""
    seller_snap = await _entity_snapshot(seller)
    buyer_snap = await _entity_snapshot(buyer)
    submit_now = bool(payload.get("submit_now"))

    # Bila submit_now → periksa ambang persetujuan (samakan gerbang dengan confirm()).
    if submit_now:
        await _assert_may_release(actor_user, float(totals["total"]), seller)

    status = "confirmed" if submit_now else "draft"
    ts = now_iso()
    submit_ts = ts if submit_now else ""

    common = {
        "pair_id": pair_id,
        "seller_entity_id": seller,
        "seller_entity_name": seller_snap["name"],
        "buyer_entity_id": buyer,
        "buyer_entity_name": buyer_snap["name"],
        "counterpart_number": "",  # diisi setelah insert (nomor kembar)
        "items": items,
        "subtotal": totals["subtotal"],
        "tax_apply": tax["apply"],
        "tax_rate": tax["rate"],
        "tax_amount": totals["tax"],
        "grand_total": totals["total"],
        "pricing_mode": pricing_mode,
        "ppn_mode": ppn_mode,
        "contract_id": (payload.get("contract_id") or "").strip(),
        # FASE E-7 (E7d) & E8.12/E9.2 — ASAL PERMINTAAN menempel di transaksinya.
        # Tanpa kolom ini, pertanyaan "transaksi antar-PT ini untuk pesanan siapa?"
        # hanya bisa dijawab dari catatan bebas — dan papan pending SO tidak bisa
        # menampilkan janji barang dari PT lain.
        "source_request_id": (payload.get("source_request_id") or "").strip(),
        "source_request_number": (payload.get("source_request_number") or "").strip(),
        "source_order_id": (payload.get("source_order_id") or "").strip(),
        "source_order_number": (payload.get("source_order_number") or "").strip(),
        "doc_date": doc_date,
        "due_date": due_date,
        "notes": (payload.get("notes") or "").strip(),
        "status": status,
        "confirmed_at": submit_ts,
        "confirmed_by": actor if submit_now else "",
        "settled_amount": 0.0,          # akumulasi settlement
        "created_at": ts,
        "created_by": actor,
        "updated_at": ts,
        "updated_by": actor,
    }
    seller_doc = {
        **common,
        "id": seller_id,
        "number": number_s,
        "role": "seller",
        "entity_id": seller,  # scope
        "counterpart_id": buyer_id,
    }
    buyer_doc = {
        **common,
        "id": buyer_id,
        "number": number_b,
        "role": "buyer",
        "entity_id": buyer,
        "counterpart_id": seller_id,
    }
    seller_doc["counterpart_number"] = number_b
    buyer_doc["counterpart_number"] = number_s

    await db[COLL_ICT].insert_many([seller_doc, buyer_doc])
    await _link_refs(pair_id)

    if submit_now:
        # Auto-post GL saat confirmed (US2/US3)
        await _post_gl_for_pair(pair_id, actor)
        await _update_account_balance(seller, buyer)
        # US7/INV-IC-03 — margin antar-PT langsung dieliminasi di laporan grup.
        await _sync_group_elimination(pair_id)

    return await get_by_pair(pair_id)


async def get_by_pair(pair_id: str) -> Optional[Dict[str, Any]]:
    docs = await db[COLL_ICT].find({"pair_id": pair_id}, {"_id": 0}).to_list(2)
    if not docs:
        return None
    seller = next((d for d in docs if d.get("role") == "seller"), docs[0])
    buyer = next((d for d in docs if d.get("role") == "buyer"), docs[-1] if len(docs) > 1 else None)
    return {"pair_id": pair_id, "seller": safe_doc(seller),
            "buyer": safe_doc(buyer) if buyer else None}


async def get_one(interco_id: str) -> Optional[Dict[str, Any]]:
    doc = await db[COLL_ICT].find_one({"id": interco_id}, {"_id": 0})
    if not doc:
        return None
    pair = await get_by_pair(doc["pair_id"])
    return pair


async def list_transactions(scope_entity_ids: List[str], entity_id: str = "",
                            status: str = "", role: str = "",
                            limit: int = 200) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"entity_id": {"$in": scope_entity_ids} if scope_entity_ids else None}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    if status:
        q["status"] = status
    if role in ("seller", "buyer"):
        q["role"] = role
    if q.get("entity_id") is None:
        q.pop("entity_id")
    rows = await db[COLL_ICT].find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return [safe_doc(r) for r in rows]


# ── Aksi siklus ──────────────────────────────────────────────────────────────
async def _pair_docs(pair_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    docs = await db[COLL_ICT].find({"pair_id": pair_id}, {"_id": 0}).to_list(2)
    if len(docs) != 2:
        raise IntercoError("Pasangan dokumen tidak lengkap.")
    seller = next(d for d in docs if d.get("role") == "seller")
    buyer = next(d for d in docs if d.get("role") == "buyer")
    return seller, buyer


async def _set_pair_status(pair_id: str, status: str, actor: str,
                           extra: Optional[Dict[str, Any]] = None) -> None:
    upd = {"status": status, "updated_at": now_iso(), "updated_by": actor}
    if extra:
        upd.update(extra)
    await db[COLL_ICT].update_many({"pair_id": pair_id}, {"$set": upd})


async def confirm(interco_id: str, actor_user: Dict[str, Any]) -> Dict[str, Any]:
    doc = await db[COLL_ICT].find_one({"id": interco_id}, {"_id": 0})
    if not doc:
        raise IntercoError("Transaksi tidak ditemukan.")
    if doc["status"] != "draft":
        raise IntercoError(f"Hanya draf yang bisa dikonfirmasi (status sekarang: {STATUS_LABEL.get(doc['status'], doc['status'])}).")

    grand = float(doc.get("grand_total") or 0)
    await _assert_may_release(actor_user, grand, doc["seller_entity_id"])

    await _set_pair_status(doc["pair_id"], "confirmed", actor_user.get("name", ""),
                           {"confirmed_at": now_iso(),
                            "confirmed_by": actor_user.get("name", "")})
    await _post_gl_for_pair(doc["pair_id"], actor_user.get("name", ""))
    await _update_account_balance(doc["seller_entity_id"], doc["buyer_entity_id"])
    await _sync_group_elimination(doc["pair_id"])
    return await get_by_pair(doc["pair_id"])


async def ship(interco_id: str, actor: str) -> Dict[str, Any]:
    doc = await db[COLL_ICT].find_one({"id": interco_id}, {"_id": 0})
    if not doc:
        raise IntercoError("Transaksi tidak ditemukan.")
    if doc["status"] != "confirmed":
        raise IntercoError("Hanya transaksi terkonfirmasi yang bisa dikirim.")
    await _set_pair_status(doc["pair_id"], "shipped", actor,
                           {"shipped_at": now_iso(), "shipped_by": actor})
    return await get_by_pair(doc["pair_id"])


async def receive(interco_id: str, actor: str) -> Dict[str, Any]:
    doc = await db[COLL_ICT].find_one({"id": interco_id}, {"_id": 0})
    if not doc:
        raise IntercoError("Transaksi tidak ditemukan.")
    if doc["status"] not in ("confirmed", "shipped"):
        raise IntercoError(
            "Transaksi harus dikonfirmasi lebih dulu sebelum barangnya bisa diterima "
            f"(status sekarang: {STATUS_LABEL.get(doc['status'], doc['status'])}).")
    # Penerimaan MENGGERAKKAN persediaan pembeli (transit → persediaan). Karena itu
    # ia hanya sah bila barangnya benar-benar berpindah lewat tugas gudang — kalau
    # tidak, GL persediaan naik untuk barang yang tidak ada di gudang mana pun.
    task = await db.warehouse_transfers.find_one(
        {"interco_pair_id": doc["pair_id"], "status": "completed"},
        {"_id": 0, "code": 1})
    if not task:
        raise IntercoError(
            "Barangnya belum berpindah di gudang. Terbitkan **Tugas Gudang** dan minta "
            "gudang menyetujuinya — status 'Diterima' akan tercatat otomatis beserta "
            "jurnal penerimaan (persediaan pembeli naik saat barangnya benar-benar ada).")
    await _set_pair_status(doc["pair_id"], "received", actor,
                           {"received_at": now_iso(), "received_by": actor})
    await post_gl_on_delivery(doc["pair_id"], actor)
    await _sync_group_elimination(doc["pair_id"])
    return await get_by_pair(doc["pair_id"])


async def invoice(interco_id: str, actor: str) -> Dict[str, Any]:
    doc = await db[COLL_ICT].find_one({"id": interco_id}, {"_id": 0})
    if not doc:
        raise IntercoError("Transaksi tidak ditemukan.")
    if doc["status"] not in ("received", "shipped"):
        raise IntercoError("Faktur internal hanya bisa diterbitkan setelah barang dikirim/diterima.")
    await _set_pair_status(doc["pair_id"], "invoiced", actor,
                           {"invoiced_at": now_iso(), "invoiced_by": actor})
    return await get_by_pair(doc["pair_id"])


async def cancel(interco_id: str, actor: str, reason: str = "") -> Dict[str, Any]:
    doc = await db[COLL_ICT].find_one({"id": interco_id}, {"_id": 0})
    if not doc:
        raise IntercoError("Transaksi tidak ditemukan.")
    if doc["status"] in ("settled",):
        raise IntercoError("Transaksi yang sudah lunas tidak bisa dibatalkan.")
    if doc["status"] in ("shipped", "received", "invoiced"):
        raise IntercoError("Transaksi yang sudah dikirim tidak bisa dibatalkan begitu saja — buat retur.")
    if doc["status"] == "cancelled":
        raise IntercoError("Transaksi ini sudah dibatalkan.")
    reason = (reason or "").strip()
    was_posted = doc["status"] == "confirmed"
    if was_posted and len(reason) < 5:
        # G-1 — koreksi WAJIB ber-alasan: jurnal yang sudah terbit hanya boleh
        # dibalik dengan sebab yang tercatat, bukan dihapus senyap.
        raise IntercoError(
            "Transaksi yang sudah dikonfirmasi hanya bisa dibatalkan dengan ALASAN "
            "(minimal 5 huruf) karena jurnalnya akan dibalik di kedua buku.")
    tugas = await db.warehouse_transfers.find_one(
        {"interco_pair_id": doc["pair_id"],
         "status": {"$nin": ["rejected", "cancelled"]}},
        {"_id": 0, "code": 1, "status": 1})
    if tugas and tugas.get("status") == "completed":
        raise IntercoError(
            f"Barangnya sudah berpindah lewat tugas gudang {tugas.get('code')} — "
            f"batalkan lewat retur, bukan pembatalan dokumen.")

    await _set_pair_status(doc["pair_id"], "cancelled", actor,
                           {"cancelled_at": now_iso(), "cancelled_by": actor,
                            "cancel_reason": reason})
    reversed_count = 0
    if was_posted:
        reversed_count = await _reverse_gl_for_pair(doc["pair_id"], actor, reason)
    if tugas:
        # Tugas gudang yang masih menunggu persetujuan wajib ikut batal supaya
        # roll penjual tidak terkunci selamanya.
        try:
            from services.roll_service import release_transfer_rolls
            await db.warehouse_transfers.update_one(
                {"interco_pair_id": doc["pair_id"], "status": "waiting_approval"},
                {"$set": {"status": "cancelled", "updated_at": now_iso(),
                          "rejected_reason": f"Transaksi antar-PT dibatalkan: {reason}"}})
            tr = await db.warehouse_transfers.find_one(
                {"interco_pair_id": doc["pair_id"], "status": "cancelled"}, {"_id": 0, "id": 1})
            if tr:
                await release_transfer_rolls(tr["id"])
                # Layar harus jujur: tugasnya sudah batal, bukan "menunggu gudang".
                await db[COLL_ICT].update_many(
                    {"pair_id": doc["pair_id"]},
                    {"$set": {"warehouse_transfer_status": "cancelled",
                              "updated_at": now_iso()}})
        except Exception as exc:  # noqa: BLE001
            print(f"[interco] gagal membatalkan tugas gudang: {exc}")
    await _update_account_balance(doc["seller_entity_id"], doc["buyer_entity_id"])
    await _sync_group_elimination(doc["pair_id"])
    res = await get_by_pair(doc["pair_id"])
    res["reversed_journals"] = reversed_count
    return res


# ═══════════════════════════════════════════════════════════════════════════
# GL POSTING (INV-IC-01, INV-IC-05)
# ═══════════════════════════════════════════════════════════════════════════
async def _post_gl_for_pair(pair_id: str, actor: str) -> None:
    """Post jurnal berpasangan dengan HARGA JUAL (bukan sekadar at-cost).

    **Saat DIKONFIRMASI** (dokumen & utang lahir — barangnya belum tentu jalan):

    Buku PENJUAL:
      Dr 1-1250 IC-AR                  = grand_total (subtotal + PPN)
        Cr 4-1000 Pendapatan             = subtotal (harga jual)
        Cr 2-1200 PPN Keluaran           = tax_amount (bila ber-PPN)

    Buku PEMBELI:
      Dr 1-1310 Persediaan Dalam Perjalanan = subtotal (harga beli internal)
      Dr 1-1500 PPN Masukan                 = tax_amount (bila ber-PPN)
        Cr 2-1250 IC-AP                       = grand_total

    **HPP penjual & masuknya persediaan pembeli TIDAK diposting di sini** — itu
    mengikuti BARANGNYA (lihat `post_gl_on_delivery`, dipanggil saat tugas gudang
    selesai). Kalau dipaksa di sini, persediaan pembeli membengkak & persediaan
    penjual menyusut untuk barang yang belum berpindah — tepatnya drift GL↔subledger
    yang dulu memunculkan WARN INV-GL-DRIFT.

    Idempotent via source_type='interco_transaction' + source_id=pair_id:{seller|buyer}.
    """
    seller, buyer = await _pair_docs(pair_id)
    # Guard idempoten
    if await gl_service._already_posted("interco_transaction", f"{pair_id}:seller") or \
       await gl_service._already_posted("interco_transaction", f"{pair_id}:buyer"):
        return

    subtotal = float(seller.get("subtotal") or 0)
    tax_amt = float(seller.get("tax_amount") or 0)
    grand = float(seller.get("grand_total") or 0)
    if grand <= EPS:
        return

    code = seller.get("number") or pair_id
    date = seller.get("confirmed_at") or seller.get("created_at") or now_iso()
    ent_s = seller["seller_entity_id"]
    ent_b = seller["buyer_entity_id"]

    # ── Buku PENJUAL: Piutang IC = Pendapatan + PPN Keluaran
    lines_s: List[Dict[str, Any]] = [
        {"account_code": gl_service.ACC_IC_AR, "debit": grand, "credit": 0.0,
         "description": f"Piutang antar-PT {code} → {buyer.get('buyer_entity_name', ent_b)}"},
        {"account_code": gl_service.ACC_PENDAPATAN, "debit": 0.0, "credit": subtotal,
         "description": f"Pendapatan antar-PT {code}"},
    ]
    if tax_amt > EPS:
        lines_s.append({"account_code": gl_service.ACC_PPN_OUT, "debit": 0.0, "credit": tax_amt,
                        "description": f"PPN Keluaran antar-PT {code}"})
    await gl_service._insert_entry(
        lines=lines_s, description=f"Penjualan antar-PT {code}",
        date=date, source_type="interco_transaction",
        source_id=f"{pair_id}:seller", entity_id=ent_s,
        created_by=actor or "system", source_label=code,
    )

    # ── Buku PEMBELI: Persediaan Dalam Perjalanan + PPN Masukan = Utang IC
    lines_b: List[Dict[str, Any]] = [
        {"account_code": gl_service.ACC_PERSEDIAAN_TRANSIT, "debit": subtotal, "credit": 0.0,
         "description": (f"Barang antar-PT dalam perjalanan {buyer.get('number', '')} "
                         f"← {seller.get('seller_entity_name', ent_s)}")},
    ]
    if tax_amt > EPS:
        lines_b.append({"account_code": gl_service.ACC_PPN_IN, "debit": tax_amt, "credit": 0.0,
                        "description": f"PPN Masukan antar-PT {code}"})
    lines_b.append({"account_code": gl_service.ACC_IC_AP, "debit": 0.0, "credit": grand,
                    "description": f"Utang antar-PT {buyer.get('number', '')}"})
    await gl_service._insert_entry(
        lines=lines_b, description=f"Pembelian antar-PT {buyer.get('number', '')}",
        date=date, source_type="interco_transaction",
        source_id=f"{pair_id}:buyer", entity_id=ent_b,
        created_by=actor or "system", source_label=buyer.get("number", code),
    )


async def post_gl_on_delivery(pair_id: str, actor: str,
                              cost_override: Optional[float] = None) -> Dict[str, Any]:
    """Jurnal yang MENGIKUTI BARANG — diposting saat perpindahan fisik selesai.

    Buku PENJUAL (barang keluar):
      Dr 5-1000 HPP            = HPP (WAC) barang yang keluar
        Cr 1-1300 Persediaan     = HPP

    Buku PEMBELI (barang masuk):
      Dr 1-1300 Persediaan     = harga beli internal (nilai roll yang dinilai ulang)
        Cr 1-1310 Persediaan Dalam Perjalanan = nilai yang sama

    Dengan pemisahan ini, GL 1-1300 kedua PT **selalu** sejalan dengan subledger roll
    (INV-GL-DRIFT bersih), dan "barang sudah dibeli tapi belum datang" punya tempat
    sendiri yang jujur di neraca pembeli.

    Idempotent via source_id `{pair}:cogs` (penjual) & `{pair}:receipt` (pembeli).
    """
    seller, buyer = await _pair_docs(pair_id)
    out: Dict[str, Any] = {"cogs": 0.0, "receipt": 0.0}
    code = seller.get("number") or pair_id
    date = now_iso()
    ent_s = seller["seller_entity_id"]
    ent_b = seller["buyer_entity_id"]

    # ── HPP penjual: biaya NYATA roll yang keluar (specific identification).
    # Memakai WAC × qty membuat GL 1-1300 penjual selalu selisih tipis dari subledger
    # (roll punya harga perolehan masing-masing). Karena tugas gudang tahu roll mana
    # yang berpindah, biayanya dihitung dari roll itu; WAC hanya cadangan terakhir.
    if not await gl_service._already_posted("interco_transaction", f"{pair_id}:cogs"):
        if cost_override is not None and cost_override > EPS:
            total_cost = round(float(cost_override), 2)
        else:
            total_cost = 0.0
            for it in seller.get("items", []):
                wac = await wac_for_product(it["product_id"], entity_id=ent_s, use_cache=False)
                total_cost += float(it["quantity"]) * float(wac.get("wac") or 0)
        total_cost = round(total_cost, 2)
        if total_cost > EPS:
            lines_c = gl_service._balanced_pair(
                gl_service.ACC_HPP, gl_service.ACC_PERSEDIAAN, total_cost,
                f"HPP antar-PT {code} (barang keluar gudang)")
            await gl_service._insert_entry(
                lines=lines_c, description=f"HPP antar-PT {code}",
                date=date, source_type="interco_transaction",
                source_id=f"{pair_id}:cogs", entity_id=ent_s,
                created_by=actor or "system", source_label=code,
            )
            out["cogs"] = total_cost

    # ── Penerimaan pembeli: transit → persediaan
    if not await gl_service._already_posted("interco_transaction", f"{pair_id}:receipt"):
        subtotal = round(float(seller.get("subtotal") or 0), 2)
        if subtotal > EPS:
            lines_r = gl_service._balanced_pair(
                gl_service.ACC_PERSEDIAAN, gl_service.ACC_PERSEDIAAN_TRANSIT, subtotal,
                f"Penerimaan barang antar-PT {buyer.get('number', '')} (harga beli internal)")
            await gl_service._insert_entry(
                lines=lines_r,
                description=f"Penerimaan barang antar-PT {buyer.get('number', '')}",
                date=date, source_type="interco_transaction",
                source_id=f"{pair_id}:receipt", entity_id=ent_b,
                created_by=actor or "system", source_label=buyer.get("number", code),
            )
            out["receipt"] = subtotal
    return out


# ═══════════════════════════════════════════════════════════════════════════
# SALDO ANTAR-PT (interco_accounts) — INV-IC-04
# ═══════════════════════════════════════════════════════════════════════════
def ica_ar_id(seller_entity_id: str, buyer_entity_id: str) -> str:
    """Id baris PIUTANG milik PT penjual untuk arah dagang penjual→pembeli."""
    return f"ica_{seller_entity_id}_{buyer_entity_id}_ar"


def ica_ap_id(buyer_entity_id: str, seller_entity_id: str) -> str:
    """Id baris UTANG milik PT pembeli untuk arah dagang penjual→pembeli."""
    return f"ica_{buyer_entity_id}_{seller_entity_id}_ap"


def ica_pair_key(seller_entity_id: str, buyer_entity_id: str) -> str:
    """Kunci ARAH DAGANG (penjual>pembeli) — penjodoh piutang↔utang (INV-IC-02)."""
    return f"{seller_entity_id}>{buyer_entity_id}"


async def _update_account_balance(seller_entity_id: str, buyer_entity_id: str) -> None:
    """Recompute saldo pasangan PT dari transaksi terbuka & settlement.

    Untuk ARAH DAGANG (seller→buyer) ada dua baris — satu per sudut pandang buku:
      * `ica_{seller}_{buyer}_ar` — piutang (receivable) di buku PT penjual.
      * `ica_{buyer}_{seller}_ap` — utang (payable) di buku PT pembeli.
    INV-IC-02: dua baris ini harus sama besar.

    KN-G6-ICA-CLOBBER (ditutup di sesi ini) — dulu id-nya `ica_{X}_{Y}` TANPA
    penanda peran, sehingga **piutang arah A→B dan utang arah B→A menempati SATU
    dokumen yang sama**. Begitu pasangan PT yang sama berdagang DUA ARAH — hal
    yang normal terjadi lewat Permintaan Internal ("stok saya habis, kirim dari
    PT sebelah") — recompute arah kedua MENIMPA saldo arah pertama dan utang yang
    nyata **hilang dari layar tanpa satu pun pesan**. Terukur pada data demo:
    utang CV Kanda Suka ke KSC Rp 1.766.010 menjadi Rp 0 hanya karena Kanda
    menerbitkan transaksi arah balik. Sejak sekarang identitas baris memuat arah
    dagang DAN peran, jadi dua arah hidup berdampingan.
    """
    docs = await db[COLL_ICT].find({
        "seller_entity_id": seller_entity_id,
        "buyer_entity_id": buyer_entity_id,
        "role": "seller",
        "status": {"$in": list(OPEN_STATUSES) + ["settled"]},
    }, {"_id": 0}).to_list(1000)
    open_docs = [d for d in docs if d.get("status") in OPEN_STATUSES]
    gross = sum(float(d.get("grand_total") or 0) for d in open_docs)
    settled = sum(float(d.get("settled_amount") or 0) for d in open_docs)
    # FASE G-6b — barang yang DIRETUR mengurangi utang antar-PT persis seperti
    # pelunasan (nilai dokumen sendiri TIDAK pernah diedit — append-only).
    returned = sum(float(d.get("returned_amount") or 0) for d in open_docs)
    outstanding = round(gross - settled - returned, 2)
    seller_snap = await _entity_snapshot(seller_entity_id)
    buyer_snap = await _entity_snapshot(buyer_entity_id)
    ts = now_iso()
    # Umur saldo dihitung dari AKTIVITAS NYATA (dokumen & settlement), bukan dari
    # `updated_at` baris ini — lihat KN-G6-IDLE-FAKE di memory/BUG_REGISTRY.md.
    try:
        from services import interco_reminder as _rem
        activity = await _rem.last_activity_at(seller_entity_id, buyer_entity_id)
    except Exception as exc:  # noqa: BLE001 — hanya penanda umur, bukan uang
        print(f"[interco] hitung aktivitas terakhir gagal: {exc}")
        activity = ""
    # Sisi penjual = piutang (receivable)
    ica_ar = ica_ar_id(seller_entity_id, buyer_entity_id)
    pair_key = ica_pair_key(seller_entity_id, buyer_entity_id)
    await db[COLL_ICA].update_one(
        {"id": ica_ar},
        {"$set": {
            "id": ica_ar,
            # Scope PT pemilik baris ini (F0-C: setiap koleksi ber-`entity_id`
            # ikut aturan isolasi lintas-PT; tanpa ini baris saldo tak bisa
            # ditapis per buku dan gate scoping memerah).
            "entity_id": seller_entity_id,
            "from_entity_id": seller_entity_id,
            "from_entity_name": seller_snap["name"],
            "to_entity_id": buyer_entity_id,
            "to_entity_name": buyer_snap["name"],
            # Arah dagang disimpan EKSPLISIT — layar & invarian tidak perlu
            # menyimpulkannya dari peran (sumber KN-G6-ICA-CLOBBER dulu).
            "pair_key": pair_key,
            "seller_entity_id": seller_entity_id,
            "seller_entity_name": seller_snap["name"],
            "buyer_entity_id": buyer_entity_id,
            "buyer_entity_name": buyer_snap["name"],
            "role": "receivable",
            "open_count": len(open_docs),
            "gross_amount": round(gross, 2),
            "settled_amount": round(settled, 2),
            "returned_amount": round(returned, 2),
            "outstanding": outstanding,
            "last_activity_at": activity,
            "updated_at": ts,
        }}, upsert=True,
    )
    # Sisi pembeli = utang (payable) — cerminan angka yang sama, arah terbalik.
    ica_ap = ica_ap_id(buyer_entity_id, seller_entity_id)
    await db[COLL_ICA].update_one(
        {"id": ica_ap},
        {"$set": {
            "id": ica_ap,
            "entity_id": buyer_entity_id,
            "from_entity_id": buyer_entity_id,
            "from_entity_name": buyer_snap["name"],
            "to_entity_id": seller_entity_id,
            "to_entity_name": seller_snap["name"],
            "pair_key": pair_key,
            "seller_entity_id": seller_entity_id,
            "seller_entity_name": seller_snap["name"],
            "buyer_entity_id": buyer_entity_id,
            "buyer_entity_name": buyer_snap["name"],
            "role": "payable",
            "open_count": len(open_docs),
            "gross_amount": round(gross, 2),
            "settled_amount": round(settled, 2),
            "returned_amount": round(returned, 2),
            "outstanding": outstanding,
            "last_activity_at": activity,
            "updated_at": ts,
        }}, upsert=True,
    )
    # Baris warisan tanpa penanda peran (skema sebelum KN-G6-ICA-CLOBBER ditutup)
    # dibuang begitu arahnya dihitung ulang, supaya layar tidak menampilkan angka
    # kembar yang sudah tidak dipelihara siapa pun.
    await db[COLL_ICA].delete_many({"id": {"$in": [
        f"ica_{seller_entity_id}_{buyer_entity_id}",
        f"ica_{buyer_entity_id}_{seller_entity_id}",
    ]}})


async def list_accounts(scope_entity_ids: List[str]) -> List[Dict[str, Any]]:
    """Saldo antar-PT untuk semua pasangan yang menyentuh scope."""
    if not scope_entity_ids:
        return []
    q = {"$or": [{"from_entity_id": {"$in": scope_entity_ids}},
                 {"to_entity_id": {"$in": scope_entity_ids}}]}
    rows = await db[COLL_ICA].find(q, {"_id": 0}).sort("outstanding", -1).to_list(1000)
    reminder_days = int(await _config("antar_entitas.settlement_reminder_days") or 30)
    today = datetime.now(timezone.utc)
    for r in rows:
        # Umur = sejak AKTIVITAS NYATA terakhir (dokumen/settlement). `updated_at`
        # hanya cadangan untuk baris lama yang belum punya `last_activity_at`.
        upd = r.get("last_activity_at") or r.get("updated_at") or ""
        aging = 0
        if upd:
            try:
                raw = str(upd)
                if len(raw) == 10:
                    raw = f"{raw}T00:00:00+00:00"
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                aging = max(0, (today - dt).days)
            except Exception:
                aging = 0
        r["aging_days"] = aging
        r["reminder_limit_days"] = reminder_days
        r["reminder_active"] = (r.get("outstanding", 0) > EPS and aging >= reminder_days)
    return [safe_doc(r) for r in rows]


async def get_account(from_entity_id: str, to_entity_id: str,
                      role: str = "payable") -> Dict[str, Any]:
    """Satu baris saldo dari sudut pandang `from_entity_id` terhadap `to_entity_id`.

    `role="payable"` (bawaan) menjawab **"berapa utang `from` kepada `to`?"** —
    itu pertanyaan yang dipakai tombol Ingatkan & Buat Settlement. `role="receivable"`
    menjawab kebalikannya (piutang `from` atas `to`). Peran WAJIB ikut karena satu
    pasangan PT bisa berdagang dua arah sekaligus; tanpa peran, jawabannya ambigu
    (akar KN-G6-ICA-CLOBBER).
    """
    role = (role or "payable").strip().lower()
    if role not in ("payable", "receivable"):
        raise IntercoError("Peran saldo antar-PT hanya 'payable' atau 'receivable'.")
    suffix = "ap" if role == "payable" else "ar"
    ica_id = f"ica_{from_entity_id}_{to_entity_id}_{suffix}"
    row = await db[COLL_ICA].find_one({"id": ica_id}, {"_id": 0})
    if not row:
        # Basis data yang belum dimigrasikan masih memakai id tanpa penanda peran.
        row = await db[COLL_ICA].find_one(
            {"id": f"ica_{from_entity_id}_{to_entity_id}", "role": role}, {"_id": 0})
    if not row:
        return {"id": ica_id, "from_entity_id": from_entity_id,
                "to_entity_id": to_entity_id, "role": role,
                "outstanding": 0.0, "open_count": 0}
    return safe_doc(row)


# ═══════════════════════════════════════════════════════════════════════════
# SETTLEMENT / NETTING (US6, pola kontrabon G-7)
# ═══════════════════════════════════════════════════════════════════════════
async def create_settlement(payload: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    payer = (payload.get("payer_entity_id") or "").strip()
    payee = (payload.get("payee_entity_id") or "").strip()
    if not payer or not payee or payer == payee:
        raise IntercoError("Pilih PT pembayar dan PT penerima yang berbeda.")
    picks = payload.get("transactions") or []
    if not picks:
        raise IntercoError("Minimal satu transaksi harus dipilih untuk settlement.")

    total_applied = 0.0
    applied_rows: List[Dict[str, Any]] = []
    for p in picks:
        ict_id = (p.get("interco_id") or "").strip()
        seller_doc = await db[COLL_ICT].find_one({"id": ict_id, "role": "seller"}, {"_id": 0})
        if not seller_doc:
            raise IntercoError(f"Transaksi {ict_id} tidak ditemukan.")
        if seller_doc["seller_entity_id"] != payee or seller_doc["buyer_entity_id"] != payer:
            raise IntercoError(
                f"Transaksi {seller_doc.get('number')} bukan milik pasangan PT ini "
                f"(butuh penjual={payee}, pembeli={payer}).")
        if seller_doc["status"] not in OPEN_STATUSES:
            raise IntercoError(
                f"Transaksi {seller_doc.get('number')} berstatus "
                f"{STATUS_LABEL.get(seller_doc['status'], seller_doc['status'])}, "
                f"tidak bisa dilunaskan lagi.")
        remaining = round(float(seller_doc.get("grand_total") or 0) -
                          float(seller_doc.get("settled_amount") or 0) -
                          float(seller_doc.get("returned_amount") or 0), 2)
        if remaining <= EPS:
            raise IntercoError(
                f"Transaksi {seller_doc.get('number')} sudah lunas "
                f"(atau seluruh nilainya sudah diretur).")
        req = p.get("applied_amount")
        applied = float(req) if req not in (None, "", 0) else remaining
        if applied > remaining + EPS:
            raise IntercoError(
                f"Nilai yang diterapkan {rupiah(applied)} melebihi sisa transaksi "
                f"{seller_doc.get('number')} ({rupiah(remaining)}).")
        applied = round(applied, 2)
        total_applied += applied
        applied_rows.append({
            "interco_id": ict_id,
            "counterpart_id": seller_doc.get("counterpart_id"),
            "pair_id": seller_doc.get("pair_id"),
            "number": seller_doc.get("number"),
            "counterpart_number": seller_doc.get("counterpart_number"),
            "grand_total": float(seller_doc.get("grand_total") or 0),
            "previous_settled": float(seller_doc.get("settled_amount") or 0),
            "applied_amount": applied,
        })

    total_applied = round(total_applied, 2)
    if total_applied <= EPS:
        raise IntercoError("Total settlement harus > 0.")

    settle_id = new_id("ics")
    number = await next_doc_number(COLL_ICS, "number", "ICS-", entity_id=payer)
    settle_date = payload.get("settle_date") or _today()
    method = (payload.get("method") or "netting").strip().lower()
    payer_snap = await _entity_snapshot(payer)
    payee_snap = await _entity_snapshot(payee)
    doc = {
        "id": settle_id,
        "number": number,
        "entity_id": payer,      # scope: PT yang membayar
        "payer_entity_id": payer,
        "payer_entity_name": payer_snap["name"],
        "payee_entity_id": payee,
        "payee_entity_name": payee_snap["name"],
        "settle_date": settle_date,
        "method": method,
        "bank_account_id": (payload.get("bank_account_id") or "").strip(),
        "notes": (payload.get("notes") or "").strip(),
        "applied": applied_rows,
        "total_applied": total_applied,
        "status": "posted",
        "created_at": now_iso(),
        "created_by": actor,
    }
    await db[COLL_ICS].insert_one(doc)

    # Update settled_amount per transaksi (kedua dokumen kembar)
    ts = now_iso()
    for row in applied_rows:
        for _id in (row["interco_id"], row["counterpart_id"]):
            cur = await db[COLL_ICT].find_one({"id": _id}, {"_id": 0, "grand_total": 1,
                                                             "settled_amount": 1,
                                                             "returned_amount": 1})
            if not cur:
                continue
            new_settled = round(float(cur.get("settled_amount") or 0) + row["applied_amount"], 2)
            grand = float(cur.get("grand_total") or 0)
            returned = float(cur.get("returned_amount") or 0)
            new_status_update: Dict[str, Any] = {"settled_amount": new_settled,
                                                  "updated_at": ts,
                                                  "updated_by": actor}
            if new_settled + returned >= grand - EPS:
                new_status_update["status"] = "settled"
                new_status_update["settled_at"] = ts
            await db[COLL_ICT].update_one({"id": _id}, {"$set": new_status_update})

    # Post GL settlement (kedua buku)
    await _post_gl_settlement(doc, actor)

    # Refresh saldo pasangan (payee=penjual, payer=pembeli). Cukup satu panggilan;
    # rewrite _update_account_balance sudah menulis kedua sisi (receivable + payable).
    await _update_account_balance(payee, payer)

    # US7/INV-IC-03 — sisa IC-AR/IC-AP yang dieliminasi ikut mengecil setelah
    # settlement; kalau tidak disinkronkan, konsolidasi menghapus saldo hantu.
    for row in applied_rows:
        await _sync_group_elimination(row["pair_id"])

    # US10 — jejak dua arah: settlement MELUNASI transaksi-transaksi ini.
    try:
        from services import doc_refs_service as _refs
        for row in applied_rows:
            for _id in (row["interco_id"], row["counterpart_id"]):
                if _id:
                    await _refs.safe_link(("interco_settlement", settle_id),
                                          ("interco_transaction", _id), "settles",
                                          note=f"Settlement antar-PT {number}")
    except Exception as exc:  # noqa: BLE001
        print(f"[interco] tautan settlement gagal: {exc}")

    return safe_doc(doc)


async def _post_gl_settlement(doc: Dict[str, Any], actor: str) -> None:
    """Post jurnal settlement.

    Kalau method='netting' (bawaan): tidak ada uang keluar; sekadar saling hapus
    piutang/utang antar-PT.
      Buku PAYER (pembeli):  Dr 2-1250 IC-AP  / Cr 1-1250 IC-AR (bila juga punya piutang)
                             ATAU Cr 1-1300 (tidak → tidak ada kas keluar)
      Buku PAYEE (penjual):  Dr 2-1250 IC-AP / Cr 1-1250 IC-AR

    Model sederhana: bila netting, kedua buku hanya mengosongkan saldo antar-PT
    (Payer Dr IC-AP / Cr IC-AR; Payee Dr IC-AP / Cr IC-AR). Bila transfer/cash:
    payer Dr IC-AP / Cr Bank; payee Dr Bank / Cr IC-AR.
    """
    total = float(doc.get("total_applied") or 0)
    if total <= EPS:
        return
    method = doc.get("method", "netting")
    sid = doc["id"]
    if await gl_service._already_posted("interco_settlement", f"{sid}:payer") or \
       await gl_service._already_posted("interco_settlement", f"{sid}:payee"):
        return
    date = doc.get("settle_date") or now_iso()
    label = doc.get("number", sid)
    payer_ent = doc["payer_entity_id"]
    payee_ent = doc["payee_entity_id"]

    if method == "netting":
        # Payer: Dr IC-AP / Cr IC-AR (saling hapus piutang balik bila ada)
        lines_payer = gl_service._balanced_pair(
            gl_service.ACC_IC_AP, gl_service.ACC_IC_AR, total,
            f"Netting antar-PT {label} → {doc.get('payee_entity_name', '')}")
        await gl_service._insert_entry(
            lines=lines_payer, description=f"Settlement antar-PT (netting) {label}",
            date=date, source_type="interco_settlement",
            source_id=f"{sid}:payer", entity_id=payer_ent,
            created_by=actor or "system", source_label=label,
        )
        # Payee: Dr IC-AP / Cr IC-AR
        lines_payee = gl_service._balanced_pair(
            gl_service.ACC_IC_AP, gl_service.ACC_IC_AR, total,
            f"Netting antar-PT {label} ← {doc.get('payer_entity_name', '')}")
        await gl_service._insert_entry(
            lines=lines_payee, description=f"Settlement antar-PT (netting) {label}",
            date=date, source_type="interco_settlement",
            source_id=f"{sid}:payee", entity_id=payee_ent,
            created_by=actor or "system", source_label=label,
        )
    else:
        # transfer/cash: uang benar-benar berpindah
        cash_acc = gl_service.ACC_KAS_BESAR
        # Payer: Dr IC-AP / Cr Bank
        lines_payer = gl_service._balanced_pair(
            gl_service.ACC_IC_AP, cash_acc, total,
            f"Bayar utang antar-PT {label} → {doc.get('payee_entity_name', '')}")
        await gl_service._insert_entry(
            lines=lines_payer, description=f"Bayar utang antar-PT {label}",
            date=date, source_type="interco_settlement",
            source_id=f"{sid}:payer", entity_id=payer_ent,
            created_by=actor or "system", source_label=label,
        )
        # Payee: Dr Bank / Cr IC-AR
        lines_payee = gl_service._balanced_pair(
            cash_acc, gl_service.ACC_IC_AR, total,
            f"Terima pelunasan antar-PT {label} ← {doc.get('payer_entity_name', '')}")
        await gl_service._insert_entry(
            lines=lines_payee, description=f"Terima pelunasan antar-PT {label}",
            date=date, source_type="interco_settlement",
            source_id=f"{sid}:payee", entity_id=payee_ent,
            created_by=actor or "system", source_label=label,
        )


async def list_settlements(scope_entity_ids: List[str], entity_id: str = "",
                           limit: int = 200) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        q["$or"] = [{"payer_entity_id": entity_id}, {"payee_entity_id": entity_id}]
    elif scope_entity_ids:
        q["$or"] = [{"payer_entity_id": {"$in": scope_entity_ids}},
                    {"payee_entity_id": {"$in": scope_entity_ids}}]
    rows = await db[COLL_ICS].find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return [safe_doc(r) for r in rows]


async def get_settlement(sid: str) -> Optional[Dict[str, Any]]:
    return safe_doc(await db[COLL_ICS].find_one({"id": sid}, {"_id": 0}))


# ═══════════════════════════════════════════════════════════════════════════
# META & SUMMARY
# ═══════════════════════════════════════════════════════════════════════════
async def summary(scope_entity_ids: List[str], entity_id: str = "") -> Dict[str, Any]:
    """Ringkasan untuk layar (US5): saldo aktif + jumlah dokumen open + settlement bulan ini."""
    accs = await list_accounts(scope_entity_ids)
    total_receivable = sum(a.get("outstanding", 0) for a in accs
                           if a.get("role") == "receivable" and
                           (not entity_id or a.get("from_entity_id") == entity_id or entity_id == "all"))
    total_payable = sum(a.get("outstanding", 0) for a in accs
                        if a.get("role") == "payable" and
                        (not entity_id or a.get("from_entity_id") == entity_id or entity_id == "all"))
    open_docs = await db[COLL_ICT].count_documents({
        "entity_id": {"$in": scope_entity_ids} if scope_entity_ids else {"$exists": True},
        "status": {"$in": list(OPEN_STATUSES)},
    })
    return {
        "total_receivable": round(total_receivable, 2),
        "total_payable": round(total_payable, 2),
        "open_documents": open_docs,
        "pair_count": len(accs),
        "statuses": [{"value": s, "label": STATUS_LABEL[s]} for s in STATUSES],
    }


async def meta() -> Dict[str, Any]:
    return {
        "statuses": [{"value": s, "label": STATUS_LABEL[s]} for s in STATUSES],
        "pricing_modes": [
            {"value": "fixed_price", "label": "Harga tetap dari kontrak internal"},
            {"value": "at_cost", "label": "Sesuai HPP penjual"},
            {"value": "cost_plus_pct", "label": "HPP + persen margin"},
        ],
        "ppn_modes": [
            {"value": "ikut_pkp", "label": "Ikut status PKP penjual"},
            {"value": "tanpa_ppn", "label": "Tanpa PPN"},
            {"value": "dengan_ppn", "label": "Dengan PPN (paksa)"},
        ],
        "settlement_methods": [
            {"value": "netting", "label": "Netting (saling hapus, tanpa uang)"},
            {"value": "transfer", "label": "Transfer bank"},
            {"value": "cash", "label": "Kas"},
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# ELIMINASI KONSOLIDASI (US7 / INV-IC-03) — dijaga OTOMATIS
# ═══════════════════════════════════════════════════════════════════════════
async def _sync_group_elimination(pair_id: str) -> None:
    """Selaraskan entri eliminasi grup untuk satu pair.

    KENAPA OTOMATIS: margin antar-PT WAJIB hilang di laporan grup selama barang
    belum terjual keluar (INV-IC-03). Kalau ini hanya bisa dijalankan lewat
    tombol, laporan konsolidasi akan salah setiap kali orang lupa menekannya —
    dan "lupa" bukan kesalahan yang boleh membuat laba grup menggelembung.
    Tombol manual di layar Konsolidasi Grup tetap ada untuk data lama/backfill.

    Kegagalan di sini TIDAK boleh menggagalkan transaksi bisnisnya (jurnal per-PT
    sudah sah); dicatat ke log supaya tetap terlihat.
    """
    try:
        from services import consolidation_service as _cons
        await _cons.sync_g6_for_pair(pair_id)
    except Exception as exc:  # noqa: BLE001 — pelengkap laporan, bukan syarat transaksi
        print(f"[interco] sync eliminasi grup gagal untuk {pair_id}: {exc}")


async def _link_refs(pair_id: str) -> None:
    """Tautan dokumen DUA ARAH (G-4/US10): dokumen kembar saling menunjuk."""
    try:
        from services import doc_refs_service as _refs
        seller, buyer = await _pair_docs(pair_id)
        await _refs.safe_link(("interco_transaction", seller["id"]),
                              ("interco_transaction", buyer["id"]), "child",
                              note="Dokumen kembar antar-PT (PO internal ↔ SO/SJ/Invoice)")
    except Exception as exc:  # noqa: BLE001
        print(f"[interco] tautan dokumen kembar gagal {pair_id}: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
# PEMBALIKAN JURNAL SAAT BATAL (G-1: koreksi ber-alasan, bukan hapus senyap)
# ═══════════════════════════════════════════════════════════════════════════
async def _reverse_gl_for_pair(pair_id: str, actor: str, reason: str) -> int:
    """Balik jurnal pair yang SUDAH diposting (Dr↔Cr ditukar), idempotent.

    Pembatalan transaksi yang sudah dikonfirmasi tidak boleh menyisakan
    pendapatan & piutang antar-PT di buku. Kita TIDAK menghapus jurnal lama
    (audit trail) melainkan menerbitkan jurnal pembalik ber-alasan.
    """
    posted = 0
    for suffix in ("seller", "cogs", "buyer", "receipt"):
        src_id = f"{pair_id}:{suffix}"
        je = await db.journal_entries.find_one(
            {"source_type": "interco_transaction", "source_id": src_id,
             "status": "posted"}, {"_id": 0})
        if not je:
            continue
        if await gl_service._already_posted("interco_transaction", f"{src_id}:reversal"):
            continue
        rev_lines = [{
            "account_code": l["account_code"],
            "debit": float(l.get("credit") or 0),
            "credit": float(l.get("debit") or 0),
            "description": f"PEMBALIKAN: {l.get('description', '')}".strip(),
        } for l in je.get("lines", [])]
        await gl_service._insert_entry(
            lines=rev_lines,
            description=f"Pembalikan {je.get('description', '')} — alasan: {reason}",
            date=now_iso(), source_type="interco_transaction",
            source_id=f"{src_id}:reversal", entity_id=je.get("entity_id", ""),
            created_by=actor or "system", source_label=je.get("source_label", ""),
        )
        posted += 1
    return posted


# ═══════════════════════════════════════════════════════════════════════════
# JURNAL PER-PAIR (dipakai Detail Panel — "tunjukkan buktinya di dua buku")
# ═══════════════════════════════════════════════════════════════════════════
async def pair_journal(pair_id: str) -> Dict[str, Any]:
    """Kumpulkan SEMUA bukti akuntansi satu pair untuk ditampilkan di layar.

    Sebelumnya frontend menebak-nebak lewat `/api/gl/entries` (endpoint yang tidak
    pernah ada) sehingga blok jurnal DIAM-DIAM kosong. Satu endpoint khusus
    membuat layar menampilkan bukti yang sama dengan yang dipakai invarian.
    """
    async def _je(source_id: str) -> Optional[Dict[str, Any]]:
        return await db.journal_entries.find_one(
            {"source_type": "interco_transaction", "source_id": source_id},
            {"_id": 0})

    seller_je = await _je(f"{pair_id}:seller")
    buyer_je = await _je(f"{pair_id}:buyer")
    cogs_je = await _je(f"{pair_id}:cogs")
    receipt_je = await _je(f"{pair_id}:receipt")
    reversals = await db.journal_entries.find(
        {"source_type": "interco_transaction",
         "source_id": {"$regex": f"^{pair_id}:.*:reversal$"}}, {"_id": 0}).to_list(20)

    # Settlement yang menyentuh pair ini → jurnal kedua buku
    settlements = await db[COLL_ICS].find(
        {"applied.pair_id": pair_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    settlement_jes: List[Dict[str, Any]] = []
    for s in settlements:
        for side in ("payer", "payee"):
            je = await db.journal_entries.find_one(
                {"source_type": "interco_settlement", "source_id": f"{s['id']}:{side}"},
                {"_id": 0})
            if je:
                settlement_jes.append({**je, "settlement_number": s.get("number", ""),
                                       "side": side})

    eliminations = await db.intercompany_eliminations.find(
        {"source_g6_pair_id": pair_id}, {"_id": 0}).to_list(20)

    transfers = await db.warehouse_transfers.find(
        {"$or": [{"interco_pair_id": pair_id},
                 {"interco_return_pair_id": {"$in": [
                     r["return_pair_id"] for r in await db.interco_returns.find(
                         {"origin_pair_id": pair_id, "role": "returner"},
                         {"_id": 0, "return_pair_id": 1}).to_list(50)]}}]},
        {"_id": 0, "id": 1, "code": 1, "status": 1, "items": 1, "created_at": 1,
         "approved_at": 1, "approved_by": 1, "je_intercompany": 1,
         "interco_return_number": 1,
         "source_entity_id": 1, "dest_entity_id": 1}).to_list(20)

    # ── FASE G-6b: retur antar-PT (dokumen + jurnalnya) ─────────────────────
    returns = await db.interco_returns.find(
        {"origin_pair_id": pair_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return_jes: List[Dict[str, Any]] = []
    seen_rp = {r["return_pair_id"] for r in returns}
    for rp in sorted(seen_rp):
        for suffix in ("seller", "buyer", "goods_out", "goods_in"):
            je = await db.journal_entries.find_one(
                {"source_type": "interco_return", "source_id": f"{rp}:{suffix}"},
                {"_id": 0})
            if je:
                return_jes.append({**je, "return_pair_id": rp, "block": suffix})

    # ── FASE G-6b: faktur pajak internal (keluaran + masukan) ───────────────
    tax_out = await db.tax_invoices.find(
        {"interco_pair_id": pair_id}, {"_id": 0}).sort("created_at", -1).to_list(20)
    tax_in = await db.tax_invoices_in.find(
        {"interco_pair_id": pair_id}, {"_id": 0}).sort("created_at", -1).to_list(20)

    return {
        "pair_id": pair_id,
        "seller": safe_doc(seller_je) if seller_je else None,
        "buyer": safe_doc(buyer_je) if buyer_je else None,
        "cogs": safe_doc(cogs_je) if cogs_je else None,
        "receipt": safe_doc(receipt_je) if receipt_je else None,
        "reversals": [safe_doc(r) for r in reversals],
        "settlement_entries": [safe_doc(j) for j in settlement_jes],
        "settlements": [safe_doc(s) for s in settlements],
        "eliminations": [safe_doc(e) for e in eliminations],
        "warehouse_tasks": [safe_doc(t) for t in transfers],
        "returns": [safe_doc(r) for r in returns],
        "return_entries": [safe_doc(j) for j in return_jes],
        "tax_invoices_out": [safe_doc(t) for t in tax_out],
        "tax_invoices_in": [safe_doc(t) for t in tax_in],
    }


# ═══════════════════════════════════════════════════════════════════════════
# JEMBATAN GUDANG (US8) — barang fisik tetap lewat tugas gudang, TANPA dobel jurnal
# ═══════════════════════════════════════════════════════════════════════════
async def create_warehouse_task(interco_id: str, actor: str) -> Dict[str, Any]:
    """Terbitkan tugas gudang (`warehouse_transfers` inter_entity) untuk satu pair.

    MASALAH NYATA yang ditutup: sebelum ini, memindahkan barangnya berarti membuat
    transfer antar-PT terpisah yang **memposting jurnal at-cost M-3 lagi** — jadi
    IC-AR/IC-AP & persediaan tercatat DUA KALI untuk satu barang. Sekarang tugas
    gudang menyimpan `interco_pair_id`; saat disetujui gudang:
      * kepemilikan roll berpindah (jalur gudang yang sudah ada, satu mutasi saja),
      * jurnal at-cost M-3 **dilewati** (G-6 sudah memposting harga jual),
      * nilai roll di pembeli **dinilai ulang** ke harga beli internal (harga
        perolehannya yang sah) sehingga GL 1-1300 == subledger,
      * status pair maju ke `shipped` → `received`.
    """
    from fastapi import HTTPException
    from services.roll_service import reserve_rolls_for_transfer, release_transfer_rolls

    doc = await db[COLL_ICT].find_one({"id": interco_id}, {"_id": 0})
    if not doc:
        raise IntercoError("Transaksi tidak ditemukan.")
    if doc["status"] in ("draft", "cancelled"):
        raise IntercoError(
            "Konfirmasi transaksinya dulu — tugas gudang hanya untuk transaksi "
            "yang sudah dikonfirmasi (barang tidak boleh berjalan tanpa dokumen sah).")
    pair_id = doc["pair_id"]
    seller, buyer = await _pair_docs(pair_id)

    existing = await db.warehouse_transfers.find_one(
        {"interco_pair_id": pair_id, "status": {"$nin": ["rejected", "cancelled"]}},
        {"_id": 0, "code": 1, "status": 1})
    if existing:
        raise IntercoError(
            f"Tugas gudang {existing.get('code')} sudah ada untuk transaksi ini "
            f"(status {existing.get('status')}).")

    transfer_id = new_id("trn")
    # FASE E-1 (E1.7) — nomor per badan usaha PENJUAL (pemilik tugas gudangnya).
    code = await next_doc_number("warehouse_transfers", "code", "TRF-",
                                 entity_id=seller.get("seller_entity_id") or None)
    items_out: List[Dict[str, Any]] = []
    wh_ids: List[str] = []
    try:
        for it in seller.get("items", []):
            reserved = await reserve_rolls_for_transfer(
                it["product_id"], seller["seller_entity_id"],
                float(it["quantity"]), transfer_id)
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
        raise IntercoError(str(exc.detail)) from exc
    except Exception:
        await release_transfer_rolls(transfer_id)
        raise

    primary_wh = wh_ids[0] if wh_ids else ""
    transfer = {
        "id": transfer_id,
        "code": code,
        "transfer_kind": "inter_entity",
        "entity_id": seller["seller_entity_id"],   # FASE E-0 (L14)
        "source_entity_id": seller["seller_entity_id"],
        "dest_entity_id": seller["buyer_entity_id"],
        "source_warehouse_id": primary_wh,
        "dest_warehouse_id": primary_wh,
        "status": "waiting_approval",
        "items": items_out,
        "transfer_price": float(seller.get("subtotal") or 0),
        "linked_order_id": None,
        # ── Jembatan G-6 (kunci anti dobel-posting) ──────────────────────────
        "interco_pair_id": pair_id,
        "interco_id": seller["id"],
        "interco_number": seller.get("number", ""),
        "notes": (f"Perpindahan fisik untuk transaksi antar-PT "
                  f"{seller.get('number', '')} ↔ {buyer.get('number', '')}"),
        "requested_by": actor or "system",
        "approved_by": None, "approved_at": None,
        "rejected_by": None, "rejected_at": None, "rejected_reason": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.warehouse_transfers.insert_one(dict(transfer))
    await db[COLL_ICT].update_many(
        {"pair_id": pair_id},
        {"$set": {"warehouse_transfer_id": transfer_id,
                  "warehouse_transfer_code": code,
                  "warehouse_transfer_status": "waiting_approval",
                  "updated_at": now_iso()}})
    try:
        from services import doc_refs_service as _refs
        await _refs.safe_link(("interco_transaction", seller["id"]),
                              ("warehouse_transfer", transfer_id), "child",
                              note="Perpindahan fisik barang antar-PT")
    except Exception as exc:  # noqa: BLE001
        print(f"[interco] tautan tugas gudang gagal: {exc}")
    return safe_doc(transfer)


async def on_warehouse_task_executed(transfer: Dict[str, Any], actor: str) -> Dict[str, Any]:
    """Dipanggil `routers/transfers.py` sesudah kepemilikan roll berpindah.

    Tiga hal yang WAJIB terjadi supaya buku tetap benar:
      1. Roll di pembeli dinilai ulang ke **harga beli internal** (kalau tidak,
         GL 1-1300 pembeli (harga jual) selamanya beda dari subledger (HPP penjual)).
      2. Status pair maju `shipped` → `received` (jejak waktu nyata, bukan tombol manual).
      3. Jurnal at-cost M-3 TIDAK diposting — itu tugas pemanggil (lihat komentar
         di `approve_transfer`); di sini kita hanya mencatat alasannya.
    """
    pair_id = transfer.get("interco_pair_id") or ""
    if not pair_id:
        return {"revalued_rolls": 0, "status": ""}
    seller, buyer = await _pair_docs(pair_id)
    price_map = {it["product_id"]: float(it.get("unit_price") or 0)
                 for it in seller.get("items", [])}
    revalued = 0
    rolls = await db.inventory_rolls.find(
        {"acquired.ref_id": transfer["id"],
         "owner_entity_id": transfer.get("dest_entity_id")},
        {"_id": 0, "id": 1, "product_id": 1, "unit_cost": 1, "base_unit_cost": 1,
         "length_remaining": 1}).to_list(10000)
    # Biaya NYATA yang keluar dari buku penjual = Σ(panjang × harga perolehan roll)
    # — dihitung SEBELUM roll dinilai ulang ke harga beli internal.
    cost_out = round(sum(float(r.get("length_remaining") or 0) *
                         float(r.get("unit_cost") or r.get("base_unit_cost") or 0)
                         for r in rolls), 2)
    for r in rolls:
        new_cost = price_map.get(r["product_id"])
        if new_cost is None or new_cost <= 0:
            continue
        await db.inventory_rolls.update_one({"id": r["id"]}, {"$set": {
            "unit_cost": round(new_cost, 2),
            "base_unit_cost": round(new_cost, 2),
            "cost_basis": {
                "source": "interco_purchase",
                "interco_pair_id": pair_id,
                "interco_number": seller.get("number", ""),
                "previous_unit_cost": float(r.get("unit_cost") or 0),
                "at": now_iso(),
            },
            "updated_at": now_iso(),
        }})
        revalued += 1

    ts = now_iso()
    stamp: Dict[str, Any] = {"warehouse_transfer_status": "completed",
                             "updated_at": ts, "updated_by": actor}
    if seller.get("status") == "confirmed":
        stamp.update({"shipped_at": ts, "shipped_by": actor})
    if seller.get("status") in ("confirmed", "shipped"):
        stamp.update({"received_at": ts, "received_by": actor, "status": "received"})
    await db[COLL_ICT].update_many({"pair_id": pair_id}, {"$set": stamp})

    # Jurnal yang MENGIKUTI BARANG (HPP penjual + transit→persediaan pembeli),
    # lalu eliminasi grup dihitung ulang karena HPP-nya baru sekarang diketahui.
    gl_delivery = await post_gl_on_delivery(pair_id, actor, cost_override=cost_out)
    await _sync_group_elimination(pair_id)
    # FASE E-9 (E9.1) — barangnya kini BENAR-BENAR ada di gudang pembeli, jadi pesanan
    # pelanggan yang menunggu stok wajib terpenuhi OTOMATIS.
    fulfilled = await _auto_fulfill_after_interco_receipt(seller, transfer, actor)
    return {"revalued_rolls": revalued, "status": stamp.get("status", seller.get("status")),
            "pair_id": pair_id, "gl_delivery": gl_delivery, "auto_fulfill": fulfilled}


async def _auto_fulfill_after_interco_receipt(
        seller: Dict[str, Any], transfer: Dict[str, Any], actor: str) -> Dict[str, Any]:
    """E9.1 — penerimaan barang antar-PT memicu pemenuhan backorder pembeli.

    CACAT YANG DITUTUP: `auto_fulfill_backorders()` dulu hanya dipanggil dari
    penerimaan barang PO supplier (`routers/inbound_receiving.py`) dan pelepasan QC.
    Pembelian internal — yang justru DILAKUKAN UNTUK sebuah pesanan pelanggan —
    tidak memicu apa pun, jadi pesanan itu tetap "menunggu stok" walaupun barangnya
    sudah masuk gudang, dan Admin Sales harus mengalokasikan manual (padahal ia
    tidak punya isyarat bahwa barangnya sudah datang).

    Pemberitahuan dikirim ke Admin Sales — mengabari, bukan meminta persetujuan.
    Kegagalan di sini TIDAK boleh membatalkan perpindahan barang: dokumen & jurnal
    sudah sah, pemenuhan bisa diulang lewat alokasi manual.
    """
    buyer_entity = seller.get("buyer_entity_id") or ""
    out: Dict[str, Any] = {"orders_touched": 0, "orders_completed": 0,
                           "qty_fulfilled": 0.0, "products": []}
    if not buyer_entity:
        return out
    try:
        from services.backorder_service import auto_fulfill_backorders
    except Exception as exc:  # noqa: BLE001
        print(f"[interco] mesin pemenuhan backorder tak tersedia: {exc}")
        return out
    for it in seller.get("items", []):
        pid = it.get("product_id")
        if not pid:
            continue
        try:
            res = await auto_fulfill_backorders(pid, buyer_entity)
        except Exception as exc:  # noqa: BLE001 — barang sudah pindah; jangan dibatalkan
            print(f"[interco] pemenuhan otomatis {pid} gagal: {exc}")
            continue
        out["orders_touched"] += int(res.get("orders_touched") or 0)
        out["orders_completed"] += int(res.get("orders_completed") or 0)
        out["qty_fulfilled"] = round(out["qty_fulfilled"] +
                                     float(res.get("qty_fulfilled") or 0), 2)
        if res.get("orders_touched"):
            out["products"].append({"product_id": pid,
                                    "qty_fulfilled": float(res.get("qty_fulfilled") or 0)})
    if out["orders_touched"]:
        try:
            from services import notification_service as notif
            src = (seller.get("source_order_number") or "").strip()
            ekor = f" Pesanan pemicunya: {src}." if src else ""
            await notif.create_notification(
                notif_type="interco_receipt_auto_fulfilled",
                title=(f"Barang dari {seller.get('seller_entity_name', 'PT lain')} masuk — "
                       f"{out['orders_touched']} pesanan terpenuhi otomatis"),
                body=(f"Barang {seller.get('number', '')} dari "
                      f"{seller.get('seller_entity_name', '')} sudah diterima gudang "
                      f"({transfer.get('code', '')}). {out['orders_touched']} pesanan yang "
                      f"tadinya menunggu stok kini ter-reservasi "
                      f"({out['orders_completed']} terpenuhi penuh, total "
                      f"{out['qty_fulfilled']:,.2f} unit).{ekor} Tidak ada alokasi manual "
                      f"yang perlu Anda lakukan — silakan periksa lalu lanjutkan prosesnya."),
                severity="info", link="pending-so", entity_id=buyer_entity or None,
                recipient_role="sales_admin",
                ref=f"icfulfill:{seller.get('pair_id', '')}")
        except Exception as exc:  # noqa: BLE001
            print(f"[interco] notifikasi pemenuhan otomatis gagal: {exc}")
    return out


async def supply_for_order(order_id: str, buyer_entity_id: str = "") -> List[Dict[str, Any]]:
    """E9.2 — janji pasokan ANTAR-PT untuk satu pesanan pelanggan.

    Dipakai layar pesanan supaya Admin Sales tahu "kekurangannya diambil dari PT mana,
    lewat dokumen apa". Hanya transaksi yang MEMANG menyebut pesanan ini
    (`source_order_id`) yang dilaporkan — sistem tidak menebak-nebak: janji yang tidak
    tertaut cukup tampil di Papan Pending SO sebagai pasokan tingkat produk.
    """
    if not order_id:
        return []
    q: Dict[str, Any] = {"role": "buyer", "source_order_id": order_id}
    if buyer_entity_id:
        q["buyer_entity_id"] = buyer_entity_id
    docs = await db[COLL_ICT].find(q, {
        "_id": 0, "id": 1, "number": 1, "status": 1, "items": 1, "doc_date": 1,
        "due_date": 1, "seller_entity_id": 1, "seller_entity_name": 1,
        "warehouse_transfer_status": 1, "warehouse_transfer_code": 1,
        "source_request_number": 1, "pair_id": 1,
    }).sort("created_at", 1).to_list(200)
    out: List[Dict[str, Any]] = []
    for d in docs:
        out.append({
            "interco_id": d.get("id", ""),
            "pair_id": d.get("pair_id", ""),
            "number": d.get("number", ""),
            "status": d.get("status", ""),
            "status_label": STATUS_LABEL.get(d.get("status", ""), d.get("status", "")),
            "from_entity_id": d.get("seller_entity_id", ""),
            "from_entity_name": d.get("seller_entity_name", ""),
            "eta": d.get("due_date") or d.get("doc_date") or "",
            "warehouse_transfer_status": d.get("warehouse_transfer_status", ""),
            "warehouse_transfer_code": d.get("warehouse_transfer_code", ""),
            "source_request_number": d.get("source_request_number", ""),
            "goods_arrived": d.get("status") in ("received", "invoiced", "settled"),
            "items": [{
                "product_id": it.get("product_id", ""),
                "sku": it.get("sku", ""),
                "product_name": it.get("product_name", ""),
                "quantity": round(float(it.get("quantity") or 0), 2),
                "unit": it.get("unit", ""),
            } for it in d.get("items", [])],
        })
    return out
