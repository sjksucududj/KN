/**
 * SampleRoundList (FASE F · PS-18) — timeline round `rnd 1 → n` per supplier.
 * Setiap round menampilkan tenggat, bukti terunggah, hasil ukur, hasil penilaian & skor.
 */
import { CheckCircle2, FileImage, Paperclip, Plus, Send, Upload } from "lucide-react";
import { roundProofUrl } from "./rndApi";
import { ROUND_RESULT_META } from "./rndMeta";

export default function SampleRoundList({ sample, canSubmit, canAssess, onUpload, onSubmit,
  onAssess, onOpenRound, busy, loading = false }) {
  const bySupplier = {};
  (sample.rounds || []).forEach((r) => {
    bySupplier[r.supplier_id] = bySupplier[r.supplier_id] || [];
    bySupplier[r.supplier_id].push(r);
  });
  const decided = sample.status === "decided" || sample.status === "cancelled";

  if (loading) {
    return (
      <div className="space-y-2.5" data-testid="sample-rounds-loading">
        {[0, 1].map((i) => (
          <div key={i} className="rounded-lg border border-[#EFF0F2] p-3">
            <div className="h-3 w-40 animate-pulse rounded bg-[#EFF0F2]" />
            <div className="mt-2 h-2.5 w-24 animate-pulse rounded bg-[#F4F5F7]" />
            <div className="mt-3 h-2.5 w-full animate-pulse rounded bg-[#F4F5F7]" />
          </div>
        ))}
        <p className="text-center text-[11.5px] text-[#6B6B73]">Memuat riwayat round…</p>
      </div>
    );
  }

  return (
    <div className="space-y-2.5" data-testid="sample-rounds">
      {(sample.participants || []).map((p) => {
        const rounds = (bySupplier[p.supplier_id] || [])
          .slice().sort((a, b) => (a.round_no || 0) - (b.round_no || 0));
        const last = rounds[rounds.length - 1];
        const canOpenNext = !decided && last && last.result === "revisi";
        return (
          <div key={p.supplier_id} className="rounded-lg border border-[#EFF0F2]"
            data-testid={`sample-participant-${p.supplier_id}`}>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#EFF0F2] bg-[#FAFBFC] px-3 py-2">
              <div>
                <p className="text-[12px] font-bold">{p.supplier_name}</p>
                <p className="text-[10.5px] text-[#6B6B73]">
                  {rounds.length} round
                  {p.best_score != null ? ` · skor terbaik ${p.best_score}` : ""}
                  {p.overdue ? " · pernah terlambat" : ""}
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="status-pill"
                  style={{ background: p.status === "acc" ? "rgba(52,199,89,0.12)"
                    : p.status === "rejected" ? "rgba(255,59,48,0.10)" : "rgba(142,142,147,0.12)",
                  color: p.status === "acc" ? "#1A7A3A"
                    : p.status === "rejected" ? "#C62828" : "#6B6B73" }}
                  data-testid={`participant-status-${p.supplier_id}`}>
                  {p.status === "acc" ? "ACC" : p.status === "rejected" ? "Ditolak"
                    : p.status === "responded" ? "Sudah kirim hasil" : "Diundang"}
                </span>
                {canOpenNext && canSubmit && (
                  <button className="secondary-button !px-2 !py-1 text-[10.5px]" disabled={busy}
                    data-testid={`open-round-${p.supplier_id}`}
                    onClick={() => onOpenRound(p)}>
                    <Plus size={12} /> Buka round berikutnya
                  </button>
                )}
              </div>
            </div>

            <div className="divide-y divide-[#F4F5F7]">
              {rounds.length === 0 && (
                <p className="px-3 py-3 text-[11px] text-[#6B6B73]"
                  data-testid={`participant-no-rounds-${p.supplier_id}`}>
                  Belum ada round untuk mitra ini — permintaan sudah dikirim, menunggu hasil pertama.
                </p>
              )}
              {rounds.map((r) => {
                const rm = ROUND_RESULT_META[r.result || ""] || ROUND_RESULT_META[""];
                return (
                  <div key={r.id} className="px-3 py-2.5" data-testid={`round-row-${r.id}`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-[11.5px] font-bold">
                        rnd {r.round_no}
                        <span className="ml-2 font-normal text-[#6B6B73]">
                          tenggat {r.due_date || "—"}
                          {r.overdue && <span className="ml-1 font-bold text-[#C0392B]">· TERLAMBAT</span>}
                        </span>
                      </p>
                      <span className="text-[11px] font-bold" style={{ color: rm.tone }}
                        data-testid={`round-result-${r.id}`}>
                        {rm.label}{r.score != null ? ` · skor ${r.score}` : ""}
                      </span>
                    </div>

                    {r.note && (
                      <p className="mt-1 text-[11px] text-[#3C3C43]">“{r.note}”</p>
                    )}
                    {r.measurements && Object.values(r.measurements).some((v) => v != null) && (
                      <p className="mt-1 text-[10.5px] text-[#6B6B73]" data-testid={`round-meas-${r.id}`}>
                        {r.measurements.delta_e != null && `ΔE ${r.measurements.delta_e}`}
                        {r.measurements.gsm_actual != null && ` · GSM ${r.measurements.gsm_actual}`}
                        {r.measurements.shrinkage_pct != null && ` · susut ${r.measurements.shrinkage_pct}%`}
                        {r.measurements.colorfastness_wash != null && ` · tahan cuci ${r.measurements.colorfastness_wash}`}
                        {r.measurements.colorfastness_rub != null && ` · tahan gosok ${r.measurements.colorfastness_rub}`}
                      </p>
                    )}

                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      {(r.attachments || []).map((a) => (
                        <a key={a.id} href={roundProofUrl(sample.id, r.id, a.id)} target="_blank"
                          rel="noreferrer" data-testid={`round-file-${a.id}`}
                          className="inline-flex items-center gap-1 rounded-md border border-[#E5E5EA] px-2 py-0.5 text-[10.5px] text-[#0058CC] hover:border-[#0058CC]">
                          <FileImage size={11} /> {a.filename}
                        </a>
                      ))}
                      {(r.attachments || []).length === 0 && r.status === "open" && (
                        <span className="inline-flex items-center gap-1 text-[10.5px] text-[#B26A00]">
                          <Paperclip size={11} /> belum ada bukti — wajib diunggah sebelum disetor
                        </span>
                      )}
                    </div>

                    {!decided && (
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        {r.status === "open" && canSubmit && (
                          <>
                            <label className="secondary-button !px-2 !py-1 text-[10.5px] cursor-pointer"
                              data-testid={`round-upload-label-${r.id}`}>
                              <Upload size={12} /> Unggah bukti
                              <input type="file" className="hidden" accept="image/*,.pdf"
                                data-testid={`round-upload-${r.id}`}
                                onChange={(e) => {
                                  const file = e.target.files?.[0];
                                  if (file) onUpload(r, file);
                                  e.target.value = "";
                                }} />
                            </label>
                            <button className="primary-button !px-2 !py-1 text-[10.5px]" disabled={busy}
                              data-testid={`round-submit-${r.id}`} onClick={() => onSubmit(r)}>
                              <Send size={12} /> Setor hasil
                            </button>
                          </>
                        )}
                        {r.status === "submitted" && canAssess && (
                          <button className="primary-button !px-2 !py-1 text-[10.5px]" disabled={busy}
                            data-testid={`round-assess-${r.id}`} onClick={() => onAssess(r)}>
                            <CheckCircle2 size={12} /> Nilai hasil
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
      {(sample.participants || []).length === 0 && (
        <p className="rounded-lg border border-dashed border-[#E5E5EA] px-3 py-6 text-center text-[11.5px] text-[#6B6B73]"
          data-testid="sample-no-participants">
          Belum dikirim ke supplier. Pilih supplier lalu kirim permintaan — boleh lebih dari satu
          supaya hasilnya bisa dibandingkan.
        </p>
      )}
    </div>
  );
}
