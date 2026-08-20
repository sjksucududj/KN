"""FASE G-6 — Katalog konfigurasi **ANTAR ENTITAS** (jual-beli antar-PT dalam grup).

Kenapa configurable: pemilik menegaskan (keputusan 2026-07-30):
  1. **Harga antar-PT `fixed_price` dari kontrak internal** (mode bawaan).
     Sistem TIDAK BOLEH menebak harga (mis. WAC diam-diam).
  2. **PPN internal berbeda per PT** — mode ber-scope entity: `ikut_pkp` (bawaan) ·
     `tanpa_ppn` · `dengan_ppn`. Bila ber-PPN, PPN keluaran penjual == PPN masukan
     pembeli (INV-IC-05).
  3. **Settlement sewaktu-waktu** lewat tombol (tanpa job penjadwal). Config opsional
     `settlement_reminder_days` memicu PENGINGAT bila saldo menganggur > N hari.

Semua kunci di sini dikonsumsi `services/interco_service.py`.
"""
from config_registry import E

G = ("global", "entity")

E("antar_entitas.pricing_mode", group="antar-entitas", type="enum", default="fixed_price",
  scopes=G,
  options=[
      {"value": "fixed_price", "label": "Harga tetap dari kontrak internal"},
      {"value": "at_cost", "label": "Sesuai HPP penjual (tanpa margin)"},
      {"value": "cost_plus_pct", "label": "HPP penjual + persen margin"},
  ],
  label="Mode harga antar-PT (bawaan)",
  help="Cara menentukan harga barang saat satu PT menjual ke PT lain dalam grup. Mode "
       "'fixed_price' — harga tetap per barang, diatur di kontrak internal aktif; transaksi "
       "DITOLAK bila barangnya belum berharga di kontrak (sistem tidak boleh menebak). "
       "Mode 'at_cost' — nilainya = HPP penjual (kompatibilitas M-3 lama). Mode "
       "'cost_plus_pct' — HPP + persen margin (angka margin di kontrak).",
  impact="Menentukan apakah margin antar-PT direalisasi & apakah dokumen ditolak saat "
         "harga kontrak belum ada.",
  example="fixed_price · kontrak PT-KSC↔CV-Kanda: PRD-001 = Rp 25.000/yard → PO internal "
          "otomatis memakai angka itu; produk tanpa kontrak → transaksi ditolak",
  consumers=("services/interco_service.py:_resolve_price",), risk="high",
  related=("antar_entitas.ppn_mode", "antar_entitas.settlement_reminder_days"))

E("antar_entitas.ppn_mode", group="antar-entitas", type="enum", default="ikut_pkp",
  scopes=G,
  options=[
      {"value": "ikut_pkp", "label": "Mengikuti status PKP entitas penjual"},
      {"value": "tanpa_ppn", "label": "Tanpa PPN"},
      {"value": "dengan_ppn", "label": "Dengan PPN (paksa)"},
  ],
  label="Mode PPN antar-PT",
  help="Cara memutuskan apakah transaksi antar-PT ber-PPN. 'ikut_pkp' — PPN diterbitkan "
       "hanya bila entitas penjual berstatus PKP. 'tanpa_ppn' — kedua sisi WAJIB nol "
       "(tidak boleh miring sebelah). 'dengan_ppn' — selalu ber-PPN, penjual menerbitkan "
       "faktur pajak keluaran, pembeli mencatat PPN masukan.",
  impact="Menentukan apakah faktur pajak internal diterbitkan & apakah PPN keluaran "
         "penjual sama besar dengan PPN masukan pembeli (INV-IC-05).",
  example="ikut_pkp · penjual PT-KSC (PKP) · pembeli CV-Kanda → ber-PPN 11%. Bila PT-C "
          "non-PKP menjual → tanpa PPN",
  consumers=("services/interco_service.py:_resolve_tax",), risk="high",
  related=("antar_entitas.pricing_mode",))

E("antar_entitas.approval_threshold_rupiah", group="antar-entitas", type="money",
  default=100000000, min=0, step=1000000, unit="Rp", scopes=G,
  label="Ambang transaksi antar-PT bernilai besar",
  help="Transaksi antar-PT dengan nilai di atas angka ini butuh persetujuan peran yang "
       "lebih tinggi (lihat 'Peran penyetuju transaksi bernilai besar').",
  impact="Menentukan kapan penjualan internal harus naik ke admin (pemisahan tugas).",
  example="Ambang Rp 100.000.000 · transaksi Rp 250.000.000 → wajib disetujui admin",
  consumers=("services/interco_service.py:confirm",), risk="high",
  related=("antar_entitas.approval_role", "antar_entitas.high_value_approval_role"))

E("antar_entitas.approval_role", group="antar-entitas", type="enum", default="manager",
  scopes=G,
  options=[{"value": "manager", "label": "Manager"}, {"value": "admin", "label": "Admin"}],
  label="Peran penyetuju transaksi antar-PT",
  help="Peran minimal yang boleh menyetujui transaksi antar-PT bernilai di bawah ambang.",
  impact="Menentukan siapa yang boleh melepas penjualan internal.",
  example="Manager · transaksi Rp 30.000.000 bisa disetujui manager",
  consumers=("services/interco_service.py:confirm",), risk="high")

E("antar_entitas.high_value_approval_role", group="antar-entitas", type="enum",
  default="admin", scopes=G,
  options=[{"value": "manager", "label": "Manager"}, {"value": "admin", "label": "Admin"}],
  label="Peran penyetuju transaksi bernilai besar",
  help="Peran minimal untuk transaksi antar-PT di atas ambang bernilai besar.",
  impact="Uang besar tidak boleh dilepas oleh wewenang yang sama dengan uang kecil.",
  example="Admin · transaksi Rp 250.000.000 ditolak bila hanya disetujui manager",
  consumers=("services/interco_service.py:confirm",), risk="high")

E("antar_entitas.settlement_reminder_days", group="antar-entitas", type="int", default=30,
  min=0, max=365, step=1, unit="hari", scopes=G,
  label="Pengingat settlement (saldo menganggur)",
  help="Bila saldo pasangan PT menganggur (tidak ada transaksi baru atau pelunasan) lebih "
       "lama dari N hari, sistem menerbitkan PENGINGAT (bukan memaksa). Ritme settlement "
       "tetap SEWAKTU-WAKTU — tombol 'Buat Settlement' selalu tersedia.",
  impact="Membuat saldo lama antar-PT terlihat tanpa memaksa jadwal.",
  example="30 hari · saldo pasangan KSC↔KANDA tidak bergerak 45 hari → pengingat muncul",
  consumers=("services/interco_reminder.py:job_interco_settlement_reminder",
             "services/interco_service.py:list_accounts"), risk="low")

E("antar_entitas.ppn_rate_percent", group="antar-entitas", type="pct", default=11.0,
  min=0, max=100, step=0.5, unit="%", scopes=G,
  label="Tarif PPN antar-PT (bila ber-PPN)",
  help="Tarif PPN yang dipakai untuk transaksi antar-PT ber-PPN. Bawaan 11% (per aturan "
       "berlaku). Bila tarif berubah, semua transaksi antar-PT baru mengikuti angka ini "
       "kecuali PT tertentu meng-override lewat scope entity.",
  impact="Menentukan besar PPN keluaran penjual & PPN masukan pembeli internal.",
  example="11% · DPP Rp 10.000.000 → PPN Rp 1.100.000",
  consumers=("services/interco_service.py:_resolve_tax",), risk="medium")
