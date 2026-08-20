/**
 * MakloonOrderDetailPanel (M3) — detail order makloon + aksi lifecycle.
 * Issue bahan → WIP-at-vendor, Terima hasil (roll + LOT manual), costing, timeline, cancel.
 */
import { useCallback, useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import {
  ArrowLeft, Boxes, ArrowRight, PackageCheck, Send, XCircle, Plus, Trash2,
  Factory, Clock, Receipt, X, Save, Wallet, Layers, TriangleAlert, Wrench,
} from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import useProcessTypes from "../../hooks/useProcessTypes";
import { MATERIAL_FLOW_BADGE } from "../../constants/makloonVocab";
import KNSelect from "../../components/KNSelect";
import ConfirmModal from "../../components/ConfirmModal";
import DocumentActionsBar from "../documents/DocumentActionsBar";
import MakloonClaimPanel from "./makloon/MakloonClaimPanel";
import { recordService } from "./makloon/makloonApi";
import { MKO_STATUS } from "./MakloonOrdersView";
import { overlayDismiss } from "@/utils/overlayDismiss";
import QtyDual from "../../components/QtyDual";      // FASE U — dua satuan
import { uomSelectOptions } from "../../utils/uomCatalog";   // FASE U — satuan dari master
import useUomConversions from "../../hooks/useUomConversions";

const STEP_STATUS = {
  pending: { label: "Menunggu Issue", cls: "pill-muted" },
  issued: { label: "Di Makloon (WIP)", cls: "pill-info" },
  received: { label: "Diterima", cls: "pill-success" },
  cancelled: { label: "Batal", cls: "pill-danger" },
};
/** FASE T — langkah jasa murni tidak pernah "di makloon": kainnya tidak pergi. */
const stepStatusMeta = (s) => {
  const base = STEP_STATUS[s.status] || STEP_STATUS.pending;
  if (s.material_flow === "service_only" && s.status === "pending") {
    return { label: "Menunggu Catat Jasa", cls: "pill-muted" };
  }
  return base;
};
const fmtDT = (s) => (s ? new Date(s).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");

export default function MakloonOrderDetailPanel({ mkoId, currentUser, onBack, onError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [warehouses, setWarehouses] = useState([]);
  const [busy, setBusy] = useState(false);
  const [issueStep, setIssueStep] = useState(null);
  const [receiveStep, setReceiveStep] = useState(null);
  const [serviceStep, setServiceStep] = useState(null);   // FASE T — Catat Jasa
  const [showCancel, setShowCancel] = useState(false);
  const { labelOf: processLabel } = useProcessTypes();

  const canAct = ["admin", "manager", "warehouse"].includes(currentUser?.role);
  const canManage = ["admin", "manager"].includes(currentUser?.role);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/makloon-orders/${mkoId}`);
      setData(r.data);
    } catch (e) { onError?.(e.response?.data?.detail || "Gagal memuat order."); onBack?.(); }
    finally { setLoading(false); }
  }, [mkoId]); // eslint-disable-line
  useEffect(() => { load(); }, [load]);
  useEffect(() => { axios.get(`${API}/warehouses`).then((r) => setWarehouses(Array.isArray(r.data) ? r.data : [])).catch(() => {}); }, []);

  async function doIssue(step, whId, docUom, docQty) {
    setBusy(true);
    try {
      const body = { step_seq: step.seq, from_warehouse_id: whId };
      if (docUom && parseFloat(docQty) > 0) { body.doc_uom = docUom; body.doc_qty = parseFloat(docQty); }
      await axios.post(`${API}/makloon-orders/${mkoId}/issue`, body);
      setIssueStep(null); await load();
    } catch (e) { onError?.(e.response?.data?.detail || "Gagal issue ke makloon."); }
    finally { setBusy(false); }
  }
  async function doReceive(step, body) {
    setBusy(true);
    try {
      await axios.post(`${API}/makloon-orders/${mkoId}/receive`, { step_seq: step.seq, ...body });
      setReceiveStep(null); await load();
    } catch (e) { onError?.(e.response?.data?.detail || "Gagal terima hasil makloon."); throw e; }
    finally { setBusy(false); }
  }
  /**
   * FASE T — selesaikan langkah JASA MURNI (mis. pembuatan kasa/screen).
   * Tidak ada roll yang lahir dan qty kain tidak berubah; yang lahir hanya tagihan
   * mitra + jurnal WIP. Sengaja aksi TERPISAH dari "Terima Hasil": memakai satu tombol
   * untuk dua arti akan mengundang petugas mengisi "hasil" untuk pekerjaan yang tidak
   * menghasilkan kain.
   */
  async function doRecordService(step, body) {
    setBusy(true);
    try {
      await recordService(mkoId, { step_seq: step.seq, ...body });
      setServiceStep(null); await load();
    } catch (e) { onError?.(e.response?.data?.detail || "Gagal mencatat jasa langkah ini."); throw e; }
    finally { setBusy(false); }
  }
  async function doCancel() {
    setBusy(true);
    try { await axios.post(`${API}/makloon-orders/${mkoId}/cancel`, { reason: "Dibatalkan dari detail" }); setShowCancel(false); await load(); }
    catch (e) { onError?.(e.response?.data?.detail || "Gagal membatalkan order."); setShowCancel(false); }
    finally { setBusy(false); }
  }

  if (loading && !data) return <div className="section-card py-12 text-center text-[12px] text-[#6B6B73]" data-testid="mko-detail-loading">Memuat pesanan…</div>;
  if (!data) return null;
  const st = MKO_STATUS[data.status] || MKO_STATUS.draft;
  const c = data.costing || {};
  const canCancel = canManage && !["completed", "cancelled"].includes(data.status) && !(data.steps || []).some((s) => s.status === "received");

  return (
    <div data-testid="mko-detail-panel">
      <div className="mb-3 flex items-center justify-between">
        <button data-testid="mko-detail-back" onClick={onBack} className="secondary-button"><ArrowLeft size={13} /> Kembali</button>
        {canCancel && <button data-testid="mko-cancel-button" onClick={() => setShowCancel(true)} className="secondary-button !text-[#C0392B] !border-[#F3C6BF]"><XCircle size={13} /> Batalkan Pesanan</button>}
      </div>

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Boxes size={17} className="text-[#0058CC]" />
              <h2 className="truncate" data-testid="mko-detail-number">{data.mko_number}</h2>
              <span className={`status-pill ${st.cls}`} data-testid="mko-detail-status">{st.label}</span>
              <span className="rounded-full bg-[#F3F4F6] px-2 py-0.5 text-[10.5px] font-semibold text-[#6B6B73]">{data.mode === "buy_process" ? "Beli + Proses" : "Proses Saja"}</span>
              {data.po_number && <span className="rounded-full bg-[#EAF2FF] px-2 py-0.5 text-[10.5px] font-semibold text-[#0058CC]">PO {data.po_number}</span>}
            </div>
            <p className="mt-1 text-[11.5px] text-[#6B6B73] flex items-center gap-1.5">{data.material_name} <ArrowRight size={11} /> {data.final_output_name || "—"} · {formatQty(data.material_qty)} {data.material_unit}</p>
          </div>
        </div>
        <div className="section-body">
          <DocumentActionsBar docType="makloon_spk" sourceId={data.id} entityId={data.entity_id}
            number={data.mko_number} label="SPK Makloon" esignable currentUser={currentUser} onChanged={load} />
        </div>
      </div>

      {/* FASE T (keputusan 3b) — peringatan yang tidak memblokir TETAP terlihat di sini.
          Peringatan itu tersimpan di dokumen saat SPK lahir; kalau hanya muncul sebagai
          toast di layar pembuatnya, petugas yang MENGERJAKAN SPK tak pernah melihatnya. */}
      {(data.warnings || []).length > 0 && (
        <div className="mb-3 rounded-lg border border-[#F5D9A8] bg-[#FFF8EC] px-3 py-2"
          data-testid="mko-detail-warnings">
          <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase text-[#8C4A00]">
            <TriangleAlert size={12} /> Perhatian pada SPK ini
          </p>
          <ul className="mt-1 space-y-1 text-[11.5px] text-[#8C4A00]">
            {data.warnings.map((w, i) => (
              <li key={`ow${i}`} data-testid={`mko-detail-warning-${i}`}>• {w}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-[300px_1fr]">
        {/* Ringkasan & Costing */}
        <div className="space-y-3">
          <div className="section-card">
            <div className="section-head"><h3 className="text-[12.5px] font-bold flex items-center gap-2"><Wallet size={14} className="text-[#0058CC]" /> Costing (HPP)</h3></div>
            <div className="section-body grid grid-cols-2 gap-2" data-testid="mko-costing">
              <Kpi label="Biaya Bahan" value={formatCurrency(c.material_cost || 0)} />
              <Kpi label="Ongkos Jasa" value={formatCurrency(c.service_cost || 0)} />
              <Kpi label="Bahan Pembantu" value={formatCurrency(c.aux_cost || 0)} />
              <Kpi label="HPP Output" value={formatCurrency(c.hpp_output || 0)} tone="#0058CC" />
              <Kpi label="HPP / Unit" value={formatCurrency(c.hpp_per_unit || 0)} tone="#1B7F4B" />
              <Kpi label="Est. Output" value={formatQty(data.forecast?.expected_finished_qty || 0)} />
            </div>
          </div>
          {/* FASE D (PS-04) — HPP BERJENJANG per langkah */}
          {(c.steps || []).length > 0 && (
            <div className="section-card">
              <div className="section-head"><h3 className="text-[12.5px] font-bold flex items-center gap-2"><Factory size={14} className="text-[#0058CC]" /> HPP Berjenjang</h3></div>
              <div className="section-body">
                <table className="w-full text-[11px]" data-testid="mko-tiered-costing">
                  <thead>
                    <tr className="text-left text-[9.5px] uppercase text-[#6B6B73]">
                      <th className="py-1">Lgk</th><th>Proses</th><th className="text-right">Hasil</th><th className="text-right">HPP/unit</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#EFF0F2]">
                    {(c.steps || []).map((cs) => (
                      <tr key={cs.seq} data-testid={`mko-costing-step-${cs.seq}`}>
                        <td className="py-1.5">{cs.seq}</td>
                        <td className="truncate">{cs.process_type}<br /><span className="text-[9.5px] text-[#9A9BA3]">{cs.makloon_name}</span></td>
                        <td className="text-right tabular-nums">{formatQty(cs.actual_output_qty || cs.expected_output_qty || 0)} {cs.output_unit}</td>
                        <td className="text-right tabular-nums font-semibold">{formatCurrency(cs.hpp_per_unit || 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          <div className="section-card">
            <div className="section-head"><h3 className="text-[12.5px] font-bold flex items-center gap-2"><Clock size={14} className="text-[#0058CC]" /> Riwayat</h3></div>
            <div className="section-body">
              <ol className="space-y-2" data-testid="mko-timeline">
                {(data.timeline || []).map((t, i) => (
                  <li key={i} className="flex gap-2 text-[11px]">
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[#0058CC]" />
                    <div><p className="font-medium text-[#1C1C1E]">{t.note || t.event}</p><p className="text-[10px] text-[#9A9BA3]">{fmtDT(t.at)}</p></div>
                  </li>
                ))}
                {(data.timeline || []).length === 0 && <p className="text-[11px] text-[#9A9BA3]">Belum ada aktivitas.</p>}
              </ol>
            </div>
          </div>
          {(data.service_bills || []).length > 0 && (
            <div className="section-card">
              <div className="section-head"><h3 className="text-[12.5px] font-bold flex items-center gap-2"><Receipt size={14} className="text-[#0058CC]" /> Tagihan Jasa</h3></div>
              <div className="section-body divide-y divide-[#EFF0F2]" data-testid="mko-service-bills">
                {data.service_bills.map((b) => (
                  <div key={b.id} className="flex items-center justify-between py-1.5 text-[11.5px]">
                    <div><p className="font-semibold">{b.bill_number}</p><p className="text-[10px] text-[#6B6B73]">{b.supplier_name} · step {b.step_seq}</p></div>
                    <span className="tabular-nums font-semibold">{formatCurrency(b.grand_total || 0)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Steps */}
        <div className="section-card self-start">
          <div className="section-head"><h3 className="text-[12.5px] font-bold flex items-center gap-2"><Factory size={14} className="text-[#0058CC]" /> Langkah Proses</h3></div>
          <div className="section-body space-y-2.5">
            {(data.steps || []).map((s, idx) => {
              const ss = stepStatusMeta(s);
              const prevReceived = idx === 0 || (data.steps[idx - 1]?.status === "received");
              // FASE T — aliran kain menentukan AKSI: `service_only` diselesaikan lewat
              // "Catat Jasa" (kain tidak keluar gudang), sisanya lewat Issue → Terima.
              const serviceOnly = s.material_flow === "service_only";
              const noTransform = s.changes_stage === false;
              return (
                <div key={s.seq} data-testid={`mko-step-${s.seq}`} className="rounded-lg border border-[#EFF0F2] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[12px] font-semibold flex items-center gap-1.5">
                        <span className="rounded bg-[#EAF2FF] px-1.5 text-[10.5px] font-bold text-[#0058CC]">Langkah {s.seq}</span>
                        {s.stage_label || processLabel(s.process_type)} · {s.makloon_name || "—"}
                      </p>
                      <p className="mt-0.5 text-[10.5px] text-[#6B6B73] flex items-center gap-1">
                        {s.input_name || s.input_sku}
                        {noTransform ? (
                          <span className="text-[#6B219A]">· kain tetap (tidak berubah)</span>
                        ) : (
                          <><ArrowRight size={10} /> {s.output_name || s.output_sku || "—"}</>
                        )}
                      </p>
                    </div>
                    <span className={`status-pill ${ss.cls}`}>{ss.label}</span>
                  </div>
                  {/* FASE T — arti tahap terlihat di kartu: kain berubah? kain dikirim? */}
                  {(s.stage_code || s.material_flow) && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px]"
                      data-testid={`mko-step-stage-${s.seq}`}>
                      <Layers size={11} className="text-[#6B219A]" />
                      {s.stage_code && (
                        <span className="rounded bg-[#F3E9FA] px-1.5 py-0.5 font-semibold text-[#6B219A]">
                          Tahap {s.stage_code}
                        </span>
                      )}
                      <span className={`rounded px-1.5 py-0.5 font-semibold ${
                        noTransform ? "bg-[#F3E9FA] text-[#6B219A]" : "bg-[#EAF2FF] text-[#0058CC]"}`}
                        data-testid={`mko-step-transform-${s.seq}`}>
                        {noTransform ? "Tidak mengubah kain" : "Mengubah tahap kain"}
                      </span>
                      {s.material_flow && (
                        <span className="rounded bg-[#F3F4F6] px-1.5 py-0.5 font-semibold text-[#3C3C43]"
                          data-testid={`mko-step-flow-${s.seq}`}>
                          {MATERIAL_FLOW_BADGE[s.material_flow] || s.material_flow}
                        </span>
                      )}
                    </div>
                  )}
                  <div className="mt-2 grid grid-cols-3 gap-2 text-[11px]">
                    <MiniStat label="Input" node={<QtyDual rolls={s.qty_rolls} measure={s.input_qty} unit={s.input_unit || ""} compact />} />
                    <MiniStat label={s.status === "received" ? "Output Aktual" : "Est. Output"} node={<QtyDual rolls={s.status === "received" ? s.qty_rolls_out : null} measure={s.status === "received" ? s.actual_output_qty : s.expected_output_qty} unit={s.output_unit || ""} compact />} />
                    <MiniStat label={s.status === "received" ? "Sisa Aktual" : "Est. Sisa"} value={formatQty(s.status === "received" ? s.actual_byproduct_qty : s.expected_byproduct_qty)} />
                  </div>
                  {s.status === "issued" && <p className="mt-1.5 text-[10.5px] text-[#0058CC]">Di makloon: <b>{formatQty(s.subcon_qty)} {s.input_unit}</b> · nilai bahan {formatCurrency(s.material_value)}</p>}
                  {s.status === "received" && (
                    <div className="mt-1.5 text-[10.5px] text-[#6B6B73]">
                      HPP output: <b className="text-[#0058CC]">{formatCurrency(s.output_value)}</b>
                      {s.actual_byproduct_qty > 0 && <> · sisa {formatQty(s.actual_byproduct_qty)} {s.input_unit} (kredit {formatCurrency(s.byproduct_value || 0)})</>}
                      <br />Roll: {(s.lots || []).map((l) => `${l.lot} (${formatQty(l.length)})`).join(", ") || "—"}
                      {s.receive_uom_trail && (
                        <><br />Dokumen mitra: {formatQty(s.receive_uom_trail.doc_qty)} {s.receive_uom_trail.doc_uom} → {formatQty(s.receive_uom_trail.base_qty)} {s.receive_uom_trail.base_uom} (faktor {s.receive_uom_trail.factor})</>
                      )}
                    </div>
                  )}
                  {/* FASE D — dasar perhitungan (kontrak · susut · tarif) terlihat & bisa diaudit */}
                  <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]" data-testid={`mko-step-basis-${s.seq}`}>
                    {s.contract_number && <span className="rounded bg-[#EAF2FF] px-1.5 py-0.5 font-semibold text-[#0058CC]">Kontrak {s.contract_number}</span>}
                    {s.tariff_basis && <span className="rounded bg-[#F3F4F6] px-1.5 py-0.5 font-semibold text-[#3C3C43]">Basis tarif: {s.tariff_basis}</span>}
                    <span className="rounded bg-[#F3F4F6] px-1.5 py-0.5 text-[#3C3C43]">Susut {formatQty(s.shrinkage_pct ?? s.waste_pct ?? 0)}% ({s.shrinkage_source || "—"})</span>
                    <span className="rounded bg-[#F3F4F6] px-1.5 py-0.5 text-[#3C3C43]">Toleransi {formatQty(s.tolerance_pct ?? 0)}%</span>
                    {s.tariff > 0 && <span className="rounded bg-[#E6F4EA] px-1.5 py-0.5 font-semibold text-[#1B7F4B]">Ongkos {formatCurrency(s.tariff)}</span>}
                  </div>
                  {(s.estimate?.explain?.length > 0 || s.tariff_actual?.explain?.length > 0) && (
                    <details className="mt-1.5" data-testid={`mko-step-explain-${s.seq}`}>
                      <summary className="cursor-pointer text-[10.5px] font-semibold text-[#0058CC]">Lihat rumus & angka antara</summary>
                      <ul className="mt-1 space-y-0.5 text-[10.5px] text-[#3C3C43]">
                        {(s.estimate?.explain || []).map((l, i) => <li key={`e${i}`}>• {l}</li>)}
                        {((s.tariff_actual || s.tariff_plan)?.explain || []).map((l, i) => <li key={`t${i}`} className="text-[#1B7F4B]">• {l}</li>)}
                      </ul>
                    </details>
                  )}
                  {s.status === "received" && (
                    <MakloonClaimPanel mkoId={mkoId} step={s} currentUser={currentUser}
                      onDone={load} onError={onError} />
                  )}
                  {canAct && s.status === "pending" && prevReceived && !serviceOnly && (
                    <button data-testid={`issue-step-${s.seq}`} onClick={() => setIssueStep(s)} className="primary-button mt-2 !py-1.5 text-[11.5px]"><Send size={12} /> Issue ke Makloon</button>
                  )}
                  {/* FASE T — langkah jasa murni: kain TIDAK boleh bergerak, jadi tombolnya
                      "Catat Jasa". Dulu petugas hanya melihat "Issue ke Makloon", menekannya,
                      lalu ditolak 409 tanpa jalan keluar. */}
                  {canAct && s.status === "pending" && prevReceived && serviceOnly && (
                    <div className="mt-2">
                      <button data-testid={`record-service-step-${s.seq}`} onClick={() => setServiceStep(s)}
                        className="primary-button !py-1.5 text-[11.5px]">
                        <Wrench size={12} /> Catat Jasa
                      </button>
                      <p className="mt-1 text-[10.5px] text-[#6B6B73]">
                        Kain tidak dikeluarkan dari gudang — yang dicatat hanya biaya jasa
                        mitra. Tidak ada roll baru yang lahir.
                      </p>
                    </div>
                  )}
                  {canAct && s.status === "pending" && !prevReceived && (
                    <p className="mt-2 text-[10.5px] text-[#9A9BA3]">Menunggu langkah sebelumnya diterima.</p>
                  )}
                  {canAct && s.status === "issued" && (
                    <button data-testid={`receive-step-${s.seq}`} onClick={() => setReceiveStep(s)} className="primary-button mt-2 !py-1.5 text-[11.5px]"><PackageCheck size={12} /> Terima Hasil</button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {issueStep && <IssueModal step={issueStep} warehouses={warehouses} defaultWh={data.from_warehouse_id} busy={busy}
        onClose={() => setIssueStep(null)} onConfirm={(wh, docUom, docQty) => doIssue(issueStep, wh, docUom, docQty)} />}
      {receiveStep && <ReceiveModal step={receiveStep} warehouses={warehouses} defaultWh={data.target_warehouse_id || data.from_warehouse_id}
        mkoNumber={data.mko_number} busy={busy} onClose={() => setReceiveStep(null)} onConfirm={(body) => doReceive(receiveStep, body)} />}
      {serviceStep && <RecordServiceModal step={serviceStep} mkoNumber={data.mko_number} busy={busy}
        onClose={() => setServiceStep(null)} onConfirm={(body) => doRecordService(serviceStep, body)} />}
      <ConfirmModal open={showCancel} title={`Batalkan ${data.mko_number}?`}
        message="Bahan yang sudah di-issue akan dikembalikan ke stok tersedia (jurnal dibalik)."
        confirmLabel="Batalkan Pesanan" danger onConfirm={doCancel} onCancel={() => setShowCancel(false)} testId="mko-cancel-modal" />
    </div>
  );
}

function IssueModal({ step, warehouses, defaultWh, busy, onClose, onConfirm }) {
  const [wh, setWh] = useState(defaultWh || (warehouses[0]?.id || ""));
  const [docUom, setDocUom] = useState("");
  const [docQty, setDocQty] = useState("");
  // Memuat katalog satuan (dan membagikannya ke penyimpan modul). Dipanggil DI SINI,
  // bukan mengandalkan layar lain sudah memanggilnya: pemilih yang bergantung pada
  // urutan kunjungan layar akan tampak "hanya berisi satu pilihan" secara acak.
  const { loading: uomLoading } = useUomConversions();
  const opts = warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }));
  // FASE U — satuan surat jalan mitra dari MASTER satuan. Dulu 7 nilai diketik di
  // sini; satuan yang ditambah pemilik (mis. `panel`) tidak pernah bisa dipilih,
  // sehingga penerimaan hasil makloon dalam satuan itu harus dikonversi manual di
  // kepala petugas — tempat kesalahan paling mahal dan paling tak terlacak.
  const uomOpts = [
    { value: "", label: uomLoading ? "Memuat satuan…" : `Pakai satuan sistem (${step.input_unit || "unit"})` },
    ...uomSelectOptions({ dimensions: ["length", "weight", "count"],
      extra: [step.input_unit].filter(Boolean) }),
  ];

  return (
    <div data-testid="mko-issue-modal" className="fixed inset-0 z-[170] flex items-center justify-center bg-black/50 p-4" {...overlayDismiss(onClose)}>
      <div className="w-full max-w-[460px] rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="text-[15px] font-bold flex items-center gap-2"><Send size={16} className="text-[#0058CC]" /> Issue Bahan ke Makloon</h2>
          <button className="icon-button" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="space-y-3 p-4">
          <p className="text-[12px] text-[#3C3C43]">Keluarkan <b>{formatQty(step.input_qty)} {step.input_unit}</b> {step.input_name} ke <b>{step.makloon_name}</b>. Stok berpindah ke bucket <b>Di Makloon (WIP-Vendor)</b>.</p>
          <label className="block"><span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">Gudang Sumber Bahan</span>
            <KNSelect data-testid="mko-issue-warehouse" className="field" value={wh} onValueChange={setWh} options={opts} /></label>
          <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
            <p className="mb-1.5 text-[10.5px] font-semibold text-[#6B6B73]">Satuan surat jalan mitra (opsional — sistem mengonversi & menyimpan jejaknya)</p>
            <div className="grid grid-cols-2 gap-2">
              <KNSelect data-testid="mko-issue-doc-uom" className="field" value={docUom} onValueChange={setDocUom} options={uomOpts} />
              <input data-testid="mko-issue-doc-qty" className="field" value={docQty} onChange={(e) => setDocQty(e.target.value)}
                placeholder="Qty sesuai dokumen mitra" disabled={!docUom} />
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button data-testid="mko-issue-confirm" className="primary-button" disabled={busy || !wh} onClick={() => onConfirm(wh, docUom, docQty)}><Send size={13} /> {busy ? "Memproses…" : "Issue Sekarang"}</button>
        </div>
      </div>
    </div>
  );
}

function ReceiveModal({ step, warehouses, defaultWh, mkoNumber, busy, onClose, onConfirm }) {
  const [outQty, setOutQty] = useState(String(step.expected_output_qty || ""));
  const [byQty, setByQty] = useState(String(step.expected_byproduct_qty || 0));
  const [tariff, setTariff] = useState("");
  const [aux, setAux] = useState(String(step.aux_cost || 0));
  const [ppn, setPpn] = useState("0");
  const [wh, setWh] = useState(defaultWh || (warehouses[0]?.id || ""));
  const [invNo, setInvNo] = useState("");
  const [docUom, setDocUom] = useState("");
  const [docQty, setDocQty] = useState("");
  const [colors, setColors] = useState(String(step.colors || ""));
  const [repeats, setRepeats] = useState(String(step.repeats || ""));
  const [rolls, setRolls] = useState([{ lot: `${step.output_sku || "OUT"}-${mkoNumber}-1`, length: String(step.expected_output_qty || ""), grade: "A", dye_lot: "" }]);
  const [err, setErr] = useState("");
  const whOpts = warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` }));
  // FASE U — satuan dari MASTER (lihat alasan di `IssueModal`).
  useUomConversions();
  const uomOpts = [
    { value: "", label: `Satuan sistem (${step.output_unit || "unit"})` },
    ...uomSelectOptions({ dimensions: ["length", "weight", "count"],
      extra: [step.output_unit].filter(Boolean) }),
  ];

  const totalRolls = rolls.reduce((a, r) => a + (parseFloat(r.length) || 0), 0);
  const setRoll = (i, k, v) => setRolls((p) => p.map((r, idx) => (idx === i ? { ...r, [k]: v } : r)));
  const usingDoc = Boolean(docUom) && parseFloat(docQty) > 0;

  const submit = async () => {
    setErr("");
    const oq = parseFloat(outQty) || 0;
    if (!usingDoc && oq <= 0) { setErr("Qty output harus > 0."); return; }
    if (rolls.some((r) => !r.lot.trim())) { setErr("Setiap roll wajib punya nomor LOT."); return; }
    if (!usingDoc && Math.abs(totalRolls - oq) > 0.5) { setErr(`Total panjang roll (${formatQty(totalRolls)}) harus = qty output (${formatQty(oq)}).`); return; }
    try {
      const body = {
        actual_output_qty: usingDoc ? 0 : oq, actual_byproduct_qty: parseFloat(byQty) || 0,
        tariff: parseFloat(tariff) || 0, aux_cost: parseFloat(aux) || 0, ppn: parseFloat(ppn) || 0,
        output_warehouse_id: wh, supplier_invoice_no: invNo,
        colors: parseInt(colors, 10) || 0, repeats: parseInt(repeats, 10) || 0,
        byproduct_lot: `SISA-${mkoNumber}-${step.seq}`,
        rolls: rolls.map((r) => ({ lot: r.lot.trim(), length: parseFloat(r.length) || 0, grade: r.grade || "A", dye_lot: (r.dye_lot || "").trim() })),
      };
      if (usingDoc) { body.output_uom = docUom; body.output_doc_qty = parseFloat(docQty); }
      await onConfirm(body);
    } catch (e) { /* error already surfaced */ }
  };

  return (
    <div data-testid="mko-receive-modal" className="fixed inset-0 z-[170] flex items-center justify-center bg-black/50 p-4" {...overlayDismiss(onClose)}>
      <div className="flex max-h-[92vh] w-full max-w-[620px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="text-[15px] font-bold flex items-center gap-2"><PackageCheck size={16} className="text-[#0058CC]" /> Terima Hasil Makloon</h2>
          <button className="icon-button" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {err && <div data-testid="mko-receive-error" className="rounded-lg bg-[#FDEDE7] px-3 py-2 text-[11.5px] text-[#C0392B]">{err}</div>}
          <div className="rounded-lg border border-[#DCE9FF] bg-[#F5F9FF] px-3 py-2 text-[11.5px] text-[#0058CC]">
            Estimasi sistem: <b>{formatQty(step.expected_output_qty)} {step.output_unit}</b>
            {step.tolerance_pct != null && <> · toleransi selisih <b>{step.tolerance_pct}%</b></>}
            {step.contract_number && <> · kontrak <b>{step.contract_number}</b> (ongkos jasa dihitung otomatis bila dikosongkan)</>}
          </div>
          <div className="grid grid-cols-3 gap-3">
            <FieldR label={`Qty Output (${step.output_unit || "unit"})`}><input data-testid="mko-recv-output-qty" type="number" className="field" value={outQty} onChange={(e) => setOutQty(e.target.value)} disabled={usingDoc} /></FieldR>
            <FieldR label={`Qty Barang Sisa (${step.input_unit || "unit"})`}><input data-testid="mko-recv-byproduct-qty" type="number" className="field" value={byQty} onChange={(e) => setByQty(e.target.value)} /></FieldR>
            <FieldR label="Gudang Terima"><KNSelect data-testid="mko-recv-warehouse" className="field" value={wh} onValueChange={setWh} options={whOpts} /></FieldR>
            <FieldR label="Ongkos Jasa (kosong = dari kontrak)"><input data-testid="mko-recv-tariff" type="number" className="field" value={tariff} onChange={(e) => setTariff(e.target.value)} placeholder="otomatis" /></FieldR>
            <FieldR label="Bahan Pembantu (Rp)"><input data-testid="mko-recv-aux" type="number" className="field" value={aux} onChange={(e) => setAux(e.target.value)} /></FieldR>
            <FieldR label="PPN (Rp)"><input data-testid="mko-recv-ppn" type="number" className="field" value={ppn} onChange={(e) => setPpn(e.target.value)} /></FieldR>
            <FieldR label="Jumlah warna (screen)"><input data-testid="mko-recv-colors" type="number" className="field" value={colors} onChange={(e) => setColors(e.target.value)} /></FieldR>
            <FieldR label="Jumlah repeat"><input data-testid="mko-recv-repeats" type="number" className="field" value={repeats} onChange={(e) => setRepeats(e.target.value)} /></FieldR>
            <FieldR label="No. Faktur Makloon"><input data-testid="mko-recv-invoice" className="field" value={invNo} onChange={(e) => setInvNo(e.target.value)} placeholder="mis. INV-MKL-001" /></FieldR>
          </div>

          <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
            <p className="mb-1.5 text-[10.5px] font-semibold text-[#6B6B73]">Laporan mitra dalam satuan lain (mis. kg untuk kain rajut) — sistem mengonversi & menyimpan jejaknya</p>
            <div className="grid grid-cols-2 gap-2">
              <KNSelect data-testid="mko-recv-doc-uom" className="field" value={docUom} onValueChange={setDocUom} options={uomOpts} />
              <input data-testid="mko-recv-doc-qty" className="field" value={docQty} onChange={(e) => setDocQty(e.target.value)}
                placeholder="Qty sesuai dokumen mitra" disabled={!docUom} />
            </div>
            {usingDoc && <p className="mt-1 text-[10.5px] text-[#B26A00]">Qty output diambil dari hasil konversi — pastikan total panjang roll sama dengan hasil konversi.</p>}
          </div>

          <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase text-[#6B6B73]">Roll Output (LOT manual wajib)</p>
              <button data-testid="mko-recv-add-roll" type="button" className="secondary-button !py-1 !px-2 text-[11px]" onClick={() => setRolls((p) => [...p, { lot: `${step.output_sku || "OUT"}-${mkoNumber}-${p.length + 1}`, length: "", grade: "A", dye_lot: "" }])}><Plus size={12} /> Roll</button>
            </div>
            <div className="space-y-1.5" data-testid="mko-recv-rolls">
              {rolls.map((r, i) => (
                <div key={i} className="grid grid-cols-[1.4fr_0.9fr_0.7fr_1fr_auto] items-center gap-1.5">
                  <input data-testid={`mko-recv-roll-lot-${i}`} className="field !py-1.5 text-[11.5px]" placeholder="No. LOT" value={r.lot} onChange={(e) => setRoll(i, "lot", e.target.value)} />
                  <input data-testid={`mko-recv-roll-len-${i}`} type="number" className="field !py-1.5 text-[11.5px]" placeholder="Panjang" value={r.length} onChange={(e) => setRoll(i, "length", e.target.value)} />
                  <input className="field !py-1.5 text-[11.5px]" placeholder="Grade" value={r.grade} onChange={(e) => setRoll(i, "grade", e.target.value)} />
                  <input data-testid={`mko-recv-roll-dyelot-${i}`} className="field !py-1.5 text-[11.5px]" placeholder="Dye lot" value={r.dye_lot} onChange={(e) => setRoll(i, "dye_lot", e.target.value)} />
                  <button type="button" className="icon-button text-red-400 hover:text-red-600" disabled={rolls.length <= 1} onClick={() => setRolls((p) => p.filter((_, idx) => idx !== i))}><Trash2 size={13} /></button>
                </div>
              ))}
            </div>
            <p className={`mt-1.5 text-[10.5px] ${!usingDoc && Math.abs(totalRolls - (parseFloat(outQty) || 0)) > 0.5 ? "text-[#C0392B]" : "text-[#1B7F4B]"}`}>Total roll: {formatQty(totalRolls)} {usingDoc ? "(harus = hasil konversi)" : `/ output ${formatQty(parseFloat(outQty) || 0)}`}</p>
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button data-testid="mko-receive-confirm" className="primary-button" disabled={busy} onClick={submit}><Save size={13} /> {busy ? "Memproses…" : "Terima & Catat"}</button>
        </div>
      </div>
    </div>
  );
}

/**
 * RecordServiceModal (FASE T) — selesaikan langkah JASA MURNI.
 *
 * Sengaja TIDAK punya kolom "qty hasil" maupun daftar roll: tidak ada kain baru yang
 * lahir dan qty kainnya tidak berubah (diambil dari `input_qty` langkah). Menyediakan
 * kolom itu akan mengundang petugas "mengisi hasil" untuk pekerjaan yang tidak
 * menghasilkan kain, lalu selisih palsu muncul di klaim.
 */
function RecordServiceModal({ step, mkoNumber, busy, onClose, onConfirm }) {
  const [tariff, setTariff] = useState("");
  const [aux, setAux] = useState(String(step.aux_cost || 0));
  const [ppn, setPpn] = useState("0");
  const [invNo, setInvNo] = useState("");
  const [colors, setColors] = useState(String(step.colors || ""));
  const [repeats, setRepeats] = useState(String(step.repeats || ""));
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");

  const submit = async () => {
    setErr("");
    if (!step.makloon_id) {
      setErr("Mitra makloon belum dipilih untuk langkah ini — tagihan jasa tidak punya "
        + "pemilik. Pilih mitranya lebih dulu (Pengaturan → Mitra Makloon bila belum ada).");
      return;
    }
    try {
      await onConfirm({
        tariff: parseFloat(tariff) || 0,
        aux_cost: parseFloat(aux) || 0,
        ppn: parseFloat(ppn) || 0,
        supplier_invoice_no: invNo,
        colors: parseInt(colors, 10) || 0,
        repeats: parseInt(repeats, 10) || 0,
        note,
      });
    } catch (e) {
      // Galat aksi tampil DI DALAM pop-up ini; bilah halaman tertutup pop-up sendiri.
      setErr(e.response?.data?.detail || "Gagal mencatat jasa langkah ini.");
    }
  };

  return (
    <div data-testid="mko-service-modal" className="fixed inset-0 z-[170] flex items-center justify-center bg-black/50 p-4" {...overlayDismiss(onClose)}>
      <div className="flex max-h-[92vh] w-full max-w-[560px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="text-[15px] font-bold flex items-center gap-2">
            <Wrench size={16} className="text-[#6B219A]" /> Catat Jasa — {step.stage_label || step.stage_code || "langkah jasa"}
          </h2>
          <button className="icon-button" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {err && <div data-testid="mko-service-error" className="rounded-lg bg-[#FDEDE7] px-3 py-2 text-[11.5px] text-[#C0392B]">{err}</div>}
          <div className="rounded-lg border border-[#E8D6F5] bg-[#FBF5FF] px-3 py-2 text-[11.5px] text-[#6B219A]">
            Tahap ini <b>tidak mengubah kain</b>. {formatQty(step.input_qty)} {step.input_unit} {step.input_name}
            {" "}tetap di gudang — tidak ada roll baru, tidak ada perpindahan stok.
            Yang lahir: <b>tagihan jasa {step.makloon_name || "mitra"}</b> + jurnal WIP.
          </div>
          <div className="grid grid-cols-3 gap-3">
            <FieldR label="Ongkos Jasa (kosong = dari kontrak/basis)">
              <input data-testid="mko-service-tariff" type="number" className="field" value={tariff}
                onChange={(e) => setTariff(e.target.value)} placeholder="otomatis" />
            </FieldR>
            <FieldR label="Biaya Lain (Rp)">
              <input data-testid="mko-service-aux" type="number" className="field" value={aux}
                onChange={(e) => setAux(e.target.value)} />
            </FieldR>
            <FieldR label="PPN (Rp)">
              <input data-testid="mko-service-ppn" type="number" className="field" value={ppn}
                onChange={(e) => setPpn(e.target.value)} />
            </FieldR>
            <FieldR label="Jumlah warna (kasa per warna)">
              <input data-testid="mko-service-colors" type="number" className="field" value={colors}
                onChange={(e) => setColors(e.target.value)} />
            </FieldR>
            <FieldR label="Jumlah repeat">
              <input data-testid="mko-service-repeats" type="number" className="field" value={repeats}
                onChange={(e) => setRepeats(e.target.value)} />
            </FieldR>
            <FieldR label="No. Faktur Mitra">
              <input data-testid="mko-service-invoice" className="field" value={invNo}
                onChange={(e) => setInvNo(e.target.value)} placeholder={`mis. INV-KASA-${step.seq}`} />
            </FieldR>
          </div>
          <FieldR label="Catatan (opsional)">
            <input data-testid="mko-service-note" className="field" value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={`mis. 3 kasa motif untuk ${mkoNumber}`} />
          </FieldR>
          {step.tariff_basis && (
            <p className="text-[10.5px] text-[#6B6B73]">
              Basis tarif langkah ini: <b>{step.tariff_basis}</b>
              {step.contract_number && <> · kontrak <b>{step.contract_number}</b></>}
              {" "}— kosongkan ongkos jasa agar dihitung sistem.
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button data-testid="mko-service-confirm" className="primary-button" disabled={busy} onClick={submit}>
            <Save size={13} /> {busy ? "Memproses…" : "Catat Jasa & Terbitkan Tagihan"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, sub, tone = "#1C1C1E" }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2">
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="text-[13.5px] font-bold tabular-nums leading-tight" style={{ color: tone }}>{value}</p>
      {sub && <p className="text-[9.5px] text-[#9A9BA3]">{sub}</p>}
    </div>
  );
}
function MiniStat({ label, value, node = null }) {
  // FASE U — `node` dipakai bila nilainya komponen (mis. <QtyDual/> dua satuan);
  // `value` (teks) tetap didukung supaya pemanggil lama tidak berubah.
  return <div><p className="text-[9.5px] font-semibold uppercase text-[#9A9BA3]">{label}</p><p className="text-[11.5px] font-semibold tabular-nums">{node || value}</p></div>;
}
function FieldR({ label, children }) {
  return <label className="block"><span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">{label}</span>{children}</label>;
}
