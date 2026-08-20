# ANALISIS DOMAIN: SALES vs ADMIN SALES (+ alur SO lengkap)

> 2026-08-10 · sesi verifikasi (belum ada eksekusi) · bukti: pembacaan
> `permissions_config.py`, `routers/sales_orders*.py`, `routers/so_approvals.py`,
> `config/navStructure.js`, `config/hubTabs.js` + **uji izin nyata** dengan 4 akun demo.
> Audit terdahulu yang relevan: `ROLE_UX_GAP_AUDIT.md` (sudah ditindaklanjuti sebagian:
> Sales Home/Manager Home/Admin Home ada; akses back-office sales sudah dicabut).

---

## 1. FAKTA: SISTEM HANYA PUNYA 4 PERAN

`DEFAULT_PERMISSIONS` = **admin · sales · manager · warehouse**. **Tidak ada "admin sales".**
Hirarki kuasa: `config_service.role_satisfies` → `{sales:1, warehouse:1, manager:2, admin:3}`.

### Akibatnya (inti masalah pemilik)
Orang yang di lapangan disebut **admin sales** hari ini hanya punya 2 pilihan, keduanya salah:

| Dijadikan… | Yang HILANG | Yang KEBABLASAN |
|---|---|---|
| `sales` | **tidak bisa Konfirmasi SO** (403) · tidak bisa Setujui SO · tidak lihat antrean persetujuan · tidak lihat progres gudang · tidak lihat piutang (AR aging) · tidak bisa apa pun di Antar Entitas | — |
| `manager` | — | **setujui & bayar tagihan supplier** · setujui PO · **tutup buku & buka periode** · **payroll & data HR** (`hr.manage_payroll`, `view_pii`) · hapus master (produk/pelanggan/supplier/makloon) · setujui transfer gudang · produksi · **settlement antar-PT** · anggaran · aset tetap |

Jadi keluhan "belum jelas pembagiannya" itu **bukan salah paham** — memang belum ada perannya.

---

## 2. ALUR SO LENGKAP (fakta, status nyata di kode)

Status SO yang benar-benar dipakai:
`draft → reserved / waiting_stock → waiting_approval → approved → confirmed →
partially_picked → picked → partially_shipped → shipped → done` (+ `cancelled`, `expired`)

| # | Langkah | Endpoint | Izin yang dibutuhkan | Sales? | Manager/Admin? | Gudang? |
|---|---|---|---|---|---|---|
| 1 | Buat SO (reservasi roll otomatis) | `POST /sales-orders` | `order.create` | ✅ | ✅ | ❌ |
| 2 | Ajukan persetujuan | `POST /{id}/submit-for-approval` | `order.update` | ✅ | ✅ | ❌ 403 |
| 3 | **Setujui SO** | `POST /{id}/approve` | `order.approve` | ❌ **403** | ✅ | ❌ |
| 4 | **Konfirmasi SO** → tugas gudang otomatis | `POST /{id}/confirm` | `order.confirm` | ❌ **403** | ✅ | ❌ |
| 5 | Pick / scan / dispatch | `/api/outbound/*`, `/api/wms/*` | `wms.*` | ❌ **403** | ✅ | ✅ |
| 6 | Tandai barang diterima pelanggan | `POST /{id}/mark-delivered` | `order.update` | ✅ (!) | ✅ | ❌ |
| 7 | Cetak Surat Jalan / Invoice | `/api/documents/*`, `/api/pdf/*` | `document.print` | ✅ | ✅ | ✅ |
| 8 | **Terbitkan Faktur Pajak keluaran** | `POST /tax-invoices` | `tax_invoice.create` | ✅ **(!)** | ✅ | ❌ |
| 9 | **Catat penerimaan uang (kwitansi AR)** | `POST /ar-receipts` | `ar_receipt.create` | ✅ **(!)** | ✅ | ❌ |
| 10 | Rencana bayar & denda | `/api/payment-plans`, `/api/penalties` | `payment_plan.*`, `penalty.view` | ✅ buat/ubah | ✅ + terbitkan/bebaskan | ❌ |
| 11 | **Putuskan selisih pembayaran** | `POST /payment-variances/...` | `payment_variance.decide` | ✅ **(!)** | ✅ | ❌ |
| 12 | Retur pelanggan | `/api/sales-returns` | `sales_return.create` / `.approve` | ✅ ajukan · ❌ setujui | ✅ keduanya | ❌ |
| 13 | Laporan piutang (AR aging) | `GET /ar/aging` | `require_role(manager)` | ❌ **403** | ✅ | ❌ |
| 14 | Antrean persetujuan | `/approvals/queue`, `/approval-requests` | `order.approve` | ❌ **403** | ✅ | ❌ |
| 15 | **Pembelian antar-entitas** | `/api/interco/*` | `interco.*` | ❌ **403** | ✅ | ✅ view/ship/receive |

Tiga jenis persetujuan yang lahir di langkah 2 (`services/so_approvals.py`):
**`nilai`** (validasi/ambang rupiah) · **`kredit`** (limit pelanggan) · **`special_price`**
(harga di bawah batas). SO tidak bisa naik ke `approved` sampai **semua** diputuskan, dan
`approve` diblokir (409 `APPROVAL_PENDING`) bila kredit/harga khusus masih menggantung.
Ambang & peran penyetuju **sudah configurable** di Pusat Pengaturan.

---

## 3. TEMUAN CELAH DOMAIN (semua berbukti)

| Kode | Temuan | Bukti |
|---|---|---|
| **SD1** | **Tidak ada peran "admin sales"** → dilema kuasa di tabel §1 | `permissions_config.py` |
| **SD2** | **Pemisahan tugas (SoD) bocor**: peran `sales` boleh **menerbitkan Faktur Pajak keluaran**, **mencatat penerimaan uang (kwitansi AR)**, **memutus selisih pembayaran**, dan membuat rencana bayar. Orang yang menjual juga yang menyatakan "sudah dibayar" | uji izin: `/api/tax-invoices` 200 · `/api/ar-receipts` 200 · `payment_variance.decide` ada di matriks sales. Sudah pernah diangkat sebagai **G5** di `ROLE_UX_GAP_AUDIT.md` dan **belum diputuskan** |
| **SD3** | **Sales tidak bisa melihat progres gudang** padahal menu "Operasi WMS" **terlihat** untuk sales → **layar mati**: `/api/wms/tasks` **403** | uji izin + `hubTabs.js: wms-operations roles ["admin","warehouse","manager","sales"]` |
| **SD4** | Menu **"Kunjungan Sales"** terlihat untuk sales tetapi `/api/hr/visits` butuh `hr.view` → **403**, layar mati | uji izin + `hubTabs.js: customers-crm` |
| **SD5** | **Sales melihat pesanan sales lain**: `sales2@` (Bima) melihat **8 SO** yang semuanya `sales_name = "Ayu Permatasari"` — dan tidak satu pun miliknya. Padahal **pelanggan sudah difilter** per `sales_pic` (Ayu 1, Bima 2) → tidak konsisten | uji nyata |
| **SD6** | `/api/sales-targets` & `/api/sales-incentives` **tidak ter-scope entitas**: admin di konteks **Kanda** tetap melihat 3 baris ber-`entity_id=ent_ksc`, termasuk baris **Citra Lestari** (sales Kanda) yang **ter-stempel ent_ksc**. Untuk role sales hasilnya sudah difilter ke miliknya sendiri | uji nyata (koreksi atas L5/L6 di `plan.md`: ini **salah stempel entitas + tanpa scope**, bukan kebocoran antar-orang) |
| **SD7** | `/api/sales-users` mengembalikan **semua sales lintas entitas** tanpa `entity_id` (3 orang termasuk sales Kanda) | uji nyata |
| **SD8** | `/api/reports/top-customers` **tidak difilter per sales** — sales melihat peringkat omzet pelanggan sales lain (per entitas sudah benar) | uji nyata |
| **SD9** | **`mark-delivered` bisa dilakukan sales** (`order.update`) — pengakuan barang sampai sebaiknya dari gudang/admin sales, bukan penjualnya | kode |
| **SD10** | **Tidak ada jalan resmi bagi penjualan untuk meminta barang dari PT lain**: sales & admin-sales (jika ada) **403** di seluruh `/api/interco/*`, padahal papan stok menampilkan isyarat `has_intercompany_opportunity` | uji nyata |
| **SD11** | Peran dikodekan sebagai **literal string** di ~63 titik backend & ~81 titik frontend (`"sales"`, `"manager"`, …) + `role_satisfies` memakai peringkat hard-code → menambah peran baru berisiko getas bila tanpa registry peran | pemindaian |

### Yang sudah baik (pola untuk ditiru)
- **Pelanggan** sudah difilter per `sales_pic` (milik saya vs semua).
- **Beranda Sales "Performa Saya"** (`GET /api/home/sales`) sudah kaya: komisi MTD
  **rincian per-SKU** (Batik Rp 45.052 · Tenun Rp 35.041), proyeksi akhir bulan
  Rp 248.291, target, KPI, riwayat, pelanggan, penagihan saya, pesanan terbaru.
- **Worklist penagihan** (`/api/collection-worklist`) sudah difilter ke sales sendiri.
- Ambang & peran penyetuju SO sudah **configurable**, bukan hard-code.

---

## 4. USULAN PEMBAGIAN DOMAIN (untuk dikonfirmasi pemilik)

Prinsip: **yang menjual tidak boleh menyatakan uang sudah masuk** (SoD), dan
**pekerjaan administratif jangan menumpuk di manajer**.

| Pekerjaan | Sales (lapangan) | **Admin Sales** (usulan baru) | Manager | Gudang | Admin sistem |
|---|---|---|---|---|---|
| Cari & kelola pelanggan sendiri, kunjungan | **A** | lihat semua | lihat semua | — | — |
| Buat SO / penawaran | **A** | A (atas nama sales) | A | — | — |
| Ajukan harga khusus / kredit | **A** (ajukan) | A (ajukan) | **memutuskan** | — | — |
| Verifikasi & lengkapi SO (alamat, syarat bayar, pajak, dokumen) | — | **A** | R | — | — |
| Perbaiki alokasi stok/roll, pecah kirim | — | **A** | R | konsultasi | — |
| **Konfirmasi SO** → memicu tugas gudang | — | **A** | A | — | — |
| Setujui SO bernilai besar (di atas ambang) | — | — | **A** | — | — |
| Pick · packing · kirim | — | pantau | pantau | **A** | — |
| Cetak Surat Jalan / Invoice / kirim dokumen | lihat | **A** | R | cetak SJ | — |
| **Terbitkan Faktur Pajak keluaran** | ❌ (dicabut) | **A** | R | — | — |
| **Catat penerimaan uang (kwitansi AR)** | ❌ (dicabut) | **A** | R | — | — |
| Putuskan selisih pembayaran / bebaskan denda | ❌ (dicabut) | usulkan | **A** | — | — |
| Follow-up penagihan pelanggan sendiri | **A** | A (semua) | R | — | — |
| Retur pelanggan | **A** (ajukan) | **A** (proses dokumen) | **menyetujui** | terima barang | — |
| **Pembelian antar-entitas** (PT lain diperlakukan seperti supplier) | lihat isyarat stok | **A** (yang mengeklik) | setujui di atas ambang | terima barang | — |
| Target & skema insentif | lihat milik sendiri | lihat | **A** | — | — |
| Master produk/harga PT, entitas, pengguna, konfigurasi | — | — | R | — | **A** |

*A = pelaku · R = pengawas/peninjau*

### Usulan matriks izin peran baru `sales_admin`
```
order:            view, create, update, confirm, print        (TANPA approve)
customer:         view, create, update
document:         view, create, print
tax_invoice:      view, create, replace, print                (cancel → manager)
ar_receipt:       view, create                                (void → manager)
payment_plan:     view, create, update
penalty:          view, issue                                 (waive/adjust → manager)
payment_variance: view                                        (decide → manager)
sales_return:     view, create, update                        (approve → manager)
price_approval:   view, create, update                        (approve → manager)
interco:          view, create, update, invoice               (settle/cancel → manager)
wms:              view                                        (pantau progres, tanpa aksi)
inventory:        view
pricelist:        view
product/uom/warehouse/template: view
finance_case:     view, create
esign/document_delivery: view, sign/send
reports:          view                                        (tanpa export biaya/HPP)
```
Dicabut dari peran `sales`: `tax_invoice.create/print` · `ar_receipt.create` ·
`payment_variance.decide` · `payment_plan.create/update` (sisakan `view`).
Ditambahkan ke peran `sales`: `wms.view` **atau** endpoint ringkas "status pengiriman
pesanan saya" (menutup SD3), dan izin melihat kunjungannya sendiri (menutup SD4).

### Usulan hirarki
`role_satisfies` diubah menjadi registry: `sales:1 · warehouse:1 · sales_admin:2 ·
manager:3 · admin:4`, dengan pemetaan `required_role` ikut registry (bukan angka ajaib).

---

## 5. USULAN UI/UX (pembeda pengalaman, bukan sekadar menu dimatikan)

### 5.1 Sales (lapangan) — "ruang kerja saya"
- Beranda **Performa Saya** (sudah ada) tetap jadi landing.
- Daftar SO **default "Pesanan Saya"** (tutup SD5) + sakelar "Semua (PT ini)" hanya bila berwenang.
- Kartu pesanan menampilkan **status perjalanan barang** (dipesan → disiapkan → dikirim →
  diterima) tanpa membuka layar gudang (menutup SD3 tanpa memberi akses aksi gudang).
- **Tanpa** angka HPP/margin, tanpa tombol faktur pajak/kwitansi.
- Isyarat stok: "stok PT ini 7 · **tersedia di PT lain**" → tombol **"Minta dari PT lain"**
  yang membuat **permintaan internal** ke Admin Sales (bukan langsung transaksi).

### 5.2 Admin Sales — "meja kerja" berbasis ANTREAN (bukan menu)
Satu layar dengan antrean kerja yang jelas jumlahnya:
1. **Perlu diverifikasi** (SO baru dari sales: alamat/syarat bayar/pajak/dokumen lengkap?)
2. **Siap dikonfirmasi** (sudah disetujui → tekan konfirmasi, tugas gudang lahir)
3. **Menunggu keputusan manajer** (harga khusus/kredit/nilai) — hanya memantau
4. **Siap cetak Surat Jalan / Invoice**
5. **Siap terbitkan Faktur Pajak**
6. **Uang masuk perlu dicatat / dialokasikan** ke invoice
7. **Jatuh tempo & pengingat**
8. **Retur menunggu proses dokumen**
9. **Permintaan internal dari sales** (stok kurang → **buat pembelian antar-entitas**)
Setiap baris: konteks pelanggan + nilai + umur (SLA) + tombol tindakan tunggal.

### 5.3 Pembelian antar-entitas dari sisi Admin Sales (keputusan pemilik #2)
Entitas lain **diperlakukan seperti supplier**, **bukan** pelanggan:
- Di layar Pembelian, pemasok bisa bertipe **"Entitas grup"** (mis. CV Kanda Suka) dan
  wajib punya **kontrak internal** (mekanisme `supplier_contracts` `partner_kind="entity"`
  yang sudah ada) sebelum harga bisa dipakai.
- Dokumen tetap lahir **kembar** lewat mesin Antar Entitas (tidak boleh lewat PO biasa —
  lihat pagar E7.2 di `plan.md`), dan **jangan** membuat pelanggan baru untuk PT sendiri.
- Pembeda tetap ada di **menu Antar Entitas**; di layar pembelian cukup ditandai
  lencana "Antar Entitas" supaya alurnya terasa sama seperti membeli dari supplier.

---

## 6. DAMPAK TEKNIS MENAMBAH PERAN
- **Registry peran** baru (`backend/role_registry.py` + `frontend/src/config/roles.js`):
  `{key, label, rank, home_view, cross_entity, description}` — sumber tunggal untuk
  matriks izin, hirarki `role_satisfies`, filter nav, beranda per peran, dan pilihan role
  di formulir pengguna.
- **~63 rujukan literal di backend** & **~81 di frontend** perlu diarahkan ke registry
  (bertahap: yang menentukan wewenang lebih dulu).
- Formulir pengguna (`AdminView.jsx`) & matriks izin (`PermissionMatrixRecords.jsx`)
  otomatis mendukung peran baru begitu registry dipakai.
- Migrasi data: akun yang sekarang `manager` tetapi sebenarnya admin sales → diubah
  perannya (daftarnya perlu ditentukan pemilik).

---

# 7. PENYELARASAN DENGAN DEFINISI PEMILIK (2026-08-10)

**Definisi pemilik (kalimat aslinya):**
> "sales hanya bisa menjual barang, memiliki basis salesnya, membuat so, view status
> lifecycle, dan hanya SO nya dia sendiri yang dimiliki… sales memang hanya fokus di
> lapangan, sales tidak terlalu mengurus operasional atau management."
>
> "ADMIN sales ini yang memanage keseluruhan SO, mulai dari validasi sampai lanjutan
> misalkan harus transfer antar pt, harus ada yang di reorder barang ke supplier karena
> untuk memenuhi SO… misalkan terjadi retur dari customer maka sales yang mengajukan
> retur yang lalu diproses oleh admin sales."

Inti domain Admin Sales = **pemilik keputusan PEMENUHAN SO**: penuhi dari stok sendiri ·
ambil dari PT lain · reorder ke supplier · tunggu barang masuk.

## 7.1 KABAR BAIK — mesin pemenuhannya SUDAH ADA (terbukti)

| Kemampuan | Endpoint / berkas | Bukti nyata |
|---|---|---|
| **Klasifikasi sumber pemenuhan per baris** | `POST /sales-orders/preview-allocation` | mengembalikan `breakdown{from_stock, from_incoming, inter_company, backorder}`, `primary_mode`, `own_available/own_incoming/own_atp`, `cross_entity[]`, dan **kalimat penjelas** ("Stok on-hand cukup (788). Dapat langsung direservasi.") |
| **Papan Pending SO + jaminan suplai** | `GET /stock/pending-so` | 1 baris nyata: `SO-0009` Tekstil Medan Jaya · minta 300 · `waiting_stock` · status coverage (`covered`/`partial`/`uncovered`) + **promise date** dari PO masuk |
| **Reorder ke supplier 1 klik dari SO** | `POST /sales-orders/{id}/repeat-restock` + `GET /{id}/restock-state` | membuat **PR** dengan **jejak dua arah** (`source="so_repeat"`, `source_ref_id=<so_id>`), notifikasi ke MD, dan `restock-state` menampilkan `open_pr_number` per SO |
| **ATP future-aware** | `GET /stock/atp` | available + incoming(horizon) − pending |
| **Pegging (tahan lunak roll utk demand)** | `POST /inventory/rolls/{id}/earmark` | roll di-earmark ke customer/order, dikecualikan dari alokasi lain |
| **Pesanan khusus (SKU belum ada)** | `/api/special-orders` | jalur MD + purchasing |
| **Backorder auto-fulfill saat barang masuk** | `services/backorder_service.py` | FIFO, owner-scoped, kembali ke `reserved` bila lunas |
| **Beli dari PT lain** | mesin Antar Entitas G-6 | dokumen kembar + kontrak internal + faktur pajak + netting (lihat `AUDIT_ANTAR_ENTITAS.md`) |
| **Retur pelanggan** | `/api/sales-returns` | sales mengajukan · manajer menyetujui · ada karantina & nota kredit |

Bahkan **UI-nya sebagian sudah membedakan peran dengan benar**: `RestockPanel.jsx`
memakai `canRequest = admin/manager/sales` dan `canOpenPR = admin/manager/warehouse` —
sales boleh **meminta** restock tetapi tidak membuka PR-nya.

## 7.2 YANG BELUM SESUAI — daftar penyimpangan (sekarang → seharusnya)

| # | Sekarang (fakta) | Seharusnya (definisi pemilik) |
|---|---|---|
| **A1** | Sales melihat **SO rekannya**: `sales2@` (Bima) melihat 8 SO milik Ayu, nol miliknya | Sales hanya melihat **SO miliknya**; Admin Sales & Manajer melihat semua |
| **A2** | Sales **tidak bisa** melihat progres gudang (`/api/wms/tasks` 403) walau menunya tampil | Sales melihat **perjalanan pesanan** (dipesan → divalidasi → disiapkan → dikirim → diterima → ditagih → dibayar) **read-only**, termasuk "kekurangan dipenuhi lewat `PO-xxxx`" atau "diambil dari PT lain `KSC/IC-0000x`" |
| **A3** | Sales boleh **terbitkan Faktur Pajak**, **catat kwitansi uang masuk**, **putuskan selisih bayar**, buat rencana bayar | Semua pindah ke Admin Sales (uang & pajak bukan urusan lapangan) |
| **A4** | Sales boleh **pegging roll** (`earmark`) dan **memicu PR** lewat repeat-restock, padahal daftar PR untuknya **403** → jalan buntu | Keputusan pemenuhan (pegging/PR/antar-PT) milik **Admin Sales**; sales hanya **meminta** |
| **A5** | Sales boleh `mark-delivered` (mengakui barang sampai) | Gudang atau Admin Sales (setelah surat jalan kembali) |
| **A6** | **Konfirmasi SO** (pemicu tugas gudang) hanya manager/admin | **Admin Sales** — ini pekerjaan administratif, bukan keputusan manajerial |
| **A7** | "Validasi administratif" tercampur jadi persetujuan **`nilai`** yang menuntut role manajer | Pisahkan **verifikasi Admin Sales** (kelengkapan: alamat, syarat bayar, pajak, dokumen) dari **persetujuan Manajer** (nilai besar, kredit, harga khusus) |
| **A8** | Transaksi **Antar Entitas tidak tertaut ke SO** yang memicunya (tidak ada `source_order_id`) — padahal PR sudah punya `source_ref_id` | Tambah tautan dua arah SO ↔ transaksi antar-PT supaya "ambil dari PT lain untuk `SO-0009`" terlacak seperti jalur PR |
| **A9** | Keputusan pemenuhan tersebar di 5 layar milik domain lain (Pembelian/Gudang/Keuangan) | **Satu Meja Admin Sales** berbasis antrean; per baris kekurangan ada 3 tombol: **Ambil dari PT lain · Reorder ke supplier · Tahan untuk barang masuk** |
| **A10** | Peran Admin Sales **tidak ada** | Peran `sales_admin` + registry peran |

## 7.3 TEMUAN KRITIS BARU (L21) — pratinjau pemenuhan memakai ENTITAS YANG SALAH

`POST /sales-orders/preview-allocation` dan `POST /sales-orders/preview-lots`
**mengabaikan konteks entitas**: entitas diambil dari `payload.entity_id` → entitas
pelanggan → **`DEFAULT_ENTITY_ID` (`ent_ksc`)**; `entity_ctx(request)` **tidak pernah dibaca**
(`routers/sales_orders_extra.py:48-56` dan `:83-90`).

Bukti empiris (akun **sales3@ = sales CV Kanda Suka, terkunci 1 entitas**):
```
POST /api/sales-orders/preview-allocation  {items:[Batik 100 yard]}   → 200
   entity_id yang dipakai : ent_ksc  (KSC)         ← BUKAN entitas dia
   own_available          : 788.0    (stok KSC)    ← stok PT lain
   own_incoming           : 800.0
   other_entity_available : 7.0      (stok Kanda dianggap "PT lain")
   explanation            : "Stok on-hand cukup (788). Dapat langsung direservasi."
POST .../preview-allocation {entity_id:"ent_ksc", ...}                → 200 (dipaksa pun diterima)
POST .../preview-lots       {items:[Batik 100 yard]}                  → entity ent_ksc, lot "LOT-001" (lot KSC)
POST .../preview-roll-reconcile {all_entities:true}                   → 200, membocorkan
   nomor roll & kode lot KSC ("RL-632A10", "KSC/LOT-2608-0026") + owner "KSC"
```
**Dampak nyata:** sales Kanda dijanjikan stok 788 yard yang bukan miliknya → SO dibuat →
alokasi gagal/menjadi backorder, atau lebih buruk: janji ke pelanggan tidak bisa ditepati.
Sekaligus **kebocoran** angka & identitas roll/lot PT lain. Ini **wajib** masuk FASE E-0.

## 7.4 RINGKAS: apa yang perlu DIBANGUN untuk domain ini
1. Peran `sales_admin` + registry peran (E8.1).
2. Perbaikan izin (cabut dari sales, tambah ke sales_admin) — E8.2/E8.6.
3. Perbaiki 3 endpoint pratinjau agar ter-scope entitas + `all_entities` hanya untuk peran
   lintas-entitas (**L21**, masuk E-0).
4. Daftar SO **default milik sendiri** untuk sales (A1) + **perjalanan pesanan read-only** (A2).
5. Pisahkan verifikasi administratif dari persetujuan manajerial (A7).
6. Tautan dua arah **SO ↔ transaksi Antar Entitas** (A8) — meniru pola `source_ref_id` PR.
7. **Meja Admin Sales** (A9) — antrean + 3 tombol keputusan pemenuhan per kekurangan.

---

# 8. KEPUTUSAN PEMILIK — SUDAH DIKUNCI (2026-08-10)

| # | Pertanyaan | Keputusan |
|---|---|---|
| 1 | Admin Sales melayani berapa entitas? | **Berbasis penugasan** — bisa dikunci 1 entitas atau diberi beberapa entitas. Jangan masukkan ke `CROSS_ENTITY_ROLES`; pakai `allowed_entity_ids` tersimpan (mekanisme peran non-lintas yang sudah ada) |
| 2 | Siapa mencatat uang masuk & menerbitkan Faktur Pajak? | **Kasir/Finance DIPISAH** → dibuat **2 peran baru**: `sales_admin` **dan** `finance`. Uang masuk (kwitansi AR) + Faktur Pajak keluaran = **`finance`** |
| 3 | Siapa menandai barang diterima pelanggan? | **Boleh gudang maupun Admin Sales** (dicabut dari sales) |
| 4 | Batas kuasa Admin Sales atas pemenuhan SO | **Penuh** — PR/reorder supplier, **ambil dari PT lain**, pegging: **tanpa** persetujuan manajer. Config ambang `antar_entitas.approval_threshold_rupiah` tetap disediakan (default tidak mengunci) |

## 8.1 Pembagian domain FINAL (6 peran)

| Pekerjaan | Sales | **Admin Sales** | **Finance/Kasir** | Manager | Gudang | Admin sistem |
|---|---|---|---|---|---|---|
| Basis pelanggan sendiri, kunjungan | **A** | lihat semua | lihat | lihat | — | — |
| Buat SO | **A** | A | — | A | — | — |
| Lihat perjalanan pesanan (read-only) | **A** (miliknya) | A (semua) | lihat | A | A | — |
| Ajukan harga khusus / kredit | **A** (ajukan) | A (ajukan) | — | **memutuskan** | — | — |
| Verifikasi kelengkapan SO | — | **A** | — | R | — | — |
| **Keputusan pemenuhan**: stok · **ambil dari PT lain** · **reorder supplier** · pegging | minta | **A (penuh)** | — | R | konsultasi | — |
| **Konfirmasi SO** → tugas gudang lahir | — | **A** | — | A | — | — |
| Pick · packing · kirim | pantau | pantau | — | pantau | **A** | — |
| Cetak Surat Jalan / Invoice | lihat | **A** | cetak | R | cetak SJ | — |
| **Faktur Pajak keluaran** | ❌ | ❌ | **A** | R | — | — |
| **Kwitansi / uang masuk (AR)** | ❌ | ❌ | **A** | R | — | — |
| Selisih bayar · terbitkan denda | ❌ | usul | **A** (dalam batas config) | **A** (di luar batas / pembebasan) | — | — |
| Rencana pembayaran | lihat | **A** (usul) | A (ubah) | void | — | — |
| Tandai barang diterima pelanggan | ❌ | **A** | — | A | **A** | — |
| Retur pelanggan | **A** (ajukan) | **A** (proses dokumen) | lihat | **menyetujui** | terima barang | — |
| Follow-up penagihan | **A** (pelanggannya) | A (semua) | **A** | R | — | — |
| Target & skema insentif | lihat milik sendiri | lihat | lihat | **A** | — | — |
| Master data · entitas · pengguna · konfigurasi | — | — | — | R | — | **A** |

*A = pelaku · R = pengawas/peninjau*

Hirarki wewenang (`role_satisfies`, pindah ke registry peran):
`sales:1 · warehouse:1 · sales_admin:2 · finance:2 · manager:3 · admin:4`
