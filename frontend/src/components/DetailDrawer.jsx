import { XCircle } from "lucide-react";

export default function DetailDrawer({ detail, onClose, onNavigate }) {
  if (!detail) return null;
  return (
    <aside data-testid="interactive-detail-drawer" className="fixed right-4 top-16 z-50 w-[min(380px,calc(100vw-32px))] rounded-[14px] border border-[#E5E5EA] bg-white/95 p-4 shadow-[0_16px_40px_rgba(20,28,45,0.18)] backdrop-blur-xl no-print" role="dialog" aria-label="Detail insight">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p data-testid="detail-drawer-kicker" className="text-[10.5px] font-bold uppercase tracking-wide text-[#0058CC]">Detail Insight</p>
          <h3 data-testid="detail-drawer-title" className="mt-0.5 text-[15px] font-bold tracking-tight">{detail.title}</h3>
        </div>
        <button data-testid="detail-drawer-close-button" className="icon-button" onClick={onClose} aria-label="Tutup"><XCircle size={14} /></button>
      </div>
      <p data-testid="detail-drawer-body" className="mt-2 text-[12px] text-[#3C3C43]">{detail.body}</p>
      <div className="mt-3 grid gap-1.5">
        {(detail.facts || []).map((fact, index) => <div data-testid={`detail-drawer-fact-${index}`} key={fact.label} className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2"><p className="text-[10.5px] font-bold uppercase tracking-wide text-[#6B6B73]">{fact.label}</p><p className="text-[13px] font-semibold">{fact.value}</p></div>)}
      </div>
      {detail.target && <button data-testid="detail-drawer-navigate-button" className="primary-button mt-3 w-full" onClick={() => onNavigate(detail.target)}>{detail.cta || "Buka halaman terkait"}</button>}
    </aside>
  );
}
