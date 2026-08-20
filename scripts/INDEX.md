# 🛠️ INDEX ALAT / GUARDRAIL — Kain Nusantara

> Dibuat **2026-07-26** pada sesi *efisiensi guardrail*.
> Tujuan berkas ini: **setiap skrip harus bisa menjawab satu pertanyaan** —
> *“kalau pemeriksaan ini hilang, apakah UANG, DATA, KEAMANAN, atau ALUR PRODUK
> bisa rusak tanpa ada yang tahu?”* Kalau tidak bisa, skrip itu tidak layak jadi gate.

---

## 1. Perintah yang perlu diingat (hanya 3)

| Kebutuhan | Perintah | Waktu |
|---|---|---|
| Iterasi cepat (statik saja — tanpa DB/backend/seed) | `bash scripts/gate.sh --quick` | **~1 s** |
| Verifikasi penuh sebelum klaim selesai | `bash scripts/gate.sh` | **~16 s** |
| Verifikasi penuh + POC fase kunci (G-0, F-1, D) | `bash scripts/gate.sh --full` | ~60 s |

Hasil selalu ditulis ke `memory/GATE_RECEIPT.md`. **Klaim “selesai” tanpa receipt hijau = void.**

---

## 2. Anggaran waktu gate (terukur, bukan perkiraan)

| Gate | Waktu | Nilai | Kalau dihapus? |
|---|---:|---|---|
| `verify_data_integrity` (183 invarian) | 1 s | **TERTINGGI** | stok/GL/nomor dokumen bisa salah tanpa jejak |
| `seed_realistic` | 4 s | perlu | baseline invarian hilang |
| `guardrails/verify_auth_coverage` | 0 s | tinggi | endpoint tanpa auth lolos |
| `guardrails/verify_cross_entity` | 1 s | tinggi | IDOR lintas-PT (data PT lain terbaca) |
| `guardrails/verify_nonfinancial_sweep` | 1 s | tinggi | IDOR non-finansial |
| `guardrails/verify_concurrency` | 1 s | tinggi | race/TOCTOU jalur uang |
| `guardrails/verify_state_machine` | 1 s | tinggi | cancel tak melepas stok, task “hidup lagi” |
| `audit_endpoint_sweep` (338 GET, paralel) | 2 s | sedang | 5xx diam-diam di endpoint jarang dipakai |
| `health_check` | 2 s | sedang | endpoint kritis kosong tak terdeteksi |
| `gate_residue` (**INV-GATE-01**) | 1 s | tinggi | gate sendiri merusak data demo (pernah terjadi) |
| `validate_compliance` | 1 s | sedang | koleksi tak terdaftar, import mati, /api hilang |
| `check_nav_map` | 0 s | sedang | menu mati / role tak bisa akses landing |
| `guardrails/verify_numeric_bounds` | 0 s | sedang | qty/harga di luar batas |
| `guardrails/verify_modal_dismiss` | 0 s | rendah | modal tak menutup otomatis |
| `guardrails/verify_error_notice` (**INV-UI-03**) | 0 s | **tinggi** | penolakan backend HILANG dari layar (tombol terasa mati) — bug KN-G9-ERR-SILENT |

**Sebelum → sesudah sesi efisiensi:** total **34 s → 16 s**; `audit_endpoint_sweep`
**24.5 s → 2.4 s** (RSS 122 MB → 41 MB); warning `validate_compliance` **19 → 0**.

---

## 3. Apa yang diperbaiki 2026-07-26 (dan buktinya)

| # | Masalah | Bukti | Perbaikan |
|---|---|---|---|
| 1 | **Guardrail-nya sendiri bug** — `check_imports` memakai `imp_line.split(' as ')[-1]` tanpa membuang komentar, jadi alias = `"_dr  # Fase A · R7 …"` → selalu “unused” | 3 warning hantu di `admin.py`, `inbound_receiving.py`, `inventory.py`, padahal `_dr` dipakai 2× | Ganti ke **AST**. Hasil: hantu hilang, lalu ketemu **39 import mati NYATA** (divalidasi silang `ruff --select F401` = 39) → dibersihkan |
| 2 | **Check duplikat** — `check_monster_files()` = fotokopi `check_file_sizes()` (limit, glob, ambang sama) | 10 dari 19 warning adalah fakta yang sama dilaporkan 2× | `check_monster_files` **dihapus**; deteksi monster jadi tingkat FAIL di `_judge_size()` |
| 3 | **Batas panjang file mengunci desain** — `> limit` = FAIL keras; `PurchaseReturns.jsx` 498/500 ⇒ tambah 3 baris = gate MERAH | 6 warning “mendekati batas” + paksaan split artifisial | 2 tingkat: **WARN di limit, FAIL di limit × 2** |
| 4 | **Invarian nav memaksa palsukan RBAC** — “admin lihat semua” mutlak; `SESSION_HANDOFF §5` menyuruh *“longgarkan `roles` item yang sudah ada”* agar hijau | Menambah menu khusus 1 role selalu MERAH | Opt-out eksplisit **`adminExempt: true`** di `navStructure.js`; gate lulus **dan melaporkannya**. Bukti-merah: tanpa flag → MERAH, dengan flag → HIJAU |
| 5 | **`check_entity_registry_sync` tak pernah membaca `ENTITY_REGISTRY.md`** — pesannya bilang begitu, tapi datanya allowlist hardcode 79 entri ⇒ 2 sumber kebenaran, drift dijamin | 4 koleksi sudah dipakai kode tapi tetap dilaporkan merah | Kini **membaca `ENTITY_REGISTRY.md` langsung** (203 nama) + tokenize anti-komentar. Bukti-merah: koleksi palsu tetap terdeteksi |
| 6 | **Gate MERUSAK data demo tiap dijalankan** (nol `finally`/cleanup di 4 guardrail runtime) | Terukur dari seed bersih, 1× gate: `SO-0006` `reserved`→`cancelled` · 2 balance bergeser (songket reserved 20→10, lurik 40→0) · `inventory_movements` 38→40 · `audit_logs` 6→16 · `vendor_bills` +1 · `ar_receipts` +1 | **`DbSnapshot` + `run_with_restore`** di 6 gate runtime; dibuktikan **nol residu** pada 3 putaran (jumlah **dan** nilai) |
| 7 | **Tak ada yang menjaga penjaganya** | 183 invarian semuanya memeriksa konsistensi internal, tak satu pun bertanya “apakah gate merusak data?” | Gate baru **`INV-GATE-01`** (`scripts/gate_residue.py`). Langsung membuktikan diri: menemukan residu `vendor_bills`/`ar_receipts` yang belum ketemu manual |
| 8 | **Ledger mutasi stok tak terjaga** | Kebocoran no.6 lolos karena semua invarian stok memeriksa `inventory_balances` | Lapisan baru **`INV-MOV-01..04`** (179 → **183** invarian) |
| 9 | Gate selalu jalan penuh walau hanya mengedit dokumen | 34 s untuk perubahan 1 baris teks | Gate **bertingkat** `--quick` / default / `--full` |
| 10 | 151 skrip uji (62 ribu baris) tanpa daftar isi | agen baru tak tahu skrip mana relevan | **`tests/INDEX.md`** (dikelompokkan per fase) |

### Yang SENGAJA TIDAK dilakukan (kejujuran teknik)
- **Invarian `Σ inventory_movements == on_hand_qty` DIUJI dan DITOLAK.** Pada seed
  bersih **14 dari 22** pasangan (produk, gudang) tidak rekonsiliasi, bahkan ada
  balance dengan **nol** mutasi (`prod_ulos_batak/wh_jakarta` on_hand 95).
  Ledger mutasi di repo ini **ilustratif, bukan otoritatif**. Menambahkannya =
  gate palsu yang selalu merah. Karena itu dipasang invarian lain yang benar
  (`INV-MOV-01..04`) dan tetap menangkap kebocoran nyata.
- **Tidak memangkas gate keamanan/uang.** Berbeda dari repo lain yang gate-nya
  >20 menit, gate di sini 34 s — memangkas `verify_data_integrity` (1 s untuk 183
  invarian) akan membuang nilai, bukan menghemat.

---

## 4. Daftar skrip

### 4.1 Dipakai `gate.sh` (14 gate)

| Skrip | Baris | Invarian | Fungsi |
|---|---:|---|---|
| `gate.sh` | ~200 | — | Orkestrator; menulis `memory/GATE_RECEIPT.md`. Tingkat `--quick`/default/`--full` |
| `verify_data_integrity.py` | ~2.560 | 183 invarian | Rekonsiliasi koleksi, konservasi stok, GL balance, nomor seri, ledger mutasi, alert, lot, UoM, makloon, sourcing, receiving |
| `gate_residue.py` | ~170 | **INV-GATE-01** | Membuktikan gate tidak mengubah data (sidik jari sebelum/sesudah) |
| `validate_compliance.py` | ~700 | — | 14 check: ukuran file, console.log, endpoint duplikat, koleksi terlarang, sinkron ENTITY_REGISTRY, docs wajib, prefix `/api`, env, naming, tech-debt, import (AST) |
| `check_nav_map.py` | ~320 | — | Navigasi vs SSOT: integritas config, tab, matriks role (+`adminExempt`), kedalaman IA |
| `audit_endpoint_sweep.py` | ~185 | — | Semua 338 GET `/api` → cari 5xx (paralel ×12) |
| `health_check.py` | ~175 | — | Endpoint kritis berisi data |
| `guardrails/verify_auth_coverage.py` | ~250 | INV-AUTH-01 | Setiap endpoint punya penjaga auth. **2026-08-15:** mengenal `require_any_permission` + pencocokan batas kata (dulu menuduh palsu `GET /sales-return-policies/{id}`) + `--self-test` 8 kasus |
| `guardrails/verify_home_kpi.py` | ~265 | **INV-HOME-01** | **BARU 2026-08-15** — KPI beranda WAJIB = kenyataan. Menutup `KN-F3-KPI-LIES`: KPI "Persetujuan Menunggu" selalu 0 (menghitung `approval_requests` yang nol pemanggil) padahal 17 dokumen menunggu. 6 invarian: KPI==rincian · ==hitung-ulang mandiri dari MongoDB · anti "angka mati" · anti layar hantu · koleksi antrean harus ADA (kelas `amendments` vs `doc_amendments`) · antrean baru wajib punya opini kedua. `--self-test` bukti-merah |
| `audit_sales_roles_ux.py` | ~640 | — | **AUDIT PERAN** (6 peran + admin sebagai kontrol): menu yang TERLIHAT vs data yang BOLEH DIBACA. `layar mati` & (sejak 2026-08-15) `panel mati` = MERAH; `izin yatim` = indikasi. Pembebasan berkunci `(layar, path)` + alamat pagarnya; `--self-test` 9 kasus; `run_with_restore` (nol residu) |
| `guardrails/verify_cross_entity.py` | ~165 | INV-ENTITY-01 | IDOR lintas-PT (finansial) |
| `guardrails/verify_nonfinancial_sweep.py` | ~260 | INV-ENTITY-01+ | IDOR lintas-PT (non-finansial) |
| `guardrails/verify_concurrency.py` | ~175 | INV-CONC-01 | Race/TOCTOU pada jalur uang |
| `guardrails/verify_state_machine.py` | ~210 | INV-STATE-01 | Transisi SO/PO/WMS task |
| `guardrails/verify_numeric_bounds.py` | ~320 | INV-NUM-01 | Batas numerik qty/harga |
| `guardrails/verify_modal_dismiss.py` | ~100 | INV-UI-01 | Modal menutup otomatis setelah sukses |
| `guardrails/verify_blocking_dialogs.py` | ~250 | INV-UI-06 | `alert`/`confirm`/`prompt` bawaan peramban dilarang + `<ConfirmHost/>` wajib ter-mount (self-test 17 kasus, termasuk anti tuduh-palsu) |
| `guardrails/verify_error_notice.py` | ~180 | **INV-UI-03** | `<ErrorNotice>` wajib prop `message`; modal penulis API wajib punya bilah error sendiri |
| `guardrails/_common.py` | ~190 | — | `Guard`, **`DbSnapshot`**, **`run_with_restore`** |

### 4.2 Alat ad-hoc (TIDAK di gate — jalankan bila perlu)

| Skrip | Kapan dipakai |
|---|---|
| `audit_config_wiring.py` | Audit Pusat Pengaturan: setiap setting benar-benar dibaca kode & punya UI (OK/HIDDEN/ORPHAN_UI/DEAD) |
| `verify_contract.py` · `verify_api_contract.py` | Cek kontrak koleksi kanonik & bentuk API saat curiga ada drift |
| `ui_smoke.py` · `ux_audit.py` | Smoke UI & audit UX berbasis Playwright | **Sejak P5 `ux_audit.py` = GATE** (`--strict`) dan punya `--self-test` 16 kasus dua arah; aturan E1/E2 sadar-rujukan (menelusuri komponen anak) supaya tidak menuduh komponen penampil.
| `audit_collection_drift.py` · `find_dead_services.py` | Cari koleksi/service yatim |
| `poc_hrd.py` · `poc_hrd_h1.py` · `poc_document_platform.py` · `poc_sales_revamp.py` | POC modul (arsip bukti fase) |
| `seed_ar_due_soon_demo.py` · `seed_escalation_demo.py` | Menyiapkan kondisi berbasis waktu agar fitur terlihat di UI tanpa menunggu |
| `seed_reset.sh` · `reset_db.sh` · `rebuild_frontend.sh` · `dev_setup.sh` · `load_context.sh` · `run_forensics.sh` | Operasional harian |
| `_codemod_rupiah.py` | **Sekali-pakai (arsip bukti FASE G-9)** — menyeragamkan 91 pola format uang gaya Inggris `Rp {x:,}` → `core_utils.rupiah()` di 30 berkas. Punya `--dry-run`. Penjaga permanennya: `audit_i18n_id.py` aturan [7] |
| `entity_audit/` (5 skrip + README) | **Audit isolasi multi-entitas (sesi verifikasi 2026-08-10)** — `audit_entity_isolation.py` menyapu ±300 endpoint GET × 4 identitas (sales 2 entitas + admin) dan melaporkan kebocoran lintas-entitas, endpoint "sama antar-PT", IDOR per dokumen, serta sebaran `entity_id` di seluruh koleksi. `verify_leaks*.py` = bukti baris-demi-baris + endpoint agregat. `probe_entity_flow*.py` = siklus hidup entitas & cacat pengelolaan akun (**menulis data uji**). Rencana: `audit_entity_isolation.py` dipromosikan jadi gate (lihat `plan.md` E0.9) |

### 4.3 `_legacy/` — diarsipkan 2026-07-26 (nol rujukan di seluruh repo)

Bukan dihapus: dipindahkan agar tidak muncul di pencarian & tidak menyesatkan agen baru.

| Skrip | Baris | Alasan |
|---|---:|---|
| `poc_traceability.py` | 196 | POC fase lama, sudah digantikan invarian lot Fase C |
| `poc_wa_esign_pdf.py` | 151 | POC platform dokumen, sudah live |
| `poc_document_gaps.py` | 138 | audit celah dokumen, sudah ditutup |
| `seed_r5_4b_scenarios.py` | 104 | seed skenario R5.4b (fase selesai) |
| `seed_r5_5_scenario.py` | 97 | seed skenario R5.5 (fase selesai) |
| `poc_wa_autosend.py` | 91 | POC auto-kirim WA, sudah live |
| `patch_overlay_dismiss.py` | 60 | patcher sekali-pakai |
| `audit_create_buttons.py` | 55 | audit sekali-pakai |
| `audit_create_buttons2.py` | 52 | duplikat iterasi kedua dari di atas |
| `fe_syntax_check.js` | 18 | digantikan `yarn build` + oxlint platform |

**Total diarsipkan: 10 berkas / 962 baris.**

---

## 5. Aturan menulis guardrail baru (supaya tidak jadi beban)

1. **Jawab pertanyaan uang/data/keamanan/alur.** Kalau tidak, jadikan alat ad-hoc — bukan gate.
2. **Jangan grep teks mentah** untuk menilai kode. Pakai **AST** (Python) — komentar & docstring
   BUKAN kode. Dua bug guardrail di repo ini lahir dari pelanggaran aturan ini.
3. **Satu fakta = satu laporan.** Jangan dua check melaporkan hal yang sama.
4. **Gate runtime WAJIB memulihkan data**: `run_with_restore(main)` dari `_common.py`.
   `INV-GATE-01` akan memerahkan gate bila lupa.
5. **Satu sumber kebenaran.** Jangan menyalin daftar dari dokumen ke dalam skrip — **baca dokumennya**.
6. **Sertakan bukti-merah.** Buktikan gate MEMERAH saat pelanggaran disuntik, lalu HIJAU setelah dipulihkan.
   Gate yang belum pernah merah belum terbukti hidup (contoh nyata: helper `_py_code_only` versi
   pertama membuat deteksi selalu lulus — hanya ketemu karena diuji-negatif).
7. **Batas gaya (panjang file, naming) = WARN**, bukan FAIL. FAIL hanya untuk kerusakan nyata.

---

**Terakhir diperbarui:** 2026-07-26 · **Receipt terakhir:** `memory/GATE_RECEIPT.md`
