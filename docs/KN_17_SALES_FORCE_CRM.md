# KN_17 — SALES FORCE, CRM & SALES INTELLIGENCE
## Kain Nusantara Group — Customer Management + Salesperson Management Blueprint (Deep Dive)

> **Status:** DRAFT v1 — Session #015 oleh E2 (Emergent), atas arahan user. **BELUM ADA CODING.**
> **Induk:** `KN_14` (IA) · **Inventory:** `KN_15` · **Process flows:** `KN_16` · **Navigasi:** `KN_13`.
> **Scope dipilih user:** **CRM-LITE** + **Sales Force Automation (SFA)** + persiapan **Sales/Marketing Intelligence**.
> **Aturan emas:** dokumen ≠ kode → **kode menang**, lalu dokumen diperbaiki.

---

## 0. Daftar Isi
| § | Isi |
|---|---|
| 1 | Prinsip & keputusan user |
| 2 | Model Customer (CRM-lite) |
| 3 | Customer per-entitas + customer sama lintas-entitas + **assigned sales (kunci)** |
| 4 | Row-level scoping (Sales hanya kelola customer sendiri) |
| 5 | Pembayaran (kontan/tunai/tempo/DP/bertahap) + Kontrol Kredit |
| 6 | **Sales Force**: target, insentif/komisi, KPI |
| 7 | Penagihan & reminder jatuh tempo (tanggung jawab Sales) |
| 8 | **Advanced Sales & Marketing** (suggestive selling, product focus, smart search) — future-ready |
| 9 | Entitas data baru + rekonsiliasi |
| 10 | Keputusan (S28–S35) & pertanyaan terbuka |
| 11 | Changelog |

---

## 1. Prinsip & Keputusan User
- **Scope = CRM-LITE:** data customer + kontrol kredit (limit vs AR, auto-blokir overdue) + riwayat order/dokumen
  + riwayat special price + segmentasi/tag. (Full CRM pipeline/loyalty = fase lanjut.)
- **Harga = manual/nego** (BUKAN tier→price). Tier/segment hanya **klasifikasi**, bukan penentu harga.
  Harga custom via `price_approvals` (KN_16 §8B.5).
- **Customer terpisah per entitas** (`entity_id`), TAPI customer yang sama bisa ada di >1 entitas.
- **KUNCI: setiap customer DI-ASSIGN ke 1 salesperson.** Sales hanya mengelola customer miliknya.
- **Salesperson punya:** target, insentif/bonus (berbasis penjualan & pencairan), tanggung jawab reminder
  jatuh tempo, dan **KPI** (penjualan, tertagih/dicairkan, dll).
- **Advanced (future):** suggestive selling, product focus, smart search berbasis kebutuhan — **disiapkan**, engine dibangun nanti.

---

## 2. Model Customer (CRM-lite) — perluasan `customers`
```
customers (cust_)  [scoped entity_id]
  EXISTING: name, pic_name, phone, email, type, city, address, npwp, credit_limit, sales_pic, entity_id, addresses[]
  TAMBAH (CRM-lite):
  assigned_sales_id   string  FK users (salesperson pemilik) — WAJIB (kunci manajemen)
  segment             enum    Retail | Wholesale | Distributor | VIP   (KLASIFIKASI saja, bukan harga)
  tags                list    [string]  (segmentasi bebas)
  contacts            list    [{name, role, phone, email, is_primary}]  (multi-PIC)
  addresses           list    [CustomerAddress]  (sudah ada — multi-alamat)
  lot_policy          enum    prefer_single | strict_single | allow_mixed   (default prefer_single, KN_15)
  payment_profile     object  (lihat §5)
  credit              object  {credit_limit, ar_outstanding(derived), overdue_amount(derived),
                               status: active | warning | blocked}
  status              enum    active | inactive | blocked
  notes               text
  created_by, created_at, updated_at
  --- DERIVED/LINKED (bukan kolom mentah) ---
  order_history       ← dari sales_orders (customer_id)
  document_history    ← dari generated_documents
  special_price_history ← dari price_approvals (customer_id)
```
⚠️ SSOT tunggal `customers`. JANGAN buat `clients`, `crm_customers`, `buyers`.

---

## 3. Customer per-Entitas + Sama Lintas-Entitas + Assigned Sales
- `customers.entity_id` → **terpisah per entitas** (sudah di ENTITY_SCOPED_COLLECTIONS).
- Customer **sama** bisa muncul di >1 entitas (record berbeda per entitas). Untuk pandangan gabungan
  (mis. NPWP sama), opsional `customer_group_id` penghubung. *(open §10-Q3)*
- **`assigned_sales_id` = kunci kepemilikan data.** Tiap customer punya 1 sales penanggung jawab.
- **Sales boleh menambah customer sendiri** → otomatis `assigned_sales_id = pembuat` (jadi basis customer sales itu).
- **Admin/Manager lihat keseluruhan**; **Sales hanya lihat/kelola customer miliknya** (§4).
- Reassign sales (mis. sales resign) = aksi Admin/Manager (teraudit), histori tetap.

---

## 4. Row-Level Scoping (Sales hanya kelola customer sendiri)
```
Role sales    : query customers/sales_orders OTOMATIS difilter assigned_sales_id == current_user.id
Role manager  : lihat semua sales di entitasnya (+ reassign)
Role admin    : lihat semua (lintas entitas)
```
- Berlaku ke modul turunan: SO, quotation, AR, reminder, KPI → semua ter-scope ke customer milik sales.
- Ini **RBAC row-level** (perluasan permission_settings). ⚠️ Pastikan endpoint enforce di backend (bukan hanya UI).

---

## 5. Pembayaran + Kontrol Kredit
### 5.1 Payment Profile (di customer, dipakai default saat SO)
```
payment_profile {
  allowed_methods: [kontan|tunai|tempo|dp|bertahap]   (subset yang diizinkan utk customer ini)
  default_method:  enum
  term_days:       int     (untuk 'tempo' — mis. 14/30/45)
  dp_percent:      float   (untuk 'dp' — mis. 30%)
  installment:     {count, interval_days}  (untuk 'bertahap')
}
```
Metode:
- **kontan/tunai** → lunas saat transaksi (no AR).
- **tempo** → kredit, jatuh tempo = tanggal + term_days → **AR**.
- **dp** → bayar muka X% lalu sisa (term/saat ambil) → AR sisa.
- **bertahap** → cicilan terjadwal → AR multi-jatuh tempo.
> Di SO, payment terms aktual bisa override default (dalam batas allowed_methods).

### 5.2 Kontrol Kredit (auto-blokir overdue)
```
ar_outstanding  = Σ invoice belum lunas (customer)             [derived dari invoices/payments]
overdue_amount  = Σ invoice lewat jatuh tempo
status:
  active   : normal
  warning  : ar_outstanding mendekati credit_limit ATAU ada overdue ringan → SO boleh + peringatan
  blocked  : ar_outstanding ≥ credit_limit ATAU overdue > ambang → SO DIBLOKIR (perlu override Manager/Finance)
```
- Saat buat SO: sistem cek limit & overdue → izinkan / peringatkan / blokir.
- **Bypass blokir (case-by-case):** Sales ajukan permohonan override → **approval FINANCE + validasi/bukti** (alasan
  + lampiran) → bila disetujui, SO blocked boleh lanjut. Tercatat di `credit_overrides` (cro_) + audit
  (siapa/kapan/alasan/bukti). Mirip pola `price_approvals`.
- Denda keterlambatan (1–3%) = di invoices (Fase 4).

---

## 6. Sales Force: Target, Insentif/Komisi, KPI
### 6.1 `sales_targets` (starg_) — NEW
```
{id, sales_id(FK users), entity_id, period_type(month|quarter|year), period(2026-06),
 target_sales_amount, target_collection_amount?, target_new_customers?, target_focus_products?[],
 created_by, created_at}
```
### 6.2 `sales_incentives` / komisi (sinc_) — NEW
```
{id, sales_id, entity_id, period, basis(sales|collection|tiered),
 scheme {rate%, tiers:[{min_achievement%, rate%}], bonus_new_customer?, bonus_focus_product?},
 computed_base, computed_amount, status(draft|approved|paid), notes}
```
> Skema komisi (kembangkan): % dari penjualan, ATAU % dari **yang tercairkan/tertagih** (mendorong penagihan),
> ATAU **tiered** (capaian target >100% → rate lebih tinggi), + bonus customer baru / focus product,
> + clawback bila piutang macet. **DEFAULT DIPILIH USER: berbasis PENCAIRAN + TIERED capaian (S36).**

### 6.3 KPI Salesperson (DERIVED — dari sales_orders/invoices/payments/customers)
```
- total_sales (penjualan kotor periode)
- total_collected / dicairkan (pembayaran masuk / invoice lunas)
- collection_rate = collected / sales
- ar_outstanding & overdue (customer yang dikelola)
- on_time_collection_rate
- target_achievement_sales % & target_achievement_collection %
- new_customers & active_customers (churn)
- orders count, quotation→SO conversion rate, average order value
- focus_product_achievement (lihat §8)
- special_price_usage & estimasi dampak margin
- incentive_earned (proyeksi)
```
> Disajikan sebagai **Sales Dashboard** per salesperson + **leaderboard** (Manager view).

---

## 7. Penagihan & Reminder Jatuh Tempo (tanggung jawab Sales)
- Setiap invoice tempo/DP/bertahap punya **jadwal jatuh tempo** → masuk **Collection Worklist** sales pemilik customer.
- **Reminder otomatis** (notifications) H-3 / H / H+overdue ke sales (dan eskalasi ke Manager bila macet).
- Sales tandai tindak lanjut (follow-up log) → mempengaruhi KPI collection.
- Reuse koleksi `notifications` (Fase 0) + worklist view; tidak buat koleksi reminder baru kecuali perlu jejak follow-up
  (opsional `collection_followups`). *(open §10-Q4)*

---

## 8. Advanced Sales & Marketing (future-ready — DISIAPKAN, engine nanti)
> Tidak ada coding AI/engine sekarang; data hooks disiapkan agar mulus saat dibangun.
- **Suggestive selling (cross/upsell):** rekomendasi produk saat buat SO berdasarkan riwayat order customer +
  asosiasi produk (market-basket) + `products.ai_meta`. Hook: order_history + product attributes/tags.
- **Product focus / campaign:** Admin/MD tandai produk "focus" + target per sales (push). Entitas baru `campaigns`/
  `product_focus` (prefix `camp_`) *(planned, §9)*; KPI focus_product_achievement.
- **Smart search berbasis kebutuhan:** cari kain by use-case/atribut (mis. "untuk seragam, gramasi tinggi, warna gelap")
  → pakai `products.search_keywords` + `attributes` + (nanti) embedding `ai_meta`. Hook sudah disiapkan (KN_16 §8B.6).
- **Next best action / lead scoring / churn alert:** future; pakai KPI + history.

---

## 9. Entitas Data Baru + Rekonsiliasi
| Entitas | Prefix | Status | Catatan |
|---|---|---|---|
| `customers` (perluasan) | cust_ | ✅ ada → perluas | +assigned_sales_id, segment, tags, contacts, payment_profile, credit, lot_policy |
| `sales_targets` | starg_ | 🆕 PLANNED | target per sales per periode |
| `sales_incentives` | sinc_ | 🆕 PLANNED | komisi/bonus per sales per periode |
| `price_approvals` | pra_ | PLANNED (sudah ada di registry) | special price (KN_16 §8B.5) |
| `campaigns`/`product_focus` | camp_ | 🆕 PLANNED (advanced) | product focus + target |
| `collection_followups` | cfu_ | 🆕 PLANNED | jejak follow-up penagihan (DIPILIH: koleksi tersendiri, S39) |
| `credit_overrides` | cro_ | 🆕 PLANNED | bypass blokir kredit via approval Finance + bukti (S37) |
| `customer.customer_group_id` | — | 🆕 field disiapkan | penghubung customer sama lintas-entitas, default kosong (S38) |
| `customer_price_lists` | cpl_ | PLANNED — **DEPRIORITAS** | harga = manual/nego (tidak pakai tier→price) |
> KPI = DERIVED (bukan koleksi). JANGAN buat: salespersons (pakai users role=sales), crm_*, leads (fase lanjut).

---

## 10. Keputusan (S28–S35) & Pertanyaan Terbuka
```
S28 ✅ Scope = CRM-LITE (credit control + history + special price history + segmentasi/tag).
S29 ✅ Harga = manual/nego (tier = klasifikasi, BUKAN penentu harga; cpl_ deprioritas).
S30 ✅ Customer scoped per entitas; customer sama boleh lintas-entitas; KUNCI = assigned_sales_id.
S31 ✅ Sales hanya kelola customer sendiri (RBAC row-level, enforce backend).
S32 ✅ Payment methods di customer: kontan/tunai/tempo/dp/bertahap (payment_profile).
S33 ✅ Kontrol kredit: blokir/peringatan saat SO lampaui limit / overdue (override teraudit).
S34 ✅ Sales Force: target + insentif/komisi + KPI (penjualan, dicairkan, dll) + reminder jatuh tempo.
S35 ✅ Advanced (suggestive selling/product focus/smart search) = future-ready (data hooks disiapkan).

PERTANYAAN TERBUKA → ✅ TERJAWAB (Session #015):
Q1  ✅ Basis komisi = PENCAIRAN (tertagih) + TIERED capaian target (dorong penagihan). [S36]
Q2  ✅ Blokir kredit jika lewat credit_limit ATAU overdue; BYPASS case-by-case via approval FINANCE + validasi/bukti
       (credit_overrides cro_ + audit). [S37]
Q3  ✅ customer_group_id DISIAPKAN sekarang (default kosong) — penghubung customer sama lintas-entitas. [S38]
Q4  ✅ collection_followups = koleksi tersendiri (riwayat follow-up penagihan lengkap). [S39]
Q5  ✅ Reassign oleh Manager/Admin (teraudit). Sales boleh TAMBAH customer sendiri → auto jadi basis customer-nya;
       Admin lihat semua, Sales lihat miliknya. [S40]
```

---

## 11. Changelog
### v1.1 — Session #015 (Q1–Q5 RESOLVED, S36–S40)
- Komisi = pencairan + tiered (S36). Blokir kredit (limit OR overdue) + bypass via approval Finance + bukti
  (`credit_overrides` cro_) (S37). `customer_group_id` disiapkan (S38). `collection_followups` koleksi tersendiri (S39).
  Sales boleh tambah customer sendiri (auto-assigned); Manager/Admin reassign & lihat semua; Sales lihat miliknya (S40).

### v1 — Session #015
- Blueprint Sales Force/CRM-lite: customer enhanced (assigned_sales, payment_profile, credit control, segment/tags,
  contacts, history), row-level scoping, payment methods (kontan/tunai/tempo/dp/bertahap), kontrol kredit auto-blokir.
- Sales Force: sales_targets, sales_incentives/komisi, KPI (penjualan/dicairkan/collection/target/new customer/...),
  reminder jatuh tempo (collection worklist).
- Advanced Sales/Marketing future-ready (suggestive selling, product focus/campaign, smart search) + data hooks.
- Keputusan S28–S35; pertanyaan terbuka Q1–Q5.

---
*SSOT: KN_14 (IA) ⇄ KN_13 (nav) ⇄ ENTITY_REGISTRY (data) ⇄ KN_15 (inventory) ⇄ KN_16 (process) ⇄ KN_17 (sales/CRM). Code wins.*
