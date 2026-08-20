import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { ArrowLeft, Edit3, UserCog, ShieldAlert, PhoneCall, MapPin, CreditCard, X } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import { CreditStatusPill, SegmentBadge, OutcomePill, KpiTile, fmtDate, money } from "./crmUtils";
import CustomerFormModal from "./CustomerFormModal";

const HIST_TABS = [
  { key: "orders", label: "Pesanan" },
  { key: "documents", label: "Dokumen" },
  { key: "prices", label: "Harga Khusus" },
  { key: "followups", label: "Penagihan" },
  { key: "overrides", label: "Override Kredit" },
];

/** Customer 360 (KN_17 §2) — profil + kredit + riwayat + aksi. */
export default function Customer360Panel({ customerId, currentUser, salesUsers, onBack, onChanged, onError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("orders");
  const [showEdit, setShowEdit] = useState(false);
  const [modal, setModal] = useState(null); // 'reassign' | 'override' | 'followup'

  const role = currentUser?.role;
  const isManager = role === "admin" || role === "manager";

  useEffect(() => { load(); }, [customerId]); // eslint-disable-line

  async function load() {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/customers/${customerId}/360`);
      setData(r.data);
    } catch (e) {
      onError?.(e.response?.data?.detail || "Gagal memuat detail pelanggan.");
      onBack?.();
    } finally { setLoading(false); }
  }

  if (loading && !data) return <div className="section-card py-12 text-center text-[12px] text-[#6B6B73]" data-testid="customer-360-loading">Memuat detail pelanggan...</div>;
  if (!data) return null;

  const credit = data.credit || {};
  const limit = Number(credit.credit_limit || 0);

  return (
    <div data-testid="customer-360-panel">
      <button data-testid="customer-360-back" onClick={onBack} className="secondary-button mb-3"><ArrowLeft size={13} /> Kembali ke daftar</button>

      {/* Header */}
      <div className="section-card mb-3">
        <div className="section-head">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="truncate" data-testid="customer-360-name">{data.name}</h2>
              <SegmentBadge segment={data.segment} />
              <CreditStatusPill status={credit.status || "active"} testId="customer-360-credit-status" />
            </div>
            <p className="text-[11px] text-[#6B6B73] mt-0.5">{data.code} · {data.city} · Sales: <b>{data.assigned_sales_name || "—"}</b></p>
          </div>
          <div className="flex items-center gap-1.5">
            <button data-testid="customer-360-edit" onClick={() => setShowEdit(true)} className="secondary-button"><Edit3 size={13} /> Ubah</button>
            {isManager && <button data-testid="customer-360-reassign" onClick={() => setModal("reassign")} className="secondary-button"><UserCog size={13} /> Reassign</button>}
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[320px_1fr]">
        {/* Left: credit + profile */}
        <div className="space-y-3">
          {/* Credit card */}
          <div className="section-card">
            <div className="section-head"><div className="flex items-center gap-2"><CreditCard size={14} className="text-[#0058CC]" /><h3 className="text-[12.5px] font-bold">Kontrol Kredit</h3></div></div>
            <div className="section-body grid grid-cols-2 gap-2">
              <KpiTile label="Limit Kredit" value={limit > 0 ? formatCurrency(limit) : "Tanpa limit"} />
              <KpiTile label="Piutang Belum Lunas" value={formatCurrency(credit.ar_outstanding)} tone="text-[#0058CC]" testId="customer-360-ar" />
              <KpiTile label="Jatuh Tempo (Lewat Tempo)" value={formatCurrency(credit.overdue_amount)} tone={Number(credit.overdue_amount) > 0 ? "text-[#C0392B]" : ""} sub={credit.max_overdue_days ? `${credit.max_overdue_days} hari` : ""} testId="customer-360-overdue" />
              <KpiTile label="Sisa Kredit" value={credit.available_credit != null ? formatCurrency(credit.available_credit) : "∞"} sub={`${credit.open_orders || 0} pesanan terbuka`} />
            </div>
            <div className="px-3 pb-3">
              <button data-testid="customer-360-override" onClick={() => setModal("override")} className="secondary-button w-full justify-center">
                <ShieldAlert size={13} /> Ajukan Override Kredit
              </button>
            </div>
          </div>

          {/* Profile */}
          <div className="section-card">
            <div className="section-head"><h3 className="text-[12.5px] font-bold">Profil & Kontak</h3></div>
            <div className="section-body space-y-2 text-[11.5px]">
              {(data.contacts || []).length > 0 ? (data.contacts || []).map((ct, i) => (
                <div key={i} className="flex items-center gap-2"><PhoneCall size={12} className="text-[#6B6B73]" />
                  <span className="font-semibold">{ct.name}</span><span className="text-[#6B6B73]">{ct.role}</span>
                  <span className="text-[#9A9BA3] ml-auto">{ct.phone}</span></div>
              )) : <p className="text-[#9A9BA3]">{data.pic_name} · {data.phone}</p>}
              {(data.addresses || []).map((ad, i) => (
                <div key={i} className="flex items-start gap-2"><MapPin size={12} className="text-[#6B6B73] mt-0.5" />
                  <span className="text-[#3C3C43]">{ad.address}, {ad.city}</span></div>
              ))}
              <div className="pt-2 border-t border-[#EFF0F2]">
                <p className="text-[10px] uppercase text-[#9A9BA3] font-semibold mb-1">Profil Pembayaran</p>
                <p>Default: <b>{(data.payment_profile?.default_method || "—").toUpperCase()}</b> · Termin {data.payment_profile?.term_days ?? 0} hari · DP {data.payment_profile?.dp_percent ?? 0}%</p>
                <p className="text-[10.5px] text-[#6B6B73]">Metode: {(data.payment_profile?.allowed_methods || []).join(", ") || "—"}</p>
              </div>
              {/* SALES REVAMP V2 — Tim sales (PIC + co-sales + split) */}
              <div className="pt-2 border-t border-[#EFF0F2]" data-testid="customer-360-sales-team">
                <p className="text-[10px] uppercase text-[#9A9BA3] font-semibold mb-1">Tim Sales (Split Insentif)</p>
                {(data.sales_team || []).length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {(data.sales_team || []).map((m, i) => (
                      <span key={i} data-testid={`customer-360-team-${i}`} className={`status-pill ${m.role === "pic" ? "status-confirmed" : "pill-muted"}`}>
                        {m.role === "pic" ? "PIC " : ""}{m.name || m.sales_id} · <b className="tabular-nums">{m.split_pct}%</b>
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-[10.5px] text-[#6B6B73]">PIC tunggal: <b>{data.assigned_sales_name || "—"}</b> (100%)</p>
                )}
              </div>
              {/* SALES REVAMP V2 — Kebijakan lot */}
              <div className="pt-2 border-t border-[#EFF0F2]" data-testid="customer-360-lot-policy">
                <p className="text-[10px] uppercase text-[#9A9BA3] font-semibold mb-1">Kebijakan Lot</p>
                <p className="text-[10.5px] text-[#6B6B73]">
                  {{
                    "": "Default (prefer single)", prefer_single: "Prefer single lot",
                    strict_single: "Strict single lot", allow_mixed: "Boleh mixed lot",
                  }[data.lot_policy || ""] || (data.lot_policy || "—")}
                  {data.enforce_single_dye_lot ? " · Paksa 1 dye lot" : ""}
                </p>
              </div>
              {(data.tags || []).length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1">
                  {data.tags.map((t) => <span key={t} className="status-pill pill-muted">{t}</span>)}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right: history */}
        <div className="section-card self-start">
          <div className="section-head">
            <div className="flex items-center gap-3 flex-wrap">
              <h3 className="text-[12.5px] font-bold">Riwayat 360°</h3>
              <span className="text-[11px] text-[#6B6B73]">{data.stats?.total_orders || 0} order · LTV {money(data.stats?.lifetime_value)}</span>
            </div>
            <button data-testid="customer-360-followup" onClick={() => setModal("followup")} className="secondary-button text-[11px]">+ Follow-up</button>
          </div>
          <div className="section-body">
            <div className="tab-bar mb-2">
              {HIST_TABS.map((t) => (
                <button key={t.key} data-testid={`customer-360-tab-${t.key}`} className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                  {t.label}<span className="tab-badge">{listFor(data, t.key).length}</span>
                </button>
              ))}
            </div>
            <HistoryTable data={data} tab={tab} />
          </div>
        </div>
      </div>

      <CustomerFormModal open={showEdit} editTarget={data} currentUser={currentUser} salesUsers={salesUsers}
        onClose={() => setShowEdit(false)}
        onSaved={(c) => { setShowEdit(false); onChanged?.(`Pelanggan ${c.name} diperbarui.`); load(); }}
        onError={onError} />

      {modal === "reassign" && <ReassignModal customer={data} salesUsers={salesUsers} onClose={() => setModal(null)}
        onDone={(msg) => { setModal(null); onChanged?.(msg); load(); }} onError={onError} />}
      {modal === "override" && <OverrideModal customer={data} onClose={() => setModal(null)}
        onDone={(msg) => { setModal(null); onChanged?.(msg); load(); }} onError={onError} />}
      {modal === "followup" && <FollowupModal customer={data} onClose={() => setModal(null)}
        onDone={(msg) => { setModal(null); onChanged?.(msg); load(); }} onError={onError} />}
    </div>
  );
}

function listFor(data, tab) {
  return ({ orders: data.order_history, documents: data.document_history, prices: data.special_price_history,
    followups: data.collection_followups, overrides: data.credit_overrides }[tab]) || [];
}

function HistoryTable({ data, tab }) {
  const rows = listFor(data, tab);
  if (rows.length === 0) return <div className="py-8 text-center text-[11.5px] text-[#9A9BA3]" data-testid="customer-360-history-empty">Belum ada data.</div>;
  return (
    <div className="divide-y divide-[#EFF0F2] max-h-[440px] overflow-y-auto" data-testid={`customer-360-history-${tab}`}>
      {tab === "orders" && rows.map((o) => (
        <div key={o.id} className="flex items-center justify-between py-2 text-[11.5px]">
          <div><p className="font-semibold text-[#0058CC]">{o.number}</p><p className="text-[10px] text-[#6B6B73]">{fmtDate(o.created_at)} · {o.status} · {o.payment_status}</p></div>
          <div className="text-right"><p className="tabular-nums font-semibold">{formatCurrency(o.grand_total)}</p><p className="text-[10px] text-[#6B6B73] tabular-nums">bayar {formatCurrency(o.paid)}</p></div>
        </div>
      ))}
      {tab === "documents" && rows.map((d, i) => (
        <div key={i} className="flex items-center justify-between py-2 text-[11.5px]">
          <span className="font-semibold">{d.document_type || d.type || d.number || "Dokumen"}</span>
          <span className="text-[10px] text-[#6B6B73]">{fmtDate(d.created_at)}</span>
        </div>
      ))}
      {tab === "prices" && rows.map((p, i) => (
        <div key={i} className="flex items-center justify-between py-2 text-[11.5px]">
          <div><p className="font-semibold">{p.product_name || p.product_id}</p><p className="text-[10px] text-[#6B6B73]">{p.status} · {fmtDate(p.created_at)}</p></div>
          <span className="tabular-nums font-semibold">{formatCurrency(p.approved_price || p.special_price || p.price)}</span>
        </div>
      ))}
      {tab === "followups" && rows.map((fu, i) => (
        <div key={i} className="flex items-start justify-between py-2 text-[11.5px] gap-2">
          <div className="min-w-0"><p className="truncate">{fu.note}</p><p className="text-[10px] text-[#6B6B73]">{fu.created_by} · {fmtDate(fu.created_at)}</p></div>
          <OutcomePill outcome={fu.outcome} />
        </div>
      ))}
      {tab === "overrides" && rows.map((ov) => (
        <div key={ov.id} className="flex items-start justify-between py-2 text-[11.5px] gap-2">
          <div className="min-w-0"><p className="truncate">{ov.reason}</p><p className="text-[10px] text-[#6B6B73]">{formatCurrency(ov.amount)} · {ov.requested_by} · {fmtDate(ov.created_at)}</p></div>
          <span className={`status-pill ${ov.status === "approved" ? "pill-success" : ov.status === "rejected" ? "pill-danger" : "pill-warning"}`}>{ov.status}</span>
        </div>
      ))}
    </div>
  );
}

function MiniModal({ title, icon, children, onClose, testId }) {
  return (
    <div className="modal-overlay" data-testid={testId} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 440, width: "92vw" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2]">
          <div className="flex items-center gap-2">{icon}<h2 className="text-[14px] font-bold">{title}</h2></div>
          <button onClick={onClose} className="icon-button"><X size={16} /></button>
        </div>
        <div className="p-4 space-y-3">{children}</div>
      </div>
    </div>
  );
}

function ReassignModal({ customer, salesUsers, onClose, onDone, onError }) {
  const [sid, setSid] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    if (!sid) { onError?.("Pilih sales tujuan."); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/customers/${customer.id}/reassign`, { assigned_sales_id: sid, reason });
      onDone?.("Pelanggan dipindahkan ke sales baru.");
    } catch (e) { onError?.(e.response?.data?.detail || "Gagal reassign."); } finally { setBusy(false); }
  }
  return (
    <MiniModal title="Reassign Salesperson" icon={<UserCog size={16} className="text-[#0058CC]" />} onClose={onClose} testId="reassign-modal">
      <KNSelect value={sid} onValueChange={setSid} className="field" data-testid="reassign-sales-select"
        placeholder="Pilih sales tujuan" options={(salesUsers || []).filter((s) => s.id !== customer.assigned_sales_id).map((s) => ({ value: s.id, label: s.name }))} />
      <input data-testid="reassign-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="field" placeholder="Alasan (opsional)" />
      <div className="flex justify-end gap-2 pt-1">
        <button onClick={onClose} className="secondary-button">Batal</button>
        <button data-testid="reassign-submit" disabled={busy} onClick={go} className="primary-button">{busy ? "..." : "Pindahkan"}</button>
      </div>
    </MiniModal>
  );
}

function OverrideModal({ customer, onClose, onDone, onError }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    if (!reason.trim()) { onError?.("Alasan override wajib diisi."); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/customers/${customer.id}/credit-override`, {
        customer_id: customer.id, amount: Number(amount) || 0, reason, evidence_url: evidence });
      onDone?.("Permohonan override kredit diajukan (menunggu approval).");
    } catch (e) { onError?.(e.response?.data?.detail || "Gagal mengajukan override."); } finally { setBusy(false); }
  }
  return (
    <MiniModal title="Ajukan Override Kredit" icon={<ShieldAlert size={16} className="text-[#B45309]" />} onClose={onClose} testId="override-modal">
      <p className="text-[11px] text-[#6B6B73]">Permohonan akan diteruskan ke Manager/Finance untuk persetujuan (KN_17 §5.2).</p>
      <input type="number" data-testid="override-amount" value={amount} onChange={(e) => setAmount(e.target.value)} className="field" placeholder="Nilai pesanan yang diminta (Rp)" />
      <textarea data-testid="override-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="field" rows="2" placeholder="Alasan (wajib): mis. PO besar sudah dikonfirmasi" />
      <input data-testid="override-evidence" value={evidence} onChange={(e) => setEvidence(e.target.value)} className="field" placeholder="URL bukti (opsional)" />
      <div className="flex justify-end gap-2 pt-1">
        <button onClick={onClose} className="secondary-button">Batal</button>
        <button data-testid="override-submit" disabled={busy} onClick={go} className="primary-button">{busy ? "..." : "Ajukan"}</button>
      </div>
    </MiniModal>
  );
}

function FollowupModal({ customer, onClose, onDone, onError }) {
  const [note, setNote] = useState("");
  const [outcome, setOutcome] = useState("contacted");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    if (!note.trim()) { onError?.("Catatan follow-up wajib diisi."); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/customers/${customer.id}/followups`, {
        customer_id: customer.id, note, outcome, next_action_date: next });
      onDone?.("Follow-up penagihan dicatat.");
    } catch (e) { onError?.(e.response?.data?.detail || "Gagal menyimpan follow-up."); } finally { setBusy(false); }
  }
  return (
    <MiniModal title="Catat Follow-up Penagihan" icon={<PhoneCall size={16} className="text-[#0058CC]" />} onClose={onClose} testId="followup-modal">
      <textarea data-testid="followup-note" value={note} onChange={(e) => setNote(e.target.value)} className="field" rows="2" placeholder="Hasil kontak / catatan..." />
      <KNSelect value={outcome} onValueChange={setOutcome} className="field" data-testid="followup-outcome"
        options={[{ value: "contacted", label: "Dihubungi" }, { value: "promised", label: "Dijanjikan bayar" },
          { value: "paid", label: "Sudah bayar" }, { value: "no_response", label: "Tak ada respon" }, { value: "escalated", label: "Eskalasi" }]} />
      <div>
        <label className="block text-[11px] font-semibold text-[#4A4B53] mb-1">Tindak lanjut berikutnya</label>
        <input type="date" data-testid="followup-next" value={next} onChange={(e) => setNext(e.target.value)} className="field" />
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <button onClick={onClose} className="secondary-button">Batal</button>
        <button data-testid="followup-submit" disabled={busy} onClick={go} className="primary-button">{busy ? "..." : "Simpan"}</button>
      </div>
    </MiniModal>
  );
}
