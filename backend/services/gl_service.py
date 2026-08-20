"""EPIC7-C — General Ledger & Chart of Accounts (akuntansi inti).

Dua koleksi kanonik baru:
- `gl_accounts`    (prefix `gla_`) — Bagan Akun / Chart of Accounts (master).
- `journal_entries` (prefix `je_`) — Jurnal umum (double-entry, balanced).

PRINSIP:
- Setiap jurnal WAJIB seimbang: Σdebit == Σkredit (di-enforce saat create).
- Auto-posting DITURUNKAN dari SSOT yang sudah ada (idempotent by
  source_type+source_id) agar tidak double-count:
    * `sales_orders`     → pengakuan pendapatan (Dr Piutang/Kas, Cr Pendapatan + PPN Keluaran)
    * `cash_transactions`→ mutasi kas (Dr/Cr Kas/Bank vs lawan akun by ref_type)
- Trial Balance & Buku Besar diturunkan dari journal_entries (status != void).

Normal balance: asset & expense = debit; liability, equity, income = credit.
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso, next_doc_number, safe_doc, DEFAULT_ENTITY_ID
from services import costing_service
from services.customer_service import (
    _order_grand_total as order_grand_total,
    order_payment_method,
    NON_AR_METHODS,
    DEAD_STATUSES,
)
from request_context import active_entity_or

EPS = 0.01

# ─── Tipe akun & normal balance ──────────────────────────────────────────────
ACCOUNT_TYPES = ["asset", "liability", "equity", "income", "expense"]
TYPE_LABELS = {
    "asset": "Aset",
    "liability": "Kewajiban",
    "equity": "Ekuitas",
    "income": "Pendapatan",
    "expense": "Beban",
}
DEBIT_TYPES = {"asset", "expense"}  # sisanya credit


def normal_balance(acc_type: str) -> str:
    return "debit" if acc_type in DEBIT_TYPES else "credit"


# ─── Default Chart of Accounts (Indonesia, ringkas namun lengkap) ────────────
# (code, name, type, parent_code, is_postable)
DEFAULT_COA: List = [
    # ASET
    ("1-0000", "ASET", "asset", "", False),
    ("1-1000", "Aset Lancar", "asset", "1-0000", False),
    ("1-1100", "Kas Besar / Bank", "asset", "1-1000", True),
    ("1-1110", "Kas Kecil", "asset", "1-1000", True),
    ("1-1150", "Kas & Bank Transit (Dana Dalam Perjalanan)", "asset", "1-1000", True),  # FASE G-9 — pindah-buku antar rekening sendiri
    ("1-1200", "Piutang Usaha", "asset", "1-1000", True),
    ("1-1250", "Piutang Antar-Perusahaan (IC-AR)", "asset", "1-1000", True),
    ("1-1260", "Piutang Klaim Mitra (Makloon)", "asset", "1-1000", True),  # Fase D — D-09 (ganti rugi mitra)
    ("1-1270", "Piutang Denda Pelanggan", "asset", "1-1000", True),  # FASE G-2 — denda keterlambatan
    ("1-1280", "Piutang Titipan Karyawan", "asset", "1-1000", True),  # FASE G-9 — uang perusahaan yang dipegang karyawan
    ("1-1300", "Persediaan Barang", "asset", "1-1000", True),
    # FASE G-6 — barang antar-PT yang SUDAH dibeli (dokumen & utang lahir) tetapi
    # BELUM diterima gudang pembeli. Tanpa akun ini, persediaan pembeli membengkak
    # sebelum barangnya ada (GL 1-1300 selalu drift dari subledger roll).
    ("1-1310", "Persediaan Dalam Perjalanan (Antar-PT)", "asset", "1-1000", True),
    ("1-1350", "Persediaan Dalam Proses (Makloon/WIP)", "asset", "1-1000", True),
    ("1-1400", "Uang Muka & Biaya Dibayar Dimuka", "asset", "1-1000", True),
    ("1-1500", "PPN Masukan", "asset", "1-1000", True),
    ("1-1900", "Aset Lancar Lainnya", "asset", "1-1000", True),
    ("1-9999", "Akun Sementara (Suspense)", "asset", "1-1000", True),
    ("1-2000", "Aset Tetap", "asset", "1-0000", False),
    ("1-2100", "Peralatan & Mesin", "asset", "1-2000", True),
    ("1-2200", "Kendaraan", "asset", "1-2000", True),               # R6.2 — Fixed Assets
    ("1-2300", "Inventaris & Perabot Kantor", "asset", "1-2000", True),  # R6.2
    ("1-2400", "Bangunan", "asset", "1-2000", True),                # R6.2
    ("1-2900", "Akumulasi Penyusutan Aset Tetap", "asset", "1-2000", True),  # R6.2 — contra-asset (saldo kredit)
    # KEWAJIBAN
    ("2-0000", "KEWAJIBAN", "liability", "", False),
    ("2-1000", "Kewajiban Lancar", "liability", "2-0000", False),
    ("2-1100", "Hutang Usaha", "liability", "2-1000", True),
    ("2-1150", "Hutang Belum Ditagih (GR/IR)", "liability", "2-1000", True),
    ("2-1250", "Utang Antar-Perusahaan (IC-AP)", "liability", "2-1000", True),
    ("2-1200", "PPN Keluaran", "liability", "2-1000", True),
    ("2-1300", "Hutang Pajak Lainnya", "liability", "2-1000", True),
    ("2-1400", "Uang Muka Pelanggan", "liability", "2-1000", True),
    ("2-1450", "Saldo Kredit Pelanggan (Store Credit)", "liability", "2-1000", True),  # R5.2 — store-credit ledger
    ("2-1500", "Hutang Insentif Penjualan", "liability", "2-1000", True),
    ("2-1600", "Hutang Gaji", "liability", "2-1000", True),
    ("2-1700", "Hutang BPJS", "liability", "2-1000", True),
    ("2-1800", "Hutang PPh 21", "liability", "2-1000", True),
    ("2-1900", "Kewajiban Lancar Lainnya", "liability", "2-1000", True),
    # FASE G-8 — dana masuk yang belum ketahuan pemiliknya diakui sebagai KEWAJIBAN
    # (titipan), bukan dibiarkan menggantung tanpa jurnal.
    ("2-1950", "Titipan Dana Belum Teridentifikasi", "liability", "2-1000", True),
    # EKUITAS
    ("3-0000", "EKUITAS", "equity", "", False),
    ("3-1000", "Modal Disetor", "equity", "3-0000", True),
    ("3-2000", "Laba Ditahan", "equity", "3-0000", True),
    ("3-2900", "Ekuitas Saldo Awal", "equity", "3-0000", True),
    ("3-3000", "Laba Tahun Berjalan", "equity", "3-0000", True),
    # PENDAPATAN
    ("4-0000", "PENDAPATAN", "income", "", False),
    ("4-1000", "Pendapatan Penjualan", "income", "4-0000", True),
    ("4-9000", "Pendapatan Lain-lain", "income", "4-0000", True),
    ("4-9100", "Laba Pelepasan Aset Tetap", "income", "4-0000", True),  # R6.2 — gain on disposal
    ("4-9200", "Pendapatan Klaim Makloon", "income", "4-0000", True),   # Fase D — D-09 (potong bon / ganti rugi)
    ("4-9300", "Pendapatan Denda Keterlambatan", "income", "4-0000", True),  # FASE G-2
    # BEBAN (termasuk HPP)
    ("5-0000", "BEBAN POKOK", "expense", "", False),
    ("5-1000", "Harga Pokok Penjualan", "expense", "5-0000", True),
    ("5-1100", "Overhead Produksi Diserap", "expense", "5-0000", True),  # R6.4 — applied mfg overhead (kredit → kapitalisasi ke persediaan)
    # FASE T — jasa makloon yang TIDAK bisa menempel ke kain mana pun. Terjadi bila
    # SPK berisi langkah "jasa murni" (mis. pembuatan kasa/screen) tetapi tidak ada
    # langkah kain sesudahnya yang bisa menyerap biayanya. Tanpa akun ini, nilainya
    # menggantung di WIP 1-1350 selamanya (drift yang tak pernah bisa dijelaskan).
    ("5-1200", "Beban Jasa Makloon Tak Terserap", "expense", "5-0000", True),
    ("5-9000", "Beban Angkut Pembelian", "expense", "5-0000", True),
    ("5-9500", "Beban Kerugian/Penghapusan Persediaan", "expense", "5-0000", True),  # R5.1 — write-off scrap/goods
    ("6-0000", "BEBAN OPERASIONAL", "expense", "", False),
    ("6-1000", "Beban Gaji", "expense", "6-0000", True),
    ("6-1100", "Beban BPJS (Perusahaan)", "expense", "6-0000", True),
    ("6-2000", "Beban Sewa", "expense", "6-0000", True),
    ("6-3000", "Beban Utilitas", "expense", "6-0000", True),
    ("6-4000", "Beban Operasional Lainnya", "expense", "6-0000", True),
    # Sub-akun beban petty cash (Digitalisasi Formulir Sukacita) — mapping configurable
    ("6-4100", "Beban ATK & Perlengkapan Kantor", "expense", "6-0000", True),
    ("6-4200", "Beban Konsumsi & Entertainment", "expense", "6-0000", True),
    ("6-4300", "Beban Cetak, Fotokopi & Materai", "expense", "6-0000", True),
    ("6-4400", "Beban Utilitas Kantor", "expense", "6-0000", True),
    ("6-4500", "Beban Kirim Dokumen & Ekspedisi", "expense", "6-0000", True),
    ("6-4600", "Beban Transportasi & BBM", "expense", "6-0000", True),
    ("6-4900", "Beban Petty Cash Lainnya", "expense", "6-0000", True),
    ("6-5000", "Beban Insentif Penjualan", "expense", "6-0000", True),
    ("6-6000", "Beban Penyusutan Aset Tetap", "expense", "6-0000", True),  # R6.2 — depreciation expense
    ("6-7000", "Beban Sample & Pengembangan (R&D)", "expense", "6-0000", True),  # FASE F — bahan yang dipakai membuat sample
    ("6-8000", "Beban Administrasi Bank", "expense", "6-0000", True),  # FASE G-8 — biaya adm/transfer yang dipotong bank
    ("6-9000", "Beban Lain-lain", "expense", "6-0000", True),
    ("6-9100", "Beban Selisih Pembayaran Pelanggan", "expense", "6-0000", True),  # FASE G-3 — kurang bayar dihapus/pembulatan
    ("6-9500", "Rugi Pelepasan Aset Tetap", "expense", "6-0000", True),  # R6.2 — loss on disposal
]

# Akun kunci untuk auto-posting
ACC_KAS_BESAR = "1-1100"
ACC_KAS_KECIL = "1-1110"
ACC_PIUTANG = "1-1200"
ACC_UANG_MUKA_PELANGGAN = "2-1400"  # KN-076-AR-GL-DRIFT — Uang Muka Pelanggan (deposit/kelebihan bayar)
ACC_IC_AR = "1-1250"           # M-3 — Piutang Antar-Perusahaan (inter-company)
ACC_PIUTANG_KLAIM = "1-1260"   # Fase D (D-09) — Piutang Klaim Mitra Makloon (ganti rugi)
ACC_PIUTANG_DENDA = "1-1270"   # FASE G-2 — Piutang Denda Pelanggan (keterlambatan)
ACC_KAS_TRANSIT = "1-1150"     # FASE G-9 — Kas/Bank Transit (pindah-buku antar rekening sendiri)
ACC_PIUTANG_KARYAWAN = "1-1280"  # FASE G-9 — Piutang Titipan Karyawan (uang KN dipegang karyawan)
ACC_PERSEDIAAN = "1-1300"     # F3 — Persediaan Barang (Inventory)
ACC_PERSEDIAAN_TRANSIT = "1-1310"  # FASE G-6 — Persediaan Dalam Perjalanan (antar-PT)
ACC_WIP_SUBCON = "1-1350"     # M2 — Persediaan Dalam Proses (Makloon/WIP-at-vendor)
ACC_HUTANG = "2-1100"
ACC_GRIR = "2-1150"            # Gelombang 1 F-3/F-5 — GR/IR (barang diterima belum ditagih)
ACC_IC_AP = "2-1250"           # M-3 — Utang Antar-Perusahaan (inter-company)
ACC_UANG_MUKA = "1-1400"       # Uang Muka & Biaya Dibayar Dimuka (cash advance / petty cash)
ACC_PPN_IN = "1-1500"          # Gelombang 1 F-5 — PPN Masukan
ACC_EKUITAS_AWAL = "3-2900"    # Gelombang 1 F-3 — saldo awal persediaan
ACC_PPN_OUT = "2-1200"
ACC_PENDAPATAN = "4-1000"
ACC_PENDAPATAN_LAIN = "4-9000"
ACC_HPP = "5-1000"            # F3 — Harga Pokok Penjualan (COGS)
ACC_OVERHEAD_APPLIED = "5-1100"  # R6.4 — Overhead Produksi Diserap (contra-expense; kredit saat kapitalisasi ke persediaan)
ACC_JASA_TAK_TERSERAP = "5-1200"  # FASE T — jasa makloon "jasa murni" yang tak menempel ke kain
ACC_LANDED = "5-9000"
ACC_WRITEOFF = "5-9500"       # R5.1 — Beban Kerugian/Penghapusan Persediaan (scrap/goods write-off)
ACC_STORE_CREDIT = "2-1450"   # R5.2 — Saldo Kredit Pelanggan (store credit liability)
ACC_TITIPAN_DANA = "2-1950"   # FASE G-8 — Titipan Dana Belum Teridentifikasi (rekonsiliasi bank)
ACC_BEBAN_OPS = "6-4000"
ACC_BEBAN_INSENTIF = "6-5000"   # F0-E — Beban Insentif Penjualan
ACC_HUTANG_INSENTIF = "2-1500"  # F0-E — Hutang Insentif Penjualan (akrual)
ACC_BEBAN_GAJI = "6-1000"       # H4 — Beban Gaji & Upah
ACC_BEBAN_BPJS = "6-1100"       # H4 — Beban BPJS (kontribusi perusahaan)
ACC_HUTANG_GAJI = "2-1600"      # H4 — Hutang Gaji (take-home belum dibayar)
ACC_HUTANG_BPJS = "2-1700"      # H4 — Hutang BPJS (employee + employer)
ACC_HUTANG_PPH21 = "2-1800"     # H4 — Hutang PPh 21
ACC_SUSPENSE = "1-9999"
# R6.2 — Fixed Assets & Depresiasi
ACC_FA_ACCUM_DEP = "1-2900"     # Akumulasi Penyusutan Aset Tetap (contra-asset)
ACC_DEP_EXPENSE = "6-6000"      # Beban Penyusutan Aset Tetap
ACC_FA_GAIN = "4-9100"          # Laba Pelepasan Aset Tetap (gain on disposal)
ACC_KLAIM_MAKLOON = "4-9200"    # Fase D (D-09) — Pendapatan Klaim Makloon (potong bon / ganti rugi)
ACC_PENDAPATAN_DENDA = "4-9300"  # FASE G-2 — Pendapatan Denda Keterlambatan
ACC_SELISIH_BAYAR = "6-9100"     # FASE G-3 — Beban Selisih Pembayaran (kurang bayar dihapus)
ACC_BEBAN_RND = "6-7000"         # FASE F — Beban Sample & Pengembangan (bahan sample keluar gudang)
ACC_BEBAN_BANK = "6-8000"        # FASE G-8 — Beban Administrasi Bank (biaya adm/transfer dipotong bank)
ACC_FA_LOSS = "6-9500"          # Rugi Pelepasan Aset Tetap (loss on disposal)

# keyword kategori → akun (manual cash entries) untuk semantik akuntansi lebih tepat
CASH_OUT_KEYWORDS = [
    ("gaji", "6-1000"), ("payroll", "6-1000"),
    ("sewa", "6-2000"), ("rent", "6-2000"),
    ("listrik", "6-3000"), ("air", "6-3000"), ("utilitas", "6-3000"),
    ("internet", "6-3000"), ("telepon", "6-3000"),
    ("pembelian", "1-1300"), ("beli", "1-1300"), ("bahan", "1-1300"),
    ("operasional", "6-4000"),
]
CASH_IN_KEYWORDS = [
    ("modal", "3-1000"), ("capital", "3-1000"), ("investasi", "3-1000"), ("setoran modal", "3-1000"),
    ("bunga", "4-9000"), ("jasa giro", "4-9000"),
    ("penjualan tunai", "4-1000"),
    # FASE G-8 — dana masuk tak dikenal: Dr Bank / Cr 2-1950 Titipan (KEWAJIBAN), bukan
    # pendapatan dan bukan suspense. Kategori ini ditulis `bank_recon_service.to_holding`.
    ("titipan", "2-1950"),
]


def _cash_account(txn: Dict[str, Any]) -> str:
    return ACC_KAS_KECIL if txn.get("cash_type") == "kas_kecil" else ACC_KAS_BESAR


# ═════════════════════════════════════════════════════════════════════════════
#  CHART OF ACCOUNTS (master)
# ═════════════════════════════════════════════════════════════════════════════

async def seed_default_coa() -> int:
    """Pastikan bagan akun baku tersedia (idempotent — hanya tambah yg belum ada).

    Akun template (`entity_id=None`) berlaku sebagai default lintas-PT. Setiap
    PT boleh membuat akun tambahan atau override nama/status via field `entity_id`
    (lihat M-3 CoA per-PT). Posting JE tetap resolve by-code global.
    """
    existing = {a["code"] for a in await db.gl_accounts.find(
        {"entity_id": {"$in": [None, ""]}}, {"_id": 0, "code": 1}).to_list(2000)}
    to_add = []
    for code, name, atype, parent, postable in DEFAULT_COA:
        if code in existing:
            continue
        to_add.append({
            "id": new_id("gla"),
            "code": code,
            "name": name,
            "type": atype,
            "normal_balance": normal_balance(atype),
            "parent_code": parent,
            "is_postable": bool(postable),
            "is_active": True,
            "system": True,           # akun baku — tak boleh dihapus
            "currency": "IDR",
            "description": "",
            "entity_id": None,        # M-3 — None = template global (SHARED)
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })
    if to_add:
        await db.gl_accounts.insert_many(to_add)
    return len(to_add)


async def list_accounts(active_only: bool = False,
                        entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Daftar akun.
    - Tanpa `entity_id` → HANYA template global (entity_id=None).
    - Dengan `entity_id` → effective view: override PT (kalau ada) menang atas
      template global per `code`; akun khusus PT (code hanya ada di override) juga
      ikut muncul. Tidak menyentuh akun PT lain.
    """
    q: Dict[str, Any] = {}
    if active_only:
        q["is_active"] = True
    if entity_id:
        # Ambil template global + override untuk entity ini; dedupe by-code, override wins.
        q_or = [{"entity_id": {"$in": [None, ""]}}, {"entity_id": entity_id}]
        rows = await db.gl_accounts.find({**q, "$or": q_or}, {"_id": 0}).to_list(4000)
        merged: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            code = r.get("code", "")
            if not code:
                continue
            eid = r.get("entity_id")
            if code not in merged:
                merged[code] = r
            else:
                # Override wins bila entity_id cocok dengan yang diminta.
                if eid == entity_id:
                    merged[code] = r
        result = list(merged.values())
    else:
        q["entity_id"] = {"$in": [None, ""]}
        result = await db.gl_accounts.find(q, {"_id": 0}).to_list(2000)
    # FASE E-4 (E4.4) — sebutkan ASAL setiap baris. Tanpa ini layar CoA tidak bisa
    # membedakan "akun ini memang milik badan usaha saya" dari "akun ini warisan
    # template grup", padahal keduanya tampil identik dan konsekuensinya beda:
    # menonaktifkan yang pertama hanya kena satu badan usaha, yang kedua kena semua.
    for row in result:
        own = entity_id and row.get("entity_id") == entity_id
        row["entity_scope"] = "entity" if own else "global"
        row["source_label"] = "Badan usaha ini" if own else "Global"
        row["is_entity_override"] = bool(own)
    result.sort(key=lambda a: a.get("code", ""))
    return result


async def get_account(code: str,
                      entity_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Ambil 1 akun by-code. Kalau `entity_id` diberikan, override PT diutamakan;
    fallback ke template global."""
    if entity_id:
        override = await db.gl_accounts.find_one(
            {"code": code, "entity_id": entity_id}, {"_id": 0})
        if override:
            return override
    return await db.gl_accounts.find_one(
        {"code": code, "entity_id": {"$in": [None, ""]}}, {"_id": 0})


async def create_account(payload, entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Buat akun. `entity_id=None` = akun template global; `entity_id=<id>` =
    akun khusus PT (bisa akun baru atau override akun template dengan `code` sama).
    Duplicate check: unique per `(code, entity_id)`."""
    code = (payload.code or "").strip()
    name = (payload.name or "").strip()
    atype = (payload.type or "").strip()
    if not code or not name:
        raise ValueError("Kode dan nama akun wajib diisi.")
    if atype not in ACCOUNT_TYPES:
        raise ValueError(f"Tipe akun harus salah satu: {', '.join(ACCOUNT_TYPES)}")
    scope_q: Dict[str, Any] = {"code": code}
    if entity_id:
        scope_q["entity_id"] = entity_id
    else:
        scope_q["entity_id"] = {"$in": [None, ""]}
    if await db.gl_accounts.find_one(scope_q, {"_id": 0}):
        scope_note = f" untuk PT {entity_id}" if entity_id else " (template global)"
        raise ValueError(f"Kode akun '{code}' sudah dipakai{scope_note}.")
    if payload.parent_code:
        parent = await db.gl_accounts.find_one(
            {"code": payload.parent_code, "entity_id": {"$in": [None, "", entity_id]}},
            {"_id": 0})
        if not parent:
            raise ValueError("Akun induk tidak ditemukan.")
    doc = {
        "id": new_id("gla"),
        "code": code,
        "name": name,
        "type": atype,
        "normal_balance": normal_balance(atype),
        "parent_code": (payload.parent_code or "").strip(),
        "is_postable": bool(payload.is_postable if payload.is_postable is not None else True),
        "is_active": True,
        "system": False,
        "currency": payload.currency or "IDR",
        "description": (payload.description or "").strip(),
        "entity_id": entity_id or None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.gl_accounts.insert_one(doc)
    return safe_doc(doc)


async def update_account(code: str, patch: Dict[str, Any],
                         entity_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Update akun. Kalau `entity_id` diberikan, target override PT (buat baru
    kalau belum ada — upsert override). Kalau tanpa `entity_id`, update akun
    template global."""
    scope: Dict[str, Any] = {"code": code}
    if entity_id:
        scope["entity_id"] = entity_id
    else:
        scope["entity_id"] = {"$in": [None, ""]}
    acc = await db.gl_accounts.find_one(scope, {"_id": 0})
    if not acc and entity_id:
        # Belum ada override untuk PT ini → buat baru berbasis template global.
        template = await db.gl_accounts.find_one(
            {"code": code, "entity_id": {"$in": [None, ""]}}, {"_id": 0})
        if not template:
            return None
        override = {**template, "id": new_id("gla"), "entity_id": entity_id,
                    "system": False, "created_at": now_iso(), "updated_at": now_iso()}
        override.pop("_id", None)
        await db.gl_accounts.insert_one(override)
        acc = override
    if not acc:
        return None
    upd: Dict[str, Any] = {}
    for k in ["name", "description", "parent_code"]:
        if patch.get(k) is not None:
            upd[k] = str(patch[k]).strip()
    if patch.get("is_active") is not None:
        upd["is_active"] = bool(patch["is_active"])
    if patch.get("is_postable") is not None and not acc.get("system"):
        upd["is_postable"] = bool(patch["is_postable"])
    upd["updated_at"] = now_iso()
    await db.gl_accounts.update_one({"id": acc["id"]}, {"$set": upd})
    return await db.gl_accounts.find_one({"id": acc["id"]}, {"_id": 0})


async def delete_account(code: str, entity_id: Optional[str] = None) -> None:
    """Hapus akun. Untuk akun template global (entity_id=None) tidak boleh sistem.
    Untuk override PT, hanya menghapus override (template tetap)."""
    scope: Dict[str, Any] = {"code": code}
    if entity_id:
        scope["entity_id"] = entity_id
    else:
        scope["entity_id"] = {"$in": [None, ""]}
    acc = await db.gl_accounts.find_one(scope, {"_id": 0})
    if not acc:
        raise ValueError("Akun tidak ditemukan.")
    if acc.get("system") and not entity_id:
        raise ValueError("Akun baku sistem tidak dapat dihapus (boleh dinonaktifkan).")
    # Cegah hapus bila dipakai jurnal (hanya cek untuk template global; override
    # PT boleh dilepas karena posting selalu memakai kode template).
    if not entity_id:
        used = await db.journal_entries.count_documents(
            {"lines.account_code": code, "status": {"$ne": "void"}}
        )
        if used:
            raise ValueError(f"Akun dipakai pada {used} jurnal — tidak dapat dihapus.")
        child = await db.gl_accounts.count_documents(
            {"parent_code": code, "entity_id": {"$in": [None, ""]}})
        if child:
            raise ValueError("Akun memiliki sub-akun — hapus/abaikan sub-akun dahulu.")
    await db.gl_accounts.delete_one({"id": acc["id"]})


# ═════════════════════════════════════════════════════════════════════════════
#  JOURNAL ENTRIES (general ledger)
# ═════════════════════════════════════════════════════════════════════════════

def _norm_lines(raw_lines: List[Dict[str, Any]], names: Dict[str, str]) -> List[Dict[str, Any]]:
    out = []
    for ln in raw_lines:
        code = str(ln.get("account_code", "")).strip()
        debit = round(float(ln.get("debit", 0) or 0), 2)
        credit = round(float(ln.get("credit", 0) or 0), 2)
        norm = {
            "account_code": code,
            "account_name": names.get(code, ln.get("account_name", "")),
            "debit": debit,
            "credit": credit,
            "description": str(ln.get("description", "") or "").strip(),
        }
        # Digitalisasi Sukacita — bawa metadata voucher opsional bila ada
        for extra in ("job", "memo", "tax_code"):
            if ln.get(extra) not in (None, ""):
                norm[extra] = ln.get(extra)
        out.append(norm)
    return out


async def _account_names(codes: List[str]) -> Dict[str, str]:
    """Nama akun by-code — SELALU dari template global (posting-agnostik terhadap PT)."""
    rows = await db.gl_accounts.find(
        {"code": {"$in": list(set(codes))}, "entity_id": {"$in": [None, ""]}},
        {"_id": 0, "code": 1, "name": 1}).to_list(2000)
    return {r["code"]: r["name"] for r in rows}


# ─── FASE G-5 — Hard-lock periode tertutup (unlock berotoritas) ──────────────
class ClosedPeriodError(ValueError):
    """Posting ke periode tertutup tanpa jendela unlock aktif — pesan siap tampil (ID)."""


async def enforce_closed_period_guard(entity_id: str, date: str, *,
                                      source_type: str = "",
                                      can_backdate: bool = True) -> Optional[Dict[str, Any]]:
    """FASE G-5 — jaga agar tak ada jurnal MUNDUR menyusup ke periode `closed`.

    - `source_type == "closing"` → dilewati (jurnal penutup MEMANG di dalam periode).
    - Tanggal di luar periode tertutup → return None (posting normal, tanpa tanda).
    - Periode tertutup + ADA jendela unlock aktif → return dokumen `plu` (caller
      WAJIB menandai `backdated_in_unlock` dan mendaftarkan JE-nya).
    - Periode tertutup TANPA jendela unlock aktif → raise ClosedPeriodError.
    - Periode dibuka tapi `can_backdate=False` (tak punya izin) → raise ClosedPeriodError.
    """
    if source_type == "closing":
        return None
    d = (date or "")[:10]
    if not d or not entity_id:
        return None
    from services import closing_service as _cs
    st = await _cs.status_for_date(d, entity_id)
    if not st.get("closed"):
        return None
    label = st.get("period_label", st.get("period_key", d))
    from services import period_unlock_service as _pus
    plu = await _pus.find_active_unlock(entity_id, d)
    if not plu:
        raise ClosedPeriodError(
            f"Periode {label} sudah DITUTUP (terkunci). Jurnal mundur ke tanggal {d} "
            f"memerlukan izin 'Buka Periode' yang disetujui dua orang. "
            f"Ajukan di Keuangan → Buka Periode (Unlock).")
    if not can_backdate:
        raise ClosedPeriodError(
            f"Periode {label} sedang dibuka, tetapi Anda tidak memiliki izin "
            f"'period.backdate' untuk memposting jurnal mundur.")
    return plu


async def _insert_entry(*, lines: List[Dict[str, Any]], description: str, date: str,
                        source_type: str, source_id: str, entity_id: str,
                        created_by: str, source_label: str = "") -> Dict[str, Any]:
    """Insert jurnal seimbang. Caller MEMASTIKAN balance (helper auto-post)."""
    names = await _account_names([l["account_code"] for l in lines])
    norm = _norm_lines(lines, names)
    total_debit = round(sum(l["debit"] for l in norm), 2)
    total_credit = round(sum(l["credit"] for l in norm), 2)
    number = await next_doc_number("journal_entries", "number", "JE-", entity_id=entity_id)
    doc = {
        "id": new_id("je"),
        "number": number,
        "date": date or now_iso(),
        "description": description,
        "source": source_type,
        "source_type": source_type,
        "source_id": source_id,
        "source_label": source_label,
        "lines": norm,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "status": "posted",
        "entity_id": entity_id or DEFAULT_ENTITY_ID,
        "created_by": created_by or "system",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    # FASE G-5 — hard-lock periode tertutup + tandai jurnal mundur ber-unlock.
    plu = await enforce_closed_period_guard(
        doc["entity_id"], doc["date"], source_type=source_type, can_backdate=True)
    if plu:
        doc["backdated_in_unlock"] = plu["id"]
    await db.journal_entries.insert_one(doc)
    if source_type != "closing":
        await _mark_stale_closings(doc["entity_id"], doc["date"])
        if plu:
            from services import period_unlock_service as _pus
            await _pus.register_backdated_je(plu["id"], doc["id"])
    return safe_doc(doc)


async def _mark_stale_closings(entity_id: str, date_iso: str) -> None:
    """F-9 — posting backdate ke periode tertutup → tandai closing STALE (perlu re-close)."""
    d = (date_iso or "")[:10]
    if not d or not entity_id:
        return
    await db.period_closings.update_many(
        {"entity_id": entity_id, "status": "closed", "stale": {"$ne": True},
         "start_date": {"$lte": d}, "end_date": {"$gte": d}},
        {"$set": {"stale": True, "stale_at": now_iso(),
                  "stale_reason": f"Ada posting jurnal backdate ({d}) setelah periode ditutup",
                  "updated_at": now_iso()}})


async def create_manual_entry(payload, actor: Dict[str, Any],
                              entity_id: Optional[str] = None,
                              can_backdate: bool = True) -> Dict[str, Any]:
    raw = [ln.model_dump() if hasattr(ln, "model_dump") else dict(ln) for ln in (payload.lines or [])]
    if len(raw) < 2:
        raise ValueError("Jurnal minimal 2 baris (debit & kredit).")
    codes = [str(l.get("account_code", "")).strip() for l in raw]
    if any(not c for c in codes):
        raise ValueError("Setiap baris harus memilih akun.")
    accounts = {a["code"]: a for a in await db.gl_accounts.find(
        {"code": {"$in": codes}, "entity_id": {"$in": [None, ""]}},
        {"_id": 0}).to_list(2000)}
    for c in codes:
        if c not in accounts:
            raise ValueError(f"Akun '{c}' tidak ditemukan.")
        if not accounts[c].get("is_postable", True):
            raise ValueError(f"Akun '{c}' adalah header — pilih akun detail (postable).")
        if accounts[c].get("is_active") is False:
            raise ValueError(f"Akun '{c}' nonaktif.")
    names = {c: accounts[c]["name"] for c in codes}
    lines = _norm_lines(raw, names)
    for l in lines:
        if l["debit"] < 0 or l["credit"] < 0:
            raise ValueError("Nilai debit/kredit tidak boleh negatif.")
        if l["debit"] > EPS and l["credit"] > EPS:
            raise ValueError("Satu baris hanya boleh debit ATAU kredit.")
        if l["debit"] <= EPS and l["credit"] <= EPS:
            raise ValueError("Setiap baris harus punya nilai debit atau kredit.")
    total_debit = round(sum(l["debit"] for l in lines), 2)
    total_credit = round(sum(l["credit"] for l in lines), 2)
    if abs(total_debit - total_credit) > EPS:
        raise ValueError(f"Jurnal tidak seimbang: debit {total_debit:,.2f} ≠ kredit {total_credit:,.2f}.")
    # FASE E-1 (E1.10) — jurnal manual masuk buku badan usaha konteks bila tak disebut.
    eid = payload.entity_id or entity_id or active_entity_or(DEFAULT_ENTITY_ID)
    number = await next_doc_number("journal_entries", "number", "JE-", entity_id=eid)
    doc = {
        "id": new_id("je"),
        "number": number,
        "date": payload.date or now_iso(),
        "description": (payload.description or "").strip() or "Jurnal manual",
        "source": "manual",
        "source_type": "manual",
        "source_id": "",
        "source_label": "Manual",
        "lines": lines,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "status": "posted",
        "entity_id": eid,
        "created_by": actor.get("name", "system"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    # FASE G-5 — jurnal manual mundur ke periode tertutup butuh jendela unlock aktif.
    plu = await enforce_closed_period_guard(
        eid, doc["date"], source_type="manual", can_backdate=can_backdate)
    if plu:
        doc["backdated_in_unlock"] = plu["id"]
    await db.journal_entries.insert_one(doc)
    await _mark_stale_closings(eid, doc["date"])
    if plu:
        from services import period_unlock_service as _pus
        await _pus.register_backdated_je(plu["id"], doc["id"])
    return safe_doc(doc)


async def list_entries(source: Optional[str] = None, account_code: Optional[str] = None,
                       status: Optional[str] = None, limit: int = 500,
                       scope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    q = _journal_query(source, account_code, status, scope)
    rows = await db.journal_entries.find(q, {"_id": 0}).sort("number", -1).to_list(limit)
    return rows


def _journal_query(source: Optional[str], account_code: Optional[str],
                   status: Optional[str], scope: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Satu tempat pembentuk filter jurnal — dipakai versi biasa MAUPUN versi paginasi,
    supaya halaman & total tidak pernah dihitung dari filter yang berbeda."""
    q: Dict[str, Any] = dict(scope or {})
    if source:
        q["source_type"] = source
    if account_code:
        q["lines.account_code"] = account_code
    if status:
        q["status"] = status
    return q


async def list_entries_paged(source: Optional[str] = None, account_code: Optional[str] = None,
                             status: Optional[str] = None, scope: Optional[Dict[str, Any]] = None,
                             page: int = 1, page_size: int = 20,
                             q: str = "") -> Dict[str, Any]:
    """P2 — satu halaman jurnal + total (kontrak {items,total,page,page_size,has_more}).

    Urutan `number` menurun dipertahankan supaya jurnal terbaru tetap di halaman 1 —
    sama seperti perilaku daftar tanpa paginasi.
    """
    from pagination import build_search, merge_query, envelope
    query = _journal_query(source, account_code, status, scope)
    if q:
        query = merge_query(query, build_search(
            q, ["number", "description", "memo", "ref_number", "source_type"]))
    total = await db.journal_entries.count_documents(query)
    rows = await (db.journal_entries.find(query, {"_id": 0})
                  .sort("number", -1)
                  .skip((page - 1) * page_size)
                  .limit(page_size)
                  .to_list(page_size))
    return envelope(rows, total, page, page_size)


async def get_entry(entry_id: str) -> Optional[Dict[str, Any]]:
    return await db.journal_entries.find_one(
        {"$or": [{"id": entry_id}, {"number": entry_id}]}, {"_id": 0})


async def void_entry(entry_id: str, actor: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    je = await db.journal_entries.find_one({"id": entry_id}, {"_id": 0})
    if not je:
        return None
    if je.get("status") == "void":
        raise ValueError("Jurnal sudah di-void.")
    if je.get("source_type") != "manual":
        raise ValueError("Hanya jurnal manual yang dapat di-void langsung (jurnal otomatis mengikuti dokumen sumber).")
    await db.journal_entries.update_one(
        {"id": entry_id},
        {"$set": {"status": "void", "voided_by": actor.get("name", "system"),
                  "voided_at": now_iso(), "updated_at": now_iso()}},
    )
    # F-9 — void jurnal dalam periode tertutup juga mengubah angka → tandai stale
    await _mark_stale_closings(je.get("entity_id", ""), je.get("date", ""))
    return await db.journal_entries.find_one({"id": entry_id}, {"_id": 0})


# ═════════════════════════════════════════════════════════════════════════════
#  AUTO-POSTING (idempotent, derived from SSOT)
# ═════════════════════════════════════════════════════════════════════════════

async def _already_posted(source_type: str, source_id: str) -> bool:
    return bool(await db.journal_entries.find_one(
        {"source_type": source_type, "source_id": source_id, "status": {"$ne": "void"}},
        {"_id": 0, "id": 1}))


# ─── Gelombang 1 F-2 — basis pengakuan pendapatan ────────────────────────────
# Pendapatan HANYA diakui saat barang terkirim (shipped+) ATAU invoice terbayar.
# Order reserved/confirmed yang belum dikirim & belum dibayar TIDAK berjurnal.
REVENUE_STATUSES = {"shipped", "partially_shipped", "done"}


def _revenue_eligible(order: Dict[str, Any]) -> bool:
    if order.get("status") in REVENUE_STATUSES:
        return True
    if order.get("payment_status") in ("paid", "paid_partial"):
        return True
    if float(order.get("paid_total", 0) or 0) > EPS:
        return True
    paid = sum(float(p.get("amount", 0) or 0) for p in (order.get("payments") or []))
    return paid > EPS


async def _revenue_date(order: Dict[str, Any]) -> str:
    """Tanggal JE = tanggal EVENT pengakuan (pengiriman/pembayaran), bukan created_at."""
    ship = await db.shipments.find_one(
        {"order_id": order.get("id")}, {"_id": 0, "created_at": 1}, sort=[("created_at", -1)])
    if ship and ship.get("created_at"):
        return ship["created_at"]
    if order.get("delivered_at"):
        return order["delivered_at"]
    pays = order.get("payments") or []
    if pays:
        last = pays[-1]
        return last.get("date") or last.get("created_at") or now_iso()
    return order.get("created_at") or now_iso()


def _balanced_pair(debit_acc: str, credit_acc: str, amount: float, desc: str) -> List[Dict[str, Any]]:
    return [
        {"account_code": debit_acc, "debit": amount, "credit": 0.0, "description": desc},
        {"account_code": credit_acc, "debit": 0.0, "credit": amount, "description": desc},
    ]


async def post_sales_order(order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pengakuan pendapatan: Dr Piutang/Kas = grand_total; Cr Pendapatan = DPP; Cr PPN Keluaran."""
    if order.get("status") in DEAD_STATUSES:
        return None
    if not _revenue_eligible(order):
        return None
    sid = order.get("id")
    if not sid or await _already_posted("sales_order", sid):
        return None
    grand = round(order_grand_total(order), 2)
    if grand <= EPS:
        return None
    ppn = round(float(order.get("ppn_amount", order.get("tax", 0)) or 0), 2)
    is_cash = order_payment_method(order) in NON_AR_METHODS
    debit_acc = ACC_KAS_BESAR if is_cash else ACC_PIUTANG
    num = order.get("number", sid)
    lines = [{"account_code": debit_acc, "debit": grand, "credit": 0.0,
              "description": f"{'Tunai' if is_cash else 'Piutang'} {num}"}]
    # F-10 — basis pendapatan = HARGA JUAL (grand − PPN), BUKAN DPP Nilai Lain (11/12).
    # DPP nilai lain hanya representasi Faktur Pajak; akuntansi memakai harga jual.
    rev = round(grand - ppn, 2)
    lines.append({"account_code": ACC_PENDAPATAN, "debit": 0.0, "credit": rev,
                  "description": f"Penjualan {num}"})
    if ppn > EPS:
        lines.append({"account_code": ACC_PPN_OUT, "debit": 0.0, "credit": ppn,
                      "description": f"PPN Keluaran {num}"})
    diff = round(grand - (rev + (ppn if ppn > EPS else 0)), 2)
    if abs(diff) > EPS:
        if diff > 0:
            lines.append({"account_code": ACC_PENDAPATAN_LAIN, "debit": 0.0, "credit": diff, "description": "Pembulatan"})
        else:
            lines.append({"account_code": ACC_PENDAPATAN_LAIN, "debit": -diff, "credit": 0.0, "description": "Pembulatan"})
    return await _insert_entry(
        lines=lines, description=f"Pengakuan penjualan {num}", date=await _revenue_date(order),
        source_type="sales_order", source_id=sid, entity_id=order.get("entity_id", ""),
        created_by="system", source_label=num)


COGS_ROLL_STATUSES = ["reserved", "committed", "picked", "packed", "in_transit_sales", "delivered"]


async def _order_item_unit_cost(order: Dict[str, Any], item: Dict[str, Any]) -> float:
    """F-7 — cost per unit untuk 1 baris order (engine costing TUNGGAL).

    Prioritas: (1) roll AKTUAL yang dialokasikan ke order (tertimbang length_initial),
    (2) snapshot cost-at-sale `item.unit_cost`, (3) WAC `costing_service` (fallback)."""
    pid = item.get("product_id", "")
    rolls = await db.inventory_rolls.find(
        {"reserved_ref.id": order.get("id"), "product_id": pid,
         "status": {"$in": COGS_ROLL_STATUSES}},
        {"_id": 0, "unit_cost": 1, "base_unit_cost": 1, "length_initial": 1}).to_list(2000)
    tot_c, tot_w = 0.0, 0.0
    for r in rolls:
        c = float(r.get("unit_cost") or r.get("base_unit_cost") or 0)
        w = float(r.get("length_initial") or 0)
        if c > 0 and w > 0:
            tot_c += c * w
            tot_w += w
    if tot_w > 0:
        return round(tot_c / tot_w, 2)
    snap = float(item.get("unit_cost") or 0)
    if snap > 0:
        return snap
    w = await costing_service.wac_for_product(pid, entity_id=order.get("entity_id") or None)
    return float(w.get("wac") or 0)


async def _avg_unit_cost(product_id: str, entity_id: str = "") -> float:
    """WAC per produk untuk COGS reversal retur (F3). Fallback 0 bila cost tak diketahui.
    Session #074 (RET-2): helper ini sebelumnya HILANG sehingga return_service.py:75
    melempar AttributeError (ditelan try/except) → Credit Note & jurnal retur tak terbentuk."""
    w = await costing_service.wac_for_product(product_id, entity_id=entity_id or None)
    return float(w.get("wac") or 0)


async def post_order_cogs(order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """F3/F-7 — HPP penjualan: Dr HPP / Cr Persediaan = Σ(qty × cost roll aktual).
    Idempotent (source_type='sales_cogs'). Skip bila cost tak diketahui (0)."""
    if order.get("status") in DEAD_STATUSES:
        return None
    if not _revenue_eligible(order):
        return None
    sid = order.get("id")
    if not sid or await _already_posted("sales_cogs", sid):
        return None
    eid = order.get("entity_id", "")
    total_cogs = 0.0
    for it in order.get("items", []):
        qty = float(it.get("base_quantity", it.get("quantity", 0)) or 0)
        if qty <= 0:
            continue
        total_cogs += qty * await _order_item_unit_cost(order, it)
    total_cogs = round(total_cogs, 2)
    if total_cogs <= EPS:
        return None
    num = order.get("number", sid)
    lines = _balanced_pair(ACC_HPP, ACC_PERSEDIAAN, total_cogs, f"HPP penjualan {num}")
    return await _insert_entry(
        lines=lines, description=f"HPP penjualan {num}", date=await _revenue_date(order),
        source_type="sales_cogs", source_id=sid, entity_id=eid,
        created_by="system", source_label=num)


# ─── M-3 — Inter-company transfer JE (at-cost) ───────────────────────────────

async def _transfer_items_value_at_cost(
    transfer: Dict[str, Any], source_entity_id: str
) -> Dict[str, Any]:
    """Hitung nilai transfer at-cost dari WAC per produk di entitas SUMBER.
    Return {total, breakdown:[{product_id, sku, name, qty, unit_cost, value}]}."""
    from services.costing_service import wac_for_product
    breakdown: List[Dict[str, Any]] = []
    total = 0.0
    for it in transfer.get("items", []) or []:
        qty = float(it.get("qty") or it.get("quantity") or 0)
        if qty <= 0:
            continue
        pid = it.get("product_id")
        if not pid:
            continue
        wac = await wac_for_product(pid, entity_id=source_entity_id, use_cache=False)
        unit_cost = float(wac.get("wac") or 0)
        value = round(qty * unit_cost, 2)
        breakdown.append({
            "product_id": pid, "sku": it.get("sku", "") or wac.get("sku", ""),
            "name": it.get("product_name", "") or wac.get("name", ""),
            "qty": round(qty, 2), "unit_cost": round(unit_cost, 2), "value": value,
            "cost_source": wac.get("source", "none"),
        })
        total += value
    return {"total": round(total, 2), "breakdown": breakdown}


async def post_intercompany_transfer(transfer: Dict[str, Any]) -> Dict[str, Any]:
    """M-3 — Posting JE saat kepemilikan roll berpindah antar-PT (at-cost).

    Konservatif (no IC profit sampai barang dijual ke external): senilai WAC-cost
    di entitas SUMBER.

    Buku B (source):  Dr `1-1250` IC-AR         / Cr `1-1300` Persediaan
    Buku E (dest):    Dr `1-1300` Persediaan    / Cr `2-1250` IC-AP

    Idempotent via source_type='inter_company_transfer' + source_id=transfer_id
    (dicek terpisah untuk sisi src dan dst via source_label suffix ':src' / ':dst').

    Jika total cost = 0 (barang tak ber-cost di source), JE dilewati dan return
    metadata dengan `posted=False` — bukan error.
    """
    tid = transfer.get("id")
    src = transfer.get("source_entity_id")
    dst = transfer.get("dest_entity_id")
    if not (tid and src and dst) or src == dst:
        return {"posted": False, "reason": "invalid_transfer", "total": 0.0}

    # Idempotent guard (cek dua-sisi terpisah)
    src_id = f"{tid}:src"
    dst_id = f"{tid}:dst"
    if await _already_posted("inter_company_transfer", src_id) or \
       await _already_posted("inter_company_transfer", dst_id):
        return {"posted": False, "reason": "already_posted", "total": 0.0}

    valuation = await _transfer_items_value_at_cost(transfer, src)
    total = float(valuation["total"])
    if total <= EPS:
        return {"posted": False, "reason": "zero_cost", "total": 0.0,
                "breakdown": valuation["breakdown"]}

    code = transfer.get("code") or tid
    pair_id = f"ict_{tid}"
    date = transfer.get("approved_at") or transfer.get("updated_at") or now_iso()
    desc_src = f"Transfer antar-PT {code} → {dst} (at-cost)"
    desc_dst = f"Transfer antar-PT {code} ← {src} (at-cost)"

    # Buku SOURCE: Dr IC-AR / Cr Persediaan
    lines_src = _balanced_pair(ACC_IC_AR, ACC_PERSEDIAAN, total, desc_src)
    je_src = await _insert_entry(
        lines=lines_src, description=desc_src, date=date,
        source_type="inter_company_transfer", source_id=src_id, entity_id=src,
        created_by="system", source_label=code,
    )
    # Buku DEST: Dr Persediaan / Cr IC-AP
    lines_dst = _balanced_pair(ACC_PERSEDIAAN, ACC_IC_AP, total, desc_dst)
    je_dst = await _insert_entry(
        lines=lines_dst, description=desc_dst, date=date,
        source_type="inter_company_transfer", source_id=dst_id, entity_id=dst,
        created_by="system", source_label=code,
    )

    # Tautkan pair (untuk audit/konsolidasi). Set pair_id sekaligus + counterpart
    # per-baris dalam DUA update_one terpisah (src.counterpart=dst, dst.counterpart=src).
    await db.journal_entries.update_one(
        {"id": je_src["id"]},
        {"$set": {"intercompany_pair_id": pair_id,
                  "intercompany_counterpart_entity_id": dst,
                  "updated_at": now_iso()}},
    )
    await db.journal_entries.update_one(
        {"id": je_dst["id"]},
        {"$set": {"intercompany_pair_id": pair_id,
                  "intercompany_counterpart_entity_id": src,
                  "updated_at": now_iso()}},
    )

    return {
        "posted": True, "total": total, "pair_id": pair_id,
        "source_je": {"id": je_src["id"], "number": je_src["number"], "entity_id": src},
        "dest_je": {"id": je_dst["id"], "number": je_dst["number"], "entity_id": dst},
        "breakdown": valuation["breakdown"],
    }


# ─── F-8 — Suspense (1-9999): laporan, saldo, reklasifikasi ──────────────────

async def suspense_report(scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Saldo & daftar jurnal yang menyentuh akun Suspense (wajib nol sebelum tutup buku)."""
    q = {**(scope or {}), "status": {"$ne": "void"}, "lines.account_code": ACC_SUSPENSE}
    entries = await db.journal_entries.find(q, {"_id": 0}).sort("date", -1).to_list(2000)
    balance = 0.0
    items: List[Dict[str, Any]] = []
    for je in entries:
        d = c = 0.0
        for l in je.get("lines", []):
            if l.get("account_code") == ACC_SUSPENSE:
                d += float(l.get("debit", 0) or 0)
                c += float(l.get("credit", 0) or 0)
        balance += d - c
        items.append({"id": je["id"], "number": je.get("number", ""), "date": je.get("date", ""),
                      "description": je.get("description", ""), "source_type": je.get("source_type", ""),
                      "source_label": je.get("source_label", ""), "entity_id": je.get("entity_id", ""),
                      "suspense_debit": round(d, 2), "suspense_credit": round(c, 2)})
    return {"account_code": ACC_SUSPENSE, "account_name": "Suspense (Sementara)",
            "balance": round(balance, 2), "entry_count": len(items), "items": items}


async def suspense_balance(entity_id: str, as_of: str = "") -> float:
    """Saldo bersih (debit − kredit) akun Suspense per entitas s/d tanggal `as_of`."""
    q: Dict[str, Any] = {"entity_id": entity_id, "status": {"$ne": "void"},
                         "lines.account_code": ACC_SUSPENSE}
    if as_of:
        q["date"] = {"$lte": as_of[:10] + "T23:59:59.9999"}
    bal = 0.0
    async for je in db.journal_entries.find(q, {"_id": 0, "lines": 1}):
        for l in je.get("lines", []):
            if l.get("account_code") == ACC_SUSPENSE:
                bal += float(l.get("debit", 0) or 0) - float(l.get("credit", 0) or 0)
    return round(bal, 2)


async def reclass_suspense(*, amount: float, side: str, target_account: str, note: str,
                           entity_id: str, actor_name: str) -> Dict[str, Any]:
    """F-8 — reklasifikasi saldo suspense ke akun yang benar (JE source suspense_reclass).

    side = posisi saldo suspense SAAT INI yang mau dibersihkan:
    'credit' (kas masuk tak dikenal) → Dr Suspense / Cr target; 'debit' → sebaliknya."""
    amount = round(float(amount or 0), 2)
    if amount <= 0:
        raise ValueError("Nominal reklasifikasi harus lebih dari 0.")
    if side not in ("debit", "credit"):
        raise ValueError("side harus 'debit' atau 'credit'.")
    if target_account == ACC_SUSPENSE:
        raise ValueError("Akun tujuan tidak boleh akun suspense itu sendiri.")
    acc = await db.gl_accounts.find_one(
        {"code": target_account, "entity_id": {"$in": [None, ""]}}, {"_id": 0})
    if not acc:
        raise ValueError(f"Akun '{target_account}' tidak ditemukan.")
    if not acc.get("is_postable", True):
        raise ValueError(f"Akun '{target_account}' adalah header — pilih akun detail (postable).")
    desc = (note or "").strip() or "Reklasifikasi saldo suspense"
    if side == "credit":
        lines = [{"account_code": ACC_SUSPENSE, "debit": amount, "credit": 0.0, "description": desc},
                 {"account_code": target_account, "debit": 0.0, "credit": amount, "description": desc}]
    else:
        lines = [{"account_code": target_account, "debit": amount, "credit": 0.0, "description": desc},
                 {"account_code": ACC_SUSPENSE, "debit": 0.0, "credit": amount, "description": desc}]
    return await _insert_entry(
        lines=lines, description=f"Reklas suspense → {target_account} · {desc}",
        date=now_iso(), source_type="suspense_reclass", source_id=new_id("reclass"),
        entity_id=entity_id, created_by=actor_name, source_label="Suspense")


async def reverse_order_journals(order_id: str, reason: str = "",
                                 actor_name: str = "system") -> List[Dict[str, Any]]:
    """Gelombang 1 F-1 — jurnal balik otomatis saat order batal/expired (audit trail utuh)."""
    out: List[Dict[str, Any]] = []
    entries = await db.journal_entries.find(
        {"source_id": order_id, "source_type": {"$in": ["sales_order", "sales_cogs"]},
         "status": {"$ne": "void"}}, {"_id": 0}).to_list(20)
    for je in entries:
        rev_type = f"{je['source_type']}_reversal"
        if await _already_posted(rev_type, order_id):
            continue
        lines = [{"account_code": l["account_code"],
                  "debit": float(l.get("credit", 0) or 0),
                  "credit": float(l.get("debit", 0) or 0),
                  "description": f"Reversal: {l.get('description', '')}".strip()}
                 for l in je.get("lines", [])]
        rev = await _insert_entry(
            lines=lines,
            description=f"Reversal {je.get('number')} — {reason or 'order dibatalkan'}",
            date=now_iso(), source_type=rev_type, source_id=order_id,
            entity_id=je.get("entity_id", ""), created_by=actor_name,
            source_label=je.get("source_label", ""))
        await db.journal_entries.update_one(
            {"id": je["id"]},
            {"$set": {"reversed": True, "reversed_at": now_iso(),
                      "reversal_id": rev["id"], "updated_at": now_iso()}})
        out.append(rev)
    return out


async def reverse_document(source_type: str, source_id: str, *, reason: str = "",
                           actor_name: str = "system",
                           extra_source_types: Optional[List[str]] = None,
                           rev_suffix: str = "_reversal",
                           date: str = "") -> List[Dict[str, Any]]:
    """R5.4 — Reversal generik: balik SEMUA JE non-void utk (source_type[+extra], source_id)
    dengan reversing entry (Dr↔Cr). Append-only (JE asal tetap 'posted', ditandai reversed=True)
    agar audit trail utuh. Idempotent per (f'{type}{rev_suffix}', source_id).

    Dipakai R5.4 untuk membatalkan settle retur, redeem/adjust store credit, dll. tanpa
    menghapus data — trial balance otomatis nol (asal + reversal saling meniadakan)."""
    out: List[Dict[str, Any]] = []
    if not source_id:
        return out
    types = [source_type] + list(extra_source_types or [])
    entries = await db.journal_entries.find(
        {"source_id": source_id, "source_type": {"$in": types}, "status": {"$ne": "void"}},
        {"_id": 0}).to_list(50)
    for je in entries:
        rev_type = f"{je['source_type']}{rev_suffix}"
        if await _already_posted(rev_type, source_id):
            # sudah pernah dibalik — kumpulkan JE reversal-nya utk info (idempotent).
            prior = await db.journal_entries.find_one(
                {"source_type": rev_type, "source_id": source_id, "status": {"$ne": "void"}}, {"_id": 0})
            if prior:
                out.append(prior)
            continue
        lines = [{"account_code": l["account_code"],
                  "debit": float(l.get("credit", 0) or 0),
                  "credit": float(l.get("debit", 0) or 0),
                  "description": f"Reversal: {l.get('description', '')}".strip()}
                 for l in je.get("lines", [])]
        rev = await _insert_entry(
            lines=lines,
            description=f"Reversal {je.get('number')} — {reason or 'koreksi/pembatalan'}",
            date=date or now_iso(), source_type=rev_type, source_id=source_id,
            entity_id=je.get("entity_id", ""), created_by=actor_name,
            source_label=je.get("source_label", ""))
        await db.journal_entries.update_one(
            {"id": je["id"]},
            {"$set": {"reversed": True, "reversed_at": now_iso(),
                      "reversal_id": rev["id"], "reversal_reason": reason,
                      "updated_at": now_iso()}})
        out.append(rev)
    return out


async def post_goods_receipt(*, task_id: str, entity_id: str, amount: float,
                             label: str = "", date: str = "") -> Optional[Dict[str, Any]]:
    """Gelombang 1 F-3 — GR → GL: Dr Persediaan / Cr GR-IR (barang diterima belum ditagih)."""
    amount = round(float(amount or 0), 2)
    if amount <= EPS or not task_id or await _already_posted("goods_receipt", task_id):
        return None
    await seed_default_coa()
    lines = _balanced_pair(ACC_PERSEDIAAN, ACC_GRIR, amount, f"Penerimaan barang {label}".strip())
    return await _insert_entry(
        lines=lines, description=f"Goods Receipt {label}".strip(), date=date or now_iso(),
        source_type="goods_receipt", source_id=task_id, entity_id=entity_id,
        created_by="system", source_label=label)


# ── M2 (Makloon/Subcon) — WIP-at-vendor postings ─────────────────────────────

async def post_subcon_issue(*, mko_id: str, step_seq: int, entity_id: str,
                            amount: float, label: str = "", date: str = "") -> Optional[Dict[str, Any]]:
    """M2 — Keluarkan bahan KN ke makloon: Dr WIP (1-1350) / Cr Persediaan (1-1300).
    Nilai = WAC bahan yang di-issue. Idempotent per (mko,step)."""
    amount = round(float(amount or 0), 2)
    src = f"{mko_id}:{step_seq}"
    if amount <= EPS or not mko_id or await _already_posted("subcon_issue", src):
        return None
    await seed_default_coa()
    lines = _balanced_pair(ACC_WIP_SUBCON, ACC_PERSEDIAAN, amount,
                           f"Issue bahan ke makloon {label}".strip())
    return await _insert_entry(
        lines=lines, description=f"Subcon Issue {label}".strip(), date=date or now_iso(),
        source_type="subcon_issue", source_id=src, entity_id=entity_id,
        created_by="system", source_label=label)


async def post_subcon_service(*, bill_id: str, mko_id: str, step_seq: int, entity_id: str,
                              net_amount: float, ppn: float = 0.0, grand_total: float = 0.0,
                              makloon_name: str = "", label: str = "", date: str = "") -> Optional[Dict[str, Any]]:
    """M2 — Tagihan JASA makloon (posted): Dr WIP (net) + Dr PPN Masukan / Cr Hutang Usaha.
    Ongkos jasa+bahan pembantu ditambahkan ke WIP (biaya konversi). Idempotent per bill."""
    net_amount = round(float(net_amount or 0), 2)
    ppn = round(float(ppn or 0), 2)
    grand = round(float(grand_total or (net_amount + ppn)), 2)
    if grand <= EPS or not bill_id or await _already_posted("subcon_service", bill_id):
        return None
    await seed_default_coa()
    lines: List[Dict[str, Any]] = [
        {"account_code": ACC_WIP_SUBCON, "debit": net_amount, "credit": 0.0,
         "description": f"Ongkos makloon {label}".strip()}]
    if ppn > EPS:
        lines.append({"account_code": ACC_PPN_IN, "debit": ppn, "credit": 0.0,
                      "description": f"PPN Masukan jasa makloon {label}".strip()})
    diff = round(grand - net_amount - (ppn if ppn > EPS else 0), 2)
    if abs(diff) > EPS:
        acc = ACC_SUSPENSE
        if diff > 0:
            lines.append({"account_code": acc, "debit": diff, "credit": 0.0, "description": "Selisih pembulatan"})
        else:
            lines.append({"account_code": acc, "debit": 0.0, "credit": -diff, "description": "Selisih pembulatan"})
    lines.append({"account_code": ACC_HUTANG, "debit": 0.0, "credit": grand,
                  "description": f"Hutang jasa makloon — {makloon_name}".strip()})
    return await _insert_entry(
        lines=lines, description=f"Tagihan Jasa Makloon {label}".strip(), date=date or now_iso(),
        source_type="subcon_service", source_id=bill_id, entity_id=entity_id,
        created_by="system", source_label=label)


async def post_subcon_receipt(*, mko_id: str, step_seq: int, entity_id: str,
                              amount: float, label: str = "", date: str = "") -> Optional[Dict[str, Any]]:
    """M2 — Terima output makloon: Dr Persediaan (1-1300) / Cr WIP (1-1350).
    `amount` = total nilai WIP yang di-clear (material + jasa + aux) → jadi HPP output.
    Byproduct/barang sisa dinilai 0 (metode conservative) → tak menambah 1-1300 di luar
    subledger (anti-drift). Idempotent per (mko,step)."""
    amount = round(float(amount or 0), 2)
    src = f"{mko_id}:{step_seq}"
    if amount <= EPS or not mko_id or await _already_posted("subcon_receipt", src):
        return None
    await seed_default_coa()
    lines = _balanced_pair(ACC_PERSEDIAAN, ACC_WIP_SUBCON, amount,
                           f"Terima output makloon {label}".strip())
    return await _insert_entry(
        lines=lines, description=f"Subcon Receipt {label}".strip(), date=date or now_iso(),
        source_type="subcon_receipt", source_id=src, entity_id=entity_id,
        created_by="system", source_label=label)


async def post_subcon_service_unabsorbed(*, mko_id: str, entity_id: str, amount: float,
                                        label: str = "", date: str = "") -> Optional[Dict[str, Any]]:
    """FASE T — bersihkan WIP jasa "jasa murni" yang tak menempel ke kain mana pun.

    Langkah ber-`material_flow="service_only"` (mis. pembuatan kasa/screen) tidak
    memindahkan kain, jadi tidak ada penerimaan roll yang meng-clear WIP-nya.
    Biayanya **diserap langkah kain berikutnya** di SPK yang sama (`receive_step`
    menambahkannya ke `wip_total`). Bila SPK habis tanpa langkah kain — mis. SPK
    berisi Screen saja — sisanya WAJIB keluar dari WIP, kalau tidak saldo 1-1350
    membesar tanpa penjelasan dan `verify_data_integrity` akan melaporkan drift
    yang tak ada pemiliknya.

        Dr 5-1200 Beban Jasa Makloon Tak Terserap / Cr 1-1350 WIP Makloon

    Idempotent per order (satu SPK = satu pembersihan).
    """
    amount = round(float(amount or 0), 2)
    src = f"{mko_id}:service_unabsorbed"
    if amount <= EPS or not mko_id or await _already_posted("subcon_service_unabsorbed", src):
        return None
    await seed_default_coa()
    lines = _balanced_pair(ACC_JASA_TAK_TERSERAP, ACC_WIP_SUBCON, amount,
                           f"Jasa makloon tanpa kain penyerap {label}".strip())
    return await _insert_entry(
        lines=lines, description=f"Jasa Makloon Tak Terserap {label}".strip(),
        date=date or now_iso(), source_type="subcon_service_unabsorbed", source_id=src,
        entity_id=entity_id, created_by="system", source_label=label)


async def post_makloon_claim(*, mko_id: str, step_seq: int, entity_id: str, action: str,                             amount: float, label: str = "",
                             date: str = "") -> Optional[Dict[str, Any]]:
    """FASE D (PS-11 · D-09) — jurnal konsekuensi selisih makloon. Idempotent per (mko,step).

    * `potong_bon`  → Dr Hutang Usaha (2-1100) / Cr Pendapatan Klaim Makloon (4-9200):
      tagihan jasa mitra dipotong; utang berkurang, subledger vendor_bill ikut dikurangi
      oleh `makloon_claim_service` sehingga AP tetap rekonsiliasi.
    * `tagih_ganti` → Dr Piutang Klaim Mitra (1-1260) / Cr Pendapatan Klaim Makloon (4-9200).
    * `terima_catatan` → TIDAK ada jurnal: kerugian sudah terserap ke HPP output saat
      penerimaan (WIP di-clear penuh ke persediaan) — mencegah dobel-hitung & drift 1-1300.
    """
    amount = round(float(amount or 0), 2)
    src = f"{mko_id}:{step_seq}"
    if action == "terima_catatan":
        return None
    if amount <= EPS or not mko_id or await _already_posted("makloon_claim", src):
        return None
    if action == "potong_bon":
        debit, credit = ACC_HUTANG, ACC_KLAIM_MAKLOON
        desc = f"Potong bon klaim makloon {label}".strip()
    elif action == "tagih_ganti":
        debit, credit = ACC_PIUTANG_KLAIM, ACC_KLAIM_MAKLOON
        desc = f"Tagih ganti rugi mitra makloon {label}".strip()
    else:
        return None
    await seed_default_coa()
    lines = _balanced_pair(debit, credit, amount, desc)
    return await _insert_entry(
        lines=lines, description=desc, date=date or now_iso(),
        source_type="makloon_claim", source_id=src, entity_id=entity_id,
        created_by="system", source_label=label)


async def post_contra_bon_deduction(*, cb_id: str, deduction_id: str, entity_id: str,
                                    kind: str, amount: float, label: str = "",
                                    date: str = "") -> Optional[Dict[str, Any]]:
    """FASE G-7 — jurnal POTONGAN kontrabon. Idempotent per (kontrabon, potongan).

    Lawan akun per jenis potongan:
      * `supplier_advance` → Dr 2-1100 Hutang / Cr 1-1400 Uang Muka (aset dipakai)
      * `supplier_penalty` → Dr 2-1100 Hutang / Cr 4-9300 Pendapatan Denda
      * `match_variance`   → Dr 2-1100 Hutang / Cr 2-1150 GR/IR (barangnya memang tak diterima)
      * `other_agreed`     → Dr 2-1100 Hutang / Cr 4-9000 Pendapatan Lain-lain

    **`purchase_return` SENGAJA TIDAK ADA di sini.** Retur beli `ap_credit` sudah
    memposting `Dr 2-1100 / Cr 1-1300` saat retur disetujui; menjurnalnya lagi akan
    mengurangi Hutang DUA KALI. Di kontrabon ia hanya diterapkan sebagai pelunasan
    non-kas pada subledger `vendor_bills` — justru itu yang menutup drift GL↔subledger.
    """
    credit_by_kind = {
        "supplier_advance": ACC_UANG_MUKA,
        "supplier_penalty": ACC_PENDAPATAN_DENDA,
        "match_variance": ACC_GRIR,
        "other_agreed": ACC_PENDAPATAN_LAIN,
    }
    credit = credit_by_kind.get(kind)
    amount = round(float(amount or 0), 2)
    src = f"{cb_id}:{deduction_id}"
    if not credit or amount <= EPS or await _already_posted("contra_bon_deduction", src):
        return None
    await seed_default_coa()
    desc = f"Potongan kontrabon {label}".strip()
    lines = _balanced_pair(ACC_HUTANG, credit, amount, desc)
    return await _insert_entry(
        lines=lines, description=desc, date=date or now_iso(),
        source_type="contra_bon_deduction", source_id=src, entity_id=entity_id,
        created_by="system", source_label=label)


async def post_production_output(*, wo_id: str, entity_id: str, overhead: float,
                                 label: str = "", date: str = "") -> Optional[Dict[str, Any]]:
    """R6.4 — Produksi in-house: kapitalisasi OVERHEAD ke Persediaan Barang Jadi.
    Transformasi bahan→barang jadi memakai akun Persediaan 1-1300 yang sama (raw==FG),
    sehingga porsi bahan NET-0 di GL (subledger roll sudah menyeimbangkan). Hanya OVERHEAD
    yang menambah nilai persediaan: Dr 1-1300 / Cr 5-1100 (Overhead Diserap). Idempotent per WO.
    Bila overhead<=0 → tak ada jurnal (GL-3 tetap konsisten dari transformasi roll)."""
    overhead = round(float(overhead or 0), 2)
    if overhead <= EPS or not wo_id or await _already_posted("production_output", wo_id):
        return None
    await seed_default_coa()
    lines = _balanced_pair(ACC_PERSEDIAAN, ACC_OVERHEAD_APPLIED, overhead,
                           f"Kapitalisasi overhead produksi {label}".strip())
    return await _insert_entry(
        lines=lines, description=f"Produksi WO {label}".strip(), date=date or now_iso(),
        source_type="production_output", source_id=wo_id, entity_id=entity_id,
        created_by="system", source_label=label)


async def reverse_subcon_issue(*, mko_id: str, step_seq: int, entity_id: str,
                               amount: float, label: str = "") -> Optional[Dict[str, Any]]:
    """M2 — Batalkan issue bahan (step belum diterima): Dr Persediaan / Cr WIP.
    Mengembalikan nilai WIP ke Persediaan saat order/step dibatalkan. Idempotent."""
    amount = round(float(amount or 0), 2)
    src = f"{mko_id}:{step_seq}"
    if amount <= EPS or not mko_id or await _already_posted("subcon_issue_reversal", src):
        return None
    await seed_default_coa()
    lines = _balanced_pair(ACC_PERSEDIAAN, ACC_WIP_SUBCON, amount,
                           f"Batal issue makloon {label}".strip())
    return await _insert_entry(
        lines=lines, description=f"Subcon Issue Reversal {label}".strip(), date=now_iso(),
        source_type="subcon_issue_reversal", source_id=src, entity_id=entity_id,
        created_by="system", source_label=label)


async def post_vendor_bill(bill: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Gelombang 1 F-5 — Vendor Bill posted → Dr GR-IR + Dr PPN Masukan / Cr Hutang Usaha."""
    bid = bill.get("id")
    if not bid or bill.get("status") not in ("posted", "paid"):
        return None
    if await _already_posted("vendor_bill", bid):
        return None
    grand = round(float(bill.get("grand_total", bill.get("total_amount", 0)) or 0), 2)
    if grand <= EPS:
        return None
    await seed_default_coa()
    ppn = round(float(bill.get("ppn_amount", 0) or 0), 2)
    # F-10 — basis biaya/GRIR = harga beli neto (grand − PPN), BUKAN DPP Nilai Lain (11/12)
    net = round(grand - ppn, 2)
    num = bill.get("bill_number", bid)
    lines: List[Dict[str, Any]] = [
        {"account_code": ACC_GRIR, "debit": net, "credit": 0.0,
         "description": f"Tagihan supplier {num}"}]
    if ppn > EPS:
        lines.append({"account_code": ACC_PPN_IN, "debit": ppn, "credit": 0.0,
                      "description": f"PPN Masukan {num}"})
    diff = round(grand - net - (ppn if ppn > EPS else 0), 2)
    if abs(diff) > EPS:
        if diff > 0:
            lines.append({"account_code": ACC_SUSPENSE, "debit": diff, "credit": 0.0,
                          "description": "Selisih pembulatan"})
        else:
            lines.append({"account_code": ACC_SUSPENSE, "debit": 0.0, "credit": -diff,
                          "description": "Selisih pembulatan"})
    lines.append({"account_code": ACC_HUTANG, "debit": 0.0, "credit": grand,
                  "description": f"Hutang usaha {num} — {bill.get('supplier_name', '')}".strip()})
    return await _insert_entry(
        lines=lines, description=f"Vendor Bill {num}",
        date=bill.get("posted_at") or bill.get("bill_date") or now_iso(),
        source_type="vendor_bill", source_id=bid, entity_id=bill.get("entity_id", ""),
        created_by="system", source_label=num)


async def reverse_vendor_bill(bill: Dict[str, Any], reason: str = "",
                              actor_name: str = "system") -> Optional[Dict[str, Any]]:
    """Session #074 (VB-CANCEL-GL) — balik jurnal Vendor Bill saat bill posted dibatalkan.
    Idempotent (source_type='vendor_bill_reversal'). Membalik Dr↔Cr dari JE vendor_bill."""
    bid = bill.get("id")
    if not bid or await _already_posted("vendor_bill_reversal", bid):
        return None
    je = await db.journal_entries.find_one(
        {"source_type": "vendor_bill", "source_id": bid, "status": {"$ne": "void"}}, {"_id": 0})
    if not je:
        return None
    lines = [{"account_code": l["account_code"],
              "debit": float(l.get("credit", 0) or 0),
              "credit": float(l.get("debit", 0) or 0),
              "description": f"Reversal: {l.get('description', '')}".strip()}
             for l in je.get("lines", [])]
    rev = await _insert_entry(
        lines=lines,
        description=f"Reversal {je.get('number')} — {reason or 'bill dibatalkan'}",
        date=now_iso(), source_type="vendor_bill_reversal", source_id=bid,
        entity_id=je.get("entity_id", ""), created_by=actor_name,
        source_label=je.get("source_label", ""))
    await db.journal_entries.update_one(
        {"id": je["id"]},
        {"$set": {"reversed": True, "reversed_at": now_iso(),
                  "reversal_id": rev["id"], "updated_at": now_iso()}})
    return rev

async def post_inventory_writeoff(*, roll_id: str, entity_id: str, amount: float,
                                  reason: str = "", label: str = "",
                                  date: str = "", source_id: str = "") -> Optional[Dict[str, Any]]:
    """R5.1 — Write-off / penghapusan persediaan (scrap & goods) → GL.
      Dr 5-9500 Beban Kerugian/Penghapusan Persediaan / Cr 1-1300 Persediaan.
    Dipanggil saat roll keluar dari subledger fisik menjadi 'damaged' (scrap) tanpa
    lawan-akun lain, agar GL 1-1300 turun sejalan subledger (anti INV-GL-DRIFT).
    Idempotent (source_type='inventory_writeoff', source_id=roll_id by default).
    `amount` = length_remaining * unit_cost roll yang di-scrap."""
    amount = round(float(amount or 0), 2)
    sid = source_id or roll_id
    if not sid or amount <= EPS or await _already_posted("inventory_writeoff", sid):
        return None
    await seed_default_coa()
    lbl = label or roll_id or sid
    rtxt = f" · {reason}" if reason else ""
    lines = [
        {"account_code": ACC_WRITEOFF, "debit": amount, "credit": 0.0,
         "description": f"Write-off persediaan {lbl}{rtxt}"},
        {"account_code": ACC_PERSEDIAAN, "debit": 0.0, "credit": amount,
         "description": f"Penghapusan stok {lbl}"},
    ]
    return await _insert_entry(
        lines=lines, description=f"Write-off persediaan {lbl}",
        date=date or now_iso(), source_type="inventory_writeoff",
        source_id=sid, entity_id=entity_id or "", created_by="system", source_label=lbl)


async def post_sample_material_issue(*, movement_id: str, entity_id: str, amount: float,
                                     label: str = "", note: str = "",
                                     date: str = "",
                                     created_by: str = "system") -> Optional[Dict[str, Any]]:
    """FASE F — Bahan yang dipakai MEMBUAT SAMPLE keluar dari persediaan → GL.
      Dr 6-7000 Beban Sample & Pengembangan (R&D) / Cr 1-1300 Persediaan.

    Tanpa jurnal ini nilai persediaan turun di subledger (roll berkurang) tetapi GL
    1-1300 tidak — memunculkan drift INV-GL-DRIFT (uang "hilang" tanpa jejak beban).
    Idempotent per `movement_id` (source_type='rnd_sample_issue')."""
    amount = round(float(amount or 0), 2)
    if not movement_id or amount <= EPS or await _already_posted("rnd_sample_issue", movement_id):
        return None
    await seed_default_coa()
    lbl = label or movement_id
    ntxt = f" · {note}" if note else ""
    lines = [
        {"account_code": ACC_BEBAN_RND, "debit": amount, "credit": 0.0,
         "description": f"Bahan sample {lbl}{ntxt}"},
        {"account_code": ACC_PERSEDIAAN, "debit": 0.0, "credit": amount,
         "description": f"Bahan keluar gudang untuk sample {lbl}"},
    ]
    return await _insert_entry(
        lines=lines, description=f"Pengambilan bahan sample {lbl}",
        date=date or now_iso(), source_type="rnd_sample_issue",
        source_id=movement_id, entity_id=entity_id or "", created_by=created_by or "system",
        source_label=lbl)


async def post_penalty_issue(*, penalty_id: str, entity_id: str, amount: float,
                             label: str = "", date: str = "",
                             created_by: str = "system") -> Optional[Dict[str, Any]]:
    """FASE G-2 — Terbitkan denda keterlambatan:
      Dr 1-1270 Piutang Denda Pelanggan / Cr 4-9300 Pendapatan Denda Keterlambatan.

    Denda berstatus `draft` SENGAJA tidak pernah lewat sini (INV-PEN-01): itulah yang
    membuat denda bisa dinegosiasikan tanpa mengotori buku besar. Idempotent per
    (`penalty`, penalty_id).
    """
    amount = round(float(amount or 0), 2)
    if not penalty_id or amount <= EPS or await _already_posted("penalty", penalty_id):
        return None
    await seed_default_coa()
    lbl = label or penalty_id
    lines = _balanced_pair(ACC_PIUTANG_DENDA, ACC_PENDAPATAN_DENDA, amount,
                           f"Denda keterlambatan {lbl}")
    return await _insert_entry(
        lines=lines, description=f"Denda keterlambatan {lbl}", date=date or now_iso(),
        source_type="penalty", source_id=penalty_id, entity_id=entity_id or "",
        created_by=created_by, source_label=lbl)


async def post_penalty_reversal(*, penalty_id: str, entity_id: str, amount: float,
                                label: str = "", date: str = "", created_by: str = "system",
                                suffix: str = "waive") -> Optional[Dict[str, Any]]:
    """FASE G-2 — Pembebasan / penyesuaian denda yang SUDAH terbit → jurnal PEMBALIK:
      Dr 4-9300 Pendapatan Denda / Cr 1-1270 Piutang Denda.

    Ledger append-only (aturan repo #7): jurnal lama TIDAK diubah/dihapus; koreksi
    selalu berupa jurnal baru yang bisa dibaca auditor. `suffix` memisahkan pembebasan
    dari penyesuaian sehingga keduanya bisa terjadi berurutan tanpa saling menimpa.
    """
    amount = round(float(amount or 0), 2)
    sid = f"{penalty_id}:{suffix}"
    if not penalty_id or amount <= EPS or await _already_posted("penalty_reversal", sid):
        return None
    await seed_default_coa()
    lbl = label or penalty_id
    lines = _balanced_pair(ACC_PENDAPATAN_DENDA, ACC_PIUTANG_DENDA, amount, lbl)
    return await _insert_entry(
        lines=lines, description=lbl, date=date or now_iso(),
        source_type="penalty_reversal", source_id=sid, entity_id=entity_id or "",
        created_by=created_by, source_label=penalty_id)


async def post_penalty_payment(*, penalty_id: str, entity_id: str, amount: float,
                               method: str = "transfer", label: str = "", date: str = "",
                               created_by: str = "system") -> Optional[Dict[str, Any]]:
    """FASE G-2 — Pembayaran denda oleh pelanggan:
      Dr Kas/Bank (atau Kas Kecil untuk tunai) / Cr 1-1270 Piutang Denda.
    """
    amount = round(float(amount or 0), 2)
    sid = f"{penalty_id}:pay"
    if not penalty_id or amount <= EPS or await _already_posted("penalty_payment", sid):
        return None
    await seed_default_coa()
    cash_acc = ACC_KAS_KECIL if (method or "").lower() in ("tunai", "cash") else ACC_KAS_BESAR
    lbl = label or f"Pembayaran denda {penalty_id}"
    lines = _balanced_pair(cash_acc, ACC_PIUTANG_DENDA, amount, lbl)
    return await _insert_entry(
        lines=lines, description=lbl, date=date or now_iso(),
        source_type="penalty_payment", source_id=sid, entity_id=entity_id or "",
        created_by=created_by, source_label=penalty_id)


async def penalty_receivable_balance(entity_id: str = "") -> float:
    """Saldo akun 1-1270 (Piutang Denda) dari jurnal — bahan INV-PEN-03."""
    flt: Dict[str, Any] = {"status": {"$ne": "void"}, "lines.account_code": ACC_PIUTANG_DENDA}
    if entity_id and entity_id != "all":
        flt["entity_id"] = entity_id
    total = 0.0
    async for je in db.journal_entries.find(flt, {"_id": 0, "lines": 1}):
        for ln in je.get("lines") or []:
            if ln.get("account_code") == ACC_PIUTANG_DENDA:
                total += float(ln.get("debit") or 0) - float(ln.get("credit") or 0)
    return round(total, 2)


# ── FASE G-3 — Selisih pembayaran (lebih / kurang bayar) ────────────────────
async def post_variance_writeoff(*, decision_id: str, entity_id: str, amount: float,
                                 label: str = "", date: str = "",
                                 created_by: str = "system") -> Optional[Dict[str, Any]]:
    """FASE G-3 — Sisa KURANG bayar yang diputus dihapus (termasuk pembulatan otomatis):
      Dr 6-9100 Beban Selisih Pembayaran Pelanggan / Cr 1-1200 Piutang Usaha.

    Piutangnya benar-benar hilang dari buku (bukan hanya ditandai lunas di dokumen),
    sehingga subledger pesanan dan saldo Piutang di GL tetap bercerita sama.
    Idempotent per (`payment_variance_writeoff`, decision_id).
    """
    amount = round(float(amount or 0), 2)
    if not decision_id or amount <= EPS or await _already_posted(
            "payment_variance_writeoff", decision_id):
        return None
    await seed_default_coa()
    lbl = label or decision_id
    lines = _balanced_pair(ACC_SELISIH_BAYAR, ACC_PIUTANG, amount,
                           f"Selisih kurang bayar {lbl}")
    return await _insert_entry(
        lines=lines, description=f"Selisih kurang bayar dihapus · {lbl}",
        date=date or now_iso(), source_type="payment_variance_writeoff",
        source_id=decision_id, entity_id=entity_id or "", created_by=created_by,
        source_label=lbl)


async def post_ap_variance_writeoff(*, decision_id: str, entity_id: str, amount: float,
                                    label: str = "", date: str = "",
                                    created_by: str = "system") -> Optional[Dict[str, Any]]:
    """FASE G-3 (jalur AP) — Sisa hutang supplier yang diputus tidak dibayar:
      Dr 2-1100 Hutang Usaha / Cr 4-9000 Pendapatan Lain-lain (potongan dari supplier).

    Idempotent per (`ap_variance_writeoff`, decision_id).
    """
    amount = round(float(amount or 0), 2)
    if not decision_id or amount <= EPS or await _already_posted(
            "ap_variance_writeoff", decision_id):
        return None
    await seed_default_coa()
    lbl = label or decision_id
    lines = _balanced_pair(ACC_HUTANG, ACC_PENDAPATAN_LAIN, amount,
                           f"Selisih pembayaran supplier {lbl}")
    return await _insert_entry(
        lines=lines, description=f"Selisih hutang supplier ditutup · {lbl}",
        date=date or now_iso(), source_type="ap_variance_writeoff",
        source_id=decision_id, entity_id=entity_id or "", created_by=created_by,
        source_label=lbl)


async def post_variance_reallocation(*, decision_id: str, entity_id: str, amount: float,
                                    label: str = "", date: str = "",
                                    created_by: str = "system") -> Optional[Dict[str, Any]]:
    """FASE G-3 — Kelebihan bayar dipakai melunasi pesanan LAIN:
      Dr 2-1400 Uang Muka Pelanggan / Cr 1-1200 Piutang Usaha.

    Kwitansi aslinya tidak diubah (append-only): uang yang tadi jadi kewajiban kami
    sekarang menutup piutang lain, dan perpindahannya punya jurnal sendiri.
    Idempotent per (`payment_variance_alloc`, decision_id).
    """
    amount = round(float(amount or 0), 2)
    if not decision_id or amount <= EPS or await _already_posted(
            "payment_variance_alloc", decision_id):
        return None
    await seed_default_coa()
    lbl = label or decision_id
    lines = _balanced_pair(ACC_UANG_MUKA_PELANGGAN, ACC_PIUTANG, amount,
                           f"Alokasi kelebihan bayar {lbl}")
    return await _insert_entry(
        lines=lines, description=f"Kelebihan bayar dialokasikan · {lbl}",
        date=date or now_iso(), source_type="payment_variance_alloc",
        source_id=decision_id, entity_id=entity_id or "", created_by=created_by,
        source_label=lbl)


async def post_bank_holding_allocation(*, source_id: str, entity_id: str, amount: float,
                                      label: str = "", date: str = "",
                                      created_by: str = "system") -> Optional[Dict[str, Any]]:
    """FASE G-8 — Titipan dana teridentifikasi → melunasi piutang pesanan:
      Dr 2-1950 Titipan Dana Belum Teridentifikasi / Cr 1-1200 Piutang Usaha.

    Kasnya SUDAH diakui saat dana dititipkan (Dr Bank / Cr 2-1950), jadi alokasi TIDAK
    boleh menyentuh kas lagi — kalau tidak, uang yang sama terhitung dua kali.
    Idempotent per (`bank_holding_alloc`, source_id).
    """
    amount = round(float(amount or 0), 2)
    if not source_id or amount <= EPS or await _already_posted("bank_holding_alloc", source_id):
        return None
    await seed_default_coa()
    lbl = label or source_id
    lines = _balanced_pair(ACC_TITIPAN_DANA, ACC_PIUTANG, amount,
                           f"Alokasi titipan dana {lbl}")
    return await _insert_entry(
        lines=lines, description=f"Titipan dana dialokasikan · {lbl}",
        date=date or now_iso(), source_type="bank_holding_alloc",
        source_id=source_id, entity_id=entity_id or "", created_by=created_by,
        source_label=lbl)


async def post_paired_entry(*, source_type: str, source_id: str, entity_id: str,
                            lines: List[Dict[str, Any]], label: str = "",
                            date: str = "", created_by: str = "system"
                            ) -> Optional[Dict[str, Any]]:
    """FASE E-7 (E7f/E7g) — jurnal SATU SISI dari peristiwa antar-PT (dokumen kembar).

    Pinjaman uang & pindah aset tetap antar-PT membentuk dua jurnal terpisah — satu di
    buku PT pengirim, satu di buku PT penerima — karena tiap badan hukum punya neraca
    sendiri (dan sejak E7.4 tidak ada lagi buku "grup"). Fungsi ini menulis satu sisi
    dengan `source_id` yang sudah dibedakan pemanggilnya (`…:a` / `…:b`) sehingga
    idempotensinya per sisi, bukan per peristiwa.
    """
    total_d = round(sum(float(l.get("debit") or 0) for l in lines), 2)
    total_c = round(sum(float(l.get("credit") or 0) for l in lines), 2)
    if not lines or total_d <= EPS or abs(total_d - total_c) > 0.01:
        return None
    if await _already_posted(source_type, source_id):
        return None
    await seed_default_coa()
    return await _insert_entry(
        lines=lines, description=label or source_type, date=date or now_iso(),
        source_type=source_type, source_id=source_id, entity_id=entity_id or "",
        created_by=created_by, source_label=label or source_id)


async def post_finance_case(*, case_id: str, entity_id: str, amount: float,
                            debit_acc: str, credit_acc: str, label: str = "",
                            suffix: str = "", date: str = "",
                            created_by: str = "system") -> Optional[Dict[str, Any]]:
    """FASE G-9 — Jurnal penyelesaian **kasus keuangan** (Pusat Kasus Keuangan).

    Satu pintu untuk seluruh playbook yang memindahkan uang: pindah-buku antar rekening
    sendiri, uang yang dipegang karyawan, settlement antar entitas, selisih biaya bank,
    uang muka supplier. Akun debit/kredit ditentukan playbook-nya (lihat
    `services/finance_case_playbooks.py`) supaya jurnalnya bisa dibaca auditor tanpa
    membuka kode.

    Idempotent per (`finance_case`, `case_id:suffix`) — satu kasus bisa melahirkan
    beberapa jurnal berlabel (mis. pindah-buku = 2 jurnal `keluar` & `masuk`), tetapi
    aksi yang sama tidak akan pernah menjurnal dua kali.
    """
    amount = round(float(amount or 0), 2)
    sid = f"{case_id}:{suffix}" if suffix else str(case_id or "")
    if not case_id or amount <= EPS or await _already_posted("finance_case", sid):
        return None
    await seed_default_coa()
    lbl = label or case_id
    lines = _balanced_pair(debit_acc, credit_acc, amount, f"Kasus keuangan {lbl}")
    return await _insert_entry(
        lines=lines, description=f"Penyelesaian kasus keuangan · {lbl}",
        date=date or now_iso(), source_type="finance_case", source_id=sid,
        entity_id=entity_id or "", created_by=created_by, source_label=lbl)


async def post_variance_reversal(*, decision_id: str, entity_id: str, amount: float,
                                 debit_acc: str, credit_acc: str, label: str = "",
                                 date: str = "", created_by: str = "system",
                                 suffix: str = "rev") -> Optional[Dict[str, Any]]:
    """FASE G-3 — PEMBALIK keputusan selisih pembayaran (ledger append-only).

    Dipakai saat kwitansinya dibatalkan / keputusan dianulir: jurnal lama TIDAK
    diubah, dibuat jurnal baru yang membalik arahnya supaya auditor bisa membaca
    kedua kejadian. Idempotent per (`payment_variance_reversal`, decision:suffix).
    """
    amount = round(float(amount or 0), 2)
    sid = f"{decision_id}:{suffix}"
    if not decision_id or amount <= EPS or await _already_posted(
            "payment_variance_reversal", sid):
        return None
    await seed_default_coa()
    lbl = label or decision_id
    lines = _balanced_pair(debit_acc, credit_acc, amount, f"Pembalik selisih bayar {lbl}")
    return await _insert_entry(
        lines=lines, description=f"Pembalik keputusan selisih · {lbl}",
        date=date or now_iso(), source_type="payment_variance_reversal",
        source_id=sid, entity_id=entity_id or "", created_by=created_by, source_label=lbl)


async def post_cash_void(txn_id: str, *, label: str = "",
                         created_by: str = "system") -> Optional[Dict[str, Any]]:
    """Pembalik jurnal mutasi kas yang DI-VOID (append-only, idempotent).

    Dipakai saat kwitansi / pembayaran dibatalkan: jurnal aslinya tidak diubah, dibuat
    jurnal baru dengan debit-kredit tertukar sehingga buku besar ikut kembali dan tidak
    ada saldo hantu (mis. Piutang sudah ter-kredit padahal uangnya dianulir).
    """
    if not txn_id or await _already_posted("cash_transaction_void", txn_id):
        return None
    orig = await db.journal_entries.find_one(
        {"source_type": "cash_transaction", "source_id": txn_id, "status": {"$ne": "void"}},
        {"_id": 0})
    if not orig:
        return None
    lines = [{"account_code": ln.get("account_code"),
              "debit": round(float(ln.get("credit") or 0), 2),
              "credit": round(float(ln.get("debit") or 0), 2),
              "description": f"Pembalik {ln.get('description', '')}"}
             for ln in (orig.get("lines") or [])]
    if not lines:
        return None
    return await _insert_entry(
        lines=lines, description=f"Pembalik mutasi kas · {label or orig.get('source_label', txn_id)}",
        date=now_iso(), source_type="cash_transaction_void", source_id=txn_id,
        entity_id=orig.get("entity_id", ""), created_by=created_by,
        source_label=orig.get("source_label", ""))


async def customer_advance_balance(entity_id: str = "") -> float:
    """Saldo akun 2-1400 (Uang Muka Pelanggan) dari jurnal — bahan INV-VAR-02.

    Nilai positif = kewajiban (uang pelanggan yang kami tahan). Dihitung
    kredit − debit supaya arahnya sesuai sifat akun kewajiban.
    """
    flt: Dict[str, Any] = {"status": {"$ne": "void"},
                           "lines.account_code": ACC_UANG_MUKA_PELANGGAN}
    if entity_id and entity_id != "all":
        flt["entity_id"] = entity_id
    total = 0.0
    async for je in db.journal_entries.find(flt, {"_id": 0, "lines": 1}):
        for ln in je.get("lines") or []:
            if ln.get("account_code") == ACC_UANG_MUKA_PELANGGAN:
                total += float(ln.get("credit") or 0) - float(ln.get("debit") or 0)
    return round(total, 2)


async def variance_writeoff_total(entity_id: str = "") -> float:
    """Σ beban selisih pembayaran (6-9100) — bahan invarian & laporan."""
    flt: Dict[str, Any] = {"status": {"$ne": "void"},
                           "lines.account_code": ACC_SELISIH_BAYAR}
    if entity_id and entity_id != "all":
        flt["entity_id"] = entity_id
    total = 0.0
    async for je in db.journal_entries.find(flt, {"_id": 0, "lines": 1}):
        for ln in je.get("lines") or []:
            if ln.get("account_code") == ACC_SELISIH_BAYAR:
                total += float(ln.get("debit") or 0) - float(ln.get("credit") or 0)
    return round(total, 2)


async def post_asset_acquisition(*, asset_id: str, entity_id: str, amount: float,                                 asset_acc: str, funding_acc: str = ACC_KAS_BESAR,
                                 label: str = "", date: str = "") -> Optional[Dict[str, Any]]:
    """R6.2 — Perolehan aset tetap → GL.
      Dr <akun aset> (harga perolehan) / Cr <akun sumber dana> (default 1-1100 Kas/Bank).
    Menaruh aset di neraca sehingga disposal (Cr aset) tidak membuat saldo negatif.
    Idempotent per asset (source_type='fixed_asset_acquisition')."""
    amount = round(float(amount or 0), 2)
    if amount <= EPS or await _already_posted("fixed_asset_acquisition", asset_id):
        return None
    await seed_default_coa()
    lbl = label or asset_id
    lines = [
        {"account_code": asset_acc, "debit": amount, "credit": 0.0,
         "description": f"Perolehan aset {lbl}"},
        {"account_code": funding_acc, "debit": 0.0, "credit": amount,
         "description": f"Pembayaran perolehan aset {lbl}"},
    ]
    return await _insert_entry(
        lines=lines, description=f"Perolehan aset tetap {lbl}",
        date=date or now_iso(), source_type="fixed_asset_acquisition",
        source_id=asset_id, entity_id=entity_id or "", created_by="system", source_label=lbl)


async def post_depreciation(*, asset_id: str, period: str, entity_id: str, amount: float,
                            asset_label: str = "", dep_exp_acc: str = ACC_DEP_EXPENSE,
                            acc_dep_acc: str = ACC_FA_ACCUM_DEP,
                            date: str = "") -> Optional[Dict[str, Any]]:
    """R6.2 — Penyusutan bulanan (straight-line) → GL.
      Dr 6-6000 Beban Penyusutan / Cr 1-2900 Akumulasi Penyusutan.
    Idempotent per (asset_id, period) via source_type='fixed_asset_depreciation',
    source_id=f'{asset_id}:{period}'. Tidak mengubah subledger fisik (GL murni)."""
    amount = round(float(amount or 0), 2)
    sid = f"{asset_id}:{period}"
    if amount <= EPS or await _already_posted("fixed_asset_depreciation", sid):
        return None
    await seed_default_coa()
    lbl = asset_label or asset_id
    lines = [
        {"account_code": dep_exp_acc, "debit": amount, "credit": 0.0,
         "description": f"Beban penyusutan {lbl} ({period})"},
        {"account_code": acc_dep_acc, "debit": 0.0, "credit": amount,
         "description": f"Akumulasi penyusutan {lbl} ({period})"},
    ]
    return await _insert_entry(
        lines=lines, description=f"Penyusutan {lbl} — {period}",
        date=date or now_iso(), source_type="fixed_asset_depreciation",
        source_id=sid, entity_id=entity_id or "", created_by="system", source_label=lbl)


async def post_asset_disposal(*, asset_id: str, entity_id: str, acquisition_cost: float,
                              accumulated: float, proceeds: float, asset_acc: str,
                              acc_dep_acc: str = ACC_FA_ACCUM_DEP, cash_acc: str = ACC_KAS_BESAR,
                              gain_acc: str = ACC_FA_GAIN, loss_acc: str = ACC_FA_LOSS,
                              label: str = "", date: str = "") -> Optional[Dict[str, Any]]:
    """R6.2 — Pelepasan/disposal aset tetap → GL (menyertakan gain/loss).
      Dr 1-2900 Akumulasi Penyusutan (hapus akumulasi)
      Dr 1-1100 Kas/Bank (proceeds, bila ada)
      [Dr 6-9500 Rugi Pelepasan]   ← bila proceeds < book value
      Cr <akun aset>  (harga perolehan)
      [Cr 4-9100 Laba Pelepasan]   ← bila proceeds > book value
    book_value = acquisition_cost − accumulated; gain_loss = proceeds − book_value.
    Self-balancing (lihat pembuktian POC). Idempotent per asset (source_type='fixed_asset_disposal')."""
    acquisition_cost = round(float(acquisition_cost or 0), 2)
    accumulated = round(float(accumulated or 0), 2)
    proceeds = round(float(proceeds or 0), 2)
    if await _already_posted("fixed_asset_disposal", asset_id):
        return None
    await seed_default_coa()
    book_value = round(acquisition_cost - accumulated, 2)
    gain_loss = round(proceeds - book_value, 2)
    lbl = label or asset_id
    lines: List[Dict[str, Any]] = []
    if accumulated > EPS:
        lines.append({"account_code": acc_dep_acc, "debit": accumulated, "credit": 0.0,
                      "description": f"Hapus akumulasi penyusutan {lbl}"})
    if proceeds > EPS:
        lines.append({"account_code": cash_acc, "debit": proceeds, "credit": 0.0,
                      "description": f"Hasil pelepasan {lbl}"})
    if gain_loss < -EPS:  # RUGI
        lines.append({"account_code": loss_acc, "debit": round(-gain_loss, 2), "credit": 0.0,
                      "description": f"Rugi pelepasan {lbl}"})
    lines.append({"account_code": asset_acc, "debit": 0.0, "credit": acquisition_cost,
                  "description": f"Hapus aset {lbl} (harga perolehan)"})
    if gain_loss > EPS:  # LABA
        lines.append({"account_code": gain_acc, "debit": 0.0, "credit": round(gain_loss, 2),
                      "description": f"Laba pelepasan {lbl}"})
    return await _insert_entry(
        lines=lines, description=f"Pelepasan aset {lbl} (gain/loss)",
        date=date or now_iso(), source_type="fixed_asset_disposal",
        source_id=asset_id, entity_id=entity_id or "", created_by="system", source_label=lbl)





async def post_purchase_return(ret: Dict[str, Any], *, amount: float, ppn: float = 0.0,
                               label: str = "", outcome: str = "ap_credit",
                               cash_account_code: str = "") -> Optional[Dict[str, Any]]:
    """Session #074 (PRET-GL) — Retur beli (Nota Debit) → balik GL.
      ap_credit (default): Dr Hutang(2-1100)|GR-IR(2-1150) / Cr Persediaan(1-1300) [+ Cr PPN Masukan].
      refund   (R5.3)    : Dr Kas/Bank (supplier kembalikan dana) / Cr Persediaan [+ Cr PPN Masukan].
    Pilih debit Hutang bila PO sudah ditagih (ada vendor_bill posted), else GR/IR.
    Idempotent (source_type='purchase_return')."""
    rid = ret.get("id")
    amount = round(float(amount or 0), 2)
    if not rid or amount <= EPS or await _already_posted("purchase_return", rid):
        return None
    await seed_default_coa()
    ppn = round(float(ppn or 0), 2)
    net = round(amount - ppn, 2)
    if (outcome or "").lower() == "refund":
        debit_acc = cash_account_code or ACC_KAS_BESAR
        debit_desc = f"Refund tunai supplier — retur beli {label}"
    else:
        debit_acc = ACC_GRIR
        po_id = ret.get("po_id")
        if po_id and await db.vendor_bills.find_one(
                {"po_id": po_id, "status": {"$in": ["posted", "paid"]}}, {"_id": 0, "id": 1}):
            debit_acc = ACC_HUTANG
        debit_desc = f"Retur beli {label} (Nota Debit)"
    lines = [{"account_code": debit_acc, "debit": amount, "credit": 0.0,
              "description": debit_desc},
             {"account_code": ACC_PERSEDIAAN, "debit": 0.0, "credit": net,
              "description": f"Barang keluar retur beli {label}"}]
    if ppn > EPS:
        lines.append({"account_code": ACC_PPN_IN, "debit": 0.0, "credit": ppn,
                      "description": f"Reversal PPN Masukan {label}"})
    return await _insert_entry(
        lines=lines, description=f"Retur beli {label}",
        date=ret.get("approved_at") or now_iso(), source_type="purchase_return",
        source_id=rid, entity_id=ret.get("entity_id", ""), created_by="system", source_label=label)


async def post_landed_cost(voucher: Dict[str, Any], *, amount: float,
                           label: str = "") -> Optional[Dict[str, Any]]:
    """Session #074 (LC-APPLY-GL) — kapitalisasi landed cost ke GL.
      Dr Persediaan(1-1300) / Cr Hutang(2-1100).
    Konsisten dgn LC-PAY (bayar = Dr Hutang / Cr Kas). Idempotent (source_type='landed_cost')."""
    vid = voucher.get("id")
    amount = round(float(amount or 0), 2)
    if not vid or amount <= EPS or await _already_posted("landed_cost", vid):
        return None
    await seed_default_coa()
    lines = _balanced_pair(ACC_PERSEDIAAN, ACC_HUTANG, amount,
                           f"Kapitalisasi landed cost {label}")
    return await _insert_entry(
        lines=lines, description=f"Landed cost {label}", date=now_iso(),
        source_type="landed_cost", source_id=vid, entity_id=voucher.get("entity_id", ""),
        created_by="system", source_label=label)


async def post_sales_return(ret: Dict[str, Any], *, return_net: float, return_ppn: float,
                            return_cogs: float, is_cash: bool = False,
                            settlement: str = "", cash_account_code: str = "",
                            credit_note_number: str = "") -> Optional[Dict[str, Any]]:
    """F3 — Credit Note (retur penjualan) → GL reversal. Idempotent (source_type='sales_return').
      Dr Pendapatan (net) + Dr PPN Keluaran (ppn) / Cr Piutang|Kas|Store-Credit (gross)
      Dr Persediaan (cogs)  / Cr HPP (cogs)   — barang balik ke stok

    R5.2 — `settlement` menentukan akun kredit sisi kewajiban/aset:
      cash          → 1-1100 Kas (refund tunai; R5.3 buat cash_transaction terpisah)
      store_credit  → 2-1450 Saldo Kredit Pelanggan (bukan pengurang piutang; jadi kewajiban)
      ar/nego/""    → 1-1200 Piutang (pengurang piutang) — default lama (kompatibel `is_cash`).
    """
    rid = ret.get("id")
    if not rid or await _already_posted("sales_return", rid):
        return None
    return_net = round(float(return_net or 0), 2)
    return_ppn = round(float(return_ppn or 0), 2)
    return_cogs = round(float(return_cogs or 0), 2)
    gross = round(return_net + return_ppn, 2)
    if gross <= EPS and return_cogs <= EPS:
        return None
    label = credit_note_number or ret.get("number", rid)
    stype = (settlement or "").lower()
    lines: List[Dict[str, Any]] = []
    if gross > EPS:
        lines.append({"account_code": ACC_PENDAPATAN, "debit": return_net, "credit": 0.0,
                      "description": f"Retur penjualan {label}"})
        if return_ppn > EPS:
            lines.append({"account_code": ACC_PPN_OUT, "debit": return_ppn, "credit": 0.0,
                          "description": f"Reversal PPN Keluaran {label}"})
        if is_cash or stype == "cash":
            credit_acc, credit_desc = (cash_account_code or ACC_KAS_BESAR), "Refund tunai"
        elif stype == "store_credit":
            credit_acc, credit_desc = ACC_STORE_CREDIT, "Saldo kredit pelanggan (store credit)"
        else:
            credit_acc, credit_desc = ACC_PIUTANG, "Pengurang piutang"
        lines.append({"account_code": credit_acc, "debit": 0.0, "credit": gross,
                      "description": f"{credit_desc} {label}"})
    if return_cogs > EPS:
        lines += _balanced_pair(ACC_PERSEDIAAN, ACC_HPP, return_cogs, f"Barang retur masuk stok {label}")
    return await _insert_entry(
        lines=lines, description=f"Credit Note / Retur penjualan {label}",
        date=ret.get("approved_at") or now_iso(),
        source_type="sales_return", source_id=rid, entity_id=ret.get("entity_id", ""),
        created_by="system", source_label=label)


async def post_store_credit_redemption(*, redemption_id: str, entity_id: str, amount: float,
                                        customer_label: str = "", date: str = "") -> Optional[Dict[str, Any]]:
    """R5.2 — Redeem store credit sebagai pembayaran piutang.
      Dr 2-1450 Saldo Kredit Pelanggan / Cr 1-1200 Piutang (sebesar yang dialokasikan).
    Idempotent (source_type='store_credit_redeem', source_id=redemption_id)."""
    amount = round(float(amount or 0), 2)
    if not redemption_id or amount <= EPS or await _already_posted("store_credit_redeem", redemption_id):
        return None
    lbl = customer_label or redemption_id
    lines = [
        {"account_code": ACC_STORE_CREDIT, "debit": amount, "credit": 0.0,
         "description": f"Pemakaian store credit {lbl}"},
        {"account_code": ACC_PIUTANG, "debit": 0.0, "credit": amount,
         "description": f"Pelunasan piutang via store credit {lbl}"},
    ]
    return await _insert_entry(
        lines=lines, description=f"Redeem store credit {lbl}",
        date=date or now_iso(), source_type="store_credit_redeem",
        source_id=redemption_id, entity_id=entity_id or "", created_by="system", source_label=lbl)


async def post_store_credit_adjust(*, adjust_id: str, entity_id: str, amount_signed: float,
                                    customer_label: str = "", date: str = "") -> Optional[Dict[str, Any]]:
    """R5.2 — Penyesuaian manual saldo store credit (admin).
      amount_signed > 0 (tambah saldo)  → Cr 2-1450 / Dr 5-9500 (beban)
      amount_signed < 0 (kurangi saldo) → Dr 2-1450 / Cr 4-9000 (pendapatan lain, hangus)
    Idempotent (source_type='store_credit_adjust', source_id=adjust_id)."""
    amt = round(float(amount_signed or 0), 2)
    if not adjust_id or abs(amt) <= EPS or await _already_posted("store_credit_adjust", adjust_id):
        return None
    lbl = customer_label or adjust_id
    if amt > 0:
        lines = [
            {"account_code": ACC_WRITEOFF, "debit": amt, "credit": 0.0,
             "description": f"Penambahan store credit {lbl}"},
            {"account_code": ACC_STORE_CREDIT, "debit": 0.0, "credit": amt,
             "description": f"Store credit bertambah {lbl}"},
        ]
    else:
        lines = [
            {"account_code": ACC_STORE_CREDIT, "debit": -amt, "credit": 0.0,
             "description": f"Store credit hangus/berkurang {lbl}"},
            {"account_code": ACC_PENDAPATAN_LAIN, "debit": 0.0, "credit": -amt,
             "description": f"Pendapatan store credit hangus {lbl}"},
        ]
    return await _insert_entry(
        lines=lines, description=f"Penyesuaian store credit {lbl}",
        date=date or now_iso(), source_type="store_credit_adjust",
        source_id=adjust_id, entity_id=entity_id or "", created_by="system", source_label=lbl)


async def post_cash_transaction(txn: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Mutasi kas: Dr/Cr Kas/Bank vs lawan akun berdasar ref_type / kategori."""
    if txn.get("status") == "void":
        return None
    tid = txn.get("id")
    if not tid or await _already_posted("cash_transaction", tid):
        return None
    amount = round(float(txn.get("amount", 0) or 0), 2)
    if amount <= EPS:
        return None
    cash_acc = _cash_account(txn)
    ref_type = txn.get("ref_type") or ""
    direction = txn.get("direction")
    desc = txn.get("description") or txn.get("category") or "Transaksi kas"
    number = txn.get("number", tid)

    # KN-076-AR-GL-DRIFT (P2, INV-AR-01): entitas buku JE + split deposit.
    # AR receipt via kas_besar mem-set cash entity="all"; jika seluruh JE (termasuk Cr Piutang)
    # dibukukan di "all", saldo Piutang 1-1200 per-PT DRIFT. Bukukan JE penerimaan AR di entitas
    # PEMILIK piutang (= entitas receipt/order). Kas gabungan tetap ter-net di konsolidasi.
    je_entity = txn.get("entity_id", "")
    ar_receipt_doc = None
    if ref_type == "ar_receipt":
        ar_receipt_doc = await db.ar_receipts.find_one({"id": txn.get("ref_id")}, {"_id": 0})
        if ar_receipt_doc and ar_receipt_doc.get("entity_id") and ar_receipt_doc["entity_id"] != "all":
            je_entity = ar_receipt_doc["entity_id"]
    # FASE G-3 — pengembalian dana / pembayaran supplier lewat kas gabungan tetap harus
    # dibukukan di buku entitas PEMILIK kewajiban (pola KN-076-AR-GL-DRIFT).
    if txn.get("owner_entity_id"):
        je_entity = txn["owner_entity_id"]

    if direction == "in":
        if ref_type == "ar_receipt":
            # KN-076-AR-GL-DRIFT (bagian deposit): jangan meng-Cr Piutang untuk SELURUH kas bila
            # ada kelebihan bayar / pemakaian deposit. Split:
            #   Dr Kas = amount (kas baru) ; Dr Uang Muka = used_deposit ;
            #   Cr Piutang = applied_total ; Cr Uang Muka = unapplied.
            # (applied+unapplied == amount+used_deposit → seimbang). Fallback ke Cr Piutang penuh
            # bila receipt lama tak punya field split (kompatibilitas mundur).
            r = ar_receipt_doc
            if r is None:
                lines = _balanced_pair(cash_acc, ACC_PIUTANG, amount, f"{number} · {desc}")
            else:
                applied = round(float(r.get("applied_total", amount) or 0), 2)
                used_dep = round(float(r.get("used_deposit", 0) or 0), 2)
                unapplied = round(float(r.get("unapplied_amount", 0) or 0), 2)
                lines = [{"account_code": cash_acc, "debit": amount, "credit": 0.0,
                          "description": f"{number} · {desc}"}]
                if used_dep > EPS:
                    lines.append({"account_code": ACC_UANG_MUKA_PELANGGAN, "debit": used_dep,
                                  "credit": 0.0, "description": f"{number} · pakai deposit"})
                if applied > EPS:
                    lines.append({"account_code": ACC_PIUTANG, "debit": 0.0, "credit": applied,
                                  "description": f"{number} · pelunasan AR"})
                if unapplied > EPS:
                    lines.append({"account_code": ACC_UANG_MUKA_PELANGGAN, "debit": 0.0,
                                  "credit": unapplied, "description": f"{number} · titipan/deposit"})
        else:
            contra = ACC_SUSPENSE  # default netral (tidak menggelembungkan pendapatan)
            cat = (txn.get("category") or "").lower()
            for kw, acc in CASH_IN_KEYWORDS:
                if kw in cat:
                    contra = acc
                    break
            # FASE G-8 — lawan akun EKSPLISIT menang atas pencocokan kata kunci: bunga/jasa
            # giro yang dibukukan dari layar rekonsiliasi memakai akun dari Pusat Pengaturan.
            contra = (txn.get("contra_account_code") or "").strip() or contra
            lines = _balanced_pair(cash_acc, contra, amount, f"{number} · {desc}")
    else:  # out
        if ref_type == "ar_refund":
            # FASE G-3 — pengembalian KELEBIHAN bayar pelanggan: uang itu tercatat sebagai
            # kewajiban (2-1400 Uang Muka Pelanggan) saat diterima, jadi saat dikembalikan
            # kewajibannya yang berkurang — bukan beban baru.
            contra = ACC_UANG_MUKA_PELANGGAN
        elif ref_type == "vendor_bill":
            contra = ACC_HUTANG
        elif ref_type == "contra_bon":
            # FASE G-7 — satu kas keluar melunasi BANYAK faktur supplier dalam satu siklus
            # tukar faktur. Lawan akunnya tetap Hutang Usaha: yang berubah hanya caranya
            # (borongan, bukan per faktur), bukan sifat kewajibannya.
            contra = ACC_HUTANG
        elif ref_type == "ap_advance":
            # FASE G-3 — kelebihan bayar ke supplier menjadi UANG MUKA (aset), bukan beban.
            contra = ACC_UANG_MUKA
        elif ref_type == "landed_cost":
            contra = ACC_HUTANG   # S#074 (LC-PAY): lunasi Hutang landed-cost (dikapitalisasi ke Persediaan), bukan Beban Angkut (double-count)
        elif ref_type == "cash_advance":
            contra = ACC_UANG_MUKA  # Sukacita: pencairan PD → Dr Uang Muka / Cr Kas (beban diakui saat settlement)
        else:
            contra = ACC_BEBAN_OPS
            cat = (txn.get("category") or "").lower()
            for kw, acc in CASH_OUT_KEYWORDS:
                if kw in cat:
                    contra = acc
                    break
        # FASE G-8 — lawan akun EKSPLISIT (biaya administrasi bank dari layar rekonsiliasi,
        # kodenya diatur di Pusat Pengaturan) menang atas dugaan berbasis kata kunci.
        contra = (txn.get("contra_account_code") or "").strip() or contra
        lines = _balanced_pair(contra, cash_acc, amount, f"{number} · {desc}")

    return await _insert_entry(
        lines=lines, description=f"Kas {direction} · {desc}", date=txn.get("txn_date") or now_iso(),
        source_type="cash_transaction", source_id=tid, entity_id=je_entity,
        created_by=txn.get("created_by", "system"), source_label=number)


async def backfill_journals() -> Dict[str, int]:
    """Posting otomatis (idempotent) seluruh SSOT yang belum berjurnal.

    Urutan: sales_orders (pendapatan) lalu cash_transactions (mutasi kas).
    Aman diulang — yang sudah posted dilewati.
    """
    await seed_default_coa()
    posted_so = posted_cash = 0
    posted_cogs = 0
    orders = await db.sales_orders.find({}, {"_id": 0}).to_list(20000)
    for o in orders:
        if await post_sales_order(o):
            posted_so += 1
        # KN-076-COGS-ZERO (P2, INV-DATA): setiap order berpendapatan WAJIB punya jurnal HPP.
        # Selaras dgn jalur runtime (routers/invoices.py) yang memanggil keduanya. Idempotent
        # (source_type='sales_cogs'); skip aman bila cost tak diketahui / order tak eligible.
        if await post_order_cogs(o):
            posted_cogs += 1
    txns = await db.cash_transactions.find(
        {"status": {"$ne": "void"}}, {"_id": 0}).sort("txn_date", 1).to_list(20000)
    for t in txns:
        if await post_cash_transaction(t):
            posted_cash += 1
    # Gelombang 1 F-5 — vendor bills posted/paid yang belum berjurnal.
    posted_bill = 0
    bills = await db.vendor_bills.find(
        {"status": {"$in": ["posted", "paid"]}}, {"_id": 0}).to_list(20000)
    for b in bills:
        if await post_vendor_bill(b):
            posted_bill += 1
    return {"sales_orders": posted_so, "cash_transactions": posted_cash,
            "vendor_bills": posted_bill, "sales_cogs": posted_cogs,
            "total": posted_so + posted_cash + posted_bill + posted_cogs}


async def post_incentive_accrual(entity_id: str, period: str,
                                 created_by: str = "system") -> Optional[Dict[str, Any]]:
    """F0-E — Akrual beban insentif penjualan per (entitas, periode).

    Model 1 (silo selling): biaya insentif ditanggung entitas SO (= entitas sales).
    Total = Σ total_incentive seluruh sales (komisi dihitung khusus entitas itu, jadi
    sales entitas lain otomatis 0). Idempotent via source_type='incentive_accrual',
    source_id=f'{entity_id}:{period}'.
      Dr Beban Insentif Penjualan / Cr Hutang Insentif Penjualan.
    """
    if not entity_id or entity_id == "all" or not period:
        raise ValueError("Akrual insentif membutuhkan entitas spesifik & periode (mis. 2026-06).")
    src_id = f"{entity_id}:{period}"
    if await _already_posted("incentive_accrual", src_id):
        return None
    await seed_default_coa()
    from services import sales_force_service as sf
    sales_users = await db.users.find(
        {"role": "sales", "status": "active"}, {"_id": 0, "id": 1}).to_list(500)
    total = 0.0
    for u in sales_users:
        c = await sf.compute_commission(u["id"], period, entity_id=entity_id)
        total += float(c.get("total_incentive", 0) or 0)
    total = round(total, 2)
    if total <= EPS:
        return None
    lines = _balanced_pair(ACC_BEBAN_INSENTIF, ACC_HUTANG_INSENTIF, total,
                           f"Akrual insentif penjualan {period}")
    return await _insert_entry(
        lines=lines, description=f"Akrual insentif penjualan {period}",
        date=now_iso(), source_type="incentive_accrual", source_id=src_id,
        entity_id=entity_id, created_by=created_by, source_label=f"INS-{period}")


async def incentive_accrual_status(entity_id: str, period: str) -> Dict[str, Any]:
    """Status akrual insentif (entitas, periode): sudah diposting? + ringkasan jurnal."""
    src_id = f"{entity_id}:{period}"
    je = await db.journal_entries.find_one(
        {"source_type": "incentive_accrual", "source_id": src_id, "status": {"$ne": "void"}},
        {"_id": 0})
    return {
        "entity_id": entity_id,
        "period": period,
        "posted": bool(je),
        "amount": round(float(je.get("total_debit", 0)), 2) if je else 0.0,
        "journal_number": je.get("number") if je else None,
        "journal_id": je.get("id") if je else None,
        "posted_at": je.get("created_at") if je else None,
    }


# ─── Digitalisasi Formulir Sukacita — Pertanggungjawaban petty cash → GL ─────

async def post_petty_cash_settlement(*, settlement_id: str, entity_id: str,
                                     category_lines: List[Dict[str, Any]],
                                     actor_name: str = "system", date: str = "",
                                     label: str = "") -> Optional[Dict[str, Any]]:
    """Laporan Pertanggungjawaban (settlement) petty cash → jurnal.

      Dr [beban per kategori COA] = Σ pengeluaran per kategori
      Cr 1-1400 Uang Muka        = Σ total pengeluaran

    Anti double-count: beban diakui SAAT settlement (bukan saat disburse). Pada
    pencairan (disburse) hanya Dr Uang Muka / Cr Kas (lihat post_cash_transaction
    ref_type='cash_advance'); settlement membersihkan Uang Muka dengan beban riil.
    Idempotent (source_type='petty_cash_settlement').
    """
    if not settlement_id or await _already_posted("petty_cash_settlement", settlement_id):
        return None
    await seed_default_coa()
    lines: List[Dict[str, Any]] = []
    total = 0.0
    for cl in (category_lines or []):
        amt = round(float(cl.get("amount", 0) or 0), 2)
        if amt <= EPS:
            continue
        lines.append({"account_code": cl.get("account_code") or ACC_BEBAN_OPS,
                      "debit": amt, "credit": 0.0,
                      "description": cl.get("desc") or f"Beban petty cash {label}".strip()})
        total += amt
    total = round(total, 2)
    if total <= EPS:
        return None
    lines.append({"account_code": ACC_UANG_MUKA, "debit": 0.0, "credit": total,
                  "description": f"Pertanggungjawaban {label}".strip()})
    return await _insert_entry(
        lines=lines, description=f"Pertanggungjawaban petty cash {label}".strip(),
        date=date or now_iso(), source_type="petty_cash_settlement",
        source_id=settlement_id, entity_id=entity_id, created_by=actor_name,
        source_label=label)


# ═════════════════════════════════════════════════════════════════════════════
#  H4 — Payroll posting (idempotent per entitas+periode). Lihat PLAN_HRD §4.4.
# ═════════════════════════════════════════════════════════════════════════════

async def post_payroll_run(run: Dict[str, Any], slips: List[Dict[str, Any]],
                           created_by: str = "system") -> Optional[Dict[str, Any]]:
    """Posting jurnal payroll run (SEIMBANG, idempotent).

      Dr Beban Gaji (6-1000)            = Σ(pokok+tunjangan+lembur)
      Dr Beban BPJS Perusahaan (6-1100) = Σ kontribusi employer
      Dr Hutang Insentif (2-1500)       = Σ komisi   [mode accrue_then_settle]
        atau Dr Beban Insentif (6-5000) [mode expense_in_payroll]
      Cr Hutang Gaji (2-1600)           = Σ take-home (net)
      Cr Hutang BPJS (2-1700)           = Σ(employee + employer)
      Cr Hutang PPh21 (2-1800)          = Σ PPh21
    Anti double-count: mode accrue → komisi sudah jadi beban saat akrual penjualan,
    payroll hanya MEMINDAH liability 2-1500 → 2-1600 (bukan beban baru).
    """
    entity_id = run.get("entity_id")
    period = run.get("period")
    src_id = f"{entity_id}:{period}"
    existing = await db.journal_entries.find_one(
        {"source_type": "payroll_run", "source_id": src_id, "status": {"$ne": "void"}}, {"_id": 0})
    if existing:
        return safe_doc(existing)
    await seed_default_coa()

    salary = round(sum(float(s.get("salary_earnings", 0) or 0) for s in slips), 2)
    er_total = round(sum(float(s.get("bpjs_er_total", 0) or 0) for s in slips), 2)
    emp_total = round(sum(float(s.get("bpjs_emp_total", 0) or 0) for s in slips), 2)
    pph21 = round(sum(float(s.get("pph21", 0) or 0) for s in slips), 2)
    net = round(sum(float(s.get("net", 0) or 0) for s in slips), 2)
    commission = round(sum(float(s.get("commission", 0) or 0) for s in slips), 2)
    mode = run.get("commission_mode", "accrue_then_settle")
    label = run.get("number", f"PR-{period}")
    desc = f"Payroll {period} ({label})"

    # Mode accrue: pastikan akrual insentif sudah diposting agar 2-1500 punya saldo.
    incentive_je_id = ""
    if commission > EPS and mode == "accrue_then_settle":
        try:
            inc = await post_incentive_accrual(entity_id, period, created_by)
            if inc:
                incentive_je_id = inc.get("id", "")
        except Exception:
            pass

    def L(code, dr, cr, d=""):
        return {"account_code": code, "debit": round(dr, 2), "credit": round(cr, 2), "description": d}

    lines: List[Dict[str, Any]] = []
    if salary > EPS:
        lines.append(L(ACC_BEBAN_GAJI, salary, 0, "Beban gaji, tunjangan & lembur"))
    if er_total > EPS:
        lines.append(L(ACC_BEBAN_BPJS, er_total, 0, "Kontribusi BPJS perusahaan"))
    if commission > EPS:
        if mode == "accrue_then_settle":
            lines.append(L(ACC_HUTANG_INSENTIF, commission, 0, "Pelunasan hutang insentif via payroll"))
        else:
            lines.append(L(ACC_BEBAN_INSENTIF, commission, 0, "Beban insentif penjualan (payroll)"))
    if net > EPS:
        lines.append(L(ACC_HUTANG_GAJI, 0, net, "Take-home pay terhutang"))
    if (emp_total + er_total) > EPS:
        lines.append(L(ACC_HUTANG_BPJS, 0, round(emp_total + er_total, 2), "Hutang BPJS (employee+employer)"))
    if pph21 > EPS:
        lines.append(L(ACC_HUTANG_PPH21, 0, pph21, "Hutang PPh 21"))

    total_debit = round(sum(l["debit"] for l in lines), 2)
    total_credit = round(sum(l["credit"] for l in lines), 2)
    if abs(total_debit - total_credit) > 0.5:
        raise ValueError(f"Jurnal payroll tidak seimbang: Dr {total_debit:,.0f} ≠ Cr {total_credit:,.0f}")

    je = await _insert_entry(
        lines=lines, description=desc, date=now_iso(),
        source_type="payroll_run", source_id=src_id, entity_id=entity_id,
        created_by=created_by, source_label=label)
    je["incentive_journal_id"] = incentive_je_id
    return je


async def pay_payroll_run(run: Dict[str, Any], created_by: str = "system",
                          cash_account: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Disbursement: Dr Hutang Gaji (2-1600) / Cr Kas/Bank. Idempotent."""
    entity_id = run.get("entity_id")
    period = run.get("period")
    src_id = f"{entity_id}:{period}"
    existing = await db.journal_entries.find_one(
        {"source_type": "payroll_pay", "source_id": src_id, "status": {"$ne": "void"}}, {"_id": 0})
    if existing:
        return safe_doc(existing)
    await seed_default_coa()
    net = round(float((run.get("totals") or {}).get("net", 0) or 0), 2)
    if net <= EPS:
        return None
    cash = cash_account or ACC_KAS_BESAR
    acc = await db.gl_accounts.find_one(
        {"code": cash, "is_postable": True, "entity_id": {"$in": [None, ""]}},
        {"_id": 0})
    if not acc:
        cash = ACC_KAS_BESAR
    label = run.get("number", f"PR-{period}")
    lines = _balanced_pair(ACC_HUTANG_GAJI, cash, net, f"Pembayaran gaji {period} ({label})")
    return await _insert_entry(
        lines=lines, description=f"Pembayaran gaji {period} ({label})", date=now_iso(),
        source_type="payroll_pay", source_id=src_id, entity_id=entity_id,
        created_by=created_by, source_label=label)



# ═════════════════════════════════════════════════════════════════════════════
#  REPORTS — Trial Balance & Account Ledger
# ═════════════════════════════════════════════════════════════════════════════

def _gl_day_end(d: Optional[str]) -> Optional[str]:
    """Gelombang 1 F-6 — as_of tanggal-saja mencakup SELURUH hari itu (konsisten dgn laporan keuangan)."""
    if not d:
        return None
    return d if "T" in d else f"{d}T23:59:59.999999"

async def trial_balance(as_of: Optional[str] = None,
                        scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Neraca saldo: saldo debit/kredit per akun (akun postable yg punya mutasi).

    `scope` = fragmen filter entitas untuk journal_entries (buku terpisah per PT).
    """
    accounts = await db.gl_accounts.find({}, {"_id": 0}).to_list(2000)
    amap = {a["code"]: a for a in accounts}
    q: Dict[str, Any] = {"status": {"$ne": "void"}, **(scope or {})}
    if as_of:
        q["date"] = {"$lte": _gl_day_end(as_of)}
    entries = await db.journal_entries.find(q, {"_id": 0, "lines": 1}).to_list(50000)

    agg: Dict[str, Dict[str, float]] = {}
    for je in entries:
        for ln in je.get("lines", []):
            code = ln.get("account_code")
            if not code:
                continue
            a = agg.setdefault(code, {"debit": 0.0, "credit": 0.0})
            a["debit"] += float(ln.get("debit", 0) or 0)
            a["credit"] += float(ln.get("credit", 0) or 0)

    rows: List[Dict[str, Any]] = []
    tot_debit = tot_credit = 0.0
    for code, v in agg.items():
        acc = amap.get(code, {})
        net = round(v["debit"] - v["credit"], 2)
        nb = acc.get("normal_balance", normal_balance(acc.get("type", "asset")))
        debit_bal = net if net > 0 else 0.0
        credit_bal = -net if net < 0 else 0.0
        rows.append({
            "code": code,
            "name": acc.get("name", code),
            "type": acc.get("type", ""),
            "type_label": TYPE_LABELS.get(acc.get("type", ""), ""),
            "normal_balance": nb,
            "debit": round(v["debit"], 2),
            "credit": round(v["credit"], 2),
            "debit_balance": round(debit_bal, 2),
            "credit_balance": round(credit_bal, 2),
        })
        tot_debit += debit_bal
        tot_credit += credit_bal
    rows.sort(key=lambda r: r["code"])
    return {
        "as_of": as_of or now_iso(),
        "rows": rows,
        "total_debit": round(tot_debit, 2),
        "total_credit": round(tot_credit, 2),
        "balanced": abs(tot_debit - tot_credit) < 0.5,
        "account_count": len(rows),
    }


async def account_ledger(code: str, as_of: Optional[str] = None,
                         scope: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Buku besar 1 akun: baris jurnal yg menyentuh akun + running balance (per entitas via `scope`)."""
    acc = await db.gl_accounts.find_one({"code": code}, {"_id": 0})
    if not acc:
        return None
    q: Dict[str, Any] = {"status": {"$ne": "void"}, "lines.account_code": code, **(scope or {})}
    if as_of:
        q["date"] = {"$lte": _gl_day_end(as_of)}
    entries = await db.journal_entries.find(q, {"_id": 0}).to_list(50000)
    nb = acc.get("normal_balance", normal_balance(acc.get("type", "asset")))
    sign = 1 if nb == "debit" else -1

    flat: List[Dict[str, Any]] = []
    for je in entries:
        for ln in je.get("lines", []):
            if ln.get("account_code") != code:
                continue
            flat.append({
                "entry_id": je.get("id"),
                "number": je.get("number"),
                "date": je.get("date"),
                "description": ln.get("description") or je.get("description"),
                "source_type": je.get("source_type"),
                "source_label": je.get("source_label", ""),
                "debit": round(float(ln.get("debit", 0) or 0), 2),
                "credit": round(float(ln.get("credit", 0) or 0), 2),
            })
    flat.sort(key=lambda r: (r.get("date") or "", r.get("number") or ""))
    running = 0.0
    total_debit = total_credit = 0.0
    for r in flat:
        running += sign * (r["debit"] - r["credit"])
        r["running_balance"] = round(running, 2)
        total_debit += r["debit"]
        total_credit += r["credit"]
    flat.reverse()  # terbaru dulu
    return {
        "account": {"code": acc["code"], "name": acc["name"], "type": acc.get("type"),
                    "type_label": TYPE_LABELS.get(acc.get("type", ""), ""),
                    "normal_balance": nb},
        "lines": flat,
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "balance": round(running, 2),
        "count": len(flat),
    }


async def gl_summary(scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """KPI ringkas untuk header GL (per entitas via `scope`)."""
    tb = await trial_balance(scope=scope)
    posted = await db.journal_entries.count_documents({"status": {"$ne": "void"}, **(scope or {})})
    accounts = await db.gl_accounts.count_documents({})
    return {
        "journal_count": posted,
        "account_count": accounts,
        "total_debit": tb["total_debit"],
        "total_credit": tb["total_credit"],
        "balanced": tb["balanced"],
    }


# ═════════════════════════════════════════════════════════════════════════════
#  Gelombang 1 F-3 — Rekonsiliasi persediaan (subledger rolls vs GL) + saldo awal
# ═════════════════════════════════════════════════════════════════════════════

PHYSICAL_ROLL_STATUSES = ["available", "reserved", "committed", "picked", "packed",
                          "quarantine", "hold"]


async def inventory_reconciliation() -> Dict[str, Any]:
    """Banding nilai persediaan fisik (Σ roll × unit_cost) vs saldo GL 1-1300 per entitas."""
    ents = await db.business_entities.find(
        {}, {"_id": 0, "id": 1, "name": 1, "legal_name": 1}).to_list(100)
    rows: List[Dict[str, Any]] = []
    for e in ents:
        rolls = await db.inventory_rolls.find(
            {"owner_entity_id": e["id"], "status": {"$in": PHYSICAL_ROLL_STATUSES}},
            {"_id": 0, "length_remaining": 1, "unit_cost": 1, "base_unit_cost": 1}).to_list(100000)
        sub = round(sum(float(r.get("length_remaining", 0) or 0) *
                        float(r.get("unit_cost") or r.get("base_unit_cost") or 0)
                        for r in rolls), 2)
        led = await account_ledger(ACC_PERSEDIAAN, scope={"entity_id": e["id"]})
        gl_bal = round(float((led or {}).get("balance", 0) or 0), 2)
        rows.append({"entity_id": e["id"],
                     "entity_name": e.get("legal_name") or e.get("name") or e["id"],
                     "subledger_value": sub, "gl_balance": gl_bal,
                     "difference": round(sub - gl_bal, 2)})
    return {"rows": rows,
            "total_difference": round(sum(r["difference"] for r in rows), 2),
            "as_of": now_iso()}


async def post_inventory_opening_balance(actor_name: str = "system",
                                         tag: str = "") -> Dict[str, Any]:
    """True-up saldo GL Persediaan ke nilai subledger per entitas.

    Dr Persediaan / Cr Ekuitas Saldo Awal (atau sebaliknya bila GL > subledger).
    Idempotent per (entitas, tanggal) — klik ganda di hari yang sama aman.
    `tag` opsional membuat kunci unik (dipakai fixture/QA yang menambah stok setelah
    true-up harian berjalan, agar tidak meninggalkan drift palsu di GL-3).
    """
    await seed_default_coa()
    recon = await inventory_reconciliation()
    posted: List[Dict[str, Any]] = []
    for r in recon["rows"]:
        diff = r["difference"]
        if abs(diff) <= EPS:
            continue
        src_id = f"{r['entity_id']}:{now_iso()[:10]}" + (f":{tag}" if tag else "")
        if await _already_posted("inventory_opening", src_id):
            continue
        if diff > 0:
            lines = _balanced_pair(ACC_PERSEDIAAN, ACC_EKUITAS_AWAL, diff,
                                   f"Saldo awal persediaan {r['entity_name']}")
        else:
            lines = _balanced_pair(ACC_EKUITAS_AWAL, ACC_PERSEDIAAN, -diff,
                                   f"Penyesuaian persediaan {r['entity_name']}")
        je = await _insert_entry(
            lines=lines, description=f"Saldo awal / true-up persediaan — {r['entity_name']}",
            date=now_iso(), source_type="inventory_opening", source_id=src_id,
            entity_id=r["entity_id"], created_by=actor_name, source_label="OPENING-INV")
        posted.append({"entity_id": r["entity_id"], "amount": round(diff, 2),
                       "journal_number": je["number"]})
    return {"posted": posted, "count": len(posted)}


# ═════════════════════════════════════════════════════════════════════════════
#  KONSOLIDASI GRUP vs PER-PT (Multi-Entity F0-E enhancement)
#  Memanfaatkan buku terpisah per entitas (scope journal_entries.entity_id) untuk
#  menyajikan ringkasan P&L + neraca tiap PT, lalu menjumlahkannya jadi gabungan.
# ═════════════════════════════════════════════════════════════════════════════

_CONS_SUM_FIELDS = [
    "revenue", "cogs", "opex", "expense", "gross_profit", "net_income",
    "assets", "liabilities", "equity", "retained_earnings", "equity_total",
    "cash", "ar", "ap", "inventory", "ppn_out", "journal_count",
]


async def _entity_financials(entity_id: str, as_of: Optional[str] = None) -> Dict[str, Any]:
    """Ringkasan keuangan satu buku (entity_id) dari trial balance terisolasi."""
    scope = {"entity_id": entity_id}
    tb = await trial_balance(as_of=as_of, scope=scope)
    revenue = cogs = opex = 0.0
    assets = liabilities = equity = 0.0
    cash = ar = ap = ppn_out = inventory = 0.0
    for r in tb["rows"]:
        t = r.get("type")
        code = r.get("code", "")
        debit_net = round(r["debit_balance"] - r["credit_balance"], 2)
        credit_net = round(r["credit_balance"] - r["debit_balance"], 2)
        if t == "income":
            revenue += credit_net
        elif t == "expense":
            if code.startswith("5"):
                cogs += debit_net
            else:
                opex += debit_net
        elif t == "asset":
            assets += debit_net
        elif t == "liability":
            liabilities += credit_net
        elif t == "equity":
            equity += credit_net
        if code in (ACC_KAS_BESAR, ACC_KAS_KECIL):
            cash += debit_net
        elif code == ACC_PIUTANG:
            ar += debit_net
        elif code == "1-1300":
            inventory += debit_net
        elif code == ACC_HUTANG:
            ap += credit_net
        elif code == ACC_PPN_OUT:
            ppn_out += credit_net
    revenue = round(revenue, 2)
    cogs = round(cogs, 2)
    opex = round(opex, 2)
    expense = round(cogs + opex, 2)
    gross_profit = round(revenue - cogs, 2)
    net_income = round(revenue - expense, 2)
    equity = round(equity, 2)
    journal_count = await db.journal_entries.count_documents(
        {"status": {"$ne": "void"}, "entity_id": entity_id})
    return {
        "revenue": revenue, "cogs": cogs, "opex": opex, "expense": expense,
        "gross_profit": gross_profit, "net_income": net_income,
        "net_margin": round(net_income / revenue * 100, 1) if revenue > 0 else 0.0,
        "assets": round(assets, 2), "liabilities": round(liabilities, 2),
        "equity": equity, "retained_earnings": net_income,
        "equity_total": round(equity + net_income, 2),
        "cash": round(cash, 2), "ar": round(ar, 2), "ap": round(ap, 2),
        "inventory": round(inventory, 2), "ppn_out": round(ppn_out, 2),
        "journal_count": journal_count, "balanced": tb["balanced"],
    }


async def consolidation(entity_ids: List[str], as_of: Optional[str] = None) -> Dict[str, Any]:
    """Konsolidasi grup: ringkasan keuangan per-PT + total gabungan.

    `entity_ids` = entitas dalam cakupan baca user (admin/manager = semua aktif).
    Jurnal ber-entity_id 'all' (kas/bank grup) ditampilkan sebagai baris 'Grup /
    Kas Bersama' agar penjumlahan baris == total konsolidasi (faithful)."""
    ents = {e["id"]: e for e in await db.business_entities.find(
        {"id": {"$in": list(entity_ids)}}, {"_id": 0}).to_list(200)}
    rows: List[Dict[str, Any]] = []
    for eid in entity_ids:
        e = ents.get(eid, {})
        if e.get("is_group"):
            continue
        fin = await _entity_financials(eid, as_of)
        raw_pkp = e.get("is_pkp")
        is_pkp = (e.get("default_tax_mode") in ("ppn", "pkp")) if raw_pkp is None else bool(raw_pkp)
        rows.append({
            "entity_id": eid,
            "entity_name": e.get("legal_name") or e.get("short_name") or eid,
            "short_name": e.get("short_name") or e.get("doc_prefix") or eid,
            "currency": e.get("currency", "IDR"),
            "is_pkp": is_pkp,
            "is_shared": False,
            **fin,
        })
    rows.sort(key=lambda r: r["revenue"], reverse=True)
    # Bucket grup (kas/bank bersama, entity_id == 'all')
    shared = await _entity_financials("all", as_of)
    if shared["journal_count"] > 0:
        rows.append({
            "entity_id": "all", "entity_name": "Grup / Kas Bersama", "short_name": "Grup",
            "currency": "IDR", "is_pkp": None, "is_shared": True, **shared,
        })
    cons = {f: round(sum(float(r.get(f, 0) or 0) for r in rows), 2) for f in _CONS_SUM_FIELDS}
    cons["journal_count"] = int(cons["journal_count"])
    cons["net_margin"] = round(cons["net_income"] / cons["revenue"] * 100, 1) if cons["revenue"] > 0 else 0.0
    cons["balanced"] = all(r.get("balanced", True) for r in rows)
    cons["entity_count"] = len([r for r in rows if not r.get("is_shared")])
    return {"as_of": as_of or now_iso(), "entities": rows, "consolidated": cons}
