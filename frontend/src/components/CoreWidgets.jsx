import { useState, useEffect } from "react";
import { ChevronDown, ChevronRight, Clock, Layers3, LogOut, Menu, RefreshCw, Search, Sparkles, Star, X } from "lucide-react";
import { roleLabel } from "../config/roles";

export function StatusPill({ status, testId }) {
  return <span data-testid={testId} className={`status-pill status-${String(status || "").toLowerCase()}`}>{String(status || "-").replaceAll("_", " ")}</span>;
}

export function MetricCard({ icon: Icon, label, value, tone, testId, onClick, hint }) {
  return (
    <button type="button" data-testid={testId} className="metric-card" onClick={onClick}>
      <div className="metric-icon" style={{ background: tone }}>
        <Icon size={18} data-testid={`${testId}-icon`} />
      </div>
      <div className="metric-body">
        <span className="metric-label" data-testid={`${testId}-label`}>{label}</span>
        <span className="metric-value" data-testid={`${testId}-value`}>{value}</span>
        {hint && <span className="metric-hint" data-testid={`${testId}-hint`}>{hint}</span>}
      </div>
    </button>
  );
}

/** Sidebar grouped navigation (KN_14 \u00a75.2 IA) */
export function Sidebar({ groups = [], activeNavId, activeView, onSelect, user, onLogout, open, onClose }) {
  const initials = (user?.name || user?.email || "?").slice(0, 2).toUpperCase();

  // Compute which group contains the current active nav item
  const activeGroupId = (() => {
    for (const entry of groups) {
      if (entry.type === "group") {
        if (entry.items?.some(item => item.id === activeNavId)) return entry.groupId;
      }
    }
    return null;
  })();

  // Expanded groups \u2014 default open: the group containing the active item
  const [expanded, setExpanded] = useState(() => {
    try {
      const stored = JSON.parse(localStorage.getItem("kn_nav_expanded") || "null");
      if (stored && Array.isArray(stored)) return new Set(stored);
    } catch (_) { /* ignore */ }
    // FASE G-0 — grup dengan `defaultCollapsed === false` (mis. "Segera Hadir" saat setting
    // `ui.coming_soon_collapsed` dimatikan) langsung tampil terbuka pada kunjungan pertama.
    const initial = new Set(activeGroupId ? [activeGroupId] : []);
    (groups || []).forEach((g) => {
      if (g.type === "group" && g.defaultCollapsed === false) initial.add(g.groupId);
    });
    return initial;
  });

  // Auto-expand group when active item changes (e.g., external navigation)
  useEffect(() => {
    if (activeGroupId && !expanded.has(activeGroupId)) {
      setExpanded(prev => {
        const next = new Set(prev);
        next.add(activeGroupId);
        localStorage.setItem("kn_nav_expanded", JSON.stringify([...next]));
        return next;
      });
    }
  }, [activeGroupId]); // eslint-disable-line

  const toggleGroup = (groupId) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      localStorage.setItem("kn_nav_expanded", JSON.stringify([...next]));
      return next;
    });
  };

  // ─── Favorit / Pin (Restrukturisasi IA) — per user, max 5, persist localStorage ───
  const favKey = `kn_favs_${user?.email || "anon"}`;
  const [favs, setFavs] = useState(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(favKey) || "[]");
      return Array.isArray(stored) ? stored : [];
    } catch (_) { return []; }
  });
  const itemIndex = (() => {
    const idx = {};
    for (const entry of groups) {
      if (entry.type === "standalone" && !entry.comingSoon) idx[entry.id] = entry;
      if (entry.type === "group" && !entry.comingSoonGroup) {
        (entry.items || []).forEach(item => { if (!item.comingSoon) idx[item.id] = item; });
      }
    }
    return idx;
  })();
  const toggleFav = (id) => {
    setFavs(prev => {
      const next = prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id].slice(-5);
      localStorage.setItem(favKey, JSON.stringify(next));
      return next;
    });
  };
  const favItems = favs.map(id => itemIndex[id]).filter(Boolean);

  const FavStar = ({ id }) => (
    <span
      role="button"
      tabIndex={-1}
      data-testid={`fav-toggle-${id}`}
      title={favs.includes(id) ? "Hapus dari favorit" : "Pin ke favorit"}
      onClick={(e) => { e.stopPropagation(); toggleFav(id); }}
      className="fav-star"
      style={{ marginLeft: "auto", display: "inline-flex", opacity: favs.includes(id) ? 1 : 0.25, color: favs.includes(id) ? "#F5A623" : "inherit" }}
    >
      <Star size={11} fill={favs.includes(id) ? "#F5A623" : "none"} />
    </span>
  );

  return (
    <>
      <div data-testid="sidebar-backdrop" className={`sidebar-backdrop ${open ? "open" : ""} no-print`} onClick={onClose} aria-hidden="true" />
      <aside data-testid="app-sidebar" className={`app-sidebar ${open ? "open" : ""} no-print`}>
        {/* Brand */}
        <div className="sidebar-brand">
          <div data-testid="brand-mark" className="sidebar-brand-mark"><Layers3 size={16} /></div>
          <div className="sidebar-brand-text">
            <span data-testid="app-brand" className="t1">Kain Nusantara</span>
            <span data-testid="app-subtitle" className="t2">ERP · WMS · Sales</span>
          </div>
        </div>

        {/* Navigation */}
        <nav data-testid="main-navigation" className="sidebar-nav" aria-label="Main">
          {/* Pencarian cepat (Command Palette Ctrl+K) */}
          <button
            type="button"
            data-testid="open-command-palette"
            className="sidebar-item"
            style={{ border: "1px dashed rgba(120,120,128,.35)", borderRadius: 8, marginBottom: 6 }}
            onClick={() => window.dispatchEvent(new CustomEvent("kn-open-palette"))}
          >
            <Search size={14} />
            <span className="label" style={{ opacity: .75 }}>Cari menu…</span>
            <span style={{ marginLeft: "auto", fontSize: 10, opacity: .5, letterSpacing: ".04em" }}>Ctrl+K</span>
          </button>

          {/* Favorit (pin) */}
          {favItems.length > 0 && (
            <div className="sidebar-group" data-testid="nav-favorites">
              <div className="sidebar-group-header" style={{ cursor: "default" }}>
                <Star size={12} className="group-icon" />
                <span className="group-label">Favorit</span>
              </div>
              <div className="sidebar-group-items">
                {favItems.map(item => {
                  const ItemIcon = item.icon;
                  const isActive = item.id === activeNavId;
                  return (
                    <button
                      key={`fav-${item.id}`}
                      data-testid={`nav-fav-${item.id}`}
                      className={`sidebar-item sidebar-sub-item ${isActive ? "active" : ""}`}
                      onClick={() => onSelect(item.id, item.view || item.id, item.tab)}
                    >
                      <ItemIcon size={14} />
                      <span className="label">{item.label}</span>
                      <FavStar id={item.id} />
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {groups.map((entry) => {
            if (entry.type === "standalone") {
              const Icon = entry.icon;
              const isActive = activeNavId === entry.id || activeView === entry.view;
              return (
                <button
                  key={entry.id}
                  data-testid={`nav-${entry.id}`}
                  className={`sidebar-item ${isActive ? "active" : ""}`}
                  onClick={() => onSelect(entry.id, entry.view)}
                  aria-current={isActive ? "page" : undefined}
                >
                  <Icon size={16} />
                  <span className="label">{entry.label}</span>
                  <FavStar id={entry.id} />
                </button>
              );
            }

            if (entry.type === "group") {
              const GroupIcon = entry.icon;
              const isOpen = expanded.has(entry.groupId);
              const groupHasActive = entry.items?.some(item => item.id === activeNavId);
              return (
                <div key={entry.groupId} className={`sidebar-group ${entry.comingSoonGroup ? "coming-soon-group" : ""}`} data-testid={`nav-group-${entry.groupId}`}>
                  {/* Group header */}
                  <button
                    className={`sidebar-group-header ${groupHasActive ? "has-active" : ""}`}
                    onClick={() => toggleGroup(entry.groupId)}
                    aria-expanded={isOpen}
                    data-testid={`nav-group-toggle-${entry.groupId}`}
                  >
                    <GroupIcon size={14} className="group-icon" />
                    <span className="group-label">{entry.label}</span>
                    {isOpen
                      ? <ChevronDown size={12} className="chevron" />
                      : <ChevronRight size={12} className="chevron" />
                    }
                  </button>

                  {/* Group items */}
                  {isOpen && (
                    <div className="sidebar-group-items">
                      {entry.items.map(item => {
                        const ItemIcon = item.icon;
                        const isActive = item.id === activeNavId;
                        return (
                          <button
                            key={item.id}
                            data-testid={`nav-${item.id}`}
                            className={`sidebar-item sidebar-sub-item ${isActive ? "active" : ""} ${item.comingSoon ? "coming-soon" : ""}`}
                            onClick={() => onSelect(item.id, item.view || item.id, item.tab)}
                            aria-current={isActive ? "page" : undefined}
                            title={item.comingSoon ? "Segera hadir" : item.label}
                          >
                            <ItemIcon size={14} />
                            <span className="label">{item.label}</span>
                            {item.comingSoon ? (
                              <span className="cs-badge-inline" title="Segera hadir">
                                <Clock size={9} />
                              </span>
                            ) : (
                              <FavStar id={item.id} />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            }
            return null;
          })}
        </nav>

        {/* Footer */}
        <div className="sidebar-footer">
          <div className="user-chip" data-testid="user-menu-button">
            <div className="avatar">{initials}</div>
            <div className="user-text">
              <span className="name">{user?.name || user?.email?.split("@")[0]}</span>
              {/* FASE E-8 — kartu profil dulu mencetak id peran MENTAH: layar
                  memamerkan "Sales_admin" (CSS mengapitalkan `sales_admin`).
                  Label manusia wajib lewat registry peran. */}
              <span className="role">{user?.role_label || roleLabel(user?.role)}</span>
            </div>
          </div>
          <button data-testid="logout-button" className="secondary-button" onClick={onLogout}><LogOut size={14} /> Keluar</button>
        </div>
      </aside>
    </>
  );
}

export function TopBar({ title, kicker, onToggleSidebar, onSync, syncing, notice, onShowDetail, infoCta, entitySwitcher, notificationCenter, scopeLabel }) {
  return (
    <header className="topbar no-print" role="banner">
      <button
        type="button"
        data-testid="sidebar-toggle-button"
        className="icon-button menu-toggle"
        onClick={onToggleSidebar}
        aria-label="Toggle navigation"
      >
        <Menu size={16} />
      </button>
      <div className="title-block">
        {kicker && (
          <nav className="breadcrumb" data-testid="breadcrumb" aria-label="Breadcrumb">
            <span className="crumb-root">Beranda</span>
            <span className="crumb-sep" aria-hidden="true">›</span>
            <span className="kicker" data-testid="page-kicker">{kicker}</span>
            {/* FASE E-3 — judul layar menyebut badan usaha yang sedang dilihat,
                supaya angka di layar tidak pernah dibaca untuk badan usaha yang salah. */}
            {scopeLabel && (
              <>
                <span className="crumb-sep" aria-hidden="true">›</span>
                <span className="kicker kicker-scope" data-testid="page-scope-label">{scopeLabel}</span>
              </>
            )}
          </nav>
        )}
        <h1 data-testid="page-title" className="page-title">{title}</h1>
      </div>
      {entitySwitcher && <div className="topbar-entity">{entitySwitcher}</div>}
      {notice && (
        <div data-testid="system-notice" className="info-ribbon desktop-only">
          <Sparkles size={13} className="ribbon-icon" />
          <span data-testid="system-notice-text">{notice}</span>
          {infoCta && (
            <button data-testid="system-notice-cta" className="nav-button ribbon-cta" onClick={infoCta.onClick}>{infoCta.label}</button>
          )}
        </div>
      )}
      <div className="topbar-actions">
        {notificationCenter}
        <button data-testid="refresh-data-button" className="icon-button" onClick={onSync} aria-label="Sync data" title="Sync">
          <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
        </button>
      </div>
    </header>
  );
}

export function PageSection({ kicker, title, actions, children, testId }) {
  return (
    <section data-testid={testId} className="section-card">
      <div className="section-head">
        <div className="flex items-center min-w-0">
          {kicker && <span className="kicker">{kicker}</span>}
          {title && <h2 className="truncate">{title}</h2>}
        </div>
        {actions && <div className="flex flex-wrap gap-2 justify-end">{actions}</div>}
      </div>
      <div className="section-body">{children}</div>
    </section>
  );
}

// LoginScreen extracted to ./LoginScreen.jsx (KN_02 modularity); re-export for back-compat.
export { LoginScreen } from "./LoginScreen";

// Re-export close icon for backwards compat if needed
export { X as CloseIcon };
