/** rfidShared — komponen & util bersama untuk view RFID (Fase 5). */
import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";

export const nf = new Intl.NumberFormat("id-ID");
export const q = (v) => nf.format(Math.round((v || 0) * 100) / 100);

export function fmtTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

// Ambil daftar gudang + state pilihan (dipakai semua view RFID).
export function useWarehouses() {
  const [warehouses, setWarehouses] = useState([]);
  const [whId, setWhId] = useState("");
  useEffect(() => {
    axios.get(`${API}/warehouses`).then((r) => setWarehouses(r.data || [])).catch(() => {});
  }, []);
  const whOpts = [{ value: "", label: "Semua Gudang" }, ...warehouses.map((w) => ({ value: w.id, label: w.name }))];
  return { warehouses, whId, setWhId, whOpts };
}

const COLORS = {
  green: "#34C759", red: "#C0341D", info: "#0058CC", blue: "#0058CC",
  orange: "#FF9500", purple: "#5856D6", gray: "#8E8E93",
};

export function Pill({ color = "gray", children, testId }) {
  const c = COLORS[color] || COLORS.gray;
  return (
    <span data-testid={testId} className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold"
      style={{ background: `${c}1A`, color: c }}>{children}</span>
  );
}

// Peta result read → warna pill.
export function resultColor(r) {
  return r === "green" ? "green" : r === "red" ? "red" : "info";
}

export function Stat({ icon: Icon, label, value, sub, color = "#0058CC", loading, testId }) {
  return (
    <div data-testid={testId} className="rounded-xl border border-[#EFF0F2] bg-white p-4 flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <div className="rounded-lg p-1.5" style={{ background: `${color}18` }}><Icon size={15} style={{ color }} /></div>
        <span className="text-[12px] font-semibold text-[#6B6B73]">{label}</span>
      </div>
      {loading ? <div className="h-6 bg-[#F5F5F7] rounded animate-pulse" />
        : <p className="text-[19px] font-bold text-[#1C1C1E] tabular-nums leading-tight">{value}</p>}
      {sub && <p className="text-[11px] text-[#6B6B73]">{sub}</p>}
    </div>
  );
}

export function TabBtn({ id, tab, setTab, label, testId }) {
  const active = tab === id;
  return (
    <button data-testid={testId} onClick={() => setTab(id)}
      className={`px-4 py-2 text-[13px] font-semibold border-b-2 -mb-px ${active ? "border-[#0058CC] text-[#0058CC]" : "border-transparent text-[#6B6B73] hover:text-[#1C1C1E]"}`}>
      {label}
    </button>
  );
}

export function EmptyBox({ icon: Icon, text }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <div className="rounded-full bg-[#F5F5F7] p-3"><Icon size={22} className="text-[#8E8E93]" /></div>
      <p className="text-[12px] text-[#6B6B73] max-w-xs">{text}</p>
    </div>
  );
}

export function SectionCard({ title, right, children }) {
  return (
    <div className="rounded-xl border border-[#EFF0F2] bg-white p-4">
      {(title || right) && (
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-[13px] font-bold text-[#1C1C1E]">{title}</h3>
          {right}
        </div>
      )}
      {children}
    </div>
  );
}

// Header standar view RFID (kicker + judul + kontrol kanan).
export function RfidHeader({ icon: Icon, title, subtitle, children }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="text-[12px] font-semibold text-[#0058CC] tracking-wide">RFID & TRACEABILITY</p>
        <h1 className="text-[20px] font-bold text-[#1C1C1E] flex items-center gap-2">
          <Icon size={20} className="text-[#0058CC]" /> {title}
        </h1>
        {subtitle && <p className="text-[12px] text-[#6B6B73] mt-0.5">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}
