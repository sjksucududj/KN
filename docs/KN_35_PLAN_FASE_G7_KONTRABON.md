# KN_35 — FASE G-7: KONTRABON ADVANCED (SIKLUS TUKAR FAKTUR SUPPLIER)

> Spesifikasi asal: `plan.md` §G-7 (permintaan pemilik #7) · urutan §G-11 **#7**.
> Dependensi **sudah lengkap**: G-1 (koreksi ber-alasan) · G-4 (relasi dokumen) ·
> G-3 (selisih bayar / uang muka supplier) · G-8 (rekonsiliasi bank).
> Keputusan pemilik **2026-07-30**: *"G-7"*, dengan tiga penegasan:
> **(a)** pembayaran kontrabon **harus terhubung** ke Rekonsiliasi Bank G-8,
> **(b)** toleransi 3-way match **jadi config** (bisa diubah pemilik sendiri),
> **(c)** jadwal tukar faktur **perlu pengingat otomatis**.

---

## 1. Masalah nyata yang diselesaikan

Supplier tekstil tidak ditagih per surat jalan. Mereka datang **satu kali per siklus**
(mis. tiap Selasa) membawa setumpuk faktur, lalu terjadi ritual **tukar faktur**:
faktur supplier ditukar dengan **tanda terima** dari kami, dan pembayarannya dijadwalkan.
Hari ini di sistem:

| Kenyataan lapangan | Kondisi sistem sebelum G-7 |
|---|---|
| Satu pembayaran menutup **banyak** faktur dari satu supplier | Pembayaran hanya bisa **per** `vendor_bill` (`POST /vendor-bills/{id}/pay`) — 12 faktur = 12 transaksi kas |
| Barang sudah diterima tapi supplier **belum** menagih | Tidak ada satu pun layar yang menjawab *"GR mana yang belum ditagih?"* |
| Faktur supplier dipotong: retur beli, uang muka, denda, selisih 3-way | Potongan hanya ada di jalur makloon (`potong_bon`) — sisanya **di luar sistem** |
| Selisih 3-way di luar toleransi harus **diputus berlabel** | Toleransi ada (`purchasing.bill_*_tolerance_percent`) tapi hanya per faktur, dan tak ada dokumen keputusan tingkat siklus |
| Supplier butuh **tanda terima** bertanda tangan | Tidak ada dokumennya |
| Retur beli `ap_credit` **sudah** mengurangi Hutang di buku besar… | …tetapi **tidak** mengurangi subledger `vendor_bills` → GL dan daftar hutang **berbeda** dan tidak ada yang menutup selisihnya |

Baris terakhir adalah temuan paling penting: G-7 bukan cuma fitur baru, ia **menutup celah
rekonsiliasi yang sudah ada**.

---

## 2. Temuan awal (dibaca dari kode, sebelum menulis apa pun)

| # | Temuan | Konsekuensi desain |
|---|---|---|
| 1 | `vendor_bills` sudah punya 3-way match per faktur (`evaluate_match`) dengan toleransi **persen** dari `settings.purchasing.*` | G-7 **tidak** menulis mesin match baru; ia **memanggil ulang** mesin yang sama saat verifikasi, lalu menambah toleransi **nilai rupiah** (permintaan pemilik) di atasnya |
| 2 | `makloon_claim_service.approve` aksi `potong_bon` **sudah** memotong `vendor_bills.grand_total` **dan** memposting `Dr 2-1100 / Cr 4-9200` | Potongan makloon **TIDAK BOLEH** jadi potongan kontrabon (dobel). Ditampilkan sebagai **informasi** "sudah menempel di tagihan" + penjaga eksplisit yang menolak bila dicoba |
| 3 | `purchase_return` outcome `ap_credit` memposting `Dr 2-1100 / Cr 1-1300` dan mengurangi `purchase_orders.returned_amount`, **tanpa** menyentuh `vendor_bills` | Potongan retur beli di kontrabon = **pelunasan NON-KAS** pada faktur, **tanpa jurnal baru** (jurnalnya sudah ada). Justru inilah yang merapikan drift GL↔subledger |
| 4 | Uang muka supplier hidup sebagai `cash_transactions.ref_type="ap_advance"` (`Dr 1-1400 / Cr Kas`), tanpa buku pemakaian | Pemakaiannya **butuh** jurnal: `Dr 2-1100 / Cr 1-1400`, dan butuh penjaga "satu uang muka tak boleh dipakai dua kali" |
| 5 | Denda **supplier** belum ada (G-2 `penalties` khusus pelanggan: `Dr 1-1270 / Cr 4-9300`) | Denda supplier di G-7 = potongan ber-alasan dengan jurnal `Dr 2-1100 / Cr 4-9300` — bukan koleksi baru |
| 6 | Rekonsiliasi bank G-8 mencocokkan `bank_statement_lines` ↔ `cash_transactions`, dan `_ref_score` membaca `number/description/ref_id` | Cukup satu transaksi kas ber-`ref_type="contra_bon"` yang **memuat nomor kontrabon di deskripsi** → langsung jadi kandidat. Plus jalur balik: **bayar kontrabon dari baris mutasi** |
| 7 | GRN = `wms_tasks` (`flow_type=inbound`, `po_id`); `already_billed_map()` sudah menghitung qty tertagih per PO | "GR belum ditagih" bisa dihitung **tanpa koleksi baru** |
| 8 | `amendment_reasons` punya `applies_to` (taksonomi G-1 yang bisa ditambah admin) | Label alasan kontrabon = 6 kode baru dengan `applies_to: ["contra_bon"]`, bukan enum keras di kode |

---

## 3. Yang dibangun

### 3.1 Backend

| Berkas | Isi |
|---|---|
| `services/contra_bon_service.py` | Mesin: `prepare()` (rakit kandidat), `create()`, `add/remove_deduction()`, `decide()` (keputusan berlabel), `submit/verify/approve/schedule/pay/dispute/cancel`, `unbilled_receipts()`, `summary()` |
| `services/contra_bon_reminder.py` | Jadwal tukar faktur per supplier + job pengingat H-1 & eskalasi kontrabon nganggur |
| `routers/contra_bons.py` | 18 endpoint `/api/contra-bons/*` + `/suppliers/{id}/invoice-exchange` |
| `schemas_contrabon.py` | Model Pydantic (nominal `MoneyDecimal`, qty `QtyDecimal`) |
| `config_catalog_contrabon.py` | Grup **`kontrabon`** di Pusat Pengaturan — 10 kunci |
| `services/gl_service.py` | `ref_type="contra_bon"` → lawan akun `2-1100`; `post_contra_bon_deduction()` |
| `services/amendment_service.py` | 6 label alasan `applies_to: ["contra_bon"]` |
| `services/doc_refs_service.py` | Jenis dokumen `contra_bon` + aturan backfill relasi |
| `services/pdf_resolvers.py` | `contra_bon` → **Tanda Terima Kontrabon** (esignable) |
| `services/scheduler_service.py` | Job `contra_bon_reminder` (harian 07:30 WIB) |
| `scripts/verify_data_integrity.py` | Lapisan `contrabon` — **INV-CB-01..04** |

### 3.2 Koleksi `contra_bons` (prefix `cbn_`, nomor `<ENT>/CB-#####`) — SCOPED

```
bills[]      : {bill_id, bill_number, supplier_invoice_no, po_id, po_number, bill_date,
                due_date, grand_total, outstanding_at_pick, applied_amount,
                match:{status, exceptions[]}, claim_deduction_info}
deductions[] : {id, kind, ref_type, ref_id, ref_number, amount, reason_code, note,
                gl_journal_id, posts_gl, added_by, added_at}
decisions[]  : {at, by, exception_key, bill_id, action, reason_code, amount, note}
totals       : {bills_total, deductions_total, net_payable, paid_total, outstanding}
match_summary: {status, exceptions_count, tolerance:{qty_percent, value_rupiah}}
schedule     : {planned_payment_date, method, bank_account_id, notes}
payments[]   : {id, amount, method, cash_txn_id, cash_txn_number, bank_line_id, paid_at, paid_by}
timeline[]   : jejak waktu · refs[] : relasi dua arah (G-4)
```

Siklus: `draft → submitted → verified → approved → scheduled_payment → paid`
(+ `disputed` dari `submitted`/`verified`, + `cancelled` hanya dari `draft`).

### 3.3 Lima jenis potongan (SSOT `DEDUCTION_KINDS`)

| Kind | Menunjuk dokumen | Jurnal saat kontrabon DIBAYAR |
|---|---|---|
| `purchase_return` | `purchase_returns` (approved · `ap_credit` · belum terpakai) | **tidak ada** — `Dr 2-1100 / Cr 1-1300` sudah diposting saat retur disetujui |
| `supplier_advance` | `cash_transactions` (`ap_advance`, sisa belum terpakai) | `Dr 2-1100 / Cr 1-1400` |
| `supplier_penalty` | nominal manual + alasan wajib | `Dr 2-1100 / Cr 4-9300` |
| `match_variance` | selisih 3-way yang diputus dipotong (menunjuk `bill_id`) | `Dr 2-1100 / Cr 2-1150` (GR/IR — barangnya memang tak diterima) |
| `other_agreed` | nominal manual + alasan wajib | `Dr 2-1100 / Cr 4-9000` |
| *(info)* `makloon_claim` | `vendor_bills.claim_deduction` | **ditolak** bila dicoba jadi potongan (sudah menempel) |

### 3.4 Config Pusat Pengaturan (grup `kontrabon`)

`qty_tolerance_percent` (1%) · `value_tolerance_rupiah` (Rp 50.000) ·
`require_reason_out_of_tolerance` (ya) · `approval_threshold_rupiah` (Rp 50.000.000) ·
`approval_role` (manager) · `high_value_approval_role` (admin) ·
`reminder_days_before` (1 = H-1) · `unbilled_gr_age_days` (3) ·
`verify_sla_days` (2) · `block_pay_before_approval` (ya).

### 3.5 Frontend `features/purchasing/contrabon/`

`ContraBonsView.jsx` (KPI + 3 tab: Daftar Kontrabon · GR Belum Ditagih · Jadwal Tukar Faktur) ·
`ContraBonCreateWizard.jsx` (3 langkah) · `ContraBonDetailPanel.jsx` ·
`DeductionModal.jsx` · `DecisionModal.jsx` · `PayModal.jsx` · `ExchangeScheduleModal.jsx` ·
`contraBonApi.js` (kamus label). Semua modal punya **bilah error sendiri** (INV-UI-03 aturan C),
nama entitas lewat `entityLabel` (INV-UI-02), nominal lewat `formatCurrency` (aturan i18n [7]).

---

## 4. User stories (dipakai juga sebagai skenario uji)

| # | Sebagai | Saya ingin | Bukti lulus |
|---|---|---|---|
| US1 | Keuangan | melihat **jadwal tukar faktur** per supplier & diingatkan **H-1** | jadwal tersimpan; job `contra_bon_reminder` membuat notifikasi H-1 berisi jumlah GR belum ditagih + tagihan siap |
| US2 | Keuangan | menggabungkan **banyak tagihan** satu supplier jadi **satu** kontrabon bernomor `<ENT>/CB-#####` | 1 kontrabon berisi ≥2 faktur dari ≥2 PO |
| US3 | Keuangan | melihat **GR yang belum ditagih** supaya tak ketinggalan menagih | daftar menampilkan PO/GR + nilai belum ditagih; hilang setelah ditagih |
| US4 | Keuangan | 3-way match dengan **toleransi dari Pusat Pengaturan**; di luar toleransi **wajib keputusan berlabel** | ubah toleransi di config → hasil verifikasi berubah; verify tanpa keputusan → **400 menuntun** |
| US5 | Keuangan | memasukkan **potongan terstruktur** yang menunjuk dokumen nyata | 5 jenis potongan jalan; retur beli/uang muka **tak bisa dipakai dua kali**; potongan makloon ditolak dengan alasan |
| US6 | Manajer | siklus lengkap + **ambang persetujuan dari config** + pemisahan tugas | kontrabon > ambang butuh admin; pembuat ≠ penyetuju (403) |
| US7 | Keuangan | membayar sekali untuk semua faktur; potongan jadi **pelunasan non-kas** | satu `cash_transactions`; tiap faktur `amount_paid` naik; Σ = net + potongan; GL seimbang |
| US8 | Keuangan | pembayaran kontrabon **nyambung** ke Rekonsiliasi Bank | transaksi kas jadi kandidat berskor; **bayar kontrabon dari baris mutasi** → baris `matched` |
| US9 | Keuangan | **mencetak Tanda Terima Kontrabon** | PDF memuat semua faktur/PO/GR + potongan + net |
| US10 | Semua | relasi dokumen dua arah + jejak waktu | `refs` kontrabon ↔ faktur ↔ PO ↔ retur ↔ kas; timeline memuat siapa memutus apa |
| US11 | Admin | isolasi lintas-PT & invarian dijaga gate | kontrabon PT lain → 403; INV-CB-01..04 **bukti-merah** |

---

## 5. Invarian baru

* **INV-CB-01** — satu `vendor_bill` hanya boleh berada di **satu** kontrabon yang belum
  `cancelled`; dan Σ `applied_amount` seluruh kontrabon atas satu faktur ≤ `grand_total`.
* **INV-CB-02** — `net_payable == Σ bills.applied_amount − Σ deductions.amount` (≥ 0), dan
  kontrabon `paid` → `Σ payments.amount == net_payable`.
* **INV-CB-03** — setiap pengecualian 3-way **di luar toleransi** wajib punya keputusan
  berlabel (`reason_code` terdaftar di `amendment_reasons` untuk `contra_bon`) sebelum
  status melewati `verified`.
* **INV-CB-04** — satu dokumen potongan (`purchase_return` / `ap_advance`) hanya boleh
  dipakai di **satu** kontrabon belum `cancelled`, dan potongan makloon yang sudah menempel
  di faktur **tidak** boleh muncul sebagai potongan kontrabon.

---

## 6. Status

✅ **DITUTUP 2026-07-30** — 11/11 user story LULUS. Bukti ada di bagian 7.

---

## 7. Hasil penutupan (2026-07-30 · repo `hakakanabava/kn`)

### 7.1 Bukti
| Bukti | Hasil |
|---|---|
| POC `backend/test_g7_contrabon_poc.py` | **120 PASS / 0 FAIL** (nol residu, stabil 3× berturut) |
| Invarian `scripts/verify_data_integrity.py` | **223 PASS / 0 FAIL / 0 WARN** (INV-CB-01..04 teruji **bukti-merah**) |
| `bash scripts/gate.sh --full` | **41 gate HIJAU** (140 s) — termasuk gate baru *POC FASE G-7* |
| `testing_agent_v3` | **iter_189** — backend 120/120, frontend nol bug |
| Uji layar Playwright (3 bagian, 4 peran) | **49 PASS / 0 FAIL** — A 21 · B 17 · C 11 |
| Data demo | 3 kontrabon nyata + 1 faktur bebas + 3 jadwal tukar faktur + 1 baris mutasi bank untuk US8 |

### 7.2 Yang dibangun di sesi penutupan
* **Seluruh frontend G-7** (sebelumnya baru backend): `features/purchasing/contrabon/`
  — `ContraBonsView` (6 KPI + 3 tab) · `ContraBonListTable` · `ContraBonDetailPanel` +
  `ContraBonParts` · `ContraBonCreateWizard` (3 langkah) · `UnbilledReceiptsTab` ·
  `ExchangeSchedulesTab` · 6 modal (`ExchangeSchedule` · `Deduction` · `Decision` ·
  `Pay` · `PaymentSchedule` · `ReasonNote`) · `contraBonApi.js`.
* **Jembatan G-8 → G-7 di layar**: `features/finance/bank/ReconContraBonModal.jsx` +
  tombol **"Bayar kontrabon"** pada baris mutasi dana KELUAR di `ReconLinesTable`.
* **Wiring IA**: tab hub `accounts-payable` (Gudang ikut melihat), `navMeta`, `AppViewRouter`.
* **Data demo lewat jalur produksi**: `seed_contra_bons()` memanggil endpoint yang SAMA
  dengan UI lewat `httpx.ASGITransport` (in-process, tanpa jaringan) — bukan dokumen
  karangan. Catatan lapangan: **login menaruh session cookie**, jadi dua peran WAJIB
  memakai dua klien HTTP terpisah; satu klien membuat pemisahan tugas menolak sendiri.
* **Gate baru** `POC FASE G-7` di `scripts/gate.sh` + label invarian 219 → 223.

### 7.3 Bug NYATA yang ditutup (detail di `memory/BUG_REGISTRY.md`)
| ID | Sev | Inti masalah |
|---|---|---|
| **KN-G7-POC-DRIFT** | P2 | POC memaku id supplier & nomor PO yang tidak deterministik → **titik henti sesi sebelumnya** (16/16 FAIL) |
| **KN-SEED-PO-ENTITY-RANDOM** | P1 | entitas PO demo diacak `random.random()` tanpa seed → data demo flaky + PO PT-A ke supplier PT-B |
| **KN-G7-CSS-GHOST** | P1 | 6 nama kelas CSS dipakai 11 berkas layar tetapi **0** di bundel CSS → kartu KPI & kotak isian tampil tanpa gaya (uji fungsional tetap hijau) |
| **KN-G7-WH-PERM-NOISE** | P2 | peran Gudang disambut bilah merah "Permission ditolak: supplier.view" di layar yang boleh dibukanya |
| **KN-G7-SCHED-DEFAULT-NONE** | P2 | "Atur jadwal" default *Tidak terjadwal* → Simpan tidak berdampak apa pun yang terlihat |
| **KN-G7-NOTICE-TIMER** | P2 | timer pesan lama menghapus konfirmasi baru (tampil ±0,5 detik) |
| **KN-G7-DEMO-NO-CANDIDATE** | P2 | seluruh faktur demo terpakai → wizard "Kontrabon baru" kosong untuk semua supplier |

### 7.4 Peta user story → bukti layar
| # | Bukti di layar (Playwright, peran) |
|---|---|
| US1 | tab *Jadwal Tukar Faktur*: 3 supplier terjadwal · modal ubah jadwal tersimpan & PIC tampil · "Jalankan pengingat" memberi kalimat hasil (1 notifikasi) |
| US2 | wizard 3 langkah menerbitkan `KSC/CB-00004` dan langsung muncul di daftar |
| US3 | tab *GR Belum Ditagih*: 4 PO · rincian barang (diterima vs belum ditagih) bisa dibuka |
| US4 | Verifikasi TANPA keputusan → **bilah merah terlihat** berisi kalimat penolakan; sesudah diputus berlabel → status *Terverifikasi* |
| US5 | modal potongan: 5 jenis · denda Rp 250.000 tersimpan · nilai bersih 5.661.000 → 5.411.000 |
| US6 | Ajukan → Verifikasi (manajer) → Setujui (admin); pembuat menyetujui sendiri → **"Pemisahan tugas…" terlihat di layar** |
| US7 | modal bayar: satu pembayaran melunasi kontrabon, notice menyebut `CASH-00017`, sisa Rp 0 |
| US8 | Rekonsiliasi Bank → baris dana keluar → *Bayar kontrabon* → kandidat "nominal tepat" → baris jadi **Tercocok · satu-satu** ke `CASH-00018` |
| US9 | bilah aksi dokumen: pratinjau Tanda Terima Kontrabon terbuka & memuat isi dokumen |
| US10 | panel *Referensi Dokumen* + *Jejak waktu* terisi pada panel detail |
| US11 | Gudang: melihat + keterangan hanya-pantau, tanpa tombol siklus/potongan, tanpa bilah error izin. Sales: tidak diberi jalan ke Hutang Supplier |

### 7.4b Tambahan pasca-penutupan — **POTONGAN OTOMATIS** (permintaan pemilik)
Wizard kontrabon kini **menawarkan** dokumen potongan yang tersedia di langkah 2
(`WizardCreditPicker.jsx`): nota debit retur beli & uang muka supplier dari
`GET /contra-bons/prepare`. Centang → nominal boleh diisi sebagian → ringkasan hidup
`nilai faktur − potongan = yang dibayar`. Urutan eksekusinya **sengaja**: terbitkan
kontrabon dulu (nomor + INV-CB-01), lalu tempelkan tiap potongan lewat endpoint
`POST /{id}/deductions` supaya penjaganya sendiri (INV-CB-04) tetap dijalankan backend;
"Ajukan langsung" ditunda sampai semua potongan menempel (kalau tidak, status sudah
berpindah dan potongan ditolak). Nilai bersih negatif → peringatan + tombol terkunci.
Langkah lanjutan yang DITOLAK dilaporkan di bilah error, kontrabon tetap terbit.
Data demo menambah **1 uang muka supplier** (kelebihan bayar jalur G-3) agar fitur ini bisa
dicoba. Bukti: uji layar **8 PASS / 0 FAIL** (termasuk penjaga nilai negatif).

### 7.5 Catatan untuk agen berikutnya
* Kontrabon **tidak** menambah koleksi potongan/jadwal: potongan inline di dokumen, jadwal
  tukar faktur adalah atribut `suppliers.invoice_exchange`. Lihat `ENTITY_REGISTRY.md`
  bagian `contra_bons` (termasuk daftar "JANGAN BUAT").
* Potongan `purchase_return` **tidak dijurnal ulang** — jurnalnya sudah lahir saat retur
  disetujui. Menjurnalnya lagi membuat Hutang berkurang dua kali.
* Data demo menyisakan **satu faktur bebas** supaya wizard bisa dicoba; jangan
  menghabiskannya di seed berikutnya tanpa mengganti.
* Anti-residu POC memakai **garis dasar**, bukan "harus nol dokumen": POC mencatat jumlah
  kontrabon + penghitung nomor + jadwal supplier sebelum jalan, lalu memulihkannya.
