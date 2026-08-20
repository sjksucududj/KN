"""FASE G-0 — Katalog registry konfigurasi: aturan bisnis LINTAS MODUL (scope `global`).

Semua entri di sini tersimpan pada dokumen `system_settings{scope:"global"}` dan bisa
di-override per entitas (`system_settings{scope:"<entity_id>"}`) — sesuai kemampuan
`config_service.get_effective_settings()` yang sudah ada.

Gaya penulisan label/help/impact SENGAJA memakai bahasa awam (bukan istilah teknis)
karena inilah teks yang dibaca pemilik usaha di Pusat Pengaturan.
"""
from config_registry import E

RP = "Rp"

# ═══════════════════════════════════════════════════════════════════════════
# PAJAK
# ═══════════════════════════════════════════════════════════════════════════
E("tax.ppn_rate", group="pajak", type="pct", default=12.0, min=0, max=100, step=0.5,
  unit="%", scopes=("global", "entity"), simulate="tax",
  label="Tarif PPN",
  help="Tarif Pajak Pertambahan Nilai yang dipakai saat membuat invoice penjualan.",
  impact="Mengubah nilai PPN pada SEMUA invoice baru. Invoice yang sudah terbit tidak berubah.",
  example="Subtotal Rp 10.000.000 · tarif 12% + DPP Nilai Lain → PPN Rp 1.100.000",
  consumers=("services/config_service.py:compute_tax", "services/tax_invoice_service.py"),
  related=("tax.dpp_nilai_lain", "tax.ppn_mode"), risk="high")

E("tax.dpp_nilai_lain", group="pajak", type="bool", default=True,
  scopes=("global", "entity"), simulate="tax",
  label="Pakai DPP Nilai Lain (11/12)",
  help="Aturan PMK 131/2024: dasar pengenaan pajak = 11/12 × harga jual untuk barang "
       "non-mewah, sehingga PPN efektif tetap 11% walau tarif tertulis 12%.",
  impact="Nominal rupiah PPN turun ke setara 11%. Kolom DPP pada Faktur Pajak berubah.",
  example="Harga jual Rp 12.000.000 → DPP Rp 11.000.000 → PPN 12% × DPP = Rp 1.320.000",
  consumers=("services/config_service.py:compute_tax",), risk="high")

E("tax.ppn_mode", group="pajak", type="enum", default="excluded",
  options=({"value": "excluded", "label": "Harga BELUM termasuk PPN (ditambah)"},
           {"value": "included", "label": "Harga SUDAH termasuk PPN (dipisah)"}),
  scopes=("global", "entity"), simulate="tax",
  label="Cara menghitung PPN dari harga",
  help="Menentukan apakah harga yang diketik sales sudah mengandung PPN atau belum.",
  impact="Mengubah grand total invoice. 'Included' membuat harga jual dipecah menjadi DPP + PPN.",
  example="Rp 11.100.000 · included → DPP Rp 10.000.000 + PPN Rp 1.100.000",
  consumers=("services/config_service.py:compute_tax",), risk="high")

E("tax.efaktur_enabled", group="pajak", type="bool", default=True,
  scopes=("global", "entity"),
  label="Terbitkan Faktur Pajak (PKP)",
  help="Aktif bila entitas sudah Pengusaha Kena Pajak dan wajib menerbitkan Faktur Pajak.",
  impact="Bila dimatikan, menu Faktur Keluaran tidak menerbitkan e-Faktur dan PPN jadi 0.",
  example="Entitas non-PKP → PPN Rp 0 dan tidak ada nomor Faktur Pajak",
  consumers=("services/config_service.py:compute_tax", "services/tax_invoice_service.py"),
  risk="high")

E("tax.pph_items", group="pajak", type="table", default=[],
  scopes=("global", "entity"),
  row_shape="list",
  columns=({"name": "enabled", "label": "Aktif", "type": "bool", "default": True, "width": "60px"},
           {"name": "code", "label": "Kode", "type": "text", "default": "pph_baru", "width": "120px"},
           {"name": "name", "label": "Nama butir", "type": "text", "default": "Butir PPh Baru"},
           {"name": "basis", "label": "Dasar hitung", "type": "enum", "default": "manual",
            "options": [{"value": "payroll", "label": "Payroll (PPh21 otomatis/TER)"},
                        {"value": "omzet", "label": "Omzet (tarif × peredaran bruto)"},
                        {"value": "manual", "label": "Manual (rekam DPP)"}],
            "width": "220px"},
           {"name": "rate", "label": "Tarif", "type": "pct", "default": 0, "unit": "%",
            "width": "110px",
            "disabled_when": {"field": "basis", "equals": "payroll"},
            "hint": "Basis payroll memakai PPh 21 aktual (TER) — tarif diabaikan."}),
  label="Daftar PPh yang dipotong",
  help="Butir PPh yang berlaku untuk perusahaan (PPh 21 karyawan, PPh 23 jasa, PPh Final UMKM). "
       "Setiap butir punya tarif dan dasar hitung sendiri.",
  impact="Menentukan butir yang muncul di Pusat Pajak → PPh & Rekap serta nominal potongannya.",
  example="PPh 23 jasa 2% aktif → tagihan jasa makloon Rp 50.000.000 dipotong Rp 1.000.000",
  consumers=("services/tax_center_service.py",), risk="medium")

# ═══════════════════════════════════════════════════════════════════════════
# DASAR KEUANGAN & PERIODE
# ═══════════════════════════════════════════════════════════════════════════
E("finance.base_currency", group="keuangan-dasar", type="enum", default="IDR",
  options=({"value": "IDR", "label": "Rupiah (IDR)"},
           {"value": "USD", "label": "Dolar AS (USD)"}),
  scopes=("global", "entity"), simulate="currency",
  label="Mata uang pembukuan",
  help="Mata uang yang dipakai seluruh laporan keuangan dan dokumen cetak.",
  impact="Mengubah simbol & format angka pada laporan, PDF invoice, dan surat jalan.",
  example="IDR → 'Rp 1.250.000' · USD → '$ 1,250.00'",
  consumers=("services/config_currency.py:money_format", "services/pdf_service.py",
             "services/pdf_engine.py:fmt_rp"),
  risk="medium")

E("finance.fiscal_year_end_month", group="keuangan-dasar", type="int", default=12,
  min=1, max=12, step=1, unit="bulan", scopes=("global", "entity"), simulate="fiscal_year",
  label="Bulan tutup tahun buku",
  help="Bulan terakhir tahun buku. 12 berarti tahun buku Januari–Desember.",
  impact="Menentukan periode tahun fiskal pada laporan keuangan dan proses tutup buku tahunan.",
  example="Diisi 3 → tahun buku April 2026 s/d Maret 2027",
  consumers=("services/config_currency.py:fiscal_year_of",
             "services/closing_service.py:period_bounds"),
  risk="high")

E("finance.default_payment_term_code", group="uang-masuk", type="text", default="NET30",
  scopes=("global", "entity"),
  label="Term pembayaran default",
  help="Term yang otomatis terpilih saat membuat pesanan baru bila pelanggan belum punya term khusus.",
  impact="Mengubah tanggal jatuh tempo default pada pesanan & invoice baru.",
  example="NET30 → invoice tanggal 1 Juli jatuh tempo 31 Juli",
  consumers=("routers/sales_orders.py", "services/ar_aging_service.py"), risk="medium")

# ═══════════════════════════════════════════════════════════════════════════
# UANG MASUK & PIUTANG (AR)
# ═══════════════════════════════════════════════════════════════════════════
E("ar.denda_rate_pct_per_month", group="uang-masuk", type="pct", default=2.0,
  min=0, max=100, step=0.25, unit="% / bulan",
  scopes=("global", "entity", "customer"), simulate="ar_penalty",
  label="Bunga denda keterlambatan",
  help="Persen denda per bulan atas saldo yang sudah lewat jatuh tempo. Dihitung prorata per 30 hari.",
  impact="Mengubah kolom 'Denda' pada laporan Umur Piutang. Bisa dibedakan per pelanggan.",
  example="Outstanding Rp 10.000.000 · telat 45 hari · 2%/bulan → denda Rp 300.000",
  consumers=("services/ar_aging_service.py:get_ar_config",),
  related=("ar.grace_days",), risk="medium")

E("ar.grace_days", group="uang-masuk", type="duration", default=0, min=0, max=180, step=1,
  unit="hari", scopes=("global", "entity", "customer"), simulate="ar_penalty",
  label="Masa tenggang sebelum denda",
  help="Jumlah hari setelah jatuh tempo yang masih bebas denda.",
  impact="Hari keterlambatan dikurangi masa tenggang sebelum denda dihitung.",
  example="Tenggang 7 hari · telat 10 hari → denda hanya dihitung 3 hari",
  consumers=("services/ar_aging_service.py:get_ar_config",),
  related=("ar.denda_rate_pct_per_month",), risk="low")

E("ar.aging_buckets", group="uang-masuk", type="list", default=[30, 60, 90],
  scopes=("global", "entity"), simulate="ar_bucket",
  label="Kelompok umur piutang (hari)",
  help="Ambang hari untuk mengelompokkan piutang: 1–30, 31–60, 61–90, dan di atas 90 hari.",
  impact="Mengubah kolom laporan Umur Piutang serta definisi 'pelanggan bermasalah'.",
  example="[14, 30, 60] → kolom menjadi 1–14, 15–30, 31–60, 60+",
  consumers=("services/ar_aging_service.py:_bucket",), risk="medium")

# ═══════════════════════════════════════════════════════════════════════════
# HARGA, DISKON & KOMISI
# ═══════════════════════════════════════════════════════════════════════════
E("sales.allow_item_discount", group="harga-diskon", type="bool", default=False,
  scopes=("global", "entity"), simulate="pricing",
  label="Izinkan diskon per baris (penjualan)",
  help="Bila mati, sales tidak bisa mengetik diskon di baris pesanan — potongan hanya lewat "
       "Harga Khusus yang disetujui.",
  impact="Kolom diskon pada layar pesanan hilang; diskon yang dikirim dari API diabaikan (0%).",
  example="Mati → baris Rp 10.000.000 diskon 5% tetap dihitung Rp 10.000.000",
  consumers=("services/config_service.py:compute_order_pricing", "utils/pricing.js"),
  related=("sales.allow_order_discount",), risk="medium")

E("sales.allow_order_discount", group="harga-diskon", type="bool", default=False,
  scopes=("global", "entity"), simulate="pricing",
  label="Izinkan diskon total pesanan (penjualan)",
  help="Diskon satu angka untuk seluruh pesanan, di atas diskon per baris.",
  impact="Menentukan apakah field diskon order dipakai saat menghitung DPP dan PPN.",
  example="Aktif · diskon order 2% dari Rp 20.000.000 → potongan Rp 400.000",
  consumers=("services/config_service.py:compute_order_pricing", "utils/pricing.js"),
  risk="medium")

E("sales.allow_partial_shipment", group="harga-diskon", type="bool", default=True,
  scopes=("global", "entity"),
  label="Izinkan kirim sebagian",
  help="Bila aktif, pesanan boleh dikirim bertahap saat stok belum lengkap. Bila mati, "
       "pesanan dipaksa berkebijakan kirim penuh (tunggu stok lengkap).",
  impact="Menentukan kebijakan pengiriman yang tersimpan pada pesanan baru dan pembentukan backorder.",
  example="Aktif → pesanan 1.000 yard boleh dikirim 600 dulu, sisanya menyusul",
  consumers=("routers/sales_orders.py:create_order",), risk="medium")

E("sales.quotation_enabled", group="harga-diskon", type="bool", default=False,
  scopes=("global", "entity"), status="not_used",
  not_used_reason=("Alur Penawaran (Quotation) BELUM ADA di sistem — tidak ada satu pun "
                   "endpoint atau layar penawaran. Mengubah tombol ini TIDAK berpengaruh. "
                   "Ditandai jujur di sini (bukan disembunyikan) dan masuk daftar pekerjaan "
                   "FASE G lanjutan. Sementara ini: sales membuat Pesanan langsung, dan "
                   "potongan harga ditempuh lewat 'Ajukan Harga Khusus'."),
  label="Aktifkan Penawaran (Quotation)",
  help="Bila alur Penawaran dibangun, sales membuat Penawaran lebih dulu sebelum pesanan resmi.",
  impact=("BELUM ADA DAMPAK — fitur Penawaran belum dibangun sehingga setting ini tidak "
          "dibaca mesin mana pun."),
  example="— (menunggu fitur Penawaran dibangun)")

# ── F1b (D-14) — Penjagaan harga langganan per pelanggan ────────────────────
# Keputusan pemilik 2026-08-10: harga khusus pelanggan yang jatuh di bawah harga PT
# atau di bawah biaya pokok WAJIB lewat persetujuan manajer, dan memakai MESIN
# persetujuan yang sudah ada (Harga Khusus / `price_approvals`) — bukan alur baru.
E("pricelist.customer_price_approval", group="harga-diskon", type="bool", default=True,
  scopes=("global", "entity"),
  label="Harga pelanggan di bawah batas wajib disetujui",
  help="Bila aktif, harga langganan pelanggan yang di bawah batas bawah (harga PT / biaya "
       "pokok) TIDAK langsung berlaku — masuk antrean Persetujuan Harga lebih dulu.",
  impact="Menentukan apakah record harga pelanggan baru berstatus 'menunggu persetujuan' "
         "atau langsung berlaku pada pesanan & POS.",
  example="Batas Rp 150.000 · admin menetapkan Rp 120.000 → menunggu persetujuan manajer",
  consumers=("services/price_guard_service.py", "services/customer_price_service.py"),
  related=("pricelist.customer_price_floor", "pricelist.customer_price_tolerance_pct"),
  risk="high")

E("pricelist.customer_price_floor", group="harga-diskon", type="enum", default="both",
  options=({"value": "entity_price", "label": "Harga jual PT"},
           {"value": "hpp", "label": "Biaya pokok (HPP)"},
           {"value": "both", "label": "Keduanya (pakai yang lebih tinggi)"}),
  scopes=("global", "entity"),
  label="Dasar batas bawah harga pelanggan",
  help="Angka pembanding yang dipakai untuk menilai sebuah harga 'terlalu murah'. "
       "Biaya pokok dibaca dari HPP berjalan (WAC) produk, sama seperti laporan margin.",
  impact="Mengubah kapan sebuah harga dianggap di bawah batas sehingga butuh persetujuan.",
  example="Pilihan 'Keduanya' · harga PT Rp 150.000 · HPP Rp 130.000 → batas Rp 150.000",
  consumers=("services/price_guard_service.py",),
  related=("pricelist.customer_price_approval",), risk="medium")

E("pricelist.customer_price_tolerance_pct", group="harga-diskon", type="pct", default=0.0,
  min=0, max=100, step=1, unit="% di bawah batas", scopes=("global", "entity"),
  label="Toleransi di bawah batas tanpa persetujuan",
  help="Selisih kecil yang masih dimaafkan supaya pembulatan harga tidak memicu antrean "
       "persetujuan. 0% = sedikit pun di bawah batas sudah butuh persetujuan.",
  impact="Menaikkan angka ini memperlebar harga yang boleh berlaku tanpa persetujuan.",
  example="Batas Rp 150.000 · toleransi 2% → harga ≥ Rp 147.000 tetap langsung berlaku",
  consumers=("services/price_guard_service.py",),
  related=("pricelist.customer_price_approval",), risk="medium")

E("commission.strategy", group="harga-diskon", type="enum", default="per_sku",
  options=({"value": "per_sku", "label": "Per SKU (tarif per barang)"},
           {"value": "achievement_tiered", "label": "Berjenjang dari pencapaian target"}),
  scopes=("global", "entity"),
  label="Cara menghitung komisi sales",
  help="Per SKU: tarif rupiah per satuan barang. Berjenjang: persen dari pencapaian target.",
  impact="Mengubah seluruh perhitungan insentif sales pada periode berjalan.",
  example="per_sku · tarif Rp 500/yard · terjual 2.000 yard → komisi Rp 1.000.000",
  consumers=("services/sales_force_service.py", "routers/incentive_rates.py"), risk="high")

E("commission.incentive_unit", group="harga-diskon", type="text", default="meter",
  scopes=("global", "entity"),
  label="Satuan dasar tarif komisi",
  help="Satuan yang dipakai saat menuliskan tarif komisi rupiah per unit.",
  impact="Qty penjualan dikonversi ke satuan ini sebelum dikalikan tarif komisi.",
  example="Satuan 'meter' · tarif Rp 500/meter → 100 yard ≈ 91,44 m → Rp 45.720",
  consumers=("routers/incentive_rates.py:create_rate",), risk="medium")

E("commission.default_margin_cap_pct", group="harga-diskon", type="pct", default=50.0,
  min=0, max=100, step=5, unit="% margin", scopes=("global", "entity"),
  simulate="commission_cap",
  label="Batas komisi terhadap margin",
  help="Komisi satu baris tidak boleh melebihi persen ini dari margin baris tersebut. "
       "Pengaman agar komisi tidak lebih besar dari keuntungan.",
  impact="Komisi yang melewati batas dipotong otomatis dan diberi catatan pemotongan.",
  example="Margin baris Rp 1.000.000 · batas 50% · komisi hitung Rp 700.000 → dibayar Rp 500.000",
  consumers=("services/sales_force_service.py",), risk="medium")

E("commission.discount_threshold_type", group="harga-diskon", type="enum", default="pct",
  options=({"value": "pct", "label": "Persen diskon"},
           {"value": "rp_per_unit", "label": "Rupiah per satuan"}),
  scopes=("global", "entity"),
  label="Dasar ambang diskon komisi",
  help="Menentukan apakah ambang diskon dibaca sebagai persen atau rupiah per satuan.",
  impact="Mengubah cara ambang diskon dibandingkan sebelum mekanik pemotongan komisi aktif.",
  example="Tipe 'pct' · ambang 10 → diskon 12% memicu pemotongan komisi",
  consumers=("services/sales_force_service.py",), risk="low")

E("commission.discount_threshold", group="harga-diskon", type="decimal", default=10.0,
  min=0, max=1000000, step=1, scopes=("global", "entity"), simulate="commission_discount",
  label="Ambang diskon yang memotong komisi",
  help="Bila diskon baris melewati ambang ini, komisi sales dipotong sesuai mekanik yang dipilih.",
  impact="Menentukan baris mana yang komisinya dipotong karena diskon terlalu besar.",
  example="Ambang 10% · diskon 15% → mekanik pemotongan aktif",
  consumers=("services/sales_force_service.py",),
  related=("commission.discount_mechanic",), risk="medium")

E("commission.discount_mechanic", group="harga-diskon", type="enum", default="tier_factor",
  options=({"value": "tier_factor", "label": "Kalikan faktor (mis. 50% komisi)"},
           {"value": "potong_rp", "label": "Kurangi rupiah per satuan"},
           {"value": "cutoff", "label": "Komisi hangus"}),
  scopes=("global", "entity"), simulate="commission_discount",
  label="Mekanik pemotongan komisi",
  help="Apa yang terjadi pada komisi ketika diskon melewati ambang.",
  impact="Menentukan besar komisi yang dibayarkan pada baris berdiskon besar.",
  example="tier_factor 0,5 → komisi Rp 1.000.000 menjadi Rp 500.000",
  consumers=("services/sales_force_service.py",), risk="medium")

E("commission.discount_factor", group="harga-diskon", type="decimal", default=0.5,
  min=0, max=1, step=0.05, scopes=("global", "entity"), simulate="commission_discount",
  label="Faktor komisi saat diskon besar",
  help="Pengali komisi bila mekanik 'Kalikan faktor' dipakai. 0,5 = komisi tinggal separuh.",
  impact="Langsung mengubah nominal komisi baris berdiskon besar.",
  example="Faktor 0,25 → komisi Rp 800.000 menjadi Rp 200.000",
  consumers=("services/sales_force_service.py",), risk="medium")

E("commission.discount_potong_rp", group="harga-diskon", type="money", default=0.0,
  min=0, max=100000000, step=100, unit=RP, scopes=("global", "entity"),
  simulate="commission_discount",
  label="Potongan rupiah per satuan",
  help="Dipakai bila mekanik 'Kurangi rupiah per satuan' dipilih.",
  impact="Mengurangi tarif komisi per satuan pada baris berdiskon besar.",
  example="Tarif Rp 500/m dipotong Rp 200 → komisi jadi Rp 300/m",
  consumers=("services/sales_force_service.py",), risk="low")

# ═══════════════════════════════════════════════════════════════════════════
# PERSETUJUAN & AMBANG
# ═══════════════════════════════════════════════════════════════════════════
E("approval.extra_levels", group="persetujuan", type="table", default={},
  scopes=("global", "entity"), simulate="approval",
  label="Jenjang persetujuan tambahan",
  help="Level persetujuan di ATAS level pertama, aktif bila nilai dokumen mencapai ambang "
       "tertentu. Level pertama diatur di Approval Rules.",
  impact="Menambah antrean approval berjenjang (mis. Direksi) untuk dokumen bernilai besar.",
  example="PO ≥ Rp 500.000.000 → setelah Manager, wajib disetujui Direksi",
  consumers=("services/config_service.py:build_approval_chain",
             "services/approval_service.py"), risk="high")

# PENGINGAT ANTREAN PERSETUJUAN (permintaan pemilik 2026-08-15).
# Angka KPI yang benar hanya bekerja kalau orangnya membuka layar. Ambang ini menjawab
# "sejak umur berapa sebuah dokumen layak diteriaki": dokumen yang baru masuk hari ini
# tidak perlu pengingat, yang sudah menua wajib. Dinaikkan ke admin/pemilik otomatis
# bila umurnya sudah 2× ambang ini (antrean bukan menumpuk lagi, tapi MANDEK).
E("approval.reminder_min_days", group="persetujuan", type="int", default=2,
  min=0, max=60, step=1, unit="hari", scopes=("global", "entity"),
  label="Umur dokumen sebelum diingatkan",
  help="Pengingat harian hanya menyebut dokumen yang sudah menunggu keputusan minimal "
       "sekian hari. Isi 0 bila ingin diingatkan sejak hari pertama.",
  impact="Menentukan isi pengingat harian 'keputusan yang menunggu Anda' di notifikasi "
         "manajer. Tidak mengubah dokumen apa pun — hanya kapan orang diberi tahu.",
  example="Ambang 2 hari · PO-00010 menunggu 12 hari → masuk pengingat & dinaikkan ke "
          "admin (12 ≥ 2×2)",
  consumers=("services/approval_reminder.py",), risk="low")

E("purchasing.price_deviation_approval_percent", group="persetujuan", type="pct",  default=10.0, min=0, max=100, step=1, unit="%", scopes=("global", "entity"),
  simulate="price_deviation",
  label="Deviasi harga beli yang wajib disetujui",
  help="Bila harga di PO lebih tinggi dari harga acuan supplier melebihi persen ini, "
       "PO wajib persetujuan.",
  impact="Menentukan PO mana yang tertahan menunggu approval karena harga naik.",
  example="Harga acuan Rp 100.000 · PO Rp 115.000 (+15%) · ambang 10% → wajib approval",
  consumers=("routers/purchase_orders.py", "services/pr_sourcing_service.py"), risk="high")

# FASE E-8 (E8.13) — VERIFIKASI ADMINISTRATIF sebelum Konfirmasi SO.
# Bawaan SENGAJA MATI: instalasi yang sudah berjalan tidak boleh mendadak menolak
# konfirmasi yang tadinya sah. Pemilik menyalakannya di sini bila ingin "tidak ada
# pesanan jalan ke gudang sebelum kelengkapannya diperiksa" jadi aturan mengikat.
E("sales_admin.require_verification_before_confirm", group="persetujuan", type="bool",
  default=False, scopes=("global", "entity"),
  label="Wajib verifikasi kelengkapan sebelum pesanan dikonfirmasi",
  help="Bila aktif, pesanan hanya bisa dikonfirmasi setelah Admin Sales menekan "
       "Verifikasi di Meja Admin Sales (alamat & penerima · syarat bayar · isi pesanan). "
       "Ini pemeriksaan ADMINISTRATIF — persetujuan nilai/kredit/harga khusus tetap "
       "keputusan manajer dan tidak terpengaruh sakelar ini.",
  impact="Konfirmasi pesanan yang belum diverifikasi ditolak (409) beserta daftar "
         "kekurangannya. Pesanan yang sudah diverifikasi tidak terpengaruh.",
  example="SO tanpa nama penerima & telepon → Konfirmasi ditolak sampai alamat dilengkapi",
  consumers=("services/so_verify_service.py:assert_ready_to_confirm",
             "routers/sales_orders_extra.py:confirm_order"),
  related=("approval.extra_levels",), risk="medium")

# ═══════════════════════════════════════════════════════════════════════════
# PEMBELIAN & TAGIHAN SUPPLIER
# ═══════════════════════════════════════════════════════════════════════════
E("purchasing.receive_tolerance_percent", group="pembelian", type="pct", default=2.0,
  min=0, max=100, step=0.5, unit="%", scopes=("global", "entity"), simulate="receiving_over",
  label="Toleransi qty kedatangan vs PO",
  help="Selisih qty yang masih boleh saat barang datang (kain/benang jarang persis).",
  impact="Penerimaan di atas PO + toleransi ini akan ditolak atau diberi peringatan.",
  example="PO 1.000 yard · toleransi 2% → boleh terima s/d 1.020 yard",
  consumers=("services/receiving_uom_service.py:receive_tolerance_pct",),
  related=("receiving.block_over_remaining",), risk="medium")

E("purchasing.require_supplier_master", group="pembelian", type="bool", default=False,
  scopes=("global", "entity"), simulate="po_supplier",
  label="PO wajib memilih supplier master",
  help="Bila aktif, PO tidak boleh diisi nama supplier bebas — harus memilih dari daftar "
       "Pemasok yang terdaftar.",
  impact="Pembuatan PO tanpa supplier terdaftar akan ditolak (400) demi kerapian data & 3-way match.",
  example="Aktif → PO dengan supplier_id kosong ditolak: 'PO wajib memilih supplier master'",
  consumers=("routers/purchase_orders.py:_create_po_core",), risk="medium")

E("purchasing.qc_on_receipt", group="pembelian", type="bool", default=True,
  scopes=("global", "entity"),
  label="Barang masuk lewat karantina QC",
  help="Bila aktif, barang yang diterima masuk status karantina dulu dan harus lulus inspeksi "
       "sebelum bisa dijual.",
  impact="Menambah langkah inspeksi QC pada alur penerimaan; stok belum tersedia sebelum lulus.",
  example="Aktif → 20 roll diterima masuk 'karantina', menunggu Inspeksi QC",
  consumers=("routers/inbound_receiving.py", "services/qc_service.py"), risk="medium")

E("purchasing.allow_item_discount", group="pembelian", type="bool", default=True,
  scopes=("global", "entity"), simulate="pricing",
  label="Izinkan diskon per baris (pembelian)",
  help="Mengizinkan potongan harga per baris pada Pesanan Pembelian.",
  impact="Menentukan apakah diskon baris PO dihitung saat menyusun DPP dan PPN masukan.",
  example="Aktif · baris Rp 5.000.000 diskon 3% → dibayar Rp 4.850.000",
  consumers=("services/config_service.py:compute_order_pricing",), risk="low")

E("purchasing.allow_order_discount", group="pembelian", type="bool", default=True,
  scopes=("global", "entity"), simulate="pricing",
  label="Izinkan diskon total (pembelian)",
  help="Mengizinkan satu potongan untuk seluruh Pesanan Pembelian.",
  impact="Menentukan apakah diskon order PO dipakai dalam perhitungan total & pajak masukan.",
  example="Aktif · diskon 1% dari Rp 50.000.000 → potongan Rp 500.000",
  consumers=("services/config_service.py:compute_order_pricing",), risk="low")

E("purchasing.bill_qty_tolerance_percent", group="pembelian", type="pct", default=0.0,
  min=0, max=100, step=0.5, unit="%", scopes=("global", "entity"), simulate="bill_match",
  label="Toleransi qty tagihan supplier",
  help="Selisih qty pada tagihan supplier dibanding barang yang benar-benar diterima yang "
       "masih boleh lewat tanpa sengketa (3-way match).",
  impact="Tagihan dengan selisih qty di atas toleransi akan ditolak/ditandai perlu keputusan.",
  example="Diterima 1.000 yard · ditagih 1.010 · toleransi 0% → tagihan ditolak",
  consumers=("routers/vendor_bills.py", "services/vendor_bill_service.py"), risk="medium")

E("purchasing.bill_price_tolerance_percent", group="pembelian", type="pct", default=5.0,
  min=0, max=100, step=0.5, unit="%", scopes=("global", "entity"), simulate="bill_match",
  label="Toleransi harga tagihan supplier",
  help="Selisih harga satuan pada tagihan supplier dibanding harga PO yang masih boleh lewat.",
  impact="Tagihan dengan harga di atas toleransi ditandai selisih dan butuh keputusan.",
  example="Harga PO Rp 100.000 · ditagih Rp 108.000 (+8%) · toleransi 5% → ditandai selisih",
  consumers=("routers/vendor_bills.py", "services/vendor_bill_service.py"), risk="medium")

# ═══════════════════════════════════════════════════════════════════════════
# STOK, SATUAN & ALOKASI
# ═══════════════════════════════════════════════════════════════════════════
E("inventory.default_uom", group="stok-satuan", type="text", default="meter",
  scopes=("global", "entity"),
  label="Satuan default produk baru",
  help="Satuan yang otomatis terpilih ketika membuat produk baru.",
  impact="Mempengaruhi satuan awal produk baru dan tampilan stok default.",
  example="'meter' → produk baru langsung bersatuan meter",
  consumers=("routers/products.py:create_product",), risk="low")

E("inventory.min_cut_qty", group="stok-satuan", type="decimal", default=0.5,
  min=0, max=1000, step=0.1, unit="satuan dasar", scopes=("global", "entity"),
  simulate="min_cut",
  label="Minimum panjang potong kain",
  help="Panjang terkecil yang boleh dipotong dari satu roll. Mencegah sisa potongan yang "
       "terlalu pendek sehingga tidak terjual.",
  impact="Pesanan/pengambilan dengan qty di bawah angka ini ditolak dengan pesan jelas.",
  example="Minimum 0,5 m → permintaan potong 0,3 m ditolak",
  consumers=("routers/sales_orders.py:_validate_min_cut",), risk="medium")

E("inventory.intercompany_transfer_required", group="stok-satuan", type="bool", default=True,
  scopes=("global", "entity"), simulate="interco",
  label="Wajib transfer sebelum jual stok entitas lain",
  help="Bila aktif, satu PT tidak boleh langsung menjual stok milik PT lain — harus dibuat "
       "transaksi antar entitas terlebih dahulu.",
  impact="Pesanan yang memakai stok milik entitas lain ditolak sampai transfer dibuat. "
       "Menjaga kebenaran laporan laba per PT.",
  example="Aktif → SO di KSC yang mengambil roll milik KANDA ditolak (400)",
  consumers=("services/config_service.py:get_allocation_policy",), risk="high")

E("inventory.stock_analytics.fast_max_days", group="stok-satuan", type="duration",
  default=30, min=1, max=365, step=1, unit="hari", scopes=("global", "entity"),
  simulate="stock_class",
  label="Batas hari barang 'Cepat Laku'",
  help="Barang yang terjual dalam rentang hari ini dihitung Fast Moving.",
  impact="Mengubah klasifikasi Fast/Slow/Dead pada Analitik Stok dan usulan reorder.",
  example="30 hari → terjual 20 hari lalu = Cepat Laku",
  consumers=("services/stock_analytics_service.py",), risk="low")

E("inventory.stock_analytics.slow_max_days", group="stok-satuan", type="duration",
  default=90, min=1, max=1095, step=1, unit="hari", scopes=("global", "entity"),
  simulate="stock_class",
  label="Batas hari barang 'Lambat'",
  help="Di atas batas Cepat Laku sampai batas ini = Slow Moving. Lebih dari itu = Dead Stock.",
  impact="Mengubah daftar barang mati yang perlu didiskon atau dihentikan pembeliannya.",
  example="90 hari → terjual 120 hari lalu = Dead Stock",
  consumers=("services/stock_analytics_service.py",), risk="low")

E("inventory.stock_analytics.velocity_window_days", group="stok-satuan", type="duration",
  default=90, min=7, max=730, step=1, unit="hari", scopes=("global", "entity"),
  label="Jendela hitung kecepatan jual",
  help="Rentang hari ke belakang yang dipakai menghitung rata-rata penjualan harian.",
  impact="Mempengaruhi angka kecepatan jual dan usulan titik pesan ulang.",
  example="90 hari · terjual 900 yard → rata-rata 10 yard/hari",
  consumers=("services/stock_analytics_service.py",), risk="low")

E("inventory.reorder.velocity_window_days", group="stok-satuan", type="duration",
  default=90, min=7, max=730, step=1, unit="hari", scopes=("global", "entity"),
  label="Jendela kecepatan jual untuk reorder",
  help="Rentang hari yang dipakai khusus untuk menghitung usulan pembelian ulang.",
  impact="Mengubah angka usulan qty pada Saran Reorder & Purchase Requisition otomatis.",
  example="60 hari → usulan lebih responsif terhadap tren terbaru",
  consumers=("services/purchase_requisition_service.py",), risk="low")

E("inventory.reorder.safety_days", group="stok-satuan", type="duration", default=7,
  min=0, max=180, step=1, unit="hari", scopes=("global", "entity"), simulate="reorder",
  label="Cadangan hari aman (safety)",
  help="Tambahan hari persediaan di atas lead time supplier agar tidak kehabisan stok.",
  impact="Menaikkan titik pesan ulang → stok lebih aman tapi modal tertahan lebih besar.",
  example="Jual 10 yard/hari · lead time 14 hari · safety 7 → titik pesan 210 yard",
  consumers=("services/purchase_requisition_service.py",), risk="medium")

E("allocation.mode", group="stok-satuan", type="enum", default="auto",
  options=({"value": "auto", "label": "Otomatis penuh"},
           {"value": "assisted", "label": "Diusulkan sistem, dikonfirmasi petugas"},
           {"value": "manual", "label": "Manual sepenuhnya"}),
  scopes=("global", "entity"),
  label="Cara memilih stok untuk pesanan",
  help="Menentukan seberapa besar campur tangan petugas saat sistem memilih roll/lot.",
  impact="Mengubah alur kerja gudang: otomatis langsung terpilih, manual harus dipilih sendiri.",
  example="assisted → sistem mengusulkan 3 roll, petugas menyetujui/menukar",
  consumers=("services/config_service.py:get_allocation_policy", "services/roll_service.py"),
  risk="medium")

E("allocation.priority_order", group="stok-satuan", type="list",
  default=["owner", "lot", "location", "roll_efficiency"], scopes=("global", "entity"),
  label="Urutan prioritas pemilihan stok",
  help="Urutan pertimbangan saat memilih roll. 'owner' (pemilik entitas) SELALU nomor satu "
       "dan tidak bisa digeser.",
  impact="Mengubah roll mana yang dipilih lebih dulu: kesamaan lot, kedekatan gudang, atau efisiensi sisa.",
  example="['owner','location','lot'] → utamakan gudang terdekat sebelum kesamaan lot",
  consumers=("services/config_service.py:_sanitize_alloc", "services/roll_service.py"),
  risk="medium")

E("allocation.lot_mode", group="stok-satuan", type="enum", default="prefer_single",
  options=({"value": "prefer_single", "label": "Usahakan satu lot"},
           {"value": "strict_single", "label": "Wajib satu lot"},
           {"value": "allow_mixed", "label": "Boleh campur lot"}),
  scopes=("global", "entity", "customer"),
  label="Kebijakan campur lot",
  help="Seberapa ketat satu pesanan harus berasal dari satu lot produksi (penting untuk warna).",
  impact="Mode 'wajib satu lot' bisa membuat pesanan tidak bisa dipenuhi walau total stok cukup.",
  example="strict_single → pesanan 600 yard ditolak bila lot terbesar hanya 400 yard",
  consumers=("services/config_service.py:get_allocation_policy", "services/roll_service.py"),
  risk="high")

E("allocation.lot_selection", group="stok-satuan", type="enum", default="fefo",
  options=({"value": "fefo", "label": "FEFO — kedaluwarsa terdekat dulu"},
           {"value": "fifo", "label": "FIFO — masuk pertama keluar pertama"},
           {"value": "smallest_fit", "label": "Sisa terkecil yang cukup"},
           {"value": "largest_fit", "label": "Sisa terbesar"}),
  scopes=("global", "entity"),
  label="Urutan pengambilan lot",
  help="Aturan memilih lot mana yang dipakai lebih dulu.",
  impact="Mengubah umur stok yang keluar dan potensi barang mengendap.",
  example="smallest_fit → habiskan roll sisa 40 yard sebelum membuka roll penuh",
  consumers=("services/config_service.py:get_allocation_policy", "services/roll_service.py"),
  risk="medium")

E("allocation.location_pref", group="stok-satuan", type="enum", default="single_warehouse",
  options=({"value": "single_warehouse", "label": "Satu gudang saja"},
           {"value": "nearest_customer", "label": "Gudang terdekat pelanggan"},
           {"value": "fewest_splits", "label": "Paling sedikit pecah kiriman"}),
  scopes=("global", "entity"),
  label="Preferensi gudang pengambilan",
  help="Menentukan gudang mana yang diutamakan saat stok tersebar.",
  impact="Mempengaruhi biaya kirim dan jumlah surat jalan per pesanan.",
  example="nearest_customer → ambil dari gudang Solo untuk pelanggan Yogyakarta",
  consumers=("services/config_service.py:get_allocation_policy", "services/roll_service.py"),
  risk="low")

E("allocation.allow_intercompany", group="stok-satuan", type="bool", default=True,
  scopes=("global", "entity"),
  label="Boleh memakai stok entitas lain",
  help="Mengizinkan alokasi mengambil stok milik PT lain dalam grup.",
  impact="Bila mati, pesanan hanya dilayani stok milik entitas penerbit pesanan.",
  example="Mati → SO KSC hanya boleh memakai roll milik KSC",
  consumers=("services/config_service.py:_sanitize_alloc", "services/roll_service.py"),
  related=("inventory.intercompany_transfer_required",), risk="high")

E("allocation.allow_partial", group="stok-satuan", type="bool", default=True,
  scopes=("global", "entity"),
  label="Boleh alokasi sebagian",
  help="Mengizinkan sistem mengalokasikan sebagian qty bila stok belum cukup.",
  impact="Bila mati, pesanan yang stoknya kurang tidak dialokasikan sama sekali.",
  example="Aktif → pesanan 1.000 yard dialokasi 700, sisa 300 jadi backorder",
  consumers=("services/config_service.py:_sanitize_alloc", "services/roll_service.py"),
  risk="medium")

E("allocation.dye_lot_strict", group="stok-satuan", type="bool", default=False,
  scopes=("global", "entity", "customer"),
  label="Wajib satu dye lot (warna sama)",
  help="Memaksa seluruh kiriman berasal dari satu nomor celup agar warna persis sama.",
  impact="Menaikkan kualitas warna tetapi memperbesar kemungkinan pesanan tidak bisa dipenuhi.",
  example="Aktif → 2 roll dye lot berbeda tidak boleh digabung dalam 1 pesanan",
  consumers=("services/config_service.py:_sanitize_alloc", "services/roll_service.py"),
  risk="high")

# ═══════════════════════════════════════════════════════════════════════════
# KUALITAS (QC)
# ═══════════════════════════════════════════════════════════════════════════
E("qc.four_point_enabled", group="kualitas", type="bool", default=True,
  scopes=("global", "entity"), simulate="qc_grade",
  label="Aktifkan inspeksi 4-Point",
  help="Metode standar tekstil: cacat dihitung poin berdasarkan panjangnya, lalu jadi grade A/B/C.",
  impact="Bila mati, layar Inspeksi QC tidak meminta rincian 4-point dan grade ditetapkan manual.",
  example="Mati → petugas langsung memilih grade tanpa menghitung poin cacat",
  consumers=("routers/qc_inspection.py:inspect",), risk="medium")

E("qc.grade_thresholds.a_max", group="kualitas", type="decimal", default=20.0,
  min=0, max=1000, step=1, unit="poin/100 yd²", scopes=("global", "entity"),
  simulate="qc_grade",
  label="Poin maksimum Grade A",
  help="Poin cacat 4-point paling tinggi yang masih dinilai Grade A.",
  impact="Mengubah grade hasil inspeksi → mempengaruhi harga jual dan klaim ke supplier.",
  example="a_max 20 · hasil 18 poin → Grade A",
  consumers=("services/qc_inspection_service.py", "services/grade_service.py"),
  related=("qc.grade_thresholds.b_max",), risk="high")

E("qc.grade_thresholds.b_max", group="kualitas", type="decimal", default=40.0,
  min=0, max=1000, step=1, unit="poin/100 yd²", scopes=("global", "entity"),
  simulate="qc_grade",
  label="Poin maksimum Grade B",
  help="Di atas batas Grade A sampai angka ini = Grade B. Lebih dari itu = Grade C.",
  impact="Menentukan kain mana yang turun ke Grade C dan wajib diskon/klaim.",
  example="b_max 40 · hasil 45 poin → Grade C",
  consumers=("services/qc_inspection_service.py", "services/grade_service.py"), risk="high")

# ═══════════════════════════════════════════════════════════════════════════
# TAMPILAN & NAVIGASI
# ═══════════════════════════════════════════════════════════════════════════
E("ui.show_coming_soon", group="tampilan", type="bool", default=True,
  scopes=("global",),
  label="Tampilkan grup menu 'Segera Hadir'",
  help="Menampilkan menu fitur yang belum aktif supaya tim tahu apa yang sedang disiapkan.",
  impact="Bila mati, grup 'Segera Hadir' hilang dari sidebar semua pengguna.",
  example="Mati → sidebar lebih ringkas, hanya menu yang sudah berfungsi",
  consumers=("App.js:buildNavGroups",), risk="low")

E("ui.coming_soon_collapsed", group="tampilan", type="bool", default=True,
  scopes=("global",),
  label="Grup 'Segera Hadir' awalnya tertutup",
  help="Menentukan apakah grup 'Segera Hadir' tampil tertutup saat aplikasi dibuka.",
  impact="Mengubah keadaan awal sidebar; pengguna tetap bisa membuka/menutup sendiri.",
  example="Aktif → grup tampil terlipat, hemat ruang layar",
  consumers=("config/navigationConfig.js:buildNavGroups",), risk="low")

for _role, _default_view, _label in (
    ("admin", "admin", "Admin"),
    ("manager", "reports", "Manager"),
    ("sales", "sales", "Sales"),
    ("warehouse", "operations", "Gudang"),
):
    E(f"role_home.{_role}", group="tampilan", type="text", default=_default_view,
      scopes=("global",),
      label=f"Halaman awal peran {_label}",
      help=f"Layar yang pertama dibuka ketika pengguna dengan peran {_label} masuk aplikasi.",
      impact="Mengubah halaman pendaratan setelah login untuk peran tersebut.",
      example=f"'{_default_view}' → {_label} langsung melihat layar tersebut setelah login",
      consumers=("permissions_config.py", "routers/admin.py"), risk="low")
