import { useState } from "react";
import { History, ChevronDown, ChevronRight, ArrowRight, PlusCircle, MinusCircle, Pencil } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";

/**
 * POVersionHistory — Phase 7.2: riwayat amandemen PO (snapshot + diff per versi).
 * Menampilkan `po.amendments[]` (terbaru di atas). Tiap entri bisa di-expand untuk
 * melihat detail perubahan (from → to) + ringkasan snapshot sebelum revisi.
 *
 * Props: amendments (array), currentVersion (number)
 */
function fmtDateTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("id-ID", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return String(iso); }
}

const MONEY_FIELDS = new Set(["total", "grand_total"]);

function fmtVal(field, v) {
  if (v === null || v === undefined || v === "-") return "-";
  if (MONEY_FIELDS.has(field) && !isNaN(Number(v))) return formatCurrency(Number(v));
  return String(v);
}

function ChangeIcon({ field }) {
  if (field === "item_add") return <PlusCircle size={12} className="text-green-600" />;
  if (field === "item_remove") return <MinusCircle size={12} className="text-red-500" />;
  return <Pencil size={11} className="text-[#6B219A]" />;
}

export default function POVersionHistory({ amendments = [], currentVersion = 1 }) {
  const list = Array.isArray(amendments) ? amendments : [];
  const [openVer, setOpenVer] = useState(list.length ? Math.max(...list.map((a) => a.version || 0)) : null);
  if (list.length === 0) return null;
  const sorted = [...list].sort((a, b) => (b.version || 0) - (a.version || 0));

  return (
    <div data-testid="po-version-history" className="rounded-md border border-[#EFF0F2] overflow-hidden">
      <div className="px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2] flex items-center gap-1.5">
        <History size={12} /> Riwayat Amandemen ({list.length})
        <span className="ml-auto rounded bg-[#F3E8FF] px-1.5 py-0.5 text-[10px] font-semibold text-[#6B219A] normal-case">v{currentVersion} aktif</span>
      </div>
      <div>
        {sorted.map((amd) => {
          const isOpen = openVer === amd.version;
          const changes = Array.isArray(amd.changes) ? amd.changes : [];
          const snap = amd.snapshot_before || {};
          return (
            <div key={amd.version} data-testid={`po-amendment-${amd.version}`} className="border-b border-[#EFF0F2] last:border-0">
              <button data-testid={`po-amendment-toggle-${amd.version}`}
                onClick={() => setOpenVer(isOpen ? null : amd.version)}
                className="w-full flex items-start gap-2 px-2.5 py-2 text-left hover:bg-[#FAFBFC] transition-colors">
                <span className="mt-0.5 text-[#6B6B73]">{isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
                <span className="flex h-5 min-w-[34px] items-center justify-center rounded bg-[#F3E8FF] px-1 text-[10.5px] font-bold text-[#6B219A]">v{amd.version}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-[11.5px] font-semibold text-[#1C1C1E] truncate">{amd.reason || "(tanpa alasan)"}</p>
                  <p className="text-[10.5px] text-[#6B6B73]">
                    oleh <span className="font-medium text-[#3C3C43]">{amd.amended_by || "—"}</span> · {fmtDateTime(amd.amended_at)} · {changes.length} perubahan
                  </p>
                </div>
              </button>
              {isOpen && (
                <div data-testid={`po-amendment-detail-${amd.version}`} className="px-3 pb-2.5 pt-0.5 space-y-2">
                  {changes.length === 0 ? (
                    <p className="text-[10.5px] text-[#6B6B73] italic">Tidak ada perubahan tercatat.</p>
                  ) : (
                    <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
                      {changes.map((c, j) => (
                        <div key={j} data-testid={`po-amendment-${amd.version}-change-${j}`}
                          className="flex items-center gap-2 px-2 py-1 border-b border-[#F2F3F5] last:border-0 text-[11px]">
                          <ChangeIcon field={c.field} />
                          <span className="min-w-0 flex-1 truncate text-[#3C3C43]">{c.label}</span>
                          <span className="tabular-nums text-[#9A9BA3] line-through">{fmtVal(c.field, c.from)}</span>
                          <ArrowRight size={11} className="text-[#9A9BA3] shrink-0" />
                          <span className="tabular-nums font-semibold text-[#1C1C1E]">{fmtVal(c.field, c.to)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {/* Snapshot ringkas sebelum revisi */}
                  <div className="rounded-md bg-[#FAFBFC] border border-[#EFF0F2] px-2.5 py-1.5 text-[10.5px] text-[#6B6B73]">
                    <p className="font-semibold text-[#3C3C43] mb-0.5">Snapshot sebelum revisi (v{snap.version ?? "—"})</p>
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                      <span>Supplier: <b className="text-[#3C3C43]">{snap.supplier_name || "—"}</b></span>
                      <span>Gudang: <b className="text-[#3C3C43]">{snap.warehouse_name || "—"}</b></span>
                      <span>Subtotal: <b className="tabular-nums text-[#3C3C43]">{formatCurrency(snap.total_amount || 0)}</b></span>
                      <span>Grand Total: <b className="tabular-nums text-[#3C3C43]">{formatCurrency(snap.grand_total || 0)}</b></span>
                      <span>Item: <b className="text-[#3C3C43]">{(snap.items || []).length}</b></span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
