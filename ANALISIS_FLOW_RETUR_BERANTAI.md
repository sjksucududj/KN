# ANALISIS SKENARIO: JUAL → BELI INTERNAL ANTAR-PT → RETUR BERANTAI

> 2026-08-10 · sesi verifikasi (tanpa eksekusi) · metode: pelacakan kode jalur demi jalur
> (`routers/sales_orders*.py`, `services/interco_service.py`, `services/interco_return_service.py`,
> `services/return_service.py`, `services/roll_service.py`, `services/purchase_return_service.py`,
> `routers/product_traceability.py`, `services/backorder_service.py`) + bukti dari data demo.

**Skenario pemilik:** Customer A beli lewat Sales A di **Entitas A** → barang tidak ada →
Entitas A **beli internal dari Entitas B** → barang sampai ke Customer A → Customer A retur →
Sales A buat permintaan retur → barang kembali ke Entitas A → **Entitas A retur ke Entitas B** →
Entitas B **retur ke supplier ATAU simpan barang** → kepemilikan barang kembali ke Entitas B.
Jadi ada **2–3 retur berantai**.

**Kesimpulan singkat: rantai ini SUDAH didukung ±80%.** Semua dokumen, jurnal, pajak, dan
perpindahan kepemilikan sudah ada dan dijaga invarian. Yang perlu dibenahi: **1 sambungan
terputus**, **1 percabangan berbahaya (dua jalan untuk satu peristiwa)**, **1 jejak asal
barang yang hilang**, **1 pemilihan roll yang bisa salah**, dan **tidak ada tautan antar
ketiga retur**.

---

## LANGKAH 1 — Customer A beli lewat Sales A di Entitas A ✅
- Sales A membuat SO di Entitas A → roll **direservasi otomatis** (reservasi di level roll).
- Stok kurang → SO menjadi **`waiting_stock`** + baris `backorders[]` (bukan koleksi baru).
- `POST /sales-orders/preview-allocation` sudah **memberi tahu sumber pemenuhan** per baris:
  `from_stock` · `from_incoming` · **`inter_company`** · `backorder`, plus `cross_entity[]`
  (stok yang ada di PT lain) dan kalimat penjelas.

⚠️ **Catatan (temuan L21, sudah masuk FASE E-0):** endpoint pratinjau itu **mengabaikan
konteks entitas** → sales di CV Kanda bisa dijanjikan stok milik KSC. Wajib dibenahi lebih
dulu, karena inilah pintu masuk keputusan "beli internal atau tidak".

## LANGKAH 2 — Entitas A beli internal dari Entitas B ✅ (prosesnya lengkap)

Proses yang sudah berjalan di sistem (FASE G-6):

1. **Prasyarat harga**: wajib ada **kontrak harga internal** — `supplier_contracts` dengan
   `partner_kind="entity"`, pemilik dokumen = **entitas penjual (B)**, `partner_id` =
   **entitas pembeli (A)**, per produk. Tanpa kontrak → **transaksi DITOLAK** dengan kalimat
   menuntun (sistem sengaja **tidak menebak** harga). Mode harga: `fixed_price` (bawaan) ·
   `at_cost` · `cost_plus_pct`.
2. `POST /api/interco/transactions` (seller=B, buyer=A) → lahir **DUA dokumen kembar**
   `B/IC-000xx` (peran *seller*) ↔ `A/IC-000xx` (peran *buyer*), saling menunjuk `pair_id`.
   Status awal `draft`. Nomor per entitas.
3. **Konfirmasi** → jurnal di **dua buku** sekaligus:
   - Penjual B: `Dr 1-1250 IC-AR / Cr 4-1000 Pendapatan (+ 2-1200 PPN keluaran)`
   - Pembeli A: `Dr 1-1310 Persediaan Dalam Perjalanan (+ 1-1500 PPN masukan) / Cr 2-1250 IC-AP`
4. **Faktur pajak internal** (bila ber-PPN): keluaran B ↔ masukan A **berpasangan**
   (`source_type="interco"`, `is_internal=true`), dijaga INV-IC-07. Mode PPN per entitas:
   `ikut_pkp` · `tanpa_ppn` · `dengan_ppn`.
5. **Barang fisik**: `POST /{id}/warehouse-task` → `warehouse_transfers` ber-`transfer_kind
   ="inter_entity"` + `interco_pair_id`. Gudang menandai kirim → terima.
6. **Saat tugas gudang selesai**: roll **pindah pemilik B→A**; **lot di-rehome** ke lot milik A
   dengan **genealogi** menunjuk lot asal (INV-LOT-05: satu lot tak boleh lintas pemilik);
   roll **dinilai ulang** ke harga beli internal. Jurnal barang: B `Dr 5-1000 HPP / Cr 1-1300`,
   A `Dr 1-1300 / Cr 1-1310`. Jurnal at-cost lama **dilewati** supaya tidak dobel (INV-IC-06).
7. **"Tandai Diterima" DITOLAK** bila tugas gudang belum selesai (persediaan pembeli tidak
   boleh naik untuk barang yang tidak ada di gudang mana pun).
8. **Saldo pasangan PT** (`interco_accounts`): IC-AR di B == IC-AP di A (INV-IC-02);
   pelunasan kapan saja lewat **netting / transfer / kas** (`interco_settlements`).
9. **Konsolidasi grup**: margin B→A **dieliminasi otomatis** selama barang belum terjual ke
   luar grup (INV-IC-03), ikut diperbarui saat settlement, dihapus saat pembatalan.
10. **Pembatalan** sesudah dikonfirmasi wajib ber-alasan → jurnal pembalik penuh di dua buku.
    Bila barang **sudah** berpindah, pembatalan ditolak → harus lewat **retur antar-PT**.

### ❌ PUTUS #1 — barang masuk dari PT lain TIDAK memicu pemenuhan SO
`auto_fulfill_backorders()` hanya dipanggil dari:
- `routers/inbound_receiving.py:585` (penerimaan barang dari **PO supplier**), dan
- `services/qc_service.py:263` (setelah pelepasan QC).

**Tidak ada** pemanggilan dari `roll_service.execute_ownership_transfer` (penerimaan
antar-PT). Akibatnya: setelah barang dari Entitas B masuk, SO Customer A **tetap
`waiting_stock`** dan harus dialokasikan **manual**. Padahal justru pembelian internal itu
dilakukan **untuk** SO tersebut.

### ❌ PUTUS #2 — transaksi antar-PT tidak tertaut ke SO pemicunya
`interco_transactions` **tidak punya** `source_order_id`/`demand_ref` (sudah dicek: nol
rujukan ke `sales_order` di `interco_service.py`). Padahal jalur reorder ke supplier **sudah
punya** pola ini (`PR.source="so_repeat"`, `source_ref_id=<so_id>`). Jadi tidak ada jejak
"IC ini dibeli untuk SO-0009", dan Papan Pending SO tidak bisa menunjukkan janji dari PT lain.

## LANGKAH 3 — Barang sampai ke Customer A ✅
Konfirmasi SO → tugas gudang outbound otomatis → picking/scan → dispatch (Surat Jalan) →
`shipped` → tandai diterima → `done`. Invoice + faktur pajak + kwitansi mengikuti.

## LANGKAH 4 — Customer A retur ke Entitas A ✅ (paling lengkap)
- **Sales A** membuat permintaan retur (`POST /api/sales-returns`, status `draft`) →
  `pending_approval` → **manajer menyetujui** → `inspecting` → `inspected` → settle.
- **Kebijakan retur** ditegakkan dari `sales_return_policies` (global / kategori / pelanggan):
  jendela hari, jenis retur & outcome yang diizinkan, biaya restocking, wajib inspeksi.
- **Inspeksi per roll**: grade, kondisi, daftar cacat.
- **4 outcome** (boleh **per item/roll**, partial): `refund` · `store_credit` · `nego` ·
  `reject`; nota kredit + jurnal balik pendapatan/HPP/PPN; `reverse_settlement` tersedia.
- **Barang masuk KARANTINA**, bukan langsung tersedia: dibuat **roll BARU** `RTN-xxxxx`
  dengan **lot tersendiri** `RTN-<nomor retur>` (status `karantina`), nilai = **WAC**
  (0 bila `damaged`, konsisten dengan pembalikan HPP). Harus `release_quarantine` dulu untuk
  jadi `available`, atau di-scrap/write-off.

## LANGKAH 5 — Entitas A retur ke Entitas B ⚠️ **ADA DUA JALAN, TANPA RAMBU**

| | **Jalan 1 — `POST /api/interco/returns` (G-6b)** | **Jalan 2 — `transfer_return_roll_ownership` (R3 §I)** |
|---|---|---|
| Dokumen | **Kembar**: nota retur A (`A/ICR-000xx`, role *returner*) ↔ nota kredit B (`B/ICR-000xx`, role *receiver*) | Hanya `warehouse_transfers` kode `RTNX-<retur>-<roll>` |
| Nilai | **Harga internal asli** (membalik pendapatan/HPP/PPN) | **At-cost** (harga pokok) |
| PPN | Faktur pajak ditandai **perlu pengganti** | **Tidak disentuh** |
| `interco_transactions` asal | `returned_qty/returned_amount` **diperbarui** (append-only) | **TIDAK diperbarui** → `qty_returnable` tetap penuh (bisa retur dobel) |
| IC-AR / IC-AP | Berkurang sesuai nilai retur | Bergerak **di harga pokok** → saldo pasangan **tidak akan nol** |
| Eliminasi margin konsolidasi | **Diperbarui** (INV-IC-03) | **Tidak diperbarui** → laba grup tetap kembung |
| Kontrol | Alasan wajib ≥5 huruf + **dual-control** (pembuat ≠ penyetuju) | Tanpa alasan wajib, tanpa dual-control |
| Barang | Tugas gudang arah balik | Kepemilikan pindah, **lokasi fisik tetap** |

**Masalahnya:** Jalan 2 justru yang paling "dekat" bagi orang yang sedang membuka dokumen
retur pelanggan, sementara Jalan 1 ada di menu Antar Entitas. **Tidak ada satu pun rambu**
yang mengatakan "barang ini asalnya dari pembelian internal `A/IC-00005` — pakai Retur
Antar-PT, jangan pindah kepemilikan at-cost". Ini persis pola kesalahan yang sudah pernah
terjadi di area lain (dan sudah dijaga di sana lewat pesan menuntun).

### ⚠️ RISIKO #3 — roll yang dikembalikan bisa SALAH ROLL
`interco_return_service` membuat tugas gudang lewat
`reserve_rolls_for_transfer(product_id, buyer_entity, qty, ...)` yang memilih roll
**FEFO per produk** dari stok Entitas A — **bukan** roll hasil retur pelanggan
(`origin_type="return"`, lot `RTN-...`, sering ber-grade B/cacat).
Akibat nyata: **roll bagus terkirim balik ke B, roll cacat tetap tinggal di A.**

### ⚠️ RISIKO #4 — `returnable` tidak memeriksa barang sudah benar-benar kembali
`interco_return_service.returnable()` menghitung `qty_total − qty_returned` dari transaksi
asal saja. Tidak ada pemeriksaan bahwa barangnya sudah kembali dari pelanggan. Pagar
fisiknya baru muncul di tahap tugas gudang (roll harus `available` & milik A) — jadi
layar bisa menawarkan retur yang kemudian **gagal di langkah berikutnya**.

## LANGKAH 6 — Entitas B: simpan barang ✅ / retur ke supplier ❌ (jejak asal hilang)

- **Simpan barang**: ✅ roll menjadi milik B (available/karantina), balance & lot di-rebuild.
- **Retur ke supplier**: `POST /api/purchase-returns` **mewajibkan supplier**
  (`"Supplier wajib dipilih"`), dan kandidat roll disaring oleh
  `build_returnable_rolls(product_id, supplier_id, po_id, …)` dengan filter
  `q["supplier_id"]` dan `{"po_id": po_id}` / `{"acquired.ref_id": po_id}`.

### ❌ PUTUS #5 — roll hasil retur pelanggan TIDAK punya jejak supplier/PO
Roll yang dibuat `_restock_returned_items()` berisi:
`origin_type="return"`, `origin_ref=<return_id>`, `acquired={"via":"return","ref_id":<return_id>}`
— **tanpa `supplier_id`, tanpa `po_id`, tanpa `po_number`, tanpa `supplier_invoice_no`**.
Dan setelah pindah kepemilikan, `execute_ownership_transfer` **menimpa** `acquired` menjadi
`{"via":"transfer","ref_id":<transfer_id>}`.

⇒ Saat Entitas B ingin meretur barang itu ke supplier aslinya, roll tersebut **tidak muncul**
sebagai kandidat bila disaring per supplier/PO. Jejak "kain ini dulu dibeli dari Toba Craft
lewat `PO-00005`" **hilang** setelah melewati retur pelanggan + perpindahan kepemilikan.
(Genealogi **lot** memang tersimpan, tetapi jalur retur beli membaca **field roll**, bukan
silsilah lot.)

Yang **sudah benar** di jalur retur beli: kebijakan supplier & asal barang ditegakkan —
barang **impor** dari supplier ber-`returnable_to_supplier=false` **ditolak** dengan saran
"REGRADE + jual lokal"; ada siklus `submit → approve → ship-to-supplier → supplier-accept/reject`.

## LANGKAH 7 — Kepemilikan kembali ke Entitas B ✅
Terjadi lewat salah satu dari dua jalan di Langkah 5 (dengan konsekuensi berbeda seperti tabel).

## ❌ PUTUS #6 — ketiga retur tidak saling tertaut
Tidak ada relasi dokumen antara **retur pelanggan** → **retur antar-PT** → **retur beli**.
Mesin relasi dua arah (FASE G-4 `doc_refs_service`, sudah dipakai 79 tautan di data demo)
**belum** dipasang untuk rantai ini. Akibatnya tidak ada satu layar yang bisa menjawab
"kain retur dari Customer A ini akhirnya ke mana?".

---

# RINGKASAN: 6 PERBAIKAN AGAR SKENARIO INI UTUH

| # | Perbaikan | Letak |
|---|---|---|
| R1 | **Penerimaan barang antar-PT memicu `auto_fulfill_backorders`** (dan pemberitahuan ke Admin Sales) | `services/roll_service.execute_ownership_transfer` / `interco_service.receive` |
| R2 | **Tautan SO ↔ transaksi antar-PT** (`source_order_id`, meniru `PR.source_ref_id`) + tampil di Papan Pending SO | `schemas.IntercoCreate`, `interco_service`, `stock_bucket_service.pending_so_board` |
| R3 | **Rambu satu jalan untuk retur antar-PT**: bila roll/produk berasal dari pembelian internal, layar retur pelanggan **mengarahkan** ke Retur Antar-PT dan **memblokir** pindah-kepemilikan at-cost (atau at-cost hanya untuk kasus non-interco) | `return_service.transfer_return_roll_ownership` + FE `ReturnDetail`/`ReturnQuarantinePanel` |
| R4 | **Retur antar-PT memilih roll SPESIFIK** (utamakan roll hasil retur pelanggan / lot `RTN-*`, grade sesuai) alih-alih FEFO per produk | `interco_return_service` + `reserve_rolls_for_transfer` (tambah parameter `roll_ids`) |
| R5 | **Warisi jejak asal barang** pada roll retur: `supplier_id`, `po_id`, `po_number`, `supplier_invoice_no` dari roll asal; dan `execute_ownership_transfer` **jangan menghapus** jejak itu (simpan `acquired_history[]`) | `return_service._restock_returned_items`, `roll_service.execute_ownership_transfer`, `build_returnable_rolls` |
| R6 | **Rantai retur tertaut** lewat `doc_refs_service` (retur pelanggan ↔ retur antar-PT ↔ retur beli) + satu layar "jejak retur" | `services/doc_refs_service.py` (mesin sudah ada) |

**Prasyarat**: L21 (pratinjau alokasi mengabaikan entitas) **wajib** dibereskan lebih dulu —
tanpa itu keputusan "beli internal atau tidak" berangkat dari angka stok PT yang salah.
