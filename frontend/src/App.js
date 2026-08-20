import { useRef, useState, useEffect } from "react";
import "./App.css";
import { LoginScreen, MetricCard, Sidebar, TopBar } from "./components/CoreWidgets";
import { formatQty } from "./utils/formatters";
import useIsMobile from "./hooks/useIsMobile";
import MobileSalesApp from "./features/sales/mobile/MobileSalesApp";
import DetailDrawer from "./components/DetailDrawer";
import TourMenu from "./components/TourMenu";
import OnboardingPanel from "./components/OnboardingPanel";
import EntitySwitcher from "./components/EntitySwitcher";
import NotificationCenter from "./components/NotificationCenter";
import { PAGE_META, GUIDANCE_MAP, buildNavGroups, defaultNavIdForRole, defaultViewForRole, isComingSoonView, isHomeView, resolveActiveNavId, hubForView } from "./config/navigationConfig";
import CommandPalette from "./components/CommandPalette";
import useDeepLinks from "./hooks/useDeepLinks";
import useViewDeepLink from "./hooks/useViewDeepLink";
import { useAppActions } from "./hooks/useAppActions";
import { setActiveEntity } from "./services/apiClient";
import axios, { API } from "./services/apiClient";
import GuidedTour from "./components/GuidedTour";
import AppViewRouter from "./AppViewRouter";
import PeriodUnlockBanner from "./components/PeriodUnlockBanner";
import ScopeReadOnlyBanner from "./components/ScopeReadOnlyBanner";
import { EntityScopeProvider } from "./context/EntityScopeContext";
import { entityShortById } from "./utils/entityLabel";
import { isGroupScope } from "./utils/writeScope";
import PublicVerify from "./features/documents/PublicVerify";
import {
  Archive,
  Boxes,
  Building2,
  Clock3,
  PackageCheck,
  Sparkles,
} from "lucide-react";


function App() {
  const [activeView, setActiveView] = useState(() => {
    const saved = JSON.parse(localStorage.getItem("kn_user") || "null");
    return saved ? defaultViewForRole(saved.role) : "sales";
  });
  const [activeNavId, setActiveNavId] = useState(() => {
    const saved = JSON.parse(localStorage.getItem("kn_user") || "null");
    return saved ? defaultNavIdForRole(saved.role) : "sales";
  });
  const [wmsInitialTab, setWmsInitialTab] = useState("stok");
  const [data, setData] = useState({ products: [], customers: [], orders: [], warehouses: [], metrics: {} });
  const [movements, setMovements] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [users, setUsers] = useState([]);
  const [uoms, setUoms] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [onboarding, setOnboarding] = useState(null);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [permissions, setPermissions] = useState({ matrix: {}, actions: [] });
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditFilters, setAuditFilters] = useState({ actor: "", module: "", action: "", date_from: "", date_to: "" });

  // Guided Tour state
  const [activeTour, setActiveTour] = useState(null);
  const [showTourMenu, setShowTourMenu] = useState(false);
  const [previewHtml, setPreviewHtml] = useState("");
  const [activeDetail, setActiveDetail] = useState(null);
  // EPIC6 — deep-link dokumen: { focus_type, focus_id } untuk auto-open di view tujuan.
  const [focusDoc, setFocusDoc] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Desktop: sidebar bisa di-hide/show (persist). Mobile (<=900px) pakai drawer (sidebarOpen).
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => typeof window !== "undefined" && localStorage.getItem("kn_sidebar_collapsed") === "1"
  );
  const handleToggleSidebar = () => {
    if (typeof window !== "undefined" && window.innerWidth <= 900) {
      setSidebarOpen((v) => !v);
    } else {
      setSidebarCollapsed((v) => {
        const nv = !v;
        try { localStorage.setItem("kn_sidebar_collapsed", nv ? "1" : "0"); } catch (_) { /* noop */ }
        return nv;
      });
    }
  };
  const [user, setUser] = useState(() => JSON.parse(localStorage.getItem("kn_user") || "null"));
  const [token, setToken] = useState(() => localStorage.getItem("kn_token") || "");
  // Semua deep-link global (Pusat Pengaturan · Jejak Dokumen · hub R&D) — lihat
  // hooks/useDeepLinks.js. `ready` menahan jangkar QR sampai pengguna masuk.
  const {
    configFocus, clearConfigFocus, traceAnchor, clearTraceAnchor, rndFocus, clearRndFocus,
    caseFocus, clearCaseFocus,
  } = useDeepLinks({ setActiveNavId, setActiveView, setSidebarOpen, ready: Boolean(user) });
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [breakdown, setBreakdown] = useState(null);
  const [cart, setCart] = useState([]);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [selectedAddress, setSelectedAddress] = useState("");
  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState("Sistem siap. Stok reservation dikunci 3 hari.");
  const [lastDocument, setLastDocument] = useState(null);
  const [lastLabel, setLastLabel] = useState(null);
  const [loading, setLoading] = useState(false);

  // Multi-Entity + Notification Center (Fase 0)
  const [entities, setEntities] = useState([]);
  const [entityContext, setEntityContext] = useState(() => JSON.parse(localStorage.getItem("kn_entity_ctx") || "null"));
  const [selectedEntity, setSelectedEntity] = useState(() => localStorage.getItem("kn_entity") || "all");
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);

  // Configuration Foundation (Fase 1A) consumed by Sales/Orders (Fase 1B)
  const [settings, setSettings] = useState({});
  const [paymentTerms, setPaymentTerms] = useState([]);

  // F-6 — device-aware: sales di HP dapat tampilan mobile-first dedicated.
  const isMobile = useIsMobile();
  const [forceDesktop, setForceDesktop] = useState(() => localStorage.getItem("kn_force_desktop") === "1");
  // Test affordance (default OFF): set localStorage kn_force_mobile="1" untuk merender
  // MobileSalesApp di lebar berapa pun (verifikasi UI mobile saat automasi memaksa desktop).
  const [forceMobile] = useState(() => typeof window !== "undefined" && localStorage.getItem("kn_force_mobile") === "1");

  const onSelectEntity = (id) => {
    setSelectedEntity(id);
    localStorage.setItem("kn_entity", id);
    setActiveEntity(id);  // sinkron header X-Entity-Id sebelum view anak re-fetch
  };

  // Pastikan header X-Entity-Id ter-set sejak awal (restore session / refresh).
  useEffect(() => { setActiveEntity(selectedEntity || "all"); }, [selectedEntity]);

  // FASE E-8 — SEGARKAN IZIN saat sesi dipulihkan dari localStorage.
  // Sejak tombol dinyalakan oleh `can(user.permissions, …)`, profil lama yang
  // tersimpan SEBELUM peran baru ada (atau setelah admin mengubah matriks izin)
  // membuat tombol yang sah ikut hilang tanpa alasan. `/auth/me` mengembalikan
  // izin efektif + label peran terbaru, jadi satu panggilan menutup selisih itu.
  useEffect(() => {
    if (!token) return;
    let alive = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/auth/me`);
        if (!alive || !r?.data?.id) return;
        setUser((prev) => {
          const next = {
            ...(prev || {}), ...r.data,
            permissions: r.data.permissions || {},
            role_label: r.data.role_label || prev?.role_label || "",
          };
          localStorage.setItem("kn_user", JSON.stringify(next));
          return next;
        });
        if (r.data.entity_context) {
          setEntityContext(r.data.entity_context);
          localStorage.setItem("kn_entity_ctx", JSON.stringify(r.data.entity_context));
          if (Array.isArray(r.data.entity_context.entities)) setEntities(r.data.entity_context.entities);
        }
      } catch {
        /* token kedaluwarsa → gate auth di bawah yang menangani */
      }
    })();
    return () => { alive = false; };
  }, [token]);

  // Auto-hide notice transien (mis. 'Login berhasil ...') agar tidak menetap permanen di TopBar.
  useEffect(() => {
    if (!notice) return undefined;
    const t = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(t);
  }, [notice]);

  // Switcher: cross-entity (admin/manager) lihat SEMUA entitas aktif; single-entity terkunci.
  const canSwitchEntity = entityContext
    ? entityContext.can_switch_entity !== false
    : entities.length > 1;
  const allowedEntityIds = entityContext?.allowed_entity_ids || entities.map((e) => e.id);
  const switcherEntities = canSwitchEntity
    ? entities
    : entities.filter((e) => allowedEntityIds.includes(e.id));

  // FASE E-3 (user story 7) — mode "Semua Entitas" = HANYA LIHAT. Pita peringatan
  // muncul selama mode itu aktif, dan berdenyut sekali lagi tiap kali server
  // menolak sebuah penyimpanan (event dari interseptor `apiClient`).
  const groupScope = isGroupScope(selectedEntity) && canSwitchEntity;
  const [scopeFlash, setScopeFlash] = useState(0);
  useEffect(() => {
    const onBlocked = () => setScopeFlash((n) => n + 1);
    window.addEventListener("kn:scope-blocked", onBlocked);
    return () => window.removeEventListener("kn:scope-blocked", onBlocked);
  }, []);

  // All async actions + side-effects live in this hook (SSOT for business logic).
  const actions = useAppActions({
    // values
    user, token, auditFilters, selectedCustomer, selectedAddress, cart, data, selectedEntity,
    // setters
    setUser, setToken, setActiveView, setNotice, setOnboarding, setShowOnboarding,
    setData, setTemplates, setUoms, setMovements, setTasks, setUsers, setPermissions, setAuditLogs,
    setSelectedCustomer, setSelectedAddress, setSelectedProduct, setBreakdown,
    setCart, setLastDocument, setLastLabel, setPreviewHtml,
    setActiveDetail, setLoading, setEntities, setNotifications, setUnreadCount,
    setSettings, setPaymentTerms, setEntityContext, setSelectedEntity,
    setActiveNavId,
  });
  const {
    login, logout, showMetricDetail, loadAll,
    markNotificationRead, markAllNotificationsRead, generateNotifications,
    approveFromNotification,
  } = actions;

  // Landing per peran: DETERMINISTIK saat pengguna berganti.
  // `login()` sudah mengarahkan ke halaman depan peran, tetapi pengguna bisa juga
  // berganti TANPA melewati jalur itu (pulih sesi dari localStorage milik akun lain,
  // tukar akun di tab yang sama, atau sesi disuntik oleh alat uji). Tanpa penjaga ini
  // layar peran SEBELUMNYA bisa tertinggal di depan mata — mis. manajer mendarat di
  // "Operasi Gudang". Deep-link tidak terganggu: efek hanya jalan saat `user.id`
  // benar-benar berubah, bukan saat berpindah view.
  const lastUserIdRef = useRef(user?.id || "");
  useEffect(() => {
    const id = user?.id || "";
    if (!id) { lastUserIdRef.current = ""; return; }
    if (id === lastUserIdRef.current) return;
    const firstLoad = lastUserIdRef.current === "";
    lastUserIdRef.current = id;
    if (firstLoad) return;   // state awal sudah dihitung dari peran tersimpan
    setActiveView(defaultViewForRole(user.role));
    setActiveNavId(defaultNavIdForRole(user.role));
  }, [user?.id, user?.role]);


  // \u2500\u2500\u2500 Navigation handler: receives { navId, view, tab } from grouped Sidebar \u2500\u2500\u2500
  const handleNavSelect = (navId, view, tab) => {
    if (navId === "home") {
      setActiveView(defaultViewForRole(user?.role));
      setActiveNavId(defaultNavIdForRole(user?.role));
    } else {
      setActiveNavId(navId);
      setActiveView(view || navId);
      if (tab) setWmsInitialTab(tab);
    }
    setSidebarOpen(false);
  };

  // ─── EPIC6 — deep-link dokumen terkait (Process Timeline / Document Hub) ───
  // Navigasi in-app ke view tujuan + set focusDoc agar view target auto-open dokumen.
  const openDocument = (link) => {
    if (!link || !link.view) return;
    handleNavSelect(link.nav_id || link.view, link.view);
    if (link.focus_id) setFocusDoc({ focus_type: link.focus_type, focus_id: link.focus_id });
    else setFocusDoc(null);
  };

  // ─── FASE E-4 — alamat untuk setiap layar (`?view=...&tab=...&entity=...`) ───
  // Satu layar sekarang bisa di-bookmark & dibagikan; menyegarkan halaman tidak
  // lagi melempar pengguna ke halaman depan peran.
  useViewDeepLink({
    role: user?.role,
    ready: Boolean(user && token),
    activeView,
    onNavigate: handleNavSelect,
    onPickEntity: onSelectEntity,
  });

  const navGroups = buildNavGroups(user?.role, {
    showComingSoon: settings?.ui?.show_coming_soon !== false,
    comingSoonCollapsed: settings?.ui?.coming_soon_collapsed !== false,
  });
  // Klasifikasi view (SSOT di navigationConfig): coming-soon & halaman landing role.
  const isComingSoon = isComingSoonView(activeView);
  const showHomeWidgets = isHomeView(activeView);

  const nav = navGroups; // passed to new Sidebar (groups prop)
  // Poin 11 — highlight sidebar SELALU turunan dari activeView (cegah desync saat navigasi non-sidebar).
  const effectiveNavId = resolveActiveNavId(activeView, activeNavId, user?.role);

  // Halaman verifikasi dokumen PUBLIK (tanpa login) — di-handle sebelum gate auth.
  const _verifyMatch = typeof window !== "undefined" && window.location.pathname.match(/^\/verify-document\/(.+)$/);
  if (_verifyMatch) return <PublicVerify code={decodeURIComponent(_verifyMatch[1])} />;

  // Gate auth. Token WAJIB ada, bukan hanya profil pengguna: bila `kn_user` masih
  // tersimpan tetapi `kn_token` hilang/kedaluwarsa (sesi lama, tab dibuka ulang setelah
  // token dibersihkan, sesi disuntik alat uji), dulu aplikasi tetap merender kerangka
  // penuh sehingga pengguna menatap layar penuh galat "Login diperlukan" tanpa tahu
  // harus masuk lagi. Sekarang dikembalikan ke layar masuk dengan pesan jelas.
  if (!user || !token) {
    return <LoginScreen onLogin={login}
      notice={user && !token ? "Sesi Anda sudah berakhir — silakan masuk lagi." : notice} />;
  }

  // F-6 — Sales di perangkat mobile → tampilan mobile-first dedicated (device-aware).
  // 'Tampilan Desktop' (forceDesktop) memberi escape-hatch ke antarmuka penuh.
  if (user.role === "sales" && (isMobile || forceMobile) && !forceDesktop) {
    return (
      <MobileSalesApp
        user={user}
        token={token}
        onLogout={logout}
        data={data}
        loading={loading}
        cart={cart}
        setCart={setCart}
        onInspect={actions.inspectProduct}
        onAdd={actions.addToCart}
        selectedCustomer={selectedCustomer}
        setSelectedCustomer={setSelectedCustomer}
        selectedAddress={selectedAddress}
        setSelectedAddress={setSelectedAddress}
        onSubmitOrder={actions.submitOrder}
        paymentTerms={paymentTerms}
        selectedEntity={selectedEntity}
        entities={entities}
        notifications={notifications}
        unreadCount={unreadCount}
        onMarkAllRead={markAllNotificationsRead}
        onForceDesktop={() => { localStorage.setItem("kn_force_desktop", "1"); setForceDesktop(true); }}
      />
    );
  }

  const pageMeta = PAGE_META[activeView] || { kicker: "Workspace", title: "Kain Nusantara" };
  const guidance = GUIDANCE_MAP[activeView];
  // Restrukturisasi IA — tab bar sekunder bila view aktif bagian dari sebuah hub.
  const hubInfo = hubForView(activeView, user?.role);

  return (
    <EntityScopeProvider
      selectedEntity={selectedEntity}
      entities={switcherEntities}
      canSwitch={canSwitchEntity}
      pickEntity={onSelectEntity}
    >
    <div className={`app-shell layout-grid ${sidebarCollapsed ? "sidebar-hidden" : ""}`}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <Sidebar
        groups={nav}
        activeNavId={effectiveNavId}
        activeView={activeView}
        onSelect={handleNavSelect}
        user={user}
        onLogout={logout}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <div className="app-main">
        <TopBar
          title={pageMeta.title}
          kicker={pageMeta.kicker}
          scopeLabel={groupScope ? "Semua Badan Usaha" : entityShortById(entities, selectedEntity)}
          onToggleSidebar={handleToggleSidebar}
          onSync={loadAll}
          syncing={loading}
          notice={notice}
          infoCta={guidance ? { label: guidance.label, onClick: () => setActiveView(guidance.target) } : null}
          entitySwitcher={<EntitySwitcher entities={switcherEntities} value={selectedEntity} onChange={onSelectEntity} canSwitch={canSwitchEntity} role={user?.role} homeEntityId={entityContext?.home_entity_id || ""} />}
          notificationCenter={
            <NotificationCenter
              notifications={notifications}
              unreadCount={unreadCount}
              canGenerate={["admin", "manager"].includes(user?.role)}
              currentUserRole={user?.role}
              onMarkRead={markNotificationRead}
              onMarkAll={markAllNotificationsRead}
              onGenerate={generateNotifications}
              onApprove={approveFromNotification}
              onNavigate={(target) => setActiveView(target)}
            />
          }
        />
        <main id="main-content" className="mx-auto w-full max-w-[1600px] px-4 py-4 md:px-5 md:py-5">
          <section data-testid="metrics-row" className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 no-print">
            {showHomeWidgets && <>
            <MetricCard testId="metric-products" icon={Archive} label="Produk Aktif" value={data.metrics?.products || 0} tone="rgba(0,122,255,.12)" hint="Buka katalog" onClick={() => showMetricDetail("products")} />
            <MetricCard testId="metric-available" icon={Boxes} label="Jml Tersedia" value={formatQty(data.metrics?.available_qty)} tone="rgba(52,199,89,.14)" hint="Lihat stok" onClick={() => showMetricDetail("available")} />
            <MetricCard testId="metric-reserved" icon={Clock3} label="Jml Dipesan" value={formatQty(data.metrics?.reserved_qty)} tone="rgba(175,82,222,.14)" hint="Buka orders" onClick={() => showMetricDetail("reserved")} />
            <MetricCard testId="metric-orders" icon={PackageCheck} label="Pesanan Aktif" value={data.metrics?.active_orders || 0} tone="rgba(255,149,0,.14)" hint="Control room" onClick={() => showMetricDetail("orders")} />
            <MetricCard testId="metric-warehouses" icon={Building2} label="Gudang" value={data.metrics?.warehouses || 0} tone="rgba(60,60,67,.10)" hint="Buka WMS" onClick={() => showMetricDetail("warehouses")} />
            </>}
          </section>

          <div className="md:hidden mt-3">
            <div data-testid="system-notice-mobile" className="info-ribbon">
              <Sparkles size={13} className="ribbon-icon" />
              <span>{notice}</span>
            </div>
          </div>

          <DetailDrawer detail={activeDetail} onClose={() => setActiveDetail(null)} onNavigate={(target) => { setActiveView(target); setActiveDetail(null); }} />

          {/* Onboarding Checklist Panel — hanya di home view (BUG #2 fix) */}
          {showOnboarding && showHomeWidgets && (
            <OnboardingPanel
              onboarding={onboarding}
              onDismiss={() => setShowOnboarding(false)}
              onUpdate={setOnboarding}
            />
          )}

          <PeriodUnlockBanner currentUser={user} onNavigate={(target) => setActiveView(target)} />

          {groupScope && (
            <ScopeReadOnlyBanner
              entities={switcherEntities}
              flash={scopeFlash}
              onPick={onSelectEntity}
            />
          )}

          <AppViewRouter
            hubInfo={hubInfo}
            activeView={activeView}
            onNavSelect={handleNavSelect}
            isComingSoon={isComingSoon}
            pageMeta={pageMeta}
            user={user}
            token={token}
            selectedEntity={selectedEntity}
            entities={entities}
            data={data}
            loading={loading}
            users={users}
            uoms={uoms}
            templates={templates}
            permissions={permissions}
            previewHtml={previewHtml}
            auditLogs={auditLogs}
            auditFilters={auditFilters}
            setAuditFilters={setAuditFilters}
            movements={movements}
            tasks={tasks}
            wmsInitialTab={wmsInitialTab}
            selectedProduct={selectedProduct}
            breakdown={breakdown}
            cart={cart}
            setCart={setCart}
            selectedCustomer={selectedCustomer}
            setSelectedCustomer={setSelectedCustomer}
            selectedAddress={selectedAddress}
            setSelectedAddress={setSelectedAddress}
            search={search}
            setSearch={setSearch}
            settings={settings}
            paymentTerms={paymentTerms}
            focusDoc={focusDoc}
            setFocusDoc={setFocusDoc}
            openDocument={openDocument}
            configFocus={configFocus}
            onConfigFocusConsumed={clearConfigFocus}
            traceAnchor={traceAnchor}
            onTraceAnchorConsumed={clearTraceAnchor}
            rndFocus={rndFocus}
            onRndFocusConsumed={clearRndFocus}
            caseFocus={caseFocus}
            onCaseFocusConsumed={clearCaseFocus}
            setActiveDetail={setActiveDetail}
            lastDocument={lastDocument}
            lastLabel={lastLabel}
            actions={actions}
          />
        </main>
      </div>

      {/* Command Palette (Ctrl+K) — lompat cepat ke menu mana pun */}
      <CommandPalette role={user?.role} onNavigate={handleNavSelect} />

      {/* Guided Tour Component */}
      {activeTour && (
        <GuidedTour
          isActive={true}
          onClose={() => setActiveTour(null)}
          steps={activeTour.steps}
          tourId={activeTour.id}
          onComplete={() => {
            setActiveTour(null);
          }}
        />
      )}

      {/* Floating Help Button */}
      <TourMenu
        userRole={user?.role}
        showMenu={showTourMenu}
        onToggleMenu={() => setShowTourMenu(!showTourMenu)}
        onSelectTour={(tour) => {
          setActiveTour(tour);
          setShowTourMenu(false);
        }}
      />
    </div>
    </EntityScopeProvider>
  );
}

export default App;
