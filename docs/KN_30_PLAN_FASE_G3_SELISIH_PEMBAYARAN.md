# KN-30 — PENUTUPAN **FASE G-3: SELISIH PEMBAYARAN (LEBIH & KURANG BAYAR)**
### + penautan kolom denda **Umur Piutang** ke **nota denda nyata**

> Sesi: 2026-07-29 · Repo `fajjanabana/kn` · Bahasa: Indonesia
> Bukti: POC `backend/test_g3_variance_poc.py` **70/0 HIJAU** · `verify_data_integrity`
> **204 PASS / 0 FAIL / 0 WARN** · `gate.sh --full` HIJAU · `testing_agent_v3` iter_178
> (backend **43/43**, 0 bug) · 7 user story UI diverifikasi langsung.

---

## 1. Masalah nyata yang ditutup

**(a) Uang masuk hampir tidak pernah pas.** Pelanggan dipotong biaya transfer, membayar
sebagian karena arus kas, atau justru mengirim lebih. Sistem lama hanya punya dua sikap
ekstrem: **menolak** ("melebihi outstanding") atau **diam-diam** menaruh kelebihan ke
deposit. Akibatnya keputusan *"ya sudah, anggap lunas"* terjadi di WhatsApp — bukan di
sistem — dan sisa receh menggantung bertahun-tahun di laporan piutang.

**(b) Kolom denda di Umur Piutang adalah angka mati.** Denda hanya estimasi informasional:
tidak bisa ditagih, tidak bisa dinegosiasikan, tidak pernah jadi dokumen. FASE G-2 sudah
melahirkan **nota denda** sebagai dokumen, tetapi laporan penagihan belum menunjuk ke sana.

---

## 2. Terobosan desain — "Kebijakan Selisih Pembayaran"

Sistem **tidak menuntut nominal persis**, tetapi setiap selisih **wajib punya label
keputusan** dengan pemutus yang jelas. Dua batas dipakai — dan inilah yang membuat angkanya
jujur:

| Istilah | Arti |
|---|---|
| `expected` | Σ tagihan yang **sudah jatuh tempo** pada pesanan tujuan (baris rencana FASE G-2, atau term pesanan bila belum ada rencana) |
| `capacity` | nominal yang benar-benar **bisa dialokasikan** (sisa tagihan pesanan tujuan / nominal alokasi yang disebut petugas) |

Uang **di antara** kedua batas itu (mis. pelanggan membayar cicilan berikutnya lebih awal)
**BUKAN selisih** — uangnya masih mendarat di tagihan yang sama, jadi tidak ada yang perlu
diputuskan. Selisih hanya lahir bila uang **kurang dari yang jatuh tempo** atau **lebih dari
yang bisa dialokasikan**.

| Kondisi | Perlakuan |
|---|---|
| `abs(delta) <= toleransi` | **otomatis** (`rounding_writeoff` / `rounding_deposit`) — tanpa persetujuan, **tetapi tetap jadi keputusan berlabel** yang bisa diaudit |
| `delta < 0` (kurang) | (a) **sisa tetap piutang** *(bawaan)* · (b) **ubah jadwal** — sisa jadi tempo baru · (c) **hapus sisa** + alasan + wewenang |
| `delta > 0` (lebih) | (a) **deposit pelanggan** *(bawaan)* · (b) **alokasi ke pesanan terbuka lain** · (c) **kembalikan dana** (kas keluar) |

### Kejujuran akuntansi: keputusan = dokumen sendiri
Kwitansi tetap dibukukan seperti biasa (Dr Kas · Cr Piutang sebesar yang teralokasi · Cr
2-1400 Uang Muka Pelanggan sebesar kelebihannya). Keputusan selisih **tidak mengubah jurnal
kwitansi** (ledger append-only, aturan repo #7) melainkan menerbitkan jurnalnya sendiri:

| Keputusan | Jurnal |
|---|---|
| hapus sisa kurang bayar / pembulatan | Dr **6-9100** Beban Selisih Pembayaran / Cr 1-1200 Piutang |
| kelebihan dipakai untuk pesanan lain | Dr 2-1400 Uang Muka Pelanggan / Cr 1-1200 Piutang |
| kelebihan dikembalikan | Dr 2-1400 Uang Muka Pelanggan / Cr Kas (lewat `cash_transactions` `ref_type=ar_refund`) |
| keputusan dianulir / kwitansi di-void | **jurnal pembalik** (arah ditukar), jurnal lama tidak diubah |

Karena itu keputusan bisa diambil **saat kwitansi dibuat** maupun **belakangan** dari
antrean "Selisih Bayar" tanpa pernah menghasilkan pembukuan ganda.

---

## 3. Yang dibangun

### 3.1 Backend
| Berkas | Isi |
|---|---|
| `services/payment_variance_service.py` (baru, ±1.200 baris) | `variance_policy` · `pre_assess` (takar selisih server-side) · `decide_receipt` (6 jenis keputusan) · `reverse_decision` (anulir + jurnal pembalik) · `assess_bill`/`decide_bill` (jalur AP) · `pending`/`list_decisions`/`stats` · bahan invarian |
| `routers/payment_variance.py` (baru) | `GET /api/payment-variances/meta` · `POST /assess` · `GET /` (+pending+stats) · `GET /pending` · `GET /receipt/{id}` · `POST /receipt/{id}/decide` · `GET /{id}` · `POST /{id}/reverse` |
| `services/ar_receipt_service.py` | takar selisih SEBELUM alokasi · blok `variance` tersimpan di kwitansi · penyelesaian otomatis dalam toleransi · `apply_from_deposit` · **jurnal kas diposting seketika** (tidak menunggu backfill) · void membalik keputusan + jurnal pembalik kas |
| `services/payment_plan_service.py` | `recompute_paid` v2: **alokasi ke baris jadwal yang DISEBUT** (`allocations[].plan_line_seq`) lalu waterfall · `reschedule_line` (geser / pecah baris, Σ rencana tetap) · `due_lines`/`due_now_amount` |
| `services/gl_service.py` | akun **6-9100** · `post_variance_writeoff` · `post_ap_variance_writeoff` · `post_variance_reallocation` · `post_variance_reversal` · `post_cash_void` · routing kas `ar_refund` & `ap_advance` |
| `routers/vendor_bills.py` | pembayaran supplier ikut ditakar: kurang receh → tagihan LUNAS (`ap_rounding_writeoff`), lebih bayar wajib keputusan `ap_advance` → **uang muka supplier** (1-1400) + `suppliers.advance_balance` |
| `config_catalog_payment.py` | **9 kunci baru** di Pusat Pengaturan → *Uang Masuk & Piutang* (toleransi AR & AP, pilihan bawaan kurang/lebih bayar, wajib persetujuan, peran penyetuju, batas nominal, hari perpanjangan tempo, cara pengembalian) |
| `services/amendment_service.py` | **9 label alasan** baru `applies_to: payment_variance` (taksonomi G-1, bisa ditambah admin) |
| `permissions_config.py` | domain baru `payment_variance: [view, decide]` (admin · manager · sales) |
| `services/doc_refs_service.py` | tipe dokumen baru `payment_variance` → keputusan ikut **Jejak Dokumen** (dua arah) |

### 3.2 Invarian baru (jujur & bukti-merah)
* **INV-VAR-01** — setiap selisih di luar toleransi punya keputusan **berlabel** (kode alasan
  + pemutus). Antrean yang masih segar = WARN (wajar), **menggantung >7 hari = FAIL**.
* **INV-VAR-02** — uang tidak hilang: (a) tiap kwitansi `dana == teralokasi + belum
  teralokasi`; (b) tiap keputusan yang memindahkan uang punya **jurnal** dan tidak melebihi
  kelebihan bayar kwitansinya.
* Kwitansi lama (sebelum G-3, mis. dari seed) **tidak dituduh melanggar** — selisihnya
  memang belum pernah ditakar. Ini ditulis eksplisit di kode invariannya.

### 3.3 Frontend
| Berkas | Isi |
|---|---|
| `payments/PaymentVarianceDialog.jsx` (baru) | dialog bahasa manusia: *"Dibayar Rp 9.950.000, seharusnya Rp 10.000.000 (tagihan yang jatuh tempo). Kurang Rp 50.000 — mau bagaimana?"* + 3 kartu pilihan berikut **dampak**, badge *disarankan* / *wajib manager*, alasan wajib, input tambahan (tanggal baru · pesanan tujuan · cara pengembalian) |
| `payments/PaymentVarianceQueue.jsx` (baru) | tab **Selisih Bayar**: KPI (perlu diputus · sisa dihapus · dana dikembalikan · dialihkan · selesai otomatis) + tabel **Perlu diputus** (umur >7 hari memerah) + **Riwayat keputusan** (jenis, alasan, pemutus, jurnal, tombol anulir) |
| `crm/ARReceiptModal.jsx` | takar selisih **live** saat nominal/alokasi berubah + pengingat sebelum simpan + dialog keputusan → keputusan ikut terkirim bersama kwitansi |
| `crm/ARReceiptsHistory.jsx` | kolom **Selisih**: badge keputusan atau *"perlu diputus"* |
| `finance/payments/PaymentPlansView.jsx` | tab ketiga **Selisih Bayar** (+ badge jumlah antrean) |
| `finance/ARAgingView.jsx` | lihat §4 |

---

## 4. Poin #2 — kolom denda Umur Piutang → **nota denda nyata**

* `ar_aging_service.aging_report` & `customer_aging_detail` sekarang membawa: `penalty_docs`,
  `penalty_draft`, `penalty_issued`, `penalty_waived`, `penalty_paid`, `penalty_actual`,
  **`denda_undocumented`** (estimasi yang belum pernah dibuatkan nota), daftar `penalties`
  per pesanan & per pelanggan, `plans`, dan `penalty_policy` yang berlaku.
* `penalty_service.accrue_order()` **baru** — pesanan **TANPA** rencana pembayaran kini juga
  bisa punya nota denda (pesanan diperlakukan sebagai satu baris jatuh tempo memakai term
  pelanggan), memakai kebijakan · perhitungan · jurnal · siklus keputusan yang SAMA.
  `accrue_customer()` menyapu rencana + pesanan tanpa rencana. **Idempoten per periode.**
* Endpoint baru **`POST /api/ar/aging/{customer_id}/accrue-penalties`** (permission
  `penalty:issue`) — tombol *"Buat Nota Denda"* di layar penagihan.
* UI `ARAgingView`: KPI **Nota Denda**, kolom **Denda** menampilkan nominal nota nyata +
  `{n} nota` (bisa diklik) atau *"est. — belum jadi nota"* + tombol **Buat Nota**; drill-down
  menampilkan kolom **Nota Denda** per pesanan (badge nomor → Jejak Dokumen) dan panel
  **Nota Denda Pelanggan Ini** dengan `PenaltyPanel` penuh (Terbitkan · Ubah Nominal ·
  Bebaskan · Catat Bayar).
* Catatan kejujuran yang ditulis di layar: estimasi dihitung kasar atas sisa jatuh tempo,
  sementara nota denda memakai **dasar kebijakan** (mis. *nilai cicilan yang telat*) — jadi
  keduanya memang bisa berbeda, dan sekarang bedanya terlihat, bukan disembunyikan.

---

## 5. Bukti

| Bukti | Hasil |
|---|---|
| POC `backend/test_g3_variance_poc.py` | **70 PASS / 0 FAIL** (13 skenario + bukti-merah 4 invarian + nol residu) |
| `scripts/verify_data_integrity.py` | **204 PASS / 0 FAIL / 0 WARN** |
| `bash scripts/gate.sh --full` | HIJAU (POC G-0/G-1/G-2/**G-3**/G-4/F-1/D ikut dijalankan) |
| `testing_agent_v3` iter_178 | backend **43/43**, 0 bug; UI: komponen & login terverifikasi |
| Verifikasi UI manual | 7 user story lintas layar (Umur Piutang · drill-down + PenaltyPanel · tab Selisih Bayar · dialog kurang bayar & simpan · dialog lebih bayar 3 pilihan · kolom Selisih di riwayat kwitansi · wewenang sales ditolak) |

### Bug nyata yang ditemukan & diperbaiki selama fase ini
1. **Blok `variance` & `plan_line_seq` hilang di jalan** — model Pydantic `ReceiptPayload`
   membuang field yang tidak dideklarasikan, sehingga keputusan yang dipilih petugas
   **tidak pernah sampai** ke server (semua keputusan inline gagal senyap). Ditemukan POC.
2. **Selisih dihitung dari batas yang salah** — versi pertama membandingkan uang masuk hanya
   dengan tagihan jatuh tempo, sehingga membayar cicilan berikutnya lebih awal dilaporkan
   sebagai "lebih bayar" padahal uangnya masih bisa dialokasikan. Diperbaiki dengan dua
   batas (`expected` & `capacity`).
3. **Jurnal kas AR tertunda** — jurnal kwitansi baru terbentuk saat backfill startup,
   sehingga keputusan selisih bisa men-debit 2-1400 sebelum kwitansinya meng-kredit akun
   yang sama (saldo kewajiban sesaat negatif). Sekarang jurnal kas AR diposting seketika,
   dan void kwitansi menerbitkan **jurnal pembalik** (`post_cash_void`).
4. **Contoh demo bisa membuat saldo AR negatif** — seed G-3 sempat membayar pesanan yang
   pendapatannya belum dijurnal (kredit Piutang tanpa debit pasangan). Seed sekarang hanya
   memilih pesanan yang sudah ber-jurnal pendapatan; INV-AR-01 kembali 0 WARN.

---

## 6. Data demo baru (idempoten)
`seed_realistic.py → seed_payment_variances()` membuat **3 kwitansi uji lewat layanan
produksi**: (1) kurang bayar receh → pembulatan otomatis + jurnal beban selisih;
(2) kurang bayar besar → keputusan *sisa tetap piutang*; (3) lebih bayar → keputusan
*simpan sebagai deposit*. Sengaja **tidak** meninggalkan selisih menggantung supaya antrean
"Selisih Bayar" pada DB baru benar-benar kosong.

---

## 7. Catatan & batasan yang jujur
* **Kurang bayar ke supplier (AP)** yang wajar (cicilan) tidak dipaksa punya keputusan —
  hanya penutupan sisanya (`ap_writeoff`) dan kelebihan bayar (`ap_advance`) yang wajib
  berlabel. Kalau kelak kontrabon (G-7) masuk, uang muka supplier ini yang dipotongkan.
* Keputusan **ubah jadwal** hanya tersedia bila pesanan punya rencana pembayaran (G-2);
  dialog menyebutkan alasannya bila tidak tersedia (bukan tombol mati tanpa penjelasan).
* Keputusan yang **dianulir** tidak memaksa jadwal yang sudah digeser kembali ke tanggal
  lama — itu kesepakatan dengan pelanggan; yang dibalik adalah uang & jurnalnya, dan
  pembatalannya tercatat.
* Kanal WhatsApp & OTP e-sign tetap provider **`simulated`** (keputusan pemilik).
* Frontend **tanpa hot reload**: jalankan `bash scripts/rebuild_frontend.sh` setelah
  mengubah `frontend/src`.

---

## 8. Langkah berikutnya (§G-11)
1. **G-8 Rekonsiliasi Bank Otomatis** — parser multi-bank + skor berbobot; menyuplai antrean G-9.
2. **G-9 Pusat Kasus Keuangan** — playbook kasus (salah transfer, dana tak dikenal, bayar dua kali…).
3. **G-7 Kontrabon Advanced** — 3-way match + potongan terstruktur; memakai uang muka supplier dari G-3.
