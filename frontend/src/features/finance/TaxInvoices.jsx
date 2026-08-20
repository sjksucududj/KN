import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { can } from "../../config/roles";
import { FileText, RefreshCw, Search, Printer, Hash, Copy, Ban } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import DocumentActionsBar from "../documents/DocumentActionsBar";
import { overlayDismiss } from "@/utils/overlayDismiss";

/**
 * Faktur Pajak Jual (Sub-fase 1.9 — tax_invoices / fkt_).
 * List + kelola Faktur Pajak: isi NSFP resmi, terbitkan PENGGANTI, BATALKAN, cetak dokumen.
 * Penerbitan awal dilakukan dari Order detail (manual, opsional). Respons BE = bare object/array.
 */
const FILTERS = [
  { id: "all", label: "Semua" },
  { id: "normal", label: "Normal" },
  { id: "pengganti", label: "Pengganti" },
  { id: "batal", label: "Batal" },
];

const STATUS_STYLE = {
  normal: "bg-[#E5F6EC] text-[#1B7A43]",
  pengganti: "bg-[#FFF3CD] text-[#8A6D00]",
  batal: "bg-[#FDE2E2] text-[#9B1C1C]",
};

export default function TaxInvoices({ currentUser = {} }) {
  // FASE E-8 (E8.10b#2) — pajak keluaran adalah wilayah peran `finance`. Daftar peran
  // lama (`["manager","admin"]`) membuat Kasir/Finance melihat layarnya tetapi TANPA
  // satu pun tombol, padahal server sudah mengizinkan. Sekarang tiap tombol memakai
  // izin aksinya sendiri: batal TETAP manajer, sisanya boleh Finance.
  const perms = currentUser?.permissions || {};
  const canSetNsfp = can(perms, "tax_invoice", "update");
  const canReplace = can(perms, "tax_invoice", "replace");
  const canCancel = can(perms, "tax_invoice", "cancel");

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState("");

  // modal: { type: 'nsfp'|'replace'|'cancel', fkt }
  const [modal, setModal] = useState(null);
  const [nsfpVal, setNsfpVal] = useState("");
  const [kodeVal, setKodeVal] = useState("01");
  const [reasonVal, setReasonVal] = useState("");
  const [modalErr, setModalErr] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const r = await axios.get(`${API}/tax-invoices`);
      setRows(Array.isArray(r.data) ? r.data : []);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Faktur Pajak.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows
      .filter((f) => filter === "all" || f.status === filter)
      .filter((f) =>
        !q ||
        (f.number || "").toLowerCase().includes(q) ||
        (f.order_number || "").toLowerCase().includes(q) ||
        (f.customer_name || "").toLowerCase().includes(q) ||
        (f.nsfp || "").toLowerCase().includes(q)
      );
  }, [rows, filter, search]);

  const openDoc = (id) => window.open(`/api/tax-invoices/${id}/document`, "_blank", "noopener,noreferrer");

  const openModal = (type, fkt) => {
    setModal({ type, fkt });
    setNsfpVal(fkt.nsfp || "");
    setKodeVal(fkt.kode_transaksi || "01");
    setReasonVal("");
    setModalErr("");
  };
  const closeModal = () => setModal(null);

  const submitModal = async () => {
    if (!modal) return;
    const { type, fkt } = modal;
    setBusyId(fkt.id);
    setModalErr("");
    try {
      if (type === "nsfp") {
        if (!nsfpVal.trim()) { setModalErr("NSFP wajib diisi."); setBusyId(""); return; }
        await axios.patch(`${API}/tax-invoices/${fkt.id}/nsfp`, { nsfp: nsfpVal.trim(), kode_transaksi: kodeVal });
      } else if (type === "replace") {
        await axios.post(`${API}/tax-invoices/${fkt.id}/replace`, { reason: reasonVal.trim(), kode_transaksi: kodeVal });
      } else if (type === "cancel") {
        if (!reasonVal.trim()) { setModalErr("Alasan pembatalan wajib diisi."); setBusyId(""); return; }
        await axios.post(`${API}/tax-invoices/${fkt.id}/cancel`, { reason: reasonVal.trim() });
      }
      closeModal();
      await load();
    } catch (e) {
      setModalErr(e.response?.data?.detail || "Operasi gagal.");
    } finally {
      setBusyId("");
    }
  };

  return (
    <div data-testid="tax-invoices-view" className="space-y-4">
      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-[#0058CC]" />
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wide text-[#0058CC]">Sub-fase 1.9</p>
              <h2 className="text-[15px] font-bold">Faktur Pajak Jual</h2>
            </div>
          </div>
          <button data-testid="fkt-refresh" className="btn-secondary" onClick={load} disabled={loading}>
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
          </button>
        </div>
        <div className="section-body space-y-3">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="fkt-error" />
          <p className="text-[11.5px] text-[#6B6B73]">
            Faktur Pajak diterbitkan dari <b>detail Pesanan</b> (opsional — pajak tidak wajib, hanya untuk entitas PKP & transaksi ber-PPN).
            Di sini Anda mengisi NSFP resmi, menerbitkan faktur pengganti, atau membatalkan.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex gap-1">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  data-testid={`fkt-filter-${f.id}`}
                  onClick={() => setFilter(f.id)}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-semibold ${
                    filter === f.id ? "bg-[#0058CC] text-white" : "bg-[#EEF2F7] text-[#3C3C43]"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="relative ml-auto">
              <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-[#8E8E93]" />
              <input
                data-testid="fkt-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Cari nomor / pesanan / pelanggan / NSFP"
                className="rounded-md border border-[#E5E5EA] bg-white py-1 pl-7 pr-2 text-[12px] w-[260px]"
              />
            </div>
          </div>

          {error && <p className="text-[12px] text-[#B23B14]">{error}</p>}

          <div className="overflow-x-auto rounded-md border border-[#EFF0F2]">
            <table className="w-full text-[11.5px]">
              <thead className="bg-[#FAFBFC] text-[#6B6B73]">
                <tr>
                  <th className="px-2.5 py-2 text-left font-bold uppercase tracking-wide text-[10px]">No. Faktur</th>
                  <th className="px-2.5 py-2 text-left font-bold uppercase tracking-wide text-[10px]">NSFP</th>
                  <th className="px-2.5 py-2 text-left font-bold uppercase tracking-wide text-[10px]">Pesanan</th>
                  <th className="px-2.5 py-2 text-left font-bold uppercase tracking-wide text-[10px]">Pembeli</th>
                  <th className="px-2.5 py-2 text-right font-bold uppercase tracking-wide text-[10px]">DPP</th>
                  <th className="px-2.5 py-2 text-right font-bold uppercase tracking-wide text-[10px]">PPN</th>
                  <th className="px-2.5 py-2 text-right font-bold uppercase tracking-wide text-[10px]">Total</th>
                  <th className="px-2.5 py-2 text-center font-bold uppercase tracking-wide text-[10px]">Status</th>
                  <th className="px-2.5 py-2 text-right font-bold uppercase tracking-wide text-[10px]">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-2.5 py-6 text-center text-[#8E8E93]">
                      {loading ? "Memuat…" : "Belum ada Faktur Pajak."}
                    </td>
                  </tr>
                ) : (
                  filtered.map((f) => {
                    const isActive = f.status !== "batal" && !f.replaced_by_id;
                    return (
                      <tr key={f.id} data-testid={`fkt-row-${f.id}`} className="border-t border-[#EFF0F2] hover:bg-[#F8FAFD]">
                        <td className="px-2.5 py-2 font-bold text-[#0058CC]">{f.number}</td>
                        <td className="px-2.5 py-2 text-[#3C3C43]">
                          {f.nsfp ? (
                            <span className="tabular-nums">{f.nsfp}</span>
                          ) : (
                            <span className="text-[#B23B14]">belum diisi</span>
                          )}
                        </td>
                        <td className="px-2.5 py-2">{f.order_number}</td>
                        <td className="px-2.5 py-2">
                          <span className="block truncate max-w-[160px]">{f.customer_name}</span>
                          <span className="text-[10px] text-[#8E8E93]">{f.customer_npwp || "tanpa NPWP"}</span>
                        </td>
                        <td className="px-2.5 py-2 text-right tabular-nums">{formatCurrency(f.dpp)}</td>
                        <td className="px-2.5 py-2 text-right tabular-nums">{formatCurrency(f.ppn_amount)}</td>
                        <td className="px-2.5 py-2 text-right tabular-nums font-semibold">{formatCurrency(f.grand_total)}</td>
                        <td className="px-2.5 py-2 text-center">
                          <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ${STATUS_STYLE[f.status] || ""}`}>
                            {f.status}
                          </span>
                        </td>
                        <td className="px-2.5 py-2">
                          <div className="flex items-center justify-end gap-1">
                            <DocumentActionsBar docType="tax_invoice" sourceId={f.id} entityId={f.entity_id}
                              number={f.number} label="Faktur Pajak" currentUser={currentUser}
                              compact autoCheckSignature={false} />
                            <button data-testid={`fkt-print-${f.id}`} className="icon-button" title="Cetak Faktur (format lama)" onClick={() => openDoc(f.id)}>
                              <Printer size={13} />
                            </button>
                            {canSetNsfp && f.status !== "batal" && (
                              <button data-testid={`fkt-nsfp-${f.id}`} className="icon-button" title="Isi NSFP resmi" onClick={() => openModal("nsfp", f)}>
                                <Hash size={13} />
                              </button>
                            )}
                            {canReplace && isActive && (
                              <button data-testid={`fkt-replace-${f.id}`} className="icon-button" title="Terbitkan Pengganti" onClick={() => openModal("replace", f)}>
                                <Copy size={13} />
                              </button>
                            )}
                            {canCancel && f.status !== "batal" && (
                              <button data-testid={`fkt-cancel-${f.id}`} className="icon-button text-[#B23B14]" title="Batalkan" onClick={() => openModal("cancel", f)}>
                                <Ban size={13} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" {...overlayDismiss(closeModal)}>
          <div data-testid="fkt-modal" className="w-full max-w-md rounded-lg bg-white p-4 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-[14px] font-bold mb-1">
              {modal.type === "nsfp" && "Isi NSFP Resmi"}
              {modal.type === "replace" && "Terbitkan Faktur Pengganti"}
              {modal.type === "cancel" && "Batalkan Faktur Pajak"}
            </h3>
            <p className="text-[11px] text-[#6B6B73] mb-3">{modal.fkt.number} · {modal.fkt.order_number}</p>

            {modal.type === "nsfp" && (
              <div className="space-y-2">
                <label className="block text-[11px] font-semibold">Nomor Seri Faktur Pajak (16 digit)</label>
                <input data-testid="fkt-nsfp-input" value={nsfpVal} onChange={(e) => setNsfpVal(e.target.value)}
                  placeholder="0100123456789012"
                  className="w-full rounded-md border border-[#E5E5EA] px-2 py-1.5 text-[12px] tabular-nums" />
                <label className="block text-[11px] font-semibold mt-2">Kode Transaksi</label>
                <KNSelect
                  data-testid="fkt-kode-select"
                  value={kodeVal}
                  onValueChange={setKodeVal}
                  className="w-full rounded-md border border-[#E5E5EA] px-2 py-1.5 text-[12px]"
                  options={["01", "02", "03", "04", "06", "07", "08", "09"].map((k) => ({ value: k, label: k }))}
                />
              </div>
            )}

            {modal.type === "replace" && (
              <div className="space-y-2">
                <label className="block text-[11px] font-semibold">Alasan Pengganti (opsional)</label>
                <input data-testid="fkt-reason-input" value={reasonVal} onChange={(e) => setReasonVal(e.target.value)}
                  placeholder="mis. Koreksi alamat / nilai"
                  className="w-full rounded-md border border-[#E5E5EA] px-2 py-1.5 text-[12px]" />
                <label className="block text-[11px] font-semibold mt-2">Kode Transaksi</label>
                <KNSelect
                  data-testid="fkt-kode-select"
                  value={kodeVal}
                  onValueChange={setKodeVal}
                  className="w-full rounded-md border border-[#E5E5EA] px-2 py-1.5 text-[12px]"
                  options={["01", "02", "03", "04", "06", "07", "08", "09"].map((k) => ({ value: k, label: k }))}
                />
                <p className="text-[10.5px] text-[#8A6D00]">Faktur lama ditandai diganti; faktur baru berstatus PENGGANTI.</p>
              </div>
            )}

            {modal.type === "cancel" && (
              <div className="space-y-2">
                <label className="block text-[11px] font-semibold">Alasan Pembatalan (wajib)</label>
                <input data-testid="fkt-reason-input" value={reasonVal} onChange={(e) => setReasonVal(e.target.value)}
                  placeholder="mis. Transaksi dibatalkan pelanggan"
                  className="w-full rounded-md border border-[#E5E5EA] px-2 py-1.5 text-[12px]" />
              </div>
            )}

            {modalErr && <p className="mt-2 text-[11px] text-[#B23B14]">{modalErr}</p>}

            <div className="mt-4 flex justify-end gap-2">
              <button className="btn-secondary" onClick={closeModal}>Batal</button>
              <button
                data-testid="fkt-modal-submit"
                className={`btn-primary ${modal.type === "cancel" ? "!bg-[#B23B14]" : ""}`}
                disabled={busyId === modal.fkt.id}
                onClick={submitModal}
              >
                {busyId === modal.fkt.id ? "Memproses…" : "Konfirmasi"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
