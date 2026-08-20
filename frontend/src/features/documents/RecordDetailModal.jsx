// RecordDetailModal — pop-up detail record generik (reusable) untuk halaman 360°.
// Menampilkan: header (judul + kode + status), bar aksi dokumen (Pratinjau/Unduh/WA/E-Sign),
// grid meta (fakta kunci), tabel baris item, total, dan catatan.
// Presentational murni — parent membangun konfigurasi dari data yang sudah dimuat.
import { X } from "lucide-react";
import DocumentActionsBar from "./DocumentActionsBar";

const toneClass = {
  success: "pill-success", danger: "pill-danger", warning: "pill-warning",
  info: "status-receiving", muted: "pill-muted",
};

export default function RecordDetailModal({
  open, onClose, icon, title, code, statusText, statusTone = "muted",
  meta = [], items = [], itemColumns = [], totals = [], note,
  docType, sourceId, entityId, number, label, esignable, currentUser,
  customActions, onChanged, testId = "record-detail-modal",
}) {
  if (!open) return null;
  return (
    <div className="modal-overlay" data-testid={testId} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card wide" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 760, width: "94vw" }}>
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2.5 min-w-0">
            {icon && <div className="w-9 h-9 rounded-lg bg-[#EFF4FF] flex items-center justify-center shrink-0">{icon}</div>}
            <div className="min-w-0">
              <p className="modal-title truncate" data-testid="record-detail-title">{title}</p>
              <p className="text-[11.5px] text-[#6B6B73] flex items-center gap-2 flex-wrap">
                {code && <span className="font-bold text-[#0058CC]">{code}</span>}
                {statusText && <span className={`status-pill ${toneClass[statusTone] || "pill-muted"}`} data-testid="record-detail-status">{statusText}</span>}
              </p>
            </div>
          </div>
          <button className="icon-button" onClick={onClose} data-testid="record-detail-close"><X size={16} /></button>
        </div>

        {/* Document actions */}
        {docType && sourceId && (
          <div className="mb-3 rounded-lg border border-[#EEF0F3] bg-[#FAFBFC] px-3 py-2">
            <p className="text-[10px] font-bold uppercase text-[#9A9BA3] mb-1.5">Dokumen</p>
            <DocumentActionsBar docType={docType} sourceId={sourceId} entityId={entityId}
              number={number || code} label={label} esignable={esignable} currentUser={currentUser}
              autoCheckSignature onChanged={onChanged} />
          </div>
        )}
        {!docType && customActions && (
          <div className="mb-3 rounded-lg border border-[#EEF0F3] bg-[#FAFBFC] px-3 py-2" data-testid="record-detail-custom-actions">
            <p className="text-[10px] font-bold uppercase text-[#9A9BA3] mb-1.5">Dokumen</p>
            <div className="flex flex-wrap items-center gap-1.5">{customActions}</div>
          </div>
        )}

        {/* Meta grid */}
        {meta.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3" data-testid="record-detail-meta">
            {meta.map((m, i) => (
              <div key={i} className="rounded-lg border border-[#EFF0F2] bg-white p-2">
                <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{m.label}</p>
                <p className={`text-[12.5px] font-semibold leading-tight ${m.tone || ""}`}>{m.value ?? "—"}</p>
              </div>
            ))}
          </div>
        )}

        {/* Items table */}
        {itemColumns.length > 0 && (
          <div className="section-card">
            <div className="section-head"><h3 className="text-[12px] font-bold">Rincian Item</h3></div>
            <div className="overflow-x-auto">
              {items.length === 0 ? (
                <div className="py-6 text-center text-[11.5px] text-[#9A9BA3]" data-testid="record-detail-items-empty">Tidak ada baris item pada dokumen ini.</div>
              ) : (
                <table className="w-full text-[11.5px]" data-testid="record-detail-items">
                  <thead>
                    <tr className="bg-[#FAFBFC] text-[10px] uppercase text-[#6B6B73]">
                      {itemColumns.map((c, i) => (
                        <th key={i} className={`px-3 py-1.5 font-bold ${c.align === "right" ? "text-right" : "text-left"}`}>{c.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#EFF0F2]">
                    {items.map((row, ri) => (
                      <tr key={ri} className="hover:bg-[#FAFBFC]">
                        {itemColumns.map((c, ci) => (
                          <td key={ci} className={`px-3 py-2 ${c.align === "right" ? "text-right tabular-nums" : ""}`}>
                            {c.render ? c.render(row) : (row[c.key] ?? "—")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {/* Totals */}
        {totals.length > 0 && (
          <div className="mt-3 flex flex-col items-end gap-1" data-testid="record-detail-totals">
            {totals.map((t, i) => (
              <div key={i} className={`flex w-full max-w-[280px] items-center justify-between text-[12px] ${t.bold ? "font-bold" : ""}`}>
                <span className="text-[#6B6B73]">{t.label}</span>
                <span className={`tabular-nums ${t.tone || ""}`}>{t.value}</span>
              </div>
            ))}
          </div>
        )}

        {note && <p className="mt-3 rounded-lg bg-[#FAFBFC] border border-[#EFF0F2] px-3 py-2 text-[11.5px] text-[#4A4B53]">{note}</p>}
      </div>
    </div>
  );
}
