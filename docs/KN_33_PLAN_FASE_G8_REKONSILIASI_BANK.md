# KN_33 — PENUTUPAN FASE G-8: REKONSILIASI BANK OTOMATIS

> **Status: DITUTUP 2026-07-29** (repo `hahabannamaka/KN`).
> Spesifikasi asal: `plan.md` §G-8 (BAGIAN B) + rencana kerja `plan.md` §BAGIAN A-G8.
> Bukti: POC `backend/test_g8_bank_poc.py` **122 PASS / 0 FAIL** ·
> `verify_data_integrity` **216 PASS / 0 FAIL / 0 WARN** (INV-BNK-01..05) ·
> `gate.sh --full` **37 gate HIJAU** · `testing_agent_v3` **iter_186** (BE 100% · FE 100%).

---

## 1. Masalah nyata yang diselesaikan

Sebelum fase ini rekonsiliasi bank praktis **tidak dipakai**:

| Kondisi lama | Akibat di lapangan |
|---|---|
| Impor hanya menerima CSV 4 kolom baku yang **harus diketik ulang manusia** | finance memilih mencocokkan dengan mata di Excel |
| Skor pencocokan hanya 2 faktor (`refhit`, `-daydiff`) **tanpa penjelasan** | angka muncul tanpa alasan → tidak dipercaya |
| `bank_statement_lines` **tidak terdaftar** di `entity_scope.SCOPED_COLLECTIONS` | user PT-A cukup mengirim `bank_account_id` PT-B lalu membaca mutasinya (**kebocoran nyata**) |
| Dana masuk tak dikenal **menggantung tanpa jurnal** | uang tidak terlihat di laporan mana pun |

## 2. Yang dibangun

| Lapisan | Hasil |
|---|---|
| Koleksi baru | `bank_statement_formats` (`bsf_`) · `bank_match_rules` (`bmr_`) — keduanya SCOPED & tercatat di `ENTITY_REGISTRY.md` |
| Koleksi diperluas | `bank_statement_lines` + `score`, `score_explain[]`, `suggestions[]`, `match_kind`, `allocations[]`, `holding_*` — **dan kini SCOPED** |
| Parser | `services/bank_statement_parser.py` — CSV/TSV (1 kolom nominal + penanda DB/CR **atau** 2 kolom Debet/Kredit), tanggal multi-format (termasuk `dd/mm` tanpa tahun), desimal gaya Indonesia & Inggris, **MT940** (`:61:`/`:86:`) & **OFX** (`<STMTTRN>`), **7 preset bawaan**, `detect_format()` |
| Pencocokan | `score_pair()` berbobot **40 nominal · 20 tanggal · 25 referensi · 15 nama** + `explain[]` kalimat manusia · `auto_match` **3 pita** (≥80 otomatis · 60–79 usulan · <60 manual) · `match_split` (1:N) · `match_group` (N:1) · `learn_from_manual()` |
| Titipan dana | akun GL **2-1950 Titipan Dana Belum Teridentifikasi** · `to_holding()` (Dr Bank / Cr 2-1950) · `allocate_holding()` (Dr 2-1950 / Cr 1-1200, **tanpa kas dobel** — pola `apply_from_deposit` G-3) · `holding_max_age_days` → penanda *perlu tindakan* |
| Biaya & bunga bank | `book-charge` → Dr Beban Adm Bank / Cr Bank (atau sebaliknya untuk jasa giro), **INV-BNK-04** |
| Konfigurasi | `config_catalog_bank.py` + grup registry `bank` — semua bobot, ambang, jendela hari, toleransi, `rule_learn_after`, `rule_bonus_score`, `holding_account_code`, `holding_max_age_days` diubah dari **Pusat Pengaturan tanpa deploy** |
| Invarian | **INV-BNK-01..05** di `scripts/verify_data_integrity.py` (lapisan `bank`) |
| Frontend | `BankReconciliationView.jsx` + `bank/{ReconImportPanel, ReconLinesTable, ReconMatchModal, ReconHoldingPanel, ReconRulesPanel, ReconFormatsPanel}` — 4 tab, 6 kartu ringkasan, filter status + rentang tanggal (ringkasan ikut periode), pratinjau impor, skor + penjelasan, usulan 1-klik, modal split, pengelola template |
| Data demo | `seed_realistic.py` → 5 baris mutasi di *BCA Operasional KSC* (1 siap cocok otomatis · 1 usulan · 1 manual · 1 dana tak dikenal · 1 biaya bank) + 7 template parser |

## 3. Invarian (INV-BNK)

| Kode | Yang dijaga |
|---|---|
| **INV-BNK-01** | setiap baris berstatus sah (`unmatched\|matched\|ignored\|holding`) & tautannya utuh |
| **INV-BNK-02** | Σ yang direkonsiliasi pada transaksi buku == Σ alokasi yang menunjuknya |
| **INV-BNK-03** | saldo akun titipan di **buku besar** == Σ titipan yang belum dialokasikan |
| **INV-BNK-04** | baris biaya admin / bunga bank yang dibukukan punya jurnalnya |
| **INV-BNK-05** | **titipan tidak pernah melintasi PT** — alokasi selalu menunjuk pesanan entitas yang sama |

Keempat-limanya **terbukti bisa MEMERAH**: POC menyuntik pelanggaran (menghapus tautan,
menggeser Σ rekonsiliasi, menghapus jurnal titipan) lalu memulihkannya kembali.

## 4. Bug NYATA yang ditemukan saat ronde penutupan

### KN-G8-DIR-SILENT (P1, uang) — **arah dana ditebak "masuk"**

Ditemukan **lewat layar**, bukan teori: menempel ekspor rekening koran BCA apa adanya
(tanpa tanda kutip) di panel Impor. Baris `BIAYA ADM UJI … 25.000,00 DB` muncul di
pratinjau sebagai **"Masuk"**, dan ringkasan menulis *"masuk Rp 1.275.000 · keluar Rp 0"*.

Akarnya dua celah bertumpuk:

1. `parse_csv` menutup rantai arah dana dengan `direction = "out" if neg else "in"` —
   penanda tak terbaca ⇒ **uang diasumsikan MASUK**. Pemicunya nyata: **koma desimal
   Indonesia adalah pemisah CSV**, jadi `25.000,00 DB` pecah jadi dua field dan kolom
   penanda bergeser.
2. `_dir_from_marker` hanya menerima penanda yang sama persis / di **awal** sel, sehingga
   penanda yang MENEMPEL pada nominal (`"12.500.000,00 CR"` — bentuk ekspor KlikBCA yang
   umum) tak pernah terbaca. Bonus: `startswith` polos membaca **`"KREDITUR"`** sebagai
   `kredit` = uang masuk.

**Dampak uang:** `statement.net` & kartu *"Selisih rekening vs buku"* salah; lebih
berbahaya, baris biaya jadi **kandidat pencocokan ke kwitansi piutang** — pendapatan yang
tidak pernah ada.

**Kenapa lolos gate:** POC lama menguji parser hanya dengan CSV **ber-tanda-kutip** yang
selalu punya kolom `DB/CR` utuh. Bentuk ekspor nyata tidak pernah diuji ⇒ hijau tapi hampa.

**Perbaikan:** arah dana **tidak pernah ditebak**. Rantai baru: kolom penanda → penanda
yang menempel pada kolom nominal → nominal bertanda minus → **kalau tetap tak pasti,
baris DITOLAK** dengan alasan yang menuntun (*"periksa kolom penanda DB/CR pada template,
atau bungkus nominal dengan tanda kutip bila koma desimal membuat kolom bergeser."*).
`_dir_from_marker` memakai **batas kata** dan mengembalikan kosong bila satu sel memuat
penanda masuk DAN keluar (ambigu). Registry: `memory/BUG_REGISTRY.md`.

**Gate baru (bukti-merah, 4 assertion):** penanda menempel terbaca `out` · `sum_out` tidak
lagi Rp 0 · baris tak pasti DITOLAK berikut arahan · `KREDITUR` bukan penanda & `DB/CR`
ambigu tidak ditebak. POC **118 → 122 PASS**.

### Bug lain yang sudah ditutup di dalam fase (tercatat di POC sebagai bukti-merah)

| Kode | Inti |
|---|---|
| `KN-G8-MATCH-PARTIAL` | mutasi Rp 3.000.000 ke transaksi buku bersisa Rp 1.000.000 dulu diam-diam dipotong jadi "tercocok" palsu → kini **400** + arahan |
| `KN-G8-FORMAT-DUP` | preset bawaan dipasang per-entitas ⇒ admin 2 PT melihatnya **dobel** → preset milik entitas GRUP (`all`) |
| kebocoran scoping | `bank_statement_lines` tidak SCOPED ⇒ PT-A bisa membaca mutasi PT-B → **403 karena entitas** (11 assertion) |

## 5. 11 user story — hasil verifikasi

| # | User story | Bukti |
|---|---|---|
| 1 | Finance menempel/mengunggah mutasi bank apa pun + **pratinjau sebelum impor** | POC §1 (BCA · Mandiri · MT940 · OFX) + layar: pratinjau membaca `1.250.000,00` & mendeteksi template otomatis |
| 2 | Finance membuat/menyunting template sendiri | POC §1 (template kustom: tanpa header, indeks kolom, desimal Inggris) + tab **Template Bank** (7 template, tombol *Template baru*, *Buka*) |
| 3 | "Cocokkan otomatis" 3 pita + **penjelasan skor** | Layar: skor **85 → Tercocok otomatis**, skor **65 → usulan** *"Terima usulan: CASH-00014"*, penjelasan *"Nominal sama (+40) · Tanggal beda 2 hari (+10) · nama mirip (90%) (+15)"* |
| 4 | 1:N & N:1, Σ alokasi tidak melebihi nominal | POC §5 (400 saat Σ ≠ nominal & saat sisa transaksi tak menutup nominal) + modal **Pecah ke beberapa transaksi** ("Sisa belum dialokasikan: Rp 6.230.000") |
| 5 | Pola sama 3× → sistem **menawarkan** aturan | POC §4 + tab **Aturan Pembelajaran** ("Sistem tidak pernah mengaktifkan aturan sendiri") |
| 6 | Dana tak dikenal → **Titipan Dana** + jurnal | POC §3 (Dr Bank / Cr 2-1950) + tab **Dana Titipan** |
| 7 | Alokasi titipan → piutang berkurang, **tanpa kas dobel** | POC §3 (Dr 2-1950 / Cr 1-1200) + modal alokasi (pelanggan → pesanan → nominal) |
| 8 | Manager melihat ringkasan + **umur titipan** | 6 kartu ringkasan; *"Titipan yang menganggur lebih dari 7 hari ditandai perlu tindakan"* |
| 9 | Admin mengubah bobot & ambang tanpa deploy | POC §2 ("ambang dibaca dari Pusat Pengaturan, bukan angka sihir di kode") |
| 10 | Auditor: status jelas + INV-BNK memerah saat dilanggar | POC §7 (INV-BNK-01/02/03 MEMERAH lalu HIJAU lagi) |
| 11 | Mutasi bank PT lain tidak pernah terlihat/terpakai | POC §6 (11 assertion 403 **karena entitas**, dua arah, + kontrol "tidak over-block" & admin `X-Entity-Id: all` tetap mengawasi) |

## 6. Nol residu

POC memakai `backend/poc_stock_guard.py` + pembersihan eksplisit: data mutasi demo kembali
ke keadaan semula (5 baris), artefak POC terhapus, **saldo akun titipan & Beban Administrasi
Bank kembali Rp 0**, dan `verify_data_integrity` **216/0/0** sesudah pembersihan.
Gate `INV-GATE-01 anti-residu FASE POC` menjaga ini setiap kali gate dijalankan.

## 7. Cara uji cepat

```bash
cd /app
python seed_realistic.py                     # data demo (idempoten)
python backend/test_g8_bank_poc.py           # harus 122 PASS / 0 FAIL
python scripts/verify_data_integrity.py --only bank   # lapisan bank saja (cepat)
bash scripts/gate.sh --full                  # 37 gate HIJAU
```

UI: **Keuangan → Kas & Bank → Rekonsiliasi Bank** (admin/manager, izin `cash`).

## 8. Titik lanjut

**FASE G-9 — Pusat Kasus Keuangan (Finance Exception Desk)** (`plan.md` §G-9, urutan §G-11
#6). Dependensinya sudah lengkap: G-1 (amandemen ber-alasan) + G-8 (titipan dana sebagai
antrean kasus).
