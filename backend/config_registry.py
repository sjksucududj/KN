"""FASE G-0 — CONFIG REGISTRY: **sumber kebenaran tunggal** untuk semua aturan configurable.

Masalah yang diselesaikan (audit 2026-07-26, `scripts/audit_config_wiring.py`):
- 105 kunci konfigurasi tersebar di `config_service.DEFAULT_GLOBAL_SETTINGS` + 5 dokumen
  scope lain di `system_settings`, **tanpa** deskripsi, tanpa batas nilai, tanpa referensi
  kode konsumen, dan tanpa satu tempat untuk melihatnya.
- Akibatnya: **6 "tombol palsu"** (ada UI, tak ada kode yang membaca) dan **31 aturan
  tersembunyi** (dipakai mesin, tak ada UI).

Registry ini membuat setiap setting **eksplisit & bisa diaudit**:
  key · label awam · penjelasan · dampak bila diubah · contoh angka · tipe & batas ·
  level scope · **referensi kode konsumen (WAJIB)** · pemilik (role) · risiko · status.

UI "Pusat Pengaturan" **di-generate dari registry ini**, sehingga UI dan mesin tidak
bisa lagi berbeda. Gate `scripts/audit_config_wiring.py` menolak kunci `active` yang
tidak punya consumer nyata (INV-CFG-01).

Catatan penyimpanan (kompatibilitas): kunci tanpa prefix scope disimpan di dokumen
`system_settings{scope:"global"}` (override per entitas di `system_settings{scope:<entity_id>}`),
sedangkan kunci ber-prefix `uom.` `lot.` `makloon.` `receiving.` `hr.` disimpan di dokumen
`system_settings{scope:"<prefix>"}`. Resolver (`services/config_resolver.py`) memakai peta ini
sehingga mesin lama TETAP berfungsi tanpa migrasi paksa.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ── Tipe nilai yang didukung UI generik ──────────────────────────────────────
TYPES = {
    "bool",      # switch
    "int",       # angka bulat
    "pct",       # persen (0..100)
    "money",     # rupiah
    "decimal",   # angka desimal bebas
    "enum",      # pilihan tunggal dari options
    "text",      # teks pendek
    "list",      # daftar sederhana (urutan bermakna)
    "table",     # tabel/objek kompleks (editor khusus)
    "duration",  # jumlah hari
}

# Lapisan scope, dari paling umum ke paling spesifik (yang kanan menang).
SCOPE_LEVELS: List[str] = ["global", "entity", "customer", "supplier", "product", "document"]
RISKS = {"low", "medium", "high"}
STATUSES = {"active", "not_used"}

# Bentuk data untuk setting bertipe `table`. Menentukan editor mana yang dipakai UI:
#   list → array of objects  ⇒ editor baris (tambah/hapus baris, kolom bertipe)
#   map  → objek datar       ⇒ editor pasangan kunci-nilai
#   json → struktur bersarang ⇒ editor JSON (kasus jarang & memang kompleks)
# Tanpa ini UI hanya bisa menampilkan JSON mentah — itulah alasan editor pajak lama
# terasa lebih ramah daripada Pusat Pengaturan sebelum FASE G-0 dituntaskan.
ROW_SHAPES = {"list", "map", "json"}

# Prefix kunci yang tersimpan di dokumen `system_settings` scope tersendiri.
LEGACY_SCOPED_PREFIXES: Tuple[str, ...] = ("uom", "lot", "makloon", "receiving", "hr")


# ── Grup: dikelompokkan berdasarkan PERTANYAAN BISNIS, bukan nama modul ──────
# `question` sengaja ditulis sebagai pertanyaan yang biasa diucapkan pemilik usaha,
# supaya user tahu grup mana yang harus dibuka tanpa perlu paham arsitektur sistem.
GROUPS: List[Dict[str, Any]] = [
    {"id": "uang-masuk", "label": "Uang Masuk & Piutang", "order": 1,
     "question": "Kapan pelanggan harus bayar, dan apa akibatnya kalau telat?"},
    {"id": "harga-diskon", "label": "Harga, Diskon & Komisi", "order": 2,
     "question": "Siapa boleh menurunkan harga, dan bagaimana komisi sales dihitung?"},
    {"id": "persetujuan", "label": "Persetujuan & Ambang", "order": 3,
     "question": "Nilai berapa yang wajib disetujui, dan oleh siapa?"},
    {"id": "pajak", "label": "Pajak", "order": 4,
     "question": "Berapa PPN dan bagaimana faktur pajak dihitung?"},
    {"id": "keuangan-dasar", "label": "Dasar Keuangan & Periode", "order": 5,
     "question": "Mata uang apa yang dipakai dan kapan tahun buku ditutup?"},
    {"id": "pembelian", "label": "Pembelian & Tagihan Supplier", "order": 6,
     "question": "Berapa selisih yang masih boleh saat barang/tagihan supplier datang?"},
    {"id": "penerimaan", "label": "Penerimaan Barang", "order": 7,
     "question": "Boleh input qty pakai satuan supplier? Boleh terima lebih dari PO?"},
    {"id": "stok-satuan", "label": "Stok, Satuan & Alokasi", "order": 8,
     "question": "Stok mana yang dipakai lebih dulu, dan bagaimana satuan dikonversi?"},
    {"id": "kualitas", "label": "Kualitas (QC)", "order": 9,
     "question": "Berapa poin cacat yang membuat kain turun grade?"},
    {"id": "lot", "label": "Lot & Ketertelusuran", "order": 10,
     "question": "Seberapa ketat nomor lot & dye lot diwajibkan?"},
    {"id": "makloon", "label": "Produksi & Makloon", "order": 11,
     "question": "Berapa selisih hasil makloon yang masih wajar sebelum jadi klaim?"},
    {"id": "sdm", "label": "SDM & Penggajian", "order": 12,
     "question": "Berapa iuran BPJS, PPh 21, dan pengali lembur?"},
    {"id": "tampilan", "label": "Tampilan & Navigasi", "order": 13,
     "question": "Menu apa yang muncul, dan halaman awal setiap peran?"},
    # FASE G-1 — fondasi amandemen: tidak ada perubahan angka secara diam-diam.
    {"id": "amandemen", "label": "Koreksi & Amandemen Dokumen", "order": 14,
     "question": "Koreksi mana yang boleh langsung jalan, dan mana yang wajib disetujui?"},
    # FASE G-4 — relasi dokumen: setiap surat harus bisa ditelusuri dari surat lain.
    {"id": "dokumen", "label": "Dokumen, Referensi & Tanda Tangan", "order": 15,
     "question": "Dokumen apa yang wajib menyebut referensinya, dan seberapa jauh jejaknya ditelusuri?"},
    # FASE F — R&D & Desain: dari mana produk baru berasal, dan kapan boleh dijual.
    {"id": "rnd", "label": "R&D & Desain", "order": 16,
     "question": "Kapan barang hasil R&D boleh dipesan/dijual, dan berapa kali sample boleh diulang?"},
    # FASE G-8 — rekonsiliasi bank: kapan mutasi dianggap cocok, dan ke mana dana tak dikenal.
    {"id": "bank", "label": "Rekonsiliasi Bank", "order": 17,
     "question": "Kapan mutasi bank dicocokkan otomatis, dan ke mana dana tak dikenal ditampung?"},
    # FASE G-9 — pusat kasus keuangan: uang yang nyangkut harus punya antrean & batas waktu.
    {"id": "kasus", "label": "Pusat Kasus Keuangan", "order": 18,
     "question": "Berapa lama kasus uang boleh menganggur, dan nominal berapa yang wajib disetujui?"},
    # FASE G-7 — kontrabon: siklus tukar faktur supplier (toleransi 3-way, approval, pengingat).
    {"id": "kontrabon", "label": "Kontrabon (Tukar Faktur)", "order": 19,
     "question": "Berapa selisih 3-way match yang masih boleh lewat, siapa yang menyetujui, "
                 "dan kapan pengingat tukar faktur dikirim?"},
    # FASE G-6 — antar-PT sebagai jual-beli: mode harga (kontrak internal), PPN per-PT,
    # ambang persetujuan, pengingat settlement.
    {"id": "antar-entitas", "label": "Antar Entitas (Jual-Beli Antar-PT)", "order": 20,
     "question": "Bagaimana harga & PPN antar-PT ditentukan, dan kapan saldo pasangan PT "
                 "harus diingatkan untuk settlement?"},
]
GROUP_IDS = {g["id"] for g in GROUPS}

_REGISTRY: Dict[str, Dict[str, Any]] = {}
_ORDER: List[str] = []


def legacy_target(key: str) -> Tuple[str, str]:
    """Peta kunci registry → (scope dokumen `system_settings`, dot-path di dalam dokumen).

    >>> legacy_target("ar.grace_days")
    ('global', 'ar.grace_days')
    >>> legacy_target("receiving.block_over_remaining")
    ('receiving', 'block_over_remaining')
    """
    head, _, rest = key.partition(".")
    if head in LEGACY_SCOPED_PREFIXES and rest:
        return head, rest
    return "global", key


def E(
    key: str,
    *,
    group: str,
    label: str,
    help: str,
    impact: str,
    example: str = "",
    type: str = "text",
    default: Any = None,
    min: Optional[float] = None,
    max: Optional[float] = None,
    step: Optional[float] = None,
    options: Optional[Sequence[Dict[str, str]]] = None,
    unit: str = "",
    scopes: Sequence[str] = ("global", "entity"),
    consumers: Sequence[str] = (),
    owner_role: str = "admin",
    risk: str = "low",
    requires_reason: bool = False,
    status: str = "active",
    not_used_reason: str = "",
    simulate: str = "",
    related: Sequence[str] = (),
    row_shape: str = "",
    columns: Optional[Sequence[Dict[str, Any]]] = None,
    permission: Optional[Tuple[str, str]] = None,
    roles: Sequence[str] = (),
) -> Dict[str, Any]:
    """Daftarkan satu setting. Validasi ketat supaya registry tidak pernah setengah jadi."""
    if key in _REGISTRY:
        raise ValueError(f"config_registry: kunci ganda '{key}'")
    if type not in TYPES:
        raise ValueError(f"config_registry[{key}]: type '{type}' tidak dikenal")
    if group not in GROUP_IDS:
        raise ValueError(f"config_registry[{key}]: group '{group}' tidak ada di GROUPS")
    if risk not in RISKS:
        raise ValueError(f"config_registry[{key}]: risk '{risk}' tidak dikenal")
    if status not in STATUSES:
        raise ValueError(f"config_registry[{key}]: status '{status}' tidak dikenal")
    bad_scopes = [s for s in scopes if s not in SCOPE_LEVELS]
    if bad_scopes:
        raise ValueError(f"config_registry[{key}]: scope tak dikenal {bad_scopes}")
    if type == "enum" and not options:
        raise ValueError(f"config_registry[{key}]: type enum wajib punya options")
    if row_shape and row_shape not in ROW_SHAPES:
        raise ValueError(f"config_registry[{key}]: row_shape '{row_shape}' tidak dikenal")
    if row_shape == "list" and not columns:
        raise ValueError(
            f"config_registry[{key}]: row_shape 'list' wajib mendefinisikan columns "
            f"supaya UI bisa menampilkan editor baris (bukan JSON mentah)")
    if status == "active" and not consumers:
        raise ValueError(
            f"config_registry[{key}]: kunci 'active' WAJIB mencantumkan consumers "
            f"(kode yang membacanya) — INV-CFG-01")
    if status == "not_used" and not not_used_reason:
        raise ValueError(f"config_registry[{key}]: status not_used wajib not_used_reason")
    if not label or not help or not impact:
        raise ValueError(f"config_registry[{key}]: label/help/impact wajib diisi")

    legacy_scope, legacy_path = legacy_target(key)
    entry: Dict[str, Any] = {
        "key": key,
        "group": group,
        "label": label,
        "help": help,
        "impact": impact,
        "example": example,
        "type": type,
        "default": default,
        "min": min,
        "max": max,
        "step": step,
        "options": list(options or []),
        "unit": unit,
        "scopes": list(scopes),
        "consumers": list(consumers),
        "owner_role": owner_role,
        "risk": risk,
        "requires_reason": bool(requires_reason) or risk == "high",
        "status": status,
        "not_used_reason": not_used_reason,
        "simulate": simulate,
        "related": list(related),
        "row_shape": row_shape or ("json" if type == "table" else ""),
        "columns": [dict(c) for c in (columns or [])],
        # Izin yang dibutuhkan untuk MENGUBAH setting ini. Default `settings.manage`
        # (admin). Beberapa setting sengaja memakai izin domainnya sendiri supaya
        # penggabungan editor lama ke Pusat Pengaturan TIDAK mencabut wewenang yang
        # sudah dimiliki peran lain (mis. manager tetap boleh mengubah aturan gaji
        # lewat `hr.manage_payroll`, persis seperti sebelum editor lama dihapus).
        "permission": list(permission or ("settings", "manage")),
        # Peran NON-admin yang tetap boleh mengubah setting ini walau tidak punya
        # `settings.manage`. Dipakai untuk menyalin persis wewenang endpoint lama
        # yang berbasis role (mis. PUT /lots/settings = require_role(["manager"]))
        # sehingga penghapusan editor lama tidak mengurangi wewenang siapa pun.
        "roles": list(roles),
        "legacy_scope": legacy_scope,
        "legacy_path": legacy_path,
        "editable": status == "active",
    }
    _REGISTRY[key] = entry
    _ORDER.append(key)
    return entry


# ── Akses ────────────────────────────────────────────────────────────────────
def all_entries() -> List[Dict[str, Any]]:
    return [_REGISTRY[k] for k in _ORDER]


def get(key: str) -> Optional[Dict[str, Any]]:
    return _REGISTRY.get(key)


def require(key: str) -> Dict[str, Any]:
    entry = _REGISTRY.get(key)
    if not entry:
        raise KeyError(f"Setting '{key}' tidak ada di registry")
    return entry


def keys() -> List[str]:
    return list(_ORDER)


def groups() -> List[Dict[str, Any]]:
    """Grup + jumlah setting di dalamnya (untuk navigasi Pusat Pengaturan)."""
    out = []
    for g in sorted(GROUPS, key=lambda x: x["order"]):
        items = [e for e in all_entries() if e["group"] == g["id"]]
        out.append({**g, "count": len(items),
                    "active_count": len([e for e in items if e["status"] == "active"])})
    return out


def by_group(group_id: str) -> List[Dict[str, Any]]:
    return [e for e in all_entries() if e["group"] == group_id]


def search(term: str) -> List[Dict[str, Any]]:
    """Pencarian awam: cocokkan label, key, help, impact, dan nama grup."""
    t = (term or "").strip().lower()
    if not t:
        return all_entries()
    glabel = {g["id"]: g["label"].lower() for g in GROUPS}
    hits = []
    for e in all_entries():
        hay = " ".join([e["key"], e["label"], e["help"], e["impact"],
                        glabel.get(e["group"], "")]).lower()
        if t in hay:
            hits.append(e)
    return hits


# ── Validasi & koersi nilai (dipakai PUT /api/config/values) ─────────────────
def coerce(entry: Dict[str, Any], value: Any) -> Any:
    """Ubah nilai masukan menjadi tipe yang benar; lempar `ValueError` bila tak sah.

    Pesan error ditulis dalam Bahasa Indonesia agar bisa langsung ditampilkan ke user.
    """
    key, typ = entry["key"], entry["type"]
    if typ == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false", "1", "0", "ya", "tidak"}:
            return value.lower() in {"true", "1", "ya"}
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"'{key}' harus Ya/Tidak")

    if typ in {"int", "duration"}:
        try:
            num = int(round(float(value)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"'{key}' harus angka bulat") from exc
        return _bounded(entry, num)

    if typ in {"pct", "money", "decimal"}:
        from core_utils import parse_decimal
        try:
            num = parse_decimal(value, 4)
        except ValueError as exc:
            raise ValueError(f"'{key}' harus angka ({exc})") from exc
        if typ == "pct" and (num < 0 or num > 100) and entry.get("max") is None:
            raise ValueError(f"'{key}' persen harus 0–100 (diberi {num})")
        return _bounded(entry, num)

    if typ == "enum":
        allowed = [o["value"] for o in entry["options"]]
        if value not in allowed:
            raise ValueError(f"'{key}' harus salah satu dari {allowed}")
        return value

    if typ == "text":
        if not isinstance(value, str):
            raise ValueError(f"'{key}' harus teks")
        return value.strip()

    if typ == "list":
        if not isinstance(value, list):
            raise ValueError(f"'{key}' harus daftar (list)")
        return value

    if typ == "table":
        if not isinstance(value, (dict, list)):
            raise ValueError(f"'{key}' harus objek/tabel")
        return value

    return value


def _bounded(entry: Dict[str, Any], num: float) -> float:
    lo, hi = entry.get("min"), entry.get("max")
    if lo is not None and num < lo:
        raise ValueError(f"'{entry['key']}' minimum {lo} (diberi {num})")
    if hi is not None and num > hi:
        raise ValueError(f"'{entry['key']}' maksimum {hi} (diberi {num})")
    return num


def covers(leaf_key: str) -> Optional[Dict[str, Any]]:
    """Entri registry yang "mencakup" sebuah kunci daun.

    Kunci tabel didaftarkan pada level container (mis. `hr.ptkp_table`), sedangkan
    audit memindai daun (`hr.ptkp_table.TK0`). Fungsi ini menjembatani keduanya.
    """
    if leaf_key in _REGISTRY:
        return _REGISTRY[leaf_key]
    parts = leaf_key.split(".")
    for i in range(len(parts) - 1, 0, -1):
        cand = ".".join(parts[:i])
        if cand in _REGISTRY:
            return _REGISTRY[cand]
    return None


# ── Muat katalog (harus di paling bawah: E() sudah terdefinisi) ──────────────
import config_catalog_core  # noqa: E402,F401  (registrasi via side-effect)
import config_catalog_ops   # noqa: E402,F401
import config_catalog_finance  # noqa: E402,F401  (FASE G-1 — amandemen)
import config_catalog_documents  # noqa: E402,F401  (FASE G-4 — relasi dokumen)
import config_catalog_payment  # noqa: E402,F401  (FASE G-2 — rencana pembayaran & denda)
import config_catalog_bank  # noqa: E402,F401  (FASE G-8 — rekonsiliasi bank: skor & titipan)
import config_catalog_case  # noqa: E402,F401  (FASE G-9 — pusat kasus keuangan: SLA & ambang)
import config_catalog_contrabon  # noqa: E402,F401  (FASE G-7 — kontrabon: toleransi 3-way & pengingat)
import config_catalog_interco  # noqa: E402,F401  (FASE G-6 — antar-PT: mode harga, PPN, settlement)
import config_catalog_period  # noqa: E402,F401  (FASE G-5 — unlock periode: jendela & batas mundur)

import config_catalog_rnd  # noqa: E402,F401  (FASE F — R&D & Desain: lifecycle, sample, kontrak)
import config_catalog_approval_matrix  # noqa: E402,F401  (PS-20/D-14 — penegakan matriks persetujuan divisi)
