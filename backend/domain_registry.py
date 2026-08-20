"""KN Fase A — DOMAIN REGISTRY (SSOT enum domain tekstil + state machine `stage`).

Rujukan wajib:
  * `docs/KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md`
      §3 rumus baku · §6 enum registry terpusat · §11 keputusan pemilik (mengikat)
  * `docs/KN_19_PLAN_FASE_A_FONDASI_DOMAIN.md` (keputusan turunan D-19…D-23)

Problem statement yang dijawab: **PS-01** (rantai stage), **PS-02** (woven vs knit),
**PS-03** (GSM sebagai fondasi), **PS-09** (grade terkendali).

Aturan repo yang ditegakkan modul ini:
  * **R1** — data terkendali TIDAK boleh teks bebas; nilai sah HANYA dari modul ini.
  * **R3** — SSOT: satu makna satu tempat.
  * **R7** — enum tidak boleh hardcode di >1 tempat → backend WAJIB impor modul ini,
    frontend WAJIB konsumsi `GET /api/enums`.

DILARANG: menyalin nilai enum ke router/service/komponen FE.
Modul ini bebas-framework (tanpa FastAPI/Mongo) agar bisa diuji terisolasi.
"""
from typing import Any, Dict, List, Optional


class DomainValidationError(ValueError):
    """Pelanggaran aturan domain (dipetakan ke HTTP 400 oleh router)."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]


# ─────────────────────────────────────────────────────────────────────────────
# 1. NILAI ENUM (SSOT)
# ─────────────────────────────────────────────────────────────────────────────

# D-01 (§11) — urutan mutu terbaik → terburuk: A → A1 → A2 → B → BS.
# Perbandingan mutu WAJIB memakai `rank` (bukan alfabet). BS = Barang Sortir.
GRADES: List[Dict[str, Any]] = [
    {"value": "A",  "label": "A — Mutu terbaik",        "rank": 1, "description": "Kualitas utama, tanpa cacat berarti"},
    {"value": "A1", "label": "A1 — Sangat baik",         "rank": 2, "description": "Cacat sangat minor, masih premium"},
    {"value": "A2", "label": "A2 — Baik",                "rank": 3, "description": "Cacat minor tersebar terbatas"},
    {"value": "B",  "label": "B — Cukup",                "rank": 4, "description": "Cacat terlihat; harga di bawah grade A"},
    {"value": "BS", "label": "BS — Barang Sortir",       "rank": 5, "description": "Mutu terendah / hasil sortir (reject)"},
]

# D-21 — `remnant` & `byproduct` masuk enum sejak Fase A.
STAGES: List[Dict[str, Any]] = [
    {"value": "yarn",      "label": "Benang (Yarn)",                       "order": 1, "semi_finished": False,
     "description": "Bahan benang; sudah menentukan tujuan woven/knit (D-02)"},
    {"value": "grey",      "label": "Grey / Greige (Kain Mentah)",         "order": 2, "semi_finished": True,
     "description": "Kain mentah hasil tenun/rajut, belum diproses basah"},
    {"value": "pfd",       "label": "PFD — Prepared for Dyeing",           "order": 3, "semi_finished": True,
     "description": "Sudah pre-treatment, siap dicelup (status milik perusahaan)"},
    {"value": "pfp",       "label": "PFP — Prepared for Printing",         "order": 3, "semi_finished": True,
     "description": "Sudah pre-treatment, siap diprint (status milik perusahaan)"},
    {"value": "finished",  "label": "Finished (Jadi — dyed/printed)",       "order": 4, "semi_finished": False,
     "description": "Kain jadi siap jual"},
    {"value": "remnant",   "label": "Sisa / Perca (Remnant)",              "order": 5, "semi_finished": False,
     "description": "Sisa potongan/ujung roll"},
    {"value": "byproduct", "label": "Hasil Samping (By-product)",          "order": 5, "semi_finished": False,
     "description": "Keluaran samping proses (mis. waste benang)"},
]

# D-02 (§11) — `fabric_type` WAJIB sejak stage `yarn` (agar jelas benang untuk apa).
FABRIC_TYPES: List[Dict[str, Any]] = [
    {"value": "woven", "label": "Woven (Tenun)", "control_uom": "meter",
     "description": "Dikendalikan panjang (meter/yard); konversi berat via GSM × lebar"},
    {"value": "knit",  "label": "Knit (Rajut)",  "control_uom": "kg",
     "description": "Dikendalikan berat (kg); konversi ke meter hanya informasi"},
]

# Nilai `tenun|celup|finishing|printing|lainnya` MEMPERTAHANKAN data lama
# (schemas_makloon.PROCESS_TYPES kini re-export dari sini — R7).
# Baru di Fase A: `rajut` (jalur knit) & `pre_treatment` (D-03).
PROCESS_TYPES: List[Dict[str, Any]] = [
    {"value": "tenun",         "label": "Tenun (Weaving)",           "fabric_type": "woven",
     "description": "Benang → kain grey (woven)"},
    {"value": "rajut",         "label": "Rajut (Knitting)",          "fabric_type": "knit",
     "description": "Benang → kain grey (knit); output dikendalikan kg"},
    {"value": "pre_treatment", "label": "Pre-Treatment (Scouring/Bleaching)", "fabric_type": None,
     "description": "D-03: satu proses; hasil PFD atau PFP tergantung target_use"},
    {"value": "celup",         "label": "Celup (Dyeing)",            "fabric_type": None,
     "description": "PFD → finished (kain berwarna)"},
    {"value": "printing",      "label": "Printing",                  "fabric_type": None,
     "description": "PFP → finished (kain bermotif cetak)"},
    {"value": "finishing",     "label": "Finishing",                 "fabric_type": None,
     "description": "Penyempurnaan kain jadi (tanpa pindah stage)"},
    # FASE T (2026-08-18) — pembuatan KASA/SCREEN untuk printing. Sengaja berdiri
    # sebagai proses tersendiri, bukan bagian `printing`: ia punya MITRA sendiri,
    # TARIF sendiri, dan yang penting **tidak menyentuh kain** (tidak ada susut,
    # tidak ada perubahan tahap). Menggabungkannya ke `printing` akan membuat
    # estimasi output printing menanggung biaya yang bukan miliknya.
    {"value": "screen",        "label": "Screen (pembuatan kasa)",   "fabric_type": None,
     "description": "Membuat kasa/screen untuk printing — TIDAK mengubah kain "
                    "(qty keluar = qty masuk); yang dibayar jasa pembuatannya"},
    {"value": "lainnya",       "label": "Lainnya",                   "fabric_type": None,
     "description": "Proses lain / keluaran sisa & hasil samping"},
]

# D-03 — penentu hasil pre_treatment (PFD vs PFP).
TARGET_USES: List[Dict[str, Any]] = [
    {"value": "dye",   "label": "Untuk dicelup → PFD",  "to_stage": "pfd"},
    {"value": "print", "label": "Untuk diprint → PFP",  "to_stage": "pfp"},
]

# D-06 & D-07 — basis tarif BEBAS dipilih per kontrak/mitra; sistem menyimpan
# tarif asli + basis asli + faktor konversi + ekuivalen satuan dasar (Fase B/D).
TARIFF_BASIS: List[Dict[str, Any]] = [
    {"value": "pick",   "label": "Per pick (PPI × tarif/pick)", "formula": "biaya_per_meter = ppi × tarif"},
    {"value": "kg",     "label": "Per kilogram",               "formula": "biaya = kg × tarif"},
    {"value": "meter",  "label": "Per meter",                  "formula": "biaya = meter × tarif"},
    {"value": "yard",   "label": "Per yard",                   "formula": "biaya = yard × tarif"},
    {"value": "ball",   "label": "Per ball",                   "formula": "biaya = ball × tarif"},
    {"value": "cone",   "label": "Per cone",                   "formula": "biaya = cone × tarif"},
    {"value": "roll",   "label": "Per roll",                   "formula": "biaya = roll × tarif"},
    {"value": "lot",    "label": "Per lot (borongan)",         "formula": "biaya = tarif per lot"},
    # FASE D (D-07) — pemilik: "semua basis didukung, bisa custom; jangan terpaku
    # pada satu variabel karena bisa case by case".
    {"value": "lumpsum", "label": "Borongan / lumpsum",        "formula": "biaya = tarif"},
    {"value": "custom",  "label": "Formula custom (kontrak)",
     "formula": "biaya = f(qty_base, basis_qty, rate, gsm, lebar, ppi, roll_count, colors, repeats)"},
]

# Satuan nomor benang (dipakai field `yarn_count_system` — D-22).
YARN_COUNT_SYSTEMS: List[Dict[str, Any]] = [
    {"value": "Ne",     "label": "Ne (English cotton count)"},
    {"value": "Nm",     "label": "Nm (metric count)"},
    {"value": "Denier", "label": "Denier (filamen)"},
    {"value": "Tex",    "label": "Tex (g/1000 m)"},
]

# Sumber sah perubahan grade (D-23). Dipakai `inventory_rolls.grade_history[].source`.
GRADE_CHANGE_SOURCES: List[Dict[str, Any]] = [
    {"value": "qc_inspection",      "label": "Inspeksi QC (4-point)",          "requires_reason": False},
    {"value": "quarantine_release", "label": "Release karantina retur",        "requires_reason": False},
    {"value": "manager_override",   "label": "Override manager/admin",         "requires_reason": True},
    {"value": "migration",          "label": "Migrasi data (Fase A)",          "requires_reason": False},
]

# ── Enum yang SUDAH disepakati tetapi fieldnya baru dipakai fase berikutnya ──
# Ditandai `planned_phase` agar tidak dianggap "field hantu" (R2).
LIFECYCLES: List[Dict[str, Any]] = [
    {"value": "konsep",     "label": "Konsep (draf R&D)"},
    {"value": "labdip",     "label": "Labdip (kain polos)"},
    {"value": "proofing",   "label": "Proofing (printing)"},
    {"value": "disetujui",  "label": "Disetujui"},
    {"value": "produksi",   "label": "Produksi (boleh dipesan/dijual)"},
    {"value": "dihentikan", "label": "Dihentikan"},
]

LOT_STATUSES: List[Dict[str, Any]] = [
    {"value": "karantina",  "label": "Karantina",              "description": "Baru diterima / menunggu QC"},
    {"value": "released",   "label": "Dirilis (siap pakai)",  "description": "Lolos mutu, boleh dipakai & dijual"},
    {"value": "in_process", "label": "Sedang diproses",        "description": "Sedang di jalur makloon/produksi"},
    {"value": "hold_shade", "label": "Ditahan (beda shade)",   "description": "Warna/shade belum seragam — perlu keputusan"},
    {"value": "rework",     "label": "Rework",                 "description": "Diproses ulang; roll pindah ke lot anak"},
]

# Fase C · D-10 — sumber pembentukan lot (dipakai `inventory_lots.source`).
LOT_SOURCES: List[Dict[str, Any]] = [
    {"value": "receiving",  "label": "Penerimaan barang (GR)",  "description": "1 batch penerimaan = 1 lot (per dye lot)"},
    {"value": "makloon",    "label": "Hasil makloon",           "description": "Output langkah makloon (input lot → output lot)"},
    {"value": "production", "label": "Produksi in-house",       "description": "Hasil perintah kerja (BOM)"},
    {"value": "split",      "label": "Split lot",               "description": "Sebagian roll dipisah menjadi lot anak"},
    {"value": "merge",      "label": "Merge lot",               "description": "Beberapa lot digabung menjadi satu"},
    {"value": "rework",     "label": "Rework / proses ulang",   "description": "Lot anak hasil proses ulang"},
    {"value": "return",     "label": "Retur masuk",             "description": "Barang kembali dari pelanggan"},
    {"value": "transfer",   "label": "Transfer masuk",          "description": "Pindah gudang / antar entitas"},
    {"value": "adjustment", "label": "Penyesuaian stok",        "description": "Opname / koreksi stok"},
    {"value": "migration",  "label": "Migrasi data lama",       "description": "Dibentuk dari string lot lama (jejak disimpan)"},
    {"value": "manual",     "label": "Input manual",            "description": "Dibuat petugas (stok awal/koreksi)"},
]

CLAIM_ACTIONS: List[Dict[str, Any]] = [
    {"value": "potong_bon",     "label": "Potong bon (kurangi tagihan jasa)"},
    {"value": "tagih_ganti",    "label": "Tagih ganti rugi"},
    {"value": "terima_catatan", "label": "Terima dengan catatan"},
]

# FASE D (D-09) — daur hidup klaim selisih makloon.
CLAIM_STATUSES: List[Dict[str, Any]] = [
    {"value": "none",             "label": "Tidak ada klaim"},
    {"value": "open",             "label": "Selisih terbuka (perlu keputusan)"},
    {"value": "pending_approval", "label": "Menunggu persetujuan manajer/admin"},
    {"value": "approved",         "label": "Disetujui & dieksekusi"},
    {"value": "rejected",         "label": "Ditolak"},
]

SAMPLE_TYPES: List[Dict[str, Any]] = [
    {"value": "labdip",      "label": "Labdip (kain polos)"},
    {"value": "proofing",    "label": "Proofing (printing)"},
    {"value": "bulk_sample", "label": "Bulk sample"},
]

# ── FASE L — LINI PRODUK (pembagian kerja MD) ────────────────────────────────
# NILAI BENIH saja. NILAI HIDUP ada di master `product_lines` (bisa ditambah
# pemilik tanpa ubah kode) dan dibaca lewat `services/master_registry.py`.
# Dipakai sebagai cadangan bila koleksi masternya belum ter-seed — supaya
# instalasi baru & tes unit tidak mati.
#
# `fabric_type_required` mengikat INV-LINE-02: lini woven hanya untuk kain woven,
# knit hanya untuk knit; `printing` SENGAJA kosong karena kain print bisa woven
# maupun knit. Lini adalah PEMBAGIAN KERJA — bukan pengganti `fabric_type`
# (fisika kain, SSOT rumus & satuan kendali).
PRODUCT_LINES: List[Dict[str, Any]] = [
    {"value": "woven", "label": "Woven (Tenun)", "fabric_type_required": "woven",
     "measure_unit_default": "yard", "sort": 1,
     "stage_sequence": ["yarn", "tenun", "celup", "inspect"],
     "sample_types_default": ["labdip"],
     "description": "Kain tenun — dikendalikan panjang (yard/meter)"},
    {"value": "knit", "label": "Knit (Rajut)", "fabric_type_required": "knit",
     "measure_unit_default": "kg", "sort": 2,
     "stage_sequence": ["yarn", "rajut", "celup", "inspect"],
     "sample_types_default": ["labdip"],
     "description": "Kain rajut — dikendalikan berat (kg)"},
    {"value": "printing", "label": "Printing", "fabric_type_required": "",
     "measure_unit_default": "yard", "sort": 3,
     "stage_sequence": ["proofing", "pfp", "screen", "printing", "inspect"],
     "sample_types_default": ["proofing"],
     "description": "Kain bermotif cetak — bisa dari woven maupun knit"},
]

# ── FASE T — TAHAPAN PROSES (master `process_stages`) ────────────────────────
# KENAPA ADA DAFTAR KEDUA DI SAMPING `PROCESS_TYPES`
# Pemilik menyebut tahapannya begini: "benang · tenun · rajut · celup · pfp ·
# screen · printing · inspect". Itu MENCAMPUR dua kosakata yang di repo ini
# sengaja dipisah (rencana §7 FASE T titik T.A):
#     STAGES        = keadaan KAIN   (yarn·grey·pfd·pfp·finished·remnant·byproduct)
#     PROCESS_TYPES = jenis PROSES   (tenun·rajut·pre_treatment·celup·printing·
#                                     finishing·screen·lainnya)
# `process_stages` adalah **daftar kerja pemilik** — satu baris per langkah yang
# dipantau papan PO & SPK makloon — dan ia MENUNJUK ke dua kosakata itu, bukan
# menggantinya. Dengan begitu "Sanforize" bisa ditambah besok tanpa programmer,
# sementara rumus & satuan kendali tetap satu sumber.
#
# NILAI DI SINI = BENIH. Nilai HIDUP ada di koleksi `process_stages` (bisa
# ditambah/diubah pemilik) dan dibaca lewat `services/master_registry.py`.
#
# Arti field yang tidak jelas dari namanya:
#   changes_stage=False → langkah TIDAK mengubah kain. Mesin makloon memaksa
#       susut 0, yield 1, dan qty keluar = qty masuk (mis. pembuatan kasa).
#   material_flow       → apakah KAINNYA bergerak:
#       "moves"        = kain dikirim ke mitra lalu kembali (masuk WIP mitra)
#       "service_only" = jasa murni; kain TIDAK bergerak sama sekali
#       "either"       = boleh dua-duanya, dipilih per langkah SPK
#   material_flow_default → dipakai bila langkah tidak memilih (hanya berlaku
#       saat `material_flow="either"`); pilihannya DICATAT di `estimate.explain[]`
#       supaya bukan tebakan diam-diam.
#   needs_vendor=True   → langkah ini dikerjakan mitra; SPK tanpa mitra hanya
#       DIPERINGATKAN (keputusan pemilik 3b), sedangkan gate INV-DOMAIN-06
#       memerah bila tak ada satu pun mitra terdaftar untuk prosesnya.
#   applies_to_lines=[] → berlaku untuk SEMUA lini (aturan "kosong = semua" yang
#       sama dengan `allowed_line_codes` FASE L — jangan diubah jadi wajib-isi).
PROCESS_STAGES: List[Dict[str, Any]] = [
    {"value": "benang", "label": "Benang (bahan masuk)", "code": "benang",
     "name": "Benang (bahan masuk)", "kind": "material", "seq": 10,
     "applies_to_lines": [], "needs_vendor": False, "process_type": "",
     "target_use": "", "changes_stage": True, "from_stage": "", "to_stage": "yarn",
     "tariff_basis_default": "", "material_flow": "", "material_flow_default": "",
     "active": True,
     "notes": "Bahan benang masuk gudang — bukan langkah makloon, tidak ber-SPK."},
    {"value": "tenun", "label": "Tenun (Weaving)", "code": "tenun",
     "name": "Tenun (Weaving)", "kind": "makloon", "seq": 20,
     "applies_to_lines": ["woven"], "needs_vendor": True, "process_type": "tenun",
     "target_use": "", "changes_stage": True, "from_stage": "yarn", "to_stage": "grey",
     "tariff_basis_default": "pick", "material_flow": "moves",
     "material_flow_default": "moves", "active": True,
     "notes": "Benang → kain grey (woven). Output panjang dari kg efektif via GSM × lebar."},
    {"value": "rajut", "label": "Rajut (Knitting)", "code": "rajut",
     "name": "Rajut (Knitting)", "kind": "makloon", "seq": 30,
     "applies_to_lines": ["knit"], "needs_vendor": True, "process_type": "rajut",
     "target_use": "", "changes_stage": True, "from_stage": "yarn", "to_stage": "grey",
     "tariff_basis_default": "kg", "material_flow": "moves",
     "material_flow_default": "moves", "active": True,
     "notes": "Benang → kain grey (knit). Output tetap kg."},
    {"value": "pfp", "label": "PFP — Pre-treatment untuk printing", "code": "pfp",
     "name": "PFP — Pre-treatment untuk printing", "kind": "makloon", "seq": 40,
     "applies_to_lines": ["printing"], "needs_vendor": True,
     "process_type": "pre_treatment", "target_use": "print", "changes_stage": True,
     "from_stage": "grey", "to_stage": "pfp", "tariff_basis_default": "kg",
     "material_flow": "moves", "material_flow_default": "moves", "active": True,
     "notes": "D-03: satu proses pre_treatment; `target_use=print` yang membuat hasilnya PFP."},
    {"value": "pfd", "label": "PFD — Pre-treatment untuk celup", "code": "pfd",
     "name": "PFD — Pre-treatment untuk celup", "kind": "makloon", "seq": 50,
     "applies_to_lines": [], "needs_vendor": True,
     "process_type": "pre_treatment", "target_use": "dye", "changes_stage": True,
     "from_stage": "grey", "to_stage": "pfd", "tariff_basis_default": "kg",
     "material_flow": "moves", "material_flow_default": "moves", "active": True,
     "notes": "D-03: satu proses pre_treatment; `target_use=dye` yang membuat hasilnya PFD."},
    {"value": "celup", "label": "Celup (Dyeing)", "code": "celup",
     "name": "Celup (Dyeing)", "kind": "makloon", "seq": 60,
     "applies_to_lines": [], "needs_vendor": True, "process_type": "celup",
     "target_use": "", "changes_stage": True, "from_stage": "pfd", "to_stage": "finished",
     "tariff_basis_default": "kg", "material_flow": "moves",
     "material_flow_default": "moves", "active": True,
     "notes": "PFD → kain jadi berwarna."},
    {"value": "screen", "label": "Screen (pembuatan kasa)", "code": "screen",
     "name": "Screen (pembuatan kasa)", "kind": "makloon", "seq": 70,
     "applies_to_lines": ["printing"], "needs_vendor": True, "process_type": "screen",
     "target_use": "", "changes_stage": False, "from_stage": "pfp", "to_stage": "pfp",
     "tariff_basis_default": "lumpsum", "material_flow": "either",
     "material_flow_default": "service_only", "active": True,
     "notes": "Membuat kasa/screen untuk printing. TIDAK mengubah kain: qty keluar = "
              "qty masuk, yang dibayar jasa pembuatan kasanya. Umumnya jasa murni "
              "(kain tidak bergerak), tetapi boleh juga kain dikirim bila mitra "
              "menuntut contoh fisik — pilih per langkah di SPK."},
    {"value": "printing", "label": "Printing", "code": "printing",
     "name": "Printing", "kind": "makloon", "seq": 80,
     "applies_to_lines": ["printing"], "needs_vendor": True, "process_type": "printing",
     "target_use": "", "changes_stage": True, "from_stage": "pfp", "to_stage": "finished",
     "tariff_basis_default": "meter", "material_flow": "moves",
     "material_flow_default": "moves", "active": True,
     "notes": "PFP → kain jadi bermotif cetak."},
    {"value": "proofing", "label": "Proofing (sample printing)", "code": "proofing",
     "name": "Proofing (sample printing)", "kind": "sampling", "seq": 90,
     "applies_to_lines": ["printing"], "needs_vendor": True, "process_type": "",
     "target_use": "", "changes_stage": False, "from_stage": "", "to_stage": "",
     "tariff_basis_default": "lumpsum", "material_flow": "service_only",
     "material_flow_default": "service_only", "active": True,
     "notes": "Uji cetak sebelum produksi (FASE F: `md_samples.sample_type=proofing`)."},
    {"value": "inspect", "label": "Inspect (inspeksi mutu)", "code": "inspect",
     "name": "Inspect (inspeksi mutu)", "kind": "inspection", "seq": 100,
     "applies_to_lines": [], "needs_vendor": False, "process_type": "",
     "target_use": "", "changes_stage": False, "from_stage": "", "to_stage": "",
     "tariff_basis_default": "", "material_flow": "", "material_flow_default": "",
     "active": True,
     "notes": "Dikerjakan petugas internal (4-point). Tidak ber-SPK makloon."},
]

# FASE T — jenis tahapan. Menentukan APAKAH tahap itu bisa jadi langkah SPK
# makloon: hanya `makloon` yang boleh. Tanpa pembeda ini, "Inspect" akan muncul
# di pemilih langkah SPK dan membuat jalan buntu (tidak ada mitra, tidak ada tarif).
PROCESS_STAGE_KINDS: List[Dict[str, Any]] = [
    {"value": "material", "label": "Bahan masuk (bukan langkah makloon)",
     "spk_step": False, "description": "Bahan datang lewat pembelian/penerimaan"},
    {"value": "makloon", "label": "Dikerjakan mitra makloon (bisa jadi langkah SPK)",
     "spk_step": True, "description": "Punya mitra, tarif, dan jejak biaya sendiri"},
    {"value": "sampling", "label": "Sampling / proofing",
     "spk_step": True, "description": "Uji sebelum produksi; tidak menambah stok jual"},
    {"value": "inspection", "label": "Inspeksi internal",
     "spk_step": False, "description": "Petugas sendiri — tidak ada tagihan mitra"},
]

# FASE T (keputusan pemilik 1c) — apakah KAIN bergerak pada satu langkah.
MATERIAL_FLOWS: List[Dict[str, Any]] = [
    {"value": "moves", "label": "Kain dikirim & kembali (WIP di mitra)",
     "description": "Bahan keluar gudang ke mitra, lalu kembali sebagai roll baru. "
                    "Biaya jasa masuk HPP kain."},
    {"value": "service_only", "label": "Jasa murni — kain TIDAK bergerak",
     "description": "Tidak ada bahan yang keluar gudang; yang lahir hanya tagihan "
                    "jasa. Biayanya menempel ke langkah kain berikutnya di SPK yang "
                    "sama; bila tidak ada, diakui sebagai beban jasa tak terserap."},
    {"value": "either", "label": "Boleh dua-duanya (dipilih per langkah)",
     "description": "Layar SPK menanyakannya; pilihan dicatat di jejak estimasi."},
]

# FASE E-1 (E1.1) — JENIS BADAN USAHA.
# Pemilik memecah satu perusahaan menjadi beberapa badan usaha karena buku
# keuangan, pajak, harga jual, dan basis pelanggannya berbeda. Jenisnya TIDAK
# menentukan status PKP: `default_tax_mode` sengaja INDEPENDEN (ada CV yang PKP,
# ada PT yang belum PKP). Yang jenis pengaruhi hanyalah bentuk nama legal
# (perorangan = nama pemilik) dan penjelasan di layar.
ENTITY_TYPES: List[Dict[str, Any]] = [
    {"value": "PT", "label": "PT (Perseroan Terbatas)", "legal_person": True,
     "description": "Badan hukum terpisah dari pemiliknya; umum untuk PKP."},
    {"value": "CV", "label": "CV (Persekutuan Komanditer)", "legal_person": True,
     "description": "Persekutuan; boleh PKP maupun non-PKP."},
    {"value": "Perorangan", "label": "Usaha Perorangan", "legal_person": False,
     "description": "Tidak ada badan hukum terpisah — nama legalnya nama pemilik; "
                    "sebutkan juga label usahanya (nama dagang)."},
    {"value": "UD", "label": "UD (Usaha Dagang)", "legal_person": False,
     "description": "Usaha dagang milik perorangan; nama legal = nama pemilik."},
    {"value": "Koperasi", "label": "Koperasi", "legal_person": True,
     "description": "Badan hukum koperasi."},
    {"value": "Yayasan", "label": "Yayasan", "legal_person": True,
     "description": "Badan hukum nirlaba."},
    {"value": "Lainnya", "label": "Lainnya", "legal_person": True,
     "description": "Bentuk lain — isi nama legal persis seperti di dokumen resmi."},
]
ENTITY_TYPE_VALUES = [t["value"] for t in ENTITY_TYPES]
# Jenis tanpa badan hukum terpisah → nama legal dibentuk dari nama pemilik.
PERSONAL_ENTITY_TYPES = {t["value"] for t in ENTITY_TYPES if not t["legal_person"]}


ENUMS: Dict[str, Dict[str, Any]] = {
    "grade": {"label": "Grade Mutu", "ps": "PS-09", "decision": "D-01", "ordered_by": "rank",
              "note": "Urutan terbaik→terburuk memakai rank 1..5 (BS = barang sortir)",
              "values": GRADES, "in_use": True},
    "stage": {"label": "Tahap Bahan (Stage)", "ps": "PS-01", "decision": "D-03/D-21",
              "note": "Transisi dikunci server; lihat GET /api/enums/stage-transitions",
              "values": STAGES, "in_use": True},
    "fabric_type": {"label": "Jenis Kain", "ps": "PS-02", "decision": "D-02",
                    "note": "Wajib sejak stage yarn", "values": FABRIC_TYPES, "in_use": True},
    "process_type": {"label": "Jenis Proses (Makloon)", "ps": "PS-01/PS-04", "decision": "D-03",
                     "values": PROCESS_TYPES, "in_use": True},
    "target_use": {"label": "Tujuan Pre-Treatment", "ps": "PS-01", "decision": "D-03",
                   "values": TARGET_USES, "in_use": True},
    "tariff_basis": {"label": "Basis Tarif Kontrak", "ps": "PS-06/PS-08", "decision": "D-06/D-07",
                     "note": "Bebas dipilih per kontrak/mitra (termasuk formula custom); "
                             "konversi wajib tercatat",
                     "values": TARIFF_BASIS, "in_use": True},
    "yarn_count_system": {"label": "Sistem Nomor Benang", "ps": "PS-03", "decision": "D-22",
                          "values": YARN_COUNT_SYSTEMS, "in_use": True},
    "grade_change_source": {"label": "Sumber Perubahan Grade", "ps": "PS-09", "decision": "D-23",
                            "values": GRADE_CHANGE_SOURCES, "in_use": True},
    # FASE F (2026-07-29) — lifecycle & sample_type AKHIRNYA dipakai nyata:
    # `products.lifecycle` ditulis `services/rnd_spec_service.py` dan DITEGAKKAN
    # `services/rnd_gate.py` (produk belum "produksi" tidak boleh masuk SO/PR/PO).
    "lifecycle": {"label": "Lifecycle Produk", "ps": "PS-12", "decision": "—",
                  "note": "Hanya `produksi` yang boleh dipesan/dijual; lifecycle kosong "
                          "(data sebelum FASE F) diperlakukan sebagai `produksi`",
                  "values": LIFECYCLES, "in_use": True},
    # FASE E-1 (E1.1) — jenis badan usaha; dipakai FE lewat GET /api/enums.
    "entity_type": {"label": "Jenis Badan Usaha", "ps": "FASE E-1", "decision": "E1.1",
                    "note": "Jenis TIDAK menentukan PKP — status PKP diatur terpisah "
                            "lewat mode pajak (`default_tax_mode`)",
                    "values": ENTITY_TYPES, "in_use": True},
    "lot_status": {"label": "Status Lot", "ps": "PS-10", "decision": "D-10",
                   "note": "Informasional (tidak memblokir penjualan) — keputusan pemilik Fase C",
                   "values": LOT_STATUSES, "in_use": True},
    "lot_source": {"label": "Sumber Pembentukan Lot", "ps": "PS-10", "decision": "D-10",
                   "note": "Granularitas per batch penerimaan/proses; 1 lot menaungi banyak roll",
                   "values": LOT_SOURCES, "in_use": True},
    "claim_action": {"label": "Tindakan Klaim Makloon", "ps": "PS-11", "decision": "D-09",
                     "note": "Semua tindakan tersedia; eksekusi WAJIB lewat persetujuan manager/admin",
                     "values": CLAIM_ACTIONS, "in_use": True},
    "claim_status": {"label": "Status Klaim Makloon", "ps": "PS-11", "decision": "D-09",
                     "note": "open → pending_approval → approved|rejected",
                     "values": CLAIM_STATUSES, "in_use": True},
    # FASE L — lini produk. `values` di sini = BENIH; `/api/enums` menimpanya dengan
    # nilai HIDUP dari master `product_lines` (lihat services/master_registry.py),
    # sehingga lini yang baru ditambah pemilik langsung muncul di 12 layar.
    "product_line": {"label": "Lini Produk", "ps": "FASE L", "decision": "L-01",
                     "note": "Pembagian kerja MD (woven/knit/printing, bisa ditambah). "
                             "BUKAN pengganti `fabric_type` — lini = pembagian kerja, "
                             "fabric_type = fisika kain. INV-LINE-02 menjaga keduanya "
                             "tidak saling bertentangan.",
                     "values": PRODUCT_LINES, "in_use": True},
    "sample_type": {"label": "Jenis Sample", "ps": "PS-12", "decision": "—",
                    "note": "FASE F — dipakai `md_samples.sample_type`: labdip (kain polos) "
                            "· proofing (printing, wajib kode desain) · bulk_sample",
                    "values": SAMPLE_TYPES, "in_use": True},
    # ── FASE T — TAHAPAN PROSES. `values` di sini = BENIH; `/api/enums` menimpanya
    # dengan nilai HIDUP dari master `process_stages` (services/master_registry.py),
    # sehingga tahap yang baru ditambah pemilik (mis. "Sanforize") langsung muncul di
    # pemilih langkah SPK & papan PO tanpa ubah kode.
    "process_stage": {"label": "Tahapan Proses", "ps": "FASE T", "decision": "T-01",
                      "note": "Daftar kerja pemilik (benang·tenun·rajut·pfp·pfd·celup·"
                              "screen·printing·proofing·inspect). MENUNJUK ke `stage` "
                              "(keadaan kain) dan `process_type` (jenis proses) — bukan "
                              "menggantinya. `changes_stage=false` = tidak mengubah kain.",
                      "values": PROCESS_STAGES, "in_use": True},
    "process_stage_kind": {"label": "Jenis Tahapan", "ps": "FASE T", "decision": "T-01",
                           "note": "Hanya `makloon`/`sampling` yang boleh jadi langkah SPK; "
                                   "`material` & `inspection` tidak ber-SPK makloon.",
                           "values": PROCESS_STAGE_KINDS, "in_use": True},
    "material_flow": {"label": "Aliran Kain pada Langkah", "ps": "FASE T", "decision": "T-02",
                      "note": "moves = kain dikirim & kembali · service_only = jasa murni "
                              "(kain tidak bergerak) · either = dipilih per langkah SPK",
                      "values": MATERIAL_FLOWS, "in_use": True},
}


# ─────────────────────────────────────────────────────────────────────────────
# 2. STATE MACHINE STAGE (PS-01) — transisi dikunci server
# ─────────────────────────────────────────────────────────────────────────────
# Kolom `fabric_type` = pembatas (None = berlaku untuk woven & knit).
# Kolom `target_use`  = pembeda hasil pre_treatment (D-03).
STAGE_TRANSITIONS: List[Dict[str, Any]] = [
    {"from_stage": "yarn", "process_type": "tenun", "target_use": None, "fabric_type": "woven",
     "to_stage": "grey", "label": "Tenun: benang → kain grey (woven)",
     "output_control_uom": "meter",
     "note": "Output panjang dihitung dari kg efektif via GSM × lebar (KN_18 §3.3-2)"},
    {"from_stage": "yarn", "process_type": "rajut", "target_use": None, "fabric_type": "knit",
     "to_stage": "grey", "label": "Rajut: benang → kain grey (knit)",
     "output_control_uom": "kg",
     "note": "Output tetap kg = kg benang × (1 − susut%) (KN_18 §3.3-3)"},
    {"from_stage": "grey", "process_type": "pre_treatment", "target_use": "dye", "fabric_type": None,
     "to_stage": "pfd", "label": "Pre-treatment (tujuan celup): grey → PFD",
     "output_control_uom": None, "note": "D-03: satu proses pre_treatment"},
    {"from_stage": "grey", "process_type": "pre_treatment", "target_use": "print", "fabric_type": None,
     "to_stage": "pfp", "label": "Pre-treatment (tujuan printing): grey → PFP",
     "output_control_uom": None, "note": "D-03: satu proses pre_treatment"},
    {"from_stage": "pfd", "process_type": "celup", "target_use": None, "fabric_type": None,
     "to_stage": "finished", "label": "Celup: PFD → kain jadi",
     "output_control_uom": None, "note": "Basis tarif bebas per kontrak (D-06/D-07)"},
    {"from_stage": "pfp", "process_type": "printing", "target_use": None, "fabric_type": None,
     "to_stage": "finished", "label": "Printing: PFP → kain jadi",
     "output_control_uom": None, "note": "Basis tarif bebas per kontrak (D-06/D-07)"},
    # FASE T — Screen: kain TETAP di tahap PFP. Transisi ini ada supaya papan &
    # validator tidak menolak langkah yang sah, bukan karena kainnya berubah.
    {"from_stage": "pfp", "process_type": "screen", "target_use": None, "fabric_type": None,
     "to_stage": "pfp", "label": "Screen: pembuatan kasa (kain tetap PFP)",
     "output_control_uom": None,
     "note": "FASE T — tidak mengubah kain; qty keluar = qty masuk, biaya = jasa screen"},
    # FASE T (keputusan pemilik 2b) — RE-SCREEN kain jadi. Kasa dibuat ulang untuk
    # motif yang sudah pernah dicetak (perbaikan motif / order ulang). Sama seperti
    # baris di atas: kainnya TIDAK berubah, hanya jasa kasanya yang dibayar.
    {"from_stage": "finished", "process_type": "screen", "target_use": None, "fabric_type": None,
     "to_stage": "finished", "label": "Screen ulang: pembuatan kasa (kain tetap jadi)",
     "output_control_uom": None,
     "note": "FASE T — re-screen; qty keluar = qty masuk, biaya = jasa screen"},
    {"from_stage": "finished", "process_type": "finishing", "target_use": None, "fabric_type": None,
     "to_stage": "finished", "label": "Finishing: kain jadi → kain jadi (tanpa pindah stage)",
     "output_control_uom": None, "note": "Stage tidak berubah"},
    # Keluaran sisa & hasil samping (D-21)
    {"from_stage": "grey", "process_type": "lainnya", "target_use": None, "fabric_type": None,
     "to_stage": "remnant", "label": "Sisa potongan dari kain grey", "output_control_uom": None, "note": ""},
    {"from_stage": "pfd", "process_type": "lainnya", "target_use": None, "fabric_type": None,
     "to_stage": "remnant", "label": "Sisa potongan dari PFD", "output_control_uom": None, "note": ""},
    {"from_stage": "pfp", "process_type": "lainnya", "target_use": None, "fabric_type": None,
     "to_stage": "remnant", "label": "Sisa potongan dari PFP", "output_control_uom": None, "note": ""},
    {"from_stage": "finished", "process_type": "lainnya", "target_use": None, "fabric_type": None,
     "to_stage": "remnant", "label": "Sisa potongan dari kain jadi", "output_control_uom": None, "note": ""},
    {"from_stage": "yarn", "process_type": "lainnya", "target_use": None, "fabric_type": None,
     "to_stage": "byproduct", "label": "Hasil samping / waste benang", "output_control_uom": None, "note": ""},
    {"from_stage": "grey", "process_type": "lainnya", "target_use": None, "fabric_type": None,
     "to_stage": "byproduct", "label": "Hasil samping dari proses kain grey", "output_control_uom": None, "note": ""},
]


# ─────────────────────────────────────────────────────────────────────────────
# 3. MATRIKS KELENGKAPAN FIELD PER STAGE (PS-02 · PS-03 · D-02 · D-22)
# ─────────────────────────────────────────────────────────────────────────────
# D-22: GSM (gramasi) + lebar wajib mulai stage `grey`; stage `yarn` wajib
#       `yarn_count`; `fabric_type` wajib sejak `yarn` (D-02).
#       Untuk `knit` field terukur TIDAK memblokir (peringatan saja) karena knit
#       dikendalikan kg — lihat KNIT_RELAXED_FIELDS.
STAGE_FIELD_RULES: Dict[str, Dict[str, List[str]]] = {
    "yarn":      {"required": ["fabric_type", "yarn_count"], "recommended": []},
    "grey":      {"required": ["fabric_type", "gramasi", "lebar"], "recommended": []},
    "pfd":       {"required": ["fabric_type", "gramasi", "lebar"], "recommended": []},
    "pfp":       {"required": ["fabric_type", "gramasi", "lebar"], "recommended": []},
    "finished":  {"required": ["fabric_type", "gramasi", "lebar"], "recommended": []},
    "remnant":   {"required": ["fabric_type"], "recommended": ["gramasi", "lebar"]},
    "byproduct": {"required": [], "recommended": ["fabric_type", "gramasi", "lebar"]},
}

# D-22 — knit: field terukur turun status menjadi "disarankan" (non-blocking).
KNIT_RELAXED_FIELDS = {"gramasi", "lebar", "yarn_count"}

FIELD_LABELS: Dict[str, str] = {
    "fabric_type": "Jenis kain (woven/knit)",
    "gramasi": "Gramasi/GSM (gram per m²)",
    "lebar": "Lebar kain (meter)",
    "yarn_count": "Nomor benang (yarn count)",
    "grade": "Grade mutu",
    "stage": "Tahap bahan (stage)",
}

NUMERIC_DOMAIN_FIELDS = {"gramasi", "lebar"}

# Field domain Fase A pada koleksi `products` (dipakai allowed-list PATCH).
PRODUCT_DOMAIN_FIELDS = [
    "stage", "fabric_type", "grade", "gramasi", "lebar",
    "yarn_count", "yarn_count_system",
]


# ─────────────────────────────────────────────────────────────────────────────
# 4. AKSES ENUM
# ─────────────────────────────────────────────────────────────────────────────

def enum_names() -> List[str]:
    return list(ENUMS.keys())


def enum_meta(name: str) -> Dict[str, Any]:
    if name not in ENUMS:
        raise DomainValidationError(
            f"Enum '{name}' tidak dikenal. Pilihan: {', '.join(enum_names())}")
    meta = dict(ENUMS[name])
    meta["name"] = name
    return meta


def enum_items(name: str) -> List[Dict[str, Any]]:
    return list(enum_meta(name)["values"])


def values_of(name: str) -> List[str]:
    """Daftar nilai (string) sebuah enum — dipakai schema/validator backend."""
    return [v["value"] for v in enum_items(name)]


def is_valid(name: str, value: Any) -> bool:
    return str(value or "") in values_of(name)


def label_of(name: str, value: Any) -> str:
    for item in enum_items(name):
        if item["value"] == value:
            return item["label"]
    return str(value or "")


def grade_rank(value: Any) -> Optional[int]:
    """Rank mutu (1 = terbaik). None bila grade tidak dikenal (D-01)."""
    for item in GRADES:
        if item["value"] == str(value or "").strip().upper():
            return int(item["rank"])
    return None


def compare_grade(a: Any, b: Any) -> Optional[int]:
    """-1 bila `a` lebih baik dari `b`, 0 sama, 1 bila lebih buruk. None bila tak dikenal."""
    ra, rb = grade_rank(a), grade_rank(b)
    if ra is None or rb is None:
        return None
    return (ra > rb) - (ra < rb)


def stage_order(value: Any) -> Optional[int]:
    for item in STAGES:
        if item["value"] == str(value or "").strip().lower():
            return int(item["order"])
    return None


# ── Normalisasi (dipakai migrasi & endpoint) ────────────────────────────────
GRADE_LEGACY_MAP: Dict[str, str] = {
    "C": "BS",        # grade lama hasil QC 4-point (A/B/C) → C = mutu terendah
    "D": "BS",
    "SORTIR": "BS",
    "REJECT": "BS",
    "BS1": "BS",
    "A+": "A",
    "AA": "A",
    "A 1": "A1",
    "A 2": "A2",
}


def normalize_grade(raw: Any) -> Dict[str, Any]:
    """Normalisasi grade lama → enum resmi.

    Return `{"value": <grade|None>, "legacy": <nilai asli bila diubah/None>, "mapped": bool}`.
    """
    text = str(raw or "").strip().upper().replace("GRADE", "").strip()
    if not text:
        return {"value": None, "legacy": None, "mapped": False}
    if text in values_of("grade"):
        return {"value": text, "legacy": None, "mapped": False}
    if text in GRADE_LEGACY_MAP:
        return {"value": GRADE_LEGACY_MAP[text], "legacy": str(raw), "mapped": True}
    return {"value": None, "legacy": str(raw), "mapped": False}


def normalize_stage(raw: Any) -> Optional[str]:
    text = str(raw or "").strip().lower().replace(" ", "_")
    aliases = {"greige": "grey", "gray": "grey", "benang": "yarn", "jadi": "finished",
               "pfd_": "pfd", "pfp_": "pfp", "sisa": "remnant"}
    text = aliases.get(text, text)
    return text if text in values_of("stage") else None


def normalize_fabric_type(raw: Any) -> Optional[str]:
    text = str(raw or "").strip().lower()
    aliases = {"tenun": "woven", "rajut": "knit", "knitting": "knit", "weaving": "woven",
               "knitted": "knit", "woven_fabric": "woven"}
    text = aliases.get(text, text)
    return text if text in values_of("fabric_type") else None


# ─────────────────────────────────────────────────────────────────────────────
# 5. TRANSISI STAGE — resolver & matriks
# ─────────────────────────────────────────────────────────────────────────────

def transitions(from_stage: Optional[str] = None,
                process_type: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = STAGE_TRANSITIONS
    if from_stage:
        rows = [r for r in rows if r["from_stage"] == from_stage]
    if process_type:
        rows = [r for r in rows if r["process_type"] == process_type]
    return list(rows)


def transition_matrix() -> List[Dict[str, Any]]:
    """Matriks siap-tampil untuk FE: baris = stage asal, kolom = proses."""
    out = []
    for stage in STAGES:
        row = {"from_stage": stage["value"], "from_label": stage["label"], "cells": []}
        for proc in PROCESS_TYPES:
            targets = [
                {"to_stage": t["to_stage"], "target_use": t["target_use"],
                 "fabric_type": t["fabric_type"], "label": t["label"]}
                for t in STAGE_TRANSITIONS
                if t["from_stage"] == stage["value"] and t["process_type"] == proc["value"]
            ]
            row["cells"].append({"process_type": proc["value"], "process_label": proc["label"],
                                 "targets": targets, "allowed": bool(targets)})
        out.append(row)
    return out


def resolve_transition(from_stage: Any, process_type: Any, target_use: Any = None,
                       fabric_type: Any = None, to_stage: Any = None) -> Dict[str, Any]:
    """Validasi & resolusi transisi stage (PS-01).

    Mengembalikan `{"ok": True, "to_stage": ..., "transition": {...}}`.
    Melempar `DomainValidationError` (pesan Indonesia) bila transisi ilegal/ambigu.
    """
    fs = normalize_stage(from_stage)
    if fs is None:
        raise DomainValidationError(
            f"Stage asal '{from_stage}' tidak dikenal. Pilihan: {', '.join(values_of('stage'))}")
    pt = str(process_type or "").strip().lower()
    if pt not in values_of("process_type"):
        raise DomainValidationError(
            f"Jenis proses '{process_type}' tidak dikenal. "
            f"Pilihan: {', '.join(values_of('process_type'))}")

    ft = normalize_fabric_type(fabric_type) if fabric_type else None
    tu = str(target_use or "").strip().lower() or None
    if tu and tu not in values_of("target_use"):
        raise DomainValidationError(
            f"Tujuan proses '{target_use}' tidak dikenal. "
            f"Pilihan: {', '.join(values_of('target_use'))}")

    cands = transitions(fs, pt)
    if not cands:
        allowed = sorted({f"{r['process_type']} → {r['to_stage']}" for r in transitions(fs)})
        raise DomainValidationError(
            f"Transisi tidak sah: stage '{fs}' tidak bisa diproses '{pt}'. "
            + (f"Transisi sah dari '{fs}': {', '.join(allowed)}."
               if allowed else f"Stage '{fs}' adalah tahap akhir (tidak ada proses lanjutan)."))

    if ft:
        by_fabric = [r for r in cands if r["fabric_type"] in (None, ft)]
        if not by_fabric:
            need = sorted({str(r["fabric_type"]) for r in cands if r["fabric_type"]})
            raise DomainValidationError(
                f"Proses '{pt}' tidak berlaku untuk jenis kain '{ft}'. "
                f"Proses ini hanya untuk: {', '.join(need)}.")
        cands = by_fabric

    if tu:
        by_use = [r for r in cands if r["target_use"] in (None, tu)]
        if not by_use:
            raise DomainValidationError(
                f"Tujuan '{tu}' tidak berlaku untuk proses '{pt}' dari stage '{fs}'.")
        cands = by_use

    ts = normalize_stage(to_stage) if to_stage else None
    if ts:
        by_target = [r for r in cands if r["to_stage"] == ts]
        if not by_target:
            opts = sorted({r["to_stage"] for r in cands})
            raise DomainValidationError(
                f"Stage tujuan '{ts}' tidak sah untuk '{fs}' + proses '{pt}'. "
                f"Stage tujuan yang sah: {', '.join(opts)}.")
        cands = by_target

    unique_targets = sorted({r["to_stage"] for r in cands})
    if len(unique_targets) > 1:
        hint = ""
        if pt == "pre_treatment":
            hint = (" Tentukan `target_use`: 'dye' (→ pfd) atau 'print' (→ pfp) "
                    "sesuai keputusan D-03.")
        raise DomainValidationError(
            f"Transisi ambigu: '{fs}' + proses '{pt}' bisa menghasilkan "
            f"{', '.join(unique_targets)}.{hint}")

    chosen = cands[0]
    return {"ok": True, "from_stage": fs, "process_type": pt, "to_stage": chosen["to_stage"],
            "target_use": chosen["target_use"] or tu, "fabric_type": chosen["fabric_type"] or ft,
            "transition": chosen,
            "message": f"Transisi sah: {chosen['label']}"}


def check_transition(from_stage: Any, process_type: Any, target_use: Any = None,
                     fabric_type: Any = None, to_stage: Any = None) -> Dict[str, Any]:
    """Versi non-raise dari `resolve_transition` (untuk pratinjau UI)."""
    try:
        return resolve_transition(from_stage, process_type, target_use, fabric_type, to_stage)
    except DomainValidationError as exc:
        return {"ok": False, "from_stage": from_stage, "process_type": process_type,
                "to_stage": None, "message": exc.message,
                "allowed_from_stage": transitions(normalize_stage(from_stage) or "")}


# ─────────────────────────────────────────────────────────────────────────────
# 6. VALIDASI DOMAIN PRODUK (PS-01 · PS-02 · PS-03 · PS-09)
# ─────────────────────────────────────────────────────────────────────────────

def field_rules(stage: Any, fabric_type: Any = None) -> Dict[str, List[str]]:
    """Kelengkapan field wajib/disarankan untuk kombinasi (stage × fabric_type)."""
    st = normalize_stage(stage) or "finished"
    ft = normalize_fabric_type(fabric_type)
    base = STAGE_FIELD_RULES.get(st, {"required": [], "recommended": []})
    required = list(base.get("required", []))
    recommended = list(base.get("recommended", []))
    if ft == "knit":  # D-22 — knit: field terukur tidak memblokir
        relaxed = [f for f in required if f in KNIT_RELAXED_FIELDS]
        required = [f for f in required if f not in KNIT_RELAXED_FIELDS]
        recommended = recommended + relaxed
    return {"stage": st, "fabric_type": ft, "required": required,
            "recommended": sorted(set(recommended))}


def _has_value(doc: Dict[str, Any], field: str) -> bool:
    val = doc.get(field)
    if field in NUMERIC_DOMAIN_FIELDS:
        try:
            return float(val or 0) > 0
        except (TypeError, ValueError):
            return False
    return bool(str(val or "").strip())


def validate_product(doc: Dict[str, Any], existing: Optional[Dict[str, Any]] = None
                     ) -> Dict[str, Any]:
    """Validasi domain produk tekstil.

    `doc`      = payload (create) atau patch (update)
    `existing` = dokumen lama (untuk PATCH parsial — nilai yang tidak dikirim dipakai ulang)

    Return: `{errors[], warnings[], needs_review, needs_review_reasons[], rules{}, resolved{}}`
    """
    merged: Dict[str, Any] = dict(existing or {})
    merged.update({k: v for k, v in (doc or {}).items() if v is not None})

    errors: List[str] = []
    warnings: List[str] = []

    raw_stage = merged.get("stage", "finished")
    stage = normalize_stage(raw_stage)
    if stage is None:
        errors.append(
            f"Tahap bahan (stage) '{raw_stage}' tidak dikenal. "
            f"Pilihan sah: {', '.join(values_of('stage'))}.")
        stage = "finished"

    raw_fabric = merged.get("fabric_type", "")
    fabric = normalize_fabric_type(raw_fabric)
    if str(raw_fabric or "").strip() and fabric is None:
        errors.append(
            f"Jenis kain (fabric_type) '{raw_fabric}' tidak dikenal. "
            f"Pilihan sah: {', '.join(values_of('fabric_type'))}.")

    raw_grade = merged.get("grade", "")
    if str(raw_grade or "").strip():
        norm = normalize_grade(raw_grade)
        if norm["value"] is None:
            errors.append(
                f"Grade '{raw_grade}' tidak dikenal. Pilihan sah (terbaik→terburuk): "
                f"{', '.join(values_of('grade'))}.")
        elif norm["mapped"]:
            warnings.append(
                f"Grade '{raw_grade}' dinormalisasi menjadi '{norm['value']}' (D-01).")

    raw_ycs = merged.get("yarn_count_system", "")
    if str(raw_ycs or "").strip() and not is_valid("yarn_count_system", raw_ycs):
        errors.append(
            f"Sistem nomor benang '{raw_ycs}' tidak dikenal. "
            f"Pilihan sah: {', '.join(values_of('yarn_count_system'))}.")

    rules = field_rules(stage, fabric)
    stage_label = label_of("stage", stage)

    for field in rules["required"]:
        if not _has_value(merged, field):
            errors.append(
                f"{FIELD_LABELS.get(field, field)} wajib diisi untuk stage "
                f"'{stage_label}'" + (f" (jenis kain {fabric})" if fabric else "") + ".")

    reasons: List[str] = []
    for field in rules["recommended"]:
        if not _has_value(merged, field):
            msg = (f"{FIELD_LABELS.get(field, field)} sebaiknya diisi untuk stage "
                   f"'{stage_label}'" + (f" (jenis kain {fabric})" if fabric else "") + ".")
            warnings.append(msg)
            reasons.append(field)

    return {
        "errors": errors,
        "warnings": warnings,
        "needs_review": bool(reasons),
        "needs_review_reasons": reasons,
        "rules": rules,
        "resolved": {"stage": stage, "fabric_type": fabric,
                     "grade": normalize_grade(merged.get("grade"))["value"]},
    }


def assert_product_valid(doc: Dict[str, Any], existing: Optional[Dict[str, Any]] = None
                         ) -> Dict[str, Any]:
    """Seperti `validate_product` tetapi melempar `DomainValidationError` bila ada error."""
    res = validate_product(doc, existing)
    if res["errors"]:
        raise DomainValidationError(" ".join(res["errors"]), res["errors"])
    return res


def apply_normalization(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalisasi in-place nilai field domain (stage/fabric_type/grade) pada dict.

    Dipakai router & migrasi supaya penyimpanan SELALU memakai nilai enum resmi
    (mis. "Woven" -> "woven", "c" -> "BS"). Field yang tidak ada dibiarkan.
    """
    if "stage" in doc and str(doc.get("stage") or "").strip():
        norm = normalize_stage(doc["stage"])
        if norm:
            doc["stage"] = norm
    if "fabric_type" in doc and str(doc.get("fabric_type") or "").strip():
        norm = normalize_fabric_type(doc["fabric_type"])
        if norm:
            doc["fabric_type"] = norm
    if "grade" in doc and str(doc.get("grade") or "").strip():
        g = normalize_grade(doc["grade"])
        if g["value"]:
            doc["grade"] = g["value"]
    if "yarn_count_system" in doc and str(doc.get("yarn_count_system") or "").strip():
        raw = str(doc["yarn_count_system"]).strip()
        for item in YARN_COUNT_SYSTEMS:
            if item["value"].lower() == raw.lower():
                doc["yarn_count_system"] = item["value"]
                break
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# 7. JALUR NON-FORM (seed · import CSV · MTO · makloon) — SSOT R3
# ─────────────────────────────────────────────────────────────────────────────
# Masalah nyata yang ditutup di sini: produk dapat lahir dari jalur SELAIN form
# admin (seeder, import CSV/XLSX, SKU custom dari special order, output makloon).
# Bila jalur itu tidak melewati registry, produk cacat domain akan lolos dan
# invarian INV-DOMAIN-02/04/05 gagal. Semua jalur non-form WAJIB memakai
# `stamp_domain_defaults()` (produk) dan `roll_domain_snapshot()` (roll).

# (gramasi gram/m², lebar meter) — nilai wajar per kategori untuk data DEMO/seed.
DEFAULT_GSM_BY_CATEGORY: Dict[str, Any] = {
    "Batik": (120.0, 1.15), "Tenun": (210.0, 1.20), "Lurik": (170.0, 1.10),
    "Songket": (280.0, 1.05), "Ulos": (230.0, 0.90), "Jumputan": (150.0, 1.15),
    "Endek": (195.0, 1.15), "Denim": (340.0, 1.50), "Grey": (120.0, 1.15),
    "Kombinasi": (135.0, 1.15),
}
DEFAULT_GSM_FALLBACK = (180.0, 1.15)

# Kategori yang berarti stage `yarn` (benang) bila stage tidak dinyatakan.
YARN_CATEGORIES = {"benang", "yarn"}
DEFAULT_YARN_COUNT = "30s"
DEFAULT_FABRIC_TYPE = "woven"          # D-20 — default aman untuk data lama/turunan


def default_stage_for_category(category: Any) -> str:
    """Stage default bila dokumen non-form tidak menyatakan stage."""
    return "yarn" if str(category or "").strip().lower() in YARN_CATEGORIES else "finished"


def stamp_domain_defaults(doc: Dict[str, Any], *, strict: bool = False,
                          fill_measurements: bool = False,
                          source: str = "system") -> Dict[str, Any]:
    """Lengkapi + normalisasi field domain produk pada jalur NON-form (in-place).

    * `strict=True`      → melempar `DomainValidationError` bila masih cacat
      (dipakai seeder: data demo tidak boleh lahir cacat).
    * `fill_measurements=True` → GSM/lebar diisi nilai wajar per kategori
      (HANYA untuk data demo/seed; jalur produksi tidak boleh mengarang ukuran).
    * `source`           → jejak asal pengisian default (`fabric_type_source`).

    Selalu menegakkan INV-DOMAIN-04: bila masih ada kekurangan WAJIB, dokumen
    ditandai `needs_review=True` + `domain_gaps[]` (bukan diam-diam lolos).
    """
    if not str(doc.get("stage") or "").strip():
        doc["stage"] = default_stage_for_category(doc.get("category"))
    if not str(doc.get("fabric_type") or "").strip():
        doc["fabric_type"] = DEFAULT_FABRIC_TYPE
        doc["fabric_type_source"] = source          # D-20 — jejak nilai bukan input user
    apply_normalization(doc)

    stage = normalize_stage(doc.get("stage")) or "finished"
    if stage == "yarn":
        if fill_measurements and not str(doc.get("yarn_count") or "").strip():
            doc["yarn_count"] = DEFAULT_YARN_COUNT
            doc.setdefault("yarn_count_system", "Ne")
    elif fill_measurements and stage in ("grey", "pfd", "pfp", "finished"):
        gsm, width = DEFAULT_GSM_BY_CATEGORY.get(
            str(doc.get("category") or ""), DEFAULT_GSM_FALLBACK)
        try:
            if float(doc.get("gramasi") or 0) <= 0:
                doc["gramasi"] = gsm
        except (TypeError, ValueError):
            doc["gramasi"] = gsm
        try:
            if float(doc.get("lebar") or 0) <= 0:
                doc["lebar"] = width
        except (TypeError, ValueError):
            doc["lebar"] = width

    check = validate_product(doc)
    doc["needs_review"] = bool(check["needs_review"] or check["errors"])
    doc["needs_review_reasons"] = check["needs_review_reasons"]
    if check["errors"]:
        doc["domain_gaps"] = check["errors"]
        if strict:
            raise DomainValidationError(
                f"Produk {doc.get('sku') or doc.get('code') or doc.get('id')} melanggar "
                f"domain Fase A: " + " ".join(check["errors"]), check["errors"])
    else:
        doc.pop("domain_gaps", None)
    return doc


def stamp_many(docs: List[Dict[str, Any]], **kwargs: Any) -> List[Dict[str, Any]]:
    """`stamp_domain_defaults` untuk banyak dokumen (dipakai seeder/import)."""
    for d in docs:
        stamp_domain_defaults(d, **kwargs)
    return docs


def roll_domain_snapshot(prod: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Snapshot domain (stage & fabric_type) produk untuk disimpan di roll.

    PS-02 / INV-DOMAIN-05: setiap roll WAJIB membawa snapshot agar riwayat tidak
    berubah saat master produk diedit. Bila master belum lengkap, dipakai default
    aman (`finished`/`woven`) + jejak `domain_snapshot_source="default"`.

    FASE L — `line_code` (pembagian kerja MD) ikut di snapshot yang SAMA. Sengaja
    di sini dan bukan di tiap pemanggil: pintu ini sudah dipakai `roll_service`,
    `lot_service`, dan `return_service`, jadi satu tambahan menutup tiga jalur
    sekaligus. Berbeda dari `fabric_type`, lini **tidak diberi nilai bawaan** —
    kosong berarti "belum bergolong lini" dan roll itu WAJIB tetap terlihat semua
    akun (kalau ditebak, papan lini akan berisi kain yang bukan urusannya).
    """
    prod = prod or {}
    stage = normalize_stage(prod.get("stage"))
    fabric = normalize_fabric_type(prod.get("fabric_type"))
    snap: Dict[str, Any] = {
        "stage": stage or "finished",
        "fabric_type": fabric or DEFAULT_FABRIC_TYPE,
        "line_code": str(prod.get("line_code") or "").strip().lower(),
    }
    if not stage or not fabric:
        snap["domain_snapshot_source"] = "default"
    return snap


def registry_snapshot() -> Dict[str, Any]:
    """Payload lengkap registry untuk FE (satu panggilan — R7)."""
    return {
        "enums": {name: enum_meta(name) for name in enum_names()},
        "stage_transitions": STAGE_TRANSITIONS,
        "stage_field_rules": STAGE_FIELD_RULES,
        "knit_relaxed_fields": sorted(KNIT_RELAXED_FIELDS),
        "field_labels": FIELD_LABELS,
        "decisions": {
            "D-01": "Urutan grade A → A1 → A2 → B → BS (rank 1..5); BS = barang sortir",
            "D-02": "fabric_type wajib sejak stage yarn",
            "D-03": "Satu proses pre_treatment → PFD (target_use=dye) atau PFP (target_use=print)",
            "D-06/D-07": "Basis tarif bebas per kontrak/mitra + wajib jejak konversi",
            "D-10": "Lot LOT-YYMM-#### per batch penerimaan/proses",
            "D-26": "Nomor lot per entitas (KSC/LOT-YYMM-####) — konsisten SO/PO",
            "D-27": "Penegakan lot configurable: warn (default) / block, tanpa deploy",
            "D-19": "PO wajib memilih grade (tanpa default)",
            "D-20": "Migrasi produk lama: fabric_type default woven",
            "D-21": "Stage remnant & byproduct aktif sejak Fase A",
            "D-22": "GSM+lebar wajib ≥ grey; yarn wajib yarn_count; knit tidak memblokir",
            "D-23": "Grade berubah via inspeksi QC atau override manager/admin beralasan",
        },
    }
