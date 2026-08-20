# CODEBASE MAP — Quick Reference
## Kain Nusantara Platform

**Gunakan file ini untuk:**
- Cek apakah fungsi/komponen yang ingin dibuat SUDAH ADA
- Cari file yang relevan sebelum mulai coding
- Cek ukuran file untuk monitor mendekati batas

**Batas ukuran file (NON-NEGOTIABLE):**
- React Component (.jsx): MAX 500 baris
- Python Router (.py): MAX 800 baris
- Utility/Helper (.js): MAX 300 baris

---

## 🐍 BACKEND FILES

### Core Files

| File | Fungsi | Baris | Status |
|------|---------|-------|--------|
| `server.py` | App factory, lifespan, router registration, seed data | 272 | ✅ OK |
| `db.py` | MongoDB connection (Motor async) | 13 | ✅ OK |
| `core_utils.py` | `now_iso()`, `new_id()`, `safe_doc()`, `hash_password()` | 45 | ✅ OK |
| `schemas.py` | Semua Pydantic request models | 214 | ✅ OK |
| `dependencies.py` | `current_user()`, `require_role()`, `require_permission()`, `audit()` | 58 | ✅ OK |
| `permissions_config.py` | `DEFAULT_PERMISSIONS` matrix | ~55 | ✅ OK |

### Routers

| File | Domain | Endpoints | Baris | Status |
|------|--------|-----------|-------|--------|
| `routers/auth.py` | Auth | POST /auth/login, GET /auth/me, POST /auth/logout | 40 | ✅ OK |
| `routers/users.py` | Users | GET/POST /users, PATCH /users/{id} | 55 | ✅ OK |
| `routers/products.py` | Products | GET/POST/PATCH/DELETE /products, GET /products/{id}/stock-breakdown | 87 | ✅ OK |
| `routers/customers.py` | Customers | GET/POST /customers, PATCH /customers/{id}, POST /customers/{id}/addresses | 74 | ✅ OK |
| `routers/warehouses.py` | Warehouses | GET/POST/PATCH/DELETE /warehouses | 77 | ✅ OK |
| `routers/uoms.py` | UOMs | GET/POST/PATCH/DELETE /uoms | 55 | ✅ OK |
| `routers/inventory.py` | Inventory | GET /inventory/balances, GET /inventory/movements, POST /inventory/initial-stock, GET /history/{id} | 77 | ✅ OK |
| `routers/sales_orders.py` | Orders | GET/POST /sales-orders, GET/PATCH /{id}, POST /{id}/submit-for-approval, /approve, /confirm, /release-reservation, /cancel | 239 | ✅ OK |
| `routers/invoices.py` | Invoices | GET /invoices, GET /sales-orders/{id}/invoices, POST /sales-orders/{id}/simulate-payment | 52 | ✅ OK |
| `routers/wms.py` | WMS Generic | GET/POST /wms/tasks, POST /wms/tasks/outbound-from-order/{id}, POST /wms/tasks/{id}/scan, POST /wms/tasks/{id}/advance | 194 | ✅ OK |
| `routers/inbound_receiving.py` | Inbound | GET /inbound/tasks, POST /inbound/tasks/{id}/scan-receive, /escalate, /resolve-escalation, /complete, GET /inbound/po/{id}/receiving-goods-document | 459 | ⚠️ MENDEKATI BATAS |
| `routers/outbound_picking.py` | Outbound | GET /outbound/tasks, POST /outbound/tasks/{id}/scan-pick, /escalate, /resolve-escalation, /dispatch, GET /outbound/so/{id}/surat-jalan | 552 | 🔴 MELEBIHI BATAS |
| `routers/transfers.py` | Transfers | GET/POST /transfers, GET/POST/DELETE /transfers/{id}, /approve, /reject, /status | 442 | ✅ OK |
| `routers/cycle_count.py` | Cycle Count | POST/GET /cycle-count/sessions, GET/POST /{id}, /{id}/items, /{id}/submit, /approve, /reject | 242 | ✅ OK |
| `routers/purchase_orders.py` | PO | GET/POST /purchase-orders, GET/POST /purchase-orders/{id}, /amend (Phase 7.2 → po_amendment_service), /approve, /reject, /pay, /close, /cancel | 655 | ✅ OK |
| `routers/dashboard.py` | Dashboard | GET /dashboard | 45 | ✅ OK |
| `routers/reporting.py` | Reports | GET /reports/stock-aging, /reservation-funnel, /order-velocity, /top-customers, /warehouse-utilization, /summary | 227 | ✅ OK |
| `routers/documents.py` | Documents | GET/POST/PATCH/DELETE /document-templates, POST /documents/generate, GET /documents/preview/{id}, POST /documents/barcode | 121 | ✅ OK |
| `routers/label_printer.py` | Labels | POST /labels/generate, POST /labels/preview | 144 | ✅ OK |
| `routers/admin.py` | Admin | POST/GET /master-data/import-*/export-*, GET/PUT /permissions, POST /admin/seed-demo | 352 | ✅ OK |
| `routers/audit.py` | Audit | GET /audit-logs | 15 | ✅ OK |
| `routers/onboarding.py` | Onboarding | GET /onboarding, POST /onboarding/{id}/complete, POST /onboarding/reset | 82 | ✅ OK |
| `routers/price_approvals.py` | Special Price / Approval Harga (Sub-fase 1.7) | GET/POST /price-approvals, GET /price-approvals/effective, GET/PATCH/DELETE /{id}, POST /{id}/submit /approve /reject, POST/GET/DELETE /{id}/attachments | ~350 | ✅ OK |

### Services

| File | Fungsi | Baris |
|------|---------|-------|
| `services/inventory_service.py` | Inventory business logic helpers | ~100 |
| `services/label_printer_service.py` | Label generation logic | ~100 |
| `services/demo_seed_service.py` | Demo seed runner (calls seed_realistic.py) | ~88 |
| `services/storage_service.py` | Emergent Object Storage wrapper (upload bukti, reusable) — Sub-fase 1.7 | ~120 |
| `services/po_amendment_service.py` | **Phase 7.2** — `amend_po()` + `diff_po_items()`: amandemen PO (item/supplier/gudang/tgl/catatan), version history + snapshot + diff, re-approval penuh, guard partial-receiving. Router thin memanggil ini (kembalikan `{po, needs_approval}`). | 274 |

---

## ⚛️ FRONTEND FILES

### Entry Points

| File | Fungsi | Baris | Status |
|------|---------|-------|--------|
| `App.js` | Root component, state management, routing | 178 | ✅ OK |
| `App.css` | `@import` aggregator → `styles/{tokens,layout,components,login}.css` | 9 | ✅ split |
| `index.css` | Tailwind base + CSS variables | 63 | ✅ OK |

### Components (Shared)

| Component | File | Exports | Baris | Digunakan Di |
|-----------|------|---------|-------|-------------|
| `LoginScreen` | `LoginScreen.jsx` (re-export via CoreWidgets) | named export | 51 | `App.js` |
| `Sidebar` | `CoreWidgets.jsx:23` | named export | — | `App.js` |
| `TopBar` | `CoreWidgets.jsx:69` | named export | — | `App.js` |
| `PageSection` | `CoreWidgets.jsx:103` | named export | — | Multiple |
| `StatusPill` | `CoreWidgets.jsx:4` | named export | — | Multiple |
| `MetricCard` | `CoreWidgets.jsx:8` | named export | — | Multiple |
| `ProductCard` | `ProductCard.jsx` | default export | 91 | `SalesPortal` |
| `ProductDetail` | `ProductDetail.jsx` | default export | 135 | `SalesPortal` |
| `CartPanel` | `CartPanel.jsx` | default export | 116 | `SalesPortal` |
| `CustomerPanel` | `CustomerPanel.jsx` | default export | 160 | `SalesPortal` |
| `DetailDrawer` | `DetailDrawer.jsx` | default export | 21 | `App.js`, `OrdersView` |
| `LabelPrinterModal` | `LabelPrinterModal.jsx` | default export | 233 | `App.js` |
| `OnboardingPanel` | `OnboardingPanel.jsx` | default export | 57 | `App.js` |
| `GuidedTour` | `GuidedTour.jsx` | default export | 415 | `App.js` |
| `GuidedActionPanel` | `GuidedActionPanel.jsx` | default export | 23 | `App.js` |
| `TourMenu` | `TourMenu.jsx` | default export | 77 | `App.js` |

### Features

| Component | File | Props Kunci | Baris | Status |
|-----------|------|-------------|-------|--------|
| `AdminView` | `features/admin/AdminView.jsx` | `{user, products, customers, warehouses, uoms, users, token, ...}` | ~400 | ✅ OK |
| `PurchaseOrderManagement` | `features/admin/PurchaseOrderManagement.jsx` | `{user}` (sub: po/POCreateForm, po/PODetailPanel, po/POAmendModal, po/POVersionHistory, po/POTimeline) | 314 | ✅ OK |
| `POAmendModal` | `features/admin/po/POAmendModal.jsx` | **Phase 7.2** — form revisi PO (item/supplier/gudang/tgl/catatan + alasan wajib + guard partial-receiving + warning re-approval) | 291 | ✅ OK |
| `POVersionHistory` | `features/admin/po/POVersionHistory.jsx` | **Phase 7.2** — riwayat amandemen (snapshot + diff per versi, expandable) | 103 | ✅ OK |
| `DocumentsView` | `features/documents/DocumentsView.jsx` | `{templates, lastDocument, lastLabel, onGenerateLabel, products}` | ~350 | ✅ OK |
| `CycleCount` | `features/inventory/CycleCount.jsx` | `{token, warehouses, products, userRole}` | ~340 | ✅ OK |
| `EscalationManagement` | `features/manager/EscalationManagement.jsx` | `{user}` | ~280 | ✅ OK |
| `ManagerDashboard` | `features/manager/ManagerDashboard.jsx` | `{token}` | ~300 | ✅ OK |
| `OrderDashboard` | `features/orders/OrderDashboard.jsx` | `{orders, customers}` | ~263 | ✅ OK |
| `OrdersView` | `features/orders/OrdersView.jsx` | `{orders, customers, products, warehouses, token, user, ...}` | ~400 | ✅ OK |
| `SalesPortal` | `features/sales/SalesPortal.jsx` | `{products, customers, warehouses, user, token, ...}` | ~350 | ✅ OK |
| `PriceApprovals` | `features/sales/PriceApprovals.jsx` | `{currentUser}` | ~470 | ✅ OK (Sub-fase 1.7) |
| `InboundScanInterface` | `features/wms/InboundScanInterface.jsx` | `{user}` | ~400 | ✅ OK |
| `InventoryStockView` | `features/wms/InventoryStockView.jsx` (+ `inventory/` sub-components) | `{warehouses, products, user}` | 216 | ✅ refactored |
| `OperationsView` | `features/wms/OperationsView.jsx` | `{user, warehouses, products, orders, token, ...}` | ~350 | ✅ OK |
| `OutboundScanInterface` | `features/wms/OutboundScanInterface.jsx` | `{user}` | ~400 | ✅ OK |
| `ScannerTaskPanel` | `features/wms/ScannerTaskPanel.jsx` | `{tasks, products, warehouses, orders, ...}` | ~300 | ✅ OK |
| `TransferManagement` | `features/wms/TransferManagement.jsx` (+ `transfer/` sub-components) | `{user}` | 266 | ✅ refactored |

### Config & Utilities

| File | Exports | Fungsi | Baris |
|------|---------|---------|-------|
| `config/navigationConfig.js` | `PAGE_META`, `GUIDANCE_MAP`, `buildNavigation()`, `defaultViewForRole()` | Konfigurasi navigasi per role | 80 |
| `data/tourDefinitions.js` | `TOUR_DEFINITIONS` | Definisi 7 guided tours | 341 |
| `hooks/useAppActions.js` | `useAppActions(state)` | Semua API calls ke backend | 402 |
| `hooks/use-toast.js` | `useToast`, `toast` | Toast notification hook | 155 |
| `services/apiClient.js` | `api` (axios instance) | Axios base config, auth header | 10 |
| `utils/formatters.js` | `formatCurrency()`, `formatQty()` | Format angka IDR + qty | 2 |
| `lib/utils.js` | `cn()` | Tailwind class merger | 6 |

---

## 🔑 UTILITY FUNCTIONS — JANGAN RE-IMPLEMENT

### Backend (core_utils.py)
```python
now_iso()         → UTC timestamp ISO 8601 (SELALU pakai ini)
new_id(prefix)    → UUID dengan prefix: new_id("so") → "so_abc123def456"
safe_doc(doc)     → MongoDB doc → JSON-safe dict (strip _id, coerce ObjectId)
hash_password(pw) → SHA256 dengan salt "kain-nusantara::"
```

### Backend (dependencies.py)
```python
current_user(request)              → Dict user dari Bearer token
require_role(request, [roles])     → User atau raise 403
require_permission(request, mod, action) → User atau raise 403
audit(actor, action, entity_type, entity_id, after) → Write audit log
```

### Frontend (utils/formatters.js)
```javascript
formatCurrency(value)   → "Rp 185.000" (IDR format)
formatQty(value)        → "1.250,50" (ID number format)
```

### Frontend (lib/utils.js)
```javascript
cn(...inputs)   → twMerge(clsx(inputs)) — Tailwind class merger
```

### Frontend (hooks/useAppActions.js)
```javascript
useAppActions(state)   → {loadDashboard, loadProducts, loadOrders,
                          createOrder, approveOrder, confirmOrder, ...}
// Semua API calls sudah ada di sini
// JANGAN buat axios.get/post langsung di komponen
```

---

## 🔴 FILE YANG PERLU SEGERA DIREFACTOR

```
routers/outbound_picking.py  → 552 baris (MELEBIHI batas 800... mendekati)
App.css                      → 527 baris (mendekati batas 400... perlu split)
```

Dan file yang perlu dimonitor:
```
routers/inbound_receiving.py → 459 baris (pantau terus)
routers/transfers.py         → 442 baris (pantau terus)
routers/admin.py             → 352 baris (pantau terus)
hooks/useAppActions.js       → 402 baris (SUDAH melebihi batas 300 untuk utility)
GuidedTour.jsx               → 415 baris (mendekati batas 500)
```

---

## 📡 ALL API ENDPOINTS (Complete List)

```
GET  /api/                                           → Health check

AUTH
POST /api/auth/login                                 → Login
GET  /api/auth/me                                    → Current user
POST /api/auth/logout                                → Logout

USERS
GET  /api/users                                      → List users (admin)
POST /api/users                                      → Create user (admin)
PATCH /api/users/{user_id}                           → Update user (admin)

PRODUCTS
GET  /api/products                                   → List products
POST /api/products                                   → Create product
PATCH /api/products/{product_id}                     → Update product
DELETE /api/products/{product_id}                    → Deactivate product
GET  /api/products/{product_id}/stock-breakdown      → Stock per warehouse

CUSTOMERS
GET  /api/customers                                  → List customers
POST /api/customers                                  → Create customer
PATCH /api/customers/{customer_id}                   → Update customer
POST /api/customers/{customer_id}/addresses          → Add address

WAREHOUSES
GET  /api/warehouses                                 → List warehouses
POST /api/warehouses                                 → Create warehouse
PATCH /api/warehouses/{warehouse_id}                 → Update warehouse
DELETE /api/warehouses/{warehouse_id}                → Deactivate warehouse

UOMs
GET  /api/uoms                                       → List UOMs
POST /api/uoms                                       → Create UOM
PATCH /api/uoms/{uom_id}                             → Update UOM
DELETE /api/uoms/{uom_id}                            → Delete UOM

INVENTORY
GET  /api/inventory/balances                         → Stock balances
GET  /api/inventory/movements                        → Movement history
POST /api/inventory/initial-stock                    → Manual stock add
GET  /api/history/{product_id}                       → Product movement history

SALES ORDERS
GET  /api/sales-orders                               → List orders
GET  /api/sales-orders/stats/summary                 → Order statistics
POST /api/sales-orders                               → Create order (+ auto reserve)
GET  /api/sales-orders/{order_id}                    → Order detail
PATCH /api/sales-orders/{order_id}                   → Update order
POST /api/sales-orders/{order_id}/submit-for-approval
POST /api/sales-orders/{order_id}/approve
POST /api/sales-orders/{order_id}/confirm
POST /api/sales-orders/{order_id}/release-reservation
POST /api/sales-orders/{order_id}/cancel

INVOICES
GET  /api/invoices                                   → List invoices
GET  /api/sales-orders/{order_id}/invoices           → Invoices per order
POST /api/sales-orders/{order_id}/simulate-payment   → Simulate payment

WMS
GET  /api/wms/tasks                                  → List WMS tasks
POST /api/wms/tasks                                  → Create task
POST /api/wms/tasks/outbound-from-order/{order_id}   → Generate outbound from SO
POST /api/wms/tasks/{task_id}/scan                   → Scan item
POST /api/wms/tasks/{task_id}/advance                → Advance task status

INBOUND
GET  /api/inbound/tasks                              → List inbound tasks
POST /api/inbound/tasks/{task_id}/scan-receive       → Scan & receive item
POST /api/inbound/tasks/{task_id}/escalate           → Escalate task
POST /api/inbound/tasks/{task_id}/resolve-escalation → Resolve escalation
POST /api/inbound/tasks/{task_id}/complete           → Complete task
GET  /api/inbound/po/{po_id}/receiving-goods-document → GR document

OUTBOUND
GET  /api/outbound/tasks                             → List outbound tasks
POST /api/outbound/tasks/{task_id}/scan-pick         → Scan & pick item
POST /api/outbound/tasks/{task_id}/escalate          → Escalate task
POST /api/outbound/tasks/{task_id}/resolve-escalation
POST /api/outbound/tasks/{task_id}/dispatch          → Dispatch (complete outbound)
GET  /api/outbound/so/{order_id}/surat-jalan         → Generate surat jalan

TRANSFERS
GET  /api/transfers                                  → List transfers
POST /api/transfers                                  → Create transfer
GET  /api/transfers/{transfer_id}                    → Transfer detail
POST /api/transfers/{transfer_id}/approve
POST /api/transfers/{transfer_id}/reject
POST /api/transfers/{transfer_id}/status             → Update status
DELETE /api/transfers/{transfer_id}                  → Delete transfer

CYCLE COUNT
POST /api/cycle-count/sessions                       → Create session
GET  /api/cycle-count/sessions                       → List sessions
GET  /api/cycle-count/sessions/{session_id}
POST /api/cycle-count/sessions/{session_id}/items    → Add item
PATCH /api/cycle-count/sessions/{session_id}/items/{item_id}
POST /api/cycle-count/sessions/{session_id}/submit
POST /api/cycle-count/sessions/{session_id}/approve
POST /api/cycle-count/sessions/{session_id}/reject

PURCHASE ORDERS
GET  /api/purchase-orders                            → List POs
POST /api/purchase-orders                            → Create PO
GET  /api/purchase-orders/{po_id}                    → PO detail
POST /api/purchase-orders/{po_id}/cancel             → Cancel PO

DASHBOARD
GET  /api/dashboard                                  → Dashboard metrics

REPORTS
GET  /api/reports/stock-aging
GET  /api/reports/reservation-funnel
GET  /api/reports/order-velocity
GET  /api/reports/top-customers
GET  /api/reports/warehouse-utilization
GET  /api/reports/summary

DOCUMENTS
GET  /api/document-templates                         → List templates
POST /api/document-templates                         → Create template
PATCH /api/document-templates/{template_id}
DELETE /api/document-templates/{template_id}
POST /api/documents/generate                         → Generate document
GET  /api/documents/preview/{order_id}
POST /api/documents/barcode                          → Generate barcode

LABELS
POST /api/labels/generate                            → Generate label
POST /api/labels/preview                             → Preview label

ADMIN
POST /api/master-data/import-products
POST /api/master-data/import-customers
POST /api/master-data/import-warehouses
GET  /api/master-data/export-products
GET  /api/master-data/export-customers
GET  /api/master-data/export-warehouses
GET  /api/permissions                                → Get permission matrix
PUT  /api/permissions                                → Update permission matrix
POST /api/admin/seed-demo                            → Re-seed demo data

AUDIT
GET  /api/audit-logs                                 → List audit logs

ONBOARDING
GET  /api/onboarding                                 → Get user onboarding state
POST /api/onboarding/{task_id}/complete              → Complete onboarding task
POST /api/onboarding/reset                           → Reset onboarding
```

---

**Versi:** 1.0  
**Dibuat:** 28 Mei 2026  
**Update wajib:** Setiap kali ada file baru, endpoint baru, atau komponen baru
