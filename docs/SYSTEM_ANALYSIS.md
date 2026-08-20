# Kain Nusantara — Analisis Sistem Komprehensif

> Versi: 1.0 · Tanggal: November 2025
> Stack: **FastAPI** (Python) + **React 19** + **MongoDB** + **TailwindCSS / Shadcn UI**
> Domain: ERP + WMS untuk industri **kain tradisional Indonesia** (Batik, Tenun, Songket, Lurik, Ulos, Endek, Jumputan).

Dokumen ini berisi tiga bagian utama:
1. **Penilaian per modul** — apa yang sudah ada, kekuatan, kelemahan, dan gap.
2. **Potential Improvement** — perbaikan yang bisa dilakukan tanpa membangun modul baru.
3. **Future Enhancement / Roadmap Modul Baru** — peta jalan menuju **End-to-End ERP**.

---

## Bagian 0 · Konteks Bisnis & Persona Pengguna

### Persona

| Role | Kebutuhan Utama | Fokus UI |
|---|---|---|
| **Admin** | Manage master data, audit, kontrol penuh | Dense data, table-heavy |
| **Sales** | Bikin order cepat dari katalog POS | Visual katalog, search cepat |
| **Manager** | Approve, monitoring, decision-making | Dashboard, analytics, summary |
| **Warehouse** | Pick / pack / scan, fokus pada task list | Mobile-friendly, scanner-first |

### Karakter Industri Kain
- **Unit ukur tidak seragam** (meter, yard, roll, pcs) → butuh konversi UOM solid.
- **Variansi batch/lot/roll** signifikan → traceability wajib.
- **Defect rate cukup tinggi** (warna luntur, motif miring) → butuh QC robust.
- **Multi-warehouse umum** karena supplier tersebar (Cirebon, Solo, NTT, Bali, Palembang).
- **Banyak SKU kustom** (motif, warna, grade) → katalog harus fleksibel.

---

## Bagian 1 · Penilaian Per Modul

Setiap modul dinilai dengan tiga aspek:
- ✅ **Strengths** — apa yang sudah baik.
- ⚠️ **Gaps** — apa yang kurang atau tidak ada.
- 🎯 **Priority** — H (High), M (Medium), L (Low) untuk perbaikan.

### 1.1 Authentication & Identity

**Endpoint**: `/auth/login`, `/auth/me`, `/auth/logout`
**Routes**: `auth.py`, `users.py`, `permissions_config.py`

✅ **Strengths**
- Demo accounts per role (`admin`, `sales`, `manager`, `warehouse`).
- Role-based permission matrix (`permission_settings` collection) editable dari Admin Panel.
- Audit trail terintegrasi (siapa login, kapan).
- Bcrypt password hash.

⚠️ **Gaps**
- **No JWT refresh token** — session lifetime tidak dikelola.
- **No multi-factor authentication (MFA)** untuk admin/manager.
- **No password reset flow** (lupa password tidak ada).
- **No user invitation email** — admin harus set password manual untuk user baru.
- **No SSO / OAuth** (Google Workspace, Microsoft Azure AD).
- **No login attempt throttling** → rentan brute-force.

🎯 Priority: **M** (untuk MVP cukup, tapi wajib sebelum production scale-up)

### 1.2 Master Data Management

**Endpoint**: `/products`, `/customers`, `/warehouses`, `/uoms`, `/users`, `/document-templates`, import/export
**Routes**: `products.py`, `customers.py`, `warehouses.py`, `uoms.py`, `admin.py`

✅ **Strengths**
- 7 entitas master ter-CRUD lengkap.
- Toggle form di Admin UI agar tidak makan ruang (UX win).
- Import/export CSV untuk products, customers, warehouses.
- Soft-delete via status `inactive` → audit-safe.
- Product variant (color, motif, grade) sudah jadi first-class field.
- Warehouse → Zone → Rack → Bin hierarchy sudah ada di schema.

⚠️ **Gaps**
- **No bulk edit** (pilih banyak produk, update harga sekaligus).
- **No product image upload** — hanya URL Unsplash (rentan link rot di production).
- **No product bundling** (paket: kain + benang + label).
- **No supplier master** sebagai entitas terpisah — sekarang nama supplier hanya string di product/PO.
- **No customer segmentation** (tier, kredit limit, term of payment).
- **No product version history** — perubahan harga tidak terlacak per tanggal.
- **No category hierarchy** — kategori datar (Batik, Tenun) tanpa sub-kategori.
- **Validasi minim**: SKU bisa duplikat antar kategori; harga bisa minus.

🎯 Priority: **H** (supplier master & validation paling urgent)

### 1.3 Sales POS & Order Creation

**Endpoint**: `/sales-orders` POST, `/products` (catalog), `/customers`
**File frontend**: `App.js → SalesPortal`, `CartPanel`, `CustomerPanel`, `ProductCard`

✅ **Strengths**
- Katalog visual dengan stock real-time per warehouse.
- Dropdown customer (compact) — sudah di-improve dari card massif sebelumnya.
- Multi-warehouse auto-allocation dengan algoritma greedy.
- Reservasi otomatis 3 hari saat order created (status `reserved`).
- Workflow status lengkap: `reserved → waiting_approval → approved → confirmed → dispatched → done`.
- Release reservation manual button.
- Search produk + filter kategori sudah berjalan.

⚠️ **Gaps**
- **No quotation/proposal flow** — sales tidak bisa kirim penawaran sebelum order resmi.
- **No price negotiation field** — diskon hanya bisa diatur lewat edit harga produk (workaround buruk).
- **No customer credit check** sebelum confirm order.
- **No payment terms** (DP 30%, lunas 30 hari, dll).
- **No order draft auto-save** — kalau browser refresh sebelum submit, cart hilang.
- **No multi-currency** — semua IDR.
- **No order cloning** ("buat order baru dengan items yang sama dari order #X").
- **No backorder support** — kalau stock kurang, order tidak bisa dibuat.

🎯 Priority: **H** (quotation flow & diskon paling sering diminta)

### 1.4 Order Management & Approval

**Endpoint**: `/sales-orders`, `/sales-orders/{id}/approve|confirm|cancel`, `/sales-orders/{id}/release-reservation`
**File frontend**: `App.js → OrdersView`, `OrderDashboard.jsx`

✅ **Strengths**
- Tab "Dashboard & Analytics" (revenue, top customers, status distribution) + "Order List".
- Status timeline visual di panel detail.
- Filter by status + search by order/customer/produk.
- Stats summary (Total / Reserved / Confirmed / Done / Cancelled).
- Manual release reservation untuk order yang stuck.
- Reservation expiry (3 hari) untuk anti-stock-hoarding.

⚠️ **Gaps**
- **No approval workflow multi-step** — saat ini cuma "approve" / "confirm" tanpa hierarki (CFO sign-off untuk order >50jt, dll).
- **No order modification post-approval** — kalau customer revisi qty setelah approved, harus cancel & re-create.
- **No partial cancellation** (cancel 1 item dari order, sisanya jalan terus).
- **No automated reservation expiry job** — meskipun field `reservation_expires_at` ada, tidak ada cron yang clean-up.
- **No notification** ke sales/manager saat order baru masuk butuh approval.
- **No SLA tracker** (berapa lama dari created → approved → dispatched).
- **No export order list to Excel/PDF** (hanya per-order document).

🎯 Priority: **H** (auto-expiry job & notification paling urgent)

### 1.5 Warehouse Management System (WMS)

**Endpoint**: `/wms/tasks`, `/inbound/tasks`, `/outbound/tasks`, `/transfers`, `/cycle-count`
**File frontend**: `OperationsView` (tabs: Stok, Inbound, Outbound, Transfer, Cycle Count)

#### 1.5.1 Inventory / Stok Tab

✅ **Strengths**
- KPI cards: Total On Hand, Available, Reserved, Stok Rendah.
- Search by SKU/nama/gudang.
- Warehouse filter pills (Semua / per gudang).
- Tab Stok vs Ledger (movement history).
- Reserved details panel (klik produk → lihat order mana yang reserve).
- Tambah Stok manual untuk admin/manager (initial stock adjustment).

⚠️ **Gaps**
- **No re-order point / safety stock** alert otomatis.
- **No ABC/XYZ classification** (mana produk fast-moving vs slow-moving).
- **No inventory aging report** (berapa lama stock di rak).
- **No stock valuation method** (FIFO/LIFO/Weighted Average) tidak terpilih.
- **No expiry tracking** — meski produk kain biasanya tidak expired, tapi untuk benang/cat bisa relevan.
- **No bin-level inventory** — sekarang on_hand_qty per (product × warehouse), tidak per bin.

🎯 Priority: **M-H** (safety stock paling penting)

#### 1.5.2 Inbound Receiving

✅ **Strengths**
- 2-panel: list task kiri + scan panel kanan (compact).
- Status filter pills (Semua / Waiting / Receiving / QC / Escalated).
- Scan via input atau kamera (BarcodeDetector API).
- Multi-scan per task (pisahkan roll/batch/lot).
- Auto-advance status: `waiting_goods → receiving → qc_check`.
- Escalation flow (warehouse → manager review → resolve).
- Surat tanda terima auto-generate.

⚠️ **Gaps**
- **No QC checklist** — `qc_check` status ada tapi tidak ada form QC (defect type, sample count, pass/fail).
- **No return-to-supplier flow** untuk barang reject.
- **No put-away suggestion** (sistem rekomendasikan bin berdasarkan empty space + product affinity).
- **No supplier rating** otomatis dari accuracy receiving.
- **No PO match validation** — sistem percaya saja qty yang di-scan, tidak cross-check ke harga PO.

🎯 Priority: **H** (QC form paling kritikal untuk industri kain)

#### 1.5.3 Outbound Picking

✅ **Strengths**
- Mirror struktur inbound (compact 2-panel).
- Auto-create task saat order `confirmed`.
- Multi-scan dengan partial pick (kalau qty di rak kurang).
- Status: `created → picking → packing → staging → dispatched`.
- Tombol Dispatch hanya muncul ketika picked_qty ≥ quantity.
- Surat Jalan auto-generate setelah dispatch.

⚠️ **Gaps**
- **No wave/batch picking** — pick task harus dikerjakan satu per satu, tidak bisa group.
- **No pick optimization** (route optimization dalam gudang).
- **No packing material tracking** (kardus, plastik, bubble wrap).
- **No shipment consolidation** untuk multiple SO ke satu customer.
- **No carrier integration** (JNE, J&T, Sicepat) — Surat Jalan generic.
- **No proof of delivery (POD)** capture (signature, foto).

🎯 Priority: **M** (carrier integration paling impactful)

#### 1.5.4 Transfer Antar Gudang

✅ **Strengths**
- Workflow lengkap: `draft → waiting_approval → approved → in_transit → received`.
- Approval/reject dengan alasan.
- Linked ke inventory movements.

⚠️ **Gaps**
- **No transfer cost** allocation.
- **No estimated arrival date** vs actual.
- **No in-transit qty** yang muncul di reporting (visibility hilang antara dispatch & receive).

🎯 Priority: **L-M**

#### 1.5.5 Cycle Count

✅ **Strengths**
- Sesi cycle count dengan status flow.
- Submit → approve / reject untuk variance significant.
- Approval generate adjustment movement.

⚠️ **Gaps**
- **No blind count** (system tampilkan expected qty saat input → bias).
- **No cycle count schedule** (auto-create sesi mingguan/bulanan).
- **No variance threshold setting** per produk/kategori.
- **No counting by zone/bin** — sekarang per product saja.

🎯 Priority: **M**

### 1.6 Purchasing

**Endpoint**: `/purchase-orders`
**File frontend**: `App.js → Purchasing` (sederhana)

✅ **Strengths**
- PO multi-item dengan harga per unit.
- Auto-create inbound task saat PO created.
- Status: `pending → receiving → completed / partial / cancelled`.

⚠️ **Gaps**
- **No supplier master** — supplier hanya string nama.
- **No RFQ (Request for Quotation)** flow.
- **No PO approval workflow** untuk PO besar.
- **No payment to supplier tracking** (utang ke supplier).
- **No PO change order** — kalau supplier kirim beda qty, harus edit manual.
- **No 3-way matching** (PO ↔ Receipt ↔ Invoice supplier).

🎯 Priority: **H** (supplier master & RFQ paling penting)

### 1.7 Invoicing & Payment

**Endpoint**: `/invoices`, `/sales-orders/{id}/simulate-payment`
**File**: `routers/invoices.py`

✅ **Strengths**
- Auto-generate invoice saat order confirmed.
- Invoice number unik per tahun.
- Payment status `pending / paid` di order.

⚠️ **Gaps**
- **Payment SIMULATED** (`simulate-payment` endpoint) — tidak ada gateway real.
- **No partial payment** (DP 30%, sisanya saat dispatch).
- **No payment method** (transfer bank, kartu, e-wallet, COD).
- **No invoice email automation** ke customer.
- **No aging receivable report** (kapan invoice jatuh tempo, siapa overdue).
- **No credit note / refund** flow.
- **No tax (PPN 11%) configurable** — saat ini hardcoded 0.

🎯 Priority: **H** (tax + payment method paling urgent untuk compliance)

### 1.8 Documents & Print Center

**Endpoint**: `/documents/generate`, `/documents/preview`, `/labels/generate`
**File**: `routers/documents.py`, `label_printer.py`

✅ **Strengths**
- Template engine untuk Surat Jalan & Invoice.
- Field customization (header, footer, columns).
- Preview before print.
- Label printer untuk produk (barcode + SKU + nama).
- Print Center punya dropdown produk untuk batch label.

⚠️ **Gaps**
- **No PDF generation native** — saat ini HTML print only.
- **No watermark** (DRAFT, COPY, PAID).
- **No multi-language** (Indonesia / English).
- **No digital signature** for legal documents.
- **No archive of generated documents** (no audit trail of "siapa cetak Surat Jalan kapan").

🎯 Priority: **M** (PDF native & archive paling penting)

### 1.9 Reporting & Analytics

**Endpoint**: `/reports/*`, `/dashboard`
**File**: `routers/reporting.py`, `routers/dashboard.py`, `OrderDashboard.jsx`

✅ **Strengths**
- 6 jenis report: stock-aging, reservation-funnel, order-velocity, top-customers, warehouse-utilization, summary.
- Dashboard tab dengan timeframe selector (7/30/90 hari).
- Visual progress bar untuk status distribution.

⚠️ **Gaps**
- **No custom dashboard** per role/user.
- **No export report to Excel/PDF**.
- **No scheduled reports** (email mingguan ke manager).
- **No drill-down** (klik metric → lihat detail data).
- **No comparative period** (this month vs last month).
- **No forecasting** (next month projection berdasarkan trend).
- **No COGS / profit margin** report.

🎯 Priority: **M-H** (forecasting & profit margin penting untuk decision-making)

### 1.10 Smart Guidelines (Onboarding Tour)

**File**: `components/GuidedTour.jsx`, `data/tourDefinitions.js`

✅ **Strengths** *(baru di-refactor)*
- 7 tour berbeda dengan role-based access filter.
- Auto-navigate per step (klik elemen sidebar otomatis).
- Polling target sampai muncul (2.5s).
- Optional steps + center placement untuk info-only.
- CSS selector support untuk first-match elemen.
- Tooltip viewport clamping (tidak terpotong di edge).

⚠️ **Gaps**
- **No interactive practice mode** (mock data sandbox untuk training).
- **No video tooltip** option.
- **No analytics**: tour mana yang paling sering ditonton/diskip.
- **No multi-language**.

🎯 Priority: **L** (sudah cukup untuk MVP)

### 1.11 Escalation Management

**Endpoint**: bagian dari inbound/outbound + transfers
**File frontend**: `EscalationsView` di sidebar

✅ **Strengths**
- Escalation per task (qty kurang, defect, dll).
- Reason + resolution notes.
- Linked ke audit log.

⚠️ **Gaps**
- **No SLA timer** untuk escalation (kapan harus resolve).
- **No escalation routing** (manager warehouse vs procurement vs finance).
- **No escalation analytics** (root cause analysis).

🎯 Priority: **M**

### 1.12 Audit Trail

**Endpoint**: `/audit-logs`
**File**: `routers/audit.py`

✅ **Strengths**
- Setiap aksi tercatat (user, action, resource, timestamp, details).
- Filter & search di Admin > Audit tab.
- Tidak bisa di-edit/hapus (immutable).

⚠️ **Gaps**
- **No retention policy** (sampai berapa lama log disimpan).
- **No tamper detection** (cryptographic hash chain).
- **No export untuk audit eksternal**.

🎯 Priority: **L** (sudah cukup baik)

---

## Bagian 2 · Potential Improvement (Quick Wins & Mid-Term)

Daftar improvement yang **TIDAK butuh modul baru** — bisa dieksekusi dalam 1-3 sprint.

### A · Quick Wins (≤1 sprint, high impact)

| # | Improvement | Modul | Effort | Impact |
|---|---|---|---|---|
| A1 | **Validasi master data**: SKU unique, harga ≥0, email regex, phone format | Master Data | XS | H |
| A2 | **Auto-reservation expiry job** (cron hourly): kembalikan reserved_qty saat expires_at lewat | Orders | S | H |
| A3 | **Discount field** per item di POS (% atau Rp) | Sales POS | S | H |
| A4 | **Tax 11% PPN configurable** di settings, auto-applied ke invoice | Invoice | S | H |
| A5 | **PDF native** via `weasyprint` untuk Surat Jalan & Invoice (tidak lagi HTML print) | Documents | S | M |
| A6 | **Order draft auto-save** ke localStorage tiap 5 detik | Sales POS | XS | M |
| A7 | **Order cloning** ("create from existing order") | Orders | XS | M |
| A8 | **Export to Excel** untuk Orders, Inventory, Reports | Reporting | S | H |
| A9 | **Safety stock & reorder point** field di product → alert di dashboard | Inventory | S | H |
| A10 | **Reserved details popover** lebih detail (order_number, customer, expiry) | Inventory | XS | M |

### B · Mid-Term (1-3 sprint)

| # | Improvement | Modul | Effort | Impact |
|---|---|---|---|---|
| B1 | **Supplier Master** sebagai entitas terpisah (CRUD + linked ke produk/PO) | Master Data | M | H |
| B2 | **QC Form** dengan checklist (defect type, sample count, pass/fail) | Inbound | M | H |
| B3 | **Quotation flow** (Sales bisa kirim penawaran sebelum jadi order) | Sales | L | H |
| B4 | **Approval workflow multi-step** (bisa setting "approval bertingkat" per nilai order) | Orders | M | M |
| B5 | **Partial payment + payment method** (DP, cash, transfer, e-wallet) | Invoice | L | H |
| B6 | **Aging receivable report** + dashboard widget invoice overdue | Reporting | M | H |
| B7 | **Notification system** (in-app toast + email): order baru, escalation, low stock | Cross | L | H |
| B8 | **Carrier integration** dummy: input AWB number manual, link ke surat jalan | Outbound | M | M |
| B9 | **Bulk edit** master data (multi-select & update qty/harga) | Master Data | M | M |
| B10 | **Drill-down report** (klik metric dashboard → detail list) | Reporting | M | M |

### C · Cross-Cutting (foundational)

| # | Improvement | Effort | Impact |
|---|---|---|---|
| C1 | **JWT refresh token + session timeout** | M | H |
| C2 | **Login attempt throttling** (block IP after 5 failed) | S | H |
| C3 | **Password reset via email** | M | H |
| C4 | **Real-time updates via WebSocket** (orders, inventory) — bukan polling | L | M |
| C5 | **Backend test suite** (pytest) untuk regression safety | L | H |
| C6 | **API rate limiting** (max 100 req/min per user) | S | M |
| C7 | **Image upload service** (S3-compatible) → ganti Unsplash URL | M | M |
| C8 | **Multi-tenancy support** (organization_id di setiap collection) — kalau mau jadi SaaS | XL | H |

---

## Bagian 3 · Future Enhancement: Modul Baru untuk End-to-End ERP

Berikut adalah peta jalan **modul tambahan** agar Kain Nusantara menjadi solusi ERP lengkap dari hulu ke hilir.

### Tier 1 · Modul Wajib untuk ERP (Operational Backbone)

#### 🏭 Modul: **Production / Manufacturing** *(opsional untuk pabrik kain)*
**Tujuan**: Track raw material → work-in-progress → finished goods.
- Bill of Materials (BOM) per produk (benang × meter, pewarna × ml, dll).
- Work Order (WO) management.
- Production scheduling (Gantt chart).
- Shop floor scanning (operator scan WO + qty produced).
- Production cost roll-up (material + labor + overhead).
- **Integrasi**: Stock dari raw material → buyer produk jadi.

**Effort**: XL (3-4 bulan) — paling kompleks.
**Trigger**: Kalau Kain Nusantara melakukan produksi sendiri, bukan hanya trading.

#### 💰 Modul: **Finance & Accounting (GL)**
**Tujuan**: General Ledger lengkap dengan Chart of Accounts.
- Chart of Accounts (COA) hierarchical.
- Journal entries auto-posted dari trx (sales, PO, payment, payroll).
- Trial Balance, Income Statement, Balance Sheet, Cash Flow.
- Multi-period (year-end closing).
- Cost center & department tracking.
- Tax reporting (PPN, PPh 21, PPh 23).
- **Integrasi**: Setiap dispatch SO → debit Cost of Goods Sold + credit Inventory. Setiap PO receive → debit Inventory + credit Accounts Payable.

**Effort**: XL (3-4 bulan).
**Trigger**: Untuk kepatuhan akuntansi & audit.

#### 💸 Modul: **Accounts Payable / Receivable (AP/AR)**
**Tujuan**: Manage utang ke supplier & piutang dari customer.
- AP: bills from supplier, payment scheduling, supplier statement.
- AR: customer invoices (sudah ada), payment receipts, collection follow-up.
- Aging report (0-30, 31-60, 61-90, 90+ days).
- Auto-reminder email untuk overdue invoices.
- Credit limit check per customer (block order kalau exceed).
- **Integrasi**: GL posting otomatis. Dashboard cashflow projection.

**Effort**: L (2 bulan).
**Trigger**: Wajib begitu volume transaksi >100/bulan.

#### 🚚 Modul: **Logistics / Shipping**
**Tujuan**: Manage proses pengiriman end-to-end.
- Carrier master (JNE, J&T, Sicepat, internal fleet).
- Shipment consolidation (gabung multiple SO ke 1 shipment).
- Route planning untuk armada sendiri.
- AWB generation + tracking link.
- Proof of Delivery (signature + foto via mobile app).
- Cost allocation (ongkir per shipment ke COGS).
- Customer notification SMS/email (paket dalam perjalanan).
- **Integrasi**: Dari Outbound Picking → Shipment → POD → invoice closed.

**Effort**: M-L (1.5-2 bulan).

### Tier 2 · Modul Pendukung Pertumbuhan

#### 👥 Modul: **CRM (Customer Relationship Management)**
- Lead capture & qualification.
- Sales pipeline (lead → qualified → proposal → won/lost).
- Activity tracking (call, email, meeting per customer).
- Customer 360° (history order, complaint, payment behavior).
- Marketing campaign (segmentasi customer untuk promo).
- Loyalty program (poin per pembelian, tier customer).
- **Integrasi**: Lead → Quotation → Sales Order.

**Effort**: L (2 bulan).

#### 👷 Modul: **HRIS (Human Resource Information System)**
- Employee master (data karyawan, kontrak, dokumen).
- Attendance (clock-in via mobile + GPS / fingerprint).
- Leave management (cuti tahunan, sakit, dll).
- Payroll engine (gaji + tunjangan + PPh 21 + BPJS).
- Performance review.
- **Integrasi**: Cost ke GL (gaji + tunjangan = expense). Linked ke user system.

**Effort**: XL (3 bulan).

#### 📊 Modul: **Business Intelligence (BI) / Advanced Analytics**
- Custom dashboard builder (drag-drop widgets).
- Data warehouse (offload dari operational DB).
- Predictive analytics (demand forecasting per produk).
- ABC/XYZ analysis automation.
- Customer churn prediction.
- Export ke Power BI / Tableau / Metabase.
- **Integrasi**: ETL dari semua modul ke data lake.

**Effort**: L (2 bulan) — bisa pakai existing tool seperti Metabase.

#### 🛒 Modul: **E-Commerce / B2B Portal**
- Self-service portal untuk customer (login, lihat catalog, place order).
- Real-time stock check dari customer side.
- Order history & invoice download.
- Online payment gateway (Midtrans, Xendit) — *NOTE: User sudah cancel payment integration, ini opsional.*
- API integration ke marketplace (Tokopedia, Shopee, Tiktok Shop).
- **Integrasi**: Portal order → masuk sebagai SO dengan flag "online".

**Effort**: L (2-3 bulan).

### Tier 3 · Modul Strategis Jangka Panjang

#### 📦 Modul: **Supply Chain Optimization**
- Demand forecasting (ML-based).
- Auto-replenishment suggestion (kapan & berapa harus order ke supplier).
- Supplier scoring (on-time delivery, defect rate).
- Multi-echelon inventory optimization (warehouse jaringan).
- **Effort**: XL (3-4 bulan, butuh data historis 1+ tahun).

#### 🌱 Modul: **Sustainability / ESG Tracking**
- Carbon footprint per produk (sourcing → shipping).
- Material origin traceability (penting untuk batik authentic).
- Fair trade compliance untuk pengrajin tradisional.
- **Effort**: M (1-2 bulan).
- **Trigger**: Untuk ekspor ke EU (CBAM regulation).

#### 🔐 Modul: **Document Management System (DMS)**
- Upload & tag dokumen (contract, invoice supplier, kuitansi).
- Version control.
- E-signature integration (PrivyID, Mekari Sign).
- Retention & archival policy.
- **Effort**: M (1.5 bulan).

#### 🤖 Modul: **AI Assistant**
- Chatbot natural language: "Berapa stock batik mega di Jakarta?" → langsung jawab.
- Auto-categorize new products via image recognition.
- Defect detection di QC dari foto.
- Demand forecasting via LLM + historical data.
- **Effort**: M-L (2-3 bulan, leverage Emergent LLM key).

---

## Bagian 4 · Rekomendasi Eksekusi (Sequencing)

### Phase 1 (Sprint 1-2) — *Stabilisasi & Quick Wins*
1. **A1**: Validasi master data
2. **A2**: Auto-reservation expiry cron job
3. **A3**: Discount field di POS
4. **A4**: Tax PPN 11% configurable
5. **A6**: Order draft auto-save
6. **A9**: Safety stock + reorder alert
7. **C1, C2, C3**: JWT refresh, throttling, password reset

### Phase 2 (Sprint 3-5) — *Capability Expansion*
8. **B1**: Supplier Master
9. **B2**: QC Form untuk inbound
10. **B3**: Quotation flow
11. **B5**: Partial payment + payment methods
12. **B7**: Notification system (toast + email)
13. **A5, A8**: PDF native + Excel export

### Phase 3 (Sprint 6-9) — *Tier 1 Modul ERP*
14. **AP/AR module** — utang piutang lengkap
15. **Logistics module** — carrier integration + POD
16. **Finance/Accounting GL** — siapkan COA & journal posting

### Phase 4 (Sprint 10+) — *Pertumbuhan*
17. CRM
18. HRIS (jika tim sudah >20 orang)
19. BI / Custom Dashboards
20. E-Commerce Portal

### Phase 5 (Strategis) — *Diferensiasi*
21. Supply Chain Optimization (ML forecasting)
22. AI Assistant (LLM-powered insights)
23. Sustainability/ESG (untuk ekspor)
24. Production (jika mulai manufaktur)

---

## Bagian 5 · KPI untuk Mengukur Keberhasilan

Untuk setiap modul yang ditambahkan, ukur dengan:

| Metric | Target Awal | Target 6 Bulan |
|---|---|---|
| **Order Cycle Time** (created → dispatched) | <3 hari | <1.5 hari |
| **Stock Accuracy** (sistem vs fisik) | >95% | >99% |
| **Order Fulfillment Rate** (qty terkirim / qty order) | >90% | >98% |
| **Reservation Expiry Rate** | <5% | <2% |
| **Invoice Aging >60d** | <15% | <5% |
| **User Adoption** (active users / total users) | 60% | 90% |
| **Tour Completion Rate** | 30% | 70% |
| **Page Load Time** (P95) | <2s | <800ms |

---

## Bagian 6 · Kesimpulan

**Kain Nusantara saat ini** adalah **WMS + Order Management yang sangat solid** untuk industri kain — sudah punya:
- ✅ End-to-end flow: Purchase → Inbound → Stock → Sales Order → Approval → Outbound → Dispatch.
- ✅ Multi-warehouse + multi-role + audit trail.
- ✅ UI yang compact, modern, accessible.
- ✅ Onboarding tour interaktif role-based.

**Yang membuat ini BELUM jadi ERP penuh**:
- ❌ Tidak ada GL/Accounting (semua trx tidak posted ke buku besar).
- ❌ Tidak ada AP/AR module (utang piutang manual).
- ❌ Tidak ada Logistics (shipment & POD).
- ❌ Tidak ada CRM (lead → quotation → opportunity).
- ❌ Tidak ada HRIS.

**Roadmap menuju End-to-End ERP**:
1. **Q1 2026** → Stabilisasi (Phase 1 + 2)
2. **Q2 2026** → AP/AR + Logistics (Tier 1)
3. **Q3 2026** → GL/Accounting + Finance reporting
4. **Q4 2026** → CRM + E-Commerce Portal
5. **2027+** → HRIS, BI advanced, AI Assistant, Production

Dengan urutan ini, Kain Nusantara bisa berevolusi dari **WMS specialist** menjadi **textile-vertical ERP platform** yang siap di-spin-off jadi produk SaaS untuk industri tekstil Indonesia.

---

*Dokumen ini akan direvisi setiap kuartal seiring evolusi sistem dan kebutuhan bisnis.*
