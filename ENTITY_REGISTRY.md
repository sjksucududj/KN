# ENTITY REGISTRY — SSOT Map
## Kain Nusantara Platform

**WAJIB DIBACA SEBELUM MEMBUAT COLLECTION, SCHEMA, ATAU ENDPOINT BARU.**

File ini adalah satu-satunya sumber kebenaran untuk semua entitas bisnis.
Sebelum membuat apapun yang baru, tanya: **"Apakah ini sudah ada di sini?"**

**Update wajib setiap kali ada:**
- Collection baru ditambahkan
- Schema baru dibuat
- Endpoint baru untuk entitas yang sudah ada
- Component baru untuk entitas yang sudah ada

---

## 📋 QUICK LOOKUP TABLE

| Entitas | Collection | Router | Schema | Frontend Component |
|---|---|---|---|---|
| User | `users` | `routers/auth.py`, `routers/users.py` | `UserCreate` | `AdminView` (tab Users) |
| Session (Auth) | `sessions` | `routers/auth.py` | — | `LoginScreen` |
| Product | `products` | `routers/products.py` | `ProductPayload` | `ProductCard`, `AdminView` (tab Product) |
| **Registry Enum Domain** *(FASE A — KODE, bukan koleksi)* | `backend/domain_registry.py` | `routers/enums.py` (`GET /api/enums*`) | — | `hooks/useDomainEnums.js`, `DomainRegistryView` (Produk & Harga → Registry Domain) |
| **Riwayat & Override Grade Roll** *(FASE A · PS-09)* | `inventory_rolls.grade_history[]` | `routers/qc_inspection.py`, `services/grade_service.py` | `RollGradeOverrideIn` | `RollGradePanel` (Gudang → Inspeksi QC → tombol Grade) |
| Customer | `customers` | `routers/customers.py` | `CustomerCreate` | `CustomerPanel`, `AdminView` (tab Customer) |
| Warehouse | `warehouses` | `routers/warehouses.py` | `WarehousePayload` | `AdminView` (tab Warehouse) |
| UOM | `uoms` | `routers/uoms.py` | `UOMPayload` | `AdminView` (tab UOM) |
| Sales Order | `sales_orders` | `routers/sales_orders.py` | `SalesOrderCreate` | `SalesPortal`, `OrdersView`, `CartPanel` |
| Invoice | `invoices` | `routers/invoices.py` | `PaymentSimulationCreate` | `DocumentsView` |
| Inventory Balance | `inventory_balances` | `routers/inventory.py` | — | `InventoryStockView` |
| Inventory Roll *(IMPLEMENTED Fase 0.5)* | `inventory_rolls` | `routers/inventory.py`, `services/roll_service.py` | `RollPayload` | `InventoryStockView`, `SalesPortal` |
| Inventory Movement | `inventory_movements` | `routers/inventory.py` | — | `InventoryStockView` (tab Ledger) |
| WMS Task | `wms_tasks` | `routers/wms.py` | `WMSTaskCreate` | `ScannerTaskPanel` |
| Inbound Task | `wms_tasks` *(flow_type=inbound)* | `routers/inbound_receiving.py` | — | `InboundScanInterface` |
| Outbound Task | `wms_tasks` *(flow_type=outbound)* | `routers/outbound_picking.py` | — | `OutboundScanInterface` |
| Transfer | `warehouse_transfers` | `routers/transfers.py` | `TransferCreate` | `TransferManagement` |
| Cycle Count | `cycle_count_sessions` | `routers/cycle_count.py` | — | `CycleCount` |
| Purchase Order | `purchase_orders` | `routers/purchase_orders.py` | `PurchaseOrderCreate` | `PurchaseOrderManagement` |
| Makloon (Subkontraktor) | `makloons` | `routers/makloons.py` | `MakloonCreate` | `MakloonsView`, `Makloon360Panel` (Pembelian → Master Pembelian) |
| Resep Proses (Konversi) | `process_recipes` | `routers/process_recipes.py` | `ProcessRecipeCreate` | `ProcessRecipesView` (Pembelian → Master Pembelian) |
| Order Makloon (Subkontrak) | `makloon_orders` | `routers/makloon_orders.py`, `services/makloon_order_service.py` | — | `MakloonOrdersView`, `MakloonOrderCreateModal` (Pembelian → PO → tab Order Makloon) |
| Document Template | `document_templates` | `routers/documents.py` | `TemplatePayload` | `DocumentsView`, `AdminView` (tab Templates) |
| Generated Document | `generated_documents` | `routers/documents.py` | `DocumentGenerate` | `DocumentsView` |
| Permission Settings | `permission_settings` | `routers/admin.py` | `PermissionUpdate` | `AdminView` (tab Permissions) |
| Audit Log | `audit_logs` | `routers/audit.py` | — | `AdminView` (tab Audit) |
| Onboarding | `user_onboarding` | `routers/onboarding.py` | — | `OnboardingPanel` |
| KPI Design *(FASE H5)* | `hr_kpi` | `routers/hr_kpi.py` | `KpiInput`, `KpiUpdate` | `KpiView`, `MyKpiCard` (ESS) |
| Design Gallery *(FASE H5)* | `design_gallery` | `routers/design_gallery.py` | `GalleryInput`, `GalleryUpdate` | `DesignGalleryView` |
| AI Integrations *(FASE H5)* | `system_settings` *(scope=integrations)* | `routers/integrations.py` | `IntegrationsUpdate` | `IntegrationsPanel` (AdminView tab Integrasi AI) |
| Kontrabon *(FASE G-7)* | `contra_bons` | `routers/contra_bons.py`, `services/contra_bon_service.py`, `services/contra_bon_reminder.py` | `ContraBonCreate`, `ContraBonDeductionIn`, `ContraBonDecisionIn`, `ContraBonScheduleIn`, `ContraBonPayIn`, `InvoiceExchangeIn` | `ContraBonsView` (Pembelian → Hutang Supplier (AP) → Kontrabon) |
| Transaksi Antar Entitas *(FASE G-6)* | `interco_transactions`, `interco_accounts`, `interco_settlements` | `routers/interco.py`, `services/interco_service.py`, `services/consolidation_service.py` (eliminasi margin) | `IntercoCreate`, `IntercoActionIn`, `IntercoSettlementCreate` | `IntercoView` (Pembelian → Hutang Supplier (AP) → Antar Entitas (Jual-Beli)) · `GroupConsolidationView` (eliminasi AUTO G-6) |
| Finance Case *(FASE G-9)* | `finance_cases` | `routers/finance_cases.py`, `services/finance_case_service.py` | `CaseCreate`, `CaseResolveInput`, `CaseRejectInput` | `FinanceCasesView` (Keuangan → Pusat Kasus Keuangan) |
| Bank Statement Line *(R6.1)* | `bank_statement_lines` | `routers/bank_reconciliation.py`, `services/bank_recon_service.py` | — | `BankReconciliationView` (Keuangan → Rekonsiliasi Bank) |
| Fixed Asset *(R6.2)* | `fin_fixed_assets` | `routers/fixed_assets.py`, `services/fixed_asset_service.py` | `FixedAssetIn/Patch` | `FixedAssetsView` (Kas & Aset → Aset Tetap) |
| Depreciation Entry *(R6.2)* | `fin_depreciation_entries` | `routers/fixed_assets.py`, `services/fixed_asset_service.py` | — | `FixedAssetsView` (histori penyusutan) |
| Budget *(P1-4 / R6.3)* | `budgets` | `routers/budgets.py`, `services/budget_service.py` | `BudgetCreate/Update` | `BudgetView` (Keuangan → Laporan & Analitik → Anggaran vs Realisasi) |
| Budget Rule *(R6.3)* | `fin_budget_rules` | `routers/budgets.py`, `services/budget_service.py` | `BudgetRulesIn` | `BudgetView` (panel Kebijakan Anggaran) |
| BOM / Resep Produksi *(R6.4)* | `mfg_boms` | `routers/production.py`, `services/production_service.py` | `BomIn/BomPatch` | `ProductionView` (Gudang → Produksi (BOM & WO) → tab BOM/Resep) |
| Work Order *(R6.4)* | `mfg_work_orders` | `routers/production.py`, `services/production_service.py` | `WorkOrderIn` | `ProductionView` + `ProductionWO` (tab Work Order) |
| Histori Job Scheduler *(R6.5)* | `sys_scheduler_runs` | `routers/scheduler.py`, `services/scheduler_service.py` | — | `SchedulerView` (Pengaturan → Penjadwal & Notifikasi → tab Riwayat Eksekusi) |
| Outbox WhatsApp *(R6.5)* | `sys_wa_outbox` | `routers/scheduler.py`, `services/wa_alert_service.py` | `WaTestRequest` | `SchedulerWa` (tab WhatsApp → Outbox) |
| Pengaturan Alert *(R6.5)* | `system_settings` *(scope=alerts)* | `routers/scheduler.py`, `services/wa_alert_service.py` | `SchedulerSettingsUpdate` | `SchedulerWa` + `JobTable` (editor jadwal inline) |

---

## 🗂️ DETAIL ENTITAS

### users
```
Collection:  users
Routers:     routers/auth.py (login, me, logout)
             routers/users.py (CRUD)
Schema:      schemas.py → UserCreate, UserResponse
Component:   AdminView.jsx (tab Users), LoginScreen (CoreWidgets.jsx)
Key Fields:
  id          string   prefix "user_"
  name        string
  email       string   UNIQUE
  role        enum     admin | sales | manager | warehouse
  password_hash string  SHA256 hash (kain-nusantara::password)
  status      enum     active | inactive
  allowed_line_codes list  [FASE L] lini produk yang boleh dikerjakan akun ini
                           (mis. ["printing"]). **KOSONG = SEMUA LINI** — itu
                           bawaannya, supaya akun lama tidak kehilangan apa pun.
                           Divalidasi ke master `product_lines` (services/line_scope.py);
                           mengubahnya MENCABUT sesi (hak baca berubah).
  created_at  string   ISO 8601 UTC

⚠️ JANGAN BUAT: staff, karyawan, operator, employee (untuk user system)
⚠️ Auth: Bearer token via Authorization header (BUKAN cookie)
⚠️ Password: hash_password() dari core_utils.py — jangan pake bcrypt
```

### sessions
```
Collection:  sessions
Router:      routers/auth.py (auto-managed)
Key Fields:
  token       string   format: "sess_[hex12]"
  user_id     string   FK → users.id
  created_at  string

⚠️ JANGAN query sessions langsung dari router lain
⚠️ Gunakan current_user() dari dependencies.py
```

### products
```
Collection:  products
Router:      routers/products.py
Schema:      schemas.py → ProductPayload
Component:   ProductCard.jsx, AdminView.jsx (tab Product), SalesPortal.jsx
Key Fields:
  id          string   prefix "prod_"
  sku         string   UNIQUE — format: CAT-MOTIF-NNN (e.g. BTK-MEGA-001)
  name        string
  category    enum     Batik | Tenun | Lurik | Songket | Ulos | Jumputan | Endek
  variant     string
  color       string
  motif       string
  grade       enum     [FASE A · D-01] A | A1 | A2 | B | BS   (rank 1..5; BS = barang sortir)
                       ⚠️ A+ / C DIPENSIUNKAN → dimigrasi (A+→A, C→BS) oleh
                       backend/scripts/migrate_fase_a_domain.py; nilai asli disimpan di grade_legacy
  grade_legacy string?  [FASE A] nilai grade lama sebelum normalisasi (audit migrasi)
  stage       enum     [FASE A · PS-01] yarn | grey | pfd | pfp | finished | remnant | byproduct
                       (transisi dikunci server — GET /api/enums/stage-transitions)
  fabric_type enum     [FASE A · PS-02/D-02] woven | knit  — WAJIB sejak stage yarn
  line_code   string   [FASE L] LINI PRODUK = pembagian kerja MD (woven|knit|printing|…,
                       bisa ditambah pemilik di master `product_lines`). **BUKAN**
                       pengganti `fabric_type`: lini = siapa yang mengerjakan & papan
                       mana; `fabric_type` = fisika kain (SSOT rumus & satuan kendali).
                       Kosong = belum bergolong lini → TETAP terlihat semua akun.
                       Dijaga INV-LINE-01/02 (scripts/guardrails/verify_line_scope.py).
  fabric_type_migrated bool?  [FASE A · D-20] true bila diisi otomatis oleh migrasi (default woven)
  yarn_count        string?  [FASE A · D-22] nomor benang (WAJIB bila stage=yarn & woven), mis. "30s"
  yarn_count_system enum?    [FASE A · D-22] Ne | Nm | Denier | Tex
  needs_review      bool     [FASE A · D-22] true bila kelengkapan domain kurang (GSM/lebar/yarn_count)
  needs_review_reasons list   field yang disarankan tapi belum terisi (turunan validasi)
  domain_gaps       list      pesan kelengkapan WAJIB yang belum terpenuhi (turunan validasi migrasi)
  gramasi     float    GSM (gram/m²) — WAJIB stage ≥ grey untuk woven (PS-03/D-22)
  lebar       float    lebar kain (meter) — WAJIB stage ≥ grey untuk woven (PS-03)
  supplier    string   (string only saat ini, bukan FK)
  base_unit   string   meter | yard | roll | pcs
  price       float    IDR per base_unit
  image       string   URL
  status      enum     active | inactive
  uom_conversions  list  [{from_unit, to_unit, factor}]
  batch_lot_rolls  list  [{batch, lot, roll_id}]
  --- METADATA SMART-SEARCH / AI-READY [PROPOSED KN_16 §8B.6] (disiapkan, diisi bertahap) ---
  description      text   deskripsi panjang (marketing/search)
  specifications   object {komposisi, lebar_cm, gramasi, perawatan, asal, ...} (key-value terstruktur)
  tags             list   [string]
  media            list   [{type: image|video, url}]  (multi-media; image lama tetap kompat)
  search_keywords  list   [string]  (untuk smart search)
  attributes       object {} facet/filter terstruktur
  ai_meta          object { embedding: [], recommender_tags: [], updated_at }  (KOSONG dulu — engine nanti)
  created_at  string
  updated_at  string

⚠️ SSOT TUNGGAL: Sales-view & Inventory-view = PROYEKSI dari products yang sama, BUKAN tabel terpisah
   (mis. GET /products?view=sales vs ?view=inventory). Cegah data ganda/konflik.
⚠️ JANGAN BUAT: items, goods, materials, kain, fabric, accessories, products_sales, products_inventory
⚠️ Stok ADA DI inventory_balances/inventory_rolls, BUKAN di products
```

### product_categories  [EPIC2 IMPLEMENTED — Master Kategori Produk]
```
Collection:  product_categories         Prefix: cat_
Router:      routers/categories.py
Schema:      routers/categories.py → CategoryPayload (inline)
Component:   features/admin/CategoryManager.jsx, AdminView.jsx (tab Kategori + dropdown form produk)
Key Fields:
  id            string   prefix "cat_"
  code          string   UNIQUE — uppercase slug (mis. BATIK)
  name          string   UNIQUE — nama kategori (mis. Batik) = nilai products.category
  base_unit     string   default UOM kategori (meter|yard|kg|roll|pcs) → default produk baru
  description   string
  sort_order    int      urutan tampil
  status        enum     active | inactive
  product_count int      DERIVED (count products by name) — tidak disimpan
  created_at    string
  updated_at    string

ℹ️ SSOT nama kategori. products.category menyimpan NAME (string), bukan id → kompat data historis.
ℹ️ Rename kategori mem-propagasi ke products.category (jaga konsistensi).
ℹ️ SO line meng-snapshot `category` (+base_unit, base_quantity) saat create; backfill historis idempotent.
⚠️ JANGAN BUAT: categories, product_category, kategori, product_groups
```

### color_library  [M0 IMPLEMENTED — Master Warna Pantone-style]
```
Collection:  color_library              Prefix: col_
Scope:       SHARED (tak di-scope entitas, mirip products/uoms)
Router:      routers/color_library.py
Service:     services/color_service.py
Schema:      schemas.py → ColorCreate, ColorPatch
Component:   features/sales/ColorLibraryView.jsx, components/PantoneFinder.jsx
Key Fields:
  id          string   prefix "col_"
  code        string   UNIQUE — kode warna (mis. KN-BLU-01, TCX-19-4052)
  name        string   nama warna (mis. Biru Indigo)
  hex         string   "#RRGGBB" (uppercase)
  system      enum     TPX | TCX | C | U | KN (default KN)
  family      string   kelompok warna (Biru/Merah/…)
  status      enum     active | inactive (delete = soft/nonaktif)
  created_by  string
  created_at  string
  updated_at  string

ℹ️ Master warna dipakai lintas menu (Master Produk, Template Varian, POS, Makloon).
ℹ️ Produk meng-snapshot warna: products.color_code / color_name / color_hex (fallback teks `color`).
ℹ️ Endpoint /api/color-library/nearest?hex= → cari warna terdekat (ΔE redmean).
⚠️ JANGAN BUAT: colors, warna, pantone, color_master
```

### makloons  [M1 IMPLEMENTED — Master Mitra Makloon/Subkontraktor]
```
Collection:  makloons                    Prefix: mak_
Scope:       SCOPED (entity_id) — mirror suppliers
Router:      routers/makloons.py
Service:     services/makloon_service.py (makloon_360, compute_makloon_scorecard)
Schema:      schemas_makloon.py → MakloonCreate (+ GenericPatch untuk update)
Component:   features/purchasing/MakloonsView.jsx, Makloon360Panel.jsx, MakloonFormModal.jsx, components/MakloonSelect.jsx
Key Fields:
  id, code (MAK-NNNNN), name, npwp, pic_name, phone, email, address, city,
  process_types [tenun|celup|finishing|printing|lainnya], capacity_note,
  capacity_per_month, capacity_unit, default_tariff, tariff_unit [output|input|roll],
  payment_term_code, lead_time_days, entity_id, notes, status, created_*
Endpoints:   GET/POST /makloons · GET /makloons/{id} (360) · PATCH/DELETE /makloons/{id} · GET /makloons/{id}/scorecard
⚠️ JANGAN BUAT: makloon, subcontractors, vendors_makloon, toll_manufacturers
```

### process_recipes  [M1 IMPLEMENTED — Resep Konversi Proses]
```
Collection:  process_recipes             Prefix: prcp_
Scope:       SCOPED (entity_id)
Router:      routers/process_recipes.py
Service:     services/process_recipe_service.py (compute_forecast + safe formula eval)
Schema:      schemas_makloon.py → ProcessRecipeCreate, ForecastPreviewIn (+ GenericPatch)
Component:   features/purchasing/ProcessRecipesView.jsx, RecipeFormModal.jsx
Key Fields:
  id, name, process_type, input_product_id, input_stage, output_product_id, output_stage,
  yield_factor, waste_pct, byproduct_pct, byproduct_product_id,
  default_makloon_id, default_tariff, tariff_unit, aux_cost_default,
  formula (ekspresi bebas opsional; var: input_qty/gramasi/lebar/yield_factor/waste_pct/byproduct_pct),
  entity_id, status, created_*
Endpoints:   GET/POST /process-recipes · PATCH/DELETE /process-recipes/{id} · POST /process-recipes/forecast
⚠️ JANGAN BUAT: recipes, konversi, bom_makloon, process_bom
```

### makloon_orders  [M3 IMPLEMENTED — Transaksi Makloon/Subkontrak (Procure→Process→Pay)]
```
Collection:  makloon_orders             Prefix: mko_   (number: MKO-#####)
Scope:       SCOPED (entity_id)
Router:      routers/makloon_orders.py
Service:     services/makloon_order_service.py (create/issue/receive/cancel + costing)
Schema:      schemas_makloon.py → MakloonOrderCreate, MakloonStepInput, MakloonIssueIn,
             MakloonReceiveIn, MakloonReceiveRoll, MakloonOrderCancel
Component:   features/purchasing/MakloonOrdersView.jsx, MakloonOrderCreateModal.jsx,
             MakloonOrderDetailPanel.jsx
Key Fields:
  id, mko_number, entity_id, mode (process_only|buy_process),
  material_product_id/sku/name/qty/unit, material_source (stock|purchase),
  from_warehouse_id, target_warehouse_id, po_id, po_number,
  final_output_product_id, steps[] (seq, process_type, makloon_id, recipe_id,
    input_product_id, input_qty, output_product_id, expected_output_qty,
    actual_output_qty, expected_byproduct_qty, actual_byproduct_qty, byproduct_product_id,
    tariff, aux_cost, service_bill_id, issue_ref, material_value, service_value, output_value,
    output_unit_cost, status(pending|issued|received|cancelled), issued_at, received_at, lots[]),
  forecast{}, costing{material_cost, service_cost, aux_cost, byproduct_credit, hpp_output, hpp_per_unit},
  status(draft|in_process|partially_received|completed|cancelled), timeline[], created_*
FASE D (additive · D-04/D-05/D-07/D-09) pada steps[]:
    contract_id, contract_number, tariff_basis, tariff_rate,
    tariff_plan{} (rencana saat create) · tariff_actual{source, basis, basis_qty, rate,
      amount, explain[], conversion{}} (aktual saat receive · INV-MKO-03),
    shrinkage_pct, shrinkage_source (input langkah|kontrak <no>|resep proses|kebijakan global),
    tolerance_pct, estimate{method(gsm|yield|formula|unknown), expected_output_qty,
      expected_byproduct_qty, explain[]},
    issue_uom_trail{}, receive_uom_trail{} (doc→base · D-04),
    variance{variance_qty, variance_pct, tolerance_pct, shortfall_qty, shortfall_value,
      unit, unit_value, claim_required, message},
    claim{status(none|open|pending_approval|approved|rejected), required, action
      (potong_bon|tagih_ganti|terima_catatan), amount, amount_suggested, reason, history[],
      proposed_by/at, approved_by/at, approval_note, rejected_by/at/reason, effect{}},
    input_lot_ids[], output_lot_ids[], output_lot_id
  order-level: order_warnings[] (mode kontrak `warn`),
    claim_summary{open, pending_approval, approved, rejected, approved_amount, needs_action}
GL:          Dr 1-1350 WIP/Cr 1-1300 (issue) · Dr 1-1350+PPN/Cr 2-1100 (service via vendor_bills
             bill_type=makloon_service) · Dr 1-1300/Cr 1-1350 (receive). WIP net 0 per siklus.
             KLAIM (D-09): potong_bon Dr 2-1100/Cr 4-9200 (+vendor_bill dipotong) ·
             tagih_ganti Dr 1-1260/Cr 4-9200 · terima_catatan TANPA jurnal (kerugian sudah
             terserap ke HPP output saat receive).
Stock:       roll status 'subcon' (WIP-at-vendor, owned non-ATP) → 'consumed' saat receive;
             output+barang sisa (is_remnant) jadi roll 'available' dgn LOT manual per roll.
Endpoints:   GET/POST /makloon-orders · GET /makloon-orders/{id} ·
             POST /makloon-orders/{id}/issue|receive|cancel ·
             POST /makloon-orders/estimate (pratinjau wizard) ·
             GET /makloon-orders/claims · GET /makloon-orders/claims/stats ·
             POST /makloon-orders/{id}/claim|claim/approve|claim/reject
Invariants:  INV-MKO-01..06 (verify_data_integrity blok L4-MKO)
Docs:        docs/KN_24_PLAN_FASE_D_MAKLOON.md
⚠️ JANGAN BUAT: subcon_orders, toll_orders, maklon_orders, work_orders, makloon_claims
```

### supplier_contracts  [FASE D IMPLEMENTED — Kontrak Mitra Makloon & Supplier]
```
Collection:  supplier_contracts          Prefix: sct_   (number: <ENT>/SCT-#####)
Scope:       SCOPED (entity_id)
Router:      routers/supplier_contracts.py
Service:     services/contract_service.py (kebijakan + CRUD + resolve_active + compute_tariff
             + tariff_preview + stats + mark_used)
Schema:      schemas_contracts.py → SupplierContractCreate, SupplierContractPatch,
             ContractStatusIn, ContractAuxFee, TariffPreviewIn, ContractResolveIn
Component:   features/purchasing/contracts/ContractsView.jsx, ContractFormModal.jsx,
             MakloonPolicyModal.jsx
             (Pembelian → Master Pembelian → tab "Kontrak Mitra & Supplier")
Key Fields:
  id, contract_number, entity_id, contract_type (makloon|purchase),
  partner_kind, partner_id, partner_name, title,
  process_type (WAJIB bila makloon; enum registry process_type),
  product_id/sku/name, input_product_id,
  tariff_basis (pick|kg|meter|yard|ball|cone|roll|lot|lumpsum|custom · D-07),
  tariff_rate, tariff_formula (safe-eval AST), tariff_qty_source (output|input), ppi,
  aux_fees[{code,label,basis(lumpsum|per_roll|per_color|per_repeat|per_kg|per_meter|
    per_output_unit),amount}], min_charge, currency,
  shrinkage_pct (D-05), tolerance_pct (nullable → kebijakan · D-09), yield_factor, byproduct_pct,
  moq, lead_time_days, payment_term_code, valid_from, valid_to,
  status (draft|active|expired|terminated), sample_ref, notes,
  usage_count (>0 ⇒ DELETE 409), created_at/by, updated_at/by
Policy:      system_settings scope `makloon` → variance_tolerance_pct, default_shrinkage_pct,
             contract_mode (off|warn|block), auto_claim, claim_approval_roles[],
             require_output_product, require_yield_reason  (configurable TANPA deploy)
Endpoints:   GET/POST /supplier-contracts · GET /supplier-contracts/stats ·
             GET/PUT /supplier-contracts/policy · POST /supplier-contracts/resolve ·
             POST /supplier-contracts/tariff-preview · GET /supplier-contracts/{id} ·
             PATCH /supplier-contracts/{id} · POST /supplier-contracts/{id}/status ·
             DELETE /supplier-contracts/{id} (409 bila terpakai) ·
             GET /makloon-partners/scorecard
RBAC:        permission resource `supplier_contract` (admin/manager CRUD · warehouse view ·
             sales TIDAK punya akses — data komersial)
Indexes:     indexes.py → (entity_id, contract_type, status), (partner_id, process_type, status),
             contract_number unik
Invariant:   INV-MKO-06 (steps[].contract_id valid & bernomor sah)
Docs:        docs/KN_24_PLAN_FASE_D_MAKLOON.md
ℹ️ contract_type=`purchase` dipakai **Fase E** (routing PR/PO berbasis kontrak): `tariff_basis`
   = satuan harga, `tariff_rate` = harga per satuan itu, `moq` = MOQ kontrak.
⚠️ JANGAN BUAT: contracts, makloon_contracts, purchase_contracts, tariffs, price_contracts
```

### supplier_items  [FASE E IMPLEMENTED — Barang Supplier (katalog versi supplier)]
```
Collection:  supplier_items              Prefix: sit_
Scope:       SCOPED (entity_id)
Router:      routers/supplier_items.py
Service:     services/supplier_item_service.py (CRUD + lookup + resolve_for_product
             + validate_rows/import_rows + csv_template + mark_used)
Schema:      schemas_supplier_items.py → SupplierItemCreate, SupplierItemPatch,
             SupplierItemImportRow, SupplierItemImportIn
Component:   features/purchasing/supplier-items/SupplierItemsView.jsx,
             SupplierItemFormModal.jsx, SupplierItemImportModal.jsx
             (Pembelian → Master Pembelian → tab "Barang Supplier")
Masalah yang diselesaikan:
  Supplier menyebut barang dengan KODE & NAMA sendiri (mis. `TX-COT-30S` "Cotton Combed 30s
  Cone 1,89kg") sementara KN memakai SKU sendiri (`BNG-KTN-001`). Tanpa peta ini, tim
  purchasing menerjemahkan manual saat buat PO & saat terima barang → salah barang/satuan/harga.
Key Fields:
  id, entity_id, supplier_id, supplier_name,
  product_id, sku, product_name, base_unit            (sisi KN)
  supplier_sku          KODE barang versi supplier — WAJIB (kunci logis)
  supplier_item_name    NAMA barang versi supplier
  supplier_uom          satuan supplier ("" = sama dengan base_unit produk)
  conv_factor           1 supplier_uom = conv_factor × base_unit  (> 0 · E-03)
  last_price, currency, moq, lead_time_days, expected_grade, barcode, notes,
  status (active|inactive), usage_count (>0 ⇒ DELETE 409),
  created_at/by, updated_at/by, last_used_at
🔑 KUNCI LOGIS UNIK: (supplier_id, supplier_sku) → impor **idempotent** (upsert · E-02)
Endpoints:   GET/POST /supplier-items · GET /supplier-items/stats ·
             GET /supplier-items/lookup?supplier_sku=&supplier_id=  (cari barang KN dari kode supplier) ·
             GET /supplier-items/import-template  (unduh template CSV) ·
             POST /supplier-items/import          (JSON: rows[] atau csv_text · dry_run) ·
             POST /supplier-items/import-file     (multipart CSV/XLSX · dry_run) ·
             GET/PATCH/DELETE /supplier-items/{id}
Impor:       kolom dikenali + alias Indonesia (kode_supplier, nama_barang_supplier, satuan_supplier,
             faktor_konversi, harga, …). Pemisah CSV auto-deteksi `,` atau `;`.
             `dry_run=true` → pratinjau (will_create/will_update + errors[] per baris).
RBAC:        resource `supplier_item` — admin/manager: view/create/update/delete/**import** ·
             warehouse: view · sales: TIDAK punya akses
Indexes:     indexes.py → (supplier_id, supplier_sku), (entity_id, created_at),
             (supplier_id, product_id, status), (product_id), (supplier_sku), (barcode)
Invariant:   INV-SRC-05 (kunci unik, referensi & faktor konversi valid, referensi PO hidup)
Docs:        docs/KN_25_PLAN_FASE_E_SOURCING_CONTRACTS.md
⚠️ JANGAN BUAT: supplier_products, supplier_skus, vendor_items, item_supplier_map, supplier_catalog
```

### purchase_requisitions  [FASE E EXTENDED — routing pemenuhan per baris + realisasi]
```
Collection:  purchase_requisitions       Prefix: pr_   (number: PR-#####)
Router:      routers/purchase_requisitions.py
Service:     services/purchase_requisition_service.py (CRUD/approval/reorder) +
             services/pr_sourcing_service.py (FASE E: routing & realisasi)
FASE E — field additive:
  items[].line_no             nomor baris 1-based (unik per PR)
  items[].fulfillment_mode    purchase | makloon   (default `purchase`, backward-compatible)
  items[].realized_qty        akumulasi qty yang sudah direalisasi
  items[].realizations[]      [{type(purchase_order|makloon_order), ref_id, ref_number, qty, at, by}]
  realization{}               TURUNAN: realization_status, realized_lines, total_lines,
                              realized_qty, total_qty, realized_pct, purchase_lines, makloon_lines
  realization_status          open | partially_realized | realized  (turunan · INV-SRC-03)
  po_ids[], makloon_order_ids[], timeline[]
Endpoints (FASE E):
  GET  /purchase-requisitions/{id}/sourcing          ringkasan realisasi + aksi per baris
  POST /purchase-requisitions/{id}/realize-po        realisasi baris `purchase` (boleh sebagian)
  GET  /purchase-requisitions/{id}/makloon-prefill?line_no=N   payload Wizard Makloon ter-prefill
  POST /purchase-requisitions/{id}/realize-makloon   realisasi 1 baris `makloon` → Order Makloon
ℹ️ `POST /{id}/convert-to-po` (lama) kini **mendelegasi** ke `realize_to_po` — perilaku lama tetap
   bila semua baris ber-mode `purchase`. PR jadi `converted` HANYA bila semua baris penuh.
ℹ️ PO hasil realisasi membawa jejak sourcing per baris: `contract_id`/`contract_number`,
   `supplier_item_id`/`supplier_sku`/`supplier_item_name`, `price_source`, `sourcing_explain[]`,
   `pr_line_no`; order-level `source_pr_line_nos[]`, `contract_ids[]`.
ℹ️ [FASE F-1] Baris PO (manual **dan** hasil realisasi PR) juga membawa `supplier_uom` +
   `supplier_conv_factor` — diteruskan ke `wms_tasks` agar penerimaan bisa menerima qty dalam
   SATUAN SUPPLIER. `_create_po_core` me-resolve `supplier_items` per (supplier × produk).
Invariants:  INV-SRC-01..04
⚠️ JANGAN BUAT: requisitions, pr_lines, pr_realizations, purchase_requests
```

### ar_receipts  [EPIC3B IMPLEMENTED — AR Receipt / Payment Application]
```
Collection:  ar_receipts                Prefix: arc_   (number: AR-#####)
Router:      routers/ar_receipts.py
Service:     services/ar_receipt_service.py
Component:   features/crm/CollectionWorklist.jsx (modal Catat Pembayaran) + ARReceiptsList
Key Fields:
  id              string   prefix "arc_"
  number          string   UNIQUE — AR-00001 (next_doc_number, deletion-safe)
  customer_id     string   FK customers.id
  customer_name   string   snapshot
  entity_id       string   FK entities.id
  receipt_date    string   ISO
  method          enum     transfer | cash | giro | qris | ...
  amount          float    nominal diterima
  applied_total   float    total ter-alokasi ke order
  unapplied_amount float   sisa (amount - applied_total)
  allocations     array    [{order_id, order_number, applied, outstanding_after, payment_status}]
  notes           string
  status          enum     posted | void
  created_by / created_by_name / created_at / updated_at

ℹ️ EFEK SAMPING: meng-apply ke sales_orders.payments[] (+paid_total, +payment_status).
   payment_status: unpaid | partial | paid. Credit gate & Collection Worklist membaca payments[] → auto-update.
ℹ️ Alokasi eksplisit (allocations) atau auto-FIFO (order terbuka tertua) bila kosong.
ℹ️ SSOT outstanding = grand_total − Σ payments[].amount (lihat customer_service._order_paid).
⚠️ JANGAN BUAT: payments, receipts, ar_payments, collections (sebagai koleksi).
```

### incentive_rates  [EPIC4 IMPLEMENTED — Incentive Engine v2 rate matrix]
```
Collection:  incentive_rates             Prefix: irate_
Router:      routers/incentive_rates.py
Service:     services/sales_force_service.py (_compute_commission_per_sku)
Component:   features/crm/IncentiveRatesEditor.jsx (matrix entity×category)
Key Fields:
  id                      string  prefix "irate_"
  entity_id               string  FK entities.id | "all" (fallback semua entitas)
  category                string  = products.category / SO line snapshot
  incentive_unit          string  UOM dasar per_unit_amount (default meter)
  per_unit_amount         float   Rp per incentive_unit
  discount_threshold_type enum    pct | rp_per_unit  (basis ambang diskon line)
  discount_threshold      float   ambang diskon (>= → mekanik aktif)
  discount_mechanic       enum    tier_factor | potong_rp | cutoff
  discount_factor         float   tier_factor: komisi × faktor bila diskon > ambang
  discount_potong_rp      float   potong_rp: kurangi per_unit_amount (Rp/unit)
  margin_cap_pct          float   komisi/line ≤ X% margin line (margin-aware, WAC EPIC3)
  status                  enum    active | inactive
  created_at / updated_at

ℹ️ UNIK per (entity_id, category). Lookup engine: entity spesifik → fallback "all".
ℹ️ Mode strategi di system_settings.commission.strategy (per_sku default | achievement_tiered arsip).
ℹ️ Engine on-collection: iterasi line terbayar (pro-rata partial payment), cap by margin.
⚠️ JANGAN BUAT: incentive_rate, commission_rates, rates, sku_rates (sebagai koleksi).
```

### bank_accounts  [EPIC7-B IMPLEMENTED — Kas & Bank multi-akun + rekonsiliasi]
Koleksi kanonik `bank_accounts` (prefix `bank_`). Master akun kas/bank; mutasi tetap
di `cash_transactions` (SSOT kas) dgn field opsional `account_id`.
```
Collection:  bank_accounts                Prefix: bank_
Router:      routers/bank.py
Service:     services/bank_service.py
Component:   features/finance/BankAccountsView.jsx
Key Fields:
  id                string  prefix "bank_"
  name              string  nama tampilan akun
  account_type      enum    bank | cash
  bank_name         string  nama bank (kosong utk cash)
  account_number    string  no rekening
  entity_id         string  FK entities.id | "all"
  opening_balance   float   saldo awal
  currency          string  default IDR
  is_active         bool
  created_at / updated_at

Saldo akun (derived) = opening_balance + Σ(in) − Σ(out) cash_transactions
  posted (status≠void) dengan account_id = akun tsb.
Rekonsiliasi: cash_transactions.reconciled (bool) + reconciled_at.
ℹ️ Endpoint: GET /api/bank-accounts, POST /api/bank-accounts,
  PATCH /api/bank-accounts/{id}, GET /api/bank-accounts/{id}/ledger,
  POST /api/cash-transactions/{id}/reconcile. RBAC: permission "cash" (admin/manager).
⚠️ JANGAN BUAT: bank, banks, accounts, rekening (sebagai koleksi).
```

### bank_statement_lines  [R6.1 IMPLEMENTED — Bank Reconciliation otomatis]
Koleksi baru `bank_statement_lines` (prefix `stmtline_`, batch `stmtbatch_`). Mutasi
rekening koran yang diimpor untuk direkonsiliasi terhadap `cash_transactions` (SSOT kas).
**GL-SAFE**: rekonsiliasi TIDAK mengubah jurnal terposting — hanya MENAUTKAN
statement line ↔ cash_transaction + menandai `reconciled`.
```
Collection:  bank_statement_lines        Prefix: stmtline_ (import_batch: stmtbatch_)
Router:      routers/bank_reconciliation.py
Service:     services/bank_recon_service.py
Component:   features/finance/BankReconciliationView.jsx (Keuangan → Rekonsiliasi Bank)
Key Fields:
  id                string  prefix "stmtline_"
  bank_account_id   string  FK bank_accounts.id
  entity_id         string  FK business_entities.id
  stmt_date         string  YYYY-MM-DD (tanggal mutasi)
  amount            float   >0 (nilai absolut)
  direction         enum    in | out
  description       string  keterangan mutasi
  ref               string  referensi (no. dok/invoice) utk heuristik match
  external_id       string  id unik dari bank (dedupe kuat bila tersedia)
  status            enum    unmatched | matched | ignored | holding   (holding = FASE G-8)
  matched_txn_id    string  FK cash_transactions.id (bila matched 1:1)
  matched_txn_ids[] string  FASE G-8 — daftar transaksi tertaut (split 1:N / gabung N:1)
  allocations[]     object  FASE G-8 — {txn_id, amount} Σ == amount baris (INV-BNK-01)
  match_kind        enum    FASE G-8 — 1:1 | 1:N | N:1
  score             float   FASE G-8 — skor berbobot pencocokan (0..100+)
  score_explain[]   object  FASE G-8 — {label, points} alasan skor yang dibaca manusia
  suggestions[]     object  FASE G-8 — usulan berperingkat (pita 60..79) belum ditautkan
  counterparty      string  FASE G-8 — nama pihak hasil tebakan parser
  desc_key          string  FASE G-8 — sidik jari berita transfer (untuk aturan belajar)
  holding           object  FASE G-8 — {cash_txn_id, cash_number, je_id, je_number, at, by, note}
  holding_allocated[] object FASE G-8 — {order_id, amount, je_id, reason_code, by, at}
  holding_remaining float   FASE G-8 — sisa titipan belum dialokasikan (INV-BNK-03)
  format_id         string  FASE G-8 — FK bank_statement_formats.id (template pembaca)
  match_type        enum    auto | manual
  matched_at / matched_by / import_batch / created_at / updated_at
Auto-match:  1:1 line↔txn (akun sama, arah sama, |Δamount| ≤ toleransi,
             |Δtanggal| ≤ window hari; prioritas ref cocok lalu tanggal terdekat).
             Idempotent: hanya proses line unmatched & txn reconciled≠true.
Efek match:  cash_transactions.reconciled=true, reconciled_at, matched_line_id.
             Unmatch membalik ketiga field tsb (append-only; GL tak berubah).
Endpoints:   POST /api/bank-reconciliation/import · POST /api/bank-reconciliation/auto-match ·
             GET /api/bank-reconciliation/lines · GET /api/bank-reconciliation/summary ·
             POST /api/bank-reconciliation/lines/{id}/match|unmatch|ignore
RBAC:        permission "cash" (admin/manager).
⚠️ JANGAN BUAT: bank_statements, rekening_koran, statements, reconciliations,
   fin_bank_statements, fin_reconciliation_sessions — gunakan bank_statement_lines.
```

### bank_statement_formats + bank_match_rules  [FASE G-8 IMPLEMENTED — parser multi-bank & aturan belajar]
Dua koleksi pendukung rekonsiliasi bank. **Keduanya SCOPED** (`entity_id`) bersama
`bank_statement_lines` — sebelum FASE G-8 mutasi bank TIDAK ter-scope sehingga user PT-A
cukup mengirim `bank_account_id` PT-B untuk membacanya (ditutup + POC bukti-merah).
```
Collections: bank_statement_formats (prefix bsf_) · bank_match_rules (prefix bmr_)
Router:      routers/bank_reconciliation.py
Services:    services/bank_statement_parser.py (murni, tanpa DB) · services/bank_recon_service.py
Components:  features/finance/bank/ReconFormatsPanel.jsx · ReconRulesPanel.jsx
Config:      config_catalog_bank.py (grup `bank` di Pusat Pengaturan)

bank_statement_formats — TEMPLATE cara membaca rekening koran (bisa dibuat user):
  id                string  prefix "bsf_"
  entity_id         string  FK business_entities.id  (SCOPED)
  name              string  nama template
  bank_code         string  bca | mandiri | bni | bri | permata | generic | custom
  file_kind         enum    csv | mt940 | ofx
  delimiter         string  pemisah kolom CSV
  has_header        bool    baris pertama header?
  skip_rows         int     baris awal yang dilewati
  decimal_style     enum    auto | id (1.234.567,89) | en (1,234,567.89)
  date_format       string  auto | dd/mm/yyyy | dd-mm-yyyy | yyyy-mm-dd | yyyymmdd | yymmdd
  columns           object  {date, description, ref, amount, amount_in, amount_out,
                            direction, balance, external_id} → NAMA header ATAU indeks kolom
  in_markers[] / out_markers[]  penanda arah dana (mis. CR/DB, K/D)
  header_signature[]  tanda tangan untuk DETEKSI OTOMATIS template
  builtin           bool    preset bawaan (5 bank + MT940 + OFX), boleh disalin & diubah
  active            bool    hapus = nonaktifkan (bukan hilang)

bank_match_rules — aturan hasil PEMBELAJARAN dari pencocokan manual:
  id                string  prefix "bmr_"
  entity_id         string  FK business_entities.id  (SCOPED)
  bank_account_id   string  FK bank_accounts.id
  desc_key          string  sidik jari berita transfer (angka dibuang)
  direction         enum    in | out
  counterparty      string  nama pihak hasil tebakan parser
  sample_desc       string  contoh berita transfer asli
  hits              int     berapa kali pola ini dicocokkan manual
  status            enum    suggested | active | rejected
  created_by / decided_by / decided_at / created_at / updated_at

Aturan HANYA ditawarkan (status `suggested`) setelah pola sama dicocokkan manual
`bank.rule_learn_after` kali (bawaan 3×) dan baru berlaku setelah MANUSIA menyetujui
(`activate`). Aturan aktif menambah `bank.rule_bonus_score` poin pada skor pencocokan.
Endpoints:   GET/POST /api/bank-reconciliation/formats · DELETE .../formats/{id} ·
             POST /api/bank-reconciliation/preview · POST .../import-file ·
             GET /api/bank-reconciliation/rules · POST .../rules/{id}/decide
RBAC:        permission "cash" (admin/manager).
⚠️ JANGAN BUAT: bank_formats, statement_templates, bank_rules, match_rules — gunakan
   bank_statement_formats & bank_match_rules.
```

### contra_bons  [FASE G-7 IMPLEMENTED — Kontrabon / siklus tukar faktur supplier]
Supplier tekstil tidak ditagih per surat jalan: mereka datang **sekali per siklus** membawa
setumpuk faktur, lalu terjadi ritual **tukar faktur** (faktur supplier ditukar tanda terima
kami, pembayarannya dijadwalkan). Satu kontrabon menggabungkan BANYAK `vendor_bills` satu
supplier menjadi **satu tanda terima + satu pembayaran**, berikut potongan terstruktur yang
menunjuk dokumen nyata. **SCOPED** (`entity_id`) — kontrabon PT lain tidak terlihat (403).
```
Collection:  contra_bons                Prefix: cbn_   Nomor: <ENT>/CB-#####
Router:      routers/contra_bons.py
Services:    services/contra_bon_service.py   (siklus, potongan, 3-way, pembayaran)
             services/contra_bon_reminder.py  (jadwal tukar faktur + pengingat H-n)
             services/contra_bon_scan.py      (pemeriksa INV-CB-01..04)
Components:  features/purchasing/contrabon/ContraBonsView.jsx · ContraBonListTable.jsx ·
             ContraBonDetailPanel.jsx · ContraBonParts.jsx · ContraBonCreateWizard.jsx ·
             UnbilledReceiptsTab.jsx · ExchangeSchedulesTab.jsx · ExchangeScheduleModal.jsx ·
             DeductionModal.jsx · DecisionModal.jsx · PayModal.jsx ·
             PaymentScheduleModal.jsx · ReasonNoteModal.jsx · contraBonApi.js
             (jembatan G-8: features/finance/bank/ReconContraBonModal.jsx)
Config:      config_catalog_contrabon.py (grup `kontrabon` di Pusat Pengaturan — 10 kunci)
Invarian:    INV-CB-01..04 (scripts/verify_data_integrity.py lapisan `contrabon`)
Job:         contra_bon_reminder (harian 07:30 WIB, services/scheduler_service.py)
PDF:         doc_type `contra_bon` → "Tanda Terima Kontrabon" (esignable)

  id                string  prefix "cbn_"
  number            string  <ENT>/CB-##### (sequence atomik number_sequences, doc_type CB)
  entity_id         string  FK business_entities.id  (SCOPED)
  supplier_id       string  FK suppliers.id · supplier_name/code/npwp/supplier_pic snapshot
  cycle_date        string  tanggal tukar faktur · due_date: jatuh tempo (dari termin supplier)
  status            enum    draft | submitted | verified | approved | scheduled_payment |
                            paid | disputed | cancelled
  bills[]           object  {bill_id, bill_number, supplier_invoice_no, po_id, po_number,
                            bill_date, due_date, grand_total, outstanding_at_pick,
                            applied_amount, settled_amount, claim_deduction_info,
                            match:{status, exceptions[], po_status, evaluated_at}}
  deductions[]      object  {id, kind, label, ref_type, ref_id, ref_number, bill_id,
                            exception_key, amount, reason_code, note, posts_gl,
                            gl_journal_id, applied_at, added_by, added_at}
                            kind: purchase_return | supplier_advance | supplier_penalty |
                                  match_variance | other_agreed
  decisions[]       object  {at, by, exception_key, bill_id, action(accept|deduct|dispute),
                            reason_code, reason_label, amount, note, exception_detail}
  totals            object  {bills_total, deductions_total, net_payable, paid_total, outstanding}
  match_summary     object  {status, exceptions_count, pending_count, pending_keys[],
                            exceptions_value}
  schedule          object  {planned_payment_date, method, bank_account_id, notes}
  payments[]        object  {id, amount, method, cash_type, cash_txn_id, cash_txn_number,
                            bank_account_id, bank_line_id, notes, paid_by, paid_at,
                            allocations[]}
  policy_snapshot   object  toleransi & ambang yang berlaku saat dokumen dibuat
  timeline[]        object  {at, event, label, actor, note}
  refs[]            object  relasi dokumen dua arah (FASE G-4)
  created_by / created_by_id / created_at / updated_at · submitted_* verified_* approved_*
  paid_at · disputed_at · dispute_reason_code · dispute_note · cancelled_at · cancel_note

suppliers.invoice_exchange (BUKAN koleksi baru — jadwal adalah ATRIBUT supplier):
  {mode: none|weekly|biweekly|monthly, weekday 0..6, day_of_month 1..28, pic_name,
   notes, anchor_date, updated_by, updated_at}

ATURAN YANG DIJAGA:
  * Satu `vendor_bill` hanya boleh berada di SATU kontrabon belum `cancelled`, dan
    Σ `applied_amount` atas satu faktur ≤ `grand_total` (INV-CB-01).
  * `net_payable == Σ bills.applied_amount − Σ deductions.amount` (≥ 0); kontrabon `paid`
    → `Σ payments.amount == net_payable` (INV-CB-02).
  * Setiap pengecualian 3-way DI LUAR toleransi wajib punya keputusan berlabel sebelum
    status melewati `verified` (INV-CB-03).
  * Satu dokumen potongan (`purchase_return`/`ap_advance`) hanya boleh dipakai di SATU
    kontrabon belum `cancelled`; potongan klaim makloon yang sudah menempel di faktur
    DITOLAK jadi potongan kontrabon (INV-CB-04) — kalau tidak, hutang berkurang dua kali.
  * Pembuat kontrabon TIDAK boleh menyetujui kontrabonnya sendiri; di atas
    `contra_bon.approval_threshold_rupiah` wewenangnya naik ke `high_value_approval_role`.
Jurnal potongan saat kontrabon DIBAYAR (services/gl_service.post_contra_bon_deduction):
  purchase_return  : TIDAK ada jurnal baru (Dr 2-1100 / Cr 1-1300 sudah lahir saat retur
                     disetujui) — di kontrabon ia jadi pelunasan NON-KAS pada faktur
  supplier_advance : Dr 2-1100 / Cr 1-1400      supplier_penalty : Dr 2-1100 / Cr 4-9300
  match_variance   : Dr 2-1100 / Cr 2-1150      other_agreed     : Dr 2-1100 / Cr 4-9000
Pembayaran        : SATU `cash_transactions` (ref_type `contra_bon`, nomor kontrabon di
                    deskripsi → langsung jadi kandidat Rekonsiliasi Bank G-8)
Endpoints:   GET /api/contra-bons · .../meta · .../summary · .../status-counts ·
             .../prepare · .../unbilled-receipts · .../exchange-schedules ·
             .../bank-line-candidates/{line_id} · GET .../{id} · .../{id}/receipt ·
             POST /api/contra-bons · .../{id}/deductions · DELETE .../deductions/{ded_id} ·
             POST .../{id}/decide · submit · verify · approve · schedule · pay ·
             pay-from-bank-line/{line_id} · dispute · cancel · POST .../run-reminder ·
             PUT /api/suppliers/{supplier_id}/invoice-exchange
RBAC:        permission "contra_bon": view · create · update · verify · approve · pay
             (warehouse: view saja — mereka pemilik jawaban "GR belum ditagih",
              tetapi tidak memutus uang)
⚠️ JANGAN BUAT: contrabons, contra_bon_items, invoice_exchanges, supplier_cycles,
   contra_bon_deductions — gunakan `contra_bons` (potongan & jadwal sudah inline).
```

### interco_transactions + interco_accounts + interco_settlements  [FASE G-6 IMPLEMENTED — Transaksi Antar Entitas (jual-beli antar-PT)]
Antar-PT itu **jual-beli**, bukan pindah gudang: PT KSC menjual kain ke CV Kanda dengan
**harga internal dari kontrak** dan mengambil **margin**; keduanya PT terpisah dengan buku,
pajak, dan pelanggan sendiri. Satu transaksi lahir sebagai **DOKUMEN KEMBAR** (satu di tiap
PT, saling menunjuk lewat `pair_id`) sehingga isolasi lintas-PT TIDAK dilonggarkan. Barang
fisiknya tetap berjalan lewat **tugas gudang** (`warehouse_transfers` ber-`interco_pair_id`)
— dan justru karena itu jurnal at-cost M-3 DILEWATI supaya tidak dobel. **SCOPED** (`entity_id`).
```
Collections: interco_transactions  Prefix: ict_   Nomor: <ENT>/IC-#####   (2 dokumen per pair)
             interco_accounts      id: ica_{from}_{to}   (saldo per pasangan PT, proyeksi)
             interco_settlements   Prefix: ics_   Nomor: <ENT>/ICS-#####  (netting)
Router:      routers/interco.py            (/api/interco/*)
             routers/consolidation.py      (POST /api/consolidation/sync-g6)
Services:    services/interco_service.py       (harga · PPN · siklus · jurnal · saldo · netting ·
                                                jembatan gudang · pembalikan · pair_journal)
             services/consolidation_service.py (eliminasi unrealized profit: create/update/remove)
             services/roll_service.py          (execute_ownership_transfer + lot pindah pemilik)
Components:  features/finance/interco/IntercoView.jsx · IntercoCreateModal.jsx ·
             IntercoSettlementModal.jsx · IntercoDetailPanel.jsx · IntercoCancelModal.jsx ·
             InternalContractWizardModal.jsx · intercoApi.js
             (eliminasi: features/finance/GroupConsolidationView.jsx)
Config:      config_catalog_interco.py (grup `antar_entitas` — 7 kunci; `ppn_mode` ber-scope PT)
Invarian:    INV-IC-01..06 (scripts/verify_data_integrity.py lapisan `interco`)
POC:         backend/tests/test_g6_poc.py (21 skenario, bukti-merah, nol residu)
Doc types:   `interco_transaction` & `interco_settlement` terdaftar di doc_refs_service (G-4)
Akun GL:     1-1250 IC-AR · 2-1250 IC-AP · 1-1310 **Persediaan Dalam Perjalanan (Antar-PT)** ·
             1-1300 Persediaan · 4-1000 Pendapatan · 5-1000 HPP · 2-1200/1-1500 PPN

interco_transactions:
  id                string  prefix "ict_"          pair_id  string  prefix "icp_" (dokumen kembar)
  number            string  <ENT>/IC-##### (sequence per entitas)
  entity_id         string  SCOPE = PT pemilik dokumen ini
  role              enum    seller | buyer         counterpart_id / counterpart_number
  seller_entity_id / seller_entity_name · buyer_entity_id / buyer_entity_name
  items[]           object  {product_id, sku, product_name, quantity, unit, unit_price,
                            price_source(fixed_price|at_cost|cost_plus_pct|override),
                            contract_id, line_subtotal, notes}
  subtotal / tax_apply / tax_rate / tax_amount / grand_total / settled_amount
  pricing_mode      enum    fixed_price | at_cost | cost_plus_pct   (bawaan dari config)
  ppn_mode          enum    ikut_pkp | tanpa_ppn | dengan_ppn       (scope PT)
  status            enum    draft | confirmed | shipped | received | invoiced | settled |
                            disputed | cancelled
  doc_date / due_date / notes
  warehouse_transfer_id / warehouse_transfer_code / warehouse_transfer_status
                            (jembatan US8: waiting_approval | completed | cancelled)
  timeline stamp    created_at/by · confirmed_at/by · shipped_at/by · received_at/by ·
                    invoiced_at/by · settled_at · cancelled_at/by · cancel_reason
  refs[]            object  relasi dokumen dua arah (FASE G-4)

interco_accounts (PROYEKSI — jangan pernah $inc, selalu hitung ulang):
  id ica_{from}_{to} · entity_id (SCOPE) · from_entity_id/name · to_entity_id/name
  role enum receivable|payable · open_count · gross_amount · settled_amount · outstanding
  aging_days · reminder_active (dari `antar_entitas.settlement_reminder_days`) · updated_at

interco_settlements:
  id ics_ · number <ENT>/ICS-##### · entity_id = PT pembayar (SCOPE)
  payer_entity_id/name · payee_entity_id/name · settle_date · method netting|transfer|cash
  applied[]  {interco_id, counterpart_id, pair_id, number, counterpart_number, grand_total,
              previous_settled, applied_amount}
  total_applied · status posted · notes · created_by/at

ATURAN YANG DIJAGA:
  * Harga `fixed_price` WAJIB dari kontrak internal aktif (`supplier_contracts` dengan
    `partner_kind="entity"`, `partner_id` = PT pembeli, `product_id` = barang). Tidak ada
    kontrak → transaksi DITOLAK dengan kalimat menuntun (sistem TIDAK menebak harga).
  * Jurnal saat DIKONFIRMASI: penjual `Dr 1-1250 / Cr 4-1000 (+2-1200)`; pembeli
    `Dr 1-1310 (+1-1500) / Cr 2-1250`. Jurnal saat BARANG BERPINDAH: penjual
    `Dr 5-1000 / Cr 1-1300` (biaya nyata roll yang keluar); pembeli `Dr 1-1300 / Cr 1-1310`.
    (INV-IC-01 · INV-IC-06 · menutup drift GL↔subledger)
  * `IC-AR` penjual == `IC-AP` pembeli untuk setiap pasangan PT (INV-IC-02); saldo
    `interco_accounts` == Σ transaksi terbuka − Σ settlement (INV-IC-04).
  * Margin antar-PT WAJIB tereliminasi di konsolidasi selama barang belum terjual keluar —
    dijaga OTOMATIS (`intercompany_eliminations.source_g6_pair_id`, `auto_generated=true`),
    ikut diperbarui saat settlement & dihapus saat pembatalan (INV-IC-03).
  * PPN keluaran penjual == PPN masukan pembeli; mode `tanpa_ppn` → nol di KEDUA sisi (INV-IC-05).
  * Tugas gudang tertaut `interco_pair_id`: jurnal at-cost M-3 TIDAK diposting lagi & roll
    pembeli dinilai ulang ke harga beli internal (INV-IC-06). Satu tugas per transaksi.
  * "Tandai Diterima" DITOLAK bila belum ada tugas gudang selesai (persediaan pembeli tidak
    boleh naik untuk barang yang tidak ada di gudang mana pun).
  * Pembatalan sesudah dikonfirmasi WAJIB ber-alasan (≥5 huruf) → jurnal pembalik
    `{pair}:{sisi}:reversal` di kedua buku + tugas gudang menunggu ikut batal (roll dilepas).
Endpoints:   GET /api/interco/meta · /summary · /transactions · /transactions/{id} ·
             /transactions/{id}/journal · /accounts · /accounts/{from}/{to} · /settlements ·
             /settlements/{id} · /contracts
             POST /api/interco/transactions · .../{id}/confirm|ship|receive|invoice|cancel ·
             .../{id}/warehouse-task · POST /api/interco/settlements ·
             POST /api/consolidation/sync-g6
RBAC:        permission "interco": view · create · update · approve · ship · receive ·
             invoice · cancel · settle   (warehouse: view · ship · receive saja)
⚠️ JANGAN BUAT: intercompany_transactions, interco_docs, interco_balances, ic_settlements,
   internal_price_lists — harga internal hidup di `supplier_contracts` (`partner_kind="entity"`),
   saldo di `interco_accounts`, pelunasan di `interco_settlements`.
```

### finance_cases  [FASE G-9 IMPLEMENTED — Pusat Kasus Keuangan (Finance Exception Desk)]
Antrean **uang yang nyangkut**: salah transfer rekening, masuk rekening pribadi karyawan,
bayar dobel, bayar invoice yang salah, nominal terpotong biaya bank, giro ditolak, dana
tak dikenal, salah PT, kelebihan bayar supplier. **SCOPED** (`entity_id`) — kasus PT lain
tidak boleh terlihat maupun ditutup (403).
```
Collection:  finance_cases              Prefix: fcs_   Nomor: <ENT>/CASE-#####
Router:      routers/finance_cases.py
Services:    services/finance_case_service.py   (siklus, SLA, wewenang, ringkasan)
             services/finance_case_playbooks.py (11 playbook — kesepakatan bisnis)
             services/finance_case_actions.py   (eksekutor: uang benar-benar berpindah)
             services/finance_case_scan.py      (kasus otomatis + pemeriksa INV-CASE)
Components:  features/finance/cases/FinanceCasesView.jsx · CaseInboxTable.jsx ·
             CaseDetailPanel.jsx · CasePlaybookWizard.jsx · CaseCreateModal.jsx
Config:      config_catalog_case.py (grup `kasus` di Pusat Pengaturan — 12 kunci)
Invarian:    INV-CASE-01..03 (scripts/verify_data_integrity.py lapisan `case`)
Job:         finance_case_scan (harian 08:25 WIB, services/scheduler_service.py)

  id                string  prefix "fcs_"
  number            string  <ENT>/CASE-##### (sequence atomik number_sequences)
  entity_id         string  FK business_entities.id  (SCOPED)
  case_type         enum    dana_tak_dikenal | bayar_dobel | salah_rekening_internal |
                            rekening_pribadi_karyawan | pembayar_pihak_ketiga |
                            salah_invoice | selisih_biaya_bank | giro_ditolak |
                            refund_pelanggan | salah_entitas | lebih_bayar_supplier
  title / description string  kalimat manusia (bukan kode)
  amount            float   nominal uang yang dipertaruhkan
  customer_id       string  FK customers.id (opsional)
  supplier_id       string  FK suppliers.id (opsional)
  order_ids[]       string  FK sales_orders.id
  source            object  {kind: bank_holding|bank_line|ar_receipt|vendor_bill|manual,
                             id, label} — asal kasus (deep-link dari layar sumbernya)
  status            enum    open | in_progress | resolved | rejected
  assignee          string  penanggung jawab
  attachments[]     object  {name, path, content_type} — bukti (wajib utk jenis ber-klaim)
  sla_hours         int     dari `case.sla_hours` / `case.sla_hours_high` (nominal besar)
  sla_due_at        string  batas waktu; lewat = TERLAMBAT di inbox
  escalation_level  int     0..2 (naik ke manager lalu admin lewat notifikasi critical)
  reason_code       string  FK amendment_reasons.code (applies_to `finance_case`, G-1)
  reason_label      string  snapshot label alasan
  resolution        object  {action, action_label, effect, produces, amount, note,
                             extra, next_action, auto_resolved, at, by}
  documents[]       object  {kind, id, number, label} — DOKUMEN TURUNAN yang benar-benar
                            lahir: journal_entry · cash_transaction · order_payment ·
                            ar_receipt · penalty · store_credit_entry · supplier_advance
  approved_by / approved_at   penyetuju bila nominal >= `case.require_approval_above`
  resolved_by / resolved_at   siapa & kapan kasus ditutup
  auto_source       string  "" | "titipan menganggur" | "kwitansi kembar"
  timeline[]        object  {event, label, actor, note, at} — jejak waktu kasus
  refs[]            object  relasi dokumen dua arah (FASE G-4)
  created_by / created_at / updated_at

ATURAN YANG DIJAGA:
  * Kasus `resolved` WAJIB punya dokumen turunan + alasan berlabel + penyelesai
    (INV-CASE-01) — tidak ada "sudah beres kok" tanpa surat.
  * Titipan dana (2-1950) menganggur > `case.holding_case_after_days` WAJIB punya kasus
    terbuka (INV-CASE-02) — uang tak dikenal tidak boleh terlupakan.
  * Playbook `moves_cash=True` WAJIB melahirkan jurnal seimbang (INV-CASE-03). Playbook
    `salah_invoice` dikecualikan DENGAN SENGAJA: realokasi antar pesanan memakai akun GL
    yang sama (1-1200) sehingga jurnal baru justru menyesatkan.
  * Kasus yang sudah melahirkan dokumen TIDAK bisa dibuka ulang (ledger tambah-saja) —
    tindak lanjutnya kasus BARU.
Akun GL baru: 1-1150 Kas & Bank Transit (pindah-buku) · 1-1280 Piutang Titipan Karyawan.
Endpoints:   GET /api/finance-cases · GET .../playbooks · .../reasons · .../policy ·
             .../stats · GET .../{id} · POST /api/finance-cases ·
             POST .../{id}/assign · .../note · .../resolve · .../reject · .../reopen ·
             POST /api/finance-cases/scan
RBAC:        permission "finance_case": view · create · resolve · admin
             (sales: view+create — melapor & memantau, TIDAK menutup kasus uang)
⚠️ JANGAN BUAT: fin_cases, exception_cases, finance_exceptions, case_files — gunakan
   finance_cases.
```

### fin_fixed_assets + fin_depreciation_entries  [R6.2 IMPLEMENTED — Aset Tetap & Penyusutan]
Master aset tetap + histori penyusutan (straight-line) + disposal (gain/loss). Semua event
diposting ke GL & **idempotent** per sumber.
```
Collections: fin_fixed_assets (prefix fasset_, number FA-##### per entitas)
             fin_depreciation_entries (prefix depe_)
Router:      routers/fixed_assets.py   Service: services/fixed_asset_service.py
Component:   features/finance/FixedAssetsView.jsx (Kas & Aset → Aset Tetap)
fin_fixed_assets fields:
  id, number, name, category (Peralatan & Mesin|Kendaraan|Inventaris & Perabot Kantor|Bangunan)
  acquisition_cost, acquisition_date, useful_life_months, salvage_value, method="straight_line"
  entity_id (FK business_entities), gl_account_asset (1-2100/2200/2300/2400),
  gl_account_dep_exp="6-6000", gl_account_acc_dep="1-2900", funding_account (default 1-1100)
  monthly_depreciation, accumulated_depreciation, book_value, depreciated_months,
  last_depreciation_period, status (active|fully_depreciated|disposed),
  acquisition_je, disposal {date, proceeds, book_value, gain_loss, result, je_id, je_number}
fin_depreciation_entries fields:
  id, asset_id, asset_number, entity_id, period (YYYY-MM), amount,
  accumulated_after, book_value_after, je_id, je_number, created_at
Straight-line: monthly = (acquisition_cost − salvage_value) / useful_life_months (bulan terakhir
  serap sisa pembulatan). Idempotent per (asset_id, period).
Posting GL (via gl_service):
  Perolehan  : Dr <akun aset> / Cr 1-1100 Kas/Bank            (source_type fixed_asset_acquisition)
  Penyusutan : Dr 6-6000 Beban Penyusutan / Cr 1-2900 Akum.   (source_type fixed_asset_depreciation, sid=asset:period)
  Disposal   : Dr 1-2900 akum + Dr 1-1100 proceeds [+Dr 6-9500 rugi]
               / Cr <akun aset> perolehan [+Cr 4-9100 laba]   (source_type fixed_asset_disposal)
Akun COA baru: 1-2200 Kendaraan, 1-2300 Inventaris & Perabot, 1-2400 Bangunan,
  1-2900 Akumulasi Penyusutan (contra-asset, saldo kredit), 6-6000 Beban Penyusutan,
  4-9100 Laba Pelepasan Aset, 6-9500 Rugi Pelepasan Aset.
Endpoints: GET /api/fixed-assets · GET /api/fixed-assets/meta · GET /api/fixed-assets/summary ·
  POST /api/fixed-assets · GET/PATCH /api/fixed-assets/{id} ·
  POST /api/fixed-assets/run-depreciation · POST /api/fixed-assets/{id}/dispose
RBAC: permission "fixed_asset" (admin/manager).
Invarian integritas: FA-1 accumulated==Σentri · FA-2 book_value==cost−akum ·
  FA-3 GL 1-2900==Σakum aktif · FA-4 GL akun aset==Σperolehan aktif.
⚠️ JANGAN BUAT: fixed_assets, assets, aset, depreciation, penyusutan (koleksi) —
   gunakan fin_fixed_assets & fin_depreciation_entries.
```

### budgets + fin_budget_rules  [P1-4 / R6.3 IMPLEMENTED — Budget Control penuh]
Anggaran per entitas dengan **dua dimensi** (akun COA & kategori beban) + kebijakan
over-budget per entitas. Komitmen & realisasi **diturunkan (derived)** — tidak ada
materialized cache sehingga selalu konsisten dengan sumber (GL-safe).
```
Collections: budgets            (prefix budget_)
             fin_budget_rules   (prefix bgrule_, 1 dokumen per entity_id)
Router:      routers/budgets.py    Service: services/budget_service.py
Component:   features/finance/BudgetView.jsx + BudgetParts.jsx
             (Keuangan → Laporan & Analitik → Anggaran vs Realisasi)
budgets fields:
  id, entity_id (FK business_entities), year, month (0=tahunan | 1–12 bulanan),
  dimension ("account" | "category"), key (kode akun COA | kode expense_categories),
  label, account_code, account_name, account_type, amount, note, created_at, updated_at
  UNIK per (entity_id, year, month, dimension, key)  → invarian BG-1.
fin_budget_rules fields:
  id, entity_id, mode ("off"|"warn"|"block"), warn_threshold_pct (0–100, default 85),
  unbudgeted_action ("allow"|"warn"|"block"), enforce_po_create, enforce_po_approve,
  updated_by, updated_at
Sumber angka (derived):
  Realisasi dimension=account   → journal_entries (non-void, exclude closing) per akun & bulan
  Realisasi dimension=category  → cash_advance_settlements status posted_to_gl (category_totals)
  Komitmen  PO terbuka          → purchase_orders status ∈ (draft, submitted, waiting_approval,
                                   pending, approved, confirmed, sent, receiving,
                                   partially_received); key = PO.budget_dimension/budget_key
                                   atau default akun Persediaan 1-1300; nilai = net_subtotal (DPP)
  Komitmen  LPJ petty cash      → cash_advance_settlements status draft|submitted (per kategori)
Rumus: spent = actual + committed · remaining = budget − spent · variance = budget − actual
Enforcement (budget_service.enforce_po_budget): dipanggil router PO saat create & approve.
  mode=off  → dilewati · mode=warn → daftar peringatan (PO tetap dibuat, jejak di timeline)
  mode=block → HTTP 400 (create) / 409 (approve). Komitmen PO sendiri dikecualikan saat approve.
PO menyimpan: budget_dimension, budget_key, budget_check {mode, when, warnings[], checks[], blocked}
Endpoints: GET/POST /api/finance/budgets · PATCH/DELETE /api/finance/budgets/{id} ·
  GET /api/finance/budget-vs-actual · GET /api/finance/budget-keys ·
  GET/PUT /api/finance/budget-rules · POST /api/finance/budget-check
RBAC: permission "budget" (admin: view/create/update/delete/configure; manager: tanpa configure).
Invarian integritas: BG-1 tak ada duplikat kunci · BG-2 amount>0 & month 0–12 ·
  BG-3 key terdaftar (akun COA/kategori) · BG-4 kebijakan rules valid.
⚠️ JANGAN BUAT: fin_budgets, anggaran, budget_lines, fin_budget_commitments,
   fin_budget_actuals — gunakan `budgets` (+ derived) & `fin_budget_rules`.
```

### mfg_boms + mfg_work_orders  [R6.4 IMPLEMENTED — Produksi In-House (BOM & Work Order)]
Resep produksi MULTI-komponen + perintah kerja yang **mengonsumsi roll bahan (FEFO)** dan
**memproduksi roll barang jadi** (Roll-as-SSOT). HPP = Σ nilai bahan + overhead (opsional).
```
Collections: mfg_boms          (prefix bom_)
             mfg_work_orders   (prefix wo_, number WO-##### )
Router:      routers/production.py   Service: services/production_service.py
Component:   features/production/ProductionView.jsx + ProductionWO.jsx + ProductionParts.jsx
             (Gudang → Produksi (BOM & WO))
mfg_boms fields:
  id, entity_id (FK business_entities), name, output_product_id (FK products), output_sku,
  output_name, output_unit, overhead_per_unit (>=0, Rp per unit output),
  components[] {material_product_id (FK products), sku, name, unit, qty_per_unit (>0)},
  status ("active"|"inactive"), notes, created_by, created_at, updated_at
  Validasi: >=1 komponen · qty_per_unit>0 · bahan != output · tanpa komponen duplikat.
mfg_work_orders fields:
  id, wo_number, entity_id, bom_id (FK mfg_boms), bom_name, output_product_id, output_sku,
  output_name, output_unit, warehouse_id (FK warehouses), warehouse_name, planned_qty (>0),
  overhead_per_unit (snapshot dari BOM), material_plan[] {material_product_id, sku, name, unit,
  qty_per_unit, required_qty, available_qty, sufficient}, status ("draft"|"released"|
  "completed"|"cancelled"), notes, consumed[] {material_product_id, sku, name, unit, qty, value},
  produced_roll_ids[] (FK inventory_rolls), produced_qty, material_cost, overhead_cost,
  total_cost, unit_cost, je_id (FK journal_entries, hanya bila overhead>0),
  created_by/at, released_by/at, completed_by/at, cancelled_by/at, cancel_reason
Alur: draft → released → completed (cancel hanya dari draft/released; completed TIDAK bisa dibatalkan).
Complete (idempotent per WO):
  1. Pre-check ketersediaan SEMUA bahan (fail-fast 400 sebelum mutasi apa pun)
  2. Konsumsi roll bahan FEFO per (product, warehouse, owner_entity) → movement
     `production_consume` (qty negatif) + rebuild_balance
  3. Produksi 1 roll barang jadi via roll_service.create_inbound_roll
     (acquired.via="production_output", unit_cost = HPP/unit)
  4. GL: hanya OVERHEAD dikapitalisasi → Dr 1-1300 / Cr 5-1100 (source_type production_output)
HPP: material_cost = Σ(qty konsumsi × unit_cost roll) · overhead_cost = overhead_per_unit × qty
     total_cost = material + overhead · unit_cost = total_cost / planned_qty
GL-safe: bahan & barang jadi memakai akun Persediaan 1-1300 yang sama → porsi bahan NET-0
  (subledger roll sudah menyeimbangkan); akun baru 5-1100 Overhead Produksi Diserap.
Endpoints: GET/POST /api/production/boms · GET/PATCH/DELETE /api/production/boms/{id} ·
  GET/POST /api/production/work-orders · GET /api/production/work-orders/{id} ·
  POST /api/production/work-orders/{id}/release|complete|cancel · GET /api/production/summary
RBAC: permission "production" — admin/manager: view, manage_bom, create, release, complete, cancel;
  warehouse: view, create, release, complete (TANPA manage_bom & cancel); sales: tidak ada akses (403).
Invarian integritas: MFG-1 resep BOM valid · MFG-2 HPP WO konsisten (total=bahan+overhead,
  unit=total/qty, roll output ada) · MFG-3 konsumsi == movement & roll output senilai HPP ·
  MFG-4 overhead terkapitalisasi tepat di GL 5-1100 (je_id iff overhead>0).
Seed demo: `seed_production()` di seed_realistic.py (2 BOM + 3 WO: 1 selesai, 1 dirilis, 1 draft).
⚠️ JANGAN BUAT: boms, bill_of_materials, work_orders, production_orders, resep_produksi —
   gunakan `mfg_boms` & `mfg_work_orders`. (Resep MAKLOON/subkon tetap `process_recipes`.)
```

### sys_scheduler_runs + sys_wa_outbox  [R6.5 IMPLEMENTED — Penjadwal, Notifikasi & Kanal WhatsApp]
Scheduler **APScheduler** (AsyncIOScheduler, zona **Asia/Jakarta**) menjalankan **12 job** alert dari
**data nyata** → menulis ke koleksi `notifications` yang SUDAH ADA (Fase 0) dan — bila kanal
WhatsApp diaktifkan — mendorong pesan ke `sys_wa_outbox` lewat provider pluggable `services/wa/`.
Mode default provider = **`simulated`**: pesan TIDAK dikirim ke jaringan tetapi TETAP tercatat
lengkap (tujuan + isi) agar user bisa verifikasi sebelum mengisi kredensial nyata.
```
Collections: sys_scheduler_runs  (prefix srun_)   — histori eksekusi job
             sys_wa_outbox       (prefix waout_)  — antrean/arsip pesan WhatsApp
             system_settings (scope="alerts")     — jadwal job override + config WA + lock
Router:      routers/scheduler.py     Schemas: schemas_scheduler.py
Services:    services/scheduler_service.py (registry job + APScheduler + histori)
             services/alert_service.py     (7 generator alert dari data nyata)
             services/alert_ops_service.py (PS-21 — 3 generator operasional + notifikasi restock)
             services/wa_alert_service.py  (penerima, compose, dispatch, outbox, dedupe)
             services/digest_service.py    (R6.6 — ringkasan harian per penerima)
             services/escalation_service.py (R6.6 — eskalasi bertingkat)
             services/wa/{simulated,meta_cloud,fonnte}.py (provider pluggable)
Component:   features/admin/scheduler/SchedulerView.jsx + SchedulerParts.jsx + SchedulerWa.jsx
             + SchedulerPolicy.jsx (R6.6 — panel eskalasi & pratinjau ringkasan)
             (Pengaturan & Master Data → Penjadwal & Notifikasi) · bell: components/NotificationCenter.jsx

Registry job (12, di services/scheduler_service.py — JADWAL dapat diubah user tanpa deploy):
  ar_overdue         harian 08:00 WIB  piutang lewat jatuh tempo (ar_aging_service)
  ap_due             harian 08:05 WIB  tagihan supplier due<=7 hari / lewat (vendor_bills + payment_terms)
  depreciation_due   harian 08:10 WIB  penyusutan bulan lalu belum dijalankan (fin_fixed_assets)
  budget_alert       harian 08:15 WIB  anggaran over/mendekati batas (budget_service)
  production_stalled harian 08:20 WIB  WO dirilis >3 hari / draft >7 hari / bahan kurang
  ops_stalled        tiap 4 jam        tugas gudang terbuka >2 hari (wms_tasks)
  event_scan         tiap 4 jam        stok menipis · reservasi kedaluwarsa · approval SO/PO
  escalation_scan    tiap 2 jam        [R6.6] alert belum dibaca > batas jam → naik ke atasan
  daily_digest       harian 08:30 WIB  [R6.6] semua alert hari ini → 1 pesan ringkas/penerima
  po_arrival         tiap 2 jam        [PS-21] GR/inbound PO selesai <24 jam → MD + gudang + sales
                                        pemilik order pendingan (juga dipanggil SEKETIKA saat GR selesai)
  backorder_ready    tiap 2 jam        [PS-21] pendingan (backorder) yang stoknya sudah tersedia →
                                        sales pemegang akun + manager (juga dipanggil saat auto-fulfill)
  ar_due_soon        harian 07:55 WIB  [PS-21] piutang pada offset H-3/H-1/H/H+1 (melengkapi ar_overdue);
                                        sumber angka = ar_aging_service.orders_due_soon (SSOT AR)

sys_scheduler_runs fields:
  id (srun_), job_id, job_label, trigger ("schedule"|"manual"), actor, started_at, finished_at,
  status ("running"|"success"|"failed"), created (jml notifikasi baru), scanned, wa_queued,
  detail, error, duration_ms
sys_wa_outbox fields:
  id (waout_), dedupe_key ("<dedupe_key notif>|<nomor>" → maks 1 pesan/hari/tujuan;
    untuk ringkasan harian: "digest:<YYYY-MM-DD>|<nomor>"),
  to (E.164 tanpa '+', mis. 6281...), to_name, to_role, notification_id (FK notifications),
  notif_type (termasuk "daily_digest" & "escalation" sejak R6.6), severity,
  title, text (isi pesan LENGKAP untuk audit), provider,
  status ("simulated"|"sent"|"failed"), error, message_id, entity_id, created_at, sent_at, retried_at,
  digest_groups / digest_alerts (hanya baris ringkasan harian — jumlah kelompok & alert)
system_settings scope="alerts" fields:
  jobs{<job_id>: {enabled, hour, minute | interval_hours}}, updated_at,
  wa{enabled, provider, phone_number_id, template_name, template_lang, sender, pic_number,
     send_to_roles, min_severity, access_token*, fonnte_token*,
     delivery_mode ("instant"|"digest", R6.6), critical_bypass (bool, R6.6)},
  escalation{enabled, after_hours (1–72), min_severity, max_level (1–3)}   ← R6.6
  lock{owner, heartbeat, since}  ← guard single-instance scheduler (TTL 180s, heartbeat 60s;
    R6.6: lock dengan PID mati di node yang sama langsung diambil alih + retry tiap 30s)
  (*) kredensial: TIDAK PERNAH dikembalikan API — respons hanya `has_access_token`/`has_fonnte_token`.

notifications — field tambahan R6.6 (koleksi Fase 0, JANGAN ganti nama):
  escalation_level    0/absen = belum dieskalasi · 1 = sudah dinaikkan (anti-berulang)
  escalated_to        role tujuan eskalasi ("manager"|"admin")
  escalated_at        ISO waktu eskalasi
  escalation_notif_id FK notifications (anak eskalasi)
  escalation_depth    kedalaman rantai pada notifikasi ESKALASI (1..max_level)
  escalated_from      FK notifications (induk) pada notifikasi ESKALASI
  escalated_from_role role induk saat dieskalasi
  Rantai: sales/warehouse → manager · manager/all → admin · admin = berhenti.

Idempotensi & anti-spam:
  - `create_notification(dedupe_scope="day")` → dedupe_key `<type>:<ref>:<YYYY-MM-DD>`
    ⇒ job dijalankan berkali-kali dalam hari yang sama TIDAK menduplikasi notifikasi.
  - WA hanya untuk severity >= `min_severity` (default `warning`) + dedupe per (kunci, nomor).
  - **R6.6** `delivery_mode="digest"` → pesan per-alert DITEKAN, digabung job `daily_digest`
    (1 pesan/penerima/hari, dedupe `digest:<hari>|<nomor>`); alert `critical` tetap dikirim
    seketika bila `critical_bypass` aktif.
  - MAX_ALERTS_PER_JOB = 40 per run · MAX_PER_RUN eskalasi = 40 (pagar anti-flood).
Endpoints: GET /api/scheduler/jobs · /summary · /runs?job_id&limit · /settings ·
  /digest-preview?role= (R6.6) · PUT /api/scheduler/settings (jobs | wa | escalation) ·
  POST /api/scheduler/jobs/{job_id|all}/run ·
  GET /api/scheduler/wa-outbox?status&limit · POST /api/scheduler/wa-outbox/{id}/retry ·
  POST /api/scheduler/wa-test   (bell: GET /api/notifications · /unread-count · POST .../read · /read-all)
RBAC: permission "scheduler" — admin: view+run+configure · manager: view+run (TANPA configure) ·
  sales/warehouse: tidak ada akses (403). Nav: tab "Penjadwal & Notifikasi" (admin + manager).
Invarian integritas: SCH-1 histori run valid (status/durasi/urutan waktu, error iff gagal) ·
  SCH-2 notifikasi valid & dedupe_key konsisten · SCH-3 alert scheduler idempotent harian
  (tanpa dedupe_key ganda) · SCH-4 outbox ternormalisasi 62xx + tanpa kebocoran kredensial +
  pengaturan provider konsisten · **SCH-5** rantai eskalasi valid (1 eskalasi per induk,
  critical, depth 1..max_level, induk ditandai, tanpa yatim) · **SCH-6** ringkasan harian &
  konfigurasi kanal (maks 1 ringkasan/nomor/hari, isi bergrup, delivery_mode & kebijakan valid).
Invarian PS-21: **INV-PS21-01** dedupe harian job operasional (kunci unik & konsisten) ·
  **INV-PS21-02** ar_due_soon hanya pada offset H-3/H-1/H/H+1 · **INV-PS21-03** jejak dua arah
  restock SO↔PR · **INV-PS21-04** item PR restock menunjuk produk master yang sah.
Jenis notifikasi PS-21 (label FE di components/NotificationCenter.jsx TYPE_LABEL):
  `po_arrival` · `backorder_ready` · `ar_due_soon` · `restock_request`
Seed demo: `scripts/seed_escalation_demo.py` (R6.6) menggeser umur beberapa alert NYATA
  (default 20 jam, dedupe_key disesuaikan) lalu menjalankan job eskalasi agar rantai terlihat.
  `scripts/seed_ar_due_soon_demo.py` (PS-21) menggeser TANGGAL beberapa order berpiutang NYATA
  agar jatuh tempo mendarat tepat di H-3/H-1/H/H+1 (nominal & pelanggan tidak diubah).
⚠️ JANGAN BUAT: `sys_notifications`, `notification_queue`, `alerts`, `wa_messages`,
   `scheduler_jobs`, `job_logs` — pakai `notifications` (sudah ada) + `sys_scheduler_runs` +
   `sys_wa_outbox`. Jadwal job disimpan sebagai override di `system_settings` scope="alerts",
   BUKAN koleksi terpisah.
```

### gl_accounts  [EPIC7-C IMPLEMENTED — Chart of Accounts / Bagan Akun]
Koleksi kanonik `gl_accounts` (prefix `gla_`). Master bagan akun double-entry.
Normal balance: asset & expense = debit; liability, equity, income = credit.
```
Collection:  gl_accounts                  Prefix: gla_
Router:      routers/gl.py
Service:     services/gl_service.py
Component:   features/finance/ChartOfAccounts.jsx
Key Fields:
  id                string  prefix "gla_"
  code              string  UNIK, mis. "1-1100"
  name              string  nama akun
  type              enum    asset | liability | equity | income | expense
  normal_balance    enum    debit | credit (derived dari type)
  parent_code       string  FK gl_accounts.code (hierarki; "" = root)
  is_postable       bool    true = akun detail (boleh dijurnal); false = header
  is_active         bool
  system            bool    akun baku — tak boleh dihapus (boleh dinonaktifkan)
  currency          string  default IDR
  created_at / updated_at
ℹ️ Endpoint: GET/POST /api/gl/accounts, PATCH/DELETE /api/gl/accounts/{code},
  GET /api/gl/accounts/{code}/ledger. RBAC: permission "accounting" (admin/manager).
⚠️ JANGAN BUAT: accounts, coa, chart_of_accounts, akun (sebagai koleksi).
```

### journal_entries  [EPIC7-C IMPLEMENTED — General Ledger / Jurnal Umum]
Koleksi kanonik `journal_entries` (prefix `je_`). Jurnal double-entry SEIMBANG
(Σdebit == Σkredit). Auto-posting idempotent diturunkan dari SSOT
(`sales_orders` → pengakuan pendapatan; `cash_transactions` → mutasi kas) via
`POST /api/gl/sync` (source_type + source_id mencegah double-post).
```
Collection:  journal_entries              Prefix: je_
Router:      routers/gl.py
Service:     services/gl_service.py
Component:   features/finance/GeneralLedger.jsx
Key Fields:
  id                string  prefix "je_"
  number            string  JE-NNNNN (number series)
  date              string  ISO tanggal jurnal
  description       string
  source / source_type  enum  manual | sales_order | cash_transaction
  source_id         string  FK dokumen sumber ("" utk manual)
  source_label      string  label dokumen (mis. SO-0007, CASH-00001)
  lines             array   [{account_code, account_name, debit, credit, description}]
  total_debit       float   == total_credit (invarian)
  total_credit      float
  status            enum    posted | void (hanya manual yg boleh di-void)
  entity_id         string  FK entities.id
  created_by / created_at / updated_at
Laporan derived: Neraca Saldo (GET /api/gl/trial-balance) & Buku Besar per-akun
  (GET /api/gl/accounts/{code}/ledger). KPI: GET /api/gl/summary.
ℹ️ Endpoint: GET/POST /api/gl/journal, GET /api/gl/journal/{id},
  POST /api/gl/journal/{id}/void, POST /api/gl/sync. RBAC: permission "accounting".
⚠️ JANGAN BUAT: journals, general_ledger, gl, jurnal, ledger (sebagai koleksi).
```







### customers
```
Collection:  customers
Router:      routers/customers.py
Schema:      schemas.py → CustomerCreate, CustomerAddress
Component:   CustomerPanel.jsx, AdminView.jsx (tab Customer)
Key Fields:
  id          string   prefix "cust_"
  code        string   format: "CUST-NNNN"
  name        string
  pic_name    string   nama contact person
  phone       string
  email       string
  type        enum     Retailer | Wholesaler | Boutique
  city        string
  status      enum     active | inactive
  addresses   list     [{id, label, recipient_name, phone, city, address, is_primary}]
  npwp, credit_limit, sales_pic, entity_id   (sudah ada)
  --- CRM-LITE [PROPOSED KN_17] ---
  assigned_sales_id  string  FK users (salesperson pemilik) — WAJIB (kunci manajemen; sales kelola miliknya)
  segment            enum    Retail|Wholesale|Distributor|VIP  (KLASIFIKASI saja, BUKAN penentu harga)
  tags               list    [string]
  contacts           list    [{name, role, phone, email, is_primary}]
  lot_policy         enum    prefer_single|strict_single|allow_mixed (default prefer_single; KN_15)
  enforce_single_dye_lot  bool  P0-4 — bila true → alokasi SO dipaksa 1 dye_lot (dye_lot_strict)
  payment_profile    object  {allowed_methods:[kontan|tunai|tempo|dp|bertahap], default_method,
                              term_days, dp_percent, installment:{count,interval_days}}
  credit             object  {credit_limit, ar_outstanding(derived), overdue_amount(derived),
                              status: active|warning|blocked}
  customer_group_id  string? penghubung customer sama lintas-entitas (DISIAPKAN, default kosong) [KN_17 S38]
  status      enum     active | inactive | blocked
  created_by  string
  created_at  string

⚠️ scoped entity_id (customer terpisah per entitas; customer sama boleh lintas-entitas; kunci=assigned_sales_id)
⚠️ RBAC row-level: role=sales hanya lihat/kelola customer assigned_sales_id==dirinya (enforce backend)
⚠️ JANGAN BUAT: clients, buyers, pembeli, pelanggan_toko, crm_customers
```

### warehouses
```
Collection:  warehouses
Router:      routers/warehouses.py
Schema:      schemas.py → WarehousePayload
Component:   AdminView.jsx (tab Warehouse)
Key Fields:
  id          string   prefix "wh_" (contoh: wh_jakarta, wh_bandung)
  code        string   format: "WH-XXX"
  name        string
  city        string
  lat, lng    float    koordinat GPS
  active      bool
  zones       list     [{id, name, racks: [{id, name, bins: [{id, code, capacity}]}]}]
  created_at  string

⚠️ Hierarchy: Zone → Rack → Bin
⚠️ JANGAN BUAT: gudang, depot, storage_location sebagai collection terpisah
⚠️ Zone/Rack/Bin adalah EMBEDDED dalam warehouse document
```

### uoms
```
Collection:  uoms
Router:      routers/uoms.py
Schema:      schemas.py → UOMPayload
Component:   AdminView.jsx (tab UOM)
Default UOMs:
  uom_meter  → MTR (length, precision 2)
  uom_yard   → YRD (length, precision 2)
  uom_roll   → RLL (volume, precision 0)
  uom_pcs    → PCS (count, precision 0)
Key Fields:
  id, code, name, base_type (length|volume|weight|count), precision, status

⚠️ JANGAN BUAT: satuan, unit_ukur, measurement
```

### sales_orders
```
Collection:  sales_orders
Router:      routers/sales_orders.py
Schema:      schemas.py → SalesOrderCreate, SalesOrderItemIn
Component:   SalesPortal.jsx, OrdersView.jsx, CartPanel.jsx
Status Lifecycle:
  reserved → waiting_approval → approved → confirmed → dispatched → done
  (cancelled tersedia di setiap stage)
Key Fields:
  id          string   prefix "so_"
  number       string  format: "SO-NNNNN"  (FIELD = "number", BUKAN "order_number")
  customer_id  string  FK → customers.id
  customer_name string SNAPSHOT (denormalized)
  items        list    [{product_id, product_name, sku, quantity, unit, price, subtotal,
                          discount_percent, discount_amount, line_total}]
                        (FIELD item = "quantity" & "price"; BUKAN "qty"/"unit_price")
                        subtotal = price×quantity (GROSS, invarian); line_total = subtotal−discount_amount
  allocations  list    [{warehouse_id, warehouse_name, warehouse_city, product_id, quantity}]
                        SNAPSHOT fulfillment (top-level, dipakai render dokumen)
  status       enum    (lihat lifecycle di atas)
  total_amount float    = Σ items.subtotal (GROSS — invarian verify_data_integrity L4)
  # Fase 1B — breakdown diskon + PPN (field TERPISAH agar total_amount tetap GROSS):
  items_discount_total   float
  order_discount_percent float   order_discount_amount float   discount_total float
  net_subtotal float   = total_amount − discount_total (= DPP base)
  dpp float   ppn_rate float   ppn_mode enum(excluded|included)   is_pkp bool
  ppn_amount float   grand_total float  (= yang dibayar customer)
  payment_term_code string   payment_term_name string   payment_status enum(pending|paid_partial|paid)
  # Fase 1B — approval dinamis (dari approval_rules):
  approval_required bool   required_approval_role string|null   approval_amount float
  sales_name   string
  # PS-21 — permintaan repeat/restock dari layar order (jejak ke PR; TANPA koleksi baru)
  restock_requests list  [{pr_id, pr_number, status, items[{product_id, product_name,
                          quantity, unit}], total_est_amount, requested_by, requested_by_id,
                          requested_at, reason}]
  last_restock_note string  ringkasan permintaan terakhir (untuk tampilan cepat)
  ar_demo_offset int?   HANYA data demo — ditulis scripts/seed_ar_due_soon_demo.py
  shipping_address_id string
  reservation_expires_at string  UTC ISO
  created_at, updated_at string

⚠️ JANGAN BUAT: orders, customer_orders, so_list, penjualan
⚠️ Stock reservation terjadi di inventory_balances SAAT order dibuat
⚠️ Dispatch flow: sales_orders.confirm → wms.outbound_from_order → outbound_picking.dispatch
⚠️ Fase 1B: pricing dihitung services/config_service.compute_order_pricing (PPN ikut PKP entitas);
   approval via evaluate_approval + role_satisfies. INVARIAN: total_amount & item.subtotal tetap GROSS.
```

### inventory_lots  [FASE C IMPLEMENTED — Lot KELAS SATU + Genealogi + Recall (D-10/D-26/D-27)]
```
Collection:  inventory_lots           Prefix: lot_
Router:      routers/lots.py                  Schema: schemas_lots.py
Services:    services/lot_service.py        (SSOT: nomor, agregat, split/merge/rework, kebijakan)
             services/lot_trace_service.py  (silsilah · recall · label/QR)
             services/lot_migration.py      (backfill IDEMPOTEN — dipakai bootstrap, seed, CLI)
Migrasi:     backend/scripts/migrate_fase_c_lots.py  (--dry-run)
Component:   features/inventory/lots/LotsView.jsx + LotParts.jsx + LotDetailPanel.jsx
             + LotGenealogyTree.jsx + LotRecallPanel.jsx + LotActionModals.jsx + lotApi.js
Nav:         Gudang → Stok & ATP → tab "Lot & Silsilah" (view: admin/manager/warehouse/sales;
             mutasi: inventory:update; kebijakan: admin/manager)
Key Fields:
  id                string  prefix "lot_"
  lot_number        string  UNIK — "KSC/LOT-YYMM-####" (per entitas · D-26; deletion-safe)
  entity_id         string  entitas penomoran (dipakai sequence number_sequences)
  owner_entity_id   string  PEMILIK lot (selaras inventory_rolls · KN_15) → SCOPED
  product_id, sku, product_name, unit, warehouse_id   (snapshot ringan utk tampilan/label)
  stage, fabric_type  enum  snapshot domain Fase A (roll_domain_snapshot)
  source            enum    receiving|makloon|production|split|merge|rework|return|transfer|
                            adjustment|migration|manual      (registry enum `lot_source`)
  source_ref        object  {type,id,number} → wms_task|purchase_order|makloon_order|
                            work_order|lot|sales_return|legacy_roll|manual
  supplier_lot      string  nomor lot versi supplier (titik input GR & inspeksi QC)
  dye_lot           string  batch warna; shade_ref string (referensi shade/Pantone)
  supplier_id, supplier_name
  process           object  {process_type, partner_id, partner_name}  (rework/makloon)
  parent_lot_ids    array   genealogi HULU (dua arah, WAJIB bebas siklus)
  child_lot_ids     array   genealogi HILIR
  lot_status        enum    karantina|released|in_process|hold_shade|rework  (registry `lot_status`)
  status_history    array   {status, status_before, reason, actor, at}
  roll_count, active_roll_count, qty_initial, qty_remaining, qty_available, status_breakdown
                            ← PROYEKSI: selalu recompute dari inventory_rolls (TIDAK pernah $inc)
  legacy_lot_codes  array   jejak string lot lama (mis. "LOT-001", "LOT-MIGRATED")
  merged_into       string? diisi bila lot digabung ke lot lain (jejak audit)
  note, created_at, updated_at, created_by, created_by_name
Index:  lot_number · (owner_entity_id, created_at) · (product_id, owner_entity_id) ·
        (source_ref.id, product_id) · legacy_lot_codes · dye_lot · supplier_lot ·
        lot_status · parent_lot_ids · child_lot_ids
Invarian: INV-LOT-01..06 (scripts/verify_data_integrity.py → L4-LOT)
Field baru pada koleksi lain: inventory_rolls.lot_id + .supplier_lot ·
        inventory_movements.lot_id · wms_tasks.lot_ids/lot_numbers/supplier_lot/lot_warnings ·
        mfg_work_orders.output_lot_id/input_lot_ids · makloon_orders.steps[].lots[].lot_id
LARANGAN NAMA: jangan buat `lots`, `dye_lots`, `batches`, `stock_lots` — pakai `inventory_lots`.
```
```
Collection:  uom_conversion_rules   Prefix: uomr_
Router:      routers/uom_conversions.py      Schema: schemas_uom.py
Services:    services/uom_rules_service.py (registry + toleransi + JEJAK konversi)
             services/uom_service.py        (MATEMATIKA konversi — SATU tempat, R3)
Component:   features/admin/uom/UomConversionView.jsx + UomConversionParts.jsx
             components/UomInputConvert.jsx · components/UomConvertHint.jsx
             hooks/useUomConversions.js   (SSOT FE — komponen dilarang hardcode satuan, R7)
Nav:         Produk & Harga → Konversi Satuan (admin & manager; ubah butuh izin uom:update)
Key Fields:
  id            string  prefix "uomr_"
  from_unit     string  kode satuan asal (ternormalisasi: "yd" → "yard", "pcs" → "piece")
  to_unit       string  kode satuan tujuan
  kind          enum    fixed (faktor fisika/standar) | pack (ukuran kemasan roll/bal/cone/box)
                        | formula (lintas dimensi, butuh spesifikasi produk)
  factor        float   > 0 untuk fixed/pack (1 from_unit = factor × to_unit); 0 untuk formula
  formula       enum?   gsm_width  (kg = meter × GSM × lebar ÷ 1000 — KN_18 §3.1)
  dimension     enum    length | weight | count | area | cross
  label, note   string  label ringkas + catatan user
  status        enum    active | inactive   (SATU aturan aktif per pasangan from→to)
  source        enum    standard (di-seed migrasi/bootstrap) | user
  created_by, created_at, updated_by, updated_at
Endpoints:   GET  /api/uom-conversions/catalog   (katalog satuan + jenis + formula + setting)
             GET  /api/uom-conversions/rules?status&dimension&kind
             POST /api/uom-conversions/rules · PATCH /api/uom-conversions/rules/{id}
             POST /api/uom-conversions/rules/{id}/status?status=active|inactive
             GET/PUT /api/uom-conversions/settings      (toleransi — configurable)
             POST /api/uom-conversions/convert          (hasil + JEJAK; dipakai FE & dokumen)
             POST /api/uom-conversions/check-variance   (level ok|warn|block)
             GET  /api/uom-conversions/usage?limit      (jejak konversi dokumen — audit D-07)
Urutan resolusi faktor (dikunci server):
  satuan sama → uoms.factor_to_base → products.uom_conversions[] → aturan GLOBAL aktif
  → formula GSM × lebar → 1-hop lewat satuan dasar → HTTP 400 (tidak pernah diam-diam 1:1)
system_settings scope="uom" (kebijakan toleransi, dapat diubah user tanpa deploy):
  warn_pct (default 2) · block_pct (default 5) · allow_override (bool) ·
  precision (0–6) · require_trail (bool) · updated_at · updated_by
JEJAK konversi (D-07) disimpan sebagai objek `uom_trail` pada:
  purchase_orders.items[] · purchase_requisitions.items[] · wms_tasks (GR)
  {doc_uom, doc_qty, base_uom, base_qty, factor, source, rule_id, formula, path[],
   context, converted_at, source_migrated?}
  source ∈ same_unit | fixed_uom | product_override | global_rule | formula_gsm_width | hop_base
wms_tasks (GR) tambahan Fase B:
  conversion_variance {level(ok|warn|block), variance_pct, expected_kg, actual_kg, factor,
                       message, override_reason?, overridden?} · needs_review bool
Invarian: INV-UOM-01 aturan sah & satu aktif per pasangan · INV-UOM-02 jejak konsisten
  (doc_qty × factor == base_qty == quantity_base) · INV-UOM-03 toleransi sah
  (0 < warn ≤ block ≤ 100, precision 0–6) · INV-UOM-04 selisih di luar toleransi ditandai
  needs_review & yang di atas blokir wajib beralasan.
Migrasi:  backend/scripts/migrate_fase_b_uom.py (idempoten; --dry-run tersedia)
⚠️ JANGAN BUAT: `uom_conversions` (koleksi), `unit_conversions`, `konversi_satuan`,
   tabel konversi per kontrak/mitra — keputusan pemilik: registry GLOBAL + override
   master produk. Faktor per produk TETAP di `products.uom_conversions[]`.
⚠️ JANGAN menghitung faktor di frontend — pakai POST /api/uom-conversions/convert.
```

### invoices
```
Collection:  invoices
Router:      routers/invoices.py
Schema:      schemas.py → PaymentSimulationCreate
Key Fields:
  id, number ("INV-NNNNN-NN"), order_id, order_number, customer_id, customer_name, entity_id,
  amount (= grand_total order), status (paid), method, created_by, created_at
  # Fase 1B — snapshot pajak untuk Faktur/Invoice:
  total_amount, discount_total, net_subtotal, dpp, ppn_rate, ppn_mode, ppn_amount, grand_total,
  payment_term_code, payment_term_name

⚠️ SIMULATED payment — belum real gateway
⚠️ amount default = order.grand_total (server-authoritative); jangan embed _id sub-dok (RC ObjectId)
⚠️ JANGAN BUAT: bills, tagihan, faktur sebagai collection terpisah
```

### inventory_balances
```
Collection:  inventory_balances
Router:      routers/inventory.py
Component:   InventoryStockView.jsx
Key Fields:
  id           string   prefix "bal_"
  product_id   string   FK → products.id
  warehouse_id string   FK → warehouses.id
  owner_entity_id string FK → business_entities.id   [IMPLEMENTED Fase 0.5 — kepemilikan, 3-key]
  on_hand_qty  float    total fisik (= Σ bucket fisik)
  available_qty / reserved_qty / committed_qty / picked_qty / packed_qty / quarantine_qty / blocked_qty / damaged_qty  float (bucket fisik)
  on_order_qty / in_transit_inbound_qty / in_transit_transfer_qty / in_transit_intercompany_qty / in_transit_sales_qty  float (pipeline/transit)
  owned_qty / incoming_qty / atp_qty  float (derived)
  in_transit_qty float  legacy alias (= Σ transit)
  updated_at   string

⚠️ UNIQUE per (product_id + warehouse_id + owner_entity_id)  [IMPLEMENTED Fase 0.5]
   Balance = PROYEKSI/cache yang diturunkan dari inventory_rolls (SSOT fisik) via roll_service.rebuild_balance().
   [KN_15 §3.4] Bucket DETAIL: fisik (available/reserved/committed/picked/packed/quarantine/blocked/damaged→on_hand)
   + transit (on_order/in_transit_*) + derived (owned/incoming/atp). Status: IMPLEMENTED Fase 0.5.
⚠️ JANGAN pindahkan stok dengan update langsung — selalu buat inventory_movements + rebuild_balance
⚠️ JANGAN BUAT: stock, stok, stock_levels, inventory_count, stock_units, rolls (lepas)
```

### inventory_rolls  [IMPLEMENTED Fase 0.5 — koleksi baru, SSOT fisik]
```
Collection:  inventory_rolls            Prefix: roll_
Router:      routers/inventory.py (atau routers/rolls.py saat coding)
Component:   InventoryStockView.jsx (+ stock-breakdown matrix), SalesPortal (visibilitas)
Status:      DRAFT / PROPOSED (belum ada di DB/kode). Lihat KN_15.
Key Fields:
  id               string   prefix "roll_"  (1 dokumen = 1 roll fisik)
  product_id       string   FK → products.id  (katalog SHARED)
  owner_entity_id  string   FK → business_entities.id  (KEPEMILIKAN — wajib utk internal)
  ownership_type   enum     internal | supplier_consignment | reseller_consignment
                            (DEFAULT internal; konsinyasi DISIAPKAN, default OFF — KN_16 G1)
  consignor_ref    object?  {type: supplier|customer, id, name}  (bila konsinyasi)
  warehouse_id     string   FK → warehouses.id  (LOKASI gudang — netral)
  bin_id           string   lokasi detail (Zone→Rack→[Level]→Bin)
  lot              string   dye-lot generik (WAJIB) — penentu warna/celup (gate: harus terisi)
  dye_lot          string   P0-4 — dye lot AKTUAL tekstil (default = `lot` agar backward-compatible)
  batch            string   batch produksi/pembelian
  roll_no          string   nomor/serial roll fisik (label)
  length_initial   float    panjang awal aktual (catch weight)
  length_remaining float    sisa panjang (0 ≤ x ≤ length_initial)
  unit             string   base unit (meter|yard|...)
  grade            enum     [FASE A · D-01] A | A1 | A2 | B | BS  (rank 1..5; BS = barang sortir)
                            ⚠️ diubah HANYA lewat services/grade_service.py (PS-09)
  grade_source     enum?    [FASE A · D-23] qc_inspection | quarantine_release | manager_override | migration
  grade_updated_at string?  [FASE A] waktu perubahan grade terakhir
  grade_history    list     [FASE A · PS-09] [{grade_before, grade_after, rank_before, rank_after,
                            direction, source, source_label, reason, changed_by, changed_by_id,
                            changed_by_role, changed_at}] — WAJIB terisi setiap perubahan grade
  stage            enum?    [FASE A · PS-01] snapshot stage produk saat roll dibuat
  fabric_type      enum?    [FASE A · PS-02] snapshot woven|knit dari master produk
  qc_grade         string   P0-4 — grade hasil keputusan QC (saat accept; = grade)
  defects          list     P0-4 — profil cacat tekstil [string] (mis. ["belang","noda"])
  status           enum     on_order|in_transit_inbound|receiving|quarantine|available|reserved|
                            committed|picked|packed|cross_dock|in_transit_sales|sold|
                            in_transit_transfer|in_transit_intercompany|blocked|damaged|returned|scrapped
  tracking_mode    enum     rfid | barcode | document | manual   (stok visible TANPA RFID — KN_15 §7B)
  earmarked_for    object?  {type: sales_order|special_order, id}  (pegging supply↔demand)
  location_type    enum     warehouse_bin|transit_in|transit_out|cross_dock|drop_ship|transit_transfer
  reserved_ref     object   {type: sales_order|transfer, id}
  unit_cost        float?   HPP final per BASE unit (P0-5: base + Σ landed cost; NULLABLE bila tak ada harga PO)
  base_unit_cost   float?   P0-5 — HPP dasar per unit dari harga PO saat GR (sebelum landed cost)
  landed_cost_total float   P0-5 — Σ biaya landed cost yang dialokasikan ke roll ini (audit; default 0)
  landed_cost_refs list     P0-5 — daftar voucher landed cost (LCV-NNNNN) yang sudah di-apply
  acquired         object   {via: po|transfer|initial|adjustment|return, ref_id, date}
  grade            string?  Grade tekstil (A|A+|B|C|BS) — P0-4 / di-set objektif oleh inspeksi 4-Point (6.2)
  defects          list     profil cacat; P0-4 free-text atau 6.2 [{point_value 1..4, count, note}]
  inspection       object?  Fase 6.2 — {points, grade, defects[], gsm_actual?, width_actual?, thresholds, inspected_by, inspected_at}
  rfid_tag_id      string?  FK → rfid_tags (Fase 5)
  is_remnant       bool     true bila roll = sisa potongan (BS)
  created_at, updated_at, created_by, created_by_name

⚠️ SSOT fisik stok. inventory_balances = PROYEKSI yang di-rebuild dari sini.
⚠️ Reservasi terjadi di LEVEL ROLL (atomic find_one_and_update status available→reserved).
⚠️ Penjualan owner-scoped: roll hanya boleh dijual entitas pemiliknya (owner_entity_id == SO.entity_id).
⚠️ JANGAN BUAT: stock_units, rolls (lepas), stock — gunakan inventory_rolls (namespace inventory_*).
```

### inventory_movements
```
Collection:  inventory_movements
Router:      routers/inventory.py
Component:   InventoryStockView.jsx (tab Ledger)
Movement Types:
  initial_stock | inbound_receiving | outbound_dispatch |
  transfer_out | transfer_in | cycle_count_adjustment | reservation | release_reservation
  [PROPOSED KN_15] + ownership_transfer_out | ownership_transfer_in (inter-company, owner berubah)
  [PROPOSED KN_15] + remnant_created | quarantine_in | quarantine_out | scrap
Key Fields:
  id, product_id, warehouse_id, movement_type, quantity, unit,
  batch, lot, roll_id, source_document, timestamp
  [PROPOSED KN_15] + owner_entity_id (wajib), roll_id (FK inventory_rolls),
                     from_owner_entity_id & to_owner_entity_id (utk ownership_transfer)

⚠️ APPEND-ONLY — tidak pernah update/delete movement yang sudah ada
⚠️ JANGAN BUAT: stock_history, gerakan_stok, stock_log
```

### system_settings  [Fase 1A IMPLEMENTED — Configuration Foundation]
```
Collection:  system_settings          Prefix: set_
Router:      routers/settings.py       Service: services/config_service.py
Component:   SettingsPanel.jsx (Admin → Pengaturan)
Key Fields:
  id, scope ("global" | entity_id),
  tax       {ppn_rate, ppn_mode(excluded|included), efaktur_enabled, is_pkp(derived)}
  finance   {base_currency, fiscal_year_end_month, default_payment_term_code}
  sales     {quotation_enabled, allow_partial_shipment, allow_order_discount, allow_item_discount}
  inventory {default_uom, min_cut_qty, intercompany_transfer_required}
  created_at, updated_at

⚠️ Effective settings = global di-override per-entitas (config_service.get_effective_settings).
⚠️ SEMUA configurable — JANGAN hardcode PPN/term/currency di kode.
⚠️ JANGAN BUAT: settings, config, configuration (lepas) — gunakan system_settings.
```

### payment_terms  [Fase 1A IMPLEMENTED]
```
Collection:  payment_terms             Prefix: pterm_
Router:      routers/settings.py
Component:   SettingsPanel.jsx (tab Term Pembayaran)
Key Fields:
  id, code (UNIQUE), name, type (cash|credit|dp|installment),
  net_days, dp_percent, installment_count, sort, active, created_at, updated_at

⚠️ JANGAN BUAT: terms, payment_term (singular) — gunakan payment_terms.
```

### product_lines  [FASE L IMPLEMENTED 2026-08-18]
```
Collection:  product_lines             Prefix: pline_
Jenis:       MASTER BERLAPIS global → badan usaha (entity_id="all" = global, override PT menang)
Router:      routers/entity_masters.py  (`/api/entity-masters/product-lines`)
Service:     services/entity_master_service.py (MASTERS["product-lines"])
             services/master_registry.py  → nilai HIDUP untuk `/api/enums` (enum `product_line`)
             services/line_scope.py       → pagar baca/tulis per akun (`users.allowed_line_codes`)
Component:   features/settings/masters/EntityMastersView.jsx + masters/masterFieldsConfig.js
             components/LineFilter.jsx (chip penyaring lini — dipakai 12 layar)
Key Fields:
  id                   string  prefix "pline_"
  entity_id            string  "all" = GLOBAL (INHERITED_GLOBAL_VALUES) | ent_xxx = override PT
  code                 string  UNIK per lapisan — woven | knit | printing | (bisa ditambah)
  name                 string  nama untuk manusia (mis. "Woven (Tenun)")
  sort                 int     urutan tampil di chip & dropdown
  active               bool
  fabric_type_required enum    "" | woven | knit — INV-LINE-02: produk ber-lini ini WAJIB
                               ber-`fabric_type` sama. `printing` SENGAJA "" (kain print
                               bisa woven maupun knit).
  measure_unit_default string  USULAN satuan saat membuat produk/PO (yard|kg|panel).
                               BUKAN sumber satuan kendali (itu `fabric_type.control_uom`
                               + `products.base_unit`) — kalau dipakai sebagai sumber,
                               FASE U melahirkan satuan ketiga.
  stage_sequence       list    urutan tahap untuk papan PO & SPK makloon (kode master FASE T)
  sample_types_default list    usulan jenis sampling saat membuat permintaan sample (FASE S)
  notes                string

Pemakai `line_code` (snapshot, bukan join):
  products.line_code · users.allowed_line_codes · inventory_rolls/inventory_lots
  (lewat domain_registry.roll_domain_snapshot) · wms_tasks · md_specs · md_samples ·
  design_gallery · makloon_orders · dan baris dokumen: sales_orders/purchase_orders/
  purchase_requisitions/warehouse_transfers/sales_returns/purchase_returns/
  interco_transactions/special_orders/internal_requests/rfqs → `items[].line_code`
  + turunan `line_codes[]` di kepala dokumen.

⚠️ TURUNAN: `line_codes[]` WAJIB == kumpulan `items[].line_code`. Dihitung SATU pintu
  `line_scope.stamp_doc()` / `codes_from_items()`; dijaga gate INV-LINE-01.
⚠️ SNAPSHOT: mengubah lini master produk TIDAK mengubah baris dokumen yang sudah terbit.
⚠️ KOSONG BUKAN PELANGGARAN: dokumen/produk tanpa lini TETAP terlihat semua akun
  (data lama) — pagar hanya menyembunyikan lini LAIN, bukan yang belum bergolong.
⚠️ JANGAN BUAT: lines, product_line (singular), fabric_lines — gunakan product_lines.
⚠️ JANGAN memakai `line_code` di rumus/konversi apa pun — itu tugas `fabric_type`.
Migrasi: scripts/migrate_lini_produk.py (idempotent · --dry-run · laporan
  docs/LAPORAN_MIGRASI_LINI_PRODUK.md untuk dikoreksi pemilik lewat layar).
```

### process_stages  [FASE T IMPLEMENTED 2026-08-19]
```
Collection:  process_stages            Prefix: pstg_
Jenis:       MASTER BERLAPIS global → badan usaha (entity_id="all" = global, override PT menang)
Router:      routers/entity_masters.py  (`/api/entity-masters/process-stages`)
             routers/makloon_orders.py  (`/api/process-stages`, `/api/process-stages/for-line/{code}`)
Service:     services/entity_master_service.py (MASTERS["process-stages"])
             services/master_registry.py  → nilai HIDUP untuk `/api/enums` (enum `process_stage`)
                                            + `process_types()` (benih ∪ nilai master)
             services/makloon_order_service.py → `_resolve_stage()` & `_resolve_material_flow()`
Component:   features/settings/masters/EntityMastersView.jsx + masters/masterFieldsConfig.js
             features/purchasing/MakloonOrderCreateModal.jsx (pemilih TAHAP langkah SPK)
             features/purchasing/MakloonOrderDetailPanel.jsx (aksi Issue / Terima / Catat Jasa)
Key Fields:
  id                    string  prefix "pstg_"
  entity_id             string  "all" = GLOBAL (INHERITED_GLOBAL_VALUES) | ent_xxx = override PT
  code                  string  UNIK per lapisan — benang | tenun | rajut | pfp | pfd |
                                celup | screen | printing | proofing | inspect | (bisa ditambah)
  name                  string  nama untuk manusia
  kind                  enum    material | makloon | sampling | inspection
                                (`process_stage_kind`; hanya makloon & sampling boleh jadi
                                 langkah SPK — lihat `spk_step` di registry)
  seq                   int     urutan papan PO & dropdown langkah
  active                bool
  applies_to_lines      list    KOSONG = SEMUA lini (aturan yang sama dengan
                                `users.allowed_line_codes` FASE L — jangan dijadikan wajib-isi)
  needs_vendor          bool    langkah dikerjakan mitra. SPK tanpa mitra hanya DIPERINGATKAN
                                (keputusan pemilik 3b); gate INV-DOMAIN-06 aturan E memerah
                                bila TIDAK ADA mitra terdaftar untuk prosesnya
  process_type          enum    sambungan ke `domain_registry.PROCESS_TYPES` (mesin tarif &
                                estimasi). KOSONG untuk tahap non-makloon
  target_use            enum    "" | dye | print — pemilah `pre_treatment` (PFD vs PFP)
  changes_stage         bool    FALSE = tahap TIDAK mengubah kain → mesin memaksa susut 0,
                                yield 1, qty keluar = qty masuk, `estimate.method="no_transform"`
  from_stage/to_stage   enum    tahap KAIN (`stage`). Bila `changes_stage=true`, pasangan
                                (from, process_type, to) WAJIB ada di STAGE_TRANSITIONS
  tariff_basis_default  enum    usulan basis tarif saat membuat langkah (`tariff_basis`)
  material_flow         enum    moves | service_only | either  ← APAKAH KAIN BERGERAK
                                moves        = kain dikirim ke mitra & kembali (jalur
                                               Issue → Terima, biaya masuk HPP kain)
                                service_only = JASA MURNI, kain tidak bergerak (jalur
                                               "Catat Jasa"; tidak ada roll yang lahir)
                                either       = boleh dua-duanya, dipilih per langkah SPK
  material_flow_default enum    moves | service_only — dipakai bila langkah SPK tidak memilih
                                (hanya berlaku saat `material_flow="either"`); pilihannya
                                DICATAT di `estimate.explain[]`, bukan ditebak diam-diam

Pemakai:
  makloon_orders.steps[].stage_code + stage_label · stage_kind · stage_seq ·
  stage_from_stage · stage_to_stage · stage_source · changes_stage · needs_vendor ·
  material_flow · material_flow_source
  product_lines.stage_sequence (urutan tahap per lini kerja)

ALIRAN UANG langkah `service_only` (FASE T — tiga pintu, tidak boleh ada pintu keempat):
  1. dicatat  → vendor_bill (`service_only: true`) + Dr 1-1350 WIP / Cr 2-1100 Hutang,
                lalu `makloon_orders.service_absorption_pending` bertambah
  2. diserap  → langkah kain berikutnya menambahkannya ke `wip_total` saat Terima Hasil
                → mendarat di HPP kain (`steps[].absorbed_service_value`)
  3. tak terserap → SPK selesai tanpa langkah kain sesudahnya:
                Dr 5-1200 Beban Jasa Makloon Tak Terserap / Cr 1-1350 WIP
                (`costing.service_unabsorbed`)
  Dijaga gate INV-MKO-07: Σ jasa murni == Σ diserap + menggantung + dibebankan.

⚠️ DUA KOSAKATA, JANGAN DICAMPUR: `process_stages` = LANGKAH KERJA (daftar pemilik) ·
  `stage` = KEADAAN KAIN · `process_type` = JENIS PROSES. Tahap MENUNJUK ke dua yang
  terakhir, tidak menggantikannya.
⚠️ `changes_stage=false` BUKAN "tahap tidak penting": ia punya mitra, tarif & tagihan
  sendiri. Yang tidak berubah hanyalah KAINNYA.
⚠️ JANGAN BUAT: process_steps, stages, makloon_stages — gunakan process_stages.
⚠️ Langkah SPK sebelum FASE T tidak punya `stage_code`; `_resolve_stage()` mencarinya
  dari `process_type` (+`target_use`) supaya angka SPK lama TIDAK bergeser.
Gate:    scripts/guardrails/verify_master_stages.py (INV-DOMAIN-06, ber-`--self-test`)
Migrasi: scripts/migrate_process_stages.py (idempotent · --dry-run = hasil sungguhan ·
  hanya MENAMBAH field turunan; `estimate`/`tariff*`/nilai HPP tidak disentuh)
```

### approval_rules  [Fase 1A IMPLEMENTED]
```
Collection:  approval_rules            Prefix: aprule_
Router:      routers/settings.py       Service: config_service.evaluate_approval()
Component:   SettingsPanel.jsx (tab Matriks Approval)
Key Fields:
  id, doc_type (sales_order|purchase_order|transfer|discount), entity_id ("all"|entity_id),
  min_amount, max_amount (null = tak terhingga), required_role ("" = tanpa approval),
  is_percent (utk discount), sort, active, created_at, updated_at

⚠️ Matriks CONFIGURABLE menyesuaikan flow. Rule entitas-spesifik diutamakan, fallback "all".
⚠️ JANGAN BUAT: approval_matrix, approvals (lepas) — gunakan approval_rules.
FASE F-6 (2026-08-17): koleksi ini **TETAP HIDUP**. Rute CRUD-nya kini
  `routers/approval_rules.py` (+ `services/approval_service.py`), layar
  Pengaturan → "Aturan Persetujuan" (`features/settings/ApprovalRulesSettings.jsx`).
  Penilai ambang yang BERLAKU hanya `config_service.evaluate_approval()` /
  `build_approval_chain()` (dipakai `routers/sales_orders.py` & `routers/purchase_orders.py`);
  penilai kembar `approval_service.check_approval_required()` DIHAPUS agar tak ada dua pendapat.
```

### approval_requests  [DIPENSIUNKAN FASE F-6 (2026-08-17) — JANGAN DIPAKAI LAGI]
```
Collection:  approval_requests         Prefix: appreq_        STATUS: RETIRED
Router:      (DIHAPUS — dulu routers/approval_requests.py)
Alasan pensiun (semuanya TERUKUR, bukan pendapat):
  · `create_approval_request()` NOL pemanggil → koleksi selalu kosong (0 dok), sementara
    `POST /approval-requests/{id}/approve|reject` ADA & izin `approval.approve` dipegang
    admin+manajer → wewenang di kertas tanpa satu pun dokumen yang bisa diputuskan.
    (KPI beranda yang berbohong 0-padahal-17 lahir dari koleksi mati ini — lihat F-3.)
  · NOL pemakai di layar: tak satu pun berkas `frontend/src` memanggil `/approval-requests`.
  · Menghidupkannya MELANGGAR arsitektur: setiap persetujuan nyata diputuskan di endpoint
    dokumennya sendiri (Pusat Persetujuan sengaja read-only) → mesin generik akan menjadi
    JALUR PENULISAN STATUS KEDUA untuk dokumen yang sama.
  · Endpointnya membaca tanpa saringan badan usaha (pada `get` bahkan `resolve_scope_ids()`
    dihitung lalu tak dipakai) → pagar multi-PT bocor pada fitur yang tak pernah dipakai.
Gantinya: 14 antrean keputusan NYATA didaftarkan di
  `services/approval_backlog_service.QUEUES` (transfer gudang · kontrabon verifikasi/
  persetujuan/sengketa · permintaan internal · retur antar-PT · tagihan supplier · biaya
  masuk · uang muka + pertanggungjawaban · klaim makloon · buka periode · cuti · lembur),
  dijaga gate **INV-APPR-01** (`scripts/guardrails/verify_approval_queues.py`).
⚠️ JANGAN MEMBUAT ULANG mesin generik tanpa produsen: invarian F pada INV-APPR-01 akan
   MEMERAH bila `approval_requests` dipakai lagi sementara produsennya masih nol.
```

### price_approvals  [Sub-fase 1.7 IMPLEMENTED — Special Price / Approval Harga]
```
Collection:  price_approvals           Prefix: pra_
Router:      routers/price_approvals.py
Service:     services/storage_service.py (upload bukti — Emergent Object Storage)
Component:   features/sales/PriceApprovals.jsx
Consumed by: routers/sales_orders.py (get_effective_special_price → override harga item)
Key Fields:
  id, entity_id, customer_id, customer_name, product_id, sku, product_name,
  normal_price (snapshot harga produk), requested_price (harga khusus/unit),
  min_quantity, unit, reason, valid_from, valid_until ("" = tanpa kadaluarsa),
  status (draft|pending|approved|rejected), attachments[] (bukti),
  requested_by, requested_by_name, approved_by, approved_by_name,
  decision_notes, decided_at, created_at, updated_at
Attachment item:
  id (att_), storage_path, original_filename, content_type, size,
  uploaded_by, uploaded_at, is_deleted (soft-delete; storage tak punya delete API)
Status flow:  draft → pending → approved | rejected
RBAC:
  sales   → create/update/delete pengajuan SENDIRI (row-level)
  manager → approve/reject; admin → semua
Konsumsi SO:
  item.price_approval_id valid (approved, berlaku, qty ≥ min_quantity) → price = requested_price.
  INVARIAN tetap: item.subtotal = price × quantity.

⚠️ Special Price = price_approvals (BUKAN koleksi 'special_prices'/'price_lists' lepas).
⚠️ JANGAN BUAT: special_prices, nego_harga, price_overrides — gunakan price_approvals.
```


### shipments  [Sub-fase 1.8 IMPLEMENTED — Status SO diperluas + Partial Shipment]
```
Collection:  shipments               Prefix: shp_   (No. Surat Jalan: SJ-#####)
Router:      routers/outbound_picking.py (GET /shipments, GET /shipments/{id}/surat-jalan)
Service:     services/shipment_service.py (dispatch_task), services/fulfillment_status.py
Component:   features/wms/OutboundScanInterface.jsx, features/orders/OrderDetailPanel.jsx
Key Fields:
  id, shipment_no (SJ-#####), order_id, order_number, task_id, allocation_id,
  warehouse_id, warehouse_name, warehouse_city, product_id, product_name, sku,
  qty (BASE UNIT), unit, rolls[] ({roll_id, lot, length, unit}),
  is_partial, status (dispatched), created_by, created_at
Dibuat saat:  dispatch task outbound (parsial/penuh) — 1 record per event dispatch.
INVARIAN (verify_data_integrity L4-SHIP):
  shipped_qty ≤ quantity per task · Σ shipments.qty == Σ task.shipped_qty per order ·
  status SO ⟺ progres task (picked / partially_shipped / shipped / done).
SSOT-safe (KN_15 §10): pengiriman = roll committed → in_transit_sales (BUKAN $inc balance);
  mark-delivered → roll in_transit_sales → 'delivered' (keluar dari owned_qty).
Status SO (Sub-fase 1.8): confirmed → partially_picked → picked → partially_shipped
  → shipped → done (manual via /sales-orders/{id}/mark-delivered).
⚠️ Status 'dispatched' di SO DEPRECATED → gunakan shipped/done. Task tetap pakai 'dispatched'.
```

### tax_invoices  [Sub-fase 1.9 IMPLEMENTED — Faktur Pajak Jual]
```
Collection:  tax_invoices             Prefix: fkt_   (No. Internal: FKT-##### + NSFP resmi 16-digit)
Router:      routers/tax_invoices.py (GET /tax-invoices, POST /sales-orders/{id}/tax-invoice,
             PATCH /tax-invoices/{id}/nsfp, POST .../replace, POST .../cancel, GET .../document)
Service:     services/tax_invoice_service.py (issue/replace/cancel/set_nsfp/render_faktur_html)
Component:   features/finance/TaxInvoices.jsx, features/orders/OrderDetailPanel.jsx
Key Fields:
  id, number (FKT-#####), nsfp (16-digit resmi, opsional/menyusul), kode_transaksi (01..09),
  status (normal|pengganti|batal), replaces_id, replaced_by_id, cancel_reason, replace_reason,
  faktur_date, order_id, order_number, entity_id,
  seller_name, seller_npwp, seller_address (snapshot entitas PKP),
  customer_id, customer_name, customer_npwp, customer_address, has_customer_npwp (snapshot),
  items[] ({product_name, sku, quantity, unit, price, subtotal, discount_amount, line_total}),
  total_amount, discount_total, net_subtotal, dpp, ppn_rate, ppn_mode, ppn_amount, grand_total,
  is_pkp, created_by, created_at, updated_at
Dibuat saat:  MANUAL (opsional — pajak TIDAK wajib) dari Order detail; PKP-only + ppn_amount>0; idempotent (1 aktif/order).
INVARIAN (verify_data_integrity L4-FKT):
  PPN == DPP × rate · Grand == DPP + PPN · ref order valid · normal/pengganti ⟹ is_pkp & ppn>0 ·
  ≤1 faktur aktif (bukan batal & belum diganti) per order · nomor unik · rantai pengganti (replaces_id valid).
⚠️ Penomoran HYBRID: FKT-##### internal + NSFP resmi diisi menyusul (alokasi DJP/Coretax e-Faktur).
⚠️ JANGAN BUAT: faktur, faktur_pajak, bills, tagihan — gunakan tax_invoices.
```



### wms_tasks
```
Collection:  wms_tasks
Routers:     routers/wms.py (generic CRUD)
             routers/inbound_receiving.py (inbound-specific ops)
             routers/outbound_picking.py (outbound-specific ops)
Schema:      schemas.py → WMSTaskCreate, ScannerScan
Components:  ScannerTaskPanel.jsx (generic)
             InboundScanInterface.jsx (inbound)
             OutboundScanInterface.jsx (outbound)
flow_type:   inbound | outbound
Status Inbound:
  waiting_goods → receiving → qc_check → completed | escalated
  [Depth #3a] QC Hold aktif (config.purchasing.qc_on_receipt=True, default):
    waiting_goods → receiving → qc_check → (complete) → qc_pending
      → (qc-decision) → completed | qc_rejected
Status Outbound:
  created → picking → packing → staging → dispatched | escalated
Key Fields:
  id, flow_type, source_type, product_id, product_name, sku,
  quantity, unit, warehouse_id, bin_id, batch, lot, roll_id,
  status, scanned_items: [{scan_value, scan_type, timestamp, actor}],
  source_document (PO id atau SO id), escalation_info, created_at
  [Depth #3a QC] quarantine_qty, qc_status (pending|passed|partial|rejected),
  qc_accept_qty, qc_reject_qty, qc_reject_disposition (damaged|return),
  qc_reason, qc_by, qc_at
  [FASE E] supplier_sku, supplier_item_name, supplier_item_id, expected_grade
           (penamaan versi supplier tampil berdampingan dengan nama KN saat penerimaan)
  [FASE F-1] supplier_uom, supplier_conv_factor    # satuan & faktor versi supplier
             last_receive_doc_uom                  # satuan terakhir yang dipakai operator
             receive_uom_trails: [{...uom_trail, scan_id, actor}]   # akumulasi jejak
             scan_log[].uom_trail: {doc_uom, doc_qty, doc_uom_label, task_uom, task_qty,
               base_uom, base_qty, factor, source, rule_id, path[], supplier_item_id,
               supplier_sku, supplier_item_name, supplier_uom, context, converted_at}
             source ∈ same_unit | supplier_item | fixed_uom | product_override |
                      global_rule | formula_gsm_width | hop_base
  Invarian FASE F-1: INV-RCV-01 jejak lengkap · INV-RCV-02 doc_qty×factor == task_qty ==
    scan_log[].actual_qty · INV-RCV-03 source sah + supplier_item_id hidup +
    receive_uom_trails sinkron dengan scan_log.
  Kebijakan (system_settings scope `receiving`, tanpa deploy):
    supplier_uom_input_mode (off|optional|prefer) · require_supplier_item_for_supplier_uom ·
    block_over_remaining        → services/receiving_uom_service.py
  ⚠️ JANGAN BUAT koleksi baru untuk jejak satuan penerimaan — jejak tinggal di dalam
     `wms_tasks` (scan_log[].uom_trail + receive_uom_trails[]).

⚠️ Depth #3a — QC Hold/Quarantine saat GR:
  • inbound_receiving.complete → roll dibuat status `quarantine` (BUKAN available)
    + roll.qc_task_id = task.id; task → `qc_pending`; TIDAK auto-fulfill.
  • Endpoints (routers/inbound_receiving.py + services/qc_service.py):
    GET  /api/inbound/qc/queue             — antrian qc_pending + quarantine_qty
    POST /api/inbound/tasks/{id}/qc-decision {accept_qty, reject_qty,
         reject_disposition: damaged|return, reason}
  • Accept → roll quarantine→available + auto_fulfill_backorders.
  • Reject damaged → roll quarantine→`damaged`.
  • Reject return  → roll quarantine→`returned_supplier` (keluar on_hand) +
    buat purchase_returns (Nota Debit, stock_adjusted=True, source=qc_reject).
  • SSOT: semua transisi level ROLL (split bila parsial) → rebuild_balance.

⚠️ SATU collection untuk inbound DAN outbound — dibedakan oleh flow_type
⚠️ JANGAN BUAT: inbound_tasks, outbound_tasks, receiving_tasks sebagai collection terpisah
```

### warehouse_transfers
```
Collection:  warehouse_transfers
Router:      routers/transfers.py
Schema:      schemas.py → TransferCreate, TransferApprove, TransferReject
Component:   TransferManagement.jsx
Status Lifecycle:
  draft → waiting_approval → approved → picking → staging → dispatched → received | rejected
Key Fields:
  id, transfer_number, source_warehouse_id, dest_warehouse_id,
  items: [{product_id, product_name, qty, unit, batch, lot, roll_id}],
  status, requested_by, approved_by, notes, created_at, updated_at
  [PROPOSED KN_15] + transfer_kind (intra_entity | inter_entity),
                     source_entity_id, dest_entity_id, transfer_price?, linked_order_id?

⚠️ [PROPOSED KN_15] Inter-company (beda entitas) = EXTEND koleksi ini (transfer_kind=inter_entity),
   BUKAN koleksi baru. Memicu ownership_transfer movement + (Fase 4) AR/AP antar entitas. Lihat KN_15 §7.
⚠️ JANGAN BUAT: transfers, stock_transfer, pemindahan_barang, inter_entity_transfers
```

### cycle_count_sessions
```
Collection:  cycle_count_sessions
Router:      routers/cycle_count.py
Component:   CycleCount.jsx
Status Lifecycle:
  draft → in_progress → submitted → approved | rejected
Key Fields:
  id, session_number, warehouse_id, status,
  items: [{id, product_id, expected_qty, actual_qty, variance, status}],
  submitted_by, approved_by, created_at

⚠️ Approval generate inventory_movements (cycle_count_adjustment)
⚠️ JANGAN BUAT: stock_count, physical_count, stock_opname
```

### purchase_orders
```
Collection:  purchase_orders
Router:      routers/purchase_orders.py
Schema:      schemas.py → PurchaseOrderCreate, POItemCreate, POReceiveItem
Component:   PurchaseOrderManagement.jsx
Status Lifecycle:
  [waiting_approval →] pending → receiving → completed | partial | cancelled
  (waiting_approval hanya jika total_amount memicu approval_rules; lihat Fase 1B)
Key Fields:
  id, po_number (format: PO-NNNNN), supplier_name, supplier_contact,
  warehouse_id, items: [{product_id, quantity, unit, price, subtotal, received_qty}],
  status, expected_delivery_date, notes, created_by, created_at, total_amount
  # Fase 1B — approval dinamis:
  approval_required bool   required_approval_role string|null
  approval_status enum(not_required|pending|approved)   approval_amount float   approved_by string
  # Depth #3 — guard penyimpangan harga:
  approval_reason string(amount_threshold|price_deviation|amount_threshold+price_deviation|"")
  price_deviation {flagged bool, threshold_pct, max_deviation_pct, items:[{sku,price,ref_price,unit,deviation_pct}]}
  last_received_at string|null   # Depth #3 — timestamp penerimaan (scorecard)
  # Setting terkait: settings.purchasing.price_deviation_approval_percent (default 10.0)

⚠️ Supplier adalah STRING saat ini — belum ada supplier master collection
⚠️ Supplier: gunakan FK `supplier_id` → suppliers.id (Fase 3). `supplier_name`/
   `supplier_npwp`/`supplier_contact` = SNAPSHOT saat PO dibuat (backward compat;
   PO lama tanpa supplier_id tetap valid via string).
⚠️ PO tanpa approval → langsung buat wms_tasks (inbound). PO butuh approval → wms_tasks
   dibuat HANYA setelah /purchase-orders/{id}/approve (role_satisfies dari approval_rules).
   /purchase-orders/{id}/reject → status 'rejected' (tanpa task).
⚠️ Depth 1A — status lifecycle: waiting_approval → pending → receiving → partial → completed
   (dihitung dari Σ received_qty vs quantity ± toleransi via recompute_po_status).
   /purchase-orders/{id}/close → 'closed_short' (tutup kurang; batalkan task terbuka).
⚠️ Depth 1C — keuangan/AP: field amount_paid, returned_amount, outstanding, payment_status
   (unpaid|partial|paid), payments[]. /purchase-orders/{id}/pay → cash_transaction(out,
   ref_type=purchase_order) + update AP. /purchase-orders/payables/summary → AP + aging.
⚠️ JANGAN BUAT: po, pembelian, supplier_orders, procurement
```

### makloons
```
Collection:  makloons          Prefix: mak_
Router:      routers/makloons.py
Schema:      schemas.py → MakloonCreate (PATCH via GenericPatch)
Component:   MakloonsView.jsx + Makloon360Panel.jsx (Pembelian → Master Pembelian → Mitra Makloon)
Scope:       SCOPED (entity_id) — mirror suppliers (bisa dipakai lintas-entitas)
Status:      active | inactive (soft delete via DELETE)
Key Fields:
  id, code, name, npwp, pic_name, phone, email, address, city,
  process_types [tenun|celup|printing|jahit|finishing|...], payment_term_code,
  lead_time_days, entity_id, notes, status, created_by, created_at, updated_at
Endpoints:   GET/POST /makloons · GET/PATCH/DELETE /makloons/{id}
             GET /makloons/{id}/scorecard   (metrik dari makloon_orders)
⚠️ Mitra subkontrak (bukan supplier beli-putus). JANGAN BUAT: subcon, subkontraktor, vendor_makloon
```

### process_recipes
```
Collection:  process_recipes   Prefix: prcp_
Router:      routers/process_recipes.py
Schema:      schemas.py → ProcessRecipeCreate (PATCH via GenericPatch)
Component:   ProcessRecipesView.jsx (Pembelian → Master Pembelian → Resep Proses)
Scope:       SCOPED (entity_id)
Status:      active | inactive
Key Fields:
  id, name, process_type, input_product_id, output_product_id, byproduct_product_id,
  input_unit, yield_factor, waste_pct, byproduct_pct, default_makloon_id,
  default_tariff, aux_cost_default, entity_id, notes, status, created_at, updated_at
Endpoints:   GET/POST /process-recipes · PATCH/DELETE /process-recipes/{id}
             POST /process-recipes/forecast   (hitung expected_output & byproduct)
⚠️ Rumus konversi bahan→output makloon. JANGAN BUAT: bom, recipe, formula, konversi_makloon
```

### makloon_orders
```
Collection:  makloon_orders    Prefix: mko_
Router:      routers/makloon_orders.py
Service:     services/makloon_order_service.py (create/issue/receive/cancel + costing + GL)
Schema:      payload dict (steps[]) — divalidasi di service
Component:   MakloonOrdersView.jsx, MakloonOrderCreateModal.jsx, MakloonOrderDetailPanel.jsx
             (Pembelian → Pesanan Pembelian → tab "Order Makloon"; dibuat via Mode Pengadaan
              "Raw Material & Proses" / "Proses Saja" pada tombol Buat di hub PO)
Scope:       SCOPED (entity_id). Respons list = ARRAY.
Status Lifecycle:
  draft → in_process → partially_received → completed | cancelled
Mode:        process_only (bahan dari stok) | buy_process (spawn PO bahan)
Key Fields:
  id, mko_number, mode, material_product_id, material_qty, material_unit,
  from_warehouse_id, target_warehouse_id, supplier_id, material_price,
  steps: [{process_type, makloon_id, recipe_id, input_product_id, output_product_id,
           byproduct_product_id, yield_factor, waste_pct, byproduct_pct, tariff,
           aux_cost, status, lots[]}],
  forecast {expected_finished_qty, ...}, final_output_name, timeline[],
  entity_id, status, created_by, created_at, updated_at
Endpoints:   GET/POST /makloon-orders · GET /makloon-orders/{id}
             POST /makloon-orders/{id}/issue     (kirim bahan → roll status subcon / WIP)
             POST /makloon-orders/{id}/receive   (terima output + barang sisa + costing/GL)
             POST /makloon-orders/{id}/cancel
GL:          akun WIP 1-1350 (WIP-at-Vendor); vendor bill per-step via vendor_bills.
⚠️ JANGAN BUAT: subcon_orders, order_subkontrak, makloon_transactions
```

### suppliers
```
Collection:  suppliers          Prefix: sup_
Router:      routers/suppliers.py
Schema:      schemas.py → SupplierCreate, SupplierPriceListCreate, GenericPatch
Component:   SuppliersView.jsx (Pembelian → Pemasok) + SupplierDetailPanel.jsx
Status:      active | inactive (soft delete via DELETE)
Key Fields:
  id, code (format: SUP-NNNNN), name, npwp, pic_name, phone, email, address,
  city, goods_type (jenis barang), payment_term_code, lead_time_days (Depth #3),
  entity_id, notes, status, created_by, created_at, updated_at
Endpoints:   GET/POST /suppliers · GET/PATCH/DELETE /suppliers/{id}
             # Depth #3 — Supplier Intelligence:
             GET /suppliers/{id}/scorecard       (metrik dari PO + penerimaan + retur)
⚠️ entity_id = default scoped (ent_ksc); supplier bisa dipakai lintas-entitas.
⚠️ JANGAN BUAT: vendor, vendors, pemasok
```

### supplier_price_lists
```
Collection:  supplier_price_lists   Prefix: spl_
Router:      routers/suppliers.py
Schema:      schemas.py → SupplierPriceListCreate (PATCH via GenericPatch)
Service:     services/supplier_service.py → resolve_price()
Component:   SupplierPriceList.jsx (tab di SupplierDetailPanel)
Status:      active | inactive (soft delete via DELETE)
Key Fields:
  id, supplier_id (FK → suppliers.id), supplier_name (snapshot),
  product_id (FK → products.id), sku, product_name (snapshot),
  price (per unit), unit (UOM; default base_unit produk — ikut UOM engine 1.13),
  min_qty (MOQ), lead_time_days (0=pakai default supplier),
  valid_from, valid_until ("" = open), currency (IDR), entity_id, notes,
  status, created_by, created_at, updated_at
Endpoints:   GET/POST /suppliers/{id}/price-list ·
             PATCH/DELETE /supplier-price-list/{entry_id} ·
             GET /supplier-price-list/resolve?supplier_id=&product_id=&qty=
Dipakai:     auto-isi harga di PO create + PR→PO convert (Depth #3).
⚠️ JANGAN BUAT: price_list, harga, vendor_prices
```

### cash_transactions
```
Collection:  cash_transactions  Prefix: cash_
Router:      routers/cash.py
Schema:      schemas.py → CashTransactionCreate
Component:   CashManagementView.jsx (Pembelian → Pengelolaan Kas)
cash_type:   kas_kecil (per entitas) | kas_besar (gabungan, entity_id="all")
direction:   in (masuk) | out (keluar)   ·   status: posted | void
Key Fields:
  id, number (format: CASH-NNNNN), cash_type, direction, amount, category,
  description, entity_id, ref_type, ref_id, txn_date, status, created_by,
  created_at, updated_at
Endpoints:   GET /cash-transactions · GET /cash-transactions/summary ·
             POST /cash-transactions · POST /cash-transactions/{id}/void
Invarian:    saldo = Σ(amount where direction=in) − Σ(amount where direction=out)
             untuk status≠void.
⚠️ JANGAN BUAT: kas, petty_cash, cash
```

### purchase_returns
```
Collection:  purchase_returns  Prefix: pret_
Router:      routers/purchase_returns.py · Service: services/purchase_return_service.py
Schema:      schemas.py → PurchaseReturnCreate, PurchaseReturnItem, PurchaseReturnDecision
Component:   PurchaseReturns.jsx (Pembelian → Retur Beli)
Status:      draft → pending_approval → approved | rejected
Key Fields:
  id, number (PRET-NNNNN), supplier_id, supplier_name, po_id, po_number,
  warehouse_id, warehouse_name, entity_id, items[{product_id, sku, product_name,
  quantity, unit, price, subtotal, reason, condition}], total_amount, reason,
  status, debit_note_number (DN-NNNNN saat approved), stock_adjusted,
  created_by, approved_by, rejected_by, ...
Endpoints:   GET/POST /purchase-returns · GET /purchase-returns/{id} ·
             POST /{id}/submit · /{id}/approve · /{id}/reject
Efek approve: KURANGI inventory_rolls available (FIFO, status→returned_supplier),
             movement return_out, terbitkan Nota Debit, KURANGI AP (PO.returned_amount).
⚠️ JANGAN BUAT: retur_beli, debit_notes, po_returns, vendor_returns
```

### purchase_requisitions
```
Collection:  purchase_requisitions  Prefix: pr_
Router:      routers/purchase_requisitions.py · Service: services/purchase_requisition_service.py
Schema:      schemas.py → PurchaseRequisitionCreate, PurchaseRequisitionItem,
             PurchaseRequisitionDecision, PurchaseRequisitionConvert, SpecialOrderToPR
Component:   PurchaseRequisitions.jsx, ReorderSuggestions.jsx (Pembelian)
Status:      draft → pending_approval → approved → converted | rejected | cancelled
Key Fields:
  id, number (PR-NNNNN), entity_id, warehouse_id, warehouse_name,
  items[{product_id (opsional), sku, product_name, description, quantity, unit,
  est_price, subtotal, note, base_unit, quantity_base, uom_trail{...} ← FASE B/D-07}],
  total_est_amount,
  source (manual|reorder|special_order|**so_repeat** ← PS-21 repeat/restock dari SO),
  source_ref_id, preferred_supplier_id, preferred_supplier_name, reason,
  needed_by_date, status, approval_required, required_approval_role, approval_status,
  po_id, po_number (saat converted), created_by, approved_by, rejected_by, ...
Endpoints:   GET/POST /purchase-requisitions · GET /purchase-requisitions/{id} ·
             GET /purchase-requisitions/reorder-suggestions ·
             POST /{id}/submit · /{id}/approve · /{id}/reject · /{id}/cancel ·
             POST /{id}/convert-to-po · POST /special-orders/{id}/create-pr (jembatan OD)
             POST /sales-orders/{id}/repeat-restock (PS-21 — 1 klik SO → PR + notifikasi MD) ·
             GET  /sales-orders/{id}/restock-state (kandidat restock + pendingan + PR terkait)
             Service PS-21: services/restock_service.py · Component: features/orders/RestockPanel.jsx
Depth #2a:   PR → approval (matriks 'purchase_requisition') → konversi ke PO (catalog only)
Depth #2b:   reorder-suggestions berbasis products.reorder_point/reorder_qty + on_order (anti double-order)
Depth #2c:   jembatan Special Order → PR (item non-katalog) + on_order/ATP (status_board)
⚠️ JANGAN BUAT: requisitions, pr_list, permintaan_pembelian, material_requests
```

### vendor_bills  [Fase 5.2 P0-2 IMPLEMENTED — Vendor Bill + 3-Way Matching]
```
Collection:  vendor_bills      Prefix: vbill_
Router:      routers/vendor_bills.py · Service: services/vendor_bill_service.py
Schema:      schemas.py → VendorBillCreate, VendorBillItemInput,
             VendorBillPaymentCreate, VendorBillDecision
Component:   VendorBillsView.jsx (Pembelian → Tagihan Supplier) +
             VendorBillCreateModal.jsx + VendorBillDetailPanel.jsx
Status:      draft → pending_approval → posted → paid (+ cancelled)
Key Fields:
  id, bill_number (VB-NNNNN), supplier_invoice_no (dedupe per supplier),
  po_id, po_number, supplier_id, supplier_name, supplier_npwp,
  warehouse_id, warehouse_name, entity_id, bill_date, due_date,
  match_mode (received|ordered),
  items[{product_id, sku, product_name, unit, billed_qty, quantity(=billed_qty),
    price, po_price, discount_percent, discount_amount, subtotal, line_total,
    ordered_qty, received_qty, already_billed_qty, remaining_qty,
    match{qty_status, price_status, price_variance_pct, messages[]}}],
  total_amount (GROSS Σ subtotal), items_discount_total, order_discount_percent,
  order_discount_amount, discount_total, net_subtotal, dpp, ppn_rate, ppn_mode,
  is_pkp, ppn_amount, grand_total, tax_mode,
  match_status (matched|warning|blocked), match_exceptions[], within_tolerance,
  approval_required, required_approval_role, approval_status, approved_by,
  amount_paid, outstanding, payment_status (unpaid|partial|paid), payments[],
  timeline[], created_by, created_by_id, created_at, updated_at
Endpoints:   GET/POST /vendor-bills · GET /vendor-bills/{id} ·
             GET /vendor-bills/payables/summary ·
             GET /purchase-orders/{id}/billing-context ·
             POST /vendor-bills/{id}/submit · /{id}/approve · /{id}/reject ·
             POST /vendor-bills/{id}/pay · /{id}/cancel
3-Way Match: PO (ordered) ↔ GR (received_qty) ↔ Bill (billed_qty). Toleransi
             settings.purchasing.bill_qty_tolerance_percent (default 0) &
             bill_price_tolerance_percent (default 5). blocked = over-billing di
             luar toleransi (tak bisa submit). warning = variance dalam toleransi
             (butuh approval manager). matched = bersih (auto-post).
Efek post:   AP berbasis bill. sync_po_billing() update PO.billed_total/unbilled_total.
Pay:         cash_transaction(out, ref_type=vendor_bill) + update AP bill.
⚠️ JANGAN BUAT: bills, tagihan, vendor_invoice, ap_bills, supplier_bills, vendor_invoices
```

### landed_cost_vouchers  [Fase 5.4 P0-5 IMPLEMENTED — Landed Cost → alokasi HPP roll]
```
Collection:  landed_cost_vouchers   Prefix: lcv_
Router:      routers/landed_cost.py · Service: services/landed_cost_service.py
Schema:      schemas.py → LandedCostCreate, LandedCostLineInput,
             LandedCostPaymentCreate, LandedCostDecision
Component:   LandedCostView.jsx (Pembelian → Landed Cost) +
             LandedCostCreateModal.jsx + LandedCostDetailPanel.jsx
Status:      draft → pending_approval → applied → paid (+ cancelled)
Key Fields:
  id, voucher_number (LCV-NNNNN), provider_name, supplier_invoice_no (dedupe),
  po_ids[], po_numbers[], entity_id,
  basis (value|quantity), effective_basis,
  cost_lines[{category(freight|duty|insurance|handling|other), description, amount}],
  total_cost, voucher_date, due_date, target_roll_count,
  allocation_preview[], allocations[{roll_id, roll_no, product_id, length, weight,
    base_unit_cost, current_unit_cost, alloc_amount, per_unit, new_unit_cost}],
  approval_required(true), required_approval_role(manager), approval_status,
  approved_by, approved_at, applied_at,
  amount_paid, payment_status (n/a|unpaid|partial|paid), payments[],
  timeline[], created_by, created_by_id, created_at, updated_at
Endpoints:   GET/POST /landed-costs · GET /landed-costs/{id} ·
             GET /landed-costs/payables/summary ·
             GET /purchase-orders/{id}/landed-cost-context ·
             POST /landed-costs/{id}/submit · /{id}/approve · /{id}/reject ·
             POST /landed-costs/{id}/pay · /{id}/cancel
Alokasi:     biaya total dibagi ke roll (acquired.ref_id ∈ po_ids). Basis value =
             base_unit_cost × length; quantity = length. Fallback value→quantity bila
             Σbobot=0; lalu bagi rata. Σalloc == total_cost (sisa pembulatan ke roll akhir).
Efek apply:  HANYA saat APPROVE (manager+, SoD pembuat≠approver, idempotent via status).
             roll.unit_cost += per_unit (additive); roll.landed_cost_total += alloc;
             roll.landed_cost_refs += voucher_number.
Pay:         cash_transaction(out, ref_type=landed_cost) (opsional, setelah applied).
⚠️ JANGAN BUAT: landed_costs, import_costs, freight_vouchers, biaya_impor, hpp_adjustments
```

### tax_invoices_in  [Fase 5.5 P0-3 IMPLEMENTED — Faktur Pajak Masukan / Input VAT]
```
Collection:  tax_invoices_in   Prefix: fpm_   (No. internal FPM-NNNNN)
Router:      routers/input_tax.py · Service: services/input_tax_service.py
Schema:      schemas.py → InputTaxInvoiceCreate, InputTaxInvoiceCancel
Component:   InputTaxView.jsx (Pembelian → Faktur Pajak Masukan) + InputTaxCreateModal.jsx
Status:      recorded → cancelled
Sumber:      Vendor Bill (status posted|paid, ppn_amount>0). DPP/PPN/supplier disalin dari bill.
Key Fields:
  id, number (FPM-NNNNN), nsfp (NSFP supplier), nsfp_digits (dedupe key), kode_transaksi,
  status (recorded|cancelled), faktur_date, period (YYYY-MM),
  vendor_bill_id, bill_number, supplier_invoice_no, po_id, po_number,
  supplier_id, supplier_name, supplier_npwp, entity_id,
  dpp, ppn_rate, ppn_mode, ppn_amount, grand_total,
  notes, timeline[], cancel_reason, cancelled_by, cancelled_at,
  created_by, created_by_id, created_at, updated_at
Dedupe:      NSFP (digit-only) unik di antara faktur status=recorded → 409 bila ganda.
             1 Vendor Bill → max 1 faktur masukan aktif (vendor_bills.input_faktur_status).
Endpoints:   GET/POST /input-tax-invoices · GET /input-tax-invoices/{id} ·
             GET /input-tax-invoices/eligible-bills · POST /input-tax-invoices/{id}/cancel ·
             GET /tax/vat-summary?period=YYYY-MM (Rekap PPN Masukan vs Keluaran)
Rekap PPN:   /tax/vat-summary → keluaran (tax_invoices, status≠batal) vs masukan
             (tax_invoices_in, status=recorded) per period; net = keluaran−masukan →
             >0 kurang_bayar (setor), <0 lebih_bayar (kredit), =0 nihil.
Efek:        create → vendor_bills.input_faktur_id/number/status='recorded'/nsfp.
             cancel → unset flag bill (eligible lagi), NSFP bisa dipakai ulang.
⚠️ JANGAN BUAT: faktur_masukan, input_vat, ppn_masukan, vat_in, purchase_tax_invoices
```

### rfqs  [Fase 6.1 P1 IMPLEMENTED — RFQ / Quotation (sourcing)]
```
Collection:  rfqs   Prefix: rfq_   (No. RFQ-NNNNN)
Router:      routers/rfq.py · Service: services/rfq_service.py
Schema:      schemas.py → RFQCreate, RFQItemInput, RFQQuoteSubmit, RFQQuoteLine, RFQAward, RFQLineAward, RFQDecision
Component:   RFQView.jsx (Pembelian → RFQ / Quotation) + RFQCreateModal.jsx + RFQDetailPanel.jsx
Status:      draft → open → awarded | cancelled
Sumber:      PR approved (tarik item) | manual (pilih produk). Undang N supplier.
Key Fields:
  id, rfq_number (RFQ-NNNNN), title, entity_id, source ("manual"|"pr"), pr_id, pr_number,
  warehouse_id, warehouse_name, status, needed_by_date, due_date, notes,
  items[] { line_id, product_id, sku, product_name, quantity, unit, note },
  suppliers[] { supplier_id, supplier_name, quote_status ("pending"|"quoted"), quoted_at,
                valid_until, lead_time_days, note, lines[]{line_id,price,available,note}, total },
  award { mode ("full"|"line"), full_supplier_id, line_awards[]{line_id,supplier_id,price},
          po_ids[], po_numbers[], awarded_by, awarded_at },
  timeline[], created_by, created_by_id, created_at, updated_at
Endpoints:   GET/POST /rfqs · GET /rfqs/{id} · GET /rfqs/{id}/compare ·
             POST /rfqs/{id}/send · POST /rfqs/{id}/quote · POST /rfqs/{id}/award ·
             POST /rfqs/{id}/cancel
Compare:     matriks item×supplier + lowest_per_line + total/supplier + recommended_full +
             recommended_line_awards (harga termurah per baris).
Award:       FULL (1 supplier → 1 PO) | LINE (split → 1 PO per supplier). Reuse pricing P0-1
             (compute_order_pricing) + approval threshold + inbound tasks. PO.source_rfq_id/number.
             Upsert supplier_price_lists dari harga pemenang (source=rfq_award, min_qty=0).
             Bila pr_id → PR.status='converted', po_id=PO pertama.
⚠️ JANGAN BUAT: quotations, tenders, bid_requests, penawaran, request_for_quote
```

### document_templates
```
Collection:  document_templates
Router:      routers/documents.py
Schema:      schemas.py → TemplatePayload
Component:   DocumentsView.jsx, AdminView.jsx (tab Templates)
document_type: surat_jalan | invoice
Key Fields:
  id, document_type, name, header, footer, columns, logo_url,
  paper_size, orientation, margin_mm, signature_left, signature_right,
  section_order, status, created_by, created_at

⚠️ JANGAN BUAT: templates, print_templates, doc_config
```

### generated_documents
```
Collection:  generated_documents
Router:      routers/documents.py
Schema:      schemas.py → DocumentGenerate
Key Fields:
  id, document_type, source_id (order_id atau po_id),
  html_content, generated_by, generated_at

⚠️ Dokumen disimpan sebagai HTML string untuk print
```

### permission_settings
```
Collection:  permission_settings
Router:      routers/admin.py
Schema:      schemas.py → PermissionUpdate
Component:   AdminView.jsx (tab Permissions)
Struktur:    {id: "default", matrix: {role: {module: [actions]}}}

⚠️ Hanya ADA 1 document dengan id="default"
⚠️ Fallback: DEFAULT_PERMISSIONS dari permissions_config.py
```

### audit_logs
```
Collection:  audit_logs
Router:      routers/audit.py (read-only list)
Ditulis:     dependencies.py → audit() helper
Component:   AdminView.jsx (tab Audit)
Key Fields:
  id, actor (user name), role, action, entity_type, entity_id,
  before, after, reason, timestamp

⚠️ APPEND-ONLY — tidak pernah update atau delete
⚠️ Gunakan audit() helper dari dependencies.py, BUKAN insert langsung
```

### user_onboarding
```
Collection:  user_onboarding
Router:      routers/onboarding.py
Component:   OnboardingPanel.jsx
Key Fields:
  id (= user_id), tasks: [{id, title, completed, completed_at}]

⚠️ Satu document per user
```

---

<!-- Discovery module (koleksi discovery_sessions/answers/attachments) dihapus 2026-06-17 — fitur assessment online-form. -->



---

## 🚨 FORBIDDEN — NAMA YANG PERNAH MENYEBABKAN DUPLIKAT

Jangan pernah buat collection atau schema dengan nama berikut
(karena sudah ada atau sudah pernah jadi sumber duplikat):

```
❌ items           → gunakan products
❌ goods           → gunakan products
❌ materials       → gunakan products
❌ accessories     → gunakan products
❌ kain            → gunakan products
❌ stock           → gunakan inventory_balances
❌ stok            → gunakan inventory_balances
❌ stock_levels    → gunakan inventory_balances
❌ orders          → gunakan sales_orders
❌ customer_orders → gunakan sales_orders
❌ penjualan       → gunakan sales_orders
❌ inbound_tasks   → gunakan wms_tasks (flow_type=inbound)
❌ outbound_tasks  → gunakan wms_tasks (flow_type=outbound)
❌ receiving_tasks → gunakan wms_tasks (flow_type=inbound)
❌ transfers       → gunakan warehouse_transfers
❌ stock_transfer  → gunakan warehouse_transfers
❌ po              → gunakan purchase_orders
❌ pembelian       → gunakan purchase_orders
❌ bills           → gunakan invoices
❌ tagihan         → gunakan invoices
❌ templates       → gunakan document_templates
❌ staff           → gunakan users
❌ operator        → gunakan users
❌ gudang          → gunakan warehouses
❌ depot           → gunakan warehouses
```

---

## 📐 BASE SCHEMA TEMPLATE

Setiap document baru WAJIB punya field-field ini:
```python
{
    "id":           new_id("prefix"),   # dari core_utils.new_id()
    "created_at":   now_iso(),           # dari core_utils.now_iso()
    "updated_at":   now_iso(),
    "created_by":   user["id"],          # dari token auth
    "created_by_name": user["name"],    # snapshot
    # ... business fields
}
```

Prefix ID yang sudah digunakan:
```
user_   → users
sess_   → sessions
prod_   → products
cust_   → customers
wh_     → warehouses
uom_    → uoms
so_     → sales_orders
bal_    → inventory_balances
roll_   → inventory_rolls            [Fase 0.5 IMPLEMENTED]
mov_    → inventory_movements
wms_    → wms_tasks
trf_    → warehouse_transfers
cc_     → cycle_count_sessions
po_     → purchase_orders
tmpl_   → document_templates
doc_    → generated_documents
inv_    → invoices
audit_  → audit_logs
addr_   → customer addresses (embedded)
ent_    → business_entities         [Fase 0 IMPLEMENTED]
ntf_    → notifications             [Fase 0 IMPLEMENTED]
set_    → system_settings           [Fase 1A IMPLEMENTED]
pterm_  → payment_terms             [Fase 1A IMPLEMENTED]
aprule_ → approval_rules            [Fase 1A IMPLEMENTED]
```
> Prefix PLANNED (lihat bagian PLANNED ENTITIES): `pra_` price_approvals (= "special price"),
> `sord_` special_orders, `bank_` bank_accounts, `cpl_` customer_price_lists, `sret_` sales_returns, `fkt_` tax_invoices.

---

## 🆕 PLANNED ENTITIES (IA KN_14 — belum diimplementasi)

> **Sumber:** `KN_14_INFORMATION_ARCHITECTURE.md`. Entitas berikut **direncanakan**
> per fase roadmap. Didaftarkan di sini lebih dulu (Navigation-First + SSOT) agar
> tidak terjadi duplikat/drift saat coding. Status: **[PLANNED]** — belum ada di DB/kode.
> Saat diimplementasi: pindahkan ke bagian DETAIL di atas + daftarkan ke `verify_contract.py`.

### Lapis Fundamental — Multi-Entity  (✅ IMPLEMENTED Fase 0)
```
Collection: business_entities            Prefix: ent_    Fase 0  [IMPLEMENTED]
  id, legal_name, short_name, type(PT|CV), npwp, address, city,
  default_tax_mode(ppn|non_ppn), doc_prefix, logo_url, status, created_at, updated_at
⚠️ entity_id (FK) ditambahkan ke koleksi TRANSAKSI (scoped): sales_orders, invoices,
   tax_invoices, purchase_orders, cash_transactions, journal_entries, bank_accounts,
   tax_records, fiscal_periods, price_approvals, sales_returns, special_orders.
   Master SHARED (products, warehouses, uoms, document_templates) TIDAK wajib entity_id.
   customers & suppliers = default scoped (opsi shared). JANGAN buat: tenant, company.
```

#### 🔒 FASE E-0 — REGISTRY CAKUPAN ENTITAS DIRAPIKAN (2026-08-10)
`backend/entity_scope.py` adalah **satu-satunya** sumber kebenaran cakupan entitas.
Sebelum FASE E-0 ada **18 koleksi ber-`entity_id` yang tidak terdaftar** (bukan SCOPED,
bukan SHARED) sehingga lolos dari gate kepatuhan dan bocor lintas badan usaha.

**Ditambahkan ke `SCOPED_COLLECTIONS`** (keputusan per koleksi, eksplisit):
`notifications` · `audit_logs` · `payment_plans` · `payment_variance_decisions` ·
`penalties` · `sales_targets` · `sales_incentives` · `warehouse_transfers` ·
`purchase_returns` · `credit_notes` · `budgets` · `fin_budget_rules` ·
`approval_rules` · `cycle_count_sessions` · `supplier_price_lists` · `rfid_tags` ·
`rfid_reads` · `rnd_person_divisions` · `landed_cost_vouchers`.

**Field entitas non-standar** (`SCOPE_FIELD`):
| Koleksi | Field | Alasan |
|---|---|---|
| `inventory_rolls` / `balances` / `movements` / `lots` | `owner_entity_id` | semantik KEPEMILIKAN (dukung konsinyasi) |
| `rfid_tags`, `rfid_reads` | `owner_entity_id` | mengikuti kepemilikan roll |
| `audit_logs` | **`scope_entity_id`** | `audit_logs.entity_id` SUDAH lama berarti **id sumber daya** (mis. `so_001`), bukan badan usaha. Menimpanya akan merusak arti kolom lama. |

**Drift nama koleksi yang dibetulkan:**
- `input_tax_invoices` → **`tax_invoices_in`** (koleksi nyata di DB; nama lama tak pernah ada).
- `landed_costs` → koleksi nyata **`landed_cost_vouchers`** (nama lama dipertahankan sebagai alias).

**`INHERITED_GLOBAL_VALUES`** — koleksi yang SAH punya baris global dan WAJIB dibaca
dengan `resolve_list_scope_inherit()` supaya baris global tidak hilang dari layar:
`notifications` (`None`) · `audit_logs` (`None`) · `incentive_rates` (`"all"`) ·
`approval_rules` (`"all"`) · `cash_transactions` (`"all"`) · `bank_accounts` (`"all"`).

**Helper baru di `entity_scope.py`:**
`resolve_list_scope_inherit()` · `scope_value()` (nilai siap-pakai `str`/`{"$in":[…]}`) ·
`assert_write_entity()` (pagar mode “Semua Entitas” = hanya-baca) ·
`resolve_requested_entity()` (payload boleh menyebut entitas, **wajib** ∈ allowed → tutup L21).

**Pagar anti-regresi:** `scripts/audit_entity_isolation.py` (masuk `scripts/gate.sh`) —
sapuan 301 endpoint GET × 2 sales beda entitas + IDOR 15 endpoint by-id + 3 pemeriksaan
statik registry. POC bukti-merah: `backend/test_core_e0_isolation_poc.py` (83 assert).
Migrasi data: `scripts/fix_orphan_entity_refs.py`.

**Izin baru (`permissions_config.py`):** `audit: [view]` (admin saja — dulu jejak audit
digerbang `product.view` sehingga sales & gudang membacanya) dan
`interco_finance: [view]` (admin/manager — memisahkan sisi UANG antar-PT dari sisi BARANG
`interco: [view, ship, receive]` yang tetap boleh gudang).

### Platform  (✅ `notifications` IMPLEMENTED Fase 0)
```
Collection: notifications    Prefix: ntf_    Fase 0  [IMPLEMENTED]
  id, entity_id, recipient_role|recipient_user, type, title, body,
  link(navigation_target), severity(info|warning|critical), ref, read, read_at, created_at
⚠️ JANGAN buat: notif, alerts (gunakan notifications)
```

### Sales (Fase 1)
```
customer_price_lists   Prefix: cpl_   — harga khusus per customer/kategori/produk + periode [DEPRIORITAS: harga manual/nego]
price_approvals        Prefix: pra_   — special price (negosiasi harga + upload bukti + approval Finance/Admin)
Collection:  sales_returns   Prefix: sret_  — retur/tukar/Barang Sisa (BS) cacat + dampak stok
Collection:  sales_return_policies Prefix: srp_ — R0 kebijakan retur JUAL (scope global|category|customer): window_days, allowed_return_types[], allowed_outcomes[], restocking_fee_pct, require_inspection, enforce_window, link_to_supplier_window, condition_requirements, custom_fields{} (extensible), valid_from/until. SHARED master (entity_id ""=semua). Router: routers/return_policies.py · Service: services/return_policy_service.py
Collection:  special_orders  Prefix: sord_  — Special Order (SKU belum ada → MD + Purchasing) + estimasi
tax_invoices           Prefix: fkt_   — Faktur Pajak (nomor, DPP, PPN, status) per entitas
sales_targets          Prefix: starg_ — target sales per salesperson per periode (penjualan/pencairan/customer baru) [KN_17]
sales_incentives       Prefix: sinc_  — komisi/bonus per sales per periode (basis sales|pencairan|tiered) [KN_17]
campaigns              Prefix: camp_  — product focus / campaign + target per sales (advanced) [KN_17]
collection_followups   Prefix: cfu_   — jejak follow-up penagihan jatuh tempo [KN_17 S39]
credit_overrides       Prefix: cro_   — bypass blokir kredit via approval Finance + bukti (case-by-case) [KN_17 S37]
⚠️ KPI salesperson = DERIVED (dari sales_orders/invoices/payments/customers), BUKAN koleksi.
⚠️ JANGAN buat: discounts, faktur, returns_generic, salespersons (pakai users role=sales), leads/crm_* (fase lanjut)
```

### Procurement (Fase 3)
```
suppliers          Prefix: sup_    — master pemasok (nama, npwp, kontak, jenis barang, entity_id?). R0: +origin_type (local|import), +country, +return_policy{} embedded (window_days, refund_modes[], returnable_to_supplier, rma_required, restocking_fee_pct, condition_requirements, custom_fields{} extensible). purchase_orders.import_flag (bool|None) = override asal per-PO.
bom_printing       Prefix: bom_    — BOM benang + bahan printing per produk/order
cash_transactions  Prefix: cash_   — kas kecil per entitas + kas besar gabungan
⚠️ purchase_orders.supplier_name (string) → refactor jadi FK suppliers.id
⚠️ Approval pembelian = workflow state + attachment pada purchase_orders (bukan koleksi baru)
⚠️ JANGAN buat: vendor, procurement, kas (pakai suppliers/cash_transactions)
```

### Finance (Fase 4)
```
chart_of_accounts  Prefix: coa_    — COA fleksibel (Aktiva/Hutang/Modal/Pendapatan/Beban)
journal_entries    Prefix: je_     — jurnal/GL double-entry (auto-posting dari invoice/kas)
bank_accounts      Prefix: bank_   — rekening per entitas (MULTI-rekening/entitas), entity_id,
                                    bank_name, account_no, account_name, branch,
                                    designation(ppn|non_ppn|both), is_active, is_default
                                    ⚠️ SO + destination_bank_account_id (dipilih saat buat SO; KN_16 §8B.3).
                                       Invoice PPN→akun ppn/both; non-PPN→non_ppn/both.
tax_records        Prefix: tax_    — rekap PPN/PPH (export Coretax = fase lanjut)
fiscal_periods     Prefix: fper_   — periode + closing (28/30/31) + lock
⚠️ AR aging/Outstanding = DERIVED dari invoices + credit_limit; denda 1–3% pada invoices
⚠️ JANGAN buat: ledger, accounts, gl (pakai journal_entries/chart_of_accounts/bank_accounts)
```

### Warehouse & RFID (Fase 5)
```
inventory_classifications Prefix: icls_ — klasifikasi fast/slow/dead (>3 bln) + analitik tren
warehouse_locations   Prefix: loc_  — master lokasi RFID hierarki (Zone→Rack→Level→Bin)
rfid_tags             Prefix: tag_  — registrasi tag ↔ item/lot/roll
rfid_devices          Prefix: dev_  — printer/reader/handheld/gate/server
rfid_events           Prefix: evt_  — log scan/gate (green/red) + alarm → notifications
⚠️ warehouses: tambah level "Level" (Zone→Rack→Level→Bin) — enhancement embedded
⚠️ JANGAN buat: rfid (terlalu generik), locations, tags_generic
```

### HRD (Fase 2)

#### hr_org_units  [FASE H0 IMPLEMENTED — Struktur Organisasi berjenjang]
```
Collection:  hr_org_units      Prefix: orgu_
Router:      routers/hr.py
Schema:      schemas_hr.py → HrOrgUnitCreate (PATCH via GenericPatch)
Service:     services/hr_service.py → build_org_tree()
Component:   features/hr/OrgUnitsView.jsx (SDM → Struktur Organisasi)
unit_type:   department | position        (hierarki: Company(entitas) > department > position)
Status:      active | inactive (soft delete via DELETE)
Key Fields:
  id, code, name, unit_type, parent_id (position→department; department→""),
  head_employee_id (opsional), description, entity_id, status,
  created_by, created_at, updated_at
Endpoints:   GET/POST /hr/org-units · GET /hr/org-units/tree ·
             GET/PATCH/DELETE /hr/org-units/{id}
⚠️ entity_id = SCOPED (per-PT). Company = entitas (business_entities) sebagai root tree.
⚠️ JANGAN BUAT: departments, positions, divisi, jabatan, org_chart (pakai hr_org_units).
```

#### hr_employees  [FASE H0 IMPLEMENTED — Master Karyawan HR]
```
Collection:  hr_employees      Prefix: emp_
Router:      routers/hr.py
Schema:      schemas_hr.py → HrEmployeeCreate, AllowanceInput (PATCH via GenericPatch)
Service:     services/hr_service.py → redact_employee_pii(), enrich_employee()
Component:   features/hr/EmployeesView.jsx + EmployeeFormDrawer.jsx (SDM → Karyawan),
             features/hr/EmployeeSelfService.jsx (ESS → Profil Saya)
employment_type: tetap | kontrak | harian | borongan
Status:      active | inactive | resigned (soft delete via DELETE → resigned)
Key Fields:
  id, code (EMP-NNNNN), user_id (nullable FK → users.id), name, nik,
  dob, gender (L|P), phone, email, address,
  department_id (FK hr_org_units), position_id (FK hr_org_units),
  employment_type, join_date, status,
  # PII-sensitive (redacted tanpa hr.view_pii; ESS lihat data sendiri penuh):
  npwp, ptkp_status (TK0..K3), bpjs_kes_enabled, bpjs_kes_no,
  bpjs_tk_enabled, bpjs_tk_no, jkk_risk_class,
  bank_name, bank_acc_no, bank_acc_name, base_salary, allowances[] {name, amount},
  photo_url, entity_id, created_by, created_at, updated_at
Endpoints:   GET/POST /hr/employees · GET /hr/employees/me (ESS, auth only) ·
             GET/PATCH/DELETE /hr/employees/{id} · GET /hr/summary
⚠️ entity_id = SCOPED (per-PT). user_id menyatukan karyawan dgn akun login (sales→komisi→payroll).
⚠️ employees/employee/staff/karyawan = TERLARANG (alias→users). Domain HRD WAJIB 'hr_employees'.
```

#### system_settings (scope="hr")  [FASE H0 — Config HR/Payroll]
```
Collection:  system_settings (scope="hr")     (SHARED, bukan koleksi baru)
Router:      routers/hr.py → GET/PUT /hr/settings
Schema:      schemas_hr.py → HrSettingsUpdate
Key Fields:  bpjs (rates+ceiling), jkk_classes[], ptkp_table, ter_enabled,
             feature_toggles {bpjs_kesehatan, bpjs_ketenagakerjaan, pph21, npwp_required},
             employment_types[], payroll_commission_mode (default accrue_then_settle)
⚠️ Config-driven (regulasi mudah update). Perhitungan statutory dipakai di FASE H4 (payroll).
```

#### HRD H1 — Absensi (IMPLEMENTED · FASE H1)
```
hr_shifts (shift_)      — Router: routers/hr_attendance.py → GET/POST /hr/shifts, PATCH/DELETE /hr/shifts/{id}
  Fields: id, code, name, jam_in(HH:MM WIB), jam_out, grace_late_min, break_min,
          work_days[1..7], status(active|inactive), entity_id, created_at/by, updated_at
hr_geofences (geo_)     — GET/POST /hr/geofences, PATCH/DELETE /hr/geofences/{id}
  Fields: id, name, lat, lon, radius_m, address, status, entity_id, audit. (validasi haversine)
hr_devices (dev_)       — GET/POST /hr/devices, PATCH/DELETE /hr/devices/{id}
  Fields: id, name, code(SN), location, device_token(auth ingest), last_sync, status, entity_id, audit
hr_attendance (att_)    — GET /hr/attendance, /hr/attendance/recap, /hr/attendance/me,
                          POST /hr/attendance/{clock-in,clock-out,manual,import,ingest}, PATCH /hr/attendance/{id}
  Fields: id, employee_id, employee_name, date(YYYY-MM-DD WIB), shift_id, shift_name,
          clock_in(iso+07:00), clock_out, method(geo|fingerprint|manual), status(hadir|telat|flagged|izin|cuti|alpha|libur),
          outside_geofence, geo{in{lat,lon,distance_m,inside,geofence_id},out{...}}, photo_url, note,
          work_min, late_min, early_leave_min, overtime_min, std_min, approved, entity_id, audit
  IDEMPOTENT: unik per (employee_id, date). Import/ingest gabung multi-punch (in=min, out=max).
Schema: schemas_hr_attendance.py · Service: services/hr_attendance_service.py (haversine, metrics, ZKTeco parse, recap)
RBAC:   hr.view (read) · hr.manage_attendance (CRUD master + manual/approve/import; admin+manager)
        clock-in/out + /me = auth + karyawan ter-link (lihat data sendiri) · ingest = device_token
Employee link: hr_employees.shift_id (FK hr_shifts) + hr_employees.device_user_id (ID enroll mesin)
⚠️ entity_id = SCOPED. JANGAN pakai 'attendance/absensi/shift/device' polos → WAJIB prefiks 'hr_'.
```

#### HRD H5 — KPI Design + Design Gallery + AI (IMPLEMENTED · FASE H5)
```
hr_kpi (hkpi_)         — Router: routers/hr_kpi.py → GET/POST /hr/kpi, PUT/DELETE /hr/kpi/{id}, GET /hr/kpi/me (ESS)
  Fields: id, employee_id, employee_name, entity_id, period(YYYY-MM), metric,
          target(num), actual(num), score(0–150; auto=min(actual/target,1.5)*100 bila kosong),
          weight, note, status(recorded), created_by, created_at, updated_at
  Service: services/hr_kpi_service.py (compute_score, list/submit/update/delete, my_kpi rekap tertimbang)
  RBAC:   hr.view (read) · hr.manage_attendance (CRUD; admin+manager) · /me = auth + karyawan ter-link
  Frontend: features/hr/KpiView.jsx (HRD) + features/hr/MyKpiCard.jsx (ESS "KPI Saya")
design_gallery (dsgn_) — Router: routers/design_gallery.py → GET/POST /design-gallery, GET/PUT/DELETE /design-gallery/{id},
          POST /design-gallery/{id}/files (UploadFile), GET/DELETE /design-gallery/{id}/files/{file_id},
          POST /design-gallery/{id}/autotag (AI, graceful)
  Fields: id, title, story, tags[], files[]({id,filename,path,content_type,size,uploaded_at}),
          product_id(opsional), ai_meta{enabled,model,tags[],summary,attributes,analyzed_at,error},
          entity_id, created_by, created_at, updated_at
  Service: services/design_gallery_service.py (storage lokal via storage_service; get_object MENGEMBALIKAN TUPLE)
  RBAC:   hr.view (read+file) · hr.manage_attendance (create/update/delete/upload/autotag; admin+manager)
  Frontend: features/hr/DesignGalleryView.jsx (gambar via blob-fetch ber-Authorization → objectURL)
  AI:     services/hr_ai_service.py — Anthropic Claude DIRECT SDK (paket `anthropic`), key di
          system_settings scope='integrations'. GRACEFUL: key kosong → autotag {enabled:false} (galeri tetap jalan).
system_settings (scope="integrations")  (SHARED, bukan koleksi baru) — Router: routers/integrations.py →
          GET/PUT /admin/integrations (admin only via hr.manage_settings). Key TIDAK pernah dikembalikan plaintext
          (GET → has_key:bool + model + enabled). Service: services/integrations_service.py (deep-merge anti data-loss).
⚠️ entity_id = SCOPED (hr_kpi, design_gallery). JANGAN pakai 'kpi/gallery/motif' polos.
```

#### HRD — koleksi fase berikut (BELUM, planned)
```
hr_schedules                                                 (H1+ — jadwal shift per-tanggal, opsional)
⚠️ Semua prefiks 'hr_'. JANGAN BUAT: attendance/absensi/payroll/gaji/kpi polos.
```

---

### Gate G-1 — Koleksi operasional HR & Pajak (didaftarkan Gelombang 3, anti self-drift)

#### hr_shifts  [FASE H1 IMPLEMENTED — Master Shift Kerja]
```
Collection:  hr_shifts         Prefix: shift_
Router:      routers/hr_attendance.py
Service:     services/hr_attendance_service.py
Key Fields:  id, code, name, jam_in, jam_out, grace_late_min, break_min, work_days[], status, entity_id
⚠️ entity_id = SCOPED (per-PT).
```

#### hr_geofences  [FASE H1 IMPLEMENTED — Geofence Absensi GPS]
```
Collection:  hr_geofences      Prefix: geo_
Router:      routers/hr_attendance.py
Service:     services/hr_attendance_service.py
Key Fields:  id, name, lat, lon, radius_m, address, status, entity_id
⚠️ entity_id = SCOPED (per-PT).
```

#### hr_attendance  [FASE H1 IMPLEMENTED — Kehadiran Harian]
```
Collection:  hr_attendance     Prefix: att_
Router:      routers/hr_attendance.py
Service:     services/hr_attendance_service.py → upsert_attendance()
Key Fields:  id, employee_id, date, check_in, check_out, method (fingerprint|geo|manual),
             late_min, overtime_min, status, entity_id
⚠️ entity_id = SCOPED (per-PT). Unik per (employee_id, date).
```

#### hr_devices  [FASE H1 IMPLEMENTED — Registry Mesin Absensi]
```
Collection:  hr_devices        Prefix: dev_
Router:      routers/hr_attendance.py
Service:     services/hr_attendance_service.py
Key Fields:  id, name, code, location, device_token, last_sync, status, entity_id
⚠️ entity_id = SCOPED (per-PT). device_token = kredensial push mesin (jaga rahasia).
```

#### hr_field_tracks  [FASE H2 IMPLEMENTED — Breadcrumb GPS Live Tracking]
```
Collection:  hr_field_tracks   Prefix: trk_
Router:      routers/hr_tracking.py
Service:     services/tracking_service.py → hydrate_latest()
Key Fields:  id, employee_id, employee_name, lat, lon, accuracy, battery, ts, source, entity_id
⚠️ entity_id = SCOPED (per-PT). Append-only (jejak posisi).
```

#### hr_visits  [FASE H2 IMPLEMENTED — Kunjungan Lapangan Sales]
```
Collection:  hr_visits         Prefix: visit_
Router:      routers/hr_tracking.py
Service:     services/tracking_service.py
Key Fields:  id, employee_id, customer_id, date, check_in{ts,lat,lon,photo_url},
             check_out{...}, notes, outcome (order|followup|none), linked_so_id,
             status, duration_min, entity_id
⚠️ entity_id = SCOPED (per-PT).
```

#### tax_pph_records  [EPIC 7 IMPLEMENTED — Rekam PPh Manual/Omzet]
```
Collection:  tax_pph_records   Prefix: pph_
Router:      routers/tax_center.py
Service:     services/tax_center_service.py → record_pph()
Key Fields:  id, code (pph21|pph23|...), period (YYYY-MM), rate, dpp, amount, note,
             status, entity_id, created_by
⚠️ entity_id = SCOPED (per-PT). Basis payroll dihitung dari hr_payroll_runs (bukan koleksi ini).
```

#### rfid_tags  [FASE 5 IMPLEMENTED — RFID Simulator: tag ↔ roll]
```
Collection:  rfid_tags         Prefix: rtag_
Router:      routers/rfid.py
Service:     services/rfid_service.py
Key Fields:  id, epc (unik saat active), roll_id (FK inventory_rolls), product_id, sku,
             product_name, roll_no, lot, owner_entity_id, warehouse_id, status (active|retired),
             last_seen_at, last_seen_device_id, last_seen_device_name, last_seen_location,
             last_seen_warehouse_id, encoded_at, encoded_by
⚠️ owner_entity_id = SCOPED (per-PT). Roll-as-SSOT: encode hanya set inventory_rolls.rfid_tag_id
   + tracking_mode="rfid" (TIDAK ubah kuantitas / inventory_balances).
```

#### rfid_devices  [FASE 5 IMPLEMENTED — RFID Reader/Gate (infra per-gudang)]
```
Collection:  rfid_devices      Prefix: rdev_
Router:      routers/rfid.py
Service:     services/rfid_service.py
Key Fields:  id, code (unik), name, type (gate|fixed_reader|handheld), direction (in|out|n/a),
             warehouse_id, warehouse_name, location, status (online|offline), last_heartbeat,
             created_at, created_by
ℹ️ SHARED (infra fisik per-gudang, bukan per-PT). Write = role admin.
```

#### rfid_reads  [FASE 5 IMPLEMENTED — Log pembacaan RFID (event)]
```
Collection:  rfid_reads        Prefix: rread_
Router:      routers/rfid.py
Service:     services/rfid_service.py
Key Fields:  id, epc, tag_id, roll_id, sku, product_name, roll_no, device_id, device_name,
             device_type, read_type (gate_in|gate_out|inventory), warehouse_id, location,
             owner_entity_id, result (green|red|info), reason, timestamp
⚠️ owner_entity_id = SCOPED (per-PT). Append-only event log; gate memutuskan HIJAU/MERAH
   berbasis status roll (kontrol keluar-masuk). Tidak mengubah stok.
```

---

## ADDENDUM — Collections registered during copy+fix session (2026-07-05)

> Koleksi berikut sudah dipakai di kode lintas router/service namun belum tercatat eksplisit
> di atas. Didaftarkan resmi di sini + di allowlist `scripts/validate_compliance.py`
> (CHECK 8 ENTITY_REGISTRY & CHECK 13 NAMING). Semua adalah domain-entity yang sah.

| Collection | Prefix/ID | Router utama | Catatan |
|-----------|-----------|--------------|---------|
| vendor_bills | vb_ | routers/vendor_bills.py | Tagihan vendor (AP). owner_entity_id SCOPED. |
| landed_cost_vouchers | lcv_ | routers/landed_cost.py | Voucher biaya masuk (impor/logistik). |
| rfqs | rfq_ | routers/rfq.py | Request for Quotation (procurement). |
| tax_invoices_in | tii_ | routers/input_tax.py | Faktur Pajak Masukan (PPN in). |
| credit_notes | cn_ | routers/sales_returns.py, crm | Nota kredit pelanggan. |
| amendment_reasons | amr_ | services/amendment_service.py, services/penalty_service.py | FASE G-1/G-2 — taksonomi label alasan koreksi & keputusan denda (dikelola admin). |
| payment_plans | pyp_ | services/payment_plan_service.py, routers/payment_plans.py | FASE G-2 — rencana pembayaran fleksibel per dokumen (DP/cicilan/milestone), nomor `<ENT>/RPB-#####`. Scoped `entity_id`. |
| penalties | pnl_ | services/penalty_service.py, routers/payment_plans.py | FASE G-2 — nota denda keterlambatan (`draft` tanpa jurnal → `issued`/`waived`/`adjusted`/`paid`), nomor `<ENT>/DN-DENDA-#####`. Scoped `entity_id`. |
| payment_variance_decisions | pvd_ | services/payment_variance_service.py, routers/payment_variance.py | FASE G-3 — keputusan **selisih pembayaran** (lebih/kurang bayar), nomor `<ENT>/SLB-#####`. Jenis: `outstanding`/`reschedule`/`writeoff`/`deposit`/`allocate`/`refund` (+`rounding_*` otomatis, +`ap_*` sisi supplier). Wajib `reason_code` & pemutus; pemindahan uang selalu ber-jurnal; `status: reversed` bila dianulir. Scoped `entity_id`. |
| credit_overrides | cro_ | routers/sales_orders.py, so_approvals | Override limit kredit (pending→approved). |
| collection_followups | cf_ | routers/crm.py | Follow-up penagihan AR. |
| sales_targets | st_ | routers/hr_kpi, home | Target penjualan per sales/periode. |
| sales_incentives | si_ | routers/incentive_rates, home | Perhitungan insentif sales. |
| login_attempts | la_ | routers/auth.py | Log percobaan login (rate-limit/security). |
| hr_employees | emp_ | routers/hr*.py | Master karyawan (SCOPED). |
| hr_attendance | att_ | routers/hr_attendance.py | Absensi harian. |
| hr_devices | dev_ | routers/hr_tracking.py | Device absensi/tracking. |
| hr_field_tracks | trk_ | routers/hr_tracking.py | Jejak posisi lapangan (live tracking). |
| hr_geofences | gf_ | routers/hr_tracking.py | Area geofence kunjungan. |
| hr_kpi | kpi_ | routers/hr_kpi.py | KPI karyawan/periode. |
| hr_leave_requests | lv_ | routers/hr_leave.py | Pengajuan cuti. |
| hr_org_units | org_ | routers/hr.py | Unit organisasi (struktur). |
| hr_overtime | ot_ | routers/hr_attendance.py | Lembur. |
| hr_shifts | shf_ | routers/hr_attendance.py | Shift kerja. |
| hr_visits | vis_ | routers/hr_tracking.py | Kunjungan lapangan sales/karyawan. |

> **Modul Digitalisasi Formulir Sukacita (Petty Cash / PD · Settlement · Kendaraan)** — koleksi baru
> FASE 0-5: `cash_advances`, `cash_advance_settlements`, `expense_categories`, `vehicles`, `vehicle_usage_logs`.
> Semua entity-scoped (`entity_id`), terdaftar di `entity_scope.SCOPED_COLLECTIONS` &
> `verify_contract.CANONICAL_COLLECTIONS`.

| Collection | Prefix/ID | Router utama | Catatan |
|-----------|-----------|--------------|---------|
| cash_advances | ca_ (number: {PT}/PD-#####) | routers/cash_advances.py | Form Pengajuan Dana (PD). State-machine draft→pending_atasan→pending_pimpinan→pending_finance→approved→disbursed→settled. SCOPED. |
| cash_advance_settlements | stl_ (number: {PT}/STL-#####) | routers/cash_advances.py | Laporan Pertanggungjawaban (LPJ) atas PD. Posting GL saat approved (Dr beban/Cr Kas Kecil). SCOPED. |
| expense_categories | — (code kategori) | routers/cash_advances.py | Mapping kategori beban petty cash → akun COA (6-4100..6-4900). Config. |
| vehicles | veh_ | routers/vehicle_logs.py | Master kendaraan ringan (no_polisi/nama/jenis). SCOPED. |
| vehicle_usage_logs | vhl_ (number: {PT}/VHL-#####) | routers/vehicle_logs.py | Laporan Penggunaan & Biaya Kendaraan (km, BBM, tol, parkir). SCOPED. |

> **Fix terkait:** `routers/hr_payroll.py` sebelumnya query `db.entities` (koleksi salah/kosong) →
> diperbaiki ke `db.business_entities` agar nama entitas muncul benar di PDF slip gaji.

---

### Platform Dokumen (PDF · WhatsApp · e-Sign) + Payroll Slip  [DIDAFTARKAN 2026-07-26]

Empat koleksi ini sudah dipakai mesin sejak lama tetapi **belum pernah tercatat** di registry,
sehingga muncul sebagai WARN `[ENTITY_REGISTRY]`/`[NAMING]` di `validate_compliance`.
Didaftarkan di sini beserta penulis/pembacanya yang sebenarnya.

| Collection | Prefix/ID | Penulis (SSOT) | Pembaca | Catatan |
|-----------|-----------|----------------|---------|---------|
| `document_deliveries` | `wadlv_` | `services/delivery_service.py:108` | `routers/pdf.py:141`, `delivery_service.list_deliveries()` | Arsip pengiriman dokumen PDF via kanal (WhatsApp). Menyimpan `doc_type`, `source_id`, `to`, `caption`, `status`, `provider`, `simulated`, `attachment_name/size`, `trigger`, `auto`, `rule_id`. **SCOPED** (`entity_id`). Provider `simulated` tetap mencatat penuh tanpa mengirim ke jaringan. |
| `document_signatures` | `esig_` | `services/esign_service.py:138` | `esign_service` (verifikasi + status ttd di daftar dokumen) | Tanda tangan elektronik terverifikasi OTP. Menyimpan `doc_hash` (integritas isi), `verification_code` (QR publik `/verify-document/<code>`), `signer_name/role`, `signature_b64`, `ip`, `channel`. Pasangannya `esign_requests` (OTP, attempts, expiry). **SCOPED**. |
| `hr_payslips` | `id` + `number` | `services/hr_payroll_service.py:287` (`insert_many`) | `routers/hr.py:344` (profil karyawan), `hr_payroll_service:295/366` | Slip gaji per karyawan per periode. Turunan dari `hr_payroll_runs` (bukan sumber). Menyimpan komponen PPh21 metode **TER** (`ter_category`, `pph21_rate`), BPJS (`bpjs_emp/er`), lembur (`overtime_auto_min`/`overtime_filed_min`), `pdf_url`. **SCOPED**. |
| `hr_kpi` | `hkpi_` | `services/hr_kpi_service.py:51` | `routers/hr.py:346`, `routers/hr_kpi.py` | KPI karyawan per periode (`metric`, `target`, `actual`, `score`, `weight`). **SCOPED**. |
| `rnd_person_divisions` | kunci majemuk `entity_id` + `name` | `services/rnd_org_service.py:set_member_division` | `rnd_org_service.division_map/list_members`, `services/rnd_kpi_service.py` (kolom & filter DIVISI), `services/approval_matrix_service.py` | **PS-17 (D-13)** penempatan divisi orang R&D. Disimpan per-NAMA karena desainer sering BUKAN akun user (hanya nama pada round sample); bila namanya seorang user, nilainya dicerminkan ke `users.division`. 1 orang = 1 divisi. **SCOPED** (`entity_id`). |
| `approval_matrix_log` | `amlog_` | `services/approval_matrix_service.py:record` | `services/approval_matrix_service.py:log`, `routers/approvals_matrix.py` (`GET /api/approvals/matrix-log`), `MyApprovalsView` (panel Jejak Persetujuan) | **PS-20 (D-14)** jejak keputusan matriks persetujuan divisi untuk 4 tahap (`design_acc`, `sample_acc`, `po_custom`, `purchase_request`): siapa memutus, tingkat berapa, hasilnya, dan **percobaan yang ditolak sistem** (`violation=true`, mis. peran salah / pengaju menyetujui dokumen sendiri). Jejak ganda juga ditulis ke `audit_logs` (`approval_matrix_*`). **SCOPED** (`entity_id`). |

> 🔴 **BUG DITUTUP 2026-07-26 (ditemukan setelah `check_imports` diperbaiki):**
> `routers/hr.py:346` membaca `db.hr_kpi_entries` — koleksi yang **nol penulis** di seluruh repo
> (0 dokumen). Akibatnya seksi **KPI di profil karyawan selalu kosong** tanpa error.
> Koleksi yang benar adalah **`hr_kpi`** (6 dokumen di data demo, field `employee_id`/`period`/`score`).
> Sudah diperbaiki. `hr_kpi_entries` **tidak dipakai lagi** — jangan dihidupkan kembali.

**Dibuat:** 28 Mei 2026 · **Update IA:** 15 Jun 2026 (planned entities KN_14) · **Update H5:** 01 Jul 2026 (hr_kpi, design_gallery, integrations) · **Update G-1:** Gelombang 3 (hr_shifts, hr_geofences, hr_attendance, hr_devices, hr_field_tracks, hr_visits, tax_pph_records) · **Update 2026-07-26:** document_deliveries, document_signatures, hr_payslips, hr_kpi didaftarkan  
**Update wajib:** Setiap kali ada entitas baru ditambahkan  
**IA induk:** `KN_14_INFORMATION_ARCHITECTURE.md` (SSOT triangle: KN_14 ⇄ KN_13 ⇄ ENTITY_REGISTRY)


---

## ADDENDUM — FASE G-6b (lanjutan Transaksi Antar Entitas) · 2026-08-06

### interco_returns   *(prefix `icr_` · nomor `<ENT>/ICR-#####` · SCOPED `entity_id`)*
**RETUR ANTAR-PT** — jalan resmi ketika barang antar-PT SUDAH berpindah (pembatalan
dokumen sengaja ditolak saat itu). **Dokumen kembar**, satu per PT:
`role="returner"` (nota retur di PT pembeli) ↔ `role="receiver"` (nota kredit di PT
penjual), saling menunjuk `return_pair_id` + `counterpart_id`/`counterpart_number`.

```
id · number · return_pair_id · role(returner|receiver) · entity_id
origin_pair_id · origin_number
seller_entity_id/name · buyer_entity_id/name
items[] {product_id, sku, product_name, unit, quantity, unit_price, line_subtotal, notes}
subtotal · tax_apply · tax_rate · tax_amount · grand_total · returned_cost
reason (WAJIB ≥5 huruf) · notes · doc_date
status: draft → approved → completed  (+ cancelled)
warehouse_transfer_id/code/status   (tugas gudang ARAH BALIK)
timeline[] · created_by/at · approved_by/at · completed_by/at · cancel_reason
```
* Jurnal (`source_type="interco_return"`): `{rp}:seller` `{rp}:buyer` (sisi dokumen,
  saat disetujui) · `{rp}:goods_out` `{rp}:goods_in` (sisi barang, saat tugas gudang
  selesai). Akun: 4-1000 · 2-1200 · 1-1250 · 2-1250 · 1-1310 · 1-1500 · 1-1300 · 5-1000.
* RBAC: `interco:{return, approve, ship}` · **dual-control**: pembuat ≠ penyetuju.
* Invarian: **INV-IC-08**. Endpoint: `/api/interco/returns*`,
  `/api/interco/transactions/{id}/returnable`.
* **JANGAN BUAT**: koleksi retur antar-PT lain (`intercompany_returns`,
  `ic_returns`), dan JANGAN mengedit `grand_total` transaksi asal — retur dicatat
  sebagai `returned_amount`/`returned_subtotal`/`returned_tax`/`returned_cost`/
  `returned_qty` pada dokumen kembar transaksi (ledger append-only).

### tax_invoices / tax_invoices_in — kini juga memuat **FAKTUR PAJAK INTERNAL**
Transaksi antar-PT ber-PPN menerbitkan pasangan dokumen pajak di koleksi yang SUDAH
ADA (sengaja tanpa koleksi baru, supaya rekap `vat_summary` & layar Pusat Pajak ikut
memperhitungkannya tanpa perubahan di sana). Penanda: `source_type="interco"` ·
`is_internal: true` · `interco_pair_id` · `interco_seller_id`/`interco_buyer_id` ·
`counterpart_faktur_id`/`counterpart_faktur_number` · `needs_replacement` (+ `_note`).
`order_id` KOSONG untuk dokumen internal (referensinya `interco_pair_id`).
Invarian: **INV-IC-07**. Jalur pengganti umum (`/api/tax-invoices/{id}/replace`)
MENOLAK dokumen internal dengan kalimat menuntun ke layar Antar Entitas.

### interco_accounts — field baru
`returned_amount` (Σ retur yang berlaku) · `last_activity_at` (aktivitas NYATA
terakhir: dokumen terbuka & settlement — dipakai untuk umur saldo, menggantikan
`updated_at` yang bisa direset oleh hitung-ulang; lihat KN-G6-IDLE-FAKE).

### intercompany_eliminations — field baru (auto G-6)
`g6_unsold_ratio` · `g6_subtotal_effective` · `g6_cost_effective` · `g6_qty_base` ·
`g6_qty_remaining` — jejak angka yang dipakai mesin eliminasi, dibaca invarian
INV-IC-03 & layar Rapor Margin Grup (satu sumber kebenaran, bukan dua rumus).

### customer_prices — F1b (D-14) **Daftar Harga per Pelanggan** (harga langganan)
Collection: `customer_prices`   Prefix: `cpr_`   Router: `routers/customer_prices.py`
Service: `services/customer_price_service.py`   SCOPED via `entity_id` (entity_scope.SCOPED_COLLECTIONS).

Menjawab "harga tetap pelanggan X untuk produk Y" — beda dari `entity_prices` (harga per PT)
dan dari `price_approvals` (izin potong harga). Rantai resolusi SATU definisi
(`customer_price_service.resolve_many`, dipakai SO, POS, dan grid):
    harga khusus disetujui → harga pelanggan → harga PT → harga umum (`products.price`)

Field: `{id, entity_id, customer_id, customer_name, product_id, sku, product_name,
base_unit, sell_price (per base unit), currency, valid_from, valid_until, is_listed,
status (active|pending_approval|rejected|inactive), price_approval_id, guard{...},
note, created_by, created_by_id, approved_by/approved_at | rejected_by/rejected_at |
revoked_by/revoked_at, created_at, updated_at}`

PENJAGAAN HARGA: harga di bawah batas bawah (harga PT / HPP — dihitung
`services/price_guard_service.py`, diatur 3 kunci `pricelist.customer_price_*` di Pusat
Pengaturan) TIDAK langsung berlaku. Record disimpan `pending_approval` dan pengajuan
dibuka di `price_approvals` (`source="customer_pricelist"`, `customer_price_id`) —
MESIN PERSETUJUAN YANG SUDAH ADA, bukan koleksi/alur baru. Approve → record `active`;
reject → `rejected`; aturan diakhiri (`/revoke`) → record `inactive`.

⚠️ JANGAN BUAT koleksi baru: `customer_pricelists`, `harga_pelanggan`,
`contract_prices` — gunakan `customer_prices`.
⚠️ Record `price_approvals` yang punya `customer_price_id` BUKAN aturan harga khusus
tersendiri (hanya jejak keputusan) → dikecualikan dari resolusi aturan STANDING.

### price_approvals — field baru (F1b)
`source` (`sales_request` bawaan | `customer_pricelist`) · `customer_price_id` ·
`guard{floor, floor_from, threshold, basis, hpp, entity_reference, below_floor, gap,
gap_pct, margin_pct, reasons[], summary, tolerance_pct}` (snapshot batas bawah saat
diajukan) · status baru `cancelled` (pengaju menarik) dan `revoked` (approver
mengakhiri aturan yang sudah disetujui, lewat `POST /api/price-approvals/{id}/revoke`
— sebelumnya aturan `approved` TIDAK BISA dihentikan sama sekali) ·
`revoked_by`/`revoked_by_name`/`revoked_at`.
