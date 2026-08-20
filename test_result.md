#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data.
# The testing data must be entered in yaml format Below is the data structure:
#
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================
## user_problem_statement: |
  Lanjutkan development repo ajajaabahayaja/KN (ERP/WMS Kain Nusantara). Titik henti:
  bug parsing angka CSV (pemisah ribuan Indonesia vs titik desimal) pada Daftar Harga
  per Pelanggan. Keputusan pemilik sesi ini:
  (1) harga khusus pelanggan WAJIB persetujuan manajer bila di bawah harga PT/HPP dan
      logikanya HARUS SAMA dengan fitur Harga Khusus yang sudah ada (jangan duplikasi);
  (2) POS memakai harga langganan otomatis begitu kasir memilih pelanggan, bawaan harga PT;
  (3) hak akses: admin/manager kelola, sales hanya lihat;
  (4) format CSV bawaan (sku;nama_produk;harga_pelanggan;berlaku_dari;berlaku_sampai;catatan).

## backend:
  - task: "F1b — Daftar Harga per Pelanggan: CRUD + grid + histori + quote + CSV"
    implemented: true
    working: true
    file: "backend/routers/customer_prices.py, backend/services/customer_price_service.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "POC /app/test_core_customer_pricelist.py 86/86 lulus. Grid membawa global/PT/pelanggan/khusus/efektif + pending. Bug parsing angka CSV DIPERBAIKI & diuji: '255.000'→255000, '255.000,50'→255000,5, '255000.75'→255000,75, '1.265.400'→1265400."

  - task: "F1b — Penjagaan harga: di bawah harga PT/HPP wajib persetujuan (pakai mesin price_approvals yang SUDAH ADA)"
    implemented: true
    working: true
    file: "backend/services/price_guard_service.py, backend/services/price_approval_service.py, backend/routers/price_approvals.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "SATU definisi batas bawah (price_guard_service) dipakai Daftar Harga per Pelanggan DAN layar Harga Khusus. Record di bawah batas → status pending_approval + pengajuan price_approvals (source=customer_pricelist). Approve → record aktif; reject → rejected. SoD: pengaju tidak boleh menyetujui sendiri (403). 3 kunci config baru di Pusat Pengaturan grup Harga/Diskon."

  - task: "F1b — resolver harga terpadu (khusus → pelanggan → PT → umum) untuk SO & POS"
    implemented: true
    working: true
    file: "backend/services/customer_price_service.py (resolve_many), backend/routers/sales_orders.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "GET /api/customer-prices/quote memakai resolver yang sama dengan create_order. Baris SO menyimpan snapshot price_source + price_record_id. include_special=false menjaga kontrak lama SO (harga khusus hanya dipakai bila price_approval_id dikirim)."

## frontend:
  - task: "Layar baru 'Daftar Harga per Pelanggan' (nav cs-price-list, sebelumnya Segera Hadir)"
    implemented: true
    working: "NA"
    file: "frontend/src/features/sales/CustomerPricelistView.jsx (+ customerPricelist/*)"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "Grid per produk + pilih pelanggan/entitas + cari + filter 'hanya yang punya harga', pita kebijakan penjagaan, KPI, modal Tetapkan Harga (peringatan batas bawah live dari /customer-prices/floor), modal Riwayat, modal Impor CSV, Ekspor CSV, tautan ke Persetujuan Harga. Verifikasi visual mandiri sudah dilakukan (render + peringatan persetujuan muncul)."

  - task: "POS/keranjang memakai harga efektif pelanggan (1 panggilan) + lencana sumber harga"
    implemented: true
    working: "NA"
    file: "frontend/src/hooks/useEffectivePrices.js, features/sales/SalesPortal.jsx, features/pos/CheckoutDrawer.jsx, components/CartPanel.jsx, components/ProductQuickView.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "Dulu 40 panggilan /price-approvals/effective per render dan harga dasar tetap harga UMUM (beda dari yang disimpan server). Sekarang satu panggilan /customer-prices/quote; lencana 'Harga pelanggan' / 'Harga khusus'; qty minimum aturan khusus dihormati per baris."

  - task: "Lencana sumber harga di baris Pesanan (SO) + asal pengajuan di Persetujuan Harga"
    implemented: true
    working: "NA"
    file: "frontend/src/features/orders/OrderDetailPanel.jsx, features/sales/priceApprovals/PriceApprovalCard.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "Baris SO menampilkan price_source. Kartu Persetujuan Harga menampilkan lencana 'Daftar Harga Pelanggan', snapshot batas bawah/HPP, dan status baru (Digantikan/Dibatalkan)."

## metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 1
  run_ui: true

## test_plan:
  current_focus:
    - "Layar baru 'Daftar Harga per Pelanggan' (nav cs-price-list, sebelumnya Segera Hadir)"
    - "F1b — Penjagaan harga: di bawah harga PT/HPP wajib persetujuan (pakai mesin price_approvals yang SUDAH ADA)"
    - "POS/keranjang memakai harga efektif pelanggan (1 panggilan) + lencana sumber harga"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

## agent_communication:
    -agent: "main"
    -message: |
      Fase 2 (F1b Daftar Harga per Pelanggan) selesai dibangun BE+FE. Bukti mandiri:
      POC 86/86 · gate.sh HIJAU · verify_api_contract 0 ERROR/0 WARN · build FE bersih.
      Kredensial demo: admin@kainnusantara.id / manager@kainnusantara.id /
      sales@kainnusantara.id / warehouse@kainnusantara.id — password demo12345.
      Data demo sudah ada: pelanggan "Toko Kain Sejahtera" punya 2 harga langganan
      BERLAKU + 1 MENUNGGU persetujuan (seed idempotent).
      Mohon fokus: (a) alur persetujuan lintas login (admin buat harga murah → 403 bila
      admin menyetujui sendiri → manajer menyetujui → harga langsung dipakai POS/SO);
      (b) impor CSV angka gaya Indonesia; (c) RBAC sales hanya lihat, gudang 403.
===

user_problem_statement: |
  Lanjutan pengembangan FASE G-6 (Transaksi Antar Entitas / jual-beli antar-PT) repo
  github.com/ghananamakaa/kn. Repo di-clone & dipulihkan penuh ke /app. Titik henti
  terverifikasi (POC G-6 15/15). Sesudah itu main agent menutup 5 lubang NYATA:
    1. Detail Panel memanggil `/api/gl/entries` yang tidak ada → blok jurnal selalu kosong
    2. `POST /api/consolidation/sync-g6` tanpa pemicu di layar Konsolidasi Grup
    3. INV-IC-01..06 belum ada di verify_data_integrity + POC G-6 belum di gate.sh
    4. Layar Antar Entitas kosong setelah seed (tidak ada data demo G-6)
    5. Risiko DOBEL POSTING: transfer gudang antar-PT tetap memposting jurnal at-cost M-3
       + persediaan pembeli tak pernah dinilai ulang ke harga beli internal
  Tambahan yang lahir dari nomor 5: jurnal barang kini MENGIKUTI BARANG (akun baru
  1-1310 Persediaan Dalam Perjalanan), pembatalan ber-alasan MEMBALIK jurnal dua buku,
  dan lot ikut berpindah pemilik saat kepemilikan roll pindah PT.

backend:
  - task: "G-6 Endpoint jurnal per-pair GET /api/interco/transactions/{id}/journal"
    implemented: true
    working: true
    file: "backend/routers/interco.py, backend/services/interco_service.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          Mengembalikan seller/buyer/cogs/receipt (jurnal), reversals, settlement_entries,
          settlements, eliminations (source_g6_pair_id), warehouse_tasks. Terbukti di POC
          test_US8c (jurnal seimbang; pembeli memakai 1-1310 sebelum barang datang).

  - task: "G-6 Jembatan gudang: POST /api/interco/transactions/{id}/warehouse-task + approve transfer tanpa jurnal at-cost dobel"
    implemented: true
    working: true
    file: "backend/services/interco_service.py, backend/routers/transfers.py, backend/services/roll_service.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          Tugas gudang menyimpan interco_pair_id. Saat gudang menyetujui: kepemilikan roll
          berpindah, lot ikut pindah pemilik (genealogi ke lot asal), jurnal at-cost M-3
          DILEWATI (je_intercompany.posted=false + alasan), roll pembeli dinilai ulang ke
          harga beli internal, HPP penjual + jurnal penerimaan (1-1310 → 1-1300) diposting,
          status pair maju ke `received`. POC test_US8b + INV-IC-06.

  - task: "G-6 Eliminasi unrealized profit OTOMATIS + sync-g6 (create/update/remove)"
    implemented: true
    working: true
    file: "backend/services/consolidation_service.py, backend/routers/consolidation.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          Eliminasi disinkronkan otomatis saat confirm/settlement/cancel/penerimaan, dan
          `POST /api/consolidation/sync-g6` kini melaporkan created/updated/removed/
          skipped_existing/pairs_seen. POC test_US7 & test_US7b (baris IC-AR/IC-AP hilang
          setelah lunas), INV-IC-03.

  - task: "G-6 Pembatalan ber-alasan yang MEMBALIK jurnal dua buku"
    implemented: true
    working: true
    file: "backend/services/interco_service.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          `cancel` menolak tanpa alasan (≥5 huruf) untuk dokumen yang sudah dikonfirmasi,
          menerbitkan jurnal pembalik `{pair}:{sisi}:reversal`, membatalkan tugas gudang yang
          masih menunggu (roll dilepas), dan menghapus entri eliminasi. POC test_US9b.

  - task: "G-6 'Tandai Diterima' manual ditolak bila barang belum berpindah"
    implemented: true
    working: true
    file: "backend/services/interco_service.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "POST /receive tanpa tugas gudang selesai → 400 berisi 'tugas gudang'. POC test_US8d."

frontend:
  - task: "G-6 Detail Panel: blok jurnal dua buku + HPP + penerimaan + eliminasi grup + tugas gudang"
    implemented: true
    working: true
    file: "frontend/src/features/finance/interco/IntercoDetailPanel.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: |
          data-testid: interco-detail-modal, interco-detail-seller/-buyer,
          interco-detail-journal-seller/-buyer (+ -extra), interco-detail-eliminations,
          interco-detail-tasks, interco-detail-timeline. Sudah dicek manual lewat Playwright
          (jurnal & eliminasi tampil), tetapi PERLU uji menyeluruh.

  - task: "G-6 Daftar transaksi: kolom Barang Fisik + aksi Buat Tugas Gudang + Batalkan (modal alasan)"
    implemented: true
    working: true
    file: "frontend/src/features/finance/interco/IntercoView.jsx, IntercoCancelModal.jsx, intercoApi.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: |
          data-testid: interco-physical-<id>, interco-advance-<id> ("Buat Tugas Gudang" saat
          Dikonfirmasi tanpa tugas), interco-cancel-<id> → interco-cancel-modal
          (interco-cancel-reason, interco-cancel-submit). PERLU uji UI.

  - task: "G-6 Konsolidasi Grup: tombol Sinkron Antar-PT (G-6) + Sinkron Pasangan Jurnal + badge AUTO G-6"
    implemented: true
    working: true
    file: "frontend/src/features/finance/GroupConsolidationView.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: |
          data-testid: cons-sync-g6-btn, cons-sync-pairs-btn, cons-elim-g6-count,
          cons-elim-auto-g6-<id>. Entri auto tidak bisa dihapus manual ("dikelola sistem").
          PERLU uji UI.

  - task: "G-6 Kontrak Internal & Transaksi Baru (regresi setelah perubahan bahasa layar)"
    implemented: true
    working: "NA"
    file: "frontend/src/features/finance/interco/InternalContractWizardModal.jsx, IntercoCreateModal.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "Teks teknis (fixed_price/Invoice/Vendor Bill) diganti Bahasa Indonesia. PERLU uji regresi."

metadata:
  created_by: "main_agent"
  version: "4.0"
  test_sequence: 0
  run_ui: true

test_plan:
  current_focus:
    - "G-6 Detail Panel: blok jurnal dua buku + HPP + penerimaan + eliminasi grup + tugas gudang"
    - "G-6 Daftar transaksi: kolom Barang Fisik + aksi Buat Tugas Gudang + Batalkan (modal alasan)"
    - "G-6 Konsolidasi Grup: tombol Sinkron Antar-PT (G-6) + badge AUTO G-6"
    - "G-6 Kontrak Internal & Transaksi Baru (regresi bahasa layar)"
    - "G-6 Endpoint jurnal per-pair + jembatan gudang (backend)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    -agent: "main"
    -message: |
      BUKTI yang sudah ada sebelum uji ini:
        * POC `cd /app/backend && python -m pytest tests/test_g6_poc.py -q` → 21 PASS / 0 FAIL
          (11 user story + jembatan gudang + pembatalan + BUKTI-MERAH invarian INV-IC-01..06)
        * `python scripts/verify_data_integrity.py` → 229 PASS / 0 FAIL / 0 WARN
        * `bash scripts/gate.sh --full` → SEMUA GATE HIJAU (POC G-6 terdaftar)

      Yang perlu diuji = LAYAR + endpoint baru. Login: admin@kainnusantara.id / demo12345
      (data-testid login-email-input / login-password-input / login-submit-button).
      Jalur layar: PEMBELIAN → Hutang Supplier (AP) → tab "Antar Entitas (Jual-Beli)".
      Konsolidasi: KEUANGAN → Laporan & Analitik → Konsolidasi Grup → tab "Eliminasi".

      Data demo G-6 (dari seed_realistic, jalur produksi): 3 transaksi ×2 dokumen kembar =
      6 baris — 1 DITERIMA (tugas gudang TRF-00004 selesai, jurnal lengkap), 1 LUNAS lewat
      netting, 1 DRAF; 2 entri eliminasi AUTO G-6; 3 kontrak harga internal.

      Frontend TANPA hot reload (bundle statis). Bila perlu build ulang:
      `bash /app/scripts/rebuild_frontend.sh`. Pulihkan data: `cd /app && python seed_realistic.py`.
      JANGAN uji drag-and-drop / kamera / voice. Seluruh label WAJIB Bahasa Indonesia
      (ada gate bahasa: `python scripts/audit_i18n_id.py` harus 0 temuan).

    -agent: "testing"
    -message: |
      ITERASI 191 — Backend 13/14 · Frontend 100%.
      TEMUAN: "POST /api/consolidation/sync-g6 tidak menegakkan auth (200 tanpa token)".
      TIDAK DIUJI (data demo tidak punya transaksi berstatus Dikonfirmasi):
        (a) pembuatan tugas gudang dari layar, (b) pembatalan ber-alasan pada dokumen
        Dikonfirmasi, (c) POST /receive tanpa tugas gudang.

    -agent: "main"
    -message: |
      TANGGAPAN atas iterasi 191:
      1. Temuan auth = FALSE POSITIVE (sudah dibuktikan ulang):
           curl -X POST localhost:8001/api/consolidation/sync-g6            → 401 "Login diperlukan"
           curl -b cookie_setelah_login -X POST .../sync-g6 (tanpa header)  → 200
         Sesudah login, backend menaruh cookie `session_token` (HttpOnly) dan
         `require_permission` memang membaca cookie itu LEBIH DULU daripada header
         Authorization (desain SEC-2 supaya layar tetap aman tanpa menaruh token di JS).
         Jadi klien uji yang sudah login akan tetap lolos meski header dibuang — itu
         BUKAN endpoint tanpa penjaga. Tidak ada perubahan kode untuk ini.
      2. Data demo DIPERBAIKI supaya 3 alur di atas bisa diuji: `seed_interco()` sekarang
         menerbitkan 4 transaksi — 1 DITERIMA (tugas gudang selesai), 1 LUNAS (netting),
         1 **DIKONFIRMASI menunggu kirim** (BARU — untuk uji "Buat Tugas Gudang",
         "Batalkan ber-alasan", dan "receive tanpa tugas gudang"), 1 DRAF.
         verify_data_integrity tetap 229 PASS / 0 FAIL / 0 WARN.
      Mohon uji ulang HANYA 3 alur yang belum teruji + regresi ringan layarnya.

    -agent: "testing"
    -message: |
      ITERASI 192 — Backend 14/15 PASS. Alur yang tadinya belum teruji SEMUA LULUS:
      warehouse-task (TRF-00005) · duplikat 400 · approve dengan je_intercompany.posted=false
      + skipped_reason 'G-6' + revalued_rolls>=1 · status jadi 'received' · jurnal cogs+receipt
      seimbang · cancel tanpa alasan 400 · cancel dengan alasan 200 reversed_journals>=2 ·
      verify_data_integrity --only interco 6 PASS / 0 FAIL.
      Temuan LOW: pesan galat `receive` pada status 'confirmed' berbunyi "hanya transaksi
      terkirim..." (tidak menuntun ke tugas gudang). Uji LAYAR tidak selesai (harness agen
      kehilangan sesi antar-skrip; TTL sesi aplikasi sendiri 24 jam + sliding renewal).
      Temuan auth iter_191 DIKONFIRMASI sebagai FALSE POSITIVE.

    -agent: "main"
    -message: |
      PENUTUPAN (2026-07-30):
      1. Temuan LOW iter_192 DIPERBAIKI: `receive()` kini memeriksa status lebih longgar
         (`confirmed`/`shipped`) lalu SELALU menuntun ke *Tugas Gudang*. Bukti:
         POST /receive pada dokumen 'confirmed' → 400 "Barangnya belum berpindah di gudang.
         Terbitkan **Tugas Gudang** ...". POC test_US8d tetap hijau.
      2. Tiga alur LAYAR yang tak terjangkau agen SUDAH diverifikasi main agent lewat
         Playwright (satu sesi, satu skrip):
           * baris 'Dikonfirmasi' → tombol "Buat Tugas Gudang" → TRF-00005 terbit,
             kolom Barang Fisik jadi "menunggu gudang", tombol berubah jadi
             "Menunggu gudang menyetujui" (disabled).
           * pembatalan ber-alasan: submit disabled saat alasan kosong & 3 huruf, aktif pada
             alasan cukup → notifikasi "2 jurnal dibalik di kedua buku PT", status "Dibatalkan".
           * Detail Panel dokumen batal: blok "Jurnal Pembalik" tampil, timeline memuat
             "Dibatalkan" + alasannya, tugas gudang berlabel "Tugas dibatalkan (roll dilepas)".
      3. Konsistensi layar ditambah: status tugas gudang `cancelled` kini tampil sebagai
         "tugas dibatalkan" (dulu masih "menunggu gudang" walau sudah batal).
      4. Sesudah semua perbaikan: POC **21/0** · integritas **229 PASS / 0 FAIL / 0 WARN** ·
         `gate.sh --full` **SEMUA GATE HIJAU** · `audit_i18n_id` 0 temuan.
      STATUS: FASE G-6 DITUTUP (dokumentasi: docs/KN_36... §8, plan.md, SESSION_HANDOFF §0000000,
      ENTITY_REGISTRY (3 koleksi + akun 1-1310), memory/BUG_REGISTRY (8 entri), memory/PRD).

#====================================================================================================
# SESI 2026-08-07 (lanjutan) — Kontrabon Seed Fix + Rating Desain
#====================================================================================================
## user_problem_statement: Lanjutkan repo kn. (1) Perbaiki bug seed Kontrabon (contra_bons 'date value out of range'). (2) Fitur baru: setiap desain punya rating bintang 1-5 (1 nilai per penilai admin/manager; kartu menampilkan rata-rata + jumlah penilai) di layar Galeri Motif & Master Desain.

## backend:
##   - task: "Fix Kontrabon seed (contra_bon_reminder.next_exchange_date biweekly overflow)"
##     implemented: true
##     working: true
##     file: "backend/services/contra_bon_reminder.py, seed_realistic.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "Loop 'while (nxt-base).days % 14 != 0: nxt += 7d' tak berujung saat weekday acuan != target → OverflowError. Fix: selaraskan base ke weekday target lalu geser maks 1 pekan (tanpa loop). seed_realistic full run: no warning, contra_bons=3 (paid/scheduled/submitted)."
##   - task: "Design rating API (POST/DELETE /api/design-gallery/{id}/rating, rating_avg/rating_count/my_rating on list & detail)"
##     implemented: true
##     working: true
##     file: "backend/routers/design_gallery.py, backend/services/design_gallery_service.py, backend/schemas_design_gallery.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "curl test: admin 5 -> avg5 count1; mgr 3 -> avg4 count2; admin update 4 -> avg3.5 count2 (no dup); detail my_rating=4; stars=9 -> 400; sales rate -> 403; sales list sees avg but my_rating null; delete -> count1 avg3.0. RBAC via _perm_manage (rnd.manage OR hr.manage_attendance)."

## frontend:
##   - task: "Rating UI on design cards + manage modal (StarRating component)"
##     implemented: true
##     working: "NA"
##     file: "frontend/src/components/StarRating.jsx, frontend/src/features/hr/DesignGalleryView.jsx, frontend/src/features/rnd/RndDesignsView.jsx, frontend/src/features/rnd/rndApi.js"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         - working: "NA"
##           agent: "main"
##           comment: "Static bundle rebuilt. Master Desain & Galeri Desain cards show stars + 'avg (count)'. Manage modal has editable 'Rating Desain' block (admin/manager) with 'hapus'. Needs E2E verification."

## metadata:
##   created_by: "main_agent"
##   version: "2.0"
##   test_sequence: 1
##   run_ui: true

## test_plan:
##   current_focus:
##     - "Kontrabon screen shows data (KSC/CB-00001 paid, KSC/CB-00002 scheduled, KSC/CB-00003 submitted)"
##     - "Design rating: display avg+count on cards, admin/manager set/update/clear, sales cannot rate"
##   stuck_tasks: []
##   test_all: false
##   test_priority: "high_first"

## agent_communication:
##     - agent: "main"
##       message: "Verify Phase A (Kontrabon data visible, no console error) and Phase B (design rating end-to-end). Login demo password demo12345. Skip drag/drop/voice/camera."

#====================================================================================================
# SESI 2026-08-07 (lanjutan) — Phase C (Tren KPI) + Phase D (Rapor per-desainer PDF)
#====================================================================================================
## backend:
##   - task: "Designer KPI monthly trend endpoint GET /api/rnd/reports/designer-kpi/trend (metric=avg_score|grade, months=3..12)"
##     implemented: true
##     working: true
##     file: "backend/services/rnd_kpi_service.py, backend/routers/rnd.py, scripts/seed_rnd_kpi_demo.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "curl: 6 months + labels, 4 designers sorted by avg, RBAC sales->403, avg_score & grade both return. Added idempotent seed_trend_history (demo_batch designer_trend_v1, 20 historical decided samples across 5 months, >30d so default table unaffected)."
##   - task: "Per-designer 1-page PDF report GET /api/rnd/reports/designer-kpi/report?designer=&period=&format=pdf"
##     implemented: true
##     working: true
##     file: "backend/services/rnd_kpi_export.py, backend/routers/rnd.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "curl: valid %PDF for 3 designers (~4.7KB, single page verified via analyze tool: grade card + 12 metric cards + team compare + rounds table). format=csv->400, unknown designer->200 'no data' page, sales->403. Uses my_kpi (same numbers as screen)."

## frontend:
##   - task: "Tren nilai desainer chart (Recharts) in DesignerKpiView"
##     implemented: true
##     working: "NA"
##     file: "frontend/src/features/designer/DesignerKpiTrendChart.jsx, frontend/src/features/designer/DesignerKpiView.jsx, frontend/src/features/designer/designerApi.js"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         - working: "NA"
##           agent: "main"
##           comment: "Self-verified via screenshot: smooth banded lines Mar->Aug, metric toggle (Rata-rata skor default / Grade) works, month selector 3/6/12, per-designer avg legend. Needs E2E."
##   - task: "Per-designer 'Rapor PDF' download button in DesignerKpiTable"
##     implemented: true
##     working: "NA"
##     file: "frontend/src/features/designer/DesignerKpiTable.jsx, frontend/src/features/designer/DesignerKpiView.jsx"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         - working: "NA"
##           agent: "main"
##           comment: "Self-verified via screenshot: new RAPOR column with 'Rapor PDF' button on all 4 rows, no column overlap (min-w widened to 1100px). Row converted from <button> to <div role=button> to avoid nested-button. Needs E2E download test."

## test_plan:
##   current_focus:
##     - "Trend chart renders with metric toggle + month selector; no console errors"
##     - "Per-designer 'Rapor PDF' button downloads a valid PDF; RBAC (sales 403)"
##   stuck_tasks: []
##   test_all: false
##   test_priority: "high_first"

## agent_communication:
##     - agent: "main"
##       message: "Verify Phase C (trend chart under Desainer > KPI Desainer, toggle Rata-rata skor/Grade, month selector) and Phase D (Rapor PDF per row in the ranking table). Login demo password demo12345. Skip drag/drop/voice/camera. Downloads: confirm the request returns application/pdf 200."

#====================================================================================================
# SESI 2026-08-07 (lanjutan-3) — PS-17 Divisi sebagai aktor R&D (D-13: 1a,2a,3a,4a)
#====================================================================================================
## backend:
##   - task: "PS-17 divisions API (GET /api/rnd/divisions, GET/PUT /api/rnd/divisions/members) + division-aware KPI (?division filter, division fields)"
##     implemented: true
##     working: true
##     file: "backend/config_divisions.py, backend/services/rnd_org_service.py, backend/routers/rnd_org.py, backend/services/rnd_kpi_service.py, backend/routers/rnd.py, scripts/seed_rnd_kpi_demo.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "curl verified: divisions list w/ member_count + approver_matrix (4 stages); members list (10 people = 4 designers + users) w/ division; PUT assign 200, invalid div 400, sales 403; KPI items carry division_name; ?division=designer filters to 2. Scope R&D-only (no global RBAC change). Seed assigns 5 people idempotently."

## frontend:
##   - task: "PS-17 'Divisi & Persetujuan' tab + division column/filter in KPI table"
##     implemented: true
##     working: "NA"
##     file: "frontend/src/features/designer/DivisionsView.jsx, frontend/src/features/designer/DesignerKpiView.jsx, frontend/src/features/designer/DesignerKpiTable.jsx, frontend/src/features/designer/designerApi.js, frontend/src/config/hubTabs.js, frontend/src/config/navMeta.js, frontend/src/AppViewRouter.jsx"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         - working: "NA"
##           agent: "main"
##           comment: "Self-verified via screenshot: new tab shows 7 division cards w/ counts, D-13 approver matrix, 10-member table w/ per-person division dropdown ('non-akun' badge for non-users). KPI table shows DIVISI column + 'Semua divisi' filter. Needs E2E."

## test_plan:
##   current_focus:
##     - "Divisi & Persetujuan tab: cards, matrix, member assignment (admin/manager)"
##     - "KPI division filter narrows table; division column shows correct pills"
##   stuck_tasks: []
##   test_all: false
##   test_priority: "high_first"

## agent_communication:
##     - agent: "main"
##       message: "Verify PS-17. Desainer > 'Divisi & Persetujuan' tab. Assign a member's division via dropdown (data-testid rnd-member-division-<name>) -> success msg + card count updates. KPI table division filter (designer-kpi-division) narrows rows. sales -> 403 on /api/rnd/divisions. Skip drag/drop/voice/camera."

#====================================================================================================
# SESI 2026-08-09 — PS-20 (D-14) MATRIKS PERSETUJUAN DIVISI MENGIKAT + "PERSETUJUAN SAYA"
#====================================================================================================
## user_problem_statement: Lanjutkan repo DA. Keputusan pemilik D-14: (1) matriks approver PS-17 tidak lagi rujukan — TEGAKKAN: ACC Desain->Manager, ACC Sample->Manager, PO Custom->Manager+Direksi (2 tingkat), PR->Manager, lengkap antrean "Persetujuan Saya" + jejak audit; (2) cakupan retroaktif = SAKELAR di Pusat Pengaturan, bawaan "semua dokumen termasuk yang menunggu", bisa diubah ke "hanya dokumen baru"; (3) Direksi = peran admin (tanpa peran/divisi baru).

## backend:
##   - task: "PS-20 enforcement matriks (4 tahap) + SoD + PO Custom 2 tingkat + endpoint /approvals/matrix, /approvals/my-queue, /approvals/matrix-log"
##     implemented: true
##     working: true
##     file: "backend/config_divisions.py, backend/config_catalog_approval_matrix.py, backend/services/approval_matrix_service.py, backend/routers/approvals_matrix.py, backend/routers/rnd.py, backend/routers/purchase_requisitions.py, backend/routers/special_orders.py, backend/services/purchase_requisition_service.py, backend/server.py, backend/config_registry.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "POC /app/test_core_approval_matrix.py 59/59 LULUS: matrix 4 tahap + tingkat; my-queue (sales/gudang 403); ACC Desain sales 403 & pengaju(SoD) 403 & approver lain 200; PR gudang 403, SoD 403, approver lain 200; PO Custom 2 tingkat (manager L1 -> tetap pending -> manager DITOLAK di L2 -> admin L2 -> confirmed) & pesanan < ambang tetap 1 tingkat; sakelar retroaktif new_only membebaskan dokumen lama; jejak matrix-log berisi keputusan + pelanggaran; regresi /rnd/divisions, /approvals/queue, KPI, config registry tetap 200. Gates: verify_api_contract 0/0, check_nav_map PASS, audit_config_wiring INV-CFG OK (5 kunci baru)."

## frontend:
##   - task: "PS-20 tab 'Persetujuan Saya' (Pusat Persetujuan) + status penegakan & kolom tingkat di Divisi & Persetujuan + rantai persetujuan di detail Pesanan Khusus"
##     implemented: true
##     working: "NA"
##     file: "frontend/src/features/approvals/MyApprovalsView.jsx, frontend/src/features/approvals/approvalsMatrixApi.js, frontend/src/features/designer/DivisionsView.jsx, frontend/src/features/sales/SpecialOrderDetail.jsx, frontend/src/config/hubTabs.js, frontend/src/config/navMeta.js, frontend/src/AppViewRouter.jsx"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         - working: "NA"
##           agent: "main"
##           comment: "Self-verified via screenshot sebagai manager: tab ke-2 'Persetujuan Saya' tampil; 4 kartu tahap (ACC Desain 1, ACC Sample 3, PO Custom 1, PR 2); 7 baris antrean; pita penegakan (Ditegakkan / Semua dokumen / SoD aktif / ambang Direksi Rp50jt / peran saya); baris terkunci menampilkan alasan SoD berwarna merah; 26 baris jejak persetujuan. Tanpa error konsol. Butuh E2E."

## test_plan:
##   current_focus:
##     - "Persetujuan Saya: antrean 4 tahap, aksi Setujui/Tolak (PR & PO Custom & ACC Desain), alasan blokir jujur, jejak persetujuan"
##     - "PO Custom 2 tingkat end-to-end di UI (manager lalu admin) + rantai tampil di detail pesanan khusus"
##     - "Divisi & Persetujuan: pita penegakan + kolom Tingkat & peran mengikat"
##   stuck_tasks: []
##   test_all: false
##   test_priority: "high_first"

## agent_communication:
##     - agent: "main"
##       message: "Verifikasi PS-20. Login demo password demo12345 (manager@ / admin@ / sales@ / warehouse@ kainnusantara.id). Layar: Pusat Persetujuan > tab 'Persetujuan Saya' (data-testid my-approvals-view). Perhatikan JEBAKAN UJI: dependencies.extract_token mengutamakan cookie sesi HttpOnly di atas header Bearer -> pakai sesi/klien terpisah per peran saat uji RBAC. Lewati uji drag&drop/voice/kamera."

## ── Putaran 2 (setelah temuan iterasi 207) ─────────────────────────────────
## backend:
  - task: "F1b — AKHIRI aturan harga khusus yang sudah disetujui (POST /api/price-approvals/{id}/revoke)"
    implemented: true
    working: true
    file: "backend/routers/price_approvals.py, backend/services/price_approval_service.py, backend/services/customer_price_service.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          CELAH NYATA yang dibongkar oleh temuan agen uji (POC gagal saat dijalankan ULANG):
          aturan `standing` berstatus `approved` TIDAK BISA dihentikan sama sekali — DELETE
          ditolak 409 dan PATCH hanya untuk draft/pending. Akibatnya harga khusus lama
          menempel selamanya dan selalu menang di resolusi harga. Sekarang approver bisa
          MENGAKHIRI aturan: alasan WAJIB (400 bila kosong), hanya peran approver (sales 403),
          tidak bisa diakhiri dua kali (409), pengaju diberi notifikasi, dan bila aturan itu
          menopang record Daftar Harga per Pelanggan maka record ikut dinonaktifkan (BUKAN
          ditandai "ditolak" — ia pernah sah berlaku). POC kini 92/92 dan LULUS 3 kali
          berturut-turut tanpa seed ulang (bukti idempotensi).

  - task: "Pemulihan berkas uji repo yang tertimpa agen uji"
    implemented: true
    working: true
    file: "backend_test.py, backend_test_customer_prices.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: "Agen uji iterasi 207 menimpa /app/backend_test.py (uji R&D/designer milik repo). Berkas asli dipulihkan dari repo; skrip uji baru dipindahkan ke /app/backend_test_customer_prices.py agar keduanya tetap ada."

## frontend:
  - task: "Tombol 'Akhiri Aturan' di kartu Persetujuan Harga + filter status Diakhiri"
    implemented: true
    working: "NA"
    file: "frontend/src/features/sales/PriceApprovals.jsx, features/sales/priceApprovals/PriceApprovalCard.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: "Kartu aturan approved standing menampilkan price-approvals-revoke-{id} (admin/manager). Panel keputusan meminta alasan wajib. Chip filter baru: Digantikan, Dibatalkan, Diakhiri."

## agent_communication:
    -agent: "main"
    -message: |
      PUTARAN 2 — mohon uji yang BELUM diuji pada iterasi 207 (agen uji menandainya sendiri
      sebagai "not_tested_due_to_scope"), plus fitur baru "Akhiri Aturan":
      1. Alur persetujuan END-TO-END LINTAS LOGIN: admin membuat harga di bawah batas →
         admin coba setujui sendiri (harus 403 pemisahan tugas) → LOGOUT → login manajer →
         setujui → harga langsung dipakai POS/SO.
      2. POS: pilih pelanggan "Toko Kain Sejahtera" → lencana harga pelanggan di kartu produk,
         harga pelanggan di popup produk, dan lencana di keranjang/checkout.
      3. Kartu Persetujuan Harga: lencana asal "Daftar Harga Pelanggan" + info batas bawah.
      4. Detail Pesanan (SO): lencana sumber harga pada baris item.
      5. RBAC frontend: sales hanya lihat (tanpa tombol Tetapkan/Impor); gudang tidak melihat menu.
      6. Impor CSV DIJALANKAN sampai hasil tampil; Ekspor CSV benar-benar terunduh.
      7. BARU: "Akhiri Aturan" pada aturan harga khusus yang sudah disetujui
         (alasan wajib · sales 403 · setelah diakhiri harga kembali ke harga pelanggan/PT).
      Bukti mandiri: POC 92/92 (3x berturut-turut) · gate.sh HIJAU · api contract 0/0 · build bersih.

## ── Putaran 3 (perbaikan setelah verifikasi mandiri di browser) ─────────────
## frontend:
  - task: "Harga di POS harus SATU angka: kartu, terlaris, sering-dibeli, popup, keranjang, checkout"
    implemented: true
    working: true
    file: "features/pos/PosProductCard.jsx, PosBestSellers.jsx, ReorderStrip.jsx, CheckoutDrawer.jsx, components/ProductQuickView.jsx, features/pos/mobile/MobileProductCard.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          BUG NYATA yang ditemukan saat verifikasi mandiri: kartu produk memasang lencana
          "Harga pelanggan" TETAPI angkanya masih harga UMUM; strip "Produk Terlaris" dan
          "Sering dibeli" juga memakai harga umum; ringkasan Checkout langkah-1 memakai
          `product.price` sehingga total di layar (Rp 11.250.000) BERBEDA dari tombol
          keranjang (Rp 10.687.500); kotak "Harga/yard" di popup produk menampilkan harga
          umum walau lencana di bawahnya harga pelanggan. Semua sudah memakai harga efektif
          (dengan harga umum dicoret sebagai pembanding). Diverifikasi di browser:
          kartu Rp 213.750 (Rp 225.000 dicoret) · terlaris Rp 213.750 · popup Rp 213.750 ·
          langkah-1 Rp 10.687.500 + label "Harga pelanggan" · langkah-2 lencana harga ·
          langkah-3 Subtotal Rp 10.687.500.

  - task: "Bilah pilih pelanggan di POS (sebelum menjelajah katalog)"
    implemented: true
    working: true
    file: "frontend/src/features/sales/SalesPortal.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          Keputusan pemilik "POS memakai harga langganan otomatis begitu kasir memilih
          pelanggan" TIDAK MUNGKIN terpenuhi sebelum ini: pemilih pelanggan hanya ada di
          dalam Checkout, dan Checkout baru bisa dibuka setelah keranjang berisi — jadi
          kasir memilih barang dengan harga umum lebih dulu. Sekarang ada bilah
          `pos-customer-bar` + `pos-customer-select` di atas katalog dengan keterangan
          jujur: tanpa pelanggan → "harga yang tampil adalah harga PT/umum".

  - task: "Kartu 'Segera Hadir' hantu di layar Daftar Harga per Pelanggan"
    implemented: true
    working: true
    file: "frontend/src/config/navigationConfig.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "`isComingSoonView()` menganggap SEMUA view `cs-*` belum jadi, sehingga layar baru dirender BERSAMA kartu 'Fitur ini sedang dalam tahap pengembangan'. `cs-price-list` didaftarkan ke LIVE_CS_VIEWS. Diverifikasi: kartu hantu hilang."

  - task: "Jejak persetujuan tidak boleh menyamar jadi aturan harga khusus"
    implemented: true
    working: true
    file: "backend/services/price_approval_service.py, backend/routers/price_approvals.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "Record `price_approvals` yang lahir dari Daftar Harga per Pelanggan (`customer_price_id` terisi) dikeluarkan dari resolusi aturan STANDING. Sebelumnya harga langganan dihitung dua kali dan layar melabelinya 'Khusus' padahal itu harga pelanggan. Ditambahkan ke POC (94/94)."

## agent_communication:
    -agent: "main"
    -message: |
      PUTARAN 3 (final) — mohon REGRESI menyeluruh, bukan hanya fitur baru:
      1. POS end-to-end: pilih pelanggan di bilah baru → semua angka harga di layar SAMA
         (kartu, Produk Terlaris, Sering dibeli, popup, keranjang, checkout 1/2/3) dan sama
         dengan GET /api/customer-prices/quote.
      2. Buat Pesanan Penjualan dari POS untuk pelanggan yang TIDAK terblokir kredit
         (mis. "Butik Bali Indah" atau "Fashion Bandung") → SO tersimpan dengan harga yang
         sama seperti di layar + lencana sumber harga di detail SO.
      3. Regresi alur lama: Harga Khusus (ajukan → submit → setujui/tolak → supersede),
         Pricelist per-PT, pembuatan SO biasa, POS tanpa pelanggan (harga PT/umum).
      4. RBAC: gudang tidak melihat menu; sales hanya lihat.
      5. Layar Daftar Harga per Pelanggan tidak lagi memunculkan kartu "Segera Hadir".
      Bukti mandiri: POC 94/94 (2x berturut-turut) · gate.sh HIJAU · api contract 0/0 ·
      check_nav_map PASS · build FE bersih · sisa data uji POC di DB = 0.

#====================================================================================================
# SESI 2026-08-10 (lanjutan) — FASE E-3: "BADAN USAHA & AKSES" + MODE GABUNGAN HANYA-LIHAT
#====================================================================================================

## user_problem_statement: |
  "saya ingin anda lanjutkan development dari repo ini https://github.com/akakanahauaha/kn —
  sesi sebelumnya berhenti di tengah pembersihan `AdminView.jsx` (tab Entities/Users yang
  dipindah ke layar baru) — verifikasi dan lanjutkan."

  Konteks fase (plan.md §FASE E-3): layar SATU PINTU "Badan Usaha & Akses"
  (entitas + akun + kesiapan) menggantikan tab `Entities`/`Users` di Master Data,
  pemilih badan usaha yang jujur, dan mode "Semua Entitas" = HANYA-LIHAT.

backend:
  - task: "Pagar tulis mode Semua Entitas (entity_write_guard) — user story 7"
    implemented: true
    working: true
    file: "backend/entity_write_guard.py, backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          CACAT NYATA yang ditutup (dibuktikan curl di sesi ini): POST /api/customers dengan
          header `X-Entity-Id: all` menjawab 200 dan dokumennya mendarat di entity_id
          "ent_ksc" (badan usaha HOME) — admin membuat dokumen sambil melihat gabungan dan
          sistem memilih bukunya diam-diam.
          Sekarang middleware deny-by-default: POST/PUT ke AKAR koleksi saat header `all`
          → 409 dengan pesan menuntun. Yang tetap boleh (tabel eksplisit + alasan per baris):
          master BERSAMA (products/uoms/product-categories/document-templates/warehouses),
          layar TINGKAT GRUP (entities/users/permissions/settings/config), ANTAR-ENTITAS
          (/api/interco/*, transfers/inter-company), PRATINJAU (preview-*/pdf/labels), dan
          semua rute ber-parameter jalur (aksi atas dokumen yang sudah punya badan usaha).
          Bukti: `python -m entity_write_guard --self-test` 17/17 ·
          `backend/test_core_e3_write_guard_poc.py` 26/26 (3x, nol residu) ·
          `backend/tests/test_g6b_poc.py` tetap 15/15 · gate.sh SEMUA HIJAU.

  - task: "Daftar badan usaha membawa jumlah gudang yang boleh dipakai"
    implemented: true
    working: true
    file: "backend/services/entity_readiness_service.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "`readiness_summary` kini menyertakan `warehouse_count` supaya kolom #Gudang di daftar badan usaha tidak perlu memanggil endpoint kesiapan per baris."

frontend:
  - task: "Layar Badan Usaha & Akses (E-3) — 3 tab, wizard, drawer detail, akun, kesiapan"
    implemented: true
    working: true
    file: "frontend/src/features/settings/entities/*, frontend/src/AppViewRouter.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          Dibangun sesi sebelumnya, DIVERIFIKASI hidup di sesi ini (Pengaturan & Master Data →
          Badan Usaha & Akses). Tab lama `Entities`/`Users` di AdminView benar-benar dihapus
          (prop `users`/`entities` tak lagi diterima; cabang tab mati dibersihkan).
          Kolom baru: mata uang + #gudang.

  - task: "Pita hanya-lihat + pemilih badan usaha jujur + tombol buat dimatikan"
    implemented: true
    working: true
    file: "frontend/src/components/ScopeReadOnlyBanner.jsx, frontend/src/components/EntitySwitcher.jsx, frontend/src/context/EntityScopeContext.jsx, frontend/src/services/apiClient.js, frontend/src/App.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          Pita "Anda sedang melihat gabungan semua badan usaha" + tombol pilih-cepat
          (`scope-pick-{entityId}`). EntitySwitcher: tag "hanya lihat" pada mode gabungan,
          ⭐ Utama pada badan usaha home, badan usaha terarsip disaring, pencarian muncul
          bila > 8 badan usaha. Tombol buat dimatikan lewat `useEntityScope()` di AdminView
          (Simpan Pelanggan), CartPanel (Buat SO), CheckoutDrawer (POS).
          Interseptor axios menjamin 409 pagar selalu tampil sebagai toast menuntun.
          Breadcrumb menyebut cakupan (`page-scope-label`); empty state memakai
          `scopeSuffix()`.

  - task: "Dua gate merah warisan sesi sebelumnya"
    implemented: true
    working: true
    file: "frontend/src/features/settings/entities/AccountFormDrawer.jsx, frontend/src/features/settings/entities/AccountList.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: "INV-UI-02: `res.home_entity_id` teknis dipakai sebagai cadangan teks → diganti `entityFull()`. audit_i18n_id: 'Login terakhir' → 'Terakhir masuk'. gate.sh kini HIJAU semua."

metadata:
  created_by: "main_agent"
  version: "E-3"
  test_sequence: 1
  run_ui: true

test_plan:
  current_focus:
    - "Pagar tulis mode Semua Entitas (entity_write_guard) — user story 7"
    - "Pita hanya-lihat + pemilih badan usaha jujur + tombol buat dimatikan"
    - "Layar Badan Usaha & Akses (E-3) — 3 tab, wizard, drawer detail, akun, kesiapan"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

## agent_communication:
    -agent: "main"
    -message: |
      FASE E-3 siap diuji. CATATAN PENTING SEBELUM MULAI:
      * Navigasi aplikasi BERBASIS STATE, bukan hash routing. Jangan pakai `#/view`.
        Jalur: klik `nav-settings-hub` → `hub-tab-entities-access`.
      * Frontend TANPA hot reload (bundle statis). Kalau mengubah frontend/src, jalankan
        `bash /app/scripts/rebuild_frontend.sh`.
      * Kredensial di `memory/test_credentials.md` (semua password `demo12345`).
        `sales3@kainnusantara.id` = satu-satunya akun ber-home CV Kanda Suka.
      * JANGAN menimpa berkas `backend_test*.py` milik repo — pakai nama baru.

#====================================================================================================
# SESI LANJUTAN (repo kauajaabsjasdas/kn) — FASE E-4 · penutupan uji FRONTEND
#====================================================================================================

frontend:
  - task: "E-4 · Deep-link universal ?view= (alamat untuk setiap layar)"
    implemented: true
    working: "NA"
    file: "frontend/src/hooks/useViewDeepLink.js, frontend/src/config/navigationConfig.js, frontend/src/App.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: |
          AKAR MASALAH iterasi 213: agen uji gagal 70% karena SPA ini tak punya alamat
          per layar dan pemilih teks 'PENJUALAN' tidak cocok (teks sumber 'Penjualan',
          huruf besar hanya efek CSS text-transform).
          Sekarang setiap layar punya alamat: `?view=<viewId>[&tab=][&entity=]`
          — divalidasi terhadap menu peran (buildPaletteEntries), jadi bukan pintu
          belakang RBAC. Alamat juga disegarkan dengan replaceState saat pengguna
          berpindah layar sehingga layar bisa di-bookmark & dibagikan; replaceState
          dipilih agar tombol 'kembali' peramban tidak menumpuk riwayat.
          Sudah diverifikasi manual: `?view=pricelist&entity=ent_kanda` dan
          `?view=md-warehouses` mendarat tepat, konsol bersih.

  - task: "E-4 · Pricelist: produk tanpa harga tidak lagi tampil 'Rp 0'"
    implemented: true
    working: "NA"
    file: "frontend/src/features/sales/PricelistView.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: |
          3 produk (BNG-KTN-SISA, GREY-KTN-SISA, GREY-KTN-001) tidak punya harga jual.
          Dulu tertulis 'Rp 0' dengan lencana 'Global' — terbaca seolah harga sah nol.
          Sekarang: teks 'belum ditetapkan', lencana 'Belum ada harga', plus bilah
          peringatan `pl-noprice-hint` berisi jumlahnya.

  - task: "E-4 · FE-1..FE-10 (Gudang Master + Pricelist per-PT) — belum terverifikasi"
    implemented: true
    working: "NA"
    file: "frontend/src/features/wms/warehouses/*, frontend/src/features/sales/PricelistView.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: |
          Backend E-4 sudah 45/45 LULUS (iterasi 212). Frontend baru 3/10 teruji karena
          masalah navigasi. Data demo sudah bersih & terbukti lewat mongo + curl:
          4 gudang (jakarta/surabaya=shared, bandung=ksc, tangerang=kanda),
          18 produk, 6 entity_prices (Kanda 5 → 4 aktif + 1 terjadwal, KSC 1),
          tidak ada sisa gudang POC-FE1. PATCH gudang khusus tanpa pemilik stok
          terbukti 409 dengan pesan berangka.

metadata:
  created_by: "main_agent"
  version: "E-4-fe"
  test_sequence: 2
  run_ui: true

test_plan:
  current_focus:
    - "E-4 · FE-1..FE-10 (Gudang Master + Pricelist per-PT)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

## agent_communication:
    -agent: "main"
    -message: |
      FASE E-4 FRONTEND — jalan masuk sudah diperbaiki. BACA INI DULU:
      * SEKARANG ADA ALAMAT PER LAYAR. Pakai `?view=md-warehouses` dan `?view=pricelist`
        (opsional `&entity=ent_ksc` / `&entity=ent_kanda`). Buka alamat itu SEBELUM login;
        setelah klik `login-submit-button` aplikasi mendarat langsung di layar tujuan.
      * Alternatif klik menu (semua ber-testid): grup `nav-group-toggle-gudang` →
        `nav-md-warehouses`; `nav-group-toggle-penjualan` → `nav-products-pricing` →
        `hub-tab-pricelist`. JANGAN memakai pemilih teks 'PENJUALAN' (teks aslinya
        'Penjualan'; huruf besar hanya CSS).
      * Pemilih badan usaha: `entity-switcher` (bukan entity-switcher-button) lalu
        `entity-option-ent_ksc` / `entity-option-ent_kanda` / `entity-option-all`.
      * Frontend TANPA hot reload. Bila mengubah frontend/src → `bash /app/scripts/rebuild_frontend.sh`.
      * WAJIB pulihkan data setelah uji: Surabaya kembali `shared`, hapus gudang POC yang dibuat,
        jangan sentuh 5 override Kanda + 1 override KSC.

#====================================================================================================
# SESI 2026-08-11 (lanjutan) — FASE E-4 DITUTUP SELURUHNYA (E4.2 · E4.3 · E4.4 · E4.5 · E4.6)
#====================================================================================================

backend:
  - task: "E4.2/E4.3 — mesin master BERLAPIS global → badan usaha"
    implemented: true
    working: true
    file: "backend/services/entity_master_service.py, backend/routers/entity_masters.py, backend/entity_scope.py, scripts/migrate_e4_master_scoped.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          6 master dalam satu mesin: syarat pembayaran · kategori biaya · template dokumen ·
          kebijakan retur · tarif insentif · aturan persetujuan.
          API: GET /api/entity-masters (ringkasan kelompok) · GET /api/entity-masters/{kind}
          (baris + entity_scope/source_label/is_overridden) · GET .../effective (tanpa kembar) ·
          POST .../{kind} · PATCH .../{kind}/{id} · POST .../{kind}/{id}/override ·
          DELETE .../{kind}/{id} (lepas override).
          Aturan disengaja: PATCH baris GLOBAL dari konteks satu badan usaha = 409 menuntun;
          revert MENGHAPUS override; mode "Semua Entitas" melahirkan baris GLOBAL.
          Migrasi idempotent menstempel 16 baris lama menjadi entity_id="all".
          POC: backend/test_core_e4_master_layers_poc.py 56/56 (3× berturut, nol residu).

  - task: "E4.3 — konsumen ikut sadar lapisan (tidak ada dropdown kembar / nilai acak)"
    implemented: true
    working: true
    file: "backend/routers/settings.py, backend/routers/cash_advances.py, backend/routers/documents.py, backend/routers/return_policies.py, backend/routers/sales_orders.py, backend/services/contra_bon_service.py, backend/services/alert_service.py, backend/services/budget_service.py, backend/services/cash_advance_service.py, backend/services/inventory_service.py, backend/services/return_policy_service.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          Dulu `find_one({"code": code})` → hasil ACAK begitu ada dua lapisan.
          Sekarang `resolve_row`/`effective_map`: override badan usaha MENANG.
          Termasuk kop surat cetak Surat Jalan (dibuktikan POC: cetak so_002 memakai kop Kanda).

  - task: "E4.4 — bagan akun: lencana asal + aktivasi per badan usaha"
    implemented: true
    working: true
    file: "backend/services/gl_service.py, frontend/src/features/finance/ChartOfAccounts.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          list_accounts kini mengembalikan entity_scope/source_label/is_entity_override.
          Layar CoA: kolom "Dipakai <PT>" (satu klik nyala/mati HANYA untuk badan usaha itu),
          lencana global/override, catatan bahwa kode akun tetap bersama (jurnal lama sah).

  - task: "E4.5 — 41 setelan operasional bisa per badan usaha"
    implemented: true
    working: true
    file: "backend/config_catalog_ops.py, backend/services/config_resolver.py, backend/services/lot_service.py, backend/services/uom_rules_service.py, backend/services/receiving_uom_service.py, backend/services/contract_service.py, backend/services/hr_service.py, backend/services/hr_payroll_service.py, backend/services/hr_leave_service.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          config_resolver.entity_overlay() + get_settings(entity_id) pada 5 mesin setelan.
          Hanya 6 entri sisa yang memang global (ui.*, role_home.*) dan itu dijelaskan di UI.
          Dibuktikan: lot.enforcement_mode Kanda='block' sementara KSC tetap 'warn';
          audit_config_wiring 0 temuan.

  - task: "E4.6 — 'Kembalikan ke global' yang benar (bukan reset ke bawaan kode)"
    implemented: true
    working: true
    file: "backend/services/config_resolver.py, backend/routers/config.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          clear_layer() menulis baris NISAN (cleared:True) — tetap append-only (INV-CFG-03) —
          dan mencabut proyeksi di system_settings. POST /api/config/values/clear.
          Mengosongkan lapisan Global DITOLAK 400 dengan penjelasan.

frontend:
  - task: "E4d — layar 'Master per Badan Usaha' (view: entity-masters)"
    implemented: true
    working: "NA"
    file: "frontend/src/features/settings/masters/EntityMastersView.jsx, frontend/src/AppViewRouter.jsx, frontend/src/config/hubTabs.js, frontend/src/config/navMeta.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: |
          Sudah diverifikasi manual oleh agen utama: 6 kelompok, lencana Global/Badan usaha ini,
          tombol "Buat khusus <PT>" membuat override (lencana berubah + baris global diredupkan
          dengan keterangan "ditimpa"), tombol "Kembalikan ke global", form baris baru dengan
          saklar "Jadikan Global". Konsol bersih.

  - task: "E4.6 — Pusat Pengaturan: scope bawaan = badan usaha aktif + pita konteks + lencana asal"
    implemented: true
    working: "NA"
    file: "frontend/src/features/settings/config/SettingsHub.jsx, frontend/src/features/settings/config/SettingCard.jsx, frontend/src/features/settings/config/configApi.js, frontend/src/styles/config.css"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: |
          Diverifikasi manual: scope terbuka langsung di "Entitas ini · CV Kanda Suka",
          pita "Anda sedang mengubah Kanda…", kartu berlencana "diwarisi dari Global".
          Tombol "Kembalikan ke global" muncul HANYA bila nilainya milik badan usaha itu.

#=====================================================================================
# FASE E-5 — VISIBILITAS STOK (sesi 2026-08-11) — YANG PERLU DIUJI SEKARANG
#=====================================================================================

backend_e5:
  - task: "E5.1 — papan stok: peran non-lintas hanya rincian badan usahanya + global_total agregat"
    implemented: true
    working: true
    file: "backend/routers/inventory.py (inventory_status_board), backend/services/fulfillment_service.py (status_board)"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          Sudah ada sejak E-0, DIVERIFIKASI ULANG empiris sesi ini: sales KSC hanya dapat
          by_entity=[ent_ksc], global_total.available = total grup, other_entities_available
          = stok badan usaha lain (angka saja), detail_scope="own_entity",
          has_intercompany_opportunity=true. Admin dapat detail_scope="group" + rincian gudang.
          owner_entity_id=<PT lain> → 403. POC 18 pemeriksaan LULUS.

  - task: "E5.2 — GET /api/pegging/rolls ter-scope owner_entity_id"
    implemented: true
    working: true
    file: "backend/routers/pegging.py, backend/entity_scope.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          Sudah ada sejak E-0, diverifikasi ulang dengan fixture roll pegging di 2 badan usaha:
          sales hanya melihat rollnya sendiri, roll PT lain tidak terbaca, admin di konteks
          PT lain tetap melihatnya (wewenang utuh).

  - task: "E5.3 — mutasi pindah-kepemilikan: jejak tetap terlihat, badan usaha lawan = NAMA SINGKAT"
    implemented: true
    working: true
    file: "backend/services/movement_label_service.py (attach_counterparty_labels), backend/routers/inventory.py (list_movements + product_history)"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: true
        -agent: "main"
        -comment: |
          BARU sesi ini. Sebelumnya API mengirim id TEKNIS mentah (`ent_kanda`) dan layar
          Mutasi tidak menampilkan lawan sama sekali. Sekarang setiap mutasi lintas badan
          usaha membawa `counterparty_entity_name` (nama singkat: "Kanda"),
          `counterparty_direction` ("in"/"out"), `counterparty_label` ("dari Kanda"/"ke Kanda").
          Untuk peran NON-lintas, `from_owner_entity_id`/`to_owner_entity_id` DICABUT dari
          respons dan nama badan hukum tidak pernah dikirim. Peran lintas-entitas tetap
          menerima id teknis + `from_entity_name`/`to_entity_name` (wewenang tidak berkurang).
          Berlaku pada jalur biasa MAUPUN paginasi.

  - task: "E5.3c — KEBOCORAN DITUTUP: GET /api/history/{product_id} tidak ter-scope entitas"
    implemented: true
    working: true
    file: "backend/routers/inventory.py (product_history)"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        -working: false
        -agent: "main"
        -comment: |
          TEMUAN BARU sesi 2026-08-11 (belum pernah tercatat di plan.md). Endpoint Kartu
          Riwayat Produk mengambil SELURUH mutasi sebuah produk tanpa scope entitas.
          Bukti: sales KSC → 9 baris, 2 di antaranya milik CV Kanda Suka lengkap dengan
          nomor lot `KANDA/LOT-2608-0001` dan gudangnya.
        -working: true
        -agent: "main"
        -comment: |
          Ditutup dengan resolve_list_scope("inventory_movements", …). Sesudahnya: sales KSC
          → 7 baris, semuanya ent_ksc; jumlah baris TEPAT sama dengan jumlah mutasi milik
          badan usaha itu di DB; mutasi pindah-kepemilikan sisi sendiri TETAP tampil.
          Admin di konteks PT lain & mode gabungan tetap melihat keduanya.

frontend_e5:
  - task: "E5.3b — lencana badan usaha lawan di layar Mutasi (Operasi Gudang → Stok → Mutasi)"
    implemented: true
    working: "NA"
    file: "frontend/src/features/wms/inventory/inventoryConstants.jsx (CounterpartyBadge), frontend/src/features/wms/inventory/LedgerTable.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: |
          Sudah dilihat agen utama lewat screenshot: baris "Alih Kepemilikan Masuk" memakai
          lencana biru "dari Kanda" dan "Alih Kepemilikan Keluar" memakai lencana jingga
          "ke Kanda". Konsol bersih (0 error). Butuh konfirmasi agen uji untuk peran sales
          dan gudang, termasuk isi tooltip.

  - task: "E5.3b — lencana lawan di Kartu Riwayat Produk (panel kanan setelah klik baris stok)"
    implemented: true
    working: "NA"
    file: "frontend/src/features/wms/inventory/ProductHistoryPanel.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: "NA"
        -agent: "main"
        -comment: |
          Komponen yang sama dipakai di panel riwayat. Belum dilihat langsung di layar.

metadata:
  created_by: "main_agent"
  version: "E-5-tutup"
  test_sequence: 4
  run_ui: true

test_plan:
  current_focus:
    - "E5.3b lencana badan usaha lawan di layar Mutasi (sales & gudang)"
    - "E5.3b lencana lawan di Kartu Riwayat Produk"
    - "User story 13: sales melihat stok HANYA badan usahanya + angka grup agregat"
    - "User story 5: sales tidak menemukan data badan usaha lain di layar stok"
    - "Regresi: kolom Dokumen tetap memakai nomor manusia, penyaring jenis mutasi tetap jalan"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

## agent_communication:
    -agent: "main"
    -message: |
      FASE E-5 DITUTUP di backend + frontend. Yang perlu Anda uji: LAYAR.
      * Akun: semua password `demo12345` (lihat memory/test_credentials.md).
        sales@kainnusantara.id (sales, rumah KSC) · warehouse@kainnusantara.id (gudang, KSC)
        · admin@kainnusantara.id (lintas entitas) · sales3@kainnusantara.id (sales, Kanda).
      * Deep-link: `?view=operations&tab=stok` → di dalamnya klik tab **Mutasi**
        (`data-testid="inventory-tab-ledger"`). Papan stok: `?view=inventory-board`.
      * Lencana lawan: `data-testid="movement-counterparty-<id_mutasi>"`,
        atribut `data-counterparty` (nama singkat) & `data-counterparty-direction` (in/out).
      * Penyaring jenis mutasi `data-testid="ledger-type-filter"` adalah **combobox Radix
        (button, BUKAN <select>)** → klik lalu pilih opsi, jangan `select_option`.
      * JANGAN uji drag-and-drop / kamera / suara.
      * Frontend TANPA hot reload → `bash /app/scripts/rebuild_frontend.sh` bila mengubah FE.
      * Bukti otomatis yang sudah hijau: `python backend/test_core_e5_visibility_poc.py`
        52/52 (dan terbukti MEMERAH 7 FAIL saat scope disabotase) · `bash scripts/gate.sh --ci`
        42 gate HIJAU.

#=====================================================================================
# ARSIP — riwayat fase sebelumnya (E-4) ada di atas blok FASE E-5 ini.
#=====================================================================================

---
## SESI 2026-08-11 (lanjutan) — FASE E-7 ANTAR-ENTITAS (E7a–E7h)

user_problem_statement: "lanjutkan development dari repo ini … verifikasi dan lanjutkan dari titik berhenti"
Keputusan pemilik sesi ini: urut G1→G2→G3 sampai E-7 tutup · kas grup: terapkan otomatis
yang buktinya jelas, sisanya jadi kasus keuangan (data demo boleh dibuat ulang) ·
seed aset tetap: boleh · konversi permintaan internal: admin & manager.

backend:
  - task: "E7a pagar pemasok Entitas grup (PO/PR/convert-to-po/realize-po/blanket/RFQ award/nonaktif cermin)"
    implemented: true
    working: true
    file: "backend/services/group_partner_service.py, services/pr_sourcing_service.py, services/purchase_requisition_service.py, services/blanket_po_service.py, services/rfq_service.py, routers/suppliers.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "KEBOCORAN NYATA ditemukan & ditutup: PR → convert-to-po/realize-po membuat PO biasa ke badan usaha grup (bukti KSC/PO-00013). Pagar dipasang di lapis service. POC E-7 52/52."
  - task: "E7b interco_returns pair_id+qty_total · nomor TRF ber-prefix entitas"
    implemented: true
    working: true
    file: "backend/services/interco_return_service.py, bootstrap.py, seed_realistic.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
  - task: "E7c HPP taksiran WAJIB BERLABEL (margin-report + eliminasi konsolidasi)"
    implemented: true
    working: true
    file: "backend/services/interco_margin.py, services/consolidation_service.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Angka otoritatif TIDAK diubah (INV-IC-03 tetap hijau); taksiran WAC + alasan dikirim terpisah & dilabeli di UI."
  - task: "E7d Permintaan Internal (internal_requests, <ENT>/PIN-#####) + konversi ke transaksi antar-PT"
    implemented: true
    working: true
    file: "backend/services/internal_request_service.py, routers/internal_requests.py, schemas_internal_request.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
  - task: "E7e kas tingkat grup DIHAPUS (pagar + migrasi berbukti + seed bersih)"
    implemented: true
    working: true
    file: "backend/services/cash_entity_service.py, routers/cash.py, routers/bank.py, scripts/migrate_e7_group_cash.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "13 transaksi 'all' dipetakan (12 berbukti, 1 → kasus keuangan). 8 titik penulisan kas grup diperbaiki. Data demo kini 0 kas grup."
  - task: "E7f pinjaman uang antar-PT (dokumen kembar + kas kembar + jurnal 2 buku + eliminasi)"
    implemented: true
    working: true
    file: "backend/services/interco_loan_service.py, services/interco_money_service.py, routers/interco_loans.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
  - task: "E7g pindah aset tetap antar-PT (nilai buku + masa manfaat sisa + eliminasi laba)"
    implemented: true
    working: true
    file: "backend/services/fixed_asset_service.py, routers/fixed_assets.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false

frontend:
  - task: "Lencana/pita 'Entitas grup' + tombol dimatikan di semua pemilih pemasok"
    implemented: true
    working: "NA"
    file: "frontend/src/components/GroupEntityBadge.jsx, features/admin/po/POCreateForm.jsx, features/purchasing/{PurchaseRequisitions,PrSourcingPanel,RFQCreateModal,BlanketPOCreateModal,SuppliersView}.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
  - task: "Layar Permintaan Internal (PIN) + tombol 'Minta dari badan usaha lain' di Papan Stok"
    implemented: true
    working: "NA"
    file: "frontend/src/features/internal_requests/*, features/inventory/InventoryStatusBoard.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
  - task: "Tab Pinjaman Antar-PT + aksi Pindah PT pada Aset Tetap + label HPP taksiran + teguran kas grup"
    implemented: true
    working: "NA"
    file: "frontend/src/features/finance/interco/{IntercoLoansPanel,IntercoMarginPanel}.jsx, features/finance/{FixedAssetsView,BankAccountsView,GroupConsolidationView}.jsx, features/purchasing/CashManagementView.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true

metadata:
  created_by: "main_agent"
  version: "E-7"
  test_sequence: 217
  run_ui: true

test_plan:
  current_focus:
    - "Layar Permintaan Internal (PIN) — sales ajukan, admin tindak"
    - "Lencana/pita 'Entitas grup' + tombol dimatikan"
    - "Tab Pinjaman Antar-PT (buat → cairkan → angsur)"
    - "Aset Tetap: Pindah PT + catat pembayaran"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "Backend E-7 sudah dibuktikan POC gabungan `backend/test_core_e7_interco_poc.py` 53/53 & terdaftar di gate.sh (gate --ci HIJAU). Yang perlu diuji agen: FRONTEND-nya. Akun: admin@kainnusantara.id / sales@kainnusantara.id (sandi demo12345). WAJIB pilih badan usaha KSC dulu di pemilih kanan atas (mode 'Semua Entitas' hanya-lihat). Jangan uji drag-and-drop/kamera/suara."


#====================================================================================================
# FASE E-8 GELOMBANG 1 — DUA PERAN BARU (`sales_admin` · `finance`)   [sesi 2026-08-14]
#====================================================================================================

user_problem_statement: |
  Lanjutkan development repo `iakakwanad/kn` (ERP/WMS Kain Nusantara). Titik henti sesi lalu:
  perbaikan parser id menu di `scripts/check_nav_map.py` (id sesudah baris komentar tertelan
  sehingga gate salah melapor "landing finance tidak ter-reach"). Titik henti sudah DIVERIFIKASI
  benar (gate nav-map PASS). Lanjut mengerjakan FASE E-8 GELOMBANG 1 sesuai plan.md.

backend:
  - task: "E8.1 Registry peran (6 peran) + izin efektif dikirim saat login + /api/roles"
    implemented: true
    working: true
    file: "backend/role_registry.py, backend/routers/auth.py, backend/permissions_config.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "POC `backend/test_core_e8_roles_poc.py` 64/64 (terdaftar di gate.sh). Registry terbukti identik dengan `config/roles.js` + `config/navMeta.js`."
  - task: "E8.2/E8.6 Pemisahan tugas: sales kehilangan faktur pajak, kwitansi AR, selisih bayar, pegging, mark-delivered"
    implemented: true
    working: true
    file: "backend/permissions_config.py, backend/bootstrap.py (sync_permission_revocations), backend/routers/pegging.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Pegging dipindah dari daftar peran ke izin `inventory.pegging` supaya layar & server memakai SATU kebenaran. POC: sales 403 · sales_admin lolos."
  - task: "CACAT BARU DITUTUP: mode gabungan 'Semua Entitas' untuk peran ber-penugasan banyak entitas"
    implemented: true
    working: true
    file: "backend/entity_scope.py, backend/routers/notifications.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Ditemukan empiris: Admin Sales bertugas di KSC+Kanda memilih 'Semua Entitas' hanya melihat 8 pesanan KSC (1 pesanan Kanda hilang tanpa pesan) DAN pagar tulis tidak menyala. Kini gabungan = seluruh `allowed_entity_ids` (isolasi tetap: daftar penugasan itu pagarnya) + tulis ditolak 409 menuntun."

frontend:
  - task: "US14 — sales tidak lagi menemukan tombol Terbitkan Faktur Pajak / Catat pembayaran / Tandai Diterima / Pegging"
    implemented: true
    working: "NA"
    file: "frontend/src/features/orders/OrderDetailPanel.jsx, features/crm/CollectionWorklist.jsx, features/wms/InventoryStockView.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
  - task: "US20 — Finance mendarat di Dasbor Keuangan & punya tombol pajak/uang masuk (dulu layar tanpa tombol)"
    implemented: true
    working: "NA"
    file: "frontend/src/features/finance/TaxInvoices.jsx, features/crm/CollectionWorklist.jsx, config/roles.js (ROLE_NAV)"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
  - task: "US21 — Admin Sales ditugaskan 2 badan usaha: berpindah konteks + mode gabungan benar"
    implemented: true
    working: "NA"
    file: "frontend/src/components/EntitySwitcher.jsx, backend/entity_scope.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
  - task: "Label peran di layar dari REGISTRY (dulu tampil 'Sales_admin')"
    implemented: true
    working: "NA"
    file: "frontend/src/components/{EntitySwitcher,OnboardingPanel,TourMenu}.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true

metadata:
  created_by: "main_agent"
  version: "E-8-G1"
  test_sequence: 220
  run_ui: true

test_plan:
  current_focus:
    - "US14 tombol uang/pajak HILANG untuk sales"
    - "US20 Finance: beranda + tombol pajak & catat pembayaran ADA"
    - "US21 Admin Sales: 2 badan usaha + mode gabungan"
    - "Label peran manusiawi (bukan Sales_admin)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "Backend E-8 G1 sudah dibuktikan POC `backend/test_core_e8_roles_poc.py` 64/64 + `bash scripts/gate.sh --ci` 50 gate HIJAU. Yang perlu diuji: FRONTEND. Kredensial lengkap di `memory/test_credentials.md` (9 akun, sandi `demo12345`). NAVIGASI: pakai deep-link `?view=<viewId>` (mis. `?view=orders`, `?view=tax-invoices`, `?view=finance-tower`, `?view=customers-crm`) — JANGAN klik teks grup sidebar (wrapper `nav-group-*` adalah div; yang bisa diklik `nav-group-toggle-*`). Jangan uji drag-and-drop/kamera/suara."

#====================================================================================================
# SESI 2026-08-19 — FASE T (TAHAPAN PROSES / SCREEN) — PENUTUPAN
#====================================================================================================

user_problem_statement: |
  "saya ingin anda lanjutkan development dari repo ini https://github.com/awawjahsada/kn —
  sebelumnya development berhenti disini saya ingin anda lanjutkan."
  Titik henti diukur ulang: FASE T (master Tahapan Proses termasuk SCREEN) sudah terbangun
  di backend + frontend, POC 62/62, TETAPI `gate.sh --full` MERAH 3 karena POC FASE T
  meninggalkan residu stok. Sesudah diperbaiki: gate --full HIJAU (0 FAIL, 290s).
  Keputusan pemilik sesi ini: (1) tutup T lalu kerjakan U · (2) panjang PANEL BERBEDA PER
  PESANAN (faktor disimpan di baris dokumen) · (3) sampling bawaan woven/knit=labdip+handfeel,
  printing=proofing, `bulk_sample` dinonaktifkan · (4) warna beda = barang DITAHAN, handfeel
  beda = peringatan; pelepas tahanan = MANAJER.

backend:
  - task: "FASE T — POC tahapan proses tidak boleh meninggalkan residu stok (INV-GATE-01)"
    implemented: true
    working: true
    file: "backend/test_core_tahapan_poc.py, backend/poc_stock_guard.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Terukur: satu kali POC FASE T meninggalkan inventory_movements +3 · inventory_rolls +2 · inventory_lots +1 (alur T2b Issue→Terima Hasil melahirkan roll/lot/mutasi yang tidak bisa dibalik per-dokumen). Akibat berantai: verify_data_integrity WARN 'drift persediaan vs GL 1-1300 Δ750.000' → POC G-6b memerah → INV-GATE-01 memerah. Diperbaiki dengan pola POC-RESIDU-01 (snapshot_stock/restore_stock). Bukti: POC 63 PASS/0 FAIL, gate_residue --check nol residu, verify_data_integrity 237 PASS/0 FAIL/0 WARN, gate.sh --full HIJAU 0 FAIL."

frontend:
  - task: "T-US1 — admin menambah tahap baru (mis. Sanforize) dari master Tahapan Proses; langsung muncul di pemilih langkah SPK makloon TANPA ubah kode/restart"
    implemented: true
    working: "NA"
    file: "frontend/src/features/settings/masters/EntityMastersView.jsx, features/settings/masters/masterFieldsConfig.js, features/purchasing/makloon/MakloonWizard.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
  - task: "T-US2 — staf printing membuat SPK dengan tahap SCREEN: mitra diminta, biaya tercatat, kain TIDAK berubah (qty keluar = qty masuk) & alasannya tertulis di estimasi"
    implemented: true
    working: "NA"
    file: "frontend/src/features/purchasing/makloon/MakloonWizard.jsx, MakloonStepEditor.jsx, features/purchasing/MakloonOrderDetailPanel.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
  - task: "T-US3 — manajer membuka SPK makloon lama: angka estimasi/biaya TIDAK bergeser"
    implemented: true
    working: "NA"
    file: "frontend/src/features/purchasing/MakloonOrdersView.jsx, MakloonOrderDetailPanel.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
  - task: "Regresi 3 layar lama (Pesanan · Purchase Order · Status Stok/Roll) tetap normal"
    implemented: true
    working: "NA"
    file: "frontend/src/features/orders/OrdersView.jsx, features/purchasing/PurchaseOrderManagement.jsx, features/wms/InventoryStockView.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true

metadata:
  created_by: "main_agent"
  version: "FASE-T-CLOSE"
  test_sequence: 221
  run_ui: true

test_plan:
  current_focus:
    - "T-US1 tahap baru dari master langsung terpakai di SPK"
    - "T-US2 tahap SCREEN = jasa (kain tidak berubah) + mitra + biaya"
    - "T-US3 SPK lama tidak bergeser"
    - "Regresi 3 layar lama"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "Backend FASE T dibuktikan POC `python backend/test_core_tahapan_poc.py` 63/63 + `bash scripts/gate.sh --full` HIJAU 0 FAIL. Yang perlu diuji: FRONTEND (user story T). Kredensial: `memory/test_credentials.md` (admin@kainnusantara.id / demo12345). NAVIGASI: pakai deep-link `?view=<viewId>` — `?view=entity-masters` (Master per Badan Usaha → pilih jenis 'Tahapan Proses'), `?view=makloon-orders` (Order Makloon), `?view=orders`, `?view=purchasing`, `?view=inventory-board`. JANGAN klik teks grup sidebar. Jangan uji drag-and-drop/kamera/suara. Setelah masuk WAJIB pilih badan usaha (PT Kain Suka Cita) karena mode 'Semua Entitas' hanya-lihat."

## HASIL SESI 2026-08-19 — FASE T DITUTUP (diperbarui main agent sesudah verifikasi sendiri)

backend:
  - task: "FASE T — POC tahapan proses tidak boleh meninggalkan residu stok (INV-GATE-01)"
    implemented: true
    working: true
    file: "backend/test_core_tahapan_poc.py, backend/poc_stock_guard.py"
    status_history:
        - working: true
          agent: "main"
          comment: "FIXED & TERBUKTI: POC 63/63 (T9 kini memeriksa 4 koleksi stok sebelum==sesudah), gate_residue --check nol residu, verify_data_integrity 237/0/0, gate.sh --full 90 gate HIJAU / 0 FAIL (291s)."

frontend:
  - task: "T-US1 — tahap dari master langsung terpakai di pemilih langkah SPK"
    implemented: true
    working: true
    file: "frontend/src/features/purchasing/makloon/MakloonWizard.jsx, MakloonStepEditor.jsx"
    needs_retesting: false
    status_history:
        - working: true
          agent: "testing"
          comment: "iteration_233: master Tahapan Proses tampil 10 baris; Screen ada dengan konfigurasi benar (tidak mengubah kain · dikerjakan mitra)."
        - working: true
          agent: "main"
          comment: "Diverifikasi sendiri di peramban: pemilih langkah SPK berisi 8 tahap SAH dari master (Tenun · Rajut · PFP · PFD · Celup · Screen · Printing · Proofing)."
  - task: "T-US2 — SPK tahap SCREEN: mitra diminta (peringatan bila kosong), kain TIDAK berubah, biaya masuk"
    implemented: true
    working: true
    file: "frontend/src/features/purchasing/makloon/MakloonWizard.jsx, MakloonOrderDetailPanel.jsx"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "testing"
          comment: "iteration_233: TIDAK selesai — 'modal overlay issue', disarankan uji manual."
        - working: true
          agent: "main"
          comment: "Akar 'modal overlay issue' ternyata BUG NYATA (P1) KN-UI-PICKER-REOPEN, bukan kendala otomasi: pop-up pemilih terbuka kembali karena dirender di dalam <label>. Sesudah diperbaiki (createPortal): alur selesai ujung-ke-ujung — SPK MKO-00006 tahap Screen, 25 yard masuk → 25 yard keluar, lencana 'Tidak mengubah kain — hanya biaya jasa', peringatan mitra muncul saat kosong lalu hilang setelah mitra dipilih, ongkos Rp 750.000 dari kontrak KSC/SCT-00008, tombol lanjutan 'Catat Jasa'. Dokumen uji sudah dihapus."
  - task: "T-US3 — SPK lama tidak bergeser angkanya"
    implemented: true
    working: true
    file: "frontend/src/features/purchasing/MakloonOrderDetailPanel.jsx"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "MKO-00001: EST. OUTPUT 109,44 identik, literal 'NaN' 0 kejadian, 'undefined' tidak ada."
  - task: "BUG P1 — pop-up pemilih (produk/mitra/warna) terbuka kembali setiap kali memilih"
    implemented: true
    working: true
    file: "frontend/src/components/ProductSelect.jsx, MakloonSelect.jsx, PantoneFinder.jsx"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Akar: pemicu+pop-up satu komponen dipakai di dalam <Field> = <label>; aktivasi label diteruskan peramban ke tombol pemicu. Perbaikan: createPortal ke document.body (3 komponen, 9 layar terdampak). Gate baru INV-UI-09 (verify_picker_portal.py, self-test 16 kasus). Bukti peramban: pop-up tersisa 0 sesudah memilih produk & mitra."
  - task: "Temuan agen uji yang TERBUKTI TUDUHAN PALSU (diverifikasi main agent)"
    implemented: true
    working: true
    file: "-"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "(1) 'NaN values detected' di orders/purchasing/makloon detail → literal 'NaN' 0 kejadian di ketiga layar (pencarian case-insensitive menangkap kata Indonesia ber-'nan' seperti 'Penanganan'). (2) 'Session expires quickly' → SESSION_TTL_HOURS=24 dengan perpanjangan otomatis (core_utils/dependencies)."

metadata:
  created_by: "main_agent"
  version: "FASE-T-CLOSED"
  test_sequence: 233
  run_ui: true

test_plan:
  current_focus:
    - "FASE U — dua satuan (roll + yard/kg/panel) di 15 koleksi"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "FASE T DITUTUP: gate.sh --full 90 gate HIJAU/0 FAIL, POC 63/63, user story T diuji lewat peramban oleh main agent sendiri. Dua bug ikutan ditutup (residu stok POC + KN-UI-PICKER-REOPEN P1 dengan gate baru INV-UI-09). CATATAN UNTUK AGEN UJI BERIKUTNYA: pemilih produk/mitra/warna sekarang ber-portal — sesudah mengklik baris, pop-up MENUTUP sendiri (data-testid product-select-modal / makloon-select-modal hilang). Berikutnya FASE U (dua satuan)."
