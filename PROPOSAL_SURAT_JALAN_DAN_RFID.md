# PROPOSAL PENGEMBANGAN SISTEM
## Kain Nusantara — Surat Jalan Digital & Integrasi RFID

**Disiapkan untuk:** Manajemen Kain Nusantara
**Ruang lingkup:** (A) Surat Jalan Digital · (B) Integrasi Perangkat RFID Chainway

---

## Ringkasan Eksekutif

Dokumen ini menjelaskan dua pengembangan yang akan meningkatkan kecepatan, kerapian,
dan akurasi operasional gudang serta pengiriman Kain Nusantara:

1. **Surat Jalan Digital** — membuat surat jalan secara otomatis dari data pesanan,
   lengkap dengan rincian ukuran tiap gulungan, siap cetak, siap dikirim ke pelanggan
   lewat WhatsApp, dan dapat ditandatangani secara digital.

2. **Integrasi RFID (perangkat Chainway)** — memasang teknologi "tag pintar" pada setiap
   gulungan kain sehingga proses hitung stok, cari barang, terima/kirim barang, dan
   pengecekan di pintu gudang menjadi jauh lebih cepat dan minim salah.

Kedua inisiatif ini saling melengkapi: RFID memastikan **data barang akurat dan real-time**,
sedangkan Surat Jalan Digital memastikan **dokumen pengiriman rapi, resmi, dan cepat**.

---

# BAGIAN A — SURAT JALAN DIGITAL

## A.1 Tujuan
Menggantikan surat jalan tulis tangan/ketik manual dengan surat jalan yang dibuat
otomatis oleh sistem, dengan format khas industri tekstil (mencantumkan **nama kain,
warna, kode barang, jumlah roll, dan rincian ukuran tiap roll**), sehingga:
- Pembuatan lebih cepat dan bebas salah hitung.
- Tampilan seragam dan profesional untuk semua pelanggan.
- Mudah dilacak, dicetak ulang, dikirim, dan diarsipkan.

## A.2 Apa yang Dibangun

| Komponen | Fungsi | Dipakai di / oleh |
|---|---|---|
| **Format Surat Jalan Tekstil** | Surat jalan otomatis berisi kepala perusahaan, tujuan pelanggan, nomor & tanggal, tabel barang (nama kain, warna, kode, jumlah roll), **rincian ukuran per roll + total**, serta kolom tanda tangan (Penerima, Mengetahui, Dibuat Oleh) dan catatan ketentuan retur | Staf admin/gudang, lewat komputer/laptop kantor |
| **Cetak & Simpan PDF** | Surat jalan langsung bisa dicetak atau disimpan sebagai file PDF resmi | Printer kantor biasa |
| **Kirim via WhatsApp** | Surat jalan dapat dikirim ke pelanggan langsung dari sistem | Staf admin |
| **Tanda Tangan Digital** | Surat jalan dapat ditandatangani secara digital dan diverifikasi keasliannya | Staf & penerima |
| **Riwayat & Pencarian** | Semua surat jalan tersimpan, mudah dicari dan dicetak ulang | Admin/manajer |

## A.3 Manfaat
- **Lebih cepat:** surat jalan jadi dalam hitungan detik dari data pesanan.
- **Akurat:** ukuran tiap roll dan total otomatis, tidak salah jumlah.
- **Profesional & konsisten:** format seragam untuk seluruh pelanggan.
- **Mudah ditelusuri:** arsip digital, tidak takut hilang.

## A.4 Tahapan Pekerjaan (Bagian A)
1. Penyesuaian format surat jalan sesuai contoh & kebutuhan Kain Nusantara.
2. Pembuatan otomatis dari data pesanan/pengiriman.
3. Fitur cetak PDF, kirim WhatsApp, dan tanda tangan digital.
4. Uji coba bersama tim & penyempurnaan tampilan.

> Catatan: fondasi sistem sudah tersedia (data ukuran per gulungan sudah tercatat), sehingga
> pekerjaan utama ada pada penyesuaian format dan integrasi cetak/kirim.

---

# BAGIAN B — INTEGRASI RFID (PERANGKAT CHAINWAY)

## B.1 Tujuan
Setiap gulungan kain diberi **label pintar (tag RFID)**. Dengan alat pembaca RFID,
petugas dapat menghitung, mencari, dan memverifikasi ratusan gulungan **tanpa memindai
satu per satu secara manual**, sehingga stok opname, penerimaan, pengiriman, dan
pengawasan pintu gudang menjadi jauh lebih cepat dan akurat.

## B.2 Apa yang Dibangun — dan Untuk Perangkat Apa

Solusi RFID terdiri dari beberapa bagian yang bekerja bersama. Berikut fungsinya dan
di perangkat mana masing-masing dipakai:

### 1) Pusat Data & Dashboard RFID
- **Fungsi:** otak sistem. Menyimpan identitas semua tag, mencocokkannya dengan data
  gulungan/stok, menampilkan posisi & jumlah barang secara real-time, membuat laporan,
  dan memberi peringatan (misalnya barang keluar tanpa izin).
- **Dipakai di:** komputer/laptop/tablet kantor melalui layar dashboard biasa.
- **Untuk pengguna:** admin, kepala gudang, manajer.

### 2) Aplikasi pada Alat Genggam (Handheld Chainway)
- **Fungsi:**
  - **Hitung massal:** memindai banyak gulungan sekaligus dalam sekejap (stok opname keliling).
  - **Pencari Barang ("Radar"):** memandu petugas menemukan satu gulungan tertentu —
    semakin dekat ke barang, sinyal/indikator semakin kuat (seperti detektor).
  - **Pemberian identitas:** menuliskan identitas ke label pada gulungan baru.
  - **Terima & kirim barang:** verifikasi barang saat masuk/keluar langsung dari tangan petugas.
- **Dipakai di:** perangkat genggam RFID Chainway (dibawa petugas berkeliling gudang).
- **Untuk pengguna:** petugas gudang.

### 3) Gerbang Pindai Otomatis (Fixed Reader Chainway)
- **Fungsi:** dipasang di **pintu masuk/keluar gudang**. Otomatis mencatat setiap gulungan
  yang melintas, dan dapat menyalakan **lampu/alarm** bila ada barang keluar tanpa izin.
- **Dipakai di:** titik pintu/loading gudang (alat terpasang permanen).
- **Untuk pengguna:** berjalan otomatis; hasil terlihat di dashboard.

### 4) Perangkat Penghubung di Lokasi (untuk Gerbang Pindai)
- **Fungsi:** kotak penghubung kecil yang dipasang di gudang, menghubungkan **gerbang
  pindai** ke pusat data dengan aman. Ia juga **tetap mencatat data walau internet
  sempat terputus**, lalu mengirimnya kembali saat koneksi pulih (tidak ada data hilang).
- **Dipakai di:** ruang/panel jaringan gudang (menyertai pemasangan gerbang pindai).
- **Untuk pengguna:** berjalan otomatis di belakang layar.
- **Catatan:** khusus untuk **gerbang pindai/alat terpasang**. Alat genggam tidak
  memerlukan ini karena sudah terhubung internet sendiri.

### 5) Cetak Label RFID (Printer Chainway)
- **Fungsi:** mencetak label **sekaligus mengisi identitas RFID-nya** untuk ditempel pada
  gulungan kain.
- **Dipakai di:** printer label RFID Chainway di area penerimaan/produksi.
- **Untuk pengguna:** petugas gudang/penerimaan.

## B.3 Ringkasan: Peta Perangkat & Fungsi

| Bagian yang dibangun | Untuk perangkat | Fungsi utama |
|---|---|---|
| Pusat Data & Dashboard | Komputer/laptop/tablet | Menyimpan data, laporan, pemantauan, peringatan |
| Aplikasi Alat Genggam | Handheld RFID Chainway | Hitung massal, **cari barang (radar)**, beri identitas, terima/kirim |
| Gerbang Pindai | Fixed reader Chainway di pintu | Pencatatan otomatis + alarm keluar tanpa izin |
| Perangkat Penghubung Lokasi | Kotak penghubung di gudang | Menyambungkan gerbang ke pusat data + cadangan saat internet putus |
| Cetak Label RFID | Printer RFID Chainway | Cetak & isi identitas label untuk ditempel |

## B.4 Manfaat
- **Stok opname super cepat:** dari berjam-jam menjadi menit.
- **Cari barang instan:** temukan gulungan tertentu tanpa bongkar rak.
- **Kurangi salah kirim & kehilangan:** pengawasan otomatis di pintu.
- **Data real-time & akurat:** posisi dan jumlah barang selalu terbarui.

## B.5 Tahapan Pekerjaan (Bagian B)
1. **Persiapan pusat data & dashboard** — sistem siap menerima dan menampilkan data RFID.
   (Fondasinya sudah tersedia dalam sistem dan tinggal diaktifkan untuk perangkat nyata.)
2. **Aplikasi alat genggam** — hitung massal, pencari barang (radar), pemberian identitas.
3. **Pemasangan gerbang pindai + perangkat penghubung** — pengawasan pintu otomatis.
4. **Cetak label RFID** — alur pemberian label pada gulungan baru.
5. **Uji coba menyeluruh di gudang & pelatihan tim.**

## B.6 Catatan Penting (agar ekspektasi jelas)
- Sebagian fitur RFID **berjalan pada perangkat khusus di lokasi** (alat genggam,
  gerbang pindai, printer) sesuai standar produsen perangkat (Chainway). Bagian ini
  memerlukan **aplikasi/penghubung yang dipasang langsung pada perangkat tersebut**,
  di luar layar dashboard biasa.
- **Pusat data, dashboard, laporan, dan pengelolaan identitas tag** dapat langsung
  dikembangkan dan diakses lewat komputer/tablet.
- Kebutuhan perangkat keras (jumlah alat genggam, titik gerbang, printer) akan disesuaikan
  dengan tata letak dan volume gudang Kain Nusantara.

---

## Rekomendasi Urutan Pelaksanaan
1. **Surat Jalan Digital** — dampak cepat, mempercepat pekerjaan admin/pengiriman.
2. **Pusat Data & Dashboard RFID** — menyiapkan pondasi data barang yang akurat.
3. **Alat Genggam RFID (termasuk fitur pencari/radar)** — percepatan kerja petugas.
4. **Gerbang Pindai + Perangkat Penghubung** — pengamanan pintu gudang.
5. **Cetak Label RFID** — melengkapi alur pemberian identitas gulungan.

---

*Proposal ini bersifat ringkas untuk kebutuhan tinjauan manajemen. Rincian teknis,
kebutuhan perangkat keras, dan jadwal pelaksanaan dapat disusun lebih lanjut sesuai
persetujuan.*
