"""FASE G-0 — Katalog registry konfigurasi: kebijakan OPERASIONAL per modul.

Entri di sini tersimpan pada dokumen `system_settings` dengan scope tersendiri
(`uom` · `lot` · `makloon` · `receiving` · `hr`) — bukan di dokumen `global`.
`config_registry.legacy_target()` memetakannya otomatis dari prefix kunci.

CATATAN KEJUJURAN SCOPE (diperbarui FASE E-4 · E4.5): dulu `scopes` di sini sengaja
hanya `("global",)` karena mesin pembacanya belum mendukung override per badan usaha —
menuliskan scope yang tidak dihormati mesin sama dengan membuat "tombol palsu".
Sejak E4.5 mesinnya SUDAH mendukung: `get_settings(entity_id)` /
`hr_service.get_hr_settings(entity_id)` menimpa nilai global dengan
`config_resolver.entity_overlay(<scope>, entity_id)`. Karena itu `scopes` sekarang
`("global", "entity")` — dan itu jujur, bukan aspiratif.

Keputusan pemilik #6 yang mendasarinya: "semua master/konfigurasi yang masih bersama
harus jadi per entitas". Contoh nyata yang memaksanya: PT Kain Suka Cita PKP dengan
karyawan tetap (BPJS penuh) vs CV Kanda Suka non-PKP dengan tenaga borongan.
"""
from config_registry import E
from core_utils import rupiah

# Global + override per badan usaha (mesin pembacanya sudah menghormati keduanya).
G = ("global", "entity")

# ═══════════════════════════════════════════════════════════════════════════
# KONVERSI SATUAN (scope `uom`)
# ═══════════════════════════════════════════════════════════════════════════
# Wewenang yang DISALIN dari endpoint konfigurasi lama (FASE G-0) supaya tidak ada
# peran yang kehilangan (atau mendapat) hak saat editor lama dihapus:
#   PUT /uom-conversions/settings   → require_permission(uom, update)      (admin)
#   PUT /lots/settings              → require_role(["manager"])            (admin+manager)
#   PUT /supplier-contracts/policy  → require_role(["admin","manager"])    (admin+manager)
_UOM_PERM = ("uom", "update")
_MANAGER_TOO = ("manager",)

E("uom.warn_pct", group="stok-satuan", type="pct", default=2.0, min=0, max=100, step=0.5,
  unit="%", scopes=G, simulate="uom_variance",
  label="Selisih konversi — batas peringatan",
  help="Bila hasil konversi satuan berbeda dari angka yang diharapkan melebihi persen ini, "
       "sistem memberi peringatan kuning (masih boleh lanjut).",
  impact="Menentukan kapan petugas mendapat peringatan selisih konversi satuan.",
  example="Harapan 47,25 kg · hasil 48,5 kg (+2,6%) · warn 2% → muncul peringatan",
  consumers=("services/uom_rules_service.py",),
  related=("uom.block_pct",), risk="medium",
  permission=_UOM_PERM)

E("uom.block_pct", group="stok-satuan", type="pct", default=5.0, min=0, max=100, step=0.5,
  unit="%", scopes=G, simulate="uom_variance",
  label="Selisih konversi — batas tolak",
  help="Selisih di atas persen ini ditolak sistem, kecuali diizinkan override.",
  impact="Melindungi angka stok dari salah ketik besar saat memakai satuan supplier.",
  example="Selisih 7% · block 5% → ditolak (butuh override berizin)",
  consumers=("services/uom_rules_service.py",),
  related=("uom.allow_override",), risk="high",
  permission=_UOM_PERM)

E("uom.allow_override", group="stok-satuan", type="bool", default=True, scopes=G,
  label="Izinkan override selisih dengan alasan",
  help="Bila aktif, petugas berizin boleh melewati batas tolak dengan menuliskan alasan "
       "yang tercatat di audit.",
  impact="Bila mati, tidak ada jalan keluar saat kiriman memang berbeda — dokumen harus dikoreksi.",
  example="Aktif → selisih 7% bisa lanjut dengan alasan 'kiriman lebih, disetujui manager'",
  consumers=("services/uom_rules_service.py", "routers/inbound_receiving.py"), risk="high",
  permission=_UOM_PERM)

E("uom.precision", group="stok-satuan", type="int", default=2, min=0, max=6, step=1,
  unit="desimal", scopes=G,
  label="Jumlah desimal hasil konversi",
  help="Banyak angka di belakang koma untuk hasil konversi satuan.",
  impact="Mengubah pembulatan qty yang tersimpan — berpengaruh pada kecocokan stok.",
  example="precision 2 → 47,2534 kg disimpan 47,25 kg",
  consumers=("services/uom_rules_service.py",), risk="medium",
  permission=_UOM_PERM)

E("uom.require_trail", group="stok-satuan", type="bool", default=True, scopes=G,
  label="Wajib simpan jejak konversi",
  help="Menyimpan asal angka: satuan & qty dokumen, faktor yang dipakai, dan sumber faktor.",
  impact="Bila mati, angka stok tidak bisa dipertanggungjawabkan ke surat jalan supplier.",
  example="Aktif → tercatat '25 cone × 1,89 = 47,25 kg (sumber: barang supplier)'",
  consumers=("services/uom_rules_service.py",), risk="high",
  permission=_UOM_PERM)

# ═══════════════════════════════════════════════════════════════════════════
# LOT & KETERTELUSURAN (scope `lot`)
# ═══════════════════════════════════════════════════════════════════════════
E("lot.enforcement_mode", group="lot", type="enum", default="warn",
  options=({"value": "off", "label": "Tidak diwajibkan"},
           {"value": "warn", "label": "Beri peringatan bila kosong"},
           {"value": "block", "label": "Tolak bila kosong"}),
  scopes=G, simulate="lot_enforce",
  label="Ketegasan pengisian nomor lot",
  help="Seberapa keras sistem menuntut nomor lot diisi saat barang masuk.",
  impact="Mode 'block' menolak penerimaan tanpa nomor lot — ketertelusuran terjamin tapi "
       "gudang bisa terhambat bila supplier tidak mencantumkan lot.",
  example="block → penerimaan tanpa nomor lot supplier ditolak (400)",
  consumers=("services/lot_service.py", "routers/inbound_receiving.py"), risk="high",
  roles=_MANAGER_TOO)

E("lot.require_supplier_lot", group="lot", type="bool", default=True, scopes=G,
  simulate="lot_enforce",
  label="Wajib nomor lot dari supplier",
  help="Meminta nomor batch/lot yang tertulis di surat jalan supplier.",
  impact="Menentukan field mana yang diperiksa oleh ketegasan pengisian lot di atas.",
  example="Aktif + mode block → field 'Lot Supplier' wajib diisi",
  consumers=("services/lot_service.py",), risk="medium",
  roles=_MANAGER_TOO)

E("lot.require_dye_lot", group="lot", type="bool", default=True, scopes=G,
  simulate="lot_enforce",
  label="Wajib nomor celup (dye lot)",
  help="Nomor celup menentukan kesamaan warna — kunci untuk menghindari klaim beda warna.",
  impact="Menentukan apakah dye lot diperiksa saat penerimaan dan alokasi warna.",
  example="Aktif → roll tanpa dye lot diberi peringatan/ditolak sesuai mode",
  consumers=("services/lot_service.py",),
  related=("allocation.dye_lot_strict",), risk="medium",
  roles=_MANAGER_TOO)

E("lot.auto_create_on_receiving", group="lot", type="bool", default=True, scopes=G,
  label="Buat lot otomatis saat penerimaan",
  help="Sistem membuat kartu lot baru otomatis ketika barang diterima, tanpa input manual.",
  impact="Bila mati, petugas harus membuat lot manual lebih dulu — lebih lambat tetapi lebih terkontrol.",
  example="Aktif → penerimaan 20 roll langsung membentuk LOT-2607-0001",
  consumers=("services/lot_service.py",), risk="medium",
  roles=_MANAGER_TOO)

E("lot.status_on_receipt", group="lot", type="enum", default="karantina",
  options=({"value": "karantina", "label": "Karantina (tunggu QC)"},
           {"value": "tersedia", "label": "Langsung tersedia"}),
  scopes=G,
  label="Status lot saat baru diterima",
  help="Menentukan apakah barang baru langsung bisa dijual atau menunggu lulus QC.",
  impact="'Langsung tersedia' mempercepat penjualan tetapi melewati kendali mutu.",
  example="karantina → stok belum masuk ATP sampai QC selesai",
  consumers=("services/lot_service.py", "routers/inbound_receiving.py"),
  related=("purchasing.qc_on_receipt",), risk="high",
  roles=_MANAGER_TOO)

E("lot.number_format", group="lot", type="text", default="LOT-YYMM-####", scopes=G,
  simulate="lot_number",
  label="Format nomor lot",
  help="Pola nomor lot otomatis. YY = tahun 2 digit, MM = bulan, #### = urutan.",
  impact="Mengubah bentuk nomor lot baru. Nomor lama tidak berubah.",
  example="'KN-LOT-YYMM-#####' → KN-LOT-2607-00001",
  consumers=("services/lot_service.py",), risk="low",
  roles=_MANAGER_TOO)

# ═══════════════════════════════════════════════════════════════════════════
# PENERIMAAN BARANG (scope `receiving`)
# ═══════════════════════════════════════════════════════════════════════════
E("receiving.supplier_uom_input_mode", group="penerimaan", type="enum", default="prefer",
  options=({"value": "off", "label": "Nonaktif — hanya satuan KN"},
           {"value": "optional", "label": "Opsional — petugas boleh memilih"},
           {"value": "prefer", "label": "Diutamakan — satuan supplier terpilih otomatis"}),
  scopes=G,
  label="Input qty pakai satuan supplier",
  help="Mengizinkan petugas mengetik qty apa adanya dari surat jalan supplier (mis. 25 cone) "
       "lalu sistem yang mengonversi ke satuan KN (kg).",
  impact="Mengurangi salah hitung manual. Mode 'off' memaksa petugas mengonversi sendiri.",
  example="prefer → satuan 'cone' langsung terpilih, ketik 25 → tersimpan 47,25 kg",
  consumers=("services/receiving_uom_service.py:uom_options",), risk="medium")

E("receiving.require_supplier_item_for_supplier_uom", group="penerimaan", type="bool",
  default=True, scopes=G,
  label="Satuan supplier wajib punya data Barang Supplier",
  help="Faktor konversi harus berasal dari master Barang Supplier, bukan dari perkiraan global.",
  impact="Bila mati, sistem boleh memakai faktor konversi umum — lebih longgar tetapi "
       "berisiko salah untuk barang tertentu.",
  example="Aktif → satuan 'cone' tanpa data barang supplier ditolak dengan petunjuk perbaikan",
  consumers=("services/receiving_uom_service.py:convert_doc_qty",), risk="medium")

E("receiving.block_over_remaining", group="penerimaan", type="bool", default=True,
  scopes=G, simulate="receiving_over",
  label="Tolak penerimaan melebihi sisa PO",
  help="Bila aktif, penerimaan yang melewati sisa PO + toleransi DITOLAK. Bila mati, "
       "penerimaan tetap diterima namun ditandai 'lebih dari PO' untuk ditinjau.",
  impact="Aktif = disiplin PO terjaga (butuh Eskalasi bila kiriman memang lebih). "
         "Mati = gudang tidak terhambat, tetapi selisih harus ditindaklanjuti.",
  example="Mati · PO sisa 20 kg · datang 25 kg → diterima + ditandai lebih 5 kg",
  consumers=("services/receiving_uom_service.py:preflight_scan",),
  related=("purchasing.receive_tolerance_percent",), risk="high")

# ═══════════════════════════════════════════════════════════════════════════
# PRODUKSI & MAKLOON (scope `makloon`)
# ═══════════════════════════════════════════════════════════════════════════
E("makloon.variance_tolerance_pct", group="makloon", type="pct", default=3.0,
  min=0, max=100, step=0.5, unit="%", scopes=G, simulate="makloon_variance",
  label="Toleransi selisih hasil makloon",
  help="Selisih hasil kembali dari mitra makloon dibanding estimasi yang masih dianggap wajar.",
  impact="Selisih di atas toleransi otomatis membuka Klaim Selisih ke mitra.",
  example="Estimasi 1.000 yard · kembali 960 (−4%) · toleransi 3% → klaim terbuka",
  consumers=("services/makloon_order_service.py", "services/contract_service.py"),
  related=("makloon.auto_claim",), risk="high",
  roles=_MANAGER_TOO)

E("makloon.auto_claim", group="makloon", type="bool", default=True, scopes=G,
  label="Buka klaim otomatis saat selisih besar",
  help="Sistem langsung membuat dokumen klaim ketika selisih melewati toleransi.",
  impact="Bila mati, selisih hanya dicatat — tim harus membuat klaim manual (berisiko terlupa).",
  example="Aktif → selisih −4% otomatis membentuk klaim status 'menunggu persetujuan'",
  consumers=("services/makloon_order_service.py", "services/contract_service.py"), risk="medium",
  roles=_MANAGER_TOO)

E("makloon.claim_approval_roles", group="makloon", type="list",
  default=["manager", "admin"], scopes=G,
  label="Peran yang boleh menyetujui klaim makloon",
  help="Daftar peran yang berwenang menyetujui aksi klaim (potong bon / ganti rugi / terima).",
  impact="Menentukan siapa yang bisa menutup klaim dan membebankan biaya ke mitra.",
  example="['manager','admin'] → supervisor gudang tidak bisa menyetujui klaim",
  consumers=("services/makloon_claim_service.py", "services/contract_service.py"), risk="high",
  roles=_MANAGER_TOO)

E("makloon.contract_mode", group="makloon", type="enum", default="warn",
  options=({"value": "off", "label": "Tidak diwajibkan"},
           {"value": "warn", "label": "Peringatan bila tanpa kontrak"},
           {"value": "block", "label": "Tolak bila tanpa kontrak"}),
  scopes=G,
  label="Ketegasan kontrak makloon",
  help="Seberapa keras order makloon harus merujuk kontrak tarif yang berlaku.",
  impact="Mode 'block' mencegah order tanpa kontrak — tarif selalu terkendali, tetapi mitra "
         "baru harus dibuatkan kontrak lebih dulu.",
  example="block → order makloon tanpa kontrak aktif ditolak",
  consumers=("services/makloon_order_service.py", "services/contract_service.py"), risk="high",
  roles=_MANAGER_TOO)

E("makloon.default_shrinkage_pct", group="makloon", type="pct", default=0.0,
  min=0, max=100, step=0.5, unit="%", scopes=G, simulate="makloon_variance",
  label="Susut standar proses makloon",
  help="Perkiraan penyusutan bawaan proses (mis. penyusutan kain saat dicelup) bila kontrak "
       "belum mencantumkan angkanya.",
  impact="Mempengaruhi estimasi hasil dan perhitungan selisih/klaim.",
  example="Susut 3% · kirim 1.000 yard → estimasi kembali 970 yard",
  consumers=("services/makloon_order_service.py", "services/contract_service.py"), risk="medium",
  roles=_MANAGER_TOO)

E("makloon.require_output_product", group="makloon", type="bool", default=True, scopes=G,
  label="Wajib tentukan produk hasil",
  help="Order makloon harus menyebutkan produk hasil, bukan hanya produk bahan.",
  impact="Bila mati, hasil makloon bisa masuk tanpa identitas produk — HPP & stok jadi kabur.",
  example="Aktif → langkah celup wajib memilih produk hasil 'Lurik Merah Grade A'",
  consumers=("services/makloon_order_service.py", "services/contract_service.py"), risk="medium",
  roles=_MANAGER_TOO)

E("makloon.require_yield_reason", group="makloon", type="bool", default=True, scopes=G,
  label="Wajib alasan bila estimasi hasil diubah",
  help="Bila petugas menimpa angka estimasi hasil, alasannya wajib ditulis dan masuk audit.",
  impact="Menjaga agar estimasi tidak diubah diam-diam untuk menutupi selisih.",
  example="Aktif → mengubah estimasi 970 → 940 wajib mengisi alasan",
  consumers=("routers/makloon_orders.py", "services/contract_service.py"), risk="medium",
  roles=_MANAGER_TOO)

# ═══════════════════════════════════════════════════════════════════════════
# SDM & PENGGAJIAN (scope `hr`)
# ═══════════════════════════════════════════════════════════════════════════
# FASE G-0 — editor lama `PayrollSetupView` DIHAPUS dan digabung ke Pusat
# Pengaturan. Agar penggabungan itu tidak diam-diam MENCABUT wewenang manager
# (yang sejak dulu boleh menulis PUT /api/hr/payroll/settings lewat izin
# `hr.manage_payroll`), setting yang dulu tercakup `SETTINGS_KEYS` di
# routers/hr_payroll.py memakai izin domainnya sendiri, bukan `settings.manage`.
_HR_PAYROLL = ("hr", "manage_payroll")

_BPJS = (
    ("kes_rate_employee", 1.0, "BPJS Kesehatan — potongan karyawan",
     "Persen gaji yang dipotong dari karyawan untuk BPJS Kesehatan."),
    ("kes_rate_employer", 4.0, "BPJS Kesehatan — beban perusahaan",
     "Persen gaji yang dibayar perusahaan untuk BPJS Kesehatan."),
    ("jht_rate_employee", 2.0, "JHT — potongan karyawan",
     "Persen gaji yang dipotong dari karyawan untuk Jaminan Hari Tua."),
    ("jht_rate_employer", 3.7, "JHT — beban perusahaan",
     "Persen gaji yang dibayar perusahaan untuk Jaminan Hari Tua."),
    ("jp_rate_employee", 1.0, "Jaminan Pensiun — potongan karyawan",
     "Persen gaji yang dipotong dari karyawan untuk Jaminan Pensiun."),
    ("jp_rate_employer", 2.0, "Jaminan Pensiun — beban perusahaan",
     "Persen gaji yang dibayar perusahaan untuk Jaminan Pensiun."),
    ("jkm_rate_employer", 0.3, "JKM — beban perusahaan",
     "Persen gaji yang dibayar perusahaan untuk Jaminan Kematian."),
)
for _f, _d, _lab, _help in _BPJS:
    E(f"hr.bpjs.{_f}", group="sdm", type="pct", default=_d, min=0, max=100, step=0.1,
      unit="%", scopes=G, simulate="payroll_bpjs",
      label=_lab, help=_help,
      impact="Mengubah potongan/iuran pada slip gaji periode berikutnya. "
             "Payroll yang sudah diposting tidak berubah.",
      example=f"Gaji Rp 5.000.000 · tarif {_d}% → {rupiah(int(5_000_000 * _d / 100))}",
      consumers=("services/hr_payroll_service.py", "services/hr_service.py"), risk="high",
      permission=_HR_PAYROLL)

E("hr.bpjs.kes_ceiling", group="sdm", type="money", default=12000000, min=0,
  max=1000000000, step=100000, unit="Rp", scopes=G, simulate="payroll_bpjs",
  label="Batas atas upah BPJS Kesehatan",
  help="Upah di atas angka ini tidak menambah iuran BPJS Kesehatan.",
  impact="Membatasi iuran BPJS Kesehatan untuk karyawan bergaji tinggi.",
  example="Batas Rp 12.000.000 · gaji Rp 20.000.000 → iuran dihitung dari Rp 12.000.000",
  consumers=("services/hr_payroll_service.py", "services/hr_service.py"), risk="high",
  permission=_HR_PAYROLL)

E("hr.bpjs.jp_ceiling", group="sdm", type="money", default=10042300, min=0,
  max=1000000000, step=100000, unit="Rp", scopes=G, simulate="payroll_bpjs",
  label="Batas atas upah Jaminan Pensiun",
  help="Upah di atas angka ini tidak menambah iuran Jaminan Pensiun (batas resmi BPJS).",
  impact="Membatasi iuran Jaminan Pensiun untuk karyawan bergaji tinggi.",
  example="Batas Rp 10.042.300 · gaji Rp 15.000.000 → iuran dari Rp 10.042.300",
  consumers=("services/hr_payroll_service.py", "services/hr_service.py"), risk="high",
  permission=_HR_PAYROLL)

E("hr.jkk_classes", group="sdm", type="table",
  default=[{"class": "I", "rate": 0.24}, {"class": "II", "rate": 0.54},
           {"class": "III", "rate": 0.89}, {"class": "IV", "rate": 1.27},
           {"class": "V", "rate": 1.74}],
  scopes=G,
  row_shape="list",
  columns=({"name": "class", "label": "Kelas risiko", "type": "text", "default": "VI",
            "width": "140px"},
           {"name": "rate", "label": "Tarif JKK", "type": "pct", "default": 0.0,
            "unit": "%", "width": "140px"}),
  label="Kelas risiko JKK & tarifnya",
  help="Tarif Jaminan Kecelakaan Kerja per kelas risiko pekerjaan. Setiap karyawan "
       "dipetakan ke salah satu kelas.",
  impact="Mengubah beban JKK perusahaan pada slip gaji periode berikutnya.",
  example="Kelas III 0,89% · gaji Rp 5.000.000 → JKK Rp 44.500",
  consumers=("routers/hr.py", "routers/hr_payroll.py"), risk="high",
  permission=_HR_PAYROLL)

E("hr.ter_enabled", group="sdm", type="bool", default=True, scopes=G,
  simulate="payroll_pph21",
  label="Pakai metode TER untuk PPh 21",
  help="TER (Tarif Efektif Rata-rata) adalah metode resmi sejak 2024: pajak bulanan dihitung "
       "dari tarif efektif berdasarkan kategori PTKP, bukan dari perhitungan tahunan.",
  impact="Menentukan cara PPh 21 bulanan dihitung pada slip gaji.",
  example="Aktif · kategori A · bruto Rp 8.000.000 → PPh 21 memakai tarif TER kategori A",
  consumers=("services/hr_payroll_service.py",),
  related=("hr.ptkp_table",), risk="high", permission=_HR_PAYROLL)

E("hr.ptkp_table", group="sdm", type="table", default={}, scopes=G,
  status="not_used",
  row_shape="map",
  columns=({"name": "__key", "label": "Status PTKP", "type": "text", "width": "160px"},
           {"name": "__value", "label": "PTKP setahun", "type": "money"}),
  not_used_reason="Payroll memakai metode TER (hr.ter_enabled = aktif). Tabel PTKP tahunan "
                  "tidak dipakai dalam perhitungan PPh 21 bulanan. Angka di sini hanya "
                  "referensi; mengubahnya TIDAK mengubah slip gaji.",
  label="Tabel PTKP tahunan (referensi)",
  help="Penghasilan Tidak Kena Pajak per status keluarga. Dipakai metode perhitungan lama; "
       "sistem sekarang memakai TER sehingga tabel ini tidak lagi menjadi dasar hitung.",
  impact="TIDAK ADA dampak selama metode TER aktif. Status karyawan (TK0/K1/…) tetap dipakai "
         "untuk menentukan kategori TER.",
  example="K1 Rp 63.000.000/tahun — hanya referensi, tidak dipakai hitung PPh 21 bulanan",
  related=("hr.ter_enabled",), risk="low", permission=_HR_PAYROLL)

E("hr.overtime.multiplier", group="sdm", type="decimal", default=1.5, min=1, max=5,
  step=0.1, unit="× upah/jam", scopes=G, simulate="payroll_overtime",
  label="Pengali upah lembur",
  help="Kelipatan upah per jam untuk jam lembur.",
  impact="Langsung mengubah nominal lembur pada slip gaji periode berikutnya.",
  example="Upah/jam Rp 28.900 · pengali 1,5 · 4 jam → lembur Rp 173.400",
  consumers=("services/hr_payroll_service.py", "services/hr_attendance_service.py"),
  related=("hr.overtime.hours_divisor",), risk="medium", permission=_HR_PAYROLL)

E("hr.overtime.hours_divisor", group="sdm", type="int", default=173, min=1, max=400,
  step=1, unit="jam/bulan", scopes=G, simulate="payroll_overtime",
  label="Pembagi jam untuk upah per jam",
  help="Angka pembagi gaji bulanan menjadi upah per jam. Standar Kemnaker = 173.",
  impact="Mengubah dasar upah per jam sehingga seluruh nominal lembur berubah.",
  example="Gaji Rp 5.000.000 ÷ 173 → upah/jam Rp 28.902",
  consumers=("services/hr_payroll_service.py",), risk="medium", permission=_HR_PAYROLL)

_TOGGLES = (
    ("bpjs_kesehatan", True, "Aktifkan komponen BPJS Kesehatan",
     "Menampilkan & menghitung potongan/iuran BPJS Kesehatan di slip gaji."),
    ("bpjs_ketenagakerjaan", True, "Aktifkan komponen BPJS Ketenagakerjaan",
     "Menampilkan & menghitung JHT, JP, JKK, dan JKM di slip gaji."),
    ("pph21", True, "Aktifkan potongan PPh 21",
     "Menghitung dan memotong PPh 21 pada slip gaji karyawan."),
    ("npwp_required", False, "Wajibkan NPWP karyawan",
     "Meminta NPWP saat mendaftarkan karyawan baru."),
)
# Consumer NYATA per toggle (diverifikasi services/config_health.py).
_TOGGLE_CONSUMERS = {
    "bpjs_kesehatan": ("services/hr_payroll_service.py:bpjs_breakdown",),
    "bpjs_ketenagakerjaan": ("services/hr_payroll_service.py:bpjs_breakdown",),
    "pph21": ("services/hr_payroll_service.py:compute_payslip",),
    "npwp_required": ("routers/hr.py:create_employee",),
}
for _f, _d, _lab, _help in _TOGGLES:
    E(f"hr.feature_toggles.{_f}", group="sdm", type="bool", default=_d, scopes=G,
      label=_lab, help=_help,
      impact="Mengubah komponen yang muncul & dihitung pada payroll periode berikutnya.",
      example=("Mati → komponen tersebut tidak muncul di slip gaji" if _d
               else "Aktif → field/komponen tersebut menjadi wajib"),
      consumers=_TOGGLE_CONSUMERS[_f], risk="high", permission=_HR_PAYROLL)

E("hr.employment_types", group="sdm", type="list",
  default=["tetap", "kontrak", "harian", "borongan"], scopes=G,
  label="Jenis hubungan kerja",
  help="Daftar status kepegawaian yang bisa dipilih saat mendaftarkan karyawan.",
  impact="Menentukan pilihan pada form karyawan dan aturan payroll yang menempel padanya.",
  example="Menambah 'magang' → muncul sebagai pilihan status karyawan baru",
  consumers=("routers/hr.py", "services/hr_service.py"), risk="medium")

E("hr.payroll_commission_mode", group="sdm", type="enum", default="accrue_then_settle",
  options=({"value": "accrue_then_settle", "label": "Dicadangkan dulu, dibayar setelah lunas"},
           {"value": "pay_on_invoice", "label": "Dibayar saat faktur terbit"},
           {"value": "off", "label": "Komisi tidak lewat payroll"}),
  scopes=G,
  label="Cara komisi masuk penggajian",
  help="Menentukan kapan komisi sales dibayarkan lewat payroll.",
  impact="Mengubah arus kas komisi dan risiko membayar komisi atas piutang yang belum tertagih.",
  example="accrue_then_settle → komisi dibayar bulan setelah pelanggan melunasi",
  consumers=("services/hr_payroll_service.py", "services/sales_force_service.py"),
  risk="high", permission=_HR_PAYROLL)
