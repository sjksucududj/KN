import axios, { API } from "../services/apiClient";
import { Target, CheckSquare, Square, Check } from "lucide-react";

import { roleLabel } from "../config/roles";

/**
 * Onboarding checklist panel.
 * - Shows progress bar + items.
 * - Each item has a "Tandai Selesai" button calling /onboarding/{id}/complete.
 * - Dismiss button hides the panel for the current session.
 */
export default function OnboardingPanel({ onboarding, onDismiss, onUpdate }) {
  if (!onboarding || onboarding.progress_pct >= 100) return null;
  // FASE E-8 — nama peran dari REGISTRY (`config/roles.js`). Peta lokal lama hanya
  // memuat 4 peran sehingga panduan Admin Sales/Finance menampilkan id teknis.
  const peran = roleLabel(onboarding.role);

  const completeItem = async (itemId) => {
    await axios.post(`${API}/onboarding/${itemId}/complete`);
    const res = await axios.get(`${API}/onboarding`);
    onUpdate(res.data);
  };

  return (
    <div data-testid="onboarding-panel" className="mt-4 rounded-xl border border-[#007AFF]/20 bg-blue-50 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Target size={20} className="text-[#007AFF]" />
          <div>
            <h3 className="text-[13px] font-bold text-[#1C1C1E]">Panduan Awal — {peran}</h3>
            <p className="text-[11px] text-[#6B6B73]">{onboarding.completed_count}/{onboarding.total} langkah selesai</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-2 w-24 rounded-full bg-[#EFF0F2] overflow-hidden">
            <div className="h-full rounded-full bg-[#007AFF] transition-all" style={{ width: `${onboarding.progress_pct}%` }} />
          </div>
          <span className="text-[11px] font-bold text-[#007AFF]">{onboarding.progress_pct}%</span>
          <button data-testid="dismiss-onboarding-button" className="secondary-button ml-2 !text-[11px]" onClick={onDismiss}>Tutup</button>
        </div>
      </div>
      <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
        {(onboarding.items || []).map(item => (
          <div key={item.id} data-testid={`onboarding-item-${item.id}`}
            className={`flex items-start gap-2 rounded-lg px-3 py-2 border transition-all ${
              item.completed ? "border-green-200 bg-green-50" : "border-[#EFF0F2] bg-white"
            }`}>
            <span className="mt-0.5 flex-shrink-0">{item.completed ? <CheckSquare size={15} className="text-green-600" /> : <Square size={15} className="text-[#C7C7CC]" />}</span>
            <div className="min-w-0">
              <p className={`text-[12px] font-semibold ${item.completed ? "line-through text-[#8E8E93]" : ""}`}>{item.label}</p>
              <p className="text-[10.5px] text-[#8E8E93]">{item.description}</p>
            </div>
            {!item.completed && (
              <button data-testid={`complete-onboarding-${item.id}`}
                className="flex-shrink-0 secondary-button !text-[10px] !py-0.5 !px-1.5 inline-flex items-center gap-1"
                onClick={() => completeItem(item.id)}><Check size={11} /> Tandai Selesai</button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
