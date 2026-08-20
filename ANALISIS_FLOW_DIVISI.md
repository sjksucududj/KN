# ANALISIS ALUR "ERP per divisi" — dibandingkan dengan aplikasi yang SUDAH berjalan

> Sumber: berkas pemilik `ERP per divisi (2) (1).xlsx` (2 lembar: **Bagan**, **Notif**),
> disalin apa adanya ke `docs/sumber/ERP_per_divisi_2026-08-18.xlsx` supaya bisa
> ditelusuri ulang. Tanggal analisis: **2026-08-18**.
>
> **Cara mengukur (bukan menebak).** Setiap baris di bawah diverifikasi dengan salah
> satu dari: (a) membaca KODE pada berkas & baris yang disebut, (b) menghitung
> DOKUMEN di MongoDB, atau (c) memanggil API sungguhan dengan akun demo. Bila sebuah
> klaim tidak bisa saya ukur, ditulis **"BUTUH KEPUTUSAN"** — bukan ditebak.

---

## 0. Isi berkas apa adanya (supaya tidak ada yang hilang saat diringkas)

**Lembar `Bagan` — blok 1 (divisi kreatif):**

| Sample | Designer | RnD | Socmed |
|---|---|---|---|
| Sample dikerjakan sesuai SO | Design PO | Timeline RnD mulai dari rnd 1, rnd 2, rnd 3, sampai barang acc | *(kosong)* |
| Tanda sample sudah jadi dan dikirim | Timeline pengerjaan design masing2 designer | semua harus berupa upload dan penjelasan | |
| Ada master stock sample (sync dengan stock roll) yang bisa dilihat tim sales dan tim sample | Designer upload design yg sudah diacc | | |
| Tim Sample akan ambil bahan untuk dibuat sample dari roll, artinya harus ada penyesuaian jumlah roll di stock (gudang) | Design yang sudah acc akan ada nilai, yg dinilai oleh management di erp | | |
| | ada laporan berapa banyak design yang sudah acc masing2 designer | | |

**Lembar `Bagan` — blok 2 (JAKARTA):**

| | barang sudah ada di master | barang po sendiri (custom) | catatan |
|---|---|---|---|
| **Woven, knitting** | sales pilih item, warna, qty, harga → barang ready → kirim · barang tidak ready → notif md untuk repeat/restock/masuk pendingan dan md harus po → barang datang/ready → kirim | sales pilih order po sendiri → pilih item → request warna → notif md untuk po custom → barang datang → kirim | |
| **Printing** | sales pilih item motif, warna, qty, harga → *(percabangan sama)* | sales pilih order po sendiri → pilih item sesuai code dari md jakarta (code ini hanya dishow ke sales tertentu, karena po sendiri artinya barang hanya untuk sales sendiri, tidak dijual oleh sales lain) | md jakarta assign to designer to design, hasil design diassign oleh md jakarta ke md printing, rnd, jadi item yg bisa diorder sales itu sendiri |

**Lembar `Notif`** (kolom = penerima):

| Sales | Admin Sales | MD | Finance | Sample | Designer | Socmed | RnD |
|---|---|---|---|---|---|---|---|
| Barang PO datang | | Stock menipis | | | | | |
| Barang pendingan datang | | | | | | | |
| Due Date pembayaran customer (H-3, H-1, Hari H, H+1) | | | Due Date pembayaran customer (H-3, H-1, Hari H, H+1) | | | | |

---

## 1. Hasil: 19 baris spesifikasi → 9 SUDAH · 5 SEBAGIAN · 5 BELUM

Kabar baiknya: **inti alur Jakarta (yang memutar uang) sudah berdiri**. Yang belum
justru terkumpul di **rantai kreatif** (desain → sample → item baru) dan di
**alamat notifikasi**.

### 1.1 Divisi SAMPLE

| # | Spesifikasi | Status | Bukti / apa yang kurang |
|---|---|---|---|
| S1 | Sample dikerjakan **sesuai SO** | ⚠️ SEBAGIAN | Field `so_id` ADA di skema (`backend/schemas_rnd.py:93`), tetapi **terisi 0 dari 28** sample di basis data, dan **tidak ada isiannya di layar** (`frontend/src/features/rnd/SampleFormModal.jsx` tak menyebut `so_id`). Jadi tautannya ada di gudang data, tidak ada di meja kerja orang. |
| S2 | Tanda sample **sudah jadi dan dikirim** | ⚠️ SEBAGIAN | Status sample yang ada: `draft · sent · in_progress · assessed · decided` (diukur dari DB). `sent_at` berarti **permintaan dikirim ke SUPPLIER** — bukan "sample fisiknya sudah jadi lalu dikirim ke pelanggan/sales". Penanda "jadi" & "diterima pelanggan" belum ada. |
| S3 | **Master stock sample** (sync stock roll), dilihat tim sales & tim sample | ❌ BELUM | Ini dulu **sengaja tidak dibuat**: keputusan PS-19 tertulis *"satu angka stok, bukan koleksi stok sample kedua"* (`backend/services/rnd_sample_service.py:15`). Yang ada: pengambilan bahan mengurangi roll. Daftar "sample apa saja yang fisiknya tersedia untuk ditunjukkan ke pelanggan" belum ada di layar mana pun. |
| S4 | Tim Sample **ambil bahan dari roll** → stok gudang menyesuaikan | ✅ SUDAH | `POST /api/rnd/samples/{id}/issue-material` → roll berkurang + `inventory_movements` jenis `sample_issue` + saldo dihitung ulang (`rnd_sample_service.issue_material`, baris 525+). Layar: `IssueMaterialModal.jsx`. |

**Catatan penting alur sample:** mesin sample sekarang **berorientasi supplier** —
`send_sample()` menolak bila tidak ada supplier (*"Pilih minimal satu supplier tujuan
permintaan sample"*, `rnd_sample_service.py:266`). Padahal bagan Anda menggambarkan
sample **dikerjakan sendiri oleh Tim Sample** dari roll. Dua-duanya nyata di pabrik
tekstil, tetapi jalur "buat sendiri" belum punya alurnya.

### 1.2 Divisi DESIGNER

| # | Spesifikasi | Status | Bukti / apa yang kurang |
|---|---|---|---|
| D1 | **Design PO** | ❌ BELUM | Tidak ada dokumen "permintaan/penugasan desain". Diukur: dokumen `design_gallery` tidak punya satu pun field penugasan (`assigned_to`/`designer_id`), hanya `created_by`. Siapa mengerjakan apa masih di luar sistem. |
| D2 | **Timeline pengerjaan design** masing-masing designer | ❌ BELUM | Galeri desain tidak punya tenggat/target tanggal. Timeline & papan SLA yang ada (`/api/rnd/sla/board`) milik **round sample R&D**, bukan desain. |
| D3 | Designer **upload design yg sudah diacc** | ✅ SUDAH | `POST /design-gallery/{id}/files` + alur **Ajukan → Sahkan / Kembalikan-ber-alasan** (baru lunas di F-6.7) + versi artwork (`/version`). |
| D4 | Design acc **ada nilai**, dinilai management | ✅ SUDAH | Rating bintang 1–5 per penilai: `POST /design-gallery/{id}/rating`. Terukur di data demo: 1 desain punya 2 penilaian (5 & 4) dari admin & manajer. |
| D5 | **Laporan berapa banyak design acc per designer** | ❌ BELUM | Tidak ada satu pun endpoint laporan untuk `design-gallery` (diukur: nol hasil pencarian `report`/`stats` pada rutenya). Yang bernama "KPI Desainer" (`/api/rnd/reports/designer-kpi`) **menghitung round sample** dari koleksi `md_samples` (`rnd_kpi_service.py:216`) — **bukan** desain yang di-ACC. Jadi laporan yang Anda maksud memang belum ada, walaupun ada layar bernama mirip. |

### 1.3 Divisi RnD

| # | Spesifikasi | Status | Bukti |
|---|---|---|---|
| R1 | Timeline **rnd 1 → rnd 2 → rnd 3 sampai acc** | ✅ SUDAH | Round bernomor (`round_no`), SLA per round, batas `rnd.max_rounds` (melewatinya wajib ber-alasan), papan SLA + eskalasi otomatis. |
| R2 | **Semua harus berupa upload dan penjelasan** | ✅ SUDAH | `submit_round()` MENOLAK tanpa lampiran *dan* tanpa catatan (`rnd_sample_service.py:379–383`): *"Tidak bisa menutup round tanpa LAMPIRAN bukti"*. Bisa dimatikan lewat Pusat Pengaturan (`require_attachment_on_round`, bawaan **wajib**). |

### 1.4 Divisi SOCMED

Kolomnya **kosong** di berkas Anda — tidak ada satu pun baris. **BUTUH KEPUTUSAN**
(lihat §3).

### 1.5 JAKARTA — pesanan barang yang sudah ada di master

| # | Spesifikasi | Status | Bukti |
|---|---|---|---|
| J1 | Sales pilih **item, warna, qty, harga** (woven/knitting) & **motif, warna, qty, harga** (printing) | ✅ SUDAH | Produk memang punya `motif`, `color`, `color_code`, `color_name`, `color_hex` (diukur dari dokumen `products`), harga per badan usaha + jalur "harga khusus" ber-persetujuan. |
| J2 | Barang **ready → kirim** | ✅ SUDAH | Reservasi stok → picking → surat jalan (WMS). |
| J3 | Barang **tidak ready** → notif MD → repeat/restock/**masuk pendingan** → MD harus PO → barang datang → kirim | ✅ SUDAH | Satu pintu 3 jalur milik Admin Sales (`fulfillment_decision_service`: **ambil dari PT lain · reorder ke supplier · tahan menunggu barang masuk**) + mesin pendingan (backorder) + notifikasi `restock_request` ke peran **manager (MD)** (`alert_ops_service.py:289`), `po_arrival`, `backorder_ready`. |

### 1.6 JAKARTA — "PO sendiri" (custom)

| # | Spesifikasi | Status | Bukti / apa yang kurang |
|---|---|---|---|
| J4 | Sales pilih **order PO sendiri → pilih item → request warna** | ⚠️ SEBAGIAN | Ada `special_orders` (Pesanan Khusus) dengan `custom_item` + `specifications`. Tapi **permintaan warna masih teks bebas**, bukan dari **pustaka warna** — padahal di R&D warna wajib dari pustaka (PS-13). Akibatnya "merah bata" versi sales bisa beda dengan yang dibaca RnD. |
| J5 | **Notif MD untuk PO custom** | ❌ BELUM | Diukur: **nol** pemanggilan notifikasi di `backend/routers/special_orders.py`. Persetujuannya ada (matriks `po_custom` 2 tingkat), tetapi **tidak ada yang memberitahu MD** bahwa ada PO custom menunggu — ia hanya muncul kalau orangnya membuka layar. |
| J6 | **Barang datang → kirim** (custom) | ✅ SUDAH | `create-pr` → PO → penerimaan → `create-sku` → `convert-to-so` (rute ada di `routers/special_orders.py:421–519`). |
| J7 | Kode item printing **hanya ditampilkan ke sales tertentu** | ✅ SUDAH | PS-20: `exclusivity` (`umum`/`sales_tertentu`) + `owner_sales_ids`, **disaring di BACKEND** (bukan sekadar disembunyikan di UI) pada katalog & saat membuat SO. Terukur lewat API sungguhan: admin melihat **19** produk, `sales2` hanya **18** — persis karena data demo punya **1 produk eksklusif** (`ENK-BALI-001 Endek Bali Rangrang`, pemilik `sales@`). |
| J8 | **MD Jakarta assign designer → hasil desain di-assign ke MD Printing & RnD → jadi item yang bisa di-order sales itu sendiri** | ❌ BELUM | Semua **potongannya** ada (galeri desain ber-ACC · spesifikasi R&D → `release-product` · `create-sku` dari pesanan khusus · eksklusivitas per sales), tetapi **tidak tersambung**: tidak ada penugasan, dan tidak ada satu tombol pun yang menjadikan "desain yang di-ACC" sebagai **item eksklusif milik sales pemesan**. Hari ini rantai itu dijalankan manual oleh orang, di luar sistem. |

### 1.7 Lembar NOTIF (alamat notifikasi)

| # | Spesifikasi | Status | Bukti terukur |
|---|---|---|---|
| N1 | **Sales**: barang PO datang | ✅ SUDAH | `po_arrival` → manager + gudang + **sales pemilik order pendingan**. |
| N2 | **Sales**: barang pendingan datang | ✅ SUDAH | `backorder_ready` → sales pemegang akun + manager (terlihat di kotak notifikasi sales demo). |
| N3 | **Sales**: due date pembayaran H-3/H-1/H/H+1 | ✅ SUDAH | `AR_DUE_SOON_OFFSETS = [-3, -1, 0, 1]` — **persis** seperti permintaan (`alert_ops_service.py:40`). |
| N4 | **Finance**: due date pembayaran H-3/H-1/H/H+1 | ❌ BELUM | Job yang sama hanya mengirim ke `recipient_role="sales"` dan `"manager"` (baris 265 & 275). Terukur: kotak notifikasi akun **finance** berisi **nol** `ar_due_soon`. Orang yang menagih justru tidak diberi tahu. |
| N5 | **MD**: stock menipis | ⚠️ SEBAGIAN | `low_stock` ada, tetapi dialamatkan `recipient_role="all"` (`notification_service.py:135`) → **semua orang** menerimanya. Terukur: akun **finance menerima 9** notifikasi "stok menipis", sales juga 9. Di berkas Anda ini milik **MD saja**. Notifikasi yang dikirim ke semua orang cepat berubah jadi latar belakang yang tidak dibaca siapa pun. |

---

## 2. Tiga temuan STRUKTURAL (tidak kelihatan dari daftar per baris)

**T1 — Notifikasi belum bisa dialamatkan ke DIVISI, hanya ke 6 PERAN.**
Lembar `Notif` Anda punya **8 kolom**: Sales · Admin Sales · MD · Finance · Sample ·
Designer · Socmed · RnD. Sistem hari ini hanya mengenal peran
`admin · manager · sales_admin · finance · sales · warehouse` (`role_registry.py`),
sementara **divisi** (`sample · designer · rnd · socmed · md · admin_sales · finance`)
ada di `config_divisions.py` tetapi **tidak dipakai untuk mengirim notifikasi**, dan
di data demo hanya **2 dari 10** pengguna yang punya divisi. Artinya: 4 kolom terakhir
berkas Anda **mustahil terisi** sebelum notifikasi bisa dialamatkan per divisi.
Ini prasyarat, bukan sekadar fitur tambahan.

**T2 — "MD" hari ini = peran `manager`, dan itu keputusan lama yang sudah tertulis.**
Di kode: *"divisi MD sebagai entitas tersendiri baru ada di Fase H (PS-17); sampai saat
itu penerima = role manager"* (`alert_ops_service.py:291-295`). Jadi ketika bagan Anda
berkata "notif md", hari ini yang menerima adalah **manajer**. Perlu keputusan Anda:
MD tetap = manajer, atau MD menjadi divisi tersendiri yang punya orang & meja kerjanya
sendiri (dan otomatis ikut T1).

**T3 — Rantai kreatif putus di dua sambungan yang sama.**
Sample tidak tahu ia milik SO mana (S1), dan desain tidak tahu siapa yang ditugasi
mengerjakannya (D1). Dua-duanya adalah sambungan **ke belakang** (ke pesanan) dan
**ke depan** (ke item yang bisa dijual). Selama dua sambungan itu kosong, laporan
apa pun tentang produktivitas desain (D5) akan selalu menghitung dari sumber yang
salah — persis yang sekarang terjadi: "KPI Desainer" menghitung round sample.

---

## 3. Yang saya TIDAK boleh tebak — butuh keputusan Anda

1. **Socmed** — kolomnya kosong. Apa pekerjaan Socmed di dalam ERP? (mis. meminta
   materi foto/konten atas desain yang sudah ACC, menjadwalkan posting, mencatat
   pesanan yang datang dari IG/WA?)
2. **"Master stock sample"** — maksudnya (a) daftar **sample fisik** (swatch/hanger)
   yang tersedia untuk ditunjukkan sales ke pelanggan, atau (b) sekadar **melihat sisa
   roll** yang boleh dipakai sample? Keduanya beda pekerjaan.
3. **"Design PO"** — maksudnya dokumen **permintaan desain** (MD/sales meminta,
   designer mengerjakan, ada tenggat), atau desain yang dibuat **untuk sebuah PO
   pelanggan**? Atau keduanya (permintaan yang lahir dari PO)?
4. **MD** — tetap dipegang peran manajer, atau jadi **divisi/peran sendiri**?
5. **Sample dibuat sendiri atau lewat supplier?** Mesin sekarang mewajibkan supplier.
   Bagan Anda menggambarkan tim sample mengambil bahan dari roll → berarti butuh
   jalur **"dikerjakan sendiri"**. Apakah keduanya harus ada?

---

## 4. Usulan urutan pengerjaan (dari yang paling murah & paling terasa)

**Fase N — "Notifikasi sampai ke orang yang benar"** *(paling murah, paling cepat terasa)*
- Finance ikut menerima jatuh tempo pelanggan (N4).
- "Stok menipis" berhenti dikirim ke semua orang → hanya MD/manajer (N5).
- PO custom memberi tahu MD saat diajukan (J5).
- Notifikasi bisa dialamatkan ke **divisi**, bukan hanya peran (T1) — sekaligus
  membuka 4 kolom berkas Anda yang sekarang mustahil terisi.

**Fase S — "Sample punya asal-usul & ujung"**
- Sample tertaut ke SO/pelanggan di layar (S1), status **jadi → dikirim → diterima** (S2),
  dan jalur **dikerjakan sendiri** tanpa supplier.
- (Bila Anda pilih 3.2(a)) daftar **stok sample fisik** yang bisa dilihat sales (S3).

**Fase D — "Pekerjaan desain punya pemilik, tenggat, dan rapor"**
- **Permintaan desain** (Design PO): MD menugaskan designer, ada tenggat, statusnya
  jalan (D1, D2).
- **Rapor desain per designer**: berapa diajukan · berapa di-ACC · berapa dikembalikan ·
  rata-rata nilai bintang · rata-rata hari pengerjaan (D5).

**Fase P — "Rantai printing tersambung utuh"**
- Desain ACC → jadikan **item** → **eksklusif** ke sales pemesan → bisa langsung
  di-order (J8), dan permintaan warna memakai **pustaka warna** (J4).

Fase N bisa saya kerjakan tanpa keputusan tambahan kecuali satu: **MD = manajer atau
divisi sendiri?** Sisanya menunggu jawaban §3.

---

_Semua angka & rujukan baris di dokumen ini bisa diperiksa ulang. Bila ada yang tidak
cocok dengan kenyataan di layar Anda, itu temuan — tolong beri tahu, akan saya ukur
ulang._

---

### Lampiran — jebakan alat ukur yang saya kenai sendiri (dicatat supaya tidak terulang)

Saat menghitung produk eksklusif saya sempat mendapat angka **7**, padahal yang benar
**1**. Sebabnya query `{"owner_sales_ids": {"$ne": []}}` di MongoDB **juga cocok untuk
dokumen yang TIDAK punya field itu sama sekali** — jadi 6 produk lama ikut terhitung.
Yang benar: hitung dari `exclusivity == "sales_tertentu"`. Pelajarannya sama dengan
pelajaran lama repo ini: *angka yang tidak dibandingkan dengan sumber kedua adalah
angka yang belum diukur* — di sini pembandingnya API sungguhan (admin 19 vs sales2 18).


---
---

# BAGIAN II — DISKUSI DESAIN (setelah 4 keputusan pemilik, 2026-08-18)

Keputusan yang sudah diberikan pemilik:

| # | Pertanyaan | Jawaban pemilik |
|---|---|---|
| 1 | Socmed | **Dilewati dulu** (tidak dikerjakan) |
| 2 | Master stock sample | **(a) Daftar sample FISIK (swatch/hanger)** yang bisa ditunjukkan sales ke pelanggan |
| 3 | Design PO | **Keduanya** — dokumen permintaan desain, DAN desain yang lahir dari pesanan pelanggan |
| 4 | MD | **Divisi DAN peran tersendiri** |
| 5 | Sample lewat supplier | Logikanya **labdip → handfeel → proofing**; **handfeel belum ada** di sistem |

Bagian ini **belum mengubah satu baris kode pun**. Isinya: apa yang sebenarnya
berubah kalau keputusan di atas dijalankan, di mana bahayanya, dan pertanyaan yang
masih harus dijawab supaya saya tidak menebak.

---

## II.1 MD jadi PERAN — seberapa besar sebenarnya

**Ini bukan "tambah satu baris".** Diukur dari peran terakhir yang pernah ditambahkan
(`sales_admin`, FASE E-8): namanya muncul di **44 berkas** (backend + skrip + layar),
dan di frontend ada **227** titik yang bercabang pada peran. Kabar baiknya:
**presedennya ada dan jalurnya sudah terbukti** — E-8 menambah 2 peran sekaligus
(`sales_admin`, `finance`) dan bahkan meninggalkan alat pemindah akun berbasis jejak
(`services/role_reality_service.py`) yang bisa dipakai lagi untuk memindahkan orang
dari `manager` ke `md` **tanpa menebak** siapa yang sebenarnya MD.

Yang harus dijawab lebih dulu — karena ini menentukan kabel, bukan warna:

**(a) MD MEMUTUSKAN atau MENGEKSEKUSI?**
Hari ini matriks persetujuan (`config_divisions.APPROVER_MATRIX`) mengikat tombol ke peran:

| Tahap | Siapa sekarang |
|---|---|
| ACC Desain | Manager / Admin |
| ACC Sample | Manager / Admin |
| **PO Custom** | Manager → naik ke **Direksi** bila di atas ambang rupiah |
| **Permintaan Pembelian (PR)** | Manager / Admin |

Kalau MD **mengeksekusi** (membuat PR/PO, menugaskan desainer) sementara manajer tetap
**menyetujui uang**, pemisahannya bersih dan aman. Kalau MD juga **menyetujui**, saya
perlu tahu **sampai nilai berapa** — di atas itu tetap naik ke manajer/direksi.

> Kenapa ini saya tanyakan keras: repo ini punya POC khusus (`role_reality`) yang lahir
> justru karena pernah ada peran yang dipakai orang **melebihi** kebutuhannya. Menambah
> peran tanpa memutuskan wewenangnya menghasilkan peran yang punya meja tapi tak punya
> tombol — dan itu terasa seperti aplikasi yang rusak.

**(b) Di bagan Anda ada DUA MD: "MD Jakarta" dan "MD Printing".**
`md jakarta assign to designer to design, hasil design diassign oleh md jakarta ke **md printing**, rnd`.
Jadi: satu peran `md` dengan **penugasan per lini** (jakarta / printing), atau **dua
divisi berbeda** yang kebetulan sama-sama berperan `md`? Ini menentukan ke mana
notifikasi "desain siap" dikirim.

**(c) Apa yang PINDAH dari manajer ke MD?**
Usulan saya (mohon dikoreksi): "stok menipis" · permintaan repeat/restock dari sales ·
pemberitahuan PO custom · penugasan desain **pindah ke MD**. Sementara nilai/kredit/
harga khusus/payroll/tutup buku **tetap manajer**. Yang tidak boleh terjadi: dua-duanya
menerima segalanya — itu sama dengan tidak ada yang merasa bertanggung jawab.

---

## II.2 Divisi sebagai ALAMAT notifikasi — bahaya "dua sistem alamat"

Fakta terukur: notifikasi hari ini hanya bisa dialamatkan ke **peran** (6) atau ke
**satu orang**. Divisi (`sample · designer · rnd · socmed · md · admin_sales · finance`)
sudah ada di `config_divisions.py` tetapi **tidak pernah dipakai mengirim apa pun**, dan
di data demo hanya **2 dari 10** akun yang punya divisi.

Kalau divisi dipakai sebagai alamat kedua **tanpa satu aturan tertulis**, yang terjadi:
satu peristiwa terkirim dua kali ke orang yang sama (karena ia cocok sebagai peran DAN
sebagai divisi), atau — lebih berbahaya — **tidak terkirim sama sekali** karena
masing-masing sisi mengira sisi lain yang mengirim. Ini kelas kesalahan yang sama dengan
"tiga angka untuk satu pertanyaan" yang dulu sudah kita bereskan di antrean persetujuan.

**Usulan:** satu fungsi tunggal `penerima(peristiwa) → daftar orang`, dengan aturan
tertulis (peran ATAU divisi ATAU orang tertentu, di-de-duplikasi per orang), plus penjaga
yang memerah kalau ada notifikasi dikirim tanpa melewati fungsi itu.

**Pertanyaan:** boleh tidak satu orang punya **lebih dari satu** divisi (mis. designer
merangkap socmed)? Dan apakah **kepala divisi** perlu dibedakan dari anggotanya
(mis. hanya kepala yang menerima notifikasi "menunggu keputusan")?

---

## II.3 Master sample FISIK (swatch/hanger) — dan satu jebakan yang harus dihindari

Yang Anda minta adalah **objek fisik**, bukan stok meteran kedua: selembar/segantung
kain contoh yang dipegang sales untuk ditunjukkan ke pelanggan. Meterannya sendiri
**sudah** berkurang dari roll ketika Tim Sample mengambilnya (S4 — sudah jalan). Jadi
mendaftarkan swatch **tidak** membuat stok dihitung dua kali; ia benda lain dengan satuan
lain (lembar/gantungan, bukan meter).

**Jebakan yang harus dihindari:** menyalin angka sisa roll ke kartu swatch. Begitu
disalin, dua angka itu akan berbeda dalam hitungan hari dan tidak ada yang tahu mana yang
benar. Yang benar: kartu swatch **menunjuk** ke produknya dan menampilkan sisa roll
**apa adanya saat dibuka** — itulah arti "sync dengan stock roll" yang aman.

**Yang masih harus Anda putuskan:**
1. Dilacak **per lembar** (tiap swatch punya nomor/QR sendiri) atau cukup **jumlah per
   jenis** ("Batik Parang merah: 12 lembar")?
2. Statusnya apa saja? Usulan: *tersedia · dibawa sales · dikirim ke pelanggan · habis/hilang*.
3. Perlu tahu **siapa yang sedang memegang** dan **pelanggan mana** yang menerimanya?
   (Ini yang membuat sales bisa menjawab "swatch itu ada di saya, bukan hilang".)
4. Di mana disimpan — perlu **lokasi** (lemari/rak/kantor cabang)?
5. Swatch lahir dari mana: (a) otomatis saat Tim Sample mengambil bahan dari roll,
   (b) didaftarkan manual setelah sample jadi, atau (c) dua-duanya?

---

## II.4 "Design PO" — rantai yang saya usulkan, dan risiko dokumen ke-3

Karena jawabannya **keduanya**, dokumen permintaan desain harus bisa lahir dari dua arah:
dari **pesanan pelanggan** (sales/MD minta desain untuk PO tertentu) dan **berdiri
sendiri** (MD mengembangkan koleksi).

Rantai utuh yang saya usulkan:

```
Permintaan Desain (Design PO)          ← baru; punya penugasan + tenggat
    ↓ designer mengerjakan
Galeri Desain: unggah artwork + versi  ← SUDAH ADA
    ↓ Ajukan → ACC (+ nilai bintang)   ← SUDAH ADA (lunas di F-6.7)
    ↓
[printing] jadikan ITEM  →  eksklusif ke sales pemesan  ← potongannya ADA, sambungannya BELUM
    ↓
bisa di-order sales itu sendiri        ← SUDAH ADA (pagar eksklusivitas di server)
```

**Risiko yang harus kita sadari sejak awal:** sudah ada **dua** dokumen bertetangga —
`md_specs` (spesifikasi teknis R&D → melahirkan produk) dan `design_gallery` (master
artwork). Kalau "Design PO" dibuat tanpa batas yang tegas, ia jadi **dokumen ketiga yang
tumpang tindih**, dan enam bulan lagi tidak ada yang tahu harus membuka yang mana.

Batas yang saya usulkan:
* **Permintaan Desain** = *pekerjaan siapa, kapan harus selesai* (penugasan & tenggat).
* **Galeri Desain** = *artwork-nya sendiri* (berkas, versi, kode, ACC, nilai).
* **Spesifikasi R&D** = *angka teknisnya* (gramasi, lebar, konstruksi) → melahirkan produk.

**Pertanyaan:**
1. Boleh tidak designer mengunggah ke galeri **tanpa** permintaan? (Kalau boleh, laporan
   "berapa desain di-ACC per designer" harus menghitung dua-duanya.)
2. Siapa yang **ACC desain** setelah MD jadi peran — MD atau manajer?
3. Permintaan desain dipakai juga untuk **woven/knitting**, atau **printing saja**?

---

## II.5 Sample lewat supplier: labdip → handfeel → proofing

Fakta terukur hari ini:

| Jenis sample | Ada di sistem? | Jumlah dokumen demo |
|---|---|---|
| `labdip` | ✅ ada | **27** |
| `proofing` | ✅ ada (wajib ber-kode desain) | **1** |
| `bulk_sample` | ✅ ada | **0** (tidak pernah dipakai) |
| **`handfeel`** | ❌ **belum ada** | — |

`handfeel` hari ini hanya muncul sebagai **alasan keputusan** ("Mutu/handfeel terbaik")
saat memilih supplier pemenang — bukan sebagai tahap yang dikerjakan & diukur.

Perlu diketahui juga: kata `labdip` & `proofing` **juga** dipakai sebagai **tahap daur
hidup produk** (`konsep → labdip → proofing → disetujui → produksi`) yang menentukan
produk boleh dijual atau belum. Jadi menambah `handfeel` menyentuh **dua** daftar, dan
saya perlu tahu tempatnya di kedua-duanya.

**Pertanyaan:**
1. Urutannya **wajib berurutan** (handfeel baru boleh dibuka setelah labdip di-ACC), atau
   bebas sesuai kebutuhan barang?
2. Handfeel **diukur apa**? Hari ini round sample mengukur: `delta E` · tahan luntur cuci ·
   tahan luntur gosok · susut (%) · gramasi aktual. Untuk handfeel biasanya: **gramasi ·
   lebar · susut · rasa/pegangan (nilai 1–5)** — mohon dikoreksi/ditambah.
3. Untuk barang apa saja tiap tahap berlaku? (Dugaan saya: woven/knit → labdip + handfeel;
   printing → + proofing. Benar?)
4. `bulk_sample` (0 dokumen) masih dipakai atau dihapus dari pilihan?
5. Bagan Anda menulis **"Sample dikerjakan sesuai SO"**, tetapi sample supplier biasanya
   untuk **pengembangan** (belum ada SO). Apakah permintaan sample bisa datang dari dua
   arah — (a) dari pesanan/permintaan pelanggan, (b) pengembangan internal — dan tautan
   ke SO wajib hanya untuk yang (a)?

---

## II.6 Urutan yang saya sarankan (kalau nanti jadi dikerjakan)

Alasannya bukan "yang mudah dulu", melainkan **yang menjadi fondasi bagi sisanya**:

1. **MD jadi peran + divisi jadi alamat notifikasi.** Semua sisanya (penugasan desain,
   notif PO custom, stok menipis) menunggu jawaban "siapa MD" — dikerjakan belakangan
   berarti mengulang pekerjaan yang sama dua kali.
2. **Notifikasi ke alamat yang benar** (finance dapat jatuh tempo · stok menipis berhenti
   membanjiri semua orang · MD diberi tahu saat ada PO custom).
3. **Permintaan Desain (Design PO)** + rapor desainer + tenggat.
4. **Rantai printing tersambung**: desain ACC → item → eksklusif ke sales pemesan.
5. **Sample**: tahap `handfeel`, tautan ke SO, penanda "jadi & dikirim".
6. **Perpustakaan swatch** (sample fisik) — paling berdiri sendiri, jadi paling aman ditaruh terakhir.

---

# BAGIAN III — "MD vs Manager": apakah cukup GANTI ISTILAH? (2026-08-18)

> Pertanyaan pemilik: *"saya tidak ingin melakukan pekerjaan besar hanya untuk mengubah
> peran untuk fitur yang sudah ada. Jika apa yang dikerjakan manager saat ini adalah MD
> (definisinya), tinggal ganti saja istilah manager menjadi MD — bukankah itu mudah?"*

**Jawaban singkat: secara TEKNIS ya, murah.** Yang mahal bukan mengganti kata, melainkan
memastikan kata barunya **tidak berbohong**. Berikut angkanya.

## III.1 Kenapa ganti istilah memang murah di aplikasi ini

| Yang diganti | Jumlah titik | Catatan |
|---|---|---|
| **ID teknis** `manager` (di basis data, izin, kode) | **556** | **JANGAN disentuh.** Ganti ID = migrasi data akun + sesi + izin + 44 berkas. Tidak perlu. |
| **LABEL** yang dilihat pengguna ("Manajer"/"Manager") | **63** di ±30 berkas | Ini saja yang diganti. |

Aplikasi ini kebetulan sudah disiapkan untuk hal semacam ini — bukan kebetulan, tapi
karena pernah kena masalahnya: gate **`INV-ROLE-01`** (`scripts/guardrails/verify_role_label.py`)
sudah **melarang** peta label peran lokal, dan **melarang** tombol dinyalakan oleh nama
peran (wajib lewat izin). Artinya label lahir dari **satu registry** di tiap sisi
(`backend/role_registry.py` ↔ `frontend/src/config/roles.js` ↔ `navMeta.js`) dan gate
memaksa ketiganya identik. Ganti di registry → berubah di seluruh layar.

Sisanya adalah **kalimat** yang menyebut "manajer" di teks notifikasi, katalog
pengaturan, matriks persetujuan, dan resolver PDF. Mekanis, tetapi **wajib ikut diganti**
— kalau tidak, layar akan menyebut "MD" di satu tempat dan "manajer" di sebelahnya.

## III.2 Tapi: apakah `manager` hari ini MEMANG MD?

`manager` hari ini memegang **59 sumber daya izin**. Kalau dipisah menurut sifat
pekerjaannya, ia sebenarnya **dua orang dalam satu peran**:

**Gugus A — memang MD (merchandising & pesanan):**
buat/setujui **PO** · setujui **PR** · supplier, kontrak & harga supplier · **RFQ award** ·
warna · **R&D** (nilai/putuskan/kelola) · setujui **harga khusus** · setujui/konfirmasi
**pesanan** · setujui **transfer** · produksi & makloon · stock opname.
→ ini **persis** yang bagan Anda tuliskan sebagai pekerjaan MD ("md harus po",
"notif md untuk repeat/restock", "notif md untuk po custom", "stock menipis").

**Gugus B — BUKAN merchandising (uang & orang):**

| Wewenang | Izin |
|---|---|
| **Payroll** & data pribadi karyawan | `hr.manage_payroll`, `hr.view_pii` |
| **Buka periode / tutup buku mundur** | `period.unlock`, `period.backdate` |
| **Jurnal akuntansi** (buat/void/kelola) | `accounting.create/void/manage` |
| **Void kwitansi AR** (membalik uang masuk) | `ar_receipt.void` |
| **Denda**: terbitkan/hapuskan/sesuaikan/bayar | `penalty.*` |
| **Bayar tagihan supplier / kontrabon / landed cost** | `vendor_bill.pay`, `contra_bon.pay`, `landed_cost.pay` |
| **Batalkan faktur pajak** | `tax_invoice.cancel` |
| **Setujui amandemen keuangan** | `finance_amendment.approve` |
| **Aset tetap** (jalankan penyusutan, hapus-buku) | `fixed_asset.run/dispose` |
| **Anggaran** & hapus kas | `budget.*`, `cash.delete` |

Diukur juga: peran **`finance` (Kasir) TIDAK punya satu pun** dari gugus B yang berat
(vendor_bill · contra_bon · landed_cost · hr · period · budget · aset tetap). Yang punya
semuanya hanya **`admin`**, dan `admin` di aplikasi ini memang sudah berlabel
**"Direksi/Admin"**.

**Jadi pertanyaannya bukan teknis, melainkan tentang perusahaan Anda:**
orang yang Anda sebut **MD** — apakah dia juga yang **menyetujui payroll, membuka
periode yang sudah ditutup, dan membayar tagihan supplier?**
* **Kalau ya** → ganti label saja, selesai. Tidak ada yang berbohong.
* **Kalau tidak** → label "MD" akan muncul di layar payroll & pembayaran supplier, dan
  itu justru membuat orang bingung — persis penyakit yang dulu bikin peran `sales_admin`
  & `finance` harus dilahirkan (dulu orang alur-pesanan **terpaksa** dijadikan `manager`
  dan ikut kebagian payroll & tutup buku).

## III.3 Tiga pilihan, dengan biaya jujur

| | Apa yang dilakukan | Biaya | Migrasi data? |
|---|---|---|---|
| **Opsi 1** | **Ganti label saja**: "Manajer" → "MD" (63 titik). Wewenang **tidak berubah**. | **Kecil** (±1 sesi) | Tidak ada |
| **Opsi 2** | Ganti label **+ pindahkan gugus B ke Direksi/Admin** (cabut ±10 izin dari satu peran yang sudah ada). MD = murni merchandising. | **Sedang** — perlu cek layar mana yang jadi kosong untuk MD + perbarui POC peran | Tidak ada (izin, bukan akun) |
| **Opsi 3** | Bikin peran `md` **baru** dan `manager` tetap ada | **Besar** (44 berkas, seperti waktu `sales_admin` lahir) | Perlu memindahkan akun |

**Opsi 3 hanya masuk akal kalau di perusahaan Anda MD dan manajer keuangan adalah DUA
orang berbeda.** Kalau tidak, Opsi 1 atau 2 sudah cukup — dan pekerjaan besar yang Anda
tolak itu memang tidak perlu.

## III.4 Satu efek samping yang harus disadari

Divisi bernama **"MD"** sudah ada di `config_divisions.py`. Kalau **label peran** juga
menjadi "MD", akan ada dua benda bernama sama (peran MD & divisi MD). Bukan bug, tetapi
membingungkan. Saran: kalau Opsi 1/2 dipilih, **divisi `md` dihapus** dari daftar divisi
(karena sudah menjadi peran) — sisakan divisi untuk yang memang bukan peran:
Sample · Designer · RnD (Socmed dilewati sesuai keputusan Anda).

## III.5 Yang TIDAK ikut selesai walau label diganti

Ganti istilah **tidak** memperbaiki hal-hal ini — semuanya tetap perlu dikerjakan sendiri:
* Finance tidak menerima notifikasi jatuh tempo pelanggan (N4).
* "Stok menipis" masih dikirim ke **semua orang**, bukan ke MD saja (N5).
* PO custom masih **tidak memberi tahu MD** sama sekali (J5).
* Penugasan desain (Design PO), rapor desain per designer, rantai desain→item eksklusif,
  tahap `handfeel`, tautan sample↔SO, perpustakaan swatch — semuanya belum ada.

Dengan kata lain: **ganti istilah menyelesaikan soal NAMA, bukan soal ALUR.** Kabar
baiknya, tiga poin pertama di atas justru kecil dan bisa dikerjakan segera setelah nama
MD-nya pasti.

---

# BAGIAN IV — KOREKSI: "ganti label" GUGUR, karena MD hanya domain pembelian

> Jawaban pemilik: *"MD bukanlah yang menyetujui payroll, membuka periode, dll — hanya
> domain pembelian."*

## IV.1 Usulan saya sebelumnya (ganti label `manager` → MD) **saya tarik**

Kalau MD hanya pembelian, maka menamai peran `manager` sebagai "MD" akan membuat layar
**berbohong di dua arah sekaligus**: orang berlabel "MD" akan muncul sebagai penyetuju
**payroll & tutup buku**, DAN sebagai penyetuju **pesanan penjualan, harga khusus, dan
retur jual**. Dua-duanya bukan pekerjaan MD.

Terukur — `manager` (59 sumber daya izin) sebenarnya **tiga gugus**, bukan satu:

| Gugus | Contoh wewenang | Milik siapa menurut Anda |
|---|---|---|
| **A. Pembelian & pengembangan barang** | buat/setujui **PO** · setujui **PR** · supplier, kontrak, harga supplier · **RFQ** · warna · R&D · makloon | **MD** ✔ |
| **B. Penjualan & pesanan** | setujui/konfirmasi **pesanan** · setujui **harga khusus** · setujui **retur jual** · pelanggan | **bukan MD** |
| **C. Uang & orang** | payroll · buka periode · jurnal · void kwitansi · denda · **bayar** tagihan supplier · faktur pajak · aset tetap | **bukan MD** |

## IV.2 Koreksi angka saya sendiri: "44 berkas" itu menyesatkan

Saya sempat menakut-nakuti dengan "peran baru = 44 berkas". Itu **jumlah berkas yang
MENYEBUT** `sales_admin` — termasuk berkas uji, skrip audit, dan komentar. Yang benar-benar
**WAJIB** diubah saat melahirkan satu peran baru jauh lebih sedikit, karena FASE E-8
sudah meninggalkan mekanismenya:

| Wajib diubah | Kenapa hanya segini |
|---|---|
| `backend/role_registry.py` | 1 entri (label · peringkat · beranda) |
| `backend/permissions_config.py` | 1 blok izin (khusus pembelian) |
| `frontend/src/config/roles.js` | 1 entri **+ `ROLE_NAV`**: `inherit` menu peran lain, lalu `add`/`remove` — tidak perlu menyunting ±40 baris menu |
| `frontend/src/config/navMeta.js` | beranda peran |
| `seed_realistic.py` | 1 akun demo MD |
| POC & gate peran (4 berkas) | daftar peran di uji `role_access` / `e8_roles` / `verify_role_label` |

Gate **`INV-ROLE-01`** justru menjadi teman di sini: ia **memaksa** registry server ↔
layar ↔ menu identik, dan **melarang** tombol dinyalakan oleh nama peran (wajib lewat
izin). Artinya peran baru tidak bisa "setengah lahir" tanpa gate memerah.

**Estimasi jujur: satu sesi**, bukan pekerjaan besar — dengan syarat MD memakai layar
pembelian yang **sudah ada** (belum bikin "Meja MD" dengan antrean sendiri).

## IV.3 Dua pilihan yang masuk akal sekarang

**Opsi A — jangan sentuh peran; perbaiki ALAMAT notifikasi berdasarkan WEWENANG.**
Alih-alih mengirim ke nama peran, kirim ke *"siapa pun yang berwenang membuat/menyetujui
PO"* (hari ini: manajer & admin). Ini sekaligus menyembuhkan penyakit yang sudah terukur:
`low_stock` dikirim `recipient_role="all"` sehingga **finance & sales masing-masing
menerima 9 notifikasi stok menipis** yang bukan urusannya. Kalau nanti peran MD lahir,
ia **otomatis** ikut menerima — tanpa satu baris pun diubah lagi.
→ Biaya kecil · tanpa peran baru · tanpa migrasi.

**Opsi B — lahirkan peran `md` (pembelian saja), plus Opsi A.**
Blok izinnya subset gugus A. Akun manajer yang ada **tidak diapa-apakan**; Anda tinggal
mengubah/membuat akun orang pembelian menjadi MD lewat layar "Akun & Akses".
→ Biaya satu sesi · tanpa migrasi akun.

Yang **tidak** saya sarankan lagi: mengganti label `manager` menjadi MD (Opsi lama).

## IV.4 Pertanyaan yang tersisa untuk memastikan batas MD

Bagan Anda juga menulis *"md jakarta assign to designer to design"* — jadi MD bukan
hanya membeli, ia juga **menugaskan desain**. Yang perlu dipastikan: dari daftar ini,
mana yang wewenang MD?

* Buat & setujui **PR** (permintaan pembelian)
* Buat & setujui **PO** (pesanan pembelian)
* Kelola **supplier**, kontrak supplier, harga supplier, **RFQ**
* **Terima/verifikasi tagihan supplier** (vendor bill) — *membayarnya tetap finance*
* **Kontrabon** & **landed cost** (biaya masuk barang impor)
* Kelola **master produk & warna** (bikin SKU baru)
* **Menugaskan desain** ke designer + memutuskan hasilnya (ACC desain)
* Memutuskan **R&D/sample** (labdip · handfeel · proofing)
* **Makloon** (jahit/proses ke pihak ketiga)
