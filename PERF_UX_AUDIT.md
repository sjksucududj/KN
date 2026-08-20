# PERF & UI/UX AUDIT + RENCANA PERUBAHAN — KainNusantara ERP
**Tanggal:** 2026-07-23 · **Sifat:** VERIFIKASI (read-only) + RENCANA. Belum ada perubahan kode.
**Basis:** `scripts/ux_audit.py`, `scripts/audit_create_buttons*.py`, grep menyeluruh 220 file `features/*.jsx` + `backend/routers|services`.

---

## RINGKASAN TEMUAN (verifikasi)

### A. Tombol "Buat/Tambah +" yang tidak memunculkan pop-up
- **Tidak ada tombol yang benar-benar mati** (semua punya `onClick`). Masalahnya **KONSISTENSI UX** — ada 3 pola berbeda:
  | Pola | Jumlah | Contoh |
  |------|-------|--------|
  | ✅ MODAL / pop-up (target) | **31 view** | banyak view admin/finance/wms |
  | ⚠️ INLINE form (muncul di dalam halaman, bukan pop-up) | **15 view** | PurchaseReturns, CashManagement, SuppliersView, ChartOfAccounts, BudgetView, BankAccountsView, SupplierPriceList, ProcessRecipesView, MakloonsView, CustomerList, OmnichannelInteractions, PriceApprovals, OrgUnitsView, RfidDevicesView, WhatsAppRules |
  | ⚠️ NAVIGATE ke halaman/detail (bukan pop-up) | **7** | SalesHome (new-order), CycleCount, CashAdvancesView, SettlementsView, PurchaseRequisitions, SpecialOrders, SalesReturns |
- **Inilah yang dirasakan "tidak memunculkan pop-up"**: ~**22 alur create** memakai inline-form / navigate, bukan modal.

### B. Tabel tanpa paginasi & tidak dioptimalkan load  → **AKAR MASALAH PERFORMA**
- **Frontend:** hanya **3 file** menyinggung paginasi; **±198 view** merender tabel/list **penuh tanpa paginasi** (fetch semua baris → render semua).
- **Backend:** mayoritas endpoint list **tanpa** `limit/skip/page`; pakai `.to_list()` besar:
  `59× to_list(2000)`, `31× (5000)`, `29× (10000)`, `17× (20000)`, `7× (100000)`, `5× (50000)`.
  Endpoint inti kembalikan **array telanjang**: `products.to_list(100)`, `purchase-orders.to_list(300)`, `suppliers.to_list(500)`.
- **DB INDEX nyaris tidak ada** — hanya **4 index** (`sessions`×2, `login_attempts`, `products.sku`).
  Koleksi terpanas **tanpa index** pada field query umum → **full collection scan**:
  `inventory_rolls` (111 query), `sales_orders` (92), `products` (86), `purchase_orders` (61), `wms_tasks` (51),
  `inventory_movements` (29), `journal_entries` (30), `customers` (45), `vendor_bills` (38), dst.
- **Bundle FE = 3.0 MB satu file** `main.js`; **`React.lazy` = 0** (tak ada code-splitting) → initial load berat.
- `debounce` hanya di **3 file** (search memicu render tiap ketik).

### C. UI/UX melanggar aturan (guardrails / `ux_audit`)
- `ux_audit.py`: **9 ERROR / 7 file** (tabel tanpa **loading/empty** state, chart tanpa **empty-guard**):
  `PermissionMatrixRecords`, `WhatsAppSettings`, `EquityChangesTab`, `FinanceTowerParts`, `FinanceTowerView`,
  `FinancialStatementsParts`, `CheckoutStep3`. + **2 WARN** uang tanpa `tabular-nums` (`DocumentCenter`, `FinanceTowerView`).
- **`window.alert()` 40×** di **6 file** (WMS: InboundScan/OutboundScan/InventoryStock/TransferManagement, SettingsPanel, EscalationManagement) → wajib ganti `notice`/`ConfirmModal`.
- **`window.confirm()` ±20** perlu direview → `ConfirmModal`.
- Inkonsistensi create-UX (bagian A) = pelanggaran konsistensi komponen.

---

## RENCANA PERUBAHAN (bertahap, performa dulu, risiko-rendah dulu)

### FASE P1 — Fondasi performa Backend: **DB Indexes** (dampak terbesar, risiko UI ~0)
- Buat `ensure_indexes()` (dipanggil saat startup) untuk koleksi terpanas:
  - `inventory_rolls`: `{product_id,warehouse_id,owner_entity_id,status}`, `{status,length_remaining}`, `qc_task_id`, `po_id`, `created_at`.
  - `sales_orders`,`purchase_orders`: `{entity_id,status,created_at}`, `supplier_id/customer_id`, `po_number/so_number`.
  - `inventory_movements`: `{product_id,warehouse_id,timestamp}`, `roll_id`, `ref_id`.
  - `journal_entries`/`gl_*`: `{entity_id,date}`, `ref_id`.
  - `wms_tasks`: `{flow_type,status}`, `po_id`, `so_id`.
  - `customers`,`suppliers`,`vendor_bills`,`products`,`purchase_returns`,`sales_returns`, `audit_logs` (created_at TTL/plain).
- **Deliverable:** modul `backend/indexes.py` + panggil di startup; verifikasi via `explain()` (COLLSCAN→IXSCAN).

### FASE P2 — Paginasi server-side + komponen FE reusable
- **Kontrak paginasi baru** (butuh persetujuan): endpoint terpaginasi kembalikan
  `{ "items": [...], "total": N, "page": p, "page_size": s, "has_more": bool }` + param `?page=&page_size=&q=&sort=`.
  (Endpoint non-list tetap array telanjang → guardrail tetap terjaga.)
- **Backend:** helper `paginate(cursor, page, page_size)` + terapkan ke **list terpanas dulu**:
  inventory rolls & movements, sales_orders, purchase_orders, products, vendor_bills, journal/GL, audit_logs, customers, suppliers, purchase/sales returns. Turunkan `to_list` cap → gunakan `skip/limit`.
- **Frontend:** komponen `Pagination` + hook `usePagedList` (fetch page, loading/empty/error state, **debounced search**). Terapkan ke view terpanas dulu (mirror daftar di atas).
- **Deliverable per modul:** endpoint + view + `data-testid` (`<x>-page-next/prev`, `<x>-search`) + lolos `verify_api_contract`.

### FASE P3 — Optimasi load Frontend (bundle & render)
- **Code-splitting**: `React.lazy` + `Suspense` di `AppViewRouter.jsx` untuk view berat (finance, wms, analytics, hr, pos) → pecah bundle 3 MB.
- `useMemo`/`useCallback` untuk tabel berat; virtualisasi (windowing) untuk list sangat panjang bila masih perlu.
- **Deliverable:** ukuran `main.js` turun signifikan; chunk per-domain.

### FASE P4 — Konsistensi Create → **pop-up (modal)**
- Buat wrapper `FormModal` (di atas `components/ui/dialog`) sbagai standar.
- Konversi **15 view INLINE** → modal pop-up (pertahankan logika form yg ada).
- Evaluasi **7 alur NAVIGATE**: yang ringkas → modal; yang kompleks (mis. `SpecialOrders`) → tetap halaman (konfirmasi user).
- **Deliverable:** semua "+ Buat/Tambah" memunculkan pop-up konsisten (kecuali yang disepakati tetap halaman).

### FASE P5 — Perbaikan aturan UI/UX (agar `ux_audit` 0 ERROR)
- Tambah **loading/empty/chart-empty** state di 7 file ber-ERROR; `tabular-nums` di 2 WARN.
- Ganti **`window.alert`/`confirm`** → `notice bar` / `ConfirmModal` (6+ file).
- Jalankan gate FE: `esbuild`, `ux_audit`(0 ERROR), `verify_api_contract`, `validate_compliance`.

### FASE P6 — Verifikasi (WAJIB via `testing_agent_v3` tiap fase)
- Uji tiap modul yang disentuh: paginasi (next/prev/search), create-modal muncul & submit, tidak ada regresi, angka & state benar.

---

## URUTAN & PRIORITAS USULAN
1. **P1 (indexes)** — cepat, dampak besar, aman. 2. **P2 (paginasi)** per-modul terpanas. 3. **P3 (bundle)**.
4. **P4 (create modal)**. 5. **P5 (aturan UI/UX)**. Verifikasi (P6) menyertai tiap fase.

## KEPUTUSAN YANG DIBUTUHKAN DARI USER
- Setujui **kontrak paginasi** `{items,total,page,page_size,has_more}`? (default `page_size` 25/50?)
- Modul mana didahulukan untuk paginasi?
- `SpecialOrders`/create kompleks: tetap halaman atau paksa modal?

---

## STATUS IMPLEMENTASI (progress log)

**Keputusan user (disetujui):** urutan P1→P2→P3→P4→P5; kontrak paginasi
`{items,total,page,page_size,has_more}` + `?page=&page_size=&q=&sort=`;
default page_size **20**; urutan modul terpanas bertahap; alur create kompleks tetap halaman.

### ✅ P1 — DB Indexes (SELESAI, terverifikasi)
- `backend/indexes.py` → `ensure_performance_indexes()` dipanggil di `bootstrap.run_bootstrap()`.
- 75+ index (compound + single) untuk 25 koleksi terpanas (inventory_rolls, inventory_movements,
  sales_orders, purchase_orders, wms_tasks, journal_entries, gl_*, vendor_bills, customers,
  suppliers, products, returns, audit_logs, notifications, dll).
- Idempotent & non-fatal. Verifikasi: query `inventory_rolls` kini **IXSCAN** (dulu COLLSCAN).

### ✅ P2 — Server-side Pagination (INFRA + 5 view, terverifikasi 100% oleh testing agent)
- Infra: `backend/pagination.py` (is_paged/get_page_params/build_search/fetch_page/envelope),
  `frontend/src/hooks/usePagedList.js` (debounce+guard urutan respons), `components/PaginationBar.jsx`.
- **OPT-IN & backward compatible**: endpoint balikan envelope hanya bila `?page/?page_size` ada;
  tanpa itu tetap array telanjang (konsumen lama + gate `verify_api_contract` aman).
- Endpoint ter-paginasi: `/inventory/rolls`, `/inventory/movements`, `/purchase-orders`,
  `/vendor-bills`, `/suppliers`, `/customers`, `/purchase-returns`, `/sales-returns`, `/audit-logs`
  + endpoint agregasi `/vendor-bills/status-counts` (jaga badge tab tanpa fetch semua).
- View ter-migrasi: InventoryStockView (tab Rolls & Ledger), CustomerList, SuppliersView,
  PurchaseOrderManagement, VendorBillsView. Search server-side + PaginationBar + loading/empty.
- **SISA P2 — SELESAI 2026-08-17** (4 modul terakhir):
  · **Retur Jual** & **Retur Beli** → `usePagedList` + `PaginationBar` + pencarian
    server; lencana tab/kartu ringkasan pindah ke endpoint agregat BARU
    `/sales-returns/status-counts` & `/purchase-returns/status-counts` — kalau lencana
    dihitung dari isi halaman, angkanya diam-diam menyusut mengikuti halaman
    ("kartu bilang 12, daftar berisi 3").
  · **Pesanan (OrdersView)** → daftarnya kini dipaginasi & dicari di server; kartu
    ringkasan 7 angka memakai `/sales-orders/stats/summary` (+ field baru
    `backorder_count`). Tab **Dasbor & Analitik** SENGAJA tetap memakai daftar penuh dari
    `/dashboard`: analitik yang hanya melihat satu halaman akan bercerita salah.
    Setiap aksi (setujui/konfirmasi/batal/bayar) dibungkus agar HALAMAN yang sedang
    dibuka ikut dimuat ulang — tanpa itu barisnya tetap memperlihatkan status lama.
  · **Jurnal GL** → `gl_service.list_entries_paged()` + pencarian
    (nomor/keterangan/sumber). Sebelumnya daftar dipotong keras di **500 baris tanpa
    halaman berikutnya**, jadi entri ke-501 tak bisa dijangkau dari layar sama sekali —
    padahal `journal_entries` koleksi yang tumbuh paling cepat.
  Semua tetap **OPT-IN**: tanpa `?page/?page_size` bentuk responsnya tidak berubah
  (array telanjang / `{items,total}` seperti sebelumnya), sehingga konsumen lama &
  `verify_api_contract` tetap aman. Diverifikasi di peramban: Jurnal GL
  `Hal 1/6 → Hal 2/6` mengirim `?page=2&page_size=20`, ukuran halaman 50 bekerja,
  pencarian Pesanan "Butik" → `1–3 dari 3`.

### ✅ P3 — Code-splitting (SELESAI, terverifikasi)
- `AppViewRouter.jsx`: semua view feature → `React.lazy()` + satu `<Suspense>` (fallback ViewLoader).
- Hasil: **main.js 3.0MB → 892KB (-70%)**, 85 chunk on-demand. Uji nav PO/GL/WMS/Sales/HR:
  nol console/page/chunk error.

### ✅ P4 — Create jadi modal (**SELESAI 2026-08-17**, terverifikasi agen uji 10/10 user story)
- **Standarnya**: `frontend/src/components/FormModal.jsx` — kepala menempel (judul+subjudul+tutup),
  badan bisa di-scroll, kaki menempel (Batal/Simpan), **Esc menutup**, scroll halaman di belakang
  dikunci, fokus otomatis ke isian pertama, **galat tampil DI DALAM modal** (bukan `alert`), dan
  backdrop memakai `overlayDismiss()` → **INV-UI-01 tetap hijau** (memilih opsi dropdown ber-portal
  Radix TIDAK menutup modal; diuji langsung di layar Transfer Gudang).
  Bila isinya sudah komponen ber-`<form>` sendiri, `FormModal` **tidak** membungkusnya lagi
  (anti "form di dalam form" → agen uji: nol `validateDOMNesting`).
- **10 layar dikonversi** (logika form tidak diubah, hanya wadahnya): Supplier · Daftar Harga
  Supplier · Kebijakan Retur · Unit Organisasi (HRD) · Kas · Retur Beli · **Retur Jual** (dulu
  MENUKAR seluruh halaman) · Aturan Persetujuan · Transfer Gudang · Master Data (AdminView).
- **Terukur** (`scripts/audit_create_modal.py`): create **inline 12 → 0** · modal **36 → 44** ·
  navigate **7** (tetap halaman, keputusan pemilik) · **tombol mati 0**.
- Ikut dibereskan: label tombol yang berbunyi *"Tutup Form"* (tak masuk akal untuk pop-up) di
  Retur Beli & Kas; `AdminView` kini tombolnya **selalu terlihat** (dulu hilang saat form terbuka)
  dan daftar Records tidak lagi terhimpit kolom 360px.
- **Gate baru `INV-UI-05`** (`scripts/audit_create_modal.py`, + `--self-test` 7 kasus bukti-merah)
  terdaftar di `gate.sh`: create **inline baru** / **pindah halaman tanpa keputusan tercatat** /
  **tombol mati** = MERAH; pengecualian wajib ber-ALASAN tertulis. Penjaga ini juga diperbaiki dua
  kali saat dibuat karena sempat **menuduh palsu** (7 layar yang sudah benar terbaca "inline" hanya
  karena nama komponen pop-up ditulis sebelum `open={state}`; `setForm({…})` disalahartikan sebagai
  "membuka pintu") — penjaga yang menuduh palsu akan dimatikan orang.
- Bukti: `gate.sh --full` **71 gate HIJAU / 0 FAIL** · `ux_audit` tidak bertambah buruk
  (22 ERROR / 17 berkas, sama seperti sebelum P4 — itu backlog P5) · konsol browser **0 error**.
### ✅ P5 — Aturan UI/UX (**SELESAI 2026-08-17**, lanjutan sesi P4)

> Keputusan pemilik untuk fase ini: **(a)** galat/gagal = **bilah pesan MENEMPEL**
> (ditutup manual) · berhasil = **toast** yang hilang sendiri; **(b)** aksi berdampak
> **uang/stok WAJIB beralasan** tertulis, sisanya cukup Ya/Batal.

**P5.0 — Angka dokumen ini diukur ulang lebih dulu, dan ternyata salah dua kali:**
- Dokumen menyebut `alert` **40×** & `confirm` **~21×**. Hitungan sebenarnya dari kode:
  **`alert` 36 · `confirm` 21 · `prompt` 4 = 61 dialog di 21 berkas.** `prompt()`
  tidak pernah masuk daftar padahal salah satunya (`AccountList`) memakai kotak bawaan
  peramban untuk **kata sandi baru tanpa penyamaran karakter**.
- Gate P4 melaporkan create-inline **0**. Nyatanya masih **3** (Buat PO · Ajukan Harga
  Khusus · Tambah Stok Awal): detektornya buta terhadap form yang isiannya dipindah ke
  **berkas ANAK** (`<POCreateForm/>` dll) — ia mencari `<input>` di berkas induk saja.
  Detektor diperbaiki (menelusuri satu lapis ke komponen anak, + 5 kasus self-test baru),
  lalu ketiga form dikonversi → **inline 0 (kali ini terukur benar)**.

**P5.1 — 61 dialog peramban dihapus, diganti satu standar**
- `services/confirmService.js` + `components/ConfirmHost.jsx` (satu instansi di root,
  pola sama seperti `use-toast` yang sudah dipakai repo): `askConfirm()` → Ya/Batal ·
  `askReason()` → **menuntut alasan** · `askText({inputType:"password"})` → isian satu
  baris/kata sandi tersamarkan. Nilai kembali dibuat beda tipe (`boolean` vs
  `string|null`) supaya batal & "lanjut tanpa alasan" **mustahil tertukar**.
- `utils/feedback.notifySuccess()` untuk kabar berhasil. **Sengaja tidak ada
  `notifyFailure()`**: bila ada jalan mudah melaporkan kegagalan lewat toast yang hilang
  sendiri, kegagalan akan dilaporkan begitu — persis kebiasaan yang sedang dihapus.
- `ErrorNotice` kini **menggeser dirinya ke dalam pandangan** (`scrollIntoView`
  `block:"nearest"`): bilah yang menempel di atas halaman panjang tadinya "ada tapi tak
  terlihat" saat operator bekerja di bagian bawah — sama saja dengan senyap.
- Galat yang muncul **di dalam pop-up**-nya sendiri (bukan di bilah halaman yang justru
  tertutup pop-up itu): pop-up eskalasi Barang Masuk/Keluar, pop-up penyelesaian
  Eskalasi, modal detail Transfer (Setujui/Tolak/Batal), form Buat Transfer & Stok Awal.

**P5.1b — Alasan yang diminta BENAR-BENAR disimpan** (menanyakan lalu membuangnya hanya
mengajari pengguna mengarang jawaban). 5 endpoint diberi `reason` (opsional di API, wajib
di layar) yang tersimpan di dokumen &/atau Jejak Audit: batal transfer
(`cancelled_reason`) · void kwitansi AR (`voided_reason`) · hapus entri eliminasi
konsolidasi · hapus tarif insentif · posting true-up persediaan.
**Temuan ikutan:** pembatalan kwitansi AR (yang MEMBALIK uang masuk pada order + kas +
deposit) sebelumnya **tidak menulis satu baris pun ke `audit_logs`** — baik di router
maupun service. Sekarang dicatat.

**P5.2 — `ux_audit` dibuat jujur dulu, baru dipatuhi**
- Dari **22 "ERROR"** yang dilaporkannya, **17 tuduhan palsu**: komponen PENAMPIL (data
  dari props, `axios` = 0) dituduh "tanpa loading" padahal induknya memang yang punya
  skeleton; penjaga `length > 0` / `hasLines` / pesan kosong di komponen anak tak
  dikenali; kata "posting"/"loading" di **kalimat JSX** dihitung sebagai bukti adanya
  indikator (`PeriodUnlockCard` lolos padahal `return null`); nama state berimbuhan
  (`loadingDaily`) tak dikenali; dan W1 kehilangan kata **"kolom"** dari standarnya
  sehingga 28 berkas ditandai hanya karena menyebut nominal **di dalam kalimat**.
- Detektor dibuat **sadar-rujukan** + diberi **`--self-test` 16 kasus dua arah** (harus
  memerah untuk gap nyata, TIDAK boleh menuduh komponen penampil). Pembersih
  komentar/string dipindah ke `guardrails/_common.py` — satu implementasi untuk semua
  penjaga, karena dua penjaga berbeda sudah pernah tertipu teks yang bukan kode.
- **5 gap NYATA lalu diperbaiki** (semuanya "tidak ada data = halaman kosong tanpa satu
  kalimat pun"): Dasbor Keuangan · Perubahan Ekuitas (tabel **dan** grafiknya) · matriks
  izin · kartu Buka Periode yang melompat masuk tanpa kerangka. Hasil: **0 ERROR**.
- Sisa **9 WARN** = `<select>` bawaan (bukan komponen Select) di 8 berkas → backlog
  tercatat, bukan diam-diam dilewati.
- `ux_audit --strict` + self-test-nya **kini terdaftar di `gate.sh`** (sebelumnya audit
  ini hanya dijalankan manual, tanpa self-test, jadi angkanya tak pernah dibuktikan
  bisa memerah dan tak ada yang mencegahnya memburuk).

**P5.3 — Gate baru `INV-UI-06`** (`scripts/guardrails/verify_blocking_dialogs.py`):
`alert(`/`confirm(`/`prompt(` bawaan peramban = **MERAH**, dan `<ConfirmHost/>` wajib
ter-mount di root (tanpa itu penggantinya gagal SENYAP → semua tombol hapus/batalkan
tampak mati). `--self-test` **17 kasus**, termasuk anti-tuduh-palsu untuk dua kasus NYATA
di repo ini: label `"1 pesan per alert (real-time)"` (kata di dalam string) dan
`async function confirm()` (fungsi yang kebetulan senama). **Bukti-merah:** dijalankan
pada kode SEBELUM P5 → **61 pelanggaran di 21 berkas + `<ConfirmHost/>` hilang**, keluar
kode 1; pada kode sesudah → 0.

**Bukti penutup P5:** `gate.sh --full` **75 gate HIJAU / 0 FAIL** (271s) · agen uji
**backend 11/11 · frontend 0 bug UI**, syarat kritis "tidak ada dialog peramban"
**LULUS** · verifikasi tangan: dialog alasan batal transfer muncul **di atas** modal
detail, tombol konfirmasi **mati sampai alasan diisi**, Esc & Batal menutup · residu data
uji dibersihkan (`gate_residue --check` **nol residu**).

---

## §P6 — DROPDOWN SERAGAM & UNDUH CSV PER DAFTAR BERHALAMAN (sesi 2026-08-18)

> Pilihan pemilik: 2 dari 6 usulan → **(a) Dropdown Seragam** + **(c) Unduh Per Halaman**.
> Keputusan detail pemilik: cakupan unduhan **ditanyakan ke pengguna** ("Halaman ini" /
> "Semua hasil filter"), berkas memakai **pemisah `;` + BOM UTF-8** (Excel Indonesia).
> Titik henti P5 diverifikasi ulang dari nol lebih dulu: **75 gate HIJAU / 0 FAIL**.

### P6.1 Angka warisan diukur ulang — dan lagi-lagi salah
`plan.md §STATUS P5` menulis "**9 WARN** `<select>` bawaan di **8 berkas**". Nyatanya
**13 dropdown di 9 berkas**: `ux_audit` melaporkan **satu WARN per BERKAS**, bukan per
dropdown, jadi "9" itu jumlah berkas dan pekerjaannya **44% lebih banyak** dari catatan.
(Pola yang sama seperti P5, di mana "alert 40× & confirm 21×" ternyata 61 dialog.)

### P6.2 Satu hal yang HAMPIR hilang tanpa disadari saat konversi
`NotificationCenter` memberi `aria-label="Filter jenis notifikasi"` pada `<select>`-nya.
`KNSelect` belum meneruskan prop itu → konversi naif akan **menghapus nama kontrol bagi
pembaca layar** tanpa satu pun gate memerah. Pass-through `aria-label` ditambahkan lebih
dulu (aditif, aman bagi 182 pemakai lama), lalu diverifikasi di peramban: elemennya kini
`BUTTON` dengan `aria-label` utuh, **plus** kotak pencarian yang `<select>` bawaan tak
pernah bisa berikan.

### P6.3 Penjaga baru dibuat jujur DULU, baru dinaikkan
Rumah aturan "native `<select>`" sudah ada (`ux_audit` W2) dan sudah jadi gate sejak P5,
jadi menulis penjaga KEDUA untuk hal yang sama akan melahirkan dua tempat yang bisa
berbeda. W2 dinaikkan **WARN → ERROR (kode `E4`)** — tapi baru **setelah** detektornya
diperbaiki. Bukti bahwa perbaikan itu perlu, dan bukan formalitas: begitu 13 konversi
selesai, `<select` di seluruh `frontend/src` tinggal **1**, dan satu-satunya itu ada
**di dalam komentar `components/KNSelect.jsx` sendiri** — berkas yang justru menjadi
penggantinya. Detektor teks-mentah **menuduh palsu berkas yang benar**; penjaga seperti
itu "diperbaiki" orang dengan cara menghapus penjelasannya. Sekarang membaca sumber yang
komentar & string-nya sudah dibuang, **+5 self-test** (total 21) termasuk kasus nyata itu.
Hasil: `ux_audit --strict` **0 ERROR · 0 WARN** (dari 0 ERROR · 9 WARN).

### P6.4 Unduh CSV dipasang di SEAM yang sudah ada, bukan 12 salinan
`hooks/usePagedList.js` (+`fetchAll`) & `components/PaginationBar.jsx` (+tombol Unduh)
adalah dua berkas yang sudah dipakai SEMUA daftar berhalaman, jadi 12 pager hanya
menyetor definisi kolomnya. **Endpoint ekspor baru di backend sengaja DITOLAK**: itu
melahirkan **dua sumber kebenaran untuk satu filter**, dan begitu keduanya menyimpang
berkas unduhan berisi jumlah baris yang **berbeda dari yang dilihat pengguna** — tanpa
ada yang tahu sampai seseorang menyelisihkan angkanya. Dengan menyusuri **endpoint daftar
yang sama memakai params yang sama**, paritas filter bukan hal yang harus dijaga: ia
**mustahil melenceng**. Terbukti pada 8 daftar: baris berkas == angka "… dari N" **persis**
(jurnal 105 · roll 59 · mutasi 52 · lot 32 · PO 14 · akun 10 · tagihan 8 · pelanggan 5 ·
retur beli 3).

Dialognya **dilewati bila kedua pilihan identik** (semua hasil filter sudah tampil di satu
halaman) — menanyakan pertanyaan yang tak punya dua jawaban hanya menambah satu klik.
`askChoice()` ditambahkan ke standar dialog P5 yang sama, bukan sebagai cara ke-22.

### P6.5 Gate baru `INV-UI-07` — MENJALANKAN kodenya, bukan membaca polanya
`scripts/guardrails/verify_list_export.py`: (A) setiap `<PaginationBar>` wajib menyetor
`exportConfig`; (B) `utils/csvExport.js` wajib lulus **20 uji PERILAKU yang dijalankan
dengan Node**. Lapis (B) ada karena semua kerusakan CSV bersifat **perilaku, bukan pola
teks** — dan semuanya SENYAP: pemisah `,` membuat Excel Indonesia menumpuk semua kolom di
kolom A; sel bermuatan `;`/kutip yang tak dibungkus **menggeser seluruh kolom di kanannya**
(angka pindah kolom: tetap bisa di-SUM, hasilnya salah) sementara barisnya tampak wajar;
desimal titik dibaca sebagai TEKS; sel diawali `=`/`+`/`@` **dieksekusi Excel**. Angka
negatif sengaja TIDAK diberi kutip pelindung — daftar keuangan penuh `-1500000`, dan
obatnya akan lebih merusak dari penyakitnya. Self-test 15 kasus termasuk **bukti-merah
lapis perilaku** (util CSV yang pemisahnya diganti `,` harus membuat gate memerah —
tanpa bukti itu, "20 kasus lulus" bisa berarti Node tak pernah jalan).

### P6.6 Dua bug NYATA ikut tertangkap (keduanya bukan bagian dari permintaan)
1. **Label Inggris yang selama ini tak terlihat gate.** `StoreCreditView` menampilkan
   "— outstanding Rp …". Sebelumnya lolos `audit_i18n_id` karena teksnya **terpotong
   antar-ekspresi JSX**; setelah konversi menjadikannya satu template literal, gate
   langsung memerah. Diterjemahkan → "belum lunas".
2. **Widget mengapung yang MENELAN klik** (backlog P5 #6, akhirnya diukur & diperbaiki).
   Agen uji melaporkan "paginasi Jurnal GL rusak". Bukan rusak:
   `document.elementFromPoint()` di titik tengah tombol "Berikutnya" mengembalikan
   **`BUTTON data-testid="help-tours-button"`** — kliknya benar-benar ditelan widget
   "Bantuan & Panduan" (`position: fixed`, kanan-bawah). Yang gagal bukan fungsinya
   melainkan **kemampuan menekannya**, dan tak ada galat apa pun yang menjelaskannya.
   Perbaikan: `#main-content { padding-bottom: 104px }` — isi halaman **selalu** bisa
   digulir melewati widget, untuk semua halaman sekarang & nanti (mengecilkan widget
   hanya menyusutkan peluang tabrakan, tidak menghapusnya). Diverifikasi pada keadaan
   terburuk (digulir ke dasar): ketiga kontrol pager kini mengembalikan **dirinya sendiri**
   dari `elementFromPoint`, dan klik KETAT (tanpa `force`) memindahkan `Hal 1/6 → 2/6`.
   Tanpa perbaikan ini, tombol **Unduh CSV** yang baru — yang duduk di bilah yang sama —
   akan ikut tertelan.

**Bukti penutup P6:** `gate.sh --full` **77 gate HIJAU / 0 FAIL / 0 SKIP** (+2 gate baru) ·
`ux_audit --strict` **0 ERROR 0 WARN** · `<select` bawaan di `frontend/src` = **0** ·
12 daftar berhalaman punya Unduh CSV · agen uji 2 ronde → ronde-2 **0 bug UI** (23/24,
sisanya jalur navigasi yang saya verifikasi sendiri) · konsol peramban **0 error** ·
unduhan nyata diperiksa byte-nya (BOM `EF BB BF`, pemisah `;`, jumlah baris == angka pager).

---

## §P7 — PANEL RINCIAN JADI POP-UP (9 LAYAR) & 7 KEBOCORAN ID ENTITAS (sesi 2026-08-18)

> Keluhan pemilik, dilaporkan **berulang kali**: *"ketika klik malah memunculkan dibawah
> bukan popup, ini ux nya sangat buruk karena kalau table ini bisa jauh sekali dibawah
> membuat user bingung saat navigasi … cek masih adakah halaman lain dengan ui ux seperti
> ini, karena ini harus diubah"*.

### P7.1 Kenapa ini bisa lolos berkali-kali
FASE P4 sudah mewajibkan pop-up — tetapi **hanya untuk tombol "Buat/Ubah"**
(`INV-UI-05`). Kelas bug yang SAMA untuk **panel rincian** tidak dijaga siapa pun, jadi
setiap kali dilaporkan ia diperbaiki satu layar, lalu muncul lagi di layar lain. Yang
hilang bukan perbaikannya, melainkan **penjaganya**.

### P7.2 Sebarannya diukur — dan detektor saya sendiri berbohong DUA kali
Angka berubah **5 → 3 → 13** sebelum benar, karena dua kesalahan yang saya buat sendiri:
1. **Menuntut `onClick` memanggil setter-nya langsung.** Nyatanya pemilihan baris hampir
   selalu lewat handler perantara (`openDetail(id)`). Akibatnya `ARAgingView` — **layar
   yang justru dilaporkan pemilik** — tidak terdeteksi sama sekali.
2. **Mencari nama kelas CSS (`divide-y`, `grid-cols-…`) di sumber yang STRING-nya sudah
   dibuang.** Nama kelas hanya hidup di dalam string, jadi penandanya selalu hilang dan
   5 layar lolos. Pelajaran: **konstruksi KODE dinilai dari sumber terstrip, penanda TEKS
   dari sumber MENTAH.** Keduanya kini menjadi kasus self-test.

Setelah detektornya jujur + klasifikasi induk berbasis **indentasi** (bukan "grid terdekat
di atas", yang keliru menangkap grid KOLOM BARIS): **9 layar** merender rincian di bawah
daftar, **4 layar** memang master-detail 2 kolom (rincian di SAMPING daftar, tetap dalam
pandangan) → sengaja **tidak** diubah.

| Diubah jadi pop-up (9) | Dibiarkan (2 kolom, 4) |
|---|---|
| AR/Piutang · Kas & Bank · Store Credit · Antar-PT · Landed Cost · RFQ · Tagihan Supplier · R&D Sample · R&D Spesifikasi | Pusat Kasus Keuangan · Kontrabon · Amandemen · Inbound Scan |

### P7.3 Shell baru sengaja TANPA kepala sendiri
`components/DetailModal.jsx` hanya menyediakan **lapisan + posisi + perilaku** (Esc,
`overlayDismiss()` per INV-UI-01, kunci scroll latar, `role="dialog"`). Kesembilan panel
sudah punya `section-head` sendiri dengan judul, nominal, dan tombol aksi kontekstual;
menambahkan kepala lagi akan menghasilkan **dua judul & dua tombol tutup**. Konsekuensinya
konversi tiap layar = **satu pembungkus**, isi panel tak disentuh → risiko kecil.

### P7.4 Gate baru `INV-UI-08`
`scripts/guardrails/verify_detail_modal.py`: rincian yang dipicu klik baris wajib
**pop-up** ATAU **berdampingan 2 kolom**. Menelusuri ke **berkas ANAK** (panel yang
overlay-nya ada di berkas lain) dan sadar-indentasi. Self-test **19 kasus**, termasuk dua
kasus yang detektornya PERNAH lewatkan sendiri. **Bukti-merah:** dijalankan pada kode
sebelum P7 → **tepat 9 pelanggaran**; sesudah → 0 (19 panel diperiksa: 15 pop-up ·
4 berdampingan).

### P7.5 Temuan ikutan: 7 tempat mencetak `ent_ksc` ke layar
Terlihat langsung pada tangkapan layar verifikasi saya (kolom "Entitas" Store Credit
berisi **`ent_ksc`**). Padahal `utils/entityLabel.js` sejak awal berbunyi *"JANGAN PERNAH
menampilkan `entity.id`"*, dan `INV-UI-02` sudah menjadi gate. Sebabnya: seluruh polanya
hanya menangkap `entity_id` yang dipakai sebagai **CADANGAN** (`nama || entity_id`) —
`entity_id` yang dicetak **LANGSUNG** tidak tertangkap sama sekali. 7 tempat: Store Credit
(kolom Entitas) · Transfer Gudang (PT Sumber, PT Tujuan, "Pemilik:", + 2 baris jurnal
antar-PT) · Cycle Count ("Pemilik:").
Perbaikan: helper baru `entityShortFromCtx()` (untuk tempat tanpa prop `entities`, mis. di
dalam *template literal*) + `<EntityBadge>`. Pola guard diperluas ke dua bentuk baru
(JSX langsung & template literal) dengan penolakan eksplisit terhadap **penerusan prop,
key React, penyusunan URL, kunci dedup, dan `data-testid`** — lima bentuk sah yang sempat
dituduh palsu saat pola pertama terlalu longgar. **Bukti-merah: 7/7** pada kode lama.

**Bukti penutup P7:** `gate.sh --full` **79 gate HIJAU / 0 FAIL / 0 SKIP** (+2 gate baru) ·
agen uji **0 bug UI** (14/14 skenario) · verifikasi tangan: **7 dari 9 pop-up** dibuka
dengan klik nyata (2 sisanya tanpa data demo), rincian AR muncul di **y=400 px** dari
viewport 1080 px **tanpa halaman bergeser**, Esc & klik backdrop menutup, dan rincian
**tidak lagi dirender ganda** di bawah tabel · `ent_` mentah di layar = **0** ·
konsol peramban **0 error**.
