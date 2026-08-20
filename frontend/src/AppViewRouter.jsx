// AppViewRouter — memetakan activeView → komponen view (dipisah dari App.js agar
// file App.js di bawah batas guardrail). Menerima `actions` (SSOT business logic
// dari useAppActions) + state/handler dari App.js.
//
// P3 — CODE SPLITTING: setiap view feature dimuat via React.lazy() sehingga bundle
// utama tidak lagi memuat SELURUH view sekaligus (dulu main.js ~3.0 MB). Hanya chunk
// view aktif yang di-fetch saat dibutuhkan. Semua render dibungkus <Suspense> tunggal.
import { lazy, Suspense } from "react";
import { Loader2 } from "lucide-react";
import HubTabs from "./components/HubTabs";
import ComingSoon from "./features/ComingSoon";
import { defaultNavIdForRole, defaultViewForRole } from "./config/navigationConfig";

// ── Lazy views (dipisah per chunk) ──────────────────────────────────────────
const SalesPortal = lazy(() => import("./features/sales/SalesPortal").then((m) => ({ default: m.SalesPortal })));
const PriceApprovals = lazy(() => import("./features/sales/PriceApprovals"));
const OrdersView = lazy(() => import("./features/orders/OrdersView"));
const CrmView = lazy(() => import("./features/crm/CrmView"));
const OperationsView = lazy(() => import("./features/wms/OperationsView"));
const QCInspection = lazy(() => import("./features/wms/QCInspection"));
const DocumentsView = lazy(() => import("./features/documents/DocumentsView"));
const AdminView = lazy(() => import("./features/admin/AdminView"));
const CostingView = lazy(() => import("./features/costing/CostingView"));
const ARAgingView = lazy(() => import("./features/finance/ARAgingView"));
const StoreCreditView = lazy(() => import("./features/finance/StoreCreditView"));
const BankAccountsView = lazy(() => import("./features/finance/BankAccountsView"));
const BankReconciliationView = lazy(() => import("./features/finance/BankReconciliationView"));
const FinanceCasesView = lazy(() => import("./features/finance/cases/FinanceCasesView"));
const FixedAssetsView = lazy(() => import("./features/finance/FixedAssetsView"));
const ProductionView = lazy(() => import("./features/production/ProductionView"));
const SchedulerView = lazy(() => import("./features/admin/scheduler/SchedulerView"));
const ChartOfAccounts = lazy(() => import("./features/finance/ChartOfAccounts"));
const GeneralLedger = lazy(() => import("./features/finance/GeneralLedger"));
const GroupConsolidationView = lazy(() => import("./features/finance/GroupConsolidationView"));
const FinancialStatementsView = lazy(() => import("./features/finance/FinancialStatementsView"));
const ClosingView = lazy(() => import("./features/finance/ClosingView"));
const PeriodUnlockView = lazy(() => import("./features/finance/PeriodUnlockView"));
const BiFinanceView = lazy(() => import("./features/finance/BiFinanceView"));
const FinanceTowerView = lazy(() => import("./features/finance/FinanceTowerView"));
const ProfitabilityView = lazy(() => import("./features/finance/ProfitabilityView"));
const CashFlowForecastView = lazy(() => import("./features/finance/CashFlowForecastView"));
const BudgetView = lazy(() => import("./features/finance/BudgetView"));
const TaxCenterView = lazy(() => import("./features/finance/TaxCenterView"));
const ManagerDashboard = lazy(() => import("./features/manager/ManagerDashboard"));
const SalesHome = lazy(() => import("./features/home/SalesHome"));
const AdminHome = lazy(() => import("./features/home/AdminHome"));
// EPIC 1 · PS-18 — Dasbor Manajer (antrean persetujuan, target tim, keterlambatan hari ini).
const ManagerHome = lazy(() => import("./features/home/ManagerHome"));
const PurchaseOrderManagement = lazy(() => import("./features/admin/PurchaseOrderManagement"));
const BlanketPOView = lazy(() => import("./features/purchasing/BlanketPOView"));
const InventoryStatusBoard = lazy(() => import("./features/inventory/InventoryStatusBoard"));
const StockBucketsView = lazy(() => import("./features/inventory/StockBucketsView"));
const LotsView = lazy(() => import("./features/inventory/lots/LotsView"));
const InterCompanyTransfers = lazy(() => import("./features/transfers/InterCompanyTransfers"));
const EscalationManagement = lazy(() => import("./features/manager/EscalationManagement"));
const TaxInvoices = lazy(() => import("./features/finance/TaxInvoices"));
const SalesReturns = lazy(() => import("./features/sales/SalesReturns"));
const ReturnPoliciesView = lazy(() => import("./features/sales/ReturnPoliciesView"));const SpecialOrders = lazy(() => import("./features/sales/SpecialOrders"));
const PricelistView = lazy(() => import("./features/sales/PricelistView"));
// F1b (D-14) — Daftar Harga per Pelanggan (harga langganan + penjagaan batas bawah).
const CustomerPricelistView = lazy(() => import("./features/sales/CustomerPricelistView"));
const ProductTemplatesView = lazy(() => import("./features/sales/ProductTemplatesView"));
const ColorLibraryView = lazy(() => import("./features/sales/ColorLibraryView"));
const DomainRegistryView = lazy(() => import("./features/admin/domain/DomainRegistryView"));
const UomConversionView = lazy(() => import("./features/admin/uom/UomConversionView"));
const ApprovalInbox = lazy(() => import("./features/approvals/ApprovalInbox"));
const MyApprovalsView = lazy(() => import("./features/approvals/MyApprovalsView"));
// FASE E-8 (E8.7/E8.20) — dua MEJA KERJA: Admin Sales (alur pesanan & pemenuhan) dan
// Finance (uang masuk & pajak keluaran). Keduanya menyusun antrean dari mesin yang sudah
// ada (papan pending SO · backorder · retur · PIN · penagihan) — bukan mesin baru (E8.11).
const SalesAdminDesk = lazy(() => import("./features/sales_admin/SalesAdminDesk"));
const FinanceDesk = lazy(() => import("./features/finance/FinanceDesk"));

// PS-20 — peta view tujuan → hub induknya, untuk tombol "Buka" di Persetujuan Saya.
const APPROVAL_HUB_OF = {
  "rnd-specs": "rnd-hub",
  "rnd-samples": "rnd-hub",
  "purchase-requisitions": "sourcing",
  "special-orders": "sales-orders",
};
// FASE G-1 — Pusat Amandemen (koreksi ber-alasan, ber-dampak, ber-penyetuju).
const AmendmentCenterView = lazy(() => import("./features/finance/amendments/AmendmentCenterView"));
const ApprovalRulesSettings = lazy(() => import("./features/settings/ApprovalRulesSettings"));
// FASE E-4 (E4d) — satu layar untuk semua master berlapis global → badan usaha.
const EntityMastersView = lazy(() => import("./features/settings/masters/EntityMastersView"));
// FASE E-3 — layar "Badan Usaha & Akses" (entitas + akun + kesiapan) dalam satu pintu.
const EntitiesAccessView = lazy(() => import("./features/settings/entities/EntitiesAccessView"));
// FASE E-4 (E4.1) — Master Gudang: mode pemakaian (bersama / khusus badan usaha),
// isi gudang per pemilik stok, dan pagar agar barang tidak terkurung.
const WarehouseMasterView = lazy(() => import("./features/wms/warehouses/WarehouseMasterView"));
// FASE G-0 — Pusat Pengaturan (satu pintu semua konfigurasi: cari, penjelasan,
// simulator "coba dulu", jejak lapisan, riwayat, berlaku-sejak, Daftar Dampak).
const SettingsHub = lazy(() => import("./features/settings/config/SettingsHub"));
const SuppliersView = lazy(() => import("./features/purchasing/SuppliersView"));
const MakloonsView = lazy(() => import("./features/purchasing/MakloonsView"));
const ProcessRecipesView = lazy(() => import("./features/purchasing/ProcessRecipesView"));
const MakloonOrdersView = lazy(() => import("./features/purchasing/MakloonOrdersView"));
// FASE D (PS-04/PS-11 · D-05/D-07/D-09) — klaim selisih makloon & kontrak mitra
const MakloonClaimsView = lazy(() => import("./features/purchasing/makloon/MakloonClaimsView"));
const ContractsView = lazy(() => import("./features/purchasing/contracts/ContractsView"));
const SupplierItemsView = lazy(() => import("./features/purchasing/supplier-items/SupplierItemsView"));
const PurchaseApprovalView = lazy(() => import("./features/purchasing/PurchaseApprovalView"));
const CashManagementView = lazy(() => import("./features/purchasing/CashManagementView"));
const PurchaseReturns = lazy(() => import("./features/purchasing/PurchaseReturns"));
const VendorBillsView = lazy(() => import("./features/purchasing/VendorBillsView"));
// FASE G-7 — Kontrabon (siklus tukar faktur supplier): gabung banyak faktur jadi satu
// tanda terima + satu pembayaran, plus "GR belum ditagih" & jadwal tukar faktur.
const ContraBonsView = lazy(() => import("./features/purchasing/contrabon/ContraBonsView"));
// FASE G-6 — Transaksi Antar Entitas (jual-beli antar-PT): dokumen kembar, saldo
// pasangan PT, settlement/netting.
const IntercoView = lazy(() => import("./features/finance/interco/IntercoView"));
// FASE E-7 (E7d) — Permintaan Internal: sales minta barang dari badan usaha lain,
// admin/manajer menjadikannya transaksi antar-PT.
const InternalRequestsView = lazy(() => import("./features/internal_requests/InternalRequestsView"));
const LandedCostView = lazy(() => import("./features/purchasing/LandedCostView"));
const InputTaxView = lazy(() => import("./features/purchasing/InputTaxView"));
const RFQView = lazy(() => import("./features/purchasing/RFQView"));
const PurchaseRequisitions = lazy(() => import("./features/purchasing/PurchaseRequisitions"));
const ReorderSuggestions = lazy(() => import("./features/purchasing/ReorderSuggestions"));
const EmployeesView = lazy(() => import("./features/hr/EmployeesView"));
const OrgUnitsView = lazy(() => import("./features/hr/OrgUnitsView"));
const EmployeeSelfService = lazy(() => import("./features/hr/EmployeeSelfService"));
const AttendanceView = lazy(() => import("./features/hr/AttendanceView"));
const AttendanceSetupView = lazy(() => import("./features/hr/AttendanceSetupView"));
const LiveTrackingView = lazy(() => import("./features/hr/LiveTrackingView"));
const VisitsView = lazy(() => import("./features/hr/VisitsView"));
const PayrollRunsView = lazy(() => import("./features/hr/PayrollRunsView"));
const PayslipsView = lazy(() => import("./features/hr/PayslipsView"));
const LeaveView = lazy(() => import("./features/hr/LeaveView"));
const OvertimeView = lazy(() => import("./features/hr/OvertimeView"));
const KpiView = lazy(() => import("./features/hr/KpiView"));
const DesignGalleryView = lazy(() => import("./features/hr/DesignGalleryView"));
const HrAnalyticsView = lazy(() => import("./features/hr/HrAnalyticsView"));
const StockAnalyticsView = lazy(() => import("./features/inventory/StockAnalyticsView"));
const LocationPutawayView = lazy(() => import("./features/wms/LocationPutawayView"));
const RfidTagsView = lazy(() => import("./features/rfid/RfidTagsView"));
const RfidDevicesView = lazy(() => import("./features/rfid/RfidDevicesView"));
const RfidGateMonitorView = lazy(() => import("./features/rfid/RfidGateMonitorView"));
const RfidLocationsView = lazy(() => import("./features/rfid/RfidLocationsView"));
const CashAdvancesView = lazy(() => import("./features/pettycash/CashAdvancesView"));
const SettlementsView = lazy(() => import("./features/pettycash/SettlementsView"));
const ExpenseCategoriesView = lazy(() => import("./features/pettycash/ExpenseCategoriesView"));
const VehicleLogsView = lazy(() => import("./features/pettycash/VehicleLogsView"));
const PdfTemplateDesigner = lazy(() => import("./features/pdf/PdfTemplateDesigner"));
const DocumentCenter = lazy(() => import("./features/documents/DocumentCenter"));
// FASE G-4 — Jejak Dokumen (relasi `refs[]` dua arah; jangkar bebas, termasuk QR cetak).
const DocTraceView = lazy(() => import("./features/documents/trace/DocTraceView"));
// FASE G-2 — Rencana Pembayaran fleksibel + denda sebagai dokumen.
const PaymentPlansView = lazy(() => import("./features/finance/payments/PaymentPlansView"));
// FASE F — R&D & Desain: spesifikasi → labdip/proofing → kontrak harga (hulu rantai).
const RndSpecsView = lazy(() => import("./features/rnd/RndSpecsView"));
const RndSamplesView = lazy(() => import("./features/rnd/RndSamplesView"));
const RndDesignsView = lazy(() => import("./features/rnd/RndDesignsView"));
const RndReportsView = lazy(() => import("./features/rnd/RndReportsView"));
// PS-18 — menu DESAINER (terpisah dari R&D): KPI desainer + eskalasi SLA aktif.
const DesignerKpiView = lazy(() => import("./features/designer/DesignerKpiView"));
const DivisionsView = lazy(() => import("./features/designer/DivisionsView"));

/** Fallback saat chunk view sedang di-fetch (code-splitting). */
function ViewLoader() {
  return (
    <div data-testid="view-loader" className="flex flex-col items-center justify-center py-24 text-[#8E8E93]">
      <Loader2 className="animate-spin mb-2" size={22} />
      <p className="text-[12px]">Memuat modul…</p>
    </div>
  );
}

export default function AppViewRouter(props) {
  const {
    hubInfo, activeView, onNavSelect, isComingSoon, pageMeta,
    user, token, selectedEntity, entities,
    data, loading, users, uoms, templates, permissions, previewHtml,
    auditLogs, auditFilters, setAuditFilters,
    movements, tasks, wmsInitialTab,
    selectedProduct, breakdown, cart, setCart,
    selectedCustomer, setSelectedCustomer, selectedAddress, setSelectedAddress,
    search, setSearch, settings, paymentTerms,
    focusDoc, setFocusDoc, openDocument, setActiveDetail, actions,
    configFocus, onConfigFocusConsumed,
    traceAnchor, onTraceAnchorConsumed,
    rndFocus, onRndFocusConsumed,
    caseFocus, onCaseFocusConsumed,
    lastDocument, lastLabel,
  } = props;

  const {
    inspectProduct, addToCart, createCustomer, submitOrder, mutateOrder,
    payInvoice, releaseReservation, markDelivered, generateDocument, generateLabel,
    approvePurchaseOrder, adminCreate, adminPatch, adminDelete, importMaster, exportMaster,
    updatePermissions, seedDemo, previewTemplate, refreshAudit,
    createInboundTask, createOutboundTasks, scanTask, advanceTask, issueTaxInvoice,
  } = actions;

  // Master-data CRUD props (AdminView dipakai ulang di beberapa domain hub via `only`).
  const adminProps = {
    data, loading, users, uoms, templates, entities, permissions, previewHtml,
    auditLogs, auditFilters, setAuditFilters,
    onAdminCreate: adminCreate, onAdminPatch: adminPatch, onAdminDelete: adminDelete,
    onImportMaster: importMaster, onExportMaster: exportMaster,
    onUpdatePermissions: updatePermissions, onPreviewTemplate: previewTemplate,
    onRefreshAudit: refreshAudit, onShowDetail: setActiveDetail,
    // FASE F — kolom Tahap Produk butuh identitas aktor (wewenang rilis) + muat ulang.
    currentUser: user, onReload: actions.loadAll,
  };

  return (
    <div className="mt-4 md:mt-5">
      {hubInfo && (
        <HubTabs
          hubId={hubInfo.hubId}
          tabs={hubInfo.tabs}
          activeView={activeView}
          onSelect={(view, tab) => onNavSelect(hubInfo.hubId, view, tab)}
        />
      )}
      <Suspense fallback={<ViewLoader />}>
      {/* Pengaturan & Master Data — hanya tab konfigurasi admin (master produk/kategori/uom/gudang telah pindah ke domain masing-masing). */}
      {activeView === "admin" && <AdminView {...adminProps} onSeedDemo={seedDemo} only={["customers", "integrations", "templates", "permissions", "audit"]} />}
      {/* FASE E-3 — badan usaha & akun kini punya layarnya sendiri (bukan tab Master Data). */}
      {activeView === "entities-access" && (
        <EntitiesAccessView
          currentUser={user}
          selectedEntity={selectedEntity}
          onNavigate={(view) => onNavSelect(view, view)}
        />
      )}
      {activeView === "pdf-templates" && <PdfTemplateDesigner currentUser={user} selectedEntity={selectedEntity} entities={entities} />}
      {activeView === "document-center" && <DocumentCenter currentUser={user} selectedEntity={selectedEntity} entities={entities} />}
      {activeView === "doc-trace" && (
        <DocTraceView
          currentUser={user}
          selectedEntity={selectedEntity}
          anchor={traceAnchor}
          anchorNonce={traceAnchor?.nonce || 0}
          onOpenDocument={openDocument}
          onAnchorConsumed={onTraceAnchorConsumed}
        />
      )}
      {/* Master data relokasi ke domain relevan (role-coherent IA). */}
      {activeView === "md-products" && <AdminView {...adminProps} only={["products"]} />}
      {activeView === "md-categories" && <AdminView {...adminProps} only={["categories"]} />}
      {activeView === "md-uoms" && <AdminView {...adminProps} only={["uoms"]} />}
      {/* FASE E-4 (E4.1) — gudang punya aturan pemakaian per badan usaha (bersama /
          khusus), jadi ia pindah dari tab generik Master Data ke layarnya sendiri. */}
      {activeView === "md-warehouses" && (
        <WarehouseMasterView entities={entities} selectedEntity={selectedEntity} currentUser={user} />
      )}
      {activeView === "reports" && <ManagerDashboard token={token} selectedEntity={selectedEntity} />}
      {activeView === "costing" && <CostingView selectedEntity={selectedEntity} />}
      {activeView === "ar-aging" && <ARAgingView selectedEntity={selectedEntity} currentUser={user} />}
      {activeView === "payment-plans" && <PaymentPlansView currentUser={user} selectedEntity={selectedEntity} onOpenDocument={openDocument} />}
      {activeView === "store-credit" && <StoreCreditView selectedEntity={selectedEntity} currentUser={user} />}
      {activeView === "bank-accounts" && <BankAccountsView selectedEntity={selectedEntity} />}
      {activeView === "bank-reconciliation" && <BankReconciliationView selectedEntity={selectedEntity} />}
      {activeView === "finance-cases" && <FinanceCasesView currentUser={user} selectedEntity={selectedEntity} entities={entities} focusCase={caseFocus} onFocusCaseConsumed={onCaseFocusConsumed} />}
      {activeView === "fixed-assets" && <FixedAssetsView selectedEntity={selectedEntity} entities={entities} />}
      {activeView === "production" && <ProductionView selectedEntity={selectedEntity} entities={entities} currentUser={user} />}
      {activeView === "scheduler" && <SchedulerView currentUser={user} onNavigate={(target) => onNavSelect(target, target)} />}
      {activeView === "chart-of-accounts" && <ChartOfAccounts entities={entities} />}
      {activeView === "general-ledger" && <GeneralLedger selectedEntity={selectedEntity} entities={entities} />}
      {activeView === "financial-statements" && <FinancialStatementsView selectedEntity={selectedEntity} />}
      {activeView === "closing" && <ClosingView selectedEntity={selectedEntity} entities={entities} currentUser={user} />}
      {activeView === "period-unlock" && <PeriodUnlockView selectedEntity={selectedEntity} entities={entities} currentUser={user} />}
      {activeView === "bi-finance" && <BiFinanceView selectedEntity={selectedEntity} />}
      {activeView === "finance-tower" && <FinanceTowerView selectedEntity={selectedEntity} />}
      {activeView === "profitability" && <ProfitabilityView selectedEntity={selectedEntity} />}
      {activeView === "cashflow-forecast" && <CashFlowForecastView selectedEntity={selectedEntity} />}
      {activeView === "budget" && <BudgetView selectedEntity={selectedEntity} currentUser={user} />}
      {activeView === "cs-pajak" && <TaxCenterView currentUser={user} selectedEntity={selectedEntity} />}
      {/* Kas & Aset — Digitalisasi Formulir Sukacita (PD / LPJ / Kendaraan) */}
      {activeView === "cash-advances" && <CashAdvancesView currentUser={user} selectedEntity={selectedEntity} entities={entities} />}
      {activeView === "settlements" && <SettlementsView currentUser={user} selectedEntity={selectedEntity} entities={entities} />}
      {activeView === "expense-categories" && <ExpenseCategoriesView currentUser={user} />}
      {activeView === "vehicle-logs" && <VehicleLogsView currentUser={user} selectedEntity={selectedEntity} entities={entities} />}
      {activeView === "consolidation" && <GroupConsolidationView entities={entities} />}
      {activeView === "sales-home" && <SalesHome token={token} user={user} onNavigate={(target) => onNavSelect(target, target)} />}
      {activeView === "admin-home" && <AdminHome token={token} entities={entities} selectedEntity={selectedEntity} onNavigate={(target) => onNavSelect(target, target)} />}
      {activeView === "manager-home" && <ManagerHome selectedEntity={selectedEntity} onNavigate={(target) => onNavSelect(target, target)} />}
      {activeView === "sales" && <SalesPortal data={data} loading={loading} selectedProduct={selectedProduct} breakdown={breakdown} onInspect={inspectProduct} onAdd={addToCart} cart={cart} setCart={setCart} selectedCustomer={selectedCustomer} setSelectedCustomer={setSelectedCustomer} selectedAddress={selectedAddress} setSelectedAddress={setSelectedAddress} onCreateCustomer={createCustomer} onSubmitOrder={submitOrder} search={search} setSearch={setSearch} onShowDetail={setActiveDetail} settings={settings} paymentTerms={paymentTerms} selectedEntity={selectedEntity} entities={entities} user={user} />}
      {activeView === "inventory-board" && <InventoryStatusBoard currentUser={user} selectedEntity={selectedEntity} entities={entities} />}
      {activeView === "stock-buckets" && <StockBucketsView entities={entities} currentUser={user} />}
      {/* Fase C (D-10/D-26/D-27) — Lot kelas satu: silsilah, recall, label */}
      {activeView === "inventory-lots" && (
        <LotsView user={user} products={data.products || []}
          warehouses={data.warehouses || []} entityId={selectedEntity} />
      )}
      {activeView === "price-approvals" && <PriceApprovals currentUser={user} />}
      {activeView === "interco-transfers" && <InterCompanyTransfers currentUser={user} />}
      {activeView === "orders" && <OrdersView orders={data.orders || []} loading={loading} user={user} onRefresh={actions.loadAll} onShowDetail={setActiveDetail} onIssueTaxInvoice={issueTaxInvoice} onSubmitForApproval={(id) => mutateOrder(`/sales-orders/${id}/submit-for-approval`, (order) => order.status === "approved" ? `${order.number} auto-approved (di bawah threshold).` : `${order.number} dikirim untuk approval (butuh ${order.required_approval_role || "approver"}).`)} onApprove={(id) => mutateOrder(`/sales-orders/${id}/approve`, (order) => `${order.number} approved.`)} onConfirm={(id) => mutateOrder(`/sales-orders/${id}/confirm`, (order) => `${order.number} confirmed.`)} onCancel={(id) => mutateOrder(`/sales-orders/${id}/cancel`, (order) => `${order.number} dibatalkan, stok unlock.`)} onPay={payInvoice} onGenerateDocument={generateDocument} onReleaseReservation={releaseReservation} onMarkDelivered={markDelivered} focusDoc={focusDoc} onClearFocus={() => setFocusDoc(null)} onOpenDocument={openDocument} />}
      {activeView === "tax-invoices" && <TaxInvoices currentUser={user} />}
      {/* FASE E-8 — MEJA ADMIN SALES & MEJA FINANCE. `onOpenDocument` dipakai supaya
          satu baris antrean melompat ke layar yang menanganinya (navigasi + auto-buka). */}
      {activeView === "sales-admin-desk" && (
        <SalesAdminDesk currentUser={user} selectedEntity={selectedEntity}
          onOpenDocument={openDocument} />
      )}
      {activeView === "finance-desk" && (
        <FinanceDesk currentUser={user} selectedEntity={selectedEntity}
          onOpenDocument={openDocument} />
      )}
      {activeView === "returns" && (
        <SalesReturns currentUser={user}
          onNavigate={(target) => onNavSelect(target, target)} />
      )}
      {activeView === "return-policies" && <ReturnPoliciesView currentUser={user} />}
      {activeView === "amendments" && <AmendmentCenterView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "special-orders" && <SpecialOrders currentUser={user} />}
      {activeView === "pricelist" && <PricelistView entities={entities} selectedEntity={selectedEntity} currentUser={user} />}
      {/* F1b — Daftar Harga per Pelanggan: harga langganan (pelanggan → PT → umum) */}
      {activeView === "cs-price-list" && (
        <CustomerPricelistView entities={entities} selectedEntity={selectedEntity} currentUser={user}
          onNavigate={(view) => onNavSelect("approval-inbox", view)} />
      )}
      {activeView === "product-templates" && <ProductTemplatesView currentUser={user} />}
      {activeView === "color-library" && <ColorLibraryView currentUser={user} />}
      {activeView === "domain-registry" && <DomainRegistryView />}
      {activeView === "uom-conversions" && <UomConversionView user={user} products={data.products || []} />}
      {activeView === "customers-crm" && <CrmView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "approval-inbox" && <ApprovalInbox currentUser={user} onNavigate={(navId, view, tab) => onNavSelect(navId, view, tab)} onOpenDocument={openDocument} />}
      {activeView === "my-approvals" && <MyApprovalsView currentUser={user} selectedEntity={selectedEntity} onNavigate={(view) => onNavSelect(APPROVAL_HUB_OF[view] || view, view)} />}
      {activeView === "approval-rules" && <ApprovalRulesSettings currentUser={user} />}
      {activeView === "entity-masters" && (
        <EntityMastersView currentUser={user} entities={entities} selectedEntity={selectedEntity} />
      )}
      {activeView === "settings-config" && (
        <SettingsHub
          currentUser={user}
          selectedEntity={selectedEntity}
          entities={entities}
          focusKey={configFocus?.key || ""}
          focusGroup={configFocus?.group || ""}
          focusNonce={configFocus?.nonce || 0}
          onFocusConsumed={onConfigFocusConsumed}
        />
      )}
      {activeView === "purchasing" && <PurchaseOrderManagement user={user} selectedEntity={selectedEntity} onApprovePO={approvePurchaseOrder} focusDoc={focusDoc} onClearFocus={() => setFocusDoc(null)} onOpenDocument={openDocument} />}
      {activeView === "blanket-po" && <BlanketPOView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "suppliers" && <SuppliersView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "makloons" && <MakloonsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "process-recipes" && <ProcessRecipesView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "makloon-orders" && <MakloonOrdersView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "makloon-claims" && <MakloonClaimsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "supplier-contracts" && <ContractsView currentUser={user} selectedEntity={selectedEntity} />}
      {/* FASE F — hub R&D & Desain (4 tab). `rndFocus` = deep-link dari Pustaka Warna,
          Kontrak Supplier, atau kartu desain (event global `kn-open-rnd`). */}
      {activeView === "rnd-specs" && (
        <RndSpecsView currentUser={user} selectedEntity={selectedEntity}
          focus={rndFocus?.view === "rnd-specs" ? rndFocus : null}
          onFocusConsumed={onRndFocusConsumed} />
      )}
      {activeView === "rnd-samples" && (
        <RndSamplesView currentUser={user} selectedEntity={selectedEntity}
          focus={rndFocus?.view === "rnd-samples" ? rndFocus : null}
          onFocusConsumed={onRndFocusConsumed} />
      )}
      {activeView === "rnd-designs" && <RndDesignsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "rnd-reports" && <RndReportsView currentUser={user} selectedEntity={selectedEntity} />}
      {/* PS-18 — hub Desainer: KPI per desainer + papan eskalasi SLA yang aktif. */}
      {activeView === "designer-kpi" && <DesignerKpiView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "rnd-divisions" && <DivisionsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "supplier-items" && <SupplierItemsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "purchase-approval" && <PurchaseApprovalView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "cash-management" && <CashManagementView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "purchase-returns" && <PurchaseReturns currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "vendor-bills" && <VendorBillsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "contra-bons" && <ContraBonsView currentUser={user} selectedEntity={selectedEntity} entities={entities} />}
      {activeView === "interco-transactions" && <IntercoView currentUser={user} selectedEntity={selectedEntity} entities={entities} />}
      {activeView === "internal-requests" && <InternalRequestsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "landed-cost" && <LandedCostView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "input-tax" && <InputTaxView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "rfq" && <RFQView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "purchase-requisitions" && <PurchaseRequisitions currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "reorder" && <ReorderSuggestions currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "operations" && <OperationsView data={data} movements={movements} tasks={tasks} entities={entities} selectedEntity={selectedEntity} onGenerateLabel={generateLabel} onCreateInboundTask={createInboundTask} onCreateOutboundTasks={createOutboundTasks} onScanTask={scanTask} onAdvanceTask={advanceTask} onShowDetail={setActiveDetail} token={token} user={user} defaultTab={wmsInitialTab} />}
      {activeView === "qc-inspection" && <QCInspection currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "hr-employees" && <EmployeesView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "hr-org-units" && <OrgUnitsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "hr-attendance" && <AttendanceView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "hr-attendance-setup" && <AttendanceSetupView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "hr-my-profile" && <EmployeeSelfService currentUser={user} />}
      {activeView === "hr-live-tracking" && <LiveTrackingView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "hr-visits" && <VisitsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "hr-payroll-runs" && <PayrollRunsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "hr-payslips" && <PayslipsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "hr-leave" && <LeaveView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "hr-overtime" && <OvertimeView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "cs-kpi" && <KpiView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "cs-design-gallery" && <DesignGalleryView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "cs-bi-hrd" && <HrAnalyticsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "cs-stock-analytics" && <StockAnalyticsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "wms-locations" && <LocationPutawayView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "cs-rfid-tags" && <RfidTagsView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "cs-rfid-devices" && <RfidDevicesView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "cs-rfid-gate" && <RfidGateMonitorView currentUser={user} selectedEntity={selectedEntity} />}
      {activeView === "cs-rfid-lokasi" && <RfidLocationsView currentUser={user} selectedEntity={selectedEntity} />}
      {isComingSoon && <ComingSoon title={pageMeta.title} kicker={pageMeta.kicker} onBack={() => onNavSelect(defaultNavIdForRole(user?.role), defaultViewForRole(user?.role))} />}
      {activeView === "escalations" && <EscalationManagement user={user} />}
      {activeView === "documents" && <DocumentsView templates={templates} loading={loading} lastDocument={lastDocument} lastLabel={lastLabel} onGenerateLabel={generateLabel} products={data.products || []} />}
      </Suspense>
    </div>
  );
}
