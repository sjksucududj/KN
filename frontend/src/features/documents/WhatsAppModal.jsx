// WhatsAppModal — kirim dokumen via WhatsApp (mode simulasi) + riwayat pengiriman.
import { useCallback, useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { X, Send, Loader2, MessageCircle, CheckCircle2, Paperclip, Info } from "lucide-react";

const statusTone = {
  simulated: "bg-[#EAF2FF] text-[#0058CC]",
  sent: "bg-[#ECFAF1] text-[#1F7A45]",
  failed: "bg-[#FDECEA] text-[#C0392B]",
};

export default function WhatsAppModal({ open, onClose, doc, onSent }) {
  const [to, setTo] = useState("");
  const [caption, setCaption] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState(null);
  const [history, setHistory] = useState([]);
  const [settings, setSettings] = useState(null);
  const [recipient, setRecipient] = useState(null);

  const loadHistory = useCallback(async () => {
    if (!doc) return;
    try {
      const r = await axios.get(`${API}/deliveries/${doc.doc_type}/${doc.source_id}`);
      setHistory(r.data.deliveries || []);
    } catch (e) { /* ignore */ }
  }, [doc]);

  useEffect(() => {
    if (open) {
      setTo(""); setCaption(doc ? `${doc.label} ${doc.number || ""}`.trim() : "");
      setMessage(""); setErr(""); setOk(null); setRecipient(null);
      loadHistory();
      axios.get(`${API}/deliveries/whatsapp/settings`).then((r) => setSettings(r.data)).catch(() => {});
      // Auto-isi nomor tujuan dari data pelanggan/pemasok dokumen.
      if (doc) {
        axios.get(`${API}/deliveries/whatsapp/recipient/${doc.doc_type}/${doc.source_id}`,
          { params: { entity_id: doc.entity_id || undefined } })
          .then((r) => {
            setRecipient(r.data);
            if (r.data?.phone) setTo(r.data.phone);
          }).catch(() => {});
      }
    }
  }, [open, doc, loadHistory]);

  const send = useCallback(async () => {
    setErr(""); setOk(null);
    if (!to.trim()) { setErr("Nomor WhatsApp tujuan wajib diisi."); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/deliveries/whatsapp/send`, {
        doc_type: doc.doc_type, source_id: doc.source_id, entity_id: doc.entity_id,
        to: to.trim(), caption: caption.trim(), message: message.trim(),
      });
      setOk(r.data);
      loadHistory();
      onSent && onSent();
    } catch (e) { setErr(e.response?.data?.detail || "Gagal mengirim."); }
    finally { setBusy(false); }
  }, [to, caption, message, doc, loadHistory, onSent]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4" data-testid="wa-modal"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="flex w-full max-w-[540px] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl" style={{ maxHeight: "92vh" }}>
        <div className="flex items-center justify-between border-b border-[#EDEEF1] px-5 py-3.5">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#E7F8EE] text-[#1F7A45]"><MessageCircle size={16} /></span>
            <div>
              <h3 className="text-[14px] font-bold leading-tight">Kirim via WhatsApp</h3>
              <p className="text-[11px] text-[#6B6B73]">{doc?.label} · {doc?.number || doc?.source_id}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-[#9A9BA3] hover:text-[#1a1a1a]" data-testid="wa-close"><X size={18} /></button>
        </div>

        <div className="overflow-y-auto px-5 py-4">
          {settings?.simulate && (
            <div className="mb-3 flex items-start gap-2 rounded-lg bg-[#FFF7E6] px-3 py-2 text-[11.5px] text-[#8a5a00]">
              <Info size={14} className="mt-0.5 shrink-0" />
              <span>Mode <b>simulasi</b> aktif — pesan tidak benar-benar dikirim, hanya dicatat untuk pengujian.</span>
            </div>
          )}
          {err && <div className="notice-bar danger mb-3 !py-1.5"><span className="text-[11.5px]">{err}</span></div>}
          {ok && (
            <div className="mb-3 flex items-center gap-2 rounded-lg bg-[#ECFAF1] px-3 py-2 text-[12px] text-[#1F7A45]" data-testid="wa-success">
              <CheckCircle2 size={15} /> Terkirim{ok.simulated ? " (simulasi)" : ""} ke <b>{ok.to}</b> · ID: {ok.message_id}
            </div>
          )}

          <div className="grid gap-3">
            <div className="grid gap-1">
              <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Nomor WhatsApp Tujuan</label>
              <input className="form-input" value={to} onChange={(e) => setTo(e.target.value)}
                placeholder="08xxx atau 62xxx" data-testid="wa-to" />
              {recipient?.name && recipient?.phone && (
                <span className="text-[10.5px] text-[#1F7A45]" data-testid="wa-recipient-hint">
                  Terisi otomatis dari {recipient.mode === "supplier" ? "pemasok" : "pelanggan"}: <b>{recipient.name}</b>
                </span>
              )}
            </div>
            <div className="grid gap-1">
              <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Keterangan (caption lampiran)</label>
              <input className="form-input" value={caption} onChange={(e) => setCaption(e.target.value)} data-testid="wa-caption" />
            </div>
            <div className="grid gap-1">
              <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Pesan tambahan (opsional)</label>
              <textarea className="form-input min-h-[56px]" value={message} onChange={(e) => setMessage(e.target.value)}
                placeholder="Halo, berikut kami kirimkan dokumen…" data-testid="wa-message" />
            </div>
            <div className="flex items-center gap-2 text-[11px] text-[#9A9BA3]">
              <Paperclip size={13} /> Lampiran PDF dokumen akan disertakan otomatis.
            </div>
            <button className="btn-primary flex items-center justify-center gap-2" onClick={send} disabled={busy} data-testid="wa-send">
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />} Kirim{settings?.simulate ? " (Simulasi)" : ""}
            </button>
          </div>

          {/* Riwayat */}
          <div className="mt-5">
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Riwayat Pengiriman ({history.length})</p>
            {history.length === 0 ? (
              <p className="text-[11.5px] text-[#9A9BA3]">Belum ada pengiriman untuk dokumen ini.</p>
            ) : (
              <div className="grid gap-1.5" data-testid="wa-history">
                {history.map((h) => (
                  <div key={h.id} className="flex items-center justify-between rounded-lg border border-[#EDEEF1] px-3 py-1.5">
                    <div className="min-w-0">
                      <p className="text-[12px] font-semibold">{h.to}</p>
                      <p className="truncate text-[10.5px] text-[#9A9BA3]">{String(h.sent_at || "").slice(0, 19).replace("T", " ")} · {h.attachment_name}</p>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ${statusTone[h.status] || "bg-[#F1F2F4] text-[#4A4B52]"}`}>{h.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
