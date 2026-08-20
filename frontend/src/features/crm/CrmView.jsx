import { useState } from "react";
import { Users, Receipt, TrendingUp, ShieldCheck, SlidersHorizontal, Percent, KanbanSquare, MessageSquare } from "lucide-react";
import CustomerList from "./CustomerList";
import CollectionWorklist from "./CollectionWorklist";
import SalesForceDashboard from "./SalesForceDashboard";
import CreditOverridesPanel from "./CreditOverridesPanel";
import IncentiveSchemeEditor from "./IncentiveSchemeEditor";
import IncentiveRatesEditor from "./IncentiveRatesEditor";
import LeadsPipeline from "./LeadsPipeline";
import OmnichannelInteractions from "./OmnichannelInteractions";

/**
 * CrmView — modul Pelanggan / CRM + Sales Force (KN_17).
 * Sub-tab: Pelanggan · Penagihan · Sales Force · Rate Insentif · Skema (Arsip) · Approval Kredit.
 * Row-level scoping ditegakkan backend (sales hanya melihat miliknya).
 */
export default function CrmView({ currentUser, selectedEntity }) {
  const role = currentUser?.role;
  const isManager = role === "admin" || role === "manager";
  const TABS = [
    { key: "customers", label: "Pelanggan", icon: Users },
    { key: "leads", label: "Leads", icon: KanbanSquare },
    { key: "interactions", label: "Interaksi", icon: MessageSquare },
    { key: "collection", label: "Penagihan", icon: Receipt },
    { key: "salesforce", label: "Sales Force", icon: TrendingUp },
    ...(isManager ? [{ key: "rates", label: "Rate Insentif", icon: Percent }] : []),
    ...(isManager ? [{ key: "schemes", label: "Skema (Arsip)", icon: SlidersHorizontal }] : []),
    ...(isManager ? [{ key: "approvals", label: "Persetujuan Kredit", icon: ShieldCheck }] : []),
  ];
  const [tab, setTab] = useState("customers");

  return (
    <div data-testid="crm-view">
      <div className="tab-bar mb-3">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button key={t.key} data-testid={`crm-tab-${t.key}`}
              className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
              <Icon size={13} /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === "customers" && <CustomerList currentUser={currentUser} selectedEntity={selectedEntity} />}
      {tab === "leads" && <LeadsPipeline currentUser={currentUser} selectedEntity={selectedEntity} />}
      {tab === "interactions" && <OmnichannelInteractions currentUser={currentUser} selectedEntity={selectedEntity} />}
      {tab === "collection" && <CollectionWorklist currentUser={currentUser} selectedEntity={selectedEntity} />}
      {tab === "salesforce" && <SalesForceDashboard currentUser={currentUser} selectedEntity={selectedEntity} />}
      {tab === "rates" && isManager && <IncentiveRatesEditor currentUser={currentUser} selectedEntity={selectedEntity} />}
      {tab === "schemes" && isManager && <IncentiveSchemeEditor currentUser={currentUser} selectedEntity={selectedEntity} />}
      {tab === "approvals" && isManager && <CreditOverridesPanel currentUser={currentUser} />}
    </div>
  );
}
