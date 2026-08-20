# POS E-COMMERCE + IA/UX FLOW AUDIT (KN3)

> Diminta user: (1) optimasi POS "rasa e-commerce" agar informasi jelas & mudah —
> analisis flow e-commerce + implementasinya; (2) analisis IA & UX seluruh business-process flow.
> Metode: baca `SalesPortal.jsx`, `ProductCard.jsx`, `CartPanel.jsx`, `CustomerPanel.jsx`,
> `OrderDetailPanel.jsx`, `navigationConfig.js` + login nyata & screenshot. Semua grounded.

---

# BAGIAN A — OPTIMASI POS BERGAYA E-COMMERCE

## A1. KONDISI POS SEKARANG (FAKTA)
Layout 2 kolom: kiri **grid produk (1fr)**, kanan **rail 340px** (Customer + Cart).
- **Discovery** = HANYA search free-text (`name+sku+category+color`). Tidak ada filter kategori, grade, warna/motif, harga, ketersediaan; tidak ada **sort**.
- **ProductCard** menonjolkan **istilah gudang**: Avail / **Resv** (reserved) / Harga; badge Grade; CTA **"Reserve"** (bahasa gudang, bukan "Tambah").
- **Product detail** = panel inline; isinya **sangat warehouse-centric**: tabel On-hand/Reserved/Available per gudang + "Kepemilikan per Entitas · Lot · Gudang · Roll". CTA "Tambah ke Draft".
- **Checkout** = numpuk di satu rail 340px: pilih customer + **form 'Buat Customer' selalu terbuka** + kebijakan dye-lot + cart "Draft Order/Reservasi 3 hari" + total + credit gate + submit.
- **Chrome**: KPI strip global + onboarding checklist memakan **~30% viewport atas** → grid belanja terdorong ke bawah.
- **Qty/UOM** dipilih hanya setelah masuk cart (bukan saat add).

## A2. FLOW KANONIK E-COMMERCE (acuan)
1. **Discover/Browse** — home → kategori → listing dengan **facet filter + sort + search**.
2. **Product Detail** — galeri, varian, harga (termasuk harga khusus/tier), stok ringkas, **add-to-cart (qty + unit)**.
3. **Cart** — review item, ubah qty, subtotal, promo, jelas tombol "Checkout".
4. **Checkout (stepper)** — identitas (customer) → alamat/pengiriman → term/pembayaran → **review**.
5. **Confirmation** — order dibuat, ringkasan, langkah berikutnya, reorder.

## A3. PETA GAP POS vs E-COMMERCE

| Aspek | E-commerce | POS sekarang | Gap |
|---|---|---|---|
| Temukan produk | Facet (kategori/warna/harga) + sort | Search teks saja | 🔴 |
| Browse kategori | Navigasi kategori/motif | Grid flat | 🔴 |
| Kartu produk | Gambar, nama, harga, stok, add | Avail/**Resv**/Harga + "Reserve" | 🟠 jargon gudang |
| Qty/UOM | Pilih di kartu/detail | Hanya di cart | 🟠 |
| Detail produk | Galeri+varian+harga+stok ringkas | Tabel lot/entitas/roll dominan | 🟠 power-user noise |
| Harga konteks | Tier/harga khusus tampil | Harga tunggal; harga khusus baru muncul di cart | 🟠 |
| Cart | Persisten, item count, subtotal | Di bawah fold rail 340px | 🟠 |
| Checkout | Stepper bertahap | Semua numpuk 1 rail | 🔴 beban kognitif |
| Buat customer | Modal saat perlu | Form selalu terbuka di rail | 🟢 |
| Rekomendasi | "Sering dibeli", reorder | Tidak ada | 🟠 (B2B sangat berguna) |
| Mobile/lapangan | Mobile-first | 2-col 340px | 🟠 |

## A4. USULAN REDESAIN POS (B2B tekstil)
**Discover**: katalog dengan **facet rail kiri** (Kategori: Batik/Tenun/Songket/Lurik/Ulos/…, Grade, Warna/Motif, Rentang harga, Ketersediaan/ATP, Entitas/Gudang) + **sort** (harga, ketersediaan, terbaru) + search. Tambah **chip kategori** di atas grid. Tambah **"Sering dibeli customer ini"** (per-customer favorites/reorder) — pembeda B2B yang kuat.
**Kartu**: utamakan gambar besar, nama, **harga (+badge harga khusus jika ada)**, badge ketersediaan; pindah Reserved ke detail; CTA **"+ Tambah"** dengan **stepper qty + pilih unit** inline. (Istilah "reserve/lot" disembunyikan ke detail/cart.)
**Detail**: galeri + varian (warna/motif swatch) + harga (termasuk tier/harga-khusus) + ringkas ketersediaan; **tabel lot/entitas/roll jadi seksi "Detail Gudang (lanjutan)" yang collapsible**.
**Cart → Checkout stepper**: (1) **Customer & Alamat** (buat customer = modal), (2) **Term & Kebijakan Lot**, (3) **Review** (credit gate, ATP/fulfillment, rencana lot) → **Konfirmasi**. Cart persisten (badge item+subtotal) di header POS.
**Chrome**: sembunyikan/auto-collapse onboarding & ramping-kan KPI agar grid naik ke atas.

## A5. FASE POS (saran)
- POS-1: Facet filter + sort + chip kategori + cart persisten (impact tertinggi, risiko rendah).
- POS-2: Kartu produk e-commerce (harga khusus, stepper qty+unit, CTA "Tambah").
- POS-3: Checkout stepper + create-customer jadi modal.
- POS-4: Detail produk (galeri/varian) + lot/entitas collapsible.
- POS-5: "Sering dibeli / reorder" per customer.

---

# BAGIAN B — IA & UX SELURUH BUSINESS-PROCESS FLOW

## B1. MODEL IA SEKARANG
IA **berorientasi MODUL** (Penjualan, Pembelian, Gudang, Keuangan, …), difilter per role. Tidak berorientasi **tugas/alur**. Pengguna harus tahu modul mana untuk tiap langkah.

## B2. PETA PROSES (end-to-end)
**O2C (Order-to-Cash / Sales):**
`Customer/CRM → (Approval Harga bila khusus) → POS buat order → Pesanan Penjualan (SO) → Outbound/WMS (pengiriman) → Faktur Pajak Jual → Penagihan (CRM) → Komisi (Sales Force)`
**P2P (Procure-to-Pay / Purchasing):**
`Saran Reorder / Purchase Requisition → RFQ → PO / Blanket-PO call-off → Inbound/QC (terima) → Landed Cost (HPP) → Tagihan Supplier → Faktur Pajak Masukan → Kas`
**WMS:** `Inbound → QC → Stok/Putaway → Transfer (intra/antar-entitas) → Cycle Count → Outbound` (sudah jadi tab di view `operations` — pengelompokan baik).
**Finance:** mayoritas **comingSoon** (CoA, GL, Bank, Pajak, AR, Closing).

## B3. ANALISIS KONTINUITAS (apa yang nyambung)
- ✅ **OrderDetailPanel = HUB yang baik**: dari 1 SO bisa lihat **fulfillment, shipments (cetak Surat Jalan), faktur pajak (cetak)**, status pembayaran. Pola yang BENAR.
- ❌ **Tidak ada "process timeline" lintas-dokumen** di luar order detail. Mis. dari **PO** tak ada lompatan ke penerimaan→landed cost→vendor bill; dari **SO** ke penagihan/komisi harus pindah menu manual.
- ❌ **Penagihan & komisi terpisah** dari order detail (di modul CRM) — alur O2C terputus secara navigasi.

## B4. TEMUAN IA (RANKED)
| # | Sev | Temuan | Bukti |
|---|---|---|---|
| IA1 | 🔴 | **~40% menu = `comingSoon`** (21/52 item). Sidebar penuh placeholder non-fungsional → sulit menemukan fitur yang benar-benar jalan. | navConfig |
| IA2 | 🔴 | **IA berorientasi modul, bukan alur**; tak ada **process timeline/dokumen-terkait** lintas modul (kecuali order detail). | navConfig + OrderDetailPanel |
| IA3 | 🟠 | **Approval tersebar**: Pusat Persetujuan + Approval Harga + Approval Pembelian + Approval Rules + per-modul. | navConfig |
| IA4 | 🟠 | **Penamaan campur & ambigu**: "Beranda" (redirect), "Operations", "Returns & Barang Sisa" (2 konsep), ID/EN campur. | navConfig |
| IA5 | 🟠 | **Tanpa breadcrumb / wayfinding** antar langkah proses. | umum |
| IA6 | 🟢 | Densitas tinggi, tanpa progressive disclosure (sama untuk semua peran). | umum |

## B5. REKOMENDASI IA
- **R-IA1**: Pisahkan `comingSoon` — sembunyikan default atau taruh di grup "Segera Hadir" yang collapsed; sidebar utama hanya fitur live.
- **R-IA2**: Tambah **"Dokumen Terkait / Process Timeline"** pada dokumen kunci (SO, PO): tampilkan rantai (requisition→PO→GRN→landed cost→bill; SO→shipment→faktur→pembayaran→komisi) dengan deep-link. Perluas pola `OrderDetailPanel` ke PO.
- **R-IA3**: **Pusat Persetujuan terpadu** — satu inbox semua approval (harga, pembelian, kredit) dengan filter tipe.
- **R-IA4**: **Mode "Alur Tugas"** opsional — selain menu modul, sediakan landing per-peran berbasis tugas (lihat audit role): "Buat Order", "Tagih", "Terima Barang", dst.
- **R-IA5**: Breadcrumb + penamaan konsisten (Bahasa Indonesia baku).

---

# BAGIAN C — KETERKAITAN DENGAN AUDIT SEBELUMNYA
- **POS checkout stepper** + **Sales Home** (audit role) saling melengkapi: Home = "apa yang harus saya kerjakan", POS = "kerjakan transaksinya".
- **Sembunyikan jargon biaya/lot dari sales** sejalan dengan G2 (jangan ekspos HPP) — detail lot/entitas jadi area lanjutan (admin/warehouse).
- **Process timeline** memberi wadah menampilkan **komisi per-SKU** di hilir O2C (saat lunas).

# BAGIAN D — PERTANYAAN/PUTUSAN
1. **Prioritas**: kerjakan **POS e-commerce** dulu, atau **Role/Sales-Home** dulu, atau **IA cleanup (sembunyikan comingSoon + process timeline)** dulu?
2. **Facet POS**: facet wajib mana lebih dulu — Kategori, Grade, Warna/Motif, Harga, Ketersediaan, Entitas? (pilih top-3)
3. **Checkout**: setuju ubah ke **stepper 3 langkah** + create-customer jadi modal?
4. **comingSoon**: sembunyikan total, atau grup "Segera Hadir" collapsed?
5. **Process timeline**: bangun di SO & PO sekaligus, atau SO dulu?
6. **"Sering dibeli/reorder" per customer**: termasuk MVP POS atau fase lanjutan?
