// HRD H4 — util Payroll bersama.
import axios, { API } from "../../services/apiClient";
import { formatCurrency } from "../../utils/formatters";

export const rp = (v) => formatCurrency(v || 0);
export const pct = (v) => `${(Number(v || 0) * 100).toFixed(2)}%`;

export const RUN_STATUS = {
  draft: { cls: "pill-muted", label: "Draf" },
  // UTANG ALUR F-6.7 — tahap "diajukan" ada di antara draf & disetujui supaya draf yang
  // masih dikerjakan HR tidak bercampur dengan yang menunggu keputusan penyetuju.
  pending_approval: { cls: "pill-warning", label: "Menunggu pengesahan" },
  approved: { cls: "pill-info", label: "Disetujui" },
  posted: { cls: "pill-warning", label: "Posted GL" },
  paid: { cls: "pill-success", label: "Dibayar" },
  void: { cls: "pill-danger", label: "Batal" },
};

const WIB_OFFSET_MS = 7 * 3600 * 1000;
export const curMonth = () => new Date(Date.now() + WIB_OFFSET_MS).toISOString().slice(0, 7);
export function recentMonths(n = 15) {
  const out = [];
  const d = new Date(Date.now() + WIB_OFFSET_MS);
  d.setDate(1);
  for (let i = 0; i < n; i++) { out.push(d.toISOString().slice(0, 7)); d.setMonth(d.getMonth() - 1); }
  return out;
}

// Unduh / buka PDF slip via blob (axios membawa header Authorization).
export async function openPayslipPdf(slipId) {
  const res = await axios.get(`${API}/hr/payslips/${slipId}/pdf`, { responseType: "blob" });
  const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
