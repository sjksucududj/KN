import { useState } from "react";
import { Home, Store, ShoppingCart, ClipboardList, Menu, Bell, Layers, X, CheckCheck } from "lucide-react";
import MobileSalesHome from "./MobileSalesHome";
import MobileCatalog from "./MobileCatalog";
import MobileCart from "./MobileCart";
import MobileOrders from "./MobileOrders";
import MobileMore from "./MobileMore";
import { entityShortById } from "../../../utils/entityLabel";

const TABS = [
  { id: "home", label: "Beranda", icon: Home },
  { id: "catalog", label: "Katalog", icon: Store },
  { id: "cart", label: "Keranjang", icon: ShoppingCart },
  { id: "orders", label: "Pesanan", icon: ClipboardList },
  { id: "more", label: "Lainnya", icon: Menu },
];

function NotifSheet({ notifications, onClose, onMarkAll }) {
  return (
    <div className="m-sheet-wrap" data-testid="mobile-notif-sheet">
      <div className="m-sheet-backdrop" onClick={onClose} />
      <div className="m-sheet">
        <div className="m-sheet-grip" />
        <div className="flex items-center justify-between px-4 py-2 border-b border-[#EFF0F2]">
          <h3 className="m-section-title">Notifikasi</h3>
          <div className="flex items-center gap-2">
            {onMarkAll && notifications.length > 0 && (
              <button data-testid="mobile-notif-markall" onClick={onMarkAll} className="inline-flex items-center gap-1 text-[12px] font-semibold text-[#0058CC]"><CheckCheck size={14} /> Tandai dibaca</button>
            )}
            <button onClick={onClose} aria-label="Tutup" className="text-[#6B6B73]"><X size={18} /></button>
          </div>
        </div>
        <div className="overflow-y-auto px-4 py-2" style={{ maxHeight: "60vh" }}>
          {notifications.length === 0 ? (
            <div className="py-12 text-center text-[13px] m-muted">Belum ada notifikasi.</div>
          ) : notifications.map((n) => (
            <div key={n.id} className={`m-list-row ${n.read ? "" : ""}`} data-testid={`mobile-notif-${n.id}`}>
              <span className={`mt-0.5 h-2 w-2 flex-shrink-0 rounded-full ${n.read ? "bg-[#D6D7DC]" : "bg-[#0058CC]"}`} />
              <div className="min-w-0 flex-1">
                <p className="text-[12.5px] font-semibold leading-tight">{n.title || n.type}</p>
                {n.body && <p className="text-[11.5px] m-muted leading-snug mt-0.5">{n.body}</p>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function MobileSalesApp(props) {
  const {
    user, token, onLogout, data, loading, cart, setCart,
    onInspect, onAdd, selectedCustomer, setSelectedCustomer,
    selectedAddress, setSelectedAddress, onSubmitOrder, paymentTerms,
    selectedEntity, entities, notifications = [], unreadCount = 0,
    onMarkAllRead, onForceDesktop,
  } = props;

  const [tab, setTab] = useState("home");
  const [notifOpen, setNotifOpen] = useState(false);

  const cartCount = (cart || []).reduce((s, it) => s + Number(it.quantity || 0), 0);
  // `/api/entities` tak punya field `name` — pakai resolver bersama supaya
  // header POS mobile tidak pernah menampilkan id teknis (`ent_ksc`).
  const entityName = entityShortById(entities, selectedEntity);

  const goCatalog = () => setTab("catalog");

  return (
    <div className="m-shell" data-testid="mobile-sales-app">
      <header className="m-appbar">
        <div className="m-brand-mark"><Layers size={16} /></div>
        <div className="m-title">
          <span className="t1">Halo, {(user?.name || "Sales").split(" ")[0]}</span>
          <span className="t2">{entityName}</span>
        </div>
        <button className="m-act" data-testid="mobile-notif-btn" onClick={() => setNotifOpen(true)} aria-label="Notifikasi">
          <Bell size={18} />
          {unreadCount > 0 && <span className="m-badge">{unreadCount > 9 ? "9+" : unreadCount}</span>}
        </button>
      </header>

      {notifOpen && <NotifSheet notifications={notifications} onClose={() => setNotifOpen(false)} onMarkAll={onMarkAllRead} />}

      <main className={`m-main ${tab === "catalog" ? "m-flush" : ""}`} data-testid={`mobile-view-${tab}`}>
        {tab === "home" && <MobileSalesHome token={token} user={user} onNewOrder={goCatalog} onOpenTab={setTab} />}
        {tab === "catalog" && (
          <MobileCatalog data={data} loading={loading} onAdd={onAdd} onInspect={onInspect}
            entityId={selectedEntity} cart={cart} onOpenCart={() => setTab("cart")}
            selectedCustomer={selectedCustomer} />
        )}
        {tab === "cart" && (
          <MobileCart cart={cart} setCart={setCart} data={data}
            selectedCustomer={selectedCustomer} setSelectedCustomer={setSelectedCustomer}
            selectedAddress={selectedAddress} setSelectedAddress={setSelectedAddress}
            paymentTerms={paymentTerms} onSubmitOrder={onSubmitOrder} onAdd={onAdd}
            entityId={selectedEntity} onBrowse={goCatalog} onDone={() => setTab("orders")} />
        )}
        {tab === "orders" && <MobileOrders orders={data?.orders || []} loading={loading} onBrowse={goCatalog} />}
        {tab === "more" && (
          <MobileMore user={user} token={token} selectedEntity={selectedEntity} entities={entities}
            onLogout={onLogout} onForceDesktop={onForceDesktop} />
        )}
      </main>

      <nav className="m-tabbar" data-testid="mobile-tabbar">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} data-testid={`mobile-tab-btn-${t.id}`} className={`m-tab ${active ? "active" : ""}`} onClick={() => setTab(t.id)} aria-current={active}>
              <span className="m-tab-ico">
                <Icon size={21} strokeWidth={active ? 2.4 : 2} />
                {t.id === "cart" && cartCount > 0 && (
                  <span className="m-tab-badge" data-testid="mobile-tab-cart-count">{cartCount > 99 ? "99+" : cartCount}</span>
                )}
              </span>
              {t.label}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
