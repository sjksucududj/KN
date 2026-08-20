"""i18n_table_id.py — TABEL terjemahan teks antarmuka (Inggris → Indonesia).

Data saja, tanpa logika, supaya `fix_i18n_id.py` tetap kecil dan tabel ini bisa
di-review pemilik seperti daftar kata. Kunci = teks PERSIS yang tampil di layar
(hasil `scripts/audit_i18n_id.py`), nilai = terjemahan yang dipakai.

Aturan penyusunan:
  · terjemahan mengikuti bahasa kerja tim (gudang/sales/keuangan), bukan bahasa kamus;
  · singkatan dokumen (PO, SO, PR, RFQ, GR, SKU, QC) DIPERTAHANKAN;
  · istilah tekstil (roll, lot, grade, makloon, dye-lot) DIPERTAHANKAN;
  · kata "sales" tetap = orang/tim penjualan (bukan "penjualan").
"""

TABEL: dict[str, str] = {
    # ── status stok & roll ────────────────────────────────────────────────
    "Available": "Tersedia",
    "Available Qty": "Jml Tersedia",
    "Available qty": "Jml tersedia",
    "Available Stock": "Stok Tersedia",
    "Reserved": "Dipesan",
    "RESERVED": "DIPESAN",
    "Reserved Qty": "Jml Dipesan",
    "Reserved qty": "Jml dipesan",
    "Reserved Stock": "Stok Dipesan",
    "Committed": "Dialokasikan",
    "Picked": "Sudah Diambil",
    "Picked:": "Sudah Diambil:",
    "Picked (Ready)": "Sudah Diambil (Siap)",
    "Partially Picked": "Sebagian Diambil",
    "Picked Qty *": "Jml Diambil *",
    "Packed": "Sudah Dikemas",
    "Quarantine": "Karantina",
    "Blocked": "Diblokir",
    "Damaged": "Rusak",
    "Sold": "Terjual",
    "Sisa (Available)": "Sisa (Tersedia)",
    "dikembalikan ke stok (available)": "dikembalikan ke stok (tersedia)",
    "In-Transit (Inbound)": "Dalam Perjalanan (Masuk)",
    "In-Transit (Transfer)": "Dalam Perjalanan (Transfer)",
    "In-Transit (Antar-PT)": "Dalam Perjalanan (Antar-PT)",
    "In-Transit (Sales)": "Dalam Perjalanan (Penjualan)",
    "In-transit": "Dalam Perjalanan",
    "Stok Multi-Bucket (WIP / Hold / In-transit)": "Stok Multi-Kantong (WIP / Ditahan / Dalam Perjalanan)",
    "Sebagian dipeg ke barang masuk (PO / in-transit).": "Sebagian dipatok ke barang masuk (PO / dalam perjalanan).",

    # ── status dokumen ────────────────────────────────────────────────────
    "Draft": "Draf",
    "draft": "draf",
    "Draft Order": "Draf Pesanan",
    "Simpan Draft": "Simpan Draf",
    "Tambah ke Draft": "Tambah ke Draf",
    "Kembali ke draft": "Kembali ke draf",
    "Usulan (draft)": "Usulan (draf)",
    "Hapus retur draft": "Hapus retur draf",
    "Jadikan Draft Eliminasi": "Jadikan Draf Eliminasi",
    "Draft — belum boleh dipakai proofing": "Draf — belum boleh dipakai proofing",
    "Retur draft ini akan dihapus permanen. Tindakan tidak dapat dibatalkan.":
        "Retur draf ini akan dihapus permanen. Tindakan tidak dapat dibatalkan.",
    "Pending": "Menunggu",
    "Approval Pending": "Persetujuan Menunggu",
    "QC Pending": "QC Menunggu",
    "Cycle Count Pending": "Stock Opname Menunggu",
    "Pending SO": "SO Menunggu",
    "No. Pending SO": "No. SO Menunggu",
    "Pending Demand": "Permintaan Menunggu",
    "Demand Pending (SO)": "Permintaan Menunggu (SO)",
    "Tidak ada pending demand.": "Tidak ada permintaan menunggu.",
    "Tidak ada Pending SO. Semua permintaan terpenuhi dari stok.":
        "Tidak ada SO Menunggu. Semua permintaan terpenuhi dari stok.",
    "Approved": "Disetujui",
    "Approved by:": "Disetujui oleh:",
    "Dari PR approved": "Dari PR disetujui",
    "Tidak ada PR approved yang belum dikonversi.": "Tidak ada PR disetujui yang belum dikonversi.",
    "Purchase Requisition (approved)": "Permintaan Pembelian (disetujui)",
    "Rejected": "Ditolak",
    "Cancelled": "Dibatalkan",
    "Completed": "Selesai",
    "Overdue": "Lewat Jatuh Tempo",
    "AR Overdue": "Piutang Lewat Tempo",
    "Jatuh Tempo (Overdue)": "Jatuh Tempo (Lewat Tempo)",
    "Penagihan (Overdue)": "Penagihan (Lewat Tempo)",
    "Penagihan Saya (Overdue)": "Penagihan Saya (Lewat Tempo)",
    "Overdue per Sales": "Lewat Tempo per Sales",
    "Tidak ada overdue 🎉": "Tidak ada tagihan lewat tempo 🎉",
    "Outstanding": "Belum Lunas",
    "AR Outstanding": "Piutang Belum Lunas",
    "On-Order": "Dalam Pesanan",
    "On-Request": "Dalam Permintaan",
    "Available + On-Order (PO terbuka) + On-Request (PR terbuka)":
        "Tersedia + Dalam Pesanan (PO terbuka) + Dalam Permintaan (PR terbuka)",

    # ── persetujuan ───────────────────────────────────────────────────────
    "Approval": "Persetujuan",
    "Persetujuan (Approval)": "Persetujuan",
    "Approval Harga": "Persetujuan Harga",
    "Price Approval": "Persetujuan Harga",
    "Approval Harga Khusus": "Persetujuan Harga Khusus",
    "Approval Pembelian": "Persetujuan Pembelian",
    "Approval Rules": "Aturan Persetujuan",
    "Approval Kredit": "Persetujuan Kredit",
    "Approval Kredit (Over-limit)": "Persetujuan Kredit (Melebihi Batas)",
    "Approval Nilai Order": "Persetujuan Nilai Pesanan",
    "Menunggu Approval": "Menunggu Persetujuan",
    "Waiting Approval": "Menunggu Persetujuan",
    "Requires Approval": "Butuh Persetujuan",
    "Butuh approval": "Butuh persetujuan",
    "Butuh approval role": "Butuh persetujuan peran",
    "Ajukan Approval": "Ajukan Persetujuan",
    "Minta Approval Kredit": "Minta Persetujuan Kredit",
    "Submit untuk Approval": "Kirim untuk Persetujuan",
    "Ajukan untuk Approval": "Ajukan untuk Persetujuan",
    "Diajukan untuk approval": "Diajukan untuk persetujuan",
    "Diajukan ke Approval": "Diajukan ke Persetujuan",
    "Alasan approval...": "Alasan persetujuan…",
    "Alasan permintaan approval kredit (wajib)": "Alasan permintaan persetujuan kredit (wajib)",
    "dipaksa melewati approval": "dipaksa melewati persetujuan",
    "mengulang approval dari awal": "mengulang persetujuan dari awal",
    "Riwayat / Timeline Approval": "Riwayat / Jejak Persetujuan",
    "approval → inspeksi → penyelesaian": "persetujuan → inspeksi → penyelesaian",
    "Hanya admin yang dapat manage approval rules.":
        "Hanya admin yang dapat mengelola aturan persetujuan.",
    "Konfigurasi approval rules untuk berbagai entity types":
        "Konfigurasi aturan persetujuan untuk berbagai jenis dokumen",
    "Memuat approval rules...": "Memuat aturan persetujuan…",
    "Belum ada approval rules.": "Belum ada aturan persetujuan.",
    "Langsung ajukan approval (jika tidak dicentang, disimpan sebagai draft)":
        "Langsung ajukan persetujuan (jika tidak dicentang, disimpan sebagai draf)",
    "Langsung ajukan approval (jika di bawah threshold, otomatis disetujui)":
        "Langsung ajukan persetujuan (jika di bawah ambang, otomatis disetujui)",
    "Cari pengaturan… coba “denda”, “toleransi”, “PPN”, “approval”":
        "Cari pengaturan… coba “denda”, “toleransi”, “PPN”, “persetujuan”",
    "Submit (minta approval manager)": "Kirim (minta persetujuan manajer)",

    # ── pesanan (order) ───────────────────────────────────────────────────
    "Order": "Pesanan",
    "Order:": "Pesanan:",
    "No. Order": "No. Pesanan",
    "Total Order": "Total Pesanan",
    "Per order": "Per pesanan",
    "Avg Order": "Rata-rata Pesanan",
    "Mode Order": "Mode Pesanan",
    "Order List": "Daftar Pesanan",
    "Tab Order List": "Tab Daftar Pesanan",
    "Order Control": "Kendali Pesanan",
    "Order Dashboard": "Dasbor Pesanan",
    "Order Terbuka": "Pesanan Terbuka",
    "Order Terbaru": "Pesanan Terbaru",
    "Order Hari Ini": "Pesanan Hari Ini",
    "Order / Closing": "Pesanan / Penutupan",
    "Order Dibatalkan": "Pesanan Dibatalkan",
    "Order piutang tujuan": "Pesanan piutang tujuan",
    "Order tersimpan sebagai": "Pesanan tersimpan sebagai",
    "Tanpa Order": "Tanpa Pesanan",
    "Buat Order": "Buat Pesanan",
    "Manual per Order": "Manual per Pesanan",
    "Batalkan Order": "Batalkan Pesanan",
    "Submit Order": "Kirim Pesanan",
    "Diskon Order (%)": "Diskon Pesanan (%)",
    "Diskon order": "Diskon pesanan",
    "SO · Nilai Order": "SO · Nilai Pesanan",
    "Berbuah Order": "Berbuah Pesanan",
    "detail Order": "detail Pesanan",
    "Belum ada order": "Belum ada pesanan",
    "Belum ada order.": "Belum ada pesanan.",
    "Belum ada data order": "Belum ada data pesanan",
    "Belum ada data order untuk periode ini": "Belum ada data pesanan untuk periode ini",
    "Memuat order…": "Memuat pesanan…",
    "Lanjut order": "Lanjut ke pesanan",
    "Buka order room": "Buka ruang pesanan",
    "Pilih Order": "Pilih Pesanan",
    "Cari Order (Opsional)": "Cari Pesanan (Opsional)",
    "Cari no. order / produk…": "Cari no. pesanan / produk…",
    "Cari no. order / mitra / produk…": "Cari no. pesanan / mitra / produk…",
    "Cari order number, customer, produk...": "Cari nomor pesanan, pelanggan, produk…",
    "Tidak ada order terbuka.": "Tidak ada pesanan terbuka.",
    "Tidak ada order terbuka. 🎉": "Tidak ada pesanan terbuka. 🎉",
    "Konfirmasi & Buat Order": "Konfirmasi & Buat Pesanan",
    "Langkah order berikutnya": "Langkah pesanan berikutnya",
    "Nilai order yang diminta (Rp)": "Nilai pesanan yang diminta (Rp)",
    "Dialokasikan otomatis ke order terbuka tertua lebih dulu.":
        "Dialokasikan otomatis ke pesanan terbuka tertua lebih dulu.",
    "Pilih order untuk lihat detail & aksi": "Pilih pesanan untuk lihat detail & aksi",
    "Pilih produk dari grid POS untuk mulai membuat order.":
        "Pilih produk dari grid POS untuk mulai membuat pesanan.",
    "Tidak ada order piutang terbuka untuk pelanggan ini.":
        "Tidak ada pesanan piutang terbuka untuk pelanggan ini.",
    "Tidak ada barang pendingan pada order ini. Anda tetap bisa meminta":
        "Tidak ada barang pendingan pada pesanan ini. Anda tetap bisa meminta",
    "bila pelanggan ingin order ulang.": "bila pelanggan ingin pesan ulang.",
    "Semua produk pada order ini sudah diminta. Buka layar":
        "Semua produk pada pesanan ini sudah diminta. Buka layar",
    "Tidak ada produk yang bisa diminta dari order ini.":
        "Tidak ada produk yang bisa diminta dari pesanan ini.",
    "mis. sisa beberapa batch disatukan untuk 1 order besar":
        "mis. sisa beberapa batch disatukan untuk 1 pesanan besar",
    "Umur dihitung dari tanggal order + term pembayaran. Kolom":
        "Umur dihitung dari tanggal pesanan + termin pembayaran. Kolom",
    "mengurangi saldo & melunasi piutang order (Dr 2-1450 / Cr 1-1200). Berlaku untuk order dari":
        "mengurangi saldo & melunasi piutang pesanan (Dr 2-1450 / Cr 1-1200). Berlaku untuk pesanan dari",
    "double-order / double-request": "pesanan ganda / permintaan ganda",
    "Generate outbound dari confirmed order": "Buat barang keluar dari pesanan terkonfirmasi",
    "Konfirmasi diperlukan saat membuat order — warna/dye-lot bisa berbeda antar lot.":
        "Konfirmasi diperlukan saat membuat pesanan — warna/dye-lot bisa berbeda antar lot.",
    "Reserved material akan otomatis dilepas jika order dibatalkan atau expired.":
        "Bahan yang dipesan akan otomatis dilepas jika pesanan dibatalkan atau kedaluwarsa.",

    # ── pelanggan ─────────────────────────────────────────────────────────
    "Customer": "Pelanggan",
    "Customer:": "Pelanggan:",
    "Customer Baru": "Pelanggan Baru",
    "Customer aktif": "Pelanggan aktif",
    "Customer Info": "Info Pelanggan",
    "Customer & Alamat": "Pelanggan & Alamat",
    "Top Customer": "Pelanggan Teratas",
    "Per Customer": "Per Pelanggan",
    "Master Customer": "Master Pelanggan",
    "Pilih Customer": "Pilih Pelanggan",
    "Buat Customer": "Buat Pelanggan",
    "Simpan Customer": "Simpan Pelanggan",
    "Nama customer": "Nama pelanggan",
    "Nama customer baru": "Nama pelanggan baru",
    "Target Customer Baru": "Target Pelanggan Baru",
    "SO / Customer": "SO / Pelanggan",
    "Ship to Customer": "Kirim ke Pelanggan",
    "Price List per Customer": "Daftar Harga per Pelanggan",
    "Customer minta Faktur Pajak": "Pelanggan minta Faktur Pajak",
    "Customer baru langsung aktif": "Pelanggan baru langsung aktif",
    "Bonus / Customer Baru (Rp)": "Bonus / Pelanggan Baru (Rp)",
    "Belum ada data customer": "Belum ada data pelanggan",
    "Pilih customer dulu.": "Pilih pelanggan dulu.",
    "Pilih customer dulu untuk membuat pesanan.": "Pilih pelanggan dulu untuk membuat pesanan.",
    "-- Pilih customer --": "-- Pilih pelanggan --",
    "-- Pilih Customer --": "-- Pilih Pelanggan --",
    "-- Pilih customer dari master --": "-- Pilih pelanggan dari master --",
    "— Pilih Customer —": "— Pilih Pelanggan —",
    "— pilih customer —": "— pilih pelanggan —",
    "atau nama customer (tanpa master)": "atau nama pelanggan (tanpa master)",
    "Cari customer / produk...": "Cari pelanggan / produk…",
    "Cari nomor / customer…": "Cari nomor / pelanggan…",
    "Cari nomor / customer / deskripsi...": "Cari nomor / pelanggan / keterangan…",
    "Cari nomor / pesanan / customer...": "Cari nomor / pesanan / pelanggan…",
    "Cari nomor / order / customer / NSFP": "Cari nomor / pesanan / pelanggan / NSFP",
    "Retur (customer kembalikan barang)": "Retur (pelanggan kembalikan barang)",
    "Tidak ada customer untuk entitas pemilik roll ini.":
        "Tidak ada pelanggan untuk entitas pemilik roll ini.",
    "Tambah saldo customer (potong bon) + barang masuk stok":
        "Tambah saldo pelanggan (potong bon) + barang masuk stok",
    "Delivery (permintaan customer / kredit)": "Pengiriman (permintaan pelanggan / kredit)",
    "mis. Kirim sampel ke customer": "mis. Kirim sampel ke pelanggan",
    "mis. Pelunasan piutang customer X": "mis. Pelunasan piutang pelanggan X",
    "mis. Transaksi dibatalkan customer": "mis. Transaksi dibatalkan pelanggan",
    "Alasan (wajib): nego customer, kompetitor, dll.":
        "Alasan (wajib): nego pelanggan, kompetitor, dll.",
    "Cara menambah produk, customer, warehouse baru":
        "Cara menambah produk, pelanggan, gudang baru",
    "CRUD product · customer · warehouse · UOM · template · user":
        "Kelola produk · pelanggan · gudang · UOM · template · pengguna",
    "Retur barang, Barang Sisa (BS), penggantian, komplain & garansi (aftersales) dari customer":
        "Retur barang, Barang Sisa (BS), penggantian, komplain & garansi (purna jual) dari pelanggan",
    "Terisi dari default customer, bisa diubah per order (total split 100%).":
        "Terisi dari bawaan pelanggan, bisa diubah per pesanan (total bagi 100%).",
    "Terisi otomatis dari default customer — bisa diubah khusus untuk order ini "
    "(PIC + co-sales, total split 100%).":
        "Terisi otomatis dari bawaan pelanggan — bisa diubah khusus untuk pesanan ini "
        "(PIC + pendamping sales, total bagi 100%).",

    # ── dokumen pembelian & penjualan ─────────────────────────────────────
    "Purchase Requisition": "Permintaan Pembelian",
    "Purchase Requisition (PR)": "Permintaan Pembelian (PR)",
    "Purchase Requisition (Permintaan Pembelian)": "Permintaan Pembelian (PR)",
    "Buat Purchase Requisition": "Buat Permintaan Pembelian",
    "Belum ada Purchase Requisition. Klik": "Belum ada Permintaan Pembelian. Klik",
    "Jembatan ke pengadaan (Purchase Requisition)": "Jembatan ke pengadaan (Permintaan Pembelian)",
    "Sudah ada Purchase Requisition terbuka untuk produk ini — hindari PR ganda":
        "Sudah ada Permintaan Pembelian terbuka untuk produk ini — hindari PR ganda",
    "Purchase Order": "Pesanan Pembelian",
    "Purchase Order (bisa lebih dari satu)": "Pesanan Pembelian (bisa lebih dari satu)",
    "Rincian Purchase Order": "Rincian Pesanan Pembelian",
    "Belum ada Purchase Order": "Belum ada Pesanan Pembelian",
    "Buat Purchase Order Baru": "Buat Pesanan Pembelian Baru",
    "Batalkan Purchase Order": "Batalkan Pesanan Pembelian",
    "Memuat purchase order...": "Memuat pesanan pembelian…",
    "Receiving dari Purchase Order": "Penerimaan dari Pesanan Pembelian",
    "Sales Order": "Pesanan Penjualan",
    "Ringkasan Sales Order": "Ringkasan Pesanan Penjualan",
    "Picking & Dispatch Sales Order": "Pengambilan & Pengiriman Pesanan Penjualan",
    "POS, Sales Order, & Invoice": "POS, Pesanan Penjualan, & Faktur",
    "Cara approve sales order yang masuk": "Cara menyetujui pesanan penjualan yang masuk",
    "Cara fulfill sales order dari warehouse": "Cara memenuhi pesanan penjualan dari gudang",
    "Panduan step-by-step membuat sales order dari POS":
        "Panduan langkah demi langkah membuat pesanan penjualan dari POS",
    "Pilih rentang tanggal lain atau pastikan ada Sales Order terkonfirmasi.":
        "Pilih rentang tanggal lain atau pastikan ada Pesanan Penjualan terkonfirmasi.",
    "Konversi special order menjadi Sales Order standar":
        "Ubah pesanan khusus menjadi Pesanan Penjualan standar",
    "Semua persetujuan yang menunggu keputusan Anda — Sales Order (nilai/kredit/harga), "
    "PO, retur & cycle count.":
        "Semua persetujuan yang menunggu keputusan Anda — Pesanan Penjualan "
        "(nilai/kredit/harga), PO, retur & stock opname.",
    "Special Order": "Pesanan Khusus",
    "Special Order (OD)": "Pesanan Khusus (OD)",
    "Special Order (MTO)": "Pesanan Khusus (MTO)",
    "Buat Special Order": "Buat Pesanan Khusus",
    "Buat Special Order Baru": "Buat Pesanan Khusus Baru",
    "Buat Special Order Pertama": "Buat Pesanan Khusus Pertama",
    "Kembali ke Daftar Special Order": "Kembali ke Daftar Pesanan Khusus",
    "Contoh: Special Order High Value": "Contoh: Pesanan Khusus Bernilai Besar",
    "Pesanan custom / made-to-order": "Pesanan khusus / dibuat sesuai pesanan",
    "Ada item non-katalog (dari Special Order) — tidak bisa auto-konversi ke PO. "
    "Buat produk dulu atau proses manual.":
        "Ada item non-katalog (dari Pesanan Khusus) — tidak bisa dikonversi otomatis ke PO. "
        "Buat produk dulu atau proses manual.",
    "Invoice": "Faktur",
    "Invoice (PPN)": "Faktur (PPN)",
    "Invoice Komersial": "Faktur Komersial",
    "No. Invoice": "No. Faktur",
    "No. Invoice Supplier": "No. Faktur Supplier",
    "No. Invoice Penyedia": "No. Faktur Penyedia",
    "invoice sudah terbit": "faktur sudah terbit",
    "Nota Kredit (Credit Note)": "Nota Kredit",
    "Credit Note diskon tanpa gerak stok": "Nota Kredit diskon tanpa gerak stok",
    "Work Order": "Perintah Kerja",
    "Work Order Baru": "Perintah Kerja Baru",
    "Buat Work Order": "Buat Perintah Kerja",
    "Belum ada Work Order": "Belum ada Perintah Kerja",
    "Buat Work Order dari BOM aktif untuk memproduksi barang jadi.":
        "Buat Perintah Kerja dari BOM aktif untuk memproduksi barang jadi.",
    "BOM (resep) & Work Order · konsumsi bahan → barang jadi (Roll-as-SSOT)":
        "BOM (resep) & Perintah Kerja · konsumsi bahan → barang jadi (Roll-as-SSOT)",
    "Packing List": "Daftar Kemasan",
    "Surat Pengambilan (Picking)": "Surat Pengambilan Barang",

    # ── proses gudang ─────────────────────────────────────────────────────
    "Inbound": "Barang Masuk",
    "Outbound": "Barang Keluar",
    "Tab Inbound": "Tab Barang Masuk",
    "Tab Outbound": "Tab Barang Keluar",
    "Inbound Tasks": "Tugas Barang Masuk",
    "Outbound Tasks": "Tugas Barang Keluar",
    "Tidak ada inbound task": "Tidak ada tugas barang masuk",
    "Tidak ada outbound task": "Tidak ada tugas barang keluar",
    "Buat inbound task": "Buat tugas barang masuk",
    "Create Inbound Task": "Buat Tugas Barang Masuk",
    "Pilih Outbound Task": "Pilih Tugas Barang Keluar",
    "Eskalasi Inbound & Outbound": "Eskalasi Barang Masuk & Barang Keluar",
    "sebelum inbound task dibuat.": "sebelum tugas barang masuk dibuat.",
    "berdasarkan nilai baru. Task inbound yang belum menerima barang akan dibuat ulang "
    "setelah disetujui.":
        "berdasarkan nilai baru. Tugas barang masuk yang belum menerima barang akan "
        "dibuat ulang setelah disetujui.",
    "Receiving": "Penerimaan",
    "Receiving dari PO": "Penerimaan dari PO",
    "Receiving selesai!": "Penerimaan selesai!",
    "Scan & Submit Receipt": "Scan & Kirim Penerimaan",
    "Picking": "Pengambilan",
    "Start Picking": "Mulai Pengambilan",
    "Submit Pick": "Kirim Pengambilan",
    "Rilis ke Picking Sekarang": "Rilis ke Pengambilan Sekarang",
    "Pengambilan terjadwal — picking di-hold.": "Pengambilan terjadwal — pengambilan ditahan.",
    "Picking list ditahan (hold) sampai tanggal ini — gudang baru menyiapkan barang pada/ "
    "setelah tanggal pengambilan.":
        "Daftar pengambilan ditahan sampai tanggal ini — gudang baru menyiapkan barang pada/ "
        "setelah tanggal pengambilan.",
    "Packing": "Pengemasan",
    "Dispatch": "Pengiriman",
    "Pick & Dispatch": "Ambil & Kirim",
    "Pick & dispatch SO": "Ambil & kirim SO",
    "Inbound · Outbound · Picking · Packing · Dispatch":
        "Barang Masuk · Barang Keluar · Pengambilan · Pengemasan · Pengiriman",
    "Putaway": "Penempatan Rak",
    "belum putaway": "belum ditempatkan ke rak",
    "Lokasi & Putaway": "Lokasi & Penempatan Rak",
    "Lokasi Gudang & Putaway": "Lokasi Gudang & Penempatan Rak",
    "Antrean Putaway — roll belum ditempatkan": "Antrean Penempatan Rak — roll belum ditempatkan",
    "Zone → Rack → Level → Bin. Putaway menempatkan roll ke bin "
    "(tidak mengubah stok/saldo).":
        "Zona → Rak → Tingkat → Bin. Penempatan rak menaruh roll ke bin "
        "(tidak mengubah stok/saldo).",
    "Diproses (Keep/Picked)": "Diproses (Ditahan/Sudah Diambil)",
    "Barang Rusak — simpan di gudang (damaged)": "Barang Rusak — simpan di gudang (rusak)",
    "Loading struktur gudang...": "Memuat struktur gudang…",
    "Kelola perpindahan inventory antar warehouse": "Kelola perpindahan persediaan antar gudang",
    "Tidak ada roll available dari asal ini. Pastikan supplier/PO sesuai.":
        "Tidak ada roll tersedia dari asal ini. Pastikan supplier/PO sesuai.",

    # ── persediaan & stock opname ─────────────────────────────────────────
    "Inventory": "Persediaan",
    "Inventory Status Board · ATP": "Papan Status Persediaan · ATP",
    "Overview Stok": "Ringkasan Stok",
    "Cara cek dan kelola inventory stock": "Cara cek dan kelola stok persediaan",
    "Cycle Count": "Stock Opname",
    "Buat Sesi Cycle Count Baru": "Buat Sesi Stock Opname Baru",
    "Belum ada sesi cycle count.": "Belum ada sesi stock opname.",

    # ── aksi & tombol ─────────────────────────────────────────────────────
    "Edit": "Ubah",
    "Batal edit": "Batal ubah",
    "Batal Edit": "Batal Ubah",
    "Edit Akun": "Ubah Akun",
    "Submit": "Kirim",
    "Submit Scan": "Kirim Hasil Scan",
    "Submit ke Manager": "Kirim ke Manajer",
    "Auto-submit": "Kirim otomatis",
    "Cancel": "Batal",
    "Close": "Tutup",
    "Close detail": "Tutup detail",
    "Close tour": "Tutup panduan",
    "Next": "Lanjut",
    "Next step": "Langkah berikutnya",
    "Print": "Cetak",
    "Print Label": "Cetak Label",
    "Print Center": "Pusat Cetak",
    "Print Center & Labels": "Pusat Cetak & Label",
    "Buka print view": "Buka tampilan cetak",
    "Buka dokumen / print": "Buka dokumen / cetak",
    "PFP (siap print)": "PFP (siap cetak)",
    "Import": "Impor",
    "Hasil Import": "Hasil Impor",
    "Konfirmasi Import": "Konfirmasi Impor",
    "Import Fingerprint": "Impor Sidik Jari",
    "Import Log Mesin Fingerprint (ZKTeco)": "Impor Log Mesin Sidik Jari (ZKTeco)",
    "Idempotent: import ulang tidak menggandakan data.":
        "Idempoten: impor ulang tidak menggandakan data.",
    "Export": "Ekspor",
    "Export CSV": "Ekspor CSV",
    "Search Produk": "Cari Produk",
    "Loading...": "Memuat…",

    # ── label umum ────────────────────────────────────────────────────────
    "Quantity": "Jumlah",
    "Quantity:": "Jumlah:",
    "Code": "Kode",
    "Notes": "Catatan",
    "Description": "Keterangan",
    "Overview": "Ringkasan",
    "Resolution Notes * (wajib)": "Catatan Penyelesaian * (wajib)",
    "Tim Sales & Split (order ini)": "Tim Sales & Bagi Hasil (pesanan ini)",
    "Tim Sales & Split Insentif (order ini)": "Tim Sales & Bagi Insentif (pesanan ini)",
    "Tim Sales (order ini):": "Tim Sales (pesanan ini):",
    "Belum ada axis varian — edit template untuk menambah Warna/Grade/Lebar.":
        "Belum ada sumbu varian — ubah template untuk menambah Warna/Grade/Lebar.",
    "Template belum punya axis. Edit template & tambah Warna/Grade/Lebar dulu.":
        "Template belum punya sumbu. Ubah template & tambah Warna/Grade/Lebar dulu.",
    "Karyawan akan ditandai resigned dan tidak muncul di daftar aktif. "
    "Anda dapat mengubah statusnya kembali via edit.":
        "Karyawan akan ditandai keluar (resign) dan tidak muncul di daftar aktif. "
        "Anda dapat mengubah statusnya kembali lewat Ubah.",
    "Entitas legal grup (PT/CV). Data transaksi (SO/PO/Invoice) akan di-scope per entitas "
    "via Entity Switcher.":
        "Entitas legal grup (PT/CV). Data transaksi (SO/PO/Faktur) dibatasi per entitas "
        "lewat pemilih entitas.",
    "Menampilkan tagihan overdue + akan jatuh tempo ≤ 60 hari. Reminder bersifat on-demand "
    "(tanpa kirim ke luar).":
        "Menampilkan tagihan lewat tempo + akan jatuh tempo ≤ 60 hari. Pengingat bersifat "
        "sesuai permintaan (tanpa kirim ke luar).",
    "Jatuh tempo AR = tanggal order + termin pelanggan; AP = due date tagihan. "
    "Posisi kas awal = saldo GL Kas/Bank.":
        "Jatuh tempo AR = tanggal pesanan + termin pelanggan; AP = tanggal jatuh tempo "
        "tagihan. Posisi kas awal = saldo GL Kas/Bank.",
    "Buat RFQ dari PR approved atau manual untuk membandingkan harga supplier.":
        "Buat RFQ dari PR disetujui atau manual untuk membandingkan harga supplier.",

    # ══ PUTARAN 2 — ekor panjang (setelah kamus diperluas) ══════════════════
    # ── termin & keuangan ──
    "Term": "Termin",
    "Term:": "Termin:",
    "Term (hari)": "Termin (hari)",
    "Term & Lot": "Termin & Lot",
    "Pilih Term": "Pilih Termin",
    "Term Pembayaran": "Termin Pembayaran",
    "Term Pembayaran:": "Termin Pembayaran:",
    "Catatan kontrak (term, syarat, dll)...": "Catatan kontrak (termin, syarat, dll)…",
    "Daftar label meta yang disembunyikan, pisahkan dengan koma. mis: Term, Referensi":
        "Daftar label meta yang disembunyikan, pisahkan dengan koma. mis: Termin, Referensi",
    "Credit limit (Rp)": "Batas kredit (Rp)",
    "Potong Bon (AP Credit)": "Potong Bon (Kredit AP)",
    "Void": "Anulir",
    "Void Transaksi": "Anulir Transaksi",
    "Void Jurnal": "Anulir Jurnal",
    "Batalkan (void) penerimaan": "Batalkan (anulir) penerimaan",
    "Void transaksi kas ini? Saldo akan disesuaikan otomatis. "
    "Tindakan tidak dapat dibatalkan.":
        "Anulir transaksi kas ini? Saldo akan disesuaikan otomatis. "
        "Tindakan tidak dapat dibatalkan.",
    "Diturunkan dari jurnal (non-void). Laba Bersih = Pendapatan − HPP − Beban Operasional.":
        "Diturunkan dari jurnal (bukan anulir). Laba Bersih = Pendapatan − HPP − "
        "Beban Operasional.",
    "Reversal": "Pembalikan",
    "Batal / Reversal": "Batal / Pembalikan",
    "dibatalkan (reversal)": "dibatalkan (pembalikan)",
    "Batalkan / Reversal Store Credit": "Batalkan / Balikkan Store Credit",
    "Store credit terbit dari retur — batalkan lewat reversal retur sumbernya":
        "Store credit terbit dari retur — batalkan lewat pembalikan retur sumbernya",
    "Basis nilai barang kembali (reversal HPP ke stok) =":
        "Basis nilai barang kembali (pembalikan HPP ke stok) =",
    "Refund": "Pengembalian Dana",
    "Refund →": "Pengembalian Dana →",
    "Refund (kas)": "Pengembalian Dana (kas)",
    "Refund Tunai": "Pengembalian Dana Tunai",
    "Tidak Ada Refund": "Tanpa Pengembalian Dana",
    "Mode Refund yang Diizinkan": "Mode Pengembalian Dana yang Diizinkan",
    "Akun Kas/Bank penerima refund": "Akun Kas/Bank penerima pengembalian dana",
    "Akun Kas/Bank Refund Tunai": "Akun Kas/Bank Pengembalian Dana Tunai",
    "AR / Piutang & Aging": "AR / Piutang & Umur",
    "Stock Aging": "Umur Stok",
    "Aging Persediaan (nilai per umur)": "Umur Persediaan (nilai per umur)",
    "Proporsional Nilai (cost × panjang)": "Proporsional Nilai (biaya × panjang)",
    "Tanpa Cost": "Tanpa Biaya",
    "Cost/Unit": "Biaya/Satuan",
    "Jurnal Antar-PT (at-cost)": "Jurnal Antar-PT (sebesar biaya)",

    # ── pengaturan & aturan ──
    "Setting": "Pengaturan",
    "Buka setting": "Buka pengaturan",
    "Tidak ada setting yang cocok.": "Tidak ada pengaturan yang cocok.",
    "Setting ini TIDAK dipakai sistem saat ini.": "Pengaturan ini TIDAK dipakai sistem saat ini.",
    "Bagian sistem yang memakai setting ini": "Bagian sistem yang memakai pengaturan ini",
    "Cari setting… (mis. denda, PPN, toleransi)": "Cari pengaturan… (mis. denda, PPN, toleransi)",
    "Belum ada perubahan pada setting ini — nilainya masih sesuai bawaan sistem.":
        "Belum ada perubahan pada pengaturan ini — nilainya masih sesuai bawaan sistem.",
    "Nama Rule": "Nama Aturan",
    "Rule Name": "Nama Aturan",
    "Buat Rule Baru": "Buat Aturan Baru",
    "Buat Rule Pertama": "Buat Aturan Pertama",
    "Deskripsi rule...": "Keterangan aturan…",
    "Threshold Value": "Nilai Ambang",
    "Threshold Field": "Kolom Ambang",
    "Approvals": "Persetujuan",

    # ── gudang & tugas ──
    "Warehouse": "Gudang",
    "Warehouse *": "Gudang *",
    "Pilih Warehouse": "Pilih Gudang",
    "Simpan Warehouse": "Simpan Gudang",
    "Filter per Warehouse": "Filter per Gudang",
    "Masuk sebagai Admin, Sales, Manager, atau Warehouse untuk akses menu dan aksi "
    "sesuai permission.":
        "Masuk sebagai Admin, Sales, Manager, atau Gudang untuk akses menu dan aksi "
        "sesuai izin.",
    "Scan task": "Scan tugas",
    "Task Menunggu QC": "Tugas Menunggu QC",
    "Pilih Task PO": "Pilih Tugas PO",
    "Pilih task dari daftar": "Pilih tugas dari daftar",
    "Tidak ada roll untuk task ini.": "Tidak ada roll untuk tugas ini.",
    "Task terminal: scan baru diblokir.": "Tugas terminal: scan baru diblokir.",
    "Semua task berjalan lancar!": "Semua tugas berjalan lancar!",
    "Tidak ada escalated tasks": "Tidak ada tugas yang dieskalasi",
    "Review & resolve escalated tasks": "Tinjau & selesaikan tugas yang dieskalasi",
    "Resolve & Continue Task": "Selesaikan & Lanjutkan Tugas",
    "Scan barcode di form task di bawah": "Scan barcode di formulir tugas di bawah",
    "Klik baris task untuk buka scan form": "Klik baris tugas untuk buka formulir scan",
    "Klik baris task untuk buka pick form": "Klik baris tugas untuk buka formulir pengambilan",
    "Alasan escalation (contoh: Stock fisik hanya 40m, sistem 50m)":
        "Alasan eskalasi (contoh: Stok fisik hanya 40m, sistem 50m)",
    "Hold": "Ditahan",
    "Ditahan (Hold)": "Ditahan",
    "Jenis Hold": "Jenis Tahanan",
    "Lepas Hold": "Lepas Tahanan",
    "Tidak ada hold aktif.": "Tidak ada tahanan aktif.",
    "cth: hold untuk PO besar": "cth: tahan untuk PO besar",
    "roll di-pegging (soft hold)": "roll dipatok (ditahan lunak)",

    # ── stok & analitik ──
    "Dead Stock": "Stok Mati",
    "Stock Analytics": "Analitik Stok",
    "Stock Analytics (Fast/Slow/Dead)": "Analitik Stok (Cepat/Lambat/Mati)",
    "Stock Analytics — Fast / Slow / Dead": "Analitik Stok — Cepat / Lambat / Mati",
    "Waiting Stock (Backorder)": "Menunggu Stok (Backorder)",
    "Tidak ada alternatif in-stock saat ini.": "Tidak ada alternatif yang ada stoknya saat ini.",

    # ── dasbor & navigasi ──
    "Dashboard & Analytics": "Dasbor & Analitik",
    "Dashboard Keuangan": "Dasbor Keuangan",
    "Dashboard BI Sales": "Dasbor BI Sales",
    "Dashboard BI Stok": "Dasbor BI Stok",
    "Dashboard BI SDM": "Dasbor BI SDM",
    "Tab Dashboard": "Tab Dasbor",
    "Memuat data dashboard…": "Memuat data dasbor…",
    "Cara gunakan dashboard untuk monitoring orders": "Cara gunakan dasbor untuk memantau pesanan",
    "Dapatkan di dashboard Fonnte → menu Device → Token.":
        "Dapatkan di dasbor Fonnte → menu Device → Token.",
    "Returns & Barang Sisa": "Retur & Barang Sisa",
    "Design Gallery + AI": "Galeri Desain + AI",
    "Aktifkan auto-tag AI pada Design Gallery": "Aktifkan auto-tag AI pada Galeri Desain",
    "RFQ / Quotation": "RFQ / Penawaran",
    "Buat RFQ / Quotation": "Buat RFQ / Penawaran",
    "RFQ / Quotation — Tender Pengadaan": "RFQ / Penawaran — Tender Pengadaan",
    "RFQ / Quotation · Tender & Banding Harga Supplier":
        "RFQ / Penawaran · Tender & Banding Harga Supplier",

    # ── status & aksi sisa ──
    "Done": "Selesai",
    "Done (Delivered)": "Selesai (Terkirim)",
    "Mark as Done": "Tandai Selesai",
    "Ready": "Siap",
    "Mark as Ready": "Tandai Siap",
    "Create": "Buat",
    "Tampilkan Form Create": "Tampilkan Formulir Buat",
    "Active Orders": "Pesanan Aktif",
    "Active orders": "Pesanan aktif",
    "Phone": "Telepon",
    "Value (contoh: Biru Navy)": "Nilai (contoh: Biru Navy)",
    "Target Price": "Harga Target",
    "Target Price per Unit (IDR)": "Harga Target per Satuan (IDR)",
    "Expected Delivery": "Perkiraan Pengiriman",
    "Expected Delivery Date": "Tanggal Perkiraan Pengiriman",
    "On-Time Delivery": "Ketepatan Pengiriman",
    "Jumlah Step": "Jumlah Langkah",
    "Step Diterima": "Langkah Diterima",
    "Step Title": "Judul Langkah",
    "Menunggu step sebelumnya diterima.": "Menunggu langkah sebelumnya diterima.",

    # ══ PUTARAN 3 — peran, pengguna & panduan ═══════════════════════════════
    "Role": "Peran",
    "Approver Role": "Peran Penyetuju",
    "Tingkat berjalan butuh role": "Tingkat berjalan butuh peran",
    "Kirim ke nomor user sesuai role penerima": "Kirim ke nomor pengguna sesuai peran penerima",
    "Buat User": "Buat Pengguna",
    "Logout": "Keluar",
    "— Tanpa akun login —": "— Tanpa akun pengguna —",
    "Tautkan ke Akun Login (opsional)": "Tautkan ke Akun Pengguna (opsional)",
    "Klik checkbox untuk ubah permission. Perubahan tersimpan otomatis.":
        "Klik kotak centang untuk ubah izin. Perubahan tersimpan otomatis.",
    "Tidak ada tour yang tersedia untuk role": "Tidak ada panduan yang tersedia untuk peran",
    "Escalate ke Manager": "Eskalasi ke Manager",
    "Hanya manager/admin yang dapat approve.": "Hanya manager/admin yang dapat menyetujui.",
    "Approve": "Setujui",
    "Approve PO": "Setujui PO",
    "Review & Approve": "Tinjau & Setujui",
    "Inspeksi wajib setelah approve": "Inspeksi wajib setelah disetujui",
    "Escalate": "Eskalasi",
    "Purchase Order (PO)": "Pesanan Pembelian (PO)",
    "Sales Order (SO)": "Pesanan Penjualan (SO)",

    # ══ PUTARAN 4 — teks dari BACKEND + tab gudang ═══════════════════════════
    # ── stok fisik / mutasi ──
    "On Hand": "Stok Fisik",
    "On-Hand": "Stok Fisik",
    "On-hand": "Stok fisik",
    "Total On Hand": "Total Stok Fisik",
    "Stok on-hand milik entitas penjual cukup.": "Stok fisik milik entitas penjual cukup.",
    "Ledger": "Mutasi",
    "Scan Queue / Log": "Antrean Scan / Log",
    "Help & Tours": "Bantuan & Panduan",
    # ── status ──
    "Confirmed": "Terkonfirmasi",
    "Confirmed (Keep)": "Terkonfirmasi (Ditahan)",
    "Dispatched": "Terkirim",
    "Dispatched (legacy)": "Terkirim (lama)",
    # ── generate → buat ──
    "Generate Varian": "Buat Varian",
    "Generate label cepat": "Buat label cepat",
    "Generate Label Roll": "Buat Label Roll",
    "Generate Label Barcode": "Buat Label Barcode",
    "Generate varian massal dari kombinasi": "Buat varian massal dari kombinasi",
    "Tambah axis (Warna/Grade/Lebar) untuk generate varian. Pisahkan opsi dengan koma.":
        "Tambah sumbu (Warna/Grade/Lebar) untuk membuat varian. Pisahkan opsi dengan koma.",
    "Generate outbound dari order yang confirmed": "Buat barang keluar dari pesanan terkonfirmasi",
    "Generate dan cetak Surat Jalan atau Invoice": "Buat dan cetak Surat Jalan atau Faktur",
    # ── langkah pengenalan (onboarding) yang dikirim backend ──
    "Cek WMS task queue": "Cek antrean tugas WMS",
    "Lihat daftar tugas inbound/outbound": "Lihat daftar tugas barang masuk/keluar",
    "Proses inbound pertama": "Proses barang masuk pertama",
    "Advance task ke stage berikutnya": "Lanjutkan tugas ke tahap berikutnya",
    "Advance Stage": "Lanjutkan Tahap",
    "Klik Advance Stage untuk update status": "Klik Lanjutkan Tahap untuk memperbarui status",
    "Proses outbound task": "Proses tugas barang keluar",
    "Dispatch pengiriman": "Kirim barang",
    "Selesaikan task outbound ke status dispatched":
        "Selesaikan tugas barang keluar sampai status terkirim",
    "Submit order ke approval": "Kirim pesanan untuk persetujuan",
    "Kirim order ke manager untuk diapprove": "Kirim pesanan ke manager untuk disetujui",
    "Cek Manager Dashboard": "Cek Dasbor Manajer",
    "Review KPI stok, order, dan warehouse": "Tinjau KPI stok, pesanan, dan gudang",
    "Approve sales order": "Setujui pesanan penjualan",
    "Review dan approve order yang masuk": "Tinjau dan setujui pesanan yang masuk",
    "Review stock aging": "Tinjau umur stok",
    "Export data produk atau customer ke CSV": "Ekspor data produk atau pelanggan ke CSV",
    "Buat user baru": "Buat pengguna baru",
    "Review permission matrix": "Tinjau matriks izin",
    "Tambah atau pilih customer": "Tambah atau pilih pelanggan",
    "Buat customer baru atau pilih existing": "Buat pelanggan baru atau pilih yang sudah ada",
    "Buat sales order pertama": "Buat pesanan penjualan pertama",
    "Buat order dan reservasi stok otomatis": "Buat pesanan dan reservasi stok otomatis",
    "Cetak dokumen order": "Cetak dokumen pesanan",
    "Jalankan cycle count": "Jalankan stock opname",
    "Buat sesi cycle count untuk gudang": "Buat sesi stock opname untuk gudang",
    "Export laporan": "Ekspor laporan",
    "Onboarding direset": "Pengenalan direset",
    "Logout berhasil": "Keluar berhasil",
    # ── dokumen cetak (judul di PDF/HTML) ──
    "No. Sales Order": "No. Pesanan Penjualan",
    "No. Purchase Order": "No. Pesanan Pembelian",
    "Sales Order Confirmation": "Konfirmasi Pesanan Penjualan",
    "Special Order (sumber)": "Pesanan Khusus (sumber)",
    "Purchase Requisition (sumber)": "Permintaan Pembelian (sumber)",
    "Quotation/Penawaran": "Penawaran",
    "Surat Pengambilan (Picking List)": "Surat Pengambilan Barang",
    "Surat Pengambilan Barang (Picking List)": "Surat Pengambilan Barang",
    "Ref Order": "Ref Pesanan",
    "Untuk Order": "Untuk Pesanan",
    # ── keuangan & notifikasi ──
    "Term Bayar": "Termin Bayar",
    "Dibayar saat invoice terbit": "Dibayar saat faktur terbit",
    "Hitung PPN invoice": "Hitung PPN faktur",
    "Usulan denda (draft, tanpa jurnal)": "Usulan denda (draf, tanpa jurnal)",
    "Konsep (draft R&D)": "Konsep (draf R&D)",
    "Seluruh sisa piutang order": "Seluruh sisa piutang pesanan",
    "Output work order (BOM)": "Hasil perintah kerja (BOM)",
    "Work Order Produksi Tertunda": "Perintah Kerja Produksi Tertunda",
    "WO dirilis > 3 hari belum selesai, WO draft > 7 hari, atau WO dengan bahan kurang.":
        "WO dirilis > 3 hari belum selesai, WO draf > 7 hari, atau WO dengan bahan kurang.",
    "Approval rule deleted successfully": "Aturan persetujuan berhasil dihapus",
    "Harga khusus hanya bisa diajukan sebelum pesanan disetujui (tahap Reserved).":
        "Harga khusus hanya bisa diajukan sebelum pesanan disetujui (tahap Dipesan).",
    "Approval kredit hanya relevan sebelum pesanan disetujui.":
        "Persetujuan kredit hanya relevan sebelum pesanan disetujui.",
    "stok menipis · reservasi kedaluwarsa · approval SO/PO":
        "stok menipis · reservasi kedaluwarsa · persetujuan SO/PO",
    "Stok menipis, reservasi mendekati kedaluwarsa, dan order/PO menunggu persetujuan.":
        "Stok menipis, reservasi mendekati kedaluwarsa, dan pesanan/PO menunggu persetujuan.",
    "Alert penting yang belum dibaca melewati batas waktu dinaikkan otomatis ke atasan "
    "(sales/gudang → manager → admin).":
        "Peringatan penting yang belum dibaca melewati batas waktu dinaikkan otomatis ke "
        "atasan (sales/gudang → manager → admin).",
    "Pindai piutang pelanggan yang lewat jatuh tempo (aging) → notifikasi manager & sales "
    "pemegang akun.":
        "Pindai piutang pelanggan yang lewat jatuh tempo (umur piutang) → notifikasi "
        "manager & sales pemegang akun.",
    "Tugas inbound/outbound terbuka > 2 hari, diringkas per gudang & arah.":
        "Tugas barang masuk/keluar terbuka > 2 hari, diringkas per gudang & arah.",
    "Penerimaan barang PO (GR) yang selesai dalam 24 jam terakhir → beri tahu MD/manager, "
    "gudang, dan sales yang punya order pendingan atas produk itu.":
        "Penerimaan barang PO (GR) yang selesai dalam 24 jam terakhir → beri tahu "
        "MD/manager, gudang, dan sales yang punya pesanan pendingan atas produk itu.",
    "Tagihan supplier terposting yang jatuh tempo <= 7 hari atau sudah lewat (berdasarkan "
    "term pembayaran supplier).":
        "Tagihan supplier terposting yang jatuh tempo <= 7 hari atau sudah lewat "
        "(berdasarkan termin pembayaran supplier).",
    "Ingatkan piutang tepat pada H-3, H-1, hari-H, dan H+1 (melengkapi 'Piutang Jatuh "
    "Tempo' yang memindai aging lama). Dedupe harian mencegah pesan dobel.":
        "Ingatkan piutang tepat pada H-3, H-1, hari-H, dan H+1 (melengkapi 'Piutang Jatuh "
        "Tempo' yang memindai umur piutang lama). Penyaringan ganda harian mencegah "
        "pesan dobel.",

    # ══ PUTARAN 5 — teks di sekitar interpolasi JSX (celah yang baru ditutup) ══
    "Import / Export": "Impor / Ekspor",
    "Langsung kirim untuk approval (skip draft)":
        "Langsung kirim untuk persetujuan (lewati draf)",
    "Langsung submit untuk approval (jika total &gt; Rp 10.000.000)":
        "Langsung kirim untuk persetujuan (jika total &gt; Rp 10.000.000)",
    "Warehouse:": "Gudang:",
    "Active": "Aktif",
    "Rule": "Aturan",
    "setting": "pengaturan",
    "Setting ini belum bisa dibedakan pada level “":
        "Pengaturan ini belum bisa dibedakan pada level “",
    "Step": "Langkah",
    "step diterima": "langkah diterima",
    "Lakukan Reversal": "Lakukan Pembalikan",
    "Batal / Reversal Retur Beli": "Batal / Pembalikan Retur Beli",
    "Batal / Reversal Return": "Batal / Pembalikan Retur",
    "Dibatalkan (Reversal)": "Dibatalkan (Pembalikan)",
    "Reversal HPP (barang kembali ke stok): Rp": "Pembalikan HPP (barang kembali ke stok): Rp",
    "task": "tugas",
    "Tasks": "Tugas",
    "On hand": "Stok fisik",
    "Hold Aktif": "Tahanan Aktif",
    "Pending:": "Menunggu:",
    "order": "pesanan",
    "tour": "panduan",
    "Maks utk order ini:": "Maks utk pesanan ini:",
    "Approved oleh": "Disetujui oleh",
    "Reject Order": "Tolak Pesanan",
    "Reject Special Order": "Tolak Pesanan Khusus",
    "Konversi ke Sales Order": "Ubah ke Pesanan Penjualan",
    "Belum ada special order": "Belum ada pesanan khusus",
    "Order Velocity —": "Kecepatan Pesanan —",
    "Customer (entitas": "Pelanggan (entitas",
    "Transfer diminta — menunggu approval": "Transfer diminta — menunggu persetujuan",
    "Tutorial relevan untuk role Anda ·": "Tutorial relevan untuk peran Anda ·",
    "Harga di atas price-list supplier (+": "Harga di atas daftar harga supplier (+",
    "Harga di atas price-list (": "Harga di atas daftar harga (",
    "bila PO tak di-tag) + LPJ pending.": "bila PO tak ditandai) + LPJ menunggu.",
    "Semua stok aktif (tidak ada aging dalam": "Semua stok aktif (tidak ada yang menua dalam",
    "berlaku. Centang bila customer minta Faktur Pajak.":
        "berlaku. Centang bila pelanggan minta Faktur Pajak.",
    "item mixed-lot — konfirmasi saat submit.": "item beda lot — konfirmasi saat kirim.",
    "dari stok ini sedang direserve untuk sales order yang belum dikonfirmasi.":
        "dari stok ini sedang dipesan untuk pesanan penjualan yang belum dikonfirmasi.",

    # ══ PUTARAN 6 — potongan teks di dalam template literal (`${n} order`) ══════
    "? Task inbound yang masih terbuka akan dibatalkan.":
        "? Tugas barang masuk yang masih terbuka akan dibatalkan.",
    "Barang cacat dari customer diteruskan ke supplier":
        "Barang cacat dari pelanggan diteruskan ke supplier",
    "draft + released": "draf + dirilis",
    "Cash in": "Kas masuk",
    "order terbuka": "pesanan terbuka",
    "overdue": "lewat jatuh tempo",
    "order ·": "pesanan ·",
    "Generate Varian ·": "Buat Varian ·",
    "% collection": "% tertagih",
    "on-collection · margin-aware": "saat tertagih · memperhatikan margin",

    # ── potongan teks yang diawali tanda (×, ·, →, —) di sekitar interpolasi ──
    "× order": "× pesanan",
    "· Term": "· Termin",
    "· Customer:": "· Pelanggan:",
    "· butuh role": "· butuh peran",
    "→ Purchase Order": "→ Pesanan Pembelian",
    "— picking di-hold sampai tanggal ambil": "— pengambilan ditahan sampai tanggal ambil",
    ") — PO mungkin butuh approval.": ") — PO mungkin butuh persetujuan.",
    "= cost)": "= biaya)",
}
