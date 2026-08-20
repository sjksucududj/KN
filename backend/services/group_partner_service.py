"""FASE E-7 (E7.2 + E7.7) — **PAGAR "LAWAN TRANSAKSI TERNYATA PT SENDIRI"**.

## Masalah nyata yang ditutup (temuan IC-G10, `AUDIT_ANTAR_ENTITAS.md` §B)
`customers` dan `suppliers` **tidak punya penanda badan usaha grup** dan tidak ada
validasi apa pun (nol rujukan ke `business_entities` di `routers/customers.py`,
`routers/suppliers.py`, `schemas.py`). Akibatnya satu badan usaha dalam grup bisa
didaftarkan sebagai pemasok/pelanggan biasa, lalu transaksi antar-PT lewat **PO/SO
biasa**:

  * tidak ada dokumen kembar di kedua badan usaha,
  * harga tidak diambil dari kontrak internal,
  * tidak ada faktur pajak internal berpasangan,
  * **tidak ada eliminasi margin** di konsolidasi → **laba grup terlihat lebih besar
    dari kenyataan** (angka yang dipakai pemilik untuk mengambil keputusan).

## Keputusan pemilik yang diterapkan (E7.7)
> "**Entitas lain diperlakukan seperti PEMASOK, bukan pelanggan.** Bila KSC membeli
> dari Kanda, maka Kanda muncul sebagai pemasok bertipe *Entitas grup* dengan logika
> yang sama (wajib kontrak internal dulu, dst). **JANGAN** membuat pelanggan untuk PT
> sendiri. Pembedanya tetap **menu Antar Entitas** (+ lencana di layar pembelian)."

Jadi modul ini melakukan DUA hal yang saling melengkapi:

1. **IDENTITAS** — `sync_group_entity_suppliers()` menyiapkan (idempotent) satu baris
   `suppliers` bertipe **Entitas grup** untuk setiap pasangan (badan usaha tuan rumah ×
   badan usaha grup lain). Baris ini adalah **jangkar navigasi**: staf pembelian bisa
   menemukan "Kanda" di daftar pemasok, melihat lencana *Entitas grup*, kontrak
   internalnya, dan saldo antar-PT-nya. Baris ini **bukan** target PO.
2. **PAGAR** — `assert_supplier_not_group_entity()` / `assert_customer_not_group_entity()`
   menolak dokumen komersial biasa (PO/PR/RFQ/Vendor Bill/SO) yang lawannya badan usaha
   grup, dengan **kalimat menuntun** ke layar Antar Entitas (pola yang sudah dipakai
   `services/tax_invoice_service.py:195`) — bukan pesan galat buntu.

Pengenalan badan usaha grup memakai **dua lapis**, supaya data lama pun tertangkap:
  * penanda eksplisit `partner_kind == "entity"` / `group_entity_id` (data baru), dan
  * pencocokan identitas **NPWP** (angka saja) lalu **nama** (legal/singkat) —
    inilah yang menangkap baris lama yang dibuat sebelum fase ini.

Penamaan `partner_kind="entity"` **sengaja sama** dengan yang sudah dipakai
`supplier_contracts` (lihat `services/contract_service._partner_snapshot`) supaya tidak
ada dua kosakata untuk satu konsep.
"""
import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from db import db
from core_utils import now_iso

# `partner_kind` pada `suppliers` — sejajar dengan `supplier_contracts`.
KIND_ENTITY = "entity"
KIND_SUPPLIER = "supplier"

# Jalan yang BENAR untuk transaksi antar badan usaha (dipakai di kalimat menuntun).
INTERCO_PATH = ("Pembelian → Hutang Supplier → **Antar Entitas**")


def _digits(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _norm_name(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().casefold()


def entity_label(entity: Dict[str, Any]) -> str:
    """Nama yang dipakai di kalimat menuntun: nama badan hukum bila ada."""
    e = entity or {}
    return (e.get("legal_name") or e.get("short_name") or e.get("doc_prefix")
            or e.get("id") or "badan usaha grup")


def entity_short(entity: Dict[str, Any]) -> str:
    e = entity or {}
    return (e.get("short_name") or e.get("doc_prefix") or entity_label(e))


# ─── IDENTITAS: pemasok bertipe "Entitas grup" ───────────────────────────────
def group_supplier_id(host_entity_id: str, group_entity_id: str) -> str:
    """Id deterministik supaya sinkronisasi benar-benar idempotent (bukan duplikat baru)."""
    h = str(host_entity_id or "").replace("ent_", "")
    g = str(group_entity_id or "").replace("ent_", "")
    return f"sup_grp_{h}_{g}"


async def _all_entities() -> List[Dict[str, Any]]:
    return await db.business_entities.find({}, {"_id": 0}).to_list(500)


async def _next_supplier_code(taken: set) -> str:
    """Nomor SUP-NNNNN berikutnya. `taken` mencegah tabrakan dalam satu batch."""
    n = 0
    async for row in db.suppliers.find({"code": {"$regex": r"^SUP-\d+$"}},
                                       {"_id": 0, "code": 1}).sort("code", -1).limit(1):
        try:
            n = int(row["code"].split("-")[1])
        except (ValueError, IndexError):
            n = await db.suppliers.count_documents({})
    while True:
        n += 1
        code = f"SUP-{n:05d}"
        if code not in taken:
            taken.add(code)
            return code


async def sync_group_entity_suppliers(*, actor_name: str = "system") -> Dict[str, Any]:
    """Pastikan setiap badan usaha melihat badan usaha grup LAIN sebagai pemasok
    bertipe *Entitas grup*. **Idempotent** — aman dipanggil di bootstrap, sesudah seed,
    dan setiap kali badan usaha dibuat/diubah/diarsipkan.

    Aturan:
      * hanya badan usaha **aktif** yang menjadi tuan rumah (badan usaha mati tidak
        perlu daftar pemasok baru);
      * badan usaha grup yang **tidak aktif** tetap punya barisnya tetapi
        `status="inactive"` — riwayat hutang-piutangnya tidak boleh hilang dari layar;
      * baris yang badan usahanya sudah **hilang** dari `business_entities` ditandai
        `status="inactive"` + `group_entity_missing=True` (jujur, bukan dihapus).
    """
    entities = await _all_entities()
    by_id = {e["id"]: e for e in entities}
    active = [e for e in entities if e.get("status", "active") == "active"]
    taken: set = {r["code"] async for r in db.suppliers.find(
        {"code": {"$exists": True}}, {"_id": 0, "code": 1}) if r.get("code")}
    created = updated = archived = 0

    for host in active:
        for grp in entities:
            if grp["id"] == host["id"]:
                continue
            sid = group_supplier_id(host["id"], grp["id"])
            existing = await db.suppliers.find_one({"id": sid}, {"_id": 0})
            desired = {
                "name": entity_label(grp),
                "npwp": (grp.get("npwp") or "").strip(),
                "pic_name": (grp.get("pic_name") or "").strip(),
                "phone": (grp.get("phone") or "").strip(),
                "email": (grp.get("email") or "").strip(),
                "address": (grp.get("address") or "").strip(),
                "city": (grp.get("city") or "").strip(),
                "entity_id": host["id"],
                # ── penanda E7.2/E7.7 ──
                "partner_kind": KIND_ENTITY,
                "group_entity_id": grp["id"],
                "group_entity_short_name": entity_short(grp),
                "group_entity_prefix": (grp.get("doc_prefix") or "").strip(),
                "group_entity_missing": False,
                "status": "active" if grp.get("status", "active") == "active" else "inactive",
                "goods_type": "Barang dari badan usaha grup (antar entitas)",
                "origin_type": "local",
                "notes": (
                    f"Badan usaha dalam grup. Pembelian dari {entity_short(grp)} WAJIB lewat "
                    f"menu Antar Entitas supaya dokumennya kembar di kedua badan usaha dan "
                    f"margin grup ikut dieliminasi di laporan konsolidasi."),
                "updated_at": now_iso(),
            }
            if existing:
                changed = {k: v for k, v in desired.items()
                           if k != "updated_at" and existing.get(k) != v}
                if changed:
                    await db.suppliers.update_one({"id": sid}, {"$set": desired})
                    updated += 1
                continue
            code = await _next_supplier_code(taken)
            await db.suppliers.insert_one({
                "id": sid, "code": code,
                "payment_term_code": "", "lead_time_days": 0,
                "country": "Indonesia", "return_policy": None,
                "created_by": actor_name, "created_at": now_iso(),
                **desired,
            })
            created += 1

    # Baris yatim: badan usaha grupnya sudah tidak ada lagi di registry.
    async for row in db.suppliers.find({"partner_kind": KIND_ENTITY}, {"_id": 0}):
        gid = row.get("group_entity_id")
        if gid and gid not in by_id and not row.get("group_entity_missing"):
            await db.suppliers.update_one(
                {"id": row["id"]},
                {"$set": {"status": "inactive", "group_entity_missing": True,
                          "updated_at": now_iso()}})
            archived += 1
    return {"created": created, "updated": updated, "archived": archived}


# ─── PENGENALAN: apakah lawan transaksi ini badan usaha grup? ────────────────
def marked_group_entity_id(partner: Optional[Dict[str, Any]]) -> str:
    """Penanda EKSPLISIT (data baru). Kosong = belum ditandai, lanjut ke pencocokan."""
    p = partner or {}
    if p.get("partner_kind") == KIND_ENTITY or p.get("is_group_entity") is True:
        return str(p.get("group_entity_id") or "")
    return str(p.get("group_entity_id") or "")


async def match_group_entity(*, name: str = "", npwp: str = "",
                             exclude_entity_id: str = "") -> Optional[Dict[str, Any]]:
    """Cocokkan identitas ke `business_entities`. NPWP lebih dulu (paling kuat), lalu nama.

    `exclude_entity_id` = badan usaha PEMILIK dokumen: mencatat diri sendiri sebagai
    lawan transaksi memang salah, tetapi pesan yang tepat berbeda, jadi pemanggil yang
    memutuskan. Di sini ia tetap ikut dicocokkan supaya tidak ada yang lolos.
    """
    npwp_d = _digits(npwp)
    nm = _norm_name(name)
    if not npwp_d and not nm:
        return None
    for e in await _all_entities():
        if npwp_d and _digits(e.get("npwp")) and _digits(e.get("npwp")) == npwp_d:
            return e
    if not nm:
        return None
    for e in await _all_entities():
        candidates = {_norm_name(e.get("legal_name")), _norm_name(e.get("short_name")),
                      _norm_name(e.get("business_label"))}
        candidates.discard("")
        if nm in candidates:
            return e
    return None


async def resolve_group_entity(partner: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Badan usaha grup di balik satu baris pemasok/pelanggan — atau None."""
    if not partner:
        return None
    gid = marked_group_entity_id(partner)
    if gid:
        ent = await db.business_entities.find_one({"id": gid}, {"_id": 0})
        if ent:
            return ent
    return await match_group_entity(name=partner.get("name", ""),
                                    npwp=partner.get("npwp", ""))


# ─── PAGAR: kalimat menuntun, bukan galat buntu ─────────────────────────────
def _buy_guidance(entity: Dict[str, Any], doc_label: str) -> str:
    short = entity_short(entity)
    return (
        f"“{entity_label(entity)}” adalah badan usaha di dalam grup Anda, bukan pemasok "
        f"luar — jadi {doc_label} biasa tidak bisa dipakai. Catat pembeliannya lewat "
        f"{INTERCO_PATH} → Transaksi Baru (pilih {short} sebagai penjual). "
        f"Di sana satu transaksi melahirkan dokumen KEMBAR di kedua badan usaha, harganya "
        f"diambil dari kontrak internal, PPN & faktur pajaknya berpasangan, dan margin "
        f"antar-PT ikut dieliminasi di laporan konsolidasi. Bila dicatat sebagai "
        f"{doc_label} biasa, laba grup akan terlihat LEBIH BESAR dari kenyataan karena "
        f"margin ke {short} tidak pernah dihapus."
    )


def _sell_guidance(entity: Dict[str, Any], doc_label: str) -> str:
    short = entity_short(entity)
    return (
        f"“{entity_label(entity)}” adalah badan usaha di dalam grup Anda, jadi tidak "
        f"dicatat sebagai pelanggan biasa dan {doc_label} ini tidak bisa dilanjutkan. "
        f"Penjualan ke badan usaha grup dibuat dari {INTERCO_PATH} → Transaksi Baru "
        f"(badan usaha Anda sebagai penjual, {short} sebagai pembeli). Di sisi {short}, "
        f"badan usaha Anda akan muncul sebagai PEMASOK bertipe “Entitas grup” — itu "
        f"memang bentuk yang benar, dan margin antar-PT ikut dieliminasi di konsolidasi."
    )


async def assert_supplier_not_group_entity(supplier: Optional[Dict[str, Any]], *,
                                           doc_label: str = "Pesanan Pembelian") -> None:
    """Tolak dokumen PEMBELIAN biasa yang pemasoknya badan usaha grup (E7.2)."""
    ent = await resolve_group_entity(supplier)
    if ent:
        raise HTTPException(status_code=409, detail=_buy_guidance(ent, doc_label))


async def assert_customer_not_group_entity(customer: Optional[Dict[str, Any]], *,
                                           doc_label: str = "Pesanan Penjualan") -> None:
    """Tolak dokumen PENJUALAN biasa yang pelanggannya badan usaha grup (E7.2)."""
    ent = await resolve_group_entity(customer)
    if ent:
        raise HTTPException(status_code=409, detail=_sell_guidance(ent, doc_label))


async def assert_new_customer_allowed(name: str, npwp: str = "") -> None:
    """Tolak PEMBUATAN pelanggan yang ternyata badan usaha grup (keputusan E7.7:
    "JANGAN membuat pelanggan untuk PT sendiri")."""
    ent = await match_group_entity(name=name, npwp=npwp)
    if not ent:
        return
    raise HTTPException(
        status_code=409,
        detail=(f"“{entity_label(ent)}” sudah terdaftar sebagai badan usaha di dalam grup, "
                f"jadi tidak boleh dibuat lagi sebagai pelanggan. Transaksi dengan badan "
                f"usaha grup memakai menu Antar Entitas — dan di sisi pembeli, badan usaha "
                f"grup sudah otomatis tersedia sebagai PEMASOK bertipe “Entitas grup”. "
                f"Kalau dibuat sebagai pelanggan, penjualannya akan lolos dari eliminasi "
                f"margin dan laba grup jadi kembung."))


async def assert_new_supplier_allowed(name: str, npwp: str = "",
                                      host_entity_id: str = "") -> None:
    """Tolak PEMBUATAN pemasok manual yang ternyata badan usaha grup — barisnya sudah
    disiapkan otomatis, dan pemasok kembar akan memecah hutang antar-PT jadi dua."""
    ent = await match_group_entity(name=name, npwp=npwp)
    if not ent:
        return
    auto = None
    if host_entity_id:
        auto = await db.suppliers.find_one(
            {"id": group_supplier_id(host_entity_id, ent["id"])}, {"_id": 0, "code": 1})
    kode = f" (kode {auto['code']})" if auto and auto.get("code") else ""
    raise HTTPException(
        status_code=409,
        detail=(f"“{entity_label(ent)}” adalah badan usaha di dalam grup, dan pemasok "
                f"bertipe “Entitas grup” untuk badan usaha ini SUDAH disiapkan otomatis"
                f"{kode}. Pakai baris itu — jangan membuat pemasok kedua, karena hutang "
                f"antar-PT akan terpecah dua dan saldo pasangan PT tidak lagi cocok."))
