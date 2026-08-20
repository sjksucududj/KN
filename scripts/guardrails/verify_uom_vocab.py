#!/usr/bin/env python3
"""INV-UOM-02 — kosakata satuan dokumen WAJIB ada di master `uoms` (kode/nama/alias).

KELAS BUG YANG DICEGAH (D1, terukur 2026-08-18 & diverifikasi ulang 2026-08-19)
==============================================================================
Dokumen menyimpan satuan sebagai **kata**: `yard` · `kg` · `meter`. Master `uoms`
menyimpan **kode**: `MTR` · `YRD` · `RLL` · `PCS`. Tak satu pun nilai satuan yang
tersimpan di 16 tempat dokumen cocok dengan satu baris master pun. Akibat nyata:
  * pemilik menambah baris `KG` di master → **tidak ada yang berubah di layar**;
  * pemilih satuan di layar tidak bisa dibangun dari master (harus diketik ulang di
    kode) → daftar satuan di layar & di master boleh berbeda tanpa ada yang tahu;
  * satuan salah ketik (`hasta`, `yrd2`) tersimpan tanpa pernah ditolak, dan
    `uom_service` tidak akan bisa menyelesaikan faktornya → konversi 400 di kemudian
    hari, jauh dari tempat kesalahan dibuat.

ATURAN (DATA — butuh Mongo)
===========================
  A. Setiap nilai satuan yang tersimpan di `uom_service.UNIT_DOC_FIELDS` (16 koleksi ·
     19 field, termasuk `products.base_unit`) WAJIB cocok — huruf besar/kecil diabaikan —
     dengan `code`, `name`, atau salah satu `aliases` sebuah baris `uoms` **aktif**.
  B. Satu kata satuan hanya boleh menunjuk SATU baris master (alias tidak boleh kembar);
     kalau kembar, faktor & pembulatan untuk kata itu jadi tak tentu.
  C. Setiap baris master aktif ber-`base_type="length"`/`"weight"` WAJIB punya
     `factor_to_base > 0` (satuan tanpa faktor = konversi mustahil, senyap).

ATURAN (KODE FE — statik, tidak butuh Mongo)
============================================
  D. **Pemilih satuan di layar DILARANG memakai daftar yang diketik di kode.**
     Ini aturan yang menjawab keluhan pemilik secara langsung: menambah `KG`/`PANEL`
     di Master Data → UOM harus MENGUBAH SESUATU di layar. Terukur sebelum aturan ini
     ada: 6 berkas FE menyimpan daftar satuannya sendiri
     (`utils/uom.js` `new Set([base,"yard","cm","inch"])` · `CategoryManager`
     `BASE_UNIT_OPTIONS` · `IncentiveRatesEditor` `UNITS` · `MakloonFormModal`
     satuan kapasitas · `MakloonOrderDetailPanel` ×2 satuan surat jalan mitra),
     sehingga satuan baru tidak pernah bisa dipilih di POS, kategori produk, tarif
     insentif, maupun penerimaan hasil makloon — dan konsekuensinya senyap: komisi
     sales untuk produk ber-`panel` diam-diam nol karena tarifnya tak bisa dibuat.
     Sumber sah satu-satunya: `useUomConversions()` / `utils/uomCatalog`
     (katalog server = benih `UNIT_CATALOG` **di-overlay** baris master aktif).

Jalankan:
    python scripts/guardrails/verify_uom_vocab.py
    python scripts/guardrails/verify_uom_vocab.py --self-test
"""
import os
import re
import sys
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from _common import (BACKEND, FRONTEND, Guard, B, C, G, R, X,  # noqa: E402
                     strip_comments_and_strings)

sys.path.insert(0, str(BACKEND))

FE_SRC = FRONTEND / "src"

# Satu tempat yang MEMANG berhak menyebut kata satuan sebagai data:
#  · `utils/uomCatalog.js`  — penyimpan katalog (hanya membaca dari server);
#  · `utils/uom.js`         — faktor PRATINJAU (`FIXED_LENGTH_FACTORS`), bukan daftar
#                              pilihan; daftar pilihannya kini dari `uomCatalog`;
#  · `hooks/useUomConversions.js` — pengambil katalog;
#  · `features/admin/uom/*` — layar MASTER satuan itu sendiri.
UNIT_LIST_ALLOWLIST = {
    "utils/uomCatalog.js", "utils/uom.js", "hooks/useUomConversions.js",
}
_ALLOW_PREFIX = ("features/admin/uom/",)

# Pola: ARRAY berisi >=2 objek `{ value: "<kata satuan>" , ... }`. Sengaja menuntut
# DUA agar satu opsi tunggal (mis. `{value:"", label:"Pakai satuan sistem"}` +
# daftar dari katalog) tidak dituduh, dan agar kata satuan yang muncul sebagai
# NILAI TERSIMPAN (bukan daftar pilihan) tidak ikut tertangkap.
_UNIT_TOKENS = (r"meter|metre|yard|yd|kg|kilogram|gram|ton|lbs|roll|rll|pcs|piece|"
                r"panel|bale|cone|box|pack|inch|cm|mm|lembar")
TYPED_UNIT_LIST = re.compile(
    r"\{\s*value\s*:\s*[\"'](?:" + _UNIT_TOKENS + r")[\"']"
    r"[^}]*\}\s*,\s*"
    r"\{\s*value\s*:\s*[\"'](?:" + _UNIT_TOKENS + r")[\"']",
    re.IGNORECASE)
# Pola kedua: himpunan/array kata satuan telanjang (>=3) — bentuk `new Set([...])`
# atau `["meter","yard","kg"]`.
TYPED_UNIT_SET = re.compile(
    r"\[\s*(?:[^\[\]]*?,\s*)?"
    r"[\"'](?:" + _UNIT_TOKENS + r")[\"']\s*,\s*"
    r"[\"'](?:" + _UNIT_TOKENS + r")[\"']\s*,\s*"
    r"[\"'](?:" + _UNIT_TOKENS + r")[\"']",
    re.IGNORECASE)

# ── ANTI TUDUH PALSU: daftar yang MENCAMPUR satuan dengan yang BUKAN satuan ──
# Ditemukan dengan MENJALANKAN aturan D pada kode nyata: dari 13 tuduhan pertama,
# 4 berkas SAH karena daftarnya bukan pemilih *satuan ukur*:
#   · `pettyCashShared.SATUAN_OPTIONS` memuat `hari` & `paket` → satuan BIAYA
#     ("2 hari sewa forklift"); master `uoms` tidak memuat satuan waktu, jadi
#     memaksanya lewat master justru MENGHAPUS pilihan yang sah;
#   · `tariff_basis_default` memuat `pick` (PPI) & `lumpsum` (borongan) → BASIS
#     tarif, bukan satuan barang.
# Aturannya jadi tegas dan bisa diuji: daftar yang SELURUH nilainya kata satuan
# ukur = pemilih satuan (WAJIB dari master); daftar yang mencampur = domain lain.
_NON_UNIT_TOKENS = {
    "", "unit", "hari", "bulan", "tahun", "jam", "paket", "borongan", "lumpsum",
    "pick", "output", "input", "orang", "kali", "titik", "set", "trip", "rit",
}
_VALUE_RE = re.compile(r"\{\s*value\s*:\s*[\"']([^\"']*)[\"']")


def _enclosing_array(src: str, pos: int) -> Tuple[int, str]:
    """Ambil literal array `[ … ]` yang MEMUAT posisi `pos` → (awal, isi)."""
    start = src.rfind("[", 0, pos)
    if start < 0:
        return -1, ""
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "[":
            depth += 1
        elif src[i] == "]":
            depth -= 1
            if depth == 0:
                return start, src[start:i + 1]
    return start, src[start:]


def _is_unit_picker(blok: str) -> bool:
    """True bila SELURUH nilai di dalam array adalah kata satuan ukur."""
    nilai = [v.strip().lower() for v in _VALUE_RE.findall(blok)]
    if len(nilai) < 2:
        return False
    return all(v not in _NON_UNIT_TOKENS for v in nilai)



def _fe_files() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for pola in ("*.jsx", "*.js"):
        for p in FE_SRC.rglob(pola):
            rel = str(p.relative_to(FE_SRC))
            if rel.startswith("components/ui/"):
                continue                  # shadcn — tidak menyentuh domain satuan
            out[rel] = p.read_text(encoding="utf-8", errors="ignore")
    return out


def find_typed_unit_lists(rel: str, src: str) -> List[str]:
    """Aturan D — daftar satuan yang diketik di kode FE (bukan dari master)."""
    if rel in UNIT_LIST_ALLOWLIST or rel.startswith(_ALLOW_PREFIX):
        return []
    # Kata satuannya HIDUP di dalam string, jadi `strip_comments_and_strings` tidak
    # bisa dipakai untuk menilai isinya. Yang boleh dibuang aman hanyalah KOMENTAR —
    # pola yang sama dengan INV-ROLL-01 & INV-UI-09.
    tanpa_komentar = _strip_comments_only(src)
    out: List[str] = []
    dilaporkan: set = set()
    for pola, sebab in ((TYPED_UNIT_LIST, "daftar opsi satuan diketik di kode"),
                        (TYPED_UNIT_SET, "himpunan kata satuan diketik di kode")):
        for m in pola.finditer(tanpa_komentar):
            awal, blok = _enclosing_array(tanpa_komentar, m.start())
            if awal in dilaporkan:
                continue                       # satu array = satu laporan
            if pola is TYPED_UNIT_LIST and not _is_unit_picker(blok):
                continue                       # domain lain (basis tarif / satuan biaya)
            dilaporkan.add(awal)
            line = tanpa_komentar[:m.start()].count("\n") + 1
            out.append(f"{rel} baris {line}: {sebab} — satuan yang ditambah pemilik "
                       f"di Master Data → UOM TIDAK akan muncul di pemilih ini. "
                       f"Pakai `useUomConversions().unitOptions()` atau "
                       f"`uomSelectOptions()` dari `utils/uomCatalog`.")
    return out


def _strip_comments_only(src: str) -> str:
    """Buang komentar `//` & `/* */`, PERTAHANKAN literal string.

    Kata satuan hidup di dalam string (`{ value: "yard" }`), jadi penjaga ini tidak
    bisa memakai `strip_comments_and_strings` apa adanya — pola yang sama sudah
    dipakai INV-ROLL-01 dan INV-UI-09. Panjang dijaga sama supaya nomor baris tepat.
    """
    out: List[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if c == "/" and nxt == "*":
            while i < n and not (src[i] == "*" and i + 1 < n and src[i + 1] == "/"):
                out.append("\n" if src[i] == "\n" else " ")
                i += 1
            out.append("  ")
            i += 2
            continue
        if c in ("'", '"', "`"):
            quote = c
            out.append(c)
            i += 1
            while i < n:
                if src[i] == "\\":
                    out.append(src[i:i + 2])
                    i += 2
                    continue
                out.append(src[i])
                if src[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def check_frontend_unit_lists() -> List[str]:
    viol: List[str] = []
    for rel, src in sorted(_fe_files().items()):
        viol.extend(find_typed_unit_lists(rel, src))
    return viol


def _db():
    if not os.environ.get("MONGO_URL"):
        from dotenv import load_dotenv
        load_dotenv(BACKEND / ".env")
    from pymongo import MongoClient
    cli = MongoClient(os.environ["MONGO_URL"].strip('"'), serverSelectionTimeoutMS=2500)
    db = cli[os.environ.get("DB_NAME", "test_database").strip('"')]
    db.command("ping")
    return db


def _unit_fields() -> Dict[str, List[str]]:
    """Peta koleksi→field satuan diambil dari SSOT backend (bukan salinan di gate)."""
    from services.uom_service import UNIT_DOC_FIELDS
    return UNIT_DOC_FIELDS


def vocab_of(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    """{kata (huruf kecil) → kode master} untuk baris AKTIF."""
    out: Dict[str, str] = {}
    for r in rows:
        if (r.get("status") or "active") != "active":
            continue
        for k in [r.get("code"), r.get("name")] + list(r.get("aliases") or []):
            k = str(k or "").strip().lower()
            if k:
                out.setdefault(k, str(r.get("code") or ""))
    return out


def alias_clashes(rows: List[Dict[str, Any]]) -> List[str]:
    """Aturan B — satu kata dipakai dua baris master aktif."""
    pemilik: Dict[str, List[str]] = {}
    for r in rows:
        if (r.get("status") or "active") != "active":
            continue
        kode = str(r.get("code") or "?")
        for k in [r.get("code"), r.get("name")] + list(r.get("aliases") or []):
            k = str(k or "").strip().lower()
            if k:
                pemilik.setdefault(k, [])
                if kode not in pemilik[k]:
                    pemilik[k].append(kode)
    return [f"kata satuan `{k}` dipakai {len(v)} baris master ({', '.join(v)}) — "
            f"faktor & pembulatan untuk kata itu jadi tak tentu"
            for k, v in sorted(pemilik.items()) if len(v) > 1]


def check_data(db, rows: List[Dict[str, Any]]) -> Tuple[List[str], int, int]:
    """→ (pelanggaran, jumlah nilai satuan diperiksa, jumlah kata unik)."""
    viol: List[str] = []
    vocab = vocab_of(rows)
    diperiksa = 0
    kata: Dict[str, Dict[str, int]] = {}      # kata → {koleksi: jumlah}
    for col, fields in _unit_fields().items():
        for f in fields:
            for v in db[col].distinct(f):
                if v in (None, ""):
                    continue
                w = str(v).strip().lower()
                diperiksa += 1
                n = db[col].count_documents({f: v})
                kata.setdefault(w, {})
                kata[w][f"{col}.{f}"] = kata[w].get(f"{col}.{f}", 0) + n
    for w, tempat in sorted(kata.items()):
        if w in vocab:
            continue
        total = sum(tempat.values())
        rinci = ", ".join(f"{k} ×{v}" for k, v in sorted(tempat.items())[:4])
        viol.append(f"satuan `{w}` dipakai {total} dokumen ({rinci}) tetapi TIDAK ADA di "
                    f"master `uoms` (kode/nama/alias aktif) — pemilih satuan di layar tak "
                    f"menawarkannya & faktornya tak bisa diselesaikan. Tambahkan sebagai "
                    f"alias baris yang tepat lewat Master Data → UOM.")
    viol.extend(alias_clashes(rows))
    for r in rows:                                            # aturan C
        if (r.get("status") or "active") != "active":
            continue
        if str(r.get("base_type") or "").lower() in ("length", "weight"):
            try:
                f = float(r.get("factor_to_base") or 0)
            except (TypeError, ValueError):
                f = 0.0
            if f <= 0:
                viol.append(f"satuan {r.get('code')} ({r.get('base_type')}) tanpa "
                            f"`factor_to_base` > 0 — konversi ke satuan dasar mustahil")
    return viol, diperiksa, len(kata)


def main() -> int:
    g = Guard("INV-UOM-02", "kosakata satuan dokumen ⊆ master `uoms` (kode/nama/alias)")
    # ── Aturan D (statik) — jalan walau Mongo mati; justru di sinilah keluhan
    # pemilik "menambah satuan tidak mengubah apa pun di layar" dijaga.
    fe_viol = check_frontend_unit_lists()
    g.bump(len(_fe_files()))
    for v in fe_viol:
        g.add(v)
    try:
        db = _db()
    except Exception as exc:  # noqa: BLE001
        print(f"  Mongo tak terjangkau ({exc}) — lapis DATA dilewati.")
        return g.finish()
    rows = list(db.uoms.find({}, {"_id": 0}))
    viol, diperiksa, unik = check_data(db, rows)
    aktif = sum(1 for r in rows if (r.get("status") or "active") == "active")
    g.bump(diperiksa + aktif)
    print(f"  master satuan aktif: {aktif} · nilai satuan tersimpan diperiksa: {diperiksa} "
          f"({unik} kata unik) · koleksi dipantau: {len(_unit_fields())} · "
          f"berkas FE diperiksa (aturan D): {len(_fe_files())}")
    for v in viol:
        g.add(v)
    return g.finish()


# ─────────────────────────────────────────────────────────────────────────────
# SELF-TEST — wajib MEMERAH pada pelanggaran buatan (data & master), dan wajib
# TIDAK menuduh keadaan yang sah. Data uji ditulis lalu DIHAPUS (nol residu).
# ─────────────────────────────────────────────────────────────────────────────
def self_test() -> int:
    kasus: List[Tuple[str, bool]] = []

    def cek(nama: str, benar: bool):
        kasus.append((nama, benar))

    ROWS_SAH = [
        {"code": "YRD", "name": "Yard", "base_type": "length", "factor_to_base": 0.9144,
         "aliases": ["yard", "yd"], "status": "active"},
        {"code": "KG", "name": "Kilogram", "base_type": "weight", "factor_to_base": 1.0,
         "aliases": ["kg"], "status": "active"},
    ]
    cek("alias kembar antar baris master → MERAH",
        len(alias_clashes(ROWS_SAH + [{"code": "YARD2", "name": "Yard lain",
                                       "aliases": ["yard"], "status": "active"}])) == 1)
    cek("master sah (tanpa alias kembar) → hijau", alias_clashes(ROWS_SAH) == [])
    cek("baris NONAKTIF tidak dihitung bentrok",
        alias_clashes(ROWS_SAH + [{"code": "OLD", "aliases": ["yard"],
                                   "status": "inactive"}]) == [])
    v = vocab_of(ROWS_SAH)
    cek("kata dokumen `yard` dikenali lewat alias", v.get("yard") == "YRD")
    cek("kode master `YRD` juga dikenali (huruf kecil)", v.get("yrd") == "YRD")
    cek("kata asing `hasta` TIDAK dikenali", "hasta" not in v)

    # ── Lapis DATA: bukti-merah pada basis data SUNGGUHAN (lalu dibersihkan) ──
    try:
        db = _db()
    except Exception as exc:  # noqa: BLE001
        print(f"{R}  Mongo tak terjangkau ({exc}) — lapis DATA self-test dilewati.{X}")
        db = None
    if db is not None:
        rows = list(db.uoms.find({}, {"_id": 0}))
        viol0, _, _ = check_data(db, rows)
        cek(f"kode nyata saat ini HIJAU ({len(viol0)} pelanggaran)", not viol0)
        probe = {"id": "wt_uomvocab_probe", "unit": "hasta", "status": "draft",
                 "type": "inbound", "entity_id": "ent_ksc", "_probe": True}
        db.wms_tasks.insert_one(dict(probe))
        try:
            viol1, _, _ = check_data(db, rows)
            cek("satuan `hasta` disuntik ke wms_tasks → MERAH",
                any("hasta" in x for x in viol1))
            cek("pesannya menyebut JUMLAH dokumen pemakainya",
                any("hasta" in x and "1 dokumen" in x for x in viol1))
        finally:
            db.wms_tasks.delete_one({"id": "wt_uomvocab_probe"})
        viol2, _, _ = check_data(db, rows)
        cek("hijau lagi sesudah data uji dihapus (nol residu)", not viol2)
        cek("tidak ada sisa dokumen uji",
            db.wms_tasks.count_documents({"id": "wt_uomvocab_probe"}) == 0)
        # Aturan C — satuan panjang tanpa faktor
        viol3, _, _ = check_data(db, rows + [{"code": "HASTAX", "name": "Hasta",
                                              "base_type": "length", "factor_to_base": 0,
                                              "aliases": [], "status": "active"}])
        cek("satuan panjang tanpa `factor_to_base` → MERAH",
            any("HASTAX" in x for x in viol3))

    # ── Aturan D (statik) — daftar satuan yang diketik di kode FE ──────────────
    cek("daftar opsi `{value:\"meter\"},{value:\"yard\"}` di layar → MERAH",
        len(find_typed_unit_lists("features/x/Form.jsx",
            'options={[{ value: "meter", label: "Meter" }, '
            '{ value: "yard", label: "Yard" }]}')) == 1)
    cek("himpunan `[\"meter\",\"yard\",\"kg\"]` → MERAH",
        len(find_typed_unit_lists("features/x/Form.jsx",
            'const seen = new Set(["meter", "yard", "kg"]);')) == 1)
    cek("satu array = SATU laporan (tidak dihitung dua kali)",
        len(find_typed_unit_lists("features/x/Form.jsx",
            'options={[{ value: "meter", label: "M" }, { value: "yard", label: "Y" }, '
            '{ value: "kg", label: "K" }]}')) == 1)
    # Anti tuduh palsu — inilah bagian yang membuat aturan D dipercaya. Keempat kasus
    # di bawah ADALAH kode nyata di repo yang versi pertama aturan ini tuduh salah.
    cek("BASIS tarif (`pick`/`lumpsum` ikut) → hijau (bukan pemilih satuan)",
        find_typed_unit_lists("features/x/Cfg.js",
            'options: [{ value: "kg", label: "Per kg" }, { value: "yard", label: "Per yard" }, '
            '{ value: "pick", label: "Per pick" }, { value: "lumpsum", label: "Borongan" }]') == [])
    cek("satuan BIAYA (`hari`/`paket` ikut) → hijau",
        find_typed_unit_lists("features/x/Petty.jsx",
            'export const SATUAN_OPTIONS = [{ value: "roll", label: "Roll" }, '
            '{ value: "yard", label: "Yard" }, { value: "hari", label: "Hari" }, '
            '{ value: "paket", label: "Paket" }]') == [])
    cek("daftar dari katalog (`uomSelectOptions`) → hijau",
        find_typed_unit_lists("features/x/Form.jsx",
            'options={uomSelectOptions({ dimensions: ["length", "weight"] })}') == [])
    cek("kata satuan di KOMENTAR → hijau",
        find_typed_unit_lists("features/x/Form.jsx",
            '// { value: "meter" }, { value: "yard" } — contoh lama\nconst a = 1;') == [])
    cek("satu opsi tunggal (bukan daftar) → hijau",
        find_typed_unit_lists("features/x/Form.jsx",
            'options={[{ value: "", label: "Satuan sistem" }, ...dariKatalog]}') == [])
    cek("berkas ber-izin (`utils/uom.js` faktor pratinjau) → hijau",
        find_typed_unit_lists("utils/uom.js",
            'export const F = { meter: 1, yard: 0.9144 };\n'
            'const x = ["meter", "yard", "kg"];') == [])
    cek("layar MASTER satuan itu sendiri → hijau",
        find_typed_unit_lists("features/admin/uom/UomConversionView.jsx",
            'const a = [{ value: "meter", label: "M" }, { value: "yard", label: "Y" }];') == [])
    cek("kode FE NYATA saat ini HIJAU (aturan D, 0 pelanggaran)",
        check_frontend_unit_lists() == [])

    gagal = sum(0 if ok else 1 for _n, ok in kasus)
    print(f"{C}{B}== SELF-TEST INV-UOM-02 (kosakata satuan) =={X}")
    for nama, ok in kasus:
        print(f"  [{G + 'PASS' + X if ok else R + 'FAIL' + X}] {nama}")
    print(f"{G}  HIJAU — penjaga menangkap satuan asing di data NYATA, alias kembar, "
          f"satuan tanpa faktor, dan daftar satuan yang diketik di layar (aturan D); "
          f"tanpa menuduh baris nonaktif, kata yang sah, basis tarif, maupun satuan "
          f"biaya (hari/paket).{X}"
          if not gagal else f"{R}{B}  SELF-TEST MERAH ({gagal} kasus).{X}")
    return gagal


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(1 if self_test() else 0)
    raise SystemExit(main())
