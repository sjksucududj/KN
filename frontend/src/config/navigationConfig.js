// ─── NAVIGATION CONFIG — fungsi builder + resolver (data di navStructure/navMeta) ─
// Data besar (NAV_STRUCTURE, HUB_TABS, PAGE_META, dst.) dipindah ke file terpisah
// agar file ini di bawah batas guardrail. Public API (import lama) TETAP di sini
// via re-export supaya komponen konsumen tidak perlu berubah.
import { Clock } from "lucide-react";
import { HUB_TABS, NAV_STRUCTURE } from "./navStructure";
import { PAGE_META, ROLE_HOME_REGISTRY, GUIDANCE_MAP } from "./navMeta";
// FASE E-8 (E8.1) — SATU definisi "boleh lihat menu ini?" (termasuk dua peran baru
// `sales_admin` & `finance`). Dulu keputusannya `roles.includes(role)` yang disalin di
// 5 tempat di berkas ini; peran baru harus ditambahkan ke ~40 baris `navStructure.js`.
import { roleCanSee } from "./roles";

// Re-export data (backward-compat untuk konsumen yang import dari navigationConfig).
export { HUB_TABS, NAV_STRUCTURE } from "./navStructure";
export { PAGE_META, ROLE_HOME_REGISTRY, GUIDANCE_MAP } from "./navMeta";

export function hubTabsForRole(hubId, role) {
  return (HUB_TABS[hubId] || []).filter((t) => roleCanSee(t.roles, role, t.view));
}

// ─── KLASIFIKASI VIEW (SSOT — dipakai App.js, jangan disalin ke komponen) ──────
// `cs-*` = konvensi "coming soon", KECUALI yang sudah punya route nyata (LIVE).
const LIVE_CS_VIEWS = [
  "cs-kpi", "cs-design-gallery", "cs-bi-hrd", "cs-pajak", "cs-stock-analytics",
  "cs-rfid-lokasi", "cs-rfid-tags", "cs-rfid-devices", "cs-rfid-gate",
  // F1b (D-14) — Daftar Harga per Pelanggan sudah punya layar & API nyata.
  "cs-price-list",
];
// Halaman landing per role — hanya di sini MetricCards & Onboarding ditampilkan.
const HOME_VIEWS = ["admin", "sales", "reports", "operations"];

export const isComingSoonView = (view) =>
  typeof view === "string" && view.startsWith("cs-") && !LIVE_CS_VIEWS.includes(view);
export const isHomeView = (view) => HOME_VIEWS.includes(view);

// view → hubId (untuk render tab bar & highlight sidebar)
const HUB_VIEW_INDEX = (() => {
  const idx = {};
  for (const [hubId, tabs] of Object.entries(HUB_TABS)) {
    tabs.forEach((t) => { idx[t.view] = hubId; });
  }
  return idx;
})();

export function hubForView(view, role) {
  const hubId = HUB_VIEW_INDEX[view];
  if (!hubId) return null;
  const tabs = hubTabsForRole(hubId, role);
  if (!tabs.length || !tabs.some((t) => t.view === view)) return null;
  return { hubId, tabs };
}

// Untuk item hub: view default = tab pertama yang boleh diakses role tsb.
function withHubView(item, role) {
  if (!item.hub) return item;
  const tabs = hubTabsForRole(item.hub, role);
  return { ...item, view: tabs.length ? tabs[0].view : (item.view || item.id) };
}

// ─── BUILD GROUPED NAVIGATION — filter per role; comingSoon → grup "Segera Hadir" ──
export function buildNavGroups(role, opts = {}) {
  const showComingSoon = opts.showComingSoon !== false;
  // FASE G-0 — `ui.coming_soon_collapsed` DULU setting mati (0 consumer). Sekarang
  // benar-benar menentukan apakah grup "Segera Hadir" tampil terlipat saat aplikasi dibuka.
  const comingSoonCollapsed = opts.comingSoonCollapsed !== false;
  const result = [];
  const comingSoonItems = [];
  for (const entry of NAV_STRUCTURE) {
    if (!roleCanSee(entry.roles, role, entry.groupId || entry.id)) continue;
    if (entry.type === "standalone") {
      if (entry.comingSoon) comingSoonItems.push(entry);
      else result.push(withHubView(entry, role));
    } else if (entry.type === "group") {
      const roleItems = entry.items.filter(item => roleCanSee(item.roles, role, item.id));
      const liveItems = roleItems.filter(item => !item.comingSoon).map(item => withHubView(item, role));
      const soonItems = roleItems.filter(item => item.comingSoon);
      if (liveItems.length > 0) result.push({ ...entry, items: liveItems });
      soonItems.forEach(item => comingSoonItems.push(item));
    }
  }
  if (showComingSoon && comingSoonItems.length > 0) {
    result.push({
      type: "group",
      groupId: "segera-hadir",
      label: "Segera Hadir",
      icon: Clock,
      roles: [role],
      comingSoonGroup: true,
      defaultCollapsed: comingSoonCollapsed,
      items: comingSoonItems,
    });
  }
  return result;
}

// Backward compat: flat array untuk komponen lama jika perlu
export function buildNavigation(role) {
  const groups = buildNavGroups(role);
  const flat = [];
  for (const entry of groups) {
    if (entry.type === "standalone") flat.push(entry);
    else entry.items.forEach(item => flat.push(item));
  }
  return flat;
}

// ─── COMMAND PALETTE ENTRIES (Ctrl+K) — semua tujuan navigasi role ini ─────────
export function buildPaletteEntries(role) {
  const entries = [];
  const seen = new Set();
  const push = (e) => {
    const key = `${e.view}::${e.tab || ""}`;
    if (seen.has(key)) return;
    seen.add(key);
    entries.push(e);
  };
  for (const entry of NAV_STRUCTURE) {
    if (!roleCanSee(entry.roles, role, entry.groupId || entry.id)) continue;
    const walk = (item, groupLabel) => {
      if (item.comingSoon) return;
      if (item.hub) {
        hubTabsForRole(item.hub, role).forEach((t) => push({
          navId: item.id, view: t.view, tab: t.tab,
          label: `${item.label} \u203a ${t.label}`, group: groupLabel, icon: item.icon,
        }));
      } else {
        push({ navId: item.id, view: item.view || item.id, tab: item.tab,
               label: item.label, group: groupLabel, icon: item.icon });
      }
    };
    if (entry.type === "standalone") walk(entry, "Umum");
    else entry.items.filter(i => roleCanSee(i.roles, role, i.id)).forEach(i => walk(i, entry.label));
  }
  return entries;
}

export function defaultViewForRole(role, registry = ROLE_HOME_REGISTRY) {
  return (registry[role] || registry.sales).view;
}
export function defaultNavIdForRole(role, registry = ROLE_HOME_REGISTRY) {
  return (registry[role] || registry.sales).navId;
}

// ─── VIEW → NAV ID INDEX (highlight sidebar = turunan dari activeView) ─────────
const VIEW_NAV_INDEX = (() => {
  const idx = {};
  const reg = (view, navId) => { (idx[view] = idx[view] || []).push(navId); };
  for (const entry of NAV_STRUCTURE) {
    const walk = (item) => {
      if (item.hub) {
        (HUB_TABS[item.hub] || []).forEach((t) => reg(t.view, item.id));
      } else {
        reg(item.view || item.id, item.id);
      }
    };
    if (entry.type === "standalone") walk(entry);
    else (entry.items || []).forEach(walk);
  }
  return idx;
})();

export function resolveActiveNavId(activeView, currentNavId, role) {
  const candidates = VIEW_NAV_INDEX[activeView];
  if (currentNavId && candidates && candidates.includes(currentNavId)) return currentNavId;
  if (candidates && candidates.length) return candidates[0];
  const home = ROLE_HOME_REGISTRY[role];
  if (home && home.view === activeView) return home.navId;
  return currentNavId || "home";
}

// ─── DEEP-LINK `?view=<viewId>` (FASE E-4) ────────────────────────────────────
// Menerjemahkan satu `viewId` dari alamat menjadi tujuan navigasi lengkap
// ({navId, view, tab}) SESUAI PERAN. Dipakai `hooks/useViewDeepLink.js`.
// Sengaja bersandar pada `buildPaletteEntries` (sumber yang sama dengan Ctrl+K)
// supaya daftar tujuan yang sah tidak pernah bercabang dua: layar "segera hadir"
// dan layar di luar menu peran otomatis TIDAK bisa dituju lewat alamat.
export function resolveDeepLinkTarget(view, role) {
  if (!view || !role) return null;
  const entries = buildPaletteEntries(role);
  const entry = entries.find((e) => e.view === view);
  if (entry) return { navId: entry.navId, view: entry.view, tab: entry.tab };
  // Alamat boleh juga menyebut ID MENU atau HUB (mis. `?view=ledger`) — diarahkan
  // ke tab pertama yang boleh dilihat peran ini. Tanpa ini pengguna yang menyalin
  // "ledger" dari peta navigasi mendarat di halaman depan tanpa penjelasan.
  const byNav = entries.find((e) => e.navId === view);
  if (byNav) return { navId: byNav.navId, view: byNav.view, tab: byNav.tab };
  const home = ROLE_HOME_REGISTRY[role];
  if (home && home.view === view) return { navId: home.navId, view: home.view };
  return null;
}
