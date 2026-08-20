# KN_01 — SYSTEM OVERVIEW
## Kain Nusantara Platform — Business Context & Architecture

**Versi:** 1.0 | **Berlaku sejak:** 2026-05-23

---

## Tentang Kain Nusantara

Kain Nusantara adalah perusahaan tekstil yang beroperasi di Indonesia dengan jaringan gudang di Pulau Jawa (ekspansi ke luar Jawa di masa mendatang). Platform ini dibangun sebagai **Enterprise ERP + WMS** yang modern, AI-assisted, dan RFID-ready.

**Visi sistem:** Microsoft Business Central — lebih modern, AI-assisted, integration-friendly.

---

## 12 System Paradigms

Setiap fitur yang dibangun harus melayani minimal satu dari 12 paradigma ini:

```
1.  System of Record              → Data lengkap, immutable history, SSOT
2.  System of Control             → Approval workflow, authorization, limits
3.  System of Automation          → Event-triggered tasks, auto-documents
4.  System of Workflow            → Task lifecycle, SLA, escalation chain
    Orchestration
5.  System of Intelligence        → AI insights, anomaly detection, forecast
6.  System of Visibility          → Real-time dashboards, RFID tracking
7.  System of Coordination        → Task assignment, cross-dept handoff
8.  System of Accountability      → Audit trail, responsibility log
9.  System of Standardization     → SOP enforcement, guided workflow
10. System of Optimization        → Performance metrics, efficiency
11. System of Governance          → Policy enforcement, compliance
12. System of Strategic           → API-first, integration-ready, scalable
    Infrastructure
```

**Rule:** Sebelum build fitur, jawab: "Paradigma mana yang dilayani fitur ini?"
Jika tidak bisa dijawab → fitur mungkin tidak perlu dibangun.

---

## Domain Map

```
┌─────────────────────────────────────────────────────────────────┐
│                    KAIN NUSANTARA PLATFORM                      │
├──────────────────┬─────────────────┬──────────────────────────┤
│  CORE DOMAIN     │  BUSINESS DOMAIN│  INTELLIGENCE DOMAIN     │
│                  │                 │                          │
│  WMS &           │  Sales & POS    │  AI & Analytics          │
│  Inventory       │  Procurement    │  Executive Dashboard     │
│  Item Master     │  Finance        │  AI Insights             │
│  RFID            │  HR             │  Predictive Analytics    │
│                  │                 │                          │
├──────────────────┴─────────────────┴──────────────────────────┤
│                   PLATFORM LAYER                               │
│  Personal Work System | Notifications | Audit Trail           │
│  Integration Layer | RFID Middleware | External API            │
└────────────────────────────────────────────────────────────────┘
```

---

## Role Definitions

```
ROLE                  SCOPE               PRIMARY ACTIVITY
─────────────────────────────────────────────────────────
SUPER_ADMIN           Global              System management
SYSTEM_ADMIN          Global              User & config management
WAREHOUSE_MANAGER     1+ Warehouses       Operations oversight
RECEIVING_OPERATOR    1 Warehouse         Inbound operations
PICKING_OPERATOR      1 Warehouse         Outbound operations
INVENTORY_CLERK       1 Warehouse         Stock management
QC_INSPECTOR          1 Warehouse         Quality inspection
FINANCE_MANAGER       Global              Financial oversight
FINANCE_USER          Global              AR/AP processing
PROCUREMENT_USER      Global              Purchase management
SALES_USER            Global              Order & POS
HR_MANAGER            Global              People management
HR_USER               Global              HR operations
EXECUTIVE             Global (read)       Strategic visibility
RFID_SERVICE          System              Machine-to-machine
```

---

## Key Business Flows

### 1. Inbound Flow (Procurement → WMS)
```
Purchase Requisition
  → Purchase Order (dengan approval)
  → Goods Receipt Notification
  → Physical Receiving (RFID scan / barcode)
  → QC Inspection (optional hold)
  → Putaway ke lokasi (directed putaway)
  → Inventory update
  → AP Accrual (Finance)
  → GR Task auto-close
```

### 2. Outbound Flow (Sales → WMS)
```
Sales Order / POS
  → Stock Reservation (otomatis)
  → Pick Task generated (system)
  → Picking (RFID / barcode)
  → Packing
  → Delivery Order generated
  → Shipping
  → Stock deduction
  → Invoice generation
  → AR update (Finance)
```

### 3. RFID Movement Flow
```
RFID Tag read oleh reader
  → Edge Agent deduplication
  → MQTT → Backend consumer
  → Zone transition detected
  → Stock movement record
  → Real-time update ke dashboard
  → Alert jika anomali
```

### 4. Personal Work Flow
```
Business event terjadi
  → System generate task
  → Assign ke role yang tepat
  → Muncul di "My Work Today"
  → User klik → navigate ke screen
  → User selesaikan → task auto-close
  → Jika overdue → eskalasi ke atasan
```

---

## Textile-Specific Considerations

```
Kain diukur dalam: meter, roll, kg, yard
  → Multi-UOM dengan konversi per item
  → Catch weight: ukur aktual saat receiving

Setiap roll punya panjang aktual berbeda
  → Tracking per roll (roll_id), bukan hanya per SKU
  → Variance antara PO quantity dan aktual = normal

Dye lot / color batch matters
  → Lot tracking wajib (kain dari lot berbeda tidak bisa dicampur)
  → Lot number capture saat receiving

Grade kualitas (A/B/C)
  → Quality attribute di item master
  → Grade mempengaruhi harga

Shrinkage factor
  → Adjustment quantity di PO vs aktual
  → Configureable per item category
```

---

## Multi-Warehouse Architecture

```
Hierarchy:
Region (Jawa Barat, Jawa Tengah, Jawa Timur)
  └── Warehouse (Gudang Cikarang, Gudang Solo...)
        └── Building / Gedung
              └── Zone (Receiving, Storage, QC Hold, Shipping)
                    └── Aisle / Lorong
                          └── Rack
                                └── Shelf / Tingkat
                                      └── Bin (unit terkecil tracking)

Warehouse Selector:
  → Setiap user di-assign ke 1+ warehouse
  → UI menampilkan active warehouse di top bar
  → Semua data filter otomatis by active warehouse
  → Manager senior bisa lihat "All Warehouses" (aggregated)
```

---

## Personal Work Guidance System

```
Filosofi: Sistem guide user, bukan user harus paham sistem dulu.

Task Sources:
  USER_CREATED     → User buat manual
  MANAGER_ASSIGNED → Atasan assign ke bawahan
  SYSTEM_GENERATED → Otomatis dari business event
  RECURRING        → Template yang auto-generate periodik

Task → Navigation Link:
  Setiap task punya navigation_target
  Klik task → langsung ke screen dengan context pre-loaded
  Contoh: "Terima PO-123" → /gudang/penerimaan?po_id=PO-123

Eskalasi:
  Task overdue +2 jam → notifikasi ke assignee
  Task overdue +8 jam → eskalasi ke atasan langsung
  Task overdue +24 jam → eskalasi ke manager senior
```
