"""movement_label_service — nomor dokumen yang LAYAK DIBACA pada mutasi stok.

MASALAH NYATA (ditemukan saat menutup FASE F, layar *Operasi Gudang → Stok →
Mutasi*): `inventory_movements.source_document` menyimpan **campuran** dua hal:

    inbound_receiving        → "PO-00001"          (sudah nomor manusia)
    outbound_dispatch        → "SO-0001"           (sudah nomor manusia)
    sample_issue             → "KSC/SMP-00001"     (sudah nomor manusia)
    reservation / release_…  → "so_d29e63366078"   ← id TEKNIS
    production_consume/out…  → "wo_b1df696d5b1f"   ← id TEKNIS
    subcon_receipt           → "mko_b1ab0520c6c7"  ← id TEKNIS
    subcon_issue / consume   → "mko_b1ab0520c6c7:1"← id TEKNIS + nomor langkah

Akibatnya petugas gudang membaca "so_d29e63366078" di kolom **Dokumen** — sampah
yang tidak bisa ditindak, dan bertentangan dengan aturan bahasa antarmuka
(`scripts/audit_i18n_id.py`) maupun prinsip yang sudah dipakai di
`services/doc_refs_service.number_of()` ("nomor yang layak dicetak").

Modul ini MENAMBAH field turunan `source_document_label` (tidak mengubah data
tersimpan — append-only ledger tetap utuh) dengan aturan:

* id teknis dikenali dari prefiksnya lalu diterjemahkan ke nomor dokumen nyata,
  mis. `so_d29e…` → **SO-0007**, `mko_b1ab…:1` → **MKO-00001 · langkah 1**;
* dokumen yang sudah TERHAPUS dilabeli jujur **"(dokumen sudah dihapus)"** —
  bukan disembunyikan, karena mutasi yatim adalah temuan, bukan kosmetik;
* nilai yang sudah berupa nomor manusia dibiarkan apa adanya.

Resolusi dilakukan **berkelompok** (satu query per koleksi untuk seluruh halaman)
supaya tidak ada N+1 query.

FASE E-5 (E5.3) — **LABEL ENTITAS LAWAN.** Modul ini juga memberi
`attach_counterparty_labels()`: mutasi pindah-kepemilikan antar badan usaha WAJIB
tetap terlihat (jejak tidak boleh disembunyikan), tetapi badan usaha lawan hanya
boleh muncul sebagai **NAMA SINGKAT** — bukan id teknis `ent_kanda`, bukan nama
badan hukum lengkap, dan tentu bukan rincian stok/gudangnya (Keputusan #1
pemilik). Lihat `plan.md` §FASE E-5.
"""
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from db import db

# prefix id teknis → (koleksi, field nomor, label jenis dokumen)
_PREFIX_MAP: Dict[str, Tuple[str, Tuple[str, ...], str]] = {
    "so_": ("sales_orders", ("number",), "Pesanan Penjualan"),
    "po_": ("purchase_orders", ("po_number", "number"), "Pesanan Pembelian"),
    "pr_": ("purchase_requisitions", ("number",), "Permintaan Pembelian"),
    "mko_": ("makloon_orders", ("mko_number", "number"), "Order Makloon"),
    "wo_": ("mfg_work_orders", ("number", "wo_number"), "Perintah Kerja"),
    "smp_": ("md_samples", ("number",), "Permintaan Sample"),
    "spec_": ("md_specs", ("number",), "Spesifikasi Produk"),
    "trn_": ("warehouse_transfers", ("code", "number"), "Transfer Gudang"),
    "cc_": ("cycle_count_sessions", ("number",), "Stock Opname"),
    "pret_": ("purchase_returns", ("number",), "Retur Beli"),
    "sret_": ("sales_returns", ("number",), "Retur Jual"),
}

DELETED_LABEL = "(dokumen sudah dihapus)"


def _split_step(raw: str) -> Tuple[str, str]:
    """`mko_abc:2` → ("mko_abc", "2"). Tanpa langkah → ("mko_abc", "")."""
    if ":" in raw:
        head, _, tail = raw.partition(":")
        return head, tail.strip()
    return raw, ""


def _prefix_of(doc_id: str) -> str:
    for pref in _PREFIX_MAP:
        if doc_id.startswith(pref):
            return pref
    return ""


def _needs_lookup(raw: Any) -> bool:
    return bool(raw) and isinstance(raw, str) and bool(_prefix_of(_split_step(raw)[0]))


async def _resolve_numbers(ids_by_prefix: Dict[str, set]) -> Dict[str, str]:
    """Ambil nomor manusia untuk seluruh id teknis (satu query per koleksi)."""
    out: Dict[str, str] = {}
    for pref, ids in ids_by_prefix.items():
        if not ids:
            continue
        coll, fields, _ = _PREFIX_MAP[pref]
        proj = {"_id": 0, "id": 1}
        for f in fields:
            proj[f] = 1
        try:
            cursor = db[coll].find({"id": {"$in": list(ids)}}, proj)
            async for doc in cursor:
                num = ""
                for f in fields:
                    if doc.get(f):
                        num = str(doc[f])
                        break
                out[doc["id"]] = num or ""
        except Exception:  # noqa: BLE001, S112 — koleksi belum ada di env tertentu;
            # label harus selalu jatuh kembali dengan aman (layar tak boleh pecah).
            continue
    return out


def _compose(raw: str, number: str, step: str, kind: str) -> str:
    if not number:
        return f"{kind} {DELETED_LABEL}"
    return f"{number} · langkah {step}" if step else number


async def attach_source_labels(movements: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Tambahkan `source_document_label` pada setiap mutasi (in-place, lalu balik list).

    Aman dipakai pada respons paginasi maupun daftar penuh. Tidak pernah melempar:
    bila resolusi gagal, label jatuh kembali ke `source_document` apa adanya supaya
    layar tidak pernah kosong.
    """
    rows = list(movements or [])
    if not rows:
        return rows

    ids_by_prefix: Dict[str, set] = {p: set() for p in _PREFIX_MAP}
    for m in rows:
        raw = m.get("source_document")
        if _needs_lookup(raw):
            base, _step = _split_step(raw)
            ids_by_prefix[_prefix_of(base)].add(base)

    numbers = await _resolve_numbers(ids_by_prefix)

    for m in rows:
        raw = m.get("source_document")
        if not raw:
            m["source_document_label"] = "-"
            continue
        if not _needs_lookup(raw):
            m["source_document_label"] = str(raw)
            continue
        base, step = _split_step(str(raw))
        pref = _prefix_of(base)
        kind = _PREFIX_MAP[pref][2]
        m["source_document_label"] = _compose(raw, numbers.get(base, ""), step, kind)
        m["source_document_missing"] = base not in numbers
    return rows


# ─── FASE E-5 · E5.3 — ENTITAS LAWAN PADA MUTASI PINDAH-KEPEMILIKAN ──────────
# Mutasi `ownership_transfer_in/out` menyimpan `from_owner_entity_id` &
# `to_owner_entity_id` berupa **id teknis** (`ent_kanda`). Sebelum fase ini id itu
# dikirim mentah ke layar dan layar Mutasi tidak menampilkannya sama sekali —
# petugas membaca "Alih Kepemilikan Masuk" tanpa tahu asalnya, sementara id
# teknisnya tetap ada di respons (melanggar aturan bahasa antarmuka
# `scripts/audit_i18n_id.py` sekaligus tidak berguna bagi manusia).
#
# Aturan yang dipakai di sini:
#   * nama yang dipakai = `short_name` (mis. "Kanda"/"KSC"). Kalau kosong →
#     `doc_prefix`. Kalau dua-duanya kosong → kalimat netral, BUKAN id teknis.
#   * `nama badan hukum lengkap` hanya untuk peran LINTAS-ENTITAS (admin/manajer).
#   * untuk peran NON-lintas, id teknis `from_owner_entity_id`/`to_owner_entity_id`
#     DICABUT dari respons — yang tersisa hanya nama singkat, sesuai E5.3.
UNKNOWN_ENTITY_LABEL = "badan usaha lain"
_RAW_ENTITY_FIELDS = ("from_owner_entity_id", "to_owner_entity_id")


async def _entity_short_names(ids: Set[str]) -> Dict[str, Dict[str, str]]:
    """Peta id badan usaha → {short, legal}. Satu query untuk seluruh halaman."""
    if not ids:
        return {}
    try:
        rows = await db.business_entities.find(
            {"id": {"$in": list(ids)}},
            {"_id": 0, "id": 1, "short_name": 1, "doc_prefix": 1, "legal_name": 1},
        ).to_list(200)
    except Exception:  # noqa: BLE001 — label tidak boleh pernah memecahkan layar
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for e in rows:
        short = (e.get("short_name") or e.get("doc_prefix") or "").strip()
        out[e["id"]] = {
            "short": short or UNKNOWN_ENTITY_LABEL,
            "legal": (e.get("legal_name") or short or UNKNOWN_ENTITY_LABEL).strip(),
        }
    return out


async def short_name_of(entity_id: str) -> str:
    """NAMA SINGKAT satu badan usaha ("Kanda"), untuk disimpan sebagai snapshot jejak.

    FASE E-9 — dipakai jejak perolehan roll (`acquired_history[]`). Jejak itu HARUS
    bisa dibaca siapa pun yang berhak melihat roll-nya, sementara **id teknis badan
    usaha lawan tidak boleh ikut** (aturan E5.3, ditegakkan runtime oleh
    `scripts/entity_audit/audit_entity_isolation.py` yang memerah begitu ada nilai
    `ent_*` milik badan usaha lain muncul di respons). Karena itu yang DISIMPAN pada
    jejak adalah namanya, bukan idnya; id presisi tetap ada di `inventory_movements`
    (`from_owner_entity_id`/`to_owner_entity_id`) yang memang sudah ter-scope & ter-redaksi.
    """
    if not entity_id:
        return ""
    names = await _entity_short_names({str(entity_id)})
    return names.get(str(entity_id), {}).get("short", UNKNOWN_ENTITY_LABEL)


async def attach_counterparty_labels(movements: Iterable[Dict[str, Any]], *,
                                     cross_entity: bool = False,
                                     viewer_entity_ids: Optional[Iterable[str]] = None,
                                     ) -> List[Dict[str, Any]]:
    """Beri nama singkat badan usaha lawan pada mutasi pindah-kepemilikan.

    Field turunan yang ditambahkan (tidak mengubah data tersimpan):
      `counterparty_entity_name`  — NAMA SINGKAT badan usaha lawan ("Kanda")
      `counterparty_direction`    — `"in"` (masuk ke kita) / `"out"` (keluar ke sana)
      `counterparty_label`        — kalimat siap tampil: "dari Kanda" / "ke Kanda"

    Untuk peran **lintas-entitas** ditambah `from_entity_name`/`to_entity_name`
    (nama badan hukum) karena mereka memang berhak melihat rincian grup, dan id
    teknis dibiarkan. Untuk peran **non-lintas** id teknis dicabut.

    Tidak pernah melempar: bila resolusi gagal, mutasi tetap kembali utuh
    (jejak lebih penting daripada kosmetik).
    """
    rows = list(movements or [])
    if not rows:
        return rows

    viewer = {v for v in (viewer_entity_ids or []) if v}
    ids: Set[str] = set()
    for m in rows:
        for f in _RAW_ENTITY_FIELDS:
            val = m.get(f)
            if val:
                ids.add(str(val))
    names = await _entity_short_names(ids) if ids else {}

    for m in rows:
        src, dst = m.get("from_owner_entity_id"), m.get("to_owner_entity_id")
        if cross_entity:
            if src:
                m["from_entity_name"] = names.get(str(src), {}).get("legal", str(src))
            if dst:
                m["to_entity_name"] = names.get(str(dst), {}).get("legal", str(dst))
        if not src or not dst or src == dst:
            # bukan perpindahan antar badan usaha → tak ada lawan yang perlu dilabeli
            if not cross_entity:
                for f in _RAW_ENTITY_FIELDS:
                    m.pop(f, None)
            continue
        # Sisi mana yang "kita"? Baris mutasi selalu milik satu pemilik
        # (`owner_entity_id`), jadi lawannya adalah sisi yang lain. Bila baris ini
        # dibaca dalam mode gabungan, `owner_entity_id` tetap menentukan arah
        # supaya baris keluar & baris masuk tidak tertukar.
        owner = str(m.get("owner_entity_id") or "")
        if owner and owner == str(dst):
            direction, other = "in", str(src)
        elif owner and owner == str(src):
            direction, other = "out", str(dst)
        else:
            # pemilik tidak dikenali (data lama) → jatuh kembali ke arah kuantitas
            direction = "in" if float(m.get("quantity") or 0) >= 0 else "out"
            other = str(src) if direction == "in" else str(dst)
        short = names.get(other, {}).get("short", UNKNOWN_ENTITY_LABEL)
        m["counterparty_entity_name"] = short
        m["counterparty_direction"] = direction
        m["counterparty_label"] = f"dari {short}" if direction == "in" else f"ke {short}"
        if viewer and owner and owner not in viewer:
            # baris ini bukan milik badan usaha yang sedang dilihat: penanda jujur
            m["counterparty_foreign_row"] = True
        if not cross_entity:
            for f in _RAW_ENTITY_FIELDS:
                m.pop(f, None)
    return rows
