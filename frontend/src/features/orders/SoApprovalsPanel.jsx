import { useRef, useState } from "react";
import {
  ShieldCheck, CreditCard, Tag, CheckCircle2, XCircle, Paperclip,
  Plus, Send, AlertTriangle, Loader2, FileCheck2,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";

const TYPE_META = {
  nilai: { label: "Persetujuan Nilai Pesanan", icon: ShieldCheck, color: "#5856D6" },
  kredit: { label: "Persetujuan Kredit (Melebihi Batas)", icon: CreditCard, color: "#FF3B30" },
  special_price: { label: "Persetujuan Harga Khusus", icon: Tag, color: "#FF9500" },
};
const STATUS_META = {
  pending: { label: "Menunggu", cls: "border-[#FFE2B8] bg-[#FFF7EC] text-[#9A5B00]" },
  approved: { label: "Disetujui", cls: "border-[#BFE6CD] bg-[#E5F6EC] text-[#1B7A43]" },
  rejected: { label: "Ditolak", cls: "border-[#F5C2C2] bg-[#FDE2E2] text-[#9B1C1C]" },
};
const OPEN_STATES = ["reserved", "waiting_approval", "waiting_stock", "draft"];

export default function SoApprovalsPanel({ order, user, onRefresh }) {
  const role = user?.role;
  const isApprover = role === "admin" || role === "manager";
  const isSales = role === "sales";
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [spOpen, setSpOpen] = useState(false);
  const [spItem, setSpItem] = useState(0);
  const [spPrice, setSpPrice] = useState("");
  const [spReason, setSpReason] = useState("");
  const [creditOpen, setCreditOpen] = useState(false);
  const [creditReason, setCreditReason] = useState("");
  const fileRefs = useRef({});

  const pa = order.pending_approvals || [];
  const items = order.items || [];
  const authToken = () => (axios.defaults.headers.common.Authorization || "").replace("Bearer ", "");
  const canRequest = OPEN_STATES.includes(order.status);
  const hasPendingCredit = pa.some((p) => p.type === "kredit" && p.status === "pending");
  const showCreditCta = canRequest && (order.credit_hold || order.credit_warning) && !hasPendingCredit;

  async function run(fn, okMsg, after) {
    setBusy(true); setErr(""); setMsg("");
    try {
      await fn();
      setMsg(okMsg);
      after && after();
      await onRefresh?.();
    } catch (e) {
      const d = e.response?.data?.detail;
      setErr((d && (d.message || (typeof d === "string" ? d : null))) || "Aksi gagal. Coba lagi.");
    } finally {
      setBusy(false);
    }
  }

  const decide = (entry, decision) =>
    run(() => axios.post(`${API}/sales-orders/${order.id}/approvals/${entry.id}/decide`, { decision, notes: "" }),
      decision === "approve" ? "Persetujuan disimpan." : "Ditolak.");

  const submitSpecialPrice = () => {
    if (!spReason.trim()) { setErr("Alasan harga khusus wajib diisi."); return; }
    if (!(Number(spPrice) > 0)) { setErr("Harga khusus harus lebih dari 0."); return; }
    run(() => axios.post(`${API}/sales-orders/${order.id}/request-special-price`, {
      item_index: Number(spItem), requested_price: Number(spPrice), reason: spReason.trim(),
    }), "Pengajuan harga khusus terkirim.", () => { setSpOpen(false); setSpPrice(""); setSpReason(""); });
  };

  const requestCredit = () =>
    run(() => axios.post(`${API}/sales-orders/${order.id}/request-credit-approval`, { reason: creditReason.trim() }),
      "Permintaan approval kredit terkirim.", () => { setCreditOpen(false); setCreditReason(""); });

  const onPickFile = (entry, e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    run(() => axios.post(`${API}/sales-orders/${order.id}/approvals/${entry.id}/evidence`, fd,
      { headers: { "Content-Type": "multipart/form-data" } }), "Bukti terunggah.");
    e.target.value = "";
  };

  if (!pa.length && !canRequest) return null;

  return (
    <div data-testid="so-approvals-panel" className="rounded-lg border border-[#EFF0F2] bg-white p-3">
      <div className="mb-2 flex items-center gap-2">
        <FileCheck2 size={14} className="text-[#0058CC]" />
        <h4 className="text-[12px] font-bold text-[#1C1C1E]">Persetujuan</h4>
        {pa.some((p) => p.status === "pending") && (
          <span className="rounded-full bg-[#FFF7EC] px-2 py-0.5 text-[10px] font-bold text-[#9A5B00]">
            {pa.filter((p) => p.status === "pending").length} menunggu
          </span>
        )}
      </div>

      {msg && <div data-testid="so-appr-msg" className="mb-2 rounded-md bg-[#E5F6EC] px-2.5 py-1.5 text-[11px] text-[#1B7A43]">{msg}</div>}
      {err && <div data-testid="so-appr-err" className="mb-2 flex items-center gap-1.5 rounded-md bg-[#FDE2E2] px-2.5 py-1.5 text-[11px] text-[#9B1C1C]"><AlertTriangle size={12} />{err}</div>}

      {/* Daftar entri approval */}
      <div className="space-y-2">
        {pa.length === 0 && (
          <p className="text-[11px] text-[#8E8E93]">Belum ada pengajuan persetujuan untuk pesanan ini.</p>
        )}
        {pa.map((entry) => {
          const tm = TYPE_META[entry.type] || TYPE_META.nilai;
          const sm = STATUS_META[entry.status] || STATUS_META.pending;
          const Icon = tm.icon;
          const ev = (entry.evidence || []).filter((a) => !a.is_deleted);
          return (
            <div key={entry.id} data-testid={`so-appr-entry-${entry.id}`} className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md" style={{ background: `${tm.color}1A` }}>
                    <Icon size={13} style={{ color: tm.color }} />
                  </span>
                  <div className="min-w-0">
                    <p className="text-[11.5px] font-bold text-[#1C1C1E]">{tm.label}</p>
                    {entry.type === "special_price" && (
                      <p className="text-[10.5px] text-[#6B6B73] tabular-nums">
                        {entry.product_name} · <span className="line-through">{formatCurrency(entry.normal_price)}</span>{" "}
                        → <b className="text-[#FF9500]">{formatCurrency(entry.requested_price)}</b>
                      </p>
                    )}
                    {entry.amount != null && entry.type !== "special_price" && (
                      <p className="text-[10.5px] text-[#6B6B73] tabular-nums">Nilai {formatCurrency(entry.amount)}</p>
                    )}
                  </div>
                </div>
                <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[9.5px] font-bold uppercase ${sm.cls}`}>{sm.label}</span>
              </div>
              {entry.reason && <p className="mt-1.5 text-[10.5px] text-[#3C3C43]">“{entry.reason}”</p>}
              <p className="mt-1 text-[9.5px] text-[#8E8E93]">
                Diminta oleh {entry.requested_by || "-"} · butuh peran <b className="uppercase">{entry.required_role}</b>
                {entry.decided_by && ` · diputuskan ${entry.decided_by}`}
              </p>
              {ev.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {ev.map((a) => (
                    <a key={a.id} data-testid={`so-appr-evidence-link-${a.id}`}
                      href={`${API}/sales-orders/${order.id}/approvals/${entry.id}/evidence/${a.id}/download?auth=${authToken()}`}
                      target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded bg-[#EEF2FF] px-1.5 py-0.5 text-[9.5px] text-[#3730A3] hover:underline">
                      <Paperclip size={9} />{a.original_filename}
                    </a>
                  ))}
                </div>
              )}

              {/* Aksi per entri */}
              {entry.status === "pending" && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {isApprover && (
                    <>
                      <button data-testid={`so-appr-approve-${entry.id}`} disabled={busy}
                        className="inline-flex items-center gap-1 rounded-md bg-[#1B7A43] px-2.5 py-1 text-[10.5px] font-semibold text-white disabled:opacity-50"
                        onClick={() => decide(entry, "approve")}>
                        <CheckCircle2 size={12} /> Setujui
                      </button>
                      <button data-testid={`so-appr-reject-${entry.id}`} disabled={busy}
                        className="inline-flex items-center gap-1 rounded-md border border-[#F5C2C2] bg-white px-2.5 py-1 text-[10.5px] font-semibold text-[#9B1C1C] disabled:opacity-50"
                        onClick={() => decide(entry, "reject")}>
                        <XCircle size={12} /> Tolak
                      </button>
                    </>
                  )}
                  <button data-testid={`so-appr-evidence-${entry.id}`} disabled={busy}
                    className="inline-flex items-center gap-1 rounded-md border border-[#E5E5EA] bg-white px-2.5 py-1 text-[10.5px] font-semibold text-[#3A3A3C] disabled:opacity-50"
                    onClick={() => fileRefs.current[entry.id]?.click()}>
                    <Paperclip size={12} /> Unggah Bukti
                  </button>
                  <input ref={(el) => (fileRefs.current[entry.id] = el)} type="file" accept="image/*,application/pdf"
                    className="hidden" onChange={(e) => onPickFile(entry, e)} />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Aksi pengajuan (sales / requester) */}
      {canRequest && (isSales || isApprover) && (
        <div className="mt-2.5 border-t border-[#EFF0F2] pt-2.5">
          <div className="flex flex-wrap gap-1.5">
            <button data-testid="so-appr-request-sp-toggle" disabled={busy}
              className="inline-flex items-center gap-1 rounded-md border border-[#FFE2B8] bg-[#FFF7EC] px-2.5 py-1 text-[10.5px] font-semibold text-[#9A5B00]"
              onClick={() => { setSpOpen((v) => !v); setCreditOpen(false); }}>
              <Tag size={12} /> Ajukan Harga Khusus
            </button>
            {showCreditCta && (
              <button data-testid="so-appr-request-credit-toggle" disabled={busy}
                className="inline-flex items-center gap-1 rounded-md border border-[#F5C2C2] bg-[#FDECEC] px-2.5 py-1 text-[10.5px] font-semibold text-[#9B1C1C]"
                onClick={() => { setCreditOpen((v) => !v); setSpOpen(false); }}>
                <CreditCard size={12} /> Minta Persetujuan Kredit
              </button>
            )}
          </div>

          {spOpen && (
            <div data-testid="so-appr-sp-form" className="mt-2 space-y-2 rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
              <KNSelect data-testid="so-appr-sp-item" className="field !py-1.5 !text-[11px]" value={String(spItem)}
                onValueChange={(v) => setSpItem(v)}
                options={items.map((it, i) => ({ value: String(i), label: `${it.product_name || it.name} · ${formatCurrency(it.price)}/unit` }))} />
              <input data-testid="so-appr-sp-price" type="number" min="0" value={spPrice} onChange={(e) => setSpPrice(e.target.value)}
                placeholder="Harga khusus per unit (Rp)" className="w-full rounded-md border border-[#E5E5EA] bg-white px-2 py-1.5 text-[11px]" />
              <textarea data-testid="so-appr-sp-reason" rows={2} value={spReason} onChange={(e) => setSpReason(e.target.value)}
                placeholder="Alasan (wajib): nego pelanggan, kompetitor, dll." className="w-full rounded-md border border-[#E5E5EA] bg-white px-2 py-1.5 text-[11px]" />
              <button data-testid="so-appr-sp-submit" disabled={busy} onClick={submitSpecialPrice}
                className="primary-button w-full justify-center py-1.5 text-[11px]">
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />} Kirim Pengajuan
              </button>
            </div>
          )}

          {creditOpen && (
            <div data-testid="so-appr-credit-form" className="mt-2 space-y-2 rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
              <textarea data-testid="so-appr-credit-reason" rows={2} value={creditReason} onChange={(e) => setCreditReason(e.target.value)}
                placeholder="Alasan permintaan persetujuan kredit (wajib)" className="w-full rounded-md border border-[#E5E5EA] bg-white px-2 py-1.5 text-[11px]" />
              <button data-testid="so-appr-credit-submit" disabled={busy} onClick={requestCredit}
                className="primary-button w-full justify-center py-1.5 text-[11px]">
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Kirim Permintaan
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
