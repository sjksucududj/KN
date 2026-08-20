# AUDIT FORENSIK CODEBASE — Kain Nusantara ERP/WMS
**Tanggal:** 1 Juli 2026 · **Metode:** Static code audit menyeluruh + verifikasi empiris via API (clean seed) + gate internal proyek
**Cakupan:** Seluruh sistem (Sales/POS, WMS/Inventory, Purchasing, Finance/GL, Tax, CRM, HR, Multi-Entity, Security, Frontend/UX)
**Konteks:** Sistem ±50% dari visi akhir. Audit MEMBEDAKAN: (a) bug di domain yang SUDAH dikembangkan, (b) miss proses bisnis, (c) gap/enhancement di fitur yang jalan tapi belum optimal, (d) domain yang MEMANG BELUM dikembangkan (bukan bug).

**Klasifikasi:** `BUG` = perilaku salah terbukti · `MISS-PROSES` = menyimpang dari praktik ERP matang/standar akuntansi · `VALIDASI` = celah input · `USABILITY` = menyulitkan user · `ENHANCEMENT` = jalan tapi belum optimal · `BELUM-DEV` = memang belum dibangun
**Severity:** 🔴 Critical · 🟠 High · 🟡 Medium · ⚪ Low
**Bukti empiris** ditandai `[TERBUKTI]` — direproduksi langsung via API pada clean seed. Artefak uji (SO KSC/SO-00010–00012, JE-00017..19) masih ada di DB untuk verifikasi Anda; jalankan `bash scripts/seed_reset.sh` untuk membersihkan.

---

## 0. RINGKASAN EKSEKUTIF

| Domain | Status Dev | Kesehatan | Temuan Kunci |
|---|---|---|---|
| Sales/POS + Reservasi Roll | ✅ Matang | 🟢 Baik | Diskon manual TERBUKTI mati; pickup hold TERBUKTI jalan; 1 celah validasi + 1 bug cancel |
| WMS (Inbound/Outbound/Transfer) | ✅ Matang | 🟡 Cukup | Outbound list bocor antar-entitas [TERBUKTI]; scan-pick tak validasi roll |
| Inventory Roll-as-SSOT | ✅ Matang | 🟢 Baik | Invarian stok terjaga (109 PASS); risiko race split roll |
| Purchasing (PO/PR/RFQ/Blanket/3-way) | ✅ Matang | 🟢 Baik | Desain bagus (PO-pay ditutup satu pintu ke Vendor Bill) |
| **Finance/GL** | ✅ Ada | 🔴 **RAWAN** | **5 temuan Critical/High — GL belum bisa dipercaya sebagai laporan keuangan** |
| Tax (PPN/Faktur/PPh) | ✅ Ada | 🟡 Cukup | Perlu penyesuaian rezim PPN 12%/DPP 11-12 (Coretax) |
| CRM (leads, kredit, kolektor, insentif) | ✅ Ada | 🟢 Baik | Kredit gate + override solid |
| HR (absensi/payroll/PPh21) | ✅ Ada | 🟢 Baik | Jurnal payroll seimbang & anti double-count |
| Multi-Entity | ✅ Matang | 🟡 Cukup | 1 kebocoran scoping (outbound) |
| Security/Auth | ⚠️ Dasar | 🟠 Lemah | SHA256 tanpa salt, sesi tanpa expiry (diketahui, tapi wajib sebelum produksi) |
| Budget Control (P4) | ❌ Belum | — | BELUM-DEV (sesuai roadmap) |
| Multi-currency (P5) | ❌ Belum | — | BELUM-DEV |
| SMTP PO PDF (P3) | ❌ Blocked | — | Menunggu kredensial SMTP |
| Carrier/Omnichannel eksternal (F-5) | ❌ Belum | — | CRM internal ada; integrasi eksternal BELUM-DEV |

**Kesimpulan utama:** Lapisan operasional (Sales→WMS→Inventory→Purchasing) tergolong kuat, invarian stok dijaga gate otomatis, dan keputusan-keputusan owner terimplementasi dengan benar. **Titik paling rawan adalah jembatan Operasional→Akuntansi (GL)**: pengakuan pendapatan prematur, tidak ada jurnal balik saat pembatalan, persediaan GL tidak sinkron subledger (selisih Rp 533 juta), dan pembayaran tidak menyentuh GL. Jika laporan keuangan GL dipakai untuk keputusan/pajak hari ini, angkanya menyesatkan. Ini area perbaikan prioritas #1.

---

## 1. FINANCE / GL — 🔴 PRIORITAS TERTINGGI

### F-1 🔴 BUG [TERBUKTI] — Jurnal TIDAK dibalik saat Sales Order dibatalkan
- **Bukti:** SO `so_643d8a…` diposting via `POST /gl/sync` → `KSC/JE-00018` (Rp 210.900). SO kemudian di-cancel → status JE **tetap `posted`**. Pendapatan & piutang menggelembung permanen.
- **Akar:** `gl_service.void_entry()` (L377–390) hanya mengizinkan void jurnal `manual`; tidak ada hook reversal di `cancel_order` (`routers/sales_orders.py` L777) maupun di `expire_old_reservations`.
- **Dampak:** Revenue/AR overstated; trial balance "balanced" tapi SALAH secara substansi. Auditor eksternal akan menolak.
- **Rekomendasi:** Saat cancel/expire order yang sudah berjurnal → buat **jurnal reversal otomatis** (bukan delete; jaga audit trail): Dr Pendapatan+PPN / Cr Piutang, plus reversal HPP bila ada. Idempotent via `source_type="sales_order_reversal"`.

### F-2 🔴 MISS-PROSES [TERBUKTI] — Pengakuan pendapatan prematur (melanggar PSAK 72)
- **Bukti:** SO berstatus `reserved` (belum di-approve, belum dikirim, belum dibayar) ikut diposting `POST /gl/sync` sebagai pendapatan penuh.
- **Akar:** `gl_service.backfill_journals()` (L581–599) memposting SEMUA `sales_orders` kecuali `DEAD_STATUSES` (`cancelled/draft/expired/rejected`). Tanggal jurnal = `order.created_at`.
- **Standar ERP matang:** revenue diakui saat **penyerahan barang / invoice terbit** (SAP: billing document → FI; Odoo: invoice posting; Business Central: posted sales invoice). Bukan saat order dibuat.
- **Rekomendasi (bertahap):**
  1. Jangka pendek: batasi sync ke status `shipped/partially_shipped/done` (porsi terkirim) ATAU minimal `confirmed`.
  2. Jangka menengah: pindahkan trigger posting ke event `dispatch/mark-delivered` (pendapatan proporsional qty terkirim) + COGS dari roll AKTUAL yang dikirim.

### F-3 🔴 BUG/MISS-PROSES [TERBUKTI] — GL Persediaan tidak sinkron subledger (selisih Rp 533,7 juta)
- **Bukti:** Nilai fisik rolls × unit_cost = **Rp 533.712.500**; saldo GL `1-1300 Persediaan` = **Rp 750.000** (hanya dari retur). COGS terus MENGKREDIT 1-1300 → akun akan makin negatif seiring penjualan.
- **Akar:** (a) Tidak ada jurnal saldo awal persediaan; (b) Goods Receipt (`inbound/complete`, `routers/inbound_receiving.py` L246+) membuat `inventory_rolls` TANPA jurnal `Dr Persediaan / Cr GR-IR|Hutang`; (c) Vendor Bill juga tidak berjurnal (lihat F-5).
- **Rekomendasi:** (1) Jurnal opening balance persediaan sekali (Dr 1-1300 / Cr 3-1000 atau ekuitas saldo awal); (2) posting GR→GL otomatis (Dr Persediaan / Cr **akun perantara GR/IR 2-1150**); (3) laporan rekonsiliasi Inventory Valuation vs GL sebagai gate bulanan.

### F-4 🟠 BUG [TERBUKTI] — Pembayaran (simulate-payment) tidak membuat jurnal settlement
- **Bukti:** SO dibayar penuh via `POST /sales-orders/{id}/simulate-payment` (method `transfer`) → hanya JE pendapatan (Dr Piutang) + HPP. **Tidak ada Dr Kas / Cr Piutang.** Order berstatus `paid`, tapi Piutang GL tetap outstanding (TB: Piutang D=99,9jt tanpa kredit sama sekali).
- **Akar:** `routers/invoices.py` L27–82 → hanya memanggil `post_sales_order` + `post_order_cogs`. Jalur paralel `ar_receipts` justru BENAR (cash_transaction ref `ar_receipt` → Dr Kas / Cr Piutang). Dua jalur pembayaran, satu benar satu bocor.
- **Rekomendasi:** Satu pintu pembayaran ke **AR Receipt** (seperti PO→Vendor Bill yang sudah benar); ubah tombol "Bayar" di Orders agar membuat AR Receipt, atau tambahkan posting kas di simulate-payment. Tandai simulate-payment sebagai DEV-ONLY.

### F-5 🟠 MISS-PROSES — Vendor Bill tidak pernah diposting ke GL
- **Bukti kode:** `services/vendor_bill_service.py` — nol referensi jurnal/gl_service. Pembayaran bill (cash out `ref_type=vendor_bill`) mendebit `2-1100 Hutang` (gl_service L562) **tanpa kredit pengakuan hutang sebelumnya** → AP GL akan bersaldo debit (negatif) begitu bill dibayar.
- **Catatan positif:** 3-way match (PO↔GR↔Bill) di `evaluate_match` sudah ada dan bagus.
- **Rekomendasi:** Posting saat bill `posted`: `Dr Persediaan/GR-IR + Dr PPN Masukan (1-1500) / Cr Hutang Usaha`. Dengan F-3(2), GR/IR menjadi jembatan yang rapi.

### F-6 🟡 BUG [TERBUKTI] — Batas tanggal `as_of` Trial Balance memotong transaksi hari itu
- **Bukti:** `GET /gl/trial-balance?as_of=2026-07-01` (hari ini) → D=79,48jt; tanpa as_of → D=109,94jt. Jurnal bertanggal hari yang sama TIDAK terhitung.
- **Akar:** `gl_service.trial_balance` L773–774 membandingkan string `date <= "2026-07-01"` sedangkan `date` berformat timestamp penuh. `financial_statement_service` sudah benar (`_day_end`). Inkonsisten antar-laporan → angka TB ≠ Neraca di tanggal yang sama.
- **Fix:** pakai `_day_end(as_of)` juga di `trial_balance` & `account_ledger`.

### F-7 🟡 MISS-PROSES — COGS memakai rata-rata seluruh roll, bukan cost roll yang benar-benar keluar
- `gl_service._avg_unit_cost` (L446) merata-rata semua roll produk saat posting; padahal order tahu persis roll mana yang dikirim (unit_cost per roll ada). Ada juga engine kedua `costing_service.wac_for_product` (dipakai snapshot `item.unit_cost` saat create SO) → **dua sumber kebenaran costing** yang bisa berbeda dari waktu ke waktu.
- **Rekomendasi:** COGS = Σ(length × unit_cost roll aktual ter-dispatch); satukan engine costing (pakai `costing_service` di GL).

### F-8 🟡 MISS-PROSES — Akun Suspense menampung Rp 10 juta tanpa alur review
- Kas masuk berkategori tak dikenal jatuh diam-diam ke `1-9999` (kredit — berlawanan saldo normalnya). Tidak ada layar/report "Suspense harus nol".
- **Rekomendasi:** widget "Saldo Suspense ≠ 0" di GL + aksi reklasifikasi; wajib nol sebelum tutup buku.

### F-9 🟡 MISS-PROSES — Tutup buku: bulanan & tahunan saling mengunci; soft-lock tanpa recompute
- `closing_service._active_closing_overlapping` memblokir closing TAHUNAN bila ada closing bulanan (overlap) → praktik standar "close 12 bulan lalu close tahun" tidak bisa dijalankan.
- Soft-lock (by design): posting ke periode tertutup DIBOLEHKAN, tapi record `period_closings` (net_income snapshot) tidak dihitung ulang → snapshot bisa basi diam-diam.
- **Rekomendasi:** (a) closing tahunan = jurnal agregat sisa saja / diperbolehkan di atas closing bulanan; (b) bila ada posting backdate ke periode tertutup → tandai closing "STALE, perlu re-close" otomatis.

### F-10 🟡 COMPLIANCE — Rezim PPN 12% / DPP Nilai Lain (11/12) belum terwakili
- Konfigurasi sekarang: `ppn_rate: 11%` flat, DPP = subtotal (`config_service` L20, L218–237). Sejak 2025, tarif resmi 12% dengan **DPP Nilai Lain 11/12** untuk barang non-mewah (nilai rupiah sama, representasi Faktur Pajak/Coretax berbeda: kolom DPP, tarif, kode transaksi).
- **Rekomendasi:** dukung mode `dpp_nilai_lain` di compute_tax + snapshot faktur (`tax_invoice_service`), verifikasi dengan konsultan pajak sebelum lapor.

### F-11 ⚪ ENHANCEMENT — GL bergantung tombol "sync" manual
- Jurnal hanya lahir saat user menekan sync / saat bayar. Lupa sync = laporan basi tanpa indikasi.
- **Rekomendasi:** auto-post per event (order shipped, GR, bill posted, receipt) + badge "N dokumen belum berjurnal" di GL.

### F-12 ⚪ MISS-PROSES — Aging piutang dihitung dari tanggal ORDER, bukan invoice/pengiriman
- `ar_aging_service` L145: jatuh tempo = `created_at + term_days`. Barang yang dikirim 2 minggu setelah order langsung "menua" sejak order. Konsisten secara internal, tapi menyimpang dari praktik (aging dari tanggal invoice).

### F-13 ⚪ BUG-RINGAN — Dua fitur konsolidasi paralel + komponen mati
- `GET /gl/consolidation` (tanpa eliminasi) masih hidup; `ConsolidationDashboard.jsx` di-import `App.js` L20 tapi **tidak pernah dirender** (dead code). Yang aktif: `GroupConsolidationView` (dengan eliminasi intercompany — benar).
- **Rekomendasi:** hapus komponen mati + endpoint lama (atau redirect) agar tidak ada dua angka konsolidasi berbeda.

---

## 2. SALES / POS

### S-1 ✅ TERVERIFIKASI BENAR — Penghapusan diskon manual (keputusan owner)
- **Bukti:** POST SO dengan `discount_percent: 50` → tersimpan `0.0`; grand total tanpa potongan. Backend memaksa 0 (`routers/sales_orders.py` L297), FE menggate input (`allowItemDiscount/allowOrderDiscount = false`) + banner edukasi "Ajukan Harga Khusus". Jalur potongan satu-satunya = Special Price approval (validasi approved/berlaku/min-qty di L276–293). **Solid, defense-in-depth.**
- ⚪ Sisa: dead code `updateDiscount`, input diskon ter-gate, dan `order_discount_percent` di payload — bersihkan agar tidak dihidupkan tak sengaja (`CheckoutDrawer.jsx` L139, L303–315, L327–331; `useAppActions.js` L233).

### S-2 ✅ TERVERIFIKASI BENAR — Order Pengambilan (pickup) di-hold sampai tanggalnya
- **Bukti:** SO `ambil` + `pickup_date=2026-07-15` → task WMS `scheduled`, `hold_until` benar, scan-pick ditolak 400, auto-release saat due (`_auto_release_due_scheduled`) + tombol rilis manual + banner ungu di UI WMS. **Sesuai permintaan.**

### S-3 🟡 VALIDASI [TERBUKTI] — Backend menerima pickup TANPA tanggal
- **Bukti:** POST `fulfillment_method:"ambil", pickup_date:""` → **201 diterima**, task langsung `created` (tidak di-hold). FE memblokir, API tidak — celah untuk integrasi/mobile/API-call langsung.
- **Fix:** `create_order`: 400 bila `ambil` tanpa `pickup_date` valid (ISO, >= hari ini). Schema comment sendiri bilang "wajib" (`schemas.py` L329) tapi tak dienforce.

### S-4 🟠 BUG [TERBUKTI] — Cancel order confirmed meninggalkan task picking aktif
- **Bukti:** SO dikonfirmasi (task terbit) → cancel sukses → task `wms_55f67bce…` **tetap `created`** di antrean gudang. Operator bisa menyiapkan barang untuk order batal (dispatch memang akan gagal 409 karena roll sudah dilepas, tapi tenaga picking terbuang + antrean kotor).
- **Fix:** di `cancel_order` (L777–788): `db.wms_tasks.update_many({order_id, status ∉ [dispatched, cancelled]}, {$set:{status:"cancelled"}})` — pola ini SUDAH ada di PO short-close (`purchase_orders.py` L657) tinggal ditiru.

### S-5 🟡 BUG-SKALA — `create_order` hanya memuat 100 produk pertama
- `routers/sales_orders.py` L255: `db.products.find({}).to_list(100)` — katalog >100 SKU → item valid ditolak "Produk tidak ditemukan". Preview pakai 2000 (inkonsisten). Varian F1b (generate Cartesian) membuat 100 cepat terlampaui.
- **Fix:** query terarah `{"id": {"$in": [ids…]}}`.

### S-6 🟡 MISS-PROSES — Resolusi eskalasi `adjusted_qty` tidak menyentuh reservasi roll & nilai order
- `outbound_picking.py` L250–266: manajer menyesuaikan qty task + allocation, tapi roll reserved, `item.reserved_qty`, `total_amount/grand_total`, dan dokumen TIDAK ikut → stok "tersandera" selisihnya & tagihan tetap qty lama.
- **Fix:** lepas selisih roll (release parsial) + recompute item/pricing, atau minimal blok penyesuaian turun dengan instruksi buat retur/amend SO.

### S-7 🟡 USABILITY/PARITY — Mobile checkout tidak punya opsi Pengambilan
- `MobileCart.jsx` / `MobileCartSheet.jsx`: nol referensi `fulfillment_method/pickup` → sales lapangan tak bisa membuat order ambil-di-gudang; default diam-diam "kirim".

### S-8 🟡 KONSISTENSI-UOM — Task WMS & shipment menyimpan qty BASE tapi label unit = unit jual
- `fulfillment_status.py` L100–102: `quantity` = alokasi (base/meter) tapi `unit` = `item.unit` (mis. yard) → UI gudang bisa menampilkan "9.14 yard" padahal 9.14 meter. Sama di `shipment_service` L75 & Surat Jalan.
- **Fix:** set `unit = product.base_unit` (qty memang base), tampilkan unit jual hanya sebagai info.

### S-9 🟡 KONKURENSI — `_split_roll` tidak atomik
- `roll_service.py` L304–326: baca-lalu-update parent tanpa guard `length_remaining` → dua checkout bersamaan di roll yang sama dapat dobel-ambil sisa roll. `_reserve_single_roll` sudah atomik; split belum.
- **Fix:** `find_one_and_update({"id": roll_id, "length_remaining": {"$gte": take}}, {$inc: {length_remaining: -take}})`; retry planner bila gagal.

### S-10 🟡 SENSITIVITAS DATA — HPP (`unit_cost`) terekspos ke role sales
- `create_order` menyimpan snapshot `item.unit_cost` (L313–322) dan `GET /sales-orders` mengembalikannya apa adanya ke semua pemegang `order.view` (termasuk sales) → staf bisa menghitung margin perusahaan.
- **Rekomendasi:** strip `unit_cost` di respons untuk role non-manager/admin.

### S-11 ⚪ CATATAN BISNIS — Reservasi order `approved` ikut auto-expire 3 hari
- `inventory_service.expire_old_reservations` L105+ meng-expire juga status `approved`. Order yang sudah disetujui manajemen bisa hangus otomatis → perlu keputusan owner: apakah `approved` seharusnya kebal expiry (atau punya SLA berbeda)?

### S-12 ⚪ LAIN-LAIN
- `sales_name` default hardcoded "Ayu Marketing" (`schemas.py` L317) — order tanpa nama sales teratribusi keliru.
- `PATCH /sales-orders/{id}` tanpa guard status/entitas (bisa edit notes order `done`; minor).
- `GET /sales-orders` cap 200 tanpa paginasi — order lama hilang dari list saat volume naik (idem movements 500).

---

## 3. WMS / INVENTORY

### W-1 🟠 BUG-ISOLASI [TERBUKTI] — Daftar outbound tasks bocor lintas-entitas
- **Bukti:** `GET /outbound/tasks` dengan header `X-Entity-Id: ent_kanda` mengembalikan **7 task milik ent_ksc + 2 ent_kanda**.
- **Akar:** `list_outbound_tasks` (L26–52) tidak memanggil `resolve_list_scope` — padahal `wms_tasks` terdaftar WAJIB-scoped di `entity_scope.SCOPED_COLLECTIONS`, dan inbound (`inbound_receiving.py` L23) sudah benar. Endpoint `release/scan/dispatch` juga tanpa cek entitas.
- **Fix:** samakan dengan inbound: `query = resolve_list_scope("wms_tasks", query, ctx)`.

### W-2 🟡 MISS-PROSES — Scan-pick tidak memvalidasi roll terhadap reservasi order
- `scan_pick_item` (L74–164) menerima `roll_id` string apa pun tanpa cek "roll ini reserved/committed untuk order ini". Di tekstil (dye-lot!) salah ambil roll = komplain warna. Sistem sudah tahu roll yang benar (`reserved_ref.id = order_id`) tapi tidak dipakai untuk guard.
- **Fix:** bila `roll_id` diisi → validasi milik order & warehouse task; tolak dengan pesan yang menyebut roll yang benar. (Nilai tambah besar, effort kecil.)

### W-3 ⚪ TRACEABILITY — Split roll tidak menyimpan `parent_roll_id`
- Child roll hasil split (`_split_roll`, `ship_order_rolls`) tak menautkan parent → genealogi roll putus; menyulitkan telusur komplain/recall per lot fisik.

### W-4 ⚪ ENHANCEMENT — Rilis jadwal pickup & expiry reservasi bersifat lazy
- Keduanya hanya berjalan saat endpoint list dibuka. Cukup untuk sekarang; jadwalkan APScheduler (sudah di roadmap PRD) agar deterministik + notifikasi "order ambil hari ini".

### W-5 ⚪ VERIFIKASI-LANJUT — `_on_order_qty` mengasumsikan qty PO = base unit
- `roll_service.py` L107–120 menjumlah `po.items.quantity` langsung ke ATP; bila PO dibuat dalam unit non-base (roll/yard), incoming ATP salah. Perlu konfirmasi unit PO selalu base.

### W-6 ⚪ CATATAN DOKUMEN — Surat Jalan versi order-level menampilkan nilai uang & qty penuh
- `GET /outbound/so/{id}/surat-jalan` menampilkan `Total Rp order` (kebocoran harga ke kurir — SJ standar tanpa nilai) dan qty task penuh meski parsial. Versi per-shipment (`/shipments/{id}/surat-jalan`) sudah benar → pertimbangkan pensiunkan versi lama.

---

## 4. PURCHASING — kondisi baik
- ✅ Lifecycle PO (approval dinamis, amend + timeline, blanket/call-off, short-close yang MEMBATALKAN inbound tasks — pola yang benar), PR→PO, RFQ, reorder suggestion, supplier scorecard/price-list, landed cost.
- ✅ Keputusan desain bagus: `POST /purchase-orders/{id}/pay` sengaja diblokir → AP satu pintu via Vendor Bill (anti double-count).
- Temuan tersisa di sisi GL saja (F-5 di atas). 
- ⚪ ENHANCEMENT: belum ada "PO acknowledgement" supplier & needed-by date link ke lead time (sebagian sudah dirintis di supplier lead_time).

## 5. TAX
- ✅ Faktur Pajak keluaran (NSFP, replace/cancel), PPN Masukan (dedupe NSFP), Tax Center (PPh ringkas), PPN per-entitas PKP/non-PKP + tax_override per order.
- 🟡 F-10 (rezim 12%/DPP 11-12) di atas.
- ⚪ PPN Masukan (1-1500) belum pernah didebit dari Vendor Bill (ikut F-5) → SPT Masa PPN dari GL tidak akan cocok dengan register pajak masukan.

## 6. CRM & HR — kondisi baik (review ringan)
- CRM: leads board + convert, credit gate (warning/block + override sekali-pakai [dikonsumsi saat dipakai — benar]), collection worklist/reminders, insentif + akrual GL idempotent, sales targets/leaderboard. Solid.
- HR: absensi (shift/geofence/device), lembur 2 sumber (anti dobel), payroll → jurnal SEIMBANG dengan mode komisi accrue-then-settle yang **benar secara akuntansi** (memindah liability, bukan beban ganda), PPh21, BPJS. 
- ⚪ HR: koleksi HR belum terdaftar di ENTITY_REGISTRY (lihat G-1).

## 7. SECURITY / PLATFORM
| # | Sev | Temuan | Bukti | Rekomendasi |
|---|---|---|---|---|
| SEC-1 | 🟠 | Password = SHA256 + pepper statis (bukan bcrypt/argon2) | `core_utils.hash_password` L134 | Migrasi bcrypt (rehash saat login sukses). Wajib sebelum data user nyata |
| SEC-2 | 🟡 | Session token tanpa expiry/TTL + entropi 48-bit + tanpa rate-limit login | `auth.py` L18, `dependencies.py` L14 | TTL index Mongo pada sessions + token 128-bit + lockout percobaan login |
| SEC-3 | ⚪ | Audit log `role: "system/demo"` hardcoded — role pelaku tidak terekam | `dependencies.audit` L52 | Isi role aktor sungguhan |
| SEC-4 | ⚪ | Belum ada reset password/MFA (PRD-known) | — | Roadmap |

## 8. GATES / ENGINEERING (meta — standar proyek sendiri)
| # | Sev | Temuan | Aksi |
|---|---|---|---|
| G-1 | 🟡 | `verify_data_integrity` L0 **FAIL**: 8 koleksi (hr_* ×7, tax_pph_records) tidak terdaftar `ENTITY_REGISTRY.md` — self-drift yang aturan proyek sendiri larang | Daftarkan ke ENTITY_REGISTRY |
| G-2 | ⚪ | `verify_api_contract` ERROR palsu pada `FinancialStatementsView downloadCsv` (path dinamis `${API}${path}`) — endpoint export.csv nyatanya ADA. "Gate berisik = sama buruknya" (aturan §Blindspot) | Ajari gate pola `downloadCsv("/path", …)` |
| G-3 | ⚪ | `ux_audit` 2 ERROR: `BiFinanceView.jsx` tabel & chart tanpa empty-state | Tambah empty state |
| G-4 | ⚪ | Gate invarian belum memeriksa `Σ allocations.quantity == Σ roll reserved per order` (celah yang membuat S-6 lolos senyap) | Tambah invarian L4-ALLOC |

## 9. USABILITY (lintas modul)
| # | Sev | Temuan | Rekomendasi |
|---|---|---|---|
| U-1 | 🟡 | Navigasi admin ±71 menu — overload kognitif; pencarian menu belum menonjol | Regrouping + collapse per domain, "favorit/pin", command-palette (Ctrl+K) |
| U-2 | 🟡 | GL sync manual tanpa indikator dokumen belum-berjurnal (F-11) | Badge counter + auto-post |
| U-3 | ⚪ | List Orders/movements tanpa paginasi (cap 200/500) | Infinite scroll / pager |
| U-4 | ⚪ | Mobile: tidak ada pickup (S-7); RollPicker & rekonsiliasi roll sudah ada — bagus | Paritas fitur mobile |
| U-5 | ✅ | Returns & Special Orders: summary cards + seed demo ADA & tampil (2 retur, 4 special order) | — |
| U-6 | ⚪ | Suspense/anomali GL tak terlihat user (F-8) | Widget anomali di GL |

## 10. DOMAIN BELUM DIKEMBANGKAN (BUKAN BUG — jangan tercampur)
- **P3 SMTP PO PDF** — BLOCKED menunggu kredensial SMTP dari owner.
- **P4 Budget Control** — belum ada satu pun kode budget.
- **P5 Multi-currency/FX** — semua IDR (field currency ada di entitas, tapi tanpa engine kurs).
- **F-5 Integrasi carrier/omnichannel eksternal** (JNE/J&T, marketplace) — CRM omnichannel internal ada; konektor eksternal belum.
- **Produksi/BOM, Fixed Assets & depresiasi, Bank reconciliation otomatis (baru flag manual), Payment gateway nyata (simulated by design), PDF native (masih HTML print), Scheduler/cron (APScheduler direncanakan), WebSocket real-time, Multi-tenancy penuh, E-commerce portal, DMS, Forecasting/AI** — sesuai Tier roadmap PRD.

---

## 11. REKOMENDASI PRIORITAS (usulan urutan eksekusi)

**Gelombang 1 — Integritas Akuntansi (Critical): ✅ SELESAI (1 Jul 2026, diverifikasi manual + testing agent iteration_97 — 0 isu critical)**
1. ✅ F-1 Reversal otomatis JE saat cancel/expire (`reverse_order_journals`, net akun = 0, flag `reversed`).
2. ✅ F-2 Pendapatan hanya diakui utk order shipped/done ATAU terbayar (`_revenue_eligible`); tanggal JE = tanggal event (`_revenue_date`), bukan created_at.
3. ✅ F-3 GR→GL otomatis (Dr 1-1300 / Cr 2-1150 GR-IR) + tab Rekonsiliasi Persediaan di GL + Posting Saldo Awal (true-up Rp 532,9jt terposting, selisih kini 0).
4. ✅ F-4 simulate-payment order AR kini membuat settlement (Dr Kas / Cr Piutang via cash_transaction). ✅ F-5 Vendor Bill posted → Dr GR-IR + Dr PPN Masukan / Cr Hutang; AP tidak lagi bisa negatif.
5. ✅ F-6 `as_of` day-end di trial balance & ledger (konsisten dgn laporan keuangan).
   *Catatan sisa (minor, ke Gelombang berikut): reversal parsial utk order partial-shipment; purchase-return/QC-reject belum membalik GR-IR; refund kas saat cancel order terbayar.*

**Gelombang 2 — Operasional: ✅ SELESAI (2 Jul 2026, uji empiris API + gate invarian 64 PASS + sweep 0×5xx)**
6. ✅ S-4 Cancel SO → task picking outbound ikut dibatalkan (`cancel_reason: "SO dibatalkan"`).
7. ✅ W-1 Outbound tasks kini ter-scope entitas (list via `resolve_list_scope`; 5 endpoint mutasi ber-guard `assert_entity_access`).
8. ✅ S-3 Validasi backend pickup: `ambil` tanpa tanggal → 400; tanggal lampau → 400.
9. ✅ S-5 Lookup produk terarah by-id di create_order & preview (cap 100/2000 dihapus).
10. ⏸ W-2 Validasi roll scan-pick — DITUNDA per keputusan owner (akan pakai RFID).
11. ✅ S-6 `adjusted_qty` eskalasi kini sinkron penuh: partial roll release (`release_order_rolls_partial`), allocation+item (`reserved_qty` ikut turun), repricing order (total/DPP/PPN/grand), timeline; guard: tak boleh naik, tak boleh < picked, blok bila order sudah dibayar.
12. ✅ S-9 `_split_roll` atomik (guard `length_remaining` + `$inc`; planner lanjut ke roll lain bila kalah race).

**Gelombang 3 — Kualitas & Kepatuhan:**
13. F-10 PPN 12%/DPP 11-12. 14. SEC-1/2 bcrypt + session TTL. 15. S-10 strip unit_cost utk sales. 16. G-1..G-4 rapikan gate. 17. U-1 navigasi. 18. F-7 unifikasi costing. 19. F-8 workflow suspense. 20. F-9 closing tahunan.

**Gelombang 3 — Penutup (F-7/F-8/F-9): ✅ SELESAI (2 Jul 2026, uji testing-agent backend 13/13 + FE 100%, semua gate hijau).**
- ✅ **F-7 Unifikasi costing** — `gl_service._order_item_unit_cost()` menghitung HPP dari roll yang benar-benar terkirim (match `reserved_ref.id`), fallback snapshot `item.unit_cost`, lalu `costing_service.wac_for_product`. Dipakai di `post_order_cogs`. Trial balance tetap seimbang.
- ✅ **F-8 Workflow suspense (1-9999)** — `GET /api/gl/suspense` (saldo+daftar) & `POST /api/gl/suspense/reclass` (JE seimbang). UI: tab **Suspense** di Buku Besar (`SuspensePanel.jsx`, testid `gl-tab-suspense`/`suspense-*`) + peringatan saldo≠0 di pratinjau tutup buku (`closing-preview-suspense`).
- ✅ **F-9 Closing tahunan + STALE** — closing TAHUNAN kini boleh di atas closing bulanan (hanya menutup **residual** = operasional − yang sudah ditutup, di-net-kan; buku tetap seimbang, tanpa dobel). Posting/void jurnal backdate ke periode tertutup → flag **STALE** (`_mark_stale_closings`), UI badge "Basi" + tombol **Tutup Ulang** (`POST /finance/closing/{id}/reclose`) yang menghitung ulang jurnal penutup. Reclose bulan me-re-stale tahun yang memuatnya.
- Baseline gate setelah Gelombang 3 penutup: verify_contract OK, verify_api_contract **0 ERROR**, verify_data_integrity **119 PASS/0 FAIL** (FKT-1 diperbarui utk DPP Nilai Lain F-10: `grand==net_subtotal+ppn`), validate_compliance 4 FAIL tersisa (pra-ada: `sales_orders.py` 832>800, `CheckoutDrawer.jsx` 509>500 — di luar scope Finance).

**Kebersihan kode:** hapus dead code diskon (CheckoutDrawer), `ConsolidationDashboard.jsx` + `/gl/consolidation`, default "Ayu Marketing", SJ order-level lama.

---
*Dokumen ini dihasilkan dari audit forensik statis + empiris. Semua temuan [TERBUKTI] direproduksi pada clean seed 1 Jul 2026; artefak uji masih di DB (SO KSC/SO-00010..12, JE KSC/JE-00017..19). Baseline gate: integrity 118 PASS/1 FAIL (G-1), endpoint sweep 0×5xx, ux_audit 2 ERROR (G-3).*
