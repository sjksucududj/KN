# PROPOSAL PENGEMBANGAN MIDDLEWARE RFID
## Kain Nusantara — Penghubung Perangkat RFID Chainway ke Sistem Pusat

**Disiapkan untuk:** Manajemen Kain Nusantara
**Ruang lingkup:** Pengembangan *middleware* (perangkat lunak penghubung) untuk perangkat RFID Chainway

---

## Apa itu "Middleware" di sini?

Perangkat RFID (alat genggam, gerbang pindai, dan printer) **tidak dapat berbicara
langsung** dengan sistem pusat. Diperlukan **perangkat lunak penghubung (middleware)**
yang dipasang di sisi perangkat/lokasi, yang bertugas:

- **membaca / mengendalikan** perangkat RFID,
- **merapikan** data hasil pembacaan, lalu
- **meneruskannya dengan aman** ke sistem pusat.

Middleware inilah jembatan antara "mesin RFID di lapangan" dan "sistem pusat".
Proposal ini **hanya** membahas bagian middleware tersebut (bukan sistem pusat/dashboard,
yang merupakan bagian terpisah).

---

## Rincian Middleware yang Akan Dibangun

### 1) Middleware Alat Genggam (Handheld)
**Device terkait:** Alat pembaca RFID genggam **Chainway** (dibawa petugas berkeliling gudang).

**Apa yang dikembangkan:** sebuah **aplikasi yang berjalan di dalam alat genggam** untuk
mengaktifkan dan mengendalikan modul pembaca RFID bawaan alat, dengan kemampuan:
- **Hitung massal** — memindai banyak gulungan sekaligus untuk stok opname keliling.
- **Pencari Barang ("Radar")** — memandu petugas menemukan satu gulungan tertentu;
  semakin dekat ke barang, indikator/sinyal semakin kuat (seperti detektor).
- **Pemberian identitas** — menuliskan identitas ke label RFID pada gulungan baru.
- **Terima & kirim barang** — verifikasi barang langsung dari genggaman petugas.
- **Pengiriman data** — hasil pembacaan langsung dikirim ke sistem pusat.

**Fungsi:** menjadi jembatan antara **mesin pembaca RFID di dalam alat genggam** dan
**sistem pusat**. Tanpa middleware ini, tampilan/layar biasa tidak bisa mengakses modul
pembaca RFID yang tertanam di alat.

---

### 2) Middleware Gerbang Pindai (Fixed Reader)
**Device terkait:** **Gerbang/pembaca RFID terpasang Chainway** di pintu masuk/keluar gudang,
beserta **kotak penghubung kecil** yang dipasang di lokasi.

**Apa yang dikembangkan:** sebuah **program penghubung di lokasi gudang** yang:
- **Menerima aliran data** bacaan tag dari gerbang pindai secara terus-menerus.
- **Merapikan data** — membuang bacaan ganda (satu barang terbaca berkali-kali) dan
  menentukan status **masuk atau keluar**.
- **Mengendalikan lampu/alarm (buzzer)** — menyalakan peringatan bila ada barang keluar
  tanpa izin.
- **Cadangan saat internet putus** — tetap menyimpan data sementara, lalu mengirim ulang
  begitu koneksi pulih (tidak ada data hilang).
- **Meneruskan dengan aman** data yang sudah rapi ke sistem pusat.

**Fungsi:** menjadi jembatan antara **gerbang pindai** dan **sistem pusat**. Ini diperlukan
karena gerbang hanya "menyiarkan" data di dalam jaringan lokal gudang dan tidak dapat
mengirim sendiri secara aman ke sistem pusat. Bagian ini **khusus untuk gerbang/alat
terpasang**; alat genggam tidak memerlukannya.

---

### 3) Middleware Printer Label RFID
**Device terkait:** **Printer label RFID Chainway** (biasanya terhubung nirkabel/Bluetooth)
di area penerimaan/produksi.

**Apa yang dikembangkan:** sebuah **penghubung ke printer** yang:
- **Terhubung ke printer** RFID.
- **Mengirim desain label + perintah pengisian identitas RFID** dalam satu langkah
  (cetak label sekaligus mengisi tag-nya).
- **Mengonfirmasi hasil** cetak & pengisian kembali ke sistem pusat.

**Fungsi:** menjadi jembatan antara **sistem pusat** dan **printer**, sehingga proses
"cetak label + isi identitas RFID" menjadi satu langkah otomatis, siap tempel di gulungan.

---

## Ringkasan: Middleware, Device, dan Fungsinya

| Middleware yang dibangun | Device terkait | Yang dikembangkan | Fungsi utama |
|---|---|---|---|
| **Middleware Alat Genggam** | Handheld RFID Chainway | Aplikasi di dalam alat genggam | Hitung massal, **Pencari Barang (radar)**, beri identitas, terima/kirim, kirim data ke pusat |
| **Middleware Gerbang Pindai** | Gerbang/fixed reader Chainway + kotak penghubung di gudang | Program penghubung di lokasi | Terima & rapikan data, kendalikan lampu/alarm, cadangan saat internet putus, teruskan aman ke pusat |
| **Middleware Printer** | Printer label RFID Chainway | Penghubung ke printer | Cetak label + isi identitas RFID sekaligus, konfirmasi ke pusat |

---

## Batasan Ruang Lingkup (agar jelas)
- Proposal ini **hanya** mencakup **middleware/penghubung** untuk ketiga jenis perangkat di atas.
- **Sistem pusat, dashboard, laporan, dan pengelolaan identitas tag** adalah **bagian terpisah**
  dan tidak termasuk dalam proposal middleware ini.
- Kebutuhan perangkat keras (jumlah alat genggam, titik gerbang, printer, dan kotak penghubung)
  disesuaikan dengan tata letak dan volume gudang Kain Nusantara.

---

## Manfaat Middleware
- **Menghidupkan fungsi perangkat RFID** (genggam, gerbang, printer) agar benar-benar
  terhubung dan berguna, bukan sekadar alat berdiri sendiri.
- **Data akurat & real-time** mengalir otomatis dari lapangan ke sistem pusat.
- **Andal** — tetap mencatat meski internet sempat terganggu.
- **Aman** — data diteruskan melalui jalur yang terlindungi.

---

## Tahapan Pekerjaan (Middleware)
1. **Middleware Alat Genggam** — hitung massal, pencari barang (radar), pemberian identitas.
2. **Middleware Gerbang Pindai + kotak penghubung** — pencatatan otomatis & alarm pintu.
3. **Middleware Printer** — cetak label + isi identitas RFID.
4. **Uji coba di gudang bersama tim & penyesuaian akhir.**

---

*Proposal ringkas ini disiapkan untuk tinjauan manajemen. Rincian pemasangan, kebutuhan
perangkat keras, dan jadwal dapat disusun lebih lanjut sesuai persetujuan.*
