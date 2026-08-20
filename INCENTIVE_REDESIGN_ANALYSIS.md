# DEEP ANALYSIS — Redesain Skema Insentif Sales (Per-SKU/Kategori) + Role-based UI

> Disusun sebelum implementasi. Sumber: pembacaan langsung kode & data (grounded, bukan asumsi).
> Bahasa: Indonesia. Modul: CRM/Sales Force, Produk/Inventory, Sales Order, Purchasing, UI/UX.

---

## 1. RINGKASAN PERMINTAAN USER

1. **Insentif BUKAN dari achievement sales**, melainkan **per SKU yang dijual, dihitung per satuan** (qty/pcs/yard) dengan nilai insentif berbeda per SKU/kategori.
2. **Simpan** konfigurasi insentif berbasis achievement yang lama (untuk kebutuhan masa depan) — jangan dihapus.
3. **3 faktor penentu insentif baru:**
   - **(a) Kategori SKU** → nilai insentif berbeda per kategori.
   - **(b) Harga/diskon yang diberikan sales** → jika diskon di atas "X ribu" maka insentif berkurang.
   - **(c) Entitas** → insentif berbeda per entitas legal.
4. **Tampilan beda Admin vs Sales** — Sales butuh **dashboard personal** lengkap (semua informasi dia).
5. **UI polish** — filter terlalu besar, boros space.

---

## 2. KONDISI NYATA SISTEM (HASIL EKSPLORASI)

### 2.1 Mesin komisi saat ini (`services/sales_force_service.py`)
- `compute_commission()` = **AGREGAT**:
  `base_amount (collected ATAU sales) × tier_rate(achievement) / 100 + bonus_new_customer × new_customers`.
- **Tidak menyentuh line item sama sekali.** Murni dari total `total_collected` / `total_sales` per periode.
- Skema disimpan di koleksi `sales_incentives` (basis: collection|sales|tiered, tiers[{min_achievement, rate}], bonus...).

### 2.2 Struktur Sales Order (DB `sales_orders`)
- Order menyimpan `entity_id` ✓ (mis. `ent_ksc`).
- **Line item** menyimpan: `product_id, sku, product_name, quantity, unit, price, discount_percent, subtotal, discount_amount, line_total`.
- **TIDAK menyimpan `category`** pada line item. (Harus di-join ke produk atau di-snapshot.)
- Diskon: tersedia `discount_percent` & `discount_amount` (Rp) **per line**; ada juga **diskon level order** (`order_discount_percent`, `order_discount_amount`) yang belum dialokasikan ke per-line.

### 2.3 Produk / Inventory (`schemas.py ProductPayload`, koleksi `products`)
- `category` = **free-text**, default `"Kain"`. 7 produk seed punya kategori bersih: Batik, Tenun, Lurik, Songket, Ulos, Jumputan, Endek.
- `base_unit` semua `"meter"`; `uom_conversions` mis. `roll→meter ×50`.
- `harga_pokok` = **kosong/None** (cost sebenarnya di level **roll** via Landed Cost). → Insentif berbasis margin = mahal/kompleks.
- Engine UOM solid (backend `uom_service.py` + frontend `utils/uom.js`): konversi meter/yard/cm/inch + catch-weight kg. → Konversi "per satuan" bisa diandalkan.

### 2.4 Entitas
- Koleksi entitas ada (`BusinessEntityCreate`): `short_name`, `doc_prefix`, `default_tax_mode`. Order sudah ber-`entity_id`. → Faktor entitas siap dipakai.

### 2.5 Role & Navigasi (`config/navigationConfig.js`, `App.js`)
- `defaultViewForRole`: admin→`admin`, manager→`reports` (ManagerDashboard), warehouse→`operations`, **sales→`sales` (POS)**.
- **Tidak ada Sales personal dashboard.** Manager punya `ManagerDashboard.jsx`; sales tidak.

### 2.6 Bug UI Filter (`features/crm/CustomerList.jsx` + `styles/components.css`)
- Filter pakai `className="field w-[150px]"`, tetapi `.field { width:100% }` (specificity setara, urutan menang) → filter **membengkak full-width**. Itu penyebab "boros space" di screenshot.

---

## 3. DESAIN MODEL INSENTIF BARU (USULAN)

### 3.1 Formula
Untuk salesperson **S** pada periode **P**:
```
total_incentive(S,P) = Σ (untuk tiap line L yang terjual di P, pada order milik customer S):
      line_incentive(L)
    + bonus opsional (customer baru / produk fokus)   [warisan, opsional]

line_incentive(L) = qty_in_incentive_unit(L)
                   × per_unit_amount( entity(L), category(L) )
                   × discount_factor( diskon_per_unit(L) )
```

### 3.2 Koleksi konfigurasi BARU: `incentive_rates`
```jsonc
{
  "id": "irate_...",
  "entity_id": "ent_ksc",          // faktor (c) ENTITAS
  "category": "Batik",             // faktor (a) KATEGORI
  "incentive_unit": "meter",       // satuan acuan nilai insentif
  "per_unit_amount": 2000,         // Rp insentif per 1 satuan
  "discount_rules": [              // faktor (b) DISKON menggerus insentif
    { "max_discount_per_unit": 5000,  "factor": 1.0 },
    { "max_discount_per_unit": 10000, "factor": 0.7 },
    { "max_discount_per_unit": null,  "factor": 0.4 }   // di atas → 0.4
  ],
  "active": true,
  "created_by": "...", "created_at": "..."
}
```
- Lookup rate = match `(entity_id, category)`. Fallback: kategori `*` (default entitas) → global default.
- `discount_factor`: ambil faktor tier pertama yang `diskon_per_unit ≤ max_discount_per_unit`.

### 3.3 Yang dibutuhkan saat hitung (per line)
- `category(L)` → **snapshot di order** (disarankan) ATAU join `product_id→products.category` (cepat, v1).
- `entity(L)` → dari `order.entity_id` ✓.
- `qty_in_incentive_unit` → konversi `quantity/unit` → `incentive_unit` via UOM engine ✓.
- `diskon_per_unit(L)` → `(discount_amount_line [+ alokasi order_discount]) / quantity` (Rp/satuan).

### 3.4 Pertahankan model lama
- Koleksi `sales_incentives` (achievement-tiered) **tetap disimpan** & editornya tetap ada (label "Lanjutan / Achievement (arsip)").
- Mesin komisi diberi **mode**: `per_sku` (baru, default) | `achievement_tiered` (lama). Bisa di-set per entitas/global di Settings.

---

## 4. PETA DAMPAK LINTAS-MODUL (JUJUR, BER-TINGKAT)

| Modul | Tingkat | Perubahan |
|---|---|---|
| **CRM / Sales Force** | 🔴 TINGGI | Koleksi `incentive_rates`; mesin `compute_commission_per_sku` (iterasi line item); endpoint CRUD rates; editor UI baru; commission card/history per kategori. |
| **Produk / Inventory** | 🟠 SEDANG | Kategori jadi **master taxonomy** (`product_categories`) agar tak bocor; form create/edit/import produk pakai daftar terkontrol; migrasi normalisasi kategori produk. |
| **Sales Order** | 🟠 SEDANG | Snapshot `category` (+`base_quantity`,`base_unit`) per line saat create; alokasi diskon order ke line; **script backfill** order historis. |
| **Purchasing** | 🟢 RENDAH | Hanya berbagi **master kategori** yang sama (konsistensi). TIDAK ada perubahan struktural PO — KECUALI jika insentif dibuat margin-aware (opsi, butuh HPP/landed cost). |
| **Role-based UI** | 🟠 SEDANG | **Sales Personal Dashboard** baru (KPI saya, komisi per-SKU/kategori, target, customer saya, penagihan saya, order saya) + jadikan default view sales. Admin/Manager = view konfigurasi & tim. |
| **UI Polish** | 🟢 RENDAH | Rapikan filter (perbaiki override `.field width:100%`), filter bar kompak/collapsible. |

> Catatan jujur soal Purchasing: dampaknya **tidak struktural** kecuali Anda mau insentif **margin-aware** (insentif dibatasi margin = harga − HPP dari landed cost). Itu menyentuh purchasing/landed cost secara nyata dan saya sarankan **ditunda** ke fase terpisah agar tidak memperlambat MVP insentif.

---

## 5. RENCANA IMPLEMENTASI BERTAHAP (USULAN)

**Fase 1 — Master Kategori (fondasi data)**
- Koleksi `product_categories` + CRUD admin + dropdown di form produk + migrasi normalisasi.

**Fase 2 — Snapshot kategori di Sales Order + backfill**
- Tulis `category/base_unit/base_quantity` per line saat create; script backfill order lama.

**Fase 3 — Engine Insentif Per-SKU + konfigurasi**
- Koleksi `incentive_rates` + endpoint CRUD + `compute_commission_per_sku` + mode switch (pertahankan lama).

**Fase 4 — Editor UI "Insentif per Kategori/Entitas"**
- Tab baru di "Skema & Target": matriks entitas×kategori (per_unit_amount, incentive_unit, discount_rules). Editor achievement lama jadi "arsip".

**Fase 5 — Sales Personal Dashboard + pembeda role**
- View `sales-home` (default sales): komisi per-SKU breakdown, target, customer, penagihan, order. Admin/Manager tetap di view konfigurasi/tim.

**Fase 6 — UI Polish filter** (cepat, bisa paralel).

Setiap fase: compile-check → screenshot → testing agent (backend+frontend) → seed_reset bila perlu.

---

## 6. PERTANYAAN TERBUKA (WAJIB DIJAWAB SEBELUM CODING)

1. **Kapan insentif "diakui"?** saat **terjual** (order confirmed) atau saat **tertagih/lunas** (collected)?
2. **Satuan insentif** seragam **meter** (base) atau **per kategori** boleh beda (meter/pcs/yard)?
3. **Mekanik diskon menggerus insentif** — pilih: (a) **faktor tier** (mis. diskon/unit > Rp10rb → ×0.4), (b) **potong Rp** proporsional, atau (c) **cutoff keras** (di atas ambang → 0)? Dan ambang diukur **per-unit Rp**, **per-line Rp**, atau **%**?
4. **Cakupan diskon**: hanya diskon item, atau termasuk **diskon level order** yang dialokasikan ke line?
5. **Kategori → master taxonomy + migrasi** produk: setuju?
6. **Snapshot kategori ke order historis (backfill)**: setuju?
7. **Margin-aware** (insentif dibatasi margin via HPP/landed cost): perlu sekarang atau **tunda**?
8. **Granularitas rate**: cukup **(entitas × kategori)** global, atau perlu **override per-salesperson**?

---

## 7. KEPUTUSAN USER (TERKONFIRMASI)

1. **Pengakuan insentif = saat TERTAGIH/LUNAS (collected/paid).** (1.b)
2. **Satuan insentif MENGIKUTI UOM yang dipakai** — JANGAN di-fix ke satu satuan. Produk bisa yard/meter/kg/dll.
   → `incentive_unit` per kategori-rate harus konfigurabel; engine mengonversi qty terjual (UOM apa pun) ke satuan rate via UOM engine (sudah dukung meter/yard/cm/inch + catch-weight kg). Perlu konfirmasi ulang detail saat implementasi.
3. **Tiga faktor penentu: kategori + diskon + entitas** (dikonfirmasi). **Mekanik diskon = bisa KEDUANYA (faktor & potong Rp & cutoff) dan KONFIGURABEL** — admin pilih metode + ambang (per-unit Rp atau %).
4. **Setuju penuh termasuk MARGIN-AWARE sekarang** (insentif dibatasi margin via HPP/landed cost). (4.b)
   → Konsekuensi: butuh resolusi HPP per line (roll cost / landed cost) saat hitung komisi → sentuh modul purchasing/inventory cost lebih dalam.
5. **Granularitas (entitas × kategori) + dikerjakan BERTAHAP**: mulai dari **engine + editor + sales dashboard** dulu; **master kategori menyusul**. (5.c)

### Catatan implementasi dari keputusan
- Karena pengakuan = collected, line_incentive harus di-pro-rata terhadap porsi pembayaran (collected/grand_total) ATAU diakui penuh saat order lunas. Perlu kebijakan partial-payment.
- Margin-aware: line_incentive_final = min(line_incentive_rate_based, margin_line × cap%?) — perlu definisi cap.
- incentive_unit konfigurabel + konversi UOM wajib (bukan fix meter).

> CATATAN: Sebelum implementasi, user meminta **AUDIT GAP UX peran (Sales vs Admin)** lebih dulu — lihat dokumen `ROLE_UX_GAP_AUDIT.md`.

