// RelatedDocsPanel — grup dokumen turunan untuk sebuah record (SO/PO/PR/Faktur).
// Menampilkan beberapa DocumentActionsBar (Pratinjau · Unduh · E-Sign · WA) berlabel,
// sehingga user bisa mencetak dokumen operasional langsung dari detail-view.
import DocumentActionsBar from "./DocumentActionsBar";
import { FileStack } from "lucide-react";

export default function RelatedDocsPanel({
  title = "Dokumen Terkait",
  docs = [],
  sourceId,
  entityId,
  number,
  currentUser,
  onChanged,
}) {
  const list = (docs || []).filter(Boolean);
  if (!sourceId || list.length === 0) return null;
  return (
    <div
      data-testid="related-docs-panel"
      className="rounded-lg border border-[#EDEEF1] bg-[#FAFBFC] p-2.5"
    >
      <p className="mb-2 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
        <FileStack size={12} className="text-[#0058CC]" /> {title}
      </p>
      <div className="space-y-2">
        {list.map((d) => (
          <div
            key={d.docType}
            data-testid={`related-doc-${d.docType}`}
            className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-[#EFF0F2] bg-white px-2 py-1.5"
          >
            <span className="min-w-[130px] text-[11px] font-semibold text-[#3C3C43]">
              {d.label}
            </span>
            <DocumentActionsBar
              docType={d.docType}
              sourceId={sourceId}
              entityId={entityId}
              number={number}
              label={d.label}
              currentUser={currentUser}
              onChanged={onChanged}
              compact
              autoCheckSignature={false}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
