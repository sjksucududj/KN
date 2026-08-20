# KN_34 — FASE G-9: PUSAT KASUS KEUANGAN (FINANCE EXCEPTION DESK)

> **Status: ✅ DITUTUP 2026-07-30.**
> 11/11 user story LULUS · POC `backend/test_g9_case_poc.py` **118 PASS / 0 FAIL** (nol residu) ·
> invarian **219** (INV-CASE-01..03, semua teruji bukti-merah) · `scripts/gate.sh --full`
> **39 gate HIJAU** · `testing_agent_v3` **iter_188** (backend 19/19 · frontend 100%) ·
> **3 bug NYATA ditutup** (1× P1, 2× P2) · **2 guardrail baru** (INV-UI-03 · i18n aturan [7]).
>
> Rencana asal: `plan.md` §BAGIAN A-G9. Spesifikasi awal: `plan.md` §G-9 (BAGIAN B).

---

## 1. Masalah nyata yang diselesaikan

Uang yang masuk/keluar **tidak selalu rapi**. Pelanggan salah transfer rekening, transfer ke
rekening pribadi karyawan, bayar dua kali, bayar invoice yang salah, nominal terpotong biaya
bank, giro ditolak, atau uang masuk tanpa identitas. Sebelum fase ini penyelesaiannya **hidup
di kepala orang keuangan dan chat WhatsApp**: tidak ada antrean, tidak ada SLA, tidak ada
bukti, dan kalau diselesaikan pun sering lewat **edit senyap** — persis yang dilarang
`plan.md` §G-10 aturan #1.

FASE G-8 menutup satu ujungnya (dana tak dikenal masuk **akun titipan 2-1950** berikut
jurnalnya), tetapi titipan itu **belum punya tempat untuk diselesaikan**. G-9 memberi tempat
itu: satu antrean bernomor, ber-SLA, ber-penanggung jawab, dan setiap penyelesaian
**melahirkan dokumen**, bukan mengubah dokumen lama.

---

## 2. Yang dibangun

### 2.1 Backend

| Berkas | Isi |
|---|---|
| `services/finance_case_playbooks.py` | Registry **11 playbook** (kesepakatan bisnis: jenis kasus + langkah + aksi + dokumen turunan + `needs_evidence` + **`reason_codes`**) |
| `services/finance_case_actions.py` | Eksekutor aksi → memanggil service yang SUDAH ADA (`bank_recon_service.allocate_holding`, `ar_receipt_service`, `store_credit_service`, `penalty_service`, `gl_service`, kas) — tidak ada mesin uang kedua |
| `services/finance_case_scan.py` | Pemindai otomatis (titipan menganggur · kwitansi kembar) + **eskalasi SLA** berjenjang (manager → admin, berhenti di level 2) |
| `services/finance_case_service.py` | Siklus `open → in_progress → resolved \| rejected`, SLA/prioritas dari nominal, penjaga alasan & bukti, `reopen` |
| `routers/finance_cases.py` | 13 endpoint: CRUD · `assign` · `note` · `resolve` · `reject` · `reopen` · `playbooks` · `reasons` · `policy` · `stats` · `scan` |
| `config_catalog_case.py` | **12 kunci** grup `kasus` di Pusat Pengaturan (SLA, ambang persetujuan, jendela duplikat, umur titipan, wajib-bukti, eskalasi, dsb) |
| `services/gl_service.py` | Akun baru **1-1280 Piutang Titipan Karyawan** |
| `scripts/verify_data_integrity.py` | Lapisan `case` → **INV-CASE-01..03** |
| `seed_realistic.py` | `seed_finance_cases()` — 3 kasus demo NYATA dari data demo (bukan mock) |

### 2.2 Frontend (`features/finance/cases/`)

`FinanceCasesView` (inbox · 5 kartu ringkasan · chip jenis · filter status/jenis/terlambat) ·
`CaseInboxTable` · `CaseDetailPanel` (sumber · playbook · bukti · **dokumen turunan** ·
relasi dokumen G-4 · jejak waktu · tindakan · **buka ulang**) · `CasePlaybookWizard`
(kartu aksi + "Yang lahir: …" + kolom masukan dinamis dari `action.needs`) ·
`CaseCreateModal` · `caseDeepLink.js` (deep-link global `kn-open-finance-case`).
Nav: **Keuangan → Pusat Kasus Keuangan** (`admin`, `manager`, `sales`).

### 2.3 11 playbook

| Jenis kasus | Penyelesaian | Dokumen turunan |
|---|---|---|
| `salah_rekening_internal` | pindah-buku antar rekening KN sendiri | 2 transaksi kas + 2 jurnal lewat 1-1150 Transit |
| `rekening_pribadi_karyawan` | akui uang dipegang karyawan → karyawan menyetor | jurnal 2 langkah: Dr 1-1280 / Cr 1-1200; lalu Dr Bank / Cr 1-1280 |
| `dana_tak_dikenal` | alokasi ke pelanggan/pesanan **atau** refund | Dr 2-1950 / Cr 1-1200 + pelunasan pesanan |
| `bayar_dobel` | refund **atau** jadikan uang muka pelanggan | kas keluar + jurnal · atau 2-1400 |
| `pembayar_pihak_ketiga` | tautkan ke pelanggan + bukti + persetujuan | Dr 2-1950 / Cr 1-1200 (wajib lampiran) |
| `salah_invoice` | **realokasi** antar pesanan (bukan void) | 2 baris alokasi (akun sama ⇒ tanpa jurnal baru) |
| `selisih_biaya_bank` | selisih ke Beban Adm Bank | Dr 6-8000 / Cr 1-1200 + pesanan lunas |
| `giro_ditolak` | batalkan kwitansi + denda opsional | kwitansi batal + jurnal pembalik (+ nota denda G-2) |
| `refund_pelanggan` | dari uang muka / store credit → kas keluar | kas keluar + jurnal (Dr 2-1400 / 2-1450) |
| `salah_entitas` | settlement antar entitas (dasar; netting = G-6) | 2 jurnal berpasangan (1-1250 / 2-1250) |
| `lebih_bayar_supplier` | uang muka supplier · refund · kontrabon (G-7) | Dr 1-1400 / Cr 2-1100 + `suppliers.advance_balance` |

---

## 3. Verifikasi 11 user story

| US | Bunyi | Bukti |
|---|---|---|
| **US1** | Finance membuka inbox & melihat antrean (jenis · nominal · umur · sisa SLA · penanggung jawab) | UI: `finance-cases-view` · 5 kartu (`case-stat-open/overdue/money/resolved`) · 3 chip · `case-table` + `case-row-<id>` · `case-filter-count`. API `GET /finance-cases` + `/stats` |
| **US2** | Menyelesaikan lewat **wizard playbook**, selalu melahirkan dokumen | `GET /playbooks` = 11. **Penyelesaian NYATA dari layar terbukti**: KSC/CASE-00001 → aksi *Alokasikan ke pelanggan/pesanan* → alokasi Rp 100.000 ke SO-0003 → status **Selesai** + *Dokumen turunan (2)*: `KSC/JE-00058` (Dr 2-1950 / Cr 1-1200) + `SO-0003` pelunasan |
| **US3** | Tidak bisa menutup tanpa **alasan berlabel** & **lampiran bukti** | tanpa `reason_code` → 400 "alasan" · aksi playbook lain → 400 "playbook" · tanpa bukti → 400 "bukti" · **alasan tak nyambung → 400 "nyambung"** (BARU) · UI `case-wizard-submit` DISABLED + `case-wizard-missing` menyebut yang kurang **termasuk "lampiran bukti"** (BARU) |
| **US4** | Sistem membuat kasus **sendiri** (titipan menganggur · bayar dobel) | `POST /scan` idempoten (dijalankan 2× tidak menggandakan) · kasus kembar untuk `source.id` sama → 400 "kembar" · UI `case-scan` |
| **US5** | Manager menyetujui penyelesaian di atas **ambang nominal** | `GET /policy` = SLA 24 jam · `approval_above` Rp 5.000.000 · `approver_role` manager · `refund_max` Rp 25.000.000. Role **sales** ditolak resolve. UI `case-approval-warning` terbukti muncul pada nominal Rp 999.000.000 |
| **US6** | Kasus melewati SLA **naik sendiri** + notifikasi | KSC/CASE-00001 TERLAMBAT (merah di tabel) · filter `case-filter-overdue` menyaring · `scan` menaikkan `escalation_level` 0→1→2 (berhenti di 2, tidak spam) · timeline "Melewati batas waktu → dinaikkan ke manager/admin" · notifikasi `critical` |
| **US7** | Auditor melihat rantai lengkap + jejak waktu | `GET /api/documents/trace/finance_case/{id}` → **200** · panel `case-detail-refs` (SO-0003 `settles`) & `case-detail-timeline` |
| **US8** | Dari layar **Titipan Dana (G-8)** tekan "Buka kasus" → terisi otomatis | **DIPERBAIKI sesi ini** — dulu klik = tidak terjadi apa pun. Sekarang: `recon-open-case-<line_id>` → berpindah sendiri ke `finance-cases-view` → `case-detail` terbuka pada KSC/CASE-00001 → `case-notice` gaya PERINGATAN "sudah punya kasus … jangan membuat kasus kembar" |
| **US9** | Admin mengubah SLA/ambang/jendela dari **Pusat Pengaturan** | `GET /api/config/registry` → grup `kasus` "Pusat Kasus Keuangan" **count 12 · active_count 12**; tampil di Pengaturan & Master Data → Pusat Pengaturan |
| **US10** | Auditor: `resolved` wajib dokumen + penyetuju + alasan; tidak ada titipan tua tanpa kasus; setiap perpindahan uang berjurnal seimbang | **INV-CASE-01/02/03** di `verify_data_integrity` (219 invarian) — ketiganya diuji **bukti-merah** di POC (disuntik pelanggaran → MEMERAH → dipulihkan → HIJAU) |
| **US11** | Kasus PT lain tidak pernah terlihat/terpakai (403) | POC: inbox PT-A tidak memuat kasus PT-B · `resolve`/`assign` lintas PT → 403 "entitas" · membuat kasus atas nama PT lain → 403 · admin `X-Entity-Id: all` tetap mengawasi |

---

## 4. Bug NYATA yang ditemukan & ditutup pada ronde penutupan

Ketiganya **lolos** dari ronde uji sebelumnya (iter_187 melaporkan "backend 23/23 · frontend
95%") karena ronde itu memeriksa **respons API**, bukan **apa yang terlihat di layar**.

### 4.1 `KN-G9-ERR-SILENT` — P1 · setiap penolakan backend HILANG dari layar

**Gejala.** Petugas menekan "Jalankan & selesaikan" / "Buka kasus" / "Buat kasus" → **tidak
terjadi apa pun**. Tidak ada pesan, tidak ada perubahan, tombol seperti mati.

**Akar.** `components/ErrorNotice.jsx` menerima prop **`message`** (string) dan
`return null` bila kosong. Dua layar keuangan terbaru menyimpan objek error axios lalu
mengirimnya lewat prop bernama **`error`**:

```jsx
{err && <ErrorNotice error={err} onDismiss={() => setErr(null)} />}   // ← props diabaikan
```

`message` undefined → komponen mengembalikan `null` → bilah error **tidak pernah dirender**.
Terdampak: `features/finance/cases/FinanceCasesView.jsx` (G-9) dan
`features/finance/BankReconciliationView.jsx` (G-8). 115 layar lain memakai `message=` dengan
benar, jadi ini murni salah nama prop pada 2 berkas terbaru.

**Lapisan kedua yang sama berbahayanya.** Wizard, modal "Kasus baru", dan modal-modal G-8
adalah **MODAL**. Bilah error milik layar induk berada di **BELAKANG** lapisan modal, jadi
sekadar memperbaiki nama prop pun belum cukup: pesan tetap tak terlihat selama modal terbuka.

**Perbaikan.**
1. `frontend/src/utils/apiError.js` (BARU) — `apiErrorText(e, fallback)` menormalkan error
   axios / `detail` string / `detail` daftar validasi 422 / `Error` / string, plus pesan per
   kode HTTP (401/403/404/409/…) dalam Bahasa Indonesia.
2. `ErrorNotice` menerima string **maupun** objek (dinormalkan lewat `apiErrorText`) —
   pertahanan berlapis. Ditambah prop opsional `onAction`/`actionLabel` untuk tombol lanjutan
   yang MENUNTUN.
3. 2 layar induk memakai `message={err}` + `onRetry` + `testId` (`case-error`, `recon-error`).
4. **6 modal** mendapat bilah error SENDIRI: `case-wizard-error` · `case-create-error` ·
   `case-detail-error` · `recon-allocate-error` · `recon-match-error` · `recon-group-error` ·
   `recon-format-error`.

**Penjaga (agar tidak kembali).** `scripts/guardrails/verify_error_notice.py` — **INV-UI-03**:
(A) setiap `<ErrorNotice>` wajib diberi `message`; (B) `ErrorNotice` wajib menormalkan lewat
`apiErrorText`; (C) modal yang memanggil `axios.post/put/patch/delete` wajib punya bilah error
sendiri. `--self-test` = bukti-merah (2 pelanggaran tertangkap · 2 pemakaian benar tidak
salah-tuduh). Masuk `gate.sh` blok STATIK. 12 modal LAMA dicatat di `MODAL_BASELINE` yang
**hanya boleh mengecil** (baseline basi = MERAH), jadi modal BARU wajib benar sejak hari pertama.

**Bukti di layar.** Alokasi Rp 999.000.000 pada titipan bersisa Rp 5.131.200 →
`case-wizard-error` tampil di dalam modal: *"Σ alokasi Rp 999.000.000 melebihi sisa titipan
Rp 5.131.200"*. Sebelum perbaikan: layar diam total.

### 4.2 `KN-G9-REASON-MISMATCH` — P2 · alasan penutupan tidak nyambung dengan jenis kasus

**Gejala.** Wizard menawarkan **seluruh 12 label alasan** untuk **semua 11 jenis kasus**,
sehingga kasus *"Dana masuk tak dikenal"* bisa ditutup dengan alasan *"Cek / giro ditolak
bank"*. **INV-CASE-01 tetap HIJAU** karena ia hanya memeriksa bahwa alasan ADA — bukan bahwa
alasannya nyambung. Jejak yang dibaca auditor justru menyesatkan.

**Perbaikan.** `reason_codes` per playbook (SSOT di `services/finance_case_playbooks.py`),
dibawa `GET /playbooks` dan bentuk kasus. `_reason_or_fail(code, case_type)` menolak yang
tidak nyambung dengan pesan yang MENUNTUN — menyebut label yang benar, bukan kode mentah:

> Alasan "Cek / giro ditolak bank" tidak nyambung dengan jenis kasus "Dana masuk tak dikenal".
> Alasan yang sah untuk jenis ini: "Pemilik dana ketemu", "Dana tak dikenal dikembalikan",
> "Dibayar pihak ketiga atas nama pelanggan".

Berlaku untuk `resolve` **dan** `reject`. UI menyaring `case-field-reason` dan
`case-reject-reason` ke daftar yang sah (terbukti di layar: 3 pilihan, bukan 12).
2 uji **bukti-merah** baru di POC (116 → **118 PASS**).

### 4.3 `KN-I18N-MONEY` — P2 · angka gaya Inggris pada pesan pengguna

**Gejala.** Sesudah 4.1 diperbaiki, pesan yang akhirnya terlihat memperlihatkan
*"Rp 999,000,000"* (koma, gaya Inggris) di antarmuka yang seluruhnya Bahasa Indonesia.

**Akar.** Pesan uang dibangun dengan tiga gaya berbeda di 30 berkas: `f"Rp {x:,.0f}"`
(Inggris), `f"Rp {x:,.0f}".replace(",", ".")`, dan **8 salinan** helper `_rp()` lokal.
Selama 4.1 masih hidup, format salah itu **tidak pernah kelihatan** — bilah errornya tidak
dirender sama sekali.

**Perbaikan.** `core_utils.rupiah()` sebagai satu sumber format uang; **91 pola** di 30
berkas dialihkan ke sana (codemod `scripts/_codemod_rupiah.py`, tercatat & dapat diaudit);
8 helper `_rp()` lokal dirampingkan jadi alias tipis ke `rupiah()`.

**Penjaga.** `scripts/audit_i18n_id.py` **aturan [7]**: pola mentah `Rp {expr:,}` = MERAH;
angka non-uang tidak ikut tertuduh; `--self-test` naik dari 12 → **16 skenario**.

---

## 5. Fitur yang dilengkapi (celah backend↔frontend)

`POST /finance-cases/{id}/reopen` sudah ada di backend sejak awal tetapi **tidak punya UI
sama sekali**. Ditambahkan `case-reopen-box` pada kasus yang sudah ditutup:

* ditutup **tanpa** dokumen turunan → boleh dibuka ulang, **alasan wajib** (terbukti:
  status `Ditutup tanpa tindakan` → `Sedang ditangani`);
* sudah **melahirkan** dokumen → tombol TERKUNCI + penjelasannya ditampilkan
  (`case-reopen-locked`: *"Terkunci: kasus ini sudah melahirkan 2 dokumen. Buku besar
  bersifat tambah-saja — tindak lanjutnya kasus baru."*) — **bukan disembunyikan**, supaya
  petugas tidak menyangka fiturnya tidak ada.

---

## 6. Invarian & gate

| Invarian | Arti | Bukti-merah |
|---|---|---|
| **INV-CASE-01** | Kasus `resolved` WAJIB punya dokumen turunan + penyetuju + alasan berlabel | dokumen dihapus → MEMERAH · label alasan dikosongkan → MEMERAH |
| **INV-CASE-02** | Tidak ada titipan dana > N hari **tanpa** kasus terbuka (uang tak boleh terlupakan) | titipan menganggur tanpa kasus → MEMERAH · pemindai membuat kasusnya → HIJAU |
| **INV-CASE-03** | Setiap kasus yang memindahkan uang punya **jurnal seimbang** | jurnal dibuat tidak seimbang → MEMERAH |
| **INV-UI-03** *(baru)* | Kegagalan backend tidak boleh hilang tanpa jejak di layar | 2 pelanggaran disuntik → tertangkap; 2 pemakaian benar → tidak salah-tuduh |
| **i18n aturan [7]** *(baru)* | Nominal yang dibaca pengguna wajib lewat `rupiah()` | 2 pola Inggris → tertangkap; `rupiah()` & angka non-uang → tidak salah-tuduh |

`bash scripts/gate.sh --full` → **39 gate HIJAU** (126s) · `verify_data_integrity`
**219 PASS / 0 FAIL / 0 WARN** · POC G-9 **118 PASS / 0 FAIL** dengan **nol residu**
(kasus demo tetap 3, saldo 1-1150/1-1280/2-1950/2-1400/1-1400 pulih EKSAK).

---

## 7. Pelajaran proses (untuk agen berikutnya)

1. **"Backend 100% hijau" BUKAN berarti fitur bisa dipakai.** Tiga bug fase ini semuanya
   berada di jalur **penyampaian ke manusia**, bukan di logika uang. Uji yang hanya membaca
   respons API akan melaporkan 100% sementara pengguna melihat layar yang diam.
   **Selalu uji: "kalau backend MENOLAK, apa yang dibaca pengguna?"**
2. **Bug bisa saling menyembunyikan.** Format uang gaya Inggris (4.3) tidak mungkin
   ditemukan sebelum 4.1 diperbaiki, karena pesannya tidak pernah dirender. Sesudah
   memperbaiki satu lapisan, **periksa ulang** lapisan yang tadinya tak terlihat.
3. **Invarian bisa HIJAU tapi hampa.** INV-CASE-01 memeriksa "ada alasan", bukan "alasan
   yang nyambung" (4.2). Saat menulis invarian, tanyakan: *apa bentuk data yang lolos
   pemeriksaan ini tetapi tetap salah bagi manusia?*
4. **Endpoint tanpa UI = fitur yang tidak ada.** `reopen` hidup di backend berbulan-bulan
   tanpa satu tombol pun. Saat menutup fase, bandingkan daftar `@router` dengan daftar
   `data-testid`.
5. **JANGAN memanggil `search_replace` PARALEL pada SATU berkas** (pelajaran FASE F yang
   masih berlaku) — edit saling menimpa dan yang terakhir menang.

---

## 8. Langkah berikutnya (`plan.md` §G-11)

`G-7 Kontrabon Advanced` (butuh G-1 + G-4; dirujuk playbook `lebih_bayar_supplier`) →
`G-6 Transaksi Antar Entitas` (dirujuk playbook `salah_entitas`; paling berdampak ke
konsolidasi) → `G-5 Unlock Periode` (kecil). Alternatif: **FASE H** (PS-17 divisi sebagai
aktor R&D — butuh keputusan pemilik D-13; PS-18 KPI designer + eskalasi SLA; PS-20 produk
eksklusif per sales).

**Utang teknis yang tercatat & terpantau gate:** `MODAL_BASELINE` di
`scripts/guardrails/verify_error_notice.py` — 12 modal lama belum punya bilah error sendiri
(daftar hanya boleh MENGECIL).
