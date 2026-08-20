# 🐞 BUG REGISTRY — Lacak Bug & Cegah Berulang (Kain Nusantara)

> **Tujuan:** setiap bug dicatat, dipetakan ke invariant (`memory/INVARIANTS.md`), dan dipastikan
> ada **gate** yang menangkapnya agar **tidak terulang**.
>
> **Aturan emas:** kalau sebuah bug LOLOS dari semua gate → itu artinya **gate kurang**.
> Wajib **perkuat gate** (tambah invarian/cek), bukan sekadar tambal kode.
>
> Format registry & disiplin ini diadaptasi dari `memory/BUG_REGISTRY.md` proyek Rahaza Travel.

## FORMAT ENTRI
```
### <ID> — <judul singkat>
- Tanggal      : YYYY-MM-DD (sesi)
- Modul         : <router/service>
- Gejala        : <apa yang terlihat>
- Invariant     : INV-...  (memory/INVARIANTS.md)
- Gate penangkap: <script gate yang menangkap>
- Severity      : P0 | P1 | P2
- Status        : OPEN | IN_PROGRESS | FIXED (bukti: <receipt/test>) | FALSE_POSITIVE
```

---

## REGISTRY — Penutupan FASE G-6 (2026-07-30 · repo `ghananamakaa/kn`)

### KN-G6-DOUBLE-POST — satu barang antar-PT bisa tercatat DUA KALI di buku
- Tanggal       : 2026-07-30 (sesi penutupan G-6)
- Modul         : routers/transfers.py · services/interco_service.py · services/gl_service.py
- Gejala        : G-6 memposting jurnal berharga jual saat transaksi dikonfirmasi, sementara
                  transfer gudang antar-PT (`transfer_kind=inter_entity`) tetap memposting
                  jurnal at-cost M-3 saat disetujui. Bila satu barang lewat KEDUANYA (jalur
                  yang justru diminta US8), IC-AR/IC-AP dan persediaan naik dua kali —
                  piutang antar-PT menggelembung tanpa ada dokumen yang salah satu pun.
- Akar masalah  : tidak ada penanda hubungan antara dokumen dagang (G-6) dan perpindahan
                  fisik (gudang), jadi lapisan gudang tidak tahu jurnalnya sudah ada.
- Perbaikan     : `warehouse_transfers.interco_pair_id` + endpoint
                  `POST /api/interco/transactions/{id}/warehouse-task`. Saat approve:
                  at-cost M-3 DILEWATI (`je_intercompany.posted=false` + `skipped_reason`),
                  roll pembeli dinilai ulang ke harga beli internal, status pair maju ke
                  `received`, dan HPP + penerimaan diposting mengikuti barang.
- Invariant     : INV-IC-06 (baru) · INV-IC-01
- Gate penangkap: scripts/verify_data_integrity.py lapisan `interco` · POC test_US8b
- Severity      : P1
- Status        : FIXED (bukti: POC 21/0 · integritas 229/0/0 · gate --full HIJAU)

### KN-G6-GL-TIMING — persediaan pembeli naik sebelum barangnya ada (drift GL↔subledger)
- Tanggal       : 2026-07-30
- Modul         : services/interco_service.py (`_post_gl_for_pair`) · services/gl_service.py
- Gejala        : WARN `INV-GL-DRIFT` muncul setiap ada transaksi antar-PT: GL `1-1300`
                  pembeli naik (harga jual) & penjual turun (WAC) saat dokumen dikonfirmasi,
                  padahal roll belum berpindah. Δ terukur: ent_kanda −150,7 juta.
- Perbaikan     : akun baru **1-1310 Persediaan Dalam Perjalanan (Antar-PT)**. Konfirmasi =
                  dokumen & utang (`Dr 1-1310`); perpindahan barang = `Dr 5-1000/Cr 1-1300`
                  (biaya NYATA roll yang keluar, bukan WAC×qty) + `Dr 1-1300/Cr 1-1310`.
- Invariant     : INV-GL-DRIFT · INV-IC-01 · INV-IC-06
- Gate penangkap: verify_data_integrity (WARN → 0) · POC test_US8b (GL == subledger)
- Severity      : P1
- Status        : FIXED (bukti: 228 PASS/1 WARN → **229 PASS / 0 WARN**)

### KN-G6-JOURNAL-404 — blok jurnal di Detail Panel SELALU kosong (galat ditelan)
- Tanggal       : 2026-07-30
- Modul         : frontend/src/features/finance/interco/IntercoDetailPanel.jsx
- Gejala        : panel detail memanggil `GET /api/gl/entries` (endpoint TIDAK ADA → 404) di
                  dalam `try/catch` kosong, sehingga blok "Jurnal Buku Penjual/Pembeli" tidak
                  pernah muncul dan tidak ada pesan galat apa pun. Fitur terlihat "belum jadi".
- Perbaikan     : endpoint `GET /api/interco/transactions/{id}/journal` (jurnal 2 buku, HPP,
                  penerimaan, pembalikan, settlement, eliminasi, tugas gudang) + panel
                  menampilkan bilah galat bila pengambilan bukti gagal (INV-UI-03).
- Invariant     : INV-UI-03 (error tak boleh senyap)
- Gate penangkap: POC test_US8c (endpoint) · uji layar Playwright
- Severity      : P1
- Status        : FIXED

### KN-G6-ELIM-NO-UI — eliminasi margin tak bisa dijalankan user + entri jadi basi
- Tanggal       : 2026-07-30
- Modul         : services/consolidation_service.py · features/finance/GroupConsolidationView.jsx
- Gejala        : (a) `POST /api/consolidation/sync-g6` tidak punya pemicu di layar mana pun;
                  (b) sinkronisasi bersifat "sudah ada → lewati", jadi entri yang dibuat saat
                  konfirmasi tetap menghapus IC-AR/IC-AP **sesudah** transaksinya dilunasi
                  (menghapus saldo yang sudah tidak ada).
- Perbaikan     : eliminasi disinkronkan OTOMATIS (confirm · terima · lunas · batal) dengan
                  create/update/remove; tombol **Sinkron Antar-PT (G-6)** + **Sinkron Pasangan
                  Jurnal (M-3)** + badge AUTO G-6 (entri auto tidak bisa dihapus manual).
- Invariant     : INV-IC-03 (baru)
- Gate penangkap: POC test_US7 & test_US7b · lapisan `interco`
- Severity      : P1
- Status        : FIXED

### KN-G6-CANCEL-NO-REVERSAL — pembatalan menyisakan pendapatan & piutang di buku
- Tanggal       : 2026-07-30
- Modul         : services/interco_service.py (`cancel`)
- Gejala        : `cancel` hanya mengganti status; jurnal yang sudah terbit saat konfirmasi
                  tetap tinggal (pendapatan + IC-AR/IC-AP), dan entri eliminasinya menggantung.
- Perbaikan     : wajib alasan ≥5 huruf (pola G-1) → jurnal pembalik `{pair}:{sisi}:reversal`
                  di kedua buku, tugas gudang menunggu ikut batal (roll dilepas), eliminasi
                  dihapus, saldo pasangan PT dihitung ulang. Modal alasan di layar.
- Invariant     : INV-IC-01 (dampak bersih pair yang dibatalkan WAJIB nol)
- Gate penangkap: POC test_US9b · lapisan `interco`
- Severity      : P1
- Status        : FIXED

### KN-G6-LOT-CROSS-OWNER — lot berisi roll milik dua PT setelah kepemilikan pindah
- Tanggal       : 2026-07-30
- Modul         : services/roll_service.py (`execute_ownership_transfer`)
- Gejala        : `INV-LOT-05` MEMERAH ("1 lot bercampur produk/pemilik") begitu ada
                  perpindahan kepemilikan antar-PT: roll berganti `owner_entity_id` tetapi
                  `lot_id`-nya tetap lot milik PT penjual. Cacat ini SUDAH ada di jalur POS
                  lama, hanya tak pernah terlihat karena data demo tak pernah memindahkannya.
- Perbaikan     : roll yang berpindah di-rumah-kan ke lot milik PT tujuan (idempoten per
                  transfer × produk × dye lot) dengan **genealogi** menunjuk lot asal; agregat
                  kedua lot dihitung ulang.
- Invariant     : INV-LOT-05 · INV-LOT-03 (genealogi)
- Gate penangkap: verify_data_integrity lapisan `lot`
- Severity      : P1
- Status        : FIXED

### KN-G6-NO-INVARIANT / KN-G6-DEMO-EMPTY / KN-G6-SCOPE-ICA — fase "selesai" tanpa penjaga & tanpa data
- Tanggal       : 2026-07-30
- Modul         : scripts/verify_data_integrity.py · scripts/gate.sh · seed_realistic.py ·
                  services/interco_service.py (`_update_account_balance`)
- Gejala        : (a) INV-IC-01..05 yang dijanjikan rencana KN_36 §3.4 belum ada di gate dan
                  POC G-6 belum terdaftar di `gate.sh --full`; (b) layar Antar Entitas KOSONG
                  setelah `seed_realistic.py`; (c) `interco_accounts` tidak punya `entity_id`
                  → gate F0-C `verify_entity_scoping` MEMERAH (`missing=2`).
- Perbaikan     : lapisan `interco` INV-IC-01..06 + POC terdaftar di gate (dan POC dijadikan
                  bukti-merah + nol residu lewat `poc_stock_guard`); `seed_interco()` lewat
                  jalur produksi (ASGI in-process); `entity_id` ditulis di kedua sisi saldo.
- Invariant     : INV-IC-01..06 · F0-C scoping
- Gate penangkap: gate.sh --full (POC G-6 + verify_entity_scoping)
- Severity      : P2
- Status        : FIXED

### KN-G6-I18N-GATE — gate bahasa MERAH sejak fase sebelumnya (8 temuan)
- Tanggal       : 2026-07-30
- Modul         : services/interco_service.py · IntercoCreateModal.jsx ·
                  InternalContractWizardModal.jsx · GroupConsolidationView.jsx
- Gejala        : `audit_i18n_id` melaporkan 8 temuan: 4 pesan uang gaya Inggris
                  (`Rp 100,000,000`) di pesan penolakan interco, dan istilah teknis yang
                  dipamerkan ke pengguna (`fixed_price`, `Invoice`, `Vendor Bill`, `at-cost`).
                  3 di antaranya WARISAN sesi sebelumnya → gate memang sudah merah.
- Perbaikan     : pakai helper `rupiah()` dari `core_utils`; label layar diterjemahkan
                  ("Harga tetap", "Faktur internal", "Tagihan internal", "nilai perolehan").
- Invariant     : aturan [7] audit_i18n_id
- Gate penangkap: scripts/audit_i18n_id.py (0 temuan setelah perbaikan)
- Severity      : P2
- Status        : FIXED

### KN-FA-UNDEF-BIAYA — validasi "Nilai residu" di Tambah Aset Tetap melempar ReferenceError
- Tanggal       : 2026-07-30 (ditemukan lint pra-penyelesaian sesi G-6)
- Modul         : frontend/src/features/finance/FixedAssetsParts.jsx
- Gejala        : `if (salvage < 0 || salvage >= biaya)` — `biaya` **tidak pernah
                  didefinisikan** (variabelnya bernama `cost`). Begitu pengguna mengisi
                  **Nilai residu**, `submit()` melempar `ReferenceError` → dialog "Tambah Aset
                  Tetap" terasa MATI (tidak tersimpan, tanpa pesan galat).
- Akar masalah  : sisa codemod bahasa (`cost` → `biaya`) yang menyentuh IDENTIFIER kode, bukan
                  hanya teks pengguna. Warisan sesi sebelumnya, bukan dari FASE G-6.
- Perbaikan     : kembalikan ke `salvage >= cost`.
- Gate penangkap: `npx oxlint src` (no-undef) — sekarang **0 errors**; guardrail
                  `fix_i18n_id SELF-TEST` sudah menjaga agar codemod tak menyentuh kode lagi.
- Severity      : P1 (fitur pengguna mati senyap)
- Status        : FIXED (bukti: oxlint 0 errors · build frontend OK)

### KN-G6-SYNC-AUTH — (FALSE POSITIVE) "sync-g6 tanpa auth mengembalikan 200"
- Tanggal       : 2026-07-30 (temuan testing agent iter_191)
- Modul         : routers/consolidation.py · dependencies.py
- Gejala klaim  : endpoint dianggap tanpa penjaga karena 200 walau header `Authorization` dibuang.
- Fakta         : tanpa kredensial APA PUN → **401 "Login diperlukan"**. Klien yang sudah login
                  membawa cookie `session_token` (HttpOnly) dan `require_permission` membaca
                  cookie itu lebih dulu (desain SEC-2) — itu sebabnya tetap 200.
- Status        : FALSE_POSITIVE (dikonfirmasi ulang oleh testing agent iter_192)

---

## REGISTRY — Penutupan FASE G-7 (2026-07-30 · repo `hakakanabava/kn`)

### KN-G7-POC-DRIFT — POC mati sesudah data demo di-seed ulang
- Tanggal      : 2026-07-30 (sesi lanjutan G-7)
- Modul        : `backend/test_g7_contrabon_poc.py`
- Gejala       : POC G-7 memaku **id supplier** (`sup_c3dd8f4879ea`, …) dan **nomor PO**
                 (`KSC/PO-00007`). `seed_realistic.py` membuat id supplier baru setiap
                 jalan dan nomor PO per-PT bergeser bila jumlah PO per PT berubah →
                 POC berhenti di langkah pertama (`400 Supplier tidak ditemukan`,
                 lalu `KeyError: 'id'`). **Inilah titik henti sesi sebelumnya**: 16 PASS /
                 16 FAIL padahal backend G-7 sehat.
- Invariant    : — (disiplin uji: fixture harus tahan-kondisi)
- Gate penangkap: `gate.sh --full` → gate baru "POC FASE G-7"
- Severity     : P2 (uji, bukan produk — tetapi memblokir seluruh fase)
- Status       : FIXED — `resolve_actors()` mengambil id supplier dari PO demo yang
                 deterministik; PO kedua supplier DICARI (supplier + produk + ada
                 penerimaan), bukan dipaku nomornya; harga +3% dihitung dari harga PO.
                 Bukti: POC **120 PASS / 0 FAIL** tiga kali berturut-turut.

### KN-SEED-PO-ENTITY-RANDOM — entitas PO data demo diacak (P1)
- Tanggal      : 2026-07-30
- Modul        : `seed_realistic.py` → `seed_entities_and_backfill()`
- Gejala       : entitas seluruh `purchase_orders` ditetapkan `"ent_kanda" if
                 random.random() < 0.3 else "ent_ksc"` TANPA `random.seed`. Dua akibat
                 nyata: (1) data demo tidak deterministik — `po_003` milik PT KSC hari ini
                 dan CV Kanda besok, sehingga uji/POC yang menyebut PO demo jadi FLAKY
                 (hijau lalu merah tanpa satu baris kode berubah, dan nomor `KSC/PO-*`
                 ikut bergeser); (2) datanya janggal di layar — PO milik PT KSC ditujukan
                 ke supplier yang terdaftar di CV Kanda, pembelian lintas-PT yang tidak
                 pernah diniatkan.
- Invariant    : INV-ENTITY-01 (semangatnya: satu dokumen satu PT yang konsisten)
- Gate penangkap: `gate.sh --full` (POC G-7 + POC F0-C) — flakiness-nya kini mustahil
- Severity     : P1
- Status       : FIXED — entitas PO MENGIKUTI entitas supplier (deterministik, sebaran dua
                 PT tetap ada karena 2 dari 6 supplier milik CV Kanda).

### KN-G7-CSS-GHOST — 6 nama kelas CSS tanpa definisi di 11 berkas layar (P1)
- Tanggal      : 2026-07-30
- Modul        : `frontend/src/styles/components.css` (pemakai: layar G-8 & G-9 terbaru)
- Gejala       : `stat-card` · `stat-label` · `stat-value` · `input-field` · `modal-panel` ·
                 `link-button` dipakai di 11 berkas layar tetapi **0 kemunculan** di bundel
                 CSS hasil build. Yang dilihat pengguna: kartu KPI tampil sebagai tulisan
                 telanjang tanpa kartu, kotak isian tanpa garis tepi (tidak terbaca sebagai
                 tempat mengetik), tombol "tautkan/lepas" di tabel mutasi bank tampil
                 sebagai tombol abu bawaan browser. Uji fungsional TETAP hijau karena
                 elemennya ada & bisa diklik — hanya tampilannya yang hilang.
- Invariant    : — (celah kelas baru: gaya yang dirujuk harus ada)
- Gate penangkap: pemeriksaan mata + `grep` pada `frontend/build/static/css/*.css`
- Severity     : P1
- Status       : FIXED — enam kelas didefinisikan mengikuti pasangan yang sudah mapan
                 (`.metric-tile`, `.field`, `.modal-card`). Diverifikasi pada bundel hasil
                 build dan pada layar Kontrabon · Pusat Kasus Keuangan · Rekonsiliasi Bank.

### KN-G7-WH-PERM-NOISE — peran Gudang disambut bilah merah "Permission ditolak" (P2)
- Tanggal      : 2026-07-30
- Modul        : `features/purchasing/contrabon/ContraBonsView.jsx`
- Gejala       : layar Kontrabon memuat `GET /api/suppliers` untuk semua peran. Gudang
                 (izin `contra_bon: view` saja, TANPA `supplier.view`) membuka layar yang
                 memang boleh dibukanya dan langsung disambut bilah merah
                 "Permission ditolak: supplier.view" — padahal tidak ada yang salah.
- Invariant    : INV-UI-03 (semangatnya: bilah error hanya untuk kegagalan yang NYATA)
- Gate penangkap: skrip uji layar peran Gudang (bagian C)
- Severity     : P2
- Status       : FIXED — daftar supplier hanya diambil bila peran boleh menulis, dan
                 kegagalannya tidak memerahkan layar. Tombol tulis (Kontrabon baru ·
                 Buat kontrabon · Atur jadwal · Jalankan pengingat) disembunyikan/dikunci
                 untuk peran pemantau.

### KN-G7-SCHED-DEFAULT-NONE — "Atur jadwal" default ke *Tidak terjadwal* (P2)
- Tanggal      : 2026-07-30
- Modul        : `features/purchasing/contrabon/ExchangeScheduleModal.jsx`
- Gejala       : supplier tanpa jadwal datang dengan `mode:"none"`. Karena nilai itu dipakai
                 sebagai isian awal, petugas mengisi PIC lalu menekan Simpan dan **tidak
                 terjadi apa pun yang terlihat**: barisnya tetap "belum dijadwalkan".
- Severity     : P2
- Status       : FIXED — isian awal jatuh ke ritme mingguan; "Tidak terjadwal" tetap bisa
                 dipilih sadar-sadar. Terbukti di layar: PIC & "Siklus berikutnya" muncul.

### KN-G7-NOTICE-TIMER — konfirmasi baru dihapus oleh pengatur waktu pesan lama (P2)
- Tanggal      : 2026-07-30
- Modul        : `features/purchasing/contrabon/ContraBonsView.jsx` (pola diwarisi G-9)
- Gejala       : `setTimeout` pembersih pesan tidak pernah dibatalkan. Bila aksi kedua
                 terjadi < 7 detik setelah aksi pertama, timer pesan LAMA menghapus pesan
                 BARU (terukur ±0,5 detik tampil) — petugas menekan Simpan, datanya benar
                 tersimpan, tetapi layar seperti tidak menjawab.
- Severity     : P2
- Status       : FIXED — id pengatur waktu disimpan di `useRef`, dibatalkan sebelum pesan
                 baru, dan dibersihkan saat komponen dilepas.

### KN-G9-POC-SC-RESIDU — POC G-9 memblokir dirinya sendiri pada jalan berikutnya (P1 uji)
- Tanggal      : 2026-07-30 (sesi lanjutan G-7 → rencana G-6)
- Modul        : `backend/test_g9_case_poc.py` (blok pembersihan)
- Gejala       : `gate.sh --full` MERAH pada gate POC G-9 dengan
                 `400 "Pengembalian Rp 120.000 melebihi saldo kredit toko Rp 0"`.
- Akar         : aksi `refund_store_credit` melahirkan baris `store_credit_ledger`
                 (`type=adjust`, `amount -120.000`) LEWAT JALUR PRODUKSI — id acak, tanpa
                 tanda POC. Pembersihan hanya menghapus baris ber-`ref_type=POC_TAG`
                 (grant suntikan), sehingga baris minus tertinggal dan menihilkan saldo
                 pelanggan uji. Jalan PERTAMA hijau, jalan BERIKUTNYA merah — POC memblokir
                 dirinya sendiri, dan `verify_data_integrity` tetap hijau (bukan pelanggaran
                 invarian, hanya residu) sehingga tak ada yang memerah lebih awal.
- Invariant    : INV-GATE-01 (POC tidak boleh meninggalkan residu)
- Gate penangkap: `gate.sh --full` → POC FASE G-9 (kini stabil dijalankan berturut-turut)
- Severity     : P1 (uji — memerahkan gate tanpa ada produk yang rusak)
- Status       : FIXED — POC mencatat NOMOR kasus yang dibuatnya (`made["case_numbers"]`)
                 dan membersihkan baris buku saldo kredit yang menyebut nomor itu. Bukti:
                 POC G-9 **114 PASS / 0 FAIL dua kali berturut-turut** + `gate.sh --full`
                 41 gate HIJAU.

### KN-FE-PORT-ORPHAN — preview mati (`frontend FATAL`) setelah build ulang (P1 operasional)
- Tanggal      : 2026-07-30
- Modul        : `scripts/rebuild_frontend.sh` + `frontend/package.json` (script `start`)
- Gejala       : sesudah `rebuild_frontend.sh`, supervisor `frontend` masuk status **FATAL**
                 (`Exited too quickly`) dan log berisi `EADDRINUSE … port 3000`. Preview
                 masih terlayani oleh proses YATIM, sehingga masalahnya tak terlihat sampai
                 seseorang me-restart layanan — lalu preview benar-benar mati.
                 Sudah **dua kali** dicatat di `SESSION_HANDOFF.md` sebagai "kejadian
                 lapangan" dengan obat MANUAL (`fuser -k 3000/tcp`), bukan diperbaiki.
- Akar         : skrip mengirim `supervisorctl signal HUP frontend` "biar aman" padahal
                 `static_server.js` melayani berkas dari disk setiap permintaan (HUP tidak
                 diperlukan). Node MENGAKHIRI DIRI saat menerima SIGHUP sementara proses
                 pembungkusnya kadang tidak ikut mati → supervisor menyalakan ulang, proses
                 yatim masih memegang port 3000, proses baru gagal mengikat port.
- Invariant    : — (kesehatan lingkungan preview)
- Gate penangkap: `supervisorctl status frontend` sesudah `rebuild_frontend.sh`
- Severity     : P1 (operasional — mematikan preview yang dilihat pemilik)
- Status       : FIXED — (a) `signal HUP` DIHAPUS beserta alasannya; (b) `yarn start`
                 membebaskan port 3000 lebih dulu (`fuser -k 3000/tcp` lalu `exec node`)
                 sehingga proses yatim tidak bisa lagi membuat FATAL. Bukti: dua
                 `supervisorctl restart frontend` berturut-turut → RUNNING + HTTP 200.

### KN-G7-DEMO-NO-CANDIDATE — wizard "Kontrabon baru" kosong pada data demo (P2)
- Tanggal      : 2026-07-30
- Modul        : `seed_realistic.py` → `seed_contra_bons()`
- Gejala       : seluruh faktur supplier demo terpakai oleh tiga kontrabon demo, sehingga
                 langkah 2 wizard kosong untuk **semua** supplier: fiturnya ada tetapi
                 tidak bisa dicoba siapa pun pada data demo.
- Severity     : P2
- Status       : FIXED — satu faktur (`INV-SLO-2620`) sengaja DIBIARKAN bebas. Terbukti di
                 layar: wizard menerbitkan `KSC/CB-00004` dari faktur itu.

---

## REGISTRY — Penutupan FASE G-9 (2026-07-30 · repo `gababannauahanam/kn`)

> **Benang merah ketiga bug di bawah:** semuanya ada di jalur **penyampaian ke manusia**,
> bukan di logika uang. Ronde uji sebelumnya (iter_187) melaporkan *"backend 23/23 · frontend
> 95%"* dan melewatkan ketiganya, karena yang diperiksa adalah **respons API**, bukan **apa
> yang dibaca pengguna ketika API menolak**. Pelajaran: tambahkan selalu pertanyaan uji
> *"kalau backend MENOLAK, apa yang muncul di layar?"*

### KN-G9-ERR-SILENT — setiap penolakan backend HILANG dari layar (2 layar keuangan terbaru)
- Tanggal      : 2026-07-30 (penutupan FASE G-9)
- Modul         : `frontend/src/components/ErrorNotice.jsx` · `features/finance/cases/FinanceCasesView.jsx` (G-9) · `features/finance/BankReconciliationView.jsx` (G-8)
- Gejala        : Petugas menekan "Jalankan & selesaikan" / "Buka kasus" / "Buat kasus" → **tidak terjadi apa pun**. Tanpa pesan, tanpa perubahan; tombol seperti mati. Terjadi pada SEMUA penjaga G-9: alasan wajib, bukti wajib, kasus kembar, di atas ambang persetujuan, 403 entitas lain.
- Akar          : `ErrorNotice` menerima prop **`message`** (string) dan `return null` bila kosong. Dua layar terbaru menyimpan objek error axios lalu mengirimnya lewat prop bernama **`error`** → `message` undefined → bilah error **tidak pernah dirender**. 115 layar lain memakai `message=` dengan benar. Lapisan kedua: wizard & modal adalah MODAL, bilah error layar induk berada di BELAKANG lapisan modal — memperbaiki nama prop saja belum cukup.
- Invariant     : **INV-UI-03** (BARU)
- Gate penangkap: `scripts/guardrails/verify_error_notice.py --self-test` (masuk `gate.sh` blok STATIK) — aturan A (prop `message` wajib) · B (`ErrorNotice` wajib menormalkan lewat `apiErrorText`) · C (modal penulis API wajib punya bilah error sendiri). 12 modal LAMA di `MODAL_BASELINE` yang **hanya boleh mengecil**.
- Severity      : **P1**
- Status        : **FIXED** — helper baru `frontend/src/utils/apiError.js`; 2 layar induk pakai `message={err}` + `testId`; **6 modal** dapat bilah error sendiri (`case-wizard-error`, `case-create-error`, `case-detail-error`, `recon-allocate-error`, `recon-match-error`, `recon-group-error`, `recon-format-error`). Bukti di layar: alokasi Rp 999.000.000 pada titipan bersisa Rp 5.131.200 → *"Σ alokasi Rp 999.000.000 melebihi sisa titipan Rp 5.131.200"* tampil DI DALAM modal. `gate.sh --full` 39 gate HIJAU.

### KN-G9-REASON-MISMATCH — alasan penutupan tidak nyambung dengan jenis kasus (invarian HIJAU tapi hampa)
- Tanggal      : 2026-07-30 (penutupan FASE G-9)
- Modul         : `services/finance_case_service.py` · `services/finance_case_playbooks.py` · `features/finance/cases/CasePlaybookWizard.jsx` · `CaseDetailPanel.jsx`
- Gejala        : Wizard menawarkan **seluruh 12 label alasan** untuk **semua 11 jenis kasus**, sehingga kasus *"Dana masuk tak dikenal"* bisa ditutup dengan alasan *"Cek / giro ditolak bank"*. Jejak yang dibaca auditor menyesatkan.
- Akar          : `GET /finance-cases/reasons` mengembalikan seluruh taksonomi `applies_to='finance_case'` secara datar, dan `_reason_or_fail()` hanya memeriksa label itu ADA + milik domain kasus keuangan. **INV-CASE-01 tetap HIJAU** karena ia hanya memeriksa "ada alasan", bukan "alasan yang nyambung" — kelas *invarian hijau tapi hampa*.
- Invariant     : INV-CASE-01 (diperkuat) — daftar sah = `reason_codes` per playbook
- Gate penangkap: `backend/test_g9_case_poc.py` — 2 uji **bukti-merah** baru (116 → **118 PASS**): `resolve` beralasan tak nyambung → 400 memuat kata "nyambung" + menyebut label yang benar; `reject` idem.
- Severity      : P2
- Status        : **FIXED** — `reason_codes` per playbook (SSOT di registry playbook), dibawa `GET /playbooks` & bentuk kasus; `_reason_or_fail(code, case_type)` menolak yang tak nyambung dengan pesan MENUNTUN (menyebut label, bukan kode); UI menyaring `case-field-reason` & `case-reject-reason` (terbukti di layar: 3 pilihan, bukan 12).

### KN-I18N-MONEY — angka gaya Inggris pada pesan pengguna (tersembunyi di balik bug P1)
- Tanggal      : 2026-07-30 (penutupan FASE G-9)
- Modul         : 30 berkas `backend/services/*` & `backend/routers/*` (terbanyak: `bank_recon_service.py` 17, `payment_plan_service.py` 9, `amendment_service.py` 8, `pr_sourcing_service.py` 8)
- Gejala        : Pesan penolakan memperlihatkan *"Rp 999,000,000"* (koma, gaya Inggris) di antarmuka yang seluruhnya Bahasa Indonesia (*"Rp 999.000.000"*).
- Akar          : uang diformat dengan tiga gaya berbeda — `f"Rp {x:,.0f}"` (Inggris), `f"Rp {x:,.0f}".replace(",", ".")`, dan **8 salinan** helper `_rp()` lokal. **Tidak mungkin ditemukan sebelum KN-G9-ERR-SILENT diperbaiki**, karena bilah errornya tidak pernah dirender — contoh nyata *bug yang saling menyembunyikan*.
- Invariant     : **audit i18n aturan [7]** (BARU) — nominal yang dibaca pengguna wajib lewat `core_utils.rupiah()`
- Gate penangkap: `scripts/audit_i18n_id.py --strict` (aturan [7]) + `--self-test` naik 12 → **16 skenario** (2 pola Inggris tertangkap · `rupiah()` dan angka non-uang tidak salah-tuduh)
- Severity      : P2
- Status        : **FIXED** — `core_utils.rupiah()` jadi satu sumber format uang; **91 pola** di 30 berkas dialihkan (codemod tercatat: `scripts/_codemod_rupiah.py`); 8 helper `_rp()` lokal dirampingkan jadi alias tipis. `ruff --select F821` bersih · `gate.sh --full` 39 gate HIJAU.

### KN-G9-REOPEN-NOUI — endpoint `reopen` hidup tanpa satu tombol pun (fitur yang "tidak ada")
- Tanggal      : 2026-07-30 (penutupan FASE G-9)
- Modul         : `routers/finance_cases.py` (`POST /finance-cases/{id}/reopen`) · `features/finance/cases/CaseDetailPanel.jsx`
- Gejala        : Kasus yang ditutup tanpa tindakan (`rejected`) tidak bisa dibuka kembali dari layar, padahal backend mendukungnya. Bagi pengguna, fiturnya tidak ada.
- Akar          : celah backend↔frontend saat fase dibangun; tidak ada gate yang membandingkan daftar `@router` dengan daftar `data-testid`.
- Invariant     : — (kandidat perluasan: gate "endpoint tanpa UI")
- Gate penangkap: verifikasi manual layar (Playwright) pada ronde penutupan
- Severity      : P2
- Status        : **FIXED** — `case-reopen-box` + `case-reopen-note` + `case-reopen-btn`. Ditutup TANPA dokumen → boleh dibuka ulang dengan alasan wajib (terbukti: `Ditutup tanpa tindakan` → `Sedang ditangani`). Sudah MELAHIRKAN dokumen → tombol TERKUNCI + penjelasan `case-reopen-locked` (*"…sudah melahirkan 2 dokumen. Buku besar bersifat tambah-saja…"*), **bukan disembunyikan**.

---

## REGISTRY — Penutupan FASE G-8 (2026-07-29 · repo `hahabannamaka/KN`)

### KN-G8-DIR-SILENT — arah dana ditebak "MASUK" saat penanda DB/CR tidak terbaca
- Tanggal      : 2026-07-29 (ronde penutupan FASE G-8)
- Modul         : `backend/services/bank_statement_parser.py` (`parse_csv`, `_dir_from_marker`)
- Gejala        : Impor rekening koran BCA **tanpa tanda kutip** (ekspor apa adanya). Baris
                  `27/07,BIAYA ADM UJI,0000,25.000,00 DB,9.975.000,00` muncul di **pratinjau**
                  sebagai **"Masuk" Rp 25.000**, dan ringkasan pratinjau melaporkan
                  *"masuk Rp 1.275.000 · keluar Rp 0"* — padahal baris itu **biaya bank
                  (uang keluar)**. Tidak ada peringatan apa pun.
- Akar masalah  : Dua celah bertumpuk.
                  (1) `parse_csv` menutup rantai arah dana dengan
                  `direction = "out" if neg else "in"` — bila penanda `DB/CR` tidak
                  terbaca, uang **diasumsikan MASUK**. Pemicunya nyata: **koma desimal
                  Indonesia adalah pemisah CSV**, jadi `25.000,00 DB` pecah menjadi dua
                  field (`25.000` + `00 DB`) dan kolom penanda bergeser.
                  (2) `_dir_from_marker` hanya menerima penanda yang **sama persis atau
                  di awal sel**, sehingga penanda yang MENEMPEL pada nominal
                  (`"12.500.000,00 CR"` — bentuk ekspor KlikBCA yang umum) tak pernah
                  terbaca. Bonus celah: `startswith` polos membaca **`"KREDITUR"`**
                  (nama pihak) sebagai `kredit` = uang masuk.
- Dampak uang   : baris keluar tercatat masuk ⇒ `statement.net` & kartu **"Selisih rekening
                  vs buku"** salah; lebih berbahaya, baris biaya jadi **kandidat pencocokan
                  ke kwitansi piutang** (pendapatan yang tidak pernah ada) dan bisa masuk
                  **Titipan Dana** sebagai dana masuk tak dikenal.
- Kenapa lolos  : POC lama menguji parser HANYA dengan CSV **ber-tanda-kutip** (`"12.500.000,00"`)
                  yang selalu punya kolom `DB/CR` utuh. Jalur ekspor nyata (tanpa kutip /
                  penanda menempel di nominal) tidak pernah diuji ⇒ gate hijau tapi hampa.
                  Ditemukan lewat **layar**, bukan teori: menempel CSV di panel Impor.
- Invariant     : `INV-BNK-01` (setiap baris berstatus & bermakna sah) — sisi **masukan** data
- Gate penangkap: `POC FASE G-8` (`backend/test_g8_bank_poc.py`) — **4 assertion bukti-merah baru**:
                  penanda menempel di kolom nominal terbaca `out` · `sum_out` tidak lagi Rp 0 ·
                  baris yang arahnya tak pasti **DITOLAK berikut arahan** · `KREDITUR` bukan
                  penanda & sel ambigu `DB/CR` tidak ditebak
- Severity      : **P1** (uang salah arah, senyap)
- Status        : **FIXED** — arah dana tidak pernah ditebak lagi. Rantai baru:
                  kolom penanda → penanda yang menempel pada kolom nominal → nominal
                  bertanda minus → **kalau tetap tak pasti: baris DITOLAK** dengan alasan
                  Bahasa Indonesia yang menuntun (*"periksa kolom penanda DB/CR pada
                  template, atau bungkus nominal dengan tanda kutip…"*). `_dir_from_marker`
                  kini memakai **batas kata** (`\b`) dan mengembalikan kosong bila satu sel
                  memuat penanda masuk DAN keluar (ambigu). Bukti: POC G-8 **118 → 122 PASS /
                  0 FAIL**, `gate.sh --full` HIJAU, `verify_data_integrity` 216/0/0.

---


### KN-F0C-FLAKY-FIXTURE — gate MERAH karena fixture uji non-deterministik (bukan bug aplikasi)
- Tanggal      : 2026-07-29 (verifikasi titik henti)
- Modul         : `backend/test_f0c_scoping_leak_poc.py` (`case_uom_usage`) vs `routers/uom_conversions.py`
- Gejala        : `gate.sh --full` MERAH pada `POC F0-C` (**26 PASS / 1 FAIL**), tetapi POC yang sama dijalankan sendiri **27 PASS / 0 FAIL**. Baris gagal: `admin X-Entity-Id=all -> melihat kedua entitas (A=['PO-00001','PO-00003','PR-00005'] B=[])`.
- Akar masalah  : `stamp()` memilih dokumen dengan `find_one({"entity_id": ent})` — **tanpa syarat & tanpa urutan**. Untuk PT-B yang terpilih bisa `wms_tasks` OUTBOUND yang **tidak punya `po_number`**, padahal endpoint melaporkan `po_number` untuk koleksi itu. Akibatnya himpunan nomor PT-B kosong.
- Bahaya sesungguhnya: **bukan** merahnya, tapi **hijau hampa** — pemeriksaan "PT-A tidak melihat dokumen PT-B" otomatis lolos bila himpunan PT-B kosong. Uji isolasi lintas-PT bisa "hijau" tanpa menguji apa pun.
- Invariant     : `INV-ENTITY-01` (isolasi lintas-entitas) — pelaksanaan uji, bukan aplikasi
- Gate penangkap: `POC F0-C` sendiri, kini dengan **bukti-merah kedua**: "fixture punya nomor dokumen yang TERLIHAT di kedua entitas" → gate MEMERAH bila fixture hampa
- Severity      : **P1** (gate palsu = risiko kebocoran PT lolos tanpa terdeteksi)
- Status        : **FIXED** — pilih dokumen dengan syarat `NUM_FIELD` (`po_number` untuk PO & wms_tasks, `number` untuk PR — selaras `routers/uom_conversions.py`) ADA & tidak kosong + `sort=[("id",1)]` agar deterministik. Bukti: **28 PASS / 0 FAIL, sama 3× berturut** + `gate.sh --full` 36/36 HIJAU (`memory/GATE_RECEIPT.md`).

### GATE-PERF-01 — gate `--full` 272 detik karena satu fungsi audit O(setting x berkas)
- Tanggal      : 2026-07-29 (permintaan pemilik: "kenapa gate lama sekali")
- Modul         : `scripts/audit_config_wiring.py` (`hits`) → dipakai `scripts/verify_data_integrity.py` (`layer_config_invariants`) → dipanggil 8-10x oleh tiap POC fase
- Gejala        : `gate.sh --full` **272s**; pemilik menunggu lama tiap kali menutup fase. `--timing` membuktikan **1 dari 30 lapisan** memakan **83%** waktu (`config` 6,37s dari 7,66s).
- Akar masalah  : `hits()` mengompilasi ulang regex dan **memindai SELURUH korpus (719 berkas) untuk SETIAP setting** — 105 setting x 3 korpus = **315 pemindaian penuh** per eksekusi. Karena lapisan config ikut di SETIAP eksekusi invarian, dan POC memanggil invarian 8-10x, biayanya berlipat ~30x dalam satu gate.
- Invariant     : - (kinerja) — tetapi berdampak pada disiplin: gate yang lambat = gate yang jarang dijalankan
- Gate penangkap: `audit_config_wiring --self-test` bagian **[6]** — membuktikan jalur cepat (index) memberi hasil **identik** dengan jalur regex (315/315). Tanpa ini, optimasi bisa menghilangkan temuan diam-diam ("hijau palsu").
- Severity      : **P2** (bukan salah hasil, tapi menghambat pemakaian gate)
- Status        : **FIXED** — index token sekali-jalan (`build_hit_index`): `build_rows` **6,23s → 0,07s (89x)**; `verify_data_integrity` LENGKAP **8,35s → 2,0s**; `gate.sh --full` **272s → 99s**; `--quick` ~8s. Cakupan tetap **36 gate / 211 invarian**. Tambahan: `--only <lapisan>` untuk blok bukti-merah POC, kolam paralel gate STATIK, mode `--ci` + receipt JSON.

---

## REGISTRY — Temuan Sesi FASE F penutup (2026-07-29)

### KN-F-LEDGER-RAWID — kolom **Dokumen** pada layar Mutasi menampilkan id teknis
- Tanggal      : 2026-07-29 (penutupan FASE F · US11)
- Modul         : `routers/inventory.py` (`/inventory/movements`, `/history/{product_id}`) + `features/wms/inventory/LedgerTable.jsx`
- Gejala        : Petugas gudang membaca `so_d29e63366078`, `wo_b1df696d5b1f`, `mko_b1ab0520c6c7:1` di kolom **Dokumen** (5 dari 12 jenis mutasi). Tak bisa ditindak, dan melanggar aturan bahasa antarmuka yang justru jadi inti FASE F.
- Invariant     : sejalan `INV-I18N` (label antarmuka) & prinsip `doc_refs_service.number_of()` ("nomor yang layak dicetak")
- Gate penangkap: `backend/test_fase_f_us3_us11_us12_poc.py` (US11 memeriksa tidak ada kode/id mentah tampil) + `scripts/audit_i18n_id.py`
- Severity      : **P2** (kosmetik-fungsional: menghambat penelusuran)
- Status        : **FIXED** — `services/movement_label_service.py` menambah field turunan `source_document_label` (batch-resolve, tanpa N+1). `so_…` → `SO-0007`, `mko_…:1` → `MKO-00001 · langkah 1`, dokumen terhapus → **"(dokumen sudah dihapus)"** (jujur, ditandai warna + `title`).

### POC-RESIDU-01 — FASE POC meninggalkan roll & pergeseran saldo stok
- Tanggal      : 2026-07-29 (penutupan FASE F)
- Modul         : `backend/test_g0_config_poc.py` · `test_g1_amendment_poc.py` · `test_g2_payment_poc.py` · `test_g3_variance_poc.py`
- Gejala        : Setelah **satu** `bash scripts/gate.sh --full` dari seed bersih: `inventory_rolls` **53 → 75** (+22) dan saldo `prod_batik_mega` bergeser (`reserved_qty` 50 → 173 · `available_qty` 435 → 307 · `atp_qty` 1235 → 1107). Akibat nyata: stok yang dilihat sales/gudang lebih kecil dari kenyataan. **Tak terdeteksi** karena `gate_residue.py --check` berjalan SEBELUM blok POC.
- Akar masalah  : POC mengonfirmasi SO (mengalokasikan & **memotong** roll — roll cut melahirkan roll baru) lalu menghapus SO **langsung dari DB** sehingga reservasi tak pernah dilepas dan roll potongan tak pernah digabung ulang.
- Invariant     : **INV-GATE-01**
- Gate penangkap: **BARU** — checkpoint kedua `gate_residue.py` khusus blok FASE POC (`KN_RESIDUE_FILE=/tmp/kn_gate_residue_poc.json`, `--ignore-trails`), dilaporkan `WARN` di receipt.
- Severity      : **P2** (hanya menyentuh data DEMO/uji, tidak ada jalur produksi)
- Status        : **FIXED** — dua lapis:
  1. **Mutasi yatim** (`inventory_movements` bertipe `reservation`/`release_reservation` yang menunjuk SO terhapus, dulu +22 baris sampah di layar Mutasi) dibersihkan di cleanup 4 POC (`source_document` **dan** `reference_id`).
  2. **Roll & saldo** ditutup lewat modul baru `backend/poc_stock_guard.py` — snapshot→restore **EKSAK** (`_id` dipertahankan) untuk `inventory_rolls`/`inventory_balances`/`inventory_movements`/`inventory_lots`, dipakai di `test_g0_config_poc.py`, `test_g1_amendment_poc.py`, `test_g2_payment_poc.py`, `test_g3_variance_poc.py`, dan `test_fase_f_us3_us11_us12_poc.py`. Pengaman: hanya jalan bila `DB_NAME` mengandung `test`/`demo`/`dev` atau `KN_GATE_ALLOW_RESTORE=1`; `KN_GATE_NO_RESTORE=1` untuk mode ukur kebocoran.
- Bukti          : `bash scripts/gate.sh --full` → **INV-GATE-01 anti-residu FASE POC PASS** ("nol residu: 15 koleksi, 21 balance, 9 SO"). Sebelum perbaikan: 8 pelanggaran (+22 roll, 7 pergeseran saldo). Gate juga menyemai ulang data demo + memverifikasi integritas SETELAH blok POC sebagai jaring kedua.
- Pelajaran      : *"kalau bug lolos semua gate → gate-nya kurang"*. Checkpoint anti-residu hanya mengukur blok guardrail runtime; blok POC yang berjalan sesudahnya tak terpantau selama berbulan-bulan.

### KN-F-SEED-NUMBER-DRIFT — nomor dokumen demo melompat setiap seed ulang
- Tanggal      : 2026-07-29 (penutupan FASE F)
- Modul         : `seed_realistic.py` (`clear_collections`)
- Gejala        : Seed ulang ke-3 menghasilkan `KSC/SCT-00026 … 00032` padahal hanya ada 7 kontrak; dokumen/uji yang menyebut `KSC/SCT-00007` jadi salah dan data demo tidak deterministik.
- Akar masalah  : counter atomik di koleksi `number_sequences` TIDAK ikut dibersihkan bersama dokumen pemiliknya.
- Gate penangkap: `backend/test_fase_f_us3_us11_us12_poc.py` (US12 mencari jangkar kontrak) + laporan `testing_agent_v3` iter_183
- Severity      : **P2**
- Status        : **FIXED** — `clear_collections()` kini juga `number_sequences.delete_many({})`. Aman karena semua dokumen pemilik nomor ikut dihapus. Bukti: seed ulang → `KSC/SCT-00001…00007`, `KSC/SPEC-00001/2`, `KSC/SMP-00001/2`.

---

## REGISTRY — Temuan Sesi #076 (report-only; dipetakan ke gate baru Guardrail v2)

### KN-076-AUTH-DOC-PREVIEW — dokumen bisnis bocor tanpa autentikasi
- Tanggal      : 2026-07-05 (#076)
- Modul         : routers/documents.py:102 `preview_document`
- Gejala        : `GET /documents/preview/{id}?document_type=surat_jalan|invoice` → 200 HTML penuh TANPA login.
- Invariant     : **INV-AUTH-01**
- Gate penangkap: `scripts/guardrails/verify_auth_coverage.py` (MERAH — terbukti menangkap).
- Severity      : **P0**
- Status        : **FIXED** (#080) — `preview_document` kini `await require_permission(request,"document","view")`. Bukti: `verify_auth_coverage.py` HIJAU (0 pelanggaran); runtime 401 tanpa auth, 200 dgn auth.

### KN-076-AUTH-MASTER-LEAK — master-data & analitik GET tanpa autentikasi
- Tanggal      : 2026-07-05 (#076)
- Modul         : products.py (GET /products & /products/{id}/stock-breakdown — 401 ditelan try/except), uoms.py, warehouses.py, pos.py (best-sellers, frequently-bought-together, substitutes)
- Gejala        : 8 endpoint GET menyajikan data TANPA login (katalog, UoM, gudang+alamat, analitik penjualan).
- Invariant     : **INV-AUTH-01**
- Gate penangkap: `scripts/guardrails/verify_auth_coverage.py` (MERAH, 8 pelanggaran).
- Severity      : **P1** (pos/warehouses lebih sensitif).
- Status        : **FIXED** (#080) — auth ditegakkan di LUAR try/except: products.py (`require_permission product.view` di `list_products` & `stock_breakdown`), uoms.py (`uom.view`), warehouses.py (`warehouse.view`), pos.py 3 endpoint (`order.view`). Bukti: `verify_auth_coverage.py` HIJAU (505 cek, 0 pelanggaran); runtime 401→200.

### KN-076-IDOR-READ-SUBRES — baca sub-resource lintas-entitas
- Tanggal      : 2026-07-05 (#076)
- Modul         : customers.py (/customers/{id}/360, /credit-status), sales_orders sub-resource (/sales-orders/{id}/invoices)
- Gejala        : sales@ent_ksc membaca profil/kredit/invoice milik ent_kanda → 200.
- Invariant     : **INV-ENTITY-01**
- Gate penangkap: `scripts/guardrails/verify_cross_entity.py` (MERAH — 3 LEAK baca).
- Severity      : **P0**
- Status        : **FIXED** (#080) — `can_access_customer` kini menegakkan isolasi entitas untuk role ter-scope (customer.entity_id ∉ allowed_entity_ids → tolak, walau assigned_sales_id cocok); `/sales-orders/{id}/invoices` kini `assert_entity_access`. Bukti: `verify_cross_entity.py` HIJAU (0 leak); sales@ent_ksc→cust ent_kanda = 403, own-customer = 200, admin oversight = 200.

### KN-076-IDOR-WRITE-INBOUND — mutasi task inbound lintas-entitas
- Tanggal      : 2026-07-05 (#076)
- Modul         : routers/inbound_receiving.py (escalate/complete/qc-decision/scan-receive/resolve-escalation; 0× assert_entity_access)
- Gejala        : warehouse@ent_ksc `POST /inbound/tasks/{id}/escalate` pada task ent_kanda → 200 tereksekusi.
- Invariant     : **INV-ENTITY-01**
- Gate penangkap: `scripts/guardrails/verify_cross_entity.py` (MERAH — 1 LEAK tulis).
- Severity      : **P1**
- Status        : **FIXED** (#080) — 5 endpoint mutasi inbound (scan-receive/escalate/resolve-escalation/complete/qc-decision) kini `assert_entity_access(task,"wms_tasks", ctx)` setelah fetch. Bukti: `verify_cross_entity.py` + `verify_nonfinancial_sweep.py` HIJAU; warehouse@ent_ksc→task ent_kanda = 404.

### KN-076-AR-GL-DRIFT — Piutang GL ≠ subledger AR; gate tak merekonsiliasi AR
- Tanggal      : 2026-07-05 (#076)
- Modul         : GL 1-1200 vs subledger (ent_ksc & ent_kanda)
- Gejala        : selisih AR GL vs subledger; gate `verify_data_integrity` tak punya invarian rekonsiliasi AR.
- Invariant     : (kandidat **INV-AR-01** — belum ada)
- Gate penangkap: BELUM ADA → **perkuat gate** (tambah invarian WARN rekonsiliasi AR).
- Severity      : **P2** (kemungkinan artefak seed; perlu triase).
- Status        : **FIXED** (#081) — `post_cash_transaction` untuk `ar_receipt` kini (a) membukukan JE di entitas PEMILIK piutang (bukan "all"/kas_besar) & (b) split: Cr Piutang=`applied_total`, Cr Uang Muka Pelanggan (2-1400)=`unapplied` (kelebihan bayar), Dr Uang Muka=`used_deposit`. Gate BARU **GL-5/INV-AR-01** ditambahkan (verify_data_integrity.py). Bukti: data-integrity HIJAU (AR tak bocor ke 'all', tak negatif; 'all' AR=0; ent_kanda deposit 950k di 2-1400; trial balance seimbang); testing agent VERIFIED.

### KN-076-COGS-ZERO — revenue diakui tanpa jurnal HPP
- Tanggal      : known (#075/#076)
- Modul         : GL fulfillment / post_order_cogs
- Gejala        : 6 order punya JE pendapatan tanpa JE HPP (margin 100%).
- Invariant     : INV-DATA (gate = WARN, belum FAIL)
- Gate penangkap: `scripts/verify_data_integrity.py` (WARN 1).
- Severity      : **P2**
- Status        : **FIXED** (#081) — `gl_service.backfill_journals` kini memanggil `post_order_cogs(o)` untuk tiap order (selaras jalur runtime routers/invoices.py), sehingga tiap order berpendapatan punya jurnal HPP (source_type='sales_cogs'). Bukti: data-integrity GL-4 HIJAU (0 COGS-ZERO); testing agent: akun 5-1000 (HPP) 6 entri, total debit 58.795.000 (non-zero), 6 revenue ↔ 6 COGS.

### KN-077-RACE-VBILL-PAY — pembayaran vendor-bill paralel → OVERPAYMENT (TOCTOU) 🆕
- Tanggal      : 2026-07-05 (#077 — blindspot konkurensi ditutup)
- Modul         : routers/vendor_bills.py `pay_vendor_bill` (baris ~392→427)
- Gejala        : 6 `POST /vendor-bills/{id}/pay` paralel amount=grand_total → **6× 200**;
                  `amount_paid = 164.835.000` vs `grand_total = 27.472.500` (**OVERPAY 6.0×**).
                  Akar: check-then-`$inc` non-atomic — semua request baca `amount_paid` stale, lolos guard
                  `amount ≤ outstanding`, lalu `$inc`. Efek: kas keluar ganda + AP under-stated + GL rusak.
- Invariant     : **INV-CONC-01**
- Gate penangkap: `scripts/guardrails/verify_concurrency.py` (MERAH — terbukti).
- Severity      : **P0** (integritas keuangan).
- Status        : **FIXED** (#080) — guard atomik `find_one_and_update({id,status:"posted", $expr:{amount_paid+amount ≤ grand_total}}, {$inc amount_paid,...})`; kas dicatat HANYA setelah guard sukses (tak ada orphan cash saat 409). Bukti: `verify_concurrency.py` HIJAU (pembayaran paralel aman, amount_paid = grand_total); sequential partial-pay tetap akumulasi benar, overpay ditolak 400.

### KN-077-RACE-AR-RECEIPT — AR-receipt paralel → LOST-UPDATE (P1)  ✅ CONFIRMED (#078)
- Tanggal      : 2026-07-05 (dikonfirmasi #078 pada K=20)
- Modul         : services/ar_receipt_service.py `_apply_to_order` (~134→163)
- Gejala        : 20 `POST /ar-receipts` paralel (amount=outstanding penuh) → **3× 200**; **3 ar_receipts dibuat**
                  tapi `order.payments` hanya **1 entri** → 2 penerimaan uang HILANG dari ledger order (lost-update).
                  Akar: `$set payments = (read list + append)` → concurrent clobber (window kecil, butuh K tinggi).
- Invariant     : **INV-CONC-01**
- Gate penangkap: `scripts/guardrails/verify_concurrency.py` (MERAH pada K_AR=20).
- Severity      : **P1** (rekonsiliasi AR rusak; pelanggan bisa over/under-credit).
- Status        : **FIXED** (#080) — `_apply_to_order` kini `$push` payment atomik + `$inc paid_total` dgn guard `$expr:{Σpayments.amount + amount ≤ grand_total}` (SSOT = Σpayments per `_order_paid`), TIDAK lagi `$set` seluruh array. Bukti: `verify_concurrency.py` HIJAU (K=20 → hanya 1 sukses; receipts=1=payments=1); sequential partial-pay akumulasi benar (status→paid).

### KN-078-WMS-RESURRECTION — task WMS terminal bisa di-advance lagi (P2)  🆕
- Tanggal      : 2026-07-05 (#078 — blindspot state-machine WMS)
- Modul         : routers/wms.py `advance_task` (~150-151) + `FLOW_STAGES`
- Gejala        : 6/6 task status **'completed'** (flow inbound) → `POST /wms/tasks/{id}/advance` → **200**,
                  status kembali ke **'in_transit'** (terminal "hidup lagi"). Idem 'qc_pending'/'waiting_goods'.
                  Akar: status tsb TAK ADA di `FLOW_STAGES[flow]` → `current_idx = ... else 0` → maju ke `stages[1]`.
                  Risiko: re-proses / DOUBLE-RECEIPT inbound yang sudah selesai.
- Invariant     : **INV-STATE-01**
- Gate penangkap: `scripts/guardrails/verify_state_machine.py` (SM-WMS-1 MERAH).
- Severity      : **P2**
- Status        : **FIXED** (#081) — `routers/wms.py advance_task` kini menolak (409) advance untuk status terminal (`done/dispatched/completed/cancelled`) ATAU status di luar `FLOW_STAGES` (tidak lagi reset `current_idx=0` — akar bug); `scan` juga menolak terminal via `TERMINAL_STATUSES`. Frontend: tombol Advance di-disable untuk task terminal. Bukti: `verify_state_machine.py` HIJAU (SM-WMS-1: 6 task terminal ditolak advance, status tak berubah); testing agent VERIFIED (advance & scan terminal → 409; in-flow advance tetap 200).

### KN-078-STATE-PO — state-machine Purchase Order (HASIL: SEHAT ✅)
- Modul         : routers/purchase_orders.py approve/cancel
- Hasil         : approve PO non-'waiting_approval' → 409 ✅ · cancel PO 'completed' → 400 ✅ · SoD + approval berjenjang terjaga.
- Invariant     : **INV-STATE-01** · Gate: `verify_state_machine.py` (SM-PO-1/2 HIJAU) · Status: **VERIFIED HEALTHY**.

### KN-077-STATE-SO — state-machine Sales Order (HASIL: SEHAT ✅)
- Tanggal      : 2026-07-05 (#077 — blindspot state-machine ditutup)
- Modul         : routers/sales_orders.py `cancel_order` + services `so_transition`
- Hasil         : SM-1 cancel melepas roll ter-reserve (2→0) ✅ · SM-2 SO 'done' tak bisa di-cancel (409) ✅ ·
                  SM-3 cancel-ulang idempoten (409, no-crash) ✅ · SM-4 tak ada zombie wms_task pasca-cancel ✅.
- Invariant     : **INV-STATE-01**
- Gate penangkap: `scripts/guardrails/verify_state_machine.py` (HIJAU).
- Severity      : —
- Status        : **VERIFIED HEALTHY** (bukti: gate hijau; regresi kini terkunci).

### KN-079-NUM-BOUNDS-GAP — skema/endpoint menerima nilai numerik mustahil (class-of-risk)  🆕
- Tanggal      : 2026-07-05 (#079 — blindspot numeric-bounds ditutup)
- Modul         : `backend/schemas*.py` (82 field INPUT) + endpoint terkait (customers/products/payment-terms/…)
- Gejala        : dari ~99 field numerik ber-semantik, HANYA 2 yang punya bound (`UOMPayload.precision ge=0`, `factor_to_base gt=0`).
                  82 field INPUT (money/percent/qty/count) TANPA `Field(ge=/gt=/le=)`. Bukti runtime:
                  `POST /customers credit_limit=-5.000.000 → 200`, `POST /products price=-1000 → 200`,
                  `POST /payment-terms dp_percent=999 → 200` — semua tersimpan ke DB.
                  Positive control `POST /uoms factor_to_base=-1 → 422` membuktikan bound MEMANG ditegakkan bila ada.
- Kelas bug     : MONEY-NEG (nominal negatif), PCT-OVER (persen di luar 0–100), QTY-NONPOS (qty/faktor ≤0).
- Invariant     : **INV-NUM-01**
- Gate penangkap: `scripts/guardrails/verify_numeric_bounds.py` (STATIK 82 HARD + 15 SOFT; RUNTIME 3 LEAK; MERAH).
- Severity      : **P1** (integritas data lintas domain: harga negatif → GL/margin rusak; diskon>100% → total negatif).
- Status        : **FIXED** (#080) — 82 field INPUT (money/qty/count → `Field(ge=0)`; percent → `Field(ge=0, le=100)`) + 15 SOFT (Patch/Update) diberi bound (total 97 field di 6 file schemas). Bukti: `verify_numeric_bounds.py` HIJAU (STATIK 0 HARD/0 SOFT, RUNTIME 0 LEAK); runtime `credit_limit=-5jt/price=-1000/dp_percent=999 → 422`, nilai valid → 200.

### KN-079-IDOR-CREDIT-STATUS — credit-status bocor lintas-PT (tanpa cek kepemilikan)  🆕 (mempertajam #076)
- Tanggal      : 2026-07-05 (#079 — sweep non-finansial bebas-ambiguitas)
- Modul         : `routers/crm.py::get_credit_status` (`GET /customers/{id}/credit-status`, ~137–150)
- Gejala        : aktor `sales` entitas A membuka credit-status customer entitas B yang **BUKAN miliknya** (assigned_sales_id≠aktor) → **200**
                  (mengungkap limit kredit, proyeksi AR, gate blokir). Endpoint hanya `require_permission(order,view)` — TAK memanggil `can_access_customer`.
                  Kontras: `/360`, `/followups`, `/credit-override` benar **403** (memakai `can_access_customer`) → membuktikan ini leak murni, bukan artefak.
- Invariant     : **INV-ENTITY-01** (perluasan non-finansial)
- Gate penangkap: `scripts/guardrails/verify_nonfinancial_sweep.py` (MERAH — 1 LEAK bersih; 5 OK).
- Severity      : **P1** (kebocoran data kredit/AR lintas entitas).
- Status        : **FIXED** (#080) — `get_credit_status` kini memanggil `can_access_customer(actor, customer)` (403 bila bukan milik / lintas-PT), konsisten dgn `get_customer_360`. Bukti: `verify_nonfinancial_sweep.py` HIJAU (0 leak; CRM credit-status lintas-PT = 403).
- Catatan       : sweep juga memverifikasi WMS task ops lintas-PT (scan/advance) = **404 (sehat)**; HR/RFID/cycle-count/omnichannel = SKIP (seed single-entity / kosong).


---

## FALSE POSITIVE (BUKAN bug aplikasi — jangan "diperbaiki")

### FP-076-P6-PPN — `forensic/fa_e2e.py`
- fa_e2e baca PPN dari akun **2-1300/2-1310** (usang); PPN Keluaran sebenarnya **2-1200** (`ACC_PPN_OUT`).
- Verifikasi: JE nyata SO-0001 seimbang dgn Cr PPN 2-1200. → **aplikasi BENAR**; perbaiki skrip test.

### FP-076-VB-PPN-NONPKP — `test_vendor_bill_backend.py`
- Test asumsikan PO-00001 non-PKP; PO-00001 yang ter-fetch milik **ent_ksc (PKP)**. Vendor-bill ent_kanda (non_ppn) terverifikasi `is_pkp=false, ppn=0`. → **aplikasi BENAR**.

### FP-076-VB-VIEW-PERM — `test_vendor_bill_backend.py`
- Test harap `sales==200` melihat vendor-bill; aplikasi benar **menolak 403** (least-privilege). → ekspektasi test usang.

---

---

## REGISTRY — Temuan Sesi FASE E (Sourcing Berbasis Kontrak · 2026-07-26)

> Keempat bug di bawah **LOLOS dari seluruh 12 gate lama** karena gate lama hanya menguji
> backend/data/nav — tidak ada satu pun yang menguji **perilaku UI**. Sesuai aturan emas
> ("bug lolos gate = gate kurang"), ditambahkan gate baru **INV-UI-01**
> (`scripts/guardrails/verify_modal_dismiss.py`, sudah di-self-test MERAH→HIJAU).

### KN-FASEE-UI-MODAL-CLOSE — memilih opsi dropdown MENUTUP modal (isian hilang)
- Tanggal      : 2026-07-26 (Fase E)
- Modul         : 21 backdrop modal FE; terparah `features/purchasing/supplier-items/SupplierItemImportModal.jsx`, `features/purchasing/PrSourcingPanel.jsx` (modal Realisasi PR→PO), `features/purchasing/makloon/MakloonWizard.jsx`
- Gejala        : Di modal "Impor Massal Barang Supplier", memilih supplier membuat SELURUH modal tertutup → pengguna tidak pernah bisa menyelesaikan impor massal. Fitur inti Fase E praktis tak terpakai.
- Akar masalah  : Backdrop memakai handler mentah `onClick={onClose}`. Isi dropdown Radix (Select/Popover) dirender lewat **React portal** ke `document.body` → pada React event system klik tetap MEREMBET ke ancestor React (backdrop). Ditambah, opsi yang menjorok melewati kartu modal memang berada DI ATAS area backdrop, sehingga klik "nyasar" juga menutup modal.
- Invariant     : **INV-UI-01** (BARU)
- Gate penangkap: `scripts/guardrails/verify_modal_dismiss.py` (BARU — self-test: MERAH 1 pelanggaran pada backdrop mentah, HIJAU 26/26 setelah perbaikan)
- Severity      : **P1**
- Status        : **FIXED** — helper baru `frontend/src/utils/overlayDismiss.js` (tutup hanya bila `pointerdown` DAN `click` tepat di backdrop) dipasang di **21 backdrop**; `components/ui/select.jsx` + `components/ui/popover.jsx` kini `stopPropagation()` pada isi portal. Bukti: iteration_169 (US-E12 & US-E14 modal tetap terbuka) + regresi manual modal `contract-form-modal` & `supplier-item-form-modal`.

### KN-FASEE-UI-SELECT-BLANK — KNSelect tampil KOSONG tanpa teks petunjuk
- Tanggal      : 2026-07-26 (Fase E)
- Modul         : `components/KNSelect.jsx` (jalur Radix Select, dipakai SELURUH aplikasi untuk daftar < 6 opsi)
- Gejala        : Field wajib seperti **"Gudang Tujuan *"** pada form PR Baru tampil sebagai kotak PUTIH KOSONG — tanpa placeholder, tanpa petunjuk harus memilih apa. (Field dengan ≥6 opsi aman karena memakai jalur combobox.)
- Akar masalah  : Radix hanya menampilkan `placeholder` bila `value === undefined`; komponen ini selalu *controlled* dan memetakan `""` → sentinel `"__empty__"` TANPA menyediakan item pendamping → Radix menilai "sudah ada nilai" tapi tak menemukan item yang cocok → render kosong.
- Invariant     : (kandidat perluasan INV-UI-02 — belum tergerbang otomatis; dijaga uji UI)
- Gate penangkap: TIDAK ADA gate statik (perilaku render Radix). Terdeteksi via uji UI Playwright.
- Severity      : **P2**
- Status        : **FIXED** — sentinel berlabel `placeholder` disisipkan **hanya selama nilai masih kosong** (tak menambah kemampuan mengosongkan field wajib setelah dipilih) + gaya redup `[data-kn-empty="true"]`. Setiap opsi kini juga punya `data-testid` `<trigger>-option-<value>` (mempermudah uji otomatis). Bukti: iteration_169 US-E13 ("— Pilih gudang —" tampil).

### KN-FASEE-PREFILL-OUTPUT-NAME — Wizard Makloon ter-prefill tampak "belum diisi"
- Tanggal      : 2026-07-26 (Fase E)
- Modul         : `backend/services/pr_sourcing_service.py` (`makloon_prefill`) + `features/purchasing/makloon/MakloonWizard.jsx`
- Gejala        : Dari baris PR ber-mode makloon, Wizard terbuka ter-prefill, TAPI kolom **"Produk Hasil (output)"** tampak KOSONG ("pilih output") dan ringkasan rantai proses menampilkan **"?"** — pengguna menyangka prefill gagal, padahal `output_product_id` sudah benar dan order tersimpan benar.
- Akar masalah  : Payload prefill hanya mengirim ID (`output_product_id`) tanpa `output_name`/`output_unit`; UI menampilkan nama, bukan ID.
- Invariant     : —
- Gate penangkap: TIDAK ADA (POC hanya memeriksa ID & hasil simpan, bukan tampilan nama). Terdeteksi via uji UI.
- Severity      : **P2**
- Status        : **FIXED** — prefill kini menyertakan `input_name/input_sku/input_unit`, `output_name/output_sku/output_unit`, `byproduct_name`; wizard memetakannya ke state langkah. Bukti: iteration_169 US-E15 (tahap 2 menampilkan "Kain Grey Katun (per Yard)", ringkasan tanpa "?").

### KN-FASEE-UI-GRID-GAP — kolom panel realisasi PR berhimpitan
- Tanggal      : 2026-07-26 (Fase E)
- Modul         : `features/purchasing/PrSourcingPanel.jsx`
- Gejala        : Header terbaca "SISAJEJAK REALISASI" dan nilai menempel: "0KSC/PO-00016" — angka sisa & nomor dokumen menyatu sehingga sulit dibaca.
- Akar masalah  : Grid 7 kolom tanpa `gap`.
- Invariant     : —
- Gate penangkap: TIDAK ADA (kualitas visual). Terdeteksi via screenshot.
- Severity      : **P2**
- Status        : **FIXED** — `gap-x-3` pada baris header & baris data. Bukti: screenshot pasca-perbaikan ("SISA | JEJAK REALISASI", "0  KSC/PO-00017").

## REGISTRY — Temuan Sesi FASE F-1 (2026-07-26 lanjutan-2)

> Bug di bawah **LOLOS dari SELURUH 13 gate** — bukan karena gate lemah pada satu titik, tetapi
> karena **tidak ada satu pun POC/gate yang pernah menerima barang berbasis `kg`**. Semua POC &
> data seed sebelumnya memakai produk berbasis panjang (meter/yard) yang punya gramasi & lebar.
> Sesuai aturan emas ("bug lolos gate = gate kurang"), POC Fase F-1 kini **selalu** menguji
> penerimaan produk `kg` sampai `complete` + roll terbentuk (TEST 9), sehingga kelas bug ini
> tidak bisa kembali diam-diam.

### KN-F1-KGBASE-GR — penerimaan produk berbasis `kg` MUSTAHIL diselesaikan
- Tanggal      : 2026-07-26 (Fase F-1)
- Modul         : `backend/services/uom_service.py` → `kg_per_base_unit()` / `resolve_roll_measures()`
                  (dipakai `routers/inbound_receiving.py` `complete`)
- Gejala        : `POST /api/inbound/tasks/{id}/complete` untuk produk `base_unit = kg` **tanpa**
                  gramasi/lebar (benang `BNG-KTN-001`, obat celup, bahan kimia) **selalu 400**:
                  *"Roll BNG-KTN-001: tak bisa menurunkan panjang dari berat — isi gramasi & lebar
                  (atau kg_per_meter) produk, atau masukkan panjang aktual."* Artinya **seluruh
                  penerimaan benang & bahan kimia tidak bisa masuk stok** — padahal benang adalah
                  bahan baku utama ERP tekstil ini.
- Pra-ada?      : **YA.** Direproduksi memakai jalur **LAMA** (`actual_qty` saja, tanpa `doc_uom`)
                  pada produk seed `prod_benang_katun` → tetap 400. **Bukan** regresi Fase F-1.
- Akar masalah  : `kg_per_base_unit()` mengembalikan `0.0` bila `product_kg_per_meter()` ≤ 0
                  (yaitu bila gramasi × lebar tak tersedia). Untuk produk yang base unit-nya
                  **memang satuan berat**, faktor kg-per-base-unit adalah **fisika murni**
                  (1 kg = 1 kg) dan GSM/lebar TIDAK relevan. Karena nilainya 0,
                  `resolve_roll_measures()` (cabang `task_unit == "kg"`, tanpa panjang aktual)
                  menolak menurunkan `length_base` dari berat. Inkonsistensi lama:
                  `makloon_calc_service` sudah men-hardcode `1.0` untuk `kg`, tapi jalur GR tidak.
- Invariant     : INV-UOM-02 (jejak konversi) · dijaga POC Fase F-1 TEST 9 (E2E `complete` + roll)
- Gate penangkap: TIDAK ADA gate lama. Sekarang: `backend/test_fase_f1_receiving_uom_poc.py`
                  TEST 9 (self-test: MERAH sebelum perbaikan — 2 assertion gagal, HIJAU sesudah).
- Severity      : **P1**
- Status        : **FIXED** — tabel `WEIGHT_BASE_KG` (`kg` 1,0 · `gram` 0,001 · `ton` 1000 ·
                  `lbs` 0,45359237 · `ounce` 0,0283495231) diperiksa **lebih dulu** di
                  `kg_per_base_unit()`. Bukti: POC Fase F-1 **47 PASS / 0 FAIL** (TEST 9 GR
                  complete 200 + roll benang total = qty PO); regresi `test_catch_weight_poc.py`
                  Bagian A tetap **14/14 PASS** (termasuk kasus "tanpa gramasi/lebar → 0" untuk
                  produk berbasis *meter*). Dampak samping positif: konversi `kg ↔ gram/ton/lbs/
                  ounce` untuk produk berbasis berat kini tersedia tanpa aturan registry tambahan.

### KN-F1-PREVIEW-422 — pratinjau satuan menjawab 422 Pydantic (tak terbaca operator)
- Tanggal      : 2026-07-26 (Fase F-1)
- Modul         : `backend/schemas_purchasing.py` → `ReceiveUomPreviewIn.doc_qty`
- Gejala        : `POST /api/inbound/tasks/{id}/preview-uom` dengan `doc_qty = 0` menjawab **422**
                  berisi detail Pydantic (`"Input should be greater than 0"`), bukan pesan
                  berbahasa Indonesia. Petugas gudang tidak bisa membaca/menindaklanjuti.
- Akar masalah  : `Field(..., gt=0)` menolak di lapis skema sebelum service sempat memberi pesan.
- Invariant     : INV-NUM-01 (batas numerik) — harus tetap dipenuhi
- Gate penangkap: `testing_agent_v3` iter_170 (minor issue) → lalu di-kunci POC TEST 11.
                  Percobaan pertama (menghapus bound sama sekali) membuat **gate `INV-NUM-01`
                  MERAH** — bukti gate bekerja.
- Severity      : **P2**
- Status        : **FIXED** — `Field(0, ge=0)` (bukan `gt=0`): qty **0** lolos skema lalu ditolak
                  service dengan **400** *"Qty surat jalan (doc_qty) harus lebih besar dari 0."*,
                  sedangkan nilai **negatif** tetap ditolak lapis skema sehingga `INV-NUM-01`
                  tetap HIJAU. Bukti: POC Fase F-1 TEST 11 (3 assertion baru) + `gate.sh` HIJAU.

## RINGKASAN
> **FIXING PHASE #080–#081 (2026-07-05):** owner menyetujui perbaikan **P0+P1** lalu **P2**. Ke-8 bug P0/P1 **FIXED** (#080) + ke-3 bug P2 **FIXED** (#081) — semua terverifikasi (6 gate guardrail HIJAU + data-integrity HIJAU + testing agent). Satu-satunya gate MERAH tersisa: `validate_compliance` karena `sales_orders.py` 803 baris (>800) — isu kualitas kode pra-ada (refactor), **bukan bug** keamanan/data.

> **REFACTOR + FIX PHASE #082 (2026-07-05) — COPY REPO + LANJUT BUG FIX (SEMUA HIJAU + 0 WARN):**
> - **`validate_compliance` MERAH→HIJAU:** `sales_orders.py` (803) di-split → `sales_orders.py` (442) + `sales_orders_extra.py` (395). Endpoint path TIDAK berubah; `sales_orders_extra` diregister SEBELUM `sales_orders` di server.py agar `/sales-orders/frequent-products` tetap match sebelum `/{order_id}`.
> - **Bug NYATA ditemukan+FIXED:** `routers/hr_payroll.py` query `db.entities` (koleksi salah/kosong) → nama entitas TIDAK muncul di PDF slip gaji. Diperbaiki ke `db.business_entities`. (Ditemukan saat investigasi warning NAMING/ENTITY_REGISTRY.)
> - **Semua 56 WARN validate_compliance → 0 WARN:**
>   - Backend router di bawah 640: `purchase_orders.py`(752→565)+`purchase_orders_extra.py`, `inbound_receiving.py`(682→500)+`inbound_receiving_extra.py`, `outbound_picking.py`(673→375)+`outbound_picking_extra.py`.
>   - Frontend di bawah threshold: `App.js`(469→362)+`AppViewRouter.jsx`, `navigationConfig.js`(541→146)+`navStructure.js`+`navMeta.js`, CartPanel/CheckoutDrawer/FinancialStatements/GeneralLedger/ProductTemplates/ApprovalRules/AdminView/Inbound&OutboundScan (semua <425 via ekstraksi sub-komponen).
>   - 21 koleksi domain didaftarkan di `ENTITY_REGISTRY.md` + allowlist `validate_compliance.py` (ENTITY_REGISTRY+NAMING). data-testid ditambah ke 5 file features.
> - **Regresi tooling ditemukan+FIXED:** split navigationConfig membuat `check_nav_map.py` gagal (parse NAV_STRUCTURE by text). Script diarahkan ke `navStructure.js`. → HIJAU lagi.
> - **HASIL:** `bash scripts/gate.sh` → **SEMUA 12 GATE HIJAU**. `validate_compliance` = 106 PASS / 0 FAIL / **0 WARN**. Regression testing_agent = 34 passed, 0 issue. Refactor murni struktural (perilaku tak berubah) + 1 bug fix.

> **FEATURE PHASE #083 (2026-07-05) — 3 PERMINTAAN OWNER (SEMUA HIJAU + 0 WARN):**
> - **F2 — Split-Sales (PIC + co-sales) DIPINDAH ke CHECKOUT:** dulu `order.sales_team = resolve_customer_sales_team(customer)` (paksa dari customer). Kini `sales_orders.py` create_order pakai `normalize_sales_team(payload.sales_team)` (validasi: tepat 1 PIC, tak duplikat, split>0, total=100%) → **fallback** ke tim default customer bila kosong. Editor `SalesTeamEditor` ditambah di **checkout desktop (Step 2)** + **mobile (MobileCart & MobileCartSheet)**, **prefill** dari default customer (`customerDefaultTeam`), bisa override per order. Insentif tetap "bagi lengkap" per split (engine `sales_force_service` sudah pakai order.sales_team). Tim per-order tampil di OrderDetailPanel via `OrderFulfillmentBadges.jsx`.
> - **F3 — Tanggal Pengiriman (metode 'kirim'):** field OPSIONAL `delivery_date` (schema `SalesOrderCreate` + create_order). Validasi: format ISO & TIDAK boleh di masa lalu (hanya hari ini ke depan; input `min=today`). Ditampilkan di CheckoutStep3 + badge di order detail. Metode 'ambil' tetap wajib pickup_date.
> - **F1 — SATUAN mengikuti MASTER DATA + 2 unit di semua tampilan inventory:** akar masalah "semua meter" = seed hanya produk meter. Ditambah 2 produk contoh: **DNM-BDG-001 Denim (base_unit=yard, 300 yard=2 roll @Bandung)** & **BNG-KTN-001 Benang (base_unit=kg, 90 kg=1 roll @Surabaya)** — balances→auto rolls (unit ikut base_unit). Perbaikan tampilan 2 unit (roll + qty·unit): `BalancesTable` kolom Available kini tampil unit; `ProductQuickView` Tersedia/Reserved tampil unit; RFQ unit ikut produk (read-only); banner backorder tak lagi hardcode 'meter'. PosProductCard/MobileProductCard/MobileQuickView sudah dual-unit.
> - **HASIL:** `bash scripts/gate.sh` → **SEMUA 12 GATE HIJAU** (validate_compliance 106/0/0 **0 WARN**, data-integrity **124/0/0** dgn produk yard/kg — roll-as-SSOT rekonsiliasi OK). testing_agent F2+F3 = backend 100% + FE code-review 100%; F1 = backend 100% + FE code-review 100%. Tanpa mock.


| Invariant | Gate | Status bug |
|-----------|------|-------------|
| INV-AUTH-01 | ✅ `verify_auth_coverage.py` HIJAU | AUTH-DOC-PREVIEW (P0) ✅FIXED, AUTH-MASTER-LEAK (P1) ✅FIXED |
| INV-ENTITY-01 | ✅ `verify_cross_entity.py` HIJAU | IDOR-READ-SUBRES (P0) ✅FIXED, IDOR-WRITE-INBOUND (P1) ✅FIXED |
| INV-CONC-01 | ✅ `verify_concurrency.py` HIJAU | KN-077-RACE-VBILL-PAY (P0) ✅FIXED, KN-077-RACE-AR-RECEIPT (P1) ✅FIXED |
| INV-STATE-01 | ✅ `verify_state_machine.py` HIJAU (SO/PO/WMS) | KN-078-WMS-RESURRECTION (P2) ✅FIXED. SO & PO = VERIFIED HEALTHY |
| INV-NUM-01 (#079) | ✅ `verify_numeric_bounds.py` HIJAU | KN-079-NUM-BOUNDS-GAP (P1) ✅FIXED |
| INV-ENTITY-01 ext (#079) | ✅ `verify_nonfinancial_sweep.py` HIJAU | KN-079-IDOR-CREDIT-STATUS (P1) ✅FIXED |
| INV-AR-01 (baru #081) | ✅ `verify_data_integrity.py` GL-5 HIJAU | KN-076-AR-GL-DRIFT (P2) ✅FIXED |
| INV-DATA (COGS) | ✅ `verify_data_integrity.py` GL-4 HIJAU | KN-076-COGS-ZERO (P2) ✅FIXED |
| INV-UI-01 (Fase E) | ✅ `verify_modal_dismiss.py` HIJAU (26 cek) | KN-FASEE-UI-MODAL-CLOSE (P1) ✅FIXED · KN-FASEE-UI-SELECT-BLANK (P2) ✅FIXED · KN-FASEE-PREFILL-OUTPUT-NAME (P2) ✅FIXED · KN-FASEE-UI-GRID-GAP (P2) ✅FIXED |
| INV-RCV-01..03 (Fase F-1) | ✅ `verify_data_integrity.py` L4-RCV HIJAU (179/0/0) | KN-F1-KGBASE-GR (P1, **pra-ada**) ✅FIXED · KN-F1-PREVIEW-422 (P2) ✅FIXED |


---

## SESI 2026-08-06 — FASE G-6b (4 lanjutan Antar Entitas) · 4 bug NYATA

| ID | Sev | Inti masalah & bukti |
|---|---|---|
| **KN-FA-SALVAGE-UNDEF** | **P1** | `features/finance/FixedAssetsParts.jsx:77` memakai `salvage >= biaya` sementara variabelnya bernama `cost` — **sisa codemod bahasa** yang tidak selesai. Akibatnya validasi "Nilai residu" melempar `ReferenceError` dan tombol **Simpan** aset tetap terasa MATI tanpa pesan apa pun. Ditemukan lewat `oxlint no-undef` (bukan lewat uji fungsional — jalur itu hanya kena bila pengguna mengisi nilai residu). Perbaikan: identifier diseragamkan ke `biaya` (sesuai maksud codemod) sehingga `audit_i18n_id` juga ikut hijau. |
| **KN-G6-ELIM-FULL-MARGIN** | **P1** | Eliminasi konsolidasi G-6 menghapus **100% margin** antar-PT sebagai *unrealized profit* — benar selama barang masih di gudang pembeli, tetapi **SALAH begitu pembeli menjualnya ke pihak luar**: laba grup dilaporkan TERLALU KECIL, dan tidak ada layar yang bisa menjawab "berapa margin kami yang sudah nyata". Kelas bug **"invarian hijau tapi hampa"**: INV-IC-03 lama hanya memeriksa `Cr Persediaan == margin`, jadi ia ikut membenarkan angka yang salah. Perbaikan: rasio belum-terjual `u` dihitung dari **sisa panjang roll bertanda `cost_basis.interco_pair_id`** (data nyata), identitas eliminasi menjadi `Dr Pendapatan S · Cr HPP (S−M·u) · Cr Persediaan (M·u)` — identik dengan perilaku lama saat `u=1` sehingga data lama tidak berubah artinya. Invarian menghitung `u` lewat helper YANG SAMA (`interco_margin.unsold_ratio`) + membandingkan `g6_unsold_ratio` tersimpan. |
| **KN-G6-IDLE-FAKE** | P2 | "Umur saldo" antar-PT dihitung dari `interco_accounts.updated_at` — field yang ikut berubah setiap kali saldo **dihitung ulang**. Saldo yang menganggur berbulan-bulan bisa tampak baru (0 hari), sehingga pengingat settlement tak pernah menyala dan kalimat "menganggur N hari" tidak berarti apa yang ia katakan. Perbaikan: `last_activity_at` dari **aktivitas nyata** (tanggal dokumen terbuka & settlement terakhir pasangan PT itu), dipakai layar + job pengingat. |
| **KN-G6-POC-RESTORE-GAP** | P2 | POC G-6 membersihkan koleksi `interco_*` lalu memulihkannya, TETAPI belum mengenal koleksi turunan baru (`interco_returns`, faktur pajak internal, jurnal `interco_return`, tugas gudang retur). Akibatnya sesudah POC G-6 berjalan, retur & faktur pajak demo menunjuk transaksi yang sudah dihapus → **INV-IC-07 & INV-IC-08 memerah di `gate.sh --full`** walau produknya benar. Contoh nyata "gate merusak data" (pola yang sama dengan POC-RESIDU-01). Perbaikan: snapshot/restore diperluas ke 4 koleksi turunan itu. |

**Pelajaran proses:** dua POC fase yang menyentuh koleksi yang sama TIDAK boleh
dijalankan dalam SATU pemanggilan pytest (xdist menjalankannya paralel dan blok
bersih-bersih saling menimpa). `gate.sh` sudah memanggilnya sebagai gate terpisah;
kalau menjalankan manual, jalankan satu per satu.

---

## SESI 2026-08-14 — FASE G-6b (lanjutan) · **saldo antar-PT hilang saat dagang dua arah**

Titik masuk sesi: `gate.sh --full` MERAH pada satu gate — `POC FASE G-6b`
(`test_c1 … AssertionError: butuh satu pasangan PT dengan utang terbuka`), padahal
POC yang sama HIJAU 15/15 bila dijalankan sendiri. Kegagalan-saat-dijalankan-di-gate
itu ternyata sinyal cacat produk, bukan tes cerewet.

### KN-G6-ICA-CLOBBER — utang antar-PT MENGHILANG begitu dua PT berdagang dua arah
- Tanggal       : 2026-08-14
- Modul         : services/interco_service.py (`_update_account_balance`, `get_account`) ·
                  services/interco_money_service.py (`refresh_pair_exposure`) ·
                  services/interco_reminder.py · routers/interco.py
- Gejala        : Utang **CV Kanda Suka → PT Kain Suka Cita Rp 1.766.010** berubah menjadi
                  **Rp 0** dan lenyap dari layar *Saldo Antar-PT*, tanpa satu pun pesan,
                  hanya karena arah dagang sebaliknya dihitung ulang. Layar lalu berkata
                  "Saldo pasangan PT ini sudah nol" saat Keuangan menekan **Ingatkan**.
- Akar masalah  : id baris saldo dulu `ica_{X}_{Y}` **tanpa penanda peran**, sehingga
                  **piutang arah A→B dan utang arah B→A menempati SATU dokumen**.
                  `_update_account_balance(A,B)` menulis `ica_A_B`=piutang & `ica_B_A`=utang;
                  `_update_account_balance(B,A)` menulis dokumen yang SAMA dengan arti
                  terbalik → siapa pun yang jalan terakhir menang, yang lain hilang.
- Pemicu nyata  : (1) **Permintaan Internal** ("stok saya habis, kirim dari PT sebelah",
                  POC E-7d) menerbitkan transaksi arah balik; (2) **PINJAMAN & PINDAH ASET
                  antar-PT** — `refresh_pair_exposure` memanggil kedua arah BERURUTAN,
                  jadi panggilan kedua selalu menghapus hasil panggilan pertama. Satu draf
                  saja sudah cukup: tidak perlu ada uang yang berpindah.
- Perbaikan     : identitas baris memuat **arah dagang + peran** —
                  `ica_{penjual}_{pembeli}_ar` & `ica_{pembeli}_{penjual}_ap` — plus field
                  eksplisit `pair_key` (`penjual>pembeli`), `seller_entity_id/name`,
                  `buyer_entity_id/name`. `get_account(from,to,role)` kini WAJIB ber-peran
                  (bawaan `payable`: "berapa utang `from` kepada `to`"). Baris warisan tanpa
                  penanda peran dibuang saat arahnya dihitung ulang; migrasi idempotent
                  `scripts/migrate_g6b_ica_directional.py` (+`--dry-run`) untuk basis data lama.
- Invariant     : INV-IC-02 (diperkuat) · INV-IC-04 (diperkuat)
- Gate penangkap: `POC FASE G-6b` test `test_c4_dua_arah_dagang_tidak_saling_menimpa_saldo`
                  (bukti-merah: pada kode lama berbunyi *"utang Rp 1.766.010,00 tertimpa
                  menjadi Rp 0,00 …"*) · `verify_data_integrity` INV-IC-04
- Severity      : **P0** (uang hilang dari layar tanpa pesan)
- Status        : FIXED (bukti: `gate.sh --full` **HIJAU 54/54 dua kali berturut-turut** ·
                  POC G-6b **16/16** · POC G-6 **21/21** · POC E-7 **57/57** · integritas
                  **229 PASS / 0 FAIL / 0 WARN**)

### KN-G6-INV-HOLE-MISSING-ROW — invarian saldo hanya memeriksa baris yang ADA
- Tanggal       : 2026-08-14
- Modul         : scripts/verify_data_integrity.py (INV-IC-02, INV-IC-04)
- Gejala        : Pada keadaan uang-hilang di atas, seluruh invarian tetap **PASS 8 · FAIL 0
                  · WARN 0** (terbukti dengan menjalankan versi lama skrip pada keadaan itu).
                  Kelas bug "hijau tapi hampa": INV-IC-04 mengiterasi *baris saldo yang ada*
                  lalu membandingkannya dengan transaksi; baris yang **hilang** tidak pernah
                  diperiksa, dan baris yang tersisa memang konsisten dengan arah dagang lain.
                  INV-IC-02 pun mencari cermin hanya dari kebalikan `from`/`to`, sehingga dua
                  baris yang saling menimpa tetap tampak "berpasangan sama besar".
- Perbaikan     : (a) INV-IC-04 kini dipimpin **arah dagang dari transaksi**: setiap arah
                  yang punya dokumen terbuka WAJIB punya baris piutang DAN utang, dengan
                  nilai yang cocok — pesan merahnya menyebut nominal yang hilang.
                  (b) INV-IC-02 menjodohkan piutang↔utang lewat `pair_key` dan MEMERAH bila
                  dua baris beperan sama berbagi satu arah dagang.
- Invariant     : INV-IC-02 · INV-IC-04
- Gate penangkap: `verify_data_integrity` (kini memerah: *"arah ent_ksc→ent_kanda: baris
                  piutang HILANG padahal ada 2 dokumen terbuka bersisa 1.766.010,00"*)
- Severity      : P1
- Status        : FIXED (bukti: merah pada keadaan cacat, hijau setelah perbaikan)

### KN-E7-RESIDU-INTERCO — POC E-7 meninggalkan transaksi antar-PT setiap kali gate jalan
- Tanggal       : 2026-08-14
- Modul         : backend/test_core_e7_interco_poc.py · scripts/gate_residue.py
- Gejala        : POC E-7d mengubah Permintaan Internal menjadi transaksi antar-PT (draf)
                  dan hanya membatalkan permintaannya — dokumen kembar `KANDA/IC-#####`
                  tertinggal PERMANEN dan menumpuk satu per satu `gate --full`. Residu ini
                  tak pernah terlihat karena `gate_residue.py` belum memantau koleksi
                  antar-PT — dan justru residu inilah yang memicu KN-G6-ICA-CLOBBER di gate.
- Perbaikan     : POC E-7 mencatat `pair_id` yang ia buat dan **menghapus draf**-nya di blok
                  pembersihan (draf belum berjurnal & belum menggeser stok, jadi tak ada
                  jejak uang yang dirusak) + pemeriksaan `nol residu transaksi antar-PT`.
                  `gate_residue.py` WATCH ditambah `interco_transactions`,
                  `interco_settlements`, `interco_returns`. `interco_accounts` SENGAJA tidak
                  dipantau (tabel turunan yang wajar lahir sendiri; kebenarannya dijaga
                  INV-IC-04 yang kini memeriksa kelengkapan per arah dagang).
- Invariant     : INV-GATE-01
- Gate penangkap: `INV-GATE-01 anti-residu` + pemeriksaan CLEANUP di POC E-7
- Severity      : P2
- Status        : FIXED (bukti: POC E-7 **57/57** dengan "dihapus 2 draf · sisa 0" ·
                  gate penuh HIJAU dua kali berturut-turut tanpa drift)

**Pelajaran proses (BACA sebelum menyentuh saldo antar-PT):** identitas baris agregat
WAJIB memuat seluruh dimensi yang membentuknya. Di sini dimensinya ada dua — *arah dagang*
dan *peran buku* — dan menghilangkan salah satunya membuat dua fakta berbeda berebut satu
dokumen. Gejalanya bukan galat, melainkan **angka yang tenang-tenang salah**.

---

### KN-T-POC-RESIDU-STOK — POC FASE T menggeser stok setiap kali gate jalan (dan memerahkan G-6b)
- Tanggal       : 2026-08-19
- Modul         : backend/test_core_tahapan_poc.py · backend/poc_stock_guard.py
- Gejala        : Titik henti sesi sebelumnya "tampak bersih" (POC FASE T 62/62 · audit
                  `--fase T` SEMUA SELESAI), tetapi `gate.sh --full` MERAH **3**:
                  `INV-GATE-01` melaporkan `inventory_movements` +3 · `inventory_rolls` +2 ·
                  `inventory_lots` +1, dan POC `G-6b` gagal pada syaratnya sendiri
                  ("`FAIL 0` **dan** `WARN 0`") karena `verify_data_integrity` memunculkan
                  WARN **drift persediaan subledger vs GL 1-1300 Δ750.000**. Ketiga gate
                  merah itu SATU akar: langkah T2b menjalankan alur kain sungguhan
                  (`Issue` → `Terima Hasil`) yang MELAHIRKAN roll/lot/mutasi baru; blok
                  bersih-bersih POC hanya menghapus dokumen SPK, master tahap, dan roll
                  yang lot-nya memuat tag uji — mutasi & roll hasil terima tidak tersentuh.
                  Stok hasil terima itu tidak berjurnal (POC tidak menutup buku), jadi
                  persediaan subledger naik tanpa pasangan GL → WARN kuning.
- Kenapa lolos  : POC-nya sendiri berakhir "62 PASS · 0 FAIL" (ia memang tidak pernah
                  MEMERIKSA residu stok), dan checkpoint residu FASE POC dijalankan SETELAH
                  sidik jari kedua diambil — jadi residu dari blok guardrail runtime tak
                  pernah masuk hitungan POC. Kelas bug yang sama sudah pernah ditutup untuk
                  POC G-0..G-3 (POC-RESIDU-01) tetapi POC baru tidak mewarisi pengamannya.
- Perbaikan     : POC FASE T memakai `poc_stock_guard.snapshot_stock()` sebelum menulis dan
                  `restore_stock()` di blok CLEANUP (pemulihan EKSAK — memotong/menerima roll
                  tidak bisa dibalik per-dokumen), **plus satu pemeriksaan baru** di POC:
                  jumlah dokumen 4 koleksi stok sebelum == sesudah (jadi kalau kelak ada
                  jalur tulis baru, POC-nya sendiri yang memerah, bukan gate di ujung).
- Invariant     : INV-GATE-01
- Gate penangkap: `INV-GATE-01 anti-residu` + `T9` di POC FASE T
- Severity      : P2 (data demo & angka GL bergeser tiap gate; menutup 2 gate lain)
- Status        : FIXED (bukti: POC **63/63** dengan "stok dipulihkan EKSAK 195 dokumen" ·
                  `gate_residue --check` nol residu · `verify_data_integrity` 237 PASS/0
                  FAIL/**0 WARN** · `gate.sh --full` HIJAU 0 FAIL)

### KN-UI-PICKER-REOPEN — pop-up pemilih terbuka kembali setiap kali pengguna memilih (3 komponen × 9 layar)
- Tanggal       : 2026-08-19
- Modul         : frontend/src/components/{ProductSelect,MakloonSelect,PantoneFinder}.jsx
- Gejala        : Di Wizard Order Makloon (dan 8 form lain), memilih produk/mitra/warna
                  BERHASIL — tetapi pop-up pemilihnya **terbuka kembali** dengan kotak cari
                  kosong, seolah "tidak mau menutup". Lapisan pop-up itu lalu menutupi tombol
                  berikutnya (**Lanjut**), sehingga alur wizard terhenti. Nol galat, nol jejak
                  konsol; uji backend tetap hijau. Ditemukan saat mencoba menjalankan sendiri
                  user story FASE T di peramban (agen uji sebelumnya melaporkannya sebagai
                  "modal overlay issue" dan menyarankan uji manual).
- Akar masalah  : ketiga komponen adalah **pemicu + pop-up dalam satu komponen** dan dipakai
                  di dalam `<Field>` yang merender **`<label>`**. Aktivasi `<label>`
                  DITERUSKAN peramban ke kontrol yang dilabeli — yaitu tombol pemicunya
                  sendiri → `setOpen(true)` lagi. `e.stopPropagation()` di kartu pop-up tidak
                  menolong: React memasang pendengarnya di AKAR dokumen, sedangkan `<label>`
                  berada di antara target klik dan akar; dan aktivasi label adalah perilaku
                  PERAMBAN, bukan perambatan React.
- Perbaikan     : pop-up dirender lewat `createPortal(…, document.body)` (keluar dari subpohon
                  `<label>`). Tidak ada perubahan gaya/tata letak; tiga baris render.
- Invariant     : **INV-UI-09 (BARU)**
- Gate penangkap: `scripts/guardrails/verify_picker_portal.py` (+`--self-test` **16 kasus dua
                  arah**, termasuk 2 anti-tuduh-palsu untuk berkas yang sudah benar dan
                  pembuang komentar terpisah — penanda lapisan pop-up hidup di dalam
                  `className`, jadi `strip_comments_and_strings` tidak bisa dipakai apa adanya)
- Severity      : P1 (alur pembuatan SPK/PO/transfer/harga khusus terhenti di tengah)
- Status        : FIXED (bukti peramban: pop-up produk & mitra tersisa **0** sesudah memilih;
                  SPK `MKO-00006` ber-tahap Screen berhasil dibuat sampai selesai — 25 yard
                  masuk → **25 yard keluar**, "Tidak mengubah kain", ongkos Rp 750.000)

**Pelajaran proses:** dua penemuan sesi ini sama-sama datang dari **menjalankan sendiri**
alat & layar yang katanya sudah selesai — bukan dari membaca laporan. Angka "62/62 PASS"
dan "audit SEMUA SELESAI" tidak bisa melihat residu yang tidak pernah diperiksa, dan agen
uji UI melaporkan gejala ("modal tidak menutup") tanpa akar masalahnya. Yang menutup
keduanya: menjalankan gate dari nol, lalu MEREPRODUKSI di peramban.
