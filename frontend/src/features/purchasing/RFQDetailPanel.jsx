import { useCallback, useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { X, Send, Award, Ban, CheckCircle2, Pencil } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import QtyDual from "../../components/QtyDual";      // FASE U — dua satuan
import { overlayDismiss } from "@/utils/overlayDismiss";

/**
 * RFQDetailPanel (Fase 6.1) — detail RFQ: input penawaran per supplier,
 * banding harga (matriks), dan award (penuh / per-baris) → PO.
 */
export default function RFQDetailPanel({ rfqId, currentUser, onClose, onChanged }) {
  const [rfq, setRfq] = useState(null);
  const [compare, setCompare] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [quoteFor, setQuoteFor] = useState(null);   // supplier_id being quoted
  const [quoteLines, setQuoteLines] = useState({}); // line_id -> price
  const [quoteMeta, setQuoteMeta] = useState({ lead_time_days: "", valid_until: "" });
  const [awardMode, setAwardMode] = useState("full");
  const [fullSupplier, setFullSupplier] = useState("");
  const [lineAwards, setLineAwards] = useState({}); // line_id -> supplier_id

  const canAct = ["admin", "manager"].includes(currentUser?.role);
  const canQuote = ["admin", "manager", "warehouse"].includes(currentUser?.role);

  const load = useCallback(async () => {
    try {
      const [d, c] = await Promise.all([
        axios.get(`${API}/rfqs/${rfqId}`),
        axios.get(`${API}/rfqs/${rfqId}/compare`).catch(() => ({ data: null })),
      ]);
      setRfq(d.data); setCompare(c.data); setErr("");
    } catch (e) { setErr(e.response?.data?.detail || "Gagal memuat RFQ."); }
  }, [rfqId]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (compare?.recommended_full_supplier_id) setFullSupplier((p) => p || compare.recommended_full_supplier_id);
    if (compare?.recommended_line_awards) {
      setLineAwards((prev) => Object.keys(prev).length ? prev :
        compare.recommended_line_awards.reduce((a, x) => ({ ...a, [x.line_id]: x.supplier_id }), {}));
    }
  }, [compare]);

  function openQuote(sup) {
    setQuoteFor(sup.supplier_id);
    setQuoteLines((sup.lines || []).reduce((a, l) => ({ ...a, [l.line_id]: l.price || "" }), {}));
    setQuoteMeta({ lead_time_days: sup.lead_time_days || "", valid_until: sup.valid_until || "" });
  }

  async function action(fn, okMsg) {
    setBusy(true); setErr("");
    try { await fn(); if (okMsg) onChanged?.(okMsg); await load(); onChanged?.(); }
    catch (e) { setErr(e.response?.data?.detail || "Operasi gagal."); }
    finally { setBusy(false); }
  }

  async function submitQuote() {
    const lines = (rfq.items || []).map((it) => ({
      line_id: it.line_id, price: Number(quoteLines[it.line_id] || 0),
      available: Number(quoteLines[it.line_id] || 0) > 0,
    }));
    await action(async () => {
      await axios.post(`${API}/rfqs/${rfqId}/quote`, {
        supplier_id: quoteFor, lines,
        lead_time_days: Number(quoteMeta.lead_time_days || 0), valid_until: quoteMeta.valid_until || "",
      });
      setQuoteFor(null);
    }, "Penawaran tersimpan.");
  }

  async function doAward() {
    const body = awardMode === "full"
      ? { mode: "full", full_supplier_id: fullSupplier }
      : { mode: "line", line_awards: (rfq.items || []).map((it) => ({ line_id: it.line_id, supplier_id: lineAwards[it.line_id] })) };
    await action(async () => { await axios.post(`${API}/rfqs/${rfqId}/award`, body); }, "RFQ di-award → PO dibuat.");
  }

  if (!rfq) {
    return (
      <div className="modal-overlay" {...overlayDismiss(onClose)}>
        <div className="modal-card p-8 text-center text-[12px]">Memuat RFQ...</div>
      </div>
    );
  }

  const quotedSuppliers = (rfq.suppliers || []).filter((s) => s.quote_status === "quoted");
  const lowest = compare?.lowest_per_line || {};
  const priceMap = compare?.price_map || {};

  return (
    <div className="modal-overlay" data-testid="rfq-detail-panel" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 920, width: "96vw", maxHeight: "94vh", overflowY: "auto" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2] sticky top-0 bg-white z-10">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-[15px] font-bold text-[#0058CC]">{rfq.rfq_number}</h2>
              <StatusPill status={rfq.status} />
            </div>
            <p className="text-[11px] text-[#6B6B73] truncate">{rfq.title} · {rfq.source === "pr" ? `Dari ${rfq.pr_number}` : "Manual"} · {rfq.warehouse_name}</p>
          </div>
          <button data-testid="rfq-detail-close" onClick={onClose} className="icon-button"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-4">
          {err && <div className="notice-bar error" data-testid="rfq-detail-error"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}

          {/* Aksi status */}
          <div className="flex items-center gap-2">
            {rfq.status === "draft" && canAct && (
              <button data-testid="rfq-send" disabled={busy} onClick={() => action(() => axios.post(`${API}/rfqs/${rfqId}/send`), "RFQ dikirim.")} className="primary-button"><Send size={13} /> Kirim ke Supplier</button>
            )}
            {["draft", "open"].includes(rfq.status) && canAct && (
              <button data-testid="rfq-cancel" disabled={busy} onClick={() => action(() => axios.post(`${API}/rfqs/${rfqId}/cancel`, { reason: "Dibatalkan dari panel" }), "RFQ dibatalkan.")} className="secondary-button text-red-600"><Ban size={13} /> Batalkan</button>
            )}
          </div>

          {/* Banding harga (matriks) */}
          <div>
            <h3 className="text-[12px] font-bold mb-2 flex items-center gap-1.5"><Award size={14} className="text-[#0058CC]" /> Perbandingan Harga</h3>
            <div className="overflow-x-auto border border-[#EFF0F2] rounded-md" data-testid="rfq-compare-matrix">
              <table className="w-full text-[11.5px]">
                <thead>
                  <tr className="bg-[#FAFBFC] text-[10px] uppercase text-[#6B6B73]">
                    <th className="text-left px-3 py-2">Item</th>
                    <th className="text-center px-2 py-2">Qty</th>
                    {(rfq.suppliers || []).map((s) => (
                      <th key={s.supplier_id} className="text-right px-3 py-2 min-w-[110px]">
                        {s.supplier_name}{s.quote_status === "quoted" ? "" : " (—)"}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(rfq.items || []).map((it) => (
                    <tr key={it.line_id} className="border-t border-[#F4F5F6]">
                      <td className="px-3 py-2"><p className="font-semibold">{it.sku}</p><p className="text-[10px] text-[#9A9BA3] truncate max-w-[160px]">{it.product_name}</p></td>
                      <td className="text-center px-2 py-2 tabular-nums"><QtyDual rolls={it.qty_rolls} measure={it.quantity} unit={it.unit} factor={it.unit_factor} factorTo={it.unit_factor_to} /></td>
                      {(rfq.suppliers || []).map((s) => {
                        const price = priceMap[s.supplier_id]?.[it.line_id];
                        const isLow = lowest[it.line_id]?.supplier_id === s.supplier_id;
                        return (
                          <td key={s.supplier_id} className={`text-right px-3 py-2 tabular-nums ${isLow ? "bg-[#E9F9EF] font-bold text-emerald-700" : ""}`}>
                            {price != null ? formatCurrency(price) : "—"}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  <tr className="border-t-2 border-[#EFF0F2] bg-[#FAFBFC]">
                    <td className="px-3 py-2 font-bold" colSpan={2}>Total Penawaran</td>
                    {(rfq.suppliers || []).map((s) => {
                      const t = compare?.suppliers?.find((x) => x.supplier_id === s.supplier_id);
                      const isRec = compare?.recommended_full_supplier_id === s.supplier_id;
                      return (
                        <td key={s.supplier_id} className="text-right px-3 py-2 tabular-nums font-bold" data-testid={`rfq-total-${s.supplier_id}`}>
                          {t ? formatCurrency(t.total) : "—"}
                          {isRec && <span className="ml-1 inline-flex items-center gap-0.5 text-[9px] text-emerald-600"><CheckCircle2 size={10} /> termurah</span>}
                        </td>
                      );
                    })}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Supplier + input penawaran */}
          <div>
            <h3 className="text-[12px] font-bold mb-2">Supplier Diundang</h3>
            <div className="space-y-1.5">
              {(rfq.suppliers || []).map((s) => (
                <div key={s.supplier_id} data-testid={`rfq-supplier-card-${s.supplier_id}`} className="flex items-center justify-between px-3 py-2 rounded-md border border-[#EFF0F2]">
                  <div>
                    <p className="text-[12px] font-semibold">{s.supplier_name} {s.quote_status === "quoted" && <span className="status-pill pill-success ml-1">Sudah menawar</span>}</p>
                    <p className="text-[10.5px] text-[#6B6B73]">{s.quote_status === "quoted" ? `Total ${formatCurrency(s.total)} · lead ${s.lead_time_days || 0} hari` : "Belum mengisi penawaran"}</p>
                  </div>
                  {["draft", "open"].includes(rfq.status) && canQuote && (
                    <button data-testid={`rfq-quote-btn-${s.supplier_id}`} onClick={() => openQuote(s)} className="secondary-button text-[11px]"><Pencil size={11} /> {s.quote_status === "quoted" ? "Ubah" : "Isi"} Penawaran</button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Form quote inline */}
          {quoteFor && (
            <div className="section-card !p-3 border-2 border-[#0058CC]" data-testid="rfq-quote-form">
              <p className="text-[12px] font-bold mb-2">Input Penawaran — {(rfq.suppliers.find((s) => s.supplier_id === quoteFor) || {}).supplier_name}</p>
              <div className="space-y-1.5">
                {(rfq.items || []).map((it) => (
                  <div key={it.line_id} className="grid grid-cols-[1fr_140px] items-center gap-2">
                    <span className="text-[11.5px]">{it.sku} × {it.quantity} {it.unit}</span>
                    <input type="number" data-testid={`rfq-quote-price-${it.line_id}`} value={quoteLines[it.line_id] || ""}
                      onChange={(e) => setQuoteLines((q) => ({ ...q, [it.line_id]: e.target.value }))}
                      className="field text-right" placeholder="Harga/unit" />
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-2 mt-2">
                <input type="number" value={quoteMeta.lead_time_days} onChange={(e) => setQuoteMeta((m) => ({ ...m, lead_time_days: e.target.value }))} className="field" placeholder="Lead time (hari)" />
                <input type="date" value={quoteMeta.valid_until} onChange={(e) => setQuoteMeta((m) => ({ ...m, valid_until: e.target.value }))} className="field" />
              </div>
              <div className="flex justify-end gap-2 mt-2">
                <button onClick={() => setQuoteFor(null)} className="secondary-button">Tutup</button>
                <button data-testid="rfq-quote-save" disabled={busy} onClick={submitQuote} className="primary-button">Simpan Penawaran</button>
              </div>
            </div>
          )}

          {/* Award */}
          {rfq.status === "open" && canAct && quotedSuppliers.length > 0 && (
            <div className="section-card !p-3 border border-emerald-300 bg-[#F6FEF9]" data-testid="rfq-award-section">
              <h3 className="text-[12px] font-bold mb-2 flex items-center gap-1.5"><Award size={14} className="text-emerald-600" /> Award → Buat PO</h3>
              <div className="flex gap-2 mb-2">
                <button data-testid="rfq-award-mode-full" onClick={() => setAwardMode("full")} className={`flex-1 py-1.5 rounded-md text-[11.5px] font-semibold border ${awardMode === "full" ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-[#EFF0F2] text-[#6B6B73]"}`}>Penuh (1 supplier)</button>
                <button data-testid="rfq-award-mode-line" onClick={() => setAwardMode("line")} className={`flex-1 py-1.5 rounded-md text-[11.5px] font-semibold border ${awardMode === "line" ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-[#EFF0F2] text-[#6B6B73]"}`}>Per-baris (split)</button>
              </div>
              {awardMode === "full" ? (
                <KNSelect value={fullSupplier} onValueChange={setFullSupplier}
                  options={quotedSuppliers.map((s) => ({ value: s.supplier_id, label: `${s.supplier_name} · ${formatCurrency(s.total)}` }))}
                  className="field" placeholder="Pilih supplier pemenang..." data-testid="rfq-award-full-select" />
              ) : (
                <div className="space-y-1.5">
                  {(rfq.items || []).map((it) => (
                    <div key={it.line_id} className="grid grid-cols-[1fr_220px] items-center gap-2">
                      <span className="text-[11.5px]">{it.sku} × {it.quantity}</span>
                      <KNSelect value={lineAwards[it.line_id] || ""} onValueChange={(v) => setLineAwards((l) => ({ ...l, [it.line_id]: v }))}
                        options={quotedSuppliers.filter((s) => priceMap[s.supplier_id]?.[it.line_id] != null)
                          .map((s) => ({ value: s.supplier_id, label: `${s.supplier_name} · ${formatCurrency(priceMap[s.supplier_id][it.line_id])}` }))}
                        className="field" placeholder="Pilih supplier..." data-testid={`rfq-award-line-${it.line_id}`} />
                    </div>
                  ))}
                </div>
              )}
              <div className="flex justify-end mt-2">
                <button data-testid="rfq-award-submit" disabled={busy} onClick={doAward} className="primary-button bg-emerald-600 hover:bg-emerald-700"><Award size={13} /> {busy ? "Memproses..." : "Award & Buat PO"}</button>
              </div>
            </div>
          )}

          {/* Hasil award */}
          {rfq.status === "awarded" && rfq.award && (
            <div className="section-card !p-3 border border-emerald-300 bg-[#F6FEF9]" data-testid="rfq-award-result">
              <p className="text-[12px] font-bold text-emerald-700 flex items-center gap-1.5"><CheckCircle2 size={14} /> RFQ di-award ({rfq.award.mode === "full" ? "Penuh" : "Per-baris"})</p>
              <p className="text-[11.5px] text-[#4A4B53] mt-1">PO dibuat: <span className="font-semibold">{(rfq.award.po_numbers || []).join(", ")}</span></p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusPill({ status }) {
  const map = { draft: ["pill-muted", "Draft"], open: ["pill-info", "Berjalan"], awarded: ["pill-success", "Awarded"], cancelled: ["pill-muted", "Batal"] };
  const [cls, label] = map[status] || ["pill-muted", status];
  return <span className={`status-pill ${cls}`}>{label}</span>;
}
