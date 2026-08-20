#!/usr/bin/env python3
"""audit_i18n_id.py — GUARDRAIL bahasa antarmuka: WAJIB Bahasa Indonesia.

Kenapa ada berkas ini
---------------------
Pemilik memakai aplikasi ini bersama tim gudang, sales, dan keuangan yang bekerja
dalam Bahasa Indonesia. Label sisa berbahasa Inggris (`Available`, `Picked`,
`Overdue`, `Loading...`) membuat operator ragu — dan keraguan di gudang = salah
kirim. Sebelum ini, "sudah Indonesia" hanya klaim prosa: agent menerjemahkan satu
berkas, berkas berikutnya kembali Inggris tanpa ada yang memerah.

Guardrail ini mengubah janji itu menjadi **kode yang bisa GAGAL**:

  KAMUS   = istilah Inggris yang WAJIB diterjemahkan (beserta usulannya)
  DIPAKAI = istilah yang SENGAJA dibiarkan (singkatan baku & serapan yang justru
            lebih dipahami operator Indonesia: PO, SO, CRM, Lot, Roll, Grade,
            Makloon, Stock Opname, Total, Status, Detail, Info, Transfer)

Cakupan pemindaian = HANYA teks yang benar-benar DILIHAT pengguna:
  · teks JSX antar-tag           `>Available<`
  · nilai prop teks              `label="Picked"` · `placeholder="Search..."`
  · nilai kunci teks di objek    `{ label: "Overdue" }` · `title: "Loading..."`
  · teks di template dokumen cetak (`utils/docPrint.js`)

TIDAK dipindai: `data-testid`, `className`, kunci objek, nama field API, import,
URL, dan komentar — supaya tidak ada temuan palsu yang membuat gate diabaikan.

Pemakaian
---------
    python scripts/audit_i18n_id.py             # laporan (exit 0)
    python scripts/audit_i18n_id.py --strict    # exit 1 bila ADA temuan  → gate
    python scripts/audit_i18n_id.py --self-test # bukti-merah: audit bisa memerah
    python scripts/audit_i18n_id.py --list      # cetak kamus + daftar DIPAKAI
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE_SRC = ROOT / "frontend" / "src"
BE_SRC = ROOT / "backend"

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; B = "\033[1m"; X = "\033[0m"

# ─────────────────────────────────────────────────────────────────────────────
# KAMUS — istilah Inggris yang WAJIB diterjemahkan di antarmuka.
# Kunci dicocokkan sebagai KATA UTUH, tidak peka huruf besar/kecil.
# Frasa yang lebih panjang harus ditulis lebih dulu (dicek berurutan).
# ─────────────────────────────────────────────────────────────────────────────
KAMUS: list[tuple[str, str]] = [
    # ── status roll / stok (paling sering dilihat operator gudang) ──
    ("in-transit (inbound)", "Dalam Perjalanan (Masuk)"),
    ("in-transit (transfer)", "Dalam Perjalanan (Transfer)"),
    ("in-transit (antar-pt)", "Dalam Perjalanan (Antar-PT)"),
    ("in-transit (sales)", "Dalam Perjalanan (Penjualan)"),
    ("in-transit", "Dalam Perjalanan"),
    ("in transit", "Dalam Perjalanan"),
    ("available", "Tersedia"),
    ("reserved", "Dipesan"),
    ("committed", "Dialokasikan"),
    ("picked", "Sudah Diambil"),
    ("packed", "Sudah Dikemas"),
    ("quarantine", "Karantina"),
    ("blocked", "Diblokir"),
    ("damaged", "Rusak"),
    ("sold", "Terjual"),
    ("putaway", "Simpan ke Rak"),
    # ── status dokumen / alur ──
    ("pending", "Menunggu"),
    ("approved", "Disetujui"),
    ("rejected", "Ditolak"),
    ("cancelled", "Dibatalkan"),
    ("canceled", "Dibatalkan"),
    ("completed", "Selesai"),
    ("draft", "Draf"),
    ("overdue", "Lewat Jatuh Tempo"),
    ("outstanding", "Belum Lunas"),
    ("on-order", "Dalam Pesanan"),
    ("on-request", "Dalam Permintaan"),
    # ── proses gudang ──
    ("inbound", "Barang Masuk"),
    ("outbound", "Barang Keluar"),
    ("receiving", "Penerimaan"),
    ("picking", "Pengambilan"),
    ("packing", "Pengemasan"),
    ("dispatch", "Pengiriman"),
    # ── kata benda dokumen ──
    ("purchase requisition", "Permintaan Pembelian"),
    ("sales order", "Pesanan Penjualan"),
    ("purchase order", "Pesanan Pembelian"),
    ("price approval", "Persetujuan Harga"),
    ("invoice", "Faktur"),
    ("customer", "Pelanggan"),
    ("order", "Pesanan"),
    ("quantity", "Jumlah"),
    ("code", "Kode"),
    ("notes", "Catatan"),
    ("note", "Catatan"),
    ("description", "Keterangan"),
    ("overview", "Ringkasan"),
    ("approval", "Persetujuan"),
    # ── aksi / tombol ──
    ("loading", "Memuat"),
    ("submit", "Kirim"),
    ("cancel", "Batal"),
    ("edit", "Ubah"),
    ("save", "Simpan"),
    ("delete", "Hapus"),
    ("close", "Tutup"),
    ("search", "Cari"),
    ("print", "Cetak"),
    ("import", "Impor"),
    ("export", "Ekspor"),
    ("next", "Lanjut"),
    ("previous", "Sebelumnya"),
    ("back", "Kembali"),
    ("retry", "Coba Lagi"),
    ("failed", "Gagal"),
    # ── lain-lain ──
    ("inventory", "Persediaan"),
    ("cycle count", "Stock Opname"),
    # ── putaran ke-2 (sisa ekor panjang) ──
    ("approvals", "Persetujuan"),
    ("returns", "Retur"),
    ("labels", "Label"),
    ("tasks", "Tugas"),
    ("task", "Tugas"),
    ("gallery", "Galeri"),
    ("quotation", "Penawaran"),
    ("dashboard", "Dasbor"),
    ("warehouse", "Gudang"),
    ("warehouses", "Gudang"),
    ("aging", "Umur"),
    ("threshold", "Ambang"),
    ("thresholds", "Ambang"),
    ("reversal", "Pembalikan"),
    ("refund", "Pengembalian Dana"),
    ("void", "Anulir"),
    ("credit note", "Nota Kredit"),
    ("credit", "Kredit"),
    ("settings", "Pengaturan"),
    ("setting", "Pengaturan"),
    ("rules", "Aturan"),
    ("rule", "Aturan"),
    ("delivery", "Pengiriman"),
    ("phone", "Telepon"),
    ("ready", "Siap"),
    ("done", "Selesai"),
    ("active", "Aktif"),
    ("inactive", "Tidak Aktif"),
    ("create", "Buat"),
    ("price", "Harga"),
    ("value", "Nilai"),
    ("cost", "Biaya"),
    ("cash", "Kas"),
    ("stock", "Stok"),
    ("terms", "Termin"),
    ("term", "Termin"),
    ("step", "Langkah"),
    ("steps", "Langkah"),
    ("hold", "Ditahan"),
    ("board", "Papan"),
    # ── putaran ke-3 ──
    ("login", "Masuk"),
    ("logout", "Keluar"),
    ("manager", "Manajer"),
    ("permission", "Izin"),
    ("permissions", "Izin"),
    ("role", "Peran"),
    ("roles", "Peran"),
    ("user", "Pengguna"),
    ("users", "Pengguna"),
    ("profile", "Profil"),
    ("report", "Laporan"),
    ("reports", "Laporan"),
    ("escalate", "Eskalasi"),
    ("approve", "Setujui"),
    ("tour", "Panduan"),
    ("tours", "Panduan"),
    ("checkbox", "Kotak centang"),
    # ── putaran ke-4: teks yang datang dari BACKEND & tab gudang ──
    ("on hand", "Stok Fisik"),
    ("ledger", "Mutasi"),
    ("queue", "Antrean"),
    ("stage", "Tahap"),
    ("advance", "Lanjutkan"),
    ("generate", "Buat"),
    ("confirmed", "Terkonfirmasi"),
    ("dispatched", "Terkirim"),
    ("onboarding", "Pengenalan"),
    ("help", "Bantuan"),
    ("collection", "Penagihan"),
    ("released", "Dirilis"),
]

# ─────────────────────────────────────────────────────────────────────────────
# IZIN KHUSUS — string yang SENGAJA memuat kata Inggris karena kata itu adalah
# **nilai sistem**, bukan kalimat untuk dibaca. Contoh paling jelas: nama peran
# RBAC (`admin`, `manager`, `sales`, `warehouse`). Kalau ditulis "manajer" di
# layar sementara nilai di server "manager", penjelasan wewenang jadi
# menyesatkan — pengguna mencari "manajer" di matriks izin dan tidak menemukannya.
# Setiap pengecualian WAJIB punya alasan agar tidak berubah jadi tempat sampah.
# ─────────────────────────────────────────────────────────────────────────────
IZIN_KHUSUS: dict[str, str] = {
    # FASE G-8 — nilai ini adalah NAMA KOLOM pada ekspor rekening koran bank berbahasa
    # Inggris (template parser `services/bank_statement_parser.py`). Ia dipakai untuk
    # MENCOCOKKAN header berkas milik bank, bukan ditampilkan ke pengguna; menerjemahkannya
    # justru membuat pembacaan berkas gagal.
    "description": "nama kolom header rekening koran bank (template parser), bukan label UI",
    "Manager": "nama peran RBAC (nilai sistem `manager`)",
    "manager/admin": "daftar nilai peran RBAC",
    "mis. Manager": "contoh isi kolom peran penyetuju (nilai sistem)",
    "1 tingkat (→ manager)": "rantai peran RBAC",
    "2 tingkat (→ manager → admin)": "rantai peran RBAC",
    "sales/gudang → manager → admin": "rantai peran RBAC",
    "Setujui (Manager)": "tombol menyebut peran penyetuju (nilai sistem)",
    "user_id": "nama field teknis, bukan kalimat",
    "Hanya admin/manager yang boleh menerapkan koreksi harga.": "menyebut nilai peran RBAC",
    "Hanya sales/manager/admin yang dapat membuat permintaan repeat/restock.":
        "menyebut nilai peran RBAC",
    "Hanya manager/admin yang dapat menyetujui.": "menyebut nilai peran RBAC",
    "Anda dapat memantau statusnya di sini, tetapi keputusan dilakukan oleh manager/admin.":
        "menyebut nilai peran RBAC",
    "di tiap item untuk mengajukan langsung dari sini (disetujui manager/admin).":
        "menyebut nilai peran RBAC",
    "di menu Pelanggan / CRM dan minta persetujuan manager.": "menyebut nilai peran RBAC",
    "Hanya Manager / Admin yang dapat mengatur skema insentif & target.":
        "menyebut nilai peran RBAC",
    "Permohonan akan diteruskan ke Manager/Finance untuk persetujuan (KN_17 §5.2).":
        "menyebut peran penyetuju sesuai dokumen KN_17",
    "Eskalasi ke Manager": "tujuan eskalasi = peran RBAC",
    "open → pending_approval → approved|rejected":
        "nilai status mesin-keadaan (harus sama dengan nilai di server)",
    "Transisi dikunci server; lihat GET /api/enums/stage-transitions":
        "menyebut endpoint & nama enum teknis",
    "Semua tindakan tersedia; eksekusi WAJIB lewat persetujuan manager/admin":
        "menyebut nilai peran RBAC",
    "Override manager/admin": "nama kebijakan RBAC yang dipakai di config & audit",
    # ── `stage` = ISTILAH DOMAIN tekstil (yarn → grey → finished). Layar sengaja
    #    menyebut nama enum-nya supaya cocok dengan aturan transisi di server.
    "Stage": "kolom tahap bahan (enum domain `stage`)",
    "Stage asal": "enum domain `stage`",
    "Stage tidak berubah": "enum domain `stage`",
    "Tahap Bahan (stage)": "sudah Indonesia + menyebut nama enum aslinya",
    "Tahap Bahan (stage) *": "sudah Indonesia + menyebut nama enum aslinya",
    "Tahap Bahan (Stage)": "sudah Indonesia + menyebut nama enum aslinya",
    "Belum ada stage terdaftar.": "menyebut enum domain `stage`",
    "Simulator Transisi Stage": "alat uji transisi enum `stage`",
    "Wajib sejak stage yarn": "menyebut nilai enum `stage` = yarn",
    "Registry Domain Tekstil (Stage · Grade · Konversi)": "nama layar registry enum domain",
    "Penyempurnaan kain jadi (tanpa pindah stage)": "menyebut enum domain `stage`",
    "Finishing: kain jadi → kain jadi (tanpa pindah stage)":
        "nama proses tekstil + enum domain `stage`",
    "Wajib dilengkapi untuk stage “": "menyebut enum domain `stage`",
    "Kelengkapan domain untuk stage “": "menyebut enum domain `stage`",
    "— stage tujuan:": "menyebut enum domain `stage`",
    "90 hari\" value=": "pecahan atribut JSX, bukan kalimat",
    # ── kalimat yang menyebut peran RBAC ──
    "Kirim pesanan ke manager untuk disetujui": "menyebut nilai peran RBAC",
    "Pindai piutang pelanggan yang lewat jatuh tempo (umur piutang) → notifikasi "
    "manager & sales pemegang akun.": "menyebut nilai peran RBAC",
    "Peringatan penting yang belum dibaca melewati batas waktu dinaikkan otomatis ke "
    "atasan (sales/gudang → manager → admin).": "menyebut rantai peran RBAC",
    "Penerimaan barang PO (GR) yang selesai dalam 24 jam terakhir → beri tahu "
    "MD/manager, gudang, dan sales yang punya pesanan pendingan atas produk itu.":
        "menyebut nilai peran RBAC",
}

# ─────────────────────────────────────────────────────────────────────────────
# DIPAKAI — istilah yang SENGAJA dibiarkan berbahasa Inggris/serapan.
# Alasan ditulis agar keputusan ini tidak "membusuk" jadi misteri.
# ─────────────────────────────────────────────────────────────────────────────
DIPAKAI: dict[str, str] = {
    # singkatan dokumen yang justru lebih jelas bagi tim
    "PO": "singkatan baku Purchase Order — dipakai lisan sehari-hari",
    "SO": "singkatan baku Sales Order",
    "PR": "singkatan baku Purchase Requisition",
    "GR": "Goods Receipt (penerimaan) — tercetak di dokumen",
    "RFQ": "permintaan penawaran — istilah pembelian baku",
    "SKU": "kode barang — istilah universal",
    "UOM": "satuan ukur — istilah master data",
    "QC": "quality control — dipakai lisan di lantai produksi",
    "RFID": "teknologi, bukan istilah bisnis",
    "WMS": "nama sistem",
    "CRM": "nama modul",
    "POS": "nama modul kasir",
    "HPP": "harga pokok penjualan (sudah Indonesia)",
    # serapan yang sudah jadi bahasa kerja di industri tekstil Indonesia
    "Lot": "istilah tekstil: satu lot pewarnaan",
    "Roll": "istilah tekstil: roll kain",
    "Grade": "kelas mutu kain — dipakai lisan",
    "Makloon": "istilah Indonesia untuk subkontrak jahit/celup",
    "Stock Opname": "istilah akuntansi Indonesia untuk cycle count",
    "Landed Cost": "istilah biaya impor yang dipakai tim keuangan",
    "Supplier": "serapan; dipakai di seluruh dokumen & lisan",
    "Item": "serapan; dipakai di seluruh dokumen",
    "Total": "sama dalam Bahasa Indonesia",
    "Status": "sama dalam Bahasa Indonesia",
    "Detail": "sama dalam Bahasa Indonesia",
    "Info": "sama dalam Bahasa Indonesia",
    "Transfer": "sama dalam Bahasa Indonesia",
    "Filter": "serapan yang lazim",
    "Reset": "serapan yang lazim",
    "Draf": "hasil terjemahan dari draft",
    # ── kata yang TERLIHAT Inggris tapi memang bahasa kerja Indonesia ──
    "Sales": "dalam praktik Indonesia = orang/tim penjualan ('tim sales', "
             "'kunjungan sales'); menerjemahkannya jadi 'Penjualan' justru salah makna",
    "Unit": "sah dalam Bahasa Indonesia (unit organisasi, unit kerja); untuk satuan "
            "ukur dipakai kata 'Satuan' — dua-duanya benar sesuai konteks",
    "Password": "serapan yang dipahami semua pengguna; 'kata sandi' jarang dipakai lisan",
    "Email": "serapan baku",
    "Scan": "serapan; dipakai lisan di gudang ('scan dulu barangnya')",
    "Batch": "serapan; dipakai di produksi & pewarnaan",
    "Bank": "sama dalam Bahasa Indonesia",
    "Debit": "sama dalam Bahasa Indonesia",
    "Target": "sama dalam Bahasa Indonesia",
    "No.": "singkatan 'nomor' — Bahasa Indonesia",
    "Stage": "ISTILAH DOMAIN tekstil di repo ini (yarn → grey → finished). Nilai enum "
             "`stage` dipakai di domain_registry, transisi, dan validasi server; "
             "menerjemahkannya memutus kaitan layar dengan aturan transisi.",
    "Finishing": "nama proses tekstil yang dipakai lisan di lantai produksi",
    "Log": "serapan teknis (log mesin, log audit)",
    "CSV": "format berkas",
}

# Frasa/konteks yang dikecualikan seluruhnya (nama produk, istilah teknis).
# Dicocokkan sebagai substring, tidak peka huruf besar/kecil.
KECUALI_FRASA = [
    "landed cost", "stock opname", "makloon", "pantone", "whatsapp",
    "control tower",
    # Istilah keuangan/teknis yang SUDAH jadi nama baku di dokumen & GL perusahaan.
    # Menerjemahkannya akan memutus kaitan dengan nama akun/laporan yang dipakai
    # tim keuangan sehari-hari.
    "store credit", "petty cash", "cash advance", "ar aging", "ap aging",
    "weighted average cost", "backorder", "phone number id", "device", "token",
]

# Prop/kunci yang nilainya PASTI dilihat pengguna.
PROP_TEKS = (
    "label", "title", "placeholder", "description", "desc", "hint", "heading",
    "emptyText", "tooltip", "subtitle", "caption", "cta", "actionLabel",
    "shortLabel", "kicker", "aria-label", "alt", "confirmLabel", "cancelLabel",
    "badgeLabel", "unitLabel", "helper", "helperText", "message", "errorText",
    # Sejak putaran 6: `sub` (baris kedua kartu KPI) & kawan-kawannya SERING memuat
    # template literal `${n} order` — tempat kata Inggris paling sering bersembunyi.
    "sub", "footer", "suffix", "prefix", "badge", "empty", "note", "sublabel",
)

RE_PROP = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in PROP_TEKS) + r")\s*[:=]\s*"
    r"(?:\{?\s*)?(\"([^\"\\\n]{1,160})\"|'([^'\\\n]{1,160})'|`([^`\\\n]{1,160})`)"
)
# Potongan interpolasi `${...}` dipisah supaya teks di sekitarnya tetap diperiksa.
RE_INTERP = re.compile(r"\$\{[^{}]*\}")
# Teks JSX antar-tag: harus mengandung huruf, tanpa kurung kurawal/tag.
RE_JSX = re.compile(r">\s*([A-Za-z][^<>{}\n]{0,118}?)\s*<")
# CELAH YANG PERNAH LOLOS: teks yang bersebelahan dengan interpolasi, mis.
#   <h3>Onboarding — {peran}</h3>          → "Onboarding — " tidak pernah diperiksa
#   <span>{n}× order</span>                → "× order" tidak pernah diperiksa
# Dua pola di bawah menutup celah itu (teks SEBELUM `{` dan SESUDAH `}`).
# Sengaja TIDAK mewajibkan huruf di karakter pertama: kata Inggris sering
# didahului tanda seperti `×`, `·`, `-`, atau `%`.
RE_JSX_PRE = re.compile(r">\s*([^\s<>{}\n][^<>{}\n]{0,80}?)\s*\{")
RE_JSX_POST = re.compile(r"\}\s*([^\s<>{}\n][^<>{}\n]{0,80}?)\s*<")
# String di dalam kurawal JSX sebagai anak langsung: {"Available"}
RE_BRACE = re.compile(r"\{\s*\"([^\"\\\n]{1,120})\"\s*\}")

# Berkas/direktori yang dilewati.
LEWATI_DIR = ("components/ui", "node_modules", "__tests__", "__snapshots__")
LEWATI_FILE = ("i18n.js",)

# ─── BACKEND ────────────────────────────────────────────────────────────────
# Sebagian teks yang DILIHAT pengguna lahir di backend (mis. langkah onboarding
# di `routers/onboarding.py`, label laporan, pesan galat). Guardrail yang hanya
# memeriksa frontend akan melaporkan "0 temuan" padahal layar masih berbahasa
# Inggris — itu kebohongan yang sama dengan yang ingin kita cegah.
# Karena itu kunci dict berikut ikut dipindai di backend.
BE_KUNCI_TEKS = ("label", "description", "title", "message", "detail", "hint",
                 "help", "note", "heading", "subtitle", "placeholder", "reason_label")
RE_PY_TEKS = re.compile(
    r"[\"'](?:" + "|".join(BE_KUNCI_TEKS) + r")[\"']\s*:\s*"
    r"(\"([^\"\\\n]{2,160})\"|'([^'\\\n]{2,160})')"
)
# Skrip uji / POC / seed bukan antarmuka → dilewati agar tidak jadi temuan palsu.
BE_LEWATI = ("test_", "backend_test", "_test.py", "scripts/", "tests/")
BE_LEWATI_DIR = ("tests", "scripts", "__pycache__")


def _kamus_regex():
    out = []
    for en, id_ in KAMUS:
        # Kata utuh; izinkan tanda hubung/spasi di dalam frasa.
        pat = re.escape(en).replace(r"\ ", r"[\s\-]")
        out.append((re.compile(rf"(?<![A-Za-z]){pat}(?![A-Za-z])", re.I), en, id_))
    return out


KAMUS_RE = _kamus_regex()


def _dikecualikan(teks: str) -> bool:
    low = teks.lower()
    return any(fr in low for fr in KECUALI_FRASA)


def periksa_teks(teks: str):
    """Kembalikan daftar (istilah_inggris, usulan_indonesia) di dalam `teks`."""
    if teks.strip() in IZIN_KHUSUS:
        return []
    if _dikecualikan(teks):
        return []
    # Buang bagian yang jelas bukan bahasa: kode, path, URL, angka+satuan.
    if teks.startswith(("http", "/", "#", "@")) or "://" in teks:
        return []
    # Pecahan KODE, bukan teks pengguna. Muncul karena `=>` mengandung '>' sehingga
    # regex teks-JSX ikut menangkap ekspresi seperti
    #   {pa.some((p) => p.status === "pending") && (
    # Tanpa saringan ini, guardrail melaporkan temuan palsu → gate mulai diabaikan.
    if any(tok in teks for tok in ("===", "!==", "&&", "||", "=>", "?.", ");", "){", "((")):
        return []
    # Saringan tambahan sejak pola "teks di sekitar interpolasi" ikut dipindai:
    # potongan seperti `act("cancel",` · `axios.delete(` · `row.available_qty + 0.01)`
    # jelas kode, bukan kalimat. Cirinya: pemanggilan fungsi, template literal,
    # akses properti, atau berakhir dengan koma/kurung buka.
    if re.search(r"[`$;]|\w\(|\(\s*[\"'`]|[,(]\s*$|[a-z]\.[a-z]|\?\?", teks):
        return []
    if re.match(r"^(if|return|const|let|var|function|await|async|new|typeof|else)\b", teks):
        return []
    hits = []
    sisa = teks
    for rx, en, id_ in KAMUS_RE:
        if rx.search(sisa):
            hits.append((en, id_))
            sisa = rx.sub(" ", sisa)  # cegah frasa panjang dilaporkan dua kali
    return hits


def kumpulkan_string(src: str):
    """Yield (baris, teks) untuk setiap string yang dilihat pengguna."""
    for rx, grup in ((RE_PROP, None), (RE_JSX, 1), (RE_BRACE, 1),
                     (RE_JSX_PRE, 1), (RE_JSX_POST, 1)):
        for m in rx.finditer(src):
            teks = None
            if grup is None:
                teks = m.group(3) or m.group(4) or m.group(5)
            else:
                teks = m.group(grup)
            if not teks or not re.search(r"[A-Za-z]", teks):
                continue
            baris = src.count("\n", 0, m.start()) + 1
            if "${" in teks:
                # Template literal: periksa tiap potongan teks di antara `${...}`.
                for potong in RE_INTERP.split(teks):
                    potong = potong.strip()
                    if potong and re.search(r"[A-Za-z]", potong):
                        yield baris, potong
                continue
            yield baris, teks.strip()


def pindai(base: Path):
    temuan = []
    for root, dirs, files in os.walk(base):
        rel_root = os.path.relpath(root, base)
        if any(s in rel_root.replace(os.sep, "/") for s in LEWATI_DIR):
            continue
        for f in sorted(files):
            if not f.endswith((".jsx", ".js")) or f in LEWATI_FILE:
                continue
            p = Path(root) / f
            src = p.read_text(encoding="utf-8", errors="ignore")
            try:
                nama_file = str(p.relative_to(ROOT))
            except ValueError:      # self-test memakai direktori sementara
                nama_file = str(p)
            for baris, teks in kumpulkan_string(src):
                for en, id_ in periksa_teks(teks):
                    temuan.append({
                        "file": nama_file, "line": baris,
                        "teks": teks, "en": en, "id": id_,
                    })
    return temuan


def pindai_backend(base: Path):
    """Teks antarmuka yang dikirim BACKEND (label onboarding, judul laporan, dll)."""
    temuan = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in BE_LEWATI_DIR]
        for f in sorted(files):
            if not f.endswith(".py") or any(s in f for s in BE_LEWATI):
                continue
            p = Path(root) / f
            src = p.read_text(encoding="utf-8", errors="ignore")
            for m in RE_PY_TEKS.finditer(src):
                teks = (m.group(2) or m.group(3) or "").strip()
                if not teks or not re.search(r"[A-Za-z]", teks):
                    continue
                for en, id_ in periksa_teks(teks):
                    try:
                        nama = str(p.relative_to(ROOT))
                    except ValueError:
                        nama = str(p)
                    temuan.append({"file": nama, "line": src.count("\n", 0, m.start()) + 1,
                                   "teks": teks, "en": en, "id": id_})
    return temuan


# ─────────────────────────────────────────────────────────────────────────────
# ATURAN [7] — ANGKA GAYA INGGRIS PADA PESAN PENGGUNA          [BARU 2026-07-30]
# ─────────────────────────────────────────────────────────────────────────────
# KELAS BUG YANG DICEGAH (temuan penutupan FASE G-9):
#   Pesan penolakan dibangun dengan `f"Rp {x:,.0f}"` → format INGGRIS
#   ("Rp 999,000,000") padahal seluruh antarmuka Bahasa Indonesia memakai titik
#   ("Rp 999.000.000"). Selama bug KN-G9-ERR-SILENT masih hidup, bilah error tidak
#   pernah dirender sehingga tidak ada yang pernah MELIHAT format salah itu. Begitu
#   error ditampilkan (INV-UI-03), 91 pesan langsung memperlihatkan angka gaya Inggris.
#
# ATURAN: nominal yang dibaca pengguna WAJIB lewat `core_utils.rupiah()`
# (atau alias `_rp`). Pola mentah `Rp {expr:,}` = MERAH.
RE_ANGKA_INGGRIS = re.compile(r"Rp\s?\{[^{}]*:,")
# `core_utils.py` = tempat `rupiah()` didefinisikan (di situ pola `:,` memang wajib ada).
BE_ANGKA_KECUALI = ("core_utils.py",)


def pindai_angka_inggris(base: Path):
    """Cari format uang gaya Inggris di string yang dibaca pengguna."""
    temuan = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in BE_LEWATI_DIR]
        for f in sorted(files):
            if not f.endswith(".py") or any(s in f for s in BE_LEWATI):
                continue
            if f in BE_ANGKA_KECUALI:
                continue
            p = Path(root) / f
            src = p.read_text(encoding="utf-8", errors="ignore")
            for i, baris in enumerate(src.split("\n"), start=1):
                if not RE_ANGKA_INGGRIS.search(baris):
                    continue
                try:
                    nama = str(p.relative_to(ROOT))
                except ValueError:
                    nama = str(p)
                temuan.append({"file": nama, "line": i, "teks": baris.strip()[:70],
                               "en": "Rp {x:,} (pemisah ribuan gaya Inggris)",
                               "id": "pakai rupiah(x) dari core_utils"})
    return temuan


def cetak_laporan(temuan):
    print(f"{C}{B}{'=' * 74}\n  AUDIT BAHASA ANTARMUKA — WAJIB BAHASA INDONESIA\n{'=' * 74}{X}")
    print(f"  Cakupan : {FE_SRC.relative_to(ROOT)} (*.jsx, *.js) · teks yang dilihat pengguna")
    print(f"            {BE_SRC.relative_to(ROOT)} (*.py) · label/pesan yang DIKIRIM ke antarmuka")
    print(f"  Kamus   : {len(KAMUS)} istilah wajib diterjemahkan")
    print(f"  Dipakai : {len(DIPAKAI)} istilah sengaja dibiarkan (lihat --list)\n")
    if not temuan:
        print(f"  {G}{B}✓ 0 temuan — seluruh label sudah Bahasa Indonesia.{X}\n")
        return
    per_file = {}
    for t in temuan:
        per_file.setdefault(t["file"], []).append(t)
    for f in sorted(per_file):
        print(f"  {Y}{f}{X}")
        for t in per_file[f]:
            print(f"     baris {t['line']:>4}  “{t['teks'][:52]}”")
            print(f"                 {R}{t['en']}{X} → {G}{t['id']}{X}")
    print(f"\n  {R}{B}✗ {len(temuan)} temuan di {len(per_file)} berkas.{X}\n")


def self_test() -> int:
    """BUKTI-MERAH: audit ini harus MEMERAH pada kasus buatan, dan HIJAU pada
    istilah yang sengaja dibiarkan. Tanpa uji ini, guardrail bisa mati senyap
    (regex salah → 0 temuan → "hijau" palsu)."""
    print(f"{C}{B}== SELF-TEST audit_i18n_id (bukti-merah guardrail) =={X}")
    skenario = [
        ("teks JSX Inggris HARUS terdeteksi",
         '<span>Available</span>', True),
        ("prop label Inggris HARUS terdeteksi",
         'const t = { label: "Picked" };', True),
        ("placeholder Inggris HARUS terdeteksi",
         '<input placeholder="Search customer" />', True),
        ("string dalam kurawal HARUS terdeteksi",
         '<div>{"Loading..."}</div>', True),
        ("istilah DIPAKAI tidak boleh dilaporkan (Lot/Roll/Grade)",
         '<span>Lot</span><span>Roll</span><b>Grade</b>', False),
        ("frasa kecuali tidak boleh dilaporkan (Landed Cost)",
         '<span>Landed Cost (HPP)</span>', False),
        ("kunci objek / data-testid TIDAK boleh dilaporkan",
         'const m = { available: 1 }; <i data-testid="stock-available" />', False),
        ("className TIDAK boleh dilaporkan",
         '<div className="text-available border-picked" />', False),
        ("label yang sudah Indonesia tidak dilaporkan",
         '<span>Tersedia</span><b>Sudah Diambil</b>', False),
        ("URL tidak dilaporkan",
         '<a title="https://x.test/order/available">x</a>', False),
        ("teks SEBELUM interpolasi HARUS terdeteksi (celah nyata)",
         '<h3>Onboarding — {peran}</h3>', True),
        ("teks SESUDAH interpolasi HARUS terdeteksi (celah nyata)",
         '<span>{n} Available</span>', True),
    ]
    # Aturan [7] — angka gaya Inggris pada pesan backend.
    skenario_py = [
        ("format uang gaya Inggris HARUS terdeteksi",
         'raise ValueError(f"Σ alokasi Rp {total:,.0f} melebihi sisa")', True),
        ("format uang gaya Inggris tanpa spasi HARUS terdeteksi",
         'msg = f"Nilai order Rp{amount:,.0f} perlu persetujuan"', True),
        ("pemakaian helper rupiah() TIDAK boleh dilaporkan",
         'raise ValueError(f"Σ alokasi {rupiah(total)} melebihi sisa")', False),
        ("angka NON-uang tidak dilaporkan (bukan nominal rupiah)",
         'label = f"{qty:,.2f} meter"', False),
    ]
    ok = 0
    with tempfile.TemporaryDirectory() as d:
        for i, (nama, isi, harus_merah) in enumerate(skenario):
            p = Path(d) / f"Kasus{i}.jsx"
            p.write_text(isi, encoding="utf-8")
            hasil = pindai(Path(d))
            p.unlink()
            merah = len(hasil) > 0
            lolos = merah == harus_merah
            ok += lolos
            tag = f"{G}PASS{X}" if lolos else f"{R}FAIL{X}"
            print(f"  [{tag}] {nama}" + ("" if lolos else f"  (temuan={len(hasil)})"))
        for i, (nama, isi, harus_merah) in enumerate(skenario_py):
            p = Path(d) / f"kasus_py_{i}.py"
            p.write_text(isi, encoding="utf-8")
            hasil = pindai_angka_inggris(Path(d))
            p.unlink()
            merah = len(hasil) > 0
            lolos = merah == harus_merah
            ok += lolos
            tag = f"{G}PASS{X}" if lolos else f"{R}FAIL{X}"
            print(f"  [{tag}] [7] {nama}" + ("" if lolos else f"  (temuan={len(hasil)})"))
    total_skenario = len(skenario) + len(skenario_py)
    print(f"\n  {ok}/{total_skenario} skenario lulus.")
    if ok != total_skenario:
        print(f"  {R}{B}✗ SELF-TEST GAGAL — guardrail bahasa tidak dapat dipercaya.{X}\n")
        return 1
    print(f"  {G}{B}✓ SELF-TEST HIJAU — guardrail terbukti bisa memerah.{X}\n")
    return 0


def cetak_daftar():
    print(f"{C}{B}KAMUS ({len(KAMUS)}) — WAJIB diterjemahkan{X}")
    for en, id_ in KAMUS:
        print(f"  {en:26} → {id_}")
    print(f"\n{C}{B}DIPAKAI ({len(DIPAKAI)}) — sengaja dibiarkan{X}")
    for k, why in DIPAKAI.items():
        print(f"  {k:16} — {why}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Guardrail bahasa antarmuka (Indonesia).")
    ap.add_argument("--strict", action="store_true", help="exit 1 bila ada temuan")
    ap.add_argument("--self-test", action="store_true", help="bukti-merah guardrail")
    ap.add_argument("--list", action="store_true", help="cetak kamus & daftar dipakai")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if a.list:
        cetak_daftar()
        return 0
    temuan = (pindai(FE_SRC) + pindai_backend(BE_SRC)
              + pindai_angka_inggris(BE_SRC))
    cetak_laporan(temuan)
    return 1 if (a.strict and temuan) else 0


if __name__ == "__main__":
    sys.exit(main())
