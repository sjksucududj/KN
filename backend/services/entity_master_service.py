"""entity_master_service (FASE E-4 · E4a) — MASTER BERLAPIS: **global → badan usaha**.

KENAPA ADA BERKAS INI
Keputusan pemilik #6: *"semua master/konfigurasi yang masih bersama harus jadi per
entitas"*. Tetapi memindahkan master SHARED → SCOPED secara naif akan **menghilangkan
baris lama dari layar** (baris tanpa `entity_id` tidak cocok filter apa pun) dan memaksa
admin menyalin 6 syarat pembayaran × puluhan badan usaha satu per satu.

Pola yang dipakai (sama dengan `incentive_rates`/`approval_rules` sejak FASE E-0):
    baris `entity_id="all"`  = **GLOBAL**, berlaku untuk semua badan usaha (bawaan)
    baris `entity_id="ent_x"` = **OVERRIDE**, hanya untuk badan usaha itu — dan MENANG
Satu kunci (`key_field`, mis. `code`) hanya boleh muncul sekali per lapisan, sehingga
"harga efektif"-nya master selalu tunggal: override kalau ada, kalau tidak global.

Yang DISENGAJA di sini:
  * `patch` pada baris GLOBAL saat satu badan usaha sedang aktif **DITOLAK** dengan
    kalimat menuntun. Alasannya nyata: admin yang sedang bekerja "di CV Kanda Suka"
    dan menekan Simpan pada baris Global akan mengubah nilai untuk SEMUA badan usaha
    tanpa sadar. Jalur yang benar: tombol **Buat khusus <badan usaha>** (`override`).
  * `revert` MENGHAPUS baris override (bukan menonaktifkan). Baris override yang
    "nonaktif" tetap sebuah override — ia akan tetap menutupi baris global dan
    membingungkan. Jejaknya tersimpan di audit log, bukan di master.
  * Di mode "Semua Entitas" (`view_all`) baris baru lahir sebagai **GLOBAL**, karena
    tidak ada satu badan usaha yang bisa memilikinya.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from db import db
from core_utils import new_id, now_iso, safe_doc
from entity_scope import EntityContext, assert_write_entity

# Nilai field entitas yang dianggap GLOBAL. `""`/`None` ditoleransi karena data
# demo/lama pernah menulis kosong sebelum migrasi E4b berjalan.
GLOBAL_ID = "all"
GLOBAL_VALUES: Tuple[Any, ...] = ("all", "", None)


@dataclass(frozen=True)
class MasterSpec:
    kind: str                 # slug di URL, mis. "payment-terms"
    collection: str
    label: str                # nama untuk manusia (bahasa Indonesia)
    key_field: str            # kunci keunikan per lapisan
    name_field: str           # field yang dipakai sebagai judul baris
    id_prefix: str
    fields: Tuple[str, ...]   # field yang boleh dibuat/diubah lewat API generik
    sort: Tuple[Tuple[str, int], ...] = (("sort", 1),)
    active_field: str = "active"
    manage: bool = True       # False = hanya ditampilkan (punya layar sendiri)
    screen: str = ""          # deep-link `?view=` layar khusus (bila manage=False)
    hint: str = ""            # penjelasan singkat di layar


MASTERS: Dict[str, MasterSpec] = {
    "payment-terms": MasterSpec(
        kind="payment-terms", collection="payment_terms", label="Syarat Pembayaran",
        key_field="code", name_field="name", id_prefix="pterm",
        fields=("code", "name", "type", "net_days", "dp_percent",
                "installment_count", "sort", "active", "notes"),
        sort=(("sort", 1), ("code", 1)),
        hint="Dipakai pesanan penjualan, POS, dan penagihan. Badan usaha non-PKP "
             "biasanya butuh syarat bayar sendiri.",
    ),
    "expense-categories": MasterSpec(
        kind="expense-categories", collection="expense_categories", label="Kategori Biaya",
        key_field="code", name_field="label", id_prefix="excat",
        fields=("code", "label", "account_code", "sort", "active", "notes"),
        sort=(("sort", 1), ("code", 1)),
        hint="Memetakan pengeluaran kas kecil & penyelesaian uang muka ke akun buku besar. "
             "Akun tujuan bisa berbeda antar badan usaha.",
    ),
    "document-templates": MasterSpec(
        kind="document-templates", collection="document_templates",
        label="Template Dokumen & Kop Surat",
        key_field="document_type", name_field="name", id_prefix="tmpl",
        fields=("document_type", "name", "header", "footer", "columns", "logo_url",
                "paper_size", "orientation", "margin_mm", "signature_left",
                "signature_right", "section_order", "notes", "status"),
        sort=(("document_type", 1),),
        active_field="status",
        hint="Kop surat & tata letak Surat Jalan / Invoice. Tiap badan usaha punya nama, "
             "alamat, dan logo sendiri sehingga template ini wajib bisa ditimpa.",
    ),
    "sales-return-policies": MasterSpec(
        kind="sales-return-policies", collection="sales_return_policies",
        label="Kebijakan Retur Jual",
        key_field="name", name_field="name", id_prefix="srpol",
        fields=("name", "scope", "scope_ref", "window_days", "restocking_fee_pct",
                "require_inspection", "enforce_window", "link_to_supplier_window",
                "condition_requirements", "valid_from", "valid_until", "notes", "status"),
        sort=(("created_at", -1),),
        active_field="status",
        manage=False, screen="return-policies",
        hint="Jendela retur, biaya restocking, dan kewajiban inspeksi. Dikelola di layar "
             "Kebijakan Retur.",
    ),
    "incentive-rates": MasterSpec(
        kind="incentive-rates", collection="incentive_rates", label="Tarif Insentif Sales",
        key_field="category", name_field="category", id_prefix="irate",
        fields=(),
        sort=(("category", 1),),
        manage=False, screen="crm",
        hint="Tarif komisi per kategori produk. Dikelola di layar CRM › Tarif Insentif.",
    ),
    "approval-rules": MasterSpec(
        kind="approval-rules", collection="approval_rules", label="Aturan Persetujuan",
        key_field="doc_type", name_field="doc_type", id_prefix="aprule",
        fields=(),
        sort=(("doc_type", 1), ("sort", 1)),
        manage=False, screen="approval-rules",
        hint="Ambang nilai & peran yang wajib menyetujui. Dikelola di layar Aturan Persetujuan.",
    ),
    # ── FASE L (2026-08-18) — LINI PRODUK: pembagian kerja MD (woven/knit/printing)
    # yang HARUS bisa bertambah tanpa ubah kode. Dibuat master berlapis supaya satu
    # badan usaha boleh punya lini yang tidak dipakai badan usaha lain (mis. hanya
    # KSC yang mengerjakan printing), tanpa memaksa seluruh grup.
    # Nilai benih ada di `domain_registry.PRODUCT_LINES`; pembacanya satu:
    # `services/master_registry.py`.
    "product-lines": MasterSpec(
        kind="product-lines", collection="product_lines", label="Lini Produk",
        key_field="code", name_field="name", id_prefix="pline",
        fields=("code", "name", "sort", "active", "notes",
                # INV-LINE-02 — pengikat ke fisika kain ("" = tidak mengikat, mis. printing)
                "fabric_type_required",
                # USULAN satuan saat membuat produk/PO. BUKAN sumber satuan kendali
                # (itu tetap `fabric_type.control_uom` + `products.base_unit`).
                "measure_unit_default",
                # urutan tahap untuk papan PO & SPK makloon (FASE T memakai kode master tahap)
                "stage_sequence",
                # usulan jenis sampling saat membuat permintaan sample (FASE S)
                "sample_types_default"),
        sort=(("sort", 1), ("code", 1)),
        hint="Pembagian kerja MD: woven / knit / printing (bisa ditambah). Menentukan "
             "penyaring 12 layar, pagar akses staf (Akun & Akses → Lini), urutan tahap "
             "papan PO, dan usulan jenis sampling.",
    ),
    # ── FASE T (2026-08-19) — TAHAPAN PROSES: daftar langkah kerja pemilik
    # (benang · tenun · rajut · pfp · pfd · celup · SCREEN · printing · proofing ·
    # inspect) yang HARUS bisa bertambah tanpa programmer. Dibuat berlapis karena
    # satu badan usaha boleh punya langkah yang tidak dipakai badan usaha lain
    # (mis. hanya KSC yang membuat kasa sendiri).
    # Nilai benih: `domain_registry.PROCESS_STAGES`; pembacanya satu:
    # `services/master_registry.py` (sama seperti lini produk FASE L).
    "process-stages": MasterSpec(
        kind="process-stages", collection="process_stages", label="Tahapan Proses",
        key_field="code", name_field="name", id_prefix="pstg",
        fields=("code", "name", "kind", "applies_to_lines", "seq", "active", "notes",
                # mitra wajib? (SPK tanpa mitra hanya DIPERINGATKAN — keputusan 3b)
                "needs_vendor",
                # sambungan ke mesin tarif/estimasi makloon
                "process_type", "target_use",
                # changes_stage=False → kain TIDAK berubah (qty keluar = qty masuk)
                "changes_stage", "from_stage", "to_stage",
                "tariff_basis_default",
                # FASE T (1c) — apakah KAIN bergerak: moves | service_only | either
                "material_flow", "material_flow_default"),
        sort=(("seq", 1), ("code", 1)),
        hint="Langkah kerja yang dipantau papan PO & SPK makloon. `process_type` "
             "menyambung ke mesin tarif/estimasi; `changes_stage=false` = tidak "
             "mengubah kain (mis. pembuatan screen/kasa); `material_flow` menentukan "
             "apakah kainnya benar-benar dikirim ke mitra atau hanya jasa.",
    ),
}

# Koleksi yang dikelola mesin ini — dipakai gate & migrasi supaya daftarnya satu sumber.
LAYERED_COLLECTIONS: Tuple[str, ...] = tuple(s.collection for s in MASTERS.values())


def spec(kind: str) -> MasterSpec:
    s = MASTERS.get(kind)
    if not s:
        raise HTTPException(status_code=404, detail=f"Master '{kind}' tidak dikenal")
    return s


def is_global(doc: Dict[str, Any]) -> bool:
    return doc.get("entity_id") in GLOBAL_VALUES


async def _entity_names() -> Dict[str, str]:
    rows = await db.business_entities.find({}, {"_id": 0, "id": 1, "short_name": 1,
                                                "legal_name": 1}).to_list(500)
    return {r["id"]: (r.get("short_name") or r.get("legal_name") or r["id"]) for r in rows}


def _is_active(doc: Dict[str, Any], s: MasterSpec) -> bool:
    """Aktif/tidak — beberapa master memakai `active: bool`, lain `status: str`."""
    if s.active_field == "status":
        return str(doc.get("status") or "active") != "inactive"
    return doc.get(s.active_field, True) is not False


def decorate(doc: Dict[str, Any], s: MasterSpec, active_entity_id: str,
             names: Dict[str, str], view_all: bool = False) -> Dict[str, Any]:
    """Menempeli baris dengan **asal lapisan** supaya UI tidak perlu menebak."""
    out = dict(doc)
    out.pop("_id", None)
    glob = is_global(doc)
    owner = "" if glob else str(doc.get("entity_id") or "")
    out["entity_scope"] = "global" if glob else "entity"
    out["owner_entity_id"] = owner
    out["owner_label"] = names.get(owner, owner)
    if glob:
        out["source_label"] = "Global"
    elif owner == active_entity_id:
        out["source_label"] = "Badan usaha ini"
    else:
        out["source_label"] = names.get(owner, owner)
    # Baris global hanya boleh diubah dari mode "Semua Entitas" (lihat docstring modul).
    out["can_edit_here"] = bool(view_all) if glob else (owner == active_entity_id or view_all)
    out["is_active"] = _is_active(doc, s)
    return out


async def list_layered(kind: str, ctx: EntityContext, entity_id: Optional[str] = None,
                       include_inactive: bool = False) -> Dict[str, Any]:
    """Semua baris yang BERLAKU untuk satu badan usaha: global + override-nya.

    Bukan `resolve_list_scope` biasa: baris global WAJIB ikut tampil, kalau tidak
    layar akan terlihat kosong padahal nilainya sedang dipakai.
    """
    s = spec(kind)
    target = entity_id or ("" if getattr(ctx, "view_all", False) else ctx.active_entity_id)
    if target and target not in ("all", *ctx.allowed_entity_ids):
        raise HTTPException(status_code=403, detail="Tidak berwenang atas badan usaha ini")

    if target and target != "all":
        q: Dict[str, Any] = {"$or": [{"entity_id": target},
                                     {"entity_id": {"$in": list(GLOBAL_VALUES)}}]}
    else:
        # Mode gabungan: perlihatkan global + seluruh override yang boleh dilihat.
        q = {"$or": [{"entity_id": {"$in": list(GLOBAL_VALUES)}},
                     {"entity_id": {"$in": list(ctx.allowed_entity_ids)}}]}

    rows = await db[s.collection].find(q, {"_id": 0}).to_list(1000)
    names = await _entity_names()
    view_all = bool(getattr(ctx, "view_all", False))
    out = [decorate(r, s, target, names, view_all) for r in rows]
    if not include_inactive:
        out = [r for r in out if r["is_active"]]

    # Baris global yang SUDAH ditimpa ditandai supaya UI bisa meredupkannya.
    overridden = {r.get(s.key_field) for r in out if r["entity_scope"] == "entity"}
    for r in out:
        r["is_overridden"] = bool(r["entity_scope"] == "global"
                                  and r.get(s.key_field) in overridden)

    for field, direction in reversed(s.sort):
        out.sort(key=lambda r, f=field: (r.get(f) is None, r.get(f) or 0 if isinstance(r.get(f), (int, float)) else str(r.get(f) or "")),
                 reverse=direction < 0)

    return {
        "kind": s.kind, "label": s.label, "hint": s.hint, "key_field": s.key_field,
        "name_field": s.name_field, "manage": s.manage, "screen": s.screen,
        "entity_id": target, "rows": out,
        "summary": {
            "total": len(out),
            "global": sum(1 for r in out if r["entity_scope"] == "global"),
            "entity": sum(1 for r in out if r["entity_scope"] == "entity"),
            "overridden": sum(1 for r in out if r["is_overridden"]),
        },
    }


async def effective_rows(kind: str, entity_id: str = "",
                         include_inactive: bool = False) -> List[Dict[str, Any]]:
    """Baris EFEKTIF untuk satu badan usaha — **tanpa kembar**.

    Dipakai semua konsumen (dropdown syarat bayar, pemetaan akun kategori biaya,
    pemilihan template cetak). Override badan usaha menutupi baris global ber-kunci
    sama; baris global tanpa override tetap ikut.
    """
    s = spec(kind)
    ent = (entity_id or "").strip()
    if ent and ent != "all":
        q: Dict[str, Any] = {"$or": [{"entity_id": ent},
                                     {"entity_id": {"$in": list(GLOBAL_VALUES)}}]}
    else:
        q = {"entity_id": {"$in": list(GLOBAL_VALUES)}}
    rows = await db[s.collection].find(q, {"_id": 0}).to_list(1000)
    if not include_inactive:
        rows = [r for r in rows if _is_active(r, s)]

    best: Dict[Any, Dict[str, Any]] = {}
    for r in rows:
        key = r.get(s.key_field)
        cur = best.get(key)
        if cur is None or (is_global(cur) and not is_global(r)):
            best[key] = r
    out = list(best.values())
    for field, direction in reversed(s.sort):
        out.sort(key=lambda r, f=field: (r.get(f) is None, r.get(f) or 0 if isinstance(r.get(f), (int, float)) else str(r.get(f) or "")),
                 reverse=direction < 0)
    return [safe_doc(r) for r in out]


def _target_entity_for_write(ctx: EntityContext, requested: Optional[str]) -> str:
    """Badan usaha pemilik baris baru. Mode gabungan → GLOBAL (tak ada pemiliknya)."""
    req = (requested or "").strip()
    if req in ("all", *[v for v in GLOBAL_VALUES if isinstance(v, str) and v]):
        return GLOBAL_ID
    if getattr(ctx, "view_all", False):
        return GLOBAL_ID
    if req:
        if req not in ctx.allowed_entity_ids:
            raise HTTPException(status_code=403, detail="Tidak berwenang atas badan usaha ini")
        return req
    return ctx.active_entity_id


async def _assert_key_free(s: MasterSpec, key_value: Any, entity_id: str,
                           exclude_id: str = "") -> None:
    q: Dict[str, Any] = {s.key_field: key_value}
    if entity_id == GLOBAL_ID:
        q["entity_id"] = {"$in": list(GLOBAL_VALUES)}
    else:
        q["entity_id"] = entity_id
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    if await db[s.collection].find_one(q, {"_id": 0, "id": 1}):
        where = "Global" if entity_id == GLOBAL_ID else "badan usaha ini"
        raise HTTPException(
            status_code=409,
            detail=f"{s.label}: '{key_value}' sudah ada pada lapisan {where}.")


async def create(kind: str, data: Dict[str, Any], ctx: EntityContext) -> Dict[str, Any]:
    s = spec(kind)
    if not s.manage:
        raise HTTPException(status_code=400,
                            detail=f"{s.label} dikelola di layarnya sendiri.")
    target = _target_entity_for_write(ctx, data.get("entity_id"))
    payload = {k: v for k, v in data.items() if k in s.fields}
    key_value = payload.get(s.key_field)
    if key_value in (None, ""):
        raise HTTPException(status_code=422, detail=f"Field '{s.key_field}' wajib diisi.")
    await _assert_key_free(s, key_value, target)
    doc = {
        "id": new_id(s.id_prefix),
        "entity_id": target,
        **payload,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    doc.setdefault(s.active_field, "active" if s.active_field == "status" else True)
    await db[s.collection].insert_one(dict(doc))
    names = await _entity_names()
    return decorate(doc, s, ctx.active_entity_id, names,
                    bool(getattr(ctx, "view_all", False)))


async def _load(s: MasterSpec, doc_id: str) -> Dict[str, Any]:
    doc = await db[s.collection].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail=f"{s.label} tidak ditemukan")
    return doc


def _assert_can_edit(s: MasterSpec, doc: Dict[str, Any], ctx: EntityContext) -> None:
    view_all = bool(getattr(ctx, "view_all", False))
    if is_global(doc):
        if not view_all:
            raise HTTPException(
                status_code=409,
                detail=(f"Baris ini **Global** — dipakai semua badan usaha. Mengubahnya dari "
                        f"konteks satu badan usaha akan mengubah nilai untuk semuanya. "
                        f"Tekan \u201cBuat khusus\u201d untuk membuat salinan hanya untuk badan "
                        f"usaha aktif, atau pindah ke mode \u201cSemua Entitas\u201d bila memang "
                        f"ingin mengubah nilai global."))
        return
    owner = str(doc.get("entity_id") or "")
    if owner not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=403, detail="Tidak berwenang atas badan usaha ini")


async def _assert_deactivation_safe(s: MasterSpec, doc: Dict[str, Any],
                                   upd: Dict[str, Any]) -> None:
    """FASE T (INV-DOMAIN-06 aturan A) — jangan matikan tahap yang MASIH dipakai dokumen.

    Kenapa dijaga di API dan bukan hanya di gate: gate berjalan saat seseorang
    menjalankannya, sedangkan pemilik menonaktifkan tahap dari layar kapan saja.
    Kalau tahap yang masih dipakai 7 langkah SPK hilang dari master, papan menampilkan
    langkah **tanpa nama** dan mesin jatuh ke jalur kompatibilitas tanpa ada yang tahu.
    Penolakan di sini menyebut ANGKA pemakainya supaya pemiliknya tahu apa yang harus
    dibereskan lebih dulu — bukan sekadar "tidak boleh".
    """
    if s.kind != "process-stages":
        return
    turning_off = (upd.get("active") is False
                   or str(upd.get("status") or "") == "inactive")
    code = str(upd.get("code") or doc.get("code") or "").strip().lower()
    renaming = "code" in upd and str(upd["code"]).strip().lower() != str(
        doc.get("code") or "").strip().lower()
    if not (turning_off or renaming) or not code:
        return
    old_code = str(doc.get("code") or "").strip().lower()
    n = await db.makloon_orders.count_documents({"steps.stage_code": old_code})
    if not n:
        return
    action = "dinonaktifkan" if turning_off else "diganti kodenya"
    raise HTTPException(
        status_code=409,
        detail=(f"Tahapan '{old_code}' tidak bisa {action}: masih dipakai {n} SPK makloon. "
                "Kalau tahap ini benar-benar sudah tidak dipakai, pindahkan dulu SPK-nya "
                "ke tahap lain (atau selesaikan/batalkan SPK-nya), baru nonaktifkan. "
                "Menonaktifkannya sekarang membuat langkah pada SPK itu kehilangan nama "
                "di papan."))


async def patch(kind: str, doc_id: str, data: Dict[str, Any],
                ctx: EntityContext) -> Dict[str, Any]:
    s = spec(kind)
    if not s.manage:
        raise HTTPException(status_code=400,
                            detail=f"{s.label} dikelola di layarnya sendiri.")
    doc = await _load(s, doc_id)
    _assert_can_edit(s, doc, ctx)
    upd = {k: v for k, v in (data or {}).items() if k in s.fields}
    if not upd:
        raise HTTPException(status_code=422, detail="Tidak ada field yang bisa diubah.")
    if s.key_field in upd and upd[s.key_field] != doc.get(s.key_field):
        await _assert_key_free(s, upd[s.key_field],
                               doc.get("entity_id") or GLOBAL_ID, exclude_id=doc_id)
    await _assert_deactivation_safe(s, doc, upd)
    upd["updated_at"] = now_iso()
    await db[s.collection].update_one({"id": doc_id}, {"$set": upd})
    names = await _entity_names()
    return decorate({**doc, **upd}, s, ctx.active_entity_id, names,
                    bool(getattr(ctx, "view_all", False)))


async def override(kind: str, doc_id: str, ctx: EntityContext) -> Dict[str, Any]:
    """Salin baris GLOBAL menjadi baris khusus badan usaha aktif."""
    s = spec(kind)
    if not s.manage:
        raise HTTPException(status_code=400,
                            detail=f"{s.label} dikelola di layarnya sendiri.")
    target = assert_write_entity(ctx, f"membuat {s.label} khusus badan usaha")
    doc = await _load(s, doc_id)
    if not is_global(doc):
        raise HTTPException(status_code=409,
                            detail="Baris ini sudah khusus badan usaha — tidak perlu ditimpa lagi.")
    await _assert_key_free(s, doc.get(s.key_field), target)
    clone = {k: v for k, v in doc.items() if k not in ("id", "entity_id", "created_at",
                                                       "updated_at", "_id")}
    new_doc = {
        "id": new_id(s.id_prefix), "entity_id": target, **clone,
        "overrides_id": doc_id,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db[s.collection].insert_one(dict(new_doc))
    names = await _entity_names()
    return decorate(new_doc, s, target, names, False)


async def revert(kind: str, doc_id: str, ctx: EntityContext) -> Dict[str, Any]:
    """Lepas override badan usaha → nilai kembali mengikuti baris GLOBAL."""
    s = spec(kind)
    if not s.manage:
        raise HTTPException(status_code=400,
                            detail=f"{s.label} dikelola di layarnya sendiri.")
    doc = await _load(s, doc_id)
    if is_global(doc):
        raise HTTPException(
            status_code=409,
            detail=("Baris Global tidak bisa \u201cdikembalikan ke global\u201d. "
                    "Nonaktifkan saja bila tidak dipakai lagi."))
    owner = str(doc.get("entity_id") or "")
    if owner not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=403, detail="Tidak berwenang atas badan usaha ini")
    await db[s.collection].delete_one({"id": doc_id})
    fallback = await db[s.collection].find_one(
        {s.key_field: doc.get(s.key_field), "entity_id": {"$in": list(GLOBAL_VALUES)}},
        {"_id": 0})
    return {
        "removed_id": doc_id,
        "key": doc.get(s.key_field),
        "fell_back_to_global": bool(fallback),
        "snapshot": safe_doc(doc),
    }


async def resolve_row(kind: str, key_value: Any, entity_id: str = "",
                      include_inactive: bool = False) -> Optional[Dict[str, Any]]:
    """SATU baris efektif untuk satu kunci — override badan usaha MENANG atas global.

    Dipakai konsumen yang mencari satu nilai (mis. `net_days` untuk kode syarat bayar
    `NET30`, atau template `surat_jalan`). Dulu mereka memanggil
    `find_one({"code": code})` sehingga hasilnya **acak** begitu ada dua lapisan:
    Mongo mengembalikan baris mana pun yang lebih dulu ditemukan.
    """
    s = spec(kind)
    ent = (entity_id or "").strip()
    if ent and ent not in GLOBAL_VALUES:
        doc = await db[s.collection].find_one({s.key_field: key_value, "entity_id": ent},
                                              {"_id": 0})
        if doc and (include_inactive or _is_active(doc, s)):
            return safe_doc(doc)
    doc = await db[s.collection].find_one(
        {s.key_field: key_value, "entity_id": {"$in": list(GLOBAL_VALUES)}}, {"_id": 0})
    if doc and (include_inactive or _is_active(doc, s)):
        return safe_doc(doc)
    # Cadangan terakhir: baris tanpa lapisan yang jelas (data belum termigrasi).
    doc = await db[s.collection].find_one({s.key_field: key_value}, {"_id": 0})
    if doc and (include_inactive or _is_active(doc, s)):
        return safe_doc(doc)
    return None


async def effective_map(kind: str, entity_id: str = "") -> Dict[Any, Dict[str, Any]]:
    """Peta `kunci → baris efektif` untuk satu badan usaha (mis. code → syarat bayar)."""
    s = spec(kind)
    rows = await effective_rows(kind, entity_id)
    return {r.get(s.key_field): r for r in rows if r.get(s.key_field) is not None}


async def groups_summary(ctx: EntityContext) -> List[Dict[str, Any]]:
    """Ringkasan tiap kelompok master untuk kartu di layar."""
    names = await _entity_names()
    target = "" if getattr(ctx, "view_all", False) else ctx.active_entity_id
    out: List[Dict[str, Any]] = []
    for s in MASTERS.values():
        rows = await db[s.collection].find(
            {"$or": [{"entity_id": {"$in": list(GLOBAL_VALUES)}},
                     {"entity_id": target or {"$in": list(ctx.allowed_entity_ids)}}]},
            {"_id": 0}).to_list(1000)
        rows = [r for r in rows if _is_active(r, s)]
        out.append({
            "kind": s.kind, "label": s.label, "hint": s.hint,
            "manage": s.manage, "screen": s.screen,
            "total": len(rows),
            "global": sum(1 for r in rows if is_global(r)),
            "entity": sum(1 for r in rows if not is_global(r)),
        })
    return out
