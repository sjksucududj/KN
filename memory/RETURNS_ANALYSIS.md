# ANALISIS MENDALAM — MODUL RETUR (Retur Jual & Retur Beli)
> Status: ANALISIS SAJA (belum eksekusi). Sumber: pembacaan kode aktual per iterasi ini.

## A. Ekspektasi bisnis (rangkuman dari penjelasan user — untuk dikonfirmasi)

Dua jenis retur dalam SATU rantai proses yang berkaitan:

### Rantai 1 — Retur Jual (customer → KN), berbasis SO
1. SO completed → dikirim ke customer.
2. Customer cek mandiri → temukan defect → hubungi sales-nya.
3. Customer kirim bukti + syarat ke sales.
4. Sales eskalasi ke atasan + lampirkan bukti.
5. Atasan: **approve** atau **reject**.
6. Jika approve → **INSPECT dulu** (belum ada fitur dedicated) sebelum benar-benar selesai.
7. Hasil inspect = 4 kemungkinan OUTPUT retur:
   - (1) Retur diterima → **kembalikan uang (refund)**.
   - (2) Retur diterima → **potong bon/tagihan berikutnya** (kredit ke pembelian customer selanjutnya).
   - (3) Retur **di-nego** → barang TIDAK diterima balik, dikembalikan ke customer, tapi diberi **diskon/harga lebih murah** (potong harga, tanpa barang masuk).
   - (4) Retur **ditolak sepenuhnya**.
   - Catatan qty: dari 1 SO bisa **semua roll** atau **sebagian** (sisanya dikirim balik ke customer).
8. Jika diterima (case 1 & 2) → barang **masuk kembali ke gudang**.
   - Gudang tujuan retur **bisa beda entitas** dari entitas pembelian (mis. beli di Kanda, barang retur di Sukacita). Sistem WAJIB tahu: **barang ini milik siapa & ada di mana**, qty ter-track jelas di inventory beserta **status qty**.
9. Dari titik ini bisa lanjut ke **Rantai 2 (Retur Beli)** — KN usaha retur ke supplier. (2 flow beda tapi berkaitan, bisa jadi 1 flow.)

### Rantai 2 — Retur Beli (KN → supplier)
1. Admin/user harus tahu: barang ini **beli dari supplier mana, kapan, PO no berapa, invoice mana**.
2. User kontak supplier → request retur → **diterima / ditolak**.
3. Variasi status:
   - Ditolak, barang **belum** dikirim ke supplier.
   - Ditolak, barang **sudah** diterima supplier.
   - Diterima untuk diretur.
4. Jika **diterima**: **refund uang** ATAU **potong bon pembelian berikutnya** (kurangi AP).
5. Jika **ditolak**: barang **masuk gudang sebagai stok**, dan **grade bisa berubah** (A→B) karena defect.

### Retur Policy (BELUM ADA)
- **Retur policy jual**: bisa dilampirkan ke dokumen legal proses SO.
- **Retur policy beli**: **beda-beda per supplier** → sistem harus simpan policy tiap supplier.
- Policy beli **menjadi dasar** policy jual (LINKED). Contoh: supplier A max terima retur 1 bulan dari tgl beli → deadline retur jual otomatis = tgl beli supplier + 1 bulan. Ada juga policy lain yang berdiri sendiri.

### Kasus terpisah — Retur dari receiving PO (bukan dari customer)
- Saat **inspect penerimaan barang PO**: ada qty reject / salah kirim (tidak sesuai PO) → buat **retur beli** langsung (tanpa rantai customer).

Dimensi lain: **multi-role**, **approval** berjenjang, dampak ke **Finance**. Modul terdampak: Sales, MD (master data), Gudang, Finance, **Inspect**.

---

## B. Kondisi SAAT INI (as-is, grounded di kode)

### B.1 Retur Jual — `services/return_service.py`, `routers/sales_returns.py`, koleksi `sales_returns`
- State machine: `draft → pending_approval → approved | rejected`. **Hanya 1 langkah approve** (bukan berjenjang).
- Create: pilih `order_id`, `return_type` ∈ {retur, bs, penggantian, komplain, garansi}, items {product_id, quantity_returned, unit, reason, **condition: ok|damaged**}, notes, attachments (bukti foto). Ada guard R1-06 (qty retur ≤ terkirim/terjual, akumulatif).
- Approve (`approve_and_adjust_stock`): LANGSUNG (a) buat **roll baru** `origin_type=return`, status `available`, condition ok/damaged, di warehouse hasil `_resolve_return_warehouse` (ambil dari outbound task SO, fallback gudang pertama), owner = `ret.entity_id`; (b) catat movement `return_in`; (c) rebuild_balance; (d) buat **Credit Note (CN-)** + posting GL reversal (revenue/PPN/COGS; refund cash vs pengurang AR ditentukan dari metode bayar order). Idempotent.
- Reject: set status rejected.
- Attachments: upload/download/delete (bukti).

**Yang TIDAK ada:**
- ❌ Tidak ada langkah **INSPECT** khusus retur jual (approve langsung bikin stok + CN).
- ❌ Tidak ada **4 outcome** (refund / potong bon / nego-diskon / reject-sebagian). Approve = selalu barang masuk + Credit Note. `condition=damaged` hanya info (COGS reversal di-skip), tak ada alur nego (barang tak masuk tapi diskon) atau "potong bon berikutnya" eksplisit sebagai store-credit.
- ❌ Tidak ada pemilihan **gudang & entitas tujuan retur** oleh user (auto-resolve saja) → kasus "beli di Kanda, retur di Sukacita" tidak tertangani eksplisit.
- ❌ Tidak ada **link ke retur beli** (rantai 2). Dua dokumen tak saling tahu.
- ❌ Tidak ada **retur policy** / window / eligibility check berbasis policy.
- ❌ Approval tidak lewat engine berjenjang (`approval_requests`/`approval_rules`) & tidak lewat modul **Eskalasi**.

### B.2 Retur Beli — `services/purchase_return_service.py`, `routers/purchase_returns.py`, koleksi `purchase_returns`
- State machine: `draft → pending_approval → approved | rejected`. **1 langkah approve**.
- Create: pilih supplier/PO/warehouse/entity, items {product_id, quantity, price, reason ∈ cacat|salah_kirim|kelebihan|lain, condition, **roll_ids** (retur PRESISI per roll/lot)}. Bisa tanpa PO. Enrich harga dari roll/PO/produk. Ada `source-rolls` untuk pilih roll asal (menelusuri supplier/invoice/PO via traceability).
- Approve (`approve_and_adjust_stock`): kurangi roll available (FIFO atau roll spesifik) → status roll jadi `returned_supplier` (terminal) atau split; movement `return_out`; terbitkan **Nota Debit (DN-)**; kurangi AP (`purchase_orders.returned_amount` + recompute payment status); posting GL retur beli (Dr Hutang/GR-IR, Cr Persediaan [+reversal PPN]).
- Reject / delete(draft) tersedia.

**Yang TIDAK ada:**
- ❌ Tidak ada status "diminta ke supplier / dikirim ke supplier / diterima supplier / ditolak supplier". Approve = langsung barang keluar + Nota Debit. Tak ada sub-state "barang belum dikirim" vs "sudah diterima supplier".
- ❌ Outcome hanya "kurangi AP (Nota Debit)". Tidak ada opsi **refund tunai** eksplisit, dan tidak ada penanganan **ditolak supplier → barang balik jadi stok + ubah grade (A→B)**.
- ❌ Tidak ada **retur policy per supplier** / eligibility window.
- ❌ Tidak ada **link ke retur jual** (asal barang dari customer return).
- ❌ Approval 1 langkah (bukan berjenjang / eskalasi).

### B.3 Inspect / QC — `services/qc_inspection_service.py`, `routers/qc_inspection.py`
- **INBOUND-only** 4-point inspection saat receiving PO: hitung poin defect → Grade A/B/C (ambang configurable), catat GSM/lebar aktual per roll, set `roll.grade`. **Tidak** ada aksi karantina/retur otomatis, **tidak** ada inspeksi untuk retur jual.
- **Tidak ada** jembatan otomatis "reject saat receiving PO → buat retur beli". (Retur beli dibuat manual, walau bisa refer PO.)

### B.4 Finance
- Retur jual → **Credit Note (CN-)** + GL reversal (koleksi `credit_notes`).
- Retur beli → **Nota Debit (DN-)** + kurangi AP + GL (`gl_service.post_purchase_return`).
- Belum ada: store-credit/"potong bon berikutnya" sebagai saldo yang bisa dipakai order berikut; refund tunai eksplisit untuk retur beli; jurnal untuk skenario nego (diskon tanpa barang) & regrade.

### B.5 Master Data / Supplier
- `SupplierCreate` punya: name, npwp, pic, phone, email, address, city, goods_type, payment_term_code, **lead_time_days**, entity_id, notes. **TIDAK ada field return policy** (window hari, mode refund, syarat, RMA required, restocking fee, dll).

### B.6 Frontend
- `SalesReturns.jsx` (299 baris): tab status + stats per-status (dihitung dari list penuh — inilah alasan belum saya migrasi ke paginasi P2), create modal (pilih order → items → type → condition → notes → attach), approve/reject.
- `PurchaseReturns.jsx` (443 baris): tab status + stats, create modal (supplier/PO/warehouse/items + RollPicker presisi), submit/approve/reject/delete.
- Keduanya: **tidak** ada layar inspect, tidak ada wizard outcome, tidak ada tampilan ownership/lokasi tujuan, tidak ada link antar-retur, tidak ada policy.

### B.7 RBAC / Approval
- Roles: admin, manager, sales, warehouse (+ HR). Returns pakai permission `sales_return`/`purchase_return` (view/create/update/approve/reject) — **approve 1 langkah**, TIDAK terhubung ke engine `approval_requests`/`approval_rules` maupun modul Eskalasi.

---

## C. GAP ANALYSIS (ekspektasi vs saat ini)

| # | Kebutuhan | Saat ini | Gap |
|---|-----------|----------|-----|
| G1 | Inspect dedicated untuk retur jual sebelum finalisasi | Tidak ada (approve langsung stok+CN) | **Besar** — perlu tahap inspect + hasil |
| G2 | 4 outcome retur jual (refund / potong bon / nego-diskon / reject) + partial per roll | Hanya "approve=barang masuk+CN" | **Besar** |
| G3 | Pilih gudang+entitas tujuan retur; tracking ownership & lokasi & status qty | Auto-resolve warehouse, owner=entity dok | **Sedang** — perlu input & kejelasan cross-entity |
| G4 | Link Retur Jual → Retur Beli (rantai) | Tidak ada | **Besar** |
| G5 | Retur beli: sub-status (diminta/dikirim/diterima/ditolak supplier) | Hanya approved/rejected | **Besar** |
| G6 | Retur beli outcome: refund vs potong bon; ditolak→stok+regrade | Hanya Nota Debit (kurangi AP) | **Besar** |
| G7 | Return policy per supplier + turunkan ke policy jual (linked) | Tidak ada | **Besar** |
| G8 | Retur beli dari inspect receiving PO (qty reject/salah kirim) | Manual, tak otomatis dari QC | **Sedang** |
| G9 | Approval berjenjang + eskalasi + bukti | Approve 1 langkah | **Sedang** |
| G10 | Finance: store-credit, refund tunai, jurnal nego & regrade | CN & DN dasar saja | **Sedang–Besar** |
| G11 | Multi-role kejelasan (sales, atasan, gudang, QC, finance, purchasing) | Permission ada, workflow peran belum eksplisit | **Sedang** |

---

## D. DESAIN TARGET (usulan, untuk didiskusikan)

### D.1 Model status terpadu (2 flow saling terhubung)

**Retur Jual (sales_returns) — status baru:**
```
draft → submitted(pending_approval) → approved(atasan)
      → inspecting → inspected
      → [outcome]:
          refund_settled        (uang dikembalikan; barang masuk gudang)
          credit_settled        (potng bon/stor-credit; barang masuk gudang)
          nego_settled          (diskon; barang TIDAK masuk — tetap di customer)
          rejected              (ditolak; tak ada dampak stok/finance)
      → (opsional) linked_to_purchase_return  (barang lanjut diretur ke supplier)
```
- Per-item / per-roll: qty diterima balik vs dikirim ulang ke customer (partial). Outcome bisa **beda per item**.

**Retur Beli (purchase_returns) — status baru:**
```
draft → submitted → approved(internal)
      → requested_supplier (diminta ke supplier)
      → shipped_supplier (barang dikirim ke supplier)
      → accepted_supplier → [refund | ap_credit] settled
      → rejected_supplier → goods_back (stok masuk lagi, opsi regrade A→B)
      → rejected(internal)
```
- Bisa dibuat dari: (a) rantai retur jual (link `origin_sales_return_id`), (b) manual, (c) **inspect receiving PO** (link `origin_qc_task_id`/`po_id`).

### D.2 Modul INSPECT diperluas (unified inspection)
- Jadikan entitas `inspections` generik dgn `context` = `inbound_po` | `sales_return` | `purchase_return_back`.
- Retur jual: setelah atasan approve → task inspect → inspector nilai kondisi per roll (pakai/format 4-point yang sudah ada) → rekomendasi outcome (accept-refund/credit, nego, reject) + grade + apakah barang layak masuk stok / layak diretur ke supplier.
- Reuse `qc_inspection_service` (compute_points/grade) agar konsisten.

### D.3 Return Policy Engine (MD)
- `supplier_return_policies` (atau embed di supplier): `window_days`, `refund_modes` (refund/ap_credit), `rma_required`, `restocking_fee_pct`, `condition_requirements`, `notes`, `valid_from/until`.
- Turunan ke retur jual: saat SO dibuat/retur diajukan, hitung `return_deadline = tgl_terima_barang_dari_supplier + window_days` (linked). Simpan snapshot policy di dokumen SO/retur agar auditable.
- `sales_return_policies` (global/per-kategori/per-customer) untuk aturan yang berdiri sendiri (mis. window jual, biaya, jenis yang boleh diretur). Lampirkan ringkasan ke dokumen legal SO.
- Eligibility check saat create retur (blok/peringatan bila di luar window).

### D.4 Inventory / Ownership & Lokasi (kunci akurasi)
- Saat barang masuk balik: **user pilih** `return_warehouse_id` + `owner_entity_id` tujuan (default cerdas dari SO, tapi bisa beda entitas). Roll baru menyimpan `origin_type=customer_return`, `source_sales_return_id`, `grade` hasil inspect, `condition`.
- Status qty jelas: available / quarantine (menunggu keputusan retur beli) / returned_supplier. Usulkan status roll baru **`quarantine`/`pending_supplier_return`** agar barang defect tidak langsung terjual sebelum keputusan.
- Cross-entity: catat jelas owner vs lokasi; laporan stok & traceability mengikuti (sudah ada engine roll SSOT + traceability yang bisa dipakai).

### D.5 Finance
- Retur jual:
  - refund → kas keluar / bank; credit → **store-credit** (saldo customer) atau pengurang AR; nego → **credit note diskon** tanpa COGS reversal (barang tak masuk); reject → tak ada jurnal.
  - Perlu koleksi **store_credit / customer_credit_balance** bila outcome "potong bon berikutnya" dipilih, agar bisa dipakai di order berikut.
- Retur beli:
  - accepted+refund → kas/bank masuk; accepted+ap_credit → Nota Debit (kurangi AP, sudah ada); rejected_supplier→goods_back → balikkan stok (mungkin regrade) + **reversal Nota Debit** bila sudah terbit; regrade menyesuaikan nilai persediaan.
- Semua state transition yang berdampak uang → jurnal GL yang sesuai + idempotent.

### D.6 RBAC / Approval / Eskalasi
- Peran eksplisit: **Sales** (buat retur jual, lampirkan bukti) → **Atasan/Manager** (approve/reject via **modul Eskalasi/Approval engine** berjenjang) → **QC/Inspector** (inspect) → **Gudang** (terima fisik, putaway, regrade) → **Purchasing** (ajukan retur beli ke supplier) → **Finance** (settle refund/credit/nota).
- Integrasikan ke `approval_requests`/`approval_rules` (threshold nilai, multi-level) alih-alih approve 1 langkah.

### D.7 Link antar-flow (rantai)
- Field `origin`: `sales_return.linked_purchase_return_id` ↔ `purchase_return.origin_sales_return_id`.
- Dari detail Retur Jual yang barangnya masuk (defect) → tombol "Ajukan Retur Beli ke Supplier" yang mem-prefill supplier/PO/invoice/roll asal (via traceability yang sudah ada).

---

## E. MODUL TERDAMPAK
- **Sales**: create retur jual, bukti, tampilan status/outcome, sisa kirim-ulang.
- **Master Data**: return policy per supplier + policy jual; snapshot ke dokumen.
- **Inspect/QC**: perluas jadi unified inspection (inbound + retur jual + barang balik dari supplier).
- **Gudang/Inventory**: pilih gudang+entitas tujuan, quarantine, regrade, ownership & lokasi, movement baru.
- **Purchasing**: retur beli dgn sub-status supplier + dari receiving reject.
- **Finance**: CN/DN, refund tunai, store-credit, jurnal nego/regrade, reversal.
- **Approval/Eskalasi**: berjenjang + threshold + audit.
- **Traceability/Docs**: telusur asal beli (PO/invoice/roll), dokumen legal SO memuat policy.

---

## F. KEPUTUSAN/PERTANYAAN yang perlu Anda jawab sebelum eksekusi
1. **Outcome "potong bon berikutnya"** (jual & beli): buat sistem **store-credit/saldo** yang bisa dipakai transaksi berikut, atau cukup pengurang AR/AP saja?
2. **Approval**: pakai engine berjenjang (`approval_rules` + threshold nilai) & modul Eskalasi, atau tetap 1 langkah approve manager?
3. **Inspect retur jual**: wajib untuk semua retur, atau hanya jika return_type tertentu / di atas nilai tertentu?
4. **Quarantine**: setuju tambah status roll `quarantine`/`pending_supplier_return` agar barang defect tak terjual sebelum keputusan retur beli?
5. **Cross-entity**: bagaimana perlakuan akuntansi bila barang retur masuk entitas berbeda dari entitas jual/beli (inter-entity transfer otomatis atau cukup catat owner+lokasi)?
6. **Return policy**: field minimum per supplier (window_days, refund_modes, rma_required, restocking_fee, condition) — apakah cukup, ada lagi?
7. **Nego (case 3)**: barang tetap di customer + diskon — apakah menerbitkan Credit Note diskon (kurangi AR/refund) tanpa gerak stok? Konfirmasi.
8. **Prioritas build**: mulai dari mana? (usulan urutan di bawah)

---

## G. USULAN RENCANA IMPLEMENTASI BERTAHAP (draft, low-risk dulu)
- **R0** — Return Policy (MD): field policy per supplier + policy jual + eligibility/deadline (fondasi, low risk).
- **R1** — State machine + outcome retur jual (refund/credit/nego/reject) + partial; simpan tanpa mengubah finance dulu (feature-flag).
- **R2** — Unified Inspect untuk retur jual (reuse QC 4-point) → grade + rekomendasi outcome + quarantine.
- **R3** — Ownership/gudang tujuan + regrade + status roll quarantine/pending_supplier_return.
- **R4** — Link → Retur Beli dgn sub-status supplier (requested/shipped/accepted/rejected) + outcome refund/ap_credit + ditolak→goods_back+regrade.
- **R5** — Finance lengkap: store-credit, refund tunai, jurnal nego/regrade, reversal DN/CN.
- **R6** — Approval berjenjang + Eskalasi + audit + dokumen legal (policy di SO).
- **R7** — UI/UX: wizard retur (jual & beli), layar inspect, tampilan rantai & ownership, paginasi (sekalian tuntaskan P2 returns).
- Tiap tahap: uji via testing agent + jaga guardrail (kontrak API, ux_audit) + idempotensi GL.

---

# PART II — KEPUTUSAN FINAL (LOCKED) & RENCANA REVISI

## H. Keputusan user (terkunci)
1. **Store credit/saldo**: YA — bangun sistem saldo customer (dipakai transaksi berikut). Outcome "potong bon berikutnya" = tambah saldo store-credit.
2. **Approval**: **1 langkah (Manager)** — TIDAK pakai engine berjenjang/eskalasi. Sederhana: Sales ajukan → Manager approve/reject.
3. **Inspect retur jual**: **WAJIB untuk semua** retur jual (setelah manager approve → tahap inspect sebelum finalisasi outcome).
4. **Quarantine**: SETUJU — tambah status roll `quarantine`/`pending_supplier_return` (barang defect tak boleh terjual sebelum keputusan retur beli).
5. **Cross-entity**: pakai pendekatan terbaik + sadar kasus SO intercompany + fleksibel inter-entity transfer agar minim opex (detail di §I).
6. **Return policy fields**: extensible — user bisa menambah field custom.
7. **Nego (case 3)**: YA — Credit Note diskon (kurangi AR / refund) **tanpa** gerak stok.
8. **Urutan**: ikut rekomendasi R0→R7.
9. **[TAMBAHAN] Impor vs Lokal**: barang bisa **impor** atau **lokal**, sumber tetap **supplier**. Klasifikasi ini **memengaruhi return policy** (detail di §J). Masuk ke R0.

## I. Desain Cross-Entity (Q5) — rekomendasi
Prinsip: **roll SSOT memisahkan `owner_entity_id` (kepemilikan) vs `warehouse_id` (lokasi fisik)**, jadi tidak perlu pindah barang fisik untuk membenahi akuntansi.

- **Default retur jual masuk**: `owner_entity_id` = **entitas penjual SO**; `warehouse_id` = gudang tujuan yang **dipilih user** (boleh gudang yang dioperasikan entitas lain). → Barang bisa "nyimpan" di lokasi entitas lain tanpa pindah kepemilikan. Minim opex (tak ada mutasi fisik/akuntansi bila tak perlu).
- **Bila kepemilikan perlu pindah** (mis. agar entitas lokasi yang meretur ke supplier / menjual ulang): sistem **menawarkan Inter-Entity Transfer** memakai engine `InterCompanyTransfers` yang sudah ada → jurnal antar-entitas (AR/AP inter-co) benar, tetap tanpa mutasi fisik.
- **Kasus SO Intercompany**: bila SO asal adalah rantai intercompany (barang milik entitas B dijual via entitas A), saat retur:
  - Rekam `origin_entity_chain` dari SO (snapshot) → default kembalikan kepemilikan ke titik yang konsisten dengan rantai asal (mis. entitas B), ATAU tawarkan **reversal** transfer intercompany asal.
  - Semua keputusan owner/lokasi ditampilkan eksplisit ke user + dapat dikoreksi manual (fleksibel).
- **Retur beli lintas entitas**: retur ke supplier dilakukan oleh entitas **pemilik** roll saat itu; bila pemilik ≠ entitas pembeli asal PO, tampilkan peringatan + opsi transfer/penyelarasan agar Nota Debit & pengurang AP jatuh di entitas yang benar.

## J. Impor vs Lokal (tambahan) — desain
- **Klasifikasi sumber** di **level Supplier**: `supplier.origin_type = local | import` (+ `country` opsional untuk import). Bisa **override di level PO** (`po.import_flag`) untuk kasus khusus.
- **Dampak ke Return Policy** (per supplier / per origin_type):
  - `local`: retur ke supplier relatif mudah; refund/AP-credit; window standar.
  - `import`: sering **tidak praktis diretur** ke supplier LN → policy: `returnable_to_supplier` (bool), window lebih panjang/berbeda, refund mode terbatas (mis. hanya AP-credit/none), keterkaitan **Landed Cost** (bea masuk/ongkos impor tak selalu bisa di-refund).
  - Default cerdas: bila `import` & `returnable_to_supplier=false` → alur retur beli **di-skip**, barang defect diarahkan ke **regrade + jual lokal** (bukan retur ke supplier).
- **Keterkaitan Landed Cost**: nilai persediaan barang impor = harga + landed cost (modul `LandedCostView` sudah ada). Saat retur/regrade impor, nilai yang dibalik/disesuaikan harus mengacu ke **landed cost**, bukan harga PO mentah.
- **Master Data**: tambah field origin_type/country di Supplier + tampil di form; return policy engine membaca origin_type.

## K. Rencana revisi (R0–R7) dengan keputusan terbaki

**R0 — Master Data: Origin (impor/lokal) + Return Policy Engine**
- Supplier: `origin_type (local|import)`, `country`, dan **Return Policy** extensible: `window_days`, `refund_modes[] (cash|ap_credit|none)`, `returnable_to_supplier`, `rma_required`, `restocking_fee_pct`, `condition_requirements`, `custom_fields{}`, `valid_from/until`.
- Sales return policy (global/kategori/customer) + **turunan deadline** dari tgl terima barang supplier + window (linked). Snapshot policy ke dokumen SO/retur (auditable). Eligibility check saat create.

**R1 — State machine + Outcome Retur Jual (feature-flag, tanpa ubah finance dulu)**
- Status: draft→pending_approval→approved(manager)→inspecting→inspected→[refund_settled|credit_settled|nego_settled|rejected]. Outcome & qty **per item/roll** (partial + sisa kirim-ulang).

**R2 — Unified Inspect (WAJIB untuk retur jual)**
- Reuse mesin 4-point/grade. Task inspect dibuat otomatis setelah manager approve. Output: grade, kondisi, rekomendasi outcome, layak-masuk-stok / layak-retur-supplier. Barang masuk → status roll **quarantine**.

**R3 — Inventory: gudang+entitas tujuan, ownership vs lokasi, regrade, quarantine**
- User pilih gudang & (opsional) entitas tujuan; owner vs lokasi jelas; regrade A→B; status roll quarantine/pending_supplier_return; cross-entity sesuai §I (tawarkan inter-entity transfer).

**R4 — Link → Retur Beli + sub-status supplier + dari receiving PO**
- `sales_return.linked_purchase_return_id` ↔ `purchase_return.origin_sales_return_id`; sub-status: requested_supplier→shipped_supplier→accepted_supplier(refund|ap_credit) | rejected_supplier→goods_back(+regrade). Retur beli dari **inspect receiving PO** (qty reject/salah kirim) → prefill. Hormati policy impor (§J).

**R5 — Finance lengkap**
- **Store-credit** (saldo customer) untuk potong-bon; refund tunai (jual & beli); CN diskon nego (tanpa stok); reversal DN/CN; jurnal regrade & landed-cost aware; idempotent.

**R6 — Approval 1-langkah Manager (rapikan) + audit + dokumen legal**
- Tetap 1 langkah manager (tanpa engine berjenjang); pastikan audit trail + bukti + policy tercantum di dokumen legal SO.

**R7 — UI/UX**
- Wizard retur jual & beli, layar Inspect, tampilan rantai (jual↔beli) & ownership/lokasi, store-credit ledger, filter impor/lokal; sekalian **tuntaskan paginasi returns (P2)**.

> Tiap R diuji via testing agent, jaga guardrail (kontrak API, ux_audit), GL idempotent. Mulai R0 setelah user beri "go".

---

## ✅ STATUS EKSEKUSI

### R0 — Return Policy Engine (Master Data) — **SELESAI** (verified end-to-end)

**Backend (baru):**
- `services/return_policy_service.py` — resolve supplier policy (+origin efektif + rekomendasi regrade lokal utk impor non-returnable), resolve sales policy (prioritas **customer > category > global**), `compute_deadline` (linked), eligibility check, snapshot policy.
- `routers/return_policies.py` — CRUD `sales_return_policies` (prefix `srp_`) + `GET /api/sales-return-policies/eligibility?order_id=&return_type=`.
- `routers/suppliers.py` — persist `origin_type`/`country`/`return_policy` (create+PATCH) + `GET /api/suppliers/{id}/return-policy`.
- `schemas_purchasing.py` — `ReturnPolicyInput` (window_days, refund_modes[], returnable_to_supplier, rma_required, restocking_fee_pct, condition_requirements, **custom_fields{} extensible**, valid_from/until) + Supplier `origin_type`/`country`/`return_policy` + PO `import_flag` (override asal per-PO).
- `schemas.py` — `SalesReturnPolicyCreate` (scope global/category/customer, allowed_return_types[], allowed_outcomes[], require_inspection, enforce_window, link_to_supplier_window, custom_fields{}).
- `services/return_service.py` — saat create retur jual → sematkan `policy_snapshot` + `return_deadline` + `policy_eligibility` (auditable, best-effort tak menggagalkan create).
- Registrasi koleksi: `entity_scope.py` (SHARED master), `verify_contract.py` CANONICAL, `validate_compliance.py` known set, `ENTITY_REGISTRY.md`.

**Frontend (baru/diubah):**
- `features/sales/ReturnPoliciesView.jsx` — halaman **Kebijakan Retur Jual** (CRUD, scope, jenis/outcome, inspeksi wajib, enforce window, linked). Tab baru "Kebijakan Retur" di hub Penjualan.
- `components/ReturnPolicyEditor.jsx` — editor kebijakan retur supplier (embedded di form Supplier) + **custom fields extensible**.
- `features/purchasing/SuppliersView.jsx` — field Asal Barang (Lokal/Impor) + Negara + ReturnPolicyEditor + badge **Impor** di list.
- `features/sales/CreateReturnForm.jsx` — **banner eligibility** (nama kebijakan, deadline+sisa hari, inspeksi wajib, peringatan luar-window/blokir) saat pilih order.

**Bukti uji:** POC backend 29/29 PASS · testing agent backend 16/16 PASS (0 bug) · guardrail hijau (Contract OK, Integrity 126/0/0, Compliance 0 FAIL) · verifikasi UI: halaman kebijakan, form buat kebijakan (scope dinamis), form supplier impor + policy editor, badge Impor, **banner eligibility** (SO-0004 Batik → policy kategori "Batik 45 Hari", deadline 2026-09-03, inspeksi wajib) — semua render benar.

**Demo seed:** `seed_r0_demo.py` — 1 supplier impor (Cirebon Craft) + 2 kebijakan retur jual (global 30 hari, kategori Batik 45 hari).

**Siap untuk R1** (state machine + 4 outcome): `allowed_outcomes` sudah tersedia di policy; snapshot & deadline sudah menempel di dokumen retur.

### R1 — State Machine + 4 Outcome + Partial — **SELESAI** (verified end-to-end)

**Backend (baru/diubah):**
- `services/return_state.py` — state machine: states (draft, pending_approval, approved, inspecting, inspected, refund_settled, credit_settled, nego_settled, rejected, cancelled), TRANSITIONS + guard `assert_transition`, `OUTCOME_TO_STATE`.
- `services/return_service.py` — dekomposisi `approve_and_adjust_stock` monolitik menjadi: `approve_return` (pending→approved, **tanpa** stok/CN), `start_inspection`/`complete_inspection` (approved→inspecting→inspected, inspeksi WAJIB), `settle_return` (inspected→terminal). `_create_credit_note_and_post_gl` digeneralisasi (items subset / post_stock / settlement_type). `_restock_returned_items` diekstrak. `reject_return` diperluas (boleh dari pending/approved/inspecting/inspected). `RETURN_ACTIVE_STATUSES` diperbarui (settled dihitung, rejected/cancelled tidak).
- `routers/sales_returns.py` — endpoint: `/approve`, `/inspect/start`, `/inspect/complete`, `/settle`, `/reject` (+guard 400 utk transisi invalid; auth per aksi).
- Efek finansial dipindah dari approve → **settle**: refund (CN+GL+stok, tunai/AR), store_credit (CN+GL+stok, settlement=store_credit + `store_credit_amount` utk ledger R5), nego (CN diskon **tanpa** gerak stok), reject (tanpa efek). Idempotent.

**Frontend (baru/diubah):**
- `ReturnShared.jsx` — STATUS_STYLE 10 state + `OUTCOME_LABEL`.
- `SalesReturns.jsx` — stats (Menunggu/Diproses/Selesai) + filter pill semua state + handler submit/approve/inspect/settle/reject.
- `ReturnDetail.jsx` — tombol aksi per-state + chip outcome/CN + wiring panel & modal.
- `ReturnInspectPanel.jsx` (baru) — inspeksi ringkas per item (grade/kondisi/rekomendasi/accepted_qty) → complete.
- `ReturnSettleModal.jsx` (baru) — pilih outcome (refund/store_credit/nego) + keputusan per item (sertakan/kecualikan + qty sebagian).

**Bukti uji:** POC `test_r1_poc.py` **28/28 PASS** (lifecycle, guard transisi, 4 outcome, partial, idempotent) · testing agent: backend 94% (16/17; 1 skip krn data uji, partial sudah lolos di POC), frontend **100%**, 0 bug kritis/UI/integrasi · guardrail hijau (Contract OK, Integrity **126/0/0**, Compliance 0 FAIL).

**Catatan lintas-fase:**
- Inspeksi R1 = grading ringkas; **R2** memperkaya dgn 4-point + quarantine roll.
- store_credit R1 mencatat `store_credit_amount` (CN pengurang piutang); **R5** buat ledger saldo customer + refund tunai + reversal + landed-cost aware (potensi drift subledger↔GL persediaan ditangani di R5).
- Stok kembali sbg 'available'; **R3** ubah ke quarantine + release + regrade + cross-entity.

### R2 — Unified Inspect (4-point) + Quarantine — **SELESAI** (verified end-to-end)

**Backend (baru/diubah):**
- `services/return_service.py` — `complete_inspection` R2: reuse engine 4-point (`qc_inspection_service.compute_points/grade_from_points/grade_thresholds`) → hitung poin per item dari `defects[{point_value,count}]`, turunkan grade (A/B/C) + `recommended_outcome` (`_recommend_outcome`: A→refund, B→store_credit, C→nego; damaged+C→reject). Simpan `inspection` per item + ringkasan dokumen (`worst_grade`, `total_points`, rekomendasi). `_restock_returned_items` → roll retur masuk **status `quarantine`** (bukan `available`), `qc_status=pending_release`, grade dari inspeksi, `unit_cost=WAC` (0 bila damaged, anti INV-GL-DRIFT), movement `return_quarantine_in`, rebuild_balance. `get_return_quarantine_rolls` + `release_quarantine` (action per roll: `release`→available, `scrap`→damaged; movement `quarantine_release`/`quarantine_scrap`; rebuild). Nego → tanpa roll (tanpa gerak stok).
- `routers/sales_returns.py` — endpoint baru: `GET /sales-returns/{id}/quarantine`, `POST /sales-returns/{id}/quarantine/release`. Inspect complete pakai `ReturnInspectComplete` (defects 4-point).
- `schemas.py` — `ReturnInspectComplete` (inspections: defects[{point_value,count}], condition, accepted_qty), `QuarantineReleaseInput` (decisions[{roll_id, action}]).

**Frontend (baru/diubah):**
- `ReturnInspectPanel.jsx` — form inspeksi **4-point** (input jumlah defect per bobot P1–P4) → preview poin/grade/rekomendasi real-time (backend tetap otoritatif); kirim `inspections` ke `/inspect/complete`.
- `ReturnQuarantinePanel.jsx` (baru) — daftar roll karantina hasil retur + checkbox scrap per-roll + tombol "Release ke Stok" (`/quarantine/release`).
- `ReturnDetail.jsx` — wiring `ReturnQuarantinePanel` (muncul di retur settled refund/store_credit) + `refetchReturn` setelah release.

**Bukti uji:** POC `test_r2_poc.py` **17/17 PASS** (grade C/B/A dari poin, rekomendasi, quarantine entry, release→available, scrap→damaged, store_credit→quarantine, nego tanpa roll) · regresi `test_r1_poc.py` **28/28 PASS** · guardrail: Contract OK, **Integrity 126/0/0 di jalur normal** (refund/store_credit/nego rekonsiliasi), Compliance 0 FAIL · testing agent iterasi 147: **backend 100%, frontend 100% (29/29), 0 bug** · screenshot: daftar retur (filter lifecycle/outcome), form inspeksi 4-point (24 poin→Grade B→rekomendasi Store Credit), panel karantina (roll RTN, Release/Scrap).

**Catatan lintas-fase (DEFERRED ke R5):**
- Aksi **scrap** (quarantine→damaged) mengurangi subledger persediaan **tanpa jurnal write-off GL** → menyisakan **1 WARN integritas** (mis. `ent_ksc` drift). Ini SENGAJA ditunda ke R5 (butuh jurnal write-off idempotent), BUKAN bug. Jalur normal (refund/store_credit/nego) tetap 126/0/0.
- Cross-entity ownership vs lokasi + regrade + pilih gudang/entitas tujuan → **R3**.

### R3 — SELESAI (verified 2026-07-24)
**Backend:** settle terima `return_warehouse_id` (LOKASI; owner tetap = entitas SO agar subledger persediaan rekonsiliasi di satu entitas); restock ke **quarantine** di lokasi terpilih (`_restock_returned_items` pakai warehouse+owner); `release_quarantine` dengan **regrade** grade final A/B/C (+`regraded_from` & movement note); endpoint baru `POST /api/sales-returns/{id}/rolls/{roll_id}/transfer-ownership` (reuse `roll_service.execute_ownership_transfer` + `gl_service.post_intercompany_transfer` — Dr IC-AR/Cr Persediaan @src; Dr Persediaan/Cr IC-AP @dst, idempotent, `pair_id`; guard: hanya roll `available`, entitas tujuan ≠ pemilik → 400); enrichment quarantine (owner_entity_name, warehouse_name, product_name, sku).

**Fix integritas (akar masalah stopping point):** `routers/dashboard.py` — KPI `available_qty`/`reserved_qty` tadinya via `product_summary()` TANPA scope (lintas-entitas) → setelah R3 transfer kepemilikan lintas-PT, roll `ent_kanda` terhitung di KPI tapi tidak di `GET /inventory/balances` (scoped) → drift 1m. Kini KPI diagregasi dari `inventory_balances` yang di-scope sama (`resolve_list_scope owner_entity_id`) → **INV-2/INV-3 hijau**.

**Frontend:** `ReturnSettleModal` picker "Lokasi Gudang Penerimaan" (refund/store_credit); `ReturnQuarantinePanel` kolom **Owner (pemilik)** vs **Lokasi (gudang)** terpisah + select grade final + tombol Release + aksi **Transfer Kepemilikan** (modal pilih PT tujuan, GL-safe).

**Bukti uji:** `test_r3_poc.py` **21/21 PASS** · regresi `test_r1_poc` 28/28, `test_r2_poc` 17/17 · guardrail clean-seed: Contract OK, **Integrity 126/0/0** · `testing_agent_v3` iter_148: **backend 30/30 PASS**, frontend code review 100%, 0 bug; modal transfer-ownership diverifikasi visual (KSC→Kanda, lokasi tetap).

### R4 — SELESAI (verified 2026-07-24)
**Link Retur Jual↔Beli + Supplier RMA lifecycle + goods_back/regrade + kebijakan IMPOR (§J).**

**Backend:**
- `create_from_sales_return` (`POST /api/sales-returns/{id}/create-purchase-return`): teruskan barang cacat retur jual (roll karantina/available) → buat **Retur Beli tertaut 2-arah** (`sales_return.linked_purchase_return_id` ↔ `purchase_return.origin_sales_return_id`). Resolve supplier best-effort dari PO terakhir produk.
- `purchase_return_state.py` — mesin `supplier_status`: `requested_supplier → shipped_supplier → accepted_supplier(refund|ap_credit) | rejected_supplier → goods_back`.
- `approve` mode-aware: **DIRECT** (`supplier_flow=false`) → konsumsi stok + Nota Debit + GL langsung (unchanged, regresi hijau); **RMA** → approve = gate internal saja.
- `ship_to_supplier` → shipped (roll TETAP di subledger; `available`→`quarantine` earmark). `supplier_accept` → finalisasi (konsumsi roll→`returned_supplier` + Nota Debit + AP + GL). `supplier_reject` → rejected. `goods_back` → roll `quarantine`→`available` (+regrade A→B), **tanpa GL**.
- **Anti INV-GL-DRIFT:** roll tetap dinilai persediaan sepanjang RMA; GL hanya bergerak saat accept. Integrity **126/0/0** setelah POC.
- Kebijakan **IMPOR (§J)**: `create_purchase_return` menolak (400) supplier impor & `returnable_to_supplier=false` (rekomendasi regrade + jual lokal); `bypass_import_policy` override (audit-only).

**Frontend:**
- `PurchaseReturns` list: badge `supplier_status` (RMA: Diajukan/Dikirim/Diterima/Ditolak/Barang Kembali) + chip origin `↩ SRET`.
- `ReturnDetailPanel`: `supplier-status-pill`, meta Asal Retur Jual, blok **ALUR RMA** (ship / accept + outcome radio ap_credit|refund / reject / goods-back + regrade select) + timeline lengkap.
- `ReturnQuarantinePanel` (retur jual): tombol **Teruskan ke Supplier** → modal pilih supplier → `create-purchase-return`; chip **linked purchase return**.

**Bukti uji:** `test_r4_poc.py` **35/35 PASS** · regresi R1 28/R2 17/R3 21 · Integrity 126/0/0 (POC) · Contract OK · `testing_agent_v3` iter_149: **backend 73/73 PASS, frontend 100%, 0 bug** · UI diverifikasi visual (PRET-00009 shipped → panel ALUR RMA; list badge+chip).

### R5 — SEDANG DIKERJAKAN (bertahap: R5.1→R5.5)

#### R5.1 — Write-off GL (scrap & goods) — ✅ SELESAI (verified 2026-07-24)
**Menghilangkan WARN INV-GL-DRIFT yang ditunda sejak R2/R3/R4.**

**Backend:**
- COA baru (idempotent, auto-seed): `5-9500 Beban Kerugian/Penghapusan Persediaan` (expense), `2-1450 Saldo Kredit Pelanggan (Store Credit)` (liability, disiapkan utk R5.2).
- `gl_service.post_inventory_writeoff(roll_id, entity_id, amount, reason, ...)` — JE **Dr 5-9500 / Cr 1-1300** sebesar `length_remaining * unit_cost`. Idempotent (`source_type="inventory_writeoff"`, `source_id=roll_id`).
- `return_service.release_quarantine`: saat aksi **scrap** (roll `quarantine`→`damaged`, keluar subledger fisik), otomatis posting write-off + tag roll (`writeoff_je_number`, `writeoff_amount`, `writeoff_at`) + `_release_summary.writeoff_total`/`writeoff_jes`.
- Efek: GL 1-1300 turun tepat sebesar nilai roll di-scrap → subledger↔GL tetap rekonsiliasi.

**Frontend:**
- `ReturnQuarantinePanel`: badge merah **"Write-off {JE}"** + nominal Rp pada roll scrapped (`writeoff-badge-<rollId>`, `writeoff-amt-<rollId>`); pesan release menyebut total write-off GL.

**Bukti uji:** `test_r5_writeoff_poc.py` **16/16 PASS** · regresi R1 28/R2 17/R3 21/R4 35 hijau · **Integrity 126/0/0 SETELAH scrap** (INV-GL-DRIFT resolved, GL-3 PASS) · Contract OK · `testing_agent_v3` iter_150: **backend 39/39 PASS, 0 bug**, frontend code-review OK · UI diverifikasi visual (SRET-00025 → roll RTN-00025-mega Scrap/Rusak + badge "Write-off KSC/JE-00081" Rp244.200).

#### R5.2 — Store-credit ledger — ✅ SELESAI (verified 2026-07-24)
**Saldo Kredit Pelanggan sebagai kewajiban (GL 2-1450), dipakai di POS + Sales Order + Invoice.**

**Backend:**
- COA `2-1450 Saldo Kredit Pelanggan (Store Credit)` (liability, auto-seed).
- `services/store_credit_service.py` — SSOT koleksi `store_credit_ledger` (entri bertanda: issue +, redeem −, adjust ±); fungsi `balance / balances_by_entity / ledger / summary / issue / redeem / adjust / backfill_from_credit_notes`.
- GL: `post_sales_return` kini terima `settlement` → store_credit **Cr 2-1450** (bukan Piutang); `post_store_credit_redemption` (Dr 2-1450 / Cr 1-1200); `post_store_credit_adjust` (2-1450 vs 5-9500/4-9000). Semua idempotent.
- Issue di-hook di `settle_return` (outcome store_credit). Redeem meng-`_apply_to_order` (AR outstanding turun selaras GL). Router `routers/store_credit.py`: GET /store-credit, /balance, /ledger, /open-orders; POST /redeem, /adjust (auth resource ar_receipt).
- Seed `clear_collections` diperluas: wipe sales_returns/credit_notes/store_credit_ledger/store_credit_redemptions (fresh seed, hindari orphan tanpa JE).

**Frontend:**
- Halaman **Store Credit (Saldo)** (Keuangan) — KPI total kewajiban + daftar saldo pelanggan + drill-down ledger + modal **Pakai Saldo** (pilih order AR, jumlah, Maks) + modal **Sesuaikan** (admin/manager).
- `StoreCreditBadge` chip saldo di POS checkout & AR/Piutang detail.

**Bukti uji:** `test_r5_store_credit_poc.py` **21/21 PASS** · Integrity 126/0/0 (termasuk rekonsiliasi 2-1450 == Σ ledger) · Contract OK · `testing_agent_v3` iter_151: **backend 12/12, frontend 100%, 0 bug** · UI diverifikasi visual (2 pelanggan bersaldo, ledger CN-00016, modal redeem SO-0003).

#### R5.3 — Cash refund + pemisahan GL — ✅ SELESAI (verified 2026-07-24)
**Refund tunai (retur jual & retur beli) + pemisahan GL refund-kas vs ap_credit + cash ledger.**

**Backend:**
- `gl_service.post_sales_return(cash_account_code=…)` → refund tunai kredit ke akun Kas/Bank terpilih (default 1-1100).
- `gl_service.post_purchase_return(outcome, cash_account_code)` outcome-aware: **refund** → Dr Kas/Bank / Cr Persediaan (supplier bayar tunai, AP tak berubah); **ap_credit** → Dr Hutang/GR-IR / Cr Persediaan (potong AP).
- `services/cash_ledger.record_return_cash(...)` — catat `cash_transaction` (out utk retur jual, in utk retur beli refund) TANPA double-GL (gl_posted=True, link ke JE CN/Nota-Debit). Idempotent per (ref_type, ref_id, direction).
- `settle_return(refund_account_code=…)` buat cash_transaction keluar saat settlement=cash. `supplier_accept(refund_account_code=…)` untuk retur beli. Endpoint `GET /api/gl/cash-accounts`.

**Frontend:**
- Modal Settle retur jual: pemilih **Akun Kas/Bank Refund Tunai** (muncul saat outcome=refund) + info.
- Panel RMA retur beli: pemilih akun Kas/Bank saat radio outcome=**Refund (kas)**; notice menampilkan `cash_txn_number`.

**Bukti uji:** `test_r5_cash_refund_poc.py` **22/22 PASS** · Integrity 126/0/0 · Contract OK · `testing_agent_v3` iter_152: **backend 100% (22/22 POC + 5/5 API), frontend 100%, 0 bug**.

#### R5.4–R5.5 — belum dikerjakan (reversals/koreksi → landed-cost awareness).
