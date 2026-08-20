import { Lightbulb } from "lucide-react";
import { roleLabel as registryRoleLabel } from "../config/roles";
import { getToursForRole } from "../data/tourDefinitions";

/**
 * Floating Help & Tours button + role-aware tour list panel.
 * Self-contained — parent only needs to provide handler when a tour is selected.
 */
export default function TourMenu({
  userRole,
  showMenu,
  onToggleMenu,
  onSelectTour,
}) {
  const availableTours = getToursForRole(userRole);
  // FASE E-8 — lencana peran memakai REGISTRY. Pembesaran huruf pertama membuat
  // `sales_admin` tampil sebagai "Sales_admin" di layar.
  const roleLabel = userRole ? registryRoleLabel(userRole) : "Tamu";

  return (
    <div className="fixed bottom-6 right-6 z-50">
      {showMenu && (
        <div
          className="absolute bottom-16 right-0 w-72 rounded-xl border border-[#EFF0F2] bg-white shadow-2xl mb-2"
          data-testid="tour-menu-panel"
        >
          <div className="border-b border-[#EFF0F2] p-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-[13px] font-bold">Smart Guidelines</h3>
              <span
                className="rounded-full bg-[#EFF4FF] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#007AFF]"
                data-testid="tour-menu-role-badge"
              >
                {roleLabel}
              </span>
            </div>
            <p className="text-[10.5px] text-[#6B6B73] mt-0.5">
              Tutorial relevan untuk peran Anda · {availableTours.length} panduan
            </p>
          </div>
          <div className="p-2 max-h-96 overflow-y-auto">
            {availableTours.length === 0 ? (
              <div
                className="px-3 py-6 text-center"
                data-testid="tour-menu-empty-state"
              >
                <p className="text-[12px] font-semibold text-[#1C1C1E]">
                  Belum ada tutorial
                </p>
                <p className="text-[10.5px] text-[#6B6B73] mt-1">
                  Tidak ada panduan yang tersedia untuk peran <b>{roleLabel}</b> saat ini.
                </p>
              </div>
            ) : (
              availableTours.map((tour) => (
                <button
                  key={tour.key}
                  onClick={() => onSelectTour(tour)}
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-[#EFF4FF] transition-colors mb-1"
                  data-testid={`tour-menu-item-${tour.id}`}
                >
                  <p className="text-[12px] font-semibold text-[#1C1C1E]">{tour.name}</p>
                  <p className="text-[10px] text-[#6B6B73] mt-0.5">{tour.description}</p>
                </button>
              ))
            )}
          </div>
        </div>
      )}
      <button
        onClick={onToggleMenu}
        className="flex items-center gap-2 rounded-full bg-[#007AFF] px-4 py-3 text-white shadow-lg hover:bg-[#0051D5] transition-all"
        data-testid="help-tours-button"
      >
        <Lightbulb size={20} />
        <span className="text-[13px] font-bold">Bantuan & Panduan</span>
      </button>
    </div>
  );
}
