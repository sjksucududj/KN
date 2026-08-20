/**
 * SampleSendModal (FASE F · PS-18) — dua peran, satu permukaan:
 *  - mode "send"  : kirim permintaan sample ke **beberapa supplier sekaligus**
 *                   supaya hasilnya bisa dibandingkan sebelum harga dikunci.
 *  - mode "round" : buka **round berikutnya** untuk satu supplier setelah hasil
 *                   `revisi`. Melewati batas `rnd.max_rounds` wajib ALASAN tertulis
 *                   (dan hanya boleh manager/admin) — server yang menegakkan.
 */
import { useEffect, useMemo, useState } from "react";
import { Plus, Search, Send, X } from "lucide-react";
import { overlayDismiss } from "@/utils/overlayDismiss";
import { listSuppliers } from "./rndApi";
import { errMsg } from "./rndMeta";

export default function SampleSendModal({ mode = "send", sample, participant, policy,
  onClose, onConfirm, busy }) {
  const [suppliers, setSuppliers] = useState([]);
  const [picked, setPicked] = useState([]);
  const [q, setQ] = useState("");
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  const isSend = mode === "send";

  useEffect(() => {
    if (!isSend) return;
    listSuppliers({ limit: 500 })
      .then((r) => setSuppliers(Array.isArray(r) ? r : r?.items || []))
      .catch((e) => setErr(errMsg(e, "Gagal memuat daftar supplier.")));
  }, [isSend]);

  const invited = useMemo(
    () => new Set((sample?.participants || []).map((p) => p.supplier_id)), [sample]);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    return suppliers.filter((s) => !term
      || `${s.name || ""}${s.code || ""}${s.city || ""}`.toLowerCase().includes(term));
  }, [suppliers, q]);

  const toggle = (id) => setPicked((p) =>
    p.includes(id) ? p.filter((x) => x !== id) : [...p, id]);

  const roundsOfPartner = (sample?.rounds || [])
    .filter((r) => r.supplier_id === participant?.supplier_id);
  const nextNo = roundsOfPartner.length + 1;
  const overLimit = nextNo > Number(policy?.max_rounds || 3);

  return (
    <div data-testid="sample-send-modal"
      className="fixed inset-0 z-[174] flex items-center justify-center bg-black/50 p-4"
      {...overlayDismiss(onClose)}>
      <div className="flex max-h-[92vh] w-full max-w-[600px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold">
            {isSend ? <Send size={16} className="text-[#0058CC]" />
              : <Plus size={16} className="text-[#0058CC]" />}
            {isSend ? "Kirim Permintaan ke Supplier"
              : `Buka round ${nextNo} — ${participant?.supplier_name || ""}`}
          </h2>
          <button className="icon-button" onClick={onClose} data-testid="sample-send-close">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-2.5 overflow-y-auto p-4">
          {err && (
            <div className="rounded-lg bg-[#FDEDE7] px-3 py-2 text-[11.5px] text-[#C0392B]"
              data-testid="sample-send-error">{err}</div>
          )}

          {isSend ? (
            <>
              <div className="rounded-lg bg-[#F2F7FF] px-3 py-2 text-[11.5px] text-[#004099]">
                Pilih <b>lebih dari satu supplier</b> bila ingin membandingkan hasil sample.
                Masing-masing otomatis mendapat <b>round 1</b> dengan tenggat yang sama.
              </div>
              <div className="relative">
                <Search size={14}
                  className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
                <input className="field !pl-8" data-testid="sample-send-search" value={q}
                  onChange={(e) => setQ(e.target.value)} placeholder="Cari supplier…" />
              </div>
              <div className="max-h-[260px] divide-y divide-[#F4F5F7] overflow-y-auto rounded-lg border border-[#EFF0F2]"
                data-testid="sample-send-supplier-list">
                {filtered.length === 0 && (
                  <p className="px-3 py-6 text-center text-[11.5px] text-[#6B6B73]">
                    Tidak ada supplier yang cocok.
                  </p>
                )}
                {filtered.map((s) => {
                  const already = invited.has(s.id);
                  const on = picked.includes(s.id);
                  return (
                    <button key={s.id} type="button" disabled={already}
                      data-testid={`sample-send-supplier-${s.id}`}
                      onClick={() => toggle(s.id)}
                      className={`flex w-full items-center justify-between px-3 py-2 text-left ${already
                        ? "cursor-not-allowed bg-[#FAFBFC] opacity-60"
                        : on ? "bg-[#EFF4FF]" : "hover:bg-[#FAFBFC]"}`}>
                      <span className="min-w-0">
                        <span className="block truncate text-[12px] font-semibold">{s.name}</span>
                        <span className="block truncate text-[10.5px] text-[#6B6B73]">
                          {s.code || "—"}{s.city ? ` · ${s.city}` : ""}
                        </span>
                      </span>
                      <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold ${already
                        ? "border-[#E5E5EA] text-[#8E8E93]"
                        : on ? "border-[#0058CC] bg-[#0058CC] text-white"
                          : "border-[#E5E5EA] text-[#6B6B73]"}`}>
                        {already ? "sudah diundang" : on ? "dipilih" : "pilih"}
                      </span>
                    </button>
                  );
                })}
              </div>
              <p className="text-[11px] text-[#6B6B73]" data-testid="sample-send-count">
                {picked.length} supplier dipilih.
              </p>
            </>
          ) : (
            <div className={`rounded-lg px-3 py-2 text-[11.5px] ${overLimit
              ? "bg-[#FFF6E5] text-[#8C4A00]" : "bg-[#F2F7FF] text-[#004099]"}`}
              data-testid="sample-round-limit-note">
              {overLimit
                ? `Round ${nextNo} MELEWATI batas ${policy?.max_rounds || 3} iterasi. `
                  + "Hanya manager/admin yang boleh membukanya, dan alasan tertulis WAJIB "
                  + "(batas bisa diubah di Pusat Pengaturan → R&D & Desain)."
                : `Round ${nextNo} dari batas ${policy?.max_rounds || 3} iterasi. `
                  + "Supplier akan mengerjakan perbaikan sesuai catatan penilaian sebelumnya."}
            </div>
          )}

          <div className="grid gap-2.5 md:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">
                Tenggat round (kosong = pakai target SLA {policy?.round_sla_days || 7} hari)
              </span>
              <input className="field" type="date" data-testid="sample-send-due" value={due}
                onChange={(e) => setDue(e.target.value)} />
            </label>
            <label className="block">
              <span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">
                Catatan untuk supplier
              </span>
              <input className="field" data-testid="sample-send-note" value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="mis. kirim swatch 3 meter" />
            </label>
          </div>

          {!isSend && (
            <label className="block">
              <span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">
                Alasan round tambahan{overLimit ? " (WAJIB)" : " (opsional)"}
              </span>
              <input className="field" data-testid="sample-round-reason" value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="mis. pelanggan minta warna sedikit lebih muda" />
            </label>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" data-testid="sample-send-confirm"
            disabled={busy || (isSend ? picked.length === 0 : (overLimit && !reason.trim()))}
            onClick={() => (isSend
              ? onConfirm({ supplier_ids: picked, due_date: due, note })
              : onConfirm({ supplier_id: participant?.supplier_id, due_date: due, note,
                reason }))}>
            <Send size={13} /> {busy ? "Memproses…"
              : isSend ? `Kirim ke ${picked.length || ""} supplier`.trim() : `Buka round ${nextNo}`}
          </button>
        </div>
      </div>
    </div>
  );
}
