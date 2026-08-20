import { useState, useEffect } from "react";
import { Layers, PackageCheck, Truck, ArrowLeftRight, ClipboardCheck } from "lucide-react";
import InventoryStockView from "./InventoryStockView";
import InboundScanInterface from "./InboundScanInterface";
import OutboundScanInterface from "./OutboundScanInterface";
import TransferManagement from "./TransferManagement";
import CycleCount from "../inventory/CycleCount";
import { can } from "../../config/roles";

export default function OperationsView({
  data,
  movements,
  tasks,
  entities = [],
  selectedEntity = "all",
  onGenerateLabel,
  onCreateInboundTask,
  onCreateOutboundTasks,
  onScanTask,
  onAdvanceTask,
  onShowDetail,
  token,
  user,
  defaultTab,
}) {
  const [wmsTab, setWmsTab] = useState(defaultTab || "stok");

  // Sync tab when deep-link navigation from sidebar changes defaultTab
  useEffect(() => {
    if (defaultTab && defaultTab !== wmsTab) setWmsTab(defaultTab);
  }, [defaultTab]); // eslint-disable-line
  const WMS_TABS = [
    { id: "stok",     label: "Stok",        icon: Layers,        desc: "Lihat qty per gudang" },
    { id: "inbound",  label: "Barang Masuk",      icon: PackageCheck,  desc: "Penerimaan dari PO" },
    { id: "outbound", label: "Barang Keluar",     icon: Truck,         desc: "Ambil & kirim SO" },
    { id: "transfer", label: "Transfer",     icon: ArrowLeftRight, desc: "Pindah antar gudang" },
    { id: "cycle",    label: "Stock Opname",  icon: ClipboardCheck, desc: "Hitung fisik stok" },
  ];
  // AUDIT SALES vs ADMIN SALES (2026-08-15) — tab disaring per IZIN, bukan per peran.
  // Admin Sales diberi `wms.view` supaya bisa MEMANTAU progres gudang, tetapi tab
  // "Stock Opname" memanggil `/cycle-count/sessions` yang menuntut
  // `inventory.cycle_count` — izin yang tidak (dan tidak seharusnya) ia punya. Dulu
  // tabnya tetap tampil, diklik, lalu 403: pengguna menabrak dinding tanpa alasan.
  // Daftar di atas SENGAJA tetap lengkap (gate `check_nav_map.py` CHECK 2 membacanya);
  // yang disaring adalah apa yang DIRENDER.
  const perms = user?.permissions || {};
  const TAB_PERMISSION = { cycle: ["inventory", "cycle_count"] };
  const visibleTabs = WMS_TABS.filter((t) => {
    const need = TAB_PERMISSION[t.id];
    return !need || can(perms, need[0], need[1]);
  });
  const activeTab = visibleTabs.some((t) => t.id === wmsTab)
    ? wmsTab
    : (visibleTabs[0]?.id || "stok");
  return (
    <div data-testid="operations-view">
      {/* Tab Bar */}
      <div className="flex items-center gap-0.5 overflow-x-auto pb-0 mb-3 border-b border-[#EFF0F2]">
        {visibleTabs.map(tab => {
          const Icon = tab.icon;
          return (
            <button key={tab.id} onClick={() => setWmsTab(tab.id)}
              data-testid={`wms-tab-${tab.id}`}
              title={tab.desc}
              className={`flex items-center gap-1.5 px-3 py-2.5 text-[12px] font-medium whitespace-nowrap transition-all border-b-2 -mb-px ${
                activeTab === tab.id
                  ? "border-[#007AFF] text-[#007AFF] bg-blue-50/50"
                  : "border-transparent text-[#6B6B73] hover:text-[#3C3C43] hover:bg-[#FAFBFC]"
              }`}>
              <Icon size={13} /> {tab.label}
            </button>
          );
        })}
      </div>

      {/* STOK TAB — inventory balances per warehouse + rolls (Roll-as-SSOT) */}
      {activeTab === "stok" && (
        <InventoryStockView
          warehouses={data.warehouses || []}
          products={data.products || []}
          entities={entities}
          customers={data.customers || []}
          selectedEntity={selectedEntity}
          user={user}
        />
      )}

      {/* INBOUND TAB — receiving from PO, scan embedded */}
      {activeTab === "inbound" && (
        <div className="section-card">
          <div className="section-head">
            <div className="flex items-center gap-2 min-w-0">
              <span className="kicker">Barang Masuk</span>
              <h2>Penerimaan dari Pesanan Pembelian</h2>
            </div>
            <span className="text-[11px] text-[#6B6B73]">Scan barcode di formulir tugas di bawah</span>
          </div>
          <div className="section-body">
            <InboundScanInterface user={user} />
          </div>
        </div>
      )}

      {/* OUTBOUND TAB — picking & dispatch for SO, scan embedded */}
      {activeTab === "outbound" && (
        <div className="section-card">
          <div className="section-head">
            <div className="flex items-center gap-2 min-w-0">
              <span className="kicker">Barang Keluar</span>
              <h2>Pengambilan & Pengiriman Pesanan Penjualan</h2>
            </div>
            <span className="text-[11px] text-[#6B6B73]">Scan barcode di formulir tugas di bawah</span>
          </div>
          <div className="section-body">
            <OutboundScanInterface user={user} />
          </div>
        </div>
      )}

      {/* TRANSFER TAB */}
      {activeTab === "transfer" && (
        <div className="section-card">
          <div className="section-head">
            <div className="flex items-center gap-2 min-w-0">
              <span className="kicker">Transfer</span>
              <h2>Transfer Antar Gudang</h2>
            </div>
          </div>
          <div className="section-body">
            <TransferManagement user={user} />
          </div>
        </div>
      )}

      {/* CYCLE COUNT TAB */}
      {activeTab === "cycle" && (
        <CycleCount token={token} warehouses={data.warehouses || []} products={data.products || []} userRole={user?.role} />
      )}
    </div>
  );
}
