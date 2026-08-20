"""FASE L — PAGAR LINI PRODUK (woven · knit · printing · dan lini baru berikutnya).

KENAPA BERKAS INI ADA
=====================
Keputusan pemilik (sesi 2026-08-18): *"woven / knit / printing dikerjakan staf
berbeda; harus jadi master yang bisa bertambah, pembedanya pagar keras tapi bisa
dikonfigurasi (satu staf boleh dapat lebih dari satu lini), dan berlaku di semua
tempat — bukan hanya saat membuat PO."*

Pola yang ditiru: `services/product_exclusivity.py` (PS-20) — pagar yang **dipaksa
di backend lewat query Mongo**, bukan sekadar disembunyikan di UI, karena UI bisa
ditembus lewat API.

DUA ATURAN YANG MEMBUAT PAGAR INI TIDAK MEMBUAT LAYAR KOSONG
------------------------------------------------------------
1. **`users.allowed_line_codes` kosong = SEMUA LINI.** Itu bawaannya, sehingga
   10 akun yang sudah ada tidak kehilangan apa pun saat fase ini mendarat.
2. **Dokumen tanpa `line_code` selalu terlihat.** Data lama (19 produk, 11 SO,
   14 PO, 59 roll pada saat fase ini dibuat) belum bergolong lini; kalau baris
   tanpa lini disembunyikan, seluruh layar mendadak kosong bagi staf ber-lini —
   kelas kejadian yang paling cepat menghancurkan kepercayaan pengguna.
   Dijaga POC L3 & L4 (`backend/test_core_lini_poc.py`).

BATAS TEGAS DENGAN `fabric_type` (jangan dilanggar — ini titik duplikasi termahal)
---------------------------------------------------------------------------------
* `products.fabric_type` (`woven|knit`) = **FISIKA KAIN**. Dipakai mesin:
  `STAGE_TRANSITIONS`, `makloon_calc_service`, `STAGE_FIELD_RULES`,
  `KNIT_RELAXED_FIELDS`, satuan kendali (`FABRIC_TYPES[].control_uom`). **SSOT.**
* `products.line_code` = **PEMBAGIAN KERJA/BISNIS** (siapa mengerjakan, papan mana,
  penyaring mana). **Tidak dipakai rumus apa pun.**
* Invarian **INV-LINE-02**: bila master lini mengisi `fabric_type_required`, produk
  ber-lini itu WAJIB ber-`fabric_type` sama. Lini `printing` sengaja TIDAK mengikat
  (kain print bisa woven maupun knit).
"""
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException

LINE_FIELD = "line_code"
LINES_FIELD = "line_codes"          # turunan di kepala dokumen (SO/PO/PR)
ITEM_LINE_FIELD = "items.line_code"  # snapshot per baris dokumen


def norm(code: Any) -> str:
    """Bentuk kanonik satu kode lini: huruf kecil, tanpa spasi tepi.

    Satu tempat menormalkan supaya `"Printing "`, `"PRINTING"`, dan `"printing"`
    tidak pernah menjadi tiga lini berbeda di basis data — kelas bug yang sudah
    pernah terjadi pada kosakata satuan (`kg` vs `KG`, §D1 rencana MD ERP).
    """
    return str(code or "").strip().lower()


# ─── Siapa yang dibatasi ─────────────────────────────────────────────────────
def allowed_lines(actor: Optional[Dict[str, Any]]) -> List[str]:
    """Lini yang boleh diakses akun ini. **Kosong = semua lini** (bawaan)."""
    raw = (actor or {}).get("allowed_line_codes") or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(c).strip().lower() for c in raw if str(c).strip()]


def is_restricted(actor: Optional[Dict[str, Any]]) -> bool:
    return bool(allowed_lines(actor))


# ─── Query ───────────────────────────────────────────────────────────────────
def _empty_or_missing(field: str) -> Dict[str, Any]:
    """Baris lama tanpa lini — WAJIB tetap terlihat (lihat docstring modul)."""
    return {"$or": [{field: {"$in": ["", None]}}, {field: {"$exists": False}},
                    {field: []}]}


def visibility_query(actor: Optional[Dict[str, Any]],
                     field: str = LINE_FIELD) -> Dict[str, Any]:
    """Fragmen filter Mongo yang menghormati pagar lini akun.

    `{}` bila akun tidak dibatasi. Selain itu: baris ber-lini yang diizinkan
    **atau** baris tanpa lini (data lama).
    """
    lines = allowed_lines(actor)
    if not lines:
        return {}
    return {"$or": [{field: {"$in": lines}},
                    {field: {"$in": ["", None]}},
                    {field: {"$exists": False}},
                    {field: []}]}


def _merge(query: Optional[Dict[str, Any]], extra: Dict[str, Any]) -> Dict[str, Any]:
    """Gabung filter TANPA menimpa `$or` yang sudah ada (mis. dari `resolve_list_scope`).

    Kalau ada tabrakan kunci, keduanya dibungkus `$and` — bukan di-`update()`.
    Menimpa `$or` entitas dengan `$or` lini adalah cara paling cepat membocorkan
    dokumen PT lain, dan bocornya tak terlihat karena hasilnya "cuma" lebih banyak baris.
    """
    q = dict(query or {})
    if not extra:
        return q
    if not q:
        return dict(extra)
    if any(k in q for k in extra):
        return {"$and": [q, dict(extra)]}
    q.update(extra)
    return q


def parse_requested(requested: Optional[str]) -> List[str]:
    """`?line=woven,printing` → `["woven","printing"]`. Kosong / `all` → `[]`."""
    text = (requested or "").strip().lower()
    if not text or text in ("all", "semua", "*"):
        return []
    return [p.strip() for p in text.split(",") if p.strip()]


def narrow(query: Optional[Dict[str, Any]], actor: Optional[Dict[str, Any]],
           requested: Optional[str] = None, field: str = LINE_FIELD) -> Dict[str, Any]:
    """Filter akhir sebuah daftar: **pagar akun** + **pilihan penyaring pengguna**.

    Pagar selalu dipasang; pilihan pengguna hanya mempersempit (dan otomatis
    dipotong ke lini yang boleh ia lihat, supaya `?line=woven` dari staf printing
    tidak menjadi jalan belakang).
    """
    q = _merge(query, visibility_query(actor, field))
    picked = parse_requested(requested)
    if not picked:
        return q
    lines = allowed_lines(actor)
    if lines:
        picked = [p for p in picked if p in lines] or ["__tidak_ada__"]
    return _merge(q, {field: {"$in": picked}})


# ─── Aksi (tulis) ────────────────────────────────────────────────────────────
def lines_of_doc(doc: Optional[Dict[str, Any]], field: str = LINE_FIELD) -> List[str]:
    """Lini sebuah dokumen: `line_code` tunggal, `line_codes[]`, atau baris `items[]`."""
    d = doc or {}
    out: List[str] = []
    single = str(d.get(field) or "").strip().lower()
    if single:
        out.append(single)
    for c in d.get(LINES_FIELD) or []:
        c = str(c or "").strip().lower()
        if c:
            out.append(c)
    for it in d.get("items") or []:
        c = str((it or {}).get(LINE_FIELD) or "").strip().lower()
        if c:
            out.append(c)
    return list(dict.fromkeys(out))


def can_touch(actor: Optional[Dict[str, Any]], doc: Optional[Dict[str, Any]],
              field: str = LINE_FIELD) -> bool:
    lines = allowed_lines(actor)
    if not lines:
        return True
    doc_lines = lines_of_doc(doc, field)
    if not doc_lines:
        return True                      # dokumen lama tanpa lini — tidak dikunci
    return any(c in lines for c in doc_lines)


def assert_can_touch(actor: Optional[Dict[str, Any]], doc: Optional[Dict[str, Any]],
                     what: str = "dokumen ini", field: str = LINE_FIELD) -> None:
    """HTTP 403 ber-kalimat Indonesia bila di luar lini yang boleh diakses akun."""
    if can_touch(actor, doc, field):
        return
    doc_lines = ", ".join(lines_of_doc(doc, field)) or "-"
    mine = ", ".join(allowed_lines(actor)) or "-"
    raise HTTPException(
        status_code=403,
        detail=(f"{what} berada di lini {doc_lines}, sedangkan akses Anda hanya lini "
                f"{mine}. Minta admin menambah lini pada akun Anda bila memang "
                "pekerjaan ini milik Anda."))


def assert_can_order(actor: Optional[Dict[str, Any]],
                     product: Optional[Dict[str, Any]]) -> None:
    """Pagar saat memakai produk di dokumen (SO/PR/PO/transfer/retur)."""
    lines = allowed_lines(actor)
    if not lines:
        return
    code = str((product or {}).get(LINE_FIELD) or "").strip().lower()
    if not code or code in lines:
        return
    name = (product or {}).get("name") or (product or {}).get("sku") or "produk ini"
    raise HTTPException(
        status_code=403,
        detail=(f"Produk '{name}' termasuk lini {code}, sedangkan akses Anda hanya lini "
                f"{', '.join(lines)}."))


def filter_visible(actor: Optional[Dict[str, Any]], docs: Iterable[Dict[str, Any]],
                   field: str = LINE_FIELD) -> List[Dict[str, Any]]:
    """Saring daftar di memori (untuk sumber yang tidak lewat query Mongo langsung)."""
    lines = allowed_lines(actor)
    if not lines:
        return list(docs)
    return [d for d in docs if can_touch(actor, d, field)]


# ─── Validasi terhadap MASTER (bukan daftar hardcode) ────────────────────────
async def validate_codes(codes: Optional[Iterable[Any]], entity_id: str = "",
                         what: str = "Lini") -> List[str]:
    """Normalkan & pastikan setiap kode ADA di master lini yang aktif.

    Melempar HTTP 400 dengan menyebut pilihan yang sah (pola pesan yang sama
    dipakai `domain_registry` untuk enum lain) — bukan diam-diam membuang nilai.
    """
    from services import master_registry as mreg
    picked = [str(c).strip().lower() for c in (codes or []) if str(c).strip()]
    picked = list(dict.fromkeys(picked))
    if not picked:
        return []
    valid = await mreg.line_codes(entity_id)
    unknown = [c for c in picked if c not in valid]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=(f"{what} '{', '.join(unknown)}' tidak ada di master Lini Produk. "
                    f"Pilihan: {', '.join(valid)}. Tambah lininya dulu di "
                    "Pengaturan → Master → Lini Produk."))
    return picked


async def normalize_product(data: Dict[str, Any],
                            existing: Optional[Dict[str, Any]] = None,
                            entity_id: str = "") -> Dict[str, Any]:
    """Validasi `products.line_code` + **INV-LINE-02** (cocok dengan `fabric_type`).

    Dipanggil pada create & patch produk. Patch parsial yang tidak menyebut
    `line_code` maupun `fabric_type` tidak disentuh sama sekali.
    """
    if "line_code" not in data and "fabric_type" not in data:
        return data
    from services import master_registry as mreg
    code = str(data.get("line_code", (existing or {}).get("line_code", "")) or "").strip().lower()
    if not code:
        if "line_code" in data:
            data["line_code"] = ""
        return data
    (await validate_codes([code], entity_id, what="Lini produk"))
    meta = await mreg.line_meta(code, entity_id)
    need = str((meta or {}).get("fabric_type_required") or "").strip().lower()
    if need:
        fabric = str(data.get("fabric_type", (existing or {}).get("fabric_type", "")) or "").strip().lower()
        if fabric and fabric != need:
            raise HTTPException(
                status_code=400,
                detail=(f"Lini '{code}' hanya untuk kain {need}, tetapi jenis kain produk "
                        f"ini '{fabric}'. Perbaiki salah satunya (INV-LINE-02) — lini "
                        "adalah pembagian kerja, jenis kain adalah fisika kainnya."))
        if not fabric:
            data["fabric_type"] = need
    data["line_code"] = code
    return data


def stamp_items(items: List[Dict[str, Any]], products: Dict[str, Dict[str, Any]]) -> List[str]:
    """Snapshot `line_code` ke setiap baris dokumen + kembalikan `line_codes[]` kepala.

    **Snapshot, bukan join**: mengubah lini master produk TIDAK boleh mengubah
    baris dokumen yang sudah terbit (POC L5). Karena itu baris yang SUDAH punya
    `line_code` **tidak ditimpa** — dokumen turunan (PO dari PR, transfer dari SO)
    membawa snapshot dari induknya, dan induk itulah kebenarannya.
    """
    codes: List[str] = []
    for it in items or []:
        cur = str(it.get(LINE_FIELD) or "").strip().lower()
        if cur:
            codes.append(cur)
            it[LINE_FIELD] = cur
            continue
        prod = products.get(it.get("product_id")) or {}
        code = str(prod.get(LINE_FIELD) or "").strip().lower()
        it[LINE_FIELD] = code
        if code:
            codes.append(code)
    return sorted(set(codes))


def codes_from_items(items: Optional[Iterable[Dict[str, Any]]]) -> List[str]:
    """`line_codes[]` kepala dokumen dari baris yang SUDAH ber-`line_code`.

    Dipisah dari `stamp_items` karena banyak dokumen menstempel barisnya sendiri
    (sudah memegang dokumen produk di tangan) dan hanya butuh turunan kepalanya.
    Satu tempat menghitung turunan ini = satu arti untuk chip penyaring.
    """
    out = {str((it or {}).get(LINE_FIELD) or "").strip().lower() for it in (items or [])}
    return sorted(c for c in out if c)


async def stamp_items_from_db(db, items: Optional[List[Dict[str, Any]]]) -> List[str]:
    """Ambil produk baris dari basis data lalu stempel `line_code` + kembalikan turunan.

    Dipakai jalur yang tidak memegang peta produk (retur, permintaan internal).
    """
    rows = items or []
    ids = [i.get("product_id") for i in rows if (i or {}).get("product_id")]
    products: Dict[str, Dict[str, Any]] = {}
    if ids:
        cursor = db.products.find({"id": {"$in": list(set(ids))}},
                                  {"_id": 0, "id": 1, LINE_FIELD: 1})
        for p in await cursor.to_list(len(set(ids)) + 1):
            products[p["id"]] = p
    return stamp_items(rows, products)


async def stamp_doc(db, doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """SATU PINTU untuk dokumen ber-`items[]` sebelum `insert_one`.

    Kenapa satu pintu: dokumen dagang lahir dari **12 jalur** berbeda (PO manual,
    PO dari PR, PO dari RFQ, blanket call-off, transfer dari SO, transfer retur,
    transfer antar-PT, …). Kalau tiap jalur menstempel sendiri, satu jalur yang
    lupa akan melahirkan dokumen yang **tak muncul di chip lini mana pun** — dan
    gejalanya bukan galat, melainkan pekerjaan yang tidak pernah terlihat oleh
    orang yang seharusnya mengerjakannya. Dijaga gate `INV-LINE-01`.

    Aman dipanggil berulang & untuk dokumen tanpa `items` (tidak melakukan apa pun).
    """
    if not doc or not isinstance(doc.get("items"), list):
        return doc
    codes = await stamp_items_from_db(db, doc.get("items") or [])
    doc[LINES_FIELD] = codes
    return doc


# ─── Backfill data yang sudah ada (dipakai migrasi DAN seed) ─────────────────
#: Koleksi ber-`items[]`: tiap baris dapat snapshot, kepala dapat turunan.
ITEM_COLLECTIONS: Tuple[str, ...] = (
    "sales_orders", "purchase_orders", "purchase_requisitions",
    "warehouse_transfers", "sales_returns", "purchase_returns",
    "interco_transactions", "special_orders", "internal_requests", "rfqs",
)
#: Koleksi ber-satu-lini → (koleksi, field penunjuk produk berurutan).
SINGLE_COLLECTIONS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("inventory_rolls", ("product_id",)),
    ("inventory_lots", ("product_id",)),
    ("wms_tasks", ("product_id",)),
    ("md_specs", ("product_id",)),
    ("md_samples", ("product_id",)),
    ("design_gallery", ("product_id",)),
    ("makloon_orders", ("final_output_product_id", "material_product_id")),
)


async def product_line_map(db) -> Dict[str, str]:
    """`product_id → line_code` (satu bacaan untuk seluruh backfill)."""
    out: Dict[str, str] = {}
    async for p in db.products.find({}, {"_id": 0, "id": 1, LINE_FIELD: 1}):
        out[p["id"]] = norm(p.get(LINE_FIELD))
    return out


async def backfill(db, prod_line: Optional[Dict[str, str]] = None,
                   dry: bool = False) -> List[Tuple[str, int, int]]:
    """Stempel lini pada dokumen yang SUDAH ada. → [(koleksi, disentuh, total), …]

    Dipakai DUA pemanggil: `scripts/migrate_lini_produk.py` (basis data lama) dan
    `seed_realistic.py` (data demo). Sengaja satu fungsi: kalau seed memakai
    rumusnya sendiri, gate `INV-LINE-01` bisa hijau di basis data hasil migrasi
    tetapi merah di basis data hasil seed — dan sebaliknya. Satu pintu = satu arti.

    Aturan: baris yang SUDAH ber-`line_code` tidak pernah ditimpa (snapshot);
    produk tanpa lini tidak menstempel apa pun (kosong = terlihat semua akun).
    """
    prod_line = dict(prod_line) if prod_line is not None else await product_line_map(db)
    out: List[Tuple[str, int, int]] = []

    for coll in ITEM_COLLECTIONS:
        total = await db[coll].count_documents({})
        if not total:
            out.append((coll, 0, 0))
            continue
        touched = 0
        async for doc in db[coll].find({}, {"_id": 0, "id": 1, "items": 1, LINES_FIELD: 1}):
            items = doc.get("items")
            if not isinstance(items, list):
                continue
            rows = [dict(it) if isinstance(it, dict) else it for it in items]
            before = [(it.get(LINE_FIELD) if isinstance(it, dict) else None) for it in rows]
            derived = stamp_items([it for it in rows if isinstance(it, dict)],
                                  {pid: {LINE_FIELD: code} for pid, code in prod_line.items()})
            after = [(it.get(LINE_FIELD) if isinstance(it, dict) else None) for it in rows]
            changed = (before != after) or (derived != (doc.get(LINES_FIELD) or []))
            if changed:
                touched += 1
                if not dry:
                    await db[coll].update_one({"id": doc["id"]},
                                              {"$set": {"items": rows, LINES_FIELD: derived}})
        out.append((coll, touched, total))

    for coll, fields in SINGLE_COLLECTIONS:
        total = await db[coll].count_documents({})
        if not total:
            out.append((coll, 0, 0))
            continue
        touched = 0
        async for doc in db[coll].find({}, {"_id": 0, "id": 1, LINE_FIELD: 1,
                                            **{f: 1 for f in fields}}):
            if norm(doc.get(LINE_FIELD)):
                continue
            want = ""
            for f in fields:
                want = prod_line.get(doc.get(f), "")
                if want:
                    break
            if not want:
                continue
            touched += 1
            if not dry:
                await db[coll].update_one({"id": doc["id"]}, {"$set": {LINE_FIELD: want}})
        out.append((coll, touched, total))

    # Sample R&D mewarisi lini SPESIFIKASI acuannya (satu rantai pekerjaan = satu
    # lini). Ini WARISAN, bukan tebakan: induknya memang menyimpan lininya.
    spec_line: Dict[str, str] = {}
    async for s in db.md_specs.find({}, {"_id": 0, "id": 1, LINE_FIELD: 1}):
        spec_line[s["id"]] = norm(s.get(LINE_FIELD))
    extra = 0
    async for smp in db.md_samples.find({}, {"_id": 0, "id": 1, LINE_FIELD: 1,
                                             "spec_id": 1, "product_id": 1}):
        if norm(smp.get(LINE_FIELD)) or prod_line.get(smp.get("product_id")):
            continue
        want = spec_line.get(smp.get("spec_id"), "")
        if not want:
            continue
        extra += 1
        if not dry:
            await db.md_samples.update_one({"id": smp["id"]}, {"$set": {LINE_FIELD: want}})
    if extra:
        out = [(c, t + extra if c == "md_samples" else t, n) for c, t, n in out]
    return out
