import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { can } from "../../config/roles";
import {
  Boxes, Search, ChevronDown, ChevronRight, ArrowLeftRight,
  RefreshCw, PackageCheck, Truck, Clock3,
} from "lucide-react";
import { formatQty } from "../../utils/formatters";
// FASE E-7 (E7d) — isyarat "tersedia di badan usaha lain" tidak boleh berakhir buntu:
// dari baris inilah permintaan internal diajukan (dulu: WhatsApp ke rekan PT lain).
import InternalRequestCreateModal from "../internal_requests/InternalRequestCreateModal";

/**
 * Inventory Status Board (Sub-fase 1.4 — ATP & Fulfillment Modes, KN_16).
 * Ringkasan per produk: on_hand / available / reserved / incoming / ATP,
 * breakdown per entitas pemilik & gudang, plus indikator peluang inter-entitas.
 */
export default function InventoryStatusBoard({ currentUser, selectedEntity = "all", entities = [] }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState({});
  // E7d — permintaan internal dari baris papan stok (produk sudah jelas).
  const [requestFor, setRequestFor] = useState(null);   // { product_id, qty }
  const [pinToast, setPinToast] = useState("");
  // FASE E-8 (E8.8) — "Minta dari PT lain" dinyalakan izin `internal_request.create`
  // (sales mengajukan · Admin Sales menindak), bukan daftar peran yang harus disunting
  // setiap kali ada peran baru.
  const canRequest = can(currentUser?.permissions || {}, "internal_request", "create")
    && selectedEntity && selectedEntity !== "all";

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const params = selectedEntity && selectedEntity !== "all" ? { owner_entity_id: selectedEntity } : {};
      const res = await axios.get(`${API}/inventory/status-board`, { params });
      setRows(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Inventory Status Board.");
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [selectedEntity]);

  const filtered = useMemo(
    () => rows.filter((r) => `${r.product_name} ${r.sku}`.toLowerCase().includes(search.toLowerCase())),
    [rows, search]
  );

  const totals = useMemo(() => ({
    products: rows.length,
    interco: rows.filter((r) => r.has_intercompany_opportunity).length,
    atp: rows.reduce((s, r) => s + (r.total_atp || 0), 0),
    incoming: rows.reduce((s, r) => s + (r.total_incoming || 0), 0),
  }), [rows]);

  const toggle = (id) => setExpanded((e) => ({ ...e, [id]: !e[id] }));
  const entityName = selectedEntity !== "all"
    ? (entities.find((e) => e.id === selectedEntity)?.short_name || "")
    : "Semua Entitas";

  return (
    <div data-testid="inventory-status-board-view" className="grid gap-4">
      {/* Header */}
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <Boxes size={15} className="text-[#0058CC]" />
            <span className="kicker">Persediaan</span>
            <h2 data-testid="status-board-title">Papan Status Persediaan · ATP</h2>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 rounded-md border border-[#E5E5EA] bg-white px-2 py-1.5 min-w-[200px]">
              <Search size={14} className="text-[#6B6B73]" />
              <input
                data-testid="status-board-search"
                className="w-full bg-transparent text-[13px] outline-none"
                placeholder="Cari SKU / produk..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button data-testid="status-board-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
        <p className="px-4 py-2 text-[12px] text-[#6B6B73]">
          Konteks: <span className="font-semibold">{entityName}</span>. ATP = Available + Incoming (barang masuk / PO terbuka).
          Indikator <ArrowLeftRight size={11} className="inline -mt-0.5 text-[#6B219A]" /> = peluang pemenuhan lintas-entitas (inter-company).
        </p>
      </section>

      {/* Summary metrics */}
      <section data-testid="status-board-metrics" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric icon={Boxes} label="Produk" value={totals.products} tone="rgba(0,122,255,.12)" testId="sb-metric-products" />
        <Metric icon={Truck} label="Total Incoming" value={formatQty(totals.incoming)} tone="rgba(255,149,0,.16)" testId="sb-metric-incoming" />
        <Metric icon={PackageCheck} label="Total ATP" value={formatQty(totals.atp)} tone="rgba(52,199,89,.15)" testId="sb-metric-atp" />
        <Metric icon={ArrowLeftRight} label="Peluang Inter-Co" value={totals.interco} tone="rgba(175,82,222,.14)" testId="sb-metric-interco" />
      </section>

      {/* Table */}
      <section className="section-card">
        <div className="section-body overflow-x-auto">
          {loading && (
            <div data-testid="status-board-loading" className="animate-pulse py-10 text-center text-[13px] text-[#6B6B73]">
              Memuat status stok…
            </div>
          )}
          {!loading && error && (
            <div data-testid="status-board-error" className="rounded-md border border-[#F3C7C2] bg-[#FDF1F0] p-3 text-[12px] text-[#A8221A]">
              {error}
            </div>
          )}
          {!loading && !error && filtered.length === 0 && (
            <div data-testid="status-board-empty" className="py-10 text-center text-[13px] text-[#6B6B73]">
              Tidak ada produk yang cocok.
            </div>
          )}
          {!loading && !error && filtered.length > 0 && (
            <table data-testid="status-board-table" className="w-full border-collapse text-[12.5px]">
              <thead>
                <tr className="border-b border-[#EFF0F2] text-left text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
                  <th className="py-2 pl-1 pr-2">Produk</th>
                  <th className="px-2 text-right">Stok Fisik</th>
                  <th className="px-2 text-right">Tersedia</th>
                  <th className="px-2 text-right">Dipesan</th>
                  <th className="px-2 text-right">Incoming</th>
                  <th className="px-2 text-right">ATP</th>
                  <th className="px-2">Entitas</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <RowGroup key={r.product_id} row={r} open={!!expanded[r.product_id]}
                            onToggle={() => toggle(r.product_id)}
                            canRequest={canRequest}
                            onRequest={() => setRequestFor({
                              product_id: r.product_id,
                              qty: r.other_entities_available || "",
                            })} />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* E7d — satu klik dari isyarat "tersedia di badan usaha lain" ke permintaan resmi */}
      <InternalRequestCreateModal
        open={!!requestFor}
        prefillProductId={requestFor?.product_id || ""}
        prefillQty={requestFor?.qty || ""}
        onClose={() => setRequestFor(null)}
        onCreated={(doc) => {
          setRequestFor(null);
          setPinToast(`${doc.number} diajukan — menunggu ditindak admin/manajer `
            + `(Penjualan → Pesanan & Retur → Permintaan Internal).`);
          setTimeout(() => setPinToast(""), 6000);
        }}
      />
      {pinToast && (
        <div className="notice-bar success" data-testid="status-board-pin-toast">
          <span>{pinToast}</span><button onClick={() => setPinToast("")}>×</button>
        </div>
      )}
    </div>
  );
}

function Metric({ icon: Icon, label, value, tone, testId }) {
  return (
    <div data-testid={testId} className="metric-card">
      <div className="metric-icon" style={{ background: tone }}>
        <Icon size={17} className="text-[#1C1C1E]" />
      </div>
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
        <p className="text-[17px] font-bold tabular-nums">{value}</p>
      </div>
    </div>
  );
}

function RowGroup({ row, open, onToggle, canRequest = false, onRequest }) {
  return (
    <>
      <tr
        data-testid={`status-board-row-${row.product_id}`}
        className="cursor-pointer border-b border-[#F4F5F7] hover:bg-[#FAFBFC]"
        onClick={onToggle}
      >
        <td className="py-2.5 pl-1 pr-2">
          <div className="flex items-center gap-1.5">
            {open ? <ChevronDown size={14} className="text-[#8E8E93]" /> : <ChevronRight size={14} className="text-[#8E8E93]" />}
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-wide text-[#0058CC]">{row.sku}</p>
              <p className="truncate font-semibold">{row.product_name}</p>
            </div>
          </div>
        </td>
        <td className="px-2 text-right tabular-nums">{formatQty(row.total_on_hand)}</td>
        <td className="px-2 text-right font-semibold tabular-nums text-[#126E2C]">{formatQty(row.total_available)}</td>
        <td className="px-2 text-right tabular-nums text-[#6B219A]">{formatQty(row.total_reserved)}</td>
        <td className="px-2 text-right tabular-nums text-[#8C4A00]">{formatQty(row.total_incoming)}</td>
        <td className="px-2 text-right font-bold tabular-nums">{formatQty(row.total_atp)}</td>
        <td className="px-2">
          <div className="flex flex-wrap items-center gap-1">
            {row.by_entity.map((e) => (
              <span key={e.entity_id} className="status-pill fmode-from_stock">{e.entity_name}</span>
            ))}
            {/* FASE E-0/E-5 (E5.1) — isyarat "tersedia di badan usaha lain" TANPA
                membocorkan rincian gudang PT lain (keputusan pemilik #1). */}
            {row.has_intercompany_opportunity && (
              <span
                data-testid={`status-board-interco-${row.product_id}`}
                className="status-pill fmode-inter_company"
                title={row.detail_scope === "own_entity"
                  ? `Tersedia ${formatQty(row.other_entities_available)} di badan usaha lain — minta lewat Admin Sales`
                  : "Peluang pemenuhan antar badan usaha"}
              >
                <ArrowLeftRight size={11} /> Inter-Co
                {row.detail_scope === "own_entity" && row.other_entities_available > 0 && (
                  <span className="ml-1 tabular-nums">{formatQty(row.other_entities_available)}</span>
                )}
              </span>
            )}
          </div>
        </td>
      </tr>
      {open && (
        <tr data-testid={`status-board-detail-${row.product_id}`} className="border-b border-[#EFF0F2] bg-[#FAFBFC]">
          <td colSpan={7} className="px-3 py-3">
            <div className="grid gap-2">
              {row.by_entity.length === 0 && (
                <p className="text-[12px] text-[#6B6B73]">Belum ada stok / incoming untuk produk ini.</p>
              )}
              {row.detail_scope === "own_entity" && (
                <div
                  data-testid={`status-board-scope-note-${row.product_id}`}
                  className="rounded-md border border-[#C9DBF7] bg-[#F2F7FF] px-2.5 py-2 text-[11px] text-[#1C1C1E]"
                >
                  Rincian gudang yang tampil hanya milik <b>badan usaha Anda</b>.
                  {row.other_entities_available > 0 ? (
                    <> Total di badan usaha lain: <b className="tabular-nums">{formatQty(row.other_entities_available)}</b>{" "}
                      (angka gabungan, tanpa rincian gudang).</>
                  ) : (
                    <> Tidak ada stok tambahan di badan usaha lain.</>
                  )}
                  {/* FASE E-7 (E7d) — isyarat ini DULU berakhir buntu ("minta lewat Admin
                      Sales" tanpa tombol). Sekarang satu klik membuat permintaan resmi
                      yang masuk antrean & tercatat. */}
                  {row.other_entities_available > 0 && canRequest && (
                    <button
                      data-testid={`status-board-request-${row.product_id}`}
                      className="btn-primary btn-xs ml-2 mt-1 inline-flex items-center gap-1"
                      onClick={(e) => { e.stopPropagation(); onRequest?.(); }}
                    >
                      <ArrowLeftRight size={11} /> Minta dari badan usaha lain
                    </button>
                  )}
                  {row.other_entities_available > 0 && !canRequest && (
                    <span className="ml-1 text-[10.5px] text-[#6B6B73]">
                      {" "}Butuh barangnya? Pilih badan usaha Anda dulu (mode gabungan hanya
                      untuk melihat), lalu tekan <b>Minta dari badan usaha lain</b>.
                    </span>
                  )}
                </div>
              )}
              {row.by_entity.map((e) => (
                <div key={e.entity_id} className="rounded-md border border-[#EFF0F2] bg-white p-2.5">
                  <div className="flex items-center justify-between">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-[#1C1C1E]">{e.entity_name}</p>
                    <p className="text-[11px] text-[#6B6B73] tabular-nums">
                      ATP <span className="font-bold text-[#1C1C1E]">{formatQty(e.atp)}</span>
                    </p>
                  </div>
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full text-[11.5px]">
                      <thead>
                        <tr className="text-left text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">
                          <th className="py-1 pr-2">Gudang</th>
                          <th className="px-2 text-right">Stok Fisik</th>
                          <th className="px-2 text-right">Tersedia</th>
                          <th className="px-2 text-right">Dipesan</th>
                          <th className="px-2 text-right">Incoming</th>
                          <th className="px-2 text-right">ATP</th>
                        </tr>
                      </thead>
                      <tbody>
                        {e.by_warehouse.map((w) => (
                          <tr key={w.warehouse_id} className="border-t border-[#F4F5F7]">
                            <td className="py-1 pr-2">{w.warehouse_name}<span className="ml-1 text-[#8E8E93]">{w.warehouse_city}</span></td>
                            <td className="px-2 text-right tabular-nums">{formatQty(w.on_hand)}</td>
                            <td className="px-2 text-right tabular-nums text-[#126E2C]">{formatQty(w.available)}</td>
                            <td className="px-2 text-right tabular-nums text-[#6B219A]">{formatQty(w.reserved)}</td>
                            <td className="px-2 text-right tabular-nums text-[#8C4A00]">{formatQty(w.incoming)}</td>
                            <td className="px-2 text-right font-semibold tabular-nums">{formatQty(w.atp)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
