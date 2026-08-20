/**
 * PricelistView (F1a → FASE E-4 · E4.7) — HARGA JUAL PER BADAN USAHA.
 *
 * Keputusan pemilik #4: harga master GLOBAL + **override per badan usaha**, dan
 * "UI override harus jelas, nilai yang berasal dari global WAJIB berlabel".
 *
 * Karena itu layar ini menampilkan TIGA angka bersebelahan, bukan satu:
 *      Harga global   ·   Harga badan usaha ini   ·   Harga efektif (+ lencana asal)
 * Tanpa itu, pengguna melihat satu angka dan tidak tahu apakah ia sedang mengubah
 * harga seluruh grup atau harga satu badan usaha saja — kesalahan yang mahal.
 *
 * Yang bisa dilakukan di sini:
 *   · **Set harga** badan usaha (dengan masa berlaku; record lama ditutup otomatis)
 *   · **Kembalikan ke global** — melepas override tanpa menghapus riwayat
 *   · **Riwayat harga** per produk (termasuk yang terjadwal & kadaluarsa)
 *   · **Ekspor/impor CSV** lewat server (satu permintaan, laporan galat per SKU)
 *
 * Urutan harga di pesanan/POS: harga khusus disetujui → pelanggan → badan usaha →
 * global. Layar ini mengelola lapisan **badan usaha**; lapisan pelanggan ada di
 * "Harga per Pelanggan".
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Tag, RefreshCw, Search, Plus, History, X, Download, Upload, Save,
  CheckCircle2, AlertTriangle, Building2, RotateCcw, CalendarClock, ArrowUp, ArrowDown,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import EntityBadge from "../../components/EntityBadge";
import { entityShort, entityShortById } from "../../utils/entityLabel";
import { formatCurrency } from "../../utils/formatters";

const STATUS_META = {
  current: { label: "Berlaku", tone: "bg-[#E6F6EC] text-[#1B7F4B]" },
  scheduled: { label: "Terjadwal", tone: "bg-[#E7F0FF] text-[#0058CC]" },
  expired: { label: "Kadaluarsa", tone: "bg-[#F5F5F7] text-[#8E8E93]" },
  inactive: { label: "Nonaktif", tone: "bg-[#FDEDE7] text-[#C0392B]" },
};

// Lencana ASAL harga — sengaja memakai kata yang sama dengan POS/keranjang
// (`hooks/useEffectivePrices.PRICE_SOURCE_META`) supaya pengguna tidak perlu
// menerjemahkan istilah dua kali.
const SOURCE_META = {
  entity: { label: "Badan usaha ini", tone: "bg-[#F3E9FA] text-[#6B219A]" },
  global: { label: "Global", tone: "bg-[#F5F5F7] text-[#6B6B73]" },
  // Produk yang BELUM punya harga jual sama sekali (mis. barang sisa / kain grey).
  // Dulu ditampilkan sebagai "Rp 0 · Global" — pembacaan yang berbahaya karena
  // seolah-olah harga jualnya memang nol dan boleh dipakai di pesanan/POS.
  none: { label: "Belum ada harga", tone: "bg-[#FDEDE7] text-[#C0392B]" },
};

/** Angka rupiah, tetapi 0/kosong ditulis apa adanya: belum ditetapkan. */
function PriceCell({ value }) {
  if (value == null || Number(value) === 0) {
    return <span className="text-[10.5px] font-normal italic text-[#C0392B]">belum ditetapkan</span>;
  }
  return <>{formatCurrency(value)}</>;
}

function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "2-digit" }); }
  catch { return "—"; }
}

export default function PricelistView({ entities = [], selectedEntity, currentUser }) {
  const canManage = ["admin", "manager"].includes(currentUser?.role);
  const activeList = entities.filter((e) => e.status !== "inactive" && e.status !== "archived");
  const [entityId, setEntityId] = useState(
    selectedEntity && selectedEntity !== "all" ? selectedEntity : (activeList[0]?.id || ""));
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [priceModal, setPriceModal] = useState(null);    // { row }
  const [historyRow, setHistoryRow] = useState(null);    // { row }
  const [busyRow, setBusyRow] = useState("");
  const [onlyOverride, setOnlyOverride] = useState(false);

  const entityName = entityShortById(activeList, entityId);

  const load = useCallback(async () => {
    if (!entityId) return;
    setLoading(true); setError("");
    try {
      const res = await axios.get(`${API}/pricelist`, { params: { entity_id: entityId, search } });
      setRows(res.data?.rows || []);
      setSummary(res.data?.summary || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat pricelist.");
    } finally {
      setLoading(false);
    }
  }, [entityId, search]);

  useEffect(() => { load(); }, [load]);

  // Ikuti pemilih badan usaha global bila pengguna berpindah konteks.
  useEffect(() => {
    if (selectedEntity && selectedEntity !== "all") setEntityId(selectedEntity);
  }, [selectedEntity]);

  const entityOptions = useMemo(
    () => activeList.map((e) => ({ value: e.id, label: entityShort(e) })),
    [activeList]);

  const shown = useMemo(
    () => (onlyOverride ? rows.filter((r) => r.entity_price != null) : rows),
    [rows, onlyOverride]);

  // Produk tanpa harga jual di lapisan mana pun — wajib terlihat, bukan disembunyikan
  // sebagai "Rp 0" yang seolah-olah harga sah.
  const noPriceCount = useMemo(
    () => rows.filter((r) => r.effective_price == null || Number(r.effective_price) === 0).length,
    [rows]);

  const exportCsv = async () => {
    setError("");
    try {
      const res = await axios.get(`${API}/pricelist/export`, {
        params: { entity_id: entityId, only_with_price: false }, responseType: "blob",
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `harga-${entityName}-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal mengunduh CSV harga.");
    }
  };

  const importCsv = async (file) => {
    if (!file) return;
    setNotice(""); setError("");
    try {
      const text = await file.text();
      const res = await axios.post(`${API}/pricelist/import`, { entity_id: entityId, csv_text: text });
      const d = res.data || {};
      setNotice(`Impor selesai: ${d.applied || 0} harga diterapkan${d.skipped ? `, ${d.skipped} dilewati` : ""}.`);
      if ((d.errors || []).length) setError(d.errors.slice(0, 5).join(" "));
      load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal membaca berkas CSV.");
    }
  };

  const revertToGlobal = async (row) => {
    setNotice(""); setError(""); setBusyRow(row.product_id);
    try {
      const res = await axios.delete(`${API}/pricelist/override/${row.product_id}`,
        { params: { entity_id: entityId } });
      setNotice(`${row.product_name} kembali memakai harga global ${formatCurrency(res.data?.global_price || row.global_price)}.`);
      load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal mengembalikan ke harga global.");
    } finally {
      setBusyRow("");
    }
  };

  return (
    <div data-testid="pricelist-view">
      <div className="mb-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi testId="pl-kpi-products" label="Produk" value={summary?.products ?? rows.length} icon={Tag} />
        <Kpi testId="pl-kpi-override" label={`Harga khusus ${entityName}`}
          value={summary?.with_entity_price ?? 0} icon={Building2} tone="text-[#6B219A]" />
        <Kpi testId="pl-kpi-global" label="Ikut harga global"
          value={summary?.following_global ?? 0} icon={Tag} tone="text-[#8E8E93]" />
        <div className="section-card" data-testid="pl-kpi-entity">
          <div className="section-body flex items-center gap-3 py-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#F3EAFB]">
              <Building2 size={17} className="text-[#6B219A]" />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">Badan usaha</p>
              <EntityBadge entityId={entityId} entities={entities} />
              {summary?.scheduled > 0 && (
                <p data-testid="pl-kpi-scheduled" className="mt-0.5 text-[10px] font-semibold text-[#0058CC]">
                  <CalendarClock size={9} className="inline" /> {summary.scheduled} harga terjadwal
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="section-card">
        <div className="section-head flex-wrap gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-[200px]">
              <KNSelect data-testid="pl-entity-select" className="field py-1.5 text-[12px]" value={entityId}
                onValueChange={setEntityId} placeholder="Pilih badan usaha" options={entityOptions} />
            </div>
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="pl-search" className="field w-[220px] py-1.5 pl-8 text-[12px]"
                placeholder="Cari SKU / nama / kategori"
                value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <button data-testid="pl-filter-override"
              className={`rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
                onlyOverride ? "bg-[#6B219A] text-white"
                  : "border border-[#E5E5EA] bg-white text-[#6B6B73] hover:border-[#6B219A]"}`}
              onClick={() => setOnlyOverride((v) => !v)}>
              Hanya harga khusus
            </button>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button data-testid="pl-export" className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-[12px]"
              onClick={exportCsv}><Download size={13} /> Ekspor</button>
            {canManage && (
              <label data-testid="pl-import" className="btn-secondary inline-flex cursor-pointer items-center gap-1 px-3 py-1.5 text-[12px]">
                <Upload size={13} /> Impor
                <input type="file" accept=".csv" className="hidden"
                  onChange={(e) => { importCsv(e.target.files?.[0]); e.target.value = ""; }} />
              </label>
            )}
            <button data-testid="pl-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="pl-error" />
          {notice && (
            <div data-testid="pl-notice"
              className="mb-3 flex items-center gap-2 rounded-md border border-[#BDE5CC] bg-[#E6F6EC] px-3 py-2 text-[12px] text-[#1B7F4B]">
              <CheckCircle2 size={14} />{notice}
              <button className="ml-auto" onClick={() => setNotice("")} aria-label="Tutup"><X size={13} /></button>
            </div>
          )}
          <p className="mb-2 text-[11px] text-[#8E8E93]" data-testid="pl-explainer">
            Harga <b>global</b> berlaku untuk semua badan usaha. Harga <b>{entityName}</b> menimpanya
            hanya untuk badan usaha ini. Pesanan &amp; POS memakai kolom <b>harga efektif</b>.
          </p>
          {!loading && noPriceCount > 0 && (
            <p data-testid="pl-noprice-hint"
              className="mb-2 flex items-center gap-1.5 rounded-md border border-[#F5C97B] bg-[#FFF7E6] px-2.5 py-1.5 text-[11px] text-[#8C4A00]">
              <AlertTriangle size={12} />
              <span>
                <b>{noPriceCount} produk</b> belum punya harga jual — baik global maupun {entityName}.
                Tetapkan harganya sebelum produk itu dipakai di pesanan atau POS.
              </span>
            </p>
          )}

          {loading ? (
            <div className="grid gap-2" data-testid="pl-loading">
              {[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-[#F5F5F7]" />)}
            </div>
          ) : shown.length === 0 ? (
            <div data-testid="pl-empty" className="py-12 text-center text-[12px] text-[#8E8E93]">
              <Tag size={26} className="mx-auto mb-2 text-gray-300" />
              {onlyOverride ? `Belum ada harga khusus untuk ${entityName}.` : "Tidak ada produk."}
            </div>
          ) : (
            <div className="overflow-auto rounded-md border border-[#EFF0F2]">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[10px] font-bold uppercase text-[#8E8E93]">
                    <th className="px-3 py-2">SKU</th>
                    <th className="px-3 py-2">Produk</th>
                    <th className="px-3 py-2 text-right">Harga global</th>
                    <th className="px-3 py-2 text-right">Harga {entityName}</th>
                    <th className="px-3 py-2 text-right">Harga efektif</th>
                    <th className="px-3 py-2 text-center">Asal</th>
                    <th className="px-3 py-2 text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((r) => {
                    const has = r.entity_price != null;
                    // Tanpa harga efektif = belum ada harga jual di lapisan mana pun.
                    const noPrice = r.effective_price == null || Number(r.effective_price) === 0;
                    const sm = noPrice ? SOURCE_META.none : (SOURCE_META[r.price_source] || SOURCE_META.global);
                    return (
                      <tr key={r.product_id} data-testid={`pl-row-${r.product_id}`}
                        className="border-b border-[#F5F5F7] last:border-0 hover:bg-[#FBF8FE]">
                        <td className="px-3 py-2 font-mono text-[11px] text-[#6B6B73]">{r.sku}</td>
                        <td className="px-3 py-2">
                          <span className="font-medium text-[#1C1C1E]">{r.product_name}</span>
                          <span className="block text-[10px] text-[#9A9BA3]">
                            {r.category} · per {r.base_unit}
                            {r.scheduled_count > 0 && (
                              <span data-testid={`pl-scheduled-${r.product_id}`} className="ml-1 font-semibold text-[#0058CC]">
                                · {r.scheduled_count} terjadwal
                              </span>
                            )}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-[#6B6B73]"
                          data-testid={`pl-global-${r.product_id}`}>
                          <PriceCell value={r.global_price} />
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums" data-testid={`pl-entity-${r.product_id}`}>
                          {has ? (
                            <>
                              <span className="font-semibold text-[#6B219A]">{formatCurrency(r.entity_price)}</span>
                              <span className={`block text-[9.5px] font-semibold ${
                                r.diff_vs_global > 0 ? "text-[#1B7F4B]" : r.diff_vs_global < 0 ? "text-[#C0392B]" : "text-[#8E8E93]"}`}>
                                {r.diff_vs_global > 0 ? <ArrowUp size={8} className="inline" />
                                  : r.diff_vs_global < 0 ? <ArrowDown size={8} className="inline" /> : null}
                                {r.diff_vs_global === 0 ? "sama dengan global"
                                  : `${formatCurrency(Math.abs(r.diff_vs_global))} lebih ${r.diff_vs_global > 0 ? "mahal" : "murah"}`}
                                {r.valid_until ? ` · s.d. ${fmtDate(r.valid_until)}` : ""}
                              </span>
                            </>
                          ) : (
                            <span className="text-[11px] text-[#9A9BA3]">ikut global</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right font-semibold tabular-nums text-[#1C1C1E]"
                          data-testid={`pl-eff-${r.product_id}`}>
                          <PriceCell value={r.effective_price} />
                        </td>
                        <td className="px-3 py-2 text-center">
                          <span data-testid={`pl-source-${r.product_id}`}
                            className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${sm.tone}`}>{sm.label}</span>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-right">
                          <button data-testid={`pl-history-${r.product_id}`} className="icon-button" title="Riwayat harga"
                            onClick={() => setHistoryRow(r)}><History size={14} /></button>
                          {canManage && has && (
                            <button data-testid={`pl-revert-${r.product_id}`}
                              className="secondary-button ml-1 text-[11px]" disabled={busyRow === r.product_id}
                              title="Lepas harga khusus, kembali ke harga global"
                              onClick={() => revertToGlobal(r)}>
                              <RotateCcw size={12} /> Ke global
                            </button>
                          )}
                          {canManage && (
                            <button data-testid={`pl-setprice-${r.product_id}`}
                              className="primary-button ml-1 text-[11px]" onClick={() => setPriceModal(r)}>
                              <Plus size={12} /> {has ? "Ubah harga" : "Set harga"}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {priceModal && (
        <SetPriceModal row={priceModal} entityId={entityId} entityName={entityName}
          onClose={() => setPriceModal(null)}
          onSaved={() => { setPriceModal(null); setNotice(`Harga ${priceModal.product_name} tersimpan untuk ${entityName}.`); load(); }}
          onError={setError} />
      )}
      {historyRow && (
        <HistoryModal row={historyRow} entityId={entityId} entities={entities} canManage={canManage}
          onClose={() => setHistoryRow(null)} onChanged={() => { load(); }} />
      )}
    </div>
  );
}

// ─── Set Harga Modal ─────────────────────────────────────────────────────────
function SetPriceModal({ row, entityId, entityName, onClose, onSaved, onError }) {
  const today = new Date().toISOString().slice(0, 10);
  const [price, setPrice] = useState(row.entity_price != null ? String(row.entity_price) : "");
  const [validFrom, setValidFrom] = useState(today);
  const [validUntil, setValidUntil] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState("");

  const numeric = parseFloat(price);
  const diff = Number.isFinite(numeric) ? numeric - Number(row.global_price || 0) : 0;

  const save = async () => {
    setLocalError("");
    const p = parseFloat(price);
    if (!p || p <= 0) { setLocalError("Harga jual harus lebih dari 0."); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/pricelist`, {
        product_id: row.product_id, sell_price: p, entity_id: entityId,
        valid_from: validFrom, valid_until: validUntil, note,
      });
      onSaved();
    } catch (e) {
      const msg = e.response?.data?.detail || "Gagal menyimpan harga.";
      setLocalError(msg); onError?.(msg);
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="pl-setprice-modal">
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl">
        <div className="flex items-center gap-2 border-b border-[#EFF0F2] px-4 py-3">
          <Tag size={16} className="text-[#6B219A]" />
          <h3 className="text-[14px] font-bold">Harga {entityName}</h3>
          <button data-testid="pl-setprice-close" className="icon-button ml-auto" onClick={onClose} aria-label="Tutup">
            <X size={15} />
          </button>
        </div>
        <div className="space-y-3 p-4 text-[12px]">
          <ErrorNotice message={localError} onDismiss={() => setLocalError("")} testId="pl-setprice-error" />
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-3 py-2">
            <p className="font-semibold text-[#1C1C1E]">{row.product_name}</p>
            <p className="text-[11px] text-[#9A9BA3]">
              {row.sku} · harga global {formatCurrency(row.global_price)} / {row.base_unit}
              {row.hpp_ref > 0 ? ` · HPP ${formatCurrency(row.hpp_ref)}` : ""}
            </p>
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Harga jual {entityName} (per {row.base_unit})
            </label>
            <input data-testid="pl-input-price" type="number" className="field py-2 text-[13px]"
              placeholder="Mis. 195000" value={price} onChange={(e) => setPrice(e.target.value)} autoFocus />
            {Number.isFinite(numeric) && numeric > 0 && (
              <p data-testid="pl-price-diff" className="mt-1 text-[10.5px] text-[#6B6B73]">
                {diff === 0 ? "Sama dengan harga global."
                  : `${diff > 0 ? "Lebih tinggi" : "Lebih rendah"} ${formatCurrency(Math.abs(diff))} dari harga global.`}
                {row.hpp_ref > 0 && numeric < row.hpp_ref && (
                  <span className="ml-1 font-bold text-[#C0392B]">
                    <AlertTriangle size={10} className="inline" /> di bawah HPP
                  </span>
                )}
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Berlaku mulai</label>
              <input data-testid="pl-input-from" type="date" className="field py-2 text-[13px]"
                value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Berlaku sampai <span className="font-normal text-[#9A9BA3]">(opsional)</span>
              </label>
              <input data-testid="pl-input-until" type="date" className="field py-2 text-[13px]"
                value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Catatan <span className="font-normal text-[#9A9BA3]">(opsional)</span>
            </label>
            <input data-testid="pl-input-note" className="field py-2 text-[13px]"
              placeholder="Mis. penyesuaian harga triwulan 3" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          <p className="text-[10.5px] text-[#8E8E93]">
            Harga lama tidak hilang: ia ditutup pada tanggal mulai harga baru dan tetap
            terlihat di riwayat.
          </p>
        </div>
        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button data-testid="pl-setprice-save" className="primary-button" onClick={save} disabled={saving}>
            <Save size={14} /> {saving ? "Menyimpan…" : "Simpan harga"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Riwayat Harga Modal ─────────────────────────────────────────────────────
function HistoryModal({ row, entityId, entities, canManage, onClose, onChanged }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const res = await axios.get(`${API}/pricelist/records`,
        { params: { product_id: row.product_id, entity_id: entityId } });
      setRecords(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal memuat riwayat.");
    } finally {
      setLoading(false);
    }
  }, [row.product_id, entityId]);

  useEffect(() => { load(); }, [load]);

  const deactivate = async (id) => {
    try {
      await axios.delete(`${API}/pricelist/${id}`);
      load(); onChanged();
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal menonaktifkan harga.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="pl-history-modal">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl bg-white shadow-xl">
        <div className="flex items-center gap-2 border-b border-[#EFF0F2] px-4 py-3">
          <History size={16} className="text-[#6B219A]" />
          <h3 className="text-[14px] font-bold">Riwayat harga · {row.product_name}</h3>
          <EntityBadge entityId={entityId} entities={entities} />
          <button data-testid="pl-history-close" className="icon-button ml-auto" onClick={onClose} aria-label="Tutup">
            <X size={15} />
          </button>
        </div>
        <div className="overflow-auto p-4">
          <ErrorNotice message={err} onRetry={load} onDismiss={() => setErr("")} testId="pl-history-error" />
          {loading ? (
            <div className="grid gap-2">{[0, 1, 2].map((i) => <div key={i} className="h-9 animate-pulse rounded bg-[#F5F5F7]" />)}</div>
          ) : records.length === 0 ? (
            <div data-testid="pl-history-empty" className="py-8 text-center text-[12px] text-[#8E8E93]">
              Belum ada harga khusus badan usaha untuk produk ini — memakai harga global {formatCurrency(row.global_price)}.
            </div>
          ) : (
            <div className="overflow-auto rounded-md border border-[#EFF0F2]">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[10px] font-bold uppercase text-[#8E8E93]">
                    <th className="px-3 py-2 text-right">Harga</th>
                    <th className="px-3 py-2">Mulai</th>
                    <th className="px-3 py-2">Sampai</th>
                    <th className="px-3 py-2 text-center">Status</th>
                    <th className="px-3 py-2">Catatan</th>
                    {canManage && <th className="px-3 py-2"></th>}
                  </tr>
                </thead>
                <tbody>
                  {records.map((r) => {
                    const sm = STATUS_META[r.effective_status] || STATUS_META.inactive;
                    return (
                      <tr key={r.id} data-testid={`pl-hist-row-${r.id}`} className="border-b border-[#F5F5F7] last:border-0">
                        <td className="px-3 py-2 text-right font-semibold tabular-nums text-[#6B219A]">{formatCurrency(r.sell_price)}</td>
                        <td className="px-3 py-2">{fmtDate(r.valid_from)}</td>
                        <td className="px-3 py-2">{r.valid_until ? fmtDate(r.valid_until) : "∞"}</td>
                        <td className="px-3 py-2 text-center">
                          <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${sm.tone}`}>{sm.label}</span>
                        </td>
                        <td className="max-w-[160px] truncate px-3 py-2 text-[#6B6B73]" title={r.note}>{r.note || "—"}</td>
                        {canManage && (
                          <td className="px-3 py-2 text-right">
                            {r.status !== "inactive" && (
                              <button data-testid={`pl-deactivate-${r.id}`} className="text-[11px] text-[#C0392B] hover:underline"
                                onClick={() => deactivate(r.id)}>Nonaktifkan</button>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div className="flex justify-end border-t border-[#EFF0F2] px-4 py-3">
          <button className="primary-button" onClick={onClose}>Tutup</button>
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, icon: Icon, tone = "", testId }) {
  return (
    <div className="section-card" data-testid={testId}>
      <div className="section-body flex items-center gap-3 py-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#F3EAFB]">
          <Icon size={17} className="text-[#6B219A]" />
        </div>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
          <p className={`truncate text-[17px] font-bold tabular-nums ${tone || "text-[#1C1C1E]"}`}
            data-testid={`${testId}-value`}>{value}</p>
        </div>
      </div>
    </div>
  );
}
