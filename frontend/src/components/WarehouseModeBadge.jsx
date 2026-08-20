/**
 * WarehouseModeBadge (FASE E-4 · E4.1) — lencana “gudang ini milik siapa”.
 *
 * Aturan pemilik #3: ada gudang BERSAMA dan ada gudang KHUSUS badan usaha
 * tertentu. Kalau lencana ini tidak ada, dua gudang tampak sama di layar padahal
 * yang satu haram dipakai — dan pengguna baru tahu setelah ditolak server.
 */
import { Building2, Users } from "lucide-react";

export default function WarehouseModeBadge({ warehouse, testId, showNames = true }) {
  if (!warehouse) return null;
  const dedicated = warehouse.sharing_mode === "dedicated";
  const names = warehouse.entity_names || [];
  const label = dedicated
    ? (showNames && names.length ? `Khusus ${names.join(", ")}` : "Khusus")
    : "Bersama";
  return (
    <span
      data-testid={testId}
      title={warehouse.sharing_label || label}
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9.5px] font-bold ${
        dedicated ? "bg-[#F3E9FA] text-[#6B219A]" : "bg-[#EAF2FF] text-[#0058CC]"
      }`}
    >
      {dedicated ? <Building2 size={10} /> : <Users size={10} />}
      {label}
    </span>
  );
}
