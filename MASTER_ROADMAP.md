# MASTER ROADMAP — KN3 ERP/WMS (Future-Proof Program Plan)

> Konsolidasi 3 audit (Insentif, Role/UX, POS+IA) + fondasi arsitektural + backlog lama.
> Semua temuan grounded dari kode & data. Bahasa: Indonesia. Status: **RENCANA — belum dieksekusi.**
> Dokumen turunan: `INCENTIVE_REDESIGN_ANALYSIS.md`, `ROLE_UX_GAP_AUDIT.md`, `POS_ECOMMERCE_AND_IA_AUDIT.md`.

---

## 0. RINGKASAN GAP (TERKONFIRMASI, GROUNDED)

### A. Insentif
- Komisi sekarang **agregat** (collected × tier%), bukan per-SKU. Model baru = **per-SKU × (kategori × diskon × entitas)**, **margin-aware**, diakui **saat lunas**.
- Line item SO **tak menyimpan kategori**; kategori produk **free-text** (perlu master).
- **Tidak ada `payments[]`/`paid_total`** di order → leg "terima pembayaran/collection" tipis (perlu **AR receipt ledger**).
- Cost ada di **roll** (`inventory_rolls.base_unit_cost`, `landed_cost_total`), tapi `allocations` order **tak membawa roll/cost** → margin-aware perlu **costing service (WAC)**.
- `system_settings` ada → wadah config engine. UOM service matang (meter/yard/kg) → satuan insentif konfigurabel.

### B. Role/UX
- Pembeda peran dangkal (filter menu + sedikit `isManager`). **Tidak ada Sales Home**; **HPP/biaya & back-office terekspos ke sales** (nav + permission). Admin tanpa control-tower. Chrome/KPI identik lintas peran.

### C. POS & IA
- POS = grid flat + search teks; jargon gudang; checkout numpuk 1 rail. Tanpa facet/sort/checkout-stepper.
- **~40% menu (21/52) = "coming soon"**. IA berorientasi modul, bukan alur. **Tak ada process-timeline** lintas dokumen (kecuali `OrderDetailPanel` — pola hub yang baik untuk diperluas).

---

## 1. PRINSIP FUTURE-PROOF (NON-NEGOTIABLE)
1. **Config-driven, bukan hardcode** — mode engine, recognition basis, mekanik diskon, role-home, feature flags di `system_settings`/permission matrix.
2. **Strategy pattern untuk komisi** — `per_sku` | `achievement_tiered` | (future: `margin_share`) pluggable; data lama tetap kompatibel.
3. **Single source of truth** — Costing (WAC) & AR ledger jadi sumber tunggal untuk margin, AR, credit, insentif, dan (future) GL.
4. **Snapshot historis** — kategori/harga/cost di-snapshot pada dokumen agar laporan masa lalu tak berubah saat master diubah.
5. **Schema currency-ready** — tambahkan `currency` + `fx_rate` (default IDR) sekarang agar multi-currency aditif, bukan rewrite.
6. **Idempotent & auditable** — migrasi/backfill aman diulang; semua perubahan tercatat di `audit_logs`.
7. **Reusable UI patterns** — perluas pola baik yang ada (CRM role-scoping, OrderDetailPanel hub, KNSelect, design tokens).

---

## 2. FONDASI LINTAS-SEKTOR (BUILD ONCE)

| ID | Fondasi | Tujuan | Mengaktifkan |
|---|---|---|---|
| **F1** | **Master Kategori Produk** (`product_categories`) + snapshot di SO line | Hilangkan kebocoran free-text; basis insentif/BI/filter | EPIC2,4,5 |
| **F2** | **Costing Service (WAC)** dari `inventory_rolls` (landed-cost aware) | Sumber tunggal COGS/margin | EPIC4, BI, GL |
| **F3** | **AR Receipt / Payment Application ledger** (cash_tx ref→order/line, update paid_total/status) | Collection akurat, credit gate, insentif-saat-lunas | EPIC3,4,7 |
| **F4** | **Settings/Config service** (`system_settings`) + feature flags | Engine & UX configurable | semua |
| **F5** | **Permission + Role-Home config** | Pembeda peran tanpa hardcode | EPIC0,1 |
| **F6** | **Document Relations / Process Timeline** service | Navigasi antar-dokumen end-to-end | EPIC6 |
| **F7** | **Money/Currency abstraction** (currency+fx_rate, default IDR) | Multi-currency aditif | EPIC7 |

---

## 3. EPIK & FASE

### EPIC 0 — IA Hygiene + Scaffold Fondasi  ⏱️ S  (risiko rendah, quick win)
- Pisahkan `comingSoon` → grup "Segera Hadir" collapsed / hidden (flag F4). Sidebar utama hanya fitur live.
- Perbaiki sizing filter (override `.field width:100%`), filter-bar kompak/collapsible. Breadcrumb + penamaan konsisten.
- Scaffold **F4 Settings service** + **F5 role-home registry**.
- **DoD:** sidebar bersih; filter ringkas; settings service dipakai ≥1 flag; tak ada regresi.

### EPIC 1 — Role Experience & Sales Home  ⏱️ M  (depends F4,F5)
- **Sales Home "Performa Saya"**: komisi MTD (akrual+proyeksi), target & pencapaian, customer saya + kredit, penagihan saya, order terbaru, quick "Buat Order" — **tanpa biaya/HPP**.
- **Admin Home (Control Tower)**: penjualan hari/MTD, AR aging, approval pending, low-stock/reorder, ringkasan payout insentif, switch entitas.
- **Manager Home**: performa tim (leaderboard, target, koleksi, approval).
- **Tighten akses sales** (cabut HPP/vendor bill/input tax/PO; tetap stok read) via **permission matrix**; re-scope faktur pajak/price-approval delete.
- Chrome/KPI **per peran**.
- **DoD:** tiap peran punya landing relevan; sales tak lagi melihat biaya/back-office; semua via config; testing role-based lulus.

### EPIC 2 — Master Kategori + Snapshot SO  ⏱️ M  (F1; enabler EPIC4/5)
- `product_categories` CRUD (admin) + dropdown di form produk + migrasi normalisasi 7 kategori.
- Snapshot `category` (+`base_qty`,`base_unit`) pada SO line saat create; **backfill** order historis (idempotent).
- **DoD:** kategori terkelola; line SO baru & lama punya kategori; laporan stabil.

### EPIC 3 — Costing (WAC) + AR Receipt Ledger  ⏱️ L  (F2,F3; enabler EPIC4/7)
- **Costing service**: WAC per produk/entitas dari `inventory_rolls` (incl. landed cost). API `GET /costing/wac`.
- **AR Receipt**: catat pembayaran customer → apply ke order (+alokasi pro-rata ke line) → update `paid_total`/`payment_status`; integrasi ke Collection Worklist & credit gate.
- **DoD:** pembayaran tercatat & memengaruhi AR/credit; WAC tersedia per line; uji akurasi.

### EPIC 4 — Incentive Engine v2 (Per-SKU, 3 Faktor, Margin-aware, On-Collection)  ⏱️ L  (depends EPIC2,3)
- Koleksi **`incentive_rates`**: (entity × category), `incentive_unit` (konfigurabel/UOM), `per_unit_amount`, **discount mechanics konfigurabel** (faktor tier / potong Rp / cutoff; ambang Rp-per-unit atau %), `margin_cap`.
- **Strategy pattern**: `compute_commission(strategy)` → `per_sku` (default) | `achievement_tiered` (arsip, tetap). Mode di settings (F4).
- Engine: iterasi **line terbayar** (F3), konversi UOM, rate×discount_factor, **cap by margin** (F2), pro-rata partial-payment.
- **Editor UI**: matriks entitas×kategori + mekanik diskon + margin cap. Editor achievement lama → "Arsip".
- **Sales Home**: breakdown komisi **per-SKU/kategori** + proyeksi saat lunas.
- **DoD:** komisi per-SKU benar & teruji (unit+integration), margin cap aktif, mode lama tetap jalan.

### EPIC 5 — POS E-commerce  ⏱️ L  (benefit dari F1; bisa paralel sebagian EPIC1)
- **Discover**: facet rail (Kategori/Grade/Warna/Harga/ATP/Entitas) + sort + chip kategori + search; "Sering dibeli customer ini" (reorder).
- **Kartu**: gambar utama, nama, **harga (+badge harga khusus)**, badge ketersediaan, **stepper qty + pilih unit**, CTA "+ Tambah". Reserved/lot → detail.
- **Detail**: galeri/varian + harga + ketersediaan ringkas; **lot/entitas/roll → seksi "lanjutan" collapsible**.
- **Checkout stepper 3 langkah** (Customer&Alamat → Term&Lot → Review/credit/ATP) ; **Buat Customer = modal**; cart persisten (badge item+subtotal).
- **DoD:** alur belanja jelas & cepat; credit gate & ATP tetap berlaku; mobile-friendly; testing lulus.

### EPIC 6 — Process Timeline / Document Hub  ⏱️ M  (F6)
- Service relasi generik + **timeline UI** di SO & PO: rantai PR→PO→GRN→LandedCost→Bill; SO→Shipment→Faktur→Bayar→Komisi (deep-link). Perluas pola `OrderDetailPanel`.
- **DoD:** dari SO/PO bisa lompat ke seluruh dokumen terkait; tak ada dead-end.

### EPIC 7 — Finance & Integrasi Backlog  ⏱️ L+  (F3,F7)
- **AR/Piutang** (atas F3), **Kas**, lalu **CoA/GL** menggantikan "coming soon" bertahap.
- **Backlog lama**: PO PDF email (perlu **integrasi SMTP** → integration agent), **Budget/Commitment Control**, **Multi-currency/FX** (pakai F7).
- **DoD:** modul finance inti live; backlog terintegrasi bertahap.

---

## 4. DEPENDENCY GRAPH
```
F4,F5 ─▶ EPIC0 ─▶ EPIC1
F1    ─▶ EPIC2 ─▶ EPIC4
F2,F3 ─▶ EPIC3 ─▶ EPIC4
EPIC2 ─▶ EPIC5
F6    ─▶ EPIC6
F3,F7 ─▶ EPIC7
```

## 5. URUTAN REKOMENDASI (value × dependency)
1. **EPIC 0** — IA hygiene + scaffold (quick win, buka jalan)
2. **EPIC 1** — Role/Sales Home (UX value tinggi, mandiri)
3. **EPIC 2** — Category master + snapshot (enabler)
4. **EPIC 3** — Costing + AR receipt (enabler)
5. **EPIC 4** — Incentive v2 (fitur unggulan)
6. **EPIC 5** — POS e-commerce (mulai setelah EPIC2; sebagian paralel)
7. **EPIC 6** — Process timeline
8. **EPIC 7** — Finance + backlog (PO PDF email, budget, multi-currency)

> Catatan kecepatan: EPIC 0–1 memberi dampak UX tercepat; EPIC 2–4 menuntaskan visi insentif; EPIC 5 menyempurnakan POS; EPIC 6–7 mematangkan ERP & menutup backlog.

## 6. RISIKO & MITIGASI
- **Backfill kategori/cost** → buat **idempotent + dry-run**; snapshot agar histori stabil.
- **Margin-aware** bergantung kualitas cost roll → fallback ke WAC produk; tandai line tanpa cost.
- **On-collection partial** → kebijakan pro-rata eksplisit + uji angka.
- **Perubahan permission sales** → lewat matrix (reversible), umumkan & uji regresi POS.
- **Strict 800-line schema** → schema baru ke `schemas_crm.py`/modul baru, hindari membengkakkan `schemas.py`.
- Selalu `bash scripts/seed_reset.sh` setelah perubahan skema/koleksi.

## 7. DEFINISI SELESAI PROGRAM
Setiap EPIC: kompilasi bersih → screenshot → `testing_agent_v3` (sesuai cakupan) → bug ditutup → `plan.md` di-update COMPLETED. Tidak menyatakan selesai bila ada bug diketahui.
