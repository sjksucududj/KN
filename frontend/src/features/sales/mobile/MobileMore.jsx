import { useState } from "react";
import { Users, RotateCcw, FileStack, Tags, Monitor, LogOut, ChevronRight, ArrowLeft, UserCircle } from "lucide-react";
import { roleLabel } from "../../../config/roles";
import CrmView from "../../crm/CrmView";
import SalesReturns from "../SalesReturns";
import SpecialOrders from "../SpecialOrders";
import PricelistView from "../PricelistView";

const MENU = [
  { id: "crm", label: "Pelanggan (CRM)", desc: "Kelola pelanggan & insentif", icon: Users },
  { id: "returns", label: "Retur Jual", desc: "Pengajuan & status retur", icon: RotateCcw },
  { id: "special", label: "Pesanan Khusus (MTO)", desc: "Pesanan khusus / dibuat sesuai pesanan", icon: FileStack },
  { id: "pricelist", label: "Daftar Harga", desc: "Lihat harga per entitas", icon: Tags },
];

const TITLES = { crm: "Pelanggan (CRM)", returns: "Retur Jual", special: "Special Order", pricelist: "Daftar Harga" };

export default function MobileMore({ user, token, selectedEntity, entities, onLogout, onForceDesktop }) {
  const [sub, setSub] = useState(null);

  if (sub) {
    return (
      <div data-testid={`mobile-sub-${sub}`} className="-mx-3.5 -mt-3.5">
        <div className="m-subpage-head">
          <button className="m-subpage-back" data-testid="mobile-sub-back" onClick={() => setSub(null)}><ArrowLeft size={17} /> Kembali</button>
          <span className="m-subpage-title">{TITLES[sub]}</span>
        </div>
        <div className="m-subpage-body">
          {sub === "crm" && <CrmView currentUser={user} selectedEntity={selectedEntity} />}
          {sub === "returns" && <SalesReturns currentUser={user} />}
          {sub === "special" && <SpecialOrders currentUser={user} />}
          {sub === "pricelist" && <PricelistView entities={entities} selectedEntity={selectedEntity} currentUser={user} />}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="mobile-more">
      {/* Profile card */}
      <div className="m-card flex items-center gap-3 p-4">
        <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-[#0058CC] text-[16px] font-bold text-white">
          {(user?.name || "S").slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-bold">{user?.name || "Sales"}</p>
          <p className="truncate text-[11.5px] m-muted">{user?.email}</p>
          {/* FASE E-8 — label peran dari registry (id mentah `sales_admin` tampil buruk). */}
          <p className="text-[10.5px] font-semibold uppercase tracking-wide text-[#0058CC]">{user?.role_label || roleLabel(user?.role)}</p>
        </div>
        <UserCircle size={22} className="text-[#C7C7CC]" />
      </div>

      {/* Menu */}
      <div className="m-card px-4">
        {MENU.map((m) => {
          const Icon = m.icon;
          return (
            <button key={m.id} data-testid={`mobile-more-${m.id}`} onClick={() => setSub(m.id)} className="m-list-row m-press w-full text-left">
              <span className="inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-[#F2F3F5]"><Icon size={17} className="text-[#0058CC]" /></span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-semibold">{m.label}</p>
                <p className="truncate text-[11px] m-muted">{m.desc}</p>
              </div>
              <ChevronRight size={16} className="text-[#C7C7CC]" />
            </button>
          );
        })}
      </div>

      {/* Settings */}
      <div className="m-card px-4">
        <button data-testid="mobile-force-desktop" onClick={onForceDesktop} className="m-list-row m-press w-full text-left">
          <span className="inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-[#F2F3F5]"><Monitor size={17} className="text-[#3C3C43]" /></span>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-semibold">Tampilan Desktop</p>
            <p className="truncate text-[11px] m-muted">Beralih ke antarmuka penuh</p>
          </div>
          <ChevronRight size={16} className="text-[#C7C7CC]" />
        </button>
        <button data-testid="mobile-logout" onClick={onLogout} className="m-list-row m-press w-full text-left">
          <span className="inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-[#FFECEB]"><LogOut size={17} className="text-[#C0392B]" /></span>
          <div className="min-w-0 flex-1"><p className="text-[13px] font-semibold text-[#C0392B]">Keluar</p></div>
        </button>
      </div>

      <p className="pt-1 text-center text-[10.5px] m-muted">Kain Nusantara — Mobile Sales</p>
    </div>
  );
}
