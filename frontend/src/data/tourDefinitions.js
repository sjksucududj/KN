/**
 * Tour Definitions untuk Smart Guidelines (aggregator + helpers)
 *
 * Setiap step bisa punya:
 *   - target:    string testid (`"foo-bar"`) ATAU CSS selector (`"[data-testid^='order-card-']"`)
 *   - title, content, placement: "top"|"bottom"|"left"|"right"|"center"
 *   - before:    testid/selector dari elemen yang HARUS DI-KLIK SEBELUM step ini (auto-navigate)
 *   - optional:  bila true → kalau target tidak ada, auto-skip ke step berikutnya
 *   - waitMs:    override polling timeout (default 2500)
 *
 * roles:        daftar role yang boleh melihat tour ini di menu Help & Tours.
 *
 * Definisi step dipecah per-domain di ./tours/ agar tiap file tetap di bawah
 * batas ukuran (KN_02). File ini hanya meng-compose + menyediakan helper.
 */
import { createSalesOrder, approveOrder, orderDashboard } from "./tours/salesTours";
import { processInbound, processOutbound, inventoryManagement } from "./tours/operationsTours";
import { adminMasterData } from "./tours/adminTours";

export const TOURS = {
  createSalesOrder,     // Tour 1 - Create Sales Order  (admin, sales)
  approveOrder,         // Tour 2 - Approve Sales Order  (admin, manager)
  processInbound,       // Tour 3 - Process Inbound  (admin, warehouse)
  processOutbound,      // Tour 4 - Process Outbound  (admin, warehouse)
  inventoryManagement,  // Tour 5 - Inventory Management  (admin, warehouse, manager)
  adminMasterData,      // Tour 6 - Admin Master Data  (admin)
  orderDashboard,       // Tour 7 - Order Dashboard  (admin, manager, sales)
};

/**
 * Mengembalikan daftar tour yang boleh dilihat oleh role tertentu.
 */
export function getToursForRole(role) {
  if (!role) return [];
  const normalized = String(role).toLowerCase();
  return Object.entries(TOURS)
    .filter(([, tour]) => {
      if (!Array.isArray(tour.roles) || tour.roles.length === 0) return true;
      return tour.roles.includes(normalized);
    })
    .map(([key, tour]) => ({ key, ...tour }));
}

export function isTourCompleted(tourId) {
  return localStorage.getItem(`tour_completed_${tourId}`) === "true";
}

export function isTourSkipped(tourId) {
  return localStorage.getItem(`tour_skipped_${tourId}`) === "true";
}

export function resetTour(tourId) {
  localStorage.removeItem(`tour_completed_${tourId}`);
  localStorage.removeItem(`tour_skipped_${tourId}`);
}
