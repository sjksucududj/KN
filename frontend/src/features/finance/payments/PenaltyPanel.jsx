/**
 * PenaltyPanel — FASE G-2 · daftar & keputusan **nota denda keterlambatan**.
 *
 * Denda lahir sebagai USULAN (draft, tanpa jurnal) supaya masih bisa dinegosiasikan.
 * Panel ini memberi jalan resmi untuk keputusannya: **Terbitkan** · **Bebaskan** ·
 * **Ubah Nominal** · **Catat Pembayaran** — dua yang di tengah WAJIB memilih label
 * alasan, sehingga tidak ada denda yang hilang diam-diam.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, BadgeDollarSign, Ban, Loader2, PencilLine, Receipt, Send } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { openTrace } from "../../documents/trace/traceDeepLink";
import {
  adjustPenalty, errText, fetchMeta, issuePenalty, money, payPenalty, penaltyMeta, waivePenalty,
} from "./paymentApi";

export default function PenaltyPanel({ rows = [], currentUser, entityId = "", onChanged }) {
  const [reasons, setReasons] = useState([]);
  const [dialog, setDialog] = useState(null);   // {kind:'waive'|'adjust'|'pay', row}
  const [reasonCode, setReasonCode] = useState("");
  const [note, setNote] = useState("");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  const canDecide = ["admin", "manager"].includes(currentUser?.role);

  useEffect(() => {
    (async () => {
      try { setReasons((await fetchMeta(entityId)).reasons || []); }
      catch { setReasons([]); }
    })();
  }, [entityId]);

  const act = useCallback(async (kind, row) => {
    setBusy(row.id); setErr("");
    try {
      if (kind === "issue") await issuePenalty(row.id);
      if (kind === "waive") await waivePenalty(row.id, { reason_code: reasonCode, note });
      if (kind === "adjust") await adjustPenalty(row.id, {
        amount: Number(amount || 0), reason_code: reasonCode, note });
      if (kind === "pay") await payPenalty(row.id, { amount: Number(amount || 0), method: "transfer" });
      setDialog(null); setReasonCode(""); setNote(""); setAmount("");
      if (onChanged) onChanged();
    } catch (e) { setErr(errText(e, "Aksi denda gagal.")); }
    finally { setBusy(""); }
  }, [reasonCode, note, amount, onChanged]);

  if (!rows.length) {
    return (
      <div data-testid="penalty-panel-empty"
        className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-3 text-center">
        <BadgeDollarSign size={20} className="mx-auto mb-1 text-[#C4C5CC]" />
        <p className="text-[11.5px] font-semibold text-[#3C3C43]">Belum ada denda keterlambatan.</p>
        <p className="text-[10.5px] text-[#6B6B73]">
          Usulan denda dibuat otomatis saat baris jadwal melewati jatuh tempo + masa tenggang.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="penalty-panel" className="space-y-1.5">
      {err && <div className="notice-bar danger !py-1.5" data-testid="penalty-error">
        <span className="text-[11.5px]">{err}</span></div>}
      {rows.map((p) => {
        const meta = penaltyMeta(p.status);
        return (
          <div key={p.id} data-testid={`penalty-row-${p.id}`}
            className="rounded-md border border-[#EFF0F2] bg-white px-2.5 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <button type="button" data-testid={`penalty-trace-${p.id}`}
                    onClick={() => openTrace({ docType: "penalty", docId: p.id, number: p.number })}
                    className="text-[11.5px] font-bold text-[#0058CC] hover:underline">
                    {p.number}
                  </button>
                  <span className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide"
                    style={{ background: meta.bg, color: meta.fg }}>{meta.label}</span>
                </div>
                <p className="truncate text-[10.5px] text-[#6B6B73]">
                  {p.line_label} · jatuh tempo {(p.due_date || "").slice(0, 10)} · telat {p.days_late} hari
                  {p.reason_label ? ` · ${p.reason_label}` : ""}
                </p>
                {(p.explain || []).length > 0 && (
                  <p className="truncate text-[9.5px] text-[#9A9BA3]" title={(p.explain || []).join(" · ")}>
                    {(p.explain || [])[2] || (p.explain || [])[0]}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[12.5px] font-bold tabular-nums" data-testid={`penalty-amount-${p.id}`}>
                  {money(p.amount)}
                </span>
                {canDecide && p.status === "draft" && (
                  <button type="button" className="secondary-button !py-1" data-testid={`penalty-issue-${p.id}`}
                    disabled={busy === p.id} onClick={() => act("issue", p)}>
                    {busy === p.id ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />} Terbitkan
                  </button>
                )}
                {canDecide && ["draft", "issued", "adjusted"].includes(p.status) && (
                  <>
                    <button type="button" className="secondary-button !py-1" data-testid={`penalty-adjust-${p.id}`}
                      onClick={() => { setDialog({ kind: "adjust", row: p }); setAmount(String(p.amount)); }}>
                      <PencilLine size={12} /> Ubah Nominal
                    </button>
                    <button type="button" className="secondary-button !py-1" data-testid={`penalty-waive-${p.id}`}
                      onClick={() => setDialog({ kind: "waive", row: p })}>
                      <Ban size={12} /> Bebaskan
                    </button>
                  </>
                )}
                {canDecide && ["issued", "adjusted"].includes(p.status) && (
                  <button type="button" className="secondary-button !py-1" data-testid={`penalty-pay-${p.id}`}
                    onClick={() => { setDialog({ kind: "pay", row: p }); setAmount(String(p.amount)); }}>
                    <Receipt size={12} /> Catat Bayar
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })}

      {dialog && (
        <div className="modal-overlay" data-testid="penalty-dialog"
          onClick={(e) => { if (e.target === e.currentTarget) setDialog(null); }}>
          <div className="modal-card" style={{ maxWidth: 460, width: "92vw" }}>
            <div className="border-b border-[#EFF0F2] px-4 py-3">
              <h3 className="text-[13.5px] font-bold">
                {dialog.kind === "waive" ? "Bebaskan Denda"
                  : dialog.kind === "adjust" ? "Ubah Nominal Denda" : "Catat Pembayaran Denda"}
                {" · "}{dialog.row.number}
              </h3>
              <p className="text-[11px] text-[#6B6B73]">
                {dialog.kind === "pay"
                  ? "Pembayaran akan dijurnal: Kas/Bank naik, Piutang Denda turun."
                  : "Keputusan ini tercatat lengkap dengan alasan & nama pemutus. Denda yang sudah berjurnal dikoreksi lewat jurnal pembalik (tidak dihapus)."}
              </p>
            </div>
            <div className="space-y-2 p-4">
              {dialog.kind !== "waive" && (
                <div className="grid gap-1">
                  <label className="kicker">Nominal</label>
                  <input type="number" className="field tabular-nums" value={amount}
                    data-testid="penalty-dialog-amount" onChange={(e) => setAmount(e.target.value)} />
                </div>
              )}
              {dialog.kind !== "pay" && (
                <div className="grid gap-1">
                  <label className="kicker">Label alasan (wajib)</label>
                  <KNSelect value={reasonCode} onValueChange={setReasonCode} className="field"
                    data-testid="penalty-dialog-reason" placeholder="Pilih alasan…"
                    options={reasons.map((r) => ({ value: r.code, label: r.label }))} />
                </div>
              )}
              {dialog.kind !== "pay" && (
                <div className="grid gap-1">
                  <label className="kicker">Catatan</label>
                  <textarea className="field" rows={2} value={note} data-testid="penalty-dialog-note"
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="Mis. hasil pembicaraan dengan pelanggan…" />
                </div>
              )}
              {err && <div className="notice-bar danger !py-1.5"><span className="text-[11.5px]">{err}</span></div>}
              {dialog.kind !== "pay" && !reasonCode && (
                <p className="flex items-center gap-1 text-[10.5px] text-[#8C4A00]">
                  <AlertTriangle size={11} /> Pilih label alasan dulu — server akan menolak tanpa alasan.
                </p>
              )}
            </div>
            <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
              <button type="button" className="secondary-button" onClick={() => setDialog(null)}
                data-testid="penalty-dialog-cancel">Batal</button>
              <button type="button" className="primary-button" data-testid="penalty-dialog-submit"
                disabled={busy !== "" || (dialog.kind !== "pay" && !reasonCode)}
                onClick={() => act(dialog.kind, dialog.row)}>
                {busy ? <Loader2 size={13} className="animate-spin" /> : null} Simpan keputusan
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
