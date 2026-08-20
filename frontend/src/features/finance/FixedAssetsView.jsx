/**
 * R6.2 — FixedAssetsView — Aset Tetap: registrasi, penyusutan straight-line & disposal.
 * Akses admin/manager (permission "fixed_asset"). Sumber: /api/fixed-assets*.
 * GL: Dr 6-6000 Beban Penyusutan / Cr 1-2900 Akumulasi Penyusutan.
 * Disposal: gain/loss = proceeds − nilai buku (append-only; aset → status disposed).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw, Building2, Plus, PlayCircle, CalendarClock, PackageMinus,
  Layers3, TrendingDown, Wallet, Scale, CheckCircle2, Search,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import { formatCurrency } from "../../utils/formatters";
import {
  AssetStatusPill, FaKpi, AddAssetDialog, ScheduleDialog, DisposeDialog, fmtDate,
} from "./FixedAssetsParts";

const thisPeriod = () => new Date().toISOString().slice(0, 7);

export default function FixedAssetsView({ selectedEntity, entities = [] }) {
  const [assets, setAssets] = useState([]);
  const [summary, setSummary] = useState(null);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [q, setQ] = useState("");
  const [period, setPeriod] = useState(thisPeriod());
  const [showAdd, setShowAdd] = useState(false);
  const [scheduleFor, setScheduleFor] = useState(null);   // detail aset (schedule)
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [disposeFor, setDisposeFor] = useState(null);     // aset yang akan dilepas
  // FASE E-7 (E7g) — pindah aset tetap ANTAR BADAN USAHA (nilai buku + masa manfaat sisa).
  const [transferFor, setTransferFor] = useState(null);
  const [trTo, setTrTo] = useState("");
  const [trPrice, setTrPrice] = useState("");
  const [trReason, setTrReason] = useState("");

  async function submitTransfer() {
    if (!transferFor) return;
    setBusy("transfer"); setError("");
    try {
      const res = await axios.post(`${API}/fixed-assets/${transferFor.id}/transfer`, {
        to_entity_id: trTo, transfer_price: trPrice ? Number(trPrice) : null,
        reason: trReason,
      });
      setMsg(`${transferFor.number} dipindah → ${res.data.new_asset.number} `
        + `(harga ${formatCurrency(res.data.price)}, nilai buku ${formatCurrency(res.data.book_value)}`
        + `${res.data.gain > 0 ? `, laba ${formatCurrency(res.data.gain)} dieliminasi di konsolidasi` : ""}). `
        + "Utang antar-PT terbentuk — catat pembayarannya bila uangnya sudah pindah.");
      setTransferFor(null); setTrTo(""); setTrPrice(""); setTrReason("");
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memindahkan aset.");
    } finally { setBusy(""); }
  }

  async function settleTransfer(a) {
    setBusy(`settle-${a.id}`); setError("");
    try {
      const res = await axios.post(`${API}/fixed-assets/${a.id}/transfer/settle`, { note: "" });
      setMsg(`Pembayaran pindah aset ${a.number} dicatat (${formatCurrency(res.data.paid)}) — `
        + `kas berpindah: ${(res.data.cash || []).join(" · ")}.`);
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal mencatat pembayaran pindah aset.");
    } finally { setBusy(""); }
  }

  const entParam = useMemo(
    () => (selectedEntity && selectedEntity !== "all" ? selectedEntity : ""),
    [selectedEntity],
  );

  const entityName = useCallback(
    (id) => {
      const e = (entities || []).find((x) => x.id === id);
      return e ? (e.short_name || e.legal_name || id) : (id || "—");
    },
    [entities],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = entParam ? { entity_id: entParam } : {};
      const [ls, sm, mt] = await Promise.all([
        axios.get(`${API}/fixed-assets`, { params }),
        axios.get(`${API}/fixed-assets/summary`, { params }),
        axios.get(`${API}/fixed-assets/meta`, { params }),
      ]);
      setAssets(Array.isArray(ls.data) ? ls.data : []);
      setSummary(sm.data || null);
      setMeta(mt.data || null);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data aset tetap.");
    } finally {
      setLoading(false);
    }
  }, [entParam]);

  useEffect(() => { load(); }, [load]);

  const notify = (m) => { setMsg(m); setTimeout(() => setMsg(""), 6000); };

  async function createAsset(payload) {
    setBusy("create");
    try {
      const res = await axios.post(`${API}/fixed-assets`, payload);
      notify(`Aset ${res.data?.number || ""} dibuat. JE perolehan: ${res.data?.acquisition_je || "—"}.`);
      setShowAdd(false);
      await load();
      return true;
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal membuat aset.");
      return false;
    } finally { setBusy(""); }
  }

  async function runDepreciation() {
    if (!/^\d{4}-\d{2}$/.test(period)) { setError("Format periode harus YYYY-MM (contoh 2026-07)."); return; }
    setBusy("run");
    try {
      const res = await axios.post(`${API}/fixed-assets/run-depreciation`, {
        period, entity_id: entParam,
      });
      const d = res.data || {};
      notify(`Penyusutan ${d.period}: ${d.posted} aset diposting (${formatCurrency(d.total_amount)}), ${d.skipped} dilewati.`);
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menjalankan penyusutan.");
    } finally { setBusy(""); }
  }

  async function openSchedule(asset) {
    setScheduleFor({ ...asset, schedule: [], depreciation_entries: [] });
    setScheduleLoading(true);
    try {
      const res = await axios.get(`${API}/fixed-assets/${asset.id}`);
      setScheduleFor(res.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat jadwal penyusutan.");
      setScheduleFor(null);
    } finally { setScheduleLoading(false); }
  }

  async function submitDispose({ proceeds, date, note }) {
    setBusy("dispose");
    try {
      const res = await axios.post(`${API}/fixed-assets/${disposeFor.id}/dispose`, { proceeds, date, note });
      const d = res.data?.disposal || {};
      const label = d.result === "gain" ? "Laba" : d.result === "loss" ? "Rugi" : "Impas";
      notify(`${res.data?.number || "Aset"} dilepas. ${label} pelepasan ${formatCurrency(Math.abs(d.gain_loss || 0))} · JE ${d.je_number || "—"}.`);
      setDisposeFor(null);
      await load();
      return true;
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal melepas aset.");
      return false;
    } finally { setBusy(""); }
  }

  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return assets;
    return assets.filter((a) => `${a.number} ${a.name} ${a.category}`.toLowerCase().includes(term));
  }, [assets, q]);

  const s = summary || {};

  return (
    <div data-testid="fixed-assets-view">
      {/* KPI ringkasan */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-3">
        <FaKpi testId="summary-count" label="Jumlah Aset" icon={Layers3}
          value={`${s.count || 0}`}
          hint={`${s.active || 0} dimiliki · ${s.transferred || 0} pindah PT · ${s.disposed || 0} dilepas`} />
        <FaKpi testId="summary-gross-cost" label="Nilai Perolehan" icon={Building2}
          value={formatCurrency(s.gross_cost)} hint="aset yang MASIH dimiliki (gross)" />
        <FaKpi testId="summary-accumulated" label="Akumulasi Penyusutan" icon={TrendingDown}
          value={formatCurrency(s.accumulated_depreciation)} tone="text-[#B45309]" hint="akun 1-2900" />
        <FaKpi testId="summary-net-book-value" label="Nilai Buku (Net)" icon={Wallet}
          value={formatCurrency(s.net_book_value)} tone="text-[#1B7F4B]" hint="perolehan − akumulasi" />
        {(s.transferred || 0) > 0 ? (
          <FaKpi testId="summary-transferred" label="Pindah ke PT Lain" icon={Building2}
            value={formatCurrency(s.transferred_book_value)} tone="text-[#0058CC]"
            hint={(s.transferred_unsettled || 0) > 0
              ? `${s.transferred} aset · ${s.transferred_unsettled} belum dibayar`
              : `${s.transferred} aset · semua sudah dibayar`} />
        ) : (
          <FaKpi testId="summary-disposal-gain-loss" label="Laba/Rugi Pelepasan" icon={Scale}
            value={formatCurrency(s.disposal_gain_loss)}
            tone={(s.disposal_gain_loss || 0) < 0 ? "text-[#C0392B]" : "text-[#1B7F4B]"}
            hint="akum. disposal" />
        )}      </div>

      {/* Kontrol penyusutan */}
      <div className="section-card mb-3">
        <div className="section-body py-3 flex flex-wrap items-end gap-3">
          <div className="flex items-center gap-2 mr-auto">
            <div className="w-9 h-9 rounded-lg bg-[#EAF1FF] flex items-center justify-center">
              <CalendarClock size={17} className="text-[#0058CC]" />
            </div>
            <div>
              <p className="text-[12px] font-bold text-[#1C1C1E]">Jalankan Penyusutan Bulanan</p>
              <p className="text-[10.5px] text-[#8E8E93]">Straight-line, idempotent per aset & periode. Posting Dr 6-6000 / Cr 1-2900.</p>
            </div>
          </div>
          <label className="grid gap-1">
            <span className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">Periode (YYYY-MM)</span>
            <input data-testid="fa-period-input" className="field w-[130px] text-[12px]" type="month"
              value={period} onChange={(e) => setPeriod(e.target.value)} />
          </label>
          <button data-testid="run-depreciation-btn" className="primary-button" disabled={busy === "run"}
            onClick={runDepreciation}>
            {busy === "run" ? <RefreshCw size={14} className="animate-spin" /> : <PlayCircle size={14} />}
            Jalankan Penyusutan
          </button>
        </div>
      </div>

      {/* Daftar aset */}
      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <Building2 size={16} className="text-[#0058CC]" />
            <h2 data-testid="fixed-assets-title">Daftar Aset Tetap</h2>
            <span className="text-[10.5px] text-[#9A9BA3]">{rows.length} aset</span>
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <div className="relative">
              <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="fa-search" className="field pl-7 py-1 text-[12px]" placeholder="Cari nomor / nama..."
                value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <button data-testid="add-asset-btn" className="primary-button" onClick={() => setShowAdd(true)}>
              <Plus size={14} /> Tambah Aset
            </button>
            <button data-testid="fa-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="fixed-assets-error" />
          {msg && (
            <div className="notice-bar success mb-2" data-testid="fa-notice">
              <CheckCircle2 size={14} /> <span>{msg}</span>
              <button onClick={() => setMsg("")} aria-label="Tutup">×</button>
            </div>
          )}

          {loading ? (
            <div className="grid gap-2" data-testid="fa-loading">
              {[0, 1, 2, 3].map((i) => <div key={i} className="h-10 bg-[#F5F5F7] rounded animate-pulse" />)}
            </div>
          ) : rows.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#8E8E93]" data-testid="fa-empty">
              <Building2 size={26} className="mx-auto mb-2 text-gray-300" />
              {q ? "Tidak ada aset yang cocok dengan pencarian."
                : "Belum ada aset tetap terdaftar. Klik \u201cTambah Aset\u201d untuk registrasi aset pertama."}
            </div>
          ) : (
            <div className="overflow-auto rounded-md border border-[#EFF0F2]">
              <table className="w-full text-[12px]" data-testid="fa-table">
                <thead>
                  <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                    <th className="px-3 py-2">Nomor</th>
                    <th className="px-3 py-2">Nama Aset</th>
                    <th className="px-3 py-2">Kategori</th>
                    <th className="px-3 py-2 text-right">Perolehan</th>
                    <th className="px-3 py-2 text-right">Akumulasi</th>
                    <th className="px-3 py-2 text-right">Nilai Buku</th>
                    <th className="px-3 py-2 text-center">Status</th>
                    <th className="px-3 py-2 text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((a) => (
                    <tr key={a.id} data-testid={`asset-row-${a.id}`} className="border-b border-[#F5F5F7] last:border-0 hover:bg-[#FAFBFF]">
                      <td className="px-3 py-2 font-semibold text-[#0058CC] whitespace-nowrap">{a.number}</td>
                      <td className="px-3 py-2">
                        <p className="font-semibold text-[#1C1C1E]">{a.name}</p>
                        <p className="text-[10px] text-[#9A9BA3]">
                          {fmtDate(a.acquisition_date)} · {a.useful_life_months} bln · {entityName(a.entity_id)}
                          {a.gl_account_asset ? ` · ${a.gl_account_asset}` : ""}
                        </p>
                      </td>
                      <td className="px-3 py-2 text-[#3C3C43]">{a.category}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(a.acquisition_cost)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-[#B45309]">
                        {formatCurrency(a.accumulated_depreciation)}
                        <span className="block text-[10px] text-[#9A9BA3]">{a.depreciated_months || 0}/{a.useful_life_months} bln</span>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-bold" data-testid={`asset-bv-${a.id}`}>
                        {formatCurrency(a.book_value)}
                      </td>
                      <td className="px-3 py-2 text-center"><AssetStatusPill asset={a} /></td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        <div className="flex items-center gap-2 justify-end">
                          <button data-testid={`schedule-btn-${a.id}`} className="secondary-button !py-1 !px-2 text-[11px]"
                            onClick={() => openSchedule(a)}>
                            <CalendarClock size={12} /> Jadwal
                          </button>
                          {a.status !== "disposed" && a.status !== "transferred" && (
                            <>
                              <button data-testid={`transfer-btn-${a.id}`} className="secondary-button !py-1 !px-2 text-[11px]"
                                title="Pindahkan aset ini ke badan usaha lain di dalam grup (nilai buku + masa manfaat sisa ikut pindah)"
                                onClick={() => { setTransferFor(a); setTrTo(""); setTrPrice(""); setTrReason(""); }}>
                                <Building2 size={12} /> Pindah PT
                              </button>
                              <button data-testid={`dispose-btn-${a.id}`} className="secondary-button !py-1 !px-2 text-[11px]"
                                style={{ color: "#B4231F", borderColor: "#F0B5AE" }} onClick={() => setDisposeFor(a)}>
                                <PackageMinus size={12} /> Lepas
                              </button>
                            </>
                          )}
                          {a.status === "transferred" && a.transfer && (
                            <span data-testid={`transferred-flag-${a.id}`} className="text-[10.5px] text-[#6B219A]"
                              title={`Dipindah ke ${a.transfer.to_entity_name} pada ${a.transfer.transfer_date} — aset penggantinya ${a.transfer.new_asset_number}`}>
                              → {a.transfer.to_entity_name} ({a.transfer.new_asset_number})
                              {!a.transfer.settled && (
                                <button data-testid={`settle-transfer-${a.id}`} className="btn-primary btn-xs ml-2"
                                  disabled={busy === `settle-${a.id}`} onClick={() => settleTransfer(a)}>
                                  Catat pembayaran
                                </button>
                              )}
                              {a.transfer.settled && <b className="ml-1 text-[#1B7F4B]">· dibayar</b>}
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-[10.5px] text-[#9A9BA3] mt-2">
            Metode <b>garis lurus (straight-line)</b>: penyusutan bulanan = (perolehan − nilai residu) / masa manfaat.
            Perolehan diposting Dr akun aset / Cr Kas-Bank. Aset yang dilepas tidak dihapus — statusnya menjadi <i>disposed</i> (append-only).
          </p>
        </div>
      </div>

      {showAdd && (
        <AddAssetDialog
          meta={meta} entities={entities} selectedEntity={selectedEntity} busy={busy === "create"}
          onCancel={() => setShowAdd(false)} onSubmit={createAsset}
        />
      )}
      {scheduleFor && (
        <ScheduleDialog asset={scheduleFor} loading={scheduleLoading} onClose={() => setScheduleFor(null)} />
      )}
      {disposeFor && (
        <DisposeDialog asset={disposeFor} busy={busy === "dispose"}
          onCancel={() => setDisposeFor(null)} onSubmit={submitDispose} />
      )}
      {/* FASE E-7 (E7g) — pindah aset tetap antar badan usaha */}
      {transferFor && (
        <div className="modal-overlay" data-testid="asset-transfer-modal"
          onClick={(e) => { if (e.target === e.currentTarget) setTransferFor(null); }}>
          <div className="modal-card" style={{ maxWidth: 560, width: "95vw" }} onClick={(e) => e.stopPropagation()}>
            <p className="modal-title">Pindah Aset ke Badan Usaha Lain</p>
            <p className="modal-subtitle">
              <b>{transferFor.number} · {transferFor.name}</b> — nilai buku sekarang{" "}
              <b>{formatCurrency(transferFor.book_value)}</b> (akumulasi penyusutan{" "}
              {formatCurrency(transferFor.accumulated_depreciation)}). Aset akan lahir kembali
              di badan usaha penerima dengan <b>masa manfaat SISA</b>, akumulasi penyusutan di
              badan usaha ini dihapus lewat jurnal, dan bila harga pindah di atas nilai buku,
              labanya <b>dieliminasi di konsolidasi</b> (menjual ke PT sendiri bukan laba grup).
            </p>
            <div className="grid gap-3 mt-3">
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-[#4A4B53]">Badan Usaha Penerima *</label>
                <KNSelect data-testid="asset-transfer-to" className="field" value={trTo}
                  onValueChange={setTrTo} aria-label="Badan usaha tujuan pindah aset"
                  placeholder="— Pilih badan usaha —"
                  options={(entities || [])
                    .filter((en) => en.id !== transferFor.entity_id
                      && (en.status || "active") === "active")
                    .map((en) => ({
                      value: en.id, label: en.short_name || en.legal_name || en.id,
                    }))} />
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-[#4A4B53]">
                  Harga Pindah <span className="font-normal text-[#9A9BA3]">(kosong = nilai buku)</span>
                </label>
                <input data-testid="asset-transfer-price" type="number" className="field"
                  value={trPrice} onChange={(e) => setTrPrice(e.target.value)}
                  placeholder={String(transferFor.book_value)} />
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-[#4A4B53]">Alasan Pindah *</label>
                <input data-testid="asset-transfer-reason" className="field" value={trReason}
                  onChange={(e) => setTrReason(e.target.value)}
                  placeholder="mis. mesin dipakai produksi badan usaha itu mulai bulan depan" />
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setTransferFor(null)}>Batal</button>
              <button data-testid="asset-transfer-submit" className="btn-primary"
                disabled={busy === "transfer" || !trTo || trReason.trim().length < 5}
                onClick={submitTransfer}>
                {busy === "transfer" ? "Memproses…" : "Pindahkan Aset"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
