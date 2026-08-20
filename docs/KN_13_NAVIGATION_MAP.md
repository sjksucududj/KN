# KN_13 — NAVIGATION MAP
## Kain Nusantara Platform — Master Navigation Structure

**Versi:** 1.0 | **Berlaku sejak:** 2026-05-23

---

## 📍 PURPOSE

Navigation Map adalah **Single Source of Truth (SSOT)** untuk struktur menu & routing aplikasi.

**Wajib digunakan untuk:**
1. **Sebelum tambah menu/halaman baru** — Check apakah sudah ada, tentukan posisi yang tepat
2. **Onboarding baru** — Pahami struktur app secara keseluruhan
3. **Refactoring** — Pastikan tidak ada menu redundant
4. **Testing** — Test suite harus cover semua nodes di navigation map

**RULE:** Setiap halaman/fitur baru **WAJIB** di-mapping di sini **SEBELUM** coding.

---

## 🏛️ NAVIGATION HIERARCHY

```
KAIN NUSANTARA APP
│
├── 🏠 HOME / DASHBOARD (Role-Specific Landing)
│   ├── Admin: Admin Dashboard (Master Data Overview)
│   ├── Sales: Sales Portal (POS)
│   ├── Manager: Executive Dashboard (Analytics)
│   └── Warehouse: Operations View (WMS)
│
├── 💼 SALES & POS
│   ├── POS (Sales Portal)
│   │   ├── Product Catalog (Visual Grid)
│   │   ├── Cart Panel (Right Sidebar)
│   │   └── Customer Panel (Dropdown)
│   │
│   └── Orders (Order Management)
│       ├── Dashboard & Analytics Tab
│       │   ├── KPI Cards (Revenue, Top Customers, Status)
│       │   └── Charts (Status Distribution, Trend)
│       │
│       └── Order List Tab
│           ├── Filter by Status (Pills)
│           ├── Search (Order/Customer/Product)
│           ├── Order Cards (List View)
│           └── Order Detail Panel (Right Sidebar)
│               ├── Status Timeline
│               ├── Item List
│               ├── Allocation (per Warehouse)
│               └── Actions (Approve, Confirm, Cancel, Release)
│
├── 🏭 WAREHOUSE & OPERATIONS (WMS)
│   ├── Stok & Inventori
│   │   ├── Tab: Stok
│   │   │   ├── KPI Cards (Total On Hand, Available, Reserved, Low Stock)
│   │   │   ├── Warehouse Filter Pills
│   │   │   ├── Search (SKU/Name/Warehouse)
│   │   │   ├── Inventory Table
│   │   │   └── Reserved Details Panel (Right Sidebar)
│   │   │
│   │   └── Tab: Ledger (Movement History)
│   │       ├── Movement Type Filter
│   │       ├── Date Range Picker
│   │       └── Movement List (Chronological)
│   │
│   ├── Inbound / Penerimaan
│   │   ├── Task List (Left Panel)
│   │   │   ├── Status Filter Pills (Waiting/Receiving/QC/Escalated)
│   │   │   ├── Task Cards
│   │   │   └── Task Actions (Start, Complete, Escalate)
│   │   │
│   │   └── Scan Panel (Right Panel)
│   │       ├── Active Task Info
│   │       ├── Barcode/QR Scanner (Camera/Input)
│   │       ├── Scanned Items List
│   │       └── Complete Button
│   │
│   ├── Outbound / Pengiriman
│   │   ├── Task List (Left Panel)
│   │   │   ├── Status Filter Pills (Created/Picking/Packing/Staging/Dispatched)
│   │   │   ├── Task Cards
│   │   │   └── Task Actions (Pick, Pack, Dispatch)
│   │   │
│   │   └── Scan Panel (Right Panel)
│   │       ├── Active Task Info
│   │       ├── Barcode/QR Scanner
│   │       ├── Picked Items List
│   │       └── Dispatch Button
│   │
│   ├── Transfer Antar Gudang
│   │   ├── Transfer List
│   │   │   ├── Status Filter (Draft/Waiting/Approved/In Transit/Received)
│   │   │   ├── Transfer Cards
│   │   │   └── Actions (Approve, Reject, Dispatch, Receive)
│   │   │
│   │   └── Create Transfer Form (Modal)
│   │       ├── Source Warehouse
│   │       ├── Destination Warehouse
│   │       ├── Item Selection (Multi)
│   │       └── Notes
│   │
│   └── Cycle Count
│       ├── Count Session List
│       │   ├── Status Filter (Draft/In Progress/Submitted/Approved)
│       │   ├── Session Cards
│       │   └── Actions (Start, Submit, Approve, Reject)
│       │
│       └── Count Entry Form
│           ├── Product Selection
│           ├── Warehouse Selection
│           ├── Expected Qty (from system)
│           ├── Actual Qty (counted)
│           └── Variance Indicator
│
├── 📊 PURCHASING
│   ├── Purchase Order List
│   │   ├── Status Filter (Pending/Receiving/Completed/Partial/Cancelled)
│   │   ├── PO Cards
│   │   └── PO Detail Panel (Right Sidebar)
│   │       ├── Supplier Info
│   │       ├── Item List
│   │       ├── Expected Delivery Date
│   │       └── Actions (Receive, Cancel)
│   │
│   └── Create PO Form (Modal)
│       ├── Supplier Name
│       ├── Warehouse Selection
│       ├── Item Selection (Multi)
│       ├── Quantity & Price per Item
│       └── Notes
│
├── 📝 DOCUMENTS & PRINT
│   ├── Print Center
│   │   ├── Surat Jalan Generator
│   │   │   ├── Select Order
│   │   │   ├── Template Selection
│   │   │   ├── Preview
│   │   │   └── Print Button
│   │   │
│   │   ├── Invoice Generator
│   │   │   ├── Select Order
│   │   │   ├── Template Selection
│   │   │   ├── Preview
│   │   │   └── Print Button
│   │   │
│   │   └── Label Printer
│   │       ├── Product Selection (Dropdown)
│   │       ├── Quantity Input
│   │       ├── Label Size (80x50mm, A4)
│   │       ├── Preview (Barcode + SKU + Name)
│   │       └── Generate Button
│   │
│   └── Template Management (Admin Only)
│       ├── Template List (Surat Jalan, Invoice)
│       ├── Template Editor
│       │   ├── Header/Footer Text
│       │   ├── Column Selection
│       │   ├── Logo URL
│       │   ├── Paper Size & Orientation
│       │   └── Signature Fields
│       │
│       └── Actions (Create, Edit, Delete, Set Default)
│
├── 📊 REPORTS & ANALYTICS
│   ├── Executive Dashboard (Manager/Admin)
│   │   ├── KPI Overview (Revenue, Orders, Stock Value, Fulfillment Rate)
│   │   ├── Charts (Revenue Trend, Top Products, Warehouse Performance)
│   │   ├── Timeframe Selector (7/30/90 days)
│   │   └── Export Button (planned)
│   │
│   └── Report Library
│       ├── Stock Aging Report
│       ├── Reservation Funnel Report
│       ├── Order Velocity Report
│       ├── Top Customers Report
│       ├── Warehouse Utilization Report
│       └── Summary Report
│
├── ⚙️ ADMIN & MASTER DATA
│   ├── Master Data Management
│   │   ├── Products
│   │   │   ├── Product List (Table)
│   │   │   ├── Search & Filter (Category, Status)
│   │   │   ├── Product Form (Toggle Expand)
│   │   │   │   ├── SKU, Name, Category, Variant
│   │   │   │   ├── Color, Motif, Grade
│   │   │   │   ├── Supplier, Base Unit, Price
│   │   │   │   ├── Image URL
│   │   │   │   └── UOM Conversions (optional)
│   │   │   │
│   │   │   └── Actions (Create, Edit, Soft Delete, Import CSV, Export CSV)
│   │   │
│   │   ├── Customers
│   │   │   ├── Customer List (Table)
│   │   │   ├── Search & Filter (Type, City)
│   │   │   ├── Customer Form (Toggle Expand)
│   │   │   │   ├── Name, PIC, Phone, Email
│   │   │   │   ├── Type (Retailer/Wholesaler/Boutique)
│   │   │   │   ├── City, Address
│   │   │   │   └── Addresses (Multi, with Primary)
│   │   │   │
│   │   │   └── Actions (Create, Edit, Soft Delete, Import CSV, Export CSV)
│   │   │
│   │   ├── Warehouses
│   │   │   ├── Warehouse List (Table)
│   │   │   ├── Search & Filter (City, Active)
│   │   │   ├── Warehouse Form (Toggle Expand)
│   │   │   │   ├── Code, Name, City
│   │   │   │   ├── Lat/Lng (Coordinates)
│   │   │   │   ├── Zone > Rack > Bin Hierarchy
│   │   │   │   └── Active Status
│   │   │   │
│   │   │   └── Actions (Create, Edit, Soft Delete, Import CSV, Export CSV)
│   │   │
│   │   ├── UOMs (Unit of Measure)
│   │   │   ├── UOM List (Table)
│   │   │   ├── UOM Form (Toggle Expand)
│   │   │   │   ├── Code, Name
│   │   │   │   ├── Base Type (length/volume/weight/count)
│   │   │   │   └── Precision (decimal places)
│   │   │   │
│   │   │   └── Actions (Create, Edit, Delete)
│   │   │
│   │   └── Users
│   │       ├── User List (Table)
│   │       ├── Search & Filter (Role, Status)
│   │       ├── User Form (Toggle Expand)
│   │       │   ├── Name, Email
│   │       │   ├── Role (admin/sales/manager/warehouse)
│   │       │   ├── Password (for new users)
│   │       │   └── Status (active/inactive)
│   │       │
│   │       └── Actions (Create, Edit, Deactivate)
│   │
│   ├── Permission Settings
│   │   ├── Permission Matrix (Role x Module)
│   │   │   ├── Rows: Roles (admin, sales, manager, warehouse)
│   │   │   ├── Columns: Modules (products, customers, orders, wms, etc)
│   │   │   ├── Cells: Actions (read, write, delete, approve, etc)
│   │   │   └── Checkboxes untuk toggle permissions
│   │   │
│   │   └── Actions (Update Matrix, Reset to Default)
│   │
│   ├── Audit Logs
│   │   ├── Audit List (Table, Chronological)
│   │   ├── Filter (Date Range, Actor, Action, Entity Type)
│   │   ├── Search (by Entity ID, Reason)
│   │   └── Log Entry Details
│   │       ├── Actor (User) + Role
│   │       ├── Action (create, update, delete, approve, etc)
│   │       ├── Entity Type + Entity ID
│   │       ├── Before/After Data (JSON diff)
│   │       └── Timestamp + Reason
│   │
│   └── System Settings (Planned)
│       ├── Tax Configuration (PPN %)
│       ├── Reservation Expiry Duration
│       ├── Email/SMTP Settings
│       └── Notification Preferences
│
├── 🔔 ESCALATIONS (Global)
│   ├── Escalation List
│   │   ├── Filter by Status (Pending/In Review/Resolved)
│   │   ├── Filter by Type (Inbound/Outbound/Transfer/Cycle Count)
│   │   ├── Escalation Cards
│   │   └── Escalation Detail Panel
│   │       ├── Source Task Link
│   │       ├── Issue Description (Reason)
│   │       ├── Escalated By + Timestamp
│   │       ├── Resolution Notes (by Manager)
│   │       └── Actions (Review, Resolve, Re-assign)
│   │
│   └── Escalation Form (Modal, from WMS tasks)
│       ├── Task ID (auto)
│       ├── Reason (required, textarea)
│       └── Submit Button
│
├── ❓ HELP & TOURS
│   ├── Guided Tour Menu (Modal)
│   │   ├── Role Badge (current user role)
│   │   ├── Tour List (filtered by role)
│   │   │   ├── Tour: Create Sales Order (5 steps)
│   │   │   ├── Tour: Approve Order (5 steps)
│   │   │   ├── Tour: Process Inbound (4 steps)
│   │   │   ├── Tour: Process Outbound (4 steps)
│   │   │   ├── Tour: Order Dashboard (5 steps)
│   │   │   ├── Tour: Inventory Management (6 steps)
│   │   │   └── Tour: Admin Master Data (7 steps)
│   │   │
│   │   └── Start Tour Button (per tour)
│   │
│   └── Tour Overlay (Active Tour)
│       ├── Highlight Target (Pulse Ring)
│       ├── Tooltip (Title + Instructions)
│       ├── Step Counter (e.g., "2/5")
│       └── Navigation (Previous, Next, Exit)
│
└── 👤 USER MENU (Top Right)
    ├── User Info (Name + Role Badge)
    ├── Profile Settings (Planned)
    ├── Change Password (Planned)
    └── Logout
```

---

## 📋 ROLE-BASED ACCESS MATRIX

| Section | Admin | Sales | Manager | Warehouse |
|---|:---:|:---:|:---:|:---:|
| **Home / Dashboard** | ✅ (Admin) | ✅ (POS) | ✅ (Analytics) | ✅ (WMS) |
| **Sales & POS** | ✅ Full | ✅ Full | 👁️ Read | ❌ No |
| **Orders** | ✅ Full | ✅ Create/View | ✅ Approve/View | 👁️ Read |
| **WMS (Stok)** | ✅ Full | 👁️ Read | 👁️ Read | ✅ Full |
| **WMS (Inbound)** | ✅ Full | ❌ No | 👁️ Read | ✅ Full |
| **WMS (Outbound)** | ✅ Full | ❌ No | 👁️ Read | ✅ Full |
| **WMS (Transfer)** | ✅ Full | ❌ No | ✅ Approve | ✅ Create/Execute |
| **WMS (Cycle Count)** | ✅ Full | ❌ No | ✅ Approve | ✅ Create/Count |
| **Purchasing** | ✅ Full | ❌ No | ✅ Approve | 👁️ Read |
| **Documents & Print** | ✅ Full | ✅ Generate | ✅ Generate | ✅ Generate |
| **Reports & Analytics** | ✅ Full | 👁️ Read | ✅ Full | 👁️ Limited |
| **Admin & Master Data** | ✅ Full | ❌ No | 👁️ Read | ❌ No |
| **Permission Settings** | ✅ Full | ❌ No | ❌ No | ❌ No |
| **Audit Logs** | ✅ Full | ❌ No | 👁️ Read | ❌ No |
| **Escalations** | ✅ Full | ❌ No | ✅ Review | ✅ Create |
| **Help & Tours** | ✅ All Tours | ✅ Sales Tours | ✅ Manager Tours | ✅ WMS Tours |

---

## 📏 NAVIGATION IMPLEMENTATION (Frontend)

### Sidebar Structure (App.js)

```jsx
const navigationConfig = {
  admin: [
    { id: 'home', label: 'Admin Dashboard', icon: LayoutDashboard, view: 'admin' },
    { id: 'pos', label: 'POS', icon: ShoppingCart, view: 'pos' },
    { id: 'orders', label: 'Orders', icon: ShoppingBag, view: 'orders' },
    { id: 'wms', label: 'Warehouse & Operations', icon: Warehouse, view: 'wms' },
    { id: 'purchasing', label: 'Purchasing', icon: ShoppingBasket, view: 'purchasing' },
    { id: 'documents', label: 'Documents & Print', icon: FileText, view: 'documents' },
    { id: 'reports', label: 'Reports & Analytics', icon: BarChart3, view: 'reports' },
    { id: 'admin', label: 'Admin & Master Data', icon: Settings, view: 'admin' },
    { id: 'escalations', label: 'Escalations', icon: AlertTriangle, view: 'escalations' },
  ],
  sales: [
    { id: 'home', label: 'POS', icon: ShoppingCart, view: 'pos' },
    { id: 'orders', label: 'Orders', icon: ShoppingBag, view: 'orders' },
    { id: 'documents', label: 'Documents & Print', icon: FileText, view: 'documents' },
  ],
  manager: [
    { id: 'home', label: 'Executive Dashboard', icon: BarChart3, view: 'reports' },
    { id: 'orders', label: 'Orders', icon: ShoppingBag, view: 'orders' },
    { id: 'wms', label: 'Warehouse & Operations', icon: Warehouse, view: 'wms' },
    { id: 'purchasing', label: 'Purchasing', icon: ShoppingBasket, view: 'purchasing' },
    { id: 'reports', label: 'Reports & Analytics', icon: BarChart3, view: 'reports' },
    { id: 'escalations', label: 'Escalations', icon: AlertTriangle, view: 'escalations' },
  ],
  warehouse: [
    { id: 'home', label: 'Warehouse & Operations', icon: Warehouse, view: 'wms' },
    { id: 'documents', label: 'Documents & Print', icon: FileText, view: 'documents' },
    { id: 'escalations', label: 'Escalations', icon: AlertTriangle, view: 'escalations' },
  ],
};
```

### WMS Tabs (OperationsView)

```jsx
const wmsTabs = [
  { id: 'stok', label: 'Stok & Inventori', icon: Package },
  { id: 'inbound', label: 'Inbound / Penerimaan', icon: PackagePlus },
  { id: 'outbound', label: 'Outbound / Pengiriman', icon: PackageMinus },
  { id: 'transfer', label: 'Transfer Antar Gudang', icon: ArrowLeftRight },
  { id: 'cycle', label: 'Cycle Count', icon: ClipboardCheck },
];
```

### Orders Tabs (OrdersView)

```jsx
const ordersTabs = [
  { id: 'dashboard', label: 'Dashboard & Analytics', icon: BarChart3 },
  { id: 'list', label: 'Order List', icon: List },
];
```

---

## 🧪 TEST DATA-TESTID MAPPING

**WAJIB:** Setiap interactive element dan info-display element harus punya `data-testid`.

### Sidebar
```jsx
<button data-testid="nav-pos">POS</button>
<button data-testid="nav-orders">Orders</button>
<button data-testid="nav-wms">Warehouse & Operations</button>
<button data-testid="nav-purchasing">Purchasing</button>
<button data-testid="nav-documents">Documents & Print</button>
<button data-testid="nav-reports">Reports & Analytics</button>
<button data-testid="nav-admin">Admin & Master Data</button>
<button data-testid="nav-escalations">Escalations</button>
<button data-testid="help-tours-button">Help & Tours</button>
```

### WMS Tabs
```jsx
<button data-testid="wms-tab-stok">Stok</button>
<button data-testid="wms-tab-inbound">Inbound</button>
<button data-testid="wms-tab-outbound">Outbound</button>
<button data-testid="wms-tab-transfer">Transfer</button>
<button data-testid="wms-tab-cycle">Cycle Count</button>
```

### Orders Dashboard
```jsx
<div data-testid="dashboard-metric-revenue">...</div>
<div data-testid="dashboard-top-customers">...</div>
<div data-testid="dashboard-status-distribution">...</div>
```

### Inventory Filters
```jsx
<div data-testid="inventory-warehouse-filters">...</div>
<input data-testid="inventory-search" />
```

---

## 🔍 NAVIGATION FIRST POLICY

**BEFORE adding any new page/feature:**

1. **Check if exists:**
   ```bash
   grep -r "feature_name" /app/docs/KN_13_NAVIGATION_MAP.md
   ```

2. **If NOT exists, decide placement:**
   - Which parent section? (Sales, WMS, Admin, etc)
   - Which role can access?
   - What's the route?
   - What's the data-testid?

3. **Update this file FIRST** before coding:
   - Add to hierarchy tree
   - Add to role access matrix
   - Add to implementation code snippet
   - Add to test data-testid mapping

4. **Then code:**
   - Backend: Create router
   - Frontend: Create component
   - Add to sidebar/tab config
   - Add data-testid attributes

---

## ⚠️ ANTI-PATTERNS (JANGAN LAKUKAN)

### ❌ 1. Menu Redundan
```
❌ BAD:
  ├── Sales Orders (di Sales section)
  ├── Order Management (di Operations section)
  └── View Orders (di Reports section)

✅ GOOD:
  └── Orders (satu tempat, dengan tabs Dashboard vs List)
```

### ❌ 2. Deep Nesting (>4 levels)
```
❌ BAD:
  Sales > Orders > Details > Items > Edit Item Modal > Warehouse Selection
  (6 levels!)

✅ GOOD:
  Sales > Orders > [Detail Panel] > Edit Item Modal
  (3 levels, panel bukan nested route)
```

### ❌ 3. Role-Specific Duplicate Pages
```
❌ BAD:
  /admin/dashboard (admin only)
  /manager/dashboard (manager only)
  /sales/dashboard (sales only)

✅ GOOD:
  /dashboard (conditional content based on role)
```

---

## 🚦 NAVIGATION CHANGE PROTOCOL

### For Minor Changes (adding data-testid, renaming label)
- Update this file
- Update code
- No review needed

### For Major Changes (new section, restructure)
1. **Propose change** di SESSION_LOG.md
2. **Update KN_13** dengan [PROPOSED] tag
3. **Review with team/user**
4. **Implement after approval**
5. **Update Guided Tours** yang terpengaruh
6. **Update tests**

---

## 📝 CHANGELOG

### v1.0 — 23 Mei 2026 (Initial Navigation Map)
- Created navigation hierarchy untuk 9 major sections
- Defined role-based access matrix (4 roles)
- Documented WMS tabs (5 tabs) & Orders tabs (2 tabs)
- Established data-testid naming convention
- Set navigation-first policy

---

## 🆕 TARGET GROUPED NAVIGATION IA (selaras KN_14 — 6 Fase)

> **Sumber:** `KN_14_INFORMATION_ARCHITECTURE.md` §5. Menu **flat eksisting** akan
> berevolusi menjadi **grouped domains** agar scale untuk 6 fase. Tanda: ✅ ada ·
> 🟡 enhancement · 🆕 [PLANNED]. **Belum diimplementasi** — IA difinalkan dulu.

```
GLOBAL SHELL (Top Bar)
  ├── Entity Switcher 🆕   (konteks entitas aktif: PT Kain Suka Cita / CV Kanda Suka / Semua)
  ├── 🔔 Notification Center 🆕
  ├── ❓ Help & Tours ✅
  └── 👤 User Menu ✅

SIDEBAR (grouped, collapsible, role-filtered)
  🏠 Beranda (role landing) ✅
  💼 Penjualan
     ├── POS / Sales Portal ✅
     ├── Pesanan Penjualan (SO) ✅🟡 (status: Pending/Keep/Ready/Waiting Shipment/Partial/Complete)
     ├── Price List per Customer 🆕
     ├── Approval Harga (negosiasi + upload bukti + approval owner) 🆕
     ├── Returns & BS 🆕
     ├── Special Order (OD) 🆕
     └── Faktur & Pajak Jual 🆕
  🧾 Pembelian
     ├── Pesanan Pembelian (PO) ✅🟡
     ├── Suppliers (Master) 🆕
     ├── Approval Pembelian 🆕
     ├── BOM Printing 🆕
     └── Pengelolaan Kas 🆕
  🏭 Gudang
     ├── Stok & Inventori ✅
     ├── Inbound / Penerimaan ✅ (toleransi ±2% 🆕)
     ├── Outbound / Pengiriman ✅
     ├── Transfer Antar Gudang ✅
     ├── Cycle Count ✅
     └── Stock Analytics (fast/slow/dead >3bln) 🆕
  📡 RFID
     ├── Lokasi RFID 🆕 · Tags 🆕 · Devices 🆕 · Gate Monitor (green/red) 🆕
  💰 Keuangan
     ├── Chart of Accounts 🆕 · Jurnal/GL 🆕 · Bank 🆕 · Pajak (PPN/PPH) 🆕
     ├── AR / Outstanding + Denda 1–3% 🆕 · Closing (28/30/31) 🆕 · Invoices ✅🟡
  💼 Kas & Aset (Digitalisasi Formulir Sukacita) ✅🆕
     ├── Petty Cash & PD → Pengajuan Dana (PD) · Pertanggungjawaban (LPJ) · Kategori Beban
     └── Kendaraan → Log & Biaya · Master Kendaraan · Rekap
  👥 SDM (HRD)
     ├── Employees 🆕 · Attendance (fingerprint) 🆕 · KPI Design 🆕 · Design Gallery + AI 🆕
  📊 Analitik (BI)
     └── Sales / Stock / Finance / HR dashboards 🆕
  📝 Dokumen
     ├── Print Center ✅ · Templates ✅
  ⚙️ Admin & Master Data
     ├── Business Entities 🆕 · Customers ✅ · Products ✅🟡 · Warehouses ✅🟡 (Zone→Rack→Level🆕→Bin)
     ├── UOMs ✅ · Users ✅ · Permissions ✅ · Audit ✅ · System Settings 🆕
  🔔 Eskalasi ✅

ROUTE STANDALONE (tanpa login)
  ├── /discovery/{session_id} ✅
  └── /catalog[/{product_id}] 🆕 (Ecommerce katalog publik — read-only)
```

**Aturan kedalaman:** Grup (L1) → Menu (L2) → Tab/Panel (L3) → Modal (L4). Maks 4.
**data-testid:** `nav-group-{domain}`, `nav-{module}`, `tab-{module}-{tab}`, `entity-switcher`, `notif-bell`.

> ⚠️ Migrasi menu flat → grouped = bagian Fase 0/1 (implementasi DITUNDA). Saat
> dieksekusi, update bagian ini dari [PLANNED] → aktif + sinkronkan Guided Tours.

---

**Maintained by:** Development Team  
**Review Cycle:** Per major feature release  
**Next Review:** Setelah Phase 4 (Tier 1 ERP modules)  
**IA induk:** `KN_14_INFORMATION_ARCHITECTURE.md` (SSOT triangle: KN_14 ⇄ KN_13 ⇄ ENTITY_REGISTRY)
