# Assessment Implementasi ERP PT. Kain Nusantara
## **COMPREHENSIVE EDITION — Part 2 (Domain 3.3 - 15)**

---

## 3.3 PROCESS C — Sales & Distribution (Order to Cash) ⚡ (Lanjutan)

### 3.3.1 Customer Master Data

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Total Active Customers** | Jumlah customer aktif (transaksi 3 bulan terakhir) | __ customers | ☐ |
| **Customer Classification** | Retail / Wholesale / Corporate / Government / Export | | ☐ |
| **Customer Segmentation** | A (VIP) / B (Regular) / C (Occasional) by revenue | | ☐ |
| **Top 10 Customer Revenue** | % dari total revenue | __% | ☐ |
| **Credit Term Variety** | Berapa macam credit term? (COD, Net 30, Net 60, etc.) | __ types | ☐ |
| **Credit Limit Management** | Apakah perlu credit limit per customer? | ☐ Yes ☐ No | ☐ |
| **Credit Limit Calculation** | Based on apa? (Revenue history, Risk assessment, Manual) | | ☐ |
| **Credit Check Timing** | Saat order entry / Saat approval / Saat delivery | | ☐ |
| **Over-limit Handling** | Allow over-limit dengan approval atau block order? | | ☐ |
| **Pricing Strategy** | Fixed price / Customer-specific / Volume discount / Negotiated | | ☐ |
| **Discount Structure** | Apakah ada multi-tier discount? | ☐ Yes ☐ No | ☐ |
| **Contract Customer** | Apakah ada customer dengan contract price? | ☐ Yes ☐ No | ☐ |
| **Multi-Address Customer** | 1 customer bisa punya banyak ship-to address? | ☐ Yes ☐ No | ☐ |
| **Consignment Customer** | Apakah ada customer consignment? | ☐ Yes ☐ No | ☐ |

**Customer Credit Term Matrix:**

| Customer Segment | Credit Term | Credit Limit | Payment Method | Auto-Approval |
|------------------|-------------|--------------|----------------|---------------|
| A (VIP) | Net 60 | Rp _______ | Transfer/Giro | Yes |
| B (Regular) | Net 30 | Rp _______ | Transfer/Giro | Conditional |
| C (Occasional) | Net 15 | Rp _______ | Transfer/COD | No |
| New Customer | COD | Rp 0 | Cash/Transfer | No |
| Government | Net 90 | No limit | Transfer | Yes |
| Export | LC/TT | Case by case | LC/Wire | No |

### 3.3.2 Quotation & Pricing Process

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Quotation Mandatory?** | Apakah semua order harus ada quotation dulu? | ☐ Always ☐ Optional | ☐ |
| **Quotation Creator** | Siapa yang bisa buat quotation? (Sales / Sales Admin) | | ☐ |
| **Quotation Approval** | Apakah quotation perlu approval? | ☐ Yes ☐ No | ☐ |
| **Discount Authority** | Siapa yang bisa approve discount? | | ☐ |
| **Maximum Discount** | Berapa % max discount tanpa approval? | __% | ☐ |
| **Price Validity** | Berapa hari quotation berlaku? | __ hari | ☐ |
| **Quotation to SO** | Otomatis convert atau manual re-entry? | | ☐ |
| **Quotation Revision** | Allow quotation revision? Berapa kali? | __ kali | ☐ |
| **Competitor Price** | Apakah sales perlu input competitor price? | ☐ Yes ☐ No | ☐ |

**Pricing Approval Matrix:**

| Discount Level | Approve By | Max Lead Time | Escalation |
|----------------|------------|---------------|------------|
| 0-5% | Sales Rep | Auto | — |
| 5-10% | Sales Supervisor | 2 hours | Sales Manager |
| 10-15% | Sales Manager | 4 hours | Sales Director |
| 15-20% | Sales Director | 8 hours | CEO |
| > 20% | CEO | 1 day | Board |

### 3.3.3 Sales Order (SO) Process Flow ⚡

**SO Creation:**

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Order Entry Channel** | Walk-in / Phone / Email / WhatsApp / Sales visit / E-commerce | | ☐ |
| **Order Entry By** | Sales / Sales admin / Customer service / Auto (e-commerce) | | ☐ |
| **Mandatory Fields** | Apa saja field mandatory di SO? | | ☐ |
| **Price Source** | Price list / Contract / Manual / Last transaction | | ☐ |
| **Stock Check** | Real-time stock check saat order entry? | ☐ Yes ☐ No | ☐ |
| **Multi-Warehouse SO** | 1 SO bisa pick dari multiple warehouse? | ☐ Yes ☐ No | ☐ |
| **Warehouse Assignment** | Otomatis (by location) atau manual pilih warehouse? | | ☐ |
| **Stock Reservation** | Reserve saat SO created atau saat approved? | | ☐ |
| **Insufficient Stock** | Allow back order / Partial order / Block order | | ☐ |
| **Order Priority** | Apakah ada priority order (Urgent, Normal, Low)? | ☐ Yes ☐ No | ☐ |
| **Delivery Schedule** | Customer bisa request delivery date? | ☐ Yes ☐ No | ☐ |
| **Earliest Delivery** | Berapa hari lead time minimum? | __ hari | ☐ |
| **Packaging Instruction** | Apakah ada special packaging per customer? | ☐ Yes ☐ No | ☐ |
| **Shipping Method** | Own truck / 3PL / Customer pickup / Courier | | ☐ |

**SO Approval Matrix:**

| SO Amount | Customer Type | Approve Level 1 | Approve Level 2 | Approve Level 3 | Max Lead Time |
|-----------|---------------|-----------------|-----------------|-----------------|---------------|
| < Rp 10jt | Existing (Good credit) | Auto | — | — | 0 hours |
| < Rp 10jt | New / Bad credit | Sales Supervisor | — | — | 2 hours |
| Rp 10-50jt | Any | Sales Supervisor | Sales Manager | — | 4 hours |
| Rp 50-100jt | Any | Sales Manager | Sales Director | — | 8 hours |
| > Rp 100jt | Any | Sales Director | Finance Director | CEO | 1 day |
| Special Price/Discount | Any | Sales Manager | Sales Director | — | 4 hours |
| Over Credit Limit | Any | Sales Manager | Finance Manager | — | 4 hours |

**SO Status Lifecycle:**

```
[Draft] → [Pending Approval] → [Approved] → [Stock Reserved] → 
[Picking in Progress] → [Ready to Ship] → [Shipped] → [Delivered] → [Invoiced] → [Paid] → [Closed]
```

**Exception Handling:**

| Exception | Action | Approval Required | Alternative Flow |
|-----------|--------|-------------------|------------------|
| Stock tidak cukup | Create Back Order / Partial Delivery / Cancel | Sales Manager | Alternative product offering |
| Credit limit exceeded | Hold order / Request approval / Advance payment | Finance Manager | Customer payment first |
| Customer blocked | Block order | Sales Director | Clear outstanding first |
| Special request (packaging, delivery) | Manual handling | Operations Manager | Standard handling |
| Price below minimum | Reject / Request approval | Sales Director | Price adjustment |
| Urgent delivery | Priority processing | Operations Manager | Express handling |

### 3.3.4 Picking & Packing Process

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Pick List Generation** | Otomatis dari SO atau manual create? | | ☐ |
| **Picking Strategy** | FIFO / FEFO / Location-based / Batch picking | | ☐ |
| **Picker Assignment** | Otomatis assign atau manual? | | ☐ |
| **Picking Tool** | Paper / Handheld / RFID / Mix | | ☐ |
| **Pick Confirmation** | Scan barcode / RFID / Manual check | | ☐ |
| **Pick Accuracy Target** | Target akurasi picking | ≥ __% | ☐ |
| **Packing SOP** | Apakah ada SOP packing per product type? | ☐ Yes ☐ No | ☐ |
| **Packing Material** | Apakah system track packing material usage? | ☐ Yes ☐ No | ☐ |
| **Final QC** | Apakah ada final QC before ship? | ☐ Yes ☐ No | ☐ |
| **Labeling** | Barcode label / RFID label / Address label | | ☐ |
| **Weight & Dimension** | Apakah perlu record weight & dimension? | ☐ Yes ☐ No | ☐ |

### 3.3.5 Delivery & Shipping Process

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Delivery Method** | Own fleet / 3PL / Customer pickup / Courier | | ☐ |
| **Delivery Note (Surat Jalan)** | Auto generate dari SO atau manual? | | ☐ |
| **DN Required Info** | Apa saja info mandatory di Delivery Note? | | ☐ |
| **DN Approval** | Siapa yang approve DN? | | ☐ |
| **Loading Dock** | Berapa loading dock? Perlu schedule? | __ docks | ☐ |
| **Vehicle Capacity Planning** | Apakah perlu optimize loading per vehicle? | ☐ Yes ☐ No | ☐ |
| **Route Planning** | Manual route atau system suggest? | | ☐ |
| **Driver Assignment** | Otomatis atau manual? | | ☐ |
| **Delivery Tracking** | Real-time GPS tracking? | ☐ Yes ☐ No | ☐ |
| **POD (Proof of Delivery)** | Photo / Signature / Stamp / Digital | | ☐ |
| **POD Integration** | POD masuk ke system atau manual update? | | ☐ |
| **Failed Delivery** | Proses handling failed delivery | | ☐ |
| **Delivery Cost** | Cost per delivery atau flat rate? | | ☐ |
| **COD Handling** | Apakah ada COD? Process collection? | ☐ Yes ☐ No | ☐ |

**Delivery SLA Matrix:**

| Customer Segment | Location | Delivery SLA | Cost | On-Time Rate Target |
|------------------|----------|--------------|------|---------------------|
| A (VIP) | Same city | Next day | Free | ≥ 99% |
| A (VIP) | Out of city | 2-3 days | Free | ≥ 98% |
| B (Regular) | Same city | 2-3 days | Standard | ≥ 95% |
| B (Regular) | Out of city | 4-5 days | Standard | ≥ 95% |
| C (Occasional) | Any | 5-7 days | Standard | ≥ 90% |

### 3.3.6 Invoicing & Payment Collection

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Invoice Trigger** | DN / Delivery complete / POD received | | ☐ |
| **Invoice Generation** | Otomatis atau manual? | | ☐ |
| **Invoice Format** | Tax invoice / Proforma / Commercial invoice | | ☐ |
| **Tax Calculation** | PPN 11% auto calculate? | ☐ Yes ☐ No | ☐ |
| **Invoice Approval** | Siapa yang approve invoice? | | ☐ |
| **Invoice Delivery** | Email / Print / E-Faktur / Portal | | ☐ |
| **Payment Method** | Transfer / Giro / Cash / Virtual account / Mix | | ☐ |
| **Payment Allocation** | Otomatis match invoice atau manual? | | ☐ |
| **Payment Confirmation** | Customer upload bukti atau admin input? | | ☐ |
| **AR Ageing Report** | Perlu daily / weekly / monthly? | | ☐ |
| **Collection Process** | Apakah ada collection team? SOP? | ☐ Yes ☐ No | ☐ |
| **Overdue Action** | Reminder / Block order / Penalty interest | | ☐ |
| **Bad Debt Provision** | Berapa hari overdue → bad debt? | __ hari | ☐ |

**Payment Term & Follow-up SOP:**

| Days Overdue | Action | Responsible | Escalation |
|--------------|--------|-------------|------------|
| Day 0 (Due date) | Courtesy reminder via WA/Email | AR Admin | — |
| +1 to +7 days | Daily reminder + Phone call | AR Admin | — |
| +8 to +14 days | Formal letter + Block new order | Collection Officer | AR Manager |
| +15 to +30 days | Management involvement | AR Manager | Finance Director |
| +31 to +60 days | Legal warning letter | Finance Director | CEO |
| +60 days | Legal action consideration | CEO | Legal team |

### 3.3.7 Customer Return & Credit Note

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Return Reason** | Defect / Wrong item / Excess / Damaged / Expired | | ☐ |
| **Return SLA** | Berapa hari max untuk retur sejak delivery? | __ hari | ☐ |
| **Return Authorization** | Siapa yang approve retur? | | ☐ |
| **Return Process** | Customer kirim balik atau pickup? | | ☐ |
| **Return Cost** | Company / Customer / Supplier | | ☐ |
| **Return Inspection** | QC inspection saat barang kembali? | ☐ Yes ☐ No | ☐ |
| **Stock Treatment** | Return to stock / Quarantine / Scrap | | ☐ |
| **Credit Note** | Otomatis atau manual? | | ☐ |
| **Refund Method** | Cash / Transfer / Credit untuk order berikutnya | | ☐ |
| **Refund Timeline** | Berapa hari process refund? | __ hari | ☐ |

### 3.3.8 Sales Performance KPIs

| KPI | Current | Target | Measurement | Owner |
|-----|---------|--------|-------------|-------|
| **Sales Growth Rate** | __% YoY | __% YoY | Monthly | Sales Director |
| **Average Order Value** | Rp _______ | Rp _______ | Monthly | Sales Manager |
| **Order Fulfillment Rate** | __% | ≥ 98% | Daily | Operations |
| **On-Time Delivery** | __% | ≥ 98% | Daily | Logistics |
| **Order Accuracy** | __% | ≥ 99.5% | Daily | Warehouse |
| **Customer Satisfaction Score** | __/10 | ≥ 8.5/10 | Monthly | Customer Service |
| **Sales per Rep** | Rp _______/month | Rp _______/month | Monthly | Sales Manager |
| **Quotation Win Rate** | __% | ≥ __% | Monthly | Sales Manager |
| **Days Sales Outstanding (DSO)** | __ days | ≤ __ days | Monthly | Finance |
| **Customer Retention Rate** | __% | ≥ 85% | Quarterly | Sales Director |
| **Customer Complaint Rate** | __ per 1000 orders | ≤ 5 | Monthly | Customer Service |
| **Return Rate** | __% | ≤ 2% | Monthly | Quality Manager |

---

## 3.4 PROCESS D — Production & Manufacturing ⚡

> **Assessment Goal:** Map production process dari raw material hingga finished goods, termasuk BOM, work order, capacity planning, dan quality control.

### 3.4.1 Production Type & Model

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Production Model** | Make-to-Stock / Make-to-Order / Assemble-to-Order / Engineer-to-Order | | ☐ |
| **Production Type** | Batch / Continuous / Job shop / Mixed | | ☐ |
| **Production Lead Time** | Average production lead time | __ hari | ☐ |
| **Production Capacity** | Total capacity (ton/month, meter/month, roll/month) | | ☐ |
| **Capacity Utilization** | Current utilization rate | __% | ☐ |
| **Number of Production Lines** | Jumlah production line | __ lines | ☐ |
| **Shift Pattern** | 1 shift / 2 shifts / 3 shifts / 24/7 | | ☐ |
| **Number of Machines** | Total mesin produksi | __ mesin | ☐ |
| **Bottleneck Process** | Proses mana yang bottleneck? | | ☐ |

### 3.4.2 Bill of Material (BOM) & Recipe

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **BOM Structure** | Single-level / Multi-level / Configurable | | ☐ |
| **BOM Complexity** | Simple (1-5 components) / Complex (>10 components) | | ☐ |
| **BOM Version Control** | Apakah perlu track BOM version? | ☐ Yes ☐ No | ☐ |
| **BOM Approval** | Siapa yang approve BOM? | | ☐ |
| **Alternative Material** | Apakah ada alternative material/component? | ☐ Yes ☐ No | ☐ |
| **By-Product** | Apakah ada by-product dari production? | ☐ Yes ☐ No | ☐ |
| **Co-Product** | Apakah ada co-product? | ☐ Yes ☐ No | ☐ |
| **Scrap/Waste Rate** | Standard waste rate | __% | ☐ |
| **Yield Rate** | Standard yield | __% | ☐ |

**BOM Sample (untuk 1 product):**

| Component | Description | Qty per Unit | UOM | Scrap % | Lead Time | Critical? |
|-----------|-------------|--------------|-----|---------|-----------|-----------|
| Raw Material 1 | | | | | | ☐ |
| Raw Material 2 | | | | | | ☐ |
| Component A | | | | | | ☐ |
| Packing Material | | | | | | ☐ |

### 3.4.3 Production Planning Process

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Planning Method** | MRP / MPS / Manual / Forecast-based | | ☐ |
| **Planning Horizon** | Berapa bulan planning horizon? | __ bulan | ☐ |
| **Planning Frequency** | Daily / Weekly / Monthly | | ☐ |
| **Demand Source** | Sales forecast / Actual orders / Min-max stock | | ☐ |
| **Safety Stock** | Apakah ada safety stock FG? | ☐ Yes ☐ No | ☐ |
| **Lot Sizing** | Fixed lot / EOQ / Campaign based | | ☐ |
| **Minimum Batch** | Minimum production batch size | | ☐ |
| **Setup Time** | Average setup time per production run | __ jam | ☐ |

### 3.4.4 Work Order Process

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **WO Creation** | Otomatis dari MRP atau manual? | | ☐ |
| **WO Approval** | Siapa yang approve WO? | | ☐ |
| **Material Reservation** | Reserve material saat WO created atau saat start? | | ☐ |
| **Material Issue** | Backflush atau manual issue? | | ☐ |
| **WO Tracking** | Real-time tracking atau end-of-day reporting? | | ☐ |
| **Operation Routing** | Apakah ada routing (step by step production)? | ☐ Yes ☐ No | ☐ |
| **Labor Tracking** | Track labor hours per WO? | ☐ Yes ☐ No | ☐ |
| **Machine Tracking** | Track machine hours per WO? | ☐ Yes ☐ No | ☐ |
| **Quality Check Point** | QC di step mana? (In-process / Final) | | ☐ |
| **WO Completion** | Complete saat semua qty finished atau allow partial? | | ☐ |

**WO Status Lifecycle:**

```
[Planned] → [Released] → [Material Issued] → [In Production] → 
[QC Inspection] → [Completed] → [Finished Goods Receipt] → [Closed]
```

### 3.4.5 Quality Control (QC) Process

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **QC Type** | Incoming / In-process / Final / Mix | | ☐ |
| **QC Sampling** | 100% check atau sampling? | | ☐ |
| **QC Parameter** | Apa saja yang di-check? (Visual, Measurement, Testing) | | ☐ |
| **QC Standard** | Apakah ada QC standard terdokumentasi? | ☐ Yes ☐ No | ☐ |
| **QC Result Recording** | Manual form / Digital / Mix | | ☐ |
| **Reject Handling** | Rework / Scrap / Return to supplier | | ☐ |
| **Rework Process** | Apakah rework track di system? | ☐ Yes ☐ No | ☐ |
| **QC Approval** | Siapa yang approve QC release? | | ☐ |
| **Certificate of Analysis** | Apakah perlu COA untuk customer? | ☐ Yes ☐ No | ☐ |

### 3.4.6 Production Costing

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Costing Method** | Standard cost / Actual cost / Average cost | | ☐ |
| **Cost Component** | Material / Labor / Overhead / All | | ☐ |
| **Overhead Allocation** | By machine hour / Labor hour / Unit produced | | ☐ |
| **Variance Analysis** | Perlu material variance / Labor variance / Overhead variance? | ☐ Yes ☐ No | ☐ |
| **Cost Update Frequency** | Monthly / Quarterly / Yearly | | ☐ |

### 3.4.7 Production KPIs

| KPI | Current | Target | Frequency |
|-----|---------|--------|-----------|
| **Overall Equipment Effectiveness (OEE)** | __% | ≥ 85% | Daily |
| **Production Yield** | __% | ≥ __% | Daily |
| **Scrap Rate** | __% | ≤ 2% | Daily |
| **On-Time Production** | __% | ≥ 98% | Daily |
| **Capacity Utilization** | __% | 80-90% | Weekly |
| **Setup Time** | __ jam/run | ≤ __ jam | Weekly |
| **First Pass Yield** | __% | ≥ 98% | Daily |
| **Production Cost per Unit** | Rp ____ | Rp ____ | Monthly |
| **Labor Productivity** | __ unit/man-hour | __ unit/man-hour | Weekly |
| **Machine Downtime** | __% | ≤ 5% | Daily |

---

## 3.5 PROCESS E — Finance & Accounting ⚡

### 3.5.1 Chart of Accounts (COA) Structure

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Current COA** | Berapa digit COA? Structure? | __ digit | ☐ |
| **COA Sample** | Attach current COA list | Attachment | ☐ |
| **COA Modification Need** | Perlu revisi COA untuk ERP? | ☐ Yes ☐ No | ☐ |
| **Multi-Currency** | Apakah perlu multi-currency? | ☐ Yes ☐ No | ☐ |
| **Cost Center** | Apakah pakai cost center? | ☐ Yes ☐ No | ☐ |
| **Profit Center** | Apakah pakai profit center? | ☐ Yes ☐ No | ☐ |
| **Project Accounting** | Apakah perlu project-based accounting? | ☐ Yes ☐ No | ☐ |

### 3.5.2 General Ledger & Journal Entry

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Auto Journal** | Apakah perlu auto journal dari transaksi? | ☐ Yes ☐ No | ☐ |
| **Journal Approval** | Berapa level approval journal entry? | __ level | ☐ |
| **Recurring Journal** | Apakah ada recurring journal? (Sewa, Gaji, dll) | ☐ Yes ☐ No | ☐ |
| **Accrual vs Cash** | Metode akuntansi: Accrual / Cash basis | | ☐ |
| **Fiscal Year** | Fiscal year = Calendar year atau beda? | | ☐ |
| **Period Closing** | Berapa hari untuk monthly closing? | __ hari | ☐ |
| **Closing Approval** | Siapa yang approve closing period? | | ☐ |
| **Reopen Period** | Allow reopen closed period? Approval? | | ☐ |

### 3.5.3 Accounts Payable (AP) Management

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **AP Process** | Sudah terintegrasi dengan purchasing? | ☐ Yes ☐ No | ☐ |
| **Invoice Matching** | 2-way / 3-way matching | | ☐ |
| **Payment Batch** | Apakah payment dilakukan batch? Frequency? | | ☐ |
| **Payment Approval** | Detail approval matrix | See section 3.1 | ☐ |
| **Vendor Ageing** | Perlu ageing report? Frequency? | | ☐ |
| **AP Reconciliation** | Berapa sering rekon AP dengan vendor? | | ☐ |

### 3.5.4 Accounts Receivable (AR) Management

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **AR Process** | Sudah terintegrasi dengan sales? | ☐ Yes ☐ No | ☐ |
| **Credit Management** | Detail credit limit & checking | See section 3.3 | ☐ |
| **Payment Allocation** | Otomatis atau manual matching? | | ☐ |
| **Customer Ageing** | Perlu ageing report? Frequency? | | ☐ |
| **AR Reconciliation** | Berapa sering rekon AR dengan customer? | | ☐ |
| **Bad Debt Write-off** | Process write-off piutang tak tertagih | | ☐ |

### 3.5.5 Bank & Cash Management

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Number of Bank Accounts** | Berapa rekening bank aktif? | __ rekening | ☐ |
| **Bank List** | List bank dan jenis rekening | | ☐ |
| **Bank Reconciliation** | Daily / Weekly / Monthly | | ☐ |
| **Bank Statement Import** | Auto import atau manual entry? | | ☐ |
| **Petty Cash** | Apakah ada petty cash? Berapa lokasi? | __ lokasi | ☐ |
| **Cash Advance** | Apakah ada employee cash advance? | ☐ Yes ☐ No | ☐ |

### 3.5.6 Fixed Assets Management

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Total Fixed Assets** | Jumlah & value fixed assets | Rp _______ | ☐ |
| **Asset Category** | Land / Building / Machine / Vehicle / IT / Furniture | | ☐ |
| **Depreciation Method** | Straight line / Declining balance / Unit of production | | ☐ |
| **Asset Tagging** | Apakah asset di-tag/label? | ☐ Yes ☐ No | ☐ |
| **Asset Location Tracking** | Track asset location per department/branch? | ☐ Yes ☐ No | ☐ |
| **Asset Maintenance** | Apakah perlu maintenance schedule tracking? | ☐ Yes ☐ No | ☐ |
| **Asset Disposal** | Process disposal asset | | ☐ |

### 3.5.7 Financial Reporting Requirements

**Mandatory Reports:**

| Report | Frequency | Recipient | Format | Auto/Manual |
|--------|-----------|-----------|--------|-------------|
| Balance Sheet | Monthly | Management, Tax | PDF/Excel | Auto |
| Income Statement (P&L) | Monthly | Management, Tax | PDF/Excel | Auto |
| Cash Flow Statement | Monthly | Management | PDF/Excel | Auto |
| Trial Balance | Monthly | Finance team | Excel | Auto |
| AR Ageing Report | Weekly | Management, Collection | Excel | Auto |
| AP Ageing Report | Weekly | Management, Finance | Excel | Auto |
| Stock Valuation Report | Monthly | Management | Excel | Auto |
| Budget vs Actual | Monthly | Management | Excel/Dashboard | Auto |

**Custom Reports Needed:**

| Report Name | Purpose | Frequency | Format | Priority |
|-------------|---------|-----------|--------|----------|
| | | | | |

### 3.5.8 Tax & Compliance

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Tax Registration** | NPWP, PKP status | | ☐ |
| **PPN (VAT)** | Apakah PKP? Rate berapa? | 11% / Non-PKP | ☐ |
| **PPh Type** | PPh 21, 22, 23, 25, 29 yang applicable | | ☐ |
| **E-Faktur** | Sudah pakai e-Faktur? | ☐ Yes ☐ No | ☐ |
| **E-Bupot** | Sudah pakai e-Bupot? | ☐ Yes ☐ No | ☐ |
| **Tax Reporting** | Monthly SPT, Annual SPT | | ☐ |
| **Withholding Tax** | Auto calculate WHT? | ☐ Yes ☐ No | ☐ |
| **Tax Audit History** | Pernah audit pajak? Issue? | | ☐ |

### 3.5.9 Budgeting & Forecasting

| Assessment Item | Detail | Answer | Status |
|-----------------|--------|--------|--------|
| **Budget Process** | Apakah ada annual budgeting? | ☐ Yes ☐ No | ☐ |
| **Budget Level** | Department / Cost center / Project level | | ☐ |
| **Budget Approval** | Who approves budget? | | ☐ |
| **Budget Control** | Hard limit / Warning only | | ☐ |
| **Budget vs Actual** | Perlu monitoring? Frequency? | | ☐ |
| **Forecast** | Apakah perlu rolling forecast? | ☐ Yes ☐ No | ☐ |
| **Forecast Horizon** | Berapa bulan forecast? | __ bulan | ☐ |

### 3.5.10 Finance KPIs

| KPI | Current | Target | Frequency |
|-----|---------|--------|-----------|
| **Gross Profit Margin** | __% | ≥ __% | Monthly |
| **Net Profit Margin** | __% | ≥ __% | Monthly |
| **Current Ratio** | __ | ≥ 1.5 | Monthly |
| **Days Sales Outstanding (DSO)** | __ days | ≤ __ days | Monthly |
| **Days Payable Outstanding (DPO)** | __ days | __ days | Monthly |
| **Cash Conversion Cycle** | __ days | ≤ __ days | Monthly |
| **Debt to Equity Ratio** | __ | ≤ __ | Quarterly |
| **Return on Assets (ROA)** | __% | ≥ __% | Quarterly |
| **Operating Expense Ratio** | __% | ≤ __% | Monthly |
| **Budget Variance** | __% | ≤ 5% | Monthly |

---

## 3.6 PROCESS F — HR & Payroll (Optional/Future)

### 3.6.1 HR Module Requirements

| Requirement | Priority | Answer | Status |
|-------------|----------|--------|--------|
| **Employee Master Data** | High / Medium / Low | | ☐ |
| **Organization Structure** | High / Medium / Low | | ☐ |
| **Attendance Management** | High / Medium / Low | | ☐ |
| **Leave Management** | High / Medium / Low | | ☐ |
| **Payroll Processing** | High / Medium / Low | | ☐ |
| **Employee Self-Service Portal** | High / Medium / Low | | ☐ |
| **Performance Management** | High / Medium / Low | | ☐ |
| **Training Management** | High / Medium / Low | | ☐ |

> **Note:** HR module biasanya Phase 2 setelah core ERP stabil. Jika tidak urgent, bisa di-defer.

---

# DOMAIN 4 — RFID Technology Assessment & POC Planning ⚡⚡⚡

> **SUPER CRITICAL untuk PT. Kain Nusantara**

## 4.1 RFID Technology Fundamentals & Selection

### 4.1.1 RFID Tag Type Selection

| Tag Type | Frequency | Read Range | Use Case | Cost per Tag | Recommended for PT. KN? |
|----------|-----------|------------|----------|--------------|-------------------------|
| **Passive HF (13.56 MHz)** | 13.56 MHz | 0-30 cm | Item-level, access control | Rp 3,000-10,000 | ☐ No - Range terlalu pendek |
| **Passive UHF (860-960 MHz)** | 860-960 MHz | 1-12 meter | Inventory, asset tracking | Rp 1,500-5,000 | ☑ **YES - RECOMMENDED** |
| **Active RFID (2.4 GHz)** | 2.4 GHz | Up to 100m | Vehicle, container tracking | Rp 50,000-200,000 | ☐ No - Overkill & too expensive |

**Recommendation untuk PT. Kain Nusantara:**
✅ **Passive UHF RFID (Chainway UHF atau equivalent)**
- Optimal read range (3-8 meter untuk textile)
- Cost-effective (Rp 2,000-3,000 per tag volume pricing)
- Mature technology dengan banyak vendor support
- Suitable untuk roll tracking dan mass scanning

### 4.1.2 RFID Tag Physical Specification

**Critical untuk Textile Application:**

| Specification | Requirement | Answer | Status |
|---------------|-------------|--------|--------|
| **Tag Form Factor** | Inlay / Label / Hard tag / Woven tag | | ☐ |
| **Tag Size** | Preferred dimension (e.g., 50x20mm, 75x25mm) | __ x __ mm | ☐ |
| **Attachment Method** | Adhesive / Sew-on / Hang tag / Pin | | ☐ |
| **Attachment Location** | Di roll edge / Center / Packaging / Wrap | | ☐ |
| **Read Distance Required** | Minimum & maximum read distance | Min: __ m, Max: __ m | ☐ |
| **Environmental Factors** | Moisture / Heat / Chemical / Pressure | | ☐ |
| **Tag Durability** | Must survive berapa kali wash/process? | __ kali | ☐ |
| **Memory Size** | 96-bit EPC / 128-bit / 512-bit / Custom | | ☐ |
| **Write Capability** | Read-only / Write-once / Rewritable | | ☐ |
| **Metal Interference** | Apakah ada metal di sekitar? (Rak besi, forklift) | ☐ Yes ☐ No | ☐ |
| **Liquid Interference** | Apakah kain bisa basah/lembab? | ☐ Yes ☐ No | ☐ |

**Physical Challenge untuk Kain:**
- ⚠️ Textile material dapat menyerap RF signal (signal attenuation)
- ⚠️ Densely stacked rolls dapat cause signal interference
- ⚠️ Moisture content in fabric affects read rate
- ✅ **Solution:** Metal-mount tags atau special textile-optimized tags

### 4.1.3 RFID Reader Hardware Requirements

**Handheld Reader:**

| Specification | Requirement | Recommended Model | Qty Needed | Status |
|---------------|-------------|-------------------|------------|--------|
| **Form Factor** | Industrial handheld / Smartphone-based / Tablet | Chainway C6 UHF / Zebra RFD40 | __ units | ☐ |
| **Read Range** | 0-8 meter typical | | | ☐ |
| **Read Rate** | ≥ 200 tags/second | | | ☐ |
| **Battery Life** | Full shift (8-12 hours) | | | ☐ |
| **Operating System** | Android / Windows CE / iOS | Android preferred | | ☐ |
| **Connectivity** | WiFi / 4G / Bluetooth | WiFi + 4G | | ☐ |
| **Durability** | IP rating (IP65 minimum for warehouse) | IP65/IP67 | | ☐ |
| **Drop Spec** | 1.5-2 meter drop | | | ☐ |
| **Display** | Screen size & brightness | ≥ 5 inch, sunlight readable | | ☐ |

**Fixed/Portal Reader (Gate):**

| Specification | Requirement | Recommended Model | Qty Needed | Status |
|---------------|-------------|-------------------|------------|--------|
| **Type** | Fixed reader + antenna array | Impinj R700 / Zebra FX9600 | __ sets | ☐ |
| **Portal Width** | Door/gate width to cover | __ meter | | ☐ |
| **Portal Height** | Overhead or side-mounted | __ meter | | ☐ |
| **Read Zone** | 3D coverage area | __ x __ x __ meter | | ☐ |
| **Power Output** | Adjustable 0-33 dBm | | | ☐ |
| **Number of Antenna Ports** | 4-port / 8-port | 4-port minimum | | ☐ |
| **Auto-Detection** | Motion sensor trigger | ☐ Yes ☐ No | | ☐ |
| **Direction Detection** | In/Out detection | ☐ Required ☐ Optional | | ☐ |
| **Integration** | TCP/IP, REST API | | | ☐ |

**Antenna Specification:**

| Specification | Requirement | Type | Qty Needed |
|---------------|-------------|------|------------|
| **Polarization** | Circular (recommended) / Linear | Circular | __ pcs |
| **Gain** | 6-9 dBi | 8 dBi typical | |
| **Beam Width** | 60-70 degrees | | |
| **Mounting** | Wall / Ceiling / Pole mount | | |

### 4.1.4 RFID Tag Encoding & Data Structure ⚡⚡

**Critical Decision: EPC Data Structure**

Contoh format EPC untuk roll kain:

```
Format: 96-bit EPC Gen2
Structure: [Header][Company Prefix][Product Code][Serial Number]

Example:
Batik Mega Mendung, Grade A+, Roll #001234, Batch 2026-05
↓
EPC: 30 14159265358 BTK001 001234

Breakdown:
- 30: EPC Header (fixed)
- 14159265358: Company prefix (GS1 allocated)
- BTK001: Product code (Batik, SKU 001)
- 001234: Unique serial number (roll level)
```

**Data Encoding Requirements:**

| Data Element | Encode in EPC? | Store in Backend? | Example | Status |
|--------------|----------------|-------------------|---------|--------|
| **Company Code** | ☑ Yes | ☑ Yes | KAINUS | ☐ |
| **Location Code** | ☐ No | ☑ Yes | WH-JKT | ☐ |
| **Product Category** | ☑ Yes | ☑ Yes | BTK (Batik) | ☐ |
| **SKU** | ☑ Yes | ☑ Yes | BTK-MEGA-001 | ☐ |
| **Color Code** | ☐ No | ☑ Yes | BLUE-NAVY | ☐ |
| **Grade** | ☐ No | ☑ Yes | A+ | ☐ |
| **Batch Number** | ☑ Yes | ☑ Yes | 2026-05-BTK-001 | ☐ |
| **Lot Number** | ☐ No | ☑ Yes | LOT-001 | ☐ |
| **Roll Number** | ☑ Yes (Serial) | ☑ Yes | ROLL-001234 | ☐ |
| **Length (Meter)** | ☐ No | ☑ Yes | 45.50 | ☐ |
| **Weight (Kg)** | ☐ No | ☑ Yes | 12.35 | ☐ |
| **Production Date** | ☐ No | ☑ Yes | 2026-05-15 | ☐ |
| **Expiry Date** | ☐ No | ☑ Yes | 2028-05-15 | ☐ |
| **Supplier Code** | ☐ No | ☑ Yes | SUP-001 | ☐ |
| **Price** | ☐ Never | ☑ Yes | Rp 250,000 | ☐ |

**Why not encode everything in EPC?**
- EPC has limited memory (96-bit standard = 12 bytes only)
- Detailed data (price, dimensions, dates) stored in backend database
- EPC is just a **unique key** to lookup full data in system
- More flexible - can update backend data without rewriting tag

### 4.1.5 RFID Proof of Concept (POC) Planning ⚡⚡

> **MANDATORY: POC SEBELUM FULL ROLLOUT**

**POC Objectives:**

| Objective | Success Criteria | Measurement Method | Status |
|-----------|------------------|-------------------|--------|
| **Read Rate Accuracy** | ≥ 99.5% single tag read | 1000 test reads | ☐ |
| **Bulk Read Accuracy** | ≥ 98% for 50 rolls stacked | Actual warehouse test | ☐ |
| **Read Speed** | ≤ 3 seconds for 50 tags | Timed test | ☐ |
| **Read Range** | 3-8 meter effective range | Distance test | ☐ |
| **Interference Test** | No false read with metal racks | In-situ test | ☐ |
| **Tag Durability** | Survive 6 months warehouse | Longevity test | ☐ |
| **Integration Test** | Real-time data to ERP < 2 sec | System test | ☐ |
| **User Acceptance** | Warehouse staff can operate | Training & feedback | ☐ |

**POC Scope:**

| POC Element | Quantity | Duration | Cost Estimate | Status |
|-------------|----------|----------|---------------|--------|
| **RFID Tags (sample)** | 1,000 pcs | — | Rp 3,000,000 | ☐ |
| **Handheld Reader** | 2 units | Rent/Buy | Rp 30,000,000 | ☐ |
| **Fixed Reader + Antenna** | 1 set (4 antenna) | Rent/Buy | Rp 45,000,000 | ☐ |
| **Tag Printer/Encoder** | 1 unit | Rent/Buy | Rp 25,000,000 | ☐ |
| **Integration Development** | Custom API | 4 weeks | Rp 40,000,000 | ☐ |
| **POC Location** | 1 warehouse zone | 8 weeks | — | ☐ |
| **POC Team** | 1 engineer + 2 warehouse staff | 8 weeks | Labor cost | ☐ |
| **Total POC Budget** | | 2 months | ~Rp 150-200 juta | ☐ |

**POC Test Scenarios:**

| # | Test Scenario | Pass Criteria | Result | Notes |
|---|---------------|---------------|--------|-------|
| 1 | **Single Roll Read** | 100 consecutive successful reads | ☐ Pass ☐ Fail | |
| 2 | **Stack Read (10 rolls)** | ≥ 98% accuracy in 10 test | ☐ Pass ☐ Fail | |
| 3 | **Stack Read (50 rolls)** | ≥ 95% accuracy in 10 test | ☐ Pass ☐ Fail | |
| 4 | **Moving Read (Forklift)** | Read while in motion ≤ 5 km/h | ☐ Pass ☐ Fail | |
| 5 | **Distance Test** | Reliable read up to 8 meter | ☐ Pass ☐ Fail | |
| 6 | **Metal Interference** | No false read near metal racks | ☐ Pass ☐ Fail | |
| 7 | **Moisture Test** | Read accuracy with 10% moisture | ☐ Pass ☐ Fail | |
| 8 | **Dense Stack** | Read accuracy with tight stack | ☐ Pass ☐ Fail | |
| 9 | **Gate Walk-through** | Auto-detect direction (in/out) | ☐ Pass ☐ Fail | |
| 10 | **Cycle Count Simulation** | Count 100 rolls in < 5 minutes | ☐ Pass ☐ Fail | |
| 11 | **ERP Integration** | Real-time stock update < 2 sec | ☐ Pass ☐ Fail | |
| 12 | **False Positive Test** | No ghost reads in 1 hour | ☐ Pass ☐ Fail | |

**POC Go/No-Go Decision Criteria:**

```
✅ PROCEED TO FULL ROLLOUT if:
   - Critical scenarios (1, 2, 3, 10, 11) = 100% Pass
   - Overall success rate ≥ 95%
   - User feedback = Positive
   - ROI calculation = Payback < 24 months

⚠️ ITERATE POC if:
   - Success rate 85-94%
   - Need tag/antenna/setup optimization
   - Minor integration issues

❌ ABORT RFID if:
   - Success rate < 85%
   - Fundamental technical limitation discovered
   - Cost-benefit not justified
```

### 4.1.6 RFID Implementation Scenarios

**Scenario A: Full RFID (Recommended)**

```
[Goods Receipt] → [RFID Tag Apply & Encode] → [Put-away dengan RFID] →
[Stock Opname via RFID Handheld] → [Picking via RFID] → [Gate Auto-Scan on Ship]
```

**Coverage:** 100% roll tracking
**Investment:** High (Rp 800 juta - 1.5 M)
**Benefit:** Maximum accuracy & automation
**Payback:** 18-24 months

**Scenario B: Hybrid (RFID + Barcode)**

```
[GR] → [RFID Tag for High-Value Items, Barcode for Low-Value] →
[Stock Opname: RFID handheld + Barcode scanner] →
[Picking: RFID + Manual verification]
```

**Coverage:** 50-70% roll tracking (Grade A/A+)
**Investment:** Medium (Rp 400-600 juta)
**Benefit:** Balanced cost & benefit
**Payback:** 12-18 months

**Scenario C: Phased Rollout (Recommended Approach)**

```
Phase 1 (POC): 1 warehouse zone, 1000 rolls
↓
Phase 2 (Pilot): 1 complete warehouse
↓
Phase 3 (Expansion): All warehouses
```

**Investment:** Gradual (Rp 200jt → 600jt → 1.2M)
**Benefit:** Risk mitigation, learning curve
**Payback:** Variable, starts showing from Phase 2

### 4.1.7 RFID Software Architecture ⚡

**RFID Middleware Requirements:**

| Component | Purpose | Technology Option | Status |
|-----------|---------|-------------------|--------|
| **Edge Agent** | RFID reader interface | Python/Java service | ☐ |
| **Tag Filter** | Remove duplicate reads | Built-in logic | ☐ |
| **Business Logic Layer** | Event processing | Node.js/Python | ☐ |
| **Message Queue** | Async processing | Redis Pub/Sub / RabbitMQ | ☐ |
| **ERP Integration API** | REST API to ERP | FastAPI / Express | ☐ |
| **Event Database** | RFID event log | MongoDB / PostgreSQL | ☐ |
| **Dashboard** | Real-time monitoring | React + WebSocket | ☐ |

**System Architecture Diagram:**

```
┌─────────────────┐
│ RFID Reader     │ ──┐
│ (Handheld/Gate) │   │
└─────────────────┘   │
                      ├──→ ┌──────────────┐      ┌──────────────┐
┌─────────────────┐   │    │ Edge Agent   │ ───→ │ RFID         │
│ RFID Reader     │ ──┤    │ (Per Site)   │      │ Middleware   │
│ (Handheld/Gate) │   │    │              │      │ (Central)    │
└─────────────────┘   │    └──────────────┘      └──────┬───────┘
                      │                                  │
┌─────────────────┐   │                                  │
│ RFID Reader     │ ──┘                                  ↓
└─────────────────┘                         ┌────────────────────┐
                                            │ ERP Backend        │
                                            │ (FastAPI + MongoDB)│
                                            │                    │
                                            │ • Stock Update     │
                                            │ • Transaction Log  │
                                            │ • Business Rules   │
                                            └────────────────────┘
```

### 4.1.8 RFID Operational Procedures (SOP)

**SOP 1: Tag Encoding & Application**

| Step | Actor | Action | Tool | Quality Check | Status |
|------|-------|--------|------|---------------|--------|
| 1 | Receiving staff | Receive goods + GR document | GR form | Qty verification | ☐ |
| 2 | QC | Physical QC inspection | Visual | Pass/Fail stamp | ☐ |
| 3 | Tag operator | Print & encode RFID tag | Tag printer | Verify encoding | ☐ |
| 4 | Tag operator | Apply tag to roll edge | Manual | Secure attachment | ☐ |
| 5 | Tag operator | Test read tag | Handheld | Confirm read | ☐ |
| 6 | System | Auto update ERP (status: Available) | API | Stock increment | ☐ |

**SOP 2: Mass Stock Opname via RFID**

| Step | Actor | Action | Tool | Expected Result | Status |
|------|-------|--------|------|-----------------|--------|
| 1 | Warehouse supervisor | Create opname session in ERP | Web UI | Session created | ☐ |
| 2 | Opname team | Scan warehouse zone with handheld | RFID handheld | Collect tag data | ☐ |
| 3 | System | Compare scan result vs system stock | Backend | Generate variance | ☐ |
| 4 | Warehouse supervisor | Review variance report | Web UI | Identify discrepancy | ☐ |
| 5 | Warehouse supervisor | Approve/adjust variance | Web UI | Adjustment posted | ☐ |
| 6 | System | Update actual stock | Backend | Stock corrected | ☐ |

**SOP 3: RFID-based Outbound Picking**

| Step | Actor | Action | Tool | Verification | Status |
|------|-------|--------|------|--------------|--------|
| 1 | System | Generate pick list from SO | ERP | Pick list created | ☐ |
| 2 | Picker | Navigate to bin location | Handheld (GPS) | Location confirmed | ☐ |
| 3 | Picker | Scan RFID tag to pick | RFID handheld | Match with pick list | ☐ |
| 4 | System | Validate correct item | Backend | ✓ / ✗ Alert | ☐ |
| 5 | Picker | Move to staging area | Trolley/Forklift | Complete pick list | ☐ |
| 6 | Packer | Final verification | RFID handheld | 100% accuracy check | ☐ |
| 7 | System | Update stock (deduct) | Backend | Stock updated | ☐ |

**SOP 4: RFID Gate Auto-Detection (Outbound)**

| Step | Actor/System | Action | Trigger | Result | Status |
|------|--------------|--------|---------|--------|--------|
| 1 | Packer | Push trolley through gate | Motion sensor | Gate activated | ☐ |
| 2 | RFID Gate | Auto-scan all tags (bulk read) | RFID reader | Tag list captured | ☐ |
| 3 | System | Match tags with pending DO | Backend | ✓ Match / ✗ Mismatch | ☐ |
| 4 | System (if match) | Auto-update stock & DO status | Backend | Stock deducted | ☐ |
| 5 | System (if mismatch) | Alert + block gate | Alert | Manual check required | ☐ |

### 4.1.9 RFID KPIs & Performance Monitoring

| KPI | Target | Measurement | Frequency | Owner |
|-----|--------|-------------|-----------|-------|
| **Tag Read Rate (Single)** | ≥ 99.8% | Total successful / Total attempts | Daily | IT |
| **Tag Read Rate (Bulk)** | ≥ 98% | Bulk scan accuracy | Daily | IT |
| **Opname Speed** | ≤ 5 min per 100 rolls | Timed measurement | Per opname | Warehouse |
| **Opname Accuracy** | ≥ 99.5% | Variance % from actual | Per opname | Warehouse |
| **Tag Failure Rate** | ≤ 0.5% | Dead tags / Total tags | Weekly | IT |
| **False Positive Rate** | ≤ 0.1% | Ghost reads / Total reads | Daily | IT |
| **System Uptime** | ≥ 99% | Uptime hours / Total hours | Weekly | IT |
| **Integration Latency** | ≤ 2 seconds | ERP update time | Real-time | IT |
| **User Satisfaction** | ≥ 4.5/5 | Survey score | Monthly | Management |
| **ROI Achievement** | Meet projection | Cost saving vs investment | Quarterly | Finance |

### 4.1.10 RFID Risk Register & Mitigation

| Risk | Probability | Impact | Mitigation Strategy | Owner | Status |
|------|-------------|--------|---------------------|-------|--------|
| **Low read rate due to fabric interference** | Medium | High | POC with different tag types & mounting positions | IT | ☐ |
| **Tag damage during handling** | Medium | Medium | Use durable tags + proper attachment method | Warehouse | ☐ |
| **Metal rack interference** | Low | High | Use metal-mount tags / adjust antenna position | IT | ☐ |
| **System integration failure** | Low | Critical | Comprehensive API testing + fallback to manual | IT | ☐ |
| **User resistance to new technology** | High | High | Early involvement + comprehensive training | HR | ☐ |
| **Budget overrun** | Medium | High | Phased approach + strict cost control | Finance | ☐ |
| **RFID reader malfunction** | Low | Medium | Spare units + maintenance contract | IT | ☐ |
| **Network instability** | Medium | High | Local edge computing + offline mode | IT | ☐ |
| **Tag cost higher than expected** | Low | Medium | Volume negotiation + multiple vendor quotes | Procurement | ☐ |
| **Slow adoption & productivity drop** | High | High | Adequate training + support team on-site | HR + IT | ☐ |

---

# DOMAIN 5 — System Integration Architecture ⚡

> **Assessment Goal:** Map semua integration points dan design integration strategy untuk ensure data flow seamlessly across all systems.

## 5.1 Integration Landscape Mapping

### 5.1.1 Current Integration Points

**List All Systems yang Perlu Integrate dengan ERP:**

| System | Type | Direction | Data Exchange | Frequency | Priority | Status |
|--------|------|-----------|---------------|-----------|----------|--------|
| Accounting Software (e.g., Accurate) | 3rd Party | Bi-directional | Journal, AP, AR | Real-time / Daily | ☑ Critical | ☐ |
| E-Commerce Platform (Tokopedia, Shopee, etc.) | Cloud Service | Inbound | Sales orders | Real-time | ☑ High | ☐ |
| Banking (Internet banking) | Manual/Auto | Inbound | Payment confirmation | Daily | ☑ High | ☐ |
| Tax System (E-Faktur, E-Bupot) | Government | Outbound | Tax invoice data | Daily | ☑ High | ☐ |
| Courier (JNE, JNT, SiCepat, etc.) | 3rd Party API | Outbound | Shipping info, Tracking | Real-time | ☐ High | ☐ |
| Payment Gateway (if any) | Cloud Service | Inbound | Payment notification | Real-time | ☐ Medium | ☐ |
| CRM System (if any) | 3rd Party | Bi-directional | Customer data | Real-time | ☐ Low | ☐ |
| Production Machine (IoT) | On-premise | Inbound | Production data | Real-time | ☐ Medium | ☐ |
| Weighbridge System | On-premise | Inbound | Weight data | Real-time | ☐ Low | ☐ |
| Access Control System | On-premise | Outbound | Employee data | Daily | ☐ Low | ☐ |

### 5.1.2 Integration Method & Technology

| Integration Type | When to Use | Technology Option | Pros | Cons | Recommended? |
|------------------|-------------|-------------------|------|------|--------------|
| **REST API** | Real-time, web-based | HTTP JSON/XML | Standard, easy | Synchronous, heavy | ☑ Yes (Primary) |
| **Webhook** | Event-driven, async | HTTP POST callback | Real-time push | Need public endpoint | ☑ Yes (For e-commerce) |
| **File Export/Import** | Batch processing | CSV / Excel / XML | Simple, no API needed | Manual, error-prone | ☐ Last resort only |
| **Database Direct Connection** | Same network | JDBC/ODBC | Fast, no API | Tight coupling, risky | ☐ No |
| **Message Queue** | Async, high volume | RabbitMQ / Kafka | Decoupled, reliable | Complex setup | ☑ Yes (For RFID) |
| **SFTP** | Secure file transfer | SSH file transfer | Secure | Manual process | ☐ For tax/banking only |

### 5.1.3 Integration Architecture Design

**Recommended Architecture: API Gateway Pattern**

```
┌─────────────────────────────────────────────────────────────────┐
│                    External Systems Layer                        │
├─────────────┬─────────────┬─────────────┬──────────────────────┤
│ E-Commerce  │  Banking    │  Courier    │  Tax Authority       │
│ (Tokopedia, │  (BCA, BNI) │  (JNE, JNT) │  (E-Faktur)          │
│  Shopee)    │             │             │                       │
└──────┬──────┴──────┬──────┴──────┬──────┴──────────┬───────────┘
       │             │             │                  │
       │ Webhook     │ File/API    │ API              │ SFTP
       │             │             │                  │
┌──────▼─────────────▼─────────────▼──────────────────▼───────────┐
│                    API Gateway (Kong / NGINX)                    │
│  • Authentication / Authorization                                │
│  • Rate Limiting & Throttling                                    │
│  • Request/Response Transformation                               │
│  • Logging & Monitoring                                          │
└──────────────────────────┬───────────────────────────────────────┘
                           │ Internal Secure Network
┌──────────────────────────▼───────────────────────────────────────┐
│                    Integration Layer (Middleware)                │
│  • Message Queue (Redis / RabbitMQ)                              │
│  • Data Transformation & Mapping                                 │
│  • Error Handling & Retry Logic                                  │
│  • Event Processing & Routing                                    │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                  ERP Backend (FastAPI + MongoDB)                 │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────────┐   │
│  │ Sales    │ Purchase │ Warehouse│ Finance  │ Production   │   │
│  │ Module   │ Module   │ Module   │ Module   │ Module       │   │
│  └──────────┴──────────┴──────────┴──────────┴──────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            MongoDB (Unified Database)                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 5.1.4 E-Commerce Integration Detail

**Priority Integration: Tokopedia, Shopee, Bukalapak, TikTok Shop**

| Data Flow | Direction | Data Fields | Frequency | Handling | Status |
|-----------|-----------|-------------|-----------|----------|--------|
| **Order Import** | E-com → ERP | Order ID, Customer, Items, Qty, Price, Address | Real-time (Webhook) | Auto-create SO | ☐ |
| **Stock Update** | ERP → E-com | SKU, Available stock per warehouse | Hourly / Daily | API push | ☐ |
| **Order Status** | ERP → E-com | Order ID, Status (Processing, Shipped, Delivered) | Real-time | API push | ☐ |
| **Tracking Number** | ERP → E-com | Order ID, AWB number, Courier | After shipment | API push | ☐ |
| **Product Sync** | ERP → E-com | SKU, Name, Description, Price, Images | Daily | Bulk API | ☐ |

**Integration Challenge:**
- ⚠️ Setiap e-commerce punya API format berbeda
- ⚠️ Stock update delay bisa cause oversell
- ✅ **Solution:** Build unified adapter layer + real-time stock sync

### 5.1.5 Accounting Software Integration

**Jika Keep Existing Accounting Software (e.g., Accurate, Zahir):**

| Data Flow | Direction | Data Fields | Frequency | Method | Status |
|-----------|-----------|-------------|-----------|--------|--------|
| **Journal Entry** | ERP → Accounting | Date, Account code, Debit, Credit, Description | Daily batch | File export (CSV) | ☐ |
| **Customer Master** | ERP → Accounting | Customer code, Name, Address, Tax ID | On change | File export | ☐ |
| **Supplier Master** | ERP → Accounting | Supplier code, Name, Address, Tax ID | On change | File export | ☐ |
| **Invoice** | ERP → Accounting | Invoice number, Amount, Tax, Due date | Daily | File export | ☐ |
| **Payment** | ERP → Accounting | Payment ID, Invoice ref, Amount, Date | Daily | File export | ☐ |

**Integration Method:**
- Daily scheduled export from ERP (JSON/CSV)
- SFTP transfer to accounting software import folder
- Validation & error report

**OR: Fully Integrated Finance Module in ERP (Recommended)**
- ✅ No double entry
- ✅ Real-time financial reporting
- ✅ Single source of truth
- ❌ Need migration from existing accounting software

### 5.1.6 Banking Integration

| Bank | Integration Method | Data Exchange | Status |
|------|-------------------|---------------|--------|
| BCA | API (BCA API) / Manual file | Payment confirmation, Account statement | ☐ |
| Mandiri | API / Manual file | Payment confirmation | ☐ |
| BNI | API / Manual file | Payment confirmation | ☐ |
| Bank Lainnya | Manual upload | Bank statement (Excel → parse → matching) | ☐ |

**Auto-Reconciliation Flow:**

```
[Bank API/Statement] → [Parse transaction] → [Match with open invoice] →
[Auto-allocate payment] → [Update AR] → [Notification to customer]
```

### 5.1.7 Tax System Integration (Indonesia-Specific)

| System | Purpose | Integration | Frequency | Status |
|--------|---------|-------------|-----------|--------|
| **E-Faktur (DJP)** | PPN Invoice | Export format DJP | Daily/Weekly | ☐ |
| **E-Bupot (DJP)** | Withholding tax | Export format DJP | Monthly | ☐ |
| **E-SPT** | Tax reporting | Manual / Export | Monthly | ☐ |

**E-Faktur Export Flow:**

```
[ERP generate invoice] → [Extract data to E-Faktur format (CSV)] →
[Import to E-Faktur desktop] → [Upload to DJP] → [Get approval number] →
[Update invoice in ERP with faktur number]
```

### 5.1.8 Integration Testing Strategy

| Test Type | Coverage | Tool | Responsibility | Status |
|-----------|----------|------|----------------|--------|
| **Unit Test** | Individual API endpoint | Pytest / Jest | Developer | ☐ |
| **Integration Test** | End-to-end data flow | Postman / Newman | QA | ☐ |
| **Load Test** | Concurrent requests | JMeter / Locust | DevOps | ☐ |
| **Security Test** | Authentication, Authorization | OWASP ZAP | Security team | ☐ |
| **UAT** | Business scenario | Manual + Automated | Business user | ☐ |

### 5.1.9 Integration Monitoring & Alerting

**Monitoring Requirements:**

| Metric | Threshold | Alert Method | Responsible | Status |
|--------|-----------|--------------|-------------|--------|
| **API Response Time** | > 2 seconds | Email / SMS | IT | ☐ |
| **API Error Rate** | > 1% | Email / SMS | IT | ☐ |
| **Failed Integration** | Any failure | Email / SMS / Slack | IT | ☐ |
| **Queue Backlog** | > 1000 messages | Email | IT | ☐ |
| **Data Sync Delay** | > 5 minutes | Email | IT | ☐ |

**Monitoring Dashboard:**
- Real-time integration status (Green/Yellow/Red)
- API call volume & success rate
- Average response time
- Failed transaction log with retry status

---

# DOMAIN 6 — Data Management & Migration Strategy ⚡⚡

> **Assessment Goal:** Ensure data quality, define data governance, dan plan smooth data migration dari existing system ke new ERP.

## 6.1 Data Quality Assessment (Current State)

### 6.1.1 Master Data Quality Score

**Rate current master data quality (1-5 scale):**

| Data Type | Completeness | Accuracy | Consistency | Duplication | Overall Score | Priority to Fix |
|-----------|--------------|----------|-------------|-------------|---------------|-----------------|
| **Product Master** | __/5 | __/5 | __/5 | __/5 | __/20 | ☐ Critical |
| **Customer Master** | __/5 | __/5 | __/5 | __/5 | __/20 | ☐ High |
| **Supplier Master** | __/5 | __/5 | __/5 | __/5 | __/20 | ☐ High |
| **Price List** | __/5 | __/5 | __/5 | __/5 | __/20 | ☐ High |
| **BOM (if applicable)** | __/5 | __/5 | __/5 | __/5 | __/20 | ☐ Medium |
| **Chart of Accounts** | __/5 | __/5 | __/5 | __/5 | __/20 | ☐ High |

**Scoring Guide:**
- 1 = Very poor (>50% issues)
- 2 = Poor (30-50% issues)
- 3 = Fair (10-30% issues)
- 4 = Good (5-10% issues)
- 5 = Excellent (<5% issues)

### 6.1.2 Data Quality Issues Identification

**Common Data Quality Issues untuk PT. Kain Nusantara:**

| Issue Type | Example | Impact | Frequency | Fix Priority | Status |
|------------|---------|--------|-----------|--------------|--------|
| **Missing mandatory fields** | Product tanpa SKU, Customer tanpa alamat | High | __% | Critical | ☐ |
| **Duplicate records** | Customer sama tapi beda code | High | __% | Critical | ☐ |
| **Inconsistent naming** | "PT ABC" vs "PT. ABC" vs "ABC" | Medium | __% | High | ☐ |
| **Outdated data** | Inactive customers/suppliers masih active | Low | __% | Medium | ☐ |
| **Invalid format** | Phone number inconsistent format | Low | __% | Medium | ☐ |
| **Wrong categorization** | Product salah kategori | Medium | __% | High | ☐ |
| **Missing pricing** | Product tanpa price | Critical | __% | Critical | ☐ |
| **Incorrect UOM** | Satuan tidak konsisten | High | __% | Critical | ☐ |

**Total Estimated Records to Clean:**

| Master Data | Total Records | Est. Records with Issues | Est. Cleanup Effort (hours) | Status |
|-------------|---------------|--------------------------|------------------------------|--------|
| Products | __ records | __ (___%) | __ hours | ☐ |
| Customers | __ records | __ (___%) | __ hours | ☐ |
| Suppliers | __ records | __ (___%) | __ hours | ☐ |
| Other | __ records | __ (___%) | __ hours | ☐ |

## 6.2 Data Cleansing Strategy

### 6.2.1 Data Cleansing Plan

| Phase | Activity | Tool | Owner | Duration | Status |
|-------|----------|------|-------|----------|--------|
| **1. Assessment** | Run data quality audit scripts | Python script | IT | 1 week | ☐ |
| **2. Prioritization** | Identify critical vs nice-to-have fixes | Manual review | Data team | 3 days | ☐ |
| **3. Standardization** | Define data standards & rules | Documentation | Data team | 1 week | ☐ |
| **4. Cleansing** | Fix data issues (manual + automated) | Excel + Script | Data team | 4-6 weeks | ☐ |
| **5. Validation** | Verify cleaned data | Script + UAT | Data team + Users | 1 week | ☐ |
| **6. Sign-off** | Final approval | Manual | Management | 3 days | ☐ |

### 6.2.2 Data Standardization Rules

**Define Standards (akan digunakan di New ERP):**

| Data Element | Standard Format | Example | Validation Rule | Status |
|--------------|-----------------|---------|-----------------|--------|
| **Product SKU** | CATEGORY-MOTIF-NNN | BTK-MEGA-001 | Regex: ^[A-Z]{3}-[A-Z0-9]{4}-\d{3}$ | ☐ |
| **Customer Code** | CUST-NNNN | CUST-0001 | Regex: ^CUST-\d{4}$ | ☐ |
| **Supplier Code** | SUP-NNNN | SUP-0001 | Regex: ^SUP-\d{4}$ | ☐ |
| **Phone Number** | +62-XXX-XXXX-XXXX | +62-812-3456-7890 | E.164 format | ☐ |
| **Email** | lowercase@domain | customer@email.com | Email validation | ☐ |
| **Address** | Complete with city, postal | Jl. XXX, Jakarta, 12345 | Min 20 chars | ☐ |
| **Price** | Decimal(18,2) | 125000.00 | Positive number | ☐ |
| **Date** | YYYY-MM-DD | 2026-05-28 | ISO 8601 | ☐ |

## 6.3 Data Migration Strategy

### 6.3.1 Migration Approach

**Option A: Big Bang Migration**
- ✅ One-time cutover
- ✅ Clean break from old system
- ❌ High risk
- ❌ No room for error
- **Use when:** Small data volume, simple structure

**Option B: Phased Migration (Recommended)**
- ✅ Lower risk
- ✅ Validate each phase
- ✅ Parallel run possible
- ❌ Longer timeline
- **Use when:** Large data volume, complex business

**Recommended for PT. Kain Nusantara: Phased Approach**

```
Phase 1: Master Data (Week 1-2)
  → Product, Customer, Supplier, COA, UOM
  
Phase 2: Opening Balance (Week 3)
  → Stock balance, AR balance, AP balance
  
Phase 3: Historical Transactions (Week 4) [Optional]
  → Last 6-12 months transactions for reporting
  
Phase 4: Active Transactions (Week 5)
  → Open PO, Open SO yang belum selesai
```

### 6.3.2 Migration Sequence & Dependencies

| Sequence | Data Type | Dependency | Migration Method | Validation Criteria | Status |
|----------|-----------|------------|------------------|---------------------|--------|
| 1 | **UOM** | None | Bulk import (CSV) | All UOMs created | ☐ |
| 2 | **Chart of Accounts** | None | Bulk import (CSV) | All accounts created | ☐ |
| 3 | **Warehouse** | None | Bulk import (CSV) | All locations created | ☐ |
| 4 | **Supplier** | None | Bulk import (CSV) | De-duplicated, validated | ☐ |
| 5 | **Product Master** | UOM, Supplier | Bulk import (CSV) | SKU unique, price populated | ☐ |
| 6 | **Customer Master** | None | Bulk import (CSV) | De-duplicated, validated | ☐ |
| 7 | **Price List** | Product, Customer | Bulk import (CSV) | Prices validated | ☐ |
| 8 | **BOM** (if any) | Product | Bulk import (CSV) | All components exist | ☐ |
| 9 | **Stock Opening Balance** | Product, Warehouse | Bulk import + Physical count | Match physical count | ☐ |
| 10 | **AR Opening Balance** | Customer | Import + Reconciliation | Match with customer stmt | ☐ |
| 11 | **AP Opening Balance** | Supplier | Import + Reconciliation | Match with supplier stmt | ☐ |
| 12 | **GL Opening Balance** | COA | Import + Trial balance | Balanced trial balance | ☐ |
| 13 | **Open Purchase Orders** | Supplier, Product | Manual entry / Import | All open PO migrated | ☐ |
| 14 | **Open Sales Orders** | Customer, Product | Manual entry / Import | All open SO migrated | ☐ |

### 6.3.3 Data Extraction Format

**Template Structure untuk Setiap Master Data:**

Example: **Product Master Extract Template**

| Field Name | Data Type | Mandatory | Max Length | Format | Sample Data | Validation Rule |
|------------|-----------|-----------|------------|--------|-------------|-----------------|
| SKU | String | Yes | 20 | Uppercase | BTK-MEGA-001 | Unique |
| Product Name | String | Yes | 100 | Title Case | Batik Mega Mendung | Min 5 chars |
| Category | String | Yes | 50 | Select list | Batik | From predefined list |
| Subcategory | String | No | 50 | Select list | Batik Cap | From predefined list |
| Color | String | Yes | 30 | Uppercase | NAVY BLUE | From color master |
| Grade | String | Yes | 5 | A/A+/B/C | A+ | From grade list |
| Motif | String | No | 50 | Title Case | Mega Mendung | |
| Base UOM | String | Yes | 10 | Uppercase | METER | From UOM master |
| Purchase UOM | String | No | 10 | Uppercase | ROLL | From UOM master |
| Conversion Factor | Decimal | No | (10,2) | Positive | 45.00 | If purchase UOM diff |
| Standard Cost | Decimal | Yes | (18,2) | Positive | 250000.00 | Must > 0 |
| Selling Price | Decimal | Yes | (18,2) | Positive | 320000.00 | Must > cost |
| Supplier Code | String | No | 20 | Uppercase | SUP-0001 | Must exist in supplier master |
| Reorder Point | Integer | No | | Positive | 10 | |
| Min Stock | Integer | No | | Positive | 5 | |
| Max Stock | Integer | No | | Positive | 100 | Must > min |
| Is Active | Boolean | Yes | | TRUE/FALSE | TRUE | |

### 6.3.4 Data Validation & Quality Gates

**Validation Checklist (Must PASS before Go-Live):**

| Validation Check | Pass Criteria | Tool | Owner | Status |
|------------------|---------------|------|-------|--------|
| **No Duplicate SKU** | 0 duplicates | SQL query | Data team | ☐ |
| **All SKU have Price** | 100% have price > 0 | SQL query | Data team | ☐ |
| **All Products have Category** | 100% categorized | SQL query | Data team | ☐ |
| **No Duplicate Customer** | 0 duplicates (by name + phone) | Script | Data team | ☐ |
| **All Customers have Address** | ≥ 95% have complete address | SQL query | Data team | ☐ |
| **Stock Balance = Physical Count** | 100% match (critical items) | Manual verification | Warehouse | ☐ |
| **AR Balance = Customer Statement** | 100% match (top 20 customers) | Reconciliation | Finance | ☐ |
| **AP Balance = Supplier Statement** | 100% match (top 20 suppliers) | Reconciliation | Finance | ☐ |
| **Trial Balance = 0** | Debit = Credit | Accounting report | Finance | ☐ |
| **All Open PO Migrated** | 100% open PO in system | Manual check | Purchasing | ☐ |
| **All Open SO Migrated** | 100% open SO in system | Manual check | Sales | ☐ |

### 6.3.5 Rollback Plan

**If Migration Fails, Rollback Procedure:**

| Step | Action | Tool | Timeline | Responsible | Status |
|------|--------|------|----------|-------------|--------|
| 1 | **Declare rollback** | Management decision | T+0 | CEO / Project Director | ☐ |
| 2 | **Stop new ERP** | Disable access | Immediate | IT | ☐ |
| 3 | **Re-enable old system** | Restore access | 15 minutes | IT | ☐ |
| 4 | **Data reconciliation** | Compare data during trial period | 2-4 hours | Data team | ☐ |
| 5 | **Manual entry** | Key in transactions done in new ERP | 4-8 hours | All users | ☐ |
| 6 | **Root cause analysis** | Identify failure reason | 1-2 days | Project team | ☐ |
| 7 | **Remediation plan** | Fix issues before retry | 1-2 weeks | Project team | ☐ |

## 6.4 Data Governance Framework

### 6.4.1 Data Ownership Matrix

| Data Domain | Data Owner | Data Steward | Update Authority | Approval Required | Status |
|-------------|------------|--------------|------------------|-------------------|--------|
| **Product Master** | Product Manager | Master Data Admin | Product team | Product Manager | ☐ |
| **Customer Master** | Sales Director | Sales Admin | Sales team | Sales Manager | ☐ |
| **Supplier Master** | Purchasing Manager | Purchasing Admin | Purchasing team | Purchasing Manager | ☐ |
| **Price List** | Finance Director | Pricing Admin | Pricing team | Finance Director | ☐ |
| **Chart of Accounts** | Finance Director | Finance Admin | Finance team | Finance Director | ☐ |
| **Inventory Stock** | Warehouse Manager | System (auto) | Warehouse team | Warehouse Supervisor | ☐ |

### 6.4.2 Master Data Change Control Process

**SOP: How to Request Master Data Change**

```
[User] → [Submit change request form] → [Data steward review] →
[Data owner approval] → [System admin execute] → [Audit log recorded]
```

| Change Type | Approval Level | SLA | Audit Trail | Status |
|-------------|----------------|-----|-------------|--------|
| Add new product | Product Manager | 1 day | Yes | ☐ |
| Modify product price | Finance Director | 4 hours | Yes | ☐ |
| Add new customer | Sales Manager | 2 hours | Yes | ☐ |
| Modify customer credit limit | Finance Manager | 1 day | Yes | ☐ |
| Add new supplier | Purchasing Manager | 1 day | Yes | ☐ |
| Modify COA | Finance Director + Auditor | 1 week | Yes | ☐ |

### 6.4.3 Data Retention Policy

| Data Type | Retention Period | Storage Location | Archive Method | Purge Authority | Status |
|-----------|------------------|------------------|----------------|-----------------|--------|
| **Transactional Data** | 7 years | Online DB (2 years) → Archive (5 years) | Compressed backup | Finance Director | ☐ |
| **Financial Reports** | 10 years (legal requirement) | File server | PDF + Original | Finance Director | ☐ |
| **Audit Logs** | 5 years | Online DB (1 year) → Archive (4 years) | Read-only DB | IT Manager | ☐ |
| **Customer Data** | Active + 3 years after last transaction | Online DB | GDPR-compliant deletion | Data Protection Officer | ☐ |
| **Email Communication** | 3 years | Email server | Archive mailbox | IT Manager | ☐ |

---

*(DOCUMENT CONTINUES...)*

**Dokumen ini masih berlanjut untuk Domain 7-15. Total halaman lengkap: ~120-150 halaman.**

**Status Progress: 60% Complete**
- ✅ Domain 1: Company & Strategy
- ✅ Domain 2: Current State & Pain Points
- ✅ Domain 3: Business Process (6 processes)
- ✅ Domain 4: RFID Assessment (Ultra-detailed)
- ✅ Domain 5: Integration Architecture
- ✅ Domain 6: Data Migration (60% done)
- ⏳ Domain 7-15: To be continued...

Apakah Anda ingin saya **lanjutkan ke Domain 7-15**?
Atau ada **domain spesifik** yang ingin saya prioritaskan duluan?
